/*
 * gl_solver.h - the putt estimator and the aim solver (PHASE 2: the port).
 *
 * C99 port of the Python reference in sim/greenline_sim:
 *
 *     physics.py     _roll, _trial, _solve_pace, _solve_kernel   -> gl_solver_roll.c, gl_solver_aim.c
 *     estimator.py   fuse_range, _fit_*, fit_patch               -> gl_solver_fit.c
 *     estimator.py   estimate_batch, _confidence                 -> gl_solver.c
 *
 * The data structures mirror the reference one to one so that exported
 * vectors map onto them field by field:
 *     gl_measurements_t   <->  greenline_sim.measurements.Measurements
 *     gl_estimate_t       <->  greenline_sim.estimator.Estimate
 *     gl_patch_fit_t      <->  greenline_sim.estimator.PatchFit
 *     gl_range_estimate_t <->  greenline_sim.estimator.RangeEstimate
 *     gl_aim_solution_t   <->  greenline_sim.physics.AimSolution
 *     gl_quad_surface_t   <->  greenline_sim.physics.QuadraticSurface
 *
 * ONE SOURCE, TWO PRECISIONS.  All numerical code is written against
 * gl_real_t.  The firmware (and the normal host build) compiles it with
 * gl_real_t = float: single precision only, as the Cortex-M33 FPU requires.
 * The host tests ALSO compile the same files with -DGL_SOLVER_DOUBLE
 * (gl_real_t = double), which is the build that is compared digit by digit
 * with the Python reference.  In that build every external symbol is renamed
 * gl_solver64_* / gls64_* (macros below), so that both precisions link into
 * one test executable.  Firmware code never defines GL_SOLVER_DOUBLE.
 *
 * FRAME.  Everything here is in the reference's DEVICE frame: origin at
 * the marker, +x out of the visor (firmware marker +y), +y to the left
 * (firmware marker -x), angles counter-clockwise from +x.  A firmware
 * bearing (counter-clockwise from marker forward) is therefore already a
 * device-frame azimuth; a marker-frame slope vector is converted with
 * gl_tilt_slope_to_device().  SI units, radians, slopes as rise/run.
 *
 * "NOT AVAILABLE" IS NaN (or the matching flag).  The estimator does its
 * own range fusion (the reference's fuse_range); the firmware gates what
 * it measured BEFORE calling it: a disparity it does not trust is passed as
 * NaN, a stick top in clutter as flag_top_visible = false, a base that was
 * not followed into the turf as flag_base_visible = false.  It never passes
 * a synthesised disparity.
 *
 * RUN TIME is bounded: no loop without a counter.  One aim solve uses at
 * most max_rolls + 120 trial rolls (reference: the budget is checked
 * between pace solves, each of which uses at most 121), one roll at most
 * 6004 RK4 steps, the fit at most lm_max_iter x 25 residual evaluations per
 * start.  gl_aim_solution_t.n_steps / gl_estimate_t.n_steps report the RK4
 * steps actually spent (the cost driver; see README "Solver").
 *
 * MEMORY.  No heap, no recursion, no statics.  The fit needs a caller-
 * supplied work area (gl_solver_work_t, 5.3 kB in single precision); the
 * aim solve needs none.  Stack: see README.
 */
#ifndef GL_SOLVER_H
#define GL_SOLVER_H

#include "gl_types.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ---- precision ----------------------------------------------------------- */

#ifdef GL_SOLVER_DOUBLE
/* HOST ONLY: the comparison build.  Same source, double precision, renamed
 * symbols. */
typedef double gl_real_t;
typedef struct { double x, y; } gl_rvec2_t;
#define GL_SOLVER_REAL_BITS 64
#define gl_solver_version            gl_solver64_version
#define gl_solver_default_options    gl_solver64_default_options
#define gl_solver_measurements_init  gl_solver64_measurements_init
#define gl_solver_estimate           gl_solver64_estimate
#define gl_solver_estimate_survey    gl_solver64_estimate_survey
#define gl_solver_solve_aim          gl_solver64_solve_aim
#define gl_solver_roll               gl_solver64_roll
#define gl_solver_fuse_range         gl_solver64_fuse_range
#define gl_solver_quad_horizon       gl_solver64_quad_horizon
#else
/** The real type of the solver: single precision in the firmware. */
typedef float gl_real_t;
typedef gl_vec2_t gl_rvec2_t;
#define GL_SOLVER_REAL_BITS 32
#endif

