"""gleda design model - "netlist as code".

Pure Python (no pcbnew, no shapely at import time).  A :class:`Design` holds
everything the rest of the toolchain needs:

* board outline (circle / rounded polygon / general line + arc path such as
  a circle clipped by a chord, + cutouts, slots, notches, NPTH holes)
* stack-up, design rules (:class:`Rules`, default :data:`US_4L_STD`) and net
  classes, each with its own track width and clearance
* parts (:class:`Part`) with BOM data, footprint, pin -> pad mapping,
  placement and height
* nets (:class:`Net`) connecting part pins, explicit no-connects
* keep-out regions and copper planes
* (after routing) :class:`Track` / :class:`Via` primitives

Units and axes: millimetres, origin at the board centre, +x right, +y up as
seen from the top, rotation counter-clockwise positive.  See
:mod:`gleda.coords` for the bottom-side convention.

Quick example::

    from gleda.model import Design, Outline, Circle, Part, two_pin

    d = Design("demo", Outline(Circle(0, 0, 19.0)))
    d.add(Part("C1", "100n", "Capacitor_SMD:C_0402_1005Metric", pins=two_pin(),
               mpn="CL05B104KO5NNNC", manufacturer="Samsung", x=0, y=5))
    d.net("GND", "C1.2", "U1.GND")
    d.net("+3V0", "C1.1", "U1.VDD", netclass="Power")
    d.add_plane("GND", "In1.Cu")
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, asdict, replace
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

TOP = "top"
BOTTOM = "bottom"
SIDES = (TOP, BOTTOM)

#: Allowed electrical pin types.
ELECTRICAL_TYPES = (
    "power_in", "power_out", "passive", "input", "output", "bidir",
    "open_drain", "nc",
)

COPPER_LAYERS_2 = ("F.Cu", "B.Cu")
COPPER_LAYERS_4 = ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")
COPPER_LAYERS_6 = ("F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu")

ALL_LAYERS = "all"

#: Allowed values of :attr:`Design.via_tenting` -> the sides on which vias get
#: a solder-mask OPENING ("both" = tented on both sides, no openings).
VIA_TENTING: Dict[str, Tuple[str, ...]] = {
    "both": (),
    "bottom": ("F.Mask",),
    "top": ("B.Mask",),
    "none": ("F.Mask", "B.Mask"),
}

Point = Tuple[float, float]


def copper_layer_names(count: int) -> Tuple[str, ...]:
    """KiCad copper layer names, top to bottom, for a ``count``-layer board."""
    if count < 2 or count % 2:
        raise ValueError("layer count must be an even number >= 2, got %r" % (count,))
    return ("F.Cu",) + tuple("In%d.Cu" % i for i in range(1, count - 1)) + ("B.Cu",)


# --------------------------------------------------------------------------
# Rules, net classes, stack-up
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Rules:
    """Fabrication rule set (all values in mm).

    The default instance is :data:`US_4L_STD`, a conservative rule set that
    standard US 4-layer services meet (5 mil trace/space, 0.25 mm drill).
    Through vias only.  Pass a modified copy (``dataclasses.replace``) to
    :class:`Design` for another fab.
    """
    name: str = "US_4L_STD"
    #: minimum copper track width
    min_track: float = 0.127
    #: minimum copper-to-copper clearance (different nets)
    min_clearance: float = 0.127
    #: via pad diameter used by the router
    via_diameter: float = 0.50
    #: via finished drill used by the router
    via_drill: float = 0.25
    #: minimum annular ring (pad radius - drill radius)
    min_annular: float = 0.125
    #: smallest via pad the fab accepts
    min_via_diameter: float = 0.50
    #: smallest plated/non-plated through hole
    min_drill: float = 0.25
    #: minimum hole wall to hole wall distance
    hole_to_hole: float = 0.25
    #: minimum hole wall to copper of another net
    hole_clearance: float = 0.20
    #: minimum copper to board edge (outline and cutouts)
    copper_to_edge: float = 0.30
    #: default signal track width
    default_track: float = 0.15
    #: default power track width (net class "Power")
    power_track: float = 0.30
    #: clearance of the net classes "Default" and "Power" (and of every net
    #: class created without an explicit clearance).  ``min_clearance`` is the
    #: board-level floor; a fine-pitch net class may go down to it.
    default_clearance: float = 0.127
    #: clearance of copper zones (planes / pours) to other nets
    zone_clearance: float = 0.20
    #: minimum copper width inside a zone fill
    zone_min_width: float = 0.15
    #: thermal relief gap / spoke width for zone-to-pad connections
    thermal_gap: float = 0.20
    thermal_spoke: float = 0.25
    #: board-level solder mask expansion per side and minimum web
    mask_expansion: float = 0.0
    mask_min_web: float = 0.0
    #: silkscreen limits (cosmetic checks)
    min_silk_width: float = 0.10
    min_text_height: float = 0.50
    #: only through vias are supported by this rule set
    blind_buried_vias: bool = False
    #: maximum arc -> polygon approximation error used by KiCad
    max_arc_error: float = 0.005

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def validate(self) -> List[str]:
        """Return a list of self-consistency problems (empty if fine)."""
        problems = []
        ring = (self.via_diameter - self.via_drill) / 2.0
        if ring < self.min_annular - 1e-9:
            problems.append("via %.3f/%.3f has annular ring %.4f < min %.4f"
                            % (self.via_diameter, self.via_drill, ring, self.min_annular))
        if self.via_drill < self.min_drill - 1e-9:
            problems.append("via drill %.3f < min drill %.3f" % (self.via_drill, self.min_drill))
        if self.via_diameter < self.min_via_diameter - 1e-9:
            problems.append("via diameter %.3f < min via diameter %.3f"
                            % (self.via_diameter, self.min_via_diameter))
        if self.default_track < self.min_track - 1e-9:
            problems.append("default track %.3f < min track %.3f"
                            % (self.default_track, self.min_track))
        if self.power_track < self.min_track - 1e-9:
            problems.append("power track %.3f < min track %.3f"
                            % (self.power_track, self.min_track))
        if self.default_clearance < self.min_clearance - 1e-9:
            problems.append("default clearance %.3f < min clearance %.3f"
                            % (self.default_clearance, self.min_clearance))
        return problems


#: Default rule set: standard US 4-layer fab, through vias only.
US_4L_STD = Rules()

#: Same fab class with the board-level minimums lowered to 0.09 / 0.09 mm
#: (3.5 mil) so that a fine net class can escape 0.5 mm-pitch BGAs.  The net
#: classes "Default" (0.15 / 0.127) and "Power" (0.30 / 0.127) are unchanged;
#: add the fine class with
#: ``design.add_netclass("Fine", track_width=0.09, clearance=0.09)``.
US_4L_FINE = replace(US_4L_STD, name="US_4L_FINE", min_track=0.09, min_clearance=0.09)


@dataclass
class NetClass:
    """KiCad net class with its own track width and clearance.

    ``track_width``      width the router uses for nets of this class
    ``clearance``        copper clearance of this class.  KiCad's DRC requires
                         ``max(clearance of class A, clearance of class B)``
                         between items of two nets (see :meth:`Design.clearance`)
    ``via_diameter`` / ``via_drill``  via used for nets of this class
    ``min_track_width``  narrowest track KiCad's DRC accepts on nets of this
                         class (written as a custom rule into ``.kicad_dru``);
                         ``None`` means ``track_width``, i.e. no neck-down

    Unspecified values are filled in from the rule set by
    :meth:`Design.add_netclass`."""
    name: str
    track_width: float
    clearance: float
    via_diameter: float
    via_drill: float
    description: str = ""
    min_track_width: Optional[float] = None

    @property
    def hard_min_track(self) -> float:
        """Narrowest track allowed on nets of this class."""
        return self.track_width if self.min_track_width is None else self.min_track_width

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StackupLayer:
    """One physical layer of the stack-up (top to bottom)."""
    name: str            # "F.Cu", "dielectric 1", "F.Mask", ...
    kind: str            # copper | prepreg | core | mask | silk | paste
    thickness: float = 0.0   # mm
    material: str = ""
    epsilon_r: float = 0.0
    loss_tangent: float = 0.0


@dataclass(frozen=True)
class Stackup:
    """Board stack-up.  Build with :meth:`Stackup.standard`."""
    layers: Tuple[StackupLayer, ...]
    finish: str = "ENIG"

    @property
    def thickness(self) -> float:
        """Total thickness of copper + dielectric + mask (mm)."""
        return round(sum(l.thickness for l in self.layers), 6)

    @property
    def copper_layers(self) -> Tuple[str, ...]:
        return tuple(l.name for l in self.layers if l.kind == "copper")

    @classmethod
    def standard(cls, copper_count: int = 4, board_thickness: float = 0.8,
                 outer_cu: float = 0.035, inner_cu: float = 0.0175,
                 prepreg: float = 0.11, mask: float = 0.01,
                 finish: str = "ENIG", material: str = "FR4",
                 epsilon_r: float = 4.5, loss_tangent: float = 0.02) -> "Stackup":
        """Symmetric stack-up: outer prepreg (``prepreg`` mm each) and a core
        (or alternating core/prepreg for > 4 layers) sized so that the total
        equals ``board_thickness``."""
        names = copper_layer_names(copper_count)
        n_diel = copper_count - 1
        cu_total = 2 * outer_cu + (copper_count - 2) * inner_cu
        fixed = cu_total + 2 * mask
        if copper_count == 2:
            diel = [("core", board_thickness - fixed)]
        else:
            n_prepreg = 2 + max(0, (n_diel - 3) // 2)
            n_core = n_diel - n_prepreg
            core_t = (board_thickness - fixed - n_prepreg * prepreg) / n_core
            if core_t <= 0.04:
                raise ValueError(
                    "board thickness %.3f mm is too thin for a %d-layer stack-up "
                    "with %.3f mm prepreg" % (board_thickness, copper_count, prepreg))
            diel = []
            for i in range(n_diel):
                diel.append(("prepreg", prepreg) if i % 2 == 0 else ("core", core_t))
        layers: List[StackupLayer] = [
            StackupLayer("F.SilkS", "silk"),
            StackupLayer("F.Paste", "paste"),
            StackupLayer("F.Mask", "mask", mask),
        ]
        for i, cu in enumerate(names):
            outer = i in (0, copper_count - 1)
            layers.append(StackupLayer(cu, "copper", outer_cu if outer else inner_cu))
            if i < n_diel:
                kind, t = diel[i]
                layers.append(StackupLayer("dielectric %d" % (i + 1), kind, round(t, 6),
                                           material, epsilon_r, loss_tangent))
        layers += [
            StackupLayer("B.Mask", "mask", mask),
            StackupLayer("B.Paste", "paste"),
            StackupLayer("B.SilkS", "silk"),
        ]
        return cls(tuple(layers), finish)

    def to_dict(self) -> Dict[str, Any]:
        return {"finish": self.finish, "thickness": self.thickness,
                "layers": [asdict(l) for l in self.layers]}


# --------------------------------------------------------------------------
# Shapes / outline
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Circle:
    """Circle with centre (cx, cy) and radius r (mm)."""
    cx: float
    cy: float
    r: float

    @property
    def diameter(self) -> float:
        return 2.0 * self.r


@dataclass(frozen=True)
class RoundedPolygon:
    """Simple polygon whose corners are rounded with ``radius`` (0 = sharp).

    ``points`` are listed in order (either winding); the polygon is closed
    automatically.  Concave corners are rounded too.
    """
    points: Tuple[Point, ...]
    radius: float = 0.0

    def __post_init__(self):
        pts = tuple((float(p[0]), float(p[1])) for p in self.points)
        if len(pts) >= 2 and pts[0] == pts[-1]:
            pts = pts[:-1]
        if len(pts) < 3:
            raise ValueError("a polygon needs at least 3 points")
        object.__setattr__(self, "points", pts)

    @classmethod
    def rect(cls, cx: float, cy: float, w: float, h: float, radius: float = 0.0,
             rotation: float = 0.0) -> "RoundedPolygon":
        """Axis-aligned (or rotated) rectangle centred on (cx, cy)."""
        hw, hh = w / 2.0, h / 2.0
        pts = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
        if rotation:
            a = math.radians(rotation)
            c, s = math.cos(a), math.sin(a)
            pts = [(x * c - y * s, x * s + y * c) for x, y in pts]
        return cls(tuple((cx + x, cy + y) for x, y in pts), radius)


@dataclass(frozen=True)
class Slot:
    """Stadium ("obround") shape: all points within ``width``/2 of the segment
    (x1, y1)-(x2, y2).  Used for routed slots and notches."""
    x1: float
    y1: float
    x2: float
    y2: float
    width: float


@dataclass(frozen=True)
class PathSegment:
    """One step of a :class:`PathShape`: a straight line to ``end`` or, when
    ``center`` is given, a circular arc to ``end`` about ``center`` (``ccw`` =
    counter-clockwise in the +y-up design frame)."""
    end: Point
    center: Optional[Point] = None
    ccw: bool = True


@dataclass(frozen=True)
class PathShape:
    """Closed outline made of straight lines and circular arcs.

    Build it step by step::

        PathShape.begin(-5, 0).line_to(5, 0).arc_to(-5, 0, 0, 0, ccw=True).close()

    or use a factory: :meth:`clipped_circle` (a circle cut by one or more
    chords) / :meth:`d_shape` (a circle with one flat).  The path may run in
    either direction; it must not intersect itself.
    """
    start: Point
    segments: Tuple[PathSegment, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "start", (float(self.start[0]), float(self.start[1])))
        object.__setattr__(self, "segments", tuple(self.segments))

    # -- construction ------------------------------------------------------
    @classmethod
    def begin(cls, x: float, y: float) -> "PathShape":
        """Start a path at (x, y)."""
        return cls((float(x), float(y)), ())

    @property
    def end(self) -> Point:
        """Current end point of the path."""
        return self.segments[-1].end if self.segments else self.start

    def line_to(self, x: float, y: float) -> "PathShape":
        """Append a straight line to (x, y); returns the extended path."""
        return PathShape(self.start, self.segments + (PathSegment((float(x), float(y))),))

    def arc_to(self, x: float, y: float, cx: float, cy: float,
               ccw: bool = True) -> "PathShape":
        """Append a circular arc about (cx, cy) to (x, y).  The current end
        point and (x, y) must be at the same distance from the centre."""
        r0 = math.hypot(self.end[0] - cx, self.end[1] - cy)
        r1 = math.hypot(x - cx, y - cy)
        if r0 < 1e-9 or abs(r0 - r1) > 1e-6:
            raise ValueError("arc end points are %.6f and %.6f mm from the centre"
                             % (r0, r1))
        if math.hypot(self.end[0] - x, self.end[1] - y) < 1e-9:
            raise ValueError("arc with identical end points (use Circle for a full circle)")
        seg = PathSegment((float(x), float(y)), (float(cx), float(cy)), bool(ccw))
        return PathShape(self.start, self.segments + (seg,))

    @property
    def closed(self) -> bool:
        return bool(self.segments) and math.hypot(
            self.end[0] - self.start[0], self.end[1] - self.start[1]) < 1e-9

    def close(self) -> "PathShape":
        """Close the path with a straight line back to the start if needed."""
        path = self
        if not path.closed:
            path = path.line_to(*path.start)
        arcs = sum(1 for seg in path.segments if seg.center is not None)
        if len(path.segments) < (2 if arcs else 3):
            raise ValueError("a closed path needs at least three lines, or two segments "
                             "one of which is an arc")
        return path

    # -- factories ---------------------------------------------------------
    @classmethod
    def clipped_circle(cls, cx: float, cy: float, r: float,
                       chords: Sequence[Tuple[float, float]]) -> "PathShape":
        """Circle of radius ``r`` about (cx, cy) with one or more segments cut
        off by straight chords.

        Each chord is ``(angle_deg, distance)``: the unit normal of the chord
        points in direction ``angle_deg`` (0 = +x, 90 = +y) and the chord lies
        ``distance`` mm from the centre along it; everything beyond the chord
        is removed.  ``(90, 17.3)`` cuts the circle off at y = cy + 17.3.
        The removed segments must not overlap each other.
        """
        if r <= 0:
            raise ValueError("radius must be positive")
        if not chords:
            raise ValueError("clipped_circle needs at least one chord (use Circle)")
        cuts = []
        for angle, dist in chords:
            if not -r < dist < r:
                raise ValueError("chord distance %.4f must be inside the radius %.4f"
                                 % (dist, r))
            cuts.append((math.radians(angle) % (2 * math.pi), math.acos(dist / r)))
        cuts.sort()
        n = len(cuts)
        for i in range(n):
            a0, h0 = cuts[i]
            a1, h1 = cuts[(i + 1) % n]
            gap = (a1 - a0) % (2 * math.pi) if n > 1 else 2 * math.pi
            if gap - h0 - h1 < 1e-9:
                raise ValueError("chords overlap; describe the outline as a polygon")

        def pt(angle: float) -> Point:
            x, y = cx + r * math.cos(angle), cy + r * math.sin(angle)
            return (round(x, 9) + 0.0, round(y, 9) + 0.0)

        path = cls.begin(*pt(cuts[0][0] + cuts[0][1]))
        for i in range(n):
            a1, h1 = cuts[(i + 1) % n]
            path = path.arc_to(*pt(a1 - h1), cx, cy, ccw=True)     # kept arc
            path = path.line_to(*pt(a1 + h1))                      # the chord
        return path.close()

    @classmethod
    def d_shape(cls, r: float, flat_y: float, cx: float = 0.0, cy: float = 0.0
                ) -> "PathShape":
        """Circle of radius ``r`` about (cx, cy) with a flat at ``y = flat_y``
        (the side beyond the flat, away from the centre, is removed)."""
        d = flat_y - cy
        return cls.clipped_circle(cx, cy, r, [(90.0, d)] if d >= 0 else [(270.0, -d)])


Shape = Union[Circle, RoundedPolygon, Slot, PathShape]


@dataclass(frozen=True)
class Hole:
    """Non-plated drilled hole (NPTH)."""
    x: float
    y: float
    drill: float
    name: str = ""


@dataclass
class Outline:
    """Board outline.

    ``shape``    outer boundary (:class:`Circle`, :class:`RoundedPolygon` or a
                 general line + arc :class:`PathShape`, e.g.
                 ``PathShape.d_shape(21.2, 17.3)``)
    ``cutouts``  shapes removed from the board.  A cutout that lies completely
                 inside the outer boundary becomes an internal routed cutout;
                 one that crosses the boundary becomes a notch (the boundary
                 is re-computed by boolean subtraction).
    ``holes``    NPTH drilled holes.
    """
    shape: Shape
    cutouts: List[Shape] = field(default_factory=list)
    holes: List[Hole] = field(default_factory=list)

    def add_cutout(self, shape: Shape) -> "Outline":
        """Remove ``shape`` from the board (internal cutout or edge notch)."""
        self.cutouts.append(shape)
        return self

    def add_notch(self, shape: Shape) -> "Outline":
        """Alias of :meth:`add_cutout` for shapes that cross the board edge."""
        return self.add_cutout(shape)

    def add_slot(self, x1: float, y1: float, x2: float, y2: float,
                 width: float) -> "Outline":
        """Add a routed slot (stadium shape)."""
        return self.add_cutout(Slot(x1, y1, x2, y2, width))

    def add_hole(self, x: float, y: float, drill: float, name: str = "") -> "Outline":
        """Add an NPTH drilled hole."""
        self.holes.append(Hole(x, y, drill, name))
        return self

    def polygon(self, tol: float = 0.005):
        """Board area as a shapely polygon (outer boundary minus cutouts; NPTH
        holes are NOT subtracted).  Lazy shapely import."""
        from . import geometry
        return geometry.outline_polygon(self, tol)

    def bounds(self) -> Tuple[float, float, float, float]:
        """(xmin, ymin, xmax, ymax) of the outer boundary."""
        from . import geometry
        return geometry.shape_polygon(self.shape).bounds


@dataclass
class Keepout:
    """Keep-out (KiCad rule area).

    ``layers`` is a tuple of copper layer names or :data:`ALL_LAYERS`.
    Flags say what is forbidden inside the shape.
    """
    shape: Shape
    layers: Union[str, Tuple[str, ...]] = ALL_LAYERS
    tracks: bool = True
    vias: bool = True
    copper: bool = True       # zone fill / pours
    pads: bool = False
    footprints: bool = False
    name: str = ""

    def layer_names(self, copper_layers: Sequence[str]) -> Tuple[str, ...]:
        """Resolve :data:`ALL_LAYERS` against the board's copper layers."""
        if self.layers == ALL_LAYERS:
            return tuple(copper_layers)
        if isinstance(self.layers, str):
            return (self.layers,)
        return tuple(self.layers)


