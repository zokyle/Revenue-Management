/*
 * gl_solver_aim.c - the aim solver: launch direction and speed that hole a
 * putt on a quadratic surface at the target pace.
 *
 * Port of physics.py (_trial, _solve_pace, _solve_kernel, solve_aim).
 * Statement order and operation order follow the reference; comments that
 * explain WHY are the reference's, shortened.
 *
 * Nested bracketing root finds.  Outer unknown: the aim angle phi (residual:
 * lateral miss y at the hole line).  Inner unknown: the launch energy
 * e = v0^2 (residual: pace g).  Each is a secant walk to a bracket followed
 * by Illinois regula falsi with a bisection step after any step that failed
 * to halve the bracket.
 *
 * Bounded: one pace solve rolls at most 1 + 40 + 80 = 121 trial balls; the
 * aim search makes at most 1 + 30 + 80 pace solves and checks the roll
 * budget (max_rolls) before each one after the first, so one aim solve
 * rolls at most max_rolls + 120 balls of at most 6004 RK4 steps each.
 */
#include "gl_solver_priv.h"

/** What a trial needs besides the aim and the energy. */
typedef struct {
    gls_roll_in_t roll;         /* surface, a_r, grain, hole, dt, t_max, r_trial */
    gl_real_t sx, sy, ux, uy;   /* ball, unit vector ball -> hole */
    gl_real_t dist;
    gl_real_t vh2;              /* target arrival speed squared */
    uint32_t n_steps;           /* RK4 steps of all trials so far */
} trial_ctx_t;

/**
 * One trial roll (reference: _trial).  Launch at `phi` from the hole line
 * with energy e0 = v0^2.  Returns the pace residual g:
 *   v_cross^2 - v_h^2                                   ball crosses the hole line
 *   -v_h^2 - 2 a_r shortfall - v_turn^2                 ball stays short
 *   -v_h^2 - 2 a_r |y|                                  FAR-CROSSING RULE: the ball
 *       crosses the (infinite) hole line more than 1 m + 0.5 D to the side:
 *       it has not reached the hole
 * and in *y the lateral miss at the hole line (+ = left), or the lateral
 * offset at the point of furthest progress if short.
 */
static gl_real_t trial_(trial_ctx_t *c, gl_real_t phi, gl_real_t e0, gl_real_t *y)
{
    const gl_real_t v0 = GLS_SQRT(e0);
    const gl_real_t cph = GLS_COS(phi);
    const gl_real_t sph = GLS_SIN(phi);
    const gl_real_t dx = c->ux * cph - c->uy * sph;
    const gl_real_t dy = c->uy * cph + c->ux * sph;
    gls_roll_out_t o;

    gls_roll(&c->roll, c->sx, c->sy, v0 * dx, v0 * dy, &o);
    c->n_steps += o.n_step;
    if (o.crossed) {
        const gl_real_t yl = o.yline;
        *y = yl;
        if (GLS_FABS(yl) > GLS_LINE_MISS_OFFSET + GLS_LINE_MISS_SLOPE * c->dist) {
            /* count it as too little pace, so that the pace solve moves on
             * to the faster branch that crosses near the hole */
            return -c->vh2 - GLS_R(2.0) * c->roll.a_r * GLS_FABS(yl);
        }
        return o.sline * o.sline - c->vh2;
    }
    *y = o.yprog;
    return -c->vh2 - GLS_R(2.0) * c->roll.a_r * (c->dist - o.xprog) - o.sprog * o.sprog;
}

/** Result of one pace solve. */
typedef struct {
    gl_real_t e, g, y;
    uint8_t flag;     /* GLS_PACE_* */
    uint32_t n;       /* trial rolls used */
} pace_t;

/**
 * Inner solve (reference: _solve_pace): launch energy giving the target
 * pace at fixed phi.  Phase A walks (unit-slope Newton step, then secant,
 * with growth limits) until the root is bracketed; phase B is Illinois
 * regula falsi inside the bracket.
 */
