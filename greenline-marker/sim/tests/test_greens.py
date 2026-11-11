"""Synthetic greens: reproducibility, geometry, slope statistics, placement."""

import dataclasses
import math

import numpy as np
import pytest

from greenline_sim import greens as gr
from greenline_sim import physics as ph

DISTANCES = [1.5, 3.0, 4.5, 6.0, 9.0, 12.0]


def _inside_nodes(green):
    xx, yy = np.meshgrid(green.surface.x, green.surface.y, indexing="ij")
    return xx, yy, np.asarray(green.on_green(xx, yy))


# --------------------------------------------------------------------------
# reproducibility
# --------------------------------------------------------------------------


@pytest.mark.parametrize("cls", gr.GREEN_CLASSES)
def test_green_is_reproducible_from_seed(cls):
    a = gr.make_green(cls, 42)
    b = gr.make_green(cls, 42)
    c = gr.make_green(cls, 43)
    assert np.array_equal(a.surface.heights, b.surface.heights)
    assert a.stimp_ft == b.stimp_ft and a.grain == b.grain
    assert a.edge_r0 == b.edge_r0 and np.array_equal(a.edge_amp, b.edge_amp)
    assert a.seed == 42 and a.green_class == cls
    assert not np.array_equal(a.surface.heights, c.surface.heights)
    assert a.z(0.0, 0.0) == pytest.approx(0.0, abs=1e-12)  # datum at the centre


def test_classes_differ_for_the_same_seed():
    heights = [gr.make_green(cls, 7).surface.heights for cls in gr.GREEN_CLASSES]
    for i in range(len(heights)):
        for j in range(i + 1, len(heights)):
            assert not np.array_equal(heights[i], heights[j])


def test_scenario_is_reproducible_and_reuses_the_green():
    s1 = gr.make_scenario("undulating", 6.0, 11)
    s2 = gr.make_scenario("undulating", 6.0, 11)
    assert np.array_equal(s1.hole_xy, s2.hole_xy) and np.array_equal(s1.ball_xy, s2.ball_xy)
    assert np.array_equal(s1.green.surface.heights, s2.green.surface.heights)
    # same seed, other distance: same green, different putt
    s3 = gr.make_scenario("undulating", 9.0, 11)
    assert np.array_equal(s1.green.surface.heights, s3.green.surface.heights)
    assert not np.array_equal(s1.hole_xy, s3.hole_xy)
    # a pre-built green gives the identical scenario
    s4 = gr.make_scenario("undulating", 6.0, 11, green=gr.make_green("undulating", 11))
    assert np.array_equal(s1.hole_xy, s4.hole_xy) and np.array_equal(s1.ball_xy, s4.ball_xy)
    with pytest.raises(ValueError):
        gr.make_scenario("gentle", 6.0, 11, green=s1.green)


def test_generator_seed_and_bad_inputs():
    g = gr.make_green("gentle", np.random.default_rng(3))
    assert g.seed is None
    with pytest.raises(ValueError):
        gr.make_green("links", 1)
    with pytest.raises(ValueError):
        gr.make_green("gentle", -1)
    with pytest.raises(TypeError):
        gr.make_green("gentle", 1.5)


# --------------------------------------------------------------------------
# geometry: boundary, collar, rough
# --------------------------------------------------------------------------


def test_boundary_is_9_to_16_m_from_the_centre():
    theta = np.linspace(0.0, 2 * np.pi, 721)
    for cls in gr.GREEN_CLASSES:
        for seed in range(40):
            g = gr.make_green(cls, seed)
            r = g.edge_radius(theta)
            assert r.min() >= 9.0 and r.max() <= 16.0
            assert g.edge_radius_min <= r.min() + 1e-12 and g.edge_radius_max >= r.max() - 1e-12
            b = g.surface.bounds
            # the height grid extends well beyond green + collar on every side
            assert min(-b[0], b[1], -b[2], b[3]) >= r.max() + g.collar_width + 2.0


