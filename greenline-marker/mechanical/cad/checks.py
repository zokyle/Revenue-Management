"""GreenLine GL-1 automatic checks.

Every check takes the dict from assembly.build_parts() and returns
    dict(id, name, passed, summary, tables=[dict(title, rows)], notes=[...], warnings=[...])
run_all() runs them and writes export/check_report.json and export/check_report.md.

All results are computed, none are asserted: boolean commons and minimum distances on the B-rep solids that are
exported to STEP, exact ray casting on those solids, and ray casting / voxel analysis on the exported STL meshes.
A check FAILS when a requirement is violated and the violation is not a recorded deviation (cad/deviations.py);
recorded deviations are printed with their numbers and stay visible as warnings.

  1 interference        pairwise boolean common between all solids
  2 clearances          minimum-clearance table for the key pairs
  3 field of view       field frustum from the prism exit face to 200 mm against tub / base / other camera
  4 fold geometry       exact ray trace lens -> prism -> visor opening, vignetting and tolerance sensitivity
  5 wall thickness      ray-cast audit of the printed parts
  6 trapped volume      closed voids and cavities without a 2 mm escape path (voxel analysis)
  7 cradle              pins on the pads, orientation key, hold-down (retention incl. tolerance, latch strain by beam
                        formula and by plane-strain FE, both over-travel stops), posed insertion and release paths
  8 mass                mass and centre of gravity
  9 quoting             printed-part boxes / volumes and export integrity (STEP and STL re-read)
 10 support posts, 11 design/check_layout.py
 12 tub keep-outs       the YAML tub_keepouts contract proven on the tub solid
 13 seal continuity     air-solid test (outside and cavity must be separate), closed bead ring, seal land widths
 14 assembly paths      LCD tilt-in, PCB / base unit join (straight and hinged) posed against the tub
"""
from __future__ import annotations
import itertools, json, math, subprocess, sys, time
import numpy as np
import cadquery as cq
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from shapely.geometry import box as sbox, Point
import params as P
import parts as PT
import assembly as A
import geom as G
import optics as O
import holddown as H
import latchfe as FE
from deviations import DEVIATIONS, OPEN as DEV_OPEN, CLOSED as DEV_CLOSED

M = P.MECH
INTERFERENCE_LIMIT_MM3 = 0.01
CONTACT_TOL = 1e-4
NUM_TOL = 2e-3             # numerical tolerance of every comparison against a minimum (mm)
USE_EXPORTED = True          # read the STL / STEP files written by this build (build.py clears this for --no-export)
R3 = lambda v: None if v is None else round(float(v), 3)


def res(id, name, passed, summary, tables=(), notes=(), warnings=()):
    return dict(id=id, name=name, passed=bool(passed), summary=summary, tables=list(tables), notes=list(notes),
                warnings=list(warnings))


def _bb_overlap(a, b, tol=0.05):
    return all(a[i] - tol <= b[i + 3] and b[i] - tol <= a[i + 3] for i in range(3))


def min_distance(sa, sb):
    d = BRepExtrema_DistShapeShape(G.as_shape(sa).wrapped, G.as_shape(sb).wrapped)
    d.Perform()
    return d.Value() if d.IsDone() else float("nan")


def common_volume(sa, sb):
    try:
        c = G.as_shape(sa).intersect(G.as_shape(sb))
        return sum(s.Volume() for s in c.Solids())
    except Exception:                                        # a failed boolean is reported, never hidden
        return float("nan")


def _key(a, b, table):
    return (a, b) if (a, b) in table else ((b, a) if (b, a) in table else None)


def _solids(parts):
    return {n: A.solid_of(i) for n, i in parts.items()}


def _tris(parts, name, print_orientation=False):
    """Triangles of a part: the exported STL when this build wrote it, otherwise the same tessellation in memory."""
    f = (A.STL_PRINT_DIR / f"{name}_print.stl") if print_orientation else (A.STL_PARTS_DIR / f"{name}.stl")
    if USE_EXPORTED and f.exists():
        return G.load_stl(f), str(f.relative_to(P.MECH_DIR))
    shape = A.print_orientation(name, parts[name].shape).val() if print_orientation else A.solid_of(parts[name])
    vs, ts = shape.tessellate(*((A.PRINT_STL_TOL, A.PRINT_STL_ANG) if print_orientation else (A.STL_TOL, A.STL_ANG)))
    v = np.array([p.toTuple() for p in vs])
    return v[np.array(ts)], "in-memory tessellation (no export in this run)"


# ==============================================================================================
# 1. interference
# ==============================================================================================
def check_interference(parts):
    """Pairwise boolean intersection between ALL solids of the assembly (puck seated in the cradle at 0 deg)."""
    names = list(parts)
    solids = _solids(parts)
    bbs = {n: A.bbox_of(parts[n]) for n in names}
    rows, fails, contacts_seen = [], [], set()
    n_pairs = n_tested = 0
    for a, b in itertools.combinations(names, 2):
        n_pairs += 1
        if not _bb_overlap(bbs[a], bbs[b]):
            continue
        n_tested += 1
        vol = common_volume(solids[a], solids[b])
        dist = min_distance(solids[a], solids[b])
        mk = _key(a, b, A.MODELLING_OVERLAPS)
        ck = _key(a, b, A.INTENDED_CONTACTS)
        status = "clear"
        if vol != vol:
            status = "BOOLEAN FAILED"; fails.append((a, b, status))
        elif vol > INTERFERENCE_LIMIT_MM3:
            if mk:
                status = "allowed modelling overlap"
            else:
                status = "INTERFERENCE"; fails.append((a, b, f"{vol:.4f} mm3"))
        elif dist < CONTACT_TOL:
            status = "intended contact" if ck else "contact (not on the list)"
            contacts_seen.add(ck or (a, b))
        if status != "clear":
            rows.append(dict(a=a, b=b, common_volume_mm3=round(vol, 5), min_distance_mm=round(dist, 5), status=status,
                             reason=(A.MODELLING_OVERLAPS.get(mk) if mk else A.INTENDED_CONTACTS.get(ck, ""))))
    missing = [k for k in A.INTENDED_CONTACTS if k not in contacts_seen and k[0] in parts and k[1] in parts]
    unlisted = [r for r in rows if r["status"] == "contact (not on the list)"]
    notes = [f"{n_pairs} pairs; {n_tested} with overlapping bounding boxes tested by boolean common and minimum distance; "
             f"limit {INTERFERENCE_LIMIT_MM3} mm3",
             "allow-list of intended contacts: cad/assembly.py (INTENDED_CONTACTS); rev C has no modelling overlap - the adhesive sheet "
             f"occupies its own {P.PSA_T} mm between base plate and PCB"]
    warns = []
    if missing:
        warns.append("intended contacts that do NOT touch in the model: " + ", ".join(f"{a}/{b}" for a, b in missing))
    if unlisted:
        warns.append("zero-volume contacts not on the intended list: " + ", ".join(f"{r['a']}/{r['b']}" for r in unlisted))
    n_over = sum(r["status"] == "allowed modelling overlap" for r in rows)
    return res(1, "interference", not fails,
               (f"no unintended interference in {n_tested} tested pairs ({n_pairs} total); "
                f"{sum(r['status'] == 'intended contact' for r in rows)} intended zero-volume contacts, {n_over} modelling overlaps"
                if not fails else f"{len(fails)} failing pairs: {fails}"),
               [dict(title="Contacts and overlaps (every pair not listed is clear)", rows=rows)], notes, warns)


# ==============================================================================================
# 2. clearances
# ==============================================================================================
def _sec_dist(a, b, axis, value, clip=None):
    pa, pb = G.section_polys(a, axis, value, 2e-4), G.section_polys(b, axis, value, 2e-4)
    if clip is not None:
        c = sbox(*clip)
        pa, pb = pa.intersection(c), pb.intersection(c)
    if pa.is_empty or pb.is_empty:
        return float("nan")
    return pa.distance(pb)


_CACHE = {}


def _cradle_without_latch():
    """Cradle body with the lip but without the latch (cached): what the marker must clear while the latch is deflected."""
    if "body_nl" not in _CACHE:
        _CACHE["body_nl"] = PT.cradle(with_latch=False).val()
    return _CACHE["body_nl"]


def _top_part_boxes():
    out = {}
    for p in P.TOP_PARTS:
        z1 = P.PCB_Z1 + p["h"]
        out[p["ref"]] = (p, PT.box(p["x"] - p["dx"] / 2, p["x"] + p["dx"] / 2, p["y"] - p["dy"] / 2, p["y"] + p["dy"] / 2,
                                   P.PCB_Z1, z1).val())
    return out


def check_clearances(parts):
    S = _solids(parts)
    tub = S["tub"]
    rows, fails, warns = [], [], []
    clr = P.CLR

    def add(item, actual, minimum, nominal=None, dev=None, method="3D minimum distance", note=""):
        if actual != actual:
            status = "FAIL: not computed"
        elif nominal is not None and abs(actual - nominal) > 0.01:
            status = f"FAIL: model {actual:.3f} differs from nominal {nominal:.3f}"
        elif actual >= minimum - NUM_TOL:
            status = "ok"
        elif dev:
            status = f"below the {minimum} rule - recorded deviation {dev}"
            warns.append(f"{item}: {actual:.3f} mm < {minimum} mm ({dev})")
        else:
            status = f"FAIL: below minimum {minimum}"
        if status.startswith("FAIL"):
            fails.append(item)
        rows.append(dict(item=item, method=method, actual_mm=R3(actual), required_min_mm=R3(minimum),
                         margin_mm=R3(actual - minimum) if actual == actual else None, status=status, note=note))

    zg = 0.5 * (P.LCD_Z0 + P.LCD_Z1)
    # --- display stack against the cameras
    for s in ("L", "R"):
        add(f"LCD glass to camera cube {s}", min_distance(S["lcd_glass"], S[f"camera_{s}"]), clr)
        add(f"LCD glass to prism {s}", min_distance(S["lcd_glass"], S[f"prism_{s}"]), clr)
    add("LCD glass to tub, lateral (ribs, posts E, hood rear walls)", _sec_dist(S["lcd_glass"], tub, "z", zg), clr, nominal=clr,
        method=f"section z = {zg:.3f}")
    add("LCD glass to roof bonding plane (adhesive frame)", min_distance(S["lcd_glass"], tub), P.LCD_PSA_T, nominal=P.LCD_PSA_T)
    add("LCD glass rear corners to side wall", P.R_IN - math.hypot(P.LCD_X1, P.LCD_Y0), clr, method="radius of the glass corner vs wall R",
        note=f"corner r = {math.hypot(P.LCD_X1, P.LCD_Y0):.3f}; the same corners do NOT pass the seating ledge (r {P.LEDGE_RI}): see D11")
    # --- battery
    bat = P.BAT
    add("Battery to foam pad", min_distance(S["battery"], S["foam_pad"]), P.BAT_SWELL, nominal=P.FOAM_Z0 - bat["z1"],
        note=f"swell allowance {P.BAT_SWELL}: {P.FOAM_Z0 - bat['z1'] - P.BAT_SWELL:.2f} mm left when fully swollen")
    add("Battery to LCD glass", min_distance(S["battery"], S["lcd_glass"]), P.BAT_SWELL + P.FOAM_T, nominal=P.LCD_Z0 - bat["z1"])
    add("Battery to tub (posts, ledge)", min_distance(S["battery"], tub), clr)
    add("Foam pad to tub", min_distance(S["foam_pad"], tub), clr)
    # --- PCB and base against the tub
    board = PT.pcb_board().val()
    zl = 0.5 * (max(P.LEDGE_Z0, P.PCB_Z0) + min(P.LEDGE_Z1, P.PCB_Z1))
    add("PCB edge to seating ledge, radial", _sec_dist(board, tub, "z", zl, clip=(-25, -25, 25, 12)), clr, nominal=P.LEDGE_RI - P.PCB_R,
        method=f"section z = {zl:.2f}", note="rev C: PCB radius 21.1")
    zs = 0.5 * (P.SPIGOT_Z0 + P.PCB_Z1)
    rx, ry, _ = P.LOC_ROUND; sx, sy, sd, sl = P.LOC_SLOT
    add("PCB locating spigot in the round hole, radial", _sec_dist(board, tub, "z", zs, clip=(rx - 1.5, ry - 1.5, rx + 1.5, ry + 1.5)), clr,
        nominal=P.SPIGOT_FIT, dev="D19", method=f"section z = {zs:.2f}", note="locating fit specified in the YAML, not a drop-in fit")
    add("PCB locating spigot in the slot, across the slot (y)", _sec_dist(board, tub, "z", zs, clip=(sx - 1.5, sy - 1.5, sx + 1.5, sy + 1.5)), clr,
        nominal=(sd - P.SPIGOT_D) / 2, dev="D19", method=f"section z = {zs:.2f}", note=f"along the slot (x): {(sl - P.SPIGOT_D) / 2:.3f} mm each way")
    add("Spigot tip to the adhesive sheet", P.SPIGOT_Z0 - A.bbox_of(parts["pcb_adhesive"])[5], 0.1, nominal=P.SPIGOT_Z0 - P.PSA_Z1, method="bounding boxes",
        note="the spigot ends inside the PCB hole")
    add("PCB flat edge to visor wall", _sec_dist(board, tub, "z", zl, clip=(-3, 15.5, 3, 20)), clr, nominal=P.Y_VISOR_IN - P.PCB_FLAT,
        method=f"section z = {zl:.2f}, |x| < 3")
    add("Base plate to tub side wall, radial", _sec_dist(S["base_plate"], tub, "z", 0.5 * (P.RIM_Z + P.BASE_T)), clr, nominal=clr,
        method=f"section z = {0.5 * (P.RIM_Z + P.BASE_T):.2f}", note="groove filled with seal adhesive; no key, no notch in the seal land")
    add("Tub rim above the base plane (rim relief)", A.bbox_of(parts["tub"])[2] - A.bbox_of(parts["base_plate"])[2], P.RIM_Z, nominal=P.RIM_Z,
        method="bounding boxes", note=f"base plate and ball feet are the lowest surfaces: the rim is {P.RIM_Z + P.BALL_PROT:.2f} mm above the ball plane (D23)")
    bead = G.RayCaster(tub).first_hit((0.0, -0.5 * (P.LAND_RI + P.BASE_R), P.BASE_T + 1e-6), (0, 0, 1), 1e-9, 5.0)
    add("Base plate top to tub seal face (adhesive bead)", (bead or float("nan")) + 1e-6, P.BEAD_T, nominal=P.BEAD_T,
        method="ray +z from the seal land", note="rev C: 0.87 mm plate, bead 0.33 mm")
    add("Ball foot top to the PCB underside", min_distance(S["ball_1"], S["main_pcb"]), 0.05, nominal=P.PCB_Z0 - P.BALL_TOP_Z,
        note="the ball stands 0.03 above the plate inside the 2.0 mm hole of the adhesive sheet")
    add("Potting epoxy to the PCB underside (sheet hole backfilled)", min_distance(S["ball_epoxy_1"], S["main_pcb"]), 0.0, nominal=0.0,
        note=f"stage 1 dome at most {M['epoxy_dome_max']} mm over the plate; stage 2 fills the 2.0 mm sheet hole, so the ball bears on the PCB through "
             f"{P.PCB_Z0 - P.BALL_TOP_Z:.2f} mm of epoxy in compression")
    # --- cover glass
    zc = 0.5 * (P.CG_Z0 + P.CG_Z1)
    add("Cover glass to recess wall, radial", _sec_dist(S["cover_glass"], tub, "z", zc), clr, nominal=(P.RECESS_D - P.CG_D) / 2,
        method=f"section z = {zc:.2f}")
    add("Cover glass underside to recess floor (tape ring)", min_distance(S["cover_glass"], tub), P.CG_TAPE_T, nominal=P.CG_TAPE_T)
    add("Cover glass top below the tub top (sub-flush)", P.T - A.bbox_of(parts["cover_glass"])[5], 0.0, nominal=P.CG_BELOW_FLUSH,
        method="bounding box")
    # --- cameras / prisms / windows against the tub
    for s in ("L", "R"):
        cx, cy = P.CAM_XY[s]
        add(f"Camera cube {s} to hood (sides, top, front pad)", min_distance(S[f"camera_{s}"], tub), clr, nominal=clr)
        rc = G.RayCaster(tub)
        up = rc.first_hit((cx, P.PRISM_EXIT_Y - 0.01, P.PRISM_Z1), (0, 0, 1), 1e-6, 5.0)
        add(f"Prism {s} top to roof underside", up if up else float("nan"), P.PRISM_ROOF_CLR, nominal=P.PRISM_ROOF_CLR,
            method="ray +z from the prism top edge", note="YAML stack value (below the 0.25 drop-in rule by specification)")
        add(f"Prism {s} to tub, any direction", min_distance(S[f"prism_{s}"], tub), P.PRISM_ROOF_CLR)
        rear = tub.intersect(PT.box(cx - 3, cx + 3, P.HOOD_REAR_Y0 - 0.1, P.HOOD_REAR_Y1 + 0.01, P.CAM_Z1, P.ROOF_Z - 0.3).val())
        add(f"Prism {s} hypotenuse to hood rear wall", min_distance(S[f"prism_{s}"], rear), clr, nominal=P.PRISM_HOOD_CLR,
            note="rear wall edge chamfered")
        add(f"Prism {s} to hood walls in the horizontal plane", _sec_dist(S[f"prism_{s}"], tub, "z", P.AXIS_Z), clr,
            method=f"section z = {P.AXIS_Z:.2f}")
        w = S[f"visor_window_{s}"]
        add(f"Visor window {s} to recess sides", _sec_dist(w, tub, "y", P.Y_VISOR - P.WIN_T / 2, clip=(cx - 5, P.WIN_Z0 + 0.3, cx + 5, P.T)),
            clr, nominal=(P.WIN_RECESS_W - P.WIN_W) / 2, method="section through the window, above the shelf")
        add(f"Visor window {s} rear face to recess floor (bond line)",
            _sec_dist(w, tub, "z", 0.5 * (P.WIN_Z0 + P.OPEN_Z0), clip=(cx - 1.5, 15, cx + 1.5, 20)), M["window_bond"], nominal=M["window_bond"],
            method="section below the opening")
        add(f"Hood gasket bead {s} to the prism", min_distance(S[f"hood_seal_{s}"], S[f"prism_{s}"]), 0.1,
            note=f"bead {M['hood_seal_w']} wide on the flat underside of the rear wall, dispensed {M['hood_seal_free_h']} high and cured before the join")
    # --- vent, flex, bottom-side parts
    others = [n for n, i in parts.items() if i.group == "puck" and n not in ("tub", "vent")]
    dv, nv = min((min_distance(S["vent"], S[n]), n) for n in others)
    add(f"Vent disc to nearest part ({nv})", dv, clr)
    add("LCD flex (representative shape) to tub", min_distance(S["lcd_flex"], tub), 0.0, note="PROVISIONAL tail geometry")
    add("LCD flex (representative shape) to connector J1 / PCB parts", min_distance(S["lcd_flex"], S["main_pcb"]), 0.0, nominal=0.0,
        note=f"PROVISIONAL tail geometry: one U-fold of radius {P.FLEX_BEND_R:.2f} mm, modelled up to the J1 mouth face (entry {M['fpc_entry_h']} mm above the PCB)")
    pd = P.PD
    pdbox = PT.box(pd["x"] - pd["dx"] / 2, pd["x"] + pd["dx"] / 2, pd["y"] - pd["dy"] / 2, pd["y"] + pd["dy"] / 2, P.PCB_Z0 - pd["h"], P.PCB_Z0).val()
    add("Photodiode body to baffle ring", min_distance(pdbox, S["base_plate"]), clr, nominal=P.BAFFLE_RI - P.PD_HALF_DIAG,
        note="the YAML rounds the ring to 5.91 (0.249)")
    dled = min(min_distance(b.val(), S["base_plate"]) for b in PT.led_boxes())
    add("Grain LEDs to opening wall / baffle / spokes", dled, clr)
    # --- cradle (rev C: nest floor, lip, latch, one pin slot)
    cr = S["cradle"]
    lipS, latchS, body_nl = PT.lip().val(), PT.latch().val(), _cradle_without_latch()
    add("Marker to nest wall, radial", _sec_dist(tub, cr, "z", 1.5), clr, nominal=clr, method="section z = 1.5")
    add("Base plate underside above the nest strip and pads (ball protrusion)", min_distance(S["base_plate"], cr), P.BALL_PROT, nominal=P.BALL_PROT,
        note="the three balls carry the marker on the front strip and the two pads; the rest of the nest floor is a drained basin")
    ang = math.radians(50.0)
    rim = G.RayCaster(cr).first_hit(((P.R_OUT - 0.15) * math.cos(ang), (P.R_OUT - 0.15) * math.sin(ang), P.RIM_Z), (0, 0, -1), 1e-9, 5.0)
    add("Tub rim above the nest strip", rim if rim is not None else float("nan"), P.RIM_Z + P.BALL_PROT, nominal=P.RIM_Z + P.BALL_PROT,
        method="ray -z from the rim at 50 deg")
    add("Lip underside to the tub top", min_distance(tub, lipS), clr, nominal=clr)
    add("Latch (retaining face and beam) to the tub", min_distance(tub, latchS), clr, nominal=clr)
    for sd_ in ("L", "R"):
        add(f"Lip to visor window {sd_}", min_distance(lipS, S[f"visor_window_{sd_}"]), clr, note="the lip must not touch the windows")
    add("Lip to cover glass", min_distance(lipS, S["cover_glass"]), clr)
    add("Latch hook to cover glass", min_distance(latchS, S["cover_glass"]), clr)
    vh = PT.cyl(P.VENT_XY[0], P.VENT_XY[1], P.VENT_HOLE_D / 2, P.T - 0.5, P.T + 0.5).val()
    add("Lip to the vent hole", min_distance(lipS, vh), clr)
    add("Latch to the vent hole", min_distance(latchS, vh), clr)
    add("Latch to the walls of its well (side gaps, stop ribs)", _sec_dist(latchS, body_nl, "z", 1.0), 0.5, nominal=M["latch_side_gap"],
        method="section z = 1.00", note=f"minimum printable gap taken as 0.5 mm; front gap {M['latch_front_gap']}, stop ribs {P.LATCH_STOP_GAP:.2f} behind the beam at their top")
    add("Spring-pin plunger to base-plate slot, radial", _sec_dist(S["spring_pin_4"], S["base_plate"], "z", 0.5 * P.BASE_T), clr,
        nominal=(P.PAD_HOLE_D - M["pin_plunger_dia"]) / 2, method=f"section z = {0.5 * P.BASE_T:.3f}", note="pin diameters PROVISIONAL")
    zb = 0.5 * (P.CPCB_Z1 + P.PIN_BODY_Z1)
    add("Spring-pin barrel to printed pin slot, radial", _sec_dist(S["spring_pin_1"], cr, "z", zb), clr, nominal=clr,
        method=f"section z = {zb:.2f}")
    zq = 0.5 * (P.CPCB_Z0 + P.CPCB_Z1)
    add("Cradle PCB to pocket walls", _sec_dist(S["cradle_pcb"], cr, "z", zq), clr, nominal=clr, method=f"section z = {zq:.2f}")
    add("USB receptacle shell to printed pocket", min_distance(S["usb_receptacle"], cr), clr, note="envelope PROVISIONAL")

    # --- table 2b: every top-side part of the YAML
    prow = []
    lcdfoam = [S["lcd_glass"], S["foam_pad"]]
    for ref, (p, bx) in _top_part_boxes().items():
        if ref == "BT1":
            continue
        d_tub = min_distance(bx, tub)
        d_lcd = min(min_distance(bx, s) for s in lcdfoam)
        d_bat = min_distance(bx, S["battery"]) if ref not in ("U2", "U3") else None
        ok = d_tub >= clr - NUM_TOL and d_lcd >= clr - NUM_TOL and (d_bat is None or d_bat >= 0.2 - NUM_TOL)
        if not ok:
            fails.append(f"{ref} clearance")
        prow.append(dict(ref=ref, part=p["name"], top_z=R3(P.PCB_Z1 + p["h"]), to_tub_mm=R3(d_tub), to_lcd_glass_or_foam_mm=R3(d_lcd),
                         to_battery_mm=R3(d_bat), status="ok" if ok else "FAIL"))
    notes = ["required minimum = 0.25 mm drop-in rule unless the row is a specified stack value (adhesive lines, prism-to-roof 0.19)",
             "passives are not in master_params.yaml, so only the 13 listed top-side parts are checked",
             "sections are true boolean sections of the solids; curved edges are sampled to 0.0002 mm",
             f"comparisons carry a numerical tolerance of {NUM_TOL} mm"]
    worst = min((r for r in rows if r["margin_mm"] is not None), key=lambda r: r["margin_mm"])
    return res(2, "clearances", not fails,
               (f"{len(rows)} key gaps and {len(prow)} PCB parts evaluated; {len(warns)} below the 0.25 mm rule are recorded deviations; "
                f"smallest margin {worst['margin_mm']} mm ({worst['item']})" if not fails else f"FAILED: {fails}"),
               [dict(title="Key clearances", rows=rows), dict(title="PCB top-side parts (envelope boxes from the YAML)", rows=prow)],
               notes, warns)


