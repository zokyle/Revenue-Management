"""Manufacturing outputs: Gerber / Excellon readers, BOM, pick-and-place,
mechanical JSON, renders, and the checks that compare what was plotted with
the design model (including that they really catch differences)."""
import csv
import hashlib
import json
import os
import zipfile

import pytest

from gleda import board, drc, geometry, outputs
from gleda import footprints as F
from gleda.model import (Design, Outline, Circle, RoundedPolygon, Part, Track, Via, two_pin,
                         BOTTOM, US_4L_FINE)

R0402 = "Resistor_SMD:R_0402_1005Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"


# --------------------------------------------------------------------------
# readers (hand-written files)
# --------------------------------------------------------------------------

GERBER = """%TF.GenerationSoftware,KiCad,Pcbnew,7.0.11*%
%TF.CreationDate,2026-11-11T17:19:01+00:00*%
%TF.FileFunction,Profile,NP*%
%FSLAX46Y46*%
G04 Gerber Fmt 4.6, Leading zero omitted, Abs format (unit mm)*
G04 Created by KiCad (PCBNEW 7.0.11) date 2026-11-11 17:19:01*
%MOMM*%
%LPD*%
G01*
%ADD10C,0.050000*%
D10*
X-3000000Y4000000D02*
G75*
G03*
X3000000Y4000000I3000000J-4000000D01*
G01*
X-3000000Y4000000D01*
X1000000Y1000000D03*
Y-2000000D03*
G36*
X0Y0D02*
X500000Y0D01*
X500000Y500000D01*
X0Y0D01*
G37*
M02*
"""


def test_read_gerber_arcs_flashes_and_modal_coordinates(tmp_path):
    path = tmp_path / "x-Edge_Cuts.gbr"
    path.write_text(GERBER)
    g = outputs.read_gerber(str(path))
    assert g.file_function == "Profile,NP"
    # a 5 mm radius arc from (-3, 4) counter-clockwise the long way round to
    # (3, 4): it passes x = -5, y = -5 and x = +5; the chord closes it at y = 4
    assert g.bounds == pytest.approx((-5.0, -5.0, 5.0, 4.0))
    assert g.flashes == [(1.0, 1.0), (1.0, -2.0)]            # modal X
    assert g.regions == 1 and g.draws == 5
    assert (-3.0, 4.0) in g.vertices and (3.0, 4.0) in g.vertices
    bad = tmp_path / "bad.gbr"
    bad.write_text("G04 nothing*\nM02*\n")
    with pytest.raises(outputs.OutputError):
        outputs.read_gerber(str(bad))


def test_arc_extents_respect_direction():
    # quarter arc from (1, 0) to (0, 1) about the origin
    ccw = outputs._arc_extents(1, 0, 0, 1, 0, 0, clockwise=False)
    cw = outputs._arc_extents(1, 0, 0, 1, 0, 0, clockwise=True)
    assert min(p[0] for p in ccw) == pytest.approx(0.0)
    assert min(p[0] for p in cw) == pytest.approx(-1.0)       # the long way round
    assert min(p[1] for p in cw) == pytest.approx(-1.0)


EXCELLON = """M48
; DRILL file {KiCad 7.0.11} date Wed Nov 11 17:19:01 2026
; FORMAT={-:-/ absolute / metric / decimal}
; #@! TF.CreationDate,2026-11-11T17:19:01+00:00
; #@! TF.FileFunction,Plated,1,4,PTH
FMAT,2
METRIC
T1C0.250
T2C0.900
%
G90
G05
T1
X-18.55Y1.35
X0.0Y-5.0
T2
X1.5Y2.5
X3.0Y4.0G85X5.0Y4.0
T0
M30
"""


def test_read_excellon_and_strip_dates(tmp_path):
    path = tmp_path / "x-PTH.drl"
    path.write_text(EXCELLON)
    d = outputs.read_excellon(str(path))
    assert d.plated is True
    assert d.hits == [(0.25, -18.55, 1.35), (0.25, 0.0, -5.0), (0.9, 1.5, 2.5)]
    assert d.slots == [(0.9, 3.0, 4.0, 5.0, 4.0)]
    assert d.table() == [(0.25, 2), (0.9, 2)]
    outputs.strip_dates(str(path))
    text = path.read_text()
    assert "2026" not in text and "CreationDate" not in text
    assert "; DRILL file {KiCad 7.0.11}\n" in text
    assert outputs.read_excellon(str(path)).hits == d.hits     # nothing else changed
    g = tmp_path / "x.gbr"
    g.write_text(GERBER)
    outputs.strip_dates(str(g))
    text = g.read_text()
    assert "2026" not in text and "G04 Created by KiCad (PCBNEW 7.0.11)*" in text
    once = text
    outputs.strip_dates(str(g))
    assert g.read_text() == once                                # idempotent
    job = tmp_path / "x-job.gbrjob"
    job.write_text(json.dumps({"Header": {"CreationDate": "2026-11-11", "x": 1}, "y": 2}))
    outputs.strip_dates(str(job))
    assert json.loads(job.read_text()) == {"Header": {"x": 1}, "y": 2}
    inch = tmp_path / "inch.drl"
    inch.write_text("M48\nINCH\n%\nM30\n")
    with pytest.raises(outputs.OutputError):
        outputs.read_excellon(str(inch))


# --------------------------------------------------------------------------
# BOM, positions, netlist (model only)
# --------------------------------------------------------------------------

def _bom_design():
    d = Design("bom", Outline(Circle(0, 0, 10)))

    def res(ref, value, mpn, price, **kw):
        return Part(ref, value, R0402, pins=two_pin(), mpn=mpn, manufacturer="Yageo",
                    distributor="Digi-Key", distributor_pn=mpn + "-ND", unit_price=price,
                    x=0.0, y=float(len(d.parts)), **kw)
    d.add(res("R10", "10k", "RC10K", 0.01), res("R2", "10k", "RC10K", 0.01),
          res("R1", "10k", "RC10K", 0.01), res("R3", "1k", "RC1K", 0.02),
          res("R4", "10k", "RC10K", 0.01, dnp=True),
          res("R5", "10k", "RC10K-ALT", 0.01),
          res("R6", "47k", "RC47K", None),
          res("TP1", "pad", "", None, in_bom=False))
    return d


