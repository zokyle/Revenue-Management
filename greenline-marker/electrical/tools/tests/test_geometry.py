"""Outline primitives, polygonisation and arc re-fitting."""
import math

import pytest

from gleda import geometry as g
from gleda.model import Circle, RoundedPolygon, Slot, Outline


def _closed(path, eps=1e-9):
    for k, el in enumerate(path):
        prev = path[k - 1]
        assert math.hypot(prev.end[0] - el.start[0], prev.end[1] - el.start[1]) < eps, k


def test_circle_polygon_inscribed_and_circumscribed():
    c = Circle(1, 2, 10)
    tol = 0.005
    inner = g.shape_polygon(c, tol, "inscribed")
    outer = g.shape_polygon(c, tol, "circumscribed")
    true_area = math.pi * 100
    assert inner.area < true_area < outer.area
    assert true_area - inner.area < 2 * math.pi * 10 * tol
    for x, y in inner.exterior.coords:
        assert math.hypot(x - 1, y - 2) == pytest.approx(10)
    # every edge midpoint of the inscribed polygon is within tol of the circle
    pts = list(inner.exterior.coords)
    for a, b in zip(pts, pts[1:]):
        mid = ((a[0] + b[0]) / 2 - 1, (a[1] + b[1]) / 2 - 2)
        assert 10 - math.hypot(*mid) <= tol + 1e-9
    for x, y in outer.exterior.coords:
        assert math.hypot(x - 1, y - 2) >= 10 - 1e-9
        assert math.hypot(x - 1, y - 2) <= 10 + tol + 1e-9


def test_rounded_rect_path():
    r = RoundedPolygon.rect(0, 0, 10, 6, radius=1)
    path = g.shape_path(r)
    assert [type(e).__name__ for e in path].count("Arc") == 4
    assert [type(e).__name__ for e in path].count("Line") == 4
    _closed(path)
    for el in path:
        if isinstance(el, g.Arc):
            assert el.radius == pytest.approx(1)
            assert abs(el.angles[1]) == pytest.approx(math.pi / 2)
    poly = g.shape_polygon(r)
    exact = 10 * 6 - (4 - math.pi) * 1 * 1
    assert poly.area == pytest.approx(exact, abs=0.03)
    assert poly.area <= exact          # inscribed
    assert poly.bounds == pytest.approx((-5, -3, 5, 3))


def test_rounded_polygon_radius_is_clamped():
    r = RoundedPolygon.rect(0, 0, 2, 1, radius=5)       # radius larger than the part
    path = g.shape_path(r)
    _closed(path)
    for el in path:
        if isinstance(el, g.Arc):
            assert el.radius <= 0.5 + 1e-9
    assert g.shape_polygon(r).is_valid


def test_sharp_polygon_and_concave_corner():
    l_shape = RoundedPolygon(((0, 0), (4, 0), (4, 2), (2, 2), (2, 4), (0, 4)), 0.3)
    path = g.shape_path(l_shape)
    _closed(path)
    poly = g.shape_polygon(l_shape)
    assert poly.is_valid
    assert poly.area == pytest.approx(12 - 5 * (1 - math.pi / 4) * 0.09
                                      + (1 - math.pi / 4) * 0.09, abs=0.01)
    sharp = RoundedPolygon(((0, 0), (4, 0), (4, 2)))
    assert all(isinstance(e, g.Line) for e in g.shape_path(sharp))


def test_slot_shape():
    s = Slot(0, 0, 4, 0, 1.0)
    path = g.shape_path(s)
    _closed(path)
    poly = g.shape_polygon(s)
    assert poly.area == pytest.approx(4 * 1 + math.pi * 0.25, abs=0.01)
    assert poly.bounds == pytest.approx((-0.5, -0.5, 4.5, 0.5), abs=1e-6)
    dot = g.shape_path(Slot(1, 1, 1, 1, 2.0))
    assert isinstance(dot[0], g.FullCircle) and dot[0].radius == 1.0


