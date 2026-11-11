"""Timing and closed-form checks for the physics kernels.

Run with ``python -m greenline_sim.bench`` (from the ``sim`` directory).
Prints

* the planar-break closed-form check (numerical aim angle vs.
  ``(5/14) G s / a_r``) and the 10 ft / 1 % / Stimp 10 reference point,
* the flat-green Stimp roll-out check,
* ``solve_aim`` timing statistics over random quadratic patches,
* batch throughput of ``roll_batch`` and ``solve_aim_quadratic_batch``.

Everything is deterministic except the timings themselves.
"""

from __future__ import annotations

import math
import time
from typing import Dict, List

import numpy as np

from . import physics as ph

__all__ = ["closed_form_table", "reference_point", "time_solver", "time_batches", "main"]


def closed_form_table() -> List[Dict[str, float]]:
    """Dying putt on a pure cross slope: numerical aim angle vs. small-slope theory.

    Returns one row per (cross slope, Stimp) with the theory angle
    ``(5/14) G s / a_r`` [rad], the solved angles at 2, 4 and 8 m [rad] and
    their mean ratio to theory.
    """
    rows = []
    for slope in (0.005, 0.01, 0.02):
        for stimp in (8.0, 10.0, 12.5):
            a_r = ph.stimp_to_decel(stimp)
            theory = ph.planar_break_angle(slope, a_r)
            phis = []
            for dist in (2.0, 4.0, 8.0):
                sol = ph.solve_aim(ph.PlaneSurface(0.0, slope), (0.0, 0.0), (dist, 0.0), a_r, past=0.0, tol_miss=1e-9)
                if not sol.ok:
                    raise RuntimeError(f"closed-form case did not solve: {sol}")
                phis.append(sol.phi)
            rows.append(
                {
                    "slope": slope,
                    "stimp": stimp,
                    "theory": theory,
                    "phi_2m": phis[0],
                    "phi_4m": phis[1],
                    "phi_8m": phis[2],
                    "ratio": float(np.mean(phis) / theory),
                    "spread": float(np.ptp(phis) / np.mean(phis)),
                }
            )
    return rows


def reference_point() -> Dict[str, float]:
    """10 ft putt, 1 % cross slope, Stimp 10, 0.43 m past the hole."""
    a_r = ph.stimp_to_decel(10.0)
    dist = 10.0 * ph.FT
    sol = ph.solve_aim(ph.PlaneSurface(0.0, 0.01), (0.0, 0.0), (dist, 0.0), a_r, past=0.43)
    if not sol.ok:
        raise RuntimeError(f"reference case did not solve: {sol}")
    return {
        "phi": sol.phi,
        "v0": sol.v0,
        "aim_offset": sol.aim_offset,
        "theory_phi": ph.planar_break_angle_paced(0.01, a_r, dist, 0.43),
        "theory_offset": dist * math.tan(ph.planar_break_angle_paced(0.01, a_r, dist, 0.43)),
    }


def _random_patches(n: int, seed: int, max_slope: float, curvature_sd: float):
    rng = np.random.default_rng(seed)
    slope = rng.uniform(0.0, max_slope, n)
    az = rng.uniform(0.0, 2.0 * math.pi, n)
    coeffs = np.column_stack(
        [
            slope * np.cos(az),
            slope * np.sin(az),
            rng.normal(0.0, curvature_sd, n),
            rng.normal(0.0, curvature_sd, n),
            rng.normal(0.0, curvature_sd, n),
        ]
    )
    dist = rng.uniform(1.0, 12.0, n)
    a_r = ph.stimp_to_decel(rng.uniform(8.0, 13.0, n))
    kappa = rng.uniform(0.0, 0.15, n)
    gaz = rng.uniform(0.0, 2.0 * math.pi, n)
    grain = np.column_stack([kappa * np.cos(gaz), kappa * np.sin(gaz)])
    return coeffs, dist, a_r, grain


def time_solver(n: int = 2000, seed: int = 0, max_slope: float = 0.03, curvature_sd: float = 0.002) -> Dict[str, float]:
    """Time :func:`physics.solve_aim` one call at a time over random patches.

    Patches: slope <= ``max_slope``, curvatures ~ N(0, ``curvature_sd``),
    distance 1-12 m, Stimp 8-13, grain kappa 0-0.15, past = 0.30 m.
    """
    coeffs, dist, a_r, grain = _random_patches(n, seed, max_slope, curvature_sd)
    ph.solve_aim(ph.PlaneSurface(0.0, 0.01), (0.0, 0.0), (3.0, 0.0), 0.55)  # compile / warm up
    times = np.empty(n)
    rolls = np.empty(n)
    ok = np.empty(n, dtype=bool)
    for i in range(n):
        surf = ph.QuadraticSurface(*coeffs[i])
        t0 = time.perf_counter()
        sol = ph.solve_aim(surf, (0.0, 0.0), (dist[i], 0.0), a_r[i], grain[i], 0.30)
        times[i] = time.perf_counter() - t0
        rolls[i] = sol.n_rolls
        ok[i] = sol.ok
    ms = times * 1e3
    out = {
        "n": n,
        "ok_fraction": float(ok.mean()),
        "mean_ms": float(ms.mean()),
        "median_ms": float(np.median(ms)),
        "p95_ms": float(np.percentile(ms, 95)),
        "p99_ms": float(np.percentile(ms, 99)),
        "max_ms": float(ms.max()),
        "ok_mean_ms": float(ms[ok].mean()),
        "ok_median_rolls": float(np.median(rolls[ok])),
        "ok_p95_rolls": float(np.percentile(rolls[ok], 95)),
    }
    if (~ok).any():
        out["failed_mean_ms"] = float(ms[~ok].mean())
        out["failed_mean_rolls"] = float(rolls[~ok].mean())
    return out


