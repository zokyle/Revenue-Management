"""GreenLine GL-1 mechanical parameters (revision D).

Loads design/master_params.yaml (the single source of truth for shared numbers, rev D) and
derives every dependent dimension exactly once.  Mechanical-only choices (not shared with the
PCB layout) live in MECH below; numbers that the rev D YAML now carries (cradle block, rim relief,
field of view, potting limits ...) are copied into MECH from the YAML under their old key names
(YAML_DRIVEN), so that nothing downstream holds a second copy.  Nothing in parts.py may contain a
bare design number: it must come from Y (YAML), MECH or a derived attribute of this module.

Base plate: the material is a parameter.  BASE_VARIANTS holds the primary (routed FR-4, YAML
base_plate) and the alternative (printed PA12, YAML base_plate.alternative); the module attributes
BASE_T, PSA_T, BALL_HOLE_D ... are those of the ACTIVE variant.  `with base_variant("pa12"):`
switches them (and everything derived from them) for the duration of the block.

Frame: origin at puck centre on the base plane, +x right, +y forward (visor), +z up, mm.
The cradle is modelled in the same frame with the marker seated (marker base plane at z = 0).
"""
from __future__ import annotations
import contextlib, json, math, pathlib
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
    lcd_rib_t=0.8, lcd_rib_z0=4.75,  # side ribs reach down to this z; the two REAR ribs reach down to the free height (LCD_REAR_RIB_Z0):
                                     # they are the stop the tilted glass is pushed back against in assembly step 9
    lcd_side_ribs_y=[(-11.0, -7.0), (4.0, 8.0)],
    lcd_rear_ribs_x=(8.0, 11.0),
    cover_tape_id=25.0,              # tape ring OD 28.0 / ID 25.0 (YAML cover_glass.bond is text only: proposed as a number)
    lcd_psa_window_dia=23.0,
    lcd_psa_vent_w=0.8,              # vent channel in the LCD adhesive frame: the cell under the cover glass breathes into the cavity
    post_names_plain=["A", "C", "E"],  # YAML tub_keepouts.post_feet.centres come in -x / +x pairs in this order
    locating_posts="B",               # YAML tub_keepouts.post_feet.locating: the pair that carries the PCB locating spigots
    spigot_tip_chamfer=0.15,          # lead-in on the spigot tip (captures +-0.2 mm of lateral error when the PCB is joined)
    # camera hood (prism bay + light baffle)
    hood_wall=0.8, hood_skirt_z0=3.0, hood_fill_margin=0.05,
    hood_leadin=0.3,                 # 45 deg lead-in chamfer on the inner bottom edges of the skirts and of the front pad
    hood_rear_chamfer_margin=0.015,  # extra on the chamfer that keeps the hood rear wall one fit clearance off the prism hypotenuse
    # black form-in-place gasket bead on the underside of each hood rear wall (dispensed along a needle guide that registers on
    # the rear face of that wall, cured before the join).  As dispensed it is a low, slumped bead: modelled as a parabolic
    # segment hood_seal_w wide and hood_seal_free_h high, centred hood_seal_centre in front of the rear face of the wall.
    # Half of it hangs behind the cube like a curtain, the other half is squeezed by the cube top to the slit height.
    hood_seal_w=0.50, hood_seal_free_h=0.33, hood_seal_centre=0.35, hood_seal_inset=0.05,
    hood_seal_E_MPa=1.5,             # modulus assumed for the estimate of the standing load of the squeezed bead (soft gasket, about Shore A 40)
    hood_seal_place_tol=0.075,       # accuracy required of the needle guide (the bead centre must stay inside its placement window)
    hood_seal_max_squeeze=0.30,      # largest squeeze accepted for a solid form-in-place bead (fraction of its free height)
    hood_seal_min_land=0.10,         # least width of the squeezed land on the cube top
    window_bond=0.0,                 # rev D: 0.55 recess - 0.40 glass - 0.15 sub-flush leaves no adhesive line: the glass is seated on the
                                     # recess floor.  The seal is a closed FRAME of thixotropic adhesive round the edge of the glass, all of it
                                     # outside the clear opening: the fill of the two side gaps, a bead along the top edge and a fillet along
                                     # the bottom edge in front of the glass.  Nothing is wicked behind the glass
    window_top_bead=0.10,            # height of the top bead above the window top (it stays 0.05 below the tub top)
    window_sill_fillet=0.12,         # leg of the fillet on the shelf in front of the bottom edge of the glass (0.03 behind the visor face)
    window_seal_test_gap=0.02,       # check 13: a bare contact is not a seal - the glass is drawn this far off the recess floor and off its
                                     # shelf for the air test, so that only an adhesive solid on all four edges closes the opening
    # vent
    vent_pad=5.6, vent_pad_h=0.3, vent_od=5.0, vent_t=0.26, vent_area_dia=2.0,
    vent_groove_w=0.6, vent_groove_d=0.3, vent_cross_half=2.5,   # drain grooves on the top face through the vent hole
    # nose index groove
    nose_w=1.0, nose_depth=0.3,
    # base plate / PCB underside
    pad_dia=1.8,
    led_body=(1.0, 0.5), led_pair_offset=0.45,
    grain_fill_recess=0.05,          # clear potting surface: never closer to the base plane than this (z = +0.05; the modelled solid is this
                                     # maximum-material condition; YAML text only: proposed as a number)
    grain_fill_recess_max=0.20,      # deepest potting surface accepted (z = +0.20)
    grain_fill_below_crest=0.10,     # the potting surface lies between the crest of the baffle ring and this far inside it (the crest is
                                     # never covered: no clear bridge from the LEDs to the photodiode); the fill target is the middle
    grain_fill_min_cover=0.30,       # least potting over an embedded part (LED 0.45, photodiode 0.48 high)
    potting_viscosity_Pa_s=(0.1, 2.0),   # mixed viscosity window for the clear potting (levels in minutes, lets bubbles rise; estimate)
    potting_dispense_tol=0.03,       # volume accuracy assumed for the positive-displacement dispenser (fraction)
    baffle_psa_t=0.13,               # die-cut adhesive annulus that bonds the separate baffle ring to the PCB (FR-4 build)
    baffle_psa_tol=0.02,
    baffle_ring_tol=(0.0, 0.03),     # finished height of the ring: +0.00 / -0.03, lapped by us in a pocket gauge (the print is oversize)
    baffle_ring_lap_allowance=0.15,  # height added to the printed ring for lapping
    baffle_crest_max_z=0.15,         # per-unit acceptance of the ring crest after lamination: between the base plane (z 0) and this
    plate_gauging_tol=0.01,          # accuracy of the plate thickness measurement that the ring height is matched to
    ring_sprue=dict(n=6, pitch=11.0, runner=2.0, gate_w=0.8, gate_len=1.0),   # print file of the baffle ring: a sprued set
    bat_pad_gap=0.7,                 # the two lead pads fill the YAML pad zone in y with this gap between them
    liner_tooling=dict(dia=3.0, x=27.0, liner=(64.0, 50.0)),   # carrier liner of the PCB-sheet die cuts: two tooling holes for the posts of the lamination jig
    fr4_min_inner_radius=0.5, fr4_min_web=1.0,   # fabrication rules checked on the FR-4 plate (web rule to be confirmed by the fabricator)
    fr4_tol_outline=0.10, fr4_tol_hole=0.05, fr4_tol_thickness=0.10,   # thickness: the fabricator's standard for boards under 1.0 mm
    fr4_mask_relief=0.15,            # solder-mask opening round each drilled hole = hole + this (no mask on the hole wall or rim)
    fr4_tab_recess_max=0.25,         # a break-off tab may only sit on the flat, its bite recessed into the outline by at most this
    # tolerances assumed for the stack arithmetic (not measured).  tol_printed is what drawing GL1-010 REQUIRES of the critical tub
    # dimensions (post feet to seal face, to rim); print_tol (below) is what the bureau quotes in general.  Both are carried
    tol_printed=0.10, tol_pcb=0.08, tol_sheet_frac=0.10, tol_fr4_plate=0.10, tol_pa12_plate=0.10,
    tol_ball_set=0.02,               # ball protrusion as set on the gauge plate: 0.10 +-0.02
    ball_gap_min=0.02,               # least epoxy between the ball top and its copper land (a ball that touches holds the laminate open)
    plate_sort_plus=dict(fr4=0.10, pa12=0.05),   # upper incoming limit of the plate thickness above nominal
    seal_dispense_margin=1.0,        # seal adhesive to dispense = volume of the joint at its upper limit x this, rounded UP to 5 mm3
    # handbook expansion coefficients for the thermal estimates (ppm/K) and the temperature range
    cte_pa12=110.0, cte_fr4=15.0, cte_glass=9.0, cte_lcd=4.0, t_assembly=23.0, t_range=(-10.0, 70.0),
    # reference solids
    flex_w=6.0, flex_t=0.15, flex_z_top_run=4.775,
    fpc_entry_h=1.0,                 # height of the J1 mouth above the PCB (PROVISIONAL: FH12 drawing)
    flex_straight=0.35, foam_dx=26.6,
    # optics (for the checks)
    pupil_below_cube_top=0.4, pupil_dia=0.38, n_prism=1.517, n_window=1.52,
    fov_down_sensor_deg=15.0,        # what the sensor could use; reported, not required (the required field is in the YAML)
    fov_up_guar_shortfall_recorded=0.05,   # deviation D31: the YAML's 15.0 deg is a rounded figure; the model gives 14.97.  A shortfall up to
                                     # this is a recorded deviation (warning), anything more fails check 4
    fov_angle_tol=0.002,             # resolution of the bisection for the limit angles (deg)
    print_tol=0.2,                   # print tolerance used for the camera-position sensitivity rows
    # ------------------------------------------------------------------ assembly paths proven in check 14
    lcd_tilt_deg=6.0, lcd_bias=0.55,                 # LCD tilt-in: rear edge first, glass shifted this far toward the visor
    join_offset=0.1,                                 # lateral guidance the join fixture must give until the spigots engage
    jig_pin_fit=0.025,                               # radial fit of a lamination-jig pin (dia 1.10) in a PCB locating hole (dia 1.15)
    jig_frame_clearance=0.10,                        # a FIXED frame round the base plate would need this clearance (sprung fingers do not)
    join_drops=[6.0, 4.5, 3.6, 3.0, 2.4, 1.8, 1.5, 1.2, 0.9, 0.62],
    hinge_y=-30.0, hinge_z=0.0,                      # axis of the join fixture hinge (parallel to x, behind the tub at the base plane)
    hinge_open_deg=[0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 12.0, 20.0, 35.0, 60.0],
    # ------------------------------------------------------------------ cradle (charging / data dock only; rev D: the YAML cradle block
    # carries body position, pin heights, cradle PCB, lip and latch numbers - see YAML_DRIVEN below)
    cradle_nest_wall_h=3.0,          # body top above the marker base plane
    cradle_corner_r=4.0,
    # Mill-Max 0914 long-stroke pin (PROVISIONAL until the drawing is read; docs/research/bom-verification-opto.md)
    pin_free_len=8.3, pin_plunger_dia=1.07, pin_body_dia=1.83, pin_tail_dia=0.76,
    pin_body_margin=0.2,             # barrel top this far below the fully compressed plunger tip
    pin_tail_below_pcb=0.7,
    cradle_screw_pilot_dia=1.7, cradle_screw_pilot_depth=0.5,   # spot marks only: drill dia 1.6 x 3 after printing
    usb=(8.94, 7.35, 3.26),
    scallop_deg=(-42.0, 0.0), scallop_inset=2.0,   # finger scallops: sectors of the nest wall removed (angles from +x on the +x side, mirrored)
    lighten_x=(17.0, 26.5), lighten_y=(-22.0, 10.0), lighten_front=(13.0, -9.5, 20.0), lighten_ceiling_z=-4.1,
    foot_pocket_dia=8.4, foot_pocket_depth=1.0, foot_xy=(23.5, 23.5), foot_h=3.0, foot_dia=8.0,
    core_dia=5.0, core_roof=3.5,     # blind core under each foot pocket (the four corners would otherwise be 13 mm solid)
    # drained nest floor: the marker stands on a front strip and two pads; the rest of the floor is a basin that falls to the scallops
    basin_depth=0.65, basin_fall_deg=2.0, strip_y0=12.8, ball_pad_dia=4.0, slot_rim_t=1.2, dam_t=1.7,
    well_drain_x=(5.7, 8.1), well_drain_skin=0.85, well_drain_h=2.4,   # tunnel from the latch well to the rear face
    # hold-down 1: fixed lip over the top front edge of the marker, between the camera windows
    lip_pocket=1.0,
    # hold-down 2: sprung cantilever latch at the rear.  Rectangular beam, front face vertical, thinnest at a neck below the hook
    # (the back face tapers in from the root and flares out again into the hook), full-width hook with a STRAIGHT nose and a
    # retaining face raked back (nose lowest), thumb tab, stop ribs for the beam and a stop under the tab
    latch_flare=2.5,                 # the neck lies this far below the nose level
    hook_nose_flat=0.4, hook_lead_deg=30.0,
    latch_root_fillet=1.0, hook_heel_fillet=0.5, tab_root_fillet=0.6, latch_neck_blend=8.0,
    latch_side_gap=1.2, latch_front_gap=2.2, latch_back_gap=2.7,
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
# Numbers that the rev D YAML carries and that the code below still reads from MECH under their old names
# ----------------------------------------------------------------------------------------------
_cr = Y["cradle"]
_hd, _pins = _cr["hold_down"], _cr["pins"]
_fr = Y["cameras"]["field_required_deg"]
YAML_DRIVEN = dict(
    rim_relief=Y["envelope"]["rim_relief"],                   # the tub side wall ends this far above the base plane
    epoxy_dome_max=Y["base_plate"]["feet"]["epoxy_dome_max"],  # stage 1 ball potting may dome this far over the plate
    fov_h_half_deg=_fr["h"], fov_up_deg=_fr["up"], fov_down_deg=_fr["down"], fov_up_guaranteed_deg=_fr["up_guaranteed"],
    lip_half_w=_hd["lip"]["half_w"], lip_overlap=_hd["lip"]["overlap"], lip_t=_hd["lip"]["t"], lip_clearance=_hd["lip"]["clearance"],
    latch_w=_hd["latch"]["w"], latch_h_root=_hd["latch"]["t_root"], latch_h_neck=_hd["latch"]["t_neck"], latch_h_tip=_hd["latch"]["t_hook"],
    latch_free_length=_hd["latch"]["free_length"], hook_overlap=_hd["latch"]["hook_overlap"], hook_rake_deg=_hd["latch"]["rake_deg"],
    latch_clearance=_hd["latch"]["clearance"], latch_stop_travel=_hd["latch"]["stop_travel"], tab_stop_travel=_hd["latch"]["tab_stop_travel"],
    pin_max_working_h=round(_pins["working_height"] + _pins["compression"], 6),   # free height of a pin above the cradle PCB (6.96)
    pin_full_stroke=_pins["stroke"],
    cradle_float=_cr["float"],
)
MECH.update(YAML_DRIVEN)

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
BASE_R, BASE_FLAT = _b["radius"], _b["flat_y"]
LAND_RI, LAND_FLAT_IN = _b["seal_land"]["r_inner"], _b["seal_land"]["flat_y_inner"]
GRAIN_X, GRAIN_Y, GRAIN_D = _b["grain_cavity"]["x"], _b["grain_cavity"]["y"], _b["grain_cavity"]["dia"]
PAD_HOLE_D, PAD_Y, PAD_XS = _b["pad_holes"]["dia"], _b["pad_holes"]["y"], list(_b["pad_holes"]["xs"])
PAD_SLOT_L = _b["pad_holes"]["slot_length"]
BALL_D, BALL_PROT = _b["feet"]["ball_dia"], _b["feet"]["protrusion"]
PSA_FOOT_HOLE_D = _b["feet"]["psa_hole_dia"]
BALL_XY = [tuple(p) for p in _b["feet"]["positions"]]
BALL_Z = BALL_D / 2 - BALL_PROT                       # ball centre height above the base plane (0.40)
BALL_TOP_Z = BALL_Z + BALL_D / 2                      # 0.90
FOOT_KEEPOUT_D, FOOT_LAND_D = _b["feet"]["pcb_keepout_dia"], _b["feet"]["pcb_land_dia"]
BAFFLE_RI, BAFFLE_RO = _b["baffle"]["inner_dia"] / 2, _b["baffle"]["outer_dia"] / 2
BAFFLE_WALL, SPOKE_W, SPOKE_ANGLES = _b["baffle"]["wall"], _b["baffle"]["spoke_width"], list(_b["baffle"]["spokes_deg"])

