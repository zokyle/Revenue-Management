/*
 * gl_solver_roll.c - the roll kernel: one putt on a quadratic surface.
 *
 * Port of physics.py (_surf_grad, _surf_z, _hermite, _hermite_closest,
 * _hermite_line_crossing, _accel, _roll) for the quadratic surface only.
 * Statement order and operation order follow the reference; comments that
 * explain WHY are the reference's, shortened.
 *
 *     dv/dt = -a_r v_hat - (5/7) G grad z(x, y) + a_grain
 *
 * Classical RK4.  The step is the smallest of dt, half the predicted time
 * to stop (when the ball is within two steps of stopping) and
 * 0.5 * speed / a_r (the friction term is stiff as the speed goes to zero);
 * below 1e-4 m/s the stop is closed analytically.  A roll takes at most
 * 4 * (int(t_max / dt) + 1) steps.  Events inside a step (closest approach
 * to the hole, crossing of the hole line) are located on the cubic Hermite
 * segment through the step's end states.
 *
 * Not ported: grid surfaces, trajectory recording, the batch drivers.
 *
 * Bounded: the main loop either leaves or counts a step in every pass, and
 * the step count is capped (see `n_budget`); the Newton loops have fixed
 * counts.  Stack: 304 bytes in single precision (arm-none-eabi-gcc -Os,
 * -fstack-usage).
 */
#include "gl_solver_priv.h"

void gls_surf_grad(const gl_quad_surface_t *sf, gl_real_t x, gl_real_t y, gl_real_t *gx,
                   gl_real_t *gy)
{
    *gx = sf->a + sf->c * x + sf->d * y;
    *gy = sf->b + sf->d * x + sf->e * y;
}

gl_real_t gls_surf_z(const gl_quad_surface_t *sf, gl_real_t x, gl_real_t y)
{
    return sf->z0 + sf->a * x + sf->b * y +
           GLS_R(0.5) * (sf->c * x * x + GLS_R(2.0) * sf->d * x * y + sf->e * y * y);
}

/** One integration step from state 0 to state 1 in time h (reference: the
 *  argument list of _hermite). */
typedef struct {
    gl_real_t x0, y0, vx0, vy0, x1, y1, vx1, vy1, h;
} seg_t;

/** Cubic Hermite segment at fraction w: position and its first and second
 *  derivatives with respect to w (velocity = dp / h). */
typedef struct {
    gl_real_t px, py, dpx, dpy, ddpx, ddpy;
} seg_pt_t;

static void hermite_(const seg_t *s, gl_real_t w, seg_pt_t *p)
{
    const gl_real_t w2 = w * w;
    const gl_real_t w3 = w2 * w;
    const gl_real_t b00 = GLS_R(2.0) * w3 - GLS_R(3.0) * w2 + GLS_R(1.0);
    const gl_real_t b10 = w3 - GLS_R(2.0) * w2 + w;
    const gl_real_t b01 = GLS_R(-2.0) * w3 + GLS_R(3.0) * w2;
    const gl_real_t b11 = w3 - w2;
    const gl_real_t d00 = GLS_R(6.0) * w2 - GLS_R(6.0) * w;
    const gl_real_t d10 = GLS_R(3.0) * w2 - GLS_R(4.0) * w + GLS_R(1.0);
    const gl_real_t d11 = GLS_R(3.0) * w2 - GLS_R(2.0) * w;
    const gl_real_t e00 = GLS_R(12.0) * w - GLS_R(6.0);
    const gl_real_t e10 = GLS_R(6.0) * w - GLS_R(4.0);
    const gl_real_t e11 = GLS_R(6.0) * w - GLS_R(2.0);
    const gl_real_t h = s->h;
    p->px = b00 * s->x0 + b10 * h * s->vx0 + b01 * s->x1 + b11 * h * s->vx1;
    p->py = b00 * s->y0 + b10 * h * s->vy0 + b01 * s->y1 + b11 * h * s->vy1;
    p->dpx = d00 * (s->x0 - s->x1) + d10 * h * s->vx0 + d11 * h * s->vx1;
    p->dpy = d00 * (s->y0 - s->y1) + d10 * h * s->vy0 + d11 * h * s->vy1;
    p->ddpx = e00 * (s->x0 - s->x1) + e10 * h * s->vx0 + e11 * h * s->vx1;
    p->ddpy = e00 * (s->y0 - s->y1) + e10 * h * s->vy0 + e11 * h * s->vy1;
}

