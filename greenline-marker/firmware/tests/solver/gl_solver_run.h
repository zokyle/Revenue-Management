/*
 * gl_solver_run.h - run reference-vector cases through the solver in either
 * precision (HOST TESTS ONLY).
 *
 * core/gl_solver.h describes ONE precision per translation unit (gl_real_t
 * is float, or double with -DGL_SOLVER_DOUBLE).  tests/solver/
 * gl_solver_run.c is therefore compiled twice by the Makefile and exports
 * the same functions under two prefixes:
 *
 *     gl_vec32_*   the firmware build  (gl_real_t = float)
 *     gl_vec64_*   the comparison build (gl_real_t = double)
 *
 * Inputs and results cross this interface as doubles and plain integers,
 * so tests/test_solver.c can compare the two builds with each other and
 * with the reference.
 */
#ifndef GL_SOLVER_RUN_H
#define GL_SOLVER_RUN_H

#include <stdint.h>

#include "gl_solver_vectors.h"

/** Which tolerances a case is run with. */
typedef enum {
    GL_VEC_TOL_CASE = 0,    /**< the tolerances the reference generated the case with (1e-9 m, 1e-10) */
    GL_VEC_TOL_DEFAULT = 1, /**< gl_solver_default_options() of the build */
    GL_VEC_TOL_SINGLE = 2   /**< the single-precision defaults, in whichever build */
} gl_vec_tol_t;

/** Result of one estimate (gl_estimate_t and the fit record, as doubles). */
typedef struct {
    int status;              /**< gl_status_t of the call */
    double phi, aim_azimuth_device, v0, plays_like, break_m, break_cups, distance, distance_sigma;
    double bearing, slope_pct, fall_line_azimuth, fall_line_azimuth_device, dz_hole, patch[5];
    double cross_slope_sigma, confidence, a_r, stimp_ft, grain[2];
    double level_offsets[2], range_stereo, range_mono, tilt_slopes[2], stations[4], fit_cost;
    double cov_diag[5], horizon_rms;
    uint8_t base_hidden, flag_missing, range_missing, poor_horizon, used_horizon, fit_converged;
    uint8_t aim_source, solve_status, fit_starts, n_stations;
    uint32_t n_rolls, n_steps, n_iter;
} gl_vec_est_result_t;

/** Result of one aim solve. */
typedef struct {
    int status;              /**< gl_status_t of the call */
    uint8_t solve_status;
    double phi, v0, v_hole, miss, distance;
    uint32_t n_rolls, n_steps;
} gl_vec_sol_result_t;

/** Result of one roll. */
typedef struct {
    int status;              /**< gl_status_t of the call */
    uint8_t roll_status, crossed, captured;
    int8_t side;
    double t_end, stop_xy[2], delta, speed_at_delta, lateral_at_line, speed_at_line;
    double lateral_miss, shortfall, path_length;
    uint32_t n_steps;
} gl_vec_roll_result_t;

/** Counters of the hostile-input run. */
typedef struct {
    unsigned calls;          /**< entry-point calls made */
    unsigned ok, err_param, err_range;
    unsigned violations;     /**< calls whose status or output was not defined */
    unsigned by_source[4];   /**< GL_OK estimates by aim_source */
    unsigned by_status[6];   /**< GL_OK estimates by solve_status */
    unsigned not_converged;
    uint32_t max_rolls, max_steps;
    char first_violation[200];
} gl_vec_hostile_t;

#define GL_VEC_DECLARE(prefix)                                                                      \
    /** Bits of gl_real_t in this build (32 or 64) and gl_solver_version(). */                      \
    unsigned prefix##_real_bits(void);                                                              \
    uint32_t prefix##_version(void);                                                                \
    /** sizeof of gl_solver_work_t, gl_measurements_t, gl_estimate_t in this build. */              \
    unsigned prefix##_sizeof(unsigned which);                                                       \
    /** One estimator case.  `ball_last`: hand the drops over with the one at the ball LAST and     \
     *  ball_index = n - 1 (the result must not depend on it).  */                                  \
    void prefix##_estimate(const gl_vec_est_case_t *c, gl_vec_tol_t tol, int ball_last,             \
                           gl_vec_est_result_t *out);                                               \
    void prefix##_solve(const gl_vec_sol_case_t *c, gl_vec_tol_t tol, gl_vec_sol_result_t *out);    \
    void prefix##_roll(const gl_vec_roll_case_t *c, gl_vec_roll_result_t *out);                     \
    /** Roll the launch (phi, v0) on a putt-frame patch, hole at (dist, 0): the trial the solver    \
     *  iterates on.  Returns 1 if the ball crossed the hole line; *lateral [m] and *speed [m/s]    \
     *  there. */                                                                                   \
    int prefix##_roll_patch(const double coeffs[5], double dist, double a_r, const double grain[2], \
                            double phi, double v0, double *lateral, double *speed);                 \
    /** Range fusion of one placement: distance, sigma, stereo, mono into out[4]. */                \
    void prefix##_fuse_range(const gl_vec_meas_t *m, double out[4]);                                \
    /** n pseudo-random hostile calls of every entry point (see gl_solver_run.c). */                \
    void prefix##_hostile(uint32_t seed, unsigned n, gl_vec_hostile_t *out);                        \
    /** The API checks that need the solver's own types (NULL pointers, options, init). */          \
    unsigned prefix##_api_checks(char *why, unsigned why_len)

GL_VEC_DECLARE(gl_vec32);
GL_VEC_DECLARE(gl_vec64);

#endif /* GL_SOLVER_RUN_H */
