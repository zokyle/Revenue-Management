"""Sensor forward models: geometry of the grazing view, noise models, modes."""

import dataclasses
import json
import math

import numpy as np
import pytest

from greenline_sim import greens as gr
from greenline_sim import physics as ph
from greenline_sim import sensors as se
from greenline_sim.measurements import Measurements

QUIET = se.SensorParams(
    sink_max=0.0,
    sigma_seat=0.0,
    sigma_tilt_bias=0.0,
    sigma_gravity=0.0,
    sigma_boresight=0.0,
    sigma_pixel_elev=0.0,
    sigma_disp=0.0,
    sigma_bearing=0.0,
    sigma_mirage=0.0,
    p_detect_fail_floor=0.0,
    detect_min_width_px=1e-9,
    base_hidden_tolerance=0.0,
    stick_height_rel_error=0.0,
    sigma_grain_azimuth=0.0,
    sigma_grain_strength=0.0,
    sigma_stimp=0.0,
    sigma_heading=math.radians(5.0),
    sigma_survey_lateral=0.0,
    sigma_survey_along=0.0,
)
"""All noise off (the visor still points up to a few degrees off the flag)."""


def _quad_green(coeffs, **kwargs):
    kwargs.setdefault("collar_step", 0.0)
    kwargs.setdefault("rough_step", 0.0)
    return gr.green_from_surface(ph.QuadraticSurface(*coeffs), **kwargs)


# --------------------------------------------------------------------------
# presets and parameters
# --------------------------------------------------------------------------


def test_default_camera_is_the_fixed_gl1_hardware():
    cam = se.SensorParams().camera
    assert cam is se.GL1 and cam.name == "GL1"
    assert cam.f_px == 657.0 and cam.baseline == 0.0200 and cam.h_cam == 0.0056
    assert math.degrees(cam.half_fov_h) == pytest.approx(26.0)
    assert math.degrees(cam.up_fov) == pytest.approx(17.6)
    for name, f_px in (("QVGA", 330.0), ("VGA", 500.0), ("2MP", 1200.0)):
        assert se.CAMERA_PRESETS[name].f_px == f_px and se.CAMERA_PRESETS[name].baseline == 0.034


def test_default_noise_parameters_match_the_specification():
    p = se.SensorParams()
    assert p.sigma_seat == 2.5e-3 and p.sigma_gravity == 0.3e-3 and p.sigma_boresight == 0.3e-3
    assert p.sigma_pixel_elev == 0.15 and p.sigma_disp == 0.08 and p.n_horizon == 41
    assert p.sigma_heading == pytest.approx(math.radians(10.0))
    assert p.sigma_hand_bearing == pytest.approx(math.radians(1.5))
    assert p.sigma_mirage == 5e-5 and p.sink_max == 1.5e-3
    assert p.sigma_grain_azimuth == pytest.approx(math.radians(20.0)) and p.sigma_grain_strength == 0.30
    assert p.sigma_stimp == 0.07 and p.stick_height_rel_error == 0.02 and p.stick_height_default_rel_error == 0.07
    # the systematic and defect terms are off by default (the Monte Carlo sweeps them)
    assert p.disparity_bias == 0.0 and p.grain_noise_floor == 0.0 and p.p_grain_flip == 0.0
    assert p.p_seat_outlier == 0.0 and p.level_shares_tilt_bias is False
    assert p.sigma_survey_lateral == 0.15


# --------------------------------------------------------------------------
# geometry of the grazing view
# --------------------------------------------------------------------------


@pytest.mark.parametrize("cls", gr.GREEN_CLASSES)
def test_canopy_and_margin_equals_the_green_methods(cls):
    green = gr.make_green(cls, 5)
    rng = np.random.default_rng(1)
    x = rng.uniform(-23.0, 23.0, 4000)
    y = rng.uniform(-23.0, 23.0, 4000)
    for g in (green, green.without_surrounds(), green.without_fringe(), green.with_mounded_surrounds(3)):
        canopy, margin = se.canopy_and_margin(g, x, y)
        assert np.allclose(canopy, g.canopy_z(x, y), rtol=0.0, atol=1e-12)
        assert np.allclose(margin, g.radial_margin(x, y), rtol=0.0, atol=1e-12)


def _brute_horizon(green, cam_xy, cam_z, azimuth, mirage_c=0.0, step=0.002, d_max=None):
    ux, uy = math.cos(azimuth), math.sin(azimuth)
    proj = cam_xy[0] * ux + cam_xy[1] * uy
    d_exit = -proj + math.sqrt(proj**2 + green.model_radius**2 - float(cam_xy @ cam_xy))
    if d_max is not None:
        d_exit = min(d_exit, d_max)
    d = np.arange(0.15, d_exit, step)
    ratio = (green.canopy_z(cam_xy[0] + d * ux, cam_xy[1] + d * uy) - cam_z) / d + 0.5 * mirage_c * d
    return float(ratio.max())


