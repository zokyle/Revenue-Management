"""Physics invariants of the rolling-ball model and integrator (SI units)."""

import math

import numpy as np
import pytest

from greenline_sim import physics as ph

A10 = ph.stimp_to_decel(10.0)
KF = ph.ROLL_FACTOR * ph.G


def flat():
    return ph.PlaneSurface(0.0, 0.0)


# --------------------------------------------------------------------------
# constants and elementary relations
# --------------------------------------------------------------------------


def test_constants_match_spec():
    assert ph.G == 9.80665
    assert ph.STIMP_V0 == 1.83
    assert ph.FT == 0.3048
    assert ph.BALL_R == 0.021335
    assert ph.HOLE_R == 0.053975
    assert ph.V_CAP0 == 1.63
    assert ph.ROLL_FACTOR == pytest.approx(5.0 / 7.0)


def test_stimp_to_decel_reference_value():
    # Stimp 10 -> 0.549 m/s^2
    assert ph.stimp_to_decel(10.0) == pytest.approx(0.549, abs=5e-4)
    assert ph.stimp_to_decel(10.0) == pytest.approx(1.83**2 / (2 * 10 * 0.3048), rel=1e-15)
    stimps = np.array([7.0, 9.5, 13.0])
    assert np.allclose(ph.decel_to_stimp(ph.stimp_to_decel(stimps)), stimps, rtol=1e-14)
    with pytest.raises(ValueError):
        ph.stimp_to_decel(0.0)


def test_target_hole_speed_and_critical_slope():
    assert ph.target_hole_speed(A10, 0.30) == pytest.approx(math.sqrt(2 * A10 * 0.30))
    assert ph.flat_roll_distance(ph.target_hole_speed(A10, 0.30), A10) == pytest.approx(0.30)
    assert ph.critical_slope(A10) == pytest.approx(A10 / KF)
    assert 0.07 < ph.critical_slope(A10) < 0.085  # ~7.8 % at Stimp 10


@pytest.mark.parametrize("stimp", [7.0, 9.0, 10.0, 11.5, 13.0])
def test_flat_roll_distance_equals_stimp(stimp):
    """A ball released at 1.83 m/s on a flat green rolls the Stimp distance."""
    a_r = ph.stimp_to_decel(stimp)
    res = ph.simulate_putt(flat(), (0.0, 0.0), (1.0, 0.0), 0.0, ph.STIMP_V0, a_r)
    assert res.status == ph.RollStatus.STOPPED
    rolled = float(np.hypot(*res.stop_xy))
    assert rolled == pytest.approx(stimp * ph.FT, rel=0.005)  # spec tolerance
    assert rolled == pytest.approx(stimp * ph.FT, rel=1e-7)  # what is actually achieved
    assert res.t_end == pytest.approx(ph.STIMP_V0 / a_r, rel=1e-5)
    assert res.path_length == pytest.approx(rolled, rel=1e-9)
    assert abs(res.stop_xy[1]) < 1e-12


# --------------------------------------------------------------------------
# integrator quality
# --------------------------------------------------------------------------

CONVERGENCE_CASES = [
    (ph.QuadraticSurface(0.012, 0.02, 0.004, -0.003, 0.005), 0.12, 3.0, 6.0),
    (ph.PlaneSurface(-0.03, 0.03), 0.30, 2.0, 5.0),
    (ph.QuadraticSurface(-0.01, 0.015, 0.003, 0.002, -0.004), -0.08, 3.5, 9.0),
]


@pytest.mark.parametrize("surf,phi,v0,dist", CONVERGENCE_CASES)
def test_time_step_convergence(surf, phi, v0, dist):
    grain = ph.Grain(0.08, 1.0)
    hole = (dist, 0.0)
    ref = ph.simulate_putt(surf, (0, 0), hole, phi, v0, A10, grain, dt=0.000625)
    assert ref.status == ph.RollStatus.STOPPED
    errs = {}
    for dt in (0.08, 0.04, 0.02, 0.01):
        r = ph.simulate_putt(surf, (0, 0), hole, phi, v0, A10, grain, dt=dt)
        assert r.status == ph.RollStatus.STOPPED
        errs[dt] = (
            float(np.hypot(*(r.stop_xy - ref.stop_xy))),
            abs(r.delta - ref.delta),
            abs(r.speed_at_delta - ref.speed_at_delta),
            abs(r.lateral_at_line - ref.lateral_at_line),
            abs(r.speed_at_line - ref.speed_at_line),
        )
    # coarse step already good to a micron; default step to 0.1 micron
    assert max(errs[0.08][:2]) < 2e-6
    assert max(errs[0.04]) < 2e-7
    assert max(errs[0.02]) < 5e-8
    assert max(errs[0.01]) < 5e-8
    # and the error really shrinks with the step
    assert errs[0.02][0] < errs[0.08][0]
    assert errs[0.02][3] < errs[0.08][3]


