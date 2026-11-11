"""Routing grid and obstacle rasterisation (numpy + shapely, no pcbnew).

The router works on a uniform grid of *nodes*.  A track is a chain of
straight moves between neighbouring nodes (8 directions); a via sits on a
node.  For every "mover" (a track of half-width ``hw`` or a via) the router
needs to know on which nodes its centre may be placed.  That is answered by
rasterising every obstacle grown by

    reach = required clearance + mover half-width (+ move margin)

into a boolean mask: a node is blocked when its distance to the obstacle
copper is smaller than ``reach``.

Clearance maths
---------------
*Distance test.*  All masks are computed from exact distances (circle,
stadium = track segment) or from shapely's point-to-polygon distance, never
from a pre-rasterised picture, with a tolerance of :data:`EPS` (1 nm): a node
exactly ``reach`` away from an obstacle is free.

*Move margin.*  Testing nodes only is not enough: half way along a move the
track can be closer to an obstacle than at both of its end nodes.

* Orthogonal move of length ``g`` past a point obstacle half way between the
  nodes: both nodes are ``sqrt(d^2 + g^2/4)`` away while the track passes at
  ``d``.  Growing the obstacle by an extra :func:`move_margin`
  ``= sqrt(reach^2 + g^2/4) - reach`` makes "both nodes free" imply "the move
  is clear".  For reach 0.135 mm and g 0.05 mm that is 2.3 um.
* Diagonal moves are only allowed when the two nodes that complete the unit
  square are free as well ("no corner cutting", enforced by the search
  kernel).  With all four corners at least ``reach`` away the diagonal is
  clear for any ``reach > g`` - no extra margin needed.

*Grid-exact obstacles* need no margin at all: a circle centred on a node
(BGA ball, via) and a stadium whose end points are nodes (a routed track).
Their closest approach to any grid move happens at a node, where the test is
exact.  This is what lets a 0.09 mm track pass between two 0.23 mm balls at
0.5 mm pitch with exactly 0.09 mm clearance on both sides.

Vias do not move, so via masks never need the margin.
"""
from __future__ import annotations

import math
from typing import Optional, Tuple

import numpy as np
import shapely

#: distance tolerance in mm (1 nm, KiCad's internal resolution)
EPS = 1e-6

Window = Tuple[int, int, int, int]          # iy0, iy1, ix0, ix1 (half-open)


def move_margin(reach: float, pitch: float) -> float:
    """Extra growth of an off-grid obstacle that makes an orthogonal move
    between two free nodes clear (see module docstring)."""
    if reach <= 0:
        return pitch / 2.0
    return math.sqrt(reach * reach + pitch * pitch / 4.0) - reach


