/*
 * gl_fieldlog.h - the records of the field log that make a read REPLAYABLE
 * (docs/VALIDATION_PLAN.md 3.3 and section 6): everything the estimator was
 * handed, everything it returned, and the circumstances.
 *
 * They are ordinary records of the ring log (core/gl_log, types
 * GL_LOG_REC_MEAS, GL_LOG_REC_READ2, GL_LOG_REC_TILT) and are written next
 * to the 72-byte read summary of phases 1 and 2 (GL_LOG_REC_READ), which is
 * kept as it was.  All fields little-endian; a float is the IEEE-754 single
 * the firmware computed with, bit for bit (NaN means what it means in
 * gl_solver.h: "not measured" / "unknown").
 *
 * ONE SOLVED READ writes, in this order and with one read_id:
 *
 *   GL_LOG_REC_MEAS   one per placement handed to the estimator (1 for a
 *                     Quick or Precision Read, 2..4 for a Survey), each the
 *                     complete gl_measurements_t: 68 bytes + 8 per turf-
 *                     horizon sample (0..41)             -> 68 .. 396 bytes
 *   GL_LOG_REC_READ   the 72-byte summary (gl_log.h)
 *   GL_LOG_REC_EVENT  GL_APP_LOGEV_ESTIMATE
 *   GL_LOG_REC_READ2  context, options, tilt, temperatures, grain, timing,
 *                     the estimate and the fit record    -> GL_FIELDLOG_READ_LEN
 *
 * The MEAS records come first so that a READ2 record found in a dump always
 * has its inputs in front of it (the log drops the OLDEST sector first).
 *
 * A TILT record (GL_FIELDLOG_TILT_LEN bytes) is a placement without a
 * camera read: see gl_fieldlog_tilt_t.
 *
 * LAYOUT VERSION: byte 0 of READ2 and TILT is GL_FIELDLOG_LAYOUT; byte 7 of
 * MEAS likewise.  A decoder must refuse a layout it does not know.  The
 * exact offsets are those of the encoders in gl_fieldlog.c, mirrored by
 * tools/glctl/logdec.py; tests/test_fieldlog.c pins the sizes and decodes
 * every field at its offset.
 *
 * Pure: no HAL, no statics.  Stack of the encoders: under 100 bytes.
 */
#ifndef GL_FIELDLOG_H
#define GL_FIELDLOG_H

#include "gl_settings.h"
#include "gl_solver.h"
#include "gl_types.h"

#ifdef GL_SOLVER_DOUBLE
#error "gl_fieldlog logs the firmware's single-precision records"
#endif

#define GL_FIELDLOG_LAYOUT 1u

/* ---- one placement as the estimator received it --------------------------- */

#define GL_FIELDLOG_MEAS_FIXED 68u
#define GL_FIELDLOG_MEAS_MAX (GL_FIELDLOG_MEAS_FIXED + 8u * GL_SOLVER_MAX_HORIZON) /* 396 */

#define GL_FIELDLOG_MEAS_F_BALL (1u << 0)         /**< this placement is the one at the ball */
#define GL_FIELDLOG_MEAS_F_FLAG_FOUND (1u << 1)
#define GL_FIELDLOG_MEAS_F_BASE_VISIBLE (1u << 2)
#define GL_FIELDLOG_MEAS_F_TOP_VISIBLE (1u << 3)

/** Returns the record length (GL_FIELDLOG_MEAS_FIXED + 8 * n_horizon), or 0
 *  if `cap` is too small.  `drop` is the index of the placement in the
 *  estimator call, `n_drops` their number. */
size_t gl_fieldlog_meas_encode(uint16_t read_id, uint8_t drop, uint8_t n_drops, bool is_ball,
                               const gl_measurements_t *m, uint8_t *out, size_t cap);

/* ---- the circumstances of a read ------------------------------------------- */

