/*
 * gl_tilt.h - gravity / slope measurement from the IMU.
 *
 * Pipeline of one tilt read:
 *   raw samples -> gl_tilt_avg_* (exact integer block averaging, stillness
 *   gating) -> mean acceleration in g -> gl_tilt_apply_cal() (temperature
 *   polynomial, offset, 3x3 scale / cross-axis matrix) -> gl_tilt_slope()
 *   (unit "up" vector -> surface gradient) -> minus the flip-calibration
 *   bias.
 *
 * At rest the accelerometer measures +1 g along the UP direction, so the
 * normalised reading is the unit up vector u expressed in the marker frame.
 * The marker sits on the surface, so the surface gradient (uphill, rise/run)
 * in marker axes is (u.x / u.z, u.y / u.z).
 *
 * Also here: six-face calibration solve, quadratic temperature fit, a
 * gyro rotation integrator (flip yaw, 180-degree spin), the flip /
 * Precision-Read algebra, and the Survey sample store.
 *
 * RAM: gl_tilt_avg_t 184 bytes, gl_rot_int_t 28 bytes, gl_survey_t 116
 * bytes.  Worst-case stack: under 200 bytes.  No recursion, no allocation.
 */
#ifndef GL_TILT_H
#define GL_TILT_H

#include "gl_cal.h"
#include "gl_types.h"

/* ---- raw samples and scale ---------------------------------------------- */

typedef struct {
    int16_t ax, ay, az; /**< accelerometer counts, already in MARKER axes */
    int16_t gx, gy, gz; /**< gyro counts, marker axes */
} gl_imu_raw_t;

typedef struct {
    float accel_g_per_lsb;       /**< from the IMU driver's range setting */
    float gyro_rad_s_per_lsb;
    uint16_t block_samples;      /**< samples per block, 4..256 */
    float still_accel_std_g;     /**< a block is still if every axis' std is below this ... */
    float still_gyro_std_rad_s;  /**< ... and every gyro axis' std is below this ... */
    float still_step_g;          /**< ... and its mean moved less than this from the previous block */
} gl_tilt_cfg_t;

/** Defaults for 240 Hz sampling: 32-sample blocks (133 ms), 4 mg accel
 *  std, 0.02 rad/s gyro std, 3 mg block-to-block step.  The scale factors
 *  are left at 0 and MUST be filled in by the caller from the IMU driver. */
void gl_tilt_cfg_defaults(gl_tilt_cfg_t *cfg);

/* ---- block averaging with stillness gating -------------------------------- */

typedef struct {
    gl_tilt_cfg_t cfg;
    /* current block (exact integer sums) */
    int32_t sum_a[3], sum_g[3];
    int64_t sq_a[3], sq_g[3];
    uint16_t n;
    /* previous block mean, for the step test */
    float prev_mean_a[3];
    bool have_prev;
    /* accumulation over still blocks */
    int64_t acc_a[3], acc_g[3];
    uint32_t acc_n;
    float acc_var_a;             /**< sum of per-block mean axis variance (g^2) */
    uint16_t blocks_still;
    uint16_t blocks_total;
    uint16_t consecutive_still;
    bool last_still;
} gl_tilt_avg_t;

/** Start with a configuration (copied). */
void gl_tilt_avg_init(gl_tilt_avg_t *a, const gl_tilt_cfg_t *cfg);

/** Forget everything accumulated; keep the configuration. */
void gl_tilt_avg_reset(gl_tilt_avg_t *a);

/** Add one sample.  Returns true when this sample completed a block; the
 *  block's verdict is then available from gl_tilt_avg_last_still(). */
bool gl_tilt_avg_add(gl_tilt_avg_t *a, const gl_imu_raw_t *s);

/** Was the most recently completed block still? */
bool gl_tilt_avg_last_still(const gl_tilt_avg_t *a);

/** Number of still blocks in a row up to now (0 after any moving block). */
uint16_t gl_tilt_avg_consecutive_still(const gl_tilt_avg_t *a);

