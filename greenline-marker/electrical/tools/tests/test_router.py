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
    # the open net itself says why (the reasons of its units), not only the dict
    assert res.unrouted[0].reason and "no path" in res.unrouted[0].reason
    assert res.unrouted[0].to_dict()["reason"] == res.unrouted[0].reason
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
    # between the balls the tracks are fine; further out the widening pass has
    # laid them again at the standard width where it found room
    widths = {round(t.width, 3) for t in res.tracks if t.net.startswith("S_")}
    assert fine in widths and widths <= {fine, 0.15}
    assert all(round(t.width, 3) == fine for t in res.tracks if t.net.startswith("S_")
               and max(abs(t.x1), abs(t.y1), abs(t.x2), abs(t.y2)) <= 1.2)
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


# --------------------------------------------------------------------------
# internals worth pinning down
# --------------------------------------------------------------------------

def test_freeze_and_unfreeze_are_exact_inverses():
    """Frozen copper moves from the negotiable maps to the hard maps and back
    without leaving a trace (region renegotiation relies on it)."""
    d = make_board("freeze", 16.0, 12.0)
    for i in range(4):
        tp(d, "L%d" % i, -5.0, 3.0 - 2.0 * i)
        tp(d, "R%d" % i, 5.0, -3.0 + 2.0 * i, side=BOTTOM if i % 2 else "top")
        d.net("N%d" % i, "L%d.1" % i, "R%d.1" % i)
    r = router.Router(d, RouterOptions(layers=OUTER))
    result = r.run()
    assert result.complete

    def state():
        out = [r.vpref.copy()]
        for rc in r.rcs.values():
            out += [rc.soft.copy(), rc.pad.copy()]
            if rc.is_via:
                out += [rc.vhole.copy(), rc.vhard.copy()]
        return out

    before = state()
    units = [u for u in r.units if u.routed and u.items]
    assert units and any(it.is_via for u in units for it in u.items)
    for u in units:
        r._freeze(u)
    frozen = state()
    assert all(u.frozen for u in units)
    assert any((a != b).any() for a, b in zip(before, frozen))
    assert all(int(rc.soft.sum()) == 0 for rc in r.rcs.values())      # nothing negotiable left
    assert r._rip(units[0]) == []                                      # frozen copper stays
    for u in units:
        r._unfreeze(u)
    after = state()
    assert all((a == b).all() for a, b in zip(before, after))
    assert r._rip(units[0]) != []


def test_escape_window_grows_past_parts_on_its_rim():
    d = _bga_design(0.09, 0.23, US_4L_FINE)
    r = router.Router(d)
    arr = r.arrays[0]
    x0, y0, x1, y1 = r._escape_window(arr["bbox"])
    reach = 3.0 + 1.0 + 0.23 / 2.0
    assert (x0, y0, x1, y1) == pytest.approx((-reach, -reach, reach, reach))   # nothing near
    tp(d, "X1", 4.1, 0.0, dia=0.8)                          # a pad right on the rim
    d.no_connect("X1.1")
    r = router.Router(d)
    gx0, gy0, gx1, gy1 = r._escape_window(r.arrays[0]["bbox"])
    assert gx1 > 4.1 + 0.4 + 0.6 and gx1 <= x1 + 1.0 + 1e-9  # past the pad, within the limit
    assert (gx0, gy0, gy1) == pytest.approx((x0, y0, y1))


# --------------------------------------------------------------------------
# regression tests for the review findings
# --------------------------------------------------------------------------

HARWIN = "Connector_Harwin:Harwin_Gecko-G125-MVX0605L1X_2x03_P1.25mm_Vertical"


def _with_timeout(seconds, fn, *args):
    """Run ``fn`` and fail (instead of hanging the test run) if it does not
    return in time."""
    import signal

    def on_alarm(_sig, _frame):
        raise AssertionError("did not return within %d s" % seconds)

    old = signal.signal(signal.SIGALRM, on_alarm)
    signal.alarm(seconds)
    try:
        return fn(*args)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def _two_nets_router():
    d = make_board("frozen")
    tp(d, "A1", -4.0, 2.0)
    tp(d, "A2", 4.0, 2.0)
    tp(d, "B1", -4.0, -2.0)
    tp(d, "B2", 4.0, -2.0)
    d.net("A", "A1.1", "A2.1")
    d.net("B", "B1.1", "B2.1")
    r = router.Router(d, RouterOptions(layers=OUTER))
    res = r.run()
    assert res.complete
    return r


