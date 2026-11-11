"""Coordinate conventions - THE one place where design <-> KiCad conversion lives.

Design ("gleda") coordinates
----------------------------
* millimetres, origin at the board centre
* +x to the right, +y UP, as seen looking at the TOP of the board
* angles in degrees, counter-clockwise positive as seen from the top
* footprint-local coordinates use the same handedness (+y up, looking at the
  component side of the footprint)

KiCad coordinates
-----------------
* integer nanometres on a page, +x right, +y DOWN
* angles in degrees, counter-clockwise positive *as drawn on screen* (KiCad
  keeps the visual sense of rotation although its y axis points down), so an
  angle value needs no conversion - only points do

The board centre is put at ``KICAD_ORIGIN_MM`` on the KiCad page (and the
auxiliary / drill-place origin of the board is set to the same point, so fab
outputs that "use the drill/place file origin" are centred on the board).

Every other module must go through :func:`to_kicad_mm` / :func:`from_kicad_mm`
(or the ``*_nm`` variants).  Do not write ``-y`` anywhere else.

Bottom-side parts
-----------------
KiCad flips a footprint to the back by mirroring it about its local X axis
(top<->bottom flip) and then rotating by the stored orientation.  gleda uses
exactly the same definition so that ``Part.rotation`` is the number KiCad shows
and writes into position files:

    top:     board = (x, y) + R(rotation) . (lx,  ly)
    bottom:  board = (x, y) + R(rotation) . (lx, -ly)

where ``(lx, ly)`` are footprint-local coordinates (+y up, looking at the
component side) and ``R`` is a counter-clockwise rotation seen from the TOP of
the board.  :func:`local_to_board` implements this.
"""
from __future__ import annotations

import math
from typing import Iterable, List, Sequence, Tuple

#: Position of the design origin (board centre) on the KiCad page, in mm.
KICAD_ORIGIN_MM: Tuple[float, float] = (100.0, 100.0)

NM_PER_MM = 1_000_000

Point = Tuple[float, float]


def to_kicad_mm(x: float, y: float, origin: Point = KICAD_ORIGIN_MM) -> Point:
    """Design mm (+y up, board centre origin) -> KiCad page mm (+y down)."""
    return (origin[0] + x, origin[1] - y)


def from_kicad_mm(kx: float, ky: float, origin: Point = KICAD_ORIGIN_MM) -> Point:
    """KiCad page mm (+y down) -> design mm (+y up, board centre origin)."""
    return (kx - origin[0], origin[1] - ky)


def mm_to_nm(v: float) -> int:
    """mm -> integer nanometres (KiCad internal units), rounded to nearest."""
    return int(round(v * NM_PER_MM))


def nm_to_mm(v: int) -> float:
    """KiCad internal units -> mm."""
    return v / NM_PER_MM


def to_kicad_nm(x: float, y: float, origin: Point = KICAD_ORIGIN_MM) -> Tuple[int, int]:
    """Design mm -> KiCad integer nm."""
    kx, ky = to_kicad_mm(x, y, origin)
    return (mm_to_nm(kx), mm_to_nm(ky))


def from_kicad_nm(kx: int, ky: int, origin: Point = KICAD_ORIGIN_MM) -> Point:
    """KiCad integer nm -> design mm."""
    return from_kicad_mm(nm_to_mm(kx), nm_to_mm(ky), origin)


def local_to_kicad_mm(lx: float, ly: float) -> Point:
    """Footprint-local design mm (+y up) -> KiCad footprint-local mm (+y down)."""
    return to_kicad_mm(lx, ly, (0.0, 0.0))


def local_from_kicad_mm(kx: float, ky: float) -> Point:
    """KiCad footprint-local mm (+y down) -> footprint-local design mm (+y up)."""
    return from_kicad_mm(kx, ky, (0.0, 0.0))


def to_kicad_angle(rotation_deg: float) -> float:
    """Design rotation -> KiCad orientation (identity; see module docstring)."""
    return float(rotation_deg)


def normalize_angle(deg: float) -> float:
    """Normalise an angle to the range (-180, 180]."""
    d = math.fmod(deg, 360.0)
    if d > 180.0:
        d -= 360.0
    elif d <= -180.0:
        d += 360.0
    return d + 0.0


def rotate(x: float, y: float, deg: float) -> Point:
    """Rotate a point counter-clockwise (in a +y-up frame) about the origin."""
    q = deg % 360.0
    if q == 0.0:
        return (x, y)
    if q == 90.0:
        return (-y, x)
    if q == 180.0:
        return (-x, -y)
    if q == 270.0:
        return (y, -x)
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return (x * c - y * s, x * s + y * c)


def local_to_board(lx: float, ly: float, px: float, py: float,
                   rotation: float = 0.0, side: str = "top") -> Point:
    """Footprint-local point -> board point (both design mm, +y up).

    ``side`` is ``"top"`` or ``"bottom"``; see the module docstring for the
    bottom-side (KiCad-native) convention.
    """
    if side == "bottom":
        ly = -ly
    rx, ry = rotate(lx, ly, rotation)
    return (px + rx, py + ry)


def board_to_local(bx: float, by: float, px: float, py: float,
                   rotation: float = 0.0, side: str = "top") -> Point:
    """Inverse of :func:`local_to_board`."""
    lx, ly = rotate(bx - px, by - py, -rotation)
    if side == "bottom":
        ly = -ly
    return (lx, ly)


def local_angle_to_board(local_deg: float, rotation: float = 0.0,
                         side: str = "top") -> float:
    """Direction angle of a footprint-local feature after placement."""
    a = -local_deg if side == "bottom" else local_deg
    return normalize_angle(a + rotation)


def points_local_to_board(points: Iterable[Sequence[float]], px: float, py: float,
                          rotation: float = 0.0, side: str = "top") -> List[Point]:
    """Vectorised :func:`local_to_board` for a list of points."""
    return [local_to_board(p[0], p[1], px, py, rotation, side) for p in points]


_FLIP_LAYER = {
    "F.Cu": "B.Cu", "B.Cu": "F.Cu",
    "F.Paste": "B.Paste", "B.Paste": "F.Paste",
    "F.Mask": "B.Mask", "B.Mask": "F.Mask",
    "F.SilkS": "B.SilkS", "B.SilkS": "F.SilkS",
    "F.CrtYd": "B.CrtYd", "B.CrtYd": "F.CrtYd",
    "F.Fab": "B.Fab", "B.Fab": "F.Fab",
    "F.Adhes": "B.Adhes", "B.Adhes": "F.Adhes",
}


def flip_layer(name: str) -> str:
    """Front <-> back layer name (inner copper layers are unchanged here;
    gleda does not swap In1/In2 because through pads sit on all layers)."""
    return _FLIP_LAYER.get(name, name)