@dataclass
class Plane:
    """Copper plane / pour: ``net`` filled on ``layer``.

    ``shape`` None means "the whole board" (KiCad clips the fill to the board
    edge).  Higher ``priority`` zones are filled first (islands inside a
    bigger plane need a higher priority).
    """
    net: str
    layer: str
    shape: Optional[Shape] = None
    priority: int = 0
    clearance: Optional[float] = None
    min_width: Optional[float] = None
    thermal: bool = False        # thermal reliefs on pads (vias are always solid)
    keep_islands: bool = False
    name: str = ""


# --------------------------------------------------------------------------
# Parts, pins, nets
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Pin:
    """A logical pin: one name, one or more footprint pad numbers, a type."""
    name: str
    pads: Tuple[str, ...]
    etype: str = "passive"

    def __post_init__(self):
        if self.etype not in ELECTRICAL_TYPES:
            raise ValueError("pin %s: unknown electrical type %r (allowed: %s)"
                             % (self.name, self.etype, ", ".join(ELECTRICAL_TYPES)))


PinInput = Union[Pin, str, int, Sequence]


def _as_pads(value) -> Tuple[str, ...]:
    if isinstance(value, (str, int)):
        return (str(value),)
    return tuple(str(v) for v in value)


def make_pin(name: str, spec: PinInput) -> Pin:
    """Normalise the accepted pin shorthand forms into a :class:`Pin`.

    Accepted forms for ``spec``::

        Pin(...)                         # as is (name is overridden)
        "5"  or 5                        # pad 5, type passive
        ("5", "input")                   # pad 5, type input
        (("6", "7"), "power_in")         # pads 6 and 7, type power_in
        ["6", "7"]                       # pads 6 and 7, type passive
    """
    if isinstance(spec, Pin):
        return spec if spec.name == name else Pin(name, spec.pads, spec.etype)
    if isinstance(spec, (str, int)):
        return Pin(name, _as_pads(spec), "passive")
    spec = tuple(spec)
    if len(spec) == 2 and isinstance(spec[1], str) and spec[1] in ELECTRICAL_TYPES:
        return Pin(name, _as_pads(spec[0]), spec[1])
    return Pin(name, _as_pads(spec), "passive")