/** Version of the ported solver (0 was the phase-1 stub).  0x00MMmmpp. */
#define GL_SOLVER_VERSION 0x00020000u

/** Samples of the turf horizon across the field (reference: n_horizon = 41). */
#define GL_SOLVER_MAX_HORIZON 41u
/** Placements in a Survey. */
#define GL_SOLVER_MAX_DROPS 4u
/** Largest budget of trial rolls a caller may ask for. */
#define GL_SOLVER_MAX_ROLLS_LIMIT 1000u
/** Residual rows of the fit: tilt-x, tilt-y and hole height per drop, plus
 *  the horizon samples. */
#define GL_SOLVER_MAX_LIN_ROWS (3u * GL_SOLVER_MAX_DROPS)
#define GL_SOLVER_MAX_ROWS (GL_SOLVER_MAX_LIN_ROWS + GL_SOLVER_MAX_HORIZON)
/** Fit parameters: a, b, c, d, e, level pitch offset, level roll offset. */
#define GL_SOLVER_NPAR 7u

/** Hole radius, metres (108 mm cup). */
#define GL_SOLVER_HOLE_RADIUS_M 0.053975f

/* ---- inputs --------------------------------------------------------------- */

/** One placement of the marker, exactly as the estimator receives it. */
typedef struct {
    gl_real_t f_px;                 /**< focal length, px (> 0) */
    gl_real_t baseline_m;           /**< stereo baseline (> 0) */
    gl_real_t h_cam_m;              /**< optical axis above the base plane */
    gl_real_t tilt_x, tilt_y;       /**< measured surface gradient (dz/dx, dz/dy), device frame */
    uint8_t tilt_reads;             /**< 1 = single placement, 2 = spin-and-reread */
    bool flag_found;                /**< false: all flag_* fields are ignored */
    gl_real_t flag_bearing_rad;     /**< + = left of the visor axis; NaN = no bearing (as flag not found) */
    gl_real_t flag_disparity_px;    /**< f * baseline / range, with "range" the DISTANCE to the
                                         stick as the reference defines it: pass the rectified
                                         disparity (which measures depth) times cos(bearing).
                                         NaN = no stereo range (never a synthesised value) */
    gl_real_t flag_low_elev_rad;    /**< elevation of the lowest visible point of the stick; NaN = none */
    bool flag_base_visible;         /**< true: that point is the base at the hole lip */
    bool flag_top_visible;
    gl_real_t flag_top_elev_rad;    /**< elevation of the top (used if flag_top_visible) */
    gl_real_t stick_height_est_m;   /**< learned (or prior) visible stick height */
    gl_real_t stick_height_rel_sigma;
    uint8_t n_horizon;              /**< number of turf-horizon samples, 0 = none */
    gl_real_t horizon_az_rad[GL_SOLVER_MAX_HORIZON];   /**< device-frame azimuth of each sample */
    gl_real_t horizon_elev_rad[GL_SOLVER_MAX_HORIZON]; /**< elevation of the turf silhouette; NaN = invalid */
    gl_real_t grain_kappa;          /**< grain strength (push = kappa * a_r), 0 = none */
    gl_real_t grain_azimuth_rad;    /**< direction the grain pushes the ball, device frame */
    gl_real_t stimp_ft;             /**< green speed entered by the golfer (clipped to 5..16) */
    gl_real_t user_distance_m;      /**< dialled distance; used only when the cameras give none.
                                         NaN or <= 0: the default (3 m) is used then */
} gl_measurements_t;

/** Estimation method (reference: the `method` argument of estimate()). */
typedef enum {
    GL_SOLVER_METHOD_B1 = 0,       /**< DEFAULT: tilt + flag-base height (Quick Read, Precision
                                        Read with tilt_reads = 2, Survey with several drops) */
    GL_SOLVER_METHOD_B0 = 1,       /**< plane from the tilt only */
    GL_SOLVER_METHOD_B2 = 2,       /**< B1 + turf horizon, anchored fit.  OFF by default: in
                                        simulation it only helps on greens without a fringe */
    GL_SOLVER_METHOD_STRAIGHT = 3  /**< baseline: straight at the hole at flat-green pace */
} gl_solver_method_t;

/**
 * Options (reference: EstimatorConfig fields that are not constants of the
 * firmware, and the keyword arguments of solve_aim).  Fill with
 * gl_solver_default_options() and change what is needed.
 */