@pytest.mark.parametrize("surf,phi,v0,dist", CONVERGENCE_CASES)
def test_against_independent_scipy_integrator(surf, phi, v0, dist):
    """Cross-check the hand-written RK4 kernel against scipy's DOP853 applied
    to the same equation of motion written independently here."""
    from scipy.integrate import solve_ivp

    grain = ph.Grain(0.08, 1.0)
    acc_g = grain.vector * A10

    def rhs(_t, s):
        gx, gy = surf.grad(s[0], s[1])
        speed = math.hypot(s[2], s[3])
        return [
            s[2],
            s[3],
            -A10 * s[2] / speed - KF * gx + acc_g[0],
            -A10 * s[3] / speed - KF * gy + acc_g[1],
        ]

    def nearly_stopped(_t, s):
        return math.hypot(s[2], s[3]) - 1e-3

    nearly_stopped.terminal = True
    r = ph.simulate_putt(surf, (0, 0), (dist, 0), phi, v0, A10, grain)
    y0 = [0.0, 0.0, v0 * math.cos(phi), v0 * math.sin(phi)]
    # (a) mid-roll state at a sample time on the fixed-step part of the path
    k = int(0.7 * r.t_end / ph.DEFAULT_DT)
    t_mid = r.t[k]
    assert t_mid == pytest.approx(k * ph.DEFAULT_DT, abs=1e-12)
    ref = solve_ivp(rhs, (0.0, t_mid), y0, method="DOP853", rtol=1e-12, atol=1e-14)
    assert ref.success
    assert np.allclose(r.xy[k], ref.y[:2, -1], rtol=0, atol=2e-8)
    assert np.allclose(r.v[k], ref.y[2:, -1], rtol=0, atol=2e-8)
    # (b) rest position: integrate the reference down to 1 mm/s, where less
    # than 1e-6 m of roll remains (v^2 / 2a), and compare
    ref = solve_ivp(rhs, (0.0, 60.0), y0, method="DOP853", rtol=1e-12, atol=1e-14, events=nearly_stopped)
    assert ref.success and ref.t_events[0].size == 1
    assert np.hypot(*(r.stop_xy - ref.y[:2, -1])) < 2e-6


def test_default_dt_is_converged():
    surf, phi, v0, dist = CONVERGENCE_CASES[0]
    a = ph.simulate_putt(surf, (0, 0), (dist, 0), phi, v0, A10)
    b = ph.simulate_putt(surf, (0, 0), (dist, 0), phi, v0, A10, dt=ph.DEFAULT_DT / 8)
    assert np.hypot(*(a.stop_xy - b.stop_xy)) < 5e-8


def test_stop_is_clean_without_jitter():
    """Near v -> 0 the speed decays monotonically, the ball never reverses,
    and the trajectory ends exactly at rest."""
    surf = ph.QuadraticSurface(0.012, 0.02, 0.004, -0.003, 0.005)
    r = ph.simulate_putt(surf, (0, 0), (6, 0), 0.12, 3.0, A10, ph.Grain(0.05, 2.0))
    assert r.status == ph.RollStatus.STOPPED
    speed = r.speed
    assert speed[-1] == 0.0 and np.all(r.v[-1] == 0.0)
    assert np.all(np.diff(r.t) > 0.0)
    tail = slice(-40, None)
    assert np.all(np.diff(speed[tail]) < 0.0)  # strictly decaying
    steps = np.diff(r.xy[tail], axis=0)
    # consecutive displacements never point backwards
    assert np.all(np.sum(steps[1:] * steps[:-1], axis=1) >= 0.0)
    # the adaptive stopping phase takes only a handful of steps
    assert len(r.t) < r.t_end / ph.DEFAULT_DT + 30
    # the final position is the last sample
    assert np.allclose(r.xy[-1], r.stop_xy, atol=0.0)
    # a rest position must be holdable
    gx, gy = surf.grad(*r.stop_xy)
    gvec = ph.Grain(0.05, 2.0).vector * A10
    assert math.hypot(gvec[0] - KF * gx, gvec[1] - KF * gy) < A10