# ==============================================================================================
# 3. field of view
# ==============================================================================================
def check_fov(parts):
    S = _solids(parts)
    rows, fails, warns = [], [], []
    for side in ("L", "R"):
        other = "R" if side == "L" else "L"
        required = ["tub", "base_plate", "seal_bead", f"camera_{other}", f"prism_{other}", f"visor_window_{other}"]
        for full in (False, True):
            fr = O.frustum_solid(side, full)
            rn, yn, rf, yf = O.frustum_rects(side, full)
            for name, info in parts.items():
                if info.group != "puck" or name == f"prism_{side}":
                    continue
                v = common_volume(fr, S[name])
                own_window = name == f"visor_window_{side}"
                if name in required or v > 1e-9 or v != v:
                    bad = (v != v) or (v > 1e-6 and not own_window)
                    if bad:
                        fails.append(f"camera {side} {'full beam' if full else 'chief rays'} hits {name}: {v:.5f} mm3")
                    rows.append(dict(camera=side, frustum="full pupil beam" if full else "chief rays", against=name,
                                     common_volume_mm3=round(v, 6),
                                     status=("passes through its own window (transparent)" if own_window and v > 0 else
                                             ("clear" if not bad else "OBSTRUCTED"))))
    # unobstructed angles by exact ray casting
    rc = G.RayCaster(S["tub"])
    spec = dict(left=M["fov_h_half_deg"], right=M["fov_h_half_deg"], up=M["fov_up_deg"], down=M["fov_down_deg"])
    arows = []
    for side in ("L", "R"):
        for d in ("left", "right", "up", "down"):
            ac, wc = O.limit_angle(side, d, rc, False)
            af, wf = O.limit_angle(side, d, rc, True)
            if ac < spec[d]:
                fails.append(f"camera {side} chief ray blocked at {ac:.2f} deg {d} (< {spec[d]})")
            if af < spec[d]:
                warns.append(f"camera {side} {d}: the full {M['pupil_dia']} mm pupil is clear only to {af:.2f} deg (field edge {spec[d]} deg): "
                             f"partial vignetting by the {wf}, quantified in check 4")
            arows.append(dict(camera=side, direction=d, specified_deg=spec[d], chief_ray_clear_to_deg=round(ac, 2), chief_limited_by=wc,
                              full_pupil_clear_to_deg=round(af, 2), full_pupil_limited_by=wf,
                              chief_margin_deg=round(ac - spec[d], 2), full_pupil_margin_deg=round(af - spec[d], 2)))
    rn, yn, rf, yf = O.frustum_rects("R", False)
    cx = P.CAM_XY["R"][0]
    turf = P.AXIS_Z / math.tan(math.radians(M["fov_down_deg"]))
    down_full = min(r["full_pupil_clear_to_deg"] for r in arows if r["direction"] == "down")
    notes = [f"frustum: ruled solid between the bounding rectangle of the traced rays on the exit-face plane (y = {yn}) and on the plane 200 mm in front of it; "
             f"chief-ray rectangle at the exit face x = cam x {rn[0] - cx:+.3f}..{rn[1] - cx:+.3f}, z = {rn[2]:.3f}..{rn[3]:.3f}",
             "rays are traced exactly through the prism (optics.py); the entrance-pupil position and diameter are ASSUMED",
             "'left/right' = toward -x/+x, 'up/down' = toward +z/-z in object space",
             f"the lower field edge ({M['fov_down_deg']} deg) meets the base plane about {turf:.1f} mm in front of the virtual pupil - turf, not a part",
             "the visor windows are treated as transparent plates (the 0.5 mm plate shifts a 26 deg ray by about 0.09 mm; not modelled)",
             f"rev C: the lower field is required only to -{M['fov_down_deg']} deg (flagstick base near the horizon); the sill stays at z {P.OPEN_Z0} and the "
             f"full pupil is in fact clear to -{down_full:.1f} deg (the sensor could use -{M['fov_down_sensor_deg']} deg)"]
    return res(3, "field of view", not fails,
               ("field frusta (chief rays and full pupil beam, both cameras) have zero intersection with tub, base, seal bead and the other "
                "camera's parts; chief rays are clear to "
                + ", ".join(f"{d} {min(r['chief_ray_clear_to_deg'] for r in arows if r['direction'] == d):.1f}" for d in ("left", "right", "up", "down"))
                + " deg" if not fails else "FAILED: " + "; ".join(fails)),
               [dict(title="Frustum intersections (exit face to 200 mm)", rows=rows),
                dict(title="Unobstructed angles from the optical axis (exact ray casting against the tub)", rows=arows)], notes, warns)


# ==============================================================================================
# 4. fold geometry
# ==============================================================================================
def check_fold(parts):
    S = _solids(parts)
    rc = G.RayCaster(S["tub"])
    rows, fails, warns = [], [], []
    yf = P.WIN_RECESS_FLOOR_Y
    m_edge = [float("inf")] * 3                              # smallest bundle margin to the opening: sides, sill, top
    for side in ("L", "R"):
        cx = P.CAM_XY[side][0]
        for name, th, tv in O.field_points():
            b = O.bundle(side, th, tv, rc, n_rim=48, n_rings=8)
            c = b["chief"]
            offs, rim = O.pupil_samples(48, 1)
            m_open = float("inf")
            for o in offs:                                   # footprint of the bundle on the aperture plane (recess floor)
                tr = O.trace(side, th, tv, o)
                if tr.get("d_out") is None:
                    continue
                q = O.at_plane_y(tr, yf)
                m3 = (P.OPEN_HALF_W - abs(q[0] - cx), q[2] - P.OPEN_Z0, P.OPEN_Z1 - q[2])
                m_edge = [min(a_, b_) for a_, b_ in zip(m_edge, m3)]
                m_open = min(m_open, *m3)
            if not b["chief_ok"]:
                fails.append(f"camera {side} {name}: chief ray clipped at {c['clipped_at'] or 'the visor opening'}")
            if b["total_fraction"] < 1.0:
                warns.append(f"camera {side} {name}: {100 * (1 - b['total_fraction']):.1f} % of the pupil is vignetted ({', '.join(b['blocked'])})")
            q = O.at_plane_y(c, yf)
            rows.append(dict(camera=side, field_point=name, h_deg=round(math.degrees(math.atan(th)), 1), v_deg=round(math.degrees(math.atan(tv)), 1),
                             chief_at_exit_face_xz=(round(c["p_exit"][0] - cx, 3), round(c["p_exit"][2] - P.AXIS_Z, 3)),
                             chief_at_opening_xz=(round(q[0] - cx, 3), round(q[2] - P.AXIS_Z, 3)),
                             margin_entrance_face_mm=R3(b["m_entrance"]), margin_hypotenuse_mm=R3(b["m_hypotenuse"]),
                             margin_exit_face_mm=R3(b["m_exit"]), margin_visor_opening_mm=R3(m_open),
                             chief_ray="clear" if b["chief_ok"] else "CLIPPED",
                             pupil_through_prism_pct=round(100 * b["prism_fraction"], 1), pupil_through_visor_pct=round(100 * b["total_fraction"], 1)))
    # tolerance sensitivity: move camera + prism relative to the tub.  Rev C: the PCB is located by the two spigots under
    # posts E, so its play is the spigot fit, amplified at the cameras by the yaw that the two fits allow
    fit = P.SPIGOT_FIT
    span = P.LOC_SLOT[0] - P.LOC_ROUND[0]
    cyr = P.CAM_XY["R"][1]

    def play(f):
        yaw = 2 * f / span                                   # rad, both spigots at opposite ends of their fit in y
        return f + yaw * abs(cyr - P.LOC_ROUND[1]), f + yaw * (P.CAM_X - P.LOC_SLOT[0]), math.degrees(yaw)
    dx, dy, yaw_deg = play(fit)
    dx2, dy2, yaw2 = play(0.125)
    cases = [("nominal", (0, 0, 0)),
             (f"PCB at the end of its spigot play: optics {dx:.3f} sideways", (dx, 0, 0)),
             (f"spigot play plus 0.2 print tolerance: {dx + 0.2:.3f} sideways", (dx + 0.2, 0, 0)),
             (f"spigot yaw play ({yaw_deg:.2f} deg): optics {dy:.3f} toward the visor", (0, dy, 0)),
             (f"spigot yaw play: optics {dy:.3f} away from the visor", (0, -dy, 0)),
             ("optics 0.2 low (print tolerance on the sill)", (0, 0, -0.2)), ("optics 0.2 high (print tolerance on the roof)", (0, 0, 0.2)),
             (f"proposal B: dia 1.25 PCB hole (0.125 fit) plus 0.2 print: {dx2 + 0.2:.3f} sideways", (dx2 + 0.2, 0, 0)),
             (f"proposal B: dia 1.25 PCB hole, yaw play ({yaw2:.2f} deg): optics {dy2:.3f} away from the visor", (0, -dy2, 0))]
    srows = []
    for label, sh in cases:
        lim = {d: O.limit_angle("R", d, rc, True, shift=sh)[0] for d in ("left", "right", "up", "down")}
        limc = {d: O.limit_angle("R", d, rc, False, shift=sh)[0] for d in ("left", "right", "up", "down")}
        worst = min(O.bundle("R", th, tv, rc, shift=sh, n_rim=48, n_rings=8)["total_fraction"] for _, th, tv in O.field_points())
        srows.append(dict(case=label, shift_xyz=tuple(round(v, 3) for v in sh),
                          full_pupil_clear_deg_left_right_up_down=tuple(round(lim[d], 1) for d in ("left", "right", "up", "down")),
                          chief_clear_deg_left_right_up_down=tuple(round(limc[d], 1) for d in ("left", "right", "up", "down")),
                          worst_field_point_transmission_pct=round(100 * worst, 1)))
    nom = [r for r in rows if r["camera"] == "R"]
    worst_nom = min(r["pupil_through_visor_pct"] for r in nom)
    m_open_min = min(r["margin_visor_opening_mm"] for r in rows)
    if m_edge[2] < 0.2:
        warns.append(f"the upper field edge (+{M['fov_up_deg']} deg) clears the top of the opening (the roof underside, z {P.OPEN_Z1}) by only {m_edge[2]:.3f} mm: "
                     "optics 0.2 mm high clip the upper field (sensitivity table). The roof cannot move without a thicker puck (open issue)")
    if m_edge[0] < 0.2 or m_edge[1] < 0.2:
        warns.append(f"bundle margin to the opening sides {m_edge[0]:.3f} mm / sill {m_edge[1]:.3f} mm is below the 0.2 mm print tolerance")
    notes = [f"entrance pupil ASSUMED: dia {M['pupil_dia']} mm, {M['pupil_below_cube_top']} mm below the cube top (z = {P.PUPIL_Z:.2f}); prism n = {O.N_GLASS}, "
             f"legs {P.PRISM_LEG}, bond gap {P.PRISM_BOND}; hypotenuse aluminised (reflects at any angle)",
             "margins are the smallest distance of any ray of the pupil bundle to the edge of that aperture (negative = clipped); "
             "the visor margin is taken on the aperture plane (window-recess floor)",
             "field points are rectilinear: direction (tan h, 1, tan v)",
             f"paraxial check: virtual pupil {P.VIRTUAL_PUPIL_BEHIND_EXIT:.3f} mm behind the exit face (y = {P.VIRTUAL_PUPIL_Y:.3f}), z = {P.AXIS_Z:.2f}",
             "sensitivity cases move the camera and prism together relative to the printed tub (camera R; L is the mirror image)",
             f"PCB location (rev C): spigots dia {P.SPIGOT_D} in a dia {P.LOC_ROUND[2]} hole and a {P.LOC_SLOT[2]} x {P.LOC_SLOT[3]} slot, {span} mm apart: +-{fit:.3f} mm "
             f"at each spigot gives +-{dx:.3f} mm sideways and +-{dy:.3f} mm fore-aft at a camera and +-{yaw_deg:.2f} deg of yaw (a stereo-calibration "
             "item, not a vignetting item)",
             f"smallest margin of the full pupil bundle to the opening over the required field: sides {m_edge[0]:.3f}, sill {m_edge[1]:.3f}, top {m_edge[2]:.3f} mm",
             f"required field: +-{M['fov_h_half_deg']} deg horizontal, +{M['fov_up_deg']} / -{M['fov_down_deg']} deg vertical (rev C: lower field to about -8 deg)"]
    return res(4, "fold geometry", not fails,
               (f"chief rays of all nine field points pass the prism and the visor opening on both cameras; pupil transmission at the worst "
                f"nominal field point {worst_nom:.1f} % (prism exit face); bundle margin to the opening: sides {m_edge[0]:.3f}, sill {m_edge[1]:.3f}, "
                f"top {m_edge[2]:.3f} mm"
                if not fails else "FAILED: " + "; ".join(fails)),
               [dict(title="Chief rays and pupil-bundle margins (nominal geometry)", rows=rows),
                dict(title="Sensitivity to misplacement of the optics relative to the tub (camera R)", rows=srows)], notes, warns)


