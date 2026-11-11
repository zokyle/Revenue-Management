"""Schematic generator: :class:`gleda.model.Design` -> KiCad 7 schematic project.

``generate_schematic(design, out_dir)`` writes a hierarchical KiCad 7 project
that opens in eeschema:

* ``<name>.kicad_sch``            root sheet: one sheet symbol per page, a summary
* ``<name>_<group>.kicad_sch``    one page per schematic group (``Part.group``);
                                  a group that does not fit the largest allowed
                                  paper continues on ``<name>_<group>_2`` ...
* ``gleda.kicad_sym`` + ``sym-lib-table``   the generated symbols as a project
                                  library (they are also embedded in every sheet)
* ``<name>.kicad_pro``            the ``schematic`` / ``sheets`` sections are
                                  added; the board sections written by
                                  :mod:`gleda.board` are kept

What the pages look like (and what they do NOT look like)

* every IC / connector is a generated box symbol: supply pins on top, ground
  pins at the bottom, inputs on the left, outputs on the right, bidirectional
  and passive pins shared between left and right; one schematic pin per
  footprint pad (a pin mapped to several pads is drawn once per pad);
* two-terminal parts are drawn as small horizontal resistor / capacitor /
  inductor / diode / LED / crystal symbols, one-pad parts as a pad symbol;
* **there are no wires between parts**: every pin carries a global label with
  its net name (or a no-connect flag), so connectivity is by name only.  This
  is a netlist drawing, complete and unambiguous, but it does not show signal
  flow the way a hand-drawn schematic does;
* placement is a grid: boxes first (ICs, then connectors, in reference
  order), then the small parts in reference order.  Sizes are computed from
  the text lengths, all connection points are on the 1.27 mm grid, and
  :func:`layout_overlaps` proves that no symbol, label or text box of one
  part overlaps another part's.

Verification: :func:`export_pdf` plots all pages with ``kicad-cli``;
:func:`round_trip` exports KiCad's own netlist of the generated schematic and
compares it net by net and pad by pad with ``Design.connectivity()`` (plus
the component list and the unconnected pins).  ``build_demo_stage`` fails
unless the round trip matches exactly.

This module does not import pcbnew.  Files are deterministic: UUIDs are
derived from the design name and the item's role, nothing depends on time.
"""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .model import Design, Part, Pin, GROUND_NAME_RE
from . import kicad_cli

#: schematic grid in mm (50 mil); every pin end and label anchor is on it
GRID = 1.27
#: KiCad file format written (KiCad 7.0)
SCH_VERSION = 20230121
SYM_LIB_VERSION = 20220914
GENERATOR = "gleda"
SYMBOL_LIB = "gleda"

FONT = 1.27                # text height of pins, labels and fields (mm)
PIN_LEN = 3                # pin length of box symbols (grid units): room for "64"
PIN_PITCH = 2              # pitch of the left / right pins of box symbols (grid units)
TB_PITCH = 3               # pitch of the top / bottom pins (their labels are vertical)
LABEL_FRAME_MM = 3.2       # outline of a global label around its text (both ends)
CELL_GAP = 3               # free grid units between two cells
HEADER_ROWS = 6            # grid units reserved for the page heading

#: usable paper sizes (mm, landscape), smallest first
PAPERS: Tuple[Tuple[str, float, float], ...] = (
    ("A4", 297.0, 210.0), ("A3", 420.0, 297.0), ("A2", 594.0, 420.0),
    ("A1", 841.0, 594.0), ("A0", 1189.0, 841.0),
)
PAGE_MARGIN_MM = 15.0                      # frame + breathing space
TITLE_BLOCK_MM = (112.0, 36.0)             # KiCad's default title block, bottom right

_ETYPE = {
    "power_in": "power_in", "power_out": "power_out", "passive": "passive",
    "input": "input", "output": "output", "bidir": "bidirectional",
    "open_drain": "open_collector", "nc": "no_connect",
}
_LABEL_SHAPE = {
    "power_in": "passive", "power_out": "passive", "passive": "passive",
    "input": "input", "output": "output", "bidir": "bidirectional",
    "open_drain": "bidirectional", "nc": "passive",
}
#: reference prefixes drawn with all pins on one side (connectors, pad rows)
CONNECTOR_PREFIXES = ("J", "P", "CN", "X", "TP")

_UUID_NS = uuid.UUID("6f1d3c0e-58c4-4b0e-9d4f-0c1a5e9a7b21")


class SchematicError(Exception):
    """The design cannot be drawn (or KiCad rejected the generated files)."""


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def _uuid(*parts: Any) -> str:
    """Deterministic UUID for an item (design name + role)."""
    return str(uuid.uuid5(_UUID_NS, "/".join(str(p) for p in parts)))


def _q(text: Any) -> str:
    """Quoted KiCad s-expression string."""
    s = str(text).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return '"%s"' % s


def _mm(g: float) -> str:
    """Grid units -> mm string.  1.27 x integer always has two decimals, so
    two places that format the same grid number produce identical text - the
    way a label is guaranteed to sit exactly on its pin."""
    return ("%.4f" % (g * GRID)).rstrip("0").rstrip(".") if g else "0"


def _num(v: float) -> str:
    return ("%.4f" % v).rstrip("0").rstrip(".") if v else "0"


_WIDE = set("MWmw@%")
_NARROW = set("iIl.,:;|!' 1()[]")


def text_width(text: str, size: float = FONT) -> float:
    """Conservative width in mm of ``text`` in KiCad's stroke font (measured
    with pcbnew for 1.27 mm text: capitals and digits 1.15 - 1.23 mm per
    character, M / W 1.47 mm, lower case 1.0 mm)."""
    total = 0.0
    for ch in text:
        if ch in _WIDE:
            total += 1.17
        elif ch.islower() or ch in "_-+/~":
            total += 0.84
        elif ch in _NARROW:
            total += 0.72
        else:
            total += 0.98
    return total * size


def _grid_len(mm: float) -> int:
    return int(math.ceil(mm / GRID - 1e-9))


def label_length(text: str) -> int:
    """Grid units a global label with this text needs along its direction."""
    return _grid_len(text_width(text) + LABEL_FRAME_MM)


def natural_key(text: str) -> Tuple:
    """Sort key: "R2" < "R10", "PA9" < "PA10"."""
    return tuple((0, int(tok)) if tok.isdigit() else (1, tok)
                 for tok in re.findall(r"\d+|\D+", str(text)))


def _safe_name(text: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_.+\-]", "_", str(text)).strip("_")
    return name or "X"


# --------------------------------------------------------------------------
# symbols
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class SymPin:
    """One schematic pin (= one footprint pad).  ``x``, ``y`` are the
    connection point in symbol grid units with +y UP (KiCad library frame);
    ``side`` is where the pin leaves the body: L, R, T or B."""
    name: str
    number: str
    etype: str
    side: str
    x: int
    y: int


@dataclass
class SymbolDef:
    """A generated library symbol.

    ``box`` is the body rectangle (x0, y0, x1, y1) in grid units, +y UP.
    ``ref_at`` / ``value_at`` are (x, y, justify) of the two visible fields.
    """
    name: str
    kind: str                        # box | two_pin | one_pin
    style: str                       # box, R, C, L, D, LED, PD, XTAL, GEN, PAD
    ref_prefix: str
    pins: Tuple[SymPin, ...]
    box: Tuple[int, int, int, int]
    graphics: Tuple[str, ...]
    ref_at: Tuple[float, float, str]
    value_at: Tuple[float, float, str]
    show_pin_text: bool = True

    @property
    def lib_id(self) -> str:
        return "%s:%s" % (SYMBOL_LIB, self.name)

    def signature(self) -> Tuple:
        return (self.kind, self.style, self.pins, self.box, self.graphics)

    def pin_by_number(self) -> Dict[str, SymPin]:
        return {p.number: p for p in self.pins}


_PIN_ANGLE = {"L": 0, "R": 180, "T": 270, "B": 90}
_STROKE = "(stroke (width 0.254) (type default))"
_THIN = "(stroke (width 0.1524) (type default))"


def _poly(points: Sequence[Tuple[float, float]], fill: str = "none", stroke: str = _STROKE
          ) -> str:
    pts = " ".join("(xy %s %s)" % (_num(x), _num(y)) for x, y in points)
    return "(polyline (pts %s) %s (fill (type %s)))" % (pts, stroke, fill)


