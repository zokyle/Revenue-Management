"""Cradle hold-down (rev C): beam model of the latch, sizing of the lip, and the poses of the insertion path.

checks.check_cradle() verifies the geometry assumed here against the solids (beam section, nose, stops, clearances),
proves the insertion and release travel by posing the marker solids against the cradle solids, and cross-checks the
strain at the root fillet with a plane-strain finite-element model of the latch section (cad/latchfe.py).

Latch = rectangular cantilever of width b and free length L (root -> nose level) whose thickness h(s) = params.latch_h(s)
falls linearly from the root to a neck and rises again into the hook; modulus E, I(s) = b h(s)^3 / 12.  The front face
is vertical, so the neutral axis is at y_f - h(s) / 2.  The hook above the nose level is rigid.

Small-deflection beam theory, integrated numerically (no closed form for the taper):
    curvature            w''(s) = M(s) / (E I(s)),  w(0) = w'(0) = 0            (w = backward deflection of the axis)
    tip force P          M(s) = P (L - s)          -> travel d = cw_F P / (E b),  strain eps = M h / (2 E I), largest at the root
    tip moment M0        M(s) = M0                 -> travel d = cw_M M0 / (E b), strain largest at the NECK
    (params.taper_coeffs gives cw_F, cw_M, the strain per mm of travel and the tip slope per mm of travel)
    mating force on a lead-in at angle a     W = P (mu + tan a) / (1 - mu tan a)
    release by pressing the thumb tab        M0 = F_thumb * lever

Retention (the load that matters): an upward force V on the hook from the top of the marker.
    The retaining face is raked back by hook_rake_deg: the NOSE is its lowest point, so the nose corner bears on the flat
    top of the marker and the frictionless reaction is vertical.  The moment about the DEFLECTED beam axis is
        M(s) = V (y_c - y_axis(s) + w(s)) - H (z_c - z(s)),      H = mu V   (friction pulls the hook forward)
    (P-delta: the lever grows as the beam leans back).  The tip turns nose-up by theta; as long as theta < rake the face
    never becomes a ramp.  If theta exceeds the rake, the face bears on the edge radius of the marker instead and the
    reaction gets the cam component V tan(theta - rake) that opens the latch (this is what an un-raked 90 deg face
    does from the first newton).  The hook lets go when the nose has travelled to the end of the flat top: the overlap.
    The retention figure is the largest V before that, found by bisection; it is evaluated WITHOUT friction.
    Retention is proportional to E b; it falls with the overlap, so it is given for the marker pushed fully forward
    in the nest (the position the lead-in leaves it in) and with the print tolerance taken off the overlap.
"""
from __future__ import annotations
import math
import numpy as np
import params as P

M = P.MECH
PIVOT = (P.Y_VISOR, 0.0)          # reference line for the tilt of the marker (front bottom corner of the envelope)
N_BEAM = 400


# ----------------------------------------------------------------------------------------------
# posing
# ----------------------------------------------------------------------------------------------
def xf(y, z, theta_deg, s, h):
    """Pose of a marker point (y, z): tilted nose-down by theta about PIVOT, moved back by s and up by h."""
    t = math.radians(theta_deg)
    dy, dz = y - PIVOT[0], z - PIVOT[1]
    return (PIVOT[0] + dy * math.cos(t) + dz * math.sin(t) - s, PIVOT[1] - dy * math.sin(t) + dz * math.cos(t) + h)


def pose(shape, theta_deg, s, h):
    """The same pose applied to a cadquery Shape."""
    import cadquery as cq
    out = shape
    if abs(theta_deg) > 1e-12:
        out = out.rotate(cq.Vector(0, PIVOT[0], PIVOT[1]), cq.Vector(1, PIVOT[0], PIVOT[1]), -theta_deg)
    return out.translate(cq.Vector(0, -s, h))


def latch_deflected(latch_shape, d, mode="F"):
    """Latch solid with its hook moved back by d: rigid rotation about the point that reproduces the tip travel AND the
    tip slope of the bent beam (params.LATCH_PIVOT_F for a tip force, LATCH_PIVOT_M for a pure moment).  Exact for the
    hook and the tab (rigid above the nose level); the beam below it lies in front of its true bent shape (conservative
    for clearance to the marker)."""
    import cadquery as cq
    if d <= 0:
        return latch_shape
    rho = P.LATCH_PIVOT_F if mode == "F" else P.LATCH_PIVOT_M
    zc = P.HOOK_Z0 - rho
    th = math.degrees(math.asin(min(1.0, d / rho)))
    return latch_shape.rotate(cq.Vector(0, P.LATCH_Y_NA, zc), cq.Vector(1, P.LATCH_Y_NA, zc), th)


