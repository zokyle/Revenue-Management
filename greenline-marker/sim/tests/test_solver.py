"""Aim solver: closed-form checks, convergence, failure statuses, batch API."""

import math
import time

import numpy as np
import pytest

from greenline_sim import physics as ph

A10 = ph.stimp_to_decel(10.0)
KF = ph.ROLL_FACTOR * ph.G


def _check_solution(surf, start, hole, a_r, grain, past, sol, tol=3e-5):
    """Re-simulate the solved putt: it must go through the hole centre at the
    target pace (pace tolerance expressed as flat roll-out distance)."""
    r = ph.simulate_putt(surf, start, hole, sol.phi, sol.v0, a_r, grain)
    if r.crossed_hole_line:
        assert abs(r.lateral_at_line) < tol
        assert abs(r.speed_at_line**2 - sol.v_hole_target**2) / (2 * a_r) < tol
    else:  # dying putt that stops a hair short of the hole line
        assert past == 0.0 or sol.v_hole_target < 0.02
        assert r.delta < tol
    assert r.delta < tol
    return r


# --------------------------------------------------------------------------
# closed-form checks
# --------------------------------------------------------------------------


def test_flat_putt_is_straight_with_exact_pace():
    for dist in (1.5, 4.0, 12.0):
        sol = ph.solve_aim(ph.PlaneSurface(0, 0), (0, 0), (dist, 0), A10, past=0.30)
        assert sol.ok and sol.status == ph.SolveStatus.OK
        assert sol.phi == pytest.approx(0.0, abs=1e-9)
        assert sol.v0 == pytest.approx(math.sqrt(2 * A10 * (dist + 0.30)), rel=1e-5)
        assert sol.plays_like == pytest.approx(dist + 0.30, abs=2e-5)
        assert sol.aim_offset == pytest.approx(0.0, abs=1e-8)
        assert sol.v_hole == pytest.approx(sol.v_hole_target, abs=1e-4)
        assert sol.distance == dist


@pytest.mark.parametrize("stimp", [8.0, 10.0, 12.5])
@pytest.mark.parametrize("slope", [0.005, 0.01, 0.02])
def test_closed_form_planar_break_dying_putt(stimp, slope):
    """Pure cross slope, putt dying at the hole: phi ~= (5/14) G s / a_r,
    independent of distance (first order in phi)."""
    a_r = ph.stimp_to_decel(stimp)
    theory = (5.0 / 14.0) * ph.G * slope / a_r
    assert ph.planar_break_angle(slope, a_r) == pytest.approx(theory, rel=1e-14)
    surf = ph.PlaneSurface(0.0, slope)  # ground rises to the left -> aim left
    phis = []
    for dist in (2.0, 4.0, 8.0):
        sol = ph.solve_aim(surf, (0, 0), (dist, 0), a_r, past=0.0, tol_miss=1e-9)
        assert sol.ok
        r = ph.simulate_putt(surf, (0, 0), (dist, 0), sol.phi, sol.v0, a_r)
        assert r.status == ph.RollStatus.STOPPED
        assert r.stop_distance < 5e-5  # the ball really dies at the hole
        phis.append(sol.phi)
    phis = np.array(phis)
    # independent of distance (to within the solver's pace tolerance)
    assert np.ptp(phis) < 1e-4 * phis.mean()
    # matches the small-slope formula up to the O(phi^2) term it neglects:
    # measured phi / theory - 1 = +1.17 ... 1.24 * theory^2  (0.08 % ... 3.1 %)
    rel = phis.mean() / theory - 1.0
    assert 1.0 * theory**2 < rel < 1.4 * theory**2
    assert rel < 0.035
    # mirror: slope falling to the left -> same angle to the right
    sol = ph.solve_aim(ph.PlaneSurface(0.0, -slope), (0, 0), (4.0, 0), a_r, past=0.0)
    assert sol.phi == pytest.approx(-phis[1], rel=1e-4)


