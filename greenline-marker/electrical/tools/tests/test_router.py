"""Router tests: clearance maths of the grid, the A* kernel, the cleanup pass,
the audit, and routing of small synthetic boards that are then judged by
KiCad's DRC (0 errors, 0 unconnected).

The synthetic boards are 4-layer boards with bare test pads, so each case
isolates one capability: a straight connection, a via, a wall, negotiation
(rip-up), a multi-pin net, a plane net, a mixed plane layer, a fine-pitch BGA.
"""
import math
import os
from dataclasses import replace

import numpy as np
import pytest
from shapely.geometry import LineString, Point

from gleda import _astar, board, drc, geometry, router
from gleda import footprints as F
from gleda.model import (Design, Outline, RoundedPolygon, Circle, Part, Track, Via, BOTTOM,
                         US_4L_STD, US_4L_FINE)
from gleda.raster import (EPS, Grid, move_margin, point_segment_distance,
                          segment_segment_distance, segments_intersect)
from gleda.router import RouterOptions, audit, cleanup_segments, plane_regions, route

HEADER3 = "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical"
OUTER = ("F.Cu", "B.Cu")


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def make_board(name, w=14.0, h=10.0, rules=US_4L_STD):
    return Design(name, Outline(RoundedPolygon.rect(0.0, 0.0, w, h)), layers=4, rules=rules)


def tp(d, ref, x, y, side="top", dia=1.0):
    d.add(Part(ref, "TP", F.test_pad(dia), pins={"1": "1"}, x=x, y=y, side=side,
               in_bom=False, height_mm=0.0))


def wall(d, x, y0, y1, thickness=0.5, layers="all", vias=True):
    d.add_keepout(RoundedPolygon.rect(x, (y0 + y1) / 2.0, thickness, y1 - y0), layers=layers,
                  tracks=True, vias=vias, copper=False, name="wall")


def kicad_judge(design, result, tmp_path):
    """Write the routing into a real board and let KiCad's DRC decide."""
    files = board.build_board(design, str(tmp_path))
    board.apply_routing(files.pcb, result.tracks, result.vias, via_tenting=design.via_tenting)
    res = drc.run_drc(files.pcb)
    drc.assert_clean(res)
    assert res.error_count == 0 and res.unconnected_count == 0
    return res


def length(tracks, net=None, layer=None):
    return sum(t.length for t in tracks
               if (net is None or t.net == net) and (layer is None or t.layer == layer))


# --------------------------------------------------------------------------
# grid and clearance maths
# --------------------------------------------------------------------------

def test_grid_nodes_are_multiples_of_the_pitch():
    g = Grid((-7.0, -5.0, 7.0, 5.0), 0.05)
    ix, iy = g.nearest(1.25, -0.4)
    assert g.xy(ix, iy) == (1.25, -0.4)
    assert g.is_node(1.25, -0.4) and not g.is_node(1.26, -0.4)
    assert g.inside(ix, iy) and not g.inside(-1, 0)
    assert g.shape == (g.ny, g.nx)
    # the grid covers the bounds plus a border
    assert g.x_of(0) < -7.0 and g.x_of(g.nx - 1) > 7.0
    win = g.window(0.0, 0.0, 0.1, 0.1)
    assert (win[1] - win[0], win[3] - win[2]) == (3, 3)
    assert g.window(100.0, 100.0, 101.0, 101.0) is None


def test_disc_mask_is_exact_at_the_boundary():
    """A node exactly ``reach`` away from an obstacle is free, one closer is not."""
    g = Grid((-2.0, -2.0, 2.0, 2.0), 0.05)
    win, mask = g.disc_mask(0.0, 0.0, 0.25)
    blocked = {(round(g.x_of(win[2] + x), 3), round(g.y_of(win[0] + y), 3))
               for y, x in zip(*np.nonzero(mask))}
    assert (0.25, 0.0) not in blocked and (0.0, -0.25) not in blocked
    assert (0.2, 0.0) in blocked and (0.15, 0.15) in blocked
    assert (0.2, 0.15) not in blocked           # exactly 0.25 away: free
    assert all(math.hypot(x, y) < 0.25 - EPS for x, y in blocked)


def test_one_track_fits_between_two_bga_balls():
    """0.23 mm balls at 0.5 mm pitch, 0.09 mm track, 0.09 mm clearance: the
    node half way between two balls is exactly at the limit - and free."""
    g = Grid((-2.0, -2.0, 2.0, 2.0), 0.05)
    reach = 0.23 / 2.0 + 0.09 + 0.09 / 2.0       # ball radius + clearance + half track
    assert reach == pytest.approx(0.25)
    blocked = np.zeros(g.shape, dtype=bool)
    for cx in (-0.25, 0.25):
        win, mask = g.disc_mask(cx, 0.0, reach)
        blocked[win[0]:win[1], win[2]:win[3]] |= mask
    ix, iy = g.nearest(0.0, 0.0)
    column = blocked[:, ix]
    assert not column.any()                      # the whole lane x = 0 is open
    assert blocked[iy, ix + 1] and blocked[iy, ix - 1]
    # with the 0.25 mm pads of the first footprint proposal the lane is closed
    win, mask = g.disc_mask(0.25, 0.0, 0.25 / 2.0 + 0.09 + 0.045)
    assert mask[iy - win[0], ix - win[2]]