def test_bom_grouping_prices_and_dnp(tmp_path):
    d = _bom_design()
    groups = outputs.bom_groups(d)
    by_refs = {" ".join(g["refs"]): g for g in groups}
    assert set(by_refs) == {"R1 R2 R10", "R3", "R4", "R5", "R6"}
    g = by_refs["R1 R2 R10"]
    assert (g["qty"], g["unit_price"], g["extended_price"], g["dnp"]) == (3, 0.01, 0.03, False)
    assert by_refs["R4"]["dnp"] and by_refs["R4"]["extended_price"] == 0.0
    assert by_refs["R6"]["extended_price"] is None             # no price known
    assert [g["item"] for g in groups] == [1, 2, 3, 4, 5]
    assert groups[-1]["refs"] == ["R4"]                         # DNP lines last
    totals = outputs.bom_totals(groups)
    assert totals == {"lines": 5, "parts_fitted": 6, "parts_dnp": 1,
                      "cost_per_board": 0.06, "unpriced_refs": ["R6"]}
    path = str(tmp_path / "bom.csv")
    outputs.write_bom(d, path)
    rows = list(csv.DictReader(open(path)))
    assert list(rows[0].keys()) == list(outputs.BOM_COLUMNS)
    first = rows[0]
    assert (first["Qty"], first["References"], first["Value"], first["MPN"],
            first["Manufacturer"], first["Distributor"], first["Distributor PN"],
            first["Unit Price"], first["Extended Price"], first["DNP"]) == (
        "3", "R1 R2 R10", "10k", "RC10K", "Yageo", "Digi-Key", "RC10K-ND", "0.0100",
        "0.0300", "")
    dnp = [r for r in rows if r["DNP"]]
    assert len(dnp) == 1 and dnp[0]["References"] == "R4" and dnp[0]["Extended Price"] == "0.0000"
    assert [r for r in rows if r["References"] == "R6"][0]["Extended Price"] == ""
    assert "TP1" not in open(path).read()


def test_check_positions_names_every_disagreement():
    d = _bom_design()
    assert outputs.placed_refs(d) == ["R10", "R2", "R1", "R3", "R5", "R6"]

    def rows():
        return [{"Ref": p.ref, "Val": p.value, "Package": "R", "PosX": p.x, "PosY": p.y,
                 "Rot": p.rotation, "Side": p.side, "MPN": p.mpn}
                for p in d.parts if p.in_bom and not p.dnp]
    assert outputs.check_positions(d, rows()) == []
    r = rows()
    r[0]["PosX"] += 0.01
    assert "R10 at" in outputs.check_positions(d, r)[0]
    r = rows()
    r[1]["Rot"] = 90.0
    assert "R2 rotation" in outputs.check_positions(d, r)[0]
    r = rows()
    r[1]["Rot"] = 360.0                                         # same angle
    assert outputs.check_positions(d, r) == []
    r = rows()
    r[2]["Side"] = "bottom"
    assert "R1 on the bottom side" in outputs.check_positions(d, r)[0]
    assert "R3 is missing" in " ".join(outputs.check_positions(d, [x for x in rows()
                                                                   if x["Ref"] != "R3"]))
    extra = rows() + [{"Ref": "R4", "Val": "", "Package": "", "PosX": 0, "PosY": 4,
                       "Rot": 0, "Side": "top", "MPN": ""}]
    assert "R4 is in the position file" in " ".join(outputs.check_positions(d, extra))
    assert "duplicate" in " ".join(outputs.check_positions(d, rows() + rows()[:1]))


def test_netlist_data_matches_connectivity(mini):
    data = outputs.netlist_data(mini)
    assert set(data["nets"]) == set(mini.nets)
    for name, pads in mini.connectivity().items():
        assert set(data["nets"][name]["pads"]) == pads
    assert data["counts"]["parts"] == len(mini.parts)
    u1 = data["parts"]["U1"]
    pin = next(iter(u1["pins"].values()))
    assert set(pin) == {"pads", "type", "net"}
    assert set(data["netclasses"]) == set(mini.netclasses)
    json.dumps(data)                                            # serialisable


def test_mechanical_data(mini):
    data = outputs.mechanical_data(mini)
    b = data["board"]
    assert b["thickness"] == 0.8
    # the 3 x 2 mm notch at the bottom removes the lowest point of the circle
    assert b["bounds"][0] == pytest.approx(-15.0) and b["bounds"][2] == pytest.approx(15.0)
    assert b["bounds"][3] == pytest.approx(15.0) and -15.0 < b["bounds"][1] < -14.8
    assert len(b["edge_contours"]) == 3                         # boundary, cut-out, slot
    assert {"type": "circle", "center": [8.0, 0.0], "radius": 3.0} in b["edge_contours"][1]
    assert sorted((h["x"], h["y"], h["diameter"]) for h in b["npth_holes"]) == [
        (-11.5, 5.0, 1.2), (11.0, 7.5, 1.2)]
    assert len(b["outline_polygon_holes"]) == 2
    comps = {c["ref"]: c for c in data["components"]}
    assert set(comps) == {p.ref for p in mini.parts}
    for part in mini.parts:
        c = comps[part.ref]
        assert (c["x"], c["y"], c["side"]) == (part.x, part.y, part.side)
        assert c["rot"] == pytest.approx(part.rotation % 360.0)
        body = c["body"]
        assert body["length"] > 0 and body["width"] > 0 and len(body["corners"]) == 4
        if part.side == BOTTOM:
            assert c["z_max"] == 0.0 and c["z_min"] == pytest.approx(-(body["height"] or 0))
        else:
            assert c["z_min"] == 0.8 and c["z_max"] == pytest.approx(0.8 + (body["height"] or 0))
    u1 = comps["U1"]
    assert (u1["body"]["length"], u1["body"]["width"], u1["body"]["height"]) == (7.0, 9.0, 1.8)
    assert data["max_height"]["top"] == max(c["body"]["height"] or 0
                                            for c in data["components"] if c["side"] == "top")
    assert any(k["no_tracks"] for k in data["keepouts"])
    json.dumps(data)


def test_mechanical_data_rotated_body_and_height_limits():
    from gleda.model import RoundedPolygon
    d = Design("rot", Outline(Circle(0, 0, 10)))
    d.add(Part("R1", "1k", R0402, pins=two_pin(), mpn="x", x=2.0, y=3.0, rotation=90.0,
               height_mm=0.4))
    d.add_height_limit(RoundedPolygon.rect(0, 5, 4, 2), 0.95, side="top", exempt=("U2",),
                       name="hood")
    data = outputs.mechanical_data(d)
    c = data["components"][0]
    xs = [p[0] for p in c["body"]["corners"]]
    ys = [p[1] for p in c["body"]["corners"]]
    # the body's long side (length, along the footprint x axis) now runs along y
    assert max(ys) - min(ys) == pytest.approx(c["body"]["length"], abs=1e-3)
    assert max(xs) - min(xs) == pytest.approx(c["body"]["width"], abs=1e-3)
    assert c["body"]["length"] > c["body"]["width"] and c["rot"] == 90.0
    hl = data["height_limits"][0]
    assert (hl["name"], hl["side"], hl["max_height"], hl["exempt"]) == ("hood", "top", 0.95,
                                                                        ["U2"])
    assert data["board"]["edge_contours"] == [[{"type": "circle", "center": [0.0, 0.0],
                                                "radius": 10.0}]]
    assert data["board"]["bounds"] == [-10.0, -10.0, 10.0, 10.0]


# --------------------------------------------------------------------------
# the whole package on a real board (mini design + one via)
# --------------------------------------------------------------------------

VIA = Via("GND", -10.0, -6.0, 0.5, 0.25)


