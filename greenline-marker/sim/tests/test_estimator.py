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
        baseline=0.0200,
        h_cam=H,
        tilt=np.array([0.0, 0.0]),
        tilt_reads=1,
        flag_found=True,
        flag_bearing=0.0,
        flag_disparity=657.0 * 0.0200 / 5.0,
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
    fb = 657.0 * 0.0200
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

# true lens height, priors switched off, grain reading used (the sensor ships disabled: default off)
EXACT = dict(sink_mean=0.0, sigma_curv=10.0, sigma_slope_prior=10.0, use_grain=True)


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
    """On a crowned line the base is hidden.  The JOINT fit pins the whole
    patch from the crest residuals (noise-free data, exact model).  The
    default anchored fit does not: it keeps the Quick Read's along-line
    profile, which on a hidden base is only bounded, and adds the twist."""
    surf = ph.QuadraticSurface(0.010, 0.006, -0.0015, 0.0010, -0.0020)
    green = gr.green_from_surface(surf, collar_step=0.0, rough_step=0.0)
    ball, hole = np.zeros(2), np.array([4.0, 3.0])
    meas, truth = se.measure(green, ball, hole, QUIET, 3)
    assert not meas.flag_base_visible
    true_patch = surf.in_frame(ball, truth.bearing).coeffs
    joint = es.estimate(meas, "B2", dataclasses.replace(_exact_config(green), horizon_joint=True))
    assert joint.base_hidden and joint.fit.converged
    assert np.allclose(joint.patch, true_patch, rtol=0.0, atol=2e-6)
    # B1 has only the bound: its hole height is pulled down onto the sight line and stops there,
    # above the true hole height by the hidden length of the stick
    b1 = es.estimate(meas, "B1", _exact_config(green))
    est = es.estimate(meas, "B2", _exact_config(green))
    assert est.base_hidden and est.fit.converged
    assert np.array_equal(est.patch[:3], b1.patch[:3]) and np.allclose(est.patch[:2], true_patch[:2], atol=2e-8)
    assert est.patch[2] != pytest.approx(true_patch[2], rel=0.02)  # c is the Quick Read's, not the truth
    assert est.patch[3] == pytest.approx(true_patch[3], abs=2e-5)  # the twist is still recovered
    assert est.dz_hole == b1.dz_hole
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


def _realistic_reads(n_seeds, fringes=("realistic",), distances=(3.0, 6.0, 12.0)):
    """Camera reads (flag found) on generated greens: (label, Measurements)."""
    out = []
    for cls in gr.GREEN_CLASSES:
        for seed in range(n_seeds):
            sc = gr.make_scenario(cls, distances[seed % len(distances)], seed)
            for fringe in fringes:
                green = {"realistic": sc.green, "no_fringe": sc.green.without_fringe(),
                         "mounded": sc.green.with_mounded_surrounds(seed=seed)}[fringe]
                meas, _ = se.measure(green, sc.ball_xy, sc.hole_xy, se.SensorParams(), seed)
                if meas.flag_found:
                    out.append((f"{cls}/{seed}/{fringe}", meas))
    return out


def _random_start(rng, fit):
    start = np.zeros(7)
    start[:2] = fit.coeffs[:2] + rng.normal(0.0, 0.01, 2)
    start[2:5] = rng.normal(0.0, 0.005, 3)
    start[5:] = rng.normal(0.0, 0.002, 2)
    return start