class Grid:
    """Uniform routing grid.

    Node ``(ix, iy)`` lies at ``(x0 + ix * pitch, y0 + iy * pitch)`` in design
    mm (+y up).  ``x0`` / ``y0`` are multiples of ``pitch`` offset by
    ``origin``, so with the default origin every node coordinate is a
    multiple of the pitch and parts placed on that raster have their pads on
    nodes.
    """

    def __init__(self, bounds: Tuple[float, float, float, float], pitch: float = 0.05,
                 origin: Tuple[float, float] = (0.0, 0.0), border: int = 2):
        if pitch <= 0:
            raise ValueError("grid pitch must be positive")
        xmin, ymin, xmax, ymax = bounds
        self.pitch = float(pitch)
        self.origin = (float(origin[0]), float(origin[1]))
        self.kx0 = int(math.floor((xmin - origin[0]) / pitch + 1e-9)) - border
        self.ky0 = int(math.floor((ymin - origin[1]) / pitch + 1e-9)) - border
        kx1 = int(math.ceil((xmax - origin[0]) / pitch - 1e-9)) + border
        ky1 = int(math.ceil((ymax - origin[1]) / pitch - 1e-9)) + border
        self.nx = kx1 - self.kx0 + 1
        self.ny = ky1 - self.ky0 + 1
        self.xs = np.array([self.x_of(i) for i in range(self.nx)], dtype=np.float64)
        self.ys = np.array([self.y_of(i) for i in range(self.ny)], dtype=np.float64)

    # -- coordinates -------------------------------------------------------
    def x_of(self, ix: int) -> float:
        return round((self.kx0 + ix) * self.pitch + self.origin[0], 9) + 0.0

    def y_of(self, iy: int) -> float:
        return round((self.ky0 + iy) * self.pitch + self.origin[1], 9) + 0.0

    def xy(self, ix: int, iy: int) -> Tuple[float, float]:
        return (self.x_of(ix), self.y_of(iy))

    def nearest(self, x: float, y: float) -> Tuple[int, int]:
        """Index of the node nearest to (x, y) (may lie outside the grid)."""
        ix = int(round((x - self.origin[0]) / self.pitch)) - self.kx0
        iy = int(round((y - self.origin[1]) / self.pitch)) - self.ky0
        return ix, iy

    def is_node(self, x: float, y: float, tol: float = 1e-7) -> bool:
        """True if (x, y) coincides with a grid node."""
        ix, iy = self.nearest(x, y)
        return abs(self.x_of(ix) - x) <= tol and abs(self.y_of(iy) - y) <= tol

    def inside(self, ix: int, iy: int) -> bool:
        return 0 <= ix < self.nx and 0 <= iy < self.ny

    @property
    def shape(self) -> Tuple[int, int]:
        """(ny, nx) - the shape of one layer map."""
        return (self.ny, self.nx)

    # -- windows -----------------------------------------------------------
    def window(self, xmin: float, ymin: float, xmax: float, ymax: float
               ) -> Optional[Window]:
        """Index window (iy0, iy1, ix0, ix1; half-open) of the nodes inside a
        box, clipped to the grid; None if empty."""
        p = self.pitch
        ix0 = int(math.ceil((xmin - self.origin[0]) / p - 1e-9)) - self.kx0
        ix1 = int(math.floor((xmax - self.origin[0]) / p + 1e-9)) - self.kx0 + 1
        iy0 = int(math.ceil((ymin - self.origin[1]) / p - 1e-9)) - self.ky0
        iy1 = int(math.floor((ymax - self.origin[1]) / p + 1e-9)) - self.ky0 + 1
        ix0, iy0 = max(ix0, 0), max(iy0, 0)
        ix1, iy1 = min(ix1, self.nx), min(iy1, self.ny)
        if ix0 >= ix1 or iy0 >= iy1:
            return None
        return (iy0, iy1, ix0, ix1)

    def window_xy(self, win: Window) -> Tuple[np.ndarray, np.ndarray]:
        """Broadcastable (Y column, X row) coordinate arrays of a window."""
        iy0, iy1, ix0, ix1 = win
        return self.ys[iy0:iy1, None], self.xs[None, ix0:ix1]

    # -- masks -------------------------------------------------------------
    def disc_mask(self, cx: float, cy: float, radius: float
                  ) -> Optional[Tuple[Window, np.ndarray]]:
        """Nodes closer than ``radius`` to the point (cx, cy)."""
        if radius <= EPS:
            return None
        win = self.window(cx - radius, cy - radius, cx + radius, cy + radius)
        if win is None:
            return None
        Y, X = self.window_xy(win)
        lim = radius - EPS
        mask = (X - cx) ** 2 + (Y - cy) ** 2 < lim * lim
        return (win, mask) if mask.any() else None

    def stadium_mask(self, x1: float, y1: float, x2: float, y2: float, radius: float
                     ) -> Optional[Tuple[Window, np.ndarray]]:
        """Nodes closer than ``radius`` to the segment (x1, y1)-(x2, y2)."""
        if radius <= EPS:
            return None
        win = self.window(min(x1, x2) - radius, min(y1, y2) - radius,
                          max(x1, x2) + radius, max(y1, y2) + radius)
        if win is None:
            return None
        Y, X = self.window_xy(win)
        dx, dy = x2 - x1, y2 - y1
        l2 = dx * dx + dy * dy
        if l2 < 1e-18:
            d2 = (X - x1) ** 2 + (Y - y1) ** 2
        else:
            t = ((X - x1) * dx + (Y - y1) * dy) / l2
            t = np.clip(t, 0.0, 1.0)
            d2 = (X - (x1 + t * dx)) ** 2 + (Y - (y1 + t * dy)) ** 2
        lim = radius - EPS
        mask = d2 < lim * lim
        return (win, mask) if mask.any() else None

    def polygon_mask(self, poly, radius: float) -> Optional[Tuple[Window, np.ndarray]]:
        """Nodes closer than ``radius`` to a shapely geometry (nodes inside a
        polygon have distance 0).  With ``radius`` 0 only interior nodes and
        nodes on the boundary are returned."""
        xmin, ymin, xmax, ymax = poly.bounds
        r = max(radius, 0.0)
        win = self.window(xmin - r, ymin - r, xmax + r, ymax + r)
        if win is None:
            return None
        iy0, iy1, ix0, ix1 = win
        xx, yy = np.meshgrid(self.xs[ix0:ix1], self.ys[iy0:iy1])
        d = shapely.distance(shapely.points(xx.ravel(), yy.ravel()), poly)
        mask = (d < r - EPS) if r > EPS else (d <= EPS)
        mask = mask.reshape(xx.shape)
        return (win, mask) if mask.any() else None

    def contained_mask(self, poly) -> np.ndarray:
        """Full-grid mask of the nodes inside (or on the edge of) a polygon."""
        if poly.is_empty:
            return np.zeros(self.shape, dtype=bool)
        xmin, ymin, xmax, ymax = poly.bounds
        out = np.zeros(self.shape, dtype=bool)
        win = self.window(xmin, ymin, xmax, ymax)
        if win is None:
            return out
        iy0, iy1, ix0, ix1 = win
        xx, yy = np.meshgrid(self.xs[ix0:ix1], self.ys[iy0:iy1])
        shapely.prepare(poly)
        inside = shapely.intersects_xy(poly, xx.ravel(), yy.ravel())
        out[iy0:iy1, ix0:ix1] = inside.reshape(xx.shape)
        return out

    def nodes_in(self, poly, inset: float = 0.0) -> np.ndarray:
        """(n, 2) integer array of the nodes (ix, iy) inside a polygon shrunk
        by ``inset``."""
        target = poly.buffer(-inset) if inset > 0 else poly
        if target.is_empty:
            return np.zeros((0, 2), dtype=np.int64)
        xmin, ymin, xmax, ymax = target.bounds
        win = self.window(xmin, ymin, xmax, ymax)
        if win is None:
            return np.zeros((0, 2), dtype=np.int64)
        iy0, iy1, ix0, ix1 = win
        xx, yy = np.meshgrid(self.xs[ix0:ix1], self.ys[iy0:iy1])
        inside = shapely.intersects_xy(target, xx.ravel(), yy.ravel()).reshape(xx.shape)
        iy, ix = np.nonzero(inside)
        return np.stack([ix + ix0, iy + iy0], axis=1).astype(np.int64)


