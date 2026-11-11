/* gl_gesture.c - see gl_gesture.h. */
#include "gl_gesture.h"

#include <math.h>
#include <string.h>

/* ---- posture --------------------------------------------------------------- */

gl_posture_t gl_posture_classify(gl_vec3_t a)
{
    float inplane = sqrtf(a.x * a.x + a.y * a.y);
    if (a.z > 0.90f && inplane < 0.45f) {
        return GL_POSTURE_FLAT;
    }
    if (fabsf(a.z) < 0.35f && inplane > 0.8f && inplane < 1.2f) {
        return GL_POSTURE_UPRIGHT;
    }
    return GL_POSTURE_OTHER;
}

void gl_posture_init(gl_posture_det_t *p, uint32_t dwell_ms)
{
    memset(p, 0, sizeof(*p));
    p->dwell_ms = dwell_ms;
}

bool gl_posture_update(gl_posture_det_t *p, gl_vec3_t accel_g, uint32_t dt_ms)
{
    gl_posture_t now = gl_posture_classify(accel_g);
    if (now != p->candidate) {
        p->candidate = now;
        p->candidate_ms = 0;
        return false;
    }
    if (p->candidate_ms < 0x7FFFFFFFu) {
        p->candidate_ms += dt_ms;
    }
    if (p->candidate_ms >= p->dwell_ms && p->stable != p->candidate) {
        p->stable = p->candidate;
        return true;
    }
    return false;
}

/* ---- dial ------------------------------------------------------------------- */

void gl_dial_begin(gl_dial_t *d, int value, int min, int max)
{
    d->min = min;
    d->max = max;
    d->value = gl_clampi(value, min, max);
    d->accum_rad = 0.0f;
    d->last_angle_rad = 0.0f;
    d->have_angle = false;
}

bool gl_dial_update(gl_dial_t *d, gl_vec3_t a)
{
    float inplane = sqrtf(a.x * a.x + a.y * a.y);
    float angle, delta;
    int steps = 0;
    int before = d->value;

    if (inplane < 0.5f) {
        return false;
    }
    /* Seen from the display side (x right, y up), rolling the BODY clockwise
     * by t turns the up vector, expressed in body axes, counter-clockwise:
     * u = (-sin t, cos t).  So t = atan2(-u.x, u.y) grows with a clockwise
     * roll. */
    angle = atan2f(-a.x, a.y);
    if (!d->have_angle) {
        d->last_angle_rad = angle;
        d->have_angle = true;
        return false;
    }
    delta = gl_wrap_pi(angle - d->last_angle_rad);
    d->last_angle_rad = angle;
    d->accum_rad += delta;
    /* Half a detent of hysteresis: the first step needs a full detent, and
     * the accumulator keeps the remainder, so jitter around a boundary
     * cannot toggle the value. */
    while (d->accum_rad >= GL_DIAL_STEP_RAD && steps < 64) {
        d->accum_rad -= GL_DIAL_STEP_RAD;
        steps++;
    }
    while (d->accum_rad <= -GL_DIAL_STEP_RAD && steps > -64) {
        d->accum_rad += GL_DIAL_STEP_RAD;
        steps--;
    }
    if (steps != 0) {
        d->value = gl_clampi(d->value + steps, d->min, d->max);
        /* after a detent, re-centre so that reversing needs a full detent */
        d->accum_rad = gl_clampf(d->accum_rad, -0.5f * GL_DIAL_STEP_RAD, 0.5f * GL_DIAL_STEP_RAD);
    }
    return d->value != before;
}

/* ---- double tap --------------------------------------------------------------- */

#define TAP_QUIET_MS 30u
#define TAP_MIN_GAP_MS 80u
#define TAP_MAX_GAP_MS 500u
#define TAP_MAX_SPIKE_MS 60u

void gl_tap_init(gl_tap_det_t *t, float threshold_g)
{
    memset(t, 0, sizeof(*t));
    t->threshold_g = threshold_g;
    t->since_tap_ms = 100000u;
}

bool gl_tap_update(gl_tap_det_t *t, gl_vec3_t a, uint32_t dt_ms)
{
    float jerk = 0.0f;
    bool hit;
    bool fired = false;

    if (t->have_prev) {
        float dx = a.x - t->prev.x, dy = a.y - t->prev.y, dz = a.z - t->prev.z;
        jerk = sqrtf(dx * dx + dy * dy + dz * dz);
    }
    t->prev = a;
    t->have_prev = true;
    hit = (jerk > t->threshold_g);

    if (t->since_tap_ms < 1000000u) {
        t->since_tap_ms += dt_ms;
    }
    if (hit) {
        if (!t->in_spike) {
            /* A new spike begins.  It counts as a tap only if the signal was
             * quiet just before it (so shaking is not a string of taps). */
            if (t->quiet_ms >= TAP_QUIET_MS) {
                if (t->taps == 1u && t->since_tap_ms >= TAP_MIN_GAP_MS &&
                    t->since_tap_ms <= TAP_MAX_GAP_MS) {
                    t->taps = 2u; /* confirmed after its own quiet period */
                } else {
                    t->taps = 1u;
                }
                t->since_tap_ms = 0;
            } else {
                t->taps = 0; /* motion without a quiet gap: not tapping */
            }
            t->in_spike = true;
        } else if (t->since_tap_ms > TAP_MAX_SPIKE_MS) {
            t->taps = 0; /* too long to be a tap: sustained motion */
        }
        t->quiet_ms = 0;
    } else {
        if (t->quiet_ms < 1000000u) {
            t->quiet_ms += dt_ms;
        }
        if (t->in_spike && t->quiet_ms >= TAP_QUIET_MS) {
            t->in_spike = false;
            if (t->taps == 2u) {
                fired = true;
                t->taps = 0;
            }
        }
        if (t->taps == 1u && t->since_tap_ms > TAP_MAX_GAP_MS) {
            t->taps = 0; /* the second tap never came */
        }
    }
    return fired;
}

/* ---- spin ---------------------------------------------------------------------- */

void gl_spin_begin(gl_spin_det_t *s, gl_vec3_t up_start, gl_vec3_t gyro_bias_rad_s)
{
    gl_rot_int_start(&s->rot, gyro_bias_rad_s);
    s->up_start = gl_vec3_unit(up_start);
    s->active = true;
}

void gl_spin_update(gl_spin_det_t *s, gl_vec3_t gyro_rad_s, float dt_s)
{
    if (s->active) {
        gl_rot_int_add(&s->rot, gyro_rad_s, dt_s);
    }
}

float gl_spin_yaw(const gl_spin_det_t *s)
{
    return gl_rot_int_yaw(&s->rot, s->up_start);
}

bool gl_spin_is_half_turn(const gl_spin_det_t *s)
{
    float yaw = gl_spin_yaw(s);
    return s->active && (GL_PI_F - fabsf(yaw)) <= GL_SPIN_TOL_RAD;
}
