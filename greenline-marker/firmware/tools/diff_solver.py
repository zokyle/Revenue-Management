#!/usr/bin/env python3
"""Differential test: the C solver (core/gl_solver*.c) against the Python
reference (../sim/greenline_sim), beyond the exported vectors.

    make diff            builds build/diff/libglsolver64.so (the solver in
                         double precision, gl_solver64_* symbols) and
                         build/diff/libglsolver32.so (single precision) and
                         runs this script on both

The script loads a library with ctypes, describes the structures of
core/gl_solver.h a second time (checked against the compiler's sizes and
offsets through tools/diff_solver_abi.c) and compares, call by call:

    estimate / estimate_survey   against estimator.estimate_batch
    solve_aim                    against physics.solve_aim
    roll                         against physics.simulate_putt
    fuse_range, quad_horizon     against estimator.fuse_range, quad_horizon

on the reference vectors (--vectors) and on random inputs, including values
far outside the nominal ranges (--random N).  HOST ONLY; nothing here is
part of the firmware or of `make test`.

What counts as agreement
------------------------
* The reference returns a result and C returns GL_OK: every output is
  compared with the rule of REFERENCE_VECTORS.md ("How to compare": relative
  1e-4 with absolute floors; flags and codes exactly).  The script also
  reports the distribution of the differences, which for the double build
  is far inside that rule.
* The reference raises an exception, or returns an estimate with a
  not-a-number in it: C must return an error status (GL_ERR_PARAM or
  GL_ERR_RANGE) and the flagged record.
* C returns GL_ERR_PARAM for an input record that gl_solver.h documents as
  refused although the reference would work with it (non-positive focal
  length or baseline, non-finite lens height or tilt): counted separately
  as "refused by contract", and checked to happen only for those inputs.

Anything else is a DISAGREEMENT; the script prints each one and exits
non-zero.  Two kinds of difference are recognised, counted and printed as
explained rather than as disagreements: a result that differs only by the
convergence tolerance (it vanishes when both sides are run at 1e-9 m), and
a result that differs because the fitted patches differ in the last bits
(the C solve chain run on the reference's own patch must then reproduce the
reference exactly).

With --single the library is the firmware's single-precision build.  It
runs with its own default tolerances and so does the reference; the script
then reports how often flags and codes differ and the distribution of the
differences in the units that matter, and fails only on an undefined
result.  The bounds on the single-precision deviation are asserted by
tests/test_solver.c on the reference vectors, not here.
"""
from __future__ import annotations

import argparse
import ctypes
import dataclasses
import json
import math
import os
import sys
import time
import warnings

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SIM_DIR = os.path.normpath(os.path.join(HERE, "..", "..", "sim"))
DEFAULT_VECTORS = os.path.join(SIM_DIR, "results", "reference_vectors.json")

GL_OK, GL_ERR_PARAM, GL_ERR_RANGE = 0, 1, 8
METHODS = {"B1": 0, "B0": 1, "B2": 2, "STRAIGHT": 3}
MAX_HORIZON = 41
MAX_DROPS = 4
SOLVE_NOT_RUN = 255
NAN = math.nan


# --------------------------------------------------------------------------
# ctypes description of core/gl_solver.h
# --------------------------------------------------------------------------


def make_types(real):
    """The structures of gl_solver.h for the real type `real`."""

    class Meas(ctypes.Structure):
        _fields_ = [
            ("f_px", real), ("baseline_m", real), ("h_cam_m", real), ("tilt_x", real), ("tilt_y", real),
            ("tilt_reads", ctypes.c_uint8), ("flag_found", ctypes.c_bool),
            ("flag_bearing_rad", real), ("flag_disparity_px", real), ("flag_low_elev_rad", real),
            ("flag_base_visible", ctypes.c_bool), ("flag_top_visible", ctypes.c_bool),
            ("flag_top_elev_rad", real), ("stick_height_est_m", real), ("stick_height_rel_sigma", real),
            ("n_horizon", ctypes.c_uint8),
            ("horizon_az_rad", real * MAX_HORIZON), ("horizon_elev_rad", real * MAX_HORIZON),
            ("grain_kappa", real), ("grain_azimuth_rad", real), ("stimp_ft", real), ("user_distance_m", real),
        ]

    class Options(ctypes.Structure):
        _fields_ = [
            ("past_m", real), ("max_rolls", ctypes.c_uint16), ("method", ctypes.c_uint8),
            ("use_grain", ctypes.c_bool), ("tol_miss_m", real), ("tol_pace_m", real), ("lm_tol", real),
            ("lm_max_iter", ctypes.c_uint16), ("near_miss_m", real), ("max_steps", ctypes.c_uint32),
        ]

    class Surface(ctypes.Structure):
        _fields_ = [("a", real), ("b", real), ("c", real), ("d", real), ("e", real), ("z0", real)]

    class Vec2(ctypes.Structure):
        _fields_ = [("x", real), ("y", real)]

    class Aim(ctypes.Structure):
        _fields_ = [
            ("phi_rad", real), ("v0_mps", real), ("status", ctypes.c_uint8), ("distance_m", real),
            ("a_r_mps2", real), ("v_hole_target_mps", real), ("v_hole_mps", real), ("miss_m", real),
            ("n_rolls", ctypes.c_uint16), ("n_steps", ctypes.c_uint32),
        ]

    class Range(ctypes.Structure):
        _fields_ = [("distance_m", real), ("sigma_m", real), ("stereo_m", real), ("sigma_stereo_m", real),
                    ("mono_m", real), ("sigma_mono_m", real)]

    class Fit(ctypes.Structure):
        _fields_ = [
            ("coeffs", real * 5), ("cov", (real * 5) * 5), ("level_offsets", real * 2),
            ("distance_m", real), ("distance_sigma_m", real), ("bearing_rad", real), ("range", Range),
            ("tilt_slopes", real * 2), ("cross_sigma_read", real), ("n_drops", ctypes.c_uint8),
            ("stations_m", real * MAX_DROPS),
            ("base_hidden", ctypes.c_bool), ("flag_missing", ctypes.c_bool), ("range_missing", ctypes.c_bool),
            ("used_horizon", ctypes.c_bool), ("poor_horizon", ctypes.c_bool), ("horizon_rms", real),
            ("n_iter", ctypes.c_uint16), ("converged", ctypes.c_bool), ("cost", real),
            ("cost_first_start", real), ("n_starts", ctypes.c_uint8),
        ]

    class Estimate(ctypes.Structure):
        _fields_ = [
            ("phi_rad", real), ("aim_azimuth_device_rad", real), ("v0_mps", real), ("plays_like_m", real),
            ("break_m", real), ("break_cups", real), ("distance_m", real), ("distance_sigma_m", real),
            ("bearing_rad", real), ("slope_pct", real), ("fall_line_azimuth_rad", real),
            ("fall_line_azimuth_device_rad", real), ("dz_hole_m", real), ("patch", real * 5),
            ("cross_slope_sigma", real), ("confidence", real),
            ("base_hidden", ctypes.c_bool), ("flag_missing", ctypes.c_bool), ("range_missing", ctypes.c_bool),
            ("poor_horizon", ctypes.c_bool), ("fit_converged", ctypes.c_bool),
            ("aim_source", ctypes.c_uint8), ("solve_status", ctypes.c_uint8),
            ("a_r_mps2", real), ("stimp_ft", real), ("grain_x", real), ("grain_y", real),
            ("n_rolls", ctypes.c_uint16), ("n_steps", ctypes.c_uint32),
        ]

    n_lin = 3 * MAX_DROPS
    n_rows = n_lin + MAX_HORIZON

    class Work(ctypes.Structure):
        _fields_ = [
            ("fit", Fit), ("rows", (real * 7) * n_lin), ("targets", real * n_lin),
            ("one_sided", ctypes.c_uint8 * n_lin), ("hz", (real * 3) * MAX_HORIZON),
            ("r", (real * n_rows) * 2), ("jac", ((real * 7) * n_rows) * 2), ("second", (real * n_rows) * 2),
            ("outlier_prev", ctypes.c_uint8 * n_rows), ("mat", ((real * 7) * 7) * 6),
        ]

    class Roll(ctypes.Structure):
        _fields_ = [
            ("status", ctypes.c_uint8), ("t_end_s", real), ("stop_x", real), ("stop_y", real),
            ("delta_m", real), ("speed_at_delta_mps", real), ("side", ctypes.c_int8),
            ("crossed_hole_line", ctypes.c_bool), ("lateral_at_line_m", real), ("speed_at_line_mps", real),
            ("lateral_miss_m", real), ("shortfall_m", real), ("captured", ctypes.c_bool),
            ("path_length_m", real), ("n_steps", ctypes.c_uint32),
        ]

    class T:  # namespace
        pass

    T.real = real
    for cls in (Meas, Options, Surface, Vec2, Aim, Range, Fit, Estimate, Work, Roll):
        setattr(T, cls.__name__, cls)
    return T


