"""Deviations of the mechanical model from the written specification, with reasons (revision D as amended: decisions N1 to N10,
spec amendments E1 to E16).

This list is written into export/check_report.{json,md} by checks.run_all() and is copied into the README.
Numbers are taken from params so they follow the YAML.

status:
    "closed (rev C)" / "closed (rev D)" / "closed (rev D amended, N<n>)"
                       that YAML revision or decision removed the conflict (the model is now what the specification says and
                       params asserts it); kept here only as a pointer
    "accepted"         the system owner accepted it; it stays a recorded deviation from a general rule
    "recorded"         the model differs from the specification text for a stated reason
    "open"             needs a decision or a change of a shared number (see PROPOSED_PARAM_CHANGES.md, part C: part B of that
                       file is the disposition of the decided proposals N1 to N10)
`yaml_change` = True means a SHARED number or the shared text would have to change (the YAML is not edited here); the
proposal is in PROPOSED_PARAM_CHANGES.md, part C.
"""
import math
import params as P
import optics as O
import legend as L

M = P.MECH
_lcd_corner_r = math.hypot(P.LCD_X1, P.LCD_Y0)
_lcd_corner_r_fwd = math.hypot(P.LCD_X1, P.LCD_Y0 + M["lcd_bias"])
_bundle_pad = 1.622 - P.THIN_STRIP_T * math.tan(math.radians(P.FOV_H))
_alt = P.BASE_VARIANTS[P.BASE_ALT]
_uf_lim = O.upper_field_closed_form(M["print_tol"])
_uf_play = O.upper_field_closed_form(M["print_tol"], P.spigot_play()["fore_aft"])
_uf_a, _uf_L, _uf_m = O.upper_field_terms(M["print_tol"])
_gap = lambda v: v["accept"][0] + (v["psa_t"] - v["psa_tol"]) - (P.BALL_TOP_Z + M["tol_ball_set"])      # epoxy under a nominal ball at the lower plate limit
_ink_to_opening = L.geometry().distance(L.feature_shapes()["grain opening"])                               # legend ink to the grain opening (1.2)
_gap_g100, _gap_g100_pa = (_gap(P.BASE_VARIANTS[k]) - M["ball_dia_tol"] for k in ("fr4", "pa12"))