typedef struct {
    gl_real_t past_m;       /**< target roll-out past the hole on a flat green (reference 0.30) */
    uint16_t max_rolls;     /**< budget of trial rolls per aim solve (reference 200);
                                 at most GL_SOLVER_MAX_ROLLS_LIMIT */
    uint8_t method;         /**< gl_solver_method_t; default GL_SOLVER_METHOD_B1 */
    bool use_grain;         /**< use grain_kappa / grain_azimuth_rad; default false (the grain
                                 sensor ships disabled) */
    gl_real_t tol_miss_m;   /**< aim solve: tolerance on the lateral miss at the hole line */
    gl_real_t tol_pace_m;   /**< aim solve: tolerance on pace, as flat roll-out distance */
    gl_real_t lm_tol;       /**< fit: convergence tolerance on the scaled step (slopes in
                                 units of 1e-2, curvatures and offsets in 1e-3) */
    uint16_t lm_max_iter;   /**< fit: Levenberg-Marquardt iteration limit per start */
} gl_solver_options_t;

/* Default tolerances.  Double (host comparison build): the reference's own
 * defaults.  Single precision: the tightest values at which the iterations
 * terminate on their tolerance rather than on rounding noise (measured; see
 * README "Solver" for the numbers and tests/test_solver.c for the bounds). */
#ifdef GL_SOLVER_DOUBLE
#define GL_SOLVER_DEFAULT_TOL_MISS_M 1e-5
#define GL_SOLVER_DEFAULT_TOL_PACE_M 1e-5
#define GL_SOLVER_DEFAULT_LM_TOL 1e-9
#else
#define GL_SOLVER_DEFAULT_TOL_MISS_M 1e-4f
#define GL_SOLVER_DEFAULT_TOL_PACE_M 1e-3f
#define GL_SOLVER_DEFAULT_LM_TOL 1e-3f
#endif
#define GL_SOLVER_DEFAULT_PAST_M 0.30f
#define GL_SOLVER_DEFAULT_MAX_ROLLS 200u
#define GL_SOLVER_DEFAULT_LM_MAX_ITER 60u

/* ---- outputs -------------------------------------------------------------- */

/** Outcome of the aim solve (values match SolveStatus in physics.py). */
typedef enum {
    GL_SOLVE_OK = 0,             /**< through the hole centre at the target pace */
    GL_SOLVE_PACE_LIMITED = 1,   /**< through the centre, cannot arrive as slowly as asked */
    GL_SOLVE_UNREACHABLE = 2,    /**< the ball cannot be made to reach the hole line */
    GL_SOLVE_NO_BRACKET = 3,     /**< no aim angle within +-1.2 rad brackets the hole */
    GL_SOLVE_NO_CONVERGENCE = 4, /**< miss discontinuous in the aim angle, or roll budget spent */
    GL_SOLVE_INVALID = 5,        /**< invalid input (zero distance, ...) */
    GL_SOLVE_NOT_RUN = 255       /**< firmware only: no solve was attempted (output of a call
                                      that returned an error before solving) */
} gl_solve_status_t;

/** Where the aim of an estimate comes from (reference: aim_source). */
typedef enum {
    GL_AIM_FROM_PATCH = 0,   /**< solved on the fitted quadratic patch */
    GL_AIM_FROM_PLANE = 1,   /**< patch not solvable: solved on its secant plane */
    GL_AIM_BEST_EFFORT = 2,  /**< neither solvable: best iterate of the plane solve */
    GL_AIM_STRAIGHT = 3      /**< no usable solution at all: straight at flat pace */
} gl_aim_source_t;

/** z = z0 + a x + b y + 0.5 (c x^2 + 2 d x y + e y^2). */
typedef struct {
    gl_real_t a, b;       /**< slopes dz/dx, dz/dy at the origin */
    gl_real_t c, d, e;    /**< curvatures z_xx, z_xy, z_yy, 1/m */
    gl_real_t z0;
} gl_quad_surface_t;

/** Result of gl_solver_solve_aim(). */
typedef struct {
    gl_real_t phi_rad;          /**< launch direction relative to the straight ball->hole line, + = left */
    gl_real_t v0_mps;           /**< launch speed */
    uint8_t status;             /**< gl_solve_status_t */
    gl_real_t distance_m;       /**< straight ball->hole distance */
    gl_real_t a_r_mps2;         /**< rolling deceleration used */
    gl_real_t v_hole_target_mps;
    gl_real_t v_hole_mps;       /**< arrival speed of the returned putt (NaN if unknown) */
    gl_real_t miss_m;           /**< residual lateral miss at the hole line, + = left (NaN if unknown) */
    uint16_t n_rolls;           /**< trial rolls used */
    uint32_t n_steps;           /**< RK4 steps used by those rolls (firmware diagnostic) */
} gl_aim_solution_t;

