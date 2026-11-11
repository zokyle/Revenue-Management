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
  7 cradle              pins on the pads, orientation key, hold-down (retention, latch strain, forces), posed insertion path
  8 mass                mass and centre of gravity
  9 quoting             printed-part boxes / volumes and export integrity (STEP and STL re-read)
 10 support posts, 11 design/check_layout.py
 12 tub keep-outs       the YAML tub_keepouts contract proven on the tub solid
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
    vs, ts = shape.tessellate(A.STL_TOL, A.STL_ANG)
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
    add("Base plate to tub side wall and key lugs, radial", _sec_dist(S["base_plate"], tub, "z", 0.5 * P.BASE_T), clr, nominal=clr,
        method=f"section z = {0.5 * P.BASE_T:.2f}")
    bead = G.RayCaster(tub).first_hit((0.0, -0.5 * (P.LAND_RI + P.BASE_R), P.BASE_T + 1e-6), (0, 0, 1), 1e-9, 5.0)
    add("Base plate top to tub seal face (adhesive bead)", (bead or float("nan")) + 1e-6, P.BEAD_T, nominal=P.BEAD_T,
        method="ray +z from the seal land", note="rev C: 0.87 mm plate, bead 0.33 mm")
    add("Ball foot top to the PCB underside", min_distance(S["ball_1"], S["main_pcb"]), 0.05, nominal=P.PCB_Z0 - P.BALL_TOP_Z,
        note="the ball stands 0.03 above the plate inside the 2.0 mm hole of the adhesive sheet")
    add("Potting epoxy dome to the PCB underside", min_distance(S["ball_epoxy_1"], S["main_pcb"]), 0.0, nominal=P.PCB_Z0 - P.EPOXY_Z1,
        note="dome height is a process limit: it must stay below the sheet thickness")
    add("Potting epoxy dome to the adhesive-sheet hole, radial", min_distance(S["ball_epoxy_1"], S["pcb_adhesive"]), 0.1,
        nominal=(P.PSA_FOOT_HOLE_D - M["epoxy_cap_dia"]) / 2)
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
    # --- vent, flex, bottom-side parts
    others = [n for n, i in parts.items() if i.group == "puck" and n not in ("tub", "vent")]
    dv, nv = min((min_distance(S["vent"], S[n]), n) for n in others)
    add(f"Vent disc to nearest part ({nv})", dv, clr)
    add("LCD flex (representative shape) to tub", min_distance(S["lcd_flex"], tub), 0.0, note="PROVISIONAL tail geometry")
    add("LCD flex (representative shape) to connector J1 / PCB parts", min_distance(S["lcd_flex"], S["main_pcb"]), 0.0,
        note="PROVISIONAL tail geometry")
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
    add("Tub rim above the nest floor (ball protrusion)", min_distance(tub, cr), P.BALL_PROT, nominal=P.BALL_PROT,
        note="the three balls carry the marker; the rim is 0.10 mm clear of the printed floor")
    add("Lip underside to the tub top", min_distance(tub, lipS), clr, nominal=clr)
    add("Latch (retaining face and beam) to the tub", min_distance(tub, latchS), clr, nominal=clr)
    for sd_ in ("L", "R"):
        add(f"Lip to visor window {sd_}", min_distance(lipS, S[f"visor_window_{sd_}"]), clr, note="the lip must not touch the windows")
    add("Lip to cover glass", min_distance(lipS, S["cover_glass"]), clr)
    add("Latch hook to cover glass", min_distance(latchS, S["cover_glass"]), clr)
    vh = PT.cyl(P.VENT_XY[0], P.VENT_XY[1], P.VENT_HOLE_D / 2, P.T - 0.5, P.T + 0.5).val()
    add("Lip and latch to the vent hole", min(min_distance(lipS, vh), min_distance(latchS, vh)), clr)
    add("Latch to the walls of its well (side gaps, stop ribs)", _sec_dist(latchS, body_nl, "z", 1.0), 0.5, nominal=M["latch_side_gap"],
        method="section z = 1.00", note="minimum printable gap taken as 0.5 mm; the stop ribs are 1.57 mm behind the beam")
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
        worst = min(O.bundle("R", th, tv, rc, shift=sh)["total_fraction"] for _, th, tv in O.field_points())
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
             f"paraxial check: virtual pupil {P.VIRTUAL_PUPIL_BEHIND_EXIT:.3f} mm behind the exit face (y = {P.VIRTUAL_PUPIL_Y:.3f}), z = {P.AXIS_Z}",
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
            land = P.HORN_X_OUT - (P.CAM_X + P.WIN_RECESS_W / 2)
            sg = 1 if cx > 0 else -1
            xa, xb = sorted((sg * (P.CAM_X + P.WIN_RECESS_W / 2 - e), sg * (P.HORN_X_OUT + e)))
            f.append((f"camera {side}: land between the window recess and the D corner ({land:.2f} mm wide; its top outer edge carries the R{M['top_fillet']} "
                      "of the arc)", "", 0.6, [(xa, P.WIN_RECESS_FLOOR_Y - e, P.T - M["top_fillet"] - e, xb, P.Y_VISOR + e, P.T + e)]))
        ch = M["bottom_chamfer"]
        f.append((f"foot of the side wall at the specified {ch} mm bottom chamfer (all round the arc)", "", P.WALL - ch,
                  [(-P.R_OUT - e, -P.R_OUT - e, -e, P.R_OUT + e, P.R_OUT + e, ch + e)]))
    if name == "cradle":
        hw = M["latch_w"] / 2
        f.append((f"latch hook nose: solid 60 deg wedge ending in a {M['hook_nose_flat']} mm flat (an edge, not a wall)", "", M["hook_nose_flat"],
                  [(-hw - e, -P.NEST_R - e, P.HOOK_Z0 - e, hw + e, -P.HOOK_R + 3.2, P.HOOK_LEAD_Z0 + 1.0)]))
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
              f"({M['latch_h']} mm, root {M['latch_h']} mm >= 1.0) and every wall of the cradle are above the rule"]
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
        if c[1] > P.KEY_NOTCH_Y0 - 0.5:
            return "key notch"
        return "edge"
    if abs(c[0]) < P.WELL_HX + 0.5 and P.WELL_Y0 - 0.5 < c[1] < P.WELL_Y1 + 0.5 and c[2] > M["latch_root_z"] - 0.5:
        return "latch well (gap round the cantilever, open at the top)"
    if abs(c[1] - P.PAD_Y) < 2 and abs(c[0]) < 10:
        return "spring-pin slot (through)"
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


