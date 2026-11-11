"""Cradle hold-down (rev C): closed-form sizing of the latch and the lip, and the insertion path of the marker.

The numbers here are textbook beam formulas on the dimensions in params; checks.check_cradle() verifies the
geometry they assume against the solids (beam section, hook overlap, clearances) and proves the insertion path by
posing the marker solids, tilt by tilt, against the cradle solids.

Latch = uniform rectangular cantilever, width b, thickness h, free length L (root -> retaining face), modulus E:
    I = b h^3 / 12
    tip force for a hook travel d            P = 3 E I d / L^3
    outer-fibre strain at the root           eps = 3 h d / (2 L^2)          (tip force; a tip moment gives h d / L^2)
    mating force on a lead-in at angle a     W = P (mu + tan a) / (1 - mu tan a)
    release by pressing the thumb tab        M = 2 E I d / L^2 ,  F = M / lever
Retention.  The retaining face is at 90 deg, so there is no cam angle.  An upward force F on the hook acts at a
distance e in front of the beam's neutral axis; the moment F e bends the beam backward:
    hook travel under load                   d = F e L^2 / (2 E I) - H L^3 / (3 E I)      (H = friction on the face, |H| <= mu F)
    the hook lets go when d reaches the overlap u:
        without friction                     F = 2 E I u / (e L^2)                          (lower bound, used for the requirement)
        with friction mu < 1.5 e / L         F = u E I / (e L^2 / 2 - mu L^3 / 3)
        with friction mu >= 1.5 e / L        self-locking: the hook does not slide at any load (strength governs)
"""
from __future__ import annotations
import math
import params as P

M = P.MECH
PIVOT = (P.Y_VISOR, 0.0)          # front bottom corner of the tub (key lugs): the marker is tilted about this line


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


def latch_deflected(latch_shape, d):
    """Latch solid with its hook moved back by d: rigid rotation about the point 2L/3 below the retaining face, which
    reproduces the tip travel AND the tip slope (3 d / 2 L) of a tip-loaded cantilever."""
    import cadquery as cq
    if d <= 0:
        return latch_shape
    zc = P.HOOK_Z0 - 2 * P.LATCH_L / 3
    return latch_shape.rotate(cq.Vector(0, P.LATCH_Y_NA, zc), cq.Vector(1, P.LATCH_Y_NA, zc), math.degrees(1.5 * d / P.LATCH_L))


def path_pose(theta_deg):
    """Closed-form pose (s, h) for a tilt: the marker rests on the nest floor (+ gap) and is as far forward as the
    front nest wall, the nose pocket and the lip tip allow (+ gap).  theta = 0 is the seated position (0, 0)."""
    if theta_deg <= 0:
        return 0.0, 0.0
    g = M["insertion_gap"]
    t = math.radians(theta_deg)
    # floor: lowest of the front bottom edge (lugs), the base-plate front edge, the three balls and the rear rim
    cand = [xf(P.Y_VISOR, 0.0, theta_deg, 0, 0)[1], xf(P.BASE_FLAT, 0.0, theta_deg, 0, 0)[1], xf(-P.R_OUT, 0.0, theta_deg, 0, 0)[1]]
    cand += [xf(by, P.BALL_Z, theta_deg, 0, 0)[1] - P.BALL_D / 2 for _, by in P.BALL_XY]
    h = P.NEST_FLOOR_Z + g - min(cand)
    # front nest wall (to the body top), nose pocket wall (above it), lip tip corner
    zw = min(P.T, (P.CRADLE_TOP_Z - h) / math.cos(t))
    s_wall = P.Y_VISOR + zw * math.sin(t) - P.NEST_FLAT + g
    s_pocket = P.Y_VISOR + P.T * math.sin(t) - P.LIP_POCKET_Y + g
    s_lip = (g - (P.LIP_Z0 - P.T * math.cos(t) - h) * math.cos(t)) / math.sin(t) - P.LIP_Y0 + P.Y_VISOR + P.T * math.sin(t)
    return max(0.0, s_wall, s_pocket, s_lip), h