# ==============================================================================================
# 5. wall thickness
# ==============================================================================================
def sample_surface(tris, spacing, seed=12345):
    """Stratified random samples (fixed seed): about one per spacing^2 of area, at least one per triangle."""
    rng = np.random.default_rng(seed)
    v0, v1, v2 = tris[:, 0], tris[:, 1], tris[:, 2]
    cr = np.cross(v1 - v0, v2 - v0); a2 = np.linalg.norm(cr, axis=1)
    ok = a2 > 1e-12
    nrm = np.zeros_like(cr); nrm[ok] = cr[ok] / a2[ok, None]
    cnt = np.where(ok, np.maximum(1, np.ceil(0.5 * a2 / spacing ** 2)).astype(int), 0)
    idx = np.repeat(np.arange(len(tris)), cnt)
    r1, r2 = np.sqrt(rng.random(len(idx))), rng.random(len(idx))
    pts = (1 - r1)[:, None] * v0[idx] + (r1 * (1 - r2))[:, None] * v1[idx] + (r1 * r2)[:, None] * v2[idx]
    return pts, nrm[idx], (0.5 * a2 / np.maximum(cnt, 1))[idx]


def ray_thickness(tris, pts, nrm, tmax=1.6, cell=2.0, tmin=1e-3):
    """Cast a ray from every sample along -normal (into the material); return the distance to the first triangle hit
    within tmax and the dot product of that triangle's normal with the start normal (-1 = parallel opposing face)."""
    v0 = tris[:, 0]; e1 = tris[:, 1] - v0; e2 = tris[:, 2] - v0
    tn = np.cross(e1, e2); ln = np.linalg.norm(tn, axis=1); good = ln > 1e-12
    tn[good] /= ln[good, None]
    tlo, thi = tris.min(axis=1), tris.max(axis=1)
    lo = np.minimum(pts, pts - nrm * tmax).min(axis=0) - 1e-6
    key = np.floor((pts - lo) / cell).astype(np.int64)
    dist = np.full(len(pts), np.inf); dots = np.zeros(len(pts))
    order = np.lexsort((key[:, 2], key[:, 1], key[:, 0]))
    ks = key[order]
    brk = np.concatenate([[0], np.where(np.any(np.diff(ks, axis=0) != 0, axis=1))[0] + 1, [len(ks)]])
    for a, b in zip(brk[:-1], brk[1:]):
        c_lo = lo + ks[a] * cell - tmax; c_hi = lo + (ks[a] + 1) * cell + tmax
        cand = np.where(good & np.all(thi >= c_lo, axis=1) & np.all(tlo <= c_hi, axis=1))[0]
        if not len(cand):
            continue
        for s in range(a, b, 4000):                           # bounded memory
            ridx = order[s:min(b, s + 4000)]
            o = pts[ridx][:, None, :]; d = -nrm[ridx][:, None, :]
            E1, E2, V0 = e1[cand][None], e2[cand][None], v0[cand][None]
            with np.errstate(divide="ignore", invalid="ignore"):
                pv = np.cross(d, E2); det = np.einsum("rtk,rtk->rt", np.broadcast_to(E1, pv.shape), pv)
                inv = 1.0 / det
                tv = o - V0
                u = np.einsum("rtk,rtk->rt", tv, pv) * inv
                qv = np.cross(tv, np.broadcast_to(E1, tv.shape))
                v = np.einsum("rtk,rtk->rt", np.broadcast_to(d, qv.shape), qv) * inv
                t = np.einsum("rtk,rtk->rt", np.broadcast_to(E2, qv.shape), qv) * inv
                hit = (np.abs(det) > 1e-12) & (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9) & (t > tmin) & (t <= tmax)
            t = np.where(hit, t, np.inf)
            j = np.argmin(t, axis=1); tb = t[np.arange(len(ridx)), j]
            dist[ridx] = tb; dots[ridx] = np.einsum("rk,rk->r", tn[cand[j]], nrm[ridx])
    return dist, dots


def _exact_thickness(caster, p, n, tmax=1.6):
    """Exact wall thickness on the B-rep along -n through p (p lies within the STL tolerance of the true surface)."""
    from OCP.gp import gp_Lin, gp_Pnt, gp_Dir
    it = caster._i
    it.Perform(gp_Lin(gp_Pnt(*map(float, p)), gp_Dir(*map(float, -n))), -0.06, tmax)
    if not it.IsDone() or it.NbPnt() < 2:
        return None
    ws = sorted(it.WParameter(k) for k in range(1, it.NbPnt() + 1))
    entry = min(ws, key=abs)
    if abs(entry) > 0.05:
        return None
    later = [w for w in ws if w > entry + 1e-4]
    return (later[0] - entry) if later else None


def _wall_features(name):
    """Documented thin features, one report row each: (label, deviation id or '', expected minimum, [bbox (x0,y0,z0,x1,y1,z1)])."""
    f = []
    e = 0.06
    if name == "tub":
        for side, (cx, _) in P.CAM_XY.items():
            f.append((f"camera {side}: wall behind the window recess in front of the camera cube (accepted)", "D04", P.THIN_STRIP_T,
                      [(cx - P.WIN_RECESS_W / 2 - e, P.HOOD_PAD_Y - e, P.WIN_Z0 - e, cx + P.WIN_RECESS_W / 2 + e, P.WIN_RECESS_FLOOR_Y + e, P.HOOD_Z_OVER_CUBE + e)]))
            c = P.HOOD_REAR_CHAMFER
            f.append((f"camera {side}: foot of the hood rear wall ({c:.2f} mm edge chamfer facing the prism)", "", P.MIN_WALL - c,
                      [(cx - P.HOOD_OUT_HW - e, P.HOOD_REAR_Y0 - e, P.HOOD_Z_OVER_CUBE - e, cx + P.HOOD_OUT_HW + e, P.HOOD_REAR_Y1 + e, P.HOOD_Z_OVER_CUBE + c + e)]))
            c = M["hood_leadin"]
            zs = M["hood_skirt_z0"]
            f.append((f"camera {side}: feet of the hood skirts ({c} mm lead-in chamfer for the camera cube)", "", M["hood_wall"] - c,
                      [(cx - P.HOOD_OUT_HW - e, P.HOOD_REAR_Y0 - e, zs - e, cx + P.HOOD_OUT_HW + e, P.Y_VISOR_IN + e, zs + c + e)]))
            land = P.HORN_X_OUT - (P.CAM_X + P.WIN_RECESS_W / 2)
            sg = 1 if cx > 0 else -1
            xa, xb = sorted((sg * (P.CAM_X + P.WIN_RECESS_W / 2 - e), sg * (P.HORN_X_OUT + e)))
            f.append((f"camera {side}: land between the window recess and the D corner ({land:.2f} mm wide; its top outer edge carries the R{M['top_fillet']} "
                      "of the arc)", "", 0.6, [(xa, P.WIN_RECESS_FLOOR_Y - e, P.T - M["top_fillet"] - e, xb, P.Y_VISOR + e, P.T + e)]))
        ch = M["bottom_chamfer"]
        f.append((f"foot of the side wall at the specified {ch} mm bottom chamfer (all round the arc)", "", P.WALL - ch,
                  [(-P.R_OUT - e, -P.R_OUT - e, P.RIM_Z - e, P.R_OUT + e, P.R_OUT + e, P.RIM_Z + ch + e)]))
        c = M["spigot_tip_chamfer"]
        for (sx_, sy_) in (P.LOC_ROUND[:2], P.LOC_SLOT[:2]):
            f.append((f"tip of the PCB locating spigot at x = {sx_} (dia {P.SPIGOT_D} pin with a {c} mm lead-in chamfer: a pin, not a wall)", "D19", P.SPIGOT_D - 2 * c,
                      [(sx_ - P.SPIGOT_D / 2 - e, sy_ - P.SPIGOT_D / 2 - e, P.SPIGOT_Z0 - e, sx_ + P.SPIGOT_D / 2 + e, sy_ + P.SPIGOT_D / 2 + e, P.PCB_Z1 + e)]))
    if name == "cradle":
        hw = M["latch_w"] / 2
        f.append((f"latch hook nose: solid wedge between the raked retaining face and the lead-in, ending in a {M['hook_nose_flat']} mm flat "
                  "(an edge, not a wall)", "", M["hook_nose_flat"],
                  [(-hw - e, P.LATCH_Y_FACE - e, P.HOOK_Z0 - e, hw + e, P.HOOK_Y + e, P.LATCH_TOP_Z + e)]))
    return f


def _cluster(pts, link):
    from scipy.spatial import cKDTree
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    if len(pts) == 0:
        return np.zeros(0, int)
    pairs = cKDTree(pts).query_pairs(link, output_type="ndarray")
    g = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(pts), len(pts)))
    return connected_components(g, directed=False)[1]


WALL_SPACING = dict(tub=0.10, base_plate=0.08, cradle=0.20)
WALL_MESH_TOL = 0.045         # worst-case effect of the 0.02 mm STL chord error on a thickness reading
WALL_OPPOSING_DOT = -0.4      # the face the ray leaves through must lie within 66 deg of parallel to the start face


def check_walls(parts):
    rows_all, thin5, fails, warns, notes = [], [], [], [], []
    summary_bits = []
    for name in ("tub", "base_plate", "cradle"):
        tris, src = _tris(parts, name)
        sp = WALL_SPACING[name]
        pts, nrm, area = sample_surface(tris, sp)
        dist, dots = ray_thickness(tris, pts, nrm)
        # candidates: every sample whose mesh reading could be below the rule; plane-parallel walls are tessellated exactly,
        # so a reading of exactly the rule on antiparallel planar faces needs no second look
        planar_at_rule = (dots < -1 + 1e-9) & (dist >= P.MIN_WALL - 2e-5)
        opp = dots < WALL_OPPOSING_DOT
        cand = np.where(opp & (dist < P.MIN_WALL + WALL_MESH_TOL) & ~planar_at_rule)[0]
        n_oblique = int((~opp & (dist < 0.5)).sum())
        caster = G.RayCaster(A.solid_of(parts[name]))
        exact = np.full(len(pts), np.nan)
        for i in cand:                                       # exact re-measurement on the B-rep (no tessellation error)
            t = _exact_thickness(caster, pts[i], nrm[i])
            exact[i] = t if t is not None else dist[i]
        thin = cand[exact[cand] < P.MIN_WALL - 1e-3]
        feats = _wall_features(name)
        label = np.full(len(pts), -1)
        for k, (_, _, tmin_expected, boxes) in enumerate(feats):
            for bx in boxes:
                inside = np.all(pts[thin] >= np.array(bx[:3]), axis=1) & np.all(pts[thin] <= np.array(bx[3:]), axis=1)
                ok = inside & (exact[thin] >= tmin_expected - 0.02) & (label[thin] < 0)
                label[thin[ok]] = k

        def row(sel, k):
            lo, hi = pts[sel].min(axis=0), pts[sel].max(axis=0)
            doc = k >= 0
            return dict(part=name, feature=feats[k][0] if doc else "UNDOCUMENTED thin region", deviation=feats[k][1] if doc else "",
                        min_mm=R3(np.nanmin(exact[sel])), median_mm=R3(np.nanmedian(exact[sel])),
                        area_below_0p8_mm2=round(float(area[sel].sum()), 2), area_below_0p5_mm2=round(float(area[sel][exact[sel] < 0.5].sum()), 2),
                        bbox_min=tuple(float(v) for v in np.round(lo, 2)), bbox_max=tuple(float(v) for v in np.round(hi, 2)),
                        status="documented" if doc else "FAIL")
        region_rows = [row(thin[label[thin] == k], k) for k in range(len(feats)) if (label[thin] == k).any()]
        und = thin[label[thin] < 0]
        if len(und):
            lab = _cluster(pts[und], max(0.5, 4 * sp))
            for c in np.unique(lab):
                r = row(und[lab == c], -1)
                region_rows.append(r)
                fails.append(f"{name}: undocumented region, min {r['min_mm']} mm at {r['bbox_min']}..{r['bbox_max']}")
        rows_all += region_rows
        thin5 += [r for r in region_rows if r["area_below_0p5_mm2"] > 0 or r["min_mm"] < 0.5]
        tmin = float(np.nanmin(exact[cand])) if len(cand) else float(dist[opp].min())
        summary_bits.append(f"{name} minimum {tmin:.3f} mm")
        notes.append(f"{name}: {len(tris)} triangles ({src}), {len(pts)} surface samples at {sp} mm spacing, {len(cand)} candidates re-measured "
                     f"exactly on the B-rep, {len(thin)} of them below {P.MIN_WALL} mm; thinnest reading {tmin:.3f} mm; {n_oblique} samples leave "
                     "through an oblique face within 0.5 mm (grazing exits at wall ends and sharp edges - not wall thickness, not counted)")
    for r in thin5:
        warns.append(f"{r['part']}: {r['feature']} - min {r['min_mm']} mm, {r['area_below_0p5_mm2']} mm2 below 0.5 mm ({r['deviation'] or 'documented'})")
    n_doc = sum(r["status"] == "documented" for r in rows_all)
    notes += ["method: from every surface sample a ray is cast along the inward normal and the distance to the first face it meets is the local "
              "thickness (mesh first, then the same ray on the exact solid for every candidate). A reading counts when the face the ray leaves "
              "through is within 66 deg of parallel to the start face (wedges up to 66 deg are walls; grazing exits are not)",
              f"a region is listed when it is thinner than the {P.MIN_WALL} mm rule; regions with any area below 0.5 mm are repeated in the second table",
              "edge chamfers and bevels read thin at their feet by this method; they are listed, not hidden",
              "the 0.7 mm wide bottom land of the side wall is an edge feature of a wall that is 1.0 mm thick above it; the latch beam "
              f"(root {P.LATCH_H0} mm >= 1.0, neck {P.LATCH_HN} mm) and every wall of the cradle are above the rule"]
    return res(5, "wall thickness", not fails,
               (f"{len(thin5)} regions thinner than 0.5 mm; {n_doc} recorded regions below {P.MIN_WALL} mm in total; no unrecorded thin region; "
                + ", ".join(summary_bits)
                if not fails else "FAILED: " + "; ".join(fails)),
               [dict(title=f"Regions thinner than the {P.MIN_WALL} mm rule", rows=rows_all),
                dict(title="Regions thinner than 0.5 mm", rows=thin5)], notes, warns)