def test_unsatisfied_terminates_on_a_frozen_connection_without_copper():
    """The endless loop of the review: a connection that only counted as made
    through other copper ("trivial", no items) was frozen during a region
    renegotiation, the copper it relied on was ripped, and _unsatisfied()
    'ripped' the frozen unit for ever."""
    r = _two_nets_router()
    real = [u for u in r.units if u.kind == "conn" and u.ctx.name == "A"][0]
    ghost = r._new_unit("conn", real.ctx, list(real.pads))    # joined by the copper of `real`
    ghost.routed, ghost.trivial, ghost.frozen = True, True, True
    r.order.append(ghost)
    assert _with_timeout(20, r._unsatisfied, r.order) == []
    r._rip(real)                                               # what the ghost relied on is gone
    open_units = _with_timeout(20, r._unsatisfied, r.order)
    assert {u.uid for u in open_units} == {real.uid, ghost.uid}
    assert not ghost.routed and not ghost.frozen and not ghost.trivial
    assert r._frozen_broken == []


def test_unsatisfied_skips_a_frozen_connection_with_copper_and_reports_it():
    r = _two_nets_router()
    a = [u for u in r.units if u.kind == "conn" and u.ctx.name == "A"][0]
    # a second connection of net A that owns the copper; the first one pretends
    # to rely on it, is frozen WITH items of its own and then loses its partner
    twin = r._new_unit("conn", a.ctx, list(a.pads))
    r.order.append(twin)
    att = r._as_attempt(a)
    r._rip(a)
    r._commit(twin, att)                                       # twin now holds the track
    stub = r._make_seg(a.ctx, 0, (10, 10), (11, 10), a.ctx.hw)  # some copper for `a`
    fake = router._Attempt()
    fake.items = [stub]
    r._commit(a, fake)
    r._freeze(a)
    r._rip(twin)                                               # a's pads are no longer joined
    open_units = _with_timeout(20, r._unsatisfied, r.order)
    assert twin in open_units and a not in open_units          # a cannot be reopened while frozen
    assert r._frozen_broken == [a] and a.routed and a.frozen
    r._unfreeze(a)
    assert a in _with_timeout(20, r._unsatisfied, r.order)     # ... but is once it is unfrozen


def test_region_renegotiation_does_not_freeze_units_without_copper():
    r = _two_nets_router()
    real = [u for u in r.units if u.kind == "conn" and u.ctx.name == "A"][0]
    ghost = r._new_unit("conn", real.ctx, list(real.pads))
    ghost.routed, ghost.trivial = True, True
    r.order.append(ghost)
    other = [u for u in r.units if u.kind == "conn" and u.ctx.name == "B"][0]
    r._rip(other)                                              # an open unit to work on
    kept = _with_timeout(60, r._renegotiate_region, other, 30.0)
    assert kept and other.routed
    assert not any(u.frozen for u in r.units)
    assert _with_timeout(20, r._unsatisfied, r.order) == []
    assert router.audit(r.design, *r._emit()).ok


def test_region_renegotiation_is_skipped_for_a_walled_in_pad():
    d = make_board("caged")
    tp(d, "A1", -4.0, 0.0)
    tp(d, "A2", 4.0, 0.0)
    tp(d, "B1", -4.0, 3.0)
    tp(d, "B2", 4.0, 3.0)
    d.net("A", "A1.1", "A2.1")
    d.net("B", "B1.1", "B2.1")
    d.add_keepout(RoundedPolygon.rect(4.0, 0.0, 3.0, 3.0), name="cage")
    log = []
    res = route(d, RouterOptions(progress=log.append))
    assert not res.complete and [u.net for u in res.unrouted] == ["A"]
    text = "\n".join(log)
    assert "skipped: no path even across other nets' copper" in text
    assert "unit(s) renegotiated" not in text                  # no time wasted on it