def test_fit_kernel_gradient_and_solver():
    """The analytic Jacobian of the residual kernel matches finite
    differences, and the Cholesky solver matches numpy."""
    sc = gr.make_scenario("undulating", 6.0, 3)
    meas, _ = se.measure(sc.green, sc.ball_xy, sc.hole_xy, se.SensorParams(), 1)
    cfg = es.EstimatorConfig()
    problem = es._Problem(6.0, np.array([0.05, 0.05, 0.004, 0.004, 0.004, 4.3e-4, 4.3e-4]), cfg.huber_k)
    problem.add_linear([1.0, 0, 0, 0, 0, 0, 0], 0.01, 2.7e-3)
    problem.add_linear([0, 1.0, 0, 0, 0, 0, 0], -0.004, 2.7e-3)
    problem.add_linear([6.0, 0, 18.0, 0, 0, 0, 0], 0.05, 3e-3, one_sided=True)
    problem.set_horizon(meas.horizon_az, np.tan(meas.horizon_elev), 1e-3, 0.00485, 0.15, 9.0)
    rng = np.random.default_rng(4)
    for _ in range(20):
        x = np.array([0.01, -0.004, 0.0, 0.0, 0.0, 0.0, 0.0]) + es._SCALE * rng.normal(0.0, 1.0, 7)
        grad = problem.gradient(x)
        num = np.empty(7)
        for j in range(7):
            step = np.zeros(7)
            step[j] = 1e-7 * es._SCALE[j] / 1e-3
            num[j] = (problem.cost(x + step) - problem.cost(x - step)) / (2.0 * step[j])
        assert np.allclose(grad, num, rtol=2e-5, atol=1e-3 * np.abs(grad).max())
    # Cholesky solve against numpy, and its refusal of an indefinite matrix
    a = rng.normal(size=(7, 7))
    spd = a @ a.T + 7.0 * np.eye(7)
    rhs = rng.normal(size=7)
    out = np.empty(7)
    assert es._chol_solve(spd.copy(), rhs, 7, out) and np.allclose(out, np.linalg.solve(spd, rhs), rtol=1e-12, atol=1e-12)
    indefinite = spd.copy()
    indefinite[3, 3] = -1.0
    assert not es._chol_solve(indefinite, rhs, 7, out)


def test_quick_read_fit_is_convex_and_start_independent():
    """Without horizon rows the cost is convex: every start gives the same
    minimum (B1, hidden and visible bases, and Survey fits)."""
    rng = np.random.default_rng(0)
    cfg = es.EstimatorConfig()
    n = 0
    for label, meas in _realistic_reads(4):
        ref = es.fit_patch(meas, "B1", cfg)
        assert ref.converged and ref.n_starts == 1 and ref.cost == ref.cost_first_start
        for _ in range(8):
            alt = es.fit_patch(meas, "B1", cfg, start=_random_start(rng, ref))
            assert alt.cost == pytest.approx(ref.cost, rel=1e-9, abs=1e-12), label
            assert np.allclose(alt.coeffs / es._SCALE[:5], ref.coeffs / es._SCALE[:5], atol=1e-6), label
        n += 1
    assert n >= 12


def test_anchored_horizon_fit_keeps_the_quick_read_and_finds_the_lowest_minimum():
    """B2 (anchored): a, b, c are exactly the Quick-Read values, and no other
    start finds a lower minimum of the conditional cost.  This is the test
    that fails when a lower minimum exists: 40 random starts per read, three
    silhouette geometries."""
    rng = np.random.default_rng(1)
    cfg = es.EstimatorConfig()
    n = n_other_start_won = 0
    for label, meas in _realistic_reads(5, fringes=("realistic", "no_fringe", "mounded")):
        b1 = es.fit_patch(meas, "B1", cfg)
        b2 = es.fit_patch(meas, "B2", cfg)
        assert b2.used_horizon and b2.n_starts == 5 and b2.converged
        # the horizon cannot move the slopes at the ball nor the along-line curvature
        assert np.array_equal(b2.coeffs[:3], b1.coeffs[:3]), label
        assert b2.cost <= b2.cost_first_start
        n_other_start_won += b2.cost < b2.cost_first_start * (1.0 - 1e-6)
        for _ in range(40):
            alt = es.fit_patch(meas, "B2", cfg, start=_random_start(rng, b2))
            assert alt.cost >= b2.cost * (1.0 - 1e-6) - 1e-9, f"{label}: a start found a lower minimum"
            assert np.array_equal(alt.coeffs[:3], b1.coeffs[:3])
        n += 1
    assert n >= 50
    # the conditional problem is very nearly unimodal: the first start is almost always the lowest
    assert n_other_start_won <= 0.05 * n
    # the comparison form with c free: 9 starts, the hole height is no longer respected
    free_c = es.fit_patch(meas, "B2", es.EstimatorConfig(horizon_free_c=True))
    assert free_c.n_starts == 9 and np.array_equal(free_c.coeffs[:2], b1.coeffs[:2]) and free_c.coeffs[2] != b1.coeffs[2]


