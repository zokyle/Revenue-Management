"""Exact (non-paraxial) ray trace of the GL-1 camera fold: lens pupil -> prism -> visor opening.

Model (all numbers from params):
  * entrance pupil: disc of diameter MECH['pupil_dia'] centred on the cube axis, MECH['pupil_below_cube_top'] below the cube top
    (ASSUMED - the OVM7692 lens data is not published);
  * air gap (bond line) to the prism entrance face (the prism's bottom leg, z = PRISM_Z0);
  * N-BK7 right-angle prism, n = MECH['n_prism'], aluminised hypotenuse at 45 deg (reflects at every angle);
  * exit face = the +y leg at y = PRISM_EXIT_Y.
A field direction is given in object space as (tan_h, tan_v): the ray leaves the exit face along (tan_h, 1, tan_v)
(+x to the right, +z up).  Rays are traced in the camera -> scene direction, which is equivalent.
"""
from __future__ import annotations
import math
import numpy as np
import params as P

M = P.MECH
N_GLASS = M["n_prism"]
HALF = P.PRISM_LEG / 2


def pupil_centre(side, shift=(0.0, 0.0, 0.0)):
    cx, cy = P.CAM_XY[side]
    return np.array([cx + shift[0], cy + shift[1], P.PUPIL_Z + shift[2]])


def pupil_samples(n_rim=32, n_rings=6):
    """Offsets (dx, dy) in the pupil plane: centre, filled rings and the rim. Returns (offsets, is_rim).
    The rim ring always contains the four extreme points (+-r, 0) and (0, +-r): they are the rays that limit the field
    left / right and up / down, so a limit angle found with these samples is the limit of the whole pupil disc (inner
    rings are staggered by half a step)."""
    r = M["pupil_dia"] / 2
    pts, rim = [(0.0, 0.0)], [False]
    for k in range(1, n_rings + 1):
        rr = r * k / n_rings
        last = k == n_rings
        m = max(6, int(round(n_rim * k / n_rings)))
        if last:
            m = 4 * max(2, int(math.ceil(m / 4)))            # a multiple of four, starting at angle 0: the extreme points are samples
        for i in range(m):
            a = 2 * math.pi * (i + (0.0 if last else 0.5 * ((n_rings - k) % 2))) / m
            pts.append((rr * math.cos(a), rr * math.sin(a))); rim.append(last)
    return np.array(pts), np.array(rim)


def trace(side, tan_h, tan_v, pupil_offset=(0.0, 0.0), shift=(0.0, 0.0, 0.0)):
    """Trace one ray. `shift` moves the whole camera + prism (PCB misplacement) relative to the tub.
    Returns a dict with the hit points, the exit direction and the margin (mm, negative = clipped) to the edge of
    each prism face."""
    cx, cy = P.CAM_XY[side]
    cx, cy = cx + shift[0], cy + shift[1]
    z0, z1 = P.PRISM_Z0 + shift[2], P.PRISM_Z1 + shift[2]
    y0, y1 = P.PRISM_Y0 + shift[1], P.PRISM_EXIT_Y + shift[1]
    p0 = pupil_centre(side, shift) + np.array([pupil_offset[0], pupil_offset[1], 0.0])
    d_in = np.array([tan_h, tan_v, 1.0]); d_in /= np.linalg.norm(d_in)          # in air, travelling up
    out = dict(p0=p0, ok=True, clipped_at=None)

    def face_margin(u, ulo, uhi, v, vlo, vhi):
        return min(u - ulo, uhi - u, v - vlo, vhi - v)

    # 1. entrance face (z = z0)
    t = (z0 - p0[2]) / d_in[2]
    pe = p0 + t * d_in
    out["p_entrance"] = pe
    out["m_entrance"] = face_margin(pe[0], cx - HALF, cx + HALF, pe[1], y0, y1)
    # refraction air -> glass at a face normal to z
    s = d_in[:2] / N_GLASS
    d1 = np.array([s[0], s[1], math.sqrt(1.0 - s @ s)])
    # 2. hypotenuse: (z - z0) = (y - y0)
    denom = d1[2] - d1[1]
    th = (pe[1] - y0) / denom if denom > 1e-12 else float("inf")
    ph = pe + th * d1
    out["p_hypotenuse"] = ph
    out["m_hypotenuse"] = face_margin(ph[0], cx - HALF, cx + HALF, ph[1], y0, y1)
    # a ray that reaches the exit face before the mirror is lost (stray path)
    if d1[1] > 0 and (y1 - pe[1]) / d1[1] < th:
        out["m_hypotenuse"] = min(out["m_hypotenuse"], -1e-9)
    d2 = np.array([d1[0], d1[2], d1[1]])                                         # mirror at 45 deg swaps y and z
    # 3. exit face (y = y1)
    tx = (y1 - ph[1]) / d2[1]
    px = ph + tx * d2
    out["p_exit"] = px
    out["m_exit"] = face_margin(px[0], cx - HALF, cx + HALF, px[2], z0, z1)
    # refraction glass -> air at a face normal to y
    sx, sz = d2[0] * N_GLASS, d2[2] * N_GLASS
    q = 1.0 - sx * sx - sz * sz
    if q <= 0:
        out.update(ok=False, clipped_at="total internal reflection at the exit face", d_out=None)
        return out
    out["d_out"] = np.array([sx, math.sqrt(q), sz])
    for name in ("entrance", "hypotenuse", "exit"):
        if out["m_" + name] < 0 and out["ok"]:
            out.update(ok=False, clipped_at=f"prism {name} face")
    return out