def test_stadium_mask_matches_point_segment_distance():
    g = Grid((-3.0, -3.0, 3.0, 3.0), 0.1)
    rng = np.random.RandomState(1)
    for _ in range(20):
        x1, y1, x2, y2 = rng.uniform(-2.0, 2.0, 4)
        radius = rng.uniform(0.15, 0.6)
        got = np.zeros(g.shape, dtype=bool)
        m = g.stadium_mask(x1, y1, x2, y2, radius)
        if m:
            win, mask = m
            got[win[0]:win[1], win[2]:win[3]] = mask
        for iy in range(0, g.ny, 3):
            for ix in range(0, g.nx, 3):
                dist = point_segment_distance(g.x_of(ix), g.y_of(iy), x1, y1, x2, y2)
                if abs(dist - radius) > 1e-4:
                    assert got[iy, ix] == (dist < radius)


def test_polygon_mask_grows_by_the_radius():
    g = Grid((-3.0, -3.0, 3.0, 3.0), 0.05)
    rect = RoundedPolygon.rect(0.0, 0.0, 1.0, 0.6)
    poly = geometry.shape_polygon(rect)
    win, mask = g.polygon_mask(poly, 0.2)
    got = np.zeros(g.shape, dtype=bool)
    got[win[0]:win[1], win[2]:win[3]] = mask

    def at(x, y):
        ix, iy = g.nearest(x, y)
        return bool(got[iy, ix])

    assert at(0.0, 0.0) and at(0.65, 0.0) and at(0.0, 0.45)
    assert not at(0.7, 0.0)                      # exactly 0.2 from the edge: free
    assert not at(0.65, 0.45)                    # corner: 0.212 away
    assert g.contained_mask(poly)[g.nearest(0.5, 0.3)[1], g.nearest(0.5, 0.3)[0]]
    nodes = g.nodes_in(poly, 0.02)
    assert len(nodes) == 19 * 11                 # nodes strictly inside the shrunk pad


def test_move_margin_makes_moves_between_free_nodes_clear():
    """Obstacle half way between two nodes: with the margin both nodes are
    blocked exactly when the track between them would come too close."""
    reach, pitch = 0.135, 0.05
    margin = move_margin(reach, pitch)
    assert margin == pytest.approx(math.sqrt(reach ** 2 + pitch ** 2 / 4.0) - reach)
    assert 0.002 < margin < 0.0025
    # a point obstacle at height d below the middle of a move: the nodes are
    # sqrt(d^2 + pitch^2/4) away, the track passes at d
    for d in (reach - 0.001, reach + 0.0001, reach + 0.01):
        node_dist = math.hypot(d, pitch / 2.0)
        node_free = node_dist >= reach + margin - EPS
        if node_free:
            assert d >= reach - EPS
    assert move_margin(0.0, 0.05) == pytest.approx(0.025)


def test_segment_distances():
    assert point_segment_distance(0.0, 1.0, -1.0, 0.0, 1.0, 0.0) == pytest.approx(1.0)
    assert point_segment_distance(3.0, 4.0, 0.0, 0.0, 0.0, 0.0) == pytest.approx(5.0)
    assert segments_intersect((0, 0, 2, 2), (0, 2, 2, 0))
    assert segments_intersect((0, 0, 1, 0), (1, 0, 1, 1))            # touching
    assert not segments_intersect((0, 0, 1, 0), (0, 0.5, 1, 0.5))
    assert segment_segment_distance((0, 0, 1, 0), (0, 0.5, 1, 0.5)) == pytest.approx(0.5)
    assert segment_segment_distance((0, 0, 2, 2), (0, 2, 2, 0)) == 0.0
    assert segment_segment_distance((0, 0, 1, 0), (2, 1, 3, 1)) == pytest.approx(math.sqrt(2.0))


# --------------------------------------------------------------------------
# A* kernel
# --------------------------------------------------------------------------

