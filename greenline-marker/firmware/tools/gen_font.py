#!/usr/bin/env python3
"""Generate core/gl_font_data.c (5x7 font and small bitmap icons) from the
ASCII art in this file.

Usage:
    gen_font.py [--check] [--show] <output gl_font_data.c>

--check : do not write; exit 1 if the existing file is stale.
--show  : print every glyph and icon to stdout for a visual check.

The art below is original work for this project: a plain upper-case 5x7
face covering ASCII 0x20..0x5F (the firmware maps lower case to upper case).
'#' = ink, '.' = background.  Each glyph is exactly 7 rows of 5 columns.
"""
import sys

GLYPH_W, GLYPH_H = 5, 7
FIRST, LAST = 0x20, 0x5F

FONT_ART = r"""
SP
.....
.....
.....
.....
.....
.....
.....
!
..#..
..#..
..#..
..#..
..#..
.....
..#..
"
.#.#.
.#.#.
.#.#.
.....
.....
.....
.....
#
.#.#.
.#.#.
#####
.#.#.
#####
.#.#.
.#.#.
$
..#..
.####
#.#..
.###.
..#.#
####.
..#..
%
##...
##..#
...#.
..#..
.#...
#..##
...##
&
.##..
#..#.
#.#..
.#...
#.#.#
#..#.
.##.#
'
..#..
..#..
.#...
.....
.....
.....
.....
(
...#.
..#..
.#...
.#...
.#...
..#..
...#.
)
.#...
..#..
...#.
...#.
...#.
..#..
.#...
*
.....
..#..
#.#.#
.###.
#.#.#
..#..
.....
+
.....
..#..
..#..
#####
..#..
..#..
.....
,
.....
.....
.....
.....
.##..
..#..
.#...
-
.....
.....
.....
#####
.....
.....
.....
.
.....
.....
.....
.....
.....
.##..
.##..
/
.....
....#
...#.
..#..
.#...
#....
.....
0
.###.
#...#
#..##
#.#.#
##..#
#...#
.###.
1
..#..
.##..
..#..
..#..
..#..
..#..
.###.
2
.###.
#...#
....#
...#.
..#..
.#...
#####
3
#####
...#.
..#..
...#.
....#
#...#
.###.
4
...#.
..##.
.#.#.
#..#.
#####
...#.
...#.
5
#####
#....
####.
....#
....#
#...#
.###.
6
..##.
.#...
#....
####.
#...#
#...#
.###.
7
#####
....#
...#.
..#..
.#...
.#...
.#...
8
.###.
#...#
#...#
.###.
#...#
#...#
.###.
9
.###.
#...#
#...#
.####
....#
...#.
.##..
:
.....
.##..
.##..
.....
.##..
.##..
.....
;
.....
.##..
.##..
.....
.##..
..#..
.#...
<
...#.
..#..
.#...
#....
.#...
..#..
...#.
=
.....
.....
#####
.....
#####
.....
.....
>
.#...
..#..
...#.
....#
...#.
..#..
.#...
?
.###.
#...#
....#
...#.
..#..
.....
..#..
@
.###.
#...#
....#
.##.#
#.#.#
#.#.#
.###.
A
.###.
#...#
#...#
#...#
#####
#...#
#...#
B
####.
#...#
#...#
####.
#...#
#...#
####.
C
.###.
#...#
#....
#....
#....
#...#
.###.
D
###..
#..#.
#...#
#...#
#...#
#..#.
###..
E
#####
#....
#....
####.
#....
#....
#####
F
#####
#....
#....
####.
#....
#....
#....
G
.###.
#...#
#....
#.###
#...#
#...#
.####
H
#...#
#...#
#...#
#####
#...#
#...#
#...#
I
.###.
..#..
..#..
..#..
..#..
..#..
.###.
J
..###
...#.
...#.
...#.
...#.
#..#.
.##..
K
#...#
#..#.
#.#..
##...
#.#..
#..#.
#...#
L
#....
#....
#....
#....
#....
#....
#####
M
#...#
##.##
#.#.#
#.#.#
#...#
#...#
#...#
N
#...#
#...#
##..#
#.#.#
#..##
#...#
#...#
O
.###.
#...#
#...#
#...#
#...#
#...#
.###.
P
####.
#...#
#...#
####.
#....
#....
#....
Q
.###.
#...#
#...#
#...#
#.#.#
#..#.
.##.#
R
####.
#...#
#...#
####.
#.#..
#..#.
#...#
S
.####
#....
#....
.###.
....#
....#
####.
T
#####
..#..
..#..
..#..
..#..
..#..
..#..
U
#...#
#...#
#...#
#...#
#...#
#...#
.###.
V
#...#
#...#
#...#
#...#
#...#
.#.#.
..#..
W
#...#
#...#
#...#
#.#.#
#.#.#
#.#.#
.#.#.
X
#...#
#...#
.#.#.
..#..
.#.#.
#...#
#...#
Y
#...#
#...#
#...#
.#.#.
..#..
..#..
..#..
Z
#####
....#
...#.
..#..
.#...
#....
#####
[
.###.
.#...
.#...
.#...
.#...
.#...
.###.
\
.....
#....
.#...
..#..
...#.
....#
.....
]
.###.
...#.
...#.
...#.
...#.
...#.
.###.
^
..#..
.#.#.
#...#
.....
.....
.....
.....
_
.....
.....
.....
.....
.....
.....
#####
"""