_p = Y["pcb"]
PCB_T, PCB_Z0, PCB_R, PCB_FLAT = _p["thickness"], _p["z_bottom"], _p["radius"], _p["flat_y"]
PCB_Z1 = PCB_Z0 + PCB_T
PCB_EDGE_CLR = _p["component_edge_clearance"]
_lh = _p["locating_holes"]
LOC_ROUND = (_lh["round"]["x"], _lh["round"]["y"], _lh["round"]["dia"])
LOC_SLOT = (_lh["slot"]["x"], _lh["slot"]["y"], _lh["slot"]["dia"], _lh["slot"]["length_x"])
SPIGOT_D, SPIGOT_H = _lh["spigot_dia"], _lh["spigot_height"]
SPIGOT_Z0 = PCB_Z1 - SPIGOT_H                         # 1.20: spigot tip (the spigot hangs from the post foot into the PCB hole)
SPIGOT_FIT = (LOC_ROUND[2] - SPIGOT_D) / 2            # 0.075 radial: a locating fit, not a drop-in fit
SPIGOT_SPAN = abs(LOC_SLOT[0] - LOC_ROUND[0])         # 28.7: the cameras lie between the two spigots

LEDGE_RI, LEDGE_Z0, LEDGE_Z1 = Y["tub_ledge"]["r_inner"], Y["tub_ledge"]["z0"], Y["tub_ledge"]["z1"]