def test_ball_at_rest_stays_or_starts():
    # holdable slope: nothing happens
    r = ph.simulate_putt(ph.PlaneSurface(0.03, 0.0), (0, 0), (3, 0), 0.0, 0.0, A10)
    assert r.status == ph.RollStatus.STOPPED and r.t_end == 0.0 and np.all(r.stop_xy == 0.0)
    # steeper than critical: the ball starts rolling downhill by itself
    steep = ph.PlaneSurface(0.10, 0.0)
    assert 0.10 > ph.critical_slope(A10)
    r = ph.simulate_putt(steep, (0, 0), (3, 0), 0.0, 0.0, A10, t_max=5.0)
    assert r.status == ph.RollStatus.MAX_TIME
    net = KF * 0.10 - A10
    assert r.stop_xy[0] == pytest.approx(-0.5 * net * 5.0**2, rel=1e-6)
    assert r.v[-1, 0] == pytest.approx(-net * 5.0, rel=1e-6)


def test_too_steep_keeps_rolling_with_clear_status():
    steep = ph.PlaneSurface(0.10, 0.0)  # rises along +x at 10 %
    # putt uphill: the ball climbs, stops momentarily, then rolls back down
    r = ph.simulate_putt(steep, (0, 0), (3, 0), 0.0, 2.0, A10, t_max=20.0)
    assert r.status in (ph.RollStatus.MAX_TIME, ph.RollStatus.OUT_OF_BOUNDS)
    assert r.status != ph.RollStatus.STOPPED
    x_top = r.xy[:, 0].max()
    assert x_top == pytest.approx(2.0**2 / (2 * (A10 + KF * 0.10)), rel=1e-6)
    assert r.stop_xy[0] < 0.0  # came back past the start
    # range limit gives OUT_OF_BOUNDS
    r2 = ph.simulate_putt(steep, (0, 0), (3, 0), 0.0, 2.0, A10, t_max=60.0, r_max=10.0)
    assert r2.status == ph.RollStatus.OUT_OF_BOUNDS
    assert np.hypot(*r2.stop_xy) > 10.0


def test_energy_balance():
    """Work-energy theorem of the model:
    v0^2 - v^2 = 2 a_r L + 2 (5/7) G dz - 2 a_grain . dr  along the path."""
    surf = ph.QuadraticSurface(0.012, -0.02, 0.004, -0.003, 0.005)
    grain = ph.Grain(0.10, 0.7)
    v0 = 3.2
    r = ph.simulate_putt(surf, (0.3, -0.2), (6.0, 0.4), 0.1, v0, A10, grain)
    assert r.status == ph.RollStatus.STOPPED
    dz = surf.z(*r.stop_xy) - surf.z(0.3, -0.2)
    dr = r.stop_xy - np.array([0.3, -0.2])
    work = 2 * A10 * r.path_length + 2 * KF * dz - 2 * A10 * float(grain.vector @ dr)
    assert work == pytest.approx(v0**2, rel=2e-6)
    # also at every sample of the trajectory
    seg = np.hypot(*np.diff(r.xy, axis=0).T)
    length = np.concatenate([[0.0], np.cumsum(seg)])
    dz_t = surf.z(r.xy[:, 0], r.xy[:, 1]) - surf.z(0.3, -0.2)
    dr_t = r.xy - np.array([0.3, -0.2])
    lhs = v0**2 - r.speed**2
    rhs = 2 * A10 * length + 2 * KF * dz_t - 2 * A10 * (dr_t @ grain.vector)
    assert np.max(np.abs(lhs - rhs)) < 2e-5


def test_mirror_symmetry():
    """Mirroring the surface, grain and aim about the putt line mirrors the path."""
    a, b, c, d, e = 0.012, 0.02, 0.004, -0.003, 0.005
    s1 = ph.QuadraticSurface(a, b, c, d, e)
    s2 = ph.QuadraticSurface(a, -b, c, -d, e)
    g1 = ph.Grain(0.08, 0.9)
    g2 = ph.Grain(0.08, -0.9)
    r1 = ph.simulate_putt(s1, (0, 0), (6, 0), 0.11, 3.0, A10, g1)
    r2 = ph.simulate_putt(s2, (0, 0), (6, 0), -0.11, 3.0, A10, g2)
    assert len(r1.t) == len(r2.t)
    assert np.allclose(r1.xy[:, 0], r2.xy[:, 0], atol=1e-12)
    assert np.allclose(r1.xy[:, 1], -r2.xy[:, 1], atol=1e-12)
    assert r1.lateral_at_line == pytest.approx(-r2.lateral_at_line, abs=1e-12)
    assert r1.side == -r2.side
    assert r1.delta == pytest.approx(r2.delta, abs=1e-12)