# ----------------------------------------------------------------------------------------------
# sizing
# ----------------------------------------------------------------------------------------------
def calc(marker_mass_g=11.4, cog_y=-1.4, d_insert=None):
    """All hold-down numbers.  d_insert = hook travel needed during insertion (from the posed solids); when None the
    nominal release travel is used."""
    E, b, h, L = M["pa12_E_MPa"], M["latch_w"], M["latch_h"], P.LATCH_L
    I = b * h ** 3 / 12
    EI = E * I
    mu, a = M["friction_mu"], math.radians(M["hook_lead_deg"])
    n = len(P.PAD_XS)
    Fp7, Fp4 = n * P.PIN_FORCE_N, len(P.PINS_CONSUMER) * P.PIN_FORCE_N
    Wm = marker_mass_g * 9.81e-3
    y_hook = -0.5 * (P.TUB_TOP_FLAT_R + P.HOOK_R)                 # centroid of the hook contact on the tub top
    y_lip = P.Y_VISOR - M["lip_overlap"] / 2
    y_pin = P.PAD_Y

    def shares(Fp):                                              # marker pushed up against lip and hook by the pins
        Fh = (Fp * (y_lip - y_pin) - Wm * (y_lip - cog_y)) / (y_lip - y_hook)
        return Fh, Fp - Wm - Fh
    Fh7, Fl7 = shares(Fp7)
    Fh4, Fl4 = shares(Fp4)
    kh = (y_lip - y_pin) / (y_lip - y_hook)                      # share of a pin-row force that the hook carries
    # retention
    u = P.HOOK_OVERLAP
    e = y_hook - P.LATCH_Y_NA
    u_min, e_min = u - P.CLR, e + P.CLR / 2                      # marker pushed fully forward in the nest
    cam = lambda uu, ee: 2 * EI * uu / (ee * L ** 2)
    F_cam, F_cam_min = cam(u, e), cam(u_min, e_min)
    mu_lock = 1.5 * e / L
    mu_lo = M["friction_mu_range"][0]
    den = e * L ** 2 / 2 - mu_lo * L ** 3 / 3
    F_fric = (u * EI / den) if den > 0 else float("inf")
    req = M["retention_factor_required"]
    F3 = req * Fp7 * kh                                          # hook load at the required pin-row force
    sig_root = 6 * F3 * e / (b * h ** 2) + F3 / (b * h)
    # deflection, strain, forces
    d_rel, d_rel_max, d_stop = M["latch_overhang"] - P.CLR, M["latch_overhang"], M["latch_stop_deflection"]
    d_ins = d_rel if d_insert is None else d_insert
    eps = lambda d: 1.5 * h * d / L ** 2
    k = 3 * EI / L ** 3
    lead = lambda m: (m + math.tan(a)) / (1 - m * math.tan(a))
    lever = (P.Y_VISOR + P.R_OUT) / (P.Y_VISOR + 15.0)           # thumb presses the marker top 8 mm in from the rear edge
    P_ins = k * d_ins
    ins = {m: P_ins * lead(m) * lever for m in (M["friction_mu_range"][0], mu, M["friction_mu_range"][1])}
    seat = (mu * k * d_rel + Fp7 * (P.Y_VISOR - y_pin) / (P.Y_VISOR + P.R_OUT)) * lever     # last degree: friction on the nose + pins
    tab_lever = P.LATCH_Y_NA - (P.TAB_Y0 + M["tab_press_inset"])
    M_rel = lambda d: 2 * EI * d / L ** 2
    creep = Fh7 * e * L ** 2 / (2 * EI)
    # lip (cantilever plate from the pocket wall)
    lw, lt = 2 * M["lip_half_w"], M["lip_t"]
    arm = P.LIP_POCKET_Y - y_lip
    F_lip3 = req * Fp7                                           # conservative: the whole required force on the lip
    sig_lip = 6 * F_lip3 * arm / (lw * lt ** 2)
    return dict(E=E, b=b, h=h, L=L, I=I, EI=EI, mu=mu, lead_deg=M["hook_lead_deg"],
                Fp7=Fp7, Fp4=Fp4, weight=Wm, F_hook7=Fh7, F_lip7=Fl7, F_hook4=Fh4, F_lip4=Fl4, hook_share=kh,
                y_hook=y_hook, y_lip=y_lip, u=u, e=e, u_min=u_min, e_min=e_min,
                F_cam=F_cam, F_cam_min=F_cam_min, pin_equiv=F_cam / kh, pin_equiv_min=F_cam_min / kh,
                factor=F_cam / kh / Fp7, factor_min=F_cam_min / kh / Fp7, mu_lock=mu_lock, mu_lo=mu_lo, F_fric=F_fric,
                F3_hook=F3, sig_root=sig_root, sf_root=M["pa12_yield_MPa"] / sig_root,
                d_rel=d_rel, d_rel_max=d_rel_max, d_stop=d_stop, d_ins=d_ins,
                eps_ins=eps(d_ins), eps_rel=eps(d_rel), eps_rel_max=eps(d_rel_max), eps_stop=eps(d_stop),
                eps_stop_moment=h * d_stop / L ** 2, k=k, P_ins=P_ins, P_rel=k * d_rel, ins=ins, seat=seat, lever=lever,
                tab_lever=tab_lever, F_tab=M_rel(d_rel) / tab_lever, F_tab_max=M_rel(d_rel_max) / tab_lever,
                tab_drop=tab_lever * 2 * d_rel / L, creep_d=creep, lip_arm=arm, sig_lip=sig_lip,
                sf_lip=M["pa12_yield_MPa"] / sig_lip, pop_up=M["pin_mid_stroke"] * (P.Y_VISOR + P.R_OUT) / (P.Y_VISOR - y_pin))


if __name__ == "__main__":
    c = calc()
    for k_, v in c.items():
        print(f"{k_:16s} {v}")
    for th in M["insertion_tilts_deg"]:
        print(th, [round(v, 3) for v in path_pose(th)])