/** Range to the flagstick from one placement (reference: RangeEstimate).
 *  NaN = that channel is not available. */
typedef struct {
    gl_real_t distance_m, sigma_m;         /**< fused */
    gl_real_t stereo_m, sigma_stereo_m;
    gl_real_t mono_m, sigma_mono_m;        /**< from the stick's angular height */
} gl_range_estimate_t;

/** The fitted patch and its diagnostics (reference: PatchFit). */
typedef struct {
    gl_real_t coeffs[5];            /**< (a, b, c, d, e), putt frame */
    gl_real_t cov[5][5];            /**< posterior covariance (Gauss-Newton; two-stage for the
                                         anchored horizon fit); NaN if it could not be formed */
    gl_real_t level_offsets[2];     /**< fitted pitch / roll offset of the level reference */
    gl_real_t distance_m;           /**< ball->hole distance used */
    gl_real_t distance_sigma_m;     /**< NaN = unknown (dialled or default distance) */
    gl_real_t bearing_rad;          /**< direction of the hole, device frame (0 if flag_missing) */
    gl_range_estimate_t range;      /**< range channels of the placement at the ball */
    gl_real_t tilt_slopes[2];       /**< tilt of the placement at the ball, putt frame */
    gl_real_t cross_sigma_read;     /**< 1-sigma of the mean cross slope from the tilt readings */
    uint8_t n_drops;                /**< placements used by the fit */
    gl_real_t stations_m[GL_SOLVER_MAX_DROPS]; /**< their stations along the line */
    bool base_hidden;               /**< hole height only bounded (base of the stick hidden) */
    bool flag_missing;              /**< no flagstick: tilt-only plane along the visor axis */
    bool range_missing;             /**< flag found, bearing used, but no range channel */
    bool used_horizon, poor_horizon;
    gl_real_t horizon_rms;          /**< in units of sigma_horizon; NaN if unused */
    uint16_t n_iter;                /**< Levenberg-Marquardt iterations of the run that was kept */
    bool converged;
    gl_real_t cost, cost_first_start;
    uint8_t n_starts;               /**< 0 no fit, 1 B1, 5 B2 with a horizon */
} gl_patch_fit_t;

/** What the device shows for one read. */
typedef struct {
    gl_real_t phi_rad;                  /**< aim relative to the line to the hole, + = aim left */
    gl_real_t aim_azimuth_device_rad;   /**< the aim line in the device frame: bearing + phi */
    gl_real_t v0_mps;
    gl_real_t plays_like_m;             /**< flat-green distance with the same launch speed */
    gl_real_t break_m;                  /**< D tan(phi), + = aim left of the hole */
    gl_real_t break_cups;               /**< the same in cup widths */
    gl_real_t distance_m;
    gl_real_t distance_sigma_m;         /**< NaN = unknown (dialled or default distance) */
    gl_real_t bearing_rad;              /**< direction of the hole in the device frame */
    gl_real_t slope_pct;                /**< slope magnitude at the ball (the tilt reading) */
    gl_real_t fall_line_azimuth_rad;    /**< steepest descent at the ball, putt frame */
    gl_real_t fall_line_azimuth_device_rad;
    gl_real_t dz_hole_m;                /**< fitted height of the hole above the ball */
    gl_real_t patch[5];                 /**< fitted (a, b, c, d, e), putt frame */
    gl_real_t cross_slope_sigma;        /**< 1-sigma of the mean cross slope (NaN for STRAIGHT) */
    gl_real_t confidence;               /**< 0..1 */
    bool base_hidden, flag_missing, range_missing, poor_horizon;
    bool fit_converged;                 /**< false: the fit stopped on its iteration limit */
    uint8_t aim_source;                 /**< gl_aim_source_t */
    uint8_t solve_status;               /**< gl_solve_status_t of the solve that produced the aim */
    gl_real_t a_r_mps2;
    gl_real_t stimp_ft;                 /**< green speed used (after clipping) */
    gl_real_t grain_x, grain_y;         /**< kappa * g_hat used, putt frame */
    uint16_t n_rolls;                   /**< trial rolls of all aim solves of this estimate */
    uint32_t n_steps;                   /**< RK4 steps of those rolls */
} gl_estimate_t;

