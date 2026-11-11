"""Putt physics reference for the GreenLine ball marker (SI units throughout).

Model
-----
A golf ball rolling without slipping on a gently sloped turf surface
``z(x, y)`` obeys, in the horizontal plane (small-slope approximation,
acceptable up to about 6 % slope),

    dv/dt = -a_r * v_hat  -  (5/7) * G * grad z(x, y)  +  a_grain

* ``a_r``      flat-green rolling deceleration [m/s^2], from the Stimpmeter
               reading: ``a_r = STIMP_V0**2 / (2 * S_ft * FT)``.
* ``(5/7) G``  gravity on a rolling solid sphere (2/7 of the weight component
               goes into spinning the ball up or down).
* ``a_grain``  ``kappa * a_r * g_hat``: grain modelled as a constant push along
               the grain direction ``g_hat`` (an "equivalent slope").  ``kappa``
               is 0 for no grain and roughly 0.05-0.15 for strong bermuda.

The ball comes to rest when its speed reaches zero at a place where the
slope-plus-grain drive ``|-(5/7) G grad z + a_grain|`` does not exceed
``a_r``.  Where the drive exceeds ``a_r`` (too steep for the green speed) the
ball cannot rest and keeps rolling; the integration is then cut off by
``t_max`` / ``r_max`` and reported with an explicit status.

Conventions
-----------
* Coordinates ``x, y`` [m] horizontal, ``z`` [m] up, right-handed.
* Angles in radians, counter-clockwise (CCW) from +x seen from above.
* The aim angle ``phi`` is measured from the straight ball->hole line,
  **positive = aim left** of the hole (CCW).
* "Left"/"right" of the hole are as seen from the ball looking at the hole.
* Speeds in m/s, accelerations in m/s^2, slopes as rise/run (0.01 = 1 %).

Numerics
--------
Classical RK4 with a fixed step ``dt`` (default 0.02 s) while the ball is
moving freely.  Near the stop the step is shortened by two rules:

* to half of the predicted time-to-stop when the ball is within two steps of
  stopping (so the speed roughly halves every step and the friction
  direction never flips inside a step);
* to ``0.5 * speed / a_r``.  The friction term ``-a_r * v_hat`` makes the
  velocity component across the drive decay at the rate ``a_r / speed``,
  which is unbounded as the ball stops; explicit RK4 is stable only for
  ``h * a_r / speed < 2.785``.  The first rule alone satisfies this only
  while the drive along the motion is below about 0.85 ``a_r``; on steeper
  (still holdable) slopes a ball stopping with the slope would otherwise
  zig-zag about the fall line and creep instead of coming to rest.

Below ``1e-4 m/s`` the last ~1e-8 m are closed analytically.  This gives a
jitter-free stop on every holdable slope; the rest position is converged to
~1e-8 m at the default step (checked up to a drive of 0.99 ``a_r``).  A roll
may take at most ``4 * t_max / dt`` steps: a ball still creeping then (only
possible within a fraction of a percent of the critical slope) is reported
as ``MAX_TIME`` like one that runs out of time.  Events inside a step
(closest approach to the hole, crossing of the hole line) are located on the
cubic Hermite segment through the step's end states, so they are as accurate
as the integration itself.

The same scalar kernels run either under numba (fast) or as plain Python
(see :mod:`greenline_sim._jit`); they are the reference for the C firmware.

Capture model (an assumption, after Holmes 1991 / Penner 2002)
---------------------------------------------------------------
The ball is holed if, at a closest approach to the hole centre (impact
parameter ``delta``), ``delta < HOLE_R`` and its speed is below
``V_CAP0 * (1 - (delta/HOLE_R)**2) ** exponent`` with ``V_CAP0 = 1.63 m/s``
(Holmes' dead-centre limit).  ``exponent = 0.5`` (default) scales the limit
with the chord of the hole the ball crosses; ``exponent = 1`` is Penner's
quadratic fit.  Lip-outs do not deflect the ball in this model.  A ball that
comes to rest with its centre inside the hole radius is holed.  The rule is
swappable: see :class:`CaptureModel` and the ``capture`` arguments.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass
from typing import Callable, Optional, Sequence, Tuple, Union

import numpy as np
from scipy import ndimage

from ._jit import HAVE_NUMBA, NUMBA_STATUS, njit, prange

__all__ = [
    "G",
    "STIMP_V0",
    "FT",
    "BALL_R",
    "HOLE_R",
    "V_CAP0",
    "ROLL_FACTOR",
    "DEFAULT_DT",
    "DEFAULT_T_MAX",
    "DEFAULT_R_MAX",
    "DEFAULT_PAST",
    "HAVE_NUMBA",
    "NUMBA_STATUS",
    "stimp_to_decel",
    "decel_to_stimp",
    "flat_roll_distance",
    "target_hole_speed",
    "critical_slope",
    "grain_equivalent_slope",
    "planar_break_angle",
    "planar_break_angle_paced",
    "Grain",
    "grain_vector",
    "Surface",
    "PlaneSurface",
    "QuadraticSurface",
    "GridSurface",
    "CaptureModel",
    "capture_speed_limit",
    "is_captured",
    "RollStatus",
    "SolveStatus",
    "PuttResult",
    "BatchRollResult",
    "AimSolution",
    "AimBatchSolution",
    "launch_velocity",
    "world_to_putt",
    "putt_to_world",
    "simulate_putt",
    "roll_batch",
    "solve_aim",
    "solve_aim_batch",
    "solve_aim_quadratic_batch",
    "DEFAULT_TOL_MISS",
    "DEFAULT_TOL_PACE",
    "DEFAULT_PHI_MAX",
    "DEFAULT_V_MAX",
    "DEFAULT_MAX_ROLLS",
]

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

G = 9.80665
"""Standard gravity [m/s^2]."""

STIMP_V0 = 1.83
"""Stimpmeter release speed [m/s] (6.00 ft/s)."""

FT = 0.3048
"""One foot [m]."""

BALL_R = 0.021335
"""Golf ball radius [m] (1.68 in diameter)."""

HOLE_R = 0.053975
"""Hole radius [m] (4.25 in diameter)."""

V_CAP0 = 1.63
"""Maximum capture speed for a dead-centre putt [m/s] (Holmes 1991)."""

ROLL_FACTOR = 5.0 / 7.0
"""Fraction of the along-slope gravity that accelerates a rolling solid sphere."""

DEFAULT_DT = 0.02
"""Default RK4 time step [s] (stop position converged to ~1e-8 m; see tests)."""

DEFAULT_T_MAX = 30.0
"""Default maximum simulated time [s] before a roll is reported as MAX_TIME."""

DEFAULT_R_MAX = 100.0
"""Default maximum distance from the start [m] before OUT_OF_BOUNDS."""

DEFAULT_PAST = 0.30
"""Default target pace: distance the ball would roll past the hole on a flat
green of the same speed [m]."""

# Kernel-private constants (module-level floats are compile-time constants
# for numba).
_KF = ROLL_FACTOR * G  # [m/s^2] gravity drive per unit slope
_S_TINY = 1e-12  # [m/s] below this the ball is treated as exactly at rest
_V_EPS = 1e-4  # [m/s] speed below which the stop is closed analytically
_H_STIFF = 0.5  # [-] largest step * a_r / speed (RK4 is stable below 2.785)
_STEP_BUDGET_FACTOR = 4  # a roll may take at most this many times t_max / dt steps
# Solver: a trial ball that crosses the (infinite) hole line further to the
# side than _LINE_MISS_OFFSET + _LINE_MISS_SLOPE * distance has not reached
# the hole (see _trial).
_LINE_MISS_OFFSET = 1.0  # [m]
_LINE_MISS_SLOPE = 0.5  # [m per m of putt length]

_KIND_QUAD = 0
_KIND_GRID = 1

_PARALLEL_MIN_BATCH = 16  # smaller batches run on the calling thread

# Roll status codes (floats inside the kernels, see RollStatus).
_ROLL_STOPPED = 0
_ROLL_MAX_TIME = 1
_ROLL_OUT_OF_BOUNDS = 2
_ROLL_CAPTURED = 3
_ROLL_AT_LINE = 4

# Layout of the kernel output record.
_O_STATUS = 0
_O_T = 1
_O_X = 2
_O_Y = 3
_O_VX = 4
_O_VY = 5
_O_DMIN = 6
_O_SMIN = 7
_O_TMIN = 8
_O_SIDE = 9
_O_CROSSED = 10
_O_YLINE = 11
_O_SLINE = 12
_O_TLINE = 13
_O_XPROG = 14
_O_YPROG = 15
_O_CAPT = 16
_O_TCAPT = 17
_O_PATH = 18
_O_NREC = 19
_O_NSTEP = 20
_O_SPROG = 21
_NOUT = 22

# Pace (inner) solve flags.
_PACE_OK = 0
_PACE_LIMITED = 1  # ball reaches the hole only faster than the target pace
_PACE_UNREACHABLE = 2  # ball cannot be made to reach the hole line

# Aim solve status codes (see SolveStatus).
_SOLVE_OK = 0
_SOLVE_PACE_LIMITED = 1
_SOLVE_UNREACHABLE = 2
_SOLVE_NO_BRACKET = 3
_SOLVE_NO_CONVERGENCE = 4
_SOLVE_INVALID = 5

# Layout of the solver result record.
_R_PHI = 0
_R_V0 = 1
_R_MISS = 2
_R_VHOLE = 3
_R_NROLLS = 4
_NRES = 5


# --------------------------------------------------------------------------
# Elementary relations
# --------------------------------------------------------------------------


def stimp_to_decel(stimp_ft):
    """Flat-green rolling deceleration ``a_r`` [m/s^2] for a Stimpmeter reading.

    A Stimpmeter releases the ball at ``STIMP_V0`` = 1.83 m/s and the reading
    ``stimp_ft`` [ft] is the roll-out distance on a flat green, so
    ``a_r = STIMP_V0**2 / (2 * stimp_ft * FT)``.  Stimp 10 -> 0.549 m/s^2.
    """
    stimp_ft = np.asarray(stimp_ft, dtype=float)
    if np.any(stimp_ft <= 0.0):
        raise ValueError("stimp_ft must be positive")
    out = STIMP_V0**2 / (2.0 * stimp_ft * FT)
    return float(out) if out.ndim == 0 else out


def decel_to_stimp(a_r):
    """Stimpmeter reading [ft] for a rolling deceleration ``a_r`` [m/s^2]."""
    a_r = np.asarray(a_r, dtype=float)
    if np.any(a_r <= 0.0):
        raise ValueError("a_r must be positive")
    out = STIMP_V0**2 / (2.0 * a_r * FT)
    return float(out) if out.ndim == 0 else out


def flat_roll_distance(v0, a_r):
    """Roll-out distance [m] on a flat green: ``v0**2 / (2 a_r)``.

    Applied to a solved launch speed this is the "plays-like" distance.
    """
    out = np.asarray(v0, dtype=float) ** 2 / (2.0 * np.asarray(a_r, dtype=float))
    return float(out) if out.ndim == 0 else out


def target_hole_speed(a_r, past=DEFAULT_PAST):
    """Arrival speed at the hole [m/s] for the "target pace".

    ``v_h = sqrt(2 a_r past)``: the speed that would carry the ball ``past``
    metres beyond the hole on a flat green of deceleration ``a_r``.
    """
    out = np.sqrt(2.0 * np.asarray(a_r, dtype=float) * np.asarray(past, dtype=float))
    return float(out) if out.ndim == 0 else out


def critical_slope(a_r):
    """Slope (rise/run) above which a ball cannot rest: ``a_r / ((5/7) G)``.

    Stimp 10 -> 7.8 %, Stimp 13 -> 6.0 % (no grain).
    """
    out = np.asarray(a_r, dtype=float) / _KF
    return float(out) if out.ndim == 0 else out


def grain_equivalent_slope(kappa, a_r):
    """Slope (rise/run) whose gravity drive equals a grain of strength ``kappa``.

    ``(5/7) G s_eq = kappa a_r``.  A grain pushing along ``g_hat`` is
    indistinguishable (in this model) from tilting the surface so that it
    falls by ``s_eq`` per metre along ``g_hat``, i.e. adding
    ``-s_eq * g_hat`` to ``grad z``.
    """
    out = np.asarray(kappa, dtype=float) * np.asarray(a_r, dtype=float) / _KF
    return float(out) if out.ndim == 0 else out


def planar_break_angle(cross_slope, a_r):
    """Small-slope aim angle [rad] for a putt that just dies at the hole.

    Plane with pure cross slope ``cross_slope`` (rise/run, positive = ground
    rises to the LEFT of the ball->hole line) and no grain:

        phi = (5/14) * G * cross_slope / a_r        (independent of distance)

    Positive ``phi`` = aim left, i.e. uphill.  First order in ``phi``.
    """
    out = 0.5 * _KF * np.asarray(cross_slope, dtype=float) / np.asarray(a_r, dtype=float)
    return float(out) if out.ndim == 0 else out


def planar_break_angle_paced(cross_slope, a_r, distance, past):
    """Small-slope aim angle [rad] on a cross-sloped plane with firm pace.

    Generalises :func:`planar_break_angle` to a putt hit to roll ``past``
    metres beyond a hole ``distance`` metres away (flat along the line):

        phi = (5/14) G s / a_r * F(rho),
        F(rho) = 1 - 2 rho^2 ln(1/rho) / (1 - rho^2),   rho^2 = past / (distance + past)

    ``rho = v_hole / v0``.  ``F -> 1`` for a dying putt and ``F -> 0`` for a
    putt hit infinitely hard.  Derived by integrating
    ``dv_y/dt = a_y - a_r v_y / v_x(t)`` with ``v_x = a_r (T - t)``.
    Reference point: 10 ft, 1 % cross slope, Stimp 10, 0.43 m past -> 0.137 m
    of aim offset at the hole.
    """
    distance = np.asarray(distance, dtype=float)
    past = np.asarray(past, dtype=float)
    rho2 = past / (distance + past)
    with np.errstate(divide="ignore", invalid="ignore"):
        f = np.where(rho2 > 0.0, 1.0 + rho2 * np.log(rho2) / (1.0 - rho2), 1.0)
    out = planar_break_angle(cross_slope, a_r) * f
    return float(out) if np.ndim(out) == 0 else out


# --------------------------------------------------------------------------
# Grain
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Grain:
    """Grain of the turf as a constant push on the ball.

    Attributes
    ----------
    kappa : float
        Dimensionless strength; the push is ``kappa * a_r`` [m/s^2].
        0 = no grain, ~0.05-0.15 = strong bermuda.
    azimuth : float
        Direction the grain pushes the ball [rad, CCW from +x] in the frame
        of the surface it is used with.
    """

    kappa: float = 0.0
    azimuth: float = 0.0

    @property
    def vector(self) -> np.ndarray:
        """``kappa * g_hat`` as a length-2 array (dimensionless)."""
        return np.array(
            [self.kappa * math.cos(self.azimuth), self.kappa * math.sin(self.azimuth)]
        )

    def rotated(self, frame_angle: float) -> "Grain":
        """Same grain expressed in a frame rotated by ``frame_angle`` [rad] CCW.

        Example: world -> putt frame uses ``frame_angle = bearing`` of the
        ball->hole line.
        """
        return Grain(self.kappa, self.azimuth - frame_angle)


GrainLike = Union[None, Grain, Sequence[float], np.ndarray]


def grain_vector(grain: GrainLike) -> np.ndarray:
    """Normalise a grain specification to ``kappa * g_hat`` (length-2 array).

    Accepts ``None`` (no grain), a :class:`Grain`, or a length-2 sequence
    ``(kappa*cos(az), kappa*sin(az))``.
    """
    if grain is None:
        return np.zeros(2)
    if isinstance(grain, Grain):
        return grain.vector
    vec = np.asarray(grain, dtype=float)
    if vec.shape != (2,):
        raise ValueError("grain must be None, a Grain, or a length-2 vector kappa*g_hat")
    return vec.copy()


# --------------------------------------------------------------------------
# Surface kernels (scalar; numba-compiled when available)
# --------------------------------------------------------------------------


@njit(cache=True)
def _grid_locate(p, x, y):
    """Cell index and local coordinates for the uniform bicubic B-spline grid.

    Returns ``(ib, jb, t, s, fx, fy)``: base indices into the padded
    coefficient array, fractional cell coordinates in [0, 1], and factors
    that are 0 where the query was clamped to the domain (constant
    extension outside the grid => zero gradient across the clamped axis).
    """
    nx = int(p[4])
    ny = int(p[5])
    pad = int(p[6])
    u = (x - p[0]) * p[2]
    v = (y - p[1]) * p[3]
    fx = 1.0
    fy = 1.0
    if u < 0.0:
        u = 0.0
        fx = 0.0
    elif u > nx - 1.0:
        u = nx - 1.0
        fx = 0.0
    if v < 0.0:
        v = 0.0
        fy = 0.0
    elif v > ny - 1.0:
        v = ny - 1.0
        fy = 0.0
    i = int(u)
    if i > nx - 2:
        i = nx - 2
    j = int(v)
    if j > ny - 2:
        j = ny - 2
    return i + pad - 1, j + pad - 1, u - i, v - j, fx, fy


@njit(cache=True)
def _bspline_w(t):
    """Uniform cubic B-spline basis weights for local coordinate ``t`` in [0, 1]."""
    omt = 1.0 - t
    t2 = t * t
    t3 = t2 * t
    return (
        omt * omt * omt / 6.0,
        (3.0 * t3 - 6.0 * t2 + 4.0) / 6.0,
        (-3.0 * t3 + 3.0 * t2 + 3.0 * t + 1.0) / 6.0,
        t3 / 6.0,
    )


@njit(cache=True)
def _bspline_dw(t):
    """Derivatives d/dt of the uniform cubic B-spline basis weights."""
    omt = 1.0 - t
    t2 = t * t
    return (
        -0.5 * omt * omt,
        1.5 * t2 - 2.0 * t,
        -1.5 * t2 + t + 0.5,
        0.5 * t2,
    )


@njit(cache=True)
def _grid_grad(p, c, x, y):
    """Gradient (dz/dx, dz/dy) of the bicubic B-spline grid surface."""
    ib, jb, t, s, fx, fy = _grid_locate(p, x, y)
    wx = _bspline_w(t)
    wy = _bspline_w(s)
    dwx = _bspline_dw(t)
    dwy = _bspline_dw(s)
    gx = 0.0
    gy = 0.0
    for k in range(4):
        r = 0.0
        dr = 0.0
        for m in range(4):
            cv = c[ib + k, jb + m]
            r += cv * wy[m]
            dr += cv * dwy[m]
        gx += dwx[k] * r
        gy += wx[k] * dr
    return gx * p[2] * fx, gy * p[3] * fy


@njit(cache=True)
def _grid_z(p, c, x, y):
    """Height z of the bicubic B-spline grid surface."""
    ib, jb, t, s, fx, fy = _grid_locate(p, x, y)
    wx = _bspline_w(t)
    wy = _bspline_w(s)
    z = 0.0
    for k in range(4):
        r = 0.0
        for m in range(4):
            r += c[ib + k, jb + m] * wy[m]
        z += wx[k] * r
    return z


@njit(cache=True)
def _grid_z_many(p, c, xs, ys, out):
    """Heights of the grid surface at many points (1-D arrays)."""
    for i in range(xs.shape[0]):
        out[i] = _grid_z(p, c, xs[i], ys[i])


@njit(cache=True)
def _grid_grad_many(p, c, xs, ys, out_x, out_y):
    """Gradients of the grid surface at many points (1-D arrays)."""
    for i in range(xs.shape[0]):
        gx, gy = _grid_grad(p, c, xs[i], ys[i])
        out_x[i] = gx
        out_y[i] = gy


@njit(cache=True, inline="always")
def _surf_grad(kind, p, c, x, y):
    """Surface gradient (dz/dx, dz/dy) for either kernel surface kind."""
    if kind == _KIND_QUAD:
        # p = [z0, a, b, c, d, e]
        return p[1] + p[3] * x + p[4] * y, p[2] + p[4] * x + p[5] * y
    return _grid_grad(p, c, x, y)


@njit(cache=True, inline="always")
def _surf_z(kind, p, c, x, y):
    """Surface height z for either kernel surface kind."""
    if kind == _KIND_QUAD:
        return (
            p[0]
            + p[1] * x
            + p[2] * y
            + 0.5 * (p[3] * x * x + 2.0 * p[4] * x * y + p[5] * y * y)
        )
    return _grid_z(p, c, x, y)


# --------------------------------------------------------------------------
# Roll kernel
# --------------------------------------------------------------------------


@njit(cache=True)
def _hermite(x0, y0, vx0, vy0, x1, y1, vx1, vy1, h, w):
    """Cubic Hermite segment of one integration step, evaluated at fraction ``w``.

    The step goes from state 0 to state 1 in time ``h``.  Returns
    ``(px, py, dpx, dpy, ddpx, ddpy)``: position [m] and its first and second
    derivatives with respect to ``w`` (velocity = ``dp / h``).
    """
    w2 = w * w
    w3 = w2 * w
    b00 = 2.0 * w3 - 3.0 * w2 + 1.0
    b10 = w3 - 2.0 * w2 + w
    b01 = -2.0 * w3 + 3.0 * w2
    b11 = w3 - w2
    d00 = 6.0 * w2 - 6.0 * w
    d10 = 3.0 * w2 - 4.0 * w + 1.0
    d11 = 3.0 * w2 - 2.0 * w
    e00 = 12.0 * w - 6.0
    e10 = 6.0 * w - 4.0
    e11 = 6.0 * w - 2.0
    px = b00 * x0 + b10 * h * vx0 + b01 * x1 + b11 * h * vx1
    py = b00 * y0 + b10 * h * vy0 + b01 * y1 + b11 * h * vy1
    dpx = d00 * (x0 - x1) + d10 * h * vx0 + d11 * h * vx1
    dpy = d00 * (y0 - y1) + d10 * h * vy0 + d11 * h * vy1
    ddpx = e00 * (x0 - x1) + e10 * h * vx0 + e11 * h * vx1
    ddpy = e00 * (y0 - y1) + e10 * h * vy0 + e11 * h * vy1
    return px, py, dpx, dpy, ddpx, ddpy


@njit(cache=True)
def _hermite_closest(x0, y0, vx0, vy0, x1, y1, vx1, vy1, h, hx, hy):
    """Closest point to the hole on one integration step, to high order.

    The caller guarantees that the ball approaches the hole at the start of
    the step and no longer at its end (``(H - P) . v`` changes sign from > 0
    to <= 0), so the distance has a minimum inside the step.  It is found by
    safeguarded Newton iteration on ``f(w) = (P(w) - H) . P'(w) = 0`` along
    the Hermite segment (see :func:`_hermite`), ``w`` in [0, 1].

    Returns ``(w, dd2, speed, cross)``: step fraction, squared distance
    [m^2], ball speed [m/s] and ``v x (H - P)`` there (> 0: hole on the left
    of the direction of travel).
    """
    q0 = (hx - x0) * vx0 + (hy - y0) * vy0
    q1 = (hx - x1) * vx1 + (hy - y1) * vy1
    lo = 0.0
    hi = 1.0
    w = 0.5
    if q0 - q1 > 0.0:
        w = q0 / (q0 - q1)
    for _ in range(30):
        px, py, dpx, dpy, ddpx, ddpy = _hermite(x0, y0, vx0, vy0, x1, y1, vx1, vy1, h, w)
        f = (px - hx) * dpx + (py - hy) * dpy
        if f < 0.0:
            lo = w
        else:
            hi = w
        df = dpx * dpx + dpy * dpy + (px - hx) * ddpx + (py - hy) * ddpy
        wn = 0.5 * (lo + hi)
        if df > 0.0:
            wn = w - f / df
            if not (wn > lo and wn < hi):
                wn = 0.5 * (lo + hi)
        done = abs(wn - w) <= 1e-13 or hi - lo <= 1e-13
        w = wn
        if done:
            break
    px, py, dpx, dpy, ddpx, ddpy = _hermite(x0, y0, vx0, vy0, x1, y1, vx1, vy1, h, w)
    dd2 = (px - hx) * (px - hx) + (py - hy) * (py - hy)
    speed = math.sqrt(dpx * dpx + dpy * dpy) / h
    cross = (dpx * (hy - py) - dpy * (hx - px)) / h
    return w, dd2, speed, cross


@njit(cache=True)
def _hermite_line_crossing(x0, y0, vx0, vy0, x1, y1, vx1, vy1, h, sx, sy, ux, uy, dist):
    """Where one integration step crosses the hole line, to high order.

    The hole line is ``X = dist`` with ``X = (P - S) . u`` the progress from
    the start ``S`` along the unit vector ``u``.  The caller guarantees
    ``X0 < dist <= X1``.  Newton iteration on the Hermite segment.

    Returns ``(w, y_line, speed)``: step fraction, lateral offset to the
    left of the hole [m] and ball speed [m/s] at the crossing.
    """
    x0p = (x0 - sx) * ux + (y0 - sy) * uy
    x1p = (x1 - sx) * ux + (y1 - sy) * uy
    w = (dist - x0p) / (x1p - x0p)
    for _ in range(4):
        px, py, dpx, dpy, ddpx, ddpy = _hermite(x0, y0, vx0, vy0, x1, y1, vx1, vy1, h, w)
        f = (px - sx) * ux + (py - sy) * uy - dist
        df = dpx * ux + dpy * uy
        if df != 0.0:
            w -= f / df
        if w < 0.0:
            w = 0.0
        elif w > 1.0:
            w = 1.0
    px, py, dpx, dpy, ddpx, ddpy = _hermite(x0, y0, vx0, vy0, x1, y1, vx1, vy1, h, w)
    y_line = (py - sy) * ux - (px - sx) * uy
    speed = math.sqrt(dpx * dpx + dpy * dpy) / h
    return w, y_line, speed


@njit(cache=True, inline="always")
def _accel(kind, p, c, x, y, vx, vy, a_r, agx, agy):
    """Ball acceleration (ax, ay) [m/s^2] at state (x, y, vx, vy).

    Moving ball: drive (slope + grain) minus rolling resistance ``a_r``
    opposing the velocity.  Ball at rest: resistance opposes the drive and
    cancels it completely if the drive does not exceed ``a_r``.
    """
    gx, gy = _surf_grad(kind, p, c, x, y)
    adx = agx - _KF * gx
    ady = agy - _KF * gy
    s = math.sqrt(vx * vx + vy * vy)
    if s > _S_TINY:
        f = a_r / s
        return adx - f * vx, ady - f * vy
    ad = math.sqrt(adx * adx + ady * ady)
    if ad > a_r:
        f = 1.0 - a_r / ad
        return adx * f, ady * f
    return 0.0, 0.0


@njit(cache=True)
def _roll(
    kind,
    p,
    c,
    x,
    y,
    vx,
    vy,
    a_r,
    agx,
    agy,
    hx,
    hy,
    dt,
    t_max,
    r_max,
    stop_at_line,
    stop_on_capture,
    v_cap0,
    cap_exp,
    hole_r,
    record,
    traj,
    out,
):
    """Integrate one roll from (x, y) with velocity (vx, vy); fill ``out``.

    Parameters (all SI)
    -------------------
    kind, p, c : kernel surface specification (see ``Surface.kernel_spec``).
    a_r        : rolling deceleration [m/s^2].
    agx, agy   : grain acceleration vector ``kappa * a_r * g_hat`` [m/s^2].
    hx, hy     : hole centre [m].
    dt, t_max  : RK4 step and time limit [s].
    r_max      : distance from the start beyond which the roll is abandoned [m].
    stop_at_line    : 1 = stop at the first crossing of the hole line (solver).
    stop_on_capture : 1 = stop once the ball is captured and has crossed the
                      hole line (so the lateral miss there is still reported).
    v_cap0, cap_exp, hole_r : capture model; ``v_cap0 <= 0`` disables capture.
    record, traj    : 1 = store (t, x, y, vx, vy) rows in ``traj``.
    out             : float array of length ``_NOUT`` (see ``_O_*`` indices).

    The "hole line" is the line through the hole centre perpendicular to the
    start->hole direction.  With X the progress along start->hole and Y the
    offset to the left, the first crossing of X = D gives the signed lateral
    miss Y and the arrival speed, located on the cubic Hermite segment of
    the step (as is every closest approach to the hole).
    """
    sx = x
    sy = y
    dist = math.sqrt((hx - sx) * (hx - sx) + (hy - sy) * (hy - sy))
    if dist > 0.0:
        ux = (hx - sx) / dist
        uy = (hy - sy) / dist
    else:
        ux = 1.0
        uy = 0.0

    bounded = kind == _KIND_GRID
    bx0 = 0.0
    bx1 = 0.0
    by0 = 0.0
    by1 = 0.0
    if bounded:
        bx0 = p[0]
        by0 = p[1]
        bx1 = p[0] + (p[4] - 1.0) / p[2]
        by1 = p[1] + (p[5] - 1.0) / p[3]
    r_max2 = r_max * r_max
    hole_r2 = hole_r * hole_r
    # Step budget: the stiffness limit shortens the steps of a slow ball, so a
    # ball creeping for seconds on a slope within a fraction of a percent of
    # critical could take an unbounded number of them before t_max.
    n_budget = _STEP_BUDGET_FACTOR * (int(t_max / dt) + 1)

    t = 0.0
    n_rec = 0
    n_cap = traj.shape[0]
    n_step = 0
    s = math.sqrt(vx * vx + vy * vy)

    dmin2 = dist * dist  # squared closest approach so far
    smin = s
    tmin = 0.0
    side = 0.0
    crossed = 0.0
    yline = np.nan
    sline = np.nan
    tline = np.nan
    xprog = 0.0
    yprog = 0.0
    sprog = s
    captured = 0.0
    tcap = np.nan
    path = 0.0
    status = -1.0
    capture_on = v_cap0 > 0.0

    while True:
        if record != 0 and n_rec < n_cap:
            traj[n_rec, 0] = t
            traj[n_rec, 1] = x
            traj[n_rec, 2] = y
            traj[n_rec, 3] = vx
            traj[n_rec, 4] = vy
            n_rec += 1
        if t >= t_max or n_step >= n_budget:
            status = _ROLL_MAX_TIME
            break

        gx, gy = _surf_grad(kind, p, c, x, y)
        adx = agx - _KF * gx  # drive: slope + grain
        ady = agy - _KF * gy

        # ---- step-size control and terminal closure near the stop -------
        h = dt
        if s > _S_TINY:
            dec = a_r - (adx * vx + ady * vy) / s  # along-track deceleration
            if dec > 0.0:
                ts = s / dec  # time to stop if the acceleration stayed frozen
                if s < _V_EPS and ts < dt:
                    # Analytic closure of the last <= 1e-8 m (straight line,
                    # constant deceleration).
                    dl = 0.5 * s * ts
                    x += vx / s * dl
                    y += vy / s * dl
                    t += ts
                    path += dl
                    vx = 0.0
                    vy = 0.0
                    s = 0.0
                    dd2 = (hx - x) * (hx - x) + (hy - y) * (hy - y)
                    if dd2 < dmin2:
                        dmin2 = dd2
                        smin = 0.0
                        tmin = t
                    xp = (x - sx) * ux + (y - sy) * uy
                    if xp > xprog:
                        xprog = xp
                        yprog = (y - sy) * ux - (x - sx) * uy
                        sprog = 0.0
                    if record != 0 and n_rec < n_cap:
                        traj[n_rec, 0] = t
                        traj[n_rec, 1] = x
                        traj[n_rec, 2] = y
                        traj[n_rec, 3] = 0.0
                        traj[n_rec, 4] = 0.0
                        n_rec += 1
                elif ts < 2.0 * h:
                    h = 0.5 * ts
            # A slow ball's velocity component across the drive decays at the
            # rate a_r / s (Jacobian of the friction term -a_r * v_hat), which
            # grows without bound as the ball stops.  Explicit RK4 is only
            # stable for h * a_r / s < 2.785, so the step is also limited by
            # this rate.  Without it a ball stopping WITH the slope (drive
            # along the motion above ~0.85 a_r, where 0.5 * ts alone is too
            # long) zig-zags about the fall line and creeps instead of resting.
            if h * a_r > _H_STIFF * s:
                h = _H_STIFF * s / a_r

        # ---- first RK4 stage (also decides whether a resting ball holds) --
        if s > _S_TINY:
            f = a_r / s
            a1x = adx - f * vx
            a1y = ady - f * vy
        else:
            vx = 0.0
            vy = 0.0
            s = 0.0
            ad = math.sqrt(adx * adx + ady * ady)
            if ad <= a_r:
                status = _ROLL_STOPPED  # rolling resistance holds the ball
                break
            # too steep to rest here: the ball rolls on from rest
            f = 1.0 - a_r / ad
            a1x = adx * f
            a1y = ady * f

        if t + h > t_max:
            h = t_max - t

        # ---- remaining RK4 stages ------------------------------------------
        hh = 0.5 * h
        vx2 = vx + hh * a1x
        vy2 = vy + hh * a1y
        a2x, a2y = _accel(kind, p, c, x + hh * vx, y + hh * vy, vx2, vy2, a_r, agx, agy)
        vx3 = vx + hh * a2x
        vy3 = vy + hh * a2y
        a3x, a3y = _accel(kind, p, c, x + hh * vx2, y + hh * vy2, vx3, vy3, a_r, agx, agy)
        vx4 = vx + h * a3x
        vy4 = vy + h * a3y
        a4x, a4y = _accel(kind, p, c, x + h * vx3, y + h * vy3, vx4, vy4, a_r, agx, agy)
        h6 = h / 6.0
        xn = x + h6 * (vx + 2.0 * vx2 + 2.0 * vx3 + vx4)
        yn = y + h6 * (vy + 2.0 * vy2 + 2.0 * vy3 + vy4)
        vxn = vx + h6 * (a1x + 2.0 * a2x + 2.0 * a3x + a4x)
        vyn = vy + h6 * (a1y + 2.0 * a2y + 2.0 * a3y + a4y)
        sn = math.sqrt(vxn * vxn + vyn * vyn)
        n_step += 1

        # ---- events on the step (x, y) -> (xn, yn) ------------------------
        ex = xn - x
        ey = yn - y
        path += math.sqrt(ex * ex + ey * ey)

        # closest approach to the hole centre: end point of the step ...
        ox = hx - xn
        oy = hy - yn
        dd2 = ox * ox + oy * oy
        if dd2 < dmin2:
            dmin2 = dd2
            smin = sn
            tmin = t + h
            cr = vxn * oy - vyn * ox
            if cr > 0.0:
                side = -1.0  # hole to the left of travel: ball passes right
            elif cr < 0.0:
                side = 1.0
            else:
                side = 0.0

        # ... and a local minimum of the distance inside the step (a "pass"),
        # which is also where the capture rule is applied
        q0 = (hx - x) * vx + (hy - y) * vy
        q1 = ox * vxn + oy * vyn
        if q0 > 0.0 and q1 <= 0.0:
            w, dd2, sp, cr = _hermite_closest(x, y, vx, vy, xn, yn, vxn, vyn, h, hx, hy)
            if dd2 < dmin2:
                dmin2 = dd2
                smin = sp
                tmin = t + w * h
                if cr > 0.0:
                    side = -1.0
                elif cr < 0.0:
                    side = 1.0
                else:
                    side = 0.0
            if capture_on and captured == 0.0 and dd2 < hole_r2:
                if sp < v_cap0 * (1.0 - dd2 / hole_r2) ** cap_exp:
                    captured = 1.0
                    tcap = t + w * h

        # first crossing of the hole line X = dist
        just_crossed = False
        if crossed == 0.0:
            if (xn - sx) * ux + (yn - sy) * uy >= dist and (x - sx) * ux + (y - sy) * uy < dist:
                w, yline, sline = _hermite_line_crossing(
                    x, y, vx, vy, xn, yn, vxn, vyn, h, sx, sy, ux, uy, dist
                )
                tline = t + w * h
                crossed = 1.0
                just_crossed = True

        # ---- advance ------------------------------------------------------
        x = xn
        y = yn
        vx = vxn
        vy = vyn
        s = sn
        t += h

        xp = (x - sx) * ux + (y - sy) * uy
        if xp > xprog:
            xprog = xp
            yprog = (y - sy) * ux - (x - sx) * uy
            sprog = sn

        if captured != 0.0 and stop_on_capture != 0 and crossed != 0.0:
            # holed, and the lateral miss at the hole line is known
            status = _ROLL_CAPTURED
            break
        if just_crossed and stop_at_line != 0:
            status = _ROLL_AT_LINE
            break
        if (x - sx) * (x - sx) + (y - sy) * (y - sy) > r_max2 or (
            bounded and (x < bx0 or x > bx1 or y < by0 or y > by1)
        ):
            status = _ROLL_OUT_OF_BOUNDS
            break

    if status != _ROLL_STOPPED and status != _ROLL_MAX_TIME:
        # loop left through a break after the state advanced: record the end
        if record != 0 and n_rec < n_cap:
            traj[n_rec, 0] = t
            traj[n_rec, 1] = x
            traj[n_rec, 2] = y
            traj[n_rec, 3] = vx
            traj[n_rec, 4] = vy
            n_rec += 1

    if status == _ROLL_STOPPED and capture_on and captured == 0.0:
        # at rest with the centre over the hole: the ball has dropped
        if (hx - x) * (hx - x) + (hy - y) * (hy - y) < hole_r2:
            captured = 1.0
            tcap = t

    out[_O_STATUS] = status
    out[_O_T] = t
    out[_O_X] = x
    out[_O_Y] = y
    out[_O_VX] = vx
    out[_O_VY] = vy
    out[_O_DMIN] = math.sqrt(dmin2)
    out[_O_SMIN] = smin
    out[_O_TMIN] = tmin
    out[_O_SIDE] = side
    out[_O_CROSSED] = crossed
    out[_O_YLINE] = yline
    out[_O_SLINE] = sline
    out[_O_TLINE] = tline
    out[_O_XPROG] = xprog
    out[_O_YPROG] = yprog
    out[_O_CAPT] = captured
    out[_O_TCAPT] = tcap
    out[_O_PATH] = path
    out[_O_NREC] = n_rec
    out[_O_NSTEP] = n_step
    out[_O_SPROG] = sprog


@njit(cache=True)
def _roll_many_serial(
    kind, p, c, sx, sy, vx, vy, a_r, agx, agy, hx, hy, dt, t_max, r_max,
    stop_on_capture, v_cap0, cap_exp, hole_r, outs,
):
    """Roll N independent putts on one surface, one after the other."""
    traj = np.empty((1, 5))
    out = np.empty(_NOUT)
    for i in range(sx.shape[0]):
        _roll(
            kind, p, c, sx[i], sy[i], vx[i], vy[i], a_r[i], agx[i], agy[i], hx[i], hy[i],
            dt, t_max, r_max, 0, stop_on_capture, v_cap0, cap_exp, hole_r, 0, traj, out,
        )
        for k in range(_NOUT):
            outs[i, k] = out[k]


@njit(cache=True, parallel=True)
def _roll_many(
    kind, p, c, sx, sy, vx, vy, a_r, agx, agy, hx, hy, dt, t_max, r_max,
    stop_on_capture, v_cap0, cap_exp, hole_r, outs,
):
    """Roll N independent putts on one surface (parallel over putts)."""
    n = sx.shape[0]
    for i in prange(n):
        traj = np.empty((1, 5))
        out = np.empty(_NOUT)
        _roll(
            kind, p, c, sx[i], sy[i], vx[i], vy[i], a_r[i], agx[i], agy[i], hx[i], hy[i],
            dt, t_max, r_max, 0, stop_on_capture, v_cap0, cap_exp, hole_r, 0, traj, out,
        )
        for k in range(_NOUT):
            outs[i, k] = out[k]


# --------------------------------------------------------------------------
# Aim solver kernels
# --------------------------------------------------------------------------


@njit(cache=True)
def _trial(kind, p, c, sx, sy, hx, hy, ux, uy, dist, phi, e0, a_r, agx, agy, vh2, dt, t_max, r_max, traj, out):
    """One trial roll for the solver.

    Launch at angle ``phi`` from the hole line with kinetic "energy"
    ``e0 = v0**2``.  Returns ``(g, y)``:

    * ``g`` [m^2/s^2] pace residual: ``v_cross**2 - v_h**2`` if the ball
      crosses the hole line, else ``-v_h**2 - 2 a_r * shortfall - v_turn**2``
      where ``shortfall`` is the distance by which the furthest progress
      toward the hole line fell short and ``v_turn`` the speed the ball
      still had there (0 if it stopped there; > 0 if it turned back before
      the line).  For a ball that stops short this is the flat continuation
      of ``v**2`` to the hole line, so ``g`` is continuous and increasing in
      ``e0`` and zero exactly at the target pace.  A ball that turns back
      short of the line can never satisfy ``g = 0`` (no false root).
    * ``y`` [m] lateral miss at the hole line (positive = left of the hole),
      or the lateral offset at the point of furthest progress if short.

    A crossing of the hole line further than ``1 m + 0.5 * dist`` to the side
    of the hole is treated as not reaching it (``g = -v_h**2 - 2 a_r |y|``,
    always negative).  On a patch whose cross slope grows along the putt the
    lowest-energy way to cross the infinite line is to swing far away from
    the hole; without this rule the pace solve settles on that branch and
    the aim search then sees a 10 m jump of the miss where the regular
    solution is.
    """
    v0 = math.sqrt(e0)
    cph = math.cos(phi)
    sph = math.sin(phi)
    dx = ux * cph - uy * sph
    dy = uy * cph + ux * sph
    _roll(
        kind, p, c, sx, sy, v0 * dx, v0 * dy, a_r, agx, agy, hx, hy,
        dt, t_max, r_max, 1, 0, 0.0, 0.5, HOLE_R, 0, traj, out,
    )
    if out[_O_CROSSED] > 0.5:
        yl = out[_O_YLINE]
        if abs(yl) > _LINE_MISS_OFFSET + _LINE_MISS_SLOPE * dist:
            # The hole line is infinite.  A ball that swings away and crosses
            # it metres to the side has not reached the hole: count it as too
            # little pace, so the pace solve moves on to the faster branch
            # that crosses near the hole instead of settling on this one.
            return -vh2 - 2.0 * a_r * abs(yl), yl
        return out[_O_SLINE] * out[_O_SLINE] - vh2, yl
    return -vh2 - 2.0 * a_r * (dist - out[_O_XPROG]) - out[_O_SPROG] * out[_O_SPROG], out[_O_YPROG]


@njit(cache=True)
def _solve_pace(
    kind, p, c, sx, sy, hx, hy, ux, uy, dist, phi, e_guess, a_r, agx, agy, vh2,
    dt, t_max, r_max, tol_g, e_min, e_max, traj, out,
):
    """Inner solve: launch energy ``e = v0**2`` giving the target pace at fixed ``phi``.

    Phase A walks (unit-slope Newton step, then secant, with growth limits)
    until the root is bracketed; phase B is Illinois regula falsi inside the
    bracket.  Returns ``(e, g, y, flag, n_rolls)`` where ``flag`` is one of
    ``_PACE_OK`` (|g| <= tol_g), ``_PACE_LIMITED`` (no slower putt reaches
    the hole: the returned one arrives above the target pace) or
    ``_PACE_UNREACHABLE`` (the ball cannot be made to reach the hole line).
    """
    n = 0
    e = e_guess
    if e < e_min:
        e = e_min
    if e > e_max:
        e = e_max
    g, y = _trial(kind, p, c, sx, sy, hx, hy, ux, uy, dist, phi, e, a_r, agx, agy, vh2, dt, t_max, r_max, traj, out)
    n += 1
    if abs(g) <= tol_g:
        return e, g, y, _PACE_OK, n

    have_lo = False
    have_hi = False
    e_lo = 0.0
    g_lo = 0.0
    y_lo = 0.0
    e_hi = 0.0
    g_hi = 0.0
    y_hi = 0.0
    if g < 0.0:
        have_lo = True
        e_lo = e
        g_lo = g
        y_lo = y
    else:
        have_hi = True
        e_hi = e
        g_hi = g
        y_hi = y

    # ---- phase A: find a bracket ------------------------------------------
    e_prev = e
    g_prev = g
    e_new = e - g  # d(g)/d(e) = 1 exactly on a plane
    it = 0
    while not (have_lo and have_hi):
        it += 1
        if it > 40:
            if have_hi:
                return e_hi, g_hi, y_hi, _PACE_LIMITED, n
            return e_lo, g_lo, y_lo, _PACE_UNREACHABLE, n
        if have_lo:
            if e_lo >= e_max:
                return e_lo, g_lo, y_lo, _PACE_UNREACHABLE, n
            if not (e_new > e_lo):
                e_new = 2.0 * e_lo + 1e-4
            if e_new > 4.0 * e_lo + 0.01:
                e_new = 4.0 * e_lo + 0.01
            if e_new > e_max:
                e_new = e_max
        else:
            if e_hi <= e_min:
                return e_hi, g_hi, y_hi, _PACE_LIMITED, n
            if not (e_new < e_hi):
                e_new = 0.5 * e_hi
            if e_new < 0.25 * e_hi:
                e_new = 0.25 * e_hi
            if e_new < e_min:
                e_new = e_min
        g, y = _trial(kind, p, c, sx, sy, hx, hy, ux, uy, dist, phi, e_new, a_r, agx, agy, vh2, dt, t_max, r_max, traj, out)
        n += 1
        if abs(g) <= tol_g:
            return e_new, g, y, _PACE_OK, n
        if g < 0.0:
            have_lo = True
            e_lo = e_new
            g_lo = g
            y_lo = y
        else:
            have_hi = True
            e_hi = e_new
            g_hi = g
            y_hi = y
        den = g - g_prev
        if den != 0.0:
            e_next = e_new - g * (e_new - e_prev) / den
        else:
            e_next = e_new - g
        e_prev = e_new
        g_prev = g
        e_new = e_next

    # ---- phase B: Illinois regula falsi inside [e_lo, e_hi] ---------------
    # (a bisection step follows any step that failed to halve the bracket, so
    # the bracket also collapses quickly onto a jump of g)
    w_lo = g_lo  # Illinois-weighted residuals
    w_hi = g_hi
    last = 0
    bisect = False
    # A continuous g with |dg/de| of order one (it is exactly 1 on a plane)
    # is within tol_g of zero long before the bracket is this narrow:
    w_jump = tol_g / 16.0
    if w_jump < 4e-15 * (1.0 + e_hi):
        w_jump = 4e-15 * (1.0 + e_hi)  # floating-point resolution of e
    for it in range(80):
        width = e_hi - e_lo
        if width <= w_jump:
            break  # bracket collapsed onto a jump of g: no (robust) exact pace
        if bisect:
            e = 0.5 * (e_lo + e_hi)
        else:
            e = (e_lo * w_hi - e_hi * w_lo) / (w_hi - w_lo)
            if not (e > e_lo and e < e_hi):
                e = 0.5 * (e_lo + e_hi)
        g, y = _trial(kind, p, c, sx, sy, hx, hy, ux, uy, dist, phi, e, a_r, agx, agy, vh2, dt, t_max, r_max, traj, out)
        n += 1
        if abs(g) <= tol_g:
            return e, g, y, _PACE_OK, n
        if g < 0.0:
            e_lo = e
            g_lo = g
            y_lo = y
            w_lo = g
            if last == -1:
                w_hi *= 0.5
            last = -1
        else:
            e_hi = e
            g_hi = g
            y_hi = y
            w_hi = g
            if last == 1:
                w_lo *= 0.5
            last = 1
        bisect = (e_hi - e_lo) > 0.5 * width
    # g jumps across zero (e.g. the ball either stops above a steep drop or
    # runs away down it): return the slowest putt that still gets there.
    return e_hi, g_hi, y_hi, _PACE_LIMITED, n


@njit(cache=True)
def _solve_kernel(
    kind, p, c, sx, sy, hx, hy, a_r, agx, agy, v_h, dt, t_max, r_max,
    tol_y, tol_dist, phi_max, v_max, max_rolls, res,
):
    """Solve (phi, v0) so the ball passes through the hole centre at speed ``v_h``.

    Nested bracketing root finds: the outer unknown is the aim angle ``phi``
    (residual: lateral miss at the hole line), the inner unknown is the
    launch energy ``v0**2`` (residual: pace, see :func:`_solve_pace`).

    Fills ``res`` (``_R_*`` indices) with the best iterate found - also on
    failure - and returns a ``_SOLVE_*`` status code.  The search gives up
    with ``_SOLVE_NO_CONVERGENCE`` once ``max_rolls`` trial rolls are spent.
    """
    for k in range(_NRES):
        res[k] = np.nan
    res[_R_NROLLS] = 0.0
    dist = math.sqrt((hx - sx) * (hx - sx) + (hy - sy) * (hy - sy))
    if not (dist > 1e-6) or not (a_r > 0.0) or not (v_h >= 0.0) or not (dt > 0.0):
        return _SOLVE_INVALID
    ux = (hx - sx) / dist
    uy = (hy - sy) / dist
    vh2 = v_h * v_h
    traj = np.empty((1, 5))
    out = np.empty(_NOUT)
    tol_g = 2.0 * a_r * tol_dist
    e_min = 1e-6
    e_max = v_max * v_max
    # A trial ball further than this from the start has run away for good.
    r_trial = 2.0 * dist + 3.0
    if r_trial > r_max:
        r_trial = r_max

    # Energy balance gives the launch energy almost exactly (path ~ straight):
    #   v0^2 = v_h^2 + 2 a_r D + 2 (5/7) G (z_hole - z_ball) - 2 a_grain . (hole - ball)
    zs = _surf_z(kind, p, c, sx, sy)
    zh = _surf_z(kind, p, c, hx, hy)
    e0 = vh2 + 2.0 * a_r * dist + 2.0 * _KF * (zh - zs) - 2.0 * (agx * (hx - sx) + agy * (hy - sy))
    if e0 < 1e-4:
        e0 = 1e-4
    if e0 > e_max:
        e0 = e_max

    # Planar small-slope theory gives the first aim guess (see
    # planar_break_angle_paced): phi = -a_n / (2 a_r) * F(rho).
    gmx, gmy = _surf_grad(kind, p, c, 0.5 * (sx + hx), 0.5 * (sy + hy))
    ghx, ghy = _surf_grad(kind, p, c, hx, hy)
    a_n = (-agx * uy + agy * ux) - _KF * (-0.5 * (gmx + ghx) * uy + 0.5 * (gmy + ghy) * ux)
    rho2 = vh2 / e0
    if rho2 < 1e-12:
        fpace = 1.0
    elif rho2 < 0.98:
        fpace = 1.0 + rho2 * math.log(rho2) / (1.0 - rho2)
    else:
        fpace = 0.01
    phi = -a_n / (2.0 * a_r) * fpace
    if phi > 0.5 * phi_max:
        phi = 0.5 * phi_max
    if phi < -0.5 * phi_max:
        phi = -0.5 * phi_max

    n_tot = 0
    e, g, y, pf, n = _solve_pace(
        kind, p, c, sx, sy, hx, hy, ux, uy, dist, phi, e0, a_r, agx, agy, vh2,
        dt, t_max, r_trial, tol_g, e_min, e_max, traj, out,
    )
    n_tot += n
    # best iterate so far (smallest |y| among iterates that reach the hole)
    b_phi = phi
    b_e = e
    b_y = y
    b_g = g
    b_pf = pf
    have_best = pf != _PACE_UNREACHABLE
    status = -1
    if pf == _PACE_UNREACHABLE:
        status = _SOLVE_UNREACHABLE
        b_e = e0  # nothing reached the hole: fall back to the energy-balance estimate
    elif abs(y) <= tol_y:
        status = _SOLVE_OK

    have_lo = False
    have_hi = False
    p_lo = 0.0
    y_lo = 0.0
    e_lo = 0.0
    p_hi = 0.0
    y_hi = 0.0
    e_hi = 0.0
    if status < 0:
        if y < 0.0:  # ball passes right of the hole: aim further left
            have_lo = True
            p_lo = phi
            y_lo = y
            e_lo = e
        else:
            have_hi = True
            p_hi = phi
            y_hi = y
            e_hi = e

    # ---- phase A: bracket the aim angle ------------------------------------
    p_cur = phi
    p_prev = phi
    y_prev = y
    p_new = phi - y / dist  # d(y)/d(phi) ~ D
    it = 0
    while status < 0 and not (have_lo and have_hi):
        it += 1
        if it > 30:
            status = _SOLVE_NO_BRACKET
            break
        if n_tot >= max_rolls:
            status = _SOLVE_NO_CONVERGENCE
            break
        step = p_new - p_cur
        if step > 0.3:
            step = 0.3
        if step < -0.3:
            step = -0.3
        if have_lo and not (step > 0.0):
            step = 0.05
        if have_hi and not (step < 0.0):
            step = -0.05
        p_new = p_cur + step
        if p_new > phi_max:
            if p_cur >= phi_max:
                status = _SOLVE_NO_BRACKET
                break
            p_new = phi_max
        if p_new < -phi_max:
            if p_cur <= -phi_max:
                status = _SOLVE_NO_BRACKET
                break
            p_new = -phi_max
        e, g, y, pf, n = _solve_pace(
            kind, p, c, sx, sy, hx, hy, ux, uy, dist, p_new, e, a_r, agx, agy, vh2,
            dt, t_max, r_trial, tol_g, e_min, e_max, traj, out,
        )
        n_tot += n
        if pf == _PACE_UNREACHABLE:
            status = _SOLVE_UNREACHABLE
            break
        if (not have_best) or abs(y) < abs(b_y):
            b_phi = p_new
            b_e = e
            b_y = y
            b_g = g
            b_pf = pf
            have_best = True
        if abs(y) <= tol_y:
            status = _SOLVE_OK
            break
        if y < 0.0:
            have_lo = True
            p_lo = p_new
            y_lo = y
            e_lo = e
        else:
            have_hi = True
            p_hi = p_new
            y_hi = y
            e_hi = e
        den = y - y_prev
        if den != 0.0:
            p_next = p_new - y * (p_new - p_prev) / den
        else:
            p_next = p_new - y / dist
        p_prev = p_new
        y_prev = y
        p_cur = p_new
        p_new = p_next

    # ---- phase B: Illinois regula falsi on the aim angle -------------------
    # (with a bisection step after any step that failed to halve the bracket)
    if status < 0:
        w_lo = y_lo
        w_hi = y_hi
        last = 0
        bisect = False
        status = _SOLVE_NO_CONVERGENCE
        # The lateral miss normally changes by about D metres per radian of
        # aim.  The bracket is declared collapsed onto a jump of the miss
        # when it is 1e4 times narrower than the tolerance needs at 1 m/rad,
        # or when the miss still changes by 1000 tolerances across a bracket
        # narrower than tol_y radians (defaults: 1e-9 rad; 1 cm across
        # 0.01 mrad).  Then there is no continuous solution.
        w_jump = 1e-4 * tol_y
        if w_jump < 1e-15:
            w_jump = 1e-15
        for it in range(80):
            width = p_hi - p_lo
            if width <= w_jump or (width <= tol_y and y_hi - y_lo > 1e3 * tol_y):
                break
            if n_tot >= max_rolls:
                break
            if bisect:
                phi = 0.5 * (p_lo + p_hi)
            else:
                phi = (p_lo * w_hi - p_hi * w_lo) / (w_hi - w_lo)
                if not (phi > p_lo and phi < p_hi):
                    phi = 0.5 * (p_lo + p_hi)
            e_start = e_lo + (e_hi - e_lo) * (phi - p_lo) / width
            e, g, y, pf, n = _solve_pace(
                kind, p, c, sx, sy, hx, hy, ux, uy, dist, phi, e_start, a_r, agx, agy, vh2,
                dt, t_max, r_trial, tol_g, e_min, e_max, traj, out,
            )
            n_tot += n
            if pf == _PACE_UNREACHABLE:
                status = _SOLVE_UNREACHABLE
                break
            if abs(y) < abs(b_y):
                b_phi = phi
                b_e = e
                b_y = y
                b_g = g
                b_pf = pf
            if abs(y) <= tol_y:
                status = _SOLVE_OK
                break
            if y < 0.0:
                p_lo = phi
                y_lo = y
                e_lo = e
                w_lo = y
                if last == -1:
                    w_hi *= 0.5
                last = -1
            else:
                p_hi = phi
                y_hi = y
                e_hi = e
                w_hi = y
                if last == 1:
                    w_lo *= 0.5
                last = 1
            bisect = (p_hi - p_lo) > 0.5 * width

    if status == _SOLVE_OK and b_pf != _PACE_OK:
        status = _SOLVE_PACE_LIMITED

    res[_R_PHI] = b_phi
    res[_R_V0] = math.sqrt(b_e)
    res[_R_NROLLS] = n_tot
    if have_best:
        res[_R_MISS] = b_y
        v2 = b_g + vh2
        if v2 > 0.0:
            res[_R_VHOLE] = math.sqrt(v2)
        else:
            res[_R_VHOLE] = 0.0
    return status


@njit(cache=True, parallel=True)
def _solve_many(
    kind, p, c, sx, sy, hx, hy, a_r, agx, agy, v_h, dt, t_max, r_max,
    tol_y, tol_dist, phi_max, v_max, max_rolls, results, statuses,
):
    """Aim solves for N putts on ONE surface (parallel over putts)."""
    n = sx.shape[0]
    for i in prange(n):
        res = np.empty(_NRES)
        statuses[i] = _solve_kernel(
            kind, p, c, sx[i], sy[i], hx[i], hy[i], a_r[i], agx[i], agy[i], v_h[i],
            dt, t_max, r_max, tol_y, tol_dist, phi_max, v_max, max_rolls, res,
        )
        for k in range(_NRES):
            results[i, k] = res[k]


@njit(cache=True, parallel=True)
def _solve_many_quadratic(
    coeffs, dist, a_r, agx, agy, v_h, dt, t_max, r_max,
    tol_y, tol_dist, phi_max, v_max, max_rolls, results, statuses,
):
    """Aim solves for N putt-frame quadratic patches (parallel over patches).

    Patch i is ``z = a x + b y + 0.5 (c x^2 + 2 d x y + e y^2)`` with the
    ball at the origin and the hole at ``(dist[i], 0)``.
    """
    n = coeffs.shape[0]
    for i in prange(n):
        res = np.empty(_NRES)
        p = np.empty(6)
        p[0] = 0.0
        for k in range(5):
            p[k + 1] = coeffs[i, k]
        c = np.empty((1, 1))
        c[0, 0] = 0.0
        statuses[i] = _solve_kernel(
            _KIND_QUAD, p, c, 0.0, 0.0, dist[i], 0.0, a_r[i], agx[i], agy[i], v_h[i],
            dt, t_max, r_max, tol_y, tol_dist, phi_max, v_max, max_rolls, res,
        )
        for k in range(_NRES):
            results[i, k] = res[k]


# --------------------------------------------------------------------------
# Surfaces (public, numpy-vectorised)
# --------------------------------------------------------------------------

_NO_GRID = np.zeros((1, 1))


def _scalar_or_array(arr: np.ndarray):
    return float(arr) if arr.ndim == 0 else arr


class Surface:
    """Height field ``z(x, y)`` [m] with an analytic gradient.

    Subclasses implement :meth:`z`, :meth:`grad` (numpy-vectorised over
    broadcastable ``x``, ``y``) and :meth:`kernel_spec`.  Scalars in ->
    Python floats out.
    """

    def z(self, x, y):
        """Height z [m] at ``(x, y)`` [m]."""
        raise NotImplementedError

    def grad(self, x, y) -> Tuple:
        """Gradient ``(dz/dx, dz/dy)`` [m/m] at ``(x, y)`` [m]."""
        raise NotImplementedError

    def slope(self, x, y):
        """Slope magnitude ``|grad z|`` [m/m]."""
        gx, gy = self.grad(x, y)
        return _scalar_or_array(np.hypot(gx, gy))

    def fall_line_azimuth(self, x, y):
        """Azimuth of steepest descent [rad, CCW from +x]."""
        gx, gy = self.grad(x, y)
        return _scalar_or_array(np.arctan2(-np.asarray(gy), -np.asarray(gx)))

    @property
    def bounds(self) -> Tuple[float, float, float, float]:
        """Domain ``(xmin, xmax, ymin, ymax)`` [m]; infinite for analytic surfaces."""
        return (-math.inf, math.inf, -math.inf, math.inf)

    def kernel_spec(self) -> Tuple[int, np.ndarray, np.ndarray]:
        """``(kind, params, coeffs)`` consumed by the compiled kernels."""
        raise NotImplementedError


class QuadraticSurface(Surface):
    """``z = z0 + a x + b y + 0.5 (c x^2 + 2 d x y + e y^2)``.

    Parameters
    ----------
    a, b : float
        Slopes dz/dx, dz/dy at the origin [m/m].
    c, d, e : float
        Curvatures z_xx, z_xy, z_yy [1/m].
    z0 : float
        Height at the origin [m].
    """

    def __init__(self, a=0.0, b=0.0, c=0.0, d=0.0, e=0.0, z0=0.0):
        self.a = float(a)
        self.b = float(b)
        self.c = float(c)
        self.d = float(d)
        self.e = float(e)
        self.z0 = float(z0)
        self._p = np.array([self.z0, self.a, self.b, self.c, self.d, self.e], dtype=np.float64)

    @staticmethod
    def from_coeffs(coeffs, z0=0.0) -> "QuadraticSurface":
        """Build a :class:`QuadraticSurface` from the length-5 vector
        ``(a, b, c, d, e)``."""
        coeffs = np.asarray(coeffs, dtype=float)
        if coeffs.shape != (5,):
            raise ValueError("coeffs must be (a, b, c, d, e)")
        return QuadraticSurface(*coeffs, z0=z0)

    @property
    def coeffs(self) -> np.ndarray:
        """``(a, b, c, d, e)`` as a length-5 array."""
        return self._p[1:].copy()

    def in_frame(self, origin, angle: float) -> "QuadraticSurface":
        """The same surface expressed in a translated and rotated frame.

        The new frame has its origin at ``origin`` (x, y) [m] of this
        surface's frame and its +x axis rotated by ``angle`` [rad] CCW, so
        ``new.z(u, v) == self.z(origin + R(angle) @ (u, v))``.  With
        ``origin`` = ball and ``angle`` = bearing of the ball->hole line the
        result is the patch in the putt frame (ball at the origin, hole at
        ``(D, 0)``); its ``z0`` is the height at ``origin``.
        """
        ox, oy = _xy(origin, "origin")
        ca = math.cos(angle)
        sa = math.sin(angle)
        # gradient at the new origin, and the Hessian, rotated into the new axes
        gx = self.a + self.c * ox + self.d * oy
        gy = self.b + self.d * ox + self.e * oy
        return QuadraticSurface(
            a=gx * ca + gy * sa,
            b=-gx * sa + gy * ca,
            c=self.c * ca * ca + 2.0 * self.d * ca * sa + self.e * sa * sa,
            d=(self.e - self.c) * ca * sa + self.d * (ca * ca - sa * sa),
            e=self.c * sa * sa - 2.0 * self.d * ca * sa + self.e * ca * ca,
            z0=self.z(ox, oy),
        )

    def z(self, x, y):
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        out = (
            self.z0
            + self.a * x
            + self.b * y
            + 0.5 * (self.c * x * x + 2.0 * self.d * x * y + self.e * y * y)
        )
        return _scalar_or_array(out)

    def grad(self, x, y):
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        gx = self.a + self.c * x + self.d * y
        gy = self.b + self.d * x + self.e * y
        return _scalar_or_array(gx), _scalar_or_array(gy)

    def kernel_spec(self):
        return _KIND_QUAD, self._p, _NO_GRID

    def __repr__(self):
        return (
            f"{type(self).__name__}(a={self.a:.6g}, b={self.b:.6g}, c={self.c:.6g}, "
            f"d={self.d:.6g}, e={self.e:.6g}, z0={self.z0:.6g})"
        )


class PlaneSurface(QuadraticSurface):
    """``z = z0 + a x + b y`` (slopes ``a``, ``b`` in m/m)."""

    def __init__(self, a=0.0, b=0.0, z0=0.0):
        super().__init__(a, b, 0.0, 0.0, 0.0, z0)

    def __repr__(self):
        return f"PlaneSurface(a={self.a:.6g}, b={self.b:.6g}, z0={self.z0:.6g})"


class GridSurface(Surface):
    """Smooth (C2) interpolation of a height grid on a uniform mesh.

    Uniform bicubic B-spline that passes exactly through the samples.  The
    gradient is the exact derivative of the interpolant, so heights and
    slopes are mutually consistent and continuous across cells.

    Parameters
    ----------
    x, y : 1-D arrays, uniformly spaced, ascending [m]
        Node coordinates (at least 4 each).
    heights : 2-D array, shape ``(len(x), len(y))`` [m]
        ``heights[i, j] = z(x[i], y[j])`` (``indexing="ij"``).

    Notes
    -----
    * End conditions: before the spline coefficients are computed the
      samples are extended beyond the grid with the parabola through the
      three end samples, so planes and quadratics are reproduced right up to
      the edge of the grid (to ~1e-9 m).
    * Outside the grid the surface is extended as a constant along the
      clamped axis (zero gradient across it).  :func:`simulate_putt` reports
      ``OUT_OF_BOUNDS`` when the ball leaves the grid.
    """

    _PAD = 16

    def __init__(self, x, y, heights):
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        heights = np.asarray(heights, dtype=float)
        if x.ndim != 1 or y.ndim != 1 or x.size < 4 or y.size < 4:
            raise ValueError("x and y must be 1-D with at least 4 nodes each")
        if heights.shape != (x.size, y.size):
            raise ValueError("heights must have shape (len(x), len(y))")
        if not np.all(np.isfinite(heights)):
            raise ValueError("heights must be finite")
        dx = (x[-1] - x[0]) / (x.size - 1)
        dy = (y[-1] - y[0]) / (y.size - 1)
        if not (dx > 0.0 and dy > 0.0):
            raise ValueError("x and y must be ascending")
        if not (
            np.allclose(np.diff(x), dx, rtol=0.0, atol=1e-9 * max(1.0, abs(dx)))
            and np.allclose(np.diff(y), dy, rtol=0.0, atol=1e-9 * max(1.0, abs(dy)))
        ):
            raise ValueError("x and y must be uniformly spaced")
        self.x = x.copy()
        self.y = y.copy()
        self.heights = heights.copy()
        self.dx = float(dx)
        self.dy = float(dy)
        pad = self._PAD
        padded = self._extrapolate(self._extrapolate(heights, pad, 0), pad, 1)
        coeffs = ndimage.spline_filter(padded, order=3, mode="mirror", output=np.float64)
        self._c = np.ascontiguousarray(coeffs, dtype=np.float64)
        self._p = np.array(
            [x[0], y[0], 1.0 / dx, 1.0 / dy, float(x.size), float(y.size), float(pad)],
            dtype=np.float64,
        )

    @staticmethod
    def _extrapolate(arr: np.ndarray, pad: int, axis: int) -> np.ndarray:
        """Extend ``arr`` by ``pad`` samples at both ends of ``axis`` with the
        parabola through the three end samples (exact for quadratics)."""
        a = np.moveaxis(arr, axis, 0)
        k = np.arange(1, pad + 1, dtype=float).reshape((-1,) + (1,) * (a.ndim - 1))
        d1_lo = a[1] - a[0]
        d2_lo = a[2] - 2.0 * a[1] + a[0]
        lo = a[0] - k * d1_lo + 0.5 * k * (k + 1.0) * d2_lo  # samples -1, -2, ...
        d1_hi = a[-1] - a[-2]
        d2_hi = a[-1] - 2.0 * a[-2] + a[-3]
        hi = a[-1] + k * d1_hi + 0.5 * k * (k + 1.0) * d2_hi  # samples n, n+1, ...
        out = np.concatenate([lo[::-1], a, hi], axis=0)
        return np.moveaxis(out, 0, axis)

    @classmethod
    def from_function(cls, func: Callable, xlim, ylim, spacing: float) -> "GridSurface":
        """Sample ``func(X, Y) -> Z`` (vectorised) on a uniform grid.

        ``xlim``/``ylim`` are ``(min, max)`` [m]; ``spacing`` is the target
        node spacing [m] (the actual spacing is adjusted to fit the limits).
        """
        nx = max(4, int(round((xlim[1] - xlim[0]) / spacing)) + 1)
        ny = max(4, int(round((ylim[1] - ylim[0]) / spacing)) + 1)
        x = np.linspace(xlim[0], xlim[1], nx)
        y = np.linspace(ylim[0], ylim[1], ny)
        xx, yy = np.meshgrid(x, y, indexing="ij")
        return cls(x, y, func(xx, yy))

    @property
    def bounds(self):
        return (float(self.x[0]), float(self.x[-1]), float(self.y[0]), float(self.y[-1]))

    def _locate(self, x, y):
        nx = self.x.size
        ny = self.y.size
        x, y = np.broadcast_arrays(np.asarray(x, dtype=float), np.asarray(y, dtype=float))
        u = (x - self._p[0]) * self._p[2]
        v = (y - self._p[1]) * self._p[3]
        fx = ((u >= 0.0) & (u <= nx - 1.0)).astype(float)
        fy = ((v >= 0.0) & (v <= ny - 1.0)).astype(float)
        u = np.clip(u, 0.0, nx - 1.0)
        v = np.clip(v, 0.0, ny - 1.0)
        i = np.minimum(u.astype(np.int64), nx - 2)
        j = np.minimum(v.astype(np.int64), ny - 2)
        return i + self._PAD - 1, j + self._PAD - 1, u - i, v - j, fx, fy

    @staticmethod
    def _w(t):
        omt = 1.0 - t
        t2 = t * t
        t3 = t2 * t
        return np.stack(
            [
                omt * omt * omt / 6.0,
                (3.0 * t3 - 6.0 * t2 + 4.0) / 6.0,
                (-3.0 * t3 + 3.0 * t2 + 3.0 * t + 1.0) / 6.0,
                t3 / 6.0,
            ],
            axis=-1,
        )

    @staticmethod
    def _dw(t):
        omt = 1.0 - t
        t2 = t * t
        return np.stack(
            [-0.5 * omt * omt, 1.5 * t2 - 2.0 * t, -1.5 * t2 + t + 0.5, 0.5 * t2],
            axis=-1,
        )

    def _patch(self, ib, jb):
        k = np.arange(4)
        return self._c[ib[..., None, None] + k[:, None], jb[..., None, None] + k[None, :]]

    def _z_numpy(self, x, y):
        """Pure-numpy evaluation of z (reference for the scalar kernel)."""
        ib, jb, t, s, _, _ = self._locate(x, y)
        out = np.einsum("...km,...k,...m->...", self._patch(ib, jb), self._w(t), self._w(s))
        return _scalar_or_array(out)

    def _grad_numpy(self, x, y):
        """Pure-numpy evaluation of the gradient (reference for the scalar kernel)."""
        ib, jb, t, s, fx, fy = self._locate(x, y)
        patch = self._patch(ib, jb)
        gx = np.einsum("...km,...k,...m->...", patch, self._dw(t), self._w(s)) * self._p[2] * fx
        gy = np.einsum("...km,...k,...m->...", patch, self._w(t), self._dw(s)) * self._p[3] * fy
        return _scalar_or_array(gx), _scalar_or_array(gy)

    def z(self, x, y):
        if not HAVE_NUMBA:
            return self._z_numpy(x, y)
        x, y = np.broadcast_arrays(np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64))
        out = np.empty(x.size, dtype=np.float64)
        _grid_z_many(self._p, self._c, np.ascontiguousarray(x).ravel(), np.ascontiguousarray(y).ravel(), out)
        return _scalar_or_array(out.reshape(x.shape))

    def grad(self, x, y):
        if not HAVE_NUMBA:
            return self._grad_numpy(x, y)
        x, y = np.broadcast_arrays(np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64))
        gx = np.empty(x.size, dtype=np.float64)
        gy = np.empty(x.size, dtype=np.float64)
        _grid_grad_many(self._p, self._c, np.ascontiguousarray(x).ravel(), np.ascontiguousarray(y).ravel(), gx, gy)
        return _scalar_or_array(gx.reshape(x.shape)), _scalar_or_array(gy.reshape(x.shape))

    def kernel_spec(self):
        return _KIND_GRID, self._p, self._c

    def __repr__(self):
        b = self.bounds
        return (
            f"GridSurface({self.x.size}x{self.y.size} nodes, spacing=({self.dx:.3g}, {self.dy:.3g}) m, "
            f"x=[{b[0]:.3g}, {b[1]:.3g}], y=[{b[2]:.3g}, {b[3]:.3g}])"
        )


# --------------------------------------------------------------------------
# Capture model
# --------------------------------------------------------------------------


def capture_speed_limit(delta, v_cap0: float = V_CAP0, hole_r: float = HOLE_R, exponent: float = 0.5):
    """Maximum speed [m/s] at which a ball with impact parameter ``delta`` drops.

    ``v_cap0 * (1 - (delta/hole_r)**2) ** exponent`` for ``delta < hole_r``,
    else 0.  ``delta`` [m] is the closest distance of the ball centre's path
    to the hole centre.
    """
    delta = np.asarray(delta, dtype=float)
    ratio2 = np.clip((delta / hole_r) ** 2, 0.0, 1.0)
    out = np.where(delta < hole_r, v_cap0 * (1.0 - ratio2) ** exponent, 0.0)
    return float(out) if out.ndim == 0 else out


def is_captured(delta, speed, v_cap0: float = V_CAP0, hole_r: float = HOLE_R, exponent: float = 0.5):
    """Capture decision for impact parameter ``delta`` [m] and speed [m/s]."""
    delta = np.asarray(delta, dtype=float)
    speed = np.asarray(speed, dtype=float)
    out = (delta < hole_r) & (speed < capture_speed_limit(delta, v_cap0, hole_r, exponent))
    return bool(out) if out.ndim == 0 else out


@dataclass(frozen=True)
class CaptureModel:
    """Parameterised hole-capture rule (assumption after Holmes / Penner).

    Captured iff ``delta < hole_r`` and
    ``speed < v_cap0 * (1 - (delta/hole_r)**2) ** exponent``.
    ``exponent = 0.5`` scales with the chord crossed (default);
    ``exponent = 1.0`` is Penner's quadratic fit.  ``v_cap0 <= 0`` disables
    capture.
    """

    v_cap0: float = V_CAP0
    hole_r: float = HOLE_R
    exponent: float = 0.5

    def speed_limit(self, delta):
        """Maximum capture speed [m/s] at impact parameter ``delta`` [m]."""
        return capture_speed_limit(delta, self.v_cap0, self.hole_r, self.exponent)

    def __call__(self, delta, speed):
        """Capture decision; same signature as a custom ``capture`` callable."""
        return is_captured(delta, speed, self.v_cap0, self.hole_r, self.exponent)


CaptureLike = Union[None, CaptureModel, Callable[[float, float], bool]]

# --------------------------------------------------------------------------
# Result containers
# --------------------------------------------------------------------------


class RollStatus(enum.IntEnum):
    """How a simulated roll ended."""

    STOPPED = _ROLL_STOPPED
    """Ball at rest (rolling resistance holds it)."""
    MAX_TIME = _ROLL_MAX_TIME
    """Still moving at ``t_max`` (e.g. slope too steep for the ball to rest), or
    after ``4 * t_max / dt`` steps (a ball creeping on a slope within a
    fraction of a percent of the critical one)."""
    OUT_OF_BOUNDS = _ROLL_OUT_OF_BOUNDS
    """Left the surface grid or went beyond ``r_max`` from the start."""
    CAPTURED = _ROLL_CAPTURED
    """Integration stopped after capture (only with ``stop_on_capture=True``)."""


class SolveStatus(enum.IntEnum):
    """Outcome of :func:`solve_aim`."""

    OK = _SOLVE_OK
    """Path passes through the hole centre at the target pace."""
    PACE_LIMITED = _SOLVE_PACE_LIMITED
    """Path passes through the hole centre, but no putt that reaches the
    hole arrives as slowly as the target pace (steep downhill)."""
    UNREACHABLE = _SOLVE_UNREACHABLE
    """The ball cannot be made to reach the hole line (below ``v_max``)."""
    NO_BRACKET = _SOLVE_NO_BRACKET
    """No aim angle within ``+-phi_max`` brackets the hole."""
    NO_CONVERGENCE = _SOLVE_NO_CONVERGENCE
    """Lateral miss is discontinuous in the aim angle near the solution."""
    INVALID = _SOLVE_INVALID
    """Invalid input (zero distance, non-positive ``a_r``, ...)."""


@dataclass(frozen=True)
class PuttResult:
    """Outcome of :func:`simulate_putt` (all SI).

    Attributes
    ----------
    status : RollStatus
    t : (n,) array [s];  xy : (n, 2) array [m];  v : (n, 2) array [m/s]
        Trajectory samples (integration steps; the last row is the end state).
    start, hole : (2,) arrays [m]
    stop_xy : (2,) array [m]
        Final integrated position.  With the default ``stop_on_capture=False``
        this is where the ball would rest if there were no hole (free roll).
    t_end : float [s]
    delta : float [m]
        Closest approach of the path to the hole centre (global minimum).
    speed_at_delta : float [m/s];  t_at_delta : float [s]
    side : int
        +1 the ball passed LEFT of the hole centre at closest approach (seen
        along its travel direction), -1 right, 0 dead centre / undefined.
    crossed_hole_line : bool
        Whether the ball reached the line through the hole perpendicular to
        the start->hole direction.
    lateral_at_line : float [m]
        Signed lateral miss at that line (+ = left of the hole); NaN if short.
    speed_at_line : float [m/s];  t_at_line : float [s]  (NaN if short)
    lateral_miss : float [m]
        ``lateral_at_line`` if the ball reached the hole line, otherwise its
        lateral offset from the start->hole line (+ = left) at the point of
        furthest progress toward the hole line.  Always finite.
    shortfall : float [m]
        Distance by which the furthest progress fell short of the hole line
        (0 if the line was reached).
    captured : bool;  t_capture : float [s] (NaN if not captured)
    path_length : float [m]
    passes : (k, 3) array
        Rows ``(t [s], delta [m], speed [m/s])`` for every local minimum of
        the distance to the hole while the ball is moving (the candidates
        the capture rule is evaluated on), in time order.  A ball that comes
        to rest while still approaching the hole produces no pass; its rest
        position is tested separately.
    """

    status: RollStatus
    t: np.ndarray
    xy: np.ndarray
    v: np.ndarray
    start: np.ndarray
    hole: np.ndarray
    stop_xy: np.ndarray
    t_end: float
    delta: float
    speed_at_delta: float
    t_at_delta: float
    side: int
    crossed_hole_line: bool
    lateral_at_line: float
    speed_at_line: float
    t_at_line: float
    lateral_miss: float
    shortfall: float
    captured: bool
    t_capture: float
    path_length: float
    passes: np.ndarray

    @property
    def final_xy(self) -> np.ndarray:
        """Where the ball ends up: the hole centre if captured, else ``stop_xy``."""
        return self.hole.copy() if self.captured else self.stop_xy.copy()

    @property
    def stop_distance(self) -> float:
        """Distance from ``stop_xy`` to the hole centre [m]."""
        return float(np.hypot(*(self.stop_xy - self.hole)))

    @property
    def speed(self) -> np.ndarray:
        """Speed along the trajectory [m/s]."""
        return np.hypot(self.v[:, 0], self.v[:, 1])


@dataclass(frozen=True)
class BatchRollResult:
    """Outcome of :func:`roll_batch`; every field is an array of length N.

    Same meaning as the fields of :class:`PuttResult`.  ``final_xy`` is the
    hole centre for captured putts and the rest position otherwise;
    ``stop_xy`` is the last integrated position (the capture point when
    ``stop_on_capture=True``).  ``status`` holds :class:`RollStatus` values.
    """

    status: np.ndarray
    hole_xy: np.ndarray
    stop_xy: np.ndarray
    final_xy: np.ndarray
    t_end: np.ndarray
    delta: np.ndarray
    speed_at_delta: np.ndarray
    side: np.ndarray
    crossed_hole_line: np.ndarray
    lateral_at_line: np.ndarray
    speed_at_line: np.ndarray
    lateral_miss: np.ndarray
    shortfall: np.ndarray
    captured: np.ndarray
    path_length: np.ndarray

    def __len__(self) -> int:
        return int(self.status.shape[0])

    @property
    def stop_distance(self) -> np.ndarray:
        """Distance from ``stop_xy`` to the hole centre [m]."""
        return np.hypot(self.stop_xy[:, 0] - self.hole_xy[:, 0], self.stop_xy[:, 1] - self.hole_xy[:, 1])

    @property
    def final_distance(self) -> np.ndarray:
        """Distance from ``final_xy`` to the hole centre [m] (0 if holed)."""
        return np.hypot(self.final_xy[:, 0] - self.hole_xy[:, 0], self.final_xy[:, 1] - self.hole_xy[:, 1])


@dataclass(frozen=True)
class AimSolution:
    """Outcome of :func:`solve_aim` (all SI).

    Attributes
    ----------
    phi : float [rad]
        Launch direction relative to the straight ball->hole line,
        positive = aim left.  Best iterate even when ``ok`` is False.
    v0 : float [m/s]
        Launch speed.
    status : SolveStatus
    distance : float [m]
        Straight ball->hole distance D.
    a_r : float [m/s^2]
    v_hole_target : float [m/s]
        Target arrival speed ``sqrt(2 a_r past)``.
    v_hole : float [m/s]
        Arrival speed of the returned putt at the hole line (NaN if unknown).
    miss : float [m]
        Residual lateral miss at the hole line (+ = left; NaN if unknown).
    n_rolls : int
        Number of trial rolls used.
    """

    phi: float
    v0: float
    status: SolveStatus
    distance: float
    a_r: float
    v_hole_target: float
    v_hole: float
    miss: float
    n_rolls: int

    @property
    def ok(self) -> bool:
        """True iff the path passes through the hole centre at the target pace."""
        return self.status == SolveStatus.OK

    @property
    def usable(self) -> bool:
        """True iff the path passes through the hole centre (pace may be limited)."""
        return self.status in (SolveStatus.OK, SolveStatus.PACE_LIMITED)

    @property
    def aim_offset(self) -> float:
        """Lateral offset of the aim line at the hole distance, ``D tan(phi)`` [m]
        (the "break" to allow; + = aim left of the hole)."""
        return self.distance * math.tan(self.phi)

    @property
    def aim_offset_cups(self) -> float:
        """:attr:`aim_offset` in hole diameters (cup widths)."""
        return self.aim_offset / (2.0 * HOLE_R)

    @property
    def plays_like(self) -> float:
        """Flat-green distance with the same launch speed, ``v0^2 / (2 a_r)`` [m]."""
        return self.v0 * self.v0 / (2.0 * self.a_r)


@dataclass(frozen=True)
class AimBatchSolution:
    """Outcome of the batch aim solvers; arrays of length N (see :class:`AimSolution`)."""

    phi: np.ndarray
    v0: np.ndarray
    status: np.ndarray
    distance: np.ndarray
    a_r: np.ndarray
    v_hole_target: np.ndarray
    v_hole: np.ndarray
    miss: np.ndarray
    n_rolls: np.ndarray

    def __len__(self) -> int:
        return int(self.phi.shape[0])

    @property
    def ok(self) -> np.ndarray:
        return self.status == int(SolveStatus.OK)

    @property
    def usable(self) -> np.ndarray:
        return (self.status == int(SolveStatus.OK)) | (self.status == int(SolveStatus.PACE_LIMITED))

    @property
    def aim_offset(self) -> np.ndarray:
        return self.distance * np.tan(self.phi)

    @property
    def aim_offset_cups(self) -> np.ndarray:
        return self.aim_offset / (2.0 * HOLE_R)

    @property
    def plays_like(self) -> np.ndarray:
        return self.v0 * self.v0 / (2.0 * self.a_r)


# --------------------------------------------------------------------------
# Geometry helpers
# --------------------------------------------------------------------------


def _xy(value, name: str) -> Tuple[float, float]:
    arr = np.asarray(value, dtype=float)
    if arr.shape != (2,):
        raise ValueError(f"{name} must be a length-2 (x, y) position in metres")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} must be finite")
    return float(arr[0]), float(arr[1])


def launch_velocity(start, hole, phi: float, v0: float) -> np.ndarray:
    """Launch velocity vector [m/s] for aim angle ``phi`` [rad] and speed ``v0``.

    ``phi`` is measured from the start->hole direction, positive = left (CCW).
    """
    sx, sy = _xy(start, "start")
    hx, hy = _xy(hole, "hole")
    ang = math.atan2(hy - sy, hx - sx) + phi
    return np.array([v0 * math.cos(ang), v0 * math.sin(ang)])


def world_to_putt(points, start, hole) -> np.ndarray:
    """Transform world points (..., 2) [m] into the putt frame.

    Putt frame: origin at ``start`` (the ball), +x toward ``hole``, +y to
    the left.  The hole is at ``(D, 0)``.
    """
    sx, sy = _xy(start, "start")
    hx, hy = _xy(hole, "hole")
    ang = math.atan2(hy - sy, hx - sx)
    ca, sa = math.cos(ang), math.sin(ang)
    pts = np.asarray(points, dtype=float)
    dx = pts[..., 0] - sx
    dy = pts[..., 1] - sy
    return np.stack([dx * ca + dy * sa, -dx * sa + dy * ca], axis=-1)


def putt_to_world(points, start, hole) -> np.ndarray:
    """Inverse of :func:`world_to_putt`."""
    sx, sy = _xy(start, "start")
    hx, hy = _xy(hole, "hole")
    ang = math.atan2(hy - sy, hx - sx)
    ca, sa = math.cos(ang), math.sin(ang)
    pts = np.asarray(points, dtype=float)
    px = pts[..., 0]
    py = pts[..., 1]
    return np.stack([sx + px * ca - py * sa, sy + px * sa + py * ca], axis=-1)


def _check_common(a_r, dt, t_max):
    if not (np.all(np.asarray(a_r) > 0.0) and np.all(np.isfinite(a_r))):
        raise ValueError("a_r must be positive and finite [m/s^2]")
    if not (dt > 0.0):
        raise ValueError("dt must be positive [s]")
    if not (t_max > 0.0):
        raise ValueError("t_max must be positive [s]")


def _passes_from_trajectory(t, xy, v, hole) -> np.ndarray:
    """Local minima of the distance to the hole along a recorded trajectory.

    Same rule and same arithmetic as the roll kernel: a pass lies in step k
    when the ball approaches the hole at its start and no longer at its end
    while still moving; it is located on the cubic Hermite segment of the
    step.  Returns rows ``(t [s], delta [m], speed [m/s])`` in time order.
    """
    hx, hy = hole
    speed = np.hypot(v[:, 0], v[:, 1])
    q = (hx - xy[:, 0]) * v[:, 0] + (hy - xy[:, 1]) * v[:, 1]
    rows = []
    idx = np.nonzero((q[:-1] > 0.0) & (q[1:] <= 0.0) & (speed[1:] > 0.0))[0]
    for k in idx:
        h = t[k + 1] - t[k]
        w, dd2, sp, _ = _hermite_closest(
            xy[k, 0], xy[k, 1], v[k, 0], v[k, 1], xy[k + 1, 0], xy[k + 1, 1], v[k + 1, 0], v[k + 1, 1], h, hx, hy
        )
        rows.append((t[k] + w * h, math.sqrt(dd2), sp))
    return np.array(rows, dtype=float).reshape(-1, 3)


# --------------------------------------------------------------------------
# Public simulation API
# --------------------------------------------------------------------------


def simulate_putt(
    surface: Surface,
    start,
    hole,
    phi: float,
    v0: float,
    a_r: float,
    grain: GrainLike = None,
    *,
    dt: float = DEFAULT_DT,
    t_max: float = DEFAULT_T_MAX,
    r_max: float = DEFAULT_R_MAX,
    capture: CaptureLike = None,
    stop_on_capture: bool = False,
) -> PuttResult:
    """Roll one putt and return its full trajectory and outcome.

    Parameters
    ----------
    surface : Surface
        Height field the ball rolls on.
    start, hole : (x, y) [m]
        Ball position and hole centre.
    phi : float [rad]
        Launch direction relative to the straight start->hole line,
        positive = left (CCW).
    v0 : float [m/s]
        Launch speed (>= 0).
    a_r : float [m/s^2]
        Flat-green rolling deceleration (see :func:`stimp_to_decel`).
    grain : None | Grain | (2,) array
        Grain as ``kappa * g_hat`` in the frame of ``surface``.
    dt : float [s]
        RK4 step.
    t_max : float [s]
        Time limit; a ball still moving then gets ``RollStatus.MAX_TIME``
        (also after ``4 * t_max / dt`` steps, see the module docstring).
    r_max : float [m]
        Range limit from the start (``RollStatus.OUT_OF_BOUNDS``).
    capture : None | CaptureModel | callable(delta, speed) -> bool
        Capture rule.  ``None`` = default :class:`CaptureModel`.  A custom
        callable is evaluated on every pass (see ``PuttResult.passes``) and
        on the rest position (with speed 0).
    stop_on_capture : bool
        If True the integration ends once the ball is holed and has reached
        the hole line (only for a :class:`CaptureModel`); default False =
        free roll through the hole, so ``stop_xy`` shows where a
        missed/over-rolled putt would finish.

    Returns
    -------
    PuttResult
    """
    sx, sy = _xy(start, "start")
    hx, hy = _xy(hole, "hole")
    a_r = float(a_r)
    _check_common(a_r, dt, t_max)
    if not (v0 >= 0.0 and math.isfinite(v0)):
        raise ValueError("v0 must be finite and >= 0 [m/s]")
    if not math.isfinite(phi):
        raise ValueError("phi must be finite [rad]")
    gvec = grain_vector(grain) * a_r
    kind, p, c = surface.kernel_spec()

    custom = capture is not None and not isinstance(capture, CaptureModel)
    model = CaptureModel() if (capture is None or custom) else capture
    if custom and stop_on_capture:
        raise ValueError("stop_on_capture requires a CaptureModel, not a custom callable")

    vel = launch_velocity((sx, sy), (hx, hy), phi, v0)
    n_cap = int(math.ceil(t_max / dt)) + 128
    out = np.empty(_NOUT, dtype=np.float64)
    while True:
        traj = np.empty((n_cap, 5), dtype=np.float64)
        _roll(
            kind, p, c, sx, sy, float(vel[0]), float(vel[1]), a_r, float(gvec[0]), float(gvec[1]),
            hx, hy, float(dt), float(t_max), float(r_max), 0, 1 if stop_on_capture else 0,
            0.0 if custom else float(model.v_cap0), float(model.exponent), float(model.hole_r),
            1, traj, out,
        )
        if int(out[_O_NREC]) < n_cap:
            break
        n_cap *= 2  # trajectory buffer was full (many stop/restart cycles): redo with more room
    n = int(out[_O_NREC])
    t = traj[:n, 0].copy()
    xy = traj[:n, 1:3].copy()
    v = traj[:n, 3:5].copy()
    status = RollStatus(int(out[_O_STATUS]))
    hole_arr = np.array([hx, hy])
    stop_xy = np.array([out[_O_X], out[_O_Y]])
    passes = _passes_from_trajectory(t, xy, v, (hx, hy))

    crossed = bool(out[_O_CROSSED] > 0.5)
    captured = bool(out[_O_CAPT] > 0.5)
    t_capture = float(out[_O_TCAPT])
    if custom:
        captured = False
        t_capture = math.nan
        for row in passes:
            if bool(capture(float(row[1]), float(row[2]))):
                captured = True
                t_capture = float(row[0])
                break
        if not captured and status == RollStatus.STOPPED:
            rest = float(np.hypot(*(stop_xy - hole_arr)))
            if bool(capture(rest, 0.0)):
                captured = True
                t_capture = float(out[_O_T])

    return PuttResult(
        status=status,
        t=t,
        xy=xy,
        v=v,
        start=np.array([sx, sy]),
        hole=hole_arr,
        stop_xy=stop_xy,
        t_end=float(out[_O_T]),
        delta=float(out[_O_DMIN]),
        speed_at_delta=float(out[_O_SMIN]),
        t_at_delta=float(out[_O_TMIN]),
        side=int(out[_O_SIDE]),
        crossed_hole_line=crossed,
        lateral_at_line=float(out[_O_YLINE]),
        speed_at_line=float(out[_O_SLINE]),
        t_at_line=float(out[_O_TLINE]),
        lateral_miss=float(out[_O_YLINE] if crossed else out[_O_YPROG]),
        shortfall=0.0 if crossed else max(0.0, math.hypot(hx - sx, hy - sy) - float(out[_O_XPROG])),
        captured=captured,
        t_capture=t_capture,
        path_length=float(out[_O_PATH]),
        passes=passes,
    )


def _broadcast_xy(value, n: int, name: str) -> Tuple[np.ndarray, np.ndarray]:
    arr = np.asarray(value, dtype=np.float64)
    if arr.shape == (2,):
        arr = np.broadcast_to(arr, (n, 2))
    if arr.shape != (n, 2):
        raise ValueError(f"{name} must have shape (2,) or (N, 2)")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} must be finite")
    return np.ascontiguousarray(arr[:, 0]), np.ascontiguousarray(arr[:, 1])


def _broadcast_1d(value, n: int, name: str) -> np.ndarray:
    arr = np.asarray(value, dtype=np.float64)
    if arr.ndim == 0:
        arr = np.full(n, float(arr))
    if arr.shape != (n,):
        raise ValueError(f"{name} must be a scalar or have shape (N,)")
    return np.ascontiguousarray(arr)


def _batch_len(scalars, points, grain) -> int:
    """Batch size implied by per-putt scalars (0-d or (N,)), points ((2,) or
    (N, 2)) and a grain specification (None, Grain, (2,) or (N, 2))."""
    n = 1
    for val in scalars:
        arr = np.asarray(val)
        if arr.ndim == 1:
            n = max(n, arr.shape[0])
        elif arr.ndim > 1:
            raise ValueError("per-putt scalars must be scalars or 1-D arrays")
    for val in points:
        arr = np.asarray(val)
        if arr.ndim == 2:
            n = max(n, arr.shape[0])
    if grain is not None and not isinstance(grain, Grain):
        arr = np.asarray(grain)
        if arr.ndim == 2:
            n = max(n, arr.shape[0])
    return n


def _grain_arrays(grain, a_r: np.ndarray, n: int) -> Tuple[np.ndarray, np.ndarray]:
    """Grain acceleration components [m/s^2] for a batch."""
    if grain is None or isinstance(grain, Grain):
        gvec = np.broadcast_to(grain_vector(grain), (n, 2))
    else:
        gvec = np.asarray(grain, dtype=np.float64)
        if gvec.shape == (2,):
            gvec = np.broadcast_to(gvec, (n, 2))
        if gvec.shape != (n, 2):
            raise ValueError("grain must be None, a Grain, shape (2,) or shape (N, 2)")
    return np.ascontiguousarray(gvec[:, 0] * a_r), np.ascontiguousarray(gvec[:, 1] * a_r)


def roll_batch(
    surface: Surface,
    start,
    hole,
    phi,
    v0,
    a_r,
    grain=None,
    *,
    dt: float = DEFAULT_DT,
    t_max: float = DEFAULT_T_MAX,
    r_max: float = DEFAULT_R_MAX,
    capture: Optional[CaptureModel] = None,
    stop_on_capture: bool = True,
) -> BatchRollResult:
    """Roll N putts on one surface (no trajectories; batches of 16 or more
    run in parallel under numba).

    Parameters
    ----------
    surface : Surface
    start, hole : (2,) or (N, 2) [m]
    phi : scalar or (N,) [rad]
        Aim angles relative to each start->hole line (+ = left).
    v0 : scalar or (N,) [m/s]
    a_r : scalar or (N,) [m/s^2]
    grain : None | Grain | (2,) | (N, 2)
        ``kappa * g_hat`` in the surface frame.
    dt, t_max, r_max : as in :func:`simulate_putt`.
    capture : CaptureModel or None (default model)
    stop_on_capture : bool
        Stop integrating a putt once it is holed and has reached the hole
        line (default True: faster).  ``captured`` and ``lateral_at_line``
        are the same as for a free roll; ``delta`` is the closest approach
        up to that moment (identical unless a later pass would come closer).

    Returns
    -------
    BatchRollResult
        Results identical to calling :func:`simulate_putt` per putt.
    """
    n = _batch_len((phi, v0, a_r), (start, hole), grain)
    sx, sy = _broadcast_xy(start, n, "start")
    hx, hy = _broadcast_xy(hole, n, "hole")
    phi_a = _broadcast_1d(phi, n, "phi")
    v0_a = _broadcast_1d(v0, n, "v0")
    a_r_a = _broadcast_1d(a_r, n, "a_r")
    _check_common(a_r_a, dt, t_max)
    if not (np.all(v0_a >= 0.0) and np.all(np.isfinite(v0_a)) and np.all(np.isfinite(phi_a))):
        raise ValueError("v0 must be finite and >= 0, phi finite")
    agx, agy = _grain_arrays(grain, a_r_a, n)
    model = CaptureModel() if capture is None else capture
    if not isinstance(model, CaptureModel):
        raise TypeError("roll_batch needs a CaptureModel (custom callables: use simulate_putt)")

    ang = np.arctan2(hy - sy, hx - sx) + phi_a
    vx = np.ascontiguousarray(v0_a * np.cos(ang))
    vy = np.ascontiguousarray(v0_a * np.sin(ang))
    kind, p, c = surface.kernel_spec()
    outs = np.empty((n, _NOUT), dtype=np.float64)
    # a handful of putts is not worth starting the thread pool for
    kernel = _roll_many if n >= _PARALLEL_MIN_BATCH else _roll_many_serial
    kernel(
        kind, p, c, sx, sy, vx, vy, a_r_a, agx, agy, hx, hy, float(dt), float(t_max), float(r_max),
        1 if stop_on_capture else 0, float(model.v_cap0), float(model.exponent), float(model.hole_r), outs,
    )
    captured = outs[:, _O_CAPT] > 0.5
    crossed = outs[:, _O_CROSSED] > 0.5
    stop_xy = outs[:, _O_X : _O_Y + 1].copy()
    hole_xy = np.stack([hx, hy], axis=1)
    final_xy = np.where(captured[:, None], hole_xy, stop_xy)
    dist = np.hypot(hx - sx, hy - sy)
    return BatchRollResult(
        status=outs[:, _O_STATUS].astype(np.int64),
        hole_xy=hole_xy,
        stop_xy=stop_xy,
        final_xy=final_xy,
        t_end=outs[:, _O_T].copy(),
        delta=outs[:, _O_DMIN].copy(),
        speed_at_delta=outs[:, _O_SMIN].copy(),
        side=outs[:, _O_SIDE].astype(np.int64),
        crossed_hole_line=crossed,
        lateral_at_line=outs[:, _O_YLINE].copy(),
        speed_at_line=outs[:, _O_SLINE].copy(),
        lateral_miss=np.where(crossed, outs[:, _O_YLINE], outs[:, _O_YPROG]),
        shortfall=np.where(crossed, 0.0, np.maximum(0.0, dist - outs[:, _O_XPROG])),
        captured=captured,
        path_length=outs[:, _O_PATH].copy(),
    )


# --------------------------------------------------------------------------
# Public aim-solver API
# --------------------------------------------------------------------------

DEFAULT_TOL_MISS = 1e-5
"""Default solver tolerance on the lateral miss at the hole [m]."""

DEFAULT_TOL_PACE = 1e-5
"""Default solver tolerance on pace, as flat roll-out distance [m]."""

DEFAULT_PHI_MAX = 1.2
"""Default limit on |phi| searched by the solver [rad]."""

DEFAULT_V_MAX = 15.0
"""Default limit on the launch speed searched by the solver [m/s]."""

DEFAULT_MAX_ROLLS = 200
"""Default budget of trial rolls per aim solve (typical solves use 6-20)."""


def solve_aim(
    surface: Surface,
    start,
    hole,
    a_r: float,
    grain: GrainLike = None,
    past: float = DEFAULT_PAST,
    *,
    dt: float = DEFAULT_DT,
    t_max: float = DEFAULT_T_MAX,
    r_max: float = DEFAULT_R_MAX,
    tol_miss: float = DEFAULT_TOL_MISS,
    tol_pace: float = DEFAULT_TOL_PACE,
    phi_max: float = DEFAULT_PHI_MAX,
    v_max: float = DEFAULT_V_MAX,
    max_rolls: int = DEFAULT_MAX_ROLLS,
) -> AimSolution:
    """Find the launch direction and speed that hole the putt at the target pace.

    Solves for ``(phi, v0)`` such that the ball's path on ``surface`` passes
    through the hole centre and arrives there with speed
    ``v_h = sqrt(2 a_r past)`` - the speed that would carry it ``past``
    metres beyond the hole on a flat green of the same speed.  ``past = 0``
    is the putt that just dies at the hole.

    Parameters
    ----------
    surface : Surface
    start, hole : (x, y) [m]
    a_r : float [m/s^2]
    grain : None | Grain | (2,) array  (``kappa * g_hat``, surface frame)
    past : float [m] (>= 0)
    dt, t_max, r_max : integration settings (use the same ``dt`` when
        re-simulating the solution).
    tol_miss : float [m]
        Convergence tolerance on the lateral miss at the hole line.
    tol_pace : float [m]
        Convergence tolerance on pace, expressed as flat roll-out distance
        (``|v_hole^2 - v_h^2| <= 2 a_r tol_pace``).
    phi_max : float [rad];  v_max : float [m/s]
        Search limits.
    max_rolls : int
        Budget of trial rolls; exceeding it gives ``NO_CONVERGENCE``.

    Returns
    -------
    AimSolution
        ``status`` is ``SolveStatus.OK`` on success.  On failure the best
        iterate is returned with an explicit status - never silently.

    Method: nested bracketing root finds (aim angle outside, launch energy
    inside), each a secant walk to a bracket followed by Illinois regula
    falsi; the initial guesses come from the energy balance and planar
    small-slope theory.  Typically 6-15 trial rolls.

    Accuracy: with the default tolerances the returned ``(phi, v0)`` lies
    within about 3e-5 m (lateral, at the hole) and 5e-6 (relative, speed) of
    the exact solution of the discretised model.  Tolerances down to 1e-9 m
    are honoured (about twice the trial rolls); use those when the numbers
    are to be compared digit by digit with another implementation, whose
    iteration path may differ.

    Failures are physical, not numerical, in the cases examined: they occur
    on surfaces whose slope-plus-grain drive near the path approaches or
    exceeds ``a_r`` (the ball cannot be stopped or arrives on a knife edge).
    A caller that needs an aim regardless can use the returned best iterate
    together with ``miss`` and ``v_hole`` to judge it.
    """
    sx, sy = _xy(start, "start")
    hx, hy = _xy(hole, "hole")
    a_r = float(a_r)
    _check_common(a_r, dt, t_max)
    if not (past >= 0.0 and math.isfinite(past)):
        raise ValueError("past must be finite and >= 0 [m]")
    gvec = grain_vector(grain) * a_r
    kind, p, c = surface.kernel_spec()
    v_h = math.sqrt(2.0 * a_r * past)
    res = np.empty(_NRES, dtype=np.float64)
    status = _solve_kernel(
        kind, p, c, sx, sy, hx, hy, a_r, float(gvec[0]), float(gvec[1]), v_h,
        float(dt), float(t_max), float(r_max), float(tol_miss), float(tol_pace),
        float(phi_max), float(v_max), int(max_rolls), res,
    )
    return AimSolution(
        phi=float(res[_R_PHI]),
        v0=float(res[_R_V0]),
        status=SolveStatus(int(status)),
        distance=math.hypot(hx - sx, hy - sy),
        a_r=a_r,
        v_hole_target=v_h,
        v_hole=float(res[_R_VHOLE]),
        miss=float(res[_R_MISS]),
        n_rolls=int(res[_R_NROLLS]),
    )


def _pack_batch(results, statuses, dist, a_r, v_h) -> AimBatchSolution:
    return AimBatchSolution(
        phi=results[:, _R_PHI].copy(),
        v0=results[:, _R_V0].copy(),
        status=statuses.copy(),
        distance=dist.copy(),
        a_r=a_r.copy(),
        v_hole_target=v_h.copy(),
        v_hole=results[:, _R_VHOLE].copy(),
        miss=results[:, _R_MISS].copy(),
        n_rolls=results[:, _R_NROLLS].astype(np.int64),
    )


def solve_aim_batch(
    surface: Surface,
    start,
    hole,
    a_r,
    grain=None,
    past=DEFAULT_PAST,
    *,
    dt: float = DEFAULT_DT,
    t_max: float = DEFAULT_T_MAX,
    r_max: float = DEFAULT_R_MAX,
    tol_miss: float = DEFAULT_TOL_MISS,
    tol_pace: float = DEFAULT_TOL_PACE,
    phi_max: float = DEFAULT_PHI_MAX,
    v_max: float = DEFAULT_V_MAX,
    max_rolls: int = DEFAULT_MAX_ROLLS,
) -> AimBatchSolution:
    """:func:`solve_aim` for N putts on ONE surface (parallel under numba).

    ``start``/``hole``: (2,) or (N, 2) [m]; ``a_r``/``past``: scalar or (N,);
    ``grain``: None | Grain | (2,) | (N, 2).  Results equal the scalar solver.
    """
    n = _batch_len((a_r, past), (start, hole), grain)
    sx, sy = _broadcast_xy(start, n, "start")
    hx, hy = _broadcast_xy(hole, n, "hole")
    a_r_a = _broadcast_1d(a_r, n, "a_r")
    past_a = _broadcast_1d(past, n, "past")
    _check_common(a_r_a, dt, t_max)
    if not (np.all(past_a >= 0.0) and np.all(np.isfinite(past_a))):
        raise ValueError("past must be finite and >= 0 [m]")
    agx, agy = _grain_arrays(grain, a_r_a, n)
    v_h = np.sqrt(2.0 * a_r_a * past_a)
    kind, p, c = surface.kernel_spec()
    results = np.empty((n, _NRES), dtype=np.float64)
    statuses = np.empty(n, dtype=np.int64)
    _solve_many(
        kind, p, c, sx, sy, hx, hy, a_r_a, agx, agy, v_h, float(dt), float(t_max), float(r_max),
        float(tol_miss), float(tol_pace), float(phi_max), float(v_max), int(max_rolls), results, statuses,
    )
    return _pack_batch(results, statuses, np.hypot(hx - sx, hy - sy), a_r_a, v_h)


def solve_aim_quadratic_batch(
    coeffs,
    distance,
    a_r,
    grain=None,
    past=DEFAULT_PAST,
    *,
    dt: float = DEFAULT_DT,
    t_max: float = DEFAULT_T_MAX,
    r_max: float = DEFAULT_R_MAX,
    tol_miss: float = DEFAULT_TOL_MISS,
    tol_pace: float = DEFAULT_TOL_PACE,
    phi_max: float = DEFAULT_PHI_MAX,
    v_max: float = DEFAULT_V_MAX,
    max_rolls: int = DEFAULT_MAX_ROLLS,
) -> AimBatchSolution:
    """:func:`solve_aim` for N quadratic patches given in the putt frame.

    Patch ``i`` is ``z = a x + b y + 0.5 (c x^2 + 2 d x y + e y^2)`` with the
    ball at the origin and the hole at ``(distance[i], 0)`` (x toward the
    hole, y to the left).

    Parameters
    ----------
    coeffs : (N, 5) or (5,) array ``(a, b, c, d, e)``  [m/m, m/m, 1/m, 1/m, 1/m]
    distance : scalar or (N,) [m]
    a_r : scalar or (N,) [m/s^2]
    grain : None | Grain | (2,) | (N, 2)   ``kappa * g_hat`` IN THE PUTT FRAME
    past : scalar or (N,) [m]

    Returns
    -------
    AimBatchSolution
        Identical to ``solve_aim(QuadraticSurface(*coeffs[i]), (0, 0),
        (distance[i], 0), ...)`` for every ``i``.
    """
    coeffs = np.asarray(coeffs, dtype=np.float64)
    if coeffs.ndim == 1:
        coeffs = coeffs[None, :]
    if coeffs.ndim != 2 or coeffs.shape[1] != 5:
        raise ValueError("coeffs must have shape (N, 5): (a, b, c, d, e)")
    n = max(coeffs.shape[0], _batch_len((distance, a_r, past), (), grain))
    if coeffs.shape[0] == 1 and n > 1:
        coeffs = np.broadcast_to(coeffs, (n, 5))
    if coeffs.shape[0] != n:
        raise ValueError("inconsistent batch sizes")
    coeffs = np.ascontiguousarray(coeffs)
    if not np.all(np.isfinite(coeffs)):
        raise ValueError("coeffs must be finite")
    dist = _broadcast_1d(distance, n, "distance")
    a_r_a = _broadcast_1d(a_r, n, "a_r")
    past_a = _broadcast_1d(past, n, "past")
    _check_common(a_r_a, dt, t_max)
    if not (np.all(past_a >= 0.0) and np.all(np.isfinite(past_a))):
        raise ValueError("past must be finite and >= 0 [m]")
    if not np.all(np.isfinite(dist)):
        raise ValueError("distance must be finite [m]")
    agx, agy = _grain_arrays(grain, a_r_a, n)
    v_h = np.sqrt(2.0 * a_r_a * past_a)
    results = np.empty((n, _NRES), dtype=np.float64)
    statuses = np.empty(n, dtype=np.int64)
    _solve_many_quadratic(
        coeffs, dist, a_r_a, agx, agy, v_h, float(dt), float(t_max), float(r_max),
        float(tol_miss), float(tol_pace), float(phi_max), float(v_max), int(max_rolls), results, statuses,
    )
    return _pack_batch(results, statuses, dist, a_r_a, v_h)
