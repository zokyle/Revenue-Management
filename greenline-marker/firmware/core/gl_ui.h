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
 *                              degrees in place, it re-reads and combines.
 *                              ONCE per placement: the result is then drawn
 *                              turned round, upright for the golfer behind
 *                              the ball (the marker faces away from the
 *                              hole).  Turning the marker back by hand is a
 *                              new placement: a new Quick Read.
 *   double tap again        -> Survey (on the spin prompt, or on a Precision
 *                              result): the shown read becomes drop 1; move
 *                              the marker along the line, each placement
 *                              adds a drop (2 to 4 in all); double tap ends
 *                              it.  DESIGN_SPEC E29: THE SURVEY FINISHES AT
 *                              THE BALL.  The placement the marker stands on
 *                              is always taken as the ball: every result,
 *                              from the second placement on, is the putt
 *                              from where the marker lies, with its line,
 *                              fitted to all placements so far (for example
 *                              1 m short of the hole, the midpoint, then the
 *                              ball).  A fifth placement is a new plain
 *                              read; picking the marker up without putting
 *                              it down again for 60 s, or leaving a result
 *                              for its 45 s, ends the Survey (the last
 *                              result can still be recalled, see below).
 *   single tap, later       -> Recall (E30): a marker that has NOT BEEN
 *                              LIFTED since its last result went off the
 *                              screen shows that result again for 45 s with
 *                              its age ("3M AGO") when it is tapped; no
 *                              camera read, nothing is logged.  The tap is
 *                              what wakes the marker (wake-on-motion).  "Not
 *                              lifted" is decided from the motion data: see
 *                              gl_app.c, recall_watch_.
 *   what a result shows     -> distance, "PLAYS" distance (the flat putt
 *                              that needs the same stroke; "?" if the hole
 *                              height is only bounded), slope with the
 *                              fall-line arrow, break in cups with the side,
 *                              confidence boxes, and ONE plain message when
 *                              something is not as usual (gl_ui_note_t).
 *                              THREE DISPLAY STATES (E33, gl_ui_show_t):
 *                              a SOLID line with the confidence bar = a
 *                              normal solution; a DASHED line with the word
 *                              APPROX where the bar would be = a fallback
 *                              solution (the message says which: TOO STEEP,
 *                              NO FLAG, NO RANGE, PACE LIMIT, ...); a
 *                              MESSAGE WITHOUT A LINE = no solution.  An
 *                              aim more than 13.5 degrees off the marker's
 *                              axis is drawn parallel through the screen
 *                              centre, in the same style.
 *   too steep               -> E31: where the fitted slope at the ball or at
 *                              the hole is GL_UI_STEEP_RATIO of the slope a
 *                              ball no longer stops on, or more, the result
 *                              says "TOO STEEP" and its line is dashed.
 *   hold upright on edge    -> settings; roll like a knob to change the
 *                              value, double tap for the next item, lay
 *                              flat to confirm.  The last item, INFO, is the
 *                              regulatory and information screen: model,
 *                              "PRACTICE DEVICE", versions, serial number,
 *                              and (rolled on) the pages of the regulatory
 *                              text.
 *   no flagstick found      -> asks for the distance ("NO FLAG", the DIST
 *                              dial).  Putting the marker down again WITHOUT
 *                              dialling reads again (the flagstick may be in
 *                              view now).  With a distance dialled it is the
 *                              flag-out fallback: point the visor at the
 *                              hole; a tilt-only line along the visor axis,
 *                              DASHED, with an empty confidence bar - its
 *                              direction is the golfer's pointing.  The
 *                              dialled distance belongs to ONE hole: it is
 *                              used only when the cameras give no range, is
 *                              shown with a question mark, and is forgotten
 *                              when a read ranges a flagstick and when the
 *                              marker goes to sleep.
 *   in the cradle           -> USB screen (charging, data) for as long as a
 *                              host talks to the marker.  After 30 s without
 *                              a word from a host - or with none there, on a
 *                              wall charger - the marker goes to sleep with
 *                              a STATIC symbol on the display: a battery
 *                              with a bolt (charging), with a tick ("FULL"),
 *                              or the reason why the charge is stopped
 *                              (DESIGN_SPEC E32: an awake marker draws more
 *                              than the charger's termination current, so a
 *                              charge would never end).  It wakes when the
 *                              host resumes the bus and when it is lifted
 *                              out.  The cradle takes the marker one way
 *                              round only and holds it down; nothing is
 *                              calibrated there.
 *   too hot                 -> no camera read is started from a cell above
 *                              60 C (E13): "TOO HOT" for 4 s, then sleep.
 *   zeroing                 -> dial item "ZERO" = YES, then lay the marker
 *                              on any HARD FLAT surface (a table, not turf):
 *                              it reads, asks for a 180-degree turn in
 *                              place, reads again and stores the device
 *                              bias; the reversal cancels the surface's own
 *                              tilt, so the surface need not be level.
 *                              Putting the marker in the cradle abandons it.
 *
 * RAM and stack: README, "Memory" (the sizes are printed by tests/test_ui.c).
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
    /* rev E (values are reported to the host and logged: append only) */
    GL_UI_TOO_HOT,           /**< E13: the cell is above 60 C, no camera read; shown 4 s */
    GL_UI_CRADLE_SLEEP,      /**< E32: in the cradle, no host talking: MCU asleep, a static
                                  charging / full / stopped symbol on the display */
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
    /* rev E, appended */
    GL_EV_TOO_HOT,           /**< a camera read was about to start with the cell above 60 C */
    GL_EV_USB_RESUME,        /**< asleep in the cradle: the host has resumed the bus */
    /* phase 3, appended */
    GL_EV_CAPTURE_SKIPPED,   /**< tilt-only mode (TILT LOG = ONLY): the cameras stay off and
                                  the placement is solved as a flag-out read */
    GL_EV_CAL_ARMED,         /**< a zeroing was armed by the factory (GL_CMD_LEVEL_ZERO) and
                                  the marker now lies out of the cradle: run it */
    GL_EV_FORCE_SLEEP,       /**< go to sleep now (the sleep-current test, GL_CMD_SLEEP_TEST) */
    GL_EV_LIFTED,            /**< E30: the marker has been lifted, turned or tilted since its
                                  last result (the application's recall watch): that result
                                  must not be shown again; a new read follows */
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
#define GL_ACT_CRADLE_SLEEP     (1u << 20) /**< E32: USB to standby or off, IMU and flash down, MCU
                                                to Stop mode; the display STAYS ON with the symbol */
