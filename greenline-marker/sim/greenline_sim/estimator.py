"""The GreenLine estimator: reference for the embedded firmware.

Input: :class:`~greenline_sim.measurements.Measurements` (one placement of
the marker, or several for a Survey) and nominal constants
(:class:`EstimatorConfig`).  Output: an :class:`Estimate` - the aim line the
display draws, the launch speed, the "plays-like" distance, the break, the
slope at the ball and a confidence score.

NOTHING in this module may look at the true green.  It imports the physics
solver and the ``Measurements`` record only (a test enforces this).

Method
------
All work is done in the PUTT FRAME: origin at the marker (the ball), ``+x``
toward the hole along the measured flag bearing, ``+y`` to the left.  The
green around the putt is modelled as the quadratic patch

    z(x, y) = a x + b y + 0.5 (c x^2 + 2 d x y + e y^2)

and ``p = (a, b, c, d, e)`` is found as the MAP estimate (Levenberg-Marquardt
on Huber-robustified, sigma-normalised residuals) from

* **tilt** of each placement at station ``s_i`` on the line:
  ``a + c s_i = tilt_x``, ``b + d s_i = tilt_y``  (sigma: seating noise);
* **hole height** from the lowest visible point of the flagstick, when its
  base is visible: ``a (D - s_i) + 0.5 c (D^2 - s_i^2) = h_cam + D_i tan(elev)``
  (tight); when the base is hidden behind a crest only the one-sided bound
  "the hole is LOWER than that sight line" is used;
* **turf horizon** (method B2 only): ``tan(elev_k) = E(theta_k; p)`` with the
  exact forward model of a quadratic seen from height ``h``
  (:func:`quad_horizon`), plus two nuisance offsets (pitch and roll) for the
  level reference of the cameras, each with the prior ``sigma_level``.  (A
  wide prior on the common offset - to absorb the unknown height of whatever
  forms the silhouette - was tried and made B2 worse in every geometry
  tested: with the level pinned, a silhouette that sits at the wrong height
  shows up as Huber outliers and loses influence.)
* **priors**: curvatures ``c, d, e ~ N(0, 0.004 1/m)``, weak priors on
  ``a, b``.

Then the putt is solved on the fitted patch with the entered green speed and
the measured grain (:func:`greenline_sim.physics.solve_aim_quadratic_batch`).

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
``B1``        Quick Read: tilt + flag-base height (MAP fit, no horizon).
              With a spin-and-reread measurement (``tilt_reads == 2``) this is
              the Precision Read; with several placements it is the Survey.
``B2``        B1 + turf-horizon residuals.

If the flagstick was not found the estimator falls back to the tilt-only
plane along the visor axis, with the dialled (or a default) distance, and
flags low confidence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple, Union

import numpy as np

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
residuals of ``B2`` help when the ground beyond the collar continues the
green or falls away smoothly, and hurt when the surrounds carry mounds that
are independent of the green.  The sign of the effect therefore depends on a
property of the course that the device cannot sense and that the simulator
can only assume, so ``B2`` stays an option and is not the default."""

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
        Use the measured grain (False = solve without grain).
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
    tol_miss, tol_pace : float [m]
        Tolerances of the aim solver.
    poor_horizon_fraction : float
        Fraction of horizon samples beyond the Huber threshold above which
        the horizon is flagged as poor.
    conf_base_hidden, conf_flag_missing, conf_poor_horizon, conf_aim_fallback : float
        Multipliers applied to the confidence score when the corresponding
        flag is raised.
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
    sigma_horizon: float = 1.0e-3
    huber_k: float = 1.5
    horizon_d_min: float = 0.15
    horizon_l_factor: float = 1.5
    horizon_l_min: float = 6.0
    horizon_l_cap: float = 20.0
    use_flag_base: bool = True
    assume_base_visible: bool = False
    use_grain: bool = True
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
    tol_miss: float = DEFAULT_TOL_MISS
    tol_pace: float = DEFAULT_TOL_PACE
    poor_horizon_fraction: float = 0.3
    conf_base_hidden: float = 0.8
    conf_flag_missing: float = 0.5
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
_SCALE = np.array([1e-2, 1e-2, 1e-3, 1e-3, 1e-3, 1e-3, 1e-3])  # natural size of each parameter


