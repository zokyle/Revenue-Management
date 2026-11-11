"""The GreenLine estimator: reference for the embedded firmware.

Input: :class:`~greenline_sim.measurements.Measurements` (one placement of
the marker, or several for a Survey) and nominal constants
(:class:`EstimatorConfig`).  Output: an :class:`Estimate` - the aim line the
display draws, the launch speed, the "plays-like" distance, the break, the
slope at the ball and a confidence score.

NOTHING in this module may look at the true green.  It imports the physics
solver, the ``Measurements`` record and the numba shim only (a test enforces
this).

Method
------
All work is done in the PUTT FRAME: origin at the marker (the ball), ``+x``
toward the hole along the measured flag bearing, ``+y`` to the left.  The
green around the putt is modelled as the quadratic patch

    z(x, y) = a x + b y + 0.5 (c x^2 + 2 d x y + e y^2)

and ``p = (a, b, c, d, e)`` is fitted by Levenberg-Marquardt on
Huber-robustified, sigma-normalised residuals plus Gaussian priors:

* **tilt** of each placement at station ``s_i`` on the line:
  ``a + c s_i = tilt_x``, ``b + d s_i = tilt_y``  (sigma: seating noise);
* **hole height** from the lowest visible point of the flagstick, when its
  base is visible: ``a (D - s_i) + 0.5 c (D^2 - s_i^2) = h_cam + D_i tan(elev)``
  (tight); when the base is hidden behind a crest only the one-sided bound
  "the hole is LOWER than that sight line" is used;
* **turf horizon** (method B2 only): ``tan(elev_k) = E(theta_k; p)`` with the
  exact forward model of a quadratic seen from height ``h``
  (:func:`quad_horizon`), plus two nuisance offsets (pitch and roll) for the
  level reference of the cameras, each with the prior ``sigma_level``;
* **priors**: curvatures ``c, d, e ~ N(0, 0.004 1/m)``, weak priors on
  ``a, b``.

Without horizon rows (``B1``, the Survey) every residual is linear in ``p``,
the robust cost is convex, and the minimum found is the MAP estimate
whatever the starting point.

With horizon rows the cost is NOT convex, and how the horizon is used
matters more than how well the cost is minimised:

* ``B2`` (default form, "anchored"): two stages.  First the ``B1`` fit.
  Then everything the Quick Read measures directly is HELD at that solution
  - the slopes at the ball ``a, b`` (the tilt) and the along-line curvature
  ``c`` (the hole height) - and only the twist ``d``, the cross curvature
  ``e``, a common-mode silhouette offset and the roll offset are fitted to
  the horizon rows.  The reason is physical: the silhouette is formed by
  whatever lies behind the green, at a height the model does not know.  A
  common-mode height error of the silhouette is indistinguishable from the
  along-line slope ``a`` and curvature ``c`` (their signatures are
  ``cos(theta)`` and ``cos^2(theta)``, 0.8 ... 1 across the field), so it
  gets a nuisance parameter of its own (prior ``sigma_silhouette``,
  practically free) and the horizon is left to say only how the surface
  tilts ACROSS the field.  With ``a, b, c`` held the cost has, in practice,
  a single minimum (see the tests and the report, section 5).
* ``B2`` with ``EstimatorConfig.horizon_free_c``: as above but ``c`` may
  move and there is no silhouette offset.  The silhouette height then goes
  into ``c`` and overrules the flag-base height.  Comparison only.
* ``B2`` with ``EstimatorConfig.horizon_joint`` ("joint"): all parameters
  fitted to all rows at once, the literal joint MAP problem.  Its cost has
  many local minima - a single run from the tilt plane ends in a non-global
  one in 14-48 % of simulated reads, depending on the surrounds - and its
  lowest minimum lets the 41 horizon samples overrule the puck's own tilt
  reading (along-line slope at the ball wrong by 10 mrad RMS against
  2.5 mrad for the tilt).  It is kept, with a 25-start search, only so that
  the report can show both.

Then the putt is solved on the fitted patch with the entered green speed
(:func:`greenline_sim.physics.solve_aim_quadratic_batch`).  The grain
reading is used only if ``EstimatorConfig.use_grain`` is set; the default is
off, because the grain sensor ships disabled.

The slope and the fall line reported at the ball are always the tilt reading
itself, never the fitted patch.

Horizon forward model (derivation)
----------------------------------
Along the ray at azimuth ``theta`` the patch is ``z(r) = A r + 0.5 K r^2``
with ``A = a cos + b sin`` and ``K = c cos^2 + 2 d sin cos + e sin^2``.  Seen
from a lens at height ``h`` above the origin, a ground point at distance
``r`` has elevation tangent ``f(r) = (z(r) - h) / r = A + 0.5 K r - h / r``,
and the horizon is ``E = max f(r)`` over ``d_min <= r <= L`` (``L`` = the
assumed far limit of the turf).  ``f'(r) = 0.5 K + h / r^2``, so

* ``K >= 0`` (ray concave-up or flat): ``f`` increases, the maximum is at the
  far limit, ``E = A + 0.5 K L - h / L``;
* ``K < 0`` (concave-down): ``f`` peaks at ``r* = sqrt(2 h / |K|)`` with
  ``E = A - sqrt(2 h |K|)`` - the crest; if ``r*`` lies outside
  ``[d_min, L]`` the maximum is at the nearer end of the interval.

In every case ``dE/dA = 1`` and ``dE/dK = 0.5 r_max`` (envelope theorem),
which gives the analytic Jacobian used by the fit.

Operating modes and baselines
-----------------------------
``STRAIGHT``  aim at the hole, flat-green pace (no slope reading).
``B0``        plane from the puck tilt only (a digital-level ball marker).
``B1``        Quick Read: tilt + flag-base height (no horizon).
              With a spin-and-reread measurement (``tilt_reads == 2``) this is
              the Precision Read; with several placements it is the Survey.
``B2``        B1 + turf-horizon residuals (anchored; see above).

Fallbacks: if the flagstick was not found the estimator uses the tilt-only
plane along the visor axis with the dialled (or a default) distance and
flags low confidence (``flag_missing``).  If the flag was found but could
not be ranged, its measured bearing is kept and only the distance falls back
(``range_missing``).

The numerical kernels (:func:`_fit_residuals`, :func:`_fit_lm`,
:func:`_chol_solve`) are scalar code that runs under numba or as plain
Python; they are what the C port follows.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple, Union

import numpy as np

from ._jit import njit
from .measurements import Measurements
from .physics import (
    DEFAULT_PAST,
    DEFAULT_TOL_MISS,
    DEFAULT_TOL_PACE,
    G,
    HOLE_R,
    ROLL_FACTOR,
    SolveStatus,
    solve_aim_quadratic_batch,
    stimp_to_decel,
)

__all__ = [
    "METHODS",
    "DEFAULT_METHOD",
    "EstimatorConfig",
    "RangeEstimate",
    "PatchFit",
    "Estimate",
    "fuse_range",
    "quad_horizon",
    "horizon_far_limit",
    "fit_patch",
    "estimate",
    "estimate_survey",
    "estimate_batch",
]

METHODS: Tuple[str, ...] = ("STRAIGHT", "B0", "B1", "B2")
"""Estimation methods accepted by :func:`estimate`."""

DEFAULT_METHOD = "B1"
"""The firmware default: the Quick Read without horizon residuals.

The Monte Carlo (results/REPORT.md, section 5) found that the turf-horizon
residuals of ``B2`` help when the camera sees the smooth continuation of the
green, give no reliable gain with the collar, rough and surrounds as
modelled (a small reduction of the mean miss that disappears when the
terrain is modelled further out), and hurt when the surrounds carry mounds
that are independent of the green.  The device cannot sense which case it is
in, so ``B2`` stays an option and is not the default.