def test_closed_form_reference_point_10ft_one_percent():
    """10 ft putt, 1 % cross slope, Stimp 10, 0.43 m past -> ~0.14 m of aim."""
    dist = 10 * ph.FT
    sol = ph.solve_aim(ph.PlaneSurface(0.0, 0.01), (0, 0), (dist, 0), A10, past=0.43)
    assert sol.ok
    assert sol.aim_offset == pytest.approx(0.14, abs=0.005)
    theory = ph.planar_break_angle_paced(0.01, A10, dist, 0.43)
    assert sol.phi == pytest.approx(theory, rel=0.01)
    assert sol.aim_offset_cups == pytest.approx(sol.aim_offset / 0.10795, rel=1e-12)


def test_paced_planar_break_formula_over_a_range():
    for slope, dist, past in ((0.005, 3.0, 0.3), (0.01, 6.0, 0.15), (0.015, 9.0, 0.45), (0.01, 1.5, 0.3)):
        sol = ph.solve_aim(ph.PlaneSurface(0.0, slope), (0, 0), (dist, 0), A10, past=past)
        assert sol.ok
        assert sol.phi == pytest.approx(ph.planar_break_angle_paced(slope, A10, dist, past), rel=0.02)
    # firmer pace -> less break
    soft = ph.solve_aim(ph.PlaneSurface(0.0, 0.01), (0, 0), (4, 0), A10, past=0.1)
    firm = ph.solve_aim(ph.PlaneSurface(0.0, 0.01), (0, 0), (4, 0), A10, past=0.6)
    assert 0 < firm.phi < soft.phi
    assert ph.planar_break_angle_paced(0.01, A10, 4.0, 0.0) == pytest.approx(ph.planar_break_angle(0.01, A10))


@pytest.mark.parametrize("slope", [-0.03, -0.015, 0.015, 0.03])
def test_uphill_downhill_pace(slope):
    """Straight up/down the fall line: no break, launch energy from the
    energy balance v0^2 = v_h^2 + 2 D (a_r + (5/7) G s)."""
    dist, past = 5.0, 0.30
    sol = ph.solve_aim(ph.PlaneSurface(slope, 0.0), (0, 0), (dist, 0), A10, past=past)
    flat = ph.solve_aim(ph.PlaneSurface(0.0, 0.0), (0, 0), (dist, 0), A10, past=past)
    assert sol.ok
    assert sol.phi == pytest.approx(0.0, abs=1e-8)
    v0_theory = math.sqrt(2 * A10 * past + 2 * dist * (A10 + KF * slope))
    assert sol.v0 == pytest.approx(v0_theory, rel=1e-5)
    if slope > 0:
        assert sol.v0 > flat.v0 and sol.plays_like > dist + past
    else:
        assert sol.v0 < flat.v0 and sol.plays_like < dist + past


def test_grain_moves_aim_like_equivalent_slope():
    kappa = 0.10
    s_eq = ph.grain_equivalent_slope(kappa, A10)
    # grain pushing to the right (-y) == ground falling to the right == rising to the left
    with_grain = ph.solve_aim(ph.PlaneSurface(0, 0), (0, 0), (5, 0), A10, ph.Grain(kappa, -math.pi / 2))
    tilted = ph.solve_aim(ph.PlaneSurface(0.0, s_eq), (0, 0), (5, 0), A10, None)
    assert with_grain.ok and tilted.ok
    assert with_grain.phi > 0
    assert with_grain.phi == pytest.approx(tilted.phi, abs=1e-6)
    assert with_grain.v0 == pytest.approx(tilted.v0, abs=1e-6)