# ==============================================================================================
# 6. trapped volume
# ==============================================================================================
def voxelize(tris, pitch, margin):
    """Solid occupancy grid of a closed mesh by z-column parity. Returns (solid[nx,ny,nz] bool, origin, odd_columns)."""
    v = tris.reshape(-1, 3)
    lo = v.min(axis=0) - margin + np.array([0.0137, 0.0291, 0.0173]) * pitch   # de-phased from round coordinates, differently per axis
                                                               # (a 45 deg facet edge must not run through column centres)
    n = np.ceil((v.max(axis=0) + margin - lo) / pitch).astype(int)
    x0, y0 = lo[0] + 0.5 * pitch, lo[1] + 0.5 * pitch
    I, J, Z = [], [], []
    for a, b, c in tris:
        det = (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])
        if abs(det) < 1e-12:
            continue
        i0 = int(math.ceil((min(a[0], b[0], c[0]) - x0) / pitch)); i1 = int(math.floor((max(a[0], b[0], c[0]) - x0) / pitch))
        j0 = int(math.ceil((min(a[1], b[1], c[1]) - y0) / pitch)); j1 = int(math.floor((max(a[1], b[1], c[1]) - y0) / pitch))
        if i1 < i0 or j1 < j0:
            continue
        ii, jj = np.meshgrid(np.arange(i0, i1 + 1), np.arange(j0, j1 + 1), indexing="ij")
        X, Yg = x0 + ii * pitch, y0 + jj * pitch
        u = ((X - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (Yg - a[1])) / det
        w = ((b[0] - a[0]) * (Yg - a[1]) - (X - a[0]) * (b[1] - a[1])) / det
        m = (u >= 0) & (w >= 0) & (u + w <= 1)
        if m.any():
            I.append(ii[m]); J.append(jj[m]); Z.append(a[2] + u[m] * (b[2] - a[2]) + w[m] * (c[2] - a[2]))
    I, J, Z = np.concatenate(I), np.concatenate(J), np.concatenate(Z)
    col = I.astype(np.int64) * n[1] + J
    order = np.lexsort((Z, col)); col, Z = col[order], Z[order]
    uniq, start, cnt = np.unique(col, return_index=True, return_counts=True)
    pos = np.arange(len(col)) - np.repeat(start, cnt)
    even = np.repeat(cnt % 2 == 0, cnt)
    ent = (pos % 2 == 0) & even
    zin, zout, c = Z[ent], Z[np.where(ent)[0] + 1], col[ent]
    k0 = np.clip(np.ceil((zin - lo[2]) / pitch - 0.5).astype(int), 0, n[2])
    k1 = np.clip(np.floor((zout - lo[2]) / pitch - 0.5).astype(int) + 1, 0, n[2])
    ok = k1 > k0
    diff = np.zeros((n[0] * n[1], n[2] + 1), np.int16)
    np.add.at(diff, (c[ok], k0[ok]), 1); np.add.at(diff, (c[ok], k1[ok]), -1)
    solid = (np.cumsum(diff, axis=1)[:, :n[2]] > 0).reshape(n[0], n[1], n[2])
    return solid, lo, int((cnt % 2 == 1).sum())


VOXEL_PITCH = dict(tub=0.10, base_plate=P.BASE_T / 10, cradle=0.20)     # base: an exact tenth of the plate thickness
ESCAPE_DIA = 2.0


def check_trapped(parts):
    from scipy import ndimage as ndi
    rows, nrows, fails, warns, notes = [], [], [], [], []
    for name in ("tub", "base_plate", "cradle"):
        tris, src = _tris(parts, name)
        h = VOXEL_PITCH[name]
        margin = ESCAPE_DIA / 2 + 6 * h
        solid, lo, odd = voxelize(tris, h, margin)
        vol_mesh, _ = G.mesh_volume_area(tris)
        vol_vox = float(solid.sum()) * h ** 3
        empty = ~solid
        # (a) closed voids: empty voxels not connected to the outside at all
        lab, nlab = ndi.label(empty)
        ext = lab[0, 0, 0]
        void_sizes = np.bincount(lab.ravel(), minlength=nlab + 1) if nlab > 1 else np.array([0, 0])
        closed = [(k, void_sizes[k] * h ** 3) for k in range(1, nlab + 1) if k != ext and void_sizes[k] * h ** 3 > 0.02]
        # (b) cavities that a ball of the escape diameter fits into but cannot leave
        r = ESCAPE_DIA / 2
        dist = ndi.distance_transform_edt(empty, sampling=h)          # distance from an empty voxel centre to the nearest solid voxel centre
        core = dist >= (r - 0.25 * h)
        clab, ncl = ndi.label(core)
        cext = clab[0, 0, 0]
        csz = np.bincount(clab.ravel(), minlength=ncl + 1)
        stuck = []
        for k in range(1, ncl + 1):
            if k == cext or csz[k] == 0:
                continue
            idx = np.argwhere(clab == k)
            stuck.append((csz[k], lo + (idx.min(axis=0) + 0.5) * h, lo + (idx.max(axis=0) + 0.5) * h))
        # (c) narrow recesses: empty space the escape-diameter ball cannot sweep
        d2 = ndi.distance_transform_edt(clab != cext, sampling=h)
        reach = empty & (d2 <= r + 0.75 * h)
        narrow = empty & ~reach
        depth = np.where(narrow, d2 - r, 0.0)
        deep = depth > 0.80                            # a 2 mm ball leaves 0.41 / 0.73 mm unswept in every square edge / corner
        nlab2, nn = ndi.label(deep)
        n_deep = 0
        if nn:
            objs = ndi.find_objects(nlab2)
            idx = np.arange(1, nn + 1)
            maxd = ndi.maximum(depth, nlab2, index=idx)
            sizes = np.bincount(nlab2.ravel(), minlength=nn + 1)[1:]
            maxw = ndi.maximum(dist, nlab2, index=idx)
            for k in np.argsort(-maxd):
                if sizes[k] * h ** 3 < 0.02:
                    continue
                sl = objs[k]
                bmin = lo + (np.array([s.start for s in sl]) + 0.5) * h; bmax = lo + (np.array([s.stop for s in sl]) - 0.5) * h
                n_deep += 1
                nrows.append(dict(part=name, feature=_narrow_feature(name, bmin, bmax), depth_beyond_2mm_ball_mm=round(float(maxd[k]), 2),
                                  local_width_mm=round(2 * float(maxw[k]), 2), volume_beyond_0p8_mm3=round(float(sizes[k]) * h ** 3, 2),
                                  bbox_min=tuple(float(v) for v in np.round(bmin, 1)), bbox_max=tuple(float(v) for v in np.round(bmax, 1))))
        shells = len(A.solid_of(parts[name]).Shells())
        bad = bool(closed) or bool(stuck) or shells != 1
        if closed:
            fails.append(f"{name}: {len(closed)} closed void(s), {sum(v for _, v in closed):.2f} mm3")
        for s in stuck:
            fails.append(f"{name}: cavity near {np.round(s[1], 1)}..{np.round(s[2], 1)} has no {ESCAPE_DIA} mm escape path")
        if shells != 1:
            fails.append(f"{name}: B-rep has {shells} shells (an inner shell is a closed void)")
        if abs(vol_vox - vol_mesh) / vol_mesh > 0.03 or odd > 20:
            fails.append(f"{name}: voxel model unreliable (volume {vol_vox:.1f} vs {vol_mesh:.1f}, {odd} odd columns)")
        rows.append(dict(part=name, voxel_mm=h, grid=tuple(int(v) for v in solid.shape), voxel_volume_mm3=round(vol_vox, 1), mesh_volume_mm3=round(vol_mesh, 1),
                         brep_shells=shells, closed_voids=len(closed), cavities_without_2mm_exit=len(stuck), narrow_recesses_listed=n_deep,
                         status="FAIL" if bad else "ok"))
        notes.append(f"{name}: {src}")
    notes += [f"closed void = empty region with no connection to the outside; cavity without exit = a place where a {ESCAPE_DIA} mm ball fits "
              "but from which it cannot roll out of the part (Euclidean distance transform of the empty space, connected components)",
              "narrow recesses = empty space more than 0.8 mm beyond the reach of a 2 mm ball (deeper than the 0.41 / 0.73 mm a ball leaves in "
              "any square edge / corner); they are open, not trapped, but need directed bead blasting or a pick at the bureau",
              "accuracy about one voxel; the part is analysed bare (as printed), not assembled"]
    for r in nrows:
        if r["depth_beyond_2mm_ball_mm"] > 2.0:
            warns.append(f"{r['part']}: narrow recess {r['feature']} is {r['depth_beyond_2mm_ball_mm']} mm deep at {r['local_width_mm']} mm width - depowdering access to confirm with the bureau")
    return res(6, "trapped volume", not fails,
               ("no closed void and no cavity without a 2 mm escape path in tub, base plate or cradle; "
                f"{len(nrows)} open narrow recesses listed" if not fails else "FAILED: " + "; ".join(fails)),
               [dict(title="Voxel analysis per printed part", rows=rows),
                dict(title="Open recesses narrower than 2 mm (not trapped; depowdering attention)", rows=nrows)], notes, warns)


def _narrow_feature(name, bmin, bmax):
    """Name a narrow recess from where it is (for the report only)."""
    c = 0.5 * (bmin + bmax)
    if name == "tub":
        vx, vy = P.VENT_XY
        if abs(c[0] - vx) < 1.5 and abs(c[1] - vy) < 1.5 and c[2] > P.ROOF_Z - 0.5:
            return "vent hole dia 1.0 (through)"
        for s, (cx, cy) in P.CAM_XY.items():
            if abs(c[0] - cx) < 5.5 and c[1] > P.HOOD_REAR_Y0 - 0.5:
                return f"camera hood {s} (bay / slot over the cube / gap to the side wall, open below)"
        if c[2] < P.LEDGE_Z1 + 0.3 and math.hypot(c[0], c[1]) > P.LEDGE_RI - 1.0:
            return "seal ledge / base rebate corner"
        if abs(c[0]) < 1.5 and c[2] > P.T - 1.0:
            return "nose index groove"
        for pn, x0, x1, y0, y1 in P.post_rects():
            if x0 - 1.5 < c[0] < x1 + 1.5 and y0 - 2.0 < c[1] < y1 + 2.0:
                return f"gap between support post {pn} and the side wall"
        if abs(abs(c[0]) - P.LCD_POCKET_X) < 1.0 and c[2] > P.BOND_Z:
            return "corner between the thick-roof (LCD pocket) step and the side wall"
        return "internal corner"
    if name == "base_plate":
        for i, (x, y) in enumerate(P.BALL_XY):
            if math.hypot(c[0] - x, c[1] - y) < 1.5:
                return f"ball-foot hole {i + 1} (through)"
        if abs(c[1] - P.PAD_Y) < 2:
            return "pad slot end"
        if math.hypot(c[0] - P.GRAIN_X, c[1] - P.GRAIN_Y) < P.GRAIN_R + 0.5:
            return "grain opening sector corner"
        return "edge"
    dx0, dx1 = M["well_drain_x"]
    if dx0 - 0.5 < c[0] < dx1 + 0.5 and c[1] < P.WELL_Y0 + 0.8 and P.WELL_DRAIN_Z0 - 0.5 < c[2] < P.WELL_DRAIN_Z1 + 0.5:
        return "drain tunnel of the latch well (through to the rear face)"
    if abs(c[0]) < P.WELL_HX + 0.5 and P.WELL_Y0 - 0.5 < c[1] < P.WELL_Y1 + 0.5 and c[2] > M["latch_root_z"] - 0.5:
        return "latch well (gap round the cantilever, open at the top, drained to the rear)"
    if abs(c[1] - P.PAD_Y) < 2 and abs(c[0]) < 10 and c[2] < P.NEST_FLOOR_Z:
        return "spring-pin slot (through)"
    fx, fy = M["foot_xy"]
    if abs(abs(c[0]) - fx) < 3.5 and abs(abs(c[1] - P.CRADLE_CY) - fy) < 3.5 and c[2] < P.CORE_Z1 + 0.5:
        return "blind core under a foot pocket"
    if P.BASIN_Z_AT_EDGE - 0.5 < c[2] < P.NEST_FLOOR_Z + 0.3:
        return "drained nest floor (corner of the basin at a pad, the slot rim, the dam or the strip)"
    if abs(c[0]) < M["lip_half_w"] + 0.5 and c[1] > P.NEST_FLAT - 2.5 and c[2] > P.CRADLE_TOP_Z - 0.5:
        return "nose pocket under the lip (open to both sides)"
    if c[2] < P.CPCB_Z1 + 1 and abs(c[0]) < P.CPCB_HX + 1:
        return "PCB / USB pocket corner or screw spot mark"
    return "pocket corner"


# ==============================================================================================
# 7. cradle: pins, orientation key, hold-down, insertion path
# ==============================================================================================
def _marker_shell(S):
    sh = S["tub"].fuse(S["base_plate"])
    for i in range(1, len(P.BALL_XY) + 1):
        sh = sh.fuse(S[f"ball_{i}"])
    return sh


def _latch_travel_needed(tub_posed, latch, mode="F", d_max=3.2, tol=1e-4):
    """Smallest hook travel at which the posed tub no longer intersects the deflected latch (bisection on the solids)."""
    vol = lambda d: common_volume(tub_posed, H.latch_deflected(latch, d, mode))
    if vol(0.0) <= tol:
        return 0.0
    if vol(d_max) > tol:
        return float("inf")
    lo, hi = 0.0, d_max
    for _ in range(11):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if vol(mid) > tol else (lo, mid)
    return hi


def _contact_travel(moving, fixed, mode, d_hi, tol=1e-4):
    """Hook travel at which the deflected latch (or a part of it) first intersects `fixed` (bisection); inf if never up to d_hi."""
    vol = lambda d: common_volume(H.latch_deflected(moving, d, mode), fixed)
    if vol(d_hi) <= tol:
        return float("inf")
    lo, hi = 0.0, d_hi
    for _ in range(12):
        mid = 0.5 * (lo + hi)
        lo, hi = (lo, mid) if vol(mid) > tol else (mid, hi)
    return hi


def check_cradle(parts):
    """Rev C dock: seven pin positions on the pads, one orientation, lip + latch hold-down proven with numbers (retention
    with the rotation of the hook and with tolerance, strain by beam formula and by FE, both over-travel stops), and the
    nose-first insertion path and the release proven by posing the marker solids against the cradle solids."""
    S = _solids(parts)
    cr, tub, base, psa = S["cradle"], S["tub"], S["base_plate"], S["pcb_adhesive"]
    fails, warns = [], []
    latch = PT.latch().val()
    v_l = common_volume(cr, latch)
    if abs(v_l - latch.Volume()) > 0.01 * latch.Volume():
        fails.append(f"the latch is not present in the cradle solid as designed ({v_l:.1f} of {latch.Volume():.1f} mm3)")
    body_nl = cr.cut(latch)                                   # the cradle with the latch removed (it deflects during insertion)
    lw, hw = M["lip_half_w"], M["latch_w"] / 2
    lipS = cr.intersect(PT.box(-lw - 0.5, lw + 0.5, P.LIP_Y0 - 0.5, P.CRADLE_Y1 + 1, P.CRADLE_TOP_Z + 0.01, P.LIP_Z1 + 1).val())
    hook = latch.intersect(PT.box(-hw - 1, hw + 1, P.TAB_Y0 - 1, P.HOOK_Y + 1, P.HOOK_Z0 - 0.3, P.LATCH_TOP_Z + 1).val())   # rigid part: hook + tab
    rc, rt = G.RayCaster(cr), G.RayCaster(tub)
    rp = M["pin_plunger_dia"] / 2
    zr = M["latch_root_z"]

    # ---------------- (a) pins at the seated position
    prow = []
    cpcb_top = A.bbox_of(parts["cradle_pcb"])[5]
    for i, x in enumerate(P.PAD_XS):
        bb = A.bbox_of(parts[f"spring_pin_{i + 1}"])
        px0, py0 = 0.5 * (bb[0] + bb[3]), 0.5 * (bb[1] + bb[4])
        off = math.hypot(px0 - x, py0 - P.PAD_Y)
        tip_gap = abs(bb[5] - P.PAD_Z0)
        cyl0 = cq.Solid.makeCylinder(rp, 3.0, cq.Vector(px0, py0, -1.0), cq.Vector(0, 0, 1))
        v0 = common_volume(base, cyl0) + common_volume(psa, cyl0)
        d0 = min(min_distance(base, cyl0), min_distance(psa, cyl0))
        work = bb[5] - cpcb_top
        good = off < 1e-3 and tip_gap < 1e-3 and v0 < 1e-6 and d0 >= P.CLR - NUM_TOL and abs(work - P.PIN_WORK_H) < 1e-3
        if not good:
            fails.append(f"pin {i + 1}")
        prow.append(dict(pin=i + 1, x=x, fitted="consumer + factory" if i < len(P.PINS_CONSUMER) else "factory fixture only",
                         axis_to_pad_centre_mm=round(off, 4), tip_to_pad_face_mm=round(tip_gap, 4),
                         clearance_in_base_and_adhesive_slot_mm=R3(d0), height_above_cradle_pcb_mm=R3(work),
                         compression_mm=R3(M["pin_max_working_h"] - work), ok=good))
    if abs(cpcb_top - (P.PAD_Z0 - P.PIN_WORK_H)) > 1e-6:
        fails.append(f"cradle PCB top at z = {cpcb_top:.3f}, not pad face {P.PAD_Z0} - working height {P.PIN_WORK_H}")

    # ---------------- (b) orientation key (the D flat): marker shell turned about its own axis against the cradle
    shell = _marker_shell(S)
    orows = []
    for ang in (0.0, 90.0, 180.0, 270.0):
        sh = shell.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), ang) if ang else shell
        v = common_volume(sh, cr)
        ok = (v < INTERFERENCE_LIMIT_MM3) if ang == 0.0 else (v > 1.0)
        if not ok:
            fails.append(f"orientation {ang:.0f} deg: common volume {v:.3f} mm3")
        orows.append(dict(marker_angle_deg=int(ang), common_volume_with_cradle_mm3=round(v, 3), expected="seats" if ang == 0.0 else "blocked",
                          status="ok" if ok else "FAIL"))

    # ---------------- (c) hold-down geometry measured on the solids (rays and sections), compared with the parameters
    grow = []

    def meas(name, value, nominal, tol=0.01, note=""):
        ok = value is not None and value == value and abs(value - nominal) <= tol
        if not ok:
            fails.append(f"{name}: measured {value} vs {nominal}")
        grow.append(dict(quantity=name, measured_mm=R3(value), parameter_mm=R3(nominal), status="ok" if ok else "FAIL", note=note))

    def beam_sec(z):
        sec = G.section_polys(latch, "z", z)
        return sec.bounds if not sec.is_empty else (0, 0, 0, 0)
    bx = beam_sec(2.0)
    meas("latch beam width b (section z = 2.0)", bx[2] - bx[0], M["latch_w"])
    for label, z, tol in (("at the top of the root fillets", zr + M["latch_root_fillet"] + 0.05, 0.01), ("half way up", zr + 0.5 * P.LATCH_S1, 0.01),
                          ("at the neck", P.LATCH_NECK_Z, 0.06), ("below the hook", P.HOOK_Z0 - 0.9, 0.01)):
        bz = beam_sec(z)
        meas(f"latch beam thickness {label} (z = {z:.2f})", bz[3] - bz[1], float(P.latch_h(z - zr)), tol,
             note="neck: the R%.0f blend adds up to 0.05" % M["latch_neck_blend"] if "neck" in label else "")
    h_root = beam_sec(zr + M["latch_root_fillet"] + 0.05); h_min = min(beam_sec(z)[3] - beam_sec(z)[1] for z in np.linspace(zr + 1.2, P.HOOK_Z0 - 0.6, 24))
    t = rc.first_hit((0, P.LATCH_Y_BACK0 - 1.6, 2.0), (0, 0, -1))
    z_root = 2.0 - t if t else float("nan")
    meas("latch root (well floor) z", z_root, zr)
    meas("skin between the well floor and the PCB pocket", z_root - cpcb_top, zr - P.CPCB_Z1, note=">= 0.8 mm wall")
    up = lambda y: (lambda t_: (P.T + 0.001 + t_) if t_ is not None else float("nan"))(rc.first_hit((0, y, P.T + 0.001), (0, 0, 1), 1e-9, 6.0))
    y1, y2 = P.HOOK_Y - 0.03, P.LATCH_Y_FACE + 0.85
    z1, z2 = up(y1), up(y2)
    meas("nose (lowest point of the retaining face) z", z1 - (P.HOOK_Y - y1) * P.HOOK_RAKE_TAN, P.HOOK_Z0)
    meas("nose above the tub top", z1 - (P.HOOK_Y - y1) * P.HOOK_RAKE_TAN - P.T, P.CLR)
    rake = math.degrees(math.atan2(z2 - z1, y1 - y2))
    meas("rake of the retaining face (deg; nose lowest)", rake, M["hook_rake_deg"], 0.05, note="the face stays inclined against release while the hook turns nose-up")
    meas("latch free length L (root to nose level)", z1 - (P.HOOK_Y - y1) * P.HOOK_RAKE_TAN - z_root, P.LATCH_L)
    zn = P.HOOK_Z0 + M["hook_nose_flat"] / 2
    ny = [rc.first_hit((x, 0, zn), (0, -1, 0)) for x in (0.0, hw - 0.5, -(hw - 0.5))]
    meas("nose position (distance behind the marker axis), x = 0", ny[0], -P.HOOK_Y)
    meas("nose is straight: same at x = +-%.1f" % (hw - 0.5), max(ny) if None not in ny else None, -P.HOOK_Y)
    lo, hi = -P.HOOK_Y, P.R_OUT
    for _ in range(40):                                       # outer radius of the flat top of the tub at the rear
        mid = 0.5 * (lo + hi)
        tt = rt.first_hit((0, -mid, P.T + 1.0), (0, 0, -1))
        lo, hi = (mid, hi) if (tt is not None and abs(tt - 1.0) < 1e-6) else (lo, mid)
    meas("flat top of the tub ends at radius", lo, P.TUB_TOP_FLAT_R, note="top edge radius 0.6 outside it")
    meas("hook overlap on the flat tub top, marker centred", lo - (ny[0] or float("nan")), P.HOOK_OVERLAP)
    meas("hook overlap, marker against the front nest wall (governing)", lo - P.CLR - (ny[0] or float("nan")), P.HOOK_OVERLAP_FWD)
    zg = M["guard_top_z"] - 0.02
    yb = P.LATCH_Y_FACE - float(P.latch_h(zg - zr))
    t = rc.first_hit((M["stop_rib_x"], yb - 0.005, zg), (0, -1, 0))
    meas("beam back face to the stop ribs at the rib top", (t or float("nan")) + 0.005, yb - P.STOP_RIB_Y1,
         note=f"met at {M['latch_stop_travel']} mm of hook travel when the hook is pushed back (beam shape under a tip force)")
    t = rc.first_hit((0, 0.5 * (P.TAB_STOP_Y0 + P.TAB_STOP_Y1), P.LATCH_TOP_Z + 2.0), (0, 0, -1))
    z_ts = P.LATCH_TOP_Z + 2.0 - t if t else float("nan")
    meas("top of the stop under the thumb tab", z_ts, P.TAB_STOP_Z, note="absent = the tab can be pressed without limit")
    t = rc.first_hit((0, P.TAB_Y0 + 1.0, P.TAB_Z0 - 1.5), (0, 0, 1))
    meas("underside of the thumb tab", P.TAB_Z0 - 1.5 + t if t else float("nan"), P.TAB_Z0)
    y_tip = rc.first_hit((0, 0, 0.5 * (P.LIP_Z0 + P.LIP_Z1)), (0, 1, 0))
    meas("lip overlap on the tub top", P.Y_VISOR - (y_tip or float("nan")), M["lip_overlap"])
    t = rc.first_hit((0, P.Y_VISOR - M["lip_overlap"] / 2, P.T + 0.001), (0, 0, 1), 1e-9, 5.0)
    meas("lip underside above the tub top", (t or float("nan")) + 0.001, P.CLR)
    lb = lipS.BoundingBox()
    meas("lip width", lb.xmax - lb.xmin, 2 * lw, note=f"window recesses start at |x| = {P.CAM_X - P.WIN_RECESS_W / 2}")
    meas("lip plate thickness", lb.zmax - P.LIP_Z0, M["lip_t"])
    if h_root[3] - h_root[1] < 1.0 - 1e-6:
        fails.append("latch root thinner than 1.0 mm")
    if h_min < P.MIN_WALL - 1e-6:
        fails.append(f"latch beam thinner than {P.MIN_WALL} mm ({h_min:.3f})")

    # ---------------- (d) both over-travel stops, on the solids
    srow = []
    d_tab_solid = _contact_travel(hook, body_nl, "M", M["tab_stop_travel"] + 0.6)
    ok = abs(d_tab_solid - M["tab_stop_travel"]) < 0.03
    if not ok:
        fails.append(f"thumb-tab stop: the pressed tab meets the body at {d_tab_solid:.3f} mm of hook travel, not {M['tab_stop_travel']}")
    srow.append(dict(stop="thumb tab on its stop (tab pressed: pure moment)", method="hook + tab solid turned about the moment pivot until it meets the cradle body (bisection)",
                     hook_travel_at_contact_mm=R3(d_tab_solid), parameter_mm=M["tab_stop_travel"], status="ok" if ok else "FAIL"))
    v_f = common_volume(H.latch_deflected(hook, M["latch_stop_travel"], "F"), body_nl)
    ok = v_f < 1e-4
    if not ok:
        fails.append(f"with the hook pushed back {M['latch_stop_travel']} mm the tab or hook intersects the body by {v_f:.4f} mm3")
    srow.append(dict(stop="stop ribs behind the beam (hook pushed back: tip force)", method="rib gap measured above; hook + tab solid at the stop travel must clear guard wall and tab stop",
                     hook_travel_at_contact_mm=M["latch_stop_travel"], parameter_mm=M["latch_stop_travel"], status="ok" if ok else "FAIL"))
    srow.append(dict(stop="stop ribs when the TAB is pressed", method="beam shape under a pure moment at the rib top (params.latch_shape)",
                     hook_travel_at_contact_mm=R3(P.RIB_TRAVEL_M), parameter_mm=f">= tab stop {M['tab_stop_travel']}: the ribs never block the release",
                     status="ok" if P.RIB_TRAVEL_M >= M["tab_stop_travel"] - 1e-9 else "FAIL"))
    if P.RIB_TRAVEL_M < M["tab_stop_travel"] - 1e-9:
        fails.append("a pressed tab reaches the stop ribs before its own stop")

    # ---------------- (e) insertion path: pose the marker solids tilt by tilt (nose first under the lip, rear last)
    plungers = [PT.spring_pin_free_plunger(x).val() for x in P.PAD_XS]
    irow, d_need = [], 0.0
    for th in M["insertion_tilts_deg"]:
        s_, h_ = H.path_pose(th)
        sp, tp = H.pose(shell, th, s_, h_), H.pose(tub, th, s_, h_)
        bp, pp = H.pose(base, th, s_, h_), H.pose(psa, th, s_, h_)
        v_fix = common_volume(sp, body_nl)
        d_lip = min_distance(sp, lipS)
        v_pin = sum(common_volume(bp, q) + common_volume(pp, q) for q in plungers)
        y_slot, z_slot = H.xf(P.PAD_Y, P.BASE_T / 2, th, s_, h_)
        y_pad, z_pad = H.xf(P.PAD_Y, P.PAD_Z0, th, s_, h_)
        comp = max(0.0, P.PIN_TIP_FREE_Z - z_pad)
        engaged = z_slot - P.BASE_T / 2 < P.PIN_TIP_FREE_Z       # the free plunger tip is inside the base slot
        dl = _latch_travel_needed(sp, latch, "F")
        d_need = max(d_need, dl)
        ok = v_fix < 1e-4 and v_pin < 1e-6 and comp <= M["pin_full_stroke"] and dl <= M["latch_stop_travel"]
        if not ok:
            fails.append(f"insertion pose {th} deg: body/lip {v_fix:.4f} mm3, pins {v_pin:.5f} mm3, latch travel {dl:.2f}, pin compression {comp:.2f}")
        irow.append(dict(tilt_deg=th, set_back_mm=round(s_, 3), lift_mm=round(h_, 3), rear_edge_height_mm=round(H.xf(-P.R_OUT, P.RIM_Z, th, s_, h_)[1], 2),
                         interference_with_nest_lip_floor_mm3=round(v_fix, 5), clearance_to_lip_mm=R3(d_lip),
                         plungers_into_base_or_adhesive_mm3=round(v_pin, 6),
                         slot_centre_offset_from_pin_axis_mm=(round(y_slot - P.PAD_Y, 3) if engaged else "pins not yet in the slot"),
                         pin_compression_mm=round(comp, 3), latch_travel_needed_mm=round(dl, 3), status="ok" if ok else "FAIL"))

    # ---------------- (f) release: hook travel that frees the marker, for the three fore-aft positions it can have in the nest
    rrow, d_rel = [], []
    for label, back, nominal in (("against the front nest wall (as the insertion leaves it)", -P.CLR, P.RELEASE_TRAVEL[0]), ("centred", 0.0, P.RELEASE_TRAVEL[1]),
                                 (f"rearmost (the rear nest wall starts {P.REAR_WALL_ANGLE_DEG:.0f} deg from the latch axis)", P.MARKER_BACK_MAX, P.RELEASE_TRAVEL[2])):
        need = 0.0
        for lift in M["release_lifts"]:
            need = max(need, _latch_travel_needed(tub.translate(cq.Vector(0, -back, lift)), hook, "M"))
        d_rel.append(need)
        ok = nominal - 0.3 < need <= nominal + 0.01 and need <= M["tab_stop_travel"] - 0.1 + 1e-9 and need <= P.RIB_TRAVEL_M + 1e-9
        if not ok:
            fails.append(f"release, marker {label}: hook travel {need:.3f} (nose to marker edge {nominal:.3f}; tab stop {M['tab_stop_travel']}, ribs {P.RIB_TRAVEL_M:.2f})")
        rrow.append(dict(marker_position=label, marker_shift_back_mm=R3(back), hook_travel_to_free_the_marker_mm=R3(need), nose_to_marker_edge_mm=R3(nominal),
                         margin_to_the_tab_stop_mm=R3(M["tab_stop_travel"] - need), status="ok" if ok else "FAIL"))

    # ---------------- (g) forces, retention, strain: beam model on the dimensions verified above, FE on the section of the solid
    mt = _mass_table(parts)
    m_puck = sum(r["mass_g"] for r in mt if r["group"] == "puck")
    cg = _cog(mt, "puck")
    c = H.calc(m_puck, cg[1], d_insert=d_need, d_release=d_rel)
    lim, req = M["latch_strain_limit"], M["retention_factor_required"]
    N2 = lambda v: round(float(v), 2)
    trow = []
    for r in c["retention"]:
        need_ok = r is c["nominal"] or r is c["governing"] or "print tolerance" in r["case"]
        ok = r["factor"] >= req
        if need_ok and not ok:
            fails.append(f"retention {r['factor']:.2f} x ({r['case']}) is below {req} x the seven-pin force")
        trow.append(dict(case=r["case"], hook_overlap_mm=R3(r["overlap"]), E_MPa=r["E"], friction=r["mu"],
                         holds_up_to_N_at_the_hook=(N2(r["F_hook"]) if r["F_hook"] != float("inf") else "self-locking"),
                         equals_N_at_the_pin_row=(N2(r["pin_row"]) if r["F_hook"] != float("inf") else "-"),
                         multiple_of_the_seven_pin_force=(N2(r["factor"]) if r["F_hook"] != float("inf") else "-"),
                         hook_rotation_at_release_deg=round(r["rot_deg"], 1), contact=r["regime"],
                         modulus_needed_for_3x_MPa=(round(r["E_min"]) if r["mu"] == 0 else "-"),
                         status=("ok" if ok else ("FAIL" if need_ok else "below 3 x (information)"))))
    if c["nominal"]["rot_deg"] > M["hook_rake_deg"] - 0.5:
        fails.append(f"hook rotation at release {c['nominal']['rot_deg']:.1f} deg reaches the rake {M['hook_rake_deg']} deg: the face becomes a ramp")
    try:
        fe = FE.run(cr)
    except Exception as ex:                                   # a failed FE run is reported, never hidden
        fe = None
        fails.append(f"FE of the latch section failed: {ex!r}")
    fe_per = dict(F=fe["F"]["eps_per_mm"], M=fe["M"]["eps_per_mm"], V=fe["V"]["eps_per_mm"]) if fe else dict(F=float("nan"), M=float("nan"), V=float("nan"))
    key = {"tip force": "F", "tab moment": "M", "hook load": "V"}
    erow, worst_full = [], 0.0
    for r in c["strain"]:
        e_fe = fe_per[key[r["load"]]] * r["travel"]
        full = r["case"].startswith("FULL")
        okk = r["eps"] <= lim + 1e-9 and e_fe <= lim + 1e-9
        if not okk:
            fails.append(f"latch strain {100 * r['eps']:.2f} % (beam) / {100 * e_fe:.2f} % (FE peak) exceeds {100 * lim} %: {r['case']}")
        if full:
            worst_full = max(worst_full, r["eps"], e_fe)
        erow.append(dict(case=r["case"], load=r["load"], hook_travel_mm=R3(r["travel"]), strain_beam_formula_pct=round(100 * r["eps"], 2), largest_at=r["at"],
                         strain_FE_peak_pct=round(100 * e_fe, 2), FE_peak_at=(fe[key[r["load"]]]["where"] if fe else "-"), limit_pct=100 * lim,
                         status="ok" if okk else "FAIL"))
    if c["d_rel_max"] > c["d_tab"] + 1e-9:
        fails.append("the tab stop engages before the hook has released in the rearmost marker position")
    ferow = []
    if fe:
        for k_, label in (("F", "hook pushed back (tip force)"), ("M", "thumb tab pressed (moment)"), ("V", "hook loaded upward (retention)")):
            beam_per = dict(F=c["epsF_per_mm"], M=c["epsM_per_mm"], V=float("nan"))[k_]
            ferow.append(dict(load=label, peak_strain_pct_per_mm_of_hook_travel=round(100 * fe[k_]["eps_per_mm"], 3), where=fe[k_]["where"], at_yz=fe[k_]["at"],
                              root_fillet_pct_per_mm=round(100 * fe[k_]["eps_root_per_mm"], 3), beam_neck_pct_per_mm=round(100 * fe[k_]["eps_beam_per_mm"], 3),
                              hook_and_tab_pct_per_mm=round(100 * fe[k_]["eps_hook_per_mm"], 3),
                              beam_formula_pct_per_mm=(round(100 * beam_per, 3) if beam_per == beam_per else "-"),
                              FE_over_formula=(round(fe[k_]["eps_per_mm"] / beam_per, 2) if beam_per == beam_per else "-"),
                              stiffness_N_per_mm_free_skin_and_PCB_backed=((N2(fe[k_]["stiffness_free_N_mm"]), N2(fe[k_]["stiffness_pcb_N_mm"])) if k_ == "F" else "-")))
    frow = [
        dict(quantity="pin force, seven pins (factory fixture) / four pins (consumer)", value=(N2(c["Fp7"]), N2(c["Fp4"])), unit="N",
             basis=f"{P.PIN_FORCE_N} N per pin at the working height (PROVISIONAL)"),
        dict(quantity="marker weight", value=round(c["weight"], 3), unit="N", basis=f"{m_puck:.1f} g (check 8)"),
        dict(quantity="hold-down reactions with seven pins: hook / lip", value=(N2(c["F_hook7"]), N2(c["F_lip7"])), unit="N",
             basis=f"moments about the lip (y {c['y_lip']:.2f}) and the hook contact (y {c['y_hook']:.2f}); the hook carries {100 * c['hook_share']:.1f} % of a pin-row force"),
        dict(quantity="hold-down reactions with four pins: hook / lip", value=(N2(c["F_hook4"]), N2(c["F_lip4"])), unit="N", basis="same"),
        dict(quantity="latch beam: b, h root / neck / at the hook, L, E, E I at the root", value=(c["b"], P.LATCH_H0, P.LATCH_HN, P.LATCH_H1, N2(c["L"]), c["E"], N2(c["EI0"])),
             unit="mm, mm, mm, mm, mm, MPa, N mm2", basis="rectangular cantilever, I(s) = b h(s)^3 / 12; E = HP PA 12 MJF data sheet (XY), dry, 23 C"),
        dict(quantity="beam stiffness at the hook (tip force) / per mm of travel for a tab moment", value=(N2(c["k"]), N2(c["kM"])), unit="N/mm, N mm/mm",
             basis="numerical integration of M / (E I(s)); the plane-strain FE is stiffer (table below), so forces can be up to a quarter higher"),
        dict(quantity="retention, governing position, no friction", value=(N2(c["governing"]["F_hook"]), N2(c["governing"]["pin_row"]), N2(c["factor_min"])), unit="N at the hook / N at the pin row / x",
             basis=f"largest upward hook force before the nose leaves the flat top (overlap {c['overlap_fwd']:.2f}), moment about the deflected axis; required >= {req} x"),
        dict(quantity="modulus at which the governing case is still 3 x", value=round(c["E_min"]), unit="MPa", basis="retention is proportional to E"),
        dict(quantity=f"hook travel and root stress at {req} x the seven-pin force", value=(N2(c["st3"]["nose_travel"]), N2(c["sig_root"]), N2(c["sf_root"])), unit="mm / MPa / safety factor",
             basis=f"hook load {c['F3_hook']:.1f} N: 6 F e / (b h^2) + F / (b h) at the root, e = {c['e_root']:.2f}; yield {M['pa12_yield_MPa']} MPa (data sheet)"),
        dict(quantity="straight pull on a latched marker (tab not pressed, hook self-locked by friction): root reaches yield at", value=(N2(c["F_yield"]), N2(c["pull_at_yield"])),
             unit="N at the hook / N of pull at the finger scallops", basis="strength of the root governs once friction locks the hook; the user must press the tab"),
        dict(quantity="hook travel needed: insertion / release forward / centred / rearmost", value=(N2(c["d_ins"]), N2(c["d_rel_fwd"]), N2(c["d_rel"]), N2(c["d_rel_max"])), unit="mm",
             basis="posed solids (tables below)"),
        dict(quantity="full deflection: stop ribs (hook pushed) / tab stop (tab pressed)", value=(N2(c["d_stop"]), N2(c["d_tab"])), unit="mm", basis="both stops verified on the solids"),
        dict(quantity="lateral force on the hook at the insertion travel", value=N2(c["P_ins"]), unit="N", basis="P = k d"),
        dict(quantity="insertion force at the thumb for friction " + " / ".join(str(m) for m in c["ins"]), value=tuple(N2(v) for v in c["ins"].values()), unit="N",
             basis=f"W = P (mu + tan a) / (1 - mu tan a), a = {c['lead_deg']:.0f} deg lead-in; thumb 8 mm in from the rear edge (lever {c['lever']:.2f})"),
        dict(quantity="force to finish seating (last degree, seven pins)", value=N2(c["seat"]), unit="N", basis="friction on the hook nose plus the pins coming under load"),
        dict(quantity="release: thumb force on the tab, marker forward / centred / rearmost", value=(N2(c["F_tab_fwd"]), N2(c["F_tab"]), N2(c["F_tab_max"])), unit="N",
             basis=f"M0 = E b d / cw_M, pressed {c['tab_lever']:.2f} mm behind the beam axis; the tab end drops {c['tab_drop']:.1f} mm (centred)"),
        dict(quantity="thumb force at which the tab lands on its stop / tab drop there", value=(N2(c["F_tab_stop"]), N2(c["tab_drop_stop"])), unit="N / mm",
             basis="beyond this the thumb force goes into the stop, not into the beam"),
        dict(quantity=f"over-press of {c['abuse']:.0f} N on the tab: load on the stop / bearing stress", value=(N2(c["abuse_excess"]), N2(c["sig_stop"])), unit="N / MPa",
             basis=f"stop {M['tab_stop_w']} x {M['tab_stop_t']} mm; the beam moment stays at its value at the stop"),
        dict(quantity="hook travel under the continuous seven-pin load (elastic / with a creep factor of 3)", value=(round(c["creep_d"], 3), round(3 * c["creep_d"], 3)),
             unit="mm", basis=f"hook load {c['F_hook7']:.2f} N, governing position; overlap {c['overlap_fwd']:.2f} mm (creep modulus of MJF PA12 not verified)"),
        dict(quantity="lip plate: stress with the whole required force on it / safety factor", value=(N2(c["sig_lip"]), N2(c["sf_lip"])), unit="MPa / -",
             basis=f"6 F a / (w t^2), F = {req} x {c['Fp7']:.2f} N, a = {c['lip_arm']:.2f}, {2 * lw:.0f} x {M['lip_t']} plate"),
        dict(quantity="marker floats against lip and hook when pins are fitted: lift / pin height / stroke used",
             value=(P.CLR, N2(P.PIN_FLOAT_H), N2(P.PIN_COMPRESSION - P.CLR)), unit="mm", basis=f"working height {P.PIN_WORK_H} with the marker on its feet, full stroke {M['pin_full_stroke']} (D21)"),
        dict(quantity="rear of the marker pops up on release by about", value=N2(c["pop_up"]), unit="mm", basis="pins return to their free length; then lift at the finger scallops"),
    ]

    # ---------------- (h) finger access at the two scallops (radial rays from outside onto the seated marker)
    arow = []
    a0, a1 = M["scallop_deg"]
    for sx in (1, -1):
        n_ok = n_all = 0
        for a in np.linspace(a0 + 4.0, a1 - 4.0, 7):
            ca, sa = sx * math.cos(math.radians(a)), math.sin(math.radians(a))
            for z in np.linspace(0.5, P.T - 0.8, 6):
                n_all += 1
                t_tub = rt.first_hit((60.0 * ca, 60.0 * sa, z), (-ca, -sa, 0))
                t_cr = rc.first_hit((60.0 * ca, 60.0 * sa, z), (-ca, -sa, 0))
                n_ok += int(t_tub is not None and (t_cr is None or t_cr > t_tub))
        okf = n_ok == n_all
        if not okf:
            fails.append(f"finger access {'+x' if sx > 0 else '-x'}: only {n_ok} of {n_all} rays reach the marker side")
        chord = 2 * P.R_OUT * math.sin(math.radians(a1 - a0) / 2)
        arow.append(dict(side="+x" if sx > 0 else "-x", scallop_from_deg=a0, to_deg=a1, opening_along_the_marker_mm=round(chord, 1),
                         marker_side_exposed_from_z=P.RIM_Z, to_z=P.T, rays_reaching_the_marker=f"{n_ok} of {n_all}", status="ok" if okf else "FAIL"))

    # ---------------- (i) drainage of the nest: every opening of the floor into the body is behind a rim at strip level
    rcb = G.RayCaster(body_nl)
    drow = []
    for label, pt, expect in (("basin floor on the centre line", (0.0, 0.0), P.BASIN_RIDGE_Z), ("basin floor at the scallop mouth", (P.NEST_R - 0.5, -6.0), P.BASIN_RIDGE_Z - (P.NEST_R - 0.5) * P.BASIN_TAN),
                              ("rim round the pin slot", (0.0, P.PAD_Y + P.CRADLE_PIN_SLOT_W / 2 + M["slot_rim_t"] / 2), P.NEST_FLOOR_Z),
                              ("dam in front of the latch well", (5.0, P.WELL_Y1 + 0.5), P.NEST_FLOOR_Z), ("pad under ball foot 2", P.BALL_XY[1], P.NEST_FLOOR_Z),
                              ("front strip under ball foot 1", P.BALL_XY[0], P.NEST_FLOOR_Z)):
        t = rcb.first_hit((pt[0], pt[1], P.CRADLE_TOP_Z + 2.0), (0, 0, -1))
        zf = P.CRADLE_TOP_Z + 2.0 - t if t is not None else float("nan")
        ok = abs(zf - expect) < 0.01
        if not ok:
            fails.append(f"nest floor at {label}: z {zf:.3f}, expected {expect:.3f}")
        drow.append(dict(place=label, xy=(round(pt[0], 2), round(pt[1], 2)), floor_z_mm=R3(zf), expected_mm=R3(expect), status="ok" if ok else "FAIL"))
    drow.append(dict(place="fall of the basin floor from the centre line to each side", xy="-", floor_z_mm=f"{M['basin_fall_deg']} deg", expected_mm="-", status="ok"))

    warns.append(f"with pins fitted the marker floats up to {P.CLR} mm against lip and hook (D21); the pins then stand {P.PIN_FLOAT_H:.2f} mm high")
    warns.append(f"insertion {c['ins'][c['mu']]:.0f} N and release {c['F_tab_fwd']:.0f} to {c['F_tab_max']:.0f} N are estimates (friction {c['mu']} assumed, modulus from the data "
                 "sheet, dry PA12); pin force and stroke are PROVISIONAL")
    warns.append(f"retention with the overlap reduced by {max(M['overlap_tolerances'])} mm is {c['factor_tol']:.1f} x at E = {c['E']:.0f} MPa and needs E >= {c['worst_tol']['E_min']:.0f} MPa: "
                 "the distance front nest wall to hook nose is a first-article dimension")
    warns.append(f"largest strain at full deflection is {100 * worst_full:.2f} % (limit {100 * lim} %); the stop positions (rib gap {P.LATCH_STOP_GAP:.2f}, tab stop z {P.TAB_STOP_Z:.2f}) "
                 "are first-article dimensions: 0.2 mm on the rib gap is about 0.3 mm of hook travel")
    notes = ["hold-down = fixed lip over the top front edge between the camera windows + rear cantilever latch; formulas in cad/holddown.py",
             f"retaining face raked {M['hook_rake_deg']} deg (nose lowest): the nose corner bears on the flat top of the marker, so the frictionless reaction is vertical "
             "and the face cannot cam the latch open while the hook turns nose-up under load; the retention figure is the frictionless lower bound and "
             "includes that rotation and the growth of the lever as the beam leans back",
             "'governing position' = marker against the front nest wall, where the lead-in of the hook leaves it during insertion: the overlap is then "
             f"{P.CLR} mm smaller than with the marker centred",
             f"insertion path: the marker is tilted nose-down, rests {M['insertion_gap']} mm above the front strip of the nest floor and is as far forward as the "
             f"front nest wall, the nose pocket and the lip tip allow ({M['insertion_gap']} mm clear); at each tilt the solids of tub + base plate + balls are "
             "intersected with the cradle (latch removed), the free-length plungers with base plate and adhesive sheet, and the latch is turned back "
             "until it no longer intersects the marker (that travel is the insertion deflection)",
             "hook travel = backward travel of the beam axis at the nose level; because the hook also turns nose-up, the nose corner itself moves a "
             "little further, which is why the travel that frees the marker is smaller than the distance nose to marker edge",
             "latch deflection in the posed checks = rigid rotation of the solid about the point that reproduces tip travel and tip slope of the bent "
             f"beam ({P.LATCH_PIVOT_F:.2f} mm below the nose level for a tip force, {P.LATCH_PIVOT_M:.2f} mm for a pure moment); exact for hook and tab",
             f"FE: plane strain, {fe['elements'] if fe else 0} constant-strain triangles on the section x = {FE.X_SECTION} of the cradle solid, {FE.H_FINE} mm elements at the "
             "fillets, nodal-averaged principal strain; skin under the well free and PCB-backed, the larger value is used (cad/latchfe.py). "
             "Refining the fillet mesh from 0.035 to 0.025 mm raised the root peak by 2 %",
             f"free plunger tip at z = {P.PIN_TIP_FREE_Z:.3f}; the pads meet the plungers at about 1.9 deg of tilt. The cradle PCB top is set {P.PIN_WORK_H} mm below "
             f"the COPPER FACE of the pads (z {P.PAD_Z0:.3f}), which is modelled {P.PIN_TIP_GAP:.3f} mm below the YAML pad plane (z {P.CRADLE_PAD_Z})",
             "printability of the latch is covered by check 5 (walls) and check 6 (the latch well is open at the top and drained; its gaps are listed there)"]
    ok_all = not fails
    return res(7, "cradle: pins, key, hold-down, insertion", ok_all,
               (f"seven pin positions on their pad centres, {min(r['clearance_in_base_and_adhesive_slot_mm'] for r in prow)} mm clear in the slots, at "
                f"{P.PIN_WORK_H} mm ({P.PIN_COMPRESSION:.2f} compressed); nest accepts 0 deg only; retention without friction {c['factor_min']:.1f} x the seven-pin "
                f"force in the governing position ({c['factor']:.1f} x centred, {c['factor_tol']:.1f} x with {max(M['overlap_tolerances'])} mm less overlap; required {req} x); "
                f"strain at full deflection {100 * c['eps_stop']:.2f} % at the stop ribs and {100 * c['eps_tab']:.2f} % at the tab stop by the beam formula, "
                f"{100 * worst_full:.2f} % peak by FE (limit {100 * lim} %); insertion {c['d_ins']:.2f} mm of hook travel, about {c['ins'][c['mu']]:.0f} N; release "
                f"{c['d_rel_fwd']:.2f} to {c['d_rel_max']:.2f} mm, {c['F_tab_fwd']:.0f} to {c['F_tab_max']:.0f} N on the tab; {len(irow)} posed tilts from "
                f"{max(M['insertion_tilts_deg']):.0f} deg to 0 without interference with lip, nest or pins"
                if ok_all else "FAILED: " + "; ".join(fails)),
               [dict(title="Pins at the seated position", rows=prow), dict(title="Orientation key", rows=orows),
                dict(title="Hold-down geometry measured on the solids", rows=grow),
                dict(title="Over-travel stops", rows=srow),
                dict(title="Retention (largest upward force on the hook before it lets go)", rows=trow),
                dict(title="Latch strain: beam formula and FE peak", rows=erow),
                dict(title="FE of the latch section (per mm of hook travel)", rows=ferow),
                dict(title="Hold-down forces", rows=frow),
                dict(title="Insertion path (marker solids posed against the cradle solids)", rows=irow),
                dict(title="Release (marker lifted straight up past the deflected hook)", rows=rrow),
                dict(title="Finger access", rows=arow), dict(title="Drained nest floor", rows=drow)], notes, warns)


