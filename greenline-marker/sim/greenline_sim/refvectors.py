"""Reference vectors for the firmware port of the estimator and the aim solver.

``python -m greenline_sim.refvectors`` (or the Monte Carlo) writes

* ``results/reference_vectors.json`` - seeded cases
  ``Measurements -> fitted patch, aim angle, launch speed, plays-like
  distance, break, ...`` for the estimator, and ``surface -> aim`` cases for
  :func:`greenline_sim.physics.solve_aim` on analytic surfaces;
* ``results/REFERENCE_VECTORS.md`` - the schema and the comparison rules.

Everything is generated with tight tolerances (aim solver 1e-9 m, fit step
1e-10 in scaled units) so that an independent C implementation, whose
iteration path will differ, can be compared at 1e-4 relative tolerance.

Every fitted case is also checked for start-independence: the fit is re-run
from a set of other starting points and with other initial damping values,
and the lowest cost found is stored next to the cost of the reference
result (``fit_check``).  A case whose minimum depended on the start could
not be reproduced by a port with a different iteration path; none is
expected with the default estimator (convex Quick-Read fit, anchored horizon
fit), and the test-suite asserts that there is none.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, replace
from typing import List, Optional

import numpy as np

from . import estimator as es
from . import physics as ph
from . import sensors as se
from .greens import GREEN_CLASSES, make_scenario

__all__ = ["SCHEMA_VERSION", "reference_config", "build_reference_vectors", "write_reference_vectors", "main"]

SCHEMA_VERSION = 2

_DISTANCES = (1.5, 3.0, 4.5, 6.0, 9.0, 12.0)
_MODES = ("B1", "B2", "B0", "PRECISION", "SURVEY3", "B2", "B1_GRAIN", "FLAG_OUT", "SURVEY2", "B2")
_SOLVER_TOL = 1e-9
_N_RANGE_MISSING = 4  # hand-modified cases at the end: flag found but not ranged
_CHECK_STARTS = 16  # random starts of the start-independence check (plus the corner starts)
_CHECK_LAMBDAS = (1e-6, 1e-2, 1.0)  # other initial damping values tried from the reference start
_SCALE5 = np.array([1e-2, 1e-2, 1e-3, 1e-3, 1e-3])


def reference_config() -> es.EstimatorConfig:
    """The estimator configuration the vectors are generated with: the
    defaults, with the convergence tolerances tightened."""
    return replace(es.EstimatorConfig(), tol_miss=_SOLVER_TOL, tol_pace=_SOLVER_TOL, lm_tol=1e-10, lm_max_iter=200)


def _num(value):
    value = float(value)
    return value if math.isfinite(value) else None


def _estimate_record(est: es.Estimate) -> dict:
    fit = est.fit
    return {
        "patch": [_num(v) for v in est.patch],
        "level_offsets": [_num(v) for v in fit.level_offsets],
        "distance": _num(est.distance),
        "distance_sigma": _num(est.distance_sigma),
        "range_stereo": _num(fit.range.stereo),
        "range_mono": _num(fit.range.mono),
        "bearing": _num(est.bearing),
        "stations": [_num(v) for v in fit.stations],
        "phi": _num(est.phi),
        "aim_azimuth_device": _num(est.aim_azimuth_device),
        "v0": _num(est.v0),
        "plays_like": _num(est.plays_like),
        "break_m": _num(est.break_m),
        "break_cups": _num(est.break_cups),
        "slope_pct": _num(est.slope_pct),
        "fall_line_azimuth": _num(est.fall_line_azimuth),
        "dz_hole": _num(est.dz_hole),
        "cross_slope_sigma": _num(est.cross_slope_sigma),
        "confidence": _num(est.confidence),
        "a_r": _num(est.a_r),
        "grain": [_num(v) for v in est.grain],
        "base_hidden": bool(est.base_hidden),
        "flag_missing": bool(est.flag_missing),
        "tilt_slopes": [_num(v) for v in fit.tilt_slopes],
        "range_missing": bool(est.range_missing),
        "poor_horizon": bool(est.poor_horizon),
        "used_horizon": bool(fit.used_horizon),
        "aim_source": int(est.aim_source),
        "solve_status": int(est.solve_status),
        "fit_converged": bool(fit.converged),
        "fit_cost": _num(fit.cost),
        "fit_starts": int(fit.n_starts),
    }


def _fit_check(drops, method: str, config: es.EstimatorConfig, fit: es.PatchFit, rng: np.random.Generator) -> dict:
    """Start-independence of one fitted case.

    Re-runs the fit from ``_CHECK_STARTS`` random starts (slopes within
    10 mrad of the result, curvatures ~ N(0, 0.005 1/m), level offsets
    ~ N(0, 2 mrad)), from the 24 corner starts of the joint search, and from
    the reference start with other initial damping values.  Returns the
    lowest cost found, the largest patch difference among the runs that
    reach the reference cost, and ``start_independent``: no run found a
    lower cost (relative 1e-6) and every run at the reference cost has the
    same patch to 1e-6 of the parameter scale.
    """
    starts = []
    for _ in range(_CHECK_STARTS):
        x = np.zeros(7)
        x[:2] = fit.coeffs[:2] + rng.normal(0.0, 0.01, 2)
        x[2:5] = rng.normal(0.0, 0.005, 3)
        x[5:] = rng.normal(0.0, 0.002, 2)
        starts.append(x)
    tilt_plane = np.zeros(7)
    tilt_plane[:2] = fit.tilt_slopes
    starts.extend(es._corner_starts(tilt_plane, es._START_CURVATURES_JOINT))
    runs = [es.fit_patch(drops, method, config, start=x) for x in starts]
    runs += [es.fit_patch(drops, method, replace(config, lm_lambda0=lam)) for lam in _CHECK_LAMBDAS]
    lowest = min([fit.cost] + [r.cost for r in runs])
    tol = 1e-6 * (1.0 + fit.cost)
    at_ref = [r for r in runs if r.cost <= fit.cost + tol]
    spread = max([float(np.max(np.abs(r.coeffs - fit.coeffs) / _SCALE5)) for r in at_ref], default=0.0)
    return {
        "n_runs": len(runs),
        "cost": _num(fit.cost),
        "lowest_cost_found": _num(lowest),
        "max_patch_difference_scaled": spread,
        "start_independent": bool(lowest >= fit.cost - tol and spread < 1e-6),
    }


def _estimator_cases(n: int, seed: int, config: es.EstimatorConfig) -> List[dict]:
    params = se.SensorParams()
    cases: List[dict] = []
    n_regular = max(n - _N_RANGE_MISSING, 0)
    k = 0
    while len(cases) < n:
        cls = GREEN_CLASSES[k % len(GREEN_CLASSES)]
        dist = _DISTANCES[(k // len(GREEN_CLASSES)) % len(_DISTANCES)]
        mode = _MODES[k % len(_MODES)] if len(cases) < n_regular else "RANGE_MISSING"
        green_seed = seed % 1000 + k // (len(GREEN_CLASSES) * len(_DISTANCES))
        sc = make_scenario(cls, dist, green_seed)
        rng = np.random.default_rng([seed, k])
        k += 1
        overrides: dict = {}
        if mode == "FLAG_OUT":
            drops = [se.measure(sc.green, sc.ball_xy, sc.hole_xy, params, rng, mode="flag_out")[0]]
            method = "B0"
        elif mode == "PRECISION":
            drops = [se.measure(sc.green, sc.ball_xy, sc.hole_xy, params, rng, spin=True, with_horizon=False)[0]]
            method = "B1"
        elif mode in ("SURVEY2", "SURVEY3"):
            drops = [m for m, _ in se.measure_survey(sc.green, sc.ball_xy, sc.hole_xy, params, rng, n_drops=int(mode[-1]))]
            method = "B1"
        elif mode == "B1_GRAIN":
            drops = [se.measure(sc.green, sc.ball_xy, sc.hole_xy, params, rng, with_horizon=False)[0]]
            method = "B1"
            overrides = {"use_grain": True}
        elif mode == "RANGE_MISSING":
            # a found flag whose stereo disparity is below the accepted minimum and whose top is out of the field
            meas = se.measure(sc.green, sc.ball_xy, sc.hole_xy, params, rng, with_horizon=False)[0]
            if not meas.flag_found:
                continue
            drops = [replace(meas, flag_disparity=0.8 * config.min_disparity, flag_top_visible=False, flag_top_elev=math.nan)]
            method = "B1"
        else:
            drops = [se.measure(sc.green, sc.ball_xy, sc.hole_xy, params, rng, with_horizon=(mode == "B2"))[0]]
            method = mode
        cfg = replace(config, **overrides)
        est = es.estimate_batch([drops], method, cfg)[0]
        if not est.fit.converged:
            continue  # never observed; such a case would be useless as a reference
        fitted = method in ("B1", "B2") and not (est.flag_missing or est.range_missing)
        check = _fit_check(drops, method, cfg, est.fit, np.random.default_rng([seed, k, 7])) if fitted else None
        cases.append(
            {
                "id": len(cases),
                "green_class": cls,
                "green_seed": green_seed,
                "nominal_distance": dist,
                "mode": mode,
                "method": method,
                "config_overrides": overrides,
                "start_independent": True if check is None else check["start_independent"],
                "fit_check": check,
                "measurements": [m.to_dict() for m in drops],
                "expected": _estimate_record(est),
            }
        )
    return cases


def _solver_cases(n: int, seed: int) -> List[dict]:
    rng = np.random.default_rng([seed, 99])
    rows: List[dict] = []

    def add(coeffs, dist, stimp, kappa, grain_az, past, tag):
        a_r = ph.stimp_to_decel(stimp)
        grain = np.array([kappa * math.cos(grain_az), kappa * math.sin(grain_az)])
        sol = ph.solve_aim_quadratic_batch(
            np.asarray(coeffs, dtype=float), dist, a_r, grain, past, tol_miss=_SOLVER_TOL, tol_pace=_SOLVER_TOL
        )
        status = ph.SolveStatus(int(sol.status[0]))
        rows.append(
            {
                "id": len(rows),
                "tag": tag,
                "coeffs": [float(v) for v in coeffs],
                "distance": float(dist),
                "stimp_ft": float(stimp),
                "a_r": float(a_r),
                "grain": [float(grain[0]), float(grain[1])],
                "past": float(past),
                "status": int(status),
                "status_name": status.name,
                "compare_values": bool(status == ph.SolveStatus.OK),
                "phi": _num(sol.phi[0]),
                "v0": _num(sol.v0[0]),
                "v_hole": _num(sol.v_hole[0]),
                "miss": _num(sol.miss[0]),
                "plays_like": _num(sol.plays_like[0]),
                "aim_offset": _num(sol.aim_offset[0]),
            }
        )

    # fixed anchors: flat, the closed-form dying putt, the 10 ft reference point, grain as a slope
    add((0, 0, 0, 0, 0), 3.0, 10.0, 0.0, 0.0, 0.30, "flat")
    for slope in (0.005, 0.01, 0.02):
        for stimp in (8.0, 10.0, 12.5):
            add((0, slope, 0, 0, 0), 4.0, stimp, 0.0, 0.0, 0.0, "closed-form: dying putt on a pure cross slope")
    add((0, 0.01, 0, 0, 0), 10.0 * ph.FT, 10.0, 0.0, 0.0, 0.43, "reference point: 10 ft, 1 % cross slope, Stimp 10, 0.43 m past")
    add((0, 0, 0, 0, 0), 5.0, 10.0, 0.1, math.pi / 2, 0.30, "grain only (pushes left)")
    add((0.02, 0, 0, 0, 0), 6.0, 10.0, 0.0, 0.0, 0.30, "uphill")
    add((-0.02, 0, 0, 0, 0), 6.0, 10.0, 0.0, 0.0, 0.30, "downhill")
    add((-0.07, 0, 0, 0, 0), 6.0, 13.0, 0.0, 0.0, 0.30, "downhill steeper than the green can hold (status only)")
    add((0.0, 0.075, 0, 0, 0), 8.0, 13.0, 0.0, 0.0, 0.30, "cross slope steeper than the green can hold (status only)")
    # regressions: a ball stopping with a slope at 0.9 of critical (stiff stop), and a long twisted
    # patch on which the lowest-energy crossing of the hole line is metres away from the hole
    s90 = 0.90 * ph.critical_slope(ph.stimp_to_decel(10.0))
    add((-s90 * math.cos(0.15), -s90 * math.sin(0.15), 0.0005, 0.001, 0.001), 2.5, 10.0, 0.0, 0.0, 0.05,
        "regression: paced putt down a slope at 0.9 of critical")
    add((0.0015494940810168451, 0.0007377930191904871, 0.0011549920136925864, -0.006981195744842645, -0.0039816409861887754),
        11.0017, 9.099, 0.14500987074957827, 2.7742995356265223, 0.30,
        "regression: far crossing of the hole line is not reaching the hole")
    while len(rows) < n:
        kind = len(rows) % 3
        slope = rng.uniform(0.0, 0.03)
        az = rng.uniform(0.0, 2.0 * math.pi)
        curv = np.zeros(3) if kind == 0 else rng.normal(0.0, 0.002, size=3)
        coeffs = (slope * math.cos(az), slope * math.sin(az), curv[0], curv[1], curv[2])
        dist = float(rng.uniform(1.0, 12.0))
        stimp = float(rng.uniform(8.0, 13.0))
        kappa = 0.0 if kind == 1 else float(rng.uniform(0.0, 0.15))
        past = float(rng.choice([0.30, 0.30, 0.30, 0.15, 0.45]))
        add(coeffs, dist, stimp, kappa, float(rng.uniform(0.0, 2.0 * math.pi)), past,
            ("plane", "quadratic, no grain", "quadratic with grain")[kind])
    return rows


def build_reference_vectors(n_estimator: int = 240, n_solver: int = 120, seed: int = 20261111) -> dict:
    """Generate the reference vectors (deterministic for a given seed).

    Parameters
    ----------
    n_estimator : int
        Number of estimator cases (cycling through the green classes, the
        putt lengths and the modes B0 / B1 / B2 / Precision Read / Survey /
        flag-out / B1 with the grain reading; the last four are "flag found
        but not ranged" cases).
    n_solver : int
        Number of aim-solver cases on analytic surfaces.
    seed : int
    """
    config = reference_config()
    return {
        "schema_version": SCHEMA_VERSION,
        "generator": "greenline_sim.refvectors",
        "seed": seed,
        "units": "SI (m, s, rad); slopes as rise/run; stimp in feet",
        "constants": {
            "G": ph.G,
            "STIMP_V0": ph.STIMP_V0,
            "FT": ph.FT,
            "HOLE_R": ph.HOLE_R,
            "ROLL_FACTOR": ph.ROLL_FACTOR,
            "DT": ph.DEFAULT_DT,
            "T_MAX": ph.DEFAULT_T_MAX,
            "PHI_MAX": ph.DEFAULT_PHI_MAX,
            "V_MAX": ph.DEFAULT_V_MAX,
            "MAX_ROLLS": ph.DEFAULT_MAX_ROLLS,
            "H_STIFF": ph._H_STIFF,
            "STEP_BUDGET_FACTOR": ph._STEP_BUDGET_FACTOR,
            "LINE_MISS_OFFSET": ph._LINE_MISS_OFFSET,
            "LINE_MISS_SLOPE": ph._LINE_MISS_SLOPE,
        },
        "estimator_config": asdict(config),
        "solver_tolerances": {"tol_miss": _SOLVER_TOL, "tol_pace": _SOLVER_TOL},
        "estimator_cases": _estimator_cases(n_estimator, seed, config),
        "solver_cases": _solver_cases(n_solver, seed),
    }


_SCHEMA_MD = """# GreenLine reference vectors (schema version {version})

`reference_vectors.json` is generated by `python -m greenline_sim.refvectors`
(seed {seed}) from the Python reference in `sim/greenline_sim`. It holds
{n_est} estimator cases and {n_sol} aim-solver cases for testing the C port.
All numbers are SI (metres, seconds, radians, slopes as rise/run); the green
speed is in feet (`stimp_ft`). JSON `null` stands for "not a number / not
available". Floats are written with 17 significant digits.

Hardware revision C: `f_px` = {f_px:g}, `baseline` = {baseline:g} m,
`h_cam` = {h_cam:g} m. These travel inside every `Measurements` record; the
estimator has no camera constants of its own.

## Top level

| Key | Content |
| --- | --- |
| `schema_version`, `seed` | version of this layout; seed of the generator |
| `constants` | physical and solver constants (`G`, `STIMP_V0`, `FT`, `HOLE_R`, `ROLL_FACTOR`, integrator step `DT`, solver limits, and the roll-kernel constants `H_STIFF`, `STEP_BUDGET_FACTOR`, `LINE_MISS_OFFSET`, `LINE_MISS_SLOPE`) |
| `estimator_config` | every field of `EstimatorConfig` used to generate the estimator cases: the firmware defaults (grain reading NOT used, `B2` anchored), except `tol_miss = tol_pace = 1e-9`, `lm_tol = 1e-10`, `lm_max_iter = 200` |
| `solver_tolerances` | `tol_miss`, `tol_pace` used for the solver cases (1e-9 m) |
| `estimator_cases` | list, see below |
| `solver_cases` | list, see below |

## Estimator cases

Each case is one read of the device on a seeded synthetic green
(`green_class`, `green_seed`, `nominal_distance` are for traceability only;
the C code must not need them).

| Key | Content |
| --- | --- |
| `id` | running number |
| `mode` | how the read was taken: `B0`, `B1`, `B2`, `PRECISION` (spin-and-reread, `tilt_reads = 2`), `SURVEY2`, `SURVEY3`, `FLAG_OUT`, `B1_GRAIN` (a `B1` read solved WITH the grain reading), `RANGE_MISSING` (flag found, bearing valid, disparity below `min_disparity`: the measured bearing is kept and the distance falls back to the default) |
| `method` | the estimator method to call: `B0`, `B1` or `B2` (`PRECISION`, `SURVEY*`, `B1_GRAIN` and `RANGE_MISSING` use `B1`; `FLAG_OUT` uses `B0`) |
| `config_overrides` | fields of `estimator_config` that differ for this case (`{{"use_grain": true}}` for `B1_GRAIN`, otherwise empty) |
| `measurements` | list of placements, ball first: one entry, or the Survey drops. Each entry is a `Measurements` record (fields below) |
| `start_independent` | `true` if no other starting point or initial damping reaches a lower cost, and all that reach the same cost give the same patch (see `fit_check`). {n_single} of the {n_fit} fitted cases are `true`, {n_multi} are `false` |
| `fit_check` | for fitted cases: `n_runs` (alternative runs made: {n_check} random starts, the 24 corner starts with curvatures of 0.002 / 0.005 / 0.012 1/m, and the reference start with `lm_lambda0` = 1e-6, 1e-2, 1), `cost` of the reference result, `lowest_cost_found`, `max_patch_difference_scaled` (largest difference, in units of 1e-2 for slopes and 1e-3 1/m for curvatures, among the runs that reach the reference cost). `null` for cases without a fit |
| `expected` | outputs, see below |

`Measurements` fields (device frame: +x out of the visor, +y left, angles
counter-clockwise from +x; elevations relative to the gravity-level plane):
`f_px` [px], `baseline` [m], `h_cam` [m] nominal lens height above the base
plane, `tilt` [2] measured surface gradient (dz/dx, dz/dy), `tilt_reads`
(1 or 2), `flag_found`, `flag_bearing` [rad], `flag_disparity` [px],
`flag_low_elev` [rad] lowest visible point of the stick,
`flag_base_visible`, `flag_top_visible`, `flag_top_elev` [rad],
`stick_height_est` [m], `stick_height_rel_sigma`, `horizon_az` [n] [rad],
`horizon_elev` [n] [rad] (empty lists when no horizon was captured),
`grain_kappa`, `grain_azimuth` [rad], `stimp_ft` [ft], `user_distance` [m].

`expected` fields:

| Key | Content |
| --- | --- |
| `patch` | fitted `(a, b, c, d, e)` of `z = a x + b y + 0.5 (c x^2 + 2 d x y + e y^2)` in the putt frame (origin at the marker, +x toward the hole along the measured flag bearing, +y left) |
| `level_offsets` | fitted pitch and roll offsets of the camera level reference [rad] (zero unless `used_horizon`) |
| `distance`, `distance_sigma` | ball-to-hole distance used and its 1-sigma [m] |
| `range_stereo`, `range_mono` | the two range channels of the first placement [m] |
| `bearing` | direction of the hole in the device frame [rad] (0 when `flag_missing`; the measured flag bearing when `range_missing`) |
| `stations` | stations of the placements used by the fit, along the line [m] |
| `phi` | aim angle relative to the line to the hole, positive = left [rad] |
| `aim_azimuth_device` | `bearing + phi`, the line the display draws [rad] (before the display quantises it) |
| `v0` | launch speed [m/s] |
| `plays_like` | `v0^2 / (2 a_r)` [m] |
| `break_m`, `break_cups` | `distance * tan(phi)` in metres and in cup widths (0.10795 m) |
| `tilt_slopes` | the tilt reading of the placement at the ball rotated into the putt frame [2] |
| `slope_pct`, `fall_line_azimuth` | slope at the ball [%] and direction of steepest descent in the putt frame [rad], both from `tilt_slopes` (NOT from `patch`) |
| `dz_hole` | fitted hole height above the ball, `a D + 0.5 c D^2` [m] |
| `cross_slope_sigma`, `confidence` | 1-sigma of the mean cross slope as known from the tilt readings (`PatchFit.cross_sigma_read`); confidence score in [0, 1] |
| `a_r`, `grain` | rolling deceleration from the entered Stimp [m/s^2]; grain `kappa * g_hat` used by the solve, in the putt frame (zero unless `use_grain`) |
| `base_hidden`, `flag_missing`, `range_missing`, `poor_horizon`, `used_horizon`, `fit_converged` | flags |
| `fit_cost`, `fit_starts` | robust MAP cost at the solution and the number of starts run (1 for `B1`, 5 for `B2` with a horizon, 0 without a fit) |
| `aim_source` | 0 solved on the patch, 1 on its secant plane, 2 best iterate, 3 straight |
| `solve_status` | `SolveStatus` of the aim solve (0 OK, 1 PACE_LIMITED, 2 UNREACHABLE, 3 NO_BRACKET, 4 NO_CONVERGENCE, 5 INVALID) |

### The fit the port has to reproduce

Parameters `x = (a, b, c, d, e, pitch offset, roll offset)`; residual rows,
priors, Huber threshold and the Levenberg-Marquardt rules are in
`estimator.py` (`_fit_residuals`, `_fit_lm`, `_chol_solve`).

* `B1` (also `PRECISION`, `SURVEY*`, `B1_GRAIN`): one run from
  `x0 = (a_tilt, b_tilt, 0, 0, 0, 0, 0)` without horizon rows. The cost is
  convex: any correct minimiser reaches the same patch.
* `B2`: stage 1 is the `B1` fit. Stage 2 holds `a`, `b` and `c` at the
  stage-1 values and minimises over `d`, `e` and the two offsets with the
  horizon rows added. In stage 2 the prior sigma of the pitch offset is
  `hypot(sigma_level, sigma_silhouette)` (it stands for the unknown height of
  the silhouette); the roll offset keeps `sigma_level`. Starts: the stage-1
  solution, then the stage-1 solution with `(d, e)` replaced by
  `(sd, se) * 0.003` 1/m for `sd, se` in `(-1, +1)`, nested in that order
  (`se` innermost). The lowest cost wins; a later start replaces the current
  best only if its cost is lower by more than `1e-9 * (1 + cost)`. The
  stage-2 cost is not convex in principle, but in every case of this file
  whose `start_independent` is `true` all {n_check_total} alternative runs end
  at the same minimum, so a port that minimises the same cost from the same 5
  starts needs no particular iteration path.

## Solver cases

`solve_aim` on the analytic surface `z = a x + b y + 0.5 (c x^2 + 2 d x y + e y^2)`
with the ball at the origin and the hole at `(distance, 0)`.

| Key | Content |
| --- | --- |
| `id`, `tag` | running number; what the case is (the first {n_anchor} are fixed anchors, including the closed-form dying putt `phi = (5/14) G s / a_r`, the 10 ft / 1 % / Stimp 10 / 0.43 m point, and two regression cases of the roll kernel and the solver) |
| `coeffs` | `(a, b, c, d, e)` |
| `distance` [m], `stimp_ft` [ft], `a_r` [m/s^2] | putt length and green speed (`a_r = 1.83^2 / (2 * stimp_ft * 0.3048)`) |
| `grain` | `kappa * g_hat`, two components in the surface frame |
| `past` | target pace: flat-green roll-out beyond the hole [m] |
| `status`, `status_name` | `SolveStatus` |
| `compare_values` | `true` when the status is OK: then `phi`, `v0`, `plays_like`, `aim_offset` must match. Otherwise only the status class (solved / not solved) is expected to match; the best iterate of a failed solve depends on the iteration path |
| `phi` [rad], `v0` [m/s], `v_hole` [m/s], `miss` [m] | solution, arrival speed at the hole line, residual lateral miss |
| `plays_like` [m], `aim_offset` [m] | `v0^2 / (2 a_r)` and `distance * tan(phi)` |

Two rules of the Python kernel that a port must copy to reproduce these
numbers (both are in `physics.py`):

* near the stop the RK4 step is the smallest of `DT`, half the predicted
  time-to-stop, and `H_STIFF * speed / a_r`; a roll takes at most
  `STEP_BUDGET_FACTOR * (int(T_MAX / DT) + 1)` steps;
* a trial ball that crosses the infinite hole line further than
  `LINE_MISS_OFFSET + LINE_MISS_SLOPE * distance` to the side counts as not
  having reached the hole.

## How to compare

Relative tolerance 1e-4 on every floating-point output, with these absolute
floors for quantities that pass through zero:

| Quantity | Absolute floor |
| --- | --- |
| `phi`, `aim_azimuth_device`, `bearing`, `fall_line_azimuth` | 1e-6 rad (compare `fall_line_azimuth` only when `slope_pct` > 0.01; compare angles modulo 2 pi) |
| `patch[0..1]` (slopes), `tilt_slopes` | 1e-7 |
| `patch[2..4]` (curvatures), `level_offsets` | 1e-8 |
| `break_m`, `aim_offset`, `dz_hole` | 1e-6 m |
| `break_cups` | 1e-5 |
| `confidence` | 1e-6 |
| `fit_cost` | 1e-6 |

`v0`, `plays_like`, `distance` and `a_r` are never near zero and need no
floor. Flags, `aim_source`, `solve_status` and `fit_starts` must match
exactly.

Why the vectors are generated with tighter tolerances than the defaults: at
the default solver tolerance (1e-5 m) the solution is only pinned to about
3e-5 m of lateral position at the hole, which for a small `phi` is of the
order of the 1e-4 comparison itself. With 1e-9 m both implementations
converge to the same solution of the discretised model (fixed RK4 step
`DT`), whatever their iteration path. The C port must use the same `DT`.

Not covered by these vectors: the joint horizon fit
(`EstimatorConfig.horizon_joint`), which exists in the Python reference for
comparison only. Its cost has many local minima and its result depends on
the iteration path, so it is not a port target.
"""


def write_reference_vectors(out_dir: str, n_estimator: int = 240, n_solver: int = 120, seed: int = 20261111) -> dict:
    """Write ``reference_vectors.json`` and ``REFERENCE_VECTORS.md`` into ``out_dir``."""
    data = build_reference_vectors(n_estimator, n_solver, seed)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "reference_vectors.json"), "w") as fh:
        json.dump(data, fh, indent=1, allow_nan=False)
    fitted = [c for c in data["estimator_cases"] if c["fit_check"] is not None]
    n_anchor = sum(1 for c in data["solver_cases"] if c["tag"] not in ("plane", "quadratic, no grain", "quadratic with grain"))
    cam = se.GL1
    text = _SCHEMA_MD.format(
        version=SCHEMA_VERSION,
        seed=seed,
        n_est=len(data["estimator_cases"]),
        n_sol=len(data["solver_cases"]),
        n_anchor=n_anchor,
        n_multi=sum(1 for c in fitted if not c["start_independent"]),
        n_single=sum(1 for c in fitted if c["start_independent"]),
        n_fit=len(fitted),
        n_check=_CHECK_STARTS,
        n_check_total=_CHECK_STARTS + 24 + len(_CHECK_LAMBDAS),
        f_px=cam.f_px,
        baseline=cam.baseline,
        h_cam=cam.h_cam,
    )
    with open(os.path.join(out_dir, "REFERENCE_VECTORS.md"), "w") as fh:
        fh.write(text)
    return data


def main(argv: Optional[List[str]] = None) -> int:
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
    data = write_reference_vectors(out_dir)
    print(f"wrote {len(data['estimator_cases'])} estimator and {len(data['solver_cases'])} solver cases to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
