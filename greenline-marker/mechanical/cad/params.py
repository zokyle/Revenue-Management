"""GreenLine GL-1 mechanical parameters.

Loads design/master_params.yaml (the single source of truth for shared numbers, rev B) and
derives every dependent dimension exactly once.  Mechanical-only choices (not shared with the
PCB layout) live in MECH below.  Nothing in parts.py may contain a bare design number: it must
come from Y (YAML), MECH (mechanical-only) or a derived attribute of this module.

Frame: origin at puck centre on the base plane, +x right, +y forward (visor), +z up, mm.
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
    # seal: no glue chamfer / channel (any relief in the 0.8 visor wall or the 0.65 ledge goes below the wall minimum)
    # roof / LCD pocket
    recess_wall=0.8,                 # wall of the cover-glass recess below roof level
    lcd_rib_t=0.8, lcd_rib_z0=4.75,  # glass locating ribs reach down to this z
    lcd_side_ribs_y=[(-11.0, -7.0), (4.0, 8.0)],
    lcd_rear_ribs_x=(8.0, 11.0),
    cover_tape_id=23.0, lcd_psa_window_dia=23.0,
    # support posts: rectangles (x0, x1, y0, y1) for the +x side; mirrored to -x
    posts=dict(A=(14.6, 16.2, 1.0, 2.6), B=(13.55, 15.15, 10.0, 11.6),
               C=(5.7, 7.3, -19.4, -17.8), E=(3.4, 5.0, 13.75, 15.35)),
    # camera hood (prism bay + light baffle)
    hood_wall=0.8, hood_skirt_z0=3.0, hood_corner_fill_y0=16.0,
    visor_land=0.50, visor_bevel_deg=30.0,   # land >= 0.5 so the bevelled rim of the opening never drops below 0.5 mm
    hood_rear_chamfer_margin=0.015,  # extra on the chamfer that keeps the hood rear wall one fit clearance off the prism hypotenuse
    window_bond=0.05,                # adhesive line behind the visor window
    # vent
    vent_xy=(17.9, -3.0), vent_pad=5.6, vent_pad_h=0.2, vent_od=5.0, vent_t=0.26, vent_area_dia=2.0,
    # nose index groove
    nose_w=1.0, nose_depth=0.3,
    # base plate
    baffle_pd_clear=0.25, baffle_wall=0.8, spoke_w=0.8, spoke_angles_deg=[90.0, 225.0, 315.0],
    ball_seat_cone_half_angle_deg=45.0, ball_seat_model_gap=0.01,
    key_w=1.2, key_x=9.25,           # tub lugs at x = +-key_x on the visor underside
    pad_dia=1.8, pad_t=0.035,
    led_body=(1.0, 0.5), led_pair_offset=0.45,
    # reference solids
    pcb_psa_t=0.13, flex_w=6.0, flex_t=0.15, flex_z_top_run=4.775, flex_z_bottom_run=3.925,
    flex_straight=0.35, foam_dx=26.6,
    # optics (for the checks)
    pupil_below_cube_top=0.4, pupil_dia=0.38, n_prism=1.517,
    fov_h_half_deg=26.0, fov_up_deg=17.6, fov_down_deg=15.0,
    # cradle
    cradle_size=(60.0, 60.0, 14.0), cradle_nest_wall_h=3.0, cradle_corner_r=4.0,
    plate_t=1.5, plate_hole_dia=2.0,
    pin_free_len=8.3, pin_working_h=5.82, pin_plunger_dia=1.07, pin_body_dia=1.83, pin_tail_dia=0.76,
    # Mill-Max 0914 travel / force as recorded in docs/research/bom-verification-opto.md (PROVISIONAL until the drawing is read)
    pin_max_working_h=6.96, pin_mid_stroke=1.14, pin_full_stroke=2.29, pin_force_working_N=0.59,
    pin_body_top_below_plate=0.3, pin_tail_below_pcb=0.7,
    real_pad_height=1.13,            # contact pad above the puck base plane incl. 0.13 PSA
    cradle_pcb=(22.0, 30.0, 1.6), cradle_pcb_rear_y=-30.5, cradle_pcb_screw_xy=[(8.5, -28.0), (8.5, -3.0)],
    cradle_screw_pilot_dia=1.7, cradle_screw_pilot_depth=0.5,   # spot marks only: drill dia 1.6 x 3 after printing
    usb=(8.94, 7.35, 3.26), usb_mouth_recess=0.5,
    scallop_half_w=8.0,
    lighten_x=(13.75, 26.5), lighten_y_half=17.0, lighten_ceiling_z=-4.1,
    foot_pocket_dia=8.4, foot_pocket_depth=1.0, foot_xy=(23.5, 23.5), foot_h=3.0, foot_dia=8.0,
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
LAND_RI, LAND_FLAT_IN = _b["seal_land"]["r_inner"], _b["seal_land"]["flat_y_inner"]
GRAIN_X, GRAIN_Y, GRAIN_D = _b["grain_cavity"]["x"], _b["grain_cavity"]["y"], _b["grain_cavity"]["dia"]
PAD_HOLE_D, PAD_Y, PAD_XS = _b["pad_holes"]["dia"], _b["pad_holes"]["y"], list(_b["pad_holes"]["xs"])
BALL_D, BALL_PROT = _b["feet"]["ball_dia"], _b["feet"]["protrusion"]
BALL_XY = [tuple(p) for p in _b["feet"]["positions"]]
BALL_Z = BALL_D / 2 - BALL_PROT                       # ball centre height above the base plane

_p = Y["pcb"]
PCB_T, PCB_Z0, PCB_R, PCB_FLAT = _p["thickness"], _p["z_bottom"], _p["radius"], _p["flat_y"]
PCB_Z1 = PCB_Z0 + PCB_T
PCB_EDGE_CLR = _p["component_edge_clearance"]

LEDGE_RI, LEDGE_Z0, LEDGE_Z1 = Y["tub_ledge"]["r_inner"], Y["tub_ledge"]["z0"], Y["tub_ledge"]["z1"]
BEAD_T = LEDGE_Z0 - BASE_T                            # dispensed seal bead thickness (0.2)

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
WIN_RECESS_DEPTH, WIN_Z0, WIN_Z1 = _w["recess_depth"], _w["z0"], _w["z1"]
WIN_RECESS_W = WIN_W + 0.1                            # 4.4 (task statement)
OPEN_HALF_W, OPEN_Z0, OPEN_Z1 = _w["opening"]["half_w"], _w["opening"]["z0"], _w["opening"]["z1"]
WIN_RECESS_FLOOR_Y = Y_VISOR - WIN_RECESS_DEPTH       # 17.85
VENT_HOLE_D = Y["vent"]["hole_dia"]

TOP_PARTS = Y["top_side_parts"]
_bs = Y["bottom_side_parts"]
LED_RING = dict(_bs["grain_led_ring"]); PD = dict(_bs["photodiode"])

# ----------------------------------------------------------------------------------------------
# Derived mechanical dimensions
# ----------------------------------------------------------------------------------------------
M = MECH
# LCD pocket (bonding plane) and the thick roof ring that carries the cover-glass recess
LCD_POCKET_X = LCD_X1 + CLR                           # 13.55
LCD_POCKET_Y1 = LCD_Y1 + CLR                          # 13.75
LCD_POCKET_Y0 = LCD_Y0 - CLR                          # -17.05
THICK_RING_R = RECESS_D / 2 + M["recess_wall"]        # 15.05

# camera hood
HOOD_IN_HW = CAM_DX / 2 + CLR                         # 1.985 half-width of the bay (clears the cube)
HOOD_OUT_HW = HOOD_IN_HW + M["hood_wall"]             # 2.785
HOOD_Z_OVER_CUBE = CAM_Z1 + CLR                       # 4.81 underside of walls that pass over the cube
HOOD_REAR_Y0 = LCD_POCKET_Y1                          # 13.75 rear face of the rear wall
HOOD_REAR_Y1 = HOOD_REAR_Y0 + M["hood_wall"]          # 14.55 front face of the rear wall = bay rear
HOOD_FRONT_IN_Y = WIN_RECESS_FLOOR_Y - MIN_WALL       # 17.05 inner face of the thickened visor wall
HOOD_PAD_Y = max(v[1] for v in CAM_XY.values()) + CAM_DY / 2 + CLR   # 17.325 pad face in front of the cube
THIN_STRIP_T = WIN_RECESS_FLOOR_Y - HOOD_PAD_Y        # 0.525 wall behind the recess below the opening
BEVEL_GROW = (WIN_RECESS_FLOOR_Y - M["visor_land"] - HOOD_FRONT_IN_Y) * math.tan(math.radians(M["visor_bevel_deg"]))
OPEN_HALF_W_INSIDE = OPEN_HALF_W + BEVEL_GROW         # 1.939 at the inner face

# the side wall below the visor ends on the radial plane through the outer D corner (full 1.0 mm wall end face)
HORN_X_OUT = math.sqrt(R_OUT ** 2 - Y_VISOR ** 2)     # 13.8 outer D corner
HORN_ANGLE_DEG = math.degrees(math.atan2(Y_VISOR, HORN_X_OUT))
HORN_X_IN = R_IN * HORN_X_OUT / R_OUT                 # 13.2 where that radial plane meets the inner wall face
HORN_Y_IN = R_IN * Y_VISOR / R_OUT                    # 17.6
# 45 deg chamfer on the bottom front edge of the hood rear wall: keeps >= CLR normal to the prism hypotenuse
_hyp_gap = ((HOOD_Z_OVER_CUBE - PRISM_Z0) - (HOOD_REAR_Y1 - PRISM_Y0)) / math.sqrt(2)    # 0.177 without the chamfer
HOOD_REAR_CHAMFER = max(0.0, (CLR - _hyp_gap) * math.sqrt(2)) + M["hood_rear_chamfer_margin"]
PRISM_HOOD_CLR = _hyp_gap + HOOD_REAR_CHAMFER / math.sqrt(2)

# base plate
PD_HALF_DIAG = math.hypot(PD["dx"] / 2, PD["dy"] / 2)
BAFFLE_RI = PD_HALF_DIAG + M["baffle_pd_clear"]       # 2.956
BAFFLE_RO = BAFFLE_RI + M["baffle_wall"]
GRAIN_R = GRAIN_D / 2
_ca = math.radians(M["ball_seat_cone_half_angle_deg"])
BALL_SEAT_APEX_Z = BALL_Z + (BALL_D / 2 + M["ball_seat_model_gap"]) / math.sin(_ca)
BALL_SEAT_R_BOTTOM = BALL_SEAT_APEX_Z * math.tan(_ca)
BALL_SEAT_R_TOP = max(0.0, (BALL_SEAT_APEX_Z - BASE_T) * math.tan(_ca))
KEY_NOTCH_HW = M["key_w"] / 2 + CLR                   # 0.85
KEY_NOTCH_Y0 = Y_VISOR_IN - CLR                       # 17.35
PAD_WEB = (PAD_XS[1] - PAD_XS[0]) - PAD_HOLE_D        # 0.34 -> merged into one slot (see deviations)
PAD_Z0 = PCB_Z0 - M["pad_t"]                          # modelled pad contact plane

# vent
VENT_PAD_Z = ROOF_Z - M["vent_pad_h"]                 # 6.6
VENT_Z0 = VENT_PAD_Z - M["vent_t"]

# optics (paraxial unfolding, for reference; the ray trace is in checks)
PUPIL_Z = CAM_Z1 - M["pupil_below_cube_top"]
VIRTUAL_PUPIL_BEHIND_EXIT = (CAM_Z1 - PUPIL_Z) + PRISM_BOND + PRISM_LEG / M["n_prism"]
VIRTUAL_PUPIL_Y = PRISM_EXIT_Y - VIRTUAL_PUPIL_BEHIND_EXIT

# cradle (same frame as the puck seated at 0 deg: puck base plane at z = 0)
NEST_R = R_OUT + CLR                                  # 23.25
NEST_FLAT = Y_VISOR + CLR                             # 18.65
NEST_SHIFT = NEST_R - NEST_FLAT                       # 4.6: puck centre moves by this at 180 deg
NEST_CY = -NEST_SHIFT / 2                             # -2.3: centre of the two-fold symmetric nest
PLATE_Z1 = -BALL_PROT                                 # -0.10 (the ball feet rest on the plate)
PLATE_Z0 = PLATE_Z1 - M["plate_t"]                    # -1.60
CRADLE_TOP_Z = M["cradle_nest_wall_h"]
CRADLE_BOT_Z = CRADLE_TOP_Z - M["cradle_size"][2]     # -11.0
CRADLE_X = M["cradle_size"][0] / 2
CRADLE_Y0 = NEST_CY - M["cradle_size"][1] / 2
CRADLE_Y1 = NEST_CY + M["cradle_size"][1] / 2
CPCB_Z1 = M["real_pad_height"] - M["pin_working_h"]   # -4.69 top face of the cradle PCB
CPCB_Z0 = CPCB_Z1 - M["cradle_pcb"][2]
CPCB_Y0 = M["cradle_pcb_rear_y"]; CPCB_Y1 = CPCB_Y0 + M["cradle_pcb"][1]
CPCB_HX = M["cradle_pcb"][0] / 2
PIN_BODY_Z1 = PLATE_Z0 - M["pin_body_top_below_plate"]
CRADLE_PIN_SLOT_W = M["pin_body_dia"] + 2 * CLR       # 2.33: drop-in clearance round the (PROVISIONAL) pin body
PIN_MODEL_COMPRESSION_EXTRA = M["real_pad_height"] - PAD_Z0   # modelled pins are this much shorter than real
USB_Y0 = CRADLE_Y0 + M["usb_mouth_recess"]
USB_Y1 = USB_Y0 + M["usb"][1]
USB_Z1 = CPCB_Z1 + M["usb"][2]


def puck_to_cradle_180(x, y):
    """Cradle-frame position of puck point (x, y) when the puck is seated turned 180 deg."""
    return (-x, 2 * NEST_CY - y)


def cradle_to_puck_180(x, y):
    """Puck-frame position that sits over cradle point (x, y) in the 180 deg position."""
    return (-x, 2 * NEST_CY - y)


def post_rects():
    """All support-post footprints as (name, x0, x1, y0, y1)."""
    out = []
    for k, (x0, x1, y0, y1) in M["posts"].items():
        out.append((k + "+", x0, x1, y0, y1))
        out.append((k + "-", -x1, -x0, y0, y1))
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


if __name__ == "__main__":
    print(write_resolved())
