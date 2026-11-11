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
        assert g.canopy_z(x, y) == pytest.approx(g.terrain_z(x, y) + 0.040)
        x, y = at(r_edge + 0.5 * g.collar_width)
        assert g.canopy_z(x, y) == pytest.approx(g.z(x, y) + 0.008)  # no surround terrain under the collar
    assert g.on_green(0.0, 0.0) and g.region(0.0, 0.0) == gr.REGION_GREEN
    assert 0.8 <= g.collar_width <= 1.5
    # the terrain is modelled out to the edge of the height grid: well into the rough
    assert g.model_radius == 24.0 >= g.edge_radius_max + g.collar_width + 2.0
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


def test_params_override_gives_an_exact_plane_and_chosen_surrounds():
    base = gr.CLASS_PARAMS["planar"]
    prm = dataclasses.replace(base, tilt_range=(0.02, 0.02), undulation_slope_rms_range=(0.0, 0.0))
    g = gr.make_green("planar", 3, prm)
    rng = np.random.default_rng(0)
    px, py = rng.uniform(-20, 20, 500), rng.uniform(-20, 20, 500)
    # the rolling surface is the plane everywhere (surround terrain is separate)
    assert np.allclose(g.z(px, py), g.tilt[0] * px + g.tilt[1] * py, atol=1e-8)
    assert np.allclose(g.slope(px, py), 0.02, atol=1e-8)
    # uniform surrounds falling away at 5 %: everything else is the same green
    g2 = gr.make_green(
        "planar", 3, dataclasses.replace(prm, surround_slope_range=(-0.05, -0.05), surround_harmonic_amp_max=(0.0, 0.0))
    )
    assert g2.surround_slope == -0.05 and np.all(g2.surround_amp == 0.0)
    assert np.array_equal(g2.surface.heights, g.surface.heights)
    assert g2.stimp_ft == g.stimp_ft and g2.grain == g.grain and g2.flagstick_height == g.flagstick_height
    assert g2.edge_r0 == g.edge_r0 and g2.collar_width == g.collar_width
    for theta in (0.0, 1.0, 4.0):
        far = g2.edge_radius(theta) + g2.collar_width + 5.0
        x, y = far * math.cos(theta), far * math.sin(theta)
        assert g2.surround_dz(x, y) == pytest.approx(-0.05 * 125.0 / (25.0 + 1.5**2))
        assert g2.terrain_z(x, y) == pytest.approx(g2.z(x, y) - 0.05 * 125.0 / 27.25)
    with pytest.raises(ValueError):
        gr.make_green("planar", 3, dataclasses.replace(prm, surround_onset=0.0))


def test_surround_terrain_starts_beyond_the_collar_and_follows_the_drawn_slope():
    lo, hi = gr.CLASS_PARAMS["gentle"].surround_slope_range
    a1, a2 = gr.CLASS_PARAMS["gentle"].surround_harmonic_amp_max
    means = []
    for seed in range(25):
        g = gr.make_green("gentle", seed)
        means.append(g.surround_slope)
        assert lo <= g.surround_slope <= hi
        assert 0.0 <= g.surround_amp[0] <= a1 and 0.0 <= g.surround_amp[1] <= a2
        theta = np.linspace(0.0, 2 * np.pi, 97)
        s_theta = g.surround_slope_at(theta)
        assert s_theta.min() >= lo - a1 - a2 and s_theta.max() <= hi + a1 + a2
        assert s_theta.mean() == pytest.approx(g.surround_slope, abs=2e-3)
        r_out = g.edge_radius(theta) + g.collar_width  # outer edge of the collar
        ux, uy = np.cos(theta), np.sin(theta)
        # nothing on the green or the collar
        for r in (0.3 * r_out, r_out - g.collar_width, r_out - 1e-9):
            assert np.all(g.surround_dz(r * ux, r * uy) == 0.0)
            assert np.array_equal(g.terrain_z(r * ux, r * uy), g.z(r * ux, r * uy))
        # smooth (C2) onset: cubic in the distance beyond the collar
        for rho in (0.01, 0.05):
            dz = g.surround_dz((r_out + rho) * ux, (r_out + rho) * uy)
            assert np.allclose(dz, s_theta * rho**3 / g.surround_onset**2, rtol=2e-3, atol=1e-12)
        # far out the extra radial slope tends to the drawn value
        d1 = g.surround_dz((r_out + 60.0) * ux, (r_out + 60.0) * uy)
        d2 = g.surround_dz((r_out + 61.0) * ux, (r_out + 61.0) * uy)
        assert np.allclose(d2 - d1, s_theta, rtol=2e-3, atol=1e-6)
        # the camera sees terrain + canopy
        x, y = (r_out + 4.0) * ux, (r_out + 4.0) * uy
        assert np.allclose(g.canopy_z(x, y), g.z(x, y) + g.surround_dz(x, y) + gr.ROUGH_STEP)
    assert np.mean(means) < 0.0  # greens are mostly built up: surrounds fall away