def test_mirror_symmetry_of_solution():
    a, b, c, d, e = 0.01, 0.018, 0.003, -0.002, 0.004
    s1 = ph.solve_aim(ph.QuadraticSurface(a, b, c, d, e), (0, 0), (6, 0), A10, ph.Grain(0.05, 1.0))
    s2 = ph.solve_aim(ph.QuadraticSurface(a, -b, c, -d, e), (0, 0), (6, 0), A10, ph.Grain(0.05, -1.0))
    assert s1.ok and s2.ok
    assert s1.phi == pytest.approx(-s2.phi, abs=1e-6)
    assert s1.v0 == pytest.approx(s2.v0, abs=1e-6)


# --------------------------------------------------------------------------
# convergence over random surfaces
# --------------------------------------------------------------------------


def _random_case(rng, max_slope, curv):
    dist = rng.uniform(1.0, 12.0)
    slope = rng.uniform(0.0, max_slope)
    az = rng.uniform(0.0, 2 * np.pi)
    c, d, e = rng.normal(0.0, curv, 3) if curv > 0 else (0.0, 0.0, 0.0)
    surf = ph.QuadraticSurface(slope * np.cos(az), slope * np.sin(az), c, d, e)
    a_r = ph.stimp_to_decel(rng.uniform(8.0, 13.0))
    grain = ph.Grain(rng.uniform(0.0, 0.15), rng.uniform(0.0, 2 * np.pi))
    past = float(rng.choice([0.15, 0.30, 0.45]))
    return surf, dist, a_r, grain, past


def test_solver_converges_on_random_planes():
    """Planes up to 3.5 % with grain: every case must solve."""
    rng = np.random.default_rng(11)
    rolls = []
    for _ in range(300):
        surf, dist, a_r, grain, past = _random_case(rng, 0.035, 0.0)
        # stay below the slope at which a ball cannot be stopped at all
        assume = (0.035 + ph.grain_equivalent_slope(grain.kappa, a_r)) < 0.95 * ph.critical_slope(a_r)
        if not assume:
            continue
        sol = ph.solve_aim(surf, (0, 0), (dist, 0), a_r, grain, past)
        assert sol.ok, (surf, dist, a_r, grain, past, sol)
        _check_solution(surf, (0, 0), (dist, 0), a_r, grain, past, sol)
        rolls.append(sol.n_rolls)
    assert len(rolls) > 200
    assert np.median(rolls) <= 12 and np.max(rolls) <= 120


def test_solver_converges_on_random_quadratics():
    """Realistic patches (slope <= 3 %, curvature sigma 0.002 1/m): at least
    99 % solve, every reported OK is a true solution, and every failure
    carries an explicit non-OK status."""
    rng = np.random.default_rng(12)
    n = 400
    n_ok = 0
    rolls = []
    for _ in range(n):
        surf, dist, a_r, grain, past = _random_case(rng, 0.03, 0.002)
        sol = ph.solve_aim(surf, (0, 0), (dist, 0), a_r, grain, past)
        assert math.isfinite(sol.phi) and math.isfinite(sol.v0)
        if sol.ok:
            n_ok += 1
            rolls.append(sol.n_rolls)
            _check_solution(surf, (0, 0), (dist, 0), a_r, grain, past, sol)
        else:
            assert sol.status != ph.SolveStatus.OK and not sol.ok
            assert sol.n_rolls <= ph.DEFAULT_MAX_ROLLS + 120
    assert n_ok >= 0.99 * n
    assert np.median(rolls) <= 12


