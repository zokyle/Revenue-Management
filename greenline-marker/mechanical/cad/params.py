"""GreenLine GL-1 mechanical parameters (revision C).

Loads design/master_params.yaml (the single source of truth for shared numbers, rev C) and
derives every dependent dimension exactly once.  Mechanical-only choices (not shared with the
PCB layout) live in MECH below.  Nothing in parts.py may contain a bare design number: it must
come from Y (YAML), MECH (mechanical-only) or a derived attribute of this module.

Frame: origin at puck centre on the base plane, +x right, +y forward (visor), +z up, mm.
The cradle is modelled in the same frame with the marker seated (marker base plane at z = 0).
"""
from __future__ import annotations
import json, math, pathlib
import yaml

HERE = pathlib.Path(__file__).resolve().parent
MECH_DIR = HERE.parent
DESIGN_DIR = MECH_DIR.parent / "design"
YAML_PATH = DESIGN_DIR / "master_params.yaml"
EXPORT_DIR = MECH_DIR / "export"

Y = yaml.safe_load(open(YAML_PATH))
REV = Y["rev"]

# ----------------------------------------------------------------------------------------------
# Mechanical-only parameters (our choices; not shared with the PCB layout)
# ----------------------------------------------------------------------------------------------
MECH = dict(
    top_fillet=0.6, bottom_chamfer=0.3,
    rim_relief=0.25,                 # the side wall ends this far above the base plane: the base plate and the ball feet are the
                                     # lowest surfaces whatever the print tolerance of the post / PCB / sheet / plate stack (D23)
    # roof / LCD pocket
    recess_wall=0.8,                 # wall of the cover-glass recess below roof level
    lcd_rib_t=0.8, lcd_rib_z0=4.75,  # glass locating ribs reach down to this z
    lcd_side_ribs_y=[(-11.0, -7.0), (4.0, 8.0)],
    lcd_rear_ribs_x=(8.0, 11.0),
    cover_tape_id=23.0, lcd_psa_window_dia=23.0,
    lcd_psa_vent_w=0.8,              # vent channel in the LCD adhesive frame: the cell under the cover glass breathes into the cavity
    post_names=["A", "B", "C", "E"],  # YAML tub_keepouts.post_feet come in -x / +x pairs in this order
    locating_posts="E",               # the pair that carries the PCB locating spigots
    spigot_tip_chamfer=0.15,          # lead-in on the spigot tip (captures +-0.2 mm of lateral error when the PCB is joined)
    # camera hood (prism bay + light baffle)
    hood_wall=0.8, hood_skirt_z0=3.0, hood_fill_margin=0.05,
    hood_leadin=0.3,                 # 45 deg lead-in chamfer on the inner bottom edges of the skirts and of the front pad
    hood_rear_chamfer_margin=0.015,  # extra on the chamfer that keeps the hood rear wall one fit clearance off the prism hypotenuse
    hood_seal_w=0.25, hood_seal_inset=0.05,   # black form-in-place gasket bead in the slit above each cube (as compressed)
    hood_seal_free_h=0.6,            # height of the bead as dispensed and cured, before the cube compresses it
    window_bond=0.05,                # adhesive line behind the visor window
    # vent
    vent_pad=5.6, vent_pad_h=0.3, vent_od=5.0, vent_t=0.26, vent_area_dia=2.0,
    vent_groove_w=0.6, vent_groove_d=0.3, vent_cross_half=2.5,   # drain grooves on the top face through the vent hole
    # nose index groove
    nose_w=1.0, nose_depth=0.3,
    # base plate / PCB underside
    pad_dia=1.8, pad_t=0.035,
    led_body=(1.0, 0.5), led_pair_offset=0.45,
    epoxy_dome_max=0.08,             # stage 1 potting may dome this far over the plate; stage 2 fills the sheet hole to the PCB
    # reference solids
    flex_w=6.0, flex_t=0.15, flex_z_top_run=4.775,
    fpc_entry_h=1.0,                 # height of the J1 mouth above the PCB (PROVISIONAL: FH12 drawing)
    flex_straight=0.35, foam_dx=26.6,
    # optics (for the checks)
    pupil_below_cube_top=0.4, pupil_dia=0.38, n_prism=1.517,
    fov_h_half_deg=26.0, fov_up_deg=17.6,
    fov_down_deg=8.0,                # rev C: the lower field is needed only to about -8 deg (flagstick base near the horizon)
    fov_down_sensor_deg=15.0,        # what the sensor could use; reported, not required
    # ------------------------------------------------------------------ assembly paths proven in check 14
    lcd_tilt_deg=6.0, lcd_bias=0.55,                 # LCD tilt-in: rear edge first, glass shifted this far toward the visor
    join_offset=0.1,                                 # lateral guidance the join fixture must give until the spigots engage
    join_drops=[6.0, 4.5, 3.6, 3.0, 2.4, 1.8, 1.5, 1.2, 0.9, 0.62],
    hinge_y=-30.0, hinge_z=0.0,                      # axis of the join fixture hinge (parallel to x, behind the tub at the base plane)
    hinge_open_deg=[0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 12.0, 20.0, 35.0, 60.0],
    # ------------------------------------------------------------------ cradle (rev C: charging / data dock only)
    cradle_nest_wall_h=3.0,          # body top above the marker base plane
    cradle_y_rear=-36.0,             # rear face of the body (the 60 mm body is not centred on the marker: latch and USB need the room)
    cradle_corner_r=4.0,
    # Mill-Max 0914 long-stroke pin (PROVISIONAL until the drawing is read; docs/research/bom-verification-opto.md)
    pin_free_len=8.3, pin_plunger_dia=1.07, pin_body_dia=1.83, pin_tail_dia=0.76,
    pin_max_working_h=6.96, pin_mid_stroke=1.14, pin_full_stroke=2.29,
    pin_body_margin=0.2,             # barrel top this far below the fully compressed plunger tip
    pin_tail_below_pcb=0.7,
    cradle_pcb_rear_inset=1.8, cradle_pcb_screw_x=12.5, cradle_pcb_screw_inset=(2.7, 2.3),   # from the rear / front PCB edge
    cradle_screw_pilot_dia=1.7, cradle_screw_pilot_depth=0.5,   # spot marks only: drill dia 1.6 x 3 after printing
    usb=(8.94, 7.35, 3.26), usb_mouth_recess=0.5,
    scallop_deg=(-42.0, 0.0), scallop_inset=2.0,   # finger scallops: sectors of the nest wall removed (angles from +x on the +x side, mirrored)
    lighten_x=(17.0, 26.5), lighten_y=(-22.0, 10.0), lighten_front=(13.0, -9.5, 20.0), lighten_ceiling_z=-4.1,
    foot_pocket_dia=8.4, foot_pocket_depth=1.0, foot_xy=(23.5, 23.5), foot_h=3.0, foot_dia=8.0,
    core_dia=5.0, core_roof=3.5,     # blind core under each foot pocket (the four corners would otherwise be 13 mm solid)
    # drained nest floor: the marker stands on a front strip and two pads; the rest of the floor is a basin that falls to the scallops
    basin_depth=0.65, basin_fall_deg=2.0, strip_y0=12.8, ball_pad_dia=4.0, slot_rim_t=1.2, dam_t=1.7,
    well_drain_x=(5.7, 8.1), well_drain_skin=0.85, well_drain_h=2.4,   # tunnel from the latch well to the rear face
    # hold-down 1: fixed lip over the top front edge of the marker, between the camera windows
    lip_half_w=6.0, lip_overlap=1.2, lip_t=1.6, lip_pocket=1.0,
    # hold-down 2: sprung cantilever latch at the rear.  Rectangular beam, front face vertical, thinnest at a neck below the hook
    # (the back face tapers in from the root and flares out again into the hook), full-width hook with a STRAIGHT nose and a
    # retaining face raked back (nose lowest), thumb tab, stop ribs for the beam and a stop under the tab
    latch_w=24.0, latch_root_z=-3.8, latch_overhang=1.95,
    latch_h_root=1.05, latch_h_neck=0.85, latch_h_tip=1.30, latch_flare=2.5,   # thickness: root -> neck (latch_flare below the nose level) -> nose level
    hook_rake_deg=14.0, hook_nose_flat=0.4, hook_lead_deg=30.0,
    latch_root_fillet=1.0, hook_heel_fillet=0.5, tab_root_fillet=0.6, latch_neck_blend=8.0,
    latch_side_gap=1.2, latch_front_gap=2.2, latch_back_gap=2.7,
    latch_stop_travel=1.90,          # hook travel at which the beam back meets the stop ribs (hook pushed or pulled back)
    tab_stop_travel=2.00,            # hook travel at which the pressed thumb tab lands on its stop ("full deflection")
    guard_t=2.0, guard_top_z=5.5, stop_rib_w=1.0, stop_rib_x=9.5,
    tab_w=14.0, tab_len=7.9, tab_t=1.6, tab_press_inset=1.5,
    tab_stop_w=10.0, tab_stop_t=2.0, tab_stop_behind=0.4,
    # material data and assumptions for the hold-down calculation
    pa12_E_MPa=1700.0,               # HP 3D HR PA 12 (MJF) tensile modulus, data-sheet value XY (1800 in Z); dry, 23 C
    pa12_E_low_MPa=1200.0,           # conditioned / warm PA12 (assumed) for the sensitivity rows
    pa12_poisson=0.40,
    pa12_yield_MPa=48.0, latch_strain_limit=0.025, friction_mu=0.3, friction_mu_range=(0.2, 0.4),
    retention_factor_required=3.0,
    overlap_tolerances=(0.2, 0.3),   # loss of hook overlap (print tolerance front wall -> hook) for the off-nominal retention rows
    thumb_force_abuse_N=40.0,        # thumb force on the tab for the over-press load case
    insertion_tilts_deg=[17.0, 15.0, 14.0, 13.0, 12.0, 11.0, 10.0, 9.0, 8.0, 7.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.5, 1.0, 0.5, 0.0],
    insertion_gap=0.05,              # clearance kept to floor, front wall and lip in the posed insertion path
    release_lifts=[0.0, 0.2, 0.4, 0.6, 0.85, 1.2, 2.0, 4.0, 7.0],   # straight lifts of the marker rear used to find the release travel
)