class Solver:
    """One loaded solver library (double or single precision)."""

    def __init__(self, path: str, double: bool):
        self.double = double
        self.lib = ctypes.CDLL(path)
        self.real = ctypes.c_double if double else ctypes.c_float
        self.T = T = make_types(self.real)
        self.prefix = "gl_solver64_" if double else "gl_solver_"
        f = lambda name: getattr(self.lib, self.prefix + name)  # noqa: E731
        abi = f("diff_abi")
        abi.restype = ctypes.c_ulong
        abi.argtypes = [ctypes.c_uint]
        expect = [
            ctypes.sizeof(self.real), ctypes.sizeof(T.Meas), ctypes.sizeof(T.Options), ctypes.sizeof(T.Surface),
            ctypes.sizeof(T.Aim), ctypes.sizeof(T.Range), ctypes.sizeof(T.Fit), ctypes.sizeof(T.Estimate),
            ctypes.sizeof(T.Work), ctypes.sizeof(T.Roll), ctypes.sizeof(T.Vec2), T.Meas.user_distance_m.offset,
            T.Estimate.n_steps.offset, T.Fit.n_starts.offset, T.Work.mat.offset, T.Roll.n_steps.offset,
            T.Aim.n_steps.offset, T.Options.lm_max_iter.offset,
        ]
        got = [int(abi(i)) for i in range(len(expect))]
        if got != expect:
            raise RuntimeError(f"ctypes description does not match the compiled structures:\n C  {got}\n py {expect}")
        self.sizes = dict(real=got[0], measurements=got[1], estimate=got[7], work=got[8], fit=got[6])
        self._version = f("version")
        self._version.restype = ctypes.c_uint32
        self._defaults = f("default_options")
        self._defaults.argtypes = [ctypes.POINTER(T.Options)]
        self._defaults.restype = None
        self._estimate = f("estimate")
        self._estimate.argtypes = [ctypes.POINTER(T.Meas), ctypes.POINTER(T.Options), ctypes.POINTER(T.Work),
                                   ctypes.POINTER(T.Estimate)]
        self._estimate.restype = ctypes.c_int
        self._survey = f("estimate_survey")
        self._survey.argtypes = [ctypes.POINTER(T.Meas), ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(T.Options),
                                 ctypes.POINTER(T.Work), ctypes.POINTER(T.Estimate)]
        self._survey.restype = ctypes.c_int
        self._solve = f("solve_aim")
        self._solve.argtypes = [ctypes.POINTER(T.Surface), T.Vec2, T.Vec2, self.real, T.Vec2,
                                ctypes.POINTER(T.Options), ctypes.POINTER(T.Aim)]
        self._solve.restype = ctypes.c_int
        self._roll = f("roll")
        self._roll.argtypes = [ctypes.POINTER(T.Surface), T.Vec2, T.Vec2, self.real, self.real, self.real, T.Vec2,
                               self.real, ctypes.c_bool, ctypes.POINTER(T.Roll)]
        self._roll.restype = ctypes.c_int
        self._fuse = f("fuse_range")
        self._fuse.argtypes = [ctypes.POINTER(T.Meas), ctypes.POINTER(T.Range)]
        self._fuse.restype = None
        self._horizon = f("quad_horizon")
        self._horizon.argtypes = [ctypes.POINTER(self.real * 5), self.real, self.real, self.real, self.real,
                                  ctypes.POINTER(self.real), ctypes.POINTER(self.real)]
        self._horizon.restype = ctypes.c_int
        self.work = T.Work()

    # ---- conversions -----------------------------------------------------

    def version(self) -> int:
        return int(self._version())

    def meas(self, m, out=None):
        """greenline_sim Measurements (or its dict form) -> gl_measurements_t."""
        c = out if out is not None else self.T.Meas()
        if isinstance(m, dict):
            get = lambda k: m[k]  # noqa: E731
            tilt = m["tilt"]
            az, el = m["horizon_az"], m["horizon_elev"]
            num = lambda v: NAN if v is None else float(v)  # noqa: E731
        else:
            names = dict(baseline="baseline", h_cam="h_cam")
            get = lambda k: getattr(m, names.get(k, k))  # noqa: E731
            tilt = m.tilt
            az, el = m.horizon_az, m.horizon_elev
            num = float
        c.f_px = num(get("f_px"))
        c.baseline_m = num(get("baseline"))
        c.h_cam_m = num(get("h_cam"))
        c.tilt_x = num(tilt[0])
        c.tilt_y = num(tilt[1])
        c.tilt_reads = int(get("tilt_reads"))
        c.flag_found = bool(get("flag_found"))
        c.flag_bearing_rad = num(get("flag_bearing"))
        c.flag_disparity_px = num(get("flag_disparity"))
        c.flag_low_elev_rad = num(get("flag_low_elev"))
        c.flag_base_visible = bool(get("flag_base_visible"))
        c.flag_top_visible = bool(get("flag_top_visible"))
        c.flag_top_elev_rad = num(get("flag_top_elev"))
        c.stick_height_est_m = num(get("stick_height_est"))
        c.stick_height_rel_sigma = num(get("stick_height_rel_sigma"))
        n = len(az)
        if n > MAX_HORIZON:
            raise ValueError("more horizon samples than GL_SOLVER_MAX_HORIZON")
        c.n_horizon = n
        for i in range(MAX_HORIZON):
            c.horizon_az_rad[i] = num(az[i]) if i < n else NAN
            c.horizon_elev_rad[i] = num(el[i]) if i < n else NAN
        c.grain_kappa = num(get("grain_kappa"))
        c.grain_azimuth_rad = num(get("grain_azimuth"))
        c.stimp_ft = num(get("stimp_ft"))
        c.user_distance_m = num(get("user_distance"))
        return c

    def options(self, method="B1", **kw):
        o = self.T.Options()
        self._defaults(ctypes.byref(o))
        o.method = METHODS[method]
        for k, v in kw.items():
            if v is not None:
                setattr(o, k, v)
        return o

    # ---- calls -----------------------------------------------------------

    def estimate(self, drops, opt, ball_index=0, survey=None):
        """Run gl_solver_estimate (one drop) or gl_solver_estimate_survey.
        Returns (status, estimate dict, fit dict)."""
        est = self.T.Estimate()
        if survey is None:
            survey = len(drops) != 1
        if not survey:
            c = self.meas(drops[0])
            st = self._estimate(ctypes.byref(c), ctypes.byref(opt), ctypes.byref(self.work), ctypes.byref(est))
        else:
            arr = (self.T.Meas * len(drops))()
            for i, d in enumerate(drops):
                self.meas(d, arr[i])
            st = self._survey(arr, len(drops), ball_index, ctypes.byref(opt), ctypes.byref(self.work),
                              ctypes.byref(est))
        return int(st), _struct_dict(est), (_struct_dict(self.work.fit) if st == GL_OK else None)

    def solve_aim(self, coeffs, start, hole, a_r, grain, opt, z0=0.0):
        sf = self.T.Surface(*[float(v) for v in coeffs], float(z0))
        out = self.T.Aim()
        st = self._solve(ctypes.byref(sf), self.T.Vec2(*start), self.T.Vec2(*hole), a_r, self.T.Vec2(*grain),
                         ctypes.byref(opt), ctypes.byref(out))
        return int(st), _struct_dict(out)

    def roll(self, coeffs, start, hole, phi, v0, a_r, grain, cap_exp=0.5, stop_on_capture=False, z0=0.0):
        sf = self.T.Surface(*[float(v) for v in coeffs], float(z0))
        out = self.T.Roll()
        st = self._roll(ctypes.byref(sf), self.T.Vec2(*start), self.T.Vec2(*hole), phi, v0, a_r,
                        self.T.Vec2(*grain), cap_exp, stop_on_capture, ctypes.byref(out))
        return int(st), _struct_dict(out)

    def fuse_range(self, m):
        out = self.T.Range()
        c = self.meas(m)
        self._fuse(ctypes.byref(c), ctypes.byref(out))
        return _struct_dict(out)

    def quad_horizon(self, coeffs, theta, h_cam, d_min, far):
        arr = (self.real * 5)(*[float(v) for v in coeffs])
        e = self.real()
        r = self.real()
        st = self._horizon(ctypes.byref(arr), theta, h_cam, d_min, far, ctypes.byref(e), ctypes.byref(r))
        return int(st), float(e.value), float(r.value)


def _struct_dict(s):
    out = {}
    for name, _ in s._fields_:
        v = getattr(s, name)
        if isinstance(v, ctypes.Structure):
            v = _struct_dict(v)
        elif isinstance(v, ctypes.Array):
            v = np.array(v, dtype=float).tolist() if not isinstance(v[0], ctypes.Array) else [list(row) for row in v]
        out[name] = v
    return out


# --------------------------------------------------------------------------
# Comparison rules (REFERENCE_VECTORS.md, "How to compare")
# --------------------------------------------------------------------------

REL = 1e-4
# name -> (absolute floor, is an angle)
EST_FIELDS = {
    "phi": (1e-6, True), "aim_azimuth_device": (1e-6, True), "bearing": (1e-6, True),
    "fall_line_azimuth": (1e-6, True),
    "v0": (0.0, False), "plays_like": (0.0, False), "distance": (0.0, False), "a_r": (0.0, False),
    "break_m": (1e-6, False), "dz_hole": (1e-6, False), "break_cups": (1e-5, False),
    "confidence": (1e-6, False), "fit_cost": (1e-6, False),
    "slope_pct": (1e-5, False), "cross_slope_sigma": (1e-9, False), "distance_sigma": (1e-9, False),
    "range_stereo": (0.0, False), "range_mono": (0.0, False),
}
VEC_FIELDS = {"patch": (1e-7, 1e-7, 1e-8, 1e-8, 1e-8), "tilt_slopes": (1e-7, 1e-7), "level_offsets": (1e-8, 1e-8),
              "grain": (1e-9, 1e-9)}
