/*
 * gl_solver.c - the putt estimator: fit, solve, fallbacks, confidence.
 *
 * Port of estimator.py (estimate_batch for one item, estimate,
 * estimate_survey, _confidence, _pace_factor, _wrap).  Statement order and
 * operation order follow the reference.
 *
 *   fit the patch (gl_solver_fit.c)
 *   -> solve the putt on it (gl_solver_aim.c)
 *   -> not solvable: solve on the patch's secant plane (keeps the hole
 *      height and the mean cross slope)             aim_source 1
 *   -> not solvable either: best iterate of that solve  aim_source 2
 *   -> nothing usable (zero distance): straight at flat pace  aim_source 3
 *   -> confidence score
 *
 * WHAT IS REJECTED.  GL_ERR_PARAM: an input the reference rejects or that
 * no placement can produce (see gl_solver.h).  GL_ERR_RANGE: the
 * arithmetic left the finite range (the reference raises an exception or
 * returns not-a-number there).  In both cases the output is the flagged
 * record of estimate_not_run_().
 */
#include "gl_solver_priv.h"

#include "gl_config.h"

uint32_t gl_solver_version(void)
{
    return GL_SOLVER_VERSION;
}

void gl_solver_default_options(gl_solver_options_t *opt)
{
    if (opt == NULL) {
        return;
    }
    opt->past_m = GLS_R(GL_SOLVER_DEFAULT_PAST_M);
    opt->max_rolls = (uint16_t)GL_SOLVER_DEFAULT_MAX_ROLLS;
    opt->method = (uint8_t)GL_SOLVER_METHOD_B1;
    opt->use_grain = false;
    opt->tol_miss_m = GLS_R(GL_SOLVER_DEFAULT_TOL_MISS_M);
    opt->tol_pace_m = GLS_R(GL_SOLVER_DEFAULT_TOL_PACE_M);
    opt->lm_tol = GLS_R(GL_SOLVER_DEFAULT_LM_TOL);
    opt->lm_max_iter = (uint16_t)GL_SOLVER_DEFAULT_LM_MAX_ITER;
}

void gl_solver_measurements_init(gl_measurements_t *m)
{
    if (m == NULL) {
        return;
    }
    m->f_px = GLS_R(GL_CFG_CAM_F_PX);
    m->baseline_m = GLS_R(GL_CFG_CAM_BASELINE_M);
    m->h_cam_m = GLS_R(GL_CFG_CAM_AXIS_HEIGHT_M);
    m->tilt_x = GLS_R(0.0);
    m->tilt_y = GLS_R(0.0);
    m->tilt_reads = 1u;
    m->flag_found = false;
    m->flag_bearing_rad = GLS_NAN;
    m->flag_disparity_px = GLS_NAN;
    m->flag_low_elev_rad = GLS_NAN;
    m->flag_base_visible = false;
    m->flag_top_visible = false;
    m->flag_top_elev_rad = GLS_NAN;
    m->stick_height_est_m = GLS_NAN;
    m->stick_height_rel_sigma = GLS_NAN;
    m->n_horizon = 0u;
    for (unsigned i = 0; i < GL_SOLVER_MAX_HORIZON; i++) {
        m->horizon_az_rad[i] = GLS_NAN;
        m->horizon_elev_rad[i] = GLS_NAN;
    }
    m->grain_kappa = GLS_R(0.0);
    m->grain_azimuth_rad = GLS_R(0.0);
    m->stimp_ft = GLS_R(10.0);
    m->user_distance_m = GLS_NAN;
}

