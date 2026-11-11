/*
 * gl_solver_fit.c - range fusion and the MAP fit of the quadratic patch.
 *
 * Port of estimator.py (fuse_range, quad_horizon, _chol_solve,
 * _fit_residuals, _fit_cost, _fit_gauss, _fit_lm, _cross_sigma_read,
 * _tilt_only_fit, fit_patch) with the firmware's fixed configuration:
 * use_flag_base, the ANCHORED horizon fit with its 5 starts.  Statement
 * order and operation order follow the reference.
 *
 * Not ported (comparison-only switches of the reference): the joint
 * horizon fit (horizon_joint), horizon_free_c, assume_base_visible, a
 * caller-supplied start.
 *
 * The patch is z = a x + b y + 0.5 (c x^2 + 2 d x y + e y^2) in the putt
 * frame; the fit parameters are x = (a, b, c, d, e, pitch offset, roll
 * offset).  Data rows, all divided by their sigma, in this order: for every
 * located placement its tilt-x row, its tilt-y row and (if the stick's
 * lowest point was measured) its hole-height row; then the horizon samples.
 *
 * Bounded: the Levenberg-Marquardt loop runs at most lm_max_iter passes,
 * each with at most 25 damping trials (lambda only grows inside a pass,
 * from >= 1e-12 to 1e12 in steps of 10); at most 1 + 5 runs per fit.
 * Memory: everything larger than a few reals is in the caller's
 * gl_solver_work_t.
 */
#include "gl_solver_priv.h"

/* indices into gl_solver_work_t.mat */
#define M_HESS 0  /* LM: iteration matrix */
#define M_GAUSS 1 /* LM: Gauss-Newton matrix of the current iterate */
#define M_CHOL 2  /* LM: damped matrix / its Cholesky factor; scratch for the covariance */
#define M_QUICK 3 /* fit: Gauss-Newton matrix of the Quick-Read (stage 1) solution */
#define M_BEST 4  /* fit: Gauss-Newton matrix of the run that is kept */
#define M_CAND 5  /* fit: Gauss-Newton matrix of the run being tried */

#define NPAR GL_SOLVER_NPAR

/* ---- range fusion ------------------------------------------------------------ */

/**
 * Reference: fuse_range.  Returns false if the arithmetic divided by zero
 * (a range channel of zero distance, or weights that vanish): the
 * reference raises ZeroDivisionError there, the estimator returns
 * GL_ERR_RANGE.  `out` is filled either way (IEEE results).
 */
static bool fuse_range_(const gl_measurements_t *m, gl_range_estimate_t *out)
{
    gl_real_t fb, stereo, sig_s, mono, sig_m;
    bool ok = true;

    out->distance_m = GLS_NAN;
    out->sigma_m = GLS_NAN;
    out->stereo_m = GLS_NAN;
    out->sigma_stereo_m = GLS_NAN;
    out->mono_m = GLS_NAN;
    out->sigma_mono_m = GLS_NAN;
    if (!m->flag_found) {
        return true;
    }
    fb = m->f_px * m->baseline_m;
    stereo = GLS_NAN;
    sig_s = GLS_NAN;
    if (gls_finite(m->flag_disparity_px) && m->flag_disparity_px >= GLS_MIN_DISPARITY) {
        stereo = fb / m->flag_disparity_px;
        sig_s = stereo * stereo * GLS_SIGMA_DISP / fb;
        ok = ok && (fb != GLS_R(0.0));
    }
    mono = GLS_NAN;
    sig_m = GLS_NAN;
    /* the angular height is used only when the top is in the field AND the
     * base is visible (a hidden base would bias the range long) */
    if (m->flag_top_visible && m->flag_base_visible && gls_finite(m->flag_top_elev_rad) &&
        gls_finite(m->flag_low_elev_rad)) {
        const gl_real_t span = GLS_TAN(m->flag_top_elev_rad) - GLS_TAN(m->flag_low_elev_rad);
        if (span > GLS_R(0.02)) {
            const gl_real_t pix = GLS_SIGMA_PIXEL_ELEV / m->f_px;
            const gl_real_t q = pix / span;
            mono = m->stick_height_est_m / span;
            sig_m = mono * GLS_SQRT(m->stick_height_rel_sigma * m->stick_height_rel_sigma +
                                    GLS_R(2.0) * (q * q));
        }
    }
    if (gls_finite(stereo) && gls_finite(mono)) {
        /* inverse-variance fusion; the stereo sigma is re-evaluated at the
         * fused range once, so that a low stereo reading does not get extra
         * weight just because it is low */
        gl_real_t dist = stereo;
        gl_real_t sig = sig_s;
        for (int it = 0; it < 2; it++) {
            const gl_real_t ws = GLS_R(1.0) / (sig_s * sig_s);
            const gl_real_t wm = GLS_R(1.0) / (sig_m * sig_m);
            ok = ok && (sig_s * sig_s != GLS_R(0.0)) && (sig_m * sig_m != GLS_R(0.0)) &&
                 (ws + wm != GLS_R(0.0));
            dist = (ws * stereo + wm * mono) / (ws + wm);
            sig = GLS_R(1.0) / GLS_SQRT(ws + wm);
            sig_s = dist * dist * GLS_SIGMA_DISP / fb;
        }
        out->distance_m = dist;
        out->sigma_m = sig;
        out->stereo_m = stereo;
        out->sigma_stereo_m = stereo * stereo * GLS_SIGMA_DISP / fb;
        out->mono_m = mono;
        out->sigma_mono_m = sig_m;
    } else if (gls_finite(stereo)) {
        out->distance_m = stereo;
        out->sigma_m = sig_s;
        out->stereo_m = stereo;
        out->sigma_stereo_m = sig_s;
    } else if (gls_finite(mono)) {
        out->distance_m = mono;
        out->sigma_m = sig_m;
        out->mono_m = mono;
        out->sigma_mono_m = sig_m;
    }
    return ok;
}

void gl_solver_fuse_range(const gl_measurements_t *m, gl_range_estimate_t *out)
{
    if (out == NULL) {
        return;
    }
    if (m == NULL) {
        out->distance_m = GLS_NAN;
        out->sigma_m = GLS_NAN;
        out->stereo_m = GLS_NAN;
        out->sigma_stereo_m = GLS_NAN;
        out->mono_m = GLS_NAN;
        out->sigma_mono_m = GLS_NAN;
        return;
    }
    (void)fuse_range_(m, out);
}