def point_segment_distance(px: float, py: float, x1: float, y1: float,
                           x2: float, y2: float) -> float:
    """Distance from the point (px, py) to the segment (x1, y1)-(x2, y2)."""
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy
    if l2 < 1e-18:
        return math.hypot(px - x1, py - y1)
    t = ((px - x1) * dx + (py - y1) * dy) / l2
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def _orient(ax, ay, bx, by, cx, cy) -> float:
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)


def segments_intersect(a, b) -> bool:
    """True if the closed segments a = (x1, y1, x2, y2) and b cross or touch."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    d1 = _orient(bx1, by1, bx2, by2, ax1, ay1)
    d2 = _orient(bx1, by1, bx2, by2, ax2, ay2)
    d3 = _orient(ax1, ay1, ax2, ay2, bx1, by1)
    d4 = _orient(ax1, ay1, ax2, ay2, bx2, by2)
    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
            ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
        return True
    tol = 1e-12

    def on(px, py, x1, y1, x2, y2, d):
        return abs(d) <= tol and min(x1, x2) - tol <= px <= max(x1, x2) + tol \
            and min(y1, y2) - tol <= py <= max(y1, y2) + tol

    return (on(ax1, ay1, bx1, by1, bx2, by2, d1) or on(ax2, ay2, bx1, by1, bx2, by2, d2)
            or on(bx1, by1, ax1, ay1, ax2, ay2, d3) or on(bx2, by2, ax1, ay1, ax2, ay2, d4))


def segment_segment_distance(a, b) -> float:
    """Distance between two segments given as (x1, y1, x2, y2); 0 if they
    intersect."""
    if segments_intersect(a, b):
        return 0.0
    return min(point_segment_distance(a[0], a[1], *b),
               point_segment_distance(a[2], a[3], *b),
               point_segment_distance(b[0], b[1], *a),
               point_segment_distance(b[2], b[3], *a))


__all__ = ["EPS", "Grid", "move_margin", "point_segment_distance",
           "segment_segment_distance", "segments_intersect"]
