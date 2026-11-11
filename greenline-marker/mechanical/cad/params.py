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
    # roof / LCD pocket
    recess_wall=0.8,                 # wall of the cover-glass recess below roof level
    lcd_rib_t=0.8, lcd_rib_z0=4.75,  # glass locating ribs reach down to this z
    lcd_side_ribs_y=[(-11.0, -7.0), (4.0, 8.0)],
    lcd_rear_ribs_x=(8.0, 11.0),
    cover_tape_id=23.0, lcd_psa_window_dia=23.0,
    post_names=["A", "B", "C", "E"],  # YAML tub_keepouts.post_feet come in -x / +x pairs in this order
    locating_posts="E",               # the pair that carries the PCB locating spigots
    # camera hood (prism bay + light baffle)
    hood_wall=0.8, hood_skirt_z0=3.0, hood_fill_margin=0.05,
    hood_rear_chamfer_margin=0.015,  # extra on the chamfer that keeps the hood rear wall one fit clearance off the prism hypotenuse
    window_bond=0.05,                # adhesive line behind the visor window
    # vent
    vent_pad=5.6, vent_pad_h=0.2, vent_od=5.0, vent_t=0.26, vent_area_dia=2.0,
    # nose index groove
    nose_w=1.0, nose_depth=0.3,
    # base plate
    key_w=1.2, key_x=9.25,           # tub lugs at x = +-key_x on the visor underside
    pad_dia=1.8, pad_t=0.035,
    led_body=(1.0, 0.5), led_pair_offset=0.45,
    epoxy_cap_dia=1.6, epoxy_cap_h=0.08,   # UV epoxy that pots each ball: fills the through hole and domes 0.08 over the plate
    # reference solids
    flex_w=6.0, flex_t=0.15, flex_z_top_run=4.775, flex_z_bottom_run=3.925,
    flex_straight=0.35, foam_dx=26.6,
    # optics (for the checks)
    pupil_below_cube_top=0.4, pupil_dia=0.38, n_prism=1.517,
    fov_h_half_deg=26.0, fov_up_deg=17.6,
    fov_down_deg=8.0,                # rev C: the lower field is needed only to about -8 deg (flagstick base near the horizon)
    fov_down_sensor_deg=15.0,        # what the sensor could use; reported, not required
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
    # hold-down 1: fixed lip over the top front edge of the marker, between the camera windows
    lip_half_w=6.0, lip_overlap=1.2, lip_t=1.6, lip_pocket=1.0,
    # hold-down 2: sprung cantilever latch at the rear (uniform rectangular beam, hook with a 90 deg retaining face)
    latch_w=14.0, latch_h=1.15, latch_root_z=-3.8, latch_overhang=1.75, hook_nose_flat=0.4, hook_lead_deg=30.0,
    latch_root_fillet=0.5,
    latch_side_gap=1.2, latch_front_gap=2.2, latch_back_gap=2.6,
    latch_stop_deflection=1.9,       # hook travel at which the beam meets the over-travel stop ribs ("full deflection")
    guard_t=2.0, guard_top_z=6.5, stop_rib_w=1.0, stop_rib_x=4.0,
    tab_len=8.6, tab_t=1.6, tab_press_inset=1.5,
    # material data and assumptions for the hold-down calculation
    pa12_E_MPa=1700.0,               # HP 3D HR PA 12 (MJF) tensile modulus, data-sheet value XY (1800 in Z); dry, 23 C
    pa12_yield_MPa=48.0, latch_strain_limit=0.025, friction_mu=0.3, friction_mu_range=(0.2, 0.4),
    retention_factor_required=3.0,
    insertion_tilts_deg=[17.0, 15.0, 14.0, 13.0, 12.0, 11.0, 10.0, 9.0, 8.0, 7.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.5, 1.0, 0.5, 0.0],
    insertion_gap=0.05,              # clearance kept to floor, front wall and lip in the posed insertion path
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
# LCD pocket (bonding plane) and the thick roof ring that carries the cover-glass recess
LCD_POCKET_X = LCD_X1 + CLR                           # 13.55
LCD_POCKET_Y1 = LCD_Y1 + CLR                          # 13.75
LCD_POCKET_Y0 = LCD_Y0 - CLR                          # -17.05
THICK_RING_R = RECESS_D / 2 + M["recess_wall"]        # 15.05