# ---------------------------------------------------------------------------------------------- base plate variants
BASE_PRIMARY, BASE_ALT = "fr4", "pa12"
_alt = _b["alternative"]
BASE_VARIANTS = {
    "fr4": dict(key="fr4", label="routed FR-4 (primary)", material=_b["material"], short="FR-4 0.80, black solder mask, no copper",
                thickness=_b["thickness"], psa_t=_b["psa"]["thickness"], psa_material=_b["psa"]["mpn"], foot_hole_d=_b["feet"]["hole_dia"],
                baffle_integral=False, printed=False, density=1.85, tol=MECH["tol_fr4_plate"], cte=MECH["cte_fr4"],
                psa_tol=round(MECH["tol_sheet_frac"] * _b["psa"]["thickness"], 3)),
    "pa12": dict(key="pa12", label="printed PA12 (alternative)", material=_alt["material"], short="MJF PA12 0.87, dyed black, not vapor smoothed",
                 thickness=_alt["thickness"], psa_t=_alt["psa_thickness"], psa_material=_alt["psa_mpn"], foot_hole_d=_alt["foot_hole_dia"],
                 baffle_integral=(_alt["baffle"] == "integral"), printed=True, density=1.01, tol=MECH["tol_pa12_plate"], cte=MECH["cte_pa12"],
                 psa_tol=round(MECH["tol_sheet_frac"] * _alt["psa_thickness"], 3)),
}
for _v in BASE_VARIANTS.values():
    assert abs(_v["thickness"] + _v["psa_t"] - PCB_Z0) < 1e-9, f"base plate + adhesive sheet must end at the PCB underside ({_v['key']})"
    # incoming limits of the plate thickness.  Lower: the ball top (set on the gauge plate, protrusion +-tol_ball_set) must keep
    # ball_gap_min of epoxy to its copper land with the sheet at its thinnest.  Upper: nominal + plate_sort_plus
    _v["accept"] = (math.ceil((BALL_TOP_Z + MECH["tol_ball_set"] + MECH["ball_gap_min"] - (_v["psa_t"] - _v["psa_tol"])) * 100 - 1e-6) / 100,
                    round(_v["thickness"] + MECH["plate_sort_plus"][_v["key"]], 2))