def test_tight_tolerances_converge_to_the_same_solution():
    """With tol_miss = tol_pace = 1e-9 m (as used for exported reference
    vectors) the solver still converges - a tight tolerance must not be
    mistaken for a discontinuity - and the default-tolerance solution lies
    within 5e-5 m (lateral, at the hole) of the tight one."""
    rng = np.random.default_rng(31)
    n_ok = 0
    for i in range(120):
        surf, dist, a_r, grain, past = _random_case(rng, 0.03, 0.002 if i % 2 else 0.0)
        loose = ph.solve_aim(surf, (0, 0), (dist, 0), a_r, grain, past)
        tight = ph.solve_aim(surf, (0, 0), (dist, 0), a_r, grain, past, tol_miss=1e-9, tol_pace=1e-9)
        assert tight.status == loose.status
        if not tight.ok:
            continue
        n_ok += 1
        r = ph.simulate_putt(surf, (0, 0), (dist, 0), tight.phi, tight.v0, a_r, grain)
        assert abs(r.lateral_at_line) < 5e-9
        assert abs(r.speed_at_line**2 - tight.v_hole_target**2) / (2 * a_r) < 5e-9
        assert abs(tight.phi - loose.phi) * dist < 5e-5
        assert tight.v0 == pytest.approx(loose.v0, rel=2e-5)
        assert tight.n_rolls <= 80
    assert n_ok >= 115


def test_ok_solutions_are_always_true_solutions_even_on_wild_patches():
    """Extreme patches (4 % slope, curvature sigma 0.004 1/m over up to 12 m,
    i.e. local slopes beyond the critical slope): failures are allowed but
    must be flagged; anything reported usable must pass through the hole."""
    rng = np.random.default_rng(13)
    counts = {}
    for _ in range(300):
        surf, dist, a_r, grain, past = _random_case(rng, 0.04, 0.004)
        sol = ph.solve_aim(surf, (0, 0), (dist, 0), a_r, grain, past)
        counts[sol.status.name] = counts.get(sol.status.name, 0) + 1
        if sol.ok:
            _check_solution(surf, (0, 0), (dist, 0), a_r, grain, past, sol)
        elif sol.status == ph.SolveStatus.PACE_LIMITED:
            r = ph.simulate_putt(surf, (0, 0), (dist, 0), sol.phi, sol.v0, a_r, grain)
            assert r.crossed_hole_line and abs(r.lateral_at_line) < 3e-5
            assert r.speed_at_line > sol.v_hole_target  # faster than asked, as reported
            assert r.speed_at_line == pytest.approx(sol.v_hole, abs=1e-3)
    assert counts.get("OK", 0) >= 0.85 * 300


def test_solver_general_start_and_hole_positions_on_grid_surface():
    quad = ph.QuadraticSurface(0.012, -0.008, 0.002, 0.001, -0.002)
    grid = ph.GridSurface.from_function(quad.z, (-15.0, 15.0), (-15.0, 15.0), 0.5)
    rng = np.random.default_rng(14)
    for _ in range(25):
        start = rng.uniform(-6, 6, 2)
        ang = rng.uniform(0, 2 * np.pi)
        dist = rng.uniform(1.5, 8.0)
        hole = start + dist * np.array([np.cos(ang), np.sin(ang)])
        grain = ph.Grain(0.05, rng.uniform(0, 2 * np.pi))
        s_grid = ph.solve_aim(grid, start, hole, A10, grain)
        s_quad = ph.solve_aim(quad, start, hole, A10, grain)
        assert s_grid.ok and s_quad.ok
        assert s_grid.phi == pytest.approx(s_quad.phi, abs=2e-5)
        assert s_grid.v0 == pytest.approx(s_quad.v0, abs=2e-5)
        _check_solution(grid, start, hole, A10, grain, 0.30, s_grid)


def test_solver_double_break():
    """S-shaped putt: the cross slope reverses half way."""
    surf = ph.QuadraticSurface(0.0, 0.02, 0.0, -0.005, 0.0)  # dz/dy = 0.02 - 0.005 x
    sol = ph.solve_aim(surf, (0, 0), (8, 0), A10)
    assert sol.ok
    r = _check_solution(surf, (0, 0), (8, 0), A10, None, 0.30, sol)
    y = ph.world_to_putt(r.xy, (0, 0), (8, 0))[:, 1]
    assert y.max() > 0.01 and y.min() < -0.001  # path lies on both sides of the line


# --------------------------------------------------------------------------
# failure statuses (no garbage)
# --------------------------------------------------------------------------


