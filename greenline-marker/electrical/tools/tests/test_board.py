"""Board builder: files, rules, placement, coordinate convention, determinism."""
import hashlib
import json
import math
import os
import re

import pytest

from gleda import board, coords, geometry, kicad_cli
from gleda.model import Design, Outline, Circle, Part, Track, Via, BOTTOM, TOP

C0402 = "Capacitor_SMD:C_0402_1005Metric"
R0402 = "Resistor_SMD:R_0402_1005Metric"


def _md5(path):
    with open(path, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()


@pytest.fixture(scope="module")
def summary(built_mini):
    design, files = built_mini
    return board.board_summary(files.pcb)


def test_files_written(built_mini):
    design, files = built_mini
    assert os.path.basename(files.pcb) == "mini.kicad_pcb"
    assert os.path.exists(files.pcb) and os.path.exists(files.pro)
    assert os.path.isdir(files.lib_dir)
    assert sorted(os.listdir(files.lib_dir)) == [
        "BatteryTab_2x3mm.kicad_mod", "MiniModule_7x9.kicad_mod", "NPTH_1.2mm.kicad_mod",
        "TestPad_D1mm.kicad_mod"]
    table = open(files.lib_table).read()
    assert '(name "gleda")' in table and "${KIPRJMOD}/gleda.pretty" in table
    # SaveBoard side effects are suppressed: no local settings file
    assert not os.path.exists(os.path.splitext(files.pcb)[0] + ".kicad_prl")


def test_stackup_and_layers_in_board_file(built_mini, summary):
    design, files = built_mini
    text = open(files.pcb).read()
    assert "(thickness 0.8)" in text
    assert '(layer "In1.Cu" (type "copper") (thickness 0.0175))' in text
    assert '(layer "dielectric 2" (type "core") (thickness 0.455)' in text
    assert '(copper_finish "ENIG")' in text
    order = [m for m in re.findall(r'\(layer "([^"]+)" \(type', text)]
    assert order == [l.name for l in design.stackup.layers]
    assert summary["copper_layers"] == 4
    assert summary["thickness"] == pytest.approx(0.8)


def test_rules_are_loaded_by_kicad_from_project(summary):
    assert summary["rules"] == {
        "min_clearance": 0.127, "min_track": 0.127, "min_annular": 0.125,
        "min_via_diameter": 0.5, "min_drill": 0.25, "hole_to_hole": 0.25,
        "hole_clearance": 0.2, "copper_to_edge": 0.3}


def test_netclass_assignment(summary):
    nc = summary["netclasses"]
    assert nc["GND"] == "Power" and nc["+3V0"] == "Power" and nc["VBAT"] == "Power"
    assert nc["SCK"] == "Default" and nc["D0"] == "Default"


def test_netclass_patterns_match_exactly_one_net(tmp_path):
    d = Design("pat", Circle(0, 0, 6))
    d.add(Part("R1", "1k", R0402, mpn="X", x=-2, y=0), Part("R2", "1k", R0402, mpn="X", x=2, y=0),
          Part("R3", "1k", R0402, mpn="X", x=0, y=2), Part("R4", "1k", R0402, mpn="X", x=0, y=-2))
    d.net("GND", "R1.1", "R2.1", netclass="Power")
    d.net("GND2", "R1.2", "R2.2")                   # must NOT inherit GND's class
    d.net("D[0]", "R3.1", "R4.1", netclass="Power")  # regex meta characters in the name
    d.net("D00", "R3.2", "R4.2")
    files = board.build_board(d, str(tmp_path))
    nc = board.board_summary(files.pcb)["netclasses"]
    assert nc == {"GND": "Power", "GND2": "Default", "D[0]": "Power", "D00": "Default"}


def test_project_file_content(built_mini):
    design, files = built_mini
    pro = json.load(open(files.pro))
    ds = pro["board"]["design_settings"]
    sev = ds["rule_severities"]
    for check in board.CORE_ERROR_CHECKS:
        assert sev[check] == "error", check
    assert sev["lib_footprint_issues"] == "ignore"
    assert set(board.SEVERITY_OVERRIDES) == {"lib_footprint_issues", "lib_footprint_mismatch"}
    changed = {k for k, v in sev.items() if board.DEFAULT_SEVERITIES[k] != v}
    assert changed == set(board.SEVERITY_OVERRIDES)        # nothing else was relaxed
    assert ds["rules"]["min_copper_edge_clearance"] == 0.3
    assert ds["rules"]["allow_blind_buried_vias"] is False
    classes = {c["name"]: c for c in pro["net_settings"]["classes"]}
    assert classes["Default"]["track_width"] == 0.15 and classes["Power"]["track_width"] == 0.3
    assert classes["Default"]["via_diameter"] == 0.5 and classes["Default"]["via_drill"] == 0.25
    pats = {p["pattern"]: p["netclass"] for p in pro["net_settings"]["netclass_patterns"]}
    assert pats == {"GND": "Power", "VBAT": "Power", "\\+3V0": "Power"}
    assert pro["meta"]["filename"] == "mini.kicad_pro"


def test_write_project_keeps_foreign_sections(tmp_path, mini):
    path = str(tmp_path / "mini.kicad_pro")
    with open(path, "w") as fh:
        json.dump({"schematic": {"drawing": {"x": 1}}, "sheets": [["abc", ""]],
                   "board": {"junk": True}}, fh)
    board.write_project(mini, path)
    pro = json.load(open(path))
    assert pro["schematic"] == {"drawing": {"x": 1}} and pro["sheets"] == [["abc", ""]]
    assert "junk" not in pro["board"] and "design_settings" in pro["board"]


def test_footprint_placement_matches_design(built_mini, summary):
    design, files = built_mini
    fps = summary["footprints"]
    assert set(fps) == {p.ref for p in design.parts} | {"H1", "H2"}
    for part in design.parts:
        fp = fps[part.ref]
        assert fp["side"] == part.side, part.ref
        assert (fp["x"], fp["y"]) == pytest.approx((part.x, part.y)), part.ref
        # the stored KiCad orientation IS the design rotation, on both sides
        assert fp["rotation"] == pytest.approx(coords.normalize_angle(part.rotation)), part.ref
        assert fp["value"] == part.value
    assert fps["U1"]["lib_id"] == "gleda:MiniModule_7x9"
    assert fps["C1"]["lib_id"] == C0402
    assert (fps["H1"]["x"], fps["H1"]["y"]) == (-11.5, 5.0)
    assert fps["H1"]["lib_id"] == "gleda:NPTH_1.2mm"


def test_pads_match_model_geometry(built_mini, summary):
    """Pad positions, nets and layers predicted by the pure-Python model are
    exactly what pcbnew reports for the saved board (top and bottom side)."""
    design, files = built_mini
    model = {}
    for pad in geometry.placed_pads(design):
        model.setdefault((pad.ref, pad.number), []).append(pad)
    n = 0
    for ref, fp in summary["footprints"].items():
        if ref.startswith("H"):
            continue
        for pad in fp["pads"]:
            cands = model[(ref, pad["number"])]
            best = min(cands, key=lambda c: math.hypot(c.x - pad["x"], c.y - pad["y"]))
            assert math.hypot(best.x - pad["x"], best.y - pad["y"]) < 1e-6, (ref, pad)
            assert (best.net or "") == pad["net"], (ref, pad)
            assert list(best.layers) == pad["layers"], (ref, pad)
            n += 1
    assert n == sum(len(v) for v in model.values()) == 78
    # bottom-side SMD pads are on B.Cu, top-side ones on F.Cu
    assert {tuple(p.layers) for p in model[("U2", "1")]} == {("B.Cu",)}
    assert {tuple(p.layers) for p in model[("U1", "1")]} == {("F.Cu",)}


def test_bottom_side_convention_explicit(tmp_path):
    """R_0402 pad 1 is at local (-0.51, 0).  Bottom side, rotation 90: flip
    about the local X axis (no change for this pad), then rotate CCW seen from
    the top -> pad 1 ends up BELOW the part centre."""
    d = Design("flip", Circle(0, 0, 8))
    d.add(Part("R1", "1k", R0402, mpn="X", x=2.0, y=3.0, rotation=90.0, side=BOTTOM),
          Part("R2", "1k", R0402, mpn="X", x=-2.0, y=-3.0, rotation=90.0, side=TOP),
          Part("U1", "IMU", "Package_LGA:Bosch_LGA-14_3x2.5mm_P0.5mm",
               pins={str(i): str(i) for i in range(1, 15)}, mpn="X", x=-3.0, y=3.0,
               rotation=0.0, side=BOTTOM))
    d.net("A", "R1.1", "R2.1", "U1.1")
    d.net("B", "R1.2", "R2.2", "U1.2")
    assert geometry.pad_position(d, "R1", "1") == pytest.approx((2.0, 3.0 - 0.51))
    assert geometry.pad_position(d, "R2", "1") == pytest.approx((-2.0, -3.0 - 0.51))
    # LGA pin 1 is top-left on the top side; flipped to the bottom (seen from
    # the top, through the board) it appears bottom-left
    x1, y1 = geometry.pad_position(d, "U1", "1")
    assert x1 < -3.0 and y1 < 3.0
    files = board.build_board(d, str(tmp_path))
    fps = board.board_summary(files.pcb)["footprints"]
    for ref in ("R1", "R2", "U1"):
        for pad in fps[ref]["pads"]:
            assert (pad["x"], pad["y"]) == pytest.approx(
                geometry.pad_position(d, ref, pad["number"])), (ref, pad)
    assert fps["R1"]["side"] == "bottom" and fps["R1"]["rotation"] == 90.0
    assert fps["R1"]["pads"][0]["layers"] == ["B.Cu"]


def test_zones_and_keepouts(summary):
    zones = {z["name"]: z for z in summary["zones"]}
    assert zones["GND_In1.Cu"]["net"] == "GND" and zones["GND_In1.Cu"]["layers"] == ["In1.Cu"]
    assert zones["+3V0_In2.Cu"]["net"] == "+3V0" and zones["+3V0_In2.Cu"]["layers"] == ["In2.Cu"]
    assert not zones["GND_In1.Cu"]["rule_area"]
    assert zones["antenna"]["rule_area"]
    assert zones["antenna"]["layers"] == ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
    assert zones["spring"]["rule_area"] and zones["spring"]["layers"] == ["B.Cu"]


def test_keepout_flags_in_file(built_mini):
    design, files = built_mini
    text = open(files.pcb).read()
    i = text.index('(name "antenna")')
    block = text[i:i + 400]
    assert "(tracks not_allowed)" in block and "(vias not_allowed)" in block
    assert "(copperpour not_allowed)" in block and "(footprints allowed)" in block
    j = text.index('(name "spring")')
    block = text[j:j + 400]
    assert "(tracks allowed)" in block and "(footprints not_allowed)" in block


def test_edge_cuts_geometry(built_mini, summary):
    design, files = built_mini
    x0, y0, x1, y1 = summary["edge_bbox"]
    half = board.EDGE_WIDTH_MM / 2
    assert (x0, x1, y1) == pytest.approx((-15 - half, 15 + half, 15 + half), abs=1e-3)
    assert y0 > -15.0                                 # the notch removed the lowest point
    text = open(files.pcb).read()
    assert text.count("(gr_circle") == 1              # the internal round cutout, exact
    assert "(gr_circle (center 108 100) (end 111 100)" in text
    assert text.count("(gr_arc") == 5                 # 1 outline + 2 notch corners + 2 slot ends
    assert "gr_poly" not in text
    assert summary["aux_origin"] == [0.0, 0.0]        # drill/place origin = board centre


def test_footprint_properties_and_attributes(built_mini):
    design, files = built_mini
    text = open(files.pcb).read()
    assert '(property "MPN" "BMI270")' in text
    assert '(property "Manufacturer" "Bosch")' in text
    assert '(property "Distributor PN" "828-BMI270CT-ND")' in text
    i = text.index('(footprint "gleda:TestPad_D1mm"')
    assert "exclude_from_pos_files exclude_from_bom" in text[i:i + 400]
    # reference designators are hidden on silk by default
    j = text.index('(fp_text reference "U1"')
    assert "hide" in text[j:j + 80]


def test_build_is_deterministic(tmp_path, mini):
    from mini_design import mini_design
    a = board.build_board(mini, str(tmp_path / "a"))
    b = board.build_board(mini_design(), str(tmp_path / "b"))
    assert _md5(a.pcb) == _md5(b.pcb)
    assert _md5(a.pro) == _md5(b.pro)
    for name in os.listdir(a.lib_dir):
        assert _md5(os.path.join(a.lib_dir, name)) == _md5(os.path.join(b.lib_dir, name))
    # rebuilding into the same directory gives the same bytes again
    before = _md5(a.pcb)
    board.build_board(mini_design(), str(tmp_path / "a"))
    assert _md5(a.pcb) == before
    assert "tstamp" in open(a.pcb).read()


def test_unbuildable_designs_raise(tmp_path, mini):
    mini.part("C1").x = None
    with pytest.raises(board.BoardBuildError, match="C1 has no placement"):
        board.build_board(mini, str(tmp_path / "a"))
    mini.part("C1").x = -9.3
    mini.add(Part("C1", "1u", C0402, mpn="X", x=0, y=-12))
    with pytest.raises(board.BoardBuildError, match="duplicate reference C1"):
        board.build_board(mini, str(tmp_path / "b"))
    d = Design("nofp", Circle(0, 0, 5))
    d.add(Part("X1", "?", "Capacitor_SMD:Nope", mpn="X", x=0, y=0))
    with pytest.raises(board.BoardBuildError, match="Nope"):
        board.build_board(d, str(tmp_path / "c"))


# -- orientation: KiCad plots must show +y UP --------------------------------

@pytest.fixture(scope="module")
def orient_board(tmp_path_factory):
    d = Design("orient", Outline(Circle(0, 0, 10)))
    d.add(Part("C1", "1u", C0402, mpn="X", x=4.0, y=6.0, side=TOP),
          Part("C2", "1u", C0402, mpn="X", x=-5.0, y=-3.0, side=BOTTOM))
    d.net("A", "C1.1", "C2.1")
    d.net("B", "C1.2", "C2.2")
    out = tmp_path_factory.mktemp("orient")
    return d, board.build_board(d, str(out))


def _copper_centre(svg_path):
    """Centre of the copper drawn in an SVG, in design coordinates, using the
    plotted board outline circle (r = 10) as the reference frame."""
    text = open(svg_path).read()
    elements = kicad_cli.svg_elements(text)
    edge = [(c, d) for c, k, d in elements if k == "circle" and abs(d[2] - 10.0) < 1e-3]
    assert len(edge) == 1, "board outline circle not found in SVG"
    edge_color, (cx, cy, _r) = edge[0]
    boxes = kicad_cli.svg_color_bboxes(text)
    copper = [b for color, b in boxes.items() if color != edge_color]
    assert len(copper) == 1
    x0, y0, x1, y1 = copper[0]
    sx, sy = (x0 + x1) / 2, (y0 + y1) / 2
    return (sx - cx, cy - sy), (sy < cy)          # SVG y grows downward


def test_top_view_svg_has_plus_y_up(orient_board, tmp_path):
    d, files = orient_board
    svg = kicad_cli.export_svg(files.pcb, str(tmp_path / "top.svg"), ["F.Cu", "Edge.Cuts"])
    (x, y), in_upper_half = _copper_centre(svg)
    assert in_upper_half, "a part placed at +y must be drawn in the upper half"
    assert (x, y) == pytest.approx((4.0, 6.0), abs=0.02)
    text = open(svg).read()
    assert "<title>top.svg</title>" in text           # no timestamp in the file


def test_bottom_layer_svg_seen_from_top_and_mirrored(orient_board, tmp_path):
    d, files = orient_board
    svg = kicad_cli.export_svg(files.pcb, str(tmp_path / "bot.svg"), ["B.Cu", "Edge.Cuts"])
    (x, y), in_upper_half = _copper_centre(svg)
    assert not in_upper_half
    assert (x, y) == pytest.approx((-5.0, -3.0), abs=0.02)      # x-ray view from the top
    svg_m = kicad_cli.export_svg(files.pcb, str(tmp_path / "bot_m.svg"),
                                 ["B.Cu", "Edge.Cuts"], mirror=True)
    (xm, ym), _ = _copper_centre(svg_m)
    assert (xm, ym) == pytest.approx((5.0, -3.0), abs=0.02)     # as seen from below


def test_export_svg_requires_layers(orient_board, tmp_path):
    d, files = orient_board
    with pytest.raises(ValueError):
        kicad_cli.export_svg(files.pcb, str(tmp_path / "x.svg"), [])


# -- routing primitives -------------------------------------------------------

def test_apply_and_read_routing_round_trip(tmp_path, mini):
    files = board.build_board(mini, str(tmp_path))
    a = geometry.pad_position(mini, "R1", "2")
    b = geometry.pad_position(mini, "D1", "2")
    tracks = [Track("LED1_A", "F.Cu", a[0], a[1], a[0], -5.6, 0.15),
              Track("LED1_A", "F.Cu", a[0], -5.6, b[0], -5.6, 0.15),
              Track("LED1_A", "F.Cu", b[0], -5.6, b[0], b[1], 0.15)]
    vias = [Via("GND", -10.3, 4.48, 0.5, 0.25)]
    result = board.apply_routing(files.pcb, tracks, vias)
    assert (result.tracks, result.vias, result.renetted) == (3, 1, [])
    n_tracks, n_vias = result                               # tuple-style unpacking
    assert (n_tracks, n_vias) == (3, 1)
    got_tracks, got_vias = board.read_routing(files.pcb)
    assert sorted(got_tracks, key=lambda t: (t.x1, t.y1, t.x2)) == \
        sorted(tracks, key=lambda t: (t.x1, t.y1, t.x2))
    assert got_vias == vias
    s = board.board_summary(files.pcb)
    assert (s["track_count"], s["via_count"]) == (3, 1)
    # replace=True drops the old routing, replace=False appends
    board.apply_routing(files.pcb, tracks[:1], [])
    assert board.board_summary(files.pcb)["track_count"] == 1
    board.apply_routing(files.pcb, tracks[1:], vias, replace=False)
    s = board.board_summary(files.pcb)
    assert (s["track_count"], s["via_count"]) == (3, 1)
    # the project file is never touched by saving a board
    assert not os.path.exists(os.path.splitext(files.pcb)[0] + ".kicad_prl")


def test_apply_routing_reports_silently_merged_nets(tmp_path, mini):
    """KiCad re-nets touching tracks that hang on no pad; this must not go
    unnoticed."""
    files = board.build_board(mini, str(tmp_path))
    crossing = [Track("D0", "F.Cu", 6.0, 4.0, 9.0, 4.0, 0.15),
                Track("D1", "F.Cu", 7.5, 3.5, 7.5, 6.0, 0.15)]
    with pytest.raises(board.BoardBuildError, match="re-assigned the net"):
        board.apply_routing(files.pcb, crossing, [])
    result = board.apply_routing(files.pcb, crossing, [], strict=False)
    assert len(result.renetted) == 1
    requested, actual = result.renetted[0]
    assert {requested.net, actual} == {"D0", "D1"}


def test_apply_routing_unknown_net(tmp_path, mini):
    files = board.build_board(mini, str(tmp_path))
    with pytest.raises(board.BoardBuildError, match="unknown net"):
        board.apply_routing(files.pcb, [Track("NOPE", "F.Cu", 0, 0, 1, 0, 0.15)], [])


def test_design_tracks_are_written_by_build(tmp_path, mini):
    mini.vias.append(Via("GND", -10.3, 4.48, 0.5, 0.25))
    files = board.build_board(mini, str(tmp_path))
    assert board.board_summary(files.pcb)["via_count"] == 1


def test_load_board_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        board.load_board(str(tmp_path / "nope.kicad_pcb"))


# -- variants -----------------------------------------------------------------

def test_two_layer_board_with_through_hole_part(tmp_path):
    from gleda import checks, drc
    d = Design("two", Outline(Circle(0, 0, 8)), layers=2, board_thickness=1.6)
    hdr = "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical"
    d.add(Part("J1", "HDR", hdr, mpn="X", x=-3.0, y=1.27, height_mm=8.5),
          Part("R1", "1k", R0402, mpn="X", x=2.0, y=0.0, height_mm=0.4),
          # a bottom-side part under the header would collide with its pins
          Part("R2", "1k", R0402, mpn="X", x=2.0, y=-3.0, side=BOTTOM, height_mm=0.4))
    d.net("A", "J1.1", "R1.1", "R2.1")
    d.net("B", "J1.2", "R1.2", "R2.2")
    assert checks.run_checks(d).ok
    files = board.build_board(d, str(tmp_path))
    s = board.board_summary(files.pcb)
    assert s["copper_layers"] == 2 and s["thickness"] == pytest.approx(1.6)
    pads = {p.number: p for p in geometry.part_pads(d, d.part("J1"))}
    assert pads["1"].layers == ("F.Cu", "B.Cu") and pads["1"].kind == "th"
    assert pads["1"].drill == pytest.approx(1.0)
    assert s["footprints"]["J1"]["pads"][0]["layers"] == ["F.Cu", "B.Cu"]
    text = open(files.pcb).read()
    assert '(layer "dielectric 1" (type "core")' in text and "In1.Cu" not in text
    r = drc.run_drc(files.pcb)
    assert r.error_count == 0 and r.unconnected_count == 4
    # through-hole parts block both sides for the courtyard check
    d.part("R2").place(-3.0, 0.0, side=BOTTOM)
    assert checks.run_checks(d).has("courtyard_overlap")


def test_four_layer_through_pad_is_on_all_copper_layers(tmp_path):
    d = Design("th4", Outline(Circle(0, 0, 8)))
    hdr = "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical"
    d.add(Part("J1", "HDR", hdr, mpn="X", x=0.0, y=1.27, side=BOTTOM),
          Part("R1", "1k", R0402, mpn="X", x=4.0, y=0.0))
    d.net("A", "J1.1", "R1.1")
    d.net("B", "J1.2", "R1.2")
    files = board.build_board(d, str(tmp_path))
    model = geometry.part_pads(d, d.part("J1"))
    assert model[0].layers == ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")
    got = board.board_summary(files.pcb)["footprints"]["J1"]["pads"]
    assert got[0]["layers"] == ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
    for pad in got:
        assert (pad["x"], pad["y"]) == pytest.approx(geometry.pad_position(d, "J1", pad["number"]))


def test_split_plane_with_priority_and_thermal(tmp_path, mini):
    from gleda import drc
    from gleda.model import RoundedPolygon
    # a VBAT island inside the +3V0 plane on In2, plus a thermal GND pour on B.Cu
    mini.add_plane("VBAT", "In2.Cu", RoundedPolygon.rect(4.0, -9.0, 9.0, 5.0, 0.5),
                   priority=1, name="VBAT_island")
    mini.add_plane("GND", "B.Cu", thermal=True, keep_islands=True)
    files = board.build_board(mini, str(tmp_path))
    r = drc.run_drc(files.pcb)
    assert r.error_count == 0, r.summary()
    assert r.zones_filled == 4
    zones = {z["name"]: z for z in board.board_summary(files.pcb)["zones"]}
    assert zones["VBAT_island"]["net"] == "VBAT" and zones["VBAT_island"]["filled"]
    text = open(files.pcb).read()
    i = text.index('(name "VBAT_island")')
    assert "(priority 1)" in text[i - 300:i + 300]
    # the B.Cu pour reaches the bottom-side GND pads: fewer missing links
    assert r.unconnected_count < 52


def test_silk_refs_option(tmp_path, mini):
    mini.silk_refs = True
    files = board.build_board(mini, str(tmp_path))
    text = open(files.pcb).read()
    j = text.index('(fp_text reference "U1"')
    assert "hide" not in text[j:j + 80]


def test_six_layer_stackup(tmp_path):
    d = Design("six", Outline(Circle(0, 0, 6)), layers=6, board_thickness=1.2)
    d.add(Part("R1", "1k", R0402, mpn="X", x=0, y=0), Part("R2", "1k", R0402, mpn="X", x=0, y=2))
    d.net("A", "R1.1", "R2.1")
    d.net("B", "R1.2", "R2.2")
    d.add_plane("A", "In3.Cu")
    files = board.build_board(d, str(tmp_path))
    s = board.board_summary(files.pcb)
    assert s["copper_layers"] == 6 and s["thickness"] == pytest.approx(1.2)
    assert s["zones"][0]["layers"] == ["In3.Cu"]
