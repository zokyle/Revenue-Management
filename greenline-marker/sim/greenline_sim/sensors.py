"""Sensor forward models: what the GreenLine hardware reports on a TRUE green.

Given the true :class:`~greenline_sim.greens.Green`, the marker position and
the hole, :func:`measure` produces a :class:`Measurements` object with exactly
the quantities the device can physically sense from ~5 mm above the turf, and
nothing else:

1. TILT of the puck (accelerometer): the local slope vector under the marker,
   corrupted by how the puck seats on the grass canopy (``sigma_seat``, the
   dominant error of the instrument) and by the device's own bias.
2. FLAGSTICK seen by the forward stereo pair: bearing, stereo disparity, the
   elevation of the lowest visible point of the stick and - when it is inside
   the upward field - the elevation of its top (for monocular ranging from
   the stick's angular height).  Whether the base of the stick is visible
   comes from a real line-of-sight test against the true surface.
3. TURF HORIZON: for each azimuth in the horizontal field, the maximum
   elevation of the grass silhouette along that ray, from ray-marching the
   true canopy (putting surface, +8 mm collar, +40 mm rough and the surround
   terrain).  From a grazing viewpoint this silhouette is ALL the far-field
   shape information there is.
4. GRAIN direction/strength (coarse photometric sensor).
5. STIMP entered by the golfer.

What the device can NOT measure, and what is therefore absent from
:class:`Measurements`: any range-resolved view of the surface between the ball
and the hole.  At camera height ``h`` the ground at distance ``d`` subtends
only ``h / d^2`` rad per metre, i.e. the whole green collapses onto the
horizon line.

Frames
------
* World frame: the green's frame (origin at the green centre).
* Device frame: origin at the marker, ``+x`` out of the visor (the direction
  the cameras look), ``+y`` to the left, angles CCW from ``+x``.  Everything
  in :class:`Measurements` is expressed in the device frame; the device does
  not know its world heading.
* Elevation angles are relative to the gravity-level plane through the lens.

All noise terms are named parameters of :class:`SensorParams`.  The random
numbers are drawn in a fixed order and scaled afterwards, so two calls with
the same seed and different noise parameters give *paired* results.

Assumptions that are NOT measurements of a real device (stated plainly):

* ``sigma_seat`` (2.5 mrad per axis) is an estimate; no published data exist
  for how a 46 mm puck seats on a putting surface.
* The flag-detection model, the tilt bias and the hand-pointing error are
  engineering guesses with named parameters.
* ``flag_base_visible`` is reported from the true line-of-sight test.  A real
  device has to *infer* it; ``p_base_misclass`` lets a caller test what
  happens when it cannot.
* Nothing above the turf behind the green (trees, people, buildings) is
  modelled: the simulated horizon is terrain plus canopy only, and the device
  is assumed able to pick the turf silhouette out of the image.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

from .greens import Green
from .measurements import Measurements
from .physics import HOLE_R

__all__ = [
    "CameraPreset",
    "CAMERA_PRESETS",
    "GL1",
    "SensorParams",
    "Measurements",
    "MeasurementTruth",
    "HorizonTruth",
    "canopy_and_margin",
    "horizon_profile",
    "flag_sight_lines",
    "detection_probability",
    "measure",
    "survey_stations",
    "measure_survey",
]


# --------------------------------------------------------------------------
# Camera presets
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CameraPreset:
    """Geometry of the forward stereo pair.

    Attributes
    ----------
    name : str
    f_px : float [px]
        Focal length in pixels.
    baseline : float [m]
        Stereo baseline.
    h_cam : float [m]
        Height of the optical axis above the base plane of the puck (the
        plane that rests on the turf).  The lens sits lower than this above
        the true turf surface by the unknown amount the puck sinks into the
        canopy (``SensorParams.sink_max``).
    half_fov_h : float [rad]
        Half of the horizontal field of view.
    up_fov : float [rad]
        Usable field above the level plane (the flagstick top must be inside
        it for monocular ranging).
    """

    name: str
    f_px: float
    baseline: float
    h_cam: float
    half_fov_h: float
    up_fov: float


GL1 = CameraPreset(
    name="GL1",
    f_px=657.0,
    baseline=0.0204,
    h_cam=0.0056,
    half_fov_h=math.radians(26.0),
    up_fov=math.radians(17.6),
)
"""The fixed GL-1 hardware (design/master_params.yaml): OVM7692 cubes with fold
prisms, f = 657 px, 20.4 mm baseline, optical axis 5.6 mm above the base."""

CAMERA_PRESETS: Dict[str, CameraPreset] = {
    "GL1": GL1,
    # Sensitivity presets from the original concept (34 mm baseline, +-40 deg
    # field, lens 4.5 mm above the base).  They are NOT buildable in the GL-1
    # envelope; they exist to show how results move with the optics.
    "QVGA": CameraPreset("QVGA", 330.0, 0.034, 0.0045, math.radians(40.0), math.radians(17.6)),
    "VGA": CameraPreset("VGA", 500.0, 0.034, 0.0045, math.radians(40.0), math.radians(17.6)),
    "2MP": CameraPreset("2MP", 1200.0, 0.034, 0.0045, math.radians(40.0), math.radians(17.6)),
}
"""Camera presets by name.  ``GL1`` is the default; the others are sensitivity
presets only."""


# --------------------------------------------------------------------------
# Parameters
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SensorParams:
    """Every noise and geometry term of the sensor models (SI units, radians).

    Attributes
    ----------
    camera : CameraPreset
    sink_max : float [m]
        The puck sinks an unknown amount ``U(0, sink_max)`` into the canopy,
        lowering the lens by that much.
    sigma_seat : float [rad per axis]
        Seating noise: random tilt of the puck relative to the true local
        slope, per placement.  ESTIMATE, no published data.
    seat_repeat_correlation : float in [0, 1]
        Correlation of the seating error between the two readings of a
        180-degree spin-and-reread (0 = independent seatings, the assumption
        the Precision Read relies on; > 0 = part of the error is a property
        of the turf spot and does not average out).
    sigma_tilt_bias : float [rad per axis]
        Device bias of the tilt reading (accelerometer offset and its
        alignment to the base plane after cradle calibration, including
        thermal drift).  Fixed in the device frame; cancelled by the spin.
    sigma_gravity : float [rad per axis]
        Noise of the gravity direction: sensor noise on each tilt reading and
        on the level reference of the cameras.
    sigma_boresight : float [rad per axis]
        Residual camera-to-accelerometer boresight error (pitch and roll).
    sigma_pixel_elev : float [px]
        Pixel noise on every measured elevation (flag base, flag top,
        horizon samples).
    sigma_disp : float [px]
        Stereo disparity noise on the flagstick.
    sigma_bearing : float [rad]
        Noise of the measured flagstick bearing (pixel noise, stick lean and
        its play in the cup).
    sigma_heading : float [rad]
        How well the golfer points the visor at the flag in a camera read
        (irrelevant to the result as long as the flag is in the field).
    sigma_hand_bearing : float [rad]
        Flag-out fallback: how well the golfer points the visor at the hole
        by hand; this IS the bearing error in that mode.
    sigma_user_distance : float [relative]
        Flag-out fallback: error of the distance the golfer dials in.
    n_horizon : int
        Number of horizon azimuth samples across the horizontal field.
    horizon_d_min : float [m]
        Nearest ground distance the horizon ray-march looks at.
    sigma_mirage : float [1/m]
        Ray-curvature term ``c ~ N(0, sigma_mirage)``: a ground point at
        distance ``d`` appears displaced vertically by ``0.5 c d^2``.
    p_detect_fail_floor : float
        Probability of missing the flagstick regardless of range (clutter,
        glare, dirty window).
    stick_diameter : float [m]
        Flagstick diameter used by the detection model.
    detect_min_width_px : float [px]
        Stick image width at which detection becomes unreliable.
    detect_exponent : float
        Sharpness of the fall-off: ``p = (1 - floor) exp(-(D / D0)^n)`` with
        ``D0 = f_px * stick_diameter / detect_min_width_px``.
    base_hidden_tolerance : float [m]
        A base hidden by less than this much stick (well below the height
        noise) is reported as visible.
    p_base_misclass : float
        Probability that the device reports the wrong ``flag_base_visible``.
    stick_height_learned : bool
        True: the device has learned this course's stick height to
        ``stick_height_rel_error``.  False: first hole, default prior.
    stick_height_rel_error : float [relative]
    stick_height_default : float [m];  stick_height_default_rel_error : float
        The default prior and its 1-sigma relative error.
    sigma_grain_azimuth : float [rad];  sigma_grain_strength : float [relative]
    sigma_stimp : float [relative]
        Error of the green speed the golfer enters.
    sigma_survey_lateral : float [m]
        Survey mode: lateral distance of a drop from the true ball->hole line.
    sigma_survey_along : float [m]
        Survey mode: how well the golfer hits the intended station along the
        line (the device measures its own range, so this hardly matters).
    """

    camera: CameraPreset = GL1
    sink_max: float = 1.5e-3
    sigma_seat: float = 2.5e-3
    seat_repeat_correlation: float = 0.0
    sigma_tilt_bias: float = 1.0e-3
    sigma_gravity: float = 0.3e-3
    sigma_boresight: float = 0.3e-3
    sigma_pixel_elev: float = 0.15
    sigma_disp: float = 0.08
    sigma_bearing: float = 1.0e-3
    sigma_heading: float = math.radians(10.0)
    sigma_hand_bearing: float = math.radians(1.5)
    sigma_user_distance: float = 0.10
    n_horizon: int = 41
    horizon_d_min: float = 0.15
    sigma_mirage: float = 5.0e-5
    p_detect_fail_floor: float = 0.02
    stick_diameter: float = 0.0127
    detect_min_width_px: float = 0.35
    detect_exponent: float = 4.0
    base_hidden_tolerance: float = 0.002
    p_base_misclass: float = 0.0
    stick_height_learned: bool = True
    stick_height_rel_error: float = 0.02
    stick_height_default: float = 2.13
    stick_height_default_rel_error: float = 0.07
    sigma_grain_azimuth: float = math.radians(20.0)
    sigma_grain_strength: float = 0.30
    sigma_stimp: float = 0.07
    sigma_survey_lateral: float = 0.05
    sigma_survey_along: float = 0.20


# --------------------------------------------------------------------------
# Truth records (evaluation only)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class HorizonTruth:
    """Noise-free turf horizon from the ray-march (see :func:`horizon_profile`).

    Attributes
    ----------
    ratio : (n,) array [m/m]
        ``max over d of (canopy_z(d) - cam_z + 0.5 c d^2) / d`` per azimuth
        (the tangent of the silhouette's elevation angle).
    distance : (n,) array [m]
        Ground distance at which that maximum occurs.
    region : (n,) int array
        What forms the silhouette there: ``REGION_GREEN`` (0, the putting
        surface itself), ``REGION_COLLAR`` (1) or ``REGION_ROUGH`` (2, rough
        and surrounds).
    """

    ratio: np.ndarray
    distance: np.ndarray
    region: np.ndarray


@dataclass(frozen=True)
class MeasurementTruth:
    """The truth behind one :class:`Measurements`.  For the Monte Carlo and
    the tests ONLY - the estimator must never be given this object.

    Attributes
    ----------
    marker_xy, hole_xy : (2,) arrays [m] (world)
    heading : float [rad]
        World azimuth of the device ``+x`` axis.
    bearing : float [rad];  distance : float [m]
        True world azimuth and length of the marker->hole line.
    cam_height : float [m];  sink : float [m]
        True lens height above the turf surface at the marker, and the sink.
    mirage_c : float [1/m]
    slope_world : (2,) array [m/m]
        True surface gradient at the marker (world frame).
    seat_error_world : (2,) array [rad]
        Seating error actually applied (world frame; the mean of the two
        seatings for a spin read).
    tilt_bias : (2,) array [rad]
        Device tilt bias (device frame).
    level_error : (2,) array [rad]
        (pitch, roll) error of the cameras' level reference.
    base_visible : bool
        True line-of-sight result (before any misclassification).
    hidden_height : float [m]
        Length of stick hidden behind the crest (0 if the base is visible).
    dz_hole : float [m]
        True ``z_hole - z_marker``.
    in_fov : bool;  p_detect : float
        Whether the flag is inside the horizontal field, and the detection
        probability given that it is.
    horizon : HorizonTruth or None
    """

    marker_xy: np.ndarray
    hole_xy: np.ndarray
    heading: float
    bearing: float
    distance: float
    cam_height: float
    sink: float
    mirage_c: float
    slope_world: np.ndarray
    seat_error_world: np.ndarray
    tilt_bias: np.ndarray
    level_error: np.ndarray
    base_visible: bool
    hidden_height: float
    dz_hole: float
    in_fov: bool
    p_detect: float
    horizon: Optional[HorizonTruth] = None


# --------------------------------------------------------------------------
# Geometry of the grazing view
# --------------------------------------------------------------------------


def _wrap(angle: float) -> float:
    """Wrap an angle to (-pi, pi]."""
    return math.atan2(math.sin(angle), math.cos(angle))


def canopy_and_margin(green: Green, x, y) -> Tuple[np.ndarray, np.ndarray]:
    """Visible grass-top height and radial margin at ``(x, y)`` [m].

    Returns ``(canopy_z, margin)`` where ``canopy_z`` equals
    :meth:`Green.canopy_z` and ``margin`` equals :meth:`Green.radial_margin`
    (positive on the putting surface, negative beyond its edge).  One pass
    over the boundary geometry instead of three; the equality with the
    ``Green`` methods is covered by a test.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    theta = np.arctan2(y, x)
    radius = np.hypot(x, y)
    margin = np.asarray(green.edge_radius(theta)) - radius
    beyond = np.maximum(-margin - green.collar_width, 0.0)  # distance beyond the collar
    surround = np.asarray(green.surround_slope_at(theta)) * beyond**3 / (beyond * beyond + green.surround_onset**2)
    if green.surround_mounds is not None:
        surround = surround + np.asarray(green.mound_field(x, y)) * beyond * beyond / (beyond * beyond + green.surround_onset**2)
    step = np.where(margin >= 0.0, 0.0, np.where(margin >= -green.collar_width, green.collar_step, green.rough_step))
    return np.asarray(green.surface.z(x, y)) + surround + step, margin


_RAY_D_LIMIT = 80.0  # [m] longest ray the cached distance grid covers
_BISECTIONS = 22  # halvings of a <= 0.25 m bracket: canopy steps located to < 1e-7 m
_REFINE_FRACTIONS = np.linspace(0.0, 1.0, 33)  # local resampling of the horizon maximum


@lru_cache(maxsize=8)
def _ray_distance_grid(d_min: float) -> np.ndarray:
    """Ground distances sampled along a horizon ray [m], from ``d_min`` out
    to ``_RAY_D_LIMIT``.

    Steps grow as 3 % of the distance, clipped to 0.01 ... 0.25 m: the
    silhouette ratio ``(z - z_cam) / d`` varies fast near the lens and slowly
    far away.  (The canopy steps are located exactly, separately; a test
    checks the result against a 2 mm brute-force march.)
    """
    out = [d_min]
    while out[-1] < _RAY_D_LIMIT:
        out.append(out[-1] + min(max(0.03 * out[-1], 0.01), 0.25))
    arr = np.array(out, dtype=float)
    arr.setflags(write=False)
    return arr


def _ray_distances(d_min: float, d_max: float) -> np.ndarray:
    """The cached grid cut just beyond ``d_max`` [m]."""
    if d_max > _RAY_D_LIMIT:
        raise ValueError(f"horizon rays longer than {_RAY_D_LIMIT} m are not supported")
    grid = _ray_distance_grid(d_min)
    return grid[: int(np.searchsorted(grid, d_max)) + 1]


def horizon_profile(
    green: Green,
    cam_xy,
    cam_z: float,
    azimuths,
    *,
    d_min: float = 0.15,
    d_max: Optional[float] = None,
    mirage_c: float = 0.0,
) -> HorizonTruth:
    """Turf horizon seen from a lens at ``cam_xy`` [m], height ``cam_z`` [m].

    For each world azimuth the ray is marched over the true canopy
    (:meth:`Green.canopy_z`) from ``d_min`` out to where it leaves the
    modelled terrain (:attr:`Green.model_radius`), or to ``d_max`` if given,
    and the largest value of

        (canopy_z(d) - cam_z + 0.5 * mirage_c * d^2) / d

    is returned together with where it occurs and what forms it.  The march
    step grows with distance (1 cm near the lens, 25 cm far away); the
    maximum found is then refined on a 32-fold finer local grid, and the
    jumps of the canopy at the green edge and at the outer edge of the
    collar are located by bisection and sampled on both sides.  Agreement
    with a 2 mm brute-force march: better than 1e-5 rad (see the tests).

    Parameters
    ----------
    green : Green
    cam_xy : (2,) [m] world;  cam_z : float [m]
    azimuths : (n,) array [rad], world azimuths of the rays
    d_min : float [m];  d_max : float [m] or None
    mirage_c : float [1/m]

    Returns
    -------
    HorizonTruth
    """
    cam_xy = np.asarray(cam_xy, dtype=float)
    az = np.atleast_1d(np.asarray(azimuths, dtype=float))
    ux = np.cos(az)
    uy = np.sin(az)
    r_model = green.model_radius
    r_cam2 = float(cam_xy @ cam_xy)
    if r_cam2 >= r_model * r_model:
        raise ValueError("camera is outside the modelled terrain")
    # distance at which each ray leaves the circle of modelled terrain
    proj = cam_xy[0] * ux + cam_xy[1] * uy
    d_exit = -proj + np.sqrt(proj * proj + (r_model * r_model - r_cam2))
    if d_max is not None:
        d_exit = np.minimum(d_exit, float(d_max))
    if np.any(d_exit <= d_min):
        raise ValueError("d_max must exceed d_min")

    d = _ray_distances(float(d_min), float(np.max(d_exit)))
    dd = np.minimum(d[None, :], d_exit[:, None])  # (rays, samples); clamped at the exit
    x = cam_xy[0] + dd * ux[:, None]
    y = cam_xy[1] + dd * uy[:, None]
    canopy, margin = canopy_and_margin(green, x, y)
    ratio = (canopy - cam_z) / dd + 0.5 * mirage_c * dd
    k = np.argmax(ratio, axis=1)
    rows = np.arange(az.size)
    best = ratio[rows, k]
    best_d = dd[rows, k]

    # refine the smooth maximum: resample finely between the neighbours of the best coarse sample
    d_lo = dd[rows, np.maximum(k - 1, 0)]
    d_hi = dd[rows, np.minimum(k + 1, dd.shape[1] - 1)]
    fine = d_lo[:, None] + (d_hi - d_lo)[:, None] * _REFINE_FRACTIONS[None, :]
    c_fine, _ = canopy_and_margin(green, cam_xy[0] + fine * ux[:, None], cam_xy[1] + fine * uy[:, None])
    r_fine = (c_fine - cam_z) / fine + 0.5 * mirage_c * fine
    kf = np.argmax(r_fine, axis=1)
    better = r_fine[rows, kf] > best
    best = np.where(better, r_fine[rows, kf], best)
    best_d = np.where(better, fine[rows, kf], best_d)

    # exact samples on both sides of the two canopy steps (green edge, outer
    # edge of the collar) along each ray: bisect every sign change of
    # ``margin + offset`` between neighbouring samples
    ray_parts, lo_parts, hi_parts, off_parts, sign_parts = [], [], [], [], []
    for offset in (0.0, green.collar_width):
        f = margin + offset
        ray_i, seg_j = np.nonzero((f[:, :-1] > 0.0) != (f[:, 1:] > 0.0))
        ray_parts.append(ray_i)
        lo_parts.append(dd[ray_i, seg_j])
        hi_parts.append(dd[ray_i, seg_j + 1])
        off_parts.append(np.full(ray_i.size, offset))
        sign_parts.append(f[ray_i, seg_j] > 0.0)
    ray_i = np.concatenate(ray_parts)
    if ray_i.size:
        lo = np.concatenate(lo_parts)
        hi = np.concatenate(hi_parts)
        off = np.concatenate(off_parts)
        sign_lo = np.concatenate(sign_parts)
        cx = cam_xy[0]
        cy = cam_xy[1]
        uxi = ux[ray_i]
        uyi = uy[ray_i]
        for _ in range(_BISECTIONS):
            mid = 0.5 * (lo + hi)
            m_mid = np.asarray(green.radial_margin(cx + mid * uxi, cy + mid * uyi))
            same = ((m_mid + off) > 0.0) == sign_lo
            lo = np.where(same, mid, lo)
            hi = np.where(same, hi, mid)
        d_side = np.concatenate([lo, hi])
        ray_side = np.concatenate([ray_i, ray_i])
        c_side, _ = canopy_and_margin(green, cx + d_side * ux[ray_side], cy + d_side * uy[ray_side])
        r_side = (c_side - cam_z) / d_side + 0.5 * mirage_c * d_side
        for i, r_val, d_val in zip(ray_side, r_side, d_side):
            if r_val > best[i]:
                best[i] = r_val
                best_d[i] = d_val

    region = np.asarray(green.region(cam_xy[0] + best_d * ux, cam_xy[1] + best_d * uy))
    return HorizonTruth(ratio=best, distance=best_d, region=np.atleast_1d(region).astype(int))


def flag_sight_lines(
    green: Green,
    cam_xy,
    cam_z: float,
    hole_xy,
    *,
    d_min: float = 0.15,
    mirage_c: float = 0.0,
    step: float = 0.02,
) -> Tuple[float, float]:
    """Sight lines from the lens toward the flagstick.

    Returns ``(base_ratio, crest_ratio)``:

    * ``base_ratio = (z_hole - cam_z + 0.5 c D^2) / D`` - tangent of the
      elevation of the hole lip (the base of the stick);
    * ``crest_ratio`` - the largest ``(canopy_z(d) - cam_z + 0.5 c d^2) / d``
      over the ground between the lens and the near lip of the hole
      (``d_min <= d <= D - HOLE_R``); ``-inf`` if there is no ground in
      between.

    The base is visible iff ``crest_ratio < base_ratio``; otherwise the stick
    emerges at the crest and its lowest visible point lies at ``crest_ratio``.
    """
    cam_xy = np.asarray(cam_xy, dtype=float)
    hole_xy = np.asarray(hole_xy, dtype=float)
    delta = hole_xy - cam_xy
    dist = float(np.hypot(delta[0], delta[1]))
    if not dist > 0.0:
        raise ValueError("marker and hole coincide")
    z_hole = float(green.z(hole_xy[0], hole_xy[1]))
    base = (z_hole - cam_z) / dist + 0.5 * mirage_c * dist
    d_end = dist - HOLE_R
    if d_end <= d_min:
        return base, -math.inf
    n = max(2, int(math.ceil((d_end - d_min) / step)) + 1)
    d = np.linspace(d_min, d_end, n)
    ux, uy = delta / dist
    canopy, _ = canopy_and_margin(green, cam_xy[0] + d * ux, cam_xy[1] + d * uy)
    crest = float(np.max((canopy - cam_z) / d + 0.5 * mirage_c * d))
    return base, crest


def detection_probability(distance, params: SensorParams):
    """Probability that the flagstick is detected at ``distance`` [m], given
    that it is inside the horizontal field.

    ``p = (1 - floor) * exp(-(D / D0)^n)`` with
    ``D0 = f_px * stick_diameter / detect_min_width_px`` - the range at which
    the stick's image is ``detect_min_width_px`` wide.  An engineering guess
    (long thin vertical line, matched filter); GL1: D0 = 23.8 m, so about
    98 % at 6 m, 96 % at 9 m and 92 % at 12 m.
    """
    d0 = params.camera.f_px * params.stick_diameter / params.detect_min_width_px
    out = (1.0 - params.p_detect_fail_floor) * np.exp(-((np.asarray(distance, dtype=float) / d0) ** params.detect_exponent))
    return float(out) if np.ndim(out) == 0 else out


# --------------------------------------------------------------------------
# The measurement
# --------------------------------------------------------------------------

_N_NORMAL = 32
_N_UNIFORM = 4

RngLike = Union[int, np.integer, np.random.Generator]


def _as_rng(rng: RngLike) -> np.random.Generator:
    if isinstance(rng, np.random.Generator):
        return rng
    if isinstance(rng, (int, np.integer)) and not isinstance(rng, bool):
        return np.random.default_rng(int(rng))
    raise TypeError("rng must be an int seed or a numpy Generator")


def measure(
    green: Green,
    marker_xy,
    hole_xy,
    params: SensorParams = SensorParams(),
    rng: RngLike = 0,
    *,
    mode: str = "camera",
    spin: bool = False,
    with_horizon: bool = True,
    tilt_bias: Optional[Sequence[float]] = None,
    entered: Optional[Measurements] = None,
) -> Tuple[Measurements, MeasurementTruth]:
    """Simulate one placement of the marker.

    Parameters
    ----------
    green : Green
        The TRUE green.
    marker_xy, hole_xy : (2,) [m] world
        Marker (lens) position and hole centre.  The marker replaces the
        ball, so for a normal read ``marker_xy`` is the ball position.
    params : SensorParams
    rng : int seed or numpy Generator
        A fixed number of variates is drawn first, in a fixed order, and
        scaled by the parameters afterwards; the horizon noise is drawn last.
    mode : ``"camera"`` or ``"flag_out"``
        ``"camera"``: the golfer points the visor roughly at the flag
        (``sigma_heading``) and the cameras find it.  ``"flag_out"``: no
        flagstick; the golfer points the visor at the hole by hand
        (``sigma_hand_bearing``) and dials in the distance.
    spin : bool
        Precision Read: after the first reading the marker is spun 180
        degrees in place and read again.  The two tilt readings are combined
        (device bias cancels, two seatings are averaged); the camera data
        come from the first orientation.
    with_horizon : bool
        Capture the turf horizon (the expensive ray-march).  False leaves the
        horizon arrays empty.
    tilt_bias : (2,) [rad], optional
        Use this device tilt bias instead of drawing one (a Survey uses the
        same device for every drop).
    entered : Measurements, optional
        Copy the golfer's entry and the device state (``stimp_ft`` and the
        stick-height estimate) from an earlier reading instead of drawing
        them again (later drops of a Survey).

    Returns
    -------
    (Measurements, MeasurementTruth)
        The second item is the truth for evaluation only.
    """
    if mode not in ("camera", "flag_out"):
        raise ValueError("mode must be 'camera' or 'flag_out'")
    gen = _as_rng(rng)
    zn = gen.standard_normal(_N_NORMAL)
    un = gen.random(_N_UNIFORM)
    cam = params.camera
    marker_xy = np.asarray(marker_xy, dtype=float).copy()
    hole_xy = np.asarray(hole_xy, dtype=float).copy()
    if marker_xy.shape != (2,) or hole_xy.shape != (2,):
        raise ValueError("marker_xy and hole_xy must be (x, y) positions")
    delta = hole_xy - marker_xy
    dist = float(np.hypot(delta[0], delta[1]))
    if not dist > 0.0:
        raise ValueError("marker and hole coincide")
    bearing = math.atan2(delta[1], delta[0])

    # ---- pose ----------------------------------------------------------------
    sigma_point = params.sigma_heading if mode == "camera" else params.sigma_hand_bearing
    heading = bearing + sigma_point * zn[0]
    ch, sh = math.cos(heading), math.sin(heading)
    sink = params.sink_max * un[0]
    cam_height = cam.h_cam - sink
    if cam_height <= 0.0:
        raise ValueError("lens would be at or below the turf surface (h_cam <= sink)")
    z_marker = float(green.z(marker_xy[0], marker_xy[1]))
    cam_z = z_marker + cam_height
    mirage_c = params.sigma_mirage * zn[17]

    # ---- tilt ----------------------------------------------------------------
    gx, gy = green.grad(marker_xy[0], marker_xy[1])
    slope_world = np.array([float(gx), float(gy)])
    rho = min(max(params.seat_repeat_correlation, 0.0), 1.0)
    seat_common = math.sqrt(rho) * zn[5:7]
    seat_1 = params.sigma_seat * (seat_common + math.sqrt(1.0 - rho) * zn[1:3])
    seat_2 = params.sigma_seat * (seat_common + math.sqrt(1.0 - rho) * zn[3:5])
    if tilt_bias is None:
        bias = params.sigma_tilt_bias * zn[7:9]
    else:
        bias = np.asarray(tilt_bias, dtype=float).copy()
        if bias.shape != (2,):
            raise ValueError("tilt_bias must have shape (2,)")

    def to_device(vec):
        return np.array([vec[0] * ch + vec[1] * sh, -vec[0] * sh + vec[1] * ch])

    read_1 = to_device(slope_world + seat_1) + bias + params.sigma_gravity * zn[9:11]
    if spin:
        # device turned by pi: it reads minus the (world) slope in its own axes, plus the same bias
        read_2 = -to_device(slope_world + seat_2) + bias + params.sigma_gravity * zn[11:13]
        tilt = 0.5 * (read_1 - read_2)
        seat_applied = 0.5 * (seat_1 + seat_2)
        tilt_reads = 2
    else:
        tilt = read_1
        seat_applied = seat_1
        tilt_reads = 1

    # ---- level reference of the cameras -----------------------------------------
    pitch_err = params.sigma_gravity * zn[13] + params.sigma_boresight * zn[15]
    roll_err = params.sigma_gravity * zn[14] + params.sigma_boresight * zn[16]
    pix = params.sigma_pixel_elev / cam.f_px  # [rad] per-sample elevation noise

    # ---- flagstick -----------------------------------------------------------------
    bearing_dev = _wrap(bearing - heading)
    z_hole = float(green.z(hole_xy[0], hole_xy[1]))
    base_ratio, crest_ratio = flag_sight_lines(
        green, marker_xy, cam_z, hole_xy, d_min=params.horizon_d_min, mirage_c=mirage_c
    )
    hidden_height = max(0.0, (crest_ratio - base_ratio) * dist)
    base_visible_true = hidden_height <= params.base_hidden_tolerance
    in_fov = abs(bearing_dev) <= cam.half_fov_h
    p_detect = detection_probability(dist, params)
    found = bool(mode == "camera" and in_fov and un[1] < p_detect)

    if found:
        common = pitch_err + roll_err * math.sin(bearing_dev)
        flag_bearing = bearing_dev + params.sigma_bearing * zn[18]
        flag_disparity = cam.f_px * cam.baseline / dist + params.sigma_disp * zn[19]
        flag_low_elev = math.atan(max(base_ratio, crest_ratio)) + common + pix * zn[20]
        flag_base_visible = base_visible_true
        if un[2] < params.p_base_misclass:
            flag_base_visible = not flag_base_visible
        top_true = math.atan2(z_hole + green.flagstick_height - cam_z, dist)
        flag_top_visible = bool(top_true <= cam.up_fov)
        flag_top_elev = top_true + common + pix * zn[21] if flag_top_visible else math.nan
    else:
        flag_bearing = math.nan
        flag_disparity = math.nan
        flag_low_elev = math.nan
        flag_base_visible = False
        flag_top_visible = False
        flag_top_elev = math.nan

    # ---- device state and golfer entries ---------------------------------------------
    if entered is not None:
        stick_est = entered.stick_height_est
        stick_sigma = entered.stick_height_rel_sigma
        stimp_entered = entered.stimp_ft
    else:
        if params.stick_height_learned:
            stick_est = green.flagstick_height * (1.0 + params.stick_height_rel_error * zn[22])
            stick_sigma = params.stick_height_rel_error
        else:
            stick_est = params.stick_height_default
            stick_sigma = params.stick_height_default_rel_error
        stimp_entered = max(1.0, green.stimp_ft * (1.0 + params.sigma_stimp * zn[25]))
    # the photometric grain reading is taken afresh at every placement
    grain_kappa = max(0.0, green.grain.kappa * (1.0 + params.sigma_grain_strength * zn[24]))
    grain_azimuth = _wrap(green.grain.azimuth + params.sigma_grain_azimuth * zn[23] - heading)
    user_distance = dist * (1.0 + params.sigma_user_distance * zn[26]) if mode == "flag_out" else math.nan

    # ---- turf horizon -------------------------------------------------------------------
    horizon_truth = None
    if with_horizon and mode == "camera":
        n_h = int(params.n_horizon)
        if n_h < 2:
            raise ValueError("n_horizon must be at least 2")
        zh = gen.standard_normal(n_h)
        az_dev = np.linspace(-cam.half_fov_h, cam.half_fov_h, n_h)
        horizon_truth = horizon_profile(
            green, marker_xy, cam_z, heading + az_dev, d_min=params.horizon_d_min, mirage_c=mirage_c
        )
        horizon_az = az_dev
        horizon_elev = np.arctan(horizon_truth.ratio) + pitch_err + roll_err * np.sin(az_dev) + pix * zh
    else:
        horizon_az = np.zeros(0)
        horizon_elev = np.zeros(0)

    meas = Measurements(
        f_px=cam.f_px,
        baseline=cam.baseline,
        h_cam=cam.h_cam,
        tilt=tilt,
        tilt_reads=tilt_reads,
        flag_found=found,
        flag_bearing=float(flag_bearing),
        flag_disparity=float(flag_disparity),
        flag_low_elev=float(flag_low_elev),
        flag_base_visible=bool(flag_base_visible),
        flag_top_visible=bool(flag_top_visible),
        flag_top_elev=float(flag_top_elev),
        stick_height_est=float(stick_est),
        stick_height_rel_sigma=float(stick_sigma),
        horizon_az=horizon_az,
        horizon_elev=horizon_elev,
        grain_kappa=float(grain_kappa),
        grain_azimuth=float(grain_azimuth),
        stimp_ft=float(stimp_entered),
        user_distance=float(user_distance),
    )
    truth = MeasurementTruth(
        marker_xy=marker_xy,
        hole_xy=hole_xy,
        heading=float(heading),
        bearing=float(bearing),
        distance=dist,
        cam_height=float(cam_height),
        sink=float(sink),
        mirage_c=float(mirage_c),
        slope_world=slope_world,
        seat_error_world=np.asarray(seat_applied, dtype=float),
        tilt_bias=np.asarray(bias, dtype=float),
        level_error=np.array([pitch_err, roll_err]),
        base_visible=bool(base_visible_true),
        hidden_height=float(hidden_height),
        dz_hole=z_hole - z_marker,
        in_fov=bool(in_fov),
        p_detect=float(p_detect),
        horizon=horizon_truth,
    )
    return meas, truth


# --------------------------------------------------------------------------
# Survey mode
# --------------------------------------------------------------------------


def survey_stations(distance: float, n_drops: int = 3) -> np.ndarray:
    """Intended stations of the Survey drops, in metres from the ball along
    the ball->hole line.

    Drop 0 is at the ball, drop 1 at the midpoint, drop 2 one metre short of
    the hole - but never closer to the ball than ``0.75 * distance``, so that
    on putts shorter than 4 m the third drop still lies beyond the midpoint.
    """
    if n_drops not in (1, 2, 3):
        raise ValueError("n_drops must be 1, 2 or 3")
    if not distance > 0.0:
        raise ValueError("distance must be positive [m]")
    stations = [0.0, 0.5 * distance, max(distance - 1.0, 0.75 * distance)]
    return np.array(stations[:n_drops])


def measure_survey(
    green: Green,
    ball_xy,
    hole_xy,
    params: SensorParams = SensorParams(),
    rng: RngLike = 0,
    *,
    n_drops: int = 3,
    first: Optional[Tuple[Measurements, MeasurementTruth]] = None,
    max_retries: int = 3,
) -> List[Tuple[Measurements, MeasurementTruth]]:
    """Simulate a Survey: up to three drops along the ball->hole line.

    Each drop is an independent placement (own seating noise, own heading
    error, own stereo range and bearing to the flag) made with the same
    device (same tilt bias, same stick-height estimate, same entered Stimp).
    Drops after the first are placed by eye: ``sigma_survey_along`` along the
    line and ``sigma_survey_lateral`` off it.  If the flag is not found at a
    drop the golfer re-places the marker (up to ``max_retries`` times); a
    drop that never finds the flag is left out of the returned list.  No
    horizon is captured in Survey mode.

    Parameters
    ----------
    first : (Measurements, MeasurementTruth), optional
        Use this reading as drop 0 instead of taking a new one (the Quick
        Read that was already made at the ball).

    Returns
    -------
    list of (Measurements, MeasurementTruth), drop 0 first.
    """
    gen = _as_rng(rng)
    ball_xy = np.asarray(ball_xy, dtype=float)
    hole_xy = np.asarray(hole_xy, dtype=float)
    delta = hole_xy - ball_xy
    dist = float(np.hypot(delta[0], delta[1]))
    unit = delta / dist
    left = np.array([-unit[1], unit[0]])
    if first is None:
        first = measure(green, ball_xy, hole_xy, params, gen, with_horizon=False)
    drops = [first]
    for station in survey_stations(dist, n_drops)[1:]:
        for _ in range(max_retries + 1):
            place = gen.standard_normal(2)
            s = float(np.clip(station + params.sigma_survey_along * place[0], 0.2, dist - 0.3))
            xy = ball_xy + s * unit + params.sigma_survey_lateral * place[1] * left
            drop = measure(
                green, xy, hole_xy, params, gen, with_horizon=False, tilt_bias=first[1].tilt_bias, entered=first[0]
            )
            if drop[0].flag_found:
                drops.append(drop)
                break
    return drops
