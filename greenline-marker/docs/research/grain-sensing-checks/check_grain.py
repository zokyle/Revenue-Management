"""Independent re-computation of the numeric claims in the first grain-sensing report.

Written for docs/research/grain-sensing.md (verification pass, 2026-11-11).
Reviewer's own models; nothing here comes from a datasheet. Section 5 assumes OPT4001
figures recalled from memory and is labelled as such.

Pure numpy. No project code is imported. Run:  python check_grain.py
"""
import numpy as np

np.set_printoptions(precision=4, suppress=True)
g = 9.81
ft = 0.3048
V0 = 1.83  # Stimpmeter release speed, m/s (report value, from memory there)

print("=" * 78)
print("1. Stimp -> rolling deceleration, equivalent slope, down/into grain asymmetry")
for S in (8, 10, 12):
    a0 = V0 ** 2 / (2 * S * ft)
    print(f"  Stimp {S:2d} ft: a0 = {a0:.4f} m/s^2 ; s_eq per unit k = a0/((5/7)g) = {a0 / (5 / 7 * g):.4f}")
a0_10 = V0 ** 2 / (2 * 10 * ft)
for k in (0.02, 0.05, 0.10, 0.12):
    s_down, s_into = 10 / (1 - k), 10 / (1 + k)
    print(
        f"  k={k:.2f}: S_down/S_into={(1 + k) / (1 - k):.3f}  diff={s_down - s_into:.2f} ft  "
        f"s_eq={100 * k * a0_10 / (5 / 7 * g):.3f} %  kD/2 (D=3 m)={100 * k * 3 / 2:.1f} cm"
    )

print("=" * 78)
print("2. Cross-grain drift: numeric integration of the vector pseudo-force model")


def putt(a0, g_lat, D, past=0.0, dt=1e-4):
    """Ball launched along +x. Friction a0 opposes velocity; constant lateral accel g_lat (+y).
    Launch speed chosen so a straight putt would stop at D + past.
    Returns lateral offset y when x first reaches D (or at stop)."""
    v = np.array([np.sqrt(2 * a0 * (D + past)), 0.0])
    p = np.zeros(2)
    while True:
        sp = np.hypot(*v)
        if sp < 1e-4:
            return p[1], p[0]
        acc = -a0 * v / sp + np.array([0.0, g_lat])
        v_new = v + acc * dt
        p_new = p + 0.5 * (v + v_new) * dt
        if p_new[0] >= D:
            f = (D - p[0]) / (p_new[0] - p[0])
            return p[1] + f * (p_new[1] - p[1]), D
        # stop when static friction would hold the ball (speed ~0 and g_lat < a0)
        if np.hypot(*v_new) < 1e-4:
            return p_new[1], p_new[0]
        v, p = v_new, p_new


for k in (0.02, 0.05, 0.10):
    D = 3.0
    y_die, x_die = putt(a0_10, k * a0_10, D, past=0.0)
    y_43, _ = putt(a0_10, k * a0_10, D, past=0.43)  # 17 in past
    y_30, _ = putt(a0_10, k * a0_10, D, past=0.30)
    print(
        f"  k={k:.2f}: dying putt y={100 * y_die:.2f} cm (x_stop={x_die:.3f} m) vs kD/2={100 * k * D / 2:.2f} cm ; "
        f"0.30 m past: {100 * y_30:.2f} cm ({100 * (1 - y_30 / y_die):.0f}% less) ; "
        f"0.43 m past: {100 * y_43:.2f} cm ({100 * (1 - y_43 / y_die):.0f}% less)"
    )
print("  Note: with a scalar anisotropic-friction model (deceleration a0(1-k cos) along -v only)")
print("  the lateral force on a cross-grain putt is zero, so drift is 0, not kD/2.")