def test_cutout_classification_and_board_polygon():
    o = Outline(Circle(0, 0, 15))
    o.add_cutout(Circle(8, 0, 3))                              # internal
    o.add_notch(RoundedPolygon.rect(0, -15, 3, 2, 0.4))        # crosses the edge
    o.add_slot(-6, -11, -4, -11, 0.8)                          # internal slot
    o.add_hole(-11.5, 5, 1.2)
    internal, notches = g.classify_cutouts(o)
    assert len(internal) == 2 and len(notches) == 1
    poly = o.polygon()
    assert len(poly.interiors) == 2
    from shapely.geometry import Point
    assert poly.contains(Point(0, 0))
    assert not poly.contains(Point(8, 0))            # inside the cutout
    assert not poly.contains(Point(0, -14.5))        # inside the notch
    assert not poly.contains(Point(-5, -11))         # inside the slot
    assert poly.contains(Point(-11.5, 5))            # NPTH holes are not subtracted
    assert len(g.hole_polygons(o)) == 1
    # conservative: the polygon lies inside the true board
    assert poly.area < math.pi * 225 - math.pi * 9


def test_outline_contours_exact_without_notches():
    o = Outline(Circle(0, 0, 19))
    o.add_cutout(Circle(9, 0, 6.5))
    contours = g.outline_contours(o)
    assert len(contours) == 2
    assert isinstance(contours[0][0], g.FullCircle) and contours[0][0].radius == 19
    assert isinstance(contours[1][0], g.FullCircle) and contours[1][0].center == (9, 0)


def test_outline_contours_with_notch_refits_arcs():
    o = Outline(Circle(0, 0, 15))
    o.add_notch(RoundedPolygon.rect(0, -15, 3, 2, 0.4))
    o.add_notch(Circle(-15, 0, 1.5))
    contours = g.outline_contours(o)
    assert len(contours) == 1
    path = contours[0]
    _closed(path)
    arcs = [e for e in path if isinstance(e, g.Arc)]
    lines = [e for e in path if isinstance(e, g.Line)]
    # two arcs of the board circle, one of the round notch, two notch corners
    radii = sorted(round(a.radius, 6) for a in arcs)
    assert radii == [0.4, 0.4, 1.5, 15.0, 15.0]
    assert len(lines) == 3
    # the big arcs together cover the circle minus the two notches
    sweep = sum(abs(a.angles[1]) for a in arcs if a.radius == 15)
    # rectangular notch 3 mm wide: 2*asin(1.5/15); round notch r=1.5 centred on
    # the edge: 2 * 2*asin(1.5/(2*15))
    assert 2 * math.pi - sweep == pytest.approx(
        2 * math.asin(1.5 / 15) + 4 * math.asin(1.5 / 30), abs=1e-3)
    # all arc end points lie exactly on their circles
    for a in arcs:
        for p in (a.start, a.mid, a.end):
            assert math.hypot(p[0] - a.center[0], p[1] - a.center[1]) == pytest.approx(
                a.radius, abs=1e-6)


def test_refit_arcs_leaves_plain_polygons_alone():
    square = [(0, 0), (2, 0), (2, 2), (0, 2)]
    path = g.refit_arcs(square, [((5, 5), 1.0)])
    assert len(path) == 4 and all(isinstance(e, g.Line) for e in path)


def test_refit_arcs_full_circle():
    pts = g.path_points([g.FullCircle((1, 1), 3)], 0.001)
    path = g.refit_arcs(pts, [((1, 1), 3.0)], 0.001)
    assert len(path) == 1 and isinstance(path[0], g.FullCircle)


def test_split_board_is_rejected():
    o = Outline(RoundedPolygon.rect(0, 0, 10, 4))
    o.add_cutout(RoundedPolygon.rect(0, 0, 1, 6))        # cuts the board in two
    with pytest.raises(ValueError):
        o.polygon()


def test_circumcircle():
    c, r = g.circumcircle((1, 0), (0, 1), (-1, 0))
    assert c == pytest.approx((0, 0)) and r == pytest.approx(1)
    assert g.circumcircle((0, 0), (1, 1), (2, 2)) is None


# -- placed part geometry (uses pcbnew through gleda.footprints) --------------