/** The "explicitly flagged" record of a call that produced no estimate. */
static void estimate_not_run_(gl_estimate_t *out)
{
    out->phi_rad = GLS_R(0.0);
    out->aim_azimuth_device_rad = GLS_R(0.0);
    out->v0_mps = GLS_R(0.0);
    out->plays_like_m = GLS_R(0.0);
    out->break_m = GLS_R(0.0);
    out->break_cups = GLS_R(0.0);
    out->distance_m = GLS_R(0.0);
    out->distance_sigma_m = GLS_R(0.0);
    out->bearing_rad = GLS_R(0.0);
    out->slope_pct = GLS_R(0.0);
    out->fall_line_azimuth_rad = GLS_R(0.0);
    out->fall_line_azimuth_device_rad = GLS_R(0.0);
    out->dz_hole_m = GLS_R(0.0);
    for (unsigned i = 0; i < 5u; i++) {
        out->patch[i] = GLS_R(0.0);
    }
    out->cross_slope_sigma = GLS_R(0.0);
    out->confidence = GLS_R(0.0);
    out->base_hidden = false;
    out->flag_missing = false;
    out->range_missing = false;
    out->poor_horizon = false;
    out->fit_converged = false;
    out->aim_source = (uint8_t)GL_AIM_STRAIGHT;
    out->solve_status = (uint8_t)GL_SOLVE_NOT_RUN;
    out->a_r_mps2 = GLS_R(0.0);
    out->stimp_ft = GLS_R(0.0);
    out->grain_x = GLS_R(0.0);
    out->grain_y = GLS_R(0.0);
    out->n_rolls = 0u;
    out->n_steps = 0u;
}

/** atan2(sin, cos): the angle wrapped to (-pi, pi] (reference: _wrap). */
static gl_real_t wrap_(gl_real_t angle)
{
    return GLS_ATAN2(GLS_SIN(angle), GLS_COS(angle));
}

/** Reduction of the small-slope break angle by firm pace:
 *  F = 1 + rho^2 ln(rho^2) / (1 - rho^2), rho^2 = past / (D + past). */
static gl_real_t pace_factor_(gl_real_t distance, gl_real_t past)
{
    gl_real_t rho2;
    if (past <= GLS_R(0.0)) {
        return GLS_R(1.0);
    }
    rho2 = past / (distance + past);
    return GLS_R(1.0) + rho2 * GLS_LOG(rho2) / (GLS_R(1.0) - rho2);
}

/**
 * Reference: _confidence.  erf(HOLE_R / (sqrt(2) D sigma_phi)) times the
 * factors of the raised flags; sigma_phi from what the read cannot know in
 * the small-slope break formula: the mean cross slope (cross_sigma_read),
 * the cross-line grain, and the hand-pointing error when the flag is
 * missing.  *sigma_lat receives the lateral 1-sigma it rests on, so that
 * the caller can refuse a value that is not a number.
 */
static gl_real_t confidence_(const gl_patch_fit_t *fit, gl_real_t a_r, gl_real_t kappa_used,
                             uint8_t aim_source, const gl_solver_options_t *opt,
                             gl_real_t *sigma_lat_out)
{
    const gl_real_t dist = fit->distance_m;
    const gl_real_t sigma_kappa = opt->use_grain ? (GLS_CONF_GRAIN_REL * kappa_used)
                                                 : GLS_CONF_GRAIN_KAPPA;
    gl_real_t sigma_phi = GLS_R(0.5) * pace_factor_(dist, opt->past_m) *
                          gls_hypot(GLS_ROLL_FACTOR * GLS_G * fit->cross_sigma_read / a_r,
                                    sigma_kappa);
    gl_real_t sigma_lat, conf;

    if (fit->flag_missing) {
        sigma_phi = gls_hypot(sigma_phi, GLS_SIGMA_HAND_BEARING);
    }
    sigma_lat = dist * sigma_phi;
    *sigma_lat_out = sigma_lat;
    conf = (sigma_lat > GLS_R(0.0)) ? GLS_ERF(GLS_HOLE_R / (GLS_SQRT(GLS_R(2.0)) * sigma_lat))
                                    : GLS_R(1.0);
    if (fit->base_hidden) {
        conf *= GLS_CONF_BASE_HIDDEN;
    }
    if (fit->flag_missing) {
        conf *= GLS_CONF_FLAG_MISSING;
    }
    if (fit->range_missing) {
        conf *= GLS_CONF_RANGE_MISSING;
    }
    if (fit->poor_horizon) {
        conf *= GLS_CONF_POOR_HORIZON;
    }
    if (aim_source != (uint8_t)GL_AIM_FROM_PATCH) {
        conf *= GLS_CONF_AIM_FALLBACK;
    }
    if (GLS_R(0.0) > conf) {
        conf = GLS_R(0.0);
    }
    if (GLS_R(1.0) < conf) {
        conf = GLS_R(1.0);
    }
    return conf;
}

