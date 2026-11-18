/*
 * gl_cal.h - calibration records: contents, defaults, storage / wire format.
 *
 * Five kinds of record, each stored as one versioned little-endian blob in
 * the flash store (gl_store) and readable over USB (gl_proto GET_CAL):
 *
 *   GL_CAL_ID_TILT    accelerometer offset, temperature polynomial, 3x3
 *                     scale / cross-axis matrix (factory 6-face), and the TWO
 *                     LEVEL ZEROS of DESIGN_SPEC E11: the ball seat (the
 *                     marker stands on its three ball feet on a hard plate)
 *                     and the base-face seat (it rests on its whole base
 *                     face, as on turf), each with its temperature, time and
 *                     scatter
 *   GL_CAL_ID_CAM_L/R per-camera intrinsics (fx, fy, cx, cy, k1), extrinsics
 *                     to the marker (= IMU) frame and the camera horizon row
 *                     (CAM_HORIZON: the sensor row on which a level target
 *                     at the height of the lens is imaged at the centre
 *                     column)
 *   GL_CAL_ID_GRAIN   per-LED white-reference gains, the modulation
 *                     acceptance threshold from the noise-floor gate
 *                     (GRAIN_FLOOR) and the photodiode dark offset read on
 *                     the bare board (assembly step 11a)
 *   GL_CAL_ID_DEVICE  the display rotation of DESIGN_SPEC E12 and the serial
 *                     number: the processor's 96-bit unique number as it was
 *                     when the unit was calibrated, and the short serial
 *                     derived from it
 *
 * WHICH ZERO A READ USES is not a calibration value but a setting
 * (gl_settings_t.surface: TURF = base face, the default; HARD = ball seat):
 * gl_cal_tilt_zero() applies the rule.  The stick height learned per course
 * is not here either: it is a store item of its own (GL_STORE_ID_COURSE,
 * core/gl_range).
 *
 * VERSIONS.  Byte 0 of every blob is the layout version.
 *   version 2 (this firmware): the fields below, then a CRC-16/CCITT-FALSE
 *             over all preceding bytes of the blob (little-endian, the last
 *             two bytes).  A blob whose CRC does not match is refused
 *             (GL_ERR_CRC) whatever its fields look like.
 *   version 1 (phases 1 and 2; tilt 94, camera 46, grain 78 bytes, no CRC):
 *             still READ and converted - gl_cal_*_decode() accepts both.
 *             The version-1 "user zeroing" becomes the BALL-seat zero (it
 *             was taken on a hard flat surface); the base-face zero, the
 *             horizon row and the dark offset are "not measured".  Nothing
 *             is ever written in version 1.
 * The store keeps a blob as it was written: a version-1 record stays
 * version 1 in flash until something stores that record again.
 *
 * A unit with no stored record runs on gl_cal_*_defaults(): nominal design
 * geometry, identity matrices, zero offsets, flags = 0 ("not calibrated").
 * NOTHING ON THE UNIT SHOWS A MISSING CALIBRATION (the confidence is not
 * reduced): GL_CMD_GET_IDENT reports the flags, and the factory's final
 * test must check them.
 */
#ifndef GL_CAL_H
#define GL_CAL_H

#include "gl_types.h"

#define GL_CAL_VERSION 2u
#define GL_CAL_VERSION_PHASE1 1u

typedef enum {
    GL_CAL_ID_TILT = 1,
    GL_CAL_ID_CAM_L = 2,
    GL_CAL_ID_CAM_R = 3,
    GL_CAL_ID_GRAIN = 4,
    GL_CAL_ID_DEVICE = 5
} gl_cal_id_t;

/** Longest blob of any record (GET_CAL / SET_CAL buffers). */
#define GL_CAL_MAX_BLOB_LEN 120u

/* ---- tilt --------------------------------------------------------------- */

#define GL_CAL_TILT_FLAG_FACTORY (1u << 0) /**< 6-face calibration present */
#define GL_CAL_TILT_FLAG_FLIP    (1u << 1) /**< BALL-seat zero present (flip_*: the 180-degree
                                                reversal on a hard flat surface - the user's
                                                zeroing, or the factory's on the plain plate) */