/** RangeEstimate.valid */
static bool range_valid_(const gl_range_estimate_t *r)
{
    return gls_finite(r->distance_m) && r->distance_m > GLS_R(0.0);
}

/* ---- horizon forward model ------------------------------------------------------ */

/**
 * Horizon of the ray with slope A and curvature K seen from height h:
 * E = max over d_min <= r <= far of A + 0.5 K r - h / r.  K >= 0: at the far
 * limit.  K < 0: at the crest r* = sqrt(2 h / |K|), clipped to the interval.
 * Returns the distance of the maximum; *interior says whether it is the
 * crest itself (then E is curved in K, else linear).
 */
static gl_real_t horizon_r_max_(gl_real_t curv, gl_real_t h_cam, gl_real_t d_min, gl_real_t far,
                                bool *interior)
{
    gl_real_t r_max = far; /* concave-up or flat ray: the horizon is at the far limit */
    *interior = false;
    if (curv < GLS_R(0.0)) {
        const gl_real_t r_star = GLS_SQRT(GLS_R(2.0) * h_cam / (-curv));
        if (r_star <= d_min) {
            r_max = d_min;
        } else if (r_star < far) {
            r_max = r_star;
            *interior = true;
        }
    }
    return r_max;
}

gl_status_t gl_solver_quad_horizon(const gl_real_t coeffs[5], gl_real_t theta_rad, gl_real_t h_cam_m,
                                   gl_real_t d_min_m, gl_real_t far_limit_m,
                                   gl_real_t *tan_horizon, gl_real_t *r_max_m)
{
    gl_real_t ct, st, slope, curv, r_max;
    bool interior;

    gl_real_t e_tan;

    if (tan_horizon == NULL || r_max_m == NULL) {
        return GL_ERR_PARAM;
    }
    *tan_horizon = GLS_NAN;
    *r_max_m = GLS_NAN;
    if (coeffs == NULL ||
        !(h_cam_m > GLS_R(0.0) && far_limit_m > d_min_m && d_min_m > GLS_R(0.0)) ||
        !gls_finite(theta_rad) || !gls_finite(h_cam_m) || !gls_finite(far_limit_m)) {
        return GL_ERR_PARAM;
    }
    ct = GLS_COS(theta_rad);
    st = GLS_SIN(theta_rad);
    slope = coeffs[0] * ct + coeffs[1] * st;
    curv = coeffs[2] * ct * ct + GLS_R(2.0) * coeffs[3] * st * ct + coeffs[4] * st * st;
    r_max = horizon_r_max_(curv, h_cam_m, d_min_m, far_limit_m, &interior);
    e_tan = slope + GLS_R(0.5) * curv * r_max - h_cam_m / r_max;
    if (!gls_finite(e_tan) || !gls_finite(r_max)) {
        return GL_ERR_RANGE; /* coefficients that are not numbers, or absurd */
    }
    *tan_horizon = e_tan;
    *r_max_m = r_max;
    return GL_OK;
}

/* ---- linear algebra -------------------------------------------------------------- */

/** In-place Cholesky factorisation of the leading n x n block (lower
 *  factor).  False if a pivot is not positive (not positive definite to
 *  rounding, or not a number). */
static bool chol_factor_(gl_real_t mat[NPAR][NPAR], unsigned n)
{
    for (unsigned j = 0; j < n; j++) {
        gl_real_t acc = mat[j][j];
        gl_real_t piv;
        for (unsigned k = 0; k < j; k++) {
            acc -= mat[j][k] * mat[j][k];
        }
        if (!(acc > GLS_R(0.0))) {
            return false;
        }
        piv = GLS_SQRT(acc);
        mat[j][j] = piv;
        for (unsigned i = j + 1u; i < n; i++) {
            acc = mat[i][j];
            for (unsigned k = 0; k < j; k++) {
                acc -= mat[i][k] * mat[j][k];
            }
            mat[i][j] = acc / piv;
        }
    }
    return true;
}

/** Solve L L^T out = rhs with the factor from chol_factor_(). */
static void chol_subst_(gl_real_t mat[NPAR][NPAR], const gl_real_t *rhs, unsigned n, gl_real_t *out)
{
    for (unsigned i = 0; i < n; i++) {
        gl_real_t acc = rhs[i];
        for (unsigned k = 0; k < i; k++) {
            acc -= mat[i][k] * out[k];
        }
        out[i] = acc / mat[i][i];
    }
    for (unsigned i = n; i-- > 0u;) {
        gl_real_t acc = out[i];
        for (unsigned k = i + 1u; k < n; k++) {
            acc -= mat[k][i] * out[k];
        }
        out[i] = acc / mat[i][i];
    }
}

/** Reference: _chol_solve.  `mat` is overwritten by its lower factor. */
static bool chol_solve_(gl_real_t mat[NPAR][NPAR], const gl_real_t *rhs, unsigned n, gl_real_t *out)
{
    if (!chol_factor_(mat, n)) {
        return false;
    }
    chol_subst_(mat, rhs, n, out);
    return true;
}

/**
 * Inverse of the symmetric positive-definite block src[off .. off+n-1]
 * [off .. off+n-1] into inv[0 .. n-1][0 .. n-1], through `scratch`.  False
 * (inv untouched) if the block is not positive definite.  (The reference
 * uses numpy.linalg.inv, an LU factorisation: same matrix to rounding.)
 */
static bool spd_inverse_(gl_real_t src[NPAR][NPAR], unsigned off, unsigned n,
                         gl_real_t scratch[NPAR][NPAR], gl_real_t inv[NPAR][NPAR])
{
    gl_real_t unit[NPAR];
    gl_real_t col[NPAR];
    for (unsigned i = 0; i < n; i++) {
        for (unsigned j = 0; j < n; j++) {
            scratch[i][j] = src[off + i][off + j];
        }
    }
    if (!chol_factor_(scratch, n)) {
        return false;
    }
    for (unsigned j = 0; j < n; j++) {
        for (unsigned i = 0; i < n; i++) {
            unit[i] = (i == j) ? GLS_R(1.0) : GLS_R(0.0);
        }
        chol_subst_(scratch, unit, n, col);
        for (unsigned i = 0; i < n; i++) {
            inv[i][j] = col[i];
        }
    }
    return true;
}