The other firmware default that matters for the numbers: the grain reading
is NOT used (``EstimatorConfig.use_grain`` is False), because the design
specification ships the grain sensor disabled until it is validated."""

# aim_source codes
AIM_FROM_PATCH = 0  # solved on the fitted quadratic patch
AIM_FROM_PLANE = 1  # patch not solvable: solved on its secant plane
AIM_BEST_EFFORT = 2  # neither solvable: best iterate of the plane solve
AIM_STRAIGHT = 3  # no usable solution at all: straight at flat pace


@dataclass(frozen=True)
class EstimatorConfig:
    """Nominal constants of the estimator (SI units, radians).

    These are FIRMWARE constants: design values, not the simulator's truth.
    In a sensitivity sweep the true noise changes while these stay put,
    exactly as it would be for a shipped device.

    Attributes
    ----------
    sigma_seat : float [rad per axis]
        Assumed seating noise of one placement.
    sigma_tilt_bias : float [rad per axis]
        Assumed device tilt bias of a single read (cancelled by a spin).
    sigma_gravity : float [rad per axis]
        Assumed accelerometer noise per tilt read.
    sigma_level : float [rad]
        Assumed error of the cameras' level reference (gravity 0.3 mrad and
        boresight 0.3 mrad in quadrature).
    sigma_pixel_elev : float [px];  sigma_disp : float [px]
        Assumed pixel noise on elevations and on the stereo disparity.
    sink_mean, sink_sigma : float [m]
        Assumed mean and spread of how far the puck sinks into the canopy
        (uniform 0 ... 1.5 mm: mean 0.75 mm, sigma 0.43 mm).  The lens height
        used by the estimator is ``Measurements.h_cam - sink_mean``.
    sigma_mirage : float [1/m]
        Assumed spread of the ray-curvature term.
    sigma_curv : float [1/m]
        Prior sigma of the curvatures ``c, d, e``.
    sigma_slope_prior : float [m/m]
        Weak prior sigma of the slopes ``a, b``.
    sigma_field : float [rad]
        Survey fits only: assumed RMS departure of the true slope field from
        the plane-plus-curvature model along the line.  It is added in
        quadrature to the tilt sigma of every drop, and (times the baseline
        ``D - s_i``) to the hole-height sigma of the drops after the first,
        so that a very precise but purely LOCAL sample - above all the
        height difference seen from one metre short of the hole - cannot
        bend the whole fitted line.  The total rise seen from the ball is
        left tight: that is the quantity the pace needs, whatever the shape
        in between.  A-priori value equal to the nominal seating noise.
    sigma_drop_lateral : float [m]
        Survey fits only: assumed 1-sigma distance of a drop (placed by eye)
        from the true ball->hole line.  A drop that is off the line by ``y``
        at distance ``r`` from the hole has its "toward the hole" frame
        rotated by ``y / r`` against the putt frame, which leaks the along
        slope into its cross tilt; the tilt sigmas of the drops after the
        first are inflated by that cross-talk.
    sigma_horizon : float [rad]
        Per-sample sigma of the horizon residuals: pixel noise (0.23 mrad for
        GL1) plus an allowance for the silhouette not being the fitted
        quadratic.  The Monte Carlo sweeps this value.
    huber_k : float
        Huber threshold in units of sigma, applied to all data residuals.
    horizon_d_min : float [m]
        Nearest ground distance of the horizon model.
    horizon_l_factor, horizon_l_min, horizon_l_cap : float
        Assumed far limit of the turf: ``L = min(max(l_factor * D, l_min), l_cap)`` [m].
    use_flag_base : bool
        Use the hole-height residual / bound (False = ablation).
    assume_base_visible : bool
        Treat the lowest visible point of the stick as its base even when the
        measurement says it is hidden (models a device that cannot tell).
    use_grain : bool
        Use the measured grain.  Default False: the design specification
        ships the grain sensor DISABLED until it is validated, so the
        firmware default solves the putt without grain.
    grain_kappa_max : float
        Clip on the measured grain strength.
    past : float [m]
        Target pace: flat-green roll-out beyond the hole.
    default_distance : float [m]
        Distance assumed when neither the cameras nor the golfer supply one.
    sigma_hand_bearing : float [rad]
        Assumed pointing error when the visor axis is used as the bearing.
    min_disparity : float [px]
        Smallest disparity accepted for stereo ranging.
    stimp_min, stimp_max : float [ft]
        Clip on the entered green speed.
    lm_max_iter : int;  lm_tol : float;  lm_lambda0 : float
        Levenberg-Marquardt iteration limit, convergence tolerance on the
        scaled step (slopes in units of 1e-2, curvatures and offsets in
        1e-3), and initial damping.
    horizon_joint : bool
        ``B2`` only.  False (default): the anchored two-stage fit - ``a, b,
        c`` from the Quick-Read problem, ``d, e`` from the horizon.  True:
        the joint fit of all parameters to all rows (comparison only).
    horizon_free_c : bool
        Anchored ``B2`` only, comparison only.  True: the horizon stage may
        also move the along-line curvature ``c`` and has no silhouette
        offset - the common-mode height of the silhouette then goes into
        ``c`` and overrules the flag-base height.
    sigma_silhouette : float [rad]
        Anchored ``B2``: prior sigma of the common-mode offset between the
        measured silhouette and the model.  The silhouette is formed by
        whatever stands behind the green (40 mm of rough 10 m away is
        4 mrad, a 0.2 m rise 15 m away 13 mrad), so the offset is left
        practically free; results do not change between 5 and 20 mrad.
    multi_start : bool
        ``B2`` only.  Run the fixed set of extra starts and keep the lowest
        minimum.  False = a single run from the first start.
    tol_miss, tol_pace : float [m]
        Tolerances of the aim solver.
    poor_horizon_fraction : float
        Fraction of horizon samples beyond the Huber threshold above which
        the horizon is flagged as poor.
    conf_twist_sigma : float [1/m];  conf_twist_length : float [m]
        Confidence score only: how much the cross slope is expected to
        change along the line, ``sigma_d = conf_twist_sigma /
        sqrt(1 + (D / conf_twist_length)^2)``.  This is the
        "representativeness" allowance of a local slope sample.  The values
        were CALIBRATED on the synthetic greens of this simulator (RMS
        difference between the cross slope at the ball and its path average:
        1.5 mrad at 1.5 m, 5 mrad at 6 m, 7.6 mrad at 12 m); they are not
        field data.  (The fit itself keeps the wider prior ``sigma_curv``.)
    conf_grain_kappa : float;  conf_grain_rel : float
        Confidence score only: RMS of the cross-line grain strength the
        solve does not know about - ``conf_grain_kappa`` when the grain is
        not used (calibrated on the synthetic greens, 35 % of which are
        strongly grained), ``conf_grain_rel`` times the measured strength
        when it is (30 % strength and 20 deg direction error).
    conf_base_hidden, conf_flag_missing, conf_range_missing, conf_poor_horizon, conf_aim_fallback : float
        Multipliers applied to the confidence score when the corresponding
        flag is raised.  (A missing flag already lowers the score through
        ``sigma_hand_bearing``; its multiplier is therefore close to 1.)
    """

    sigma_seat: float = 2.5e-3
    sigma_tilt_bias: float = 1.0e-3
    sigma_gravity: float = 0.3e-3
    sigma_level: float = 0.43e-3
    sigma_pixel_elev: float = 0.15
    sigma_disp: float = 0.08
    sink_mean: float = 0.75e-3
    sink_sigma: float = 0.43e-3
    sigma_mirage: float = 5.0e-5
    sigma_curv: float = 0.004
    sigma_slope_prior: float = 0.05
    sigma_field: float = 2.5e-3
    sigma_drop_lateral: float = 0.15
    sigma_horizon: float = 1.0e-3
    huber_k: float = 1.5
    horizon_d_min: float = 0.15
    horizon_l_factor: float = 1.5
    horizon_l_min: float = 6.0
    horizon_l_cap: float = 20.0
    use_flag_base: bool = True
    assume_base_visible: bool = False
    use_grain: bool = False
    grain_kappa_max: float = 0.25
    past: float = DEFAULT_PAST
    default_distance: float = 3.0
    sigma_hand_bearing: float = math.radians(1.5)
    min_disparity: float = 0.25
    stimp_min: float = 5.0
    stimp_max: float = 16.0
    lm_max_iter: int = 60
    lm_tol: float = 1e-9
    lm_lambda0: float = 1e-4
    horizon_joint: bool = False
    horizon_free_c: bool = False
    sigma_silhouette: float = 0.02
    multi_start: bool = True
    tol_miss: float = DEFAULT_TOL_MISS
    tol_pace: float = DEFAULT_TOL_PACE
    poor_horizon_fraction: float = 0.3
    conf_twist_sigma: float = 0.002
    conf_twist_length: float = 10.0
    conf_grain_kappa: float = 0.045
    conf_grain_rel: float = 0.45
    conf_base_hidden: float = 0.8
    conf_flag_missing: float = 0.9
    conf_range_missing: float = 0.5
    conf_poor_horizon: float = 0.8
    conf_aim_fallback: float = 0.7


# --------------------------------------------------------------------------
# Range fusion
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RangeEstimate:
    """Range to the flagstick from one placement [m].

    ``stereo`` / ``mono`` are NaN when that channel is unavailable;
    ``distance`` is their inverse-variance fusion (or the only one
    available; NaN if neither is).  ``sigma*`` are 1-sigma values [m].
    """

    distance: float
    sigma: float
    stereo: float
    sigma_stereo: float
    mono: float
    sigma_mono: float

    @property
    def valid(self) -> bool:
        return math.isfinite(self.distance) and self.distance > 0.0


def fuse_range(meas: Measurements, config: EstimatorConfig = EstimatorConfig()) -> RangeEstimate:
    """Range to the flagstick: stereo fused with the stick's angular height.

    * Stereo: ``D = f b / disparity``, ``sigma_D = D^2 sigma_disp / (f b)``.
    * Monocular: ``D = H / (tan(top) - tan(base))`` with ``H`` the device's
      estimate of the visible stick height; available only when the top of
      the stick is inside the upward field AND its base is visible (a hidden
      base would bias the range long).  ``sigma_D / D`` combines the relative
      uncertainty of ``H`` with the pixel noise on the two elevations.
    * Fusion by inverse variance.  The stereo sigma is re-evaluated at the
      fused range once, so that a low stereo reading does not get extra
      weight just because it is low.
    """
    nan = math.nan
    if not meas.flag_found:
        return RangeEstimate(nan, nan, nan, nan, nan, nan)
    fb = meas.f_px * meas.baseline
    stereo = sig_s = nan
    if math.isfinite(meas.flag_disparity) and meas.flag_disparity >= config.min_disparity:
        stereo = fb / meas.flag_disparity
        sig_s = stereo * stereo * config.sigma_disp / fb
    mono = sig_m = nan
    base_ok = meas.flag_base_visible or config.assume_base_visible
    if meas.flag_top_visible and base_ok and math.isfinite(meas.flag_top_elev) and math.isfinite(meas.flag_low_elev):
        span = math.tan(meas.flag_top_elev) - math.tan(meas.flag_low_elev)
        if span > 0.02:
            mono = meas.stick_height_est / span
            pix = config.sigma_pixel_elev / meas.f_px
            sig_m = mono * math.sqrt(meas.stick_height_rel_sigma**2 + 2.0 * (pix / span) ** 2)
    if math.isfinite(stereo) and math.isfinite(mono):
        dist = stereo
        sig = sig_s
        for _ in range(2):
            ws = 1.0 / sig_s**2
            wm = 1.0 / sig_m**2
            dist = (ws * stereo + wm * mono) / (ws + wm)
            sig = 1.0 / math.sqrt(ws + wm)
            sig_s = dist * dist * config.sigma_disp / fb
        return RangeEstimate(dist, sig, stereo, stereo * stereo * config.sigma_disp / fb, mono, sig_m)
    if math.isfinite(stereo):
        return RangeEstimate(stereo, sig_s, stereo, sig_s, nan, nan)
    if math.isfinite(mono):
        return RangeEstimate(mono, sig_m, nan, nan, mono, sig_m)
    return RangeEstimate(nan, nan, nan, nan, nan, nan)


# --------------------------------------------------------------------------
# Horizon forward model of a quadratic patch
# --------------------------------------------------------------------------


def horizon_far_limit(distance: float, config: EstimatorConfig = EstimatorConfig()) -> float:
    """Assumed far limit of the turf [m]: ``min(max(1.5 D, 6 m), 20 m)`` by default."""
    return min(max(config.horizon_l_factor * distance, config.horizon_l_min), config.horizon_l_cap)


def quad_horizon(coeffs, theta, h_cam: float, d_min: float, far_limit: float) -> Tuple[np.ndarray, np.ndarray]:
    """Turf horizon of a quadratic patch seen from height ``h_cam`` above its origin.

    Parameters
    ----------
    coeffs : (5,) ``(a, b, c, d, e)`` of ``z = a x + b y + 0.5 (c x^2 + 2 d x y + e y^2)``
    theta : (n,) array [rad]
        Ray azimuths in the patch frame.
    h_cam : float [m] (> 0)
    d_min, far_limit : float [m]
        The ground is looked at for ``d_min <= r <= far_limit``.

    Returns
    -------
    (E, r_max) : two (n,) arrays
        ``E = max_r (z(r, theta) - h_cam) / r`` (tangent of the horizon
        elevation) and the distance ``r_max`` [m] at which it occurs.  The
        derivative of ``E`` with respect to the ray curvature ``K`` is
        ``0.5 * r_max`` and with respect to the ray slope ``A`` it is 1 (see
        the module docstring).
    """
    theta = np.asarray(theta, dtype=float)
    if not (h_cam > 0.0 and far_limit > d_min > 0.0):
        raise ValueError("need h_cam > 0 and far_limit > d_min > 0")
    horizon, r_max, _ = _horizon_terms(np.asarray(coeffs, dtype=float), np.cos(theta), np.sin(theta), h_cam, d_min, far_limit)
    return horizon, r_max


def _horizon_terms(coeffs: np.ndarray, ct: np.ndarray, st: np.ndarray, h_cam: float, d_min: float, far_limit: float):
    """``(E, r_max, d2E/dK2)`` of the quadratic-patch horizon for rays with
    direction cosines ``ct``, ``st`` (see :func:`quad_horizon`).

    The second derivative is ``r* / (4 |K|)`` where the horizon is an
    interior crest (``E = A - sqrt(2 h |K|)``) and zero where it sits at an
    end of the interval (``E`` linear in ``K`` there).
    """
    a, b, c, d, e = coeffs[0], coeffs[1], coeffs[2], coeffs[3], coeffs[4]
    slope = a * ct + b * st
    curv = c * ct * ct + 2.0 * d * st * ct + e * st * st
    # concave-down rays crest at r* = sqrt(2 h / |K|); everything else peaks at the far limit
    neg = np.maximum(-curv, 1e-300)
    r_star = np.where(curv < 0.0, np.sqrt(2.0 * h_cam / neg), np.inf)
    r_max = np.clip(r_star, d_min, far_limit)
    horizon = slope + 0.5 * curv * r_max - h_cam / r_max
    interior = (r_star > d_min) & (r_star < far_limit)
    second = np.where(interior, 0.25 * r_max / neg, 0.0)
    return horizon, r_max, second


# --------------------------------------------------------------------------
# MAP fit of the patch
# --------------------------------------------------------------------------

_NPAR = 7  # a, b, c, d, e, level pitch offset, level roll offset
_FREE_ALL = np.ones(7, dtype=np.uint8)
_FREE_CURVATURES = np.array([0, 0, 1, 1, 1, 1, 1], dtype=np.uint8)  # a, b held
_FREE_TWIST = np.array([0, 0, 0, 1, 1, 1, 1], dtype=np.uint8)  # a, b, c held
_NO_HORIZON = np.zeros((0, 3))
_SCALE = np.array([1e-2, 1e-2, 1e-3, 1e-3, 1e-3, 1e-3, 1e-3])  # natural size of each parameter


@dataclass(frozen=True)
class PatchFit:
    """Result of :func:`fit_patch`.

    Attributes
    ----------
    coeffs : (5,) array ``(a, b, c, d, e)`` in the putt frame [m/m, 1/m]
    cov : (5, 5) array
        Posterior covariance (Gauss-Newton approximation at the solution).
        For the anchored horizon fit it is the two-stage covariance: the
        Quick-Read covariance of ``(a, b, c)`` propagated through the
        conditional fit of ``(d, e)``.
    level_offsets : (2,) array [rad]
        Fitted (pitch, roll) offsets of the cameras' level reference (zero
        unless horizon residuals were used).
    distance : float [m];  distance_sigma : float [m]
        Ball->hole distance used (fused camera range, or the dialled /
        default distance) and its 1-sigma uncertainty (NaN if unknown).
    bearing : float [rad]
        Direction of the hole in the device frame = direction of putt-frame
        ``+x`` (0 when the flag was not found: the visor axis).
    range : RangeEstimate
        Stereo / monocular / fused range of the first placement.
    tilt_slopes : (2,) array [m/m]
        The tilt reading of the placement at the ball, in the putt frame:
        the slope the puck measured directly.  The displayed slope and fall
        line at the ball come from this, whatever the fit did.
    cross_sigma_read : float [m/m]
        1-sigma of the mean cross slope along the line as far as the tilt
        readings know it: posterior of ``b + 0.5 d D`` from the cross-tilt
        of every located placement, with the confidence prior on the twist
        ``d`` (see :class:`EstimatorConfig`).  The horizon is deliberately
        left out of it.  Used by the confidence score.
    n_drops : int
        Placements used by the fit.
    stations : tuple of float [m]
        Their stations along the line.
    base_hidden : bool
        The hole height was only bounded (base of the stick hidden).
    flag_missing : bool
        No flagstick: tilt-only fallback along the visor axis.
    range_missing : bool
        The flag was found (its bearing is used) but neither range channel
        gave a distance: tilt-only plane at the dialled / default distance.
    used_horizon : bool;  poor_horizon : bool;  horizon_rms : float
        Whether horizon residuals entered the fit, whether they were flagged
        as poor, and their RMS in units of ``sigma_horizon`` (NaN if unused).
    n_iter : int;  converged : bool;  cost : float
        Levenberg-Marquardt diagnostics of the run that was kept.
    cost_first_start : float;  n_starts : int
        Cost reached from the first start, and the number of starts run.
        ``cost < cost_first_start`` means another start found a lower
        minimum than the first.
    """

    coeffs: np.ndarray
    cov: np.ndarray
    level_offsets: np.ndarray
    distance: float
    distance_sigma: float
    bearing: float
    range: RangeEstimate
    tilt_slopes: np.ndarray
    cross_sigma_read: float
    n_drops: int
    stations: Tuple[float, ...]
    base_hidden: bool
    flag_missing: bool
    range_missing: bool
    used_horizon: bool
    poor_horizon: bool
    horizon_rms: float
    n_iter: int
    converged: bool
    cost: float
    cost_first_start: float
    n_starts: int


_COST_TIE = 1e-9  # relative cost difference below which two minima count as the same
_START_CURVATURES_ANCHORED = (0.003,)  # [1/m] corner starts (d, e = +-this) of the anchored horizon fit
_START_CURVATURES_JOINT = (0.002, 0.005, 0.012)  # [1/m] corner starts of the joint fit


def _corner_starts(x0: np.ndarray, magnitudes: Sequence[float]) -> List[np.ndarray]:
    """Extra starting points of a horizon fit: ``x0`` with the curvatures
    ``(c, d, e)`` set to every sign combination of each magnitude [1/m]
    (8 starts per magnitude, in a fixed order)."""
    out = []
    for mag in magnitudes:
        for sign_c in (-1.0, 1.0):
            for sign_d in (-1.0, 1.0):
                for sign_e in (-1.0, 1.0):
                    x = x0.copy()
                    x[2], x[3], x[4] = sign_c * mag, sign_d * mag, sign_e * mag
                    out.append(x)
    return out


def _rotate_to(vec: np.ndarray, angle: float) -> Tuple[float, float]:
    """Components of a device-frame vector in a frame rotated by ``angle`` CCW."""
    ca = math.cos(angle)
    sa = math.sin(angle)
    return vec[0] * ca + vec[1] * sa, -vec[0] * sa + vec[1] * ca


def _tilt_sigma(meas: Measurements, config: EstimatorConfig) -> float:
    """Assumed 1-sigma error of one tilt component [rad]."""
    if meas.tilt_reads >= 2:  # spin-and-reread: two seatings averaged, bias cancelled
        return math.sqrt(0.5 * (config.sigma_seat**2 + config.sigma_gravity**2))
    return math.sqrt(config.sigma_seat**2 + config.sigma_tilt_bias**2 + config.sigma_gravity**2)


# ---- scalar kernels (numba or plain Python; the reference for the C port) ----


@njit(cache=True)
def _chol_solve(mat, rhs, n, out):
    """Solve ``mat @ out = rhs`` for a symmetric positive-definite ``mat``
    (n x n) by Cholesky factorisation.  ``mat`` is overwritten by its lower
    factor.  Returns False (``out`` undefined) if a pivot is not positive,
    i.e. the matrix is not positive definite to rounding."""
    for j in range(n):
        acc = mat[j, j]
        for k in range(j):
            acc -= mat[j, k] * mat[j, k]
        if not (acc > 0.0):
            return False
        piv = math.sqrt(acc)
        mat[j, j] = piv
        for i in range(j + 1, n):
            acc = mat[i, j]
            for k in range(j):
                acc -= mat[i, k] * mat[j, k]
            mat[i, j] = acc / piv
    for i in range(n):
        acc = rhs[i]
        for k in range(i):
            acc -= mat[i, k] * out[k]
        out[i] = acc / mat[i, i]
    for i in range(n - 1, -1, -1):
        acc = out[i]
        for k in range(i + 1, n):
            acc -= mat[k, i] * out[k]
        out[i] = acc / mat[i, i]
    return True


@njit(cache=True)
def _fit_residuals(x, rows, targets, one_sided, hz, hpar, r, jac, second):
    """Sigma-normalised data residuals of a patch fit at ``x`` (7,).

    ``rows`` (m, 7), ``targets`` (m,), ``one_sided`` (m,): the linear rows,
    residual ``rows[i] . x - targets[i]``; a one-sided row counts only while
    positive.  ``hz`` (n_h, 3): per horizon sample ``tan(elev), cos(theta),
    sin(theta)``; ``hpar = (sigma, h_cam, d_min, far_limit)``.  Fills ``r``
    (m + n_h), the Jacobian ``jac`` (m + n_h, 7) and ``second`` (m + n_h):
    the second derivative of each residual with respect to its ray curvature
    ``K`` (non-zero only where the horizon is an interior crest).
    """
    n_lin = rows.shape[0]
    for i in range(n_lin):
        acc = -targets[i]
        for j in range(_NPAR):
            acc += rows[i, j] * x[j]
        if one_sided[i] != 0 and acc <= 0.0:  # bound satisfied: no residual, no gradient
            r[i] = 0.0
            for j in range(_NPAR):
                jac[i, j] = 0.0
        else:
            r[i] = acc
            for j in range(_NPAR):
                jac[i, j] = rows[i, j]
        second[i] = 0.0
    n_h = hz.shape[0]
    if n_h > 0:
        sigma = hpar[0]
        h_cam = hpar[1]
        d_min = hpar[2]
        far = hpar[3]
        for k in range(n_h):
            ct = hz[k, 1]
            st = hz[k, 2]
            slope = x[0] * ct + x[1] * st
            curv = x[2] * ct * ct + 2.0 * x[3] * st * ct + x[4] * st * st
            interior = False
            r_max = far  # concave-up or flat ray: the horizon is at the far limit
            if curv < 0.0:  # concave-down: crest at r* = sqrt(2 h / |K|), clipped to the interval
                r_star = math.sqrt(2.0 * h_cam / (-curv))
                if r_star <= d_min:
                    r_max = d_min
                elif r_star < far:
                    r_max = r_star
                    interior = True
            i = n_lin + k
            r[i] = (slope + 0.5 * curv * r_max - h_cam / r_max + x[5] + x[6] * st - hz[k, 0]) / sigma
            jac[i, 0] = ct / sigma
            jac[i, 1] = st / sigma
            jac[i, 2] = 0.5 * r_max * ct * ct / sigma
            jac[i, 3] = r_max * st * ct / sigma
            jac[i, 4] = 0.5 * r_max * st * st / sigma
            jac[i, 5] = 1.0 / sigma
            jac[i, 6] = st / sigma
            second[i] = 0.25 * r_max / (-curv) / sigma if interior else 0.0


@njit(cache=True)
def _fit_cost(x, r, prior_w, huber_k):
    """Robust MAP cost: Huber loss of the data residuals + Gaussian priors."""
    cost = 0.0
    for i in range(r.shape[0]):
        a = abs(r[i])
        if a <= huber_k:
            cost += 0.5 * a * a
        else:
            cost += huber_k * a - 0.5 * huber_k * huber_k
    for j in range(_NPAR):
        cost += 0.5 * prior_w[j] * x[j] * x[j]
    return cost


@njit(cache=True)
def _fit_gauss(r, jac, prior_w, huber_k, gauss):
    """Gauss-Newton matrix of the robust MAP cost with Huber (IRLS) weights
    ``min(1, k / |r|)``; its inverse is the posterior covariance reported."""
    for a in range(_NPAR):
        for b in range(_NPAR):
            gauss[a, b] = 0.0
        gauss[a, a] = prior_w[a]
    for i in range(r.shape[0]):
        ar = abs(r[i])
        w = 1.0 if ar <= huber_k else huber_k / ar
        for a in range(_NPAR):
            wa = w * jac[i, a]
            if wa != 0.0:
                for b in range(_NPAR):
                    gauss[a, b] += wa * jac[i, b]


@njit(cache=True)
def _fit_lm(x0, free, rows, targets, one_sided, hz, hpar, prior_w, huber_k, scale, max_iter, tol, lam0, x_out, gauss_out):
    """Levenberg-Marquardt minimisation of the robust MAP cost from ``x0``.

    Solves ``(H + lam * diag(H_gauss)) step = -grad`` by Cholesky, accepts
    the step only if it does not increase the cost, otherwise raises ``lam``
    tenfold (also when the matrix is not positive definite).  ``H`` is the
    Gauss-Newton matrix with Huber (IRLS) weights - a majoriser of the robust
    cost, safe far from the solution but only linearly convergent while
    outliers remain - until the set of Huber outliers is the same at two
    consecutive iterates; from then on it is the exact Hessian of the Huber
    cost for that outlier set (weight 1 for inliers, 0 for outliers, which
    still pull through the gradient), giving quadratic convergence.  In both
    cases the exact second-order term of the horizon rows (the only
    non-linear ones) is added: ``psi(r_k) * d2r_k/dK2 * q_k q_k^T`` with
    ``q_k = dK/dp = (cos^2, 2 sin cos, sin^2)``.

    Parameters with ``free[j] == 0`` are held at their value in ``x0`` (their
    row and column of the system are replaced by the identity).

    Converged when the scaled step falls below ``tol``.  Fills ``x_out`` (7)
    and ``gauss_out`` (7, 7; the Gauss-Newton matrix of ALL seven parameters
    at the solution) and returns ``(cost, n_iter, converged)``.  Without
    horizon rows the cost is convex and the minimum is the global one; with
    horizon rows it is not convex and the minimum found is a LOCAL one.
    """
    n_lin = rows.shape[0]
    n_h = hz.shape[0]
    m = n_lin + n_h
    x = x0.copy()
    r = np.empty(m)
    jac = np.empty((m, _NPAR))
    second = np.empty(m)
    r_new = np.empty(m)
    jac_new = np.empty((m, _NPAR))
    second_new = np.empty(m)
    x_new = np.empty(_NPAR)
    grad = np.empty(_NPAR)
    hess = np.empty((_NPAR, _NPAR))
    gauss = np.empty((_NPAR, _NPAR))
    work = np.empty((_NPAR, _NPAR))
    rhs = np.empty(_NPAR)
    step = np.empty(_NPAR)
    outlier_prev = np.zeros(m, dtype=np.uint8)
    have_prev = False

    _fit_residuals(x, rows, targets, one_sided, hz, hpar, r, jac, second)
    cost = _fit_cost(x, r, prior_w, huber_k)
    lam = lam0
    converged = False
    n_iter = 0
    for it in range(1, max_iter + 1):
        n_iter = it
        # ---- same outlier set as at the previous iterate? -> exact Hessian
        exact = have_prev
        for i in range(m):
            flag = 1 if abs(r[i]) > huber_k else 0
            if flag != outlier_prev[i]:
                exact = False
            outlier_prev[i] = flag
        have_prev = True
        # ---- gradient, Gauss-Newton matrix, iteration matrix
        _fit_gauss(r, jac, prior_w, huber_k, gauss)
        for a in range(_NPAR):
            grad[a] = prior_w[a] * x[a]
            for b in range(_NPAR):
                hess[a, b] = 0.0 if exact else gauss[a, b]
            if exact:
                hess[a, a] = prior_w[a]
        for i in range(m):
            ri = r[i]
            psi = ri
            if psi > huber_k:
                psi = huber_k
            elif psi < -huber_k:
                psi = -huber_k
            for a in range(_NPAR):
                grad[a] += jac[i, a] * psi
            if exact and abs(ri) <= huber_k:
                for a in range(_NPAR):
                    ja = jac[i, a]
                    if ja != 0.0:
                        for b in range(_NPAR):
                            hess[a, b] += ja * jac[i, b]
            if second[i] != 0.0:
                k = i - n_lin
                ct = hz[k, 1]
                st = hz[k, 2]
                wq = psi * second[i]
                q0 = ct * ct
                q1 = 2.0 * st * ct
                q2 = st * st
                hess[2, 2] += wq * q0 * q0
                hess[2, 3] += wq * q0 * q1
                hess[2, 4] += wq * q0 * q2
                hess[3, 2] += wq * q1 * q0
                hess[3, 3] += wq * q1 * q1
                hess[3, 4] += wq * q1 * q2
                hess[4, 2] += wq * q2 * q0
                hess[4, 3] += wq * q2 * q1
                hess[4, 4] += wq * q2 * q2
        for a in range(_NPAR):
            if free[a] == 0:  # held: unit row and column, no step
                grad[a] = 0.0
                for b in range(_NPAR):
                    hess[a, b] = 0.0
                    hess[b, a] = 0.0
                hess[a, a] = 1.0
        # ---- damped step
        accepted = False
        small = False
        while lam <= 1e12:
            for a in range(_NPAR):
                rhs[a] = -grad[a]
                for b in range(_NPAR):
                    work[a, b] = hess[a, b]
                if free[a] != 0:
                    work[a, a] += lam * gauss[a, a]
            if not _chol_solve(work, rhs, _NPAR, step):  # not positive definite: damp harder
                lam *= 10.0
                continue
            biggest = 0.0
            for a in range(_NPAR):
                rel = abs(step[a]) / scale[a]
                if rel > biggest:
                    biggest = rel
                x_new[a] = x[a] + step[a]
            small = biggest < tol
            _fit_residuals(x_new, rows, targets, one_sided, hz, hpar, r_new, jac_new, second_new)
            cost_new = _fit_cost(x_new, r_new, prior_w, huber_k)
            if cost_new <= cost:
                for a in range(_NPAR):
                    x[a] = x_new[a]
                for i in range(m):
                    r[i] = r_new[i]
                    second[i] = second_new[i]
                    for a in range(_NPAR):
                        jac[i, a] = jac_new[i, a]
                cost = cost_new
                lam = lam * 0.1
                if lam < 1e-12:
                    lam = 1e-12
                accepted = True
                break
            if small:  # at the minimum to rounding: keep the better point
                break
            lam *= 10.0
        if small:
            converged = True
            break
        if not accepted:
            break
    _fit_gauss(r, jac, prior_w, huber_k, gauss_out)
    for a in range(_NPAR):
        x_out[a] = x[a]
    return cost, n_iter, converged


class _Problem:
    """Residuals of one patch fit (all normalised by their sigma).

    Data residuals, in this order: tilt-x and tilt-y of every placement,
    hole heights (two-sided or one-sided), horizon samples.  The Gaussian
    priors are kept apart because they are not robustified.
    """

    def __init__(self, distance: float, prior_sigma: np.ndarray, huber_k: float):
        self.distance = distance
        self.rows: List[np.ndarray] = []
        self.targets: List[float] = []
        self.one_sided: List[bool] = []
        self.prior_w = 1.0 / (prior_sigma * prior_sigma)
        self.huber_k = float(huber_k)
        self.hz = np.zeros((0, 3))
        self.hpar = np.zeros(4)
        self._lin = None

    def add_linear(self, row, target: float, sigma: float, one_sided: bool = False) -> None:
        """Residual ``(row . x - target) / sigma``; one-sided = only its
        positive part counts (an upper bound on ``row . x``)."""
        self.rows.append(np.asarray(row, dtype=float) / sigma)
        self.targets.append(target / sigma)
        self.one_sided.append(one_sided)
        self._lin = None

    def set_horizon(self, theta, tan_elev, sigma: float, h_cam: float, d_min: float, far_limit: float) -> None:
        theta = np.asarray(theta, dtype=float)
        self.hz = np.ascontiguousarray(np.column_stack([np.asarray(tan_elev, dtype=float), np.cos(theta), np.sin(theta)]))
        self.hpar = np.array([sigma, h_cam, d_min, far_limit], dtype=float)

    @property
    def n_linear(self) -> int:
        return len(self.rows)

    def _linear(self):
        if self._lin is None:
            self._lin = (
                np.ascontiguousarray(np.array(self.rows, dtype=float).reshape(-1, _NPAR)),
                np.array(self.targets, dtype=float),
                np.array(self.one_sided, dtype=np.uint8),
            )
        return self._lin

    def data(self, x: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Data residuals ``r`` (m,), their Jacobian (m, 7) and the second
        derivative of each residual with respect to its ray curvature."""
        rows, targets, one_sided = self._linear()
        m = rows.shape[0] + self.hz.shape[0]
        r = np.empty(m)
        jac = np.empty((m, _NPAR))
        second = np.empty(m)
        _fit_residuals(np.asarray(x, dtype=float), rows, targets, one_sided, self.hz, self.hpar, r, jac, second)
        return r, jac, second

    def cost(self, x: np.ndarray) -> float:
        x = np.asarray(x, dtype=float)
        return float(_fit_cost(x, self.data(x)[0], self.prior_w, self.huber_k))

    def gradient(self, x: np.ndarray) -> np.ndarray:
        """Gradient of the robust MAP cost (for the tests)."""
        x = np.asarray(x, dtype=float)
        r, jac, _ = self.data(x)
        return jac.T @ np.clip(r, -self.huber_k, self.huber_k) + self.prior_w * x

    def minimise(self, x0: np.ndarray, config: "EstimatorConfig", *, horizon: bool = True, free: np.ndarray = None):
        """One Levenberg-Marquardt run from ``x0``: ``(x, gauss, n_iter, converged, cost)``.

        ``horizon=False`` leaves the horizon rows out (the convex Quick-Read
        problem); ``free`` (7 flags, default all 1) marks the parameters
        that may move - the others keep their values in ``x0``.  ``gauss``
        is the Gauss-Newton matrix of all seven parameters at the solution.
        """
        rows, targets, one_sided = self._linear()
        x = np.empty(_NPAR)
        gauss = np.empty((_NPAR, _NPAR))
        cost, n_iter, converged = _fit_lm(
            np.asarray(x0, dtype=float), _FREE_ALL if free is None else free, rows, targets, one_sided,
            self.hz if horizon else _NO_HORIZON, self.hpar, self.prior_w, self.huber_k,
            _SCALE, int(config.lm_max_iter), float(config.lm_tol), float(config.lm_lambda0), x, gauss,
        )
        return x, gauss, int(n_iter), bool(converged), float(cost)