/**
 * Closest point to the hole on one step (the caller guarantees that the
 * ball approaches the hole at the start of the step and no longer at its
 * end).  Safeguarded Newton iteration on f(w) = (P(w) - H) . P'(w) = 0.
 * Returns the step fraction; *dd2 squared distance, *speed, *cross =
 * v x (H - P) there (> 0: hole on the left of the direction of travel).
 */
static gl_real_t hermite_closest_(const seg_t *s, gl_real_t hx, gl_real_t hy, gl_real_t *dd2,
                                  gl_real_t *speed, gl_real_t *cross)
{
    const gl_real_t q0 = (hx - s->x0) * s->vx0 + (hy - s->y0) * s->vy0;
    const gl_real_t q1 = (hx - s->x1) * s->vx1 + (hy - s->y1) * s->vy1;
    gl_real_t lo = GLS_R(0.0);
    gl_real_t hi = GLS_R(1.0);
    gl_real_t w = GLS_R(0.5);
    seg_pt_t p;
    if (q0 - q1 > GLS_R(0.0)) {
        w = q0 / (q0 - q1);
    }
    for (int it = 0; it < 30; it++) {
        gl_real_t f, df, wn;
        bool done;
        hermite_(s, w, &p);
        f = (p.px - hx) * p.dpx + (p.py - hy) * p.dpy;
        if (f < GLS_R(0.0)) {
            lo = w;
        } else {
            hi = w;
        }
        df = p.dpx * p.dpx + p.dpy * p.dpy + (p.px - hx) * p.ddpx + (p.py - hy) * p.ddpy;
        wn = GLS_R(0.5) * (lo + hi);
        if (df > GLS_R(0.0)) {
            wn = w - f / df;
            if (!(wn > lo && wn < hi)) {
                wn = GLS_R(0.5) * (lo + hi);
            }
        }
        done = GLS_FABS(wn - w) <= GLS_R(GLS_W_TOL) || hi - lo <= GLS_R(GLS_W_TOL);
        w = wn;
        if (done) {
            break;
        }
    }
    hermite_(s, w, &p);
    *dd2 = (p.px - hx) * (p.px - hx) + (p.py - hy) * (p.py - hy);
    *speed = GLS_SQRT(p.dpx * p.dpx + p.dpy * p.dpy) / s->h;
    *cross = (p.dpx * (hy - p.py) - p.dpy * (hx - p.px)) / s->h;
    return w;
}

/**
 * Where one step crosses the hole line X = dist (X = progress from the
 * start S along the unit vector u; the caller guarantees X0 < dist <= X1).
 * Returns the step fraction; *y_line lateral offset to the left of the
 * hole, *speed at the crossing.
 */
static gl_real_t hermite_line_crossing_(const seg_t *s, gl_real_t sx, gl_real_t sy, gl_real_t ux,
                                        gl_real_t uy, gl_real_t dist, gl_real_t *y_line,
                                        gl_real_t *speed)
{
    const gl_real_t x0p = (s->x0 - sx) * ux + (s->y0 - sy) * uy;
    const gl_real_t x1p = (s->x1 - sx) * ux + (s->y1 - sy) * uy;
    gl_real_t w = (dist - x0p) / (x1p - x0p);
    seg_pt_t p;
    for (int it = 0; it < 4; it++) {
        gl_real_t f, df;
        hermite_(s, w, &p);
        f = (p.px - sx) * ux + (p.py - sy) * uy - dist;
        df = p.dpx * ux + p.dpy * uy;
        if (df != GLS_R(0.0)) {
            w -= f / df;
        }
        if (w < GLS_R(0.0)) {
            w = GLS_R(0.0);
        } else if (w > GLS_R(1.0)) {
            w = GLS_R(1.0);
        }
    }
    hermite_(s, w, &p);
    *y_line = (p.py - sy) * ux - (p.px - sx) * uy;
    *speed = GLS_SQRT(p.dpx * p.dpx + p.dpy * p.dpy) / s->h;
    return w;
}