def time_batches(n: int = 20000, seed: int = 1) -> Dict[str, float]:
    """Wall-clock throughput of the batch kernels (all available threads)."""
    coeffs, dist, a_r, grain = _random_patches(n, seed, 0.03, 0.002)
    ph.solve_aim_quadratic_batch(coeffs[:8], dist[:8], a_r[:8], grain[:8])
    t0 = time.perf_counter()
    sol = ph.solve_aim_quadratic_batch(coeffs, dist, a_r, grain)
    t_solve = time.perf_counter() - t0

    surf = ph.QuadraticSurface(0.012, -0.008, 0.002, 0.001, -0.002)
    grid = ph.GridSurface.from_function(surf.z, (-12.0, 20.0), (-16.0, 16.0), 0.5)
    a10 = ph.stimp_to_decel(10.0)
    aim = ph.solve_aim(grid, (0.0, 0.0), (6.0, 0.0), a10)
    rng = np.random.default_rng(seed)
    phi = aim.phi + rng.normal(0.0, math.radians(1.0), n)
    v0 = aim.v0 * (1.0 + rng.normal(0.0, 0.06, n))
    ph.roll_batch(grid, (0.0, 0.0), (6.0, 0.0), phi[:8], v0[:8], a10)
    t0 = time.perf_counter()
    rolls = ph.roll_batch(grid, (0.0, 0.0), (6.0, 0.0), phi, v0, a10)
    t_roll = time.perf_counter() - t0
    return {
        "n": n,
        "solve_batch_ms_per_solve": t_solve / n * 1e3,
        "solve_batch_ok_fraction": float(sol.ok.mean()),
        "roll_batch_us_per_roll": t_roll / n * 1e6,
        "roll_batch_make_fraction": float(rolls.captured.mean()),
    }


def main() -> None:
    print(f"greenline_sim physics benchmark   [{ph.NUMBA_STATUS}]   default dt = {ph.DEFAULT_DT} s")

    print("\nFlat green: roll-out from the Stimpmeter speed 1.83 m/s")
    for stimp in (8.0, 10.0, 12.0):
        a_r = ph.stimp_to_decel(stimp)
        r = ph.simulate_putt(ph.PlaneSurface(0.0, 0.0), (0.0, 0.0), (1.0, 0.0), 0.0, ph.STIMP_V0, a_r)
        print(f"  Stimp {stimp:4.1f}: a_r = {a_r:.4f} m/s^2, rolled {r.stop_xy[0] / ph.FT:.6f} ft")

    print("\nDying putt on a pure cross slope: phi vs (5/14) G s / a_r")
    print("  slope  stimp   theory[rad]   phi@2m      phi@4m      phi@8m      ratio    spread")
    for row in closed_form_table():
        print(
            f"  {row['slope'] * 100:4.1f}%  {row['stimp']:5.1f}   {row['theory']:.6f}    "
            f"{row['phi_2m']:.6f}    {row['phi_4m']:.6f}    {row['phi_8m']:.6f}    "
            f"{row['ratio']:.4f}   {row['spread']:.1e}"
        )
    ref = reference_point()
    print(
        "\nReference: 10 ft, 1 % cross slope, Stimp 10, 0.43 m past -> "
        f"aim offset {ref['aim_offset']:.4f} m (phi {ref['phi']:.5f} rad, v0 {ref['v0']:.4f} m/s); "
        f"paced small-slope formula {ref['theory_offset']:.4f} m"
    )

    quick = not ph.HAVE_NUMBA
    stats = time_solver(n=200 if quick else 2000)
    print("\nsolve_aim, one call at a time, random quadratic patches (past = 0.30 m):")
    for key, val in stats.items():
        print(f"  {key:20s} {val:.4g}")
    batch = time_batches(n=200 if quick else 20000)
    print("\nBatch kernels (wall clock, all threads):")
    for key, val in batch.items():
        print(f"  {key:28s} {val:.4g}")


if __name__ == "__main__":
    main()
