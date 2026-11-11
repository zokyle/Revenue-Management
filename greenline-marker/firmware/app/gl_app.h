/*
 * gl_app.h - the GreenLine GL-1 application: one object, one cooperative
 * main loop, no RTOS.
 *
 *     for (;;) gl_app_run_once(&app);
 *
 * One iteration of gl_app_run_once():
 *   1. collect the pending interrupt sources (gl_hal_irq_take) and turn
 *      them into work: VBUS / charger pins, the IMU wake-up while asleep,
 *      one IMU sample (-> gl_motion: stillness, motion, posture, tap, dial,
 *      spin; -> the tilt average; -> the zeroing procedure), USB bytes
 *      (-> gl_proto), a finished strip capture (-> gl_read)
 *   2. timers: UI time-outs, battery, streams, the "SAVED" screen
 *   3. drain the event queue through the UI transition table and carry out
 *      the actions it returns
 *   4. redraw the screen if something changed (only changed LCD lines go out)
 *   5. sleep until the next interrupt source or deadline: Stop mode
 *      whenever nothing needs the fast clocks, idle sleep while the camera
 *      rail is on or USB is running
 *
 * Everything the firmware remembers lives in gl_app_t (static storage in
 * app/gl_main.c; the host tests allocate their own).  Nothing is allocated
 * dynamically.
 *
 * RAM: sizeof(gl_app_t) is about 184.5 kB, of which 173 kB are the image
 * buffers and vision work areas of gl_read_t (see gl_read.h).  The exact
 * figure is in the `make cross` size table (bss of gl_main); gl_app.c and
 * gl_usb.c add 1.8 kB of static scratch (one raw-strip log record, two raw
 * grain measurements).
 * Stack (arm-none-eabi-gcc -Os, -fstack-usage): the deepest chain is
 * gl_app_run_once (312) -> gl_read_step (208) -> strip / band analysis
 * (650 / 640 including their callees) = about 1.2 kB; the logging, solve,
 * USB and start-up chains stay below 1 kB.  With the HAL backend's frames
 * and nested interrupt frames on top, a 4 kB main stack is ample.  No
 * recursion anywhere.
 */
#ifndef GL_APP_H
#define GL_APP_H

#include "gl_app_cfg.h"
#include "gl_cal.h"
#include "gl_event.h"
#include "gl_gfx.h"
#include "gl_log.h"
#include "gl_motion.h"
#include "gl_proto.h"
#include "gl_range.h"
#include "gl_read.h"
#include "gl_settings.h"
#include "gl_solver.h"
#include "gl_tilt.h"
#include "gl_types.h"
#include "gl_ui.h"
#include "ls013b7dh03.h"
#include "lsm6dsv16x.h"
#include "mx25r.h"
#include "ov7692.h"
#include "power.h"

/**
 * One read as the application keeps it.  Slopes, bearings and the target
 * are in the marker frame the CAMERAS had when they measured the flagstick
 * ("read frame").  view_yaw_rad is how far the marker has been turned since
 * (0, or about pi after the spin of a Precision Read); the screen is drawn
 * in the marker's current frame.
 */
typedef struct {
    bool tilt_valid;
    gl_vec3_t up;             /**< unit up vector at the read, marker frame */
    gl_vec3_t gyro_bias;      /**< still-period gyro mean, rad/s */
    gl_vec2_t slope_raw;      /**< calibrated slope with the zeroing bias NOT removed */
    gl_vec2_t slope;          /**< slope used: bias removed (or the Precision combination) */
    float temp_c;
    bool precision;           /**< slope is the combination of two reads 180 degrees apart */
    float view_yaw_rad;
    bool flag_found;
    bool manual_range;        /**< the distance is the dialled one (flag-out fallback) */
    float bearing_rad;        /**< flagstick bearing from the left camera */
    float base_elev_rad, top_elev_rad;
    bool top_valid;
    uint8_t base;             /**< gl_vis_base_t */
    float disparity_px, disparity_sigma_px;
    bool range_valid;
    gl_range_result_t range;  /**< horizontal distance stereo head -> stick */
    gl_ball_target_t target;  /**< ball centre -> flagstick (bearing in the read frame) */
} gl_app_read_t;

/** Zeroing procedure (GL_UI_CAL_ZERO): read, turn 180 degrees, read. */
typedef struct {
    bool active;
    uint8_t step;             /**< 0 first read, 1 turning, 2 second read, 3 saved */
    bool averaging;           /**< the 1 s average of the current read is running */
    bool turned;              /**< the turn has gone far enough */
    gl_vec2_t m1;             /**< first slope reading (bias not removed) */
    gl_vec3_t up1;
    gl_rot_int_t rot;         /**< gyro integration from the end of read 1 */
    uint32_t saved_at_ms;
} gl_app_zero_t;

/** Six-face factory calibration (USB START_CAL): one still average per face. */
typedef struct {
    bool active;              /**< an average for face `face` is running */
    uint8_t face;
    uint8_t done_mask;        /**< faces captured so far */
    gl_vec3_t meas[6];
} gl_app_six_face_t;