#define GL_FIELDLOG_F_PRECISION (1u << 0)   /**< slope = combination of two reads 180 deg apart */
#define GL_FIELDLOG_F_SURVEY (1u << 1)      /**< estimated from several stored placements */
#define GL_FIELDLOG_F_FLAG_FOUND (1u << 2)
#define GL_FIELDLOG_F_AMBIGUOUS (1u << 3)
#define GL_FIELDLOG_F_TOP_VALID (1u << 4)
#define GL_FIELDLOG_F_GRAIN_RAN (1u << 5)   /**< the grain reader ran in this read */
#define GL_FIELDLOG_F_GRAIN_VALID (1u << 6)
#define GL_FIELDLOG_F_LINE_HERE (1u << 7)
#define GL_FIELDLOG_F_CAMERAS_OFF (1u << 8) /**< tilt-only mode: no camera read was made */
#define GL_FIELDLOG_F_SOLID_LINE (1u << 9)  /**< the line was drawn solid (a solution) */

/** Stages of a read whose end time is logged, in ms after the marker was
 *  found still (GL_EV_STILL acted on).  0xFFFF = did not happen. */
typedef enum {
    GL_FIELDLOG_T_TILT_DONE = 0,   /**< the 1 s tilt average (and the grain reading) complete */
    GL_FIELDLOG_T_CAM_ON,          /**< camera rail switched on */
    GL_FIELDLOG_T_CAPTURE_DONE,    /**< last strip analysed (the rail went off cam_on_ms after
                                        it came on, before the last group was analysed) */
    GL_FIELDLOG_T_SOLVE_START,
    GL_FIELDLOG_T_SOLVE_DONE,
    GL_FIELDLOG_T_COUNT
} gl_fieldlog_stage_t;

typedef struct {
    /* identity and versions */
    uint16_t read_id;
    uint32_t rtc_s;
    uint32_t tick_ms;             /**< milliseconds since boot at the end of the solve */
    uint16_t fw_version;
    uint32_t fw_build;
    uint32_t solver_version;
    uint8_t hw_rev;
    uint8_t cal_version;          /**< GL_CAL_VERSION of the firmware */
    uint8_t cal_flags[5];         /**< flags of the tilt, left, right, grain, device records */
    uint16_t cal_crc[5];          /**< CRC-16 of each record as it would be stored now: two
                                       reads with equal values were taken with the same
                                       calibration */
    uint8_t settings[GL_SETTINGS_BLOB_LEN]; /**< the settings in force (gl_settings_encode) */
    /* the call */
    uint8_t n_drops, ball_index;
    uint8_t solver_ret;           /**< gl_status_t the estimator returned */
    uint8_t tier;                 /**< gl_read_tier_t of the camera read */
    uint8_t base;                 /**< gl_vis_base_t */
    uint8_t seat;                 /**< gl_cal_seat_t whose zero was removed (0xFF = none stored) */
    uint8_t note;                 /**< gl_ui_note_t shown */
    uint8_t groups_ok;            /**< L R R L groups that measured the stick */
    uint16_t flags;               /**< GL_FIELDLOG_F_* */
    /* tilt */
    gl_vec2_t slope_raw;          /**< calibrated slope, zero NOT removed (marker frame) */
    gl_vec2_t slope;              /**< slope used (zero removed, or the Precision combination) */
    gl_vec2_t zero;               /**< the zero that was removed */
    gl_vec2_t spin_slope_raw;     /**< Precision: the reading before the spin ... */
    gl_vec2_t reread_slope_raw;   /**< ... and after it */
    float view_yaw_rad;           /**< Precision: the measured turn */
    gl_vec3_t up;                 /**< unit up vector, marker frame */
    gl_vec3_t gyro_bias;          /**< rad/s */
    float tilt_scatter;           /**< RMS of the 133 ms block slopes about their mean, rise/run */
    float accel_noise_g;          /**< rms sample noise within the blocks */
    uint8_t tilt_blocks;          /**< still blocks averaged */
    /* temperatures and supply */
    int16_t imu_temp_c_x100;
    int16_t cell_temp_c_x10;      /**< NTC2; INT16_MIN = not valid */
    int16_t mcu_temp_c_x10;       /**< INT16_MIN = not valid */
    uint16_t batt_mv;
    /* grain (valid with GL_FIELDLOG_F_GRAIN_RAN) */
    float grain_red_mod, grain_red_az, grain_nir_mod, grain_nir_az;
    uint8_t grain_reject;         /**< GL_GRAIN_REJECT_* */
    uint16_t grain_signal[16];    /**< per-LED gain-corrected signal, counts (clamped) */
    /* vision summary */
    float bearing_rad, disparity_px, disparity_sigma_px, base_elev_rad, top_elev_rad;
    float diag_range_m, diag_range_sigma_m; /**< the application's own range fusion (diagnostic) */
    float stick_height_m, stick_height_sigma_m; /**< learned stick height at the read */
    uint8_t quality[5];           /**< rows used %, line contrast, sharpness match %, saturated %,
                                       sun (0/1) */
    /* timing */
    uint16_t stage_ms[GL_FIELDLOG_T_COUNT];
    uint16_t cam_on_ms;           /**< how long the camera rail was on */
    /* what was shown */
    float shown_aim_rad;          /**< aim line as drawn, marker's current frame, display
                                       rotation NOT included */
    float shown_confidence;
    float display_rot_rad;        /**< the stored rotation the renderer added */
} gl_fieldlog_ctx_t;