@dataclass(frozen=True)
class PatchFit:
    """Result of :func:`fit_patch`.

    Attributes
    ----------
    coeffs : (5,) array ``(a, b, c, d, e)`` in the putt frame [m/m, 1/m]
    cov : (5, 5) array
        Posterior covariance (Gauss-Newton approximation at the solution).
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
    n_drops : int
        Placements used by the fit.
    stations : tuple of float [m]
        Their stations along the line.
    base_hidden : bool
        The hole height was only bounded (base of the stick hidden).
    flag_missing : bool
        No flagstick: tilt-only fallback along the visor axis.
    used_horizon : bool;  poor_horizon : bool;  horizon_rms : float
        Whether horizon residuals entered the fit, whether they were flagged
        as poor, and their RMS in units of ``sigma_horizon`` (NaN if unused).
    n_iter : int;  converged : bool;  cost : float
        Levenberg-Marquardt diagnostics.
    """

    coeffs: np.ndarray
    cov: np.ndarray
    level_offsets: np.ndarray
    distance: float
    distance_sigma: float
    bearing: float
    range: RangeEstimate
    n_drops: int
    stations: Tuple[float, ...]
    base_hidden: bool
    flag_missing: bool
    used_horizon: bool
    poor_horizon: bool
    horizon_rms: float
    n_iter: int
    converged: bool
    cost: float


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


def _huber_cost(r: np.ndarray, k: float) -> float:
    a = np.abs(r)
    return float(np.sum(np.where(a <= k, 0.5 * r * r, k * a - 0.5 * k * k)))