# ----------------------------------------------------------------------------------------------
# Shared numbers from the YAML, under short names
# ----------------------------------------------------------------------------------------------
_e = Y["envelope"]
R_OUT, T, WALL = _e["outer_radius"], _e["thickness"], _e["wall"]
MIN_WALL, CLR = _e["min_printed_wall"], _e["fit_clearance"]
Y_VISOR, VISOR_WALL = _e["front_flat_y_outer"], _e["front_flat_wall"]
R_IN = R_OUT - WALL
Y_VISOR_IN = Y_VISOR - VISOR_WALL

_b = Y["base_plate"]
BASE_T, BASE_R, BASE_FLAT = _b["thickness"], _b["radius"], _b["flat_y"]
PSA_T = _b["psa"]["thickness"]                        # die-cut adhesive sheet between base plate and PCB
PSA_Z0, PSA_Z1 = BASE_T, BASE_T + PSA_T               # 0.87 .. 1.00
LAND_RI, LAND_FLAT_IN = _b["seal_land"]["r_inner"], _b["seal_land"]["flat_y_inner"]
GRAIN_X, GRAIN_Y, GRAIN_D = _b["grain_cavity"]["x"], _b["grain_cavity"]["y"], _b["grain_cavity"]["dia"]
PAD_HOLE_D, PAD_Y, PAD_XS = _b["pad_holes"]["dia"], _b["pad_holes"]["y"], list(_b["pad_holes"]["xs"])
PAD_SLOT_L = _b["pad_holes"]["slot_length"]
BALL_D, BALL_PROT = _b["feet"]["ball_dia"], _b["feet"]["protrusion"]
BALL_HOLE_D, PSA_FOOT_HOLE_D = _b["feet"]["hole_dia"], _b["feet"]["psa_hole_dia"]
BALL_XY = [tuple(p) for p in _b["feet"]["positions"]]
BALL_Z = BALL_D / 2 - BALL_PROT                       # ball centre height above the base plane (0.40)
BALL_TOP_Z = BALL_Z + BALL_D / 2                      # 0.90
BAFFLE_RI, BAFFLE_RO = _b["baffle"]["inner_dia"] / 2, _b["baffle"]["outer_dia"] / 2
BAFFLE_WALL, SPOKE_W, SPOKE_ANGLES = _b["baffle"]["wall"], _b["baffle"]["spoke_width"], list(_b["baffle"]["spokes_deg"])

