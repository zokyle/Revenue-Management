/*
 * gl_motion.h - turns the IMU sample stream into the motion events of the
 * UI (the device has no buttons): stillness, sustained movement, posture
 * (flat / upright), double tap, roll-to-set dial steps and the completed
 * 180-degree spin.  It also owns the block averager whose still blocks a
 * tilt read accumulates.
 *
 * Pure: it is fed samples and posts events into a gl_event_queue_t; it
 * never calls the HAL.
 *
 * What GL_EV_MOTION means depends on the mode:
 *   strict   (during a tilt read or a capture) ANY moving 133 ms block
 *   gesture  (result shown, waiting, ...) the marker was really moved:
 *            its posture left FLAT, or the gravity direction of a block
 *            moved by more than GL_APP_DISPLACE_G from where it rested for
 *            2 blocks, or 8 moving blocks in a row.  A tap, or a double
 *            tap, is NOT motion in this mode (the UI needs both).
 * One GL_EV_MOTION is posted per episode; the next comes only after the
 * marker has been still again.
 *
 * RAM: sizeof(gl_motion_t) about 400 bytes.  Stack: under 150 bytes.
 */
#ifndef GL_MOTION_H
#define GL_MOTION_H

#include "gl_event.h"
#include "gl_gesture.h"
#include "gl_tilt.h"
#include "gl_types.h"

/** Bits returned by gl_motion_sample(). */
#define GL_MOTION_F_BLOCK (1u << 0)       /**< this sample completed a block */
#define GL_MOTION_F_BLOCK_STILL (1u << 1) /**< ... and the block was still */
#define GL_MOTION_F_AT_REST (1u << 2)     /**< flat and still for 0.5 s as of this block */

typedef struct {
    gl_tilt_avg_t avg;          /**< stillness blocks; still blocks accumulate for a tilt read */
    gl_posture_det_t posture;
    gl_tap_det_t tap;
    gl_dial_t dial;
    gl_spin_det_t spin;
    gl_vec3_t accel_g;          /**< newest sample, marker axes */
    gl_vec3_t gyro_rad_s;
    float rest_x, rest_y;       /**< block-mean gravity direction when it last came to rest */
    bool have_rest;
    bool watch_still;           /**< post GL_EV_STILL the next time it is at rest */
    bool strict;                /**< see the file comment */
    bool motion_latched;        /**< GL_EV_MOTION already posted for this episode */
    bool dial_active;
    bool spin_active;           /**< the gyro is being integrated for the Precision spin */
    bool spin_reported;         /**< GL_EV_SPIN_DONE posted for the present rest position */
    bool taps_enabled;
    uint8_t moving_blocks;      /**< consecutive moving blocks */
    uint8_t displaced_blocks;   /**< consecutive blocks displaced from the rest direction */
} gl_motion_t;

/** Start with the IMU's scale factors (gl_imu_t after gl_imu_start_measure). */
void gl_motion_init(gl_motion_t *m, float accel_g_per_lsb, float gyro_rad_s_per_lsb);

/** Forget posture, stillness history and gestures (after the IMU was off). */
void gl_motion_restart(gl_motion_t *m);

/** Ask for one GL_EV_STILL when the marker is next flat and still for
 *  0.5 s (GL_APP_STILL_BLOCKS blocks).  Leaves strict mode. */
void gl_motion_watch_still(gl_motion_t *m);

/** Enter / leave strict mode (see the file comment).  Entering it also
 *  clears the motion latch, so that a movement during the read is reported
 *  even if one was reported shortly before. */
void gl_motion_set_strict(gl_motion_t *m, bool strict);

/** Start the dial at `value` within [min, max]; gl_motion_sample() then
 *  posts GL_EV_DIAL_STEP (arg = new value) while the marker is upright. */
void gl_motion_dial_begin(gl_motion_t *m, int value, int min, int max);
void gl_motion_dial_end(gl_motion_t *m);

/** Arm the 180-degree spin detector at a still moment: `up` is the unit up
 *  vector and `gyro_bias` the still-period gyro mean.  GL_EV_SPIN_DONE is
 *  posted when the marker is at rest after a half turn.  THE INTEGRATION
 *  GOES ON until gl_motion_spin_end(): the angle (gl_spin_yaw(&m->spin))
 *  stays true if the marker is turned again afterwards, and if it then
 *  comes to rest at a half turn once more, GL_EV_SPIN_DONE is posted again. */
void gl_motion_spin_begin(gl_motion_t *m, gl_vec3_t up, gl_vec3_t gyro_bias_rad_s);
/** Stop integrating (the angle is no longer needed). */
void gl_motion_spin_end(gl_motion_t *m);

/**
 * Feed one sample (marker axes, raw counts) that covers dt_ms.  Posts
 * GL_EV_STILL, GL_EV_MOTION, GL_EV_UPRIGHT, GL_EV_FLAT, GL_EV_DOUBLE_TAP,
 * GL_EV_DIAL_STEP and GL_EV_SPIN_DONE into `q` as they occur.  Returns
 * GL_MOTION_F_* bits.
 */
unsigned gl_motion_sample(gl_motion_t *m, const gl_imu_raw_t *s, uint32_t dt_ms,
                          gl_event_queue_t *q);

#endif /* GL_MOTION_H */