def test_rotation_and_translation_invariance():
    """The same putt described in a rotated/translated world frame gives the
    same outcome in putt-frame terms."""
    a, b = 0.015, -0.022
    grain = ph.Grain(0.07, 0.4)
    base = ph.simulate_putt(ph.PlaneSurface(a, b), (0, 0), (5, 0), 0.09, 2.8, A10, grain)
    ang = 1.234
    ca, sa = math.cos(ang), math.sin(ang)
    start = np.array([3.0, -2.0])
    hole = start + 5.0 * np.array([ca, sa])
    # plane with the same gradient rotated by ang; passes through any height at start
    ar, br = a * ca - b * sa, a * sa + b * ca
    rot = ph.simulate_putt(ph.PlaneSurface(ar, br, z0=0.37), start, hole, 0.09, 2.8, A10, grain.rotated(-ang))
    assert rot.lateral_at_line == pytest.approx(base.lateral_at_line, abs=1e-10)
    assert rot.speed_at_line == pytest.approx(base.speed_at_line, abs=1e-10)
    assert rot.delta == pytest.approx(base.delta, abs=1e-10)
    assert np.allclose(ph.world_to_putt(rot.stop_xy, start, hole), base.stop_xy, atol=1e-9)
    assert np.allclose(ph.putt_to_world(ph.world_to_putt(rot.xy, start, hole), start, hole), rot.xy, atol=1e-12)


@pytest.mark.parametrize("kappa,az", [(0.05, 0.0), (0.12, 2.1), (0.15, -1.3)])
def test_grain_is_equivalent_to_a_slope(kappa, az):
    """A grain kappa along g_hat rolls exactly like an extra tilt that falls
    by (7/5) kappa a_r / G per metre along g_hat."""
    a, b = 0.01, -0.015
    s_eq = ph.grain_equivalent_slope(kappa, A10)
    assert s_eq == pytest.approx(1.4 * kappa * A10 / ph.G)
    with_grain = ph.simulate_putt(ph.PlaneSurface(a, b), (0, 0), (5, 0), 0.05, 2.7, A10, ph.Grain(kappa, az))
    tilted = ph.PlaneSurface(a - s_eq * math.cos(az), b - s_eq * math.sin(az))
    no_grain = ph.simulate_putt(tilted, (0, 0), (5, 0), 0.05, 2.7, A10, None)
    assert len(with_grain.t) == len(no_grain.t)
    assert np.allclose(with_grain.xy, no_grain.xy, atol=1e-11)
    assert np.allclose(with_grain.v, no_grain.v, atol=1e-11)
    # grain given as a raw vector is the same thing
    vec = ph.simulate_putt(ph.PlaneSurface(a, b), (0, 0), (5, 0), 0.05, 2.7, A10, ph.Grain(kappa, az).vector)
    assert np.array_equal(vec.xy, with_grain.xy)


def test_down_grain_rolls_further_than_into_grain():
    down = ph.simulate_putt(flat(), (0, 0), (3, 0), 0.0, 2.0, A10, ph.Grain(0.1, 0.0))
    into = ph.simulate_putt(flat(), (0, 0), (3, 0), 0.0, 2.0, A10, ph.Grain(0.1, math.pi))
    assert down.stop_xy[0] == pytest.approx(2.0**2 / (2 * A10 * 0.9), rel=1e-7)
    assert into.stop_xy[0] == pytest.approx(2.0**2 / (2 * A10 * 1.1), rel=1e-7)


def test_uphill_shorter_downhill_longer_closed_form():
    v0 = 2.5
    for s in (-0.03, -0.01, 0.0, 0.01, 0.03):
        r = ph.simulate_putt(ph.PlaneSurface(s, 0.0), (0, 0), (4, 0), 0.0, v0, A10)
        assert r.status == ph.RollStatus.STOPPED
        assert r.stop_xy[0] == pytest.approx(v0**2 / (2 * (A10 + KF * s)), rel=1e-7)
        assert abs(r.stop_xy[1]) < 1e-12