_p = Y["pcb"]
PCB_T, PCB_Z0, PCB_R, PCB_FLAT = _p["thickness"], _p["z_bottom"], _p["radius"], _p["flat_y"]
PCB_Z1 = PCB_Z0 + PCB_T
PCB_EDGE_CLR = _p["component_edge_clearance"]
PCB_FREE_H = _p["max_top_height_under_lcd"]           # 2.55: component height the layout may use (z <= 4.35)
_lh = _p["locating_holes"]
LOC_ROUND = (_lh["round"]["x"], _lh["round"]["y"], _lh["round"]["dia"])
LOC_SLOT = (_lh["slot"]["x"], _lh["slot"]["y"], _lh["slot"]["dia"], _lh["slot"]["length_x"])
SPIGOT_D, SPIGOT_H = _lh["spigot_dia"], _lh["spigot_height"]
SPIGOT_Z0 = PCB_Z1 - SPIGOT_H                         # 1.20: spigot tip (the spigot hangs from the post foot into the PCB hole)
SPIGOT_FIT = (LOC_ROUND[2] - SPIGOT_D) / 2            # 0.075 radial: a locating fit, not a drop-in fit

LEDGE_RI, LEDGE_Z0, LEDGE_Z1 = Y["tub_ledge"]["r_inner"], Y["tub_ledge"]["z0"], Y["tub_ledge"]["z1"]
BEAD_T = LEDGE_Z0 - BASE_T                            # dispensed seal bead thickness (0.33)

_l = Y["lcd"]
LCD = dict(_l["glass"])                               # x, y, dx, dy, z0, z1
LCD_X0, LCD_X1 = LCD["x"] - LCD["dx"] / 2, LCD["x"] + LCD["dx"] / 2
LCD_Y0, LCD_Y1 = LCD["y"] - LCD["dy"] / 2, LCD["y"] + LCD["dy"] / 2
LCD_Z0, LCD_Z1 = LCD["z0"], LCD["z1"]
LCD_PSA_T, APERTURE_D = _l["psa_thickness"], _l["aperture_dia"]
BOND_Z = LCD_Z1 + LCD_PSA_T                           # underside of the roof ledge = LCD bonding plane (5.55)

_c = Y["cover_glass"]
CG_D, CG_T, RECESS_D, RECESS_DEPTH = _c["dia"], _c["thickness"], _c["recess_dia"], _c["recess_depth"]
CG_TAPE_T = 0.2                                       # VHB 5907 (YAML cover_glass.bond)
RECESS_FLOOR_Z = T - RECESS_DEPTH                     # 6.35
ROOF_LEDGE_T = RECESS_FLOOR_Z - BOND_Z                # 0.80
CG_Z0 = RECESS_FLOOR_Z + CG_TAPE_T
CG_Z1 = CG_Z0 + CG_T
CG_BELOW_FLUSH = T - CG_Z1                            # 0.05

ROOF_Z, ROOF_T = Y["roof"]["underside_z"], Y["roof"]["thickness"]

_bt = Y["battery"]
BAT = dict(_bt["body"]); BAT_SWELL, FOAM_T = _bt["swell_allowance"], _bt["foam_above"]
FOAM_Z1 = LCD_Z0; FOAM_Z0 = FOAM_Z1 - FOAM_T