def _huber_weight(r: np.ndarray, k: float) -> np.ndarray:
    return k / np.maximum(np.abs(r), k)  # 1 for |r| <= k, k / |r| beyond


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
        self.huber_k = huber_k
        self.horizon = None
        self._lin = None

    def add_linear(self, row, target: float, sigma: float, one_sided: bool = False) -> None:
        """Residual ``(row . x - target) / sigma``; one-sided = only its
        positive part counts (an upper bound on ``row . x``)."""
        self.rows.append(np.asarray(row, dtype=float) / sigma)
        self.targets.append(target / sigma)
        self.one_sided.append(one_sided)

    def set_horizon(self, theta, tan_elev, sigma: float, h_cam: float, d_min: float, far_limit: float) -> None:
        theta = np.asarray(theta, dtype=float)
        self.horizon = (np.asarray(tan_elev, dtype=float), sigma, h_cam, d_min, far_limit, np.cos(theta), np.sin(theta))

    def _linear(self):
        if self._lin is None:
            self._lin = (
                np.array(self.rows, dtype=float).reshape(-1, _NPAR),
                np.array(self.targets, dtype=float),
                np.array(self.one_sided, dtype=bool),
            )
        return self._lin

    def data(self, x: np.ndarray) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]:
        """Data residuals ``r`` (m,), their Jacobian (m, 7) and - for the
        horizon rows only - the second derivative of each residual with
        respect to its ray curvature ``K`` (None without a horizon)."""
        rows, targets, one_sided = self._linear()
        r = rows @ x - targets
        jac = rows
        idle = one_sided & (r <= 0.0)  # bound satisfied: no residual, no gradient
        if idle.any():
            r = np.where(idle, 0.0, r)
            jac = np.where(idle[:, None], 0.0, rows)
        if self.horizon is None:
            return r, jac, None
        tan_elev, sigma, h_cam, d_min, far_limit, ct, st = self.horizon
        horizon, r_max, second = _horizon_terms(x, ct, st, h_cam, d_min, far_limit)
        r_h = (horizon + x[5] + x[6] * st - tan_elev) / sigma
        jac_h = np.empty((ct.size, _NPAR))
        jac_h[:, 0] = ct
        jac_h[:, 1] = st
        jac_h[:, 2] = 0.5 * r_max * ct * ct
        jac_h[:, 3] = r_max * st * ct
        jac_h[:, 4] = 0.5 * r_max * st * st
        jac_h[:, 5] = 1.0
        jac_h[:, 6] = st
        return np.concatenate([r, r_h]), np.vstack([jac, jac_h / sigma]), second / sigma

    def cost(self, x: np.ndarray, r: Optional[np.ndarray] = None) -> float:
        if r is None:
            r = self.data(x)[0]
        return _huber_cost(r, self.huber_k) + 0.5 * float(np.sum(self.prior_w * x * x))

    def normal_equations(self, r: np.ndarray, jac: np.ndarray) -> np.ndarray:
        """Gauss-Newton matrix of the robust MAP cost with Huber (IRLS)
        weights; its inverse is the posterior covariance reported."""
        w = _huber_weight(r, self.huber_k)
        return jac.T @ (jac * w[:, None]) + np.diag(self.prior_w)

    def newton_system(self, x: np.ndarray, r: np.ndarray, jac: np.ndarray, second: Optional[np.ndarray],
                      exact: bool):
        """Gradient, iteration matrix and a positive damping diagonal.

        ``exact=False``: the Gauss-Newton matrix with Huber (IRLS) weights
        ``min(1, k / |r|)`` - a majoriser of the robust cost, safe far from
        the solution but only linearly convergent while outliers remain.

        ``exact=True``: the exact Hessian of the Huber cost for the current
        set of outliers (weight 1 for inliers, 0 for outliers; the outliers
        still pull through the gradient).  Used once the outlier set has
        stopped changing; it gives quadratic convergence.

        In both cases the exact second-order term of the horizon rows (the
        only non-linear ones) is added:
        ``psi(r_k) * d2r_k/dK2 * q_k q_k^T`` with
        ``q_k = dK/dp = (cos^2, 2 sin cos, sin^2)``.
        """
        k = self.huber_k
        psi = np.clip(r, -k, k)
        grad = jac.T @ psi + self.prior_w * x
        gauss = self.normal_equations(r, jac)
        if exact:
            inlier = (np.abs(r) <= k).astype(float)
            hess = jac.T @ (jac * inlier[:, None]) + np.diag(self.prior_w)
        else:
            hess = gauss.copy()
        if second is not None:
            ct, st = self.horizon[5], self.horizon[6]
            q = np.stack([ct * ct, 2.0 * st * ct, st * st], axis=1)
            wq = psi[-ct.size:] * second
            hess[2:5, 2:5] += q.T @ (q * wq[:, None])
        return grad, hess, np.diag(gauss).copy()