static void solve_pace_(trial_ctx_t *c, gl_real_t phi, gl_real_t e_guess, gl_real_t tol_g,
                        gl_real_t e_min, gl_real_t e_max, pace_t *out)
{
    uint32_t n = 0u;
    gl_real_t e = e_guess;
    gl_real_t g, y;
    bool have_lo = false;
    bool have_hi = false;
    gl_real_t e_lo = GLS_R(0.0), g_lo = GLS_R(0.0), y_lo = GLS_R(0.0);
    gl_real_t e_hi = GLS_R(0.0), g_hi = GLS_R(0.0), y_hi = GLS_R(0.0);
    gl_real_t e_prev, g_prev, e_new, w_lo, w_hi, w_jump;
    int it, last;
    bool bisect;

    if (e < e_min) {
        e = e_min;
    }
    if (e > e_max) {
        e = e_max;
    }
    g = trial_(c, phi, e, &y);
    n++;
    if (GLS_FABS(g) <= tol_g) {
        out->e = e;
        out->g = g;
        out->y = y;
        out->flag = (uint8_t)GLS_PACE_OK;
        out->n = n;
        return;
    }
    if (g < GLS_R(0.0)) {
        have_lo = true;
        e_lo = e;
        g_lo = g;
        y_lo = y;
    } else {
        have_hi = true;
        e_hi = e;
        g_hi = g;
        y_hi = y;
    }

    /* ---- phase A: find a bracket ---------------------------------------- */
    e_prev = e;
    g_prev = g;
    e_new = e - g; /* d(g)/d(e) = 1 exactly on a plane */
    it = 0;
    while (!(have_lo && have_hi)) {
        gl_real_t den, e_next;
        it++;
        if (it > 40) {
            if (have_hi) {
                out->e = e_hi;
                out->g = g_hi;
                out->y = y_hi;
                out->flag = (uint8_t)GLS_PACE_LIMITED;
            } else {
                out->e = e_lo;
                out->g = g_lo;
                out->y = y_lo;
                out->flag = (uint8_t)GLS_PACE_UNREACHABLE;
            }
            out->n = n;
            return;
        }
        if (have_lo) {
            if (e_lo >= e_max) {
                out->e = e_lo;
                out->g = g_lo;
                out->y = y_lo;
                out->flag = (uint8_t)GLS_PACE_UNREACHABLE;
                out->n = n;
                return;
            }
            if (!(e_new > e_lo)) {
                e_new = GLS_R(2.0) * e_lo + GLS_R(1e-4);
            }
            if (e_new > GLS_R(4.0) * e_lo + GLS_R(0.01)) {
                e_new = GLS_R(4.0) * e_lo + GLS_R(0.01);
            }
            if (e_new > e_max) {
                e_new = e_max;
            }
        } else {
            if (e_hi <= e_min) {
                out->e = e_hi;
                out->g = g_hi;
                out->y = y_hi;
                out->flag = (uint8_t)GLS_PACE_LIMITED;
                out->n = n;
                return;
            }
            if (!(e_new < e_hi)) {
                e_new = GLS_R(0.5) * e_hi;
            }
            if (e_new < GLS_R(0.25) * e_hi) {
                e_new = GLS_R(0.25) * e_hi;
            }
            if (e_new < e_min) {
                e_new = e_min;
            }
        }
        g = trial_(c, phi, e_new, &y);
        n++;
        if (GLS_FABS(g) <= tol_g) {
            out->e = e_new;
            out->g = g;
            out->y = y;
            out->flag = (uint8_t)GLS_PACE_OK;
            out->n = n;
            return;
        }
        if (g < GLS_R(0.0)) {
            have_lo = true;
            e_lo = e_new;
            g_lo = g;
            y_lo = y;
        } else {
            have_hi = true;
            e_hi = e_new;
            g_hi = g;
            y_hi = y;
        }
        den = g - g_prev;
        if (den != GLS_R(0.0)) {
            e_next = e_new - g * (e_new - e_prev) / den;
        } else {
            e_next = e_new - g;
        }
        e_prev = e_new;
        g_prev = g;
        e_new = e_next;
    }

    /* ---- phase B: Illinois regula falsi inside [e_lo, e_hi] --------------- */
    w_lo = g_lo; /* Illinois-weighted residuals */
    w_hi = g_hi;
    last = 0;
    bisect = false;
    /* A continuous g with |dg/de| of order one is within tol_g of zero long
     * before the bracket is this narrow: */
    w_jump = tol_g / GLS_R(16.0);
    if (w_jump < GLS_E_RESOLUTION * (GLS_R(1.0) + e_hi)) {
        w_jump = GLS_E_RESOLUTION * (GLS_R(1.0) + e_hi); /* floating-point resolution of e */
    }
    for (it = 0; it < 80; it++) {
        const gl_real_t width = e_hi - e_lo;
        if (width <= w_jump) {
            break; /* bracket collapsed onto a jump of g: no (robust) exact pace */
        }
        if (bisect) {
            e = GLS_R(0.5) * (e_lo + e_hi);
        } else {
            e = (e_lo * w_hi - e_hi * w_lo) / (w_hi - w_lo);
            if (!(e > e_lo && e < e_hi)) {
                e = GLS_R(0.5) * (e_lo + e_hi);
            }
        }
        g = trial_(c, phi, e, &y);
        n++;
        if (GLS_FABS(g) <= tol_g) {
            out->e = e;
            out->g = g;
            out->y = y;
            out->flag = (uint8_t)GLS_PACE_OK;
            out->n = n;
            return;
        }
        if (g < GLS_R(0.0)) {
            e_lo = e;
            g_lo = g;
            y_lo = y;
            w_lo = g;
            if (last == -1) {
                w_hi *= GLS_R(0.5);
            }
            last = -1;
        } else {
            e_hi = e;
            g_hi = g;
            y_hi = y;
            w_hi = g;
            if (last == 1) {
                w_lo *= GLS_R(0.5);
            }
            last = 1;
        }
        bisect = (e_hi - e_lo) > GLS_R(0.5) * width;
    }
    /* g jumps across zero (the ball either stops above a steep drop or runs
     * away down it): return the slowest putt that still gets there. */
    (void)g_lo;
    (void)y_lo;
    out->e = e_hi;
    out->g = g_hi;
    out->y = y_hi;
    out->flag = (uint8_t)GLS_PACE_LIMITED;
    out->n = n;
}