_cam = Y["cameras"]
CAM_DX, CAM_DY, CAM_H = _cam["body_dx"], _cam["body_dy"], _cam["height"]
CAM_XY = dict(L=(_cam["left"]["x"], _cam["left"]["y"]), R=(_cam["right"]["x"], _cam["right"]["y"]))
CAM_Z0, CAM_Z1 = PCB_Z1, PCB_Z1 + CAM_H
_pr = Y["prisms"]
PRISM_LEG, PRISM_BOND, PRISM_EXIT_Y = _pr["leg"], _pr["bond_line"], _pr["exit_face_y"]
PRISM_Z0 = CAM_Z1 + PRISM_BOND
PRISM_Z1 = PRISM_Z0 + PRISM_LEG
PRISM_Y0 = PRISM_EXIT_Y - PRISM_LEG
AXIS_Z = PRISM_Z0 + PRISM_LEG / 2                     # 5.61
PRISM_ROOF_CLR = ROOF_Z - PRISM_Z1                    # 0.19

_w = Y["visor_window"]
WIN_W, WIN_H, WIN_T = _w["w"], _w["h"], _w["t"]
WIN_RECESS_W, WIN_RECESS_DEPTH, WIN_Z0, WIN_Z1 = _w["recess_w"], _w["recess_depth"], _w["z0"], _w["z1"]
OPEN_HALF_W, OPEN_Z0, OPEN_Z1 = _w["opening"]["half_w"], _w["opening"]["z0"], _w["opening"]["z1"]
WIN_RECESS_FLOOR_Y = Y_VISOR - WIN_RECESS_DEPTH       # 17.85
VENT_HOLE_D = Y["vent"]["hole_dia"]
VENT_XY = (Y["vent"]["x"], Y["vent"]["y"])

_ko = Y["tub_keepouts"]
KO_POST_SIZE = _ko["post_feet"]["size"]
KO_POST_CENTRES = [tuple(c) for c in _ko["post_feet"]["centres"]]
KO_HOOD_HW, KO_HOOD_Y0, KO_HOOD_Y1 = _ko["camera_hoods"]["half_w"], _ko["camera_hoods"]["y0"], _ko["camera_hoods"]["y1"]
KO_HOOD_MAX_H = _ko["camera_hoods"]["max_part_height"]
KO_FREE_Z = PCB_Z1 + PCB_FREE_H                       # 4.35: below this the tub may exist over the PCB only inside the keep-outs

TOP_PARTS = Y["top_side_parts"]
_bs = Y["bottom_side_parts"]
LED_RING = dict(_bs["grain_led_ring"]); PD = dict(_bs["photodiode"])

_cr = Y["cradle"]
CRADLE_SIZE = (_cr["body"]["dx"], _cr["body"]["dy"], _cr["body"]["dz"])
CRADLE_PAD_Z = _cr["pad_plane_z"]                     # 1.00
PIN_ROW_Y = _cr["pin_row_y"]
PIN_WORK_H, PIN_FORCE_N = _cr["pins"]["working_height"], _cr["pins"]["force_working_N"]
PIN_POSITIONS = _cr["pins"]["positions"]
PINS_CONSUMER = list(_cr["pins"]["populated_consumer"])          # the four at x = -7.62 .. 0.0
CPCB_SIZE = (_cr["pcb"]["dx"], _cr["pcb"]["dy"], _cr["pcb"]["thickness"])

# ----------------------------------------------------------------------------------------------
# Derived mechanical dimensions
# ----------------------------------------------------------------------------------------------
M = MECH
RIM_Z = M["rim_relief"]                               # 0.25: bottom of the tub side wall (the base plate bottom is z = 0)
# LCD pocket (bonding plane) and the thick roof ring that carries the cover-glass recess
LCD_POCKET_X = LCD_X1 + CLR                           # 13.55
LCD_POCKET_Y1 = LCD_Y1 + CLR                          # 13.75
LCD_POCKET_Y0 = LCD_Y0 - CLR                          # -17.05
THICK_RING_R = RECESS_D / 2 + M["recess_wall"]        # 15.05
LCD_VENT_ANGLE_DEG = math.degrees(math.atan2(LCD_Y0, LCD_X1))   # vent channel of the adhesive frame runs to the rear right corner

