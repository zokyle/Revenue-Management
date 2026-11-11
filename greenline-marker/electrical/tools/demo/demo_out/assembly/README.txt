GreenLine GL-1 DEMO (toolchain proof, not the product circuit) - assembly data
==============================================================================

Design: greenline_demo    revision demo-1

FILES
-----
greenline_demo-pos.csv   pick-and-place, both sides, one row per placed part
greenline_demo-bom.csv   grouped bill of materials (DNP parts on their own lines)

POSITION FILE
-------------
Columns:  Ref, Val, Package, PosX, PosY, Rot, Side, MPN, BodyX, BodyY
Units:    millimetres, degrees.
Origin:   the centre of the board - the same origin as the Gerber and drill files.
Axes:     X to the right, Y up, seen from the TOP side, for both sides.
Bottom:   X is NOT mirrored: a bottom-side part at PosX = +5 lies under the top-side point X = +5.
Rot:      footprint rotation counter-clockwise seen from the TOP side, for both sides (KiCad's convention); 0 = the orientation of the footprint in the library, for a bottom-side part after flipping it about its X axis.
PosX/Y:   the footprint anchor (origin of the land pattern).
BodyX/Y:  the centre of the component body outline.  Use it as the pick point where it differs from PosX/Y:
            J1     anchor (0.000, -13.900), body centre (0.000, -15.500), 1.600 mm apart

PARTS
-----
top:    74 placed part(s)
bottom: 17 placed part(s)
DNP (do not place): none
Bare pads, not parts (no placement, no paste): BT1, BT2, J2

FIDUCIALS
---------
top:    (-19.300, -0.800), (19.000, -3.000), (-16.500, 9.900)
bottom: (-13.500, -3.000), (14.000, -7.000), (0.000, -13.300)
         1.00 mm bare copper in a 2.00 mm solder-mask opening, same coordinates as the position file

BOM
---
31 line(s), 91 part(s) to fit, 0 DNP.
Prices are single-unit list prices from the design script.