/**
 * Work area of the fit.  Supplied by the caller (no statics in core); its
 * content between calls is of no interest EXCEPT `fit`: after a
 * gl_solver_estimate*() call that returned GL_OK it holds the fit record
 * of that estimate (the reference's Estimate.fit).
 */
typedef struct {
    gl_patch_fit_t fit;
    gl_real_t rows[GL_SOLVER_MAX_LIN_ROWS][GL_SOLVER_NPAR];  /**< linear rows / sigma */
    gl_real_t targets[GL_SOLVER_MAX_LIN_ROWS];
    uint8_t one_sided[GL_SOLVER_MAX_LIN_ROWS];
    gl_real_t hz[GL_SOLVER_MAX_HORIZON][3];                  /**< tan(elev), cos, sin per sample */
    gl_real_t r[2][GL_SOLVER_MAX_ROWS];                      /**< residuals: current / trial */
    gl_real_t jac[2][GL_SOLVER_MAX_ROWS][GL_SOLVER_NPAR];
    gl_real_t second[2][GL_SOLVER_MAX_ROWS];
    uint8_t outlier_prev[GL_SOLVER_MAX_ROWS];
} gl_solver_work_t;

/** How a roll ended (values match RollStatus / the kernel codes in physics.py). */
typedef enum {
    GL_ROLL_STOPPED = 0,        /**< at rest */
    GL_ROLL_MAX_TIME = 1,       /**< still moving after 30 s or 6004 steps */
    GL_ROLL_OUT_OF_BOUNDS = 2,  /**< further than r_max from the start */
    GL_ROLL_CAPTURED = 3,       /**< stopped after capture (stop_on_capture) */
    GL_ROLL_AT_LINE = 4,        /**< stopped at the hole line (solver trials) */
    GL_ROLL_INVALID = 255       /**< invalid input: nothing was rolled */
} gl_roll_status_t;

/** Result of gl_solver_roll() (reference: PuttResult without the trajectory). */
typedef struct {
    uint8_t status;                 /**< gl_roll_status_t */
    gl_real_t t_end_s;
    gl_real_t stop_x, stop_y;       /**< last integrated position */
    gl_real_t delta_m;              /**< closest approach to the hole centre */
    gl_real_t speed_at_delta_mps;
    int8_t side;                    /**< +1 passed left of the hole, -1 right, 0 centre / undefined */
    bool crossed_hole_line;
    gl_real_t lateral_at_line_m;    /**< + = left of the hole; NaN if the line was not reached */
    gl_real_t speed_at_line_mps;    /**< NaN if the line was not reached */
    gl_real_t lateral_miss_m;       /**< lateral_at_line, or the offset at the furthest progress */
    gl_real_t shortfall_m;          /**< 0 if the line was reached */
    bool captured;
    gl_real_t path_length_m;
    uint32_t n_steps;
} gl_roll_result_t;

/* ---- functions ------------------------------------------------------------ */

/** GL_SOLVER_VERSION (non-zero: the solver is real). */
uint32_t gl_solver_version(void);

/** Reference defaults: past 0.30 m, 200 rolls, method B1, grain not used,
 *  60 fit iterations; tolerances GL_SOLVER_DEFAULT_TOL_* / _LM_TOL. */
void gl_solver_default_options(gl_solver_options_t *opt);

/**
 * Clear a measurement record to "nothing measured": flag not found, NaN
 * where the reference uses NaN, nominal camera constants from gl_config.h.
 */
void gl_solver_measurements_init(gl_measurements_t *m);

/**
 * Estimate the putt from ONE placement (Quick Read, or Precision Read when
 * m->tilt_reads == 2).  Reference: estimator.estimate().
 *
 * Returns GL_OK when an estimate was produced.  That INCLUDES the
 * fallbacks, which are part of the reference and are reported in the
 * output: flag_missing / range_missing (tilt-only plane at the dialled or
 * default distance), aim_source 1..3 with the solve_status that caused it,
 * fit_converged false.  Every real of the output is then finite, except
 * distance_sigma_m and cross_slope_sigma where NaN means "unknown".
 *
 * Returns GL_ERR_PARAM for an input the reference rejects or cannot use
 * (NULL pointer; non-finite or non-positive f_px / baseline_m; non-finite
 * h_cam_m, tilt or stimp_ft; n_horizon > 41; non-finite horizon azimuth of
 * a valid sample; options out of range), GL_ERR_RANGE when the arithmetic
 * left the finite range (absurd but finite inputs).  The output is then
 * the "explicitly flagged" record: all reals 0, solve_status
 * GL_SOLVE_NOT_RUN, aim_source GL_AIM_STRAIGHT, confidence 0.
 *
 * `opt` may be NULL (defaults).  `work` must not be NULL.
 */