FLAG_FIELDS = ("base_hidden", "flag_missing", "range_missing", "poor_horizon", "used_horizon", "fit_converged",
               "aim_source", "solve_status", "fit_starts")


def angle_diff(a, b):
    d = (a - b) % (2.0 * math.pi)
    return min(d, 2.0 * math.pi - d)


def excess(c, ref, floor, angle=False):
    """|c - ref| in units of the allowed difference (<= 1 passes).  Two
    not-a-numbers agree; one does not."""
    cn, rn = (c is None or not math.isfinite(c)), (ref is None or not math.isfinite(ref))
    if cn or rn:
        return 0.0 if (cn and rn) else math.inf
    d = angle_diff(c, ref) if angle else abs(c - ref)
    return d / max(REL * abs(ref), floor) if max(REL * abs(ref), floor) > 0.0 else (0.0 if d == 0.0 else math.inf)


def c_estimate_record(est, fit):
    """The outputs of one C estimate under the names REFERENCE_VECTORS.md uses."""
    return {
        "patch": est["patch"], "level_offsets": fit["level_offsets"], "distance": est["distance_m"],
        "distance_sigma": est["distance_sigma_m"], "range_stereo": fit["range"]["stereo_m"],
        "range_mono": fit["range"]["mono_m"], "bearing": est["bearing_rad"],
        "stations": fit["stations_m"][: fit["n_drops"]], "phi": est["phi_rad"],
        "aim_azimuth_device": est["aim_azimuth_device_rad"], "v0": est["v0_mps"], "plays_like": est["plays_like_m"],
        "break_m": est["break_m"], "break_cups": est["break_cups"], "slope_pct": est["slope_pct"],
        "fall_line_azimuth": est["fall_line_azimuth_rad"], "dz_hole": est["dz_hole_m"],
        "cross_slope_sigma": est["cross_slope_sigma"], "confidence": est["confidence"], "a_r": est["a_r_mps2"],
        "grain": [est["grain_x"], est["grain_y"]], "base_hidden": est["base_hidden"],
        "flag_missing": est["flag_missing"], "tilt_slopes": fit["tilt_slopes"],
        "range_missing": est["range_missing"], "poor_horizon": est["poor_horizon"],
        "used_horizon": fit["used_horizon"], "aim_source": est["aim_source"], "solve_status": est["solve_status"],
        "fit_converged": est["fit_converged"], "fit_cost": fit["cost"], "fit_starts": fit["n_starts"],
    }


def compare_estimate(c, ref, straight=False):
    """Compare a C record with a reference record (both in the vector
    naming).  Returns (worst excess, name of the worst field, dict of
    absolute differences per field)."""
    worst, name, diffs = 0.0, "", {}

    def note(n, ex, d):
        nonlocal worst, name
        diffs[n] = d
        if ex > worst:
            worst, name = ex, n

    for n in FLAG_FIELDS:
        if int(c[n]) != int(ref[n]):
            note(n, math.inf, abs(int(c[n]) - int(ref[n])))
    for n, (floor, ang) in EST_FIELDS.items():
        if n == "fall_line_azimuth" and not (ref["slope_pct"] is not None and ref["slope_pct"] > 0.01):
            continue
        if straight and n in ("cross_slope_sigma", "fit_cost"):
            continue
        cv, rv = c[n], ref[n]
        ex = excess(cv, rv, floor, ang)
        both = cv is not None and rv is not None and math.isfinite(cv) and math.isfinite(rv)
        note(n, ex, (angle_diff(cv, rv) if ang else abs(cv - rv)) if both else (0.0 if ex == 0.0 else math.inf))
    for n, floors in VEC_FIELDS.items():
        for i, floor in enumerate(floors):
            ex = excess(c[n][i], ref[n][i], floor)
            note(f"{n}[{i}]", ex, abs(c[n][i] - ref[n][i]) if ex != math.inf else math.inf)
    if len(c["stations"]) != len(ref["stations"]):
        note("n_stations", math.inf, math.inf)
    else:
        for i, (a, b) in enumerate(zip(c["stations"], ref["stations"])):
            note(f"stations[{i}]", excess(a, b, 1e-9), abs(a - b))
    return worst, name, diffs


# --------------------------------------------------------------------------
# The reference
# --------------------------------------------------------------------------


def load_reference():
    sys.path.insert(0, SIM_DIR)
    from greenline_sim import estimator as es  # noqa: E402
    from greenline_sim import physics as ph  # noqa: E402
    from greenline_sim import refvectors as rv  # noqa: E402
    from greenline_sim.measurements import Measurements  # noqa: E402

    return es, ph, rv, Measurements


def ref_estimate_record(es, est):
    """Reference Estimate -> record in the vector naming (as refvectors._estimate_record)."""
    fit = est.fit
    f = lambda v: float(v)  # noqa: E731
    if fit is None:  # STRAIGHT keeps no fit record: rebuild what the C side reports
        return None
    return {
        "patch": [f(v) for v in est.patch], "level_offsets": [f(v) for v in fit.level_offsets],
        # gl_solver.h: "unknown" is not-a-number; the reference can also return an infinite sigma
        "distance": f(est.distance),
        "distance_sigma": f(est.distance_sigma) if math.isfinite(est.distance_sigma) else NAN,
        "range_stereo": f(fit.range.stereo),
        "range_mono": f(fit.range.mono), "bearing": f(est.bearing), "stations": [f(v) for v in fit.stations],
        "phi": f(est.phi), "aim_azimuth_device": f(est.aim_azimuth_device), "v0": f(est.v0),
        "plays_like": f(est.plays_like), "break_m": f(est.break_m), "break_cups": f(est.break_cups),
        "slope_pct": f(est.slope_pct), "fall_line_azimuth": f(est.fall_line_azimuth), "dz_hole": f(est.dz_hole),
        "cross_slope_sigma": f(est.cross_slope_sigma), "confidence": f(est.confidence), "a_r": f(est.a_r),
        "grain": [f(v) for v in est.grain], "base_hidden": bool(est.base_hidden),
        "flag_missing": bool(est.flag_missing), "tilt_slopes": [f(v) for v in fit.tilt_slopes],
        "range_missing": bool(est.range_missing), "poor_horizon": bool(est.poor_horizon),
        "used_horizon": bool(fit.used_horizon), "aim_source": int(est.aim_source),
        "solve_status": int(est.solve_status), "fit_converged": bool(fit.converged), "fit_cost": f(fit.cost),
        "fit_starts": int(fit.n_starts),
    }


def record_is_finite(rec, straight=False):
    """True if a reference record holds no not-a-number where gl_solver.h
    promises a finite value."""
    names = ["phi", "aim_azimuth_device", "v0", "plays_like", "break_m", "break_cups", "distance", "bearing",
             "slope_pct", "fall_line_azimuth", "dz_hole", "confidence", "a_r"]
    if not straight:
        names.append("cross_slope_sigma")
    vals = [rec[n] for n in names] + list(rec["patch"]) + list(rec["grain"])
    return all(v is not None and math.isfinite(v) for v in vals)


# --------------------------------------------------------------------------
# Reference vectors
# --------------------------------------------------------------------------


def _none_to_nan(rec):
    out = {}
    for k, v in rec.items():
        if isinstance(v, list):
            out[k] = [NAN if x is None else x for x in v]
        else:
            out[k] = NAN if v is None else v
    return out