# ==============================================================================================
# 8. mass and centre of gravity
# ==============================================================================================
PCB_BOARD_DENSITY, PCB_PART_DENSITY = 1.85, 1.5


def _mass_table(parts):
    rows = []
    for n, info in parts.items():
        s = A.solid_of(info)
        v = s.Volume()
        c = cq.Shape.centerOfMass(s)
        cen = np.array([c.x, c.y, c.z])
        if n == "main_pcb":                                  # bare board at FR-4 density, part envelope boxes at a lower effective density
            b = PT.pcb_board().val(); vb = b.Volume(); cb = cq.Shape.centerOfMass(b); cb = np.array([cb.x, cb.y, cb.z])
            vr = v - vb; cr = (v * cen - vb * cb) / vr
            m = (vb * PCB_BOARD_DENSITY + vr * PCB_PART_DENSITY) / 1000
            cen = (vb * PCB_BOARD_DENSITY * cb + vr * PCB_PART_DENSITY * cr) / (m * 1000)
            dens = f"{PCB_BOARD_DENSITY} board / {PCB_PART_DENSITY} part boxes"
        else:
            m = v * info.density / 1000
            dens = info.density
        rows.append(dict(part=n, group=info.group, material=info.material, volume_mm3=round(v, 2), density_g_cm3=dens, mass_g=round(m, 4),
                         cog_x=round(float(cen[0]), 2), cog_y=round(float(cen[1]), 2), cog_z=round(float(cen[2]), 2)))
    return rows


