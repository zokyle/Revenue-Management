"""Surface height fields: analytic gradients, grid interpolation, consistency."""

import math

import numpy as np
import pytest
from scipy.interpolate import RectBivariateSpline

from greenline_sim import physics as ph

A10 = ph.stimp_to_decel(10.0)


def _fd_grad(surf, x, y, h=1e-5):
    gx = (np.asarray(surf.z(x + h, y)) - np.asarray(surf.z(x - h, y))) / (2 * h)
    gy = (np.asarray(surf.z(x, y + h)) - np.asarray(surf.z(x, y - h))) / (2 * h)
    return gx, gy


def test_plane_surface():
    s = ph.PlaneSurface(0.02, -0.01, z0=0.5)
    assert s.z(0.0, 0.0) == 0.5
    assert s.z(2.0, 3.0) == pytest.approx(0.5 + 0.04 - 0.03)
    assert s.grad(7.0, -3.0) == (0.02, -0.01)
    assert s.slope(1.0, 1.0) == pytest.approx(math.hypot(0.02, 0.01))
    # steepest descent points opposite to the gradient
    assert s.fall_line_azimuth(0.0, 0.0) == pytest.approx(math.atan2(0.01, -0.02))
    assert s.bounds == (-math.inf, math.inf, -math.inf, math.inf)
    assert isinstance(s.z(1.0, 2.0), float)


def test_quadratic_surface_values_and_gradient():
    rng = np.random.default_rng(0)
    s = ph.QuadraticSurface(0.01, -0.02, 0.004, 0.003, -0.005, z0=0.1)
    assert np.allclose(s.coeffs, [0.01, -0.02, 0.004, 0.003, -0.005])
    x = rng.uniform(-10, 10, 200)
    y = rng.uniform(-10, 10, 200)
    z = 0.1 + 0.01 * x - 0.02 * y + 0.5 * (0.004 * x**2 + 2 * 0.003 * x * y - 0.005 * y**2)
    assert np.allclose(s.z(x, y), z, atol=1e-14)
    gx, gy = s.grad(x, y)
    fx, fy = _fd_grad(s, x, y)
    assert np.allclose(gx, fx, atol=1e-9) and np.allclose(gy, fy, atol=1e-9)
    s2 = ph.QuadraticSurface.from_coeffs(s.coeffs, z0=0.1)
    assert np.array_equal(s2.z(x, y), s.z(x, y))
    with pytest.raises(ValueError):
        ph.QuadraticSurface.from_coeffs([1, 2, 3])
    # also reachable through the subclass, and always a full quadratic
    s3 = ph.PlaneSurface.from_coeffs(s.coeffs)
    assert type(s3) is ph.QuadraticSurface and np.array_equal(s3.coeffs, s.coeffs)
    # broadcasting
    assert np.asarray(s.z(x[:, None], y[None, :5])).shape == (200, 5)


