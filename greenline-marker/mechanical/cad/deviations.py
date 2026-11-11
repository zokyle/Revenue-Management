"""Deviations of the mechanical model from the written specification, with reasons (revision C).

This list is written into export/check_report.{json,md} by checks.run_all() and is copied into the README.
Numbers are taken from params so they follow the YAML.

status:
    "closed (rev C)"   the rev C YAML / decision removed the conflict; kept here only as a pointer
    "accepted"         the system owner accepted it in rev C; it stays a recorded deviation
    "recorded"         the model differs from the original task text for a stated reason; no shared number involved
    "open"             needs a decision or a change of a shared number (see PROPOSED_PARAM_CHANGES.md, part B)
`yaml_change` = True means a SHARED number or the shared layout rule would have to change (the YAML is not edited here).
"""
import math
import params as P

M = P.MECH
_lcd_corner_r = math.hypot(P.LCD_X1, P.LCD_Y0)
_lcd_corner_r_fwd = math.hypot(P.LCD_X1, P.LCD_Y0 + P.CLR)
_bundle_in = 1.622 - (P.WIN_RECESS_FLOOR_Y - P.HOOD_FRONT_IN_Y) * math.tan(math.radians(M["fov_h_half_deg"]))

DEVIATIONS = [
    dict(id="D01", part="base_plate / pcb_adhesive", status="closed (rev C)", yaml_change=False,
         requirement="seven dia 2.2 pad holes at 2.54 pitch (rev B)",
         implemented=f"one slot {P.PAD_SLOT_L:.2f} x {P.PAD_HOLE_D} mm",
         reason="rev C YAML specifies the slot (base_plate.pad_holes.form: slot)"),
    dict(id="D02", part="base_plate", status="closed (rev C)", yaml_change=False,
         requirement="blind seats for the 1.0 mm balls (rev B)",
         implemented=f"three dia {P.BALL_HOLE_D} through holes; balls set {P.BALL_PROT} proud on a gauge plate and potted with UV epoxy",
         reason="rev C YAML specifies through holes and the gauge-plate process; the conical seats are removed"),
    dict(id="D03", part="base_plate", status="closed (rev C)", yaml_change=False,
         requirement="baffle ring about dia 5.4, wall 0.6 (rev B task text)",
         implemented=f"inner dia {2 * P.BAFFLE_RI:.2f}, wall {P.BAFFLE_WALL}, spokes at {P.SPOKE_ANGLES} deg",
         reason="rev C YAML carries these numbers (base_plate.baffle)"),
    dict(id="D04", part="tub", status="accepted", yaml_change=False,
         requirement="every printed wall >= 0.8 mm",
         implemented=f"the wall behind each window recess in front of the camera cube is {P.THIN_STRIP_T:.3f} mm: z {P.WIN_Z0}..{P.OPEN_Z0} across the "
                     f"{2 * P.HOOD_IN_HW:.1f} mm bay ({2 * P.HOOD_IN_HW * (P.OPEN_Z0 - P.WIN_Z0):.1f} mm2 per camera); the bonded window backs it",
         reason=f"visor face {P.Y_VISOR} to cube front {P.HOOD_PAD_Y - P.CLR:.3f} leaves {P.Y_VISOR - (P.HOOD_PAD_Y - P.CLR):.3f} mm for "
                f"recess {P.WIN_RECESS_DEPTH} + wall 0.8 + clearance {P.CLR}. Accepted in rev C (visor_window.min_wall_behind_recess = "
                f"{P.Y['visor_window']['min_wall_behind_recess']})"),
    dict(id="D05", part="tub", status="recorded", yaml_change=False,
         requirement="camera opening bevelled wider toward the inside",
         implemented=f"no bevel: the opening is straight, +-{P.OPEN_HALF_W} wide and z {P.OPEN_Z0}..{P.OPEN_Z1}, through the full {P.MIN_WALL} mm of wall, "
                     f"flush with the bay walls (bay half-width {P.HOOD_IN_HW})",
         reason=f"the light bundle diverges outward: it is +-1.62 mm wide at the aperture and only about +-{_bundle_in:.2f} at the inner face, so a "
                f"bevel toward the inside clears nothing. A wider bay would push the hood to more than the {P.KO_HOOD_HW} mm half-width of the "
                f"keep-out contract (hood outside is +-{P.HOOD_OUT_HW}). The straight opening also removes the thin bevelled rim of rev B"),
    dict(id="D06", part="tub", status="recorded", yaml_change=False,
         requirement="shallow glue channel if possible without going below the wall minimum",
         implemented="no glue channel and no glue chamfer anywhere",
         reason="the arc ledge is 0.65 mm wide and the seal land 0.4 mm: any groove leaves a seal lip below 0.5 mm, and a chamfer on the "
                f"0.8 mm visor wall leaves less than 0.8 at its foot. The {P.CLR} x {P.LEDGE_Z0} mm radial gap between base edge and side wall is the "
                f"adhesive reservoir on the arc; the bead itself is {P.BEAD_T:.2f} mm thick in rev C"),
    dict(id="D07", part="tub / base_plate", status="recorded", yaml_change=False,
         requirement="two or three 1.2 mm locating pins/keys between base and tub",
         implemented=f"two tub lugs {M['key_w']} x {P.VISOR_WALL} x {P.LEDGE_Z0} mm under the visor wall at x = +-{M['key_x']}, in base notches "
                     f"{2 * P.KEY_NOTCH_HW:.1f} wide",
         reason="no room for round pins inside the seal line (front strip 0.95 mm). The lugs interrupt the front seal land twice and must be "
                "flooded with adhesive (leak-test item)"),
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
         implemented="glass is inserted biased 0.25 mm forward (against posts E and the hood rear walls) and then slid back: an assembly step",
         reason=f"rear glass corners are at r = {_lcd_corner_r:.3f} > ledge inner radius {P.LEDGE_RI}; biased forward they pass at "
                f"r = {_lcd_corner_r_fwd:.3f} ({P.LEDGE_RI - _lcd_corner_r_fwd:.3f} mm nominal clearance, less than the print tolerance). Accepted in rev C"),
    dict(id="D12", part="tub / main_pcb / windows", status="closed (rev C)", yaml_change=False,
         requirement="0.25 mm clearance on every drop-in fit",
         implemented=f"PCB edge to seating ledge {P.LEDGE_RI - P.PCB_R:.2f} mm; visor window in its recess {(P.WIN_RECESS_W - P.WIN_W) / 2:.2f} mm per side",
         reason="rev C YAML: pcb.radius 21.1 and visor_window.recess_w 5.5"),
    dict(id="D13", part="tub", status="accepted", yaml_change=False,
         requirement="light baffle from the visor wall back to each prism (light-tight)",
         implemented=f"hood: side skirts and a front pad down to z {M['hood_skirt_z0']}, rear wall down to z {P.HOOD_Z_OVER_CUBE} (over the cube); bottom "
                     f"front edge of the rear wall chamfered {P.HOOD_REAR_CHAMFER:.2f} mm ({P.PRISM_HOOD_CLR:.2f} mm to the prism hypotenuse). "
                     f"A slit of {P.HOOD_SLIT[0]:.2f} to {P.HOOD_SLIT[1]:.2f} mm remains above the cube at the rear",
         reason="the rear wall cannot pass the cube (LCD glass 0.63 mm behind it). Rev C: the slit is closed with a dab of black adhesive at "
                "assembly (README assembly step); the light-leak coupon test stays on the test list"),
    dict(id="D14", part="tub", status="recorded", yaml_change=False,
         requirement="top edge radius 0.6, bottom chamfer 0.3; cavity below z 1.2 = R 22 circle clipped at the visor face",
         implemented=f"radius and chamfer on the arc only (visor edges sharp); below z = {P.LEDGE_Z0} the side wall ends on the radial plane through the "
                     f"outer D corner (+-{P.HORN_X_OUT:.1f}, {P.Y_VISOR}), which leaves an open notch about {P.HORN_X_OUT - math.sqrt(P.BASE_R ** 2 - P.BASE_FLAT ** 2):.1f} mm wide under each end "
                     "of the visor wall that the seal adhesive must fill",
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
                     f"({M['latch_w']} x {M['latch_h']} x {P.LATCH_L:.2f} mm, hook {P.HOOK_OVERLAP:.2f} mm on the tub top) with a thumb tab",
         reason="designed and proven in check 7 (retention, strain, forces, posed insertion path)"),
    dict(id="D18", part="cradle", status="recorded", yaml_change=False,
         requirement="four 3 mm feet pockets; PCB pocket underneath",
         implemented=f"four pockets dia {M['foot_pocket_dia']} x {M['foot_pocket_depth']} for dia {M['foot_dia']} x {M['foot_h']} mm adhesive bumpers; PCB held "
                     f"against the pocket ceiling by four M2 thread-forming screws (not modelled; printed as dia {M['cradle_screw_pilot_dia']} x {M['cradle_screw_pilot_depth']} spot marks, "
                     "drilled dia 1.6 x 3 after printing because a blind 1.7 mm hole would trap powder); three lightening pockets underneath",
         reason="'3 mm feet' read as 3 mm high bumpers (ambiguous); the pin force pushes the PCB out of its pocket so it needs positive retention"),
    dict(id="D19", part="tub / main_pcb", status="open", yaml_change=True,
         requirement="PCB located to the tub by two printed spigots in non-plated holes (rev C YAML)",
         implemented=f"spigots dia {P.SPIGOT_D} x {P.SPIGOT_H} under posts E in a dia {P.LOC_ROUND[2]} hole and a {P.LOC_SLOT[2]} x {P.LOC_SLOT[3]} slot: "
                     f"{P.SPIGOT_FIT:.3f} mm radial clearance, as specified",
         reason=f"{P.SPIGOT_FIT:.3f} mm is a locating fit, far below the {P.CLR} mm drop-in rule and below the +-0.2 mm print tolerance: a spigot that "
                "prints 0.15 mm oversize does not enter. The spigots are therefore a gauged feature (go / no-go at first article, dress with a "
                "hollow punch or fine file). Part B of PROPOSED_PARAM_CHANGES.md offers a looser hole with the optical margin it costs"),
    dict(id="D20", part="cradle", status="recorded", yaml_change=True,
         requirement=f"cradle body {P.CRADLE_SIZE[0]:.0f} x {P.CRADLE_SIZE[1]:.0f} x {P.CRADLE_SIZE[2]:.0f} mm",
         implemented=f"body {P.CRADLE_SIZE[0]:.0f} x {P.CRADLE_SIZE[1]:.0f} x {P.CRADLE_SIZE[2]:.0f} (z {P.CRADLE_BOT_Z} to {P.CRADLE_TOP_Z}); the lip stands to z {P.LIP_Z1:.2f} and the latch to z "
                     f"{P.LATCH_TOP_Z:.2f}, so the printed part is {P.LATCH_TOP_Z - P.CRADLE_BOT_Z:.1f} mm tall; the body is not centred on the marker "
                     f"(y {P.CRADLE_Y0} to {P.CRADLE_Y1})",
         reason=f"a hook over the marker top (z {P.T}) with a {P.LATCH_L:.2f} mm cantilever and a {M['hook_lead_deg']:.0f} deg lead-in cannot stay inside a "
                "14 mm block; the rear needs the room for the latch well, the guard wall and the USB-C receptacle behind it"),
    dict(id="D21", part="cradle / marker", status="recorded", yaml_change=True,
         requirement="the marker rests on its three ball feet on the nest floor, pins at the working height",
         implemented=f"lip and hook have the {P.CLR} mm drop-in clearance above the tub top. With pins fitted the marker is pushed up against them: it "
                     f"floats up to {P.CLR} mm above its feet and the pins then work at {P.PIN_WORK_H + P.CLR:.2f} instead of {P.PIN_WORK_H} mm "
                     f"({M['pin_mid_stroke'] - P.CLR:.2f} of {M['pin_full_stroke']} mm stroke used)",
         reason="a 90 deg retaining face cannot preload a part whose height varies by the print tolerance; the float is inside the pin stroke. "
                "A dock does not need a seating datum (calibration is done elsewhere)"),
    dict(id="D22", part="tub / PCB layout", status="open", yaml_change=True,
         requirement="tub_keepouts is the complete contract: every tub feature that touches or hangs over the PCB top lies inside it",
         implemented=f"true for everything below z = {P.KO_FREE_Z:.2f} ({P.PCB_FREE_H} mm above the PCB top), which check 12 proves on the solids. Above that "
                     f"height the tub still has features over the PCB outside the keep-outs: glass locating ribs down to z {M['lcd_rib_z0']}, the thick "
                     f"roof at z {P.BOND_Z} (also behind and beside the LCD glass), the nose pad at z {P.ROOF_Z - M['nose_depth']:.1f} and the vent pad at z {P.VENT_PAD_Z:.1f}",
         reason="design/check_layout.py lets a part outside the LCD footprint reach z = roof - 0.1 = 6.7. No listed part is taller than "
                "2.0 mm there, so nothing clashes today, but the rule and the tub disagree: a free height must be added to the contract"),
]

OPEN = [d for d in DEVIATIONS if not d["status"].startswith("closed")]
CLOSED = [d for d in DEVIATIONS if d["status"].startswith("closed")]