def test_regions_and_canopy_steps():
    g = gr.make_green("gentle", 5)
    assert gr.COLLAR_STEP == 0.008 and gr.ROUGH_STEP == 0.040
    for theta in np.linspace(0.0, 2 * np.pi, 13):
        r_edge = g.edge_radius(theta)
        ux, uy = math.cos(theta), math.sin(theta)

        def at(r):
            return r * ux, r * uy

        assert g.region(*at(r_edge - 0.05)) == gr.REGION_GREEN
        assert g.region(*at(r_edge + 0.05)) == gr.REGION_COLLAR
        assert g.region(*at(r_edge + g.collar_width - 0.05)) == gr.REGION_COLLAR
        assert g.region(*at(r_edge + g.collar_width + 0.05)) == gr.REGION_ROUGH
        assert g.canopy_step(*at(r_edge - 0.05)) == 0.0
        assert g.canopy_step(*at(r_edge + 0.05)) == 0.008
        assert g.canopy_step(*at(r_edge + g.collar_width + 0.05)) == 0.040
        assert g.radial_margin(*at(r_edge - 1.0)) == pytest.approx(1.0)
        x, y = at(r_edge + 3.0)
        assert g.canopy_z(x, y) == pytest.approx(g.z(x, y) + 0.040)
    assert g.on_green(0.0, 0.0) and g.region(0.0, 0.0) == gr.REGION_GREEN
    assert 0.8 <= g.collar_width <= 1.5
    # vectorised
    xs = np.linspace(-20, 20, 81)
    reg = g.region(xs, 0 * xs)
    assert set(np.unique(reg)) == {0, 1, 2}
    assert np.array_equal(g.canopy_step(xs, 0 * xs) > 0, reg > 0)
    # the canopy does not change the rolling surface: it is smooth across the edge
    r_edge = g.edge_radius(0.0)
    assert abs(g.z(r_edge + 1e-6, 0.0) - g.z(r_edge - 1e-6, 0.0)) < 1e-6


# --------------------------------------------------------------------------
# shape statistics
# --------------------------------------------------------------------------


@pytest.mark.parametrize("cls", ["planar", "gentle", "undulating"])
def test_overall_tilt_and_undulation_match_the_drawn_values(cls):
    lo, hi = gr.CLASS_PARAMS[cls].tilt_range
    u_lo, u_hi = gr.CLASS_PARAMS[cls].undulation_slope_rms_range
    l_lo, l_hi = gr.CLASS_PARAMS[cls].corr_length_range
    n_checked = 0
    for seed in range(40):
        g = gr.make_green(cls, seed)
        tilt_mag = float(np.hypot(*g.tilt))
        assert lo <= tilt_mag <= hi
        assert 0.005 <= tilt_mag <= 0.03  # spec: roughly 0.5-3 %
        assert u_lo <= g.undulation_slope_rms <= u_hi
        assert l_lo <= g.corr_length <= l_hi and 4.0 <= g.corr_length <= 8.0
        if g.ridge is not None:
            continue  # a ridge adds its own tilt/slope
        n_checked += 1
        xx, yy, inside = _inside_nodes(g)
        # best-fit plane over the putting surface == the drawn overall tilt
        design = np.column_stack([np.ones(inside.sum()), xx[inside], yy[inside]])
        coef, *_ = np.linalg.lstsq(design, g.surface.heights[inside], rcond=None)
        assert coef[1] == pytest.approx(g.tilt[0], abs=1e-9)
        assert coef[2] == pytest.approx(g.tilt[1], abs=1e-9)
        # RMS slope of what is left == the drawn undulation slope
        gx, gy = g.grad(xx[inside], yy[inside])
        rms = math.sqrt(np.mean((gx - g.tilt[0]) ** 2 + (gy - g.tilt[1]) ** 2))
        assert rms == pytest.approx(g.undulation_slope_rms, rel=0.01, abs=2e-6)
    assert n_checked >= 20


def test_classes_are_ordered_by_difficulty():
    def median_rms_slope_about_tilt(cls):
        vals = []
        for seed in range(30):
            g = gr.make_green(cls, seed)
            xx, yy, inside = _inside_nodes(g)
            gx, gy = g.grad(xx[inside], yy[inside])
            vals.append(math.sqrt(np.mean((gx - g.tilt[0]) ** 2 + (gy - g.tilt[1]) ** 2)))
        return float(np.median(vals))

    planar, gentle, undulating, tiered = (median_rms_slope_about_tilt(c) for c in gr.GREEN_CLASSES)
    assert planar < 0.002 < gentle < 0.0095 < undulating
    assert tiered > gentle


def test_tiered_greens_have_a_tier_and_others_do_not():
    for seed in range(20):
        g = gr.make_green("tiered", seed)
        t = g.tier
        assert t is not None
        assert 0.20 <= t["height"] <= 0.45 and 0.04 <= t["max_slope"] <= 0.07
        assert t["width"] == pytest.approx(t["height"] / (2 * t["max_slope"]))
        # crossing the tier line the surface climbs by about the tier height
        ca, sa = math.cos(t["azimuth"]), math.sin(t["azimuth"])
        s = np.array([-3.0 * t["width"], 3.0 * t["width"]]) + t["offset"]
        step = np.diff(g.z(s * ca, s * sa))[0] - np.diff(s)[0] * (g.tilt[0] * ca + g.tilt[1] * sa)
        assert step == pytest.approx(t["height"] * math.tanh(3.0), abs=0.12)
        assert step > 0.1
        for cls in ("planar", "gentle", "undulating"):
            assert gr.make_green(cls, seed).tier is None
    ridges = [gr.make_green("undulating", s).ridge is not None for s in range(100)]
    assert 0.15 < np.mean(ridges) < 0.45
    assert all(gr.make_green("planar", s).ridge is None for s in range(20))