print("=" * 78)
print("3. Single-facet lean contrast (centre-point geometry)")
d2r = np.pi / 180
for phi, e in ((60, 20), (80, 20), (80, 35), (70, 20), (80, 45)):
    back = np.cos((phi - e) * d2r)
    front = max(0.0, -np.cos((phi + e) * d2r))
    mod = (back - front) / (back + front)
    m1_unclipped = 1 / np.tan(phi * d2r) / np.tan(e * d2r)
    print(f"  lean {phi} deg, LED elev {e} deg: back-lit {back:.2f}, front-lit {front:.2f}, "
          f"2-point modulation {mod:.2f}, cot(phi)cot(e)={m1_unclipped:.2f}")
print("  Specular facet for elev 20, nadir view: normal tilt (90-20)/2 = 35 deg -> blade lean 55 deg")

print("=" * 78)
print("4. Ring-sensor simulation: 8 LEDs, nadir detector, finite field of view")

PHI = np.arange(8) * 2 * np.pi / 8


def ring_signals(r, h_det, fov_d, emitter="flat", h_led=None, tilt_deg=0.0,
                 canopy="lambert", lean_deg=80.0, rho=0.05, step=0.04):
    """Detector at origin looking down (-z). Canopy nominal plane z=-h_det, tilted by tilt_deg
    about the y axis through the point under the detector. LEDs on radius r.
    emitter: 'flat' (Lambertian, axis -z, in the ceiling z=0), 'aimed' (axis at FOV centre),
             'side' (at height h_led above canopy, axis horizontal radially inward), 'iso'.
    canopy: 'lambert' or 'facet' (all blades lean toward +x by lean_deg from vertical).
    Returns the 8 detector illuminances per unit on-axis intensity (lux per cd), plus
    irradiance-weighted mean LED elevation and near/far irradiance ratio for LED 0."""
    h = h_det
    if h_led is None:
        h_led = h
    R = fov_d / 2
    td = np.tan(tilt_deg * d2r)
    ext = R * 1.3
    xs = np.arange(-ext, ext + step / 2, step)
    X, Y = np.meshgrid(xs, xs)
    Z = -h - X * td
    n = np.array([np.sin(tilt_deg * d2r), 0.0, np.cos(tilt_deg * d2r)])
    dA = step * step / np.cos(tilt_deg * d2r) * 1e-6  # m^2
    # detector geometry (mm)
    wx, wy, wz = -X, -Y, -Z
    wd = np.sqrt(wx ** 2 + wy ** 2 + wz ** 2)
    in_fov = (np.sqrt(X ** 2 + Y ** 2) / (-Z)) <= (R / h)
    cos_d = wz / wd
    cos_s = (n[0] * wx + n[1] * wy + n[2] * wz) / wd
    lean = lean_deg * d2r
    nf = np.array([-np.cos(lean), 0.0, np.sin(lean)])
    view_f = np.clip((nf[0] * wx + nf[1] * wy + nf[2] * wz) / wd, 0, None)
    out = []
    stats = None
    for i, ph in enumerate(PHI):
        sx, sy = r * np.cos(ph), r * np.sin(ph)
        sz = 0.0 if emitter != "side" else -(h - h_led)
        ux, uy, uz = X - sx, Y - sy, Z - sz
        d = np.sqrt(ux ** 2 + uy ** 2 + uz ** 2)
        if emitter == "flat":
            pat = np.clip(-uz / d, 0, None)
        elif emitter == "aimed":
            ax = np.array([-sx, -sy, -h - sz]); ax = ax / np.linalg.norm(ax)
            pat = np.clip((ux * ax[0] + uy * ax[1] + uz * ax[2]) / d, 0, None)
        elif emitter == "side":
            ax = np.array([-np.cos(ph), -np.sin(ph), 0.0])
            pat = np.clip((ux * ax[0] + uy * ax[1] + uz * ax[2]) / d, 0, None)
        else:
            pat = np.ones_like(d)
        lx, ly, lz = -ux / d, -uy / d, -uz / d  # unit vector surface -> LED
        d_m2 = (d * 1e-3) ** 2
        if canopy == "lambert":
            E = pat * np.clip(n[0] * lx + n[1] * ly + n[2] * lz, 0, None) / d_m2  # lux per cd
            Lum = rho * E / np.pi
            dS = Lum * np.clip(cos_s, 0, None) * cos_d / (wd * 1e-3) ** 2 * dA
        else:
            E = pat * np.clip(nf[0] * lx + nf[1] * ly + nf[2] * lz, 0, None) / d_m2
            dS = rho * E / np.pi * view_f * cos_d / (wd * 1e-3) ** 2 * dA
        out.append(np.sum(dS[in_fov]))
        if i == 0:
            Eh = pat * np.clip(lz, 0, None) / d_m2
            elev = np.arcsin(np.clip(lz, -1, 1)) / d2r
            w = Eh[in_fov]
            row = np.argmin(np.abs(xs))  # y = 0 row
            near = Eh[row, np.argmin(np.abs(xs - R))]
            far = Eh[row, np.argmin(np.abs(xs + R))]
            stats = (np.sum(w * elev[in_fov]) / np.sum(w), near / far,
                     np.arctan2(h_led, r) / d2r)
    return np.array(out), stats


