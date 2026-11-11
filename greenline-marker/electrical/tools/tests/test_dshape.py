"""The GreenLine-shaped reference board: circle clipped by a chord, BGAs with a
shared bus, bottom-side LED ring and bare pad row, per-layer keep-outs under
sensor bodies, via tenting.  KiCad (pcbnew / DRC / kicad-cli) is the judge."""
import hashlib
import math
import os
import re

import pytest
from shapely.geometry import Point

from gleda import board, checks, drc, geometry, kicad_cli
from gleda import geometry as g
from gleda.model import (Design, Outline, Circle, PathShape, RoundedPolygon, Part, Track, Via,
                         BOTTOM, TOP, VIA_TENTING)
from dshape_design import (dshape_design, BOARD_RADIUS, FLAT_Y, LED_RING, PAD_ROW_Y, CAM_BUS)

R0402 = "Resistor_SMD:R_0402_1005Metric"
HALF_CHORD = math.sqrt(BOARD_RADIUS ** 2 - FLAT_Y ** 2)


def _md5(path):
    with open(path, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()


# -- general line + arc outlines ---------------------------------------------------

def test_d_shape_path_is_one_arc_and_one_chord():
    shape = PathShape.d_shape(BOARD_RADIUS, FLAT_Y)
    assert shape.closed and len(shape.segments) == 2
    path = g.shape_path(shape)
    arc, line = path
    assert isinstance(arc, g.Arc) and isinstance(line, g.Line)
    assert arc.center == (0.0, 0.0) and arc.radius == pytest.approx(BOARD_RADIUS)
    # the kept arc runs counter-clockwise from the right chord end, through the
    # bottom of the board, to the left chord end
    assert arc.start == pytest.approx((-HALF_CHORD, FLAT_Y)) or \
        arc.start == pytest.approx((HALF_CHORD, FLAT_Y))
    assert arc.mid == pytest.approx((0.0, -BOARD_RADIUS))
    assert {round(line.start[0], 6), round(line.end[0], 6)} == \
        {round(-HALF_CHORD, 6), round(HALF_CHORD, 6)}
    assert line.start[1] == pytest.approx(FLAT_Y) and line.end[1] == pytest.approx(FLAT_Y)
    half = math.acos(FLAT_Y / BOARD_RADIUS)
    assert abs(arc.angles[1]) == pytest.approx(2 * math.pi - 2 * half)


def test_d_shape_polygon_is_exact_and_conservative():
    shape = PathShape.d_shape(BOARD_RADIUS, FLAT_Y)
    half = math.acos(FLAT_Y / BOARD_RADIUS)
    segment = BOARD_RADIUS ** 2 * (half - math.sin(half) * math.cos(half))   # cut-off cap
    exact = math.pi * BOARD_RADIUS ** 2 - segment
    inner = g.shape_polygon(shape, 0.005, "inscribed")
    outer = g.shape_polygon(shape, 0.005, "circumscribed")
    assert inner.area < exact < outer.area
    assert exact - inner.area < 0.7 and outer.area - exact < 0.7
    assert inner.bounds == pytest.approx((-BOARD_RADIUS, -BOARD_RADIUS, BOARD_RADIUS, FLAT_Y),
                                         abs=0.006)
    assert inner.contains(Point(0, 17.29)) and not outer.contains(Point(0, 17.31))
    assert inner.contains(Point(12.0, 17.2)) and not outer.contains(Point(12.6, 17.2))
    assert Outline(shape).polygon().equals(inner)


def test_d_shape_flat_below_the_centre_and_offset_centre():
    low = PathShape.d_shape(10.0, -6.0, cx=2.0, cy=1.0)       # flat 7 mm below the centre
    poly = g.shape_polygon(low)
    assert poly.bounds == pytest.approx((-8.0, -6.0, 12.0, 11.0), abs=0.006)
    assert poly.contains(Point(2.0, 10.9)) and not poly.contains(Point(2.0, -6.1))


def test_clipped_circle_with_several_chords():
    shape = PathShape.clipped_circle(0, 0, 10, [(90, 8), (270, 8), (0, 9)])
    path = g.shape_path(shape)
    assert [type(e).__name__ for e in path] == ["Arc", "Line"] * 3
    poly = g.shape_polygon(shape)
    assert poly.bounds == pytest.approx((-10, -8, 9, 8), abs=0.006)
    for k, el in enumerate(path):
        prev = path[k - 1]
        assert math.hypot(prev.end[0] - el.start[0], prev.end[1] - el.start[1]) < 1e-9
    with pytest.raises(ValueError, match="overlap"):
        PathShape.clipped_circle(0, 0, 10, [(90, 2), (0, 2)])
    with pytest.raises(ValueError, match="inside the radius"):
        PathShape.clipped_circle(0, 0, 10, [(90, 10)])
    with pytest.raises(ValueError):
        PathShape.clipped_circle(0, 0, 10, [])


def test_path_shape_builder_and_validation():
    # a 6 x 4 rectangle whose right side is a semicircle bulging outward
    shape = PathShape.begin(0, 0).line_to(6, 0).arc_to(6, 4, 6, 2, ccw=True).line_to(0, 4).close()
    assert shape.closed and len(shape.segments) == 4
    poly = g.shape_polygon(shape)
    assert poly.area == pytest.approx(24 + math.pi * 2, abs=0.02)
    assert poly.bounds == pytest.approx((0, 0, 8, 4), abs=0.006)
    # the same path walked clockwise describes the same area
    cw = PathShape.begin(0, 0).line_to(0, 4).line_to(6, 4).arc_to(6, 0, 6, 2, ccw=False).close()
    assert g.shape_polygon(cw).area == pytest.approx(poly.area, abs=1e-6)
    with pytest.raises(ValueError, match="from the centre"):
        PathShape.begin(0, 0).arc_to(5, 5, 1, 0)
    with pytest.raises(ValueError, match="identical end points"):
        PathShape.begin(1, 0).arc_to(1, 0, 0, 0)
    with pytest.raises(ValueError, match="not closed"):
        g.shape_path(PathShape.begin(0, 0).line_to(1, 0).line_to(1, 1))
    with pytest.raises(ValueError):
        PathShape.begin(0, 0).line_to(1, 0).close()


def test_concave_arcs_are_polygonised_conservatively():
    """A rectangle with a semicircular bite: 'inscribed' must stay inside the
    true shape (outside the bite), 'circumscribed' must contain it."""
    bite = PathShape.begin(0, 0).line_to(10, 0).line_to(10, 6).line_to(7, 6) \
        .arc_to(3, 6, 5, 6, ccw=False).line_to(0, 6).close()
    exact = 60 - math.pi * 4 / 2
    inner = g.shape_polygon(bite, 0.01, "inscribed")
    outer = g.shape_polygon(bite, 0.01, "circumscribed")
    assert inner.area < exact < outer.area
    assert inner.difference(outer).area < 1e-12 and outer.difference(inner).area > 0.01
    # points on the true arc: never inside the inscribed polygon (beyond rounding),
    # always inside the circumscribed one
    shrunk, grown = inner.buffer(-1e-9), outer.buffer(1e-9)
    for deg in range(185, 360, 10):
        p = Point(5 + 2 * math.cos(math.radians(deg)), 6 + 2 * math.sin(math.radians(deg)))
        assert not shrunk.contains(p)
        assert grown.contains(p)
        # ... and never further away from either polygon than the tolerance
        assert inner.distance(p) <= 0.01 + 1e-9 and outer.exterior.distance(p) <= 0.01 + 1e-9
    # rounded polygons with concave corners get the same treatment
    l_shape = RoundedPolygon(((0, 0), (4, 0), (4, 2), (2, 2), (2, 4), (0, 4)), 0.5)
    li = g.shape_polygon(l_shape, 0.01, "inscribed")
    lo = g.shape_polygon(l_shape, 0.01, "circumscribed")
    assert li.difference(lo).area < 1e-12 and li.area < lo.area
    exact_l = 12 - 5 * (1 - math.pi / 4) * 0.25 + (1 - math.pi / 4) * 0.25
    assert li.area < exact_l < lo.area


def test_d_shape_with_notch_and_cutout_keeps_exact_arcs():
    o = Outline(PathShape.d_shape(BOARD_RADIUS, FLAT_Y))
    o.add_cutout(Circle(9.0, -3.0, 6.5))                          # internal
    o.add_notch(RoundedPolygon.rect(0.0, -BOARD_RADIUS, 3.0, 2.0, 0.4))
    contours = g.outline_contours(o)
    assert len(contours) == 2 and isinstance(contours[1][0], g.FullCircle)
    arcs = [e for e in contours[0] if isinstance(e, g.Arc)]
    assert sorted(round(a.radius, 6) for a in arcs) == [0.4, 0.4, BOARD_RADIUS, BOARD_RADIUS]
    for a in arcs:
        for p in (a.start, a.mid, a.end):
            assert math.hypot(p[0] - a.center[0], p[1] - a.center[1]) == pytest.approx(
                a.radius, abs=1e-6)
    poly = o.polygon()
    assert not poly.contains(Point(9, -3)) and not poly.contains(Point(0, -20.8))
    assert not poly.contains(Point(0, 17.4)) and poly.contains(Point(0, 17.2))


# -- the reference design --------------------------------------------------------

@pytest.fixture(scope="module")
def dshape(tmp_path_factory):
    design = dshape_design()
    files = board.build_board(design, str(tmp_path_factory.mktemp("dshape")))
    return design, files


@pytest.fixture(scope="module")
def dshape_drc(dshape):
    design, files = dshape
    return drc.run_drc(files.pcb)


def test_reference_design_passes_the_checks():
    d = dshape_design()
    report = checks.run_checks(d)
    assert report.ok and not report.findings, report.text()
    sides = {p.side for p in d.parts}
    assert sides == {TOP, BOTTOM}
    assert sum(1 for p in d.parts if p.side == BOTTOM) == 18          # 16 LEDs, PD1, J2
    assert d.rules.name == "US_4L_FINE"
    assert {n.netclass for n in d.nets.values()} == {"Default", "Power", "Fine"}
    fine = sorted(n.name for n in d.nets.values() if n.netclass == "Fine")
    assert fine == sorted(["CAM_D%d" % i for i in range(8)] + ["CAM_HREF"])
    for net in CAM_BUS:                       # the bus is shared by both cameras
        refs = {ref for ref, _pin in d.nets[net].nodes}
        assert refs == {"U1", "U2", "U3"}, net


def test_part_beyond_the_flat_is_outside_the_outline():
    d = dshape_design()
    d.part("C5").place(4.0, 17.2)                 # inside the circle, beyond the chord
    r = checks.run_checks(d)
    assert [f.refs for f in r.find("outside_outline")] == [("C5",)]
    assert r.has("pad_edge_clearance")
    d.part("C5").place(4.0, 14.6)
    assert checks.run_checks(d).ok
    # the camera courtyards end 0.02 mm inside the flat
    cy = geometry.part_courtyard(d.part("U2"))
    assert cy.bounds[3] == pytest.approx(FLAT_Y - 0.02)


def test_edge_cuts_is_one_arc_plus_one_line(dshape):
    design, files = dshape
    text = open(files.pcb).read()
    assert text.count("(gr_arc") == 1 and text.count("(gr_line") == 1
    assert "gr_poly" not in text and "gr_circle" not in text
    m = re.search(r"\(gr_line \(start ([\d.]+) ([\d.]+)\) \(end ([\d.]+) ([\d.]+)\)", text)
    x0, y0, x1, y1 = (float(v) for v in m.groups())
    assert y0 == y1 == pytest.approx(100.0 - FLAT_Y)                 # KiCad y is down
    assert sorted((x0, x1)) == pytest.approx([100 - HALF_CHORD, 100 + HALF_CHORD], abs=1e-5)
    s = board.board_summary(files.pcb)
    half = board.EDGE_WIDTH_MM / 2
    assert s["edge_bbox"] == pytest.approx(
        [-BOARD_RADIUS - half, -BOARD_RADIUS - half, BOARD_RADIUS + half, FLAT_Y + half],
        abs=1e-3)
    assert s["copper_layers"] == 4 and s["thickness"] == pytest.approx(0.8)


def test_pads_match_model_on_both_sides(dshape):
    design, files = dshape
    s = board.board_summary(files.pcb)
    model = {}
    for pad in geometry.placed_pads(design):
        model.setdefault((pad.ref, pad.number), []).append(pad)
    n = 0
    for ref, fp in s["footprints"].items():
        part = design.part(ref)
        assert fp["side"] == part.side and (fp["x"], fp["y"]) == pytest.approx((part.x, part.y))
        for pad in fp["pads"]:
            cands = model[(ref, pad["number"])]
            best = min(cands, key=lambda c: math.hypot(c.x - pad["x"], c.y - pad["y"]))
            assert math.hypot(best.x - pad["x"], best.y - pad["y"]) < 1e-6, (ref, pad)
            assert (best.net or "") == pad["net"], (ref, pad)
            assert list(best.layers) == pad["layers"], (ref, pad)
            assert best.clearance == pad["clearance"], (ref, pad)
            n += 1
    assert n == sum(len(v) for v in model.values()) > 250


def test_bga_cameras_ball_a1_and_shared_bus(dshape):
    design, files = dshape
    for ref, cx in (("U2", -10.2), ("U3", 10.2)):
        pads = {p.number: p for p in geometry.part_pads(design, design.part(ref))}
        assert len(pads) == 25
        assert (pads["A1"].x, pads["A1"].y) == pytest.approx((cx - 1.0, 15.6 + 1.0))  # top-left
        assert (pads["E5"].x, pads["E5"].y) == pytest.approx((cx + 1.0, 15.6 - 1.0))
        assert (pads["C3"].x, pads["C3"].y) == pytest.approx((cx, 15.6))
        assert all(p.clearance == 0.09 and p.layers == ("F.Cu",) and p.shape == "circle"
                   and p.w == pytest.approx(0.23) for p in pads.values())
        assert pads["C3"].net == "CAM_D4" and pads["A2"].net == "CAM_PCLK"
        # pad to pad inside the BGA: 0.27 mm of copper gap
        assert pads["A1"].polygon.distance(pads["A2"].polygon) == pytest.approx(0.27, abs=0.006)
    text = open(files.pcb).read()
    assert text.count("(clearance 0.09)") == 50


def test_bottom_side_led_ring_and_contact_row(dshape):
    design, files = dshape
    s = board.board_summary(files.pcb)
    cx, cy, r = LED_RING
    for i in range(1, 17):
        fp = s["footprints"]["D%d" % i]
        assert fp["side"] == "bottom"
        assert math.hypot(fp["x"] - cx, fp["y"] - cy) == pytest.approx(r, abs=1e-3)
        assert all(p["layers"] == ["B.Cu"] for p in fp["pads"])
    row = s["footprints"]["J2"]
    assert row["side"] == "bottom" and row["lib_id"] == "gleda:ContactRow_7x1.8mm_P2.54"
    xs = [p["x"] for p in sorted(row["pads"], key=lambda p: int(p["number"]))]
    assert xs == pytest.approx([-7.62, -5.08, -2.54, 0.0, 2.54, 5.08, 7.62])
    assert all(p["y"] == pytest.approx(PAD_ROW_Y) and p["layers"] == ["B.Cu"]
               for p in row["pads"])
    nets = {p["number"]: p["net"] for p in row["pads"]}
    assert nets == {"1": "VBUS", "2": "USB_DM", "3": "USB_DP", "4": "GND", "5": "SWDIO",
                    "6": "SWCLK", "7": "NRST"}
    # bare contact pads: copper + mask opening on the bottom, no paste, not in BOM / PnP
    text = open(files.pcb).read()
    i = text.index('(footprint "gleda:ContactRow_7x1.8mm_P2.54"')
    block = text[i:text.index("(footprint ", i + 10)]
    assert '(layer "B.Cu")' in block[:200]
    assert block.count('(layers "B.Cu" "B.Mask")') == 7 and "Paste" not in block
    assert "exclude_from_pos_files exclude_from_bom" in block
    assert "(size 1.8 1.8)" in block
    # the two-pad photodiode sits in the middle of the ring
    pd = s["footprints"]["PD1"]
    assert (pd["x"], pd["y"], pd["side"]) == (cx, cy, "bottom")


def test_unrouted_d_board_has_no_geometry_errors(dshape, dshape_drc):
    design, files = dshape
    r = dshape_drc
    assert r.error_count == 0, r.summary()
    assert r.errors_by_type == {} and not r.footprint_errors and not r.tampered
    assert r.unconnected_count > 150                      # nothing is routed yet
    assert set(r.warnings_by_type) <= {"isolated_copper", "silk_edge_clearance",
                                       "silk_overlap", "silk_over_copper"}
    drc.assert_clean(r, allow_unconnected=True)
    with pytest.raises(drc.DrcError, match="unconnected"):
        drc.assert_clean(r)
    assert r.zones_filled == 2
    assert len(r.custom_rules) == 3


def test_top_view_svg_shows_the_flat_at_the_top(dshape, tmp_path):
    """+y up: the chord (y = +17.3) must be the TOP edge of the plotted board,
    the cameras just below it, the FPC connector near the bottom."""
    design, files = dshape
    svg = kicad_cli.export_svg(files.pcb, str(tmp_path / "top.svg"), ["F.Cu", "Edge.Cuts"])
    text = open(svg).read()
    boxes = kicad_cli.svg_color_bboxes(text)
    assert len(boxes) == 2
    # the edge layer spans the whole board; copper lies inside it
    (edge_color, edge), (cu_color, cu) = sorted(
        boxes.items(), key=lambda kv: -(kv[1][2] - kv[1][0]) * (kv[1][3] - kv[1][1]))
    width, height = edge[2] - edge[0], edge[3] - edge[1]
    assert width == pytest.approx(2 * BOARD_RADIUS, abs=0.1)
    assert height == pytest.approx(BOARD_RADIUS + FLAT_Y, abs=0.1)
    # board centre in SVG units: the arc's lowest point is one radius below it
    cx = (edge[0] + edge[2]) / 2
    cy = edge[3] - BOARD_RADIUS - board.EDGE_WIDTH_MM / 2
    assert cy - edge[1] == pytest.approx(FLAT_Y, abs=0.06)        # flat is 17.3 ABOVE centre
    assert edge[3] - cy == pytest.approx(BOARD_RADIUS, abs=0.06)  # arc is 21.2 BELOW centre

    def design_xy(sx, sy):
        return (sx - cx, cy - sy)

    paths = [d for c, k, d in kicad_cli.svg_elements(text) if c == cu_color]
    assert paths
    # topmost copper: camera balls (y = 16.6 + 0.115); lowest: FPC mounting pads
    top_y = max(design_xy(0, min(d[1::2]))[1] for d in paths if len(d) >= 2)
    low_y = min(design_xy(0, max(d[1::2]))[1] for d in paths if len(d) >= 2)
    cam_top = 15.6 + 1.0 + 0.115
    assert top_y == pytest.approx(cam_top, abs=0.05)
    fpc_low = min(p.polygon.bounds[1] for p in geometry.part_pads(design, design.part("J1")))
    assert low_y == pytest.approx(fpc_low, abs=0.05)


def test_bottom_layer_svg_is_mirrored_left_right_only(dshape, tmp_path):
    design, files = dshape
    xray = kicad_cli.export_svg(files.pcb, str(tmp_path / "b.svg"), ["B.Cu", "Edge.Cuts"])
    below = kicad_cli.export_svg(files.pcb, str(tmp_path / "bm.svg"), ["B.Cu", "Edge.Cuts"],
                                 mirror=True)

    def copper_box(path):
        boxes = kicad_cli.svg_color_bboxes(open(path).read())
        (_ec, edge), (_cc, cu) = sorted(
            boxes.items(), key=lambda kv: -(kv[1][2] - kv[1][0]) * (kv[1][3] - kv[1][1]))
        cx, cy = (edge[0] + edge[2]) / 2, edge[3] - BOARD_RADIUS - board.EDGE_WIDTH_MM / 2
        return (cu[0] - cx, cy - cu[3], cu[2] - cx, cy - cu[1])       # design-frame bbox

    a, b = copper_box(xray), copper_box(below)
    # contact row: x from -8.52 to +8.52 at y = -17 +- 0.9, the lowest copper
    assert a == pytest.approx((-8.52, PAD_ROW_Y - 0.9, 8.52, LED_RING[1] + LED_RING[2] + 0.5),
                              abs=0.3)
    assert b == pytest.approx((-a[2], a[1], -a[0], a[3]), abs=0.02)   # x mirrored, y kept


def test_d_board_build_is_deterministic(dshape, tmp_path):
    design, files = dshape
    again = board.build_board(dshape_design(), str(tmp_path))
    for name in ("pcb", "pro", "dru", "lib_table"):
        assert _md5(getattr(again, name)) != "" and _md5(getattr(again, name)) == _md5(
            os.path.join(tmp_path, os.path.basename(getattr(files, name))))
    fresh = _md5(again.pcb)
    assert fresh == _md5(board.build_board(dshape_design(), str(tmp_path / "b")).pcb)


def test_edge_clearance_is_measured_to_the_outline_centre_line(tmp_path):
    """Facts a router needs: KiCad measures copper-to-edge distance to the
    centre line of Edge.Cuts; exact for a track along the straight flat, but a
    round via against the curved edge loses a few micrometres to KiCad's arc
    approximation - hence :data:`gleda.geometry.DRC_SLACK`."""
    rule = 0.30
    results = {}
    for tag, gap in (("exact", rule), ("slack", rule + g.DRC_SLACK), ("short", rule - 0.02)):
        d = Design("edge_" + tag, Outline(PathShape.d_shape(BOARD_RADIUS, FLAT_Y)))
        d.add(Part("R1", "1k", R0402, mpn="X", x=-3, y=0),
              Part("R2", "1k", R0402, mpn="X", x=3, y=0))
        d.net("A", "R1.1", "R2.1")
        d.net("B", "R1.2", "R2.2")
        files = board.build_board(d, str(tmp_path / tag))
        w = 0.15
        y = FLAT_Y - gap - w / 2
        tracks = [Track("A", "F.Cu", -5.0, y, 5.0, y, w)]                 # along the flat
        vias = [Via("B", -(BOARD_RADIUS - gap - 0.25), 0.0, 0.5, 0.25)]  # at the curved edge
        board.apply_routing(files.pcb, tracks, vias)
        r = drc.run_drc(files.pcb)
        results[tag] = [v for v in r.violations if v.type == "copper_edge_clearance"]
    # exactly on the rule: the straight track passes, the via at the arc does not
    assert len(results["exact"]) == 1
    assert "Via" in results["exact"][0].items[1].description
    m = re.search(r"actual ([\d.]+) mm", results["exact"][0].description)
    assert rule - 0.005 < float(m.group(1)) < rule
    assert results["slack"] == []
    assert len(results["short"]) == 2
    assert any("actual 0.2800 mm" in v.description for v in results["short"])


# -- per-layer keep-outs under sensor bodies ------------------------------------

def test_body_keepout_shape_is_the_pad_free_area():
    d = dshape_design()
    imu, inc = d.keepouts[0], d.keepouts[1]
    assert (imu.name, imu.layers) == ("under_U4", ("F.Cu",))
    assert (imu.tracks, imu.vias, imu.copper, imu.pads, imu.footprints) == \
        (True, True, True, False, False)
    # LGA-14: pad inner ends at x = +-0.85, y = +-0.6, margin 0.15 -> 1.4 x 0.9 mm
    assert g.keepout_polygon(imu).bounds == pytest.approx((-11.7, 5.55, -10.3, 6.45))
    assert g.keepout_polygon(inc).bounds == pytest.approx((10.35, 4.35, 13.65, 7.65))
    for ko, ref in ((imu, "U4"), (inc, "U5")):
        poly = g.keepout_polygon(ko)
        for pad in geometry.part_pads(d, d.part(ref)):
            assert pad.polygon.distance(poly) >= 0.15 - 1e-6, (ref, pad.number)
    # follows rotation and side; margin shrinks the area
    d.part("U4").place(-11.0, 6.0, rotation=90.0)
    assert g.shape_polygon(g.body_keepout_shape(d, "U4", 0.15)).bounds == pytest.approx(
        (-11.45, 5.3, -10.55, 6.7))
    assert g.shape_polygon(g.body_keepout_shape(d, "U4", 0.25)).area < 1.4 * 0.9
    with pytest.raises(ValueError, match="no pad-free area"):
        g.body_keepout_shape(d, "U2")                       # BGA: balls everywhere
    with pytest.raises(KeyError):
        d.add_body_keepout("U99")


def test_kicad_enforces_the_top_layer_keepout_only_on_top(dshape, tmp_path):
    design, files = dshape
    out = str(tmp_path)
    files2 = board.build_board(dshape_design(), out)
    text = open(files2.pcb).read()
    i = text.index('(name "under_U5")')
    block = text[i - 200:i + 400]
    assert '(layer "F.Cu")' in block and "B.Cu" not in block
    assert "(tracks not_allowed)" in block and "(vias not_allowed)" in block
    assert "(copperpour not_allowed)" in block and "(footprints allowed)" in block
    j = text.index('(name "battery_body")')
    assert "(tracks allowed)" in text[j:j + 400] and "(footprints not_allowed)" in text[j:j + 400]
    # a B.Cu track right under the inclinometer is fine, the same track on F.Cu is not
    under = [Track("SPI_SCK", "B.Cu", 11.0, 6.0, 13.0, 6.0, 0.15)]
    board.apply_routing(files2.pcb, under, [])
    r = drc.run_drc(files2.pcb)
    assert r.error_count == 0, r.summary()
    board.apply_routing(files2.pcb, [Track("SPI_SCK", "F.Cu", 11.0, 6.0, 13.0, 6.0, 0.15)], [])
    r = drc.run_drc(files2.pcb)
    assert r.errors_by_type == {"items_not_allowed": 1}, r.summary()
    # a through via crosses F.Cu, so it violates the top-layer keep-out as well
    board.apply_routing(files2.pcb, [], [Via("GND", 12.0, 6.0, 0.5, 0.25)])
    r = drc.run_drc(files2.pcb)
    assert r.errors_by_type.get("items_not_allowed") == 1, r.summary()


def test_top_side_placement_keepout_ignores_bottom_parts():
    d = dshape_design()
    assert checks.run_checks(d).ok                 # the LED ring lies under the battery: fine
    d.part("R9").place(13.0, -3.0)                 # a top-side part under the battery body
    r = checks.run_checks(d)
    assert [f.refs for f in r.find("in_keepout")] == [("R9",)]
    assert "battery_body" in r.find("in_keepout")[0].message


def test_pad_buried_in_a_no_track_keepout_is_reported():
    d = dshape_design()
    d.add_keepout(RoundedPolygon.rect(13.0, 2.2, 3.0, 1.5), layers=("F.Cu",), name="blocked")
    r = checks.run_checks(d)
    assert r.ok
    assert sorted(f.message.split(" lies")[0] for f in r.find("keepout_blocks_pad")) == [
        "R9 pad 1 (net CAM_EN)", "R9 pad 2 (net GND)"]


def test_pad_spacing_check_catches_a_bad_land_pattern():
    from gleda import footprints as F
    d = dshape_design()
    bad = F.quad_package("LGA-16_bad", 5.0, 5.0, pitch=1.0, nx=4, ny=4, pad_w=0.5,
                         pad_l=0.8, pad_centre_inset=0.55)          # corner pads collide
    d.part("U5").footprint = bad
    r = checks.run_checks(d)
    msgs = [f.message for f in r.find("pad_spacing")]
    assert len(msgs) == 4 and msgs[0].startswith("U5 pads 1 (+3V0) and 16 (no net) are 0.000 mm")
    # two pads of the SAME net may touch; BGA pads rely on their clearance override
    assert not [f for f in r.find("pad_spacing") if "U2" in f.refs or "U1" in f.refs]


# -- via tenting ---------------------------------------------------------------------

def _tent_board(tmp_path, mode):
    d = Design("tent_" + mode, Outline(Circle(0, 0, 8)))
    d.via_tenting = mode
    d.add(Part("R1", "1k", R0402, mpn="X", x=-3, y=0),
          Part("R2", "1k", R0402, mpn="X", x=3, y=0, side=BOTTOM))
    d.net("A", "R1.1", "R2.1")
    d.net("B", "R1.2", "R2.2")
    files = board.build_board(d, str(tmp_path / mode))
    a, b = geometry.pad_position(d, "R1", "1"), geometry.pad_position(d, "R2", "1")
    a2, b2 = geometry.pad_position(d, "R1", "2"), geometry.pad_position(d, "R2", "2")
    tracks = [Track("A", "F.Cu", a[0], a[1], a[0], 2.0, 0.15),
              Track("A", "F.Cu", a[0], 2.0, 0.0, 2.0, 0.15),
              Track("A", "B.Cu", 0.0, 2.0, b[0], 2.0, 0.15),
              Track("A", "B.Cu", b[0], 2.0, b[0], b[1], 0.15),
              Track("B", "F.Cu", a2[0], a2[1], a2[0], -2.0, 0.15),
              Track("B", "F.Cu", a2[0], -2.0, 1.0, -2.0, 0.15),
              Track("B", "B.Cu", 1.0, -2.0, b2[0], -2.0, 0.15),
              Track("B", "B.Cu", b2[0], -2.0, b2[0], b2[1], 0.15)]
    vias = [Via("A", 0.0, 2.0, 0.5, 0.25), Via("B", 1.0, -2.0, 0.5, 0.25)]
    return d, files, tracks, vias


def _mask_flashes_at_vias(files, tmp_path, tag):
    """Which mask Gerbers contain an aperture at the via positions."""
    out = tmp_path / ("gerber_" + tag)
    out.mkdir()
    kicad_cli.run_kicad_cli(["pcb", "export", "gerbers", "--output", str(out) + "/",
                             "--layers", "F.Mask,B.Mask", "--use-drill-file-origin", files.pcb])
    hit = {}
    for fn in sorted(os.listdir(out)):
        if not fn.endswith((".gts", ".gbs")):
            continue
        text = open(out / fn).read()
        # via A at (0, 2): KiCad plots a filled circle as an arc of radius d/4 around it
        hit["F.Mask" if fn.endswith(".gts") else "B.Mask"] = \
            "X125000Y2000000" in text and "X1125000Y-2000000" in text
    return hit


@pytest.mark.parametrize("mode", ["both", "bottom", "top", "none"])
def test_via_tenting_modes(tmp_path, mode):
    d, files, tracks, vias = _tent_board(tmp_path, mode)
    assert board.project_via_tenting(files.pcb) == mode
    res = board.apply_routing(files.pcb, tracks, vias)        # mode comes from the project
    assert (res.tracks, res.vias) == (8, 2)
    open_layers = VIA_TENTING[mode]
    s = board.board_summary(files.pcb)
    assert s["via_mask_openings"] == {layer: 2 for layer in sorted(open_layers)}
    r = drc.run_drc(files.pcb)
    assert r.error_count == 0 and r.unconnected_count == 0, r.summary()
    drc.assert_clean(r)
    flashes = _mask_flashes_at_vias(files, tmp_path, mode)
    assert flashes == {"F.Mask": "F.Mask" in open_layers, "B.Mask": "B.Mask" in open_layers}


def test_tenting_openings_follow_the_routing(tmp_path):
    d, files, tracks, vias = _tent_board(tmp_path, "bottom")
    board.apply_routing(files.pcb, tracks, vias)
    first = _md5(files.pcb)
    board.apply_routing(files.pcb, tracks, vias)              # replace: no leftovers
    assert _md5(files.pcb) == first
    assert board.board_summary(files.pcb)["via_mask_openings"] == {"F.Mask": 2}
    text = open(files.pcb).read()
    assert text.count('(group "%s"' % board.VIA_MASK_GROUP) == 1
    assert text.count('(fill solid) (layer "F.Mask")') == 2
    board.apply_routing(files.pcb, tracks[:4], vias[:1])
    assert board.board_summary(files.pcb)["via_mask_openings"] == {"F.Mask": 1}
    board.apply_routing(files.pcb, tracks[4:], vias[1:], replace=False)
    assert board.board_summary(files.pcb)["via_mask_openings"] == {"F.Mask": 2}
    assert open(files.pcb).read().count('(group "%s"' % board.VIA_MASK_GROUP) == 1
    # explicit override, and removal together with the vias
    board.apply_routing(files.pcb, tracks, vias, via_tenting="none")
    assert board.board_summary(files.pcb)["via_mask_openings"] == {"B.Mask": 2, "F.Mask": 2}
    board.apply_routing(files.pcb, [], [])
    assert board.board_summary(files.pcb)["via_mask_openings"] == {}
    assert board.VIA_MASK_GROUP not in open(files.pcb).read()
    with pytest.raises(board.BoardBuildError, match="via_tenting"):
        board.apply_routing(files.pcb, tracks, vias, via_tenting="sideways")


def test_bad_tenting_mode_is_rejected(tmp_path):
    d = Design("t", Circle(0, 0, 5))
    d.via_tenting = "sideways"
    assert checks.run_checks(d, footprints=False).has("rule_violation")
    with pytest.raises(board.BoardBuildError, match="via_tenting"):
        board.build_board(d, str(tmp_path))


def test_d_board_records_tenting_and_plot_default(dshape):
    design, files = dshape
    assert design.via_tenting == "bottom"
    assert board.project_via_tenting(files.pcb) == "bottom"
    # KiCad's global "plot vias on mask" switch stays off: tenting is explicit
    assert "(viasonmask false)" in open(files.pcb).read()
