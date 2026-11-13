/*
 * gl_solver_ref.h - the DOUBLE-PRECISION build of the solver, callable from
 * a test that is itself compiled for the firmware's single precision (HOST
 * TESTS ONLY).
 *
 * core/gl_solver.h describes one precision per translation unit, so
 * tests/solver/gl_solver_ref.c is compiled with -DGL_SOLVER_DOUBLE and
 * offers the estimator behind plain doubles and integers.  The double build
 * is the one that tests/test_solver.c and `make diff` compare with the
 * Python reference (0 cases outside the tolerance on the vectors, 0
 * disagreements on 20000 random reads); the end-to-end tests use it as "the
 * reference" for the very record the application built, and
 * tools/app_diff.py checks that again against the Python package itself.
 */
#ifndef GL_SOLVER_REF_H
#define GL_SOLVER_REF_H

#define GL_REF_MAX_HORIZON 41
#define GL_REF_MAX_DROPS 4

/** One placement (greenline_sim.measurements.Measurements); NaN = not available. */
typedef struct {
    double f_px, baseline, h_cam, tilt[2];
    int tilt_reads, flag_found, flag_base_visible, flag_top_visible;
    double flag_bearing, flag_disparity, flag_low_elev, flag_top_elev;
    double stick_height_est, stick_height_rel_sigma;
    int n_horizon;
    double horizon_az[GL_REF_MAX_HORIZON], horizon_elev[GL_REF_MAX_HORIZON];
    double grain_kappa, grain_azimuth, stimp_ft, user_distance;
} gl_ref_meas_t;

typedef struct {
    int method;              /**< gl_solver_method_t */
    double past;
    int tight;               /**< 1: the tolerances of the reference vectors (1e-9 m, 1e-10,
                                  200 iterations); 0: the reference's defaults (1e-5, 1e-9, 60) */
    int use_grain;           /**< EstimatorConfig.use_grain (the GRAIN setting) */
    double near_miss;        /**< EstimatorConfig.near_miss_keep [m] (the application: 0.005) */
} gl_ref_opt_t;

typedef struct {
    int status;              /**< gl_status_t */
    double phi, aim_azimuth_device, v0, plays_like, break_m, break_cups, distance, distance_sigma;
    double bearing, slope_pct, fall_line_azimuth_device, dz_hole, confidence, patch[5];
    int base_hidden, flag_missing, range_missing, poor_horizon, fit_converged, used_horizon;
    int aim_source, solve_status, n_starts, n_drops_used;
} gl_ref_est_t;

/** Estimate from 1..4 placements; `ball` is the index of the one at the ball. */
void gl_ref_estimate(const gl_ref_meas_t *drops, unsigned n, unsigned ball, const gl_ref_opt_t *opt,
                     gl_ref_est_t *out);

#endif /* GL_SOLVER_REF_H */
