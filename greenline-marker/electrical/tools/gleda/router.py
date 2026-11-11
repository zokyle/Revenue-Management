"""gleda autorouter: grid-based A* with rip-up-and-reroute, for the kind of
board gleda targets (small, 4 layers, two routing layers plus planes,
fine-pitch parts, a few hundred connections).

Typical use::

    from gleda import router, board, drc
    result = router.route(design)                       # RouteResult
    print(result.summary())
    board.apply_routing(files.pcb, result.tracks, result.vias)
    drc.assert_clean(drc.run_drc(files.pcb))            # KiCad is the judge

or everything in one call: :func:`route_board`.

How it works
------------
*Grid.*  Tracks run between the nodes of a uniform grid (default 0.05 mm) in
8 directions, vias sit on nodes (:mod:`gleda.raster`).  Routing layers are
``Design.signal_layers()`` - copper layers that are not given to a whole-board
plane.

*Obstacle maps.*  For every "route class" - (track half-width, class
clearance) and (via radius, drill, class clearance) of the nets to route -
the router keeps count maps of all obstacles grown by the clearance KiCad
will ask for (:meth:`gleda.model.Design.clearance`: the larger class
clearance of the two nets, or a pad's local override) plus the mover's
half-width: pads of every net on both outer layers, routed tracks and vias,
keep-outs, board edge and cutouts, drilled holes (hole-to-copper and
hole-to-hole).  A net's own copper is subtracted while that net is routed.
Distances are exact; see :mod:`gleda.raster` for the clearance maths.

*Search.*  A* over (layer, y, x) with integer costs (:mod:`gleda._astar`),
no corner cutting, optional preferred direction per layer, a cost per via and
an optional limit of vias per net.  Multi-pin nets grow as a tree: pins are
added in minimum-spanning-tree order and each new pin is connected to the
nearest copper of the tree (pad, track or via), not just to another pin.

*Planes.*  A net with a whole-board plane on an inner layer is not routed
pin to pin: every SMD pad gets a short stub and a through via that drops into
the plane (never a via in the pad; a pad may share the via of a neighbouring
pad of the same net).

*Rip-up and reroute.*  Units (a tree net, or one plane fan-out) are routed in
order - fine-pitch classes first, then fan-outs, then the rest shortest first.
When a unit finds no legal path it is routed again with other nets' tracks
allowed at a price; the units it runs over are ripped up and queued again,
and the contested cells get a history cost so that later attempts avoid them.
A unit that has been ripped up often becomes more expensive to rip.

*Cleanup.*  Every net's tracks are dissolved into unit grid edges and rebuilt:
duplicates vanish, dangling stubs are pruned, loops are opened, collinear
pieces are merged and segments are split at junctions so that every
connection is end-to-end.

*Audit.*  :func:`audit` re-checks the final geometry with exact shapely
distances (clearance, edge, holes, keep-outs) and computes the connectivity
from the copper alone.  ``RouteResult.unrouted`` comes from this audit, not
from the router's book-keeping.  KiCad's DRC remains the judge.

Per-net options (set on :class:`gleda.model.Net`): ``width``, ``max_vias``,
``layers``, ``no_route``, ``priority``; clearance and default width come from
the net class.

Limits: see the README ("Router limitations").
"""
from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import numpy as np
import shapely
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

from . import _astar, geometry
from .model import Design, Track, Via
from .raster import (EPS, Grid, move_margin, point_segment_distance,
                     segment_segment_distance)

FREE_VIA = _astar.FREE_VIA
STEP = 10                     # integer cost of one orthogonal grid step
DIAG = 14                     # ... and of one diagonal step
_COST_CAP = 200000            # per cell; keeps path costs far below 2**31


# --------------------------------------------------------------------------
# options / result
# --------------------------------------------------------------------------

@dataclass
class RouterOptions:
    """Tuning knobs of the router (all lengths in mm).

    ``grid``             node pitch; 0.05 suits 0.5 mm-pitch parts
    ``grid_origin``      a point that must be a grid node
    ``layers``           routing layers (default ``design.signal_layers()``)
    ``via_cost``         price of a via, expressed as track length
    ``plane_via_cost``   price of the via of a plane fan-out (cheap, so that
                         every power pad gets its own via unless another via
                         of its net is right next to it)
    ``layer_directions`` optional preferred direction per layer, e.g.
                         ``{"F.Cu": "h", "B.Cu": "v"}`` ("h", "v" or "any")
    ``direction_bias``   extra cost (fraction) of moving against it
    ``present_cost``     negotiation: price (as track length) of one grid
                         cell inside another net's clearance zone in the first
                         iteration ...
    ``present_growth``   ... multiplied by this factor every iteration ...
    ``present_max``      ... up to this ceiling (a crossing is about ten cells
                         wide); beyond it only the history term grows
    ``history_cost``     cost added to a cell each time a route is laid over
                         another net there
    ``max_iterations``   negotiation rounds before the remaining conflicts are
                         resolved by ripping nets up (reported as unrouted
                         unless a clean path is then found)
    ``ripup_depth``      end game: a net that is still unrouted may push other
                         nets out of its way if those find a clean path again;
                         this is how many levels deep that may cascade
    ``patience``         stop negotiating when the number of conflicts has not
                         improved for this many rounds; the best state seen is
                         the one that is kept
    ``neckdown``         if a connection cannot be made at the net's width,
                         try again at ``Design.min_track_width(net)`` (only
                         narrower when the net class has ``min_track_width``)
    ``smooth``           straighten every path (fewer bends, same cost)
    ``time_limit``       seconds after which no more rip-up is started;
                         whatever is unrouted then is reported as unrouted
    ``improve_passes``   reroute-everything-once passes after completion
    ``search_margin``    window around a connection searched first
    ``edge_slack``       extra distance to the board edge and keep-outs
    ``via_pad_gap``      copper gap between a via and a pad of its own net
                         (vias are never placed in pads)
    ``array_via_keepout``  no via closer than this to the pad field of a
                         fine-pitch array (BGA / CSP): the escape tracks of
                         all its pads need the lanes around it, a via there
                         blocks several of them.  0 switches it off.
    ``array_pitch``      a part counts as fine-pitch array when it has nine or
                         more round pads at this pitch or less
    ``array_escape``     give every pad on the outer ring of such an array a
                         short fixed straight escape stub before anything else
                         is routed, so that its net claims its own lane and
                         the lanes between stay open for the inner pads
    ``array_escape_length``  length of those stubs from the pad centre
                         (default: one array pitch)
    ``array_zone``       width of the fan-out zone around such an array, beyond
                         the via-free zone.  Nets that do not belong to the
                         array pay ``array_zone_cost`` (fraction of the normal
                         step cost) extra per step there, on every layer, so
                         that through traffic leaves the room to the array's
                         own vias.  0 switches it off.
    ``via_spacing``      preferred centre distance between vias: a new via
                         closer than this to an existing one costs
                         ``via_spacing_cost`` (track length) extra.  Vias packed
                         at the legal minimum form a wall no track can cross;
                         at this spacing one track fits between two vias.
                         0 switches the preference off.
    ``history_gain``     each recorded conflict on a cell makes running over
                         another net there this much (fraction) more expensive;
                         this is what breaks "you move - no, you move" ties
    ``plane_share_radius``  a plane fan-out may use an existing via of its
                         net within this distance instead of a new one
    ``center_stubs``     end tracks on the pad centre with a short stub when
                         the pad centre is not a grid node
    ``heuristic_weight`` > 1 trades path quality for speed
    ``progress``         callable receiving log lines
    """
    grid: float = 0.05
    grid_origin: Tuple[float, float] = (0.0, 0.0)
    layers: Optional[Sequence[str]] = None
    via_cost: float = 3.0
    plane_via_cost: float = 1.0
    layer_directions: Optional[Dict[str, str]] = None
    direction_bias: float = 0.3
    present_cost: float = 0.02
    present_growth: float = 1.4
    present_max: float = 2.0
    history_cost: float = 0.02
    max_iterations: int = 60
    patience: int = 12
    ripup_depth: int = 3
    neckdown: bool = True
    smooth: bool = True
    time_limit: Optional[float] = None
    improve_passes: int = 1
    search_margin: float = 3.0
    edge_slack: float = geometry.DRC_SLACK
    via_pad_gap: float = 0.1
    array_via_keepout: float = 0.75
    array_pitch: float = 0.65
    array_escape: bool = True
    array_escape_length: Optional[float] = None
    array_zone: float = 1.5
    array_zone_cost: float = 1.0
    history_gain: float = 0.25
    via_spacing: float = 0.9
    via_spacing_cost: float = 1.5
    plane_share_radius: float = 1.2
    center_stubs: bool = True
    heuristic_weight: float = 1.2
    progress: Optional[Callable[[str], None]] = None


@dataclass
class Unrouted:
    """One missing connection: ``net`` is split into ``pieces`` groups of
    pads that are not connected to each other."""
    net: str
    pieces: List[List[str]]
    reason: str = ""

    @property
    def missing(self) -> int:
        return max(0, len(self.pieces) - 1)

    def to_dict(self) -> Dict[str, Any]:
        return {"net": self.net, "missing_connections": self.missing,
                "pieces": self.pieces, "reason": self.reason}


@dataclass
class AuditResult:
    """Exact re-check of routed geometry (see :func:`audit`)."""
    violations: List[Dict[str, Any]] = field(default_factory=list)
    unrouted: List[Unrouted] = field(default_factory=list)
    connections_total: int = 0

    @property
    def missing(self) -> int:
        return sum(u.missing for u in self.unrouted)

    @property
    def ok(self) -> bool:
        return not self.violations and not self.unrouted

    def to_dict(self) -> Dict[str, Any]:
        return {"violations": self.violations,
                "unrouted": [u.to_dict() for u in self.unrouted],
                "connections_total": self.connections_total,
                "connections_missing": self.missing}


@dataclass
class RouteResult:
    """Outcome of :func:`route`."""
    tracks: List[Track]
    vias: List[Via]
    audit: AuditResult
    stats: Dict[str, Any] = field(default_factory=dict)
    failures: Dict[str, str] = field(default_factory=dict)

    @property
    def unrouted(self) -> List[Unrouted]:
        return self.audit.unrouted

    @property
    def connections_total(self) -> int:
        return self.audit.connections_total

    @property
    def connections_routed(self) -> int:
        return self.audit.connections_total - self.audit.missing

    @property
    def routed_fraction(self) -> float:
        total = self.connections_total
        return 1.0 if total == 0 else self.connections_routed / total

    @property
    def complete(self) -> bool:
        """Every connection made and the internal audit found no violation."""
        return self.audit.ok

    def summary(self) -> str:
        s = self.stats
        return ("routed %d/%d connections (%.1f %%) of %d nets, %d tracks, %d vias, "
                "%.1f mm, %d audit violation(s), %.1f s" % (
                    self.connections_routed, self.connections_total,
                    100.0 * self.routed_fraction, s.get("nets", 0), len(self.tracks),
                    len(self.vias), s.get("track_length_mm", 0.0),
                    len(self.audit.violations), s.get("runtime_s", 0.0)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "complete": self.complete,
            "connections_total": self.connections_total,
            "connections_routed": self.connections_routed,
            "routed_percent": round(100.0 * self.routed_fraction, 3),
            "tracks": len(self.tracks), "vias": len(self.vias),
            "stats": self.stats, "failures": dict(self.failures),
            "audit": self.audit.to_dict(),
        }


class RoutingError(Exception):
    """The design cannot be routed at all (bad options, no routing layer)."""


# --------------------------------------------------------------------------
# internal data
# --------------------------------------------------------------------------

class _Pad:
    """A placed pad as terminal and as obstacle."""
    __slots__ = ("idx", "key", "net", "x", "y", "cu", "lay", "circle", "R", "poly", "geom",
                 "georad", "local_clr", "cls_clr", "drill", "smd", "exact", "nodes",
                 "nodeset", "center", "bbox")


class _Seg:
    """A routed track piece.  ``a`` / ``b`` are grid nodes (ix, iy); ``b`` is
    None for an off-grid stub that ends at (x2, y2)."""
    __slots__ = ("net", "layer", "a", "b", "x1", "y1", "x2", "y2", "hw", "cls_clr",
                 "exact", "unit", "masks", "alive")
    is_via = False

    def bbox(self):
        return (min(self.x1, self.x2) - self.hw, min(self.y1, self.y2) - self.hw,
                max(self.x1, self.x2) + self.hw, max(self.y1, self.y2) + self.hw)

    @property
    def length(self) -> float:
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)


