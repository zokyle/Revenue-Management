#!/usr/bin/env python3
"""steep_sweep.py - how often the aim FLIPS on a one-microradian change of
the tilt, as a function of the steepness ratio the firmware computes
(DESIGN_SPEC E31, "TOO STEEP").  HOST ONLY; `make steep-sweep`.

The ratio (core/gl_ui.c, gl_ui_steep_ratio) uses only what the estimator
returns: the fitted patch (a, b, c, d), the distance D and the rolling
deceleration a_r:

    s_crit = a_r / ((5/7) g)            the slope a ball no longer stops on
    ratio  = max(|(a, b)|, |(a + c D, b + d D)|) / s_crit

(the slope of the fitted patch at the ball and at the hole; the gradient is
linear along the straight line between them, so its largest magnitude on
that line is at one of its ends).

For every random read the estimate is made once as measured and four times
with the tilt changed by +-1e-6 rad on one axis.  A read FLIPS when one of
the four
    - ends in another (aim_source, solve_status) class, or
    - moves the aim by more than half a display step (8 mrad; the display
      resolves about 16 mrad).
The sweep is made with the PYTHON REFERENCE (estimator.estimate_batch, its
own tolerances, near_miss_keep 5 mm as the application sets it) and, with
more reads, with the firmware's single-precision solver (the library of
`make diff`, the application's options incl. the step budget).

Output: one table per estimator, by ratio bin; the cumulative flip rate
below each candidate threshold; the threshold the firmware uses.
"""
import argparse
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import diff_solver as ds  # noqa: E402

G = 9.80665
FLIP_MRAD = 8.0
EDGES = [0.0, 0.3, 0.4, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.2, 1.4]


def ratio_of(patch, dist, a_r):
    a, b, c, d = patch[0], patch[1], patch[2], patch[3]
    s_crit = a_r / ((5.0 / 7.0) * G)
    return max(math.hypot(a, b), math.hypot(a + c * dist, b + d * dist)) / s_crit


def make_read(rng, Measurements, ph, curv):
    """One Quick Read (method B1, flag found, stereo range, base visible) on a
    patch whose slope is 0.2 to 1.4 of the critical slope of its green speed."""
    f_px, base, h_cam = 657.0, 0.02, 0.0056
    stimp = rng.uniform(6.0, 14.0)
    a_r = float(ph.stimp_to_decel(stimp))
    s_crit = a_r / ((5.0 / 7.0) * G)
    dist = rng.uniform(1.0, 10.0)
    mag = rng.uniform(0.2, 1.4) * s_crit
    ang = rng.uniform(-math.pi, math.pi)
    a, b = mag * math.cos(ang), mag * math.sin(ang)
    c, d = rng.normal(0.0, curv, 2)
    brg = rng.normal(0.0, 0.1)
    tx, ty = ds._rot(a, b, -brg)
    dz = a * dist + 0.5 * c * dist * dist
    low = math.atan((dz - h_cam + 0.00075) / dist) + rng.normal(0.0, 0.0005)
    stick = 1.96
    return Measurements(
        f_px=f_px, baseline=base, h_cam=h_cam, tilt=np.array([tx, ty]), tilt_reads=1, flag_found=True,
        flag_bearing=brg, flag_disparity=f_px * base / dist + rng.normal(0.0, 0.05), flag_low_elev=low,
        flag_base_visible=True, flag_top_visible=False, flag_top_elev=math.nan, stick_height_est=stick,
        stick_height_rel_sigma=0.07, horizon_az=np.zeros(0), horizon_elev=np.zeros(0), grain_kappa=0.0,
        grain_azimuth=0.0, stimp_ft=stimp, user_distance=math.nan)


DELTA = 1e-6  # the tilt change, rad (--delta; the E31 sweep uses one microradian)


