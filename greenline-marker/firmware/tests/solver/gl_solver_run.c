/*
 * gl_solver_run.c - reference-vector cases and hostile inputs through the
 * solver, in the precision this file is compiled for (HOST TESTS ONLY).
 *
 * Compiled twice by the Makefile: as it is (gl_real_t = float, functions
 * gl_vec32_*) and with -DGL_SOLVER_DOUBLE (gl_real_t = double, functions
 * gl_vec64_*).  See gl_solver_run.h.
 */
#include "gl_solver_run.h"

#include <float.h>
#include <stdio.h>
#include <string.h>

#include "gl_solver.h"

#ifdef GL_SOLVER_DOUBLE
#define GLV(name) gl_vec64_##name
#define REAL_MAX DBL_MAX
#define REAL_MIN DBL_MIN
#else
#define GLV(name) gl_vec32_##name
#define REAL_MAX FLT_MAX
#define REAL_MIN FLT_MIN
#endif

#define R(x) ((gl_real_t)(x))

/* One work area per precision: the tests are single-threaded. */
static gl_solver_work_t work_;

unsigned GLV(real_bits)(void)
{
    return (unsigned)GL_SOLVER_REAL_BITS;
}

uint32_t GLV(version)(void)
{
    return gl_solver_version();
}

unsigned GLV(sizeof)(unsigned which)
{
    switch (which) {
    case 0u: return (unsigned)sizeof(gl_solver_work_t);
    case 1u: return (unsigned)sizeof(gl_measurements_t);
    case 2u: return (unsigned)sizeof(gl_estimate_t);
    case 3u: return (unsigned)sizeof(gl_patch_fit_t);
    case 4u: return (unsigned)sizeof(gl_solver_options_t);
    default: return 0u;
    }
}

/* ---- conversions ------------------------------------------------------------- */

static void to_meas_(const gl_vec_meas_t *v, gl_measurements_t *m)
{
    gl_solver_measurements_init(m);
    m->f_px = R(v->f_px);
    m->baseline_m = R(v->baseline);
    m->h_cam_m = R(v->h_cam);
    m->tilt_x = R(v->tilt[0]);
    m->tilt_y = R(v->tilt[1]);
    m->tilt_reads = v->tilt_reads;
    m->flag_found = v->flag_found != 0u;
    m->flag_bearing_rad = R(v->flag_bearing);
    m->flag_disparity_px = R(v->flag_disparity);
    m->flag_low_elev_rad = R(v->flag_low_elev);
    m->flag_base_visible = v->flag_base_visible != 0u;
    m->flag_top_visible = v->flag_top_visible != 0u;
    m->flag_top_elev_rad = R(v->flag_top_elev);
    m->stick_height_est_m = R(v->stick_height_est);
    m->stick_height_rel_sigma = R(v->stick_height_rel_sigma);
    m->n_horizon = (uint8_t)v->n_horizon;
    for (unsigned i = 0; i < v->n_horizon && i < GL_SOLVER_MAX_HORIZON; i++) {
        m->horizon_az_rad[i] = R(gl_vec_horizon_az[v->horizon_first + i]);
        m->horizon_elev_rad[i] = R(gl_vec_horizon_elev[v->horizon_first + i]);
    }
    m->grain_kappa = R(v->grain_kappa);
    m->grain_azimuth_rad = R(v->grain_azimuth);
    m->stimp_ft = R(v->stimp_ft);
    m->user_distance_m = R(v->user_distance);
}

static void tolerances_(gl_solver_options_t *opt, gl_vec_tol_t tol, double tol_miss, double tol_pace,
                        double lm_tol, unsigned lm_max_iter, int lm_overridden)
{
    gl_solver_default_options(opt);
    if (tol == GL_VEC_TOL_CASE) {
        opt->tol_miss_m = R(tol_miss);
        opt->tol_pace_m = R(tol_pace);
        opt->lm_tol = R(lm_tol);
        opt->lm_max_iter = (uint16_t)lm_max_iter;
    } else {
        if (tol == GL_VEC_TOL_SINGLE) {
            opt->tol_miss_m = R(GL_SOLVER_SINGLE_TOL_MISS_M);
            opt->tol_pace_m = R(GL_SOLVER_SINGLE_TOL_PACE_M);
            opt->lm_tol = R(GL_SOLVER_SINGLE_LM_TOL);
        }
        if (lm_overridden) {
            opt->lm_max_iter = (uint16_t)lm_max_iter;
        }
    }
}

/* ---- vector cases -------------------------------------------------------------- */

/* step budget of the estimates that follow (0 = none, the reference) */
static uint32_t max_steps_;

void GLV(set_max_steps)(uint32_t max_steps)
{
    max_steps_ = max_steps;
}

/* gl_estimate_t and the fit record of the call just made -> the result record */
static void fill_(gl_status_t st, const gl_estimate_t *est_p, gl_vec_est_result_t *out)
{
    const gl_estimate_t est = *est_p;
    const gl_patch_fit_t *fit = &work_.fit;
    out->status = (int)st;
    out->phi = (double)est.phi_rad;
    out->aim_azimuth_device = (double)est.aim_azimuth_device_rad;
    out->v0 = (double)est.v0_mps;
    out->plays_like = (double)est.plays_like_m;
    out->break_m = (double)est.break_m;
    out->break_cups = (double)est.break_cups;
    out->distance = (double)est.distance_m;
    out->distance_sigma = (double)est.distance_sigma_m;
    out->bearing = (double)est.bearing_rad;
    out->slope_pct = (double)est.slope_pct;
    out->fall_line_azimuth = (double)est.fall_line_azimuth_rad;
    out->fall_line_azimuth_device = (double)est.fall_line_azimuth_device_rad;
    out->dz_hole = (double)est.dz_hole_m;
    for (unsigned i = 0; i < 5u; i++) {
        out->patch[i] = (double)est.patch[i];
    }
    out->cross_slope_sigma = (double)est.cross_slope_sigma;
    out->confidence = (double)est.confidence;
    out->a_r = (double)est.a_r_mps2;
    out->stimp_ft = (double)est.stimp_ft;
    out->grain[0] = (double)est.grain_x;
    out->grain[1] = (double)est.grain_y;
    out->base_hidden = est.base_hidden ? 1u : 0u;
    out->flag_missing = est.flag_missing ? 1u : 0u;
    out->range_missing = est.range_missing ? 1u : 0u;
    out->poor_horizon = est.poor_horizon ? 1u : 0u;
    out->fit_converged = est.fit_converged ? 1u : 0u;
    out->aim_source = est.aim_source;
    out->solve_status = est.solve_status;
    out->n_rolls = est.n_rolls;
    out->n_steps = est.n_steps;
    if (st != GL_OK) {
        return;
    }
    out->level_offsets[0] = (double)fit->level_offsets[0];
    out->level_offsets[1] = (double)fit->level_offsets[1];
    out->range_stereo = (double)fit->range.stereo_m;
    out->range_mono = (double)fit->range.mono_m;
    out->tilt_slopes[0] = (double)fit->tilt_slopes[0];
    out->tilt_slopes[1] = (double)fit->tilt_slopes[1];
    out->n_stations = fit->n_drops;
    for (unsigned i = 0; i < GL_SOLVER_MAX_DROPS; i++) {
        out->stations[i] = (double)fit->stations_m[i];
    }
    out->fit_cost = (double)fit->cost;
    for (unsigned i = 0; i < 5u; i++) {
        out->cov_diag[i] = (double)fit->cov[i][i];
    }
    out->horizon_rms = (double)fit->horizon_rms;
    out->used_horizon = fit->used_horizon ? 1u : 0u;
    out->fit_starts = fit->n_starts;
    out->n_iter = fit->n_iter;
}