def _apply_base(key):
    """Make `key` the active base-plate variant: sets every module attribute that depends on the plate."""
    v = BASE_VARIANTS[key]
    g = globals()
    g.update(
        BASE_KEY=key, BASE=v,
        BASE_T=v["thickness"],                            # plate z 0 .. BASE_T
        PSA_T=v["psa_t"],                                 # die-cut adhesive sheet between base plate and PCB
        PSA_Z0=v["thickness"], PSA_Z1=v["thickness"] + v["psa_t"],
        BALL_HOLE_D=v["foot_hole_d"],
        BAFFLE_INTEGRAL=v["baffle_integral"],             # True: ring on three spokes, part of the plate; False: separate bonded ring
        BEAD_T=LEDGE_Z0 - v["thickness"],                 # height of the perimeter seal joint (base top -> tub seal face)
    )
    return v


@contextlib.contextmanager
def base_variant(key):
    """Temporarily switch the active base-plate variant (parts.py and checks.py read the module attributes at call time)."""
    old = BASE_KEY
    _apply_base(key)
    try:
        yield BASE_VARIANTS[key]
    finally:
        _apply_base(old)


BASE_KEY = BASE_PRIMARY
_apply_base(BASE_PRIMARY)

_l = Y["lcd"]
LCD = dict(_l["glass"])                               # x, y, dx, dy, z0, z1
LCD_X0, LCD_X1 = LCD["x"] - LCD["dx"] / 2, LCD["x"] + LCD["dx"] / 2
LCD_Y0, LCD_Y1 = LCD["y"] - LCD["dy"] / 2, LCD["y"] + LCD["dy"] / 2
LCD_Z0, LCD_Z1 = LCD["z0"], LCD["z1"]
LCD_PSA_T, APERTURE_D = _l["psa_thickness"], _l["aperture_dia"]
BOND_Z = LCD_Z1 + LCD_PSA_T                           # underside of the roof ledge = LCD bonding plane (5.55)

_c = Y["cover_glass"]
CG_D, CG_T, RECESS_D, RECESS_DEPTH = _c["dia"], _c["thickness"], _c["recess_dia"], _c["recess_depth"]
CG_TAPE_T = _c["bond_thickness"]                      # 0.13 transfer-tape ring (rev D)
RECESS_FLOOR_Z = T - RECESS_DEPTH                     # 6.35
ROOF_LEDGE_T = RECESS_FLOOR_Z - BOND_Z                # 0.80
CG_Z0 = RECESS_FLOOR_Z + CG_TAPE_T
CG_Z1 = CG_Z0 + CG_T
CG_BELOW_FLUSH = T - CG_Z1                            # 0.12
CG_TAPE_W = (CG_D - MECH["cover_tape_id"]) / 2        # 1.5 wide ring

ROOF_Z, ROOF_T = Y["roof"]["underside_z"], Y["roof"]["thickness"]

_bt = Y["battery"]
BAT = dict(_bt["body"]); BAT_SWELL, FOAM_T = _bt["swell_allowance"], _bt["foam_above"]
BAT_FIX_T = _bt["fixing_adhesive_max"]
FOAM_Z1 = LCD_Z0; FOAM_Z0 = FOAM_Z1 - FOAM_T
_bp = _bt["pads"]
BAT_PAD_ZONE = (_bp["zone"]["x"][0], _bp["zone"]["y"][0], _bp["zone"]["x"][1], _bp["zone"]["y"][1])   # x0, y0, x1, y1
BAT_PAD_SIZE = tuple(_bp["size"])                     # (dx, dy) of one lead pad
BAT_JOINT_H = _bp["joint_max_height"]                 # lead + solder joint may stand this high above the PCB top


def battery_pad_rects():
    """The two lead pads (x0, y0, x1, y1), nominal: centred in x in the YAML zone, stacked in y with MECH['bat_pad_gap'] between
    them.  The board layout may move them inside the zone; the board-import check then uses the real pads."""
    zx0, zy0, zx1, zy1 = BAT_PAD_ZONE
    dx, dy = BAT_PAD_SIZE
    cx = 0.5 * (zx0 + zx1)
    cy = 0.5 * (zy0 + zy1)
    off = 0.5 * (dy + MECH["bat_pad_gap"])
    return [(cx - dx / 2, cy + s * off - dy / 2, cx + dx / 2, cy + s * off + dy / 2) for s in (1, -1)]


_cam = Y["cameras"]
CAM_DX, CAM_DY, CAM_H = _cam["body_dx"], _cam["body_dy"], _cam["height"]
CAM_XY = dict(L=(_cam["left"]["x"], _cam["left"]["y"]), R=(_cam["right"]["x"], _cam["right"]["y"]))
CAM_Z0, CAM_Z1 = PCB_Z1, PCB_Z1 + CAM_H
FOV_H, FOV_UP, FOV_UP_GUAR, FOV_DOWN = _fr["h"], _fr["up"], _fr["up_guaranteed"], _fr["down"]
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
WIN_Y0 = WIN_RECESS_FLOOR_Y + MECH["window_bond"]     # rear face of the window (seated on the recess floor in rev D)
WIN_Y1 = WIN_Y0 + WIN_T                               # 18.25 front face
WIN_SUBFLUSH = Y_VISOR - WIN_Y1                       # 0.15 below the visor face
WIN_TOP_Z = WIN_Z0 + WIN_H                            # 7.45
WIN_TOP_BELOW = T - WIN_TOP_Z                         # 0.15 below the tub top
WIN_LANDS = ((WIN_W - 2 * OPEN_HALF_W) / 2, OPEN_Z0 - WIN_Z0, WIN_TOP_Z - OPEN_Z1)   # glass on the recess floor: sides, sill, top
WIN_SILL_FILLET = MECH["window_sill_fillet"]          # fillet on the shelf in front of the bottom edge of the glass
WIN_FRAME_BELOW_FACE = Y_VISOR - (WIN_Y1 + WIN_SILL_FILLET)   # 0.03: the fillet stays behind the visor face
VENT_HOLE_D = Y["vent"]["hole_dia"]
VENT_XY = (Y["vent"]["x"], Y["vent"]["y"])

_ko = Y["tub_keepouts"]
KO_POST_SIZE = _ko["post_feet"]["size"]
KO_POST_CENTRES = [tuple(c) for c in _ko["post_feet"]["centres"]]                # plain support posts (A, C, E)
KO_LOC_SIZE = _ko["post_feet"]["locating"]["size"]
KO_LOC_CENTRES = [tuple(c) for c in _ko["post_feet"]["locating"]["centres"]]     # posts B: they carry the two PCB spigots
KO_HOOD_HW, KO_HOOD_Y0, KO_HOOD_Y1 = _ko["camera_hoods"]["half_w"], _ko["camera_hoods"]["y0"], _ko["camera_hoods"]["y1"]
KO_HOOD_MAX_H = _ko["camera_hoods"]["max_part_height"]
PCB_FREE_H = _ko["free_height_above_pcb"]             # 2.55: component height the layout may use anywhere outside the keep-outs
KO_FREE_Z = PCB_Z1 + PCB_FREE_H                       # 4.35: below this the tub may exist over the PCB only inside the keep-outs
FOOT_ZONE_D, FOOT_ZONE_LAND_D = _ko["foot_zones"]["dia"], _ko["foot_zones"]["land_dia"]
FOOT_ZONES = [tuple(c) for c in _ko["foot_zones"]["positions"]]