# camera hood: the bay is as wide as the clear opening (2.0 > cube half-width + clearance 1.985), so the opening runs
# straight through the visor wall into the bay - no bevel (the light bundle is narrower inside than at the aperture)
HOOD_IN_HW = max(CAM_DX / 2 + CLR, OPEN_HALF_W)       # 2.0 half-width of the bay
HOOD_OUT_HW = HOOD_IN_HW + M["hood_wall"]             # 2.8 (keep-out contract: 2.85)
HOOD_Z_OVER_CUBE = CAM_Z1 + CLR                       # 4.81 underside of walls that pass over the cube
HOOD_REAR_Y0 = LCD_POCKET_Y1                          # 13.75 rear face of the rear wall
HOOD_REAR_Y1 = HOOD_REAR_Y0 + M["hood_wall"]          # 14.55 front face of the rear wall = bay rear
HOOD_FRONT_IN_Y = WIN_RECESS_FLOOR_Y - MIN_WALL       # 17.05 inner face of the thickened visor wall
HOOD_PAD_Y = max(v[1] for v in CAM_XY.values()) + CAM_DY / 2 + CLR   # 17.325 pad face in front of the cube
THIN_STRIP_T = WIN_RECESS_FLOOR_Y - HOOD_PAD_Y        # 0.525 wall behind the recess below the opening (accepted deviation)
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
HOOD_SLIT = (HOOD_Z_OVER_CUBE - CAM_Z1, HOOD_Z_OVER_CUBE + HOOD_REAR_CHAMFER - CAM_Z1)   # 0.25 .. 0.36 slit above the cube at the rear

# base plate
PD_HALF_DIAG = math.hypot(PD["dx"] / 2, PD["dy"] / 2)
GRAIN_R = GRAIN_D / 2
KEY_NOTCH_HW = M["key_w"] / 2 + CLR                   # 0.85
KEY_NOTCH_Y0 = Y_VISOR_IN - CLR                       # 17.35
PAD_WEB = (PAD_XS[1] - PAD_XS[0]) - PAD_HOLE_D        # 0.34: why the seven holes are one slot
PAD_Z0 = PCB_Z0 - M["pad_t"]                          # modelled copper face of a contact pad (0.965)
EPOXY_Z1 = BASE_T + M["epoxy_cap_h"]                  # 0.95: top of the potting dome (0.05 under the PCB)

# vent
VENT_PAD_Z = ROOF_Z - M["vent_pad_h"]                 # 6.6
VENT_Z0 = VENT_PAD_Z - M["vent_t"]

# optics (paraxial unfolding, for reference; the ray trace is in checks)
PUPIL_Z = CAM_Z1 - M["pupil_below_cube_top"]
VIRTUAL_PUPIL_BEHIND_EXIT = (CAM_Z1 - PUPIL_Z) + PRISM_BOND + PRISM_LEG / M["n_prism"]
VIRTUAL_PUPIL_Y = PRISM_EXIT_Y - VIRTUAL_PUPIL_BEHIND_EXIT

# ---------------------------------------------------------------------------------------------- cradle
NEST_R = R_OUT + CLR                                  # 23.25
NEST_FLAT = Y_VISOR + CLR                             # 18.65 (the D flat is the orientation key)
NEST_FLOOR_Z = -BALL_PROT                             # -0.10: the three ball feet rest on the printed nest floor
CRADLE_TOP_Z = M["cradle_nest_wall_h"]                # 3.0
CRADLE_BOT_Z = CRADLE_TOP_Z - CRADLE_SIZE[2]          # -11.0
CRADLE_X = CRADLE_SIZE[0] / 2
CRADLE_Y0 = M["cradle_y_rear"]                        # -36.0
CRADLE_Y1 = CRADLE_Y0 + CRADLE_SIZE[1]                # 24.0
CRADLE_CY = 0.5 * (CRADLE_Y0 + CRADLE_Y1)
CPCB_Z1 = CRADLE_PAD_Z - PIN_WORK_H                   # -4.82 top face of the cradle PCB (pins at working height on the pad plane)
CPCB_Z0 = CPCB_Z1 - CPCB_SIZE[2]
CPCB_HX = CPCB_SIZE[0] / 2                            # 15.0
CPCB_Y0 = CRADLE_Y0 + M["cradle_pcb_rear_inset"]      # -34.2
CPCB_Y1 = CPCB_Y0 + CPCB_SIZE[1]                      # -12.2
CPCB_SCREWS = [(M["cradle_pcb_screw_x"], CPCB_Y0 + M["cradle_pcb_screw_inset"][0]),
               (M["cradle_pcb_screw_x"], CPCB_Y1 - M["cradle_pcb_screw_inset"][1])]