@pytest.mark.parametrize("cls", gr.GREEN_CLASSES)
def test_horizon_ray_march_agrees_with_brute_force(cls):
    worst = 0.0
    for seed in (0, 1, 2):
        sc = gr.make_scenario(cls, 6.0, seed)
        for green in (sc.green, sc.green.without_fringe(), sc.green.with_mounded_surrounds(seed)):
            cam_z = green.z(*sc.ball_xy) + 0.005
            az = sc.bearing + np.linspace(-0.45, 0.45, 7)
            got = se.horizon_profile(green, sc.ball_xy, cam_z, az, mirage_c=3e-5)
            for k, a in enumerate(az):
                worst = max(worst, abs(got.ratio[k] - _brute_horizon(green, sc.ball_xy, cam_z, a, mirage_c=3e-5)))
    # pixel noise on a horizon sample is 0.15 px / 657 px = 2.3e-4 rad
    assert worst < 2e-5


def test_horizon_reports_where_and_what_forms_the_silhouette():
    # flat green, rough 40 mm high beyond r = 12 + 1 m: the silhouette is the edge of the rough
    green = gr.green_from_surface(ph.PlaneSurface(0.0, 0.0), edge_radius=12.0, collar_width=1.0)
    h = 0.005
    got = se.horizon_profile(green, np.zeros(2), h, np.array([0.0, 1.0, 2.5]))
    assert np.allclose(got.distance, 13.0, atol=1e-6)
    assert np.all(got.region == gr.REGION_ROUGH)
    assert np.allclose(got.ratio, (0.040 - h) / 13.0, rtol=1e-6)
    # no fringe: the turf just sinks toward the level line; the maximum is at the far end
    bare = green.without_fringe()
    got = se.horizon_profile(bare, np.zeros(2), h, np.array([0.3]))
    assert got.ratio[0] == pytest.approx(-h / bare.model_radius, rel=1e-6)
    # a 2 % up-slope adds 0.02 to the silhouette
    tilted = gr.green_from_surface(ph.PlaneSurface(0.02, 0.0), collar_step=0.0, rough_step=0.0)
    got = se.horizon_profile(tilted, np.zeros(2), h, np.array([0.0]), d_max=10.0)
    assert got.ratio[0] == pytest.approx(0.02 - h / 10.0, rel=1e-9)
    assert got.distance[0] == pytest.approx(10.0, abs=1e-9)


def test_fringe_raises_the_horizon_above_the_bare_putting_surface():
    sc = gr.make_scenario("gentle", 6.0, 4)
    cam_z = sc.green.z(*sc.ball_xy) + 0.005
    az = sc.bearing + np.linspace(-0.45, 0.45, 11)
    bare = se.horizon_profile(sc.green.without_fringe(), sc.ball_xy, cam_z, az)
    canopy_only = se.horizon_profile(sc.green.without_surrounds(), sc.ball_xy, cam_z, az)
    assert np.all(canopy_only.ratio >= bare.ratio - 1e-12)
    assert np.any(canopy_only.ratio > bare.ratio + 1e-4)


def test_mirage_sags_the_sight_lines_by_half_c_d():
    green = _quad_green((0.0, 0.0, 0.0, 0.0, 0.0))
    cam = np.zeros(2)
    hole = np.array([8.0, 0.0])
    base0, _ = se.flag_sight_lines(green, cam, 0.005, hole)
    base1, _ = se.flag_sight_lines(green, cam, 0.005, hole, mirage_c=1e-4)
    assert base1 - base0 == pytest.approx(0.5 * 1e-4 * 8.0, rel=1e-12)


def test_flag_base_visibility_is_a_real_line_of_sight_test():
    h = 0.005
    cam = np.zeros(2)
    # plane (any slope): the sight line to the hole lip clears the ground in between
    for slope in (-0.03, 0.0, 0.03):
        base, crest = se.flag_sight_lines(_quad_green((slope, 0.01, 0, 0, 0)), cam, h, np.array([6.0, 0.0]))
        assert crest < base and base == pytest.approx(slope - h / 6.0, rel=1e-9)
    # bowl: visible
    base, crest = se.flag_sight_lines(_quad_green((0.0, 0.0, 0.002, 0, 0)), cam, h, np.array([6.0, 0.0]))
    assert crest < base
    # crown: hidden once the hole is beyond r* = sqrt(2 h / |c|), with the crest at a - sqrt(2 h |c|)
    c = -0.002
    r_star = math.sqrt(2.0 * h / abs(c))  # 2.24 m
    green = _quad_green((0.01, 0.0, c, 0, 0))
    base, crest = se.flag_sight_lines(green, cam, h, np.array([1.5, 0.0]), step=0.001)
    assert crest < base  # hole nearer than the crest: visible
    base, crest = se.flag_sight_lines(green, cam, h, np.array([6.0, 0.0]), step=0.001)
    assert crest > base  # hidden
    assert crest == pytest.approx(0.01 - math.sqrt(2.0 * h * abs(c)), abs=1e-7)
    assert r_star < 6.0


