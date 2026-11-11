"""Estimator (firmware reference): forward model, fit, modes, no truth leakage."""

import ast
import dataclasses
import inspect
import math
import pathlib

import numpy as np
import pytest

from greenline_sim import estimator as es
from greenline_sim import greens as gr
from greenline_sim import physics as ph
from greenline_sim import sensors as se
from greenline_sim.measurements import Measurements

from test_sensors import QUIET

H = 0.0056


def _quad_green(coeffs, **kwargs):
    kwargs.setdefault("collar_step", 0.0)
    kwargs.setdefault("rough_step", 0.0)
    return gr.green_from_surface(ph.QuadraticSurface(*coeffs), **kwargs)


def _meas(**overrides) -> Measurements:
    """A hand-made measurement: 5 m putt, flag dead ahead, flat, no horizon."""
    base = dict(
        f_px=657.0,
        baseline=0.0204,
        h_cam=H,
        tilt=np.array([0.0, 0.0]),
        tilt_reads=1,
        flag_found=True,
        flag_bearing=0.0,
        flag_disparity=657.0 * 0.0204 / 5.0,
        flag_low_elev=math.atan(-(H - 0.75e-3) / 5.0),
        flag_base_visible=True,
        flag_top_visible=False,
        flag_top_elev=math.nan,
        stick_height_est=2.13,
        stick_height_rel_sigma=0.02,
        horizon_az=np.zeros(0),
        horizon_elev=np.zeros(0),
        grain_kappa=0.0,
        grain_azimuth=0.0,
        stimp_ft=10.0,
        user_distance=math.nan,
    )
    base.update(overrides)
    return Measurements(**base)


# --------------------------------------------------------------------------
# horizon forward model of a quadratic patch
# --------------------------------------------------------------------------

QUADS = [
    (0.010, 0.006, 0.0015, -0.0010, 0.0020),  # concave-up everywhere
    (0.010, 0.006, -0.0015, 0.0010, -0.0020),  # concave-down everywhere (crowned)
    (-0.008, 0.012, 0.0020, 0.0030, -0.0025),  # saddle: both regimes across the field
    (0.020, -0.004, -0.0001, 0.0, -0.00005),  # so gently crowned that the crest lies beyond the far limit
    (0.0, 0.0, 0.0, 0.0, 0.0),
]


@pytest.mark.parametrize("coeffs", QUADS)
def test_quad_horizon_matches_brute_force_ray_march(coeffs):
    theta = np.linspace(-0.7, 0.7, 29)
    d_min, far = 0.15, 9.0
    got, r_max = es.quad_horizon(coeffs, theta, H, d_min, far)
    a, b, c, d, e = coeffs
    r = np.linspace(d_min, far, 400001)
    for k, th in enumerate(theta):
        slope = a * math.cos(th) + b * math.sin(th)
        curv = c * math.cos(th) ** 2 + 2 * d * math.sin(th) * math.cos(th) + e * math.sin(th) ** 2
        f = slope + 0.5 * curv * r - H / r
        j = int(np.argmax(f))
        assert got[k] == pytest.approx(f[j], abs=1e-10)
        assert r_max[k] == pytest.approx(r[j], abs=2e-3)
        if curv >= 0.0:  # concave-up or flat ray: the far limit
            assert r_max[k] == far and got[k] == pytest.approx(slope + 0.5 * curv * far - H / far, abs=1e-15)
        elif d_min < math.sqrt(2 * H / -curv) < far:  # concave-down: the crest
            assert r_max[k] == pytest.approx(math.sqrt(2 * H / -curv), rel=1e-12)
            assert got[k] == pytest.approx(slope - math.sqrt(2 * H * -curv), abs=1e-15)


def test_quad_horizon_clips_the_crest_to_the_interval():
    theta = np.array([0.0])
    # crest nearer than d_min (absurdly strong crown): maximum at d_min
    c = -2.0
    got, r_max = es.quad_horizon((0.0, 0.0, c, 0.0, 0.0), theta, H, 0.15, 9.0)
    assert r_max[0] == 0.15 and got[0] == pytest.approx(0.5 * c * 0.15 - H / 0.15)
    # crest beyond the far limit: maximum at the far limit
    c = -1e-5
    got, r_max = es.quad_horizon((0.0, 0.0, c, 0.0, 0.0), theta, H, 0.15, 9.0)
    assert r_max[0] == 9.0 and got[0] == pytest.approx(0.5 * c * 9.0 - H / 9.0)
    with pytest.raises(ValueError):
        es.quad_horizon((0, 0, 0, 0, 0), theta, 0.0, 0.15, 9.0)
    with pytest.raises(ValueError):
        es.quad_horizon((0, 0, 0, 0, 0), theta, H, 9.0, 9.0)