@pytest.fixture(scope="module")
def mini_out(tmp_path_factory):
    """Mini board with one via, unrouted (so not DRC clean), all outputs."""
    from mini_design import mini_design
    design = mini_design()
    out = str(tmp_path_factory.mktemp("mini_out"))
    files = board.build_board(design, out)
    board.apply_routing(files.pcb, [], [VIA])
    result = drc.run_drc(files.pcb)
    with pytest.raises(outputs.OutputError) as err:
        outputs.generate_outputs(design, files.pcb, out, drc_result=result, vias=[VIA])
    assert "not clean" in str(err.value) and not os.path.exists(os.path.join(out, "fab"))
    produced = outputs.generate_outputs(design, files.pcb, out, drc_result=result, vias=[VIA],
                                        require_clean=False, dpi=300)
    return design, files, out, produced


def test_unclean_board_is_marked_everywhere(mini_out):
    design, files, out, produced = mini_out
    assert produced.drc_clean is False and produced.ok is False
    assert "NOT CLEAN" in produced.drc_line and "unconnected" in produced.drc_line
    readme = open(os.path.join(out, "fab", "README.txt")).read()
    assert "NOT CLEAN - DO NOT FABRICATE" in readme.split("\n\n")[1]
    assert json.load(open(os.path.join(out, "outputs.json")))["ok"] is False
    # the data itself agrees with the model: only the DRC status is bad
    assert produced.problems == []


def test_fab_package_contents(mini_out):
    design, files, out, produced = mini_out
    fab = os.path.join(out, "fab")
    names = sorted(os.listdir(fab))
    want = sorted(
        ["mini-%s.gbr" % stem for stem in (
            "F_Cu", "In1_Cu", "In2_Cu", "B_Cu", "F_Mask", "B_Mask", "F_Paste", "B_Paste",
            "F_Silkscreen", "B_Silkscreen", "Edge_Cuts")]
        + ["mini-job.gbrjob", "mini-PTH.drl", "mini-NPTH.drl", "mini-PTH-drl_map.gbr",
           "mini-NPTH-drl_map.gbr", "README.txt"])
    assert names == want
    for name in names:
        text = open(os.path.join(fab, name), errors="replace").read()
        assert "CreationDate" not in text
        assert not any(" date " in line for line in text.split("\n")[:12]), name
    assert produced.drill_tables == {"mini-PTH.drl": [(0.25, 1)], "mini-NPTH.drl": [(1.2, 2)]}
    pth = outputs.read_excellon(os.path.join(fab, "mini-PTH.drl"))
    assert pth.plated is True and pth.hits == [(0.25, -10.0, -6.0)]
    edge = outputs.read_gerber(os.path.join(fab, "mini-Edge_Cuts.gbr"))
    assert edge.bounds == pytest.approx(outputs.edge_bounds(design), abs=0.002)
    assert outputs.read_gerber(os.path.join(fab, "mini-F_Cu.gbr")).file_function == \
        "Copper,L1,Top"
    assert outputs.read_gerber(os.path.join(fab, "mini-In2_Cu.gbr")).file_function == \
        "Copper,L3,Inr"
    assert outputs.read_gerber(os.path.join(fab, "mini-B_Cu.gbr")).file_function == \
        "Copper,L4,Bot"
    readme = open(os.path.join(fab, "README.txt")).read()
    for needle in ("Copper layers:       4", "Finished thickness:  0.80 mm", "STACK-UP",
                   "Minimum track width:        0.127 mm (5.0 mil)",
                   "Minimum copper clearance:   0.127 mm", "0.500 / 0.250 mm",
                   "Copper to board edge:       0.300 mm", "mini-NPTH.drl: 2 hole(s)",
                   "Routed non-plated slot on Edge.Cuts: 0.800 x 2.800 mm",
                   "Routed cut-out on Edge.Cuts: Circle, 6.000 x 6.000 mm",
                   "origin: the centre of the board", "mini-In1_Cu.gbr", "GND plane",
                   "tented (covered by solder mask) on both sides"):
        assert needle in readme, needle
    for name in names:
        assert name in readme


def test_fab_readme_states_fine_minimums():
    """A board with a fine net class: the README gives the board-level
    minimums 0.09 / 0.09 and names the class."""
    from dshape_design import dshape_design
    design = dshape_design()
    text = outputs.fab_readme(design, {}, [("x.gbr", "copper")], "KiCad DRC 0 error(s)", True)
    assert "Minimum track width:        0.090 mm (3.5 mil)" in text
    assert "Minimum copper clearance:   0.090 mm (3.5 mil)" in text
    assert "Rule set:                   US_4L_FINE" in text
    # nothing is claimed about WHERE the fine geometry is unless it was measured
    assert "Fine" in text and "was not measured" in text
    assert "only where a fine-pitch package needs them" not in text
    assert "DO NOT FABRICATE" not in text
    assert "DO NOT FABRICATE" in outputs.fab_readme(design, {}, [("x.gbr", "c")], "bad", False)
    design.via_tenting = "bottom"
    design.via_protection = "plugged from the bottom side (IPC-4761 type III-a)"
    design.fab_notes = ["The bottom side is a wetted surface."]
    text = outputs.fab_readme(design, {}, [("x", "c")], "", True)
    assert "tented on the BOTTOM side" in text
    assert "Via protection:      plugged from the bottom side (IPC-4761 type III-a)" in text
    assert "FAB NOTES" in text and "- The bottom side is a wetted surface." in text
    # the mask web between an open via and a pad of its net is a stated rule
    assert "Via to pad, top:     design rule 0.200 mm" in text and "solder-mask web" in text
    assert "Via to pad, bottom:  design rule 0.100 mm" in text and "vias tented" in text


def _fine_design(areas=True):
    d = Design("finefab", Outline(RoundedPolygon.rect(0.0, 0.0, 30.0, 16.0)), layers=4,
               rules=US_4L_FINE)
    d.add_netclass("Fine", track_width=0.09, clearance=0.09)
    fp = F.bga("FabBGA9", 3, 3, pitch=0.5, pad_d=0.23, pad_clearance=0.09, height=1.0)
    balls = ["%s%d" % (r, c) for r in "ABC" for c in (1, 2, 3)]
    d.add(Part("U1", "bga", fp, pins={b: (b, "bidir") for b in balls}, x=-8.0, y=0.0,
               in_bom=False, height_mm=1.0))
    d.add(Part("T1", "TP", F.test_pad(0.6), pins={"1": "1"}, x=10.0, y=0.0, in_bom=False,
               height_mm=0.0))
    d.net("SIG", "U1.B3", "T1.1", netclass="Fine")
    d.no_connect(*["U1.%s" % b for b in balls if b != "B3"])
    if areas:
        d.add_fine_area("U1", margin=3.0)
    return d