def path_pose(theta_deg):
    """Closed-form pose (s, h) for a tilt: the marker rests on the front strip of the nest floor (+ gap) and is as far
    forward as the front nest wall, the nose pocket and the lip tip allow (+ gap).  theta = 0 is the seated position."""
    if theta_deg <= 0:
        return 0.0, 0.0
    g = M["insertion_gap"]
    t = math.radians(theta_deg)
    # lowest point: front or rear edge of the base plate, the rim of the tub (front wall end, rear), or a ball
    cand = [xf(P.BASE_FLAT, 0.0, theta_deg, 0, 0)[1], xf(-P.BASE_R, 0.0, theta_deg, 0, 0)[1],
            xf(P.Y_VISOR, P.RIM_Z, theta_deg, 0, 0)[1], xf(-P.R_OUT, P.RIM_Z, theta_deg, 0, 0)[1]]
    cand += [xf(by, P.BALL_Z, theta_deg, 0, 0)[1] - P.BALL_D / 2 for _, by in P.BALL_XY]
    h = P.NEST_FLOOR_Z + g - min(cand)
    # front nest wall (to the body top), nose pocket wall (above it), lip tip corner
    zw = min(P.T, (P.CRADLE_TOP_Z - h) / math.cos(t))
    s_wall = P.Y_VISOR + zw * math.sin(t) - P.NEST_FLAT + g
    s_pocket = P.Y_VISOR + P.T * math.sin(t) - P.LIP_POCKET_Y + g
    s_lip = (g - (P.LIP_Z0 - P.T * math.cos(t) - h) * math.cos(t)) / math.sin(t) - P.LIP_Y0 + P.Y_VISOR + P.T * math.sin(t)
    return max(0.0, s_wall, s_pocket, s_lip), h


# ----------------------------------------------------------------------------------------------
# beam model
# ----------------------------------------------------------------------------------------------
def beam(E, b, loads, back=0.0):
    """Tapered cantilever under a load on the rigid hook, moment taken about the deflected axis.
    loads(d_tip, th_tip) -> (V up, H forward, y_c, zs_c): the force and where it acts (zs_c = height above the root).
    `back` moves the whole latch back (print tolerance).  Returns dict(d, th, eps (max outer-fibre strain), eps_root, w)
    or None when the iteration diverges (the hook is thrown open)."""
    L = P.LATCH_L
    s = np.linspace(0.0, L, N_BEAM + 1); ds = s[1] - s[0]
    h = P.latch_h(s)
    EI = E * b * h ** 3 / 12
    yna = P.LATCH_Y_FACE - back - h / 2
    w = np.zeros(N_BEAM + 1); th = 0.0
    for _ in range(600):
        V, H, yc, zc = loads(w[-1], th)
        Mb = V * (yc - (yna - w)) - H * (zc - s)
        k = Mb / EI
        sl = np.concatenate([[0.0], np.cumsum(0.5 * (k[1:] + k[:-1]) * ds)])
        wn = np.concatenate([[0.0], np.cumsum(0.5 * (sl[1:] + sl[:-1]) * ds)])
        if not np.isfinite(wn).all() or abs(wn[-1]) > 8.0:
            return None
        if abs(wn[-1] - w[-1]) < 1e-9 and abs(sl[-1] - th) < 1e-10:
            eps = np.abs(Mb) * h / (2 * EI)
            return dict(d=float(wn[-1]), th=float(sl[-1]), eps=float(eps.max()), eps_root=float(eps[0]), eps_at=float(s[int(np.argmax(eps))] / L),
                        M_root=float(Mb[0]), w=wn)
        w = 0.5 * (w + wn); th = 0.5 * (th + sl[-1])
    return None