@pytest.mark.parametrize("coeffs", QUADS[:4])
def test_quad_horizon_derivatives(coeffs):
    """dE/dA = 1 and dE/dK = r_max / 2 (envelope theorem), checked by finite differences."""
    theta = np.linspace(-0.45, 0.45, 9)
    ct, st = np.cos(theta), np.sin(theta)
    base, r_max = es.quad_horizon(coeffs, theta, H, 0.15, 9.0)
    jac = np.stack([ct, st, 0.5 * r_max * ct * ct, r_max * st * ct, 0.5 * r_max * st * st], axis=1)
    for j in range(5):
        step = 1e-7 if j < 2 else 1e-9
        hi = np.array(coeffs, dtype=float)
        lo = hi.copy()
        hi[j] += step
        lo[j] -= step
        num = (es.quad_horizon(hi, theta, H, 0.15, 9.0)[0] - es.quad_horizon(lo, theta, H, 0.15, 9.0)[0]) / (2 * step)
        assert np.allclose(num, jac[:, j], rtol=2e-4, atol=1e-6)
    # second derivative used by the fit: r* / (4 |K|) at an interior crest, zero at the ends
    _, r_max, second = es._horizon_terms(np.array(coeffs, dtype=float), ct, st, H, 0.15, 9.0)
    curv = coeffs[2] * ct * ct + 2 * coeffs[3] * st * ct + coeffs[4] * st * st
    interior = (curv < 0) & (r_max > 0.15) & (r_max < 9.0)
    assert np.allclose(second[interior], 0.25 * r_max[interior] / -curv[interior])
    assert np.all(second[~interior] == 0.0)


@pytest.mark.parametrize("coeffs", QUADS[:3])
def test_quad_horizon_equals_the_sensor_ray_march_on_a_quadratic_green(coeffs):
    """The estimator's closed form against the simulator's ray-march of the true surface."""
    green = _quad_green(coeffs)
    cam = np.array([0.5, -1.0])
    patch = ph.QuadraticSurface(*coeffs).in_frame(cam, 0.3)  # putt frame: origin at the lens, x at azimuth 0.3
    theta = np.linspace(-0.45, 0.45, 13)
    far = 8.0
    truth = se.horizon_profile(green, cam, green.z(*cam) + H, 0.3 + theta, d_min=0.15, d_max=far)
    model, r_max = es.quad_horizon(patch.coeffs, theta, H, 0.15, far)
    assert np.allclose(truth.ratio, model, rtol=0.0, atol=2e-7)
    assert np.allclose(truth.distance, r_max, rtol=0.0, atol=0.05)


def test_horizon_far_limit():
    cfg = es.EstimatorConfig()
    assert es.horizon_far_limit(1.5, cfg) == 6.0
    assert es.horizon_far_limit(6.0, cfg) == 9.0
    assert es.horizon_far_limit(12.0, cfg) == 18.0
    assert es.horizon_far_limit(30.0, cfg) == 20.0


# --------------------------------------------------------------------------
# range fusion
# --------------------------------------------------------------------------


def test_range_fusion_is_inverse_variance():
    cfg = es.EstimatorConfig()
    fb = 657.0 * 0.0204
    low = math.atan(-0.005 / 9.0)
    meas = _meas(
        flag_disparity=fb / 9.4,
        flag_low_elev=low,
        flag_top_visible=True,
        flag_top_elev=math.atan(math.tan(low) + 2.13 / 8.9),
    )
    r = es.fuse_range(meas, cfg)
    assert r.stereo == pytest.approx(9.4) and r.mono == pytest.approx(8.9)
    assert r.sigma_stereo == pytest.approx(9.4**2 * 0.08 / fb)
    span = 2.13 / 8.9
    assert r.sigma_mono == pytest.approx(8.9 * math.sqrt(0.02**2 + 2 * (0.15 / 657.0 / span) ** 2))
    # stereo sigma is evaluated at the fused range (two passes)
    dist = 9.4
    sig_s = r.sigma_stereo
    for _ in range(2):
        ws, wm = 1 / sig_s**2, 1 / r.sigma_mono**2
        dist = (ws * 9.4 + wm * 8.9) / (ws + wm)
        sig = 1 / math.sqrt(ws + wm)
        sig_s = dist**2 * 0.08 / fb
    assert r.distance == pytest.approx(dist) and r.sigma == pytest.approx(sig)
    assert 8.9 < r.distance < 9.0 and r.sigma < min(r.sigma_stereo, r.sigma_mono)