/**
 * Ball acceleration at state (x, y, vx, vy).  Moving ball: drive (slope +
 * grain) minus rolling resistance opposing the velocity.  Ball at rest:
 * resistance opposes the drive and cancels it if the drive does not exceed
 * a_r.
 */
static inline void accel_(const gls_roll_in_t *in, gl_real_t x, gl_real_t y, gl_real_t vx,
                          gl_real_t vy, gl_real_t *ax, gl_real_t *ay)
{
    gl_real_t gx, gy, adx, ady, s, ad, f;
    gls_surf_grad(in->sf, x, y, &gx, &gy);
    adx = in->agx - GLS_KF * gx;
    ady = in->agy - GLS_KF * gy;
    s = GLS_SQRT(vx * vx + vy * vy);
    if (s > GLS_S_TINY) {
        f = in->a_r / s;
        *ax = adx - f * vx;
        *ay = ady - f * vy;
        return;
    }
    ad = GLS_SQRT(adx * adx + ady * ady);
    if (ad > in->a_r) {
        f = GLS_R(1.0) - in->a_r / ad;
        *ax = adx * f;
        *ay = ady * f;
        return;
    }
    *ax = GLS_R(0.0);
    *ay = GLS_R(0.0);
}

/** 4 * (int(t_max / dt) + 1), defined for every input (the conversion of an
 *  out-of-range real to an integer is undefined in C). */
static uint32_t step_budget_(gl_real_t t_max, gl_real_t dt)
{
    const gl_real_t q = t_max / dt;
    uint32_t n = 0u;
    if (q >= GLS_R(1.0e6)) {
        n = 1000000u; /* never reached with the firmware's constants (1500) */
    } else if (q > GLS_R(0.0)) {
        n = (uint32_t)q;
    }
    return GLS_STEP_BUDGET_FACTOR * (n + 1u);
}

