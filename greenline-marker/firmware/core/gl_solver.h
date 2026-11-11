/*
 * gl_solver.h - interface of the putt estimator and solver (PHASE 2).
 *
 * The maths behind these functions is being finished in the Python
 * reference (sim/greenline_sim: measurements.py, estimator.py, physics.py)
 * and will be ported to C99 in phase 2, tested against vectors exported
 * from the reference.  Phase 1 ships this header and gl_solver_stub.c, in
 * which every function returns GL_ERR_NOT_IMPLEMENTED and
 * gl_solver_version() returns 0.  The application and the UI are written
 * against this interface and show a tilt-and-bearing-only screen while the
 * stub is linked.
 *
 * The data structures mirror the reference one to one so that exported
 * vectors map onto them field by field:
 *     gl_measurements_t   <->  greenline_sim.measurements.Measurements
 *     gl_estimate_t       <->  greenline_sim.estimator.Estimate
 *     gl_aim_solution_t   <->  greenline_sim.physics.AimSolution
 *     gl_quad_surface_t   <->  greenline_sim.physics.QuadraticSurface
 *
 * FRAME.  Everything here is in the reference's DEVICE frame: origin at
 * the marker, +x out of the visor (firmware marker +y), +y to the left
 * (firmware marker -x), angles counter-clockwise from +x.  A firmware
 * bearing (counter-clockwise from marker forward) is therefore already a
 * device-frame azimuth; a marker-frame slope vector is converted with
 * gl_tilt_slope_to_device().  SI units, radians, slopes as rise/run.
 *
 * Constraints the port must keep: C99, no allocation, no recursion,
 * single-precision float, bounded run time (the reference solve uses at
 * most 200 trial rolls).
 */
#ifndef GL_SOLVER_H
#define GL_SOLVER_H

#include "gl_types.h"

/** Samples of the turf horizon across the field (reference: n_horizon = 41). */
#define GL_SOLVER_MAX_HORIZON 41u
/** Placements in a Survey. */
#define GL_SOLVER_MAX_DROPS 4u

/** Hole radius, metres (108 mm cup). */
#define GL_SOLVER_HOLE_RADIUS_M 0.053975f

/** One placement of the marker, exactly as the estimator receives it. */
typedef struct {
    float f_px;                 /**< focal length, px */
    float baseline_m;           /**< stereo baseline */
    float h_cam_m;              /**< optical axis above the base plane */
    float tilt_x, tilt_y;       /**< measured surface gradient (dz/dx, dz/dy), device frame */
    uint8_t tilt_reads;         /**< 1 = single placement, 2 = spin-and-reread */
    bool flag_found;            /**< false: all flag_* fields are invalid */
    float flag_bearing_rad;     /**< + = left of the visor axis */
    float flag_disparity_px;    /**< f * baseline / range, with "range" the DISTANCE to the
                                     stick as the reference defines it: pass the rectified
                                     disparity (which measures depth) times cos(bearing) */
    float flag_low_elev_rad;    /**< elevation of the lowest visible point of the stick */
    bool flag_base_visible;     /**< true: that point is the base at the hole lip */
    bool flag_top_visible;
    float flag_top_elev_rad;    /**< elevation of the top (valid if flag_top_visible) */
    float stick_height_est_m;   /**< learned (or prior) visible stick height */
    float stick_height_rel_sigma;
    uint8_t n_horizon;          /**< number of turf-horizon samples, 0 = none */
    float horizon_az_rad[GL_SOLVER_MAX_HORIZON];   /**< device-frame azimuth of each sample */
    float horizon_elev_rad[GL_SOLVER_MAX_HORIZON]; /**< elevation of the turf silhouette; NaN = invalid */
    float grain_kappa;          /**< grain strength (push = kappa * a_r), 0 = none */
    float grain_azimuth_rad;    /**< direction the grain pushes the ball, device frame */
    float stimp_ft;             /**< green speed entered by the golfer */
    float user_distance_m;      /**< dialled distance (flag-out fallback); NaN otherwise */
} gl_measurements_t;

/** Outcome of the aim solve (values match SolveStatus in physics.py). */
typedef enum {
    GL_SOLVE_OK = 0,             /**< through the hole centre at the target pace */
    GL_SOLVE_PACE_LIMITED = 1,   /**< through the centre, cannot arrive as slowly as asked */
    GL_SOLVE_UNREACHABLE = 2,
    GL_SOLVE_NO_BRACKET = 3,
    GL_SOLVE_NO_CONVERGENCE = 4,
    GL_SOLVE_INVALID = 5,
    GL_SOLVE_NOT_RUN = 255       /**< firmware only: the solver is the phase-1 stub */
} gl_solve_status_t;