def harmonics(S):
    c = np.sum(S * np.exp(-1j * PHI)) * 2 / np.sum(S)
    return abs(c), np.angle(c) / d2r


print("  4a. False first harmonic from 1 deg seating tilt on a uniform Lambertian canopy")
print("      (report formula: (2/h-4h/d^2)*r*tan(1deg) flat; reviewer centre-point formula: (r/h)*tan(1deg))")
cases = [
    ("flat  r=6.0 h=2.2 FOV 8mm", dict(r=6.0, h_det=2.2, fov_d=8, emitter="flat")),
    ("flat  r=6.0 h=2.2 FOV 4mm", dict(r=6.0, h_det=2.2, fov_d=4, emitter="flat")),
    ("flat  r=6.0 h=2.2 FOV 1mm", dict(r=6.0, h_det=2.2, fov_d=1, emitter="flat")),
    ("flat  r=4.5 h=2.2 FOV 6mm", dict(r=4.5, h_det=2.2, fov_d=6, emitter="flat")),
    ("aimed r=4.5 h=3.15 (35deg) FOV 1mm", dict(r=4.5, h_det=3.15, fov_d=1, emitter="aimed")),
    ("aimed r=4.5 h=3.15 (35deg) FOV 6mm", dict(r=4.5, h_det=3.15, fov_d=6, emitter="aimed")),
    ("side  r=4.5 hLED=2.2 det 2.6 FOV 1mm", dict(r=4.5, h_det=2.6, fov_d=1, emitter="side", h_led=2.2)),
    ("side  r=4.5 hLED=2.6 (r/sqrt3) det 3.0 FOV 1mm", dict(r=4.5, h_det=3.0, fov_d=1, emitter="side", h_led=2.598)),
    ("side  r=4.5 hLED=2.6 (r/sqrt3) det 3.0 FOV 6mm", dict(r=4.5, h_det=3.0, fov_d=6, emitter="side", h_led=2.598)),
    ("side  r=6.0 hLED=1.5 det 2.2 FOV 8mm", dict(r=6.0, h_det=2.2, fov_d=8, emitter="side", h_led=1.5)),
    ("flat  r=9.0 h=2.2 FOV 10mm", dict(r=9.0, h_det=2.2, fov_d=10, emitter="flat")),
]
for name, kw in cases:
    S0, st = ring_signals(**kw, tilt_deg=0.0)
    S1, _ = ring_signals(**kw, tilt_deg=1.0)
    m0, _ = harmonics(S0)
    m1, ang = harmonics(S1)
    r = kw["r"]; hl = kw.get("h_led", kw["h_det"])
    d2 = r * r + hl * hl
    rep = {"flat": 2 / hl - 4 * hl / d2, "aimed": 1 / hl - 3 * hl / d2,
           "side": 1 / hl - 4 * hl / d2}[kw["emitter"]] * r * np.tan(d2r)
    mine = r / hl * np.tan(d2r)
    print(f"   {name:48s} m1_false={100 * m1:5.2f}%/deg (untilted residual {100 * m0:.3f}%) "
          f"| report formula {100 * abs(rep):5.2f}% | (r/h)tan(1deg) {100 * mine:5.2f}%")

