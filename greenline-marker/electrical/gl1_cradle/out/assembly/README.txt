GreenLine GL-1 cradle board - assembly data
===========================================

Design: gl1_cradle    revision E-EVT1

FILES
-----
gl1_cradle-pos.csv   pick-and-place, both sides, one row per placed part
gl1_cradle-bom.csv   grouped bill of materials (DNP parts on their own lines)

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
            (no part: anchor and body centre agree within 0.05 mm everywhere)

PARTS
-----
top:    5 placed part(s)
bottom: 5 placed part(s)
DNP (do not place): SP5, SP6, SP7
Bare pads, not parts (no placement, no paste): J2

FIDUCIALS
---------
top:    (-11.000, 1.500), (11.500, -2.000), (12.500, 4.600)
bottom: (-11.500, 4.000), (12.000, -3.500), (-12.500, -4.500)
         1.00 mm bare copper in a 2.00 mm solder-mask opening, same coordinates as the position file

BOM
---
7 line(s), 10 part(s) to fit, 3 DNP.
Prices are single-unit list prices from the design script.

ADDED BY THE BOARD BUILD (not by the toolchain)
-----------------------------------------------
gl1_cradle-bom-status.csv   the same grouped BOM with, for every line:
  Status                  sourcing status of the exact part number as docs/SOURCING.md has it:
                          VERIFIED = a US source listing this part number was seen on the date in
                          the last column (listed for sale, NOT a stock promise); PROVISIONAL =
                          everything else. It says nothing about the land pattern or pin table.
  Design evidence / note  RESEARCH or PROVISIONAL: how well the design data of the line (pin table,
                          land pattern, value) is known. PROVISIONAL lines gate the board order.
  Sourcing risk, alternates, sourcing row: copied from the row of docs/sourcing.csv that has the
                          line's references (main-NN / cradle-NN = the BOM item number). The alternates
                          are CANDIDATES named by the sourcing report, NOT approved parts: each is
                          VERIFIED (a listing was seen) or PROVISIONAL as its text says, and none has
                          been approved by the design owner (docs/SOURCING.md action A18).
Read a live distributor page before ordering: every stock figure behind these columns is an
undated snapshot.