def test_range_channels_fall_back_gracefully():
    cfg = es.EstimatorConfig()
    stereo_only = es.fuse_range(_meas(), cfg)
    assert stereo_only.distance == pytest.approx(5.0) and math.isnan(stereo_only.mono) and stereo_only.valid
    # hidden base: no monocular range (it would be biased long)
    hidden = _meas(flag_base_visible=False, flag_top_visible=True, flag_top_elev=0.2)
    assert math.isnan(es.fuse_range(hidden, cfg).mono)
    assert math.isfinite(es.fuse_range(hidden, dataclasses.replace(cfg, assume_base_visible=True)).mono)
    # disparity lost in the noise: monocular only, or nothing
    mono_only = es.fuse_range(_meas(flag_disparity=0.05, flag_top_visible=True, flag_top_elev=math.atan(2.13 / 9.0)), cfg)
    assert math.isnan(mono_only.stereo) and mono_only.distance == pytest.approx(mono_only.mono) and mono_only.valid
    assert not es.fuse_range(_meas(flag_disparity=-0.3), cfg).valid
    assert not es.fuse_range(_meas(flag_found=False), cfg).valid


# --------------------------------------------------------------------------
# recovery from noise-free measurements
# --------------------------------------------------------------------------

EXACT = dict(sink_mean=0.0, sigma_curv=10.0, sigma_slope_prior=10.0)  # true lens height, priors switched off


def _exact_config(green):
    """Estimator config whose assumed far limit equals the true one (the
    lens is at the green centre, so every ray ends at the model radius)."""
    far = green.model_radius
    return es.EstimatorConfig(horizon_l_factor=0.0, horizon_l_min=far, horizon_l_cap=far, **EXACT)


@pytest.mark.parametrize("slopes", [(0.012, -0.008), (-0.02, 0.005), (0.0, 0.0)])
def test_every_method_recovers_a_plane(slopes):
    surf = ph.PlaneSurface(*slopes)
    green = gr.green_from_surface(surf, collar_step=0.0, rough_step=0.0, stimp_ft=10.5, grain=ph.Grain(0.06, 2.0))
    ball, hole = np.zeros(2), np.array([4.0, 3.0])
    meas, truth = se.measure(green, ball, hole, QUIET, 3)
    true_patch = surf.in_frame(ball, truth.bearing).coeffs
    oracle = ph.solve_aim(surf, ball, hole, green.a_r, green.grain)
    for method in ("B0", "B1", "B2"):
        est = es.estimate(meas, method, _exact_config(green))
        assert np.allclose(est.patch, true_patch, rtol=0.0, atol=2e-8), method
        assert est.distance == pytest.approx(5.0, rel=1e-12)
        assert est.phi == pytest.approx(oracle.phi, abs=2e-6) and est.v0 == pytest.approx(oracle.v0, rel=2e-6)
        assert est.aim_source == es.AIM_FROM_PATCH and not est.base_hidden and not est.flag_missing
        # the aim line the display draws, checked in the world frame
        assert truth.heading + est.aim_azimuth_device == pytest.approx(truth.bearing + oracle.phi, abs=2e-6)
        assert est.slope_pct == pytest.approx(100 * math.hypot(*slopes), abs=1e-5)
        assert est.dz_hole == pytest.approx(surf.z(*hole) - surf.z(*ball), abs=1e-6)
        if math.hypot(*slopes) > 0:
            fall_world = math.atan2(-slopes[1], -slopes[0])
            assert math.cos(truth.heading + est.fall_line_azimuth_device - fall_world) == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize("coeffs", [QUADS[0], QUADS[2], (0.005, -0.012, 0.001, 0.002, -0.0015)])
def test_full_fusion_recovers_a_quadratic(coeffs):
    """Tilt + flag-base height + horizon determine all five coefficients."""
    surf = ph.QuadraticSurface(*coeffs)
    green = gr.green_from_surface(surf, collar_step=0.0, rough_step=0.0, stimp_ft=10.0, grain=ph.Grain(0.05, 1.0))
    ball, hole = np.zeros(2), np.array([4.0, 3.0])
    meas, truth = se.measure(green, ball, hole, QUIET, 3)
    assert meas.flag_base_visible
    true_patch = surf.in_frame(ball, truth.bearing).coeffs
    est = es.estimate(meas, "B2", _exact_config(green))
    assert est.fit.converged and est.fit.used_horizon and not est.poor_horizon
    assert np.allclose(est.patch, true_patch, rtol=0.0, atol=5e-7)
    assert est.fit.horizon_rms < 1e-3
    oracle = ph.solve_aim(surf, ball, hole, green.a_r, green.grain)
    assert est.phi == pytest.approx(oracle.phi, abs=1e-5) and est.v0 == pytest.approx(oracle.v0, rel=1e-5)
    # without the horizon only the along-line curvature c is observable (from the hole height)
    b1 = es.estimate(meas, "B1", _exact_config(green))
    assert np.allclose(b1.patch[:3], true_patch[:3], atol=5e-8) and np.all(b1.patch[3:] == 0.0)