# camera hood: the bay is as wide as the clear opening (2.0 > cube half-width + clearance 1.985), so the opening runs
# straight from the bay to the window recess - no bevel (the light bundle is narrower inside than at the aperture)
HOOD_IN_HW = max(CAM_DX / 2 + CLR, OPEN_HALF_W)       # 2.0 half-width of the bay
HOOD_OUT_HW = HOOD_IN_HW + M["hood_wall"]             # 2.8 (keep-out contract: 2.85)
HOOD_Z_OVER_CUBE = CAM_Z1 + CLR                       # 4.81 underside of walls that pass over the cube
HOOD_REAR_Y0 = LCD_POCKET_Y1                          # 13.75 rear face of the rear wall
HOOD_REAR_Y1 = HOOD_REAR_Y0 + M["hood_wall"]          # 14.55 front face of the rear wall = bay rear
HOOD_PAD_Y = max(v[1] for v in CAM_XY.values()) + CAM_DY / 2 + CLR   # 17.325 pad face in front of the cube
THIN_STRIP_T = WIN_RECESS_FLOOR_Y - HOOD_PAD_Y        # 0.525 wall behind the recess below the opening (accepted deviation)
BAY_LEN_OPEN = WIN_RECESS_FLOOR_Y - HOOD_REAR_Y1      # 3.3 bay rear wall -> recess floor at opening height
BAY_LEN_BELOW = HOOD_PAD_Y - HOOD_REAR_Y1             # 2.775 bay rear wall -> pad face below the sill
HOOD_PAD_T = Y_VISOR_IN - HOOD_PAD_Y                  # 0.275 thickness of the pad on the visor wall
HOOD_PAD_LEADIN = min(M["hood_leadin"], HOOD_PAD_T)   # the pad lead-in cannot be deeper than the pad
CAM_X = max(abs(v[0]) for v in CAM_XY.values())       # 10.0
# corner fill between the hood and the side wall: starts where the PCB outline has left the hood keep-out zone, so that
# nothing outside the contract zone hangs over the PCB
HOOD_FILL_Y0 = math.sqrt(PCB_R ** 2 - (CAM_X + KO_HOOD_HW) ** 2) + M["hood_fill_margin"]     # 16.79

# the side wall below the visor ends on the radial plane through the outer D corner (full 1.0 mm wall end face)
HORN_X_OUT = math.sqrt(R_OUT ** 2 - Y_VISOR ** 2)     # 13.8 outer D corner
HORN_ANGLE_DEG = math.degrees(math.atan2(Y_VISOR, HORN_X_OUT))
HORN_X_IN = R_IN * HORN_X_OUT / R_OUT                 # 13.2 where that radial plane meets the inner wall face
HORN_Y_IN = R_IN * Y_VISOR / R_OUT                    # 17.6
# 45 deg chamfer on the bottom front edge of the hood rear wall: keeps >= CLR normal to the prism hypotenuse
_hyp_gap = ((HOOD_Z_OVER_CUBE - PRISM_Z0) - (HOOD_REAR_Y1 - PRISM_Y0)) / math.sqrt(2)    # 0.177 without the chamfer
HOOD_REAR_CHAMFER = max(0.0, (CLR - _hyp_gap) * math.sqrt(2)) + M["hood_rear_chamfer_margin"]
PRISM_HOOD_CLR = _hyp_gap + HOOD_REAR_CHAMFER / math.sqrt(2)
HOOD_SLIT = (HOOD_Z_OVER_CUBE - CAM_Z1, HOOD_Z_OVER_CUBE + HOOD_REAR_CHAMFER - CAM_Z1)   # 0.25 .. 0.37 slit above the cube at the rear
# black gasket bead in that slit: on the flat underside of the rear wall, over the rear edge of the cube top
CAM_REAR_Y = min(v[1] for v in CAM_XY.values()) - CAM_DY / 2          # 14.125 rear face of the cube
HOOD_SEAL_Y0 = CAM_REAR_Y + 0.025
HOOD_SEAL_Y1 = HOOD_SEAL_Y0 + M["hood_seal_w"]        # 14.40 (the rear-wall chamfer starts at 14.43, the prism edge is at 14.60)
HOOD_SEAL_HW = HOOD_IN_HW - M["hood_seal_inset"]
HOOD_SEAL_VOL = 2 * HOOD_SEAL_HW * M["hood_seal_w"] * M["hood_seal_free_h"]   # mm3 of gasket material per hood, as dispensed

# base plate
PD_HALF_DIAG = math.hypot(PD["dx"] / 2, PD["dy"] / 2)
GRAIN_R = GRAIN_D / 2
PAD_WEB = (PAD_XS[1] - PAD_XS[0]) - PAD_HOLE_D        # 0.34: why the seven holes are one slot
PAD_Z0 = PCB_Z0 - M["pad_t"]                          # modelled copper face of a contact pad (0.965)
BASE_CORNER_X = math.sqrt(BASE_R ** 2 - BASE_FLAT ** 2)   # 11.83 front corner of the base plate

# vent
VENT_PAD_Z = ROOF_Z - M["vent_pad_h"]                 # 6.5
VENT_Z0 = VENT_PAD_Z - M["vent_t"]

# LCD flex tail (representative): one U-fold from the glass rear edge down into the J1 mouth
FLEX_ZT = M["flex_z_top_run"]
FLEX_ZB = PCB_Z1 + M["fpc_entry_h"]                   # 2.8
FLEX_BEND_R = (FLEX_ZT - FLEX_ZB) / 2                 # 0.99 centre-line radius of the fold

# optics (paraxial unfolding, for reference; the ray trace is in checks)
PUPIL_Z = CAM_Z1 - M["pupil_below_cube_top"]
VIRTUAL_PUPIL_BEHIND_EXIT = (CAM_Z1 - PUPIL_Z) + PRISM_BOND + PRISM_LEG / M["n_prism"]
VIRTUAL_PUPIL_Y = PRISM_EXIT_Y - VIRTUAL_PUPIL_BEHIND_EXIT