def test_quadratic_surface_in_frame_is_the_same_surface():
    """in_frame(origin, angle) re-expresses the patch in a moved and rotated
    frame: heights and (rotated) gradients agree, and a putt solved in the
    putt frame equals the putt solved in the world frame."""
    rng = np.random.default_rng(21)
    s = ph.QuadraticSurface(0.012, -0.02, 0.004, 0.003, -0.005, z0=0.1)
    for _ in range(5):
        origin = rng.uniform(-5, 5, 2)
        ang = rng.uniform(-np.pi, np.pi)
        t = s.in_frame(origin, ang)
        ca, sa = math.cos(ang), math.sin(ang)
        u, v = rng.uniform(-8, 8, 100), rng.uniform(-8, 8, 100)
        wx, wy = origin[0] + ca * u - sa * v, origin[1] + sa * u + ca * v
        assert np.allclose(t.z(u, v), s.z(wx, wy), rtol=0, atol=1e-13)
        assert t.z0 == pytest.approx(s.z(*origin), abs=1e-15)
        gx, gy = s.grad(wx, wy)
        tu, tv = t.grad(u, v)
        assert np.allclose(tu, gx * ca + gy * sa, atol=1e-14)
        assert np.allclose(tv, -gx * sa + gy * ca, atol=1e-14)
        # curvature invariants
        assert t.c + t.e == pytest.approx(s.c + s.e, abs=1e-15)
        assert t.c * t.e - t.d**2 == pytest.approx(s.c * s.e - s.d**2, abs=1e-15)
        # identity and round trip
        back = t.in_frame((-(origin[0] * ca + origin[1] * sa), origin[0] * sa - origin[1] * ca), -ang)
        assert np.allclose(back.coeffs, s.coeffs, atol=1e-14) and back.z0 == pytest.approx(s.z0, abs=1e-14)
    assert np.array_equal(s.in_frame((0.0, 0.0), 0.0).coeffs, s.coeffs)
    # putt-frame patch: ball at the origin, hole at (D, 0)
    ball, hole = np.array([1.0, -2.0]), np.array([4.5, 1.0])
    bearing = math.atan2(hole[1] - ball[1], hole[0] - ball[0])
    dist = float(np.hypot(*(hole - ball)))
    grain = ph.Grain(0.07, 0.6)
    world = ph.solve_aim(s, ball, hole, A10, grain)
    putt = ph.solve_aim(s.in_frame(ball, bearing), (0.0, 0.0), (dist, 0.0), A10, grain.rotated(bearing))
    assert world.ok and putt.ok
    assert putt.phi == pytest.approx(world.phi, abs=2e-6)
    assert putt.v0 == pytest.approx(world.v0, abs=2e-6)
    plane = ph.PlaneSurface(0.02, 0.0).in_frame((3.0, 1.0), math.pi / 2)  # x' = world +y
    assert plane.a == pytest.approx(0.0, abs=1e-17) and plane.b == pytest.approx(-0.02)
    assert plane.z0 == pytest.approx(0.06) and plane.c == plane.d == plane.e == 0.0


def _random_grid(seed=1, n=41, spacing=0.25):
    rng = np.random.default_rng(seed)
    x = -5.0 + spacing * np.arange(n)
    y = -4.0 + spacing * np.arange(n + 6)
    heights = rng.normal(0.0, 0.01, size=(x.size, y.size))  # rough data: worst case
    return x, y, heights


def test_grid_surface_interpolates_nodes_exactly():
    x, y, heights = _random_grid()
    g = ph.GridSurface(x, y, heights)
    xx, yy = np.meshgrid(x, y, indexing="ij")
    assert np.allclose(g.z(xx, yy), heights, atol=1e-13)
    assert g.bounds == (x[0], x[-1], y[0], y[-1])
    assert isinstance(g.z(0.1, 0.2), float)


def test_grid_surface_gradient_matches_finite_differences():
    x, y, heights = _random_grid()
    g = ph.GridSurface(x, y, heights)
    rng = np.random.default_rng(2)
    px = rng.uniform(x[0] + 0.01, x[-1] - 0.01, 2000)
    py = rng.uniform(y[0] + 0.01, y[-1] - 0.01, 2000)
    gx, gy = g.grad(px, py)
    fx, fy = _fd_grad(g, px, py, h=1e-5)
    assert np.max(np.abs(gx - fx)) < 1e-7
    assert np.max(np.abs(gy - fy)) < 1e-7
    assert np.max(np.hypot(gx, gy)) > 0.01  # the test data really is rough


def test_grid_surface_is_c1_across_cells():
    """Height and gradient are continuous across node lines (C1; in fact C2)."""
    x, y, heights = _random_grid()
    g = ph.GridSurface(x, y, heights)
    rng = np.random.default_rng(3)
    eps = 1e-9
    # points straddling interior node lines in x and in y
    xi = x[rng.integers(2, x.size - 2, 300)]
    yv = rng.uniform(y[1], y[-2], 300)
    for lo, hi in (((xi - eps, yv), (xi + eps, yv)),):
        assert np.max(np.abs(np.asarray(g.z(*lo)) - np.asarray(g.z(*hi)))) < 1e-8
        g_lo = g.grad(*lo)
        g_hi = g.grad(*hi)
        assert np.max(np.abs(g_lo[0] - g_hi[0])) < 1e-6
        assert np.max(np.abs(g_lo[1] - g_hi[1])) < 1e-6
    yi = y[rng.integers(2, y.size - 2, 300)]
    xv = rng.uniform(x[1], x[-2], 300)
    g_lo = g.grad(xv, yi - eps)
    g_hi = g.grad(xv, yi + eps)
    assert np.max(np.abs(g_lo[0] - g_hi[0])) < 1e-6
    assert np.max(np.abs(g_lo[1] - g_hi[1])) < 1e-6


