/*
 * gl_ui.h - user-interface state machine and screen composition.
 *
 * The device has no buttons.  Inputs are motion gestures (gl_gesture.h),
 * measurement results and power / USB events, all delivered as events to
 * gl_ui_dispatch().  The state machine is a plain TRANSITION TABLE
 * (state, event, guard) -> (next state, actions); the application carries
 * out the returned actions.  The module is pure: no HAL, no drawing side
 * effects outside the gl_gfx_t it is given.
 *
 * How the golfer drives it
 *   place the marker        -> wakes, waits for stillness, reads, shows the line
 *   pick up and re-place    -> new read
 *   double tap on a result  -> Precision Read prompt: spin the marker 180
 *                              degrees in place, it re-reads and combines
 *   double tap again        -> Survey: the shown read becomes drop 1; move
 *                              the marker along the line, each placement
 *                              adds a drop (up to 4); double tap ends it
 *   hold upright on edge    -> settings; roll like a knob to change the
 *                              value, double tap for the next item, lay
 *                              flat to confirm
 *   no flagstick found      -> flag-out fallback: asks for the distance
 *                              (dial); re-place the marker pointing at the
 *                              hole and it shows a tilt-only line along the
 *                              visor axis with low confidence.  The dialled
 *                              distance stays in the settings until changed
 *                              ("--" = none); the application uses it ONLY
 *                              when no flagstick is found.
 *   in the cradle           -> USB screen; flip calibration from there
 *
 * RAM: gl_ui_t 40 bytes.  Stack: gl_ui_render() about 250 bytes.
 */
#ifndef GL_UI_H
#define GL_UI_H

#include "gl_gfx.h"
#include "gl_settings.h"
#include "gl_types.h"

typedef enum {
    GL_UI_SLEEP = 0,
    GL_UI_WAKE,
    GL_UI_WAIT_STILL,
    GL_UI_READ_TILT,
    GL_UI_CAPTURE,
    GL_UI_SOLVE,
    GL_UI_SHOW_RESULT,
    GL_UI_PRECISION_WAIT_SPIN,
    GL_UI_SURVEY_NEXT_DROP,
    GL_UI_SETTINGS_DIAL,
    GL_UI_CRADLE_USB,
    GL_UI_CAL_FLIP,
    GL_UI_ERROR,
    GL_UI_LOW_BATT,
    GL_UI_STATE_COUNT
} gl_ui_state_t;

/** Wildcard for the `state` column of the transition table. */
#define GL_UI_ANY 0xFFu

typedef enum {
    GL_EV_NONE = 0,
    GL_EV_MOTION,            /**< the marker was moved: wake-on-motion while asleep; while
                                  awake only SUSTAINED movement (about 0.4 s without
                                  stillness, or a change of posture) - a tap is not motion */
    GL_EV_STILL,             /**< flat on its base and still for 0.5 s */
    GL_EV_TILT_DONE,
    GL_EV_TILT_FAIL,         /**< moved during the average, or not lying on a green */
    GL_EV_CAPTURE_DONE,      /**< flagstick measured */
    GL_EV_CAPTURE_NO_STICK,  /**< no flagstick in view */
    GL_EV_CAPTURE_FAIL,      /**< camera or bus error */
    GL_EV_SOLVE_DONE,        /**< a result is ready to show (possibly tilt-only) */
    GL_EV_SOLVE_FAIL,
    GL_EV_DOUBLE_TAP,
    GL_EV_SPIN_DONE,         /**< a half turn about the vertical, and still again */
    GL_EV_UPRIGHT,           /**< held upright on edge */
    GL_EV_FLAT,              /**< laid flat on its base again */
    GL_EV_DIAL_STEP,         /**< arg = new dial value */
    GL_EV_USB_ATTACH,        /**< VBUS present */
    GL_EV_USB_DETACH,
    GL_EV_BATT_LOW,
    GL_EV_CAL_START,         /**< flip calibration requested (USB command) */
    GL_EV_CAL_DONE,
    GL_EV_CAL_FAIL,
    GL_EV_FAULT,             /**< arg = gl_status_t */
    GL_EV_TIMEOUT,           /**< produced by gl_ui_tick() */
    GL_EV_COUNT
} gl_ui_event_t;