/* ---- the robust MAP problem ------------------------------------------------------ */

/** One patch fit (reference: _Problem and the arguments of _fit_lm). */
typedef struct {
    gl_solver_work_t *w;
    unsigned n_lin;                 /* linear rows in w->rows */
    unsigned n_h;                   /* horizon samples in w->hz */
    gl_real_t prior_w[NPAR];        /* 1 / prior sigma^2 */
    gl_real_t hz_sigma, hz_h_cam, hz_d_min, hz_far;
    gl_real_t huber_k;
} problem_t;

/**
 * Reference: _fit_residuals.  Sigma-normalised data residuals at x, their
 * Jacobian and the second derivative of each residual with respect to its
 * ray curvature, into buffer `buf` of the work area.  `n_h` = horizon rows
 * to evaluate (0 leaves them out: the convex Quick-Read problem).
 */
static void fit_residuals_(const problem_t *p, unsigned n_h, const gl_real_t *x, unsigned buf)
{
    gl_solver_work_t *w = p->w;
    gl_real_t *r = w->r[buf];
    gl_real_t (*jac)[NPAR] = w->jac[buf];
    gl_real_t *second = w->second[buf];

    for (unsigned i = 0; i < p->n_lin; i++) {
        gl_real_t acc = -w->targets[i];
        for (unsigned j = 0; j < NPAR; j++) {
            acc += w->rows[i][j] * x[j];
        }
        if (w->one_sided[i] != 0u && acc <= GLS_R(0.0)) {
            /* bound satisfied: no residual, no gradient */
            r[i] = GLS_R(0.0);
            for (unsigned j = 0; j < NPAR; j++) {
                jac[i][j] = GLS_R(0.0);
            }
        } else {
            r[i] = acc;
            for (unsigned j = 0; j < NPAR; j++) {
                jac[i][j] = w->rows[i][j];
            }
        }
        second[i] = GLS_R(0.0);
    }
    for (unsigned k = 0; k < n_h; k++) {
        const gl_real_t sigma = p->hz_sigma;
        const gl_real_t ct = w->hz[k][1];
        const gl_real_t st = w->hz[k][2];
        const gl_real_t slope = x[0] * ct + x[1] * st;
        const gl_real_t curv = x[2] * ct * ct + GLS_R(2.0) * x[3] * st * ct + x[4] * st * st;
        bool interior;
        const gl_real_t r_max = horizon_r_max_(curv, p->hz_h_cam, p->hz_d_min, p->hz_far, &interior);
        const unsigned i = p->n_lin + k;
        r[i] = (slope + GLS_R(0.5) * curv * r_max - p->hz_h_cam / r_max + x[5] + x[6] * st -
                w->hz[k][0]) / sigma;
        jac[i][0] = ct / sigma;
        jac[i][1] = st / sigma;
        jac[i][2] = GLS_R(0.5) * r_max * ct * ct / sigma;
        jac[i][3] = r_max * st * ct / sigma;
        jac[i][4] = GLS_R(0.5) * r_max * st * st / sigma;
        jac[i][5] = GLS_R(1.0) / sigma;
        jac[i][6] = st / sigma;
        second[i] = interior ? (GLS_R(0.25) * r_max / (-curv) / sigma) : GLS_R(0.0);
    }
}

/** Reference: _fit_cost.  Huber loss of the data residuals + Gaussian priors. */
static gl_real_t fit_cost_(const problem_t *p, unsigned m, const gl_real_t *x, const gl_real_t *r)
{
    const gl_real_t k = p->huber_k;
    gl_real_t cost = GLS_R(0.0);
    for (unsigned i = 0; i < m; i++) {
        const gl_real_t a = GLS_FABS(r[i]);
        if (a <= k) {
            cost += GLS_R(0.5) * a * a;
        } else {
            cost += k * a - GLS_R(0.5) * k * k;
        }
    }
    for (unsigned j = 0; j < NPAR; j++) {
        cost += GLS_R(0.5) * p->prior_w[j] * x[j] * x[j];
    }
    return cost;
}

/** Reference: _fit_gauss.  Gauss-Newton matrix with Huber (IRLS) weights
 *  min(1, k / |r|); its inverse is the posterior covariance reported. */
static void fit_gauss_(const problem_t *p, unsigned m, unsigned buf, gl_real_t gauss[NPAR][NPAR])
{
    const gl_real_t *r = p->w->r[buf];
    gl_real_t (*jac)[NPAR] = p->w->jac[buf];
    for (unsigned a = 0; a < NPAR; a++) {
        for (unsigned b = 0; b < NPAR; b++) {
            gauss[a][b] = GLS_R(0.0);
        }
        gauss[a][a] = p->prior_w[a];
    }
    for (unsigned i = 0; i < m; i++) {
        const gl_real_t ar = GLS_FABS(r[i]);
        const gl_real_t wgt = (ar <= p->huber_k) ? GLS_R(1.0) : (p->huber_k / ar);
        for (unsigned a = 0; a < NPAR; a++) {
            const gl_real_t wa = wgt * jac[i][a];
            if (wa != GLS_R(0.0)) {
                for (unsigned b = 0; b < NPAR; b++) {
                    gauss[a][b] += wa * jac[i][b];
                }
            }
        }
    }
}

/** Natural size of each parameter (reference: _SCALE). */
static gl_real_t par_scale_(unsigned j)
{
    return (j < 2u) ? GLS_R(1e-2) : GLS_R(1e-3);
}

/** Result of one Levenberg-Marquardt run. */
typedef struct {
    gl_real_t x[NPAR];
    gl_real_t cost;
    uint16_t n_iter;
    bool converged;
    unsigned buf;       /* work buffer holding r / jac / second of x */
} lm_result_t;

/**
 * Reference: _fit_lm.  Levenberg-Marquardt minimisation of the robust MAP
 * cost from x0.  Solves (H + lam diag(H_gauss)) step = -grad by Cholesky,
 * accepts the step only if it does not increase the cost, otherwise raises
 * lam tenfold (also when the matrix is not positive definite).  H is the
 * Gauss-Newton matrix with Huber weights until the set of Huber outliers is
 * the same at two consecutive iterates, then the exact Hessian of the Huber
 * cost for that outlier set; in both cases with the exact second-order term
 * of the horizon rows.  Parameters with free[j] == 0 are held.  Converged
 * when the scaled step falls below tol.  `gauss_out` receives the
 * Gauss-Newton matrix of all seven parameters at the solution.
 */
