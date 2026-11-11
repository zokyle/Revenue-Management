/* gl_solver_ref.c - see gl_solver_ref.h.  Compiled with -DGL_SOLVER_DOUBLE only. */
#include "gl_solver_ref.h"

#include <string.h>

#include "gl_solver.h"

#ifndef GL_SOLVER_DOUBLE
#error "tests/solver/gl_solver_ref.c is the double-precision comparison build"
#endif

static gl_solver_work_t work_;
static gl_measurements_t meas_[GL_REF_MAX_DROPS];

static void to_meas_(const gl_ref_meas_t *r, gl_measurements_t *m)
{
    gl_solver_measurements_init(m);
    m->f_px = r->f_px;
    m->baseline_m = r->baseline;
    m->h_cam_m = r->h_cam;
    m->tilt_x = r->tilt[0];
    m->tilt_y = r->tilt[1];
    m->tilt_reads = (uint8_t)r->tilt_reads;
    m->flag_found = r->flag_found != 0;
    m->flag_bearing_rad = r->flag_bearing;
    m->flag_disparity_px = r->flag_disparity;
    m->flag_low_elev_rad = r->flag_low_elev;
    m->flag_base_visible = r->flag_base_visible != 0;
    m->flag_top_visible = r->flag_top_visible != 0;
    m->flag_top_elev_rad = r->flag_top_elev;
    m->stick_height_est_m = r->stick_height_est;
    m->stick_height_rel_sigma = r->stick_height_rel_sigma;
    m->n_horizon = (uint8_t)((r->n_horizon <= GL_REF_MAX_HORIZON) ? r->n_horizon : GL_REF_MAX_HORIZON);
    for (unsigned i = 0; i < m->n_horizon; i++) {
        m->horizon_az_rad[i] = r->horizon_az[i];
        m->horizon_elev_rad[i] = r->horizon_elev[i];
    }
    m->grain_kappa = r->grain_kappa;
    m->grain_azimuth_rad = r->grain_azimuth;
    m->stimp_ft = r->stimp_ft;
    m->user_distance_m = r->user_distance;
}

void gl_ref_estimate(const gl_ref_meas_t *drops, unsigned n, unsigned ball, const gl_ref_opt_t *opt,
                     gl_ref_est_t *out)
{
    gl_solver_options_t o;
    gl_estimate_t e;
    gl_status_t st;

    memset(out, 0, sizeof(*out));
    if (n == 0u || n > GL_REF_MAX_DROPS) {
        out->status = (int)GL_ERR_PARAM;
        return;
    }
    for (unsigned i = 0; i < n; i++) {
        to_meas_(&drops[i], &meas_[i]);
    }
    gl_solver_default_options(&o); /* the double build: the reference's own defaults */
    o.method = (uint8_t)opt->method;
    o.past_m = opt->past;
    if (opt->tight != 0) {
        o.tol_miss_m = 1e-9;
        o.tol_pace_m = 1e-9;
        o.lm_tol = 1e-10;
        o.lm_max_iter = 200;
    }
    if (n == 1u) {
        st = gl_solver_estimate(&meas_[0], &o, &work_, &e);
    } else {
        st = gl_solver_estimate_survey(meas_, n, ball, &o, &work_, &e);
    }
    out->status = (int)st;
    out->phi = e.phi_rad;
    out->aim_azimuth_device = e.aim_azimuth_device_rad;
    out->v0 = e.v0_mps;
    out->plays_like = e.plays_like_m;
    out->break_m = e.break_m;
    out->break_cups = e.break_cups;
    out->distance = e.distance_m;
    out->distance_sigma = e.distance_sigma_m;
    out->bearing = e.bearing_rad;
    out->slope_pct = e.slope_pct;
    out->fall_line_azimuth_device = e.fall_line_azimuth_device_rad;
    out->dz_hole = e.dz_hole_m;
    out->confidence = e.confidence;
    for (int i = 0; i < 5; i++) {
        out->patch[i] = e.patch[i];
    }
    out->base_hidden = e.base_hidden;
    out->flag_missing = e.flag_missing;
    out->range_missing = e.range_missing;
    out->poor_horizon = e.poor_horizon;
    out->fit_converged = e.fit_converged;
    out->aim_source = e.aim_source;
    out->solve_status = e.solve_status;
    if (st == GL_OK) {
        out->used_horizon = work_.fit.used_horizon;
        out->n_starts = work_.fit.n_starts;
        out->n_drops_used = work_.fit.n_drops;
    }
}
