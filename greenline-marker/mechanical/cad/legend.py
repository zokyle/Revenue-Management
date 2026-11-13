"""Legend on the outer face of the FR-4 base plate (spec amendment E10): PLACEHOLDER blocks, their stroke geometry and
the keep-clear zones.

The YAML (base_plate.legend) asks for: maker, model, "Practice device", the statements that docs/COMPLIANCE.md requires,
and a serial-number box, printed in white on the black mask (or laser-marked), at least `clear_of_features` (1.0 mm) from
the ball-foot holes and their mask reliefs, the grain opening and the pad slot.  The wording of the statements is not
frozen (COMPLIANCE.md rows 5 and 33), so this module lays out BLOCKS: three lines of real text (a maker placeholder, the
model, "PRACTICE DEVICE"), two framed blocks reserved for the statements and a framed serial-number box.

Frames of reference
    reading frame (u, v)   the outer face as it is READ: seen from below with the visor at the top; u to the right
    model frame (x, y)     the marker frame, seen from above: x = -u, y = v.  The Gerber data of a bottom-side layer is in
                           this frame (text reads mirrored in the file, correctly on the part)

Everything is drawn with round-ended strokes (a Gerber round aperture), in a small built-in stroke font; nothing is
filled.  geometry() is the ink as a shapely shape in the model frame; fabdata writes the same strokes into the legend
Gerber and check 15 reads that file back and measures the keep-clear distances on what it read.
"""
from __future__ import annotations
import math
from shapely.geometry import LineString, Point, box as sbox
from shapely.ops import unary_union
import params as P

M = P.MECH