def test_copper_report_measures_where_the_fine_tracks_are():
    """The review finding: the README said the fine classes "are used only
    where a fine-pitch package needs them" while a third of all track was
    0.09 mm wide and ran across the whole board.  Now it is measured."""
    confined = [Track("SIG", "F.Cu", -7.5, 0.0, -4.5, 0.0, 0.09),      # ends inside the area
                Track("SIG", "F.Cu", -4.5, 0.0, 10.0, 0.0, 0.15)]
    # one fine piece that starts inside the area and leaves it, one outside
    everywhere = [Track("SIG", "F.Cu", -7.5, 0.0, -4.5, 0.0, 0.09),
                  Track("SIG", "F.Cu", -4.5, 0.0, 3.0, 0.0, 0.09),
                  Track("SIG", "B.Cu", 3.0, 0.0, 10.0, 0.0, 0.09)]
    d = _fine_design()
    assert geometry.fine_area_polygon(d.fine_areas[0]).bounds == pytest.approx(
        (-11.615, -3.615, -4.385, 3.615))
    rep = outputs.copper_report(d, confined, [])
    assert rep["confined"] is True and rep["offender_count"] == 0
    assert rep["length_by_width"] == {"0.090": {"F.Cu": 3.0, "total": 3.0},
                                      "0.150": {"F.Cu": 14.5, "total": 14.5}}
    assert rep["narrow_length_mm"] == 3.0 and rep["narrow_outside_fine_areas_mm"] == 0.0
    assert rep["narrow_farthest"]["distance_mm"] == pytest.approx(2.885, abs=1e-3)
    assert rep["fine_pitch_arrays"] == ["U1"] and rep["narrow_nets"] == ["SIG"]
    text = outputs.fab_readme(d, {}, [("x", "c")], "", True, rep)
    assert "TRACKS AS ROUTED (measured" in text
    assert " 0.090 mm    3.0 mm" in text and " 0.150 mm   14.5 mm" in text
    assert "Net classes below the standard 0.150 / 0.127 mm: Fine." in text
    assert "Tracks narrower than 0.150 mm: 3.0 mm on 1 net(s)." in text
    assert "Every one of these tracks lies completely inside a fine area; the farthest " \
           "reaches 2.9 mm from the pad field of U1." in text
    assert "fine_U1 x -11.62..-4.38, y -3.62..3.62 - 52 mm2, 11 % of the board." in text
    assert outputs.check_fine_geometry(d, confined) == []
    # the same class laid across the whole board: said so, and a problem
    rep = outputs.copper_report(d, everywhere, [])
    assert rep["confined"] is False and rep["offender_count"] == 2
    assert rep["narrow_outside_fine_areas_mm"] == 14.5
    assert rep["narrow_farthest"] == {"net": "SIG", "layer": "B.Cu", "x": 10.0, "y": 0.0,
                                      "distance_mm": pytest.approx(17.385, abs=1e-3),
                                      "nearest_array": "U1"}
    text = outputs.fab_readme(d, {}, [("x", "c")], "", True, rep)
    assert "*** 14.5 mm of them (2 track piece(s)) lie OUTSIDE the fine areas" in text
    assert "Every one of these tracks" not in text
    problems = outputs.check_fine_geometry(d, everywhere)
    assert len(problems) == 2 and "is not completely inside a fine area (0.150 mm needed " \
        "there)" in problems[0]
    # a design that declares no fine area: no reassurance, the real reach is printed
    d2 = _fine_design(areas=False)
    rep = outputs.copper_report(d2, everywhere, [])
    assert rep["confined"] is False and rep["fine_areas"] == []
    assert rep["offender_count"] == 0 and rep["narrow_outside_fine_areas_mm"] is None
    assert rep["narrow_length_mm"] == 17.5
    text = outputs.fab_readme(d2, {}, [("x", "c")], "", True, rep)
    assert "The design declares no fine areas: these tracks may run anywhere along their " \
           "nets; the farthest is SIG on B.Cu at (10.00, 0.00), 17.4 mm from the nearest " \
           "fine-pitch array (U1)." in text
    assert "Quote the whole board at the board-level minimums." in text
    assert outputs.check_fine_geometry(d2, everywhere) == []       # nothing was promised


def test_copper_report_states_the_smallest_via_to_pad_web():
    d = Design("web", Outline(RoundedPolygon.rect(0.0, 0.0, 10.0, 8.0)), layers=4)
    d.add(Part("C1", "100n", C0402, pins=two_pin(), mpn="x", x=0.0, y=0.0, height_mm=0.5))
    d.add(Part("C2", "100n", C0402, pins=two_pin(), mpn="x", x=0.0, y=2.0, side=BOTTOM,
               height_mm=0.5))
    d.net("GND", "C1.2", "C2.2")
    d.net("V", "C1.1", "C2.1")
    pad = [p for p in geometry.placed_pads(d) if p.key == "C1.2"][0]
    right = pad.polygon.bounds[2]
    vias = [Via("GND", right + 0.25 + 0.21, 0.0, 0.5, 0.25)]
    rep = outputs.copper_report(d, [], vias)
    assert rep["min_via_to_own_pad_gap"]["top"] == pytest.approx(0.21, abs=1e-3)
    d.via_tenting = "bottom"
    text = outputs.fab_readme(d, {}, [("x", "c")], "", True, rep)
    assert "Via to pad, top:     design rule 0.200 mm" in text
    assert "smallest on this board 0.210 mm" in text


def test_zip_and_manifest_are_complete_and_deterministic(mini_out, tmp_path):
    design, files, out, produced = mini_out
    with zipfile.ZipFile(produced.fab_zip) as zf:
        assert sorted(zf.namelist()) == sorted(os.listdir(os.path.join(out, "fab")))
        assert {i.date_time for i in zf.infolist()} == {outputs.ZIP_TIME}
        assert zf.read("README.txt") == open(os.path.join(out, "fab", "README.txt"), "rb").read()
    again = outputs.write_zip(os.path.join(out, "fab"), str(tmp_path / "again.zip"))
    assert open(again, "rb").read() == open(produced.fab_zip, "rb").read()
    manifest = json.load(open(os.path.join(out, "outputs.json")))["files"]
    paths = [f["path"] for f in manifest]
    for needed in ("fab/README.txt", "assembly/mini-pos.csv", "assembly/mini-bom.csv",
                   "mini-netlist.json", "mini-mechanical.json", "mini-fab.zip",
                   "mini-board.step",
                   "renders/mini-top.png", "renders/mini-top.svg", "renders/mini-bottom.png",
                   "renders/mini-bottom.svg", "renders/mini-In1_Cu.png",
                   "renders/mini-In2_Cu.svg"):
        assert needed in paths, needed
    for f in manifest:
        data = open(os.path.join(out, f["path"]), "rb").read()
        assert len(data) == f["bytes"] > 0 and hashlib.sha256(data).hexdigest() == f["sha256"]


def test_bare_board_step(mini_out):
    from mini_design import mini_design
    design, files, out, produced = mini_out
    path = os.path.join(out, "mini-board.step")
    text = open(path).read()
    assert text.startswith("ISO-10303-21;")
    assert "FILE_NAME('mini-board.step','%s'" % outputs.STEP_FIXED_DATE in text
    x0, y0, z0, x1, y1, z1 = outputs.step_extents(path)
    assert (x0, x1, y1) == pytest.approx((-15.0, 15.0, 15.0), abs=0.02)
    assert -15.0 < y0 < -14.8                    # the notch took the lowest point
    assert z1 == pytest.approx(0.8)              # top surface = board thickness
    assert outputs.check_step(design, path) == []
    other = mini_design()
    other.outline.shape = Circle(0.0, 0.0, 16.0)
    assert any("STEP xmax" in p for p in outputs.check_step(other, path))
    thick = mini_design()
    thick.board_thickness = 1.6
    assert any("STEP top surface" in p for p in outputs.check_step(thick, path))
    bad = os.path.join(out, "empty.step")
    with open(bad, "w") as fh:
        fh.write("ISO-10303-21;\n")
    assert outputs.check_step(design, bad) == ["empty.step: no geometry"]
    os.remove(bad)


