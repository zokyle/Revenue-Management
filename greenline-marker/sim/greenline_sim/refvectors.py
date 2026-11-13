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

Appended for the firmware port (phase 2), without touching the cases above:
three further groups under their own keys - ``fallback_estimator_cases``
(reads built from plain numbers that exercise what the simulated reads never
do: every ``aim_source``, every ``SolveStatus``, a fit stopped by its
iteration limit, flag missing / not ranged, base hidden, the range channels,
Survey with 2, 3 and 4 drops, the horizon stage), ``fallback_solver_cases``
(aim problems for every ``SolveStatus``) and ``roll_cases`` (single rolls
with the capture model).  ``schema_version`` stays 2: a reader of schema 2
that ignores unknown keys is unaffected.

Appended after the firmware review (phase 2), again without touching anything
above: ``near_miss_estimator_cases`` - reads generated with
``EstimatorConfig.near_miss_keep = 0.005`` (the firmware's setting; the
default, and the setting of every other case, is 0 = off).  The key
``estimator_config`` of the file does not list ``near_miss_keep``, so that
the text of the file up to the appended group is unchanged; its value for a
case of the new group is in that case's ``config_overrides``.
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
from .refvectors_near_miss import NEAR_MISS_CASES

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


# --------------------------------------------------------------------------
# Fallback, status and roll cases (appended for the firmware port, phase 2)
# --------------------------------------------------------------------------
#
# These are NOT reads of a simulated green.  Every input is a plain number
# written here (or computed from plain numbers by the two formulas of
# _placement), chosen so that the estimator takes a path the simulated reads
# never take.  They do not depend on the seed.

_FB_CAM = se.GL1
_FB_STICK = 1.96  # [m] visible stick height the placements are built with
_STATUS_NAMES = {int(v): v.name for v in ph.SolveStatus}


def _fb_meas(**kw) -> dict:
    """A ``Measurements`` record as keyword arguments (NaN = not available)."""
    d = dict(
        f_px=_FB_CAM.f_px, baseline=_FB_CAM.baseline, h_cam=_FB_CAM.h_cam, tilt=(0.0, 0.0), tilt_reads=1,
        flag_found=True, flag_bearing=0.0, flag_disparity=math.nan, flag_low_elev=math.nan, flag_base_visible=True,
        flag_top_visible=False, flag_top_elev=math.nan, stick_height_est=_FB_STICK, stick_height_rel_sigma=0.07,
        horizon_az=(), horizon_elev=(), grain_kappa=0.0, grain_azimuth=0.0, stimp_ft=10.0, user_distance=math.nan,
    )
    unknown = set(kw) - set(d)
    if unknown:
        raise KeyError(f"not a Measurements field: {sorted(unknown)}")
    d.update(kw)
    return d


def _placement(rng_m: float, dz: Optional[float] = None, top: bool = False, **kw) -> dict:
    """A placement ``rng_m`` metres from the stick.

    ``flag_disparity = f b / rng_m`` (4 decimals) unless given; with ``dz``
    (height of the stick's base above the marker's base plane [m]) also
    ``flag_low_elev = atan((dz - h_lens) / rng_m)`` and, with ``top``, the
    elevation of the stick's top (9 decimals), where ``h_lens`` is the lens
    height the estimator assumes (``h_cam - sink_mean``).
    """
    h_lens = _FB_CAM.h_cam - es.EstimatorConfig().sink_mean
    kw.setdefault("flag_disparity", round(_FB_CAM.f_px * _FB_CAM.baseline / rng_m, 4))
    if dz is not None:
        kw.setdefault("flag_low_elev", round(math.atan((dz - h_lens) / rng_m), 9))
        if top:
            kw.setdefault("flag_top_visible", True)
            kw.setdefault("flag_top_elev", round(math.atan((dz + _FB_STICK - h_lens) / rng_m), 9))
    return _fb_meas(**kw)


def _survey(dist: float, a: float, b: float, c: float, d: float, fractions, **kw) -> List[dict]:
    """Noise-free drops of a Survey on the patch ``(a, b, c, d, e = 0)`` at the
    stations ``fractions * dist`` (the first one must be 0: the ball)."""
    drops = []
    for f in fractions:
        s = round(f * dist, 3)
        dz = a * (dist - s) + 0.5 * c * (dist * dist - s * s)
        drops.append(_placement(dist - s, dz=dz, tilt=(round(a + c * s, 4), round(b + d * s, 4)), **kw))
    return drops


def _horizon(coeffs, bearing: float, dist: float, n: int = 41, offset: float = 0.0, mound=None, invalid=()):
    """Turf-horizon samples of the putt-frame patch ``coeffs`` seen from the
    marker: ``n`` azimuths across +-0.45 rad, the model horizon plus a fixed
    0.4 mrad wobble, a common offset and optionally a mound ``(k0, k1,
    height)``; samples listed in ``invalid`` are NaN.  9 decimals."""
    az = np.linspace(-0.45, 0.45, n)
    cfg = es.EstimatorConfig()
    tan_e, _ = es.quad_horizon(coeffs, az - bearing, _FB_CAM.h_cam - cfg.sink_mean, cfg.horizon_d_min,
                               es.horizon_far_limit(dist, cfg))
    el = np.arctan(tan_e) + 0.0004 * np.sin(1.7 * np.arange(n)) + offset
    if mound is not None:
        el[mound[0] : mound[1]] += mound[2]
    return ([round(float(v), 9) for v in az],
            [math.nan if k in invalid else round(float(v), 9) for k, v in enumerate(el)])