def test_measure_reports_hidden_base_and_the_crest_elevation():
    green = _quad_green((0.01, 0.0, -0.002, 0.0, 0.0))
    ball = np.zeros(2)
    hole = np.array([6.0, 0.0])
    meas, truth = se.measure(green, ball, hole, QUIET, 1)
    assert meas.flag_found and not meas.flag_base_visible and not truth.base_visible
    h = QUIET.camera.h_cam
    assert math.tan(meas.flag_low_elev) == pytest.approx(0.01 - math.sqrt(2.0 * h * 0.002), abs=2e-6)
    # the hole is LOWER than that sight line
    bound = h + 6.0 * math.tan(meas.flag_low_elev)
    assert truth.dz_hole < bound
    assert truth.hidden_height == pytest.approx(bound - truth.dz_hole, abs=1e-5)
    # a base hidden by less than the tolerance is reported visible
    tol = dataclasses.replace(QUIET, base_hidden_tolerance=1.0)
    assert se.measure(green, ball, hole, tol, 1)[0].flag_base_visible


# --------------------------------------------------------------------------
# the measurement, noise off
# --------------------------------------------------------------------------


def test_noise_free_measurement_reproduces_the_truth():
    surf = ph.QuadraticSurface(0.012, -0.007, 0.001, 0.0005, 0.0015)
    green = gr.green_from_surface(
        surf, collar_step=0.0, rough_step=0.0, stimp_ft=9.5, grain=ph.Grain(0.08, 0.7), flagstick_height=2.2
    )
    ball = np.array([1.0, -2.0])
    hole = np.array([8.5, 3.0])
    meas, truth = se.measure(green, ball, hole, QUIET, 7)
    cam = QUIET.camera
    dist = float(np.hypot(*(hole - ball)))
    bearing = math.atan2(hole[1] - ball[1], hole[0] - ball[0])
    assert truth.distance == pytest.approx(dist) and truth.bearing == pytest.approx(bearing)
    # tilt = true gradient, expressed in the device frame
    gx, gy = surf.grad(*ball)
    ch, sh = math.cos(truth.heading), math.sin(truth.heading)
    assert np.allclose(meas.tilt, [gx * ch + gy * sh, -gx * sh + gy * ch], atol=1e-15)
    assert meas.tilt_reads == 1
    # flag: bearing in the device frame, stereo disparity, base elevation -> hole height
    assert meas.flag_found and meas.flag_base_visible
    assert meas.flag_bearing == pytest.approx(bearing - truth.heading, abs=1e-12)
    assert meas.flag_disparity == pytest.approx(cam.f_px * cam.baseline / dist, rel=1e-12)
    dz = cam.h_cam + dist * math.tan(meas.flag_low_elev)
    assert dz == pytest.approx(surf.z(*hole) - surf.z(*ball), abs=1e-12)
    assert truth.dz_hole == pytest.approx(dz, abs=1e-12)
    # top of the stick inside the upward field at 9 m: monocular range is exact
    assert meas.flag_top_visible
    assert meas.stick_height_est == pytest.approx(2.2) and meas.stick_height_rel_sigma == 0.0
    mono = meas.stick_height_est / (math.tan(meas.flag_top_elev) - math.tan(meas.flag_low_elev))
    assert mono == pytest.approx(dist, rel=1e-12)
    # golfer's entry and grain
    assert meas.stimp_ft == pytest.approx(9.5) and meas.grain_kappa == pytest.approx(0.08)
    assert math.cos(meas.grain_azimuth - (0.7 - truth.heading)) == pytest.approx(1.0)
    assert math.isnan(meas.user_distance)
    # horizon: 41 samples across the horizontal field, equal to the ray-march
    assert meas.horizon_az.shape == (41,) and meas.horizon_elev.shape == (41,)
    assert meas.horizon_az[0] == pytest.approx(-cam.half_fov_h) and meas.horizon_az[-1] == pytest.approx(cam.half_fov_h)
    assert np.allclose(np.tan(meas.horizon_elev), truth.horizon.ratio, atol=1e-15)