#define GL_ACT_RECALL           (1u << 21) /**< E30: show the stored result again with its age; no
                                                read, no camera, no log record */

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
    GL_G_ITEM_ZERO_YES,      /**< dial is on the "ZERO" item with value YES */
    GL_G_DIST_PROMPT,        /**< the dial was opened to ask for the distance (no flagstick seen) */
    GL_G_DIST_PROMPT_MOVED,  /**< ... and the marker has been picked up since */
    GL_G_RECALL              /**< E30: a result is stored and the marker has not been lifted
                                  since it went off the screen (gl_ui_t.recall) */
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
/** ... and the last one: "INFO", the regulatory and information screen.
 *  Rolling turns its pages (page 0: model, versions, serial; then the text
 *  block).  It sets nothing; laying the marker flat leaves the dial as from
 *  any other item. */
#define GL_UI_ITEM_INFO ((uint8_t)GL_ITEM_COUNT + 1u)
#define GL_UI_ITEM_COUNT ((uint8_t)GL_ITEM_COUNT + 2u)

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
    bool recall;             /**< E30: the last result went off the screen by its time limit
                                  and nothing has happened since that makes it untrue: a wake
                                  by motion that ends at rest shows it again (GL_G_RECALL).
                                  Owned by gl_ui_dispatch(); cleared by GL_EV_LIFTED and by
                                  every transition that is not on the way to the recall */
    uint8_t info_pages;      /**< pages of the INFO item (set by the application before the
                                  dial is used; 0 is taken as 1) */
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
    GL_UI_NOTE_HORIZON,      /**< "POOR HORIZON": method B2, the turf horizon did not fit the patch */
    GL_UI_NOTE_FIT,          /**< "FIT NOT DONE": the fit stopped on its iteration limit */
    GL_UI_NOTE_PACE,         /**< "PACE LIMIT": through the hole, but cannot arrive as slowly as set */
    GL_UI_NOTE_APPROX,       /**< "APPROX": solved on the secant plane of the fitted patch */
    GL_UI_NOTE_NO_RANGE,     /**< "NO RANGE": flag found, distance dialled or assumed */
    GL_UI_NOTE_NO_FLAG,      /**< "NO FLAG": tilt only, along the visor axis */
    GL_UI_NOTE_NOT_SOLVED,   /**< "NOT SOLVED": the estimator's best effort, not a solution */
    GL_UI_NOTE_NO_SOLUTION,  /**< "NO SOLUTION": straight at the hole for want of anything */
    /* phase 3 (the value is logged: appended, whatever its rank) */
    GL_UI_NOTE_TOO_STEEP,    /**< "TOO STEEP" (E31): the fitted slope is close to the slope a
                                  ball no longer stops on; the solution is not determined */
    GL_UI_NOTE_COUNT
} gl_ui_note_t;

