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
 *                              adds a drop (up to 4); double tap ends it.
 *                              The putt is the one from the drop FARTHEST
 *                              from the flagstick (the ball).  The aim line
 *                              is drawn only while the marker lies there
 *                              (start at the ball, or come back to it for
 *                              the last drop); at any other drop the screen
 *                              shows the numbers and "PUT AT BALL".
 *   what a result shows     -> distance, "PLAYS" distance, slope with the
 *                              fall-line arrow, break in cups with the side,
 *                              confidence boxes, and ONE plain message when
 *                              something is not as usual (gl_ui_note_t).  An
 *                              aim that is not a solution of the putt is
 *                              drawn DASHED with "BREAK ?", never as a
 *                              normal line.
 *   hold upright on edge    -> settings; roll like a knob to change the
 *                              value, double tap for the next item, lay
 *                              flat to confirm
 *   no flagstick found      -> flag-out fallback: asks for the distance
 *                              (dial); re-place the marker pointing at the
 *                              hole and it shows a tilt-only line along the
 *                              visor axis with low confidence.  The dialled
 *                              distance stays in the settings until changed
 *                              ("--" = none); it is used ONLY when the
 *                              cameras give no range (no flagstick, or a
 *                              flagstick that could not be ranged) and is
 *                              then shown with a question mark.
 *   in the cradle           -> USB screen (charging, data).  The cradle
 *                              takes the marker one way round only and
 *                              holds it down; nothing is calibrated there.
 *   zeroing                 -> dial item "ZERO" = YES, then lay the marker
 *                              on any HARD FLAT surface (a table, not turf):
 *                              it reads, asks for a 180-degree turn in
 *                              place, reads again and stores the device
 *                              bias; the reversal cancels the surface's own
 *                              tilt, so the surface need not be level.
 *                              Putting the marker in the cradle abandons it.
 *
 * RAM: gl_ui_t 44 bytes, gl_ui_view_t 48 bytes.  Stack: gl_ui_render() about 250 bytes.
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
    GL_UI_CAL_ZERO,          /**< user zeroing on a hard flat surface (rev B called this CAL_FLIP
                                  and ran it in the cradle; rev C: never in the cradle) */
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
    GL_EV_CAL_DONE,          /**< zeroing finished and stored */
    GL_EV_CAL_FAIL,          /**< arg = gl_status_t (moved, turn not near 180 degrees, ...) */
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
#define GL_ACT_CAL_ZERO_START   (1u << 15) /**< begin the zeroing procedure (read, turn 180, read) */
#define GL_ACT_CAL_ABORT        (1u << 16)
#define GL_ACT_REDRAW           (1u << 17) /**< the screen content changed */
#define GL_ACT_NEW_READ         (1u << 18) /**< forget the previous result (new placement) */
#define GL_ACT_SPIN_ABANDON     (1u << 19) /**< the Precision spin was given up: stop integrating,
                                                show the single read for where the marker faces now */

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
    GL_G_ITEM_ZERO_YES       /**< dial is on the "ZERO" item with value YES */
} gl_ui_guard_t;

typedef struct {
    uint8_t state;    /**< gl_ui_state_t or GL_UI_ANY */
    uint8_t event;    /**< gl_ui_event_t */
    uint8_t guard;    /**< gl_ui_guard_t */
    uint8_t next;     /**< gl_ui_state_t */
    uint32_t actions; /**< GL_ACT_* */
} gl_ui_transition_t;

/** The dial item after the settings items: "ZERO" (NO / YES), which starts
 *  the zeroing routine when the marker is then laid flat. */
#define GL_UI_ITEM_ZERO ((uint8_t)GL_ITEM_COUNT)
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
    uint8_t item;            /**< dial item: gl_item_t or GL_UI_ITEM_ZERO */
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

/**
 * Progress report from the application: the activity of the current state
 * is alive and legitimately takes longer than the state's time limit (used
 * while raw strips are written to the log during a capture: field data
 * collection).  Restarts the time limit of the current state; no transition,
 * no actions.  Each strip capture keeps its own time-out in the driver, so
 * a hung camera is still caught.
 */
void gl_ui_keepalive(gl_ui_t *ui, uint32_t now_ms);

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

/**
 * The ONE plain message a result may carry.  The application picks the most
 * serious condition that applies (the order of this enum, highest first):
 * a fallback or a weak read must be visible to the golfer as a message and
 * as reduced confidence, never only as a normal-looking line.
 */