def test_position_file_agrees_with_model_and_kicad(mini_out):
    design, files, out, produced = mini_out
    rows = list(csv.DictReader(open(os.path.join(out, "assembly", "mini-pos.csv"))))
    assert list(rows[0].keys()) == list(outputs.POS_COLUMNS)
    assert produced.position_rows == len(rows) == len(outputs.placed_refs(design))
    parts = design.parts_by_ref
    assert {r["Ref"] for r in rows} == set(outputs.placed_refs(design))
    sides = set()
    for r in rows:
        p = parts[r["Ref"]]
        assert (float(r["PosX"]), float(r["PosY"])) == pytest.approx((p.x, p.y), abs=1e-4)
        assert (float(r["Rot"]) - p.rotation) % 360.0 == pytest.approx(0.0, abs=1e-3)
        assert r["Side"] == p.side and r["MPN"] == p.mpn
        sides.add(r["Side"])
    assert sides == {"top", "bottom"}                           # both sides are covered
    # parts that are not on the BOM (test pads, battery tabs) are not placed
    assert not {p.ref for p in design.parts if not p.in_bom} & {r["Ref"] for r in rows}


def test_verify_outputs_catches_differences(mini_out):
    """The same files against a deliberately different model."""
    from mini_design import mini_design
    design, files, out, produced = mini_out
    fab = os.path.join(out, "fab")
    assert outputs.verify_outputs(design, fab, [VIA]) == []

    def verify(mutate=None, vias=(VIA,)):
        other = mini_design()
        if mutate:
            mutate(other)
        return " | ".join(outputs.verify_outputs(other, fab, list(vias)))

    # a part somewhere else: its pads are not flashed where the model says
    top = [p for p in design.parts if p.side == "top" and p.ref.startswith("R")][0]
    text = verify(lambda d: d.part(top.ref).place(top.x + 0.5, top.y, top.rotation))
    assert "F.Cu: pad %s." % top.ref in text
    bottom = [p for p in design.parts if p.side == BOTTOM][0]
    text = verify(lambda d: d.part(bottom.ref).place(bottom.x, bottom.y + 0.4, bottom.rotation))
    assert "B.Cu: pad %s." % bottom.ref in text
    # a bottom part turned by 90 degrees
    text = verify(lambda d: d.part(bottom.ref).place(bottom.x, bottom.y,
                                                     bottom.rotation + 90.0))
    assert "B.Cu: pad %s." % bottom.ref in text
    # drills
    assert "unexpected 0.250 mm hole at (-10.000, -6.000)" in verify(vias=())
    text = verify(vias=(Via("GND", -10.0, -6.1, 0.5, 0.25),))
    assert "no 0.250 mm hole at (-10.000, -6.100)" in text and "unexpected" in text
    assert "no 0.300 mm hole" in verify(vias=(Via("GND", -10.0, -6.0, 0.6, 0.3),))
    text = verify(lambda d: d.outline.add_hole(0.0, 10.0, 1.0))
    assert "mini-NPTH.drl: no 1.000 mm hole at (0.000, 10.000)" in text
    # outline: a different radius, a moved cut-out, a missing slot
    text = verify(lambda d: setattr(d.outline, "shape", Circle(0.0, 0.0, 15.2)))
    assert "Edge.Cuts xmin" in text and "Edge.Cuts ymax" in text

    def move_cutout(d):
        d.outline.cutouts[0] = Circle(8.0, 1.0, 3.0)
    assert "circle r 3.000 at (8.000, 1.000)" in verify(move_cutout)

    def move_slot(d):
        d.outline.cutouts[2] = type(d.outline.cutouts[2])(-6.0, -10.0, -4.0, -10.0, 0.8)
    assert "is not in the Gerber" in verify(move_slot)
    # a mirrored board (y flipped) would not pass either
    assert verify(lambda d: [p.place(p.x, -p.y, p.rotation) for p in d.parts]) != ""
    # missing files
    os.rename(os.path.join(fab, "mini-B_Cu.gbr"), os.path.join(fab, "hidden"))
    try:
        assert "missing Gerber for B.Cu" in verify()
    finally:
        os.rename(os.path.join(fab, "hidden"), os.path.join(fab, "mini-B_Cu.gbr"))
    assert outputs.verify_outputs(design, fab, [VIA]) == []


def test_drilled_slots_must_be_the_slots_of_the_design(mini_out, tmp_path):
    import shutil
    design, files, out, produced = mini_out
    fab = str(tmp_path / "fab")
    shutil.copytree(os.path.join(out, "fab"), fab)
    path = os.path.join(fab, "mini-NPTH.drl")
    original = open(path).read()
    assert "X-11.5Y5.0\n" in original
    # the round hole at (-11.5, 5) drilled as a 1 mm long slot: not what the design has
    with open(path, "w") as fh:
        fh.write(original.replace("X-11.5Y5.0\n", "X-12.0Y5.0G85X-11.0Y5.0\n"))
    assert outputs.read_excellon(path).slots == [(1.2, -12.0, 5.0, -11.0, 5.0)]
    text = " | ".join(outputs.verify_outputs(design, fab, [VIA]))
    assert "the drilled slot at (-11.500, 5.000) (1.200 mm tool, 2.200 mm long) is not the " \
           "hole the design has there" in text
    assert "no 1.200 mm hole at (-11.500, 5.000)" in text
    # a slot where the design has no hole, and the real hole now missing
    with open(path, "w") as fh:
        fh.write(original.replace("X-11.5Y5.0\n", "X0.0Y0.0G85X1.0Y0.0\n"))
    text = " | ".join(outputs.verify_outputs(design, fab, [VIA]))
    assert "drilled slot at (0.500, 0.000) where the design has no hole" in text
    assert "no 1.200 mm hole at (-11.500, 5.000)" in text
    # plating attribute swapped
    with open(path, "w") as fh:
        fh.write(original.replace("TF.FileFunction,NonPlated", "TF.FileFunction,Plated"))
    assert "wrong plating attribute" in " | ".join(outputs.verify_outputs(design, fab, [VIA]))