# ---------------------------------------------------------------------------------------------- cradle
NEST_R = R_OUT + CLR                                  # 23.25
NEST_FLAT = Y_VISOR + CLR                             # 18.65 (the D flat is the orientation key)
NEST_FLOOR_Z = -BALL_PROT                             # -0.10: level of the front strip and of the two pads the ball feet rest on
CRADLE_TOP_Z = M["cradle_nest_wall_h"]                # 3.0
CRADLE_BOT_Z = CRADLE_TOP_Z - CRADLE_SIZE[2]          # -11.0
CRADLE_X = CRADLE_SIZE[0] / 2
CRADLE_Y0 = M["cradle_y_rear"]                        # -36.0
CRADLE_Y1 = CRADLE_Y0 + CRADLE_SIZE[1]                # 24.0
CRADLE_CY = 0.5 * (CRADLE_Y0 + CRADLE_Y1)
# The pins stand at their working height on the COPPER FACE of the pads, which is modelled pad_t below the YAML pad plane
PIN_TIP_GAP = CRADLE_PAD_Z - PAD_Z0                   # 0.035: copper face below the YAML pad plane (board underside)
CPCB_Z1 = PAD_Z0 - PIN_WORK_H                         # -4.855 top face of the cradle PCB
CPCB_Z0 = CPCB_Z1 - CPCB_SIZE[2]
CPCB_HX = CPCB_SIZE[0] / 2                            # 15.0
CPCB_Y0 = CRADLE_Y0 + M["cradle_pcb_rear_inset"]      # -34.2
CPCB_Y1 = CPCB_Y0 + CPCB_SIZE[1]                      # -12.2
CPCB_SCREWS = [(M["cradle_pcb_screw_x"], CPCB_Y0 + M["cradle_pcb_screw_inset"][0]),
               (M["cradle_pcb_screw_x"], CPCB_Y1 - M["cradle_pcb_screw_inset"][1])]
PIN_TIP_FREE_Z = CPCB_Z1 + M["pin_max_working_h"]     # 2.105: free plunger tip above the marker base plane
PIN_BODY_Z1 = CPCB_Z1 + M["pin_max_working_h"] - M["pin_full_stroke"] - M["pin_body_margin"]   # -0.385 barrel top (PROVISIONAL)
PIN_COMPRESSION = M["pin_max_working_h"] - PIN_WORK_H     # 1.14 of the stroke used with the marker on its feet
PIN_FLOAT_H = PIN_WORK_H + CLR                        # 6.07 pin height when the marker floats up against lip and hook
CRADLE_PIN_SLOT_W = M["pin_body_dia"] + 2 * CLR       # 2.33: drop-in clearance round the (PROVISIONAL) pin barrel
USB_Y0 = CRADLE_Y0 + M["usb_mouth_recess"]
USB_Y1 = USB_Y0 + M["usb"][1]
USB_Z1 = CPCB_Z1 + M["usb"][2]
# drained nest floor
BASIN_RIDGE_Z = NEST_FLOOR_Z - M["basin_depth"]       # -0.75 basin floor on the centre line
BASIN_TAN = math.tan(math.radians(M["basin_fall_deg"]))
STRIP_Y0 = M["strip_y0"]                              # the nest floor in front of this line stays at NEST_FLOOR_Z (landing strip)
BASIN_Z_AT_WALL = BASIN_RIDGE_Z - NEST_R * BASIN_TAN  # -1.56 basin floor where it leaves through the scallops
BASIN_Z_AT_EDGE = BASIN_RIDGE_Z - CRADLE_X * BASIN_TAN
WELL_DRAIN_Z0 = CPCB_Z1 + M["well_drain_skin"]        # -4.005 floor of the drain tunnel (below the well floor)
WELL_DRAIN_Z1 = WELL_DRAIN_Z0 + M["well_drain_h"]
CORE_Z1 = CRADLE_TOP_Z - M["core_roof"]               # -0.5 top of the blind cores under the feet
# fixed lip
LIP_Z0 = T + CLR                                      # 7.85 underside
LIP_Z1 = LIP_Z0 + M["lip_t"]                          # 9.45
LIP_Y0 = Y_VISOR - M["lip_overlap"]                   # 17.2 lip tip
LIP_POCKET_Y = NEST_FLAT + M["lip_pocket"]            # 19.65 wall of the nose pocket under the lip
# rear latch: cantilever with the front face vertical at the nest radius and a necked back face, straight nose
LATCH_H0, LATCH_HN, LATCH_H1 = M["latch_h_root"], M["latch_h_neck"], M["latch_h_tip"]
LATCH_Y_FACE = -NEST_R                                # -23.25 front face of the beam (0.25 from the marker at x = 0)
LATCH_Y_BACK0 = LATCH_Y_FACE - LATCH_H0               # -24.30 back face at the root
LATCH_Y_BACKN = LATCH_Y_FACE - LATCH_HN               # -24.10 back face at the neck
LATCH_Y_BACK1 = LATCH_Y_FACE - LATCH_H1               # -24.55 back face at the nose level (and above it)
LATCH_Y_NA = LATCH_Y_FACE - LATCH_H1 / 2              # neutral axis at the nose level: reference point of the rigid hook
HOOK_Z0 = T + CLR                                     # 7.85 nose = lowest point of the retaining face
HOOK_Y = LATCH_Y_FACE + M["latch_overhang"]           # -21.30 straight nose
HOOK_RAKE_TAN = math.tan(math.radians(M["hook_rake_deg"]))
HOOK_HEEL_Z = HOOK_Z0 + M["latch_overhang"] * HOOK_RAKE_TAN   # 8.34 the retaining face rises to the heel (negative rake)
TUB_TOP_FLAT_R = R_OUT - M["top_fillet"]              # 22.4 where the flat top of the tub ends
HOOK_OVERLAP = TUB_TOP_FLAT_R + HOOK_Y                # 1.10 nose on the flat top, marker centred
HOOK_OVERLAP_FWD = HOOK_OVERLAP - CLR                 # 0.85 marker against the front nest wall: the governing position
LATCH_L = HOOK_Z0 - M["latch_root_z"]                 # 11.65 free length root -> nose level
LATCH_S1 = LATCH_L - M["latch_flare"]                 # 9.15 height of the neck above the root
LATCH_NECK_Z = M["latch_root_z"] + LATCH_S1           # 5.35