class _ViaItem:
    """A routed through via on node ``a``."""
    __slots__ = ("net", "a", "x", "y", "R", "drill", "cls_clr", "unit", "masks", "alive")
    is_via = True

    def bbox(self):
        return (self.x - self.R, self.y - self.R, self.x + self.R, self.y + self.R)


class _RC:
    """Obstacle maps of one route class (see module docstring)."""

    def __init__(self, key, hw: float, hole_r: float, clr: float, is_via: bool,
                 layers: int, shape: Tuple[int, int]):
        self.key = key
        self.hw = hw
        self.hole_r = hole_r
        self.clr = clr
        self.is_via = is_via
        n = 1 if is_via else layers
        self.static = np.zeros((n,) + shape, dtype=bool)
        self.pad = np.zeros((n,) + shape, dtype=np.uint8)
        self.soft = np.zeros((n,) + shape, dtype=np.uint16)
        #: via classes only: hole-to-hole reach of the routed vias (all nets)
        self.vhole = np.zeros(shape, dtype=np.uint16) if is_via else None


class _NetCtx:
    __slots__ = ("name", "cls_clr", "width", "hw", "via_d", "via_drill", "rct", "rcv",
                 "rct_alt", "pads", "allowed", "max_vias", "plane", "priority")


class _Unit:
    __slots__ = ("uid", "kind", "ctx", "pads", "phase", "hpwl", "items", "rips", "weight",
                 "failed", "reason", "routed", "deps", "dependents", "attempts", "order",
                 "paths", "root", "missing")

    def __init__(self, uid, kind, ctx, pads):
        self.uid = uid
        self.kind = kind
        self.ctx = ctx
        self.pads = pads
        self.phase = 2
        self.hpwl = 0.0
        self.items: List[Any] = []
        self.rips = 0
        self.weight = 1
        self.failed = False
        self.reason = ""
        self.routed = False
        self.deps: Set[int] = set()
        self.dependents: Set[int] = set()
        self.attempts = 0
        self.order = 0
        self.paths: List[Any] = []                         # tree units: one per connection
        self.root: Optional[int] = None                    # tree units: pad the tree grew from
        self.missing: List[str] = []                       # pads a partial route left out

    @property
    def name(self) -> str:
        if self.kind == "tree":
            return self.ctx.name
        return "%s@%s" % (self.ctx.name, self.pads[0].key)


class _Path:
    """One connection of a tree net: the copper that attached pad ``pad`` to
    the tree, the pads it met on the way, and the connection it hangs on
    (``parent``: index into the unit's path list, -1 = the root pad)."""
    __slots__ = ("pad", "met", "items", "cells", "vias", "parent")


class _Attempt:
    """Result of routing one unit (not yet committed)."""

    def __init__(self):
        self.items: List[Any] = []
        self.victims: Set[int] = set()
        self.hist: List[Tuple[int, int, int]] = []
        self.deps: Set[int] = set()
        self.cells: List[Tuple[int, int, int]] = []        # tree cells (l, ix, iy)
        self.free: Set[Tuple[int, int]] = set()            # nodes with a free layer change
        self.vias: List[_ViaItem] = []
        self.stubbed: Set[Tuple[int, Tuple[int, int]]] = set()
        self.connected: Set[int] = set()                   # pad indices in the tree
        self.paths: List[_Path] = []
        self.root: Optional[int] = None
        self.missing: List[str] = []


class _Index:
    """Bucket index of the routed items for exact conflict queries."""

    def __init__(self, cell: float = 1.0):
        self.cell = cell
        self.buckets: Dict[Tuple[int, int], List[Any]] = {}

    def _keys(self, bbox):
        c = self.cell
        x0, y0 = int(math.floor(bbox[0] / c)), int(math.floor(bbox[1] / c))
        x1, y1 = int(math.floor(bbox[2] / c)), int(math.floor(bbox[3] / c))
        for bx in range(x0, x1 + 1):
            for by in range(y0, y1 + 1):
                yield (bx, by)

    def add(self, it) -> None:
        it.alive = True
        for k in self._keys(it.bbox()):
            self.buckets.setdefault(k, []).append(it)

    def remove(self, it) -> None:
        it.alive = False
        for k in self._keys(it.bbox()):
            lst = self.buckets.get(k)
            if lst is not None:
                try:
                    lst.remove(it)
                except ValueError:
                    pass

    def query(self, bbox, grow: float) -> List[Any]:
        box = (bbox[0] - grow, bbox[1] - grow, bbox[2] + grow, bbox[3] + grow)
        seen: Set[int] = set()
        out = []
        for k in self._keys(box):
            for it in self.buckets.get(k, ()):
                if id(it) not in seen:
                    seen.add(id(it))
                    out.append(it)
        return out


def _blit(dst: np.ndarray, win, item_win, mask: np.ndarray, value) -> None:
    """Add ``value`` to the cells of ``dst`` (a copy of window ``win`` of a
    map) that are set in ``mask`` (positioned at ``item_win``)."""
    iy0, iy1, ix0, ix1 = win
    jy0, jy1, jx0, jx1 = item_win
    y0, y1 = max(iy0, jy0), min(iy1, jy1)
    x0, x1 = max(ix0, jx0), min(ix1, jx1)
    if y0 >= y1 or x0 >= x1:
        return
    sub = mask[y0 - jy0:y1 - jy0, x0 - jx0:x1 - jx0]
    view = dst[y0 - iy0:y1 - iy0, x0 - ix0:x1 - ix0]
    view[sub] += value


def _collinear_runs(nodes: List[Tuple[int, int]]) -> List[Tuple[Tuple[int, int], Tuple[int, int]]]:
    """Merge a chain of adjacent grid nodes into straight (start, end) runs."""
    out = []
    if len(nodes) < 2:
        return out
    start = nodes[0]
    prev = nodes[0]
    direction = None
    for cur in nodes[1:]:
        d = (cur[0] - prev[0], cur[1] - prev[1])
        if direction is not None and d != direction:
            out.append((start, prev))
            start = prev
        direction = d
        prev = cur
    out.append((start, prev))
    return out


# --------------------------------------------------------------------------
# the router
# --------------------------------------------------------------------------