/* ---- the three display states of a result (DESIGN_SPEC E33) --------------------- */

/** What a result looks like.  Exactly one of these applies to every estimate
 *  (gl_ui_classify); tests/test_ui.c proves it over every aim source and
 *  solve status, and that the three differ in the frame buffer. */
typedef enum {
    GL_UI_SHOW_NORMAL = 0,   /**< SOLID aim line and the confidence bar: a solution of the
                                  putt on the fitted patch, at the pace set, of a putt whose
                                  distance and direction the cameras measured */
    GL_UI_SHOW_APPROX = 1,   /**< DASHED aim line, the word "APPROX" in place of the confidence
                                  bar, and the reason as the message: a fallback solution */
    GL_UI_SHOW_NONE = 2,     /**< the message, NO line, no bar, no break: no solution */
    GL_UI_SHOW_COUNT
} gl_ui_show_t;

/**
 * E31: at and above this ratio of the fitted slope to the critical slope
 * (gl_ui_steep_ratio) a solved result is shown as "TOO STEEP", dashed.
 * Chosen from a sweep against the Python reference (tools/steep_sweep.py,
 * `make steep-sweep`; the table is in the README, "TOO STEEP"): with a
 * one-microradian change of the tilt the aim flipped in none of 11185
 * reference reads (and none of 56191 firmware reads) with a ratio below
 * 0.90, in 0.1 % (0.4 %) at 0.90 to 0.95, 2 % (3 %) at 0.95 to 1.00 and a
 * quarter to a half above 1.05.  0.80 leaves a margin of 0.10 below the
 * first flip for the error of the fitted slope itself (the tilt reading: 2
 * mrad on a critical slope of 56 to 131 mrad for green speeds 14 to 6).
 */
#define GL_UI_STEEP_RATIO 0.80f

/** Standard gravity and the rolling factor of the reference (physics.py:
 *  G, ROLL_FACTOR): the critical slope is a_r / ((5/7) g). */
#define GL_UI_G_MPS2 9.80665f
#define GL_UI_ROLL_FACTOR (5.0f / 7.0f)

/**
 * The steepness ratio of an estimate, from quantities the estimator
 * returns (gl_estimate_t.patch[0..3], distance_m, a_r_mps2):
 *
 *     max(|(a, b)|, |(a + c D, b + d D)|) / (a_r / ((5/7) g))
 *
 * - the slope of the fitted patch at the ball and at the hole (it is linear
 * along the straight line between them, so its largest magnitude on that
 * line is at one of its ends) over the slope on which a ball no longer
 * stops.  Returns +infinity if a_r is not positive, or if anything is not
 * a number (such a result is then TOO STEEP, never normal).
 */
float gl_ui_steep_ratio(float a, float b, float c, float d, float distance_m, float a_r_mps2);

/** What gl_ui_classify() looks at. */
typedef struct {
    uint8_t aim_source;      /**< gl_aim_source_t */
    uint8_t solve_status;    /**< gl_solve_status_t */
    bool flag_missing, range_missing, fit_converged, poor_horizon; /**< of gl_estimate_t */
    bool distance_known;     /**< the distance was measured by the cameras, or dialled */
    float steep_ratio;       /**< gl_ui_steep_ratio() */
    bool one_camera;         /**< the flagstick was measured by the left camera only */
    bool ambiguous;          /**< another line also passed as a flagstick */
} gl_ui_class_in_t;

/**
 * The display state of an estimate and its ONE message.  First match wins:
 *
 *   NONE    aim source 3 (straight) or unknown, or solve status INVALID /
 *           NOT_RUN / unknown: "NO SOLUTION"
 *   NONE    aim source 2 (best effort): "TOO STEEP" if the ratio says so,
 *           else "NOT SOLVED"
 *   APPROX  flag missing: "NO FLAG";  range missing: "NO RANGE";  (any
 *           other result whose distance is not known: "NO RANGE")
 *   APPROX  ratio >= GL_UI_STEEP_RATIO: "TOO STEEP"
 *   APPROX  aim source 1 (secant plane): "APPROX"
 *   APPROX  aim source 0, status PACE_LIMITED: "PACE LIMIT"
 *   APPROX  aim source 0, any status but OK (a kept near miss): "APPROX"
 *   APPROX  fit not converged: "FIT NOT DONE";  poor horizon: "POOR HORIZON"
 *   NORMAL  everything else (aim source 0, status OK): "1 CAMERA",
 *           "2 LINES SEEN" or no message
 *
 * PACE_LIMITED and the kept near miss are the SAME state on purpose: on a
 * knife-edge putt the single- and the double-precision build end in the one
 * or the other (reference vectors, near-miss ids 1, 3, 4, 9, 16).
 */