def test_speed_and_grain_ranges():
    stimps, kappas = [], []
    for cls in gr.GREEN_CLASSES:
        for seed in range(60):
            g = gr.make_green(cls, seed)
            stimps.append(g.stimp_ft)
            kappas.append(g.grain.kappa)
            assert g.a_r == pytest.approx(ph.stimp_to_decel(g.stimp_ft))
            assert np.allclose(g.grain_vector, g.grain.vector)
            assert -math.pi <= g.grain.azimuth <= math.pi
    stimps, kappas = np.array(stimps), np.array(kappas)
    assert stimps.min() >= 7.5 and stimps.max() <= 13.0
    assert 9.5 < np.median(stimps) < 10.5
    assert kappas.min() >= 0.0 and kappas.max() <= 0.15
    assert 0.2 < np.mean(kappas >= 0.05) < 0.5  # share of strongly grained greens


def test_params_override_gives_an_exact_plane_and_optional_surrounds():
    base = gr.CLASS_PARAMS["planar"]
    prm = dataclasses.replace(base, tilt_range=(0.02, 0.02), undulation_slope_rms_range=(0.0, 0.0))
    g = gr.make_green("planar", 3, prm)
    rng = np.random.default_rng(0)
    px, py = rng.uniform(-20, 20, 500), rng.uniform(-20, 20, 500)
    assert np.allclose(g.z(px, py), g.tilt[0] * px + g.tilt[1] * py, atol=1e-8)
    assert np.allclose(g.slope(px, py), 0.02, atol=1e-8)
    # surrounds falling away: putting surface and collar unchanged, rough lower
    g2 = gr.make_green("planar", 3, dataclasses.replace(prm, surround_slope_range=(-0.05, -0.05)))
    assert g2.surround_slope == -0.05 and g.surround_slope == 0.0
    xx, yy, inside = _inside_nodes(g)
    assert np.allclose(g2.surface.heights[inside], g.surface.heights[inside], atol=1e-12)
    assert g2.stimp_ft == g.stimp_ft and g2.grain == g.grain
    far = g.edge_radius(0.0) + g.collar_width + 5.0
    assert g2.z(far, 0.0) < g.z(far, 0.0) - 0.15


# --------------------------------------------------------------------------
# hole and ball placement
# --------------------------------------------------------------------------


def test_scenarios_exist_for_all_classes_and_distances_and_are_legal():
    hole_slopes = {cls: [] for cls in gr.GREEN_CLASSES}
    ring = np.arange(8) * (math.pi / 4)
    for cls in gr.GREEN_CLASSES:
        for seed in range(40):
            g = gr.make_green(cls, seed)
            for dist in DISTANCES:
                sc = gr.make_scenario(cls, dist, seed, green=g)  # must not raise
                hole, ball = sc.hole_xy, sc.ball_xy
                assert sc.distance == dist
                assert np.hypot(*(hole - ball)) == pytest.approx(dist, abs=1e-12)
                assert sc.bearing == pytest.approx(math.atan2(hole[1] - ball[1], hole[0] - ball[0]))
                assert sc.dz == pytest.approx(g.z(*hole) - g.z(*ball))
                # hole: legal location
                s_hole = g.slope(*hole)
                hole_slopes[cls].append(s_hole)
                assert s_hole <= 0.03
                assert g.radial_margin(*hole) >= 3.0
                assert np.all(g.slope(hole[0] + 0.9 * np.cos(ring), hole[1] + 0.9 * np.sin(ring)) <= 0.036 + 1e-12)
                # ball: on the green, can rest, straight line stays on the green
                assert g.on_green(*ball, 0.5)
                assert g.can_rest(*ball, 0.9)
                f = np.linspace(0, 1, 9)
                assert np.all(g.on_green(ball[0] + f * (hole[0] - ball[0]), ball[1] + f * (hole[1] - ball[1])))
    # spec: local slope near legal hole locations is typically 0.5-3 %
    for cls, vals in hole_slopes.items():
        vals = np.array(vals)
        assert 0.008 < np.median(vals) < 0.025, cls
        assert np.mean((vals >= 0.005) & (vals <= 0.03)) > 0.85, cls