def test_grid_surface_reproduces_planes_and_quadratics_to_the_edge():
    quad = ph.QuadraticSurface(0.02, -0.015, 0.004, 0.002, -0.003, z0=0.3)
    g = ph.GridSurface.from_function(quad.z, (-8.0, 8.0), (-6.0, 6.0), 0.5)
    rng = np.random.default_rng(4)
    px = rng.uniform(-8.0, 8.0, 3000)  # includes the cells next to the boundary
    py = rng.uniform(-6.0, 6.0, 3000)
    assert np.max(np.abs(g.z(px, py) - quad.z(px, py))) < 1e-7
    gx, gy = g.grad(px, py)
    qx, qy = quad.grad(px, py)
    assert np.max(np.abs(gx - qx)) < 1e-6
    assert np.max(np.abs(gy - qy)) < 1e-6
    plane = ph.PlaneSurface(0.03, -0.01)
    gp = ph.GridSurface.from_function(plane.z, (-8.0, 8.0), (-6.0, 6.0), 0.5)
    gx, gy = gp.grad(px, py)
    assert np.max(np.abs(gx - 0.03)) < 1e-8 and np.max(np.abs(gy + 0.01)) < 1e-8


def test_grid_surface_matches_smooth_function_and_scipy_spline():
    def f(x, y):
        return 0.05 * np.sin(0.5 * x) * np.cos(0.4 * y) + 0.01 * x - 0.004 * y

    def fgrad(x, y):
        return (
            0.025 * np.cos(0.5 * x) * np.cos(0.4 * y) + 0.01,
            -0.02 * np.sin(0.5 * x) * np.sin(0.4 * y) - 0.004,
        )

    g = ph.GridSurface.from_function(f, (-12.0, 12.0), (-12.0, 12.0), 0.5)
    rbs = RectBivariateSpline(g.x, g.y, g.heights, kx=3, ky=3, s=0)
    rng = np.random.default_rng(5)
    px = rng.uniform(-10.0, 10.0, 2000)
    py = rng.uniform(-10.0, 10.0, 2000)
    assert np.max(np.abs(g.z(px, py) - f(px, py))) < 2e-6
    gx, gy = g.grad(px, py)
    ax, ay = fgrad(px, py)
    assert np.max(np.abs(gx - ax)) < 1e-5 and np.max(np.abs(gy - ay)) < 1e-5
    # agrees with scipy's interpolating bicubic spline away from the boundary
    assert np.max(np.abs(g.z(px, py) - rbs.ev(px, py))) < 2e-6
    assert np.max(np.abs(gx - rbs.ev(px, py, dx=1))) < 1e-5
    assert np.max(np.abs(gy - rbs.ev(px, py, dy=1))) < 1e-5