def test_joint_horizon_fit_has_many_local_minima():
    """The joint fit (comparison only) is NOT start-independent: a single
    run from the tilt plane misses the lowest minimum in a sizeable share of
    realistic reads, and its 25-start search is never worse than one start.
    (This is why B2 is not the joint fit; the report shows both.)"""
    joint = es.EstimatorConfig(horizon_joint=True)
    single = dataclasses.replace(joint, multi_start=False)
    n = n_lower = 0
    slope_shift = []
    for label, meas in _realistic_reads(8, fringes=("realistic", "mounded")):
        one = es.fit_patch(meas, "B2", single)
        many = es.fit_patch(meas, "B2", joint)
        assert one.n_starts == 1 and many.n_starts == 25
        assert many.cost_first_start == pytest.approx(one.cost, rel=1e-12)
        assert many.cost <= one.cost * (1.0 + 1e-12)
        n += 1
        n_lower += many.cost < one.cost * (1.0 - 1e-6)
        b1 = es.fit_patch(meas, "B1")
        slope_shift.append(abs(many.coeffs[0] - b1.coeffs[0]))
    assert n >= 50 and n_lower >= 0.10 * n
    # ... and its lowest minimum lets the horizon overrule the puck's along-line tilt
    assert np.sqrt(np.mean(np.square(slope_shift))) > 3 * es._tilt_sigma(meas, joint)


def test_displayed_slope_at_the_ball_is_the_tilt_reading():
    sc = gr.make_scenario("undulating", 9.0, 2)
    meas, _ = se.measure(sc.green.with_mounded_surrounds(seed=1), sc.ball_xy, sc.hole_xy, se.SensorParams(), 7)
    assert meas.flag_found
    a_t, b_t = es._rotate_to(meas.tilt, meas.flag_bearing)
    for method, cfg in (("B0", es.EstimatorConfig()), ("B1", es.EstimatorConfig()), ("B2", es.EstimatorConfig()),
                        ("B2", es.EstimatorConfig(horizon_joint=True))):
        est = es.estimate(meas, method, cfg)
        assert np.allclose(est.fit.tilt_slopes, [a_t, b_t])
        assert est.slope_pct == pytest.approx(100.0 * math.hypot(a_t, b_t))
        assert est.fall_line_azimuth == pytest.approx(math.atan2(-b_t, -a_t))
    # the joint fit moved the patch slope away from the reading; the display did not follow
    joint = es.estimate(meas, "B2", es.EstimatorConfig(horizon_joint=True))
    assert abs(joint.patch[0] - a_t) > 1e-3


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
    # a, b and c are anchored on the Quick Read; the mound can only reach d and e
    assert np.array_equal(robust.patch[:3], clean.patch[:3]) and np.array_equal(naive.patch[:3], clean.patch[:3])
    err_robust = np.abs(robust.patch[3:] - clean.patch[3:])
    err_naive = np.abs(naive.patch[3:] - clean.patch[3:])
    # d stays put; e (seen only through sin^2 <= 0.19, and with its prior switched off here) moves a little
    assert err_robust[0] < 2e-4 and err_robust.max() < 1e-3
    assert np.all(err_naive > 5 * err_robust)
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
    grain_on = es.EstimatorConfig(use_grain=True)
    ref = es.estimate(_meas(tilt=slope_putt, grain_kappa=0.08, grain_azimuth=1.0), "B1", grain_on)
    assert np.hypot(*ref.grain) == pytest.approx(0.08)
    for beta in (-0.4, 0.25):
        cb, sb = math.cos(beta), math.sin(beta)
        tilt_dev = np.array([slope_putt[0] * cb - slope_putt[1] * sb, slope_putt[0] * sb + slope_putt[1] * cb])
        est = es.estimate(_meas(tilt=tilt_dev, flag_bearing=beta, grain_kappa=0.08, grain_azimuth=1.0 + beta), "B1", grain_on)
        assert est.phi == pytest.approx(ref.phi, abs=1e-9) and est.v0 == pytest.approx(ref.v0, rel=1e-9)
        assert est.aim_azimuth_device == pytest.approx(beta + ref.phi, abs=1e-9)
        assert np.allclose(est.patch, ref.patch, atol=1e-12) and np.allclose(est.grain, ref.grain, atol=1e-12)