print("  4b. Illumination non-uniformity and effective elevation (LED 0, flat emitter, h=2.2)")
for r, fov in ((6.0, 4), (6.0, 8), (6.0, 10), (4.5, 6), (4.5, 8), (9.0, 10)):
    S0, st = ring_signals(r=r, h_det=2.2, fov_d=fov, emitter="flat")
    print(f"   r={r} FOV {fov} mm: near/far edge irradiance ratio {st[1]:7.1f}:1 ; "
          f"centre elevation {st[2]:.1f} deg ; irradiance-weighted mean elevation {st[0]:.1f} deg")
# closed forms for the report's '7:1 across a 4 mm FOV, r=6, h=2'
for h in (2.0, 2.2):
    near, far = (6 - 2) ** 2 + h * h, (6 + 2) ** 2 + h * h
    print(f"   closed form r=6 h={h} +/-2 mm: flat Lambertian (h^2/d^4) {(far / near) ** 2:.1f}:1 ; "
          f"aimed/isotropic (h/d^3) {(far / near) ** 1.5:.1f}:1")

print("  4c. Lean signal with finite field of view (all blades leaning toward +x, no shadowing)")
for lean in (60, 70, 80):
    for name, kw in (("flat r=6 h=2.2 FOV 8mm", dict(r=6.0, h_det=2.2, fov_d=8, emitter="flat")),
                     ("flat r=6 h=2.2 FOV 4mm", dict(r=6.0, h_det=2.2, fov_d=4, emitter="flat")),
                     ("flat r=6 h=2.2 FOV 1mm", dict(r=6.0, h_det=2.2, fov_d=1, emitter="flat")),
                     ("flat r=9 h=2.2 FOV 10mm", dict(r=9.0, h_det=2.2, fov_d=10, emitter="flat")),
                     ("side r=6 hLED=1.5 det 2.2 FOV 8mm", dict(r=6.0, h_det=2.2, fov_d=8, emitter="side", h_led=1.5))):
        S, _ = ring_signals(**kw, canopy="facet", lean_deg=lean)
        m1, ang = harmonics(S)
        print(f"   lean {lean} deg, {name:34s}: m1={m1:.2f}, bright azimuth {ang:6.1f} deg "
              f"(lean is toward 0 deg), max/min={S.max() / max(S.min(), 1e-12):.1f}")

print("  4d. Signal level at the detector (uniform Lambertian canopy, rho=0.05, no window loss)")
for name, kw in (("flat r=6 h=2.2 FOV 8mm", dict(r=6.0, h_det=2.2, fov_d=8, emitter="flat")),
                 ("flat r=4.5 h=2.2 FOV 8mm", dict(r=4.5, h_det=2.2, fov_d=8, emitter="flat")),
                 ("flat r=9 h=2.2 FOV 10mm", dict(r=9.0, h_det=2.2, fov_d=10, emitter="flat"))):
    S, _ = ring_signals(**kw)
    per_cd = S.mean()
    print(f"   {name}: {per_cd * 1e-3:.3f} lux per mcd of on-axis LED intensity "
          f"-> 15 mcd: {per_cd * 0.015:.2f} lux ; 50 mcd: {per_cd * 0.05:.2f} lux")

