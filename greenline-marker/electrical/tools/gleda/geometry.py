"""Geometry helpers (shapely based, no pcbnew).

* exact "path" descriptions of the model shapes (lines + arcs) used to draw
  Edge.Cuts and rule areas without polygonising arcs
* shapely polygons of shapes / the board outline for checks and routing
* placed geometry of parts: pad polygons, courtyards and body rectangles in
  board coordinates (via :mod:`gleda.footprints` for the footprint data)

All coordinates are design mm, +y up (see :mod:`gleda.coords`).

Polygon approximation of arcs: ``tol`` is the maximum deviation.  With
``mode="inscribed"`` the polygon lies inside the true shape, with
``mode="circumscribed"`` it contains the true shape.  :func:`outline_polygon`
uses an inscribed outer boundary and circumscribed cutouts, so the returned
board polygon is always a (slightly) conservative subset of the real board.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from shapely.geometry import Polygon
from shapely.ops import unary_union

from . import coords
from .model import Circle, RoundedPolygon, Slot, Outline, Design, Part, BOTTOM

Point = Tuple[float, float]

DEFAULT_TOL = 0.005

#: KiCad approximates round pad outlines with polygons that lie INSIDE the true
#: copper by up to ~5 um; :meth:`PlacedPad.inflated` adds this much on top.
PAD_POLYGON_TOLERANCE = 0.006


# --------------------------------------------------------------------------
# exact paths
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Line:
    """Straight path element."""
    start: Point
    end: Point


@dataclass(frozen=True)
class Arc:
    """Circular arc path element from ``start`` through ``mid`` to ``end``."""
    start: Point
    mid: Point
    end: Point
    center: Point
    radius: float

    @property
    def angles(self) -> Tuple[float, float]:
        """(start angle, signed sweep) in radians, sweep > 0 = CCW (+y up)."""
        a0 = math.atan2(self.start[1] - self.center[1], self.start[0] - self.center[0])
        am = math.atan2(self.mid[1] - self.center[1], self.mid[0] - self.center[0])
        a1 = math.atan2(self.end[1] - self.center[1], self.end[0] - self.center[0])
        ccw = (a1 - a0) % (2 * math.pi)
        mid_ccw = (am - a0) % (2 * math.pi)
        if mid_ccw <= ccw + 1e-12:
            return a0, ccw
        return a0, ccw - 2 * math.pi


@dataclass(frozen=True)
class FullCircle:
    """Complete circle path (a closed contour on its own)."""
    center: Point
    radius: float


PathElement = "Line | Arc | FullCircle"


def _unit(dx: float, dy: float) -> Point:
    n = math.hypot(dx, dy)
    if n == 0:
        raise ValueError("zero-length polygon edge")
    return (dx / n, dy / n)


def rounded_polygon_path(points: Sequence[Point], radius: float) -> List[object]:
    """Closed path of a polygon with rounded corners.

    The corner radius is clamped so that two fillets never overlap on an edge
    (each fillet may use at most half of each adjacent edge).
    """
    pts = [tuple(p) for p in points]
    n = len(pts)
    if radius <= 0:
        return [Line(pts[i], pts[(i + 1) % n]) for i in range(n)]
    corners = []
    for i in range(n):
        p = pts[i]
        prev_pt = pts[i - 1]
        next_pt = pts[(i + 1) % n]
        ux, uy = _unit(prev_pt[0] - p[0], prev_pt[1] - p[1])
        vx, vy = _unit(next_pt[0] - p[0], next_pt[1] - p[1])
        cosphi = max(-1.0, min(1.0, ux * vx + uy * vy))
        phi = math.acos(cosphi)             # interior angle between the edges
        if phi < 1e-6 or abs(phi - math.pi) < 1e-6:
            corners.append((p, p, None))    # straight / degenerate: no fillet
            continue
        len_prev = math.hypot(prev_pt[0] - p[0], prev_pt[1] - p[1])
        len_next = math.hypot(next_pt[0] - p[0], next_pt[1] - p[1])
        t = radius / math.tan(phi / 2.0)
        t_max = min(len_prev, len_next) / 2.0
        r = radius
        if t > t_max:
            t = t_max
            r = t * math.tan(phi / 2.0)
        a = (p[0] + ux * t, p[1] + uy * t)          # tangent point on incoming edge
        b = (p[0] + vx * t, p[1] + vy * t)          # tangent point on outgoing edge
        bx, by = _unit(ux + vx, uy + vy)            # bisector
        dist = r / math.sin(phi / 2.0)
        c = (p[0] + bx * dist, p[1] + by * dist)
        mid = (c[0] - bx * r, c[1] - by * r)
        corners.append((a, b, Arc(a, mid, b, c, r)))
    path: List[object] = []
    for i in range(n):
        a, b, arc = corners[i]
        if arc is not None:
            path.append(arc)
        nxt_a = corners[(i + 1) % n][0]
        if math.hypot(nxt_a[0] - b[0], nxt_a[1] - b[1]) > 1e-9:
            path.append(Line(b, nxt_a))
    return path


def slot_path(slot: Slot) -> List[object]:
    """Closed path of a stadium shape."""
    r = slot.width / 2.0
    dx, dy = slot.x2 - slot.x1, slot.y2 - slot.y1
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return [FullCircle((slot.x1, slot.y1), r)]
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux                                  # left normal
    p1l = (slot.x1 + nx * r, slot.y1 + ny * r)
    p1r = (slot.x1 - nx * r, slot.y1 - ny * r)
    p2l = (slot.x2 + nx * r, slot.y2 + ny * r)
    p2r = (slot.x2 - nx * r, slot.y2 - ny * r)
    cap1 = (slot.x1 - ux * r, slot.y1 - uy * r)
    cap2 = (slot.x2 + ux * r, slot.y2 + uy * r)
    return [
        Line(p1r, p2r),
        Arc(p2r, cap2, p2l, (slot.x2, slot.y2), r),
        Line(p2l, p1l),
        Arc(p1l, cap1, p1r, (slot.x1, slot.y1), r),
    ]


def shape_path(shape) -> List[object]:
    """Exact closed path (list of :class:`Line`/:class:`Arc`, or a single
    :class:`FullCircle`) of a model shape."""
    if isinstance(shape, Circle):
        return [FullCircle((shape.cx, shape.cy), shape.r)]
    if isinstance(shape, RoundedPolygon):
        return rounded_polygon_path(shape.points, shape.radius)
    if isinstance(shape, Slot):
        return slot_path(shape)
    raise TypeError("unsupported shape %r" % (shape,))


# --------------------------------------------------------------------------
# polygonisation
# --------------------------------------------------------------------------

def arc_segments(radius: float, sweep: float, tol: float) -> int:
    """Number of chords needed to approximate an arc within ``tol``."""
    if radius <= tol:
        return max(2, int(math.ceil(abs(sweep) / (math.pi / 2))))
    step = 2.0 * math.acos(max(-1.0, 1.0 - tol / radius))
    return max(2, int(math.ceil(abs(sweep) / step)))


def _arc_points(center: Point, radius: float, a0: float, sweep: float, tol: float,
                mode: str, include_start: bool = True) -> List[Point]:
    n = arc_segments(radius, sweep, tol)
    out: List[Point] = []
    if mode == "circumscribed":
        # vertices pushed out so that every chord is tangent to the true arc
        half = abs(sweep) / n / 2.0
        r_out = radius / math.cos(half)
        if include_start:
            out.append((center[0] + radius * math.cos(a0), center[1] + radius * math.sin(a0)))
        for i in range(n):
            a = a0 + sweep * (i + 0.5) / n
            out.append((center[0] + r_out * math.cos(a), center[1] + r_out * math.sin(a)))
        a = a0 + sweep
        out.append((center[0] + radius * math.cos(a), center[1] + radius * math.sin(a)))
        return out
    start = 0 if include_start else 1
    for i in range(start, n + 1):
        a = a0 + sweep * i / n
        out.append((center[0] + radius * math.cos(a), center[1] + radius * math.sin(a)))
    return out


def path_points(path: Sequence[object], tol: float = DEFAULT_TOL,
                mode: str = "inscribed") -> List[Point]:
    """Polygon vertices approximating a closed path.

    ``mode`` refers to arcs that bulge OUTWARD (convex corners); for a simple
    convex-cornered shape "inscribed" gives a polygon inside the true shape.
    """
    if len(path) == 1 and isinstance(path[0], FullCircle):
        fc = path[0]
        n = max(8, arc_segments(fc.radius, 2 * math.pi, tol))
        r = fc.radius / math.cos(math.pi / n) if mode == "circumscribed" else fc.radius
        return [(fc.center[0] + r * math.cos(2 * math.pi * i / n),
                 fc.center[1] + r * math.sin(2 * math.pi * i / n)) for i in range(n)]
    pts: List[Point] = []
    for el in path:
        if isinstance(el, Line):
            pts.append(el.start)
        elif isinstance(el, Arc):
            a0, sweep = el.angles
            arc_pts = _arc_points(el.center, el.radius, a0, sweep, tol, mode)
            pts.extend(arc_pts[:-1])
        else:
            raise TypeError("unexpected path element %r" % (el,))
    # drop consecutive duplicates
    out: List[Point] = []
    for p in pts:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > 1e-9:
            out.append(p)
    if len(out) > 1 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) <= 1e-9:
        out.pop()
    return out


def shape_polygon(shape, tol: float = DEFAULT_TOL, mode: str = "inscribed") -> Polygon:
    """Shapely polygon of a model shape (see module docstring for ``mode``)."""
    poly = Polygon(path_points(shape_path(shape), tol, mode))
    if not poly.is_valid:
        poly = poly.buffer(0)
    return poly


def classify_cutouts(outline: Outline, tol: float = DEFAULT_TOL
                     ) -> Tuple[List[object], List[object]]:
    """Split ``outline.cutouts`` into (internal cutouts, edge notches).

    A cutout is internal when it lies strictly inside the outer boundary and
    does not touch another cutout; otherwise it is handled as a notch by
    boolean subtraction.  Internal cutouts that overlap each other are also
    treated as notches (merged by the boolean operation)."""
    outer = shape_polygon(outline.shape, tol)
    polys = [shape_polygon(c, tol, "circumscribed") for c in outline.cutouts]
    internal, notches = [], []
    for i, (shape, poly) in enumerate(zip(outline.cutouts, polys)):
        inside = outer.contains(poly) and outer.exterior.distance(poly) > 1e-6
        overlaps = any(j != i and poly.intersects(other) for j, other in enumerate(polys))
        if inside and not overlaps:
            internal.append(shape)
        else:
            notches.append(shape)
    return internal, notches


def outline_polygon(outline: Outline, tol: float = DEFAULT_TOL) -> Polygon:
    """Board area: outer boundary minus all cutouts / notches.

    NPTH holes are not subtracted (see :func:`hole_polygons`).  Raises
    ValueError if the result is empty or split into several pieces."""
    outer = shape_polygon(outline.shape, tol, "inscribed")
    if outline.cutouts:
        cut = unary_union([shape_polygon(c, tol, "circumscribed") for c in outline.cutouts])
        outer = outer.difference(cut)
    if outer.is_empty:
        raise ValueError("board outline is empty after subtracting cutouts")
    if outer.geom_type != "Polygon":
        raise ValueError("cutouts split the board into %d pieces"
                         % len(getattr(outer, "geoms", [])))
    return outer


def hole_polygons(outline: Outline, tol: float = DEFAULT_TOL) -> List[Polygon]:
    """Circumscribed polygons of the NPTH holes."""
    return [shape_polygon(Circle(h.x, h.y, h.drill / 2.0), tol, "circumscribed")
            for h in outline.holes]


def outline_contours(outline: Outline, tol: float = DEFAULT_TOL) -> List[List[object]]:
    """Closed contours to draw on Edge.Cuts.

    Exact line/arc/circle paths are returned whenever the outer boundary is
    not modified by notches; if notches exist the boundary is the boolean
    result, with arcs re-fitted where the vertices lie on a known circle
    (see :func:`refit_arcs`)."""
    internal, notches = classify_cutouts(outline, tol)
    contours: List[List[object]] = []
    if not notches:
        contours.append(shape_path(outline.shape))
    else:
        # the boolean is done on a much finer polygonisation than ``tol`` so
        # that the re-fitted arcs are accurate to well below a micrometre
        fine = min(tol, 0.0005)
        outer = shape_polygon(outline.shape, fine, "inscribed")
        cut = unary_union([shape_polygon(c, fine, "circumscribed") for c in notches])
        result = outer.difference(cut)
        if result.is_empty or result.geom_type != "Polygon":
            raise ValueError("notches make the board outline empty or disconnected")
        circles = _known_circles([outline.shape] + list(notches))
        contours.append(refit_arcs(list(result.exterior.coords)[:-1], circles, fine))
        for ring in result.interiors:
            contours.append(refit_arcs(list(ring.coords)[:-1], circles, fine))
    for shape in internal:
        contours.append(shape_path(shape))
    return contours


def _known_circles(shapes: Sequence[object]) -> List[Tuple[Point, float]]:
    """Centres/radii of all arcs appearing in the given shapes."""
    out: List[Tuple[Point, float]] = []
    for s in shapes:
        for el in shape_path(s):
            if isinstance(el, (Arc, FullCircle)):
                item = (el.center, el.radius)
                if not any(math.hypot(item[0][0] - c[0], item[0][1] - c[1]) < 1e-9
                           and abs(item[1] - r) < 1e-9 for c, r in out):
                    out.append(item)
    return out


def circumcircle(a: Point, b: Point, c: Point) -> Optional[Tuple[Point, float]]:
    """Centre and radius of the circle through three points (None if collinear)."""
    ax, ay = a
    bx, by = b
    cx, cy = c
    d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return None
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay)
          + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx)
          + (cx * cx + cy * cy) * (bx - ax)) / d
    return (ux, uy), math.hypot(ax - ux, ay - uy)


def circle_intersection(c1: Tuple[Point, float], c2: Tuple[Point, float],
                        near: Point) -> Optional[Point]:
    """Intersection point of two circles closest to ``near`` (None if the
    circles do not intersect)."""
    (x1, y1), r1 = c1
    (x2, y2), r2 = c2
    d = math.hypot(x2 - x1, y2 - y1)
    if d < 1e-12 or d > r1 + r2 or d < abs(r1 - r2):
        return None
    a = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
    h = math.sqrt(max(0.0, r1 * r1 - a * a))
    mx, my = x1 + a * (x2 - x1) / d, y1 + a * (y2 - y1) / d
    cands = [(mx + h * (y2 - y1) / d, my - h * (x2 - x1) / d),
             (mx - h * (y2 - y1) / d, my + h * (x2 - x1) / d)]
    return min(cands, key=lambda p: math.hypot(p[0] - near[0], p[1] - near[1]))


def refit_arcs(points: Sequence[Point], circles: Sequence[Tuple[Point, float]],
               tol: float = DEFAULT_TOL) -> List[object]:
    """Turn a polygon ring back into lines and arcs.

    Consecutive polygon edges whose end points lie on one of the known
    ``circles`` (within ``2.5*tol``) and whose chord is short enough to be a
    polygonisation chord of that circle are merged into a single :class:`Arc`
    running from the first to the last vertex of the run through the (snapped)
    middle vertex.  All other edges stay :class:`Line`.  Polygon vertices are
    kept as element end points, so the contour stays closed, and the result
    deviates from the polygon by at most about ``tol``.
    """
    pts = [tuple(p) for p in points]
    n = len(pts)
    if n < 3:
        raise ValueError("ring needs at least 3 points")

    def edge_circle(i: int) -> Optional[int]:
        a, b = pts[i], pts[(i + 1) % n]
        chord = math.hypot(b[0] - a[0], b[1] - a[1])
        for k, (c, r) in enumerate(circles):
            da = abs(math.hypot(a[0] - c[0], a[1] - c[1]) - r)
            db = abs(math.hypot(b[0] - c[0], b[1] - c[1]) - r)
            if da > 2.5 * tol or db > 2.5 * tol:
                continue
            # longest chord a polygonisation of this circle can produce
            n_seg = max(8, arc_segments(r, 2 * math.pi, tol))
            max_chord = 2.0 * r * math.tan(math.pi / n_seg) * 1.05
            if chord <= max_chord + 1e-9:
                return k
        return None

    tags = [edge_circle(i) for i in range(n)]
    if tags[0] is not None and all(t == tags[0] for t in tags):
        c, r = circles[tags[0]]
        return [FullCircle(c, r)]
    # start at a tag boundary so that runs do not wrap around
    start = 0
    for i in range(n):
        if tags[i] != tags[i - 1]:
            start = i
            break
    order = [(start + i) % n for i in range(n)]       # edge indices in walk order
    runs: List[Tuple[int, int, Optional[int]]] = []   # (first walk idx, last walk idx, tag)
    i = 0
    while i < n:
        tag = tags[order[i]]
        j = i
        while j + 1 < n and tags[order[j + 1]] == tag:
            j += 1
        if tag is not None and j - i + 1 < 2:
            tag = None                                 # a single chord stays a line
        runs.append((i, j, tag))
        i = j + 1

    def snap(p: Point, k: int) -> Point:
        c, r = circles[k]
        d = math.hypot(p[0] - c[0], p[1] - c[1])
        return (c[0] + (p[0] - c[0]) * r / d, c[1] + (p[1] - c[1]) * r / d)

    # snap the end vertices of every arc run onto its circle (shared vertices
    # move by less than the polygonisation tolerance, the contour stays closed);
    # a vertex shared by two arcs goes to the exact intersection of the circles
    snapped = list(pts)
    vertex_tags: Dict[int, List[int]] = {}
    for i, j, tag in runs:
        if tag is None:
            continue
        for v in (order[i], (order[j] + 1) % n):
            vertex_tags.setdefault(v, [])
            if tag not in vertex_tags[v]:
                vertex_tags[v].append(tag)
    for v, vtags in vertex_tags.items():
        if len(vtags) >= 2:
            hit = circle_intersection(circles[vtags[0]], circles[vtags[1]], pts[v])
            if hit is not None:
                snapped[v] = hit
                continue
        snapped[v] = snap(pts[v], vtags[0])
    path: List[object] = []
    for i, j, tag in runs:
        if tag is None:
            for k in range(i, j + 1):
                e = order[k]
                a, b = snapped[e], snapped[(e + 1) % n]
                if math.hypot(b[0] - a[0], b[1] - a[1]) > 1e-9:
                    path.append(Line(a, b))
            continue
        c, r = circles[tag]
        run = j - i + 1
        a = snapped[order[i]]
        b = snapped[(order[j] + 1) % n]
        m = snap(pts[(order[i] + run // 2) % n], tag)
        path.append(Arc(a, m, b, c, r))
    return path


# --------------------------------------------------------------------------
# placed part geometry
# --------------------------------------------------------------------------

@dataclass
class PlacedPad:
    """A footprint pad placed on the board (design mm, +y up).

    ``layers``   copper layers of THIS board on which the pad has copper
                 (empty for NPTH holes)
    ``polygon``  copper shape (shapely polygon, board coordinates) or None for
                 NPTH; identical on every layer in ``layers``
    ``net``      net name or None (unconnected / no-connect)
    ``kind``     "smd" | "th" | "npth" | "conn"
    ``drill``    finished hole diameter (0 for SMD)
    """
    ref: str
    number: str
    pin: Optional[str]
    net: Optional[str]
    x: float
    y: float
    layers: Tuple[str, ...]
    polygon: Optional[Polygon]
    kind: str
    drill: float
    w: float
    h: float
    rotation: float
    shape: str
    side: str

    @property
    def key(self) -> str:
        return "%s.%s" % (self.ref, self.number)

    def inflated(self, distance: float, resolution: int = 8) -> Optional[Polygon]:
        """Copper outline grown by ``distance`` plus :data:`PAD_POLYGON_TOLERANCE`
        (round corners) - a conservative keep-out, e.g. for a track centre line
        use ``distance = clearance + track_width / 2``.  None for NPTH pads
        (use ``x``, ``y``, ``drill``)."""
        if self.polygon is None:
            return None
        return self.polygon.buffer(distance + PAD_POLYGON_TOLERANCE, resolution)


def _board_copper_layers(pad_layers: Sequence[str], side: str,
                         copper_layers: Sequence[str]) -> Tuple[str, ...]:
    names = set()
    for l in pad_layers:
        if not l.endswith(".Cu"):
            continue
        names.add(coords.flip_layer(l) if side == BOTTOM else l)
    return tuple(l for l in copper_layers if l in names)


def part_pads(design: Design, part: Part) -> List[PlacedPad]:
    """All pads of one placed part in board coordinates."""
    from . import footprints
    if not part.placed:
        raise ValueError("%s is not placed" % part.ref)
    geom = footprints.resolve(part.footprint)
    pad_net = design.pad_nets(part.ref)
    pad_pin: Dict[str, str] = {}
    for pin in part.pins.values():
        for num in pin.pads:
            pad_pin.setdefault(num, pin.name)
    out: List[PlacedPad] = []
    for pg in geom.pads:
        x, y = coords.local_to_board(pg.x, pg.y, part.x, part.y, part.rotation, part.side)
        poly = None
        if pg.polygon and pg.kind != "npth":
            poly = Polygon(coords.points_local_to_board(
                pg.polygon, part.x, part.y, part.rotation, part.side))
            if not poly.is_valid:
                poly = poly.buffer(0)
        layers = () if pg.kind == "npth" else _board_copper_layers(
            pg.layers, part.side, design.copper_layers)
        out.append(PlacedPad(
            ref=part.ref, number=pg.number, pin=pad_pin.get(pg.number),
            net=pad_net.get(pg.number) if pg.number else None,
            x=x, y=y, layers=layers, polygon=poly, kind=pg.kind, drill=pg.drill,
            w=pg.w, h=pg.h,
            rotation=coords.local_angle_to_board(pg.rotation, part.rotation, part.side),
            shape=pg.shape, side=part.side))
    return out


def placed_pads(design: Design) -> List[PlacedPad]:
    """All pads of all placed parts (board coordinates) - the router's view
    of the component copper.  Unplaced parts are skipped."""
    out: List[PlacedPad] = []
    for part in design.parts:
        if part.placed:
            out.extend(part_pads(design, part))
    return out


def pads_by_net(design: Design) -> Dict[str, List[PlacedPad]]:
    """net name -> placed pads on that net (the terminals a router must join).
    Pads without a net are not included."""
    out: Dict[str, List[PlacedPad]] = {}
    for pad in placed_pads(design):
        if pad.net:
            out.setdefault(pad.net, []).append(pad)
    return out


def pad_position(design: Design, ref: str, pad: str) -> Point:
    """Board position of the (first) pad ``pad`` of part ``ref``."""
    from . import footprints
    part = design.part(ref)
    geom = footprints.resolve(part.footprint)
    for pg in geom.pads:
        if pg.number == str(pad):
            return coords.local_to_board(pg.x, pg.y, part.x, part.y, part.rotation, part.side)
    raise KeyError("%s has no pad %r" % (ref, pad))


def _rect_points(b: Tuple[float, float, float, float]) -> List[Point]:
    xmin, ymin, xmax, ymax = b
    return [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)]


def part_courtyard(part: Part) -> Polygon:
    """Courtyard polygon of a placed part in board coordinates."""
    from . import footprints
    geom = footprints.resolve(part.footprint)
    pts = geom.courtyard_polygon or _rect_points(geom.courtyard)
    poly = Polygon(coords.points_local_to_board(pts, part.x, part.y, part.rotation, part.side))
    return poly if poly.is_valid else poly.buffer(0)


def part_body(part: Part) -> Dict[str, float]:
    """Body description of a placed part for the mechanical team.

    Returns ``{"x", "y", "rotation", "side", "length", "width", "height",
    "cx", "cy"}`` where length/width are the body extents along the footprint
    local x / y axes, and (cx, cy) is the body centre on the board (it can
    differ from the anchor x, y for asymmetric footprints)."""
    from . import footprints
    geom = footprints.resolve(part.footprint)
    xmin, ymin, xmax, ymax = geom.body
    if part.body:
        length, width = part.body
        lcx, lcy = (xmin + xmax) / 2.0, (ymin + ymax) / 2.0
    else:
        length, width = xmax - xmin, ymax - ymin
        lcx, lcy = (xmin + xmax) / 2.0, (ymin + ymax) / 2.0
    cx, cy = coords.local_to_board(lcx, lcy, part.x, part.y, part.rotation, part.side)
    height = part.height_mm if part.height_mm is not None else geom.height
    return {"x": part.x, "y": part.y, "rotation": part.rotation, "side": part.side,
            "length": round(length, 4), "width": round(width, 4),
            "height": height, "cx": round(cx, 4), "cy": round(cy, 4)}


def part_body_polygon(part: Part) -> Polygon:
    """Body rectangle of a placed part in board coordinates."""
    from . import footprints
    geom = footprints.resolve(part.footprint)
    xmin, ymin, xmax, ymax = geom.body
    if part.body:
        cx, cy = (xmin + xmax) / 2.0, (ymin + ymax) / 2.0
        hl, hw = part.body[0] / 2.0, part.body[1] / 2.0
        xmin, ymin, xmax, ymax = cx - hl, cy - hw, cx + hl, cy + hw
    poly = Polygon(coords.points_local_to_board(
        _rect_points((xmin, ymin, xmax, ymax)), part.x, part.y, part.rotation, part.side))
    return poly


def keepout_polygon(keepout, tol: float = DEFAULT_TOL) -> Polygon:
    """Shapely polygon of a keep-out (circumscribed = conservative)."""
    return shape_polygon(keepout.shape, tol, "circumscribed")


def board_bounds(design: Design) -> Tuple[float, float, float, float]:
    """(xmin, ymin, xmax, ymax) of the outer board boundary."""
    return shape_polygon(design.outline.shape).bounds