def test_placed_pads_cover_all_parts_and_layers(mini):
    pads = g.placed_pads(mini)
    assert len(pads) == 78
    by_net = g.pads_by_net(mini)
    assert set(by_net) == set(mini.nets)
    assert sum(len(v) for v in by_net.values()) == len([p for p in pads if p.net])
    # no-connect pads carry no net but are still obstacles with copper
    nc = [p for p in pads if p.ref == "U1" and p.number == "19"]
    assert len(nc) == 1 and nc[0].net is None and nc[0].polygon is not None
    assert nc[0].pin == "NC"
    for p in pads:
        assert p.layers in (("F.Cu",), ("B.Cu",))
        assert p.polygon.is_valid and p.polygon.area > 0
        assert p.polygon.contains(__import__("shapely.geometry").geometry.Point(p.x, p.y))
        assert p.side == mini.part(p.ref).side
        assert p.key == "%s.%s" % (p.ref, p.number)


def test_pad_polygon_follows_rotation_and_flip(mini):
    # C1: top side, rotated 90 -> the 0.56 x 0.62 pad becomes 0.62 wide, 0.56 tall
    pad = [p for p in g.part_pads(mini, mini.part("C1")) if p.number == "1"][0]
    x0, y0, x1, y1 = pad.polygon.bounds
    assert (x1 - x0, y1 - y0) == pytest.approx((0.62, 0.56), abs=0.011)
    assert (pad.x, pad.y) == pytest.approx((-9.3, 4.0 - 0.48))
    assert pad.rotation == 90
    # U3 (SOT-23-5): bottom side, rotation 180
    u3 = {p.number: p for p in g.part_pads(mini, mini.part("U3"))}
    assert u3["1"].layers == ("B.Cu",)
    # top side pin 1 is at local (-1.1375, +0.95); flip -> (-1.1375, -0.95); rot 180 -> (+, +)
    assert (u3["1"].x, u3["1"].y) == pytest.approx((3.0 + 1.1375, -8.5 + 0.95))


def test_courtyard_and_body(mini):
    cy = g.part_courtyard(mini.part("U1"))
    x0, y0, x1, y1 = cy.bounds
    assert (x0, x1) == pytest.approx((-3.5 - 4.05, -3.5 + 4.05))
    body = g.part_body(mini.part("U1"))
    assert (body["length"], body["width"], body["height"]) == (7.0, 9.0, 1.8)
    assert (body["cx"], body["cy"]) == (-3.5, 1.5)
    assert body["side"] == "top" and body["rotation"] == 0.0
    # library part: body from the fab outline, height from the Part
    c1 = g.part_body(mini.part("C1"))
    assert (c1["length"], c1["width"], c1["height"]) == (1.0, 0.5, 0.55)
    # asymmetric connector body: centre differs from the anchor and follows the flip
    j1 = g.part_body(mini.part("J1"))
    assert j1["side"] == "bottom" and j1["cx"] == pytest.approx(-4.0)
    assert j1["cy"] != pytest.approx(7.0)
    assert g.part_body_polygon(mini.part("J1")).centroid.y == pytest.approx(j1["cy"])
    mini.part("C1").body = (1.2, 0.6)
    assert g.part_body(mini.part("C1"))["length"] == 1.2


def test_pad_position_errors(mini):
    with pytest.raises(KeyError):
        g.pad_position(mini, "C1", "9")
    mini.part("C1").x = None
    with pytest.raises(ValueError):
        g.part_pads(mini, mini.part("C1"))
    assert len(g.placed_pads(mini)) == 76          # unplaced parts are skipped


def test_inflated_pad_is_conservative(mini):
    import math as m
    tp = [p for p in g.placed_pads(mini) if p.ref == "TP1"][0]       # 1.0 mm round pad
    grown = tp.inflated(0.2)
    # the true copper circle (r = 0.5) grown by 0.2 must be inside the keep-out
    for i in range(360):
        a = m.radians(i)
        from shapely.geometry import Point
        assert grown.contains(Point(tp.x + 0.7 * m.cos(a), tp.y + 0.7 * m.sin(a)))
    assert grown.bounds[2] - grown.bounds[0] < 1.4 + 2 * g.PAD_POLYGON_TOLERANCE + 1e-6