def hook_load(E, V, fwd=0.0, back=0.0, mu=0.0, b=None):
    """State of the latch under an upward force V on the hook from the marker top.
    fwd = how far the marker sits forward of centre; back = how far the latch is printed back of nominal.
    Returns the beam() dict plus `released` and `regime`, or None (thrown open)."""
    b = M["latch_w"] if b is None else b
    rake = math.radians(M["hook_rake_deg"])
    a = P.HOOK_Y - P.LATCH_Y_NA                                  # nose in front of the tip reference point
    yna_tip = P.LATCH_Y_NA - back
    y_fe = -P.TUB_TOP_FLAT_R + fwd                               # end of the flat top of the marker
    rf = M["top_fillet"]
    state = {}

    def loads(d, th):
        yn = yna_tip - d + a * math.cos(th); zn = P.LATCH_L + a * math.sin(th)
        if th <= rake:                                           # nose corner on the flat top: vertical reaction
            state["regime"] = "nose on the flat top"
            return V, mu * V, yn, zn
        g = th - rake                                            # the face has become a ramp: it bears on the edge radius
        state["regime"] = "face on the edge radius (cam)"
        yc = y_fe - rf * math.sin(g)
        Nn = V / (math.cos(g) + mu * math.sin(g))
        return V, -Nn * math.sin(g) + mu * Nn * math.cos(g), yc, zn + (yc - yn) * math.tan(g)
    r = beam(E, b, loads, back)
    if r is None:
        return None
    yn = yna_tip - r["d"] + a * math.cos(r["th"])
    lim = y_fe if r["th"] <= rake else y_fe - rf * math.sin(r["th"] - rake)
    r.update(released=bool(yn < lim), regime=state.get("regime", ""), nose_travel=float(P.HOOK_Y - back - yn))
    return r


def retention(E, fwd=0.0, back=0.0, mu=0.0, b=None, v_max=400.0):
    """Largest upward force the hook holds (bisection on hook_load).  Returns dict(F, d, rot_deg, eps, regime); F = inf
    when the hook still holds at v_max (self-locking with friction)."""
    holds = lambda v: (lambda r: r is not None and not r["released"])(hook_load(E, v, fwd, back, mu, b))
    if holds(v_max):
        r = hook_load(E, v_max, fwd, back, mu, b)
        return dict(F=float("inf"), d=r["d"], rot_deg=math.degrees(r["th"]), eps=r["eps"], regime=r["regime"])
    lo, hi = 0.0, v_max
    for _ in range(50):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if holds(mid) else (lo, mid)
    r = hook_load(E, lo, fwd, back, mu, b) if lo > 0 else None
    if r is None:
        return dict(F=0.0, d=0.0, rot_deg=0.0, eps=0.0, regime="no overlap")
    return dict(F=lo, d=r["nose_travel"], rot_deg=math.degrees(r["th"]), eps=r["eps"], regime=r["regime"])