typedef struct {
    gl_vec3_t accel_g;         /**< mean of the still blocks, uncalibrated, in g */
    gl_vec3_t gyro_rad_s;      /**< mean gyro of the still blocks = gyro bias estimate */
    float accel_noise_g;       /**< rms per-axis sample noise within blocks */
    uint32_t samples;          /**< samples that went into the mean */
    uint16_t blocks_still;
    uint16_t blocks_total;
} gl_tilt_mean_t;

/** Mean over all still blocks since the last reset.  GL_ERR_MOTION if no
 *  block was still. */
gl_status_t gl_tilt_avg_result(const gl_tilt_avg_t *a, gl_tilt_mean_t *out);

/* ---- calibration ---------------------------------------------------------- */

/** a_cal = M (a_raw - b0 - b1 dT - b2 dT^2), dT = temp_c - t0. */
gl_vec3_t gl_tilt_apply_cal(const gl_cal_tilt_t *cal, gl_vec3_t accel_g, float temp_c);

/**
 * Six-face calibration.  meas[0..5] = mean raw readings (g) with marker
 * +x, -x, +y, -y, +z, -z pointing UP on an accurate fixture.  Solves
 * offset b and M such that M (meas[k] - b) is the true unit up vector.
 * GL_ERR_RANGE if the data are implausible (scale outside 0.8..1.2,
 * offset above 0.2 g, singular matrix).
 */
gl_status_t gl_tilt_six_face_solve(const gl_vec3_t meas[6], gl_vec3_t *offset_g, gl_mat3_t *m);

/**
 * Least-squares fit of the offset polynomial b(T) = b0 + b1 dT + b2 dT^2
 * per axis from n >= 3 (temperature, offset) pairs with at least 3 distinct
 * temperatures; fills offset_g, tempco1, tempco2 and t0_c of `cal`.
 */
gl_status_t gl_tilt_tempco_fit(const float *temp_c, const gl_vec3_t *offset_g, unsigned n,
                               float t0_c, gl_cal_tilt_t *cal);

/* ---- slope ---------------------------------------------------------------- */

/**
 * Surface gradient (uphill, rise/run, marker axes) from a calibrated
 * acceleration.  GL_ERR_RANGE if |a| is not within 0.9..1.1 g or the marker
 * is tilted more than 30 degrees (not lying on a green).
 */
gl_status_t gl_tilt_slope(gl_vec3_t accel_cal_g, gl_vec2_t *slope);

/** Slope magnitude in percent. */
float gl_tilt_slope_percent(gl_vec2_t slope);

/** Azimuth of the fall line (the DOWNHILL direction), rad, counter-clockwise
 *  from marker forward.  0 for a level surface. */
float gl_tilt_fall_line_rad(gl_vec2_t slope);

/** Components of a marker-frame slope along a line of sight at `bearing_rad`
 *  (CCW from forward): out.x = uphill rate toward the target, out.y = uphill
 *  rate toward the LEFT of that line (the cross slope). */
gl_vec2_t gl_tilt_slope_along(gl_vec2_t slope_marker, float bearing_rad);

/** The same slope in the solver's device frame (+x forward, +y left). */
gl_vec2_t gl_tilt_slope_to_device(gl_vec2_t slope_marker);

/* ---- rotation integrator (gyro) ------------------------------------------- */

typedef struct {
    float q[4];        /**< orientation now relative to start: w, x, y, z */
    gl_vec3_t bias;    /**< gyro bias subtracted from every sample, rad/s */
} gl_rot_int_t;

/** Begin integrating; `gyro_bias_rad_s` from the still period just before. */
void gl_rot_int_start(gl_rot_int_t *r, gl_vec3_t gyro_bias_rad_s);

/** Add one gyro sample (rad/s, marker axes) held for dt_s seconds. */
void gl_rot_int_add(gl_rot_int_t *r, gl_vec3_t gyro_rad_s, float dt_s);

