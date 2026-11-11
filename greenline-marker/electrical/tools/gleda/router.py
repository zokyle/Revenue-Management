"""gleda autorouter: grid-based A* with negotiated rip-up-and-reroute, for the
kind of board gleda targets (small, 4 layers, two or three routing layers plus
planes, fine-pitch parts, a few hundred connections).

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
``Design.signal_layers()``: the outer layers and every inner layer that is not
given to a whole-board plane, or whose plane is ``routable``.

*Obstacle maps.*  For every "route class" - (track half-width, class
clearance) and (via radius, drill, class clearance) of the nets to route -
the router keeps count maps of all obstacles grown by the clearance KiCad
will ask for (:meth:`gleda.model.Design.clearance`: the larger class
clearance of the two nets, or a pad's local override) plus the mover's
half-width: pads of every net on both outer layers, routed tracks and vias,
keep-outs, board edge and cutouts, drilled holes (hole-to-copper and
hole-to-hole).  A net's own copper is subtracted while that net is routed.
Distances are exact; see :mod:`gleda.raster` for the clearance maths.

*Units.*  The work is cut into small units that are routed, ripped up and
rerouted independently:

* a **connection** - one edge of a net's minimum spanning tree.  It joins
  the copper that hangs on one pad with the copper that hangs on the other,
  wherever the two are closest (pad, track or via), so a multi-pin net grows
  as a tree with T junctions, not as a chain of pad-to-pad wires;
* a **fan-out** - stub and through via that drop one pad of a plane net into
  its plane (never a via in the pad; a pad may share the via of a neighbour
  of its net);
* an **escape** - the way out of a fine-pitch array for one of its pads.

*Stage A: array escape.*  Before anything else is on the board, the pads of
each fine-pitch array (BGA / CSP) and the other pads in a window around it
are routed among themselves: every signal pad gets a track to the rim of the
window - on any layer, pulled toward where its net has to go - or straight to
a pad of its net inside the window, every plane pad its stub and via.  This
small puzzle is negotiated to zero conflicts and then frozen: the fan-out a
designer would draw first.  Connections of an escaped pad start from its
escape track; what remains unused of it is pruned at the end.

*Search.*  A* over (layer, y, x) with integer costs (:mod:`gleda._astar`),
no corner cutting, optional preferred direction per layer, a cost per via, an
optional limit of vias per net and a higher price for tracks on a plane layer
that signals share.

*Negotiation.*  All units are routed with other nets' copper allowed at a
price; the units that conflict are routed again and again while the price of
sharing and the history cost of contested cells go up (PathFinder style).
What still conflicts when that stalls is ripped up, worst offender first.

*End game.*  From here only conflict-free copper is accepted.  An open unit is
placed strictly if it can be; otherwise it is laid over other units, those are
ripped and placed again the same way (a bounded cascade), and the board goes
back to how it was if that does not work out.  Units still open start another
negotiation wave from the board as it is.  Nets of a class with
``min_track_width`` may neck down as the last resort.

*Planes.*  Tracks on a shared plane layer and rows of via clearances can cut
a plane's fill into pieces.  :func:`plane_regions` predicts the fill the way
KiCad makes it; a pad whose via ends up in a cut-off piece gets a real track
to the main part.

*Improvement and cleanup.*  With the history forgotten every unit is ripped
once and routed again along the plain shortest path (kept if better); nets
with long detours or many vias are taken off as a whole and routed again;
nets of a fine class that is not confined to fine areas are laid again at
the standard width where they find room.  Then every net's tracks are
dissolved into unit grid edges and rebuilt: duplicates vanish, dangling stubs
are pruned, loops are opened, a narrow piece on a wider track of its net
goes, collinear pieces are merged and segments are split at junctions so
that every connection is end-to-end; one-step staircases become diagonals
where an exact check allows it.

*Fine areas.*  In a design with fine areas
(:meth:`gleda.model.Design.add_fine_area`) a net of a fine class uses its
fine width and clearance only between grid nodes inside an area and the
standard values everywhere else; the search joins the two obstacle maps along
the area boundary and the track changes width there.

*Audit.*  :func:`audit` re-checks the final geometry with exact shapely
distances (clearance, edge, holes round and oblong, keep-outs, widths, fine
areas, the gap between a via and a pad of its own net) and computes the
connectivity from the copper alone, planes and pours by their predicted fill.
``RouteResult.unrouted`` comes from this audit, not from the router's
book-keeping.  :func:`net_quality` compares every net with its spanning tree
(``RouteResult.warnings``).  KiCad's DRC remains the judge.

Per-net options (set on :class:`gleda.model.Net`): ``width``, ``max_vias``,
``layers``, ``no_route``, ``priority``; clearance, default width and the
neck-down width come from the net class.

Everything is deterministic: the same design and options give the same
copper (:func:`fingerprint`, :func:`save_routing`, :func:`load_routing`).

Limits: see the README ("Router: limits").
"""
from __future__ import annotations

import json
import math
import random
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.strtree import STRtree

from . import _astar, geometry
from .model import Design, Track, Via, VIA_TENTING
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
                         this is how many levels deep that may cascade ...
    ``ripup_budget``     ... and how many units one such push may reroute in all
    ``patience``         stop negotiating when the number of conflicts has not
                         improved for this many rounds; the best state seen is
                         the one that is kept
    ``waves``            negotiation + end game are repeated up to this many
                         times while units are still open: each later wave
                         starts from the board as it is, with the history
                         forgotten ...
    ``reheat_price``     ... and the price of sharing set back to this value
                         (track length per cell), so that the open units push
                         their way in and their neighbours make room
    ``region_margins``   last resort for a unit that is still open: everything
                         routed within this distance of it is ripped up and
                         negotiated again as one small puzzle while the rest of
                         the board is frozen; one try per margin ...
    ``region_tries``     ... for at most this many open units ...
    ``region_iterations`` / ``region_patience``  ... with these limits
    ``neckdown``         nets of a class with ``min_track_width`` may be routed
                         at that width where the full width does not fit: the
                         stub of a pad narrower than the track, a connection
                         that has no way at full width at all, and - as the
                         last resort of the end game - a connection that could
                         not be placed at full width even by pushing other
                         nets aside.  A net with its own ``width`` never necks
                         down.
    ``smooth``           straighten every path (fewer bends, same cost)
    ``time_limit``       seconds after which no more rip-up is started;
                         whatever is unrouted then is reported as unrouted
    ``improve_passes``   reroute-everything-once passes after completion
    ``improve_nets``     after those: every net whose track is longer than this
                         many times its spanning tree (or has more vias than
                         pads) is taken off the board as a whole and routed
                         again, shortest connections first; kept if cheaper.
                         0 switches it off
    ``straighten``       final cleanup: replace one-step staircases and jogs by
                         a diagonal where an exact check allows it
    ``widen``            a net of a fine class that is NOT confined to fine
                         areas (the design declares none) is laid again, once
                         the board is complete, with the standard width and
                         clearance wherever a connection finds room for it;
                         kept if that removes fine track without making the
                         net much longer.  Best effort: nothing guarantees
                         where the remaining fine track is - fine areas do
    ``widen_reach``      for that pass the fine geometry is wanted only within
                         this distance of the pad field of a fine-pitch array;
                         a connection that cannot be made that way keeps its
                         fine track
    ``search_margin``    window around a connection searched first
    ``edge_slack``       extra distance to the board edge and keep-outs
    ``via_pad_gap``      copper gap between a via and an SMD pad of its own net
                         (vias are never placed in pads).  None (default): from
                         the rule set - ``Rules.via_pad_gap_open`` where the via
                         is not tented on the pad's side
                         (``Design.via_tenting``), ``via_pad_gap_tented``
                         where it is
    ``array_via_keepout``  no via closer than this to the pad field of a
                         fine-pitch array (BGA / CSP): the escape tracks of
                         all its pads need the lanes around it, a via there
                         blocks several of them.  0 switches it off.
    ``array_pitch``      a part counts as fine-pitch array when it has nine or
                         more round pads at this pitch or less
    ``array_escape``     stage A: before anything else is routed, fan every
                         connected pad of such an array out to its own via
                         outside the array (negotiated among the pads of the
                         array only) and freeze that copper.  Nets with
                         ``max_vias`` are left out.
    ``escape_iterations``  negotiation rounds of stage A per array ...
    ``escape_patience``  ... and the patience there (rounds are cheap)
    ``escape_attempts``  stage A is tried in up to this many unit orders while
                         pads are left without an escape; the best try is kept
    ``escape_reach``     size of the escape window around the pad field of an
                         array: an escape is a route from the pad to the rim
                         of that window on any layer
    ``escape_pad_gap``   an escape does not end closer than this to a pad on
                         the rim (pads there must stay reachable from outside)
    ``escape_grow``      a side of the escape window that would cut through a
                         part's pads moves outward past them by at most this
    ``escape_exit``      an escape may only end on a rim cell from which the
                         track can go on: this far straight beyond the rim
                         everything must be free for its net (no hole, pad,
                         edge or keep-out right behind the rim).  0 = any cell
    ``fine_transition``  an array whose nets are confined to a fine area keeps
                         its escape window this far inside that area: the room
                         in which the fan-out spreads from the fine to the
                         standard pitch
    ``escape_direction``  how strongly an escape is pulled toward the rest of
                         its net (0 = leave wherever it is shortest)
    ``escape_improve``   reroute-each-once passes that straighten the fan-out
                         after its negotiation
    ``escape_freeze``    the fan-out found in stage A is final: its copper is a
                         hard obstacle for every other net from then on (the
                         lanes between the balls are too scarce to be traded
                         in the main negotiation).  Off: the escapes stay
                         negotiable, only more expensive to run over ...
    ``escape_weight``    ... by this factor
    ``escape_neighbours``  the other pads inside an array's escape window (its
                         decoupling capacitors, pull-ups ...) get their plane
                         via or their way out in stage A as well, so that the
                         whole neighbourhood is fanned out as one puzzle
    ``endgame_rounds``   passes over the open units in the end game ...
    ``endgame_tries``    ... and tries per unit and pass
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
    ``plane_layer_cost`` a track on a plane layer that signals may share
                         (``Plane.routable``) costs this many times its length:
                         the layer is kept for what does not fit elsewhere
    ``plane_repair_rounds``  how often the router looks for pads cut off from
                         their plane by other copper and joins them with a track
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
    max_iterations: int = 150
    patience: int = 20
    waves: int = 2
    reheat_price: float = 0.15
    region_margins: Tuple[float, ...] = (2.0, 4.0)
    region_tries: int = 6
    region_iterations: int = 80
    region_patience: int = 25
    ripup_depth: int = 8
    ripup_budget: int = 60
    neckdown: bool = True
    smooth: bool = True
    time_limit: Optional[float] = None
    improve_passes: int = 1
    improve_nets: float = 1.3
    straighten: bool = True
    widen: bool = True
    widen_reach: float = 5.0
    search_margin: float = 3.0
    edge_slack: float = geometry.DRC_SLACK
    via_pad_gap: Optional[float] = None
    array_via_keepout: float = 0.75
    array_pitch: float = 0.65
    array_escape: bool = True
    escape_iterations: int = 200
    escape_patience: int = 40
    escape_attempts: int = 6
    escape_reach: float = 3.0
    escape_pad_gap: float = 0.6
    escape_grow: float = 1.0
    escape_exit: float = 0.4
    fine_transition: float = 1.0
    escape_direction: float = 1.0
    escape_improve: int = 4
    escape_freeze: bool = True
    escape_weight: int = 20
    escape_neighbours: bool = True
    endgame_rounds: int = 4
    endgame_tries: int = 4
    array_zone: float = 1.5
    array_zone_cost: float = 1.0
    history_gain: float = 0.25
    via_spacing: float = 0.9
    via_spacing_cost: float = 1.5
    plane_share_radius: float = 1.2
    plane_layer_cost: float = 4.0
    plane_repair_rounds: int = 3
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
    #: "net/layer" -> number of separate pieces of that plane's fill
    plane_pieces: Dict[str, int] = field(default_factory=dict)

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
                "connections_missing": self.missing,
                "plane_pieces": dict(self.plane_pieces)}


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

    @property
    def quality(self) -> Dict[str, Any]:
        """Per-net length against the spanning tree, via counts and the
        warnings derived from them (see :func:`net_quality`)."""
        return self.stats.get("quality", {})

    @property
    def warnings(self) -> List[str]:
        """Nets a layout engineer should look at: long detours, many vias."""
        return list(self.quality.get("warnings", []))

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
                 "nodeset", "nodelist", "center", "bbox", "hole", "via_gap")


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
        #: via classes only: hole-to-hole reach of the routed vias (all nets) ...
        self.vhole = np.zeros(shape, dtype=np.uint16) if is_via else None
        #: ... and of the frozen vias (a hard obstacle, the via's own net included)
        self.vhard = np.zeros(shape, dtype=np.uint8) if is_via else None


class _NetCtx:
    __slots__ = ("name", "cls_clr", "width", "hw", "via_d", "via_drill", "rct", "rcv",
                 "rct_alt", "pads", "allowed", "max_vias", "plane", "priority", "th_nodes",
                 "rct_out", "out_hw", "out_clr", "via_clr", "rct_wide")


class _Unit:
    """One routing job.

    ``conn``    join the copper that hangs on pad ``pads[0]`` with the copper
                that hangs on ``pads[1]`` (one edge of the net's spanning tree)
    ``fanout``  stub + via that drops pad ``pads[0]`` of a plane net into its
                plane
    ``escape``  way out of a fine-pitch array for pad ``pads[0]`` of a signal
                net (optional helper: the pad's connections start from it)
    """
    __slots__ = ("uid", "kind", "ctx", "pads", "phase", "length", "items", "rips", "weight",
                 "failed", "reason", "routed", "deps", "dependents", "attempts", "order",
                 "touch", "cells", "hw", "trivial", "win", "rim", "targets", "array",
                 "narrow", "frozen", "at_rim", "rimset", "wide")

    def __init__(self, uid, kind, ctx, pads):
        self.uid = uid
        self.kind = kind
        self.ctx = ctx
        self.pads = pads
        self.phase = 2
        self.length = 0.0
        self.items: List[Any] = []
        self.rips = 0
        self.weight = 1
        self.failed = False
        self.reason = ""
        self.routed = False
        self.deps: Set[int] = set()                        # units whose copper it touches
        self.dependents: Set[int] = set()
        self.attempts = 0
        self.order = 0
        self.touch: Set[int] = set()                       # pads its copper touches
        self.cells: List[Tuple[int, int, int]] = []        # its cell path (l, ix, iy)
        self.hw = 0.0                                      # track half-width used
        self.trivial = False                               # conn: joined by other copper
        self.win = None                                    # escape: search window ...
        self.rim = None                                    # ... the cells on its border ...
        self.targets = None                                # ... (destination cells, extra cost)
        self.array = False                                 # pad of a fine-pitch array
        self.narrow = False                                # end game: may neck down
        self.frozen = False                                # its copper is there to stay
        self.at_rim = False                                # escape: ends on the window rim
        self.rimset = None                                 # escape: the rim cells as a set
        self.wide = False                                  # conn: use the standard width

    @property
    def name(self) -> str:
        if self.kind == "conn":
            return "%s:%s-%s" % (self.ctx.name, self.pads[0].key, self.pads[1].key)
        if self.kind == "escape":
            return "%s@%s(escape)" % (self.ctx.name, self.pads[0].key)
        return "%s@%s" % (self.ctx.name, self.pads[0].key)


class _Attempt:
    """Result of routing one unit (not yet committed)."""

    def __init__(self):
        self.items: List[Any] = []
        self.victims: Set[int] = set()
        self.hist: List[Tuple[int, int, int]] = []
        self.deps: Set[int] = set()
        self.touch: Set[int] = set()
        self.cells: List[Tuple[int, int, int]] = []
        self.vias: List[_ViaItem] = []
        self.stubbed: Set[Tuple[int, Tuple[int, int]]] = set()
        self.hw = 0.0
        self.trivial = False
        self.at_rim = False


