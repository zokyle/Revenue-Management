GreenLine GL-1 main board - bare board fabrication data
=======================================================

Design:    gl1_main    revision D-EVT1    GreenLine
Generated: by the gleda toolchain with KiCad 7 (kicad-cli) from the design script.
DRC:       KiCad DRC 0 error(s), 0 unconnected, 2 warning(s) (silk_over_copper 1, silk_overlap 1)

BOARD
-----
Copper layers:       4
Finished thickness:  0.80 mm
Surface finish:      ENIG
Size:                42.20 x 38.40 mm (see gl1_main-Edge_Cuts.gbr)
Outline:             routed; every closed contour on Edge.Cuts inside the outline is a routed cut-out / non-plated slot
Vias:                through vias only (no blind, buried or micro vias)
Via tenting:         tented (covered by solder mask) on both sides
Via protection:      plugged with solder mask from the BOTTOM side (IPC-4761 type III-a) and tented on both sides
Via to pad, top:     design rule 0.100 mm copper to copper between a via and an SMD pad of its own net (vias tented); smallest on this board 0.100 mm
Via to pad, bottom:  design rule 0.100 mm copper to copper between a via and an SMD pad of its own net (vias tented); smallest on this board 0.405 mm

FAB NOTES
---------
- The bottom side is a wetted surface in use: no open via holes there, and no via at all inside the grain opening (dia 13 at 0, -4) or the pad slot (17.44 x 2.2 at y -17).
- Under each ball foot (0, 15), (-16.5, -9.5), (16.5, -9.5): an UNMASKED dia 1.6 copper land on the bottom side inside a dia 2.5 zone without tracks and vias.
- Layer 2 (In1.Cu) is a solid ground plane.
- 0.100 mm track and gap (3.94 mil) inside the two fine areas round the cameras: the fabricator must accept it in writing (DESIGN_SPEC E7, release gate). The acceptance must cover ALL THREE routing layers - F.Cu, In2.Cu (layer 3) and B.Cu: fine-class tracks change layer inside the fine areas, so 0.100 mm track and 0.100 mm gap occur on the inner layer and on the bottom as well as on the top (lengths per layer under TRACKS AS ROUTED; DEPARTURE from the specification's 'used only to escape the camera BGAs', recorded in electrical/README.md).
- Lead-free assembly (SAC305), RoHS-compliant parts, no conformal coating (DESIGN_SPEC E5).
- Solder mask is drawn 1:1 on every land. U9 (6 balls on 0.4 mm, lands 0.23 mm) and U2 / U3 (25 balls on 0.5 mm, lands 0.20 mm): whatever mask compensation the fabricator applies must leave a mask web of at least 0.075 mm between the openings of these parts.
- Vias: 0.50 mm pad, through only, tented on both sides and plugged from the bottom (see via protection). HOLE SIZE - QUESTION FOR THE FABRICATOR, to be answered with the E7 question: the specification says '0.25 mm drill'; the design data carries 0.25 mm as the hole size and the toolchain's README line calls it the finished hole. Intended: 0.25 mm DRILL (tool) on the 0.50 mm pad, finished hole about 0.20 mm. If the fabricator reads 0.25 mm as the FINISHED size it drills 0.30 to 0.35 mm, which leaves 0.075 to 0.10 mm of ring and less hole-to-copper distance than the 0.20 mm the design keeps: not accepted without review.
- Plane (zone) clearance: 0.20 mm everywhere (the build adds a KiCad rule for it; the generated fine-class rule alone would let the fill come to 0.127 mm of camera-side nets outside the fine areas).
- Layer 3 (In2.Cu) is the V2V8 supply fill AND a routing layer: it is not a solid plane (the real coverage is in layout_quality.md).
- BT1 / BT2 (cell-lead pads), the test points and the seven underside contact pads carry no solder paste.

STACK-UP (top to bottom)
------------------------
layer            type       thickness  material
F.Mask           mask       0.0100 mm  
F.Cu             copper     0.0350 mm  
dielectric 1     prepreg    0.1100 mm  FR4 (er 4.50)
In1.Cu           copper     0.0175 mm  
dielectric 2     core       0.4550 mm  FR4 (er 4.50)
In2.Cu           copper     0.0175 mm  
dielectric 3     prepreg    0.1100 mm  FR4 (er 4.50)
B.Cu             copper     0.0350 mm  
B.Mask           mask       0.0100 mm  
total                       0.8000 mm

BOARD-LEVEL MINIMUMS (the smallest features on this board)
----------------------------------------------------------
Rule set:                   GL1_4L_0.10mm
Minimum track width:        0.100 mm (3.9 mil)
Minimum copper clearance:   0.100 mm (3.9 mil)
Smallest track in use:      0.100 mm
Smallest clearance in use:  0.100 mm
Via pad / drill:            0.500 / 0.250 mm (finished hole)
Minimum annular ring:       0.125 mm
Minimum drill:              0.250 mm
Hole to hole (wall-wall):   0.250 mm
Hole to copper:             0.200 mm
Copper to board edge:       0.300 mm
Zone (plane) clearance:     0.200 mm

NET CLASSES (track width / clearance as routed)
-----------------------------------------------
class            track min track clearance  nets
Default       0.150 mm  0.150 mm  0.127 mm  58
CamPower      0.150 mm  0.150 mm  0.100 mm  3
Fine          0.100 mm  0.100 mm  0.100 mm  28
Power         0.300 mm  0.150 mm  0.127 mm  6

TRACKS AS ROUTED (measured on the board these files were plotted from)
----------------------------------------------------------------------
width          F.Cu    In2.Cu      B.Cu     total
 0.100 mm  133.7 mm   31.8 mm   52.8 mm  218.3 mm
 0.150 mm  600.0 mm  379.3 mm  778.3 mm 1757.6 mm
 0.300 mm  214.9 mm   50.2 mm   56.5 mm  321.6 mm
Net classes below the standard 0.150 / 0.127 mm: CamPower, Fine.
Tracks narrower than 0.150 mm: 218.3 mm on 28 net(s).
Fine areas (rule areas in the board file, as far as they lie on the board): fine_U2 x -16.10..-3.90, y 9.50..17.30; fine_U3 x 3.90..16.10, y 9.50..17.30 - 175 mm2, 13 % of the board.
Every one of these tracks lies completely inside a fine area; the farthest reaches 5.3 mm from the pad field of U3.  Outside the fine areas all tracks are at least 0.150 mm wide and the design rules ask for 0.127 mm clearance; KiCad's DRC checked both.

PLANES
------
In1.Cu   GND (whole board)
In2.Cu   V2V8 (whole board), shared with signal tracks
F.Cu     GND
B.Cu     GND

DRILLS
------
gl1_main-NPTH.drl: 1 hole(s)
     1.150 mm  x 1
gl1_main-PTH.drl: 278 hole(s)
     0.250 mm  x 278
Non-plated hole H1: 1.150 mm at (14.350, 10.800)
Routed non-plated slot on Edge.Cuts: 1.150 x 2.200 mm centred on (-14.350, 10.800)

COORDINATES
-----------
All Gerber and drill files share one origin: the centre of the board.
Units mm, X to the right and Y up, seen from the top side.

FILES
-----
gl1_main-F_Cu.gbr          copper, top (layer 1)
gl1_main-In1_Cu.gbr        copper, inner (layer 2), GND plane
gl1_main-In2_Cu.gbr        copper, inner (layer 3), V2V8 plane
gl1_main-B_Cu.gbr          copper, bottom (layer 4)
gl1_main-F_Mask.gbr        solder mask openings, top
gl1_main-B_Mask.gbr        solder mask openings, bottom
gl1_main-F_Paste.gbr       solder paste (stencil), top
gl1_main-B_Paste.gbr       solder paste (stencil), bottom
gl1_main-F_Silkscreen.gbr  silkscreen (legend), top
gl1_main-B_Silkscreen.gbr  silkscreen (legend), bottom
gl1_main-Edge_Cuts.gbr     board outline, cut-outs and routed (non-plated) slots
gl1_main-job.gbrjob        Gerber job file (stack-up, rules, file list)
gl1_main-PTH.drl           plated holes, Excellon, mm
gl1_main-NPTH.drl          non-plated holes, Excellon, mm
gl1_main-PTH-drl_map.gbr   drill map of the plated holes (Gerber X2)
gl1_main-NPTH-drl_map.gbr  drill map of the non-plated holes (Gerber X2)
README.txt                 this file
