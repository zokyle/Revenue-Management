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
``B2``         B1 + turf-horizon residuals (anchored two-stage fit).
``B0S``        Precision Read: B1 with a 180-degree spin-and-reread.
``SURVEY2/3``  Survey: two / three drops along the line.
``FLAGOUT``    flag-out fallback: the golfer points the visor by hand and
               dials the distance; tilt-only.

References that use the truth (defined in this module, NOT in the estimator):

``ORACLE``        true surface, true speed, true grain.
``ORACLE_SLOPE``  true surface, but the entered speed and the device's grain
                  knowledge (none by default): isolates how much of the miss
                  is slope reading.
``HUMAN05/10``    a golfer who reads the path-average cross slope with
                  0.5 % / 1 % (1-sigma) error, knows the hole height and the
                  bearing exactly, and uses the same entered speed as the
                  device.  Grain knowledge: ``MCConfig.human_grain``.

Shipping configuration (the default of every table unless it says otherwise)
----------------------------------------------------------------------------
* The grain reading is NOT used (``EstimatorConfig.use_grain`` False): the
  design specification ships the grain sensor disabled.  The human baselines
  solve without grain as well (``MCConfig.human_grain = "none"``).
* The golfer follows the displayed aim LINE.  The line is drawn on a 1-bit
  128 x 128 display through a 22 mm aperture (122 px long), so its direction
  is quantised in steps of 2/122 rad = 0.94 deg, and transferring it to the
  start direction of the ball costs a further ``MCConfig.sigma_transfer``
  (0.5 deg 1 sigma: an ESTIMATE, swept).  Both apply to every device mode and
  to nothing else; ``STRAIGHT`` and the references aim without the display.

A camera read in which the flag is not found is retried as a flag-out read
(the golfer points the visor at the hole and dials the distance); every
device mode then works from that fallback read.

Everything is deterministic given ``MCConfig.master_seed``; the sensor noise,
the human reading noise, the aim-transfer error and the execution noise are
common random numbers across methods and across sweeps, so comparisons are
paired.
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
from scipy import stats as _stats

from . import estimator as es
from . import physics as ph
from . import sensors as se
from .greens import CLASS_PARAMS, GREEN_CLASSES, Green, PlacementError, PuttScenario, make_green, make_scenario
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
_STREAM_TRANSFER = 5

EXEC_LEVELS: Tuple[Tuple[float, float], ...] = ((1.0, 0.06), (1.5, 0.08), (2.0, 0.10), (2.5, 0.12))
"""Execution-noise levels of the sweep: (direction sigma [deg], relative speed
sigma).  The first is the specified default - about the level of an elite
putter; a typical amateur is nearer the third."""


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
    human_grain : ``"none"`` or ``"sensor"``
        Grain knowledge of the human baselines (and nothing else):
        ``"none"`` = they solve without grain, like the shipping device;
        ``"sensor"`` = they are handed the device's grain reading.
    sigma_transfer : float [rad]
        Aim-transfer error, device modes only: how well the golfer starts
        the ball along the line shown on the puck (reading a 22 mm line off
        the display and setting the ball / putter to it), 1 sigma, one draw
        per putt.  ESTIMATE, no data.  It is NOT the execution noise, which
        every method gets alike.
    display_line_px : float [px]
        Length of the aim line on the display (128 px over 23.04 mm seen
        through a 22 mm aperture: 122 px).  The 1-bit display can show line
        directions only in steps of ``2 / display_line_px`` rad (one pixel
        at the end of the line); 0 switches the quantisation off.
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
    human_grain: str = "none"
    sigma_transfer: float = math.radians(0.5)
    display_line_px: float = 122.0
    master_seed: int = 20261111

    @property
    def display_step(self) -> float:
        """Direction step of the displayed aim line [rad] (0 = not quantised)."""
        return 2.0 / self.display_line_px if self.display_line_px > 0.0 else 0.0


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
    local_cross : float [m/m];  local_along : float [m/m]
        True cross slope and true slope along the line at the ball.
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
    local_along: float = 0.0


def _wrap(angle):
    return np.arctan2(np.sin(angle), np.cos(angle))


def _stream(config: MCConfig, case: Case, purpose: int) -> np.random.Generator:
    """Independent, reproducible random stream for one purpose of one case."""
    key = [config.master_seed, case.cls_idx, int(round(case.distance * 1000.0)), case.seed, purpose]
    return np.random.default_rng(key)


def _make_case(sc: PuttScenario, cls_idx: int, seed: int, dist: float, n_samples: int = 17) -> Case:
    """Solve the oracle and collect the truth-derived facts of one putt.
    ``n_samples`` points along the line are used for the path averages."""
    green = sc.green
    sol = ph.solve_aim(green.surface, sc.ball_xy, sc.hole_xy, green.a_r, green.grain)
    bearing = sc.bearing
    pts = sc.point_at(np.linspace(0.0, 1.0, n_samples) * sc.distance)
    gx, gy = green.grad(pts[:, 0], pts[:, 1])
    cross = -np.asarray(gx) * math.sin(bearing) + np.asarray(gy) * math.cos(bearing)
    along = np.asarray(gx) * math.cos(bearing) + np.asarray(gy) * math.sin(bearing)
    return Case(
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
        local_along=float(along[0]),
    )