class _NetState:
    """Connectivity of one net's routed copper (see Router._net_state)."""
    __slots__ = ("parent", "find", "units", "escaped", "owner")

    def __init__(self):
        self.parent: Dict[Any, Any] = {}
        self.find: Any = None
        self.units: List[_Unit] = []
        self.escaped: Set[int] = set()
        self.owner: Dict[Tuple[int, int, int], Tuple[str, int]] = {}


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
        self.net_units: Dict[str, List[_Unit]] = {}
        self.pad_masks: Dict[Tuple[int, Any], Any] = {}
        self._forced_cells: List[Tuple[int, int, int]] = []
        self._force_left = 0
        self._copper_tree: Any = None
        self._inner: Dict[float, Any] = {}
        #: frozen connections found broken by the last _unsatisfied() call
        self._frozen_broken: List[_Unit] = []
        self.stats: Dict[str, Any] = {"searches": 0, "expansions": 0, "ripups": 0,
                                      "reroutes": 0}
        self.units: List[_Unit] = []
        self.order: List[_Unit] = []
        self.conf: Dict[int, Set[int]] = {}
        self.failed: Dict[str, str] = {}
        self._failed_net: Dict[str, str] = {}
        self._setup_costs()
        self._setup_pads()
        self._setup_nets()
        self._setup_maps()

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
            # a diagonal step is one step with and one against the preference; it
            # must not be cheaper than taking the two on their own layers
            sd.append(DIAG if pref == "any" else int(round(DIAG * (1.0 + bias))))
        self.step_h = np.array(sh, dtype=np.int32)
        self.step_v = np.array(sv, dtype=np.int32)
        self.step_d = np.array(sd, dtype=np.int32)
        w = max(1.0, o.heuristic_weight)
        self.hnum, self.hden = int(round(w * 100)), 100

    def _setup_pads(self) -> None:
        d, g = self.design, self.grid
        self.pads: List[_Pad] = []
        #: non-plated holes: (centre line (x1, y1, x2, y2), width) - round
        #: holes have a centre line of length 0 - and the netless copper rings
        #: of NPTH pads that are larger than their hole
        self.npth: List[Tuple[Tuple[float, float, float, float], float]] = []
        self.rings: List[Any] = []
        for seg, width, ring, _name in geometry.npth_holes(d):
            self.npth.append((seg, width))
            if ring is not None:
                self.rings.append(ring)
        open_sides = VIA_TENTING.get(d.via_tenting, ())
        o_gap = self.opt.via_pad_gap
        for pp in geometry.placed_pads(d):
            if pp.kind == "npth" or pp.polygon is None or not pp.layers:
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
            p.hole = pp.hole_segment
            p.smd = pp.kind != "th"
            # gap between the pad and a via of its own net: wider where the via
            # is not covered by solder mask on the pad's side
            if o_gap is not None:
                p.via_gap = o_gap
            else:
                mask = "F.Mask" if pp.side == "top" else "B.Mask"
                p.via_gap = self.rules.via_pad_gap_open if mask in open_sides \
                    else self.rules.via_pad_gap_tented
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
            if len(p.nodes) == 0:
                # smaller than the grid: entered at the nodes around its centre
                p.nodes = self._near_nodes(p)
            p.nodelist = [(int(n[0]), int(n[1])) for n in p.nodes]
            p.nodeset = set(p.nodelist)
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
        #: planes on routing layers that signals may share (layer -> net)
        self.mixed: Dict[str, str] = {}
        for layer, net in d.routable_plane_layers().items():
            if layer in self.lidx:
                self.mixed[layer] = net
                plane_of.setdefault(net, layer)
                k = max(1.0, self.opt.plane_layer_cost)
                l = self.lidx[layer]
                self.step_h[l] = int(round(self.step_h[l] * k))
                self.step_v[l] = int(round(self.step_v[l] * k))
                self.step_d[l] = int(round(self.step_d[l] * k))
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
            c.rct = c.rcv = c.rct_alt = c.rct_out = c.rct_wide = None
            c.out_hw, c.out_clr = c.hw, c.cls_clr
            if d.is_confined(name):
                # fine class in a design with fine areas: fine geometry inside
                # them, the standard width and clearance everywhere else
                ow, oc = d.outside_values(name)
                c.out_hw, c.out_clr = ow / 2.0, max(oc, self.floor)
            # vias keep the wider clearance everywhere (they never sit between balls)
            c.via_clr = c.out_clr
            c.th_nodes = set()
            for p in pads:
                if len(p.lay) > 1:                      # plated through: free layer change
                    c.th_nodes.update(p.nodelist)
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
                              round(c.via_clr, 6)), c.via_d / 2.0, c.via_drill / 2.0,
                             c.via_clr, True)
            if d.is_confined(name):
                c.rct_out = self._rc(("t", round(c.out_hw, 6), round(c.out_clr, 6)), c.out_hw,
                                     0.0, c.out_clr, False)
            elif self.opt.neckdown and d.netclass_of(name).min_track_width is not None \
                    and net.width is None:
                wmin = d.min_track_width(name)
                if wmin < c.width - 1e-9:
                    c.rct_alt = self._rc(("t", round(wmin / 2.0, 6), round(c.cls_clr, 6)),
                                         wmin / 2.0, 0.0, c.cls_clr, False)
            if self.opt.widen and not d.is_confined(name) and net.width is None \
                    and d.is_fine_class(d.netclass_of(name)):
                # an unconfined fine class: the standard width and clearance
                # are tried for its connections once the board is complete
                whw = max(c.width, self.rules.default_track) / 2.0
                wclr = max(c.cls_clr, self.rules.default_clearance, self.floor)
                if whw > c.hw + 1e-9 or wclr > c.cls_clr + 1e-9:
                    c.rct_wide = self._rc(("t", round(whw, 6), round(wclr, 6)), whw, 0.0,
                                          wclr, False)

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
        default_clr = max(d.netclasses["Default"].clearance, self.floor)
        # Nodes inside the fine areas: a confined net may join two of them with
        # a fine track.  Its search uses the fine obstacle maps only at the nodes
        # whose eight neighbours are fine nodes too (``fine_core``): a node on
        # the rim can be the end of a standard-width piece that leaves the area.
        region = geometry.fine_region(d)
        #: no fine areas declared, but fine-pitch arrays and the widening pass:
        #: the surroundings of the arrays serve as stand-in fine areas for that
        #: pass ("fine near the arrays, standard width beyond" - not enforced)
        self.virtual_fine = False
        if region is None and o.widen and o.widen_reach > 0 and self.arrays \
                and any(c.rct_wide is not None for c in self.routable):
            boxes = [shapely.box(a["bbox"][0] - o.widen_reach, a["bbox"][1] - o.widen_reach,
                                 a["bbox"][2] + o.widen_reach, a["bbox"][3] + o.widen_reach)
                     for a in self.arrays]
            region = shapely.unary_union(boxes)
            shapely.prepare(region)
            self.virtual_fine = True
        self.fine_region = region
        self.fine_mask = g.contained_mask(region) if region is not None \
            else np.zeros(self.shape, dtype=bool)
        core = self.fine_mask.copy()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx or dy:
                    shifted = np.zeros_like(core)
                    ys = slice(max(0, dy), self.shape[0] + min(0, dy))
                    yd = slice(max(0, -dy), self.shape[0] + min(0, -dy))
                    xs = slice(max(0, dx), self.shape[1] + min(0, dx))
                    xd = slice(max(0, -dx), self.shape[1] + min(0, -dx))
                    shifted[yd, xd] = self.fine_mask[ys, xs]
                    core &= shifted
        self.fine_core = core
        # nodes at which a via of a plane net really reaches its plane: inside
        # the plane's static area (not in a copper keep-out of the plane layer,
        # not in a higher-priority pour of another net, not at the edge)
        self.plane_ok: Dict[str, np.ndarray] = {}
        for net, layer in sorted(self.plane_of.items()):
            area = plane_static_area(d, layer, net)
            ok = g.contained_mask(area.buffer(-(r.zone_min_width / 2.0 + 0.03)))
            self.plane_ok[net] = ok
        for rc in self.rcs.values():
            # board edge and cutouts
            inset = r.copper_to_edge + rc.hw + o.edge_slack
            allowed = self.board_poly.buffer(-inset)
            rc.static[:] = ~g.contained_mask(allowed)[None, :, :]
            # drilled holes without copper: round or oblong (a stadium)
            for (hseg, width) in self.npth:
                reach = max(r.hole_clearance, r.copper_to_edge) + rc.hw + o.edge_slack
                if rc.is_via:
                    reach = max(reach, r.hole_to_hole + rc.hole_r)
                m = g.stadium_mask(hseg[0], hseg[1], hseg[2], hseg[3],
                                   width / 2.0 + reach + move_margin(reach, g.pitch))
                if m:
                    win, mask = m
                    rc.static[:, win[0]:win[1], win[2]:win[3]] |= mask[None, :, :]
            # ... and the netless copper around a non-plated hole (every layer)
            for ring in self.rings:
                reach = self._reach(rc, default_clr)
                m = g.polygon_mask(ring, reach + move_margin(reach, g.pitch)
                                   + geometry.PAD_POLYGON_TOLERANCE)
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
                    m = g.stadium_mask(p.hole[0], p.hole[1], p.hole[2], p.hole[3],
                                       p.drill / 2.0 + reach)
                    if m and rc.is_via:
                        # hole-to-hole applies to the pad's own net as well
                        win, mask = m
                        rc.static[0, win[0]:win[1], win[2]:win[3]] |= mask

    # -- units -------------------------------------------------------------------
    def _new_unit(self, kind: str, ctx: _NetCtx, pads: List[_Pad]) -> _Unit:
        u = _Unit(len(self.units), kind, ctx, pads)
        self.units.append(u)
        self.conf[u.uid] = set()
        self.net_units.setdefault(ctx.name, []).append(u)
        return u

    @staticmethod
    def _mst(pads: List[_Pad]) -> List[Tuple[_Pad, _Pad, float]]:
        """Minimum spanning tree over pad centres (Prim, started at the closest
        pair): the connections a net is made of."""
        n = len(pads)
        if n < 2:
            return []

        def dist(i, j):
            return math.hypot(pads[i].x - pads[j].x, pads[i].y - pads[j].y)

        best = None
        for i in range(n):
            for j in range(i + 1, n):
                dij = dist(i, j)
                if best is None or dij < best[0] - 1e-12:
                    best = (dij, i, j)
        start = best[1]
        in_tree = [False] * n
        in_tree[start] = True
        near = [dist(start, j) for j in range(n)]
        link = [start] * n
        edges: List[Tuple[_Pad, _Pad, float]] = []
        for _k in range(n - 1):
            j = min((k for k in range(n) if not in_tree[k]),
                    key=lambda k: (round(near[k], 9), pads[k].idx))
            edges.append((pads[link[j]], pads[j], near[j]))
            in_tree[j] = True
            for k in range(n):
                if not in_tree[k]:
                    dk = dist(j, k)
                    if dk < near[k] - 1e-12:
                        near[k] = dk
                        link[k] = j
        return edges

    def _escape_window(self, bbox, confined: bool = False
                       ) -> Tuple[float, float, float, float]:
        """The escape window of an array: its pad field grown by
        ``escape_reach``; a side that would cut through a part's pads is moved
        outward past them (by at most ``escape_grow``), so that the part is
        fanned out with the array instead of sitting on the rim.

        ``confined``: nets of the array may be fine only inside a fine area.
        The window then stays ``fine_transition`` inside the fine area around
        the array, so that the fanned-out tracks - which leave the window at
        the fine pitch - have that much room to spread to the standard pitch
        before the area ends."""
        o = self.opt
        e = max(o.escape_reach, o.array_via_keepout + 1.0)
        gap = o.escape_pad_gap
        x0, y0, x1, y1 = bbox[0] - e, bbox[1] - e, bbox[2] + e, bbox[3] + e
        lim = (x0 - o.escape_grow, y0 - o.escape_grow, x1 + o.escape_grow, y1 + o.escape_grow)
        if confined and self.fine_region is not None:
            cx, cy = (bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0
            for poly in getattr(self.fine_region, "geoms", [self.fine_region]):
                if poly.contains(Point(cx, cy)):
                    fx0, fy0, fx1, fy1 = poly.bounds
                    t = max(0.0, o.fine_transition)
                    keep = o.array_via_keepout + 0.5      # ... but never tighter than this
                    inner = (min(fx0 + t, bbox[0] - keep), min(fy0 + t, bbox[1] - keep),
                             max(fx1 - t, bbox[2] + keep), max(fy1 - t, bbox[3] + keep))
                    x0, y0 = max(x0, inner[0]), max(y0, inner[1])
                    x1, y1 = min(x1, inner[2]), min(y1, inner[3])
                    lim = (max(lim[0], inner[0]), max(lim[1], inner[1]),
                           min(lim[2], inner[2]), min(lim[3], inner[3]))
                    break
        step = self.grid.pitch
        for _round in range(8):
            changed = False
            for p in self.pads:
                bx0, by0, bx1, by1 = p.bbox
                if bx1 < x0 - gap or bx0 > x1 + gap or by1 < y0 - gap or by0 > y1 + gap:
                    continue
                if bx0 - gap < x0 < bx1 + gap and by1 > y0 and by0 < y1:
                    new = max(lim[0], bx0 - gap - step)
                    if new < x0 - 1e-9:
                        x0, changed = new, True
                if bx0 - gap < x1 < bx1 + gap and by1 > y0 and by0 < y1:
                    new = min(lim[2], bx1 + gap + step)
                    if new > x1 + 1e-9:
                        x1, changed = new, True
                if by0 - gap < y0 < by1 + gap and bx1 > x0 and bx0 < x1:
                    new = max(lim[1], by0 - gap - step)
                    if new < y0 - 1e-9:
                        y0, changed = new, True
                if by0 - gap < y1 < by1 + gap and bx1 > x0 and bx0 < x1:
                    new = min(lim[3], by1 + gap + step)
                    if new > y1 + 1e-9:
                        y1, changed = new, True
            if not changed:
                break
        return x0, y0, x1, y1

    def _escape_arrays(self) -> None:
        """Stage A: route every connected pad of a fine-pitch array (BGA /
        CSP) out of the array before anything else is on the board.

        The pads of one array are negotiated among themselves (a small problem
        that converges quickly): a pad of a signal net gets a track to the rim
        of the array's escape window - on any layer, pulled toward where its
        net has to go - or straight to a pad of its net inside the window; a
        pad of a plane net gets its stub and via.  What comes out is the fan-out
        a designer would draw first.  The escapes then take part in the main
        negotiation like any other copper, only they are more expensive to
        run over (``escape_weight``); the connections of an escaped pad start
        from its escape track."""
        o = self.opt
        self.stats["escapes"] = 0
        self.stats["escape_failed"] = 0
        if not o.array_escape or not self.arrays:
            return
        for arr in self.arrays:
            units: List[_Unit] = []
            pads = arr["pads"]
            cx = sum(p.x for p in pads) / len(pads)
            cy = sum(p.y for p in pads) / len(pads)
            confined = any(self.ctx[n].rct_out is not None for n in arr["nets"]
                           if n in self.ctx)
            win = self.grid.window(*self._escape_window(arr["bbox"], confined))
            iy0, iy1, ix0, ix1 = win
            border = [(ix, iy) for ix in range(ix0, ix1) for iy in (iy0, iy1 - 1)]
            border += [(ix, iy) for iy in range(iy0 + 1, iy1 - 1) for ix in (ix0, ix1 - 1)]
            # an escape must not end right next to a pad: that pad (and the
            # pads beyond it) still have to be reached from outside the window
            pts = shapely.points([self.grid.x_of(ix) for ix, _iy in border],
                                 [self.grid.y_of(iy) for _ix, iy in border])
            if self._copper_tree is None:                     # pad copper outlines, built once
                self._copper_tree = STRtree([p.poly for p in self.pads])
            near = self._copper_tree.query(pts, predicate="dwithin",
                                           distance=o.escape_pad_gap)
            crowded = set(int(i) for i in near[0])
            border = [b for i, b in enumerate(border) if i not in crowded]
            rim = np.array([(l, ix, iy) for l in range(self.L) for ix, iy in border],
                           dtype=np.int64).reshape(-1, 3)
            rimset = set((int(a), int(b), int(c)) for a, b, c in rim)
            # inner pads first: they have the fewest ways out
            for p in sorted(pads, key=lambda q: (max(abs(q.x - cx), abs(q.y - cy)), q.idx)):
                ctx = self.ctx.get(p.net) if p.net else None
                if ctx is None or ctx.rct is None or not p.lay:
                    continue
                if ctx.plane:
                    if ctx.plane in p.cu:
                        continue
                    u = self._new_unit("fanout", ctx, [p])
                else:
                    u = self._new_unit("escape", ctx, [p])
                    u.win, u.rim, u.rimset = win, rim, rimset
                u.array = True
                u.phase = -1
                u.order = u.uid
                units.append(u)
            if not units:
                continue
            mine_idx = {p.idx for p in pads}
            if o.escape_neighbours:
                # the other pads inside the window are part of the same puzzle:
                # their plane vias and ways out are negotiated with the fan-out
                wx0, wx1 = self.grid.x_of(ix0), self.grid.x_of(ix1 - 1)
                wy0, wy1 = self.grid.y_of(iy0), self.grid.y_of(iy1 - 1)
                mine = {p.idx for p in pads}
                taken = {u.pads[0].idx for u in self.units if u.array}
                for p in self.pads:
                    if p.idx in mine or p.idx in taken or not p.net or not p.lay:
                        continue
                    if not (wx0 < p.x < wx1 and wy0 < p.y < wy1):
                        continue
                    ctx = self.ctx.get(p.net)
                    if ctx is None or ctx.rct is None:
                        continue
                    if ctx.plane:
                        if ctx.plane in p.cu:
                            continue
                        u = self._new_unit("fanout", ctx, [p])
                    else:
                        u = self._new_unit("escape", ctx, [p])
                        u.win, u.rim, u.rimset = win, rim, rimset
                    u.array = True
                    u.phase = -1
                    u.order = u.uid
                    units.append(u)
            # The puzzle is small, so it is tried in several orders and the best
            # result is kept: first the array from the inside out, then the
            # reverse, then the neighbours' pads first.
            base = list(units)
            orders = [base, base[::-1],
                      sorted(base, key=lambda u: (u.pads[0].idx in mine_idx, u.uid))]
            for seed in range(max(0, o.escape_attempts - 3)):
                mixed = list(base)
                random.Random(seed + 1).shuffle(mixed)        # fixed seeds: reproducible
                orders.append(mixed)
            best = None                                       # (open, attempt, snapshot)
            iterations = 0
            for attempt in range(max(1, o.escape_attempts)):
                if attempt:
                    for u in units:
                        if u.routed:
                            self._rip(u)
                        u.failed = False
                        self.conf[u.uid] = set()
                seq = orders[attempt % len(orders)]
                for i, u in enumerate(seq):
                    u.order = units[0].uid + i
                self.hist[:] = 0
                failed, its = self._negotiate(seq, o.escape_iterations, o.escape_patience,
                                              "escape %s" % arr["ref"], optional_escapes=False)
                iterations += its
                self._rip_conflicts(seq, failed)
                self.hist[:] = 0                              # its job is done
                for _round in range(2):                       # second chance, pushing allowed
                    self._escape_sweep(seq)
                    for u in seq:
                        if not u.routed and not self._time_up():
                            self._place(u)
                self.hist[:] = 0
                still = sum(1 for u in units if not u.routed)
                if best is None or still < best[0]:
                    best = (still, attempt, self._snapshot())
                if still == 0 or self._time_up():
                    break
            if best is not None and best[0] < sum(1 for u in units if not u.routed):
                self._restore(best[2])
            for _pass in range(max(0, o.escape_improve)):     # pull the fan-out tight
                gain = self._improve(units)
                if gain[0] < 0.05 and gain[1] == 0:
                    break
            done = sum(1 for u in units if u.routed)
            self.stats["escapes"] += done
            self.stats["escape_failed"] += len(units) - done
            self.log("escape %s: %d of %d pad(s) fanned out in %d iteration(s)" % (
                arr["ref"], done, len(units), iterations))
            # a complete fan-out is frozen; an incomplete one stays negotiable
            # (only expensive to run over), or the pads left out could be
            # walled in for good
            freeze = o.escape_freeze and done == len(units)
            if o.escape_freeze and not freeze:
                self.log("escape %s: incomplete, left negotiable" % arr["ref"])
            for u in units:
                self.conf[u.uid] = set()
                u.failed = False
                if freeze:
                    self._freeze(u)

    def _setup_units(self) -> None:
        """The units of the main stage: one connection per edge of every
        net's spanning tree, one fan-out per pad of a plane net; the escapes
        of stage A stay in the game."""
        default_clr = max(self.design.netclasses["Default"].clearance, self.floor)
        for c in self.routable:
            if c.plane:
                have = {u.pads[0].idx for u in self.net_units.get(c.name, ())
                        if u.kind == "fanout"}
                for p in c.pads:
                    if c.plane in p.cu or p.idx in have:
                        continue                       # on the plane / handled in stage A
                    u = self._new_unit("fanout", c, [p])
                    u.phase = 1
            else:
                for a, b, dist in self._mst(c.pads):
                    u = self._new_unit("conn", c, [a, b])
                    u.length = dist
                    u.phase = 0 if c.cls_clr < default_clr - 1e-9 else 2
        order = sorted(self.units, key=lambda u: (-u.ctx.priority, u.phase, u.length, u.uid))
        for i, u in enumerate(order):
            u.order = i
        self.order = order

    @staticmethod
    def _seg_nodes(seg: _Seg) -> List[Tuple[int, int]]:
        """All grid nodes on an on-grid segment."""
        a, b = seg.a, seg.b
        n = max(abs(b[0] - a[0]), abs(b[1] - a[1]))
        if n == 0:
            return [a]
        sx, sy = (b[0] - a[0]) // n, (b[1] - a[1]) // n
        return [(a[0] + sx * i, a[1] + sy * i) for i in range(n + 1)]

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

    def _freeze(self, unit: _Unit) -> None:
        """Make a routed unit's copper a hard obstacle: it moves from the maps
        of negotiable copper to the maps of hard obstacles (like pads), so
        nothing is routed over it and it is not ripped up - for good (the
        fan-out of stage A) or until :meth:`_unfreeze`."""
        if unit.frozen or not unit.routed:
            return
        for it in unit.items:
            self._apply(it, unit.weight, -1)
            self._apply_hard(it, +1)
        unit.frozen = True
        self.conf[unit.uid] = set()

    def _unfreeze(self, unit: _Unit) -> None:
        """Undo :meth:`_freeze`."""
        if not unit.frozen:
            return
        for it in unit.items:
            self._apply_hard(it, -1)
            self._apply(it, unit.weight, +1)
        unit.frozen = False

    def _apply_hard(self, it, sign: int) -> None:
        """Add / remove an item to / from the hard obstacle maps."""
        g, r = self.grid, self.rules
        for rc in self.rcs.values():
            if rc.is_via:
                layers: Sequence[int] = (0,)
            elif it.is_via:
                layers = range(self.L)
            else:
                layers = (it.layer,)
            for win, mask in it.masks[rc.key]:
                for l in layers:
                    view = rc.pad[l, win[0]:win[1], win[2]:win[3]]
                    if sign > 0:
                        view[mask] += 1
                    else:
                        view[mask] -= 1
            if rc.is_via and it.is_via:
                # hole to hole: for every net, the via's own included
                m = g.disc_mask(it.x, it.y, it.drill / 2.0 + r.hole_to_hole + rc.hole_r)
                if m:
                    win, mask = m
                    view = rc.vhard[win[0]:win[1], win[2]:win[3]]
                    if sign > 0:
                        view[mask] += 1
                    else:
                        view[mask] -= 1
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
        unit.cells = list(att.cells)
        unit.hw = att.hw
        unit.touch = set(att.touch)
        unit.trivial = att.trivial
        unit.at_rim = att.at_rim
        unit.weight = max(1, int(self.opt.escape_weight)) \
            if unit.array and unit.kind != "conn" else 1
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
        whose copper hangs on its copper)."""
        out = []
        stack = [unit]
        while stack:
            u = stack.pop()
            if not u.routed or u.frozen:
                continue
            lst = self.net_items.get(u.ctx.name, [])
            for it in u.items:
                self._apply(it, u.weight, -1)
                self.index.remove(it)
                lst.remove(it)
            u.items = []
            u.cells = []
            u.touch = set()
            u.trivial = False
            u.at_rim = False
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
        edge = round(self.rules.copper_to_edge + seg.hw + self.opt.edge_slack, 6)
        inner = self._inner.get(edge)
        if inner is None:
            inner = self._inner[edge] = self.board_poly.buffer(-edge)
        if not inner.contains(line):
            return False
        need = max(self.rules.hole_clearance, self.rules.copper_to_edge) + seg.hw \
            + self.opt.edge_slack
        for hseg, width in self.npth:
            if segment_segment_distance((seg.x1, seg.y1, seg.x2, seg.y2), hseg) \
                    - width / 2.0 < need - EPS:
                return False
        for ring in self.rings:
            clr = max(seg.cls_clr, self.design.netclasses["Default"].clearance, self.floor)
            if line.distance(ring) - geometry.PAD_POLYGON_TOLERANCE - seg.hw < clr - EPS:
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
               vias_left: Optional[int], ban: Sequence[Any] = (), plane_sites: bool = False):
        """Cost array and via map of ``win`` for one search of net ``ctx`` with
        track class ``rc``.  With ``soft`` other nets' routed copper may be
        crossed at a price.  ``plane_sites``: vias only where they reach the
        net's plane (fan-outs).

        A confined net (fine class in a design with fine areas) searches with
        its fine class inside the fine areas and with the standard width and
        clearance outside (and on the rim nodes, see ``fine_core``): the two
        maps are joined along the area boundary."""
        cost, vmap, softl, softv = self._local_rc(ctx, rc, win, soft, att, vias_left, ban,
                                                  plane_sites)
        if ctx.rct_out is None or rc is not ctx.rct:
            return cost, vmap, softl, softv
        cost_o, _vmap, softl_o, _softv = self._local_rc(ctx, ctx.rct_out, win, soft, att,
                                                        vias_left, ban, plane_sites)
        iy0, iy1, ix0, ix1 = win
        fm = self.fine_core[None, iy0:iy1, ix0:ix1]
        cost = np.ascontiguousarray(np.where(fm, cost, cost_o).astype(np.int32))
        softl = np.where(fm, softl, softl_o)
        return cost, vmap, softl, softv

    def _local_rc(self, ctx: _NetCtx, rc: _RC, win, soft: bool, att: _Attempt,
                  vias_left: Optional[int], ban: Sequence[Any] = (),
                  plane_sites: bool = False):
        """:meth:`_local` for one route class."""
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
                    reach = rcv.hw + p.via_gap
                    if p.circle:
                        self.pad_masks[key] = g.disc_mask(p.x, p.y, p.R + reach)
                    else:
                        self.pad_masks[key] = g.polygon_mask(
                            p.poly, reach + geometry.PAD_POLYGON_TOLERANCE)
                m = self.pad_masks[key]
                if m:
                    _blit(ownblock, win, m[0], m[1], 1)
        free_nodes: List[Tuple[int, int]] = []
        softl = rc.soft[:, iy0:iy1, ix0:ix1].astype(np.int32)
        softv = rcv.soft[0, iy0:iy1, ix0:ix1].astype(np.int32)
        softv += rcv.vhole[iy0:iy1, ix0:ix1]
        wx0, wy0 = g.x_of(ix0) - 1.0, g.y_of(iy0) - 1.0
        wx1, wy1 = g.x_of(ix1 - 1) + 1.0, g.y_of(iy1 - 1) + 1.0
        for it in self.net_items.get(ctx.name, ()):
            bb = it.bbox()
            if bb[2] < wx0 or bb[0] > wx1 or bb[3] < wy0 or bb[1] > wy1:
                continue
            owner = self.units[it.unit]
            layers = range(self.L) if it.is_via else (it.layer,)
            if owner.frozen:                             # hard for the others, not for its net
                for mwin, mask in it.masks[rc.key]:
                    for l in layers:
                        _blit(padl[l], win, mwin, mask, -1)
                for mwin, mask in it.masks[rcv.key]:
                    _blit(padv, win, mwin, mask, -1)
            else:
                w = owner.weight
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

        vblocked = rcv.static[0, iy0:iy1, ix0:ix1] | (padv > 0) | (ownblock > 0) \
            | (rcv.vhard[iy0:iy1, ix0:ix1] > 0)
        if plane_sites and ctx.name in self.plane_ok:
            vblocked |= ~self.plane_ok[ctx.name][iy0:iy1, ix0:ix1]
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
        for node in list(ctx.th_nodes) + free_nodes:
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
        with ``wide``) every node inside it."""
        if p.center is not None and not wide:
            nodes = np.array([p.center], dtype=np.int64)
        else:
            nodes = p.nodes
        out = [np.concatenate([np.full((len(nodes), 1), l, dtype=np.int64), nodes], axis=1)
               for l in p.lay]
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

    def _make_seg(self, ctx: _NetCtx, layer: int, a, b, hw: float,
                  clr: Optional[float] = None) -> _Seg:
        g = self.grid
        s = _Seg()
        a = (int(a[0]), int(a[1]))
        b = (int(b[0]), int(b[1]))
        s.net, s.layer, s.a, s.b = ctx.name, int(layer), a, b
        s.x1, s.y1 = g.xy(*a)
        s.x2, s.y2 = g.xy(*b)
        s.hw, s.cls_clr = hw, ctx.cls_clr if clr is None else clr
        s.exact = True
        s.unit, s.masks, s.alive = -1, None, False
        return s

    def _make_stub(self, ctx: _NetCtx, layer: int, a, x: float, y: float, hw: float,
                   clr: Optional[float] = None) -> _Seg:
        g = self.grid
        s = _Seg()
        a = (int(a[0]), int(a[1]))
        s.net, s.layer, s.a, s.b = ctx.name, int(layer), a, None
        s.x1, s.y1 = g.xy(*a)
        s.x2, s.y2 = x, y
        s.hw, s.cls_clr = hw, ctx.cls_clr if clr is None else clr
        s.exact = False
        s.unit, s.masks, s.alive = -1, None, False
        return s

    def _is_fine(self, node) -> bool:
        """True if the grid node lies inside a fine area."""
        ix, iy = int(node[0]), int(node[1])
        return 0 <= ix < self.grid.nx and 0 <= iy < self.grid.ny \
            and bool(self.fine_mask[iy, ix])

    def _edge_class(self, ctx: _NetCtx, rc: _RC, a, b) -> Tuple[float, float]:
        """(half-width, class clearance) of the track piece between the grid
        nodes ``a`` and ``b`` of a net routed with class ``rc``.  For a confined
        net a piece is fine only if BOTH its ends are fine nodes - it then lies
        completely inside the area, which is what KiCad's rule asks for."""
        if ctx.rct_out is None or rc is not ctx.rct:
            return rc.hw, (rc.clr if rc is ctx.rct_wide else ctx.cls_clr)
        if self._is_fine(a) and self._is_fine(b):
            return ctx.hw, ctx.cls_clr
        return ctx.out_hw, ctx.out_clr

    def _make_via(self, ctx: _NetCtx, node) -> _ViaItem:
        v = _ViaItem()
        node = (int(node[0]), int(node[1]))
        v.net, v.a = ctx.name, node
        v.x, v.y = self.grid.xy(*node)
        v.R, v.drill, v.cls_clr = ctx.via_d / 2.0, ctx.via_drill, ctx.via_clr
        v.unit, v.masks, v.alive = -1, None, False
        return v

    def _path_items(self, ctx: _NetCtx, cells: List[Tuple[int, int, int]],
                    free: Set[Tuple[int, int]], rc: _RC):
        """Turn a cell path into segments and new vias."""
        segs: List[_Seg] = []
        vias: List[_ViaItem] = []
        run: List[Tuple[int, int]] = [(cells[0][1], cells[0][2])]
        layer = cells[0][0]

        def flush(nodes, lay):
            if ctx.rct_out is None or rc is not ctx.rct:
                clr = rc.clr if rc is ctx.rct_wide else None
                for a, b in _collinear_runs(nodes):
                    segs.append(self._make_seg(ctx, lay, a, b, rc.hw, clr))
                return
            # confined net: the width follows the fine areas, piece by piece
            start, prev, key = nodes[0], nodes[0], None
            for cur in nodes[1:]:
                k = ((cur[0] - prev[0], cur[1] - prev[1]),) + self._edge_class(ctx, rc, prev, cur)
                if key is not None and k != key:
                    segs.append(self._make_seg(ctx, lay, start, prev, key[1], key[2]))
                    start = prev
                key = k
                prev = cur
            if key is not None:
                segs.append(self._make_seg(ctx, lay, start, prev, key[1], key[2]))

        for cur in cells[1:]:
            if cur[0] != layer:
                flush(run, layer)
                node = (cur[1], cur[2])
                if node not in free:
                    vias.append(self._make_via(ctx, node))
                layer = cur[0]
                run = [node]
            else:
                run.append((cur[1], cur[2]))
        flush(run, layer)
        return segs, vias

    def _stub_for(self, ctx: _NetCtx, p: _Pad, cell, att: _Attempt, rc: _RC
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
        hw, clr = self._edge_class(ctx, rc, (ix, iy), (ix, iy))
        if ctx.rct_out is not None and hw < ctx.out_hw - 1e-9 and \
                not self.fine_region.contains(Point(p.x, p.y)):
            hw, clr = ctx.out_hw, ctx.out_clr            # the stub would leave the area
        stub = self._make_stub(ctx, l, (ix, iy), p.x, p.y, hw, clr)
        if not self._pad_clear(stub, ctx.name) or self._victims([stub]):
            return None
        att.stubbed.add(key)
        return stub

    # -- one search -----------------------------------------------------------------
    def _search_path(self, ctx: _NetCtx, att: _Attempt, src: np.ndarray, dst: np.ndarray,
                     soft: bool, rc: _RC, win, *, tlayers: int = 0,
                     via_cost: Optional[int] = None, dst_bias: Optional[np.ndarray] = None,
                     heuristic: bool = True, vias_left: Optional[int] = None,
                     plane_sites: bool = False):
        """Cheapest path inside window ``win`` from the cells ``src`` to the
        cells ``dst`` (or to any cell of the layers ``tlayers``) for a track
        of class ``rc``.  ``dst_bias`` is an extra cost per destination cell.
        Returns (cells, segments, new vias) or None."""
        lsrc = self._to_local(src, win)
        ldst = self._to_local(dst, win)
        if len(lsrc) == 0 or (len(ldst) == 0 and not tlayers):
            return None
        hbox = None
        if heuristic and not tlayers and len(dst):
            iy0, iy1, ix0, ix1 = win
            xs = dst[:, 1] - ix0
            ys = dst[:, 2] - iy0
            ok = (xs >= 0) & (xs < ix1 - ix0) & (ys >= 0) & (ys < iy1 - iy0)
            hbox = (int(xs[ok].min()), int(ys[ok].min()), int(xs[ok].max()), int(ys[ok].max()))
        nv = 1
        if vias_left is not None and vias_left > 0:
            nv = vias_left + 1
        if via_cost is None:
            via_cost = self.via_cost
        ban: List[Any] = []
        for _round in range(6):
            cost, vmap, softl, softv = self._local(ctx, rc, win, soft, att, vias_left, ban,
                                                   plane_sites)
            if dst_bias is not None:
                # entering a destination cell costs extra (escape: distance from
                # that rim cell to where the net has to go)
                ly = dst[:, 2] - win[0]
                lx = dst[:, 1] - win[2]
                ok = (ly >= 0) & (ly < cost.shape[1]) & (lx >= 0) & (lx < cost.shape[2])
                ll, ly, lx = dst[ok, 0], ly[ok], lx[ok]
                cur = cost[ll, ly, lx]
                cost[ll, ly, lx] = np.where(
                    cur > 0, np.minimum(cur + dst_bias[ok], _COST_CAP), 0)
            path = self._run_search(cost, vmap, lsrc, ldst, tlayers, hbox, nv, via_cost)
            if len(path) == 0:
                return None
            if self.opt.smooth and len(path) > 2:
                path = _astar.smooth(path, cost, self.step_h, self.step_v, self.step_d, 400)
            cells = self._decode(path, win)
            marks = np.argwhere(vmap == FREE_VIA)
            free = {(int(x) + win[2], int(y) + win[0]) for y, x in marks}
            segs, vias = self._path_items(ctx, cells, free, rc)
            clash = None
            for i, a in enumerate(vias):
                for b in vias[i + 1:]:
                    if self._conflict(a, b):
                        clash = a
                        break
                if clash is not None:
                    break
            if clash is not None:
                ban.append(clash)                    # search again with room around it
                continue
            if soft:                                 # cells that ran over other nets' copper
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

    def _vias_left(self, ctx: _NetCtx) -> Optional[int]:
        if ctx.max_vias is None:
            return None
        used = sum(1 for it in self.net_items.get(ctx.name, ()) if it.is_via)
        return ctx.max_vias - used

    # -- what is connected to what inside one net ------------------------------------
    def _net_state(self, ctx: _NetCtx, skip_uid: int = -1, cells: bool = True) -> _NetState:
        """Connectivity of the routed copper of one net (leaving out unit
        ``skip_uid``): pads and units are joined where a unit's copper touches
        them.  With ``cells`` also the owner of every cell of that copper."""
        st = _NetState()
        parent = st.parent

        def find(x):
            root = x
            while parent.setdefault(root, root) != root:
                root = parent[root]
            while parent[x] != root:
                parent[x], x = root, parent[x]
            return root

        st.find = find
        st.units = [u for u in self.net_units.get(ctx.name, ())
                    if u.routed and u.uid != skip_uid]
        for u in st.units:
            ku = find(("u", u.uid))
            for pid in u.touch:
                parent[find(("p", pid))] = ku
                ku = find(ku)
            for dep in u.deps:
                parent[find(("u", dep))] = ku
                ku = find(ku)
            if u.kind == "escape" and u.cells:
                st.escaped.add(u.pads[0].idx)
        if cells:
            owner = st.owner
            for p in ctx.pads:
                kp = ("p", p.idx)
                for n in p.nodelist:
                    for l in p.lay:
                        owner[(l, n[0], n[1])] = kp
            for u in st.units:
                ku = ("u", u.uid)
                for c in u.cells:
                    owner.setdefault(c, ku)
                for it in u.items:
                    if it.is_via:
                        for l in range(self.L):
                            owner.setdefault((l, it.a[0], it.a[1]), ku)
        return st

    def _comp_cells(self, ctx: _NetCtx, st: _NetState, root, wide: bool) -> np.ndarray:
        """Cells (l, ix, iy) at which the component ``root`` can be entered:
        its pads (a pad with an escape only through that escape), the tracks
        of its units and their vias on every layer."""
        out: List[np.ndarray] = []
        for p in ctx.pads:
            if p.idx in st.escaped or st.find(("p", p.idx)) != root:
                continue
            out.append(self._pad_cells(p, wide))
        extra: List[Tuple[int, int, int]] = []
        for u in st.units:
            if st.find(("u", u.uid)) != root:
                continue
            extra.extend(u.cells)
            for it in u.items:
                if it.is_via:
                    extra.extend((l, it.a[0], it.a[1]) for l in range(self.L))
        if extra:
            out.append(np.array(extra, dtype=np.int64))
        if not out:
            return np.zeros((0, 3), dtype=np.int64)
        return np.concatenate(out, axis=0)

    def _touched(self, st: _NetState, cells, vias) -> Tuple[Set[int], Set[int]]:
        """(pads, units) of the net whose copper a new path touches."""
        owner = st.owner
        keys = set()
        for c in cells:
            k = owner.get(c)
            if k is not None:
                keys.add(k)
        for v in vias:
            for l in range(self.L):
                k = owner.get((l, v.a[0], v.a[1]))
                if k is not None:
                    keys.add(k)
        return ({k[1] for k in keys if k[0] == "p"}, {k[1] for k in keys if k[0] == "u"})

    def _end_stubs(self, ctx: _NetCtx, st: _NetState, cells, att: _Attempt, rc: _RC
                   ) -> List[_Seg]:
        """Stubs to off-grid pad centres at both ends of a path."""
        out = []
        for cell in (cells[0], cells[-1]):
            k = st.owner.get(cell)
            if k is not None and k[0] == "p":
                stub = self._stub_for(ctx, self.pads[k[1]], cell, att, rc)
                if stub is not None:
                    out.append(stub)
        return out

    # -- routing a connection ----------------------------------------------------------
    def _route_conn(self, unit: _Unit, soft: bool) -> Optional[_Attempt]:
        """Join the copper of pad a with the copper of pad b, wherever the
        two are closest - not necessarily at the pads themselves."""
        ctx = unit.ctx
        a, b = unit.pads
        att = _Attempt()
        st = self._net_state(ctx, unit.uid)
        ra, rb = st.find(("p", a.idx)), st.find(("p", b.idx))
        if ra == rb:
            att.trivial = True                       # other copper of the net does the job
            return att                               # (it claims nothing: see _unsatisfied)
        g = self.grid
        # full width first; the narrow width only where it is the last resort:
        # with other copper as a soft obstacle "no path" means no way at full
        # width at all, in a strict search only once the end game has given up
        # on the full width (unit.narrow)
        rcs = [ctx.rct]
        if unit.wide and ctx.rct_wide is not None:
            rcs = [ctx.rct_wide]                     # the widening pass: standard width or nothing
        elif ctx.rct_alt is not None and (soft or unit.narrow):
            rcs.append(ctx.rct_alt)
        m = int(math.ceil(self.opt.search_margin / g.pitch))
        na, nb = g.nearest(a.x, a.y), g.nearest(b.x, b.y)
        vias_left = self._vias_left(ctx)
        res = None
        rc = rcs[0]
        tries = []
        for full in (False, True):
            src = self._comp_cells(ctx, st, ra, full)
            dst = self._comp_cells(ctx, st, rb, full)
            if len(src) == 0 or len(dst) == 0:
                continue
            if full:
                win = (0, g.ny, 0, g.nx)
            else:
                win = (max(0, min(na[1], nb[1]) - m), min(g.ny, max(na[1], nb[1]) + m + 1),
                       max(0, min(na[0], nb[0]) - m), min(g.nx, max(na[0], nb[0]) + m + 1))
            tries.append((src, dst, win))
        for rc in rcs:
            for src, dst, win in tries:
                res = self._search_path(ctx, att, src, dst, soft, rc, win,
                                        vias_left=vias_left)
                if res is not None:
                    break
            if res is not None:
                break
        if res is None:
            unit.reason = "no path from %s to %s" % (a.key, b.key)
            return None
        cells, segs, vias = res
        att.touch, att.deps = self._touched(st, cells, vias)
        att.items = list(segs) + list(vias) + self._end_stubs(ctx, st, cells, att, rc)
        att.vias = list(vias)
        att.cells = list(cells)
        att.hw = rc.hw
        return att

    # -- routing a plane fan-out ---------------------------------------------------------
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
        ok_sites = self.plane_ok.get(ctx.name)
        share = []
        via_units: Dict[Tuple[int, int], int] = {}
        for it in self.net_items.get(ctx.name, ()):
            if not it.is_via or it.unit == unit.uid:
                continue
            via_units[it.a] = it.unit
            if ok_sites is not None and not ok_sites[it.a[1], it.a[0]]:
                continue                                 # that via is not on the plane
            if math.hypot(it.x - p.x, it.y - p.y) <= self.opt.plane_share_radius:
                for l in p.lay:
                    share.append((l, it.a[0], it.a[1]))
        share_arr = np.array(share, dtype=np.int64) if share else np.zeros((0, 3), dtype=np.int64)
        if tl == 0 and not share:
            unit.reason = "no layer to drop a via from pad %s" % p.key
            return None
        # stub width: the net's width, or the neck-down width for narrow pads
        rcs = [ctx.rct]
        if ctx.rct_alt is not None:
            dim = min(p.bbox[2] - p.bbox[0], p.bbox[3] - p.bbox[1])
            rcs = [ctx.rct_alt] if dim < ctx.width - 1e-9 else [ctx.rct, ctx.rct_alt]
        res = None
        rc = rcs[0]
        pts = [(int(c[1]), int(c[2])) for c in share_arr]
        for margin, wide in ((2.0, False), (5.0, True), (15.0, True)):
            src = self._pad_cells(p, wide)
            win = self._window(src, pts, margin, False)
            for rc in rcs:
                res = self._search_path(ctx, att, src, share_arr, soft, rc, win, tlayers=tl,
                                        via_cost=self.plane_via_cost, heuristic=False,
                                        vias_left=self._vias_left(ctx), plane_sites=True)
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
            found = False
            for c in cells:
                uid = via_units.get((c[1], c[2]))
                if uid is not None:
                    found = True
                    if uid >= 0:
                        att.deps.add(uid)
            if not found:
                unit.reason = "fan-out of %s found no via" % p.key
                return None
        stub = self._stub_for(ctx, p, cells[0], att, rc)
        if stub is not None:
            items.append(stub)
        att.items = items
        att.vias = list(vias)
        att.cells = list(cells)
        att.touch = {p.idx}
        att.hw = rc.hw
        return att

    # -- routing the escape of an array pad ------------------------------------------------
    def _route_escape(self, unit: _Unit, soft: bool) -> Optional[_Attempt]:
        """Route a pad inside an array's escape window out to the rim of the
        window, or onto copper of its net inside the window.

        What the pad needs depends on its net: if the net has pads outside the
        window, the pad's copper must reach the rim - directly, or by joining
        copper of the net that already does; a net that lives inside the
        window only is simply connected up."""
        ctx = unit.ctx
        p = unit.pads[0]
        att = _Attempt()
        st = self._net_state(ctx, unit.uid)
        if unit.targets is None:
            unit.targets = self._escape_targets(unit)         # prepared once per unit
        rim, bias, inside, has_outside = unit.targets
        root = st.find(("p", p.idx))
        mine = [u for u in st.units if st.find(("u", u.uid)) == root]
        need_rim = has_outside and not any(u.at_rim for u in mine)
        # copper of the net inside the window that this pad is not joined to yet
        roots: Dict[Any, bool] = {}
        for q in inside:
            rq = st.find(("p", q.idx))
            if rq != root:
                roots.setdefault(rq, False)
        for u in st.units:
            ru = st.find(("u", u.uid))
            if ru in roots and u.at_rim:
                roots[ru] = True
        # joining copper that is not on the rim either does not help a pad that
        # has to get out
        joinable = [r for r, on_rim in roots.items() if on_rim or not need_rim]
        if not need_rim and (mine or not joinable):
            att.trivial = True                                # nothing left to do for it
            return att
        cells = []
        extra = []
        if need_rim and len(rim):
            cells.append(rim)
            extra.append(bias)
        for r in joinable:
            rc_cells = self._comp_cells(ctx, st, r, True)
            if len(rc_cells):
                cells.append(rc_cells)
                extra.append(np.zeros(len(rc_cells), dtype=np.int64))
        if not cells:
            unit.reason = "no way out of the array for pad %s" % p.key
            return None
        dst = np.concatenate(cells, axis=0)
        dbias = np.concatenate(extra, axis=0)
        # The escape starts at ITS pad.  (It used to start anywhere on the copper
        # joined to the pad - also on another pad of the net that some other
        # unit had connected to this one.  When that unit was rerouted later,
        # the pad was left without copper while this unit still claimed it.)
        src = self._pad_cells(p, False)
        rcs = [ctx.rct]
        if ctx.rct_alt is not None:
            dim = min(p.bbox[2] - p.bbox[0], p.bbox[3] - p.bbox[1])
            rcs = [ctx.rct_alt] if dim < ctx.width - 1e-9 else [ctx.rct, ctx.rct_alt]
        res = None
        rc = rcs[0]
        for rc in rcs:
            res = self._search_path(ctx, att, src, dst, soft, rc, unit.win,
                                    via_cost=self.via_cost, dst_bias=dbias, heuristic=False,
                                    vias_left=self._vias_left(ctx))
            if res is not None:
                break
        if res is None:
            unit.reason = "no way out of the array for pad %s" % p.key
            return None
        path, segs, vias = res
        att.touch, att.deps = self._touched(st, path, vias)
        att.touch.add(p.idx)
        att.items = list(segs) + list(vias) + self._end_stubs(ctx, st, path, att, rc)
        att.vias = list(vias)
        att.cells = list(path)
        att.hw = rc.hw
        att.at_rim = tuple(path[-1]) in unit.rimset or \
            any(self.units[d].at_rim for d in att.deps)
        return att

    def _escape_targets(self, unit: _Unit):
        """What an escape aims for: the rim cells with their extra cost, the
        other pads of the net inside the window, and whether the net has
        pads outside it at all.

        A rim cell costs the distance from there to the nearest pad of the
        net outside the window (times ``escape_direction``), so that escapes
        leave toward where their net has to go."""
        g = self.grid
        ctx = unit.ctx
        p = unit.pads[0]
        iy0, iy1, ix0, ix1 = unit.win
        others = [q for q in ctx.pads if q is not p]
        rim = self._open_rim(unit)
        bias = np.zeros(len(rim), dtype=np.int64)
        w = max(0.0, self.opt.escape_direction)
        outside = [q for q in others
                   if not (g.x_of(ix0) < q.x < g.x_of(ix1 - 1)
                           and g.y_of(iy0) < q.y < g.y_of(iy1 - 1))]
        inside = [q for q in others if q not in outside]
        if outside and w > 0 and len(rim):
            xs = g.xs[rim[:, 1]]
            ys = g.ys[rim[:, 2]]
            dist = None
            for q in outside:
                dq = np.hypot(xs - q.x, ys - q.y)
                dist = dq if dist is None else np.minimum(dist, dq)
            bias = np.round(w * dist / g.pitch * STEP).astype(np.int64)
        return rim, bias, inside, bool(outside)

    def _open_rim(self, unit: _Unit) -> np.ndarray:
        """The rim cells of an escape window that are exits for this unit's
        net: the track can go on from there.  A rim cell is dropped when the
        ``escape_exit`` just beyond it, straight outward, is not all free for
        the net (a hole's exclusion zone, a pad of another net, the board
        edge, a keep-out, the frozen fan-out of another array) - an escape
        that ended there would be a dead end, and it is frozen once placed."""
        rim = unit.rim
        n = int(round(max(0.0, self.opt.escape_exit) / self.grid.pitch))
        if n <= 0 or len(rim) == 0:
            return rim
        g = self.grid
        ctx = unit.ctx
        iy0, iy1, ix0, ix1 = unit.win
        ext = (max(0, iy0 - n), min(g.ny, iy1 + n), max(0, ix0 - n), min(g.nx, ix1 + n))
        rc = ctx.rct_out if ctx.rct_out is not None else ctx.rct
        cost, _vmap, _softl, _softv = self._local_rc(ctx, rc, ext, True, _Attempt(), None)
        free = cost > 0
        keep = np.zeros(len(rim), dtype=bool)
        for i, (l, ix, iy) in enumerate(rim):
            l, ix, iy = int(l), int(ix), int(iy)
            dirs = []
            if ix == ix0:
                dirs.append((-1, 0))
            if ix == ix1 - 1:
                dirs.append((1, 0))
            if iy == iy0:
                dirs.append((0, -1))
            if iy == iy1 - 1:
                dirs.append((0, 1))
            for dx, dy in dirs:
                ok = True
                for k in range(1, n + 1):
                    x, y = ix + dx * k, iy + dy * k
                    if not (ext[2] <= x < ext[3] and ext[0] <= y < ext[1]) \
                            or not free[l, y - ext[0], x - ext[2]]:
                        ok = False
                        break
                if ok:
                    keep[i] = True
                    break
        if not keep.any():
            return rim                               # nowhere is good: no worse than before
        unit.rimset = set((int(a), int(b), int(c)) for a, b, c in rim[keep])
        return rim[keep]

    def _escape_sweep(self, units: Sequence[_Unit]) -> None:
        """Stage A book-keeping: a group of pads of one net inside the window
        whose copper does not reach the rim (although the net goes on outside)
        gets one of its escapes reopened - it will then head for the rim."""
        nets: Dict[str, List[_Unit]] = {}
        for u in units:
            if u.kind == "escape":
                nets.setdefault(u.ctx.name, []).append(u)
        for name in sorted(nets):
            ctx = self.ctx[name]
            for _guard in range(len(nets[name]) + 1):
                st = self._net_state(ctx, cells=False)
                groups: Dict[Any, List[_Unit]] = {}
                for u in nets[name]:
                    if u.routed:
                        groups.setdefault(st.find(("p", u.pads[0].idx)), []).append(u)
                on_rim = set()
                for u in st.units:
                    if u.at_rim:
                        on_rim.add(st.find(("u", u.uid)))
                reopened = False
                for root in sorted(groups, key=lambda r: min(u.uid for u in groups[r])):
                    group = groups[root]
                    if root in on_rim:
                        continue
                    if group[0].targets is None:
                        group[0].targets = self._escape_targets(group[0])
                    if not group[0].targets[3]:
                        continue                              # the net lives in the window
                    # the one that costs least to reopen: no copper, no dependents
                    pick = min(group, key=lambda u: (bool(u.items), len(u.dependents), u.uid))
                    self._rip(pick)
                    reopened = True
                    break
                if not reopened:
                    break

    # -- unit driver -------------------------------------------------------------------------
    def _route_unit(self, unit: _Unit, soft: bool) -> Optional[_Attempt]:
        """Route one unit; the returned attempt lists the units its copper
        conflicts with (``victims``; always empty for a strict route unless
        the maps are wrong)."""
        unit.attempts += 1
        unit.reason = ""
        if unit.kind == "conn":
            att = self._route_conn(unit, soft)
        elif unit.kind == "escape":
            att = self._route_escape(unit, soft)
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
        att.touch = set(unit.touch)
        att.cells = list(unit.cells)
        att.hw = unit.hw
        att.trivial = unit.trivial
        att.at_rim = unit.at_rim
        return att

    def _time_up(self) -> bool:
        return self.opt.time_limit is not None and \
            time.time() - self.t0 > self.opt.time_limit

    def _unsatisfied(self, units: Sequence[_Unit], optional_escapes: bool = True
                     ) -> List[_Unit]:
        """The units that still have work to do: fan-outs without a route and
        connections whose two pads are not joined by copper.  A connection
        that counts as routed but no longer joins its pads (the copper it
        relied on has moved) is ripped up here.  Escapes are optional helpers
        unless ``optional_escapes`` is off."""
        out: List[_Unit] = []
        by_net: Dict[str, List[_Unit]] = {}
        if not optional_escapes:
            self._escape_sweep(units)
        for u in units:
            if u.kind == "conn":
                by_net.setdefault(u.ctx.name, []).append(u)
            elif not u.routed and (u.kind == "fanout" or not optional_escapes):
                out.append(u)
        self._frozen_broken = []
        for name, conns in by_net.items():
            ctx = self.ctx[name]
            stuck: Set[int] = set()
            while True:
                st = self._net_state(ctx, cells=False)
                broken = None
                for u in conns:
                    if u.routed and u.uid not in stuck and \
                            st.find(("p", u.pads[0].idx)) != st.find(("p", u.pads[1].idx)):
                        broken = u
                        break
                if broken is None:
                    break
                if self._rip(broken):
                    continue
                # A frozen unit is not ripped by _rip().  One without copper (a
                # connection that only counted as made through other copper)
                # simply stops counting as routed; one with copper stays where it
                # is until it is unfrozen and is remembered in _frozen_broken.
                # Either way the loop moves on - it must never spin on a unit it
                # cannot change.
                if not broken.items:
                    self._drop_trivial(broken)
                else:
                    stuck.add(broken.uid)
                    self._frozen_broken.append(broken)
            out.extend(u for u in conns if not u.routed)
        out.sort(key=lambda u: (u.order, u.uid))
        return out

    def _drop_trivial(self, unit: _Unit) -> None:
        """Mark a connection that holds no copper (``trivial``: its pads were
        joined by other copper of the net) as not routed, frozen or not."""
        if unit.items:
            raise RoutingError("internal: %s holds copper" % unit.name)
        unit.frozen = False
        unit.routed = False
        unit.trivial = False
        unit.touch = set()
        unit.cells = []
        for dep in unit.deps:
            self.units[dep].dependents.discard(unit.uid)
        unit.deps = set()
        for other in self.conf.get(unit.uid, ()):
            self.conf[other].discard(unit.uid)
        self.conf[unit.uid] = set()

    def _negotiate(self, units: Sequence[_Unit], max_iterations: int, patience: int,
                   label: str = "", optional_escapes: bool = True,
                   start_price: Optional[float] = None) -> Tuple[Dict[int, str], int]:
        """Negotiated congestion routing of ``units``: every unit is routed
        with other nets' copper allowed at a price, then the units that
        conflict are routed again and again while the price of sharing and
        the history cost of contested cells go up.  Stops when nothing
        conflicts, after ``max_iterations`` rounds or when the number of open
        units has not improved for ``patience`` rounds (the best state seen is
        restored).  Conflicts that remain are left in ``self.conf``.

        Returns ({uid: reason} of the units that found no path at all,
        number of rounds)."""
        o = self.opt
        failed: Dict[int, str] = {}
        uset = {u.uid for u in units}
        pen = self.pen0
        if start_price is not None:
            pen = max(self.pen0, start_price / self.grid.pitch * STEP)
        pen_max = max(self.pen0, o.present_max / self.grid.pitch * STEP)
        iteration = 0
        best = None                              # (score, iteration, failed, snapshot)
        tag = (label + ": ") if label else ""
        while iteration < max(1, max_iterations) and not self._time_up():
            open_units = self._unsatisfied(units, optional_escapes)
            if iteration % 8 != 0:
                open_units = [u for u in open_units if not u.failed]    # hopeless ones rest
            todo = {u.uid: u for u in open_units}
            for u in units:
                if u.routed and self.conf[u.uid] and not u.frozen:
                    todo[u.uid] = u
            if not todo:
                break
            iteration += 1
            self.pen = max(1, int(round(min(pen, pen_max))))
            ordered = sorted(todo.values(), key=lambda u: (u.order, u.uid))
            if iteration % 2 == 0:
                ordered.reverse()                            # take turns in giving way
            queue = deque(ordered)
            pending = {u.uid for u in ordered}
            forced: Set[int] = set()
            while queue:
                if self._time_up():
                    break
                unit = queue.popleft()
                pending.discard(unit.uid)
                if unit.routed and not self.conf[unit.uid] and unit.uid not in forced:
                    continue                                 # its partner has moved away
                if unit.routed:
                    for other in self._rip(unit):
                        if other is not unit and other.uid in uset:
                            forced.add(other.uid)            # hung on this unit's copper
                            if other.uid not in pending:
                                queue.append(other)
                                pending.add(other.uid)
                att = self._route_unit(unit, soft=True)
                self.stats["reroutes"] += 1
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
            n_conf = sum(1 for u in units if u.routed and self.conf[u.uid] and not u.frozen)
            n_open = len(self._unsatisfied(units, optional_escapes))
            self.log("%siteration %d: %d unit(s) in conflict, %d open, price %d" % (
                tag, iteration, n_conf, n_open, self.pen))
            score = n_conf + n_open
            if not self._time_up() and (best is None or score < best[0]):
                best = (score, iteration, dict(failed), self._snapshot())
            elif best is not None and iteration - best[1] >= patience:
                self.log("%sno progress for %d iterations" % (tag, patience))
                break
            if score == 0:
                break
            pen *= o.present_growth
        if best is not None and best[1] != iteration:
            self.log("%sback to the state after iteration %d (%d open)" % (
                tag, best[1], best[0]))
            failed = dict(best[2])
            self._restore(best[3])
        return failed, iteration

    def _rip_conflicts(self, units: Sequence[_Unit], failed: Dict[int, str]) -> List[_Unit]:
        """Rip up whatever still conflicts, worst offender first; the ripped
        units are entered in ``failed``."""
        ripped: List[_Unit] = []
        while True:
            worst = None
            for u in units:
                n = len(self.conf[u.uid])
                if not n or not u.routed or u.frozen:
                    continue
                # the fan-out of an array goes last: ordinary copper gives way first
                key = (0 if u.array else 1, n, u.order)
                if worst is None or key > worst[0]:
                    worst = (key, u)
            if worst is None:
                break
            worst = worst[1]
            partners = sorted(self.units[v].name for v in self.conf[worst.uid])
            for u in self._rip(worst):
                u.rips += 1
                ripped.append(u)
                failed[u.uid] = "conflict with %s not resolved" % ", ".join(partners[:3])
        return ripped

    def run(self) -> "RouteResult":
        """Escape stage, negotiated routing, end game, cleanup and audit (see
        the module docstring)."""
        o = self.opt
        self.log("router: %d nets, grid %.3f mm (%d x %d), layers %s, kernel %s" % (
            len(self.routable), self.grid.pitch, self.grid.nx, self.grid.ny,
            "/".join(self.layers), "numba" if _astar.HAVE_NUMBA else "python"))
        self._escape_arrays()
        self._setup_units()
        self.log("main stage: %d unit(s)" % len(self.order))
        reasons: Dict[int, str] = {}
        self.stats.update({"iterations": 0, "ripups": 0, "endgame_placed": 0,
                           "plane_repairs": 0, "waves": 0})
        best = None                              # (open units, snapshot, reasons)
        stale = 0
        waves = max(1, o.waves)
        wave = -1
        while wave + 1 < waves:
            wave += 1
            # ---- negotiation; later waves start from the board as it is, with
            # the history forgotten and the price of sharing back at a moderate
            # level, so that the units still open push their way in ----
            failed, iteration = self._negotiate(
                self.order, o.max_iterations, o.patience, "" if wave == 0 else "wave %d" % (wave + 1),
                start_price=None if wave == 0 else o.reheat_price)
            self.stats["iterations"] += iteration
            self.stats["waves"] = wave + 1
            reasons.update(failed)
            # ---- whatever still conflicts is ripped up, worst offender first,
            # then only conflict-free copper is accepted (end game) ----
            self.stats["ripups"] += len(self._rip_conflicts(self.order, reasons))
            self.stats["endgame_placed"] += self._endgame(reasons)
            self._mend_planes(reasons)
            still_open = self._unsatisfied(self.order)
            n_open = len(still_open)
            self.log("wave %d done after %d iteration(s): %d unit(s) open" % (
                wave + 1, iteration, n_open))
            if best is None or n_open < best[0]:
                best = (n_open, self._snapshot(), dict(reasons))
                stale = 0
            else:
                stale += 1
            if n_open == 0 or self._time_up() or stale >= 2:
                break
            if all(u.uid in failed for u in still_open):
                # No path even across other nets' copper.  If the frozen fan-out
                # of an array is what walls them in, it is made negotiable again
                # (once) and gets one more wave; pads, edge and keep-outs stay.
                if self._thaw_arrays(still_open):
                    waves = max(waves, wave + 2)
                else:
                    break
            self.hist[:] = 0
        if best is not None and len(self._unsatisfied(self.order)) > best[0]:
            self.log("back to the best state (%d open)" % best[0])
            self._restore(best[1])
            reasons = dict(best[2])
        if self._unsatisfied(self.order) and not self._time_up():
            self._renegotiate_regions(reasons)
            self._mend_planes(reasons)
        # ---- improvement: plain shortest paths, one unit at a time.  Undone
        # if it costs a connection (a shorter track can cut a pad off its plane).
        self.hist[:] = 0
        open_before = len(self._unsatisfied(self.order))
        snap = self._snapshot()
        for i in range(max(0, o.improve_passes)):
            if self._time_up():
                break
            gain = self._improve()
            self.log("improve pass %d: %.1f mm / %d via(s) saved" % (i + 1, gain[0], gain[1]))
            if gain[0] < 0.05 and gain[1] == 0:
                break
        if o.improve_nets > 0 and not self._time_up():
            gain = self._improve_nets(o.improve_nets)
            self.log("net improvement: %d net(s) rerouted, %.1f mm / %d via(s) saved" % gain)
        if o.widen and not self._time_up():
            nets, mm = self._widen()
            if nets:
                self.log("widening: %d net(s) of fine classes, %.1f mm of fine track laid again "
                         "at the standard width" % (nets, mm))
        self._settle()
        self._mend_planes(reasons)
        if len(self._unsatisfied(self.order)) > open_before:
            self.log("improvement undone: it left more open than before")
            self._restore(snap)
        still = self._unsatisfied(self.order)
        self.failed = {u.name: reasons.get(u.uid) or u.reason or "not routed" for u in still}
        self._failed_net = {u.name: u.ctx.name for u in still}
        return self._finish()

    def _thaw_arrays(self, open_units: Sequence[_Unit]) -> bool:
        """Unfreeze the fan-out of stage A (see ``escape_freeze``) when units
        are still open that have no path at all: frozen copper is a hard
        obstacle, and a fan-out can - rarely - wall in a neighbouring pad.
        Thawed copper takes part in the negotiation again, only more expensive
        to run over.  Done at most once; returns True if anything was thawed."""
        if getattr(self, "_thawed", False):
            return False
        frozen = [u for u in self.units if u.frozen]
        if not frozen:
            return False
        self._thawed = True
        for u in frozen:
            self._unfreeze(u)
        self.stats["thawed"] = len(frozen)
        self.log("%d unit(s) have no path at all (%s): the frozen fan-out of the arrays (%d "
                 "unit(s)) is made negotiable again" % (
                     len(open_units), ", ".join(u.name for u in open_units[:3]), len(frozen)))
        return True

    def _renegotiate_regions(self, reasons: Dict[int, str]) -> None:
        """Last resort for the units that are still open: for each of them,
        everything routed in a window around it is ripped up and negotiated
        again as one small puzzle against the rest of the board, which is
        frozen meanwhile.  Kept only if fewer units are open afterwards."""
        o = self.opt
        hopeless: Set[int] = set()
        for margin in o.region_margins:
            pending = [u for u in self._unsatisfied(self.order) if u.kind != "escape"]
            for unit in pending[:max(0, o.region_tries)]:
                if unit.routed or self._time_up() or unit.uid in hopeless:
                    continue
                # Moving other nets' copper only helps a unit that has a way
                # over that copper.  One that has none even then is walled in by
                # pads, edge, keep-outs or frozen copper: no puzzle to solve.
                if self._route_unit(unit, soft=True) is None:
                    hopeless.add(unit.uid)
                    self.log("region around %s skipped: no path even across other nets' "
                             "copper (%s)" % (unit.name, unit.reason or "blocked"))
                    reasons[unit.uid] = unit.reason or reasons.get(unit.uid, "no path")
                    continue
                if self._renegotiate_region(unit, margin):
                    reasons.pop(unit.uid, None)
            if not self._unsatisfied(self.order) or self._time_up():
                break

    def _renegotiate_region(self, unit: _Unit, margin: float) -> bool:
        o = self.opt
        xs = [p.x for p in unit.pads]
        ys = [p.y for p in unit.pads]
        x0, y0, x1, y1 = min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin
        region: Set[int] = set()
        for u in self.units:
            if not u.routed or u.frozen or not u.items:
                continue
            for it in u.items:
                bb = it.bbox()
                if bb[2] >= x0 and bb[0] <= x1 and bb[3] >= y0 and bb[1] <= y1:
                    region.add(u.uid)
                    break
        stack = list(region)
        while stack:                                         # what hangs on them goes too
            for d in self.units[stack.pop()].dependents:
                if d not in region and not self.units[d].frozen:
                    region.add(d)
                    stack.append(d)
        # Connections that hold no copper of their own ("trivial": their pads are
        # joined by other copper of the net) depend on that copper without being
        # recorded as dependents.  Those of the nets the region touches belong
        # to the puzzle: they are reopened with it and routed again.
        nets = {self.units[uid].ctx.name for uid in region}
        for u in self.units:
            if u.routed and not u.frozen and not u.items and u.kind == "conn" \
                    and u.ctx.name in nets:
                region.add(u.uid)
        open_before = self._unsatisfied(self.order)
        snap = self._snapshot()
        # only copper can be frozen: a unit without items has nothing to protect,
        # and a frozen unit cannot be reopened when what it relied on has moved
        outside = [u for u in self.units
                   if u.routed and not u.frozen and u.items and u.uid not in region]
        for u in outside:
            self._freeze(u)
        for uid in sorted(region):
            self._rip(self.units[uid])
        todo = {u.uid: u for u in open_before}
        for uid in region:
            todo[uid] = self.units[uid]
        todo_list = sorted(todo.values(), key=lambda u: (u.order, u.uid))
        self.log("region around %s (%.1f mm margin): %d unit(s) renegotiated" % (
            unit.name, margin, len(todo_list)))
        self.hist[:] = 0
        failed, _its = self._negotiate(todo_list, o.region_iterations, o.region_patience,
                                       "region")
        self._rip_conflicts(todo_list, failed)
        self.hist[:] = 0
        for u in todo_list:                                  # strict second chance
            if not u.routed and u.kind != "escape" and not self._time_up():
                att = self._route_unit(u, soft=False)
                if att is not None and not att.victims:
                    self._commit(u, att)
        # frozen connections that no longer join their pads count as open too
        # (they cannot be ripped while frozen, see _unsatisfied)
        open_after = len(self._unsatisfied(self.order)) + len(self._frozen_broken)
        better = open_after < len(open_before)
        if not better:
            self._restore(snap)                              # (frozen units stay as they are)
        for u in outside:
            self._unfreeze(u)
        self.log("region around %s: %s" % (unit.name, "kept" if better else "undone"))
        return better and unit.routed

    def _mend_planes(self, reasons: Dict[int, str]) -> None:
        """Pads cut off from their plane by other copper get a real track
        (see :meth:`_repair_planes`), placed by the end game."""
        for _round in range(max(0, self.opt.plane_repair_rounds)):
            if self._time_up():
                break
            added = self._repair_planes()
            if not added:
                break
            self.stats["plane_repairs"] += added
            self.stats["endgame_placed"] += self._endgame(reasons)

    def _endgame(self, reasons: Dict[int, str]) -> int:
        """Only conflict-free copper is accepted here.  An open unit may
        displace others if they all find a clean path again (bounded cascade,
        see :meth:`_force`); otherwise the board goes back to how it was.
        Returns the number of units placed."""
        o = self.opt
        pen_max = max(self.pen0, o.present_max / self.grid.pitch * STEP)
        self.pen = max(1, int(round(pen_max)))
        forced = 0
        for _round in range(max(1, o.endgame_rounds)):
            pending = self._unsatisfied(self.order)
            if not pending:
                break
            self.log("end game round %d: %d unit(s) open" % (_round + 1, len(pending)))
            progress = False
            waiting = {p.idx for u in pending if u.kind == "conn" for p in u.pads}
            for unit in self.order:                          # lost escapes first
                if unit.kind == "escape" and not unit.routed and not self._time_up() \
                        and unit.pads[0].idx in waiting:
                    att = self._route_unit(unit, soft=False)
                    if att is not None and not att.victims:
                        self._commit(unit, att)
            for unit in pending:
                if unit.routed:
                    continue                                 # placed along the way
                if self._time_up():
                    reasons.setdefault(unit.uid, "time limit reached")
                    continue
                placed = self._place(unit)
                if placed:
                    reasons.pop(unit.uid, None)
                    progress = True
                    forced += 1
                else:
                    reasons[unit.uid] = unit.reason or reasons.get(unit.uid, "no clean path")
                    unit.failed = True
            if not progress:
                break
        return forced

    def _place(self, unit: _Unit) -> bool:
        """Place one open unit with clean copper, pushing others aside if need
        be (:meth:`_force`; several tries, each undone if it does not work
        out); a connection of a class with ``min_track_width`` may neck down
        as the last resort."""
        o = self.opt
        depth = max(0, o.ripup_depth)
        modes = [False]
        if unit.ctx.rct_alt is not None and unit.kind == "conn" and not unit.narrow:
            modes.append(True)                       # last resort: neck the connection down
        for narrow in modes:
            unit.narrow = unit.narrow or narrow
            for _try in range(o.endgame_tries if depth else 1):
                snap = self._snapshot() if depth else None
                self._forced_cells = []
                self._force_left = max(1, o.ripup_budget)
                if self._force(unit, depth, frozenset()):
                    return True
                if snap is not None:
                    self._restore(snap)
                # make the next try look elsewhere: the cells where this one ran
                # over other nets get more expensive
                for (l, ix, iy) in self._forced_cells:
                    self.hist[l, iy, ix] = min(int(self.hist[l, iy, ix]) + 4, 1000)
                if not self._forced_cells or self._time_up():
                    break
            if self._time_up():
                break
        return False

    def _repair_planes(self) -> int:
        """Find pads of plane nets that the plane fill will not reach (their
        via sits in a pocket cut off by other nets' tracks or via clearances,
        see :func:`plane_regions`) and add a connection from each cut-off
        group to the main part.  Returns the number of connections added."""
        nets: Dict[str, List[str]] = {}
        for layer, net in self.design.full_plane_layers().items():
            ctx = self.ctx.get(net)
            if ctx is not None and ctx.plane and ctx.rct is not None:
                nets.setdefault(net, []).append(layer)
        if not nets:
            return 0
        tracks, vias = self._emit()
        added = 0
        last = max([u.order for u in self.order] + [0])
        for net in sorted(nets):
            ctx = self.ctx[net]
            st = self._net_state(ctx, cells=False)
            find, parent = st.find, st.parent
            for layer in nets[net]:
                regions = plane_regions(self.design, layer, net, tracks, vias)
                for u in st.units:
                    for it in u.items:
                        if it.is_via:
                            k = _region_index(regions, it.x, it.y)
                            if k is not None:
                                parent[find(("u", u.uid))] = find(("r", layer, k))
                for p in ctx.pads:
                    if layer in p.cu:
                        k = _region_index(regions, p.x, p.y)
                        if k is not None:
                            parent[find(("p", p.idx))] = find(("r", layer, k))
            groups: Dict[Any, List[_Pad]] = {}
            for p in ctx.pads:
                groups.setdefault(find(("p", p.idx)), []).append(p)
            if len(groups) <= 1:
                continue
            ordered = sorted(groups.values(), key=lambda g: (-len(g), g[0].idx))
            main = ordered[0]
            for group in ordered[1:]:
                best = min((math.hypot(a.x - b.x, a.y - b.y), a.idx, b.idx, a, b)
                           for a in group for b in main)
                u = self._new_unit("conn", ctx, [best[3], best[4]])
                u.length = best[0]
                last += 1
                u.order = last
                self.order.append(u)
                added += 1
                self.log("plane %s: %s is cut off from the plane - adding a track to %s" % (
                    net, ", ".join(p.key for p in group[:4]), best[4].key))
        return added

    def _settle(self) -> None:
        """Last sweep: whatever is open gets one more strict try (cheap; it
        catches connections that only counted as made through copper that has
        since been rerouted)."""
        for _round in range(3):
            pending = self._unsatisfied(self.order)
            progress = False
            for unit in pending:
                if unit.routed or self._time_up():
                    continue
                att = self._route_unit(unit, soft=False)
                if att is not None and not att.victims:
                    self._commit(unit, att)
                    progress = True
            if not progress:
                break

    def _force(self, unit: _Unit, depth: int, locked: frozenset) -> bool:
        """Place ``unit`` with clean copper.  If it has no clean path and
        ``depth`` allows, lay it over other units, rip those up and place them
        again the same way.  Returns False when that fails somewhere - the
        caller then restores its snapshot."""
        self._force_left -= 1
        att = self._route_unit(unit, soft=False)
        if att is not None and not att.victims:
            self._commit(unit, att)
            return True
        if depth <= 0 or self._force_left <= 0:
            return False
        att = self._route_unit(unit, soft=True)
        if att is None:
            return False
        self._forced_cells.extend(att.hist)
        victims = [self.units[v] for v in sorted(att.victims)]
        if not victims or any(v.uid in locked or v.frozen for v in victims):
            return False
        ripped: List[_Unit] = []
        for v in victims:
            ripped.extend(self._rip(v))
        if any(v.uid in locked for v in ripped):
            return False
        left = self._victims(att.items)
        left.discard(unit.uid)
        if left or any(not self.units[d].routed for d in att.deps):
            return False
        self._commit(unit, att)
        locked = locked | {unit.uid}
        for v in sorted(ripped, key=lambda u: (u.order, u.uid)):
            if v.routed:
                continue
            if not self._force(v, depth - 1, locked):
                unit.reason = "no clean path; pushing %s aside did not work either" % v.name
                return False
        return True

    def _snapshot(self) -> Dict[str, Any]:
        """Remember the routed copper and conflicts of every unit."""
        return {"units": {u.uid: self._as_attempt(u) for u in self.units if u.routed},
                "conf": {uid: set(v) for uid, v in self.conf.items()},
                "narrow": {u.uid: u.narrow for u in self.units},
                "n_units": len(self.units), "order": list(self.order)}

    def _restore(self, snap: Dict[str, Any]) -> None:
        """Go back to a state saved by :meth:`_snapshot`."""
        for u in self.units:
            if u.routed and not u.frozen:
                self._rip(u)
        n = snap["n_units"]
        if len(self.units) > n:                  # units made since (plane repairs) go
            del self.units[n:]
            self.order = list(snap["order"])
            for name in self.net_units:
                self.net_units[name] = [u for u in self.net_units[name] if u.uid < n]
        for u in sorted(self.units, key=lambda v: (v.order, v.uid)):
            u.narrow = snap["narrow"].get(u.uid, False)
            att = snap["units"].get(u.uid)
            if att is not None and not u.frozen:
                self._commit(u, att)
        self.conf = {uid: set(v) for uid, v in snap["conf"].items() if uid < n}
        for u in self.units:
            self.conf.setdefault(u.uid, set())

    # -- improvement -------------------------------------------------------------
    def _score(self, unit: _Unit, att: _Attempt) -> float:
        """What a route costs, in mm of track: length, vias and - for an
        escape - how far its end is from where the net has to go."""
        length = sum(it.length for it in att.items if not it.is_via)
        vias = sum(1 for it in att.items if it.is_via)
        score = length + self.opt.via_cost * vias
        if unit.kind == "escape" and att.cells and unit.targets is not None:
            dst, bias = unit.targets[0], unit.targets[1]
            end = att.cells[-1]
            hit = np.nonzero((dst[:, 0] == end[0]) & (dst[:, 1] == end[1])
                             & (dst[:, 2] == end[2]))[0] if len(dst) else []
            if len(hit):
                score += float(bias[hit[0]]) * self.grid.pitch / STEP
        return score

    def _improve(self, units: Optional[Sequence[_Unit]] = None) -> Tuple[float, int]:
        """Rip each unit once and route it again with everything else in
        place; keep the better of the two.  Returns (mm, vias) saved."""
        saved_len, saved_vias = 0.0, 0
        for unit in (self.order if units is None else units):
            if not unit.routed or unit.dependents or unit.trivial or not unit.items:
                continue
            if unit.kind == "fanout" or unit.frozen:
                continue
            if self._time_up():
                break
            before = self._as_attempt(unit)
            old = self._score(unit, before)
            self._rip(unit)
            att = self._route_unit(unit, soft=False)
            if att is not None and not att.victims and self._score(unit, att) < old - 1e-9:
                self._commit(unit, att)
                a, b = self._unit_cost(before.items), self._unit_cost(att.items)
                saved_len += a[0] - b[0]
                saved_vias += a[1] - b[1]
            else:
                self._commit(unit, before)
        return saved_len, saved_vias

    def _improve_nets(self, ratio: float) -> Tuple[int, float, int]:
        """Take a whole net off the board and route it again, connection by
        connection, with everything else in place: the detours a net made
        while the board was being negotiated are often not needed any more,
        and :meth:`_improve` cannot touch a connection other copper of the net
        hangs on.  Tried for every net whose track is longer than ``ratio``
        times its spanning tree or that has more vias than pads, worst first;
        kept only if every connection is made again and the net got cheaper.
        Returns (nets rerouted, mm saved, vias saved)."""
        cands = []
        for ctx in self.routable:
            if ctx.plane:
                continue
            units = [u for u in self.net_units.get(ctx.name, ()) if u.kind == "conn"]
            if not units or any(u.frozen or not u.routed for u in units):
                continue
            items = [it for u in units for it in u.items]
            length, nvias = self._unit_cost(items)
            tree = sum(u.length for u in units)
            if tree < 0.5:
                continue
            if length > ratio * tree + 1.0 or nvias > len(ctx.pads):
                cands.append((-(length + self.opt.via_cost * nvias - tree), ctx.name, ctx, units,
                              length, nvias))
        done, saved_len, saved_vias = 0, 0.0, 0
        for _key, _name, ctx, units, length, nvias in sorted(cands, key=lambda c: c[:2]):
            if self._time_up():
                break
            if any(not u.routed for u in units):
                continue
            # units of other kinds that hang on these connections would be ripped
            # with them: leave such a net alone
            mine = {u.uid for u in units}
            if any(d not in mine for u in units for d in u.dependents):
                continue
            before = [(u, self._as_attempt(u)) for u in units]
            old = length + self.opt.via_cost * nvias
            for u in units:
                if u.routed:
                    self._rip(u)
            ok = True
            for u in sorted(units, key=lambda v: (v.length, v.uid)):
                att = self._route_unit(u, soft=False)
                if att is None or att.victims:
                    ok = False
                    break
                self._commit(u, att)
            new_len, new_vias = self._unit_cost([it for u in units for it in u.items])
            if ok and new_len + self.opt.via_cost * new_vias < old - 0.05:
                done += 1
                saved_len += length - new_len
                saved_vias += nvias - new_vias
                continue
            for u in units:                            # put the old copper back
                if u.routed:
                    self._rip(u)
            for u, att in before:
                self._commit(u, att)
        return done, saved_len, saved_vias

    def _widen(self, passes: int = 3) -> Tuple[int, float]:
        """Lay the connections of unconfined fine-class nets again at the
        standard width and clearance wherever they find room (see the
        ``widen`` option).  Net by net: all its connections are taken off,
        each is routed with the standard class first and with its fine class
        only if that fails; the result is kept if every connection is made
        again, fine track became less, and the net did not get much longer or
        via-heavier.  Repeated (a net that has moved out of a bundle makes
        room for its neighbours) until a pass changes nothing.  Returns (nets
        changed, mm of fine track removed)."""
        changed: Set[str] = set()
        saved = 0.0

        def fine_len(units, ctx):
            return sum(it.length for u in units for it in u.items
                       if not it.is_via and it.hw < ctx.rct_wide.hw - 1e-9)

        for _pass in range(max(1, passes)):
            progress = False
            for ctx in self.routable:
                if ctx.rct_wide is None or ctx.plane:
                    continue
                if self._time_up():
                    break
                units = [u for u in self.net_units.get(ctx.name, ()) if u.kind == "conn"]
                if not units or any(u.frozen or not u.routed for u in units):
                    continue
                mine = {u.uid for u in units}
                if any(d not in mine for u in units for d in u.dependents):
                    continue
                old_fine = fine_len(units, ctx)
                if old_fine < 0.5:
                    continue
                before = [(u, self._as_attempt(u)) for u in units]
                length, nvias = self._unit_cost([it for u in units for it in u.items])
                old_cost = length + self.opt.via_cost * nvias
                for u in units:
                    if u.routed:
                        self._rip(u)
                ok = True
                for u in sorted(units, key=lambda v: (v.length, v.uid)):
                    if self.virtual_fine:
                        # fine near the arrays, the standard class beyond: the
                        # net is routed like a confined one for this attempt
                        ctx.rct_out = ctx.rct_wide
                        ctx.out_hw, ctx.out_clr = ctx.rct_wide.hw, ctx.rct_wide.clr
                        try:
                            att = self._route_unit(u, soft=False)
                        finally:
                            ctx.rct_out = None
                            ctx.out_hw, ctx.out_clr = ctx.hw, ctx.cls_clr
                    else:
                        u.wide = True                  # no array: all of it or nothing
                        att = self._route_unit(u, soft=False)
                        u.wide = False
                    if att is None or att.victims:
                        att = self._route_unit(u, soft=False)   # its own (fine) class
                    if att is None or att.victims:
                        ok = False
                        break
                    self._commit(u, att)
                new_len, new_vias = self._unit_cost([it for u in units for it in u.items])
                new_cost = new_len + self.opt.via_cost * new_vias
                new_fine = fine_len(units, ctx)
                if ok and new_fine < old_fine - 0.5 and new_cost <= 1.3 * old_cost + 2.0:
                    changed.add(ctx.name)
                    saved += old_fine - new_fine
                    progress = True
                    continue
                for u in units:                        # put the old copper back
                    if u.routed:
                        self._rip(u)
                for u, att in before:
                    self._commit(u, att)
            if not progress or self._time_up():
                break
        if changed:
            self.stats["widened_nets"] = len(changed)
            self.stats["widened_mm"] = round(saved, 3)
        return len(changed), saved

    def _unit_cost(self, items: Sequence[Any]) -> Tuple[float, int]:
        length = sum(it.length for it in items if not it.is_via)
        vias = sum(1 for it in items if it.is_via)
        return length, vias

    # -- output --------------------------------------------------------------------
    def _finish(self) -> "RouteResult":
        tracks, vias = self._emit()
        aud = audit(self.design, tracks, vias)
        if self.opt.straighten and self.stats.get("corners_cut") and not aud.ok:
            # the diagonals are checked one by one, but the audit has the last
            # word: if the straightened copper is not clean, the plain one is used
            plain = self._emit(straighten=False)
            aud_plain = audit(self.design, plain[0], plain[1])
            if len(aud_plain.violations) < len(aud.violations) or \
                    aud_plain.missing < aud.missing:
                self.log("straightening undone: the audit prefers the plain copper")
                tracks, vias, aud = plain[0], plain[1], aud_plain
                self.stats["corners_cut"] = 0
        # a unit that stayed open although its net is connected (a fan-out that
        # a track replaced, say) is no failure
        open_nets = {u.net for u in aud.unrouted}
        self.failed = {name: reason for name, reason in self.failed.items()
                       if self._failed_net.get(name) in open_nets}
        # every open net carries the reasons of its units, so that
        # ``for u in result.unrouted: print(u.net, u.pieces, u.reason)`` says why
        why: Dict[str, List[str]] = {}
        for name, reason in sorted(self.failed.items()):
            reasons = why.setdefault(self._failed_net.get(name, ""), [])
            if reason not in reasons:
                reasons.append(reason)
        for u in aud.unrouted:
            if not u.reason:
                u.reason = "; ".join(why.get(u.net, [])) or \
                    "not connected by the final copper (no unit reported a failure)"
        quality = net_quality(self.design, tracks, vias)
        for line in quality["warnings"]:
            self.log("look at " + line)
        length: Dict[str, float] = {}
        for t in tracks:
            length[t.layer] = length.get(t.layer, 0.0) + t.length
        self.stats.update({
            "nets": len(self.routable),
            "units": len(self.order),
            "grid_mm": self.grid.pitch,
            "grid_nodes": [self.grid.nx, self.grid.ny],
            "routing_layers": list(self.layers),
            "plane_nets": dict(sorted(self.plane_of.items())),
            "kernel": "numba" if _astar.HAVE_NUMBA else "python",
            "track_length_mm": round(sum(length.values()), 3),
            "track_length_by_layer_mm": {k: round(v, 3) for k, v in sorted(length.items())},
            "tracks": len(tracks), "vias": len(vias),
            "quality": quality,
            "runtime_s": round(time.time() - self.t0, 2),
        })
        res = RouteResult(tracks, vias, aud, dict(self.stats), dict(getattr(self, "failed", {})))
        self.log(res.summary())
        return res

    def _emit(self, straighten: Optional[bool] = None) -> Tuple[List[Track], List[Via]]:
        """Final cleanup and conversion to model primitives.

        Per net: duplicate, dangling and looping track pieces go
        (:func:`cleanup_segments`); a narrow piece that lies on a wider track
        of the net goes; two units' stubs into the same pad become one; and so
        does a via that no longer joins two things (an escape via whose way on
        was never used, a plane via outside its plane) - then the cleanup runs
        again, because the track into that via now dangles.  With
        ``straighten`` (default: the option of that name) one-step staircases
        become diagonals where an exact check allows it (:meth:`_straighten`)."""
        g = self.grid
        if straighten is None:
            straighten = self.opt.straighten
        per_net: List[Tuple[str, Dict[float, List[Any]], List[Any], List[Tuple[int, int]]]] = []
        for name in self.design.nets:
            items = self.net_items.get(name, [])
            if not items:
                continue
            ctx = self.ctx[name]
            # one stub per (layer, node, pad centre): the widest of its copies
            stub_map: Dict[Any, _Seg] = {}
            for it in items:
                if not it.is_via and it.b is None:
                    key = (it.layer, it.a, round(it.x2, 6), round(it.y2, 6))
                    old = stub_map.get(key)
                    if old is None or it.hw > old.hw + 1e-9:
                        stub_map[key] = it
            stubs = [stub_map[k] for k in sorted(stub_map)]
            vset = {it.a for it in items if it.is_via}
            plane_ok = self.plane_ok.get(name) if ctx.plane else None
            base: Set[Tuple[int, int, int]] = set()
            pad_layers: Dict[Tuple[int, int], Set[int]] = {}
            for p in ctx.pads:
                for n in p.nodelist:
                    pad_layers.setdefault(n, set()).update(p.lay)
                    for l in p.lay:
                        base.add((l, n[0], n[1]))
            for st in stubs:
                base.add((st.layer, st.a[0], st.a[1]))
            # unit edges per width; an edge two units laid at different widths
            # keeps the wider one only
            edge_w: Dict[Tuple[int, Tuple[int, int], Tuple[int, int]], float] = {}
            for it in items:
                if it.is_via or it.b is None:
                    continue
                width = round(2.0 * it.hw, 6)
                nodes = self._seg_nodes(it)
                for a, b in zip(nodes, nodes[1:]):
                    key = (it.layer, a, b) if a < b else (it.layer, b, a)
                    if edge_w.get(key, 0.0) < width:
                        edge_w[key] = width
            groups: Dict[float, List[Any]] = {}
            for (layer, a, b), width in edge_w.items():
                groups.setdefault(width, []).append((layer, a, b))
            covered: Dict[float, Set[Tuple[int, int, int]]] = {}
            if len(groups) > 1:
                # tracks of different width are cleaned up separately: where one
                # ends on another (end to end or in a T) both keep that node
                for width, segs in groups.items():
                    nodes_w: Set[Tuple[int, int, int]] = set()
                    for layer, a, b in segs:
                        nodes_w.add((layer, a[0], a[1]))
                        nodes_w.add((layer, b[0], b[1]))
                    covered[width] = nodes_w
            cleaned: Dict[float, List[Any]] = {}
            for _pass in range(6):
                anchors = set(base)
                for v in vset:
                    for l in range(self.L):
                        anchors.add((l, v[0], v[1]))
                cleaned = {}
                for width in sorted(groups):
                    other: Set[Tuple[int, int, int]] = set()
                    for w2, nodes_w in covered.items():
                        if w2 != width:
                            other |= nodes_w
                    joints = (covered.get(width, set()) & other) if other else set()
                    cleaned[width] = cleanup_segments(groups[width], anchors | joints,
                                                      set(vset), self.L, breaks=joints)
                # what does each via join?  track ends per layer, pad copper, the plane
                joined: Dict[Tuple[int, int], Set[Any]] = {v: set() for v in vset}
                for segs in cleaned.values():
                    for layer, a, b in segs:
                        for n in (a, b):
                            if n in joined:
                                joined[n].add(layer)
                for st in stubs:
                    if st.a in joined:
                        joined[st.a].add(st.layer)
                for v in vset:
                    joined[v].update(pad_layers.get(v, ()))
                    if plane_ok is not None and plane_ok[v[1], v[0]]:
                        joined[v].add("plane")       # (a via outside the plane joins nothing)
                dead = [v for v in vset if len(joined[v]) < 2]
                if not dead:
                    break
                vset -= set(dead)
            per_net.append((name, cleaned, stubs, sorted(vset)))
        if straighten:
            self._straighten(per_net)
        tracks: List[Track] = []
        vias: List[Via] = []
        for name, cleaned, stubs, vlist in per_net:
            ctx = self.ctx[name]
            for width in sorted(cleaned):
                for layer, a, b in cleaned[width]:
                    x1, y1 = g.xy(*a)
                    x2, y2 = g.xy(*b)
                    tracks.append(Track(name, self.layers[layer], x1, y1, x2, y2, width))
            for st in stubs:
                tracks.append(Track(name, self.layers[st.layer], round(st.x1, 6),
                                    round(st.y1, 6), round(st.x2, 6), round(st.y2, 6),
                                    round(2.0 * st.hw, 6)))
            for v in vlist:
                x, y = g.xy(*v)
                vias.append(Via(name, x, y, ctx.via_d, ctx.via_drill))
        return tracks, vias

    def _straighten(self, per_net) -> int:
        """Replace one-step staircases and jogs by diagonals.

        The search may not cut corners (a diagonal move needs all four nodes
        of its unit square free), so a track that runs diagonally at the limit
        distance to something becomes a chain of alternating one-step
        horizontal and vertical pieces.  Here every corner between two
        perpendicular grid steps of one width - at least one of them a single
        step, the corner node carrying nothing else - is cut by the diagonal
        if an EXACT check of that diagonal against all other copper, pads,
        holes, edge and keep-outs passes.  ``per_net`` (name, {width:
        segments}, stubs, vias) is rewritten in place; returns the number of
        corners cut."""
        g = self.grid
        r = self.rules
        index = _Index(0.5)

        class _Rec:                                    # a final track piece / via of some net
            __slots__ = ("net", "layer", "x1", "y1", "x2", "y2", "hw", "clr", "alive", "via",
                         "R", "drill")

            def bbox(self):
                e = max(self.hw, self.R)
                return (min(self.x1, self.x2) - e, min(self.y1, self.y2) - e,
                        max(self.x1, self.x2) + e, max(self.y1, self.y2) + e)

        def record(net, layer, x1, y1, x2, y2, hw, clr, via=False, R=0.0, drill=0.0):
            t = _Rec()
            t.net, t.layer, t.x1, t.y1, t.x2, t.y2 = net, layer, x1, y1, x2, y2
            t.hw, t.clr, t.via, t.R, t.drill = hw, clr, via, R, drill
            index.add(t)
            return t

        def piece_clr(ctx, width):
            """Clearance class of a track piece of this width (the wider one
            for the standard-width pieces of a confined net: safe wherever
            they are)."""
            if ctx.rct_out is not None and width / 2.0 >= ctx.out_hw - 1e-9:
                return ctx.out_clr
            return ctx.cls_clr

        def add_records(name, cleaned):
            ctx = self.ctx[name]
            out = []
            for width, segs in cleaned.items():
                clr = piece_clr(ctx, width)
                for layer, a, b in segs:
                    x1, y1 = g.xy(*a)
                    x2, y2 = g.xy(*b)
                    out.append(record(name, layer, x1, y1, x2, y2, width / 2.0, clr))
            return out

        track_recs: Dict[str, List[Any]] = {}
        for name, cleaned, stubs, vlist in per_net:
            ctx = self.ctx[name]
            track_recs[name] = add_records(name, cleaned)
            for st in stubs:
                record(name, st.layer, st.x1, st.y1, st.x2, st.y2, st.hw, st.cls_clr)
            for v in vlist:
                x, y = g.xy(*v)
                record(name, -1, x, y, x, y, 0.0, ctx.via_clr, True, ctx.via_d / 2.0,
                       ctx.via_drill)

        def clear(name, layer, a, c, hw, clr) -> bool:
            x1, y1 = g.xy(*a)
            x2, y2 = g.xy(*c)
            probe = _Seg()
            probe.net, probe.layer, probe.a, probe.b = name, layer, a, c
            probe.x1, probe.y1, probe.x2, probe.y2 = x1, y1, x2, y2
            probe.hw, probe.cls_clr, probe.exact = hw, clr, True
            if not self._pad_clear(probe, name):       # pads, edge, keep-outs, holes
                return False
            seg = (x1, y1, x2, y2)
            for o in index.query(probe.bbox(), 1.0):
                if o.net == name:
                    continue
                need = max(clr, o.clr, self.floor)
                if o.via:
                    d = point_segment_distance(o.x1, o.y1, x1, y1, x2, y2)
                    if d - hw - o.R < need - EPS or \
                            d - hw - o.drill / 2.0 < r.hole_clearance - EPS:
                        return False
                elif o.layer == layer:
                    if segment_segment_distance(seg, (o.x1, o.y1, o.x2, o.y2)) - hw - o.hw \
                            < need - EPS:
                        return False
            return True

        total = 0
        for name, cleaned, stubs, vlist in per_net:
            ctx = self.ctx[name]
            vset = set(vlist)
            fixed: Set[Tuple[int, int, int]] = set()   # nodes that keep their corner
            for p in ctx.pads:
                for n in p.nodelist:
                    for l in p.lay:
                        fixed.add((l, n[0], n[1]))
            for st in stubs:
                fixed.add((st.layer, st.a[0], st.a[1]))
            # the net as unit edges: (layer, node) -> {neighbour node: width}
            adj: Dict[Tuple[int, int, int], Dict[Tuple[int, int], float]] = {}
            for width, segs in cleaned.items():
                for layer, a, b in segs:
                    n = max(abs(b[0] - a[0]), abs(b[1] - a[1]))
                    if n == 0:
                        continue
                    sx, sy = (b[0] - a[0]) // n, (b[1] - a[1]) // n
                    for i in range(n):
                        u = (a[0] + sx * i, a[1] + sy * i)
                        v = (u[0] + sx, u[1] + sy)
                        adj.setdefault((layer,) + u, {})[v] = width
                        adj.setdefault((layer,) + v, {})[u] = width
            cut = 0
            for key in sorted(adj):
                nb = adj.get(key)
                if nb is None or len(nb) != 2 or key in fixed or key[1:] in vset:
                    continue
                layer, b = key[0], key[1:]
                (p1, w1), (p2, w2) = sorted(nb.items())
                if abs(w1 - w2) > 1e-9:
                    continue
                d1 = (p1[0] - b[0], p1[1] - b[1])
                d2 = (p2[0] - b[0], p2[1] - b[1])
                if d1[0] * d1[1] != 0 or d2[0] * d2[1] != 0 \
                        or d1[0] * d2[0] + d1[1] * d2[1] != 0:
                    continue                           # not two perpendicular grid steps
                # a corner between two long straight runs stays; a staircase step or
                # a one-step jog goes
                single1 = (p1[0] + d1[0], p1[1] + d1[1]) not in adj.get((layer,) + p1, {})
                single2 = (p2[0] + d2[0], p2[1] + d2[1]) not in adj.get((layer,) + p2, {})
                if not (single1 or single2):
                    continue
                if p2 in adj.get((layer,) + p1, {}):
                    continue
                hw = w1 / 2.0
                if ctx.rct_out is not None and hw < ctx.out_hw - 1e-9 \
                        and not (self._is_fine(p1) and self._is_fine(p2)):
                    continue                           # a fine piece must stay in a fine area
                if not clear(name, layer, p1, p2, hw, piece_clr(ctx, w1)):
                    continue
                del adj[key]
                del adj[(layer,) + p1][b]
                del adj[(layer,) + p2][b]
                adj[(layer,) + p1][p2] = w1
                adj[(layer,) + p2][p1] = w1
                cut += 1
            if not cut:
                continue
            total += cut
            groups: Dict[float, List[Any]] = {}
            for (layer, ux, uy), nb in adj.items():
                for v, width in nb.items():
                    if (ux, uy) < v:
                        groups.setdefault(width, []).append((layer, (ux, uy), v))
            anchors = set(fixed)
            for v in vset:
                for l in range(self.L):
                    anchors.add((l, v[0], v[1]))
            nodes_w: Dict[float, Set[Tuple[int, int, int]]] = {}
            for width, segs in groups.items():
                ns: Set[Tuple[int, int, int]] = set()
                for layer, a, b in segs:
                    ns.add((layer,) + a)
                    ns.add((layer,) + b)
                nodes_w[width] = ns
            cleaned.clear()
            for width in sorted(groups):
                other: Set[Tuple[int, int, int]] = set()
                for w2, ns in nodes_w.items():
                    if w2 != width:
                        other |= ns
                joints = nodes_w[width] & other
                cleaned[width] = cleanup_segments(groups[width], anchors | joints, vset,
                                                  self.L, breaks=joints)
            for rec in track_recs[name]:               # the others now see the new shape
                index.remove(rec)
            track_recs[name] = add_records(name, cleaned)
        if total:
            self.stats["corners_cut"] = total
        return total

# --------------------------------------------------------------------------
# cleanup
# --------------------------------------------------------------------------

_AXES = ((1, 0), (0, 1), (1, 1), (1, -1))


def cleanup_segments(segs: Iterable[Tuple[int, Tuple[int, int], Tuple[int, int]]],
                     anchors: Set[Tuple[int, int, int]], via_nodes: Set[Tuple[int, int]],
                     n_layers: int, breaks: Iterable[Tuple[int, int, int]] = ()
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
      junctions, at vias and at the nodes ``breaks`` (``(layer, ix, iy)``:
      where a track of another width joins) so that every connection is
      end-to-end.

    Returns segments in the same form, sorted."""
    breaks = set(breaks)
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
            cut = {n for n in via_nodes} | {(b[1], b[2]) for b in breaks if b[0] == layer}
            starts = [p for p, q in mine
                      if (p[0] - ax[0], p[1] - ax[1]) not in nxt or deg[p] != 2 or p in cut]
            for s in starts:
                e = nxt[s]
                while e in nxt and deg[e] == 2 and e not in cut:
                    e = nxt[e]
                out.append((layer, s, e))
    out.sort()
    return out


# --------------------------------------------------------------------------
# planes
# --------------------------------------------------------------------------

def _zone_values(design: Design, layer: str, net: str) -> Tuple[List[Any], float, float]:
    """(planes of ``net`` on ``layer``, zone clearance, zone minimum width)."""
    r = design.rules
    mine = [pl for pl in design.planes if pl.layer == layer and pl.net == net]
    zc = max(r.zone_clearance, design.netclass_of(net).clearance)
    mw = r.zone_min_width
    for pl in mine:
        if pl.clearance is not None:
            zc = pl.clearance
        if pl.min_width is not None:
            mw = pl.min_width
    return mine, zc, mw


def plane_static_area(design: Design, layer: str, net: str, margin: float = 0.02):
    """Where the plane(s) of ``net`` on ``layer`` can have copper at all,
    whatever is routed later: the planes' own outlines (the whole board for a
    plane without a shape) inside the copper-to-edge distance, minus

    * copper keep-outs of that layer,
    * the outline of every plane of ANOTHER net on the layer that KiCad fills
      first (higher ``priority``; equal priorities are reported by the checks),
      grown by the zone clearance - an island cuts a hole into the big plane,
    * non-plated holes.

    A shapely geometry (possibly empty).  The router lets a fan-out via land
    only here; :func:`plane_regions` starts from it."""
    r = design.rules
    mine, zc, _mw = _zone_values(design, layer, net)
    board_poly = geometry.outline_polygon(design.outline, r.max_arc_error)
    area = board_poly.buffer(-(max(r.copper_to_edge, zc) + margin))
    if not mine:
        return Polygon()
    if all(pl.shape is not None for pl in mine):
        own = shapely.unary_union([geometry.shape_polygon(pl.shape, r.max_arc_error)
                                   for pl in mine])
        area = area.intersection(own)
    prio = max(pl.priority for pl in mine)
    cuts: List[Any] = []
    for other in design.planes:
        if other.layer != layer or other.net == net or other.priority <= prio:
            continue
        ozc = other.clearance if other.clearance is not None else max(
            r.zone_clearance, design.netclass_of(other.net).clearance)
        if other.shape is None:
            return Polygon()                         # a whole-board plane is filled first
        cuts.append(geometry.shape_polygon(other.shape, r.max_arc_error, "circumscribed")
                    .buffer(max(zc, ozc) + margin))
    for ko in design.keepouts:
        if ko.copper and layer in ko.layer_names(design.copper_layers):
            cuts.append(geometry.keepout_polygon(ko).buffer(margin))
    for seg, width, _ring, _name in geometry.npth_holes(design):
        cuts.append(LineString([seg[:2], seg[2:]]).buffer(
            width / 2.0 + max(r.hole_clearance, r.copper_to_edge, zc) + margin)
            if seg[:2] != seg[2:] else Point(seg[0], seg[1]).buffer(
                width / 2.0 + max(r.hole_clearance, r.copper_to_edge, zc) + margin))
    if cuts:
        area = area.difference(shapely.unary_union(cuts))
    return area


def plane_regions(design: Design, layer: str, net: str, tracks: Sequence[Track],
                  vias: Sequence[Via], margin: float = 0.02) -> List[Any]:
    """Connected pieces of the filled plane(s) of ``net`` on ``layer``,
    predicted the way KiCad fills a zone - a little on the safe side
    (``margin``): :func:`plane_static_area` (outline, board edge, copper
    keep-outs, pours of other nets that are filled first, non-plated holes)
    minus everything foreign on that layer grown by the zone clearance
    (tracks, via pads, pads, drilled holes), with necks narrower than the
    zone's minimum width removed.

    Returns shapely polygons, largest first.  A via or plated pad of the net
    is connected to the piece its centre lies in; pieces do not connect to
    each other on this layer.  One piece = the plane is whole."""
    r = design.rules
    _mine, zc, mw = _zone_values(design, layer, net)
    area = plane_static_area(design, layer, net, margin)
    holes: List[Any] = []

    def clr(other: Optional[str], local: Optional[float] = None) -> float:
        return max(zc, design.clearance(net, other, local_b=local)) + margin

    for t in tracks:
        if t.layer == layer and t.net != net:
            line = LineString([(t.x1, t.y1), (t.x2, t.y2)]) if t.length > 1e-9 \
                else Point(t.x1, t.y1)
            holes.append(line.buffer(t.width / 2.0 + clr(t.net)))
    for v in vias:
        if v.net != net:
            holes.append(Point(v.x, v.y).buffer(max(
                v.diameter / 2.0 + clr(v.net), v.drill / 2.0 + r.hole_clearance + margin)))
    for p in geometry.placed_pads(design):
        if p.kind == "npth" or p.polygon is None:
            if p.ring is not None:
                holes.append(p.ring.buffer(clr(None) + geometry.PAD_POLYGON_TOLERANCE))
            continue
        if layer in p.layers and p.net != net:
            holes.append(p.polygon.buffer(clr(p.net, p.clearance)
                                          + geometry.PAD_POLYGON_TOLERANCE))
        if p.kind == "th" and p.drill > 0 and p.net != net:
            holes.append(p.hole_geometry().buffer(p.drill / 2.0 + r.hole_clearance + margin))
    region = area.difference(shapely.unary_union(holes)) if holes else area
    half = mw / 2.0 + margin / 2.0
    region = region.buffer(-half).buffer(mw / 2.0)
    polys = [g for g in getattr(region, "geoms", [region])
             if g.geom_type == "Polygon" and not g.is_empty and g.area > 1e-4]
    polys.sort(key=lambda g: (-g.area, g.bounds))
    for g in polys:
        shapely.prepare(g)
    return polys


def _region_index(regions: Sequence[Any], x: float, y: float) -> Optional[int]:
    """Index of the plane piece the point lies in (None: in none)."""
    pt = Point(x, y)
    for k, g in enumerate(regions):
        if g.contains(pt):
            return k
    return None


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
    * non-plated holes of the outline AND of footprints, round or oblong, and
      the netless copper ring around them;
    * track widths per net class - and, in a design with fine areas, that a
      fine class is fine only for copper completely inside an area: elsewhere
      the standard width and clearance apply (``Design.outside_values``);
    * the gap between a via and an SMD pad of its own net
      (``Rules.via_pad_gap_open`` where the via is not tented on the pad's
      side, ``via_pad_gap_tented`` where it is) - not a KiCad rule;
    * connectivity computed from the copper: pads, tracks and vias that touch
      are joined, and every via or pad of a net that owns a plane or pour is
      joined to the piece of that fill its centre lies in
      (:func:`plane_regions` - a prediction of KiCad's zone fill; KiCad's own
      fill and DRC have the last word).

    Nets with ``no_route`` and single-pad nets are not expected to be
    connected."""
    r = design.rules
    res = AuditResult()
    all_pads = geometry.placed_pads(design)
    pads = [p for p in all_pads if p.polygon is not None and p.layers]
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

    # ---- fine areas: which tracks / vias are not completely inside one ---------
    areas = geometry.FineAreas(design)
    confined = {name for name in design.nets if design.is_confined(name)}
    t_out = [t.net in confined and not areas.encloses(t_geoms[i], t.width / 2.0)
             for i, t in enumerate(tracks)]
    v_out = [v.net in confined and not areas.encloses(v_geoms[i], v.diameter / 2.0)
             for i, v in enumerate(vias)]
    open_sides = VIA_TENTING.get(design.via_tenting, ())

    # ---- clearances --------------------------------------------------------
    for i, t in enumerate(tracks):
        gt = t_geoms[i]
        hw = t.width / 2.0
        if t.width < design.min_track_width(t.net, outside=t_out[i]) - tol:
            viol("track_width", t.net, t.x1, t.y1, "width %.4f%s" % (
                t.width, " outside the fine areas" if t_out[i] else ""))
        for j in near(pad_tree, gt):
            p = pads[j]
            if p.net == t.net or t.layer not in p.layers:
                continue
            need = design.clearance(t.net, p.net, local_b=p.clearance, outside_a=t_out[i])
            gap = gt.distance(pad_geoms[j]) - pad_rad[j] - hw
            if gap < need - tol:
                viol("clearance", t.net, t.x1, t.y1,
                     "track to pad %s: %.4f < %.4f" % (p.key, gap, need))
            if p.kind == "th" and p.drill > 0:
                hole_gap = gt.distance(p.hole_geometry()) - p.drill / 2.0 - hw
                if hole_gap < r.hole_clearance - tol:
                    viol("hole_clearance", t.net, t.x1, t.y1,
                         "track to hole of %s: %.4f" % (p.key, hole_gap))
        for j in near(t_tree, gt):
            if j <= i:
                continue
            o = tracks[j]
            if o.net == t.net or o.layer != t.layer:
                continue
            need = max(design.clearance(t.net, o.net, outside_a=t_out[i],
                                        outside_b=t_out[j]), floor)
            gap = gt.distance(t_geoms[j]) - hw - o.width / 2.0
            if gap < need - tol:
                viol("clearance", t.net, t.x1, t.y1,
                     "track to track of %s: %.4f < %.4f" % (o.net, gap, need))
        for j in near(v_tree, gt):
            v = vias[j]
            if v.net == t.net:
                continue
            need = design.clearance(t.net, v.net, outside_a=t_out[i], outside_b=v_out[j])
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
                need = design.clearance(v.net, p.net, local_b=p.clearance, outside_a=v_out[i])
                if dist - rad < need - tol:
                    viol("clearance", v.net, v.x, v.y,
                         "via to pad %s: %.4f < %.4f" % (p.key, dist - rad, need))
                if dist - v.drill / 2.0 < r.hole_clearance - tol:
                    viol("hole_clearance", v.net, v.x, v.y, "via hole to pad %s" % p.key)
            elif p.kind != "th":
                # own pad: the via must not sit in or right next to it
                mask = "F.Mask" if p.side == "top" else "B.Mask"
                need = r.via_pad_gap_open if mask in open_sides else r.via_pad_gap_tented
                if dist - rad < need - tol - geometry.PAD_POLYGON_TOLERANCE:
                    viol("via_pad_gap", v.net, v.x, v.y,
                         "via %.4f mm from pad %s of its own net, %.3f wanted%s" % (
                             dist - rad, p.key, need,
                             " (via not tented on that side)" if mask in open_sides else ""))
            if p.kind == "th" and p.drill > 0:
                hh = gv.distance(p.hole_geometry()) - v.drill / 2.0 - p.drill / 2.0
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
                need = design.clearance(v.net, o.net, outside_a=v_out[i], outside_b=v_out[j])
                if dist - rad - o.diameter / 2.0 < need - tol:
                    viol("clearance", v.net, v.x, v.y, "via to via of %s" % o.net)
        edge_gap = gv.distance(boundary) - rad
        if edge_gap < r.copper_to_edge - tol or not board_poly.contains(gv):
            viol("copper_edge_clearance", v.net, v.x, v.y, "via to edge %.4f" % edge_gap)
    # ---- non-plated holes (outline and footprints; round or oblong) ---------------
    hole_need = max(r.hole_clearance, r.copper_to_edge)
    for seg, width, ring, name in geometry.npth_holes(design):
        hg = LineString([seg[:2], seg[2:]]) if seg[:2] != seg[2:] else Point(seg[0], seg[1])
        for i in near(t_tree, hg):
            t = tracks[i]
            gap = t_geoms[i].distance(hg) - width / 2.0 - t.width / 2.0
            if gap < hole_need - tol:
                viol("hole_clearance", t.net, t.x1, t.y1,
                     "track to NPTH hole %s: %.4f < %.4f" % (name, gap, hole_need))
            elif ring is not None:
                need = design.clearance(t.net, None, outside_a=t_out[i])
                gap = t_geoms[i].distance(ring) - t.width / 2.0
                if gap < need - tol - geometry.PAD_POLYGON_TOLERANCE:
                    viol("clearance", t.net, t.x1, t.y1,
                         "track to the copper of NPTH hole %s: %.4f < %.4f" % (name, gap, need))
        for i in near(v_tree, hg):
            v = vias[i]
            dist = v_geoms[i].distance(hg) - width / 2.0
            if dist - v.drill / 2.0 < r.hole_to_hole - tol:
                viol("hole_near_hole", v.net, v.x, v.y, "via to NPTH hole %s" % name)
            elif dist - v.diameter / 2.0 < hole_need - tol:
                viol("hole_clearance", v.net, v.x, v.y,
                     "via to NPTH hole %s: %.4f < %.4f" % (name, dist - v.diameter / 2.0,
                                                           hole_need))
            elif ring is not None:
                need = design.clearance(v.net, None, outside_a=v_out[i])
                gap = v_geoms[i].distance(ring) - v.diameter / 2.0
                if gap < need - tol - geometry.PAD_POLYGON_TOLERANCE:
                    viol("clearance", v.net, v.x, v.y,
                         "via to the copper of NPTH hole %s" % name)
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
        for j in near(pad_tree, v_geoms[i]):
            p = pads[j]
            if p.net == v.net and v_geoms[i].distance(pad_geoms[j]) - pad_rad[j] <= touch:
                union(("v", i), ("p", j))
    # planes and pours: a via or pad is on the piece of the fill its centre lies in
    for layer, net in plane_pairs(design):
        regions = plane_regions(design, layer, net, tracks, vias)
        res.plane_pieces["%s/%s" % (net, layer)] = len(regions)
        for i, v in enumerate(vias):
            if v.net == net:
                k = _region_index(regions, v.x, v.y)
                if k is not None:
                    union(("v", i), ("plane", net, layer, k))
        for j, p in enumerate(pads):
            if p.net == net and layer in p.layers:
                k = _region_index(regions, p.x, p.y)
                if k is not None:
                    union(("p", j), ("plane", net, layer, k))
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


def plane_pairs(design: Design) -> List[Tuple[str, str]]:
    """Distinct (layer, net) pairs that have a plane or pour, sorted."""
    return sorted({(pl.layer, pl.net) for pl in design.planes if pl.net in design.nets})


# --------------------------------------------------------------------------
# quality of a routing result
# --------------------------------------------------------------------------

def _octile(ax: float, ay: float, bx: float, by: float) -> float:
    dx, dy = abs(ax - bx), abs(ay - by)
    return max(dx, dy) + (math.sqrt(2.0) - 1.0) * min(dx, dy)


def net_quality(design: Design, tracks: Sequence[Track], vias: Sequence[Via], *,
                detour_warn: float = 2.5, same_side_vias_warn: int = 4) -> Dict[str, Any]:
    """How good is the copper, net by net - for the eyes of a layout engineer.

    For every routed net without a whole-board plane: track length, the
    length of the octile (0 / 45 / 90 degree) minimum spanning tree over its
    pad centres, their ratio, the number of vias, the number of pads and
    whether all pads are on one side.  ``warnings`` names the nets whose
    track is more than ``detour_warn`` times the spanning tree (and at least
    10 mm longer) and the nets with all pads on one side that use more than
    ``same_side_vias_warn`` vias per connection.  Nothing here is a rule
    violation; KiCad's DRC does not see any of it."""
    pads = [p for p in geometry.placed_pads(design) if p.polygon is not None and p.layers]
    by_net: Dict[str, List[Any]] = {}
    for p in pads:
        if p.net:
            by_net.setdefault(p.net, []).append(p)
    plane_nets = set(design.full_plane_layers().values())
    length: Dict[str, float] = {}
    n_vias: Dict[str, int] = {}
    for t in tracks:
        length[t.net] = length.get(t.net, 0.0) + t.length
    for v in vias:
        n_vias[v.net] = n_vias.get(v.net, 0) + 1
    nets: List[Dict[str, Any]] = []
    warnings: List[str] = []
    total_len = total_mst = 0.0
    for name, net in design.nets.items():
        ps = by_net.get(name, [])
        if net.no_route or len(ps) < 2 or name in plane_nets:
            continue
        pts = [(p.x, p.y) for p in ps]
        inn = {0}
        mst = 0.0
        best = {j: _octile(pts[0][0], pts[0][1], pts[j][0], pts[j][1])
                for j in range(1, len(pts))}
        while best:
            j = min(best, key=lambda k: (best[k], k))
            mst += best.pop(j)
            inn.add(j)
            for k in best:
                d = _octile(pts[j][0], pts[j][1], pts[k][0], pts[k][1])
                if d < best[k]:
                    best[k] = d
        ln = length.get(name, 0.0)
        nv = n_vias.get(name, 0)
        sides = sorted({p.side for p in ps})
        ratio = round(ln / mst, 2) if mst > 0.2 else None
        nets.append({"net": name, "pads": len(ps), "length_mm": round(ln, 3),
                     "tree_mm": round(mst, 3), "ratio": ratio, "vias": nv, "sides": sides})
        total_len += ln
        total_mst += mst
        if ratio is not None and ratio > detour_warn and ln - mst > 10.0:
            warnings.append("%s: %.1f mm of track for a %.1f mm spanning tree (x%.1f), "
                            "%d via(s)" % (name, ln, mst, ratio, nv))
        elif len(sides) == 1 and nv > same_side_vias_warn * (len(ps) - 1):
            warnings.append("%s: %d vias although its %d pads are all on the %s side" % (
                name, nv, len(ps), sides[0]))
    nets.sort(key=lambda n: (-(n["ratio"] or 0.0), n["net"]))
    return {
        "signal_length_mm": round(total_len, 3),
        "signal_tree_mm": round(total_mst, 3),
        "signal_ratio": round(total_len / total_mst, 3) if total_mst > 0 else None,
        "nets_over_1_5": sum(1 for n in nets if n["ratio"] and n["ratio"] > 1.5),
        "worst": nets[:10],
        "warnings": warnings,
        "nets": {n["net"]: {k: v for k, v in n.items() if k != "net"} for n in nets},
    }


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


# --------------------------------------------------------------------------
# keeping a routing result
# --------------------------------------------------------------------------

def fingerprint(design: Design, options: Optional[RouterOptions] = None) -> str:
    """Hash of everything the router's result depends on: the design (parts
    and their placement, nets, classes, rules, planes), the outline, the
    keep-outs and the router options.  Two designs with the same fingerprint
    get the same routing."""
    import hashlib
    opt = options or RouterOptions()
    outline = geometry.outline_polygon(design.outline, design.rules.max_arc_error)
    data = {
        "design": design.to_dict(),
        "outline": [[round(x, 6), round(y, 6)] for x, y in outline.exterior.coords],
        "cutouts": [[[round(x, 6), round(y, 6)] for x, y in ring.coords]
                    for ring in outline.interiors],
        "holes": [[h.x, h.y, h.drill] for h in design.outline.holes],
        "keepouts": [{"shape": repr(k.shape), "layers": list(k.layer_names(design.copper_layers)),
                      "tracks": k.tracks, "vias": k.vias, "copper": k.copper, "pads": k.pads}
                     for k in design.keepouts],
        "options": {k: (list(v) if isinstance(v, tuple) else v)
                    for k, v in sorted(vars(opt).items()) if k not in ("progress", "time_limit")},
        "router": ROUTER_VERSION,
    }
    text = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def save_routing(path: str, design: Design, result: RouteResult,
                 options: Optional[RouterOptions] = None) -> str:
    """Write the routed copper of ``result`` to a JSON file (tracks, vias,
    the design's :func:`fingerprint`, the routing statistics without the run
    time - the file is the same for every run of the same design)."""
    stats = {k: v for k, v in result.stats.items() if k != "runtime_s"}
    data = {
        "design": design.name,
        "fingerprint": fingerprint(design, options),
        "complete": result.complete,
        "connections_total": result.connections_total,
        "connections_routed": result.connections_routed,
        "stats": stats,
        "failures": dict(result.failures),
        "unrouted": [u.to_dict() for u in result.unrouted],
        "tracks": [[t.net, t.layer, t.x1, t.y1, t.x2, t.y2, t.width] for t in result.tracks],
        "vias": [[v.net, v.x, v.y, v.diameter, v.drill] for v in result.vias],
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=0, sort_keys=True)
        f.write("\n")
    return path


def load_routing(path: str, design: Optional[Design] = None,
                 options: Optional[RouterOptions] = None) -> RouteResult:
    """Read a file written by :func:`save_routing`.  With ``design`` the
    stored fingerprint must match (else :class:`RoutingError`) and the copper
    is audited again against that design, so the returned result is as
    trustworthy as a fresh one."""
    with open(path) as f:
        data = json.load(f)
    tracks = [Track(*t) for t in data["tracks"]]
    vias = [Via(*v) for v in data["vias"]]
    if design is None:
        aud = AuditResult(connections_total=data.get("connections_total", 0))
        return RouteResult(tracks, vias, aud, dict(data.get("stats", {})),
                           dict(data.get("failures", {})))
    if data.get("fingerprint") != fingerprint(design, options):
        raise RoutingError("%s was made for another version of the design or other router "
                           "options (fingerprint mismatch)" % path)
    return RouteResult(tracks, vias, audit(design, tracks, vias), dict(data.get("stats", {})),
                       dict(data.get("failures", {})))


#: bumped whenever the router's output for a given design can change
ROUTER_VERSION = "3"

__all__ = ["RouterOptions", "RouteResult", "AuditResult", "Unrouted", "RoutingError",
           "Router", "route", "route_board", "audit", "cleanup_segments", "plane_regions",
           "plane_static_area", "plane_pairs", "net_quality",
           "fingerprint", "save_routing", "load_routing", "ROUTER_VERSION"]