void GLV(estimate)(const gl_vec_est_case_t *c, gl_vec_tol_t tol, int ball_last, gl_vec_est_result_t *out)
{
    gl_measurements_t drops[GL_SOLVER_MAX_DROPS];
    gl_solver_options_t opt;
    gl_estimate_t est;
    const unsigned n = c->n_drops;
    gl_status_t st;

    memset(out, 0, sizeof(*out));
    tolerances_(&opt, tol, c->tol_miss, c->tol_pace, c->lm_tol, c->lm_max_iter,
                c->lm_max_iter_overridden != 0u);
    opt.past_m = R(c->past);
    opt.method = c->method;
    opt.use_grain = c->use_grain != 0u;
    opt.near_miss_m = R(c->near_miss);
    opt.max_steps = max_steps_;
    if (n == 1u && !ball_last) {
        to_meas_(&gl_vec_meas[c->first_meas], &drops[0]);
        st = gl_solver_estimate(&drops[0], &opt, &work_, &est);
    } else if (!ball_last) {
        for (unsigned i = 0; i < n; i++) {
            to_meas_(&gl_vec_meas[c->first_meas + i], &drops[i]);
        }
        st = gl_solver_estimate_survey(drops, n, 0u, &opt, &work_, &est);
    } else {
        /* the drop at the ball last, the others before it in their order */
        for (unsigned i = 1u; i < n; i++) {
            to_meas_(&gl_vec_meas[c->first_meas + i], &drops[i - 1u]);
        }
        to_meas_(&gl_vec_meas[c->first_meas], &drops[n - 1u]);
        st = gl_solver_estimate_survey(drops, n, n - 1u, &opt, &work_, &est);
    }
    fill_(st, &est, out);
}

void GLV(estimate_meas)(const gl_vec_meas_t *v, unsigned n, const double *hz_az, const double *hz_elev,
                        unsigned method, double past, double near_miss, uint32_t max_steps, int single_tol,
                        gl_vec_est_result_t *out)
{
    gl_measurements_t drops[GL_SOLVER_MAX_DROPS];
    gl_solver_options_t opt;
    gl_estimate_t est;
    gl_status_t st;

    memset(out, 0, sizeof(*out));
    gl_solver_default_options(&opt);
    if (single_tol) {
        opt.tol_miss_m = R(GL_SOLVER_SINGLE_TOL_MISS_M);
        opt.tol_pace_m = R(GL_SOLVER_SINGLE_TOL_PACE_M);
        opt.lm_tol = R(GL_SOLVER_SINGLE_LM_TOL);
    }
    opt.method = (uint8_t)method;
    opt.past_m = R(past);
    opt.near_miss_m = R(near_miss);
    opt.max_steps = max_steps;
    if (n == 0u || n > GL_SOLVER_MAX_DROPS) {
        out->status = (int)GL_ERR_PARAM;
        return;
    }
    for (unsigned i = 0; i < n; i++) {
        gl_vec_meas_t one = v[i];
        const unsigned n_h = one.n_horizon;
        one.n_horizon = 0u; /* (the horizon of an ad-hoc placement is not in the generated tables) */
        to_meas_(&one, &drops[i]);
        if (i == 0u && hz_az != NULL && hz_elev != NULL && n_h <= GL_SOLVER_MAX_HORIZON) {
            drops[0].n_horizon = (uint8_t)n_h;
            for (unsigned k = 0; k < n_h; k++) {
                drops[0].horizon_az_rad[k] = R(hz_az[k]);
                drops[0].horizon_elev_rad[k] = R(hz_elev[k]);
            }
        }
    }
    if (n == 1u) {
        st = gl_solver_estimate(&drops[0], &opt, &work_, &est);
    } else {
        st = gl_solver_estimate_survey(drops, n, 0u, &opt, &work_, &est);
    }
    fill_(st, &est, out);
}

void GLV(default_options)(double out[4], uint32_t *max_steps)
{
    gl_solver_options_t opt;
    gl_solver_default_options(&opt);
    out[0] = (double)opt.past_m;
    out[1] = (double)opt.near_miss_m;
    out[2] = (double)opt.tol_miss_m;
    out[3] = (double)opt.lm_tol;
    *max_steps = opt.max_steps;
}

void GLV(solve)(const gl_vec_sol_case_t *c, gl_vec_tol_t tol, gl_vec_sol_result_t *out)
{
    gl_solver_options_t opt;
    gl_quad_surface_t sf;
    gl_aim_solution_t sol;
    gl_rvec2_t start, hole, grain;
    gl_status_t st;

    memset(out, 0, sizeof(*out));
    tolerances_(&opt, tol, c->tol_miss, c->tol_pace, 0.0, 0u, 0);
    opt.past_m = R(c->past);
    opt.max_rolls = c->max_rolls;
    sf.a = R(c->coeffs[0]);
    sf.b = R(c->coeffs[1]);
    sf.c = R(c->coeffs[2]);
    sf.d = R(c->coeffs[3]);
    sf.e = R(c->coeffs[4]);
    sf.z0 = R(0.0);
    start.x = R(0.0);
    start.y = R(0.0);
    hole.x = R(c->distance);
    hole.y = R(0.0);
    grain.x = R(c->grain[0]);
    grain.y = R(c->grain[1]);
    st = gl_solver_solve_aim(&sf, start, hole, R(c->a_r), grain, &opt, &sol);
    out->status = (int)st;
    out->solve_status = sol.status;
    out->phi = (double)sol.phi_rad;
    out->v0 = (double)sol.v0_mps;
    out->v_hole = (double)sol.v_hole_mps;
    out->miss = (double)sol.miss_m;
    out->distance = (double)sol.distance_m;
    out->n_rolls = sol.n_rolls;
    out->n_steps = sol.n_steps;
}