#define GL_CAL_TILT_FLAG_BASE    (1u << 2) /**< BASE-FACE zero present (base_*: the factory's
                                                reversal on the plate with the ball pockets) */
#define GL_CAL_TILT_FLAG_TEMPCO  (1u << 3) /**< temperature coefficients fitted (not zero by default) */
#define GL_CAL_TILT_FLAG_BASE_DERIVED (1u << 4) /**< the base-face zero was MOVED with a later
                                                ball-seat zeroing (the difference between the
                                                two seats is a property of the housing and was
                                                kept), not measured again */
#define GL_CAL_TILT_FLAG_ALL 0x1Fu

/** The two seats of DESIGN_SPEC E11.  Values of gl_settings_t.surface. */
typedef enum {
    GL_CAL_SEAT_BASE = 0, /**< whole base face (turf): the default for a read */
    GL_CAL_SEAT_BALL = 1, /**< three ball feet (hard plate): bench checks */
    GL_CAL_SEAT_COUNT,
    GL_CAL_SEAT_NONE = 0xFF /**< no zero stored at all */
} gl_cal_seat_t;

typedef struct {
    float offset_g[3];          /**< accel zero offset b0 at t0_c, in g, marker axes */
    float tempco1_g_per_k[3];   /**< b1: offset drift, g / K */
    float tempco2_g_per_k2[3];  /**< b2: offset drift, g / K^2 */
    float t0_c;                 /**< reference temperature of the polynomial, deg C */
    gl_mat3_t m;                /**< a_cal = M (a_raw - b(T)); identity when uncalibrated */
    /* ball-seat zero (the names are those of phases 1 and 2, where it was the only one) */
    float flip_bias_x;          /**< residual slope bias (rise/run, marker x) on the BALL seat */
    float flip_bias_y;          /**< same, marker y; both are SUBTRACTED from a slope reading */
    float flip_temp_c;          /**< IMU temperature at that zeroing */
    uint32_t flip_time_s;       /**< RTC seconds at that zeroing (0 = unknown) */
    float flip_scatter;         /**< scatter of that zeroing (rise/run, RMS of the 133 ms block
                                     slopes about their mean, the worse of its two reads);
                                     0 = not recorded */
    /* base-face zero */
    float base_bias_x;          /**< residual slope bias on the BASE-FACE seat */
    float base_bias_y;
    float base_temp_c;
    uint32_t base_time_s;
    float base_scatter;
    uint8_t flags;              /**< GL_CAL_TILT_FLAG_* */
} gl_cal_tilt_t;

#define GL_CAL_TILT_BLOB_LEN 120u
#define GL_CAL_TILT_BLOB_LEN_V1 94u

/** Uncalibrated record: zero offsets, identity matrix, t0 = 25 C, flags 0. */
void gl_cal_tilt_defaults(gl_cal_tilt_t *c);
/** Serialise to GL_CAL_TILT_BLOB_LEN bytes (version byte first, CRC last). */
void gl_cal_tilt_encode(const gl_cal_tilt_t *c, uint8_t out[GL_CAL_TILT_BLOB_LEN]);
/** Version 2 or 1 (see the file comment).  GL_ERR_PARAM (shorter than the
 *  record of ITS version), GL_ERR_UNSUPPORTED (version), GL_ERR_CRC,
 *  GL_ERR_RANGE (a non-finite or implausible field).  `c` is only modified
 *  on GL_OK. */
gl_status_t gl_cal_tilt_decode(const uint8_t *blob, size_t len, gl_cal_tilt_t *c);

/**
 * The level zero a read uses.  `wanted` is the seat of the surface setting.
 * If that zero is stored it is returned.  If only the OTHER seat's zero is
 * stored, that one is returned (a unit zeroed by its user on a hard surface
 * and never at the factory behaves as it did in phase 2; the two seats
 * differ by up to 1.6 mrad, DESIGN_SPEC E11).  If none is stored the bias is
 * zero.  Returns the seat whose zero was written to *bias, or
 * GL_CAL_SEAT_NONE.  `cal` NULL = none.
 */
gl_cal_seat_t gl_cal_tilt_zero(const gl_cal_tilt_t *cal, gl_cal_seat_t wanted, gl_vec2_t *bias);