# --------------------------------------------------------------------------
# closest approach, hole line, capture
# --------------------------------------------------------------------------


def test_closest_approach_and_hole_line_on_flat_green():
    dist, phi, v0 = 4.0, 0.05, 3.0
    r = ph.simulate_putt(flat(), (0, 0), (dist, 0), phi, v0, A10)
    assert r.delta == pytest.approx(dist * math.sin(phi), abs=1e-9)
    assert r.speed_at_delta == pytest.approx(math.sqrt(v0**2 - 2 * A10 * dist * math.cos(phi)), abs=1e-8)
    assert r.side == 1  # aimed left -> passes left of the hole
    assert r.crossed_hole_line
    assert r.lateral_at_line == pytest.approx(dist * math.tan(phi), abs=1e-9)
    assert r.lateral_miss == r.lateral_at_line and r.shortfall == 0.0
    assert r.speed_at_line == pytest.approx(math.sqrt(v0**2 - 2 * A10 * dist / math.cos(phi)), abs=1e-8)
    assert r.passes.shape == (1, 3)
    assert r.passes[0, 1] == pytest.approx(r.delta, abs=1e-12)
    assert r.passes[0, 2] == pytest.approx(r.speed_at_delta, abs=1e-12)
    # aimed right
    r = ph.simulate_putt(flat(), (0, 0), (dist, 0), -phi, v0, A10)
    assert r.side == -1 and r.lateral_at_line == pytest.approx(-dist * math.tan(phi), abs=1e-9)


def test_short_putt_reports_no_crossing():
    r = ph.simulate_putt(flat(), (0, 0), (4, 0), 0.0, 1.0, A10)
    assert not r.crossed_hole_line
    assert math.isnan(r.lateral_at_line) and math.isnan(r.speed_at_line)
    short = 4.0 - 1.0 / (2 * A10)
    assert r.delta == pytest.approx(short, abs=1e-8)
    assert r.speed_at_delta == 0.0
    assert not r.captured
    assert r.passes.shape == (0, 3)
    assert r.stop_distance == pytest.approx(short, abs=1e-8)
    assert r.shortfall == pytest.approx(short, abs=1e-8) and r.lateral_miss == pytest.approx(0.0, abs=1e-12)
    # short and offline: the lateral miss is taken at the furthest progress
    r = ph.simulate_putt(flat(), (0, 0), (4, 0), 0.1, 1.0, A10)
    rolled = 1.0 / (2 * A10)
    assert not r.crossed_hole_line
    assert r.lateral_miss == pytest.approx(rolled * math.sin(0.1), abs=1e-8)
    assert r.shortfall == pytest.approx(4.0 - rolled * math.cos(0.1), abs=1e-8)


def test_capture_speed_limit_function():
    assert ph.capture_speed_limit(0.0) == pytest.approx(ph.V_CAP0)
    assert ph.capture_speed_limit(ph.HOLE_R) == 0.0
    assert ph.capture_speed_limit(0.1) == 0.0
    d = np.linspace(0, ph.HOLE_R, 20)
    lim = ph.capture_speed_limit(d)
    assert np.all(np.diff(lim) < 0)
    assert lim[10] == pytest.approx(ph.V_CAP0 * math.sqrt(1 - (d[10] / ph.HOLE_R) ** 2))
    penner = ph.CaptureModel(exponent=1.0)
    assert penner.speed_limit(0.03) == pytest.approx(1.63 * (1 - (0.03 / ph.HOLE_R) ** 2))
    assert ph.is_captured(0.0, 1.62) and not ph.is_captured(0.0, 1.64)
    assert not ph.is_captured(0.06, 0.01)


def _arrive(v_arrive, offset=0.0, dist=3.0, **kw):
    """Flat putt travelling along +x that passes the hole at lateral offset
    `offset` [m] (hole to the left for offset > 0) with speed `v_arrive`."""
    v0 = math.sqrt(v_arrive**2 + 2 * A10 * dist)
    return ph.simulate_putt(flat(), (0, 0), (dist, offset), -math.atan2(offset, dist), v0, A10, **kw)