def test_flag_top_outside_the_upward_field_at_short_range():
    green = _quad_green((0.0, 0.0, 0.0, 0.0, 0.0), flagstick_height=2.13)
    near, _ = se.measure(green, np.zeros(2), np.array([4.0, 0.0]), QUIET, 1)
    far, _ = se.measure(green, np.zeros(2), np.array([9.0, 0.0]), QUIET, 1)
    assert near.flag_found and not near.flag_top_visible and math.isnan(near.flag_top_elev)
    assert far.flag_top_visible and math.isfinite(far.flag_top_elev)
    # the limit is where the top is 17.6 degrees up: 2.13 / tan(17.6 deg) = 6.7 m
    assert 2.13 / math.tan(QUIET.camera.up_fov) == pytest.approx(6.71, abs=0.01)


def test_measurement_is_deterministic_and_seed_dependent():
    sc = gr.make_scenario("undulating", 6.0, 2)
    a, _ = se.measure(sc.green, sc.ball_xy, sc.hole_xy, se.SensorParams(), 11)
    b, _ = se.measure(sc.green, sc.ball_xy, sc.hole_xy, se.SensorParams(), 11)
    c, _ = se.measure(sc.green, sc.ball_xy, sc.hole_xy, se.SensorParams(), 12)
    assert a.to_dict() == b.to_dict()
    assert a.to_dict() != c.to_dict()
    gen = np.random.default_rng(11)
    d, _ = se.measure(sc.green, sc.ball_xy, sc.hole_xy, se.SensorParams(), gen)
    assert d.to_dict() == a.to_dict()


def test_measurements_json_round_trip():
    sc = gr.make_scenario("gentle", 4.5, 3)
    for kwargs in ({}, {"mode": "flag_out"}, {"with_horizon": False, "spin": True}):
        meas, _ = se.measure(sc.green, sc.ball_xy, sc.hole_xy, se.SensorParams(), 5, **kwargs)
        back = Measurements.from_dict(json.loads(json.dumps(meas.to_dict(), allow_nan=False)))
        assert back.to_dict() == meas.to_dict()
        assert np.array_equal(back.tilt, meas.tilt) and np.array_equal(back.horizon_elev, meas.horizon_elev)
        assert back.flag_found == meas.flag_found and back.tilt_reads == meas.tilt_reads


# --------------------------------------------------------------------------
# noise models
# --------------------------------------------------------------------------


def test_noise_draws_are_paired_across_parameter_changes():
    sc = gr.make_scenario("gentle", 6.0, 6)
    base = se.SensorParams(sigma_tilt_bias=0.0, sigma_gravity=0.0)
    lo, t_lo = se.measure(sc.green, sc.ball_xy, sc.hole_xy, dataclasses.replace(base, sigma_seat=1e-3), 21)
    hi, t_hi = se.measure(sc.green, sc.ball_xy, sc.hole_xy, dataclasses.replace(base, sigma_seat=5e-3), 21)
    # same pose and camera data; only the seating error is scaled
    assert t_lo.heading == t_hi.heading
    assert lo.flag_disparity == hi.flag_disparity and np.array_equal(lo.horizon_elev, hi.horizon_elev)
    assert np.allclose(t_hi.seat_error_world, 5.0 * t_lo.seat_error_world, rtol=1e-12)
    gx, gy = sc.green.grad(*sc.ball_xy)
    ch, sh = math.cos(t_lo.heading), math.sin(t_lo.heading)
    true_dev = np.array([gx * ch + gy * sh, -gx * sh + gy * ch])
    assert np.allclose(hi.tilt - true_dev, 5.0 * (lo.tilt - true_dev), rtol=1e-9, atol=1e-15)


def test_spin_and_reread_cancels_the_device_bias():
    sc = gr.make_scenario("planar", 3.0, 1)
    params = dataclasses.replace(QUIET, sigma_tilt_bias=3e-3)
    single, truth = se.measure(sc.green, sc.ball_xy, sc.hole_xy, params, 4)
    spun, truth_s = se.measure(sc.green, sc.ball_xy, sc.hole_xy, params, 4, spin=True)
    gx, gy = sc.green.grad(*sc.ball_xy)
    ch, sh = math.cos(truth.heading), math.sin(truth.heading)
    true_dev = np.array([gx * ch + gy * sh, -gx * sh + gy * ch])
    assert np.allclose(single.tilt - true_dev, truth.tilt_bias, atol=1e-15)
    assert np.linalg.norm(truth.tilt_bias) > 1e-4
    assert np.allclose(spun.tilt, true_dev, atol=1e-15)
    assert spun.tilt_reads == 2 and truth_s.heading == truth.heading