gl_status_t gl_solver_estimate(const gl_measurements_t *m, const gl_solver_options_t *opt,
                               gl_solver_work_t *work, gl_estimate_t *out);

/**
 * Estimate the putt from the drops of a Survey (1..GL_SOLVER_MAX_DROPS).
 * `ball_index` is the drop taken at the ball: it defines the putt frame,
 * the distance and the device-frame angles of the result, and supplies the
 * horizon, the green speed and the grain.  The other drops are used in
 * array order; a drop whose flag was not found or not ranged is ignored.
 * Reference: estimator.estimate_survey() (which takes the ball drop first).
 * Status and output as gl_solver_estimate(); n_drops == 0, n_drops >
 * GL_SOLVER_MAX_DROPS or ball_index >= n_drops give GL_ERR_PARAM.
 */
gl_status_t gl_solver_estimate_survey(const gl_measurements_t *drops, unsigned n_drops,
                                      unsigned ball_index, const gl_solver_options_t *opt,
                                      gl_solver_work_t *work, gl_estimate_t *out);

/**
 * Launch direction and speed that hole a putt from `start` to `hole` on a
 * quadratic surface at the target pace.  grain = kappa * g_hat in the
 * surface frame.  Uses opt->past_m, max_rolls, tol_miss_m, tol_pace_m
 * (`opt` may be NULL).  Reference: physics.solve_aim().
 *
 * Returns GL_OK when the solver ran; out->status then tells how it ended
 * and the best iterate is returned also on failure.  Returns GL_ERR_PARAM
 * for an input the reference rejects (non-finite surface, positions,
 * grain; a_r not positive and finite; past negative; start == hole);
 * out->status is then GL_SOLVE_INVALID, phi / v0 / miss / v_hole are NaN.
 */
gl_status_t gl_solver_solve_aim(const gl_quad_surface_t *surface, gl_rvec2_t start, gl_rvec2_t hole,
                                gl_real_t a_r_mps2, gl_rvec2_t grain,
                                const gl_solver_options_t *opt, gl_aim_solution_t *out);

/**
 * Roll one putt (the kernel the solver iterates on) with the reference's
 * capture model: launch at `phi_rad` from the start->hole line with speed
 * `v0_mps`.  capture_exponent 0.5 is the reference default (1.0: Penner);
 * v_cap0 is 1.63 m/s.  stop_on_capture ends the roll once the ball is
 * holed and has reached the hole line.  Reference: physics.simulate_putt()
 * / roll_batch() on a QuadraticSurface, dt 0.02 s, t_max 30 s, r_max 100 m.
 * Not used by the firmware's read path; it is here so that the kernel and
 * the capture model can be tested against the reference.
 * Returns GL_ERR_PARAM (status GL_ROLL_INVALID) for non-finite input,
 * a_r not positive or v0 negative.
 */
gl_status_t gl_solver_roll(const gl_quad_surface_t *surface, gl_rvec2_t start, gl_rvec2_t hole,
                           gl_real_t phi_rad, gl_real_t v0_mps, gl_real_t a_r_mps2,
                           gl_rvec2_t grain, gl_real_t capture_exponent, bool stop_on_capture,
                           gl_roll_result_t *out);

/** Range to the flagstick of one placement: stereo fused with the stick's
 *  angular height.  Reference: estimator.fuse_range(). */
void gl_solver_fuse_range(const gl_measurements_t *m, gl_range_estimate_t *out);

/**
 * Turf horizon of a quadratic patch seen from height h_cam above its
 * origin, along the ray at azimuth `theta_rad`: the tangent of the horizon
 * elevation and the distance at which it occurs.  Reference:
 * estimator.quad_horizon().  Returns GL_ERR_PARAM unless h_cam > 0 and
 * far_limit > d_min > 0.
 */
gl_status_t gl_solver_quad_horizon(const gl_real_t coeffs[5], gl_real_t theta_rad, gl_real_t h_cam_m,
                                   gl_real_t d_min_m, gl_real_t far_limit_m,
                                   gl_real_t *tan_horizon, gl_real_t *r_max_m);

#ifdef __cplusplus
}
#endif
#endif /* GL_SOLVER_H */