gl_ui_show_t gl_ui_classify(const gl_ui_class_in_t *in, gl_ui_note_t *note);

/** The text of a note ("" for GL_UI_NOTE_NONE and out-of-range values). */
const char *gl_ui_note_text(gl_ui_note_t note);

/** Everything the screens show that the state machine does not own. */
typedef struct {
    /* result of the last read (GL_UI_SHOW_RESULT) */
    bool have_result;
    bool solved;             /**< true: the aim is a solution of the putt on the estimated
                                  surface (patch or secant plane).  false: best effort or
                                  straight: NO line, the break is not quoted */
    uint8_t show;            /**< gl_ui_show_t as classified (gl_ui_classify).  The renderer
                                  draws gl_ui_view_show(), which can only be MORE cautious */
    bool recalled;           /**< E30: this is the stored result shown again ... */
    uint32_t age_s;          /**< ... this many seconds after it was made */
    bool flag_found;
    bool precision;          /**< result of a spin-and-reread */
    bool distance_assumed;   /**< the distance is the dialled or the default one (shown "?") */
    bool plays_uncertain;    /**< the base of the stick was hidden: the hole height is only
                                  bounded, the plays-like distance is shown with a "?" */
    uint8_t note;            /**< gl_ui_note_t */
    uint8_t drop;            /**< Survey: number of the drop this result was taken at (1..4);
                                  0 = not a Survey */
    bool zero_missing;       /**< E11: the level zero of the seat this read was made on (the
                                  SURFACE setting) is NOT stored - the other seat's zero, or
                                  none, was removed.  A unit without it reads the 1.6 mrad
                                  between the two seats as slope: 10.9 mrad of aim at 4 m.
                                  Shown as "Z?" at the lower left of every result */
    uint8_t drops_used;      /**< Survey: how many placements the result is MADE OF (the
                                  estimator cannot use one that lies behind the present ball);
                                  0 or equal to `drop`: all of them.  Shown as "D3/1" when fewer */
    float aim_rad;           /**< aim line direction in the marker's CURRENT frame, CCW from forward */
    float display_rot_rad;   /**< E12: the stored display rotation (gl_cal_device_t).  The
                                  AIM LINE is drawn turned by it about the screen centre,
                                  counter-clockwise for a viewer looking down on the display:
                                  both its direction and the direction of the ball position
                                  it passes through.  Text and symbols are not turned */
    float ball_az_rad;       /**< direction from the marker centre to the ball centre, CCW from
                                  forward: 0 normally; near pi after the 180-degree spin of a
                                  Precision Read (the marker then faces away from the hole).
                                  More than 90 degrees either way: the result screen is drawn
                                  turned round, upright for the golfer behind the ball */
    float distance_m;        /**< to the hole; <= 0 = unknown */
    float plays_like_m;      /**< the FLAT putt that needs the same stroke: the estimator's
                                  roll-out distance v0^2 / (2 a_r) less the PAST setting, so a
                                  dead-flat putt plays its own length; <= 0 = none */
    float slope_pct;         /**< slope magnitude at the ball */
    float fall_line_rad;     /**< downhill direction, marker frame, CCW from forward */
    float break_cups;        /**< + = aim left of the hole */
    float confidence;        /**< 0..1, as shown (after the application's own reductions) */
    /* status */
    uint8_t battery_pct;
    bool charging;           /**< the charger says a charge is running */
    bool chg_full;           /**< the charge has terminated (the charger released its status
                                  output with the cell at its end voltage) */
    bool usb_connected;      /**< host has opened the port */
    uint8_t chg_blocked;     /**< cradle: 0 = nothing stops the charge; the FIRMWARE stopped it:
                                  1 too cold, 2 too hot, 3 temperature sensor (unknown, faulty
                                  or implausible), 4 time limit (6 h of continuous charging),
                                  5 by command; 6 = the CHARGER is not charging and the
                                  firmware does not know why; 7 = the charger holds itself
                                  (its own temperature window) */
    uint8_t cal_step;        /**< zeroing: 0 hold still (first read), 1 turn 180 degrees in
                                  place, 2 hold still (second read), 3 saved */
    /* the INFO item of the dial (regulatory and information screen) */
    char info_hw;            /**< hardware revision letter ('E') */
    uint16_t info_fw;        /**< firmware version, major << 8 | minor */
    char info_serial[8];     /**< serial number, 7 characters and a NUL ("" = none) */
    const char *info_text;   /**< the regulatory text block (NUL-terminated, upper case and
                                  the font's punctuation; '\n' = new line; NULL = none) */
} gl_ui_view_t;