def two_pin(etype: str = "passive") -> Dict[str, Pin]:
    """Pins of a two-terminal part: names "1" and "2" on pads "1" and "2"."""
    return {"1": Pin("1", ("1",), etype), "2": Pin("2", ("2",), etype)}


def n_pin(n: int, etype: str = "passive", extra: Optional[Dict[str, PinInput]] = None
          ) -> Dict[str, Pin]:
    """Pins "1".."n" on pads "1".."n" (connectors, test pad arrays).  ``extra``
    adds more pins, e.g. ``{"MP": ("MP", "passive")}``."""
    pins = {str(i): Pin(str(i), (str(i),), etype) for i in range(1, n + 1)}
    for k, v in (extra or {}).items():
        pins[k] = make_pin(k, v)
    return pins


@dataclass
class Part:
    """One component instance.

    ``footprint`` is a KiCad library id ``"Lib:Name"`` or a
    :class:`gleda.footprints.FootprintSpec`.  ``pins`` maps pin name to the
    forms accepted by :func:`make_pin`; ``None`` means a two-pin passive.
    Placement is the footprint anchor in board mm, ``rotation`` in degrees CCW
    seen from the top, ``side`` "top" or "bottom".
    """
    ref: str
    value: str
    footprint: Any
    pins: Optional[Dict[str, PinInput]] = None
    mpn: str = ""
    manufacturer: str = ""
    description: str = ""
    distributor: str = ""
    distributor_pn: str = ""
    unit_price: Optional[float] = None
    x: Optional[float] = None
    y: Optional[float] = None
    rotation: float = 0.0
    side: str = TOP
    height_mm: Optional[float] = None
    group: str = "main"
    dnp: bool = False
    #: False for things that are not purchased/placed (test pads, bare pads,
    #: fiducials): no MPN needed, excluded from BOM and pick-and-place.
    in_bom: bool = True
    #: body size override (length along local x, width along local y) for the
    #: mechanical export; default is taken from the footprint fab outline.
    body: Optional[Tuple[float, float]] = None
    #: allow the courtyard to cross the board edge (edge-mounted parts)
    allow_overhang: bool = False
    #: treat as an IC for the decoupling check (default: ref starts with "U")
    is_ic: Optional[bool] = None
    #: free-form extra fields copied to the BOM / footprint properties
    fields: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if self.pins is None:
            self.pins = two_pin()
        self.pins = {str(name): make_pin(str(name), spec) for name, spec in self.pins.items()}
        if self.side not in SIDES:
            raise ValueError("%s: side must be 'top' or 'bottom', got %r" % (self.ref, self.side))

    # -- convenience -------------------------------------------------------
    @property
    def placed(self) -> bool:
        return self.x is not None and self.y is not None

    @property
    def footprint_name(self) -> str:
        """Library id string, or the custom footprint's ``gleda:<name>`` id."""
        fp = self.footprint
        if isinstance(fp, str):
            return fp
        name = getattr(fp, "name", None)
        return "gleda:%s" % name if name else repr(fp)

    @property
    def ref_prefix(self) -> str:
        m = re.match(r"[A-Za-z_#]+", self.ref)
        return m.group(0) if m else ""

    @property
    def ic(self) -> bool:
        return self.ref_prefix == "U" if self.is_ic is None else bool(self.is_ic)

    def pin(self, name: str) -> Pin:
        return self.pins[str(name)]

    def place(self, x: float, y: float, rotation: float = 0.0, side: Optional[str] = None
              ) -> "Part":
        """Set the placement; returns self for chaining."""
        self.x, self.y, self.rotation = float(x), float(y), float(rotation)
        if side is not None:
            if side not in SIDES:
                raise ValueError("side must be 'top' or 'bottom'")
            self.side = side
        return self

    def pad_numbers(self) -> Set[str]:
        """All pad numbers referenced by the pin map."""
        out: Set[str] = set()
        for p in self.pins.values():
            out.update(p.pads)
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ref": self.ref, "value": self.value, "footprint": self.footprint_name,
            "mpn": self.mpn, "manufacturer": self.manufacturer,
            "description": self.description, "distributor": self.distributor,
            "distributor_pn": self.distributor_pn, "unit_price": self.unit_price,
            "x": self.x, "y": self.y, "rotation": self.rotation, "side": self.side,
            "height_mm": self.height_mm, "group": self.group, "dnp": self.dnp,
            "in_bom": self.in_bom,
            "pins": {n: {"pads": list(p.pads), "type": p.etype} for n, p in self.pins.items()},
            "fields": dict(self.fields),
        }