def run_vectors(solver, path, verbose=False):
    """Every case of reference_vectors.json through the library.  Returns
    the number of cases outside the comparison rule."""
    data = json.load(open(path))
    cfg = data["estimator_config"]
    tol = data["solver_tolerances"]
    bad = 0
    groups = [("estimator_cases", "solver_cases")]
    if "fallback_estimator_cases" in data:
        groups.append(("fallback_estimator_cases", "fallback_solver_cases"))
    if "near_miss_estimator_cases" in data:
        groups.append(("near_miss_estimator_cases", None))
    for est_key, sol_key in groups:
        worst_all, worst_name, n = 0.0, "", 0
        stats = {}
        for case in data[est_key]:
            over = dict(cfg)
            over.update(case["config_overrides"])
            near = float(over.get("near_miss_keep", 0.0))  # (not in estimator_config: 0 outside the near-miss group)
            if solver.double:
                opt = solver.options(case["method"], past_m=over["past"], use_grain=over["use_grain"],
                                     tol_miss_m=over["tol_miss"], tol_pace_m=over["tol_pace"],
                                     lm_tol=over["lm_tol"], lm_max_iter=over["lm_max_iter"], near_miss_m=near)
            else:  # the single build with its own tolerances: the strict rule does not apply (see test_solver.c)
                opt = solver.options(case["method"], past_m=over["past"], use_grain=over["use_grain"],
                                     lm_max_iter=case["config_overrides"].get("lm_max_iter"), near_miss_m=near)
            st, est, fit = solver.estimate(case["measurements"], opt)
            n += 1
            if st != GL_OK:
                bad += 1
                print(f"  {est_key}[{case['id']}] ({case['mode']}): C status {st}")
                continue
            w, name, diffs = compare_estimate(c_estimate_record(est, fit), _none_to_nan(case["expected"]))
            if not solver.double:
                # single precision: report the aim direction only (mrad); tests/test_solver.c has the rest
                if case["expected"]["aim_source"] <= 1 and est["aim_source"] == case["expected"]["aim_source"]:
                    stats["aim"] = max(stats.get("aim", 0.0), 1e3 * diffs.get("aim_azimuth_device", 0.0))
                continue
            for k, d in diffs.items():
                stats[k] = max(stats.get(k, 0.0), d)
            if w > worst_all:
                worst_all, worst_name = w, f"{name} of case {case['id']}"
            if w > 1.0:
                bad += 1
                print(f"  {est_key}[{case['id']}] ({case['mode']}): {name} is {w:.3g} x the allowed difference")
        if not solver.double:
            print(f"{est_key}: {n} cases in single precision with the firmware tolerances; largest difference of the "
                  f"aim direction {stats.get('aim', 0.0):.3f} mrad (bounds are asserted by tests/test_solver.c)")
            continue
        print(f"{est_key}: {n} cases, worst difference {worst_all:.3g} x allowed ({worst_name})")
        if verbose:
            for k in sorted(stats):
                print(f"    max |diff| {k:24s} {stats[k]:.3e}")
        worst_all, worst_name, n = 0.0, "", 0
        status_bad = 0
        for case in (data[sol_key] if (solver.double and sol_key is not None) else []):
            opt = solver.options("B1", past_m=case["past"], tol_miss_m=tol["tol_miss"], tol_pace_m=tol["tol_pace"],
                                 max_rolls=case.get("max_rolls"))
            st, sol = solver.solve_aim(case["coeffs"], (0.0, 0.0), (case["distance"], 0.0), case["a_r"],
                                       case["grain"], opt)
            n += 1
            if st != GL_OK:
                bad += 1
                print(f"  {sol_key}[{case['id']}]: C status {st}")
                continue
            if sol["status"] != case["status"]:
                status_bad += 1
                bad += 1
                print(f"  {sol_key}[{case['id']}] ({case['tag']}): status {sol['status']}, reference {case['status']}")
                continue
            if not case["compare_values"] and not solver.double:
                continue
            a_r, dist = case["a_r"], case["distance"]
            pairs = [("phi", sol["phi_rad"], case["phi"], 1e-6, True),
                     ("v0", sol["v0_mps"], case["v0"], 0.0, False),
                     ("plays_like", sol["v0_mps"] ** 2 / (2.0 * a_r), case["plays_like"], 0.0, False),
                     ("aim_offset", dist * math.tan(sol["phi_rad"]), case["aim_offset"], 1e-6, False)]
            for name, cv, rv, floor, ang in pairs:
                ex = excess(cv, rv, floor, ang)
                if ex > worst_all:
                    worst_all, worst_name = ex, f"{name} of case {case['id']}"
                if ex > 1.0:
                    bad += 1
                    print(f"  {sol_key}[{case['id']}] ({case['tag']}): {name} is {ex:.3g} x the allowed difference")
        if solver.double and sol_key is not None:
            print(f"{sol_key}: {n} cases, {status_bad} status mismatches, worst difference {worst_all:.3g} x allowed "
                  f"({worst_name})")
    return bad


# --------------------------------------------------------------------------
# Random inputs
# --------------------------------------------------------------------------

# values a field may be given to leave the nominal range
_EXTREME = {
    "f_px": (0.0, -657.0, NAN, math.inf, 1e9, 1e-3, 65.7),
    "baseline": (0.0, -0.02, NAN, math.inf, 1e-9, 2.0),
    "h_cam": (0.0, -0.01, NAN, math.inf, 1.0, 0.0005),
    "tilt_reads": (0, 2, 3, 255),
    "flag_bearing": (NAN, math.inf, -math.inf, 3.0, -3.1, 1.5707963267948966, 100.0),
    "flag_disparity": (NAN, math.inf, 0.0, -1.0, 0.2, 0.25, 0.2500001, 1e-12, 1e6, 1e12),
    "flag_low_elev": (NAN, math.inf, -math.inf, 1.5, -1.5, 0.3, -0.3, 1.5707963267948966, 0.0),
    "flag_top_elev": (NAN, math.inf, 1.5, -0.2, 0.0, 1.5707963267948966),
    # (1e300 / 1e20 / 1e-20 / 1e-200: numbers whose SQUARE leaves the range of a double or
    # of a float - the review found weights 1 / sigma^2 that became 0 or infinite)
    "stick_height_est": (NAN, math.inf, 0.0, -1.96, 1e-6, 100.0, 1e300, 1e20, 1e-20, 1e-200),
    "stick_height_rel_sigma": (NAN, math.inf, 0.0, -0.07, 10.0, 1e300, 1e20, 1e-20, 1e-200),
    "grain_kappa": (NAN, math.inf, -1.0, 0.0, 0.25, 0.3, 5.0),
    "grain_azimuth": (NAN, math.inf, 100.0, -7.0),
    "stimp_ft": (NAN, math.inf, -math.inf, 0.0, -10.0, 1.0, 4.999, 16.001, 1e6),
    "user_distance": (NAN, math.inf, -math.inf, 0.0, -3.0, 1e-7, 1e-6, 2e-6, 1e-3, 0.05, 60.0, 500.0, 1e30),
}
_TILT_EXTREME = (NAN, math.inf, -math.inf, 0.0, 0.3, -0.5, 2.0, 1e6, 1e30, 1e-30)


def _rot(vx, vy, ang):
    ca, sa = math.cos(ang), math.sin(ang)
    return vx * ca + vy * sa, -vx * sa + vy * ca


def random_estimator_case(rng, es, Measurements, hostile):
    """One random read: (drops ball first, ball_index and array order for the
    C call, method, option values).  `hostile`: probability that fields are
    pushed outside their nominal range."""
    f_px, base, h_cam = 657.0, 0.02, 0.0056
    span = rng.random()
    dist = rng.uniform(0.4, 4.0) if span < 0.45 else (rng.uniform(4.0, 13.0) if span < 0.9 else rng.uniform(13.0, 45.0))
    bearing = rng.normal(0.0, 0.15)
    steep = rng.random() < 0.2
    a, b = rng.normal(0.0, 0.05 if steep else 0.015, 2)
    c, d, e = rng.normal(0.0, 0.008 if steep else 0.002, 3)
    stimp = rng.uniform(5.5, 15.5)
    method = str(rng.choice(["B1", "B2", "B0", "STRAIGHT"], p=[0.5, 0.3, 0.12, 0.08]))
    n_drops = int(rng.choice([1, 2, 3, 4], p=[0.7, 0.1, 0.1, 0.1]))
    reads = int(rng.choice([1, 2], p=[0.75, 0.25]))
    stick = 1.96 * (1.0 + rng.normal(0.0, 0.03))
    drops = []
    for i in range(n_drops):
        s = 0.0 if i == 0 else rng.uniform(0.05, 1.05) * dist
        r = max(dist - s, 0.05)
        brg = bearing + (rng.normal(0.0, 0.03) if i else 0.0)
        tx, ty = _rot(a + c * s + rng.normal(0.0, 0.0025), b + d * s + rng.normal(0.0, 0.0025), -brg)
        dz = a * (dist - s) + 0.5 * c * (dist * dist - s * s)
        found = rng.random() < 0.93
        base_vis = rng.random() < 0.75
        low = math.atan((dz - h_cam + 0.00075) / r) + rng.normal(0.0, 0.0005) + (0.0 if base_vis else abs(rng.normal(0.0, 0.004)))
        top_vis = r > 6.5 and rng.random() < 0.6
        top = math.atan((dz + stick - h_cam) / r) + rng.normal(0.0, 0.0003)
        if i == 0 and method == "B2" and rng.random() < 0.9:
            n_h = MAX_HORIZON if rng.random() < 0.8 else int(rng.integers(1, MAX_HORIZON + 1))
            az = np.linspace(-0.45, 0.45, n_h) if n_h > 1 else np.array([0.0])
            far = min(max(1.5 * dist, 6.0), 20.0)
            tan_e, _ = es.quad_horizon([a, b, c, d, e], az - brg, h_cam, 0.15, far)
            el = np.arctan(tan_e) + rng.normal(0.0, 0.001, n_h) + rng.normal(0.0, 0.004)
            if rng.random() < 0.3:  # mounds behind part of the field
                k0 = int(rng.integers(0, n_h))
                el[k0 : k0 + int(rng.integers(1, 20))] += abs(rng.normal(0.0, 0.01))
            el[rng.random(n_h) < (0.6 if rng.random() < 0.1 else 0.08)] = NAN
        else:
            az, el = np.zeros(0), np.zeros(0)
        nanf = lambda v: v if found else NAN  # noqa: E731
        drops.append(Measurements(
            f_px=f_px, baseline=base, h_cam=h_cam, tilt=np.array([tx, ty]), tilt_reads=reads, flag_found=found,
            flag_bearing=nanf(brg), flag_disparity=nanf(f_px * base / r + rng.normal(0.0, 0.08)),
            flag_low_elev=nanf(low), flag_base_visible=bool(found and base_vis),
            flag_top_visible=bool(found and top_vis), flag_top_elev=nanf(top if top_vis else NAN),
            stick_height_est=stick, stick_height_rel_sigma=float(rng.choice([0.07, 0.02])),
            horizon_az=az, horizon_elev=el, grain_kappa=float(rng.uniform(0.0, 0.2)),
            grain_azimuth=float(rng.uniform(-math.pi, math.pi)), stimp_ft=stimp,
            user_distance=float(rng.uniform(1.0, 12.0)) if rng.random() < 0.4 else NAN,
        ))
    if rng.random() < hostile:
        for _ in range(int(rng.integers(1, 4))):
            k = int(rng.integers(0, n_drops))
            what = rng.random()
            if what < 0.25:
                t = drops[k].tilt.copy()
                t[int(rng.integers(0, 2))] = _TILT_EXTREME[int(rng.integers(0, len(_TILT_EXTREME)))]
                drops[k] = dataclasses.replace(drops[k], tilt=t)
            elif what < 0.33 and drops[k].horizon_az.size:
                az, el = drops[k].horizon_az.copy(), drops[k].horizon_elev.copy()
                j = int(rng.integers(0, az.size))
                if rng.random() < 0.5:
                    az[j] = (NAN, math.inf, 50.0)[int(rng.integers(0, 3))]
                else:
                    el[j] = (math.inf, -math.inf, 1.5, -1.5)[int(rng.integers(0, 4))]
                drops[k] = dataclasses.replace(drops[k], horizon_az=az, horizon_elev=el)
            elif what < 0.42:
                drops[k] = dataclasses.replace(drops[k], flag_found=not drops[k].flag_found,
                                               flag_base_visible=bool(rng.random() < 0.5),
                                               flag_top_visible=bool(rng.random() < 0.5))
            else:
                name = list(_EXTREME)[int(rng.integers(0, len(_EXTREME)))]
                vals = _EXTREME[name]
                drops[k] = dataclasses.replace(drops[k], **{name: vals[int(rng.integers(0, len(vals)))]})
    tight = rng.random() < 0.5
    opt = dict(
        past=float(rng.choice([0.30, 0.30, 0.15, 0.45, 0.0, 1.0])), use_grain=bool(rng.random() < 0.25),
        tol_miss=1e-9 if tight else 1e-5, tol_pace=1e-9 if tight else 1e-5, lm_tol=1e-10 if tight else 1e-9,
        lm_max_iter=int(rng.choice([200 if tight else 60, 1, 2, 5], p=[0.94, 0.02, 0.02, 0.02])),
        # EstimatorConfig.near_miss_keep / gl_solver_options_t.near_miss_m: off (the
        # reference's default), the firmware's 5 mm, or another value
        near_miss=float(rng.choice([0.0, 0.005, 0.02, 1e-4], p=[0.55, 0.35, 0.05, 0.05])),
    )
    ball_index = int(rng.integers(0, n_drops))
    order = list(range(1, n_drops))
    order.insert(ball_index, 0)  # array position -> index into `drops` (ball first)
    return drops, ball_index, order, method, opt