def _cog(rows, group=None):
    sel = [r for r in rows if group is None or r["group"] == group]
    m = sum(r["mass_g"] for r in sel)
    return tuple(sum(r["mass_g"] * r[k] for r in sel) / m for k in ("cog_x", "cog_y", "cog_z"))


def check_mass(parts):
    rows = _mass_table(parts)
    tot = []
    for g, label in (("puck", "marker (all puck parts)"), ("cradle", "cradle assembly"), (None, "marker in cradle")):
        sel = [r for r in rows if g is None or r["group"] == g]
        c = _cog(rows, g)
        tot.append(dict(assembly=label, parts=len(sel), mass_g=round(sum(r["mass_g"] for r in sel), 2),
                        cog_x=round(c[0], 2), cog_y=round(c[1], 2), cog_z=round(c[2], 2)))
    cg = _cog(rows, "puck")
    tri = __import__("shapely.geometry", fromlist=["Polygon"]).Polygon(P.BALL_XY)
    inside = tri.contains(Point(cg[0], cg[1]))
    margin = tri.exterior.distance(Point(cg[0], cg[1])) if inside else -tri.exterior.distance(Point(cg[0], cg[1]))
    tip = math.degrees(math.atan2(margin, cg[2] + P.BALL_PROT)) if inside else 0.0
    notes = ["densities are typical handbook values, not measured (PROVISIONAL): PA12 MJF 1.01, glass 2.5, N-BK7 2.51, FR-4 1.85, stainless 7.9, epoxy 1.15, "
             "LiPo cell 2.1, camera module 2.5, PSA 1.0, VHB foam 0.72, PU foam 0.32; purchased parts are envelope solids, so their mass is an estimate",
             "solder, passives, conformal coat and cured adhesive fillets are not included (expect about +0.5 to 1 g on the marker)",
             f"marker centre of gravity is {margin:.1f} mm inside the triangle of the three ball feet (static tip-over angle about {tip:.0f} deg)"]
    return res(8, "mass and centre of gravity", inside,
               f"marker {tot[0]['mass_g']} g, CoG ({tot[0]['cog_x']}, {tot[0]['cog_y']}, {tot[0]['cog_z']}) mm; cradle assembly {tot[1]['mass_g']} g; "
               f"CoG {margin:.1f} mm inside the ball-foot triangle",
               [dict(title="Totals", rows=tot), dict(title="Per part", rows=rows)], notes,
               [] if inside else ["marker centre of gravity is outside the ball-foot triangle"])


# ==============================================================================================
# 9. quoting data and export integrity
# ==============================================================================================
def _facet_sag(name, tris):
    """Largest chord error of the print mesh on the main cylindrical wall of the part (None when not measurable)."""
    R = dict(tub=P.R_OUT, base_plate=P.BASE_R, cradle=P.NEST_R)[name]
    mid = 0.5 * (tris + np.roll(tris, 1, axis=1)).reshape(-1, 3)
    if name == "cradle":                                   # print frame: x' = -z, y' = y, z' = x - xmin
        z_model = -mid[:, 0]; x_model = mid[:, 2] - P.CRADLE_X
        r = np.hypot(x_model, mid[:, 1])
        on = (np.abs(r - R) < 0.05) & (z_model > 0.3) & (z_model < P.CRADLE_TOP_Z - 1.0) & (mid[:, 1] > -19.0) & (mid[:, 1] < P.STRIP_Y0)
        return float(R - r[on].min()) if on.any() else None
    r = np.hypot(mid[:, 0], mid[:, 1])
    zmid = (P.T - mid[:, 2]) if name == "tub" else mid[:, 2]
    lo, hi = (P.RIM_Z + M["bottom_chamfer"] + 0.2, P.T - M["top_fillet"] - 0.2) if name == "tub" else (0.1, P.BASE_T - 0.1)
    on = (np.abs(r - R) < 0.05) & (zmid > lo) & (zmid < hi)
    return float(R - r[on].min()) if on.any() else None


def check_quoting(parts):
    rows, fails, notes = [], [], []
    for name in ("tub", "base_plate", "cradle"):
        info = parts[name]
        s = A.solid_of(info)
        tris, src = _tris(parts, name, print_orientation=True)
        bb = A.bbox_of(A.print_orientation(name, info.shape))          # exact box of the solid in print orientation
        size = np.array(bb[3:]) - np.array(bb[:3])
        vol, area = G.mesh_volume_area(tris)
        closed = G.mesh_is_closed(tris)
        dv = abs(vol - s.Volume()) / s.Volume()
        ok = closed and dv < 0.005
        if not ok:
            fails.append(f"{name}: STL closed={closed}, volume differs {100 * dv:.2f} %")
        zmin = float(tris[:, :, 2].min())
        sag = _facet_sag(name, tris)
        if abs(zmin) > 1e-4:
            ok = False; fails.append(f"{name}: print file does not rest on z = 0 (z min {zmin:.4f})")
        if sag is not None and sag > A.PRINT_STL_TOL + 1e-3:
            ok = False; fails.append(f"{name}: facet sag {sag:.4f} mm exceeds the stated STL tolerance {A.PRINT_STL_TOL}")
        rows.append(dict(part=name, process=info.material, print_file=src, box_x_mm=R3(size[0]), box_y_mm=R3(size[1]), box_z_build_mm=R3(size[2]),
                         volume_cm3=round(s.Volume() / 1000, 3), stl_volume_cm3=round(vol / 1000, 3), surface_area_cm2=round(s.Area() / 100, 2),
                         mass_g=round(s.Volume() * info.density / 1000, 2), stl_triangles=len(tris), stl_watertight=closed,
                         stl_z_min_mm=round(zmin, 5), largest_facet_sag_on_the_main_radius_mm=(round(sag, 4) if sag is not None else "-"),
                         box_volume_cm3=round(float(np.prod(size)) / 1000, 2)))
    # export integrity: re-read every exported STEP and STL and compare with the solid that was checked
    irows = []
    if USE_EXPORTED:
        for name, info in parts.items():
            s = A.solid_of(info)
            step = A.STEP_DIR / f"{name}.step"
            stl = A.STL_PARTS_DIR / f"{name}.stl"
            try:
                rv = cq.importers.importStep(str(step)).val().Volume()
                tv, _ = G.mesh_volume_area(G.load_stl(stl))
                closed = G.mesh_is_closed(G.load_stl(stl))
            except Exception as e:
                fails.append(f"{name}: export unreadable ({e})"); continue
            ok = abs(rv - s.Volume()) < 1e-3 * max(1.0, s.Volume()) and abs(tv - s.Volume()) < 0.02 * s.Volume() + 0.01 and closed
            if not ok:
                fails.append(f"{name}: STEP {rv:.3f} / STL {tv:.3f} vs solid {s.Volume():.3f} mm3, closed={closed}")
            irows.append(dict(part=name, solid_volume_mm3=round(s.Volume(), 3), step_reimport_volume_mm3=round(rv, 3), stl_volume_mm3=round(tv, 3),
                              stl_watertight=closed, status="ok" if ok else "FAIL"))
        asm = A.STEP_DIR / "GL1_assembly.step"
        notes.append(f"{asm.name}: {asm.stat().st_size / 1e6:.2f} MB, {len(parts)} named parts" if asm.exists() else "GL1_assembly.step MISSING")
        if not asm.exists():
            fails.append("GL1_assembly.step missing")
    else:
        notes.append("export integrity not run (no export in this run)")
    notes += [f"print files: STL tolerance {A.PRINT_STL_TOL} mm linear, {A.PRINT_STL_ANG} rad angular, resting on z = 0; the same parts are exported as "
              "STEP in print orientation (export/step/*_print.step) - send the STEP when the bureau accepts it",
              f"part meshes for renders and mesh checks: {A.STL_TOL} mm linear, {A.STL_ANG} rad angular",
              "print orientation (z = build direction): tub roof-down; base plate flat; cradle with its x axis as the build direction, so that the side "
              "profile of the latch beam and of the lip lies in the build plane (orientation of the cradle is to be LOCKED with the bureau)",
              "facet sag = main radius minus the smallest mid-edge radius of the facets on the cylindrical wall (tub R 23.0, base R 21.75, cradle nest R 23.25)",
              "box = exact axis-aligned bounding box of the solid in print orientation"]
    return res(9, "printed parts for quoting / export integrity", not fails,
               ("; ".join(f"{r['part']} {r['box_x_mm']} x {r['box_y_mm']} x {r['box_z_build_mm']} mm, {r['volume_cm3']} cm3" for r in rows)
                + (f"; all {len(irows)} STEP and STL files re-read and match the checked solids" if irows else "")
                if not fails else "FAILED: " + "; ".join(fails)),
               [dict(title="Printed parts (print orientation)", rows=rows), dict(title="Export integrity (files re-read)", rows=irows)], notes)


# ==============================================================================================
# 10. support posts, 11. layout script, 12. tub keep-out contract
# ==============================================================================================
def _pcb_outline():
    return Point(0, 0).buffer(P.PCB_R, 256).intersection(sbox(-99, -99, 99, P.PCB_FLAT))


def check_posts(parts):
    """Each support post foot must land on the PCB top, clear every top-side part and the LCD glass by the fit clearance;
    the two posts E carry the spigots that locate the PCB."""
    S = _solids(parts)
    pcb = _pcb_outline()
    lcd = sbox(P.LCD_X0, P.LCD_Y0, P.LCD_X1, P.LCD_Y1)
    board_top = G.section_polys(PT.pcb_board().val(), "z", P.PCB_Z1 - 0.005)      # with the two locating holes
    feet = G.section_polys(S["tub"], "z", P.PCB_Z1 + 0.005)
    spig = G.section_polys(S["tub"], "z", 0.5 * (P.SPIGOT_Z0 + P.PCB_Z1))
    rows, ok = [], True
    for name, x0, x1, y0, y1 in P.post_rects():
        foot = sbox(x0, y0, x1, y1)
        edge = pcb.exterior.distance(foot) if pcb.contains(foot) else -1.0
        near, dmin = None, 1e9
        for p in P.TOP_PARTS:
            r = sbox(p["x"] - p["dx"] / 2, p["y"] - p["dy"] / 2, p["x"] + p["dx"] / 2, p["y"] + p["dy"] / 2)
            d = foot.distance(r)
            if d < dmin:
                dmin, near = d, p["ref"]
        # the post really exists in the tub solid and really reaches the PCB: a probe column must be all tub, and touch the board
        probe = PT.box(x0 + 0.1, x1 - 0.1, y0 + 0.1, y1 - 0.1, P.PCB_Z1, P.ROOF_Z).val()
        solid_frac = common_volume(S["tub"], probe) / probe.Volume()
        seat = feet.intersection(foot).intersection(board_top).area
        has_spigot = name[0] == M["locating_posts"]
        sp_area = spig.intersection(foot).area
        sp_ok = (abs(sp_area - math.pi * P.SPIGOT_D ** 2 / 4) < 0.01) if has_spigot else sp_area < 1e-6
        good = (edge >= P.PCB_EDGE_CLR and dmin >= P.CLR - 1e-9 and foot.distance(lcd) >= P.CLR - 1e-9 and solid_frac > 0.999 and seat > 0.5 and sp_ok)
        ok &= good
        rows.append(dict(post=name, x0=R3(x0), x1=R3(x1), y0=R3(y0), y1=R3(y1), to_pcb_edge_mm=R3(edge), nearest_part=near, gap_to_nearest_part_mm=R3(dmin),
                         gap_to_lcd_glass_mm=R3(foot.distance(lcd)), solid_from_pcb_to_roof_pct=round(100 * solid_frac, 1),
                         seat_area_on_pcb_mm2=round(seat, 2), locating_spigot=("dia %.1f x %.1f" % (P.SPIGOT_D, P.SPIGOT_H)) if has_spigot else "-", ok=good))
    area = sum(r["seat_area_on_pcb_mm2"] for r in rows)
    notes = ["post feet are the YAML tub_keepouts.post_feet (the contract with the PCB layout, proven in check 12); passives are not in the YAML",
             f"posts E seat on the PCB round their spigots: full annulus at the round hole, two strips beside the {P.LOC_SLOT[3]} mm slot "
             f"(the slot is wider than the {P.KO_POST_SIZE} mm foot)",
             f"intended load path roof -> posts -> PCB -> adhesive sheet -> base plate. Total seat area {area:.1f} mm2: an 800 N "
             f"footstep carried by the posts alone would be {800 / area:.0f} MPa (PA12 yields near 48 MPa). The side wall shares the load only "
             f"through the ledge and the perimeter joint into the edge of the base plate: its rim ends {P.RIM_Z} mm above the base plane (D23). "
             "The design review estimates that a load on the cover glass also passes through the roof ledge into the LCD glass. The footstep "
             "case is NOT analysed or tested (README open issues 3 to 5)"]
    return res(10, "support posts", ok, f"{len(rows)} posts on their keep-out squares, solid from PCB to roof, clear of listed parts and of the LCD glass; "
               f"two spigots under posts E; seat area {area:.1f} mm2" if ok else "post placement problem",
               [dict(title="Support posts", rows=rows)], notes)