static void fit_lm_(const problem_t *p, unsigned n_h, const gl_real_t *x0, const uint8_t *free_par,
                    const gl_solver_options_t *opt, gl_real_t gauss_out[NPAR][NPAR],
                    lm_result_t *res)
{
    gl_solver_work_t *w = p->w;
    const unsigned m = p->n_lin + n_h;
    const gl_real_t huber_k = p->huber_k;
    gl_real_t (*hess)[NPAR] = w->mat[M_HESS];
    gl_real_t (*gauss)[NPAR] = w->mat[M_GAUSS];
    gl_real_t (*chol)[NPAR] = w->mat[M_CHOL];
    gl_real_t *x = res->x;
    gl_real_t x_new[NPAR];
    gl_real_t grad[NPAR];
    gl_real_t rhs[NPAR];
    gl_real_t step[NPAR];
    unsigned cur = 0u;
    bool have_prev = false;
    gl_real_t cost;
    gl_real_t lam = GLS_LM_LAMBDA0;
    bool converged = false;
    uint16_t n_iter = 0u;

    for (unsigned a = 0; a < NPAR; a++) {
        x[a] = x0[a];
    }
    for (unsigned i = 0; i < m; i++) {
        w->outlier_prev[i] = 0u;
    }
    fit_residuals_(p, n_h, x, cur);
    cost = fit_cost_(p, m, x, w->r[cur]);

    for (uint16_t it = 1u; it <= opt->lm_max_iter; it++) {
        const gl_real_t *r = w->r[cur];
        gl_real_t (*jac)[NPAR] = w->jac[cur];
        const gl_real_t *second = w->second[cur];
        bool exact = have_prev;
        bool accepted = false;
        bool small = false;

        n_iter = it;
        /* ---- same outlier set as at the previous iterate? -> exact Hessian */
        for (unsigned i = 0; i < m; i++) {
            const uint8_t flag = (GLS_FABS(r[i]) > huber_k) ? 1u : 0u;
            if (flag != w->outlier_prev[i]) {
                exact = false;
            }
            w->outlier_prev[i] = flag;
        }
        have_prev = true;
        /* ---- gradient, Gauss-Newton matrix, iteration matrix */
        fit_gauss_(p, m, cur, gauss);
        for (unsigned a = 0; a < NPAR; a++) {
            grad[a] = p->prior_w[a] * x[a];
            for (unsigned b = 0; b < NPAR; b++) {
                hess[a][b] = exact ? GLS_R(0.0) : gauss[a][b];
            }
            if (exact) {
                hess[a][a] = p->prior_w[a];
            }
        }
        for (unsigned i = 0; i < m; i++) {
            const gl_real_t ri = r[i];
            gl_real_t psi = ri;
            if (psi > huber_k) {
                psi = huber_k;
            } else if (psi < -huber_k) {
                psi = -huber_k;
            }
            for (unsigned a = 0; a < NPAR; a++) {
                grad[a] += jac[i][a] * psi;
            }
            if (exact && GLS_FABS(ri) <= huber_k) {
                for (unsigned a = 0; a < NPAR; a++) {
                    const gl_real_t ja = jac[i][a];
                    if (ja != GLS_R(0.0)) {
                        for (unsigned b = 0; b < NPAR; b++) {
                            hess[a][b] += ja * jac[i][b];
                        }
                    }
                }
            }
            if (second[i] != GLS_R(0.0)) {
                /* only horizon rows have a second derivative (i >= n_lin) */
                const unsigned k = i - p->n_lin;
                const gl_real_t ct = w->hz[k][1];
                const gl_real_t st = w->hz[k][2];
                const gl_real_t wq = psi * second[i];
                const gl_real_t q0 = ct * ct;
                const gl_real_t q1 = GLS_R(2.0) * st * ct;
                const gl_real_t q2 = st * st;
                hess[2][2] += wq * q0 * q0;
                hess[2][3] += wq * q0 * q1;
                hess[2][4] += wq * q0 * q2;
                hess[3][2] += wq * q1 * q0;
                hess[3][3] += wq * q1 * q1;
                hess[3][4] += wq * q1 * q2;
                hess[4][2] += wq * q2 * q0;
                hess[4][3] += wq * q2 * q1;
                hess[4][4] += wq * q2 * q2;
            }
        }
        for (unsigned a = 0; a < NPAR; a++) {
            if (free_par[a] == 0u) { /* held: unit row and column, no step */
                grad[a] = GLS_R(0.0);
                for (unsigned b = 0; b < NPAR; b++) {
                    hess[a][b] = GLS_R(0.0);
                    hess[b][a] = GLS_R(0.0);
                }
                hess[a][a] = GLS_R(1.0);
            }
        }
        /* ---- damped step (lam only grows in this loop: at most 25 passes) */
        while (lam <= GLS_R(1e12)) {
            const unsigned nxt = 1u - cur;
            gl_real_t biggest = GLS_R(0.0);
            gl_real_t cost_new;
            for (unsigned a = 0; a < NPAR; a++) {
                rhs[a] = -grad[a];
                for (unsigned b = 0; b < NPAR; b++) {
                    chol[a][b] = hess[a][b];
                }
                if (free_par[a] != 0u) {
                    chol[a][a] += lam * gauss[a][a];
                }
            }
            if (!chol_solve_(chol, rhs, NPAR, step)) { /* not positive definite: damp harder */
                lam *= GLS_R(10.0);
                continue;
            }
            for (unsigned a = 0; a < NPAR; a++) {
                const gl_real_t rel = GLS_FABS(step[a]) / par_scale_(a);
                if (rel > biggest) {
                    biggest = rel;
                }
                x_new[a] = x[a] + step[a];
            }
            small = biggest < opt->lm_tol;
            fit_residuals_(p, n_h, x_new, nxt);
            cost_new = fit_cost_(p, m, x_new, w->r[nxt]);
            if (cost_new <= cost) {
                for (unsigned a = 0; a < NPAR; a++) {
                    x[a] = x_new[a];
                }
                cur = nxt; /* (the reference copies r, jac, second) */
                cost = cost_new;
                lam = lam * GLS_R(0.1);
                if (lam < GLS_R(1e-12)) {
                    lam = GLS_R(1e-12);
                }
                accepted = true;
                break;
            }
            if (small) { /* at the minimum to rounding: keep the better point */
                break;
            }
            lam *= GLS_R(10.0);
        }
        if (small) {
            converged = true;
            break;
        }
        if (!accepted) {
            break;
        }
    }
    fit_gauss_(p, m, cur, gauss);
    for (unsigned a = 0; a < NPAR; a++) {
        for (unsigned b = 0; b < NPAR; b++) {
            gauss_out[a][b] = gauss[a][b];
        }
    }
    res->cost = cost;
    res->n_iter = n_iter;
    res->converged = converged;
    res->buf = cur;
}