def _fallback_estimator_inputs() -> List[tuple]:
    """``(mode, tag, method, config overrides, drops)`` of every fallback
    estimator case, in a fixed order."""
    cases: List[tuple] = []

    def add(mode, tag, method, drops, **overrides):
        cases.append((mode, tag, method, overrides, drops if isinstance(drops, list) else [drops]))

    nan = math.nan
    t = (0.012, -0.018)
    fb = _FB_CAM.f_px * _FB_CAM.baseline
    # ---- no flag / no range / the range channels ---------------------------------
    add("FLAG_MISSING", "flag not found, dialled distance 4.2 m: tilt-only plane along the visor axis", "B1",
        _fb_meas(flag_found=False, tilt=t, user_distance=4.2))
    add("FLAG_MISSING", "flag not found, nothing dialled: default distance 3 m", "B1", _fb_meas(flag_found=False, tilt=t))
    add("FLAG_MISSING", "flag_found false although the flag fields are filled in: they are ignored", "B1",
        _placement(5.0, dz=0.03, top=True, flag_found=False, tilt=t, flag_bearing=0.2, user_distance=7.5))
    add("FLAG_MISSING", "flag bearing not a number: counts as flag not found", "B1",
        _placement(5.0, dz=0.03, tilt=t, flag_bearing=nan))
    az, el = _horizon((0.012, -0.018, 0.0, 0.0, 0.0), 0.0, 3.0)
    add("FLAG_MISSING", "method B2 with a horizon but no flag: the horizon is not used", "B2",
        _fb_meas(flag_found=False, tilt=t, horizon_az=az, horizon_elev=el))
    add("FLAG_MISSING", "method B0, flag not found, Precision Read, dialled distance 2.5 m", "B0",
        _fb_meas(flag_found=False, tilt=t, tilt_reads=2, user_distance=2.5))
    add("RANGE_MISSING", "flag found, disparity not a number, top not visible: bearing kept, default distance", "B1",
        _placement(5.0, dz=0.03, tilt=t, flag_bearing=0.12, flag_disparity=nan))
    add("RANGE_MISSING", "flag found but not ranged, dialled distance 6.5 m along the measured bearing", "B1",
        _placement(5.0, dz=0.03, tilt=t, flag_bearing=-0.21, flag_disparity=nan, user_distance=6.5))
    add("RANGE_MISSING", "disparity 0.2 px (below the accepted 0.25), top visible but base hidden: no range channel", "B1",
        _placement(65.7, dz=0.3, top=True, tilt=t, flag_base_visible=False, flag_disparity=0.2))
    add("RANGE_MISSING", "method B2 with a horizon, flag not ranged: tilt-only plane, horizon not used", "B2",
        _placement(5.0, dz=0.03, tilt=t, flag_bearing=0.05, flag_disparity=nan, horizon_az=az, horizon_elev=el))
    add("RANGE", "range from the angular height only (no disparity; top and base visible), 9 m", "B1",
        _placement(9.0, dz=0.05, top=True, tilt=(0.004, 0.011), flag_disparity=nan))
    add("RANGE", "stereo and angular height fused, 9 m (the disparity reads 9.4 m)", "B1",
        _placement(9.0, dz=0.05, top=True, tilt=(0.004, 0.011), flag_disparity=round(fb / 9.4, 4)))
    add("RANGE", "top visible but base hidden: stereo only, hole height only bounded", "B1",
        _placement(9.0, dz=0.05, top=True, tilt=(0.004, 0.011), flag_base_visible=False))
    add("RANGE", "learned stick height with 2 % sigma dominates the fusion, 12 m", "B1",
        _placement(12.0, dz=-0.08, top=True, tilt=(-0.006, 0.009), stick_height_rel_sigma=0.02,
                   flag_disparity=round(fb / 11.2, 4)))
    add("RANGE", "dialled distance present but the cameras range the flag: the dialled value is not used", "B1",
        _placement(4.0, dz=0.02, tilt=t, user_distance=9.0))
    # ---- hole height ----------------------------------------------------------------
    add("BASE", "base hidden, bound active: the sight line lies below the tilt plane at the hole", "B1",
        _placement(5.0, dz=0.05, tilt=(0.02, 0.01), flag_base_visible=False))
    add("BASE", "base hidden, bound inactive: the sight line lies above the tilt plane at the hole", "B1",
        _placement(5.0, dz=0.20, tilt=(0.02, 0.01), flag_base_visible=False))
    add("BASE", "no elevation of the stick (not a number): tilt rows and priors only", "B1",
        _placement(5.0, tilt=(0.02, 0.01)))
    add("BASE", "hole height far off the tilt plane (0.25 m in 6 m): Huber outlier row", "B1",
        _placement(6.0, dz=0.25, tilt=(-0.01, 0.005)))
    # ---- methods, Precision Read, options -----------------------------------------------
    add("METHOD", "method B0 with flag and range: plane from the tilt only", "B0",
        _placement(4.0, dz=0.02, tilt=t, flag_bearing=0.08))
    add("METHOD", "method STRAIGHT with flag and range: straight at flat pace", "STRAIGHT",
        _placement(4.0, dz=0.02, tilt=t, flag_bearing=0.08))
    add("METHOD", "method STRAIGHT, flag not found, dialled distance 5.5 m", "STRAIGHT",
        _fb_meas(flag_found=False, tilt=t, user_distance=5.5))
    add("PRECISION", "Precision Read (two tilt reads), B1", "B1", _placement(4.0, dz=0.02, tilt=t, tilt_reads=2))
    add("PRECISION", "Precision Read, base hidden", "B1",
        _placement(7.0, dz=0.04, tilt=(0.015, 0.02), tilt_reads=2, flag_base_visible=False))
    add("OPTION", "flag bearing 3.1 rad: the aim azimuth wraps", "B1", _placement(4.0, dz=0.02, tilt=t, flag_bearing=3.1))
    add("OPTION", "grain used, strength 0.4 clipped to 0.25", "B1",
        _placement(4.0, dz=0.02, tilt=t, grain_kappa=0.4, grain_azimuth=1.1), use_grain=True)
    add("OPTION", "grain used, negative strength clipped to 0", "B1",
        _placement(4.0, dz=0.02, tilt=t, grain_kappa=-0.1, grain_azimuth=1.1), use_grain=True)
    add("OPTION", "grain used but its azimuth is not a number: solved without grain", "B1",
        _placement(4.0, dz=0.02, tilt=t, grain_kappa=0.1, grain_azimuth=nan), use_grain=True)
    add("OPTION", "grain used, flag bearing 0.3 rad: the grain is rotated into the putt frame", "B1",
        _placement(6.0, dz=-0.03, tilt=(0.0, 0.004), flag_bearing=0.3, grain_kappa=0.12, grain_azimuth=2.0), use_grain=True)
    add("OPTION", "green speed 3 ft entered: clipped to 5", "B1", _placement(4.0, dz=0.02, tilt=t, stimp_ft=3.0))
    add("OPTION", "green speed 20 ft entered: clipped to 16", "B1", _placement(4.0, dz=0.02, tilt=t, stimp_ft=20.0))
    add("OPTION", "pace: 0.6 m past the hole", "B1", _placement(4.0, dz=0.02, tilt=t), past=0.6)
    add("OPTION", "pace: the putt that dies at the hole (past 0) on a gentle cross slope", "B1",
        _placement(3.0, dz=0.0, tilt=(0.0, 0.01)), past=0.0)
    add("OPTION", "short putt, 0.4 m", "B1", _placement(0.4, dz=0.004, tilt=(0.01, 0.02)))
    add("OPTION", "long putt, 25 m (stereo only)", "B1", _placement(25.0, dz=0.3, tilt=(0.012, 0.006)))
    # ---- horizon (method B2) -------------------------------------------------------------
    patch = (0.010, -0.014, 0.0015, 0.0022, -0.0018)
    dz6 = patch[0] * 6.0 + 0.5 * patch[2] * 36.0
    az, el = _horizon(patch, 0.06, 6.0)
    add("HORIZON", "B2, 41 horizon samples of a twisted patch", "B2",
        _placement(6.0, dz=dz6, tilt=patch[:2], flag_bearing=0.06, horizon_az=az, horizon_elev=el))
    az4, el4 = _horizon(patch, 0.06, 6.0, invalid=set(range(41)) - {3, 14, 25, 36})
    add("HORIZON", "B2, only 4 valid horizon samples: horizon not used", "B2",
        _placement(6.0, dz=dz6, tilt=patch[:2], flag_bearing=0.06, horizon_az=az4, horizon_elev=el4))
    az5, el5 = _horizon(patch, 0.06, 6.0, invalid=set(range(41)) - {3, 14, 20, 25, 36})
    add("HORIZON", "B2, exactly 5 valid horizon samples", "B2",
        _placement(6.0, dz=dz6, tilt=patch[:2], flag_bearing=0.06, horizon_az=az5, horizon_elev=el5))
    azm, elm = _horizon(patch, 0.06, 6.0, mound=(4, 22, 0.012))
    add("HORIZON", "B2, mounds behind 18 of 41 samples: poor horizon", "B2",
        _placement(6.0, dz=dz6, tilt=patch[:2], flag_bearing=0.06, horizon_az=azm, horizon_elev=elm))
    add("HORIZON", "B2, base hidden", "B2",
        _placement(6.0, dz=dz6 - 0.03, tilt=patch[:2], flag_bearing=0.06, flag_base_visible=False, horizon_az=az,
                   horizon_elev=el))
    crest = (0.004, 0.006, -0.004, -0.002, -0.006)
    dzc = crest[0] * 8.0 + 0.5 * crest[2] * 64.0
    azc, elc = _horizon(crest, -0.1, 8.0, offset=0.003)
    add("HORIZON", "B2, crowned patch (the horizon is the crest on every ray), silhouette 3 mrad high", "B2",
        _placement(8.0, dz=dzc, tilt=crest[:2], flag_bearing=-0.1, horizon_az=azc, horizon_elev=elc))
    az9, el9 = _horizon(patch, 0.06, 6.0, n=9)
    add("HORIZON", "B2, 9 horizon samples, Precision Read", "B2",
        _placement(6.0, dz=dz6, tilt=patch[:2], tilt_reads=2, flag_bearing=0.06, horizon_az=az9, horizon_elev=el9))
    azn = list(az)
    azn[7] = nan
    add("HORIZON", "B2, one horizon azimuth is not a number: the horizon stage cannot run (its cost is not a "
        "number), the Quick-Read patch is kept and the fit is reported as not converged", "B2",
        _placement(6.0, dz=dz6, tilt=patch[:2], flag_bearing=0.06, horizon_az=azn, horizon_elev=el))
    # ---- fits stopped by their iteration limit ------------------------------------------------
    add("NOT_CONVERGED", "B1 stopped after 1 iteration", "B1", _placement(5.0, dz=0.03, tilt=(0.02, 0.01)), lm_max_iter=1)
    add("NOT_CONVERGED", "B1, base hidden with the bound active, stopped after 2 iterations", "B1",
        _placement(5.0, dz=0.05, tilt=(0.02, 0.01), flag_base_visible=False), lm_max_iter=2)
    add("NOT_CONVERGED", "B2 stopped after 2 iterations per start", "B2",
        _placement(6.0, dz=dz6, tilt=patch[:2], flag_bearing=0.06, horizon_az=azm, horizon_elev=elm), lm_max_iter=2)
    add("NOT_CONVERGED", "Survey of 3 drops stopped after 1 iteration", "B1",
        _survey(6.0, 0.012, -0.02, 0.002, 0.004, (0.0, 0.5, 0.8)), lm_max_iter=1)
    add("NOT_CONVERGED", "iteration limit 0: the tilt plane itself", "B1", _placement(5.0, dz=0.03, tilt=(0.02, 0.01)),
        lm_max_iter=0)
    # ---- Survey --------------------------------------------------------------------------------
    add("SURVEY2", "Survey, 2 drops", "B1", _survey(5.0, 0.010, 0.015, 0.002, -0.004, (0.0, 0.6)))
    add("SURVEY3", "Survey, 3 drops", "B1", _survey(8.0, -0.012, 0.020, 0.003, -0.005, (0.0, 0.5, 0.85)))
    add("SURVEY4", "Survey, 4 drops", "B1", _survey(11.0, 0.006, -0.012, -0.0015, 0.003, (0.0, 0.3, 0.6, 0.9)))
    add("SURVEY4", "Survey, 4 drops, Precision Read at every drop", "B1",
        _survey(11.0, 0.006, -0.012, -0.0015, 0.003, (0.0, 0.3, 0.6, 0.9), tilt_reads=2))
    d4 = _survey(9.0, 0.008, 0.010, 0.001, 0.002, (0.0, 0.3, 0.6, 0.9))
    d4[2] = dict(d4[2], flag_found=False)
    add("SURVEY4", "Survey, 4 drops, the third did not find the flag: 3 used", "B1", d4)
    d3 = _survey(9.0, 0.008, 0.010, 0.001, 0.002, (0.0, 0.5, 0.8))
    d3[1] = dict(d3[1], flag_disparity=nan)
    add("SURVEY3", "Survey, 3 drops, the second not ranged: 2 used", "B1", d3)
    d3 = _survey(6.0, 0.008, 0.010, 0.001, 0.002, (0.0, 0.5, 0.8))
    d3[1] = dict(d3[1], flag_disparity=round(fb / 7.5, 4))
    d3[2] = dict(d3[2], flag_disparity=round(fb / 0.2, 4))
    add("SURVEY3", "Survey, 3 drops: one ranged further than the ball (station clipped to 0), one 0.2 m from the hole",
        "B1", d3)
    d2 = _survey(7.0, 0.008, 0.010, 0.001, 0.002, (0.0, 0.6))
    d2[0] = dict(d2[0], flag_found=False, user_distance=7.0)
    add("SURVEY2", "Survey, the drop at the ball did not find the flag: tilt-only from that drop", "B1", d2)
    d3 = _survey(7.0, 0.015, -0.010, -0.002, 0.003, (0.0, 0.5, 0.8))
    d3[1] = dict(d3[1], flag_base_visible=False)
    d3[2] = dict(d3[2], flag_low_elev=nan)
    add("SURVEY3", "Survey, 3 drops: base hidden at the second, no stick elevation at the third", "B1", d3)
    d3 = _survey(6.0, patch[0], patch[1], patch[2], patch[3], (0.0, 0.5, 0.8), flag_bearing=0.06)
    d3[0] = dict(d3[0], horizon_az=az, horizon_elev=el)
    add("SURVEY3", "Survey, 3 drops, method B2 with the horizon of the drop at the ball", "B2", d3)
    add("SURVEY3", "Survey, 3 drops, method B0: only the drop at the ball is used", "B0",
        _survey(8.0, -0.012, 0.020, 0.003, -0.005, (0.0, 0.5, 0.85)))
    d3 = _survey(8.0, 0.01, 0.01, 0.0, 0.0, (0.0, 0.5, 0.85))
    d3[1] = dict(d3[1], flag_bearing=0.25, tilt=(0.03, -0.02))
    add("SURVEY3", "Survey, 3 drops, the second read far off the line with a different tilt (cross-talk sigmas, Huber)",
        "B1", d3)
    # ---- steep or pathological patches: every aim source and solve status -----------------------
    add("STEEP", "downhill 7 % at Stimp 13 (steeper than the green can hold): PACE_LIMITED on the patch", "B1",
        _placement(6.0, dz=-0.42, tilt=(-0.07, 0.0), stimp_ft=13.0))
    add("STEEP", "Survey of a patch that steepens downhill: PACE_LIMITED on the patch", "B1",
        _survey(6.0, -0.035, -0.032, -0.0202, 0.0234, (0.0, 0.5), stimp_ft=12.0))
    add("STEEP", "10 m downhill, crowned: NO_BRACKET at this tolerance, best iterate (a knife edge: with a pace "
        "tolerance of 1e-3 m the patch solve ends PACE_LIMITED instead)", "B1",
        _survey(10.0, -0.056, -0.003, -0.0104, 0.0, (0.0,), stimp_ft=8.0))
    add("STEEP", "cross slope 6 % at Stimp 13, just holdable: solved, aim 0.65 rad", "B1",
        _placement(6.0, dz=0.0, tilt=(0.0, 0.06), stimp_ft=13.0))
    add("STEEP", "twisted patch (Survey, 4 drops): not solvable, solved on its secant plane", "B1",
        _survey(6.0, 0.048, -0.018, -0.0117, -0.0136, (0.0, 0.5, 0.8, 0.3), stimp_ft=12.0))
    add("STEEP", "twisted patch (Survey, 3 drops): not solvable, solved on its secant plane", "B1",
        _survey(5.0, 0.004, -0.062, -0.0009, -0.0088, (0.0, 0.5, 0.8), stimp_ft=8.0))
    add("STEEP", "twisted patch (Survey, 4 drops), 8 m: solved on its secant plane", "B1",
        _survey(8.0, 0.011, -0.023, -0.0023, 0.0133, (0.0, 0.5, 0.8, 0.3), stimp_ft=12.0))
    add("STEEP", "steep uphill twisted patch: secant plane, PACE_LIMITED there", "B1",
        _survey(6.0, 0.126, -0.082, 0.0009, -0.0069, (0.0, 0.5, 0.8, 0.3), stimp_ft=12.0))
    add("STEEP", "uphill twisted patch, 8 m: secant plane, PACE_LIMITED there", "B1",
        _survey(8.0, 0.072, -0.033, 0.0056, -0.0103, (0.0, 0.5), stimp_ft=13.0))
    add("STEEP", "cross slope 7.5 % at Stimp 13: UNREACHABLE on patch and plane, best iterate", "B1",
        _placement(8.0, dz=0.0, tilt=(0.0, 0.075), stimp_ft=13.0))
    add("STEEP", "cross slope 9 % at Stimp 10, method B0: UNREACHABLE, best iterate", "B0",
        _placement(6.0, dz=0.0, tilt=(0.0, 0.09)))
    add("STEEP", "Survey, 4 drops, cross slope 6.4 % at Stimp 13: UNREACHABLE, best iterate", "B1",
        _survey(10.0, -0.009, -0.064, 0.0002, -0.0005, (0.0, 0.5, 0.8, 0.3), stimp_ft=13.0))
    add("STEEP", "unreachable hole: 18 m above the marker at 12 m (launch speed limit 15 m/s)", "B1",
        _placement(12.0, dz=18.0, tilt=(1.5, 0.0)))
    add("STEEP", "absurd tilt reading (50 % cross slope), 3 m: UNREACHABLE, best iterate", "B1",
        _placement(3.0, dz=0.0, tilt=(0.0, 0.5)))
    add("STEEP", "downhill 6.5 % with 3 % cross slope at Stimp 13: NO_BRACKET, best iterate", "B1",
        _placement(5.0, dz=-0.325, tilt=(-0.065, 0.03), stimp_ft=13.0))
    add("STEEP", "10 m downhill crowned patch with cross slope: NO_BRACKET, best iterate", "B1",
        _survey(10.0, -0.059, 0.037, -0.0132, 0.0, (0.0,), stimp_ft=13.0))
    add("STEEP", "3 m downhill crowned patch with cross slope: NO_BRACKET, best iterate", "B1",
        _survey(3.0, -0.053, 0.04, -0.0122, 0.0, (0.0,), stimp_ft=12.0))
    add("STEEP", "Survey, 2 drops, cross slope near the limit: NO_CONVERGENCE at this tolerance, best iterate (a "
        "knife edge: with tolerances of 2e-4 m / 1e-3 m the secant plane is solved, PACE_LIMITED)", "B1",
        _survey(4.0, 0.037, -0.069, -0.0032, -0.0046, (0.0, 0.5), stimp_ft=12.0))
    add("STEEP", "Survey, 4 drops, strong twist: NO_CONVERGENCE, best iterate", "B1",
        _survey(8.0, 0.006, -0.011, 0.0092, -0.0147, (0.0, 0.5, 0.8, 0.3), stimp_ft=13.0))
    add("STEEP", "3 m, 8.4 % cross slope uphill at Stimp 12: NO_CONVERGENCE, best iterate", "B1",
        _survey(3.0, 0.045, 0.084, 0.0077, 0.0, (0.0,), stimp_ft=12.0))
    add("ZERO_DISTANCE", "flag not found, dialled distance 5e-7 m: the solve is INVALID, straight at flat pace", "B1",
        _fb_meas(flag_found=False, tilt=t, user_distance=5e-7))
    add("ZERO_DISTANCE", "flag found but not ranged, dialled distance 1e-6 m (not above the solver's limit): INVALID, "
        "straight at flat pace", "B0",
        _placement(5.0, dz=0.03, tilt=t, flag_bearing=0.1, flag_disparity=nan, user_distance=1e-6))
    return cases