def build_cases(config: MCConfig, n_seeds: Optional[int] = None) -> Tuple[List[Case], int]:
    """Generate the putts: ``n_seeds`` greens per class, one putt per distance.

    Returns ``(cases, n_skipped)``; a (green, distance) pair for which no
    legal putt exists (:class:`~greenline_sim.greens.PlacementError`) is
    skipped and counted, never silently replaced.
    """
    n_seeds = config.n_seeds if n_seeds is None else n_seeds
    cases: List[Case] = []
    skipped = 0
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
                cases.append(_make_case(sc, cls_idx, seed, dist))
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
    was rolled instead.  ``transfer`` is True when the golfer takes the
    start direction from the line on the display: :func:`evaluate` then adds
    the aim-transfer error (``phi`` already includes the display
    quantisation).
    """

    phi: np.ndarray
    v0: np.ndarray
    estimates: Optional[List[es.Estimate]] = None
    n_unsolved: int = 0
    transfer: bool = False


def quantise_line(azimuth, step: float):
    """Direction the display can actually draw: ``azimuth`` [rad] rounded to
    a multiple of ``step`` [rad] (``step <= 0``: unchanged)."""
    if step <= 0.0:
        return azimuth
    return np.round(np.asarray(azimuth, dtype=float) / step) * step


def _launch_from(estimates: List[es.Estimate], truths: Sequence[se.MeasurementTruth], display_step: float = 0.0) -> Launch:
    """Turn device-frame aim lines into launch angles relative to the true line.

    ``STRAIGHT`` is the golfer aiming at the hole without the device: no
    display, no quantisation, no transfer error.
    """
    uses_display = bool(estimates) and estimates[0].method != "STRAIGHT"
    az = np.array([e.aim_azimuth_device for e in estimates])
    if uses_display:
        az = quantise_line(az, display_step)
    phi = np.array([_wrap(t.heading + a - t.bearing) for a, t in zip(az, truths)])
    v0 = np.array([e.v0 for e in estimates])
    unsolved = sum(1 for e in estimates if e.aim_source != es.AIM_FROM_PATCH and e.method != "STRAIGHT")
    return Launch(phi=phi, v0=v0, estimates=estimates, n_unsolved=unsolved, transfer=uses_display)


def device_launches(
    reads: Reads,
    methods: Sequence[str],
    est_config: es.EstimatorConfig = es.EstimatorConfig(),
    display_step: float = 0.0,
) -> Dict[str, Launch]:
    """Run the estimator for the requested device modes.

    ``methods`` may contain any of ``STRAIGHT, B0, B1, B2, B0S, SURVEY2,
    SURVEY3, FLAGOUT``.  The estimator receives the ``Measurements`` only;
    the truth records are used afterwards, to express the resulting aim line
    relative to the true ball->hole line.  ``display_step`` [rad] is the
    direction step of the displayed line (``MCConfig.display_step``).
    """
    out: Dict[str, Launch] = {}

    def launch(estimates, truths):  # every mode draws on the same display
        return _launch_from(estimates, truths, display_step)

    quick_meas = [m for m, _ in reads.quick]
    quick_truth = [t for _, t in reads.quick]
    for name in methods:
        if name in ("STRAIGHT", "B0", "B1", "B2"):
            out[name] = launch(es.estimate_batch(quick_meas, name, est_config), quick_truth)
        elif name == "B0S":
            if reads.spin is None:
                raise ValueError("B0S needs reads taken with spin=True")
            out[name] = launch(
                es.estimate_batch([m for m, _ in reads.spin], "B1", est_config), [t for _, t in reads.spin]
            )
        elif name in ("SURVEY2", "SURVEY3"):
            if reads.survey is None:
                raise ValueError(f"{name} needs reads taken with survey=True")
            n_drops = 2 if name == "SURVEY2" else 3
            items = [[m for m, _ in drops[:n_drops]] for drops in reads.survey]
            out[name] = launch(es.estimate_batch(items, "B1", est_config), [drops[0][1] for drops in reads.survey])
        elif name == "FLAGOUT":
            if reads.flag_out is None:
                raise ValueError("FLAGOUT needs reads taken with flag_out=True")
            out[name] = launch(
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
    The entered green speed is taken from the ``quick`` read.  Grain:
    ``ORACLE_SLOPE`` has exactly the device's grain knowledge (the measured
    grain if ``est_config.use_grain``, none otherwise); the human baselines
    follow ``config.human_grain`` (``"none"`` or ``"sensor"`` = the device's
    reading).  None of them uses the display, so no aim-transfer error.
    """
    if config.human_grain not in ("none", "sensor"):
        raise ValueError("MCConfig.human_grain must be 'none' or 'sensor'")
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
        grain_dev = grain_world if est_config.use_grain else np.zeros((n, 2))
        for i, case in enumerate(cases):
            sc = case.scenario
            sol = ph.solve_aim(sc.green.surface, sc.ball_xy, sc.hole_xy, entered_a_r[i], grain_dev[i], past)
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
        if config.human_grain == "none":
            grain_putt = np.zeros((n, 2))
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

    ``status`` (n,) and ``status_h`` (n, n_exec): :class:`RollStatus` of
    every roll.  A roll that was not holed and did not end ``STOPPED`` left
    the modelled surface (``OUT_OF_BOUNDS``) or was still moving at the time
    limit (``MAX_TIME``); these are counted by :func:`summarise`, never
    dropped.

    For device modes "perfect execution" means a perfect stroke along the
    line the golfer took from the display: it includes the display
    quantisation and the aim-transfer error.
    """

    lat: np.ndarray
    made: np.ndarray
    short: np.ndarray
    leave: np.ndarray
    made_h: np.ndarray
    lat_h: np.ndarray
    pace: np.ndarray
    status: np.ndarray
    status_h: np.ndarray


def evaluate(
    cases: Sequence[Case],
    launches: Dict[str, Launch],
    config: MCConfig,
    past: float = ph.DEFAULT_PAST,
    *,
    capture: Optional[ph.CaptureModel] = None,
    perfect_only: bool = False,
) -> Dict[str, Outcome]:
    """Roll every method's launch on the TRUE green (true speed, true grain).

    Per case one perfectly executed putt per method plus ``n_exec`` putts
    with human execution noise (direction ``sigma_dir``, speed
    ``sigma_speed``); the execution errors are the same for every method.
    Launches with ``transfer`` set (the device modes) additionally get the
    aim-transfer error ``config.sigma_transfer``: one draw per putt, the
    same for every device mode, applied to the perfectly executed putt and
    to the human-execution samples alike.

    ``past`` [m] is the target pace the pace error is measured against;
    ``capture`` replaces the default capture rule.  ``perfect_only`` rolls
    the perfectly executed putt only (20 times fewer rolls): the
    human-execution fields of the outcome are then NaN / empty, and so are
    the statistics derived from them.
    """
    names = list(launches)
    n = len(cases)
    n_m = len(names)
    n_e = 0 if perfect_only else config.n_exec
    per = 1 + n_e
    lat = np.zeros((n_m, n))
    made = np.zeros((n_m, n), dtype=bool)
    short = np.zeros((n_m, n), dtype=bool)
    leave = np.zeros((n_m, n))
    made_h = np.zeros((n_m, n))
    lat_h = np.zeros((n_m, n, n_e), dtype=np.float32)
    pace = np.zeros((n_m, n))
    status = np.zeros((n_m, n), dtype=np.int8)
    status_h = np.zeros((n_m, n, n_e), dtype=np.int8)
    phi_m = np.stack([launches[k].phi for k in names])  # (methods, cases)
    v0_m = np.stack([launches[k].v0 for k in names])
    uses_display = np.array([launches[k].transfer for k in names], dtype=float)
    if not (np.all(np.isfinite(phi_m)) and np.all(np.isfinite(v0_m)) and np.all(v0_m > 0.0)):
        raise ValueError("a method produced a non-finite or non-positive launch")
    for i, case in enumerate(cases):
        sc = case.scenario
        green = sc.green
        gen = _stream(config, case, _STREAM_EXECUTION)
        d_phi = np.concatenate([[0.0], config.sigma_dir * gen.standard_normal(n_e)])
        f_v = np.concatenate([[1.0], np.maximum(1.0 + config.sigma_speed * gen.standard_normal(n_e), 0.2)])
        transfer = config.sigma_transfer * float(_stream(config, case, _STREAM_TRANSFER).standard_normal())
        phi_case = phi_m[:, i] + uses_display * transfer
        phi_all = (phi_case[:, None] + d_phi[None, :]).ravel()
        v_all = (v0_m[:, i][:, None] * f_v[None, :]).ravel()
        res = ph.roll_batch(green.surface, sc.ball_xy, sc.hole_xy, phi_all, v_all, green.a_r, green.grain, capture=capture)
        cap = res.captured.reshape(n_m, per)
        lm = res.lateral_miss.reshape(n_m, per)
        st = res.status.reshape(n_m, per)
        made[:, i] = cap[:, 0]
        lat[:, i] = lm[:, 0]
        crossed = res.crossed_hole_line.reshape(n_m, per)[:, 0]
        short[:, i] = ~crossed
        leave[:, i] = res.final_distance.reshape(n_m, per)[:, 0]
        v_line = np.where(crossed, res.speed_at_line.reshape(n_m, per)[:, 0], 0.0)
        beyond = np.where(crossed, v_line * v_line / (2.0 * green.a_r), -res.shortfall.reshape(n_m, per)[:, 0])
        pace[:, i] = beyond - past
        if n_e:
            made_h[:, i] = cap[:, 1:].mean(axis=1)
            lat_h[:, i, :] = lm[:, 1:]
        # a holed ball's free roll beyond the hole is of no interest: record it as STOPPED
        st = np.where(cap, int(ph.RollStatus.STOPPED), st)
        status[:, i] = st[:, 0]
        status_h[:, i, :] = st[:, 1:]
    if not n_e:
        made_h[:] = np.nan
    return {
        name: Outcome(
            lat=lat[k], made=made[k], short=short[k], leave=leave[k], made_h=made_h[k], lat_h=lat_h[k], pace=pace[k],
            status=status[k], status_h=status_h[k],
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
    error of the perfectly executed putt [m] (see :class:`Outcome`);
    ``within_hole``: fraction of perfectly executed putts whose line passes
    within the hole radius of its centre; ``not_at_rest`` /
    ``not_at_rest_human``: fraction of rolls (perfect / human execution)
    that were not holed and did not come to rest on the modelled surface.
    """
    if mask is None:
        mask = np.ones(outcome.lat.shape[0], dtype=bool)
    n = int(mask.sum())
    if n == 0:
        return {"n": 0}
    a = np.abs(outcome.lat[mask])
    has_human = outcome.lat_h.shape[1] > 0
    return {
        "n": n,
        "median_miss": float(np.median(a)),
        "p90_miss": float(np.percentile(a, 90.0)),
        "make_perfect": float(np.mean(outcome.made[mask])),
        "make_human": float(np.mean(outcome.made_h[mask])),
        "short": float(np.mean(outcome.short[mask])),
        "median_leave": float(np.median(outcome.leave[mask])),
        "median_miss_human": float(np.median(np.abs(outcome.lat_h[mask]))) if has_human else math.nan,
        "median_pace_err": float(np.median(np.abs(outcome.pace[mask]))),
        "mean_pace_err": float(np.mean(np.clip(outcome.pace[mask], -3.0, 3.0))),
        "within_hole": float(np.mean(a < ph.HOLE_R)),
        "not_at_rest": float(np.mean(outcome.status[mask] != int(ph.RollStatus.STOPPED))),
        "not_at_rest_human": float(np.mean(outcome.status_h[mask] != int(ph.RollStatus.STOPPED))) if has_human else math.nan,
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
    standard error; ``d_make_human``: the same with human execution (per
    putt, the fraction of the execution samples holed); ``d_mean_miss``: difference in mean absolute lateral
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
    dh = b.made_h[mask] - a.made_h[mask]
    la = np.minimum(np.abs(a.lat[mask]), 1.0)
    lb = np.minimum(np.abs(b.lat[mask]), 1.0)
    dl = lb - la
    differ = np.abs(dl) > 1e-9
    return {
        "n": n,
        "d_make": float(dm.mean()),
        "d_make_se": float(dm.std(ddof=1) / math.sqrt(n)),
        "d_make_human": float(dh.mean()),
        "d_make_human_se": float(dh.std(ddof=1) / math.sqrt(n)),
        "make_a": float(a.made[mask].mean()),
        "make_b": float(b.made[mask].mean()),
        "d_mean_miss": float(dl.mean()),
        "d_mean_miss_se": float(dl.std(ddof=1) / math.sqrt(n)),
        "median_miss_a": float(np.median(np.abs(a.lat[mask]))),
        "median_miss_b": float(np.median(np.abs(b.lat[mask]))),
        "b_closer": float(np.mean(dl[differ] < 0.0)) if differ.any() else 0.5,
        "n_differ": int(differ.sum()),
    }


def verdict(delta: Dict[str, float]) -> str:
    """Plain-words verdict for a :func:`paired_delta` (``b`` relative to
    ``a``), judged at 2 standard errors on the make probability and on the
    mean clipped miss:

    * ``"helps"`` / ``"hurts"``: both measures move that way;
    * ``"reduces the mean miss, makes unchanged"`` (and its three siblings):
      only one of the two measures moves;
    * ``"mixed (make probability and mean miss disagree)"``;
    * ``"no measurable effect"``.
    """
    if delta.get("n", 0) < 2:
        return "not enough cases"
    z_make = delta["d_make"] / delta["d_make_se"] if delta["d_make_se"] > 0.0 else 0.0
    z_miss = delta["d_mean_miss"] / delta["d_mean_miss_se"] if delta["d_mean_miss_se"] > 0.0 else 0.0
    make = 1 if z_make > 2.0 else (-1 if z_make < -2.0 else 0)
    miss = 1 if z_miss < -2.0 else (-1 if z_miss > 2.0 else 0)  # +1 = better
    if make * miss < 0:
        return "mixed (make probability and mean miss disagree)"
    if make > 0 and miss > 0:
        return "helps"
    if make < 0 and miss < 0:
        return "hurts"
    if miss > 0:
        return "reduces the mean miss, makes unchanged"
    if miss < 0:
        return "increases the mean miss, makes unchanged"
    if make > 0:
        return "raises the make probability, mean miss unchanged"
    if make < 0:
        return "lowers the make probability, mean miss unchanged"
    return "no measurable effect"


def verdict_sign(text: str) -> int:
    """+1 if a :func:`verdict` reports any gain and no loss, -1 for the
    mirror image, 0 otherwise."""
    if text in ("helps", "reduces the mean miss, makes unchanged", "raises the make probability, mean miss unchanged"):
        return 1
    if text in ("hurts", "increases the mean miss, makes unchanged", "lowers the make probability, mean miss unchanged"):
        return -1
    return 0


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
    if region is not None:
        # samples whose silhouette sits where the ray leaves the modelled terrain
        at_edge = np.concatenate([t.horizon.at_boundary for _, t in reads.first])
        rough = np.concatenate([t.horizon.region == 2 for _, t in reads.first])
        out["horizon_at_model_boundary"] = float(np.mean(at_edge))
        out["horizon_rough_at_model_boundary"] = float(np.mean(at_edge[rough])) if rough.any() else math.nan
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
    along-line slope ``a + 0.5 c D``, against the truth; ``along_at_ball`` /
    ``cross_at_ball``: RMS error of the FITTED patch slopes ``a``, ``b``
    against the true slope at the ball (this is where a fit that lets the
    horizon overrule the tilt shows up); ``slope_pct``: RMS error of the
    displayed slope at the ball [% slope].
    """
    dist = np.array([c.distance for c in cases])
    mean_cross = np.array([c.mean_cross for c in cases])
    local_cross = np.array([c.local_cross for c in cases])
    mean_along = np.array([c.mean_along for c in cases])
    local_along = np.array([c.local_along for c in cases])
    slope_true = 100.0 * np.hypot(local_along, local_cross)
    hidden = np.array([not t.base_visible for _, t in reads.first])
    out: Dict[str, dict] = {}
    for d in list(config.distances) + ["all"]:
        sel = dist == d if d != "all" else np.ones(len(cases), dtype=bool)
        row = {
            "representativeness": _rms(local_cross[sel] - mean_cross[sel]),
            "mean_cross_rms": _rms(mean_cross[sel]),
            "cross": {},
            "along": {},
            "along_base_visible": {},
            "along_base_hidden": {},
            "along_at_ball": {},
            "cross_at_ball": {},
            "slope_pct": {},
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
            row["along_at_ball"][name] = _rms(np.array([e.patch[0] for e in est])[ok] - local_along[ok])
            row["cross_at_ball"][name] = _rms(np.array([e.patch[1] for e in est])[ok] - local_cross[ok])
            row["slope_pct"][name] = _rms(np.array([e.slope_pct for e in est])[ok] - slope_true[ok])
        out[d if d == "all" else f"{d:g}"] = row
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


def _spearman(a, b) -> float:
    """Spearman rank correlation (NaN if either input is constant)."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if a.size < 3 or np.all(a == a[0]) or np.all(b == b[0]):
        return math.nan
    return float(np.corrcoef(_stats.rankdata(a), _stats.rankdata(b))[0, 1])


def _confidence_table(
    cases: Sequence[Case], launches: Dict[str, Launch], outcomes: Dict[str, Outcome], reads: Reads,
    config: MCConfig, methods: Sequence[str],
) -> Dict[str, dict]:
    """How informative and how well calibrated the confidence score is.

    Per method: ``mean_confidence`` against ``within_hole`` (fraction of
    perfectly executed putts passing within the hole radius);
    ``spearman_pooled``: rank correlation of the score with the absolute
    lateral miss over all putts (dominated by putt length);
    ``spearman_within_length``: the same computed inside each putt length
    and averaged - what the score knows beyond the length;
    ``spearman_minus_distance``: rank correlation of MINUS THE DISTANCE with
    the miss, the yardstick a score has to beat; ``z_rms``: RMS of (error of
    the estimated mean cross slope) / (its claimed sigma) on camera reads -
    1 means the sigma is right, above 1 overconfident; ``bins``: see
    :func:`_calibration`.
    """
    dist = np.array([c.distance for c in cases])
    mean_cross = np.array([c.mean_cross for c in cases])
    out: Dict[str, dict] = {}
    for name in methods:
        est = launches[name].estimates
        conf = np.array([e.confidence for e in est])
        miss = np.abs(outcomes[name].lat)
        within = [
            _spearman(conf[dist == d], miss[dist == d]) for d in config.distances
        ]
        within = [w for w in within if math.isfinite(w)]
        cross = np.array([e.patch[1] + 0.5 * e.patch[3] * e.distance for e in est])
        sigma = np.array([e.cross_slope_sigma for e in est])
        ok = reads.found & np.isfinite(sigma) & (sigma > 0.0)
        out[name] = {
            "mean_confidence": float(conf.mean()),
            "within_hole": float(np.mean(miss < ph.HOLE_R)),
            "spearman_pooled": _spearman(conf, miss),
            "spearman_within_length": float(np.mean(within)) if within else math.nan,
            "spearman_minus_distance": _spearman(-dist, miss),
            "z_rms": _rms((cross[ok] - mean_cross[ok]) / sigma[ok]),
            "by_distance": {
                f"{d:g}": {"mean_confidence": float(conf[dist == d].mean()), "within_hole": float(np.mean(miss[dist == d] < ph.HOLE_R))}
                for d in config.distances
            },
            "bins": _calibration(launches[name], outcomes[name]),
        }
    return out


def _roll_status(outcomes: Dict[str, Outcome]) -> Dict[str, dict]:
    """Rolls that were not holed and did not come to rest on the modelled
    surface, per method: counts for the perfectly executed putts and for the
    human-execution samples.  Nothing is dropped from any statistic; this is
    the count of rolls whose rest position is not a physical one."""
    out = {}
    for name, o in outcomes.items():
        out[name] = {
            "max_time": int(np.sum(o.status == int(ph.RollStatus.MAX_TIME))),
            "out_of_bounds": int(np.sum(o.status == int(ph.RollStatus.OUT_OF_BOUNDS))),
            "n": int(o.status.size),
            "max_time_human": int(np.sum(o.status_h == int(ph.RollStatus.MAX_TIME))),
            "out_of_bounds_human": int(np.sum(o.status_h == int(ph.RollStatus.OUT_OF_BOUNDS))),
            "n_human": int(o.status_h.size),
        }
    return out


def cups_launch(launch: Launch) -> Launch:
    """The same reads under the "break in cups" use model: the golfer takes
    the displayed break (the aim offset relative to the hole) and aims by
    eye relative to the hole he can see, instead of following the line on
    the puck.  The aim is then the estimator's ``phi`` relative to the TRUE
    line: no display quantisation, no aim-transfer error and no bearing
    error (hand-pointed or measured)."""
    if launch.estimates is None:
        raise ValueError("cups_launch needs a device launch")
    return Launch(
        phi=np.array([e.phi for e in launch.estimates]), v0=launch.v0.copy(), estimates=launch.estimates,
        n_unsolved=launch.n_unsolved, transfer=False,
    )


def _crossing(levels: Sequence[float], values: Sequence[float], target: float) -> Optional[float]:
    """Level at which ``values`` (piecewise linear in ``levels``) falls to
    ``target``; None if it never does inside the range."""
    for (x0, y0), (x1, y1) in zip(zip(levels[:-1], values[:-1]), zip(levels[1:], values[1:])):
        if (y0 - target) * (y1 - target) <= 0.0 and y0 != y1:
            return float(x0 + (x1 - x0) * (y0 - target) / (y0 - y1))
    return None


def breakeven_band(levels: Sequence[float], deltas: Sequence[dict], key: str = "d_make") -> Dict[str, Optional[float]]:
    """Where a paired difference that falls with the level crosses zero.

    ``deltas[i]`` is the :func:`paired_delta` at ``levels[i]``.  Returns
    ``mid`` (the difference itself is zero), ``lo`` (its lower 95 % bound is
    zero) and ``hi`` (its upper 95 % bound is zero), each by linear
    interpolation between the levels and ``None`` where there is no crossing
    inside the range.  ``lo`` .. ``hi`` is the band of levels at which the
    two methods cannot be told apart.
    """
    d = [x[key] for x in deltas]
    se = [1.96 * x[key + "_se"] for x in deltas]
    return {
        "mid": _crossing(levels, d, 0.0),
        "lo": _crossing(levels, [a - b for a, b in zip(d, se)], 0.0),
        "hi": _crossing(levels, [a + b for a, b in zip(d, se)], 0.0),
        "first_level": float(levels[0]),
        "last_level": float(levels[-1]),
        "ahead_at_first": bool(d[0] - se[0] > 0.0),
        "behind_at_last": bool(d[-1] + se[-1] < 0.0),
    }


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


_FRINGE_TAGS = (("realistic", ""), ("no_surround", "_NOSURROUND"), ("no_fringe", "_NOFRINGE"), ("mounded", "_MOUNDED"))
HORIZON_FITS = (("anchored", "B2"), ("anchored_free_c", "B2C"), ("joint", "B2J"), ("joint_single_start", "B2L"))
"""Forms of the horizon fit compared in the horizon test: summary label and
method tag.  ``B2`` is the estimator's default (anchored)."""
GRAIN_METHODS = ("B1", "B0S", "SURVEY3")
CUPS_METHODS = ("B1", "B0S", "SURVEY3", "FLAGOUT")


def _pairs(outcomes: Dict[str, Outcome], pairs: Sequence[Tuple[str, str]], mask: Optional[np.ndarray] = None) -> Dict[str, dict]:
    """``{"X_vs_Y": paired_delta(Y -> X)}`` (X minus Y) for the given pairs."""
    return {f"{x}_vs_{y}": paired_delta(outcomes[y], outcomes[x], mask) for x, y in pairs if x in outcomes and y in outcomes}


def _horizon_fit_stats(launch: Launch) -> Dict[str, float]:
    """Diagnostics of the horizon fits behind a ``B2`` launch."""
    fits = [e.fit for e in launch.estimates if e.fit is not None and e.fit.used_horizon]
    if not fits:
        return {"n": 0}
    lower = [f.cost < f.cost_first_start - 1e-6 * (1.0 + f.cost_first_start) for f in fits]
    return {
        "n": len(fits),
        "first_start_not_lowest": float(np.mean(lower)),
        "poor_horizon": float(np.mean([f.poor_horizon for f in fits])),
        "mean_starts": float(np.mean([f.n_starts for f in fits])),
    }


def run_main(
    cases: Sequence[Case],
    config: MCConfig,
    base_params: se.SensorParams = se.SensorParams(),
    est_config: es.EstimatorConfig = es.EstimatorConfig(),
    log: Callable[[str], None] = print,
) -> Dict[str, dict]:
    """Main experiment: every method at every seating-noise level, plus - at
    the nominal level - the horizon test, the grain-on and "break in cups"
    variants and the diagnostics."""
    result: Dict[str, dict] = {"by_seat": {}, "paired_by_seat": {}, "methods": list(DEVICE_METHODS + REFERENCE_METHODS)}
    step = config.display_step
    human_pairs = [(m, h) for m in ("B1", "B0S", "SURVEY2", "SURVEY3", "B2") for h in ("HUMAN05", "HUMAN10")]
    # STRAIGHT and the references do not use the tilt: their launches are the
    # same at every seating level (same noise draws), so they are rolled once
    tilt_free = ("STRAIGHT",) + REFERENCE_METHODS
    tilt_free_out: Dict[str, Outcome] = {}
    for seat in config.seat_levels:
        t0 = time.perf_counter()
        params = replace(base_params, sigma_seat=seat)
        reads = take_reads(cases, params, config, with_horizon=True, spin=True, survey=True, flag_out=True)
        launches = device_launches(reads, DEVICE_METHODS, est_config, step)
        launches.update(reference_launches(cases, reads, config, REFERENCE_METHODS, est_config))
        if tilt_free_out:
            first_launch = tilt_free_launch
            if not all(np.array_equal(launches[k].phi, first_launch[k].phi) and np.array_equal(launches[k].v0, first_launch[k].v0)
                       for k in tilt_free):
                raise RuntimeError("a tilt-free method changed with the seating noise")
        else:
            tilt_free_launch = {k: launches[k] for k in tilt_free}
        nominal = abs(seat - config.nominal_seat) < 1e-12
        horizon_fits: Dict[str, dict] = {}
        if nominal:
            # horizon test: the anchored fit (B2), the anchored fit with c
            # left free (B2C), the joint fit with its 25 starts (B2J) and the
            # joint fit from a single start (B2L), on four versions of what
            # lies behind the green
            free_c = replace(est_config, horizon_free_c=True)
            joint = replace(est_config, horizon_joint=True)
            local = replace(joint, multi_start=False)
            for fringe, tag in _FRINGE_TAGS:
                alt = reads if fringe == "realistic" else take_reads(cases, params, config, fringe=fringe, with_horizon=True)
                if tag:
                    launches["B2" + tag] = device_launches(alt, ["B2"], est_config, step)["B2"]
                launches["B2C" + tag] = device_launches(alt, ["B2"], free_c, step)["B2"]
                launches["B2J" + tag] = device_launches(alt, ["B2"], joint, step)["B2"]
                launches["B2L" + tag] = device_launches(alt, ["B2"], local, step)["B2"]
                horizon_fits[fringe] = {
                    "anchored": _horizon_fit_stats(launches["B2" + tag]),
                    "anchored_free_c": _horizon_fit_stats(launches["B2C" + tag]),
                    "joint": _horizon_fit_stats(launches["B2J" + tag]),
                }
            # the grain sensor switched on (it ships disabled)
            grain_cfg = replace(est_config, use_grain=True)
            for name, launch in device_launches(reads, GRAIN_METHODS, grain_cfg, step).items():
                launches[name + "_GRAIN"] = launch
            ref_grain = reference_launches(
                cases, reads, replace(config, human_grain="sensor"), ("HUMAN05", "HUMAN10", "ORACLE_SLOPE"), grain_cfg
            )
            for name, launch in ref_grain.items():
                launches[name + "_GRAIN"] = launch
            # the other use model: break in cups relative to the hole
            for name in CUPS_METHODS:
                launches[name + "_CUPS"] = cups_launch(launches[name])
        # the forms of the horizon fit are compared on the perfectly executed putt only
        variant = {n: l for n, l in launches.items() if n.startswith(("B2C", "B2J", "B2L", "B2_"))}
        todo = {n: l for n, l in launches.items() if n not in variant and n not in tilt_free_out}
        outcomes = evaluate(cases, todo, config)
        if not tilt_free_out:
            tilt_free_out = {k: outcomes[k] for k in tilt_free}
        outcomes.update(tilt_free_out)
        outcomes = {n: outcomes[n] for n in launches if n in outcomes}  # keep the order of the methods
        if variant:
            outcomes.update(evaluate(cases, variant, config, perfect_only=True))
        key = f"{seat * 1e3:g}"
        result["by_seat"][key] = {name: _tables(cases, outcomes[name], config) for name in outcomes}
        result["paired_by_seat"][key] = _pairs(outcomes, human_pairs)
        if nominal:
            cls = np.array([c.cls_idx for c in cases])
            horizon = {}
            for fringe, tag in _FRINGE_TAGS:
                block = {}
                for label, name in HORIZON_FITS:
                    entry = {"all": paired_delta(outcomes["B1"], outcomes[name + tag])}
                    entry["all"]["verdict"] = verdict(entry["all"])
                    for cname in config.classes:
                        sel = cls == GREEN_CLASSES.index(cname)
                        entry[cname] = paired_delta(outcomes["B1"], outcomes[name + tag], sel)
                        entry[cname]["verdict"] = verdict(entry[cname])
                    block[label] = entry
                block["fits"] = horizon_fits[fringe]
                horizon[fringe] = block
            result["horizon_test"] = horizon
            strong = np.array([c.scenario.green.grain.kappa >= 0.05 for c in cases])
            est_names = [n for n in ("B0", "B1", "B2", "B2C", "B2J", "B2L", "B0S", "SURVEY2", "SURVEY3", "FLAGOUT") if n in launches]
            result["diagnostics"] = {
                "range": _range_table(cases, reads, config, est_config),
                "flag": _flag_table(cases, reads, config),
                "slope_error": _slope_error_table(cases, {n: launches[n] for n in est_names}, reads, config),
                "confidence": _confidence_table(
                    cases, launches, outcomes, reads, config, ("B1", "B2", "B0S", "SURVEY2", "SURVEY3", "FLAGOUT")
                ),
                "aim_sources": _aim_sources({n: launches[n] for n in est_names}),
                "unsolved": {name: int(launch.n_unsolved) for name, launch in launches.items()},
                "roll_status": _roll_status(outcomes),
                "subsets": _subset_tables(
                    cases, outcomes, reads, ("STRAIGHT", "B0", "B1", "B2", "B0S", "SURVEY3", "HUMAN05", "HUMAN10", "ORACLE")
                ),
                "double_break_fraction": {
                    f"{d:g}": float(np.mean([c.double_break for c in cases if c.distance == d])) for d in config.distances
                },
                "oracle_not_solved": int(sum(not c.oracle_ok for c in cases)),
                "strong_grain": {
                    "fraction_of_putts": float(np.mean(strong)),
                    **{n: summarise(outcomes[n], strong) for n in ("B1", "B1_GRAIN", "HUMAN05", "HUMAN05_GRAIN", "ORACLE")},
                },
                "paired": _pairs(
                    outcomes,
                    [
                        ("B0", "STRAIGHT"), ("B1", "B0"), ("B2", "B1"), ("ORACLE", "B2"), ("ORACLE", "B1"),
                        ("B0S", "B1"), ("SURVEY2", "B1"), ("SURVEY3", "B1"), ("B0", "FLAGOUT"),
                        ("B1", "HUMAN05"), ("B1", "HUMAN10"), ("B0S", "HUMAN05"), ("B0S", "HUMAN10"),
                        ("SURVEY3", "HUMAN05"), ("SURVEY3", "HUMAN10"),
                        ("B1_GRAIN", "B1"), ("B0S_GRAIN", "B0S"), ("SURVEY3_GRAIN", "SURVEY3"),
                        ("HUMAN05_GRAIN", "HUMAN05"), ("B1_GRAIN", "HUMAN05_GRAIN"), ("B1_GRAIN", "HUMAN05"),
                        ("B1_CUPS", "B1"), ("B1_CUPS", "HUMAN05"), ("B0S_CUPS", "HUMAN05"), ("SURVEY3_CUPS", "HUMAN05"),
                        ("FLAGOUT_CUPS", "FLAGOUT"), ("B1_CUPS", "FLAGOUT_CUPS"),
                    ],
                ),
            }
        log(f"  main, seating {key} mrad: {time.perf_counter() - t0:.1f} s")
    seats = [s * 1e3 for s in config.seat_levels]
    result["seating_breakeven_mrad"] = {
        f"{m}_vs_{h}": {
            key: breakeven_band(seats, [result["paired_by_seat"][f"{s:g}"][f"{m}_vs_{h}"] for s in seats], key)
            for key in ("d_make", "d_make_human")
        }
        for m, h in human_pairs
    }
    return result


def _twin_cases(cases: Sequence[Case], make_twin: Callable[[Case], Green], n_samples: int = 17) -> List[Case]:
    """The same putts (ball, hole, random streams) on twin greens.  One twin
    per (class, seed); every truth-derived fact of the case is recomputed."""
    cache: Dict[Tuple[int, int], Green] = {}
    out = []
    for case in cases:
        key = (case.cls_idx, case.seed)
        if key not in cache:
            cache[key] = make_twin(case)
        out.append(_make_case(replace(case.scenario, green=cache[key]), case.cls_idx, case.seed, case.distance, n_samples))
    return out


def run_sweeps(
    cases: Sequence[Case],
    config: MCConfig,
    base_params: se.SensorParams = se.SensorParams(),
    est_config: es.EstimatorConfig = es.EstimatorConfig(),
    log: Callable[[str], None] = print,
) -> Dict[str, dict]:
    """Sensitivity sweeps on the sweep subset of cases (nominal seating noise).

    Every entry maps a variant label to ``{method: tables}`` (see
    :func:`_tables`), sometimes with paired comparisons next to it.  The
    label ``"baseline"`` is the default configuration on the same cases, so
    every variant can be compared like for like.
    """
    t0 = time.perf_counter()
    step = config.display_step
    read_cache: Dict[str, Reads] = {}

    def reads_for(key: str, params: se.SensorParams, **kwargs) -> Reads:
        if key not in read_cache:
            read_cache[key] = take_reads(cases, params, config, **kwargs)
        return read_cache[key]

    def launch(reads: Reads, methods: Sequence[str], cfg: es.EstimatorConfig, mc: MCConfig = config,
               on: Sequence[Case] = cases, quantise: bool = True) -> Dict[str, Launch]:
        dev = [m for m in methods if m in DEVICE_METHODS]
        ref = [m for m in methods if m in REFERENCE_METHODS]
        out = device_launches(reads, dev, cfg, mc.display_step if quantise else 0.0)
        if ref:
            out.update(reference_launches(on, reads, mc, ref, cfg))
        return out

    def tables(outcomes: Dict[str, Outcome], on: Sequence[Case] = cases, rename: Optional[Dict[str, str]] = None):
        return {(rename or {}).get(name, name): _tables(on, outcomes[name], config) for name in outcomes}

    def run(reads: Reads, methods: Sequence[str], cfg: es.EstimatorConfig, mc: MCConfig = config,
            on: Sequence[Case] = cases, **kwargs):
        outcomes = evaluate(on, launch(reads, methods, cfg, mc, on), mc, **kwargs)
        return tables(outcomes, on), outcomes

    def quick(reads: Reads, methods: Sequence[str], cfg: es.EstimatorConfig, mc: MCConfig = config,
              on: Sequence[Case] = cases):
        """As ``run`` but with the perfectly executed putt only."""
        return run(reads, methods, cfg, mc, on, perfect_only=True)

    sweeps: Dict[str, dict] = {}
    base_methods = ("STRAIGHT", "B0", "B1", "B2", "B0S", "SURVEY2", "SURVEY3", "HUMAN05", "HUMAN10", "ORACLE_SLOPE", "ORACLE")
    base_reads = reads_for("base", base_params, with_horizon=True, spin=True, survey=True)
    base_launch = launch(base_reads, base_methods, est_config)
    base_out = evaluate(cases, base_launch, config)
    baseline = tables(base_out)
    sweeps["baseline"] = baseline
    log(f"  sweeps: baseline {time.perf_counter() - t0:.1f} s")

    # ---- camera preset ---------------------------------------------------------
    cam: Dict[str, dict] = {"GL1": {"B1": baseline["B1"]}}
    cam_range: Dict[str, dict] = {"GL1": _range_table(cases, base_reads, config, est_config)}
    cam_found: Dict[str, float] = {"GL1": float(np.mean(base_reads.found))}
    for name in ("QVGA", "VGA", "2MP"):
        params = replace(base_params, camera=se.CAMERA_PRESETS[name])
        reads = reads_for(f"cam_{name}", params, with_horizon=False)
        cam[name], _ = quick(reads, ("B1",), est_config)
        cam_range[name] = _range_table(cases, reads, config, est_config)
        cam_found[name] = float(np.mean(reads.found))
    sweeps["camera"] = cam
    sweeps["camera_range"] = cam_range
    sweeps["camera_found"] = cam_found
    log(f"  sweeps: camera presets {time.perf_counter() - t0:.1f} s")

    # ---- lens height -----------------------------------------------------------
    height: Dict[str, dict] = {}
    for h_mm in (3.0, 4.5, 6.0):
        params = replace(base_params, camera=replace(base_params.camera, h_cam=h_mm * 1e-3))
        reads = reads_for(f"h_{h_mm:g}", params, with_horizon=False)
        height[f"{h_mm:g}"], _ = quick(reads, ("B1",), est_config)
        height[f"{h_mm:g}"]["base_hidden"] = float(np.mean([not t.base_visible for _, t in reads.first]))
    height["5.6 (GL1)"] = {"B1": baseline["B1"]}
    height["5.6 (GL1)"]["base_hidden"] = float(np.mean([not t.base_visible for _, t in base_reads.first]))
    sweeps["h_cam_mm"] = height
    log(f"  sweeps: lens height {time.perf_counter() - t0:.1f} s")

    # ---- flag base on / off, and a device that cannot tell a hidden base ----------
    no_base, no_base_out = quick(base_reads, ("B1", "B2"), replace(est_config, use_flag_base=False))
    blind, blind_out = quick(base_reads, ("B1",), replace(est_config, assume_base_visible=True))
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

    # ---- entered green speed -----------------------------------------------------
    stimp: Dict[str, dict] = {}
    for err in (0.0, 0.07, 0.15):
        if abs(err - base_params.sigma_stimp) < 1e-12:
            stimp[f"{err * 100:g}"] = {k: baseline[k] for k in ("B1", "ORACLE_SLOPE")}
            continue
        reads = reads_for(f"stimp_{err:g}", replace(base_params, sigma_stimp=err), with_horizon=False)
        stimp[f"{err * 100:g}"], _ = quick(reads, ("B1", "ORACLE_SLOPE"), est_config)
    sweeps["stimp_error_pct"] = stimp
    log(f"  sweeps: flag base, stimp {time.perf_counter() - t0:.1f} s")

    # ---- grain sensor (ships disabled) -----------------------------------------
    grain_cfg = replace(est_config, use_grain=True)
    grain_mc = replace(config, human_grain="sensor")
    grain_methods = ("B1", "B0S", "SURVEY3", "HUMAN05", "HUMAN10")
    on_tab, on_out = run(base_reads, grain_methods, grain_cfg, grain_mc)
    grain: Dict[str, dict] = {
        "sensor off (shipping default)": {k: baseline[k] for k in grain_methods},
        "sensor as specified (20 deg, 30 %)": on_tab,
    }
    defects = {
        "perfect sensor": dict(sigma_grain_azimuth=0.0, sigma_grain_strength=0.0),
        "additive floor 0.02 per axis": dict(grain_noise_floor=0.02),
        "additive floor 0.04 per axis": dict(grain_noise_floor=0.04),
        "direction sigma 60 deg": dict(sigma_grain_azimuth=math.radians(60.0)),
        "180-deg ambiguity wrong 25 %": dict(p_grain_flip=0.25),
        "180-deg ambiguity wrong 50 %": dict(p_grain_flip=0.50),
        "strength error 100 %": dict(sigma_grain_strength=1.0),
    }
    grain_paired = {"sensor as specified (20 deg, 30 %)": paired_delta(base_out["B1"], on_out["B1"])}
    strong = np.array([c.scenario.green.grain.kappa >= 0.05 for c in cases])
    grain_strong = {
        "fraction_of_putts": float(np.mean(strong)),
        "sensor off (shipping default)": summarise(base_out["B1"], strong),
        "sensor as specified (20 deg, 30 %)": summarise(on_out["B1"], strong),
    }
    for label, changes in defects.items():
        reads = reads_for(f"grain_{label}", replace(base_params, **changes), with_horizon=False)
        tab, out = quick(reads, ("B1",), grain_cfg)
        grain[label] = tab
        grain_paired[label] = paired_delta(base_out["B1"], out["B1"])
        grain_strong[label] = summarise(out["B1"], strong)
    sweeps["grain"] = grain
    sweeps["grain_vs_off"] = grain_paired
    sweeps["grain_strong_greens"] = grain_strong
    sweeps["grain_vs_human"] = {
        "sensor off; humans without grain": paired_delta(base_out["HUMAN05"], base_out["B1"]),
        "sensor off; humans with the sensor's grain reading": paired_delta(on_out["HUMAN05"], base_out["B1"]),
        "sensor on; humans with the sensor's grain reading": paired_delta(on_out["HUMAN05"], on_out["B1"]),
    }
    log(f"  sweeps: grain {time.perf_counter() - t0:.1f} s")

    # ---- aim transfer (reading the line off the puck) ----------------------------
    tr_dev = ("B1", "B0S", "SURVEY3")
    tr_methods = tr_dev + ("HUMAN05", "HUMAN10")
    humans = {k: base_out[k] for k in ("HUMAN05", "HUMAN10")}  # they do not use the display
    transfer: Dict[str, dict] = {}
    transfer_pairs: Dict[str, dict] = {}
    for deg in (0.0, 0.5, 1.0, 1.5):
        mc = replace(config, sigma_transfer=math.radians(deg))
        if abs(mc.sigma_transfer - config.sigma_transfer) < 1e-15:
            out = base_out
        else:
            out = {**evaluate(cases, {k: base_launch[k] for k in tr_dev}, mc), **humans}
        transfer[f"{deg:g}"] = {k: _tables(cases, out[k], config) for k in tr_methods}
        transfer_pairs[f"{deg:g}"] = _pairs(out, [(m, h) for m in ("B1", "B0S", "SURVEY3") for h in ("HUMAN05", "HUMAN10")])
    mc0 = replace(config, sigma_transfer=0.0, display_line_px=0.0)
    out = {**evaluate(cases, launch(base_reads, tr_dev, est_config, mc0), mc0), **humans}
    transfer["0, ideal display"] = {k: _tables(cases, out[k], config) for k in tr_methods}
    transfer_pairs["0, ideal display"] = _pairs(out, [(m, h) for m in ("B1", "B0S", "SURVEY3") for h in ("HUMAN05", "HUMAN10")])
    sweeps["transfer_deg"] = transfer
    sweeps["transfer_vs_human"] = transfer_pairs
    log(f"  sweeps: aim transfer {time.perf_counter() - t0:.1f} s")

    # ---- execution level and capture rule --------------------------------------
    ex_methods = ("ORACLE", "SURVEY3", "B1", "HUMAN05", "HUMAN10", "STRAIGHT")
    ex_launch = {k: base_launch[k] for k in ex_methods}
    execution: Dict[str, dict] = {}
    execution_pairs: Dict[str, dict] = {}
    for deg, rel in EXEC_LEVELS:
        mc = replace(config, sigma_dir=math.radians(deg), sigma_speed=rel)
        same = abs(mc.sigma_dir - config.sigma_dir) < 1e-15 and abs(rel - config.sigma_speed) < 1e-15
        out = base_out if same else evaluate(cases, ex_launch, mc)
        label = f"{deg:g} deg / {100 * rel:g} %"
        execution[label] = {k: _tables(cases, out[k], config) for k in ex_methods}
        execution_pairs[label] = _pairs(
            out, [("B1", "HUMAN05"), ("B1", "HUMAN10"), ("B1", "STRAIGHT"), ("ORACLE", "B1"), ("SURVEY3", "B1"), ("SURVEY3", "HUMAN05")]
        )
    sweeps["execution"] = execution
    sweeps["execution_paired"] = execution_pairs
    cap_methods = ("ORACLE", "B1", "HUMAN05", "HUMAN10", "STRAIGHT")
    cap_out = evaluate(cases, {k: base_launch[k] for k in cap_methods}, config, capture=ph.CaptureModel(exponent=1.0))
    sweeps["capture"] = {
        "exponent 0.5 (default)": {k: baseline[k] for k in cap_methods},
        "exponent 1.0 (Penner-style)": {k: _tables(cases, cap_out[k], config) for k in cap_methods},
    }
    sweeps["capture_paired"] = {
        "exponent 0.5 (default)": _pairs(base_out, [("B1", "HUMAN05"), ("B1", "HUMAN10")]),
        "exponent 1.0 (Penner-style)": _pairs(cap_out, [("B1", "HUMAN05"), ("B1", "HUMAN10")]),
    }
    log(f"  sweeps: execution, capture {time.perf_counter() - t0:.1f} s")

    # ---- flag-out fallback: bearing x distance ---------------------------------
    fo: Dict[str, dict] = {}
    fo_out: Dict[str, Outcome] = {}
    variants = {
        "hand bearing, dialled distance (FLAGOUT)": {},
        "hand bearing, true distance": dict(sigma_user_distance=0.0),
        "true bearing, dialled distance": dict(sigma_hand_bearing=0.0),
        "true bearing, true distance": dict(sigma_hand_bearing=0.0, sigma_user_distance=0.0),
    }
    for label, changes in variants.items():
        reads = reads_for(f"fo_{label}", replace(base_params, **changes), with_horizon=False, flag_out=True)
        launches = device_launches(reads, ["FLAGOUT"], est_config, step)
        out = evaluate(cases, launches, config, perfect_only=True)
        fo[label] = {"FLAGOUT": _tables(cases, out["FLAGOUT"], config)}
        fo_out[label] = out["FLAGOUT"]
        if not changes:
            cups = evaluate(cases, {"FLAGOUT": cups_launch(launches["FLAGOUT"])}, config, perfect_only=True)
            fo["hand bearing, dialled distance, break-in-cups use model"] = {"FLAGOUT": _tables(cases, cups["FLAGOUT"], config)}
            fo_out["cups"] = cups["FLAGOUT"]
    fo["camera bearing and range (B0)"] = {"FLAGOUT": baseline["B0"]}
    keys = list(variants)
    sweeps["flagout_2x2"] = fo
    sweeps["flagout_2x2_paired"] = {
        "bearing, at the dialled distance": paired_delta(fo_out[keys[0]], fo_out[keys[2]]),
        "bearing, at the true distance": paired_delta(fo_out[keys[1]], fo_out[keys[3]]),
        "distance, with the hand bearing": paired_delta(fo_out[keys[0]], fo_out[keys[1]]),
        "distance, with the true bearing": paired_delta(fo_out[keys[2]], fo_out[keys[3]]),
        "camera (B0) against FLAGOUT": paired_delta(fo_out[keys[0]], base_out["B0"]),
        "FLAGOUT, cups against line": paired_delta(fo_out[keys[0]], fo_out["cups"]),
    }

    # ---- Survey: how far off the line the drops are placed ------------------------
    lateral: Dict[str, dict] = {}
    lateral_pairs: Dict[str, dict] = {}
    for sig in (0.05, 0.15, 0.30, 0.50):
        if abs(sig - base_params.sigma_survey_lateral) < 1e-12:
            out = base_out
        else:
            reads = reads_for(f"lat_{sig:g}", replace(base_params, sigma_survey_lateral=sig), with_horizon=False, survey=True)
            out = evaluate(cases, launch(reads, ("B1", "SURVEY2", "SURVEY3"), est_config), config, perfect_only=True)
        lateral[f"{sig:g}"] = {k: _tables(cases, out[k], config) for k in ("SURVEY2", "SURVEY3")}
        lateral_pairs[f"{sig:g}"] = _pairs(out, [("SURVEY3", "B1"), ("SURVEY2", "B1")])
    sweeps["survey_lateral_m"] = lateral
    sweeps["survey_lateral_paired"] = lateral_pairs
    log(f"  sweeps: flag-out 2x2, survey placement {time.perf_counter() - t0:.1f} s")

    # ---- seating noise beyond the main range, and seating outliers ----------------
    seat_methods = ("B1", "B0S", "SURVEY3")
    seat_pairs = [(m, h) for m in seat_methods for h in ("HUMAN05", "HUMAN10")]
    seating: Dict[str, dict] = {}
    seating_pairs: Dict[str, dict] = {}
    for mrad in (1.0, 2.5, 5.0, 7.5, 10.0):
        if abs(mrad * 1e-3 - base_params.sigma_seat) < 1e-12:
            out = base_out
        else:
            reads = reads_for(f"seat_{mrad:g}", replace(base_params, sigma_seat=mrad * 1e-3), with_horizon=False, spin=True, survey=True)
            out = {**evaluate(cases, launch(reads, seat_methods, est_config), config), **humans}
        seating[f"{mrad:g}"] = {k: _tables(cases, out[k], config) for k in seat_methods}
        seating_pairs[f"{mrad:g}"] = _pairs(out, seat_pairs)
    levels = [float(k) for k in seating]
    sweeps["seating_ext_mrad"] = seating
    sweeps["seating_ext_paired"] = seating_pairs
    sweeps["seating_breakeven_mrad"] = {
        f"{m}_vs_{h}": {
            key: breakeven_band(levels, [seating_pairs[k][f"{m}_vs_{h}"] for k in seating], key)
            for key in ("d_make", "d_make_human")
        }
        for m, h in seat_pairs
    }
    outl: Dict[str, dict] = {"no outliers": {k: baseline[k] for k in seat_methods}}
    for frac in (0.10, 0.25):
        reads = reads_for(f"outl_{frac:g}", replace(base_params, p_seat_outlier=frac), with_horizon=False, spin=True, survey=True)
        outl[f"{100 * frac:g} % of seatings carry an extra {1e3 * base_params.seat_outlier_sigma:g} mrad"], _ = quick(reads, seat_methods, est_config)
    sweeps["seating_outliers"] = outl
    log(f"  sweeps: seating range and outliers {time.perf_counter() - t0:.1f} s")

    # ---- systematic sensor errors -----------------------------------------------
    def systematics_entry(reads: Reads, tab: dict, out: Dict[str, Outcome], lch: Dict[str, Launch]) -> dict:
        slope = _slope_error_table(cases, {"B1": lch["B1"]}, reads, config)
        return {
            "B1": tab["B1"],
            "range": _range_table(cases, reads, config, est_config),
            "found": float(np.mean(reads.found)),
            "base_hidden": float(np.mean([not t.base_visible for _, t in reads.first])),
            "along_base_visible": {d: slope[d]["along_base_visible"]["B1"] for d in slope},
            "vs_baseline": paired_delta(base_out["B1"], out["B1"]),
        }

    sys_variants = {
        "disparity bias +0.1 px": dict(disparity_bias=0.1),
        "disparity bias -0.1 px": dict(disparity_bias=-0.1),
        "disparity bias +0.2 px": dict(disparity_bias=0.2),
        "disparity bias -0.2 px": dict(disparity_bias=-0.2),
        "mirage x 10": dict(sigma_mirage=10.0 * base_params.sigma_mirage),
        "tilt bias 2.5 mrad": dict(sigma_tilt_bias=2.5e-3),
        "level reference shares the tilt bias": dict(level_shares_tilt_bias=True),
        "detection floor 20 %": dict(p_detect_fail_floor=0.20),
        "visor pointing sigma 20 deg": dict(sigma_heading=math.radians(20.0)),
    }
    systematics = {"baseline": systematics_entry(base_reads, baseline, base_out, base_launch)}
    for label, changes in sys_variants.items():
        reads = reads_for(f"sys_{label}", replace(base_params, **changes), with_horizon=False)
        lch = launch(reads, ("B1",), est_config)
        out = evaluate(cases, lch, config, perfect_only=True)
        systematics[label] = systematics_entry(reads, tables(out), out, lch)
    sweeps["systematics"] = systematics
    log(f"  sweeps: systematic sensor errors {time.perf_counter() - t0:.1f} s")

    # ---- metre-scale relief of the green -----------------------------------------
    relief_methods = ("STRAIGHT", "B1", "B0S", "SURVEY3", "HUMAN05", "HUMAN10")
    relief: Dict[str, dict] = {"0": {k: baseline[k] for k in relief_methods}}
    relief_pairs: Dict[str, dict] = {"0": _pairs(base_out, [("B1", "HUMAN05"), ("B0S", "B1"), ("SURVEY3", "B1"), ("SURVEY3", "HUMAN05")])}
    relief_slope: Dict[str, float] = {"0": 0.0}
    for mm in (0.5, 1.0, 2.0):
        twins = _twin_cases(
            cases, lambda c, mm=mm: c.scenario.green.with_relief(mm * 1e-3, seed=1000 * c.seed + c.cls_idx), n_samples=129
        )
        reads = take_reads(twins, base_params, config, with_horizon=False, spin=True, survey=True)
        out = evaluate(twins, launch(reads, relief_methods, est_config, on=twins), config)
        relief[f"{mm:g}"] = {k: _tables(twins, out[k], config) for k in relief_methods}
        relief_pairs[f"{mm:g}"] = _pairs(out, [("B1", "HUMAN05"), ("B0S", "B1"), ("SURVEY3", "B1"), ("SURVEY3", "HUMAN05")])
        relief_pairs[f"{mm:g}"]["B1_vs_smooth"] = paired_delta(base_out["B1"], out["B1"])
        relief_pairs[f"{mm:g}"]["SURVEY3_vs_smooth"] = paired_delta(base_out["SURVEY3"], out["SURVEY3"])
        relief_slope[f"{mm:g}"] = _rms([t.local_cross - c.local_cross for t, c in zip(twins, cases)])
    sweeps["relief_mm"] = relief
    sweeps["relief_paired"] = relief_pairs
    sweeps["relief_added_slope"] = relief_slope
    log(f"  sweeps: metre-scale relief {time.perf_counter() - t0:.1f} s")

    # ---- horizon: weight of the residuals, and extent of the modelled terrain -----
    nf_reads = reads_for("no_fringe", base_params, fringe="no_fringe", with_horizon=True)
    md_reads = reads_for("mounded", base_params, fringe="mounded", with_horizon=True)
    hw: Dict[str, dict] = {"realistic": {}, "no_fringe": {}, "mounded": {}}
    for sigma_mrad in (0.3, 1.0, 3.0, 10.0):
        cfg = replace(est_config, sigma_horizon=sigma_mrad * 1e-3)
        for label, reads in (("realistic", base_reads), ("no_fringe", nf_reads), ("mounded", md_reads)):
            tab, out = quick(reads, ("B2",), cfg)
            entry = {"B2": tab["B2"], "vs_B1": paired_delta(base_out["B1"], out["B2"])}
            entry["vs_B1"]["verdict"] = verdict(entry["vs_B1"])
            hw[label][f"{sigma_mrad:g}"] = entry
    hw["B1"] = baseline["B1"]
    sweeps["horizon_sigma_mrad"] = hw

    def boundary_share(reads: Reads) -> float:
        return float(np.mean(np.concatenate([t.horizon.at_boundary for _, t in reads.first])))

    first = paired_delta(base_out["B1"], base_out["B2"])
    first["verdict"] = verdict(first)
    half0 = CLASS_PARAMS[GREEN_CLASSES[0]].half_width
    domain: Dict[str, dict] = {f"{half0:g}": {"vs_B1": first, "at_boundary": boundary_share(base_reads)}}
    for half in (40.0, 60.0):
        twins = _twin_cases(cases, lambda c, half=half: make_green(
            GREEN_CLASSES[c.cls_idx], c.seed, replace(CLASS_PARAMS[GREEN_CLASSES[c.cls_idx]], half_width=half)))
        reads = take_reads(twins, base_params, config, with_horizon=True)
        out = evaluate(twins, launch(reads, ("B1", "B2"), est_config, on=twins), config, perfect_only=True)
        entry = paired_delta(out["B1"], out["B2"])
        entry["verdict"] = verdict(entry)
        domain[f"{half:g}"] = {"vs_B1": entry, "at_boundary": boundary_share(reads)}
    sweeps["horizon_domain_m"] = domain
    log(f"  sweeps: horizon weight and terrain extent {time.perf_counter() - t0:.1f} s")

    # ---- Precision Read when the two seatings are not independent -----------------
    spin: Dict[str, dict] = {"0": {"B0S": baseline["B0S"], "B1": baseline["B1"]}}
    for rho in (0.5, 1.0):
        reads = reads_for(f"spin_{rho:g}", replace(base_params, seat_repeat_correlation=rho), with_horizon=False, spin=True)
        spin[f"{rho:g}"], _ = quick(reads, ("B0S",), est_config)
    sweeps["spin_seat_correlation"] = spin

    # ---- Survey with and without the model-error allowance on local samples -------
    sweeps["survey_sigma_field_mrad"] = {
        f"{est_config.sigma_field * 1e3:g} (default)": {k: baseline[k] for k in ("SURVEY2", "SURVEY3")},
        "0 (local samples trusted fully)": quick(base_reads, ("SURVEY2", "SURVEY3"), replace(est_config, sigma_field=0.0))[0],
    }

    # ---- range with the first-hole stick-height prior ------------------------------
    first_hole = reads_for("first_hole", replace(base_params, stick_height_learned=False), with_horizon=False)
    sweeps["range_first_hole"] = _range_table(cases, first_hole, config, est_config)
    log(f"  sweeps: done {time.perf_counter() - t0:.1f} s")
    return sweeps


def run_all(config: MCConfig = MCConfig(), log: Callable[[str], None] = print) -> Dict[str, dict]:
    """Run the whole Monte Carlo and return the summary dictionary."""
    t_start = time.perf_counter()
    cpu_start = time.process_time()
    load_start = os.getloadavg()[0] if hasattr(os, "getloadavg") else math.nan
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
            "sigma_transfer_deg": math.degrees(config.sigma_transfer),
            "display_line_px": config.display_line_px,
            "display_step_deg": math.degrees(config.display_step),
            "human_cross_errors": list(config.human_cross_errors),
            "human_grain": config.human_grain,
            "exec_levels": [list(level) for level in EXEC_LEVELS],
            "master_seed": config.master_seed,
            "camera": {**asdict(cam), "half_fov_h_deg": math.degrees(cam.half_fov_h), "up_fov_deg": math.degrees(cam.up_fov)},
            "sensor_params": {k: v for k, v in asdict(base_params).items() if k != "camera"},
            "estimator_config": asdict(est_config),
            "default_method": es.DEFAULT_METHOD,
            "numba": ph.NUMBA_STATUS,
            "runtime_s": {
                "cases": t_cases, "main": t_main, "sweeps": t_total - t_main - t_cases, "total": t_total,
                "cpu": time.process_time() - cpu_start, "n_cpu": os.cpu_count(), "load_average_at_start": load_start,
            },
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
