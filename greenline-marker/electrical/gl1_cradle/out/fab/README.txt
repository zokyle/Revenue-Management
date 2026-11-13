GreenLine GL-1 cradle board - bare board fabrication data
=========================================================

Design:    gl1_cradle    revision D-EVT1    GreenLine
Generated: by the gleda toolchain with KiCad 7 (kicad-cli) from the design script.
DRC:       KiCad DRC 0 error(s), 0 unconnected, 1 warning(s) (silk_overlap 1)

BOARD
-----
Copper layers:       2
Finished thickness:  1.60 mm
Surface finish:      ENIG
Size:                30.00 x 22.00 mm (see gl1_cradle-Edge_Cuts.gbr)
Outline:             routed; every closed contour on Edge.Cuts inside the outline is a routed cut-out / non-plated slot
Vias:                through vias only (no blind, buried or micro vias)
Via tenting:         tented (covered by solder mask) on both sides
Via to pad, top:     design rule 0.100 mm copper to copper between a via and an SMD pad of its own net (vias tented); smallest on this board 0.269 mm
Via to pad, bottom:  design rule 0.100 mm copper to copper between a via and an SMD pad of its own net (vias tented); smallest on this board 0.130 mm

FAB NOTES
---------
- The TOP face lies against a plastic ceiling: only J1 and the spring pins stand on it.
- Spring pins SP1-SP7 are soldered square to the board in a jig (mechanical/README).
- Lead-free assembly (SAC305), RoHS-compliant parts (DESIGN_SPEC E5).

STACK-UP (top to bottom)
------------------------
layer            type       thickness  material
F.Mask           mask       0.0100 mm  
F.Cu             copper     0.0350 mm  
dielectric 1     core       1.5100 mm  FR4 (er 4.50)
B.Cu             copper     0.0350 mm  
B.Mask           mask       0.0100 mm  
total                       1.6000 mm

BOARD-LEVEL MINIMUMS (the smallest features on this board)
----------------------------------------------------------
Rule set:                   US_2L_STD
Minimum track width:        0.127 mm (5.0 mil)
Minimum copper clearance:   0.127 mm (5.0 mil)
Smallest track in use:      0.200 mm
Smallest clearance in use:  0.150 mm
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
Default       0.200 mm  0.200 mm  0.150 mm  7
Power         0.400 mm  0.400 mm  0.150 mm  3

TRACKS AS ROUTED (measured on the board these files were plotted from)
----------------------------------------------------------------------
width          F.Cu      B.Cu     total
 0.200 mm   26.2 mm   29.8 mm   55.9 mm
 0.400 mm   15.5 mm   55.4 mm   70.8 mm

PLANES
------
none

DRILLS
------
gl1_cradle-NPTH.drl: 6 hole(s)
     0.650 mm  x 2
     2.200 mm  x 4
gl1_cradle-PTH.drl: 20 hole(s)
     0.250 mm  x 9
     0.600 mm  x 4
     0.900 mm  x 7
Non-plated hole MH1: 2.200 mm at (-12.500, -8.300)
Non-plated hole MH2: 2.200 mm at (12.500, -8.300)
Non-plated hole MH3: 2.200 mm at (-12.500, 8.700)
Non-plated hole MH4: 2.200 mm at (12.500, 8.700)

COORDINATES
-----------
All Gerber and drill files share one origin: the centre of the board.
Units mm, X to the right and Y up, seen from the top side.

FILES
-----
gl1_cradle-F_Cu.gbr          copper, top (layer 1)
gl1_cradle-B_Cu.gbr          copper, bottom (layer 2)
gl1_cradle-F_Mask.gbr        solder mask openings, top
gl1_cradle-B_Mask.gbr        solder mask openings, bottom
gl1_cradle-F_Paste.gbr       solder paste (stencil), top
gl1_cradle-B_Paste.gbr       solder paste (stencil), bottom
gl1_cradle-F_Silkscreen.gbr  silkscreen (legend), top
gl1_cradle-B_Silkscreen.gbr  silkscreen (legend), bottom
gl1_cradle-Edge_Cuts.gbr     board outline, cut-outs and routed (non-plated) slots
gl1_cradle-job.gbrjob        Gerber job file (stack-up, rules, file list)
gl1_cradle-PTH.drl           plated holes, Excellon, mm
gl1_cradle-NPTH.drl          non-plated holes, Excellon, mm
gl1_cradle-PTH-drl_map.gbr   drill map of the plated holes (Gerber X2)
gl1_cradle-NPTH-drl_map.gbr  drill map of the non-plated holes (Gerber X2)
README.txt                   this file