# Icons: name, then rows of equal width (max 16 columns).
ICON_ART = r"""
FLAG
..######.
..#####..
..####...
..###....
..##.....
..#......
..#......
..#......
..#......
..#......
.###.....
NOFLAG
#.######.
.######..
..####...
..###....
..###....
..#.#....
..#..#...
..#...#..
..#....#.
..#.....#
.###.....
BOLT
....##.
...##..
..##...
.#####.
...##..
..##...
.##....
CHECK
........#
.......#.
......#..
#....#...
.#..#....
..##.....
..#......
CROSS
#.....#
.#...#.
..#.#..
...#...
..#.#..
.#...#.
#.....#
WARN
.....#.....
....#.#....
....#.#....
...#...#...
...#.#.#...
..#..#..#..
..#..#..#..
.#.......#.
.#...#...#.
###########
USB
..#####..
..#.#.#..
..#####..
.#######.
.#.....#.
.#.....#.
.#.....#.
..#####..
...###...
....#....
....#....
"""


def parse_blocks(art, fixed_h=None):
    """Return [(name, [rows])] from the art text."""
    lines = [ln for ln in art.strip("\n").split("\n")]
    blocks = []
    i = 0
    while i < len(lines):
        name = lines[i]
        i += 1
        rows = []
        while i < len(lines) and len(lines[i]) > 0 and set(lines[i]) <= set("#."):
            # A glyph name can itself be '#' or '.': the first line of a
            # block is always the name, handled above.
            rows.append(lines[i])
            i += 1
            if fixed_h is not None and len(rows) == fixed_h:
                break
        blocks.append((name, rows))
    return blocks


def build_font():
    blocks = parse_blocks(FONT_ART, GLYPH_H)
    glyphs = {}
    for name, rows in blocks:
        ch = " " if name == "SP" else name
        if len(ch) != 1:
            raise SystemExit("bad glyph name %r" % name)
        if len(rows) != GLYPH_H or any(len(r) != GLYPH_W for r in rows):
            raise SystemExit("glyph %r is not %dx%d" % (ch, GLYPH_W, GLYPH_H))
        if ch in glyphs:
            raise SystemExit("duplicate glyph %r" % ch)
        glyphs[ch] = rows
    missing = [chr(c) for c in range(FIRST, LAST + 1) if chr(c) not in glyphs]
    if missing:
        raise SystemExit("missing glyphs: %r" % missing)
    return glyphs


def build_icons():
    icons = []
    for name, rows in parse_blocks(ICON_ART):
        w = len(rows[0])
        if w > 16 or any(len(r) != w for r in rows):
            raise SystemExit("icon %s: ragged or wider than 16" % name)
        icons.append((name, w, rows))
    return icons


def generate():
    glyphs = build_font()
    icons = build_icons()
    out = []
    w = out.append
    w("/*")
    w(" * gl_font_data.c - GENERATED by tools/gen_font.py.  DO NOT EDIT.")
    w(" * Run `make config` after changing the art in the generator.")
    w(" *")
    w(" * 5x7 font, ASCII 0x%02X..0x%02X, 7 bytes per glyph: one byte per row, top" %
      (FIRST, LAST))
    w(" * row first, bit 4 = leftmost column.  Icons: one uint16_t per row, bit 15")
    w(" * = leftmost column.")
    w(" */")
    w('#include "gl_gfx.h"')
    w("")
    w("const uint8_t gl_font5x7[GL_FONT_GLYPHS][GL_FONT_H] = {")
    for code in range(FIRST, LAST + 1):
        rows = glyphs[chr(code)]
        vals = []
        for r in rows:
            v = 0
            for c in r:
                v = (v << 1) | (1 if c == "#" else 0)
            vals.append("0x%02Xu" % v)
        label = chr(code) if chr(code) not in ("\\",) else "backslash"
        w("    { %s }, /* 0x%02X %s */" % (", ".join(vals), code, label))
    w("};")
    w("")
    for name, width, rows in icons:
        vals = []
        for r in rows:
            v = 0
            for c in r:
                v = (v << 1) | (1 if c == "#" else 0)
            v <<= (16 - width)
            vals.append("0x%04Xu" % v)
        w("static const uint16_t icon_%s_rows_[%d] = { %s };" %
          (name.lower(), len(rows), ", ".join(vals)))
    w("")
    w("const gl_icon_bitmap_t gl_icons[GL_ICON_COUNT] = {")
    for name, width, rows in icons:
        w("    { %d, %d, icon_%s_rows_ }, /* GL_ICON_%s */" %
          (width, len(rows), name.lower(), name))
    w("};")
    return "\n".join(out) + "\n", glyphs, icons


def main(argv):
    flags = [a for a in argv[1:] if a.startswith("--")]
    args = [a for a in argv[1:] if not a.startswith("--")]
    text, glyphs, icons = generate()
    if "--show" in flags:
        for code in range(FIRST, LAST + 1):
            print("0x%02X %r" % (code, chr(code)))
            for r in glyphs[chr(code)]:
                print("   " + r.replace(".", " "))
        for name, _, rows in icons:
            print(name)
            for r in rows:
                print("   " + r.replace(".", " "))
    if len(args) != 1:
        if "--show" in flags:
            return 0
        raise SystemExit(__doc__)
    if "--check" in flags:
        try:
            with open(args[0], "r", encoding="utf-8") as fh:
                current = fh.read()
        except OSError:
            current = None
        if current != text:
            print("STALE: %s (run `make config`)" % args[0])
            return 1
        return 0
    with open(args[0], "w", encoding="utf-8") as fh:
        fh.write(text)
    print("wrote %s" % args[0])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