def test_full_fusion_recovers_a_crowned_quadratic_with_hidden_base():
    """On a crowned line the base is hidden; the horizon (crest) residuals still pin the patch."""
    surf = ph.QuadraticSurface(0.010, 0.006, -0.0015, 0.0010, -0.0020)
    green = gr.green_from_surface(surf, collar_step=0.0, rough_step=0.0)
    ball, hole = np.zeros(2), np.array([4.0, 3.0])
    meas, truth = se.measure(green, ball, hole, QUIET, 3)
    assert not meas.flag_base_visible
    true_patch = surf.in_frame(ball, truth.bearing).coeffs
    est = es.estimate(meas, "B2", _exact_config(green))
    assert est.base_hidden and est.fit.converged
    assert np.allclose(est.patch, true_patch, rtol=0.0, atol=2e-6)
    # B1 has only the bound: its hole height is pulled down onto the sight line and stops there,
    # above the true hole height by the hidden length of the stick
    b1 = es.estimate(meas, "B1", _exact_config(green))
    bound = H + 5.0 * math.tan(meas.flag_low_elev)
    assert truth.dz_hole < bound and truth.hidden_height == pytest.approx(bound - truth.dz_hole, abs=1e-6)
    assert b1.dz_hole == pytest.approx(bound, abs=1e-6) and b1.dz_hole > truth.dz_hole
    assert b1.dz_hole < 5.0 * b1.patch[0]  # lower than the tilt plane alone would put it


@pytest.mark.parametrize("coeffs", [QUADS[0], QUADS[1], (0.005, -0.012, 0.001, 0.002, 0.0)])
def test_survey_recovers_the_slope_field_along_the_line(coeffs):
    """Three drops give a, b, c, d (z_yy is not observable from the line: stays at its prior, 0)."""
    surf = ph.QuadraticSurface(*coeffs)
    green = gr.green_from_surface(surf, collar_step=0.0, rough_step=0.0)
    ball, hole = np.array([-3.0, 1.0]), np.array([4.0, 3.5])
    drops = se.measure_survey(green, ball, hole, QUIET, 3)
    true_patch = surf.in_frame(ball, drops[0][1].bearing).coeffs
    est = es.estimate_survey([m for m, _ in drops], es.EstimatorConfig(**EXACT))
    assert est.fit.n_drops == 3
    assert np.allclose(est.fit.stations, se.survey_stations(drops[0][1].distance), atol=1e-9)
    assert np.allclose(est.patch[:4], true_patch[:4], rtol=0.0, atol=2e-8)
    assert est.patch[4] == 0.0
    two = es.estimate_survey([m for m, _ in drops[:2]], es.EstimatorConfig(**EXACT))
    assert two.fit.n_drops == 2 and np.allclose(two.patch[:4], true_patch[:4], rtol=0.0, atol=2e-8)


def test_priors_pull_unobserved_curvature_to_zero_and_shrink_little():
    surf = ph.QuadraticSurface(0.01, 0.006, 0.0015, -0.001, 0.002)
    green = gr.green_from_surface(surf, collar_step=0.0, rough_step=0.0)
    meas, truth = se.measure(green, np.zeros(2), np.array([4.0, 3.0]), QUIET, 3)
    true_patch = surf.in_frame(np.zeros(2), truth.bearing).coeffs
    est = es.estimate(meas, "B1", es.EstimatorConfig(sink_mean=0.0))  # default priors
    assert np.all(est.patch[3:] == 0.0)
    assert est.patch[1] == pytest.approx(true_patch[1], rel=0.005)  # weak prior on b: < 0.5 % shrink
    assert est.dz_hole == pytest.approx(truth.dz_hole, abs=3e-4)


# --------------------------------------------------------------------------
# the fit
# --------------------------------------------------------------------------


def test_hidden_base_is_a_one_sided_bound():
    low = math.atan(0.004)  # sight line to the crest: the hole is below 0.75e-3-corrected h + 5 * 0.004
    bound = (H - 0.75e-3) + 5.0 * 0.004
    # tilt says the hole is well below the bound: the bound is idle, the fit is the tilt plane
    idle = es.estimate(_meas(tilt=np.array([-0.01, 0.003]), flag_base_visible=False, flag_low_elev=low), "B1")
    assert idle.base_hidden and idle.dz_hole < bound
    assert idle.patch[0] == pytest.approx(-0.01, rel=0.01) and abs(idle.patch[2]) < 1e-9
    # tilt says the hole is above the bound: the fit is pulled down onto it
    active = es.estimate(_meas(tilt=np.array([0.02, 0.003]), flag_base_visible=False, flag_low_elev=low), "B1")
    assert active.dz_hole == pytest.approx(bound, abs=3e-3) and active.dz_hole < 5.0 * 0.02 - 0.05
    assert active.patch[2] < 0.0  # it does so by crowning the line
    # the same elevation with a visible base is an equality
    equal = es.estimate(_meas(tilt=np.array([-0.01, 0.003]), flag_base_visible=True, flag_low_elev=low), "B1")
    assert equal.dz_hole == pytest.approx(bound, abs=3e-4) and not equal.base_hidden
    # a device that cannot tell treats the bound as an equality
    blind = es.estimate(
        _meas(tilt=np.array([-0.01, 0.003]), flag_base_visible=False, flag_low_elev=low),
        "B1", es.EstimatorConfig(assume_base_visible=True),
    )
    assert blind.dz_hole == pytest.approx(equal.dz_hole) and not blind.base_hidden
    # without the flag base the hole height comes from the tilt alone
    off = es.estimate(_meas(tilt=np.array([0.02, 0.003]), flag_low_elev=low), "B1", es.EstimatorConfig(use_flag_base=False))
    assert off.dz_hole == pytest.approx(5.0 * 0.02, rel=0.01)