def test_grain_and_stimp_inputs():
    # the grain sensor ships disabled: by default the reading is ignored
    assert es.EstimatorConfig().use_grain is False
    no_grain = es.estimate(_meas(grain_kappa=0.1, grain_azimuth=math.pi / 2), "B0")
    assert abs(no_grain.phi) < 1e-9 and np.all(no_grain.grain == 0.0)
    with_grain = es.estimate(_meas(grain_kappa=0.1, grain_azimuth=math.pi / 2), "B0", es.EstimatorConfig(use_grain=True))
    assert with_grain.phi < -0.01 and np.allclose(with_grain.grain, [0.0, 0.1], atol=1e-12)  # pushes left: aim right
    # not knowing the grain is itself an uncertainty: with the reading in use the score is higher on a grainless green
    assert es.estimate(_meas(), "B0", es.EstimatorConfig(use_grain=True)).confidence > es.estimate(_meas(), "B0").confidence
    # the entered green speed sets the pace and scales the break
    slow = es.estimate(_meas(tilt=np.array([0.0, 0.01]), stimp_ft=8.0), "B0")
    fast = es.estimate(_meas(tilt=np.array([0.0, 0.01]), stimp_ft=12.0), "B0")
    assert slow.v0 > fast.v0 and fast.phi > slow.phi
    assert slow.a_r == pytest.approx(ph.stimp_to_decel(8.0)) and slow.stimp_ft == 8.0
    assert es.estimate(_meas(stimp_ft=40.0), "B0").stimp_ft == es.EstimatorConfig().stimp_max


def test_confidence_score_behaviour():
    cfg = es.EstimatorConfig()
    kf = ph.ROLL_FACTOR * ph.G
    confs = []
    for dist in (1.5, 3.0, 6.0, 12.0):
        meas = _meas(flag_disparity=657.0 * 0.0200 / dist, flag_low_elev=math.atan(-(H - 0.75e-3) / dist))
        est = es.estimate(meas, "B1")
        assert 0.0 <= est.confidence <= 1.0
        confs.append(est.confidence)
        # one placement: reading error and the representativeness allowance in quadrature
        sigma_tilt = es._tilt_sigma(meas, cfg)
        sigma_twist = cfg.conf_twist_sigma / math.sqrt(1.0 + (dist / cfg.conf_twist_length) ** 2)
        prior_shrink = 1.0 / math.sqrt(1.0 + (sigma_tilt / cfg.sigma_slope_prior) ** 2)
        sigma_cross = math.hypot(sigma_tilt * prior_shrink, 0.5 * dist * sigma_twist)
        assert est.cross_slope_sigma == pytest.approx(sigma_cross, rel=1e-6)
        assert est.cross_slope_sigma == pytest.approx(est.fit.cross_sigma_read)
        sigma_phi = 0.5 * es._pace_factor(dist, cfg.past) * math.hypot(kf * sigma_cross / est.a_r, cfg.conf_grain_kappa)
        assert est.confidence == pytest.approx(math.erf(ph.HOLE_R / (math.sqrt(2) * dist * sigma_phi)))
    assert confs == sorted(confs, reverse=True) and confs[0] > 0.7 and confs[-1] < 0.1
    visible = es.estimate(_meas(), "B1")
    hidden = es.estimate(_meas(flag_base_visible=False), "B1")
    assert hidden.confidence == pytest.approx(0.8 * visible.confidence, rel=1e-6)
    # the allowance for the slope changing along the line is the calibrated one, not the fit prior
    assert cfg.conf_twist_sigma < cfg.sigma_curv