def _rect(x0: float, y0: float, x1: float, y1: float, fill: str = "none") -> str:
    return "(rectangle (start %s %s) (end %s %s) %s (fill (type %s)))" % (
        _num(x0), _num(y0), _num(x1), _num(y1), _STROKE, fill)


def _circle(x: float, y: float, r: float, fill: str = "none") -> str:
    return "(circle (center %s %s) (radius %s) %s (fill (type %s)))" % (
        _num(x), _num(y), _num(r), _STROKE, fill)


def _is_ground(design: Design, part: Part, pin: Pin) -> bool:
    net = design.pin_net(part.ref, pin.name)
    if net is not None:
        return design.is_ground(net)
    return bool(GROUND_NAME_RE.match(pin.name)) or pin.name.upper() in ("EP", "PAD", "TAB")


def two_pin_style(part: Part) -> Optional[str]:
    """Drawing style of a two-terminal part, or None if it is not one."""
    pins = list(part.pins.values())
    if len(pins) != 2 or any(len(p.pads) != 1 for p in pins):
        return None
    names = {p.name.upper() for p in pins}
    prefix = part.ref_prefix.upper()
    text = ("%s %s" % (part.value, part.description)).lower()
    if names == {"A", "K"}:
        if "photodiode" in text or prefix == "PD":
            return "PD"
        if prefix == "LED" or "led" in text.split() or re.search(r"\bled\b", text):
            return "LED"
        return "D"
    if any(p.etype not in ("passive",) for p in pins):
        return None
    if prefix == "R":
        return "R"
    if prefix == "C":
        return "C"
    if prefix in ("L", "FB"):
        return "L"
    if prefix in ("Y", "XTAL"):
        return "XTAL"
    if prefix in ("D", "LED"):
        return "D"
    if prefix in CONNECTOR_PREFIXES or prefix == "U":
        return None
    return "GEN"


def _two_pin_graphics(style: str) -> Tuple[str, ...]:
    """Body graphics of a horizontal two-terminal symbol whose pins end at
    x = -2.54 and x = +2.54 mm (pin 'left' = first / anode)."""
    g: List[str] = []
    if style == "R":
        g.append(_rect(-2.54, -0.9, 2.54, 0.9))
    elif style == "C":
        g += [_poly([(-2.54, 0), (-0.45, 0)]), _poly([(0.45, 0), (2.54, 0)]),
              _poly([(-0.45, -1.4), (-0.45, 1.4)]), _poly([(0.45, -1.4), (0.45, 1.4)])]
    elif style == "L":
        g.append(_rect(-2.54, -0.7, 2.54, 0.7, "outline"))
    elif style == "XTAL":
        g += [_poly([(-2.54, 0), (-1.1, 0)]), _poly([(1.1, 0), (2.54, 0)]),
              _poly([(-1.1, -1.4), (-1.1, 1.4)]), _poly([(1.1, -1.4), (1.1, 1.4)]),
              _rect(-0.55, -1.2, 0.55, 1.2)]
    elif style in ("D", "LED", "PD"):
        g += [_poly([(-2.54, 0), (-0.9, 0)]), _poly([(0.9, 0), (2.54, 0)]),
              _poly([(-0.9, 1.1), (-0.9, -1.1), (0.9, 0), (-0.9, 1.1)], "outline"),
              _poly([(0.9, 1.1), (0.9, -1.1)])]
        if style == "LED":       # two arrows leaving the junction
            for dx in (0.0, 0.8):
                g += [_poly([(-0.5 + dx, 1.3), (0.2 + dx, 2.1)], stroke=_THIN),
                      _poly([(-0.2 + dx, 2.1), (0.2 + dx, 2.1), (0.2 + dx, 1.7)], stroke=_THIN)]
        elif style == "PD":      # two arrows arriving
            for dx in (0.0, 0.8):
                g += [_poly([(0.2 + dx, 2.1), (-0.5 + dx, 1.3)], stroke=_THIN),
                      _poly([(-0.5 + dx, 1.7), (-0.5 + dx, 1.3), (-0.1 + dx, 1.3)],
                            stroke=_THIN)]
    else:
        g.append(_rect(-2.54, -1.1, 2.54, 1.1, "background"))
    return tuple(g)


def _two_pin_symbol(part: Part, style: str) -> SymbolDef:
    pins = list(part.pins.values())
    if {p.name.upper() for p in pins} == {"A", "K"}:
        pins.sort(key=lambda p: 0 if p.name.upper() == "A" else 1)     # anode on the left
    left, right = pins
    sym_pins = (SymPin(left.name, left.pads[0], left.etype, "L", -3, 0),
                SymPin(right.name, right.pads[0], right.etype, "R", 3, 0))
    text_y = 2.8 if style in ("LED", "PD") else 2.0       # above the light arrows
    return SymbolDef(name=style if style != "GEN" else "TwoPin", kind="two_pin", style=style,
                     ref_prefix=part.ref_prefix or "X", pins=sym_pins, box=(-2, -1, 2, 1),
                     graphics=_two_pin_graphics(style), ref_at=(-0.4, text_y, "right"),
                     value_at=(0.4, text_y, "left"), show_pin_text=False)


def _one_pin_symbol(part: Part) -> SymbolDef:
    pin = next(iter(part.pins.values()))
    sym_pins = tuple(SymPin(pin.name, pad, pin.etype, "R", 3, -2 * i)
                     for i, pad in enumerate(pin.pads))
    graphics = tuple(_circle(0, -2.54 * i, 1.0, "background") for i in range(len(sym_pins))) \
        + tuple(_poly([(1.0, -2.54 * i), (2.54, -2.54 * i)]) for i in range(len(sym_pins)))
    return SymbolDef(name="Pad", kind="one_pin", style="PAD", ref_prefix=part.ref_prefix or "TP",
                     pins=sym_pins, box=(-1, -2 * (len(sym_pins) - 1) - 1, 1, 1),
                     graphics=graphics, ref_at=(-0.4, 2.0, "right"), value_at=(0.4, 2.0, "left"),
                     show_pin_text=False)


