/*
 * gl_cal.h - calibration records: contents, defaults, storage / wire format.
 *
 * Three kinds of record, each stored as one versioned little-endian blob in
 * the flash store (gl_store) and readable over USB (gl_proto GET_CAL):
 *
 *   GL_CAL_ID_TILT    accelerometer offset, temperature polynomial, 3x3
 *                     scale / cross-axis matrix (factory 6-face), user
 *                     zeroing bias (180-degree reversal on any hard flat
 *                     surface; never done in the cradle)
 *   GL_CAL_ID_CAM_L/R per-camera intrinsics (fx, fy, cx, cy, k1) and
 *                     extrinsics to the marker (= IMU) frame
 *   GL_CAL_ID_GRAIN   per-LED white-reference gains and the modulation
 *                     acceptance threshold from the noise-floor gate
 *
 * A unit with no stored record runs on gl_cal_*_defaults(): nominal design
 * geometry, identity matrices, zero offsets, flags = 0 ("not calibrated").
 * The UI shows reduced confidence while a flag is missing.
 */
#ifndef GL_CAL_H
#define GL_CAL_H

#include "gl_types.h"

#define GL_CAL_VERSION 1u

typedef enum {
    GL_CAL_ID_TILT = 1,
    GL_CAL_ID_CAM_L = 2,
    GL_CAL_ID_CAM_R = 3,
    GL_CAL_ID_GRAIN = 4
} gl_cal_id_t;

/* ---- tilt --------------------------------------------------------------- */

#define GL_CAL_TILT_FLAG_FACTORY (1u << 0) /**< 6-face + temperature cal present */
#define GL_CAL_TILT_FLAG_FLIP    (1u << 1) /**< user zeroing (180-degree reversal) present */

typedef struct {
    float offset_g[3];          /**< accel zero offset b0 at t0_c, in g, marker axes */
    float tempco1_g_per_k[3];   /**< b1: offset drift, g / K */
    float tempco2_g_per_k2[3];  /**< b2: offset drift, g / K^2 */
    float t0_c;                 /**< reference temperature of the polynomial, deg C */
    gl_mat3_t m;                /**< a_cal = M (a_raw - b(T)); identity when uncalibrated */
    float flip_bias_x;          /**< residual slope bias (rise/run, marker x) from the user zeroing */
    float flip_bias_y;          /**< same, marker y; both are SUBTRACTED from a slope reading */
    float flip_temp_c;          /**< IMU temperature at the zeroing */
    uint32_t flip_time_s;       /**< RTC seconds at the zeroing (0 = unknown) */
    uint8_t flags;              /**< GL_CAL_TILT_FLAG_* */
} gl_cal_tilt_t;

#define GL_CAL_TILT_BLOB_LEN 94u

/** Uncalibrated record: zero offsets, identity matrix, t0 = 25 C, flags 0. */
void gl_cal_tilt_defaults(gl_cal_tilt_t *c);
/** Serialise to GL_CAL_TILT_BLOB_LEN bytes (version byte first). */
void gl_cal_tilt_encode(const gl_cal_tilt_t *c, uint8_t out[GL_CAL_TILT_BLOB_LEN]);
/** GL_ERR_PARAM (short), GL_ERR_UNSUPPORTED (version), GL_ERR_RANGE (a
 *  non-finite or implausible field).  `c` is only modified on GL_OK. */
gl_status_t gl_cal_tilt_decode(const uint8_t *blob, size_t len, gl_cal_tilt_t *c);

/* ---- camera ------------------------------------------------------------- */

#define GL_CAL_CAM_FLAG_INTRINSICS (1u << 0)
#define GL_CAL_CAM_FLAG_EXTRINSICS (1u << 1)

typedef struct {
    float fx_px, fy_px;   /**< focal lengths in pixels */
    float cx_px, cy_px;   /**< principal point, full-sensor pixel coordinates */
    float k1;             /**< radial term: x_dist = x_undist * (1 + k1 r_undist^2) */
    /** Extrinsics.  Camera-to-marker rotation is
     *      R = Rz(yaw_left) * Rx(pitch_up) * R_nominal * Rz_cam(roll)
     *  with R_nominal mapping camera (x right, y down, z forward) onto marker
     *  (x right, y forward, z up).  All three angles are zero for a perfectly
     *  mounted camera. */
    float pitch_up_rad;   /**< optical axis above the base plane */
    float yaw_left_rad;   /**< optical axis rotated counter-clockwise seen from above */
    float roll_rad;       /**< rotation about the optical axis (right-handed about camera +z) */
    float pos_mm[3];      /**< optical centre in the marker frame, mm */
    uint8_t flags;        /**< GL_CAL_CAM_FLAG_* */
} gl_cal_cam_t;

#define GL_CAL_CAM_BLOB_LEN 46u

/** Nominal design values from gl_config.h for the given camera (0 = left,
 *  1 = right): f = 657 px, principal point at the sensor centre, k1 = 0,
 *  angles 0, position from master_params. */
void gl_cal_cam_defaults(gl_cal_cam_t *c, unsigned cam_index);
/** Serialise to GL_CAL_CAM_BLOB_LEN bytes. */
void gl_cal_cam_encode(const gl_cal_cam_t *c, uint8_t out[GL_CAL_CAM_BLOB_LEN]);
/** Parse and range-check; errors as for gl_cal_tilt_decode(). */
gl_status_t gl_cal_cam_decode(const uint8_t *blob, size_t len, gl_cal_cam_t *c);

/* ---- grain -------------------------------------------------------------- */

#define GL_GRAIN_LEDS 16u /* 0..7 red, 8..15 near-infrared */

#define GL_CAL_GRAIN_FLAG_WHITE_REF   (1u << 0) /**< gains measured on the white tile */
#define GL_CAL_GRAIN_FLAG_NOISE_FLOOR (1u << 1) /**< threshold set from gate 0 data */

typedef struct {
    float gain[GL_GRAIN_LEDS];      /**< white-tile response of each LED, relative (mean 1) */
    float mod_threshold;            /**< accept a reading only if modulation >= this */
    float noise_floor_mod;          /**< measured no-grain modulation (median), 0 = unknown */
    uint16_t min_signal_counts;     /**< reject if the mean on-minus-dark signal is below */
    uint16_t max_dark_drift_counts; /**< reject an LED cycle if |dark2 - dark1| exceeds */
    uint8_t flags;                  /**< GL_CAL_GRAIN_FLAG_* */
} gl_cal_grain_t;

#define GL_CAL_GRAIN_BLOB_LEN 78u

/** Unity gains, threshold = GL_PROV_GRAIN_MOD_THRESHOLD_DEFAULT, flags 0. */
void gl_cal_grain_defaults(gl_cal_grain_t *c);
/** Serialise to GL_CAL_GRAIN_BLOB_LEN bytes. */
void gl_cal_grain_encode(const gl_cal_grain_t *c, uint8_t out[GL_CAL_GRAIN_BLOB_LEN]);
/** Parse and range-check (a threshold below 0.01 is refused); errors as for
 *  gl_cal_tilt_decode(). */
gl_status_t gl_cal_grain_decode(const uint8_t *blob, size_t len, gl_cal_grain_t *c);

#endif /* GL_CAL_H */