def test_fit_converges_to_a_stationary_point_on_realistic_reads():
    cfg = es.EstimatorConfig()
    n_checked = 0
    for cls in gr.GREEN_CLASSES:
        for seed in range(6):
            sc = gr.make_scenario(cls, (3.0, 6.0, 12.0)[seed % 3], seed)
            meas, _ = se.measure(sc.green, sc.ball_xy, sc.hole_xy, se.SensorParams(), seed)
            if not meas.flag_found:
                continue
            for method in ("B1", "B2"):
                fit = es.fit_patch(meas, method, cfg)
                assert fit.converged and fit.n_iter < cfg.lm_max_iter
                assert np.all(np.isfinite(fit.coeffs)) and np.all(np.linalg.eigvalsh(fit.cov) > 0.0)
                n_checked += 1
    assert n_checked >= 40


def test_fit_minimises_the_robust_cost():
    """No small perturbation of the solution lowers the Huber MAP cost (B2, realistic horizon)."""
    sc = gr.make_scenario("undulating", 6.0, 3)
    meas, _ = se.measure(sc.green, sc.ball_xy, sc.hole_xy, se.SensorParams(), 1)
    cfg = es.EstimatorConfig()
    captured = {}
    original = es._levenberg_marquardt

    def spy(problem, x0, config):
        out = original(problem, x0, config)
        captured["problem"], captured["x"], captured["cost"] = problem, out[0], out[4]
        return out

    es._levenberg_marquardt = spy
    try:
        fit = es.fit_patch(meas, "B2", cfg)
    finally:
        es._levenberg_marquardt = original
    problem, x, cost = captured["problem"], captured["x"], captured["cost"]
    assert fit.used_horizon and cost == pytest.approx(problem.cost(x))
    rng = np.random.default_rng(0)
    for scale in (1e-3, 1e-5):
        for _ in range(40):
            trial = x + scale * es._SCALE * rng.standard_normal(7)
            assert problem.cost(trial) >= cost - 1e-12
    # and it is far better than the starting point (the tilt plane)
    x0 = np.zeros(7)
    x0[:2] = es._rotate_to(meas.tilt, meas.flag_bearing)
    assert cost < problem.cost(x0)


def test_huber_loss_limits_the_pull_of_outlying_horizon_samples():
    green = _quad_green((0.01, -0.006, 0.0, 0.0, 0.0))
    meas, truth = se.measure(green, np.zeros(2), np.array([5.0, 0.0]), QUIET, 2)
    cfg = _exact_config(green)
    clean = es.estimate(meas, "B2", cfg)
    elev = meas.horizon_elev.copy()
    elev[3:9] += 0.05  # a mound in part of the field: 50 mrad, six samples
    spoiled = dataclasses.replace(meas, horizon_elev=elev)
    robust = es.estimate(spoiled, "B2", cfg)
    naive = es.estimate(spoiled, "B2", dataclasses.replace(cfg, huber_k=1e9))
    err_robust = np.abs(robust.patch[:2] - clean.patch[:2]).max()
    err_naive = np.abs(naive.patch[:2] - clean.patch[:2]).max()
    assert err_robust < 2e-4 and err_naive > 5 * err_robust
    assert robust.fit.horizon_rms > 1.0


def test_spin_read_tightens_the_tilt_and_raises_confidence():
    single = es.estimate(_meas(tilt=np.array([0.0, 0.01])), "B1")
    spun = es.estimate(_meas(tilt=np.array([0.0, 0.01]), tilt_reads=2), "B1")
    cfg = es.EstimatorConfig()
    assert single.patch_cov[1, 1] == pytest.approx(cfg.sigma_seat**2 + cfg.sigma_tilt_bias**2 + cfg.sigma_gravity**2, rel=0.01)
    assert spun.patch_cov[1, 1] == pytest.approx(0.5 * (cfg.sigma_seat**2 + cfg.sigma_gravity**2), rel=0.01)
    assert spun.confidence > single.confidence
    assert spun.phi == pytest.approx(single.phi, rel=5e-3)  # same reading; only the weak-prior shrink differs


# --------------------------------------------------------------------------
# outputs
# --------------------------------------------------------------------------