def test_spin_averages_two_seatings_unless_they_are_correlated():
    sc = gr.make_scenario("planar", 3.0, 1)
    gx, gy = sc.green.grad(*sc.ball_xy)

    def tilt_error_rms(rho, spin):
        params = dataclasses.replace(QUIET, sigma_seat=2.5e-3, seat_repeat_correlation=rho)
        err = []
        for seed in range(600):
            meas, truth = se.measure(sc.green, sc.ball_xy, sc.hole_xy, params, seed, spin=spin, with_horizon=False)
            ch, sh = math.cos(truth.heading), math.sin(truth.heading)
            err.append(meas.tilt - np.array([gx * ch + gy * sh, -gx * sh + gy * ch]))
        return float(np.sqrt(np.mean(np.square(err))))

    single = tilt_error_rms(0.0, False)
    assert single == pytest.approx(2.5e-3, rel=0.08)
    assert tilt_error_rms(0.0, True) == pytest.approx(2.5e-3 / math.sqrt(2.0), rel=0.08)
    assert tilt_error_rms(1.0, True) == pytest.approx(2.5e-3, rel=0.08)


def test_stereo_range_noise_follows_the_disparity_formula():
    green = _quad_green((0.0, 0.0, 0.0, 0.0, 0.0))
    params = dataclasses.replace(QUIET, sigma_disp=0.08)
    cam = params.camera
    for dist in (3.0, 9.0):
        disp = np.array(
            [se.measure(green, np.zeros(2), np.array([dist, 0.0]), params, s, with_horizon=False)[0].flag_disparity
             for s in range(800)]
        )
        rel = cam.f_px * cam.baseline / disp / dist - 1.0
        assert float(np.std(rel)) == pytest.approx(dist * 0.08 / (cam.f_px * cam.baseline), rel=0.1)


def test_elevation_noise_and_level_error_have_the_specified_size():
    green = _quad_green((0.0, 0.0, 0.0, 0.0, 0.0))
    params = dataclasses.replace(QUIET, sigma_pixel_elev=0.15, sigma_gravity=0.3e-3, sigma_boresight=0.3e-3)
    base = math.atan(-params.camera.h_cam / 5.0)
    err = np.array(
        [se.measure(green, np.zeros(2), np.array([5.0, 0.0]), params, s, with_horizon=False)[0].flag_low_elev - base
         for s in range(1500)]
    )
    expect = math.sqrt((0.15 / 657.0) ** 2 + 2.0 * 0.3e-3**2)  # pixel + gravity + boresight pitch (roll * sin(bearing) is tiny)
    assert float(np.std(err)) == pytest.approx(expect, rel=0.08)
    assert abs(float(np.mean(err))) < 4.0 * expect / math.sqrt(1500)


def test_sink_lowers_the_lens_and_stays_within_its_range():
    green = _quad_green((0.0, 0.0, 0.0, 0.0, 0.0))
    params = dataclasses.replace(QUIET, sink_max=1.5e-3)
    sinks = np.array(
        [se.measure(green, np.zeros(2), np.array([3.0, 0.0]), params, s, with_horizon=False)[1].sink for s in range(300)]
    )
    assert sinks.min() >= 0.0 and sinks.max() <= 1.5e-3 and 0.6e-3 < sinks.mean() < 0.9e-3
    meas, truth = se.measure(green, np.zeros(2), np.array([3.0, 0.0]), params, 0, with_horizon=False)
    assert truth.cam_height == pytest.approx(params.camera.h_cam - truth.sink)
    assert meas.h_cam == params.camera.h_cam  # the device only knows the nominal height
    assert math.tan(meas.flag_low_elev) == pytest.approx(-truth.cam_height / 3.0, rel=1e-12)


def test_grain_and_stimp_noise():
    green = _quad_green((0.0, 0.0, 0.0, 0.0, 0.0), stimp_ft=10.0, grain=ph.Grain(0.1, 0.4))
    params = dataclasses.replace(
        QUIET, sigma_stimp=0.07, sigma_grain_azimuth=math.radians(20.0), sigma_grain_strength=0.30
    )
    stimp, kappa, az = [], [], []
    for s in range(1200):
        meas, truth = se.measure(green, np.zeros(2), np.array([3.0, 0.0]), params, s, with_horizon=False)
        stimp.append(meas.stimp_ft / 10.0 - 1.0)
        kappa.append(meas.grain_kappa / 0.1 - 1.0)
        az.append(math.remainder(meas.grain_azimuth + truth.heading - 0.4, 2.0 * math.pi))
    assert float(np.std(stimp)) == pytest.approx(0.07, rel=0.1)
    assert float(np.std(kappa)) == pytest.approx(0.30, rel=0.1)
    assert float(np.std(az)) == pytest.approx(math.radians(20.0), rel=0.1)