def test_oblong_npth_holes_are_modelled_as_slots(tmp_path):
    """Library footprint with two non-plated slots, 1.0 x 1.9 mm, long axis
    along y: the hole reaches 0.45 mm further than a circle of its width."""
    rules = replace(US_4L_STD, name="EDGE025", copper_to_edge=0.25)
    d = Design("slots", Outline(RoundedPolygon.rect(0.0, 0.0, 16.0, 10.0)), rules=rules)
    pins = {str(i): (str(i), "passive") for i in range(1, 7)}
    d.add(Part("J1", "hdr", HARWIN, pins=pins, x=0.0, y=0.0, in_bom=False, height_mm=4.0))
    slots = [p for p in geometry.placed_pads(d) if p.kind == "npth"]
    assert len(slots) == 2
    s = [p for p in slots if p.x > 0][0]
    assert s.drill == pytest.approx(1.0) and s.slot == pytest.approx((3.75, 0.175, 3.75, 1.075))
    assert s.ring is not None and s.ring.bounds == pytest.approx((3.2, -0.375, 4.3, 1.625),
                                                                 abs=6e-3)
    # two pads whose shortest grid route runs along y = 1.6, straight across the
    # upper end of that slot (which a circle of the slot's width would not reach)
    tp(d, "A0", 5.5, 1.6, dia=0.5)
    tp(d, "B0", 2.9, 2.15, dia=0.5)
    d.net("W0", "A0.1", "B0.1", layers=("F.Cu",))
    for i in range(1, 7):
        d.no_connect("J1.%d" % i)
    res = route(d)
    assert res.complete
    hole = LineString([s.slot[:2], s.slot[2:]])
    for t in res.tracks:
        gap = LineString([(t.x1, t.y1), (t.x2, t.y2)]).distance(hole) - 0.5 - t.width / 2.0
        assert gap >= 0.25 - 1e-9
    kicad_judge(d, res, tmp_path)
    # the audit sees a track that runs through the slot end
    bad = [Track("W0", "F.Cu", 5.5, 1.6, 3.4, 1.6, 0.15),
           Track("W0", "F.Cu", 3.4, 1.6, 2.9, 2.15, 0.15)]
    round_hole = LineString([(5.5, 1.6), (3.4, 1.6)]).distance(Point(3.75, 0.625)) - 0.5 - 0.075
    assert round_hole > 0.3                                    # a round hole would be far away
    kinds = {v["type"] for v in audit(d, bad, []).violations}
    assert kinds == {"hole_clearance"}
    files = board.build_board(d, str(tmp_path / "bad"))
    board.apply_routing(files.pcb, bad, [])
    assert drc.run_drc(files.pcb).errors_by_type.get("hole_clearance")


def _island_design():
    d = make_board("island", 24.0, 14.0)
    island = RoundedPolygon.rect(5.0, 0.0, 9.0, 9.0)
    for i, (x, y) in enumerate(((-9.0, 4.0), (-9.0, -4.0), (4.0, 1.5), (6.0, -1.5))):
        tp(d, "A%d" % i, x, y, dia=0.8)
    d.net("+3V0", *["A%d.1" % i for i in range(4)], netclass="Power")
    for i, (x, y) in enumerate(((3.0, -3.0), (7.5, 3.0), (-4.0, 0.0))):
        tp(d, "B%d" % i, x, y, dia=0.8)
    d.net("+1V8", *["B%d.1" % i for i in range(3)], netclass="Power")
    d.add_plane("+3V0", "In2.Cu")
    d.add_plane("+1V8", "In2.Cu", shape=island, priority=1)
    return d, island


def test_island_of_another_net_cuts_the_plane(tmp_path):
    """Split power plane: +3V0 on all of In2.Cu with a +1V8 island of higher
    priority in it.  Vias of +3V0 must not be dropped into the island."""
    d, island = _island_design()
    poly = geometry.shape_polygon(island)
    area = router.plane_static_area(d, "In2.Cu", "+3V0")
    assert not area.intersects(poly) and area.distance(poly) >= 0.2
    assert router.plane_static_area(d, "In2.Cu", "+1V8").within(poly)
    res = route(d)
    assert res.complete
    for v in res.vias:
        if v.net == "+3V0":
            assert Point(v.x, v.y).distance(poly) >= 0.3      # its centre is in the +3V0 fill
    out = kicad_judge(d, res, tmp_path)
    assert out.unconnected_count == 0
    # what the old router did: a via straight under a pad that sits over the island
    bad_vias = [Via("+3V0", 4.75, 1.5, 0.5, 0.25)]
    bad_tracks = [Track("+3V0", "F.Cu", 4.0, 1.5, 4.75, 1.5, 0.3)]
    a = audit(d, bad_tracks, bad_vias)
    assert "+3V0" in [u.net for u in a.unrouted]
    regions = plane_regions(d, "In2.Cu", "+3V0", bad_tracks, bad_vias)
    assert all(not g.contains(Point(4.75, 1.5)) for g in regions)


def test_no_fanout_via_into_a_void_of_the_plane(tmp_path):
    """A GND pad in the middle of a copper keep-out of the plane layer: its
    via must land where the plane is, not in the void (where it would join
    nothing and only look connected)."""
    d = make_board("void", 20.0, 12.0)
    void = RoundedPolygon.rect(0.0, 0.0, 8.0, 8.0)
    d.add_keepout(void, layers=("In1.Cu",), tracks=False, vias=False, copper=True,
                  name="plane_void")
    for i, (x, y) in enumerate(((-8.0, 3.0), (0.0, 0.0), (1.5, -1.5), (8.0, -3.0))):
        tp(d, "G%d" % i, x, y, side="top" if i % 2 == 0 else BOTTOM, dia=0.8)
    d.net("GND", *["G%d.1" % i for i in range(4)])
    d.add_plane("GND", "In1.Cu")
    res = route(d)
    assert res.complete
    poly = geometry.shape_polygon(void)
    assert res.vias and all(not poly.contains(Point(v.x, v.y)) for v in res.vias)
    out = kicad_judge(d, res, tmp_path)
    assert "via_dangling" not in out.warnings_by_type