/**
 * Store the result of a zeroing in the record (RAM only; the caller encodes
 * and stores).  BALL seat: if a base-face zero exists it is moved by the
 * same amount (GL_CAL_TILT_FLAG_BASE_DERIVED): what a later zeroing on a
 * hard surface finds is drift of the sensor, common to both seats, and the
 * difference between the seats is mechanical.  BASE seat: the ball-seat zero
 * is left alone and BASE_DERIVED is cleared.
 */
void gl_cal_tilt_set_zero(gl_cal_tilt_t *cal, gl_cal_seat_t seat, gl_vec2_t bias, float temp_c,
                          uint32_t time_s, float scatter);

/* ---- camera ------------------------------------------------------------- */

#define GL_CAL_CAM_FLAG_INTRINSICS (1u << 0)
#define GL_CAL_CAM_FLAG_EXTRINSICS (1u << 1)
#define GL_CAL_CAM_FLAG_HORIZON    (1u << 2) /**< horizon_row measured (CAM_HORIZON); pitch_up_rad
                                                  and roll_rad were set from it */
#define GL_CAL_CAM_FLAG_ALL 0x07u

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
    float horizon_row;    /**< CAM_HORIZON: the sensor row (full-sensor coordinates) on which
                               a level target at the height of the lens is imaged at the
                               centre column, as measured at the factory; valid with
                               GL_CAL_CAM_FLAG_HORIZON, otherwise the nominal row */
    uint8_t flags;        /**< GL_CAL_CAM_FLAG_* */
} gl_cal_cam_t;

#define GL_CAL_CAM_BLOB_LEN 52u
#define GL_CAL_CAM_BLOB_LEN_V1 46u

/** Nominal design values from gl_config.h for the given camera (0 = left,
 *  1 = right): f = 657 px, principal point at the sensor centre, k1 = 0,
 *  angles 0, position from master_params. */
void gl_cal_cam_defaults(gl_cal_cam_t *c, unsigned cam_index);
/** Serialise to GL_CAL_CAM_BLOB_LEN bytes. */
void gl_cal_cam_encode(const gl_cal_cam_t *c, uint8_t out[GL_CAL_CAM_BLOB_LEN]);
/** Parse and range-check; errors as for gl_cal_tilt_decode(). */
gl_status_t gl_cal_cam_decode(const uint8_t *blob, size_t len, gl_cal_cam_t *c);

/**
 * CAM_HORIZON: adopt a measured horizon row.  `row` is where the camera
 * images a level target at the height of its lens at the centre column
 * (full-sensor row, y down), `roll_rad` the measured rotation about the
 * optical axis (0 if not measured).  Sets horizon_row, roll_rad and
 *
 *     pitch_up_rad = atan((row - cy) / fy)
 *
 * (an optical axis that points UP puts the horizon BELOW the centre: a
 * larger row), and GL_CAL_CAM_FLAG_HORIZON.  GL_ERR_RANGE if the row is not
 * finite, lies outside the sensor or gives a pitch beyond the record's
 * +-0.2 rad, or the roll is beyond +-0.2 rad; nothing is changed then.
 */
gl_status_t gl_cal_cam_set_horizon(gl_cal_cam_t *c, float row, float roll_rad);

/* ---- grain -------------------------------------------------------------- */

#define GL_GRAIN_LEDS 16u /* 0..7 red, 8..15 near-infrared */

#define GL_CAL_GRAIN_FLAG_WHITE_REF   (1u << 0) /**< gains measured on the white tile */
#define GL_CAL_GRAIN_FLAG_NOISE_FLOOR (1u << 1) /**< threshold set from gate 0 data (GRAIN_FLOOR) */
#define GL_CAL_GRAIN_FLAG_DARK_OFFSET (1u << 2) /**< pd_dark_counts recorded (assembly step 11a) */
#define GL_CAL_GRAIN_FLAG_ALL 0x07u