static void roll_out_(gl_status_t st, const gl_roll_result_t *r, gl_vec_roll_result_t *out)
{
    out->status = (int)st;
    out->roll_status = r->status;
    out->crossed = r->crossed_hole_line ? 1u : 0u;
    out->captured = r->captured ? 1u : 0u;
    out->side = r->side;
    out->t_end = (double)r->t_end_s;
    out->stop_xy[0] = (double)r->stop_x;
    out->stop_xy[1] = (double)r->stop_y;
    out->delta = (double)r->delta_m;
    out->speed_at_delta = (double)r->speed_at_delta_mps;
    out->lateral_at_line = (double)r->lateral_at_line_m;
    out->speed_at_line = (double)r->speed_at_line_mps;
    out->lateral_miss = (double)r->lateral_miss_m;
    out->shortfall = (double)r->shortfall_m;
    out->path_length = (double)r->path_length_m;
    out->n_steps = r->n_steps;
}

void GLV(roll)(const gl_vec_roll_case_t *c, gl_vec_roll_result_t *out)
{
    gl_quad_surface_t sf;
    gl_roll_result_t r;
    gl_rvec2_t start, hole, grain;
    gl_status_t st;

    sf.a = R(c->coeffs[0]);
    sf.b = R(c->coeffs[1]);
    sf.c = R(c->coeffs[2]);
    sf.d = R(c->coeffs[3]);
    sf.e = R(c->coeffs[4]);
    sf.z0 = R(c->z0);
    start.x = R(c->start[0]);
    start.y = R(c->start[1]);
    hole.x = R(c->hole[0]);
    hole.y = R(c->hole[1]);
    grain.x = R(c->grain[0]);
    grain.y = R(c->grain[1]);
    st = gl_solver_roll(&sf, start, hole, R(c->phi), R(c->v0), R(c->a_r), grain,
                        R(c->capture_exponent), c->stop_on_capture != 0u, &r);
    roll_out_(st, &r, out);
}

int GLV(roll_patch)(const double coeffs[5], double dist, double a_r, const double grain[2], double phi,
                    double v0, double *lateral, double *speed)
{
    gl_quad_surface_t sf;
    gl_roll_result_t r;
    gl_rvec2_t start, hole, g;

    sf.a = R(coeffs[0]);
    sf.b = R(coeffs[1]);
    sf.c = R(coeffs[2]);
    sf.d = R(coeffs[3]);
    sf.e = R(coeffs[4]);
    sf.z0 = R(0.0);
    start.x = R(0.0);
    start.y = R(0.0);
    hole.x = R(dist);
    hole.y = R(0.0);
    g.x = R(grain[0]);
    g.y = R(grain[1]);
    *lateral = GL_VEC_NAN;
    *speed = GL_VEC_NAN;
    if (gl_solver_roll(&sf, start, hole, R(phi), R(v0), R(a_r), g, R(0.5), false, &r) != GL_OK ||
        !r.crossed_hole_line) {
        return 0;
    }
    *lateral = (double)r.lateral_at_line_m;
    *speed = (double)r.speed_at_line_mps;
    return 1;
}

void GLV(fuse_range)(const gl_vec_meas_t *v, double out[4])
{
    gl_measurements_t m;
    gl_range_estimate_t r;
    to_meas_(v, &m);
    gl_solver_fuse_range(&m, &r);
    out[0] = (double)r.distance_m;
    out[1] = (double)r.sigma_m;
    out[2] = (double)r.stereo_m;
    out[3] = (double)r.mono_m;
}

/* ---- hostile inputs --------------------------------------------------------------- */

static uint32_t rng_;

static uint32_t rnd_(void)
{
    /* xorshift32 */
    rng_ ^= rng_ << 13;
    rng_ ^= rng_ >> 17;
    rng_ ^= rng_ << 5;
    return rng_;
}

/** Uniform in [0, 1). */
static gl_real_t uni_(void)
{
    return (gl_real_t)(rnd_() >> 8) / R(16777216.0);
}

static gl_real_t range_(gl_real_t lo, gl_real_t hi)
{
    return lo + (hi - lo) * uni_();
}

/** A value chosen to break things. */
#ifdef GL_SOLVER_DOUBLE
#define SQUARE_OVERFLOWS 1e300
#define SQUARE_UNDERFLOWS 1e-200
#else
#define SQUARE_OVERFLOWS 1e20f
#define SQUARE_UNDERFLOWS 1e-23f
#endif

static gl_real_t nasty_(void)
{
    static const double table[] = {
        0.0, -0.0, 1.0, -1.0, 1e-30, -1e-30, 1e30, -1e30, 1e-6, 1e-7, 2e-6, 0.25, 0.2499999,
        3.14159265358979, -3.14159265358979, 1.5707963267948966, 100.0, -100.0, 1e6, -1e6,
        1e12, 1e-12, 0.5, -0.5, 16.0, 5.0, 4.999, 0.02, 657.0, 41.0, 1e-3, 3.0, 1e4,
    };
    const uint32_t k = rnd_() % 47u;
    if (k < 33u) {
        return R(table[k]);
    }
    switch (k) {
    /* numbers whose SQUARE leaves the range of the real type (the review
     * found weights 1 / sigma^2 that became 0 or infinite and passed as
     * results): 1e20 / 1e-23 in single precision, 1e300 / 1e-200 in double */
    case 44u: return R(SQUARE_OVERFLOWS);
    case 45u: return -R(SQUARE_OVERFLOWS);
    case 46u: return R(SQUARE_UNDERFLOWS);
    case 33u: return R(NAN);
    case 34u: return R(INFINITY);
    case 35u: return -R(INFINITY);
    case 36u: return R(REAL_MAX);
    case 37u: return -R(REAL_MAX);
    case 38u: return R(REAL_MIN);
    case 39u: return R(REAL_MIN) / R(1024.0); /* subnormal */
    case 40u: return range_(R(-10.0), R(10.0));
    case 41u: return range_(R(-0.2), R(0.2));
    case 42u: return R(REAL_MAX) / R(4.0);
    default: return R(NAN);
    }
}