/* ---- pieces of fit_patch ----------------------------------------------------------- */

/** Components of a device-frame vector in a frame rotated by `angle`. */
static void rotate_to_(gl_real_t vx, gl_real_t vy, gl_real_t angle, gl_real_t *ox, gl_real_t *oy)
{
    const gl_real_t ca = GLS_COS(angle);
    const gl_real_t sa = GLS_SIN(angle);
    *ox = vx * ca + vy * sa;
    *oy = -vx * sa + vy * ca;
}

/** Assumed 1-sigma error of one tilt component (reference: _tilt_sigma). */
static gl_real_t tilt_sigma_(const gl_measurements_t *m)
{
    if (m->tilt_reads >= 2u) { /* spin-and-reread: two seatings averaged, bias cancelled */
        return GLS_SQRT(GLS_R(0.5) *
                        (GLS_SIGMA_SEAT * GLS_SIGMA_SEAT + GLS_SIGMA_GRAVITY * GLS_SIGMA_GRAVITY));
    }
    return GLS_SQRT(GLS_SIGMA_SEAT * GLS_SIGMA_SEAT + GLS_SIGMA_TILT_BIAS * GLS_SIGMA_TILT_BIAS +
                    GLS_SIGMA_GRAVITY * GLS_SIGMA_GRAVITY);
}

/**
 * Reference: _cross_sigma_read.  1-sigma of the mean cross slope
 * b + 0.5 d D from cross-tilt readings at `stations` with errors `sigmas`:
 * Bayesian straight-line fit tilt_y(s) = b + d s with the weak slope prior
 * on b and the confidence prior on the twist d.
 */
static gl_real_t cross_sigma_read_(gl_real_t distance, const gl_real_t *stations,
                                   const gl_real_t *sigmas, unsigned n)
{
    const gl_real_t q = distance / GLS_CONF_TWIST_LENGTH;
    const gl_real_t sigma_d = GLS_CONF_TWIST_SIGMA / GLS_SQRT(GLS_R(1.0) + q * q);
    gl_real_t n00 = GLS_R(1.0) / (GLS_SIGMA_SLOPE_PRIOR * GLS_SIGMA_SLOPE_PRIOR);
    gl_real_t n01 = GLS_R(0.0);
    gl_real_t n11 = GLS_R(1.0) / (sigma_d * sigma_d);
    gl_real_t det, v_b, v_d, v_bd, v;
    for (unsigned i = 0; i < n; i++) {
        const gl_real_t wgt = GLS_R(1.0) / (sigmas[i] * sigmas[i]);
        n00 += wgt;
        n01 += wgt * stations[i];
        n11 += wgt * stations[i] * stations[i];
    }
    det = n00 * n11 - n01 * n01;
    v_b = n11 / det;
    v_d = n00 / det;
    v_bd = -n01 / det;
    v = v_b + distance * v_bd + GLS_R(0.25) * distance * distance * v_d;
    if (GLS_R(0.0) > v) {
        v = GLS_R(0.0);
    }
    return GLS_SQRT(v);
}

/** Reference: _tilt_only_fit.  Plane from the puck tilt alone (method B0
 *  and the fallbacks). */
static void tilt_only_fit_(const gl_measurements_t *m, gl_real_t bearing, gl_real_t distance,
                           gl_real_t distance_sigma, const gl_range_estimate_t *rng,
                           bool flag_missing, bool range_missing, gl_patch_fit_t *fit)
{
    const gl_real_t sig = tilt_sigma_(m);
    const gl_real_t station0 = GLS_R(0.0);
    gl_real_t a_t, b_t;

    rotate_to_(m->tilt_x, m->tilt_y, bearing, &a_t, &b_t);
    fit->coeffs[0] = a_t;
    fit->coeffs[1] = b_t;
    fit->coeffs[2] = GLS_R(0.0);
    fit->coeffs[3] = GLS_R(0.0);
    fit->coeffs[4] = GLS_R(0.0);
    for (unsigned i = 0; i < 5u; i++) {
        for (unsigned j = 0; j < 5u; j++) {
            fit->cov[i][j] = GLS_R(0.0);
        }
        fit->cov[i][i] = (i < 2u) ? (sig * sig) : (GLS_SIGMA_CURV * GLS_SIGMA_CURV);
    }
    fit->level_offsets[0] = GLS_R(0.0);
    fit->level_offsets[1] = GLS_R(0.0);
    fit->distance_m = distance;
    fit->distance_sigma_m = distance_sigma;
    fit->bearing_rad = bearing;
    fit->range = *rng;
    fit->tilt_slopes[0] = a_t;
    fit->tilt_slopes[1] = b_t;
    fit->cross_sigma_read = cross_sigma_read_(distance, &station0, &sig, 1u);
    fit->n_drops = 1u;
    for (unsigned i = 0; i < GL_SOLVER_MAX_DROPS; i++) {
        fit->stations_m[i] = GLS_R(0.0);
    }
    fit->base_hidden = false;
    fit->flag_missing = flag_missing;
    fit->range_missing = range_missing;
    fit->used_horizon = false;
    fit->poor_horizon = false;
    fit->horizon_rms = GLS_NAN;
    fit->n_iter = 0u;
    fit->converged = true;
    fit->cost = GLS_R(0.0);
    fit->cost_first_start = GLS_R(0.0);
    fit->n_starts = 0u;
}

/** Append the row (row . x - target) / sigma. */
static void add_linear_(problem_t *p, const gl_real_t *row, gl_real_t target, gl_real_t sigma,
                        bool one_sided)
{
    gl_solver_work_t *w = p->w;
    const unsigned i = p->n_lin;
    for (unsigned j = 0; j < NPAR; j++) {
        w->rows[i][j] = row[j] / sigma;
    }
    w->targets[i] = target / sigma;
    w->one_sided[i] = one_sided ? 1u : 0u;
    p->n_lin = i + 1u;
}