def check_layout_script(parts=None):
    r = subprocess.run([sys.executable, str(P.DESIGN_DIR / "check_layout.py")], capture_output=True, text=True)
    lines = r.stdout.strip().splitlines()
    return res(11, "design/check_layout.py", r.returncode == 0, lines[-1] if lines else "no output",
               [dict(title="Output of design/check_layout.py (plan view and z stack of master_params.yaml)", rows=[dict(line=l) for l in lines])],
               [f"exit code {r.returncode}"] + ([r.stderr.strip()] if r.stderr.strip() else []))


KO_GRID = 0.4


def check_keepouts(parts):
    """Rev C contract with the PCB layout (YAML tub_keepouts): below the free height the tub may touch or hang over the
    PCB top side only inside the eight post-foot squares and the two camera-hood zones (there no lower than a 0.95 mm part)."""
    S = _solids(parts)
    tub = S["tub"]
    fails, warns = [], []
    zt, zf, zh = P.PCB_Z1, P.KO_FREE_Z, P.PCB_Z1 + P.KO_HOOD_MAX_H
    tol, half = 2e-4, P.KO_POST_SIZE / 2
    squares = [sbox(cx - half, cy - half, cx + half, cy + half) for cx, cy in P.KO_POST_CENTRES]
    zones = {s: sbox(cx - P.KO_HOOD_HW, P.KO_HOOD_Y0, cx + P.KO_HOOD_HW, P.KO_HOOD_Y1) for s, (cx, _) in P.CAM_XY.items()}
    # (a) boolean proof: the space the layout may fill = PCB outline x [PCB top, free height] minus the keep-outs
    space = PT.dprism(P.PCB_R, P.PCB_FLAT, zt, zf)
    for cx, cy in P.KO_POST_CENTRES:
        space = space.cut(PT.box(cx - half - tol, cx + half + tol, cy - half - tol, cy + half + tol, zt - 1, zf + 1))
    for s, (cx, _) in P.CAM_XY.items():
        space = space.cut(PT.box(cx - P.KO_HOOD_HW - tol, cx + P.KO_HOOD_HW + tol, P.KO_HOOD_Y0 - tol, P.KO_HOOD_Y1 + 1, zh, zf + 1))
    space = space.val()
    try:
        com = tub.intersect(space)
        v = sum(x.Volume() for x in com.Solids())
        where = ""
        if v > 1e-4:
            bb = com.BoundingBox()
            where = f" at x {bb.xmin:.2f}..{bb.xmax:.2f}, y {bb.ymin:.2f}..{bb.ymax:.2f}, z {bb.zmin:.2f}..{bb.zmax:.2f}"
    except Exception:
        v, where = float("nan"), ""
    if not v < 1e-4:
        fails.append(f"{v:.4f} mm3 of tub inside the layout space{where}")
    brow = [dict(test="tub solid INTERSECT (PCB outline x z %.2f..%.2f minus post-foot squares minus hood zones above z %.2f)" % (zt, zf, zh),
                 layout_space_volume_mm3=round(space.Volume(), 1), common_volume_mm3=round(v, 6), limit_mm3=1e-4, status="ok" if v < 1e-4 else "FAIL")]
    # (b) every keep-out against the tub sections
    pcb = _pcb_outline()
    feet = G.section_polys(tub, "z", zt + 0.005)
    krow = []
    for (name, x0, x1, y0, y1), sq in zip(P.post_rects(), squares):
        near = feet.intersection(sq.buffer(1.0)).intersection(pcb)
        inside, outside = near.intersection(sq).area, near.difference(sq.buffer(tol)).area
        okk = inside > 0.9 * sq.area and outside < 1e-6
        if not okk:
            fails.append(f"post foot {name}: {inside:.2f} mm2 inside its square, {outside:.4f} mm2 outside")
        krow.append(dict(keep_out=f"post foot {name}", yaml_centre=(round(0.5 * (x0 + x1), 3), round(0.5 * (y0 + y1), 3)), yaml_size_mm=f"{P.KO_POST_SIZE} x {P.KO_POST_SIZE}",
                         tub_area_inside_mm2=round(inside, 3), tub_area_outside_mm2=round(outside, 5), lowest_tub_above_pcb_mm=0.0,
                         allowed=">= 0 (contact)", status="ok" if okk else "FAIL"))
    lev = sorted({zh + 0.002, M["hood_skirt_z0"] + 0.01, 0.5 * (M["hood_skirt_z0"] + zf), zf - 0.002})
    secs = [G.section_polys(tub, "z", z).intersection(pcb) for z in lev]
    rc = G.RayCaster(tub)
    board_top = G.section_polys(PT.pcb_board().val(), "z", zt - 0.005)
    from shapely.prepared import prep
    pb = prep(board_top)
    xs = np.arange(-P.PCB_R + 0.5 * KO_GRID, P.PCB_R, KO_GRID)
    cls, hts, pts = [], [], []
    for x in xs:
        for y in np.arange(-P.PCB_R + 0.5 * KO_GRID, P.PCB_FLAT, KO_GRID):
            pt = Point(x, y)
            if not pb.contains(pt):
                continue
            t = rc.first_hit((x, y, zt - 0.02), (0, 0, 1), 1e-9, 20.0)
            hgt = max(0.0, (t if t is not None else 99.0) - 0.02)
            if any(sq.buffer(1e-6).contains(pt) for sq in squares):
                c = "post feet"
            elif any(z.buffer(1e-6).contains(pt) for z in zones.values()):
                c = "camera-hood zones"
            elif sbox(P.LCD_X0, P.LCD_Y0, P.LCD_X1, P.LCD_Y1).contains(pt):
                c = "under the LCD glass"
            else:
                c = "elsewhere on the PCB"
            cls.append(c); hts.append(hgt); pts.append((x, y))
    cls, hts, pts = np.array(cls), np.array(hts), np.array(pts)
    for s, z in zones.items():
        cx = P.CAM_XY[s][0]
        zone_pcb = z.intersection(pcb)
        low = [sec.intersection(zone_pcb) for sec in secs]
        used = max(g.area for g in low) / zone_pcb.area
        allm = [g for g in low if not g.is_empty]
        bx = (min(g.bounds[0] for g in allm), min(g.bounds[1] for g in allm), max(g.bounds[2] for g in allm), max(g.bounds[3] for g in allm)) if allm else (cx, 0, cx, 0)
        sel = cls == "camera-hood zones"
        sel &= np.abs(pts[:, 0] - cx) <= P.KO_HOOD_HW + 1e-6
        hmin = float(hts[sel].min()) if sel.any() else float("nan")
        okk = hmin >= P.KO_HOOD_MAX_H - NUM_TOL
        if not okk:
            fails.append(f"camera hood {s}: tub only {hmin:.2f} mm above the PCB inside the zone (parts up to {P.KO_HOOD_MAX_H} allowed)")
        krow.append(dict(keep_out=f"camera hood {s}", yaml_centre=(cx, round(0.5 * (P.KO_HOOD_Y0 + P.KO_HOOD_Y1), 3)),
                         yaml_size_mm=f"{2 * P.KO_HOOD_HW} x {P.KO_HOOD_Y1 - P.KO_HOOD_Y0:.1f}", tub_area_inside_mm2=round(max(g.area for g in low), 2),
                         tub_area_outside_mm2=f"hood spans x {bx[0] - cx:+.3f}..{bx[2] - cx:+.3f} of +-{P.KO_HOOD_HW}, from y {bx[1]:.3f} (zone from {P.KO_HOOD_Y0})",
                         lowest_tub_above_pcb_mm=round(hmin, 3), allowed=f">= {P.KO_HOOD_MAX_H} (part height)", status="ok" if okk else "FAIL"))
    # (c) height map of the tub above the PCB top (rays +z from the board top on a grid), by region
    hrow = []
    limits = {"post feet": 0.0, "camera-hood zones": P.KO_HOOD_MAX_H, "under the LCD glass": P.PCB_FREE_H, "elsewhere on the PCB": P.PCB_FREE_H}
    for c, lim_ in limits.items():
        sel = cls == c
        if not sel.any():
            continue
        i = int(np.argmin(np.where(sel, hts, np.inf)))
        okk = hts[i] >= lim_ - NUM_TOL
        if not okk:
            fails.append(f"{c}: tub {hts[i]:.2f} mm above the PCB at ({pts[i][0]:.1f}, {pts[i][1]:.1f}), contract minimum {lim_}")
        h = hts[sel]
        hrow.append(dict(region=c, grid_points=int(sel.sum()), lowest_tub_above_pcb_mm=round(float(h.min()), 3), at_xy=(round(float(pts[i][0]), 1), round(float(pts[i][1]), 1)),
                         contract_minimum_mm=lim_, share_below_free_height_pct=round(100 * float((h < P.PCB_FREE_H - NUM_TOL).mean()), 1),
                         share_between_free_height_and_roof_pct=round(100 * float(((h >= P.PCB_FREE_H - NUM_TOL) & (h < P.ROOF_Z - zt - 0.11)).mean()), 1),
                         share_at_roof_height_pct=round(100 * float((h >= P.ROOF_Z - zt - 0.11).mean()), 1), status="ok" if okk else "FAIL"))
    out = cls == "elsewhere on the PCB"
    low_out = float(hts[out].min())
    warns.append(f"D22: above the free height (z {zf:.2f}) the tub still hangs over the PCB outside the keep-outs: lowest feature {low_out:.2f} mm above the PCB top "
                 f"(z {zt + low_out:.2f}, glass locating rib), thick roof at z {P.BOND_Z:.2f}; design/check_layout.py allows parts to z {P.ROOF_Z - 0.1:.1f} there. "
                 "The contract needs a free height (PROPOSED_PARAM_CHANGES.md, part B)")
    notes = [f"free height = pcb.max_top_height_under_lcd = {P.PCB_FREE_H} mm above the PCB top (z {zf:.2f}): the height the layout may use everywhere on the "
             "board outside the keep-outs. 'Overhangs the PCB top side' is evaluated below this height; the YAML does not state one for the area outside the LCD (D22)",
             f"keep-out prisms are enlarged by {tol} mm so that a face lying exactly on the contract boundary does not count as an intrusion",
             f"hood zones: tub material is allowed from {P.KO_HOOD_MAX_H} mm above the PCB top upward; the camera cube is exempt (it is a part, not tub)",
             f"height map: {len(hts)} rays on a {KO_GRID} mm grid over the board top (locating holes excluded); the corner fill between hood and side wall starts "
             f"at y = {P.HOOD_FILL_Y0:.2f}, where the PCB outline has left the hood zone",
             "the seating ledge (r >= 21.35) lies outside the PCB (r 21.1) and is checked as a clearance in check 2"]
    okall = not fails
    return res(12, "tub keep-out contract (YAML tub_keepouts)", okall,
               (f"no tub material in the layout space below z {zf:.2f} ({v:.6f} mm3 common); eight post feet inside their {P.KO_POST_SIZE} mm squares; hood skirts "
                f"{min(r['lowest_tub_above_pcb_mm'] for r in krow if r['keep_out'].startswith('camera')):.2f} mm above the PCB inside the +-{P.KO_HOOD_HW} zones "
                f"(parts to {P.KO_HOOD_MAX_H}); lowest tub feature elsewhere {low_out:.2f} mm above the PCB" if okall else "FAILED: " + "; ".join(fails)),
               [dict(title="Boolean proof", rows=brow), dict(title="Keep-outs of the YAML against the tub solid", rows=krow),
                dict(title="Height of the tub above the PCB top by region (ray-cast height map)", rows=hrow)], notes, warns)


# ==============================================================================================
# 13. seal continuity
# ==============================================================================================
SEAL_ENVELOPE = (-26.0, 26.0, -26.0, 22.0, -2.0, 10.0)


def _air_solids(S, names):
    """The air round and inside the marker: a box minus every marker solid.  Returns the list of connected air solids."""
    air = PT.box(*SEAL_ENVELOPE).val()
    for n in names:
        air = air.cut(S[n])
    return list(air.Solids())


def check_seal(parts):
    """Is the marker closed?  (a) air-solid test: the outside and the inner cavity must be DIFFERENT connected air solids
    when every modelled seal (bead, adhesive sheet, pottings, window bonds, cover tape, vent disc) is in place;
    (b) the perimeter bead is one closed ring; (c) the width of every seal land, measured on the sections."""
    S = _solids(parts)
    puck = [n for n, i in parts.items() if i.group == "puck"]
    fails, warns = [], []
    cx, cy = P.CAM_XY["R"]
    cxl = P.CAM_XY["L"][0]
    rx, ry, _ = P.LOC_ROUND
    probes = [
        ("outside, above the marker", (0.0, 0.0, 9.5), "outside"),
        ("grain opening", (P.GRAIN_X + 0.5 * (P.BAFFLE_RO + P.GRAIN_R), P.GRAIN_Y, 0.3), "outside"),
        ("pad slot", (0.5 * (P.PAD_XS[3] + P.PAD_XS[4]), P.PAD_Y, 0.5), "outside"),
        ("vent hole (the membrane is modelled as a closed disc)", (P.VENT_XY[0], P.VENT_XY[1], P.T - 0.6), "outside"),
        ("cover-glass rim gap", (0.5 * (P.CG_D + P.RECESS_D) / 2, 0.0, P.T - 0.5), "outside"),
        ("window R side slot", (cx + 0.25 * (P.WIN_W + P.WIN_RECESS_W), P.Y_VISOR - 0.25, 5.5), "outside"),
        ("main cavity (beside the battery)", (-18.0, 5.0, 3.0), "cavity"),
        ("camera bay R", (cx + 1.5, 15.0, 6.7), "cavity"),
        ("camera bay L", (cxl - 1.5, 15.0, 6.7), "cavity"),
        ("camera opening R, behind the window", (cx, P.WIN_RECESS_FLOOR_Y - 0.1, P.AXIS_Z), "cavity"),
        ("cell between cover glass and LCD", (0.0, 0.0, 0.5 * (P.BOND_Z + P.CG_Z0)), "cavity"),
        ("PCB locating hole (round), under the spigot tip", (rx, ry, P.PCB_Z0 + 0.1), "closed pocket"),
        ("PCB locating slot, beside the spigot", (P.LOC_SLOT[0] + 0.5 * (P.LOC_SLOT[3] - 0.1), P.LOC_SLOT[1], P.PCB_Z0 + 0.1), "cavity"),
        ("radial gap PCB edge to ledge", (0.0, -0.5 * (P.PCB_R + P.LEDGE_RI), 1.5), "cavity"),
    ]
    arow, prow = [], []
    try:
        sols = _air_solids(S, puck)
        where = {}
        for name, pt, expect in probes:
            v = cq.Vector(*pt)
            hit = [i for i, a_ in enumerate(sols) if a_.isInside(v, 1e-6)]
            where[name] = hit[0] if hit else None
        i_out = where[probes[0][0]]
        i_cav = where["main cavity (beside the battery)"]
        known = set()
        for name, pt, expect in probes:
            i = where[name]
            got = "inside material" if i is None else ("outside" if i == i_out else ("cavity" if i == i_cav else "closed pocket"))
            ok = got == expect and i_out != i_cav
            if got == "closed pocket":
                known.add(i); got = f"closed pocket ({sols[i].Volume():.2f} mm3)"; ok = expect == "closed pocket" and i_out != i_cav
            if not ok:
                fails.append(f"{name}: {got} (expected {expect})" if i_out != i_cav else "the cavity is connected to the outside")
            prow.append(dict(probe=name, at_xyz=tuple(round(v_, 2) for v_ in pt), found_in=got, expected=expect, status="ok" if ok else "FAIL"))
        for i, a_ in sorted(enumerate(sols), key=lambda t: -t[1].Volume()):
            kind = "outside" if i == i_out else ("inner cavity" if i == i_cav else "closed pocket")
            if kind == "closed pocket" and i not in known and a_.Volume() > 0.05:
                fails.append(f"unexpected closed air pocket of {a_.Volume():.2f} mm3")
            bb = a_.BoundingBox()
            arow.append(dict(air_solid=kind, volume_mm3=round(a_.Volume(), 2), x=(round(bb.xmin, 1), round(bb.xmax, 1)), y=(round(bb.ymin, 1), round(bb.ymax, 1)),
                             z=(round(bb.zmin, 1), round(bb.zmax, 1)), contains=", ".join(n for n, _, _ in probes if where[n] == i) or "-"))
        if i_out is None or i_cav is None or i_out == i_cav:
            fails.append("outside and cavity are ONE connected air solid: the marker is open")
        v_cav = sols[i_cav].Volume() if i_cav is not None and i_cav != i_out else float("nan")
    except Exception as ex:
        fails.append(f"air-solid boolean failed: {ex!r}")
        v_cav = float("nan")
    # (b) the perimeter bead is one closed ring round the PCB
    brow = []
    for z in (0.5 * (P.BASE_T + P.LEDGE_Z0), 0.5 * (P.RIM_Z + P.BASE_T)):
        sec = G.section_polys(S["seal_bead"], "z", z)
        pcs = [g for g in getattr(sec, "geoms", [sec]) if not g.is_empty]
        closed = len(pcs) == 1 and len(pcs[0].interiors) == 1 and __import__("shapely.geometry", fromlist=["Polygon"]).Polygon(pcs[0].interiors[0]).contains(Point(0, 0))
        level = "joint on the seal land" if z > P.BASE_T else "fill of the radial groove (arc only: open across the visor front by design)"
        need = z > P.BASE_T
        if need and not closed:
            fails.append(f"perimeter bead at z = {z:.2f} is not one closed ring ({len(pcs)} pieces)")
        brow.append(dict(section_z=round(z, 3), level=level, pieces=len(pcs), closed_ring_round_the_interior=closed, area_mm2=round(sec.area, 2),
                         status="ok" if (closed or not need) else "FAIL"))
    # (c) seal lands
    from shapely.geometry import Polygon as SPoly
    lrow = []

    def land(name, value, note=""):
        lrow.append(dict(seal=name, land_width_mm=R3(value), note=note))
    bsec = G.section_polys(S["seal_bead"], "z", 0.5 * (P.BASE_T + P.LEDGE_Z0))
    face = G.section_polys(S["tub"], "z", P.LEDGE_Z0 + 1e-3).difference(G.section_polys(S["tub"], "z", P.LEDGE_Z0 - 1e-3).buffer(1e-6))   # tub faces at the seal plane
    joint = bsec.intersection(face).intersection(G.section_polys(S["base_plate"], "z", P.BASE_T - 1e-3))
    ws = []
    for ang in np.arange(-179.5, 180.0, 1.0):
        ray = __import__("shapely.geometry", fromlist=["LineString"]).LineString([(0, 0), (30 * math.cos(math.radians(ang)), 30 * math.sin(math.radians(ang)))])
        ws.append(joint.intersection(ray).length)
    land("base perimeter: bead between the tub seal face and the base top, narrowest radial width", min(ws),
         f"arc {P.BASE_R - P.LAND_RI:.2f}, front {P.BASE_FLAT - P.LAND_FLAT_IN:.2f}; plus the fill of the {P.CLR} mm radial groove ({P.BASE_T - P.RIM_Z:.2f} deep)")
    if min(ws) < 0.3:
        fails.append(f"seal land interrupted: bead width {min(ws):.3f} mm at one azimuth")
    psec = G.section_polys(S["pcb_adhesive"], "z", 0.5 * (P.PSA_Z0 + P.PSA_Z1))
    pg = max(getattr(psec, "geoms", [psec]), key=lambda g_: g_.area)
    ext = pg.exterior
    for ring in pg.interiors:
        hole = SPoly(ring); c0 = hole.centroid
        if hole.contains(Point(P.GRAIN_X, P.GRAIN_Y)) or hole.distance(Point(P.GRAIN_X, P.GRAIN_Y)) < P.GRAIN_R:
            nm = "adhesive sheet: grain opening to the PCB edge"
        elif abs(c0.y - P.PAD_Y) < 0.5:
            nm = "adhesive sheet: pad slot to the PCB edge"
        else:
            k = min(range(len(P.BALL_XY)), key=lambda i_: math.hypot(c0.x - P.BALL_XY[i_][0], c0.y - P.BALL_XY[i_][1]))
            nm = f"adhesive sheet: foot hole {k + 1} to the PCB edge (the hole itself is filled with epoxy)"
        land(nm, hole.distance(ext), "the sheet is the only barrier at the pad slot and the grain opening; a fillet round the PCB edge is the second one")
    for s_ in ("L", "R"):
        wsec = G.section_polys(S[f"window_bond_{s_}"], "y", 0.5 * (P.WIN_RECESS_FLOOR_Y + P.Y_VISOR - P.WIN_T))
        wg = max(getattr(wsec, "geoms", [wsec]), key=lambda g_: g_.area)
        land(f"visor window {s_}: adhesive frame, narrowest side", SPoly(wg.interiors[0]).distance(wg.exterior) if wg.interiors else 0.0,
             f"sides {(P.WIN_W - 2 * P.OPEN_HALF_W) / 2:.2f}, sill {P.OPEN_Z0 - P.WIN_Z0:.2f}, top {P.WIN_Z0 + P.WIN_H - P.OPEN_Z1:.2f}; the side gaps of the recess are filled too")
    land("cover glass: tape ring", (P.CG_D - M["cover_tape_id"]) / 2, "VHB ring on the recess floor")
    land("vent: adhesive ring of the membrane disc", (M["vent_od"] - M["vent_area_dia"]) / 2, "PROVISIONAL part data")
    land("ball feet: epoxy plug in the through hole, length of the leak path", P.BASE_T, f"annulus {(P.BALL_HOLE_D - P.BALL_D) / 2:.3f} round the ball, then the backfilled sheet hole")
    notes = ["air-solid test: a box minus all marker solids; each remaining solid is one connected body of air. The marker is closed when the "
             "outside and the cavity are different bodies. Adhesives are modelled as cured, at nominal size; this proves that no modelled opening "
             "by-passes a seal - it does not prove that the adhesive wets or fills (leak test of every unit)",
             f"free air volume of the sealed cavity: {v_cav:.0f} mm3 (for the leak-test and vent calculations); it includes the cell between cover glass and LCD, "
             f"which breathes through the {M['lcd_psa_vent_w']} mm channel of the LCD adhesive frame",
             "the round PCB locating hole is closed by the foot of post E- that seats round it: 0.39 mm3 of trapped air, harmless; the slot is longer "
             "than the post foot and stays open to the cavity",
             "first rev C model: two key notches crossed the seal land and connected cavity and outside (design review); the base plate now has a "
             "plain edge and the bead is one ring"]
    return res(13, "seal continuity (air-solid test)", not fails,
               (f"outside and inner cavity are separate air solids (cavity {v_cav:.0f} mm3 incl. the cell under the cover glass); perimeter bead is one closed ring, "
                f"narrowest joint {min(ws):.2f} mm; adhesive-sheet lands {min(r['land_width_mm'] for r in lrow if r['seal'].startswith('adhesive sheet')):.2f} mm and more"
                if not fails else "FAILED: " + "; ".join(dict.fromkeys(fails))),
               [dict(title="Probe points", rows=prow), dict(title="Connected air solids (box minus all marker solids)", rows=arow),
                dict(title="Perimeter bead sections", rows=brow), dict(title="Seal lands", rows=lrow)], notes, warns)


