"""Footprints: programmatic land patterns + KiCad library wrappers.

Two kinds of footprint can be given to :class:`gleda.model.Part`:

* a KiCad library id string ``"Lib:Name"`` (loaded from the installed
  ``*.pretty`` libraries), or
* a :class:`FootprintSpec` built here (BGA, castellated module, FPC
  connector, quad/dual leadless package, two-pad chip part, bare test / pogo /
  contact pads and pad rows, battery tab, NPTH hole, ...).

A :class:`FootprintSpec` is pure data in footprint-local design coordinates
(mm, +y UP, looking at the component side, rotation CCW).  It is turned into a
real KiCad footprint by writing a ``.kicad_mod`` file (:func:`kicad_mod_text`,
:func:`write_library`) and loading that with pcbnew, so custom and library
footprints go through exactly the same code path afterwards.

:func:`resolve` returns a pure-Python :class:`FootprintGeom` (pads with copper
polygons, courtyard, body box) for either kind; it is what the checks, the
router and the mechanical export use.  pcbnew is imported lazily, so building
specs and generating ``.kicad_mod`` text works without it.
"""
from __future__ import annotations

import atexit
import dataclasses
import hashlib
import math
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union

from . import coords

Point = Tuple[float, float]
BBox = Tuple[float, float, float, float]

#: Library nickname used for generated footprints.
CUSTOM_LIB = "gleda"

PAD_SHAPES = ("rect", "roundrect", "circle", "oval")
PAD_KINDS = ("smd", "conn", "th", "npth", "castellated")

_LIBRARY_DIRS: List[str] = []


def library_dirs() -> List[str]:
    """Directories searched for ``<Lib>.pretty`` (first match wins)."""
    dirs = list(_LIBRARY_DIRS)
    for var in ("GLEDA_FOOTPRINT_DIRS",):
        for d in os.environ.get(var, "").split(os.pathsep):
            if d:
                dirs.append(d)
    for var in ("KICAD7_FOOTPRINT_DIR", "KICAD6_FOOTPRINT_DIR"):
        if os.environ.get(var):
            dirs.append(os.environ[var])
    dirs.append("/usr/share/kicad/footprints")
    return dirs


def add_library_dir(path: str) -> None:
    """Prepend a directory containing ``*.pretty`` libraries to the search path."""
    if path not in _LIBRARY_DIRS:
        _LIBRARY_DIRS.insert(0, path)


class FootprintError(Exception):
    """Footprint cannot be found / loaded / built."""


# --------------------------------------------------------------------------
# Spec data model
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class PadSpec:
    """One pad of a custom footprint (footprint-local mm, +y up).

    ``kind``
        ``smd``          copper + mask opening + paste (top side)
        ``conn``         copper + mask opening, NO paste (test / pogo / contact pads)
        ``th``           plated through hole (``drill`` required)
        ``npth``         non-plated hole (``w``/``h`` = hole size unless copper wanted)
        ``castellated``  plated half-hole on the board edge (when THIS board is
                         the module); a module's land pattern on a carrier
                         board uses plain ``smd`` pads
    ``paste`` / ``mask`` switch the paste / mask aperture off for SMD pads;
    ``paste_margin`` / ``mask_margin`` are per-pad overrides (mm, negative
    shrinks the aperture).
    ``clearance`` is a local copper clearance override (mm).  KiCad's DRC uses
    it INSTEAD of the net-class clearances for anything next to this pad
    (never below the board minimum) - the way to let a fine track pass
    between the balls of a fine-pitch BGA without putting every net of the
    package into the fine class.  See :meth:`gleda.model.Design.clearance`.
    """
    number: str
    x: float
    y: float
    w: float
    h: float
    shape: str = "rect"
    kind: str = "smd"
    rotation: float = 0.0
    rratio: float = 0.25
    drill: float = 0.0
    paste: bool = True
    mask: bool = True
    paste_margin: Optional[float] = None
    mask_margin: Optional[float] = None
    clearance: Optional[float] = None

    def __post_init__(self):
        if self.clearance is not None and self.clearance <= 0:
            raise ValueError("pad %s: clearance override must be positive" % (self.number,))
        if self.shape not in PAD_SHAPES:
            raise ValueError("pad %s: unknown shape %r" % (self.number, self.shape))
        if self.kind not in PAD_KINDS:
            raise ValueError("pad %s: unknown kind %r" % (self.number, self.kind))
        if self.kind in ("th", "npth", "castellated") and self.drill <= 0:
            raise ValueError("pad %s: kind %s needs a drill" % (self.number, self.kind))
        if self.w <= 0 or self.h <= 0:
            raise ValueError("pad %s: size must be positive" % (self.number,))

    def bbox(self) -> BBox:
        """Axis-aligned bounding box (rotation taken into account)."""
        hw, hh = self.w / 2.0, self.h / 2.0
        pts = [coords.rotate(dx, dy, self.rotation)
               for dx, dy in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh))]
        xs = [self.x + p[0] for p in pts]
        ys = [self.y + p[1] for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))


@dataclass(frozen=True)
class Graphic:
    """Extra drawing on a footprint layer (local mm, +y up).

    ``kind``: "line" (points = 2), "rect" (2 corners), "circle" (centre +
    point on the circle), "poly" (>= 3 points, filled).
    """
    layer: str
    kind: str
    points: Tuple[Point, ...]
    width: float = 0.1
    fill: bool = False