/**
 * The state the renderer draws for a view: view->show, made more cautious
 * by what the view itself says - never NORMAL unless the aim is a solution
 * of a putt with a known distance and a measured flagstick, never a line
 * unless the aim is a solution.  (So a view that the application classified
 * wrongly still cannot look like a normal result.)
 */
gl_ui_show_t gl_ui_view_show(const gl_ui_view_t *view);

/** The strings of the result screen, as drawn ("" = not drawn). */
typedef struct {
    char distance[12];       /**< "19.6FT", "6.0M?", "--" */
    char plays[16];          /**< "PLAYS 21.3FT", "PLAYS 21.3FT?" (hole height only bounded) */
    char note[16];           /**< gl_ui_note_text() */
    char slope[8];           /**< "2.3%" */
    char brk[12];            /**< "<2.5 CUP", "2.5 CUP>", "STRAIGHT", "BREAK ?" */
    char mode[6];            /**< "D2", "2X"; "D3/1": the third placement of a Survey, a result
                                  made of 1 placement (the others lie behind this ball) */
    char zero[4];            /**< "Z?" when the zero of the seat is missing, else "" */
    char state[8];           /**< "APPROX" in the APPROX state, "" otherwise (drawn where the
                                  confidence bar is in the NORMAL state) */
    char age[12];            /**< a recalled result: "45S AGO", "12M AGO", "5H AGO", "3D AGO" */
} gl_ui_result_text_t;

/** Format the strings of the result screen (pure; gl_ui_render() draws
 *  exactly these, and the tests read the numbers shown from here). */
void gl_ui_result_text(const gl_ui_t *ui, const gl_ui_view_t *view, gl_ui_result_text_t *out);

/** Boxes of the confidence bar that are filled (0..5) for a confidence. */
int gl_ui_conf_boxes(float confidence);

/* ---- the INFO item: regulatory and information screen ---------------------------- */

/** Text lines of one page of the regulatory text and the widest of them. */
#define GL_UI_INFO_LINES 10u
#define GL_UI_INFO_LINE_MAX 20u
/** Pages of text the screen will show at most (after the first page with
 *  model, versions and serial number).  Text beyond them is NOT shown: the
 *  build of the text must check gl_ui_info_fit(). */
#define GL_UI_INFO_TEXT_PAGES 4u

/** Characters that fit line `line` (0 .. GL_UI_INFO_LINES - 1) of a text
 *  page inside the round aperture, and where the line starts.  0 for a line
 *  that does not exist. */
unsigned gl_ui_info_line_chars(unsigned line, int *x, int *y);

/** Character cells of one text page (the sum over its lines). */
unsigned gl_ui_info_page_chars(void);

/**
 * Lay `text` out (words are not broken unless one is longer than a line;
 * '\n' starts a new line; a space at a line end is dropped).  Returns the
 * number of text pages it needs and, if `shown` is not NULL, how many of
 * its characters fall on the first GL_UI_INFO_TEXT_PAGES pages (equal to
 * strlen(text) when it fits).
 */
unsigned gl_ui_info_fit(const char *text, size_t *shown);

/** Pages of the INFO item for this text: 1 + the text pages, at most
 *  1 + GL_UI_INFO_TEXT_PAGES. */
unsigned gl_ui_info_pages(const char *text);

/** Tell the UI that the stored result must not be recalled (E30); the same
 *  as GL_EV_LIFTED without a transition.  For the application's start-up. */
void gl_ui_recall_clear(gl_ui_t *ui);

/**
 * Draw the screen of the current state into `g` (cleared first).  All ink
 * stays inside the round aperture (the gfx clip is enabled by this call).
 */
void gl_ui_render(const gl_ui_t *ui, const gl_ui_view_t *view, gl_gfx_t *g);

#endif /* GL_UI_H */