def _search(cost, viamap, src, dst, nv=1, tlayers=0, via_cost=50, h=True):
    L, H, W = cost.shape
    one = np.full(L, 10, dtype=np.int32)
    diag = np.full(L, 14, dtype=np.int32)

    def cell(l, x, y):
        return (l * H + y) * W + x

    s = np.array([cell(*c) for c in src], dtype=np.int32)
    t = np.array([cell(*c) for c in dst], dtype=np.int32)
    xs = [c[1] for c in dst] or [0]
    ys = [c[2] for c in dst] or [0]
    path, pops = _astar.search(cost, viamap, s, t, tlayers, one, one, diag, via_cost, nv,
                               min(xs), min(ys), max(xs), max(ys), 1 if h else 0, 1, 0)
    out = [(int(p) // (H * W), int(p) % W, (int(p) % (H * W)) // W) for p in path]
    return out, pops


def test_astar_straight_and_diagonal():
    cost = np.ones((1, 12, 12), dtype=np.int32)
    vm = np.zeros((12, 12), dtype=np.int32)
    path, _ = _search(cost, vm, [(0, 1, 1)], [(0, 9, 1)])
    assert path == [(0, x, 1) for x in range(1, 10)]
    path, _ = _search(cost, vm, [(0, 1, 1)], [(0, 6, 6)])
    assert len(path) == 6 and path[0] == (0, 1, 1) and path[-1] == (0, 6, 6)


def test_astar_goes_around_and_does_not_cut_corners():
    cost = np.ones((1, 9, 9), dtype=np.int32)
    cost[0, 0:7, 4] = 0                           # wall with an opening at the top
    vm = np.zeros((9, 9), dtype=np.int32)
    path, _ = _search(cost, vm, [(0, 1, 1)], [(0, 7, 1)])
    assert path and path[-1] == (0, 7, 1)
    assert all(cost[l, y, x] > 0 for l, x, y in path)
    # a single blocked cell: the diagonal past its corner is not allowed
    cost = np.ones((1, 5, 5), dtype=np.int32)
    cost[0, 1, 2] = 0
    path, _ = _search(cost, vm[:5, :5].copy(), [(0, 1, 1)], [(0, 2, 2)])
    assert path == [(0, 1, 1), (0, 1, 2), (0, 2, 2)]
    # no way at all
    cost = np.ones((1, 5, 5), dtype=np.int32)
    cost[0, :, 2] = 0
    path, _ = _search(cost, vm[:5, :5].copy(), [(0, 0, 0)], [(0, 4, 4)])
    assert path == []


def test_astar_uses_a_via_only_where_allowed_and_respects_the_limit():
    cost = np.ones((2, 7, 11), dtype=np.int32)
    cost[0, :, 5] = 0                             # wall on layer 0 only
    vm = np.zeros((7, 11), dtype=np.int32)
    path, _ = _search(cost, vm, [(0, 1, 3)], [(0, 9, 3)])
    assert path == []                             # no via sites: no path
    vm[3, 2] = 1
    vm[3, 8] = 1
    path, _ = _search(cost, vm, [(0, 1, 3)], [(0, 9, 3)])
    layers = [p[0] for p in path]
    assert path and layers.count(1) > 0 and layers[0] == 0 and layers[-1] == 0
    changes = sum(1 for a, b in zip(path, path[1:]) if a[0] != b[0])
    assert changes == 2
    assert all((x, y) in ((2, 3), (8, 3)) for a, b in zip(path, path[1:]) if a[0] != b[0]
               for (x, y) in [(a[1], a[2])])
    path, _ = _search(cost, vm, [(0, 1, 3)], [(0, 9, 3)], nv=2)      # at most one new via
    assert path == []
    path, _ = _search(cost, vm, [(0, 1, 3)], [(0, 9, 3)], nv=3)
    assert path
    # an existing via of the net is free and does not count
    vm[3, 2] = _astar.FREE_VIA
    path, _ = _search(cost, vm, [(0, 1, 3)], [(0, 9, 3)], nv=2)
    assert path
    # "reach that layer anywhere" target (plane fan-out)
    vm[:] = 0
    vm[3, 4] = 1
    path, _ = _search(cost, vm, [(0, 1, 3)], [], tlayers=0b10)
    assert path[-1] == (1, 4, 3) and path[-2] == (0, 4, 3)


def test_astar_prefers_cheap_cells_and_smooth_keeps_the_cost():
    cost = np.ones((1, 9, 15), dtype=np.int32)
    cost[0, 3:6, 4:11] = 200                      # expensive block in the direct line
    vm = np.zeros((9, 15), dtype=np.int32)
    path, _ = _search(cost, vm, [(0, 1, 4)], [(0, 13, 4)], h=False)
    assert all(cost[l, y, x] == 1 for l, x, y in path)
    H, W = 9, 15
    arr = np.array([(l * H + y) * W + x for l, x, y in path], dtype=np.int32)
    one = np.full(1, 10, dtype=np.int32)
    out = _astar.smooth(arr, cost, one, one, np.full(1, 14, dtype=np.int32), 400)
    assert out[0] == arr[0] and out[-1] == arr[-1] and len(out) <= len(arr)


# --------------------------------------------------------------------------
# cleanup pass
# --------------------------------------------------------------------------

def test_cleanup_merges_collinear_pieces():
    segs = [(0, (0, 0), (3, 0)), (0, (3, 0), (7, 0)), (0, (7, 0), (9, 2))]
    anchors = {(0, 0, 0), (0, 9, 2)}
    assert cleanup_segments(segs, anchors, set(), 2) == [
        (0, (0, 0), (7, 0)), (0, (7, 0), (9, 2))]
    # duplicates and overlaps vanish
    segs = [(0, (0, 0), (5, 0)), (0, (2, 0), (8, 0)), (0, (8, 0), (0, 0))]
    assert cleanup_segments(segs, {(0, 0, 0), (0, 8, 0)}, set(), 1) == [(0, (0, 0), (8, 0))]


def test_cleanup_removes_dangling_stubs_and_keeps_anchored_ends():
    segs = [(0, (0, 0), (10, 0)), (0, (5, 0), (5, 4))]            # T with a dangling arm
    anchors = {(0, 0, 0), (0, 10, 0)}
    assert cleanup_segments(segs, anchors, set(), 1) == [(0, (0, 0), (10, 0))]
    anchors.add((0, 5, 4))                                          # now the arm ends on a pad
    out = cleanup_segments(segs, anchors, set(), 1)
    assert sorted(out) == [(0, (0, 0), (5, 0)), (0, (5, 0), (5, 4)), (0, (5, 0), (10, 0))]


def test_cleanup_opens_loops():
    square = [(0, (0, 0), (4, 0)), (0, (4, 0), (4, 4)), (0, (4, 4), (0, 4)), (0, (0, 4), (0, 0))]
    anchors = {(0, 0, 0), (0, 4, 4)}
    out = cleanup_segments(square, anchors, set(), 1)
    total = sum(max(abs(b[0] - a[0]), abs(b[1] - a[1])) for _l, a, b in out)
    assert total == 8                                               # one way round is enough
    # a loop closed through two vias and the other layer is opened as well
    segs = [(0, (0, 0), (6, 0)), (1, (0, 0), (6, 0))]
    out = cleanup_segments(segs, {(0, 0, 0), (0, 6, 0), (1, 0, 0), (1, 6, 0)}, {(0, 0), (6, 0)}, 2)
    assert len(out) == 1


def test_cleanup_splits_at_vias_and_at_joints_with_other_widths():
    segs = [(0, (0, 0), (10, 0))]
    anchors = {(0, 0, 0), (0, 10, 0)}
    assert cleanup_segments(segs, anchors, {(4, 0)}, 2) == [
        (0, (0, 0), (4, 0)), (0, (4, 0), (10, 0))]
    assert cleanup_segments(segs, anchors, set(), 2, breaks={(0, 7, 0)}) == [
        (0, (0, 0), (7, 0)), (0, (7, 0), (10, 0))]
    with pytest.raises(ValueError):
        cleanup_segments([(0, (0, 0), (3, 1))], anchors, set(), 1)


# --------------------------------------------------------------------------
# audit (the router's own exact re-check)
# --------------------------------------------------------------------------

def _two_nets():
    d = make_board("audit")
    tp(d, "A1", -4.0, 1.0)
    tp(d, "A2", 4.0, 1.0)
    tp(d, "B1", -4.0, -1.0)
    tp(d, "B2", 4.0, -1.0)
    d.net("A", "A1.1", "A2.1")
    d.net("B", "B1.1", "B2.1")
    return d


def test_audit_accepts_clean_copper_and_counts_connections():
    d = _two_nets()
    tracks = [Track("A", "F.Cu", -4.0, 1.0, 4.0, 1.0, 0.15),
              Track("B", "F.Cu", -4.0, -1.0, 4.0, -1.0, 0.15)]
    res = audit(d, tracks, [])
    assert res.ok and res.connections_total == 2 and res.missing == 0


def test_audit_reports_missing_connections():
    d = _two_nets()
    res = audit(d, [Track("A", "F.Cu", -4.0, 1.0, 4.0, 1.0, 0.15)], [])
    assert not res.ok and res.missing == 1
    assert [u.net for u in res.unrouted] == ["B"]
    assert res.unrouted[0].pieces == [["B1.1"], ["B2.1"]]
    # a track that stops short of the pad does not connect
    res = audit(d, [Track("A", "F.Cu", -4.0, 1.0, 3.0, 1.0, 0.15),
                    Track("B", "F.Cu", -4.0, -1.0, 4.0, -1.0, 0.15)], [])
    assert [u.net for u in res.unrouted] == ["A"]


def test_audit_finds_rule_violations():
    d = _two_nets()
    good = Track("A", "F.Cu", -4.0, 1.0, 4.0, 1.0, 0.15)
    # 0.15 mm tracks 0.25 mm apart: gap 0.10 < 0.127
    close = [good, Track("B", "F.Cu", -4.0, -1.0, -3.0, 0.75, 0.15),
             Track("B", "F.Cu", -3.0, 0.75, 3.0, 0.75, 0.15),
             Track("B", "F.Cu", 3.0, 0.75, 4.0, -1.0, 0.15)]
    kinds = {v["type"] for v in audit(d, close, []).violations}
    assert kinds == {"clearance"}
    # too narrow, via with too small a ring, via too close to the edge, hole to hole
    res = audit(d, [replace(good, width=0.1)], [Via("A", 0.0, 1.0, 0.4, 0.25),
                                                Via("B", 6.8, -1.0, 0.5, 0.25),
                                                Via("B", 0.0, -1.0, 0.5, 0.25),
                                                Via("B", 0.45, -1.0, 0.5, 0.25)])
    kinds = {v["type"] for v in res.violations}
    assert {"track_width", "annular_width", "copper_edge_clearance", "hole_near_hole"} <= kinds
    # keep-outs
    wall(d, 0.0, -5.0, 5.0)
    kinds = {v["type"] for v in audit(d, [good], [Via("B", 0.0, -1.0, 0.5, 0.25)]).violations}
    assert kinds == {"items_not_allowed"}


# --------------------------------------------------------------------------
# routing small boards (KiCad's DRC is the judge)
# --------------------------------------------------------------------------

def test_straight_connection(tmp_path):
    d = make_board("straight")
    tp(d, "A1", -4.0, 0.0)
    tp(d, "A2", 4.0, 0.0)
    d.net("A", "A1.1", "A2.1")
    res = route(d)
    assert res.complete and res.connections_total == 1 and res.routed_fraction == 1.0
    assert res.vias == []
    assert [(t.layer, t.x1, t.y1, t.x2, t.y2, t.width) for t in res.tracks] == [
        ("F.Cu", -4.0, 0.0, 4.0, 0.0, 0.15)]
    kicad_judge(d, res, tmp_path)


def test_pads_on_opposite_sides_need_one_via(tmp_path):
    d = make_board("via")
    tp(d, "A1", -4.0, 0.0)
    tp(d, "A2", 4.0, 0.0, side=BOTTOM)
    d.net("A", "A1.1", "A2.1")
    res = route(d)
    assert res.complete and len(res.vias) == 1
    via = res.vias[0]
    assert (via.diameter, via.drill) == (0.5, 0.25)
    # never a via in a pad: it keeps clear of both pads' copper
    for x in (-4.0, 4.0):
        assert math.hypot(via.x - x, via.y) >= 0.5 + 0.25 + 0.1 - 1e-9
    assert {t.layer for t in res.tracks} == {"F.Cu", "B.Cu"}
    kicad_judge(d, res, tmp_path)


def test_wall_on_the_top_layer_is_passed_underneath(tmp_path):
    d = make_board("wall")
    tp(d, "A1", -4.0, 0.0)
    tp(d, "A2", 4.0, 0.0)
    d.net("A", "A1.1", "A2.1")
    wall(d, 0.0, -5.0, 5.0, layers=("F.Cu",), vias=False)      # no top-layer tracks across
    res = route(d, RouterOptions(layers=OUTER))
    assert res.complete and len(res.vias) == 2
    keepout = geometry.keepout_polygon(d.keepouts[0])
    for t in res.tracks:
        if t.layer == "F.Cu":
            line = LineString([(t.x1, t.y1), (t.x2, t.y2)])
            assert line.distance(keepout) >= t.width / 2.0
    assert length(res.tracks, layer="B.Cu") > 0.5
    kicad_judge(d, res, tmp_path)


def test_negotiation_makes_the_first_net_give_way(tmp_path):
    """Single layer, a wall with a wide and a narrow gap.  Net A (routed
    first) takes the wide gap by default; the wide net B fits only there, so
    A has to be ripped up and sent through the narrow gap."""
    d = make_board("ripup", 16.0, 12.0)
    for y0, y1 in ((-6.0, -0.4), (0.4, 3.75), (4.25, 6.0)):
        wall(d, 0.0, y0, y1)
    tp(d, "A1", -3.0, 0.0)
    tp(d, "A2", 3.0, 0.0)
    tp(d, "B1", -3.0, -2.2)
    tp(d, "B2", 3.0, -2.2)
    d.net("A", "A1.1", "A2.1")
    d.net("B", "B1.1", "B2.1", width=0.6)
    res = route(d, RouterOptions(layers=("F.Cu",)))
    assert res.complete and res.vias == []
    assert res.stats["iterations"] > 1                    # it did take a negotiation
    assert {t.width for t in res.tracks if t.net == "B"} == {0.6}
    crossing = {t.net: (t.y1 + t.y2) / 2.0 for t in res.tracks
                if min(t.x1, t.x2) < 0.0 < max(t.x1, t.x2)}
    assert abs(crossing["B"]) < 0.2 and crossing["A"] == pytest.approx(4.0, abs=0.2)
    kicad_judge(d, res, tmp_path)


def test_multi_pin_net_is_routed_as_a_tree(tmp_path):
    d = make_board("tree", 16.0, 10.0)
    pads = [("P1", -6.0, 0.0), ("P2", -2.0, 0.0), ("P3", 2.0, 0.0), ("P4", 6.0, 0.0),
            ("P5", 2.0, 3.0), ("P6", 0.0, -3.0)]
    for ref, x, y in pads:
        tp(d, ref, x, y)
    d.net("N", *["%s.1" % ref for ref, _x, _y in pads])
    res = route(d)
    assert res.complete and res.connections_total == 5 and res.vias == []
    # trunk 12 mm + branch to P5 (3 mm) + branch to P6 (joins the trunk, not a pad)
    assert length(res.tracks) == pytest.approx(12.0 + 3.0 + 3.0, abs=0.9)
    kicad_judge(d, res, tmp_path)


def test_connection_joins_existing_copper_not_just_pads():
    d = make_board("steiner", 16.0, 10.0)
    tp(d, "P1", -6.0, 0.0)
    tp(d, "P2", 6.0, 0.0)
    tp(d, "P3", 0.0, 2.5)
    d.net("N", "P1.1", "P2.1", "P3.1")
    res = route(d)
    assert res.complete
    # P3 drops onto the P1-P2 track (12 mm) with a short branch, not to a pad
    assert 13.9 <= length(res.tracks) <= 14.6


def test_plane_net_gets_a_stub_and_a_via_per_pad(tmp_path):
    d = make_board("plane")
    for ref, x, y in (("G1", -4.0, 2.0), ("G2", 4.0, 2.0), ("G3", 0.0, -2.0)):
        tp(d, ref, x, y)
    tp(d, "G4", -2.5, -3.5, side=BOTTOM)
    tp(d, "S1", -4.0, -2.0)
    tp(d, "S2", 4.0, -2.0)
    d.net("GND", "G1.1", "G2.1", "G3.1", "G4.1")
    d.net("S", "S1.1", "S2.1")
    d.add_plane("GND", "In1.Cu")
    assert d.signal_layers() == ("F.Cu", "In2.Cu", "B.Cu")
    res = route(d)
    assert res.complete and res.stats["plane_nets"] == {"GND": "In1.Cu"}
    gnd_vias = [v for v in res.vias if v.net == "GND"]
    assert len(gnd_vias) == 4 and len(res.vias) == 4
    assert res.audit.plane_pieces == {"GND/In1.Cu": 1}
    pads = {p.key: p for p in geometry.placed_pads(d) if p.net == "GND"}
    for pad in pads.values():
        nearest = min(math.hypot(v.x - pad.x, v.y - pad.y) for v in gnd_vias)
        assert 0.5 + 0.25 + 0.1 - 1e-9 <= nearest <= 1.5        # short stub, via outside the pad
    assert length(res.tracks, net="GND") < 4 * 1.5
    out = kicad_judge(d, res, tmp_path)
    assert out.zones_filled


def test_through_hole_pads_change_layer_for_free(tmp_path):
    d = make_board("header")
    d.add(Part("J1", "HDR", HEADER3, pins={"1": "1", "2": "2", "3": "3"}, x=-4.0, y=2.54,
               rotation=0.0, in_bom=False, height_mm=8.5))
    tp(d, "T1", 4.0, 2.0)
    tp(d, "B1", 4.0, 0.0, side=BOTTOM)
    tp(d, "G1", 4.0, -2.5)
    d.net("TOPSIG", "J1.1", "T1.1")
    d.net("BOTSIG", "J1.2", "B1.1")
    d.net("GND", "J1.3", "G1.1")
    d.add_plane("GND", "In1.Cu")
    res = route(d)
    assert res.complete
    # the plated pins need no vias; only the SMD ground pad drops into the plane
    assert [v.net for v in res.vias] == ["GND"]
    assert {t.layer for t in res.tracks if t.net == "BOTSIG"} == {"B.Cu"}
    kicad_judge(d, res, tmp_path)


def test_off_grid_pads_are_connected_at_their_centre(tmp_path):
    d = make_board("offgrid")
    tp(d, "A1", -4.013, 0.527)
    tp(d, "A2", 3.981, -0.411)
    d.net("A", "A1.1", "A2.1")
    res = route(d)
    assert res.complete
    ends = {(t.x1, t.y1) for t in res.tracks} | {(t.x2, t.y2) for t in res.tracks}
    assert (-4.013, 0.527) in ends and (3.981, -0.411) in ends
    kicad_judge(d, res, tmp_path)


def test_per_net_options_are_honoured(tmp_path):
    d = make_board("options", 16.0, 12.0)
    for i, y in enumerate((4.0, 2.0, 0.0, -2.0, -4.0)):
        tp(d, "L%d" % i, -5.0, y)
        tp(d, "R%d" % i, 5.0, y, side=BOTTOM if i in (1,) else "top")
    d.net("WIDE", "L0.1", "R0.1", width=0.4)
    d.net("CROSS", "L1.1", "R1.1")                          # top pad to bottom pad
    d.net("TOPONLY", "L2.1", "R2.1", layers=("F.Cu",))
    d.net("NOVIA", "L3.1", "R3.1", max_vias=0)
    d.net("MANUAL", "L4.1", "R4.1", no_route=True)
    d.add_netclass("Fat", track_width=0.5, clearance=0.2)
    tp(d, "F1", -2.0, -5.2)
    tp(d, "F2", 2.0, -5.2)
    d.net("FAT", "F1.1", "F2.1", netclass="Fat")
    res = route(d)
    assert res.complete
    by_net = {}
    for t in res.tracks:
        by_net.setdefault(t.net, []).append(t)
    assert {t.width for t in by_net["WIDE"]} == {0.4}
    assert {t.width for t in by_net["FAT"]} == {0.5}
    assert {t.layer for t in by_net["TOPONLY"]} == {"F.Cu"}
    assert {t.layer for t in by_net["NOVIA"]} == {"F.Cu"}
    assert "MANUAL" not in by_net and res.connections_total == 5
    assert sorted(v.net for v in res.vias) == ["CROSS"]
    # the Fat class keeps its own clearance: nothing foreign within 0.2 mm
    fat = [LineString([(t.x1, t.y1), (t.x2, t.y2)]).buffer(t.width / 2.0) for t in by_net["FAT"]]
    for t in res.tracks:
        if t.net != "FAT" and t.layer == "F.Cu":
            other = LineString([(t.x1, t.y1), (t.x2, t.y2)]).buffer(t.width / 2.0)
            assert min(f.distance(other) for f in fat) >= 0.2 - 1e-6
    # KiCad: MANUAL is deliberately left open, everything else must be clean
    files = board.build_board(d, str(tmp_path))
    board.apply_routing(files.pcb, res.tracks, res.vias)
    out = drc.run_drc(files.pcb)
    assert out.error_count == 0 and out.unconnected_count == 1
    with pytest.raises(drc.DrcError):
        drc.assert_clean(out)


def test_copper_keeps_away_from_edge_holes_and_cutouts(tmp_path):
    outline = Outline(RoundedPolygon.rect(0.0, 0.0, 14.0, 8.0))
    outline.add_hole(0.0, 0.0, 1.15, name="H1")                       # locating hole
    outline.add_npth_slot(0.0, -1.9, width=1.15, length=1.65)          # locating slot
    outline.add_cutout(Circle(0.0, 1.9, 0.6))
    d = Design("holes", outline, layers=4, rules=US_4L_STD)
    tp(d, "A1", -5.0, 0.0)
    tp(d, "A2", 5.0, 0.0)
    tp(d, "B1", -5.0, -1.9)
    tp(d, "B2", 5.0, -1.9)
    d.net("A", "A1.1", "A2.1")
    d.net("B", "B1.1", "B2.1")
    res = route(d, RouterOptions(layers=OUTER))
    assert res.complete
    boundary = geometry.outline_polygon(d.outline).boundary
    for t in res.tracks:
        line = LineString([(t.x1, t.y1), (t.x2, t.y2)])
        assert line.distance(boundary) - t.width / 2.0 >= 0.3
        assert line.distance(Point(0.0, 0.0)) - 1.15 / 2.0 - t.width / 2.0 >= 0.2
    kicad_judge(d, res, tmp_path)


def test_unroutable_connection_is_reported_not_faked(tmp_path):
    d = make_board("blocked")
    tp(d, "A1", -4.0, 0.0)
    tp(d, "A2", 4.0, 0.0)
    tp(d, "B1", -4.0, 3.0)
    tp(d, "B2", 4.0, 3.0)
    d.net("A", "A1.1", "A2.1")
    d.net("B", "B1.1", "B2.1")
    wall(d, 0.0, -1.0, 5.0)                                            # reaches the top edge ...
    d.add_keepout(RoundedPolygon.rect(4.0, 0.0, 3.0, 3.0), name="cage")  # ... and A2 is caged
    res = route(d)
    assert not res.complete
    assert res.connections_total == 2 and res.connections_routed == 1
    assert res.routed_fraction == 0.5
    assert [u.net for u in res.unrouted] == ["A"]
    assert any(name.startswith("A:") for name in res.failures)
    assert "50.0 %" in res.summary()
    files = board.build_board(d, str(tmp_path))
    result, out = router.route_board(d, files.pcb)
    assert out.unconnected_count == 1 and out.error_count == 0
    with pytest.raises(drc.DrcError):
        drc.assert_clean(out)


def test_routing_is_deterministic_and_can_be_saved(tmp_path):
    def design():
        d = make_board("same", 16.0, 12.0)
        for i in range(5):
            tp(d, "L%d" % i, -5.0, 4.0 - 2.0 * i)
            tp(d, "R%d" % i, 5.0, -4.0 + 2.0 * i)          # every net crosses the others
            d.net("N%d" % i, "L%d.1" % i, "R%d.1" % i)
        return d

    a = route(design(), RouterOptions(layers=OUTER))
    b = route(design(), RouterOptions(layers=OUTER))
    assert a.complete and a.tracks == b.tracks and a.vias == b.vias
    path = router.save_routing(str(tmp_path / "routing.json"), design(), a,
                               RouterOptions(layers=OUTER))
    back = router.load_routing(path, design(), RouterOptions(layers=OUTER))
    assert back.tracks == a.tracks and back.vias == a.vias and back.complete
    changed = design()
    tp(changed, "X1", 0.0, 5.0)
    with pytest.raises(router.RoutingError):
        router.load_routing(path, changed, RouterOptions(layers=OUTER))
    assert router.fingerprint(design()) != router.fingerprint(changed)


def test_router_refuses_bad_input():
    d = make_board("bad")
    tp(d, "A1", -4.0, 0.0)
    tp(d, "A2", 4.0, 0.0)
    d.net("A", "A1.1", "A2.1")
    with pytest.raises(router.RoutingError):
        route(d, RouterOptions(layer_directions={"F.Cu": "diagonal"}))
    d.tracks.append(Track("A", "F.Cu", -4.0, 0.0, 4.0, 0.0, 0.15))
    with pytest.raises(router.RoutingError):
        route(d)


def test_preferred_directions_per_layer():
    d = make_board("hv", 16.0, 12.0)
    tp(d, "A1", -5.0, -3.0)
    tp(d, "A2", 5.0, 3.0, side=BOTTOM)
    d.net("A", "A1.1", "A2.1")
    res = route(d, RouterOptions(layers=OUTER, layer_directions={"F.Cu": "h", "B.Cu": "v"},
                                 direction_bias=1.0))
    assert res.complete

    def spans(layer):
        dx = sum(abs(t.x2 - t.x1) for t in res.tracks if t.layer == layer)
        dy = sum(abs(t.y2 - t.y1) for t in res.tracks if t.layer == layer)
        return dx, dy

    top, bottom = spans("F.Cu"), spans("B.Cu")
    assert top[0] > 3.0 * top[1] and bottom[1] > 3.0 * bottom[0]


# --------------------------------------------------------------------------
# planes that share their layer with tracks
# --------------------------------------------------------------------------

def _split_plane_design():
    """In2.Cu is the V plane and a routing layer; net S is forced onto In2
    and runs from the top edge to the bottom edge between two header pins,
    which cuts the plane in two."""
    d = Design("mixed", Outline(RoundedPolygon.rect(0.0, 0.0, 12.0, 7.4)), layers=4,
               rules=US_4L_STD)
    d.add(Part("J1", "HDR", HEADER3, pins={"1": "1", "2": "2", "3": "3"}, x=0.0, y=2.54,
               in_bom=False, height_mm=8.5))
    tp(d, "V1", -4.0, 0.0)
    tp(d, "V2", 4.0, 0.0)
    d.net("S", "J1.1", "J1.3", layers=("In2.Cu",))
    d.net("V", "V1.1", "V2.1")
    d.no_connect("J1.2")
    d.add_plane("V", "In2.Cu", routable=True)
    return d


def test_plane_regions_predict_a_cut_plane():
    d = _split_plane_design()
    assert d.signal_layers() == ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")
    assert d.routable_plane_layers() == {"In2.Cu": "V"}
    whole = plane_regions(d, "In2.Cu", "V", [], [])
    assert len(whole) == 1                                   # three pin holes, one piece
    cut = [Track("S", "In2.Cu", 0.0, 2.54, 0.0, -2.54, 0.15)]
    pieces = plane_regions(d, "In2.Cu", "V", cut, [])
    assert len(pieces) == 2
    assert pieces[0].contains(Point(-4.0, 0.0)) != pieces[0].contains(Point(4.0, 0.0))
    # vias on both sides: the audit sees the plane net in two parts
    vias = [Via("V", -4.0, 1.2, 0.5, 0.25), Via("V", 4.0, 1.2, 0.5, 0.25)]
    stubs = [Track("V", "F.Cu", -4.0, 0.0, -4.0, 1.2, 0.15),
             Track("V", "F.Cu", 4.0, 0.0, 4.0, 1.2, 0.15)]
    res = audit(d, cut + stubs, vias)
    assert res.plane_pieces == {"V/In2.Cu": 2}
    assert sorted(u.net for u in res.unrouted) == ["V"]
    whole = audit(d, stubs, vias)                            # without the cut it is whole
    assert whole.plane_pieces == {"V/In2.Cu": 1}
    assert [u.net for u in whole.unrouted] == ["S"]


def test_router_bridges_a_plane_cut_by_tracks(tmp_path):
    d = _split_plane_design()
    res = route(d)
    assert res.complete
    assert res.stats["plane_nets"] == {"V": "In2.Cu"}
    assert res.audit.plane_pieces == {"V/In2.Cu": 2}         # the fill is in two pieces ...
    assert res.stats["plane_repairs"] == 1                   # ... so V got a real track
    assert {t.layer for t in res.tracks if t.net == "S"} == {"In2.Cu"}
    bridge = [t for t in res.tracks if t.net == "V" and t.layer != "In2.Cu"]
    assert length(bridge) > 7.0
    kicad_judge(d, res, tmp_path)


# --------------------------------------------------------------------------
# fine-pitch array (BGA) escape
# --------------------------------------------------------------------------

def _bga_design(fine, pad_d, rules):
    """5 x 5 BGA, 0.5 mm pitch: every ball but the centre one goes to a test
    pad on a ring, the four corners are ground (plane)."""
    d = Design("bga", Outline(Circle(0.0, 0.0, 11.0)), layers=4, rules=rules)
    d.add_netclass("Fine", track_width=fine, clearance=fine)
    fp = F.bga("BGA25_test", 5, 5, pitch=0.5, pad_d=pad_d, body=(3.4, 3.4), height=1.0,
               pad_clearance=fine, courtyard_margin=0.2)
    balls = ["%s%d" % (row, col) for row in "ABCDE" for col in range(1, 6)]
    pins = {b: (b, "nc" if b == "C3" else "bidir") for b in balls}
    d.add(Part("U1", "BGA", fp, pins=pins, x=0.0, y=0.0, in_bom=False, height_mm=1.0))
    d.no_connect("U1.C3")
    signals = [b for b in balls if b not in ("A1", "A5", "E1", "E5", "C3")]
    for i, b in enumerate(signals):
        a = 2.0 * math.pi * i / len(signals)
        ref = "T%d" % (i + 1)
        tp(d, ref, round(8.5 * math.cos(a), 2), round(8.5 * math.sin(a), 2), dia=0.8)
        d.net("S_%s" % b, "U1.%s" % b, "%s.1" % ref, netclass="Fine")
    d.net("GND", "U1.A1", "U1.A5", "U1.E1", "U1.E5")
    d.add_plane("GND", "In1.Cu")
    return d


@pytest.mark.parametrize("fine,pad_d,rules", [
    (0.09, 0.23, US_4L_FINE),
    (0.10, 0.20, replace(US_4L_FINE, name="US_4L_4MIL", min_track=0.10, min_clearance=0.10)),
])
def test_bga_escape(tmp_path, fine, pad_d, rules):
    d = _bga_design(fine, pad_d, rules)
    res = route(d)
    assert res.complete, res.summary()
    # stage A fans the balls out; one that loses there is routed in the main stage
    assert res.stats["escapes"] >= 22 and res.stats["escapes"] + res.stats["escape_failed"] == 24
    assert res.connections_total == 20 + 3
    assert {t.width for t in res.tracks if t.net.startswith("S_")} == {fine}
    # no via closer than the keep-away distance to the ball field
    for v in res.vias:
        assert max(abs(v.x), abs(v.y)) >= 1.0 + pad_d / 2.0 + 0.75 + 0.25 - 1e-6
    # the inner ring really escapes between the outer balls on the top layer
    inner = [t for t in res.tracks if t.net in ("S_B2", "S_B3", "S_C2", "S_D4")
             and max(abs(t.x1), abs(t.y1), abs(t.x2), abs(t.y2)) <= 1.2]
    assert inner and {t.layer for t in inner} == {"F.Cu"}
    kicad_judge(d, res, tmp_path)


# --------------------------------------------------------------------------
# a complete small board
# --------------------------------------------------------------------------

def test_mini_board_routes_and_passes_kicad_drc(mini, tmp_path):
    files = board.build_board(mini, str(tmp_path))
    result, out = router.route_board(mini, files.pcb,
                                     json_path=os.path.join(str(tmp_path), "drc.json"))
    assert result.complete and result.routed_fraction == 1.0
    assert result.audit.violations == []
    drc.assert_clean(out)
    assert out.error_count == 0 and out.unconnected_count == 0
    data = result.to_dict()
    assert data["complete"] and data["routed_percent"] == 100.0
    assert data["stats"]["kernel"] in ("numba", "python")
    tracks, vias = board.read_routing(files.pcb)
    assert len(tracks) == len(result.tracks) and len(vias) == len(result.vias)