/** Actions for the application (bit mask returned by dispatch / tick). */
#define GL_ACT_DISPLAY_ON       (1u << 0)  /**< power the display, start EXTCOMIN */
#define GL_ACT_ENTER_SLEEP      (1u << 1)  /**< display off, IMU to wake-on-motion, Stop mode */
#define GL_ACT_WATCH_STILL      (1u << 2)  /**< run the stillness detector, post GL_EV_STILL */
#define GL_ACT_START_TILT       (1u << 3)  /**< start the 1 s tilt average */
#define GL_ACT_START_CAPTURE    (1u << 4)  /**< camera rail on, capture and analyse */
#define GL_ACT_START_SOLVE      (1u << 5)
#define GL_ACT_ABORT_READ       (1u << 6)  /**< stop tilt / capture; camera rail OFF */
#define GL_ACT_ARM_SPIN         (1u << 7)  /**< start integrating the gyro for the 180-degree spin */
#define GL_ACT_PRECISION        (1u << 8)  /**< the tilt read just done is the re-read: combine */
#define GL_ACT_SURVEY_STORE     (1u << 9)  /**< append the current read to the survey */
#define GL_ACT_SURVEY_RESET     (1u << 10)
#define GL_ACT_DIAL_BEGIN       (1u << 11) /**< start the dial for ui->item at ui->dial_value */
#define GL_ACT_SAVE_SETTINGS    (1u << 12) /**< adopt and store ui->edit */
#define GL_ACT_USB_START        (1u << 13)
#define GL_ACT_USB_STOP         (1u << 14)
#define GL_ACT_CAL_FLIP_START   (1u << 15)
#define GL_ACT_CAL_ABORT        (1u << 16)
#define GL_ACT_REDRAW           (1u << 17) /**< the screen content changed */
#define GL_ACT_NEW_READ         (1u << 18) /**< forget the previous result (new placement) */

/** Guards of the transition table. */
typedef enum {
    GL_G_ALWAYS = 0,
    GL_G_PRECISION_REREAD,   /**< the read in progress is the re-read after the spin */
    GL_G_SURVEY_ACTIVE,      /**< a survey is in progress */
    GL_G_SURVEY_ROOM,        /**< survey active and fewer than 4 drops stored */
    GL_G_SURVEY_FULL,        /**< survey active with 4 drops */
    GL_G_HAS_MANUAL_DIST,    /**< settings hold a manual distance */
    GL_G_MOVED,              /**< motion was seen since the state was entered */
    GL_G_USB,                /**< VBUS present */
    GL_G_ITEM_FLIP_CAL_YES   /**< dial is on the "FLIP CAL" item with value YES */
} gl_ui_guard_t;

typedef struct {
    uint8_t state;    /**< gl_ui_state_t or GL_UI_ANY */
    uint8_t event;    /**< gl_ui_event_t */
    uint8_t guard;    /**< gl_ui_guard_t */
    uint8_t next;     /**< gl_ui_state_t */
    uint32_t actions; /**< GL_ACT_* */
} gl_ui_transition_t;

/** The dial item after the settings items: "FLIP CAL" (NO / YES). */
#define GL_UI_ITEM_FLIP_CAL ((uint8_t)GL_ITEM_COUNT)
#define GL_UI_ITEM_COUNT ((uint8_t)GL_ITEM_COUNT + 1u)

typedef enum {
    GL_READ_QUICK = 0,       /**< tilt + capture */
    GL_READ_PRECISION = 1,   /**< tilt only, combined with the previous read */
    GL_READ_SURVEY = 2       /**< tilt + capture, stored as a survey drop */
} gl_ui_read_kind_t;