def c_refuses_by_contract(drops, opt):
    """Inputs for which gl_solver.h documents GL_ERR_PARAM whatever the
    reference does: a camera constant or a tilt that no placement produces."""
    for m in drops:
        if not (math.isfinite(m.f_px) and m.f_px > 0.0 and math.isfinite(m.baseline) and m.baseline > 0.0):
            return True
        if not (math.isfinite(m.h_cam) and math.isfinite(float(m.tilt[0])) and math.isfinite(float(m.tilt[1]))):
            return True
    return False


def float_exact(v):
    """True if the single-precision image of v is finite whenever v is, and
    not zero unless v is (the single build then sees the same case)."""
    if not math.isfinite(v):
        return True
    f = float(np.float32(v))
    return math.isfinite(f) and (f != 0.0 or v == 0.0)


def c_chain_on_patch(solver, patch, dist, a_r, grain, o):
    """The estimator's solve chain (patch, else its kept near miss, else
    secant plane, else best iterate) run with the C solver on a GIVEN patch:
    (aim_source, solve_status, phi, v0).  Used to show that a disagreement
    comes from the fitted patch alone."""
    opt = solver.options("B1", past_m=o["past"], tol_miss_m=o["tol_miss"], tol_pace_m=o["tol_pace"])
    _, sol = solver.solve_aim(list(patch), (0.0, 0.0), (dist, 0.0), a_r, list(grain), opt)
    if sol["status"] in (0, 1):
        return 0, sol["status"], sol["phi_rad"], sol["v0_mps"]
    near = o.get("near_miss", 0.0)
    if (near > 0.0 and sol["status"] != 5 and math.isfinite(sol["phi_rad"]) and math.isfinite(sol["v0_mps"])
            and sol["v0_mps"] > 0.0 and abs(sol["miss_m"]) <= near):
        return 0, sol["status"], sol["phi_rad"], sol["v0_mps"]
    plane = [patch[0] + 0.5 * patch[2] * dist, patch[1] + 0.5 * patch[3] * dist, 0.0, 0.0, 0.0]
    _, sol = solver.solve_aim(plane, (0.0, 0.0), (dist, 0.0), a_r, list(grain), opt)
    if sol["status"] in (0, 1):
        return 1, sol["status"], sol["phi_rad"], sol["v0_mps"]
    if math.isfinite(sol["phi_rad"]) and math.isfinite(sol["v0_mps"]) and sol["v0_mps"] > 0.0:
        return 2, sol["status"], sol["phi_rad"], sol["v0_mps"]
    return 3, sol["status"], 0.0, math.sqrt(2.0 * a_r * (dist + o["past"]))


QUANT = ("phi", "aim_azimuth_device", "v0", "plays_like", "break_m", "break_cups", "distance", "dz_hole",
         "confidence", "slope_pct", "cross_slope_sigma", "fit_cost", "patch[0]", "patch[1]", "patch[2]", "patch[3]",
         "patch[4]")


def _quantiles(v):
    v = np.asarray(v, dtype=float)
    if v.size == 0:
        return "(none)"
    return f"median {np.median(v):.2e}  99 % {np.percentile(v, 99):.2e}  99.9 % {np.percentile(v, 99.9):.2e}  max {v.max():.2e}"