def at_plane_y(tr, y):
    """Point of a traced ray (after the exit face) on the plane y = const."""
    t = (y - tr["p_exit"][1]) / tr["d_out"][1]
    return tr["p_exit"] + t * tr["d_out"]


def field_points():
    """Named field points (tan_h, tan_v) for the specified field: +-h, +up / -down."""
    th = math.tan(math.radians(M["fov_h_half_deg"]))
    tu = math.tan(math.radians(M["fov_up_deg"]))
    td = -math.tan(math.radians(M["fov_down_deg"]))
    return [("axis", 0.0, 0.0), ("left edge", -th, 0.0), ("right edge", th, 0.0), ("top edge", 0.0, tu), ("bottom edge", 0.0, td),
            ("top-left corner", -th, tu), ("top-right corner", th, tu), ("bottom-left corner", -th, td), ("bottom-right corner", th, td)]


def bundle(side, tan_h, tan_v, caster=None, shift=(0.0, 0.0, 0.0), n_rim=32, n_rings=6, reach=60.0):
    """Trace the full pupil bundle for one field direction.  `caster` (geom.RayCaster of the tub) tests the visor.
    Returns transmission fractions and the limiting margins."""
    offs, rim = pupil_samples(n_rim, n_rings)
    n = len(offs)
    pass_prism = pass_all = 0
    m_ent = m_hyp = m_exit = float("inf")
    first_block = {}
    for o in offs:
        tr = trace(side, tan_h, tan_v, o, shift)
        m_ent, m_hyp, m_exit = min(m_ent, tr["m_entrance"]), min(m_hyp, tr["m_hypotenuse"]), min(m_exit, tr["m_exit"])
        if not tr["ok"]:
            first_block[tr["clipped_at"]] = first_block.get(tr["clipped_at"], 0) + 1
            continue
        pass_prism += 1
        if caster is not None and caster.blocked(tr["p_exit"], tr["d_out"], 1e-6, reach):
            first_block["tub (visor opening)"] = first_block.get("tub (visor opening)", 0) + 1
            continue
        pass_all += 1
    chief = trace(side, tan_h, tan_v, (0.0, 0.0), shift)
    chief_ok = chief["ok"] and not (caster is not None and caster.blocked(chief["p_exit"], chief["d_out"], 1e-6, reach))
    return dict(n=n, prism_fraction=pass_prism / n, total_fraction=pass_all / n, chief=chief, chief_ok=chief_ok,
                m_entrance=m_ent, m_hypotenuse=m_hyp, m_exit=m_exit, blocked=first_block)