typedef struct {
    float gain[GL_GRAIN_LEDS];      /**< white-tile response of each LED, relative (mean 1) */
    float mod_threshold;            /**< accept a reading only if modulation >= this */
    float noise_floor_mod;          /**< measured no-grain modulation (median), 0 = unknown */
    uint16_t min_signal_counts;     /**< reject if the mean on-minus-dark signal is below */
    uint16_t max_dark_drift_counts; /**< reject an LED cycle if |dark2 - dark1| exceeds */
    uint16_t pd_dark_counts;        /**< photodiode amplifier output with every LED off, in the
                                         dark, ADC counts, as read on the bare board */
    uint8_t flags;                  /**< GL_CAL_GRAIN_FLAG_* */
} gl_cal_grain_t;

#define GL_CAL_GRAIN_BLOB_LEN 82u
#define GL_CAL_GRAIN_BLOB_LEN_V1 78u

/** Unity gains, threshold = GL_PROV_GRAIN_MOD_THRESHOLD_DEFAULT, flags 0. */
void gl_cal_grain_defaults(gl_cal_grain_t *c);
/** Serialise to GL_CAL_GRAIN_BLOB_LEN bytes. */
void gl_cal_grain_encode(const gl_cal_grain_t *c, uint8_t out[GL_CAL_GRAIN_BLOB_LEN]);
/** Parse and range-check (a threshold below 0.01 is refused); errors as for
 *  gl_cal_tilt_decode(). */
gl_status_t gl_cal_grain_decode(const uint8_t *blob, size_t len, gl_cal_grain_t *c);

/* ---- device: display rotation, serial number ------------------------------ */

#define GL_CAL_DEV_FLAG_DISPLAY_ROT (1u << 0) /**< display_rot_rad measured (E12) */
#define GL_CAL_DEV_FLAG_SERIAL      (1u << 1) /**< unique_id / serial recorded */
#define GL_CAL_DEV_FLAG_ALL 0x03u

/** Largest display rotation the record accepts: 2 degrees.  The glass can
 *  sit up to about 1.2 degrees rotated in its pocket (E22: 1.19 computed);
 *  more than 2 is a wrong measurement or a wrong sign convention. */
#define GL_CAL_DISPLAY_ROT_MAX_RAD 0.0349066f

typedef struct {
    /** E12.  The angle by which the firmware TURNS THE DRAWN AIM LINE,
     *  counter-clockwise for a viewer looking down on the display (the sense
     *  of every angle on the screen: + = toward the golfer's left of the
     *  visor axis).  It is MINUS the angle at which the factory camera saw
     *  the uncorrected reference line (GL_CMD_DISPLAY_TEST pattern
     *  GL_DISP_PATTERN_REF_RAW) lie against the visor flat's normal: a glass
     *  that sits 1.2 degrees counter-clockwise shows that line 1.2 degrees
     *  counter-clockwise, and the stored value is -1.2 degrees. */
    float display_rot_rad;
    uint8_t unique_id[12];  /**< the processor's unique number when this was written */
    uint32_t serial;        /**< gl_cal_serial_from_uid(unique_id) */
    uint32_t time_s;        /**< RTC seconds when the record was last written (0 = unknown) */
    uint8_t flags;          /**< GL_CAL_DEV_FLAG_* */
} gl_cal_device_t;

#define GL_CAL_DEVICE_BLOB_LEN 28u

/** Rotation 0, serial 0, flags 0. */
void gl_cal_device_defaults(gl_cal_device_t *c);
void gl_cal_device_encode(const gl_cal_device_t *c, uint8_t out[GL_CAL_DEVICE_BLOB_LEN]);
/** Errors as for gl_cal_tilt_decode() (there is no version-1 device record). */
gl_status_t gl_cal_device_decode(const uint8_t *blob, size_t len, gl_cal_device_t *c);

/**
 * The short serial number: CRC-32 (IEEE 802.3, reflected, as zlib's) of the
 * 12 bytes of the unique number.  0 is mapped to 1 (0 means "none").  Two
 * units can share one: with 10 000 units the chance that any two do is about
 * 1.2 % (birthday bound, 32 bits) - the unique number itself is the identity
 * of record, the short serial is what is marked on the base plate.
 */
uint32_t gl_cal_serial_from_uid(const uint8_t unique_id[12]);

/** The serial as 7 characters of Crockford base 32 (no I, L, O, U), most
 *  significant first, NUL terminated: `out` must hold 8 bytes. */
void gl_cal_serial_text(uint32_t serial, char out[8]);

#endif /* GL_CAL_H */