def test_emit_drops_duplicate_stubs_and_narrow_copper_on_wider_tracks():
    d = make_board("dups")
    tp(d, "A1", -4.02, 0.03)                                   # off the grid: stubs to the centre
    tp(d, "A2", 4.02, 0.03)
    d.net("A", "A1.1", "A2.1")
    r = router.Router(d, RouterOptions(layers=OUTER))
    assert r.run().complete
    unit = [u for u in r.units if u.kind == "conn"][0]
    before_t, _ = r._emit()
    stubs = [it for it in unit.items if not it.is_via and it.b is None]
    segs = [it for it in unit.items if not it.is_via and it.b is not None]
    assert stubs and segs
    # a second unit lays the same stub again and a narrower track on top of the first
    twin = r._new_unit("conn", unit.ctx, list(unit.pads))
    att = router._Attempt()
    att.items = [r._make_stub(unit.ctx, s.layer, s.a, s.x2, s.y2, s.hw) for s in stubs]
    att.items += [r._make_seg(unit.ctx, s.layer, s.a, s.b, s.hw / 2.0) for s in segs]
    r._commit(twin, att)
    tracks, _vias = r._emit()
    keys = [(t.layer, round(t.x1, 6), round(t.y1, 6), round(t.x2, 6), round(t.y2, 6))
            for t in tracks]
    assert len(keys) == len(set(keys))                         # no exact duplicates
    assert {t.width for t in tracks} == {t.width for t in before_t}   # the narrow copy is gone
    assert sorted(keys) == sorted((t.layer, round(t.x1, 6), round(t.y1, 6), round(t.x2, 6),
                                   round(t.y2, 6)) for t in before_t)


def _staircase_router(with_neighbour):
    """Net A: 2 mm straight, a staircase of five one-step pairs, straight on.
    ``with_neighbour``: a stub of net B ends at a point that keeps the
    clearance to every node of the staircase - but not to the diagonal
    between two of them (the 1 um case the exact check is there for)."""
    d = make_board("stairs", 10.0, 8.0)
    tp(d, "A1", -3.0, -1.0, dia=0.4)
    tp(d, "A2", 0.0, -0.75, dia=0.4)
    d.net("A", "A1.1", "A2.1")
    tp(d, "B1", -3.0, 2.5, dia=0.4)
    tp(d, "B2", 3.0, 2.5, dia=0.4)
    d.net("B", "B1.1", "B2.1")
    r = router.Router(d, RouterOptions(layers=OUTER))
    r._setup_units()
    g = r.grid
    a = [u for u in r.order if u.ctx.name == "A"][0]
    b = [u for u in r.order if u.ctx.name == "B"][0]
    n0 = g.nearest(-3.0, -1.0)
    nodes = [n0, (n0[0] + 40, n0[1])]
    x, y = nodes[-1]
    for _ in range(5):
        x += 1
        nodes.append((x, y))
        y += 1
        nodes.append((x, y))
    nodes.append((x + 15, y))
    assert g.xy(*nodes[-1]) == (0.0, -0.75)
    att = router._Attempt()
    att.items = [r._make_seg(a.ctx, 0, p, q, a.ctx.hw) for p, q in zip(nodes, nodes[1:])]
    r._commit(a, att)
    if with_neighbour:
        sx, sy = nodes[1]
        mx, my = g.xy(sx + 2, sy + 2)
        mx, my = mx + 0.025, my + 0.025                    # middle of the third diagonal
        need = 0.127 + 0.075 + 0.075                       # clearance + two half widths
        dist = need - 0.0015                               # the nodes are 0.8 um further away
        px, py = mx - dist / math.sqrt(2.0), my + dist / math.sqrt(2.0)
        assert math.hypot(px - g.xy(sx + 2, sy + 2)[0], py - g.xy(sx + 2, sy + 2)[1]) > need
        att = router._Attempt()
        att.items = [r._make_stub(b.ctx, 0, (sx - 8, sy + 14), px, py, b.ctx.hw)]
        r._commit(b, att)
    return r, nodes


