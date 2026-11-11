"""Monte-Carlo evaluation of the GreenLine estimator on synthetic greens.

Run with ``python -m greenline_sim.montecarlo`` (from the ``sim`` directory).

For putt lengths 1.5 ... 12 m x four green classes x many seeded greens the
script simulates what the hardware would measure
(:mod:`greenline_sim.sensors`), lets every method turn that into an aim line
and a launch speed (:mod:`greenline_sim.estimator` plus the truth-based
references defined here), and then rolls the ball on the TRUE green with the
TRUE speed and grain.  It reports, per distance and class, the median and
90th-percentile lateral miss at the hole, the make probability with perfect
execution and the make probability with human execution noise.

Methods
-------
Device modes (estimator, Measurements only):

``STRAIGHT``   aim at the flag, flat-green pace - no slope reading.
``B0``         plane from one puck tilt reading (a digital-level marker).
``B1``         Quick Read: tilt + flag-base height.
``B2``         B1 + turf-horizon residuals.
``B0S``        Precision Read: B1 with a 180-degree spin-and-reread.
``SURVEY2/3``  Survey: two / three drops along the line.
``FLAGOUT``    flag-out fallback: the golfer points the visor by hand and
               dials the distance; tilt-only.

References that use the truth (defined in this module, NOT in the estimator):

``ORACLE``        true surface, true speed, true grain.
``ORACLE_SLOPE``  true surface, but the entered speed and the measured grain:
                  isolates how much of the miss is slope reading.
``HUMAN05/10``    a golfer who reads the path-average cross slope with
                  0.5 % / 1 % (1-sigma) error, knows the hole height and the
                  bearing exactly, and uses the same entered speed and
                  measured grain as the device.

A camera read in which the flag is not found is retried as a flag-out read
(the golfer points the visor at the hole and dials the distance); every
device mode then works from that fallback read.

Everything is deterministic given ``MCConfig.master_seed``; the sensor noise,
the human reading noise and the execution noise are common random numbers
across methods and across sweeps, so comparisons are paired.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import time
from dataclasses import asdict, dataclass, replace
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import estimator as es
from . import physics as ph
from . import sensors as se
from .greens import GREEN_CLASSES, PlacementError, PuttScenario, make_green, make_scenario
from .measurements import Measurements

__all__ = [
    "MCConfig",
    "Case",
    "Reads",
    "Outcome",
    "build_cases",
    "take_reads",
    "device_launches",
    "reference_launches",
    "evaluate",
    "summarise",
    "run_main",
    "run_sweeps",
    "run_all",
    "main",
]

DEVICE_METHODS = ("STRAIGHT", "B0", "B1", "B2", "B0S", "SURVEY2", "SURVEY3", "FLAGOUT")
REFERENCE_METHODS = ("HUMAN05", "HUMAN10", "ORACLE_SLOPE", "ORACLE")

# purposes of the independent random streams of one case
_STREAM_CAMERA = 0
_STREAM_FLAG_OUT = 1
_STREAM_SURVEY = 2
_STREAM_EXECUTION = 3
_STREAM_HUMAN_READ = 4


@dataclass(frozen=True)
class MCConfig:
    """Size and settings of the Monte Carlo.

    Attributes
    ----------
    distances : tuple of float [m]
    classes : tuple of str
    n_seeds : int
        Greens per class in the main experiment; each green is used once per
        distance, so there are ``n_seeds`` putts per (distance, class) cell.
    n_seeds_sweep : int
        Greens per class in the sensitivity sweeps (the first ``n_seeds_sweep``
        of the main set).
    n_exec : int
        Human-execution samples per putt and method.
    sigma_dir : float [rad];  sigma_speed : float [relative]
        Human execution noise on start direction and launch speed.
    seat_levels : tuple of float [rad]
        True seating noise levels of the main experiment.
    nominal_seat : float [rad]
        The level at which the horizon test and the diagnostics are run.
    human_cross_errors : tuple of float [m/m]
        1-sigma cross-slope reading errors of the two human baselines.
    master_seed : int
    """

    distances: Tuple[float, ...] = (1.5, 3.0, 4.5, 6.0, 9.0, 12.0)
    classes: Tuple[str, ...] = GREEN_CLASSES
    n_seeds: int = 150
    n_seeds_sweep: int = 60
    n_exec: int = 20
    sigma_dir: float = math.radians(1.0)
    sigma_speed: float = 0.06
    seat_levels: Tuple[float, ...] = (1.0e-3, 2.5e-3, 5.0e-3)
    nominal_seat: float = 2.5e-3
    human_cross_errors: Tuple[float, float] = (0.005, 0.010)
    master_seed: int = 20261111


# --------------------------------------------------------------------------
# Cases (the truth of each putt)
# --------------------------------------------------------------------------


@dataclass
class Case:
    """One putt of the Monte Carlo and the truth-derived facts about it.

    Attributes
    ----------
    scenario : PuttScenario
    cls_idx : int;  seed : int;  distance : float [m]
    bearing : float [rad]
        World azimuth of the ball->hole line.
    oracle_phi : float [rad];  oracle_v0 : float [m/s];  oracle_ok : bool
        Aim solution on the true surface with the true speed and grain.
    mean_cross : float [m/m]
        True cross slope (dz/dy in the putt frame, + = rises to the left)
        averaged along the straight ball->hole line.
    local_cross : float [m/m]
        True cross slope at the ball.
    mean_along : float [m/m]
        True mean slope along the line, ``dz / D``.
    double_break : bool
        The cross slope along the line changes sign with at least 0.3 % on
        both sides.
    """

    scenario: PuttScenario
    cls_idx: int
    seed: int
    distance: float
    bearing: float
    oracle_phi: float
    oracle_v0: float
    oracle_ok: bool
    mean_cross: float
    local_cross: float
    mean_along: float
    double_break: bool


def _wrap(angle):
    return np.arctan2(np.sin(angle), np.cos(angle))


def _stream(config: MCConfig, case: Case, purpose: int) -> np.random.Generator:
    """Independent, reproducible random stream for one purpose of one case."""
    key = [config.master_seed, case.cls_idx, int(round(case.distance * 1000.0)), case.seed, purpose]
    return np.random.default_rng(key)


def build_cases(config: MCConfig, n_seeds: Optional[int] = None) -> Tuple[List[Case], int]:
    """Generate the putts: ``n_seeds`` greens per class, one putt per distance.

    Returns ``(cases, n_skipped)``; a (green, distance) pair for which no
    legal putt exists (:class:`~greenline_sim.greens.PlacementError`) is
    skipped and counted, never silently replaced.
    """
    n_seeds = config.n_seeds if n_seeds is None else n_seeds
    cases: List[Case] = []
    skipped = 0
    frac = np.linspace(0.0, 1.0, 17)
    for seed in range(n_seeds):
        for cls in config.classes:
            cls_idx = GREEN_CLASSES.index(cls)
            green = make_green(cls, seed)
            for dist in config.distances:
                try:
                    sc = make_scenario(cls, dist, seed, green=green)
                except PlacementError:
                    skipped += 1
                    continue
                sol = ph.solve_aim(green.surface, sc.ball_xy, sc.hole_xy, green.a_r, green.grain)
                bearing = sc.bearing
                pts = sc.point_at(frac * sc.distance)
                gx, gy = green.grad(pts[:, 0], pts[:, 1])
                cross = -np.asarray(gx) * math.sin(bearing) + np.asarray(gy) * math.cos(bearing)
                cases.append(
                    Case(
                        scenario=sc,
                        cls_idx=cls_idx,
                        seed=seed,
                        distance=float(dist),
                        bearing=bearing,
                        oracle_phi=sol.phi,
                        oracle_v0=sol.v0,
                        oracle_ok=bool(sol.usable),
                        mean_cross=float(np.mean(cross)),
                        local_cross=float(cross[0]),
                        mean_along=sc.dz / sc.distance,
                        double_break=bool(cross.max() > 0.003 and cross.min() < -0.003),
                    )
                )
    return cases, skipped


# --------------------------------------------------------------------------
# Reads (what the device measures)
# --------------------------------------------------------------------------

Read = Tuple[Measurements, se.MeasurementTruth]


@dataclass
class Reads:
    """Simulated measurements for a list of cases.

    Attributes
    ----------
    first : list of Read
        The first camera read at the ball (the flag may not have been found).
    found : (n,) bool array
        Whether that read found the flag.
    quick : list of Read
        The read the single-placement modes work from: ``first`` if the flag
        was found, otherwise the flag-out retry.
    spin : list of Read or None
        The same placement read with a 180-degree spin (Precision Read).
    survey : list of list of Read, or None
        Survey drops (ball first); just the flag-out read if the flag was
        not found from the ball.
    flag_out : list of Read or None
        A flag-out read of every case (hand-pointed, dialled distance).
    """

    first: List[Read]
    found: np.ndarray
    quick: List[Read]
    spin: Optional[List[Read]] = None
    survey: Optional[List[List[Read]]] = None
    flag_out: Optional[List[Read]] = None


def _variant_green(case: Case, fringe: str):
    green = case.scenario.green
    if fringe == "realistic":
        return green
    if fringe == "no_surround":
        return green.without_surrounds()
    if fringe == "no_fringe":
        return green.without_fringe()
    if fringe == "mounded":
        return green.with_mounded_surrounds(seed=1000 * case.seed + case.cls_idx)
    raise ValueError("fringe must be 'realistic', 'no_surround', 'no_fringe' or 'mounded'")


def take_reads(
    cases: Sequence[Case],
    params: se.SensorParams,
    config: MCConfig,
    *,
    fringe: str = "realistic",
    with_horizon: bool = True,
    spin: bool = False,
    survey: bool = False,
    flag_out: bool = False,
) -> Reads:
    """Simulate the device's measurements for every case.

    Parameters
    ----------
    fringe : ``"realistic"`` (collar, rough and the generator's smooth
        surround terrain), ``"no_surround"`` (canopy steps only),
        ``"no_fringe"`` (the optimistic twin: the camera sees the smooth
        continuation of the putting surface) or ``"mounded"`` (the
        pessimistic twin: mounds and hollows of 0.2 m RMS, independent of
        the putting surface, beyond the collar).  Only the turf horizon
        differs between them.
    with_horizon : bool
        Capture the turf horizon in the camera read (needed by ``B2`` only).
    spin, survey, flag_out : bool
        Also take the Precision Read, the Survey drops and a flag-out read.
    """
    first: List[Read] = []
    quick: List[Read] = []
    found = np.zeros(len(cases), dtype=bool)
    spins: List[Read] = []
    surveys: List[List[Read]] = []
    flag_outs: List[Read] = []
    for i, case in enumerate(cases):
        green = _variant_green(case, fringe)
        ball = case.scenario.ball_xy
        hole = case.scenario.hole_xy
        cam = se.measure(green, ball, hole, params, _stream(config, case, _STREAM_CAMERA), with_horizon=with_horizon)
        first.append(cam)
        found[i] = cam[0].flag_found
        fallback = None
        if not found[i] or flag_out:
            fallback = se.measure(
                green, ball, hole, params, _stream(config, case, _STREAM_FLAG_OUT), mode="flag_out", with_horizon=False
            )
        quick.append(cam if found[i] else fallback)
        if spin:
            if found[i]:
                spins.append(
                    se.measure(green, ball, hole, params, _stream(config, case, _STREAM_CAMERA), spin=True, with_horizon=False)
                )
            else:
                spins.append(
                    se.measure(
                        green, ball, hole, params, _stream(config, case, _STREAM_FLAG_OUT),
                        mode="flag_out", spin=True, with_horizon=False,
                    )
                )
        if survey:
            if found[i]:
                surveys.append(
                    se.measure_survey(green, ball, hole, params, _stream(config, case, _STREAM_SURVEY), n_drops=3, first=cam)
                )
            else:
                surveys.append([fallback])
        if flag_out:
            flag_outs.append(fallback)
    return Reads(
        first=first,
        found=found,
        quick=quick,
        spin=spins if spin else None,
        survey=surveys if survey else None,
        flag_out=flag_outs if flag_out else None,
    )


# --------------------------------------------------------------------------
# Launches (what each method tells the golfer to do)
# --------------------------------------------------------------------------


@dataclass
class Launch:
    """Launch conditions of one method for every case.

    ``phi`` [rad] is relative to the TRUE ball->hole line (+ = left), i.e. it
    includes the method's bearing error; ``v0`` [m/s].  ``estimates`` holds
    the estimator output for device methods (None for references).
    ``n_unsolved`` counts the cases in which the aim solver did not return a
    usable solution and a fallback (best iterate, or straight at flat pace)
    was rolled instead.
    """

    phi: np.ndarray
    v0: np.ndarray
    estimates: Optional[List[es.Estimate]] = None
    n_unsolved: int = 0


def _launch_from(estimates: List[es.Estimate], truths: Sequence[se.MeasurementTruth]) -> Launch:
    """Turn device-frame aim lines into launch angles relative to the true line."""
    phi = np.array([_wrap(t.heading + e.aim_azimuth_device - t.bearing) for e, t in zip(estimates, truths)])
    v0 = np.array([e.v0 for e in estimates])
    unsolved = sum(1 for e in estimates if e.aim_source != es.AIM_FROM_PATCH and e.method != "STRAIGHT")
    return Launch(phi=phi, v0=v0, estimates=estimates, n_unsolved=unsolved)


def device_launches(
    reads: Reads,
    methods: Sequence[str],
    est_config: es.EstimatorConfig = es.EstimatorConfig(),
) -> Dict[str, Launch]:
    """Run the estimator for the requested device modes.

    ``methods`` may contain any of ``STRAIGHT, B0, B1, B2, B0S, SURVEY2,
    SURVEY3, FLAGOUT``.  The estimator receives the ``Measurements`` only;
    the truth records are used afterwards, to express the resulting aim line
    relative to the true ball->hole line.
    """
    out: Dict[str, Launch] = {}
    quick_meas = [m for m, _ in reads.quick]
    quick_truth = [t for _, t in reads.quick]
    for name in methods:
        if name in ("STRAIGHT", "B0", "B1", "B2"):
            out[name] = _launch_from(es.estimate_batch(quick_meas, name, est_config), quick_truth)
        elif name == "B0S":
            if reads.spin is None:
                raise ValueError("B0S needs reads taken with spin=True")
            out[name] = _launch_from(
                es.estimate_batch([m for m, _ in reads.spin], "B1", est_config), [t for _, t in reads.spin]
            )
        elif name in ("SURVEY2", "SURVEY3"):
            if reads.survey is None:
                raise ValueError(f"{name} needs reads taken with survey=True")
            n_drops = 2 if name == "SURVEY2" else 3
            items = [[m for m, _ in drops[:n_drops]] for drops in reads.survey]
            out[name] = _launch_from(es.estimate_batch(items, "B1", est_config), [drops[0][1] for drops in reads.survey])
        elif name == "FLAGOUT":
            if reads.flag_out is None:
                raise ValueError("FLAGOUT needs reads taken with flag_out=True")
            out[name] = _launch_from(
                es.estimate_batch([m for m, _ in reads.flag_out], "B0", est_config), [t for _, t in reads.flag_out]
            )
        else:
            raise ValueError(f"unknown device method {name!r}")
    return out


def reference_launches(
    cases: Sequence[Case],
    reads: Reads,
    config: MCConfig,
    methods: Sequence[str] = REFERENCE_METHODS,
    est_config: es.EstimatorConfig = es.EstimatorConfig(),
) -> Dict[str, Launch]:
    """Launches of the truth-based references (ORACLE, ORACLE_SLOPE, HUMAN05/10).

    These use the true green and are therefore NOT part of the estimator.
    The entered green speed and the measured grain are taken from the
    ``quick`` read, so that ``ORACLE_SLOPE`` and the human baselines have
    exactly the speed and grain knowledge the device has.
    """
    n = len(cases)
    out: Dict[str, Launch] = {}
    past = est_config.past
    if "ORACLE" in methods:
        out["ORACLE"] = Launch(
            phi=np.array([c.oracle_phi for c in cases]),
            v0=np.array([c.oracle_v0 for c in cases]),
            n_unsolved=sum(1 for c in cases if not c.oracle_ok),
        )
    entered_a_r = np.array([ph.stimp_to_decel(m.stimp_ft) for m, _ in reads.quick])
    # measured grain as kappa * g_hat in the WORLD frame (device azimuth + true heading)
    grain_world = np.array(
        [
            [m.grain_kappa * math.cos(m.grain_azimuth + t.heading), m.grain_kappa * math.sin(m.grain_azimuth + t.heading)]
            for m, t in reads.quick
        ]
    ).reshape(n, 2)
    if "ORACLE_SLOPE" in methods:
        phi = np.zeros(n)
        v0 = np.zeros(n)
        unsolved = 0
        for i, case in enumerate(cases):
            sc = case.scenario
            sol = ph.solve_aim(sc.green.surface, sc.ball_xy, sc.hole_xy, entered_a_r[i], grain_world[i], past)
            unsolved += 0 if sol.usable else 1
            if sol.usable or (math.isfinite(sol.phi) and math.isfinite(sol.v0) and sol.v0 > 0.0):
                phi[i], v0[i] = sol.phi, sol.v0  # the best iterate if not usable (counted in n_unsolved)
            else:  # no finite iterate with the entered speed: straight at flat pace
                phi[i], v0[i] = 0.0, math.sqrt(2.0 * entered_a_r[i] * (case.distance + past))
        out["ORACLE_SLOPE"] = Launch(phi=phi, v0=v0, n_unsolved=unsolved)
    human = [name for name in methods if name.startswith("HUMAN")]
    if human:
        bearing = np.array([c.bearing for c in cases])
        cb, sb = np.cos(bearing), np.sin(bearing)
        grain_putt = np.stack(
            [grain_world[:, 0] * cb + grain_world[:, 1] * sb, -grain_world[:, 0] * sb + grain_world[:, 1] * cb], axis=1
        )
        dist = np.array([c.distance for c in cases])
        z_read = np.array([_stream(config, c, _STREAM_HUMAN_READ).standard_normal() for c in cases])
        for name in human:
            sigma = {"HUMAN05": config.human_cross_errors[0], "HUMAN10": config.human_cross_errors[1]}[name]
            coeffs = np.zeros((n, 5))
            coeffs[:, 0] = [c.mean_along for c in cases]
            coeffs[:, 1] = np.array([c.mean_cross for c in cases]) + sigma * z_read
            sol = ph.solve_aim_quadratic_batch(coeffs, dist, entered_a_r, grain_putt, past)
            phi = np.where(np.isfinite(sol.phi), sol.phi, 0.0)
            v0 = np.where(np.isfinite(sol.v0) & (sol.v0 > 0.0), sol.v0, np.sqrt(2.0 * entered_a_r * (dist + past)))
            out[name] = Launch(phi=phi, v0=v0, n_unsolved=int(np.sum(~sol.usable)))
    return out


# --------------------------------------------------------------------------
# Rolling on the true green
# --------------------------------------------------------------------------


@dataclass
class Outcome:
    """What happened when a method's launch was rolled on the true green.

    Arrays over the cases: ``lat`` signed lateral miss at the hole with
    perfect execution [m] (+ = left); ``made`` holed with perfect execution;
    ``short`` the ball did not reach the hole; ``leave`` distance of the
    resting ball from the hole [m] (0 if holed); ``made_h`` fraction of the
    human-execution samples holed; ``lat_h`` (n, n_exec) lateral misses with
    human execution [m]; ``pace`` pace error of the perfectly executed putt
    [m]: how far past the hole the ball would roll on a flat green of the
    true speed given its speed at the hole (minus the shortfall if it never
    gets there), relative to the 0.30 m target.
    """

    lat: np.ndarray
    made: np.ndarray
    short: np.ndarray
    leave: np.ndarray
    made_h: np.ndarray
    lat_h: np.ndarray
    pace: np.ndarray


def evaluate(
    cases: Sequence[Case], launches: Dict[str, Launch], config: MCConfig, past: float = ph.DEFAULT_PAST
) -> Dict[str, Outcome]:
    """Roll every method's launch on the TRUE green (true speed, true grain).

    Per case one perfectly executed putt per method plus ``n_exec`` putts
    with human execution noise (direction ``sigma_dir``, speed
    ``sigma_speed``); the execution errors are the same for every method.
    ``past`` [m] is the target pace the pace error is measured against.
    """
    names = list(launches)
    n = len(cases)
    n_m = len(names)
    n_e = config.n_exec
    per = 1 + n_e
    lat = np.zeros((n_m, n))
    made = np.zeros((n_m, n), dtype=bool)
    short = np.zeros((n_m, n), dtype=bool)
    leave = np.zeros((n_m, n))
    made_h = np.zeros((n_m, n))
    lat_h = np.zeros((n_m, n, n_e), dtype=np.float32)
    pace = np.zeros((n_m, n))
    phi_m = np.stack([launches[k].phi for k in names])  # (methods, cases)
    v0_m = np.stack([launches[k].v0 for k in names])
    if not (np.all(np.isfinite(phi_m)) and np.all(np.isfinite(v0_m)) and np.all(v0_m > 0.0)):
        raise ValueError("a method produced a non-finite or non-positive launch")
    for i, case in enumerate(cases):
        sc = case.scenario
        green = sc.green
        gen = _stream(config, case, _STREAM_EXECUTION)
        d_phi = np.concatenate([[0.0], config.sigma_dir * gen.standard_normal(n_e)])
        f_v = np.concatenate([[1.0], np.maximum(1.0 + config.sigma_speed * gen.standard_normal(n_e), 0.2)])
        phi_all = (phi_m[:, i][:, None] + d_phi[None, :]).ravel()
        v_all = (v0_m[:, i][:, None] * f_v[None, :]).ravel()
        res = ph.roll_batch(green.surface, sc.ball_xy, sc.hole_xy, phi_all, v_all, green.a_r, green.grain)
        cap = res.captured.reshape(n_m, per)
        lm = res.lateral_miss.reshape(n_m, per)
        made[:, i] = cap[:, 0]
        lat[:, i] = lm[:, 0]
        crossed = res.crossed_hole_line.reshape(n_m, per)[:, 0]
        short[:, i] = ~crossed
        leave[:, i] = res.final_distance.reshape(n_m, per)[:, 0]
        v_line = np.where(crossed, res.speed_at_line.reshape(n_m, per)[:, 0], 0.0)
        beyond = np.where(crossed, v_line * v_line / (2.0 * green.a_r), -res.shortfall.reshape(n_m, per)[:, 0])
        pace[:, i] = beyond - past
        made_h[:, i] = cap[:, 1:].mean(axis=1)
        lat_h[:, i, :] = lm[:, 1:]
    return {
        name: Outcome(
            lat=lat[k], made=made[k], short=short[k], leave=leave[k], made_h=made_h[k], lat_h=lat_h[k], pace=pace[k]
        )
        for k, name in enumerate(names)
    }


# --------------------------------------------------------------------------
# Statistics
# --------------------------------------------------------------------------


def summarise(outcome: Outcome, mask: Optional[np.ndarray] = None) -> Dict[str, float]:
    """Summary statistics of one method over the cases selected by ``mask``.

    ``median_miss`` / ``p90_miss``: median and 90th percentile of the
    absolute lateral miss at the hole with perfect execution [m];
    ``make_perfect`` / ``make_human``: make probability with perfect and
    with human execution; ``short``: fraction of perfectly executed putts
    that do not reach the hole; ``median_leave``: median distance left after
    a perfectly executed putt [m] (0 if holed); ``median_miss_human``: median
    absolute lateral miss with human execution [m]; ``median_pace_err`` /
    ``mean_pace_err``: median absolute and mean signed (clipped at 3 m) pace
    error of the perfectly executed putt [m] (see :class:`Outcome`).
    """
    if mask is None:
        mask = np.ones(outcome.lat.shape[0], dtype=bool)
    n = int(mask.sum())
    if n == 0:
        return {"n": 0}
    a = np.abs(outcome.lat[mask])
    return {
        "n": n,
        "median_miss": float(np.median(a)),
        "p90_miss": float(np.percentile(a, 90.0)),
        "make_perfect": float(np.mean(outcome.made[mask])),
        "make_human": float(np.mean(outcome.made_h[mask])),
        "short": float(np.mean(outcome.short[mask])),
        "median_leave": float(np.median(outcome.leave[mask])),
        "median_miss_human": float(np.median(np.abs(outcome.lat_h[mask]))),
        "median_pace_err": float(np.median(np.abs(outcome.pace[mask]))),
        "mean_pace_err": float(np.mean(np.clip(outcome.pace[mask], -3.0, 3.0))),
    }


def _tables(cases: Sequence[Case], outcome: Outcome, config: MCConfig) -> Dict[str, dict]:
    """Summaries overall, by distance, by class and by (distance, class)."""
    dist = np.array([c.distance for c in cases])
    cls = np.array([c.cls_idx for c in cases])
    out = {"overall": summarise(outcome), "by_distance": {}, "by_class": {}, "by_distance_class": {}}
    for d in config.distances:
        out["by_distance"][f"{d:g}"] = summarise(outcome, dist == d)
        for name in config.classes:
            k = GREEN_CLASSES.index(name)
            out["by_distance_class"][f"{d:g}|{name}"] = summarise(outcome, (dist == d) & (cls == k))
    for name in config.classes:
        out["by_class"][name] = summarise(outcome, cls == GREEN_CLASSES.index(name))
    return out


def paired_delta(a: Outcome, b: Outcome, mask: Optional[np.ndarray] = None) -> Dict[str, float]:
    """Paired comparison ``b`` minus ``a`` over the same cases.

    ``d_make``: difference in make probability (perfect execution) with its
    standard error; ``d_mean_miss``: difference in mean absolute lateral
    miss, each miss clipped at 1 m so that a few run-away balls do not
    dominate, with its standard error [m]; ``b_closer``: fraction of cases
    in which ``b`` misses by less than ``a`` (ties excluded).
    """
    if mask is None:
        mask = np.ones(a.lat.shape[0], dtype=bool)
    n = int(mask.sum())
    if n < 2:
        return {"n": n}
    dm = b.made[mask].astype(float) - a.made[mask].astype(float)
    la = np.minimum(np.abs(a.lat[mask]), 1.0)
    lb = np.minimum(np.abs(b.lat[mask]), 1.0)
    dl = lb - la
    differ = np.abs(dl) > 1e-9
    return {
        "n": n,
        "d_make": float(dm.mean()),
        "d_make_se": float(dm.std(ddof=1) / math.sqrt(n)),
        "d_mean_miss": float(dl.mean()),
        "d_mean_miss_se": float(dl.std(ddof=1) / math.sqrt(n)),
        "median_miss_a": float(np.median(np.abs(a.lat[mask]))),
        "median_miss_b": float(np.median(np.abs(b.lat[mask]))),
        "b_closer": float(np.mean(dl[differ] < 0.0)) if differ.any() else 0.5,
        "n_differ": int(differ.sum()),
    }


def verdict(delta: Dict[str, float]) -> str:
    """``"helps"``, ``"hurts"`` or ``"no measurable effect"`` for a
    :func:`paired_delta` (``b`` relative to ``a``), judged at 2 standard
    errors on the make probability and on the mean clipped miss."""
    if delta.get("n", 0) < 2:
        return "not enough cases"
    z_make = delta["d_make"] / delta["d_make_se"] if delta["d_make_se"] > 0.0 else 0.0
    z_miss = delta["d_mean_miss"] / delta["d_mean_miss_se"] if delta["d_mean_miss_se"] > 0.0 else 0.0
    better = (z_make > 2.0) + (z_miss < -2.0)
    worse = (z_make < -2.0) + (z_miss > 2.0)
    if better and not worse:
        return "helps"
    if worse and not better:
        return "hurts"
    if better and worse:
        return "mixed (make probability and mean miss disagree)"
    return "no measurable effect"


# --------------------------------------------------------------------------
# Diagnostics
# --------------------------------------------------------------------------


def _rms(x) -> float:
    x = np.asarray(x, dtype=float)
    return float(np.sqrt(np.mean(x * x))) if x.size else math.nan


def _range_table(cases: Sequence[Case], reads: Reads, config: MCConfig, est_config: es.EstimatorConfig) -> Dict[str, dict]:
    """Relative range error by distance for stereo only, monocular only and fused."""
    rows: Dict[str, dict] = {}
    dist = np.array([c.distance for c in cases])
    est = [es.fuse_range(m, est_config) if m.flag_found else None for m, _ in reads.first]
    for d in config.distances:
        idx = [i for i in np.nonzero(dist == d)[0] if est[i] is not None]
        e_s = np.array([est[i].stereo / d - 1.0 for i in idx])
        e_m = np.array([est[i].mono / d - 1.0 for i in idx])
        e_f = np.array([est[i].distance / d - 1.0 for i in idx])
        has_m = np.isfinite(e_m)
        has_s = np.isfinite(e_s)
        rows[f"{d:g}"] = {
            "n_found": len(idx),
            "stereo_rms": _rms(e_s[has_s]),
            "stereo_bias": float(np.mean(e_s[has_s])) if has_s.any() else math.nan,
            "stereo_predicted": d * est_config.sigma_disp / (reads.first[0][0].f_px * reads.first[0][0].baseline),
            "mono_available": float(np.mean(has_m)) if idx else math.nan,
            "mono_rms": _rms(e_m[has_m]) if has_m.any() else math.nan,
            "fused_rms": _rms(e_f[np.isfinite(e_f)]),
            "fused_bias": float(np.mean(e_f[np.isfinite(e_f)])) if np.isfinite(e_f).any() else math.nan,
        }
    return rows


def _flag_table(cases: Sequence[Case], reads: Reads, config: MCConfig) -> Dict[str, dict]:
    """Flag detection, base visibility and what forms the turf horizon."""
    dist = np.array([c.distance for c in cases])
    cls = np.array([c.cls_idx for c in cases])
    hidden = np.array([not t.base_visible for _, t in reads.first])
    hidden_h = np.array([t.hidden_height for _, t in reads.first])
    in_fov = np.array([t.in_fov for _, t in reads.first])
    region = None
    hor_dist = None
    if reads.first[0][1].horizon is not None:
        region = np.array([[np.mean(t.horizon.region == k) for k in (0, 1, 2)] for _, t in reads.first])
        hor_dist = np.array([np.median(t.horizon.distance) for _, t in reads.first])
    out: Dict[str, dict] = {"by_distance": {}, "hidden_by_distance_class": {}}
    for d in config.distances:
        sel = dist == d
        row = {
            "n": int(sel.sum()),
            "found": float(np.mean(reads.found[sel])),
            "in_fov": float(np.mean(in_fov[sel])),
            "base_hidden": float(np.mean(hidden[sel])),
            "hidden_height_median": float(np.median(hidden_h[sel & hidden])) if (sel & hidden).any() else 0.0,
        }
        if region is not None:
            row["horizon_on_green"] = float(np.mean(region[sel, 0]))
            row["horizon_on_collar"] = float(np.mean(region[sel, 1]))
            row["horizon_on_rough"] = float(np.mean(region[sel, 2]))
            row["horizon_distance_median"] = float(np.median(hor_dist[sel]))
        out["by_distance"][f"{d:g}"] = row
        for name in config.classes:
            s2 = sel & (cls == GREEN_CLASSES.index(name))
            out["hidden_by_distance_class"][f"{d:g}|{name}"] = float(np.mean(hidden[s2])) if s2.any() else math.nan
    return out


def _slope_error_table(
    cases: Sequence[Case], launches: Dict[str, Launch], reads: Reads, config: MCConfig
) -> Dict[str, dict]:
    """Error budget of the slope read, by distance [m/m].

    ``representativeness``: RMS difference between the true cross slope at
    the ball and its true average along the line (the error a perfect
    single-point reading would still make).  Per method: RMS error of the
    estimated mean cross slope ``b + 0.5 d D`` and of the estimated mean
    along-line slope ``a + 0.5 c D``, against the truth.
    """
    dist = np.array([c.distance for c in cases])
    mean_cross = np.array([c.mean_cross for c in cases])
    local_cross = np.array([c.local_cross for c in cases])
    mean_along = np.array([c.mean_along for c in cases])
    hidden = np.array([not t.base_visible for _, t in reads.first])
    out: Dict[str, dict] = {}
    for d in config.distances:
        sel = dist == d
        row = {
            "representativeness": _rms(local_cross[sel] - mean_cross[sel]),
            "mean_cross_rms": _rms(mean_cross[sel]),
            "cross": {},
            "along": {},
            "along_base_visible": {},
            "along_base_hidden": {},
        }
        for name, launch in launches.items():
            if launch.estimates is None or name == "STRAIGHT":
                continue
            est = launch.estimates
            ok = sel & reads.found  # camera reads only: the putt frame is the true one to ~1 mrad
            if name == "FLAGOUT":
                ok = sel
            cross = np.array([e.patch[1] + 0.5 * e.patch[3] * e.distance for e in est])
            along = np.array([e.patch[0] + 0.5 * e.patch[2] * e.distance for e in est])
            row["cross"][name] = _rms(cross[ok] - mean_cross[ok])
            row["along"][name] = _rms(along[ok] - mean_along[ok])
            row["along_base_visible"][name] = _rms(along[ok & ~hidden] - mean_along[ok & ~hidden])
            row["along_base_hidden"][name] = _rms(along[ok & hidden] - mean_along[ok & hidden])
        out[f"{d:g}"] = row
    return out


def _calibration(launch: Launch, outcome: Outcome, edges=(0.0, 0.1, 0.2, 0.35, 0.5, 0.7, 0.85, 1.0000001)) -> List[dict]:
    """Confidence score against what happened: per confidence bin, the mean
    score and the fraction of perfectly executed putts that passed within
    the hole radius of its centre."""
    conf = np.array([e.confidence for e in launch.estimates])
    inside = np.abs(outcome.lat) < ph.HOLE_R
    rows = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = (conf >= lo) & (conf < hi)
        if sel.any():
            rows.append(
                {
                    "lo": lo,
                    "hi": min(hi, 1.0),
                    "n": int(sel.sum()),
                    "mean_confidence": float(conf[sel].mean()),
                    "within_hole": float(inside[sel].mean()),
                    "made": float(outcome.made[sel].mean()),
                }
            )
    return rows


def _aim_sources(launches: Dict[str, Launch]) -> Dict[str, List[int]]:
    """How often each device method's aim came from the patch (0), its secant
    plane (1), a best-effort iterate (2) or the straight fallback (3)."""
    out = {}
    for name, launch in launches.items():
        if launch.estimates is not None and name != "STRAIGHT":
            out[name] = np.bincount([e.aim_source for e in launch.estimates], minlength=4).tolist()
    return out


def _subset_tables(cases: Sequence[Case], outcomes: Dict[str, Outcome], reads: Reads, methods: Sequence[str]) -> Dict[str, dict]:
    """Performance on the putts where fusion is expected to struggle."""
    hidden = np.array([not t.base_visible for _, t in reads.first])
    double = np.array([c.double_break for c in cases])
    dist = np.array([c.distance for c in cases])
    sets = {
        "base_visible": ~hidden,
        "base_hidden (crowned line)": hidden,
        "single_break": ~double,
        "double_break": double,
        "double_break, D >= 6 m": double & (dist >= 6.0),
        "flag_not_found": ~reads.found,
    }
    out: Dict[str, dict] = {}
    for label, sel in sets.items():
        out[label] = {name: summarise(outcomes[name], sel) for name in methods if name in outcomes}
    return out


# --------------------------------------------------------------------------
# Experiments
# --------------------------------------------------------------------------


def run_main(
    cases: Sequence[Case],
    config: MCConfig,
    base_params: se.SensorParams = se.SensorParams(),
    est_config: es.EstimatorConfig = es.EstimatorConfig(),
    log: Callable[[str], None] = print,
) -> Dict[str, dict]:
    """Main experiment: every method at every seating-noise level, plus the
    horizon test and the diagnostics at the nominal level."""
    result: Dict[str, dict] = {"by_seat": {}, "methods": list(DEVICE_METHODS + REFERENCE_METHODS)}
    for seat in config.seat_levels:
        t0 = time.perf_counter()
        params = replace(base_params, sigma_seat=seat)
        reads = take_reads(cases, params, config, with_horizon=True, spin=True, survey=True, flag_out=True)
        launches = device_launches(reads, DEVICE_METHODS, est_config)
        launches.update(reference_launches(cases, reads, config, REFERENCE_METHODS, est_config))
        nominal = abs(seat - config.nominal_seat) < 1e-12
        if nominal:
            for fringe, name in (("no_surround", "B2_NOSURROUND"), ("no_fringe", "B2_NOFRINGE"), ("mounded", "B2_MOUNDED")):
                alt = take_reads(cases, params, config, fringe=fringe, with_horizon=True)
                launches[name] = device_launches(alt, ["B2"], est_config)["B2"]
        outcomes = evaluate(cases, launches, config)
        key = f"{seat * 1e3:g}"
        result["by_seat"][key] = {name: _tables(cases, outcomes[name], config) for name in outcomes}
        if nominal:
            cls = np.array([c.cls_idx for c in cases])
            horizon = {}
            for label, name in (
                ("realistic", "B2"),
                ("no_surround", "B2_NOSURROUND"),
                ("no_fringe", "B2_NOFRINGE"),
                ("mounded", "B2_MOUNDED"),
            ):
                entry = {"all": paired_delta(outcomes["B1"], outcomes[name])}
                entry["all"]["verdict"] = verdict(entry["all"])
                for cname in config.classes:
                    sel = cls == GREEN_CLASSES.index(cname)
                    entry[cname] = paired_delta(outcomes["B1"], outcomes[name], sel)
                    entry[cname]["verdict"] = verdict(entry[cname])
                horizon[label] = entry
            result["horizon_test"] = horizon
            result["diagnostics"] = {
                "range": _range_table(cases, reads, config, est_config),
                "flag": _flag_table(cases, reads, config),
                "slope_error": _slope_error_table(cases, launches, reads, config),
                "calibration": {name: _calibration(launches[name], outcomes[name]) for name in ("B1", "B2", "B0S", "SURVEY3")},
                "aim_sources": _aim_sources(launches),
                "unsolved": {name: int(launch.n_unsolved) for name, launch in launches.items()},
                "subsets": _subset_tables(
                    cases, outcomes, reads, ("STRAIGHT", "B0", "B1", "B2", "B0S", "SURVEY3", "HUMAN05", "HUMAN10", "ORACLE")
                ),
                "double_break_fraction": {
                    f"{d:g}": float(np.mean([c.double_break for c in cases if c.distance == d])) for d in config.distances
                },
                "oracle_not_solved": int(sum(not c.oracle_ok for c in cases)),
                "paired": {
                    "B0S_vs_B1": paired_delta(outcomes["B1"], outcomes["B0S"]),
                    "SURVEY3_vs_B1": paired_delta(outcomes["B1"], outcomes["SURVEY3"]),
                    "B1_vs_B0": paired_delta(outcomes["B0"], outcomes["B1"]),
                    "B0_vs_FLAGOUT": paired_delta(outcomes["FLAGOUT"], outcomes["B0"]),
                    "HUMAN05_vs_B1": paired_delta(outcomes["B1"], outcomes["HUMAN05"]),
                    "HUMAN10_vs_B1": paired_delta(outcomes["B1"], outcomes["HUMAN10"]),
                },
            }
        log(f"  main, seating {key} mrad: {time.perf_counter() - t0:.1f} s")
    return result


def run_sweeps(
    cases: Sequence[Case],
    config: MCConfig,
    base_params: se.SensorParams = se.SensorParams(),
    est_config: es.EstimatorConfig = es.EstimatorConfig(),
    log: Callable[[str], None] = print,
) -> Dict[str, dict]:
    """Sensitivity sweeps on the sweep subset of cases (nominal seating noise).

    Every entry maps a variant label to ``{method: tables}`` (see
    :func:`_tables`).  The label ``"baseline"`` is the default configuration
    on the same cases, so every variant can be compared like for like.
    """
    t0 = time.perf_counter()
    read_cache: Dict[str, Reads] = {}

    def reads_for(key: str, params: se.SensorParams, **kwargs) -> Reads:
        if key not in read_cache:
            read_cache[key] = take_reads(cases, params, config, **kwargs)
        return read_cache[key]

    def run(reads: Reads, methods: Sequence[str], cfg: es.EstimatorConfig, rename: Optional[Dict[str, str]] = None):
        dev = [m for m in methods if m in DEVICE_METHODS]
        ref = [m for m in methods if m in REFERENCE_METHODS]
        launches = device_launches(reads, dev, cfg)
        if ref:
            launches.update(reference_launches(cases, reads, config, ref, cfg))
        outcomes = evaluate(cases, launches, config)
        return {(rename or {}).get(name, name): _tables(cases, outcomes[name], config) for name in outcomes}, outcomes

    sweeps: Dict[str, dict] = {}
    base_reads = reads_for("base", base_params, with_horizon=True, spin=True)
    baseline, base_out = run(base_reads, ("B0", "B1", "B2", "B0S", "ORACLE_SLOPE", "ORACLE"), est_config)
    sweeps["baseline"] = baseline
    log(f"  sweeps: baseline {time.perf_counter() - t0:.1f} s")

    # camera preset
    cam: Dict[str, dict] = {"GL1": {k: baseline[k] for k in ("B1", "B2")}}
    cam_range: Dict[str, dict] = {"GL1": _range_table(cases, base_reads, config, est_config)}
    cam_found: Dict[str, float] = {"GL1": float(np.mean(base_reads.found))}
    for name in ("QVGA", "VGA", "2MP"):
        params = replace(base_params, camera=se.CAMERA_PRESETS[name])
        reads = reads_for(f"cam_{name}", params, with_horizon=True)
        cam[name], _ = run(reads, ("B1", "B2"), est_config)
        cam_range[name] = _range_table(cases, reads, config, est_config)
        cam_found[name] = float(np.mean(reads.found))
    sweeps["camera"] = cam
    sweeps["camera_range"] = cam_range
    sweeps["camera_found"] = cam_found
    log(f"  sweeps: camera presets {time.perf_counter() - t0:.1f} s")

    # lens height
    height: Dict[str, dict] = {}
    for h_mm in (3.0, 4.5, 6.0):
        params = replace(base_params, camera=replace(base_params.camera, h_cam=h_mm * 1e-3))
        reads = reads_for(f"h_{h_mm:g}", params, with_horizon=True)
        height[f"{h_mm:g}"], _ = run(reads, ("B1", "B2"), est_config)
        height[f"{h_mm:g}"]["base_hidden"] = float(np.mean([not t.base_visible for _, t in reads.first]))
    height["5.6 (GL1)"] = {k: baseline[k] for k in ("B1", "B2")}
    height["5.6 (GL1)"]["base_hidden"] = float(np.mean([not t.base_visible for _, t in base_reads.first]))
    sweeps["h_cam_mm"] = height
    log(f"  sweeps: lens height {time.perf_counter() - t0:.1f} s")

    # flag base on / off, and a device that cannot tell a hidden base from a visible one
    no_base, no_base_out = run(base_reads, ("B1", "B2"), replace(est_config, use_flag_base=False))
    blind, blind_out = run(base_reads, ("B1",), replace(est_config, assume_base_visible=True))
    sweeps["flag_base"] = {
        "with flag base": {k: baseline[k] for k in ("B1", "B2")},
        "without flag base": no_base,
        "base visibility unknown (always assumed visible)": blind,
    }
    sweeps["flag_base_paired"] = {
        "B1_with_vs_without": paired_delta(no_base_out["B1"], base_out["B1"]),
        "B2_with_vs_without": paired_delta(no_base_out["B2"], base_out["B2"]),
        "B1_blind_vs_informed": paired_delta(base_out["B1"], blind_out["B1"]),
    }

    # entered green speed
    stimp: Dict[str, dict] = {}
    for err in (0.0, 0.07, 0.15):
        if abs(err - base_params.sigma_stimp) < 1e-12:
            stimp[f"{err * 100:g}"] = {k: baseline[k] for k in ("B1", "ORACLE_SLOPE")}
            continue
        reads = reads_for(f"stimp_{err:g}", replace(base_params, sigma_stimp=err), with_horizon=False)
        stimp[f"{err * 100:g}"], _ = run(reads, ("B1", "ORACLE_SLOPE"), est_config)
    sweeps["stimp_error_pct"] = stimp

    # grain sensor
    perfect_grain = reads_for(
        "grain_perfect", replace(base_params, sigma_grain_azimuth=0.0, sigma_grain_strength=0.0), with_horizon=False
    )
    sweeps["grain"] = {
        "grain sensor as specified (20 deg, 30 %)": {"B1": baseline["B1"]},
        "grain sensor off (estimator assumes no grain)": run(base_reads, ("B1",), replace(est_config, use_grain=False))[0],
        "perfect grain sensor": run(perfect_grain, ("B1",), est_config)[0],
    }
    log(f"  sweeps: flag base, stimp, grain {time.perf_counter() - t0:.1f} s")

    # weight of the horizon residuals, realistic and optimistic silhouettes
    nf_reads = reads_for("no_fringe", base_params, fringe="no_fringe", with_horizon=True)
    md_reads = reads_for("mounded", base_params, fringe="mounded", with_horizon=True)
    hw: Dict[str, dict] = {"realistic": {}, "no_fringe": {}, "mounded": {}}
    for sigma_mrad in (0.3, 1.0, 3.0, 10.0):
        cfg = replace(est_config, sigma_horizon=sigma_mrad * 1e-3)
        for label, reads in (("realistic", base_reads), ("no_fringe", nf_reads), ("mounded", md_reads)):
            tables, out = run(reads, ("B2",), cfg)
            entry = {"B2": tables["B2"], "vs_B1": paired_delta(base_out["B1"], out["B2"])}
            entry["vs_B1"]["verdict"] = verdict(entry["vs_B1"])
            hw[label][f"{sigma_mrad:g}"] = entry
    hw["B1"] = baseline["B1"]
    sweeps["horizon_sigma_mrad"] = hw
    log(f"  sweeps: horizon weight {time.perf_counter() - t0:.1f} s")

    # Precision Read when the two seatings are not independent
    spin: Dict[str, dict] = {"0": {"B0S": baseline["B0S"], "B1": baseline["B1"]}}
    for rho in (0.5, 1.0):
        reads = reads_for(f"spin_{rho:g}", replace(base_params, seat_repeat_correlation=rho), with_horizon=False, spin=True)
        spin[f"{rho:g}"], _ = run(reads, ("B0S",), est_config)
    sweeps["spin_seat_correlation"] = spin

    # Survey with and without the model-error allowance on local samples
    survey_reads = reads_for("survey", base_params, with_horizon=False, survey=True)
    sweeps["survey_sigma_field_mrad"] = {
        f"{est_config.sigma_field * 1e3:g} (default)": run(survey_reads, ("SURVEY2", "SURVEY3"), est_config)[0],
        "0 (local samples trusted fully)": run(survey_reads, ("SURVEY2", "SURVEY3"), replace(est_config, sigma_field=0.0))[0],
    }

    # range with the first-hole stick-height prior
    first_hole = reads_for("first_hole", replace(base_params, stick_height_learned=False), with_horizon=False)
    sweeps["range_first_hole"] = _range_table(cases, first_hole, config, est_config)
    log(f"  sweeps: done {time.perf_counter() - t0:.1f} s")
    return sweeps


def run_all(config: MCConfig = MCConfig(), log: Callable[[str], None] = print) -> Dict[str, dict]:
    """Run the whole Monte Carlo and return the summary dictionary."""
    t_start = time.perf_counter()
    base_params = se.SensorParams()
    est_config = es.EstimatorConfig()
    log(f"building {config.n_seeds} greens per class x {len(config.distances)} distances ...")
    cases, skipped = build_cases(config)
    t_cases = time.perf_counter() - t_start
    log(f"  {len(cases)} putts ({skipped} skipped), {t_cases:.1f} s")
    main_result = run_main(cases, config, base_params, est_config, log)
    t_main = time.perf_counter() - t_start - t_cases
    sweep_cases = [c for c in cases if c.seed < config.n_seeds_sweep]
    log(f"sweeps on {len(sweep_cases)} putts ...")
    sweeps = run_sweeps(sweep_cases, config, base_params, est_config, log)
    t_total = time.perf_counter() - t_start
    cam = base_params.camera
    summary = {
        "meta": {
            "n_putts_main": len(cases),
            "n_putts_per_cell": config.n_seeds,
            "n_putts_sweep": len(sweep_cases),
            "n_skipped": skipped,
            "n_exec": config.n_exec,
            "distances": list(config.distances),
            "classes": list(config.classes),
            "seat_levels_mrad": [s * 1e3 for s in config.seat_levels],
            "nominal_seat_mrad": config.nominal_seat * 1e3,
            "sigma_dir_deg": math.degrees(config.sigma_dir),
            "sigma_speed": config.sigma_speed,
            "human_cross_errors": list(config.human_cross_errors),
            "master_seed": config.master_seed,
            "camera": {**asdict(cam), "half_fov_h_deg": math.degrees(cam.half_fov_h), "up_fov_deg": math.degrees(cam.up_fov)},
            "sensor_params": {k: v for k, v in asdict(base_params).items() if k != "camera"},
            "estimator_config": asdict(est_config),
            "default_method": es.DEFAULT_METHOD,
            "numba": ph.NUMBA_STATUS,
            "runtime_s": {"cases": t_cases, "main": t_main, "sweeps": t_total - t_main - t_cases, "total": t_total},
        },
        "main": main_result,
        "sweeps": sweeps,
    }
    return summary


def _json_default(obj):
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    raise TypeError(f"not JSON serialisable: {type(obj)}")


def _clean(obj):
    """Replace NaN / inf by None so that the output is strict JSON."""
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (float, np.floating)):
        return float(obj) if math.isfinite(obj) else None
    return obj


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--n-seeds", type=int, default=MCConfig.n_seeds, help="greens per class (putts per distance x class cell)")
    parser.add_argument("--n-seeds-sweep", type=int, default=MCConfig.n_seeds_sweep, help="greens per class in the sweeps")
    parser.add_argument("--n-exec", type=int, default=MCConfig.n_exec, help="human-execution samples per putt")
    parser.add_argument("--seed", type=int, default=MCConfig.master_seed, help="master seed")
    parser.add_argument("--out", default=None, help="output directory (default: sim/results)")
    parser.add_argument("--no-report", action="store_true", help="write summary.json only")
    parser.add_argument("--no-vectors", action="store_true", help="do not regenerate reference_vectors.json")
    args = parser.parse_args(argv)
    if args.n_seeds < 1 or args.n_seeds_sweep < 1 or args.n_exec < 20:
        parser.error("need n-seeds >= 1, n-seeds-sweep >= 1 and n-exec >= 20")
    config = MCConfig(
        n_seeds=args.n_seeds, n_seeds_sweep=min(args.n_seeds_sweep, args.n_seeds), n_exec=args.n_exec, master_seed=args.seed
    )
    out_dir = args.out or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
    os.makedirs(out_dir, exist_ok=True)
    summary = run_all(config)
    with open(os.path.join(out_dir, "summary.json"), "w") as fh:
        json.dump(_clean(summary), fh, indent=1, default=_json_default, allow_nan=False)
    print(f"wrote {os.path.join(out_dir, 'summary.json')}  (total {summary['meta']['runtime_s']['total']:.0f} s)")
    if not args.no_vectors:
        from . import refvectors

        refvectors.write_reference_vectors(out_dir)
        print(f"wrote {os.path.join(out_dir, 'reference_vectors.json')}")
    if not args.no_report:
        from . import report

        report.write_report(_clean(summary), out_dir)
        print(f"wrote {os.path.join(out_dir, 'REPORT.md')} and plots")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