def test_grid_kernel_matches_numpy_evaluation():
    """The scalar (firmware-style) kernel and the vectorised numpy path are
    the same function."""
    x, y, heights = _random_grid(seed=7)
    g = ph.GridSurface(x, y, heights)
    kind, p, c = g.kernel_spec()
    rng = np.random.default_rng(8)
    px = rng.uniform(x[0] - 1.0, x[-1] + 1.0, 500)  # also outside the grid
    py = rng.uniform(y[0] - 1.0, y[-1] + 1.0, 500)
    z_np = g._z_numpy(px, py)
    gx_np, gy_np = g._grad_numpy(px, py)
    # the public (possibly compiled) path is the same function too
    assert np.allclose(g.z(px, py), z_np, rtol=0, atol=1e-13)
    assert np.allclose(g.grad(px, py)[0], gx_np, rtol=0, atol=1e-12)
    assert np.allclose(g.grad(px, py)[1], gy_np, rtol=0, atol=1e-12)
    assert np.asarray(g.z(px.reshape(50, 10), py.reshape(50, 10))).shape == (50, 10)
    assert np.asarray(g.z(px[:7, None], py[None, :3])).shape == (7, 3)
    for i in range(px.size):
        assert ph._surf_z(kind, p, c, px[i], py[i]) == pytest.approx(z_np[i], abs=1e-13)
        kx, ky = ph._surf_grad(kind, p, c, px[i], py[i])
        assert kx == pytest.approx(gx_np[i], abs=1e-12)
        assert ky == pytest.approx(gy_np[i], abs=1e-12)


def test_grid_surface_outside_domain_is_constant_extension():
    quad = ph.QuadraticSurface(0.02, -0.015, 0.004, 0.002, -0.003)
    g = ph.GridSurface.from_function(quad.z, (-4.0, 4.0), (-3.0, 3.0), 0.5)
    assert g.z(6.0, 1.0) == pytest.approx(g.z(4.0, 1.0))
    assert g.z(-9.0, -7.0) == pytest.approx(g.z(-4.0, -3.0))
    gx, gy = g.grad(6.0, 1.0)
    assert gx == 0.0 and gy == pytest.approx(g.grad(4.0, 1.0)[1])
    gx, gy = g.grad(1.0, -5.0)
    assert gy == 0.0 and gx == pytest.approx(g.grad(1.0, -3.0)[0])


def test_grid_surface_validation():
    x = np.linspace(0, 1, 5)
    with pytest.raises(ValueError):
        ph.GridSurface(x, x, np.zeros((5, 4)))
    with pytest.raises(ValueError):
        ph.GridSurface(np.array([0.0, 0.1, 0.3, 0.6, 1.0]), x, np.zeros((5, 5)))
    with pytest.raises(ValueError):
        ph.GridSurface(x[::-1], x, np.zeros((5, 5)))
    with pytest.raises(ValueError):
        ph.GridSurface(x[:3], x, np.zeros((3, 5)))
    bad = np.zeros((5, 5))
    bad[2, 2] = np.nan
    with pytest.raises(ValueError):
        ph.GridSurface(x, x, bad)


def test_roll_on_grid_equals_roll_on_analytic_surface():
    quad = ph.QuadraticSurface(0.012, 0.02, 0.004, -0.003, 0.005)
    grid = ph.GridSurface.from_function(quad.z, (-6.0, 14.0), (-8.0, 8.0), 0.5)
    grain = ph.Grain(0.06, 2.0)
    crossings = 0
    for phi, v0 in ((0.12, 3.0), (-0.05, 2.2), (0.3, 3.6), (0.05, 2.9)):
        a = ph.simulate_putt(quad, (0, 0), (6, 0), phi, v0, A10, grain)
        b = ph.simulate_putt(grid, (0, 0), (6, 0), phi, v0, A10, grain)
        assert a.status == b.status == ph.RollStatus.STOPPED
        assert np.hypot(*(a.stop_xy - b.stop_xy)) < 2e-6
        assert a.crossed_hole_line == b.crossed_hole_line
        if a.crossed_hole_line:
            crossings += 1
            assert a.lateral_at_line == pytest.approx(b.lateral_at_line, abs=1e-6)
        assert a.delta == pytest.approx(b.delta, abs=1e-6)
    assert crossings >= 2


def test_ball_leaving_the_grid_is_out_of_bounds():
    plane = ph.PlaneSurface(0.0, 0.0)
    grid = ph.GridSurface.from_function(plane.z, (-2.0, 2.0), (-2.0, 2.0), 0.5)
    r = ph.simulate_putt(grid, (0, 0), (1, 0), 0.0, 3.0, A10)
    assert r.status == ph.RollStatus.OUT_OF_BOUNDS
    assert r.stop_xy[0] > 2.0
    assert not r.captured  # crossed the hole at 2.8 m/s