/** A plausible placement to start from. */
static void nominal_(gl_measurements_t *m)
{
    const gl_real_t dist = range_(R(0.3), R(30.0));
    gl_solver_measurements_init(m);
    m->tilt_x = range_(R(-0.04), R(0.04));
    m->tilt_y = range_(R(-0.04), R(0.04));
    m->tilt_reads = (uint8_t)(1u + rnd_() % 2u);
    m->flag_found = (rnd_() % 8u) != 0u;
    m->flag_bearing_rad = range_(R(-0.4), R(0.4));
    m->flag_disparity_px = m->f_px * m->baseline_m / dist;
    m->flag_low_elev_rad = range_(R(-0.03), R(0.03));
    m->flag_base_visible = (rnd_() % 4u) != 0u;
    m->flag_top_visible = (rnd_() % 2u) != 0u;
    m->flag_top_elev_rad = m->flag_low_elev_rad + R(1.96) / dist;
    m->stick_height_est_m = R(1.96);
    m->stick_height_rel_sigma = R(0.07);
    m->n_horizon = (uint8_t)((rnd_() % 3u == 0u) ? (rnd_() % (GL_SOLVER_MAX_HORIZON + 1u)) : 0u);
    for (unsigned i = 0; i < GL_SOLVER_MAX_HORIZON; i++) {
        m->horizon_az_rad[i] = R(-0.45) + R(0.0225) * (gl_real_t)i;
        m->horizon_elev_rad[i] = (rnd_() % 10u == 0u) ? R(NAN) : range_(R(-0.02), R(0.02));
    }
    m->grain_kappa = range_(R(0.0), R(0.2));
    m->grain_azimuth_rad = range_(R(-3.0), R(3.0));
    m->stimp_ft = range_(R(5.0), R(16.0));
    m->user_distance_m = (rnd_() % 3u == 0u) ? range_(R(0.5), R(15.0)) : R(NAN);
}

/** Overwrite one randomly chosen field with a value chosen to break things. */
static void mutate_(gl_measurements_t *m)
{
    const gl_real_t v = nasty_();
    switch (rnd_() % 24u) {
    case 0u: m->f_px = v; break;
    case 1u: m->baseline_m = v; break;
    case 2u: m->h_cam_m = v; break;
    case 3u: m->tilt_x = v; break;
    case 4u: m->tilt_y = v; break;
    case 5u: m->tilt_reads = (uint8_t)rnd_(); break;
    case 6u: m->flag_found = !m->flag_found; break;
    case 7u: m->flag_bearing_rad = v; break;
    case 8u: m->flag_disparity_px = v; break;
    case 9u: m->flag_low_elev_rad = v; break;
    case 10u: m->flag_base_visible = !m->flag_base_visible; break;
    case 11u: m->flag_top_visible = !m->flag_top_visible; break;
    case 12u: m->flag_top_elev_rad = v; break;
    case 13u: m->stick_height_est_m = v; break;
    case 14u: m->stick_height_rel_sigma = v; break;
    case 15u: m->n_horizon = (uint8_t)rnd_(); break; /* also beyond GL_SOLVER_MAX_HORIZON */
    case 16u: m->horizon_az_rad[rnd_() % GL_SOLVER_MAX_HORIZON] = v; break;
    case 17u: m->horizon_elev_rad[rnd_() % GL_SOLVER_MAX_HORIZON] = v; break;
    case 18u: m->grain_kappa = v; break;
    case 19u: m->grain_azimuth_rad = v; break;
    case 20u: m->stimp_ft = v; break;
    case 21u: m->user_distance_m = v; break;
    case 22u:
        for (unsigned i = 0; i < GL_SOLVER_MAX_HORIZON; i++) {
            m->horizon_elev_rad[i] = nasty_();
        }
        m->n_horizon = (uint8_t)GL_SOLVER_MAX_HORIZON;
        break;
    default:
        m->tilt_x = nasty_();
        m->tilt_y = nasty_();
        break;
    }
}

static void hostile_options_(gl_solver_options_t *opt)
{
    gl_solver_default_options(opt);
    opt->method = (uint8_t)(rnd_() % 4u);
    opt->use_grain = (rnd_() % 3u) == 0u;
    if (rnd_() % 4u == 0u) {
        switch (rnd_() % 8u) {
        case 0u: opt->past_m = nasty_(); break;
        case 1u: opt->max_rolls = (uint16_t)(rnd_() % 1100u); break; /* also beyond the limit */
        case 2u: opt->method = (uint8_t)(rnd_() % 7u); break;       /* also not a method */
        case 3u: opt->tol_miss_m = nasty_(); break;
        case 4u: opt->tol_pace_m = nasty_(); break;
        case 5u: opt->lm_tol = nasty_(); break;
        case 6u: opt->lm_max_iter = (uint16_t)(rnd_() % 1100u); break;
        default: opt->max_rolls = (uint16_t)(rnd_() % 8u); break;
        }
    }
}

static bool fin_(gl_real_t x)
{
    return isfinite(x) != 0;
}

static void violation_(gl_vec_hostile_t *h, const char *what, unsigned call)
{
    if (h->violations == 0u) {
        snprintf(h->first_violation, sizeof(h->first_violation), "call %u: %s", call, what);
    }
    h->violations++;
}

/** The record gl_solver.h promises for a call that produced no estimate. */
static bool is_flagged_(const gl_estimate_t *e)
{
    bool z = e->phi_rad == R(0.0) && e->aim_azimuth_device_rad == R(0.0) && e->v0_mps == R(0.0) &&
             e->plays_like_m == R(0.0) && e->break_m == R(0.0) && e->break_cups == R(0.0) &&
             e->distance_m == R(0.0) && e->distance_sigma_m == R(0.0) && e->bearing_rad == R(0.0) &&
             e->slope_pct == R(0.0) && e->fall_line_azimuth_rad == R(0.0) &&
             e->fall_line_azimuth_device_rad == R(0.0) && e->dz_hole_m == R(0.0) &&
             e->cross_slope_sigma == R(0.0) && e->confidence == R(0.0) && e->a_r_mps2 == R(0.0) &&
             e->stimp_ft == R(0.0) && e->grain_x == R(0.0) && e->grain_y == R(0.0) &&
             e->n_rolls == 0u && e->n_steps == 0u && !e->fit_converged &&
             e->aim_source == (uint8_t)GL_AIM_STRAIGHT && e->solve_status == (uint8_t)GL_SOLVE_NOT_RUN;
    for (unsigned i = 0; i < 5u; i++) {
        z = z && e->patch[i] == R(0.0);
    }
    return z;
}

