/*
 * gl_solver_priv.h - internals shared by the gl_solver_*.c files.
 *
 * Not an interface: nothing outside core/gl_solver*.c includes this file.
 *
 * The code is written against gl_real_t (gl_solver.h).  Three things make
 * the same source compile for both precisions without a single implicit
 * double in the single-precision build (-Wdouble-promotion -Werror):
 *
 *   GLS_R(x)       a constant of the real type.  The cast is applied to a
 *                  constant expression, so it is folded at compile time;
 *   GLS_SQRT ...   the libm function of the real type (sqrtf / sqrt, ...);
 *   GLS_NAME(n)    the external name of an internal function (gls_n, or
 *                  gls64_n in the double build so that both link together).
 *
 * CONSTANTS.  Everything below is copied from the reference (physics.py and
 * EstimatorConfig in estimator.py) with the same values.  They are firmware
 * constants there too ("design values, not the simulator's truth").  Three
 * numbers of the reference are floating-point resolutions rather than
 * physical quantities (1e-13, 4e-15, 1e-15, all written for double); they
 * are expressed here as the same multiples of the machine epsilon so that
 * the single-precision build gets the equivalent thresholds.
 */
#ifndef GL_SOLVER_PRIV_H
#define GL_SOLVER_PRIV_H

#include <float.h>
#include <math.h>

#include "gl_solver.h"

#define GLS_R(x) ((gl_real_t)(x))

#ifdef GL_SOLVER_DOUBLE
#define GLS_SQRT(x) sqrt(x)
#define GLS_FABS(x) fabs(x)
#define GLS_SIN(x) sin(x)
#define GLS_COS(x) cos(x)
#define GLS_TAN(x) tan(x)
#define GLS_ATAN2(y, x) atan2((y), (x))
#define GLS_LOG(x) log(x)
#define GLS_ERF(x) erf(x)
#define GLS_POW(x, y) pow((x), (y))
#define GLS_HYPOT(x, y) hypot((x), (y))
#define GLS_NAME(n) gls64_##n
/* the reference's own literals */
#define GLS_W_TOL 1e-13          /* step fraction of a closest approach */
#define GLS_E_RESOLUTION 4e-15   /* relative resolution of the launch energy */
#define GLS_PHI_JUMP_MIN 1e-15   /* narrowest aim bracket, rad */
#else
#define GLS_SQRT(x) sqrtf(x)
#define GLS_FABS(x) fabsf(x)
#define GLS_SIN(x) sinf(x)
#define GLS_COS(x) cosf(x)
#define GLS_TAN(x) tanf(x)
#define GLS_ATAN2(y, x) atan2f((y), (x))
#define GLS_LOG(x) logf(x)
#define GLS_ERF(x) erff(x)
#define GLS_POW(x, y) powf((x), (y))
#define GLS_HYPOT(x, y) hypotf((x), (y))
#define GLS_NAME(n) gls_##n
/* the same multiples of the machine epsilon as the reference's literals
 * are of the double epsilon (450, 18 and 4.5) */
#define GLS_W_TOL (450.0f * FLT_EPSILON)
#define GLS_E_RESOLUTION (18.0f * FLT_EPSILON)
#define GLS_PHI_JUMP_MIN (4.5f * FLT_EPSILON)
#endif

/* ---- physics.py ----------------------------------------------------------- */

#define GLS_G GLS_R(9.80665)                      /* standard gravity, m/s^2 */
#define GLS_STIMP_V0_SQ GLS_R(1.83 * 1.83)        /* Stimpmeter release speed squared */
#define GLS_FT GLS_R(0.3048)
#define GLS_HOLE_R GLS_R(0.053975)
#define GLS_V_CAP0 GLS_R(1.63)                    /* dead-centre capture speed (Holmes) */
#define GLS_ROLL_FACTOR GLS_R(5.0 / 7.0)
#define GLS_KF GLS_R(5.0 / 7.0 * 9.80665)         /* gravity drive per unit slope */
#define GLS_DT GLS_R(0.02)                        /* RK4 step, s */
#define GLS_T_MAX GLS_R(30.0)
#define GLS_R_MAX GLS_R(100.0)
#define GLS_S_TINY GLS_R(1e-12)                   /* below this the ball is at rest */
#define GLS_V_EPS GLS_R(1e-4)                     /* below this the stop is closed analytically */
#define GLS_H_STIFF GLS_R(0.5)                    /* largest step * a_r / speed */
#define GLS_STEP_BUDGET_FACTOR 4u
#define GLS_LINE_MISS_OFFSET GLS_R(1.0)           /* far-crossing rule: 1 m + 0.5 D */
#define GLS_LINE_MISS_SLOPE GLS_R(0.5)
#define GLS_PHI_MAX GLS_R(1.2)                    /* search limit on |phi|, rad */
#define GLS_V_MAX GLS_R(15.0)                     /* search limit on the launch speed */
#define GLS_E_MIN GLS_R(1e-6)                     /* smallest launch energy tried */