print("=" * 78)
print("5. OPT4001 quantisation at short conversion times (ASSUMES datasheet values recalled")
print("   from memory: 312.5 ulux LSB at 20 bits/800 ms in lowest range, one bit lost per halving)")
fs0 = 312.5e-6 * 2 ** 20
for t_ms, bits in ((0.6, 9), (6.5, 13), (12.7, 14), (25, 15), (50, 16), (100, 17)):
    print(f"   {t_ms:5.1f} ms: {bits} bits -> step {1e3 * fs0 / 2 ** bits:7.2f} mlux in the {fs0:.0f} lux range")

print("=" * 78)
print("6. Energy and time per read")
for i_ma, t_ms, cyc in ((10, 6.5, 3), (20, 6.5, 4), (20, 25, 4)):
    on = 8 * cyc * t_ms * 1e-3
    total = 16 * cyc * t_ms * 1e-3
    print(f"   {i_ma} mA from 3.0 V, {t_ms} ms conversions, {cyc} cycles: LED on-time {on:.2f} s, "
          f"read time {total:.2f} s, LED energy {3.0 * i_ma * on:.1f} mJ")

print("=" * 78)
print("7. Sample size: shoots in the field of view")
for fov in (4, 8, 10, 12):
    area = np.pi * (fov / 20) ** 2
    print(f"   FOV {fov} mm: area {area:.3f} cm^2 -> {15 * area:.1f}-{25 * area:.1f} shoots at 15-25 shoots/cm^2")

print("=" * 78)
print("8. Geometry odds and ends")
print(f"   r=6 h=2.2: centre is {np.arctan2(6, 2.2) / d2r:.1f} deg off a downward LED axis, cos={np.cos(np.arctan2(6, 2.2)):.3f}")
for xedge in (2.0, 3.0, 4.0):
    print(f"   LED elevation at FOV edge +/-{xedge} mm: near {np.arctan2(2.2, 6 - xedge) / d2r:.1f} deg, "
          f"far {np.arctan2(2.2, 6 + xedge) / d2r:.1f} deg")
ti, n_ = 70 * d2r, 1.5
tt = np.arcsin(np.sin(ti) / n_)
Rs = (np.sin(ti - tt) / np.sin(ti + tt)) ** 2
Rp = (np.tan(ti - tt) / np.tan(ti + tt)) ** 2
print(f"   Fresnel loss, n=1.5, 70 deg in air: one surface {(Rs + Rp) / 2 * 100:.1f}% , two surfaces {(1 - (1 - (Rs + Rp) / 2) ** 2) * 100:.1f}%")
print(f"   1 deg tilt at r=6 mm: height change {6 * np.tan(d2r):.3f} mm ; report dlnE/dh = {2 / 2.2 - 4 * 2.2 / (36 + 2.2 ** 2):.3f} /mm")
print(f"   Charlieplex: 4 pins -> {4 * 3} LEDs")
print(f"   Mower widths: 21 in = {21 * 0.0254:.3f} m, 26 in = {26 * 0.0254:.3f} m, 62 in = {62 * 0.0254:.2f} m")

print("=" * 78)
print("9. Stimpmeter release speed plausibility (geometry recalled from memory: 30 in run,")
print("   about 20 deg release angle, 145 deg V-groove; ball radius 21.3 mm)")
drop = 30 * 0.0254 * np.sin(20.5 * d2r)
k_roll = 0.4 / np.sin(72.5 * d2r) ** 2  # (2/5) (r / r_eff)^2 for a ball rolling in a V-groove
v_exit = np.sqrt(2 * g * drop / (1 + k_roll))
print(f"   drop {drop:.3f} m, speed at the foot of the ramp before the ramp-to-turf transition {v_exit:.2f} m/s")
print("   (the commonly quoted on-turf release speed is 1.83 m/s)")
print(f"   Stimp 10: rolling resistance coefficient rho = a0/((5/7)g) = {a0_10 / (5 / 7 * g):.4f} ; equivalent slope = k * rho")