def _cross_sigma_read(distance: float, stations: Sequence[float], sigmas: Sequence[float], config: EstimatorConfig) -> float:
    """1-sigma of the mean cross slope ``b + 0.5 d D`` from cross-tilt
    readings at ``stations`` with 1-sigma errors ``sigmas`` [rad].

    Bayesian straight-line fit ``tilt_y(s) = b + d s`` with the weak slope
    prior on ``b`` and the CONFIDENCE prior on the twist ``d``:
    ``sigma_d = conf_twist_sigma / sqrt(1 + (D / conf_twist_length)^2)``.
    For one placement at the ball this is
    ``sqrt(sigma_tilt^2 + (0.5 D sigma_d)^2)``: the reading error plus how
    far the slope at the ball is expected to differ from the average along
    the line.
    """
    sigma_d = config.conf_twist_sigma / math.sqrt(1.0 + (distance / config.conf_twist_length) ** 2)
    n00 = 1.0 / config.sigma_slope_prior**2
    n01 = 0.0
    n11 = 1.0 / sigma_d**2
    for station, sig in zip(stations, sigmas):
        w = 1.0 / (sig * sig)
        n00 += w
        n01 += w * station
        n11 += w * station * station
    det = n00 * n11 - n01 * n01
    v_b = n11 / det
    v_d = n00 / det
    v_bd = -n01 / det
    return math.sqrt(max(v_b + distance * v_bd + 0.25 * distance * distance * v_d, 0.0))


