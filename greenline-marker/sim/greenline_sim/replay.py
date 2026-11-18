"""Replay of a read logged by the GL-1 firmware (docs/VALIDATION_PLAN.md 3.3).

The firmware's field log holds, for every solved read, the complete
measurement record of every placement it handed to its estimator and the
options of that call (firmware/core/gl_fieldlog.h).  ``firmware/tools/glctl``
decodes a log dump into JSON; a decoded read is a dictionary with

    drops       list of placements, each the dictionary form of
                :class:`greenline_sim.measurements.Measurements`
                (``Measurements.to_dict``; ``None`` = not a number)
    ball_index  which placement is the one at the ball
    method      0 B1, 1 B0, 2 B2, 3 STRAIGHT (the firmware's codes)
    past        target roll-out past the hole, metres
    use_grain   bool
    near_miss   the firmware's near_miss_m (0 = off)
    estimate    what the firmware's estimator returned (optional; needed
                for :func:`compare`)

:func:`replay_read` runs THIS package's estimator - the reference the
firmware is a port of - on that record and returns its estimate in the same
dictionary form; :func:`compare` applies the comparison rule of the
firmware's own differential test (``firmware/tools/app_diff.py``: flags and
codes exact; of a solved aim the direction within 0.5 mrad, the speed within
0.1 %, the break within 0.01 cup, the confidence within 1e-4; of an aim that
is not a solution only its class).

Nothing here changes the estimator: it is a second entry to it.  The
reference is run with tight tolerances (the firmware's single-precision
tolerances are wider than the comparison rule) and WITHOUT the firmware's
budget of integration steps, which the reference does not have: a read that
the firmware cut short at its budget shows as a difference of class.
"""
from __future__ import annotations

import math
from dataclasses import replace
from typing import List, Optional, Sequence

from . import estimator as es
from .measurements import Measurements

METHODS = {0: "B1", 1: "B0", 2: "B2", 3: "STRAIGHT"}

#: comparison rule for the firmware's single-precision estimate: key -> (relative, absolute floor)
FIRMWARE_RULE = {
    "aim_azimuth_device": (0.0, 5e-4),
    "bearing": (0.0, 2e-6),
    "v0": (1e-3, 0.0),
    "plays_like": (2e-3, 0.0),
    "distance": (1e-5, 1e-6),
    "break_cups": (1e-3, 0.01),
    "slope_pct": (0.0, 1e-4),
    "confidence": (0.0, 1e-4),
}
#: of an aim that is not a solution only these are defined
_ALWAYS = ("distance", "bearing", "slope_pct", "confidence")
_ANGLES = ("phi", "aim_azimuth_device", "bearing")
CODES = ("base_hidden", "flag_missing", "range_missing", "poor_horizon", "fit_converged",
         "aim_source", "solve_status")


def _wrap(a: float) -> float:
    return math.atan2(math.sin(a), math.cos(a))


def reference_config(past: float = 0.30, use_grain: bool = False, near_miss: float = 0.0) -> es.EstimatorConfig:
    """The configuration the replay runs the reference with."""
    base = replace(es.EstimatorConfig(), tol_miss=1e-9, tol_pace=1e-9, lm_tol=1e-10, lm_max_iter=200)
    return replace(base, past=float(past), use_grain=bool(use_grain), near_miss_keep=float(near_miss))


def estimate_to_dict(est) -> dict:
    """An :class:`Estimate` as the dictionary the firmware's decoder produces."""
    return {
        "phi": float(est.phi),
        "aim_azimuth_device": float(est.aim_azimuth_device),
        "v0": float(est.v0),
        "plays_like": float(est.plays_like),
        "break_cups": float(est.break_cups),
        "distance": float(est.distance),
        "bearing": float(est.bearing),
        "slope_pct": float(est.slope_pct),
        "dz_hole": float(est.dz_hole),
        "confidence": float(est.confidence),
        "base_hidden": int(est.base_hidden),
        "flag_missing": int(est.flag_missing),
        "range_missing": int(est.range_missing),
        "poor_horizon": int(est.poor_horizon),
        "fit_converged": int(est.fit.converged),
        "aim_source": int(est.aim_source),
        "solve_status": int(est.solve_status),
    }


def replay_read(read: dict) -> dict:
    """Run the reference estimator on one decoded read record."""
    drops = read["drops"]
    if not drops:
        raise ValueError("a read record without a placement cannot be replayed")
    ball = int(read.get("ball_index", 0))
    if not 0 <= ball < len(drops):
        raise ValueError("ball_index %d outside the %d placements" % (ball, len(drops)))
    method = METHODS[int(read.get("method", 0))]
    ms = [Measurements.from_dict(d) for d in drops]
    ordered = [ms[ball]] + [m for i, m in enumerate(ms) if i != ball]  # the reference: ball first
    cfg = reference_config(read.get("past", 0.30), read.get("use_grain", False), read.get("near_miss", 0.0))
    est = es.estimate_batch([ordered], method, cfg)[0]
    return estimate_to_dict(est)


def compare(reference: dict, logged: dict, rule: Optional[dict] = None) -> List[str]:
    """Differences between the reference's estimate and the logged one.

    Returns a list of sentences; empty = they agree under ``rule``
    (default :data:`FIRMWARE_RULE`).
    """
    rule = FIRMWARE_RULE if rule is None else rule
    why: List[str] = []
    for key in CODES:
        if int(logged[key]) != int(reference[key]):
            why.append("%s %d, reference %d" % (key, int(logged[key]), int(reference[key])))
    solved = int(reference["aim_source"]) in (0, 1)
    for key, (rel, floor) in rule.items():
        if not solved and key not in _ALWAYS:
            continue
        a, b = logged[key], reference[key]
        if a is None or b is None or not (math.isfinite(a) and math.isfinite(b)):
            if not (a is None and b is None) and not (a is not None and b is not None and math.isnan(a) and math.isnan(b)):
                why.append("%s %r, reference %r" % (key, a, b))
            continue
        d = abs(_wrap(a - b)) if key in _ANGLES else abs(a - b)
        if d > max(floor, rel * abs(b)):
            why.append("%s %.9g, reference %.9g" % (key, a, b))
    return why


def replay_and_compare(reads: Sequence[dict]) -> List[dict]:
    """Replay every read; each result has ``reference``, ``logged`` (if the
    record carries an estimate), ``aim_diff_mrad`` and ``mismatches``."""
    out = []
    for read in reads:
        ref = replay_read(read)
        logged = read.get("estimate")
        item = {"read_id": read.get("read_id"), "reference": ref, "logged": logged,
                "mismatches": None, "aim_diff_mrad": None}
        if logged is not None:
            item["mismatches"] = compare(ref, logged)
            item["aim_diff_mrad"] = 1000.0 * abs(_wrap(logged["aim_azimuth_device"] - ref["aim_azimuth_device"]))
        out.append(item)
    return out