def test_steep_downhill_reports_pace_limited():
    """Straight down a slope steeper than critical: any putt that gets going
    arrives too fast; the solver must say so."""
    slope = -1.3 * ph.critical_slope(A10)
    sol = ph.solve_aim(ph.PlaneSurface(slope, 0.0), (0, 0), (4, 0), A10, past=0.30)
    assert sol.status == ph.SolveStatus.PACE_LIMITED
    assert not sol.ok and sol.usable
    assert sol.phi == pytest.approx(0.0, abs=1e-6)
    assert sol.v_hole > sol.v_hole_target
    assert sol.v0 < 0.05  # "just get it rolling"


def test_unreachable_hole_reports_unreachable():
    # needs ~2.9 m/s but the search is capped at 2 m/s
    sol = ph.solve_aim(ph.PlaneSurface(0, 0), (0, 0), (7, 0), A10, v_max=2.0)
    assert sol.status == ph.SolveStatus.UNREACHABLE
    assert not sol.ok and not sol.usable
    assert math.isfinite(sol.phi) and math.isfinite(sol.v0)


def test_invalid_geometry_reports_invalid():
    sol = ph.solve_aim(ph.PlaneSurface(0, 0), (1, 1), (1, 1), A10)
    assert sol.status == ph.SolveStatus.INVALID and not sol.ok
    with pytest.raises(ValueError):
        ph.solve_aim(ph.PlaneSurface(0, 0), (0, 0), (3, 0), -1.0)
    with pytest.raises(ValueError):
        ph.solve_aim(ph.PlaneSurface(0, 0), (0, 0), (3, 0), A10, past=-0.1)


def test_hole_on_unholdable_side_slope_is_not_reported_ok():
    """Hole sitting on a cross slope steeper than critical: a ball arriving at
    the target pace cannot be threaded through; whatever happens, the solver
    must not claim success unless the re-simulated putt really goes in line."""
    a_r = ph.stimp_to_decel(12.0)
    surf = ph.QuadraticSurface(-0.026, 0.029, 0.0001, 0.0044, -0.0029)
    grain = ph.Grain(0.035, 5.34)
    sol = ph.solve_aim(surf, (0, 0), (10.8, 0), a_r, grain, 0.45)
    assert sol.status in (
        ph.SolveStatus.NO_CONVERGENCE,
        ph.SolveStatus.NO_BRACKET,
        ph.SolveStatus.PACE_LIMITED,
        ph.SolveStatus.UNREACHABLE,
    )
    assert math.isfinite(sol.phi) and math.isfinite(sol.v0) and sol.v0 > 0
    assert sol.n_rolls <= ph.DEFAULT_MAX_ROLLS + 120
    # a small budget is honoured and reported as non-convergence
    sol2 = ph.solve_aim(surf, (0, 0), (10.8, 0), a_r, grain, 0.45, max_rolls=20)
    assert not sol2.ok


def test_dying_putt_that_must_curl_back_is_flagged_not_faked():
    """past = 0 on an uphill side slope: the putt that stops exactly in the
    hole has to pass above it and curl back.  The solver looks for the FIRST
    arrival at the hole line, so it either reports a real dying putt (OK) or
    PACE_LIMITED with the honest arrival speed - never a false 'OK'."""
    rng = np.random.default_rng(15)
    seen = set()
    for _ in range(120):
        slope = rng.uniform(0.01, 0.03)
        az = rng.uniform(0.0, 2 * np.pi)
        surf = ph.PlaneSurface(slope * np.cos(az), slope * np.sin(az))
        dist = rng.uniform(2.0, 9.0)
        sol = ph.solve_aim(surf, (0, 0), (dist, 0), A10, past=0.0)
        seen.add(sol.status)
        assert sol.usable
        r = ph.simulate_putt(surf, (0, 0), (dist, 0), sol.phi, sol.v0, A10)
        assert r.delta < 5e-5  # passes through the hole centre either way
        if sol.ok:
            assert r.stop_distance < 5e-4  # and really dies there
        else:
            assert sol.status == ph.SolveStatus.PACE_LIMITED
            assert r.speed_at_delta == pytest.approx(sol.v_hole, abs=2e-3)
            assert sol.v_hole < 0.5  # still a slow arrival
    assert ph.SolveStatus.OK in seen