def test_confidence_reflects_the_mode_that_produced_the_read():
    """More information about the cross slope raises the score: Quick Read <
    Precision Read < Survey; the horizon never raises it (its samples are
    not independent evidence), and a poor horizon lowers it."""
    sc = gr.make_scenario("gentle", 6.0, 4)
    params = se.SensorParams()
    quick, _ = se.measure(sc.green, sc.ball_xy, sc.hole_xy, params, 3)
    spin, _ = se.measure(sc.green, sc.ball_xy, sc.hole_xy, params, 3, spin=True)
    drops = [m for m, _ in se.measure_survey(sc.green, sc.ball_xy, sc.hole_xy, params, 3)]
    assert quick.flag_found and len(drops) == 3
    c_quick = es.estimate(quick, "B1")
    c_spin = es.estimate(spin, "B1")
    c_two = es.estimate_survey(drops[:2])
    c_three = es.estimate_survey(drops)
    assert c_quick.confidence < c_spin.confidence < c_two.confidence < c_three.confidence
    assert c_quick.cross_slope_sigma > c_spin.cross_slope_sigma > c_two.cross_slope_sigma > c_three.cross_slope_sigma
    b2 = es.estimate(quick, "B2")
    assert b2.fit.used_horizon and b2.cross_slope_sigma == c_quick.cross_slope_sigma
    assert b2.confidence == pytest.approx(c_quick.confidence * (0.8 if b2.poor_horizon else 1.0))
    mounded, _ = se.measure(sc.green.with_mounded_surrounds(seed=2), sc.ball_xy, sc.hole_xy, params, 3)
    assert es.estimate(mounded, "B2").confidence <= es.estimate(mounded, "B1").confidence


def test_survey_drop_off_the_line_is_down_weighted_on_a_slope():
    """A drop placed by eye sits an unknown distance off the line, which
    rotates its "toward the hole" frame.  On a steep along-line slope that
    leaks into the cross tilt, so the drop's cross reading counts for less;
    on a flat line it counts fully."""
    def mid_drop(along):
        return _meas(tilt=np.array([along, 0.010]), flag_disparity=657.0 * 0.0200 / 1.0,
                     flag_low_elev=math.atan(along - (H - 0.75e-3) / 1.0))

    def ball(along):
        return _meas(tilt=np.array([along, 0.0]), flag_low_elev=math.atan(along - (H - 0.75e-3) / 5.0))

    flat = es.estimate_survey([ball(0.0), mid_drop(0.0)])
    steep = es.estimate_survey([ball(0.05), mid_drop(0.05)])
    assert flat.fit.stations == pytest.approx((0.0, 4.0))
    # the fitted twist d follows the drop's cross tilt less on the steep line
    assert 0.0 < steep.patch[3] < 0.9 * flat.patch[3]
    assert steep.cross_slope_sigma > flat.cross_slope_sigma
    # the cross-talk allowance: 0.15 m off the line at 1 m from the hole turns the frame by 0.15 rad,
    # i.e. 7.5 mrad of the 5 % along slope leaks into the cross tilt of that drop
    cfg = es.EstimatorConfig()
    assert cfg.sigma_drop_lateral == 0.15
    sig_drop = math.hypot(es._tilt_sigma(mid_drop(0.05), cfg), cfg.sigma_field)
    expected = es._cross_sigma_read(5.0, (0.0, 4.0), (sig_drop, math.hypot(sig_drop, 0.15 * 0.05)), cfg)
    assert steep.cross_slope_sigma == pytest.approx(expected, rel=1e-3)
    # with the allowance switched off the two agree
    off = es.EstimatorConfig(sigma_drop_lateral=0.0)
    assert es.estimate_survey([ball(0.05), mid_drop(0.05)], off).patch[3] == pytest.approx(
        es.estimate_survey([ball(0.0), mid_drop(0.0)], off).patch[3], rel=1e-6)


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
    found = es.estimate(_meas(tilt=np.array([0.004, 0.012]), flag_disparity=657.0 * 0.0200 / 7.0), "B0")
    # low confidence is flagged: the hand-pointing error is in the score, and the flag multiplier on top
    cfg = es.EstimatorConfig()
    assert est.confidence < 0.8 * found.confidence
    sigma_phi = math.hypot(found.cross_slope_sigma * ph.ROLL_FACTOR * ph.G / found.a_r, cfg.conf_grain_kappa)
    sigma_phi = math.hypot(0.5 * es._pace_factor(7.0, cfg.past) * sigma_phi, cfg.sigma_hand_bearing)
    assert est.confidence == pytest.approx(cfg.conf_flag_missing * math.erf(ph.HOLE_R / (math.sqrt(2) * 7.0 * sigma_phi)), rel=1e-3)
    # no dialled distance either: the default distance
    assert es.estimate(_meas(**lost), "B1").distance == es.EstimatorConfig().default_distance
    assert es.estimate(_meas(**lost), "STRAIGHT").flag_missing