void gls_roll(const gls_roll_in_t *in, gl_real_t x, gl_real_t y, gl_real_t vx, gl_real_t vy,
              gls_roll_out_t *out)
{
    const gl_real_t a_r = in->a_r;
    const gl_real_t hx = in->hx;
    const gl_real_t hy = in->hy;
    const gl_real_t dt = in->dt;
    const gl_real_t t_max = in->t_max;
    const gl_real_t sx = x;
    const gl_real_t sy = y;
    const gl_real_t dist = GLS_SQRT((hx - sx) * (hx - sx) + (hy - sy) * (hy - sy));
    const gl_real_t r_max2 = in->r_max * in->r_max;
    const gl_real_t hole_r2 = in->hole_r * in->hole_r;
    /* Step budget: the stiffness limit shortens the steps of a slow ball, so
     * a ball creeping on a slope within a fraction of a percent of critical
     * could take an unbounded number of them before t_max. */
    const uint32_t n_budget = step_budget_(t_max, dt);
    const bool capture_on = in->v_cap0 > GLS_R(0.0);
    gl_real_t ux, uy;
    gl_real_t t = GLS_R(0.0);
    uint32_t n_step = 0u;
    gl_real_t s = GLS_SQRT(vx * vx + vy * vy);
    gl_real_t dmin2 = dist * dist; /* squared closest approach so far */
    gl_real_t smin = s;
    gl_real_t tmin = GLS_R(0.0);
    int8_t side = 0;
    bool crossed = false;
    gl_real_t yline = GLS_NAN;
    gl_real_t sline = GLS_NAN;
    gl_real_t tline = GLS_NAN;
    gl_real_t xprog = GLS_R(0.0);
    gl_real_t yprog = GLS_R(0.0);
    gl_real_t sprog = s;
    bool captured = false;
    gl_real_t tcap = GLS_NAN;
    gl_real_t path = GLS_R(0.0);
    uint8_t status;

    if (dist > GLS_R(0.0)) {
        ux = (hx - sx) / dist;
        uy = (hy - sy) / dist;
    } else {
        ux = GLS_R(1.0);
        uy = GLS_R(0.0);
    }

    for (;;) {
        gl_real_t gx, gy, adx, ady, h, a1x, a1y, hh, vx2, vy2, a2x, a2y, vx3, vy3, a3x, a3y;
        gl_real_t vx4, vy4, a4x, a4y, h6, xn, yn, vxn, vyn, sn, ex, ey, ox, oy, dd2, q0, q1, xp;
        bool just_crossed;

        if (t >= t_max || n_step >= n_budget) {
            status = (uint8_t)GL_ROLL_MAX_TIME;
            break;
        }

        gls_surf_grad(in->sf, x, y, &gx, &gy);
        adx = in->agx - GLS_KF * gx; /* drive: slope + grain */
        ady = in->agy - GLS_KF * gy;

        /* ---- step-size control and terminal closure near the stop ------- */
        h = dt;
        if (s > GLS_S_TINY) {
            const gl_real_t dec = a_r - (adx * vx + ady * vy) / s; /* along-track deceleration */
            if (dec > GLS_R(0.0)) {
                const gl_real_t ts = s / dec; /* time to stop if the acceleration stayed frozen */
                if (s < GLS_V_EPS && ts < dt) {
                    /* analytic closure of the last <= 1e-8 m (straight line,
                     * constant deceleration) */
                    const gl_real_t dl = GLS_R(0.5) * s * ts;
                    x += vx / s * dl;
                    y += vy / s * dl;
                    t += ts;
                    path += dl;
                    vx = GLS_R(0.0);
                    vy = GLS_R(0.0);
                    s = GLS_R(0.0);
                    dd2 = (hx - x) * (hx - x) + (hy - y) * (hy - y);
                    if (dd2 < dmin2) {
                        dmin2 = dd2;
                        smin = GLS_R(0.0);
                        tmin = t;
                    }
                    xp = (x - sx) * ux + (y - sy) * uy;
                    if (xp > xprog) {
                        xprog = xp;
                        yprog = (y - sy) * ux - (x - sx) * uy;
                        sprog = GLS_R(0.0);
                    }
                } else if (ts < GLS_R(2.0) * h) {
                    h = GLS_R(0.5) * ts;
                }
            }
            /* A slow ball's velocity component across the drive decays at
             * the rate a_r / s, which grows without bound as the ball
             * stops.  Explicit RK4 is only stable for h * a_r / s < 2.785,
             * so the step is also limited by this rate. */
            if (h * a_r > GLS_H_STIFF * s) {
                h = GLS_H_STIFF * s / a_r;
            }
        }

        /* ---- first RK4 stage (also decides whether a resting ball holds) -- */
        if (s > GLS_S_TINY) {
            const gl_real_t f = a_r / s;
            a1x = adx - f * vx;
            a1y = ady - f * vy;
        } else {
            gl_real_t ad, f;
            vx = GLS_R(0.0);
            vy = GLS_R(0.0);
            s = GLS_R(0.0);
            ad = GLS_SQRT(adx * adx + ady * ady);
            if (ad <= a_r) {
                status = (uint8_t)GL_ROLL_STOPPED; /* rolling resistance holds the ball */
                break;
            }
            /* too steep to rest here: the ball rolls on from rest */
            f = GLS_R(1.0) - a_r / ad;
            a1x = adx * f;
            a1y = ady * f;
        }

        if (t + h > t_max) {
            h = t_max - t;
        }

        /* ---- remaining RK4 stages ---------------------------------------- */
        hh = GLS_R(0.5) * h;
        vx2 = vx + hh * a1x;
        vy2 = vy + hh * a1y;
        accel_(in, x + hh * vx, y + hh * vy, vx2, vy2, &a2x, &a2y);
        vx3 = vx + hh * a2x;
        vy3 = vy + hh * a2y;
        accel_(in, x + hh * vx2, y + hh * vy2, vx3, vy3, &a3x, &a3y);
        vx4 = vx + h * a3x;
        vy4 = vy + h * a3y;
        accel_(in, x + h * vx3, y + h * vy3, vx4, vy4, &a4x, &a4y);
        h6 = h / GLS_R(6.0);
        xn = x + h6 * (vx + GLS_R(2.0) * vx2 + GLS_R(2.0) * vx3 + vx4);
        yn = y + h6 * (vy + GLS_R(2.0) * vy2 + GLS_R(2.0) * vy3 + vy4);
        vxn = vx + h6 * (a1x + GLS_R(2.0) * a2x + GLS_R(2.0) * a3x + a4x);
        vyn = vy + h6 * (a1y + GLS_R(2.0) * a2y + GLS_R(2.0) * a3y + a4y);
        sn = GLS_SQRT(vxn * vxn + vyn * vyn);
        n_step++;

        /* ---- events on the step (x, y) -> (xn, yn) ------------------------ */
        ex = xn - x;
        ey = yn - y;
        path += GLS_SQRT(ex * ex + ey * ey);

        /* closest approach to the hole centre: end point of the step ... */
        ox = hx - xn;
        oy = hy - yn;
        dd2 = ox * ox + oy * oy;
        if (dd2 < dmin2) {
            const gl_real_t cr = vxn * oy - vyn * ox;
            dmin2 = dd2;
            smin = sn;
            tmin = t + h;
            /* hole to the left of travel: ball passes right */
            side = (cr > GLS_R(0.0)) ? (int8_t)-1 : ((cr < GLS_R(0.0)) ? (int8_t)1 : (int8_t)0);
        }

        /* ... and a local minimum of the distance inside the step (a "pass"),
         * which is also where the capture rule is applied */
        q0 = (hx - x) * vx + (hy - y) * vy;
        q1 = ox * vxn + oy * vyn;
        if (q0 > GLS_R(0.0) && q1 <= GLS_R(0.0)) {
            const seg_t seg = { x, y, vx, vy, xn, yn, vxn, vyn, h };
            gl_real_t sp, cr;
            const gl_real_t w = hermite_closest_(&seg, hx, hy, &dd2, &sp, &cr);
            if (dd2 < dmin2) {
                dmin2 = dd2;
                smin = sp;
                tmin = t + w * h;
                side = (cr > GLS_R(0.0)) ? (int8_t)-1 : ((cr < GLS_R(0.0)) ? (int8_t)1 : (int8_t)0);
            }
            if (capture_on && !captured && dd2 < hole_r2) {
                if (sp < in->v_cap0 * GLS_POW(GLS_R(1.0) - dd2 / hole_r2, in->cap_exp)) {
                    captured = true;
                    tcap = t + w * h;
                }
            }
        }

        /* first crossing of the hole line X = dist */
        just_crossed = false;
        if (!crossed) {
            if ((xn - sx) * ux + (yn - sy) * uy >= dist && (x - sx) * ux + (y - sy) * uy < dist) {
                const seg_t seg = { x, y, vx, vy, xn, yn, vxn, vyn, h };
                const gl_real_t w = hermite_line_crossing_(&seg, sx, sy, ux, uy, dist, &yline, &sline);
                tline = t + w * h;
                crossed = true;
                just_crossed = true;
            }
        }

        /* ---- advance -------------------------------------------------------- */
        x = xn;
        y = yn;
        vx = vxn;
        vy = vyn;
        s = sn;
        t += h;

        xp = (x - sx) * ux + (y - sy) * uy;
        if (xp > xprog) {
            xprog = xp;
            yprog = (y - sy) * ux - (x - sx) * uy;
            sprog = sn;
        }

        if (captured && in->stop_on_capture && crossed) {
            /* holed, and the lateral miss at the hole line is known */
            status = (uint8_t)GL_ROLL_CAPTURED;
            break;
        }
        if (just_crossed && in->stop_at_line) {
            status = (uint8_t)GL_ROLL_AT_LINE;
            break;
        }
        if ((x - sx) * (x - sx) + (y - sy) * (y - sy) > r_max2) {
            status = (uint8_t)GL_ROLL_OUT_OF_BOUNDS;
            break;
        }
    }

    if (status == (uint8_t)GL_ROLL_STOPPED && capture_on && !captured) {
        /* at rest with the centre over the hole: the ball has dropped */
        if ((hx - x) * (hx - x) + (hy - y) * (hy - y) < hole_r2) {
            captured = true;
            tcap = t;
        }
    }

    out->status = status;
    out->t = t;
    out->x = x;
    out->y = y;
    out->vx = vx;
    out->vy = vy;
    out->dmin = GLS_SQRT(dmin2);
    out->smin = smin;
    out->tmin = tmin;
    out->side = side;
    out->crossed = crossed;
    out->yline = yline;
    out->sline = sline;
    out->tline = tline;
    out->xprog = xprog;
    out->yprog = yprog;
    out->sprog = sprog;
    out->captured = captured;
    out->tcapt = tcap;
    out->path = path;
    out->n_step = n_step;
}