def _levenberg_marquardt(problem: _Problem, x0: np.ndarray, config: EstimatorConfig):
    """Minimise the robust MAP cost.  Returns ``(x, cov, n_iter, converged, cost)``.

    Levenberg-Marquardt: solve ``(H + lam * diag(H_gauss)) step = -grad``
    with ``H`` from :meth:`_Problem.newton_system`, accept the step only if
    it does not increase the cost, otherwise raise ``lam`` tenfold.  ``H`` is
    the IRLS majoriser until the set of Huber outliers is the same at two
    consecutive iterates, and the exact Hessian from then on.  Converged
    when the scaled step falls below ``config.lm_tol``.  Deterministic.
    """
    x = x0.copy()
    r, jac, second = problem.data(x)
    cost = problem.cost(x, r)
    lam = config.lm_lambda0
    converged = False
    n_iter = 0
    outliers_prev = None
    for n_iter in range(1, config.lm_max_iter + 1):
        outliers = np.abs(r) > problem.huber_k
        exact = outliers_prev is not None and np.array_equal(outliers, outliers_prev)
        outliers_prev = outliers
        grad, hess, diag = problem.newton_system(x, r, jac, second, exact)
        accepted = False
        small = False
        while lam <= 1e12:
            try:
                step = -np.linalg.solve(hess + lam * np.diag(diag), grad)
            except np.linalg.LinAlgError:  # singular (indefinite matrix): damp harder
                lam *= 10.0
                continue
            small = float(np.max(np.abs(step) / _SCALE)) < config.lm_tol
            x_new = x + step
            r_new, jac_new, second_new = problem.data(x_new)
            cost_new = problem.cost(x_new, r_new)
            if cost_new <= cost:
                x, r, jac, second, cost = x_new, r_new, jac_new, second_new, cost_new
                lam = max(lam * 0.1, 1e-12)
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
    cov = np.linalg.inv(problem.normal_equations(r, jac))
    return x, cov, n_iter, converged, cost