def _tilt_only_fit(meas: Measurements, config: EstimatorConfig, *, bearing: float, distance: float,
                   distance_sigma: float, rng_est: RangeEstimate, flag_missing: bool,
                   range_missing: bool = False) -> PatchFit:
    """Plane from the puck tilt alone (method B0 and the fallbacks)."""
    a_t, b_t = _rotate_to(meas.tilt, bearing)
    sig = _tilt_sigma(meas, config)
    cov = np.diag([sig**2, sig**2, config.sigma_curv**2, config.sigma_curv**2, config.sigma_curv**2])
    return PatchFit(
        coeffs=np.array([a_t, b_t, 0.0, 0.0, 0.0]),
        cov=cov,
        level_offsets=np.zeros(2),
        distance=distance,
        distance_sigma=distance_sigma,
        bearing=bearing,
        range=rng_est,
        tilt_slopes=np.array([a_t, b_t]),
        cross_sigma_read=_cross_sigma_read(distance, (0.0,), (sig,), config),
        n_drops=1,
        stations=(0.0,),
        base_hidden=False,
        flag_missing=flag_missing,
        range_missing=range_missing,
        used_horizon=False,
        poor_horizon=False,
        horizon_rms=math.nan,
        n_iter=0,
        converged=True,
        cost=0.0,
        cost_first_start=0.0,
        n_starts=0,
    )