def _fallback_estimate_record(est: es.Estimate, fit: es.PatchFit) -> dict:
    """As :func:`_estimate_record`, with the fit record passed in (method
    ``STRAIGHT`` keeps none in the ``Estimate``; the ``B0`` fit it was
    computed from is used then)."""
    return _estimate_record(replace(est, fit=fit))


def _fallback_estimator_cases(config: es.EstimatorConfig) -> List[dict]:
    cases: List[dict] = []
    for mode, tag, method, overrides, drops_in in _fallback_estimator_inputs():
        drops = [se.Measurements(**dict(d, tilt=np.array(d["tilt"], dtype=float),
                                        horizon_az=np.array(d["horizon_az"], dtype=float),
                                        horizon_elev=np.array(d["horizon_elev"], dtype=float))) for d in drops_in]
        cfg = replace(config, **overrides)
        with np.errstate(all="ignore"):
            est = es.estimate_batch([drops], method, cfg)[0]
            fit = est.fit if est.fit is not None else es.fit_patch(drops, "B0", cfg)
        cases.append(
            {
                "id": len(cases),
                "mode": mode,
                "tag": tag,
                "method": method,
                "config_overrides": overrides,
                "measurements": [m.to_dict() for m in drops],
                "expected": _fallback_estimate_record(est, fit),
            }
        )
    return cases


