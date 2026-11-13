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

``--check`` writes nothing and exits 1 if the stored copy differs from what
the installed KiCad library gives now.
"""
import os
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
    "B12": ("(at -3.2 -3.68) (size 0.6 1.15)", "(at -3.2 -3.7) (size 0.6 1.11)"),
    "A12": ("(at 3.2 -3.68) (size 0.6 1.15)", "(at 3.2 -3.7) (size 0.6 1.11)"),
    "B1": ("(at 3.2 -3.68) (size 0.6 1.15)", "(at 3.2 -3.7) (size 0.6 1.11)"),
}


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
                                   '(PROVISIONAL). USB 2.0 Type C Receptacle, GCT, 16P, top mounted, horizontal, 5A: ')
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