def _split_sides(design: Design, part: Part) -> Dict[str, List[Tuple[Pin, str]]]:
    """Assign every (pin, pad) of a box symbol to a side."""
    sides: Dict[str, List[Tuple[Pin, str]]] = {"T": [], "B": [], "L": [], "R": []}
    flex: List[Pin] = []
    connector = part.ref_prefix.upper() in CONNECTOR_PREFIXES
    for pin in part.pins.values():
        if connector:
            target = "L"
        elif pin.etype == "power_in":
            target = "B" if _is_ground(design, part, pin) else "T"
        elif pin.etype == "input":
            target = "L"
        elif pin.etype in ("output", "power_out", "open_drain"):
            target = "R"
        else:
            flex.append(pin)
            continue
        for pad in pin.pads:
            sides[target].append((pin, pad))
    if connector:
        sides["L"].sort(key=lambda pp: (natural_key(pp[0].name), natural_key(pp[1])))
    # bidirectional / passive / unused pins: fill up the shorter of left and
    # right, in natural name order, unused ("nc") pins last
    flex.sort(key=lambda p: (p.etype == "nc", natural_key(p.name)))
    flex_pads = [(pin, pad) for pin in flex for pad in pin.pads]
    total = len(sides["L"]) + len(sides["R"]) + len(flex_pads)
    to_left = min(len(flex_pads), max(0, (total + 1) // 2 - len(sides["L"])))
    sides["L"] += flex_pads[:to_left]
    sides["R"] += flex_pads[to_left:]
    return sides


def _box_symbol(design: Design, part: Part) -> SymbolDef:
    sides = _split_sides(design, part)

    def names_len(side: str) -> int:
        return max([_grid_len(text_width(pin.name) + 1.0) for pin, _pad in sides[side]] or [0])

    n_left, n_right = len(sides["L"]), len(sides["R"])
    n_top, n_bottom = len(sides["T"]), len(sides["B"])
    wl, wr = names_len("L"), names_len("R")
    centre = _grid_len(max(text_width(part.ref), text_width(part.value)) + 2.0)
    rows = max(n_left, n_right)
    row_h = max(PIN_PITCH * rows, 4)
    top_band = names_len("T") + 1 if n_top else 1
    bottom_band = names_len("B") + 1 if n_bottom else 1
    width = max(wl + wr + centre, TB_PITCH * n_top + 1, TB_PITCH * n_bottom + 1, 8)
    width += width % 2                               # even: the centre is on the grid
    height = top_band + row_h + bottom_band
    # origin = top-left corner of the body; +y up, so the body spans y = 0 .. -height
    pins: List[SymPin] = []
    for i, (pin, pad) in enumerate(sides["L"]):
        pins.append(SymPin(pin.name, pad, pin.etype, "L", -PIN_LEN,
                           -(top_band + 1 + PIN_PITCH * i)))
    for i, (pin, pad) in enumerate(sides["R"]):
        pins.append(SymPin(pin.name, pad, pin.etype, "R", width + PIN_LEN,
                           -(top_band + 1 + PIN_PITCH * i)))
    for side, y in (("T", PIN_LEN), ("B", -height - PIN_LEN)):
        n = len(sides[side])
        x0 = (width - TB_PITCH * (n - 1)) // 2
        for i, (pin, pad) in enumerate(sides[side]):
            pins.append(SymPin(pin.name, pad, pin.etype, side, x0 + TB_PITCH * i, y))
    cx = (wl + (width - wr)) / 2.0
    cy = -(top_band + row_h / 2.0)
    graphics = (_rect(0, 0, width * GRID, -height * GRID, "background"),)
    return SymbolDef(name=_safe_name(part.value or part.ref), kind="box", style="box",
                     ref_prefix=part.ref_prefix or "U", pins=tuple(pins),
                     box=(0, -height, width, 0), graphics=graphics,
                     ref_at=(cx, cy + 1.0, "center"), value_at=(cx, cy - 1.0, "center"))


def make_symbol(design: Design, part: Part) -> SymbolDef:
    """Generated symbol for one part (not yet de-duplicated / named uniquely)."""
    if not part.pins:
        raise SchematicError("%s has no pins" % part.ref)
    if len(part.pins) == 1:
        return _one_pin_symbol(part)
    style = two_pin_style(part)
    if style is not None:
        return _two_pin_symbol(part, style)
    return _box_symbol(design, part)


class SymbolTable:
    """De-duplicates generated symbols and gives each distinct one a unique
    library name (``R``, ``C``, ``STM32U585RIT6``, ``OVM7692`` ...)."""

    def __init__(self) -> None:
        self.by_name: Dict[str, SymbolDef] = {}
        self._by_sig: Dict[Tuple, SymbolDef] = {}

    def intern(self, sym: SymbolDef, hint: str = "") -> SymbolDef:
        sig = sym.signature()
        known = self._by_sig.get(sig)
        if known is not None:
            return known
        name, n = sym.name, 1
        while name in self.by_name:
            n += 1
            name = "%s_%s" % (sym.name, _safe_name(hint) if hint and n == 2 else n)
        sym.name = name
        self.by_name[name] = sym
        self._by_sig[sig] = sym
        return sym


def _font(size: float = FONT, justify: str = "", hide: bool = False) -> str:
    out = "(effects (font (size %s %s))" % (_num(size), _num(size))
    if justify and justify != "center":
        out += " (justify %s)" % justify
    if hide:
        out += " hide"
    return out + ")"


def symbol_sexpr(sym: SymbolDef, lib_prefix: bool, indent: str = "    ") -> str:
    """Library definition of a symbol: for ``lib_symbols`` of a sheet
    (``lib_prefix`` True -> ``"gleda:NAME"``) or for the ``.kicad_sym`` file."""
    full = sym.lib_id if lib_prefix else sym.name
    i1, i2, i3 = indent, indent + "  ", indent + "    "
    head = "%s(symbol %s" % (i1, _q(full))
    if not sym.show_pin_text:
        head += " (pin_numbers hide) (pin_names (offset 0) hide)"
    else:
        head += " (pin_names (offset 0.508))"
    head += " (in_bom yes) (on_board yes)"
    rx, ry, rj = sym.ref_at
    vx, vy, vj = sym.value_at
    lines = [head,
             "%s(property \"Reference\" %s (at %s %s 0) %s)" % (
                 i2, _q(sym.ref_prefix), _mm(rx), _mm(ry), _font(justify=rj)),
             "%s(property \"Value\" %s (at %s %s 0) %s)" % (
                 i2, _q(sym.name), _mm(vx), _mm(vy), _font(justify=vj)),
             "%s(property \"Footprint\" \"\" (at 0 0 0) %s)" % (i2, _font(hide=True)),
             "%s(property \"Datasheet\" \"~\" (at 0 0 0) %s)" % (i2, _font(hide=True)),
             "%s(symbol %s" % (i2, _q(sym.name + "_0_1"))]
    for g in sym.graphics:
        lines.append(i3 + g)
    lines.append(i2 + ")")
    lines.append("%s(symbol %s" % (i2, _q(sym.name + "_1_1")))
    for p in sym.pins:
        length = PIN_LEN if sym.kind == "box" else 1
        lines.append("%s(pin %s line (at %s %s %d) (length %s) (name %s %s) (number %s %s))" % (
            i3, _ETYPE[p.etype], _mm(p.x), _mm(p.y), _PIN_ANGLE[p.side], _mm(length),
            _q(p.name or "~"), _font(), _q(p.number), _font()))
    lines.append(i2 + ")")
    lines.append(i1 + ")")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# layout
# --------------------------------------------------------------------------

Box = Tuple[float, float, float, float]          # x0, y0, x1, y1 in grid units, +y DOWN


@dataclass
class PinPlacement:
    """A pin of a placed symbol: connection point on the sheet (grid units),
    its net (None = no-connect flag) and the label direction."""
    number: str
    name: str
    etype: str
    side: str
    x: int
    y: int
    net: Optional[str]


@dataclass
class Cell:
    """A part with the room it needs: extents (grid units) to the left, right,
    above and below the symbol origin, labels and field texts included."""
    part: Part
    symbol: SymbolDef
    nets: Dict[str, Optional[str]]              # pad number -> net
    left: int = 0
    right: int = 0
    up: int = 0
    down: int = 0
    x: int = 0                                  # symbol origin on the sheet (after placement)
    y: int = 0

    @property
    def width(self) -> int:
        return self.left + self.right

    @property
    def height(self) -> int:
        return self.up + self.down

    def pins(self) -> List[PinPlacement]:
        return [PinPlacement(p.number, p.name, p.etype, p.side, self.x + p.x, self.y - p.y,
                             self.nets.get(p.number)) for p in self.symbol.pins]

    def body_box(self) -> Box:
        x0, y0, x1, y1 = self.symbol.box
        return (self.x + x0, self.y - y1, self.x + x1, self.y - y0)

    def field_boxes(self) -> List[Box]:
        out = []
        for (fx, fy, justify), text in ((self.symbol.ref_at, self.part.ref),
                                        (self.symbol.value_at, self.part.value)):
            w = text_width(text) / GRID
            cx, cy = self.x + fx, self.y - fy
            if justify == "right":
                box = (cx - w, cy - 0.6, cx, cy + 0.6)
            elif justify == "left":
                box = (cx, cy - 0.6, cx + w, cy + 0.6)
            else:
                box = (cx - w / 2.0, cy - 0.6, cx + w / 2.0, cy + 0.6)
            out.append(box)
        return out


def _label_box(pin: PinPlacement) -> Box:
    """Room taken by the global label (or no-connect flag) of a pin."""
    n = label_length(pin.net) if pin.net else 1
    if pin.side == "L":
        return (pin.x - n, pin.y - 1, pin.x, pin.y + 1)
    if pin.side == "R":
        return (pin.x, pin.y - 1, pin.x + n, pin.y + 1)
    if pin.side == "T":
        return (pin.x - 1, pin.y - n, pin.x + 1, pin.y)
    return (pin.x - 1, pin.y, pin.x + 1, pin.y + n)


def make_cell(design: Design, part: Part, symbol: SymbolDef) -> Cell:
    """Measure the room a part needs around its symbol origin."""
    nets = design.pad_nets(part.ref)
    cell = Cell(part, symbol, {p.number: nets.get(p.number) for p in symbol.pins})
    boxes: List[Box] = [cell.body_box()] + cell.field_boxes()
    for pin in cell.pins():
        boxes.append(_label_box(pin))
        boxes.append((pin.x, pin.y, pin.x, pin.y))
    cell.left = int(math.ceil(-min(b[0] for b in boxes) - 1e-9))
    cell.right = int(math.ceil(max(b[2] for b in boxes) - 1e-9))
    cell.up = int(math.ceil(-min(b[1] for b in boxes) - 1e-9))
    cell.down = int(math.ceil(max(b[3] for b in boxes) - 1e-9))
    return cell


@dataclass
class Page:
    """One schematic page: paper, placed cells, heading."""
    group: str
    index: int                                   # 1-based page number within the group
    paper: str
    width: int                                   # grid units
    height: int
    cells: List[Cell] = field(default_factory=list)
    name: str = ""                               # sheet name (unique)
    filename: str = ""
    uuid: str = ""

    def frame(self) -> Box:
        m = _grid_len(PAGE_MARGIN_MM)
        return (m, m, self.width - m, self.height - m)

    def title_block(self) -> Box:
        m = _grid_len(PAGE_MARGIN_MM) - 3
        return (self.width - m - _grid_len(TITLE_BLOCK_MM[0]),
                self.height - m - _grid_len(TITLE_BLOCK_MM[1]), self.width - m,
                self.height - m)


def _paper(name: str) -> Tuple[str, int, int]:
    for pname, w, h in PAPERS:
        if pname == name:
            return pname, int(w // GRID), int(h // GRID)
    raise SchematicError("unknown paper size %r (known: %s)" % (
        name, ", ".join(p[0] for p in PAPERS)))


def _fill_page(page: Page, boxes: Sequence[Cell], smalls: Sequence[Cell],
               column: Optional[Tuple[int, int, int, int]]) -> int:
    """Place as many cells as fit, in order: the box symbols on shelves, then
    the small parts in a uniform grid.  Returns the number of cells placed."""
    x0, y0, x1, y1 = page.frame()
    tb = page.title_block()
    y0 += HEADER_ROWS

    def x_limit(top: int, bottom: int) -> int:
        return tb[0] - CELL_GAP if bottom > tb[1] - CELL_GAP and top < tb[3] else x1

    placed = 0
    x, y, shelf = x0, y0, 0
    for cell in boxes:
        if x > x0 and x + cell.width > x_limit(y, y + cell.height):
            x, y, shelf = x0, y + shelf + CELL_GAP, 0
        if y + cell.height > y1 or x + cell.width > x_limit(y, y + cell.height):
            return placed
        cell.x, cell.y = x + cell.left, y + cell.up
        page.cells.append(cell)
        placed += 1
        x += cell.width + CELL_GAP
        shelf = max(shelf, cell.height)
    if not smalls:
        return placed
    if placed < len(boxes):
        return placed
    left, right, up, down = column or (0, 0, 0, 0)
    cw, ch = left + right + CELL_GAP, up + down + 1
    if shelf:
        y += shelf + CELL_GAP
    x = x0
    for cell in smalls:
        if x > x0 and x + cw - CELL_GAP > x_limit(y, y + ch):
            x, y = x0, y + ch
        if y + ch - 1 > y1 or x + cw - CELL_GAP > x_limit(y, y + ch):
            return placed
        cell.x, cell.y = x + left, y + up
        page.cells.append(cell)
        placed += 1
        x += cw
    return placed


def paginate(group: str, cells: Sequence[Cell], max_paper: str = "A3",
             min_paper: str = "A4") -> List[Page]:
    """Lay the cells of one group out on as few pages as possible, each on the
    smallest paper between ``min_paper`` and ``max_paper`` that holds it."""
    names = [p[0] for p in PAPERS]
    if names.index(min_paper) > names.index(max_paper):
        raise SchematicError("min_paper %s is larger than max_paper %s" % (min_paper, max_paper))
    papers = names[names.index(min_paper):names.index(max_paper) + 1]
    boxes = sorted((c for c in cells if c.symbol.kind == "box"),
                   key=lambda c: (c.part.ref_prefix.upper() != "U", natural_key(c.part.ref)))
    smalls = sorted((c for c in cells if c.symbol.kind != "box"),
                    key=lambda c: natural_key(c.part.ref))
    column = None
    if smalls:
        column = (max(c.left for c in smalls), max(c.right for c in smalls),
                  max(c.up for c in smalls), max(c.down for c in smalls))
    pages: List[Page] = []
    while boxes or smalls:
        best: Optional[Page] = None
        count = 0
        for paper in papers:
            pname, w, h = _paper(paper)
            page = Page(group, len(pages) + 1, pname, w, h)
            count = _fill_page(page, boxes, smalls, column)
            best = page
            if count == len(boxes) + len(smalls):
                break
        if best is None or count == 0:
            first = (boxes or smalls)[0]
            raise SchematicError("%s does not fit on %s paper (it needs %.0f x %.0f mm); "
                                 "raise max_paper" % (first.part.ref, max_paper,
                                                      first.width * GRID, first.height * GRID))
        pages.append(best)
        n_boxes = min(count, len(boxes))
        boxes = boxes[n_boxes:]
        smalls = smalls[count - n_boxes:]
    return pages


def page_boxes(page: Page) -> List[Tuple[str, Box]]:
    """Every drawn item of a page with its bounding box (grid units): symbol
    bodies, pins, labels / no-connect flags and field texts."""
    out: List[Tuple[str, Box]] = []
    for cell in page.cells:
        ref = cell.part.ref
        out.append(("%s body" % ref, cell.body_box()))
        for i, box in enumerate(cell.field_boxes()):
            out.append(("%s %s" % (ref, ("reference", "value")[i]), box))
        for pin in cell.pins():
            out.append(("%s.%s label" % (ref, pin.number), _label_box(pin)))
    return out


def layout_overlaps(page: Page) -> List[str]:
    """Problems of a page layout: items of DIFFERENT parts that overlap, items
    outside the drawing frame or on the title block, and two connection points
    at the same place (which KiCad would connect).  Empty list = clean."""
    problems: List[str] = []
    frame, tb = page.frame(), page.title_block()
    items = page_boxes(page)
    for name, b in items:
        if b[0] < frame[0] - 1e-6 or b[1] < frame[1] - 1e-6 or b[2] > frame[2] + 1e-6 \
                or b[3] > frame[3] + 1e-6:
            problems.append("%s is outside the drawing frame" % name)
        if b[0] < tb[2] and b[2] > tb[0] and b[1] < tb[3] and b[3] > tb[1]:
            problems.append("%s is on the title block" % name)
    eps = 1e-6
    by_part: Dict[str, List[Tuple[str, Box]]] = {}
    for name, b in items:
        by_part.setdefault(name.split(" ")[0].split(".")[0], []).append((name, b))
    refs = sorted(by_part)
    hulls = {r: (min(b[0] for _n, b in by_part[r]), min(b[1] for _n, b in by_part[r]),
                 max(b[2] for _n, b in by_part[r]), max(b[3] for _n, b in by_part[r]))
             for r in refs}
    for i, a in enumerate(refs):
        ha = hulls[a]
        for b in refs[i + 1:]:
            hb = hulls[b]
            if ha[0] < hb[2] - eps and hb[0] < ha[2] - eps and ha[1] < hb[3] - eps \
                    and hb[1] < ha[3] - eps:
                for na, ba in by_part[a]:
                    for nb, bb in by_part[b]:
                        if ba[0] < bb[2] - eps and bb[0] < ba[2] - eps \
                                and ba[1] < bb[3] - eps and bb[1] < ba[3] - eps:
                            problems.append("%s overlaps %s" % (na, nb))
    # within one part: labels must not overlap each other or the field texts
    for ref in refs:
        own = [(n, b) for n, b in by_part[ref] if not n.endswith(" body")]
        for i, (na, ba) in enumerate(own):
            for nb, bb in own[i + 1:]:
                if ba[0] < bb[2] - eps and bb[0] < ba[2] - eps and ba[1] < bb[3] - eps \
                        and bb[1] < ba[3] - eps:
                    problems.append("%s overlaps %s" % (na, nb))
    seen: Dict[Tuple[int, int], str] = {}
    for cell in page.cells:
        for pin in cell.pins():
            key = (pin.x, pin.y)
            if key in seen:
                problems.append("%s.%s and %s share a connection point" % (
                    cell.part.ref, pin.number, seen[key]))
            seen[key] = "%s.%s" % (cell.part.ref, pin.number)
    return problems


# --------------------------------------------------------------------------
# writing sheets
# --------------------------------------------------------------------------

#: longest title KiCad's default title block shows without running over its frame
TITLE_MAX_CHARS = 44


def split_title(title: str, limit: int = TITLE_MAX_CHARS) -> Tuple[str, str]:
    """(title, rest): a title too long for the title block is cut at a
    bracket or a space; the rest goes into a comment line."""
    title = title.strip()
    if len(title) <= limit:
        return title, ""
    cut = title.rfind(" (", 0, limit + 1)
    if cut <= 0:
        cut = title.rfind(" ", 0, limit + 1)
    if cut <= 0:
        cut = limit
    return title[:cut].rstrip(), title[cut:].strip()


def _title_block(design: Design, comments: Sequence[str]) -> str:
    title, rest = split_title(design.title)
    comments = list(comments) + ([rest] if rest else [])
    lines = ["  (title_block", "    (title %s)" % _q(title)]
    if design.date:
        lines.append("    (date %s)" % _q(design.date))
    lines.append("    (rev %s)" % _q(design.revision))
    if design.company:
        lines.append("    (company %s)" % _q(design.company))
    for i, text in enumerate(comments, start=1):
        if text:
            lines.append("    (comment %d %s)" % (i, _q(text)))
    lines.append("  )")
    return "\n".join(lines)


def _text(text: str, x: float, y: float, size: float, uid: str) -> str:
    return "  (text %s (at %s %s 0) %s (uuid %s))" % (
        _q(text), _mm(x), _mm(y), _font(size, "left bottom"), uid)


_LABEL_ANGLE = {"L": (180, "right"), "R": (0, "left"), "T": (90, "left"), "B": (270, "right")}


def _label(net: str, pin: PinPlacement, uid: str) -> str:
    angle, justify = _LABEL_ANGLE[pin.side]
    return ("  (global_label %s (shape %s) (at %s %s %d) %s\n    (uuid %s)\n"
            "    (property \"Intersheetrefs\" \"${INTERSHEET_REFS}\" (at %s %s 0) %s)\n  )" % (
                _q(net), _LABEL_SHAPE[pin.etype], _mm(pin.x), _mm(pin.y), angle,
                _font(justify=justify), uid, _mm(pin.x), _mm(pin.y), _font(hide=True)))


def _hidden_fields(part: Part) -> List[Tuple[str, str]]:
    fields = [("MPN", part.mpn), ("Manufacturer", part.manufacturer),
              ("Distributor", part.distributor), ("Distributor PN", part.distributor_pn),
              ("Description", part.description)]
    if part.unit_price is not None:
        fields.append(("Unit Price", "%g" % part.unit_price))
    if part.height_mm is not None:
        fields.append(("Height", "%g mm" % part.height_mm))
    for key in sorted(part.fields):
        fields.append((str(key), str(part.fields[key])))
    return [(k, v) for k, v in fields if v]


def _instance(design: Design, cell: Cell, sheet_path: str) -> str:
    part, sym = cell.part, cell.symbol
    uid = _uuid(design.name, "symbol", part.ref)
    lines = ["  (symbol (lib_id %s) (at %s %s 0) (unit 1)" % (
        _q(sym.lib_id), _mm(cell.x), _mm(cell.y)),
        "    (in_bom %s) (on_board yes) (dnp %s)" % (
            "yes" if part.in_bom else "no", "yes" if part.dnp else "no"),
        "    (uuid %s)" % uid]
    rx, ry, rj = sym.ref_at
    vx, vy, vj = sym.value_at
    lines.append("    (property \"Reference\" %s (at %s %s 0) %s)" % (
        _q(part.ref), _mm(cell.x + rx), _mm(cell.y - ry), _font(justify=rj)))
    lines.append("    (property \"Value\" %s (at %s %s 0) %s)" % (
        _q(part.value), _mm(cell.x + vx), _mm(cell.y - vy), _font(justify=vj)))
    lines.append("    (property \"Footprint\" %s (at %s %s 0) %s)" % (
        _q(part.footprint_name), _mm(cell.x), _mm(cell.y), _font(hide=True)))
    lines.append("    (property \"Datasheet\" \"~\" (at %s %s 0) %s)" % (
        _mm(cell.x), _mm(cell.y), _font(hide=True)))
    for key, value in _hidden_fields(part):
        lines.append("    (property %s %s (at %s %s 0) %s)" % (
            _q(key), _q(value), _mm(cell.x), _mm(cell.y), _font(hide=True)))
    for p in sym.pins:
        lines.append("    (pin %s (uuid %s))" % (_q(p.number),
                                                  _uuid(design.name, "pin", part.ref, p.number)))
    lines.append("    (instances (project %s (path %s (reference %s) (unit 1))))" % (
        _q(design.name), _q(sheet_path), _q(part.ref)))
    lines.append("  )")
    return "\n".join(lines)


def page_text(design: Design, page: Page, root_uuid: str) -> str:
    """Content of one sub-sheet ``.kicad_sch`` file."""
    symbols: Dict[str, SymbolDef] = {}
    for cell in page.cells:
        symbols.setdefault(cell.symbol.name, cell.symbol)
    out = ["(kicad_sch (version %d) (generator %s)" % (SCH_VERSION, GENERATOR), "",
           "  (uuid %s)" % _uuid(design.name, "sheet-file", page.name), "",
           "  (paper %s)" % _q(page.paper), "",
           _title_block(design, ("Sheet: %s" % page.name,
                                 "Generated by gleda from the design script - do not edit",
                                 "Connectivity is by global label; there are no wires")), "",
           "  (lib_symbols"]
    for name in sorted(symbols):
        out.append(symbol_sexpr(symbols[name], lib_prefix=True))
    out.append("  )")
    out.append("")
    frame = page.frame()
    n_parts = len(page.cells)
    out.append(_text("%s  -  %d part%s" % (page.name, n_parts, "" if n_parts == 1 else "s"),
                     frame[0], frame[1] + 3, 2.54, _uuid(design.name, "heading", page.name)))
    sheet_path = "/%s/%s" % (root_uuid, page.uuid)
    for cell in page.cells:
        for pin in cell.pins():
            uid = _uuid(design.name, "label", cell.part.ref, pin.number)
            if pin.net:
                out.append(_label(pin.net, pin, uid))
            else:
                out.append("  (no_connect (at %s %s) (uuid %s))" % (_mm(pin.x), _mm(pin.y), uid))
    for cell in page.cells:
        out.append(_instance(design, cell, sheet_path))
    out.append(")")
    return "\n".join(out) + "\n"


def _root_text(design: Design, pages: Sequence[Page], root_uuid: str, paper: str) -> str:
    _pname, width, _height = _paper(paper)
    m = _grid_len(PAGE_MARGIN_MM)
    out = ["(kicad_sch (version %d) (generator %s)" % (SCH_VERSION, GENERATOR), "",
           "  (uuid %s)" % root_uuid, "", "  (paper %s)" % _q(paper), "",
           _title_block(design, ("Sheet: root",
                                 "Generated by gleda from the design script - do not edit",
                                 "Connectivity is by global label; there are no wires")), "",
           "  (lib_symbols)", ""]
    out.append(_text(design.title, m, m + 4, 3.0, _uuid(design.name, "root-title")))
    sw, sh, per_row = 30, 8, max(1, (width - 2 * m) // 36)
    y = m + 10
    for i, page in enumerate(pages):
        col, row = i % per_row, i // per_row
        x, yy = m + col * 36, y + row * 16
        refs = sorted((c.part.ref for c in page.cells), key=natural_key)
        out.append("  (sheet (at %s %s) (size %s %s)" % (_mm(x), _mm(yy), _mm(sw), _mm(sh)))
        out.append("    (stroke (width 0.1524) (type solid))")
        out.append("    (fill (color 255 255 194 1.0000))")
        out.append("    (uuid %s)" % page.uuid)
        out.append("    (property \"Sheetname\" %s (at %s %s 0) %s)" % (
            _q(page.name), _mm(x), _mm(yy - 0.6), _font(justify="left bottom")))
        out.append("    (property \"Sheetfile\" %s (at %s %s 0) %s)" % (
            _q(page.filename), _mm(x), _mm(yy + sh + 0.6), _font(justify="left top")))
        out.append("    (instances (project %s (path %s (page %s))))" % (
            _q(design.name), _q("/" + root_uuid), _q(str(i + 2))))
        out.append("  )")
        summary = "%d parts: %s" % (len(refs), " ".join(refs))
        if len(summary) > 24:
            summary = "%d parts: %s ... %s" % (len(refs), refs[0], refs[-1])
        out.append("  (text %s (at %s %s 0) %s (uuid %s))" % (
            _q(summary), _mm(x + 1), _mm(yy + sh / 2.0 + 0.5), _font(justify="left bottom"),
            _uuid(design.name, "root-sheet-note", page.name)))
    rows = (len(pages) + per_row - 1) // per_row
    y_notes = y + rows * 16 + 4
    bom_parts = [p for p in design.parts if p.in_bom]
    board_only = len(design.parts) - len(design.schematic_parts)
    notes = [
        "%d parts (%d on the BOM%s), %d nets, %d copper layers, %.2f mm, rule set %s" % (
            len(design.schematic_parts), len(bom_parts),
            "; plus %d board-only item(s) such as fiducials" % board_only if board_only else "",
            len(design.nets), design.layers, design.board_thickness, design.rules.name),
        "Net classes (track / clearance, mm):",
    ]
    for name in ["Default"] + sorted(n for n in design.netclasses if n != "Default"):
        nc = design.netclasses[name]
        n_nets = sum(1 for n in design.nets.values() if n.netclass == name)
        notes.append("    %-10s %.3f / %.3f    %d nets" % (name, nc.track_width, nc.clearance,
                                                           n_nets))
    for plane in design.planes:
        notes.append("Plane: %s on %s%s" % (plane.net, plane.layer,
                                            " (shared with routing)" if plane.routable else ""))
    notes.append("Every pin carries a global label with its net name; pins without a net "
                 "carry a no-connect flag.")
    notes.append("This schematic is generated from the design script (netlist as code). "
                 "Edit the script, not these files.")
    for i, line in enumerate(notes):
        out.append(_text(line, m, y_notes + 2 * i, FONT, _uuid(design.name, "root-note", i)))
    out.append("")
    out.append("  (sheet_instances (path \"/\" (page \"1\")))")
    out.append(")")
    return "\n".join(out) + "\n"


def symbol_library_text(symbols: Iterable[SymbolDef]) -> str:
    """``gleda.kicad_sym``: all generated symbols as a KiCad symbol library."""
    out = ["(kicad_symbol_lib (version %d) (generator %s)" % (SYM_LIB_VERSION, GENERATOR)]
    for sym in sorted(symbols, key=lambda s: s.name):
        out.append(symbol_sexpr(sym, lib_prefix=False, indent="  "))
    out.append(")")
    return "\n".join(out) + "\n"


SYM_LIB_TABLE = ('(sym_lib_table\n  (lib (name "%s")(type "KiCad")'
                 '(uri "${KIPRJMOD}/%s.kicad_sym")(options "")'
                 '(descr "symbols generated by gleda"))\n)\n' % (SYMBOL_LIB, SYMBOL_LIB))


@dataclass
class SchematicFiles:
    """What :func:`generate_schematic` wrote."""
    directory: str
    root: str
    sheets: List[str]
    pages: List[Page]
    project: Optional[str]
    symbol_library: str
    symbol_table: str
    symbols: Dict[str, SymbolDef]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "root": os.path.basename(self.root),
            "sheets": [{"name": p.name, "file": p.filename, "paper": p.paper,
                        "parts": len(p.cells)} for p in self.pages],
            "project": os.path.basename(self.project) if self.project else None,
            "symbol_library": os.path.basename(self.symbol_library),
            "symbols": sorted(self.symbols),
        }


def build_pages(design: Design, max_paper: str = "A3", min_paper: str = "A4"
                ) -> Tuple[List[Page], Dict[str, SymbolDef]]:
    """Symbols and page layouts of a design (nothing is written)."""
    refs = [p.ref for p in design.schematic_parts]
    dup = sorted({r for r in refs if refs.count(r) > 1})
    if dup:
        raise SchematicError("duplicate reference(s): %s" % ", ".join(dup))
    table = SymbolTable()
    pages: List[Page] = []
    for group in design.groups:
        cells = []
        for part in design.schematic_parts:
            if part.group != group:
                continue
            sym = table.intern(make_symbol(design, part), hint=part.ref)
            cells.append(make_cell(design, part, sym))
        pages += paginate(group, cells, max_paper, min_paper)
    used: Set[str] = set()
    for page in pages:
        base = _safe_name(page.group) if page.index == 1 else "%s_%d" % (
            _safe_name(page.group), page.index)
        name, n = base, 1
        while name.lower() in used:
            n += 1
            name = "%s_%d" % (base, n)
        used.add(name.lower())
        page.name = name
        page.filename = "%s_%s.kicad_sch" % (design.name, name)
        page.uuid = _uuid(design.name, "sheet", name)
    return pages, table.by_name


def write_schematic_project(design: Design, pro_path: str, root_uuid: str,
                            pages: Sequence[Page]) -> str:
    """Add the schematic sections to ``<name>.kicad_pro`` (the file is created
    with the board sections of :func:`gleda.board.project_dict` if missing;
    existing board / net-class sections are left alone)."""
    data: Optional[Dict[str, Any]] = None
    if os.path.exists(pro_path):
        try:
            with open(pro_path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            data = None
    if not isinstance(data, dict):
        from . import board
        data = board.project_dict(design)
    data["schematic"] = {
        "annotate_start_num": 0,
        "drawing": {
            "dashed_lines_dash_length_ratio": 12.0, "dashed_lines_gap_length_ratio": 3.0,
            "default_line_thickness": 6.0, "default_text_size": 50.0,
            "field_names": [], "intersheets_ref_own_page": False,
            "intersheets_ref_prefix": "", "intersheets_ref_short": False,
            "intersheets_ref_show": False, "intersheets_ref_suffix": "",
            "junction_size_choice": 3, "label_size_ratio": 0.375, "pin_symbol_size": 25.0,
            "text_offset_ratio": 0.15,
        },
        "legacy_lib_dir": "", "legacy_lib_list": [],
        "meta": {"version": 1},
        "net_format_name": "", "page_layout_descr_file": "", "plot_directory": "",
        "spice_current_sheet_as_root": False, "spice_external_command": "spice \"%I\"",
        "spice_model_current_sheet_as_root": True, "spice_save_all_currents": False,
        "spice_save_all_voltages": False, "subpart_first_id": 65, "subpart_id_separator": 0,
    }
    data["sheets"] = [[root_uuid, ""]] + [[p.uuid, p.name] for p in pages]
    libs = dict(data.get("libraries") or {})
    libs.setdefault("pinned_footprint_libs", [])
    libs["pinned_symbol_libs"] = [SYMBOL_LIB]
    data["libraries"] = libs
    with open(pro_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return pro_path


def generate_schematic(design: Design, out_dir: str, *, max_paper: str = "A3",
                       min_paper: str = "A4", project: bool = True) -> SchematicFiles:
    """Write the hierarchical schematic of ``design`` into ``out_dir``.

    ``max_paper`` is the largest page used (a group that needs more room is
    continued on further pages).  With ``project`` the ``.kicad_pro`` next to
    the root sheet gets its schematic sections.  Raises
    :class:`SchematicError` if a layout would overlap (a bug - please report)
    or a single part cannot fit ``max_paper``."""
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    pages, symbols = build_pages(design, max_paper, min_paper)
    for page in pages:
        problems = layout_overlaps(page)
        if problems:
            raise SchematicError("layout of sheet %s is not clean: %s" % (
                page.name, "; ".join(problems[:8])))
    root_uuid = _uuid(design.name, "root")
    # sheets of an earlier run of THIS design that are no longer needed: only a
    # file that carries the UUID this generator gives to that sheet is removed
    stale = re.compile(r"^%s_(.+)\.kicad_sch$" % re.escape(design.name))
    wanted = {p.filename for p in pages}
    for fn in sorted(os.listdir(out_dir)):
        m = stale.match(fn)
        if not m or fn in wanted:
            continue
        path = os.path.join(out_dir, fn)
        with open(path, encoding="utf-8", errors="replace") as fh:
            head = fh.read(400)
        if "(uuid %s)" % _uuid(design.name, "sheet-file", m.group(1)) in head:
            os.remove(path)
    sheets = []
    for page in pages:
        path = os.path.join(out_dir, page.filename)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(page_text(design, page, root_uuid))
        sheets.append(path)
    root = os.path.join(out_dir, design.name + ".kicad_sch")
    root_paper = "A4" if len(pages) <= 18 else "A3"
    with open(root, "w", encoding="utf-8") as fh:
        fh.write(_root_text(design, pages, root_uuid, root_paper))
    lib = os.path.join(out_dir, SYMBOL_LIB + ".kicad_sym")
    with open(lib, "w", encoding="utf-8") as fh:
        fh.write(symbol_library_text(symbols.values()))
    table = os.path.join(out_dir, "sym-lib-table")
    with open(table, "w", encoding="utf-8") as fh:
        fh.write(SYM_LIB_TABLE)
    pro = None
    if project:
        pro = write_schematic_project(design, os.path.join(out_dir, design.name + ".kicad_pro"),
                                      root_uuid, pages)
    return SchematicFiles(out_dir, root, sheets, pages, pro, lib, table, symbols)


# --------------------------------------------------------------------------
# kicad-cli: PDF, PNG previews, netlist
# --------------------------------------------------------------------------

_PDF_DATE = re.compile(rb"/CreationDate \(D:\d{14}\)")
PDF_FIXED_DATE = b"/CreationDate (D:20000101000000)"


def normalise_pdf_date(pdf_path: str) -> None:
    """Replace the creation time in a KiCad PDF by a fixed placeholder of the
    same length (2000-01-01), so that re-runs give identical files."""
    with open(pdf_path, "rb") as fh:
        data = fh.read()
    fixed = _PDF_DATE.sub(PDF_FIXED_DATE, data)
    if fixed != data:
        with open(pdf_path, "wb") as fh:
            fh.write(fixed)


def export_pdf(root_sch: str, pdf_path: str) -> str:
    """Plot every sheet into one PDF with ``kicad-cli sch export pdf``."""
    kicad_cli.run_kicad_cli(["sch", "export", "pdf", "--output", pdf_path, root_sch])
    if not os.path.exists(pdf_path) or os.path.getsize(pdf_path) < 1000:
        raise SchematicError("kicad-cli did not create %s" % pdf_path)
    normalise_pdf_date(pdf_path)
    return pdf_path


def pdf_page_count(pdf_path: str) -> int:
    """Number of pages of a PDF (``pdfinfo``)."""
    proc = subprocess.run(["pdfinfo", pdf_path], capture_output=True, text=True)
    m = re.search(r"^Pages:\s+(\d+)", proc.stdout, re.M)
    if proc.returncode != 0 or not m:
        raise SchematicError("pdfinfo failed on %s: %s" % (pdf_path, proc.stderr.strip()))
    return int(m.group(1))


def pdf_to_png(pdf_path: str, out_prefix: str, dpi: int = 100) -> List[str]:
    """Render every page of a PDF to ``<out_prefix>-<n>.png`` (``pdftoppm``)."""
    directory = os.path.dirname(os.path.abspath(out_prefix)) or "."
    base = os.path.basename(out_prefix)
    for fn in sorted(os.listdir(directory)):
        if re.match(r"^%s-\d+\.png$" % re.escape(base), fn):
            os.remove(os.path.join(directory, fn))
    proc = subprocess.run(["pdftoppm", "-png", "-r", str(int(dpi)), pdf_path, out_prefix],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise SchematicError("pdftoppm failed: %s" % proc.stderr.strip())
    return sorted((os.path.join(directory, fn) for fn in os.listdir(directory)
                   if re.match(r"^%s-\d+\.png$" % re.escape(base), fn)), key=natural_key)


def export_netlist(root_sch: str, net_path: str) -> str:
    """KiCad's own netlist of a schematic (``kicad-cli sch export netlist``)."""
    kicad_cli.run_kicad_cli(["sch", "export", "netlist", "--format", "kicadsexpr",
                             "--output", net_path, root_sch])
    if not os.path.exists(net_path):
        raise SchematicError("kicad-cli did not create %s" % net_path)
    return net_path


def parse_sexpr(text: str) -> Any:
    """Minimal s-expression reader: nested lists of strings (quoted strings
    are unescaped; atoms are returned as written)."""
    token = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))')
    stack: List[List[Any]] = [[]]
    pos, n = 0, len(text)
    while pos < n:
        m = token.match(text, pos)
        if not m:
            if text[pos:].strip():
                raise ValueError("bad s-expression near offset %d" % pos)
            break
        pos = m.end()
        if m.group(1):
            stack.append([])
        elif m.group(2):
            if len(stack) < 2:
                raise ValueError("unbalanced ')' at offset %d" % pos)
            done = stack.pop()
            stack[-1].append(done)
        elif m.group(3) is not None:
            stack[-1].append(re.sub(r"\\(.)", lambda k: {"n": "\n"}.get(k.group(1), k.group(1)),
                                    m.group(3)))
        else:
            stack[-1].append(m.group(4))
    if len(stack) != 1:
        raise ValueError("unbalanced '(' in s-expression")
    return stack[0][0] if len(stack[0]) == 1 else stack[0]


def _child(node: Sequence[Any], name: str) -> Optional[List[Any]]:
    for item in node:
        if isinstance(item, list) and item and item[0] == name:
            return item
    return None


def _children(node: Sequence[Any], name: str) -> List[List[Any]]:
    return [item for item in node if isinstance(item, list) and item and item[0] == name]


def _value(node: Sequence[Any], name: str, default: str = "") -> str:
    child = _child(node, name)
    return str(child[1]) if child is not None and len(child) > 1 else default


@dataclass
class KicadNetlist:
    """What a KiCad netlist export says.

    ``components``  ref -> {"value", "footprint", "fields": {name: value}}
    ``nets``        net name -> {"REF.PIN", ...}   (every net KiCad lists)
    ``pin_types``   "REF.PIN" -> KiCad pin type
    """
    components: Dict[str, Dict[str, Any]]
    nets: Dict[str, Set[str]]
    pin_types: Dict[str, str] = field(default_factory=dict)

    def connected(self) -> Dict[str, Set[str]]:
        """Nets without KiCad's automatic ``unconnected-(...)`` single-pin nets."""
        return {n: pins for n, pins in self.nets.items() if not n.startswith("unconnected-")}

    def unconnected(self) -> Set[str]:
        """Pins KiCad reports as not connected to anything."""
        out: Set[str] = set()
        for name, pins in self.nets.items():
            if name.startswith("unconnected-"):
                out |= pins
        return out


def parse_netlist(text: str) -> KicadNetlist:
    """Parse a ``kicadsexpr`` netlist."""
    tree = parse_sexpr(text)
    if not isinstance(tree, list) or not tree or tree[0] != "export":
        raise ValueError("not a KiCad netlist (no 'export' node)")
    components: Dict[str, Dict[str, Any]] = {}
    for comp in _children(_child(tree, "components") or [], "comp"):
        fields = {}
        for f in _children(_child(comp, "fields") or [], "field"):
            name = _value(f, "name")
            fields[name] = str(f[-1]) if len(f) > 2 and not isinstance(f[-1], list) else ""
        for prop in _children(comp, "property"):
            fields.setdefault(_value(prop, "name"), _value(prop, "value"))
        components[_value(comp, "ref")] = {
            "value": _value(comp, "value"), "footprint": _value(comp, "footprint"),
            "fields": fields}
    nets: Dict[str, Set[str]] = {}
    pin_types: Dict[str, str] = {}
    for net in _children(_child(tree, "nets") or [], "net"):
        name = _value(net, "name")
        pins = nets.setdefault(name, set())
        for node in _children(net, "node"):
            key = "%s.%s" % (_value(node, "ref"), _value(node, "pin"))
            pins.add(key)
            pin_types[key] = _value(node, "pintype")
    return KicadNetlist(components, nets, pin_types)


@dataclass
class RoundTrip:
    """Result of comparing a KiCad netlist with the design model."""
    problems: List[str]
    nets_compared: int = 0
    pads_compared: int = 0
    components_compared: int = 0
    unconnected_compared: int = 0

    @property
    def ok(self) -> bool:
        return not self.problems

    def summary(self) -> str:
        if self.ok:
            return ("netlist round trip matches: %d nets, %d pads, %d components, "
                    "%d unconnected pins" % (self.nets_compared, self.pads_compared,
                                             self.components_compared,
                                             self.unconnected_compared))
        return "netlist round trip MISMATCH: %d problem(s)" % len(self.problems)

    def to_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "problems": list(self.problems),
                "nets_compared": self.nets_compared, "pads_compared": self.pads_compared,
                "components_compared": self.components_compared,
                "unconnected_compared": self.unconnected_compared}


_KICAD_ESCAPES = {"dblquote": '"', "quote": "'", "lt": "<", "gt": ">", "backslash": "\\",
                  "slash": "/", "bar": "|", "comma": ",", "colon": ":", "space": " ",
                  "dollar": "$", "tab": "\t", "return": "\n", "brace": "{"}


def kicad_unescape(name: str) -> str:
    """Undo KiCad's net-name escaping (``a{slash}b`` -> ``a/b``)."""
    return re.sub(r"\{(%s)\}" % "|".join(_KICAD_ESCAPES),
                  lambda m: _KICAD_ESCAPES[m.group(1)], name)


def compare_netlist(design: Design, netlist: KicadNetlist) -> RoundTrip:
    """Compare KiCad's view of the schematic with the design model.

    The connectivity must be identical: the same net names, each with exactly
    the same set of ``REF.PAD``; the same components (reference, value,
    footprint, MPN); and exactly the pads without a net in the model must be
    unconnected in KiCad.  Every difference is listed.

    KiCad writes a few characters of a net name in escaped form (``/`` becomes
    ``{slash}``); a KiCad name that matches no design net as written is
    compared in its unescaped form."""
    problems: List[str] = []
    want = {name: pads for name, pads in design.connectivity().items() if pads}
    got: Dict[str, Set[str]] = {}
    for name, pins in netlist.connected().items():
        plain = kicad_unescape(name)
        if name not in want and plain in want and plain not in netlist.nets:
            name = plain
        got[name] = pins
    for name in sorted(set(want) - set(got)):
        problems.append("net %s is missing in the schematic (%d pads)" % (name, len(want[name])))
    for name in sorted(set(got) - set(want)):
        problems.append("schematic has an extra net %s: %s" % (
            name, ", ".join(sorted(got[name], key=natural_key)[:8])))
    pads = 0
    for name in sorted(set(want) & set(got)):
        pads += len(want[name])
        missing = sorted(want[name] - got[name], key=natural_key)
        extra = sorted(got[name] - want[name], key=natural_key)
        if missing:
            problems.append("net %s: schematic lacks %s" % (name, ", ".join(missing)))
        if extra:
            problems.append("net %s: schematic adds %s" % (name, ", ".join(extra)))
    all_pads: Set[str] = set()
    for part in design.schematic_parts:
        for pad in part.pad_numbers():
            all_pads.add("%s.%s" % (part.ref, pad))
    connected: Set[str] = set()
    for pads_of_net in want.values():
        connected |= pads_of_net
    open_want = all_pads - connected
    open_got = netlist.unconnected()
    for key in sorted(open_want - open_got, key=natural_key):
        problems.append("%s has no net in the design but is not an unconnected pin in the "
                        "schematic" % key)
    for key in sorted(open_got - open_want, key=natural_key):
        problems.append("%s is unconnected in the schematic but on a net in the design" % key)
    parts = {p.ref: p for p in design.schematic_parts}
    for ref in sorted(set(parts) - set(netlist.components), key=natural_key):
        problems.append("component %s is missing in the schematic" % ref)
    for ref in sorted(set(netlist.components) - set(parts), key=natural_key):
        problems.append("schematic has an extra component %s" % ref)
    for ref in sorted(set(parts) & set(netlist.components), key=natural_key):
        part, comp = parts[ref], netlist.components[ref]
        if comp["value"] != part.value:
            problems.append("%s: value %r in the schematic, %r in the design" % (
                ref, comp["value"], part.value))
        if comp["footprint"] != part.footprint_name:
            problems.append("%s: footprint %r in the schematic, %r in the design" % (
                ref, comp["footprint"], part.footprint_name))
        if part.mpn and comp["fields"].get("MPN", "") != part.mpn:
            problems.append("%s: MPN %r in the schematic, %r in the design" % (
                ref, comp["fields"].get("MPN", ""), part.mpn))
    return RoundTrip(problems, nets_compared=len(want), pads_compared=pads,
                     components_compared=len(parts), unconnected_compared=len(open_want))


def round_trip(design: Design, root_sch: str, net_path: Optional[str] = None) -> RoundTrip:
    """Export KiCad's netlist of the generated schematic and compare it with
    the design (see :func:`compare_netlist`).  ``net_path`` keeps the netlist
    file (default: next to the root sheet as ``<name>.net``)."""
    if net_path is None:
        net_path = os.path.splitext(root_sch)[0] + ".net"
    export_netlist(root_sch, net_path)
    with open(net_path, encoding="utf-8") as fh:
        text = fh.read()
    # the export time and the absolute project directory are the only things
    # in the file that differ between runs / machines
    fixed = re.sub(r'\(date "[^"]*"\)', '(date "")', text)
    fixed = fixed.replace(os.path.dirname(os.path.abspath(root_sch)) + os.sep, "${KIPRJMOD}/")
    fixed = re.sub(r'\(source "([^"]*)"\)',
                   lambda m: '(source %s)' % _q(os.path.basename(m.group(1))), fixed)
    if fixed != text:
        with open(net_path, "w", encoding="utf-8") as fh:
            fh.write(fixed)
    return compare_netlist(design, parse_netlist(fixed))


# --------------------------------------------------------------------------
# demo build stage
# --------------------------------------------------------------------------

def build_demo_stage(design: Design, out_dir: str, ctx: Dict[str, Any]
                     ) -> Tuple[bool, Dict[str, Any]]:
    """Stage ``schematic`` of ``demo/build_demo.py``: generate, plot, preview
    and round-trip the schematic.  Passes only if KiCad's netlist of the
    generated sheets equals the design's connectivity exactly."""
    def say(msg: str) -> None:
        print("  " + msg, flush=True)

    files = generate_schematic(design, out_dir)
    sub = os.path.join(out_dir, "schematic")
    os.makedirs(sub, exist_ok=True)
    pdf = export_pdf(files.root, os.path.join(sub, design.name + "-schematic.pdf"))
    n_pages = pdf_page_count(pdf)
    previews = pdf_to_png(pdf, os.path.join(sub, design.name + "-schematic"), dpi=150)
    result = round_trip(design, files.root, os.path.join(sub, design.name + ".net"))
    with open(os.path.join(sub, "roundtrip.json"), "w", encoding="utf-8") as fh:
        json.dump(result.to_dict(), fh, indent=1, sort_keys=True)
        fh.write("\n")
    say("%d sheets (%s), %d symbols, PDF with %d pages" % (
        len(files.pages) + 1, ", ".join("%s %s" % (p.name, p.paper) for p in files.pages),
        len(files.symbols), n_pages))
    say(result.summary())
    for problem in result.problems[:20]:
        say("MISMATCH " + problem)
    ok = result.ok and n_pages == len(files.pages) + 1
    if n_pages != len(files.pages) + 1:
        say("PDF has %d pages, expected %d" % (n_pages, len(files.pages) + 1))
    info = dict(files.to_dict())
    info.update({"pdf": os.path.relpath(pdf, out_dir), "pdf_pages": n_pages,
                 "previews": [os.path.relpath(p, out_dir) for p in previews],
                 "round_trip": result.to_dict()})
    return ok, info


__all__ = [
    "SchematicError", "SchematicFiles", "SymbolDef", "SymPin", "Cell", "Page", "KicadNetlist",
    "RoundTrip", "generate_schematic", "build_pages", "make_symbol", "make_cell", "paginate",
    "layout_overlaps", "page_boxes", "page_text", "symbol_sexpr", "symbol_library_text",
    "write_schematic_project", "export_pdf", "pdf_to_png", "pdf_page_count", "export_netlist",
    "parse_sexpr", "parse_netlist", "compare_netlist", "kicad_unescape", "round_trip",
    "normalise_pdf_date",
    "text_width", "label_length", "natural_key", "two_pin_style", "split_title",
    "build_demo_stage",
    "GRID", "PAPERS",
]