Node = Tuple[str, str]          # (ref, pin name)
NodeInput = Union[str, Sequence[str]]


def parse_node(node: NodeInput) -> Node:
    """``"U1.VDD"`` or ``("U1", "VDD")`` -> ``("U1", "VDD")``.

    The string is split at the FIRST dot so pin names may contain dots
    (``"U1.P0.13"`` -> ``("U1", "P0.13")``).
    """
    if isinstance(node, str):
        if "." not in node:
            raise ValueError("node %r must look like 'REF.PIN'" % (node,))
        ref, pin = node.split(".", 1)
        return (ref, pin)
    ref, pin = node
    return (str(ref), str(pin))


@dataclass
class Net:
    """A named net: list of (ref, pin name) nodes plus class / router options.

    Router options (all optional):

    ``width``     track width override (default: net class width)
    ``max_vias``  maximum number of vias the router may use for this net
    ``layers``    allowed routing layers (default: all signal layers)
    ``no_route``  do not route with tracks (left to a zone / done by hand)
    ``priority``  larger = routed earlier
    ``power_flag`` the net is driven from outside the netlist (battery tab,
                  connector): suppresses the "power input not driven" check
    """
    name: str
    nodes: List[Node] = field(default_factory=list)
    netclass: str = "Default"
    width: Optional[float] = None
    max_vias: Optional[int] = None
    layers: Optional[Tuple[str, ...]] = None
    no_route: bool = False
    priority: int = 0
    power_flag: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name, "netclass": self.netclass,
            "nodes": ["%s.%s" % n for n in self.nodes],
            "width": self.width, "max_vias": self.max_vias,
            "layers": list(self.layers) if self.layers else None,
            "no_route": self.no_route, "priority": self.priority,
            "power_flag": self.power_flag,
        }


