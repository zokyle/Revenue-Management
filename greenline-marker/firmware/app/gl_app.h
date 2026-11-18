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
 * What a result looks like (E33), the Survey that finishes at the ball
 * (E29), the recall of the last result by a tap (E30) and "TOO STEEP" (E31)
 * are described in core/gl_ui.h; the regulatory and information screen is
 * the INFO item of the settings dial (text: app/gl_regulatory.h).
 *
 * In the cradle (DESIGN_SPEC E32): awake with USB for as long as a host
 * talks; after 30 s without it the marker sleeps in Stop mode with a static
 * symbol on the display, USB in standby under a suspended host and off
 * otherwise, and wakes when the host resumes, when it is lifted out and
 * when the charger changes its status; the cell temperature and the charger
 * are still looked at every 5 s.  Ship mode (E13): gl_app_ship_mode_arm().
 *
 * Everything the firmware remembers lives in gl_app_t (static storage in
 * app/gl_main.c; the host tests allocate their own).  Nothing is allocated
 * dynamically.
 *
 * RAM: sizeof(gl_app_t) is about 323 kB, of which 301 kB are the image
 * buffers and vision work areas of gl_read_t (see gl_read.h).  The exact
 * figure is in the `make cross` size table (bss of gl_main) and in the
 * README, "Memory"; gl_app.c, gl_factory.c and gl_usb.c add 3.6 kB of
 * static scratch (one raw-strip log record, one field-log record, two raw
 * grain measurements, the factory commands' buffers).
 * Stack (arm-none-eabi-gcc -Os, -fstack-usage; the frames and the chains
 * are listed in the README, "Memory"): the deepest chain is the putt solve,
 * about 1.7 kB below main(); the vision's is about 1.4 kB; the logging, USB
 * and start-up chains stay below 1 kB.  With the HAL backend's frames and
 * nested interrupt frames on top, a 4 kB main stack leaves a factor of two.
 * No recursion anywhere.
 */
#ifndef GL_APP_H
#define GL_APP_H

#include "gl_app_cfg.h"
#include "gl_cal.h"
#include "gl_event.h"
#include "gl_factory.h"
#include "gl_fieldlog.h"
#include "gl_gfx.h"
#include "gl_log.h"
#include "gl_motion.h"
#include "gl_proto.h"
#include "gl_range.h"
#include "gl_read.h"
#include "gl_regulatory.h"
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
    bool flag_found;          /**< the left camera measured the flagstick (with or without
                                   a disparity) */
    bool bearing_valid;       /**< bearing_rad was measured in this read */
    bool stored;              /**< this read is the newest drop of the Survey */
    uint8_t tier;             /**< gl_read_tier_t of the camera read */
    bool ambiguous;           /**< another line in view also passed as a flagstick */
    float bearing_rad;        /**< flagstick bearing from the left camera */
    float base_elev_rad, top_elev_rad;
    bool top_valid;
    uint8_t base;             /**< gl_vis_base_t */
    float disparity_px, disparity_sigma_px;
    /* DIAGNOSTICS, not on the way to the aim: the application's own range
     * fusion (core/gl_range), which learns the stick height.  The distance
     * shown and solved with is gl_estimate_t.distance_m. */
    bool range_valid;
    gl_range_result_t range;  /**< horizontal distance stereo head -> stick */
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
    uint8_t seat;             /**< gl_cal_seat_t being zeroed: the ball seat from the menu (a
                                   hard flat surface), the armed seat from the factory */
    bool armed;               /**< started by the factory's armed zeroing */
    float scatter;            /**< worse block scatter of the reads so far */
} gl_app_zero_t;

/** Statistics of the 133 ms block slopes of one tilt average (the "tilt
 *  samples summary" of the field log). */
typedef struct {
    float sum_x, sum_y, sq_x, sq_y;
    uint16_t n;
} gl_app_tilt_stat_t;

