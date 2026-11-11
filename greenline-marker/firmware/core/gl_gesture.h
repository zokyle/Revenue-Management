/*
 * gl_gesture.h - motion gestures: the device has no buttons.
 *
 *   posture      FLAT (lying on its base), UPRIGHT (held on edge, display
 *                vertical) or OTHER, with hysteresis and a dwell time
 *   dial         "roll-to-set": while UPRIGHT, the direction of gravity in
 *                the display plane is the dial position; rolling the puck
 *                like a knob changes a value in detents
 *   double tap   two short acceleration spikes 80..500 ms apart
 *   spin         a completed turn of about 180 degrees about the vertical
 *                (uses gl_rot_int_t from gl_tilt.h)
 *
 * All detectors are fed calibrated-enough samples in g / rad/s at the IMU
 * sample rate and are pure state machines.  RAM: under 64 bytes each.
 */
#ifndef GL_GESTURE_H
#define GL_GESTURE_H

#include "gl_tilt.h"
#include "gl_types.h"

/* ---- posture --------------------------------------------------------------- */

typedef enum {
    GL_POSTURE_UNKNOWN = 0,
    GL_POSTURE_FLAT,     /**< base down: |a.z| large and positive */
    GL_POSTURE_UPRIGHT,  /**< on edge: a.z near 0, |a| near 1 g */
    GL_POSTURE_OTHER     /**< upside down, in the hand, moving */
} gl_posture_t;

typedef struct {
    gl_posture_t stable;     /**< posture held for at least the dwell time */
    gl_posture_t candidate;
    uint32_t candidate_ms;   /**< how long the candidate has persisted */
    uint32_t dwell_ms;
} gl_posture_det_t;

/** dwell_ms: time a posture must persist before it is reported (e.g. 400). */
void gl_posture_init(gl_posture_det_t *p, uint32_t dwell_ms);

/** Feed one acceleration sample (g) covering dt_ms.  Returns true when the
 *  stable posture just changed. */
bool gl_posture_update(gl_posture_det_t *p, gl_vec3_t accel_g, uint32_t dt_ms);

/** Classify one sample without hysteresis.  FLAT: a.z > 0.90 g.  UPRIGHT:
 *  |a.z| < 0.35 g and in-plane magnitude 0.8..1.2 g. */
gl_posture_t gl_posture_classify(gl_vec3_t accel_g);

/* ---- roll-to-set dial ------------------------------------------------------- */

/** Roll angle per detent. */
#define GL_DIAL_STEP_RAD (15.0f * GL_DEG2RAD_F)

typedef struct {
    float last_angle_rad;  /**< previous gravity angle in the display plane */
    float accum_rad;       /**< unwrapped roll since the last detent change */
    int value;
    int min, max;
    bool have_angle;
} gl_dial_t;

/** Start a dial at `value` within [min, max]. */
void gl_dial_begin(gl_dial_t *d, int value, int min, int max);

/**
 * Feed an acceleration sample taken while UPRIGHT.  The dial position is
 * the angle of the up vector in the display (x, y) plane; rolling the puck
 * clockwise as seen from the display side (the top edge moving right)
 * INCREASES the value, one detent per GL_DIAL_STEP_RAD, with half a detent
 * of hysteresis.  The value saturates at min / max.  Returns true when the
 * value changed.  Samples with an in-plane magnitude below 0.5 g are
 * ignored (the puck is not upright).
 */
bool gl_dial_update(gl_dial_t *d, gl_vec3_t accel_g);

/* ---- double tap -------------------------------------------------------------- */

typedef struct {
    float threshold_g;      /**< jerk magnitude that counts as a tap (e.g. 0.6) */
    gl_vec3_t prev;
    bool have_prev;
    uint32_t since_tap_ms;  /**< time since the last tap spike began */
    uint32_t quiet_ms;      /**< time the signal has been below threshold */
    uint8_t taps;           /**< taps seen in the current sequence (0..2) */
    bool in_spike;
} gl_tap_det_t;

/** Reset the detector; threshold_g is the sample-to-sample jerk of a tap. */
void gl_tap_init(gl_tap_det_t *t, float threshold_g);

/**
 * Feed one acceleration sample (g) covering dt_ms.  A tap is a sample-to-
 * sample change above the threshold followed by at least 30 ms of quiet.
 * Returns true exactly once when a second tap arrives 80..500 ms after the
 * first.  Continuous shaking (no quiet gaps) never triggers.
 */
bool gl_tap_update(gl_tap_det_t *t, gl_vec3_t accel_g, uint32_t dt_ms);

/* ---- 180-degree spin ----------------------------------------------------------- */

/** A spin is accepted when the heading change is within this of 180 deg. */
#define GL_SPIN_TOL_RAD (35.0f * GL_DEG2RAD_F)

typedef struct {
    gl_rot_int_t rot;
    gl_vec3_t up_start;
    bool active;
} gl_spin_det_t;

/** Arm the detector at a moment when the marker is still: `up_start` is the
 *  unit up vector and `gyro_bias` the still-period gyro mean. */
void gl_spin_begin(gl_spin_det_t *s, gl_vec3_t up_start, gl_vec3_t gyro_bias_rad_s);

/** Add a gyro sample (rad/s) covering dt_s. */
void gl_spin_update(gl_spin_det_t *s, gl_vec3_t gyro_rad_s, float dt_s);

/** Heading change so far, rad, CCW positive. */
float gl_spin_yaw(const gl_spin_det_t *s);

/** True if the heading change is 180 degrees within GL_SPIN_TOL_RAD.  Call
 *  it once the marker is still again. */
bool gl_spin_is_half_turn(const gl_spin_det_t *s);

#endif /* GL_GESTURE_H */