def test_renders_show_plus_y_up_and_mirror_the_bottom(mini_out, tmp_path):
    """Pixel-level orientation proof on Edge.Cuts: the mini board has a round
    cut-out at x = +8 (right, seen from the top) and a notch at y = -15."""
    import matplotlib.image as mpimg
    design, files, out, produced = mini_out
    bounds = outputs.edge_bounds(design)
    DARK = 0.93                      # the edge is plotted in a light colour on white

    def dark_near(img, info, x, y, reach=3):
        px = info["origin_px"][0] + info["x_sign"] * x * info["px_per_mm"]
        py = info["origin_px"][1] - y * info["px_per_mm"]
        j0, i0 = int(round(px)), int(round(py))
        patch = img[max(0, i0 - reach):i0 + reach + 1, max(0, j0 - reach):j0 + reach + 1, :3]
        return patch.size > 0 and float(patch.min()) < DARK

    for mirror in (False, True):
        png = str(tmp_path / ("edge_%d.png" % mirror))
        info = outputs.render_view(files.pcb, png, ["Edge.Cuts"], bounds, mirror=mirror,
                                   dpi=300)
        img = mpimg.imread(png)
        assert img.shape[1] == info["size_px"][0] and img.shape[0] == info["size_px"][1]
        assert info["x_sign"] == (-1 if mirror else 1) and info["mirrored"] is mirror
        # the outline circle: right-most, left-most and top-most points
        assert dark_near(img, info, 15.0, 0.0) and dark_near(img, info, -15.0, 0.0)
        assert dark_near(img, info, 0.0, 15.0)
        # the cut-out is at design x = +8: its edge is at x = 11 and x = 5 ...
        assert dark_near(img, info, 11.0, 0.0) and dark_near(img, info, 5.0, 0.0)
        # ... and there is nothing at the mirror-image place
        assert not dark_near(img, info, -11.0, 0.0) and not dark_near(img, info, -5.0, 0.0)
        # the notch is at the bottom (y = -15): its inner edge runs along y = -14
        assert dark_near(img, info, 0.0, -14.0) and not dark_near(img, info, 0.0, 14.0)
        # in the picture itself: mirrored means the cut-out is in the left half
        cols = (img[:, :, :3].min(axis=2) < DARK)
        mid_row = cols[int(round(info["origin_px"][1])), :]
        inner = [j for j in range(len(mid_row)) if mid_row[j]]
        inside = [j for j in inner if 4 * info["px_per_mm"] < abs(j - info["origin_px"][0])
                  < 12 * info["px_per_mm"]]
        assert inside and all((j < info["origin_px"][0]) == mirror for j in inside)
    renders = json.load(open(os.path.join(out, "renders", "renders.json")))
    assert renders["top"]["mirrored"] is False and renders["bottom"]["mirrored"] is True
    assert renders["bottom"]["x_sign"] == -1 and "below" in renders["bottom"]["view"]
    for view in ("top", "bottom", "In1_Cu", "In2_Cu"):
        for ext in ("png", "svg"):
            path = os.path.join(out, "renders", "mini-%s.%s" % (view, ext))
            assert os.path.getsize(path) > 2000, path


def test_render_puts_parts_where_the_design_says(tmp_path):
    """A part placed at +y is drawn toward the top of the top view; a bottom
    part appears mirrored (left <-> right) in the view from below and
    un-mirrored when the bottom copper is looked at from above."""
    import matplotlib.image as mpimg
    d = Design("where", Outline(Circle(0, 0, 8)))
    d.add(Part("R1", "1k", R0402, pins=two_pin(), mpn="x", x=3.0, y=4.0))
    d.add(Part("R2", "1k", R0402, pins=two_pin(), mpn="x", x=-2.0, y=3.0, side=BOTTOM))
    d.net("A", "R1.1", "R2.1")
    d.net("B", "R1.2", "R2.2")
    files = board.build_board(d, str(tmp_path))
    bounds = outputs.edge_bounds(d)

    def copper(layer, mirror, x, y):
        png = str(tmp_path / ("%s_%d.png" % (layer.replace(".", "_"), mirror)))
        info = outputs.render_view(files.pcb, png, [layer], bounds, mirror=mirror, dpi=300)
        img = mpimg.imread(png)
        px = int(round(info["origin_px"][0] + info["x_sign"] * x * info["px_per_mm"]))
        py = int(round(info["origin_px"][1] - y * info["px_per_mm"]))
        r = int(0.8 * info["px_per_mm"])
        patch = img[max(0, py - r):py + r + 1, max(0, px - r):px + r + 1, :3]
        dark = (patch.min(axis=2) < 0.7).mean()
        # also where the copper is in the raw picture, relative to its centre
        ys, xs = (img[:, :, :3].min(axis=2) < 0.7).nonzero()
        return dark, (xs.mean() - img.shape[1] / 2.0, ys.mean() - img.shape[0] / 2.0)

    # top copper, seen from above: R1 at (+3, +4) = right of and above the centre
    here, (dx, dy) = copper("F.Cu", False, 3.0, 4.0)
    assert here > 0.1 and dx > 0 and dy < 0
    assert copper("F.Cu", False, -3.0, 4.0)[0] == 0 and copper("F.Cu", False, 3.0, -4.0)[0] == 0
    # bottom copper, seen from below: R2 at design (-2, +3) is drawn RIGHT of the centre
    here, (dx, dy) = copper("B.Cu", True, -2.0, 3.0)
    assert here > 0.1 and dx > 0 and dy < 0
    assert copper("B.Cu", True, 2.0, 3.0)[0] == 0
    # bottom copper, seen from above (X-ray view): left of the centre
    here, (dx, dy) = copper("B.Cu", False, -2.0, 3.0)
    assert here > 0.1 and dx < 0 and dy < 0


def test_export_needs_explicit_layers(mini_out, tmp_path):
    design, files, out, produced = mini_out
    with pytest.raises(outputs.OutputError):
        outputs.export_gerbers(files.pcb, str(tmp_path), [])
    with pytest.raises(outputs.OutputError):
        outputs.render_view(files.pcb, str(tmp_path / "x.png"), [], (0, 0, 1, 1))
    assert outputs.fab_layers(design) == ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu", "F.Mask",
                                          "B.Mask", "F.Paste", "B.Paste", "F.SilkS",
                                          "B.SilkS", "Edge.Cuts"]
    with pytest.raises(outputs.OutputError):
        outputs.generate_outputs(design, str(tmp_path / "nope.kicad_pcb"), str(tmp_path))


def test_unfilled_zones_are_refused(tmp_path):
    """A DRC result that claims a pass does not help a board whose planes
    were never filled: the Gerbers would have empty plane layers."""
    from mini_design import mini_design
    design = mini_design()
    files = board.build_board(design, str(tmp_path))
    claimed = drc.DrcResult(board=files.pcb)
    assert claimed.is_clean()
    with pytest.raises(outputs.OutputError) as err:
        outputs.generate_outputs(design, files.pcb, str(tmp_path), drc_result=claimed)
    assert "zones not filled" in str(err.value)
    assert not os.path.exists(os.path.join(str(tmp_path), "fab"))