typedef struct {
    /* ---- drivers ---- */
    gl_imu_t imu;
    gl_lcd_t lcd;
    gl_mx25r_t flash;
    gl_ov7692_t cam;
    gl_power_t power;
    gl_flash_if_t flash_if;
    gl_store_t store;
    gl_log_t log;
    bool imu_ok, flash_ok, storage_ok;
    /* ---- persistent data (RAM copies of the store) ---- */
    gl_settings_t settings;
    gl_cal_tilt_t cal_tilt;
    gl_cal_cam_t cal_cam[GL_CAM_COUNT];
    gl_cal_grain_t cal_grain;
    gl_stick_height_t stick_height;
    /* ---- UI ---- */
    gl_ui_t ui;
    gl_ui_view_t view;
    gl_gfx_t gfx;
    gl_event_queue_t events;
    bool redraw;
    /* ---- state of the device ---- */
    bool awake;               /**< display on, IMU measuring */
    bool usb_on;
    bool tilt_active;         /**< a 1 s tilt average is running */
    bool capture_active;
    bool batt_low_sent;
    uint32_t irq_mask;        /**< interrupt sources currently enabled */
    uint32_t last_sample_ms;
    uint32_t sleep_since_ms;  /**< when the device last went to sleep */
    uint32_t next_batt_ms;
    float temp_c;
    bool temp_valid;
    uint16_t last_error;      /**< gl_status_t of the last failed operation */
    uint32_t reads_total;
    uint16_t read_id;
    uint32_t loops;           /**< main loop iterations (diagnostics) */
    /* ---- reads ---- */
    gl_motion_t motion;
    gl_app_read_t cur;        /**< the read in progress / shown */
    gl_vec2_t spin_slope_raw; /**< slope reading before the Precision spin */
    gl_vec2_t reread_slope_raw;
    gl_survey_t survey;
    gl_measurements_t meas_cur;                  /**< solver input for the read shown */
    gl_measurements_t meas[GL_SOLVER_MAX_DROPS]; /**< solver input for each stored Survey drop */
    /* grain (experimental, off by default): newest optical reading of this read */
    bool grain_valid;
    float grain_modulation, grain_azimuth_rad;
    gl_estimate_t est;
    gl_status_t solver_status; /**< what the solver returned for the shown read */
    gl_app_zero_t zero;
    gl_app_six_face_t six;
    /* ---- USB ---- */
    gl_proto_t proto;
    gl_proto_ops_t ops;
    uint16_t stream_mask;
    uint16_t stream_period_ms;
    uint32_t stream_next_ms;
    uint32_t usb_last_rx_ms;
    gl_imu_raw_t last_raw;    /**< newest IMU sample (for the stream) */
    gl_log_iter_t log_iter;
    bool log_iter_valid;
    bool log_erasing;
    uint32_t log_erase_cursor;
    bool reboot_pending;
    uint8_t reboot_how;
    /* ---- the camera pipeline (large) ---- */
    gl_read_t read;
} gl_app_t;

/**
 * Bring the device up: HAL, drivers, storage (settings and calibration are
 * loaded, defaults where nothing is stored), UI in GL_UI_SLEEP, IMU in
 * wake-on-motion.  A missing IMU or flash does not stop the boot: the
 * fault is shown on the screen and logged if possible.  Returns the first
 * driver error, GL_OK if all devices answered.
 */
gl_status_t gl_app_init(gl_app_t *app);

/** One iteration of the main loop, INCLUDING the sleep at its end. */
void gl_app_run_once(gl_app_t *app);

/** Post a UI event from outside the loop (tests, future ISRs via a lock). */
void gl_app_post(gl_app_t *app, gl_ui_event_t ev, int32_t arg);

/* ---- used by app/gl_usb.c --------------------------------------------------- */

/** Bind the protocol callbacks (gl_usb.c). */
void gl_usb_bind(gl_app_t *app);
/** Move received USB bytes into the protocol, run streams, continue a log
 *  erase, perform a pending reboot. */
void gl_usb_service(gl_app_t *app, uint32_t now_ms);
/** Remember the newest IMU sample for the IMU stream. */
void gl_usb_stream_imu(gl_app_t *app, const gl_imu_raw_t *s);

/** Adopt new settings (from the dial or from USB): RAM, UI and store. */
gl_status_t gl_app_set_settings(gl_app_t *app, const gl_settings_t *s);
/** Store a blob; GL_ERR_NOT_FOUND if the flash is unusable. */
gl_status_t gl_app_store_put(gl_app_t *app, uint8_t id, const uint8_t *data, size_t len);
/** Append an event record to the log (ignored if the flash is unusable). */
void gl_app_log_event(gl_app_t *app, uint16_t code, int32_t arg);
/**
 * Start a factory calibration procedure (gl_proto_calproc_t).
 *   ZERO          GL_ERR_STATE: the zeroing is started from the settings
 *                 dial on a hard flat surface, never in the cradle
 *   SIX_FACE      arg 0..5: start a 1 s still average with that face up
 *                 (GL_ERR_BUSY while the previous face is still being
 *                 averaged); arg 6: solve and store (GL_ERR_STATE until all
 *                 six faces have been captured)
 *   GRAIN_WHITE   measure the white tile now and store the LED gains
 *   ABORT         stop a running face average
 *   GRAIN_FLOOR, CAM_HORIZON   GL_ERR_UNSUPPORTED in phase 1
 */
gl_status_t gl_app_start_cal(gl_app_t *app, uint8_t procedure, uint8_t arg);

#endif /* GL_APP_H */