/** Every promise gl_solver.h makes about an estimate that returned GL_OK. */
static const char *check_estimate_(const gl_estimate_t *e, const gl_solver_options_t *opt)
{
    const uint32_t roll_cap = 2u * ((uint32_t)opt->max_rolls + 120u);
    bool f = fin_(e->phi_rad) && fin_(e->aim_azimuth_device_rad) && fin_(e->v0_mps) &&
             fin_(e->plays_like_m) && fin_(e->break_m) && fin_(e->break_cups) && fin_(e->distance_m) &&
             fin_(e->bearing_rad) && fin_(e->slope_pct) && fin_(e->fall_line_azimuth_rad) &&
             fin_(e->fall_line_azimuth_device_rad) && fin_(e->dz_hole_m) && fin_(e->confidence) &&
             fin_(e->a_r_mps2) && fin_(e->stimp_ft) && fin_(e->grain_x) && fin_(e->grain_y);
    for (unsigned i = 0; i < 5u; i++) {
        f = f && fin_(e->patch[i]);
    }
    if (!f) {
        return "GL_OK with a not-a-number or an infinity in the estimate";
    }
    if (!(fin_(e->distance_sigma_m) || e->distance_sigma_m != e->distance_sigma_m)) {
        return "distance_sigma_m is infinite (must be finite or not-a-number)";
    }
    if (opt->method == (uint8_t)GL_SOLVER_METHOD_STRAIGHT) {
        if (e->cross_slope_sigma == e->cross_slope_sigma) {
            return "cross_slope_sigma of STRAIGHT is a number";
        }
    } else if (!fin_(e->cross_slope_sigma)) {
        return "cross_slope_sigma is not finite";
    }
    if (!(e->confidence >= R(0.0) && e->confidence <= R(1.0))) {
        return "confidence outside 0..1";
    }
    if (e->aim_source > (uint8_t)GL_AIM_STRAIGHT || e->solve_status > (uint8_t)GL_SOLVE_INVALID) {
        return "aim_source or solve_status is not a defined code";
    }
    if (!(e->distance_m > R(0.0)) || !(e->a_r_mps2 > R(0.0)) || !(e->v0_mps > R(0.0))) {
        return "distance, a_r or v0 not positive";
    }
    if (!(e->stimp_ft >= R(5.0) && e->stimp_ft <= R(16.0))) {
        return "green speed outside 5..16";
    }
    if (!(e->phi_rad >= R(-1.2001) && e->phi_rad <= R(1.2001))) {
        return "aim beyond the search limit of 1.2 rad";
    }
    if ((uint32_t)e->n_rolls > roll_cap) {
        return "more trial rolls than 2 x (max_rolls + 120)";
    }
    if (e->n_steps > (uint32_t)e->n_rolls * 6004u) {
        return "more RK4 steps than 6004 per roll";
    }
    return NULL;
}