typedef struct {
    uint8_t state;           /**< gl_ui_state_t */
    uint8_t read_kind;       /**< gl_ui_read_kind_t of the read in progress / shown */
    uint8_t survey_count;    /**< drops stored so far (0 = no survey) */
    uint8_t item;            /**< dial item: gl_item_t or GL_UI_ITEM_FLIP_CAL */
    bool moved;
    bool usb;
    bool dist_prompt;        /**< the dial was opened to ask for the distance */
    uint16_t error_code;     /**< gl_status_t shown in GL_UI_ERROR */
    int32_t dial_value;
    uint32_t state_since_ms;
    uint32_t transitions;    /**< count, for diagnostics */
    gl_settings_t edit;      /**< settings working copy (live copy + edits in the dial) */
    gl_settings_t saved;     /**< last confirmed settings; restored if a dial is abandoned */
} gl_ui_t;

/** Start in GL_UI_SLEEP with a copy of the current settings. */
void gl_ui_init(gl_ui_t *ui, const gl_settings_t *settings, uint32_t now_ms);

/**
 * Feed one event.  Looks up the first table row matching the current state
 * (rows for the state itself before wildcard rows), event and guard;
 * applies it; returns the row's actions.  Events with no matching row are
 * ignored (returns 0, state unchanged).
 */
uint32_t gl_ui_dispatch(gl_ui_t *ui, gl_ui_event_t ev, int32_t arg, uint32_t now_ms);

/** Call periodically (and after wake-up): raises GL_EV_TIMEOUT when the
 *  current state has been held longer than its limit.  Wrap-safe. */
uint32_t gl_ui_tick(gl_ui_t *ui, uint32_t now_ms);

/** Time limit of a state in ms; 0 = none. */
uint32_t gl_ui_timeout_ms(gl_ui_state_t state);

/** Milliseconds until the current state times out (0 = no timeout or due
 *  now): how long the main loop may sleep. */
uint32_t gl_ui_time_left_ms(const gl_ui_t *ui, uint32_t now_ms);

/** The transition table, for inspection and tests. */
const gl_ui_transition_t *gl_ui_table(size_t *rows);

/** Constant names for logs and tests ("SHOW_RESULT", "DOUBLE_TAP", ...);
 *  "?" for an out-of-range value. */
const char *gl_ui_state_name(gl_ui_state_t state);
const char *gl_ui_event_name(gl_ui_event_t ev);

/* ---- screens ------------------------------------------------------------------ */

/** Everything the screens show that the state machine does not own. */
typedef struct {
    /* result of the last read (GL_UI_SHOW_RESULT) */
    bool have_result;
    bool solved;             /**< false: no putt solution (phase-1 stub, or flag-out): tilt-only */
    bool flag_found;
    bool precision;          /**< result of a spin-and-reread */
    float aim_rad;           /**< aim line direction in the marker frame, CCW from forward */
    float distance_m;        /**< to the hole; <= 0 = unknown */
    float slope_pct;         /**< slope magnitude at the ball */
    float fall_line_rad;     /**< downhill direction, marker frame, CCW from forward */
    float along_pct;         /**< slope along the line to the hole, + = uphill */
    float break_cups;        /**< + = aim left of the hole */
    float confidence;        /**< 0..1 */
    /* status */
    uint8_t battery_pct;
    bool charging;
    bool usb_connected;      /**< host has opened the port */
    uint8_t cal_step;        /**< flip calibration: 0 hold still, 1 turn 180, 2 hold still, 3 saved */
} gl_ui_view_t;

/**
 * Draw the screen of the current state into `g` (cleared first).  All ink
 * stays inside the round aperture (the gfx clip is enabled by this call).
 */
void gl_ui_render(const gl_ui_t *ui, const gl_ui_view_t *view, gl_gfx_t *g);

#endif /* GL_UI_H */