/** Posterior covariance of (a, b, c, d, e) from a Gauss-Newton matrix of
 *  all seven parameters: the 5 x 5 corner of its inverse.  NaN if the
 *  matrix is not positive definite. */
static void cov_from_gauss_(gl_solver_work_t *w, unsigned which, gl_patch_fit_t *fit)
{
    gl_real_t (*inv)[NPAR] = w->mat[M_HESS];
    const bool ok = spd_inverse_(w->mat[which], 0u, NPAR, w->mat[M_CHOL], inv);
    for (unsigned i = 0; i < 5u; i++) {
        for (unsigned j = 0; j < 5u; j++) {
            fit->cov[i][j] = ok ? inv[i][j] : GLS_NAN;
        }
    }
}

/**
 * Two-stage covariance of the anchored horizon fit: the held parameters
 * (a, b, c) as in the Quick Read; the rest follows them through the
 * conditional fit (theta_2 = -G22^-1 G21 theta_1 + ...).
 */
static void cov_anchored_(gl_solver_work_t *w, gl_patch_fit_t *fit)
{
    enum { HELD = 3, REST = 4 };
    gl_real_t (*gq_inv)[NPAR] = w->mat[M_HESS];
    gl_real_t (*gauss)[NPAR] = w->mat[M_BEST];
    gl_real_t (*cond)[NPAR] = w->mat[M_GAUSS]; /* free once the last LM run has ended */
    gl_real_t gain[REST][HELD];
    gl_real_t gc[REST][HELD];
    const bool ok_held = spd_inverse_(w->mat[M_QUICK], 0u, NPAR, w->mat[M_CHOL], gq_inv);
    const bool ok_rest = ok_held &&
                         spd_inverse_(gauss, (unsigned)HELD, (unsigned)REST, w->mat[M_CHOL], cond);

    if (!ok_rest) {
        /* the held block is still the Quick Read's; the rest is unknown */
        for (unsigned i = 0; i < 5u; i++) {
            for (unsigned j = 0; j < 5u; j++) {
                fit->cov[i][j] = (ok_held && i < (unsigned)HELD && j < (unsigned)HELD) ? gq_inv[i][j]
                                                                                      : GLS_NAN;
            }
        }
        return;
    }
    /* gain = -cond @ gauss[3:, :3];  gc = gain @ cov_held */
    for (unsigned i = 0; i < (unsigned)REST; i++) {
        for (unsigned j = 0; j < (unsigned)HELD; j++) {
            gl_real_t acc = GLS_R(0.0);
            for (unsigned k = 0; k < (unsigned)REST; k++) {
                acc += cond[i][k] * gauss[HELD + k][j];
            }
            gain[i][j] = -acc;
        }
    }
    for (unsigned i = 0; i < (unsigned)REST; i++) {
        for (unsigned j = 0; j < (unsigned)HELD; j++) {
            gl_real_t acc = GLS_R(0.0);
            for (unsigned k = 0; k < (unsigned)HELD; k++) {
                acc += gain[i][k] * gq_inv[k][j];
            }
            gc[i][j] = acc;
        }
    }
    for (unsigned i = 0; i < 5u; i++) {
        for (unsigned j = 0; j < 5u; j++) {
            gl_real_t v;
            if (i < (unsigned)HELD && j < (unsigned)HELD) {
                v = gq_inv[i][j];
            } else if (i >= (unsigned)HELD && j < (unsigned)HELD) {
                v = gc[i - HELD][j];
            } else if (i < (unsigned)HELD) {
                v = gc[j - HELD][i];
            } else {
                gl_real_t acc = GLS_R(0.0);
                for (unsigned k = 0; k < (unsigned)HELD; k++) {
                    acc += gc[i - HELD][k] * gain[j - HELD][k];
                }
                v = cond[i - HELD][j - HELD] + acc;
            }
            fit->cov[i][j] = v;
        }
    }
}

/* ---- fit_patch ------------------------------------------------------------------------ */