def test_without_fringe_is_the_same_green_with_a_smooth_continuation():
    sc = gr.make_scenario("undulating", 6.0, 4)
    g = sc.green
    assert g.has_fringe
    twin = g.without_fringe()
    assert not twin.has_fringe
    assert twin.surface is g.surface  # the ball rolls on the very same surface
    assert twin.collar_step == 0.0 and twin.rough_step == 0.0 and twin.surround_slope == 0.0
    assert twin.stimp_ft == g.stimp_ft and twin.grain == g.grain and twin.flagstick_height == g.flagstick_height
    assert twin.edge_r0 == g.edge_r0 and twin.collar_width == g.collar_width and twin.seed == g.seed
    rng = np.random.default_rng(1)
    px, py = rng.uniform(-22, 22, 2000), rng.uniform(-22, 22, 2000)
    assert np.array_equal(twin.canopy_z(px, py), twin.z(px, py))
    assert np.array_equal(twin.terrain_z(px, py), g.z(px, py))
    assert np.array_equal(twin.region(px, py), g.region(px, py))  # the boundary is still known
    on = g.on_green(px, py)
    assert np.array_equal(g.canopy_z(px[on], py[on]), twin.canopy_z(px[on], py[on]))
    assert np.max(np.abs(g.canopy_z(px[~on], py[~on]) - twin.canopy_z(px[~on], py[~on]))) > 0.04
    # intermediate twin: canopy steps kept, terrain continues the putting surface
    mid = g.without_surrounds()
    assert mid.surface is g.surface and mid.has_fringe
    assert mid.collar_step == gr.COLLAR_STEP and mid.rough_step == gr.ROUGH_STEP
    assert np.array_equal(mid.terrain_z(px, py), g.z(px, py))
    assert np.allclose(mid.canopy_z(px, py), g.z(px, py) + g.canopy_step(px, py), rtol=0, atol=1e-15)
    assert not mid.without_fringe().has_fringe
    # the original is untouched, and the scenario twin is the same putt
    assert g.has_fringe and g.rough_step == gr.ROUGH_STEP
    sc2 = sc.without_fringe()
    assert np.array_equal(sc2.hole_xy, sc.hole_xy) and np.array_equal(sc2.ball_xy, sc.ball_xy)
    assert sc2.distance == sc.distance and sc2.seed == sc.seed and not sc2.green.has_fringe
    assert sc2.green.surface is g.surface


def test_flagstick_height_is_drawn_per_green():
    heights = []
    for cls in gr.GREEN_CLASSES:
        for seed in range(30):
            h = gr.make_green(cls, seed).flagstick_height
            assert 2.0 <= h <= 2.3
            heights.append(h)
    assert np.ptp(heights) > 0.2
    assert gr.make_green("gentle", 8).flagstick_height == gr.make_green("gentle", 8).flagstick_height
    assert gr.DEFAULT_FLAGSTICK_HEIGHT == 2.13


def test_scenario_point_at():
    sc = gr.make_scenario("gentle", 9.0, 6)
    assert np.allclose(sc.point_at(0.0), sc.ball_xy)
    assert np.allclose(sc.point_at(9.0), sc.hole_xy)
    mid = sc.point_at(4.5)
    assert mid.shape == (2,) and np.allclose(mid, 0.5 * (sc.ball_xy + sc.hole_xy))
    pts = sc.point_at(np.array([0.0, 4.5, 8.0]))
    assert pts.shape == (3, 2)
    assert np.allclose(np.hypot(*(pts - sc.ball_xy).T), [0.0, 4.5, 8.0])
    assert np.all(sc.green.on_green(pts[:, 0], pts[:, 1]))


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
    assert g.surround_slope == 0.0 and g.terrain_z(0.0, 15.0) == quad.z(0.0, 15.0)
    assert g.flagstick_height == gr.DEFAULT_FLAGSTICK_HEIGHT
    assert g.model_radius == pytest.approx(10.0 + 1.2 + 10.0)  # analytic surface: 10 m beyond the collar
    g3 = gr.green_from_surface(quad, edge_radius=10.0, collar_width=1.0, surround_slope=0.04, flagstick_height=2.2)
    assert g3.terrain_z(0.0, 14.0) == pytest.approx(quad.z(0.0, 14.0) + 0.04 * 27.0 / (9.0 + 2.25))
    assert g3.flagstick_height == 2.2 and g3.has_fringe
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


# --------------------------------------------------------------------------
# mounded surrounds (stress-test twin for the turf-horizon hypothesis)
# --------------------------------------------------------------------------


def test_mounded_surrounds_leave_the_green_and_collar_untouched():
    green = gr.make_green("gentle", 4)
    twin = green.with_mounded_surrounds(seed=9)
    assert twin.surface is green.surface and twin.has_fringe
    assert green.surround_mounds is None and twin.surround_mounds.shape == (12, 4)
    rng = np.random.default_rng(0)
    x = rng.uniform(-23.0, 23.0, 20000)
    y = rng.uniform(-23.0, 23.0, 20000)
    margin = np.asarray(green.radial_margin(x, y))
    near = margin >= -green.collar_width  # putting surface and collar
    assert np.array_equal(twin.canopy_z(x[near], y[near]), green.canopy_z(x[near], y[near]))
    assert np.array_equal(twin.z(x, y), green.z(x, y))  # the ball rolls on the same surface everywhere
    far = margin < -green.collar_width - 5.0
    diff = np.asarray(twin.terrain_z(x[far], y[far])) - np.asarray(green.terrain_z(x[far], y[far]))
    assert 0.12 < float(np.std(diff)) < 0.28  # about the requested 0.20 m RMS
    # the onset at the edge of the collar is continuous
    theta = 0.7
    r_edge = green.edge_radius(theta) + green.collar_width
    for eps in (1e-6, 1e-3):
        xo, yo = (r_edge + eps) * math.cos(theta), (r_edge + eps) * math.sin(theta)
        assert abs(twin.surround_dz(xo, yo) - green.surround_dz(xo, yo)) < eps
    # reproducible, seed dependent, and removed again by the optimistic twins
    assert np.array_equal(green.with_mounded_surrounds(9).surround_mounds, twin.surround_mounds)
    assert not np.array_equal(green.with_mounded_surrounds(10).surround_mounds, twin.surround_mounds)
    assert twin.without_fringe().surround_mounds is None and twin.without_surrounds().surround_mounds is None
    assert not twin.without_fringe().has_fringe
    with pytest.raises(ValueError):
        green.with_mounded_surrounds(1, height_rms=-0.1)