def _neck_blend():
    """Arc of radius latch_neck_blend that rounds the neck of the back face: (centre y, centre z, z_low, z_high)."""
    R = M["latch_neck_blend"]
    a = (LATCH_Y_BACK0 - LATCH_Y_BACKN, -LATCH_S1); b = (LATCH_Y_BACK1 - LATCH_Y_BACKN, LATCH_L - LATCH_S1)
    na, nb = math.hypot(*a), math.hypot(*b)
    u1, u2 = (a[0] / na, a[1] / na), (b[0] / nb, b[1] / nb)
    half = 0.5 * math.acos(max(-1.0, min(1.0, u1[0] * u2[0] + u1[1] * u2[1])))
    t = R / math.tan(half)
    bis = (u1[0] + u2[0], u1[1] + u2[1]); nn = math.hypot(*bis)
    return (LATCH_Y_BACKN + bis[0] / nn * R / math.sin(half), LATCH_NECK_Z + bis[1] / nn * R / math.sin(half),
            LATCH_NECK_Z + u1[1] * t, LATCH_NECK_Z + u2[1] * t)


NECK_BLEND = _neck_blend()


def latch_h(s):
    """Thickness of the latch beam at the height s above its root (scalar or numpy array): the back face runs straight
    from the root to the neck and from the neck to the nose level, with the neck rounded by the blend arc."""
    import numpy as np
    s = np.asarray(s, float)
    z = M["latch_root_z"] + s
    lin = np.where(s <= LATCH_S1, LATCH_H0 + (LATCH_HN - LATCH_H0) * s / LATCH_S1,
                   LATCH_HN + (LATCH_H1 - LATCH_HN) * np.clip((s - LATCH_S1) / (LATCH_L - LATCH_S1), 0.0, 1.0))
    cy, cz, z0, z1 = NECK_BLEND
    R = M["latch_neck_blend"]
    arc = LATCH_Y_FACE - (cy + np.sqrt(np.maximum(R * R - (z - cz) ** 2, 0.0)))
    return np.where((z > z0) & (z < z1), arc, lin)


HOOK_LEAD_Z0 = HOOK_Z0 + M["hook_nose_flat"]          # 8.25 start of the lead-in
LATCH_TOP_Z = HOOK_LEAD_Z0 + M["latch_overhang"] / math.tan(math.radians(M["hook_lead_deg"]))   # 11.63
TAB_Y0 = LATCH_Y_BACK1 - M["tab_len"]                 # -32.45 rear end of the thumb tab
TAB_Z0 = LATCH_TOP_Z - M["tab_t"]
WELL_HX = M["latch_w"] / 2 + M["latch_side_gap"]      # 13.2
WELL_Y1 = LATCH_Y_FACE + M["latch_front_gap"]         # -21.05
WELL_Y0 = LATCH_Y_BACK0 - M["latch_back_gap"]         # -27.0
NEST_WINDOW_Y1 = -math.sqrt(NEST_R ** 2 - WELL_HX ** 2) + 0.02   # the nest wall is open over the width of the latch well
REAR_WALL_ANGLE_DEG = math.degrees(math.asin(WELL_HX / NEST_R))   # the rear nest wall starts this far from the -y axis
MARKER_BACK_MAX = CLR / math.cos(math.radians(REAR_WALL_ANGLE_DEG))   # how far back the nest wall lets the marker go
RELEASE_TRAVEL = (R_OUT + HOOK_Y - CLR, R_OUT + HOOK_Y, R_OUT + HOOK_Y + MARKER_BACK_MAX)   # nose back to the marker edge: marker forward / centred / rearmost


def taper_coeffs(n=4000):
    """The latch beam (rectangular section, thickness latch_h(s), length L) as a cantilever: small deflections, numerical
    integration of curvature = M / (E I).  Returns quantities that do not depend on E or on the width b:
      th_F, th_M        tip slope per mm of tip travel (rad/mm) for a tip force / a tip moment
      eps_F, eps_M      largest outer-fibre strain per mm of tip travel (and eps_*_at = where, as s / L)
      cw_F, cw_M        tip travel = cw_F * P / (E b) for a tip force P;  = cw_M * M0 / (E b) for a tip moment M0
      s, shape_F, shape_M   deflection along the beam as a fraction of the tip travel
    A uniform beam would give th_F = 1.5 / L, th_M = 2 / L, eps_F = 1.5 h / L^2 (root), eps_M = h / L^2."""
    import numpy as np
    L = LATCH_L
    s = np.linspace(0.0, L, n + 1)
    h = latch_h(s)
    inv = 12.0 / h ** 3                                   # b / I
    cum = lambda f: np.concatenate([[0.0], np.cumsum(0.5 * (f[1:] + f[:-1]) * (s[1] - s[0]))])
    out = {}
    for tag, mom in (("F", L - s), ("M", np.ones_like(s))):
        k = mom * inv                                    # curvature * E b for a unit load
        sl = cum(k); w = cum(sl)
        eps = k * h / 2
        i = int(np.argmax(eps))
        out.update({f"th_{tag}": float(sl[-1] / w[-1]), f"cw_{tag}": float(w[-1]), f"eps_{tag}": float(eps[i] / w[-1]),
                    f"eps_{tag}_at": float(s[i] / L), f"eps_{tag}_root": float(eps[0] / w[-1]), f"shape_{tag}": w / w[-1]})
    out["s"] = s
    return out