/** An input record the estimator can work with. */
static bool measurement_ok_(const gl_measurements_t *m)
{
    return gls_finite(m->f_px) && m->f_px > GLS_R(0.0) && gls_finite(m->baseline_m) &&
           m->baseline_m > GLS_R(0.0) && gls_finite(m->h_cam_m) && gls_finite(m->tilt_x) &&
           gls_finite(m->tilt_y) && m->n_horizon <= GL_SOLVER_MAX_HORIZON;
}

/** One aim solve on the putt-frame patch `coeffs` (ball at the origin,
 *  hole at (dist, 0)); adds its rolls and steps to the estimate. */
static uint8_t solve_patch_(const gl_real_t *coeffs, gl_real_t dist, gl_real_t a_r, gl_real_t gx,
                            gl_real_t gy, const gl_solver_options_t *opt, gls_solve_res_t *res,
                            uint32_t *n_rolls, uint32_t *n_steps)
{
    gl_quad_surface_t sf;
    uint8_t status;
    sf.a = coeffs[0];
    sf.b = coeffs[1];
    sf.c = coeffs[2];
    sf.d = coeffs[3];
    sf.e = coeffs[4];
    sf.z0 = GLS_R(0.0);
    status = gls_solve_kernel(&sf, GLS_R(0.0), GLS_R(0.0), dist, GLS_R(0.0), a_r, gx * a_r,
                              gy * a_r, GLS_SQRT(GLS_R(2.0) * a_r * opt->past_m), GLS_DT, GLS_T_MAX,
                              GLS_R_MAX, opt->tol_miss_m, opt->tol_pace_m, GLS_PHI_MAX, GLS_V_MAX,
                              (uint32_t)opt->max_rolls, res);
    *n_rolls += res->n_rolls;
    *n_steps += res->n_steps;
    return status;
}

/** Reference: estimate_batch() for one item.  `order` lists the drops, the
 *  one at the ball first. */