_NEAR_MISS_KEEP = 0.005  # [m] the firmware's setting of EstimatorConfig.near_miss_keep


def _near_miss_estimator_cases(config: es.EstimatorConfig) -> List[dict]:
    """Reads whose patch solve ends without a usable solution, estimated with
    ``near_miss_keep`` on.  Layout of the fallback estimator cases, plus what
    the patch solve returned (``patch_solve``) and what the estimate is
    without the rule (``without_rule``)."""
    cases: List[dict] = []
    for entry in NEAR_MISS_CASES:
        drops = [se.Measurements.from_dict(d) for d in entry["drops"]]
        overrides = {"past": entry["past"], "near_miss_keep": _NEAR_MISS_KEEP}
        cfg_off = replace(config, past=entry["past"])
        cfg = replace(config, **overrides)
        with np.errstate(all="ignore"):
            est = es.estimate_batch([drops], "B1", cfg)[0]
            off = es.estimate_batch([drops], "B1", cfg_off)[0]
            sol = ph.solve_aim_quadratic_batch(
                np.array([off.fit.coeffs]), np.array([off.fit.distance]), np.array([off.a_r]), np.array([off.grain]),
                entry["past"], tol_miss=cfg.tol_miss, tol_pace=cfg.tol_pace,
            )
        kept = bool(est.aim_source == es.AIM_FROM_PATCH)
        cases.append(
            {
                "id": len(cases),
                "mode": "NEAR_MISS" if kept else "NEAR_MISS_CONTROL",
                "tag": entry["tag"],
                "method": "B1",
                "config_overrides": overrides,
                "measurements": [m.to_dict() for m in drops],
                "expected": _fallback_estimate_record(est, est.fit),
                "kept": kept,
                "patch_solve": {
                    "status": int(sol.status[0]),
                    "status_name": _STATUS_NAMES[int(sol.status[0])],
                    "miss": _num(sol.miss[0]),
                    "n_rolls": int(sol.n_rolls[0]),
                },
                "without_rule": {
                    "aim_source": int(off.aim_source),
                    "solve_status": int(off.solve_status),
                    "phi": _num(off.phi),
                    "v0": _num(off.v0),
                    "confidence": _num(off.confidence),
                },
            }
        )
    return cases