/* pace-solve flags */
#define GLS_PACE_OK 0
#define GLS_PACE_LIMITED 1
#define GLS_PACE_UNREACHABLE 2
/* single precision only: a fit step of at most this many spacings of the
 * parameter it moves is "no step" (gl_solver_fit.c, fit_lm_) */
#define GLS_LM_STEP_ULPS GLS_R(4.0)
#define GLS_PACE_CUT 3 /* firmware only: the step budget ran out during the pace solve */

/* ---- EstimatorConfig (estimator.py) ---------------------------------------- */

#define GLS_SIGMA_SEAT GLS_R(2.5e-3)
#define GLS_SIGMA_TILT_BIAS GLS_R(1.0e-3)
#define GLS_SIGMA_GRAVITY GLS_R(0.3e-3)
#define GLS_SIGMA_LEVEL GLS_R(0.43e-3)
#define GLS_SIGMA_PIXEL_ELEV GLS_R(0.15)
#define GLS_SIGMA_DISP GLS_R(0.08)
#define GLS_SINK_MEAN GLS_R(0.75e-3)
#define GLS_SINK_SIGMA GLS_R(0.43e-3)
#define GLS_SIGMA_MIRAGE GLS_R(5.0e-5)
#define GLS_SIGMA_CURV GLS_R(0.004)
#define GLS_SIGMA_SLOPE_PRIOR GLS_R(0.05)
#define GLS_SIGMA_FIELD GLS_R(2.5e-3)
#define GLS_SIGMA_DROP_LATERAL GLS_R(0.15)
#define GLS_SIGMA_HORIZON GLS_R(1.0e-3)
#define GLS_HUBER_K GLS_R(1.5)
#define GLS_HORIZON_D_MIN GLS_R(0.15)
#define GLS_HORIZON_L_FACTOR GLS_R(1.5)
#define GLS_HORIZON_L_MIN GLS_R(6.0)
#define GLS_HORIZON_L_CAP GLS_R(20.0)
#define GLS_GRAIN_KAPPA_MAX GLS_R(0.25)
#define GLS_DEFAULT_DISTANCE GLS_R(3.0)
#define GLS_SIGMA_HAND_BEARING GLS_R(0.026179938779914945) /* radians(1.5) */
#define GLS_MIN_DISPARITY GLS_R(0.25)
#define GLS_STIMP_MIN GLS_R(5.0)
#define GLS_STIMP_MAX GLS_R(16.0)
#define GLS_LM_LAMBDA0 GLS_R(1e-4)
#define GLS_SIGMA_SILHOUETTE GLS_R(0.02)
#define GLS_POOR_HORIZON_FRACTION GLS_R(0.3)
#define GLS_CONF_TWIST_SIGMA GLS_R(0.002)
#define GLS_CONF_TWIST_LENGTH GLS_R(10.0)
#define GLS_CONF_GRAIN_KAPPA GLS_R(0.045)
#define GLS_CONF_GRAIN_REL GLS_R(0.45)
#define GLS_CONF_BASE_HIDDEN GLS_R(0.8)
#define GLS_CONF_FLAG_MISSING GLS_R(0.9)
#define GLS_CONF_RANGE_MISSING GLS_R(0.5)
#define GLS_CONF_POOR_HORIZON GLS_R(0.8)
#define GLS_CONF_AIM_FALLBACK GLS_R(0.7)
#define GLS_MIN_HORIZON_SAMPLES 5u
#define GLS_COST_TIE GLS_R(1e-9)                  /* two minima count as the same below this */
#define GLS_START_CURVATURE_ANCHORED GLS_R(0.003) /* corner starts of the anchored horizon fit */

/* ---- small helpers ---------------------------------------------------------- */

/** sqrt(x^2 + y^2) as the reference computes it (math.hypot): the libm
 *  function of the real type, which neither overflows nor loses the last
 *  bit for operands of any size.  Called a few times per estimate, never
 *  in the roll kernel. */
