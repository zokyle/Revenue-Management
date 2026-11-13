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
 10 support posts       posts, spigots and the ball-foot zones; 11 design/check_layout.py
 12 tub keep-outs       the YAML tub_keepouts contract proven on the tub solid
 13 seal continuity     air-solid test (outside and cavity must be separate), closed bead ring, seal land widths
 14 assembly paths      LCD tilt-in, PCB / base unit join (straight and hinged) posed against the tub
 15 FR-4 base plate     fabrication rules on the routed plate (corner radii, webs, edge distances, hole table)
 16 alternative base    the printed PA12 base plate build: interference, walls, powder, feet, baffle, seal joint, mass
 17 board import        the real circuit board (electrical/gl1_main/out/*-mechanical.json) against the YAML and the tub;
                        "skipped: no board file" when the file does not exist yet (cad/board_import.py)
 18 fixtures on the outer face   the two seat plates of the two-seat level zero (drawing GL1-050), the ball gauge plate of
                        assembly step 2 and the footprint of the bridge gauge, against the marker and the legend

Checks 1 to 14 run on the PRIMARY build (routed FR-4 base plate).  The parts of the alternative build are in the same
dict under names ending in "_pa12" (group "alt"); only checks 9 and 16 look at them.
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
    """Triangles of a part: the exported STL when this build wrote it, otherwise the same tessellation in memory.
    The file is the one of the PartInfo (in the alternative view the key "base_plate" holds the part "base_plate_pa12")."""
    fname = parts[name].name
    f = (A.STL_PRINT_DIR / f"{fname}_print.stl") if print_orientation else (A.STL_PARTS_DIR / f"{fname}.stl")
    if USE_EXPORTED and f.exists():
        return G.load_stl(f), str(f.relative_to(P.MECH_DIR))
    shape = A.print_shape(fname, parts[name].shape).val() if print_orientation else A.solid_of(parts[name])
    vs, ts = shape.tessellate(*((A.PRINT_STL_TOL, A.PRINT_STL_ANG) if print_orientation else (A.STL_TOL, A.STL_ANG)))
    v = np.array([p.toTuple() for p in vs])
    return v[np.array(ts)], "in-memory tessellation (no export in this run)"


# ==============================================================================================
# 1. interference
# ==============================================================================================
def check_interference(parts, focus=None, cid=1, cname="interference"):
    """Pairwise boolean intersection between ALL solids of the assembly (puck seated in the cradle at 0 deg).  The
    parts of the alternative build (group "alt") are not part of this assembly.  focus = a set of part names: only pairs
    with at least one member in it are tested (used for the alternative base plate, where everything else is unchanged)."""
    names = [n for n, i in parts.items() if i.group not in A.EXTRA_GROUPS]
    solids = _solids(parts)
    bbs = {n: A.bbox_of(parts[n]) for n in names}
    rows, fails, contacts_seen = [], [], set()
    n_pairs = n_tested = 0
    for a, b in itertools.combinations(names, 2):
        if focus is not None and a not in focus and b not in focus:
            continue
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
    missing = [k for k in A.INTENDED_CONTACTS if k not in contacts_seen and k[0] in names and k[1] in names
               and (focus is None or k[0] in focus or k[1] in focus)]
    unlisted = [r for r in rows if r["status"] == "contact (not on the list)"]
    notes = [f"{n_pairs} pairs; {n_tested} with overlapping bounding boxes tested by boolean common and minimum distance; "
             f"limit {INTERFERENCE_LIMIT_MM3} mm3",
             "allow-list of intended contacts: cad/assembly.py (INTENDED_CONTACTS); there is no modelling overlap - the adhesive sheet "
             f"occupies its own {P.PSA_T} mm between base plate and PCB",
             f"base plate variant: {P.BASE['label']} ({P.BASE_T} mm plate, {P.PSA_T} mm sheet)"
             + ("; only pairs that involve a base-specific part are tested, every other pair is the same as in check 1" if focus is not None else "")]
    warns = []
    if missing:
        warns.append("intended contacts that do NOT touch in the model: " + ", ".join(f"{a}/{b}" for a, b in missing))
    if unlisted:
        warns.append("zero-volume contacts not on the intended list: " + ", ".join(f"{r['a']}/{r['b']}" for r in unlisted))
    n_over = sum(r["status"] == "allowed modelling overlap" for r in rows)
    if missing or unlisted:                                 # the allow-list is part of the proof: a contact that is lost or new is a failure
        fails += [(a, b, "intended contact missing") for a, b in missing] + [(r["a"], r["b"], "contact not on the list") for r in unlisted]
    return res(cid, cname, not fails,
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


class _Rows:
    """Collector for a clearance table: computes the status of every row against its minimum and its nominal value."""

    def __init__(self):
        self.rows, self.fails, self.warns = [], [], []

    def add(self, item, actual, minimum, nominal=None, dev=None, method="3D minimum distance", note=""):
        if actual != actual:
            status = "FAIL: not computed"
        elif nominal is not None and abs(actual - nominal) > 0.01:
            status = f"FAIL: model {actual:.3f} differs from nominal {nominal:.3f}"
        elif actual >= minimum - NUM_TOL:
            status = "ok"
        elif dev:
            status = f"below the {minimum} rule - recorded deviation {dev}"
            self.warns.append(f"{item}: {actual:.3f} mm < {minimum} mm ({dev})")
        else:
            status = f"FAIL: below minimum {minimum}"
        if status.startswith("FAIL"):
            self.fails.append(item)
        self.rows.append(dict(item=item, method=method, actual_mm=R3(actual), required_min_mm=R3(minimum),
                              margin_mm=R3(actual - minimum) if actual == actual else None, status=status, note=note))


def _base_rows(parts, S, T):
    """The clearance rows that depend on the base-plate variant (plate in the tub, seal joint, ball feet, grain opening,
    baffle, potting, pad slot).  Run for the primary build in check 2 and for the alternative build in check 16."""
    add, clr, tub, base = T.add, P.CLR, S["tub"], S["base_plate"]
    v = P.BASE
    add("Base plate to tub side wall, radial", _sec_dist(base, tub, "z", 0.5 * (P.RIM_Z + P.BASE_T)), clr, nominal=clr,
        method=f"section z = {0.5 * (P.RIM_Z + P.BASE_T):.3f}", note="groove filled with seal adhesive; no key, no notch in the seal land")
    add("Tub rim above the base plane (rim relief)", A.bbox_of(parts["tub"])[2] - A.bbox_of(parts["base_plate"])[2], P.RIM_Z, nominal=P.RIM_Z,
        method="bounding boxes", note=f"base plate and ball feet are the lowest surfaces: the rim is {P.RIM_Z + P.BALL_PROT:.2f} mm above the ball plane")
    add("Base plate thickness", A.bbox_of(parts["base_plate"])[5] - A.bbox_of(parts["base_plate"])[2], P.BASE_T, nominal=P.BASE_T, method="bounding box",
        note=v["short"])
    bead = G.RayCaster(tub).first_hit((0.0, -0.5 * (P.LAND_RI + P.BASE_R), P.BASE_T + 1e-6), (0, 0, 1), 1e-9, 5.0)
    st, stb = P.stack_tolerance(), P.stack_tolerance(printed=M["print_tol"])
    j, jb = st["joint"], stb["joint"]
    add("Base plate top to tub seal face (height of the perimeter seal joint)", (bead or float("nan")) + 1e-6, P.BEAD_T, nominal=P.BEAD_T,
        method="ray +z from the seal land", note=f"joint = PCB {P.PCB_T} - printed step {P.PCB_Z1 - P.LEDGE_Z0:.2f} + sheet {P.PSA_T} = {P.BEAD_T:.2f} mm (the plate thickness is not in "
        f"this chain); {P.BEAD_T - j['rss']:.2f} to {P.BEAD_T + j['rss']:.2f} (+-{j['rss']:.2f} RSS, +-{j['worst']:.2f} worst case) with +-{M['tol_printed']} on the printed step, "
        f"{P.BEAD_T - jb['rss']:.2f} to {P.BEAD_T + jb['rss']:.2f} with the bureau's general +-{M['print_tol']}")
    add("Adhesive sheet between base plate and PCB", min_distance(base, PT.pcb_board().val()), P.PSA_T, nominal=P.PSA_T,
        note=f"{v['psa_material']}; plate {P.BASE_T} + sheet {P.PSA_T} = PCB underside z {P.PCB_Z0}")
    add("Ball in its through hole, radial", _sec_dist(S["ball_1"], base, "z", P.BALL_Z), 0.03, nominal=(P.BALL_HOLE_D - P.BALL_D) / 2,
        method=f"section z = {P.BALL_Z:.2f} (ball equator)", note=f"hole dia {P.BALL_HOLE_D} ({'drilled' if not v['printed'] else 'printed, reamed'}): annulus filled with the potting epoxy")
    add("Ball feet below the base plane (protrusion)", A.bbox_of(parts["base_plate"])[2] - A.bbox_of(parts["ball_1"])[2], P.BALL_PROT, nominal=P.BALL_PROT,
        method="bounding boxes", note="set on the gauge plate, not by the plate")
    add("Ball foot top to the PCB underside", min_distance(S["ball_1"], S["main_pcb"]), 0.05, nominal=P.PCB_Z0 - P.BALL_TOP_Z,
        note=f"the ball stands {P.BALL_TOP_Z - P.BASE_T:.2f} above the plate inside the {P.PSA_FOOT_HOLE_D} mm hole of the adhesive sheet")
    gap_min = v["accept"][0] + (P.PSA_T - v["psa_tol"]) - (P.BALL_TOP_Z + M["tol_ball_set"])
    add("Ball top to its copper land: plate at its lower incoming limit, sheet at its thinnest, ball set high", gap_min, M["ball_gap_min"], method="arithmetic on the incoming limits",
        note=f"plate accepted from {v['accept'][0]:.2f} to {v['accept'][1]:.2f} mm (YAML thickness_accepted; nominal {P.BASE_T}), sheet {P.PSA_T} +-{v['psa_tol']}, ball protrusion {P.BALL_PROT} +-{M['tol_ball_set']}, "
             f"ball diameter exactly {P.BALL_D}: a thinner plate would let the ball hold the laminate open. The plate thickness also sets the rim relief and the depth of the grain opening, not the seal joint")
    add(f"Same with a ball at the upper diameter limit of grade 100 (E8: dia +{M['ball_dia_tol']}, ABMA figure as remembered)", gap_min - M["ball_dia_tol"], M["ball_gap_min"], dev="D33",
        method="arithmetic on the incoming limits",
        note=f"a ball set to its protrusion on the gauge plate carries its whole diameter error at its top. Incoming rule that restores the {M['ball_gap_min']} mm: measure the ball lot; "
             f"lower plate limit = {v['accept'][0]:.2f} + (lot diameter - {P.BALL_D}), i.e. {v['accept'][0] + M['ball_dia_tol']:.3f} at the grade limit. A grade 25 ball (+{M['ball_dia_tol_g25']}) leaves "
             f"{gap_min - M['ball_dia_tol_g25']:.3f} mm; radial clearance of the largest grade 100 ball in its hole {(P.BALL_HOLE_D - P.BALL_D - M['ball_dia_tol']) / 2:.3f} mm")
    add("Potting epoxy of a ball to the PCB underside (sheet hole backfilled)", min_distance(S["ball_epoxy_1"], S["main_pcb"]), 0.0, nominal=0.0,
        note=f"stage 1 dome at most {M['epoxy_dome_max']} mm over the plate; stage 2 fills the {P.PSA_FOOT_HOLE_D} mm sheet hole, so the ball bears on its "
             f"dia {P.FOOT_LAND_D} copper land through {P.PCB_Z0 - P.BALL_TOP_Z:.2f} mm of epoxy in compression")
    pdbox = PT.photodiode_box().val()
    baffle = S["baffle_ring"] if "baffle_ring" in S else base
    what = "separate ring" if "baffle_ring" in S else "integral ring of the plate"
    add(f"Photodiode body to the baffle ring ({what})", min_distance(pdbox, baffle), clr, nominal=P.BAFFLE_RI - P.PD_HALF_DIAG,
        note=f"ring dia {2 * P.BAFFLE_RI:.1f} / {2 * P.BAFFLE_RO:.1f}; photodiode half diagonal {P.PD_HALF_DIAG:.3f}")
    leds = [b.val() for b in PT.led_boxes()]
    if "baffle_ring" in S:
        add("Grain LEDs to the baffle ring", min(min_distance(b, baffle) for b in leds), clr, nominal=P.LED_R_IN - P.BAFFLE_RO,
            note=f"0402 LEDs on r {P.LED_RING['radius']}: inner edge at r {P.LED_R_IN:.2f}")
        add("Grain LEDs to the wall of the grain opening", min(min_distance(b, base) for b in leds), clr, nominal=P.GRAIN_R - P.LED_R_OUT,
            note=f"plain dia {P.GRAIN_D} hole; outer LED corner at r {P.LED_R_OUT:.3f}")
        add("Baffle ring to the wall of the grain opening", min_distance(baffle, base), clr, nominal=P.GRAIN_R - P.BAFFLE_RO)
        add("Baffle ring crest to the potting surface at its limit (flush in the model)", A.bbox_of(parts["baffle_ring"])[2] - A.bbox_of(parts["grain_potting"])[2], 0.0, nominal=0.0,
            method="bounding boxes", note=f"ring {P.BAFFLE_RING_H:.2f} high on a {P.BAFFLE_PSA_T} mm adhesive annulus; the potting solid is its maximum-material condition (z {P.GRAIN_FILL_Z})")
        plus, minus = M["baffle_ring_tol"]
        cr = P.baffle_crest_range()
        zr1 = A.bbox_of(parts["baffle_ring"])[5]
        add(f"Baffle ring crest with the ring at its upper height limit (+{plus:.2f}): not closer to the base plane than z {P.GRAIN_FILL_Z}", zr1 - (P.BAFFLE_RING_H + plus), P.GRAIN_FILL_Z,
            method="ring top of the solid - tallest ring", note=f"finished height {P.BAFFLE_RING_H:.2f} +{plus:.2f} / -{minus:.2f}, lapped by us (printed {P.BAFFLE_RING_PRINT_H:.2f} high)")
        add("Baffle ring crest above the base plane, worst case (ring lapped to the plate lot and to the tape used)", cr["matched"][0], 0.0, method="arithmetic on the tolerances",
            note=f"ring height = measured plate thickness + {P.BAFFLE_RING_RULE:.2f} - tape thickness (E16; {P.BAFFLE_RING_H:.2f} for the nominal {P.BASE_T} plate and a {P.BAFFLE_PSA_T} tape, i.e. plate + "
                 f"{P.baffle_ring_height(0.0):.2f}); sheet +-{v['psa_tol']}, annulus +-{M['baffle_psa_tol']}, "
                 f"gauging +-{M['plate_gauging_tol']}: crest z {cr['matched'][0]:.2f} to {cr['matched'][1]:.2f}. A ring lapped to {P.BAFFLE_RING_H:.2f} regardless of the plate would end between "
                 f"z {cr['unmatched'][0]:.2f} (proud of the base plane) and {cr['unmatched'][1]:.2f}")
        add(f"Baffle ring crest not deeper than z {P.BAFFLE_CREST_MAX_Z} (acceptance after lamination), worst case", P.BAFFLE_CREST_MAX_Z - cr["matched"][1], 0.0, method="arithmetic on the tolerances",
            note=f"per unit: crest between the base plane and z {P.BAFFLE_CREST_MAX_Z}, measured with a depth gauge after lamination")
        lo_, hi_, _t = P.potting_window(cr["matched"][1])
        pv, pa = S["grain_potting"].Volume(), _potting_areas(S)
        need = 2 * M["potting_dispense_tol"] * pv / sum(pa)
        add("Baffle ring print file: printed height less the tallest finished ring (lapping allowance)", P.BAFFLE_RING_PRINT_H - P.BAFFLE_RING_H_RANGE[1], M["baffle_ring_lap_allowance"],
            nominal=M["baffle_ring_lap_allowance"], method="arithmetic (E16)",
            note=f"finished rings from {P.BAFFLE_RING_H_RANGE[0]:.3f} (plate {v['accept'][0]:.2f}, tape {max(P.BAFFLE_TAPE_RANGE)}, lower height limit) to {P.BAFFLE_RING_H_RANGE[1]:.3f} "
                 f"(plate {v['accept'][1]:.2f}, tape {min(P.BAFFLE_TAPE_RANGE)}); printed {P.BAFFLE_RING_PRINT_H:.2f} high")
        add("Potting window (crest to %.2f inside it, within z %.2f to %.2f) with the crest at its deepest: width" % (M["grain_fill_below_crest"], P.GRAIN_FILL_Z, P.GRAIN_FILL_Z_MAX),
            hi_ - lo_, need, method="window width against the dispenser accuracy",
            note=f"window z {lo_:.2f} to {hi_:.2f}; a dispenser good to +-{100 * M['potting_dispense_tol']:.0f} % places the level within +-{need / 2:.3f} mm; the level is checked wet and trimmed before cure")
    else:
        add("Grain LEDs to opening wall / baffle ring / spokes", min(min_distance(b, base) for b in leds), clr,
            note=f"integral ring on spokes at {P.SPOKE_ANGLES} deg; LEDs from r {P.LED_R_IN:.2f} to {P.LED_R_OUT:.3f}")
    zp = A.bbox_of(parts["grain_potting"])[2]
    lo_, hi_, tg_ = P.potting_window()
    add("Potting surface inside the grain opening (above the base plane), maximum-material condition", zp - A.bbox_of(parts["base_plate"])[2], P.GRAIN_FILL_Z, nominal=P.GRAIN_FILL_Z,
        method="bounding boxes", note=f"the surface must never be closer to the base plane than z {P.GRAIN_FILL_Z} (the modelled solid); accepted for the nominal crest: z {lo_:.2f} to {hi_:.2f}, "
        f"fill target z {tg_:.3f}; a wall meniscus may reach, not pass, the base plane; the ball feet are {P.GRAIN_FILL_Z + P.BALL_PROT:.2f} below z {P.GRAIN_FILL_Z}")
    cover = min(P.PCB_Z0 - P.LED_RING["led_height"], P.PCB_Z0 - P.PD["h"]) - zp
    add("Potting over the tallest embedded part (photodiode)", cover, M["grain_fill_min_cover"], nominal=P.GRAIN_FILL_DEPTH - max(P.LED_RING["led_height"], P.PD["h"]),
        method="heights", note=f"LEDs {P.LED_RING['led_height']} and photodiode {P.PD['h']} high under {P.GRAIN_FILL_DEPTH:.2f} of potting")
    add(f"Potting over the photodiode with the surface at the deepest accepted level (z {P.GRAIN_FILL_Z_MAX})", P.PCB_Z0 - P.PD["h"] - P.GRAIN_FILL_Z_MAX, M["grain_fill_min_cover"],
        nominal=P.PCB_Z0 - P.PD["h"] - P.GRAIN_FILL_Z_MAX, method="heights", note=f"inspection window of the potting surface: z {P.GRAIN_FILL_Z} to z {P.GRAIN_FILL_Z_MAX}")
    add("Spring-pin plunger to base-plate slot, radial", _sec_dist(S["spring_pin_4"], base, "z", 0.5 * P.BASE_T), clr,
        nominal=(P.PAD_HOLE_D - M["pin_plunger_dia"]) / 2, method=f"section z = {0.5 * P.BASE_T:.3f}", note="pin diameters PROVISIONAL")
    add("Base plate underside above the nest strip and pads (ball protrusion)", min_distance(base, S["cradle"]), P.BALL_PROT, nominal=P.BALL_PROT,
        note="the three balls carry the marker on the front strip and the two pads; the rest of the nest floor is a drained basin")


def _potting_areas(S):
    """Free-surface area of the clear potting per compartment (mm2), largest first: section of the potting solid just
    inside its surface."""
    sec = G.section_polys(S["grain_potting"], "z", P.GRAIN_FILL_Z + 0.01, 2e-4)
    return sorted((g.area for g in getattr(sec, "geoms", [sec]) if not g.is_empty), reverse=True)


def _potting_table(S):
    """Volumes and levels of the clear potting, from the potting solid of the active base variant (the solid is the fill
    to z = GRAIN_FILL_Z, the level that must never be passed)."""
    cells = []
    for sol in S["grain_potting"].Solids():
        sec = G.section_polys(sol, "z", P.GRAIN_FILL_Z + 0.01, 2e-4)      # the free surface of THIS compartment
        c = cq.Shape.centerOfMass(sol)                                    # the disc inside the ring: centred, and no larger than the ring bore
        inside = math.hypot(c.x - P.GRAIN_X, c.y - P.GRAIN_Y) < 0.5 * P.BAFFLE_RI and sec.area <= math.pi * P.BAFFLE_RI ** 2 + 0.05
        cells.append((sol.Volume(), sec.area, "inside the baffle ring" if inside else "outside the baffle ring"))
    cells.sort(key=lambda t: (t[2] != "inside the baffle ring", -t[0]))
    lo, hi, tg = P.potting_window()
    rows = []
    for vol, a, where in cells:
        rows.append(dict(compartment=where, free_surface_mm2=round(a, 2), volume_to_the_limit_z_mm3=round(vol, 2),
                         volume_to_the_fill_target_mm3=round(vol - a * (tg - P.GRAIN_FILL_Z), 2), volume_to_the_deepest_accepted_level_mm3=round(vol - a * (hi - P.GRAIN_FILL_Z), 2),
                         change_per_0p01_mm_of_level_mm3=round(0.01 * a, 3), change_per_0p1_mm_of_opening_depth_mm3=round(0.1 * a, 2)))
    tv, ta = sum(c_[0] for c_ in cells), sum(c_[1] for c_ in cells)
    rows.append(dict(compartment="TOTAL", free_surface_mm2=round(ta, 2), volume_to_the_limit_z_mm3=round(tv, 2), volume_to_the_fill_target_mm3=round(tv - ta * (tg - P.GRAIN_FILL_Z), 2),
                     volume_to_the_deepest_accepted_level_mm3=round(tv - ta * (hi - P.GRAIN_FILL_Z), 2), change_per_0p01_mm_of_level_mm3=round(0.01 * ta, 3),
                     change_per_0p1_mm_of_opening_depth_mm3=round(0.1 * ta, 2)))
    return rows, (lo, hi, tg)


def check_clearances(parts):
    S = _solids(parts)
    tub = S["tub"]
    T = _Rows()
    add, rows, fails, warns = T.add, T.rows, T.fails, T.warns
    clr = P.CLR

    zg = 0.5 * (P.LCD_Z0 + P.LCD_Z1)
    # --- display stack against the cameras
    for s in ("L", "R"):
        add(f"LCD glass to camera cube {s}", min_distance(S["lcd_glass"], S[f"camera_{s}"]), clr)
        add(f"LCD glass to prism {s}", min_distance(S["lcd_glass"], S[f"prism_{s}"]), clr)
    add("LCD glass to tub, lateral (ribs, posts B and E, hood rear walls)", _sec_dist(S["lcd_glass"], tub, "z", zg), clr, nominal=clr,
        method=f"section z = {zg:.3f}", note=f"posts B are cut back to /x/ >= {P.LCD_POCKET_X} for this gap (YAML post_feet.locating.foot, N1)")
    add("LCD glass to roof bonding plane (adhesive frame)", min_distance(S["lcd_glass"], tub), P.LCD_PSA_T, nominal=P.LCD_PSA_T)
    add("LCD glass rear corners to side wall", P.R_IN - math.hypot(P.LCD_X1, P.LCD_Y0), clr, method="radius of the glass corner vs wall R",
        note=f"corner r = {math.hypot(P.LCD_X1, P.LCD_Y0):.3f}; the same corners do NOT pass the seating ledge (r {P.LEDGE_RI}): see D11")
    # --- battery and its leads
    bat = P.BAT
    add("Battery to foam pad", min_distance(S["battery"], S["foam_pad"]), P.BAT_SWELL, nominal=P.FOAM_Z0 - bat["z1"],
        note=f"swell allowance {P.BAT_SWELL}: {P.FOAM_Z0 - bat['z1'] - P.BAT_SWELL:.2f} mm left when fully swollen (the fixing adhesive, up to {P.BAT_FIX_T}, comes out of it)")
    add("Battery to LCD glass", min_distance(S["battery"], S["lcd_glass"]), P.BAT_SWELL + P.FOAM_T, nominal=P.LCD_Z0 - bat["z1"])
    add("Battery to tub (posts, ledge)", min_distance(S["battery"], tub), clr)
    add("Foam pad to tub", min_distance(S["foam_pad"], tub), clr)
    leads = [S[n] for n in parts if n.startswith("battery_lead_")]
    add("Battery leads and joints (envelope) to tub", min(min_distance(l, tub) for l in leads), clr,
        note=f"two pads {P.BAT_PAD_SIZE[0]} x {P.BAT_PAD_SIZE[1]} in the YAML zone x {P.BAT_PAD_ZONE[0]}..{P.BAT_PAD_ZONE[2]}, y {P.BAT_PAD_ZONE[1]}..{P.BAT_PAD_ZONE[3]}; "
             f"joint up to {P.BAT_JOINT_H} mm above the PCB (z {P.PCB_Z1 + P.BAT_JOINT_H:.2f})")
    add("Battery leads and joints to LCD glass / foam pad", min(min_distance(l, S[n]) for l in leads for n in ("lcd_glass", "foam_pad")), clr)
    add("Battery lead joint top below the free height", P.KO_FREE_Z - max(A.bbox_of(parts[n])[5] for n in parts if n.startswith("battery_lead_")), 0.0,
        nominal=P.PCB_FREE_H - P.BAT_JOINT_H, method="bounding boxes", note=f"free height z {P.KO_FREE_Z:.2f}")
    # --- PCB against the tub
    board = S["main_pcb"]                                    # the PCB solid of THIS build (at these levels its section is the bare board)
    zl = 0.5 * (max(P.LEDGE_Z0, P.PCB_Z0) + min(P.LEDGE_Z1, P.PCB_Z1))
    add("PCB edge to seating ledge, radial", _sec_dist(board, tub, "z", zl, clip=(-25, -25, 25, 9)), clr, nominal=P.LEDGE_RI - P.PCB_R,
        method=f"section z = {zl:.2f}", note=f"PCB radius {P.PCB_R}")
    zs = 0.5 * (P.SPIGOT_Z0 + P.PCB_Z1)
    rx, ry, _ = P.LOC_ROUND; sx, sy, sd, sl = P.LOC_SLOT
    add("PCB locating spigot in the round hole, radial", _sec_dist(board, tub, "z", zs, clip=(rx - 1.0, ry - 1.0, rx + 1.0, ry + 1.0)), clr,
        nominal=P.SPIGOT_FIT, dev="D19", method=f"section z = {zs:.2f} of the main PCB solid", note="locating fit specified in the YAML, not a drop-in fit; go gauge dia 1.10 at first article. "
        "The row FAILS when the fit of the solid differs from the YAML fit by more than 0.01 (a hole or a spigot off its position)")
    add("PCB locating spigot in the slot, across the slot (y)", _sec_dist(board, tub, "z", zs, clip=(sx - 1.0, sy - 1.0, sx + 1.0, sy + 1.0)), clr,
        nominal=(sd - P.SPIGOT_D) / 2, dev="D19", method=f"section z = {zs:.2f} of the main PCB solid", note=f"along the slot (x): {(sl - P.SPIGOT_D) / 2:.3f} mm each way; a slot off its centre line fails this row")
    add("Spigot tip to the adhesive sheet", P.SPIGOT_Z0 - A.bbox_of(parts["pcb_adhesive"])[5], 0.1, nominal=P.SPIGOT_Z0 - P.PSA_Z1, method="bounding boxes",
        note="the spigot ends inside the PCB hole")
    add("PCB flat edge to visor wall", _sec_dist(board, tub, "z", zl, clip=(-3, 15.5, 3, 20)), clr, nominal=P.Y_VISOR_IN - P.PCB_FLAT,
        method=f"section z = {zl:.2f}, |x| < 3")
    # --- base plate, seal joint, ball feet, grain opening (the rows that depend on the base-plate variant)
    _base_rows(parts, S, T)
    # --- cover glass
    zc = 0.5 * (P.CG_Z0 + P.CG_Z1)
    add("Cover glass to recess wall, radial", _sec_dist(S["cover_glass"], tub, "z", zc), clr, nominal=(P.RECESS_D - P.CG_D) / 2,
        method=f"section z = {zc:.2f}")
    add("Cover glass underside to recess floor (tape ring)", min_distance(S["cover_glass"], tub), P.CG_TAPE_T, nominal=P.CG_TAPE_T,
        note=f"transfer-tape ring dia {P.CG_D} / {M['cover_tape_id']}")
    add("Cover glass top below the tub top (sub-flush)", P.T - A.bbox_of(parts["cover_glass"])[5], P.Y["cover_glass"]["sub_flush"], nominal=P.CG_BELOW_FLUSH,
        method="bounding box", note="rev D: 0.12 below flush (was 0.05)")
    # --- E9: optional quarter-wave retarder film on the underside of the cover glass (EVT trial; not part of the primary build)
    if "retarder_film" in parts:
        rf, rbb = S["retarder_film"], A.bbox_of(parts["retarder_film"])
        zf = 0.5 * (rbb[2] + rbb[5])
        tol_gap = P.CG_TAPE_T * M["tol_sheet_frac"] + M["retarder_t_tol"]
        add("Optional retarder film (E9): bonded to the underside of the cover glass", min_distance(rf, S["cover_glass"]), 0.0, nominal=0.0,
            note=f"quarter-wave film with its laminating adhesive, {P.RETARDER_T} mm, dia {P.RETARDER_D}; axis at 45 deg to the LCD polariser (not a mechanical item)")
        add("Optional retarder film to the display (LCD glass top)", min_distance(rf, S["lcd_glass"]), clr, nominal=P.RETARDER_Z0 - P.LCD_Z1,
            note=f"air between display and glass {P.CG_Z0 - P.LCD_Z1:.2f} mm without the film")
        add("Optional retarder film to the roof ledge under it (the film lies in the tape gap outside the aperture)", min_distance(rf, tub), tol_gap, nominal=P.RETARDER_LEDGE_GAP,
            note=f"required: more than the tolerances that close it (tape {P.CG_TAPE_T} -{100 * M['tol_sheet_frac']:.0f} %, film +{M['retarder_t_tol']}): {P.RETARDER_LEDGE_GAP_MIN:.3f} mm is left then. "
                 f"A film thicker than {P.RETARDER_T + M['retarder_t_tol']:.2f} mm would carry the glass off its tape: cut it to dia {P.APERTURE_D - 2 * clr:.1f} (inside the aperture) instead")
        add("Optional retarder film to the bore of the tape ring, radial (the tape ring still seats on glass)", _sec_dist(rf, S["cover_tape"], "z", zf), clr,
            nominal=(M["cover_tape_id"] - P.RETARDER_D) / 2, method=f"section z = {zf:.2f}", note=f"tape ring dia {P.CG_D} / {M['cover_tape_id']}: its whole {P.CG_TAPE_W} mm width stays on bare glass")
        add("Optional retarder film: overlap beyond the display aperture, radial", 0.5 * (rbb[3] - rbb[0]) - P.APERTURE_D / 2, clr, nominal=(P.RETARDER_D - P.APERTURE_D) / 2,
            method="bounding box", note=f"aperture dia {P.APERTURE_D}: the film edge is hidden under the roof ledge")
        ch = P.retarder_chain()
        d_bore = _sec_dist(rf, S["cover_tape"], "z", zf)
        add("Optional retarder film to the bore of the tape ring AFTER THE CENTRING CHAIN, worst case", d_bore - (ch["place"] + ch["glass"] + ch["tape"]), 0.0,
            method="radial gap of the solids less the three placements", note=f"film on the glass +-{ch['place']} (lamination nest), glass in its recess +-{ch['glass']}, tape ring in the same recess "
            f"+-{ch['tape']}: {ch['place'] + ch['glass'] + ch['tape']:.2f} worst case, {math.sqrt(ch['place'] ** 2 + ch['glass'] ** 2 + ch['tape'] ** 2):.2f} RSS ({ch['bore'][2]:.2f} left at RSS). "
            "A film that reached under the tape would lift the glass off its seal")
        add("Optional retarder film: overlap beyond the aperture AFTER THE CENTRING CHAIN, worst case (round edge)", 0.5 * (rbb[3] - rbb[0]) - P.APERTURE_D / 2 - (ch["place"] + ch["glass"]), 0.0,
            method="overlap of the solid less two placements", note=f"film on the glass +-{ch['place']} and glass in its recess +-{ch['glass']} (the aperture is part of the tub); {ch['aperture'][2]:.2f} left at RSS")
        add("Optional retarder film: clocking flat beyond the aperture (the flat is the chord toward the visor)", rbb[4] - P.APERTURE_D / 2, clr, nominal=M["retarder_flat_overlap"],
            method="bounding box (y max of the film)", note=f"flat {P.RETARDER_FLAT_LEN:.2f} mm long at y = {P.RETARDER_FLAT_Y}: it carries the film axis from the die cut to the tub (lamination nest with a straight stop, "
            f"edge mark on the crystal, mark set to the nose groove within +-{M['retarder_clock_tol_deg']:.0f} deg); after the chain {ch['flat'][1]:.2f} worst case, {ch['flat'][2]:.2f} at RSS: the flat may "
            "just reach the aperture edge, never the round edge")
        v_rf = max(common_volume(rf, S[n]) for n, i in parts.items() if i.group == "puck")
        add("Optional retarder film: interference with any part of the marker (mm3, negated)", -v_rf, -INTERFERENCE_LIMIT_MM3, method="boolean common with every marker part",
            note="the film is not in the assembly of check 1; this row is its interference check")
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
        wb = A.bbox_of(parts[f"visor_window_{s}"])
        add(f"Visor window {s} to recess sides", _sec_dist(w, tub, "y", 0.5 * (P.WIN_Y0 + P.WIN_Y1), clip=(cx - 5, P.WIN_Z0 + 0.3, cx + 5, P.T)),
            clr, nominal=(P.WIN_RECESS_W - P.WIN_W) / 2, method="section through the window, above the shelf", note="gaps filled with the window adhesive")
        add(f"Visor window {s} front face below the visor face (sub-flush)", P.Y_VISOR - wb[4], P.WIN_RECESS_DEPTH - P.WIN_T, nominal=P.WIN_SUBFLUSH,
            method="bounding box", note=f"{P.WIN_T} mm glass seated on the floor of the {P.WIN_RECESS_DEPTH} recess (YAML visor_window.sub_flush, bond_line {M['window_bond']}: N2)")
        add(f"Visor window {s} top edge below the tub top", P.T - wb[5], P.T - (P.WIN_Z0 + P.Y['visor_window']['h']), nominal=P.WIN_TOP_BELOW,
            method="bounding box", note=f"window {P.WIN_W} x {P.WIN_H} x {P.WIN_T}")
        add(f"Visor window {s} rear face to recess floor", min_distance(w, tub), 0.0, nominal=M["window_bond"],
            note="seated on the floor and on its shelf; the seal is the adhesive frame round its edge (side gaps, top bead, sill fillet): check 13")
        add(f"Window adhesive {s}: sill fillet behind the visor face", P.Y_VISOR - A.bbox_of(parts[f"window_bond_{s}"])[4], 0.0, nominal=P.WIN_FRAME_BELOW_FACE, method="bounding box",
            note=f"fillet {P.WIN_SILL_FILLET} x {P.WIN_SILL_FILLET} on the shelf in front of the bottom edge of the glass")
        add(f"Window adhesive {s}: top bead below the tub top", P.T - A.bbox_of(parts[f"window_bond_{s}"])[5], 0.0, nominal=P.T - P.WIN_TOP_Z - M["window_top_bead"], method="bounding box")
        hsb = A.bbox_of(parts[f"hood_seal_{s}"])
        add(f"Hood gasket bead {s} (as squeezed, constant volume) to the prism", min_distance(S[f"hood_seal_{s}"], S[f"prism_{s}"]), 0.1,
            note=f"bead {M['hood_seal_w']} wide x {M['hood_seal_free_h']} high as dispensed (parabolic segment, {P.HOOD_SEAL_VOL:.2f} mm3), centred {M['hood_seal_centre']} in front of the rear face "
                 "of the hood rear wall; cured before the join; the cube top flattens it to the slit height")
        add(f"Hood gasket bead {s}: volume of the squeezed solid = volume dispensed", S[f"hood_seal_{s}"].Volume(), 0.99 * P.HOOD_SEAL_VOL, nominal=P.HOOD_SEAL_VOL, method="volume of the solid, mm3",
            note="a solid elastomer keeps its volume: what the cube displaces is moved forward under the bead")
        add(f"Hood gasket bead {s}: front edge behind the chamfer of the rear wall", P.HOOD_FLAT_Y1 - hsb[4], 0.0, method="bounding box",
            note=f"flat underside of the rear wall from y {P.HOOD_REAR_Y0} to {P.HOOD_FLAT_Y1:.3f}")
    add("Hood gasket bead: squeezed land on the cube top, width", P.HOOD_SEAL_CONTACT_W, M["hood_seal_min_land"], method="constant-volume section (params.hood_seal_section)",
        note=f"peak squeeze {100 * P.HOOD_SEAL_COMPRESSION:.0f} % of the free height; standing load about {P.HOOD_SEAL_LOAD_N:.2f} N per hood at E = {M['hood_seal_E_MPa']} MPa (estimate)")
    add("Hood gasket bead: peak squeeze below the limit for a solid form-in-place bead", M["hood_seal_max_squeeze"] - P.HOOD_SEAL_COMPRESSION, 0.0, method="(free height - slit) / free height",
        note=f"slit {P.HOOD_SLIT[0]:.2f} mm, free height {M['hood_seal_free_h']} mm; limit {100 * M['hood_seal_max_squeeze']:.0f} %")
    add("Hood gasket bead: placement window of its centre line (the smaller side)", min(P.HOOD_SEAL_WINDOW), M["hood_seal_place_tol"], method="bead edges against the flat of the rear wall",
        note=f"-{P.HOOD_SEAL_WINDOW[0]:.3f} / +{P.HOOD_SEAL_WINDOW[1]:.3f} mm about y {P.HOOD_SEAL_YC:.2f}; dispensed along a needle guide that registers on the rear face of the rear wall")
    # --- vent, flex
    others = [n for n, i in parts.items() if i.group == "puck" and n not in ("tub", "vent")]
    dv, nv = min((min_distance(S["vent"], S[n]), n) for n in others)
    add(f"Vent disc to nearest part ({nv})", dv, clr)
    add("LCD flex (representative shape) to tub", min_distance(S["lcd_flex"], tub), 0.0, note="PROVISIONAL tail geometry")
    add("LCD flex (representative shape) to connector J1 / PCB parts", min_distance(S["lcd_flex"], S["main_pcb"]), 0.0, nominal=0.0,
        note=f"PROVISIONAL tail geometry: one U-fold of radius {P.FLEX_BEND_R:.2f} mm, modelled up to the J1 mouth face (entry {M['fpc_entry_h']} mm above the PCB)")
    # --- cradle (nest, lip, latch, one pin slot)
    cr = S["cradle"]
    lipS, latchS, body_nl = PT.lip().val(), PT.latch().val(), _cradle_without_latch()
    add("Marker to nest wall, radial", _sec_dist(tub, cr, "z", 1.5), clr, nominal=clr, method="section z = 1.5")
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
        prow.append(dict(ref=ref, part=p["name"], x=p["x"], y=p["y"], top_z=R3(P.PCB_Z1 + p["h"]), to_tub_mm=R3(d_tub), to_lcd_glass_or_foam_mm=R3(d_lcd),
                         to_battery_mm=R3(d_bat), status="ok" if ok else "FAIL"))
    # --- table 2c: stack tolerance and thermal estimates (arithmetic on assumed inputs, both base variants)
    srow, trow = [], []
    for key in P.BASE_VARIANTS:
        with P.base_variant(key):
            for tp_, tname in ((M["tol_printed"], f"+-{M['tol_printed']} on the printed tub dimension (REQUIRED on drawing GL1-010)"),
                               (M["print_tol"], f"+-{M['print_tol']} on the printed tub dimension (the bureau's general tolerance)")):
                st = P.stack_tolerance(printed=tp_)
                for cname, label in (("joint", "seal joint: base top to tub seal face"), ("rim", "tub rim above the base plane (rim relief)"),
                                     ("ball", "epoxy between ball top and copper land")):
                    c = st[cname]
                    if cname == "ball" and tp_ != M["tol_printed"]:
                        continue                              # no printed dimension in this chain
                    extra = ""
                    if cname == "rim":
                        extra = f"rim above the plane of the ball feet: {c['nominal'] + P.BALL_PROT - c['rss']:.2f} at the RSS limit, {c['nominal'] + P.BALL_PROT - c['worst']:.2f} worst case"
                    if cname == "ball":
                        extra = f"with the plates sorted to {P.BASE['accept'][0]:.2f} .. {P.BASE['accept'][1]:.2f} the gap is never below {M['ball_gap_min']:.2f}"
                    srow.append(dict(base_plate=P.BASE["label"], quantity=label, nominal_mm=R3(c["nominal"]), chain="; ".join(f"{n} +-{t}" for n, t in c["chain"]),
                                     printed_tolerance=(tname if cname != "ball" else "-"), rss_mm=R3(c["rss"]), worst_case_mm=R3(c["worst"]),
                                     range_rss_mm=(R3(c["nominal"] - c["rss"]), R3(c["nominal"] + c["rss"])),
                                     range_worst_case_mm=(R3(c["nominal"] - c["worst"]), R3(c["nominal"] + c["worst"])), note=extra))
    potrow, (pw_lo, pw_hi, pw_tg) = _potting_table(S)
    v_tg = next(r for r in potrow if r["compartment"] == "TOTAL")["volume_to_the_fill_target_mm3"]
    add("Clear potting to the fill target: model volume against YAML fill_volume_nominal_mm3 (within 0.1 mm3)", 0.1 - abs(v_tg - P.GRAIN_FILL_VOL_YAML), 0.0,
        method="potting solid less its free surface x (target - limit)", note=f"model {v_tg} mm3 to z {pw_tg:.2f}; YAML {P.GRAIN_FILL_VOL_YAML} mm3 (fill_surface_z.target {P.GRAIN_FILL_TARGET_Z})")
    # E16: baffle-ring height by tape thickness (the tape is 0.10 to 0.145 mm as available; the ring is lapped to plate lot and tape)
    v0 = P.BASE_VARIANTS[P.BASE_PRIMARY]
    crr = P.baffle_crest_range()
    erow = []
    for tape in sorted({min(P.BAFFLE_TAPE_RANGE), P.BAFFLE_PSA_T, max(P.BAFFLE_TAPE_RANGE)}):
        h_nom, h_lo, h_hi = (P.baffle_ring_height(t_, tape) for t_ in (v0["thickness"], v0["accept"][0], v0["accept"][1]))
        ok_e = crr["matched"][0] >= -1e-9 and crr["matched"][1] <= P.BAFFLE_CREST_MAX_Z + 1e-9 and P.BAFFLE_RING_PRINT_H - h_hi >= M["baffle_ring_lap_allowance"] - 1e-9
        if not ok_e:
            fails.append(f"baffle ring for a {tape} mm tape")
        erow.append(dict(tape_mm=tape, tape=("modelled (YAML ring height)" if abs(tape - P.BAFFLE_PSA_T) < 1e-9 else "available tape (E16)"),
                         ring_height_rule=f"plate + {P.BAFFLE_RING_RULE:.2f} - {tape:g} = plate + {P.BAFFLE_RING_RULE - tape:.3f}",
                         ring_height_for_the_nominal_plate_mm=R3(h_nom), for_the_thinnest_and_thickest_accepted_plate_mm=(R3(h_lo), R3(h_hi)),
                         height_tolerance_mm=f"+{M['baffle_ring_tol'][0]:.2f} / -{M['baffle_ring_tol'][1]:.2f}", lapped_off_the_printed_ring_mm=(R3(P.BAFFLE_RING_PRINT_H - h_hi), R3(P.BAFFLE_RING_PRINT_H - h_lo)),
                         crest_z_nominal=P.BAFFLE_RING_Z0, crest_z_range=crr["matched"], crest_window_z=(0.0, P.BAFFLE_CREST_MAX_Z), status="ok" if ok_e else "FAIL"))
    dT = max(abs(t - M["t_assembly"]) for t in M["t_range"])
    th = lambda length, a1, a2: length * abs(a1 - a2) * 1e-6 * dT
    r_cg, r_lcd = P.CG_D / 2, math.hypot(P.LCD["dx"] / 2, P.LCD["dy"] / 2)
    for label, length, a1, a2, layer, lname in (
            ("cover glass edge against the tub", r_cg, M["cte_pa12"], M["cte_glass"], P.CG_TAPE_T, "tape ring"),
            ("LCD glass corner against the tub", r_lcd, M["cte_pa12"], M["cte_lcd"], P.LCD_PSA_T, "adhesive frame"),
            ("PCB edge against the base plate, FR-4 plate (primary)", P.PCB_R, M["cte_fr4"], P.BASE_VARIANTS["fr4"]["cte"], P.BASE_VARIANTS["fr4"]["psa_t"], "adhesive sheet"),
            ("PCB edge against the base plate, PA12 plate (alternative)", P.PCB_R, M["cte_fr4"], P.BASE_VARIANTS["pa12"]["cte"], P.BASE_VARIANTS["pa12"]["psa_t"], "adhesive sheet"),
            ("the two spigots (tub) against the PCB holes", P.SPIGOT_SPAN, M["cte_pa12"], M["cte_fr4"], None, f"slot allows +-{(P.LOC_SLOT[3] - P.SPIGOT_D) / 2:.3f}")):
        d = th(length, a1, a2)
        trow.append(dict(pair=label, length_mm=R3(length), cte_ppm_per_K=(a1, a2), temperature_span_K=dT, relative_movement_mm=R3(d),
                         shear_of_the_layer_pct=(round(100 * d / layer) if layer else "-"), layer=(f"{lname} {layer}" if layer else lname)))
    notes = ["required minimum = 0.25 mm drop-in rule unless the row is a specified stack value (adhesive lines, prism-to-roof 0.19, sub-flush values)",
             f"passives are not in master_params.yaml, so only the {len(P.TOP_PARTS)} listed top-side parts are checked here; the real board is checked by check 17",
             "the optional retarder film (E9) is checked by its own rows; it is not part of the assembly of checks 1, 8, 13 and 14",
             "sections are true boolean sections of the solids; curved edges are sampled to 0.0002 mm",
             f"comparisons carry a numerical tolerance of {NUM_TOL} mm",
             f"tolerance chains are arithmetic on ASSUMED part tolerances (critical printed tub dimensions +-{M['tol_printed']} as drawing GL1-010 requires, or +-{M['print_tol']} as the "
             f"bureau quotes in general; PCB +-{M['tol_pcb']}; sheet +-{100 * M['tol_sheet_frac']:.0f} %; FR-4 plate +-{M['tol_fr4_plate']}, PA12 plate +-{M['tol_pa12_plate']}; ball protrusion "
             f"+-{M['tol_ball_set']}). The posts seat on the PCB top, so the seal joint = PCB - printed step + sheet and does not depend on the plate thickness; the plate sets "
             "the rim relief, the gap under the balls and the depth of the grain opening",
             f"thermal estimates use handbook expansion coefficients over {M['t_range'][0]:.0f} to {M['t_range'][1]:.0f} C from a {M['t_assembly']:.0f} C assembly; nothing here is measured",
             f"clear potting: the modelled solid is the fill to z {P.GRAIN_FILL_Z}, the level that must never be passed; the fill target is the middle of the accepted window; "
             f"mixed viscosity {M['potting_viscosity_Pa_s'][0]} to {M['potting_viscosity_Pa_s'][1]} Pa.s (estimate), vacuum degassing"]
    worst = min((r for r in rows if r["margin_mm"] is not None), key=lambda r: r["margin_mm"])
    return res(2, "clearances", not fails,
               (f"{len(rows)} key gaps and {len(prow)} PCB parts evaluated; {len(warns)} rows below their minimum are recorded deviations (the two spigot fits, D19; the epoxy under an oversize "
                f"grade 100 ball, D33); retarder film after its centring chain: {P.retarder_chain()['bore'][1]:.2f} to the tape bore, {P.retarder_chain()['aperture'][1]:.2f} beyond the aperture (worst case); "
                f"smallest margin {worst['margin_mm']} mm ({worst['item']})" if not fails else f"FAILED: {fails}"),
               [dict(title="Key clearances", rows=rows), dict(title="PCB top-side parts (envelope boxes from the YAML)", rows=prow),
                dict(title="Tolerance chains: seal joint, rim relief, ball to land (both base-plate variants)", rows=srow),
                dict(title=f"Clear potting: volumes and levels (FR-4 build; accepted z {pw_lo:.2f} to {pw_hi:.2f}, fill target z {pw_tg:.3f} for the nominal ring crest)", rows=potrow),
                dict(title="Baffle ring height by tape thickness (E16: ring height = plate thickness + %.2f - tape thickness)" % P.BAFFLE_RING_RULE, rows=erow),
                dict(title="Thermal estimates (handbook coefficients, not measured)", rows=trow)],
               notes, warns)


# ==============================================================================================
# 3. field of view
# ==============================================================================================
def check_fov(parts):
    S = _solids(parts)
    rows, fails, warns = [], [], []
    for side in ("L", "R"):
        other = "R" if side == "L" else "L"
        required = ["tub", "base_plate", "seal_bead", f"window_bond_{side}", f"camera_{other}", f"prism_{other}", f"visor_window_{other}"]
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
    spec = dict(left=P.FOV_H, right=P.FOV_H, up=P.FOV_UP, down=P.FOV_DOWN)                 # YAML cameras.field_required_deg
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
    a_w = math.radians(P.FOV_H)
    shift_w = P.WIN_T * (math.tan(a_w) - math.tan(math.asin(math.sin(a_w) / M["n_window"])))
    notes = [f"frustum: ruled solid between the bounding rectangle of the traced rays on the exit-face plane (y = {yn}) and on the plane 200 mm in front of it; "
             f"chief-ray rectangle at the exit face x = cam x {rn[0] - cx:+.3f}..{rn[1] - cx:+.3f}, z = {rn[2]:.3f}..{rn[3]:.3f}",
             "rays are traced exactly through the prism (optics.py); the entrance-pupil position and diameter are ASSUMED",
             "'left/right' = toward -x/+x, 'up/down' = toward +z/-z in object space",
             f"the lower field edge ({M['fov_down_deg']} deg) meets the base plane about {turf:.1f} mm in front of the virtual pupil - turf, not a part",
             f"the visor windows are treated as transparent plates (the {P.WIN_T} mm plate shifts a {P.FOV_H:.0f} deg ray by about {shift_w:.2f} mm; not modelled); "
             f"rev D window {P.WIN_W} x {P.WIN_H} x {P.WIN_T}: it covers the opening with lands of {P.WIN_LANDS[0]:.2f} (sides), {P.WIN_LANDS[1]:.2f} (sill) and "
             f"{P.WIN_LANDS[2]:.2f} mm (top), and the adhesive round it lies outside every frustum (rows window_bond)",
             f"required field (YAML cameras.field_required_deg): +-{P.FOV_H} deg horizontal, +{P.FOV_UP} / -{P.FOV_DOWN} deg vertical; the upper edge is accepted "
             f"with {P.FOV_UP_GUAR} deg guaranteed at the tolerance limit (check 4)",
             f"the lower field is required only to -{M['fov_down_deg']} deg (flagstick base near the horizon); the sill stays at z {P.OPEN_Z0} and the "
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
    # tolerance sensitivity: move camera + prism relative to the tub.  Rev D: the PCB is located by the two spigots under
    # posts B (SPIGOT_SPAN apart, the cameras between them), so the play at a camera is the spigot fit itself
    pl = P.spigot_play()
    dx, dy, yaw_deg = pl["side"], pl["fore_aft"], pl["yaw_deg"]
    tp = M["print_tol"]
    cases = [("nominal", (0, 0, 0)),
             (f"spigot play sideways: optics {dx:.3f} in x", (dx, 0, 0)),
             (f"spigot play plus {tp} print tolerance: {dx + tp:.3f} sideways", (dx + tp, 0, 0)),
             (f"spigot fore-aft play: optics {dy:.3f} toward the visor", (0, dy, 0)),
             (f"spigot fore-aft play: optics {dy:.3f} away from the visor (yaw {yaw_deg:.2f} deg when the two spigots oppose)", (0, -dy, 0)),
             (f"fore-aft play plus {tp} print tolerance: optics {dy + tp:.3f} away from the visor", (0, -dy - tp, 0)),
             (f"optics {tp} low (print tolerance on the sill)", (0, 0, -tp)),
             (f"optics {tp} high (print tolerance on the roof), no play", (0, 0, tp)),
             (f"GUARANTEED CASE (YAML up_guaranteed, N3): optics {tp} high AND the spigot play {dy:.3f} away from the visor", (0, -dy, tp))]
    srows = []
    up_limit = up_play = None
    up_side = {}                                             # upper field of the full pupil in the guaranteed case, per camera
    for label, sh in cases:
        # the full table is traced on camera R; the upper field, the quantity with no margin, is traced on BOTH cameras in every case
        # (camera L with the mirrored sideways shift) and the SMALLER value is the one that is compared
        lim = {d: O.limit_angle("R", d, rc, True, shift=sh)[0] for d in ("left", "right", "up", "down")}
        limc = {d: O.limit_angle("R", d, rc, False, shift=sh)[0] for d in ("left", "right", "up", "down")}
        up_l = O.limit_angle("L", "up", rc, True, shift=(-sh[0], sh[1], sh[2]))[0]
        up_both = min(lim["up"], up_l)
        worst = min(O.bundle("R", th, tv, rc, shift=sh, n_rim=48, n_rings=8)["total_fraction"] for _, th, tv in O.field_points())
        if label.startswith("optics") and sh == (0, 0, tp):
            up_limit = up_both
        if label.startswith("GUARANTEED CASE"):
            up_play = up_both
            up_side = dict(L=up_l, R=lim["up"])
            worst = min(worst, min(O.bundle("L", th, tv, rc, shift=sh, n_rim=48, n_rings=8)["total_fraction"] for _, th, tv in O.field_points()))
        srows.append(dict(case=label, shift_xyz=tuple(round(v, 3) for v in sh),
                          full_pupil_clear_deg_left_right_up_down=tuple(round(lim[d], 2) for d in ("left", "right", "up", "down")),
                          chief_clear_deg_left_right_up_down=tuple(round(limc[d], 2) for d in ("left", "right", "up", "down")),
                          upper_field_full_pupil_deg_camera_R=round(lim["up"], 2), upper_field_full_pupil_deg_camera_L=round(up_l, 2),
                          upper_field_full_pupil_deg=round(up_both, 2), upper_field_margin_to_required_deg=round(up_both - P.FOV_UP, 2),
                          worst_field_point_transmission_pct=round(100 * worst, 1)))
    # Decision N3 (YAML cameras.field_required_deg.up_guaranteed): the guaranteed upper field is DEFINED as the worst case with the
    # optics print_tol high AND the fore-aft play of the spigot fit against it.  The comparison is strict (no recorded shortfall)
    # and is made on the SMALLER of the two cameras
    cf_play = O.upper_field_closed_form(tp, dy)
    guar_margin = float("-inf") if up_play is None else up_play - P.FOV_UP_GUAR
    for side_, v_ in sorted(up_side.items()):
        if not v_ - P.FOV_UP_GUAR >= 0.0:
            fails.append(f"upper field of camera {side_} in the guaranteed case (optics {tp} high and {dy:.3f} of spigot play against it) is {v_:.2f} deg, BELOW the {P.FOV_UP_GUAR} deg the YAML guarantees")
    if not up_side:
        fails.append("the guaranteed case was not traced")
    # What uses up the margin of the guaranteed case (closed form; information).  The YAML defines the case with the NOMINAL spigot fit
    # and the model assumes the lens pupil: each row below changes ONE of these and shows what is left
    fit_hi = P.SPIGOT_FIT + M["pcb_hole_tol"] / 2
    dy_hi = P.spigot_play(fit_hi)["fore_aft"]
    fit_max = P.SPIGOT_FIT + M["pcb_hole_tol"] / 2 + M["spigot_undersize"] / 2      # hole at its upper limit and spigot at the no-go size proposed in N18
    dy_max = P.spigot_play(fit_max)["fore_aft"]
    per_mm_z = (O.upper_field_closed_form(tp, dy) - O.upper_field_closed_form(tp + 0.01, dy)) / 0.01
    per_mm_y = (O.upper_field_closed_form(tp, dy) - O.upper_field_closed_form(tp, dy + 0.01)) / 0.01
    mrow, m_worst = [], []
    for what, kw, basis in (
            (f"the case the YAML defines: fit {P.SPIGOT_FIT:.3f} (hole dia {P.LOC_ROUND[2]}, spigot dia {P.SPIGOT_D}), pupil dia {M['pupil_dia']}, {M['pupil_below_cube_top']} below the cube top", dict(dy_away=dy), "N3"),
            (f"PCB hole at its upper limit, dia {P.LOC_ROUND[2] + M['pcb_hole_tol']:.2f} (ordinary NPTH tolerance +{M['pcb_hole_tol']}, assumed): fit {fit_hi:.3f}; a spigot {M['pcb_hole_tol']} undersize does the same",
             dict(dy_away=dy_hi), "the hole tolerance is not in the YAML"),
            (f"pupil dia {M['pupil_dia_alt']} instead of the assumed {M['pupil_dia']}", dict(dy_away=dy, pupil_dia=M["pupil_dia_alt"]), "lens data not published"),
            (f"pupil {M['pupil_below_alt']} instead of {M['pupil_below_cube_top']} below the cube top", dict(dy_away=dy, pupil_below=M["pupil_below_alt"]), "lens data not published"),
            (f"roof {M['roof_cold_drop']} lower over the opening (-10 C; not part of the YAML case)", dict(dy_away=dy, dz_extra=M["roof_cold_drop"]), "thermal estimate of the README"),
            (f"hole at its upper limit AND the roof {M['roof_cold_drop']} lower", dict(dy_away=dy_hi, dz_extra=M["roof_cold_drop"]), "both mechanical items together"),
            (f"largest fit {fit_max:.3f}: hole dia {P.LOC_ROUND[2] + M['pcb_hole_tol']:.2f} and a spigot of dia {P.SPIGOT_D - M['spigot_undersize']:.2f} (no spigot gauge for the LOWER size exists yet)",
             dict(dy_away=dy_max), "proposal N18: a no-go gauge for the spigots"),
            (f"largest fit {fit_max:.3f} AND the roof {M['roof_cold_drop']} lower (-10 C): the case proposal N18 would define the guarantee on", dict(dy_away=dy_max, dz_extra=M["roof_cold_drop"]),
             f"proposal N18: up_guaranteed {M['up_guaranteed_proposed']}")):
        dz_ = tp + kw.pop("dz_extra", 0.0)
        a_ = O.upper_field_closed_form(dz_, **kw)
        mrow.append(dict(what=what, upper_field_deg_closed_form=round(a_, 3), margin_to_the_guaranteed_deg=round(a_ - P.FOV_UP_GUAR, 3), basis=basis,
                         status=("the comparison of this check (ray trace: %.2f / %.2f deg, camera L / R)" % (up_side.get("L", float("nan")), up_side.get("R", float("nan"))) if basis == "N3" else
                                 (("information: inside" if a_ >= P.FOV_UP_GUAR else "information: BELOW the guaranteed figure") +
                                  (f"; {a_ - M['up_guaranteed_proposed']:+.3f} against the proposed {M['up_guaranteed_proposed']}" if "N18" in basis else "")))))
        if basis != "N3":
            m_worst.append((a_, what))
    mrow.append(dict(what="what the margin of the defined case is worth", upper_field_deg_closed_form=round(cf_play, 3), margin_to_the_guaranteed_deg=round(cf_play - P.FOV_UP_GUAR, 3),
                     basis=f"{per_mm_z:.1f} deg per mm of roof or optics height, {per_mm_y:.2f} deg per mm of fore-aft play",
                     status=f"= {(cf_play - P.FOV_UP_GUAR) / per_mm_z:.4f} mm of height = {(cf_play - P.FOV_UP_GUAR) / per_mm_y:.3f} mm of extra fore-aft play"))
    below = [w for a_, w in m_worst if a_ < P.FOV_UP_GUAR]
    if below:
        warns.append(f"the {guar_margin:+.2f} deg margin of the guaranteed case holds for the NOMINAL spigot fit and the ASSUMED pupil only. Closed form (required {P.FOV_UP_GUAR}): PCB hole dia +{M['pcb_hole_tol']} -> "
                     f"{mrow[1]['upper_field_deg_closed_form']:.3f} deg; pupil dia {M['pupil_dia_alt']} -> {mrow[2]['upper_field_deg_closed_form']:.3f}; pupil {M['pupil_below_alt']} below the cube top -> "
                     f"{mrow[3]['upper_field_deg_closed_form']:.3f}; roof {M['roof_cold_drop']} lower (-10 C) -> {mrow[4]['upper_field_deg_closed_form']:.3f}: {len(below)} of {len(m_worst)} rows are below the guaranteed "
                     "figure. The YAML defines the guarantee on the nominal fit, so this is not a failure of the check: proposal N18 (PROPOSED_PARAM_CHANGES.md part C)")
    # test gate 2 of the assembly sequence (wet adhesive): a target bar inside the guaranteed field must be fully clear on every
    # in-tolerance unit; a bar at +17 deg (the former gate) is not
    g2 = P.FOV_UP_GUAR - M["gate2_margin_deg"]
    grow = []
    for ulabel, sh in (("nominal unit", (0, 0, 0)), ("guaranteed case (optics high, play against it)", (0, -dy, tp))):
        for ang, what in ((g2, f"gate 2 target: guaranteed {P.FOV_UP_GUAR} - {M['gate2_margin_deg']} margin"), (-g2, "gate 2 reference bar (mirrored)"), (P.FOV_UP_GUAR, "guaranteed upper field"),
                          (17.0, "former gate 2 target (+17 deg)"), (P.FOV_UP, "required nominal field edge")):
            trs = {sd_: O.bundle(sd_, 0.0, math.tan(math.radians(ang)), rc, shift=sh, n_rim=48, n_rings=8)["total_fraction"] for sd_ in ("L", "R")}
            tr_ = min(trs.values())
            grow.append(dict(unit=ulabel, elevation_deg=round(ang, 2), what=what, pupil_transmission_pct_camera_L=round(100 * trs["L"], 1), pupil_transmission_pct_camera_R=round(100 * trs["R"], 1),
                             pupil_transmission_pct=round(100 * tr_, 1),
                             height_of_the_bar_above_the_optical_axis_at_the_gate_distance_mm=round(M["gate2_distance"] * math.tan(math.radians(ang)), 1)))
            for sd_, t_ in trs.items():
                if ulabel.startswith("guaranteed") and abs(abs(ang) - g2) < 1e-9 and t_ < 1.0 - 1e-9:
                    fails.append(f"test gate 2: a bar at {ang:+.1f} deg is only {100 * t_:.1f} % clear in camera {sd_} on a unit at the tolerance limit")
    prow_ = [dict(quantity="radial fit of each spigot (dia %.2f in dia %.2f / in the %.2f x %.2f slot)" % (P.SPIGOT_D, P.LOC_ROUND[2], P.LOC_SLOT[2], P.LOC_SLOT[3]),
                  value=round(pl["fit"], 3), unit="mm", basis="YAML pcb.locating_holes"),
             dict(quantity="spigot spacing", value=P.SPIGOT_SPAN, unit="mm", basis=f"posts B at x = +-{abs(P.LOC_ROUND[0])}, y = {P.LOC_ROUND[1]}; cameras at x = +-{P.CAM_X}, y = {P.CAM_XY['R'][1]}"),
             dict(quantity="yaw of the PCB when the two spigots use their fit in opposite directions", value=round(yaw_deg, 3), unit="deg", basis="2 x fit / spacing (a stereo-calibration item)"),
             dict(quantity="fore-aft play at a camera", value=round(dy, 3), unit="mm", basis="the cameras lie between the spigots: never more than the fit itself"),
             dict(quantity="sideways play at a camera", value=round(dx, 3), unit="mm", basis=f"fit of the round hole plus yaw x {abs(P.CAM_XY['R'][1] - P.LOC_ROUND[1]):.1f} mm (camera y - spigot y)"),
             dict(quantity="for comparison, rev C (spigots under posts E, 8.4 mm apart)", value=(0.094, 0.179, 1.02), unit="mm sideways / mm fore-aft / deg yaw", basis="rev C check report"),
             dict(quantity="upper field, full pupil: nominal / with the fore-aft play / at the tolerance limit", value=tuple(r["upper_field_full_pupil_deg"] for r in (srows[0], srows[4], srows[7])),
                  unit="deg", basis=f"required {P.FOV_UP} nominal (YAML)"),
             dict(quantity="upper field at the tolerance limit, closed form (rim ray of the pupil through the top edge of the opening)", value=round(O.upper_field_closed_form(tp), 3),
                  unit="deg", basis="a tan(t) + (prism leg) tan(t') = margin, sin(t) = n sin(t'); cross-check of the ray trace"),
             dict(quantity="GUARANTEED CASE: upper field with the optics high AND the fore-aft play (spigot fit) against it, the smaller of the two cameras", value=srows[8]["upper_field_full_pupil_deg"], unit="deg",
                  basis=f"YAML up_guaranteed = {P.FOV_UP_GUAR} is defined on this case (N3): camera L {up_side.get('L', float('nan')):.2f}, camera R {up_side.get('R', float('nan')):.2f}; margin {guar_margin:+.2f} deg; "
                        f"closed form {cf_play:.3f} deg"),
             dict(quantity="roof lower by 0.01 mm over the opening: loss of upper field (sensitivity)", value=round((srows[0]["upper_field_full_pupil_deg"] - srows[7]["upper_field_full_pupil_deg"]) / (tp / 0.01), 3),
                  unit="deg per 0.01 mm", basis=f"the margin of {guar_margin:.2f} deg is {guar_margin / max(1e-9, (srows[0]['upper_field_full_pupil_deg'] - srows[7]['upper_field_full_pupil_deg']) / tp):.3f} mm of roof or optics height")]
    nom = [r for r in rows if r["camera"] == "R"]
    worst_nom = min(r["pupil_through_visor_pct"] for r in nom)
    m_open_min = min(r["margin_visor_opening_mm"] for r in rows)
    if m_edge[2] < 0.2:
        warns.append(f"the upper field edge (+{M['fov_up_deg']} deg) clears the top of the opening (the roof underside, z {P.OPEN_Z1}) by only {m_edge[2]:.3f} mm: "
                     f"optics {tp} mm high clip the upper field to {up_limit:.2f} deg, {up_play:.2f} deg with the spigot play against it (accepted: {P.FOV_UP_GUAR} deg guaranteed, YAML N3)")
    if m_edge[0] < 0.2 or m_edge[1] < 0.2:
        warns.append(f"bundle margin to the opening sides {m_edge[0]:.3f} mm / sill {m_edge[1]:.3f} mm is below the 0.2 mm print tolerance")
    notes = [f"entrance pupil ASSUMED: dia {M['pupil_dia']} mm, {M['pupil_below_cube_top']} mm below the cube top (z = {P.PUPIL_Z:.2f}); prism n = {O.N_GLASS}, "
             f"legs {P.PRISM_LEG}, bond gap {P.PRISM_BOND}; hypotenuse aluminised (reflects at any angle)",
             "margins are the smallest distance of any ray of the pupil bundle to the edge of that aperture (negative = clipped); "
             "the visor margin is taken on the aperture plane (window-recess floor)",
             "field points are rectilinear: direction (tan h, 1, tan v)",
             f"paraxial check: virtual pupil {P.VIRTUAL_PUPIL_BEHIND_EXIT:.3f} mm behind the exit face (y = {P.VIRTUAL_PUPIL_Y:.3f}), z = {P.AXIS_Z:.2f}",
             "sensitivity cases move the camera and prism together relative to the printed tub. The four-direction columns are those of camera R; the UPPER FIELD is traced on both cameras in "
             "every case (camera L with the mirrored sideways shift) and the smaller value is compared, so a one-sided change of the tub over either opening is caught",
             f"PCB location (rev D): spigots dia {P.SPIGOT_D} under posts B in a dia {P.LOC_ROUND[2]} hole and a {P.LOC_SLOT[2]} x {P.LOC_SLOT[3]} slot, {P.SPIGOT_SPAN} mm apart: "
             f"+-{pl['fit']:.3f} mm at each spigot gives +-{dx:.3f} mm sideways and +-{dy:.3f} mm fore-aft at a camera and +-{yaw_deg:.2f} deg of yaw (a stereo-calibration "
             "item, not a vignetting item)",
             f"smallest margin of the full pupil bundle to the opening over the required field: sides {m_edge[0]:.3f}, sill {m_edge[1]:.3f}, top {m_edge[2]:.3f} mm",
             f"required field (YAML): +-{P.FOV_H} deg horizontal, +{P.FOV_UP} / -{P.FOV_DOWN} deg vertical; upper field guaranteed at the tolerance limit: {P.FOV_UP_GUAR} deg",
             f"limit angles: bisection to {M['fov_angle_tol']} deg; the pupil samples include the four extreme rim points, so the full-pupil limits are those of the whole "
             f"{M['pupil_dia']} mm disc. The comparison with the guaranteed {P.FOV_UP_GUAR} deg is strict and is made on the case the YAML defines (optics {tp} high and the spigot play "
             f"against it), for each camera: L {up_side.get('L', float('nan')):.2f}, R {up_side.get('R', float('nan')):.2f} deg, closed form {cf_play:.3f} deg",
             f"the margin of {guar_margin:+.2f} deg belongs to the case as the YAML defines it (nominal fit {P.SPIGOT_FIT:.3f}) and to the assumed pupil; the table 'What uses up the margin' shows the "
             f"figure with the hole at its upper limit, with other pupil numbers and with the roof {M['roof_cold_drop']} mm lower at -10 C",
             f"test gate 2 (assembly step 16): target bar at +{g2:.1f} deg = guaranteed {P.FOV_UP_GUAR} - {M['gate2_margin_deg']} deg (placement of target and unit in the join fixture), reference bar at "
             f"-{g2:.1f} deg; both are fully clear on every in-tolerance unit, so the upper bar may not be darker than the lower one (threshold to be set on first units). A bar at +17 deg is "
             "vignetted on in-tolerance units and cannot be a pass / fail limit"]
    return res(4, "fold geometry", not fails,
               (f"chief rays of all nine field points pass the prism and the visor opening on both cameras; pupil transmission at the worst "
                f"nominal field point {worst_nom:.1f} % (prism exit face); bundle margin to the opening: sides {m_edge[0]:.3f}, sill {m_edge[1]:.3f}, "
                f"top {m_edge[2]:.3f} mm; upper field {srows[0]['upper_field_full_pupil_deg']:.2f} deg nominal, {up_limit:.2f} deg with the optics {tp} high, "
                f"{up_play:.2f} deg in the guaranteed case (optics high and spigot play against it; camera L {up_side.get('L', float('nan')):.2f}, camera R {up_side.get('R', float('nan')):.2f}): "
                f"YAML guarantees {P.FOV_UP_GUAR}, margin {guar_margin:+.2f} deg at the nominal fit ({mrow[1]['margin_to_the_guaranteed_deg']:+.3f} with the PCB hole {M['pcb_hole_tol']} oversize); "
                f"gate 2 target +{g2:.1f} deg fully clear on a unit at the limit"
                if not fails else "FAILED: " + "; ".join(fails)),
               [dict(title="Chief rays and pupil-bundle margins (nominal geometry)", rows=rows),
                dict(title="Camera position from the spigot fit (rev D: spigots under posts B)", rows=prow_),
                dict(title="Sensitivity to misplacement of the optics relative to the tub (four directions: camera R; upper field: both cameras)", rows=srows),
                dict(title="What uses up the margin of the guaranteed upper field (closed form; one change per row)", rows=mrow),
                dict(title="Test gate 2 target and the former +17 deg target: pupil transmission on the axis of each camera", rows=grow)], notes, warns)


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
            f.append((f"tip of the PCB locating spigot at x = {sx_} under post B (dia {P.SPIGOT_D} pin with a {c} mm lead-in chamfer: a pin, not a wall)", "D19", P.SPIGOT_D - 2 * c,
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


WALL_SPACING = dict(tub=0.10, base_plate=0.08, cradle=0.20, baffle_ring=0.04)
WALL_PARTS = ("tub", "cradle", "baffle_ring")       # the printed parts of the primary build (the FR-4 plate is checked in check 15)
WALL_MESH_TOL = 0.045         # worst-case effect of the 0.02 mm STL chord error on a thickness reading
WALL_OPPOSING_DOT = -0.4      # the face the ray leaves through must lie within 66 deg of parallel to the start face


def _wall_audit(parts, names):
    """Ray-cast wall audit of the named printed parts.  Returns (rows_all, thin5, fails, notes, summary_bits)."""
    rows_all, thin5, fails, notes = [], [], [], []
    summary_bits = []
    for name in names:
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
            return dict(part=parts[name].name, feature=feats[k][0] if doc else "UNDOCUMENTED thin region", deviation=feats[k][1] if doc else "",
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
        summary_bits.append(f"{parts[name].name} minimum {tmin:.3f} mm")
        notes.append(f"{parts[name].name}: {len(tris)} triangles ({src}), {len(pts)} surface samples at {sp} mm spacing, {len(cand)} candidates re-measured "
                     f"exactly on the B-rep, {len(thin)} of them below {P.MIN_WALL} mm; thinnest reading {tmin:.3f} mm; {n_oblique} samples leave "
                     "through an oblique face within 0.5 mm (grazing exits at wall ends and sharp edges - not wall thickness, not counted)")
    return rows_all, thin5, fails, notes, summary_bits


def check_walls(parts):
    rows_all, thin5, fails, notes, summary_bits = _wall_audit(parts, WALL_PARTS)
    warns = []
    for r in thin5:
        warns.append(f"{r['part']}: {r['feature']} - min {r['min_mm']} mm, {r['area_below_0p5_mm2']} mm2 below 0.5 mm ({r['deviation'] or 'documented'})")
    n_doc = sum(r["status"] == "documented" for r in rows_all)
    notes += ["method: from every surface sample a ray is cast along the inward normal and the distance to the first face it meets is the local "
              "thickness (mesh first, then the same ray on the exact solid for every candidate). A reading counts when the face the ray leaves "
              "through is within 66 deg of parallel to the start face (wedges up to 66 deg are walls; grazing exits are not)",
              f"a region is listed when it is thinner than the {P.MIN_WALL} mm rule; regions with any area below 0.5 mm are repeated in the second table",
              "edge chamfers and bevels read thin at their feet by this method; they are listed, not hidden",
              "the 0.7 mm wide bottom land of the side wall is an edge feature of a wall that is 1.0 mm thick above it; the latch beam "
              f"(root {P.LATCH_H0} mm >= 1.0, neck {P.LATCH_HN} mm) and every wall of the cradle are above the rule",
              f"baffle ring (GL1-013): wall {P.BAFFLE_WALL} radial, {P.BAFFLE_RING_H:.2f} high. The routed FR-4 base plate is not a printed part: its thickness, webs "
              "and radii are checked in check 15; the printed PA12 alternative plate is audited in check 16"]
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


VOXEL_PITCH = dict(tub=0.10, cradle=0.20, baffle_ring=0.041)
ESCAPE_DIA = 2.0


def _voxel_pitch(name):
    return P.BASE_T / 10 if name == "base_plate" else VOXEL_PITCH[name]     # base plate: an exact tenth of its thickness


def _powder_audit(parts, names):
    """Voxel analysis of the named printed parts.  Returns (rows, nrows, fails, notes)."""
    from scipy import ndimage as ndi
    rows, nrows, fails, notes = [], [], [], []
    for name in names:
        tris, src = _tris(parts, name)
        h = _voxel_pitch(name)
        pname = parts[name].name
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
                nrows.append(dict(part=pname, feature=_narrow_feature(name, bmin, bmax), depth_beyond_2mm_ball_mm=round(float(maxd[k]), 2),
                                  local_width_mm=round(2 * float(maxw[k]), 2), volume_beyond_0p8_mm3=round(float(sizes[k]) * h ** 3, 2),
                                  bbox_min=tuple(float(v) for v in np.round(bmin, 1)), bbox_max=tuple(float(v) for v in np.round(bmax, 1))))
        shells = len(A.solid_of(parts[name]).Shells())
        bad = bool(closed) or bool(stuck) or shells != 1
        if closed:
            fails.append(f"{pname}: {len(closed)} closed void(s), {sum(v for _, v in closed):.2f} mm3")
        for s in stuck:
            fails.append(f"{pname}: cavity near {np.round(s[1], 1)}..{np.round(s[2], 1)} has no {ESCAPE_DIA} mm escape path")
        if shells != 1:
            fails.append(f"{pname}: B-rep has {shells} shells (an inner shell is a closed void)")
        if abs(vol_vox - vol_mesh) / vol_mesh > 0.03 or odd > 20:
            fails.append(f"{pname}: voxel model unreliable (volume {vol_vox:.1f} vs {vol_mesh:.1f}, {odd} odd columns)")
        rows.append(dict(part=pname, voxel_mm=round(h, 3), grid=tuple(int(v) for v in solid.shape), voxel_volume_mm3=round(vol_vox, 1), mesh_volume_mm3=round(vol_mesh, 1),
                         brep_shells=shells, closed_voids=len(closed), cavities_without_2mm_exit=len(stuck), narrow_recesses_listed=n_deep,
                         status="FAIL" if bad else "ok"))
        notes.append(f"{pname}: {src}")
    return rows, nrows, fails, notes


def check_trapped(parts):
    rows, nrows, fails, notes = _powder_audit(parts, WALL_PARTS)
    warns = []
    notes += [f"closed void = empty region with no connection to the outside; cavity without exit = a place where a {ESCAPE_DIA} mm ball fits "
              "but from which it cannot roll out of the part (Euclidean distance transform of the empty space, connected components)",
              "narrow recesses = empty space more than 0.8 mm beyond the reach of a 2 mm ball (deeper than the 0.41 / 0.73 mm a ball leaves in "
              "any square edge / corner); they are open, not trapped, but need directed bead blasting or a pick at the bureau",
              "accuracy about one voxel; the part is analysed bare (as printed), not assembled",
              "the routed FR-4 base plate is not printed (check 15); the printed PA12 alternative plate is analysed in check 16"]
    for r in nrows:
        if r["depth_beyond_2mm_ball_mm"] > 2.0:
            warns.append(f"{r['part']}: narrow recess {r['feature']} is {r['depth_beyond_2mm_ball_mm']} mm deep at {r['local_width_mm']} mm width - depowdering access to confirm with the bureau")
    return res(6, "trapped volume", not fails,
               ("no closed void and no cavity without a 2 mm escape path in tub, cradle or baffle ring; "
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
        xa_, xb_ = M["lcd_rear_ribs_x"]
        if xa_ - 1.0 < abs(c[0]) < xb_ + 1.0 and c[1] < P.LCD_POCKET_Y0 and c[2] > P.LCD_REAR_RIB_Z0 - 0.5:
            return "corner between a rear glass rib and the side wall, under the thick roof"
        if abs(abs(c[0]) - P.LCD_POCKET_X) < 1.0 and c[2] > P.BOND_Z:
            return "corner between the thick-roof (LCD pocket) step and the side wall"
        return "internal corner"
    if name == "baffle_ring":
        return "bore of the ring"
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
    """Dock (rev D: every number of the YAML cradle block): seven pin positions on the pads, one orientation, lip + latch hold-down proven with numbers (retention
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
             value=(M["cradle_float"], N2(P.PIN_FLOAT_H), N2(P.PIN_COMPRESSION - M["cradle_float"])), unit="mm", basis=f"working height {P.PIN_WORK_H} with the marker on its feet, full stroke {M['pin_full_stroke']} (YAML cradle.float)"),
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

    warns.append(f"with pins fitted the marker floats up to {M['cradle_float']} mm against lip and hook (YAML cradle.float); the pins then stand {P.PIN_FLOAT_H:.2f} mm high")
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
             f"the COPPER FACE of the pads (YAML cradle.pad_plane_z = {P.CRADLE_PAD_Z}; the board underside is z {P.PCB_Z0})",
             "rev D: body position, seat level, pad plane, pin heights, cradle PCB, lip and latch dimensions are read from the YAML cradle block; the model "
             f"reproduces its derived values (overall height {P.LATCH_TOP_Z - P.CRADLE_BOT_Z:.2f}, PCB top {P.CPCB_Z1:.3f}, hook overlap {P.HOOK_OVERLAP:.2f}), asserted in cad/params.py",
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
        if info.group in A.EXTRA_GROUPS:                      # alternative base-plate parts (check 16), the optional film, the fixtures
            continue
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
        rows.append(dict(part=info.name, group=info.group, material=info.material, volume_mm3=round(v, 2), density_g_cm3=dens, mass_g=round(m, 4),
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
    notes = ["densities are typical handbook values, not measured (PROVISIONAL): PA12 MJF 1.01, glass 2.5, N-BK7 and borosilicate 2.51, FR-4 1.85, stainless 7.9, "
             "epoxy 1.15, LiPo cell 2.1, camera module 2.5, adhesive tapes 1.0, PU foam 0.32; purchased parts are envelope solids, so their mass is an estimate",
             f"base plate: {P.BASE['label']}, {P.BASE_T} mm; the two battery-lead solids are envelopes up to the joint height (their real mass is far smaller)",
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
    mid = 0.5 * (tris + np.roll(tris, 1, axis=1)).reshape(-1, 3)
    if name == "cradle":                                   # print frame: x' = -z, y' = y, z' = x - xmin
        R = P.NEST_R
        z_model = -mid[:, 0]; x_model = mid[:, 2] - P.CRADLE_X
        r = np.hypot(x_model, mid[:, 1])
        on = (np.abs(r - R) < 0.05) & (z_model > 0.3) & (z_model < P.CRADLE_TOP_Z - 1.0) & (mid[:, 1] > -19.0) & (mid[:, 1] < P.STRIP_Y0)
        return float(R - r[on].min()) if on.any() else None
    if name == "baffle_ring":                              # the print file is the sprued set: measure on the ring nearest to each facet
        R = P.BAFFLE_RO
        sp = M["ring_sprue"]
        per_row = (sp["n"] + 1) // 2
        cx = sp["runner"] / 2 + sp["gate_len"] + R
        cen = np.array([(sx * cx, (j_ - (per_row - 1) / 2) * sp["pitch"]) for sx in (1, -1) for j_ in range(per_row)][:sp["n"]])
        r = np.min(np.hypot(mid[:, None, 0] - cen[None, :, 0], mid[:, None, 1] - cen[None, :, 1]), axis=1)
        on = (np.abs(r - R) < 0.05) & (mid[:, 2] > P.MIN_WALL + 0.02) & (mid[:, 2] < P.BAFFLE_RING_PRINT_H - 0.02)
        return float(R - r[on].min()) if on.any() else None
    alt_t = P.BASE_VARIANTS[P.BASE_ALT]["thickness"]
    R = P.R_OUT if name == "tub" else P.BASE_R
    r = np.hypot(mid[:, 0], mid[:, 1])
    zmid = (P.T - mid[:, 2]) if name == "tub" else mid[:, 2]
    lo, hi = (P.RIM_Z + M["bottom_chamfer"] + 0.2, P.T - M["top_fillet"] - 0.2) if name == "tub" else (0.1, alt_t - 0.1)
    on = (np.abs(r - R) < 0.05) & (zmid > lo) & (zmid < hi)
    return float(R - r[on].min()) if on.any() else None


def check_quoting(parts):
    rows, fails, notes = [], [], []
    for name in A.PRINTED:
        info = parts[name]
        pshape = A.print_shape(name, info.shape)                       # the print file: the part, or the sprued ring set
        s = pshape.val()
        tris, src = _tris(parts, name, print_orientation=True)
        bb = A.bbox_of(pshape)                                         # exact box of the solid in print orientation
        size = np.array(bb[3:]) - np.array(bb[:3])
        vol, area = G.mesh_volume_area(tris)
        closed = G.mesh_is_closed(tris)
        dv = abs(vol - s.Volume()) / s.Volume()
        ok = closed and dv < 0.005
        if not ok:
            fails.append(f"{name}: STL closed={closed}, volume differs {100 * dv:.2f} %")
        zmin = float(tris[:, :, 2].min())
        sag = _facet_sag(name.replace(A.ALT_SUFFIX, ""), tris)
        if abs(zmin) > 1e-4:
            ok = False; fails.append(f"{name}: print file does not rest on z = 0 (z min {zmin:.4f})")
        if sag is not None and sag > A.PRINT_STL_TOL + 1e-3:
            ok = False; fails.append(f"{name}: facet sag {sag:.4f} mm exceeds the stated STL tolerance {A.PRINT_STL_TOL}")
        what = name if name != "baffle_ring" else f"baffle_ring: sprued set of {M['ring_sprue']['n']} rings, each {P.BAFFLE_RING_PRINT_H:.2f} high for lapping"
        rows.append(dict(part=what, used_in=("alternative build only" if info.group == "alt" else "primary build"), process=info.material, print_file=src,
                         box_x_mm=R3(size[0]), box_y_mm=R3(size[1]), box_z_build_mm=R3(size[2]),
                         volume_cm3=round(s.Volume() / 1000, 4), stl_volume_cm3=round(vol / 1000, 4), surface_area_cm2=round(s.Area() / 100, 2),
                         mass_g=round(s.Volume() * info.density / 1000, 3), stl_triangles=len(tris), stl_watertight=closed,
                         stl_z_min_mm=round(zmin, 5), largest_facet_sag_on_the_main_radius_mm=(round(sag, 4) if sag is not None else "-"),
                         box_volume_cm3=round(float(np.prod(size)) / 1000, 3)))
    # the fabricated (not printed) base plate of the primary build: data for the PCB fabricator's quote
    frows = []
    bp = parts["base_plate"]
    sb = A.solid_of(bp); bb = A.bbox_of(bp)
    frows.append(dict(part="base_plate", drawing="GL1-011", material=bp.material, box_x_mm=R3(bb[3] - bb[0]), box_y_mm=R3(bb[4] - bb[1]), thickness_mm=R3(bb[5] - bb[2]),
                      area_cm2=round(sb.Volume() / (bb[5] - bb[2]) / 100, 3), volume_cm3=round(sb.Volume() / 1000, 4), mass_g=round(sb.Volume() * bp.density / 1000, 3),
                      files="drawings/GL1-011_base_plate_FR4.pdf, drawings/dxf/GL1-011_base_plate_FR4_fab.dxf, export/step/base_plate.step"))
    # export integrity: re-read every exported STEP and STL and compare with the solid that was checked
    irows = []
    if USE_EXPORTED:
        for name, info in parts.items():
            s = A.solid_of(info)
            step = A.STEP_DIR / f"{name}.step"
            stl = A.STL_PARTS_DIR / f"{name}.stl"
            try:
                rv = sum(x.Volume() for x in cq.importers.importStep(str(step)).vals())
                tv, _ = G.mesh_volume_area(G.load_stl(stl))
                closed = G.mesh_is_closed(G.load_stl(stl))
            except Exception as e:
                fails.append(f"{name}: export unreadable ({e})"); continue
            ok = abs(rv - s.Volume()) < 1e-3 * max(1.0, s.Volume()) and abs(tv - s.Volume()) < 0.02 * s.Volume() + 0.01 and closed
            if not ok:
                fails.append(f"{name}: STEP {rv:.3f} / STL {tv:.3f} vs solid {s.Volume():.3f} mm3, closed={closed}")
            irows.append(dict(part=name, build=A.GROUP_LABEL.get(info.group, info.group), solid_volume_mm3=round(s.Volume(), 3),
                              step_reimport_volume_mm3=round(rv, 3), stl_volume_mm3=round(tv, 3), stl_watertight=closed, status="ok" if ok else "FAIL"))
        n_main = sum(1 for i in parts.values() if i.group not in A.EXTRA_GROUPS)
        for fname, n_exp in (("GL1_assembly.step", n_main), ("GL1_marker_only.step", None), (f"GL1_marker_only{A.ALT_SUFFIX}_base.step", None)):
            asm = A.STEP_DIR / fname
            notes.append(f"{fname}: {asm.stat().st_size / 1e6:.2f} MB" + (f", {n_exp} named parts" if n_exp else "") if asm.exists() else f"{fname} MISSING")
            if not asm.exists():
                fails.append(f"{fname} missing")
    else:
        notes.append("export integrity not run (no export in this run)")
    notes += [f"print files: STL tolerance {A.PRINT_STL_TOL} mm linear, {A.PRINT_STL_ANG} rad angular, resting on z = 0; the same parts are exported as "
              "STEP in print orientation (export/step/*_print.step) - send the STEP when the bureau accepts it",
              f"part meshes for renders and mesh checks: {A.STL_TOL} mm linear, {A.STL_ANG} rad angular",
              f"the baffle ring is printed as a sprued set of {M['ring_sprue']['n']} rings on a {M['ring_sprue']['runner']} mm runner (gates {M['ring_sprue']['gate_w']} wide on the outside of each ring), "
              f"each ring {P.BAFFLE_RING_PRINT_H:.2f} high: {M['baffle_ring_lap_allowance']} mm or more is lapped off by us to the height that suits the plate lot and the tape used "
              f"({P.BAFFLE_RING_H_RANGE[0]:.3f} to {P.BAFFLE_RING_H_RANGE[1]:.2f}; {P.BAFFLE_RING_H:.2f} for the nominal plate and a {P.BAFFLE_PSA_T} tape)",
              "print orientation (z = build direction): tub roof-down; baffle-ring set and PA12 base plate flat; cradle with its x axis as the build direction, so that "
              "the side profile of the latch beam and of the lip lies in the build plane (orientation of the cradle is to be LOCKED with the bureau)",
              f"facet sag = main radius minus the smallest mid-edge radius of the facets on the cylindrical wall (tub R {P.R_OUT}, cradle nest R {P.NEST_R}, "
              f"baffle ring R {P.BAFFLE_RO}, PA12 base plate R {P.BASE_R})",
              "box = exact axis-aligned bounding box of the solid in print orientation",
              "rev D: the base plate of the primary build is routed FR-4 from the PCB fabricator (no print file); the PA12 plate is printed only for the "
              "alternative build and the EVT comparison"]
    return res(9, "printed and fabricated parts for quoting / export integrity", not fails,
               ("; ".join(f"{r['part']} {r['box_x_mm']} x {r['box_y_mm']} x {r['box_z_build_mm']} mm, {r['volume_cm3']} cm3" for r in rows)
                + f"; FR-4 base plate {frows[0]['box_x_mm']} x {frows[0]['box_y_mm']} x {frows[0]['thickness_mm']} mm, {frows[0]['area_cm2']} cm2"
                + (f"; all {len(irows)} STEP and STL files re-read and match the checked solids" if irows else "")
                if not fails else "FAILED: " + "; ".join(fails)),
               [dict(title="Printed parts (print orientation)", rows=rows), dict(title="Fabricated part (PCB fabricator)", rows=frows),
                dict(title="Export integrity (files re-read)", rows=irows)], notes)


# ==============================================================================================
# 10. support posts, 11. layout script, 12. tub keep-out contract
# ==============================================================================================
def _pcb_outline():
    return Point(0, 0).buffer(P.PCB_R, 256).intersection(sbox(-99, -99, 99, P.PCB_FLAT))


def check_posts(parts):
    """Each support post foot must land on the PCB top, clear every top-side part and the LCD glass by the fit clearance;
    the two posts B carry the spigots that locate the PCB (rev D).  Ball-foot zones: no post foot and no soldered top-side
    part other than the battery may lie over a foot (the ball bears on the PCB there)."""
    S = _solids(parts)
    pcb = _pcb_outline()
    lcd = sbox(P.LCD_X0, P.LCD_Y0, P.LCD_X1, P.LCD_Y1)
    board_top = G.section_polys(PT.pcb_board().val(), "z", P.PCB_Z1 - 0.005, 2e-5)   # with the two locating holes (arcs sampled to 0.00002 mm)
    feet = G.section_polys(S["tub"], "z", P.PCB_Z1 + 0.005)
    spig = G.section_polys(S["tub"], "z", 0.5 * (P.SPIGOT_Z0 + P.PCB_Z1))
    squares = {n: sbox(x0, y0, x1, y1) for n, x0, x1, y0, y1 in P.ko_post_squares()}
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
        built = feet.intersection(squares[name].buffer(0.5)).area               # what the tub really has at this post
        has_spigot = name[0] == M["locating_posts"]
        sp_area = spig.intersection(foot).area
        sp_ok = (abs(sp_area - math.pi * P.SPIGOT_D ** 2 / 4) < 0.01) if has_spigot else sp_area < 1e-6
        good = (edge >= P.PCB_EDGE_CLR and dmin >= P.CLR - 1e-9 and foot.distance(lcd) >= P.CLR - 1e-9 and solid_frac > 0.999 and seat > 0.5 and sp_ok
                and abs(built - foot.area) < 0.01)
        ok &= good
        rows.append(dict(post=name, x0=R3(x0), x1=R3(x1), y0=R3(y0), y1=R3(y1), foot_mm=f"{x1 - x0:.1f} x {y1 - y0:.1f}",
                         yaml_square_mm=f"{squares[name].bounds[2] - squares[name].bounds[0]:.1f} x {squares[name].bounds[3] - squares[name].bounds[1]:.1f}",
                         to_pcb_edge_mm=R3(edge), nearest_part=near, gap_to_nearest_part_mm=R3(dmin),
                         gap_to_lcd_glass_mm=R3(foot.distance(lcd)), solid_from_pcb_to_roof_pct=round(100 * solid_frac, 1), foot_area_in_the_tub_mm2=round(built, 2),
                         seat_area_on_pcb_mm2=round(seat, 2), locating_spigot=("dia %.1f x %.1f" % (P.SPIGOT_D, P.SPIGOT_H)) if has_spigot else "-", ok=good))
    # ---- ball-foot zones (YAML tub_keepouts.foot_zones)
    zrows = []
    leads = {f"battery lead pad {i + 1}": sbox(*r) for i, r in enumerate(P.battery_pad_rects())}
    for i, (fx, fy) in enumerate(P.FOOT_ZONES):
        zone = Point(fx, fy).buffer(P.FOOT_ZONE_D / 2, 128)
        tub_in = feet.intersection(zone).area                                     # any tub material standing on the PCB inside the zone
        d_post = min(sbox(x0, y0, x1, y1).distance(Point(fx, fy)) - P.FOOT_ZONE_D / 2 for _, x0, x1, y0, y1 in P.post_rects())
        over, d_part, n_part = [], 1e9, None
        for p in P.TOP_PARTS:
            r = sbox(p["x"] - p["dx"] / 2, p["y"] - p["dy"] / 2, p["x"] + p["dx"] / 2, p["y"] + p["dy"] / 2)
            d = r.distance(Point(fx, fy)) - P.FOOT_ZONE_D / 2
            if p["ref"] == "BT1":
                bat_over = d < 0
                continue
            if d < 0:
                over.append(p["ref"])
            if d < d_part:
                d_part, n_part = d, p["ref"]
        for n, r in leads.items():
            d = r.distance(Point(fx, fy)) - P.FOOT_ZONE_D / 2
            if d < 0:
                over.append(n)
            if d < d_part:
                d_part, n_part = d, n
        land_on = board_top.contains(Point(fx, fy).buffer(P.FOOT_ZONE_LAND_D / 2, 64))
        near_ok = d_part >= P.FOOT_PART_MARGIN - 1e-9                              # N7: free parts keep part_margin from a zone
        good = tub_in < 1e-6 and d_post >= -1e-9 and not over and land_on and near_ok
        ok &= good
        zrows.append(dict(foot=i + 1, xy=(fx, fy), zone_dia_mm=P.FOOT_ZONE_D, land_dia_mm=P.FOOT_ZONE_LAND_D, tub_area_inside_the_zone_mm2=round(tub_in, 4),
                          nearest_post_foot_to_the_zone_mm=R3(d_post), soldered_parts_over_the_zone=", ".join(over) or "none",
                          nearest_soldered_part=n_part, its_gap_to_the_zone_mm=R3(d_part), required_gap_mm=P.FOOT_PART_MARGIN, battery_over_the_zone=("yes (allowed)" if bat_over else "no"),
                          land_on_the_board=land_on, status="ok" if good else "FAIL"))
    area = sum(r["seat_area_on_pcb_mm2"] for r in rows)
    loc = [r for r in rows if r["locating_spigot"] != "-"]
    notes = ["post feet are the YAML tub_keepouts.post_feet (the contract with the PCB layout, proven in check 12); passives are not in the YAML",
             f"rev D: the spigots are under posts B at ({P.LOC_SLOT[0]}, {P.LOC_SLOT[1]}) (slot {P.LOC_SLOT[2]} x {P.LOC_SLOT[3]} along x, on the IMU side) and "
             f"({P.LOC_ROUND[0]}, {P.LOC_ROUND[1]}) (round dia {P.LOC_ROUND[2]}, on the flash side), {P.SPIGOT_SPAN} mm apart; posts E are plain {P.KO_POST_SIZE} mm posts",
             f"posts B: the YAML keep-out square is {P.KO_LOC_SIZE} x {P.KO_LOC_SIZE}; the foot as built is {P.LOC_FOOT[0]:.1f} x {P.LOC_FOOT[1]:.1f} with its inner face at /x/ = {P.LCD_POCKET_X} "
             f"(YAML post_feet.locating.foot, N1) because the LCD glass (/x/ <= {P.LCD_X1}) passes between the two posts with the {P.CLR} mm fit clearance; the foot stays inside its square. "
             f"Seat round the round hole {loc[-1]['seat_area_on_pcb_mm2']} mm2; over the slot {loc[0]['seat_area_on_pcb_mm2']} mm2: the {P.LOC_SLOT[3]} mm slot (N9) runs from x = "
             f"{P.LOC_SLOT[0] - P.LOC_SLOT[3] / 2:.2f} to {P.LOC_SLOT[0] + P.LOC_SLOT[3] / 2:.2f} and so crosses the whole foot (x {-P.LCD_POCKET_X - P.LOC_FOOT[0]:.2f} to {-P.LCD_POCKET_X:.2f}): post B- seats on two strips "
             f"{(P.LOC_FOOT[1] - P.LOC_SLOT[2]) / 2:.3f} mm wide, one in front of the slot and one behind it",
             f"intended load path roof -> posts -> PCB -> adhesive sheet -> base plate. Total seat area {area:.1f} mm2: an 800 N "
             f"footstep carried by the posts alone would be {800 / area:.0f} MPa (PA12 yields near 48 MPa). The side wall shares the load only "
             f"through the ledge and the perimeter joint into the edge of the base plate: its rim ends {P.RIM_Z} mm above the base plane. "
             "The design review estimates that a load on the cover glass also passes through the roof ledge into the LCD glass. The footstep "
             "case is NOT analysed or tested (README open issues)",
             f"foot zones: dia {P.FOOT_ZONE_D} on the PCB at each ball foot; on the bottom side no via and no track and an unmasked dia {P.FOOT_ZONE_LAND_D} copper land "
             "(a layout rule: check 17 looks for the keep-out in the board file). The battery lies over the two rear feet by decision; the two battery-lead "
             f"pads (nominal positions) are soldered and are tested like parts. N7: every other soldered part keeps {P.FOOT_PART_MARGIN} mm from a zone (YAML foot_zones.part_margin)"]
    return res(10, "support posts and ball-foot zones", ok,
               (f"{len(rows)} posts on their keep-out squares, solid from PCB to roof, clear of listed parts and of the LCD glass; two spigots under posts B "
                f"({P.SPIGOT_SPAN} mm apart); seat area {area:.1f} mm2 (post B+ {loc[-1]['seat_area_on_pcb_mm2']}, post B- over its {P.LOC_SLOT[3]} mm slot {loc[0]['seat_area_on_pcb_mm2']}); "
                f"no post foot and no soldered part other than the battery over the {len(zrows)} ball-foot zones "
                f"(nearest part {min(r['its_gap_to_the_zone_mm'] for r in zrows)} mm, required {P.FOOT_PART_MARGIN}; nearest post {min(r['nearest_post_foot_to_the_zone_mm'] for r in zrows)} mm from a zone)")
               if ok else "FAILED: " + "; ".join([f"post {r['post']}" for r in rows if not r["ok"]] + [f"foot zone {r['foot']}: over it {r['soldered_parts_over_the_zone']}, nearest part "
                                                                                                    f"{r['nearest_soldered_part']} at {r['its_gap_to_the_zone_mm']} mm (required {P.FOOT_PART_MARGIN}), tub {r['tub_area_inside_the_zone_mm2']} mm2"
                                                                                                    for r in zrows if r["status"] != "ok"]),
               [dict(title="Support posts", rows=rows), dict(title="Ball-foot zones on the PCB (YAML tub_keepouts.foot_zones)", rows=zrows)], notes)


def check_layout_script(parts=None):
    r = subprocess.run([sys.executable, str(P.DESIGN_DIR / "check_layout.py")], capture_output=True, text=True)
    lines = r.stdout.strip().splitlines()
    return res(11, "design/check_layout.py", r.returncode == 0, lines[-1] if lines else "no output",
               [dict(title="Output of design/check_layout.py (plan view and z stack of master_params.yaml)", rows=[dict(line=l) for l in lines])],
               [f"exit code {r.returncode}"] + ([r.stderr.strip()] if r.stderr.strip() else []))


KO_GRID = 0.4


def check_keepouts(parts):
    """Contract with the PCB layout (YAML tub_keepouts): below the free height the tub may touch or hang over the PCB top
    side only inside the eight post-foot squares (six plain, two larger ones for the locating posts B) and the two
    camera-hood zones (there no lower than a 0.95 mm part).  Rev D: the free height is part of the YAML."""
    S = _solids(parts)
    tub = S["tub"]
    fails, warns = [], []
    zt, zf, zh = P.PCB_Z1, P.KO_FREE_Z, P.PCB_Z1 + P.KO_HOOD_MAX_H
    tol = 2e-4
    ko = P.ko_post_squares()                                  # (name, x0, x1, y0, y1): the YAML contract squares
    built = {n: sbox(x0, y0, x1, y1) for n, x0, x1, y0, y1 in P.post_rects()}
    squares = [sbox(x0, y0, x1, y1) for _, x0, x1, y0, y1 in ko]
    zones = {s: sbox(cx - P.KO_HOOD_HW, P.KO_HOOD_Y0, cx + P.KO_HOOD_HW, P.KO_HOOD_Y1) for s, (cx, _) in P.CAM_XY.items()}
    # (a) boolean proof: the space the layout may fill = PCB outline x [PCB top, free height] minus the keep-outs
    space = PT.dprism(P.PCB_R, P.PCB_FLAT, zt, zf)
    for _, x0, x1, y0, y1 in ko:
        space = space.cut(PT.box(x0 - tol, x1 + tol, y0 - tol, y1 + tol, zt - 1, zf + 1))
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
    for (name, x0, x1, y0, y1), sq in zip(ko, squares):
        near = feet.intersection(sq.buffer(1.0)).intersection(pcb)
        inside, outside = near.intersection(sq).area, near.difference(sq.buffer(tol)).area
        expect = built[name].intersection(sq).area              # posts B are built smaller than their square (YAML post_feet.locating.foot, N1)
        okk = abs(inside - expect) < 0.02 and inside > 0.8 * sq.area and outside < 1e-6
        if not okk:
            fails.append(f"post foot {name}: {inside:.2f} mm2 inside its square (expected {expect:.2f}), {outside:.4f} mm2 outside")
        krow.append(dict(keep_out=f"post foot {name}", yaml_centre=(round(0.5 * (x0 + x1), 3), round(0.5 * (y0 + y1), 3)), yaml_size_mm=f"{x1 - x0:.1f} x {y1 - y0:.1f}",
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
    # (b2) N10: the keep-out under the folded LCD flex tail.  The contract is with the layout (parts up to max_part_height inside
    #      the zone); here the modelled tail is proven to lie inside the zone and to clear the tallest part the zone allows
    kt = P.KO_TAIL
    fb = A.bbox_of(parts["lcd_flex"])
    j1 = next(q for q in P.TOP_PARTS if q["ref"] == "J1")
    mouth = j1["y"] - j1["dy"] / 2
    m_x = kt["half_w"] - max(abs(fb[0]), abs(fb[3]))
    m_y0, m_y1 = fb[1] - kt["y"][0], kt["y"][1] - fb[4]
    low = G.section_polys(S["lcd_flex"], "x", 0.0).intersection(sbox(kt["y"][0] - 1, 0.0, mouth + 1e-6, 0.5 * (P.FLEX_ZB + P.FLEX_ZT)))   # lower run of the fold
    z_under = low.bounds[1] - zt if not low.is_empty else float("nan")
    need = 0.2                                                # the clearance check 17 keeps between a part and the tail
    okk = m_x >= -1e-9 and m_y0 >= -1e-9 and m_y1 >= -1e-9 and z_under - kt["max_part_height"] >= need - NUM_TOL and abs(kt["y"][1] - mouth) < 1e-6
    if not okk:
        fails.append(f"LCD tail keep-out: tail outside the zone (x margin {m_x:.3f}, y margins {m_y0:.3f} / {m_y1:.3f}) or only {z_under - kt['max_part_height']:.3f} mm above a part of the allowed height")
    krow.append(dict(keep_out="LCD flex tail (N10, PROVISIONAL)", yaml_centre=(0.0, round(0.5 * (kt["y"][0] + kt["y"][1]), 3)), yaml_size_mm=f"{2 * kt['half_w']} x {kt['y'][1] - kt['y'][0]:.1f}",
                     tub_area_inside_mm2="-", tub_area_outside_mm2=f"modelled tail inside the zone by {m_x:.3f} in x, {m_y0:.3f} at the rear; the zone ends at the mouth of J1 (y {mouth})",
                     lowest_tub_above_pcb_mm=round(z_under, 3), allowed=f"parts to {kt['max_part_height']} (tail underside {z_under:.3f} above the PCB: {z_under - kt['max_part_height']:.3f} over such a part, {need} needed)",
                     status="ok" if okk else "FAIL"))
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
    notes = [f"free height = YAML tub_keepouts.free_height_above_pcb = {P.PCB_FREE_H} mm above the PCB top (z {zf:.2f}): the height the layout may use everywhere on the "
             f"board outside the keep-outs (rev D; design/check_layout.py uses the same number, which closes D22). Above it the tub has the glass locating ribs "
             f"(lowest feature outside the keep-outs {low_out:.2f} mm above the PCB top, z {zt + low_out:.2f}), the thick roof at z {P.BOND_Z:.2f} and the nose and vent pads",
             f"keep-out prisms are enlarged by {tol} mm so that a face lying exactly on the contract boundary does not count as an intrusion",
             f"hood zones: tub material is allowed from {P.KO_HOOD_MAX_H} mm above the PCB top upward; the camera cube is exempt (it is a part, not tub)",
             f"height map: {len(hts)} rays on a {KO_GRID} mm grid over the board top (locating holes excluded); the corner fill between hood and side wall starts "
             f"at y = {P.HOOD_FILL_Y0:.2f}, where the PCB outline has left the hood zone",
             "the seating ledge (r >= 21.35) lies outside the PCB (r 21.1) and is checked as a clearance in check 2",
             f"LCD tail zone (YAML tub_keepouts.lcd_tail, N10): x +-{kt['half_w']}, y {kt['y'][0]} to {kt['y'][1]}, parts to {kt['max_part_height']} mm; it is a contract for the layout, not a tub "
             "feature: the row shows that the representative tail of the model (one U-fold behind the mouth of J1) lies inside it. PROVISIONAL until the Sharp tail drawing is in hand (gate B16)"]
    okall = not fails
    return res(12, "tub keep-out contract (YAML tub_keepouts)", okall,
               (f"no tub material in the layout space below z {zf:.2f} ({v:.6f} mm3 common); eight post feet inside their squares ({P.KO_POST_SIZE} mm, posts B {P.KO_LOC_SIZE} mm, built "
                f"{P.LOC_FOOT[0]:.1f} x {P.LOC_FOOT[1]:.1f}); LCD tail inside its zone, {z_under - kt['max_part_height']:.3f} mm over a {kt['max_part_height']} mm part; hood skirts "
                f"{min(r['lowest_tub_above_pcb_mm'] for r in krow if r['keep_out'].startswith('camera')):.2f} mm above the PCB inside the +-{P.KO_HOOD_HW} zones "
                f"(parts to {P.KO_HOOD_MAX_H}); lowest tub feature elsewhere {low_out:.2f} mm above the PCB" if okall else "FAILED: " + "; ".join(fails)),
               [dict(title="Boolean proof", rows=brow), dict(title="Keep-outs of the YAML against the tub solid", rows=krow),
                dict(title="Height of the tub above the PCB top by region (ray-cast height map)", rows=hrow)], notes, warns)


# ==============================================================================================
# 13. seal continuity
# ==============================================================================================
SEAL_ENVELOPE = (-26.0, 26.0, -26.0, 22.0, -2.0, 10.0)


def _seal_test_solid(name, solid):
    """The solid as it enters the air test.  A bare contact is not a seal: each visor window is drawn
    MECH['window_seal_test_gap'] off the recess floor and off its shelf, so that the cavity stays closed only if an
    adhesive solid closes all four edges of the glass."""
    if name.startswith("visor_window_"):
        g = M["window_seal_test_gap"]
        bb = solid.BoundingBox()
        return solid.intersect(PT.box(bb.xmin - 1, bb.xmax + 1, bb.ymin + g, bb.ymax + 1, bb.zmin + g, bb.zmax + 1).val())
    return solid


def _air_solids(S, names):
    """The air round and inside the marker: a box minus every marker solid (the visor windows drawn off their seats, see
    _seal_test_solid).  Returns the list of connected air solids."""
    air = PT.box(*SEAL_ENVELOPE).val()
    for n in names:
        air = air.cut(_seal_test_solid(n, S[n]))
    return list(air.Solids())


def check_seal(parts, cid=13, cname="seal continuity (air-solid test)"):
    """Is the marker closed?  (a) air-solid test: the outside and the inner cavity must be DIFFERENT connected air solids
    when every modelled seal (bead, adhesive sheet, pottings, window adhesive frames, cover tape, vent disc) is in place.
    Seals must be adhesive SOLIDS: the visor windows, which sit bare on their seats, are drawn 0.02 mm off the recess floor
    and off the shelf for this test, so a missing side fill, top bead or sill fillet opens the cavity;
    (b) the perimeter bead is one closed ring, with its height and volume; (c) the width of every seal land, measured on
    the sections.  Works on the active base variant (the alternative build is passed as A.variant_view)."""
    S = _solids(parts)
    puck = [n for n, i in parts.items() if i.group == "puck"]
    fails, warns = [], []
    cx, cy = P.CAM_XY["R"]
    cxl = P.CAM_XY["L"][0]
    rx, ry, _ = P.LOC_ROUND
    r_pot = 0.5 * (P.BAFFLE_RO + P.GRAIN_R)
    a_pot = math.radians(0.0)                                # between the LED pairs at 22.5 and 337.5 deg and off the 90 / 225 / 315 deg spokes
    probes = [
        ("outside, above the marker", (0.0, 0.0, 9.5), "outside"),
        ("grain opening, below the potting surface", (P.GRAIN_X + r_pot, P.GRAIN_Y, 0.5 * P.GRAIN_FILL_Z), "outside"),
        ("grain opening, in the potting outside the baffle", (P.GRAIN_X + r_pot * math.cos(a_pot), P.GRAIN_Y + r_pot * math.sin(a_pot), 0.5), "inside material"),
        ("grain opening, in the potting inside the baffle", (P.GRAIN_X + P.BAFFLE_RI - 0.3, P.GRAIN_Y, 0.3), "inside material"),
        ("pad slot", (0.5 * (P.PAD_XS[3] + P.PAD_XS[4]), P.PAD_Y, 0.5), "outside"),
        ("vent hole (the membrane is modelled as a closed disc)", (P.VENT_XY[0], P.VENT_XY[1], P.T - 0.6), "outside"),
        ("cover-glass rim gap", (0.5 * (P.CG_D + P.RECESS_D) / 2, 0.0, P.T - 0.5), "outside"),
        ("window R, in front of the glass", (cx, 0.5 * (P.WIN_Y1 + P.Y_VISOR), P.AXIS_Z), "outside"),
        ("window R, adhesive in the side gap", (cx + 0.25 * (P.WIN_W + P.WIN_RECESS_W), 0.5 * (P.WIN_Y0 + P.WIN_Y1), 5.5), "inside material"),
        ("window R, adhesive bead on the top edge of the glass", (cx, 0.5 * (P.WIN_Y0 + P.WIN_Y1), P.WIN_TOP_Z + 0.5 * M["window_top_bead"]), "inside material"),
        ("window R, adhesive fillet on the shelf in front of the glass", (cx, P.WIN_Y1 + 0.25 * P.WIN_SILL_FILLET, P.WIN_Z0 + 0.25 * P.WIN_SILL_FILLET), "inside material"),
        ("window R, test gap behind the glass, on the side land", (cx + 0.5 * (P.OPEN_HALF_W + P.WIN_W / 2), P.WIN_Y0 + 0.5 * M["window_seal_test_gap"], P.AXIS_Z), "cavity"),
        ("window R, test gap under the glass, on the shelf", (cx, 0.5 * (P.WIN_Y0 + P.WIN_Y1), P.WIN_Z0 + 0.5 * M["window_seal_test_gap"]), "cavity"),
        ("window L, test gap under the glass, on the shelf", (cxl, 0.5 * (P.WIN_Y0 + P.WIN_Y1), P.WIN_Z0 + 0.5 * M["window_seal_test_gap"]), "cavity"),
        ("main cavity (beside the battery)", (-18.0, 5.0, 3.0), "cavity"),
        ("camera bay R", (cx + 1.5, 15.0, 6.7), "cavity"),
        ("camera bay L", (cxl - 1.5, 15.0, 6.7), "cavity"),
        ("camera opening R, behind the window", (cx, P.WIN_RECESS_FLOOR_Y - 0.1, P.AXIS_Z), "cavity"),
        ("cell between cover glass and LCD", (0.0, 0.0, 0.5 * (P.BOND_Z + P.CG_Z0)), "cavity"),
        ("PCB locating hole (round), under the spigot tip", (rx, ry, P.PCB_Z0 + 0.1), "closed pocket"),
        ("PCB locating slot, beside the spigot", (P.LOC_SLOT[0] + math.copysign(0.5 * (P.LOC_SLOT[3] - 0.1), -P.LOC_SLOT[0]), P.LOC_SLOT[1], P.PCB_Z0 + 0.1), "cavity"),
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
            if i is None:                                         # which solid is the probe in?
                inside = [n for n in puck if S[n].isInside(v := cq.Vector(*pt), 1e-6)]
                got = "inside material" + (f" ({inside[0]})" if inside else "")
            ok = got.split(" (")[0] == expect and i_out != i_cav
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
    # (b) the perimeter bead is one closed ring round the PCB; its height and volume
    brow = []
    jsec = None
    for z in (0.5 * (P.BASE_T + P.LEDGE_Z0), 0.5 * (P.RIM_Z + P.BASE_T)):
        sec = G.section_polys(S["seal_bead"], "z", z)
        jsec = jsec if jsec is not None else sec
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
        land(nm, hole.distance(ext), "at the pad slot the sheet is the only barrier (a fillet round the PCB edge is the second one); the grain opening is "
             "potted as well, the foot holes are filled with epoxy")
    for s_ in ("L", "R"):
        # bond land of a window = glass rear face on the recess floor round the opening: section of the glass (just in front of
        # the floor) INTERSECT section of the tub (just behind the floor); the opening is the hole in it
        wsec = G.section_polys(S[f"visor_window_{s_}"], "y", P.WIN_Y0 + 0.01)
        tsec = G.section_polys(S["tub"], "y", P.WIN_RECESS_FLOOR_Y - 0.01)
        lsec = wsec.intersection(tsec)
        wg = max(getattr(lsec, "geoms", [lsec]), key=lambda g_: g_.area) if not lsec.is_empty else None
        wmin = SPoly(wg.interiors[0]).distance(wg.exterior) if (wg is not None and wg.interiors) else 0.0
        if wg is not None and wg.interiors:
            hb, eb = SPoly(wg.interiors[0]).bounds, wg.bounds
            sides = (min(hb[0] - eb[0], eb[2] - hb[2]), hb[1] - eb[1], eb[3] - hb[3])
        else:
            sides = (0.0, 0.0, 0.0)
        land(f"visor window {s_}: glass seated on the recess floor round the opening, narrowest seat (a seat, not a seal)", wmin,
             f"measured: sides {sides[0]:.2f}, sill {sides[1]:.2f}, top {sides[2]:.2f} (window {P.WIN_W} x {P.WIN_H}). The SEAL is the adhesive frame round the edge of the "
             f"glass: side-gap fills {(P.WIN_RECESS_W - P.WIN_W) / 2:.2f} x {P.WIN_T}, top bead {M['window_top_bead']} high, sill fillet {P.WIN_SILL_FILLET} x {P.WIN_SILL_FILLET} "
             f"({S[f'window_bond_{s_}'].Volume():.2f} mm3), proven by the air test with the glass drawn {M['window_seal_test_gap']} off its seats")
        fb = S[f"window_bond_{s_}"]
        land(f"visor window {s_}: adhesive frame, bonded width on the glass (side faces / top edge / front face at the sill)", min(P.WIN_T, P.WIN_SILL_FILLET),
             f"side faces {P.WIN_T} (glass thickness), top edge {P.WIN_T}, front face {P.WIN_SILL_FILLET}; one solid of {len(fb.Solids())} piece(s)")
        if len(fb.Solids()) != 1:
            fails.append(f"window {s_}: the adhesive frame is in {len(fb.Solids())} pieces")
        if wmin < min(P.WIN_LANDS) - 0.01 or any(abs(a_ - b_) > 0.01 for a_, b_ in zip(sides, P.WIN_LANDS)):
            fails.append(f"window {s_} seats {sides} differ from the design {P.WIN_LANDS}")
        if min(P.WIN_LANDS) < 0.4 - 1e-9:
            fails.append(f"window {s_}: a seat of {min(P.WIN_LANDS):.2f} mm is below 0.4 mm")
    csec = G.section_polys(S["cover_tape"], "z", 0.5 * (P.RECESS_FLOOR_Z + P.CG_Z0))
    cg_ = max(getattr(csec, "geoms", [csec]), key=lambda g_: g_.area)
    land("cover glass: tape ring", SPoly(cg_.interiors[0]).distance(cg_.exterior) if cg_.interiors else 0.0,
         f"{P.CG_TAPE_T} mm transfer tape, dia {P.CG_D} / {M['cover_tape_id']} on the recess floor (rev D)")
    land("vent: adhesive ring of the membrane disc", (M["vent_od"] - M["vent_area_dia"]) / 2, "PROVISIONAL part data")
    land("ball feet: epoxy plug in the through hole, length of the leak path", P.BASE_T, f"annulus {(P.BALL_HOLE_D - P.BALL_D) / 2:.3f} round the ball, then the backfilled sheet hole")
    gsec = G.section_polys(S["grain_potting"], "z", 0.5 * (P.GRAIN_FILL_Z + P.BASE_T))
    wall = G.section_polys(S["base_plate"], "z", 0.5 * (P.GRAIN_FILL_Z + P.BASE_T))
    land("grain opening: potting against the wall of the opening, bonded height", P.BASE_T - P.GRAIN_FILL_Z,
         f"clear potting from z {P.GRAIN_FILL_Z} to the PCB (z {P.PCB_Z0}), {S['grain_potting'].Volume():.1f} mm3 in {len(S['grain_potting'].Solids())} compartments; "
         f"gap potting to opening wall {gsec.distance(wall):.3f} mm; behind it the adhesive sheet round the opening")
    v_bead = S["seal_bead"].Volume()
    z_b0, z_b1 = A.bbox_of(parts["seal_bead"])[2], A.bbox_of(parts["seal_bead"])[5]
    jt, jtb = P.stack_tolerance()["joint"], P.stack_tolerance(printed=M["print_tol"])["joint"]
    v_hi, v_disp = P.seal_dispense_volume(v_bead, jsec.area)
    jrow = [dict(quantity="height of the joint on the seal land (base top to tub seal face)", value=R3(z_b1 - P.BASE_T), unit="mm",
                 basis=f"PCB {P.PCB_T} - printed step {P.PCB_Z1 - P.LEDGE_Z0:.2f} (post foot to seal face) + sheet {P.PSA_T}; the plate thickness is not in this chain ({P.BASE['label']})"),
            dict(quantity=f"range with +-{M['tol_printed']} on the printed step (drawing requirement): RSS / worst case",
                 value=((R3(P.BEAD_T - jt["rss"]), R3(P.BEAD_T + jt["rss"])), (R3(P.BEAD_T - jt["worst"]), R3(P.BEAD_T + jt["worst"]))), unit="mm",
                 basis="; ".join(f"{n} +-{t}" for n, t in jt["chain"]) + " (assumed)"),
            dict(quantity=f"range with +-{M['print_tol']} on the printed step (bureau general tolerance): RSS / worst case",
                 value=((R3(P.BEAD_T - jtb["rss"]), R3(P.BEAD_T + jtb["rss"])), (R3(P.BEAD_T - jtb["worst"]), R3(P.BEAD_T + jtb["worst"]))), unit="mm",
                 basis="; ".join(f"{n} +-{t}" for n, t in jtb["chain"]) + " (assumed)"),
            dict(quantity="area of the joint in plan (land + radial groove at that level)", value=round(jsec.area, 2), unit="mm2", basis="section of the bead solid"),
            dict(quantity="volume of adhesive at nominal gaps", value=round(v_bead, 2), unit="mm3",
                 basis=f"joint {jsec.area * P.BEAD_T:.1f} + fill of the {P.CLR} mm radial groove from the rim (z {P.RIM_Z}) to the plate top {v_bead - jsec.area * P.BEAD_T:.1f}"),
            dict(quantity=f"volume with the joint at its upper RSS limit, printed step +-{M['tol_printed']}", value=round(v_bead + jsec.area * jt["rss"], 1), unit="mm3", basis="nominal + plan area x RSS"),
            dict(quantity=f"volume with the joint at its upper RSS limit, printed step +-{M['print_tol']}", value=round(v_hi, 1), unit="mm3", basis="nominal + plan area x RSS: the least to dispense"),
            dict(quantity="volume to dispense", value=round(v_disp, 0), unit="mm3", basis="the line above rounded up to 5 mm3; squeeze-out is wiped; top-up fillet from outside")]
    if abs((z_b1 - P.BASE_T) - P.BEAD_T) > 1e-6 or abs(z_b0 - P.RIM_Z) > 1e-6:
        fails.append(f"seal bead spans z {z_b0:.3f}..{z_b1:.3f}, expected {P.RIM_Z}..{P.LEDGE_Z0}")
    notes = ["air-solid test: a box minus all marker solids; each remaining solid is one connected body of air. The marker is closed when the "
             "outside and the cavity are different bodies. Adhesives are modelled as cured, at nominal size; this proves that no modelled opening "
             "by-passes a seal - it does not prove that the adhesive wets or fills (leak test of every unit)",
             f"a bare contact is not counted as a seal: for the air test each visor window is drawn {M['window_seal_test_gap']} mm off the recess floor and off its shelf "
             "(probes 'test gap ...' lie in that gap and must belong to the cavity). The cavity then stays closed only through the adhesive frame of each window: "
             "two side-gap fills, the bead on the top edge and the fillet on the shelf; the self-test removes the fillet, and the bead, and the check fails",
             f"free air volume of the sealed cavity: {v_cav:.0f} mm3 (for the leak-test and vent calculations); it includes the cell between cover glass and LCD, "
             f"which breathes through the {M['lcd_psa_vent_w']} mm channel of the LCD adhesive frame",
             "the round PCB locating hole is closed by the foot of post B+ that seats round it: 0.39 mm3 of trapped air, harmless; the slot under post B- "
             f"reaches {P.LOC_SLOT[3] / 2 - (abs(P.LOC_SLOT[0]) - P.LCD_POCKET_X):.2f} mm past the cut-back foot and stays open to the cavity",
             f"rev D: the grain opening is potted (clear, from the PCB down to z {P.GRAIN_FILL_Z}); the pad slot stays open, there the adhesive sheet is the only "
             "barrier. The base plate has a plain edge and the bead is one ring (no key notch)",
             f"base plate variant: {P.BASE['label']}: plate {P.BASE_T}, sheet {P.PSA_T}, joint {P.BEAD_T:.2f} mm"]
    return res(cid, cname, not fails,
               (f"outside and inner cavity are separate air solids (cavity {v_cav:.0f} mm3 incl. the cell under the cover glass); perimeter bead is one closed ring, "
                f"{P.BEAD_T:.2f} mm high, narrowest joint {min(ws):.2f} mm, {v_bead:.1f} mm3 at nominal gaps; adhesive-sheet lands "
                f"{min(r['land_width_mm'] for r in lrow if r['seal'].startswith('adhesive sheet')):.2f} mm and more; grain opening potted; each visor window closed by its "
                f"adhesive frame (air test run with the glass {M['window_seal_test_gap']} mm off its seats); to dispense {v_disp:.0f} mm3"
                if not fails else "FAILED: " + "; ".join(dict.fromkeys(fails))),
               [dict(title="Probe points", rows=prow), dict(title="Connected air solids (box minus all marker solids)", rows=arow),
                dict(title="Perimeter bead sections", rows=brow), dict(title="Perimeter seal joint: height and volume", rows=jrow),
                dict(title="Seal lands", rows=lrow)], notes, warns)


# ==============================================================================================
# 14. assembly paths
# ==============================================================================================
def _turn_x(shape, y0, z0, deg):
    """Rotate about the axis parallel to x through (y0, z0); positive angle lifts +y points to +z."""
    return shape.rotate(cq.Vector(0, y0, z0), cq.Vector(1, y0, z0), deg) if abs(deg) > 1e-12 else shape


def _pcb_slot_from_solid(S):
    """The locating slot of the PCB as BUILT: (length along x, width, centre x, centre y) of the cut-out nearest to the YAML slot
    position in the section of the main PCB solid at mid thickness (None when there is no such cut-out)."""
    from shapely.geometry import Polygon as SPoly
    sec = G.section_polys(S["main_pcb"], "z", 0.5 * (P.PCB_Z0 + P.PCB_Z1), 2e-4)
    pg = max(getattr(sec, "geoms", [sec]), key=lambda g_: g_.area)
    best = None
    for ring in pg.interiors:
        hp = SPoly(ring)
        d = math.hypot(hp.centroid.x - P.LOC_SLOT[0], hp.centroid.y - P.LOC_SLOT[1])
        if d < 1.0 and (best is None or d < best[0]):
            x0, y0, x1, y1 = hp.bounds
            best = (d, x1 - x0, y1 - y0, 0.5 * (x0 + x1), 0.5 * (y0 + y1))
    return best[1:] if best else None


def _pcb_round_from_solid(S):
    """The round locating hole of the PCB as BUILT: (diameter, centre x, centre y) of the circular cut-out nearest to the YAML
    position in the section of the main PCB solid at mid thickness (None when there is none)."""
    from shapely.geometry import Polygon as SPoly
    sec = G.section_polys(S["main_pcb"], "z", 0.5 * (P.PCB_Z0 + P.PCB_Z1), 2e-4)
    pg = max(getattr(sec, "geoms", [sec]), key=lambda g_: g_.area)
    best = None
    for ring in pg.interiors:
        hp = SPoly(ring)
        d = math.hypot(hp.centroid.x - P.LOC_ROUND[0], hp.centroid.y - P.LOC_ROUND[1])
        if d < 1.0 and (best is None or d < best[0]):
            x0, y0, x1, y1 = hp.bounds
            best = (d, 0.5 * ((x1 - x0) + (y1 - y0)), 0.5 * (x0 + x1), 0.5 * (y0 + y1), abs((x1 - x0) - (y1 - y0)))
    return best[1:] if best else None


def _lcd_pocket_obstacles(tub):
    """Everything of the tub that the LCD glass and its adhesive frame can meet when they move in their own plane: the union
    of the tub sections inside their height range, near the glass, as a shapely shape relative to the glass centre."""
    from shapely.ops import unary_union
    from shapely import affinity
    zs = sorted({P.LCD_Z0 + 0.01, M["lcd_rib_z0"] + 0.02, P.HOOD_Z_OVER_CUBE + 0.02, 0.5 * (P.LCD_Z0 + P.BOND_Z), P.BOND_Z - 0.01})
    zs = [z for z in zs if P.LCD_Z0 < z < P.BOND_Z]
    win = sbox(P.LCD_X0 - 3.0, P.LCD_Y0 - 3.0, P.LCD_X1 + 3.0, P.LCD_Y1 + 3.0)
    obs = unary_union([G.section_polys(tub, "z", z, 5e-4).intersection(win) for z in zs])
    return affinity.translate(obs, -P.LCD["x"], -P.LCD["y"]), zs


def _lcd_feasible(obs, deg, half=1.5):
    """Positions (dx, dy) of the glass centre at which the glass, turned by `deg` about its centre, touches nothing: the
    window of translations less the configuration-space obstacle (Minkowski sum of the obstacles with the mirrored glass,
    built as the union of the hulls swept by every boundary segment)."""
    from shapely.geometry import MultiPoint
    from shapely.ops import unary_union
    a, b = P.LCD["dx"] / 2, P.LCD["dy"] / 2
    t = math.radians(deg)
    ct, st = math.cos(t), math.sin(t)
    cor = [(ct * x - st * y, st * x + ct * y) for x, y in ((a, b), (-a, b), (-a, -b), (a, -b))]
    hulls = []
    for pg in getattr(obs, "geoms", [obs]):
        if pg.is_empty or pg.geom_type != "Polygon":
            continue
        for ring in [pg.exterior] + list(pg.interiors):
            xy = list(ring.simplify(1e-3).coords)
            for (x0, y0), (x1, y1) in zip(xy[:-1], xy[1:]):
                hulls.append(MultiPoint([(x0 - cx, y0 - cy) for cx, cy in cor] + [(x1 - cx, y1 - cy) for cx, cy in cor]).convex_hull)
    return sbox(-half, -half, half, half).difference(unary_union(hulls + [obs]))


def _lcd_rotation(S, tol_deg=0.002):
    """Display rotation (E12): how far the LCD glass can turn in its pocket.  Returns dict(ccw, cw (deg, by bisection on the
    configuration-space construction), pose (dx, dy at the limit), stops (what the glass touches there), walls (the same for
    a pocket with continuous walls at the fit clearance), ribs (the two rear ribs measured on the tub section), levels)."""
    from shapely import affinity
    tub = S["tub"]
    obs, zs = _lcd_pocket_obstacles(tub)
    a, b = P.LCD["dx"] / 2, P.LCD["dy"] / 2
    out = dict(levels=zs)
    for key, sgn in (("ccw", 1.0), ("cw", -1.0)):
        lo, hi = 0.0, 6.0
        if _lcd_feasible(obs, 0.0).area < 1e-9:
            out[key] = float("nan"); continue
        while hi - lo > tol_deg:
            mid = 0.5 * (lo + hi)
            if _lcd_feasible(obs, sgn * mid).area > 1e-9:
                lo = mid
            else:
                hi = mid
        out[key] = lo
        free = _lcd_feasible(obs, sgn * lo)
        c = free.representative_point()
        glass = affinity.translate(affinity.rotate(sbox(-a, -b, a, b), sgn * lo, origin=(0, 0)), c.x, c.y)
        near = obs.intersection(glass.buffer(0.02))
        stops = []
        for g_ in getattr(near, "geoms", [near]):
            if g_.is_empty:
                continue
            x, y = g_.centroid.x + P.LCD["x"], g_.centroid.y + P.LCD["y"]
            side = "+x" if x > 0 else "-x"
            if y < P.LCD_Y0:
                nm = f"rear glass rib {side}"
            elif y > P.LCD_Y1:
                nm = f"hood rear wall {side}" if abs(x) > abs(P.CAM_X) - P.HOOD_OUT_HW - 0.1 else f"post E{side[0]}"
            elif abs(x) > P.LCD_X1:
                nm = f"post B{side[0]}" if abs(y - P.LOC_ROUND[1]) < P.KO_LOC_SIZE else f"side rib {side} (y {y:.1f})"
            else:
                nm = f"tub at ({x:.1f}, {y:.1f})"
            if nm not in stops:
                stops.append(nm)
        out[key + "_pose"] = (c.x, c.y)
        out[key + "_stops"] = stops
    # the manufacturing review's estimate: a pocket with continuous walls at the fit clearance all round
    lo, hi = 0.0, 6.0
    while hi - lo > 1e-5:
        mid = 0.5 * (lo + hi)
        t = math.radians(mid)
        if max(2 * a * math.cos(t) + 2 * b * math.sin(t) - 2 * (a + P.CLR), 2 * b * math.cos(t) + 2 * a * math.sin(t) - 2 * (b + P.CLR)) <= 0:
            lo = mid
        else:
            hi = mid
    out["walls"] = lo
    # the two rear glass ribs (the pocket datum of step 9), measured on the tub section at the height of the glass
    band = sbox(P.LCD_X0 - 1.0, P.LCD_POCKET_Y0 - M["lcd_rib_t"] - 0.2, P.LCD_X1 + 1.0, P.LCD_POCKET_Y0 + 0.2)
    sec = G.section_polys(tub, "z", 0.5 * (P.LCD_Z0 + P.LCD_Z1), 2e-4).intersection(band)
    ribs = []
    for g_ in getattr(sec, "geoms", [sec]):
        if g_.is_empty or g_.area < 0.5:
            continue
        x0, y0, x1, y1 = g_.bounds
        if x1 - x0 < 6.0 and x0 >= P.LCD_X0 and x1 <= P.LCD_X1:   # a rib behind the glass edge, not the side wall
            ribs.append((x0, x1, y1))
    out["ribs"] = sorted(ribs)
    return out


def check_assembly_paths(parts):
    """Blind assembly steps proven on the solids: (a) the LCD glass (with its adhesive frame) tilted in past the seating
    ledge; (b) the PCB / base unit lowered straight into the tub with the lateral error a guide may leave; (c) the same
    unit closed about a hinge behind the tub (the motion that lets the LCD tail be mated with the unit open); (e) the
    travel of the spigot in the PCB slot, measured on the PCB solid (N9); (f) the rotation the LCD glass can take in its
    pocket and the squaring of the glass against the two rear ribs (E12)."""
    S = _solids(parts)
    tub = S["tub"]
    fails, warns = [], []
    lim = 1e-4
    # ---------------- (a) LCD tilt-in
    lcd = cq.Compound.makeCompound([S["lcd_glass"], S["lcd_adhesive"]])
    tau, bias = M["lcd_tilt_deg"], M["lcd_bias"]
    y0, z0 = P.LCD_Y0, P.BOND_Z                               # rear top edge of the glass + frame
    rise = P.LCD["dy"] * math.sin(math.radians(tau))          # the front edge trails this far behind the rear edge
    t_stack = P.BOND_Z - P.LCD_Z0                             # glass + adhesive frame (0.90)
    front_margin = 0.15                                       # the front top edge stays this far below the feet of posts E while shifted
    z_push = P.PCB_Z1 - front_margin + rise                   # rear top edge at the push-back height (4.82): level with the rear ribs
    ttau = math.tan(math.radians(tau))
    # push back until the rear face of the tilted glass meets the lower corner of the two rear ribs (z = LCD_REAR_RIB_Z0); while the
    # rear edge is raised that corner slides down the rear face, and once the lower rear edge has passed it the edge runs up the ribs
    dy_at = lambda zr: -(P.CLR - min(max(0.0, zr - P.LCD_REAR_RIB_Z0), t_stack * math.cos(math.radians(tau))) * ttau)
    dy_stop = dy_at(z_push)
    dy_rib = -(P.CLR - t_stack * math.sin(math.radians(tau)))
    z_mid = 0.5 * (z_push + z0 - 0.3)
    hair = 0.005                                              # the poses stand this far off the ribs (a contact pose is not a robust boolean)
    seq = [(tau, bias, -(z0 - P.RIM_Z - 0.1), "rear edge enters the rim, glass tilted, shifted toward the visor"),
           (tau, bias, -(z0 - P.LEDGE_Z0 - 0.05), "rear edge at the underside of the seating ledge"),
           (tau, bias, -(z0 - 0.5 * (P.LEDGE_Z0 + P.LEDGE_Z1)), "rear corners inside the ledge ring"),
           (tau, bias, -(z0 - P.LEDGE_Z1 - 0.05), "rear edge leaves the ledge"),
           (tau, bias, -(z0 - P.LEDGE_Z1 - 0.9), "rear edge above the ledge"),
           (tau, bias, -(z0 - z_push), f"last shifted pose: rear edge level with the rear ribs, front edge {front_margin:.2f} below the feet of posts E"),
           (tau, dy_stop + hair, -(z0 - z_push), f"pushed back against the two rear ribs (the stop; {hair} mm off them in this pose)"),
           (tau, dy_at(z_mid) + hair, -(z0 - z_mid), "rear edge rising, the rear face sliding on the foot of the ribs"),
           (tau, dy_rib + hair, -0.3, "rear edge 0.3 below the bonding plane, lower rear edge on the ribs"),
           (0.66 * tau, dy_rib + hair, -0.2, "front hinged up"), (0.33 * tau, dy_rib + hair, -0.1, "front hinged up"), (1.0, dy_rib + hair, -0.05, "nearly flat"),
           (0.0, dy_rib + hair, 0.0, f"seated on the bonding plane, {abs(dy_rib + hair):.2f} behind the nominal position (contact)"),
           (0.0, 0.0, 0.0, "the nominal position of the model, for reference (contact)")]
    # the ribs must really BE the stop at the push-back height: 0.05 mm further back the glass has to run into them
    past = _turn_x(lcd, y0, z0, -tau).translate(cq.Vector(0, dy_stop - 0.05, -(z0 - z_push)))
    v_past = common_volume(past, tub)
    if not v_past > 1e-4:
        fails.append(f"LCD tilt-in: the rear ribs do not stop the glass at the push-back height (rear edge z {z_push:.2f}, ribs from z {P.LCD_REAR_RIB_Z0})")
    lrow = []
    for i, (t_, dy, dz, what) in enumerate(seq, 1):
        sh = _turn_x(lcd, y0, z0, -t_).translate(cq.Vector(0, dy, dz))
        v = common_volume(sh, tub)
        d = min_distance(sh, tub)
        zf = z0 + dz - P.LCD["dy"] * math.sin(math.radians(t_))
        ok = v < lim
        if not ok:
            fails.append(f"LCD tilt-in pose {i}: {v:.4f} mm3 of interference with the tub")
        lrow.append(dict(pose=i, what=what, tilt_deg=round(t_, 2), shift_toward_visor_mm=R3(dy), rear_edge_z=R3(z0 + dz), front_edge_z=R3(zf),
                         interference_with_tub_mm3=round(v, 5), smallest_gap_to_tub_mm=R3(d), status="ok" if ok else "FAIL"))
    flat = lcd.translate(cq.Vector(0, P.CLR, -(z0 - 0.5 * (P.LEDGE_Z0 + P.LEDGE_Z1))))
    lrow.append(dict(pose="-", what="proof of the stop: 0.05 mm further back than the push-back pose the glass runs into the rear ribs", tilt_deg=tau, shift_toward_visor_mm=R3(dy_stop - 0.05),
                     rear_edge_z=R3(z_push), front_edge_z=R3(z_push - rise), interference_with_tub_mm3=round(v_past, 5), smallest_gap_to_tub_mm=0.0,
                     status="information (interference expected)" if v_past > 1e-4 else "FAIL"))
    lrow.append(dict(pose="-", what=f"for comparison: glass kept FLAT and shifted {P.CLR} (the rev B method, no longer used)", tilt_deg=0.0, shift_toward_visor_mm=P.CLR,
                     rear_edge_z=R3(0.5 * (P.LEDGE_Z0 + P.LEDGE_Z1)), front_edge_z=R3(0.5 * (P.LEDGE_Z0 + P.LEDGE_Z1)),
                     interference_with_tub_mm3=round(common_volume(flat, tub), 5), smallest_gap_to_tub_mm=R3(min_distance(flat, tub)), status="information"))
    gap_ledge = min(r["smallest_gap_to_tub_mm"] for r in lrow[1:4])
    if gap_ledge < P.CLR - NUM_TOL:
        fails.append(f"LCD tilt-in: only {gap_ledge:.3f} mm to the ledge")
    # ---------------- (b), (c) PCB / base unit
    board_names = ["main_pcb", "battery", "pcb_adhesive", "base_plate"] + [n for n in parts if n.startswith("battery_lead_")]
    optics = cq.Compound.makeCompound([S[n] for n in ("camera_L", "camera_R", "prism_L", "prism_R")])
    board = cq.Compound.makeCompound([S[n] for n in board_names])
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
    # ---------------- (d) lateral chain base-plate edge -> tub bore (arithmetic on ASSUMED tolerances): why every unit is tried dry
    crow = []
    for tp_, tname in ((M["tol_printed"], f"printed +-{M['tol_printed']} (drawing requirement)"), (M["print_tol"], f"printed +-{M['print_tol']} (bureau general)")):
        for frame, fname in ((M["jig_frame_clearance"], "fixed frame round the plate"), (0.0, "plate centred by sprung fingers")):
            chain = [("plate outline (radius)", M["fr4_tol_outline"]), ("plate in the jig", frame), ("jig pin in the PCB hole", M["jig_pin_fit"]), ("spigot fit", P.SPIGOT_FIT),
                     ("spigot to bore axis (printed)", tp_), ("bore radius (printed)", tp_ / 2)]
            rss, worst = math.sqrt(sum(t * t for _, t in chain)), sum(t for _, t in chain)
            crow.append(dict(tub_tolerance=tname, lamination_jig=fname, chain="; ".join(f"{n} {t:g}" for n, t in chain if t), rss_mm=R3(rss), worst_case_mm=R3(worst),
                             radial_gap_mm=P.CLR, margin_rss_mm=R3(P.CLR - rss), margin_worst_case_mm=R3(P.CLR - worst)))
    # ---------------- (e) the PCB slot under post B-, MEASURED on the PCB solid (decision N9: 2.2 long)
    slot = _pcb_slot_from_solid(S)
    slot_len = slot[0] if slot else float("nan")
    pos_tol = 0.01                                            # the solid must carry the YAML numbers: length, width and BOTH centre coordinates
    if (slot is None or abs(slot[0] - P.LOC_SLOT[3]) > pos_tol or abs(slot[1] - P.LOC_SLOT[2]) > pos_tol or abs(slot[2] - P.LOC_SLOT[0]) > pos_tol
            or abs(slot[3] - P.LOC_SLOT[1]) > pos_tol):
        fails.append(f"PCB locating slot: the board solid has {('%.2f x %.2f at (%.3f, %.3f)' % slot[:4]) if slot else 'no slot'}, the YAML asks for {P.LOC_SLOT[3]} x {P.LOC_SLOT[2]} at "
                     f"({P.LOC_SLOT[0]}, {P.LOC_SLOT[1]}): a slot {pos_tol} or more off its centre line moves the cameras (the across-slot fit is {P.SPIGOT_FIT:.3f})")
    rnd = _pcb_round_from_solid(S)
    if (rnd is None or abs(rnd[0] - P.LOC_ROUND[2]) > pos_tol or abs(rnd[1] - P.LOC_ROUND[0]) > pos_tol or abs(rnd[2] - P.LOC_ROUND[1]) > pos_tol or rnd[3] > pos_tol):
        fails.append(f"PCB locating hole (round): the board solid has {('dia %.2f at (%.3f, %.3f)' % rnd[:3]) if rnd else 'no round hole'}, the YAML asks for dia {P.LOC_ROUND[2]} at "
                     f"({P.LOC_ROUND[0]}, {P.LOC_ROUND[1]})")
    slot_allow = (slot_len - P.SPIGOT_D) / 2
    dT = max(abs(t - M["t_assembly"]) for t in M["t_range"])
    slot_need = [(f"spigot spacing printed +-{tp_}", tp_) for tp_ in (M["print_tol"], 0.3)]
    th_sp = P.SPIGOT_SPAN * abs(M["cte_pa12"] - M["cte_fr4"]) * 1e-6 * dT
    srow_ = [dict(case=n, slot_length_on_the_solid_mm=R3(slot_len), slot_centre_on_the_solid_xy=((R3(slot[2]), R3(slot[3])) if slot else "-"), spacing_error_mm=t, hole_position_mm=M["fr4_tol_hole"], thermal_mm=R3(th_sp), sum_mm=R3(t + M["fr4_tol_hole"] + th_sp),
                  slot_allows_mm=R3(slot_allow), margin_mm=R3(slot_allow - (t + M["fr4_tol_hole"] + th_sp))) for n, t in slot_need]
    # ---------------- (f) display rotation (E12): free rotation of the glass in its pocket, and the squaring aid of step 9
    rot = _lcd_rotation(S)
    rmax = max(rot["ccw"], rot["cw"])
    lcd_c = cq.Vector(P.LCD["x"], P.LCD["y"], 0.0)
    rrow = []
    for key, sgn in (("ccw", 1.0), ("cw", -1.0)):
        th, (px, py) = rot[key], rot[key + "_pose"]
        turned = lambda d_: lcd.rotate(lcd_c, lcd_c + cq.Vector(0, 0, 1), sgn * d_).translate(cq.Vector(px, py, 0))
        v_in, v_out = common_volume(turned(max(0.0, th - 0.02)), tub), common_volume(turned(th + 0.05), tub)
        if not v_in < lim:
            fails.append(f"display rotation: the pose found on the sections ({th:.2f} deg {key}) interferes with the tub solid by {v_in:.4f} mm3")
        rrow.append(dict(quantity=f"free rotation of the glass in its pocket, {'counter-clockwise' if sgn > 0 else 'clockwise'} seen from above", value_deg=round(th, 3),
                         glass_centre_shift_xy_mm=(R3(px), R3(py)), stopped_by=", ".join(rot[key + "_stops"]) or "-",
                         solid_check=f"glass + frame turned {max(0.0, th - 0.02):.2f} deg at that position: {v_in:.5f} mm3 common with the tub; turned {th + 0.05:.2f} deg: {v_out:.4f} mm3",
                         status="ok" if (th <= M["lcd_free_rotation_limit_deg"] and v_in < lim) else "FAIL"))
    if not rmax <= M["lcd_free_rotation_limit_deg"]:
        fails.append(f"display rotation: the LCD glass can turn {rmax:.2f} deg in its pocket, more than the {M['lcd_free_rotation_limit_deg']} deg the stored correction (E12) is sized for")
    ribs = rot["ribs"]
    rib_ok = len(ribs) == 2 and ribs[0][1] < 0 < ribs[1][0] and abs(ribs[0][2] - ribs[1][2]) < 1e-6
    push_e = M["lcd_pusher_pad_w"] / 2 + M["lcd_pusher_guide_tol"]
    if rib_ok:
        span_in, span_c = ribs[1][0] - ribs[0][1], ribs[1][1] - ribs[0][1]         # between the inner corners; inner corner of one rib to the outer corner of the other
        m_push = min(-ribs[0][1], ribs[1][0]) - push_e
        resid = math.degrees(math.atan(M["lcd_rib_step_tol"] / span_c))
        if m_push <= 0:
            fails.append("display rotation: the squaring pusher does not act between the two rear glass ribs")
    else:
        span_in = span_c = m_push = resid = float("nan")
        fails.append(f"display rotation: the two rear glass ribs (the datum the glass is squared against) were not found on the tub section ({len(ribs)} found)")
    rrow += [dict(quantity="for comparison: a pocket with continuous walls at the fit clearance (the manufacturing review's estimate)", value_deg=round(rot["walls"], 3),
                  glass_centre_shift_xy_mm="-", stopped_by="arithmetic", solid_check="-", status="information"),
             dict(quantity="aim-line transfer budget of the specification (E12)", value_deg=M["lcd_line_budget_deg"], glass_centre_shift_xy_mm="-",
                  stopped_by="DESIGN_SPEC section 6", solid_check="-", status="information: the free rotation exceeds it, hence the squaring aid and the factory measurement"),
             dict(quantity="glass squared against the two rear ribs (assembly step 9): rotation left in the model", value_deg=0.0, glass_centre_shift_xy_mm="-",
                  stopped_by=(f"both rear ribs: faces at y {ribs[0][2]:.2f}, x {ribs[0][0]:.1f}..{ribs[0][1]:.1f} and {ribs[1][0]:.1f}..{ribs[1][1]:.1f}" if rib_ok else "-"),
                  solid_check="rib faces coplanar on the tub section" if rib_ok else "-", status="ok" if rib_ok else "FAIL"),
             dict(quantity=f"residual angle per {M['lcd_rib_step_tol']} mm of step between the two rib faces (printed)", value_deg=round(resid, 3), glass_centre_shift_xy_mm="-",
                  stopped_by=f"contact points {span_c:.1f} mm apart" if rib_ok else "-", solid_check="arithmetic on an assumed print error", status="information"),
             dict(quantity="squaring pusher: its line of action inside the span of the two rib faces (margin, mm)", value_deg=R3(m_push), glass_centre_shift_xy_mm="-",
                  stopped_by=f"pad {M['lcd_pusher_pad_w']} wide on x = 0 +-{M['lcd_pusher_guide_tol']}; inner rib corners at x = +-{min(-ribs[0][1], ribs[1][0]):.1f}" if rib_ok else "-",
                  solid_check="a push between the two ribs beds the glass on both", status="ok" if rib_ok and m_push > 0 else "FAIL")]
    e_in = min(abs(x_) for n_, x0_, x1_, y0_, y1_ in P.post_rects() if n_[0] == "E" for x_ in (x0_, x1_))      # inner faces of the two posts E
    m_e = e_in - push_e
    if m_e < P.CLR - NUM_TOL:
        fails.append(f"display rotation: the squaring pusher (half width {push_e} with its guidance) has only {m_e:.2f} mm to the posts E")
    rrow.append(dict(quantity="squaring pusher: clearance to the two posts E, between which it passes (mm)", value_deg=R3(m_e), glass_centre_shift_xy_mm="-",
                     stopped_by=f"inner faces of posts E at x = +-{e_in:.1f}", solid_check="post rectangles of the model", status="ok" if m_e >= P.CLR - NUM_TOL else "FAIL"))
    if min(r["margin_worst_case_mm"] for r in crow) < 0:
        warns.append(f"base-plate edge to tub bore: the lateral chain uses up the {P.CLR} mm gap at the worst case "
                     f"({max(r['worst_case_mm'] for r in crow)} mm; RSS {min(r['rss_mm'] for r in crow)} to {max(r['rss_mm'] for r in crow)} mm): every laminated unit is tried dry "
                     "in its own tub before the seal bead (assembly step 14)")
    if not min(r["margin_mm"] for r in srow_) >= 0:
        fails.append(f"PCB slot: +-{slot_allow:.2f} mm along the slot against up to {max(r['sum_mm'] for r in srow_)} mm of spacing error, hole position and thermal movement "
                     f"(the YAML slot is {P.LOC_SLOT[3]} long for this, N9)")
    if rmax > M["lcd_line_budget_deg"]:
        warns.append(f"display rotation: left free, the LCD glass can turn {rmax:.2f} deg in its pocket ({rot['walls']:.2f} deg with continuous walls), more than the {M['lcd_line_budget_deg']} deg "
                     "line-transfer budget: it is squared against the two rear ribs in step 9 and the residual angle is measured at the factory and stored (E12)")
    notes = [f"(a) LCD: glass with its adhesive frame, rear edge first at {tau} deg, shifted {bias} mm toward the visor while the rear corners pass the "
             f"seating ledge (r {P.LEDGE_RI}); the front edge is then still below the feet of posts E (z {P.PCB_Z1}), so the shift is free. The glass passes between the two "
             f"posts B with {P.LCD_POCKET_X - P.LCD_X1:.2f} mm per side (their feet are cut back for it: YAML post_feet.locating.foot, N1; the spigots are {abs(P.LOC_ROUND[0]) - P.SPIGOT_D / 2 - P.LCD_X1:.2f} mm "
             f"outside the glass edge). Smallest gap to the ledge {gap_ledge:.2f} mm (flat insertion: {lrow[-1]['smallest_gap_to_tub_mm']} mm). The frame is applied to the LCD, not to the roof",
             f"(a) the stop: still shifted, the rear edge is raised to z {z_push:.2f} (front edge {front_margin:.2f} below the feet of posts E); the two rear ribs reach down to z "
             f"{P.LCD_REAR_RIB_Z0} (the free height above the PCB), so the rear face of the glass overlaps them by {z_push - P.LCD_REAR_RIB_Z0:.2f} mm and the glass is pushed back "
             f"{bias - dy_stop:.2f} mm against them. Raised further, its lower rear edge runs up the ribs; hinged flat it lies {abs(dy_rib):.2f} mm behind its nominal position, "
             f"{P.CLR - abs(dy_rib):.2f} mm in front of the ribs, inside the {P.CLR} mm pocket clearance (the nominal position is the last pose)",
             f"(b) the unit = PCB with cameras, prisms, battery and its leads, adhesive sheet, base plate, baffle, potting and potted feet (the base is laminated to the PCB "
             f"and the grain opening potted before the join). Straight descent with +-{o} mm of lateral error in x and y until the spigots engage ({P.SPIGOT_H} mm before the seat); the "
             f"{M['spigot_tip_chamfer']} mm tip chamfer of the spigots captures up to {cap:.3f} mm. The hood gaskets (compressible) and the wet seal adhesive are not part of this test",
             f"(c) hinge axis parallel to x at y = {hy}, z = {hz} (join fixture). The last column is the straight distance from the mouth of J1 to the rear "
             "edge of the LCD glass: the length of free tail needed to mate the connector at that opening (the real tail length is PROVISIONAL)",
             "these are nominal solids: the paths show that the motion exists and how much room it has, not that every printed part allows it "
             "(go gauges in the assembly sequence)",
             f"(d) no key between base plate and tub: the plate edge reaches the bore through the chain in the fourth table. The plate top passes the rim {P.BASE_T - P.RIM_Z:.2f} mm "
             f"before the seat, after the spigots have engaged at {P.SPIGOT_H} mm, so an offset plate would fight the two spigots with the bead wet: hence the dry trial close of every unit",
             f"(e) slot under post B-: {slot_len:.2f} x {slot[1] if slot else float('nan'):.2f} at ({slot[2] if slot else float('nan'):.2f}, {slot[3] if slot else float('nan'):.2f}) and round hole dia "
             f"{rnd[0] if rnd else float('nan'):.2f} at ({rnd[1] if rnd else float('nan'):.2f}, {rnd[2] if rnd else float('nan'):.2f}), measured on the section of the PCB solid and compared with the YAML to {pos_tol} in "
             f"length, width and both centre coordinates (YAML {P.LOC_SLOT[3]} x {P.LOC_SLOT[2]}, decision N9); the spigot may move "
             f"+-{slot_allow:.3f} along it. Needed: spacing error of the two printed spigots, hole position +-{M['fr4_tol_hole']} and {th_sp:.2f} mm of thermal movement at {max(M['t_range']):.0f} C",
             f"(f) display rotation: obstacles = union of the tub sections at z {', '.join(f'{z:.2f}' for z in rot['levels'])} (the height of the glass and its frame) near the glass; for a rotation "
             "angle the set of free positions of the glass centre is the translation window less the Minkowski sum of the obstacles with the mirrored glass; the largest angle with a free position "
             f"is found by bisection to 0.002 deg and confirmed by a boolean on the solids. The check fails above {M['lcd_free_rotation_limit_deg']} deg (the specification sizes the stored "
             "correction on 'up to about 1 degree'). The squaring aid is a pusher on the centre of the front edge of the tilted glass: pushed between the two rear ribs the glass beds on both"]
    return res(14, "assembly paths (LCD tilt-in, PCB / base join)", not fails,
               (f"LCD glass tilts in at {tau} deg with {gap_ledge:.2f} mm to the ledge ({len(seq)} poses, no interference); the PCB / base unit descends with "
                f"+-{o} mm lateral error ({len(jrow)} heights) and closes about the fixture hinge ({len(hrow)} angles) without interference; PCB slot {slot_len:.2f} long on the solid: "
                f"+-{slot_allow:.2f} against {min(r['sum_mm'] for r in srow_)} to {max(r['sum_mm'] for r in srow_)} needed (margin {min(r['margin_mm'] for r in srow_)} to {max(r['margin_mm'] for r in srow_)}); "
                f"display rotation: the glass can turn {rmax:.2f} deg free in its pocket, 0 when bedded on the two rear ribs"
                if not fails else "FAILED: " + "; ".join(fails)),
               [dict(title="LCD tilt-in (glass + adhesive frame against the tub)", rows=lrow),
                dict(title="PCB / base unit, straight descent", rows=jrow), dict(title="PCB / base unit, hinged close", rows=hrow),
                dict(title="Base-plate edge to the tub bore: lateral chain (arithmetic on assumed tolerances)", rows=crow),
                dict(title="PCB slot: travel along the slot (length measured on the PCB solid) against spacing error, hole position and thermal movement", rows=srow_),
                dict(title="LCD glass: rotation in its pocket (display rotation, E12)", rows=rrow)], notes, warns)


# ==============================================================================================
# 15. FR-4 base plate: fabrication rules
# ==============================================================================================
def _ring_corners(coords, hole, sharp_deg=15.0):
    """Sharp vertices of a boundary ring: [(x, y, turn_deg, internal)].  internal = the material is re-entrant there (a router
    bit cannot make it sharp: it needs a radius or a drilled relief)."""
    from shapely.geometry import Polygon as SPoly
    pts = np.asarray(coords)
    keep = np.ones(len(pts), bool)
    keep[1:] = np.hypot(*(pts[1:] - pts[:-1]).T) > 1e-7        # drop repeated points (the closing point, doubled seams)
    pts = pts[keep]
    if np.hypot(*(pts[0] - pts[-1])) < 1e-7:
        pts = pts[:-1]
    ccw = SPoly(pts).exterior.is_ccw
    out = []
    n = len(pts)
    for i in range(n):
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % n]
        u, v = b - a, c - b
        lu, lv = np.hypot(*u), np.hypot(*v)
        if lu < 1e-9 or lv < 1e-9:
            continue
        cr = (u[0] * v[1] - u[1] * v[0]) / (lu * lv)
        turn = math.degrees(math.asin(max(-1.0, min(1.0, cr))))
        if (u @ v) < 0:
            turn = math.copysign(180.0 - abs(turn), turn)
        if abs(turn) < sharp_deg:
            continue
        left = (turn > 0) == ccw                              # a turn toward the inside of the ring polygon
        internal = (not left) if not hole else left           # outline: reflex vertex; cut-out: convex vertex of the cut-out
        out.append((float(b[0]), float(b[1]), abs(turn), internal))
    return out


def check_fr4_plate(parts, legend_blocks=None):
    """The primary base plate is routed and drilled by a PCB fabricator: it must be a constant-section (2.5 D) plate of
    the YAML thickness whose internal corners all have at least the router radius, with webs and edge distances a
    fabricator accepts.  Everything is measured on the plate solid (typed section edges and the section polygon).
    E10: the legend of the outer face (cad/legend.py; legend_blocks overrides its blocks, for the self-test) is written
    as a Gerber layer, read back, and its keep-clear distances are measured on what was read."""
    from shapely.geometry import Polygon as SPoly
    v = P.BASE_VARIANTS[P.BASE_PRIMARY]
    info = parts["base_plate"]
    plate = A.solid_of(info)
    fails, warns = [], []
    if v["printed"]:
        return res(15, "FR-4 base plate: fabrication rules", True, "not applicable: the primary base plate is printed", [], [], [])
    bb = A.bbox_of(info)                                      # tight box (x0, y0, z0, x1, y1, z1)
    t = bb[5] - bb[2]
    zs = (0.25 * t, 0.5 * t, 0.75 * t)
    secs = [G.section_polys(plate, "z", bb[2] + z, 2e-4) for z in zs]
    prof = secs[1]
    pg = max(getattr(prof, "geoms", [prof]), key=lambda g_: g_.area)
    prism = max(secs[0].symmetric_difference(prof).area, secs[2].symmetric_difference(prof).area)
    rules = []

    def rule(name, value, need, ok, note=""):
        if not ok:
            fails.append(f"{name}: {value} (required {need})")
        rules.append(dict(rule=name, measured=value, required=need, status="ok" if ok else "FAIL", note=note))
    rule("thickness (z extent of the solid)", R3(t), v["thickness"], abs(t - v["thickness"]) < 1e-6,
         f"finished thickness OVER THE MASK, tolerance +-{M['fr4_tol_thickness']} (fabricator standard below 1.0 mm); plates from {v['accept'][0]:.2f} to {v['accept'][1]:.2f} are used "
         f"(lower limit from the gap under the ball feet); the seal joint does not depend on it")
    rule("constant section through the thickness (routable and drillable from one side)", round(prism, 6), "0 mm2 difference between sections at 25 / 50 / 75 %", prism < 1e-6)
    rule("one piece", len(getattr(prof, "geoms", [prof])), 1, len(getattr(prof, "geoms", [prof])) == 1)
    # ---- features: every ring of the profile, typed from the exact section edges
    ents = G.section_edges(plate, "z", bb[2] + zs[1])
    circles = [(e[1], e[2]) for e in ents if e[0] == "circle"]
    arcs = [e for e in ents if e[0] == "arc"]
    frow, rings = [], [("outline", pg.exterior, False)]
    max_drill = 6.3
    for ring in pg.interiors:
        hp = SPoly(ring)
        c0 = hp.centroid
        circ = next(((c, r) for c, r in circles if math.hypot(c[0] - c0.x, c[1] - c0.y) < 1e-3 and abs(math.pi * r * r - hp.area) < 0.01 * math.pi * r * r), None)
        if circ and 2 * circ[1] <= max_drill:
            k = min(range(len(P.BALL_XY)), key=lambda i_: math.hypot(c0.x - P.BALL_XY[i_][0], c0.y - P.BALL_XY[i_][1]))
            nm, kind, size, tol = f"ball-foot hole {k + 1}", "drilled, NPTH", f"dia {2 * circ[1]:.2f}", f"+-{M['fr4_tol_hole']}"
        elif circ:
            nm, kind, size, tol = "grain opening", "routed, round", f"dia {2 * circ[1]:.2f}", f"+-{M['fr4_tol_outline']}"
        else:
            x0, y0, x1, y1 = hp.bounds
            nm, kind, size, tol = "pad slot", "routed slot, full-radius ends", f"{x1 - x0:.2f} x {y1 - y0:.2f}", f"+-{M['fr4_tol_outline']}"
        rings.append((nm, ring, True))
        frow.append(dict(feature=nm, how=kind, size_mm=size, centre_xy=(round(c0.x, 3), round(c0.y, 3)), tolerance_mm=tol, position_tolerance_mm=f"+-{M['fr4_tol_hole'] if 'drilled' in kind else M['fr4_tol_outline']}",
                         distance_to_the_outline_mm=R3(SPoly(ring).distance(pg.exterior))))
    x0, y0, x1, y1 = pg.bounds
    frow.insert(0, dict(feature="outline", how="routed", size_mm=f"R {P.BASE_R} about (0, 0), flat at y = {P.BASE_FLAT}; {x1 - x0:.2f} x {y1 - y0:.2f} overall", centre_xy=(0.0, 0.0),
                        tolerance_mm=f"+-{M['fr4_tol_outline']}", position_tolerance_mm="datum", distance_to_the_outline_mm="-"))
    n_drill = sum("drilled" in r["how"] for r in frow)
    rule("outline as in the YAML (x min, y min, x max, y max)", tuple(round(q, 3) for q in pg.bounds), (-P.BASE_R, -P.BASE_R, P.BASE_R, P.BASE_FLAT),
         all(abs(a_ - b_) < 1e-3 for a_, b_ in zip(pg.bounds, (-P.BASE_R, -P.BASE_R, P.BASE_R, P.BASE_FLAT))))
    rule("features: one grain opening, one pad slot, three drilled ball-foot holes", f"{len(pg.interiors)} cut-outs, {n_drill} drilled", "5 cut-outs, 3 drilled",
         len(pg.interiors) == 5 and n_drill == 3, "no integral baffle in the FR-4 plate: the opening is a plain round hole")
    holes_ok = all(abs(2 * r - P.BALL_HOLE_D) < 1e-6 for c, r in circles if 2 * r <= max_drill)
    rule("drilled hole diameter", sorted({round(2 * r, 3) for c, r in circles if 2 * r <= max_drill}), P.BALL_HOLE_D, holes_ok)
    # ---- internal corner radii: arcs whose centre lies in the removed region, and sharp re-entrant vertices
    crow, r_int = [], []
    for e in arcs + [("circle", c, r) for c, r in circles]:
        c, r = e[1], e[2]
        if e[0] == "arc":                                      # a point just inside the arc (toward its centre): material = convex outline, air = cutter radius
            am = math.radians(e[3] + 0.5 * ((e[4] - e[3]) % 360.0))
            internal = not pg.contains(Point(c[0] + (r - 0.01) * math.cos(am), c[1] + (r - 0.01) * math.sin(am)))
        else:
            internal = True                                    # a full circle in the profile is a hole
        where = "outline" if abs(math.hypot(c[0], c[1])) < 1e-6 and abs(r - P.BASE_R) < 1e-6 else ("pad slot end" if abs(c[1] - P.PAD_Y) < 1e-6 and abs(r - P.PAD_HOLE_D / 2) < 1e-6
                                                                                                   else ("grain opening" if abs(r - P.GRAIN_R) < 1e-6 else "ball-foot hole (drilled)"))
        if internal and "drilled" not in where:
            r_int.append(r)
        crow.append(dict(entity=e[0], where=where, centre_xy=(round(c[0], 3), round(c[1], 3)), radius_mm=R3(r), kind="internal (cutter or drill)" if internal else "external (convex outline)",
                         status="ok" if (not internal or r >= M["fr4_min_inner_radius"] - 1e-9) else "FAIL"))
    sharp = []
    for nm, ring, hole in rings:
        for x, y, turn, internal in _ring_corners(ring.coords, hole):
            sharp.append(dict(entity="sharp corner", where=nm, centre_xy=(round(x, 3), round(y, 3)), radius_mm=0.0,
                              kind=f"{'INTERNAL' if internal else 'external'} corner, direction change {turn:.0f} deg", status="FAIL" if internal else "ok (external corners may be sharp)"))
    crow += sharp
    n_int_sharp = sum(r["status"] == "FAIL" for r in sharp)
    rmin = min(r_int) if r_int else float("inf")
    rule("smallest internal corner radius on routed features", R3(rmin), f">= {M['fr4_min_inner_radius']}", rmin >= M["fr4_min_inner_radius"] - 1e-9,
         f"slot ends R {P.PAD_HOLE_D / 2}, grain opening R {P.GRAIN_R}: a dia {2 * min(rmin, 1.0):.1f} or smaller router bit")
    rule("sharp internal corners (would need a drilled relief)", n_int_sharp, 0, n_int_sharp == 0, f"{len(sharp)} sharp corners in all: the two ends of the flat, both external")
    # ---- webs between features and edge distances
    wrow = []
    wmin = (float("inf"), "")
    for i in range(len(rings)):
        for j in range(i + 1, len(rings)):
            d = rings[i][1].distance(rings[j][1])
            wrow.append(dict(between=rings[i][0], and_=rings[j][0], web_mm=R3(d), status="ok" if d >= M["fr4_min_web"] - 1e-9 else "FAIL"))
            if d < wmin[0]:
                wmin = (d, f"{rings[i][0]} to {rings[j][0]}")
    wrow.sort(key=lambda r: r["web_mm"])
    rule("smallest web or edge distance", f"{wmin[0]:.3f} ({wmin[1]})", f">= {M['fr4_min_web']}", wmin[0] >= M["fr4_min_web"] - 1e-9, "rule assumed, to be confirmed by the fabricator")
    # ---- fabrication data (Gerber profile, two mask layers, Excellon drill): generated from THIS solid, read back and compared with it
    import fabdata as FD
    import legend as L
    gen = FD.generate(plate, legend_blocks)
    grow, lrow, brow = [], [], []
    g_min, cap_all = float("nan"), 0
    try:
        prof = FD.parse_gerber(gen["profile"])
        poly = FD.profile_polygon(prof["segments"])
        dholes = FD.parse_excellon(gen["drill"])
        fine = G.section_polys(plate, "z", bb[2] + zs[1], 2e-5)
        a_solid = fine.area + sum(math.pi * d_ * d_ / 4 for *_q, d_ in dholes)       # the profile does not contain the drilled holes
        want = sorted((round(x_, 4), round(y_, 4)) for x_, y_ in P.BALL_XY)
        got = sorted((round(x_, 4), round(y_, 4)) for x_, y_, _d in dholes)
        ok_d = got == want and all(abs(d_ - P.BALL_HOLE_D) < 1e-6 for *_q, d_ in dholes) and len(circles) - 1 == len(dholes)
        rule("fabrication data: Excellon NPTH file read back", f"{len(dholes)} holes dia {sorted({d_ for *_q, d_ in dholes})} at {got}", f"3 x dia {P.BALL_HOLE_D} at the YAML positions", ok_d,
             FD.FILES["drill"])
        ok_p = poly is not None and abs(poly.area - a_solid) < 0.005 and len(poly.interiors) == len(pg.interiors) - len(dholes)
        rule("fabrication data: Gerber profile read back (area of the routed plate, routed cut-outs)", f"{poly.area:.3f} mm2, {len(poly.interiors)} cut-outs" if poly is not None else "no closed profile",
             f"{a_solid:.3f} mm2 (section of the solid + the drilled holes), {len(pg.interiors) - len(dholes)} cut-outs", ok_p, FD.FILES["profile"] + ": arcs as G03, units mm, 4.6 format")
        dm = P.BALL_HOLE_D + M["fr4_mask_relief"]
        ok_m = True
        for key in ("mask_top", "mask_bottom"):
            mk = FD.parse_gerber(gen[key])
            fl = sorted((round(x_, 4), round(y_, 4)) for x_, y_, _d in mk["flashes"])
            ok_m &= mk["negative"] and fl == want and all(abs(d_ - dm) < 1e-6 for *_q, d_ in mk["flashes"]) and not mk["segments"]
        rule("fabrication data: solder-mask layers read back (negative: only the three hole reliefs are open)", f"openings dia {dm:.2f} at the three holes: {ok_m}", f"dia {dm:.2f} = hole + {M['fr4_mask_relief']}",
             ok_m, f"{FD.FILES['mask_top']}, {FD.FILES['mask_bottom']}: no mask on the hole wall or rim (ball clearance {(P.BALL_HOLE_D - P.BALL_D) / 2:.3f} radial)")
        # ---- E10: legend of the outer face.  Written from cad/legend.py, read back; every distance below is measured on the ink
        #      that was READ (strokes with the width of their aperture) against the plate solid and the mask layer read back
        lg = FD.parse_gerber(gen["legend_bottom"])
        ink = FD.legend_shape(lg)
        blks = L.blocks() if legend_blocks is None else legend_blocks
        ink_model = L.geometry(blks)
        d_ink = ink.symmetric_difference(ink_model).area if ink is not None else float("nan")
        rule("fabrication data: legend layer of the outer face read back (ink = the blocks of cad/legend.py)",
             f"{ink.area:.2f} mm2 of ink in {len(lg['segments'])} strokes, apertures {sorted(set(lg['widths']))}; differs from the blocks by {d_ink:.5f} mm2" if ink is not None else "no ink",
             f"{ink_model.area:.2f} mm2, positive layer 'Legend,Bot'", ink is not None and d_ink < 1e-3 and lg["function"].startswith("Legend,Bot") and not lg["negative"],
             FD.FILES["legend_bottom"] + ": bottom layer given as seen from the top face (text mirrored in the file, correct on the part)")
        # ---- the legend is a BOTTOM layer: the file must be the mirror image (x -> -x) of the legend as it is read on the part.
        #      Two tests that do not go through legend.to_model(): (a) the ink read back, mirrored HERE, against the reading view
        #      built from the block strokes; (b) from the file and the model text alone: the first glyph of the model text lies at
        #      larger x than its last glyph (text that reads left to right on the underside runs right to left seen from the top)
        from shapely import affinity
        ink_read = L.reading_geometry(blks)
        d_mir = affinity.scale(ink, xfact=-1.0, yfact=1.0, origin=(0, 0)).symmetric_difference(ink_read).area if ink is not None else float("nan")
        d_same = ink.symmetric_difference(ink_read).area if ink is not None else float("nan")
        mb = next((b_ for b_ in blks if b_["name"] == "model" and b_["kind"] == "text"), None)
        order_ok, order_txt = False, "model text not found"
        if mb is not None and ink is not None:
            (cu, cv), hh, tx = mb["centre"], mb["h"], mb["text"]
            hw = abs(cu) + L.text_width(tx, hh, mb["stroke"]) / 2 + 0.5
            inb = ink.intersection(sbox(-hw, cv - hh / 2 - 0.3, hw, cv + hh / 2 + 0.3))
            gl = sorted((g_ for g_ in getattr(inb, "geoms", [inb]) if not g_.is_empty and g_.bounds[3] - g_.bounds[1] > 0.8 * hh), key=lambda g_: g_.bounds[0])
            gw = lambda ch_: (max(x_ for pl_ in L.FONT[ch_] for x_, _y in pl_) - min(x_ for pl_ in L.FONT[ch_] for x_, _y in pl_)) * hh / L.GLYPH_H + mb["stroke"]
            w_first, w_last = gw(tx[0]), gw(tx[-1])
            if len(gl) >= 2 and abs(w_first - w_last) > 0.2:
                w_lo, w_hi = gl[0].bounds[2] - gl[0].bounds[0], gl[-1].bounds[2] - gl[-1].bounds[0]
                order_ok = abs(w_hi - w_first) < 0.05 and abs(w_lo - w_last) < 0.05
                order_txt = (f"in the file the glyph at the largest x is {w_hi:.2f} wide ({tx[0]!r} is {w_first:.2f}), the one at the smallest x {w_lo:.2f} ({tx[-1]!r} is {w_last:.2f})")
            else:
                order_txt = "first and last glyph of the model text cannot be told apart by width"
        rule("legend layer is MIRRORED (bottom layer given as seen from the top face): file mirrored about x = 0 = the legend as read; first glyph of the model text at larger x than the last",
             f"mirrored file differs from the reading view by {d_mir:.5f} mm2 (un-mirrored it would differ by {d_same:.2f} mm2); {order_txt}",
             "0 mm2; first glyph at +x", ink is not None and d_mir < 1e-3 and d_same > 1.0 and order_ok,
             "independent of legend.to_model(): an un-mirrored file would read backwards on the part (the block layout is symmetric, so no keep-clear distance would show it)")
        # ---- clear space between separate pieces of ink (a narrower space fills in when printed): measured on the ink read back
        from shapely.strtree import STRtree
        pieces_ = [g_ for g_ in getattr(ink, "geoms", [ink]) if not g_.is_empty] if ink is not None else []
        tree_ = STRtree(pieces_) if pieces_ else None
        g_min, g_at, n_close = float("inf"), None, 0
        for i_, c_ in enumerate(pieces_):
            for j_ in tree_.query(c_.buffer(1.0)):
                if j_ > i_:
                    d_ = c_.distance(pieces_[j_])
                    n_close += d_ < M["legend_min_gap"] - NUM_TOL
                    if d_ < g_min:
                        g_min, g_at = d_, (0.5 * (c_.centroid.x + pieces_[j_].centroid.x), 0.5 * (c_.centroid.y + pieces_[j_].centroid.y))
        rule("legend print rules: smallest clear space between two separate pieces of ink (letter to letter, label to frame, block to block)",
             f"{g_min:.3f} mm" + (f" at x {g_at[0]:.1f}, y {g_at[1]:.1f}" if g_at else "") + f"; {len(pieces_)} pieces, {n_close} pair(s) closer than the rule",
             f">= {M['legend_min_gap']}", g_min >= M["legend_min_gap"] - NUM_TOL,
             f"legend ink gap: letters are pitched so that the space between them is at least the line width (cad/legend.py advance(): {L.letter_gap(M['legend_min_text_h']):.2f} mm at "
             f"{M['legend_min_text_h']} mm text, {L.advance(M['legend_min_text_h']):.3f} mm pitch); rule assumed equal to the least line width, to be confirmed with the quote")
        clear = M["legend_clear"]
        feats = [(nm + (" (drilled edge)" if "ball-foot" in nm else ""), SPoly(ring)) for nm, ring, hole in rings if hole]
        mkb = FD.parse_gerber(gen["mask_bottom"])
        feats += [(f"mask relief dia {d_:.2f} at ball-foot hole {1 + min(range(len(P.BALL_XY)), key=lambda i_: math.hypot(x_ - P.BALL_XY[i_][0], y_ - P.BALL_XY[i_][1]))} (mask layer read back)",
                   Point(x_, y_).buffer(d_ / 2, 128)) for x_, y_, d_ in mkb["flashes"]]
        for nm, shp in feats:
            d_ = ink.distance(shp)
            lrow.append(dict(legend_ink_to=nm, distance_mm=R3(d_), required_mm=clear, margin_mm=R3(d_ - clear), basis="YAML base_plate.legend.clear_of_features",
                             status="ok" if d_ >= clear - NUM_TOL else "FAIL"))
        outer = SPoly(pg.exterior)
        d_edge = pg.exterior.distance(ink) if outer.contains(ink) else -1.0
        lrow.append(dict(legend_ink_to="routed outline (ink inside the face)", distance_mm=R3(d_edge), required_mm=M["legend_edge_margin"], margin_mm=R3(d_edge - M["legend_edge_margin"]),
                         basis="mechanical-only: registration of a legend print", status="ok" if d_edge >= M["legend_edge_margin"] - NUM_TOL else "FAIL"))
        for i_, z_ in enumerate(L.seat_zones()):
            d_ = ink.distance(z_)
            lrow.append(dict(legend_ink_to=f"calibration seat zone dia {P.CAL_LEGEND_ZONE_D:.1f} round ball foot {i_ + 1}", distance_mm=R3(d_), required_mm=0.0, margin_mm=R3(d_),
                             basis="mechanical-only: the seat pads of plate GL1-050 bear on bare mask (D34)", status="ok" if d_ >= -1e-9 and not ink.intersects(z_) else "FAIL"))
        # fixtures that take the outer face as their reference bear on bare mask: gauge-plate bosses (step 2), seat pads of GL1-050
        # (step 19), feet of the bridge gauge (steps 11, 12, 14, 15), each grown by the play of its location
        reg = M["legend_registration"]
        for nm, shp in L.fixture_footprints().items():
            d_ = ink.distance(shp)
            lrow.append(dict(legend_ink_to="fixture footprint: " + nm, distance_mm=R3(d_), required_mm=reg, margin_mm=R3(d_ - reg),
                             basis="mechanical-only: fixtures bear on bare mask; registration of the legend print (D34)", status="ok" if d_ >= reg - NUM_TOL and not ink.intersects(shp) else "FAIL"))
        ser_ = next((b_ for b_ in blks if b_["name"] == "serial"), None)
        if ser_ is not None:
            box_ = sbox(-ser_["rect"][2], ser_["rect"][1], -ser_["rect"][0], ser_["rect"][3])      # the inside of the serial box in the model frame (mirrored here)
            d_, nn_ = min((box_.distance(shp), nm) for nm, shp in list(L.fixture_footprints().items()) + [(f"seat zone {i_ + 1}", z_) for i_, z_ in enumerate(L.seat_zones())])
            lrow.append(dict(legend_ink_to=f"(the serial number marked per unit inside its box, assembly step 13) to the nearest fixture footprint or seat zone: {nn_.split(' (')[0]}", distance_mm=R3(d_),
                             required_mm=reg, margin_mm=R3(d_ - reg), basis="mechanical-only: an ink-jet mark adds thickness on the seat face", status="ok" if d_ >= reg - NUM_TOL else "FAIL"))
        bad_l = [r_["legend_ink_to"] for r_ in lrow if r_["status"] != "ok"]
        rule(f"legend keep-clear: at least {clear} mm to ball-foot holes, mask reliefs, grain opening and pad slot; inside the outline; outside the seat zones; {reg} from every fixture footprint",
             f"smallest distance to a YAML feature {min(r_['distance_mm'] for r_ in lrow if 'YAML' in r_['basis'])} mm; {len(bad_l)} violation(s)" + (": " + "; ".join(bad_l) if bad_l else ""),
             f">= {clear} (YAML), edge >= {M['legend_edge_margin']}, seat zones clear, fixtures >= {reg}", not bad_l, "E10: legend of the outer face, measured on the legend layer read back")
        per = L.geometry(blks, by_block=True)
        names = [b_["name"] for b_ in blks]
        missing = [q for q in L.REQUIRED if not any(n_.startswith(q) for n_ in names)]
        texts = {b_["name"]: b_.get("text", "") for b_ in blks}
        h_min = min([b_["h"] for b_ in blks if b_["kind"] == "text"] + [b_.get("label_h", 9.0) for b_ in blks if b_["kind"] == "frame"])
        w_min = min(w_ for w_ in lg["widths"] if w_)
        ser = next((b_ for b_ in blks if b_["name"] == "serial"), None)
        ok_c = not missing and texts.get("model") == "GL-1" and texts.get("practice") == "PRACTICE DEVICE" and ser is not None
        rule("legend content (YAML base_plate.legend.content): maker, model 'GL-1', 'Practice device', statements block(s), serial-number box",
             f"blocks {names}; model text {texts.get('model')!r}; missing {missing or 'none'}", "all five kinds present; placeholders only where the text is not frozen", ok_c,
             (f"serial-number box {ser['rect'][2] - ser['rect'][0]:.1f} x {ser['rect'][3] - ser['rect'][1]:.1f} mm inside its frame" if ser else "") + "; the wording of the statements is not frozen (docs/COMPLIANCE.md rows 5 and 33)")
        rule("legend print rules: smallest text height / smallest line width", f"{h_min} / {w_min}", f">= {M['legend_min_text_h']} / >= {M['legend_stroke']}",
             h_min >= M["legend_min_text_h"] - 1e-9 and w_min >= M["legend_stroke"] - 1e-9, "fabricator rules for legend print, assumed: to be confirmed with the quote")
        free = outer.buffer(-M["legend_edge_margin"])
        for nm, shp in feats:
            free = free.difference(shp.buffer(clear))
        for z_ in L.seat_zones():
            free = free.difference(z_)
        for b_ in blks:
            g_ = per[b_["name"]]
            ext = L.block_extent(b_)
            dn, nn = min((g_.distance(shp), nm) for nm, shp in feats)
            cap = L.capacity(b_) if b_["kind"] == "frame" else None
            brow.append(dict(block=b_["name"], content=b_["content"], drawn=(repr(b_["text"]) if b_["kind"] == "text" else "frame + " + " / ".join(b_.get("label") or [])),
                             extent_as_read_u0_v0_u1_v1_mm=tuple(round(q, 2) for q in ext), size_mm=f"{ext[2] - ext[0]:.2f} x {ext[3] - ext[1]:.2f}",
                             text_height_mm=(b_["h"] if b_["kind"] == "text" else b_.get("label_h")), line_width_mm=b_["stroke"],
                             inside_of_the_frame_mm=(f"{b_['rect'][2] - b_['rect'][0]:.1f} x {b_['rect'][3] - b_['rect'][1]:.1f}" if b_["kind"] == "frame" else "-"),
                             capacity_at_the_smallest_text=(f"{cap[1]} lines of {cap[0]} characters at {M['legend_min_text_h']} mm" if cap else "-"),
                             nearest_feature=nn.split(" (")[0], distance_mm=R3(dn)))
        cap_all = sum(L.capacity(b_)[0] * L.capacity(b_)[1] for b_ in blks if b_["name"].startswith("statements"))
        notes_legend = [f"E10 legend (outer face): placeholder blocks from cad/legend.py; {ink.area:.1f} mm2 of ink; area of the outer face open to legend after every keep-clear: {free.area:.0f} mm2 of {pg.area:.0f}. "
                        f"The statement blocks hold about {cap_all} characters at {M['legend_min_text_h']} mm text height and {L.advance(M['legend_min_text_h']):.3f} mm pitch ({L.letter_gap(M['legend_min_text_h']):.2f} mm between "
                        f"letters): the short FCC sentence fits, the full two-condition statement (about 240 characters) "
                        "does not; whether it goes on the plate, on an e-label or in the manual and on the packaging is the open decision of docs/COMPLIANCE.md row 5",
                        "extents are given in the READING frame (the outer face seen from below with the visor at the top, u to the right): u = -x, v = y"]
        for key, text in gen.items():
            grow.append(dict(file="drawings/fab/" + FD.FILES[key], format=("Excellon, metric, decimal" if key == "drill" else "Gerber RS-274X, mm, 4.6"), bytes=len(text),
                             content={"profile": f"{len(prof['segments'])} segments: outline arc + flat, round opening, slot", "mask_top": "3 openings", "mask_bottom": "3 openings",
                                      "drill": f"{len(dholes)} NPTH holes, tool dia {P.BALL_HOLE_D:.3f}",
                                      "legend_bottom": f"legend of the outer face: {len(lg['segments'])} strokes in {len(blks)} placeholder blocks"}[key]))
    except Exception as ex:
        fails.append(f"fabrication data could not be generated or read back: {ex!r}")
        notes_legend = []
    land = P.BASE_R - P.LAND_RI
    notes = [f"material (YAML base_plate.material): {v['material']}; no copper; legend on the outer face only (YAML base_plate.legend: {P.Y['base_plate']['legend']['process']})",
             "fabrication data: drawings/fab/ holds a Gerber board profile (outline and routed cut-outs), two solder-mask layers, an Excellon NPTH drill file and the legend layer of the "
             "outer face, written by cad/fabdata.py from the plate solid and from cad/legend.py; the rules above read the same text back and compare it with the solid; build.py compares "
             "the files on disk with that text after the drawings are written",
             f"break-off tabs, if the fabricator panelises: on the flat only (land {P.BASE_FLAT - P.LAND_FLAT_IN:.2f} mm, no bore there), mouse bites recessed into the outline by at most "
             f"{M['fr4_tab_recess_max']} mm, no nub proud of the outline; on the arc the land is only {land:.2f} mm and the bore gap {P.CLR} mm",
             f"tolerances on the drawing GL1-011: outline and routed features +-{M['fr4_tol_outline']}, drilled holes +-{M['fr4_tol_hole']} (diameter and position), finished thickness over the mask "
             f"+-{M['fr4_tol_thickness']}; holes free of mask (relief dia {P.BALL_HOLE_D + M['fr4_mask_relief']:.2f})",
             f"the plate drops into the tub with {P.CLR} mm radial clearance and its top face carries the seal land ({land:.2f} mm on the arc, {P.BASE_FLAT - P.LAND_FLAT_IN:.2f} mm on the flat): "
             "no break-off nub may stand proud of the outline, and no V-score",
             "sharp corners are found on the section polygon (direction change above 15 deg between neighbouring edges; arcs are sampled to 0.0002 mm chord error); "
             "radii come from the exact arcs and circles of the section",
             f"area {pg.area:.1f} mm2, perimeter of the outline {pg.exterior.length:.1f} mm, routed length of the cut-outs "
             f"{sum(r.length for n_, r, h_ in rings[1:] if 'hole' not in n_):.1f} mm"] + notes_legend
    leg_sum = (f"; legend of the outer face ({len(brow)} placeholder blocks) read back, mirrored in the file as a bottom layer must be: {min(r_['distance_mm'] for r_ in lrow if 'YAML' in r_['basis'])} mm or more to "
               f"holes, mask reliefs, opening and slot (required {M['legend_clear']}), {min(r_['distance_mm'] for r_ in lrow if r_['legend_ink_to'].startswith('calibration seat zone'))} mm outside the seat zones, "
               f"{min(r_['distance_mm'] for r_ in lrow if r_['legend_ink_to'].startswith('fixture footprint'))} mm or more to the footprints of gauge plate, seat pads and bridge gauge; "
               f"smallest space between pieces of ink {g_min:.2f} mm (rule {M['legend_min_gap']}); statement blocks hold {cap_all} characters") if lrow else ""
    return res(15, "FR-4 base plate: fabrication rules", not fails,
               (f"0.80 mm plate of constant section, {n_drill} drilled dia {P.BALL_HOLE_D} holes, grain opening dia {P.GRAIN_D} and pad slot {P.PAD_SLOT_L} x {P.PAD_HOLE_D} routed; "
                f"smallest internal radius {rmin:.2f} mm (rule {M['fr4_min_inner_radius']}), no sharp internal corner; smallest web {wmin[0]:.2f} mm ({wmin[1]}; rule {M['fr4_min_web']})" + leg_sum
                if not fails else "FAILED: " + "; ".join(fails)),
               [dict(title="Fabrication rules", rows=rules), dict(title="Feature and drill table", rows=frow),
                dict(title="Corner radii and sharp corners", rows=crow), dict(title="Webs and edge distances", rows=wrow),
                dict(title="Legend of the outer face (E10): keep-clear distances measured on the legend layer read back", rows=lrow),
                dict(title="Legend blocks (placeholders)", rows=brow),
                dict(title="Fabrication data files (written with the drawings)", rows=grow)], notes, warns)


# ==============================================================================================
# 16. alternative base plate (printed PA12)
# ==============================================================================================
def check_alt_base(parts):
    """The all-printed build for the EVT comparison: the PA12 base plate with its 0.13 mm sheet, integral baffle, dia 1.15
    foot holes, 0.33 mm seal joint and its own pottings replaces the FR-4 set.  Everything else is the primary build, so
    only what the plate touches is re-checked: interference (all pairs with a base-specific part), the base-specific
    clearances (feet, baffle, potting, pad slot), wall thickness and trapped powder of the printed plate, the seal
    (air-solid test, joint height and volume, lands) and the mass."""
    if not any(i.group == "alt" for i in parts.values()):
        return res(16, "alternative base plate (printed PA12)", False, "FAILED: the alternative parts were not built", [], [], [])
    prim_mass = {r["part"]: r["mass_g"] for r in _mass_table(parts)}
    m_prim = sum(r["mass_g"] for r in _mass_table(parts) if r["group"] == "puck")
    fails, warns, notes = [], [], []
    with P.base_variant(P.BASE_ALT):
        vp = A.variant_view(parts)
        S = _solids(vp)
        v = P.BASE
        r1 = check_interference(vp, focus=set(A.BASE_SPECIFIC), cid=16, cname="interference")
        if not r1["passed"]:
            fails.append("interference: " + r1["summary"])
        warns += r1["warnings"]
        T = _Rows()
        _base_rows(vp, S, T)
        fails += [f"clearance: {f}" for f in T.fails]
        warns += T.warns
        wrows, thin5, wf, wnotes, wbits = _wall_audit(vp, ["base_plate"])
        fails += wf
        prow, nrow, pf, pnotes = _powder_audit(vp, ["base_plate"])
        fails += pf
        r13 = check_seal(vp, cid=16, cname="seal")
        if not r13["passed"]:
            fails.append("seal: " + r13["summary"])
        warns += r13["warnings"]
        mt = _mass_table(vp)
        m_alt = sum(r["mass_g"] for r in mt if r["group"] == "puck")
        cg = _cog(mt, "puck")
        tri = __import__("shapely.geometry", fromlist=["Polygon"]).Polygon(P.BALL_XY)
        inside = tri.contains(Point(cg[0], cg[1]))
        if not inside:
            fails.append("centre of gravity outside the ball-foot triangle")
        mrow = [dict(part=n, primary_build=parts[n].name if n in parts else "-", primary_mass_g=prim_mass.get(n, "-"),
                     alternative_build=vp[n].name, alternative_mass_g=next(r["mass_g"] for r in mt if r["part"] == vp[n].name)) for n in A.BASE_SPECIFIC]
        for n in A.PRIMARY_ONLY:
            mrow.append(dict(part=n, primary_build=n, primary_mass_g=prim_mass.get(n, "-"), alternative_build="not used (baffle integral with the plate)", alternative_mass_g=0.0))
        mrow.append(dict(part="MARKER TOTAL", primary_build=f"{len([i for i in parts.values() if i.group == 'puck'])} parts", primary_mass_g=round(m_prim, 2),
                         alternative_build=f"{len([i for i in vp.values() if i.group == 'puck'])} parts", alternative_mass_g=round(m_alt, 2)))
        mrow.append(dict(part="centre of gravity (alternative build)", primary_build="-", primary_mass_g="-", alternative_build=f"({cg[0]:.2f}, {cg[1]:.2f}, {cg[2]:.2f})",
                         alternative_mass_g=f"{tri.exterior.distance(Point(cg[0], cg[1])):.1f} mm inside the foot triangle"))
        s1, s2 = P.epoxy_volumes()
        joint = next(r for r in r13["tables"] if r["title"].startswith("Perimeter seal joint"))
        v_bead = S["seal_bead"].Volume()
        tmin = wbits[0] if wbits else ""
        notes += [f"alternative (YAML base_plate.alternative): {v['material']}; plate {P.BASE_T}, sheet {P.PSA_T} ({v['psa_material']}), foot holes dia {P.BALL_HOLE_D}, "
                  f"integral baffle ring dia {2 * P.BAFFLE_RI:.1f} / {2 * P.BAFFLE_RO:.1f} on spokes at {P.SPOKE_ANGLES} deg; seal joint {P.BEAD_T:.2f} mm",
                  "the check functions are the ones of the primary build, run with the base variant switched (params.base_variant); pairs and rows that do not involve "
                  "a base-specific part are identical to checks 1, 2 and 13 and are not repeated",
                  f"ball potting per foot: stage 1 {s1:.2f} mm3, stage 2 {s2:.2f} mm3 (primary build: see README)",
                  "EVT comparison of the two plates: tilt drift with temperature and humidity is to be MEASURED on both (README, test items); nothing here predicts it"] + wnotes + pnotes
        tables = [dict(title="Interference: every pair that involves a base-specific part", rows=r1["tables"][0]["rows"]),
                  dict(title="Base-specific clearances (plate, seal joint, ball feet, baffle, potting, pad slot)", rows=T.rows),
                  dict(title="Wall thickness of the printed plate (regions below the 0.8 mm rule)", rows=wrows),
                  dict(title="Trapped powder: voxel analysis of the printed plate", rows=prow),
                  dict(title="Open recesses narrower than 2 mm in the printed plate", rows=nrow)]
        potrow, (pw_lo, pw_hi, pw_tg) = _potting_table(S)
        tables.append(dict(title=f"Clear potting: volumes and levels (PA12 build: the integral ring has its crest on the base plane; accepted z {pw_lo:.2f} to {pw_hi:.2f}, target z {pw_tg:.3f})",
                           rows=potrow))
        tables += [dict(title="Seal: " + t["title"], rows=t["rows"]) for t in r13["tables"]]
        tables.append(dict(title="Mass: base-specific parts and marker total, primary against alternative", rows=mrow))
        summary = (f"PA12 plate {P.BASE_T} mm + sheet {P.PSA_T} mm: no interference ({r1['summary'].split(';')[0].replace('no unintended interference in ', '')}); "
                   f"{len(T.rows)} base-specific clearances met (ball in its hole {(P.BALL_HOLE_D - P.BALL_D) / 2:.3f}, photodiode to ring {P.BAFFLE_RI - P.PD_HALF_DIAG:.3f}); "
                   f"{tmin}, no trapped powder; seal joint {P.BEAD_T:.2f} mm, {v_bead:.1f} mm3 (dispense {P.seal_dispense_volume(v_bead, joint['rows'][3]['value'])[1]:.0f}), closed; "
                   f"plates sorted to {v['accept'][0]:.2f} .. {v['accept'][1]:.2f} mm; marker {m_alt:.2f} g (primary {m_prim:.2f} g)")
    return res(16, "alternative base plate (printed PA12)", not fails, summary if not fails else "FAILED: " + "; ".join(fails), tables, notes, warns)


# ==============================================================================================
# 17. board import
# ==============================================================================================
def check_board_import(parts, path=None, data=None):
    """The real circuit board against the YAML and the tub (cad/board_import.py).  Skipped, and passed, while the board
    file does not exist."""
    import board_import as B
    r = B.check_board(parts, path=path, data=data)
    return res(17, "board import (electrical/gl1_main)", r["passed"], r["summary"], r["tables"], r["notes"], r["warnings"])


# ==============================================================================================
# 18. calibration seat plates (fixtures of the two-seat level zero, E11)
# ==============================================================================================
def check_cal_plates(parts):
    """The two calibration seat plates of drawing GL1-050 against the marker solids, in both nests (the marker as
    modelled = nest A; turned 180 deg about the plate centre = nest B).  BASE-FACE seat plate: the base plate rests on
    the three annular seat pads and on nothing else, every ball hangs free in its pocket, the visor flat lies against
    the datum fence above the relief of its foot and the round wall touches the side stop.  BALL seat plate: the three
    balls stand on the plain face.  Fixtures are not product parts: this check proves that the drawn fixtures do what
    the two-seat zero (DESIGN_SPEC section 6, E11) needs; nothing has been made."""
    from shapely.geometry import Polygon as SPoly
    import legend as L
    name = "fixtures on the outer face: calibration seat plates (E11), ball gauge plate, bridge gauge"
    if "cal_seat_plate" not in parts or "cal_plain_plate" not in parts or "gauge_plate" not in parts:
        return res(18, name, False, "FAILED: the seat plates or the ball gauge plate were not built", [], [], [])
    S = _solids(parts)
    c = P.CAL
    seat = S["cal_seat_plate"]
    plain = S["cal_plain_plate"].translate(cq.Vector(0, 0, -P.BALL_PROT))        # in the marker frame the balls stand on its top face
    balls = [n for n in parts if n.startswith("ball_") and not n.startswith("ball_epoxy_")]
    outside = ["tub", "base_plate", "seal_bead", "grain_potting"] + balls + [n for n in parts if n.startswith("ball_epoxy_") and parts[n].group == "puck"]
    cen = cq.Vector(P.CAL_CENTRE[0], P.CAL_CENTRE[1], 0.0)
    T = _Rows()
    add = T.add
    zc = 0.5 * (c["fence_relief"][1] + c["fence_h"])                             # a level inside the contact band of the fence
    st = P.stack_tolerance(printed=M["tol_printed"])["rim"]
    prow, areas = [], {}
    r_cap = math.sqrt(max(0.0, (P.BALL_D / 2) ** 2 - (P.BALL_D / 2 - (P.BALL_PROT + M["tol_ball_set"])) ** 2))   # ball cap at the seat plane, ball set high
    for nest in ("A", "B"):
        turn = (lambda sh: sh) if nest == "A" else (lambda sh: sh.rotate(cen, cen + cq.Vector(0, 0, 1), 180))
        m = {n: turn(S[n]) for n in outside}
        base, tub = m["base_plate"], m["tub"]
        tag = f"nest {nest}"
        # ---------------- base-face seat plate
        v_max, n_max = max((common_volume(m[n], seat), n) for n in outside)
        add(f"{tag}, base-face seat: interference of the marker with the plate (mm3, negated)", -v_max, -INTERFERENCE_LIMIT_MM3, method="boolean common, every outside part of the marker",
            note=f"largest: {n_max}")
        add(f"{tag}, base-face seat: base plate on the seat pads (gap)", min_distance(base, seat), 0.0, nominal=0.0, note="contact: the pad tops are the marker base plane")
        pads = G.section_polys(seat, "z", P.CAL_SEAT_Z - 1e-3, 2e-4)
        face = G.section_polys(base, "z", 1e-3, 2e-4)
        foot = SPoly(max(getattr(face, "geoms", [face]), key=lambda g_: g_.area).exterior)   # the outline of the base plate
        under = pads.intersection(foot)                                            # plate material that reaches the seat plane under the base plate
        on = [g_ for g_ in getattr(under, "geoms", [under]) if not g_.is_empty and g_.area > 0.01]
        contact = [g_.intersection(face).area for g_ in on]
        d_edge = min((foot.exterior.distance(g_) if foot.contains(g_) else -1.0) for g_ in on) if on else float("nan")
        add(f"{tag}, base-face seat: number of seat pads under the base plate", float(len(on)), 3.0, nominal=3.0, method="section of the plate at the seat plane",
            note="three pads and nothing else of the plate reach the seat plane under the marker")
        add(f"{tag}, base-face seat: smallest contact area of a pad on the FR-4 face (mm2)", min(contact) if contact else float("nan"), 10.0,
            method="pad section INTERSECT base-plate section", note=f"areas {', '.join(f'{a_:.1f}' for a_ in sorted(contact))} mm2 (a full annulus dia {c['pad_od']} / {c['pocket_dia']} is "
            f"{math.pi * (c['pad_od'] ** 2 - c['pocket_dia'] ** 2) / 4:.1f}; the pads are trimmed at the plate edge)")
        add(f"{tag}, base-face seat: seat pads inside the base plate outline by", d_edge, M["legend_edge_margin"], nominal=M["legend_edge_margin"], method="pad sections against the plate outline",
            note="no pad reaches under the seal fillet at the plate edge or under the tub rim")
        areas[nest] = contact
        for bn in balls:
            b = m[bn]
            bb = b.BoundingBox()
            bx, by = 0.5 * (bb.xmin + bb.xmax), 0.5 * (bb.ymin + bb.ymax)
            d3 = min_distance(b, seat)
            zs_ = -0.5 * P.BALL_PROT
            rad = _sec_dist(b, seat, "z", zs_, clip=(bx - 3, by - 3, bx + 3, by + 3))
            prow.append(dict(nest=nest, ball=bn, centre_xy=(round(bx, 3), round(by, 3)), pocket=f"dia {c['pocket_dia']} x {c['pocket_depth']} deep",
                             ball_to_plate_3d_mm=R3(d3), under_the_ball_mm=R3(c["pocket_depth"] - P.BALL_PROT), radial_at_z_mm=(zs_, R3(rad)),
                             radial_to_the_cap_of_a_ball_set_high_mm=R3(c["pocket_dia"] / 2 - r_cap), location_allowance_mm=c["locate_tol"],
                             status="ok" if (d3 >= P.CLR - NUM_TOL and c["pocket_dia"] / 2 - r_cap >= c["locate_tol"] + P.CLR - NUM_TOL) else "FAIL"))
        d_b = min(r_["ball_to_plate_3d_mm"] for r_ in prow if r_["nest"] == nest)
        add(f"{tag}, base-face seat: ball foot to its pocket, nearest (the floor under it)", d_b, P.CLR, nominal=c["pocket_depth"] - P.BALL_PROT,
            note=f"pocket {c['pocket_depth']} deep: {c['pocket_depth'] - (P.BALL_PROT + M['tol_ball_set']):.2f} under a ball set {M['tol_ball_set']} high")
        add(f"{tag}, base-face seat: pocket wall to the cap of a ball set high, radial, less the location allowance", c["pocket_dia"] / 2 - r_cap - c["locate_tol"], P.CLR,
            method="arithmetic on the pocket of the solid", note=f"cap radius at the seat plane {r_cap:.3f} (protrusion {P.BALL_PROT + M['tol_ball_set']:.2f}); a ball may sit up to {c['locate_tol']} off its pocket centre "
            f"(fence and stop to the tub wall, bore gap {P.CLR}, plate outline +-{M['fr4_tol_outline']}, hole +-{M['fr4_tol_hole']}, printed wall)")
        # location: visor flat on the fence, round wall on the side stop
        ps, ts = G.section_polys(seat, "z", zc, 2e-4), G.section_polys(tub, "z", zc, 2e-4)
        pieces = sorted((g_ for g_ in getattr(ps, "geoms", [ps]) if not g_.is_empty), key=lambda g_: -g_.area)
        fence = pieces[0]
        pin = min(pieces[1:], key=lambda g_: g_.distance(ts)) if len(pieces) > 1 else None
        touch = ts.buffer(1e-4).intersection(fence.exterior).length
        add(f"{tag}: visor flat against the datum fence (gap at z {zc:.1f})", ts.distance(fence), 0.0, nominal=0.0, method=f"sections z = {zc:.2f}")
        add(f"{tag}: length of the visor flat on the fence", touch, 2 * P.HORN_X_OUT - 0.5, nominal=2 * P.HORN_X_OUT, method="tub section against the fence face",
            note=f"contact band z {c['fence_relief'][1]} to {c['fence_h']} above the seat plane: below the window recesses (z {P.WIN_Z0}), above the seal joint at the foot of the visor wall")
        add(f"{tag}: round wall against the side stop pin (gap)", ts.distance(pin) if pin is not None else float("nan"), 0.0, nominal=0.0, method=f"sections z = {zc:.2f}",
            note=f"pin dia {c['pin_dia']} at the marker's -x side: with the fence it fixes x, y and the rotation")
        zl = 0.5 * (P.LEDGE_Z0 + c["fence_relief"][1])
        low = G.section_polys(seat, "z", zl, 2e-4)
        mk = [G.section_polys(m[n], "z", zl, 2e-4) for n in ("tub", "base_plate", "seal_bead")]
        fl = max((g_ for g_ in getattr(low, "geoms", [low]) if not g_.is_empty), key=lambda g_: g_.area)
        add(f"{tag}: relief at the foot of the fence, to the marker (z {zl:.2f})", min(g_.distance(fl) for g_ in mk if not g_.is_empty), c["fence_relief"][0] - 0.01, nominal=c["fence_relief"][0],
            method=f"sections z = {zl:.2f}", note="room for the seal fillet under the visor wall")
        rim = min_distance(tub, seat.intersect(PT.box(-200, 200, -200, 200, -50, P.CAL_SEAT_Z - c["relief"] + 1e-6).val()))
        add(f"{tag}, base-face seat: tub rim above the relieved face of the plate", rim, st["worst"], nominal=P.RIM_Z + c["relief"],
            note=f"rim relief {P.RIM_Z} + relief {c['relief']} (the pads end {M['legend_edge_margin']} inside the plate outline, so none lies under the rim); the rim-relief chain is "
                 f"+-{st['worst']:.2f} worst case with the tub at +-{M['tol_printed']}")
        # ---------------- ball seat plate
        v_pl, n_pl = max((common_volume(m[n], plain), n) for n in outside)
        add(f"{tag}, ball seat: interference of the marker with the plain plate (mm3, negated)", -v_pl, -INTERFERENCE_LIMIT_MM3, method="boolean common", note=f"largest: {n_pl}")
        add(f"{tag}, ball seat: the three balls on the plain face (largest gap)", max(min_distance(m[bn], plain) for bn in balls), 0.0, nominal=0.0)
        add(f"{tag}, ball seat: base plate above the plain face", min_distance(base, plain), P.BALL_PROT, nominal=P.BALL_PROT)
        pps = G.section_polys(plain, "z", zc, 2e-4)
        pf = max((g_ for g_ in getattr(pps, "geoms", [pps]) if not g_.is_empty), key=lambda g_: g_.area)
        add(f"{tag}, ball seat: visor flat against the datum fence (gap at z {zc:.1f})", ts.distance(pf), 0.0, nominal=0.0, method=f"sections z = {zc:.2f}")
    # ---------------- ball gauge plate (assembly step 2): the base plate lies on it OUTER FACE DOWN, so the legend lies between them.
    #                  Plate frame = marker frame, boss tops at z = 0.  Everything is measured on the gauge-plate solid
    gq = P.GAUGE
    gauge = S["gauge_plate"]
    base0 = S["base_plate"]
    ink = L.geometry()
    grc = G.RayCaster(gauge)
    GT = _Rows()
    gadd = GT.add
    gadd("Ball gauge plate: base plate on the gauge plate (gap)", min_distance(base0, gauge), 0.0, nominal=0.0, note="contact on the boss tops: they are the plane the protrusion is set from")
    gsec = G.section_polys(gauge, "z", -1e-3, 2e-4)
    face0 = G.section_polys(base0, "z", 1e-3, 2e-4)
    foot0 = SPoly(max(getattr(face0, "geoms", [face0]), key=lambda g_: g_.area).exterior)
    under0 = gsec.intersection(foot0)
    lands = [g_ for g_ in getattr(under0, "geoms", [under0]) if not g_.is_empty and g_.area > 0.01]
    gadd("Ball gauge plate: pieces of the plate that reach the outer face of the base plate (bosses)", float(len(lands)), 3.0, nominal=3.0, method="section of the gauge plate just below the boss tops",
         note="three bosses and nothing else: a plain plate would be one piece and would carry the base plate on its legend")
    gadd("Ball gauge plate: smallest contact area of a boss on the FR-4 face (mm2)", min((g_.intersection(face0).area for g_ in lands), default=float("nan")), 10.0, method="boss section INTERSECT base-plate section",
         note=f"boss dia {gq['boss_od']} round a gauge hole; the boss face closes the bottom of the dia {P.BALL_HOLE_D} hole annulus (it dams the stage 1 epoxy)")
    pts_ink = [(g_.representative_point().x, g_.representative_point().y) for g_ in getattr(ink, "geoms", [ink]) if not g_.is_empty]
    drop = min((grc.first_hit((x_, y_, 1e-6), (0, 0, -1), 1e-9, 5.0) or 0.0) for x_, y_ in pts_ink)
    gadd(f"Ball gauge plate: room under the legend ink (ink up to {M['legend_ink_t_max']} thick), smallest", drop - M["legend_ink_t_max"], 0.05, nominal=gq["relief"] - M["legend_ink_t_max"],
         method=f"ray -z from the outer face at a point of each of the {len(pts_ink)} pieces of legend ink", note=f"the plate face outside the bosses lies {gq['relief']} below the boss tops: the legend never touches the gauge plate")
    d_boss = min(ink.distance(g_) for g_ in lands) if lands else float("nan")
    gadd("Ball gauge plate: legend ink to the nearest boss, less the location of the plate on its three balls", d_boss - gq["locate_tol"], M["legend_registration"], method="legend blocks against the boss sections",
         note=f"the base plate is located by its three balls in the gauge holes (+-{gq['locate_tol']}); required: the registration of the legend print ({M['legend_registration']})")
    hsec = G.section_polys(gauge, "z", -0.5 * min(gq["hole_depth"], gq["relief"]), 2e-4)       # through the bosses (or the plain face), inside the gauge holes
    hholes = [SPoly(r_) for g_ in getattr(hsec, "geoms", [hsec]) if not g_.is_empty for r_ in g_.interiors]
    hrow = []
    for bn in balls:
        bb_ = S[bn].BoundingBox()
        bx, by = 0.5 * (bb_.xmin + bb_.xmax), 0.5 * (bb_.ymin + bb_.ymax)
        ring_ = min(hholes, key=lambda h_: math.hypot(h_.centroid.x - bx, h_.centroid.y - by), default=None)
        d_h = (ring_.bounds[2] - ring_.bounds[0]) if ring_ is not None and math.hypot(ring_.centroid.x - bx, ring_.centroid.y - by) < 0.05 else float("nan")
        prot = P.gauge_protrusion(d_h) if d_h == d_h else float("nan")
        v_b, d_b3 = common_volume(S[bn], gauge), min_distance(S[bn], gauge)
        hrow.append(dict(ball=bn, centre_xy=(round(bx, 3), round(by, 3)), gauge_hole_dia_on_the_solid_mm=R3(d_h), protrusion_of_a_dia_1p000_ball_on_its_rim_mm=R3(prot),
                         required_mm=f"{P.BALL_PROT} +-{M['tol_ball_set']}", ball_of_the_model_to_the_plate_mm=R3(d_b3), interference_mm3=round(v_b, 6),
                         protrusion_of_an_oversize_grade_100_ball_mm=(R3(P.gauge_protrusion(d_h, P.BALL_D + M["ball_dia_tol"])) if d_h == d_h else None),
                         status="ok" if (prot == prot and abs(prot - P.BALL_PROT) < 1e-3 and d_b3 < 2e-3 and v_b < INTERFERENCE_LIMIT_MM3) else "FAIL"))
    perr = max((abs(P.gauge_protrusion(r_["gauge_hole_dia_on_the_solid_mm"]) - P.BALL_PROT) if r_["gauge_hole_dia_on_the_solid_mm"] is not None and r_["gauge_hole_dia_on_the_solid_mm"] == r_["gauge_hole_dia_on_the_solid_mm"]
                else float("nan")) for r_ in hrow) if hrow else float("nan")
    gadd("Ball gauge plate: protrusion set by the three gauge holes, largest error against the YAML protrusion (negated)", -perr, -1e-3,
         method="hole diameter measured on the section of the gauge plate", note=f"a dia {P.BALL_D} ball on the rim of a dia {P.GAUGE_HOLE_D:.2f} hole stands {P.BALL_PROT} below the boss top")
    # ---------------- bridge gauge (depth readings of steps 11, 12, 14, 15): three annular feet round the balls; requirement, not a solid
    bq = P.BRIDGE
    foot_reach = bq["foot_od"] / 2 + P.BRIDGE_FOOT_PLAY
    d_foot = min(ink.distance(Point(x_, y_).buffer(foot_reach, 128)) for x_, y_ in P.BALL_XY)
    gadd("Bridge gauge: legend ink to the footprint of its feet (foot + play on the ball), smallest", d_foot, M["legend_registration"],
         method="legend blocks against the foot circles", note=f"annular feet dia {bq['foot_od']} / {bq['foot_bore']} round the three balls; a bore on the cap of a ball set low centres the foot within {P.BRIDGE_FOOT_PLAY:.2f}")
    gadd("Bridge gauge: foot bore clear of the mask relief of a ball-foot hole, radial", (bq["foot_bore"] - (P.BALL_HOLE_D + M["fr4_mask_relief"])) / 2, 0.1, method="arithmetic",
         note="the feet rest on solder mask, not on the bare ring of laminate round each hole")
    tub_rc = G.RayCaster(S["tub"])
    rims = []
    for az in bq["rim_station_deg"]:
        x_, y_ = bq["rim_station_r"] * math.cos(math.radians(az)), bq["rim_station_r"] * math.sin(math.radians(az))
        h_ = tub_rc.first_hit((x_, y_, -1.0), (0, 0, 1), 1e-9, 5.0)
        rims.append((az, (h_ - 1.0) if h_ is not None else float("nan")))
    gadd("Bridge gauge: its four rim stations lie on the flat of the tub rim (rim height read there, worst deviation from the rim relief, negated)",
         -max(abs(z_ - P.RIM_Z) if z_ == z_ else float("nan") for _a, z_ in rims), -1e-6, method="ray +z onto the tub solid at each station",
         note=f"stations at r {bq['rim_station_r']} (rim flat r {P.RIM_FLAT_R[0]} to {P.RIM_FLAT_R[1]}), azimuth {', '.join(f'{a_:.0f}' for a_, _z in rims)} deg from +x: rim at z "
              f"{', '.join(f'{z_:.3f}' for _a, z_ in rims)}; the reading of steps 14 and 15 is this height below the plane of the three feet")
    d_mask = min(math.hypot(x_ - P.GRAIN_X, y_ - P.GRAIN_Y) for x_, y_ in P.BALL_XY) - foot_reach - bq["mask_od"] / 2
    gadd("Bridge gauge: its feet clear of the low-tack potting mask (step 12), radial", d_mask, 0.5, method="arithmetic on the foot positions",
         note=f"mask = an annulus dia {2 * P.GRAIN_R + 2.0:.0f} to {bq['mask_od']} centred on the grain opening: the three seat zones stay bare for the wet level check")
    T.rows += GT.rows; T.fails += GT.fails; T.warns += GT.warns
    gfail = [f"{r_['ball']} on the gauge plate" for r_ in hrow if r_["status"] != "ok"]
    # legend ink against the seat pads (nest A = the marker frame)
    padsA = G.section_polys(seat, "z", P.CAL_SEAT_Z - 1e-3, 2e-4).intersection(sbox(-P.BASE_R, -P.BASE_R, P.BASE_R, P.BASE_FLAT))
    add("Legend ink of the outer face to the nearest seat pad", ink.distance(padsA), c["locate_tol"] + c["legend_zone_margin"], method="legend blocks against the pad sections",
        note=f"a legend print stands about {M['legend_ink_t']} mm proud of the mask: the pads must bear on bare mask wherever the marker sits inside its location allowance (D34)")
    cg = _cog(_mass_table(parts), "puck")
    tri = SPoly(P.BALL_XY)
    add("Marker centre of gravity inside the triangle of the three seat pads / balls", tri.exterior.distance(Point(cg[0], cg[1])) if tri.contains(Point(cg[0], cg[1])) else -1.0, 2.0,
        method="mass table of check 8", note="the marker lies stable on either plate without a clamp; no spring pin may touch it while the zero is read")
    span = min(math.hypot(P.BALL_XY[i][0] - P.BALL_XY[j][0], P.BALL_XY[i][1] - P.BALL_XY[j][1]) for i in range(3) for j in range(i))
    hgt = tri.area * 2 / max(math.hypot(P.BALL_XY[i][0] - P.BALL_XY[j][0], P.BALL_XY[i][1] - P.BALL_XY[j][1]) for i in range(3) for j in range(i))
    frow = [dict(requirement="plate blank", value=f"{c['plate'][0]} x {c['plate'][1]} x {c['plate'][2]} mm", basis="two nests either side of the fence; marker dia 46 + stop pin + handling margin"),
            dict(requirement="seat pads: six pad tops in one plane", value=f"{c['coplanar']} mm", basis=f"a height error of {c['coplanar']} mm at one pad is {1000 * c['coplanar'] / hgt:.3f} mrad over the "
                 f"{hgt:.1f} mm height of the foot triangle (target of the tilt chain 0.5 to 1 mrad)"),
            dict(requirement="plain plate: flatness of the top face", value=f"{c['flat_plain']} mm over each nest", basis="same tilt error; the balls are 33.0 and 25.8 mm apart"),
            dict(requirement="reversal between the nests", value="no parallelism of the plate needed", basis="both nests lie in one lapped plane: reading in nest A, then turned 180 deg in nest B, "
                 "cancels the tilt of the plate and of the table under it; what remains is half the difference in tilt between the two nests (bounded by the coplanarity above)"),
            dict(requirement="fence: datum faces square to the seat plane, parallel to each other", value=f"{c['fence_square']} mm", basis=f"yaw of the marker {math.degrees(math.atan(c['fence_square'] / (2 * P.HORN_X_OUT))):.3f} deg "
                 f"over the {2 * P.HORN_X_OUT:.1f} mm flat (the reversal needs the half turn only to about 1 deg; the display-rotation measurement, E12, needs 0.1 deg)"),
            dict(requirement="pocket", value=f"dia {c['pocket_dia']} x {c['pocket_depth']} deep", basis=f"ball cap dia {2 * r_cap:.2f} at the seat plane when set {M['tol_ball_set']} high; mask relief dia "
                 f"{P.BALL_HOLE_D + M['fr4_mask_relief']:.2f}; location allowance {c['locate_tol']}; depth = {c['pocket_depth'] / (P.BALL_PROT + M['tol_ball_set']):.1f} x the largest protrusion"),
            dict(requirement="seat pad", value=f"annulus dia {c['pad_od']} / {c['pocket_dia']}, {c['relief']} proud of the plate face", basis=f"bare mask next to each foot; legend-free zone dia {P.CAL_LEGEND_ZONE_D:.1f} "
                 f"on the base plate (pad + 2 x ({c['locate_tol']} + {c['legend_zone_margin']}))"),
            dict(requirement="contacts", value="none on either plate", basis=f"a spring pin pushes with {P.PIN_FORCE_N} N against a marker weight of about 0.12 N: the zero is read without contact "
                 "(started from the menu, or armed in the pogo fixture and run after the marker has come to rest on the plate)"),
            dict(requirement="positions of the level zero", value="0 and 180 deg only (nest A, nest B)", basis="the fence takes the visor flat: a four-position zero (0, 90, 180, 270 deg; docs/MANUFACTURING_PLAN.md "
                 "6.2 and 6.7, for production) cannot be run on these plates: it needs a location on the round wall (three pins) instead of the fence. Not designed"),
            dict(requirement="BALL GAUGE PLATE (step 2): bosses", value=f"3 x dia {gq['boss_od']}, tops ground in one plane within 0.005, {gq['relief']} proud of the plate face", basis=f"inside the legend-free zones dia "
                 f"{P.CAL_LEGEND_ZONE_D:.1f} with the location on the balls (+-{gq['locate_tol']}) and the print registration ({M['legend_registration']}); the legend (up to {M['legend_ink_t_max']}) never touches the plate"),
            dict(requirement="BALL GAUGE PLATE: gauge holes", value=f"3 x dia {P.GAUGE_HOLE_D:.2f} +0.005 / 0 reamed, {gq['hole_depth']} deep, sharp burr-free rim, at the ball-foot positions +-0.02",
                 basis=f"a dia {P.BALL_D} ball on the rim stands {P.BALL_PROT} below the boss top; +0.01 on the hole diameter is +{P.gauge_protrusion(P.GAUGE_HOLE_D + 0.01) - P.BALL_PROT:.4f} of protrusion"),
            dict(requirement="BALL GAUGE PLATE: clamp", value=f"a weight with three annular feet over the bosses (dia {gq['boss_od']} / dia 3), open above each hole", basis="the load passes straight through the plate into the "
                 "bosses: a flat weight would bend the 0.8 mm plate between its three supports"),
            dict(requirement="BRIDGE GAUGE (steps 11, 12, 14, 15): feet", value=f"3 annular feet dia {bq['foot_od']} / {bq['foot_bore']} at the ball-foot positions, {bq['foot_h']} proud, lapped in one plane within 0.002",
                 basis="every depth reading on the underside (ring crest, potting level, rim relief) is taken from the bare mask round the three feet: the plane of the seat pads of GL1-050 and of the gauge-plate bosses. "
                       "NOT drawn: a requirement"),
            dict(requirement="BRIDGE GAUGE: stations", value=f"indicator bores over the grain opening (centre and four points at r 5 outside the ring) and at four rim stations r {bq['rim_station_r']}, "
                 + ", ".join(f"{a_:.0f}" for a_ in bq["rim_station_deg"]) + " deg", basis=f"rim flat r {P.RIM_FLAT_R[0]} to {P.RIM_FLAT_R[1]}; zeroed on a flat plate; contact tip dia 2 (dia 1 on the ring crest, 0.8 wide)")]
    fails = list(T.fails) + [f"{r_['ball']} in nest {r_['nest']}" for r_ in prow if r_["status"] != "ok"] + gfail
    notes = ["fixtures, not product parts: drawing GL1-050; solids exported as cal_seat_plate.step and cal_plain_plate.step (the plain plate in its own frame, top face z = 0)",
             "ball gauge plate: solid exported as gauge_plate.step, drawn in the detail of GL1-011 sheet 1. The outer face of the base plate carries the legend (E10), so this plate bears on three "
             f"bosses inside the legend-free zones, not on its whole face: a print of {M['legend_ink_t']} to {M['legend_ink_t_max']} mm under a flat plate would add itself to the ball protrusion "
             f"({P.BALL_PROT} +-{M['tol_ball_set']}) and take the same amount from the epoxy between ball and land (D34)",
             "bridge gauge: not a solid of this model; its footprint (three annular feet round the balls), its rim stations and the potting mask are checked as geometry against the legend and the tub. "
             "No depth gauge rests on printed legend: one that bridged the grain opening on the legend (1.2 mm from the opening) would read the ring crest and the potting level up to "
             f"{M['legend_ink_t_max']} mm deep against a never-below limit of {P.GRAIN_FILL_Z}",
             f"plate frame = marker frame of nest A (the marker as modelled); nest B = nest A turned 180 deg about ({P.CAL_CENTRE[0]}, {P.CAL_CENTRE[1]}), the middle of the fence. "
             f"Fence faces at y = {P.CAL_FENCE_Y0} and {P.CAL_FENCE_Y1}; side stops at ({P.CAL_PIN_XY[0]}, {P.CAL_PIN_XY[1]}) and its image",
             "base-face seat: E11 asks that the base face seats (the turf seat). The pads touch the FR-4 face in a ring round each foot, so the stored difference between the two seats is "
             "the difference between the plane of the face at the feet and the plane of the balls; a bowed laminate floats on turf on its mean plane, which three pads do not measure (D34)",
             "the six-face calibration needs pad contact in six orientations: that fixture is NOT designed (README, fixtures)"]
    return res(18, name, not fails,
               (f"base-face seat plate: the base plate rests on three pads per nest (contact {min(min(a_) for a_ in areas.values()):.1f} to {max(max(a_) for a_ in areas.values()):.1f} mm2 each), "
                f"balls {c['pocket_depth'] - P.BALL_PROT:.2f} clear of the pocket floors and {c['pocket_dia'] / 2 - r_cap:.2f} radially, visor flat on the fence over {2 * P.HORN_X_OUT:.1f} mm, "
                f"side stop touching, rim {P.RIM_Z + c['relief']:.2f} above the plate; ball seat plate: three balls on the plain face, base {P.BALL_PROT:.2f} above it; both nests, no interference. "
                f"Ball gauge plate: base plate on three bosses dia {gq['boss_od']} (legend {drop - M['legend_ink_t_max']:.2f} clear of the plate, {d_boss - gq['locate_tol']:.2f} from a boss), "
                f"gauge holes dia {P.GAUGE_HOLE_D:.2f} set {P.BALL_PROT:.2f} of protrusion; bridge gauge: feet {d_foot:.2f} from the legend, four rim stations on the rim flat"
                if not fails else "FAILED: " + "; ".join(fails)),
               [dict(title="Marker on the seat plates, both nests; base plate on the ball gauge plate; bridge gauge", rows=T.rows), dict(title="Ball feet in their pockets (base-face seat plate)", rows=prow),
                dict(title="Ball gauge plate: the three gauge holes, measured on the solid", rows=hrow),
                dict(title="Requirements on the fixtures (GL1-050, ball gauge plate, bridge gauge) and their basis", rows=frow)], notes, T.warns)


CHECKS = [check_interference, check_clearances, check_fov, check_fold, check_walls, check_trapped, check_cradle, check_mass,
          check_quoting, check_posts, check_layout_script, check_keepouts, check_seal, check_assembly_paths,
          check_fr4_plate, check_alt_base, check_board_import, check_cal_plates]


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
          "", f"Primary build: base plate {P.BASE_VARIANTS[P.BASE_PRIMARY]['short']} (checks 1 to 15). Alternative build: "
          f"{P.BASE_VARIANTS[P.BASE_ALT]['short']} (check 16). Board import: check 17. Fixtures on the outer face (calibration seat plates, ball gauge plate, bridge gauge): check 18.",
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
           "Status: accepted = accepted by the system owner (rev C or rev D); recorded = differs from the specification for the stated reason; open = needs a "
           "decision. Items marked YAML are detailed in PROPOSED_PARAM_CHANGES.md, part C (master_params.yaml is not edited by this package).", ""]
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