def _fallback_solver_cases() -> List[dict]:
    rows: List[dict] = []

    def add(tag, coeffs, dist, stimp=10.0, kappa=0.0, grain_az=0.0, past=0.30, max_rolls=ph.DEFAULT_MAX_ROLLS):
        a_r = ph.stimp_to_decel(stimp)
        grain = np.array([kappa * math.cos(grain_az), kappa * math.sin(grain_az)])
        sol = ph.solve_aim_quadratic_batch(
            np.asarray(coeffs, dtype=float), dist, a_r, grain, past, tol_miss=_SOLVER_TOL, tol_pace=_SOLVER_TOL,
            max_rolls=max_rolls,
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
                "max_rolls": int(max_rolls),
                "status": int(status),
                "status_name": status.name,
                "compare_values": bool(status == ph.SolveStatus.OK),
                "phi": _num(sol.phi[0]),
                "v0": _num(sol.v0[0]),
                "v_hole": _num(sol.v_hole[0]),
                "miss": _num(sol.miss[0]),
                "plays_like": _num(sol.plays_like[0]),
                "aim_offset": _num(sol.aim_offset[0]),
                "n_rolls": int(sol.n_rolls[0]),
            }
        )

    # solved, at the edges of the nominal range
    add("0.3 m putt on a 1 % / 2 % plane", (0.01, 0.02, 0, 0, 0), 0.3)
    add("25 m putt on a 1 % cross slope", (0.0, 0.01, 0, 0, 0), 25.0)
    add("Stimp 5 (slowest accepted)", (0.01, 0.015, 0, 0, 0), 4.0, stimp=5.0)
    add("Stimp 16 (fastest accepted)", (0.005, 0.01, 0, 0, 0), 4.0, stimp=16.0)
    add("saddle with strong curvature", (0.005, 0.01, 0.010, 0.005, -0.010), 4.0)
    add("bowl with strong curvature", (0.0, 0.0, 0.012, 0.0, 0.012), 5.0)
    add("pace 0.8 m past the hole", (0.01, 0.02, 0.001, 0.0, 0.0), 5.0, past=0.8)
    add("grain 0.25 across the line on a flat green", (0, 0, 0, 0, 0), 6.0, kappa=0.25, grain_az=math.pi / 2)
    add("grain 0.25 against the putt, uphill 2 %", (0.02, 0, 0, 0, 0), 6.0, kappa=0.25, grain_az=math.pi)
    add("grain 1.5 against the putt (stronger than the rolling resistance)", (0, 0, 0, 0, 0), 5.0, kappa=1.5,
        grain_az=math.pi)
    add("distance 2e-6 m (just above the solver's limit)", (0.01, 0.02, 0, 0, 0), 2e-6)
    add("flat green, 1 cm", (0, 0, 0, 0, 0), 0.01)
    # the putt that dies at the hole: the outcome class depends on the tolerance
    add("dying putt (past 0) uphill across a slope: PACE_LIMITED at 1e-9 m (solved at looser tolerances)",
        (0.015, 0.012, 0, 0, 0), 3.0, past=0.0)
    add("dying putt (past 0) on a twisted patch: NO_CONVERGENCE at 1e-9 m (solved at looser tolerances)",
        (0.0, 0.01, 0.0, 0.004, 0.0), 4.0, past=0.0)
    # PACE_LIMITED
    add("downhill, steepening beyond what the green holds near the hole: PACE_LIMITED", (-0.03, 0.0, -0.02, 0, 0), 5.0,
        stimp=12.0)
    add("downhill 7 % at Stimp 13, 2 m: PACE_LIMITED", (-0.07, 0.0, 0, 0, 0), 2.0, stimp=13.0)
    # UNREACHABLE
    add("cross slope 9 % at Stimp 10 (steeper than the green holds): UNREACHABLE", (0.0, 0.09, 0, 0, 0), 6.0)
    add("uphill 150 %: beyond the launch speed limit: UNREACHABLE", (1.5, 0.0, 0, 0, 0), 12.0)
    add("grain 1.5 across the line (stronger than the rolling resistance): UNREACHABLE", (0, 0, 0, 0, 0), 5.0,
        kappa=1.5, grain_az=math.pi / 2)
    add("twisted patch, 8 m: UNREACHABLE", (0.006, -0.011, 0.0092, -0.0147, 0.0), 8.0, stimp=13.0)
    add("twisted patch, 6 m (the estimator falls back to its secant plane): UNREACHABLE",
        (0.048, -0.018, -0.0117, -0.0136, 0.0), 6.0, stimp=12.0)
    # NO_BRACKET
    add("downhill 9 % with 0.5 % cross slope at Stimp 10: NO_BRACKET", (-0.09, 0.005, 0, 0, 0), 4.0)
    add("downhill 6.5 % with 3 % cross slope at Stimp 13: NO_BRACKET", (-0.065, 0.03, 0, 0, 0), 5.0, stimp=13.0)
    add("downhill 9 % with 4 % cross slope at Stimp 10: NO_BRACKET", (-0.09, 0.04, 0, 0, 0), 3.0)
    # NO_CONVERGENCE
    add("8.4 % cross slope uphill, 3 m, Stimp 12: NO_CONVERGENCE", (0.0566, 0.084, 0, 0, 0), 3.0, stimp=12.0)
    add("downhill 8 % with 8 % cross slope at Stimp 12: NO_CONVERGENCE at 1e-9 m (NO_BRACKET at looser tolerances)",
        (-0.08, 0.08, 0, 0, 0), 5.0, stimp=12.0)
    add("roll budget of 2 on a breaking putt: NO_CONVERGENCE", (0.0, 0.02, 0, 0, 0), 4.0, max_rolls=2)
    add("roll budget of 1: NO_CONVERGENCE", (0.01, 0.02, 0.002, 0.001, 0.0), 6.0, max_rolls=1)
    add("roll budget of 12: NO_CONVERGENCE at 1e-9 m (solved within the budget at looser tolerances)",
        (0.01, 0.02, 0.002, 0.001, 0.0), 6.0, max_rolls=12)
    # INVALID
    add("zero distance: INVALID", (0.01, 0.02, 0, 0, 0), 0.0)
    add("distance 1e-7 m: INVALID", (0.01, 0.02, 0, 0, 0), 1e-7)
    add("distance exactly 1e-6 m (not above the limit): INVALID", (0.01, 0.02, 0, 0, 0), 1e-6)
    return rows