PIN_TIP_FREE_Z = CPCB_Z1 + M["pin_max_working_h"]     # 2.14: free plunger tip above the marker base plane
PIN_BODY_Z1 = CPCB_Z1 + M["pin_max_working_h"] - M["pin_full_stroke"] - M["pin_body_margin"]   # -0.35 barrel top (PROVISIONAL)
PIN_TIP_GAP = CRADLE_PAD_Z - PAD_Z0                   # 0.035: the modelled copper face is this far below the YAML pad plane
CRADLE_PIN_SLOT_W = M["pin_body_dia"] + 2 * CLR       # 2.33: drop-in clearance round the (PROVISIONAL) pin barrel
USB_Y0 = CRADLE_Y0 + M["usb_mouth_recess"]
USB_Y1 = USB_Y0 + M["usb"][1]
USB_Z1 = CPCB_Z1 + M["usb"][2]
# fixed lip
LIP_Z0 = T + CLR                                      # 7.85 underside
LIP_Z1 = LIP_Z0 + M["lip_t"]                          # 9.45
LIP_Y0 = Y_VISOR - M["lip_overlap"]                   # 17.2 lip tip
LIP_POCKET_Y = NEST_FLAT + M["lip_pocket"]            # 19.65 wall of the nose pocket under the lip
# rear latch
LATCH_Y_FACE = -NEST_R                                # -23.25 front face of the beam (0.25 from the marker at x = 0)
LATCH_Y_BACK = LATCH_Y_FACE - M["latch_h"]            # -24.4
LATCH_Y_NA = 0.5 * (LATCH_Y_FACE + LATCH_Y_BACK)      # neutral axis of the beam
HOOK_Z0 = T + CLR                                     # 7.85 retaining face (90 deg)
HOOK_R = NEST_R - M["latch_overhang"]                 # 21.5 hook nose radius (concentric with the marker)
TUB_TOP_FLAT_R = R_OUT - M["top_fillet"]              # 22.4 where the flat top of the tub ends
HOOK_OVERLAP = TUB_TOP_FLAT_R - HOOK_R                # 0.90 hook on the flat top (nominal)
LATCH_L = HOOK_Z0 - M["latch_root_z"]                 # 11.65 free length root -> retaining face
HOOK_LEAD_Z0 = HOOK_Z0 + M["hook_nose_flat"]          # 8.25 start of the lead-in
LATCH_TOP_Z = HOOK_LEAD_Z0 + M["latch_overhang"] / math.tan(math.radians(M["hook_lead_deg"]))   # 11.28
TAB_Y0 = LATCH_Y_BACK - M["tab_len"]                  # -33.0 rear end of the thumb tab
TAB_Z0 = LATCH_TOP_Z - M["tab_t"]
WELL_HX = M["latch_w"] / 2 + M["latch_side_gap"]      # 8.2
WELL_Y1 = LATCH_Y_FACE + M["latch_front_gap"]         # -21.05
WELL_Y0 = LATCH_Y_BACK - M["latch_back_gap"]          # -27.0
_s = M["guard_top_z"] - M["latch_root_z"]
LATCH_STOP_GAP = M["latch_stop_deflection"] * (3 * LATCH_L * _s ** 2 - _s ** 3) / (2 * LATCH_L ** 3)   # 1.571 beam back -> stop rib
STOP_RIB_Y1 = LATCH_Y_BACK - LATCH_STOP_GAP           # front face of the stop ribs


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