uint8_t gls_solve_kernel(const gl_quad_surface_t *sf, gl_real_t sx, gl_real_t sy, gl_real_t hx,
                         gl_real_t hy, gl_real_t a_r, gl_real_t agx, gl_real_t agy, gl_real_t v_h,
                         gl_real_t dt, gl_real_t t_max, gl_real_t r_max, gl_real_t tol_y,
                         gl_real_t tol_dist, gl_real_t phi_max, gl_real_t v_max,
                         uint32_t max_rolls, gls_solve_res_t *res)
{
    const gl_real_t dist = GLS_SQRT((hx - sx) * (hx - sx) + (hy - sy) * (hy - sy));
    trial_ctx_t c;
    pace_t pc;
    gl_real_t ux, uy, vh2, tol_g, e_min, e_max, r_trial, zs, zh, e0, gmx, gmy, ghx, ghy, a_n, rho2;
    gl_real_t fpace, phi, e, g, y;
    uint8_t pf;
    uint32_t n_tot = 0u;
    gl_real_t b_phi, b_e, b_y, b_g;
    uint8_t b_pf;
    bool have_best;
    int status = -1;
    bool have_lo = false;
    bool have_hi = false;
    gl_real_t p_lo = GLS_R(0.0), y_lo = GLS_R(0.0), e_lo = GLS_R(0.0);
    gl_real_t p_hi = GLS_R(0.0), y_hi = GLS_R(0.0), e_hi = GLS_R(0.0);
    gl_real_t p_cur, p_prev, y_prev, p_new;
    int it;

    res->phi = GLS_NAN;
    res->v0 = GLS_NAN;
    res->miss = GLS_NAN;
    res->vhole = GLS_NAN;
    res->n_rolls = 0u;
    res->n_steps = 0u;
    if (!(dist > GLS_R(1e-6)) || !(a_r > GLS_R(0.0)) || !(v_h >= GLS_R(0.0)) ||
        !(dt > GLS_R(0.0))) {
        return (uint8_t)GL_SOLVE_INVALID;
    }
    ux = (hx - sx) / dist;
    uy = (hy - sy) / dist;
    vh2 = v_h * v_h;
    tol_g = GLS_R(2.0) * a_r * tol_dist;
    e_min = GLS_E_MIN;
    e_max = v_max * v_max;
    /* A trial ball further than this from the start has run away for good. */
    r_trial = GLS_R(2.0) * dist + GLS_R(3.0);
    if (r_trial > r_max) {
        r_trial = r_max;
    }

    c.roll.sf = sf;
    c.roll.a_r = a_r;
    c.roll.agx = agx;
    c.roll.agy = agy;
    c.roll.hx = hx;
    c.roll.hy = hy;
    c.roll.dt = dt;
    c.roll.t_max = t_max;
    c.roll.r_max = r_trial;
    c.roll.stop_at_line = true;
    c.roll.stop_on_capture = false;
    c.roll.v_cap0 = GLS_R(0.0); /* no capture in the solver's trials */
    c.roll.cap_exp = GLS_R(0.5);
    c.roll.hole_r = GLS_HOLE_R;
    c.sx = sx;
    c.sy = sy;
    c.ux = ux;
    c.uy = uy;
    c.dist = dist;
    c.vh2 = vh2;
    c.n_steps = 0u;

    /* Energy balance gives the launch energy almost exactly (path ~ straight):
     *   v0^2 = v_h^2 + 2 a_r D + 2 (5/7) G (z_hole - z_ball) - 2 a_grain . (hole - ball) */
    zs = gls_surf_z(sf, sx, sy);
    zh = gls_surf_z(sf, hx, hy);
    e0 = vh2 + GLS_R(2.0) * a_r * dist + GLS_R(2.0) * GLS_KF * (zh - zs) -
         GLS_R(2.0) * (agx * (hx - sx) + agy * (hy - sy));
    if (e0 < GLS_R(1e-4)) {
        e0 = GLS_R(1e-4);
    }
    if (e0 > e_max) {
        e0 = e_max;
    }

    /* Planar small-slope theory gives the first aim guess:
     * phi = -a_n / (2 a_r) * F(rho). */
    gls_surf_grad(sf, GLS_R(0.5) * (sx + hx), GLS_R(0.5) * (sy + hy), &gmx, &gmy);
    gls_surf_grad(sf, hx, hy, &ghx, &ghy);
    a_n = (-agx * uy + agy * ux) -
          GLS_KF * (GLS_R(-0.5) * (gmx + ghx) * uy + GLS_R(0.5) * (gmy + ghy) * ux);
    rho2 = vh2 / e0;
    if (rho2 < GLS_R(1e-12)) {
        fpace = GLS_R(1.0);
    } else if (rho2 < GLS_R(0.98)) {
        fpace = GLS_R(1.0) + rho2 * GLS_LOG(rho2) / (GLS_R(1.0) - rho2);
    } else {
        fpace = GLS_R(0.01);
    }
    phi = -a_n / (GLS_R(2.0) * a_r) * fpace;
    if (phi > GLS_R(0.5) * phi_max) {
        phi = GLS_R(0.5) * phi_max;
    }
    if (phi < GLS_R(-0.5) * phi_max) {
        phi = GLS_R(-0.5) * phi_max;
    }

    solve_pace_(&c, phi, e0, tol_g, e_min, e_max, &pc);
    e = pc.e;
    g = pc.g;
    y = pc.y;
    pf = pc.flag;
    n_tot += pc.n;
    /* best iterate so far (smallest |y| among iterates that reach the hole) */
    b_phi = phi;
    b_e = e;
    b_y = y;
    b_g = g;
    b_pf = pf;
    have_best = (pf != (uint8_t)GLS_PACE_UNREACHABLE);
    if (pf == (uint8_t)GLS_PACE_UNREACHABLE) {
        status = (int)GL_SOLVE_UNREACHABLE;
        b_e = e0; /* nothing reached the hole: fall back to the energy-balance estimate */
    } else if (GLS_FABS(y) <= tol_y) {
        status = (int)GL_SOLVE_OK;
    }

    if (status < 0) {
        if (y < GLS_R(0.0)) { /* ball passes right of the hole: aim further left */
            have_lo = true;
            p_lo = phi;
            y_lo = y;
            e_lo = e;
        } else {
            have_hi = true;
            p_hi = phi;
            y_hi = y;
            e_hi = e;
        }
    }

    /* ---- phase A: bracket the aim angle ------------------------------------ */
    p_cur = phi;
    p_prev = phi;
    y_prev = y;
    p_new = phi - y / dist; /* d(y)/d(phi) ~ D */
    it = 0;
    while (status < 0 && !(have_lo && have_hi)) {
        gl_real_t step, den, p_next;
        it++;
        if (it > 30) {
            status = (int)GL_SOLVE_NO_BRACKET;
            break;
        }
        if (n_tot >= max_rolls) {
            status = (int)GL_SOLVE_NO_CONVERGENCE;
            break;
        }
        step = p_new - p_cur;
        if (step > GLS_R(0.3)) {
            step = GLS_R(0.3);
        }
        if (step < GLS_R(-0.3)) {
            step = GLS_R(-0.3);
        }
        if (have_lo && !(step > GLS_R(0.0))) {
            step = GLS_R(0.05);
        }
        if (have_hi && !(step < GLS_R(0.0))) {
            step = GLS_R(-0.05);
        }
        p_new = p_cur + step;
        if (p_new > phi_max) {
            if (p_cur >= phi_max) {
                status = (int)GL_SOLVE_NO_BRACKET;
                break;
            }
            p_new = phi_max;
        }
        if (p_new < -phi_max) {
            if (p_cur <= -phi_max) {
                status = (int)GL_SOLVE_NO_BRACKET;
                break;
            }
            p_new = -phi_max;
        }
        solve_pace_(&c, p_new, e, tol_g, e_min, e_max, &pc);
        e = pc.e;
        g = pc.g;
        y = pc.y;
        pf = pc.flag;
        n_tot += pc.n;
        if (pf == (uint8_t)GLS_PACE_UNREACHABLE) {
            status = (int)GL_SOLVE_UNREACHABLE;
            break;
        }
        if (!have_best || GLS_FABS(y) < GLS_FABS(b_y)) {
            b_phi = p_new;
            b_e = e;
            b_y = y;
            b_g = g;
            b_pf = pf;
            have_best = true;
        }
        if (GLS_FABS(y) <= tol_y) {
            status = (int)GL_SOLVE_OK;
            break;
        }
        if (y < GLS_R(0.0)) {
            have_lo = true;
            p_lo = p_new;
            y_lo = y;
            e_lo = e;
        } else {
            have_hi = true;
            p_hi = p_new;
            y_hi = y;
            e_hi = e;
        }
        den = y - y_prev;
        if (den != GLS_R(0.0)) {
            p_next = p_new - y * (p_new - p_prev) / den;
        } else {
            p_next = p_new - y / dist;
        }
        p_prev = p_new;
        y_prev = y;
        p_cur = p_new;
        p_new = p_next;
    }

    /* ---- phase B: Illinois regula falsi on the aim angle -------------------- */
    if (status < 0) {
        gl_real_t w_lo = y_lo;
        gl_real_t w_hi = y_hi;
        int last = 0;
        bool bisect = false;
        /* The lateral miss normally changes by about D metres per radian of
         * aim.  The bracket is declared collapsed onto a jump of the miss
         * when it is 1e4 times narrower than the tolerance needs at 1 m/rad,
         * or when the miss still changes by 1000 tolerances across a bracket
         * narrower than tol_y radians.  Then there is no continuous solution. */
        gl_real_t w_jump = GLS_R(1e-4) * tol_y;
        if (w_jump < GLS_PHI_JUMP_MIN) {
            w_jump = GLS_PHI_JUMP_MIN;
        }
        status = (int)GL_SOLVE_NO_CONVERGENCE;
        for (it = 0; it < 80; it++) {
            const gl_real_t width = p_hi - p_lo;
            gl_real_t e_start;
            if (width <= w_jump || (width <= tol_y && y_hi - y_lo > GLS_R(1e3) * tol_y)) {
                break;
            }
            if (n_tot >= max_rolls) {
                break;
            }
            if (bisect) {
                phi = GLS_R(0.5) * (p_lo + p_hi);
            } else {
                phi = (p_lo * w_hi - p_hi * w_lo) / (w_hi - w_lo);
                if (!(phi > p_lo && phi < p_hi)) {
                    phi = GLS_R(0.5) * (p_lo + p_hi);
                }
            }
            e_start = e_lo + (e_hi - e_lo) * (phi - p_lo) / width;
            solve_pace_(&c, phi, e_start, tol_g, e_min, e_max, &pc);
            e = pc.e;
            g = pc.g;
            y = pc.y;
            pf = pc.flag;
            n_tot += pc.n;
            if (pf == (uint8_t)GLS_PACE_UNREACHABLE) {
                status = (int)GL_SOLVE_UNREACHABLE;
                break;
            }
            if (GLS_FABS(y) < GLS_FABS(b_y)) {
                b_phi = phi;
                b_e = e;
                b_y = y;
                b_g = g;
                b_pf = pf;
            }
            if (GLS_FABS(y) <= tol_y) {
                status = (int)GL_SOLVE_OK;
                break;
            }
            if (y < GLS_R(0.0)) {
                p_lo = phi;
                y_lo = y;
                e_lo = e;
                w_lo = y;
                if (last == -1) {
                    w_hi *= GLS_R(0.5);
                }
                last = -1;
            } else {
                p_hi = phi;
                y_hi = y;
                e_hi = e;
                w_hi = y;
                if (last == 1) {
                    w_lo *= GLS_R(0.5);
                }
                last = 1;
            }
            bisect = (p_hi - p_lo) > GLS_R(0.5) * width;
        }
    }

    if (status == (int)GL_SOLVE_OK && b_pf != (uint8_t)GLS_PACE_OK) {
        status = (int)GL_SOLVE_PACE_LIMITED;
    }

    res->phi = b_phi;
    res->v0 = GLS_SQRT(b_e);
    res->n_rolls = n_tot;
    res->n_steps = c.n_steps;
    if (have_best) {
        const gl_real_t v2 = b_g + vh2;
        res->miss = b_y;
        res->vhole = (v2 > GLS_R(0.0)) ? GLS_SQRT(v2) : GLS_R(0.0);
    }
    return (uint8_t)status;
}