def test_grain_sensor_defects():
    """Additive floor: grain is reported where there is none.  180-degree
    ambiguity: the axis is right, the sense wrong, with the stated probability."""
    bare = _quad_green((0.0, 0.0, 0.0, 0.0, 0.0), grain=ph.Grain(0.0, 0.0))
    floor = dataclasses.replace(QUIET, grain_noise_floor=0.02)
    kx, ky = [], []
    for s in range(1500):
        meas, truth = se.measure(bare, np.zeros(2), np.array([3.0, 0.0]), floor, s, with_horizon=False)
        az = meas.grain_azimuth + truth.heading
        kx.append(meas.grain_kappa * math.cos(az))
        ky.append(meas.grain_kappa * math.sin(az))
    assert float(np.std(kx)) == pytest.approx(0.02, rel=0.1) and float(np.std(ky)) == pytest.approx(0.02, rel=0.1)
    assert se.measure(bare, np.zeros(2), np.array([3.0, 0.0]), QUIET, 0, with_horizon=False)[0].grain_kappa == 0.0
    grained = _quad_green((0.0, 0.0, 0.0, 0.0, 0.0), grain=ph.Grain(0.1, 0.4))
    flip = dataclasses.replace(QUIET, p_grain_flip=0.25)
    flipped = 0
    for s in range(1500):
        meas, truth = se.measure(grained, np.zeros(2), np.array([3.0, 0.0]), flip, s, with_horizon=False)
        err = math.remainder(meas.grain_azimuth + truth.heading - 0.4, 2.0 * math.pi)
        assert abs(err) < 1e-9 or abs(abs(err) - math.pi) < 1e-9
        flipped += abs(err) > 1.0
        assert meas.grain_kappa == pytest.approx(0.1)
    assert flipped / 1500 == pytest.approx(0.25, abs=0.035)


def test_disparity_bias_shifts_the_stereo_range():
    green = _quad_green((0.0, 0.0, 0.0, 0.0, 0.0))
    fb = 657.0 * 0.0200
    for bias in (0.1, -0.2):
        meas, _ = se.measure(green, np.zeros(2), np.array([9.0, 0.0]), dataclasses.replace(QUIET, disparity_bias=bias), 1,
                             with_horizon=False)
        assert meas.flag_disparity == pytest.approx(fb / 9.0 + bias, abs=1e-12)
        # +0.1 px at 9 m reads 6 % short; -0.2 px reads 16 % long
        assert fb / meas.flag_disparity == pytest.approx(9.0 / (1.0 + bias * 9.0 / fb), rel=1e-12)


def test_seating_outlier_mixture():
    green = _quad_green((0.0, 0.0, 0.0, 0.0, 0.0))
    params = dataclasses.replace(QUIET, sigma_seat=2.5e-3, p_seat_outlier=0.25, seat_outlier_sigma=11e-3)
    plain = dataclasses.replace(params, p_seat_outlier=0.0)
    err = np.array([se.measure(green, np.zeros(2), np.array([3.0, 0.0]), params, s, with_horizon=False)[1].seat_error_world
                    for s in range(3000)])
    base = np.array([se.measure(green, np.zeros(2), np.array([3.0, 0.0]), plain, s, with_horizon=False)[1].seat_error_world
                     for s in range(3000)])
    changed = np.any(err != base, axis=1)
    assert changed.mean() == pytest.approx(0.25, abs=0.03)  # the same draws, a quarter of them with the extra term
    assert float(np.std(base)) == pytest.approx(2.5e-3, rel=0.05)
    assert float(np.std(err[changed])) == pytest.approx(math.hypot(2.5e-3, 11e-3), rel=0.08)
    assert np.array_equal(err[~changed], base[~changed])