static gl_status_t estimate_(const gl_measurements_t *drops, const uint8_t *order, unsigned n_drops,
                             const gl_solver_options_t *opt_in, gl_solver_work_t *work,
                             gl_estimate_t *out)
{
    gl_solver_options_t defaults;
    const gl_solver_options_t *opt = opt_in;
    const gl_measurements_t *first;
    const gl_patch_fit_t *fit;
    gls_solve_res_t sol;
    gl_real_t dist, stimp, a_r, gx = GLS_R(0.0), gy = GLS_R(0.0);
    gl_real_t phi = GLS_R(0.0);
    gl_real_t v0, conf, sigma_cross, sigma_lat = GLS_R(0.0), t_x, t_y, slope, fall, brk;
    uint8_t source = (uint8_t)GL_AIM_STRAIGHT;
    uint8_t status = (uint8_t)GL_SOLVE_OK;
    uint32_t n_rolls = 0u, n_steps = 0u;
    gl_status_t st;
    bool finite;

    estimate_not_run_(out);
    if (opt == NULL) {
        gl_solver_default_options(&defaults);
        opt = &defaults;
    }
    if (!gls_options_ok(opt)) {
        return GL_ERR_PARAM;
    }
    for (unsigned i = 0; i < n_drops; i++) {
        if (!measurement_ok_(&drops[order[i]])) {
            return GL_ERR_PARAM;
        }
    }
    first = &drops[order[0]];
    /* green speed: clip to 5..16 ft (a not-a-number stays one and is refused) */
    stimp = first->stimp_ft;
    if (GLS_STIMP_MIN > stimp) {
        stimp = GLS_STIMP_MIN;
    }
    if (GLS_STIMP_MAX < stimp) {
        stimp = GLS_STIMP_MAX;
    }
    if (!gls_finite(stimp)) {
        return GL_ERR_PARAM;
    }

    st = gls_fit_patch(drops, order, n_drops, opt->method, opt, work);
    if (st != GL_OK) {
        return st;
    }
    fit = &work->fit;
    dist = fit->distance_m;
    a_r = GLS_STIMP_V0_SQ / (GLS_R(2.0) * stimp * GLS_FT);
    if (opt->use_grain && gls_finite(first->grain_kappa) && gls_finite(first->grain_azimuth_rad)) {
        gl_real_t kappa = first->grain_kappa;
        const gl_real_t az = first->grain_azimuth_rad - fit->bearing_rad;
        if (GLS_R(0.0) > kappa) {
            kappa = GLS_R(0.0);
        }
        if (GLS_GRAIN_KAPPA_MAX < kappa) {
            kappa = GLS_GRAIN_KAPPA_MAX;
        }
        gx = kappa * GLS_COS(az);
        gy = kappa * GLS_SIN(az);
    }
    /* the solver's own preconditions (the reference raises otherwise) */
    finite = gls_finite(dist) && gls_finite(a_r) && a_r > GLS_R(0.0) && gls_finite(gx) &&
             gls_finite(gy);
    for (unsigned i = 0; i < 5u; i++) {
        finite = finite && gls_finite(fit->coeffs[i]);
    }
    if (!finite) {
        return GL_ERR_RANGE;
    }

    v0 = GLS_SQRT(GLS_R(2.0) * a_r * (dist + opt->past_m)); /* flat-green pace */
    if (opt->method != (uint8_t)GL_SOLVER_METHOD_STRAIGHT) {
        status = solve_patch_(fit->coeffs, dist, a_r, gx, gy, opt, &sol, &n_rolls, &n_steps);
        if (status == (uint8_t)GL_SOLVE_OK || status == (uint8_t)GL_SOLVE_PACE_LIMITED) {
            phi = sol.phi;
            v0 = sol.v0;
            source = (uint8_t)GL_AIM_FROM_PATCH;
        } else {
            /* secant plane of the patch: keeps the hole height and the mean cross slope */
            gl_real_t plane[5];
            plane[0] = fit->coeffs[0] + GLS_R(0.5) * fit->coeffs[2] * dist;
            plane[1] = fit->coeffs[1] + GLS_R(0.5) * fit->coeffs[3] * dist;
            plane[2] = GLS_R(0.0);
            plane[3] = GLS_R(0.0);
            plane[4] = GLS_R(0.0);
            if (!gls_finite(plane[0]) || !gls_finite(plane[1])) {
                return GL_ERR_RANGE;
            }
            status = solve_patch_(plane, dist, a_r, gx, gy, opt, &sol, &n_rolls, &n_steps);
            if (status == (uint8_t)GL_SOLVE_OK || status == (uint8_t)GL_SOLVE_PACE_LIMITED) {
                phi = sol.phi;
                v0 = sol.v0;
                source = (uint8_t)GL_AIM_FROM_PLANE;
            } else if (gls_finite(sol.phi) && gls_finite(sol.v0) && sol.v0 > GLS_R(0.0)) {
                phi = sol.phi;
                v0 = sol.v0;
                source = (uint8_t)GL_AIM_BEST_EFFORT;
            }
            /* else: keep straight at flat pace (GL_AIM_STRAIGHT) */
        }
    }

    if (opt->method == (uint8_t)GL_SOLVER_METHOD_STRAIGHT) {
        conf = GLS_R(0.0);
        sigma_cross = GLS_NAN;
    } else {
        conf = confidence_(fit, a_r, gls_hypot(gx, gy), source, opt, &sigma_lat);
        sigma_cross = fit->cross_sigma_read;
    }
    /* slope and fall line at the ball: the tilt reading itself */
    t_x = fit->tilt_slopes[0];
    t_y = fit->tilt_slopes[1];
    slope = gls_hypot(t_x, t_y);
    fall = (slope > GLS_R(0.0)) ? GLS_ATAN2(-t_y, -t_x) : GLS_R(0.0);
    brk = dist * GLS_TAN(phi);

    out->phi_rad = phi;
    out->aim_azimuth_device_rad = wrap_(fit->bearing_rad + phi);
    out->v0_mps = v0;
    out->plays_like_m = v0 * v0 / (GLS_R(2.0) * a_r);
    out->break_m = brk;
    out->break_cups = brk / (GLS_R(2.0) * GLS_HOLE_R);
    out->distance_m = dist;
    /* "unknown" is one value: not-a-number (an infinite sigma means the same) */
    out->distance_sigma_m = gls_finite(fit->distance_sigma_m) ? fit->distance_sigma_m : GLS_NAN;
    out->bearing_rad = fit->bearing_rad;
    out->slope_pct = GLS_R(100.0) * slope;
    out->fall_line_azimuth_rad = fall;
    out->fall_line_azimuth_device_rad = wrap_(fall + fit->bearing_rad);
    out->dz_hole_m = fit->coeffs[0] * dist + GLS_R(0.5) * fit->coeffs[2] * (dist * dist);
    for (unsigned i = 0; i < 5u; i++) {
        out->patch[i] = fit->coeffs[i];
    }
    out->cross_slope_sigma = sigma_cross;
    out->confidence = conf;
    out->base_hidden = fit->base_hidden;
    out->flag_missing = fit->flag_missing;
    out->range_missing = fit->range_missing;
    out->poor_horizon = fit->poor_horizon;
    out->fit_converged = fit->converged;
    out->aim_source = source;
    out->solve_status = status;
    out->a_r_mps2 = a_r;
    out->stimp_ft = stimp;
    out->grain_x = gx;
    out->grain_y = gy;
    out->n_rolls = (uint16_t)((n_rolls > 65535u) ? 65535u : n_rolls);
    out->n_steps = n_steps;

    /* Every real of an estimate is finite, except the two documented
     * "unknown" values.  Anything else means that the arithmetic left the
     * finite range (absurd inputs): flag it instead of handing it on. */
    finite = gls_finite(out->phi_rad) && gls_finite(out->aim_azimuth_device_rad) &&
             gls_finite(out->v0_mps) && gls_finite(out->plays_like_m) && gls_finite(out->break_m) &&
             gls_finite(out->break_cups) && gls_finite(out->distance_m) &&
             gls_finite(out->bearing_rad) && gls_finite(out->slope_pct) &&
             gls_finite(out->fall_line_azimuth_rad) &&
             gls_finite(out->fall_line_azimuth_device_rad) && gls_finite(out->dz_hole_m) &&
             gls_finite(out->confidence) && gls_finite(sigma_lat) &&
             (opt->method == (uint8_t)GL_SOLVER_METHOD_STRAIGHT || gls_finite(sigma_cross));
    if (!finite) {
        estimate_not_run_(out);
        return GL_ERR_RANGE;
    }
    return GL_OK;
}