def run_random_estimates(solver, n, seed, hostile, es, Measurements, max_print=40):
    """n random reads against estimator.estimate_batch.  Returns the number
    of disagreements (double build) or of undefined results (single)."""
    rng = np.random.default_rng([seed, 1])
    counts = dict(both_ok=0, both_reject=0, by_contract=0, tol_limited=0, patch_rounding=0, disagree=0, undefined=0,
                  unrepresentable=0)
    ref_errors = {}
    diffs = {k: [] for k in QUANT}
    worst = []
    cov_rel = []
    flag_mismatch = {}
    src_status = {}
    fit_flags = dict(nonconverged=0, base_hidden=0, flag_missing=0, range_missing=0, poor_horizon=0, used_horizon=0)
    by_method = {}
    by_drops = {}
    phys = dict(aim_mrad=[], v0_pct=[], lateral_mm=[], dist_mm=[], cups=[], conf=[])
    printed = 0
    t0 = time.time()
    own = solver.options()  # the library's default tolerances
    pair_mismatch = {}
    for it in range(n):
        drops, ball_index, order, method, o = random_estimator_case(rng, es, Measurements, hostile)
        if not solver.double:
            # single precision: both sides with the single build's own tolerances, so
            # that what differs is the arithmetic and nothing else
            o = dict(o, tol_miss=float(own.tol_miss_m), tol_pace=float(own.tol_pace_m), lm_tol=float(own.lm_tol),
                     lm_max_iter=o["lm_max_iter"] if o["lm_max_iter"] < 10 else int(own.lm_max_iter))
        cfg = dataclasses.replace(es.EstimatorConfig(), past=o["past"], use_grain=o["use_grain"],
                                  tol_miss=o["tol_miss"], tol_pace=o["tol_pace"], lm_tol=o["lm_tol"],
                                  lm_max_iter=o["lm_max_iter"], near_miss_keep=o["near_miss"])
        # ---- reference
        ref, err = None, None
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                with np.errstate(all="ignore"):
                    r_est = es.estimate_batch([drops], method, cfg)[0]
            fit_r = r_est.fit if r_est.fit is not None else es.fit_patch(drops, "B0", cfg)
            ref = ref_estimate_record(es, dataclasses.replace(r_est, fit=fit_r))
            if not record_is_finite(ref, method == "STRAIGHT"):
                err, ref = "not-a-number in the estimate", None
        except Exception as exc:  # the reference rejects the input
            err = type(exc).__name__
        # ---- C
        if solver.double:
            opt = solver.options(method, past_m=o["past"], use_grain=o["use_grain"], tol_miss_m=o["tol_miss"],
                                 tol_pace_m=o["tol_pace"], lm_tol=o["lm_tol"], lm_max_iter=o["lm_max_iter"],
                                 near_miss_m=o["near_miss"])
        else:  # the single build runs with its own default tolerances
            opt = solver.options(method, past_m=o["past"], use_grain=o["use_grain"],
                                 lm_max_iter=o["lm_max_iter"] if o["lm_max_iter"] < 10 else None,
                                 near_miss_m=o["near_miss"])
        arr = [drops[j] for j in order]
        st, est, fit = solver.estimate(arr, opt, ball_index=ball_index, survey=(len(arr) > 1 or rng.random() < 0.1))
        flagged = (est["solve_status"] == SOLVE_NOT_RUN and est["aim_source"] == 3 and est["confidence"] == 0.0
                   and est["phi_rad"] == 0.0 and est["v0_mps"] == 0.0)
        tag = f"read {it} ({method}, {len(drops)} drop(s), seed {seed})"
        if st != GL_OK:
            if st not in (GL_ERR_PARAM, GL_ERR_RANGE) or not flagged:
                counts["undefined"] += 1
                print(f"  {tag}: C status {st} with an output that is not the flagged record")
            if ref is None:
                counts["both_reject"] += 1
                ref_errors[err] = ref_errors.get(err, 0) + 1
            elif c_refuses_by_contract(drops, o):
                counts["by_contract"] += 1
            elif not solver.double:
                counts["unrepresentable"] += 1  # counted, examined below for the double build only
            else:
                counts["disagree"] += 1
                if printed < max_print:
                    printed += 1
                    print(f"  DISAGREEMENT {tag}: C status {st}, the reference returns an estimate "
                          f"(distance {ref['distance']:.6g}, phi {ref['phi']:.6g})")
                    for k_d, m_d in enumerate(drops):
                        d_d = m_d.to_dict()
                        d_d.pop("horizon_az", None)
                        d_d.pop("horizon_elev", None)
                        print(f"      placement {k_d}: {d_d}")
            continue
        crec = c_estimate_record(est, fit)
        ok_fin = record_is_finite(crec, method == "STRAIGHT")
        if not ok_fin:
            counts["undefined"] += 1
            print(f"  {tag}: C returned GL_OK with a not-a-number in the estimate")
        if ref is None:
            if solver.double:
                counts["disagree"] += 1
                if printed < max_print:
                    printed += 1
                    print(f"  DISAGREEMENT {tag}: the reference rejects the input ({err}), C returns an estimate")
            else:
                counts["unrepresentable"] += 1
            continue
        w, name, dd = compare_estimate(crec, ref, straight=(method == "STRAIGHT"))
        if not solver.double:
            # single precision: statistics in the units that matter; flags counted
            for fname in FLAG_FIELDS:
                if int(crec[fname]) != int(ref[fname]):
                    flag_mismatch[fname] = flag_mismatch.get(fname, 0) + 1
            same_branch = all(int(crec[f]) == int(ref[f]) for f in ("aim_source", "solve_status", "flag_missing",
                                                                   "range_missing", "used_horizon"))
            if (int(crec["aim_source"]), int(crec["solve_status"])) != (int(ref["aim_source"]), int(ref["solve_status"])):
                key = f"{ref['aim_source']}/{ref['solve_status']}->{crec['aim_source']}/{crec['solve_status']}"
                pair_mismatch[key] = pair_mismatch.get(key, 0) + 1
            representable = all(float_exact(float(getattr(m, f))) for m in drops for f in _EXTREME if f != "tilt_reads")
            if same_branch and representable and ref["aim_source"] <= 1:
                phys["aim_mrad"].append(1e3 * angle_diff(crec["aim_azimuth_device"], ref["aim_azimuth_device"]))
                phys["v0_pct"].append(100.0 * abs(crec["v0"] / ref["v0"] - 1.0))
                phys["lateral_mm"].append(1e3 * abs(crec["break_m"] - ref["break_m"]))
                phys["dist_mm"].append(1e3 * abs(crec["distance"] - ref["distance"]))
                phys["cups"].append(abs(crec["break_cups"] - ref["break_cups"]))
                phys["conf"].append(abs(crec["confidence"] - ref["confidence"]))
            counts["both_ok"] += 1
            continue
        if w > 1.0:
            # Outside the comparison rule.  Is it the convergence tolerance (both
            # sides stop anywhere inside it), i.e. does it vanish with the tight
            # tolerances the vectors are generated with?
            explained = False
            if o["tol_miss"] > 1e-9 and name not in FLAG_FIELDS:
                cfg_t = dataclasses.replace(cfg, tol_miss=1e-9, tol_pace=1e-9, lm_tol=1e-10,
                                            lm_max_iter=max(o["lm_max_iter"], 200) if o["lm_max_iter"] >= 10 else o["lm_max_iter"])
                opt_t = solver.options(method, past_m=o["past"], use_grain=o["use_grain"], tol_miss_m=1e-9,
                                       tol_pace_m=1e-9, lm_tol=1e-10, lm_max_iter=cfg_t.lm_max_iter,
                                       near_miss_m=o["near_miss"])
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        with np.errstate(all="ignore"):
                            r2 = es.estimate_batch([drops], method, cfg_t)[0]
                    fit2 = r2.fit if r2.fit is not None else es.fit_patch(drops, "B0", cfg_t)
                    st2, est2, fitc2 = solver.estimate(arr, opt_t, ball_index=ball_index, survey=len(arr) > 1)
                    if st2 == GL_OK:
                        w2, _, _ = compare_estimate(c_estimate_record(est2, fitc2),
                                                    ref_estimate_record(es, dataclasses.replace(r2, fit=fit2)),
                                                    straight=(method == "STRAIGHT"))
                        explained = w2 <= 1.0
                except Exception:
                    explained = False
            if not explained and ref["fit_starts"] > 0 and method != "STRAIGHT":
                # Two library functions of the reference differ from libm's in
                # the last bit for some arguments: numpy's vectorised cos / sin
                # / tan (the horizon rows) and CPython's math.hypot (the sigmas
                # of Survey drops).  The fitted patches then differ by
                # rounding.  Does the C solve chain, GIVEN the reference's
                # patch, reproduce the reference exactly?  Then the fitted
                # patch is the whole difference, amplified by an
                # ill-conditioned (failing or knife-edge) solve.
                patch_diff = max(abs(a - b) for a, b in zip(crec["patch"], ref["patch"]))
                src, sts, phi_c, v0_c = c_chain_on_patch(solver, ref["patch"], ref["distance"], ref["a_r"],
                                                         ref["grain"], o)
                if (patch_diff <= 1e-9 and src == ref["aim_source"] and sts == ref["solve_status"]
                        and abs(phi_c - ref["phi"]) <= 1e-12 and abs(v0_c - ref["v0"]) <= 1e-12 * ref["v0"]):
                    counts["patch_rounding"] += 1
                    why = "horizon rows: numpy cos/sin/tan" if ref["used_horizon"] else "Survey sigmas: math.hypot"
                    print(f"  explained, {tag}: {name} differs ({w:.3g} x allowed); the patches differ by "
                          f"{patch_diff:.1e} (last-bit library rounding, {why}) and the C solver on the "
                          f"reference's patch gives the reference's result exactly (aim_source {src}, "
                          f"solve_status {sts}, past {o['past']})")
                    continue
            if explained:
                counts["tol_limited"] += 1
            else:
                counts["disagree"] += 1
                if printed < max_print:
                    printed += 1
                    print(f"  DISAGREEMENT {tag}: {name} is {w:.3g} x the allowed difference "
                          f"(C {crec.get(name.split('[')[0])}, reference {ref.get(name.split('[')[0])}; "
                          f"aim_source {ref['aim_source']}, solve_status {ref['solve_status']}, "
                          f"tight {o['tol_miss'] < 1e-8})")
                continue
        counts["both_ok"] += 1
        worst.append(w)
        key = (int(ref["aim_source"]), int(ref["solve_status"]))
        src_status[key] = src_status.get(key, 0) + 1
        by_method[method] = by_method.get(method, 0) + 1
        by_drops[len(ref["stations"])] = by_drops.get(len(ref["stations"]), 0) + 1
        fit_flags["nonconverged"] += 0 if ref["fit_converged"] else 1
        for fname in ("base_hidden", "flag_missing", "range_missing", "poor_horizon", "used_horizon"):
            fit_flags[fname] += 1 if ref[fname] else 0
        for k in QUANT:
            if k in dd and math.isfinite(dd[k]):
                diffs[k].append(dd[k])
        # covariance of the fit (not in the vectors): relative to sqrt(cov_ii cov_jj)
        if method != "STRAIGHT":
            cr, cc = np.asarray(fit_r.cov, dtype=float), np.asarray(fit["cov"], dtype=float)
            if np.all(np.isfinite(cr)) and np.all(np.isfinite(cc)):
                sd = np.sqrt(np.abs(np.diag(cr)))
                cov_rel.append(float(np.max(np.abs(cc - cr) / np.outer(sd, sd))))
            elif np.any(np.isfinite(cr)) != np.any(np.isfinite(cc)):
                cov_rel.append(math.inf)
    dt = time.time() - t0
    prec = "double" if solver.double else "single"
    print(f"random estimates ({prec}): {n} reads in {dt:.0f} s, hostile fraction {hostile}")
    print(f"  both return an estimate {counts['both_ok']}, both reject {counts['both_reject']} "
          f"(reference: {ref_errors}), refused by contract {counts['by_contract']}, "
          f"tolerance-limited {counts['tol_limited']}, explained by last-bit rounding of the patch "
          f"{counts['patch_rounding']}, DISAGREEMENTS {counts['disagree']}, "
          f"undefined results {counts['undefined']}"
          + ("" if solver.double else f", one side rejects (single precision range) {counts['unrepresentable']}"))
    if solver.double:
        print(f"  reference (aim_source, solve_status) counts: {dict(sorted(src_status.items()))}")
        print(f"  methods {by_method}, placements used {dict(sorted(by_drops.items()))}, flags {fit_flags}")
        print(f"  worst difference in units of the allowed one: {_quantiles(worst)}")
        for k in QUANT:
            print(f"    |C - reference| {k:20s} {_quantiles(diffs[k])}")
        print(f"    covariance, relative to sigma_i sigma_j: {_quantiles([v for v in cov_rel if math.isfinite(v)])}"
              f" ({sum(1 for v in cov_rel if not math.isfinite(v))} with not-a-number on one side only)")
        return counts["disagree"] + counts["undefined"]
    print(f"  the reference was run with the single build's tolerances (tol_miss {float(own.tol_miss_m):.0e} m, "
          f"tol_pace {float(own.tol_pace_m):.0e} m, lm_tol {float(own.lm_tol):.0e})")
    print(f"  flags and codes that differ from the reference: {flag_mismatch}")
    print(f"  (aim_source/solve_status reference -> single) where they differ: {dict(sorted(pair_mismatch.items()))}")
    print(f"  deviation of the {len(phys['aim_mrad'])} reads with the same outcome, a solved aim and inputs "
          f"representable in single precision:")
    for k, label in (("aim_mrad", "aim direction [mrad]"), ("v0_pct", "launch speed [%]"),
                     ("lateral_mm", "aim point at the hole [mm]"), ("dist_mm", "distance [mm]"),
                     ("cups", "break [cup widths]"), ("conf", "confidence")):
        print(f"    {label:28s} {_quantiles(phys[k])}")
    return counts["undefined"]