gl_status_t gl_solver_roll(const gl_quad_surface_t *surface, gl_rvec2_t start, gl_rvec2_t hole,
                           gl_real_t phi_rad, gl_real_t v0_mps, gl_real_t a_r_mps2,
                           gl_rvec2_t grain, gl_real_t capture_exponent, bool stop_on_capture,
                           gl_roll_result_t *out)
{
    gls_roll_in_t in;
    gls_roll_out_t o;
    gl_real_t ang, dist;

    if (out == NULL) {
        return GL_ERR_PARAM;
    }
    out->status = (uint8_t)GL_ROLL_INVALID;
    out->t_end_s = GLS_NAN;
    out->stop_x = GLS_NAN;
    out->stop_y = GLS_NAN;
    out->delta_m = GLS_NAN;
    out->speed_at_delta_mps = GLS_NAN;
    out->side = 0;
    out->crossed_hole_line = false;
    out->lateral_at_line_m = GLS_NAN;
    out->speed_at_line_mps = GLS_NAN;
    out->lateral_miss_m = GLS_NAN;
    out->shortfall_m = GLS_NAN;
    out->captured = false;
    out->path_length_m = GLS_NAN;
    out->n_steps = 0u;
    if (surface == NULL || !gls_finite(surface->a) || !gls_finite(surface->b) ||
        !gls_finite(surface->c) || !gls_finite(surface->d) || !gls_finite(surface->e) ||
        !gls_finite(surface->z0) || !gls_finite(start.x) || !gls_finite(start.y) ||
        !gls_finite(hole.x) || !gls_finite(hole.y) || !gls_finite(phi_rad) ||
        !gls_finite(v0_mps) || !(v0_mps >= GLS_R(0.0)) || !gls_finite(a_r_mps2) ||
        !(a_r_mps2 > GLS_R(0.0)) || !gls_finite(grain.x) || !gls_finite(grain.y) ||
        !gls_finite(capture_exponent)) {
        return GL_ERR_PARAM;
    }
    in.sf = surface;
    in.a_r = a_r_mps2;
    in.agx = grain.x * a_r_mps2;
    in.agy = grain.y * a_r_mps2;
    in.hx = hole.x;
    in.hy = hole.y;
    in.dt = GLS_DT;
    in.t_max = GLS_T_MAX;
    in.r_max = GLS_R_MAX;
    in.stop_at_line = false;
    in.stop_on_capture = stop_on_capture;
    in.v_cap0 = GLS_V_CAP0;
    in.cap_exp = capture_exponent;
    in.hole_r = GLS_HOLE_R;
    /* reference: launch_velocity() */
    ang = GLS_ATAN2(hole.y - start.y, hole.x - start.x) + phi_rad;
    gls_roll(&in, start.x, start.y, v0_mps * GLS_COS(ang), v0_mps * GLS_SIN(ang), &o);

    dist = gls_hypot(hole.x - start.x, hole.y - start.y);
    if (!gls_finite(o.t) || !gls_finite(o.x) || !gls_finite(o.y) || !gls_finite(o.dmin) ||
        !gls_finite(o.smin) || !gls_finite(o.path) || !gls_finite(o.xprog) || !gls_finite(o.yprog) ||
        !gls_finite(dist) || (o.crossed && (!gls_finite(o.yline) || !gls_finite(o.sline)))) {
        /* absurd but finite inputs: the arithmetic left the finite range */
        return GL_ERR_RANGE;
    }
    out->status = o.status;
    out->t_end_s = o.t;
    out->stop_x = o.x;
    out->stop_y = o.y;
    out->delta_m = o.dmin;
    out->speed_at_delta_mps = o.smin;
    out->side = o.side;
    out->crossed_hole_line = o.crossed;
    out->lateral_at_line_m = o.yline;
    out->speed_at_line_mps = o.sline;
    out->lateral_miss_m = o.crossed ? o.yline : o.yprog;
    out->shortfall_m = GLS_R(0.0);
    if (!o.crossed && dist - o.xprog > GLS_R(0.0)) {
        out->shortfall_m = dist - o.xprog;
    }
    out->captured = o.captured;
    out->path_length_m = o.path;
    out->n_steps = o.n_step;
    return GL_OK;
}