gl_status_t gl_solver_estimate(const gl_measurements_t *m, const gl_solver_options_t *opt,
                               gl_solver_work_t *work, gl_estimate_t *out)
{
    static const uint8_t order[1] = { 0u };
    if (out == NULL) {
        return GL_ERR_PARAM;
    }
    if (m == NULL || work == NULL) {
        estimate_not_run_(out);
        return GL_ERR_PARAM;
    }
    return estimate_(m, order, 1u, opt, work, out);
}

gl_status_t gl_solver_estimate_survey(const gl_measurements_t *drops, unsigned n_drops,
                                      unsigned ball_index, const gl_solver_options_t *opt,
                                      gl_solver_work_t *work, gl_estimate_t *out)
{
    uint8_t order[GL_SOLVER_MAX_DROPS];
    unsigned k = 1u;
    if (out == NULL) {
        return GL_ERR_PARAM;
    }
    if (drops == NULL || work == NULL || n_drops == 0u || n_drops > GL_SOLVER_MAX_DROPS ||
        ball_index >= n_drops) {
        estimate_not_run_(out);
        return GL_ERR_PARAM;
    }
    /* the drop at the ball first, the others in array order */
    order[0] = (uint8_t)ball_index;
    for (unsigned i = 0; i < n_drops; i++) {
        if (i != ball_index) {
            order[k++] = (uint8_t)i;
        }
    }
    return estimate_(drops, order, n_drops, opt, work, out);
}