def test_capture_dead_centre_threshold():
    assert _arrive(1.60).captured
    assert not _arrive(1.66).captured
    r = _arrive(1.0)
    assert r.captured and r.delta < 1e-9 and r.speed_at_delta == pytest.approx(1.0, abs=1e-6)
    assert np.allclose(r.final_xy, r.hole)
    assert r.t_capture == pytest.approx(r.t_at_delta)
    # free roll continues past the hole by v^2 / (2 a_r)
    assert r.stop_xy[0] - 3.0 == pytest.approx(1.0 / (2 * A10), rel=1e-6)


def test_capture_off_centre_threshold():
    off = 0.03
    limit = ph.capture_speed_limit(off)
    assert limit == pytest.approx(1.63 * math.sqrt(1 - (off / ph.HOLE_R) ** 2))
    below = _arrive(limit - 0.03, off)
    above = _arrive(limit + 0.03, off)
    assert below.delta == pytest.approx(off, abs=1e-9) and below.side == -1
    assert below.captured and not above.captured
    # outside the hole radius: never captured while moving
    assert not _arrive(0.3, 0.06).captured
    # other capture rules can be swapped in
    penner = ph.CaptureModel(exponent=1.0)
    v_mid = 0.5 * (penner.speed_limit(off) + limit)  # between the two limits
    assert _arrive(v_mid, off).captured and not _arrive(v_mid, off, capture=penner).captured
    assert not _arrive(1.0, 0.0, capture=lambda delta, speed: False).captured
    assert _arrive(1.66, 0.0, capture=lambda delta, speed: delta < ph.HOLE_R and speed < 2.0).captured


def test_ball_dying_in_the_hole_is_captured():
    # stops 2 cm short of the centre: centre inside the hole radius -> holed
    v0 = math.sqrt(2 * A10 * (3.0 - 0.02))
    r = ph.simulate_putt(flat(), (0, 0), (3, 0), 0.0, v0, A10)
    assert r.status == ph.RollStatus.STOPPED and r.captured
    assert r.delta == pytest.approx(0.02, abs=1e-8)
    # stops 8 cm short: not holed
    v0 = math.sqrt(2 * A10 * (3.0 - 0.08))
    assert not ph.simulate_putt(flat(), (0, 0), (3, 0), 0.0, v0, A10).captured
    # custom rule also sees the rest position
    r = ph.simulate_putt(flat(), (0, 0), (3, 0), 0.0, math.sqrt(2 * A10 * 2.98), A10, capture=ph.is_captured)
    assert r.captured


def test_stop_on_capture_truncates_the_roll():
    full = _arrive(1.0)
    cut = _arrive(1.0, stop_on_capture=True)
    assert cut.status == ph.RollStatus.CAPTURED and cut.captured
    assert cut.t_end < full.t_end
    assert np.hypot(*(cut.stop_xy - cut.hole)) < 0.03
    assert cut.delta == pytest.approx(full.delta, abs=1e-12)
    assert np.allclose(cut.final_xy, cut.hole)
    with pytest.raises(ValueError):
        _arrive(1.0, capture=lambda d, s: True, stop_on_capture=True)


def test_ball_rolling_back_into_the_hole_is_captured():
    """Too fast on the first pass, the ball climbs a slope beyond the hole,
    rolls back and drops on the second pass."""
    surf = ph.QuadraticSurface(0.0, 0.0, 0.03, 0.0, 0.0)  # valley along y: z = 0.015 x^2
    hole = (0.5, 0.0)
    r = ph.simulate_putt(surf, (-2.0, 0.0), hole, 0.0, 4.0, A10)
    assert len(r.passes) >= 2
    assert r.passes[0, 2] > ph.V_CAP0  # first pass too fast
    assert r.captured
    assert r.t_capture == pytest.approx(r.passes[1, 0])
    assert r.passes[1, 2] < ph.V_CAP0
    # the batch kernel agrees
    b = ph.roll_batch(surf, (-2.0, 0.0), hole, 0.0, 4.0, A10)
    assert bool(b.captured[0]) and np.allclose(b.final_xy[0], hole)


# --------------------------------------------------------------------------
# batch API
# --------------------------------------------------------------------------