def test_cross_slope_gives_the_planar_break():
    for slope in (0.005, 0.015):
        est = es.estimate(_meas(tilt=np.array([0.0, slope])), "B0")
        a_r = ph.stimp_to_decel(10.0)
        theory = ph.planar_break_angle_paced(slope, a_r, 5.0, 0.30)
        assert est.phi == pytest.approx(theory, rel=0.03) and est.phi > 0.0  # ground rises to the left: aim left
        assert est.break_m == pytest.approx(5.0 * math.tan(est.phi))
        assert est.break_cups == pytest.approx(est.break_m / 0.10795)
        assert est.plays_like == pytest.approx(est.v0**2 / (2 * a_r))
        assert est.plays_like == pytest.approx(5.3, rel=0.01)  # flat along the line: D + past
        assert est.slope_pct == pytest.approx(100 * slope)
        assert est.fall_line_azimuth == pytest.approx(-math.pi / 2)  # falls to the right
        mirrored = es.estimate(_meas(tilt=np.array([0.0, -slope])), "B0")
        assert mirrored.phi == pytest.approx(-est.phi, abs=1e-9) and mirrored.v0 == pytest.approx(est.v0, rel=1e-9)


def test_uphill_plays_longer_and_downhill_shorter():
    up = es.estimate(_meas(tilt=np.array([0.02, 0.0]), flag_low_elev=math.atan(0.02 - (H - 0.75e-3) / 5.0)), "B1")
    down = es.estimate(_meas(tilt=np.array([-0.02, 0.0]), flag_low_elev=math.atan(-0.02 - (H - 0.75e-3) / 5.0)), "B1")
    assert up.plays_like > 5.3 + 0.5 and down.plays_like < 5.3 - 0.5
    assert up.dz_hole == pytest.approx(0.1, abs=1e-3) and down.dz_hole == pytest.approx(-0.1, abs=1e-3)
    assert abs(up.phi) < 1e-6 and abs(down.phi) < 1e-6


def test_straight_ignores_the_slope():
    est = es.estimate(_meas(tilt=np.array([0.01, 0.02]), flag_bearing=0.1), "STRAIGHT")
    assert est.phi == 0.0 and est.aim_azimuth_device == pytest.approx(0.1) and est.confidence == 0.0
    assert est.v0 == pytest.approx(math.sqrt(2 * ph.stimp_to_decel(10.0) * 5.3)) and est.fit is None
    assert est.aim_source == es.AIM_STRAIGHT


def test_measured_bearing_defines_the_putt_frame():
    """Turning the device does not change the read: tilt and grain are rotated by the flag bearing."""
    slope_putt = np.array([0.004, 0.012])
    ref = es.estimate(_meas(tilt=slope_putt, grain_kappa=0.08, grain_azimuth=1.0), "B1")
    for beta in (-0.4, 0.25):
        cb, sb = math.cos(beta), math.sin(beta)
        tilt_dev = np.array([slope_putt[0] * cb - slope_putt[1] * sb, slope_putt[0] * sb + slope_putt[1] * cb])
        est = es.estimate(_meas(tilt=tilt_dev, flag_bearing=beta, grain_kappa=0.08, grain_azimuth=1.0 + beta), "B1")
        assert est.phi == pytest.approx(ref.phi, abs=1e-9) and est.v0 == pytest.approx(ref.v0, rel=1e-9)
        assert est.aim_azimuth_device == pytest.approx(beta + ref.phi, abs=1e-9)
        assert np.allclose(est.patch, ref.patch, atol=1e-12) and np.allclose(est.grain, ref.grain, atol=1e-12)


def test_grain_and_stimp_inputs():
    with_grain = es.estimate(_meas(grain_kappa=0.1, grain_azimuth=math.pi / 2), "B0")  # pushes left
    assert with_grain.phi < -0.01 and np.allclose(with_grain.grain, [0.0, 0.1], atol=1e-12)
    no_grain = es.estimate(_meas(grain_kappa=0.1, grain_azimuth=math.pi / 2), "B0", es.EstimatorConfig(use_grain=False))
    assert abs(no_grain.phi) < 1e-9 and np.all(no_grain.grain == 0.0)
    # the entered green speed sets the pace and scales the break
    slow = es.estimate(_meas(tilt=np.array([0.0, 0.01]), stimp_ft=8.0), "B0")
    fast = es.estimate(_meas(tilt=np.array([0.0, 0.01]), stimp_ft=12.0), "B0")
    assert slow.v0 > fast.v0 and fast.phi > slow.phi
    assert slow.a_r == pytest.approx(ph.stimp_to_decel(8.0)) and slow.stimp_ft == 8.0
    assert es.estimate(_meas(stimp_ft=40.0), "B0").stimp_ft == es.EstimatorConfig().stimp_max