/** Six-face factory calibration (USB START_CAL): one still average per face. */
typedef struct {
    bool active;              /**< an average for face `face` is running */
    uint8_t face;
    uint8_t done_mask;        /**< faces captured so far */
    gl_vec3_t meas[6];
} gl_app_six_face_t;

typedef struct gl_app {
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
    /* ---- IMU supervision (motion is the only user input) ---- */
    uint8_t imu_fails;        /**< failed recoveries in a row */
    bool imu_fault_shown;     /**< the failure of this episode has been reported */
    bool wdg_hold;            /**< stop refreshing the watchdog: force a reset */
    uint32_t imu_retry_ms;    /**< next recovery attempt (while awake) */
    uint32_t imu_backoff_ms;
    uint32_t imu_recoveries;  /**< successful recoveries since boot (diagnostics) */
    uint32_t imu_polls;       /**< samples fetched by polling: an interrupt latch was lost */
    /* ---- persistent data (RAM copies of the store) ---- */
    gl_settings_t settings;
    gl_cal_tilt_t cal_tilt;
    gl_cal_cam_t cal_cam[GL_CAM_COUNT];
    gl_cal_grain_t cal_grain;
    gl_cal_device_t cal_dev;  /**< display rotation (E12), serial number */
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
    float temp_c;             /**< IMU die temperature of the last GOOD read */
    bool temp_valid;          /**< that read was the most recent attempt and succeeded */
    uint32_t temp_ms;         /**< when it was taken */
    uint32_t mcu_temp_ms;     /**< when power.mcu_temp_c was taken */
    bool cell_seen;           /**< the cell temperature has been measured since boot */
    uint32_t cell_temp_ms;    /**< when power.cell_temp_c was taken */
    uint32_t next_chg_ms;     /**< next charge-temperature check while VBUS is present */
    bool clock_fast;          /**< the 160 MHz clock is on (capture and solve only) */
    uint16_t clock_fails;     /**< switches to the fast clock that failed (diagnostics) */
    bool vbus_acted;          /**< the VBUS level that has been dealt with (vbus_edge_): the
                                   pin is compared with it at every loop pass, so the edge
                                   interrupt is a convenience, not a necessity */
    bool vbus_pending;        /**< a VBUS edge is being debounced */
    uint32_t vbus_settle_ms;
    bool storage_mode;        /**< cell nearly empty: IMU off, only the cradle wakes the device */
    /* ---- rev E: cradle sleep (E32), ship mode and the read's temperature gate (E13) ---- */
    bool cradle_sleep;        /**< asleep IN the cradle: MCU in Stop mode, display on with the
                                   static symbol, IMU off, USB in standby or off */
    bool usb_standby;         /**< USB attached to a suspended bus, clocks stopped: the host's
                                   resume wakes the marker (GL_IRQ_USB_WAKE) */
    bool ship_armed;          /**< ship mode will be entered when the marker has left the cradle */
    bool ship_pending;        /**< ... it has: asleep with the IMU off, waiting out the bounce */
    uint32_t ship_due_ms;     /**< when ship mode is entered */
    bool halted;              /**< HOST BUILD ONLY: ship mode has been entered (the target does
                                   not return from gl_hal_ship_mode_enter); the main loop
                                   does nothing until gl_app_init() is called again */
    bool chg_odd;             /**< the charger's status is NOT_CHARGING or STOP_FAILED ... */
    uint32_t chg_odd_since_ms; /**< ... since then */
    bool chg_fault;           /**< ... for GL_APP_CHG_FAULT_AFTER_MS: shown and logged */
    uint8_t chg_shown;        /**< what the cradle screens last showed (redraw on a change) */
    uint8_t chg_status_logged; /**< gl_chg_status_t of the last GL_APP_LOGEV_CHARGER */
    bool ntc1_logged;         /**< the "charge outside the charger's own window" event is logged */
    uint16_t sleep_ticks;     /**< housekeeping wake-ups since the device went to sleep */
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
    gl_solver_work_t solver_work; /**< work area of the fit; .fit = fit record of `est` */
    gl_status_t solver_status; /**< what the solver returned for the shown read */
    gl_solver_options_t solve_opt; /**< the options of that call */
    uint8_t solve_drops;      /**< placements handed to it: meas_cur alone, or solve_meas[0..n-1] */
    uint8_t solve_ball;       /**< Survey: index, in solve_meas, of the placement at the ball
                                   (E29: the newest, handed over last) */
    bool solve_survey;        /**< the call was gl_solver_estimate_survey() on solve_meas */
    uint8_t solve_src[GL_SOLVER_MAX_DROPS]; /**< which stored placement each handed one is */
    gl_measurements_t solve_meas[GL_SOLVER_MAX_DROPS]; /**< Survey: the placements handed over -
                                   the stored ones that are not behind the ball (survey_select_) */
    bool line_here;           /**< always true since DESIGN_SPEC E29 (the placement the marker
                                   stands on IS the ball); kept because the log records it */
    float steep_ratio;        /**< gl_ui_steep_ratio() of the estimate shown (E31) */
    /* ---- Recall (E30): may the result be shown again after it went off the screen? ---- */
    uint32_t result_ms;       /**< when the result shown was made (gl_hal_tick_ms) */
    float recall_rest_x, recall_rest_y; /**< block-mean gravity direction the marker rested in
                                   when that result was made, g */
    gl_rot_int_t recall_rot;  /**< gyro integration while the result is on the screen, and
                                   from a wake-up until the marker is at rest */
    bool recall_spoiled;      /**< the marker was turned or tilted while the result was shown,
                                   or a Precision spin was given up: no recall */
    bool recall_checking;     /**< woken with a result that may be recalled: watching for a
                                   lift until the marker is at rest */
    uint8_t recall_moving;    /**< moving blocks since that wake-up */
    uint32_t recalls;         /**< results shown again since boot (diagnostics) */
    gl_app_zero_t zero;
    gl_app_six_face_t six;
    /* ---- phase 3: what the field log records about a read (core/gl_fieldlog) ---- */
    gl_app_tilt_stat_t tstat; /**< block slopes of the tilt average in progress */
    gl_vec3_t tilt_accel_g;   /**< uncalibrated mean of the last tilt average */
    float tilt_scatter;       /**< its block scatter (rise/run RMS) */
    float tilt_noise_g;
    uint8_t tilt_blocks;
    uint8_t seat_used;        /**< gl_cal_seat_t whose zero the current read removed */
    gl_vec2_t zero_used;
    bool tilt_logged;         /**< a tilt record has been written for the current placement */
    bool cameras_off;         /**< the current read was made in tilt-only mode */
    bool grain_ran;
    uint8_t grain_reject;
    float grain_nir_mod, grain_nir_az;
    uint16_t grain_signal[16];
    uint32_t still_ms;        /**< when the tilt average of the current read started */
    uint32_t cam_on_at_ms;
    bool cam_seen_on;         /**< the camera rail has been seen on in the current read */
    uint16_t stage_ms[GL_FIELDLOG_T_COUNT];
    uint16_t cam_on_ms;
    uint32_t log_seek_seq;    /**< GL_CMD_LOG_SEEK: records below this number are skipped */
    bool boot_confirmed;      /**< the boot stub has been told that this image runs (E34) */
    /* ---- phase 3: factory commands (app/gl_factory.c) ---- */
    gl_factory_t fac;
    /* ---- USB ---- */
    gl_proto_t proto;
    gl_proto_ops_t ops;
    uint16_t stream_mask;
    uint16_t stream_period_ms;
    uint32_t stream_next_ms;
    uint32_t usb_last_rx_ms;
    bool usb_activity;        /**< the host has sent bytes since the main loop last looked (E32:
                                   the cradle state lasts for as long as a host talks) */
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

/* ---- rev E: power interfaces (also behind GL_CMD_SHIP_MODE / GET_POWER / SET_CHARGE) -- */

/** Where the marker is as far as the cradle goes. */
typedef enum {
    GL_CRADLE_OUT = 0,   /**< no VBUS */
    GL_CRADLE_LINK,      /**< in the cradle, awake: USB started (or about to be) */
    GL_CRADLE_SLEEP      /**< in the cradle, asleep with the static symbol (E32) */
} gl_cradle_state_t;
gl_cradle_state_t gl_app_cradle_state(const gl_app_t *app);

/**
 * SHIP MODE (E13).  Arm: the next time the marker is lifted out of the
 * cradle it does not go to its ordinary sleep but, GL_APP_SHIP_SETTLE_MS
 * after VBUS has gone, into ship mode: display off, IMU and flash powered
 * down (no wake-on-motion), CHG_INHIBIT released, MCU in its lowest-power
 * state (gl_hal_ship_mode_enter).  Only VBUS brings it back, and that is a
 * reset: gl_app_init() runs, the boot event in the log carries
 * GL_RESET_SHIP_WAKE.  Armed is a state in RAM: a reset disarms.  Disarm:
 * false.  Returns the state afterwards.
 */
bool gl_app_ship_mode_arm(gl_app_t *app, bool arm);

/**
 * The cell temperature the firmware acts on: the MCU's thermistor (NTC2).
 * Returns true and writes *temp_c if the last measurement is valid and at
 * most GL_APP_CELL_TEMP_MAX_AGE_MS old (`now_ms` = gl_hal_tick_ms()).  The
 * fields behind it are app->power.cell_temp_c / cell_temp_valid / ntc_fault
 * and app->cell_temp_ms; the charger's status is app->power.chg_status
 * (gl_chg_status_t), the reason the firmware stops a charge
 * app->power.chg_reason (gl_chg_reason_t).  While VBUS is present they are
 * refreshed every GL_APP_CHG_TEMP_PERIOD_MS, out of the cradle with the
 * battery (GL_APP_BATT_PERIOD_MS, while awake) and before every camera read.
 */
bool gl_app_cell_temperature(const gl_app_t *app, uint32_t now_ms, float *temp_c);

/** Measure battery and temperatures now and apply the charge gate (what
 *  GL_CMD_GET_POWER does before it answers).  Not during a read. */
gl_status_t gl_app_power_refresh(gl_app_t *app);

/**
 * Compose the result view again from app->est and the current read, exactly
 * as after a solve (shown confidence, the message, solid or tentative line).
 * For the host tests: the mapping of estimates that no read sequence
 * produces (aim_source 3, a fit that did not converge, a poor horizon) is
 * checked by putting such an estimate into app->est and calling this.
 */
void gl_app_recompose_view(gl_app_t *app);

/* ---- phase 3: used by app/gl_factory.c ------------------------------------------ */
/** E13 for the factory's camera commands: measures the cell if the last
 *  reading is older than 5 s and applies the read gate (above 60 C: false,
 *  logged as GL_APP_LOGEV_TOO_HOT). */
bool gl_app_camera_allowed(gl_app_t *app);
/** The 160 MHz clock for a camera capture (and back). */
void gl_app_clock_fast(gl_app_t *app, bool fast);
/** Flags and CRC-16 of the five calibration records as they would be stored
 *  now (tilt, left camera, right camera, grain, device). */
void gl_app_cal_ids(const gl_app_t *app, uint8_t flags[5], uint16_t crc[5]);
/** Encode and store one calibration record from RAM (gl_cal_id_t). */
gl_status_t gl_app_cal_store(gl_app_t *app, uint8_t cal_id);
/** How long a boot must have run its main loop before the boot stub is told
 *  that this image works (gl_hal_boot_confirm, DESIGN_SPEC E34). */
#define GL_APP_BOOT_CONFIRM_MS 10000u

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
 *   GRAIN_FLOOR, CAM_HORIZON   GL_ERR_UNSUPPORTED: they are GL_CMD_SET_GRAIN_FLOOR and
 *                 GL_CMD_SET_CAM_HORIZON (the PC supplies the measurement)
 */
gl_status_t gl_app_start_cal(gl_app_t *app, uint8_t procedure, uint8_t arg);

#endif /* GL_APP_H */