def fit_patch(
    drops: Union[Measurements, Sequence[Measurements]],
    method: str = DEFAULT_METHOD,
    config: EstimatorConfig = EstimatorConfig(),
    *,
    start: Optional[Sequence[float]] = None,
) -> PatchFit:
    """Fit the quadratic patch to one placement or to the drops of a Survey.

    Parameters
    ----------
    drops : Measurements or sequence of Measurements
        The first one is the placement at the ball; it defines the putt
        frame, the distance, and supplies the horizon.  Further ones are
        Survey drops along the line; each contributes its tilt at the
        station ``s_i = D - range_i`` and its own hole height.  Drops whose
        flag was not found are ignored.
    method : ``"B0"``, ``"B1"`` or ``"B2"``
    config : EstimatorConfig
    start : (7,) sequence, optional
        Starting point ``(a, b, c, d, e, pitch offset, roll offset)`` of the
        iteration INSTEAD of the firmware's start(s); a single run is made
        from it.  In the anchored horizon fit ``a``, ``b`` and ``c`` of the
        start are ignored (they are held at the Quick-Read solution).  Only
        for checking that the minimum found does not depend on the start.

    Returns
    -------
    PatchFit

    The fit (see the module docstring)
    ----------------------------------
    ``B1``: one Levenberg-Marquardt run from the tilt plane.  The cost is
    convex, so the minimum is the MAP estimate whatever the start.

    ``B2`` (default, anchored): first the ``B1`` fit; then ``a``, ``b`` and
    ``c`` are held at its solution and ``d``, ``e``, a common-mode
    silhouette offset and the roll offset are fitted to the horizon rows and
    the priors, from the ``B1`` solution and from 4 further starts
    (``d, e = +-0.003`` 1/m in every sign combination); the lowest minimum
    is kept.

    ``B2`` with ``config.horizon_joint``: all seven parameters fitted
    jointly to all rows, from the tilt plane and (``config.multi_start``) 24
    further starts; the lowest minimum is kept.  This is the literal joint
    MAP problem; its cost has many local minima (see the tests and the
    report) and is kept for comparison only.
    """
    if method not in ("B0", "B1", "B2"):
        raise ValueError("fit_patch method must be 'B0', 'B1' or 'B2'")
    if isinstance(drops, Measurements):
        drops = (drops,)
    if len(drops) == 0:
        raise ValueError("need at least one placement")
    first = drops[0]
    rng_first = fuse_range(first, config)

    # ---- no usable flag, or no usable range: tilt-only plane -------------------
    have_bearing = bool(first.flag_found and math.isfinite(first.flag_bearing))
    if not (have_bearing and rng_first.valid):
        if math.isfinite(first.user_distance) and first.user_distance > 0.0:
            dist = float(first.user_distance)
        else:
            dist = config.default_distance
        if have_bearing:
            # the flag was found but could not be ranged: its bearing (about
            # 1 mrad) is still far better than the visor axis
            return _tilt_only_fit(first, config, bearing=float(first.flag_bearing), distance=dist,
                                  distance_sigma=math.nan, rng_est=rng_first, flag_missing=False, range_missing=True)
        return _tilt_only_fit(first, config, bearing=0.0, distance=dist, distance_sigma=math.nan,
                              rng_est=rng_first, flag_missing=True)

    bearing = float(first.flag_bearing)
    dist = rng_first.distance
    if method == "B0":
        return _tilt_only_fit(first, config, bearing=bearing, distance=dist, distance_sigma=rng_first.sigma,
                              rng_est=rng_first, flag_missing=False)

    # ---- assemble the residuals ----------------------------------------------------
    prior_sigma = np.array([
        config.sigma_slope_prior, config.sigma_slope_prior,
        config.sigma_curv, config.sigma_curv, config.sigma_curv,
        config.sigma_level, config.sigma_level,
    ])
    anchored = method == "B2" and not config.horizon_joint
    if anchored and not config.horizon_free_c:
        # the common-mode height of the silhouette is a nuisance of its own
        prior_sigma[5] = math.hypot(config.sigma_level, config.sigma_silhouette)
    problem = _Problem(dist, prior_sigma, config.huber_k)
    # placements that can be located on the line (the first one always can)
    located: List[Tuple[Measurements, RangeEstimate, float]] = [(first, rng_first, 0.0)]
    for drop in drops[1:]:
        rng_i = fuse_range(drop, config)
        if drop.flag_found and rng_i.valid and math.isfinite(drop.flag_bearing):
            located.append((drop, rng_i, min(max(dist - rng_i.distance, 0.0), dist)))
    sigma_field = config.sigma_field if len(located) > 1 else 0.0

    stations: List[float] = []
    cross_sigmas: List[float] = []
    base_hidden = False
    a0 = b0 = 0.0
    for i, (drop, rng_i, station) in enumerate(located):
        stations.append(station)
        # tilt, rotated into this drop's own "toward the hole" frame
        a_t, b_t = _rotate_to(drop.tilt, float(drop.flag_bearing))
        if i == 0:
            a0, b0 = a_t, b_t
        sig_t = math.hypot(_tilt_sigma(drop, config), sigma_field)
        sig_x = sig_y = sig_t
        if i > 0:
            # A drop placed by eye lies an unknown distance off the ball->hole
            # line, so its "toward the hole" frame is rotated against the putt
            # frame by about (lateral offset) / (distance to the hole).  That
            # mixes the two slope components: cross-talk of the along slope
            # into the cross tilt, and vice versa.
            rot = config.sigma_drop_lateral / max(rng_i.distance, 0.3)
            sig_x = math.hypot(sig_t, rot * b_t)
            sig_y = math.hypot(sig_t, rot * a_t)
        cross_sigmas.append(sig_y)
        problem.add_linear([1.0, 0.0, station, 0.0, 0.0, 0.0, 0.0], a_t, sig_x)
        problem.add_linear([0.0, 1.0, 0.0, station, 0.0, 0.0, 0.0], b_t, sig_y)
        # hole height above this drop
        if config.use_flag_base and math.isfinite(drop.flag_low_elev):
            h_lens = drop.h_cam - config.sink_mean
            dz = h_lens + rng_i.distance * math.tan(drop.flag_low_elev)
            sig_e = math.hypot(config.sigma_pixel_elev / drop.f_px, config.sigma_level)
            sig_z = math.sqrt(
                (rng_i.distance * sig_e) ** 2 + config.sink_sigma**2 + (0.5 * config.sigma_mirage * rng_i.distance**2) ** 2
            )
            if i > 0:  # a partial rise: the model need not reproduce it better than sigma_field
                sig_z = math.hypot(sig_z, sigma_field * (dist - station))
            hidden = not (drop.flag_base_visible or config.assume_base_visible)
            if i == 0:
                base_hidden = hidden
            row = [dist - station, 0.0, 0.5 * (dist * dist - station * station), 0.0, 0.0, 0.0, 0.0]
            problem.add_linear(row, dz, sig_z, one_sided=hidden)

    used_horizon = False
    n_linear = problem.n_linear
    if method == "B2" and first.horizon_az.size > 0:
        valid = np.isfinite(first.horizon_elev)
        if int(valid.sum()) >= 5:
            problem.set_horizon(
                first.horizon_az[valid] - bearing,
                np.tan(first.horizon_elev[valid]),
                config.sigma_horizon,
                first.h_cam - config.sink_mean,
                config.horizon_d_min,
                horizon_far_limit(dist, config),
            )
            used_horizon = True

    x_tilt = np.zeros(_NPAR)
    x_tilt[0] = a0
    x_tilt[1] = b0
    if start is not None:
        x_user = np.asarray(start, dtype=float).copy()
        if x_user.shape != (_NPAR,) or not np.all(np.isfinite(x_user)):
            raise ValueError("start must be 7 finite numbers")

    if not used_horizon:
        # convex problem: one run, the same minimum from any start
        x, gauss, n_iter, converged, cost = problem.minimise(x_tilt if start is None else x_user, config, horizon=False)
        cost_first = cost
        n_starts = 1
        cov = np.linalg.inv(gauss)[:5, :5]
    elif config.horizon_joint:
        # joint fit of all seven parameters (non-convex)
        x, gauss, n_iter, converged, cost = problem.minimise(x_tilt if start is None else x_user, config)
        cost_first = cost
        n_starts = 1
        if start is None and config.multi_start:
            for x_alt in _corner_starts(x_tilt, _START_CURVATURES_JOINT):
                n_starts += 1
                cand = problem.minimise(x_alt, config)
                if cand[4] < cost - _COST_TIE * (1.0 + cost):
                    x, gauss, n_iter, converged, cost = cand
        cov = np.linalg.inv(gauss)[:5, :5]
    else:
        # anchored fit: what the Quick Read measures directly is held, the horizon adds the rest
        x_quick, gauss_quick, _, conv_quick, _ = problem.minimise(x_tilt, config, horizon=False)
        if config.horizon_free_c:
            n_held, free, corners = 2, _FREE_CURVATURES, _corner_starts(x_quick, _START_CURVATURES_ANCHORED)
        else:
            n_held, free = 3, _FREE_TWIST
            corners = [x for x in _corner_starts(x_quick, _START_CURVATURES_ANCHORED) if x[2] > 0.0]
            for x_alt in corners:
                x_alt[2] = x_quick[2]
        if start is None:
            x_first = x_quick
        else:
            x_first = x_user
            x_first[:n_held] = x_quick[:n_held]
        x, gauss, n_iter, converged, cost = problem.minimise(x_first, config, free=free)
        cost_first = cost
        n_starts = 1
        if start is None and config.multi_start:
            for x_alt in corners:
                n_starts += 1
                cand = problem.minimise(x_alt, config, free=free)
                if cand[4] < cost - _COST_TIE * (1.0 + cost):
                    x, gauss, n_iter, converged, cost = cand
        converged = bool(converged and conv_quick)
        # two-stage covariance: the held parameters as in the Quick Read; the
        # rest follows them through the conditional fit
        # (theta_2 = -G22^-1 G21 theta_1 + ...)
        cov_held = np.linalg.inv(gauss_quick)[:n_held, :n_held]
        cond = np.linalg.inv(gauss[n_held:, n_held:])
        gain = -cond @ gauss[n_held:, :n_held]
        full = np.empty((_NPAR, _NPAR))
        full[:n_held, :n_held] = cov_held
        full[n_held:, :n_held] = gain @ cov_held
        full[:n_held, n_held:] = full[n_held:, :n_held].T
        full[n_held:, n_held:] = cond + gain @ cov_held @ gain.T
        cov = full[:5, :5]

    poor_horizon = False
    horizon_rms = math.nan
    if used_horizon:
        r_h = problem.data(x)[0][n_linear:]
        horizon_rms = float(np.sqrt(np.mean(r_h * r_h)))
        poor_horizon = bool(np.mean(np.abs(r_h) > config.huber_k) > config.poor_horizon_fraction)

    return PatchFit(
        coeffs=x[:5].copy(),
        cov=cov.copy(),
        level_offsets=x[5:].copy(),
        distance=dist,
        distance_sigma=rng_first.sigma,
        bearing=bearing,
        range=rng_first,
        tilt_slopes=np.array([a0, b0]),
        cross_sigma_read=_cross_sigma_read(dist, stations, cross_sigmas, config),
        n_drops=len(stations),
        stations=tuple(stations),
        base_hidden=bool(base_hidden and config.use_flag_base),
        flag_missing=False,
        range_missing=False,
        used_horizon=used_horizon,
        poor_horizon=poor_horizon,
        horizon_rms=horizon_rms,
        n_iter=n_iter,
        converged=converged,
        cost=cost,
        cost_first_start=cost_first,
        n_starts=n_starts,
    )