DEVIATIONS = [
    dict(id="D01", part="base_plate / pcb_adhesive", status="closed (rev C)", yaml_change=False,
         requirement="seven dia 2.2 pad holes at 2.54 pitch (rev B)",
         implemented=f"one slot {P.PAD_SLOT_L:.2f} x {P.PAD_HOLE_D} mm",
         reason="rev C YAML specifies the slot (base_plate.pad_holes.form: slot); rev D keeps it at y -17.0, 2.2 wide (B20 not adopted)"),
    dict(id="D02", part="base_plate", status="closed (rev C)", yaml_change=False,
         requirement="blind seats for the 1.0 mm balls (rev B)",
         implemented=f"three through holes (drilled dia {P.BALL_HOLE_D} in the FR-4 plate, dia {_alt['foot_hole_d']} in the PA12 plate); balls set {P.BALL_PROT} proud on a "
                     "gauge plate and potted",
         reason="rev C YAML specifies through holes and the gauge-plate process; rev D gives the hole diameter per plate"),
    dict(id="D03", part="base_plate / baffle_ring", status="closed (rev D)", yaml_change=False,
         requirement="baffle ring round the photodiode",
         implemented=f"inner dia {2 * P.BAFFLE_RI:.1f}, outer dia {2 * P.BAFFLE_RO:.1f}: a separate printed ring in the FR-4 build, integral on spokes at "
                     f"{P.SPOKE_ANGLES} deg in the PA12 plate",
         reason=f"rev D YAML carries the rebalanced ring (proposal B11): {P.BAFFLE_RI - P.PD_HALF_DIAG:.3f} mm to the photodiode, {P.LED_R_IN - P.BAFFLE_RO:.2f} mm to the LEDs"),
    dict(id="D04", part="tub", status="accepted", yaml_change=False,
         requirement="every printed wall >= 0.8 mm",
         implemented=f"the wall behind each window recess in front of the camera cube is {P.THIN_STRIP_T:.3f} mm: z {P.WIN_Z0}..{P.OPEN_Z0} across the "
                     f"{2 * P.HOOD_IN_HW:.1f} mm bay ({2 * P.HOOD_IN_HW * (P.OPEN_Z0 - P.WIN_Z0):.1f} mm2 per camera); the bonded window backs it",
         reason=f"visor face {P.Y_VISOR} to cube front {P.HOOD_PAD_Y - P.CLR:.3f} leaves {P.Y_VISOR - (P.HOOD_PAD_Y - P.CLR):.3f} mm for "
                f"recess {P.WIN_RECESS_DEPTH} + wall 0.8 + clearance {P.CLR}. Accepted in rev C (visor_window.min_wall_behind_recess = "
                f"{P.Y['visor_window']['min_wall_behind_recess']})"),
    dict(id="D05", part="tub", status="closed (rev D)", yaml_change=False,
         requirement="camera opening bevelled wider toward the inside (rev C text)",
         implemented=f"straight opening, +-{P.OPEN_HALF_W} wide and z {P.OPEN_Z0}..{P.OPEN_Z1}, as wide as the prism bay behind it",
         reason=f"rev D adopts the straight opening (proposal B4; YAML visor_window.opening, DESIGN_SPEC section 5): the bundle is +-1.62 mm wide at the aperture "
                f"plane and +-{_bundle_pad:.2f} mm at the inner edge of the sill, so a bevel clears nothing"),
    dict(id="D06", part="tub", status="recorded", yaml_change=False,
         requirement="shallow glue channel if possible without going below the wall minimum",
         implemented="no glue channel and no glue chamfer anywhere",
         reason="the arc ledge is 0.65 mm wide and the seal land 0.4 mm: any groove leaves a seal lip below 0.5 mm, and a chamfer on the "
                f"0.8 mm visor wall leaves less than 0.8 at its foot. The {P.CLR} mm radial groove between base edge and side wall is the adhesive "
                f"reservoir on the arc (it is filled down to the rim and modelled as part of the bead); the joint on the land is {P.BEAD_T:.2f} mm high "
                f"(FR-4 plate; {P.LEDGE_Z0 - _alt['thickness']:.2f} mm on the PA12 plate)"),
    dict(id="D07", part="tub / base_plate", status="closed (rev D)", yaml_change=False,
         requirement="two or three 1.2 mm locating pins/keys between base and tub (original task text)",
         implemented="no key between base plate and tub; plain base edge. The plate is laminated to the PCB in a jig, the PCB / base unit is located in the tub by "
                     "the two spigots of posts B",
         reason="rev D adopts it (proposal B22 a): a key under the visor wall interrupts the seal land; check 13 proves the seal ring closed"),
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
         implemented=f"rev D: FR-4 base plate {P.BASE_T} + sheet {P.PSA_T} (z {P.PSA_Z0}..{P.PSA_Z1}); PCB at z {P.PCB_Z0}..{P.PCB_Z1}; alternative PA12 plate "
                     f"{_alt['thickness']} + sheet {_alt['psa_t']}; no modelling overlap",
         reason="rev C gave the sheet its own thickness; rev D sets the two plate / sheet pairs (base_plate.thickness, psa.thickness, alternative)"),
    dict(id="D11", part="tub / lcd_glass", status="accepted", yaml_change=False,
         requirement="LCD glass assembled from below",
         implemented=f"the glass is tilted in: rear edge first at {M['lcd_tilt_deg']:.0f} deg, shifted {M['lcd_bias']} mm toward the visor while its rear corners "
                     f"pass the seating ledge, then pushed back against the two rear glass ribs (which reach down to z {P.LCD_REAR_RIB_Z0}) and hinged up "
                     "(assembly step 9, path proven in check 14)",
         reason=f"rear glass corners are at r = {_lcd_corner_r:.3f} > ledge inner radius {P.LEDGE_RI}. Rev C accepted a flat insertion biased {P.CLR} mm forward "
                f"({P.LEDGE_RI - math.hypot(P.LCD_X1, P.LCD_Y0 + P.CLR):.3f} mm to the ledge, less than the print tolerance); the design review showed that the "
                f"flat glass cannot go further forward because posts E stop it. Tilted, the front edge is still below the post feet while the rear corners "
                f"pass, so the shift can be {M['lcd_bias']} mm (corners at r = {_lcd_corner_r_fwd:.3f})"),
    dict(id="D12", part="tub / main_pcb / windows", status="closed (rev C)", yaml_change=False,
         requirement="0.25 mm clearance on every drop-in fit",
         implemented=f"PCB edge to seating ledge {P.LEDGE_RI - P.PCB_R:.2f} mm; visor window in its recess {(P.WIN_RECESS_W - P.WIN_W) / 2:.2f} mm per side",
         reason="rev C YAML: pcb.radius 21.1 and visor_window.recess_w 5.5"),
    dict(id="D13", part="tub", status="closed (rev D)", yaml_change=False,
         requirement="light baffle from the visor wall back to each prism (light-tight)",
         implemented=f"hood: side skirts and a front pad down to z {M['hood_skirt_z0']}, rear wall down to z {P.HOOD_Z_OVER_CUBE} (over the cube); bottom "
                     f"front edge of the rear wall chamfered {P.HOOD_REAR_CHAMFER:.2f} mm ({P.PRISM_HOOD_CLR:.2f} mm to the prism hypotenuse). "
                     f"The slit of {P.HOOD_SLIT[0]:.2f} to {P.HOOD_SLIT[1]:.2f} mm above the cube at the rear is closed by a bead of black gasket material "
                     f"({M['hood_seal_w']} mm wide x {M['hood_seal_free_h']} mm high as dispensed, {P.HOOD_SEAL_VOL:.2f} mm3, on the underside of the rear wall astride the rear edge of the "
                     f"cube, CURED before the PCB is joined; the cube squeezes it by {100 * P.HOOD_SEAL_COMPRESSION:.0f} % over a land of {P.HOOD_SEAL_CONTACT_W:.2f} mm, modelled at constant volume)",
         reason="rev D adopts the pre-cured gasket (proposal B22 c; DESIGN_SPEC section 5, part 1). The gaps beside and in front of the cube "
                "(0.265 / 0.25 mm) stay open: light-leak test (README test items)"),
    dict(id="D14", part="tub", status="recorded", yaml_change=False,
         requirement="top edge radius 0.6, bottom chamfer 0.3; cavity below z 1.2 = R 22 circle clipped at the visor face",
         implemented=f"radius and chamfer on the arc only (visor edges sharp); below z = {P.LEDGE_Z0} the side wall ends on the radial plane through the "
                     f"outer D corner (+-{P.HORN_X_OUT:.1f}, {P.Y_VISOR}), which leaves an open pocket about {P.HORN_X_OUT - P.BASE_CORNER_X:.1f} mm wide under each end "
                     "of the visor wall. The pockets lie OUTSIDE the seal ring (the bead runs round both D corners on the base land)",
         reason="a rounded visor edge would cut into the window recesses, which are open to the top face; the R 22 circle meets the visor plane at "
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
         reason="designed and proven in check 7; rev D carries the lip and latch numbers in the YAML (cradle.hold_down)"),
    dict(id="D18", part="cradle", status="recorded", yaml_change=False,
         requirement="four 3 mm feet pockets; PCB pocket underneath",
         implemented=f"four pockets dia {M['foot_pocket_dia']} x {M['foot_pocket_depth']} for dia {M['foot_dia']} x {M['foot_h']} mm adhesive bumpers, each with a blind core "
                     f"dia {M['core_dia']} behind it (the corners would otherwise be 13 mm solid); PCB held "
                     f"against the pocket ceiling by four M2 thread-forming screws (not modelled; printed as dia {M['cradle_screw_pilot_dia']} x {M['cradle_screw_pilot_depth']} spot marks, "
                     "drilled dia 1.6 x 3 after printing because a blind 1.7 mm hole would trap powder); three lightening pockets underneath",
         reason="'3 mm feet' read as 3 mm high bumpers (ambiguous); the pin force pushes the PCB out of its pocket so it needs positive retention"),
    dict(id="D19", part="tub / main_pcb", status="accepted", yaml_change=False,
         requirement="0.25 mm clearance on every drop-in fit",
         implemented=f"the two PCB locating spigots (dia {P.SPIGOT_D} x {P.SPIGOT_H}, tip chamfered {M['spigot_tip_chamfer']}) under posts B sit in a dia {P.LOC_ROUND[2]} hole and a "
                     f"{P.LOC_SLOT[2]} x {P.LOC_SLOT[3]} slot with {P.SPIGOT_FIT:.3f} mm radial clearance, as the YAML specifies",
         reason=f"a locating fit, not a drop-in fit: rev D keeps it and moves the pair to posts B ({P.SPIGOT_SPAN} mm apart, the cameras between them), which cuts the "
                f"fore-aft play at a camera to +-{P.spigot_play()['fore_aft']:.3f} mm and the yaw to +-{P.spigot_play()['yaw_deg']:.2f} deg. {P.SPIGOT_FIT:.3f} mm is below the "
                "+-0.2 mm print tolerance, so the spigots are a gauged feature (go gauge dia 1.10 at first article; dress an oversize spigot, never "
                "the PCB hole). They only locate until the adhesives have cured"),
    dict(id="D20", part="cradle", status="closed (rev D)", yaml_change=False,
         requirement=f"cradle body {P.CRADLE_SIZE[0]:.0f} x {P.CRADLE_SIZE[1]:.0f} x {P.CRADLE_SIZE[2]:.0f} mm",
         implemented=f"body {P.CRADLE_SIZE[0]:.0f} x {P.CRADLE_SIZE[1]:.0f} x {P.CRADLE_SIZE[2]:.0f} (z {P.CRADLE_BOT_Z} to {P.CRADLE_TOP_Z}, y {P.CRADLE_Y0} to {P.CRADLE_Y1}); with lip "
                     f"and latch {P.LATCH_TOP_Z - P.CRADLE_BOT_Z:.2f} mm overall",
         reason="rev D YAML carries these numbers (cradle.body.y, overall_height; proposal B5)"),
    dict(id="D21", part="cradle / marker", status="closed (rev D)", yaml_change=False,
         requirement="the marker rests on its three ball feet on the nest floor, pins at the working height",
         implemented=f"with pins fitted the marker floats up to {M['cradle_float']} mm against lip and hook; the pins then stand {P.PIN_FLOAT_H:.2f} instead of "
                     f"{P.PIN_WORK_H} mm high ({P.PIN_COMPRESSION - M['cradle_float']:.2f} of {M['pin_full_stroke']} mm stroke used)",
         reason="rev D YAML states the float (cradle.float; proposal B7)"),
    dict(id="D22", part="tub / PCB layout", status="closed (rev D)", yaml_change=False,
         requirement="tub_keepouts is the complete contract: every tub feature that touches or hangs over the PCB top lies inside it",
         implemented=f"true below z = {P.KO_FREE_Z:.2f} ({P.PCB_FREE_H} mm above the PCB top), which check 12 proves on the solids; above it the tub has the glass "
                     f"locating ribs (side ribs from z {M['lcd_rib_z0']}, the two rear ribs from z {P.LCD_REAR_RIB_Z0}, exactly the free height), the thick roof (z {P.BOND_Z:.2f}) and the "
                     "nose and vent pads",
         reason="rev D adds tub_keepouts.free_height_above_pcb and design/check_layout.py uses it (proposal B1)"),
    dict(id="D23", part="tub", status="closed (rev D)", yaml_change=False,
         requirement="tub side wall from z = 0 (the base plane) to the top (rev C)",
         implemented=f"the side wall ends {P.RIM_Z} mm above the base plane: the tub is {P.T - P.RIM_Z:.2f} mm tall, the marker still {P.T} mm; the rim is "
                     f"{P.RIM_Z + P.BALL_PROT:.2f} mm above the plane of the ball feet",
         reason="rev D YAML: envelope.rim_relief (proposal B9)"),
    dict(id="D24", part="tub / vent", status="closed (rev D)", yaml_change=False,
         requirement="vent on a pad raised 0.2 mm, plain top face (rev C)",
         implemented=f"pad raised {M['vent_pad_h']} mm and run out to the side wall; two grooves {M['vent_groove_w']} wide x {M['vent_groove_d']} deep through the vent hole on the top face",
         reason="rev D YAML vent.location describes exactly this (proposal B10)"),
    dict(id="D25", part="cradle", status="closed (rev D)", yaml_change=False,
         requirement="the marker rests on its three ball feet on the printed nest floor",
         implemented=f"front strip (y >= {P.STRIP_Y0}) and two pads dia {M['ball_pad_dia']} at z = {P.NEST_FLOOR_Z}; the rest of the floor is a drained basin "
                     f"{M['basin_depth']} mm lower on the centre line, falling {M['basin_fall_deg']} deg to both sides",
         reason="rev D YAML: cradle.seat_z and its comment (proposal B22 d)"),
    dict(id="D26", part="lcd_adhesive", status="closed (rev D)", yaml_change=False,
         requirement="adhesive frame bonding the LCD under the roof ledge (closed frame, rev C)",
         implemented=f"frame with a {M['lcd_psa_vent_w']} mm vent channel from the dia {M['lcd_psa_window_dia']} window to its rear right corner (die cut GL1-032)",
         reason="rev D DESIGN_SPEC section 5: 'the LCD adhesive frame has a vent channel' (proposal B22 b)"),
    dict(id="D27", part="base_plate / pcb_adhesive / main_pcb", status="closed (rev D)", yaml_change=False,
         requirement="balls potted in through holes",
         implemented=f"two stages: the hole round the ball, then the back-fill of the dia {P.PSA_FOOT_HOLE_D} sheet hole, so that each ball bears on a dia {P.FOOT_LAND_D} "
                     f"copper land of the PCB through {P.PCB_Z0 - P.BALL_TOP_Z:.2f} mm of epoxy (stage 1 dome at most {M['epoxy_dome_max']} mm)",
         reason="rev D YAML: base_plate.feet.backfill, epoxy_dome_max, pcb_land_dia, pcb_keepout_dia and tub_keepouts.foot_zones (proposal B6)"),
    dict(id="D28", part="cradle", status="closed (rev D)", yaml_change=False,
         requirement="cradle pins at their working height on the pad plane",
         implemented=f"cradle PCB top at z = {P.CPCB_Z1:.3f}: the pins stand {P.PIN_WORK_H} mm on the copper face of the pads (z {P.PAD_Z0})",
         reason=f"rev D YAML: cradle.pad_plane_z = {P.CRADLE_PAD_Z} is the copper face (proposal B7)"),
    dict(id="D29", part="tub / PCB layout", status="closed (rev D amended, N1)", yaml_change=False,
         requirement=f"feet of the locating posts B {P.KO_LOC_SIZE} x {P.KO_LOC_SIZE} mm, centred on the spigots (rev D before the amendment)",
         implemented=f"feet {P.LOC_FOOT[0]:.1f} x {P.LOC_FOOT[1]:.1f} mm with their inner faces at |x| = {P.LCD_POCKET_X}, inside the {P.KO_LOC_SIZE} mm keep-out squares",
         reason=f"the amended YAML states the foot as built (tub_keepouts.post_feet.locating.foot: dx {P.KO_LOC_FOOT['dx']}, dy {P.KO_LOC_FOOT['dy']}, x_inner {P.KO_LOC_FOOT['x_inner']}); params asserts it. "
                f"The LCD glass ({P.LCD['dx']} mm wide) passes between the two posts"),
    dict(id="D30", part="visor_window / window_bond", status="closed (rev D amended, N2)", yaml_change=False,
         requirement=f"visor window {P.WIN_T} mm thick in the {P.WIN_RECESS_DEPTH} mm recess, bonded with an adhesive line behind the glass (rev C: 0.05 mm)",
         implemented=f"glass seated bare on the recess floor, {P.WIN_SUBFLUSH:.2f} below the visor face; sealed by a closed frame of thixotropic adhesive round its edge "
                     f"(side gaps, top bead {M['window_top_bead']}, sill fillet {P.WIN_SILL_FILLET} x {P.WIN_SILL_FILLET}); nothing behind the glass",
         reason=f"the amended YAML says exactly this (visor_window.sub_flush {P.Y['visor_window']['sub_flush']}, bond_line {P.Y['visor_window']['bond_line']}, bond); params asserts the numbers; "
                "check 13 proves that the frame, not the bare seat, closes the opening"),
    dict(id="D31", part="tub / optics", status="closed (rev D amended, N3)", yaml_change=False,
         requirement="upper field 15.0 deg guaranteed at the tolerance limit (rev D before the amendment)",
         implemented=f"YAML up_guaranteed = {P.FOV_UP_GUAR} deg, DEFINED as the worst case with the optics {M['print_tol']} mm high and the {P.spigot_play()['fore_aft']:.3f} mm fore-aft play of the spigot fit "
                     f"against it: the model gives {_uf_play:.2f} deg there (closed form {_uf_play:.3f}; {_uf_lim:.2f} without the play)",
         reason=f"check 4 compares the with-play figure with the YAML strictly and fails below it; the margin is {_uf_play - P.FOV_UP_GUAR:.2f} deg (closed form: {_uf_a:.2f} tan(t) + {_uf_L:.2f} tan(t') = "
                f"{_uf_m:.2f} mm, sin(t) = {M['n_prism']} sin(t'), without the play)"),
    dict(id="D32", part="grain_potting / baffle_ring", status="closed (rev D amended, N4 and E16)", yaml_change=False,
         requirement="clear potting with its surface 0.05 below the base plane; baffle ring with its top flush with the potting (rev D before the amendment)",
         implemented=f"potting surface never closer to the base plane than z {P.GRAIN_FILL_Z}, aimed at z {P.GRAIN_FILL_TARGET_Z}, accepted to z {P.GRAIN_FILL_Z_MAX} and from the ring crest to "
                     f"{M['grain_fill_below_crest']} inside it; separate ring {P.BAFFLE_RING_H:.2f} +{M['baffle_ring_tol'][0]:.2f} / -{M['baffle_ring_tol'][1]:.2f} for the nominal plate, lapped to "
                     f"plate thickness + {P.BAFFLE_RING_RULE:.2f} - tape thickness, crest z {P.baffle_crest_range()['matched'][0]:.2f} to {P.baffle_crest_range()['matched'][1]:.2f} (accepted 0 to {P.BAFFLE_CREST_MAX_Z})",
         reason="the amended YAML carries these numbers (base_plate.grain_cavity.fill_surface_z, base_plate.baffle.ring); the model reads them and asserts target, ring height, crest window "
                f"and tape range; E16: the tape is {min(P.BAFFLE_TAPE_RANGE)} to {max(P.BAFFLE_TAPE_RANGE)} mm as available (modelled {P.BAFFLE_PSA_T})"),
    dict(id="D33", part="ball feet / base_plate", status="recorded", yaml_change=True,
         requirement=f"plates accepted from {P.BASE_VARIANTS['fr4']['accept'][0]:.2f} mm (PA12 {P.BASE_VARIANTS['pa12']['accept'][0]:.2f}): the lower limit keeps {M['ball_gap_min']} mm of epoxy between each ball and "
                     f"its land (YAML base_plate.thickness_accepted, N6); balls of grade 100 or better (E8)",
         implemented=f"true for a ball of exactly {P.BALL_D} mm. A grade 100 ball may be {M['ball_dia_tol']} mm larger (basic diameter tolerance, ABMA figure as remembered): set to its protrusion on the gauge "
                     f"plate it stands that much higher, and {_gap_g100:.3f} mm (PA12 {_gap_g100_pa:.3f}) of epoxy is left at the lower plate limit. Incoming rule of this package: the ball lot is measured and "
                     f"the lower plate limit is raised by the oversize of the lot ({P.BASE_VARIANTS['fr4']['accept'][0] + M['ball_dia_tol']:.3f} mm at the grade limit)",
         reason=f"E8 widened the ball grade from 25 (+-{M['ball_dia_tol_g25']} mm) to 100 after the plate limits were fixed; no grade 25 ball in 316 stainless was found at 1 mm (docs/SOURCING.md). "
                "The protrusion, not the ball top, is what the gauge plate sets. Check 2 carries the row as this deviation"),
    dict(id="D34", part="fixtures on the outer face (calibration seat plate, ball gauge plate, bridge gauge) / base_plate legend", status="recorded", yaml_change=True,
         requirement="turf-seat zero on a plate with three clearance pockets for the balls so that the base face seats (DESIGN_SPEC section 6, E11); legend at least "
                     f"{M['legend_clear']} mm from the ball-foot holes (E10); balls set on a gauge plate (YAML base_plate.feet)",
         implemented=f"no fixture bears on printed legend. The base face seats on three annular pads (dia {P.CAL['pad_od']} round each dia {P.CAL['pocket_dia']} x {P.CAL['pocket_depth']} pocket, trimmed "
                     f"{M['legend_edge_margin']} inside the plate outline), not on the whole face; the ball gauge plate of assembly step 2 carries the base plate on three bosses dia {P.GAUGE['boss_od']} "
                     f"round its gauge holes, its face {P.GAUGE['relief']} lower elsewhere; every depth reading on the underside (ring crest, potting level, rim relief) is taken with a bridge gauge on three "
                     f"annular feet dia {P.BRIDGE['foot_od']} / {P.BRIDGE['foot_bore']} round the balls. The legend is kept out of a dia {P.CAL_LEGEND_ZONE_D:.1f} zone round each ball foot and "
                     f"{M['legend_registration']} or more from each of these footprints (checks 15 and 18)",
         reason=f"a printed legend stands about {M['legend_ink_t']} mm proud of the mask ({M['legend_ink_t_max']} at most) and the tub rim is only {P.RIM_Z} above the base plane. On a full-face hard seat the marker "
                f"would rest on ink islands, on a bowed plate or on the rim ({M['legend_ink_t']} mm across the foot triangle is about {1000 * M['legend_ink_t'] / 24.5:.1f} mrad); on a flat gauge plate the ink would "
                f"add itself to the ball protrusion ({P.BALL_PROT} +-{M['tol_ball_set']}) and take the same {M['legend_ink_t_max']} from the epoxy between ball and land ({M['ball_gap_min']} at the lower plate "
                f"limit); a depth gauge resting on legend {_ink_to_opening:.1f} mm from the grain opening would read the potting level that much deep against a never-below "
                f"limit of {P.GRAIN_FILL_Z}. Three points next to the feet on bare mask are one reference plane for all of these, and they measure what E11 is about: the plane of the base face against the plane "
                "of the balls. A laser-marked legend has no height and would not need this"),
    dict(id="D35", part="retarder_film (optional) / cover_glass", status="recorded", yaml_change=True,
         requirement="quarter-wave film, about 0.1 mm, on the underside of the cover glass, axis 45 deg to the LCD polariser; 1.08 mm of air between display and glass, so nothing else moves (E9)",
         implemented=f"film dia {P.RETARDER_D} x {P.RETARDER_T} (with its laminating adhesive) with a clocking flat {P.RETARDER_FLAT_LEN:.1f} long toward the visor: {P.RETARDER_Z0 - P.LCD_Z1:.2f} mm to the display, "
                     f"{(M['cover_tape_id'] - P.RETARDER_D) / 2:.2f} mm inside the bore of the tape ring ({P.retarder_chain()['bore'][1]:.2f} left after the centring chain at its worst case), "
                     f"{(P.RETARDER_D - P.APERTURE_D) / 2:.2f} beyond the aperture ({P.retarder_chain()['aperture'][1]:.2f} after the chain; {P.retarder_chain()['flat'][1]:.2f} at the flat). Outside the dia "
                     f"{P.APERTURE_D} aperture it lies over the roof ledge in the {P.CG_TAPE_T} mm gap that the tape leaves: {P.RETARDER_LEDGE_GAP:.2f} mm nominal, "
                     f"{P.RETARDER_LEDGE_GAP_MIN:.3f} mm with the tape at its thinnest and the film {M['retarder_t_tol']} thicker",
         reason=f"the air gap of 1.08 mm exists only inside the aperture. A film (with adhesive) thicker than {P.RETARDER_T + M['retarder_t_tol']:.2f} mm would carry the glass off its tape ring: "
                f"it is then cut to dia {P.APERTURE_D - 2 * P.CLR:.1f} and hangs inside the aperture (its edge visible). The diameter is set by the centring chain (film on glass {M['retarder_place_tol']}, glass in "
                f"its recess {(P.RECESS_D - P.CG_D) / 2:.2f}, tape ring in the recess {(P.RECESS_D - P.CG_D) / 2:.2f}): a film that reached under the tape would lift the glass off its seal. The crystal and its "
                f"recess are round, so the flat is what carries the film axis to the tub (edge mark on the crystal set to the nose groove, +-{M['retarder_clock_tol_deg']:.0f} deg). Check 2 carries the rows"),
]

OPEN = [d for d in DEVIATIONS if not d["status"].startswith("closed")]
CLOSED = [d for d in DEVIATIONS if d["status"].startswith("closed")]