def limit_angle(side, direction, caster, full_pupil, shift=(0.0, 0.0, 0.0), hi=60.0, tol=None):
    """Largest field angle (deg) in `direction` ('left','right','up','down') that is still unobstructed, by bisection.
    full_pupil=False: chief ray only; True: every sampled pupil ray must pass.  Returns (angle, limiting element)."""
    sgn = {"left": (-1, 0), "right": (1, 0), "up": (0, 1), "down": (0, -1)}[direction]
    tol = M["fov_angle_tol"] if tol is None else tol

    def clear(a):
        t = math.tan(math.radians(a))
        b = bundle(side, sgn[0] * t, sgn[1] * t, caster, shift, n_rim=24, n_rings=3)
        return (b["total_fraction"] >= 1.0) if full_pupil else b["chief_ok"], b
    lo_a, hi_a = 0.0, hi
    ok, _ = clear(lo_a)
    if not ok:
        return 0.0, "blocked on axis"
    while hi_a - lo_a > tol:
        mid = 0.5 * (lo_a + hi_a)
        ok, _ = clear(mid)
        lo_a, hi_a = (mid, hi_a) if ok else (lo_a, mid)
    _, b = clear(hi_a + 0.05)
    if full_pupil:
        why = max(b["blocked"], key=b["blocked"].get) if b["blocked"] else "none"
    else:
        why = b["chief"]["clipped_at"] or ("tub (visor opening)" if not b["chief_ok"] else "none")
    return lo_a, why


def upper_field_closed_form(dz=0.0, dy_away=0.0):
    """Upper field of the full pupil (deg) with the optics dz high and dy_away further from the visor, in closed form: the
    ray from the upper rim of the pupil through the top edge of the opening on the recess floor.  With a = air path (pupil
    to prism + exit face to the recess floor) and L = glass path (one prism leg):
        a tan(t) + L tan(t') = margin,   sin(t) = n sin(t').      Cross-check of the ray trace in check 4."""
    from scipy.optimize import brentq
    a = (P.PRISM_Z0 - P.PUPIL_Z) + (P.WIN_RECESS_FLOOR_Y - P.PRISM_EXIT_Y) + dy_away
    margin = P.OPEN_Z1 - (P.AXIS_Z + dz) - M["pupil_dia"] / 2
    f = lambda t: a * math.tan(t) + P.PRISM_LEG * math.tan(math.asin(math.sin(t) / N_GLASS)) - margin
    return math.degrees(brentq(f, 0.0, math.radians(60.0)))


def upper_field_terms(dz=0.0):
    """(air path a, glass path L, margin) of upper_field_closed_form, for the report text."""
    return ((P.PRISM_Z0 - P.PUPIL_Z) + (P.WIN_RECESS_FLOOR_Y - P.PRISM_EXIT_Y), P.PRISM_LEG, P.OPEN_Z1 - (P.AXIS_Z + dz) - M["pupil_dia"] / 2)


def frustum_rects(side, full_pupil, far=200.0):
    """Bounding rectangles (x0, x1, z0, z1) of the field at the exit-face plane and `far` mm in front of it."""
    y_near = P.PRISM_EXIT_Y
    y_far = y_near + far
    offs, rim = pupil_samples(32, 1) if full_pupil else (np.array([(0.0, 0.0)]), np.array([True]))
    near, farp = [], []
    for _, th, tv in field_points():
        for o in offs:
            tr = trace(side, th, tv, o)
            a, b = at_plane_y(tr, y_near), at_plane_y(tr, y_far)
            near.append((a[0], a[2])); farp.append((b[0], b[2]))
    near, farp = np.array(near), np.array(farp)
    return ((near[:, 0].min(), near[:, 0].max(), near[:, 1].min(), near[:, 1].max()), y_near,
            (farp[:, 0].min(), farp[:, 0].max(), farp[:, 1].min(), farp[:, 1].max()), y_far)


def frustum_solid(side, full_pupil, far=200.0):
    """Field frustum from the prism exit face out to `far` mm as a cadquery Solid (ruled loft of the two rectangles)."""
    import cadquery as cq
    rn, yn, rf, yf = frustum_rects(side, full_pupil, far)

    def wire(r, y):
        pts = [cq.Vector(r[0], y, r[2]), cq.Vector(r[1], y, r[2]), cq.Vector(r[1], y, r[3]), cq.Vector(r[0], y, r[3])]
        return cq.Wire.makePolygon(pts + [pts[0]])
    return cq.Solid.makeLoft([wire(rn, yn), wire(rf, yf)], ruled=True)