def _latch_travel_needed(tub_posed, latch, d_max=3.0, tol=1e-4):
    """Smallest hook travel at which the posed tub no longer intersects the deflected latch (bisection on the solids)."""
    vol = lambda d: common_volume(tub_posed, H.latch_deflected(latch, d))
    if vol(0.0) <= tol:
        return 0.0
    if vol(d_max) > tol:
        return float("inf")
    lo, hi = 0.0, d_max
    for _ in range(10):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if vol(mid) > tol else (lo, mid)
    return hi


def check_cradle(parts):
    """Rev C dock: seven pin positions on the pads, one orientation, lip + latch hold-down proven with numbers, and the
    nose-first insertion path proven by posing the marker solids against the cradle solids."""
    S = _solids(parts)
    cr, tub, base, psa = S["cradle"], S["tub"], S["base_plate"], S["pcb_adhesive"]
    fails, warns = [], []
    latch = PT.latch().val()
    v_l = common_volume(cr, latch)
    if abs(v_l - latch.Volume()) > 0.01 * latch.Volume():
        fails.append(f"the latch is not present in the cradle solid as designed ({v_l:.1f} of {latch.Volume():.1f} mm3)")
    body_nl = cr.cut(latch)                                   # the cradle with the latch removed (it deflects during insertion)
    lw = M["lip_half_w"]
    lipS = cr.intersect(PT.box(-lw - 0.5, lw + 0.5, P.LIP_Y0 - 0.5, P.CRADLE_Y1 + 1, P.CRADLE_TOP_Z + 0.01, P.LIP_Z1 + 1).val())
    rc, rt = G.RayCaster(cr), G.RayCaster(tub)
    rp = M["pin_plunger_dia"] / 2

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
        good = off < 1e-3 and tip_gap < 1e-3 and v0 < 1e-6 and d0 >= P.CLR - NUM_TOL and abs(work - (P.PIN_WORK_H - P.PIN_TIP_GAP)) < 1e-3
        if not good:
            fails.append(f"pin {i + 1}")
        prow.append(dict(pin=i + 1, x=x, fitted="consumer + factory" if i < len(P.PINS_CONSUMER) else "factory fixture only",
                         axis_to_pad_centre_mm=round(off, 4), tip_to_pad_face_mm=round(tip_gap, 4),
                         clearance_in_base_and_adhesive_slot_mm=R3(d0), height_above_cradle_pcb_mm=R3(work), ok=good))
    if abs(cpcb_top - (P.CRADLE_PAD_Z - P.PIN_WORK_H)) > 1e-6:
        fails.append(f"cradle PCB top at z = {cpcb_top:.3f}, not pad plane {P.CRADLE_PAD_Z} - working height {P.PIN_WORK_H}")

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
    sec = G.section_polys(cr, "z", 2.0).intersection(sbox(-P.WELL_HX + 0.01, P.STOP_RIB_Y1 + 0.01, P.WELL_HX - 0.01, P.WELL_Y1 - 0.01))
    bx = sec.bounds if not sec.is_empty else (0, 0, 0, 0)
    meas("latch beam width b (section z = 2.0)", bx[2] - bx[0], M["latch_w"])
    meas("latch beam thickness h (section z = 2.0)", bx[3] - bx[1], M["latch_h"], note="uniform; root >= 1.0 mm required")
    t = rc.first_hit((0, P.LATCH_Y_BACK - 0.8, 2.0), (0, 0, -1))
    z_root = 2.0 - t if t else float("nan")
    yc = -0.5 * (P.TUB_TOP_FLAT_R + P.HOOK_R)
    t = rc.first_hit((0, yc, P.T + 0.001), (0, 0, 1), 1e-9, 5.0)
    z_hook = P.T + 0.001 + t if t else float("nan")
    meas("latch root (well floor) z", z_root, M["latch_root_z"])
    meas("retaining face z", z_hook, P.HOOK_Z0)
    meas("latch free length L (root to retaining face)", z_hook - z_root, P.LATCH_L)
    meas("retaining face above the tub top", z_hook - P.T, P.CLR)
    r_nose = rc.first_hit((0, 0, P.HOOK_Z0 + M["hook_nose_flat"] / 2), (0, -1, 0))
    lo, hi = P.HOOK_R, P.R_OUT
    for _ in range(40):                                       # outer radius of the flat top of the tub at the rear
        mid = 0.5 * (lo + hi)
        tt = rt.first_hit((0, -mid, P.T + 1.0), (0, 0, -1))
        lo, hi = (mid, hi) if (tt is not None and abs(tt - 1.0) < 1e-6) else (lo, mid)
    meas("hook nose radius", r_nose, P.HOOK_R)
    meas("flat top of the tub ends at radius", lo, P.TUB_TOP_FLAT_R, note="top edge radius 0.6 outside it")
    meas("hook overlap u on the flat tub top", lo - (r_nose or float("nan")), P.HOOK_OVERLAP)
    t = rc.first_hit((M["stop_rib_x"], P.LATCH_Y_BACK - 0.005, M["guard_top_z"] - 0.5), (0, -1, 0))
    meas("beam back face to the over-travel stop ribs", (t or float("nan")) + 0.005, P.LATCH_STOP_GAP,
         note=f"contact when the hook has travelled {M['latch_stop_deflection']} mm")
    y_tip = rc.first_hit((0, 0, 0.5 * (P.LIP_Z0 + P.LIP_Z1)), (0, 1, 0))
    meas("lip overlap on the tub top", P.Y_VISOR - (y_tip or float("nan")), M["lip_overlap"])
    t = rc.first_hit((0, P.Y_VISOR - M["lip_overlap"] / 2, P.T + 0.001), (0, 0, 1), 1e-9, 5.0)
    meas("lip underside above the tub top", (t or float("nan")) + 0.001, P.CLR)
    lb = lipS.BoundingBox()
    meas("lip width", lb.xmax - lb.xmin, 2 * lw, note=f"window recesses start at |x| = {P.CAM_X - P.WIN_RECESS_W / 2}")
    meas("lip plate thickness", lb.zmax - P.LIP_Z0, M["lip_t"])

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
        dl = _latch_travel_needed(tp, latch)
        d_need = max(d_need, dl)
        ok = v_fix < 1e-4 and v_pin < 1e-6 and comp <= M["pin_full_stroke"] and dl <= M["latch_stop_deflection"]
        if not ok:
            fails.append(f"insertion pose {th} deg: body/lip {v_fix:.4f} mm3, pins {v_pin:.5f} mm3, latch travel {dl:.2f}, pin compression {comp:.2f}")
        irow.append(dict(tilt_deg=th, set_back_mm=round(s_, 3), lift_mm=round(h_, 3), rear_edge_height_mm=round(H.xf(-P.R_OUT, 0.0, th, s_, h_)[1], 2),
                         interference_with_nest_lip_floor_mm3=round(v_fix, 5), clearance_to_lip_mm=R3(d_lip),
                         plungers_into_base_or_adhesive_mm3=round(v_pin, 6),
                         slot_centre_offset_from_pin_axis_mm=(round(y_slot - P.PAD_Y, 3) if engaged else "pins not yet in the slot"),
                         pin_compression_mm=round(comp, 3), latch_travel_needed_mm=round(dl, 3), status="ok" if ok else "FAIL"))

    # ---------------- (d) forces, retention, strain (closed form, on the dimensions verified above)
    mt = _mass_table(parts)
    m_puck = sum(r["mass_g"] for r in mt if r["group"] == "puck")
    cg = _cog(mt, "puck")
    c = H.calc(m_puck, cg[1], d_insert=d_need)
    lim, req = M["latch_strain_limit"], M["retention_factor_required"]
    if c["factor"] < req or c["factor_min"] < req:
        fails.append(f"retention {c['factor']:.2f} x (nominal) / {c['factor_min']:.2f} x (marker fully forward) is below {req} x the seven-pin force")
    if max(c["eps_stop"], c["eps_ins"], c["eps_rel_max"]) > lim + 1e-9:
        fails.append(f"latch strain {100 * max(c['eps_stop'], c['eps_ins']):.2f} % exceeds {100 * lim} %")
    if c["d_rel_max"] > c["d_stop"]:
        fails.append("the over-travel stop engages before the hook has released")
    if M["latch_h"] < 1.0 - 1e-9:
        fails.append("latch root thinner than 1.0 mm")
    N2 = lambda v: round(float(v), 2)
    frow = [
        dict(quantity="pin force, seven pins (factory fixture) / four pins (consumer)", value=(N2(c["Fp7"]), N2(c["Fp4"])), unit="N",
             basis=f"{P.PIN_FORCE_N} N per pin at the working height (PROVISIONAL)"),
        dict(quantity="marker weight", value=round(c["weight"], 3), unit="N", basis=f"{m_puck:.1f} g (check 8)"),
        dict(quantity="hold-down reactions with seven pins: hook / lip", value=(N2(c["F_hook7"]), N2(c["F_lip7"])), unit="N",
             basis=f"moments about the lip (y {c['y_lip']:.2f}) and the hook (y {c['y_hook']:.2f}); the hook carries {100 * c['hook_share']:.1f} % of a pin-row force"),
        dict(quantity="hold-down reactions with four pins: hook / lip", value=(N2(c["F_hook4"]), N2(c["F_lip4"])), unit="N", basis="same"),
        dict(quantity="latch beam: b x h x L, E, E I", value=(c["b"], c["h"], N2(c["L"]), c["E"], N2(c["EI"])), unit="mm, mm, mm, MPa, N mm2",
             basis="uniform rectangular cantilever, I = b h^3 / 12; E = HP PA 12 MJF data sheet (XY), dry, 23 C"),
        dict(quantity="retention at the hook, no friction, nominal overlap", value=N2(c["F_cam"]), unit="N",
             basis=f"F = 2 E I u / (e L^2), u = {c['u']:.2f}, e = {c['e']:.3f} (hook contact to the beam's neutral axis)"),
        dict(quantity="= pin-row force that opens the latch / multiple of the seven-pin force", value=(N2(c["pin_equiv"]), N2(c["factor"])), unit="N / x",
             basis=f"hook force / {c['hook_share']:.3f}; required >= {req} x"),
        dict(quantity="same with the marker pushed fully forward in the nest", value=(N2(c["F_cam_min"]), N2(c["pin_equiv_min"]), N2(c["factor_min"])), unit="N / N / x",
             basis=f"u = {c['u_min']:.2f}, e = {c['e_min']:.3f}; required >= {req} x"),
        dict(quantity="friction above which the hook is self-locking", value=round(c["mu_lock"], 3), unit="-",
             basis="mu >= 1.5 e / L; PA12 on PA12 is usually 0.2 to 0.4 (assumed, not measured)"),
        dict(quantity=f"retention at the hook with friction {c['mu_lo']}", value=N2(c["F_fric"]) if c["F_fric"] != float("inf") else "self-locking", unit="N",
             basis="F = u E I / (e L^2 / 2 - mu L^3 / 3)"),
        dict(quantity=f"root stress at {req} x the seven-pin force / safety factor to yield", value=(N2(c["sig_root"]), N2(c["sf_root"])), unit="MPa / -",
             basis=f"hook load {c['F3_hook']:.1f} N: 6 F e / (b h^2) + F / (b h); yield {M['pa12_yield_MPa']} MPa (data sheet)"),
        dict(quantity="hook travel: insertion (posed solids) / release nominal / release worst / over-travel stop",
             value=(N2(c["d_ins"]), N2(c["d_rel"]), N2(c["d_rel_max"]), N2(c["d_stop"])), unit="mm",
             basis="release = hook nose back to the marker radius (nominal: 0.25 gap; worst: marker against the beam)"),
        dict(quantity="root strain at those travels", value=tuple(round(100 * c[k], 2) for k in ("eps_ins", "eps_rel", "eps_rel_max", "eps_stop")), unit="%",
             basis=f"eps = 3 h d / (2 L^2) (tip force); limit {100 * lim} %; at the stop under a pure tab moment: {100 * c['eps_stop_moment']:.2f} %"),
        dict(quantity="latch stiffness at the hook / lateral force at the insertion travel", value=(N2(c["k"]), N2(c["P_ins"])), unit="N/mm / N", basis="k = 3 E I / L^3"),
        dict(quantity="insertion force at the thumb for friction " + " / ".join(str(m) for m in c["ins"]), value=tuple(N2(v) for v in c["ins"].values()), unit="N",
             basis=f"W = P (mu + tan a) / (1 - mu tan a), a = {c['lead_deg']:.0f} deg lead-in; thumb 8 mm in from the rear edge (lever {c['lever']:.2f})"),
        dict(quantity="force to finish seating (last degree, seven pins)", value=N2(c["seat"]), unit="N", basis="friction on the hook nose plus the pins coming under load"),
        dict(quantity="release: thumb force on the tab, nominal / worst", value=(N2(c["F_tab"]), N2(c["F_tab_max"])), unit="N",
             basis=f"M = 2 E I d / L^2, pressed {c['tab_lever']:.2f} mm behind the beam axis; the tab end drops about {c['tab_drop']:.1f} mm"),
        dict(quantity="hook creep-out under the continuous seven-pin load (elastic / with a creep factor of 3)", value=(round(c["creep_d"], 3), round(3 * c["creep_d"], 3)),
             unit="mm", basis=f"d = F e L^2 / (2 E I) with F = {c['F_hook7']:.2f} N; overlap {c['u']:.2f} mm (creep modulus of MJF PA12 not verified)"),
        dict(quantity="lip plate: stress with the whole required force on it / safety factor", value=(N2(c["sig_lip"]), N2(c["sf_lip"])), unit="MPa / -",
             basis=f"6 F a / (w t^2), F = {req} x {c['Fp7']:.2f} N, a = {c['lip_arm']:.2f}, {2 * lw:.0f} x {M['lip_t']} plate"),
        dict(quantity="marker floats against lip and hook when pins are fitted: lift / pin height / stroke used",
             value=(P.CLR, N2(P.PIN_WORK_H + P.CLR), N2(M["pin_mid_stroke"] - P.CLR)), unit="mm", basis=f"recommended height {P.PIN_WORK_H}, full stroke {M['pin_full_stroke']} (D21)"),
        dict(quantity="rear of the marker pops up on release by about", value=N2(c["pop_up"]), unit="mm", basis="pins return to their free length; then lift at the finger scallops"),
    ]

    # ---------------- (f) finger access at the two scallops (radial rays from outside onto the seated marker)
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
                         marker_side_exposed_from_z=0.0, to_z=P.T, rays_reaching_the_marker=f"{n_ok} of {n_all}", status="ok" if okf else "FAIL"))

    warns.append(f"with pins fitted the marker floats up to {P.CLR} mm against lip and hook (D21); the pins then work at {P.PIN_WORK_H + P.CLR:.2f} mm")
    warns.append(f"insertion {c['ins'][c['mu']]:.0f} N and release {c['F_tab']:.0f} N are estimates (friction {c['mu']} assumed, modulus from the data sheet, "
                 "dry PA12); pin force and stroke are PROVISIONAL")
    warns.append(f"the latch beam stands in the build z direction if the cradle is printed as modelled: ask the bureau to lay the beam in the build "
                 f"plane, and test ten latch cycles on the first article (strain at the stop {100 * c['eps_stop']:.2f} %)")
    notes = ["hold-down = fixed lip over the top front edge between the camera windows + rear cantilever latch with a 90 deg retaining face; "
             "formulas in cad/holddown.py",
             "retention requirement is evaluated WITHOUT friction (lower bound): an upward force on the hook bends the beam back through its "
             "eccentricity e until the hook has moved by the overlap u",
             f"insertion path: the marker is tilted nose-down about its front bottom edge, rests {M['insertion_gap']} mm above the nest floor and is as far "
             f"forward as the front nest wall, the nose pocket and the lip tip allow ({M['insertion_gap']} mm clear); at each tilt the solids of tub + base "
             "plate + balls are intersected with the cradle (latch removed), the free-length plungers with base plate and adhesive sheet, and the "
             "latch is rotated back until it no longer intersects the tub (that travel is the insertion deflection)",
             "latch deflection is modelled as a rigid rotation about the point 2L/3 below the retaining face (exact tip travel and tip slope of a "
             "tip-loaded cantilever)",
             f"free plunger tip at z = {P.PIN_TIP_FREE_Z:.2f}; the pads meet the plungers at about 1.9 deg of tilt; the copper pad face is modelled "
             f"{P.PIN_TIP_GAP} mm below the YAML pad plane, so the modelled pin stands {P.PIN_WORK_H - P.PIN_TIP_GAP:.3f} mm high",
             "printability of the latch is covered by check 5 (walls; beam 1.15 mm, hook nose recorded) and check 6 (the latch well is open at the "
             "top; its gaps are listed there)"]
    ok_all = not fails
    return res(7, "cradle: pins, key, hold-down, insertion", ok_all,
               (f"seven pin positions on their pad centres, {min(r['clearance_in_base_and_adhesive_slot_mm'] for r in prow)} mm clear in the slots; nest "
                f"accepts 0 deg only; hold-down retention {c['factor']:.1f} x the seven-pin force without friction ({c['factor_min']:.1f} x with the marker "
                f"fully forward; required {req} x); latch strain {100 * c['eps_ins']:.2f} % at insertion ({c['d_ins']:.2f} mm), {100 * c['eps_stop']:.2f} % at the stop "
                f"(limit {100 * lim} %); insertion about {c['ins'][c['mu']]:.0f} N, release about {c['F_tab']:.0f} N; {len(irow)} posed tilts from "
                f"{max(M['insertion_tilts_deg']):.0f} deg to 0 without interference with lip, nest or pins"
                if ok_all else "FAILED: " + "; ".join(fails)),
               [dict(title="Pins at the seated position", rows=prow), dict(title="Orientation key", rows=orows),
                dict(title="Hold-down geometry measured on the solids", rows=grow),
                dict(title="Hold-down forces, retention and latch strain", rows=frow),
                dict(title="Insertion path (marker solids posed against the cradle solids)", rows=irow),
                dict(title="Finger access", rows=arow)], notes, warns)


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
        rows.append(dict(part=name, process=info.material, print_file=src, box_x_mm=R3(size[0]), box_y_mm=R3(size[1]), box_z_build_mm=R3(size[2]),
                         volume_cm3=round(s.Volume() / 1000, 3), stl_volume_cm3=round(vol / 1000, 3), surface_area_cm2=round(s.Area() / 100, 2),
                         mass_g=round(s.Volume() * info.density / 1000, 2), stl_triangles=len(tris), stl_watertight=closed,
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
    notes += [f"STL tolerance {A.STL_TOL} mm linear, {A.STL_ANG} rad angular; print orientation: tub roof-down, base plate and cradle as modelled (z = build direction)",
              "box = exact axis-aligned bounding box of the solid in print orientation; orientation is a recommendation, the bureau may nest differently"]
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
             f"load path roof -> posts -> PCB -> adhesive sheet -> base plate, none through LCD or battery. Total seat area {area:.1f} mm2: an 800 N "
             f"footstep carried by the posts alone would be {800 / area:.0f} MPa (PA12 yields near 48 MPa). That is an upper bound - the side wall "
             "runs to the base plane and takes most of the load - but the footstep case is NOT analysed or tested (open issue)"]
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


CHECKS = [check_interference, check_clearances, check_fov, check_fold, check_walls, check_trapped, check_cradle, check_mass,
          check_quoting, check_posts, check_layout_script, check_keepouts]


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
          f"{len(DEV_OPEN)} recorded deviations from the specification still stand, {len(DEV_CLOSED)} were closed by revision C (listed at the end).", "",
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
    md += ["", "Closed by revision C:", ""]
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