static inline gl_real_t gls_hypot(gl_real_t x, gl_real_t y)
{
    return GLS_HYPOT(x, y);
}

static inline bool gls_finite(gl_real_t x)
{
    return isfinite(x) != 0;
}

#define GLS_NAN GLS_R(NAN)

/* ---- roll kernel (gl_solver_roll.c) ------------------------------------------ */

/** Output record of one roll (reference: the `out` array of _roll). */
typedef struct {
    uint8_t status;       /* gl_roll_status_t */
    gl_real_t t, x, y, vx, vy;
    gl_real_t dmin, smin, tmin;
    int8_t side;
    bool crossed;
    gl_real_t yline, sline, tline;
    gl_real_t xprog, yprog, sprog;
    bool captured;
    gl_real_t tcapt;
    gl_real_t path;
    uint32_t n_step;
} gls_roll_out_t;

/** Constant arguments of a roll. */
typedef struct {
    const gl_quad_surface_t *sf;
    gl_real_t a_r, agx, agy;   /* deceleration and grain acceleration */
    gl_real_t hx, hy;          /* hole centre */
    gl_real_t dt, t_max, r_max;
    bool stop_at_line, stop_on_capture;
    gl_real_t v_cap0, cap_exp, hole_r;
} gls_roll_in_t;

#define gls_roll GLS_NAME(roll)
#define gls_surf_z GLS_NAME(surf_z)
#define gls_surf_grad GLS_NAME(surf_grad)

/** Reference: _roll.  Integrates one roll from (x, y) with velocity (vx, vy). */
void gls_roll(const gls_roll_in_t *in, gl_real_t x, gl_real_t y, gl_real_t vx, gl_real_t vy,
              gls_roll_out_t *out);
gl_real_t gls_surf_z(const gl_quad_surface_t *sf, gl_real_t x, gl_real_t y);
void gls_surf_grad(const gl_quad_surface_t *sf, gl_real_t x, gl_real_t y, gl_real_t *gx,
                   gl_real_t *gy);

/* ---- aim solver (gl_solver_aim.c) --------------------------------------------- */

/** Result record of the solve kernel (reference: the `res` array). */
typedef struct {
    gl_real_t phi, v0, miss, vhole;
    uint32_t n_rolls;
    uint32_t n_steps;
    bool budget_spent;  /* the step budget ran out: the solve was cut short */
} gls_solve_res_t;

#define gls_solve_kernel GLS_NAME(solve_kernel)

/** Reference: _solve_kernel.  Returns a gl_solve_status_t.
 *  `max_steps` (0 = none; NOT in the reference): budget of RK4 steps, of
 *  which `steps_used` are spent already (by an earlier solve of the same
 *  estimate); checked before every trial roll.  When it runs out the solve
 *  ends GL_SOLVE_NO_CONVERGENCE with the best iterate it had
 *  (res->budget_spent); with nothing left at the start that is the planar
 *  first guess, and nothing is rolled. */
uint8_t gls_solve_kernel(const gl_quad_surface_t *sf, gl_real_t sx, gl_real_t sy, gl_real_t hx,
                         gl_real_t hy, gl_real_t a_r, gl_real_t agx, gl_real_t agy, gl_real_t v_h,
                         gl_real_t dt, gl_real_t t_max, gl_real_t r_max, gl_real_t tol_y,
                         gl_real_t tol_dist, gl_real_t phi_max, gl_real_t v_max,
                         uint32_t max_rolls, uint32_t max_steps, uint32_t steps_used,
                         gls_solve_res_t *res);

/* ---- fit (gl_solver_fit.c) ---------------------------------------------------- */

#define gls_fit_patch GLS_NAME(fit_patch)
#define gls_options_ok GLS_NAME(options_ok)

/**
 * Reference: fit_patch.  `order` lists the drops, the one at the ball
 * first.  Fills work->fit.  Returns GL_OK, GL_ERR_PARAM (an input the
 * reference cannot use) or GL_ERR_RANGE (non-finite result).
 */
gl_status_t gls_fit_patch(const gl_measurements_t *drops, const uint8_t *order, unsigned n_drops,
                          uint8_t method, const gl_solver_options_t *opt, gl_solver_work_t *work);

/** True if every field of the options is usable. */
bool gls_options_ok(const gl_solver_options_t *opt);

#endif /* GL_SOLVER_PRIV_H */
