/* gl_motion.c - IMU samples -> UI motion events.  See gl_motion.h. */
#include "gl_motion.h"

#include <math.h>
#include <string.h>

#include "gl_app_cfg.h"
#include "gl_ui.h"

void gl_motion_restart(gl_motion_t *m)
{
    gl_tilt_avg_reset(&m->avg);
    gl_posture_init(&m->posture, GL_APP_POSTURE_DWELL_MS);
    gl_tap_init(&m->tap, GL_APP_TAP_THRESHOLD_G);
    m->have_rest = false;
    m->watch_still = false;
    m->strict = false;
    m->motion_latched = false;
    m->dial_active = false;
    m->spin_active = false;
    m->spin_reported = false;
    m->taps_enabled = true;
    m->moving_blocks = 0;
    m->displaced_blocks = 0;
}

void gl_motion_init(gl_motion_t *m, float accel_g_per_lsb, float gyro_rad_s_per_lsb)
{
    gl_tilt_cfg_t cfg;
    memset(m, 0, sizeof(*m));
    gl_tilt_cfg_defaults(&cfg);
    cfg.accel_g_per_lsb = accel_g_per_lsb;
    cfg.gyro_rad_s_per_lsb = gyro_rad_s_per_lsb;
    gl_tilt_avg_init(&m->avg, &cfg);
    gl_motion_restart(m);
}

void gl_motion_watch_still(gl_motion_t *m)
{
    m->watch_still = true;
    m->strict = false;
}

void gl_motion_set_strict(gl_motion_t *m, bool strict)
{
    if (strict && !m->strict) {
        m->motion_latched = false;
    }
    m->strict = strict;
}

void gl_motion_dial_begin(gl_motion_t *m, int value, int min, int max)
{
    gl_dial_begin(&m->dial, value, min, max);
    m->dial_active = true;
}

void gl_motion_dial_end(gl_motion_t *m)
{
    m->dial_active = false;
}

void gl_motion_spin_begin(gl_motion_t *m, gl_vec3_t up, gl_vec3_t gyro_bias_rad_s)
{
    gl_spin_begin(&m->spin, up, gyro_bias_rad_s);
    m->spin_active = true;
    m->spin_reported = false;
}

void gl_motion_spin_rearm(gl_motion_t *m)
{
    m->spin_reported = false;
}

void gl_motion_spin_end(gl_motion_t *m)
{
    m->spin_active = false;
    m->spin_reported = false;
}

static void post_motion_(gl_motion_t *m, gl_event_queue_t *q)
{
    if (!m->motion_latched) {
        m->motion_latched = true;
        (void)gl_event_post(q, (uint16_t)GL_EV_MOTION, 0);
    }
}

unsigned gl_motion_sample(gl_motion_t *m, const gl_imu_raw_t *s, uint32_t dt_ms,
                          gl_event_queue_t *q)
{
    const float ka = m->avg.cfg.accel_g_per_lsb;
    const float kg = m->avg.cfg.gyro_rad_s_per_lsb;
    unsigned flags = 0;

    m->accel_g.x = (float)s->ax * ka;
    m->accel_g.y = (float)s->ay * ka;
    m->accel_g.z = (float)s->az * ka;
    m->gyro_rad_s.x = (float)s->gx * kg;
    m->gyro_rad_s.y = (float)s->gy * kg;
    m->gyro_rad_s.z = (float)s->gz * kg;

    /* gestures that work on single samples */
    if (m->taps_enabled && gl_tap_update(&m->tap, m->accel_g, dt_ms)) {
        (void)gl_event_post(q, (uint16_t)GL_EV_DOUBLE_TAP, 0);
    }
    if (gl_posture_update(&m->posture, m->accel_g, dt_ms)) {
        if (m->posture.stable == GL_POSTURE_UPRIGHT) {
            (void)gl_event_post(q, (uint16_t)GL_EV_UPRIGHT, 0);
        } else if (m->posture.stable == GL_POSTURE_FLAT) {
            (void)gl_event_post(q, (uint16_t)GL_EV_FLAT, 0);
        } else {
            post_motion_(m, q); /* in the hand, upside down, ... */
        }
    }
    if (m->dial_active && m->posture.stable == GL_POSTURE_UPRIGHT &&
        gl_dial_update(&m->dial, m->accel_g)) {
        (void)gl_event_post(q, (uint16_t)GL_EV_DIAL_STEP, (int32_t)m->dial.value);
    }
    if (m->spin_active) {
        gl_spin_update(&m->spin, m->gyro_rad_s, (float)dt_ms * 0.001f);
    }

    /* 133 ms blocks: stillness and sustained movement */
    if (!gl_tilt_avg_add(&m->avg, s)) {
        return 0;
    }
    flags |= GL_MOTION_F_BLOCK;
    if (gl_tilt_avg_last_still(&m->avg)) {
        flags |= GL_MOTION_F_BLOCK_STILL;
        m->moving_blocks = 0;
    } else {
        /* it moved: a completed spin has to be confirmed again at the next rest */
        m->spin_reported = false;
        if (m->moving_blocks < 255u) {
            m->moving_blocks++;
        }
        if (m->strict || m->moving_blocks >= GL_APP_MOTION_BLOCKS) {
            post_motion_(m, q);
        }
    }
    /* displaced from where it rested (prev_mean_a is the mean of the block
     * just completed) */
    if (m->have_rest && !m->strict) {
        const float dx = m->avg.prev_mean_a[0] - m->rest_x;
        const float dy = m->avg.prev_mean_a[1] - m->rest_y;
        if (fabsf(dx) > GL_APP_DISPLACE_G || fabsf(dy) > GL_APP_DISPLACE_G) {
            if (m->displaced_blocks < 255u) {
                m->displaced_blocks++;
            }
            if (m->displaced_blocks >= GL_APP_DISPLACE_BLOCKS) {
                post_motion_(m, q);
            }
        } else {
            m->displaced_blocks = 0;
        }
    }
    /* at rest: flat and still for 0.5 s */
    if (gl_tilt_avg_consecutive_still(&m->avg) >= GL_APP_STILL_BLOCKS &&
        m->posture.stable == GL_POSTURE_FLAT) {
        flags |= GL_MOTION_F_AT_REST;
        m->rest_x = m->avg.prev_mean_a[0];
        m->rest_y = m->avg.prev_mean_a[1];
        m->have_rest = true;
        m->displaced_blocks = 0;
        m->motion_latched = false;
        /* the integration is NOT stopped here: the re-read that follows
         * must be combined with the angle it was really taken at */
        if (m->spin_active && !m->spin_reported && gl_spin_is_half_turn(&m->spin)) {
            m->spin_reported = true;
            (void)gl_event_post(q, (uint16_t)GL_EV_SPIN_DONE, 0);
        }
        if (m->watch_still) {
            m->watch_still = false;
            (void)gl_event_post(q, (uint16_t)GL_EV_STILL, 0);
        }
    }
    return flags;
}