gl_status_t gls_fit_patch(const gl_measurements_t *drops, const uint8_t *order, unsigned n_drops,
                          uint8_t method, const gl_solver_options_t *opt, gl_solver_work_t *work)
{
    static const uint8_t free_all[NPAR] = { 1u, 1u, 1u, 1u, 1u, 1u, 1u };
    static const uint8_t free_twist[NPAR] = { 0u, 0u, 0u, 1u, 1u, 1u, 1u }; /* a, b, c held */
    const gl_measurements_t *first = &drops[order[0]];
    gl_patch_fit_t *fit = &work->fit;
    gl_range_estimate_t rng_first;
    problem_t prob;
    lm_result_t run;
    gl_real_t x_best[NPAR];
    gl_real_t x_tilt[NPAR];
    gl_real_t cross_sigmas[GL_SOLVER_MAX_DROPS];
    gl_real_t bearing, dist, sigma_field, a0 = GLS_R(0.0), b0 = GLS_R(0.0);
    bool have_bearing, base_hidden = false, used_horizon = false, converged;
    unsigned n_located = 0u, n_h = 0u;
    unsigned n_other = 0u;
    uint16_t n_iter;
    gl_real_t cost, cost_first;
    uint8_t n_starts;

    if (!fuse_range_(first, &rng_first)) {
        return GL_ERR_RANGE;
    }

    /* ---- no usable flag, or no usable range: tilt-only plane ------------------- */
    have_bearing = first->flag_found && gls_finite(first->flag_bearing_rad);
    if (!(have_bearing && range_valid_(&rng_first))) {
        const gl_real_t d = (gls_finite(first->user_distance_m) &&
                             first->user_distance_m > GLS_R(0.0))
                                ? first->user_distance_m
                                : GLS_DEFAULT_DISTANCE;
        if (have_bearing) {
            /* the flag was found but could not be ranged: its bearing (about
             * 1 mrad) is still far better than the visor axis */
            tilt_only_fit_(first, first->flag_bearing_rad, d, GLS_NAN, &rng_first, false, true, fit);
        } else {
            tilt_only_fit_(first, GLS_R(0.0), d, GLS_NAN, &rng_first, true, false, fit);
        }
        return GL_OK;
    }
    bearing = first->flag_bearing_rad;
    dist = rng_first.distance_m;
    if (method == (uint8_t)GL_SOLVER_METHOD_B0 || method == (uint8_t)GL_SOLVER_METHOD_STRAIGHT) {
        tilt_only_fit_(first, bearing, dist, rng_first.sigma_m, &rng_first, false, false, fit);
        return GL_OK;
    }

    /* ---- assemble the residuals -------------------------------------------------- */
    prob.w = work;
    prob.n_lin = 0u;
    prob.n_h = 0u;
    prob.huber_k = GLS_HUBER_K;
    prob.hz_sigma = GLS_SIGMA_HORIZON;
    prob.hz_h_cam = GLS_R(0.0);
    prob.hz_d_min = GLS_HORIZON_D_MIN;
    prob.hz_far = GLS_R(0.0);
    {
        gl_real_t s5 = GLS_SIGMA_LEVEL;
        if (method == (uint8_t)GL_SOLVER_METHOD_B2) {
            /* the common-mode height of the silhouette is a nuisance of its own */
            s5 = gls_hypot(GLS_SIGMA_LEVEL, GLS_SIGMA_SILHOUETTE);
        }
        prob.prior_w[0] = GLS_R(1.0) / (GLS_SIGMA_SLOPE_PRIOR * GLS_SIGMA_SLOPE_PRIOR);
        prob.prior_w[1] = prob.prior_w[0];
        prob.prior_w[2] = GLS_R(1.0) / (GLS_SIGMA_CURV * GLS_SIGMA_CURV);
        prob.prior_w[3] = prob.prior_w[2];
        prob.prior_w[4] = prob.prior_w[2];
        prob.prior_w[5] = GLS_R(1.0) / (s5 * s5);
        prob.prior_w[6] = GLS_R(1.0) / (GLS_SIGMA_LEVEL * GLS_SIGMA_LEVEL);
    }
    /* placements that can be located on the line (the first one always can) */
    for (unsigned i = 1u; i < n_drops; i++) {
        const gl_measurements_t *drop = &drops[order[i]];
        gl_range_estimate_t rng_i;
        if (!fuse_range_(drop, &rng_i)) {
            return GL_ERR_RANGE;
        }
        if (drop->flag_found && range_valid_(&rng_i) && gls_finite(drop->flag_bearing_rad)) {
            n_other++;
        }
    }
    sigma_field = (n_other > 0u) ? GLS_SIGMA_FIELD : GLS_R(0.0);

    for (unsigned i = 0; i < n_drops; i++) {
        const gl_measurements_t *drop = &drops[order[i]];
        gl_range_estimate_t rng_i;
        gl_real_t station = GLS_R(0.0);
        gl_real_t a_t, b_t, sig_t, sig_x, sig_y;
        gl_real_t row[NPAR] = { GLS_R(0.0), GLS_R(0.0), GLS_R(0.0), GLS_R(0.0),
                                GLS_R(0.0), GLS_R(0.0), GLS_R(0.0) };
        const unsigned li = n_located;

        if (i == 0u) {
            rng_i = rng_first;
        } else {
            (void)fuse_range_(drop, &rng_i);
            if (!(drop->flag_found && range_valid_(&rng_i) && gls_finite(drop->flag_bearing_rad))) {
                continue; /* a drop whose flag was not found or not ranged is ignored */
            }
            /* station = min(max(dist - range_i, 0), dist) */
            station = dist - rng_i.distance_m;
            if (GLS_R(0.0) > station) {
                station = GLS_R(0.0);
            }
            if (dist < station) {
                station = dist;
            }
        }
        fit->stations_m[li] = station;
        /* tilt, rotated into this drop's own "toward the hole" frame */
        rotate_to_(drop->tilt_x, drop->tilt_y, drop->flag_bearing_rad, &a_t, &b_t);
        if (li == 0u) {
            a0 = a_t;
            b0 = b_t;
        }
        sig_t = gls_hypot(tilt_sigma_(drop), sigma_field);
        sig_x = sig_t;
        sig_y = sig_t;
        if (li > 0u) {
            /* A drop placed by eye lies an unknown distance off the line, so
             * its "toward the hole" frame is rotated against the putt frame
             * by about (lateral offset) / (distance to the hole): cross-talk
             * of the along slope into the cross tilt, and vice versa. */
            const gl_real_t rot = GLS_SIGMA_DROP_LATERAL /
                                  ((GLS_R(0.3) > rng_i.distance_m) ? GLS_R(0.3) : rng_i.distance_m);
            sig_x = gls_hypot(sig_t, rot * b_t);
            sig_y = gls_hypot(sig_t, rot * a_t);
        }
        cross_sigmas[li] = sig_y;
        row[0] = GLS_R(1.0);
        row[2] = station;
        add_linear_(&prob, row, a_t, sig_x, false);
        row[0] = GLS_R(0.0);
        row[2] = GLS_R(0.0);
        row[1] = GLS_R(1.0);
        row[3] = station;
        add_linear_(&prob, row, b_t, sig_y, false);
        row[1] = GLS_R(0.0);
        row[3] = GLS_R(0.0);
        /* hole height above this drop */
        if (gls_finite(drop->flag_low_elev_rad)) {
            const gl_real_t h_lens = drop->h_cam_m - GLS_SINK_MEAN;
            const gl_real_t dz = h_lens + rng_i.distance_m * GLS_TAN(drop->flag_low_elev_rad);
            const gl_real_t sig_e = gls_hypot(GLS_SIGMA_PIXEL_ELEV / drop->f_px, GLS_SIGMA_LEVEL);
            const gl_real_t t1 = rng_i.distance_m * sig_e;
            const gl_real_t t3 = GLS_R(0.5) * GLS_SIGMA_MIRAGE * (rng_i.distance_m * rng_i.distance_m);
            gl_real_t sig_z = GLS_SQRT(t1 * t1 + GLS_SINK_SIGMA * GLS_SINK_SIGMA + t3 * t3);
            const bool hidden = !drop->flag_base_visible;
            if (li > 0u) {
                /* a partial rise: the model need not reproduce it better than sigma_field */
                sig_z = gls_hypot(sig_z, sigma_field * (dist - station));
            }
            if (li == 0u) {
                base_hidden = hidden;
            }
            row[0] = dist - station;
            row[2] = GLS_R(0.5) * (dist * dist - station * station);
            add_linear_(&prob, row, dz, sig_z, hidden);
        }
        n_located++;
    }

    if (method == (uint8_t)GL_SOLVER_METHOD_B2 && first->n_horizon > 0u) {
        unsigned n_valid = 0u;
        for (unsigned k = 0; k < first->n_horizon; k++) {
            if (gls_finite(first->horizon_elev_rad[k])) {
                n_valid++;
            }
        }
        if (n_valid >= GLS_MIN_HORIZON_SAMPLES) {
            for (unsigned k = 0; k < first->n_horizon; k++) {
                if (gls_finite(first->horizon_elev_rad[k])) {
                    const gl_real_t theta = first->horizon_az_rad[k] - bearing;
                    work->hz[n_h][0] = GLS_TAN(first->horizon_elev_rad[k]);
                    work->hz[n_h][1] = GLS_COS(theta);
                    work->hz[n_h][2] = GLS_SIN(theta);
                    n_h++;
                }
            }
            prob.n_h = n_h;
            prob.hz_h_cam = first->h_cam_m - GLS_SINK_MEAN;
            /* assumed far limit of the turf: min(max(1.5 D, 6 m), 20 m) */
            prob.hz_far = GLS_HORIZON_L_FACTOR * dist;
            if (GLS_HORIZON_L_MIN > prob.hz_far) {
                prob.hz_far = GLS_HORIZON_L_MIN;
            }
            if (GLS_HORIZON_L_CAP < prob.hz_far) {
                prob.hz_far = GLS_HORIZON_L_CAP;
            }
            used_horizon = true;
        }
    }

    for (unsigned j = 0; j < NPAR; j++) {
        x_tilt[j] = GLS_R(0.0);
    }
    x_tilt[0] = a0;
    x_tilt[1] = b0;

    if (!used_horizon) {
        /* convex problem: one run, the same minimum from any start */
        fit_lm_(&prob, 0u, x_tilt, free_all, opt, work->mat[M_BEST], &run);
        for (unsigned j = 0; j < NPAR; j++) {
            x_best[j] = run.x[j];
        }
        n_iter = run.n_iter;
        converged = run.converged;
        cost = run.cost;
        cost_first = cost;
        n_starts = 1u;
        cov_from_gauss_(work, M_BEST, fit);
    } else {
        /* anchored fit: what the Quick Read measures directly is held, the
         * horizon adds the rest */
        gl_real_t x_quick[NPAR];
        bool conv_quick;
        fit_lm_(&prob, 0u, x_tilt, free_all, opt, work->mat[M_QUICK], &run);
        for (unsigned j = 0; j < NPAR; j++) {
            x_quick[j] = run.x[j];
        }
        conv_quick = run.converged;
        fit_lm_(&prob, n_h, x_quick, free_twist, opt, work->mat[M_BEST], &run);
        for (unsigned j = 0; j < NPAR; j++) {
            x_best[j] = run.x[j];
        }
        n_iter = run.n_iter;
        converged = run.converged;
        cost = run.cost;
        cost_first = cost;
        n_starts = 1u;
        /* 4 further starts: (d, e) = (+-0.003, +-0.003) 1/m, e innermost */
        for (unsigned s = 0; s < 4u; s++) {
            gl_real_t x_alt[NPAR];
            for (unsigned j = 0; j < NPAR; j++) {
                x_alt[j] = x_quick[j];
            }
            x_alt[3] = ((s & 2u) != 0u) ? GLS_START_CURVATURE_ANCHORED : -GLS_START_CURVATURE_ANCHORED;
            x_alt[4] = ((s & 1u) != 0u) ? GLS_START_CURVATURE_ANCHORED : -GLS_START_CURVATURE_ANCHORED;
            n_starts++;
            fit_lm_(&prob, n_h, x_alt, free_twist, opt, work->mat[M_CAND], &run);
            if (run.cost < cost - GLS_COST_TIE * (GLS_R(1.0) + cost)) {
                for (unsigned j = 0; j < NPAR; j++) {
                    x_best[j] = run.x[j];
                    for (unsigned k = 0; k < NPAR; k++) {
                        work->mat[M_BEST][j][k] = work->mat[M_CAND][j][k];
                    }
                }
                n_iter = run.n_iter;
                converged = run.converged;
                cost = run.cost;
            }
        }
        converged = converged && conv_quick;
        cov_anchored_(work, fit);
    }

    fit->poor_horizon = false;
    fit->horizon_rms = GLS_NAN;
    if (used_horizon) {
        gl_real_t sum2 = GLS_R(0.0);
        unsigned n_out = 0u;
        fit_residuals_(&prob, n_h, x_best, 0u);
        for (unsigned k = 0; k < n_h; k++) {
            const gl_real_t rk = work->r[0][prob.n_lin + k];
            sum2 += rk * rk;
            if (GLS_FABS(rk) > GLS_HUBER_K) {
                n_out++;
            }
        }
        fit->horizon_rms = GLS_SQRT(sum2 / (gl_real_t)n_h);
        fit->poor_horizon = ((gl_real_t)n_out / (gl_real_t)n_h) > GLS_POOR_HORIZON_FRACTION;
    }

    for (unsigned j = 0; j < 5u; j++) {
        fit->coeffs[j] = x_best[j];
    }
    fit->level_offsets[0] = x_best[5];
    fit->level_offsets[1] = x_best[6];
    fit->distance_m = dist;
    fit->distance_sigma_m = rng_first.sigma_m;
    fit->bearing_rad = bearing;
    fit->range = rng_first;
    fit->tilt_slopes[0] = a0;
    fit->tilt_slopes[1] = b0;
    fit->cross_sigma_read = cross_sigma_read_(dist, fit->stations_m, cross_sigmas, n_located);
    fit->n_drops = (uint8_t)n_located;
    for (unsigned i = n_located; i < GL_SOLVER_MAX_DROPS; i++) {
        fit->stations_m[i] = GLS_R(0.0);
    }
    fit->base_hidden = base_hidden;
    fit->flag_missing = false;
    fit->range_missing = false;
    fit->used_horizon = used_horizon;
    fit->n_iter = n_iter;
    fit->converged = converged;
    fit->cost = cost;
    fit->cost_first_start = cost_first;
    fit->n_starts = n_starts;
    return GL_OK;
}