# --------------------------------------------------------------------------
# batch API and speed
# --------------------------------------------------------------------------


def test_quadratic_batch_equals_scalar_solver():
    rng = np.random.default_rng(16)
    n = 60
    coeffs = np.column_stack(
        [rng.uniform(-0.02, 0.02, n), rng.uniform(-0.02, 0.02, n), *(rng.normal(0, 0.002, n) for _ in range(3))]
    )
    dist = rng.uniform(1.5, 12.0, n)
    a_r = ph.stimp_to_decel(rng.uniform(8, 12.5, n))
    grain = np.column_stack([rng.uniform(-0.08, 0.08, n), rng.uniform(-0.08, 0.08, n)])
    batch = ph.solve_aim_quadratic_batch(coeffs, dist, a_r, grain, 0.30)
    assert len(batch) == n and batch.ok.mean() > 0.95
    for i in range(n):
        one = ph.solve_aim(ph.QuadraticSurface(*coeffs[i]), (0, 0), (dist[i], 0), a_r[i], grain[i], 0.30)
        assert batch.status[i] == int(one.status)
        assert batch.phi[i] == one.phi and batch.v0[i] == one.v0
        assert batch.n_rolls[i] == one.n_rolls
        assert batch.aim_offset[i] == pytest.approx(one.aim_offset)
        assert batch.plays_like[i] == pytest.approx(one.plays_like)
    # scalar broadcasting
    b2 = ph.solve_aim_quadratic_batch(coeffs[0], dist[:5], A10)
    assert len(b2) == 5
    with pytest.raises(ValueError):
        ph.solve_aim_quadratic_batch(np.zeros((3, 4)), 3.0, A10)


def test_surface_batch_equals_scalar_solver():
    rng = np.random.default_rng(17)
    quad = ph.QuadraticSurface(0.012, -0.008, 0.002, 0.001, -0.002)
    grid = ph.GridSurface.from_function(quad.z, (-15.0, 15.0), (-15.0, 15.0), 0.5)
    n = 16
    start = rng.uniform(-5, 5, (n, 2))
    ang = rng.uniform(0, 2 * np.pi, n)
    dist = rng.uniform(1.5, 8.0, n)
    hole = start + dist[:, None] * np.column_stack([np.cos(ang), np.sin(ang)])
    grain = ph.Grain(0.06, 0.3)
    batch = ph.solve_aim_batch(grid, start, hole, A10, grain, 0.30)
    for i in range(n):
        one = ph.solve_aim(grid, start[i], hole[i], A10, grain, 0.30)
        assert batch.status[i] == int(one.status) and batch.phi[i] == one.phi and batch.v0[i] == one.v0
        assert batch.distance[i] == pytest.approx(dist[i])
    assert batch.usable.all()


@pytest.mark.skipif(not ph.HAVE_NUMBA, reason="speed target applies to the numba kernels")
def test_solver_speed_target():
    """Spec: << 50 ms per solve.  (Measured ~0.3 ms; the bound is loose so
    the test is not flaky on a loaded machine.)"""
    rng = np.random.default_rng(18)
    cases = [_random_case(rng, 0.03, 0.002) for _ in range(200)]
    ph.solve_aim(ph.PlaneSurface(0, 0.01), (0, 0), (3, 0), A10)  # compile
    t0 = time.perf_counter()
    for surf, dist, a_r, grain, past in cases:
        ph.solve_aim(surf, (0, 0), (dist, 0), a_r, grain, past)
    mean_ms = (time.perf_counter() - t0) / len(cases) * 1e3
    assert mean_ms < 10.0
