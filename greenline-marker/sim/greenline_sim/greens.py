"""Seeded synthetic putting greens and putt scenarios (SI units).

A :class:`Green` is the TRUE world the Monte Carlo rolls balls on and the
sensor models look at.  It consists of

* a smooth turf surface ``z(x, y)`` (a :class:`~greenline_sim.physics.GridSurface`)
  covering the putting surface and its surrounds, built from
  an overall tilt + a low-frequency random undulation field
  (+ an optional tier or ridge),
* a closed green boundary 9-16 m from the centre, a collar (fringe) ring
  whose canopy stands ``COLLAR_STEP`` = 8 mm above the putting surface and
  rough beyond it standing ``ROUGH_STEP`` = 40 mm above (these steps are what
  a grazing camera sees; they do not change the rolling surface),
* the true green speed (Stimp) and grain.

Four classes are provided: ``'planar'``, ``'gentle'``, ``'undulating'`` and
``'tiered'`` (see :data:`CLASS_PARAMS`).  Everything is reproducible from an
integer seed.

Construction of the undulation
------------------------------
A stationary Gaussian random field with covariance
``A^2 exp(-r^2 / (2 l^2))`` is synthesised from ``n_modes`` random plane
waves (random Fourier features).  Its best-fit plane over the putting
surface is removed (so the drawn overall tilt really is the green's overall
tilt) and it is rescaled so that its RMS slope over the putting surface
equals the value drawn for the class.  ``l`` is the correlation length
(4-8 m): slopes change over a few metres, so a 3 m putt sees an almost
planar patch with slight curvature while a 12 m putt can see a double break.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Dict, Optional, Tuple, Union

import numpy as np

from .physics import (
    G,
    ROLL_FACTOR,
    Grain,
    GridSurface,
    Surface,
    stimp_to_decel,
)

__all__ = [
    "GREEN_CLASSES",
    "COLLAR_STEP",
    "ROUGH_STEP",
    "REGION_GREEN",
    "REGION_COLLAR",
    "REGION_ROUGH",
    "GreenParams",
    "CLASS_PARAMS",
    "Green",
    "PuttScenario",
    "PlacementError",
    "make_green",
    "green_from_surface",
    "place_hole",
    "place_ball",
    "place_putt",
    "make_scenario",
]

GREEN_CLASSES: Tuple[str, ...] = ("planar", "gentle", "undulating", "tiered")
"""Available green classes, in order of increasing difficulty."""

COLLAR_STEP = 0.008
"""Height of the collar (fringe) canopy above the putting surface [m]."""

ROUGH_STEP = 0.040
"""Height of the rough canopy above the putting surface [m]."""

REGION_GREEN = 0
REGION_COLLAR = 1
REGION_ROUGH = 2

SeedLike = Union[int, np.integer, np.random.Generator]


class PlacementError(RuntimeError):
    """No legal hole/ball position could be found on a green."""


@dataclass(frozen=True)
class GreenParams:
    """Sampling ranges for one green class (all SI; slopes as rise/run).

    Attributes
    ----------
    tilt_range : (min, max)
        Overall tilt magnitude of the green [m/m].
    undulation_slope_rms_range : (min, max)
        RMS slope magnitude of the undulation field over the putting
        surface [m/m] (0 = none).
    corr_length_range : (min, max)
        Correlation length ``l`` of the undulation [m].
    tier_prob : float
        Probability of a tier (a tanh step across the green).
    tier_height_range : (min, max) [m];  tier_max_slope_range : (min, max) [m/m]
        Tier height and the maximum slope on its face.
    ridge_prob : float
        Probability of a ridge or swale (a Gaussian bump along a line).
    ridge_max_slope_range : (min, max) [m/m];  ridge_width_range : (min, max) [m]
    edge_radius_range : (min, max) [m]
        Mean radius of the green boundary.
    edge_harmonic_amp_max : 3 floats
        Maximum relative amplitudes of the 2nd, 3rd and 4th angular harmonics
        of the boundary radius (their sum is kept <= 0.14 so that the
        boundary stays within 9-16 m for the default radius range).
    collar_width_range : (min, max) [m]
    collar_step, rough_step : float [m]
        Canopy heights above the putting surface.
    surround_slope_range : (min, max) [m/m]
        Extra radial slope of the terrain beyond the collar (negative =
        falls away, positive = rises).  Default (0, 0): the surrounds simply
        continue the tilt + undulation field.
    half_width : float [m];  spacing : float [m]
        Half-width and node spacing of the square height grid.
    n_modes : int
        Number of random plane waves in the undulation field.
    stimp_mean, stimp_sd : float [ft];  stimp_range : (min, max) [ft]
        True green speed ~ Normal(mean, sd) clipped to the range.
    grain_strong_prob : float
        Probability that the green is strongly grained (bermuda-like).
    grain_weak_kappa_max : float;  grain_strong_kappa_range : (min, max)
        Grain strength kappa: Uniform(0, weak max) or Uniform(strong range).
    grain_downhill_prob : float;  grain_downhill_sd : float [rad]
        Probability that the grain follows the overall fall line (with the
        given angular scatter); otherwise its direction is uniform.
    """

    tilt_range: Tuple[float, float] = (0.005, 0.03)
    undulation_slope_rms_range: Tuple[float, float] = (0.0, 0.0)
    corr_length_range: Tuple[float, float] = (4.0, 8.0)
    tier_prob: float = 0.0
    tier_height_range: Tuple[float, float] = (0.20, 0.45)
    tier_max_slope_range: Tuple[float, float] = (0.04, 0.07)
    ridge_prob: float = 0.0
    ridge_max_slope_range: Tuple[float, float] = (0.015, 0.04)
    ridge_width_range: Tuple[float, float] = (1.5, 3.0)
    edge_radius_range: Tuple[float, float] = (10.5, 14.0)
    edge_harmonic_amp_max: Tuple[float, float, float] = (0.08, 0.04, 0.02)
    collar_width_range: Tuple[float, float] = (0.8, 1.5)
    collar_step: float = COLLAR_STEP
    rough_step: float = ROUGH_STEP
    surround_slope_range: Tuple[float, float] = (0.0, 0.0)
    half_width: float = 24.0
    spacing: float = 0.5
    n_modes: int = 48
    stimp_mean: float = 10.0
    stimp_sd: float = 1.2
    stimp_range: Tuple[float, float] = (7.5, 13.0)
    grain_strong_prob: float = 0.35
    grain_weak_kappa_max: float = 0.03
    grain_strong_kappa_range: Tuple[float, float] = (0.05, 0.15)
    grain_downhill_prob: float = 0.5
    grain_downhill_sd: float = 0.5


CLASS_PARAMS: Dict[str, GreenParams] = {
    # essentially a tilted plane; hole cap is 3 %, so tilt stops at 2.8 %
    "planar": GreenParams(
        tilt_range=(0.005, 0.028),
        undulation_slope_rms_range=(0.0, 0.0015),
        corr_length_range=(6.0, 8.0),
    ),
    # tilt plus mild, long-wavelength contours
    "gentle": GreenParams(
        tilt_range=(0.005, 0.025),
        undulation_slope_rms_range=(0.004, 0.009),
        corr_length_range=(5.0, 8.0),
    ),
    # strongly contoured, sometimes with a ridge or swale
    "undulating": GreenParams(
        tilt_range=(0.005, 0.03),
        undulation_slope_rms_range=(0.010, 0.020),
        corr_length_range=(4.0, 7.0),
        ridge_prob=0.3,
    ),
    # two levels joined by a tier face of 4-7 % slope
    "tiered": GreenParams(
        tilt_range=(0.005, 0.02),
        undulation_slope_rms_range=(0.004, 0.010),
        corr_length_range=(5.0, 8.0),
        tier_prob=1.0,
    ),
}
"""Default :class:`GreenParams` per green class."""


@dataclass
class Green:
    """A synthetic green: true surface, boundary, canopy, speed and grain.

    Coordinates: origin at the green centre, x/y horizontal [m], z up [m].

    Attributes
    ----------
    green_class : str
    seed : int or None
        Seed it was generated from (None if a Generator was passed).
    surface : Surface
        True turf surface z(x, y) the ball rolls on; also covers the collar
        and rough (smooth continuation), without the canopy steps.  A
        :class:`~greenline_sim.physics.GridSurface` for generated greens.
    edge_r0 : float [m]
        Mean boundary radius.
    edge_amp, edge_phase : (3,) arrays
        Relative amplitudes and phases [rad] of the 2nd-4th angular
        harmonics of the boundary radius.
    collar_width : float [m]
    collar_step, rough_step : float [m]
        Canopy height above the putting surface in the collar / rough.
    tilt : (2,) array [m/m]
        Overall gradient (dz/dx, dz/dy) of the green before tier/ridge.
    undulation_slope_rms : float [m/m];  corr_length : float [m]
    tier : dict or None
        ``{'height', 'width', 'azimuth', 'offset', 'max_slope'}`` of the tier
        ``0.5 * height * tanh((x cos(az) + y sin(az) - offset) / width)``.
    ridge : dict or None
        ``{'height', 'width', 'azimuth', 'offset', 'max_slope'}`` of the ridge
        ``height * exp(-(x cos(az) + y sin(az) - offset)^2 / (2 width^2))``
        (negative height = swale).
    surround_slope : float [m/m]
    stimp_ft : float [ft]
        True green speed.
    grain : Grain
        True grain (world frame).
    """

    green_class: str
    seed: Optional[int]
    surface: Surface
    edge_r0: float
    edge_amp: np.ndarray
    edge_phase: np.ndarray
    collar_width: float
    collar_step: float
    rough_step: float
    tilt: np.ndarray
    undulation_slope_rms: float
    corr_length: float
    tier: Optional[dict]
    ridge: Optional[dict]
    surround_slope: float
    stimp_ft: float
    grain: Grain

    # ---- speed / grain ----------------------------------------------------

    @property
    def a_r(self) -> float:
        """True flat-green rolling deceleration [m/s^2]."""
        return stimp_to_decel(self.stimp_ft)

    @property
    def grain_vector(self) -> np.ndarray:
        """True grain as ``kappa * g_hat`` (world frame, dimensionless)."""
        return self.grain.vector

    # ---- surface ----------------------------------------------------------

    def z(self, x, y):
        """True turf height z [m] (no canopy)."""
        return self.surface.z(x, y)

    def grad(self, x, y):
        """True surface gradient ``(dz/dx, dz/dy)`` [m/m]."""
        return self.surface.grad(x, y)

    def slope(self, x, y):
        """True slope magnitude [m/m]."""
        return self.surface.slope(x, y)

    def can_rest(self, x, y, margin: float = 1.0):
        """Whether a ball can rest at ``(x, y)`` on this green.

        True where the slope-plus-grain drive is below ``margin * a_r``
        (``margin < 1`` adds a safety factor).
        """
        gx, gy = self.surface.grad(x, y)
        a_r = self.a_r
        gvec = self.grain_vector * a_r
        kf = ROLL_FACTOR * G
        drive = np.hypot(gvec[0] - kf * np.asarray(gx), gvec[1] - kf * np.asarray(gy))
        out = drive < margin * a_r
        return bool(out) if np.ndim(out) == 0 else out

    # ---- boundary / canopy -------------------------------------------------

    def edge_radius(self, theta):
        """Radius of the green boundary [m] at azimuth ``theta`` [rad]."""
        theta = np.asarray(theta, dtype=float)
        rel = np.zeros_like(theta)
        for k, m in enumerate((2, 3, 4)):
            rel = rel + self.edge_amp[k] * np.cos(m * (theta - self.edge_phase[k]))
        out = self.edge_r0 * (1.0 + rel)
        return float(out) if out.ndim == 0 else out

    @property
    def edge_radius_min(self) -> float:
        """Lower bound on the boundary radius [m]."""
        return float(self.edge_r0 * (1.0 - np.sum(self.edge_amp)))

    @property
    def edge_radius_max(self) -> float:
        """Upper bound on the boundary radius [m]."""
        return float(self.edge_r0 * (1.0 + np.sum(self.edge_amp)))

    def radial_margin(self, x, y):
        """Radial distance from ``(x, y)`` to the green boundary [m].

        Positive inside the green, negative outside; measured along the ray
        from the green centre (a close stand-in for the distance to the edge).
        """
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        out = self.edge_radius(np.arctan2(y, x)) - np.hypot(x, y)
        return float(out) if np.ndim(out) == 0 else out

    def on_green(self, x, y, margin: float = 0.0):
        """True where ``(x, y)`` is on the putting surface, at least
        ``margin`` [m] inside the boundary."""
        out = np.asarray(self.radial_margin(x, y)) >= margin
        return bool(out) if out.ndim == 0 else out

    def region(self, x, y):
        """Region code: ``REGION_GREEN`` (0), ``REGION_COLLAR`` (1) or
        ``REGION_ROUGH`` (2)."""
        m = np.asarray(self.radial_margin(x, y))
        out = np.where(m >= 0.0, REGION_GREEN, np.where(m >= -self.collar_width, REGION_COLLAR, REGION_ROUGH))
        return int(out) if out.ndim == 0 else out

    def canopy_step(self, x, y):
        """Height of the grass canopy above the putting-surface datum [m]:
        0 on the green, ``collar_step`` on the collar, ``rough_step`` beyond."""
        m = np.asarray(self.radial_margin(x, y))
        out = np.where(m >= 0.0, 0.0, np.where(m >= -self.collar_width, self.collar_step, self.rough_step))
        return float(out) if out.ndim == 0 else out

    def canopy_z(self, x, y):
        """Height of the visible grass top [m]: ``z + canopy_step``.  This is
        the silhouette a grazing camera sees; the ball rolls on ``z``."""
        out = np.asarray(self.surface.z(x, y)) + np.asarray(self.canopy_step(x, y))
        return float(out) if out.ndim == 0 else out


@dataclass
class PuttScenario:
    """One putt on one green.

    Attributes
    ----------
    green : Green
    hole_xy, ball_xy : (2,) arrays [m] (world frame)
    distance : float [m]
        Straight ball->hole distance.
    seed : int or None
    """

    green: Green
    hole_xy: np.ndarray
    ball_xy: np.ndarray
    distance: float
    seed: Optional[int] = None

    @property
    def bearing(self) -> float:
        """Azimuth of the ball->hole line [rad, CCW from +x]."""
        d = self.hole_xy - self.ball_xy
        return float(math.atan2(d[1], d[0]))

    @property
    def dz(self) -> float:
        """Height of the hole relative to the ball, ``z_hole - z_ball`` [m]."""
        return float(self.green.z(*self.hole_xy) - self.green.z(*self.ball_xy))


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------


def _class_index(green_class: str) -> int:
    if green_class not in GREEN_CLASSES:
        raise ValueError(f"unknown green class {green_class!r}; choose from {GREEN_CLASSES}")
    return GREEN_CLASSES.index(green_class)


def _rng_for(seed: SeedLike, *stream: int) -> Tuple[np.random.Generator, Optional[int]]:
    """Generator for ``seed`` (int -> independent stream per ``stream`` key)."""
    if isinstance(seed, np.random.Generator):
        return seed, None
    if isinstance(seed, (int, np.integer)) and not isinstance(seed, bool):
        if seed < 0:
            raise ValueError("seed must be non-negative")
        return np.random.default_rng(np.random.SeedSequence([int(seed), *[int(s) for s in stream]])), int(seed)
    raise TypeError("seed must be a non-negative int or a numpy Generator")


def _uniform(rng: np.random.Generator, bounds: Tuple[float, float]) -> float:
    lo, hi = bounds
    if hi < lo:
        raise ValueError(f"invalid range {bounds}")
    return float(rng.uniform(lo, hi))


def make_green(green_class: str, seed: SeedLike, params: Optional[GreenParams] = None) -> Green:
    """Generate a random green of the given class.

    Parameters
    ----------
    green_class : one of :data:`GREEN_CLASSES`
    seed : int or numpy Generator
        An int gives a green that depends only on ``(seed, green_class)``.
    params : GreenParams, optional
        Override the class defaults (:data:`CLASS_PARAMS`).

    Returns
    -------
    Green
    """
    cls_idx = _class_index(green_class)
    prm = CLASS_PARAMS[green_class] if params is None else params
    rng, seed_int = _rng_for(seed, cls_idx, 0)

    # ---- boundary -----------------------------------------------------------
    edge_r0 = _uniform(rng, prm.edge_radius_range)
    edge_amp = np.array([rng.uniform(0.0, a) for a in prm.edge_harmonic_amp_max])
    edge_phase = rng.uniform(0.0, 2.0 * math.pi, size=3)
    collar_width = _uniform(rng, prm.collar_width_range)

    # ---- grid ---------------------------------------------------------------
    n = int(round(2.0 * prm.half_width / prm.spacing)) + 1
    x = np.linspace(-prm.half_width, prm.half_width, n)
    y = x.copy()
    xx, yy = np.meshgrid(x, y, indexing="ij")
    rr = np.hypot(xx, yy)
    th = np.arctan2(yy, xx)
    rel = np.zeros_like(th)
    for k, m in enumerate((2, 3, 4)):
        rel += edge_amp[k] * np.cos(m * (th - edge_phase[k]))
    edge_r = edge_r0 * (1.0 + rel)
    inside = rr <= edge_r
    if edge_r.max() + collar_width + 2.0 > prm.half_width:
        raise ValueError("half_width too small for the requested green size")

    # ---- overall tilt -------------------------------------------------------
    tilt_mag = _uniform(rng, prm.tilt_range)
    tilt_az = float(rng.uniform(0.0, 2.0 * math.pi))  # uphill direction
    tilt = np.array([tilt_mag * math.cos(tilt_az), tilt_mag * math.sin(tilt_az)])
    zz = tilt[0] * xx + tilt[1] * yy

    # ---- undulation: random plane waves, detrended and rescaled --------------
    corr_length = _uniform(rng, prm.corr_length_range)
    slope_rms = _uniform(rng, prm.undulation_slope_rms_range)
    n_modes = int(prm.n_modes)
    kx = rng.normal(0.0, 1.0 / corr_length, size=n_modes)
    ky = rng.normal(0.0, 1.0 / corr_length, size=n_modes)
    ph = rng.uniform(0.0, 2.0 * math.pi, size=n_modes)
    if slope_rms > 0.0:
        ax = kx[:, None] * x[None, :] + ph[:, None]  # (modes, nx)
        by = ky[:, None] * y[None, :]  # (modes, ny)
        cax, sax = np.cos(ax), np.sin(ax)
        cby, sby = np.cos(by), np.sin(by)
        amp = math.sqrt(2.0 / n_modes)
        und = amp * (cax.T @ cby - sax.T @ sby)
        gux = -amp * ((kx[:, None] * sax).T @ cby + (kx[:, None] * cax).T @ sby)
        guy = -amp * (sax.T @ (ky[:, None] * cby) + cax.T @ (ky[:, None] * sby))
        # remove the best-fit plane over the putting surface
        design = np.column_stack([np.ones(inside.sum()), xx[inside], yy[inside]])
        coef, *_ = np.linalg.lstsq(design, und[inside], rcond=None)
        und = und - (coef[0] + coef[1] * xx + coef[2] * yy)
        gux = gux - coef[1]
        guy = guy - coef[2]
        rms = math.sqrt(float(np.mean(gux[inside] ** 2 + guy[inside] ** 2)))
        if not (rms > 0.0):
            raise RuntimeError("degenerate undulation field (zero slope)")
        zz = zz + und * (slope_rms / rms)

    # ---- tier ---------------------------------------------------------------
    tier = None
    if rng.random() < prm.tier_prob:
        height = _uniform(rng, prm.tier_height_range)
        max_slope = _uniform(rng, prm.tier_max_slope_range)
        width = height / (2.0 * max_slope)
        az = float(rng.uniform(0.0, 2.0 * math.pi))
        offset = float(rng.uniform(-0.25, 0.25) * edge_r0)
        s = xx * math.cos(az) + yy * math.sin(az) - offset
        zz = zz + 0.5 * height * np.tanh(s / width)
        tier = {"height": height, "width": width, "azimuth": az, "offset": offset, "max_slope": max_slope}

    # ---- ridge / swale ------------------------------------------------------
    ridge = None
    if rng.random() < prm.ridge_prob:
        width = _uniform(rng, prm.ridge_width_range)
        max_slope = _uniform(rng, prm.ridge_max_slope_range)
        sign = 1.0 if rng.random() < 0.5 else -1.0
        height = sign * max_slope * width * math.sqrt(math.e)
        az = float(rng.uniform(0.0, 2.0 * math.pi))
        offset = float(rng.uniform(-0.4, 0.4) * edge_r0)
        s = xx * math.cos(az) + yy * math.sin(az) - offset
        zz = zz + height * np.exp(-0.5 * (s / width) ** 2)
        ridge = {"height": height, "width": width, "azimuth": az, "offset": offset, "max_slope": max_slope}

    # ---- surrounds ----------------------------------------------------------
    surround_slope = _uniform(rng, prm.surround_slope_range)
    if surround_slope != 0.0:
        rho = np.maximum(rr - (edge_r + collar_width), 0.0)
        zz = zz + surround_slope * rho * rho / (rho + 1.0)  # C1 onset, -> slope

    # ---- speed and grain ----------------------------------------------------
    stimp = float(np.clip(rng.normal(prm.stimp_mean, prm.stimp_sd), *prm.stimp_range))
    if rng.random() < prm.grain_strong_prob:
        kappa = _uniform(rng, prm.grain_strong_kappa_range)
    else:
        kappa = float(rng.uniform(0.0, prm.grain_weak_kappa_max))
    if rng.random() < prm.grain_downhill_prob:
        grain_az = tilt_az + math.pi + float(rng.normal(0.0, prm.grain_downhill_sd))
    else:
        grain_az = float(rng.uniform(0.0, 2.0 * math.pi))
    grain_az = math.atan2(math.sin(grain_az), math.cos(grain_az))

    surface = GridSurface(x, y, zz)
    z_centre = surface.z(0.0, 0.0)
    surface = GridSurface(x, y, zz - z_centre)  # datum: z = 0 at the green centre

    return Green(
        green_class=green_class,
        seed=seed_int,
        surface=surface,
        edge_r0=edge_r0,
        edge_amp=edge_amp,
        edge_phase=edge_phase,
        collar_width=collar_width,
        collar_step=float(prm.collar_step),
        rough_step=float(prm.rough_step),
        tilt=tilt,
        undulation_slope_rms=slope_rms,
        corr_length=corr_length,
        tier=tier,
        ridge=ridge,
        surround_slope=surround_slope,
        stimp_ft=stimp,
        grain=Grain(kappa, grain_az),
    )


def green_from_surface(
    surface,
    *,
    edge_radius: float = 12.0,
    collar_width: float = 1.0,
    stimp_ft: float = 10.0,
    grain: Optional[Grain] = None,
    collar_step: float = COLLAR_STEP,
    rough_step: float = ROUGH_STEP,
    half_width: float = 24.0,
    spacing: float = 0.5,
    green_class: str = "custom",
) -> Green:
    """Wrap a known surface as a :class:`Green` with a circular boundary.

    For tests and worked examples (e.g. an exact plane or quadratic green).

    Parameters
    ----------
    surface : Surface or callable ``f(x, y) -> z``
        A :class:`~greenline_sim.physics.Surface` is used as is (so a
        ``QuadraticSurface`` stays exact); a vectorised callable is sampled
        on a ``2 * half_width`` square grid with node ``spacing`` [m].
    edge_radius : float [m]
        Radius of the (circular) green boundary.
    collar_width : float [m]
    stimp_ft : float [ft];  grain : Grain or None (no grain)
        True green speed and grain.
    collar_step, rough_step : float [m]
        Canopy heights above the putting surface.
    green_class : str
        Label stored on the green (not one of :data:`GREEN_CLASSES`).
    """
    if not (edge_radius > 0.0 and collar_width >= 0.0 and stimp_ft > 0.0):
        raise ValueError("edge_radius and stimp_ft must be positive, collar_width >= 0")
    if isinstance(surface, Surface):
        surf = surface
    elif callable(surface):
        surf = GridSurface.from_function(surface, (-half_width, half_width), (-half_width, half_width), spacing)
    else:
        raise TypeError("surface must be a physics.Surface or a callable f(x, y) -> z")
    gx0, gy0 = surf.grad(0.0, 0.0)
    return Green(
        green_class=green_class,
        seed=None,
        surface=surf,
        edge_r0=float(edge_radius),
        edge_amp=np.zeros(3),
        edge_phase=np.zeros(3),
        collar_width=float(collar_width),
        collar_step=float(collar_step),
        rough_step=float(rough_step),
        tilt=np.array([float(gx0), float(gy0)]),
        undulation_slope_rms=0.0,
        corr_length=math.inf,
        tier=None,
        ridge=None,
        surround_slope=0.0,
        stimp_ft=float(stimp_ft),
        grain=Grain() if grain is None else grain,
    )


# --------------------------------------------------------------------------
# Hole and ball placement
# --------------------------------------------------------------------------


def place_hole(
    green: Green,
    rng: np.random.Generator,
    *,
    max_slope: float = 0.03,
    min_edge_dist: float = 3.0,
    check_radius: float = 0.9,
    ring_slope_factor: float = 1.2,
    max_tries: int = 10000,
) -> np.ndarray:
    """Pick a legal hole location uniformly at random.

    Legal means: at least ``min_edge_dist`` [m] inside the boundary, slope at
    the hole <= ``max_slope`` [m/m], and slope at 8 points on a circle of
    ``check_radius`` [m] around it <= ``ring_slope_factor * max_slope`` (the
    area around a hole should be of consistent, modest slope).

    Returns the hole centre ``(x, y)`` [m].  Raises :class:`PlacementError`
    if ``max_tries`` candidates were all illegal.
    """
    if max_slope <= 0.0 or min_edge_dist < 0.0:
        raise ValueError("max_slope must be > 0 and min_edge_dist >= 0")
    r_box = green.edge_radius_max - min_edge_dist
    if r_box <= 0.0:
        raise PlacementError("green too small for the requested edge distance")
    ring = np.arange(8) * (math.pi / 4.0)
    batch = 256
    tried = 0
    while tried < max_tries:
        cand = rng.uniform(-r_box, r_box, size=(batch, 2))
        tried += batch
        ok = np.asarray(green.radial_margin(cand[:, 0], cand[:, 1])) >= min_edge_dist
        ok &= np.asarray(green.slope(cand[:, 0], cand[:, 1])) <= max_slope
        if not ok.any():
            continue
        idx = np.nonzero(ok)[0]
        rx = cand[idx, 0][:, None] + check_radius * np.cos(ring)[None, :]
        ry = cand[idx, 1][:, None] + check_radius * np.sin(ring)[None, :]
        ring_ok = (np.asarray(green.slope(rx, ry)) <= ring_slope_factor * max_slope).all(axis=1)
        if ring_ok.any():
            return cand[idx[np.argmax(ring_ok)]].copy()
    raise PlacementError(
        f"no legal hole location found in {tried} tries (class {green.green_class}, seed {green.seed})"
    )


def place_ball(
    green: Green,
    hole_xy,
    distance: float,
    rng: np.random.Generator,
    *,
    edge_margin: float = 0.5,
    rest_margin: float = 0.9,
    max_tries: int = 256,
) -> np.ndarray:
    """Place the ball ``distance`` [m] from the hole at a random azimuth.

    The ball must be on the putting surface at least ``edge_margin`` [m]
    inside the boundary, must be able to rest there (drive below
    ``rest_margin * a_r`` for the green's true speed and grain), and the
    straight ball->hole line must stay on the putting surface.

    Returns the ball position ``(x, y)`` [m].  Raises
    :class:`PlacementError` if no azimuth works.
    """
    if distance <= 0.0:
        raise ValueError("distance must be positive [m]")
    hole_xy = np.asarray(hole_xy, dtype=float)
    frac = np.linspace(0.0, 1.0, 9)[1:-1]
    batch = 64
    tried = 0
    while tried < max_tries:
        az = rng.uniform(0.0, 2.0 * math.pi, size=batch)
        tried += batch
        bx = hole_xy[0] + distance * np.cos(az)
        by = hole_xy[1] + distance * np.sin(az)
        ok = np.asarray(green.on_green(bx, by, edge_margin))
        ok &= np.asarray(green.can_rest(bx, by, rest_margin))
        if not ok.any():
            continue
        lx = hole_xy[0] + (bx[:, None] - hole_xy[0]) * frac[None, :]
        ly = hole_xy[1] + (by[:, None] - hole_xy[1]) * frac[None, :]
        ok &= np.asarray(green.on_green(lx, ly)).all(axis=1)
        if ok.any():
            k = int(np.argmax(ok))
            return np.array([bx[k], by[k]])
    raise PlacementError(
        f"no legal ball position {distance:.2f} m from the hole (class {green.green_class}, seed {green.seed})"
    )


def place_putt(
    green: Green,
    distance: float,
    rng: np.random.Generator,
    *,
    max_hole_tries: int = 200,
    hole_kwargs: Optional[dict] = None,
    ball_kwargs: Optional[dict] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """Place a hole and a ball ``distance`` [m] apart on ``green``.

    Draws a legal hole (see :func:`place_hole`), then a ball position (see
    :func:`place_ball`); if no ball position exists for that hole a new hole
    is drawn.  Returns ``(hole_xy, ball_xy)``.
    """
    hole_kwargs = {} if hole_kwargs is None else hole_kwargs
    ball_kwargs = {} if ball_kwargs is None else ball_kwargs
    for _ in range(max_hole_tries):
        hole = place_hole(green, rng, **hole_kwargs)
        try:
            ball = place_ball(green, hole, distance, rng, **ball_kwargs)
        except PlacementError:
            continue  # this hole has no room for a putt of that length: redraw
        return hole, ball
    raise PlacementError(
        f"could not place a {distance:.2f} m putt (class {green.green_class}, seed {green.seed})"
    )


def make_scenario(
    green_class: str,
    distance: float,
    seed: int,
    *,
    green: Optional[Green] = None,
    params: Optional[GreenParams] = None,
    hole_kwargs: Optional[dict] = None,
    ball_kwargs: Optional[dict] = None,
) -> PuttScenario:
    """Build a reproducible putt: green + hole + ball.

    Parameters
    ----------
    green_class : one of :data:`GREEN_CLASSES`
    distance : float [m]
        Requested straight ball->hole distance.
    seed : int
        The green depends on ``(seed, green_class)`` only, so the same seed
        gives the same green for every distance; hole and ball depend on
        ``(seed, green_class, distance)``.
    green : Green, optional
        Reuse an already generated ``make_green(green_class, seed)`` (saves
        time when looping over distances).
    params, hole_kwargs, ball_kwargs : optional overrides passed to
        :func:`make_green`, :func:`place_hole` and :func:`place_ball`.
    """
    cls_idx = _class_index(green_class)
    if green is None:
        green = make_green(green_class, seed, params)
    elif green.green_class != green_class:
        raise ValueError("green.green_class does not match green_class")
    rng, seed_int = _rng_for(seed, cls_idx, 1, int(round(distance * 1000.0)))
    hole, ball = place_putt(green, distance, rng, hole_kwargs=hole_kwargs, ball_kwargs=ball_kwargs)
    return PuttScenario(green=green, hole_xy=hole, ball_xy=ball, distance=float(distance), seed=seed_int)
