"""Deviations of the mechanical model from the written specification, with reasons.

This list is written into export/check_report.{json,md} by checks.run_all() and must be copied into
the README.  Numbers are taken from params so they follow the YAML.  `yaml_change` = True means a
SHARED number would have to change; those are detailed in PROPOSED_PARAM_CHANGES.md (the YAML is not edited).
"""
import math
import params as P

M = P.MECH
_lcd_corner_r = math.hypot(P.LCD_X1, P.LCD_Y0)
_lcd_corner_r_fwd = math.hypot(P.LCD_X1, P.LCD_Y0 + P.CLR)

DEVIATIONS = [
    dict(id="D01", part="base_plate / pcb_adhesive", yaml_change=True,
         requirement=f"seven dia {P.PAD_HOLE_D} pad holes at 2.54 pitch",
         implemented=f"one slot {P.PAD_XS[-1] - P.PAD_XS[0] + P.PAD_HOLE_D:.2f} x {P.PAD_HOLE_D} mm through all seven pad positions",
         reason=f"the web between adjacent holes would be {P.PAD_WEB:.2f} mm (< {P.MIN_WALL} mm minimum wall)"),
    dict(id="D02", part="base_plate", yaml_change=True,
         requirement="blind seats for 1.0 mm balls protruding 0.10 mm, wall >= 0.8",
         implemented=f"90 deg conical seat from below; apex at z = {P.BALL_SEAT_APEX_Z:.3f} breaks through the top face as a dia "
                     f"{2 * P.BALL_SEAT_R_TOP:.2f} pin-hole (closed by the PCB adhesive sheet); 0.01 mm modelling gap ball-to-cone",
         reason="the ball top is at z = 0.90 in a 1.00 mm plate, so any blind seat leaves <= 0.10 mm of skin. As-printed MJF tolerance "
                "(+-0.2) also exceeds the 0.10 mm protrusion: seats must be finish-machined (90 deg spot drill to depth) or the balls "
                "set on a jig and potted"),
    dict(id="D03", part="base_plate", yaml_change=False,
         requirement="baffle ring inner dia about 5.4, wall 0.6",
         implemented=f"inner dia {2 * P.BAFFLE_RI:.2f}, wall {M['baffle_wall']}, outer dia {2 * P.BAFFLE_RO:.2f}; spokes at {M['spoke_angles_deg']} deg",
         reason=f"the photodiode body ({P.PD['dx']} x {P.PD['dy']}) has a {2 * P.PD_HALF_DIAG:.2f} mm diagonal and would clash with a 5.4 ring; "
                "0.25 clearance added; wall raised to the 0.8 print minimum. Spokes are unequally spaced because three equal spokes "
                "cannot all avoid LED positions on a 45 deg grid"),
    dict(id="D04", part="tub", yaml_change=True,
         requirement="every printed wall >= 0.8 mm",
         implemented=f"wall behind each window recess in front of the camera cube is {P.THIN_STRIP_T:.3f} mm: z {P.WIN_Z0}..{P.OPEN_Z0} across the "
                     f"{P.WIN_RECESS_W} mm recess and z {P.OPEN_Z0}..{P.HOOD_Z_OVER_CUBE} beside the opening (3.5 mm2 per camera); everywhere else "
                     "behind the recess the visor wall is thickened inward to 0.8",
         reason=f"visor face {P.Y_VISOR} to cube front {P.HOOD_PAD_Y - P.CLR:.3f} leaves {P.Y_VISOR - (P.HOOD_PAD_Y - P.CLR):.3f} mm for "
                f"recess {P.WIN_RECESS_DEPTH} + wall 0.8 + clearance {P.CLR} = {P.WIN_RECESS_DEPTH + 0.8 + P.CLR:.2f} mm"),
    dict(id="D05", part="tub", yaml_change=False,
         requirement="camera opening bevelled wider toward the inside",
         implemented=f"side walls only: {M['visor_land']} mm straight land at the aperture, then {M['visor_bevel_deg']} deg bevel to "
                     f"+-{P.OPEN_HALF_W_INSIDE:.3f} at the inner face; top is the roof underside, bottom is a flat sill at z {P.OPEN_Z0}",
         reason="a knife edge cannot be printed in MJF (the land was 0.3 in the first model; the wall audit put its rim below 0.5 mm, so "
                "it is now 0.5); the camera cube is directly below the sill and the roof directly above"),
    dict(id="D06", part="tub", yaml_change=False,
         requirement="shallow glue channel if possible without going below the wall minimum",
         implemented="no glue channel and no glue chamfer anywhere",
         reason="the arc ledge is 0.65 mm wide and the seal land 0.4 mm: any groove leaves a seal lip below 0.5 mm, and a chamfer on the "
                "0.8 mm visor wall leaves less than 0.8 at its foot (the wall audit flagged a 0.2 mm chamfer at 0.61 mm, so it was removed). "
                "The 0.25 x 1.0 mm radial gap between base edge and side wall is the adhesive reservoir on the arc; on the visor the "
                "adhesive fillets against the 0.15 mm step between the base edge and the visor face"),
    dict(id="D07", part="tub / base_plate", yaml_change=False,
         requirement="two or three 1.2 mm locating pins/keys between base and tub",
         implemented=f"two tub lugs {M['key_w']} x {P.VISOR_WALL} x {P.LEDGE_Z0} mm under the visor wall at x = +-{M['key_x']}, in base notches "
                     f"{2 * P.KEY_NOTCH_HW:.1f} wide",
         reason="no room for round pins inside the seal line (PCB edge to land 0.15 mm; front strip 0.95 mm). The lugs interrupt the "
                "front seal land twice and must be flooded with adhesive (leak-test item)"),
    dict(id="D08", part="tub / vent", yaml_change=True,
         requirement="vent pad near (17, -3)",
         implemented=f"vent at {M['vent_xy']}, pad {M['vent_pad'] + 0.6} x {M['vent_pad']} raised {M['vent_pad_h']} mm, hole dia {P.VENT_HOLE_D}",
         reason=f"a 5 mm disc at (17, -3) would overlap the thick roof ring (r {P.THICK_RING_R}) that carries the cover-glass recess"),
    dict(id="D09", part="tub", yaml_change=False,
         requirement="nose groove from the aperture edge to the visor",
         implemented=f"groove {M['nose_w']} x {M['nose_depth']} from the cover-glass recess edge (r {P.RECESS_D / 2}) to the visor; roof thickened "
                     f"{M['nose_depth']} mm underneath",
         reason="the aperture edge is under the cover glass; the thickening keeps 0.8 mm under the groove"),
    dict(id="D10", part="pcb_adhesive / stack", yaml_change=True,
         requirement="PCB adhesive sheet 0.13 mm; YAML has PCB bottom = base top",
         implemented=f"sheet modelled at true {M['pcb_psa_t']} mm (z {P.BASE_T}..{P.BASE_T + M['pcb_psa_t']}), overlapping the nominal PCB by its own volume "
                     "(allow-listed modelling overlap)",
         reason="the YAML carries the PSA at zero thickness. In the real stack the posts datum the PCB top at tub z = 1.80, so the base "
                "plate sits 0.13 mm lower relative to the tub: seal bead 0.33 instead of 0.20, tub rim 0.13 above the base plane, overall "
                "height 7.73, contact pads 1.13 and optical axis 5.74 above the base plane; all tub-internal clearances are unchanged"),
    dict(id="D11", part="tub / lcd_glass", yaml_change=True,
         requirement="LCD glass assembled from below",
         implemented="glass must be inserted biased 0.25 mm forward (against the front locators) and then slid back",
         reason=f"rear glass corners are at r = {_lcd_corner_r:.3f} > ledge inner radius {P.LEDGE_RI}; biased forward they pass at "
                f"r = {_lcd_corner_r_fwd:.3f} ({P.LEDGE_RI - _lcd_corner_r_fwd:.3f} mm nominal clearance, less than the print tolerance)"),
    dict(id="D12", part="tub / main_pcb", yaml_change=True,
         requirement="0.25 mm clearance on every drop-in fit",
         implemented=f"PCB edge to seating ledge {P.LEDGE_RI - P.PCB_R:.2f} mm; visor window in its recess {(P.WIN_RECESS_W - P.WIN_W) / 2:.2f} mm per side",
         reason="these are YAML / task numbers; kept as specified and flagged"),
    dict(id="D13", part="tub", yaml_change=False,
         requirement="light baffle from the visor wall back to each prism",
         implemented=f"hood: side skirts and a front pad down to z {M['hood_skirt_z0']}, rear wall down to z {P.HOOD_Z_OVER_CUBE} (over the cube), "
                     f"corner fill to the side wall; bottom front edge of the rear wall chamfered {P.HOOD_REAR_CHAMFER:.2f} mm so that it stays "
                     f"{P.PRISM_HOOD_CLR:.2f} mm off the prism hypotenuse (0.18 without it)",
         reason="the rear wall cannot pass the cube (LCD glass 0.63 mm behind it): a 0.25 mm slit remains above the cube top at the rear, "
                "facing the aluminised hypotenuse. PCB keep-out: parts under the skirts must be below 0.95 mm"),
    dict(id="D14", part="tub", yaml_change=False,
         requirement="top edge radius 0.6, bottom chamfer 0.3; cavity below z 1.2 = R 22 circle clipped at the visor face",
         implemented=f"radius and chamfer on the arc only (visor edges sharp); below z = {P.LEDGE_Z0} the side wall ends on the radial plane through the "
                     f"outer D corner (+-{P.HORN_X_OUT:.1f}, {P.Y_VISOR}), which leaves an open notch about {P.HORN_X_OUT - math.sqrt(P.BASE_R ** 2 - P.BASE_FLAT ** 2):.1f} mm wide under each end "
                     "of the visor wall that the seal adhesive must fill",
         reason="the windows are flush with the top, a rounded visor edge would leave them proud; the R 22 circle meets the visor plane at "
                "33 deg and would leave feather-edged wall ends; the radial cut keeps the full 1.0 mm wall at the end face"),
    dict(id="D15", part="cradle", yaml_change=False,
         requirement="nest accepts the puck at 0 and 180 deg about z",
         implemented=f"nest = union of the puck outline at 0 deg and turned 180 deg about the nest centre (0, {P.NEST_CY}); the puck centre "
                     f"moves {P.NEST_SHIFT:.1f} mm between the two positions; at 180 deg the pins bear on the base plate at puck y = "
                     f"{P.cradle_to_puck_180(0, P.PAD_Y)[1]:.1f}",
         reason="a D with one flat cannot be located at both 0 and 180 deg about its own centre by fixed features (any stop on the flat "
                "lies inside the turned outline)"),
    dict(id="D16", part="cradle", yaml_change=False,
         requirement="seven 2.0 mm clearance holes for the spring pins",
         implemented=f"printed body: one slot {P.CRADLE_PIN_SLOT_W:.2f} mm wide (pin body dia {M['pin_body_dia']} + 2 x {P.CLR}); steel plate: seven dia {M['plate_hole_dia']} holes; pin bodies stop "
                     f"{M['pin_body_top_below_plate']} mm below the plate so only the dia {M['pin_plunger_dia']} plunger passes the steel",
         reason="0.54 mm webs are below the print minimum, and a 2.0 mm printed slot would leave only 0.085 mm round the pin body; "
                "0.54 mm webs in 1.5 mm steel are marginal for laser cutting (OPEN); a dia 1.83 "
                "pin body in a dia 2.0 steel hole would risk shorting VBUS to GND through the plate"),
    dict(id="D17", part="cradle", yaml_change=False,
         requirement="spring pins compressed to the working height against the pads; DESIGN_SPEC: a puck placed 180 deg round touches no pins",
         implemented=f"cradle PCB top at z = {P.CPCB_Z1:.2f} (pad plane 1.13 - working height {M['pin_working_h']}); pins are drawn "
                     f"{P.PIN_MODEL_COMPRESSION_EXTRA:.3f} mm shorter than real because the model keeps the YAML PCB height. At 180 deg the pins "
                     "bear on the solid base plate (they touch no pad and no opening)",
         reason=f"OPEN: no hold-down is modelled. Seven pins at {M['pin_force_working_N']} N each (PROVISIONAL) give about "
                f"{7 * M['pin_force_working_N']:.1f} N against a marker weight of about 0.11 N, so the marker is lifted off the reference plate; "
                f"about 9 N applied at the marker centre would be needed to keep all three ball feet seated. At 180 deg the pins are compressed "
                f"{M['pin_max_working_h'] + P.CPCB_Z1:.2f} of {M['pin_full_stroke']} mm full stroke. A hold-down (lid or latch), magnetic retention, "
                "or pins that retract for the flip calibration are required before the cradle can charge reliably or serve as the "
                "calibration seat"),
    dict(id="D18", part="cradle", yaml_change=False,
         requirement="four 3 mm feet pockets; PCB pocket underneath",
         implemented=f"four pockets dia {M['foot_pocket_dia']} x {M['foot_pocket_depth']} for dia {M['foot_dia']} x {M['foot_h']} mm adhesive bumpers; PCB held "
                     f"against the pocket ceiling by four M2 thread-forming screws (not modelled; printed as dia {M['cradle_screw_pilot_dia']} x {M['cradle_screw_pilot_depth']} spot marks, "
                     "drilled dia 1.6 x 3 after printing because a blind 1.7 mm hole would trap powder); "
                     "three lightening pockets underneath",
         reason="'3 mm feet' read as 3 mm high bumpers (ambiguous); the pin force pushes the PCB out of its pocket so it needs positive retention"),
]