_tc = taper_coeffs()
LATCH_BEAM = {k: v for k, v in _tc.items() if not hasattr(v, "shape")}   # scalars only (exported)
LATCH_PIVOT_F = 1.0 / LATCH_BEAM["th_F"]              # the hook moves like a rigid body turning about a point this far below
LATCH_PIVOT_M = 1.0 / LATCH_BEAM["th_M"]              # the nose level (tip force / pure moment): exact tip travel and tip slope


def latch_shape(z, mode="F"):
    """Backward deflection of the beam at height z as a fraction of the hook travel (tip-force or pure-moment bending)."""
    import numpy as np
    return float(np.interp(z - M["latch_root_z"], _tc["s"], _tc[f"shape_{mode}"]))


def latch_pose(y, z, d, mode="F"):
    """Where a point (y, z) of the rigid hook / tab is when the hook has travelled back by d (tip-force or moment bending)."""
    rho = LATCH_PIVOT_F if mode == "F" else LATCH_PIVOT_M
    th = math.asin(min(1.0, d / rho))
    dy, dz = y - LATCH_Y_NA, z - (HOOK_Z0 - rho)
    return LATCH_Y_NA + dy * math.cos(th) - dz * math.sin(th), HOOK_Z0 - rho + dy * math.sin(th) + dz * math.cos(th)


# over-travel stop for the hook (hook pushed or pulled back = tip force): the back face of the beam meets the top of the
# stop ribs.  The ribs end below the nose level, at the height where a pressed tab (pure moment) reaches them LATER than
# a pushed hook does, so that they never block the release
LATCH_Y_BACK_AT_STOP = LATCH_Y_FACE - float(latch_h(M["guard_top_z"] - M["latch_root_z"]))   # back face of the beam at the rib top
LATCH_STOP_GAP = M["latch_stop_travel"] * latch_shape(M["guard_top_z"], "F")     # beam back -> rib at the rib top
STOP_RIB_Y1 = LATCH_Y_BACK_AT_STOP - LATCH_STOP_GAP   # front face of the stop ribs
RIB_TRAVEL_M = LATCH_STOP_GAP / latch_shape(M["guard_top_z"], "M")   # hook travel at which a pressed tab would bring the beam to the ribs
# stop under the thumb tab (pure moment): the lower rear corner of the tab lands on it at tab_stop_travel
TAB_LAND_Y, TAB_STOP_Z = latch_pose(TAB_Y0, TAB_Z0, M["tab_stop_travel"], "M")
TAB_DROP_AT_STOP = TAB_Z0 - TAB_STOP_Z
TAB_STOP_Y0 = TAB_LAND_Y - M["tab_stop_behind"]       # rear face of the tab stop
TAB_STOP_Y1 = TAB_STOP_Y0 + M["tab_stop_t"]
TAB_PRESS_Y = TAB_Y0 + M["tab_press_inset"]           # where the thumb presses
TAB_LEVER = LATCH_Y_NA - TAB_PRESS_Y                  # lever of the thumb force about the beam axis


def post_rects():
    """All support-post footprints as (name, x0, x1, y0, y1), straight from the YAML keep-out contract."""
    out, h = [], KO_POST_SIZE / 2
    for i, (cx, cy) in enumerate(KO_POST_CENTRES):
        out.append((M["post_names"][i // 2] + ("+" if cx > 0 else "-"), cx - h, cx + h, cy - h, cy + h))
    return out


def resolved():
    """Every resolved number (YAML + mechanical-only + derived) for export/params_resolved.json."""
    derived = {k: v for k, v in globals().items()
               if k.isupper() and isinstance(v, (int, float, str, list, tuple, dict)) and k not in ("Y", "MECH", "M")}
    return dict(rev=REV, source=str(YAML_PATH), yaml=Y, mechanical_only=MECH, derived=derived,
                posts=[dict(name=n, x0=a, x1=b, y0=c, y1=d) for n, a, b, c, d in post_rects()])


def write_resolved(path=None):
    path = pathlib.Path(path or EXPORT_DIR / "params_resolved.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(resolved(), indent=1, default=str))
    return path


assert abs(PSA_Z1 - PCB_Z0) < 1e-9, "base plate + adhesive sheet must end at the PCB underside"
assert abs(PAD_SLOT_L - (PAD_XS[-1] - PAD_XS[0] + PAD_HOLE_D)) < 1e-9, "pad slot length does not match the pad row"
assert abs(PIN_ROW_Y - PAD_Y) < 1e-9 and PIN_POSITIONS == len(PAD_XS)

if __name__ == "__main__":
    print(write_resolved())