def test_outputs_run_drc_themselves_on_a_clean_board(tmp_path):
    """Without a DRC result the board file is checked here; a clean board
    passes, and its outputs verify."""
    d = Design("tiny", Outline(Circle(0, 0, 6)))
    d.add(Part("R1", "1k", R0402, pins=two_pin(), mpn="RC1K", manufacturer="Yageo",
               x=-1.5, y=0.0, height_mm=0.4))
    d.add(Part("R2", "1k", R0402, pins=two_pin(), mpn="RC1K", manufacturer="Yageo",
               x=1.5, y=0.0, side=BOTTOM, rotation=90.0, height_mm=0.4))
    d.net("A", "R1.1", "R1.2")
    d.net("B", "R2.1", "R2.2")
    files = board.build_board(d, str(tmp_path))
    from gleda import geometry
    pads = {p.key: p for p in geometry.placed_pads(d)}
    from gleda.model import Track
    tracks = [Track("A", "F.Cu", pads["R1.1"].x, pads["R1.1"].y, pads["R1.2"].x,
                    pads["R1.2"].y, 0.15),
              Track("B", "B.Cu", pads["R2.1"].x, pads["R2.1"].y, pads["R2.2"].x,
                    pads["R2.2"].y, 0.15)]
    board.apply_routing(files.pcb, tracks, [])
    result = outputs.generate_outputs(d, files.pcb, str(tmp_path), renders=False, step=False)
    assert result.ok and result.drc_clean and result.problems == []
    assert not os.path.exists(os.path.join(str(tmp_path), "tiny-board.step"))
    assert "0 error(s), 0 unconnected" in result.drc_line
    assert "DO NOT FABRICATE" not in open(os.path.join(str(tmp_path), "fab",
                                                       "README.txt")).read()
    assert result.renders == {} and not os.path.exists(os.path.join(str(tmp_path), "renders"))
    assert result.drill_tables["tiny-PTH.drl"] == []


# --------------------------------------------------------------------------
# solder mask, paste and via tenting are part of the verification
# --------------------------------------------------------------------------

def _mask_design():
    d = Design("masks", Outline(RoundedPolygon.rect(0.0, 0.0, 16.0, 10.0)), layers=4)
    d.add(Part("C1", "100n", C0402, pins=two_pin(), mpn="x", x=-4.0, y=2.0, height_mm=0.5))
    d.add(Part("U1", "flash", "Package_SON:WSON-8-1EP_6x5mm_P1.27mm_EP3.4x4.3mm",
               pins={str(i): str(i) for i in range(1, 10)}, mpn="x", x=3.0, y=0.0,
               height_mm=0.8))
    d.add(Part("J2", "pads", F.pad_row("Row3", 3, 2.54, 1.8), pins={"1": "1", "2": "2", "3": "3"},
               x=-3.0, y=-2.5, side=BOTTOM, in_bom=False, height_mm=0.0))
    d.add_fiducial(-6.5, -3.5)
    d.net("A", "C1.1", "J2.1", "U1.1")
    d.net("B", "C1.2", "J2.2", "U1.9")
    d.no_connect("J2.3", *["U1.%d" % i for i in range(2, 9)])
    d.via_tenting = "bottom"
    return d


MASK_VIAS = [Via("A", -6.0, 3.5, 0.5, 0.25), Via("B", 6.5, -3.5, 0.5, 0.25)]


@pytest.fixture(scope="module")
def mask_out(tmp_path_factory):
    design = _mask_design()
    out = str(tmp_path_factory.mktemp("mask_out"))
    files = board.build_board(design, out)
    board.apply_routing(files.pcb, [], MASK_VIAS, via_tenting=design.via_tenting)
    produced = outputs.generate_outputs(design, files.pcb, out, vias=MASK_VIAS,
                                        require_clean=False, renders=False, step=False)
    return design, files, out, produced


def test_mask_paste_and_tenting_agree_with_the_model(mask_out):
    design, files, out, produced = mask_out
    assert produced.problems == []
    fab = os.path.join(out, "fab")
    top_mask = outputs.read_gerber(os.path.join(fab, "masks-F_Mask.gbr"))
    bot_mask = outputs.read_gerber(os.path.join(fab, "masks-B_Mask.gbr"))
    top_paste = outputs.read_gerber(os.path.join(fab, "masks-F_Paste.gbr"))
    bot_paste = outputs.read_gerber(os.path.join(fab, "masks-B_Paste.gbr"))
    # top: C1 (2) + U1 (9) + fiducial; paste: C1 (2) + U1 leads (8) + 4 split EP apertures
    assert len(top_mask.flashes) == 12 and len(top_paste.flashes) == 14
    assert len(bot_mask.flashes) == 3 and bot_paste.flashes == []     # bare pads: no paste
    assert len(top_mask.discs()) == 2 and bot_mask.discs() == {}      # vias open on top only
    assert set(top_mask.discs().values()) == {0.25}
    pads = {p.key: p for p in geometry.placed_pads(design)}
    assert pads["C1.1"].tech == ("F.Mask", "F.Paste") and pads["J2.1"].tech == ("B.Mask",)
    assert pads["U1.9"].tech == ("F.Mask",) and pads["FID1."].tech == ("F.Mask",)
    assert len(geometry.placed_apertures(design)) == 4


def test_a_different_model_is_caught_on_mask_paste_and_tenting(mask_out):
    design, files, out, produced = mask_out
    fab = os.path.join(out, "fab")

    def verify(mutate):
        other = _mask_design()
        mutate(other)
        return " | ".join(outputs.verify_outputs(other, fab, MASK_VIAS))

    # tenting: the files have openings on top, none on the bottom
    text = verify(lambda d: setattr(d, "via_tenting", "both"))
    assert "F.Mask: a round mask opening at (-6.000, 3.500) although vias are tented on the " \
           "top side (via_tenting = 'both')" in text
    text = verify(lambda d: setattr(d, "via_tenting", "none"))
    assert "B.Mask: the via at (-6.000, 3.500) has no mask opening although vias are not " \
           "tented on the bottom side" in text and "F.Mask" not in text
    text = verify(lambda d: setattr(d, "via_tenting", "top"))
    assert "B.Mask: the via at" in text and "F.Mask: a round mask opening" in text
    # a via the files do not have / one the model does not have
    other = _mask_design()
    text = " | ".join(outputs.verify_outputs(other, fab, MASK_VIAS[:1]))
    assert "F.Mask: a via mask opening at (6.500, -3.500) where the design has no via" in text
    # paste on the bare pad row, no paste on C1, no mask on the fiducial
    def paste_row(d):
        d.part("J2").footprint = F.pad_row("Row3", 3, 2.54, 1.8, paste=True)
    assert "B.Paste: pad J2.1 at (-5.540, -2.500) has no paste in the Gerber" in verify(paste_row)

    def bare_cap(d):
        d.part("C1").footprint = F.two_pad("C_bare", pad_w=0.56, pad_h=0.62, pitch=0.96,
                                           paste=False)
    text = verify(bare_cap)
    assert "F.Paste: unexpected paste at (-4.480, 2.000) - pad C1.1 must not have one" in text

    def moved_fiducial(d):
        d.part("FID1").place(-6.5, -3.0)
    text = verify(moved_fiducial)
    assert "F.Mask: pad FID1. at (-6.500, -3.000) has no mask opening" in text
    assert "F.Mask: unexpected mask opening at (-6.500, -3.500)" in text