@dataclass(frozen=True)
class Track:
    """Routed copper segment (design mm, +y up)."""
    net: str
    layer: str
    x1: float
    y1: float
    x2: float
    y2: float
    width: float

    @property
    def length(self) -> float:
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)


@dataclass(frozen=True)
class Via:
    """Through via (design mm, +y up)."""
    net: str
    x: float
    y: float
    diameter: float
    drill: float


# --------------------------------------------------------------------------
# Design
# --------------------------------------------------------------------------

GROUND_NAME_RE = re.compile(r"^(A|D|P)?(GND|VSS)(_.*|[A-Z0-9]*)?$", re.IGNORECASE)


class Design:
    """The complete design description.

    Parameters
    ----------
    name:            project / file base name
    outline:         :class:`Outline` (or a bare shape)
    layers:          copper layer count (2, 4 or 6; the toolchain targets 4)
    rules:           :class:`Rules` parameter object (default :data:`US_4L_STD`)
    board_thickness: finished thickness in mm (used for the stack-up)
    stackup:         explicit :class:`Stackup` (default: ``Stackup.standard``)
    """

    def __init__(self, name: str, outline: Union[Outline, Shape], layers: int = 4,
                 rules: Rules = US_4L_STD, board_thickness: float = 0.8,
                 stackup: Optional[Stackup] = None, title: str = "",
                 revision: str = "A", company: str = "", date: str = "",
                 silk_refs: bool = False):
        if not re.match(r"^[A-Za-z0-9_.\-]+$", name):
            raise ValueError("design name %r must be a plain file base name" % (name,))
        self.name = name
        self.outline = outline if isinstance(outline, Outline) else Outline(outline)
        self.layers = int(layers)
        self.copper_layers: Tuple[str, ...] = copper_layer_names(self.layers)
        self.rules = rules
        self.board_thickness = float(board_thickness)
        self.stackup = stackup or Stackup.standard(self.layers, self.board_thickness)
        self.title = title or name
        self.revision = revision
        self.company = company
        #: fixed date string for the title block (empty = none; never "now")
        self.date = date
        #: show reference designators on the silkscreen (default: fab layer only)
        self.silk_refs = silk_refs
        self.parts: List[Part] = []
        self.nets: Dict[str, Net] = {}
        self.netclasses: Dict[str, NetClass] = {}
        self.no_connects: Set[Node] = set()
        self.keepouts: List[Keepout] = []
        self.planes: List[Plane] = []
        self.tracks: List[Track] = []
        self.vias: List[Via] = []
        #: nets treated as ground for the decoupling check (None = by name)
        self.ground_nets: Optional[Set[str]] = None
        #: which side(s) of the board have their vias covered by solder mask:
        #: "both" (default), "bottom" (top side open), "top" or "none".
        #: See :data:`VIA_TENTING` and :func:`gleda.board.apply_routing`.
        self.via_tenting: str = "both"
        #: write a ``.kicad_dru`` rule per net class (and per net with a width
        #: override) so that KiCad's DRC rejects tracks narrower than the
        #: class allows; without it KiCad only checks the board minimum.
        self.enforce_track_widths: bool = True
        self.add_netclass("Default", track_width=rules.default_track,
                          clearance=rules.default_clearance)
        self.add_netclass("Power", track_width=rules.power_track,
                          clearance=rules.default_clearance)

    # -- net classes -------------------------------------------------------
    def add_netclass(self, name: str, track_width: Optional[float] = None,
                     clearance: Optional[float] = None,
                     via_diameter: Optional[float] = None,
                     via_drill: Optional[float] = None, description: str = "",
                     min_track_width: Optional[float] = None) -> NetClass:
        """Create or replace a net class; unspecified values come from the
        rules (``default_track``, ``default_clearance``, the standard via).

        A fine-pitch escape class on a board built with :data:`US_4L_FINE`::

            d.add_netclass("Fine", track_width=0.09, clearance=0.09)
            d.net("CAM_D3", "U2.C3", "U1.PC9", netclass="Fine")

        ``min_track_width`` permits neck-downs: KiCad's DRC then accepts
        tracks of this class down to that width instead of ``track_width``.
        """
        r = self.rules
        nc = NetClass(
            name=name,
            track_width=r.default_track if track_width is None else track_width,
            clearance=r.default_clearance if clearance is None else clearance,
            via_diameter=r.via_diameter if via_diameter is None else via_diameter,
            via_drill=r.via_drill if via_drill is None else via_drill,
            description=description,
            min_track_width=min_track_width,
        )
        self.netclasses[name] = nc
        return nc

    # -- parts -------------------------------------------------------------
    def add_part(self, part: Part) -> Part:
        """Add one part (duplicates are reported by the checks, not here)."""
        self.parts.append(part)
        return part

    def add(self, *parts: Part) -> "Design":
        """Add several parts; returns self."""
        for p in parts:
            self.add_part(p)
        return self

    def part(self, ref: str) -> Part:
        """Look a part up by reference (KeyError if absent)."""
        for p in self.parts:
            if p.ref == ref:
                return p
        raise KeyError(ref)

    def has_part(self, ref: str) -> bool:
        return any(p.ref == ref for p in self.parts)

    @property
    def parts_by_ref(self) -> Dict[str, Part]:
        return {p.ref: p for p in self.parts}

    @property
    def groups(self) -> List[str]:
        """Schematic sheet names in order of first use."""
        out: List[str] = []
        for p in self.parts:
            if p.group not in out:
                out.append(p.group)
        return out

    # -- nets --------------------------------------------------------------
    def net(self, name: str, *nodes: NodeInput, netclass: Optional[str] = None,
            **options) -> Net:
        """Create net ``name`` or extend it with more nodes.

        ``nodes`` are ``"REF.PIN"`` strings or ``(ref, pin)`` tuples.  Keyword
        ``options`` set :class:`Net` attributes (width, max_vias, layers,
        no_route, priority, power_flag).
        """
        n = self.nets.get(name)
        if n is None:
            n = Net(name)
            self.nets[name] = n
        for node in nodes:
            parsed = parse_node(node)
            if parsed not in n.nodes:
                n.nodes.append(parsed)
        if netclass is not None:
            n.netclass = netclass
        for key, value in options.items():
            if not hasattr(n, key) or key in ("name", "nodes"):
                raise TypeError("unknown net option %r" % (key,))
            if key == "layers" and value is not None:
                value = tuple(value)
            setattr(n, key, value)
        return n

    connect = net

    def no_connect(self, *nodes: NodeInput) -> "Design":
        """Mark pins as intentionally unconnected."""
        for node in nodes:
            self.no_connects.add(parse_node(node))
        return self

    def pin_nets(self, ref: str, pin: str) -> List[str]:
        """Names of all nets a pin is on (normally zero or one)."""
        key = (ref, str(pin))
        return [n.name for n in self.nets.values() if key in n.nodes]

    def pin_net(self, ref: str, pin: str) -> Optional[str]:
        """Net name of a pin or None."""
        nets = self.pin_nets(ref, pin)
        return nets[0] if nets else None

    def pad_nets(self, ref: str) -> Dict[str, str]:
        """pad number -> net name for one part (unconnected pads are absent)."""
        part = self.part(ref)
        out: Dict[str, str] = {}
        for net in self.nets.values():
            for r, pin in net.nodes:
                if r == ref and pin in part.pins:
                    for pad in part.pins[pin].pads:
                        out.setdefault(pad, net.name)
        return out

    def net_pads(self, name: str) -> List[Tuple[str, str]]:
        """(ref, pad number) pairs on a net, in node order."""
        parts = self.parts_by_ref
        out: List[Tuple[str, str]] = []
        for ref, pin in self.nets[name].nodes:
            part = parts.get(ref)
            if part is None or pin not in part.pins:
                continue
            for pad in part.pins[pin].pads:
                if (ref, pad) not in out:
                    out.append((ref, pad))
        return out

    def connectivity(self) -> Dict[str, Set[str]]:
        """Canonical pad-level connectivity: net name -> {"REF.PAD", ...}.

        This is the form compared against a KiCad netlist export in the
        schematic round trip."""
        return {name: {"%s.%s" % rp for rp in self.net_pads(name)} for name in self.nets}

    def netclass_of(self, net_name: Optional[str]) -> NetClass:
        """Net class object of a net (falls back to Default)."""
        net = self.nets.get(net_name) if net_name else None
        cls = net.netclass if net else "Default"
        return self.netclasses.get(cls, self.netclasses["Default"])

    def track_width(self, net_name: str) -> float:
        """Effective routing width of a net (net override or class width)."""
        net = self.nets.get(net_name)
        if net is not None and net.width is not None:
            return net.width
        return self.netclass_of(net_name).track_width

    def min_track_width(self, net_name: str) -> float:
        """Narrowest track KiCad's DRC accepts on this net.

        This is the smaller of the net's ``width`` override and its class's
        ``min_track_width`` (default: the class ``track_width``), never below
        the board minimum ``rules.min_track``.  With
        ``enforce_track_widths`` (default) the same number is written into the
        board's ``.kicad_dru``; without it only ``rules.min_track`` is checked
        by KiCad."""
        nc = self.netclass_of(net_name)
        width = nc.hard_min_track
        net = self.nets.get(net_name)
        if net is not None and net.width is not None:
            width = min(width, net.width)
        return max(width, self.rules.min_track)

    def via_size(self, net_name: Optional[str] = None) -> Tuple[float, float]:
        """(pad diameter, drill) of the via used for a net (from its class)."""
        nc = self.netclass_of(net_name)
        return (nc.via_diameter, nc.via_drill)

    def clearance(self, net_a: Optional[str], net_b: Optional[str] = None, *,
                  local_a: Optional[float] = None,
                  local_b: Optional[float] = None) -> float:
        """Copper clearance KiCad 7's DRC requires between an item of
        ``net_a`` and an item of a different net ``net_b``.

        Verified against KiCad 7.0.11 (``tests/test_netclasses.py``):

        * normally ``max(clearance of class A, clearance of class B)`` - a
          fine-class track next to Default-class copper needs the Default
          clearance;
        * if either item is a pad with a local clearance override
          (``local_a`` / ``local_b``, see ``PlacedPad.clearance``) the result
          is the larger override instead, whatever the net classes say;
        * never less than the board minimum ``rules.min_clearance``.

        ``None`` (or an unknown name) stands for copper without a net, which
        KiCad puts in the Default class.  Zones additionally keep their own
        clearance (``rules.zone_clearance`` / ``Plane.clearance``).
        """
        floor = self.rules.min_clearance
        overrides = [c for c in (local_a, local_b) if c]
        if overrides:
            return max(max(overrides), floor)
        return max(self.netclass_of(net_a).clearance,
                   self.netclass_of(net_b).clearance, floor)

    def board_minimums(self) -> Dict[str, Any]:
        """Smallest features the fab must be able to make - for the fab README.

        ``min_track`` / ``min_clearance`` are the board-level DRC floors of
        the rule set.  ``smallest_*`` are the smallest values any net class in
        use (or pad clearance override) actually asks for; they can be larger
        than the floors when no fine class is used."""
        r = self.rules
        used = {n.netclass for n in self.nets.values()} | {"Default"}
        classes = [nc for name, nc in self.netclasses.items() if name in used]
        widths = [nc.hard_min_track for nc in classes]
        widths += [n.width for n in self.nets.values() if n.width is not None]
        clearances = [nc.clearance for nc in classes]
        pad_overrides: List[float] = []
        for part in self.parts:
            for pad in getattr(part.footprint, "pads", ()) or ():
                c = getattr(pad, "clearance", None)
                if c:
                    pad_overrides.append(c)
        return {
            "rule_set": r.name,
            "min_track": r.min_track,
            "min_clearance": r.min_clearance,
            "smallest_track_in_use": max(min(widths), r.min_track),
            "smallest_clearance_in_use": max(min(clearances + pad_overrides),
                                             r.min_clearance),
            "smallest_pad_clearance_override": min(pad_overrides) if pad_overrides else None,
            "via_diameter": min(nc.via_diameter for nc in classes),
            "via_drill": min(nc.via_drill for nc in classes),
            "min_annular": r.min_annular,
            "min_drill": r.min_drill,
            "hole_to_hole": r.hole_to_hole,
            "hole_clearance": r.hole_clearance,
            "copper_to_edge": r.copper_to_edge,
            "blind_buried_vias": r.blind_buried_vias,
            "via_tenting": self.via_tenting,
            "net_classes": {
                nc.name: {"track_width": nc.track_width, "clearance": nc.clearance,
                          "min_track_width": nc.hard_min_track,
                          "via_diameter": nc.via_diameter, "via_drill": nc.via_drill,
                          "nets": sorted(n.name for n in self.nets.values()
                                         if n.netclass == nc.name)}
                for nc in sorted(self.netclasses.values(), key=lambda c: c.name)},
        }

    def is_ground(self, net_name: str) -> bool:
        if self.ground_nets is not None:
            return net_name in self.ground_nets
        return bool(GROUND_NAME_RE.match(net_name))

    # -- planes / keepouts ---------------------------------------------------
    def add_plane(self, net: str, layer: str, shape: Optional[Shape] = None,
                  **kwargs) -> Plane:
        """Assign ``net`` to a copper plane / pour on ``layer``."""
        plane = Plane(net, layer, shape, **kwargs)
        self.planes.append(plane)
        return plane

    def add_keepout(self, shape: Shape, layers: Union[str, Sequence[str]] = ALL_LAYERS,
                    **kwargs) -> Keepout:
        """Add a keep-out region (see :class:`Keepout` for the flags)."""
        if not isinstance(layers, str):
            layers = tuple(layers)
        ko = Keepout(shape, layers, **kwargs)
        self.keepouts.append(ko)
        return ko

    def add_body_keepout(self, ref: str, layers: Union[str, Sequence[str]] = ("F.Cu",),
                         margin: float = 0.15, **kwargs) -> Keepout:
        """Keep copper out from under a component body, e.g. no tracks, vias
        or pours on the top layer under a MEMS sensor::

            d.add_body_keepout("U4")                    # F.Cu under top-side U4

        The region is the largest rectangle under the body that stays
        ``margin`` mm away from every pad of the part (so its own pads can
        still be reached from outside); see
        :func:`gleda.geometry.body_keepout_shape`.  ``layers`` defaults to the
        top copper layer - pass ``("B.Cu",)`` for a bottom-side part or
        :data:`ALL_LAYERS`.  Keyword arguments are the :class:`Keepout` flags
        (tracks, vias and copper pours are forbidden by default; note that a
        via keep-out on any layer blocks through vias)."""
        from . import geometry
        shape = geometry.body_keepout_shape(self, ref, margin)
        kwargs.setdefault("name", "under_%s" % ref)
        return self.add_keepout(shape, layers, **kwargs)

    def plane_layers(self, net_name: str) -> List[str]:
        """Layers on which ``net_name`` has a plane / pour."""
        out: List[str] = []
        for p in self.planes:
            if p.net == net_name and p.layer not in out:
                out.append(p.layer)
        return out

    def full_plane_layers(self) -> Dict[str, str]:
        """layer -> net for layers completely given to one whole-board plane."""
        out: Dict[str, str] = {}
        for p in self.planes:
            if p.shape is None:
                out.setdefault(p.layer, p.net)
        return out

    def signal_layers(self) -> Tuple[str, ...]:
        """Copper layers not occupied by a whole-board plane, top to bottom."""
        planes = self.full_plane_layers()
        inner = set(self.copper_layers[1:-1])
        return tuple(l for l in self.copper_layers if not (l in planes and l in inner))

    # -- export --------------------------------------------------------------
    def netlist(self) -> Dict[str, Any]:
        """JSON-able netlist: nets with pin and pad level nodes, no-connects."""
        nets = {}
        for name, net in self.nets.items():
            d = net.to_dict()
            d["pads"] = ["%s.%s" % rp for rp in self.net_pads(name)]
            d["planes"] = self.plane_layers(name)
            nets[name] = d
        return {
            "design": self.name,
            "nets": nets,
            "no_connects": sorted("%s.%s" % n for n in self.no_connects),
        }

    def to_dict(self) -> Dict[str, Any]:
        """JSON-able dump of the whole design (parts, nets, rules, stack-up)."""
        return {
            "name": self.name, "title": self.title, "revision": self.revision,
            "layers": self.layers, "copper_layers": list(self.copper_layers),
            "board_thickness": self.board_thickness,
            "rules": self.rules.to_dict(),
            "stackup": self.stackup.to_dict(),
            "netclasses": {k: v.to_dict() for k, v in self.netclasses.items()},
            "minimums": self.board_minimums(),
            "via_tenting": self.via_tenting,
            "parts": [p.to_dict() for p in self.parts],
            "netlist": self.netlist(),
            "planes": [{"net": p.net, "layer": p.layer, "whole_board": p.shape is None,
                        "priority": p.priority} for p in self.planes],
        }

    def __repr__(self) -> str:
        return "<Design %s: %d parts, %d nets, %d layers>" % (
            self.name, len(self.parts), len(self.nets), self.layers)


__all__ = [
    "TOP", "BOTTOM", "ELECTRICAL_TYPES", "ALL_LAYERS", "Rules", "US_4L_STD", "US_4L_FINE",
    "NetClass", "Stackup", "StackupLayer", "Circle", "RoundedPolygon", "Slot",
    "PathShape", "PathSegment", "VIA_TENTING",
    "Hole", "Outline", "Keepout", "Plane", "Pin", "Part", "Net", "Track", "Via",
    "Design", "make_pin", "two_pin", "n_pin", "parse_node", "copper_layer_names",
    "replace",
]