@dataclass
class FootprintSpec:
    """A programmatically defined footprint.

    ``body``            (length_x, width_y) of the component body (fab outline)
    ``body_offset``     centre of the body relative to the footprint anchor
    ``courtyard``       explicit (xmin, ymin, xmax, ymax); default = bounding
                        box of pads and body grown by ``courtyard_margin``
    ``pin1``            location of the pin-1 marker (silk dot + fab chamfer
                        mark); None = no marker
    ``height``          component height above the board (mm), informational
    ``silk``            draw a silkscreen body outline (gaps over pads)
    ``exclude_from_bom`` / ``exclude_from_pos``  footprint attributes
    ``board_only``      footprint has no schematic symbol (holes, fiducials)
    """
    name: str
    pads: List[PadSpec]
    body: Tuple[float, float] = (1.0, 1.0)
    body_offset: Point = (0.0, 0.0)
    courtyard: Optional[BBox] = None
    courtyard_margin: float = 0.25
    pin1: Optional[Point] = None
    height: Optional[float] = None
    description: str = ""
    tags: str = ""
    silk: bool = True
    exclude_from_bom: bool = False
    exclude_from_pos: bool = False
    board_only: bool = False
    graphics: List[Graphic] = field(default_factory=list)

    # -- derived geometry --------------------------------------------------
    def body_bbox(self) -> BBox:
        cx, cy = self.body_offset
        hw, hh = self.body[0] / 2.0, self.body[1] / 2.0
        return (cx - hw, cy - hh, cx + hw, cy + hh)

    def pads_bbox(self) -> Optional[BBox]:
        boxes = [p.bbox() for p in self.pads]
        if not boxes:
            return None
        return (min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes))

    def courtyard_bbox(self) -> BBox:
        if self.courtyard is not None:
            return tuple(self.courtyard)  # type: ignore[return-value]
        b = self.body_bbox()
        pb = self.pads_bbox()
        if pb:
            b = (min(b[0], pb[0]), min(b[1], pb[1]), max(b[2], pb[2]), max(b[3], pb[3]))
        m = self.courtyard_margin
        return (_grid(b[0] - m, math.floor), _grid(b[1] - m, math.floor),
                _grid(b[2] + m, math.ceil), _grid(b[3] + m, math.ceil))

    def pad_numbers(self) -> List[str]:
        """Distinct, non-empty pad numbers in definition order."""
        out: List[str] = []
        for p in self.pads:
            if p.number and p.number not in out:
                out.append(p.number)
        return out

    @property
    def smd(self) -> bool:
        return all(p.kind in ("smd", "conn") for p in self.pads)

    @property
    def lib_id(self) -> str:
        return "%s:%s" % (CUSTOM_LIB, self.name)

    def key(self) -> str:
        """Stable content hash (used for caching and conflict detection)."""
        return hashlib.sha1(kicad_mod_text(self).encode("utf-8")).hexdigest()


def _grid(v: float, fn, step: float = 0.01) -> float:
    return round(fn(round(v / step, 6)) * step, 6)


# --------------------------------------------------------------------------
# .kicad_mod generation
# --------------------------------------------------------------------------

def _f(v: float) -> str:
    """Format a number the way KiCad does (max 6 decimals, no trailing zeros)."""
    s = ("%.6f" % (v + 0.0)).rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _q(s: str) -> str:
    return '"%s"' % str(s).replace("\\", "\\\\").replace('"', '\\"')


def _xy(p: Point) -> str:
    kx, ky = coords.local_to_kicad_mm(p[0], p[1])
    return "%s %s" % (_f(kx), _f(ky))