def test_flag_found_but_not_ranged_keeps_the_camera_bearing():
    """Regression: a found flag whose stereo disparity is below the accepted
    minimum (and whose top is out of the field) used to be treated like a
    missing flag - bearing 0 along the visor axis, which in a camera read is
    pointed only to about 10 degrees."""
    beta = math.radians(9.0)
    slope_putt = np.array([0.004, 0.012])
    tilt_dev = np.array([slope_putt[0] * math.cos(beta) - slope_putt[1] * math.sin(beta),
                         slope_putt[0] * math.sin(beta) + slope_putt[1] * math.cos(beta)])
    weak = _meas(tilt=tilt_dev, flag_bearing=beta, flag_disparity=0.24)
    assert es.EstimatorConfig().min_disparity == 0.25 and not es.fuse_range(weak).valid
    for method in ("B0", "B1", "B2"):
        est = es.estimate(weak, method)
        assert est.range_missing and not est.flag_missing
        assert est.bearing == pytest.approx(beta) and est.distance == es.EstimatorConfig().default_distance
        assert np.allclose(est.patch, [0.004, 0.012, 0, 0, 0], atol=1e-12)  # tilt rotated by the measured bearing
        assert est.aim_azimuth_device == pytest.approx(beta + est.phi)
    ranged = es.estimate(_meas(tilt=tilt_dev, flag_bearing=beta, flag_disparity=657.0 * 0.0200 / 3.0), "B0")
    assert est.confidence == pytest.approx(0.5 * ranged.confidence, rel=1e-6)  # low confidence is flagged
    assert es.estimate(dataclasses.replace(weak, user_distance=7.0), "B1").distance == 7.0
    assert es.estimate(weak, "STRAIGHT").aim_azimuth_device == pytest.approx(beta)


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
    mid = _meas(tilt=np.array([0.0, 0.004]), flag_disparity=657.0 * 0.0200 / 2.5,
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
    """Structural check: the estimator imports only the Measurements record,
    the physics solver and the numba shim."""
    source = pathlib.Path(es.__file__).read_text()
    allowed_local = {"measurements", "physics", "_jit"}
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
    # ... and no identifier in the code refers to it (prose in docstrings may say "greens")
    used = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            used.add(node.attr)
        elif isinstance(node, ast.arg):
            used.add(node.arg)
    assert forbidden.isdisjoint(used)
    for word in ("MeasurementTruth", "make_green", "PuttScenario", "HorizonTruth"):
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