def test_confidence_score_behaviour():
    confs = []
    for dist in (1.5, 3.0, 6.0, 12.0):
        meas = _meas(flag_disparity=657.0 * 0.0204 / dist, flag_low_elev=math.atan(-(H - 0.75e-3) / dist))
        est = es.estimate(meas, "B1")
        assert 0.0 <= est.confidence <= 1.0
        confs.append(est.confidence)
        cfg = es.EstimatorConfig()
        sigma_cross = math.sqrt(est.patch_cov[1, 1] + dist * est.patch_cov[1, 3] + 0.25 * dist**2 * est.patch_cov[3, 3])
        assert est.cross_slope_sigma == pytest.approx(sigma_cross)
        sigma_lat = dist * 0.5 * ph.ROLL_FACTOR * ph.G * sigma_cross / est.a_r * es._pace_factor(dist, cfg.past)
        assert est.confidence == pytest.approx(math.erf(ph.HOLE_R / (math.sqrt(2) * sigma_lat)))
    assert confs == sorted(confs, reverse=True) and confs[0] > 0.7 and confs[-1] < 0.1
    visible = es.estimate(_meas(), "B1")
    hidden = es.estimate(_meas(flag_base_visible=False), "B1")
    assert hidden.confidence == pytest.approx(0.8 * visible.confidence, rel=1e-6)


# --------------------------------------------------------------------------
# fallbacks
# --------------------------------------------------------------------------


def test_flag_not_found_falls_back_to_tilt_only_along_the_visor_axis():
    nan = math.nan
    lost = dict(flag_found=False, flag_bearing=nan, flag_disparity=nan, flag_low_elev=nan, flag_base_visible=False)
    dialled = _meas(tilt=np.array([0.004, 0.012]), user_distance=7.0, **lost)
    for method in ("B0", "B1", "B2"):
        est = es.estimate(dialled, method)
        assert est.flag_missing and est.bearing == 0.0 and est.distance == 7.0 and math.isnan(est.distance_sigma)
        assert np.allclose(est.patch, [0.004, 0.012, 0, 0, 0])
        assert est.aim_azimuth_device == pytest.approx(est.phi) and est.phi > 0.0
    found = es.estimate(_meas(tilt=np.array([0.004, 0.012]), flag_disparity=657.0 * 0.0204 / 7.0), "B0")
    assert est.confidence < 0.5 * found.confidence  # low confidence is flagged
    # no dialled distance either: the default distance
    assert es.estimate(_meas(**lost), "B1").distance == es.EstimatorConfig().default_distance
    assert es.estimate(_meas(**lost), "STRAIGHT").flag_missing


def test_unsolvable_patch_falls_back_and_says_so():
    # a 9 % downhill tilt reading on a fast green: the ball cannot be stopped on the fitted patch
    steep = _meas(tilt=np.array([-0.09, 0.02]), stimp_ft=13.0, flag_low_elev=math.atan(-0.01))
    est = es.estimate(steep, "B1")
    assert math.isfinite(est.phi) and math.isfinite(est.v0) and est.v0 > 0.0
    usable = est.solve_status in (int(ph.SolveStatus.OK), int(ph.SolveStatus.PACE_LIMITED))
    assert (est.aim_source == es.AIM_FROM_PATCH) == (usable and est.aim_source == es.AIM_FROM_PATCH)
    hopeless = _meas(tilt=np.array([-0.2, 0.05]), stimp_ft=13.0, flag_base_visible=False, flag_low_elev=0.5)
    est = es.estimate(hopeless, "B0")
    assert est.aim_source != es.AIM_FROM_PATCH
    assert math.isfinite(est.phi) and math.isfinite(est.v0) and est.v0 > 0.0
    ok = es.estimate(_meas(tilt=np.array([0.0, 0.01])), "B0")
    assert est.confidence < ok.confidence


def test_survey_ignores_a_drop_that_did_not_find_the_flag():
    nan = math.nan
    ball = _meas(tilt=np.array([0.0, 0.010]))
    mid = _meas(tilt=np.array([0.0, 0.004]), flag_disparity=657.0 * 0.0204 / 2.5,
                flag_low_elev=math.atan(-(H - 0.75e-3) / 2.5))
    blind = _meas(tilt=np.array([0.3, 0.3]), flag_found=False, flag_bearing=nan, flag_disparity=nan, flag_low_elev=nan)
    both = es.estimate_survey([ball, mid])
    with_blind = es.estimate_survey([ball, blind, mid])
    assert both.fit.n_drops == 2 and with_blind.fit.n_drops == 2
    assert both.fit.stations == pytest.approx((0.0, 2.5))
    assert np.allclose(with_blind.patch, both.patch) and with_blind.phi == both.phi
    # the cross slope falls along the line: d < 0, and the read lies between the two local ones
    assert both.patch[3] < 0.0
    lo = es.estimate(_meas(tilt=np.array([0.0, 0.004])), "B1").phi
    hi = es.estimate(ball, "B1").phi
    assert lo < both.phi < hi


# --------------------------------------------------------------------------
# API and truth leakage
# --------------------------------------------------------------------------