def _roll_cases() -> List[dict]:
    rows: List[dict] = []

    def add(tag, coeffs, start, hole, phi, v0, stimp=10.0, kappa=0.0, grain_az=0.0, exponent=0.5,
            stop_on_capture=False, z0=0.0):
        a_r = ph.stimp_to_decel(stimp)
        grain = np.array([kappa * math.cos(grain_az), kappa * math.sin(grain_az)])
        surface = ph.QuadraticSurface(*coeffs, z0=z0)
        model = ph.CaptureModel(exponent=exponent)
        res = ph.simulate_putt(surface, start, hole, phi, v0, a_r, grain, capture=model,
                               stop_on_capture=stop_on_capture)
        # the number of RK4 steps is not part of PuttResult: the same roll once more through the kernel
        kind, par, grid = surface.kernel_spec()
        vel = ph.launch_velocity(start, hole, phi, v0)
        out = np.empty(ph._NOUT)
        ph._roll(
            kind, par, grid, float(start[0]), float(start[1]), float(vel[0]), float(vel[1]), a_r,
            float(grain[0] * a_r), float(grain[1] * a_r), float(hole[0]), float(hole[1]), ph.DEFAULT_DT,
            ph.DEFAULT_T_MAX, ph.DEFAULT_R_MAX, 0, 1 if stop_on_capture else 0, model.v_cap0, model.exponent,
            model.hole_r, 0, np.empty((1, 5)), out,
        )
        if out[ph._O_X] != res.stop_xy[0] or out[ph._O_T] != res.t_end or int(out[ph._O_STATUS]) != int(res.status):
            raise RuntimeError("roll_cases: the kernel call does not repeat simulate_putt")
        rows.append(
            {
                "id": len(rows),
                "tag": tag,
                "coeffs": [float(v) for v in coeffs],
                "z0": float(z0),
                "start": [float(start[0]), float(start[1])],
                "hole": [float(hole[0]), float(hole[1])],
                "phi": float(phi),
                "v0": float(v0),
                "stimp_ft": float(stimp),
                "a_r": float(a_r),
                "grain": [float(grain[0]), float(grain[1])],
                "capture_exponent": float(exponent),
                "stop_on_capture": bool(stop_on_capture),
                "status": int(res.status),
                "status_name": res.status.name,
                "t_end": _num(res.t_end),
                "stop_xy": [_num(res.stop_xy[0]), _num(res.stop_xy[1])],
                "delta": _num(res.delta),
                "speed_at_delta": _num(res.speed_at_delta),
                "side": int(res.side),
                "crossed_hole_line": bool(res.crossed_hole_line),
                "lateral_at_line": _num(res.lateral_at_line),
                "speed_at_line": _num(res.speed_at_line),
                "lateral_miss": _num(res.lateral_miss),
                "shortfall": _num(res.shortfall),
                "captured": bool(res.captured),
                "path_length": _num(res.path_length),
                "n_steps": int(out[ph._O_NSTEP]),
            }
        )

    a10 = ph.stimp_to_decel(10.0)
    flat = (0, 0, 0, 0, 0)
    v_3m = math.sqrt(2.0 * a10 * 3.3)  # 3 m putt hit to finish 0.3 m past on a flat green
    hole = (3.0, 0.0)
    add("flat, dead centre at pace: holed (free roll through the hole)", flat, (0, 0), hole, 0.0, v_3m)
    add("flat, dead centre at pace, integration stopped on capture", flat, (0, 0), hole, 0.0, v_3m, stop_on_capture=True)
    add("flat, dead centre, far too fast (4 m/s at the hole): not holed", flat, (0, 0), hole, 0.0,
        math.sqrt(16.0 + 2.0 * a10 * 3.0))
    add("flat, 30 mm off centre at pace: holed", flat, (0, 0), hole, 0.010, v_3m)
    add("flat, 50 mm off centre at pace: just holed with exponent 0.5", flat, (0, 0), hole, 0.0167, v_3m)
    add("flat, 52 mm off centre at pace: lips out", flat, (0, 0), hole, 0.01735, v_3m)
    add("flat, 52 mm off centre, 0.3 m/s at the hole: holed", flat, (0, 0), hole, 0.01735,
        math.sqrt(0.09 + 2.0 * a10 * 3.0))
    add("flat, 30 mm off centre, 1.3 m/s at the hole: holed with exponent 0.5", flat, (0, 0), hole, 0.010,
        math.sqrt(1.69 + 2.0 * a10 * 3.0))
    add("the same with Penner's exponent 1: not holed", flat, (0, 0), hole, 0.010,
        math.sqrt(1.69 + 2.0 * a10 * 3.0), exponent=1.0)
    add("flat, 60 mm off centre: misses on the left", flat, (0, 0), hole, 0.020, v_3m)
    add("flat, 60 mm off centre: misses on the right", flat, (0, 0), hole, -0.020, v_3m)
    add("flat, short by 0.5 m", flat, (0, 0), hole, 0.0, math.sqrt(2.0 * a10 * 2.5))
    add("flat, stops inside the hole radius (2.97 m): holed at rest", flat, (0, 0), hole, 0.0, math.sqrt(2.0 * a10 * 2.97))
    add("zero launch speed on a flat green: at rest at once", flat, (0, 0), hole, 0.0, 0.0)
    add("zero launch speed on a slope too steep to rest (10 % at Stimp 10): rolls from rest, holed in passing, "
        "still rolling at 30 s (MAX_TIME)", (-0.10, 0.0, 0, 0, 0), (0, 0), hole, 0.0, 0.0)
    add("downhill 10 % at Stimp 10: runs away, OUT_OF_BOUNDS", (-0.10, 0.0, 0, 0, 0), (0, 0), hole, 0.0, 1.5)
    add("downhill 7.7 % at Stimp 10 (0.98 of critical): creeps for 26 s before it rests (stiffness-limited steps)",
        (-0.0768, 0.0, 0, 0, 0), (0, 0), (30.0, 0.0), 0.0, 0.3)
    add("stopping with a slope at 0.9 of critical (stiff stop)", (-0.0706, 0.0, 0, 0, 0), (0, 0), (2.5, 0.0), 0.0, 0.5)
    add("cross slope 2 %, aimed straight: misses low", (0.0, 0.02, 0, 0, 0), (0, 0), hole, 0.0, v_3m)
    add("cross slope 2 %, aimed 0.105 rad left", (0.0, 0.02, 0, 0, 0), (0, 0), hole, 0.105, v_3m)
    add("uphill 3 %, dead centre: holed", (0.03, 0.0, 0, 0, 0), (0, 0), hole, 0.0, 2.2)
    add("uphill 9 % at Stimp 10 (not holdable): rolls back past the start", (0.09, 0.0, 0, 0, 0), (0, 0), hole, 0.0, 1.8)
    add("twisted patch with grain, 6 m", (0.01, 0.015, 0.002, -0.003, 0.004), (0, 0), (6.0, 0.0), 0.12, 3.0,
        kappa=0.08, grain_az=1.0)
    add("general position: start (-2, 1), hole (3, 2.5), surface with z0", (0.008, -0.011, 0.0012, 0.0018, -0.0015),
        (-2.0, 1.0), (3.0, 2.5), -0.05, 2.7, z0=0.3)
    gen = (0.008, -0.011, 0.0012, 0.0018, -0.0015)
    sol = ph.solve_aim(ph.QuadraticSurface(*gen, z0=0.3), (-2.0, 1.0), (3.0, 2.5), a10)
    add("general position, the solver's own solution, stopped on capture", gen, (-2.0, 1.0), (3.0, 2.5), sol.phi, sol.v0,
        z0=0.3, stop_on_capture=True)
    add("general position, the solver's own solution with Penner's exponent, free roll", gen, (-2.0, 1.0), (3.0, 2.5),
        sol.phi, sol.v0, z0=0.3, exponent=1.0)
    add("start equal to hole: at rest in the hole", flat, (1.0, 1.0), (1.0, 1.0), 0.3, 0.0)
    add("start equal to hole, launched away", flat, (1.0, 1.0), (1.0, 1.0), 0.3, 1.0)
    add("launched away from the hole (phi = 3 rad)", flat, (0, 0), hole, 3.0, 1.5)
    add("strong grain across the line (0.5), Stimp 8", flat, (0, 0), (4.0, 0.0), 0.0, 2.6, stimp=8.0, kappa=0.5,
        grain_az=math.pi / 2)
    add("fast green (Stimp 14), 12 m over a crown: runs away down the far side (OUT_OF_BOUNDS)",
        (0.01, 0.004, -0.003, 0.0, -0.001), (0, 0), (12.0, 0.0), 0.03, 3.6, stimp=14.0)
    add("fast green (Stimp 14), 12 m across a gentle slope", (0.004, 0.008, -0.0004, 0.0, 0.0003), (0, 0), (12.0, 0.0),
        0.12, 3.35, stimp=14.0)
    add("bowl: the ball swings back through the hole line", (0.0, 0.0, 0.04, 0.0, 0.04), (0, 0), (2.0, 0.0), 0.8, 2.5)
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
        # (near_miss_keep is a later addition with default 0 = off; it is left out here so
        # that the file is unchanged up to the appended near_miss_estimator_cases)
        "estimator_config": {k: v for k, v in asdict(config).items() if k != "near_miss_keep"},
        "solver_tolerances": {"tol_miss": _SOLVER_TOL, "tol_pace": _SOLVER_TOL},
        "estimator_cases": _estimator_cases(n_estimator, seed, config),
        "solver_cases": _solver_cases(n_solver, seed),
        # appended groups (see the module docstring); independent of n_estimator, n_solver and seed
        "fallback_estimator_cases": _fallback_estimator_cases(config),
        "fallback_solver_cases": _fallback_solver_cases(),
        "roll_cases": _roll_cases(),
        # appended after the firmware review (phase 2): EstimatorConfig.near_miss_keep = 0.005
        "near_miss_estimator_cases": _near_miss_estimator_cases(config),
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