def _silk_segments(spec: FootprintSpec, clearance: float = 0.15,
                   width: float = 0.12) -> List[Tuple[Point, Point]]:
    """Body outline on silk, pushed outside the body by half a line width, with
    gaps wherever a pad (grown by ``clearance``) would be overprinted."""
    xmin, ymin, xmax, ymax = spec.body_bbox()
    off = width / 2.0 + 0.05
    xmin, ymin, xmax, ymax = xmin - off, ymin - off, xmax + off, ymax + off
    grow = clearance + width / 2.0
    pads = [(b[0] - grow, b[1] - grow, b[2] + grow, b[3] + grow)
            for b in (p.bbox() for p in spec.pads)]
    segs: List[Tuple[Point, Point]] = []

    def cut(lo: float, hi: float, blocked: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        free = [(lo, hi)]
        for b0, b1 in blocked:
            nxt = []
            for f0, f1 in free:
                if b1 <= f0 or b0 >= f1:
                    nxt.append((f0, f1))
                    continue
                if b0 > f0:
                    nxt.append((f0, b0))
                if b1 < f1:
                    nxt.append((b1, f1))
            free = nxt
        return [(a, b) for a, b in free if b - a >= 0.2]

    for y in (ymin, ymax):
        blocked = [(b[0], b[2]) for b in pads if b[1] < y < b[3]]
        for a, b in cut(xmin, xmax, blocked):
            segs.append(((a, y), (b, y)))
    for x in (xmin, xmax):
        blocked = [(b[1], b[3]) for b in pads if b[0] < x < b[2]]
        for a, b in cut(ymin, ymax, blocked):
            segs.append(((x, a), (x, b)))
    return segs


def _pad_sexpr(p: PadSpec) -> str:
    if p.kind in ("smd", "conn"):
        ptype = "smd" if p.kind == "smd" else "connect"
        layers = ['"F.Cu"']
        if p.kind == "smd" and p.paste:
            layers.append('"F.Paste"')
        if p.mask:
            layers.append('"F.Mask"')
    elif p.kind == "npth":
        ptype = "np_thru_hole"
        layers = ['"*.Cu"', '"*.Mask"']
    else:
        ptype = "thru_hole"
        layers = ['"*.Cu"', '"*.Mask"']
    at = _xy((p.x, p.y))
    if p.rotation:
        at += " %s" % _f(coords.to_kicad_angle(p.rotation))
    parts = ['(pad %s %s %s (at %s) (size %s %s)' % (
        _q(p.number), ptype, p.shape, at, _f(p.w), _f(p.h))]
    if p.kind in ("th", "npth", "castellated"):
        parts.append("(drill %s)" % _f(p.drill))
    if p.kind == "castellated":
        parts.append("(property pad_prop_castellated)")
    parts.append("(layers %s)" % " ".join(layers))
    if p.shape == "roundrect":
        parts.append("(roundrect_rratio %s)" % _f(p.rratio))
    if p.mask_margin is not None:
        parts.append("(solder_mask_margin %s)" % _f(p.mask_margin))
    if p.paste_margin is not None:
        parts.append("(solder_paste_margin %s)" % _f(p.paste_margin))
    if p.clearance is not None:
        parts.append("(clearance %s)" % _f(p.clearance))
    return " ".join(parts) + ")"


def _graphic_sexpr(g: Graphic) -> str:
    stroke = "(stroke (width %s) (type solid))" % _f(g.width)
    layer = "(layer %s)" % _q(g.layer)
    if g.kind == "line":
        return "(fp_line (start %s) (end %s) %s %s)" % (
            _xy(g.points[0]), _xy(g.points[1]), stroke, layer)
    if g.kind == "rect":
        return "(fp_rect (start %s) (end %s) %s (fill %s) %s)" % (
            _xy(g.points[0]), _xy(g.points[1]), stroke,
            "solid" if g.fill else "none", layer)
    if g.kind == "circle":
        return "(fp_circle (center %s) (end %s) %s (fill %s) %s)" % (
            _xy(g.points[0]), _xy(g.points[1]), stroke,
            "solid" if g.fill else "none", layer)
    if g.kind == "poly":
        pts = " ".join("(xy %s)" % _xy(p) for p in g.points)
        return "(fp_poly (pts %s) %s (fill %s) %s)" % (
            pts, stroke, "solid" if g.fill else "none", layer)
    raise ValueError("unknown graphic kind %r" % (g.kind,))


def kicad_mod_text(spec: FootprintSpec) -> str:
    """KiCad 7 ``.kicad_mod`` text of a spec (deterministic)."""
    bx0, by0, bx1, by1 = spec.body_bbox()
    cx0, cy0, cx1, cy1 = spec.courtyard_bbox()
    attrs = []
    if spec.pads and spec.smd:
        attrs.append("smd")
    elif any(p.kind in ("th", "castellated") for p in spec.pads):
        attrs.append("through_hole")
    if spec.board_only:
        attrs.append("board_only")
    if spec.exclude_from_pos:
        attrs.append("exclude_from_pos_files")
    if spec.exclude_from_bom:
        attrs.append("exclude_from_bom")
    text_h = 0.6 if min(spec.body) >= 2.0 else 0.4
    lines = [
        "(footprint %s (version 20221018) (generator gleda)" % _q(spec.name),
        '  (layer "F.Cu")',
    ]
    if spec.description:
        lines.append("  (descr %s)" % _q(spec.description))
    if spec.tags:
        lines.append("  (tags %s)" % _q(spec.tags))
    if attrs:
        lines.append("  (attr %s)" % " ".join(attrs))
    ref_y = cy1 + 0.6
    val_y = cy0 - 0.6
    lines += [
        '  (fp_text reference "REF**" (at %s) (layer "F.SilkS")' % _xy(((cx0 + cx1) / 2, ref_y)),
        "    (effects (font (size 0.8 0.8) (thickness 0.12)))",
        "  )",
        "  (fp_text value %s (at %s) (layer \"F.Fab\")" % (
            _q(spec.name), _xy(((cx0 + cx1) / 2, val_y))),
        "    (effects (font (size 0.8 0.8) (thickness 0.12)))",
        "  )",
        '  (fp_text user "${REFERENCE}" (at %s) (layer "F.Fab")' % _xy(
            ((bx0 + bx1) / 2, (by0 + by1) / 2)),
        "    (effects (font (size %s %s) (thickness %s)))" % (
            _f(text_h), _f(text_h), _f(text_h * 0.15)),
        "  )",
    ]
    glist: List[Graphic] = []
    # fab body outline
    glist.append(Graphic("F.Fab", "rect", ((bx0, by0), (bx1, by1)), 0.1))
    # courtyard
    glist.append(Graphic("F.CrtYd", "rect", ((cx0, cy0), (cx1, cy1)), 0.05))
    if spec.silk:
        for a, b in _silk_segments(spec):
            glist.append(Graphic("F.SilkS", "line", (a, b), 0.12))
    if spec.pin1 is not None:
        px, py = spec.pin1
        glist.append(Graphic("F.SilkS", "circle", ((px, py), (px + 0.1, py)), 0.2, True))
        glist.append(Graphic("F.Fab", "circle", ((px, py), (px + 0.15, py)), 0.1))
    glist.extend(spec.graphics)
    for g in glist:
        lines.append("  " + _graphic_sexpr(g))
    for p in spec.pads:
        lines.append("  " + _pad_sexpr(p))
    lines.append(")")
    return "\n".join(lines) + "\n"


def write_library(specs: Iterable[FootprintSpec], pretty_dir: str) -> Dict[str, str]:
    """Write specs into a ``.pretty`` directory; returns name -> file path.

    Two different specs with the same name are an error."""
    os.makedirs(pretty_dir, exist_ok=True)
    seen: Dict[str, str] = {}
    out: Dict[str, str] = {}
    for spec in specs:
        text = kicad_mod_text(spec)
        if spec.name in seen:
            if seen[spec.name] != text:
                raise FootprintError("two different footprints are both named %r" % spec.name)
            continue
        seen[spec.name] = text
        path = os.path.join(pretty_dir, spec.name + ".kicad_mod")
        if not (os.path.exists(path) and open(path, encoding="utf-8").read() == text):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
        out[spec.name] = path
    return out


# --------------------------------------------------------------------------
# Generators
# --------------------------------------------------------------------------

def castellated_module(name: str, body_w: float, body_h: float, *, pitch: float,
                       left: int = 0, bottom: int = 0, right: int = 0, top: int = 0,
                       pad_w: float = 0.3, inset: float = 0.6, overhang: float = 0.4,
                       offsets: Optional[Dict[str, float]] = None,
                       under_pads: Sequence[Tuple[str, float, float, float, float]] = (),
                       start_number: int = 1, height: Optional[float] = None,
                       pad_shape: str = "rect", description: str = "",
                       courtyard_margin: float = 0.25) -> FootprintSpec:
    """Land pattern for a castellated (edge-plated) module, seen from the top.

    Pads are numbered counter-clockwise starting at the top-left corner:
    ``left`` side top->bottom, ``bottom`` side left->right, ``right`` side
    bottom->top, ``top`` side right->left.

    Each edge pad is ``pad_w`` wide along the edge and reaches from
    ``overhang`` outside the body edge to ``inset`` under the body.  A row is
    centred on its edge unless ``offsets[side]`` gives the distance from the
    row's starting corner to the first pad centre (left: from the top edge,
    bottom: from the left edge, right: from the bottom edge, top: from the
    right edge).  ``under_pads`` adds pads below the module, e.g. ground pads:
    ``(number, x, y, w, h)``; several may share a number.
    """
    offsets = dict(offsets or {})
    pads: List[PadSpec] = []
    num = start_number
    hw, hh = body_w / 2.0, body_h / 2.0
    length = inset + overhang
    shift = (inset - overhang) / 2.0          # pad centre, measured inward from the edge

    def first(side: str, count: int, edge_len: float) -> float:
        if side in offsets:
            return offsets[side]
        return (edge_len - (count - 1) * pitch) / 2.0

    for side, count in (("left", left), ("bottom", bottom), ("right", right), ("top", top)):
        if count <= 0:
            continue
        edge_len = body_h if side in ("left", "right") else body_w
        o = first(side, count, edge_len)
        if o < 0 or o + (count - 1) * pitch > edge_len + 1e-9:
            raise ValueError("%s: %d pads at pitch %.3f do not fit on the %s edge"
                             % (name, count, pitch, side))
        for i in range(count):
            d = o + i * pitch
            if side == "left":
                x, y, w, h = -hw + shift, hh - d, length, pad_w
            elif side == "bottom":
                x, y, w, h = -hw + d, -hh + shift, pad_w, length
            elif side == "right":
                x, y, w, h = hw - shift, -hh + d, length, pad_w
            else:
                x, y, w, h = hw - d, hh - shift, pad_w, length
            pads.append(PadSpec(str(num), round(x, 6), round(y, 6), w, h, pad_shape))
            num += 1
    for number, x, y, w, h in under_pads:
        pads.append(PadSpec(str(number), x, y, w, h, "rect"))
    if not pads:
        raise ValueError("%s: module without pads" % name)
    return FootprintSpec(
        name=name, pads=pads, body=(body_w, body_h), height=height,
        pin1=(-hw - overhang - 0.35, hh - first("left", left, body_h) if left else hh),
        description=description or "Castellated module %gx%g mm, pitch %g mm" % (
            body_w, body_h, pitch),
        tags="module castellated", courtyard_margin=courtyard_margin)


def fpc_connector(name: str, n: int, *, pitch: float = 0.5, pad_w: float = 0.3,
                  pad_h: float = 1.3, pad_y: float = 1.85, mp_w: float = 1.8,
                  mp_h: float = 2.2, mp_dx: float = 1.9, mp_y: float = -1.4,
                  mp_number: str = "MP", body_w: Optional[float] = None,
                  body_h: float = 5.0, body_y: float = -0.8,
                  height: Optional[float] = None, description: str = "") -> FootprintSpec:
    """Generic single-row FFC/FPC connector land pattern.

    ``n`` signal pads (numbers "1".."n", pin 1 at -x) in a row at ``y = pad_y``
    and two mounting pads (number ``mp_number``) ``mp_dx`` beyond the end pads
    at ``y = mp_y``.  Defaults resemble a 0.5 mm pitch horizontal ZIF
    connector (signal pads towards +y, actuator/cable side towards -y).
    Always check against the manufacturer's recommended land pattern.
    """
    if n < 2:
        raise ValueError("FPC connector needs at least 2 contacts")
    span = (n - 1) * pitch
    pads = [PadSpec(str(i + 1), round(-span / 2.0 + i * pitch, 6), pad_y, pad_w, pad_h)
            for i in range(n)]
    mx = span / 2.0 + mp_dx
    pads.append(PadSpec(mp_number, -mx, mp_y, mp_w, mp_h))
    pads.append(PadSpec(mp_number, mx, mp_y, mp_w, mp_h))
    if body_w is None:
        body_w = 2 * mx + mp_w - 0.6
    return FootprintSpec(
        name=name, pads=pads, body=(body_w, body_h), body_offset=(0.0, body_y),
        pin1=(-span / 2.0 - pad_w - 0.45, pad_y), height=height,
        description=description or "FFC/FPC connector 1x%d, pitch %g mm" % (n, pitch),
        tags="FPC FFC connector")


def quad_package(name: str, body_w: float, body_h: float, *, pitch: float,
                 nx: int, ny: int, pad_w: float, pad_l: float,
                 pad_centre_inset: Optional[float] = None,
                 ep: Optional[Tuple[float, float]] = None,
                 height: Optional[float] = None, description: str = "",
                 shape: str = "roundrect") -> FootprintSpec:
    """Leadless quad or dual package (LGA / QFN / DFN) land pattern.

    Pads are numbered counter-clockwise from the top-left: ``ny`` pads down
    the left side, ``nx`` along the bottom, ``ny`` up the right side, ``nx``
    along the top.  Use ``nx=0`` for a dual (DFN/SON) package.  ``pad_l`` is
    the pad length perpendicular to the edge, ``pad_centre_inset`` the distance
    of the pad centre from the body edge (default: pad flush with the edge).
    ``ep`` adds an exposed pad (w, h) numbered n+1.
    """
    hw, hh = body_w / 2.0, body_h / 2.0
    inset = pad_l / 2.0 if pad_centre_inset is None else pad_centre_inset
    pads: List[PadSpec] = []
    num = 1
    for side, count in (("left", ny), ("bottom", nx), ("right", ny), ("top", nx)):
        for i in range(count):
            d = (i - (count - 1) / 2.0) * pitch
            if side == "left":
                x, y, w, h = -hw + inset, -d, pad_l, pad_w
            elif side == "bottom":
                x, y, w, h = d, -hh + inset, pad_w, pad_l
            elif side == "right":
                x, y, w, h = hw - inset, d, pad_l, pad_w
            else:
                x, y, w, h = -d, hh - inset, pad_w, pad_l
            pads.append(PadSpec(str(num), round(x, 6), round(y, 6), w, h, shape))
            num += 1
    if ep:
        pads.append(PadSpec(str(num), 0.0, 0.0, ep[0], ep[1], "rect"))
    first_y = (ny - 1) / 2.0 * pitch if ny else hh
    return FootprintSpec(
        name=name, pads=pads, body=(body_w, body_h), height=height,
        pin1=(-hw - 0.35, first_y),
        description=description or "Leadless package %gx%g mm, pitch %g mm" % (
            body_w, body_h, pitch),
        tags="LGA QFN DFN")


#: BGA row letters (JEDEC: I, O, Q, S, X and Z are not used).
BGA_ROW_LETTERS = "ABCDEFGHJKLMNPRTUVWY"


def bga_row_name(index: int) -> str:
    """Row name of a BGA for a 0-based row index: A, B, ... Y, AA, AB, ..."""
    n = len(BGA_ROW_LETTERS)
    if index < n:
        return BGA_ROW_LETTERS[index]
    return BGA_ROW_LETTERS[index // n - 1] + BGA_ROW_LETTERS[index % n]


def bga(name: str, nx: int, ny: int, *, pitch: float, pad_d: float,
        body: Optional[Tuple[float, float]] = None, height: Optional[float] = None,
        pad_clearance: Optional[float] = None, mask_margin: Optional[float] = None,
        paste_margin: Optional[float] = None, omit: Sequence[str] = (),
        description: str = "", courtyard_margin: float = 0.25) -> FootprintSpec:
    """Ball grid array land pattern, seen from the top of the board.

    ``nx`` columns (numbered 1..nx from the left) by ``ny`` rows (lettered
    A, B, ... from the top, skipping I, O, Q, S, X, Z), so ball A1 is the
    top-left pad.  Round pads of diameter ``pad_d`` on a ``pitch`` grid
    centred on the footprint anchor.  ``omit`` lists depopulated balls
    (``["C3"]``).  ``body`` is the package outline (default: the ball field
    plus one pitch).

    ``pad_clearance`` gives every pad a local clearance override (see
    :class:`PadSpec`).  Escape arithmetic for one track between two adjacent
    pads: ``pitch - pad_d >= track + 2 * clearance``.  At 0.5 mm pitch a
    0.09 mm track with 0.09 mm clearance needs ``pad_d <= 0.23`` - with
    0.25 mm pads KiCad reports a clearance of 0.08 mm
    (``tests/test_netclasses.py`` proves both cases with KiCad's DRC).
    """
    if nx < 1 or ny < 1:
        raise ValueError("%s: a BGA needs at least one ball" % name)
    if pad_d >= pitch:
        raise ValueError("%s: pad diameter %.3f must be smaller than the pitch %.3f"
                         % (name, pad_d, pitch))
    skip = {str(o).upper() for o in omit}
    pads: List[PadSpec] = []
    known = set()
    for row in range(ny):
        for col in range(nx):
            number = "%s%d" % (bga_row_name(row), col + 1)
            known.add(number)
            if number in skip:
                continue
            x = (col - (nx - 1) / 2.0) * pitch
            y = ((ny - 1) / 2.0 - row) * pitch
            pads.append(PadSpec(number, round(x, 6), round(y, 6), pad_d, pad_d, "circle",
                                mask_margin=mask_margin, paste_margin=paste_margin,
                                clearance=pad_clearance))
    if skip - known:
        raise ValueError("%s: cannot omit unknown ball(s) %s" % (name, sorted(skip - known)))
    if not pads:
        raise ValueError("%s: every ball is omitted" % name)
    if body is None:
        body = (round(nx * pitch, 6), round(ny * pitch, 6))
    return FootprintSpec(
        name=name, pads=pads, body=tuple(body), height=height,
        pin1=(-body[0] / 2.0 - 0.3, body[1] / 2.0),
        description=description or "BGA-%d %dx%d, pitch %g mm, pad %g mm" % (
            len(pads), nx, ny, pitch, pad_d),
        tags="BGA CSP", courtyard_margin=courtyard_margin)


def two_pad(name: str, *, pad_w: float, pad_h: float, pitch: float,
            body: Optional[Tuple[float, float]] = None, shape: str = "roundrect",
            numbers: Tuple[str, str] = ("1", "2"), height: Optional[float] = None,
            paste: bool = True, polarised: bool = False, description: str = "",
            tags: str = "", courtyard_margin: float = 0.25) -> FootprintSpec:
    """Two-terminal part (photodiode, big LED, inductor, switch, ...): pads
    ``numbers[0]`` at ``x = -pitch/2`` and ``numbers[1]`` at ``+pitch/2``.

    ``pitch`` is the pad centre distance, ``pad_w`` the pad size along x.
    ``polarised`` adds a pin-1 mark next to the first pad; ``paste=False``
    makes bare contact pads (mask opening, no paste)."""
    if pitch <= pad_w:
        raise ValueError("%s: pads overlap (pitch %.3f <= pad width %.3f)"
                         % (name, pitch, pad_w))
    kind = "smd" if paste else "conn"
    pads = [PadSpec(str(numbers[0]), -pitch / 2.0, 0.0, pad_w, pad_h, shape, kind),
            PadSpec(str(numbers[1]), pitch / 2.0, 0.0, pad_w, pad_h, shape, kind)]
    if body is None:
        body = (pitch + pad_w, pad_h)
    pin1 = (-pitch / 2.0 - pad_w / 2.0 - 0.35, 0.0) if polarised else None
    return FootprintSpec(
        name=name, pads=pads, body=tuple(body), height=height, pin1=pin1,
        description=description or "Two-pad part, pads %gx%g mm, pitch %g mm" % (
            pad_w, pad_h, pitch),
        tags=tags or "two pad", courtyard_margin=courtyard_margin)


def smd_pad(name: str, w: float, h: Optional[float] = None, *, shape: str = "circle",
            paste: bool = False, number: str = "1", description: str = "",
            tags: str = "pad", height: Optional[float] = 0.0) -> FootprintSpec:
    """Single bare SMD pad footprint (no body, not in BOM / position files)."""
    h = w if h is None else h
    if shape == "circle" and abs(w - h) > 1e-9:
        shape = "oval"
    pad = PadSpec(number, 0.0, 0.0, w, h, shape, "smd" if paste else "conn")
    return FootprintSpec(
        name=name, pads=[pad], body=(w, h), height=height, silk=False,
        description=description or "Bare pad %gx%g mm" % (w, h), tags=tags,
        exclude_from_bom=True, exclude_from_pos=True, courtyard_margin=0.15)


def test_pad(diameter: float = 1.0, name: Optional[str] = None) -> FootprintSpec:
    """Round test point / pogo-pin target pad (mask opening, no paste)."""
    return smd_pad(name or "TestPad_D%smm" % _f(diameter), diameter,
                   description="Test / pogo pad, %g mm" % diameter, tags="test point pogo")


test_pad.__test__ = False        # keep pytest from collecting it when imported into a test
pogo_pad = test_pad


def battery_tab(w: float, h: float, name: Optional[str] = None,
                paste: bool = True) -> FootprintSpec:
    """Rectangular solder landing for a battery tab / spring contact."""
    return smd_pad(name or "BatteryTab_%sx%smm" % (_f(w), _f(h)), w, h, shape="rect",
                   paste=paste, description="Battery tab landing %gx%g mm" % (w, h),
                   tags="battery tab")


def pad_row(name: str, n: int, pitch: float, pad_w: float, pad_h: Optional[float] = None, *,
            shape: str = "circle", paste: bool = False,
            description: str = "") -> FootprintSpec:
    """Row of ``n`` bare pads along x (numbers "1".."n"), e.g. a pogo-pin
    programming header."""
    pad_h = pad_w if pad_h is None else pad_h
    if shape == "circle" and abs(pad_w - pad_h) > 1e-9:
        shape = "oval"
    span = (n - 1) * pitch
    pads = [PadSpec(str(i + 1), round(-span / 2.0 + i * pitch, 6), 0.0, pad_w, pad_h, shape,
                    "smd" if paste else "conn") for i in range(n)]
    return FootprintSpec(
        name=name, pads=pads, body=(span + pad_w, pad_h), height=0.0, silk=False,
        pin1=(-span / 2.0, pad_h / 2.0 + 0.4),
        description=description or "%d bare pads, pitch %g mm" % (n, pitch),
        tags="pogo test pads", exclude_from_bom=True, exclude_from_pos=True,
        courtyard_margin=0.15)


def fiducial(copper: float = 1.0, mask: float = 2.0, name: Optional[str] = None
             ) -> FootprintSpec:
    """Global fiducial for the pick-and-place machine: a round bare copper
    dot of diameter ``copper`` in a solder-mask opening of diameter ``mask``,
    no paste (the IPC "1 mm in 2 mm" mark by default).

    The pad carries a clearance override of ``(mask - copper) / 2`` so that
    no other copper (track, via, pour) shows in the mask opening - the router
    and KiCad's DRC both honour it.  The footprint is board-only: no
    schematic symbol, not in the BOM or the position file.  Place it with
    :meth:`gleda.model.Design.add_fiducial`."""
    if mask < copper:
        raise ValueError("fiducial: the mask opening must not be smaller than the copper")
    margin = (mask - copper) / 2.0
    pad = PadSpec("", 0.0, 0.0, copper, copper, "circle", "conn",
                  mask_margin=margin if margin > 0 else None,
                  clearance=margin if margin > 0 else None)
    return FootprintSpec(
        name=name or "Fiducial_%smm_Mask%smm" % (_f(copper), _f(mask)), pads=[pad],
        body=(mask, mask), height=0.0, silk=False,
        description="Fiducial, %g mm copper in a %g mm mask opening" % (copper, mask),
        tags="fiducial", exclude_from_bom=True, exclude_from_pos=True, board_only=True,
        courtyard_margin=0.25)


def npth_hole(drill: float, name: Optional[str] = None) -> FootprintSpec:
    """Non-plated drilled hole as a board-only footprint."""
    pad = PadSpec("", 0.0, 0.0, drill, drill, "circle", "npth", drill=drill)
    return FootprintSpec(
        name=name or "NPTH_%smm" % _f(drill), pads=[pad], body=(drill, drill),
        height=0.0, silk=False, description="NPTH hole %g mm" % drill, tags="hole npth",
        exclude_from_bom=True, exclude_from_pos=True, board_only=True,
        courtyard_margin=0.1)


# --------------------------------------------------------------------------
# Resolved geometry (pure data) and pcbnew access
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class PadGeom:
    """A pad as found in the real footprint (local mm, +y up, top side).

    ``layers`` are KiCad layer names for the footprint on the top side
    (through pads list every copper layer name KiCad knows).  ``polygon`` is
    the copper outline (arcs approximated by KiCad, max error ~5 um).
    ``clearance`` is the pad's (or its footprint's) local clearance override
    in mm, None if there is none.

    Holes: ``drill`` is the tool diameter - the hole diameter, or the WIDTH of
    an oblong hole.  ``slot`` is then the half vector of the slot's centre
    line: the hole is everything within ``drill / 2`` of the segment from
    ``(x, y) - slot`` to ``(x, y) + slot`` ((0, 0) for a round hole).
    ``ring`` is the copper of a non-plated pad that is larger than its hole
    (netless copper around an NPTH hole); empty otherwise.
    """
    number: str
    x: float
    y: float
    w: float
    h: float
    shape: str
    rotation: float
    kind: str
    drill: float
    layers: Tuple[str, ...]
    polygon: Tuple[Point, ...]
    clearance: Optional[float] = None
    slot: Point = (0.0, 0.0)
    ring: Tuple[Point, ...] = ()

    @property
    def slotted(self) -> bool:
        return abs(self.slot[0]) > 1e-9 or abs(self.slot[1]) > 1e-9

    @property
    def hole_length(self) -> float:
        """Overall length of the hole (= ``drill`` for a round one)."""
        return self.drill + 2.0 * math.hypot(self.slot[0], self.slot[1])


@dataclass(frozen=True)
class ApertureGeom:
    """A pad without copper: an extra paste or mask aperture of a footprint
    (the split paste of an exposed pad, say).  Local mm, +y up, top side."""
    x: float
    y: float
    w: float
    h: float
    layers: Tuple[str, ...]


@dataclass(frozen=True)
class FootprintGeom:
    """Pure-Python view of a footprint (local mm, +y up, top side)."""
    lib_id: str
    pads: Tuple[PadGeom, ...]
    courtyard: BBox
    courtyard_polygon: Tuple[Point, ...]
    body: BBox
    height: Optional[float]
    smd: bool
    has_courtyard: bool
    #: copper-less paste / mask apertures (not pads of the model)
    apertures: Tuple[ApertureGeom, ...] = ()

    @property
    def pad_numbers(self) -> List[str]:
        out: List[str] = []
        for p in self.pads:
            if p.number and p.number not in out:
                out.append(p.number)
        return out

    def pads_numbered(self, number: str) -> List[PadGeom]:
        return [p for p in self.pads if p.number == str(number)]


def split_lib_id(lib_id: str) -> Tuple[str, str]:
    """``"Lib:Name"`` -> ``("Lib", "Name")``."""
    if ":" not in lib_id:
        raise FootprintError("footprint id %r must look like 'Library:Name'" % (lib_id,))
    lib, name = lib_id.split(":", 1)
    return lib, name


def find_library(lib: str) -> str:
    """Path of ``<lib>.pretty`` (FootprintError if not found)."""
    for d in library_dirs():
        path = os.path.join(d, lib + ".pretty")
        if os.path.isdir(path):
            return path
    raise FootprintError("footprint library %r not found in %s" % (lib, library_dirs()))


_TMP_LIB: Optional[str] = None


def _tmp_library() -> str:
    """Private scratch directory for specs that are resolved without an output
    directory; removed again when the process exits."""
    global _TMP_LIB
    if _TMP_LIB is None:
        _TMP_LIB = tempfile.mkdtemp(prefix="gleda_fp_")
        atexit.register(shutil.rmtree, _TMP_LIB, True)
    return _TMP_LIB


def load(footprint: Union[str, FootprintSpec], custom_lib_dir: Optional[str] = None):
    """Return a NEW ``pcbnew.FOOTPRINT`` for a library id or a spec.

    Specs are written to ``custom_lib_dir`` (a ``.pretty`` directory; default
    a private temporary one) and loaded from there.  The footprint's library
    link is set (``Lib:Name`` or ``gleda:Name``)."""
    import pcbnew
    if isinstance(footprint, FootprintSpec):
        lib_dir = custom_lib_dir or _tmp_library()
        if custom_lib_dir is None:
            # private scratch library: file name carries the content hash so
            # that two different specs sharing a name never collide
            scratch = os.path.join(lib_dir, footprint.key()[:16] + ".pretty")
            lib_dir = scratch
        write_library([footprint], lib_dir)
        lib, name = CUSTOM_LIB, footprint.name
    elif isinstance(footprint, str):
        lib, name = split_lib_id(footprint)
        lib_dir = find_library(lib)
        if not os.path.exists(os.path.join(lib_dir, name + ".kicad_mod")):
            raise FootprintError("footprint %r not found in %s" % (name, lib_dir))
    else:
        raise FootprintError("unsupported footprint object %r" % (footprint,))
    try:
        fp = pcbnew.FootprintLoad(lib_dir, name)
    except Exception as exc:                                  # pragma: no cover
        raise FootprintError("cannot load footprint %s:%s: %s" % (lib, name, exc))
    if fp is None:
        raise FootprintError("cannot load footprint %s:%s" % (lib, name))
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


_SHAPE_NAMES: Dict[int, str] = {}
_KIND_NAMES: Dict[int, str] = {}


def _init_enums() -> None:
    import pcbnew
    if _SHAPE_NAMES:
        return
    _SHAPE_NAMES.update({
        pcbnew.PAD_SHAPE_CIRCLE: "circle", pcbnew.PAD_SHAPE_RECT: "rect",
        pcbnew.PAD_SHAPE_OVAL: "oval", pcbnew.PAD_SHAPE_ROUNDRECT: "roundrect",
        pcbnew.PAD_SHAPE_TRAPEZOID: "trapezoid",
        pcbnew.PAD_SHAPE_CHAMFERED_RECT: "chamfered_rect",
        pcbnew.PAD_SHAPE_CUSTOM: "custom",
    })
    _KIND_NAMES.update({
        pcbnew.PAD_ATTRIB_SMD: "smd", pcbnew.PAD_ATTRIB_CONN: "conn",
        pcbnew.PAD_ATTRIB_PTH: "th", pcbnew.PAD_ATTRIB_NPTH: "npth",
    })


_SCRATCH_BOARD = None


def _scratch_board():
    """One process-wide scratch BOARD that owns every footprint we inspect.

    pcbnew 7 gotchas handled here: (1) ``GetCourtyard`` segfaults on a
    footprint without a parent board; (2) letting a temporary BOARD that had
    footprints added/removed be garbage collected corrupts pcbnew's state
    (later ``FootprintLoad`` calls fail or crash).  So the scratch board is
    created once and kept alive for the life of the process."""
    global _SCRATCH_BOARD
    if _SCRATCH_BOARD is None:
        import pcbnew
        _SCRATCH_BOARD = pcbnew.BOARD()
    return _SCRATCH_BOARD


def geom_from_pcbnew(fp, height: Optional[float] = None) -> FootprintGeom:
    """Extract a :class:`FootprintGeom` from a pcbnew footprint that sits at
    the page origin with orientation 0 on the front side (as returned by
    :func:`load`).

    NOTE: the footprint is CONSUMED - it is handed to an internal scratch
    board (see :func:`_scratch_board`) and must not be added to another board
    afterwards.  Call :func:`load` again for a footprint to place."""
    import pcbnew
    _init_enums()
    board = _scratch_board()
    board.Add(fp)
    nm = coords.nm_to_mm
    pads: List[PadGeom] = []
    apertures: List[ApertureGeom] = []

    def outline_points(pad) -> List[Point]:
        ps = pad.GetEffectivePolygon()
        pts: List[Point] = []
        if ps.OutlineCount() > 0:
            outline = ps.Outline(0)
            for i in range(outline.PointCount()):
                pt = outline.CPoint(i)
                pts.append(coords.local_from_kicad_mm(nm(pt.x), nm(pt.y)))
        return pts

    for pad in fp.Pads():
        pos = pad.GetPosition()
        x, y = coords.local_from_kicad_mm(nm(pos.x), nm(pos.y))
        size = pad.GetSize()
        kind = _KIND_NAMES.get(pad.GetAttribute(), "smd")
        layers = tuple(pcbnew.BOARD.GetStandardLayerName(l) for l in pad.GetLayerSet().Seq())
        has_copper = any(l.endswith(".Cu") for l in layers)
        poly_pts: List[Point] = []
        if has_copper and kind != "npth":
            poly_pts = outline_points(pad)
        drill = 0.0
        slot: Point = (0.0, 0.0)
        ring: List[Point] = []
        angle = pad.GetOrientationDegrees()
        if kind in ("th", "npth"):
            dsz = pad.GetDrillSize()
            dx, dy = nm(dsz.x), nm(dsz.y)
            if dy <= 0:
                dy = dx
            drill = min(dx, dy)
            half = abs(dx - dy) / 2.0
            if half > 1e-9:
                # long axis: the pad's own x (or y) axis, turned with the pad.
                # KiCad angles are counter-clockwise on the screen, i.e. in the
                # +y-up frame used here.
                a = math.radians(angle + (0.0 if dx > dy else 90.0))
                slot = (round(half * math.cos(a), 6) + 0.0, round(half * math.sin(a), 6) + 0.0)
            if kind == "npth" and has_copper and (
                    nm(size.x) > dx + 1e-6 or nm(size.y) > dy + 1e-6):
                ring = outline_points(pad)
        # KiCad: a pad's own override wins, else the footprint-level one
        local_clearance = pad.GetLocalClearance() or fp.GetLocalClearance()
        if not has_copper and kind in ("smd", "conn"):
            # paste-only / mask-only aperture pads carry no copper: not pads of
            # the model, but what they open is remembered for the output checks
            apertures.append(ApertureGeom(round(x, 6), round(y, 6), nm(size.x), nm(size.y),
                                          layers))
            continue
        pads.append(PadGeom(
            number=str(pad.GetNumber()), x=round(x, 6), y=round(y, 6),
            w=nm(size.x), h=nm(size.y),
            shape=_SHAPE_NAMES.get(pad.GetShape(), "custom"),
            rotation=coords.normalize_angle(angle),
            kind=kind, drill=drill, layers=layers,
            polygon=tuple((round(px, 6), round(py, 6)) for px, py in poly_pts),
            clearance=(nm(local_clearance) if local_clearance > 0 else None),
            slot=slot, ring=tuple((round(px, 6), round(py, 6)) for px, py in ring)))
    # body: bounding box of the fab-layer drawings (line width removed)
    body: Optional[List[float]] = None
    for g in fp.GraphicalItems():
        if g.GetLayer() != pcbnew.F_Fab or not isinstance(g, pcbnew.FP_SHAPE):
            continue
        bb = g.GetBoundingBox()
        hw = g.GetWidth() // 2
        x0, y0 = coords.local_from_kicad_mm(nm(bb.GetLeft() + hw), nm(bb.GetBottom() - hw))
        x1, y1 = coords.local_from_kicad_mm(nm(bb.GetRight() - hw), nm(bb.GetTop() + hw))
        if body is None:
            body = [x0, y0, x1, y1]
        else:
            body = [min(body[0], x0), min(body[1], y0), max(body[2], x1), max(body[3], y1)]
    # courtyard
    fp.BuildCourtyardCaches()
    cy = fp.GetCourtyard(pcbnew.F_CrtYd)
    cy_pts: List[Point] = []
    has_cy = cy.OutlineCount() > 0
    if has_cy:
        outline = cy.Outline(0)
        for i in range(outline.PointCount()):
            pt = outline.CPoint(i)
            px, py = coords.local_from_kicad_mm(nm(pt.x), nm(pt.y))
            cy_pts.append((round(px, 5), round(py, 5)))
    xs = [p[0] for pad in pads for p in pad.polygon] + [pad.x for pad in pads]
    ys = [p[1] for pad in pads for p in pad.polygon] + [pad.y for pad in pads]
    for pad in pads:
        if pad.kind == "npth":
            ex = abs(pad.slot[0]) + pad.drill / 2
            ey = abs(pad.slot[1]) + pad.drill / 2
            xs += [pad.x - ex, pad.x + ex]
            ys += [pad.y - ey, pad.y + ey]
    if body is None:
        if xs:
            body = [min(xs), min(ys), max(xs), max(ys)]
        else:
            body = [0.0, 0.0, 0.0, 0.0]
    if cy_pts:
        cbox = (min(p[0] for p in cy_pts), min(p[1] for p in cy_pts),
                max(p[0] for p in cy_pts), max(p[1] for p in cy_pts))
    else:
        allx = xs + [body[0], body[2]]
        ally = ys + [body[1], body[3]]
        cbox = (min(allx) - 0.25, min(ally) - 0.25, max(allx) + 0.25, max(ally) + 0.25)
        cy_pts = [(cbox[0], cbox[1]), (cbox[2], cbox[1]), (cbox[2], cbox[3]), (cbox[0], cbox[3])]
    lib_id = str(fp.GetFPID().GetUniStringLibId())
    smd = all(p.kind in ("smd", "conn") for p in pads) if pads else True
    geom = FootprintGeom(
        lib_id=lib_id, pads=tuple(pads),
        courtyard=tuple(round(v, 5) for v in cbox),          # type: ignore[arg-type]
        courtyard_polygon=tuple(cy_pts),
        body=tuple(round(v, 5) for v in body),               # type: ignore[arg-type]
        height=height, smd=smd, has_courtyard=has_cy, apertures=tuple(apertures))
    return geom


_GEOM_CACHE: Dict[str, FootprintGeom] = {}


def footprint_key(footprint: Union[str, FootprintSpec]) -> str:
    """Cache key: the library id, or ``gleda:<name>@<content hash>``."""
    if isinstance(footprint, FootprintSpec):
        return "%s@%s" % (footprint.lib_id, footprint.key())
    return str(footprint)


def resolve(footprint: Union[str, FootprintSpec]) -> FootprintGeom:
    """:class:`FootprintGeom` of a library id or spec (cached).

    Raises :class:`FootprintError` when the footprint cannot be loaded."""
    key = footprint_key(footprint)
    geom = _GEOM_CACHE.get(key)
    if geom is None:
        fp = load(footprint)
        height = footprint.height if isinstance(footprint, FootprintSpec) else None
        geom = geom_from_pcbnew(fp, height)
        if isinstance(footprint, FootprintSpec):
            # the spec knows its body exactly (fab markers may stick out)
            geom = dataclasses.replace(
                geom, body=tuple(round(v, 5) for v in footprint.body_bbox()))
        _GEOM_CACHE[key] = geom
    return geom


def clear_cache() -> None:
    """Forget cached footprint geometry (tests)."""
    _GEOM_CACHE.clear()


def lib_id_of(footprint: Union[str, FootprintSpec]) -> str:
    """``"Lib:Name"`` for either kind of footprint."""
    return footprint.lib_id if isinstance(footprint, FootprintSpec) else str(footprint)


__all__ = [
    "PadSpec", "Graphic", "FootprintSpec", "PadGeom", "ApertureGeom", "FootprintGeom",
    "FootprintError", "fiducial",
    "castellated_module", "fpc_connector", "quad_package", "bga", "bga_row_name",
    "two_pad", "smd_pad", "test_pad",
    "pogo_pad", "battery_tab", "pad_row", "npth_hole", "kicad_mod_text",
    "write_library", "load", "resolve", "geom_from_pcbnew", "lib_id_of",
    "footprint_key", "find_library", "add_library_dir", "library_dirs",
    "clear_cache", "CUSTOM_LIB",
]