/** Total rotation angle since start, rad, 0..pi. */
float gl_rot_int_angle(const gl_rot_int_t *r);

/**
 * Change of HEADING since start: the angle, counter-clockwise seen from
 * above, by which the marker's forward axis has turned about the vertical,
 * in (-pi, pi].  `up_start` is the unit up vector in the marker frame at
 * the start (from the tilt read just before).  Lifting and re-seating the
 * marker in between does not matter: only the net rotation counts.
 */
float gl_rot_int_yaw(const gl_rot_int_t *r, gl_vec3_t up_start);

/* ---- flip calibration and Precision Read ---------------------------------- */

/** Largest deviation of the flip yaw from 180 degrees that is accepted. */
#define GL_TILT_FLIP_YAW_TOL_RAD (30.0f * GL_DEG2RAD_F)

/**
 * Two slope readings m1, m2 (rise/run, each in the marker frame of ITS OWN
 * read, device bias NOT removed) taken on the same spot before and after
 * turning the marker by yaw_rad about the vertical (CCW positive, close to
 * +-pi).  Model: m1 = c + b, m2 = R(-yaw) c + b with c the true surface
 * slope in the frame of read 1 and b the device bias.  Solves both.
 * GL_ERR_RANGE if |yaw| is not within GL_TILT_FLIP_YAW_TOL_RAD of pi.
 */
gl_status_t gl_tilt_flip_solve(gl_vec2_t m1, gl_vec2_t m2, float yaw_rad, gl_vec2_t *bias,
                               gl_vec2_t *surface_slope);

typedef struct {
    gl_vec2_t slope;         /**< surface slope in the frame of read 1, bias-free */
    gl_vec2_t implied_bias;  /**< device bias implied by the two reads */
    float bias_mismatch;     /**< |implied bias - stored flip bias|, rise/run */
    float yaw_rad;
} gl_precision_t;

/**
 * Precision Read: combine the read at the ball (m1) with the re-read after
 * the 180-degree spin (m2); both raw (stored flip bias NOT subtracted).
 * bias_mismatch compares the implied bias with cal's stored one: a large
 * value means the two seatings disagreed (a confidence input).
 */
gl_status_t gl_tilt_precision_combine(gl_vec2_t m1, gl_vec2_t m2, float yaw_rad,
                                      const gl_cal_tilt_t *cal, gl_precision_t *out);

/* ---- Survey sample store --------------------------------------------------- */

#define GL_SURVEY_MAX_DROPS 4u

#define GL_DROP_FLAG_STICK        (1u << 0) /**< flagstick measured at this drop */
#define GL_DROP_FLAG_BASE_VISIBLE (1u << 1)
#define GL_DROP_FLAG_PRECISION    (1u << 2) /**< slope from a spin-and-reread */

typedef struct {
    gl_vec2_t slope;       /**< rise/run, marker frame of this drop, bias removed */
    float bearing_rad;     /**< flagstick bearing in this drop's marker frame */
    float range_m;         /**< distance to the flagstick */
    float range_sigma_m;
    float base_elev_rad;   /**< elevation of the lowest visible point of the stick */
    uint8_t flags;         /**< GL_DROP_FLAG_* */
} gl_survey_drop_t;

typedef struct {
    gl_survey_drop_t drop[GL_SURVEY_MAX_DROPS];
    uint8_t count;
} gl_survey_t;

/** Empty the store. */
void gl_survey_reset(gl_survey_t *s);

/** Add a drop.  GL_ERR_FULL after GL_SURVEY_MAX_DROPS; GL_ERR_PARAM if the
 *  drop has no flagstick fix (a survey sample needs its own range). */
gl_status_t gl_survey_add(gl_survey_t *s, const gl_survey_drop_t *d);

/** Index of the drop farthest from the flagstick (the ball end), or -1. */
int gl_survey_farthest(const gl_survey_t *s);

#endif /* GL_TILT_H */