TOP_PARTS = Y["top_side_parts"]
_bs = Y["bottom_side_parts"]
LED_RING = dict(_bs["grain_led_ring"]); PD = dict(_bs["photodiode"])
VIA_KEEPOUTS = dict(_bs["via_keepouts"])

CRADLE_SIZE = (_cr["body"]["dx"], _cr["body"]["dy"], _cr["body"]["dz"])
CRADLE_PAD_Z = _cr["pad_plane_z"]                     # 0.965: copper face of the contact pads (rev D: the YAML states the face)
PIN_ROW_Y = _cr["pin_row_y"]
PIN_WORK_H, PIN_FORCE_N = _pins["working_height"], _pins["force_working_N"]
PIN_POSITIONS = _pins["positions"]
PINS_CONSUMER = list(_pins["populated_consumer"])                # the four at x = -7.62 .. 0.0
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
LCD_REAR_RIB_Z0 = KO_FREE_Z                           # 4.35: the two rear glass ribs reach down to the free height above the PCB
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
# black gasket bead on the flat underside of the rear wall, astride the rear edge of the cube top
CAM_REAR_Y = min(v[1] for v in CAM_XY.values()) - CAM_DY / 2          # 14.125 rear face of the cube
HOOD_FLAT_Y1 = HOOD_REAR_Y1 - HOOD_REAR_CHAMFER       # 14.43: where the chamfer of the rear wall starts (end of its flat underside)
HOOD_SEAL_YC = HOOD_REAR_Y0 + M["hood_seal_centre"]   # 14.10 centre line of the bead
HOOD_SEAL_HW = HOOD_IN_HW - M["hood_seal_inset"]      # half length of the bead along x