# --------------------------------------------------------------------------
# The estimate
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Estimate:
    """What the device shows for one read (all SI, radians).

    Attributes
    ----------
    method : str
    phi : float [rad]
        Aim angle relative to the line to the hole, positive = aim left.
    aim_azimuth_device : float [rad]
        The aim line in the device frame (``bearing + phi``): this is what
        the display draws.
    v0 : float [m/s]
        Launch speed.
    plays_like : float [m]
        Flat-green distance with the same launch speed, ``v0^2 / (2 a_r)``.
    break_m : float [m];  break_cups : float
        Lateral offset of the aim line at the hole, ``D tan(phi)`` (+ = aim
        left of the hole), in metres and in cup widths (108 mm).
    distance : float [m];  distance_sigma : float [m]
        Distance to the hole used, and its 1-sigma uncertainty (NaN unknown).
    bearing : float [rad]
        Direction of the hole in the device frame.
    slope_pct : float [%]
        Slope magnitude at the ball, from the tilt reading of the placement
        at the ball (``PatchFit.tilt_slopes``): the direct measurement, not
        the fitted patch.
    fall_line_azimuth : float [rad]
        Direction of steepest descent at the ball in the putt frame (CCW
        from the direction to the hole), from the same tilt reading.
    fall_line_azimuth_device : float [rad]
        The same in the device frame.
    dz_hole : float [m]
        Fitted height of the hole above the ball, ``a D + 0.5 c D^2``.
    patch : (5,) array ``(a, b, c, d, e)`` (putt frame);  patch_cov : (5, 5)
    cross_slope_sigma : float [m/m]
        1-sigma of the mean cross slope along the line as known from the
        tilt readings (``PatchFit.cross_sigma_read``): reading error plus
        the expected difference between the sampled and the path-average
        slope.  The horizon never tightens it.
    confidence : float in [0, 1]
        ``erf(HOLE_R / (sqrt(2) sigma_lat))`` - the probability that the
        read error alone leaves the ball inside the hole's width, where
        ``sigma_lat`` is the lateral 1-sigma at the hole implied by
        ``cross_slope_sigma``, by the grain the solve does not know about
        and (flag missing) by the hand-pointing error - multiplied by the
        factors for the raised flags.  See :func:`_confidence`.
    base_hidden, flag_missing, range_missing, poor_horizon : bool
    aim_source : int
        0 solved on the fitted patch; 1 patch not solvable, solved on its
        secant plane; 2 best iterate of that solve; 3 straight at flat pace.
    solve_status : int
        :class:`~greenline_sim.physics.SolveStatus` of the solve that
        produced the aim (``OK`` for ``STRAIGHT``).
    a_r : float [m/s^2];  stimp_ft : float [ft]
        Green speed used.
    grain : (2,) array
        Grain ``kappa * g_hat`` used, in the putt frame.
    fit : PatchFit or None
        Full fit record (None for ``STRAIGHT``).
    """

    method: str
    phi: float
    aim_azimuth_device: float
    v0: float
    plays_like: float
    break_m: float
    break_cups: float
    distance: float
    distance_sigma: float
    bearing: float
    slope_pct: float
    fall_line_azimuth: float
    fall_line_azimuth_device: float
    dz_hole: float
    patch: np.ndarray
    patch_cov: np.ndarray
    cross_slope_sigma: float
    confidence: float
    base_hidden: bool
    flag_missing: bool
    range_missing: bool
    poor_horizon: bool
    aim_source: int
    solve_status: int
    a_r: float
    stimp_ft: float
    grain: np.ndarray
    fit: Optional[PatchFit]