# ---------------------------------------------------------------------------------------------- stroke font
# Glyphs on a grid 4 wide x 6 high (cap height = 6 units); each glyph is a list of polylines.
GLYPH_W, GLYPH_H, GLYPH_ADV = 4.0, 6.0, 5.2          # least advance 5.2 units (0.867 x text height); widened by advance() where the print rule needs it
_O = [(1, 0), (0, 1), (0, 5), (1, 6), (3, 6), (4, 5), (4, 1), (3, 0), (1, 0)]
_P = [(0, 0), (0, 6), (3, 6), (4, 5), (4, 4), (3, 3), (0, 3)]
FONT = {
    "A": [[(0, 0), (0, 4), (2, 6), (4, 4), (4, 0)], [(0, 2), (4, 2)]],
    "B": [[(0, 0), (0, 6), (3, 6), (4, 5), (4, 4), (3, 3), (0, 3)], [(3, 3), (4, 2), (4, 1), (3, 0), (0, 0)]],
    "C": [[(4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0), (3, 0), (4, 1)]],
    "D": [[(0, 0), (0, 6), (2.5, 6), (4, 4.5), (4, 1.5), (2.5, 0), (0, 0)]],
    "E": [[(4, 6), (0, 6), (0, 0), (4, 0)], [(0, 3), (3, 3)]],
    "F": [[(4, 6), (0, 6), (0, 0)], [(0, 3), (3, 3)]],
    "G": [[(4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0), (3, 0), (4, 1), (4, 3), (2, 3)]],
    "H": [[(0, 0), (0, 6)], [(4, 0), (4, 6)], [(0, 3), (4, 3)]],
    "I": [[(1, 0), (3, 0)], [(2, 0), (2, 6)], [(1, 6), (3, 6)]],
    "J": [[(0, 1), (1, 0), (3, 0), (4, 1), (4, 6)]],
    "K": [[(0, 0), (0, 6)], [(4, 6), (0, 2.5)], [(1.4, 3.7), (4, 0)]],
    "L": [[(0, 6), (0, 0), (4, 0)]],
    "M": [[(0, 0), (0, 6), (2, 3), (4, 6), (4, 0)]],
    "N": [[(0, 0), (0, 6), (4, 0), (4, 6)]],
    "O": [_O],
    "P": [_P],
    "Q": [_O, [(2.5, 1.5), (4, 0)]],
    "R": [_P, [(2, 3), (4, 0)]],
    "S": [[(4, 5), (3, 6), (1, 6), (0, 5), (0, 4), (1, 3), (3, 3), (4, 2), (4, 1), (3, 0), (1, 0), (0, 1)]],
    "T": [[(0, 6), (4, 6)], [(2, 6), (2, 0)]],
    "U": [[(0, 6), (0, 1), (1, 0), (3, 0), (4, 1), (4, 6)]],
    "V": [[(0, 6), (2, 0), (4, 6)]],
    "W": [[(0, 6), (1, 0), (2, 4), (3, 0), (4, 6)]],
    "X": [[(0, 0), (4, 6)], [(0, 6), (4, 0)]],
    "Y": [[(0, 6), (2, 3), (4, 6)], [(2, 3), (2, 0)]],
    "Z": [[(0, 6), (4, 6), (0, 0), (4, 0)]],
    "0": [_O, [(0.8, 1.2), (3.2, 4.8)]],
    "1": [[(1, 4.5), (2, 6), (2, 0)], [(1, 0), (3, 0)]],
    "2": [[(0, 5), (1, 6), (3, 6), (4, 5), (4, 4), (0, 0), (4, 0)]],
    "3": [[(0, 5), (1, 6), (3, 6), (4, 5), (4, 4), (3, 3), (1.5, 3)], [(3, 3), (4, 2), (4, 1), (3, 0), (1, 0), (0, 1)]],
    "4": [[(3, 0), (3, 6), (0, 2), (4, 2)]],
    "5": [[(4, 6), (0, 6), (0, 3.5), (3, 3.5), (4, 2.5), (4, 1), (3, 0), (1, 0), (0, 1)]],
    "6": [[(4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0), (3, 0), (4, 1), (4, 2.5), (3, 3.5), (0, 3.5)]],
    "7": [[(0, 6), (4, 6), (1.5, 0)]],
    "8": [[(1, 3), (0, 4), (0, 5), (1, 6), (3, 6), (4, 5), (4, 4), (3, 3), (1, 3), (0, 2), (0, 1), (1, 0), (3, 0), (4, 1), (4, 2), (3, 3)]],
    "9": [[(0, 1), (1, 0), (3, 0), (4, 1), (4, 5), (3, 6), (1, 6), (0, 5), (0, 3.5), (1, 2.5), (4, 2.5)]],
    "-": [[(0.5, 3), (3.5, 3)]],
    "/": [[(0, 0), (4, 6)]],
    ".": [[(1.8, 0), (2.2, 0), (2.2, 0.4), (1.8, 0.4), (1.8, 0)]],
    ":": [[(1.8, 1), (2.2, 1), (2.2, 1.4), (1.8, 1.4), (1.8, 1)], [(1.8, 4), (2.2, 4), (2.2, 4.4), (1.8, 4.4), (1.8, 4)]],
    " ": [],
}


def advance(h, stroke=None):
    """Character pitch (mm) of text of cap height h drawn with line width `stroke`: the font's own advance, widened where
    needed so that the CLEAR space between two neighbouring letters (pitch - glyph width - line width) is at least the line
    width and at least MECH['legend_min_gap'].  (At the 1.0 mm minimum height the font's own advance would leave 0.05 mm
    between letters with vertical edges, which a legend print fills in.)"""
    stroke = M["legend_stroke"] if stroke is None else stroke
    k = h / GLYPH_H
    return max(GLYPH_ADV * k, GLYPH_W * k + stroke + max(stroke, M["legend_min_gap"]))


def letter_gap(h, stroke=None):
    """Clear space between two neighbouring letters of full width (mm)."""
    stroke = M["legend_stroke"] if stroke is None else stroke
    return advance(h, stroke) - GLYPH_W * h / GLYPH_H - stroke


def text_width(text, h, stroke=None):
    """Width of a line of text of cap height h (first stroke centre to last stroke centre)."""
    k = h / GLYPH_H
    return ((len(text) - 1) * advance(h, stroke) + GLYPH_W * k) if text else 0.0


def text_strokes(text, h, centre, stroke=None):
    """Polylines (reading frame) of `text`, cap height h, centred on `centre` (u, v), spaced for line width `stroke`."""
    k = h / GLYPH_H
    adv = advance(h, stroke)
    u0 = centre[0] - text_width(text, h, stroke) / 2
    v0 = centre[1] - h / 2
    out = []
    for i, ch in enumerate(text.upper()):
        if ch not in FONT:
            raise KeyError(f"legend font has no glyph for {ch!r}")
        for pl in FONT[ch]:
            out.append([(u0 + i * adv + x * k, v0 + y * k) for x, y in pl])
    return out