class Router:
    """One routing job.  Use :func:`route` unless you need the internals."""

    def __init__(self, design: Design, options: Optional[RouterOptions] = None):
        self.design = design
        self.opt = options or RouterOptions()
        self.rules = design.rules
        if design.tracks or design.vias:
            raise RoutingError("the design already carries tracks / vias; pre-routed copper "
                               "is not supported by the router (clear design.tracks / vias)")
        self.t0 = time.time()
        self.log_lines: List[str] = []
        names = tuple(self.opt.layers) if self.opt.layers else design.signal_layers()
        self.layers: Tuple[str, ...] = tuple(l for l in design.copper_layers if l in names)
        if not self.layers:
            raise RoutingError("no routing layer")
        self.L = len(self.layers)
        self.lidx = {name: i for i, name in enumerate(self.layers)}
        self.board_poly = geometry.outline_polygon(design.outline, self.rules.max_arc_error)
        self.grid = Grid(self.board_poly.bounds, self.opt.grid, self.opt.grid_origin)
        g = self.grid
        self.shape = g.shape
        self.floor = self.rules.min_clearance
        self.hist = np.zeros((self.L,) + self.shape, dtype=np.uint16)
        #: number of routed vias within the preferred via spacing of each node
        self.vpref = np.zeros(self.shape, dtype=np.uint16)
        self.index = _Index()
        self.net_items: Dict[str, List[Any]] = {}
        self.pad_masks: Dict[Tuple[int, Any], Any] = {}
        #: fixed copper (escape stubs): per net, and per pad it is attached to
        self.fixed: Dict[str, List[Any]] = {}
        self.pad_fixed: Dict[int, List[Any]] = {}
        self.conf: Dict[int, Set[int]] = {}
        self._forced_cells: List[Tuple[int, int, int]] = []
        self._inner: Dict[float, Any] = {}
        self.stats: Dict[str, Any] = {"searches": 0, "expansions": 0, "ripups": 0,
                                      "reroutes": 0}
        self._setup_costs()
        self._setup_pads()
        self._setup_nets()
        self._setup_maps()
        self._escape_arrays()
        self._setup_units()

    # -- logging -----------------------------------------------------------
    def log(self, msg: str) -> None:
        line = "[%6.1fs] %s" % (time.time() - self.t0, msg)
        self.log_lines.append(line)
        if self.opt.progress:
            self.opt.progress(line)

    # -- setup -------------------------------------------------------------
    def mm_cost(self, mm: float) -> int:
        return max(1, int(round(mm / self.grid.pitch * STEP)))

    def _setup_costs(self) -> None:
        o = self.opt
        self.via_cost = self.mm_cost(o.via_cost)
        self.plane_via_cost = self.mm_cost(o.plane_via_cost)
        self.vspace_cost = self.mm_cost(o.via_spacing_cost) if o.via_spacing > 0 else 0
        self.pen0 = max(1.0, o.present_cost / self.grid.pitch * STEP)
        self.pen = int(round(self.pen0))
        self.hinc = max(1, self.mm_cost(o.history_cost))
        sh, sv, sd = [], [], []
        bias = max(0.0, o.direction_bias)
        for name in self.layers:
            pref = (o.layer_directions or {}).get(name, "any")
            if pref not in ("h", "v", "any"):
                raise RoutingError("layer direction must be 'h', 'v' or 'any'")
            against = int(round(STEP * (1.0 + bias)))
            sh.append(against if pref == "v" else STEP)
            sv.append(against if pref == "h" else STEP)
            sd.append(DIAG if pref == "any" else int(round(DIAG * (1.0 + bias / 2.0))))
        self.step_h = np.array(sh, dtype=np.int32)
        self.step_v = np.array(sv, dtype=np.int32)
        self.step_d = np.array(sd, dtype=np.int32)
        w = max(1.0, o.heuristic_weight)
        self.hnum, self.hden = int(round(w * 100)), 100

    def _setup_pads(self) -> None:
        d, g = self.design, self.grid
        self.pads: List[_Pad] = []
        self.npth: List[Tuple[float, float, float]] = [
            (h.x, h.y, h.drill) for h in d.outline.holes]
        for pp in geometry.placed_pads(d):
            if pp.kind == "npth" or pp.polygon is None or not pp.layers:
                if pp.drill > 0:
                    self.npth.append((pp.x, pp.y, pp.drill))
                continue
            p = _Pad()
            p.idx = len(self.pads)
            p.key = pp.key
            p.net = pp.net if pp.net in d.nets else None
            p.x, p.y = pp.x, pp.y
            p.cu = tuple(pp.layers)
            p.lay = tuple(self.lidx[l] for l in pp.layers if l in self.lidx)
            p.circle = pp.shape == "circle" and abs(pp.w - pp.h) < 1e-9
            p.R = pp.w / 2.0 if p.circle else 0.0
            p.poly = pp.polygon
            if p.circle:
                p.geom, p.georad = Point(pp.x, pp.y), p.R
            else:
                p.geom, p.georad = pp.polygon, geometry.PAD_POLYGON_TOLERANCE
            p.local_clr = pp.clearance
            p.cls_clr = d.netclass_of(p.net).clearance
            p.drill = pp.drill if pp.kind == "th" else 0.0
            p.smd = pp.kind != "th"
            p.exact = p.circle and g.is_node(pp.x, pp.y)
            xmin, ymin, xmax, ymax = pp.polygon.bounds
            p.bbox = (xmin, ymin, xmax, ymax)
            inset = min(0.02, 0.2 * min(xmax - xmin, ymax - ymin))
            if p.circle:
                m = g.disc_mask(pp.x, pp.y, max(p.R - inset, 2 * EPS))
                if m is None:
                    p.nodes = np.zeros((0, 2), dtype=np.int64)
                else:
                    (iy0, _iy1, ix0, _ix1), mask = m
                    iy, ix = np.nonzero(mask)
                    p.nodes = np.stack([ix + ix0, iy + iy0], axis=1).astype(np.int64)
            else:
                p.nodes = g.nodes_in(pp.polygon, inset)
            p.nodeset = {(int(n[0]), int(n[1])) for n in p.nodes}
            p.center = None
            if g.is_node(pp.x, pp.y):
                c = g.nearest(pp.x, pp.y)
                if g.inside(*c) and pp.polygon.buffer(1e-9).contains(Point(pp.x, pp.y)):
                    p.center = c
            self.pads.append(p)
        self.pad_tree = STRtree([p.geom for p in self.pads]) if self.pads else None
        # fine-pitch arrays: pads and (xmin, ymin, xmax, ymax) of their pad copper
        self.arrays: List[Dict[str, Any]] = []
        by_ref: Dict[str, List[_Pad]] = {}
        for p in self.pads:
            if p.circle and p.smd:
                by_ref.setdefault(p.key.split(".", 1)[0], []).append(p)
        for ref in sorted(by_ref):
            group = by_ref[ref]
            if len(group) < 9:
                continue
            pitch = min(math.hypot(a.x - b.x, a.y - b.y)
                        for i, a in enumerate(group[:4]) for b in group if b is not a)
            if pitch <= self.opt.array_pitch + 1e-9:
                self.arrays.append({"ref": ref, "pads": group, "pitch": pitch, "bbox": (
                    min(p.x - p.R for p in group), min(p.y - p.R for p in group),
                    max(p.x + p.R for p in group), max(p.y + p.R for p in group)),
                    "nets": {p.net for p in group if p.net}})
        for arr in self.arrays:
            x0, y0, x1, y1 = arr["bbox"]
            m = self.opt.array_via_keepout + self.opt.array_zone
            arr["zone"] = g.window(x0 - m, y0 - m, x1 + m, y1 + m) \
                if self.opt.array_zone > 0 else None

    def _setup_nets(self) -> None:
        d = self.design
        planes = d.full_plane_layers()                    # layer -> net
        plane_of: Dict[str, str] = {}
        for layer, net in planes.items():
            if layer not in self.lidx:
                plane_of.setdefault(net, layer)
        self.plane_of = plane_of
        self.ctx: Dict[str, _NetCtx] = {}
        by_net: Dict[str, List[_Pad]] = {}
        for p in self.pads:
            if p.net:
                by_net.setdefault(p.net, []).append(p)
        self.rcs: Dict[Any, _RC] = {}
        for name, net in d.nets.items():
            pads = by_net.get(name, [])
            c = _NetCtx()
            c.name = name
            c.cls_clr = max(d.netclass_of(name).clearance, self.floor)
            c.width = d.track_width(name)
            c.hw = c.width / 2.0
            c.via_d, c.via_drill = d.via_size(name)
            c.pads = pads
            c.max_vias = net.max_vias
            c.priority = net.priority
            c.plane = plane_of.get(name)
            if net.layers:
                c.allowed = tuple(self.lidx[l] for l in net.layers if l in self.lidx)
            else:
                c.allowed = tuple(range(self.L))
            c.rct = c.rcv = c.rct_alt = None
            self.ctx[name] = c
        self.routable: List[_NetCtx] = []
        for name, net in d.nets.items():
            c = self.ctx[name]
            if net.no_route or len(c.pads) < 2:
                continue
            self.routable.append(c)
            c.rct = self._rc(("t", round(c.hw, 6), round(c.cls_clr, 6)), c.hw, 0.0,
                             c.cls_clr, False)
            c.rcv = self._rc(("v", round(c.via_d / 2.0, 6), round(c.via_drill / 2.0, 6),
                              round(c.cls_clr, 6)), c.via_d / 2.0, c.via_drill / 2.0,
                             c.cls_clr, True)
            if self.opt.neckdown:
                wmin = d.min_track_width(name)
                if wmin < c.width - 1e-9:
                    c.rct_alt = self._rc(("t", round(wmin / 2.0, 6), round(c.cls_clr, 6)),
                                         wmin / 2.0, 0.0, c.cls_clr, False)

    def _rc(self, key, hw, hole_r, clr, is_via) -> _RC:
        rc = self.rcs.get(key)
        if rc is None:
            rc = _RC(key, hw, hole_r, clr, is_via, self.L, self.shape)
            self.rcs[key] = rc
        return rc

    def _reach(self, rc: _RC, obst_cls: float, local: Optional[float] = None) -> float:
        """Distance the centre of a mover of class ``rc`` must keep from the
        copper edge of an obstacle (without move margin)."""
        if local:
            clr = max(local, self.floor)
        else:
            clr = max(rc.clr, obst_cls, self.floor)
        reach = clr + rc.hw
        if rc.hole_r:
            reach = max(reach, self.rules.hole_clearance + rc.hole_r)
        return reach

    def _pad_mask(self, p: _Pad, rc: _RC):
        """(window, mask) of the nodes a mover of class ``rc`` may not use
        because of pad ``p`` (cached)."""
        key = (p.idx, rc.key)
        if key in self.pad_masks:
            return self.pad_masks[key]
        g = self.grid
        reach = self._reach(rc, p.cls_clr, p.local_clr)
        if not rc.is_via and not p.exact:
            reach += move_margin(reach, g.pitch)
        if p.circle:
            m = g.disc_mask(p.x, p.y, p.R + reach)
        else:
            m = g.polygon_mask(p.poly, reach + geometry.PAD_POLYGON_TOLERANCE)
        self.pad_masks[key] = m
        return m

    def _setup_maps(self) -> None:
        d, g, r, o = self.design, self.grid, self.rules, self.opt
        for rc in self.rcs.values():
            # board edge and cutouts
            inset = r.copper_to_edge + rc.hw + o.edge_slack
            allowed = self.board_poly.buffer(-inset)
            rc.static[:] = ~g.contained_mask(allowed)[None, :, :]
            # drilled holes without copper
            for (hx, hy, drill) in self.npth:
                reach = max(r.hole_clearance, r.copper_to_edge) + rc.hw + o.edge_slack
                if rc.is_via:
                    reach = max(reach, r.hole_to_hole + rc.hole_r)
                m = g.disc_mask(hx, hy, drill / 2.0 + reach + move_margin(reach, g.pitch))
                if m:
                    win, mask = m
                    rc.static[:, win[0]:win[1], win[2]:win[3]] |= mask[None, :, :]
            # escape zone of fine-pitch arrays: no vias
            if rc.is_via and o.array_via_keepout > 0:
                for arr in self.arrays:
                    x0, y0, x1, y1 = arr["bbox"]
                    m = o.array_via_keepout + rc.hw
                    win = g.window(x0 - m, y0 - m, x1 + m, y1 + m)
                    if win:
                        rc.static[0, win[0]:win[1], win[2]:win[3]] = True
            # keep-outs
            for ko in d.keepouts:
                names = ko.layer_names(d.copper_layers)
                if rc.is_via:
                    if not ko.vias:
                        continue
                    targets = [0]
                else:
                    if not ko.tracks:
                        continue
                    targets = [self.lidx[n] for n in names if n in self.lidx]
                if not targets:
                    continue
                poly = geometry.keepout_polygon(ko).buffer(rc.hw + o.edge_slack)
                mask = g.contained_mask(poly)
                for l in targets:
                    rc.static[l] |= mask
            # pads
            for p in self.pads:
                m = self._pad_mask(p, rc)
                if m:
                    win, mask = m
                    for l in ([0] if rc.is_via else p.lay):
                        rc.pad[l, win[0]:win[1], win[2]:win[3]] += mask
                if p.drill > 0:
                    reach = r.hole_clearance + rc.hw
                    if rc.is_via:
                        reach = max(reach, r.hole_to_hole + rc.hole_r)
                    else:
                        reach += move_margin(reach, g.pitch)
                    m = g.disc_mask(p.x, p.y, p.drill / 2.0 + reach)
                    if m and rc.is_via:
                        # hole-to-hole applies to the pad's own net as well
                        win, mask = m
                        rc.static[0, win[0]:win[1], win[2]:win[3]] |= mask

    # -- fixed copper: escape stubs of fine-pitch arrays -----------------------
    def _add_fixed(self, ctx: _NetCtx, seg: _Seg, pad: _Pad) -> None:
        """Register a fixed track piece that hangs on ``pad``: a hard obstacle
        for every other net, part of the pad for its own net."""
        seg.unit = -2
        seg.masks = self._item_masks(seg)
        for rc in self.rcs.values():
            layer = 0 if rc.is_via else seg.layer
            for win, mask in seg.masks[rc.key]:
                rc.pad[layer, win[0]:win[1], win[2]:win[3]] += mask
        self.fixed.setdefault(ctx.name, []).append(seg)
        self.pad_fixed.setdefault(pad.idx, []).append(seg)

    def _legal_run(self, ctx: _NetCtx, rc: _RC, p: _Pad, layer: int, d: Tuple[int, int],
                   steps: int) -> int:
        """Number of grid moves (at most ``steps``) a track of class ``rc`` can
        make from the centre of pad ``p`` in direction ``d`` without coming too
        close to fixed copper, pads or the board edge."""
        g = self.grid
        cx, cy = p.center
        m = steps + 2
        win = (max(0, cy - m), min(g.ny, cy + m + 1), max(0, cx - m), min(g.nx, cx + m + 1))
        cost = self._local(ctx, rc, win, False, _Attempt(), None)[0]
        iy0, iy1, ix0, ix1 = win
        x, y = cx - ix0, cy - iy0
        if cost[layer, y, x] == 0:
            return 0
        n = 0
        for _k in range(steps):
            nx, ny = x + d[0], y + d[1]
            if not (0 <= nx < ix1 - ix0 and 0 <= ny < iy1 - iy0) or cost[layer, ny, nx] == 0:
                break
            if d[0] and d[1] and (cost[layer, y, nx] == 0 or cost[layer, ny, x] == 0):
                break
            x, y = nx, ny
            n += 1
        return n

    def _escape_arrays(self) -> None:
        """Fixed straight escape stubs for the outer ring of every fine-pitch
        array (see ``RouterOptions.array_escape``).  Side pads leave along the
        outward normal, corner pads along the longest legal of diagonal /
        the two normals.  A stub runs to the first place where a via is
        allowed (or as far as it legally can)."""
        o, g = self.opt, self.grid
        count = 0
        if not o.array_escape:
            self.stats["escape_stubs"] = 0
            return
        for arr in self.arrays:
            pads = arr["pads"]
            x0, x1 = min(p.x for p in pads), max(p.x for p in pads)
            y0, y1 = min(p.y for p in pads), max(p.y for p in pads)
            for p in pads:
                ctx = self.ctx.get(p.net) if p.net else None
                if ctx is None or ctx.rct is None or p.center is None or not p.lay:
                    continue
                dx = -1 if abs(p.x - x0) < 1e-6 else (1 if abs(p.x - x1) < 1e-6 else 0)
                dy = -1 if abs(p.y - y0) < 1e-6 else (1 if abs(p.y - y1) < 1e-6 else 0)
                if dx == 0 and dy == 0:
                    continue                                  # inner pad: negotiated
                dirs = [(dx, dy)] if (dx == 0 or dy == 0) else [(dx, dy), (dx, 0), (0, dy)]
                rc = ctx.rct
                if ctx.rct_alt is not None and 2.0 * p.R < ctx.width - 1e-9:
                    rc = ctx.rct_alt                          # neck down at the ball
                want = o.array_escape_length or arr["pitch"]
                best = None
                for d in dirs:
                    step = g.pitch * (math.sqrt(2.0) if d[0] and d[1] else 1.0)
                    steps = int(round(want / g.pitch))        # diagonal: same count of moves
                    n = self._legal_run(ctx, rc, p, p.lay[0], d, steps)
                    if best is None or n * step > best[0] + 1e-9:
                        best = (n * step, n, d)
                if best is None or best[1] < 3:
                    continue
                _length, n, d = best
                end = (p.center[0] + d[0] * n, p.center[1] + d[1] * n)
                seg = self._make_seg(ctx, p.lay[0], p.center, end, rc.hw)
                self._add_fixed(ctx, seg, p)
                count += 1
        self.stats["escape_stubs"] = count
        if count:
            self.log("escape: %d fixed stub(s) on %d fine-pitch array(s)" % (
                count, len(self.arrays)))

    @staticmethod
    def _seg_nodes(seg: _Seg) -> List[Tuple[int, int]]:
        """All grid nodes on an on-grid segment."""
        a, b = seg.a, seg.b
        n = max(abs(b[0] - a[0]), abs(b[1] - a[1]))
        if n == 0:
            return [a]
        sx, sy = (b[0] - a[0]) // n, (b[1] - a[1]) // n
        return [(a[0] + sx * i, a[1] + sy * i) for i in range(n + 1)]

    def _setup_units(self) -> None:
        self.units: List[_Unit] = []
        default_clr = max(self.design.netclasses["Default"].clearance, self.floor)
        for c in self.routable:
            if c.plane:
                plane_layer = c.plane
                for p in c.pads:
                    if plane_layer in p.cu:
                        continue                       # plated through: already on the plane
                    u = _Unit(len(self.units), "fanout", c, [p])
                    u.phase = 1
                    u.hpwl = 0.0
                    self.units.append(u)
            else:
                u = _Unit(len(self.units), "tree", c, list(c.pads))
                xs = [p.x for p in c.pads]
                ys = [p.y for p in c.pads]
                u.hpwl = (max(xs) - min(xs)) + (max(ys) - min(ys))
                u.phase = 0 if c.cls_clr < default_clr - 1e-9 else 2
                self.units.append(u)
        order = sorted(self.units, key=lambda u: (-u.ctx.priority, u.phase, u.hpwl, u.uid))
        for i, u in enumerate(order):
            u.order = i
        self.order = order

    # -- item maps -----------------------------------------------------------
    def _item_masks(self, it) -> Dict[Any, List[Tuple[Any, np.ndarray]]]:
        """Masks of a routed item for every route class."""
        g, r = self.grid, self.rules
        out: Dict[Any, List[Tuple[Any, np.ndarray]]] = {}
        for rc in self.rcs.values():
            masks = []
            if it.is_via:
                reach = self._reach(rc, it.cls_clr) + it.R
                reach = max(reach, it.drill / 2.0 + r.hole_clearance + rc.hw)
                m = g.disc_mask(it.x, it.y, reach)
                if m:
                    masks.append(m)
            else:
                reach = self._reach(rc, it.cls_clr)
                if not rc.is_via and not it.exact:
                    reach += move_margin(reach, g.pitch)
                rad = it.hw + reach
                for (x1, y1, x2, y2) in self._chunks(it):
                    m = g.stadium_mask(x1, y1, x2, y2, rad)
                    if m:
                        masks.append(m)
            out[rc.key] = masks
        return out

    @staticmethod
    def _chunks(seg: _Seg, limit: float = 2.0):
        """Split long diagonal segments so that their masks stay small."""
        dx, dy = seg.x2 - seg.x1, seg.y2 - seg.y1
        n = int(min(abs(dx), abs(dy)) // limit) + 1
        if n <= 1:
            return [(seg.x1, seg.y1, seg.x2, seg.y2)]
        return [(seg.x1 + dx * i / n, seg.y1 + dy * i / n,
                 seg.x1 + dx * (i + 1) / n, seg.y1 + dy * (i + 1) / n) for i in range(n)]

    def _apply(self, it, weight: int, sign: int) -> None:
        """Add (sign +1) or remove (-1) a routed item to / from all maps."""
        g, r = self.grid, self.rules
        if it.masks is None:
            it.masks = self._item_masks(it)
        for rc in self.rcs.values():
            if rc.is_via or it.is_via:
                layers = range(rc.soft.shape[0])
            else:
                layers = (it.layer,)
            for win, mask in it.masks[rc.key]:
                for l in layers:
                    view = rc.soft[l, win[0]:win[1], win[2]:win[3]]
                    if sign > 0:
                        view[mask] += weight
                    else:
                        view[mask] -= weight
            if rc.is_via and it.is_via:
                m = g.disc_mask(it.x, it.y, it.drill / 2.0 + r.hole_to_hole + rc.hole_r)
                if m:
                    win, mask = m
                    view = rc.vhole[win[0]:win[1], win[2]:win[3]]
                    if sign > 0:
                        view[mask] += weight
                    else:
                        view[mask] -= weight
        if it.is_via and self.opt.via_spacing > 0:
            m = g.disc_mask(it.x, it.y, self.opt.via_spacing)
            if m:
                win, mask = m
                view = self.vpref[win[0]:win[1], win[2]:win[3]]
                if sign > 0:
                    view[mask] += 1
                else:
                    view[mask] -= 1

    def _commit(self, unit: _Unit, att: _Attempt) -> None:
        unit.items = list(att.items)
        unit.paths = list(att.paths)
        unit.root = att.root
        unit.missing = list(att.missing)
        unit.weight = 1
        unit.deps = set(att.deps)
        for dep in unit.deps:
            self.units[dep].dependents.add(unit.uid)
        lst = self.net_items.setdefault(unit.ctx.name, [])
        for it in unit.items:
            it.unit = unit.uid
            self._apply(it, unit.weight, +1)
            self.index.add(it)
            lst.append(it)
        unit.routed = True
        unit.failed = False
        unit.reason = ""

    def _rip(self, unit: _Unit) -> List[_Unit]:
        """Remove a unit's copper; returns all units ripped (it and the units
        that hang on its copper)."""
        out = []
        stack = [unit]
        while stack:
            u = stack.pop()
            if not u.routed:
                continue
            lst = self.net_items.get(u.ctx.name, [])
            for it in u.items:
                self._apply(it, u.weight, -1)
                self.index.remove(it)
                lst.remove(it)
            u.items = []
            u.routed = False
            for other in self.conf.get(u.uid, ()):
                self.conf[other].discard(u.uid)
            self.conf[u.uid] = set()
            for dep in u.deps:
                self.units[dep].dependents.discard(u.uid)
            u.deps = set()
            out.append(u)
            for uid in sorted(u.dependents):
                stack.append(self.units[uid])
            u.dependents = set()
        return out

    # -- exact conflict checks -------------------------------------------
    def _conflict(self, a, b) -> bool:
        """True if routed items ``a`` and ``b`` violate a rule."""
        r = self.rules
        same = a.net == b.net
        if a.is_via and b.is_via:
            dist = math.hypot(a.x - b.x, a.y - b.y)
            if dist - a.drill / 2.0 - b.drill / 2.0 < r.hole_to_hole - EPS:
                return True
            if same:
                return False
            clr = max(a.cls_clr, b.cls_clr, self.floor)
            return (dist - a.R - b.R < clr - EPS
                    or dist - a.drill / 2.0 - b.R < r.hole_clearance - EPS
                    or dist - b.drill / 2.0 - a.R < r.hole_clearance - EPS)
        if same:
            return False
        clr = max(a.cls_clr, b.cls_clr, self.floor)
        if not a.is_via and not b.is_via:
            if a.layer != b.layer:
                return False
            dist = segment_segment_distance((a.x1, a.y1, a.x2, a.y2),
                                            (b.x1, b.y1, b.x2, b.y2))
            return dist - a.hw - b.hw < clr - EPS
        seg, via = (b, a) if a.is_via else (a, b)
        dist = point_segment_distance(via.x, via.y, seg.x1, seg.y1, seg.x2, seg.y2)
        return (dist - seg.hw - via.R < clr - EPS
                or dist - seg.hw - via.drill / 2.0 < r.hole_clearance - EPS)

    def _victims(self, items: Sequence[Any]) -> Set[int]:
        """Units whose routed copper conflicts with the given new items."""
        out: Set[int] = set()
        for it in items:
            grow = 1.0
            for other in self.index.query(it.bbox(), grow):
                if other.unit in out:
                    continue
                if self._conflict(it, other):
                    out.add(other.unit)
        return out

    def _pad_clear(self, seg: _Seg, own_net: str) -> bool:
        """Exact check of a (stub) segment against all pads of other nets and
        the board edge."""
        line = LineString([(seg.x1, seg.y1), (seg.x2, seg.y2)])
        layer = self.layers[seg.layer]
        grow = seg.hw + 0.5
        box = shapely.box(*line.buffer(grow).bounds)
        for i in self.pad_tree.query(box):
            p = self.pads[int(i)]
            if p.net == own_net or layer not in p.cu:
                continue
            clr = max(p.local_clr, self.floor) if p.local_clr else \
                max(seg.cls_clr, p.cls_clr, self.floor)
            if line.distance(p.geom) - p.georad - seg.hw < clr - EPS:
                return False
        for name, fixed in self.fixed.items():
            if name == own_net:
                continue
            for fx in fixed:
                if fx.layer == seg.layer and self._conflict(seg, fx):
                    return False
        edge = round(self.rules.copper_to_edge + seg.hw + self.opt.edge_slack, 6)
        inner = self._inner.get(edge)
        if inner is None:
            inner = self._inner[edge] = self.board_poly.buffer(-edge)
        if not inner.contains(line):
            return False
        for ko in self.design.keepouts:
            if ko.tracks and layer in ko.layer_names(self.design.copper_layers):
                if line.distance(geometry.keepout_polygon(ko)) < seg.hw + self.opt.edge_slack:
                    return False
        return True

    # -- local maps for one search ------------------------------------------
    def _window(self, cells: np.ndarray, extra: Sequence[Tuple[int, int]], margin_mm: float,
                full: bool):
        g = self.grid
        if full:
            return (0, g.ny, 0, g.nx)
        xs = list(cells[:, 1]) if len(cells) else []
        ys = list(cells[:, 2]) if len(cells) else []
        xs += [e[0] for e in extra]
        ys += [e[1] for e in extra]
        m = int(math.ceil(margin_mm / g.pitch))
        return (max(0, min(ys) - m), min(g.ny, max(ys) + m + 1),
                max(0, min(xs) - m), min(g.nx, max(xs) + m + 1))

    def _local(self, ctx: _NetCtx, rc: _RC, win, soft: bool, att: _Attempt,
               vias_left: Optional[int], ban: Sequence[Any] = ()):
        """Cost array and via map of ``win`` for one search of net ``ctx`` with
        track class ``rc``.  With ``soft`` other nets' routed copper may be
        crossed at a price (unless it is frozen)."""
        g, r = self.grid, self.rules
        iy0, iy1, ix0, ix1 = win
        rcv = ctx.rcv
        padl = rc.pad[:, iy0:iy1, ix0:ix1].astype(np.int16)
        padv = rcv.pad[0, iy0:iy1, ix0:ix1].astype(np.int16)
        ownblock = np.zeros(padv.shape, dtype=np.int16)
        vp_key = ("vp", rcv.key)
        for p in ctx.pads:
            m = self._pad_mask(p, rc)
            if m:
                for l in p.lay:
                    _blit(padl[l], win, m[0], m[1], -1)
            m = self._pad_mask(p, rcv)
            if m:
                _blit(padv, win, m[0], m[1], -1)
            if p.smd:
                key = (p.idx, vp_key)
                if key not in self.pad_masks:
                    reach = rcv.hw + self.opt.via_pad_gap
                    if p.circle:
                        self.pad_masks[key] = g.disc_mask(p.x, p.y, p.R + reach)
                    else:
                        self.pad_masks[key] = g.polygon_mask(
                            p.poly, reach + geometry.PAD_POLYGON_TOLERANCE)
                m = self.pad_masks[key]
                if m:
                    _blit(ownblock, win, m[0], m[1], 1)
        for fx in self.fixed.get(ctx.name, ()):
            for mwin, mask in fx.masks[rc.key]:
                _blit(padl[fx.layer], win, mwin, mask, -1)
            for mwin, mask in fx.masks[rcv.key]:
                _blit(padv, win, mwin, mask, -1)
        softl = rc.soft[:, iy0:iy1, ix0:ix1].astype(np.int32)
        softv = rcv.soft[0, iy0:iy1, ix0:ix1].astype(np.int32)
        softv += rcv.vhole[iy0:iy1, ix0:ix1]
        wx0, wy0 = g.x_of(ix0) - 1.0, g.y_of(iy0) - 1.0
        wx1, wy1 = g.x_of(ix1 - 1) + 1.0, g.y_of(iy1 - 1) + 1.0
        free_nodes: List[Tuple[int, int]] = []
        for it in self.net_items.get(ctx.name, ()):
            bb = it.bbox()
            if bb[2] < wx0 or bb[0] > wx1 or bb[3] < wy0 or bb[1] > wy1:
                continue
            w = self.units[it.unit].weight
            layers = range(self.L) if it.is_via else (it.layer,)
            for mwin, mask in it.masks[rc.key]:
                for l in layers:
                    _blit(softl[l], win, mwin, mask, -w)
            for mwin, mask in it.masks[rcv.key]:
                _blit(softv, win, mwin, mask, -w)
            if it.is_via:
                free_nodes.append(it.a)
        blocked = rc.static[:, iy0:iy1, ix0:ix1] | (padl > 0)
        hist = self.hist[:, iy0:iy1, ix0:ix1].astype(np.int32)
        cost = hist * self.hinc + 1
        zone_cost = int(round(STEP * self.opt.array_zone_cost))
        for arr in self.arrays:
            zw = arr["zone"]
            if zw is None or ctx.name in arr["nets"] or zone_cost <= 0:
                continue
            y0, y1 = max(iy0, zw[0]), min(iy1, zw[1])
            x0, x1 = max(ix0, zw[2]), min(ix1, zw[3])
            if y0 < y1 and x0 < x1:
                cost[:, y0 - iy0:y1 - iy0, x0 - ix0:x1 - ix0] += zone_cost
        gain = max(1, int(round(1.0 / max(self.opt.history_gain, 1e-3))))
        if soft:
            cost += np.minimum(softl * self.pen * (gain + hist) // gain, _COST_CAP)
        else:
            blocked = blocked | (softl > 0)
        for l in range(self.L):
            if l not in ctx.allowed:
                blocked[l] = True
        cost[blocked] = 0
        np.minimum(cost, _COST_CAP, out=cost)
        cost = np.ascontiguousarray(cost.astype(np.int32))

        vblocked = rcv.static[0, iy0:iy1, ix0:ix1] | (padv > 0) | (ownblock > 0)
        hreach = r.hole_to_hole + rcv.hole_r
        tmp = np.zeros(padv.shape, dtype=np.int16)
        for v in att.vias:                                   # this attempt's own new vias
            m = g.disc_mask(v.x, v.y, v.drill / 2.0 + hreach)
            if m:
                _blit(tmp, win, m[0], m[1], 1)
        for v in ban:                                        # keep other new vias away from v
            m = g.disc_mask(v.x, v.y, v.drill / 2.0 + hreach)
            if m:
                _blit(tmp, win, m[0], m[1], 1)
                x, y = v.a[0] - ix0, v.a[1] - iy0
                if 0 <= x < ix1 - ix0 and 0 <= y < iy1 - iy0:
                    tmp[y, x] -= 1
        vblocked |= tmp > 0
        vmap = 1 + self.vpref[iy0:iy1, ix0:ix1].astype(np.int32) * self.vspace_cost
        for v in att.vias:
            m = g.disc_mask(v.x, v.y, self.opt.via_spacing)
            if m:
                _blit(vmap, win, m[0], m[1], self.vspace_cost)
        if soft:
            hmax = hist.max(axis=0)
            vmap += np.minimum(softv * (self.pen * 8) * (gain + hmax) // gain, _COST_CAP)
        else:
            vblocked = vblocked | (softv > 0)
        vmap[vblocked] = 0
        if vias_left is not None and vias_left <= 0:
            vmap[:] = 0
        np.minimum(vmap, _COST_CAP, out=vmap)
        vmap = np.ascontiguousarray(vmap.astype(np.int32))
        for node in list(att.free) + free_nodes:
            x, y = node[0] - ix0, node[1] - iy0
            if 0 <= x < ix1 - ix0 and 0 <= y < iy1 - iy0:
                vmap[y, x] = FREE_VIA
        return cost, vmap, softl, softv

    # -- search helpers ------------------------------------------------------
    def _to_local(self, cells: np.ndarray, win) -> np.ndarray:
        """(n, 3) global cells (l, ix, iy) -> local cell indices inside win."""
        if len(cells) == 0:
            return np.zeros(0, dtype=np.int32)
        iy0, iy1, ix0, ix1 = win
        h, w = iy1 - iy0, ix1 - ix0
        x = cells[:, 1] - ix0
        y = cells[:, 2] - iy0
        ok = (x >= 0) & (x < w) & (y >= 0) & (y < h)
        return ((cells[ok, 0] * h + y[ok]) * w + x[ok]).astype(np.int32)

    def _pad_cells(self, p: _Pad, wide: bool) -> np.ndarray:
        """Access cells (l, ix, iy) of a pad.

        Normally the centre node when the pad is on the grid, otherwise (or
        with ``wide``) every node inside it.  A pad with a fixed escape stub
        is entered at the far end of the stub (``wide``: anywhere on it)."""
        fixed = self.pad_fixed.get(p.idx)
        if fixed and not wide:
            return np.array([(s.layer, s.b[0], s.b[1]) for s in fixed], dtype=np.int64)
        if p.center is not None and not wide:
            nodes = np.array([p.center], dtype=np.int64)
        else:
            nodes = p.nodes
            if len(nodes) == 0:
                nodes = self._near_nodes(p)
        out = [np.concatenate([np.full((len(nodes), 1), l, dtype=np.int64), nodes], axis=1)
               for l in p.lay]
        for s in fixed or ():
            out.append(np.array([(s.layer, n[0], n[1]) for n in self._seg_nodes(s)],
                                dtype=np.int64))
        if not out:
            return np.zeros((0, 3), dtype=np.int64)
        return np.concatenate(out, axis=0)

    def _near_nodes(self, p: _Pad) -> np.ndarray:
        """The grid nodes around the centre of a pad too small to contain one."""
        g = self.grid
        cx, cy = g.nearest(p.x, p.y)
        out = [(cx + dx, cy + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
               if g.inside(cx + dx, cy + dy)]
        return np.array(out, dtype=np.int64)

    def _run_search(self, cost, vmap, src, dst, tlayers, hbox, nv_levels, via_cost):
        self.stats["searches"] += 1
        if len(src) == 0:
            return np.zeros(0, dtype=np.int32)
        if hbox is None:
            hx0 = hy0 = hx1 = hy1 = 0
            hnum = 0
        else:
            hx0, hy0, hx1, hy1 = hbox
            hnum = self.hnum
        path, pops = _astar.search(cost, vmap, np.ascontiguousarray(src, dtype=np.int32),
                                   np.ascontiguousarray(dst, dtype=np.int32), int(tlayers),
                                   self.step_h, self.step_v, self.step_d, int(via_cost),
                                   int(nv_levels), int(hx0), int(hy0), int(hx1), int(hy1),
                                   int(hnum), int(self.hden), 0)
        self.stats["expansions"] += int(pops)
        return path

    def _decode(self, path: np.ndarray, win) -> List[Tuple[int, int, int]]:
        iy0, iy1, ix0, ix1 = win
        h, w = iy1 - iy0, ix1 - ix0
        l = path // (h * w)
        rem = path - l * (h * w)
        y = rem // w
        x = rem - y * w
        return [(int(a), int(b) + ix0, int(c) + iy0) for a, b, c in zip(l, x, y)]

    def _make_seg(self, ctx: _NetCtx, layer: int, a, b, hw: float) -> _Seg:
        g = self.grid
        s = _Seg()
        a = (int(a[0]), int(a[1]))
        b = (int(b[0]), int(b[1]))
        s.net, s.layer, s.a, s.b = ctx.name, int(layer), a, b
        s.x1, s.y1 = g.xy(*a)
        s.x2, s.y2 = g.xy(*b)
        s.hw, s.cls_clr = hw, ctx.cls_clr
        s.exact = True
        s.unit, s.masks, s.alive = -1, None, False
        return s

    def _make_stub(self, ctx: _NetCtx, layer: int, a, x: float, y: float, hw: float) -> _Seg:
        g = self.grid
        s = _Seg()
        a = (int(a[0]), int(a[1]))
        s.net, s.layer, s.a, s.b = ctx.name, int(layer), a, None
        s.x1, s.y1 = g.xy(*a)
        s.x2, s.y2 = x, y
        s.hw, s.cls_clr = hw, ctx.cls_clr
        s.exact = False
        s.unit, s.masks, s.alive = -1, None, False
        return s

    def _make_via(self, ctx: _NetCtx, node) -> _ViaItem:
        v = _ViaItem()
        node = (int(node[0]), int(node[1]))
        v.net, v.a = ctx.name, node
        v.x, v.y = self.grid.xy(*node)
        v.R, v.drill, v.cls_clr = ctx.via_d / 2.0, ctx.via_drill, ctx.cls_clr
        v.unit, v.masks, v.alive = -1, None, False
        return v

    def _path_items(self, ctx: _NetCtx, cells: List[Tuple[int, int, int]], att: _Attempt,
                    free: Set[Tuple[int, int]], hw: float):
        """Turn a cell path into segments and new vias."""
        segs: List[_Seg] = []
        vias: List[_ViaItem] = []
        run: List[Tuple[int, int]] = [(cells[0][1], cells[0][2])]
        layer = cells[0][0]
        for cur in cells[1:]:
            if cur[0] != layer:
                for a, b in _collinear_runs(run):
                    segs.append(self._make_seg(ctx, layer, a, b, hw))
                node = (cur[1], cur[2])
                if node not in free and node not in att.free:
                    vias.append(self._make_via(ctx, node))
                layer = cur[0]
                run = [node]
            else:
                run.append((cur[1], cur[2]))
        for a, b in _collinear_runs(run):
            segs.append(self._make_seg(ctx, layer, a, b, hw))
        return segs, vias

    def _stub_for(self, ctx: _NetCtx, p: _Pad, cell, att: _Attempt, hw: float
                  ) -> Optional[_Seg]:
        """Stub from a path end inside pad ``p`` to the pad centre, if wanted
        and legal."""
        if not self.opt.center_stubs:
            return None
        l, ix, iy = cell
        if l not in p.lay or (ix, iy) not in p.nodeset:
            return None
        if p.center is not None and p.center == (ix, iy):
            return None
        key = (p.idx, (ix, iy))
        if key in att.stubbed:
            return None
        x, y = self.grid.xy(ix, iy)
        if math.hypot(x - p.x, y - p.y) < 1e-6:
            return None
        stub = self._make_stub(ctx, l, (ix, iy), p.x, p.y, hw)
        if not self._pad_clear(stub, ctx.name) or self._victims([stub]):
            return None
        att.stubbed.add(key)
        return stub

    # -- routing one connection ------------------------------------------------
    def _connect(self, ctx: _NetCtx, att: _Attempt, src_cells: np.ndarray,
                 target: Optional[_Pad], soft: bool, share: Optional[np.ndarray] = None,
                 tlayers: int = 0, margin: Optional[float] = None, rc: Optional[_RC] = None):
        """Search from ``src_cells`` to pad ``target`` (or, for fan-outs, to a
        via: ``tlayers`` / ``share``) with track class ``rc``.  Returns
        (cells, segs, vias) or None."""
        rc = rc or ctx.rct
        vias_left = None
        if ctx.max_vias is not None:
            vias_left = ctx.max_vias - len(att.vias)
        margin = self.opt.search_margin if margin is None else margin
        tries = [(False, False), (True, True)] if target is not None else [(False, False)]
        for full, wide in tries:
            if target is not None:
                dst_cells = self._pad_cells(target, wide)
            else:
                dst_cells = share if share is not None else np.zeros((0, 3), dtype=np.int64)
            src = src_cells
            if wide:
                extra = [self._pad_cells(p, True) for p in ctx.pads if p.idx in att.connected]
                if extra:
                    src = np.concatenate([src_cells] + extra, axis=0)
            elif target is not None and len(src) > 400 and len(dst_cells):
                # big tree: search from the part of it that is near the target
                tx, ty = float(dst_cells[:, 1].mean()), float(dst_cells[:, 2].mean())
                d2 = (src[:, 1] - tx) ** 2 + (src[:, 2] - ty) ** 2
                lim = (math.sqrt(float(d2.min())) + 2.0 * margin / self.grid.pitch) ** 2
                src = src[d2 <= lim]
            pts = [(int(c[1]), int(c[2])) for c in dst_cells]
            win = self._window(src, pts, margin if not full else 0.0, full)
            lsrc = self._to_local(src, win)
            ldst = self._to_local(dst_cells, win)
            if target is not None and len(ldst) == 0:
                continue
            hbox = None
            if target is not None and not tlayers:
                iy0, _iy1, ix0, _ix1 = win
                xs = dst_cells[:, 1] - ix0
                ys = dst_cells[:, 2] - iy0
                hbox = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
            nv = 1
            if vias_left is not None and vias_left > 0:
                nv = vias_left + 1
            via_cost = self.via_cost if target is not None else self.plane_via_cost
            ban: List[Any] = []
            for _round in range(6):
                cost, vmap, softl, softv = self._local(ctx, rc, win, soft, att, vias_left,
                                                         ban)
                path = self._run_search(cost, vmap, lsrc, ldst, tlayers, hbox, nv, via_cost)
                if len(path) == 0:
                    break
                if self.opt.smooth and len(path) > 2:
                    path = _astar.smooth(path, cost, self.step_h, self.step_v, self.step_d, 400)
                cells = self._decode(path, win)
                marks = np.argwhere(vmap == FREE_VIA)
                free = {(int(x) + win[2], int(y) + win[0]) for y, x in marks}
                segs, vias = self._path_items(ctx, cells, att, free, rc.hw)
                clash = None
                for i, a in enumerate(vias):
                    for b in vias[i + 1:]:
                        if self._conflict(a, b):
                            clash = a
                            break
                    if clash is not None:
                        break
                if clash is not None:
                    ban.append(clash)                # search again with room around it
                    continue
                if soft:                             # cells that ran over other nets' copper
                    iy0, _iy1, ix0, _ix1 = win
                    for (l, ix, iy) in cells:
                        if softl[l, iy - iy0, ix - ix0] > 0:
                            att.hist.append((l, ix, iy))
                    for v in vias:                       # vias dropped onto others' copper
                        if softv[v.a[1] - iy0, v.a[0] - ix0] > 0:
                            for l in range(self.L):
                                att.hist.append((l, v.a[0], v.a[1]))
                return cells, segs, vias
        return None



    # -- routing a tree net ----------------------------------------------------
    def _route_tree(self, unit: _Unit, soft: bool, keep: Optional[List[_Path]] = None,
                    partial: bool = False) -> Optional[_Attempt]:
        """Route a tree net pad by pad.

        ``keep``     connections of the previous route to start from (only the
                     pads they do not reach are routed again)
        ``partial``  leave out pads that cannot be reached instead of giving up
                     (they are listed in ``attempt.missing``)"""
        ctx = unit.ctx
        pads = unit.pads
        by_idx = {p.idx: p for p in pads}
        att = _Attempt()
        # plated-through pads allow a free layer change
        for p in pads:
            if len(p.lay) > 1:
                for n in p.nodes:
                    att.free.add((int(n[0]), int(n[1])))
        node_pad: Dict[Tuple[int, int, int], int] = {}
        for p in pads:
            for n in p.nodes:
                for l in p.lay:
                    node_pad[(l, int(n[0]), int(n[1]))] = p.idx
            for fx in self.pad_fixed.get(p.idx, ()):
                for n in self._seg_nodes(fx):
                    node_pad[(fx.layer, n[0], n[1])] = p.idx
        if keep and unit.root in by_idx:
            start = by_idx[unit.root]
        else:
            keep = None
            best = None                    # Prim order starts from the closest pair
            for i, a in enumerate(pads):
                for b in pads[i + 1:]:
                    dist = math.hypot(a.x - b.x, a.y - b.y)
                    if best is None or dist < best[0] - 1e-12:
                        best = (dist, a, b)
            start = best[1]
        att.root = start.idx
        connected = [start]
        att.connected.add(start.idx)
        tree = [self._pad_cells(start, False)]
        cell_owner: Dict[Tuple[int, int, int], int] = {}    # track / via cell -> path index
        pad_owner: Dict[int, int] = {start.idx: -1}

        def adopt(path: _Path) -> None:
            idx = len(att.paths)
            att.paths.append(path)
            att.items.extend(path.items)
            tree.append(path.cells)
            for c in path.cells:
                cell_owner.setdefault((int(c[0]), int(c[1]), int(c[2])), idx)
            for v in path.vias:
                att.vias.append(v)
                att.free.add(v.a)
                tree.append(np.array([(l, v.a[0], v.a[1]) for l in range(self.L)],
                                     dtype=np.int64))
                for l in range(self.L):
                    cell_owner.setdefault((l, v.a[0], v.a[1]), idx)
            for pid in [path.pad] + sorted(path.met):
                if pid in att.connected or pid not in by_idx:
                    continue
                pad_owner[pid] = idx
                connected.append(by_idx[pid])
                att.connected.add(pid)
                tree.append(self._pad_cells(by_idx[pid], False))

        for path in keep or ():
            adopt(path)
        remaining = [p for p in pads if p.idx not in att.connected]
        while remaining:
            nxt = min(remaining, key=lambda p: (min(math.hypot(p.x - q.x, p.y - q.y)
                                                    for q in connected), p.idx))
            src = np.concatenate(tree, axis=0)
            rc = ctx.rct
            res = self._connect(ctx, att, src, nxt, soft, rc=rc)
            if res is None and ctx.rct_alt is not None:
                rc = ctx.rct_alt                             # neck down
                res = self._connect(ctx, att, src, nxt, soft, rc=rc)
            if res is None:
                unit.reason = "no path to pad %s" % nxt.key
                if not partial:
                    return None
                att.missing.append(nxt.key)
                remaining.remove(nxt)
                continue
            cells, segs, vias = res
            items: List[Any] = list(segs) + list(vias)
            # stubs to off-grid pad centres at both ends
            first, last = cells[0], cells[-1]
            sp = node_pad.get(first)
            if sp is not None:
                stub = self._stub_for(ctx, self.pads[sp], first, att, rc.hw)
                if stub is not None:
                    items.append(stub)
            stub = self._stub_for(ctx, nxt, last, att, rc.hw)
            if stub is not None:
                items.append(stub)
            path = _Path()
            path.pad = nxt.idx
            path.items = items
            path.cells = np.array(cells, dtype=np.int64)
            path.vias = list(vias)
            path.met = {node_pad[c] for c in cells if c in node_pad} - {nxt.idx}
            if first in cell_owner:
                path.parent = cell_owner[first]
            else:
                path.parent = pad_owner.get(node_pad.get(first, start.idx), -1)
            adopt(path)
            remaining = [p for p in remaining if p.idx not in att.connected]
        return att

    def _kept_paths(self, unit: _Unit) -> Optional[List[_Path]]:
        """Connections of a routed tree unit that are free of conflicts and do
        not hang on a conflicting one - they survive a reroute.  None when
        there is nothing worth keeping (the unit is then routed from scratch)."""
        paths = unit.paths
        if unit.kind != "tree" or len(paths) < 2:
            return None
        bad: Set[int] = set()
        for j, path in enumerate(paths):
            victims = self._victims(path.items)
            victims.discard(unit.uid)
            if victims:
                bad.add(j)
        if not bad:
            return None
        changed = True
        while changed:
            changed = False
            for j, path in enumerate(paths):
                if j not in bad and path.parent in bad:
                    bad.add(j)
                    changed = True
        if len(bad) == len(paths):
            return None
        remap: Dict[int, int] = {-1: -1}
        kept: List[_Path] = []
        for j, path in enumerate(paths):
            if j in bad:
                continue
            copy = _Path()
            copy.pad, copy.met, copy.items = path.pad, set(path.met), path.items
            copy.cells, copy.vias = path.cells, path.vias
            copy.parent = remap[path.parent]
            remap[j] = len(kept)
            kept.append(copy)
        return kept

    # -- routing a plane fan-out ---------------------------------------------
    def _route_fanout(self, unit: _Unit, soft: bool) -> Optional[_Attempt]:
        ctx = unit.ctx
        p = unit.pads[0]
        att = _Attempt()
        if not p.lay:
            unit.reason = "pad %s has no copper on a routing layer" % p.key
            return None
        tl = 0
        for l in range(self.L):
            if l not in p.lay and l in ctx.allowed:
                tl |= 1 << l
        # existing vias of the net close to the pad may be shared
        share = []
        via_units: Dict[Tuple[int, int], int] = {}
        for it in self.net_items.get(ctx.name, ()):
            if not it.is_via:
                continue
            via_units[it.a] = it.unit
            if math.hypot(it.x - p.x, it.y - p.y) <= self.opt.plane_share_radius:
                for l in p.lay:
                    share.append((l, it.a[0], it.a[1]))
        share_arr = np.array(share, dtype=np.int64) if share else None
        if tl == 0 and share_arr is None:
            unit.reason = "no layer to drop a via from pad %s" % p.key
            return None
        # stub width: the net's width, or the neck-down width for narrow pads
        rcs = [ctx.rct]
        if ctx.rct_alt is not None:
            dim = min(p.bbox[2] - p.bbox[0], p.bbox[3] - p.bbox[1])
            rcs = [ctx.rct_alt] if dim < ctx.width - 1e-9 else [ctx.rct, ctx.rct_alt]
        res = None
        rc = rcs[0]
        for margin, wide in ((2.0, False), (5.0, True), (15.0, True)):
            for rc in rcs:
                res = self._connect(ctx, att, self._pad_cells(p, wide), None, soft,
                                    share=share_arr, tlayers=tl, margin=margin, rc=rc)
                if res is not None:
                    break
            if res is not None:
                break
        if res is None:
            unit.reason = "no via site reachable from pad %s" % p.key
            return None
        cells, segs, vias = res
        items: List[Any] = list(segs) + list(vias)
        if not vias:
            # the path ended on (or changed layer through) an existing via
            for c in cells:
                uid = via_units.get((c[1], c[2]))
                if uid is not None:
                    att.deps.add(uid)
            if not att.deps:
                unit.reason = "fan-out of %s found no via" % p.key
                return None
        stub = self._stub_for(ctx, p, cells[0], att, rc.hw)
        if stub is not None:
            items.append(stub)
        att.items = items
        att.vias = list(vias)
        return att

    # -- unit driver -----------------------------------------------------------
    def _route_unit(self, unit: _Unit, soft: bool, keep: Optional[List[_Path]] = None,
                    partial: bool = False) -> Optional[_Attempt]:
        """Route one unit; the returned attempt lists the units its copper
        conflicts with (``victims``; always empty for a strict route unless
        the maps are wrong)."""
        unit.attempts += 1
        unit.reason = ""
        if unit.kind == "tree":
            att = self._route_tree(unit, soft, keep=keep, partial=partial)
        else:
            att = self._route_fanout(unit, soft)
        if att is None:
            return None
        victims = self._victims(att.items)
        victims.discard(unit.uid)
        att.victims = victims
        return att

    def _as_attempt(self, unit: _Unit) -> _Attempt:
        """The routed state of a unit as an attempt (to put it back later)."""
        att = _Attempt()
        att.items = list(unit.items)
        att.deps = set(unit.deps)
        att.paths = list(unit.paths)
        att.root = unit.root
        att.missing = list(unit.missing)
        return att

    def _time_up(self) -> bool:
        return self.opt.time_limit is not None and \
            time.time() - self.t0 > self.opt.time_limit

    def run(self) -> "RouteResult":
        """Negotiated routing (see module docstring), then cleanup and audit."""
        o = self.opt
        self.log("router: %d nets, %d units, grid %.3f mm (%d x %d), layers %s, kernel %s" % (
            len(self.routable), len(self.units), self.grid.pitch, self.grid.nx, self.grid.ny,
            "/".join(self.layers), "numba" if _astar.HAVE_NUMBA else "python"))
        self.conf = {u.uid: set() for u in self.units}
        failed: Dict[int, str] = {}
        todo = list(self.order)
        pen = self.pen0
        iteration = 0
        reroutes = 0
        best = None                              # (score, iteration, failed, snapshot)
        while todo and iteration < max(1, o.max_iterations) and not self._time_up():
            iteration += 1
            pen_max = max(self.pen0, o.present_max / self.grid.pitch * STEP)
            self.pen = max(1, int(round(min(pen, pen_max))))
            if iteration % 2 == 0:
                todo = todo[::-1]                            # take turns in giving way
            queue = deque(todo)
            pending = {u.uid for u in todo}
            forced: Set[int] = set()
            while queue:
                if self._time_up():
                    break
                unit = queue.popleft()
                pending.discard(unit.uid)
                if unit.routed and not self.conf[unit.uid] and unit.uid not in forced:
                    continue                                 # its partner has moved away
                keep = None
                if unit.routed:
                    if unit.uid not in forced:
                        keep = self._kept_paths(unit)        # reroute only what conflicts
                    for other in self._rip(unit):
                        if other is not unit:
                            forced.add(other.uid)            # hung on this unit's via
                            if other.uid not in pending:
                                queue.append(other)
                                pending.add(other.uid)
                att = self._route_unit(unit, soft=True, keep=keep)
                reroutes += 1
                if att is None:
                    failed[unit.uid] = unit.reason or "no path"
                    unit.failed = True
                    continue
                failed.pop(unit.uid, None)
                self._commit(unit, att)
                for v in att.victims:
                    self.conf[unit.uid].add(v)
                    self.conf[v].add(unit.uid)
                if att.victims:
                    for (l, ix, iy) in att.hist:
                        self.hist[l, iy, ix] = min(int(self.hist[l, iy, ix]) + 1, 1000)
            todo = [u for u in self.order if self.conf[u.uid] and u.routed]
            self.log("iteration %d: %d unit(s) in conflict, %d without path, price %d" % (
                iteration, len(todo), len(failed), self.pen))
            score = len(todo) + len(failed)
            if not self._time_up() and (best is None or score < best[0]):
                best = (score, iteration, dict(failed), self._snapshot())
            elif best is not None and iteration - best[1] >= o.patience:
                self.log("no progress for %d iterations" % o.patience)
                break
            pen *= o.present_growth
        if best is not None and best[1] != iteration:
            self.log("back to the state after iteration %d (%d open)" % (best[1], best[0]))
            failed = dict(best[2])
            self._restore(best[3])
        self.stats["iterations"] = iteration
        self.stats["reroutes"] = reroutes
        # ---- whatever still conflicts is ripped up, worst offender first ----
        ripped: List[_Unit] = []
        while True:
            worst = None
            for u in self.order:
                n = len(self.conf[u.uid])
                if n and u.routed and (worst is None or n > len(self.conf[worst.uid])
                                       or (n == len(self.conf[worst.uid]) and u.order > worst.order)):
                    worst = u
            if worst is None:
                break
            partners = sorted(self.units[v].name for v in self.conf[worst.uid])
            for u in self._rip(worst):
                u.rips += 1
                ripped.append(u)
                failed[u.uid] = "conflict with %s not resolved" % ", ".join(partners[:3])
        self.stats["ripups"] = len(ripped)
        # ---- end game: only conflict-free copper is accepted from here.  An
        # unrouted unit may displace others if they all find a clean path again
        # (bounded cascade); otherwise the board goes back to how it was. ----
        pen_max = max(self.pen0, o.present_max / self.grid.pitch * STEP)
        self.pen = max(1, int(round(pen_max)))
        forced = 0
        for _round in range(3):
            progress = False
            for uid in sorted(failed, key=lambda i: self.units[i].order):
                unit = self.units[uid]
                if unit.routed:
                    failed.pop(uid, None)
                    continue
                reason = failed[uid]
                depth = 0 if self._time_up() else max(0, o.ripup_depth)
                placed = False
                for _try in range(4 if depth else 1):
                    snap = self._snapshot() if depth else None
                    self._forced_cells = []
                    if self._force(unit, depth, frozenset()):
                        placed = True
                        break
                    if snap is not None:
                        self._restore(snap)
                    # make the next try look elsewhere: the cells where this one
                    # ran over other nets get more expensive
                    for (l, ix, iy) in self._forced_cells:
                        self.hist[l, iy, ix] = min(int(self.hist[l, iy, ix]) + 4, 1000)
                    if not self._forced_cells or self._time_up():
                        break
                if placed:
                    failed.pop(uid, None)
                    progress = True
                    forced += 1
                else:
                    failed[uid] = unit.reason or reason
                    unit.failed = True
            if not failed or not progress:
                break
        self.stats["endgame_placed"] = forced
        # what still has no complete clean route gets as much of it as possible
        for uid in sorted(failed, key=lambda i: self.units[i].order):
            unit = self.units[uid]
            if unit.routed or unit.kind != "tree":
                continue
            att = self._route_unit(unit, soft=False, partial=True)
            if att is not None and att.items and not att.victims:
                self._commit(unit, att)
                failed[uid] = "partly routed, no clean path to %s" % ", ".join(att.missing)
        self.log("negotiation done after %d iteration(s): %d unit(s) unrouted" % (
            iteration, len(failed)))
        for i in range(max(0, o.improve_passes)):
            if self._time_up():
                break
            gain = self._improve()
            self.log("improve pass %d: %.1f mm / %d via(s) saved" % (i + 1, gain[0], gain[1]))
            if gain[0] < 0.05 and gain[1] == 0:
                break
        self.failed = {self.units[uid].name: reason for uid, reason in
                       sorted(failed.items(), key=lambda kv: self.units[kv[0]].order)}
        return self._finish()

    def _force(self, unit: _Unit, depth: int, locked: frozenset) -> bool:
        """Place ``unit`` with clean copper.  If it has no clean path and
        ``depth`` allows, lay it over other units, rip those up and place them
        again the same way.  Returns False when that fails somewhere - the
        caller then restores its snapshot."""
        att = self._route_unit(unit, soft=False)
        if att is not None and not att.victims:
            self._commit(unit, att)
            return True
        if depth <= 0:
            return False
        att = self._route_unit(unit, soft=True)
        if att is None:
            return False
        self._forced_cells.extend(att.hist)
        victims = [self.units[v] for v in sorted(att.victims)]
        if not victims or any(v.uid in locked for v in victims):
            return False
        ripped: List[_Unit] = []
        for v in victims:
            ripped.extend(self._rip(v))
        if any(v.uid in locked for v in ripped):
            return False
        left = self._victims(att.items)
        left.discard(unit.uid)
        if left:
            return False
        self._commit(unit, att)
        locked = locked | {unit.uid}
        for v in sorted(ripped, key=lambda u: u.order):
            if not self._force(v, depth - 1, locked):
                unit.reason = "no clean path; pushing %s aside did not work either" % v.name
                return False
        return True

    def _snapshot(self) -> Dict[str, Any]:
        """Remember the routed copper and conflicts of every unit."""
        return {"units": {u.uid: self._as_attempt(u) for u in self.units if u.routed},
                "conf": {uid: set(v) for uid, v in self.conf.items()}}

    def _restore(self, snap: Dict[str, Any]) -> None:
        """Go back to a state saved by :meth:`_snapshot`."""
        for u in self.units:
            if u.routed:
                self._rip(u)
        for u in self.order:
            att = snap["units"].get(u.uid)
            if att is not None:
                self._commit(u, att)
        self.conf = {uid: set(v) for uid, v in snap["conf"].items()}

    # -- improvement -------------------------------------------------------------
    def _unit_cost(self, items: Sequence[Any]) -> Tuple[float, int]:
        length = sum(it.length for it in items if not it.is_via)
        vias = sum(1 for it in items if it.is_via)
        return length, vias

    def _improve(self) -> Tuple[float, int]:
        """Rip each tree unit once and route it again with everything else in
        place; keep the better of the two."""
        saved_len, saved_vias = 0.0, 0
        for unit in self.order:
            if unit.kind != "tree" or not unit.routed or unit.dependents:
                continue
            if unit.missing:
                continue
            before = self._as_attempt(unit)
            old = self._unit_cost(before.items)
            self._rip(unit)
            att = self._route_unit(unit, soft=False)
            better = False
            if att is not None and not att.victims:
                new = self._unit_cost(att.items)
                better = (new[0] + self.opt.via_cost * new[1]
                          < old[0] + self.opt.via_cost * old[1] - 1e-9)
            if better:
                self._commit(unit, att)
                saved_len += old[0] - new[0]
                saved_vias += old[1] - new[1]
            else:
                self._commit(unit, before)
        return saved_len, saved_vias

    # -- output --------------------------------------------------------------------
    def _finish(self) -> "RouteResult":
        tracks, vias = self._emit()
        aud = audit(self.design, tracks, vias)
        length: Dict[str, float] = {}
        for t in tracks:
            length[t.layer] = length.get(t.layer, 0.0) + t.length
        self.stats.update({
            "nets": len(self.routable),
            "units": len(self.units),
            "grid_mm": self.grid.pitch,
            "grid_nodes": [self.grid.nx, self.grid.ny],
            "routing_layers": list(self.layers),
            "plane_nets": dict(sorted(self.plane_of.items())),
            "kernel": "numba" if _astar.HAVE_NUMBA else "python",
            "track_length_mm": round(sum(length.values()), 3),
            "track_length_by_layer_mm": {k: round(v, 3) for k, v in sorted(length.items())},
            "tracks": len(tracks), "vias": len(vias),
            "runtime_s": round(time.time() - self.t0, 2),
        })
        res = RouteResult(tracks, vias, aud, dict(self.stats), dict(getattr(self, "failed", {})))
        self.log(res.summary())
        return res

    def _emit(self) -> Tuple[List[Track], List[Via]]:
        """Final cleanup and conversion to model primitives."""
        g = self.grid
        tracks: List[Track] = []
        vias: List[Via] = []
        for name in self.design.nets:
            items = self.net_items.get(name, [])
            fixed = self.fixed.get(name, [])
            if not items and not fixed:
                continue
            ctx = self.ctx[name]
            stubs = [it for it in items if not it.is_via and it.b is None]
            vnodes = sorted({it.a for it in items if it.is_via})
            anchors: Set[Tuple[int, int, int]] = set()
            for p in ctx.pads:
                for n in p.nodes:
                    for l in p.lay:
                        anchors.add((l, int(n[0]), int(n[1])))
            for s in stubs:
                anchors.add((s.layer, s.a[0], s.a[1]))
            for v in vnodes:
                for l in range(self.L):
                    anchors.add((l, v[0], v[1]))
            for fx in fixed:
                for n in self._seg_nodes(fx):
                    anchors.add((fx.layer, n[0], n[1]))
                tracks.append(Track(name, self.layers[fx.layer], fx.x1, fx.y1, fx.x2, fx.y2,
                                    round(2.0 * fx.hw, 6)))
            groups: Dict[float, List[Any]] = {}
            for it in items:
                if not it.is_via and it.b is not None:
                    groups.setdefault(round(2.0 * it.hw, 6), []).append((it.layer, it.a, it.b))
            if len(groups) > 1:
                # pieces of different width meet end to end: those nodes are anchors too
                seen: Dict[Tuple[int, int, int], float] = {}
                for width, segs in groups.items():
                    for layer, a, b in segs:
                        for n in (a, b):
                            key = (layer, n[0], n[1])
                            if seen.setdefault(key, width) != width:
                                anchors.add(key)
            for width in sorted(groups):
                cleaned = cleanup_segments(groups[width], anchors, set(vnodes), self.L)
                for layer, a, b in cleaned:
                    x1, y1 = g.xy(*a)
                    x2, y2 = g.xy(*b)
                    tracks.append(Track(name, self.layers[layer], x1, y1, x2, y2, width))
            for s in stubs:
                tracks.append(Track(name, self.layers[s.layer], round(s.x1, 6), round(s.y1, 6),
                                    round(s.x2, 6), round(s.y2, 6), round(2.0 * s.hw, 6)))
            for v in vnodes:
                x, y = g.xy(*v)
                vias.append(Via(name, x, y, ctx.via_d, ctx.via_drill))
        return tracks, vias

# --------------------------------------------------------------------------
# cleanup
# --------------------------------------------------------------------------

_AXES = ((1, 0), (0, 1), (1, 1), (1, -1))


def cleanup_segments(segs: Iterable[Tuple[int, Tuple[int, int], Tuple[int, int]]],
                     anchors: Set[Tuple[int, int, int]], via_nodes: Set[Tuple[int, int]],
                     n_layers: int
                     ) -> List[Tuple[int, Tuple[int, int], Tuple[int, int]]]:
    """Final cleanup of one net's grid tracks.

    ``segs`` are ``(layer, (ix, iy), (ix, iy))`` pieces along the 8 grid
    directions.  They are dissolved into unit edges (duplicates and overlaps
    vanish), then

    * dangling ends are pruned back to the next junction: an end node must be
      an *anchor* (``(layer, ix, iy)`` inside a pad, on a via or carrying an
      off-grid stub);
    * loops are opened (an edge whose two ends are already connected through
      tracks and vias is dropped, then the pruning is repeated);
    * collinear edges are merged into maximal segments, which are split at
      junctions and vias so that every connection is end-to-end.

    Returns segments in the same form, sorted."""
    edges: Dict[int, Set[Tuple[Tuple[int, int], Tuple[int, int]]]] = {}
    for layer, a, b in segs:
        layer = int(layer)
        a = (int(a[0]), int(a[1]))
        b = (int(b[0]), int(b[1]))
        dx, dy = b[0] - a[0], b[1] - a[1]
        n = max(abs(dx), abs(dy))
        if n == 0:
            continue
        if not (dx == 0 or dy == 0 or abs(dx) == abs(dy)):
            raise ValueError("segment %r-%r is not on a grid direction" % (a, b))
        sx, sy = (dx > 0) - (dx < 0), (dy > 0) - (dy < 0)
        es = edges.setdefault(layer, set())
        for i in range(n):
            p = (a[0] + sx * i, a[1] + sy * i)
            q = (p[0] + sx, p[1] + sy)
            es.add((p, q) if p < q else (q, p))

    def degrees(layer):
        deg: Dict[Tuple[int, int], int] = {}
        for p, q in edges.get(layer, ()):
            deg[p] = deg.get(p, 0) + 1
            deg[q] = deg.get(q, 0) + 1
        return deg

    def prune():
        for layer in list(edges):
            es = edges[layer]
            adj: Dict[Tuple[int, int], Set[Tuple[int, int]]] = {}
            for p, q in es:
                adj.setdefault(p, set()).add(q)
                adj.setdefault(q, set()).add(p)
            stack = [n for n, nb in adj.items() if len(nb) == 1 and (layer,) + n not in anchors]
            while stack:
                n = stack.pop()
                nb = adj.get(n)
                if not nb or len(nb) != 1 or (layer,) + n in anchors:
                    continue
                m = next(iter(nb))
                es.discard((n, m) if n < m else (m, n))
                adj[m].discard(n)
                del adj[n]
                if len(adj[m]) == 1 and (layer,) + m not in anchors:
                    stack.append(m)

    prune()
    # loops: union-find over (layer, node); a via joins its node on all layers
    parent: Dict[Any, Any] = {}

    def find(x):
        root = x
        while parent.setdefault(root, root) != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    for v in sorted(via_nodes):
        for l in range(1, n_layers):
            parent[find((l,) + v)] = find((0,) + v)
    dropped = False
    for layer in sorted(edges):
        for p, q in sorted(edges[layer]):
            a, b = find((layer,) + p), find((layer,) + q)
            if a == b:
                edges[layer].discard((p, q))
                dropped = True
            else:
                parent[a] = b
    if dropped:
        prune()

    out: List[Tuple[int, Tuple[int, int], Tuple[int, int]]] = []
    for layer in sorted(edges):
        deg = degrees(layer)
        es = edges[layer]
        for ax in _AXES:
            mine = sorted(e for e in es if (e[1][0] - e[0][0], e[1][1] - e[0][1]) == ax)
            nxt = {p: q for p, q in mine}
            starts = [p for p, q in mine
                      if (p[0] - ax[0], p[1] - ax[1]) not in nxt or deg[p] != 2 or p in via_nodes]
            for s in starts:
                e = nxt[s]
                while e in nxt and deg[e] == 2 and e not in via_nodes:
                    e = nxt[e]
                out.append((layer, s, e))
    out.sort()
    return out


# --------------------------------------------------------------------------
# audit
# --------------------------------------------------------------------------

def audit(design: Design, tracks: Sequence[Track], vias: Sequence[Via],
          tol: float = 1e-6) -> AuditResult:
    """Exact check of routed geometry against the design's rules, without
    KiCad.

    * clearance of every track / via to pads, tracks and vias of other nets
      (:meth:`gleda.model.Design.clearance`, pad overrides included), hole to
      copper and hole to hole (same net included), copper to board edge, track
      and via keep-outs;
    * connectivity computed from the copper: pads, tracks and vias that touch
      are joined, and every via or plated pad of a net that owns a whole-board
      plane is joined to that plane.  (The plane itself is assumed to be in
      one piece - KiCad's zone fill and DRC have the last word on that.)

    Nets with ``no_route`` and single-pad nets are not expected to be
    connected."""
    r = design.rules
    res = AuditResult()
    pads = [p for p in geometry.placed_pads(design) if p.polygon is not None and p.layers]
    floor = r.min_clearance
    board_poly = geometry.outline_polygon(design.outline, r.max_arc_error)
    boundary = board_poly.boundary

    def viol(kind, net, x, y, detail):
        res.violations.append({"type": kind, "net": net, "x": round(x, 4), "y": round(y, 4),
                               "detail": detail})

    pad_geoms = []
    pad_rad = []
    for p in pads:
        if p.shape == "circle" and abs(p.w - p.h) < 1e-9:
            pad_geoms.append(Point(p.x, p.y))
            pad_rad.append(p.w / 2.0)
        else:
            pad_geoms.append(p.polygon)
            pad_rad.append(0.0)
    t_geoms = [LineString([(t.x1, t.y1), (t.x2, t.y2)]) if t.length > 1e-9
               else Point(t.x1, t.y1) for t in tracks]
    v_geoms = [Point(v.x, v.y) for v in vias]
    pad_tree = STRtree(pad_geoms) if pad_geoms else None
    t_tree = STRtree(t_geoms) if t_geoms else None
    v_tree = STRtree(v_geoms) if v_geoms else None
    reach = 1.0 + max([t.width for t in tracks] + [v.diameter for v in vias] + [0.0])

    def near(tree, geom):
        if tree is None:
            return []
        return [int(i) for i in tree.query(geom.buffer(reach))]

    # ---- clearances --------------------------------------------------------
    for i, t in enumerate(tracks):
        gt = t_geoms[i]
        hw = t.width / 2.0
        if t.width < design.min_track_width(t.net) - tol:
            viol("track_width", t.net, t.x1, t.y1, "width %.4f" % t.width)
        for j in near(pad_tree, gt):
            p = pads[j]
            if p.net == t.net or t.layer not in p.layers:
                continue
            need = design.clearance(t.net, p.net, local_b=p.clearance)
            gap = gt.distance(pad_geoms[j]) - pad_rad[j] - hw
            if gap < need - tol:
                viol("clearance", t.net, t.x1, t.y1,
                     "track to pad %s: %.4f < %.4f" % (p.key, gap, need))
            if p.kind == "th" and p.drill > 0:
                hole_gap = gt.distance(Point(p.x, p.y)) - p.drill / 2.0 - hw
                if hole_gap < r.hole_clearance - tol:
                    viol("hole_clearance", t.net, t.x1, t.y1,
                         "track to hole of %s: %.4f" % (p.key, hole_gap))
        for j in near(t_tree, gt):
            if j <= i:
                continue
            o = tracks[j]
            if o.net == t.net or o.layer != t.layer:
                continue
            need = max(design.clearance(t.net, o.net), floor)
            gap = gt.distance(t_geoms[j]) - hw - o.width / 2.0
            if gap < need - tol:
                viol("clearance", t.net, t.x1, t.y1,
                     "track to track of %s: %.4f < %.4f" % (o.net, gap, need))
        for j in near(v_tree, gt):
            v = vias[j]
            if v.net == t.net:
                continue
            need = design.clearance(t.net, v.net)
            dist = gt.distance(v_geoms[j])
            if dist - hw - v.diameter / 2.0 < need - tol:
                viol("clearance", t.net, v.x, v.y,
                     "track to via of %s: %.4f < %.4f" % (v.net, dist - hw - v.diameter / 2.0,
                                                          need))
            if dist - hw - v.drill / 2.0 < r.hole_clearance - tol:
                viol("hole_clearance", t.net, v.x, v.y, "track to via hole of %s" % v.net)
        edge_gap = gt.distance(boundary) - hw
        if edge_gap < r.copper_to_edge - tol or not board_poly.contains(gt):
            viol("copper_edge_clearance", t.net, t.x1, t.y1, "track to edge %.4f" % edge_gap)
    for i, v in enumerate(vias):
        gv = v_geoms[i]
        rad = v.diameter / 2.0
        if rad - v.drill / 2.0 < r.min_annular - tol:
            viol("annular_width", v.net, v.x, v.y, "ring %.4f" % (rad - v.drill / 2.0))
        for j in near(pad_tree, gv):
            p = pads[j]
            dist = gv.distance(pad_geoms[j]) - pad_rad[j]
            if p.net != v.net:
                need = design.clearance(v.net, p.net, local_b=p.clearance)
                if dist - rad < need - tol:
                    viol("clearance", v.net, v.x, v.y,
                         "via to pad %s: %.4f < %.4f" % (p.key, dist - rad, need))
                if dist - v.drill / 2.0 < r.hole_clearance - tol:
                    viol("hole_clearance", v.net, v.x, v.y, "via hole to pad %s" % p.key)
            if p.kind == "th" and p.drill > 0:
                hh = math.hypot(v.x - p.x, v.y - p.y) - v.drill / 2.0 - p.drill / 2.0
                if hh < r.hole_to_hole - tol:
                    viol("hole_near_hole", v.net, v.x, v.y, "via to hole of %s" % p.key)
        for j in near(v_tree, gv):
            if j <= i:
                continue
            o = vias[j]
            dist = math.hypot(v.x - o.x, v.y - o.y)
            if dist - v.drill / 2.0 - o.drill / 2.0 < r.hole_to_hole - tol:
                viol("hole_near_hole", v.net, v.x, v.y,
                     "via to via of %s: %.4f" % (o.net, dist - v.drill / 2.0 - o.drill / 2.0))
            if o.net != v.net:
                need = design.clearance(v.net, o.net)
                if dist - rad - o.diameter / 2.0 < need - tol:
                    viol("clearance", v.net, v.x, v.y, "via to via of %s" % o.net)
        edge_gap = gv.distance(boundary) - rad
        if edge_gap < r.copper_to_edge - tol or not board_poly.contains(gv):
            viol("copper_edge_clearance", v.net, v.x, v.y, "via to edge %.4f" % edge_gap)
        for h in design.outline.holes:
            hh = math.hypot(v.x - h.x, v.y - h.y) - v.drill / 2.0 - h.drill / 2.0
            if hh < r.hole_to_hole - tol:
                viol("hole_near_hole", v.net, v.x, v.y, "via to NPTH hole")
    for h in design.outline.holes:
        hp = Point(h.x, h.y)
        for i in near(t_tree, hp):
            t = tracks[i]
            if t_geoms[i].distance(hp) - h.drill / 2.0 - t.width / 2.0 < r.hole_clearance - tol:
                viol("hole_clearance", t.net, h.x, h.y, "track to NPTH hole")
    for ko in design.keepouts:
        poly = geometry.shape_polygon(ko.shape, r.max_arc_error, "inscribed")
        names = ko.layer_names(design.copper_layers)
        if ko.tracks:
            for i in near(t_tree, poly):
                t = tracks[i]
                if t.layer in names and t_geoms[i].distance(poly) < t.width / 2.0 - tol:
                    viol("items_not_allowed", t.net, t.x1, t.y1,
                         "track in keep-out %s" % (ko.name or "?"))
        if ko.vias:
            for i in near(v_tree, poly):
                v = vias[i]
                if v_geoms[i].distance(poly) < v.diameter / 2.0 - tol:
                    viol("items_not_allowed", v.net, v.x, v.y,
                         "via in keep-out %s" % (ko.name or "?"))

    # ---- connectivity ------------------------------------------------------------
    parent: Dict[Any, Any] = {}

    def find(x):
        root = x
        while parent.setdefault(root, root) != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    planes = design.full_plane_layers()
    plane_layers: Dict[str, Set[str]] = {}
    for layer, net in planes.items():
        plane_layers.setdefault(net, set()).add(layer)
    touch = 1e-6
    for i, t in enumerate(tracks):
        gt = t_geoms[i]
        for j in near(pad_tree, gt):
            p = pads[j]
            if p.net == t.net and t.layer in p.layers and \
                    gt.distance(pad_geoms[j]) - pad_rad[j] <= touch:
                union(("t", i), ("p", j))
        for j in near(t_tree, gt):
            if j > i and tracks[j].net == t.net and tracks[j].layer == t.layer \
                    and gt.distance(t_geoms[j]) <= touch:
                union(("t", i), ("t", j))
        for j in near(v_tree, gt):
            if vias[j].net == t.net and gt.distance(v_geoms[j]) <= touch:
                union(("t", i), ("v", j))
    for i, v in enumerate(vias):
        if v.net in plane_layers:
            union(("v", i), ("plane", v.net))
        for j in near(pad_tree, v_geoms[i]):
            p = pads[j]
            if p.net == v.net and v_geoms[i].distance(pad_geoms[j]) - pad_rad[j] <= touch:
                union(("v", i), ("p", j))
    for j, p in enumerate(pads):
        if p.net in plane_layers and plane_layers[p.net] & set(p.layers):
            union(("p", j), ("plane", p.net))
    by_net: Dict[str, List[int]] = {}
    for j, p in enumerate(pads):
        if p.net:
            by_net.setdefault(p.net, []).append(j)
    for name, net in design.nets.items():
        idxs = by_net.get(name, [])
        if net.no_route or len(idxs) < 2:
            continue
        res.connections_total += len(idxs) - 1
        groups: Dict[Any, List[str]] = {}
        for j in idxs:
            groups.setdefault(find(("p", j)), []).append(pads[j].key)
        if len(groups) > 1:
            pieces = sorted((sorted(set(g)) for g in groups.values()),
                            key=lambda g: (-len(g), g))
            res.unrouted.append(Unrouted(name, pieces))
    return res


# --------------------------------------------------------------------------
# public entry points
# --------------------------------------------------------------------------

def route(design: Design, options: Optional[RouterOptions] = None) -> RouteResult:
    """Route every net of ``design`` that has two or more pads and is not
    marked ``no_route``.  Nothing is written to the design or to disk.

    The result is honest: ``RouteResult.unrouted`` lists every connection the
    final copper does not make, and ``RouteResult.complete`` is true only if
    there is none and the exact audit found no rule violation."""
    return Router(design, options).run()


def route_board(design: Design, pcb_path: str, options: Optional[RouterOptions] = None, *,
                run_drc: bool = True, json_path: Optional[str] = None):
    """Route ``design`` and write the result into the board file built from
    it (:func:`gleda.board.build_board`), then fill the zones and run KiCad's
    DRC.  Returns ``(RouteResult, DrcResult or None)``.

    Nothing is asserted here - call :func:`gleda.drc.assert_clean` on the DRC
    result and check ``RouteResult.complete``."""
    from . import board as board_mod
    result = route(design, options)
    board_mod.apply_routing(pcb_path, result.tracks, result.vias,
                            via_tenting=design.via_tenting)
    drc_result = None
    if run_drc:
        from . import drc as drc_mod
        drc_result = drc_mod.run_drc(pcb_path, json_path=json_path)
    return result, drc_result


__all__ = ["RouterOptions", "RouteResult", "AuditResult", "Unrouted", "RoutingError",
           "Router", "route", "route_board", "audit", "cleanup_segments"]