def _tilt_only_fit(meas: Measurements, config: EstimatorConfig, *, bearing: float, distance: float,
                   distance_sigma: float, rng_est: RangeEstimate, flag_missing: bool) -> PatchFit:
    """Plane from the puck tilt alone (method B0 and the no-flag fallback)."""
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
        n_drops=1,
        stations=(0.0,),
        base_hidden=False,
        flag_missing=flag_missing,
        used_horizon=False,
        poor_horizon=False,
        horizon_rms=math.nan,
        n_iter=0,
        converged=True,
        cost=0.0,
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
        iteration.  The default - and the firmware's - is the tilt plane of
        the first placement with everything else zero.  Only for checking
        that the minimum found does not depend on the start.

    Returns
    -------
    PatchFit
    """
    if method not in ("B0", "B1", "B2"):
        raise ValueError("fit_patch method must be 'B0', 'B1' or 'B2'")
    if isinstance(drops, Measurements):
        drops = (drops,)
    if len(drops) == 0:
        raise ValueError("need at least one placement")
    first = drops[0]
    rng_first = fuse_range(first, config)

    # ---- no usable flag: tilt-only plane along the visor axis -------------------
    if not (first.flag_found and rng_first.valid and math.isfinite(first.flag_bearing)):
        if math.isfinite(first.user_distance) and first.user_distance > 0.0:
            dist = float(first.user_distance)
        else:
            dist = config.default_distance
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
    problem = _Problem(dist, prior_sigma, config.huber_k)
    # placements that can be located on the line (the first one always can)
    located: List[Tuple[Measurements, RangeEstimate, float]] = [(first, rng_first, 0.0)]
    for drop in drops[1:]:
        rng_i = fuse_range(drop, config)
        if drop.flag_found and rng_i.valid and math.isfinite(drop.flag_bearing):
            located.append((drop, rng_i, min(max(dist - rng_i.distance, 0.0), dist)))
    sigma_field = config.sigma_field if len(located) > 1 else 0.0

    stations: List[float] = []
    base_hidden = False
    a0 = b0 = 0.0
    for i, (drop, rng_i, station) in enumerate(located):
        stations.append(station)
        # tilt, rotated into this drop's own "toward the hole" frame
        a_t, b_t = _rotate_to(drop.tilt, float(drop.flag_bearing))
        if i == 0:
            a0, b0 = a_t, b_t
        sig_t = math.hypot(_tilt_sigma(drop, config), sigma_field)
        problem.add_linear([1.0, 0.0, station, 0.0, 0.0, 0.0, 0.0], a_t, sig_t)
        problem.add_linear([0.0, 1.0, 0.0, station, 0.0, 0.0, 0.0], b_t, sig_t)
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
    n_data_before_horizon = len(problem.rows)
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

    if start is None:
        x0 = np.zeros(_NPAR)
        x0[0] = a0
        x0[1] = b0
    else:
        x0 = np.asarray(start, dtype=float).copy()
        if x0.shape != (_NPAR,) or not np.all(np.isfinite(x0)):
            raise ValueError("start must be 7 finite numbers")
    x, cov, n_iter, converged, cost = _levenberg_marquardt(problem, x0, config)

    poor_horizon = False
    horizon_rms = math.nan
    if used_horizon:
        r_h = problem.data(x)[0][n_data_before_horizon:]
        horizon_rms = float(np.sqrt(np.mean(r_h * r_h)))
        poor_horizon = bool(np.mean(np.abs(r_h) > config.huber_k) > config.poor_horizon_fraction)

    return PatchFit(
        coeffs=x[:5].copy(),
        cov=cov[:5, :5].copy(),
        level_offsets=x[5:].copy(),
        distance=dist,
        distance_sigma=rng_first.sigma,
        bearing=bearing,
        range=rng_first,
        n_drops=len(stations),
        stations=tuple(stations),
        base_hidden=bool(base_hidden and config.use_flag_base),
        flag_missing=False,
        used_horizon=used_horizon,
        poor_horizon=poor_horizon,
        horizon_rms=horizon_rms,
        n_iter=n_iter,
        converged=converged,
        cost=cost,
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
        Slope magnitude at the ball, ``100 * hypot(a, b)``.
    fall_line_azimuth : float [rad]
        Direction of steepest descent at the ball in the putt frame (CCW
        from the direction to the hole).
    fall_line_azimuth_device : float [rad]
        The same in the device frame.
    dz_hole : float [m]
        Fitted height of the hole above the ball, ``a D + 0.5 c D^2``.
    patch : (5,) array ``(a, b, c, d, e)`` (putt frame);  patch_cov : (5, 5)
    cross_slope_sigma : float [m/m]
        Posterior 1-sigma of the mean cross slope along the line,
        ``b + 0.5 d D``.
    confidence : float in [0, 1]
        ``erf(HOLE_R / (sqrt(2) sigma_lat))`` - the probability that the
        read error alone leaves the ball inside the hole's width, where
        ``sigma_lat`` is the lateral 1-sigma at the hole implied by
        ``cross_slope_sigma`` (and by the hand-pointing error when the flag
        is missing) - multiplied by the factors for the raised flags.
    base_hidden, flag_missing, poor_horizon : bool
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


def _confidence(fit: PatchFit, a_r: float, aim_source: int, config: EstimatorConfig) -> Tuple[float, float]:
    """Confidence score and the posterior sigma of the mean cross slope."""
    dist = fit.distance
    cov = fit.cov
    var = cov[1, 1] + dist * cov[1, 3] + 0.25 * dist * dist * cov[3, 3]
    sigma_cross = math.sqrt(max(var, 0.0))
    sigma_phi = 0.5 * ROLL_FACTOR * G * sigma_cross / a_r * _pace_factor(dist, config.past)
    if fit.flag_missing:
        sigma_phi = math.hypot(sigma_phi, config.sigma_hand_bearing)
    sigma_lat = dist * sigma_phi
    conf = math.erf(HOLE_R / (math.sqrt(2.0) * sigma_lat)) if sigma_lat > 0.0 else 1.0
    if fit.base_hidden:
        conf *= config.conf_base_hidden
    if fit.flag_missing:
        conf *= config.conf_flag_missing
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
        a, b, c = float(f.coeffs[0]), float(f.coeffs[1]), float(f.coeffs[2])
        if method == "STRAIGHT":
            conf, sigma_cross = 0.0, math.nan
            fit_out = None
        else:
            conf, sigma_cross = _confidence(f, float(a_r[i]), int(source[i]), config)
            fit_out = f
        slope = math.hypot(a, b)
        fall = math.atan2(-b, -a) if slope > 0.0 else 0.0
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