# ---------------------------------------------------------------------------------------------- the placeholder blocks
def blocks():
    """The legend blocks in the READING frame.  kind 'text': one line of stroke text.  kind 'frame': a framed rectangle
    reserved for content that is not frozen (its label is placeholder text).  `rect` = (u0, v0, u1, v1) is the INSIDE of a
    frame; the frame line is centred on it."""
    s, sf = M["legend_stroke"], M["legend_frame_stroke"]
    out = [
        dict(name="maker", kind="text", text="MAKER NAME", h=1.5, centre=(0.0, 9.6), stroke=s, content="maker (placeholder: name or mark of the maker)"),
        dict(name="model", kind="text", text="GL-1", h=2.2, centre=(0.0, 6.9), stroke=0.25, content='model "GL-1"'),
        dict(name="practice", kind="text", text="PRACTICE DEVICE", h=1.2, centre=(0.0, 4.6), stroke=s, content='"Practice device"'),
        dict(name="statements_1", kind="frame", rect=(8.0, -4.8, 19.5, 3.0), stroke=sf, label=["STATEMENTS", "RESERVED 1"], label_h=1.0,
             content="reserved for the statements of docs/COMPLIANCE.md (text not frozen)"),
        dict(name="statements_2", kind="frame", rect=(-19.5, -4.8, -8.0, 3.0), stroke=sf, label=["STATEMENTS", "RESERVED 2"], label_h=1.0,
             content="reserved for the statements of docs/COMPLIANCE.md (text not frozen)"),
        dict(name="serial", kind="frame", rect=(-7.0, -14.6, 7.0, -11.8), stroke=sf, label=["S/N"], label_h=1.4, label_at="left",
             content="serial-number box: the number is marked inside it per unit (laser or ink-jet)"),
    ]
    return out


REQUIRED = ("maker", "model", "practice", "statements", "serial")      # block names (or name prefixes) the YAML content asks for


def block_strokes(b):
    """[(polyline in the reading frame, stroke width)] of one block."""
    out = []
    if b["kind"] == "text":
        out += [(pl, b["stroke"]) for pl in text_strokes(b["text"], b["h"], b["centre"], b["stroke"])]
    else:
        u0, v0, u1, v1 = b["rect"]
        out.append(([(u0, v0), (u1, v0), (u1, v1), (u0, v1), (u0, v0)], b["stroke"]))
        lab, h = b.get("label") or [], b.get("label_h", 1.0)
        if b.get("label_at") == "left":
            cu = u0 + 0.7 + text_width(lab[0], h, M["legend_stroke"]) / 2
            out += [(pl, M["legend_stroke"]) for pl in text_strokes(lab[0], h, (cu, 0.5 * (v0 + v1)), M["legend_stroke"])]
        else:
            n = len(lab)
            for i, line in enumerate(lab):
                cv = 0.5 * (v0 + v1) + ((n - 1) / 2 - i) * 1.6 * h
                out += [(pl, M["legend_stroke"]) for pl in text_strokes(line, h, (0.5 * (u0 + u1), cv), M["legend_stroke"])]
    return out


def to_model(pl):
    """Reading frame -> model frame (the outer face is read from below: x = -u)."""
    return [(-u, v) for u, v in pl]


def strokes(blks=None):
    """Every stroke of the legend in the MODEL frame: [(polyline, width, block name)]."""
    out = []
    for b in (blocks() if blks is None else blks):
        out += [(to_model(pl), w, b["name"]) for pl, w in block_strokes(b)]
    return out


def geometry(blks=None, by_block=False):
    """The ink (strokes with their width, round ends) as a shapely shape in the model frame; by_block=True -> {name: shape}."""
    per = {}
    for pl, w, name in strokes(blks):
        g = (LineString(pl) if len(pl) > 1 else Point(pl[0])).buffer(w / 2, 16)
        per.setdefault(name, []).append(g)
    per = {n: unary_union(g) for n, g in per.items()}
    return per if by_block else unary_union(list(per.values()))