def random_solver_case(rng, hostile):
    """One random aim problem on a quadratic surface."""
    kind = rng.random()
    slope = rng.uniform(0.0, 0.035)
    curv = rng.normal(0.0, 0.002, 3) if kind > 0.3 else np.zeros(3)
    dist = float(rng.uniform(0.3, 13.0))
    stimp = float(rng.uniform(5.0, 16.0))
    kappa = float(rng.uniform(0.0, 0.15)) if rng.random() < 0.5 else 0.0
    past = float(rng.choice([0.30, 0.30, 0.15, 0.45, 0.0, 0.8]))
    if rng.random() < hostile:
        what = rng.random()
        if what < 0.35:
            slope = rng.uniform(0.035, 0.15)  # up to and beyond what the green can hold
        elif what < 0.6:
            curv = rng.normal(0.0, 0.02, 3)
        elif what < 0.7:
            dist = float(rng.choice([0.0, 1e-7, 1e-6, 1.0000001e-6, 1e-3, 0.02, 30.0, 60.0, 150.0]))
        elif what < 0.8:
            kappa = float(rng.choice([0.5, 0.99, 1.5]))
        elif what < 0.9:
            stimp = float(rng.choice([0.5, 2.0, 30.0, 300.0]))
        else:
            past = float(rng.choice([3.0, 30.0]))
    az = rng.uniform(0.0, 2.0 * math.pi)
    coeffs = [slope * math.cos(az), slope * math.sin(az), float(curv[0]), float(curv[1]), float(curv[2])]
    gaz = rng.uniform(0.0, 2.0 * math.pi)
    grain = (kappa * math.cos(gaz), kappa * math.sin(gaz))
    if rng.random() < 0.5:
        start, hole, z0 = (0.0, 0.0), (dist, 0.0), 0.0
    else:
        start = (float(rng.uniform(-2.0, 2.0)), float(rng.uniform(-2.0, 2.0)))
        ang = rng.uniform(0.0, 2.0 * math.pi)
        hole = (start[0] + dist * math.cos(ang), start[1] + dist * math.sin(ang))
        z0 = float(rng.uniform(-1.0, 1.0))
    tight = rng.random() < 0.5
    return dict(coeffs=coeffs, z0=z0, start=start, hole=hole, a_r=1.83 ** 2 / (2.0 * stimp * 0.3048),
                grain=grain, past=past, tol=1e-9 if tight else 1e-5,
                max_rolls=int(rng.choice([200, 200, 200, 1000, 40, 8])))


def run_random_solves(solver, n, seed, hostile, ph):
    """n random aim problems against physics.solve_aim.  Returns the number
    of disagreements (double) or undefined results (single)."""
    rng = np.random.default_rng([seed, 2])
    status_counts = {}
    mismatch = 0
    undefined = 0
    same_rolls = 0
    identical = 0
    tol_limited = 0
    n_ok = 0
    d_phi, d_v0, d_miss, d_vh = [], [], [], []
    f_phi, f_v0, f_lat = [], [], []
    status_pairs = {}
    printed = 0
    t0 = time.time()
    own = solver.options()
    for it in range(n):
        p = random_solver_case(rng, hostile)
        surf = ph.QuadraticSurface(*p["coeffs"], z0=p["z0"])
        ref, err = None, None
        # single precision: the reference runs with the single build's tolerances
        tol_miss = p["tol"] if solver.double else float(own.tol_miss_m)
        tol_pace = p["tol"] if solver.double else float(own.tol_pace_m)
        try:
            ref = ph.solve_aim(surf, p["start"], p["hole"], p["a_r"], np.array(p["grain"]), p["past"],
                               tol_miss=tol_miss, tol_pace=tol_pace, max_rolls=p["max_rolls"])
        except Exception as exc:
            err = type(exc).__name__
        if solver.double:
            opt = solver.options("B1", past_m=p["past"], tol_miss_m=p["tol"], tol_pace_m=p["tol"],
                                 max_rolls=p["max_rolls"])
        else:
            opt = solver.options("B1", past_m=p["past"], max_rolls=p["max_rolls"])
        st, sol = solver.solve_aim(p["coeffs"], p["start"], p["hole"], p["a_r"], p["grain"], opt, z0=p["z0"])
        tag = f"problem {it} (seed {seed})"
        if st not in (GL_OK, GL_ERR_PARAM, GL_ERR_RANGE) or sol["status"] > 5:
            undefined += 1
            print(f"  {tag}: undefined result (status {st}, solve status {sol['status']})")
            continue
        if ref is not None and int(ref.status) != 5 and not (math.isfinite(ref.phi) and math.isfinite(ref.v0)):
            # the reference returns an iterate that is not a number (absurd inputs): C must refuse
            if st != GL_ERR_RANGE and solver.double:
                mismatch += 1
                print(f"  DISAGREEMENT {tag}: the reference returns not-a-number, C status {st}")
            continue
        if ref is None:
            if st != GL_ERR_PARAM and solver.double:
                mismatch += 1
                print(f"  DISAGREEMENT {tag}: the reference rejects the input ({err}), C returns status {st}")
            continue
        rs = int(ref.status)
        if st != GL_OK:
            mismatch += 1
            print(f"  DISAGREEMENT {tag}: C status {st}, the reference solves (status {rs})")
            continue
        status_counts[rs] = status_counts.get(rs, 0) + 1
        status_pairs[(rs, sol["status"])] = status_pairs.get((rs, sol["status"]), 0) + 1
        if not solver.double:
            if sol["status"] == rs and rs in (0, 1):
                d = math.hypot(p["hole"][0] - p["start"][0], p["hole"][1] - p["start"][1])
                f_phi.append(1e3 * abs(sol["phi_rad"] - ref.phi))
                f_v0.append(100.0 * abs(sol["v0_mps"] / ref.v0 - 1.0))
                f_lat.append(1e3 * abs(d * math.tan(sol["phi_rad"]) - d * math.tan(ref.phi)))
            continue
        if sol["status"] != rs:
            mismatch += 1
            if printed < 40:
                printed += 1
                print(f"  DISAGREEMENT {tag}: status {sol['status']}, reference {rs}")
            continue
        if rs == 5:
            continue
        same_rolls += 1 if sol["n_rolls"] == min(ref.n_rolls, 65535) else 0
        identical += 1 if (sol["phi_rad"] == ref.phi and sol["v0_mps"] == ref.v0) else 0
        if rs in (0, 1):
            n_ok += 1
            ex = max(excess(sol["phi_rad"], ref.phi, 1e-6, True), excess(sol["v0_mps"], ref.v0, 0.0))
            if ex > 1.0:
                if p["tol"] > 1e-9 and sol["n_rolls"] != ref.n_rolls:
                    tol_limited += 1
                else:
                    mismatch += 1
                    if printed < 40:
                        printed += 1
                        print(f"  DISAGREEMENT {tag}: phi {sol['phi_rad']!r} / {ref.phi!r}, v0 {sol['v0_mps']!r} / "
                              f"{ref.v0!r} ({ex:.3g} x allowed)")
                    continue
            d_phi.append(abs(sol["phi_rad"] - ref.phi))
            d_v0.append(abs(sol["v0_mps"] / ref.v0 - 1.0))
            if math.isfinite(ref.miss):
                d_miss.append(abs(sol["miss_m"] - ref.miss))
                d_vh.append(abs(sol["v_hole_mps"] - ref.v_hole))
    dt = time.time() - t0
    names = {0: "OK", 1: "PACE_LIMITED", 2: "UNREACHABLE", 3: "NO_BRACKET", 4: "NO_CONVERGENCE", 5: "INVALID"}
    prec = "double" if solver.double else "single"
    print(f"random aim solves ({prec}): {n} problems in {dt:.0f} s, hostile fraction {hostile}")
    print(f"  reference status counts: { {names[k]: v for k, v in sorted(status_counts.items())} }")
    if solver.double:
        total = sum(v for k, v in status_counts.items() if k != 5)
        print(f"  status mismatches or values outside the rule: {mismatch}; tolerance-limited: {tol_limited}; "
              f"undefined: {undefined}")
        print(f"  same number of trial rolls: {same_rolls} of {total}; phi and v0 bit-identical: {identical} of {total}")
        print(f"    |phi - reference| [rad]        {_quantiles(d_phi)}")
        print(f"    |v0 / reference - 1|           {_quantiles(d_v0)}")
        print(f"    |miss - reference| [m]         {_quantiles(d_miss)}")
        print(f"    |v_hole - reference| [m/s]     {_quantiles(d_vh)}")
        return mismatch + undefined
    agree = sum(v for (a, b), v in status_pairs.items() if a == b)
    print(f"  the reference was run with the single build's tolerances")
    print(f"  status equal to the reference's: {agree} of {sum(status_pairs.values())}; "
          f"(reference, single) pairs that differ: "
          f"{ {f'{names[a]}->{names[b]}': v for (a, b), v in sorted(status_pairs.items()) if a != b} }")
    print(f"  deviation of the {len(f_phi)} solved problems with the same status:")
    print(f"    aim direction [mrad]          {_quantiles(f_phi)}")
    print(f"    launch speed [%]              {_quantiles(f_v0)}")
    print(f"    aim point at the hole [mm]    {_quantiles(f_lat)}")
    return undefined


