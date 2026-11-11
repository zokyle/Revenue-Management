"""Monte-Carlo estimate of blade-sampling noise for the 8-LED single-pixel grain sensor.

Reviewer's own model, written for docs/research/grain-sensing.md. It is NOT taken from any
published source and has not been compared with turf measurements.

Model
- The canopy inside the detector field of view is a set of discrete leaf facets (points) with
  random position, size, lean angle (50-85 deg from vertical) and lean azimuth.
- Lean azimuths follow a von Mises distribution about the true grain direction (0 deg) with
  mean resultant length R (R = 0: no grain, R = 1: every blade leans the same way).
- Each facet is a Lambertian upper face. No shadowing, no specular term, no leaf transmission.
- A non-directional background carries a fixed fraction of the mean signal.
- Detector: at height h above the canopy, cosine response, hard-baffled field of view.
- Emitters: 8 at 45 deg pitch; 'flat' = Lambertian chip LED facing straight down in the ceiling,
  'far' = ideal uniform collimated light at a fixed elevation (best case for comparison).
- Placement: 'poisson' (random points, pessimistic) or 'grid' (jittered grid, full cover).

Output per case: median and 90th percentile of the first-harmonic modulation m1, median absolute
direction error, probability of being within 30 deg, probability of the correct half-plane.

Run:  python mc_blades.py      (needs numpy and scipy)
"""
import numpy as np
from scipy.optimize import brentq
from scipy.special import i0, i1

rng = np.random.default_rng(20261111)
D2R = np.pi / 180
PHI = np.arange(8) * 2 * np.pi / 8


def kappa_for_resultant(R):
    if R <= 0:
        return 0.0
    return brentq(lambda k: i1(k) / i0(k) - R, 1e-6, 500)


def facet_positions(fov_d, density_cm2, placement):
    rf = fov_d / 2
    if placement == "grid":
        s = 10 / np.sqrt(density_cm2)  # pitch in mm
        g1 = np.arange(-rf - s, rf + s, s) + rng.uniform(0, s)
        g2 = np.arange(-rf - s, rf + s, s) + rng.uniform(0, s)
        gx, gy = np.meshgrid(g1, g2)
        px = (gx + rng.uniform(-s / 2, s / 2, gx.shape)).ravel()
        py = (gy + rng.uniform(-s / 2, s / 2, gy.shape)).ravel()
        keep = px ** 2 + py ** 2 <= rf ** 2
        return px[keep], py[keep]
    n = rng.poisson(density_cm2 * np.pi * (rf / 10) ** 2)
    rad = rf * np.sqrt(rng.random(n))
    ang = 2 * np.pi * rng.random(n)
    return rad * np.cos(ang), rad * np.sin(ang)


def one_read(geom, R, density_cm2, placement="grid", size_cv=0.3, diffuse=0.3):
    """Return the complex first harmonic (2/sum) * sum(S_i exp(-j phi_i)) of one placement."""
    mode, r, h, fov_d, elev = geom
    px, py = facet_positions(fov_d, density_cm2, placement)
    n = px.size
    if n < 1:
        return None
    lean = rng.uniform(50, 85, n) * D2R
    kap = kappa_for_resultant(R)
    psi = rng.vonmises(0.0, kap, n) if kap > 0 else 2 * np.pi * rng.random(n)
    sig = np.sqrt(np.log(1 + size_cv ** 2))
    area = rng.lognormal(-sig ** 2 / 2, sig, n)
    # upper-face normal of a blade leaning toward azimuth psi
    nx, ny, nz = -np.cos(lean) * np.cos(psi), -np.cos(lean) * np.sin(psi), np.sin(lean)
    # detector at (0, 0, h) above the canopy plane z = 0
    wx, wy, wz = -px, -py, np.full(n, h)
    wd = np.sqrt(wx ** 2 + wy ** 2 + wz ** 2)
    view = np.clip((nx * wx + ny * wy + nz * wz) / wd, 0, None) * (wz / wd) / wd ** 2
    s_dir = np.zeros(8)
    s_dif = np.zeros(8)
    for i, ph in enumerate(PHI):
        if mode == "far":
            e = elev * D2R
            lx = np.full(n, np.cos(e) * np.cos(ph))
            ly = np.full(n, np.cos(e) * np.sin(ph))
            lz = np.full(n, np.sin(e))
            irr = np.ones(n)
        else:  # 'flat'
            ux, uy, uz = r * np.cos(ph) - px, r * np.sin(ph) - py, np.full(n, h)
            d = np.sqrt(ux ** 2 + uy ** 2 + uz ** 2)
            lx, ly, lz = ux / d, uy / d, uz / d
            irr = lz / d ** 2  # Lambertian emitter facing down
        s_dir[i] = np.sum(area * irr * np.clip(nx * lx + ny * ly + nz * lz, 0, None) * view)
        s_dif[i] = np.sum(area * irr * lz * (wz / wd) ** 2 / wd ** 2)
    if s_dir.mean() > 0 and s_dif.mean() > 0:
        s_dif *= diffuse / (1 - diffuse) * s_dir.mean() / s_dif.mean()
    total = s_dir + s_dif
    return np.sum(total * np.exp(-1j * PHI)) * 2 / np.sum(total)