def hood_seal_section(n=60):
    """Cross-section of the hood gasket bead in the y-z plane, as dispensed and as squeezed by the cube top.
    Free shape: parabolic segment hood_seal_w wide, hood_seal_free_h high, hanging from the wall underside (z = HOOD_Z_OVER_CUBE).
    Squeezed: behind the cube (y < CAM_REAR_Y) it hangs free; over the cube it cannot be deeper than the slit, and the area
    the cube displaces is moved FORWARD at constant volume (first into the wedge under the thin front of the bead, then
    beyond it at the full slit height) - the conservative direction for the clearance to the prism.
    Returns dict(pts=[(y, z)...] polygon as squeezed, area_free, area_squeezed, displaced, y0, y1, contact=(ya, yb) on the cube top,
    compression (peak, fraction of the free height))."""
    import numpy as np
    w, h, yc = M["hood_seal_w"], M["hood_seal_free_h"], HOOD_SEAL_YC
    zw, slit = HOOD_Z_OVER_CUBE, HOOD_SLIT[0]
    ya, yb = yc - w / 2, yc + w / 2
    depth = lambda y: h * max(0.0, 1.0 - ((y - yc) / (w / 2)) ** 2)
    fine = np.linspace(max(ya, CAM_REAR_Y), yb, 4001)
    dfine = np.array([depth(y) for y in fine])
    dy = fine[1] - fine[0]
    displaced = float(np.sum(np.maximum(dfine - slit, 0.0)) * dy)
    need, y_fill, ext = displaced, None, 0.0
    over = dfine > slit
    i0 = int(np.argmax(~over)) if over[0] else 0          # first sample (going forward) where the free bead is thinner than the slit
    acc = 0.0
    for i in range(i0, len(fine)):
        if acc >= need:
            y_fill = float(fine[i]); break
        acc += (slit - dfine[i]) * dy
    if y_fill is None:                                    # the wedge under the bead is full: the rest stands in front of it
        y_fill = yb; ext = (need - acc) / slit
    y_end = yb + ext
    lower = [(float(y), zw - depth(float(y))) for y in np.linspace(ya, min(CAM_REAR_Y, yb), n + 1)]
    if yb > CAM_REAR_Y:
        lower += [(CAM_REAR_Y, zw - slit), (y_fill, zw - slit)] if depth(CAM_REAR_Y) >= slit or displaced > 0 else []
        if ext > 0:
            lower += [(y_end, zw - slit)]
        else:
            lower += [(float(y), zw - depth(float(y))) for y in np.linspace(y_fill, yb, n // 2 + 1)[1:]]
    pts = [(ya, zw)] + [p for p in lower[1:]]
    if abs(pts[-1][1] - zw) > 1e-9:
        pts.append((y_end, zw))
    area_free = 2.0 / 3.0 * w * h
    xs = np.array([p[0] for p in pts]); zs = np.array([p[1] for p in pts])
    area_sq = 0.5 * abs(float(np.dot(xs, np.roll(zs, -1)) - np.dot(zs, np.roll(xs, -1))))
    return dict(pts=pts, area_free=area_free, area_squeezed=area_sq, displaced=displaced, y0=ya, y1=y_end,
                contact=(CAM_REAR_Y, y_fill) if displaced > 0 else None, compression=max(0.0, (h - slit) / h))


_hs = hood_seal_section()
HOOD_SEAL_Y0, HOOD_SEAL_Y1 = _hs["y0"], _hs["y1"]      # 13.85 .. 14.35 on the wall underside
HOOD_SEAL_VOL = 2 * HOOD_SEAL_HW * _hs["area_free"]    # mm3 of gasket material per hood, as dispensed
HOOD_SEAL_CONTACT_W = (_hs["contact"][1] - _hs["contact"][0]) if _hs["contact"] else 0.0   # width of the squeezed land on the cube top
HOOD_SEAL_COMPRESSION = _hs["compression"]             # peak squeeze as a fraction of the free height
# placement window of the bead centre: its rear edge stays on the wall underside, its front edge behind the chamfer
HOOD_SEAL_WINDOW = (HOOD_SEAL_Y0 - HOOD_REAR_Y0, HOOD_FLAT_Y1 - (HOOD_SEAL_YC + M["hood_seal_w"] / 2))
# standing load of the squeezed bead on the cube (estimate: mean strain over the land x modulus x area)
HOOD_SEAL_LOAD_N = M["hood_seal_E_MPa"] * 0.5 * HOOD_SEAL_COMPRESSION * HOOD_SEAL_CONTACT_W * 2 * min(HOOD_SEAL_HW, CAM_DX / 2)

# base plate, grain opening, baffle, potting
PD_HALF_DIAG = math.hypot(PD["dx"] / 2, PD["dy"] / 2)
GRAIN_R = GRAIN_D / 2
PAD_WEB = (PAD_XS[1] - PAD_XS[0]) - PAD_HOLE_D        # 0.34: why the seven holes are one slot
PAD_Z0 = CRADLE_PAD_Z                                 # copper face of a contact pad (0.965, YAML cradle.pad_plane_z)
M["pad_t"] = round(PCB_Z0 - PAD_Z0, 6)                # 0.035 modelled pad thickness
BASE_CORNER_X = math.sqrt(BASE_R ** 2 - BASE_FLAT ** 2)   # 11.83 front corner of the base plate
GRAIN_FILL_Z = M["grain_fill_recess"]                 # 0.05: surface of the clear potting (0.05 inside the opening)
GRAIN_FILL_DEPTH = PCB_Z0 - GRAIN_FILL_Z              # 0.95 of potting under the PCB
GRAIN_FILL_Z_MAX = M["grain_fill_recess_max"]         # 0.20: the surface may lie between GRAIN_FILL_Z and this, never proud of GRAIN_FILL_Z
BAFFLE_PSA_T = M["baffle_psa_t"]
BAFFLE_RING_Z0 = GRAIN_FILL_Z                         # separate ring (FR-4 build): lower face (crest) flush with the potting at its limit
BAFFLE_RING_Z1 = PCB_Z0 - BAFFLE_PSA_T                # 0.87: the adhesive annulus lies between ring and PCB
BAFFLE_RING_H = BAFFLE_RING_Z1 - BAFFLE_RING_Z0       # 0.82 nominal, for the nominal plate
BAFFLE_RING_PRINT_H = BAFFLE_RING_H + M["baffle_ring_lap_allowance"]   # 0.97 as printed (lapped to height by us)
BAFFLE_CREST_MAX_Z = M["baffle_crest_max_z"]          # 0.15


def baffle_ring_height(plate_t=None):
    """Finished (lapped) height of the separate baffle ring for a base plate of the measured thickness plate_t: the crest is
    to end GRAIN_FILL_Z inside the base plane, whatever the plate lot is.  Nominal plate -> BAFFLE_RING_H."""
    v = BASE_VARIANTS[BASE_PRIMARY]
    t = v["thickness"] if plate_t is None else plate_t
    return t + v["psa_t"] - BAFFLE_PSA_T - GRAIN_FILL_Z


def baffle_crest_range():
    """z of the ring crest above the base plane (FR-4 build) with the ring lapped to the plate lot (baffle_ring_height):
    (lowest, highest) from the sheet, annulus, ring and gauging tolerances, worst case.  And the same if the ring were
    lapped to the nominal height regardless of the plate (for comparison: that is why the height is matched)."""
    v = BASE_VARIANTS[BASE_PRIMARY]
    plus, minus = M["baffle_ring_tol"]
    lo = GRAIN_FILL_Z - v["psa_tol"] - M["baffle_psa_tol"] - M["plate_gauging_tol"] - plus
    hi = GRAIN_FILL_Z + v["psa_tol"] + M["baffle_psa_tol"] + M["plate_gauging_tol"] + minus
    un_lo = lo + M["plate_gauging_tol"] - (v["thickness"] - v["accept"][0])
    un_hi = hi - M["plate_gauging_tol"] + (v["accept"][1] - v["thickness"])
    return dict(matched=(round(lo, 4), round(hi, 4)), unmatched=(round(un_lo, 4), round(un_hi, 4)))


def potting_window(crest_z=None):
    """Accepted level of the potting surface (z above the base plane, centre of each compartment) for a ring crest at
    crest_z: between the crest and grain_fill_below_crest inside it, and always within GRAIN_FILL_Z .. GRAIN_FILL_Z_MAX.
    Returns (z_low, z_high, z_target = middle).  The integral ring of the PA12 plate has its crest on the base plane (0)."""
    zc = (0.0 if BAFFLE_INTEGRAL else BAFFLE_RING_Z0) if crest_z is None else crest_z
    lo, hi = max(GRAIN_FILL_Z, zc), min(GRAIN_FILL_Z_MAX, zc + M["grain_fill_below_crest"])
    return lo, hi, 0.5 * (lo + hi)
LED_R_IN = LED_RING["radius"] - M["led_body"][0] / 2  # 4.7 inner edge of the LED bodies
LED_R_OUT = math.hypot(LED_RING["radius"] + M["led_body"][0] / 2, M["led_pair_offset"] + M["led_body"][1] / 2)   # 5.74 outer corner


def epoxy_volumes():
    """Ball potting per foot for the ACTIVE base variant, mm3 (= microlitre): (stage 1: through hole round the ball,
    stage 2: back-fill of the sheet hole round the ball top)."""
    r = BALL_D / 2

    def ball_between(z0, z1):                          # volume of the ball between two heights
        a, b = max(-r, z0 - BALL_Z), min(r, z1 - BALL_Z)
        return 0.0 if b <= a else math.pi * (r * r * (b - a) - (b ** 3 - a ** 3) / 3)
    s1 = math.pi * (BALL_HOLE_D / 2) ** 2 * BASE_T - ball_between(0.0, BASE_T)
    s2 = math.pi * (PSA_FOOT_HOLE_D / 2) ** 2 * PSA_T - ball_between(PSA_Z0, PSA_Z1)
    return s1, s2


def stack_tolerance(key=None, printed=None):
    """Tolerance chains through the laminate (arithmetic on ASSUMED part tolerances), for the base variant `key`.
    The posts of the tub seat on the PCB TOP, so:
      joint    seal joint = PCB thickness - printed step (post foot to seal face) + adhesive sheet.  The plate thickness is
               NOT in this chain (the base top is one sheet thickness below the PCB underside, whatever the plate is)
      rim      tub rim above the base plane = plate + sheet + PCB - printed distance post foot to rim
      ball     epoxy between the ball top and its copper land = plate + sheet - ball top (set on the gauge plate)
    `printed` = tolerance of the printed tub dimension (default tol_printed, the drawing requirement; pass print_tol for
    the bureau's general tolerance).  Returns {name: dict(nominal, chain=[(item, +-mm)], rss, worst)}."""
    v = BASE_VARIANTS[key or BASE_KEY]
    tp = M["tol_printed"] if printed is None else printed
    sheet = (f"adhesive sheet {v['psa_t']}", v["psa_tol"])
    plate = (f"base plate ({v['key']})", v["tol"])
    pcb = ("PCB thickness", M["tol_pcb"])
    chains = dict(
        joint=(LEDGE_Z0 - v["thickness"], [(f"tub: post foot to seal face, printed {PCB_Z1 - LEDGE_Z0:.2f}", tp), pcb, sheet]),
        rim=(RIM_Z, [(f"tub: post foot to rim, printed {PCB_Z1 - RIM_Z:.2f}", tp), pcb, sheet, plate]),
        ball=(PCB_Z0 - BALL_TOP_Z, [plate, sheet, ("ball protrusion as set on the gauge plate", M["tol_ball_set"])]))
    out = {}
    for name, (nom, chain) in chains.items():
        out[name] = dict(nominal=nom, chain=chain, rss=math.sqrt(sum(t * t for _, t in chain)), worst=sum(t for _, t in chain))
    return out


def seal_dispense_volume(v_nominal, joint_area, key=None):
    """Seal adhesive to dispense (mm3): the joint at its upper RSS limit with the bureau's general print tolerance on the
    printed step, times seal_dispense_margin, rounded up to the next 5 mm3.  Returns (volume at the upper limit, to dispense)."""
    st = stack_tolerance(key, printed=M["print_tol"])["joint"]
    v_hi = v_nominal + joint_area * st["rss"]
    return v_hi, 5.0 * math.ceil(v_hi * M["seal_dispense_margin"] / 5.0)


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


def spigot_play(fit=None):
    """Play of the cameras that the two spigot fits allow (rev D: spigots under posts B, SPIGOT_SPAN apart, cameras between them).
    Returns dict(yaw_deg, side, fore_aft): +-mm sideways and fore-aft at the worse camera when each spigot uses its whole
    radial fit, the round hole also in x, the slot only in y."""
    f = SPIGOT_FIT if fit is None else fit
    xr, yr = LOC_ROUND[:2]
    xs = LOC_SLOT[0]
    yaw = 2 * f / SPIGOT_SPAN                            # rad: the two spigots at opposite ends of their fit in y
    side = fore = 0.0
    for cx, cy in CAM_XY.values():
        side = max(side, f + yaw * abs(cy - yr))         # shift in x plus the yaw about the round hole
        u = (cx - xr) / (xs - xr)                        # 0 at the round hole, 1 at the slot
        fore = max(fore, max(abs(a * f + (b - a) * f * u) for a in (-1, 1) for b in (-1, 1)))
    return dict(yaw_deg=math.degrees(yaw), side=side, fore_aft=fore, fit=f)


# ---------------------------------------------------------------------------------------------- cradle
# Rev D: body position, seat level, pad plane, pin heights, cradle PCB, lip and latch come from the YAML cradle block.
NEST_R = R_OUT + CLR                                  # 23.25
NEST_FLAT = Y_VISOR + CLR                             # 18.65 (the D flat is the orientation key)
NEST_FLOOR_Z = _cr["seat_z"]                          # -0.10: level of the front strip and of the two pads the ball feet rest on
CRADLE_TOP_Z = M["cradle_nest_wall_h"]                # 3.0
CRADLE_BOT_Z = CRADLE_TOP_Z - CRADLE_SIZE[2]          # -11.0
CRADLE_X = CRADLE_SIZE[0] / 2
CRADLE_Y0, CRADLE_Y1 = _cr["body"]["y"]               # -36.0 .. 24.0 (not centred on the marker: latch and USB need the room)
CRADLE_CY = 0.5 * (CRADLE_Y0 + CRADLE_Y1)
# The pins stand at their working height on the COPPER FACE of the pads (YAML cradle.pad_plane_z)
CPCB_Z1 = PAD_Z0 - PIN_WORK_H                         # -4.855 top face of the cradle PCB
CPCB_Z0 = CPCB_Z1 - CPCB_SIZE[2]
CPCB_HX = _cr["pcb"]["x"][1]                          # 15.0
CPCB_Y0, CPCB_Y1 = _cr["pcb"]["y"]                    # -34.2 .. -12.2
CPCB_SCREWS = sorted({(abs(x), y) for x, y in _cr["pcb"]["screws"]})   # [(12.5, -31.5), (12.5, -14.5)], each at +-x
PIN_TIP_FREE_Z = CPCB_Z1 + M["pin_max_working_h"]     # 2.105: free plunger tip above the marker base plane
PIN_BODY_Z1 = CPCB_Z1 + M["pin_max_working_h"] - M["pin_full_stroke"] - M["pin_body_margin"]   # -0.385 barrel top (PROVISIONAL)
PIN_COMPRESSION = M["pin_max_working_h"] - PIN_WORK_H     # 1.14 of the stroke used with the marker on its feet
PIN_FLOAT_H = PIN_WORK_H + M["cradle_float"]          # 6.07 pin height when the marker floats up against lip and hook
CRADLE_PIN_SLOT_W = M["pin_body_dia"] + 2 * CLR       # 2.33: drop-in clearance round the (PROVISIONAL) pin barrel
USB_Y0 = _cr["pcb"]["usb_mouth_y"]                    # -35.5 mouth of the receptacle (0.5 inside the rear face)
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
LIP_Z0 = T + M["lip_clearance"]                       # 7.85 underside
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
HOOK_Z0 = T + M["latch_clearance"]                    # 7.85 nose = lowest point of the retaining face
TUB_TOP_FLAT_R = R_OUT - M["top_fillet"]              # 22.4 where the flat top of the tub ends
M["latch_overhang"] = round(M["hook_overlap"] + NEST_R - TUB_TOP_FLAT_R, 6)   # 1.95: the nose lies hook_overlap on the flat top
M["latch_root_z"] = round(HOOK_Z0 - M["latch_free_length"], 6)                # -3.8: root of the cantilever (floor of the latch well)
HOOK_Y = LATCH_Y_FACE + M["latch_overhang"]           # -21.30 straight nose
HOOK_RAKE_TAN = math.tan(math.radians(M["hook_rake_deg"]))
HOOK_HEEL_Z = HOOK_Z0 + M["latch_overhang"] * HOOK_RAKE_TAN   # 8.34 the retaining face rises to the heel (negative rake)
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


def ko_post_squares():
    """The post-foot keep-out squares of the YAML contract as (name, x0, x1, y0, y1): six plain squares and the two larger
    squares of the locating posts.  The PCB layout keeps parts out of these; check 12 proves that the tub stays inside them."""
    out = []
    for i, (cx, cy) in enumerate(KO_POST_CENTRES):
        h = KO_POST_SIZE / 2
        out.append((M["post_names_plain"][i // 2] + ("+" if cx > 0 else "-"), cx - h, cx + h, cy - h, cy + h))
    for cx, cy in KO_LOC_CENTRES:
        h = KO_LOC_SIZE / 2
        out.append((M["locating_posts"] + ("+" if cx > 0 else "-"), cx - h, cx + h, cy - h, cy + h))
    return sorted(out, key=lambda r: (r[0][0], r[1]))


def post_rects():
    """Footprints of the support posts as BUILT, (name, x0, x1, y0, y1).  The plain posts fill their YAML squares.  The
    locating posts B cannot: the LCD glass (|x| <= LCD_X1) has to pass between them with the fit clearance, so each foot is
    cut back to |x| >= LCD_POCKET_X and stays inside its YAML square (deviation D29)."""
    out = []
    for name, x0, x1, y0, y1 in ko_post_squares():
        if name[0] == M["locating_posts"]:
            if x0 > 0:
                x0 = max(x0, LCD_POCKET_X)
            else:
                x1 = min(x1, -LCD_POCKET_X)
        out.append((name, x0, x1, y0, y1))
    return out


LOC_FOOT = next((x1 - x0, y1 - y0) for n, x0, x1, y0, y1 in post_rects() if n[0] == M["locating_posts"])   # (1.9, 2.2) as built


def resolved():
    """Every resolved number (YAML + mechanical-only + derived) for export/params_resolved.json."""
    skip = ("Y", "MECH", "M", "YAML_DRIVEN", "BASE", "BASE_VARIANTS", "_hs")
    derived = {k: v for k, v in globals().items()
               if k.isupper() and isinstance(v, (int, float, str, list, tuple, dict)) and k not in skip}
    variants = {}
    for k in BASE_VARIANTS:
        with base_variant(k):
            s1, s2 = epoxy_volumes()
            st, stb = stack_tolerance(), stack_tolerance(printed=M["print_tol"])
            variants[k] = dict(BASE_VARIANTS[k], seal_joint_height=BEAD_T, psa_z=(PSA_Z0, PSA_Z1), ball_hole_dia=BALL_HOLE_D,
                               ball_epoxy_stage1_mm3=round(s1, 3), ball_epoxy_stage2_mm3=round(s2, 3),
                               stack_tolerance={n: dict(nominal=round(c["nominal"], 3), rss=round(c["rss"], 3), worst=round(c["worst"], 3),
                                                        rss_with_bureau_print_tolerance=round(stb[n]["rss"], 3)) for n, c in st.items()},
                               potting_window_z=tuple(round(q, 3) for q in potting_window()))
    return dict(rev=REV, source=str(YAML_PATH), yaml=Y, active_base_variant=BASE_KEY, base_variants=variants,
                mechanical_only={k: v for k, v in MECH.items() if k not in YAML_DRIVEN and k not in ("pad_t", "latch_overhang", "latch_root_z")},
                from_yaml_under_mech_names=YAML_DRIVEN, derived=derived,
                posts=[dict(name=n, x0=a, x1=b, y0=c, y1=d) for n, a, b, c, d in post_rects()],
                post_keepout_squares=[dict(name=n, x0=a, x1=b, y0=c, y1=d) for n, a, b, c, d in ko_post_squares()],
                camera_play=spigot_play(), baffle_crest_range=baffle_crest_range(),
                hood_seal={k_: v_ for k_, v_ in hood_seal_section().items() if k_ != "pts"})


def write_resolved(path=None):
    path = pathlib.Path(path or EXPORT_DIR / "params_resolved.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(resolved(), indent=1, default=str))
    return path


# ---------------------------------------------------------------------------------------------- consistency of the YAML with the model
def _chk(cond, msg):
    if not cond:
        raise AssertionError("master_params.yaml and the mechanical model disagree: " + msg)


_chk(abs(PAD_SLOT_L - (PAD_XS[-1] - PAD_XS[0] + PAD_HOLE_D)) < 1e-9, "pad slot length does not match the pad row")
_chk(abs(PIN_ROW_Y - PAD_Y) < 1e-9 and PIN_POSITIONS == len(PAD_XS), "cradle pin row and pad row differ")
_chk(abs(NEST_FLOOR_Z + BALL_PROT) < 1e-9, "cradle.seat_z is not the plane of the ball feet")
_chk(abs(CG_BELOW_FLUSH - _c["sub_flush"]) < 1e-6, f"cover glass is {CG_BELOW_FLUSH:.3f} below flush, YAML says {_c['sub_flush']}")
_chk(abs(PCB_FREE_H - _p["max_top_height_under_lcd"]) < 1e-9, "free height above the PCB differs from pcb.max_top_height_under_lcd")
_chk(abs(KO_FREE_Z - FOAM_Z0) < 1e-9, "free height does not end at the underside of the foam pad")
_chk(abs(CRADLE_Y1 - CRADLE_Y0 - CRADLE_SIZE[1]) < 1e-9, "cradle.body.y does not span cradle.body.dy")
_chk(abs(LATCH_TOP_Z - CRADLE_BOT_Z - _cr["body"]["overall_height"]) < 0.01, f"cradle overall height {LATCH_TOP_Z - CRADLE_BOT_Z:.3f} vs YAML {_cr['body']['overall_height']}")
_chk(abs(CPCB_Z1 - _cr["pcb"]["top_z"]) < 1e-6, f"cradle PCB top {CPCB_Z1:.3f} vs YAML {_cr['pcb']['top_z']}")
_chk(abs(2 * CPCB_HX - CPCB_SIZE[0]) < 1e-9 and abs(CPCB_Y1 - CPCB_Y0 - CPCB_SIZE[1]) < 1e-9, "cradle.pcb x / y do not span dx / dy")
_chk(abs(PIN_COMPRESSION - _pins["compression"]) < 1e-6, "pin compression differs from the YAML")
_chk(_cr["print"]["build_direction"] == "x" and _cr["print"]["tumbling"] is False, "cradle print orientation differs from the model (x, not tumbled)")
_chk(sorted(FOOT_ZONES) == sorted(BALL_XY) and abs(FOOT_ZONE_D - FOOT_KEEPOUT_D) < 1e-9, "tub_keepouts.foot_zones differ from base_plate.feet")
_chk(all(abs(abs(cx) - abs(LOC_ROUND[0])) < 1e-9 and abs(cy - LOC_ROUND[1]) < 1e-9 for cx, cy in KO_LOC_CENTRES), "locating posts are not over the PCB locating holes")
_chk(abs(BAFFLE_RO - BAFFLE_RI - BAFFLE_WALL) < 1e-9, "baffle wall does not match its diameters")
_chk(abs(WIN_SUBFLUSH - (WIN_RECESS_DEPTH - WIN_T)) < 1e-9, "visor window is not seated on the recess floor")
_chk(BAT_JOINT_H <= PCB_FREE_H, "battery lead joint is taller than the free height above the PCB")
_chk(WIN_FRAME_BELOW_FACE > 0, "the sill fillet of the window adhesive would stand proud of the visor face")
_chk(min(HOOD_SEAL_WINDOW) > 0 and HOOD_SEAL_Y1 <= HOOD_FLAT_Y1 + 1e-9, "the hood gasket bead does not fit on the flat underside of the rear wall")
_chk(all(_v_["accept"][0] <= _v_["thickness"] <= _v_["accept"][1] for _v_ in BASE_VARIANTS.values()), "nominal plate thickness outside its incoming limits")

if __name__ == "__main__":
    print(write_resolved())