# ==============================================================================================
# 14. assembly paths
# ==============================================================================================
def _turn_x(shape, y0, z0, deg):
    """Rotate about the axis parallel to x through (y0, z0); positive angle lifts +y points to +z."""
    return shape.rotate(cq.Vector(0, y0, z0), cq.Vector(1, y0, z0), deg) if abs(deg) > 1e-12 else shape


def check_assembly_paths(parts):
    """Blind assembly steps proven on the solids: (a) the LCD glass (with its adhesive frame) tilted in past the seating
    ledge; (b) the PCB / base unit lowered straight into the tub with the lateral error a guide may leave; (c) the same
    unit closed about a hinge behind the tub (the motion that lets the LCD tail be mated with the unit open)."""
    S = _solids(parts)
    tub = S["tub"]
    fails, warns = [], []
    lim = 1e-4
    # ---------------- (a) LCD tilt-in
    lcd = cq.Compound.makeCompound([S["lcd_glass"], S["lcd_adhesive"]])
    tau, bias = M["lcd_tilt_deg"], M["lcd_bias"]
    y0, z0 = P.LCD_Y0, P.BOND_Z                               # rear top edge of the glass + frame
    rise = P.LCD["dy"] * math.sin(math.radians(tau))          # the front edge trails this far behind the rear edge
    seq = [(tau, bias, -(z0 - P.RIM_Z - 0.1), "rear edge enters the rim, glass tilted, shifted toward the visor"),
           (tau, bias, -(z0 - P.LEDGE_Z0 - 0.05), "rear edge at the underside of the seating ledge"),
           (tau, bias, -(z0 - 0.5 * (P.LEDGE_Z0 + P.LEDGE_Z1)), "rear corners inside the ledge ring"),
           (tau, bias, -(z0 - P.LEDGE_Z1 - 0.05), "rear edge leaves the ledge"),
           (tau, bias, -(z0 - P.LEDGE_Z1 - 0.9), "rear edge above the ledge"),
           (tau, bias, -(z0 - (P.SPIGOT_Z0 + rise) + 0.15), "last shifted pose: front edge just below the spigot tips"),
           (tau, 0.0, -(z0 - (P.SPIGOT_Z0 + rise) + 0.15), "glass pushed back to its final y (rear corners above the ledge)"),
           (tau, 0.0, -0.8, "rear edge rising to the roof"), (tau, 0.0, -0.3, "rear edge 0.3 below the bonding plane"),
           (0.66 * tau, 0.0, -0.2, "front hinged up"), (0.33 * tau, 0.0, -0.1, "front hinged up"), (1.0, 0.0, -0.05, "nearly flat"),
           (0.0, 0.0, 0.0, "seated on the bonding plane (contact)")]
    lrow = []
    for i, (t_, dy, dz, what) in enumerate(seq, 1):
        sh = _turn_x(lcd, y0, z0, -t_).translate(cq.Vector(0, dy, dz))
        v = common_volume(sh, tub)
        d = min_distance(sh, tub)
        zf = z0 + dz - P.LCD["dy"] * math.sin(math.radians(t_))
        ok = v < lim
        if not ok:
            fails.append(f"LCD tilt-in pose {i}: {v:.4f} mm3 of interference with the tub")
        lrow.append(dict(pose=i, what=what, tilt_deg=round(t_, 2), shift_toward_visor_mm=dy, rear_edge_z=R3(z0 + dz), front_edge_z=R3(zf),
                         interference_with_tub_mm3=round(v, 5), smallest_gap_to_tub_mm=R3(d), status="ok" if ok else "FAIL"))
    flat = lcd.translate(cq.Vector(0, P.CLR, -(z0 - 0.5 * (P.LEDGE_Z0 + P.LEDGE_Z1))))
    lrow.append(dict(pose="-", what=f"for comparison: glass kept FLAT and shifted {P.CLR} (the rev B method, no longer used)", tilt_deg=0.0, shift_toward_visor_mm=P.CLR,
                     rear_edge_z=R3(0.5 * (P.LEDGE_Z0 + P.LEDGE_Z1)), front_edge_z=R3(0.5 * (P.LEDGE_Z0 + P.LEDGE_Z1)),
                     interference_with_tub_mm3=round(common_volume(flat, tub), 5), smallest_gap_to_tub_mm=R3(min_distance(flat, tub)), status="information"))
    gap_ledge = min(r["smallest_gap_to_tub_mm"] for r in lrow[1:4])
    if gap_ledge < P.CLR - NUM_TOL:
        fails.append(f"LCD tilt-in: only {gap_ledge:.3f} mm to the ledge")
    # ---------------- (b), (c) PCB / base unit
    unit_names = ["main_pcb", "camera_L", "camera_R", "prism_L", "prism_R", "battery", "pcb_adhesive", "base_plate"] + \
                 [f"{k}_{i}" for i in range(1, len(P.BALL_XY) + 1) for k in ("ball", "ball_epoxy")]
    optics = cq.Compound.makeCompound([S[n] for n in ("camera_L", "camera_R", "prism_L", "prism_R")])
    board = cq.Compound.makeCompound([S[n] for n in ("main_pcb", "battery", "pcb_adhesive", "base_plate")])
    fixed = cq.Compound.makeCompound([S[n] for n in ("lcd_glass", "lcd_adhesive", "foam_pad", "vent")])
    o = M["join_offset"]
    offs = [(0.0, 0.0), (o, o), (o, -o), (-o, o), (-o, -o)]
    jrow = []
    for drop in M["join_drops"]:
        worst, dmin_o, dmin_b = 0.0, float("inf"), float("inf")
        for ox, oy in offs:
            mv = cq.Vector(ox, oy, -drop)
            a_, b_ = optics.translate(mv), board.translate(mv)
            worst = max(worst, common_volume(a_, tub), common_volume(b_, tub))
            if (ox, oy) == (0.0, 0.0):
                worst = max(worst, common_volume(b_, fixed))
            else:
                dmin_o = min(dmin_o, min_distance(a_, tub))
                if (ox, oy) == (o, o):
                    dmin_b = min_distance(b_, tub)
        ok = worst < lim
        if not ok:
            fails.append(f"PCB / base unit {drop} mm below its seat with {o} mm lateral error: {worst:.4f} mm3 of interference")
        jrow.append(dict(unit_below_its_seat_mm=drop, lateral_error_tested_mm=f"0 and +-{o} in x and y", prism_top_z=R3(P.PRISM_Z1 - drop), pcb_top_z=R3(P.PCB_Z1 - drop),
                         worst_interference_mm3=round(worst, 5), cameras_and_prisms_to_tub_mm=R3(dmin_o), board_and_base_to_tub_mm=R3(dmin_b),
                         status="ok" if ok else "FAIL"))
    hy, hz = M["hinge_y"], M["hinge_z"]
    hrow = []
    for th in M["hinge_open_deg"]:
        a_, b_ = _turn_x(optics, hy, hz, -th), _turn_x(board, hy, hz, -th)
        v = max(common_volume(a_, tub), common_volume(b_, tub), common_volume(b_, fixed))
        d_o, d_b = min_distance(a_, tub), min_distance(b_, tub)
        ok = v < lim
        if not ok:
            fails.append(f"hinged close, unit open by {th} deg: {v:.4f} mm3 of interference")
        j1 = next(q for q in P.TOP_PARTS if q["ref"] == "J1")
        my, mz = j1["y"] - j1["dy"] / 2, P.FLEX_ZB
        t = math.radians(th)
        qy = hy + (my - hy) * math.cos(t) + (mz - hz) * math.sin(t); qz = hz - (my - hy) * math.sin(t) + (mz - hz) * math.cos(t)
        hrow.append(dict(unit_open_by_deg=th, front_edge_of_the_base_below_the_rim_mm=R3((P.BASE_FLAT - hy) * math.sin(t) - P.RIM_Z), interference_mm3=round(v, 5),
                         cameras_and_prisms_to_tub_mm=R3(d_o), board_and_base_to_tub_mm=R3(d_b),
                         J1_mouth_to_the_glass_rear_edge_mm=R3(math.hypot(qy - P.LCD_Y0, qz - P.LCD_Z0)), status="ok" if ok else "FAIL"))
    cap = (P.LOC_ROUND[2] - (P.SPIGOT_D - 2 * M["spigot_tip_chamfer"])) / 2
    notes = [f"(a) LCD: glass with its adhesive frame, rear edge first at {tau} deg, shifted {bias} mm toward the visor while the rear corners pass the "
             f"seating ledge (r {P.LEDGE_RI}); the front edge is then still below the spigot tips (z {P.SPIGOT_Z0:.1f}) and the post feet, so the shift is free. Smallest gap to the "
             f"ledge {gap_ledge:.2f} mm (flat insertion: {lrow[-1]['smallest_gap_to_tub_mm']} mm). The frame is applied to the LCD, not to the roof",
             f"(b) the unit = PCB with cameras, prisms, battery, adhesive sheet, base plate and potted feet (the base is laminated to the PCB before the "
             f"join). Straight descent with +-{o} mm of lateral error in x and y until the spigots engage ({P.SPIGOT_H} mm before the seat); the "
             f"{M['spigot_tip_chamfer']} mm tip chamfer of the spigots captures up to {cap:.3f} mm. The hood gaskets (compressible) and the wet seal adhesive are not part of this test",
             f"(c) hinge axis parallel to x at y = {hy}, z = {hz} (join fixture). The last column is the straight distance from the mouth of J1 to the rear "
             "edge of the LCD glass: the length of free tail needed to mate the connector at that opening (the real tail length is PROVISIONAL)",
             "these are nominal solids: the paths show that the motion exists and how much room it has, not that every printed part allows it "
             "(go gauges in the assembly sequence)"]
    return res(14, "assembly paths (LCD tilt-in, PCB / base join)", not fails,
               (f"LCD glass tilts in at {tau} deg with {gap_ledge:.2f} mm to the ledge ({len(seq)} poses, no interference); the PCB / base unit descends with "
                f"+-{o} mm lateral error ({len(jrow)} heights) and closes about the fixture hinge ({len(hrow)} angles) without interference"
                if not fails else "FAILED: " + "; ".join(fails)),
               [dict(title="LCD tilt-in (glass + adhesive frame against the tub)", rows=lrow),
                dict(title="PCB / base unit, straight descent", rows=jrow), dict(title="PCB / base unit, hinged close", rows=hrow)], notes, warns)


CHECKS = [check_interference, check_clearances, check_fov, check_fold, check_walls, check_trapped, check_cradle, check_mass,
          check_quoting, check_posts, check_layout_script, check_keepouts, check_seal, check_assembly_paths]


# ==============================================================================================
# report
# ==============================================================================================
def _cell(v):
    if isinstance(v, float):
        return f"{v:g}"
    if isinstance(v, (tuple, list)):
        return "(" + ", ".join(_cell(x) for x in v) + ")"
    return str(v).replace("|", "/")


def _md_table(rows):
    if not rows:
        return ["(none)", ""]
    keys = list(rows[0])
    out = ["| " + " | ".join(k.replace("_", " ") for k in keys) + " |", "|" + "---|" * len(keys)]
    out += ["| " + " | ".join(_cell(r.get(k, "")) for k in keys) + " |" for r in rows]
    return out + [""]


def write_report(results, elapsed=None):
    P.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    ok = all(r["passed"] for r in results)
    (P.EXPORT_DIR / "check_report.json").write_text(json.dumps(
        dict(rev=P.REV, all_passed=ok, results=results, deviations=DEVIATIONS), indent=1, default=str))
    md = [f"# GL-1 mechanical check report (parameters rev {P.REV})", "",
          "Generated by `python3 cad/build.py`. PROVISIONAL: nothing has been built or measured; every number below is computed from the CAD model.",
          "", f"**Overall: {'all checks pass' if ok else 'CHECKS FAILED'}**; {sum(len(r['warnings']) for r in results)} warnings; "
          f"{len(DEV_OPEN)} recorded deviations from the specification still stand, {len(DEV_CLOSED)} are closed (listed at the end).", "",
          "| # | Check | Result | Warnings | Summary |", "|---|---|---|---|---|"]
    for r in results:
        md.append(f"| {r['id']} | {r['name']} | {'PASS' if r['passed'] else 'FAIL'} | {len(r['warnings'])} | {r['summary'].replace('|', '/')} |")
    md.append("")
    for r in results:
        md += [f"## {r['id']}. {r['name']}: {'PASS' if r['passed'] else 'FAIL'}", "", r["summary"], ""]
        if r["warnings"]:
            md += ["Warnings:", ""] + [f"- {w}" for w in r["warnings"]] + [""]
        if r["notes"]:
            md += ["Notes:", ""] + [f"- {n}" for n in r["notes"]] + [""]
        for t in r["tables"]:
            md += [f"### {t['title']}", ""] + _md_table(t["rows"])
    md += ["## Deviations from the specification", "",
           "Status: accepted = accepted by the system owner in rev C; recorded = differs from the task text for the stated reason; open = needs a "
           "decision. Items marked YAML are detailed in PROPOSED_PARAM_CHANGES.md (master_params.yaml is not edited).", ""]
    for d in DEV_OPEN:
        md += [f"- **{d['id']} {d['part']}** [{d['status']}]{' (YAML)' if d['yaml_change'] else ''}: required: {d['requirement']}. "
               f"Implemented: {d['implemented']}. Reason: {d['reason']}."]
    md += ["", "Closed:", ""]
    for d in DEV_CLOSED:
        md += [f"- {d['id']} {d['part']}: {d['requirement']} -> {d['implemented']} ({d['reason']})."]
    md.append("")
    (P.EXPORT_DIR / "check_report.md").write_text("\n".join(md))


def run_all(parts, write=True):
    results = []
    for fn in CHECKS:
        t = time.time()
        r = fn(parts)
        results.append(r)
        print(f"[{'PASS' if r['passed'] else 'FAIL'}] {r['id']:2d} {r['name']}: {r['summary']}  ({time.time() - t:.1f} s)", flush=True)
        for w in r["warnings"]:
            print(f"        warning: {w}", flush=True)
    if write:
        write_report(results)
    return results