def run(geom, R, density_cm2, ntrial=1500, placements=1, **kw):
    cs = []
    for _ in range(ntrial):
        acc = [c for c in (one_read(geom, R, density_cm2, **kw) for _ in range(placements)) if c is not None]
        if acc:
            cs.append(np.mean(acc))
    cs = np.array(cs)
    m1 = np.abs(cs)
    err = np.abs(np.angle(-cs)) / D2R  # down-grain estimate = bright azimuth + 180 deg; truth = 0
    return np.median(m1), np.percentile(m1, 90), np.median(err), np.mean(err <= 30), np.mean(err <= 90)


GEOMS = {
    # name: (mode, LED radius mm, height mm, field-of-view diameter mm, elevation deg for 'far')
    "A  flat LEDs r=6 h=2.2, FOV 8 mm": ("flat", 6.0, 2.2, 8.0, None),
    "A2 flat LEDs r=6 h=2.2, FOV 10 mm": ("flat", 6.0, 2.2, 10.0, None),
    "B  flat LEDs r=9 h=2.2, FOV 10 mm": ("flat", 9.0, 2.2, 10.0, None),
    "U  ideal uniform light 20 deg, FOV 8 mm": ("far", 0.0, 2.2, 8.0, 20.0),
    "U2 ideal uniform light 20 deg, FOV 12 mm": ("far", 0.0, 2.2, 12.0, 20.0),
}


def main():
    print("columns: median m1 | 90th pct m1 | median abs direction error | P(err<=30 deg) | P(correct half-plane)")
    for label, kw in (("jittered grid (full cover), size cv 0.3", dict(placement="grid", size_cv=0.3)),
                      ("Poisson points, size cv 0.5", dict(placement="poisson", size_cv=0.5))):
        for dens in (50, 100):
            print(f"--- {label}; {dens} facets per cm^2; diffuse fraction 0.3; single read ---")
            for name, gm in GEOMS.items():
                for R in (0.0, 0.3, 0.5, 0.8):
                    med, p90, e, p30, ph = run(gm, R, dens, **kw)
                    print(f"  {name:42s} R={R:.1f}: m1 med {med:.2f} p90 {p90:.2f} | err {e:5.1f} deg | "
                          f"P30 {p30:.2f} | Phalf {ph:.2f}")
    print("--- geometry A, jittered grid, 50 facets per cm^2: vector average of independent placements ---")
    for k in (1, 3, 5, 9):
        for R in (0.0, 0.3, 0.5):
            med, p90, e, p30, ph = run(GEOMS["A  flat LEDs r=6 h=2.2, FOV 8 mm"], R, 50, ntrial=800,
                                       placements=k, placement="grid", size_cv=0.3)
            print(f"  placements={k}: R={R:.1f}: m1 med {med:.2f} p90 {p90:.2f} | err {e:5.1f} deg | "
                  f"P30 {p30:.2f} | Phalf {ph:.2f}")


if __name__ == "__main__":
    main()
