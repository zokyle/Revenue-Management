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

SCHEMA_VERSION = 1

_DISTANCES = (1.5, 3.0, 4.5, 6.0, 9.0, 12.0)
_MODES = ("B1", "B2", "B0", "PRECISION", "SURVEY3", "B2", "B1", "FLAG_OUT", "SURVEY2", "B2")
_SOLVER_TOL = 1e-9


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
        "poor_horizon": bool(est.poor_horizon),
        "used_horizon": bool(fit.used_horizon),
        "aim_source": int(est.aim_source),
        "solve_status": int(est.solve_status),
        "fit_converged": bool(fit.converged),
    }


def _estimator_cases(n: int, seed: int, config: es.EstimatorConfig) -> List[dict]:
    params = se.SensorParams()
    cases: List[dict] = []
    k = 0
    while len(cases) < n:
        cls = GREEN_CLASSES[k % len(GREEN_CLASSES)]
        dist = _DISTANCES[(k // len(GREEN_CLASSES)) % len(_DISTANCES)]
        mode = _MODES[k % len(_MODES)]
        green_seed = seed % 1000 + k // (len(GREEN_CLASSES) * len(_DISTANCES))
        sc = make_scenario(cls, dist, green_seed)
        rng = np.random.default_rng([seed, k])
        k += 1
        if mode == "FLAG_OUT":
            drops = [se.measure(sc.green, sc.ball_xy, sc.hole_xy, params, rng, mode="flag_out")[0]]
            method = "B0"
        elif mode == "PRECISION":
            drops = [se.measure(sc.green, sc.ball_xy, sc.hole_xy, params, rng, spin=True, with_horizon=False)[0]]
            method = "B1"
        elif mode in ("SURVEY2", "SURVEY3"):
            drops = [m for m, _ in se.measure_survey(sc.green, sc.ball_xy, sc.hole_xy, params, rng, n_drops=int(mode[-1]))]
            method = "B1"
        else:
            drops = [se.measure(sc.green, sc.ball_xy, sc.hole_xy, params, rng, with_horizon=(mode == "B2"))[0]]
            method = mode
        est = es.estimate_batch([drops], method, config)[0]
        if not est.fit.converged:
            continue  # never observed; such a case would be useless as a reference
        # does the fitted minimum depend on where the iteration starts?
        start_independent = True
        if method in ("B1", "B2") and not est.flag_missing:
            alt = es.fit_patch(drops, method, config, start=np.zeros(7))
            scale = np.array([1e-2, 1e-2, 1e-3, 1e-3, 1e-3])
            start_independent = bool(np.max(np.abs(alt.coeffs - est.patch) / scale) < 1e-6)
        cases.append(
            {
                "id": len(cases),
                "green_class": cls,
                "green_seed": green_seed,
                "nominal_distance": dist,
                "mode": mode,
                "method": method,
                "start_independent": start_independent,
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
        flag-out).
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

## Top level

| Key | Content |
| --- | --- |
| `schema_version`, `seed` | version of this layout; seed of the generator |
| `constants` | physical and solver constants (`G`, `STIMP_V0`, `FT`, `HOLE_R`, `ROLL_FACTOR`, integrator step `DT`, solver limits) |
| `estimator_config` | every field of `EstimatorConfig` used to generate the estimator cases: the defaults, except `tol_miss = tol_pace = 1e-9`, `lm_tol = 1e-10`, `lm_max_iter = 200` |
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
| `mode` | how the read was taken: `B0`, `B1`, `B2`, `PRECISION` (spin-and-reread, `tilt_reads = 2`), `SURVEY2`, `SURVEY3`, `FLAG_OUT` |
| `method` | the estimator method to call: `B0`, `B1` or `B2` (`PRECISION` and `SURVEY*` use `B1`; `FLAG_OUT` uses `B0`) |
| `measurements` | list of placements, ball first: one entry, or the Survey drops. Each entry is a `Measurements` record (fields below) |
| `start_independent` | `true` if the fit reaches the same patch (to 1e-6 of the parameter scale) from an all-zero start as from the reference start. Where `false`, the cost has more than one minimum and the port must use the reference start to reproduce the numbers |
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
| `bearing` | direction of the hole in the device frame [rad] (0 when `flag_missing`) |
| `stations` | stations of the placements used by the fit, along the line [m] |
| `phi` | aim angle relative to the line to the hole, positive = left [rad] |
| `aim_azimuth_device` | `bearing + phi`, the line the display draws [rad] |
| `v0` | launch speed [m/s] |
| `plays_like` | `v0^2 / (2 a_r)` [m] |
| `break_m`, `break_cups` | `distance * tan(phi)` in metres and in cup widths (0.10795 m) |
| `slope_pct`, `fall_line_azimuth` | slope at the ball [%] and direction of steepest descent in the putt frame [rad] |
| `dz_hole` | fitted hole height above the ball, `a D + 0.5 c D^2` [m] |
| `cross_slope_sigma`, `confidence` | posterior sigma of the mean cross slope `b + 0.5 d D`; confidence score in [0, 1] |
| `a_r`, `grain` | rolling deceleration from the entered Stimp [m/s^2]; grain `kappa * g_hat` in the putt frame |
| `base_hidden`, `flag_missing`, `poor_horizon`, `used_horizon`, `fit_converged` | flags |
| `aim_source` | 0 solved on the patch, 1 on its secant plane, 2 best iterate, 3 straight |
| `solve_status` | `SolveStatus` of the aim solve (0 OK, 1 PACE_LIMITED, 2 UNREACHABLE, 3 NO_BRACKET, 4 NO_CONVERGENCE, 5 INVALID) |

The reference start of the fit is `x0 = (a_tilt, b_tilt, 0, 0, 0, 0, 0)`:
the first placement's tilt rotated into the putt frame, all curvatures and
level offsets zero.

## Solver cases

`solve_aim` on the analytic surface `z = a x + b y + 0.5 (c x^2 + 2 d x y + e y^2)`
with the ball at the origin and the hole at `(distance, 0)`.

| Key | Content |
| --- | --- |
| `id`, `tag` | running number; what the case is (the first {n_anchor} are fixed anchors, including the closed-form dying putt `phi = (5/14) G s / a_r` and the 10 ft / 1 % / Stimp 10 / 0.43 m point) |
| `coeffs` | `(a, b, c, d, e)` |
| `distance` [m], `stimp_ft` [ft], `a_r` [m/s^2] | putt length and green speed (`a_r = 1.83^2 / (2 * stimp_ft * 0.3048)`) |
| `grain` | `kappa * g_hat`, two components in the surface frame |
| `past` | target pace: flat-green roll-out beyond the hole [m] |
| `status`, `status_name` | `SolveStatus` |
| `compare_values` | `true` when the status is OK: then `phi`, `v0`, `plays_like`, `aim_offset` must match. Otherwise only the status class (solved / not solved) is expected to match; the best iterate of a failed solve depends on the iteration path |
| `phi` [rad], `v0` [m/s], `v_hole` [m/s], `miss` [m] | solution, arrival speed at the hole line, residual lateral miss |
| `plays_like` [m], `aim_offset` [m] | `v0^2 / (2 a_r)` and `distance * tan(phi)` |

## How to compare

Relative tolerance 1e-4 on every floating-point output, with these absolute
floors for quantities that pass through zero:

| Quantity | Absolute floor |
| --- | --- |
| `phi`, `aim_azimuth_device`, `bearing`, `fall_line_azimuth` | 1e-6 rad (compare `fall_line_azimuth` only when `slope_pct` > 0.01; compare angles modulo 2 pi) |
| `patch[0..1]` (slopes) | 1e-7 |
| `patch[2..4]` (curvatures), `level_offsets` | 1e-8 |
| `break_m`, `aim_offset`, `dz_hole` | 1e-6 m |
| `break_cups` | 1e-5 |
| `confidence` | 1e-6 |

`v0`, `plays_like`, `distance` and `a_r` are never near zero and need no
floor. Flags, `aim_source` and `solve_status` must match exactly.

Why the vectors are generated with tighter tolerances than the defaults: at
the default solver tolerance (1e-5 m) the solution is only pinned to about
3e-5 m of lateral position at the hole, which for a small `phi` is of the
order of the 1e-4 comparison itself. With 1e-9 m both implementations
converge to the same solution of the discretised model (fixed RK4 step
`DT`), whatever their iteration path. The C port must use the same `DT`.

{n_multi} of the {n_fit} fitted cases have `start_independent = false`.
"""


def write_reference_vectors(out_dir: str, n_estimator: int = 240, n_solver: int = 120, seed: int = 20261111) -> dict:
    """Write ``reference_vectors.json`` and ``REFERENCE_VECTORS.md`` into ``out_dir``."""
    data = build_reference_vectors(n_estimator, n_solver, seed)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "reference_vectors.json"), "w") as fh:
        json.dump(data, fh, indent=1, allow_nan=False)
    fitted = [c for c in data["estimator_cases"] if c["method"] in ("B1", "B2") and not c["expected"]["flag_missing"]]
    n_anchor = sum(1 for c in data["solver_cases"] if c["tag"] not in ("plane", "quadratic, no grain", "quadratic with grain"))
    text = _SCHEMA_MD.format(
        version=SCHEMA_VERSION,
        seed=seed,
        n_est=len(data["estimator_cases"]),
        n_sol=len(data["solver_cases"]),
        n_anchor=n_anchor,
        n_multi=sum(1 for c in fitted if not c["start_independent"]),
        n_fit=len(fitted),
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
