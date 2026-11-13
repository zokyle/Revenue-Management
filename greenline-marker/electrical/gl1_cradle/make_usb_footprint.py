#!/usr/bin/python3
"""Make the project copy of the USB-C receptacle land pattern.

    /usr/bin/python3 -B electrical/gl1_cradle/make_usb_footprint.py [--check]

Why a copy.  KiCad's library footprint for the GCT USB4105
(``Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal``)
has its two non-plated locating-peg holes (dia 0.65) 0.194 mm from the corner
of the outer ground pads (A1 / B12 and A12 / B1).  The cradle board's rule
set asks for 0.20 mm between a hole wall and foreign copper, and KiCad's DRC
reports the four pairs as ``hole_clearance`` errors on the bare, unrouted
board.  No rule is relaxed: the four pads are shortened by 0.04 mm at the end
that faces the pegs (1.15 -> 1.11 mm long, centre moved 0.02 mm away), which
gives 0.233 mm.  Everything else is the library footprint, byte for byte,
except its name and description.  PROVISIONAL: the change has not been
checked against GCT's drawing.

Second change (layout stage).  The library footprint numbers the four wide
lands twice: pads A1 and B12, A4 and B9, A9 and B4, A12 and B1 are pairs of
pad objects with the SAME position and size (one piece of copper for the two
contacts of the reversible plug).  The toolchain's router (gleda 0.4.0) cannot
join two coincident pads of one net - it then leaves the whole net open
(reported; a 20-line reproduction is in the layout report).  The copy
therefore keeps one pad object per land - A1, A4, A9, A12 - and drops the
duplicates B12, B9, B4, B1.  The copper, the mask and the paste are unchanged:
only the second NAME of each land is gone.  ``MERGED_LANDS`` says which land
serves which contact; ``check_cradle_rules.py`` uses it for the pin table.

``--check`` writes nothing and exits 1 if the stored copy differs from what
the installed KiCad library gives now.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KICAD_LIB = "/usr/share/kicad/footprints/Connector_USB.pretty"
SOURCE_NAME = "USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal"
LOCAL_LIB = "gl1_cradle_fp"
LOCAL_NAME = SOURCE_NAME + "_GL1"
LOCAL_PATH = os.path.join(HERE, LOCAL_LIB + ".pretty", LOCAL_NAME + ".kicad_mod")
#: pad -> (old "at ... size" text, new text).  KiCad file coordinates (y down).
CHANGES = {
    "A1": ("(at -3.2 -3.68) (size 0.6 1.15)", "(at -3.2 -3.7) (size 0.6 1.11)"),
    "A12": ("(at 3.2 -3.68) (size 0.6 1.15)", "(at 3.2 -3.7) (size 0.6 1.11)"),
}
#: duplicate pad object -> the pad object of the same land that is kept, with the
#: "at ... size" text both have in the library file (they must be identical)
MERGED_LANDS = {"B12": "A1", "B9": "A4", "B4": "A9", "B1": "A12"}
_LAND_TEXT = {"A1": "(at -3.2 -3.68) (size 0.6 1.15)", "A4": "(at -2.4 -3.68) (size 0.6 1.15)",
              "A9": "(at 2.4 -3.68) (size 0.6 1.15)", "A12": "(at 3.2 -3.68) (size 0.6 1.15)"}


def local_text():
    with open(os.path.join(KICAD_LIB, SOURCE_NAME + ".kicad_mod"), encoding="utf-8") as fh:
        text = fh.read()
    head = '(footprint "%s"' % SOURCE_NAME
    if text.count(head) != 1:
        raise SystemExit("unexpected library file: footprint header not found once")
    text = text.replace(head, '(footprint "%s"' % LOCAL_NAME)
    old_descr = '(descr "USB 2.0 Type C Receptacle, GCT, 16P, top mounted, horizontal, 5A: '
    if text.count(old_descr) != 1:
        raise SystemExit("unexpected library file: description not found once")
    text = text.replace(old_descr, '(descr "GL-1 copy: outer GND pads shortened 0.04 mm for 0.2 mm to the peg holes '
                                   '(PROVISIONAL); one pad object per wide land (B12, B9, B4, B1 merged into A1, A4, '
                                   'A9, A12). USB 2.0 Type C Receptacle, GCT, 16P, top mounted, horizontal, 5A: ')
    # drop the duplicate pad object of each wide land - only if it really is a duplicate
    for dup, keep in MERGED_LANDS.items():
        geom = _LAND_TEXT[keep]
        if text.count('(pad "%s" smd roundrect %s' % (keep, geom)) != 1:
            raise SystemExit("unexpected library file: pad %s is not where it was" % keep)
        m = re.findall(r'^  \(pad "%s" smd roundrect %s .*\)\n' % (re.escape(dup), re.escape(geom)), text, re.M)
        if len(m) != 1:
            raise SystemExit("unexpected library file: pad %s is not a duplicate of %s" % (dup, keep))
        rest_dup = m[0].split(geom, 1)[1].split("(tstamp")[0]
        keep_line = re.findall(r'^  \(pad "%s" smd roundrect %s .*\)\n' % (re.escape(keep), re.escape(geom)),
                               text, re.M)[0]
        if keep_line.split(geom, 1)[1].split("(tstamp")[0] != rest_dup:
            raise SystemExit("unexpected library file: pads %s and %s differ" % (dup, keep))
        text = text.replace(m[0], "")
    for pad, (old, new) in CHANGES.items():
        line = '(pad "%s" smd roundrect %s' % (pad, old)
        if text.count(line) != 1:
            raise SystemExit("unexpected library file: pad %s is not where it was" % pad)
        text = text.replace(line, '(pad "%s" smd roundrect %s' % (pad, new))
    return text


def main(argv=None):
    check = "--check" in (argv if argv is not None else sys.argv[1:])
    text = local_text()
    have = None
    if os.path.isfile(LOCAL_PATH):
        with open(LOCAL_PATH, encoding="utf-8") as fh:
            have = fh.read()
    if have == text:
        print("up to date: %s" % LOCAL_PATH)
        return 0
    if check:
        print("STALE or missing: %s" % LOCAL_PATH)
        return 1
    os.makedirs(os.path.dirname(LOCAL_PATH), exist_ok=True)
    with open(LOCAL_PATH, "w", encoding="utf-8") as fh:
        fh.write(text)
    print("written: %s" % LOCAL_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