# ----------------------------------------------------------------------------------------------
# sizing
# ----------------------------------------------------------------------------------------------
def calc(marker_mass_g=11.3, cog_y=-1.4, d_insert=None, d_release=None):
    """All hold-down numbers.  d_insert = hook travel needed during insertion and d_release = (forward, centred, rearmost)
    hook travel needed to free the marker, both from the posed solids; nominal values when None."""
    E, b, h0, h1, L = M["pa12_E_MPa"], M["latch_w"], P.LATCH_H0, P.LATCH_HN, P.LATCH_L
    tc = P.LATCH_BEAM
    I0 = b * h0 ** 3 / 12
    mu, a = M["friction_mu"], math.radians(M["hook_lead_deg"])
    n = len(P.PAD_XS)
    Fp7, Fp4 = n * P.PIN_FORCE_N, len(P.PINS_CONSUMER) * P.PIN_FORCE_N
    Wm = marker_mass_g * 9.81e-3
    y_hook = -P.TUB_TOP_FLAT_R + P.CLR                            # where the nose leaves the flat top (marker forward)
    y_lip = P.Y_VISOR - M["lip_overlap"] / 2
    y_pin = P.PAD_Y

    def shares(Fp):                                              # marker pushed up against lip and hook by the pins
        Fh = (Fp * (y_lip - y_pin) - Wm * (y_lip - cog_y)) / (y_lip - y_hook)
        return Fh, Fp - Wm - Fh
    Fh7, Fl7 = shares(Fp7)
    Fh4, Fl4 = shares(Fp4)
    kh = (y_lip - y_pin) / (y_lip - y_hook)                      # share of a pin-row force that the hook carries
    req = M["retention_factor_required"]
    F3 = req * Fp7 * kh                                          # hook load at the required pin-row force

    # ---- retention cases (frictionless unless stated)
    def ret_row(label, fwd, back, E_=E, mu_=0.0, governs=False):
        r = retention(E_, fwd, back, mu_)
        fac = r["F"] / kh / Fp7
        return dict(case=label, overlap=P.HOOK_OVERLAP - fwd - back, E=E_, mu=mu_, F_hook=r["F"], pin_row=r["F"] / kh, factor=fac,
                    travel=r["d"], rot_deg=r["rot_deg"], eps=r["eps"], regime=r["regime"], governs=governs,
                    E_min=(E_ * req / fac if fac not in (0.0, float("inf")) else (0.0 if fac else float("inf"))))
    rows = [ret_row("marker centred in the nest", 0.0, 0.0),
            ret_row("marker against the front nest wall (governing position)", P.CLR, 0.0, governs=True)]
    for tol in M["overlap_tolerances"]:
        rows.append(ret_row(f"governing position, overlap reduced by {tol} mm (print tolerance)", P.CLR, tol))
    rows.append(ret_row(f"governing position, E = {M['pa12_E_low_MPa']:.0f} MPa (conditioned / warm PA12, assumed)", P.CLR, 0.0, E_=M["pa12_E_low_MPa"]))
    rows.append(ret_row(f"governing position, with friction {M['friction_mu_range'][0]}", P.CLR, 0.0, mu_=M["friction_mu_range"][0]))
    nominal, governing = rows[0], rows[1]
    worst_tol = rows[1 + len(M["overlap_tolerances"])]
    st3 = hook_load(E, F3, P.CLR, 0.0)                           # state at the required load, governing position
    st7 = hook_load(E, Fh7, P.CLR, 0.0)                          # under the continuous seven-pin load
    e_root = (P.HOOK_Y - (P.LATCH_Y_FACE - h0 / 2))              # lever of a force at the nose about the root axis
    sig_root = 6 * F3 * e_root / (b * h0 ** 2) + F3 / (b * h0)
    F_yield = M["pa12_yield_MPa"] / (6 * e_root / (b * h0 ** 2) + 1 / (b * h0))   # hook force at which the root reaches yield
    y_scallop = 0.5 * P.NEST_R * math.sin(math.radians(M["scallop_deg"][0]))      # where the fingers lift
    pull_at_yield = F_yield * (y_lip - y_hook) / (y_lip - y_scallop)

    # ---- travel, strain, forces
    rel = P.RELEASE_TRAVEL if d_release is None else tuple(d_release)
    d_rel_fwd, d_rel, d_rel_max = rel
    d_stop, d_tab = M["latch_stop_travel"], M["tab_stop_travel"]
    d_ins = d_rel if d_insert is None else d_insert
    kF = E * b / tc["cw_F"]                                      # N per mm of hook travel, tip force
    kM = E * b / tc["cw_M"]                                      # N mm of tip moment per mm of hook travel
    epsF = lambda d: tc["eps_F"] * d
    epsM = lambda d: tc["eps_M"] * d
    strain = [
        dict(case="insertion: the marker edge runs down the lead-in", load="tip force", travel=d_ins, eps=epsF(d_ins), at="root"),
        dict(case="release, marker against the front wall (as left by the insertion)", load="tab moment", travel=d_rel_fwd, eps=epsM(d_rel_fwd), at="neck"),
        dict(case="release, marker centred", load="tab moment", travel=d_rel, eps=epsM(d_rel), at="neck"),
        dict(case="release, marker at its rearmost position", load="tab moment", travel=d_rel_max, eps=epsM(d_rel_max), at="neck"),
        dict(case="FULL DEFLECTION 1: hook pushed or pulled back onto the stop ribs", load="tip force", travel=d_stop, eps=epsF(d_stop), at="root"),
        dict(case="FULL DEFLECTION 2: thumb tab pressed onto its stop", load="tab moment", travel=d_tab, eps=epsM(d_tab), at="neck"),
        dict(case=f"hook loaded with {req:.0f} x the seven-pin force (governing position)", load="hook load", travel=st3["nose_travel"] if st3 else float("nan"),
             eps=st3["eps"] if st3 else float("nan"), at="neck"),
        dict(case="continuous seven-pin load (docked, factory fixture)", load="hook load", travel=st7["nose_travel"] if st7 else float("nan"),
             eps=st7["eps"] if st7 else float("nan"), at="neck"),
    ]
    eps_full = max(epsF(d_stop), epsM(d_tab))
    lead = lambda m: (m + math.tan(a)) / (1 - m * math.tan(a))
    lever = (P.Y_VISOR + P.R_OUT) / (P.Y_VISOR + 15.0)           # thumb presses the marker top 8 mm in from the rear edge
    P_ins = kF * d_ins
    ins = {m: P_ins * lead(m) * lever for m in (M["friction_mu_range"][0], mu, M["friction_mu_range"][1])}
    seat = (mu * kF * d_rel + Fp7 * (P.Y_VISOR - y_pin) / (P.Y_VISOR + P.R_OUT)) * lever     # last degree: friction on the nose + pins
    F_tab = lambda d: kM * d / P.TAB_LEVER
    F_tab_stop = F_tab(d_tab)                                    # thumb force at which the tab lands on its stop
    abuse = M["thumb_force_abuse_N"]
    stop_area = M["tab_stop_w"] * M["tab_stop_t"]
    tab_drop = P.TAB_Z0 - P.latch_pose(P.TAB_Y0, P.TAB_Z0, d_rel, "M")[1]
    # ---- lip (cantilever plate from the pocket wall)
    lw, lt = 2 * M["lip_half_w"], M["lip_t"]
    arm = P.LIP_POCKET_Y - y_lip
    F_lip3 = req * Fp7                                           # conservative: the whole required force on the lip
    sig_lip = 6 * F_lip3 * arm / (lw * lt ** 2)
    return dict(E=E, b=b, h0=h0, h1=h1, L=L, I0=I0, EI0=E * I0, mu=mu, lead_deg=M["hook_lead_deg"], rake_deg=M["hook_rake_deg"],
                Fp7=Fp7, Fp4=Fp4, weight=Wm, F_hook7=Fh7, F_lip7=Fl7, F_hook4=Fh4, F_lip4=Fl4, hook_share=kh,
                y_hook=y_hook, y_lip=y_lip, retention=rows, nominal=nominal, governing=governing, worst_tol=worst_tol,
                factor=nominal["factor"], factor_min=governing["factor"], factor_tol=worst_tol["factor"], E_min=governing["E_min"],
                F3_hook=F3, st3=st3, st7=st7, e_root=e_root, sig_root=sig_root, sf_root=M["pa12_yield_MPa"] / sig_root,
                F_yield=F_yield, pull_at_yield=pull_at_yield,
                d_rel_fwd=d_rel_fwd, d_rel=d_rel, d_rel_max=d_rel_max, d_stop=d_stop, d_tab=d_tab, d_ins=d_ins,
                strain=strain, eps_ins=epsF(d_ins), eps_rel=epsM(d_rel), eps_rel_max=epsM(d_rel_max), eps_stop=epsF(d_stop), eps_tab=epsM(d_tab),
                eps_full=eps_full, epsF_per_mm=tc["eps_F"], epsM_per_mm=tc["eps_M"], epsM_root_per_mm=tc["eps_M_root"],
                k=kF, kM=kM, P_ins=P_ins, ins=ins, seat=seat, lever=lever,
                tab_lever=P.TAB_LEVER, F_tab_fwd=F_tab(d_rel_fwd), F_tab=F_tab(d_rel), F_tab_max=F_tab(d_rel_max), F_tab_stop=F_tab_stop,
                tab_drop=tab_drop, tab_drop_stop=P.TAB_DROP_AT_STOP, abuse=abuse, abuse_excess=max(0.0, abuse - F_tab_stop),
                sig_stop=max(0.0, abuse - F_tab_stop) / stop_area, rib_travel_M=P.RIB_TRAVEL_M,
                creep_d=st7["nose_travel"] if st7 else float("nan"), overlap_fwd=P.HOOK_OVERLAP_FWD,
                lip_arm=arm, sig_lip=sig_lip, sf_lip=M["pa12_yield_MPa"] / sig_lip,
                pop_up=P.PIN_COMPRESSION * (P.Y_VISOR + P.R_OUT) / (P.Y_VISOR - y_pin))


if __name__ == "__main__":
    c = calc()
    for r in c["retention"]:
        print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()})
    for r in c["strain"]:
        print({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()})
    for k_ in ("k", "kM", "P_ins", "ins", "seat", "F_tab_fwd", "F_tab", "F_tab_max", "F_tab_stop", "tab_drop", "tab_drop_stop", "sig_root", "F_yield",
               "pull_at_yield", "creep_d", "sig_lip", "pop_up", "E_min", "hook_share", "F_hook7", "F_lip7"):
        print(f"{k_:16s} {c[k_]}")
    for th in M["insertion_tilts_deg"]:
        print(th, [round(v, 3) for v in path_pose(th)])
