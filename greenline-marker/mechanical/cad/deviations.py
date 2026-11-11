"""Deviations of the mechanical model from the written specification, with reasons (revision C, after design review).

This list is written into export/check_report.{json,md} by checks.run_all() and is copied into the README.
Numbers are taken from params so they follow the YAML.

status:
    "closed (rev C)"   the rev C YAML / decision removed the conflict; kept here only as a pointer
    "accepted"         the system owner accepted it in rev C; it stays a recorded deviation
    "recorded"         the model differs from the original task text or the spec text for a stated reason
    "open"             needs a decision or a change of a shared number (see PROPOSED_PARAM_CHANGES.md, part B)
`yaml_change` = True means a SHARED number or the shared text would have to change (the YAML is not edited here).
"""
import math
import params as P

M = P.MECH
_lcd_corner_r = math.hypot(P.LCD_X1, P.LCD_Y0)
_lcd_corner_r_fwd = math.hypot(P.LCD_X1, P.LCD_Y0 + M["lcd_bias"])
_bundle_pad = 1.622 - P.THIN_STRIP_T * math.tan(math.radians(M["fov_h_half_deg"]))

DEVIATIONS = [
    dict(id="D01", part="base_plate / pcb_adhesive", status="closed (rev C)", yaml_change=False,
         requirement="seven dia 2.2 pad holes at 2.54 pitch (rev B)",
         implemented=f"one slot {P.PAD_SLOT_L:.2f} x {P.PAD_HOLE_D} mm",
         reason="rev C YAML specifies the slot (base_plate.pad_holes.form: slot)"),
    dict(id="D02", part="base_plate", status="closed (rev C)", yaml_change=False,
         requirement="blind seats for the 1.0 mm balls (rev B)",
         implemented=f"three dia {P.BALL_HOLE_D} through holes; balls set {P.BALL_PROT} proud on a gauge plate and potted",
         reason="rev C YAML specifies through holes and the gauge-plate process; the conical seats are removed"),
    dict(id="D03", part="base_plate", status="closed (rev C)", yaml_change=False,
         requirement="baffle ring about dia 5.4, wall 0.6 (rev B task text)",
         implemented=f"inner dia {2 * P.BAFFLE_RI:.2f}, wall {P.BAFFLE_WALL}, spokes at {P.SPOKE_ANGLES} deg",
         reason="rev C YAML carries these numbers (base_plate.baffle); a rebalanced ring is proposed in PROPOSED_PARAM_CHANGES.md"),
    dict(id="D04", part="tub", status="accepted", yaml_change=False,
         requirement="every printed wall >= 0.8 mm",
         implemented=f"the wall behind each window recess in front of the camera cube is {P.THIN_STRIP_T:.3f} mm: z {P.WIN_Z0}..{P.OPEN_Z0} across the "
                     f"{2 * P.HOOD_IN_HW:.1f} mm bay ({2 * P.HOOD_IN_HW * (P.OPEN_Z0 - P.WIN_Z0):.1f} mm2 per camera); the bonded window backs it",
         reason=f"visor face {P.Y_VISOR} to cube front {P.HOOD_PAD_Y - P.CLR:.3f} leaves {P.Y_VISOR - (P.HOOD_PAD_Y - P.CLR):.3f} mm for "
                f"recess {P.WIN_RECESS_DEPTH} + wall 0.8 + clearance {P.CLR}. Accepted in rev C (visor_window.min_wall_behind_recess = "
                f"{P.Y['visor_window']['min_wall_behind_recess']})"),
    dict(id="D05", part="tub", status="recorded", yaml_change=False,
         requirement="camera opening bevelled wider toward the inside",
         implemented=f"no bevel: the opening is straight, +-{P.OPEN_HALF_W} wide and z {P.OPEN_Z0}..{P.OPEN_Z1}, and as wide as the prism bay behind it "
                     f"(bay half-width {P.HOOD_IN_HW}); it runs from the floor of the window recess (y {P.WIN_RECESS_FLOOR_Y:.2f}) straight into the bay, "
                     f"over a sill {P.THIN_STRIP_T:.3f} mm thick",
         reason=f"the light bundle diverges outward: it is +-1.62 mm wide at the aperture plane (the recess floor) and +-{_bundle_pad:.2f} mm at the "
                f"inner edge of the sill, {P.THIN_STRIP_T:.3f} mm further in, so a bevel toward the inside clears nothing. A wider bay would push the hood "
                f"beyond the {P.KO_HOOD_HW} mm half-width of the keep-out contract (hood outside is +-{P.HOOD_OUT_HW})"),
    dict(id="D06", part="tub", status="recorded", yaml_change=False,
         requirement="shallow glue channel if possible without going below the wall minimum",
         implemented="no glue channel and no glue chamfer anywhere",
         reason="the arc ledge is 0.65 mm wide and the seal land 0.4 mm: any groove leaves a seal lip below 0.5 mm, and a chamfer on the "
                f"0.8 mm visor wall leaves less than 0.8 at its foot. The {P.CLR} mm radial groove between base edge and side wall is the adhesive "
                f"reservoir on the arc (it is filled down to the rim and modelled as part of the bead); the joint on the land is {P.BEAD_T:.2f} mm high"),
    dict(id="D07", part="tub / base_plate", status="recorded", yaml_change=False,
         requirement="two or three 1.2 mm locating pins/keys between base and tub so that the base cannot be assembled rotated",
         implemented="no key between base plate and tub; the edge of the base plate is plain. The base plate is laminated to the PCB in a jig that "
                     "locates the PCB by its two locating holes and the plate by its D outline; the PCB / base unit is then located in the tub by the "
                     "two spigots of posts E",
         reason="there is no room for a key inside the seal line, and a key under the visor wall interrupts the seal land: the two lugs of the first "
                "rev C model sat in through-notches that connected the underside to the camera bays (design review; check 13 now proves the seal ring is "
                f"closed). A key with {P.CLR} mm clearance could not hold the {P.BAFFLE_RI - P.PD_HALF_DIAG:.3f} mm between baffle ring and photodiode either"),
    dict(id="D08", part="tub / vent", status="closed (rev C)", yaml_change=False,
         requirement="vent pad near (17, -3) (rev B)",
         implemented=f"vent at {P.VENT_XY}",
         reason="rev C YAML gives this position"),
    dict(id="D09", part="tub", status="recorded", yaml_change=False,
         requirement="nose groove from the aperture edge to the visor",
         implemented=f"groove {M['nose_w']} x {M['nose_depth']} from the cover-glass recess edge (r {P.RECESS_D / 2}) to the visor; roof thickened "
                     f"{M['nose_depth']} mm underneath",
         reason="the aperture edge is under the cover glass; the thickening keeps 0.8 mm under the groove"),
    dict(id="D10", part="pcb_adhesive / stack", status="closed (rev C)", yaml_change=False,
         requirement="adhesive sheet at zero thickness in the YAML (rev B)",
         implemented=f"base plate {P.BASE_T} + sheet {P.PSA_T} (z {P.PSA_Z0}..{P.PSA_Z1}); PCB at z {P.PCB_Z0}..{P.PCB_Z1}; no modelling overlap",
         reason="rev C YAML: base_plate.thickness 0.87 and base_plate.psa.thickness 0.13"),
    dict(id="D11", part="tub / lcd_glass", status="accepted", yaml_change=False,
         requirement="LCD glass assembled from below",
         implemented=f"the glass is tilted in: rear edge first at {M['lcd_tilt_deg']:.0f} deg, shifted {M['lcd_bias']} mm toward the visor while its rear corners "
                     "pass the seating ledge, then pushed back and hinged up (assembly step, path proven in check 14)",
         reason=f"rear glass corners are at r = {_lcd_corner_r:.3f} > ledge inner radius {P.LEDGE_RI}. Rev C accepted a flat insertion biased {P.CLR} mm forward "
                f"({P.LEDGE_RI - math.hypot(P.LCD_X1, P.LCD_Y0 + P.CLR):.3f} mm to the ledge, less than the print tolerance); the design review showed that the "
                f"flat glass cannot go further forward because posts E stop it. Tilted, the front edge is still below the post feet while the rear corners "
                f"pass, so the shift can be {M['lcd_bias']} mm (corners at r = {_lcd_corner_r_fwd:.3f})"),
    dict(id="D12", part="tub / main_pcb / windows", status="closed (rev C)", yaml_change=False,
         requirement="0.25 mm clearance on every drop-in fit",
         implemented=f"PCB edge to seating ledge {P.LEDGE_RI - P.PCB_R:.2f} mm; visor window in its recess {(P.WIN_RECESS_W - P.WIN_W) / 2:.2f} mm per side",
         reason="rev C YAML: pcb.radius 21.1 and visor_window.recess_w 5.5"),
    dict(id="D13", part="tub", status="accepted", yaml_change=False,
         requirement="light baffle from the visor wall back to each prism (light-tight)",
         implemented=f"hood: side skirts and a front pad down to z {M['hood_skirt_z0']}, rear wall down to z {P.HOOD_Z_OVER_CUBE} (over the cube); bottom "
                     f"front edge of the rear wall chamfered {P.HOOD_REAR_CHAMFER:.2f} mm ({P.PRISM_HOOD_CLR:.2f} mm to the prism hypotenuse). "
                     f"A slit of {P.HOOD_SLIT[0]:.2f} to {P.HOOD_SLIT[1]:.2f} mm remains above the cube at the rear; it is closed by a bead of black adhesive "
                     f"({M['hood_seal_w']} mm wide, dispensed {M['hood_seal_free_h']} mm high on the underside of the rear wall and CURED before the PCB is joined, so that "
                     "the cube top beds into a soft gasket)",
         reason="the rear wall cannot pass the cube (LCD glass 0.63 mm behind it). Rev C: the slit is closed with black adhesive at assembly. A bead "
                "applied wet and closed blind (first rev C sequence) would squeeze out next to the prism and glue the PCB to the tub before any test "
                "(design review), hence the pre-cured bead; the gaps beside and in front of the cube (0.265 / 0.25 mm) stay open: light-leak test"),
    dict(id="D14", part="tub", status="recorded", yaml_change=False,
         requirement="top edge radius 0.6, bottom chamfer 0.3; cavity below z 1.2 = R 22 circle clipped at the visor face",
         implemented=f"radius and chamfer on the arc only (visor edges sharp); below z = {P.LEDGE_Z0} the side wall ends on the radial plane through the "
                     f"outer D corner (+-{P.HORN_X_OUT:.1f}, {P.Y_VISOR}), which leaves an open pocket about {P.HORN_X_OUT - P.BASE_CORNER_X:.1f} mm wide under each end "
                     "of the visor wall. The pockets lie OUTSIDE the seal ring (the bead runs round both D corners on the base land)",
         reason="the windows are flush with the top, a rounded visor edge would leave them proud; the R 22 circle meets the visor plane at "
                "33 deg and would leave feather-edged wall ends; the radial cut keeps the full 1.0 mm wall at the end face"),
    dict(id="D15", part="cradle", status="closed (rev C)", yaml_change=False,
         requirement="nest accepts the puck at 0 and 180 deg (rev B)",
         implemented="one orientation only; the D flat is the key",
         reason="rev C: the cradle is a charging and data dock; calibration does not use it"),
    dict(id="D16", part="cradle", status="closed (rev C)", yaml_change=False,
         requirement="seven 2.0 mm pin holes and a stainless reference plate (rev B)",
         implemented=f"one printed slot {P.CRADLE_PIN_SLOT_W:.2f} mm wide through the nest floor; no plate",
         reason="rev C: 'spring pins come up through one slot'; the reference plate is deleted"),
    dict(id="D17", part="cradle", status="closed (rev C)", yaml_change=False,
         requirement="hold the marker down against the spring pins (open in rev B)",
         implemented=f"fixed lip (|x| <= {M['lip_half_w']}, {M['lip_overlap']} mm over the tub top) and a rear cantilever latch "
                     f"({M['latch_w']} wide, {P.LATCH_H0} / {P.LATCH_HN} / {P.LATCH_H1} thick, {P.LATCH_L:.2f} mm long, nose {P.HOOK_OVERLAP_FWD:.2f} to {P.HOOK_OVERLAP:.2f} mm on the tub top) "
                     "with a thumb tab and two over-travel stops",
         reason="designed and proven in check 7 (retention with tolerance, strain by formula and FE, forces, posed insertion and release)"),
    dict(id="D18", part="cradle", status="recorded", yaml_change=False,
         requirement="four 3 mm feet pockets; PCB pocket underneath",
         implemented=f"four pockets dia {M['foot_pocket_dia']} x {M['foot_pocket_depth']} for dia {M['foot_dia']} x {M['foot_h']} mm adhesive bumpers, each with a blind core "
                     f"dia {M['core_dia']} behind it (the corners would otherwise be 13 mm solid); PCB held "
                     f"against the pocket ceiling by four M2 thread-forming screws (not modelled; printed as dia {M['cradle_screw_pilot_dia']} x {M['cradle_screw_pilot_depth']} spot marks, "
                     "drilled dia 1.6 x 3 after printing because a blind 1.7 mm hole would trap powder); three lightening pockets underneath",
         reason="'3 mm feet' read as 3 mm high bumpers (ambiguous); the pin force pushes the PCB out of its pocket so it needs positive retention"),
    dict(id="D19", part="tub / main_pcb", status="open", yaml_change=True,
         requirement="PCB located to the tub by two printed spigots in non-plated holes (rev C YAML)",
         implemented=f"spigots dia {P.SPIGOT_D} x {P.SPIGOT_H} under posts E (tip chamfered {M['spigot_tip_chamfer']} as a lead-in) in a dia {P.LOC_ROUND[2]} hole and a "
                     f"{P.LOC_SLOT[2]} x {P.LOC_SLOT[3]} slot: {P.SPIGOT_FIT:.3f} mm radial clearance, as specified",
         reason=f"{P.SPIGOT_FIT:.3f} mm is a locating fit, far below the {P.CLR} mm drop-in rule and below the +-0.2 mm print tolerance: a spigot that "
                "prints 0.15 mm oversize does not enter. The spigots are therefore a gauged feature (go / no-go at first article, dress with a "
                "hollow punch or fine file). They are 8.4 mm apart while the cameras are 20 mm apart, so their play is amplified at the cameras, and "
                "they only locate until the adhesives have cured (a dia 1.0 PA12 pin cannot hold the board against the base laminate). "
                "PROPOSED_PARAM_CHANGES.md proposes to move the pair to posts B"),
    dict(id="D20", part="cradle", status="recorded", yaml_change=True,
         requirement=f"cradle body {P.CRADLE_SIZE[0]:.0f} x {P.CRADLE_SIZE[1]:.0f} x {P.CRADLE_SIZE[2]:.0f} mm",
         implemented=f"body {P.CRADLE_SIZE[0]:.0f} x {P.CRADLE_SIZE[1]:.0f} x {P.CRADLE_SIZE[2]:.0f} (z {P.CRADLE_BOT_Z} to {P.CRADLE_TOP_Z}); the lip stands to z {P.LIP_Z1:.2f} and the latch to z "
                     f"{P.LATCH_TOP_Z:.2f}, so the printed part is {P.LATCH_TOP_Z - P.CRADLE_BOT_Z:.1f} mm tall; the body is not centred on the marker "
                     f"(y {P.CRADLE_Y0} to {P.CRADLE_Y1})",
         reason=f"a hook over the marker top (z {P.T}) with a {P.LATCH_L:.2f} mm cantilever and a {M['hook_lead_deg']:.0f} deg lead-in cannot stay inside a "
                "14 mm block; the rear needs the room for the latch well, the guard wall, the tab stop and the USB-C receptacle"),
    dict(id="D21", part="cradle / marker", status="recorded", yaml_change=True,
         requirement="the marker rests on its three ball feet on the nest floor, pins at the working height",
         implemented=f"lip and hook have the {P.CLR} mm drop-in clearance above the tub top. With pins fitted the marker is pushed up against them: it "
                     f"floats up to {P.CLR} mm above its feet and the pins then stand {P.PIN_FLOAT_H:.2f} instead of {P.PIN_WORK_H} mm high "
                     f"({P.PIN_COMPRESSION - P.CLR:.2f} of {M['pin_full_stroke']} mm stroke used)",
         reason="a retaining face with drop-in clearance cannot preload a part whose height varies by the print tolerance; the float is inside the "
                "pin stroke. A dock does not need a seating datum (calibration is done elsewhere)"),
    dict(id="D22", part="tub / PCB layout", status="open", yaml_change=True,
         requirement="tub_keepouts is the complete contract: every tub feature that touches or hangs over the PCB top lies inside it",
         implemented=f"true for everything below z = {P.KO_FREE_Z:.2f} ({P.PCB_FREE_H} mm above the PCB top), which check 12 proves on the solids. Above that "
                     f"height the tub still has features over the PCB outside the keep-outs: glass locating ribs down to z {M['lcd_rib_z0']}, the thick "
                     f"roof at z {P.BOND_Z:.2f} (also behind and beside the LCD glass), the nose pad at z {P.ROOF_Z - M['nose_depth']:.1f} and the vent pad at z {P.VENT_PAD_Z:.1f}",
         reason="design/check_layout.py lets a part outside the LCD footprint reach z = roof - 0.1 = 6.7. No listed part is taller than "
                "2.0 mm there, so nothing clashes today, but the rule and the tub disagree: a free height must be added to the contract"),
    dict(id="D23", part="tub", status="recorded", yaml_change=True,
         requirement="tub side wall from z = 0 (the base plane) to the top",
         implemented=f"the side wall ends {P.RIM_Z} mm above the base plane (rim relief): the tub is {P.T - P.RIM_Z:.2f} mm tall, the marker still {P.T} mm. The rim is "
                     f"{P.RIM_Z + P.BALL_PROT:.2f} mm above the plane of the ball feet",
         reason=f"with rim and base plate in one plane the feet stood only {P.BALL_PROT} mm proud of a rim whose height is set by a four-part stack (post, "
                "PCB, sheet, plate: +-0.16 mm RSS, +-0.29 worst case): about one unit in ten would have rocked on its rim (design review). "
                "Price: on a hard floor the side wall no longer shares a footstep load until the base has given by the relief (open issue)"),
    dict(id="D24", part="tub / vent", status="recorded", yaml_change=True,
         requirement="vent on a pad raised 0.2 mm (YAML vent.location); plain top face",
         implemented=f"pad raised {M['vent_pad_h']} mm and run out to the side wall; two grooves {M['vent_groove_w']} wide x {M['vent_groove_d']} deep through the vent hole on the top "
                     f"face, one of them over the edge radius (drain), the other +-{M['vent_cross_half']} mm across",
         reason="the vent hole is a well on the face that is stepped on: it ponds water and a shoe sole can seal it and pump the membrane (design "
                f"review). The grooves let it drain and breathe; {P.T - M['vent_groove_d'] - P.VENT_PAD_Z:.1f} mm of roof stays under them thanks to the thicker pad"),
    dict(id="D25", part="cradle", status="recorded", yaml_change=False,
         requirement="the marker rests on its three ball feet on the printed nest floor",
         implemented=f"the feet rest on a front strip (y >= {P.STRIP_Y0}) and two round pads dia {M['ball_pad_dia']} at the level z = {P.NEST_FLOOR_Z}; the rest of the floor is a "
                     f"basin {M['basin_depth']} mm lower on the centre line that falls {M['basin_fall_deg']} deg to both sides and out through the finger scallops. A rim "
                     f"{M['slot_rim_t']} mm wide round the pin slot and a dam in front of the latch well stay at strip level; the latch well drains through a "
                     f"{M['well_drain_x'][1] - M['well_drain_x'][0]:.1f} x {M['well_drain_h']} mm tunnel to the rear face",
         reason="a flat floor 0.10 mm under the marker held a film of water whose only drain was the pin slot, straight onto the cradle PCB, and the "
                "latch well was a blind sump above that PCB (design review: wet docking)"),
    dict(id="D26", part="lcd_adhesive", status="recorded", yaml_change=False,
         requirement="adhesive frame bonding the LCD under the roof ledge (closed frame)",
         implemented=f"frame with a {M['lcd_psa_vent_w']} mm vent channel from the dia {M['lcd_psa_window_dia']} window to its rear right corner (in the die-cut GL1-030)",
         reason="a closed frame makes the 450 mm3 between cover glass and LCD a sealed cell that the vent does not serve: +16 kPa at 70 C on both "
                "bond lines, and fogging (design review). The channel is 0.15 mm high and hidden under the roof ledge"),
    dict(id="D27", part="base_plate / pcb_adhesive / main_pcb", status="recorded", yaml_change=True,
         requirement="ball top 0.03 above the plate inside a 2.0 mm hole of the adhesive sheet (YAML comment); potting from the inside before the sheet",
         implemented=f"as specified, plus a second stage: at lamination the three sheet holes are filled with the potting epoxy, so that each ball bears on "
                     f"the PCB underside through {P.PCB_Z0 - P.BALL_TOP_Z:.2f} mm of epoxy in compression (stage 1 dome at most {M['epoxy_dome_max']} mm)",
         reason="in straight through holes the balls are held only by the shear strength of the potting (about 3 mm2 of hole wall): a step on a hard "
                "floor pushes them in (design review). The backing needs the PCB underside to be free of tracks and vias under the feet (proposal)"),
    dict(id="D28", part="cradle", status="recorded", yaml_change=True,
         requirement=f"cradle pins at their working height on the pad plane z = {P.CRADLE_PAD_Z}",
         implemented=f"cradle PCB top at z = {P.CPCB_Z1:.3f}: the pins stand {P.PIN_WORK_H} mm on the COPPER FACE of the pads, which is modelled {M['pad_t']} mm "
                     f"below the board underside (z {P.PAD_Z0})",
         reason="the first rev C model put the board 5.82 below the board underside, so the modelled pins stood 5.785 mm while every table said 5.82 "
                "(design review). pad_plane_z should say which face it means"),
]

OPEN = [d for d in DEVIATIONS if not d["status"].startswith("closed")]
CLOSED = [d for d in DEVIATIONS if d["status"].startswith("closed")]