def test_batch_equals_single_calls():
    sc = gr.make_scenario("undulating", 6.0, 3)
    reads = [se.measure(sc.green, sc.ball_xy, sc.hole_xy, se.SensorParams(), s)[0] for s in range(12)]
    for method in es.METHODS:
        batch = es.estimate_batch(reads, method)
        for meas, b in zip(reads, batch):
            single = es.estimate(meas, method)
            assert single.phi == b.phi and single.v0 == b.v0 and single.confidence == b.confidence
            assert np.array_equal(single.patch, b.patch)
    assert es.estimate_batch([], "B1") == []
    with pytest.raises(ValueError):
        es.estimate(reads[0], "B7")


def test_estimator_is_deterministic():
    sc = gr.make_scenario("tiered", 9.0, 4)
    meas, _ = se.measure(sc.green, sc.ball_xy, sc.hole_xy, se.SensorParams(), 2)
    a = es.estimate(meas, "B2")
    b = es.estimate(Measurements.from_dict(meas.to_dict()), "B2")
    assert a.phi == b.phi and a.v0 == b.v0 and np.array_equal(a.patch, b.patch) and a.confidence == b.confidence


def test_estimator_module_cannot_see_the_true_green():
    """Structural check: the estimator imports only the Measurements record and the physics solver."""
    source = pathlib.Path(es.__file__).read_text()
    allowed_local = {"measurements", "physics"}
    allowed_external = {"__future__", "math", "dataclasses", "typing", "numpy"}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            if node.level > 0:
                assert node.module in allowed_local, f"estimator imports .{node.module}"
            else:
                assert node.module.split(".")[0] in allowed_external, f"estimator imports {node.module}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] in allowed_external, f"estimator imports {alias.name}"
    # nothing from the truth side is reachable through the module namespace
    forbidden = {"Green", "PuttScenario", "MeasurementTruth", "HorizonTruth", "greens", "sensors", "montecarlo", "make_green"}
    assert forbidden.isdisjoint(vars(es))
    for word in ("greens", "MeasurementTruth", "make_green", "PuttScenario"):
        assert word not in source
    # the measurements module itself is free of truth-side imports
    import greenline_sim.measurements as mm

    for node in ast.walk(ast.parse(pathlib.Path(mm.__file__).read_text())):
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0 and node.module in ("__future__", "dataclasses")
        elif isinstance(node, ast.Import):
            assert all(alias.name in ("math", "numpy") for alias in node.names)


def test_estimator_api_takes_only_measurements():
    params = list(inspect.signature(es.estimate).parameters)
    assert params == ["meas", "method", "config"]
    assert list(inspect.signature(es.estimate_survey).parameters) == ["drops", "config", "method"]
    assert list(inspect.signature(es.estimate_batch).parameters) == ["items", "method", "config"]
    assert list(inspect.signature(es.fit_patch).parameters) == ["drops", "method", "config", "start"]
    # the config holds plain nominal numbers only
    for f in dataclasses.fields(es.EstimatorConfig):
        assert isinstance(getattr(es.EstimatorConfig(), f.name), (int, float, bool)), f.name
    # the Measurements record carries no truth: only scalars and three small arrays
    names = {f.name for f in dataclasses.fields(Measurements)}
    assert names == {
        "f_px", "baseline", "h_cam", "tilt", "tilt_reads", "flag_found", "flag_bearing", "flag_disparity",
        "flag_low_elev", "flag_base_visible", "flag_top_visible", "flag_top_elev", "stick_height_est",
        "stick_height_rel_sigma", "horizon_az", "horizon_elev", "grain_kappa", "grain_azimuth", "stimp_ft",
        "user_distance",
    }
    sc = gr.make_scenario("gentle", 6.0, 1)
    meas, truth = se.measure(sc.green, sc.ball_xy, sc.hole_xy, se.SensorParams(), 0)
    for bad in (truth, sc, sc.green, (meas, truth), None):
        with pytest.raises(TypeError):
            es.estimate(bad)
    with pytest.raises(TypeError):
        es.estimate_survey([meas, truth])
    with pytest.raises(TypeError):
        es.estimate_batch([[]])


def test_estimate_depends_on_the_green_only_through_the_measurements():
    """Two different greens that yield the same Measurements get the same estimate."""
    sc_a = gr.make_scenario("gentle", 6.0, 1)
    sc_b = gr.make_scenario("tiered", 6.0, 9)
    meas_a, _ = se.measure(sc_a.green, sc_a.ball_xy, sc_a.hole_xy, se.SensorParams(), 0)
    meas_b, _ = se.measure(sc_b.green, sc_b.ball_xy, sc_b.hole_xy, se.SensorParams(), 0)
    assert meas_a.to_dict() != meas_b.to_dict()
    clone = Measurements.from_dict(meas_a.to_dict())  # carries nothing but the numbers
    for method in ("B1", "B2"):
        one, two = es.estimate(meas_a, method), es.estimate(clone, method)
        assert one.phi == two.phi and one.v0 == two.v0 and np.array_equal(one.patch_cov, two.patch_cov)