def test_roll_batch_matches_simulate_putt():
    rng = np.random.default_rng(5)
    surf = ph.QuadraticSurface(0.01, -0.015, 0.003, 0.002, -0.004)
    n = 40
    start = rng.uniform(-1, 1, size=(n, 2))
    hole = start + np.column_stack([rng.uniform(2, 8, n), rng.uniform(-1, 1, n)])
    phi = rng.uniform(-0.15, 0.15, n)
    v0 = rng.uniform(1.5, 4.0, n)
    a_r = ph.stimp_to_decel(rng.uniform(8, 12, n))
    grain = np.column_stack([rng.uniform(-0.1, 0.1, n), rng.uniform(-0.1, 0.1, n)])
    for stop_on_capture in (False, True):
        batch = ph.roll_batch(surf, start, hole, phi, v0, a_r, grain, stop_on_capture=stop_on_capture)
        assert len(batch) == n
        for i in range(n):
            one = ph.simulate_putt(surf, start[i], hole[i], phi[i], v0[i], a_r[i], grain[i])
            assert batch.captured[i] == one.captured
            assert batch.delta[i] == one.delta
            assert batch.crossed_hole_line[i] == one.crossed_hole_line
            if one.crossed_hole_line:
                assert batch.lateral_at_line[i] == one.lateral_at_line
                assert batch.speed_at_line[i] == one.speed_at_line
            assert batch.side[i] == one.side
            assert batch.lateral_miss[i] == one.lateral_miss and batch.shortfall[i] == one.shortfall
            assert np.isfinite(batch.lateral_miss[i])
            assert np.array_equal(batch.final_xy[i], one.final_xy)
            assert batch.final_distance[i] == pytest.approx(np.hypot(*(one.final_xy - one.hole)))
            if not stop_on_capture:
                assert batch.status[i] == int(one.status)
                assert np.array_equal(batch.stop_xy[i], one.stop_xy)
                assert batch.path_length[i] == one.path_length


def test_roll_batch_broadcasting_and_validation():
    surf = ph.PlaneSurface(0.0, 0.01)
    out = ph.roll_batch(surf, (0, 0), (3, 0), np.array([0.0, 0.05, 0.1]), 2.0, A10)
    assert len(out) == 3 and out.final_xy.shape == (3, 2)
    assert np.all(np.diff(out.lateral_at_line) > 0)
    # small batches (serial kernel) and large ones (parallel kernel) agree
    phi = np.linspace(-0.1, 0.1, 64)
    big = ph.roll_batch(surf, (0, 0), (3, 0), phi, 2.0, A10)
    small = [ph.roll_batch(surf, (0, 0), (3, 0), phi[i : i + 4], 2.0, A10) for i in range(0, 64, 4)]
    assert np.array_equal(big.lateral_miss, np.concatenate([s.lateral_miss for s in small]))
    assert np.array_equal(big.stop_xy, np.concatenate([s.stop_xy for s in small]))
    assert np.array_equal(big.captured, np.concatenate([s.captured for s in small]))
    with pytest.raises(ValueError):
        ph.roll_batch(surf, (0, 0), (3, 0), 0.0, -1.0, A10)
    with pytest.raises(ValueError):
        ph.roll_batch(surf, (0, 0), (3, 0), 0.0, 1.0, 0.0)
    with pytest.raises(TypeError):
        ph.roll_batch(surf, (0, 0), (3, 0), 0.0, 1.0, A10, capture=lambda d, s: True)


def test_simulate_putt_validation():
    with pytest.raises(ValueError):
        ph.simulate_putt(flat(), (0, 0), (3, 0), 0.0, 1.0, -0.5)
    with pytest.raises(ValueError):
        ph.simulate_putt(flat(), (0, 0), (3, 0), 0.0, -1.0, A10)
    with pytest.raises(ValueError):
        ph.simulate_putt(flat(), (0, 0, 0), (3, 0), 0.0, 1.0, A10)
    with pytest.raises(ValueError):
        ph.simulate_putt(flat(), (0, 0), (3, 0), 0.0, 1.0, A10, dt=0.0)
    with pytest.raises(ValueError):
        ph.simulate_putt(flat(), (0, 0), (3, 0), 0.0, 1.0, A10, grain=(1.0, 2.0, 3.0))


def test_long_stop_restart_trajectory_is_fully_recorded():
    """Many stop/restart cycles must not truncate the recorded trajectory."""
    bowl = ph.QuadraticSurface(0.0, 0.0, 0.2, 0.0, 0.2)  # steep bowl: ball oscillates
    r = ph.simulate_putt(bowl, (3.0, 0.0), (0.0, 0.0), 0.0, 0.0, A10, t_max=40.0, dt=0.01)
    assert r.t[-1] == pytest.approx(r.t_end)
    assert np.allclose(r.xy[-1], r.stop_xy)