typedef enum {
    GL_UI_NOTE_NONE = 0,
    GL_UI_NOTE_AMBIGUOUS,    /**< "2 LINES SEEN": another line also passed as a flagstick */
    GL_UI_NOTE_ONE_CAMERA,   /**< "1 CAMERA": left camera only, not checked against a disparity */
    GL_UI_NOTE_FIT,          /**< "FIT NOT DONE": the fit stopped on its iteration limit */
    GL_UI_NOTE_PACE,         /**< "PACE LIMIT": through the hole, but cannot arrive as slowly as set */
    GL_UI_NOTE_APPROX,       /**< "APPROX": solved on the secant plane of the fitted patch */
    GL_UI_NOTE_NO_RANGE,     /**< "NO RANGE": flag found, distance dialled or assumed */
    GL_UI_NOTE_NO_FLAG,      /**< "NO FLAG": tilt only, along the visor axis */
    GL_UI_NOTE_NOT_SOLVED,   /**< "NOT SOLVED": the estimator's best effort, not a solution */
    GL_UI_NOTE_NO_SOLUTION,  /**< "NO SOLUTION": straight at the hole for want of anything */
    GL_UI_NOTE_COUNT
} gl_ui_note_t;

/** The text of a note ("" for GL_UI_NOTE_NONE and out-of-range values). */
const char *gl_ui_note_text(gl_ui_note_t note);

/** Everything the screens show that the state machine does not own. */
typedef struct {
    /* result of the last read (GL_UI_SHOW_RESULT) */
    bool have_result;
    bool solved;             /**< true: the aim is a solution of the putt on the estimated
                                  surface (solid line).  false: best effort or straight (the
                                  line is drawn in dashes, the break is not quoted) */
    bool line_here;          /**< true: the marker lies at the ball, the aim line applies to
                                  where it lies.  false (a Survey drop along the line): no
                                  line is drawn, the numbers are shown with "PUT AT BALL" */
    bool flag_found;
    bool precision;          /**< result of a spin-and-reread */
    bool distance_assumed;   /**< the distance is the dialled or the default one (shown "?") */
    uint8_t note;            /**< gl_ui_note_t */
    uint8_t drop;            /**< Survey: number of the drop this result was taken at (1..4);
                                  0 = not a Survey */
    float aim_rad;           /**< aim line direction in the marker's CURRENT frame, CCW from forward */
    float ball_az_rad;       /**< direction from the marker centre to the ball centre, CCW from
                                  forward: 0 normally; near pi after the 180-degree spin of a
                                  Precision Read (the marker then faces away from the hole) */
    float distance_m;        /**< to the hole; <= 0 = unknown */
    float plays_like_m;      /**< flat-green distance with the same launch speed; <= 0 = none */
    float slope_pct;         /**< slope magnitude at the ball */
    float fall_line_rad;     /**< downhill direction, marker frame, CCW from forward */
    float break_cups;        /**< + = aim left of the hole */
    float confidence;        /**< 0..1, as shown (after the application's own reductions) */
    /* status */
    uint8_t battery_pct;
    bool charging;
    bool usb_connected;      /**< host has opened the port */
    uint8_t chg_blocked;     /**< cradle: 0 = the charger may run; 1 too cold, 2 too hot,
                                  3 temperature sensor (unknown, faulty or implausible) */
    uint8_t cal_step;        /**< zeroing: 0 hold still (first read), 1 turn 180 degrees in
                                  place, 2 hold still (second read), 3 saved */
} gl_ui_view_t;

/** The strings of the result screen, as drawn ("" = not drawn). */
typedef struct {
    char distance[12];       /**< "19.6FT", "6.0M?", "--" */
    char plays[16];          /**< "PLAYS 21.3FT" */
    char note[16];           /**< gl_ui_note_text(), or the Survey prompt */
    char slope[8];           /**< "2.3%" */
    char brk[12];            /**< "<2.5 CUP", "2.5 CUP>", "STRAIGHT", "BREAK ?" */
    char mode[4];            /**< "D2", "2X" */
} gl_ui_result_text_t;

/** Format the strings of the result screen (pure; gl_ui_render() draws
 *  exactly these, and the tests read the numbers shown from here). */
void gl_ui_result_text(const gl_ui_t *ui, const gl_ui_view_t *view, gl_ui_result_text_t *out);

/** Boxes of the confidence bar that are filled (0..5) for a confidence. */
int gl_ui_conf_boxes(float confidence);

/**
 * Draw the screen of the current state into `g` (cleared first).  All ink
 * stays inside the round aperture (the gfx clip is enabled by this call).
 */
void gl_ui_render(const gl_ui_t *ui, const gl_ui_view_t *view, gl_gfx_t *g);

#endif /* GL_UI_H */