bool gls_options_ok(const gl_solver_options_t *opt)
{
    return gls_finite(opt->past_m) && opt->past_m >= GLS_R(0.0) &&
           opt->max_rolls <= GL_SOLVER_MAX_ROLLS_LIMIT &&
           opt->method <= (uint8_t)GL_SOLVER_METHOD_STRAIGHT &&
           gls_finite(opt->tol_miss_m) && opt->tol_miss_m >= GLS_R(0.0) &&
           gls_finite(opt->tol_pace_m) && opt->tol_pace_m >= GLS_R(0.0) &&
           gls_finite(opt->lm_tol) && opt->lm_tol >= GLS_R(0.0) &&
           opt->lm_max_iter <= GL_SOLVER_LM_MAX_ITER_LIMIT;
}

gl_status_t gl_solver_solve_aim(const gl_quad_surface_t *surface, gl_rvec2_t start, gl_rvec2_t hole,
                                gl_real_t a_r_mps2, gl_rvec2_t grain,
                                const gl_solver_options_t *opt, gl_aim_solution_t *out)
{
    gl_solver_options_t defaults;
    gls_solve_res_t res;
    gl_real_t v_h;
    uint8_t status;

    if (out == NULL) {
        return GL_ERR_PARAM;
    }
    out->phi_rad = GLS_NAN;
    out->v0_mps = GLS_NAN;
    out->status = (uint8_t)GL_SOLVE_INVALID;
    out->distance_m = GLS_NAN;
    out->a_r_mps2 = GLS_NAN;
    out->v_hole_target_mps = GLS_NAN;
    out->v_hole_mps = GLS_NAN;
    out->miss_m = GLS_NAN;
    out->n_rolls = 0u;
    out->n_steps = 0u;
    if (opt == NULL) {
        gl_solver_default_options(&defaults);
        opt = &defaults;
    }
    if (surface == NULL || !gls_options_ok(opt) || !gls_finite(surface->a) ||
        !gls_finite(surface->b) || !gls_finite(surface->c) || !gls_finite(surface->d) ||
        !gls_finite(surface->e) || !gls_finite(surface->z0) || !gls_finite(start.x) ||
        !gls_finite(start.y) || !gls_finite(hole.x) || !gls_finite(hole.y) ||
        !gls_finite(a_r_mps2) || !(a_r_mps2 > GLS_R(0.0)) || !gls_finite(grain.x) ||
        !gls_finite(grain.y)) {
        return GL_ERR_PARAM;
    }
    v_h = GLS_SQRT(GLS_R(2.0) * a_r_mps2 * opt->past_m);
    status = gls_solve_kernel(surface, start.x, start.y, hole.x, hole.y, a_r_mps2,
                              grain.x * a_r_mps2, grain.y * a_r_mps2, v_h, GLS_DT, GLS_T_MAX,
                              GLS_R_MAX, opt->tol_miss_m, opt->tol_pace_m, GLS_PHI_MAX, GLS_V_MAX,
                              (uint32_t)opt->max_rolls, &res);
    if (status != (uint8_t)GL_SOLVE_INVALID) {
        /* Absurd but finite inputs (a curvature of 1e30 /m ...) take the
         * arithmetic out of the finite range; a launch that is not a number
         * never moves, which the search would read as "no lateral miss".
         * The reference returns that iterate; here it is refused. */
        const bool usable = (status == (uint8_t)GL_SOLVE_OK || status == (uint8_t)GL_SOLVE_PACE_LIMITED);
        if (!gls_finite(res.phi) || !gls_finite(res.v0) ||
            (usable && (!gls_finite(res.miss) || !gls_finite(res.vhole)))) {
            out->n_rolls = (uint16_t)((res.n_rolls > 65535u) ? 65535u : res.n_rolls);
            out->n_steps = res.n_steps;
            return GL_ERR_RANGE;
        }
    }
    out->phi_rad = res.phi;
    out->v0_mps = res.v0;
    out->status = status;
    out->distance_m = gls_hypot(hole.x - start.x, hole.y - start.y);
    out->a_r_mps2 = a_r_mps2;
    out->v_hole_target_mps = v_h;
    out->v_hole_mps = res.vhole;
    out->miss_m = res.miss;
    out->n_rolls = (uint16_t)((res.n_rolls > 65535u) ? 65535u : res.n_rolls);
    out->n_steps = res.n_steps;
    return GL_OK;
}