def test_level_reference_can_share_the_tilt_bias():
    """With the option on, a tilt bias (apparent slope) raises the measured
    elevations by the same angle: the hole height seen at the flag base then
    carries the bias, exactly as the tilt does."""
    green = _quad_green((0.0, 0.0, 0.0, 0.0, 0.0))
    bias = np.array([1.5e-3, -0.8e-3])
    own = se.measure(green, np.zeros(2), np.array([6.0, 0.0]), QUIET, 4, tilt_bias=bias)
    shared = se.measure(green, np.zeros(2), np.array([6.0, 0.0]), dataclasses.replace(QUIET, level_shares_tilt_bias=True), 4,
                        tilt_bias=bias)
    assert np.allclose(own[1].level_error, 0.0) and np.allclose(shared[1].level_error, bias)
    beta = own[0].flag_bearing
    assert shared[0].flag_low_elev == pytest.approx(own[0].flag_low_elev + bias[0] + bias[1] * math.sin(beta), abs=1e-12)
    az = shared[0].horizon_az
    assert np.allclose(shared[0].horizon_elev, own[0].horizon_elev + bias[0] + bias[1] * np.sin(az), atol=1e-12)
    # the tilt says "rises 1.5 mrad more along the visor axis than it does", and so does the flag base
    rise_tilt = 6.0 * (shared[0].tilt[0] - own[0].tilt[0] + bias[0])
    rise_flag = 6.0 * (math.tan(shared[0].flag_low_elev) - math.tan(own[0].flag_low_elev))
    assert rise_flag == pytest.approx(rise_tilt, rel=0.1)
    assert np.array_equal(shared[0].tilt, own[0].tilt)


def test_horizon_truth_marks_samples_formed_at_the_edge_of_the_model():
    """Where the terrain keeps rising to the edge of the modelled world the
    silhouette is set by where the model ends, and is flagged as such."""
    rising = gr.green_from_surface(ph.PlaneSurface(0.02, 0.0), collar_step=0.0, rough_step=0.0)
    az = np.radians([-20.0, 0.0, 20.0])
    up = se.horizon_profile(rising, np.zeros(2), 0.005, az)
    assert np.all(up.at_boundary) and np.allclose(up.distance, rising.model_radius)
    crowned = _quad_green((0.0, 0.0, -0.004, 0.0, -0.004))
    crest = se.horizon_profile(crowned, np.zeros(2), 0.005, az)
    assert not np.any(crest.at_boundary) and np.allclose(crest.distance, math.sqrt(2 * 0.005 / 0.004), atol=0.02)


def test_stick_height_knowledge_learned_or_default():
    green = _quad_green((0.0, 0.0, 0.0, 0.0, 0.0), flagstick_height=2.25)
    args = (green, np.zeros(2), np.array([9.0, 0.0]))
    learned = [se.measure(*args, se.SensorParams(), s, with_horizon=False)[0] for s in range(600)]
    rel = np.array([m.stick_height_est / 2.25 - 1.0 for m in learned])
    assert float(np.std(rel)) == pytest.approx(0.02, rel=0.1) and learned[0].stick_height_rel_sigma == 0.02
    first_hole, _ = se.measure(*args, dataclasses.replace(se.SensorParams(), stick_height_learned=False), 0, with_horizon=False)
    assert first_hole.stick_height_est == 2.13 and first_hole.stick_height_rel_sigma == 0.07


# --------------------------------------------------------------------------
# flag detection and modes
# --------------------------------------------------------------------------


def test_detection_probability_falls_with_range_and_rises_with_focal_length():
    p = se.SensorParams()
    d = np.array([1.5, 3.0, 6.0, 9.0, 12.0, 20.0])
    prob = se.detection_probability(d, p)
    assert np.all(np.diff(prob) < 0.0) and prob[0] <= 1.0 - p.p_detect_fail_floor
    assert prob[0] == pytest.approx(0.98, abs=0.001) and 0.90 < prob[4] < 0.93
    qvga = dataclasses.replace(p, camera=se.CAMERA_PRESETS["QVGA"])
    two_mp = dataclasses.replace(p, camera=se.CAMERA_PRESETS["2MP"])
    assert np.all(se.detection_probability(d, qvga) < prob) and np.all(se.detection_probability(d, two_mp) > prob)
    assert se.detection_probability(12.0, qvga) < 0.5


def test_flag_outside_the_field_or_missed_is_not_found():
    green = _quad_green((0.01, 0.0, 0.0, 0.0, 0.0))
    ball, hole = np.zeros(2), np.array([4.0, 0.0])
    wild = dataclasses.replace(QUIET, sigma_heading=math.radians(120.0))
    outcomes = [se.measure(green, ball, hole, wild, s, with_horizon=False) for s in range(200)]
    for meas, truth in outcomes:
        assert meas.flag_found == truth.in_fov
        assert truth.in_fov == (abs(math.remainder(truth.bearing - truth.heading, 2 * math.pi)) <= QUIET.camera.half_fov_h)
        if not meas.flag_found:
            assert math.isnan(meas.flag_bearing) and math.isnan(meas.flag_disparity) and math.isnan(meas.flag_low_elev)
            assert not meas.flag_base_visible and not meas.flag_top_visible
    assert 0.05 < np.mean([m.flag_found for m, _ in outcomes]) < 0.6
    # detection failures at the modelled rate
    lossy = dataclasses.replace(QUIET, p_detect_fail_floor=0.3)
    found = np.mean([se.measure(green, ball, hole, lossy, s, with_horizon=False)[0].flag_found for s in range(1500)])
    assert found == pytest.approx(0.7, abs=0.04)