void GLV(hostile)(uint32_t seed, unsigned n, gl_vec_hostile_t *h)
{
    memset(h, 0, sizeof(*h));
    rng_ = (seed != 0u) ? seed : 1u;

    /* ---- gl_solver_estimate / gl_solver_estimate_survey ------------------------- */
    for (unsigned it = 0; it < n; it++) {
        gl_measurements_t drops[GL_SOLVER_MAX_DROPS];
        gl_solver_options_t opt;
        gl_estimate_t est;
        unsigned n_drops = 1u + rnd_() % GL_SOLVER_MAX_DROPS;
        unsigned ball = rnd_() % n_drops;
        const unsigned n_mut = rnd_() % 4u;
        const bool survey = (rnd_() % 3u) == 0u;
        const uint32_t null_what = rnd_() % 64u; /* 0: m, 1: opt, 2: work, 3: out */
        const char *why = NULL;
        gl_status_t st;

        for (unsigned i = 0; i < GL_SOLVER_MAX_DROPS; i++) {
            nominal_(&drops[i]);
        }
        for (unsigned i = 0; i < n_mut; i++) {
            mutate_(&drops[rnd_() % n_drops]);
        }
        hostile_options_(&opt);
        if (survey && rnd_() % 16u == 0u) {
            n_drops = rnd_() % 7u;      /* 0 .. 6: also out of range */
            ball = rnd_() % 7u;         /* also not a drop */
        }
        memset(&est, 0x5A, sizeof(est)); /* garbage: the call must overwrite all of it */
        est.base_hidden = false;
        est.flag_missing = false;
        est.range_missing = false;
        est.poor_horizon = false;
        est.fit_converged = false;
        if (survey) {
            st = gl_solver_estimate_survey((null_what == 0u) ? NULL : drops, n_drops, ball,
                                           (null_what == 1u) ? NULL : &opt,
                                           (null_what == 2u) ? NULL : &work_,
                                           (null_what == 3u) ? NULL : &est);
        } else {
            st = gl_solver_estimate((null_what == 0u) ? NULL : &drops[0],
                                    (null_what == 1u) ? NULL : &opt, (null_what == 2u) ? NULL : &work_,
                                    (null_what == 3u) ? NULL : &est);
        }
        h->calls++;
        if (null_what == 1u) {
            gl_solver_default_options(&opt); /* what the call used */
        }
        if (st == GL_OK) {
            h->ok++;
            if (null_what == 0u || null_what == 2u || null_what == 3u) {
                why = "GL_OK with a NULL argument";
            } else {
                why = check_estimate_(&est, &opt);
                if (why == NULL) {
                    h->by_source[est.aim_source]++;
                    h->by_status[est.solve_status]++;
                    h->not_converged += est.fit_converged ? 0u : 1u;
                    if (est.n_rolls > h->max_rolls) {
                        h->max_rolls = est.n_rolls;
                    }
                    if (est.n_steps > h->max_steps) {
                        h->max_steps = est.n_steps;
                    }
                    if (work_.fit.n_drops < 1u || work_.fit.n_drops > GL_SOLVER_MAX_DROPS) {
                        why = "fit record: n_drops out of range";
                    }
                }
            }
        } else if (st == GL_ERR_PARAM || st == GL_ERR_RANGE) {
            if (st == GL_ERR_PARAM) {
                h->err_param++;
            } else {
                h->err_range++;
            }
            if (null_what != 3u && !is_flagged_(&est)) {
                why = "error status but the output is not the flagged record";
            }
        } else {
            why = "status is none of GL_OK, GL_ERR_PARAM, GL_ERR_RANGE";
        }
        if (why != NULL) {
            violation_(h, why, h->calls);
        }
    }

    /* ---- gl_solver_solve_aim -------------------------------------------------------- */
    for (unsigned it = 0; it < n; it++) {
        gl_quad_surface_t sf;
        gl_solver_options_t opt;
        gl_aim_solution_t sol;
        gl_rvec2_t start, hole, grain;
        gl_real_t a_r = R(1.83 * 1.83) / (R(2.0) * range_(R(5.0), R(16.0)) * R(0.3048));
        const unsigned n_mut = rnd_() % 3u;
        const char *why = NULL;
        gl_status_t st;

        sf.a = range_(R(-0.05), R(0.05));
        sf.b = range_(R(-0.05), R(0.05));
        sf.c = range_(R(-0.01), R(0.01));
        sf.d = range_(R(-0.01), R(0.01));
        sf.e = range_(R(-0.01), R(0.01));
        sf.z0 = range_(R(-1.0), R(1.0));
        start.x = range_(R(-3.0), R(3.0));
        start.y = range_(R(-3.0), R(3.0));
        hole.x = start.x + range_(R(-12.0), R(12.0));
        hole.y = start.y + range_(R(-12.0), R(12.0));
        grain.x = range_(R(-0.1), R(0.1));
        grain.y = range_(R(-0.1), R(0.1));
        for (unsigned i = 0; i < n_mut; i++) {
            const gl_real_t v = nasty_();
            switch (rnd_() % 14u) {
            case 0u: sf.a = v; break;
            case 1u: sf.b = v; break;
            case 2u: sf.c = v; break;
            case 3u: sf.d = v; break;
            case 4u: sf.e = v; break;
            case 5u: sf.z0 = v; break;
            case 6u: start.x = v; break;
            case 7u: start.y = v; break;
            case 8u: hole.x = v; break;
            case 9u: hole.y = v; break;
            case 10u: grain.x = v; break;
            case 11u: grain.y = v; break;
            case 12u: a_r = v; break;
            default: hole = start; break; /* zero distance */
            }
        }
        hostile_options_(&opt);
        memset(&sol, 0x5A, sizeof(sol));
        st = gl_solver_solve_aim((rnd_() % 64u == 0u) ? NULL : &sf, start, hole, a_r, grain,
                                 (rnd_() % 64u == 0u) ? NULL : &opt, &sol);
        h->calls++;
        if (st == GL_OK) {
            h->ok++;
            if (sol.status > (uint8_t)GL_SOLVE_INVALID) {
                why = "solve_aim: status is not a defined code";
            } else if (sol.status != (uint8_t)GL_SOLVE_INVALID &&
                       !(fin_(sol.phi_rad) && fin_(sol.v0_mps) && sol.v0_mps > R(0.0))) {
                why = "solve_aim: GL_OK but phi or v0 is not finite";
            } else if ((sol.status == (uint8_t)GL_SOLVE_OK ||
                        sol.status == (uint8_t)GL_SOLVE_PACE_LIMITED) &&
                       !(fin_(sol.miss_m) && fin_(sol.v_hole_mps))) {
                why = "solve_aim: solved but miss or arrival speed is not finite";
            } else if ((uint32_t)sol.n_rolls > 1000u + 120u || sol.n_steps > (uint32_t)sol.n_rolls * 6004u) {
                why = "solve_aim: more rolls or steps than the bound";
            } else if (sol.n_steps > h->max_steps) {
                h->max_steps = sol.n_steps;
            }
        } else if (st == GL_ERR_PARAM || st == GL_ERR_RANGE) {
            if (st == GL_ERR_PARAM) {
                h->err_param++;
            } else {
                h->err_range++;
            }
            if (sol.status != (uint8_t)GL_SOLVE_INVALID || sol.phi_rad == sol.phi_rad ||
                sol.v0_mps == sol.v0_mps || (st == GL_ERR_PARAM && sol.n_rolls != 0u)) {
                why = "solve_aim: error status but the output is not the flagged record";
            }
        } else {
            why = "solve_aim: status is none of GL_OK, GL_ERR_PARAM, GL_ERR_RANGE";
        }
        if (why != NULL) {
            violation_(h, why, h->calls);
        }
    }

    /* ---- gl_solver_roll, gl_solver_fuse_range, gl_solver_quad_horizon ----------------- */
    for (unsigned it = 0; it < n; it++) {
        gl_quad_surface_t sf;
        gl_roll_result_t r;
        gl_range_estimate_t rng;
        gl_measurements_t m;
        gl_rvec2_t start, hole, grain;
        gl_real_t coeffs[5], e_tan, r_max;
        gl_real_t par[5];
        const char *why = NULL;
        gl_status_t st;

        sf.a = (rnd_() % 4u == 0u) ? nasty_() : range_(R(-0.1), R(0.1));
        sf.b = (rnd_() % 4u == 0u) ? nasty_() : range_(R(-0.1), R(0.1));
        sf.c = (rnd_() % 6u == 0u) ? nasty_() : range_(R(-0.02), R(0.02));
        sf.d = (rnd_() % 6u == 0u) ? nasty_() : range_(R(-0.02), R(0.02));
        sf.e = (rnd_() % 6u == 0u) ? nasty_() : range_(R(-0.02), R(0.02));
        sf.z0 = (rnd_() % 8u == 0u) ? nasty_() : R(0.0);
        start.x = (rnd_() % 8u == 0u) ? nasty_() : R(0.0);
        start.y = (rnd_() % 8u == 0u) ? nasty_() : R(0.0);
        hole.x = (rnd_() % 6u == 0u) ? nasty_() : range_(R(0.2), R(12.0));
        hole.y = (rnd_() % 8u == 0u) ? nasty_() : R(0.0);
        grain.x = (rnd_() % 8u == 0u) ? nasty_() : R(0.0);
        grain.y = (rnd_() % 8u == 0u) ? nasty_() : range_(R(-0.1), R(0.1));
        for (unsigned i = 0; i < 5u; i++) {
            par[i] = (rnd_() % 5u == 0u) ? nasty_() : range_(R(0.0), R(4.0));
        }
        memset(&r, 0x5A, sizeof(r));
        r.crossed_hole_line = false;
        r.captured = false;
        st = gl_solver_roll(&sf, start, hole, par[0] - R(2.0), par[1], par[2] * R(0.3) + R(0.05), grain,
                            (rnd_() % 2u == 0u) ? R(0.5) : par[3], (rnd_() % 2u) == 0u, &r);
        h->calls++;
        if (st == GL_OK) {
            h->ok++;
            if (r.status > (uint8_t)GL_ROLL_AT_LINE || r.n_steps > 6004u) {
                why = "roll: status not a defined code or more than 6004 steps";
            } else if (!(fin_(r.t_end_s) && fin_(r.stop_x) && fin_(r.stop_y) && fin_(r.delta_m) &&
                         fin_(r.speed_at_delta_mps) && fin_(r.lateral_miss_m) && fin_(r.shortfall_m) &&
                         fin_(r.path_length_m))) {
                why = "roll: GL_OK with a not-a-number in the result";
            } else if (r.crossed_hole_line != (fin_(r.lateral_at_line_m) && fin_(r.speed_at_line_mps))) {
                why = "roll: lateral_at_line / speed_at_line do not match crossed_hole_line";
            }
        } else if (st == GL_ERR_PARAM || st == GL_ERR_RANGE) {
            if (st == GL_ERR_PARAM) {
                h->err_param++;
            } else {
                h->err_range++;
            }
            if (r.status != (uint8_t)GL_ROLL_INVALID || r.n_steps != 0u || r.stop_x == r.stop_x) {
                why = "roll: error status but the output is not the flagged record";
            }
        } else {
            why = "roll: undefined status";
        }
        if (why != NULL) {
            violation_(h, why, h->calls);
        }

        nominal_(&m);
        mutate_(&m);
        mutate_(&m);
        gl_solver_fuse_range(&m, &rng); /* IEEE arithmetic only: must not trap; values are free */
        gl_solver_fuse_range(NULL, &rng);
        gl_solver_fuse_range(&m, NULL);
        h->calls += 3u;

        for (unsigned i = 0; i < 5u; i++) {
            coeffs[i] = (rnd_() % 4u == 0u) ? nasty_() : range_(R(-0.05), R(0.05));
        }
        st = gl_solver_quad_horizon((rnd_() % 32u == 0u) ? NULL : coeffs, par[0], par[1] * R(0.01),
                                    (rnd_() % 4u == 0u) ? nasty_() : R(0.15),
                                    (rnd_() % 4u == 0u) ? nasty_() : R(6.0), &e_tan, &r_max);
        h->calls++;
        if (st == GL_OK) {
            h->ok++;
            if (!(fin_(e_tan) && fin_(r_max) && r_max > R(0.0))) {
                violation_(h, "quad_horizon: GL_OK with a result that is not finite", h->calls);
            }
        } else if (st == GL_ERR_PARAM || st == GL_ERR_RANGE) {
            if (st == GL_ERR_PARAM) {
                h->err_param++;
            } else {
                h->err_range++;
            }
            if (e_tan == e_tan || r_max == r_max) {
                violation_(h, "quad_horizon: error status but the outputs are numbers", h->calls);
            }
        } else {
            violation_(h, "quad_horizon: undefined status", h->calls);
        }
    }
}