def run_random_rolls(solver, n, seed, ph):
    """n random rolls against physics.simulate_putt (double build only:
    one roll has no tolerance, the numbers must be the same)."""
    rng = np.random.default_rng([seed, 3])
    bad = 0
    worst = dict(stop=0.0, delta=0.0, lateral=0.0, speed=0.0, path=0.0, t=0.0)
    statuses = {}
    captured = 0
    steps_same = 0
    for it in range(n):
        p = random_solver_case(rng, 0.2)
        dist = math.hypot(p["hole"][0] - p["start"][0], p["hole"][1] - p["start"][1])
        v0 = math.sqrt(max(2.0 * p["a_r"] * (dist + 0.3), 0.0)) * rng.uniform(0.5, 1.5)
        phi = rng.normal(0.0, 0.08)
        cap_exp = float(rng.choice([0.5, 1.0]))
        stop = bool(rng.random() < 0.5)
        surf = ph.QuadraticSurface(*p["coeffs"], z0=p["z0"])
        ref = ph.simulate_putt(surf, p["start"], p["hole"], phi, v0, p["a_r"], np.array(p["grain"]),
                               capture=ph.CaptureModel(exponent=cap_exp), stop_on_capture=stop)
        st, r = solver.roll(p["coeffs"], p["start"], p["hole"], phi, v0, p["a_r"], p["grain"], cap_exp, stop, z0=p["z0"])
        statuses[int(ref.status)] = statuses.get(int(ref.status), 0) + 1
        captured += 1 if ref.captured else 0
        same = (st == GL_OK and r["status"] == int(ref.status) and r["captured"] == ref.captured
                and r["crossed_hole_line"] == ref.crossed_hole_line and r["side"] == ref.side)
        if same:
            steps_same += 1 if r["n_steps"] == len(ref.t) - 1 or True else 0
            pairs = [("stop", math.hypot(r["stop_x"] - ref.stop_xy[0], r["stop_y"] - ref.stop_xy[1])),
                     ("delta", abs(r["delta_m"] - ref.delta)), ("path", abs(r["path_length_m"] - ref.path_length)),
                     ("t", abs(r["t_end_s"] - ref.t_end)), ("speed", abs(r["speed_at_delta_mps"] - ref.speed_at_delta))]
            if ref.crossed_hole_line:
                pairs.append(("lateral", abs(r["lateral_at_line_m"] - ref.lateral_at_line)))
            for k, d in pairs:
                worst[k] = max(worst[k], d)
                if not d <= 1e-9:
                    same = False
        if not same:
            bad += 1
            if bad <= 20:
                print(f"  DISAGREEMENT roll {it} (seed {seed}): C {r}, reference status {int(ref.status)} "
                      f"captured {ref.captured} delta {ref.delta}")
    print(f"random rolls (double): {n} rolls, reference status counts {dict(sorted(statuses.items()))}, "
          f"{captured} holed; outside 1e-9: {bad}")
    print(f"  largest differences: {', '.join(f'{k} {v:.2e}' for k, v in worst.items())}")
    return bad


def run_random_small(solver, n, seed, es, Measurements):
    """fuse_range and quad_horizon on random and extreme inputs (double)."""
    rng = np.random.default_rng([seed, 4])
    bad = 0
    worst = 0.0
    for it in range(n):
        drops, _, _, _, _ = random_estimator_case(rng, es, Measurements, 0.6)
        m = drops[0]
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                r = es.fuse_range(m)
        except Exception:
            continue  # ZeroDivisionError / OverflowError of plain Python floats: C returns inf or NaN instead
        c = solver.fuse_range(m)
        for a, b in ((c["distance_m"], r.distance), (c["sigma_m"], r.sigma), (c["stereo_m"], r.stereo),
                     (c["sigma_stereo_m"], r.sigma_stereo), (c["mono_m"], r.mono), (c["sigma_mono_m"], r.sigma_mono)):
            ex = excess(a, b, 0.0)
            if ex > 1e-6 and not (math.isinf(a) and math.isinf(b)):
                bad += 1
                if bad <= 10:
                    print(f"  DISAGREEMENT fuse_range {it}: {c} against {r}")
                break
            if math.isfinite(ex):
                worst = max(worst, ex * REL)
    worst_h = 0.0
    for it in range(n // 4):
        coeffs = list(rng.normal(0.0, 0.03, 2)) + list(rng.normal(0.0, 0.01, 3))
        theta = float(rng.uniform(-math.pi, math.pi))
        h_cam = float(rng.choice([0.0056, 0.00485, 0.001, 0.05]))
        far = float(rng.uniform(0.2, 25.0))
        e_ref, r_ref = es.quad_horizon(coeffs, np.array([theta]), h_cam, 0.15, far)
        st, e_c, r_c = solver.quad_horizon(coeffs, theta, h_cam, 0.15, far)
        d = max(abs(e_c - float(e_ref[0])), abs(r_c - float(r_ref[0])) / far)
        worst_h = max(worst_h, d)
        if st != GL_OK or not d <= 1e-12:
            bad += 1
            if bad <= 10:
                print(f"  DISAGREEMENT quad_horizon {it}: C {e_c}, {r_c}; reference {float(e_ref[0])}, {float(r_ref[0])}")
    print(f"fuse_range ({n} records) and quad_horizon ({n // 4} rays): outside tolerance {bad}; "
          f"largest relative difference {worst:.2e} (range), {worst_h:.2e} (horizon)")
    return bad


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--lib", required=True, help="shared library built by `make diff`")
    ap.add_argument("--single", action="store_true", help="the library is the single-precision build")
    ap.add_argument("--vectors", nargs="?", const=DEFAULT_VECTORS, default=None,
                    help="run the reference vectors (default file: sim/results/reference_vectors.json)")
    ap.add_argument("--random", type=int, default=0, metavar="N",
                    help="N random reads and N random aim problems (and N / 4 rolls, N range fusions)")
    ap.add_argument("--seed", type=int, default=20261111)
    ap.add_argument("--hostile", type=float, default=0.3,
                    help="fraction of random cases pushed outside the nominal ranges (default 0.3)")
    ap.add_argument("--only", choices=("estimates", "solves", "rolls", "small"), default=None)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)
    solver = Solver(args.lib, double=not args.single)
    print(f"library {args.lib}: gl_solver_version 0x{solver.version():08x}, "
          f"{'double' if solver.double else 'single'} precision, structure sizes {solver.sizes}")
    bad = 0
    if args.vectors:
        bad += run_vectors(solver, args.vectors, args.verbose)
    if args.random > 0:
        es, ph, _, Measurements = load_reference()
        print(f"reference: greenline_sim from {SIM_DIR}, numba {'on' if ph.HAVE_NUMBA else 'OFF (pure Python kernels)'}")
        if args.only in (None, "estimates"):
            bad += run_random_estimates(solver, args.random, args.seed, args.hostile, es, Measurements)
        if args.only in (None, "solves"):
            bad += run_random_solves(solver, args.random, args.seed, args.hostile, ph)
        if solver.double and args.only in (None, "rolls"):
            bad += run_random_rolls(solver, max(args.random // 4, 1), args.seed, ph)
        if solver.double and args.only in (None, "small"):
            bad += run_random_small(solver, args.random, args.seed, es, Measurements)
    print("RESULT:", "agreement" if bad == 0 else f"{bad} DISAGREEMENTS")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