def test_flag_out_mode_points_by_hand_and_dials_the_distance():
    sc = gr.make_scenario("gentle", 6.0, 8)
    params = se.SensorParams()
    reads = [se.measure(sc.green, sc.ball_xy, sc.hole_xy, params, s, mode="flag_out") for s in range(500)]
    meas, truth = reads[0]
    assert not meas.flag_found and meas.horizon_az.size == 0 and meas.horizon_elev.size == 0
    assert math.isfinite(meas.user_distance) and np.all(np.isfinite(meas.tilt))
    pointing = np.array([math.remainder(t.heading - t.bearing, 2 * math.pi) for _, t in reads])
    assert float(np.std(pointing)) == pytest.approx(math.radians(1.5), rel=0.1)
    dial = np.array([m.user_distance / 6.0 - 1.0 for m, _ in reads])
    assert float(np.std(dial)) == pytest.approx(params.sigma_user_distance, rel=0.1)
    with pytest.raises(ValueError):
        se.measure(sc.green, sc.ball_xy, sc.hole_xy, params, 0, mode="telepathy")


def test_only_the_horizon_differs_between_a_green_and_its_fringe_twins():
    sc = gr.make_scenario("undulating", 6.0, 5)
    real, _ = se.measure(sc.green, sc.ball_xy, sc.hole_xy, se.SensorParams(), 9)
    for twin in (sc.green.without_fringe(), sc.green.without_surrounds(), sc.green.with_mounded_surrounds(1)):
        other, _ = se.measure(twin, sc.ball_xy, sc.hole_xy, se.SensorParams(), 9)
        a, b = real.to_dict(), other.to_dict()
        assert a.pop("horizon_elev") != b.pop("horizon_elev")
        assert a == b


# --------------------------------------------------------------------------
# survey
# --------------------------------------------------------------------------


def test_survey_stations():
    assert np.allclose(se.survey_stations(6.0), [0.0, 3.0, 5.0])
    assert np.allclose(se.survey_stations(12.0, 2), [0.0, 6.0])
    assert np.allclose(se.survey_stations(1.5), [0.0, 0.75, 1.125])  # third drop still beyond the midpoint
    assert np.allclose(se.survey_stations(3.0, 1), [0.0])
    with pytest.raises(ValueError):
        se.survey_stations(3.0, 4)


def test_survey_drops_share_the_device_and_lie_along_the_line():
    sc = gr.make_scenario("gentle", 9.0, 2)
    params = dataclasses.replace(se.SensorParams(), p_detect_fail_floor=0.0)
    drops = se.measure_survey(sc.green, sc.ball_xy, sc.hole_xy, params, 13)
    assert len(drops) == 3
    first_meas, first_truth = drops[0]
    assert np.allclose(first_truth.marker_xy, sc.ball_xy)
    stations = se.survey_stations(9.0)
    unit = (sc.hole_xy - sc.ball_xy) / 9.0
    left = np.array([-unit[1], unit[0]])
    for k, (meas, truth) in enumerate(drops[1:], start=1):
        offset = truth.marker_xy - sc.ball_xy
        assert abs(offset @ unit - stations[k]) < 1.0  # sigma_survey_along = 0.2 m
        assert abs(offset @ left) < 0.6  # sigma_survey_lateral = 0.15 m
        assert np.array_equal(truth.tilt_bias, first_truth.tilt_bias)  # one device
        assert meas.stimp_ft == first_meas.stimp_ft and meas.stick_height_est == first_meas.stick_height_est
        assert meas.flag_found and meas.horizon_az.size == 0
        assert truth.heading != first_truth.heading  # its own placement
        # its own range to the flag
        assert meas.f_px * meas.baseline / meas.flag_disparity == pytest.approx(truth.distance, rel=0.2)
    # reproducible, and an existing Quick Read can serve as drop 0
    again = se.measure_survey(sc.green, sc.ball_xy, sc.hole_xy, params, 13)
    assert [m.to_dict() for m, _ in again] == [m.to_dict() for m, _ in drops]
    quick = se.measure(sc.green, sc.ball_xy, sc.hole_xy, params, 99)
    reuse = se.measure_survey(sc.green, sc.ball_xy, sc.hole_xy, params, 13, first=quick, n_drops=2)
    assert len(reuse) == 2 and reuse[0][0] is quick[0]