/* ---- API checks that need the solver's own types -------------------------------------- */

#define API_CHECK(cond)                                                                    \
    do {                                                                                   \
        if (!(cond)) {                                                                     \
            if (failed == 0u && why != NULL && why_len > 0u) {                             \
                snprintf(why, why_len, "%s:%d: %s", __FILE__, __LINE__, #cond);            \
            }                                                                              \
            failed++;                                                                      \
        }                                                                                  \
    } while (0)

unsigned GLV(api_checks)(char *why, unsigned why_len)
{
    unsigned failed = 0u;
    gl_measurements_t m, drops[GL_SOLVER_MAX_DROPS];
    gl_solver_options_t opt, bad;
    gl_estimate_t e;
    gl_aim_solution_t a;
    gl_roll_result_t r;
    gl_quad_surface_t sf = { R(0.01), R(0.02), R(0.0), R(0.0), R(0.0), R(0.0) };
    const gl_rvec2_t p0 = { R(0.0), R(0.0) }, p1 = { R(3.0), R(0.0) }, g0 = { R(0.0), R(0.0) };
    gl_real_t coeffs[5] = { R(0.0), R(0.0), R(0.0), R(0.0), R(0.0) }, e_tan, r_max;

    if (why != NULL && why_len > 0u) {
        why[0] = '\0';
    }
    /* version and defaults */
    API_CHECK(gl_solver_version() == GL_SOLVER_VERSION && GL_SOLVER_VERSION != 0u);
    gl_solver_default_options(NULL); /* NULL is safe */
    gl_solver_measurements_init(NULL);
    gl_solver_default_options(&opt);
    /* the reference's 0.30: exactly that double in the comparison build (it
     * used to be the float nearest to it, 0.30000001192092896, there too) */
#ifdef GL_SOLVER_DOUBLE
    API_CHECK(opt.past_m == 0.30);
#else
    API_CHECK(opt.past_m == 0.30f);
#endif
    API_CHECK(opt.max_rolls == 200u && opt.lm_max_iter == 60u);
    API_CHECK(opt.near_miss_m == R(0.0) && opt.max_steps == 0u); /* off, as in the reference */
    API_CHECK(opt.method == (uint8_t)GL_SOLVER_METHOD_B1 && !opt.use_grain);
    API_CHECK(opt.tol_miss_m == R(GL_SOLVER_DEFAULT_TOL_MISS_M) &&
              opt.tol_pace_m == R(GL_SOLVER_DEFAULT_TOL_PACE_M) && opt.lm_tol == R(GL_SOLVER_DEFAULT_LM_TOL));
    gl_solver_measurements_init(&m);
    API_CHECK(m.f_px == R(657.0) && m.baseline_m > R(0.0199) && m.baseline_m < R(0.0201));
    API_CHECK(m.h_cam_m > R(0.0055) && m.h_cam_m < R(0.0057));
    API_CHECK(!m.flag_found && !m.flag_base_visible && !m.flag_top_visible && m.tilt_reads == 1u);
    API_CHECK(m.flag_bearing_rad != m.flag_bearing_rad && m.flag_disparity_px != m.flag_disparity_px &&
              m.flag_low_elev_rad != m.flag_low_elev_rad && m.user_distance_m != m.user_distance_m);
    API_CHECK(m.n_horizon == 0u && m.tilt_x == R(0.0) && m.tilt_y == R(0.0) && m.stimp_ft == R(10.0));

    /* "nothing measured" is a valid input: flag missing, default distance, straight line */
    API_CHECK(gl_solver_estimate(&m, &opt, &work_, &e) == GL_OK);
    API_CHECK(e.flag_missing && !e.range_missing && e.distance_m == R(3.0) && e.phi_rad == R(0.0));
    API_CHECK(e.aim_source == (uint8_t)GL_AIM_FROM_PATCH && e.solve_status == (uint8_t)GL_SOLVE_OK);
    API_CHECK(e.distance_sigma_m != e.distance_sigma_m && work_.fit.n_drops == 1u && work_.fit.n_starts == 0u);
    API_CHECK(gl_solver_estimate(&m, NULL, &work_, &e) == GL_OK); /* NULL options = defaults */

    /* NULL pointers */
    API_CHECK(gl_solver_estimate(NULL, &opt, &work_, &e) == GL_ERR_PARAM && is_flagged_(&e));
    API_CHECK(gl_solver_estimate(&m, &opt, NULL, &e) == GL_ERR_PARAM && is_flagged_(&e));
    API_CHECK(gl_solver_estimate(&m, &opt, &work_, NULL) == GL_ERR_PARAM);
    /* Survey arguments */
    for (unsigned i = 0; i < GL_SOLVER_MAX_DROPS; i++) {
        gl_solver_measurements_init(&drops[i]);
    }
    API_CHECK(gl_solver_estimate_survey(drops, 0u, 0u, &opt, &work_, &e) == GL_ERR_PARAM && is_flagged_(&e));
    API_CHECK(gl_solver_estimate_survey(drops, GL_SOLVER_MAX_DROPS + 1u, 0u, &opt, &work_, &e) == GL_ERR_PARAM);
    API_CHECK(gl_solver_estimate_survey(drops, 2u, 2u, &opt, &work_, &e) == GL_ERR_PARAM && is_flagged_(&e));
    API_CHECK(gl_solver_estimate_survey(NULL, 1u, 0u, &opt, &work_, &e) == GL_ERR_PARAM);
    API_CHECK(gl_solver_estimate_survey(drops, GL_SOLVER_MAX_DROPS, GL_SOLVER_MAX_DROPS - 1u, &opt, &work_, &e) ==
              GL_OK);
    /* options out of range */
    bad = opt;
    bad.past_m = R(-0.1);
    API_CHECK(gl_solver_estimate(&m, &bad, &work_, &e) == GL_ERR_PARAM && is_flagged_(&e));
    bad = opt;
    bad.tol_miss_m = R(NAN);
    API_CHECK(gl_solver_estimate(&m, &bad, &work_, &e) == GL_ERR_PARAM);
    bad = opt;
    bad.method = 4u;
    API_CHECK(gl_solver_estimate(&m, &bad, &work_, &e) == GL_ERR_PARAM);
    bad = opt;
    bad.max_rolls = (uint16_t)(GL_SOLVER_MAX_ROLLS_LIMIT + 1u);
    API_CHECK(gl_solver_estimate(&m, &bad, &work_, &e) == GL_ERR_PARAM);
    bad = opt;
    bad.lm_max_iter = (uint16_t)(GL_SOLVER_LM_MAX_ITER_LIMIT + 1u);
    API_CHECK(gl_solver_estimate(&m, &bad, &work_, &e) == GL_ERR_PARAM);
    /* inputs no placement produces */
    gl_solver_measurements_init(&m);
    m.f_px = R(0.0);
    API_CHECK(gl_solver_estimate(&m, &opt, &work_, &e) == GL_ERR_PARAM && is_flagged_(&e));
    gl_solver_measurements_init(&m);
    m.tilt_y = R(NAN);
    API_CHECK(gl_solver_estimate(&m, &opt, &work_, &e) == GL_ERR_PARAM);
    gl_solver_measurements_init(&m);
    m.stimp_ft = R(NAN);
    API_CHECK(gl_solver_estimate(&m, &opt, &work_, &e) == GL_ERR_PARAM);
    gl_solver_measurements_init(&m);
    m.n_horizon = (uint8_t)(GL_SOLVER_MAX_HORIZON + 1u);
    API_CHECK(gl_solver_estimate(&m, &opt, &work_, &e) == GL_ERR_PARAM);
    gl_solver_measurements_init(&m);
    m.stimp_ft = R(INFINITY); /* clipped like any other speed above 16 */
    API_CHECK(gl_solver_estimate(&m, &opt, &work_, &e) == GL_OK && e.stimp_ft == R(16.0));

    /* solve_aim */
    API_CHECK(gl_solver_solve_aim(&sf, p0, p1, R(0.549), g0, &opt, &a) == GL_OK &&
              a.status == (uint8_t)GL_SOLVE_OK && a.n_rolls > 0u && a.n_steps > 0u);
    API_CHECK(gl_solver_solve_aim(&sf, p0, p1, R(0.549), g0, NULL, &a) == GL_OK);
    API_CHECK(gl_solver_solve_aim(NULL, p0, p1, R(0.549), g0, &opt, &a) == GL_ERR_PARAM &&
              a.status == (uint8_t)GL_SOLVE_INVALID && a.phi_rad != a.phi_rad);
    API_CHECK(gl_solver_solve_aim(&sf, p0, p1, R(0.0), g0, &opt, &a) == GL_ERR_PARAM);
    API_CHECK(gl_solver_solve_aim(&sf, p0, p1, R(NAN), g0, &opt, &a) == GL_ERR_PARAM);
    API_CHECK(gl_solver_solve_aim(&sf, p0, p1, R(0.549), g0, &opt, NULL) == GL_ERR_PARAM);
    /* zero distance: the solver runs and says INVALID, as the reference does */
    API_CHECK(gl_solver_solve_aim(&sf, p0, p0, R(0.549), g0, &opt, &a) == GL_OK &&
              a.status == (uint8_t)GL_SOLVE_INVALID && a.n_rolls == 0u && a.phi_rad != a.phi_rad);

    /* roll */
    API_CHECK(gl_solver_roll(&sf, p0, p1, R(0.0), R(1.9), R(0.549), g0, R(0.5), false, &r) == GL_OK &&
              r.status == (uint8_t)GL_ROLL_STOPPED && r.n_steps > 0u);
    API_CHECK(gl_solver_roll(&sf, p0, p1, R(0.0), R(-1.0), R(0.549), g0, R(0.5), false, &r) == GL_ERR_PARAM &&
              r.status == (uint8_t)GL_ROLL_INVALID);
    API_CHECK(gl_solver_roll(&sf, p0, p1, R(0.0), R(1.0), R(0.549), g0, R(0.5), false, NULL) == GL_ERR_PARAM);

    /* quad_horizon */
    API_CHECK(gl_solver_quad_horizon(coeffs, R(0.0), R(0.005), R(0.15), R(6.0), &e_tan, &r_max) == GL_OK &&
              r_max == R(6.0));
    API_CHECK(gl_solver_quad_horizon(coeffs, R(0.0), R(0.0), R(0.15), R(6.0), &e_tan, &r_max) == GL_ERR_PARAM);
    API_CHECK(gl_solver_quad_horizon(coeffs, R(0.0), R(0.005), R(6.0), R(6.0), &e_tan, &r_max) == GL_ERR_PARAM);
    API_CHECK(gl_solver_quad_horizon(NULL, R(0.0), R(0.005), R(0.15), R(6.0), &e_tan, &r_max) == GL_ERR_PARAM);
    return failed;
}