#define GL_FIELDLOG_READ_LEN 684u

/** Serialise context, options, estimate and fit to GL_FIELDLOG_READ_LEN
 *  bytes.  Returns that length, or 0 if `cap` is too small. */
size_t gl_fieldlog_read_encode(const gl_fieldlog_ctx_t *c, const gl_solver_options_t *opt,
                               const gl_estimate_t *e, const gl_patch_fit_t *fit, uint8_t *out,
                               size_t cap);

/* ---- a placement without a camera read ------------------------------------- */

typedef enum {
    GL_FIELDLOG_TILT_PLACEMENT = 0, /**< the tilt average of a read (tilt logger ON / ONLY) */
    GL_FIELDLOG_TILT_REREAD = 1,    /**< the re-read after the spin of a Precision Read */
    GL_FIELDLOG_TILT_ZERO_1 = 2,    /**< first read of a zeroing */
    GL_FIELDLOG_TILT_ZERO_2 = 3,    /**< second read of a zeroing (after the half turn) */
    GL_FIELDLOG_TILT_TOO_HOT = 4,   /**< the camera read was refused (E13): always logged */
    GL_FIELDLOG_TILT_NOT_SOLVED = 5 /**< the read that followed did not end in a result: always
                                         logged (no READ2 record exists for it) */
} gl_fieldlog_tilt_kind_t;

typedef struct {
    uint8_t kind;                 /**< gl_fieldlog_tilt_kind_t */
    uint8_t seat;                 /**< gl_cal_seat_t whose zero was removed; a zeroing: the seat
                                       being zeroed */
    uint16_t read_id;             /**< of the read it belongs to (the NEXT read's id for a
                                       placement: a READ2 record with the same id may follow) */
    uint32_t rtc_s;
    uint32_t tick_ms;
    gl_vec2_t slope_raw;          /**< calibrated slope, zero not removed */
    gl_vec2_t slope;              /**< zero removed */
    gl_vec3_t accel_g;            /**< mean of the still blocks, UNCALIBRATED, g */
    gl_vec3_t gyro_bias;
    float tilt_scatter;
    float accel_noise_g;
    float yaw_rad;                /**< ZERO_2 / REREAD: the measured turn; else 0 */
    int16_t imu_temp_c_x100;
    int16_t cell_temp_c_x10;
    int16_t mcu_temp_c_x10;
    uint16_t batt_mv;
    uint16_t cal_tilt_crc;
    uint8_t cal_tilt_flags;
    uint8_t tilt_blocks;
} gl_fieldlog_tilt_t;

#define GL_FIELDLOG_TILT_LEN 80u

void gl_fieldlog_tilt_encode(const gl_fieldlog_tilt_t *t, uint8_t out[GL_FIELDLOG_TILT_LEN]);

#endif /* GL_FIELDLOG_H */
