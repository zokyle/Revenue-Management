/*
 * gl_solver_stub.c - PHASE-1 PLACEHOLDER for the putt estimator / solver.
 *
 * Every solving function returns GL_ERR_NOT_IMPLEMENTED.  Phase 2 replaces
 * this file with the C99 port of sim/greenline_sim (estimator.py and
 * physics.py) and removes it from the build.  Nothing here computes a putt.
 */
#include "gl_solver.h"

#include <math.h>
#include <string.h>

#include "gl_config.h"

uint32_t gl_solver_version(void)
{
    return 0u; /* stub */
}

void gl_solver_default_options(gl_solver_options_t *opt)
{
    opt->past_m = 0.30f;
    opt->max_rolls = 200;
}

void gl_solver_measurements_init(gl_measurements_t *m)
{
    memset(m, 0, sizeof(*m));
    m->f_px = GL_CFG_CAM_F_PX;
    m->baseline_m = GL_CFG_CAM_BASELINE_M;
    m->h_cam_m = GL_CFG_CAM_AXIS_HEIGHT_M;
    m->tilt_reads = 1;
    m->flag_found = false;
    m->flag_bearing_rad = NAN;
    m->flag_disparity_px = NAN;
    m->flag_low_elev_rad = NAN;
    m->flag_top_elev_rad = NAN;
    m->stick_height_est_m = NAN;
    m->stick_height_rel_sigma = NAN;
    m->user_distance_m = NAN;
    for (unsigned i = 0; i < GL_SOLVER_MAX_HORIZON; i++) {
        m->horizon_az_rad[i] = NAN;
        m->horizon_elev_rad[i] = NAN;
    }
}

static void estimate_not_run_(gl_estimate_t *out)
{
    if (out != NULL) {
        memset(out, 0, sizeof(*out));
        out->solve_status = (uint8_t)GL_SOLVE_NOT_RUN;
        out->aim_source = 3; /* "straight": nothing was solved */
    }
}

gl_status_t gl_solver_estimate(const gl_measurements_t *m, const gl_solver_options_t *opt,
                               gl_estimate_t *out)
{
    (void)m;
    (void)opt;
    estimate_not_run_(out);
    return GL_ERR_NOT_IMPLEMENTED;
}

gl_status_t gl_solver_estimate_survey(const gl_measurements_t *drops, unsigned n_drops,
                                      unsigned ball_index, const gl_solver_options_t *opt,
                                      gl_estimate_t *out)
{
    (void)drops;
    (void)n_drops;
    (void)ball_index;
    (void)opt;
    estimate_not_run_(out);
    return GL_ERR_NOT_IMPLEMENTED;
}

gl_status_t gl_solver_solve_aim(const gl_quad_surface_t *surface, gl_vec2_t start, gl_vec2_t hole,
                                float a_r_mps2, gl_vec2_t grain, const gl_solver_options_t *opt,
                                gl_aim_solution_t *out)
{
    (void)surface;
    (void)start;
    (void)hole;
    (void)a_r_mps2;
    (void)grain;
    (void)opt;
    if (out != NULL) {
        memset(out, 0, sizeof(*out));
        out->status = (uint8_t)GL_SOLVE_NOT_RUN;
    }
    return GL_ERR_NOT_IMPLEMENTED;
}
