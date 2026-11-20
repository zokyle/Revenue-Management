GreenLine GL-1 main board - assembly data
=========================================

Design: gl1_main    revision E-EVT1

FILES
-----
gl1_main-pos.csv   pick-and-place, both sides, one row per placed part
gl1_main-bom.csv   grouped bill of materials (DNP parts on their own lines)

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
            J1     anchor (0.000, -12.900), body centre (0.000, -14.500), 1.600 mm apart

PARTS
-----
top:    86 placed part(s)
bottom: 17 placed part(s)
DNP (do not place): R14
Bare pads, not parts (no placement, no paste): BT1, BT2, J2, TP1, TP2, TP3, TP4, TP5

FIDUCIALS
---------
top:    (-16.800, 9.300), (18.900, -4.500), (8.600, -17.200)
bottom: (-13.500, -3.000), (14.000, -7.000), (-17.000, 7.500)
         1.00 mm bare copper in a 2.00 mm solder-mask opening, same coordinates as the position file

BOM
---
37 line(s), 103 part(s) to fit, 1 DNP.
Prices are single-unit list prices from the design script.

ADDED BY THE BOARD BUILD (not by the toolchain)
-----------------------------------------------
gl1_main-bom-status.csv   the same grouped BOM with, for every line:
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

OFF-BOARD ITEMS joined to this board (on no board BOM; they belong on the purchasing list
above the board BOMs, docs/SOURCING.md actions A11 / A12):
  display LS013B7DH03 (Sharp; its tail plugs into J1) - single source, 28-week factory lead (docs/SOURCING.md 9.2)
  cell GM201030-PCB (PowerStream; leads soldered to BT1 = + and BT2 = -, polarity PROVISIONAL) - single seller (docs/SOURCING.md 9.3)