def test_staircase_becomes_a_diagonal_only_where_the_exact_check_allows_it():
    r, nodes = _staircase_router(with_neighbour=False)
    plain, _ = r._emit(straighten=False)
    tracks, _ = r._emit(straighten=True)
    a_plain = [t for t in plain if t.net == "A"]
    a = [t for t in tracks if t.net == "A"]
    assert len(a_plain) == 11 and len(a) == 3                  # straight, one diagonal, straight
    diag = [t for t in a if abs(t.x2 - t.x1) > 1e-9 and abs(t.y2 - t.y1) > 1e-9]
    assert len(diag) == 1 and diag[0].length == pytest.approx(5 * 0.05 * math.sqrt(2.0))
    assert r.stats["corners_cut"] == 5
    assert audit(r.design, tracks, []).violations == []
    # a diagonal that would come 1.5 um too close to other copper is not taken:
    # the step next to it is cut on its other side instead
    r, nodes = _staircase_router(with_neighbour=True)
    plain, _ = r._emit(straighten=False)
    assert audit(r.design, plain, []).violations == []
    tracks, _ = r._emit(straighten=True)
    assert audit(r.design, tracks, []).violations == []
    a = [t for t in tracks if t.net == "A"]
    assert len(a) == 5                                         # diagonal, one step, diagonal
    sx, sy = nodes[1]
    p, q = r.grid.xy(sx + 2, sy + 2), r.grid.xy(sx + 3, sy + 3)
    line = LineString([p, q])
    assert all(LineString([(t.x1, t.y1), (t.x2, t.y2)]).intersection(line).length < 1e-9
               for t in a)
    # forcing it is exactly what the audit (and KiCad) would reject
    forced = list(tracks) + [Track("A", "F.Cu", p[0], p[1], q[0], q[1], 0.15)]
    assert [v["type"] for v in audit(r.design, forced, []).violations] == ["clearance"]


def test_via_keeps_a_wider_gap_to_its_pad_where_it_is_not_tented(tmp_path):
    def gap(tenting):
        d = make_board("gap_%s" % tenting, 8.0, 6.0)
        d.add(Part("C1", "100n", "Capacitor_SMD:C_0402_1005Metric", x=0.0, y=0.0,
                   in_bom=False, height_mm=0.5))
        tp(d, "T1", -3.0, 0.0)
        d.net("GND", "C1.2", netclass="Power")
        d.net("SIG", "C1.1", "T1.1")
        tp(d, "G1", 3.0, 2.0)
        d.net("GND", "G1.1")
        d.add_plane("GND", "In1.Cu")
        d.via_tenting = tenting
        res = route(d)
        assert res.complete
        pad = [p for p in geometry.placed_pads(d) if p.key == "C1.2"][0]
        via = min((v for v in res.vias if v.net == "GND"),
                  key=lambda v: math.hypot(v.x - pad.x, v.y - pad.y))
        return d, res, pad.polygon.distance(Point(via.x, via.y)) - via.diameter / 2.0, via

    d, res, g_open, via = gap("bottom")                       # top side open: C1 is on top
    assert g_open >= US_4L_STD.via_pad_gap_open - 1e-6
    kicad_judge(d, res, tmp_path)
    d2, res2, g_tented, via2 = gap("both")
    assert US_4L_STD.via_pad_gap_tented - 1e-6 <= g_tented < US_4L_STD.via_pad_gap_open
    # the copper that is fine with tented vias is flagged where they are open
    assert audit(d2, res2.tracks, res2.vias).violations == []
    d2.via_tenting = "bottom"
    kinds = [v["type"] for v in audit(d2, res2.tracks, res2.vias).violations]
    assert kinds and set(kinds) == {"via_pad_gap"}
    # RouterOptions.via_pad_gap overrides the rule set
    d3 = make_board("gap_opt", 8.0, 6.0)
    d3.add(Part("C1", "100n", "Capacitor_SMD:C_0402_1005Metric", x=0.0, y=0.0,
                in_bom=False, height_mm=0.5))
    tp(d3, "G1", 3.0, 2.0)
    d3.net("GND", "C1.2", "G1.1")
    d3.no_connect("C1.1")
    d3.add_plane("GND", "In1.Cu")
    res3 = route(d3, RouterOptions(via_pad_gap=0.4))
    pad = [p for p in geometry.placed_pads(d3) if p.key == "C1.2"][0]
    assert min(pad.polygon.distance(Point(v.x, v.y)) - v.diameter / 2.0
               for v in res3.vias) >= 0.4 - 1e-6