_SCHEMA_MD_FALLBACK = """
## Fallback, status and roll cases (appended for the firmware port, phase 2)

The cases above are reads of simulated greens: every one of them ends with
`aim_source` 0 and `solve_status` 0 and a converged fit, and only two solver
cases end with another status. Three further groups, under their own
top-level keys, exercise the rest. They were appended without changing a
byte of the cases above; `schema_version` is still 2 and a reader that
ignores unknown keys is unaffected. Their inputs are plain numbers written
in `refvectors.py` (not simulated reads), so they do not depend on the seed.

| Key | Content |
| --- | --- |
| `fallback_estimator_cases` | {n_fb} estimator cases with the same layout as `estimator_cases` (`id` counts from 0 in this group; `mode` is the class of the case, `tag` says what it exercises; no `green_*`, `fit_check` or `start_independent` keys). Generated with the same `estimator_config` plus `config_overrides` (`use_grain`, `past`, `lm_max_iter`) |
| `fallback_solver_cases` | {n_fs} aim problems with the layout of `solver_cases` plus `max_rolls` (the roll budget used) and `n_rolls` (trial rolls the reference used) |
| `roll_cases` | {n_roll} single rolls (`simulate_putt`) with the capture model |

How the placements were built: `flag_disparity = f_px * baseline / range`
rounded to 4 decimals; with a stick base `dz` above the marker
`flag_low_elev = atan((dz - (h_cam - sink_mean)) / range)` and
`flag_top_elev` the same with `dz + {stick:g}` m, rounded to 9 decimals; a
Survey takes the tilt `(a + c s, b + d s)` and the hole height of a patch at
each station, without noise. Horizon samples are the model horizon of a
patch plus a fixed 0.4 mrad wobble.

What the `fallback_estimator_cases` cover (`aim_source`, `solve_status`,
fit converged -> number of cases):

{coverage}

For method `STRAIGHT` the reference keeps no fit record; the fit-derived
fields of `expected` (`level_offsets`, `range_*`, `stations`, `tilt_slopes`,
`used_horizon`, `fit_converged`, `fit_cost`, `fit_starts`) are those of the
`B0` fit the estimate was computed from, and `cross_slope_sigma` is `null`.

### How to compare these groups

* Flags, `aim_source`, `solve_status` and `fit_starts` exactly, and every
  floating-point output with the rule above, for an implementation that
  follows the reference's iteration path at these tolerances (the C port in
  double precision does: it reproduces `n_rolls` of every solver case).
* An implementation with other tolerances or another arithmetic cannot be
  held to all of them. Three kinds of case are tolerance-dependent by
  construction and say so in their `tag`: the putt that dies at the hole
  (`past` 0), a roll budget that is only exhausted at the 1e-9 m tolerance,
  and patches on a knife edge between two outcomes. Of a solve that failed
  (`aim_source` 2, or a solver `status` other than OK) only the outcome
  class is defined; its best iterate depends on the iteration path.
* A fit stopped by `lm_max_iter` (`fit_converged` false) returns the iterate
  it had reached; with the same Levenberg-Marquardt rules that iterate is
  reproducible, and it is what `expected` holds.
* `roll_cases`: one roll has no tolerance. `status` (0 STOPPED, 1 MAX_TIME,
  2 OUT_OF_BOUNDS, 3 CAPTURED), `captured`, `crossed_hole_line`, `side` and
  `n_steps` (RK4 steps) exactly; `stop_xy`, `t_end`, `delta`,
  `speed_at_delta`, `lateral_at_line`, `speed_at_line`, `lateral_miss`,
  `shortfall`, `path_length` to 1e-9. Inputs: `coeffs` and `z0` of the
  surface, `start`, `hole`, launch `phi` [rad] from the start-to-hole line
  and `v0` [m/s], `a_r`, `grain`, `capture_exponent` (0.5 or 1) and
  `stop_on_capture`.

### The fallback estimator cases

| id | mode | method | drops | aim_source | solve_status | converged | what it exercises |
| --- | --- | --- | --- | --- | --- | --- | --- |
{listing}

### The fallback solver cases

| id | status | max_rolls | n_rolls | what it is |
| --- | --- | --- | --- | --- |
{solver_listing}

### The roll cases

| id | status | holed | steps | what it is |
| --- | --- | --- | --- | --- |
{roll_listing}
"""


