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
  7 cradle              pin / pad alignment at 0 deg, 180 deg position, nest orientations, pin force
  8 mass                mass and centre of gravity
  9 quoting             printed-part boxes / volumes and export integrity (STEP and STL re-read)
 10 support posts, 11 design/check_layout.py
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
from deviations import DEVIATIONS

M = P.MECH
INTERFERENCE_LIMIT_MM3 = 0.01
CONTACT_TOL = 1e-4
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
                expect = solids["pcb_adhesive"].Volume() if "pcb_adhesive" in (a, b) else None
                ok = expect is None or abs(vol - expect) < 0.01
                status = "allowed modelling overlap" if ok else "MODELLING OVERLAP WRONG VOLUME"
                if not ok:
                    fails.append((a, b, status))
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
             "allow-list of intended contacts and the one modelling overlap: cad/assembly.py (INTENDED_CONTACTS, MODELLING_OVERLAPS)"]
    warns = []
    if missing:
        warns.append("intended contacts that do NOT touch in the model: " + ", ".join(f"{a}/{b}" for a, b in missing))
    if unlisted:
        warns.append("zero-volume contacts not on the intended list: " + ", ".join(f"{r['a']}/{r['b']}" for r in unlisted))
    n_over = sum(r["status"] == "allowed modelling overlap" for r in rows)
    return res(1, "interference", not fails,
               (f"no unintended interference in {n_tested} tested pairs ({n_pairs} total); "
                f"{sum(r['status'] == 'intended contact' for r in rows)} intended zero-volume contacts, {n_over} allow-listed modelling overlap"
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
        elif actual >= minimum - 1e-3:
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
    add("PCB edge to seating ledge, radial", _sec_dist(board, tub, "z", zl), clr, nominal=P.LEDGE_RI - P.PCB_R, dev="D12",
        method=f"section z = {zl:.2f}")
    add("PCB flat edge to visor wall", _sec_dist(board, tub, "z", zl, clip=(-8, 15, 8, 20)), clr, nominal=P.Y_VISOR_IN - P.PCB_FLAT,
        method=f"section z = {zl:.2f}, |x| < 8")
    add("Base plate to tub side wall and key lugs, radial", _sec_dist(S["base_plate"], tub, "z", 0.5 * P.BASE_T), clr, nominal=clr,
        method=f"section z = {0.5 * P.BASE_T:.2f}")
    add("Base plate top to tub seal face (adhesive bead)", min_distance(S["base_plate"], tub), P.BEAD_T, nominal=P.BEAD_T,
        note="nominal bead; 0.33 in the real stack with the 0.13 mm PSA (D10)")
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
            note="rear wall edge chamfered; 0.177 before the fix")
        add(f"Prism {s} to hood walls in the horizontal plane", _sec_dist(S[f"prism_{s}"], tub, "z", P.AXIS_Z), clr,
            method=f"section z = {P.AXIS_Z:.2f}")
        w = S[f"visor_window_{s}"]
        add(f"Visor window {s} to recess sides", _sec_dist(w, tub, "y", P.Y_VISOR - P.WIN_T / 2, clip=(cx - 5, P.WIN_Z0 + 0.3, cx + 5, P.T)),
            clr, nominal=(P.WIN_RECESS_W - P.WIN_W) / 2, dev="D12", method="section through the window, above the shelf")
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
    add("Photodiode body to baffle ring", min_distance(pdbox, S["base_plate"]), clr, nominal=M["baffle_pd_clear"])
    dled = min(min_distance(b.val(), S["base_plate"]) for b in PT.led_boxes())
    add("Grain LEDs to opening wall / baffle / spokes", dled, clr)
    # --- cradle
    add("Puck to nest wall, radial", _sec_dist(tub, S["cradle"], "z", 1.5), clr, nominal=clr, method="section z = 1.5")
    add("Tub rim above the reference plate (ball protrusion)", min_distance(tub, S["cradle_plate"]), P.BALL_PROT, nominal=P.BALL_PROT)
    zp = 0.5 * (P.PLATE_Z0 + P.PLATE_Z1)
    add("Reference plate to nest seat, radial", _sec_dist(S["cradle_plate"], S["cradle"], "z", zp), clr, nominal=clr, method=f"section z = {zp:.2f}")
    add("Spring-pin plunger to plate hole, radial", _sec_dist(S["spring_pin_4"], S["cradle_plate"], "z", zp), clr,
        nominal=(M["plate_hole_dia"] - M["pin_plunger_dia"]) / 2, method=f"section z = {zp:.2f}", note="pin diameters PROVISIONAL")
    add("Spring-pin plunger to base-plate slot, radial", _sec_dist(S["spring_pin_4"], S["base_plate"], "z", 0.5), clr,
        nominal=(P.PAD_HOLE_D - M["pin_plunger_dia"]) / 2, method="section z = 0.50")
    zb = 0.5 * (P.CPCB_Z1 + P.PIN_BODY_Z1)
    add("Spring-pin body to printed pin slot, radial", _sec_dist(S["spring_pin_1"], S["cradle"], "z", zb), clr, nominal=clr,
        method=f"section z = {zb:.2f}", note="2.0 mm slot gave 0.085; widened")
    zq = 0.5 * (P.CPCB_Z0 + P.CPCB_Z1)
    add("Cradle PCB to pocket walls", _sec_dist(S["cradle_pcb"], S["cradle"], "z", zq), clr, nominal=clr, method=f"section z = {zq:.2f}")
    add("USB receptacle shell to printed pocket", min_distance(S["usb_receptacle"], S["cradle"]), clr, note="envelope PROVISIONAL")

    # --- table 2b: every top-side part of the YAML
    prow = []
    lcdfoam = [S["lcd_glass"], S["foam_pad"]]
    for ref, (p, bx) in _top_part_boxes().items():
        if ref == "BT1":
            continue
        d_tub = min_distance(bx, tub)
        d_lcd = min(min_distance(bx, s) for s in lcdfoam)
        d_bat = min_distance(bx, S["battery"]) if ref not in ("U2", "U3") else None
        ok = d_tub >= clr - 1e-3 and d_lcd >= clr - 1e-3 and (d_bat is None or d_bat >= 0.2 - 1e-3)
        if not ok:
            fails.append(f"{ref} clearance")
        prow.append(dict(ref=ref, part=p["name"], top_z=R3(P.PCB_Z1 + p["h"]), to_tub_mm=R3(d_tub), to_lcd_glass_or_foam_mm=R3(d_lcd),
                         to_battery_mm=R3(d_bat), status="ok" if ok else "FAIL"))
    notes = ["required minimum = 0.25 mm drop-in rule unless the row is a specified stack value (adhesive lines, prism-to-roof 0.19)",
             "passives are not in master_params.yaml, so only the 13 listed top-side parts are checked",
             "sections are true boolean sections of the solids; curved edges are sampled to 0.0002 mm"]
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
    notes = [f"frustum: ruled solid between the bounding rectangle of the traced rays on the exit-face plane (y = {yn}) and on the plane 200 mm in front of it; "
             f"chief-ray rectangle at the exit face x = cam x {rn[0] - cx:+.3f}..{rn[1] - cx:+.3f}, z = {rn[2]:.3f}..{rn[3]:.3f}",
             "rays are traced exactly through the prism (optics.py); the entrance-pupil position and diameter are ASSUMED",
             "'left/right' = toward -x/+x, 'up/down' = toward +z/-z in object space",
             f"the lower field edge ({M['fov_down_deg']} deg) meets the base plane about {turf:.1f} mm in front of the virtual pupil - turf, not a part",
             "the visor windows are treated as transparent plates (the 0.5 mm plate shifts a 26 deg ray by about 0.09 mm; not modelled)"]
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
                m_open = min(m_open, P.OPEN_HALF_W - abs(q[0] - cx), q[2] - P.OPEN_Z0, P.OPEN_Z1 - q[2])
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
    # tolerance sensitivity: move camera + prism relative to the tub
    srows = []
    lat = round(P.LEDGE_RI - P.PCB_R, 3)
    cases = [("nominal", (0, 0, 0)), (f"PCB shifted +x by the PCB-to-ledge gap ({lat})", (lat, 0, 0)),
             (f"+x {lat} plus 0.2 print tolerance", (lat + 0.2, 0, 0)),
             ("optics 0.2 low (print tolerance on the sill / PSA stack)", (0, 0, -0.2)), ("optics 0.2 high", (0, 0, 0.2))]
    for label, sh in cases:
        lim = {d: O.limit_angle("R", d, rc, True, shift=sh)[0] for d in ("left", "right", "up", "down")}
        limc = {d: O.limit_angle("R", d, rc, False, shift=sh)[0] for d in ("left", "right", "up", "down")}
        worst = min(O.bundle("R", th, tv, rc, shift=sh)["total_fraction"] for _, th, tv in O.field_points())
        srows.append(dict(case=label, shift_xyz=sh,
                          full_pupil_clear_deg_left_right_up_down=tuple(round(lim[d], 1) for d in ("left", "right", "up", "down")),
                          chief_clear_deg_left_right_up_down=tuple(round(limc[d], 1) for d in ("left", "right", "up", "down")),
                          worst_field_point_transmission_pct=round(100 * worst, 1)))
    nom = [r for r in rows if r["camera"] == "R"]
    worst_nom = min(r["pupil_through_visor_pct"] for r in nom)
    m_open_min = min(r["margin_visor_opening_mm"] for r in rows)
    if m_open_min < 0.1:
        warns.append(f"smallest margin of the pupil bundle to the visor opening is {m_open_min:.3f} mm - far below the print tolerance (+-0.2) "
                     "and the PCB location play; see the sensitivity table and PROPOSED_PARAM_CHANGES.md")
    notes = [f"entrance pupil ASSUMED: dia {M['pupil_dia']} mm, {M['pupil_below_cube_top']} mm below the cube top (z = {P.PUPIL_Z:.2f}); prism n = {O.N_GLASS}, "
             f"legs {P.PRISM_LEG}, bond gap {P.PRISM_BOND}; hypotenuse aluminised (reflects at any angle)",
             "margins are the smallest distance of any ray of the pupil bundle to the edge of that aperture (negative = clipped); "
             "the visor margin is taken on the aperture plane (window-recess floor)",
             "field points are rectilinear: direction (tan h, 1, tan v)",
             f"paraxial check: virtual pupil {P.VIRTUAL_PUPIL_BEHIND_EXIT:.3f} mm behind the exit face (y = {P.VIRTUAL_PUPIL_Y:.3f}), z = {P.AXIS_Z}",
             "sensitivity cases move the camera and prism together relative to the printed tub (camera R; L is the mirror image)"]
    return res(4, "fold geometry", not fails,
               (f"chief rays of all nine field points pass the prism and the visor opening on both cameras; pupil transmission at the worst "
                f"nominal field point {worst_nom:.1f} % (prism exit face); smallest bundle margin to the visor opening {m_open_min:.3f} mm"
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
            f.append((f"camera {side}: wall behind the window recess in front of the camera cube", "D04", P.THIN_STRIP_T,
                      [(cx - P.WIN_RECESS_W / 2 - e, P.HOOD_PAD_Y - e, P.WIN_Z0 - e, cx + P.WIN_RECESS_W / 2 + e, P.WIN_RECESS_FLOOR_Y + e, P.HOOD_Z_OVER_CUBE + e)]))
            f.append((f"camera {side}: bevelled rim of the opening (specified bevel; {M['visor_land']} mm land)", "D05", M["visor_land"],
                      [(cx + P.OPEN_HALF_W - e, P.HOOD_FRONT_IN_Y - e, P.OPEN_Z0 - e, cx + P.OPEN_HALF_W_INSIDE + e, P.WIN_RECESS_FLOOR_Y + e, P.OPEN_Z1 + e),
                       (cx - P.OPEN_HALF_W_INSIDE - e, P.HOOD_FRONT_IN_Y - e, P.OPEN_Z0 - e, cx - P.OPEN_HALF_W + e, P.WIN_RECESS_FLOOR_Y + e, P.OPEN_Z1 + e)]))
            c = P.HOOD_REAR_CHAMFER
            f.append((f"camera {side}: foot of the hood rear wall ({c:.2f} mm edge chamfer facing the prism)", "", P.MIN_WALL - c,
                      [(cx - P.HOOD_OUT_HW - e, P.HOOD_REAR_Y0 - e, P.HOOD_Z_OVER_CUBE - e, cx + P.HOOD_OUT_HW + e, P.HOOD_REAR_Y1 + e, P.HOOD_Z_OVER_CUBE + c + e)]))
        ch = M["bottom_chamfer"]
        f.append((f"foot of the side wall at the specified {ch} mm bottom chamfer (all round the arc)", "", P.WALL - ch,
                  [(-P.R_OUT - e, -P.R_OUT - e, -e, P.R_OUT + e, P.R_OUT + e, ch + e)]))
    if name == "base_plate":
        r = P.BALL_SEAT_R_BOTTOM + 0.1
        for i, (x, y) in enumerate(P.BALL_XY):
            f.append((f"ball seat {i + 1}: skin over the conical seat (apex breaks through as a pin-hole)", "D02", 0.0,
                      [(x - r, y - r, -e, x + r, y + r, P.BASE_T + e)]))
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
              "the 0.7 mm wide bottom land of the side wall and the 0.5 mm aperture land are edge features of walls that are 1.0 / 0.8 mm thick above them"]
    return res(5, "wall thickness", not fails,
               (f"{len(thin5)} regions thinner than 0.5 mm, all recorded (the three conical ball seats, D02); {n_doc} recorded regions below "
                f"{P.MIN_WALL} mm in total; no unrecorded thin region; " + ", ".join(summary_bits)
                if not fails else "FAILED: " + "; ".join(fails)),
               [dict(title=f"Regions thinner than the {P.MIN_WALL} mm rule", rows=rows_all),
                dict(title="Regions thinner than 0.5 mm", rows=thin5)], notes, warns)


# ==============================================================================================
# 6. trapped volume
# ==============================================================================================
def voxelize(tris, pitch, margin):
    """Solid occupancy grid of a closed mesh by z-column parity. Returns (solid[nx,ny,nz] bool, origin, odd_columns)."""
    v = tris.reshape(-1, 3)
    lo = v.min(axis=0) - margin + 0.0137 * pitch              # de-phased from round coordinates
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


VOXEL_PITCH = dict(tub=0.10, base_plate=0.10, cradle=0.20)
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
        vx, vy = M["vent_xy"]
        if abs(c[0] - vx) < 1.5 and abs(c[1] - vy) < 1.5 and c[2] > P.ROOF_Z - 0.5:
            return "vent hole dia 1.0 (through)"
        for s, (cx, cy) in P.CAM_XY.items():
            if abs(c[0] - cx) < 4.5 and c[1] > P.HOOD_REAR_Y0 - 0.5:
                return f"camera hood {s} (bay / slot over the cube, open below)"
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
                return f"ball seat {i + 1} (conical, open below)"
        if abs(c[1] - P.PAD_Y) < 2:
            return "pad slot end"
        if math.hypot(c[0] - P.GRAIN_X, c[1] - P.GRAIN_Y) < P.GRAIN_R + 0.5:
            return "grain opening sector corner"
        if c[1] > P.KEY_NOTCH_Y0 - 0.5:
            return "key notch"
        return "edge"
    if abs(c[1] - P.PAD_Y) < 2 and abs(c[0]) < 10:
        return "spring-pin slot (through)"
    if c[2] < P.CPCB_Z1 + 1 and abs(c[0]) < 12:
        return "PCB / USB pocket corner or screw spot mark"
    return "pocket corner"


# ==============================================================================================
# 7. cradle
# ==============================================================================================
def _rot180_about_nest(shape, angle=180.0):
    return shape.rotate(cq.Vector(0, P.NEST_CY, 0), cq.Vector(0, P.NEST_CY, 1), angle)


def check_cradle(parts):
    S = _solids(parts)
    base = S["base_plate"]
    rp = M["pin_plunger_dia"] / 2
    fails, warns = [], []
    base_sec = G.section_polys(base, "z", 0.5 * P.BASE_T)
    rows = []
    for i, x in enumerate(P.PAD_XS):
        pin = S[f"spring_pin_{i + 1}"]
        bb = A.bbox_of(parts[f"spring_pin_{i + 1}"])
        px0, py0 = 0.5 * (bb[0] + bb[3]), 0.5 * (bb[1] + bb[4])
        off = math.hypot(px0 - x, py0 - P.PAD_Y)                      # pin axis to pad centre
        tip_gap = abs(bb[5] - P.PAD_Z0)                               # plunger tip on the modelled pad plane
        cyl0 = cq.Solid.makeCylinder(rp, 3.0, cq.Vector(px0, py0, -1.0), cq.Vector(0, 0, 1))
        v0 = common_volume(base, cyl0); d0 = min_distance(base, cyl0)
        # 180 deg: this pin sits under puck point (qx, qy)
        qx, qy = P.cradle_to_puck_180(px0, py0)
        disc = cq.Solid.makeCylinder(rp, P.BASE_T, cq.Vector(qx, qy, 0), cq.Vector(0, 0, 1))
        v180 = common_volume(base, disc); full = math.pi * rp * rp * P.BASE_T
        inside = base_sec.contains(Point(qx, qy))
        edge = base_sec.boundary.distance(Point(qx, qy)) - rp if inside else -1.0   # plunger rim to the nearest opening / edge
        to_pads = min(math.hypot(qx - xx, qy - P.PAD_Y) for xx in P.PAD_XS) - rp - M["pad_dia"] / 2
        good = off < 1e-3 and tip_gap < 1e-3 and v0 < 1e-6 and d0 >= P.CLR and abs(v180 - full) < 1e-3 and edge > 0.25 and to_pads > 1.0
        if not good:
            fails.append(f"pin {i + 1}")
        rows.append(dict(pin=i + 1, x=x, at0_axis_to_pad_centre_mm=round(off, 4), at0_tip_to_pad_plane_mm=round(tip_gap, 4),
                         at0_clearance_in_base_slot_mm=R3(d0), at180_lands_on_puck_xy=(round(qx, 2), round(qy, 2)),
                         at180_backed_by_solid_base_pct=round(100 * v180 / full, 2), at180_rim_to_nearest_opening_mm=R3(edge),
                         at180_to_nearest_pad_mm=R3(to_pads), ok=good))
    # nest orientations: puck shell (tub + base) turned about the nest centre against cradle body + plate
    shell = S["tub"].fuse(base)
    fixed = S["cradle"].fuse(S["cradle_plate"])
    orows = []
    for ang in (0.0, 90.0, 180.0, 270.0):
        v = common_volume(_rot180_about_nest(shell, ang) if ang else shell, fixed)
        want_clear = ang in (0.0, 180.0)
        ok = (v < INTERFERENCE_LIMIT_MM3) if want_clear else (v > 1.0)
        if not ok:
            fails.append(f"nest orientation {ang:.0f} deg: common volume {v:.3f} mm3")
        orows.append(dict(puck_angle_deg=int(ang), common_volume_with_cradle_and_plate_mm3=round(v, 3),
                          expected="fits" if want_clear else "blocked", status="ok" if ok else "FAIL"))
    # stroke and force (PROVISIONAL pin data)
    work = M["real_pad_height"] - P.CPCB_Z1                       # height of the pad above the cradle PCB
    stroke0 = M["pin_max_working_h"] - work
    stroke180 = M["pin_max_working_h"] - (0.0 - P.CPCB_Z1)        # at 180 deg the plungers bear on the base plane (z = 0)
    if abs(work - M["pin_working_h"]) > 1e-6:
        fails.append(f"working height {work:.3f} != {M['pin_working_h']}")
    mt = _mass_table(parts)
    m_puck = sum(r["mass_g"] for r in mt if r["group"] == "puck")
    cg = _cog(mt, "puck")
    W = m_puck * 9.81e-3
    Fp = len(P.PAD_XS) * M["pin_force_working_N"]
    (x1, y1), (x2, y2), _ = P.BALL_XY
    R1 = (W * (cg[1] - y2) - Fp * (P.PAD_Y - y2)) / (y1 - y2)
    R23 = W - Fp - R1
    k = (0.0 - y2) / (y1 - y2)                                     # hold-down applied at the puck centre
    Fc = (Fp - W + R1) / (1 - k)
    frow = [dict(quantity="pad height above the cradle PCB at 0 deg (pin working height)", value=round(work, 3), unit="mm",
                 note=f"recommended {M['pin_working_h']}; cradle PCB top at z = {P.CPCB_Z1:.2f}"),
            dict(quantity="plunger travel used at 0 deg", value=round(stroke0, 3), unit="mm", note=f"mid stroke {M['pin_mid_stroke']}, full stroke {M['pin_full_stroke']}"),
            dict(quantity="plunger travel used at 180 deg (pins bear on the base plate)", value=round(stroke180, 3), unit="mm",
                 note=f"{M['pin_full_stroke'] - stroke180:.2f} mm short of full stroke"),
            dict(quantity="total pin force at working height", value=round(Fp, 2), unit="N", note=f"7 x {M['pin_force_working_N']} N (60 gf each, PROVISIONAL)"),
            dict(quantity="puck weight", value=round(W, 3), unit="N", note=f"{m_puck:.1f} g (check 8)"),
            dict(quantity="ball reactions without hold-down: front / rear pair", value=(round(R1, 2), round(R23, 2)), unit="N",
                 note="negative = that foot lifts: the puck does not stay on the reference plate"),
            dict(quantity="hold-down force needed at the puck centre to keep all three balls seated at 0 deg", value=round(Fc, 1), unit="N", note="not provided by the cradle as modelled")]
    warns.append(f"OPEN (D17): seven pins push up with about {Fp:.1f} N against a puck weight of {W:.2f} N - without a hold-down the puck is lifted off the "
                 f"reference plate at 0 deg and at 180 deg; about {Fc:.0f} N at the puck centre would be needed. No hold-down is modelled")
    warns.append(f"at 180 deg every pin bears on the solid base plate (no pin is over a pad, the pad slot, the grain opening or a ball seat), but it is compressed "
                 f"{stroke180:.2f} mm of {M['pin_full_stroke']} mm full stroke ({M['pin_full_stroke'] - stroke180:.2f} mm margin): the DESIGN_SPEC sentence "
                 "'a puck placed 180 degrees round touches no pins' is NOT met - the pins touch the base, they touch no pad")
    notes = [f"180 deg position = puck turned about the nest centre (0, {P.NEST_CY:.1f}); its own centre moves {P.NEST_SHIFT:.1f} mm toward -y (D15)",
             "pin travel and force are from docs/research/bom-verification-opto.md (Mill-Max 0914); plunger and body diameters are PROVISIONAL",
             f"the model keeps the YAML PCB height, so the modelled plunger is {P.PIN_MODEL_COMPRESSION_EXTRA:.3f} mm shorter than real; the cradle PCB is "
             f"placed for the real pad height {M['real_pad_height']} mm"]
    return res(7, "cradle pins", not fails,
               ("0 deg: all seven pins on their pad centres at the recommended working height, 0.565 mm clear in the base slot; 180 deg: every pin lands on "
                f"solid base plate at puck y = {P.cradle_to_puck_180(0, P.PAD_Y)[1]:.1f}, at least "
                f"{min(r['at180_rim_to_nearest_opening_mm'] for r in rows):.2f} mm from any opening; nest accepts 0 and 180 deg only"
                if not fails else "FAILED: " + "; ".join(fails)),
               [dict(title="Pins at 0 deg and at 180 deg", rows=rows), dict(title="Nest orientations", rows=orows),
                dict(title="Pin travel and force balance (PROVISIONAL pin data)", rows=frow)], notes, warns)


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
    notes = ["densities are typical handbook values, not measured (PROVISIONAL): PA12 MJF 1.01, glass 2.5, N-BK7 2.51, FR-4 1.85, stainless 7.9-8.0, "
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
# 10. support posts, 11. layout script
# ==============================================================================================
def check_posts(parts):
    """Each support post foot must land on the PCB top, clear every top-side part and the LCD glass by the fit clearance."""
    S = _solids(parts)
    pcb = Point(0, 0).buffer(P.PCB_R, 256).intersection(sbox(-99, -99, 99, P.PCB_FLAT))
    lcd = sbox(P.LCD_X0, P.LCD_Y0, P.LCD_X1, P.LCD_Y1)
    board = PT.pcb_board().val()
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
        good = edge >= P.PCB_EDGE_CLR and dmin >= P.CLR - 1e-9 and foot.distance(lcd) >= P.CLR - 1e-9 and solid_frac > 0.999
        ok &= good
        rows.append(dict(post=name, x0=x0, x1=x1, y0=y0, y1=y1, to_pcb_edge_mm=R3(edge), nearest_part=near, gap_to_nearest_part_mm=R3(dmin),
                         gap_to_lcd_glass_mm=R3(foot.distance(lcd)), solid_from_pcb_to_roof_pct=round(100 * solid_frac, 1), ok=good))
    area = sum((r["x1"] - r["x0"]) * (r["y1"] - r["y0"]) for r in rows)
    notes = ["only parts listed in master_params.yaml are checked; passives are not in the YAML - the post feet are PCB keep-outs (PROPOSED_PARAM_CHANGES.md)",
             f"load path roof -> posts -> PCB -> PSA -> base plate, none through LCD or battery. Total post foot area {area:.1f} mm2: an 800 N "
             f"footstep carried by the posts alone would be {800 / area:.0f} MPa (PA12 yields near 48 MPa). That is an upper bound - the side wall "
             "runs to the base plane and takes most of the load - but the footstep case is NOT analysed or tested (open issue)"]
    return res(10, "support posts", ok, f"{len(rows)} posts, all on the PCB, solid from PCB to roof, clear of listed parts and of the LCD glass" if ok else "post placement problem",
               [dict(title="Support posts", rows=rows)], notes)


def check_layout_script(parts=None):
    r = subprocess.run([sys.executable, str(P.DESIGN_DIR / "check_layout.py")], capture_output=True, text=True)
    lines = r.stdout.strip().splitlines()
    return res(11, "design/check_layout.py", r.returncode == 0, lines[-1] if lines else "no output",
               [dict(title="Output of design/check_layout.py (plan view and z stack of master_params.yaml)", rows=[dict(line=l) for l in lines])],
               [f"exit code {r.returncode}"] + ([r.stderr.strip()] if r.stderr.strip() else []))


CHECKS = [check_interference, check_clearances, check_fov, check_fold, check_walls, check_trapped, check_cradle, check_mass,
          check_quoting, check_posts, check_layout_script]


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
          f"{len(DEVIATIONS)} recorded deviations from the specification (listed at the end).", "",
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
           "Items marked YAML need a shared number changed: see PROPOSED_PARAM_CHANGES.md (master_params.yaml is not edited).", ""]
    for d in DEVIATIONS:
        md += [f"- **{d['id']} {d['part']}**{' (YAML)' if d['yaml_change'] else ''}: required: {d['requirement']}. "
               f"Implemented: {d['implemented']}. Reason: {d['reason']}."]
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