def _fine_board(confine=True):
    d = Design("fine_area", Outline(RoundedPolygon.rect(0.0, 0.0, 24.0, 14.0)), layers=4,
               rules=US_4L_FINE)
    d.add_netclass("Fine", track_width=0.09, clearance=0.09)
    fp = F.bga("FBGA16", 4, 4, pitch=0.5, pad_d=0.23, pad_clearance=0.09, height=1.0)
    balls = ["%s%d" % (row, col) for row in "ABCD" for col in range(1, 5)]
    d.add(Part("U1", "bga", fp, pins={b: (b, "bidir") for b in balls}, x=-6.0, y=0.0,
               in_bom=False, height_mm=1.0))
    used = ["A2", "A4", "B2", "B3", "C2", "C3", "D1", "D3"]     # two rings deep
    for i, b in enumerate(used):
        tp(d, "T%d" % i, 2.0 + 2.5 * (i % 4), -3.0 + 6.0 * (i // 4), dia=0.6)
        d.net("N%d" % i, "U1.%s" % b, "T%d.1" % i, netclass="Fine")
    d.no_connect(*["U1.%s" % b for b in balls if b not in used])
    if confine:
        d.add_fine_area("U1", margin=4.0)
    return d


def test_fine_classes_are_confined_to_the_fine_areas(tmp_path):
    d = _fine_board()
    assert d.is_confined("N0") and d.outside_values("N0") == (0.15, 0.127)
    assert d.clearance("N0", "N1") == 0.09
    assert d.clearance("N0", "N1", outside_a=True) == 0.127
    assert d.min_track_width("N0") == 0.09 and d.min_track_width("N0", outside=True) == 0.15
    res = route(d)
    assert res.complete, res.unrouted
    region = geometry.fine_region(d)
    narrow = [t for t in res.tracks if t.width < 0.15 - 1e-9]
    wide = [t for t in res.tracks if t.width >= 0.15 - 1e-9]
    assert narrow and wide
    for t in narrow:                                           # every fine piece touches the area
        assert region.intersects(LineString([(t.x1, t.y1), (t.x2, t.y2)]))
    area = geometry.fine_area_polygon(d.fine_areas[0])
    far = max(max(Point(t.x1, t.y1).distance(area), Point(t.x2, t.y2).distance(area))
              for t in narrow)
    assert far <= 0.071 + 1e-6                                 # at most one grid step outside
    assert max(max(t.x1, t.x2) for t in wide) > 6.0            # the long runs are 0.15 mm
    out = kicad_judge(d, res, tmp_path)
    assert "gleda fine class Fine outside the fine areas" in out.custom_rules
    # a fine track outside the area: the audit and KiCad both object
    t0 = [t for t in wide if t.length > 1.0 and
          area.distance(LineString([(t.x1, t.y1), (t.x2, t.y2)])) > 0.5][0]
    bad = [Track(t.net, t.layer, t.x1, t.y1, t.x2, t.y2, 0.09) if t is t0 else t
           for t in res.tracks]
    viol = audit(d, bad, res.vias).violations
    assert [v["type"] for v in viol] == ["track_width"] and "outside" in viol[0]["detail"]
    files = board.build_board(d, str(tmp_path / "bad"))
    board.apply_routing(files.pcb, bad, res.vias)
    assert drc.run_drc(files.pcb).errors_by_type == {"track_width": 1}


def test_without_fine_areas_fine_nets_are_widened_where_there_is_room(tmp_path):
    """No fine area declared: the fine class may be fine anywhere on its net.
    Once the board is complete the router lays such nets again - fine within
    ``widen_reach`` of the array, standard width beyond - and keeps what
    works (best effort, nothing is enforced)."""
    d = _fine_board(confine=False)
    assert not d.is_confined("N0") and d.min_track_width("N0", outside=True) == 0.09
    plain = route(d, RouterOptions(widen=False))
    assert plain.complete
    assert {round(t.width, 3) for t in plain.tracks} == {0.09}       # the old behaviour
    res = route(d)
    assert res.complete
    fine = [t for t in res.tracks if t.width < 0.15 - 1e-9]
    total = sum(t.length for t in res.tracks)
    assert {round(t.width, 3) for t in res.tracks} == {0.09, 0.15}
    assert res.stats["widened_nets"] == 8
    assert sum(t.length for t in fine) < 0.55 * total
    # what stays fine lies within 5 mm of the ball field (centre -6, 0; field +- 0.865)
    for t in fine:
        assert max(abs(t.x1 + 6.0), abs(t.x2 + 6.0)) <= 5.865 + 1e-6
        assert max(abs(t.y1), abs(t.y2)) <= 5.865 + 1e-6
    # the audit and KiCad have nothing against it (the class allows 0.09 anywhere)
    kicad_judge(d, res, tmp_path)
    # without stand-in areas a connection is widened as a whole or not at all:
    # fewer nets make it (those in the middle of the fine-pitch bundle cannot)
    whole = route(d, RouterOptions(widen_reach=0.0))
    assert whole.complete and 0 < whole.stats["widened_nets"] < 8


def test_net_quality_reports_detours_and_vias():
    d = make_board("quality", 30.0, 20.0)
    tp(d, "A1", -5.0, 0.0)
    tp(d, "A2", 5.0, 0.0)
    tp(d, "B1", -5.0, 4.0)
    tp(d, "B2", 5.0, 4.0)
    d.net("A", "A1.1", "A2.1")
    d.net("B", "B1.1", "B2.1")
    tracks = [Track("A", "F.Cu", -5.0, 0.0, 5.0, 0.0, 0.15),
              # B goes a long way round: 4 + 8 + 10 + 8 + ... mm
              Track("B", "F.Cu", -5.0, 4.0, -5.0, 9.0, 0.15),
              Track("B", "F.Cu", -5.0, 9.0, 12.0, 9.0, 0.15),
              Track("B", "F.Cu", 12.0, 9.0, 12.0, 4.0, 0.15),
              Track("B", "F.Cu", 12.0, 4.0, 5.0, 4.0, 0.15)]
    vias = [Via("A", x, 0.0, 0.5, 0.25) for x in (-3.0, -1.0, 0.0, 1.0, 3.0)]
    q = router.net_quality(d, tracks, vias)
    assert q["nets"]["A"] == {"pads": 2, "length_mm": 10.0, "tree_mm": 10.0, "ratio": 1.0,
                              "vias": 5, "sides": ["top"]}
    assert q["nets"]["B"]["ratio"] == 3.4 and q["worst"][0]["net"] == "B"
    assert q["signal_length_mm"] == 44.0 and q["signal_tree_mm"] == 20.0
    assert len(q["warnings"]) == 2
    assert any(w.startswith("B: 34.0 mm of track for a 10.0 mm spanning tree") for w in q["warnings"])
    assert any(w.startswith("A: 5 vias although its 2 pads are all on the top side")
               for w in q["warnings"])
    res = route(d)
    assert res.quality["nets"]["A"]["ratio"] == 1.0 and res.warnings == []
    assert res.to_dict()["stats"]["quality"]["signal_ratio"] == 1.0


def test_whole_net_improvement_removes_a_needless_detour():
    d = make_board("detour", 16.0, 10.0)
    tp(d, "A1", -5.0, 0.0)
    tp(d, "A2", 0.0, 0.0)
    tp(d, "A3", 5.0, 0.0)
    d.net("A", "A1.1", "A2.1", "A3.1")
    r = router.Router(d, RouterOptions(layers=OUTER, improve_nets=0))
    assert r.run().complete
    conns = sorted((u for u in r.units if u.kind == "conn"), key=lambda u: u.uid)
    first = conns[0]
    # replace the first connection by a long way round; the second one hangs on it
    g = r.grid
    a, b = first.pads
    na, nb = g.nearest(a.x, a.y), g.nearest(b.x, b.y)
    for u in conns:
        r._rip(u)
    up = 60
    att = router._Attempt()
    att.items = [r._make_seg(first.ctx, 0, na, (na[0], na[1] + up), first.ctx.hw),
                 r._make_seg(first.ctx, 0, (na[0], na[1] + up), (nb[0], nb[1] + up),
                             first.ctx.hw),
                 r._make_seg(first.ctx, 0, (nb[0], nb[1] + up), nb, first.ctx.hw)]
    att.touch = {a.idx, b.idx}
    att.cells = [(0,) + n for it in att.items for n in r._seg_nodes(it)]
    r._commit(first, att)
    for u in conns[1:]:
        r._commit(u, r._route_unit(u, soft=False))
    before = sum(t.length for t in r._emit()[0])
    done, saved, _vias = r._improve_nets(1.3)
    after = sum(t.length for t in r._emit()[0])
    assert done == 1 and saved > 5.0 and after < before - 5.0
    assert audit(d, *r._emit()).ok


def _bga_next_to_a_hole():
    d = Design("exits", Outline(RoundedPolygon.rect(0.0, 0.0, 26.0, 16.0)), layers=4,
               rules=US_4L_FINE)
    d.add_netclass("Fine", track_width=0.09, clearance=0.09)
    fp = F.bga("ExitBGA9", 3, 3, pitch=0.5, pad_d=0.23, pad_clearance=0.09, height=1.0)
    balls = ["%s%d" % (r, c) for r in "ABC" for c in (1, 2, 3)]
    d.add(Part("U1", "bga", fp, pins={b: (b, "bidir") for b in balls}, x=0.0, y=0.0,
               in_bom=False, height_mm=1.0))
    for i, b in enumerate(("A3", "B3", "C3", "B2")):
        tp(d, "T%d" % i, 10.0, 4.5 - 3.0 * i, dia=0.6)        # all of them to the right
        d.net("N%d" % i, "U1.%s" % b, "T%d.1" % i, netclass="Fine")
    d.no_connect(*["U1.%s" % b for b in balls if b not in ("A3", "B3", "C3", "B2")])
    # a locating hole right behind the right-hand rim of the escape window
    # (ball field +- 0.615, window = +- 3.615): its exclusion zone touches the rim
    d.outline.add_hole(4.6, 0.0, 1.2)
    return d


def test_an_escape_does_not_end_in_front_of_a_hole(tmp_path):
    """Stage A used to end escapes on any rim cell - also one with a hole's
    exclusion zone right behind it.  Frozen there, the connection that had to
    go on from it had no path at all (found on the demo board)."""
    d = _bga_next_to_a_hole()
    r = router.Router(d)
    r._escape_arrays()
    g = r.grid
    escapes = [u for u in r.units if u.kind == "escape"]
    assert len(escapes) == 4 and all(u.routed and u.frozen and u.at_rim for u in escapes)
    for u in escapes:
        end = u.cells[-1]
        x, y = g.xy(end[1], end[2])
        # not in the dead end between the rim and the hole (whose exclusion zone
        # begins less than 0.4 mm behind the rim for |y| <= 0.7)
        assert not (x > 3.5 and abs(y) <= 0.7 + 1e-9), (u.name, x, y)
        assert tuple(end) in u.rimset and len(u.rimset) < len(u.rim)
    # with the exit test off the nearest rim cell is taken, hole or not
    r0 = router.Router(d, RouterOptions(escape_exit=0.0))
    r0._escape_arrays()
    ends = [g.xy(u.cells[-1][1], u.cells[-1][2]) for u in r0.units if u.kind == "escape"]
    assert any(x > 3.5 and abs(y) <= 0.7 + 1e-9 for x, y in ends)
    res = route(d)
    assert res.complete, res.failures
    kicad_judge(d, res, tmp_path)


def test_frozen_fanout_is_thawed_once_for_units_without_any_path():
    d = _bga_next_to_a_hole()
    r = router.Router(d)
    r._escape_arrays()
    r._setup_units()
    frozen = [u for u in r.units if u.frozen]
    assert frozen
    open_units = [u for u in r.order if not u.routed]
    assert r._thaw_arrays(open_units) is True
    assert not any(u.frozen for u in r.units) and r.stats["thawed"] == len(frozen)
    assert all(u.routed for u in frozen)                       # the copper stays, negotiable
    assert r._thaw_arrays(open_units) is False                 # only once
    assert any("made negotiable again" in line for line in r.log_lines)


def test_an_escape_starts_at_its_own_pad():
    """Found on the demo board: the escape of pad P started on copper that
    another unit had laid from pad Q to P - at Q.  It claimed P without
    touching it; when the Q-P copper was rerouted, P was left with no copper
    at all while the router still counted it as connected."""
    d = _bga_next_to_a_hole()
    tp(d, "P", -1.5, 2.6, dia=0.5)
    tp(d, "Q", -2.6, 2.6, dia=0.5)                             # closer to the left rim
    tp(d, "T", -10.0, 2.6, dia=0.6)
    d.net("N", "P.1", "Q.1", "T.1")
    r = router.Router(d)
    r._escape_arrays()
    esc = {u.pads[0].key: u for u in r.units if u.kind == "escape" and u.ctx.name == "N"}
    assert set(esc) == {"P.1", "Q.1"}
    for u in esc.values():
        r._unfreeze(u)
    for u in esc.values():
        if u.routed:
            r._rip(u)
    # Q's unit: a track from Q to P (it touches both pads, it is not on the rim)
    g = r.grid
    q, p = esc["Q.1"].pads[0], esc["P.1"].pads[0]
    nq, np_ = g.nearest(q.x, q.y), g.nearest(p.x, p.y)
    att = router._Attempt()
    att.items = [r._make_seg(esc["Q.1"].ctx, 0, nq, np_, esc["Q.1"].ctx.hw)]
    att.cells = [(0,) + n for n in r._seg_nodes(att.items[0])]
    att.touch = {q.idx, p.idx}
    r._commit(esc["Q.1"], att)
    out = r._route_escape(esc["P.1"], soft=False)
    assert out is not None and not out.trivial and out.at_rim
    first = out.cells[0]
    assert (first[1], first[2]) in p.nodeset and (first[1], first[2]) not in q.nodeset
    # and in a complete run every escape that holds copper starts inside its pad
    r2 = router.Router(d)
    assert r2.run().complete
    for u in r2.units:
        if u.kind == "escape" and u.items:
            assert (u.cells[0][1], u.cells[0][2]) in u.pads[0].nodeset, u.name