/** z = z0 + a x + b y + 0.5 (c x^2 + 2 d x y + e y^2). */
typedef struct {
    float a, b;       /**< slopes dz/dx, dz/dy at the origin */
    float c, d, e;    /**< curvatures z_xx, z_xy, z_yy, 1/m */
    float z0;
} gl_quad_surface_t;

/** Result of gl_solver_solve_aim(). */
typedef struct {
    float phi_rad;          /**< launch direction relative to the straight ball->hole line, + = left */
    float v0_mps;           /**< launch speed */
    uint8_t status;         /**< gl_solve_status_t */
    float distance_m;       /**< straight ball->hole distance */
    float a_r_mps2;         /**< rolling deceleration used */
    float v_hole_target_mps;
    float v_hole_mps;       /**< arrival speed of the returned putt (NaN if unknown) */
    float miss_m;           /**< residual lateral miss at the hole line, + = left (NaN if unknown) */
    uint16_t n_rolls;       /**< trial rolls used */
} gl_aim_solution_t;

/** What the device shows for one read. */
typedef struct {
    float phi_rad;                  /**< aim relative to the line to the hole, + = aim left */
    float aim_azimuth_device_rad;   /**< the aim line in the device frame: bearing + phi */
    float v0_mps;
    float plays_like_m;             /**< flat-green distance with the same launch speed */
    float break_m;                  /**< D tan(phi), + = aim left of the hole */
    float break_cups;               /**< the same in cup widths */
    float distance_m, distance_sigma_m;
    float bearing_rad;              /**< direction of the hole in the device frame */
    float slope_pct;                /**< slope magnitude at the ball */
    float fall_line_azimuth_device_rad;
    float dz_hole_m;                /**< fitted height of the hole above the ball */
    float patch[5];                 /**< fitted (a, b, c, d, e), putt frame */
    float cross_slope_sigma;        /**< posterior 1-sigma of the mean cross slope */
    float confidence;               /**< 0..1 */
    bool base_hidden, flag_missing, poor_horizon;
    uint8_t aim_source;             /**< 0 fitted patch, 1 secant plane, 2 best iterate, 3 straight */
    uint8_t solve_status;           /**< gl_solve_status_t */
    float a_r_mps2;
    float stimp_ft;
    float grain_x, grain_y;         /**< kappa * g_hat used, putt frame */
} gl_estimate_t;

/** Options (reference: EstimatorConfig / solve_aim keyword arguments). */
typedef struct {
    float past_m;        /**< target roll-out past the hole on a flat green (reference default 0.30) */
    uint16_t max_rolls;  /**< budget of trial rolls (reference default 200) */
} gl_solver_options_t;

/** Version of the ported solver: 0 while the phase-1 stub is linked. */
uint32_t gl_solver_version(void);

/** Reference defaults: past 0.30 m, 200 rolls. */
void gl_solver_default_options(gl_solver_options_t *opt);

/**
 * Estimate the putt from ONE placement (Quick Read, or Precision Read when
 * m->tilt_reads == 2).  Reference: estimator.estimate().
 * Phase 1: returns GL_ERR_NOT_IMPLEMENTED and sets out->solve_status to
 * GL_SOLVE_NOT_RUN.
 */
gl_status_t gl_solver_estimate(const gl_measurements_t *m, const gl_solver_options_t *opt,
                               gl_estimate_t *out);

/**
 * Estimate the putt from the drops of a Survey.  `ball_index` is the drop
 * taken at the ball: the result's device-frame angles refer to that drop.
 * Reference: estimator.estimate_survey() (which takes the ball drop first).
 * Phase 1: GL_ERR_NOT_IMPLEMENTED.
 */
gl_status_t gl_solver_estimate_survey(const gl_measurements_t *drops, unsigned n_drops,
                                      unsigned ball_index, const gl_solver_options_t *opt,
                                      gl_estimate_t *out);

/**
 * Launch direction and speed that hole a putt from `start` to `hole` on a
 * quadratic surface at the target pace.  grain = kappa * g_hat in the
 * surface frame.  Reference: physics.solve_aim().
 * Phase 1: GL_ERR_NOT_IMPLEMENTED.
 */
gl_status_t gl_solver_solve_aim(const gl_quad_surface_t *surface, gl_vec2_t start, gl_vec2_t hole,
                                float a_r_mps2, gl_vec2_t grain, const gl_solver_options_t *opt,
                                gl_aim_solution_t *out);

/**
 * Convenience (implemented in phase 1, pure bookkeeping): clear a
 * measurement record to "nothing measured": flag not found, NaN where the
 * reference uses NaN, nominal camera constants from gl_config.h.
 */
void gl_solver_measurements_init(gl_measurements_t *m);

#endif /* GL_SOLVER_H */
