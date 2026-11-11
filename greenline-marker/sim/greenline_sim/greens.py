"""Seeded synthetic putting greens and putt scenarios (SI units).

A :class:`Green` is the TRUE world the Monte Carlo rolls balls on and the
sensor models look at.  It consists of

* a smooth turf surface ``z(x, y)`` (a :class:`~greenline_sim.physics.GridSurface`)
  covering the putting surface and continuing smoothly beyond it, built
  from an overall tilt + a low-frequency random undulation field
  (+ an optional tier or ridge),
* a closed green boundary 9-16 m from the centre, a collar (fringe) ring
  whose canopy stands ``COLLAR_STEP`` = 8 mm above the putting surface and
  rough beyond it standing ``ROUGH_STEP`` = 40 mm above (these steps are what
  a grazing camera sees; they do not change the rolling surface),
* the terrain of the surrounds: beyond the collar the ground departs from
  the smooth continuation of the putting surface with a radial slope that
  varies with azimuth (run-offs, mounds, a hillside behind the green).  The
  default ranges (mean -8 % ... +2 %, azimuthal variation up to 6 % and 3 %)
  are an ASSUMPTION, not survey data; they are named parameters of
  :class:`GreenParams`,
* the true green speed (Stimp) and grain, and the height of the flagstick.

Three height functions are kept apart on purpose:

``Green.z`` / ``Green.surface``
    the surface the BALL ROLLS on: the putting surface and its smooth
    continuation.  No canopy, no surround terrain.
``Green.terrain_z``
    the true ground: ``z`` plus the surround terrain beyond the collar.
``Green.canopy_z``
    the top of the grass a grazing CAMERA sees: ``terrain_z`` plus the canopy
    step of the collar / rough.

On the putting surface itself all three are identical.  ``Green.without_fringe()``
gives the optimistic "no-fringe" twin of a green (no canopy steps, no
surround terrain, same putting surface) for testing how much the collar,
rough and surrounds spoil what a grazing camera can learn from the turf
horizon.

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
    "DEFAULT_FLAGSTICK_HEIGHT",
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

DEFAULT_FLAGSTICK_HEIGHT = 2.13
"""Nominal visible flagstick height above the hole lip [m] (7 ft)."""

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
        Mean extra radial slope of the terrain beyond the collar, relative to
        the smooth continuation of the putting surface (negative = falls
        away, positive = rises).  Most greens are built up, so the default
        range is mostly negative.
    surround_harmonic_amp_max : 2 floats [m/m]
        Maximum amplitudes of the 1st and 2nd angular harmonics of that
        radial slope (1st: one side higher than the other, e.g. a hillside;
        2nd: saddle).  Amplitudes ~ Uniform(0, max), phases uniform.
    surround_onset : float [m]
        Length scale over which the surround slope sets in beyond the collar.
    flagstick_height_range : (min, max) [m]
        Visible height of the flagstick above the hole lip (one value per
        green, standing in for "per course").
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
    surround_slope_range: Tuple[float, float] = (-0.08, 0.02)
    surround_harmonic_amp_max: Tuple[float, float] = (0.06, 0.03)
    surround_onset: float = 1.5
    flagstick_height_range: Tuple[float, float] = (2.0, 2.3)
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
    """A synthetic green: true surface, boundary, canopy, surrounds, speed and grain.

    Coordinates: origin at the green centre, x/y horizontal [m], z up [m].

    Attributes
    ----------
    green_class : str
    seed : int or None
        Seed it was generated from (None if a Generator was passed).
    surface : Surface
        True turf surface z(x, y) the ball rolls on: the putting surface and
        its smooth continuation under the collar and beyond, without the
        canopy steps and without the surround terrain.  A
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
        Mean extra radial slope of the terrain beyond the collar (negative =
        falls away from the green).
    stimp_ft : float [ft]
        True green speed.
    grain : Grain
        True grain (world frame).
    surround_amp, surround_phase : (2,) arrays [m/m], [rad]
        Amplitudes and phases of the 1st and 2nd angular harmonics of the
        surround slope (see :meth:`surround_slope_at`).
    surround_onset : float [m]
        Length scale of the onset of the surround slope beyond the collar.
    flagstick_height : float [m]
        True visible height of the flagstick above the hole lip.
    surround_mounds : (k, 4) array or None
        Optional mounds and hollows of the surrounds, independent of the
        putting surface: rows ``(amplitude [m], kx [rad/m], ky [rad/m],
        phase [rad])`` of plane waves ``amplitude * cos(kx x + ky y + phase)``
        that set in beyond the collar.  None (the default) for generated
        greens; see :meth:`with_mounded_surrounds`.
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
    surround_amp: np.ndarray = field(default_factory=lambda: np.zeros(2))
    surround_phase: np.ndarray = field(default_factory=lambda: np.zeros(2))
    surround_onset: float = 1.5
    flagstick_height: float = DEFAULT_FLAGSTICK_HEIGHT
    surround_mounds: Optional[np.ndarray] = None

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
        """Height z [m] of the surface the ball rolls on (no canopy, no
        surround terrain; identical to :meth:`terrain_z` and
        :meth:`canopy_z` on the putting surface)."""
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
        """Height of the grass canopy above the ground [m]: 0 on the green,
        ``collar_step`` on the collar, ``rough_step`` beyond."""
        m = np.asarray(self.radial_margin(x, y))
        out = np.where(m >= 0.0, 0.0, np.where(m >= -self.collar_width, self.collar_step, self.rough_step))
        return float(out) if out.ndim == 0 else out

    # ---- surrounds -----------------------------------------------------------

    def surround_slope_at(self, theta):
        """Extra radial slope of the surrounds [m/m] at azimuth ``theta`` [rad]:
        ``surround_slope + sum_k surround_amp[k] cos((k + 1)(theta - surround_phase[k]))``,
        k = 0, 1.  Negative = the ground falls away from the green."""
        theta = np.asarray(theta, dtype=float)
        out = np.full_like(theta, self.surround_slope)
        for k in range(2):
            out = out + self.surround_amp[k] * np.cos((k + 1) * (theta - self.surround_phase[k]))
        return float(out) if out.ndim == 0 else out

    def surround_dz(self, x, y):
        """Height of the true ground above the smooth continuation of the
        putting surface [m]; zero on the green and the collar.

        With ``rho`` the radial distance beyond the outer edge of the collar
        and ``s`` the surround slope at that azimuth,
        ``dz = s * rho^3 / (rho^2 + surround_onset^2)``: a C2 onset at the
        collar edge that tends to the radial slope ``s`` (its steepest point,
        ``1.125 s``, is at ``rho = sqrt(3) * surround_onset``).  Optional
        mounds (:attr:`surround_mounds`) are added on top with the onset
        ramp ``rho^2 / (rho^2 + surround_onset^2)``.
        """
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        theta = np.arctan2(y, x)
        rho = np.maximum(np.hypot(x, y) - (np.asarray(self.edge_radius(theta)) + self.collar_width), 0.0)
        out = np.asarray(self.surround_slope_at(theta)) * rho**3 / (rho * rho + self.surround_onset**2)
        if self.surround_mounds is not None:
            # mounds set in with a C1 ramp rho^2 / (rho^2 + onset^2) beyond the collar
            out = out + np.asarray(self.mound_field(x, y)) * rho * rho / (rho * rho + self.surround_onset**2)
        return float(out) if out.ndim == 0 else out

    def mound_field(self, x, y):
        """Raw height of the surround mounds [m] at ``(x, y)`` before the
        onset ramp: ``sum_k amplitude_k cos(kx_k x + ky_k y + phase_k)``
        (zero if the green has no mounds)."""
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        out = np.zeros(np.broadcast(x, y).shape)
        if self.surround_mounds is not None:
            for amp, kx, ky, phase in self.surround_mounds:
                out = out + amp * np.cos(kx * x + ky * y + phase)
        return float(out) if out.ndim == 0 else out

    def terrain_z(self, x, y):
        """Height of the true ground [m]: ``z + surround_dz`` (no canopy)."""
        out = np.asarray(self.surface.z(x, y)) + np.asarray(self.surround_dz(x, y))
        return float(out) if out.ndim == 0 else out

    def canopy_z(self, x, y):
        """Height of the visible grass top [m]: ``terrain_z + canopy_step``.
        This is the silhouette a grazing camera sees; the ball rolls on ``z``."""
        out = np.asarray(self.terrain_z(x, y)) + np.asarray(self.canopy_step(x, y))
        return float(out) if out.ndim == 0 else out

    @property
    def model_radius(self) -> float:
        """Radius from the green centre [m] within which the terrain is
        modelled; a sensor ray-march should not look further.  The largest
        circle inside the height grid, or 10 m beyond the collar for an
        analytic (unbounded) surface."""
        xmin, xmax, ymin, ymax = self.surface.bounds
        r = min(-xmin, xmax, -ymin, ymax)
        if math.isfinite(r):
            return float(r)
        return self.edge_radius_max + self.collar_width + 10.0

    @property
    def has_fringe(self) -> bool:
        """True if anything beyond the putting surface differs from its smooth
        continuation (canopy steps or surround terrain)."""
        return bool(
            self.collar_step != 0.0
            or self.rough_step != 0.0
            or self.surround_slope != 0.0
            or np.any(np.asarray(self.surround_amp) != 0.0)
            or self.surround_mounds is not None
        )

    def without_surrounds(self) -> "Green":
        """Twin of this green whose terrain beyond the collar simply continues
        the putting surface (``terrain_z == z``); the collar and rough canopy
        steps are kept.  Intermediate case between the realistic green and
        :meth:`without_fringe`.  Same rolling surface object."""
        return replace(
            self, surround_slope=0.0, surround_amp=np.zeros(2), surround_phase=np.zeros(2), surround_mounds=None
        )

    def without_fringe(self) -> "Green":
        """Optimistic "no-fringe" twin of this green.

        Same rolling surface (the same object), boundary, speed, grain and
        flagstick, but no collar/rough canopy steps and no surround terrain:
        beyond the putting surface a camera sees its smooth continuation, so
        ``canopy_z == terrain_z == z`` everywhere.  Holes and balls placed on
        the original are equally valid on the twin.
        """
        return replace(
            self,
            collar_step=0.0,
            rough_step=0.0,
            surround_slope=0.0,
            surround_amp=np.zeros(2),
            surround_phase=np.zeros(2),
            surround_mounds=None,
        )

    def with_mounded_surrounds(
        self,
        seed: int,
        height_rms: float = 0.20,
        wavelength_range: Tuple[float, float] = (5.0, 15.0),
        n_modes: int = 12,
    ) -> "Green":
        """Stress-test twin whose surrounds carry mounds and hollows that are
        independent of the putting surface (greenside mounds, bunker faces, a
        broken backdrop).

        Beyond the collar a random field of ``n_modes`` plane waves with RMS
        height ``height_rms`` [m] and wavelengths drawn from
        ``wavelength_range`` [m] is added to the terrain a camera sees.  The
        putting surface, the collar, the canopy steps and the mean surround
        slope are unchanged, and the ball still rolls on the same surface
        object.  The default magnitudes are an ASSUMPTION for testing how
        much a grazing camera's turf horizon depends on the surrounds; they
        are not survey data.  Reproducible from ``seed``.
        """
        if not (height_rms >= 0.0 and n_modes >= 1 and wavelength_range[1] >= wavelength_range[0] > 0.0):
            raise ValueError("need height_rms >= 0, n_modes >= 1 and a positive wavelength range")
        rng = np.random.default_rng(np.random.SeedSequence([int(seed), 7919]))
        wavelength = rng.uniform(wavelength_range[0], wavelength_range[1], size=n_modes)
        azimuth = rng.uniform(0.0, 2.0 * math.pi, size=n_modes)
        phase = rng.uniform(0.0, 2.0 * math.pi, size=n_modes)
        k = 2.0 * math.pi / wavelength
        amp = np.full(n_modes, height_rms * math.sqrt(2.0 / n_modes))
        mounds = np.column_stack([amp, k * np.cos(azimuth), k * np.sin(azimuth), phase])
        return replace(self, surround_mounds=mounds)


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

    def point_at(self, s) -> np.ndarray:
        """Point(s) on the straight ball->hole line, ``s`` [m] from the ball
        (0 = ball, ``distance`` = hole).  Scalar -> (2,), array (n,) -> (n, 2)."""
        s = np.asarray(s, dtype=float)
        unit = (self.hole_xy - self.ball_xy) / self.distance
        return self.ball_xy + s[..., None] * unit

    def without_fringe(self) -> "PuttScenario":
        """The same putt on the no-fringe twin of the green
        (see :meth:`Green.without_fringe`)."""
        return replace(self, green=self.green.without_fringe())


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

    # ---- surrounds (analytic, on top of the rolling surface: Green.surround_dz)
    surround_slope = _uniform(rng, prm.surround_slope_range)
    surround_amp = np.array([rng.uniform(0.0, a) for a in prm.surround_harmonic_amp_max])
    surround_phase = rng.uniform(0.0, 2.0 * math.pi, size=2)
    if surround_amp.shape != (2,):
        raise ValueError("surround_harmonic_amp_max must hold two amplitudes")
    if not (prm.surround_onset > 0.0):
        raise ValueError("surround_onset must be positive [m]")

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
    flagstick_height = _uniform(rng, prm.flagstick_height_range)

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
        surround_amp=surround_amp,
        surround_phase=surround_phase,
        surround_onset=float(prm.surround_onset),
        flagstick_height=flagstick_height,
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
    surround_slope: float = 0.0,
    flagstick_height: float = DEFAULT_FLAGSTICK_HEIGHT,
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
    surround_slope : float [m/m]
        Extra radial slope of the terrain beyond the collar, the same at
        every azimuth (default 0: the surrounds continue the surface).
    flagstick_height : float [m]
        Visible height of the flagstick above the hole lip.
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
        surround_slope=float(surround_slope),
        stimp_ft=float(stimp_ft),
        grain=Grain() if grain is None else grain,
        flagstick_height=float(flagstick_height),
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