def _wrap(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


def _pace_factor(distance: float, past: float) -> float:
    """Reduction of the small-slope break angle by firm pace:
    ``F = 1 + rho^2 ln(rho^2) / (1 - rho^2)`` with ``rho^2 = past / (D + past)``
    (see :func:`greenline_sim.physics.planar_break_angle_paced`)."""
    if past <= 0.0:
        return 1.0
    rho2 = past / (distance + past)
    return 1.0 + rho2 * math.log(rho2) / (1.0 - rho2)


def _confidence(fit: PatchFit, a_r: float, kappa_used: float, aim_source: int, config: EstimatorConfig) -> Tuple[float, float]:
    """Confidence score and the 1-sigma of the mean cross slope it rests on.

    The lateral error at the hole is modelled from what the read cannot
    know, in the small-slope break formula ``phi = F / 2 * (cross drive) /
    a_r`` (``F`` = pace factor):

    * the mean cross slope along the line, known to ``fit.cross_sigma_read``
      (tilt reading error, and how far a local sample is expected to be from
      the path average; several drops and a spin read tighten it, the
      horizon does not);
    * the cross-line grain: ``conf_grain_kappa`` when the grain is not used,
      ``conf_grain_rel * kappa_used`` when it is;
    * the hand-pointing error when the flag is missing.

    ``confidence = erf(HOLE_R / (sqrt(2) D sigma_phi))`` times the factors
    of the raised flags.  The constants were calibrated on the simulator's
    synthetic greens; the score is a ranking aid, not a measured probability.
    """
    dist = fit.distance
    sigma_cross = fit.cross_sigma_read
    sigma_kappa = config.conf_grain_rel * kappa_used if config.use_grain else config.conf_grain_kappa
    sigma_phi = 0.5 * _pace_factor(dist, config.past) * math.hypot(ROLL_FACTOR * G * sigma_cross / a_r, sigma_kappa)
    if fit.flag_missing:
        sigma_phi = math.hypot(sigma_phi, config.sigma_hand_bearing)
    sigma_lat = dist * sigma_phi
    conf = math.erf(HOLE_R / (math.sqrt(2.0) * sigma_lat)) if sigma_lat > 0.0 else 1.0
    if fit.base_hidden:
        conf *= config.conf_base_hidden
    if fit.flag_missing:
        conf *= config.conf_flag_missing
    if fit.range_missing:
        conf *= config.conf_range_missing
    if fit.poor_horizon:
        conf *= config.conf_poor_horizon
    if aim_source != AIM_FROM_PATCH:
        conf *= config.conf_aim_fallback
    return min(max(conf, 0.0), 1.0), sigma_cross


def estimate_batch(
    items: Sequence[Union[Measurements, Sequence[Measurements]]],
    method: str = DEFAULT_METHOD,
    config: EstimatorConfig = EstimatorConfig(),
) -> List[Estimate]:
    """Estimate many reads at once (same results as one call per read).

    Parameters
    ----------
    items : sequence
        Each element is a :class:`Measurements` (one placement) or a
        sequence of them (the drops of a Survey, ball first).
    method : one of :data:`METHODS`
    config : EstimatorConfig

    Returns
    -------
    list of Estimate, one per item.

    The patch fits run one after another; the aim solves run as one batch
    (:func:`~greenline_sim.physics.solve_aim_quadratic_batch`).
    """
    if method not in METHODS:
        raise ValueError(f"unknown method {method!r}; choose from {METHODS}")
    n = len(items)
    if n == 0:
        return []
    fit_method = "B0" if method == "STRAIGHT" else method
    fits: List[PatchFit] = []
    firsts: List[Measurements] = []
    for item in items:
        drops = (item,) if isinstance(item, Measurements) else tuple(item)
        if len(drops) == 0 or not all(isinstance(d, Measurements) for d in drops):
            raise TypeError("every item must be a Measurements or a non-empty sequence of Measurements")
        fits.append(fit_patch(drops, fit_method, config))
        firsts.append(drops[0])

    dist = np.array([f.distance for f in fits])
    stimp = np.array([min(max(m.stimp_ft, config.stimp_min), config.stimp_max) for m in firsts])
    a_r = np.asarray(stimp_to_decel(stimp), dtype=float).reshape(n)
    grain = np.zeros((n, 2))
    if config.use_grain:
        for i, (m, f) in enumerate(zip(firsts, fits)):
            if math.isfinite(m.grain_kappa) and math.isfinite(m.grain_azimuth):
                kappa = min(max(m.grain_kappa, 0.0), config.grain_kappa_max)
                az = m.grain_azimuth - f.bearing
                grain[i, 0] = kappa * math.cos(az)
                grain[i, 1] = kappa * math.sin(az)

    phi = np.zeros(n)
    v0 = np.sqrt(2.0 * a_r * (dist + config.past))  # flat-green pace
    source = np.full(n, AIM_STRAIGHT, dtype=int)
    status = np.full(n, int(SolveStatus.OK), dtype=int)

    if method != "STRAIGHT":
        coeffs = np.array([f.coeffs for f in fits]).reshape(n, 5)
        kwargs = dict(tol_miss=config.tol_miss, tol_pace=config.tol_pace)
        sol = solve_aim_quadratic_batch(coeffs, dist, a_r, grain, config.past, **kwargs)
        good = sol.usable
        phi[good] = sol.phi[good]
        v0[good] = sol.v0[good]
        source[good] = AIM_FROM_PATCH
        status[:] = sol.status
        bad = np.nonzero(~good)[0]
        if bad.size:
            # secant plane of the patch: keeps the hole height and the mean cross slope
            plane = np.zeros((bad.size, 5))
            plane[:, 0] = coeffs[bad, 0] + 0.5 * coeffs[bad, 2] * dist[bad]
            plane[:, 1] = coeffs[bad, 1] + 0.5 * coeffs[bad, 3] * dist[bad]
            sol2 = solve_aim_quadratic_batch(plane, dist[bad], a_r[bad], grain[bad], config.past, **kwargs)
            for j, i in enumerate(bad):
                status[i] = int(sol2.status[j])
                if sol2.usable[j]:
                    phi[i], v0[i], source[i] = sol2.phi[j], sol2.v0[j], AIM_FROM_PLANE
                elif math.isfinite(sol2.phi[j]) and math.isfinite(sol2.v0[j]) and sol2.v0[j] > 0.0:
                    phi[i], v0[i], source[i] = sol2.phi[j], sol2.v0[j], AIM_BEST_EFFORT
                # else: keep straight at flat pace (AIM_STRAIGHT)

    out: List[Estimate] = []
    for i, (m, f) in enumerate(zip(firsts, fits)):
        a, c = float(f.coeffs[0]), float(f.coeffs[2])
        if method == "STRAIGHT":
            conf, sigma_cross = 0.0, math.nan
            fit_out = None
        else:
            conf, sigma_cross = _confidence(f, float(a_r[i]), float(np.hypot(grain[i, 0], grain[i, 1])), int(source[i]), config)
            fit_out = f
        # slope and fall line at the ball: the tilt reading itself
        t_x, t_y = float(f.tilt_slopes[0]), float(f.tilt_slopes[1])
        slope = math.hypot(t_x, t_y)
        fall = math.atan2(-t_y, -t_x) if slope > 0.0 else 0.0
        brk = float(dist[i] * math.tan(phi[i]))
        out.append(
            Estimate(
                method=method,
                phi=float(phi[i]),
                aim_azimuth_device=_wrap(f.bearing + float(phi[i])),
                v0=float(v0[i]),
                plays_like=float(v0[i] * v0[i] / (2.0 * a_r[i])),
                break_m=brk,
                break_cups=brk / (2.0 * HOLE_R),
                distance=float(dist[i]),
                distance_sigma=float(f.distance_sigma),
                bearing=float(f.bearing),
                slope_pct=100.0 * slope,
                fall_line_azimuth=fall,
                fall_line_azimuth_device=_wrap(fall + f.bearing),
                dz_hole=a * float(dist[i]) + 0.5 * c * float(dist[i]) ** 2,
                patch=f.coeffs.copy(),
                patch_cov=f.cov.copy(),
                cross_slope_sigma=sigma_cross,
                confidence=conf,
                base_hidden=f.base_hidden,
                flag_missing=f.flag_missing,
                range_missing=f.range_missing,
                poor_horizon=f.poor_horizon,
                aim_source=int(source[i]),
                solve_status=int(status[i]),
                a_r=float(a_r[i]),
                stimp_ft=float(stimp[i]),
                grain=grain[i].copy(),
                fit=fit_out,
            )
        )
    return out


def estimate(
    meas: Measurements,
    method: str = DEFAULT_METHOD,
    config: EstimatorConfig = EstimatorConfig(),
) -> Estimate:
    """Estimate the putt from ONE placement of the marker.

    Parameters
    ----------
    meas : Measurements
        The only data input.  (A spin-and-reread measurement, with
        ``tilt_reads == 2``, makes this the Precision Read.)
    method : one of :data:`METHODS`
    config : EstimatorConfig

    Returns
    -------
    Estimate
    """
    if not isinstance(meas, Measurements):
        raise TypeError("estimate() takes a Measurements object")
    return estimate_batch([meas], method, config)[0]


def estimate_survey(
    drops: Sequence[Measurements],
    config: EstimatorConfig = EstimatorConfig(),
    method: str = "B1",
) -> Estimate:
    """Estimate the putt from the drops of a Survey (ball first).

    The slope field along the line is plane-plus-curvature:
    ``dz/dx = a + c s``, ``dz/dy = b + d s`` at station ``s``, fitted to the
    tilt of every drop together with each drop's hole height.
    """
    drops = tuple(drops)
    if len(drops) == 0 or not all(isinstance(d, Measurements) for d in drops):
        raise TypeError("estimate_survey() takes a non-empty sequence of Measurements")
    return estimate_batch([drops], method, config)[0]