def _fallback_md(data: dict) -> str:
    fb = data["fallback_estimator_cases"]
    cover: dict = {}
    for c in fb:
        e = c["expected"]
        key = (e["aim_source"], e["solve_status"], e["fit_converged"])
        cover[key] = cover.get(key, 0) + 1
    coverage = "\n".join(
        f"* `aim_source` {k[0]}, `solve_status` {k[1]} ({_STATUS_NAMES[k[1]]}), "
        f"{'converged' if k[2] else 'NOT converged'}: {v}"
        for k, v in sorted(cover.items())
    )
    listing = "\n".join(
        f"| {c['id']} | {c['mode']} | {c['method']} | {len(c['measurements'])} | {c['expected']['aim_source']} | "
        f"{c['expected']['solve_status']} {_STATUS_NAMES[c['expected']['solve_status']]} | "
        f"{'yes' if c['expected']['fit_converged'] else 'no'} | {c['tag']} |"
        for c in fb
    )
    solver_listing = "\n".join(
        f"| {c['id']} | {c['status']} {c['status_name']} | {c['max_rolls']} | {c['n_rolls']} | {c['tag']} |"
        for c in data["fallback_solver_cases"]
    )
    roll_listing = "\n".join(
        f"| {c['id']} | {c['status']} {c['status_name']} | {'yes' if c['captured'] else 'no'} | {c['n_steps']} | {c['tag']} |"
        for c in data["roll_cases"]
    )
    return _SCHEMA_MD_FALLBACK.format(
        n_fb=len(fb), n_fs=len(data["fallback_solver_cases"]), n_roll=len(data["roll_cases"]), stick=_FB_STICK,
        coverage=coverage, listing=listing, solver_listing=solver_listing, roll_listing=roll_listing,
    )


_SCHEMA_MD_NEAR_MISS = """
## Near-miss cases (appended after the firmware review, phase 2)

`EstimatorConfig.near_miss_keep` (default 0 = off, the setting of every case
above) makes the estimator keep the best iterate of the aim solve on the
fitted patch when that solve ended without a usable solution but the iterate
reaches the hole line within `near_miss_keep` of the hole centre:
`aim_source` stays 0, `solve_status` reports how the solve ended, the
confidence takes `conf_aim_fallback`, and the secant plane is not tried.
The firmware runs with 5 mm. Why: near a jump of the lateral miss the
bracketing search stops a fraction of a millimetre to a few millimetres from
the centre and reports NO_CONVERGENCE; the secant-plane solution that
replaced such an iterate misses the hole on the fitted patch by decimetres
in most of those reads.

| Key | Content |
| --- | --- |
| `near_miss_estimator_cases` | {n_nm} estimator cases with the layout of `fallback_estimator_cases`, generated with `config_overrides` = `past` and `near_miss_keep` = {keep:g}. Extra keys: `kept` (the rule applied), `patch_solve` (`status`, `miss` [m] and `n_rolls` of the solve on the fitted patch) and `without_rule` (`aim_source`, `solve_status`, `phi`, `v0`, `confidence` of the same read with the rule off) |

The key `estimator_config` at the top of the file does not list
`near_miss_keep` (it is 0 for every case outside this group), so that the
file is unchanged, byte for byte, up to this appended group. The inputs are
plain numbers in `greenline_sim/refvectors_near_miss.py`. The last
{n_ctl} cases are controls: their best miss is outside {keep_mm:g} mm, and
the estimate is the one without the rule.

| id | drops | kept | best miss of the patch solve [mm] | trial rolls | aim_source, status | without the rule | aim moved by [mrad] | what it is |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
{listing}
"""


def _near_miss_md(data: dict) -> str:
    nm = data["near_miss_estimator_cases"]
    listing = "\n".join(
        f"| {c['id']} | {len(c['measurements'])} | {'yes' if c['kept'] else 'no'} | "
        f"{1e3 * c['patch_solve']['miss']:+.3f} | {c['patch_solve']['n_rolls']} | "
        f"{c['expected']['aim_source']}, {_STATUS_NAMES[c['expected']['solve_status']]} | "
        f"{c['without_rule']['aim_source']}, {_STATUS_NAMES[c['without_rule']['solve_status']]} | "
        f"{1e3 * (c['expected']['phi'] - c['without_rule']['phi']):+.1f} | {c['tag']} |"
        for c in nm
    )
    return _SCHEMA_MD_NEAR_MISS.format(
        n_nm=len(nm), keep=_NEAR_MISS_KEEP, keep_mm=1e3 * _NEAR_MISS_KEEP,
        n_ctl=sum(1 for c in nm if not c["kept"]), listing=listing,
    )


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
        fh.write(_fallback_md(data))
        fh.write(_near_miss_md(data))
    return data


def main(argv: Optional[List[str]] = None) -> int:
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
    data = write_reference_vectors(out_dir)
    print(f"wrote {len(data['estimator_cases'])} estimator and {len(data['solver_cases'])} solver cases to {out_dir}")
    print(f"      {len(data['fallback_estimator_cases'])} fallback estimator, {len(data['fallback_solver_cases'])} "
          f"fallback solver and {len(data['roll_cases'])} roll cases appended")
    print(f"      {len(data['near_miss_estimator_cases'])} near-miss estimator cases appended")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