def test_a_tampered_board_is_caught_on_mask_paste_and_tenting(mask_out, tmp_path):
    """The review's experiment: mask and paste removed from a part, paste
    added to bare contact pads, the via openings deleted.  KiCad's DRC has no
    objection to any of it - the output verification must."""
    import shutil
    import pcbnew
    design, files, out, produced = mask_out
    work = str(tmp_path / "tampered")
    shutil.copytree(out, work)
    pcb = os.path.join(work, "masks.kicad_pcb")
    brd = board.load_board(pcb)
    for fp in brd.GetFootprints():
        ref = str(fp.GetReference())
        for pad in fp.Pads():
            layers = pad.GetLayerSet()
            if ref == "C1":
                layers.RemoveLayer(pcbnew.F_Mask)
                layers.RemoveLayer(pcbnew.F_Paste)
            elif ref == "J2":
                layers.AddLayer(pcbnew.B_Paste)
            pad.SetLayerSet(layers)
    group = board._via_mask_group(brd)
    for member in list(group.GetItems()):
        brd.Remove(member)
    board.save_board(brd, pcb)
    result = drc.run_drc(pcb)
    assert result.error_count == 0                              # KiCad does not mind
    produced = outputs.generate_outputs(design, pcb, work, drc_result=result, vias=MASK_VIAS,
                                        require_clean=False, renders=False, step=False)
    text = " | ".join(produced.problems)
    assert not produced.ok
    assert "F.Mask: pad C1.1 at (-4.480, 2.000) has no mask opening in the Gerber" in text
    assert "F.Paste: pad C1.2 at (-3.520, 2.000) has no paste in the Gerber" in text
    assert "B.Paste: unexpected paste at (-5.540, -2.500) - pad J2.1 must not have one" in text
    assert "F.Mask: the via at (-6.000, 3.500) has no mask opening although vias are not " \
           "tented on the top side (via_tenting = 'bottom')" in text
    assert json.load(open(os.path.join(work, "outputs.json")))["ok"] is False


# --------------------------------------------------------------------------
# assembly package
# --------------------------------------------------------------------------

def test_assembly_readme_states_units_origin_and_conventions(mini_out):
    design, files, out, produced = mini_out
    text = open(os.path.join(out, "assembly", "README.txt")).read()
    for needle in ("Units:    millimetres, degrees.",
                   "Origin:   the centre of the board - the same origin as the Gerber and "
                   "drill files.",
                   "Axes:     X to the right, Y up, seen from the TOP side, for both sides.",
                   "Bottom:   X is NOT mirrored",
                   "Rot:      footprint rotation counter-clockwise seen from the TOP side, for "
                   "both sides",
                   "PosX/Y:   the footprint anchor", "BodyX/Y:  the centre of the component body",
                   "DNP (do not place):", "FIDUCIALS", "mini-pos.csv", "mini-bom.csv"):
        assert needle in text, needle
    rows = list(csv.DictReader(open(os.path.join(out, "assembly", "mini-pos.csv"))))
    by_side = {side: sum(1 for r in rows if r["Side"] == side) for side in ("top", "bottom")}
    assert "top:    %d placed part(s)" % by_side["top"] in text
    assert "bottom: %d placed part(s)" % by_side["bottom"] in text
    # the zip holds the same three files, with fixed time stamps
    with zipfile.ZipFile(os.path.join(out, "mini-assembly.zip")) as zf:
        assert sorted(zf.namelist()) == ["README.txt", "mini-bom.csv", "mini-pos.csv"]
        assert {i.date_time for i in zf.infolist()} == {(1980, 1, 1, 0, 0, 0)}
    assert "assembly/README.txt" in {f["path"] for f in produced.files}


def test_anchor_that_is_not_the_body_centre_is_pointed_out(mini_out):
    """The FPC connector's KiCad anchor sits on its pad row, 1.6 mm from the
    centre of its body: the position file gives both, the README names it."""
    design, files, out, produced = mini_out
    offs = outputs.anchor_offsets(design)
    assert [o["ref"] for o in offs] == ["J1"] and offs[0]["offset"] == pytest.approx(1.6)
    assert produced.anchor_offsets == offs
    assert json.load(open(os.path.join(out, "outputs.json")))["anchor_offsets"][0]["ref"] == "J1"
    rows = {r["Ref"]: r for r in csv.DictReader(open(os.path.join(out, "assembly",
                                                                    "mini-pos.csv")))}
    j1 = design.part("J1")
    body = geometry.part_body(j1)
    assert (float(rows["J1"]["PosX"]), float(rows["J1"]["PosY"])) == (j1.x, j1.y)
    assert (float(rows["J1"]["BodyX"]), float(rows["J1"]["BodyY"])) == \
        pytest.approx((body["cx"], body["cy"]), abs=1e-4)
    other = [r for r in rows.values() if r["Ref"] != "J1"]
    assert other and all(abs(float(r["BodyX"]) - float(r["PosX"])) < 0.05 and
                         abs(float(r["BodyY"]) - float(r["PosY"])) < 0.05 for r in other)
    text = open(os.path.join(out, "assembly", "README.txt")).read()
    assert "J1     anchor (%.3f, %.3f), body centre (%.3f, %.3f), 1.600 mm apart" % (
        j1.x, j1.y, body["cx"], body["cy"]) in text
    # a wrong body centre in the file is a problem
    bad = [dict(r, PosX=float(r["PosX"]), PosY=float(r["PosY"]), Rot=float(r["Rot"]),
                BodyX=float(r["BodyX"]) + (0.3 if r["Ref"] == "J1" else 0.0),
                BodyY=float(r["BodyY"])) for r in rows.values()]
    assert any("J1 body centre" in p for p in outputs.check_positions(design, bad))


# --------------------------------------------------------------------------
# oblong holes of footprints
# --------------------------------------------------------------------------

def test_oblong_footprint_holes_are_slots_in_the_drill_file(tmp_path):
    harwin = "Connector_Harwin:Harwin_Gecko-G125-MVX0605L1X_2x03_P1.25mm_Vertical"
    d = Design("slotdrill", Outline(RoundedPolygon.rect(0.0, 0.0, 16.0, 10.0)), layers=4)
    d.add(Part("J1", "hdr", harwin, pins={str(i): str(i) for i in range(1, 7)}, mpn="x",
               x=0.0, y=0.0, rotation=90.0, height_mm=4.0))
    for i in range(1, 7):
        d.no_connect("J1.%d" % i)
    plated, npth = outputs.expected_slots(d)
    assert plated == [] and len(npth) == 2
    # rotated by 90 degrees the slots lie along x: 1.0 mm tool, 0.9 mm travel
    assert sorted(npth)[0] == pytest.approx((1.0, -0.175, -1.25, -1.075, -1.25))
    files = board.build_board(d, str(tmp_path))
    fab = str(tmp_path / "fab")
    outputs.export_gerbers(files.pcb, fab, outputs.fab_layers(d))
    outputs.export_drill(files.pcb, fab)
    drill = outputs.read_excellon(os.path.join(fab, "slotdrill-NPTH.drl"))
    assert len(drill.slots) == 2 and drill.hits == []
    assert outputs.verify_outputs(d, fab, []) == []
    # the same files against a part turned back to 0 degrees: slots along y expected
    other = Design("slotdrill", Outline(RoundedPolygon.rect(0.0, 0.0, 16.0, 10.0)), layers=4)
    other.add(Part("J1", "hdr", harwin, pins={str(i): str(i) for i in range(1, 7)}, mpn="x",
                   x=0.0, y=0.0, rotation=0.0, height_mm=4.0))
    text = " | ".join(outputs.verify_outputs(other, fab, []))
    assert "slotdrill-NPTH.drl: no 1.000 mm slot from (3.750, 0.175) to (3.750, 1.075)" in text
    assert "where the design has no hole" in text
