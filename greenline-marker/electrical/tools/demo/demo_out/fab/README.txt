GreenLine GL-1 DEMO (toolchain proof, not the product circuit) - bare board fabrication data
============================================================================================

Design:    greenline_demo    revision demo-1    GreenLine
Generated: by the gleda toolchain with KiCad 7 (kicad-cli) from the design script.
DRC:       KiCad DRC 0 error(s), 0 unconnected, 39 warning(s) (silk_edge_clearance 1, silk_over_copper 38)

BOARD
-----
Copper layers:       4
Finished thickness:  0.80 mm
Surface finish:      ENIG
Size:                42.20 x 38.40 mm (see greenline_demo-Edge_Cuts.gbr)
Outline:             routed; every closed contour on Edge.Cuts inside the outline is a routed cut-out / non-plated slot
Vias:                through vias only (no blind, buried or micro vias)
Via tenting:         tented on the BOTTOM side; open (mask opening) on the top side
Via protection:      plugged with solder mask from the BOTTOM side and tented there (IPC-4761 type III-a); the top side of the vias stays open
Via to pad, top:     design rule 0.200 mm copper to copper between a via and an SMD pad of its own net (vias open: this is the solder-mask web); smallest on this board 0.206 mm
Via to pad, bottom:  design rule 0.100 mm copper to copper between a via and an SMD pad of its own net (vias tented); smallest on this board 0.100 mm

FAB NOTES
---------
- The bottom side is a wetted surface in use: no open via holes there.

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
Rule set:                   US_4L_FINE
Minimum track width:        0.090 mm (3.5 mil)
Minimum copper clearance:   0.090 mm (3.5 mil)
Smallest track in use:      0.090 mm
Smallest clearance in use:  0.090 mm
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
Default       0.150 mm  0.150 mm  0.127 mm  45
CamPower      0.150 mm  0.150 mm  0.090 mm  3
Fine          0.090 mm  0.090 mm  0.090 mm  18
Power         0.300 mm  0.150 mm  0.127 mm  6

TRACKS AS ROUTED (measured on the board these files were plotted from)
----------------------------------------------------------------------
width          F.Cu    In2.Cu      B.Cu     total
 0.090 mm  159.1 mm  109.4 mm  159.3 mm  427.8 mm
 0.150 mm  612.7 mm  148.2 mm  647.2 mm 1408.1 mm
 0.300 mm  224.0 mm   25.5 mm   68.0 mm  317.4 mm
Net classes below the standard 0.150 / 0.127 mm: CamPower, Fine.
Tracks narrower than 0.150 mm: 427.8 mm on 18 net(s).
The design declares no fine areas: these tracks may run anywhere along their nets; the farthest is CAM_D2 on F.Cu at (-0.75, 1.23), 15.6 mm from the nearest fine-pitch array (U2).  Quote the whole board at the board-level minimums.

PLANES
------
In1.Cu   GND (whole board)
In2.Cu   V2V8 (whole board), shared with signal tracks

DRILLS
------
greenline_demo-NPTH.drl: 1 hole(s)
     1.150 mm  x 1
greenline_demo-PTH.drl: 298 hole(s)
     0.250 mm  x 298
Non-plated hole H1: 1.150 mm at (-4.200, 14.550)
Routed non-plated slot on Edge.Cuts: 1.150 x 1.650 mm centred on (4.200, 14.550)

COORDINATES
-----------
All Gerber and drill files share one origin: the centre of the board.
Units mm, X to the right and Y up, seen from the top side.

FILES
-----
greenline_demo-F_Cu.gbr          copper, top (layer 1)
greenline_demo-In1_Cu.gbr        copper, inner (layer 2), GND plane
greenline_demo-In2_Cu.gbr        copper, inner (layer 3), V2V8 plane
greenline_demo-B_Cu.gbr          copper, bottom (layer 4)
greenline_demo-F_Mask.gbr        solder mask openings, top
greenline_demo-B_Mask.gbr        solder mask openings, bottom
greenline_demo-F_Paste.gbr       solder paste (stencil), top
greenline_demo-B_Paste.gbr       solder paste (stencil), bottom
greenline_demo-F_Silkscreen.gbr  silkscreen (legend), top
greenline_demo-B_Silkscreen.gbr  silkscreen (legend), bottom
greenline_demo-Edge_Cuts.gbr     board outline, cut-outs and routed (non-plated) slots
greenline_demo-job.gbrjob        Gerber job file (stack-up, rules, file list)
greenline_demo-PTH.drl           plated holes, Excellon, mm
greenline_demo-NPTH.drl          non-plated holes, Excellon, mm
greenline_demo-PTH-drl_map.gbr   drill map of the plated holes (Gerber X2)
greenline_demo-NPTH-drl_map.gbr  drill map of the non-plated holes (Gerber X2)
README.txt                       this file