def perturbed(m, k, dataclasses):
    t = m.tilt.copy()
    t[k // 2] += DELTA if (k % 2 == 0) else -DELTA
    return dataclasses.replace(m, tilt=t)


def table(name, rows):
    """rows: list of (ratio, flipped, class_changed, max_daim_mrad)"""
    print(f"\n{name}: {len(rows)} reads")
    print("  ratio bin      reads  flips   rate   | class changes | aim moved > 8 mrad | largest move, mrad")
    for lo, hi in zip(EDGES[:-1], EDGES[1:]):
        sel = [r for r in rows if lo <= r[0] < hi]
        if not sel:
            continue
        nf = sum(1 for r in sel if r[1])
        nc = sum(1 for r in sel if r[2])
        na = sum(1 for r in sel if r[3] > FLIP_MRAD)
        print(f"  {lo:4.2f} - {hi:4.2f}  {len(sel):6d} {nf:6d} {100.0 * nf / len(sel):6.2f} % | {nc:13d} | {na:18d} | "
              f"{max(r[3] for r in sel):8.2f}")
    print("  cumulative: reads with a ratio BELOW the threshold (what would still be shown as a normal result)")
    for thr in (0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 1.0):
        sel = [r for r in rows if r[0] < thr]
        nf = sum(1 for r in sel if r[1])
        print(f"    below {thr:4.2f}: {nf:5d} flips in {len(sel):6d} reads = {100.0 * nf / max(len(sel), 1):6.3f} %")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", required=True, help="single-precision library of `make diff` (libglsolver32.so)")
    ap.add_argument("--ref", type=int, default=3000, help="reads through the Python reference")
    ap.add_argument("--fw", type=int, default=30000, help="reads through the firmware's solver")
    ap.add_argument("--seed", type=int, default=20261118)
    ap.add_argument("--curv", type=float, default=0.0015,
                    help="sigma of the true curvatures c, d of the green, 1/m (default 0.0015)")
    ap.add_argument("--threshold", type=float, required=True, help="GL_UI_STEEP_RATIO, printed with the result")
    ap.add_argument("--delta", type=float, default=1e-6,
                    help="tilt change in rad (default 1e-6: the sweep the threshold was chosen from; "
                         "2e-4 is about the tilt noise of a read: how far a result just below the "
                         "threshold moves for that - phase-3 review, application finding 9)")
    args = ap.parse_args()
    global DELTA
    DELTA = args.delta
    if args.delta != 1e-6:
        print(f"TILT CHANGE {args.delta:g} rad (not the one microradian of the E31 sweep)")
    import dataclasses

    es, ph, _rv, Measurements = ds.load_reference()
    rng = np.random.default_rng(args.seed)
    reads = [make_read(rng, Measurements, ph, args.curv) for _ in range(max(args.ref, args.fw))]
    print(f"random Quick Reads: slope 0.2 to 1.4 of critical, green speed 6 to 14, 1 to 10 m, true curvature sigma {args.curv} /m, seed {args.seed}")

    # ---- the Python reference ----
    cfg = es.EstimatorConfig(near_miss_keep=0.005)
    batch = []
    for m in reads[:args.ref]:
        batch.append(m)
        batch.extend(perturbed(m, k, dataclasses) for k in range(4))
    out = es.estimate_batch(batch, "B1", cfg)
    rows = []
    for i in range(args.ref):
        e0 = out[5 * i]
        r = ratio_of(e0.patch, e0.distance, e0.a_r)
        cls = any((e.aim_source, int(e.solve_status)) != (e0.aim_source, int(e0.solve_status)) for e in out[5 * i + 1:5 * i + 5])
        dmax = max(1e3 * abs(ds.angle_diff(e.aim_azimuth_device, e0.aim_azimuth_device)) for e in out[5 * i + 1:5 * i + 5])
        rows.append((r, cls or dmax > FLIP_MRAD, cls, dmax))
    table("Python reference (estimator.estimate_batch, method B1, near_miss_keep 0.005)", rows)

    # ---- the firmware's solver, single precision, the application's options ----
    s = ds.Solver(args.lib, False)
    opt = s.options("B1", near_miss_m=0.005, max_steps=300000)
    rows = []
    for m in reads[:args.fw]:
        st, e0, _ = s.estimate([m], opt)
        if st != 0:
            continue
        r = ratio_of(e0["patch"], e0["distance_m"], e0["a_r_mps2"])
        cls, dmax = False, 0.0
        for k in range(4):
            st, e, _ = s.estimate([perturbed(m, k, dataclasses)], opt)
            if st != 0 or (e["aim_source"], e["solve_status"]) != (e0["aim_source"], e0["solve_status"]):
                cls = True
            else:
                dmax = max(dmax, 1e3 * abs(ds.angle_diff(e["aim_azimuth_device_rad"], e0["aim_azimuth_device_rad"])))
        rows.append((r, cls or dmax > FLIP_MRAD, cls, dmax))
    table("firmware solver, single precision (gl_solver_estimate, near_miss_m 0.005, max_steps 300000)", rows)
    print(f"\nGL_UI_STEEP_RATIO (core/gl_ui.h) = {args.threshold:.2f}: at and above it the result is shown as "
          f"TOO STEEP (dashed line)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