def reading_geometry(blks=None):
    """The ink as it is READ on the part (reading frame: seen from below, visor at the top, u to the right), built from the
    block strokes WITHOUT to_model().  Check 15 mirrors the legend layer it read back (x -> -x, the rule for every bottom
    layer) and compares it with this shape: an independent test that the file is mirrored and the text reads correctly."""
    parts_ = []
    for b in (blocks() if blks is None else blks):
        for pl, w in block_strokes(b):
            parts_.append((LineString(pl) if len(pl) > 1 else Point(pl[0])).buffer(w / 2, 16))
    return unary_union(parts_)


def block_extent(b):
    """Outer extent (u0, v0, u1, v1) of a block's ink in the reading frame."""
    g = unary_union([(LineString(pl) if len(pl) > 1 else Point(pl[0])).buffer(w / 2, 16) for pl, w in block_strokes(b)])
    return g.bounds


def capacity(b, h=None):
    """(characters per line, lines) of text of cap height h that fit inside a frame block with a 0.5 mm margin and a line
    pitch of 1.5 x h, at the character pitch of advance() (the least line width, so the letters keep legend_min_gap)."""
    h = M["legend_min_text_h"] if h is None else h
    u0, v0, u1, v1 = b["rect"]
    w, ht = (u1 - u0) - 1.0, (v1 - v0) - 1.0
    k = h / GLYPH_H
    return max(0, int((w - GLYPH_W * k) / advance(h) + 1e-9) + 1), max(0, int((ht - h) / (1.5 * h) + 1e-9) + 1)


def fixture_footprints():
    """Where fixtures bear on the outer face (model frame), each grown by the play of its location: {name: shape}.  The
    legend must keep MECH['legend_registration'] from every one of them (check 15).  All lie inside the seat zones."""
    out = {}
    g, br, c = P.GAUGE, P.BRIDGE, P.CAL
    for i, (x, y) in enumerate(P.BALL_XY):
        out[f"ball gauge plate, boss {i + 1} (dia {g['boss_od']} + {g['locate_tol']} location)"] = Point(x, y).buffer(g["boss_od"] / 2 + g["locate_tol"], 128)
        out[f"calibration seat pad {i + 1} (dia {c['pad_od']} + {c['locate_tol']} location)"] = Point(x, y).buffer(c["pad_od"] / 2 + c["locate_tol"], 128)
        out[f"bridge gauge, foot {i + 1} (dia {br['foot_od']} + {P.BRIDGE_FOOT_PLAY:.2f} play on the ball)"] = Point(x, y).buffer(br["foot_od"] / 2 + P.BRIDGE_FOOT_PLAY, 128)
    return out


def seat_zones():
    """Legend-free zones round the ball feet (model frame): the annular seat pads of the base-face calibration plate
    (GL1-050) bear on the bare mask there, with the location tolerance of the marker on the plate and the registration of
    the legend print added.  A mechanical-only requirement (not in the YAML): a legend print stands about 0.02 mm proud."""
    return [Point(x, y).buffer(P.CAL_LEGEND_ZONE_D / 2, 128) for x, y in P.BALL_XY]


def feature_shapes(mask_relief=True):
    """The features the YAML keeps the legend away from, as shapes in the model frame built from params (used by the
    drawing; check 15 measures against the plate SOLID and the mask layer read back)."""
    out = {}
    for i, (x, y) in enumerate(P.BALL_XY):
        out[f"ball-foot hole {i + 1} with its mask relief"] = Point(x, y).buffer((P.BALL_HOLE_D + (M["fr4_mask_relief"] if mask_relief else 0.0)) / 2, 128)
    out["grain opening"] = Point(P.GRAIN_X, P.GRAIN_Y).buffer(P.GRAIN_R, 256)
    r = P.PAD_HOLE_D / 2
    xa, xb = min(P.PAD_XS), max(P.PAD_XS)
    out["pad slot"] = sbox(xa, P.PAD_Y - r, xb, P.PAD_Y + r).union(Point(xa, P.PAD_Y).buffer(r, 64)).union(Point(xb, P.PAD_Y).buffer(r, 64))
    return out