def test_ball_can_actually_rest_at_its_position():
    """A ball placed at the scenario position and released stays put."""
    for cls in ("undulating", "tiered"):
        for seed in range(15):
            sc = gr.make_scenario(cls, 6.0, seed)
            g = sc.green
            r = ph.simulate_putt(g.surface, sc.ball_xy, sc.hole_xy, 0.0, 0.0, g.a_r, g.grain)
            assert r.status == ph.RollStatus.STOPPED and r.t_end == 0.0


def test_true_green_putts_are_solvable_by_the_oracle():
    """solve_aim on the true grid surface with the true speed and grain."""
    n = n_ok = 0
    for cls in gr.GREEN_CLASSES:
        for seed in range(12):
            g = gr.make_green(cls, seed)
            for dist in (3.0, 9.0):
                sc = gr.make_scenario(cls, dist, seed, green=g)
                sol = ph.solve_aim(g.surface, sc.ball_xy, sc.hole_xy, g.a_r, g.grain)
                n += 1
                if sol.ok:
                    n_ok += 1
                    r = ph.simulate_putt(g.surface, sc.ball_xy, sc.hole_xy, sol.phi, sol.v0, g.a_r, g.grain)
                    assert r.captured and abs(r.lateral_at_line) < 5e-5
                else:
                    assert sol.status != ph.SolveStatus.OK
    assert n_ok >= 0.95 * n


def test_impossible_placement_raises():
    g = gr.make_green("gentle", 2)
    rng = np.random.default_rng(0)
    with pytest.raises(gr.PlacementError):
        gr.place_ball(g, (0.0, 0.0), 40.0, rng)
    with pytest.raises(gr.PlacementError):
        gr.place_putt(g, 40.0, rng, max_hole_tries=5)
    with pytest.raises(gr.PlacementError):
        gr.place_hole(g, rng, max_slope=1e-6, max_tries=512)
    with pytest.raises(gr.PlacementError):
        gr.place_hole(g, rng, min_edge_dist=30.0)
    with pytest.raises(ValueError):
        gr.place_ball(g, (0.0, 0.0), -1.0, rng)


def test_placement_respects_custom_limits():
    g = gr.make_green("undulating", 9)
    rng = np.random.default_rng(1)
    for _ in range(20):
        hole = gr.place_hole(g, rng, max_slope=0.015, min_edge_dist=4.0)
        assert g.slope(*hole) <= 0.015 and g.radial_margin(*hole) >= 4.0
        ball = gr.place_ball(g, hole, 3.0, rng, edge_margin=1.0)
        assert g.on_green(*ball, 1.0)


def test_green_from_surface_wraps_exact_surfaces():
    quad = ph.QuadraticSurface(0.01, -0.02, 0.003, 0.001, -0.002)
    g = gr.green_from_surface(quad, edge_radius=10.0, collar_width=1.2, stimp_ft=11.0, grain=ph.Grain(0.08, 0.5))
    assert g.surface is quad and g.green_class == "custom" and g.seed is None
    assert g.z(3.0, -2.0) == quad.z(3.0, -2.0)  # exact, no interpolation
    assert g.a_r == pytest.approx(ph.stimp_to_decel(11.0)) and g.grain.kappa == 0.08
    assert g.edge_radius(1.3) == 10.0 and g.edge_radius_min == g.edge_radius_max == 10.0
    assert g.region(9.9, 0.0) == gr.REGION_GREEN
    assert g.region(0.0, 10.5) == gr.REGION_COLLAR
    assert g.region(-11.3, 0.0) == gr.REGION_ROUGH
    assert g.canopy_z(0.0, 12.0) == pytest.approx(quad.z(0.0, 12.0) + gr.ROUGH_STEP)
    assert np.allclose(g.tilt, [0.01, -0.02])
    # holes and balls can be placed on it, and the aim solver runs on it
    rng = np.random.default_rng(0)
    hole, ball = gr.place_putt(g, 5.0, rng)
    assert g.slope(*hole) <= 0.03 and g.on_green(*ball, 0.5)
    assert ph.solve_aim(g.surface, ball, hole, g.a_r, g.grain).ok
    # a callable is sampled onto a grid
    g2 = gr.green_from_surface(lambda x, y: 0.02 * x - 0.01 * y)
    assert isinstance(g2.surface, ph.GridSurface)
    assert g2.z(4.0, 3.0) == pytest.approx(0.05, abs=1e-9)
    assert g2.grain.kappa == 0.0 and g2.stimp_ft == 10.0
    with pytest.raises(TypeError):
        gr.green_from_surface(3.0)
    with pytest.raises(ValueError):
        gr.green_from_surface(quad, edge_radius=-1.0)
