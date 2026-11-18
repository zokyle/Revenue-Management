/* gl_ui.c - UI state machine (transition table) and screens.  See gl_ui.h. */
#include "gl_ui.h"

#include <math.h>
#include <string.h>

#include "gl_fmt.h"
#include "gl_solver.h"

/* ======================================================================= */
/* Transition table                                                         */
/* ======================================================================= */

#define T(s, e, g, n, a) { (uint8_t)(s), (uint8_t)(e), (uint8_t)(g), (uint8_t)(n), (uint32_t)(a) }

/* Rows for a specific state take precedence over GL_UI_ANY rows; within a
 * state the first row whose guard holds wins. */
static const gl_ui_transition_t table_[] = {
    /* ---- SLEEP: display off, MCU in Stop mode, IMU wake-on-motion ---- */
    T(GL_UI_SLEEP, GL_EV_MOTION, GL_G_ALWAYS, GL_UI_WAKE, GL_ACT_DISPLAY_ON | GL_ACT_REDRAW),
    T(GL_UI_SLEEP, GL_EV_USB_ATTACH, GL_G_ALWAYS, GL_UI_CRADLE_USB,
      GL_ACT_DISPLAY_ON | GL_ACT_USB_START | GL_ACT_REDRAW),
    T(GL_UI_SLEEP, GL_EV_BATT_LOW, GL_G_ALWAYS, GL_UI_SLEEP, 0),

    /* ---- WAKE: splash ---- */
    /* E30: woken with a result that may be recalled: it is kept until the
     * marker is seen to be at rest (recall) or to have been lifted */
    T(GL_UI_WAKE, GL_EV_TIMEOUT, GL_G_RECALL, GL_UI_WAIT_STILL, GL_ACT_WATCH_STILL | GL_ACT_REDRAW),
    T(GL_UI_WAKE, GL_EV_TIMEOUT, GL_G_ALWAYS, GL_UI_WAIT_STILL,
      GL_ACT_WATCH_STILL | GL_ACT_NEW_READ | GL_ACT_REDRAW),
    T(GL_UI_WAKE, GL_EV_LIFTED, GL_G_ALWAYS, GL_UI_WAKE, GL_ACT_NEW_READ),
    T(GL_UI_WAKE, GL_EV_UPRIGHT, GL_G_ALWAYS, GL_UI_SETTINGS_DIAL,
      GL_ACT_DIAL_BEGIN | GL_ACT_REDRAW),

    /* ---- WAIT_STILL ---- */
    /* E30 Recall: tapped awake, at rest again and not lifted since the last
     * result: that result, with its age.  No tilt read, no camera */
    T(GL_UI_WAIT_STILL, GL_EV_STILL, GL_G_RECALL, GL_UI_SHOW_RESULT, GL_ACT_RECALL | GL_ACT_REDRAW),
    T(GL_UI_WAIT_STILL, GL_EV_STILL, GL_G_ALWAYS, GL_UI_READ_TILT,
      GL_ACT_START_TILT | GL_ACT_REDRAW),
    T(GL_UI_WAIT_STILL, GL_EV_LIFTED, GL_G_ALWAYS, GL_UI_WAIT_STILL,
      GL_ACT_WATCH_STILL | GL_ACT_NEW_READ | GL_ACT_REDRAW),
    T(GL_UI_WAIT_STILL, GL_EV_UPRIGHT, GL_G_ALWAYS, GL_UI_SETTINGS_DIAL,
      GL_ACT_DIAL_BEGIN | GL_ACT_REDRAW),
    T(GL_UI_WAIT_STILL, GL_EV_TIMEOUT, GL_G_ALWAYS, GL_UI_SLEEP,
      GL_ACT_ENTER_SLEEP | GL_ACT_SURVEY_RESET),

    /* ---- READ_TILT: 1 s accelerometer average ---- */
    T(GL_UI_READ_TILT, GL_EV_TILT_DONE, GL_G_PRECISION_REREAD, GL_UI_SOLVE,
      GL_ACT_START_SOLVE | GL_ACT_PRECISION | GL_ACT_REDRAW),
    T(GL_UI_READ_TILT, GL_EV_TILT_DONE, GL_G_ALWAYS, GL_UI_CAPTURE,
      GL_ACT_START_CAPTURE | GL_ACT_REDRAW),
    /* A disturbed RE-READ of a Precision Read goes back to the spin prompt
     * with the gyro integration still running: the marker has to come to
     * rest at a half turn again before another re-read starts (it used to
     * re-read from WAIT_STILL and combine with the angle measured BEFORE the
     * disturbance). */
    T(GL_UI_READ_TILT, GL_EV_TILT_FAIL, GL_G_PRECISION_REREAD, GL_UI_PRECISION_WAIT_SPIN,
      GL_ACT_ABORT_READ | GL_ACT_REDRAW),
    T(GL_UI_READ_TILT, GL_EV_MOTION, GL_G_PRECISION_REREAD, GL_UI_PRECISION_WAIT_SPIN,
      GL_ACT_ABORT_READ | GL_ACT_REDRAW),
    T(GL_UI_READ_TILT, GL_EV_TILT_FAIL, GL_G_ALWAYS, GL_UI_WAIT_STILL,
      GL_ACT_ABORT_READ | GL_ACT_WATCH_STILL | GL_ACT_REDRAW),
    T(GL_UI_READ_TILT, GL_EV_MOTION, GL_G_ALWAYS, GL_UI_WAIT_STILL,
      GL_ACT_ABORT_READ | GL_ACT_WATCH_STILL | GL_ACT_REDRAW),
    T(GL_UI_READ_TILT, GL_EV_TIMEOUT, GL_G_ALWAYS, GL_UI_ERROR,
      GL_ACT_ABORT_READ | GL_ACT_REDRAW),

    /* ---- CAPTURE: camera rail on ---- */
    T(GL_UI_CAPTURE, GL_EV_CAPTURE_DONE, GL_G_SURVEY_ROOM, GL_UI_SOLVE,
      GL_ACT_SURVEY_STORE | GL_ACT_START_SOLVE | GL_ACT_REDRAW),
    T(GL_UI_CAPTURE, GL_EV_CAPTURE_DONE, GL_G_ALWAYS, GL_UI_SOLVE,
      GL_ACT_START_SOLVE | GL_ACT_REDRAW),
    T(GL_UI_CAPTURE, GL_EV_CAPTURE_NO_STICK, GL_G_HAS_MANUAL_DIST, GL_UI_SOLVE,
      GL_ACT_START_SOLVE | GL_ACT_REDRAW),
    T(GL_UI_CAPTURE, GL_EV_CAPTURE_NO_STICK, GL_G_ALWAYS, GL_UI_SETTINGS_DIAL,
      GL_ACT_DIAL_BEGIN | GL_ACT_REDRAW),
    T(GL_UI_CAPTURE, GL_EV_CAPTURE_FAIL, GL_G_ALWAYS, GL_UI_ERROR,
      GL_ACT_ABORT_READ | GL_ACT_REDRAW),
    /* tilt-only mode: no camera read was made; solved as a flag-out read */
    T(GL_UI_CAPTURE, GL_EV_CAPTURE_SKIPPED, GL_G_ALWAYS, GL_UI_SOLVE,
      GL_ACT_START_SOLVE | GL_ACT_REDRAW),
    T(GL_UI_CAPTURE, GL_EV_MOTION, GL_G_ALWAYS, GL_UI_WAIT_STILL,
      GL_ACT_ABORT_READ | GL_ACT_WATCH_STILL | GL_ACT_REDRAW),
    T(GL_UI_CAPTURE, GL_EV_TIMEOUT, GL_G_ALWAYS, GL_UI_ERROR,
      GL_ACT_ABORT_READ | GL_ACT_REDRAW),

    /* ---- SOLVE ---- */
    T(GL_UI_SOLVE, GL_EV_SOLVE_DONE, GL_G_ALWAYS, GL_UI_SHOW_RESULT, GL_ACT_REDRAW),
    T(GL_UI_SOLVE, GL_EV_SOLVE_FAIL, GL_G_ALWAYS, GL_UI_ERROR, GL_ACT_REDRAW),
    T(GL_UI_SOLVE, GL_EV_TIMEOUT, GL_G_ALWAYS, GL_UI_ERROR, GL_ACT_REDRAW),

    /* ---- SHOW_RESULT ---- */
    T(GL_UI_SHOW_RESULT, GL_EV_DOUBLE_TAP, GL_G_SURVEY_ACTIVE, GL_UI_SHOW_RESULT,
      GL_ACT_SURVEY_RESET | GL_ACT_REDRAW),
    /* The Precision Read is offered ONCE per placement.  After a re-read the
     * marker has been turned since its cameras saw the flagstick: a second
     * double tap goes on to the Survey (what the spin prompt offers for a
     * second double tap anyway), it never arms another spin.  (It used to,
     * with the first read's slope and a gyro angle counted from the turned
     * marker: the half turn back then cancelled the slope to "0.0 %,
     * STRAIGHT, 2X".) */
    T(GL_UI_SHOW_RESULT, GL_EV_DOUBLE_TAP, GL_G_PRECISION_REREAD, GL_UI_SURVEY_NEXT_DROP,
      GL_ACT_SURVEY_STORE | GL_ACT_REDRAW),
    T(GL_UI_SHOW_RESULT, GL_EV_DOUBLE_TAP, GL_G_ALWAYS, GL_UI_PRECISION_WAIT_SPIN,
      GL_ACT_ARM_SPIN | GL_ACT_REDRAW),
    T(GL_UI_SHOW_RESULT, GL_EV_MOTION, GL_G_SURVEY_ROOM, GL_UI_SURVEY_NEXT_DROP,
      GL_ACT_WATCH_STILL | GL_ACT_REDRAW),
    /* a FIFTH placement: the Survey is over, this is a new plain read */
    T(GL_UI_SHOW_RESULT, GL_EV_MOTION, GL_G_SURVEY_FULL, GL_UI_WAIT_STILL,
      GL_ACT_SURVEY_RESET | GL_ACT_WATCH_STILL | GL_ACT_NEW_READ | GL_ACT_REDRAW),
    T(GL_UI_SHOW_RESULT, GL_EV_MOTION, GL_G_ALWAYS, GL_UI_WAIT_STILL,
      GL_ACT_WATCH_STILL | GL_ACT_NEW_READ | GL_ACT_REDRAW),
    T(GL_UI_SHOW_RESULT, GL_EV_UPRIGHT, GL_G_ALWAYS, GL_UI_SETTINGS_DIAL,
      GL_ACT_DIAL_BEGIN | GL_ACT_REDRAW),
    T(GL_UI_SHOW_RESULT, GL_EV_TIMEOUT, GL_G_ALWAYS, GL_UI_SLEEP,
      GL_ACT_ENTER_SLEEP | GL_ACT_SURVEY_RESET),

    /* ---- PRECISION_WAIT_SPIN: "spin 180" prompt; motion is expected ---- */
    T(GL_UI_PRECISION_WAIT_SPIN, GL_EV_SPIN_DONE, GL_G_ALWAYS, GL_UI_READ_TILT,
      GL_ACT_START_TILT | GL_ACT_REDRAW),
    T(GL_UI_PRECISION_WAIT_SPIN, GL_EV_DOUBLE_TAP, GL_G_ALWAYS, GL_UI_SURVEY_NEXT_DROP,
      GL_ACT_SURVEY_STORE | GL_ACT_REDRAW),
    T(GL_UI_PRECISION_WAIT_SPIN, GL_EV_UPRIGHT, GL_G_ALWAYS, GL_UI_SETTINGS_DIAL,
      GL_ACT_DIAL_BEGIN | GL_ACT_REDRAW),
    T(GL_UI_PRECISION_WAIT_SPIN, GL_EV_TIMEOUT, GL_G_ALWAYS, GL_UI_SHOW_RESULT,
      GL_ACT_SPIN_ABANDON | GL_ACT_REDRAW),

    /* ---- SURVEY_NEXT_DROP: waiting for the marker to be moved and re-placed ---- */
    T(GL_UI_SURVEY_NEXT_DROP, GL_EV_MOTION, GL_G_ALWAYS, GL_UI_SURVEY_NEXT_DROP,
      GL_ACT_WATCH_STILL),
    T(GL_UI_SURVEY_NEXT_DROP, GL_EV_STILL, GL_G_MOVED, GL_UI_READ_TILT,
      GL_ACT_START_TILT | GL_ACT_REDRAW),
    T(GL_UI_SURVEY_NEXT_DROP, GL_EV_DOUBLE_TAP, GL_G_ALWAYS, GL_UI_SHOW_RESULT,
      GL_ACT_SURVEY_RESET | GL_ACT_REDRAW),
    T(GL_UI_SURVEY_NEXT_DROP, GL_EV_TIMEOUT, GL_G_ALWAYS, GL_UI_SLEEP,
      GL_ACT_SURVEY_RESET | GL_ACT_ENTER_SLEEP),

    /* ---- SETTINGS_DIAL: upright; roll to change, double tap = next item,
     *      lay flat = confirm ---- */
    T(GL_UI_SETTINGS_DIAL, GL_EV_DIAL_STEP, GL_G_ALWAYS, GL_UI_SETTINGS_DIAL, GL_ACT_REDRAW),
    T(GL_UI_SETTINGS_DIAL, GL_EV_DOUBLE_TAP, GL_G_ALWAYS, GL_UI_SETTINGS_DIAL,
      GL_ACT_DIAL_BEGIN | GL_ACT_REDRAW),
    T(GL_UI_SETTINGS_DIAL, GL_EV_FLAT, GL_G_ITEM_ZERO_YES, GL_UI_CAL_ZERO,
      GL_ACT_SAVE_SETTINGS | GL_ACT_CAL_ZERO_START | GL_ACT_REDRAW),
    T(GL_UI_SETTINGS_DIAL, GL_EV_FLAT, GL_G_ALWAYS, GL_UI_WAIT_STILL,
      GL_ACT_SAVE_SETTINGS | GL_ACT_WATCH_STILL | GL_ACT_NEW_READ | GL_ACT_REDRAW),
    /* The distance PROMPT (no flagstick seen) is reached with the marker
     * lying on the green.  Picking it up and putting it down again - without
     * ever standing it upright - is a new placement: read again.  (It used
     * to be ignored: the prompt could only be left through the dial or,
     * after 30 s, into sleep.)  A golfer who did stand it upright and rolled
     * it gets FLAT first (row above), which saves what he dialled. */
    T(GL_UI_SETTINGS_DIAL, GL_EV_MOTION, GL_G_DIST_PROMPT, GL_UI_SETTINGS_DIAL, GL_ACT_WATCH_STILL),
    T(GL_UI_SETTINGS_DIAL, GL_EV_STILL, GL_G_DIST_PROMPT_MOVED, GL_UI_READ_TILT,
      GL_ACT_START_TILT | GL_ACT_NEW_READ | GL_ACT_REDRAW),
    T(GL_UI_SETTINGS_DIAL, GL_EV_TIMEOUT, GL_G_ALWAYS, GL_UI_SLEEP,
      GL_ACT_ENTER_SLEEP | GL_ACT_SURVEY_RESET),

    /* ---- CRADLE_USB: charging and data, while a host talks.  The cradle
     *      accepts the marker one way round only and holds it down: nothing
     *      is calibrated here.  The state's time limit is the 30 s WITHOUT
     *      HOST ACTIVITY of DESIGN_SPEC E32: the application restarts it
     *      (gl_ui_keepalive) whenever a host sends something, so on a wall
     *      charger, or under an idle host, it runs out and the marker goes
     *      to sleep in the cradle ---- */
    T(GL_UI_CRADLE_USB, GL_EV_USB_DETACH, GL_G_ALWAYS, GL_UI_SLEEP,
      GL_ACT_USB_STOP | GL_ACT_ENTER_SLEEP),
    T(GL_UI_CRADLE_USB, GL_EV_USB_ATTACH, GL_G_ALWAYS, GL_UI_CRADLE_USB, 0),
    T(GL_UI_CRADLE_USB, GL_EV_BATT_LOW, GL_G_ALWAYS, GL_UI_CRADLE_USB, 0),
    T(GL_UI_CRADLE_USB, GL_EV_TOO_HOT, GL_G_ALWAYS, GL_UI_CRADLE_USB, 0),
    T(GL_UI_CRADLE_USB, GL_EV_TIMEOUT, GL_G_ALWAYS, GL_UI_CRADLE_SLEEP,
      GL_ACT_CRADLE_SLEEP | GL_ACT_REDRAW),

    /* ---- CRADLE_SLEEP (E32): MCU in Stop mode, the display on with a static
     *      symbol.  Out of it: the host resumes the bus, or the marker is
     *      lifted out.  VBUS bouncing, motion and taps do not wake it ---- */
    T(GL_UI_CRADLE_SLEEP, GL_EV_USB_RESUME, GL_G_ALWAYS, GL_UI_CRADLE_USB,
      GL_ACT_DISPLAY_ON | GL_ACT_USB_START | GL_ACT_REDRAW),
    T(GL_UI_CRADLE_SLEEP, GL_EV_USB_DETACH, GL_G_ALWAYS, GL_UI_SLEEP,
      GL_ACT_USB_STOP | GL_ACT_ENTER_SLEEP),
    T(GL_UI_CRADLE_SLEEP, GL_EV_USB_ATTACH, GL_G_ALWAYS, GL_UI_CRADLE_SLEEP, 0),
    T(GL_UI_CRADLE_SLEEP, GL_EV_BATT_LOW, GL_G_ALWAYS, GL_UI_CRADLE_SLEEP, 0),
    T(GL_UI_CRADLE_SLEEP, GL_EV_TOO_HOT, GL_G_ALWAYS, GL_UI_CRADLE_SLEEP, 0),

    /* ---- CAL_ZERO: zeroing on any hard flat surface (read, turn the marker
     *      180 degrees in place, read again).  Entered only from the dial;
     *      the turn is expected motion, so MOTION is ignored here.  Being put
     *      in the cradle abandons the procedure ---- */
    T(GL_UI_CAL_ZERO, GL_EV_CAL_DONE, GL_G_ALWAYS, GL_UI_WAIT_STILL,
      GL_ACT_WATCH_STILL | GL_ACT_NEW_READ | GL_ACT_REDRAW),
    T(GL_UI_CAL_ZERO, GL_EV_CAL_FAIL, GL_G_ALWAYS, GL_UI_ERROR, GL_ACT_CAL_ABORT | GL_ACT_REDRAW),
    T(GL_UI_CAL_ZERO, GL_EV_USB_ATTACH, GL_G_ALWAYS, GL_UI_CRADLE_USB,
      GL_ACT_CAL_ABORT | GL_ACT_USB_START | GL_ACT_DISPLAY_ON | GL_ACT_REDRAW),
    T(GL_UI_CAL_ZERO, GL_EV_DOUBLE_TAP, GL_G_ALWAYS, GL_UI_WAIT_STILL,
      GL_ACT_CAL_ABORT | GL_ACT_WATCH_STILL | GL_ACT_NEW_READ | GL_ACT_REDRAW),
    T(GL_UI_CAL_ZERO, GL_EV_BATT_LOW, GL_G_ALWAYS, GL_UI_CAL_ZERO, 0),
    T(GL_UI_CAL_ZERO, GL_EV_FAULT, GL_G_ALWAYS, GL_UI_ERROR,
      GL_ACT_CAL_ABORT | GL_ACT_ABORT_READ | GL_ACT_REDRAW),
    T(GL_UI_CAL_ZERO, GL_EV_TIMEOUT, GL_G_ALWAYS, GL_UI_ERROR, GL_ACT_CAL_ABORT | GL_ACT_REDRAW),

    /* ---- ERROR ---- */
    /* in the cradle a double tap goes back to the cradle state, never to a
     * read: the device must stay supervised (USB, charge gate) there */
    T(GL_UI_ERROR, GL_EV_DOUBLE_TAP, GL_G_USB, GL_UI_CRADLE_USB, GL_ACT_REDRAW),
    T(GL_UI_ERROR, GL_EV_DOUBLE_TAP, GL_G_ALWAYS, GL_UI_WAIT_STILL,
      GL_ACT_WATCH_STILL | GL_ACT_NEW_READ | GL_ACT_REDRAW),
    T(GL_UI_ERROR, GL_EV_TIMEOUT, GL_G_USB, GL_UI_CRADLE_USB, GL_ACT_REDRAW),
    T(GL_UI_ERROR, GL_EV_TIMEOUT, GL_G_ALWAYS, GL_UI_SLEEP,
      GL_ACT_ENTER_SLEEP | GL_ACT_SURVEY_RESET),
    T(GL_UI_ERROR, GL_EV_FAULT, GL_G_ALWAYS, GL_UI_ERROR, GL_ACT_REDRAW),
    T(GL_UI_ERROR, GL_EV_USB_DETACH, GL_G_ALWAYS, GL_UI_ERROR, GL_ACT_USB_STOP),

    /* ---- LOW_BATT ---- */
    T(GL_UI_LOW_BATT, GL_EV_TIMEOUT, GL_G_ALWAYS, GL_UI_SLEEP,
      GL_ACT_ENTER_SLEEP | GL_ACT_SURVEY_RESET),
    T(GL_UI_LOW_BATT, GL_EV_BATT_LOW, GL_G_ALWAYS, GL_UI_LOW_BATT, 0),
    T(GL_UI_LOW_BATT, GL_EV_TOO_HOT, GL_G_ALWAYS, GL_UI_LOW_BATT, 0),

    /* ---- TOO_HOT (E13): the cell is above 60 C; no camera read.  Shown for
     *      4 s, then sleep; the next placement measures again ---- */
    T(GL_UI_TOO_HOT, GL_EV_TIMEOUT, GL_G_ALWAYS, GL_UI_SLEEP,
      GL_ACT_ENTER_SLEEP | GL_ACT_SURVEY_RESET),
    T(GL_UI_TOO_HOT, GL_EV_TOO_HOT, GL_G_ALWAYS, GL_UI_TOO_HOT, 0),

    /* ---- states in which TOO_HOT changes nothing: asleep; a result that is
     *      already on the screen stays; the dial and the zeroing use no
     *      camera (the read that follows them is gated when it starts) ---- */
    T(GL_UI_SLEEP, GL_EV_TOO_HOT, GL_G_ALWAYS, GL_UI_SLEEP, 0),
    T(GL_UI_SHOW_RESULT, GL_EV_TOO_HOT, GL_G_ALWAYS, GL_UI_SHOW_RESULT, 0),
    T(GL_UI_PRECISION_WAIT_SPIN, GL_EV_TOO_HOT, GL_G_ALWAYS, GL_UI_PRECISION_WAIT_SPIN, 0),
    T(GL_UI_SETTINGS_DIAL, GL_EV_TOO_HOT, GL_G_ALWAYS, GL_UI_SETTINGS_DIAL, 0),
    T(GL_UI_CAL_ZERO, GL_EV_TOO_HOT, GL_G_ALWAYS, GL_UI_CAL_ZERO, 0),
    T(GL_UI_ERROR, GL_EV_TOO_HOT, GL_G_ALWAYS, GL_UI_ERROR, 0),

    /* ---- the factory's armed zeroing: it starts where a read would start,
     *      when the marker has been put down out of the cradle ---- */
    T(GL_UI_WAIT_STILL, GL_EV_CAL_ARMED, GL_G_ALWAYS, GL_UI_CAL_ZERO,
      GL_ACT_CAL_ZERO_START | GL_ACT_REDRAW),
    /* ... and nowhere else: in every other state the event has no row and
     * is ignored (a result on the screen, the dial, the cradle) */
    /* ---- the sleep-current test: asleep at once, from wherever (not from
     *      the cradle: the application does not send it there) ---- */
    T(GL_UI_CRADLE_USB, GL_EV_FORCE_SLEEP, GL_G_ALWAYS, GL_UI_CRADLE_USB, 0),
    T(GL_UI_CRADLE_SLEEP, GL_EV_FORCE_SLEEP, GL_G_ALWAYS, GL_UI_CRADLE_SLEEP, 0),
    T(GL_UI_SLEEP, GL_EV_FORCE_SLEEP, GL_G_ALWAYS, GL_UI_SLEEP, 0),
    T(GL_UI_ANY, GL_EV_FORCE_SLEEP, GL_G_ALWAYS, GL_UI_SLEEP,
      GL_ACT_ABORT_READ | GL_ACT_CAL_ABORT | GL_ACT_SURVEY_RESET | GL_ACT_ENTER_SLEEP),

    /* ---- from any state ---- */
    T(GL_UI_ANY, GL_EV_USB_ATTACH, GL_G_ALWAYS, GL_UI_CRADLE_USB,
      GL_ACT_ABORT_READ | GL_ACT_SURVEY_RESET | GL_ACT_USB_START | GL_ACT_DISPLAY_ON |
          GL_ACT_REDRAW),
    T(GL_UI_ANY, GL_EV_BATT_LOW, GL_G_ALWAYS, GL_UI_LOW_BATT,
      GL_ACT_ABORT_READ | GL_ACT_SURVEY_RESET | GL_ACT_REDRAW),
    T(GL_UI_ANY, GL_EV_FAULT, GL_G_ALWAYS, GL_UI_ERROR,
      GL_ACT_ABORT_READ | GL_ACT_DISPLAY_ON | GL_ACT_REDRAW),
    /* a camera read was about to start from a cell that is too hot */
    T(GL_UI_ANY, GL_EV_TOO_HOT, GL_G_ALWAYS, GL_UI_TOO_HOT,
      GL_ACT_ABORT_READ | GL_ACT_SURVEY_RESET | GL_ACT_DISPLAY_ON | GL_ACT_REDRAW),
    /* VBUS went away in a state that has no row for it (the application has
     * already stopped USB itself, below the UI): leave the cradle business
     * cleanly, whatever the state was */
    T(GL_UI_ANY, GL_EV_USB_DETACH, GL_G_ALWAYS, GL_UI_SLEEP,
      GL_ACT_ABORT_READ | GL_ACT_USB_STOP | GL_ACT_SURVEY_RESET | GL_ACT_ENTER_SLEEP),
};

static const uint32_t timeout_ms_[GL_UI_STATE_COUNT] = {
    0,      /* SLEEP */
    800,    /* WAKE */
    20000,  /* WAIT_STILL */
    4000,   /* READ_TILT */
    8000,   /* CAPTURE */
    3000,   /* SOLVE */
    45000,  /* SHOW_RESULT */
    20000,  /* PRECISION_WAIT_SPIN */
    60000,  /* SURVEY_NEXT_DROP */
    30000,  /* SETTINGS_DIAL */
    30000,  /* CRADLE_USB: without host activity (the application restarts it) */
    120000, /* CAL_ZERO */
    5000,   /* ERROR */
    4000,   /* LOW_BATT */
    4000,   /* TOO_HOT */
    0,      /* CRADLE_SLEEP */
};

const gl_ui_transition_t *gl_ui_table(size_t *rows)
{
    if (rows != NULL) {
        *rows = GL_ARRAY_LEN(table_);
    }
    return table_;
}

uint32_t gl_ui_timeout_ms(gl_ui_state_t state)
{
    return ((unsigned)state < (unsigned)GL_UI_STATE_COUNT) ? timeout_ms_[state] : 0u;
}

const char *gl_ui_state_name(gl_ui_state_t state)
{
    static const char *const names[GL_UI_STATE_COUNT] = {
        "SLEEP", "WAKE", "WAIT_STILL", "READ_TILT", "CAPTURE", "SOLVE", "SHOW_RESULT",
        "PRECISION_WAIT_SPIN", "SURVEY_NEXT_DROP", "SETTINGS_DIAL", "CRADLE_USB", "CAL_ZERO",
        "ERROR", "LOW_BATT", "TOO_HOT", "CRADLE_SLEEP"
    };
    return ((unsigned)state < (unsigned)GL_UI_STATE_COUNT) ? names[state] : "?";
}

const char *gl_ui_event_name(gl_ui_event_t ev)
{
    static const char *const names[GL_EV_COUNT] = {
        "NONE", "MOTION", "STILL", "TILT_DONE", "TILT_FAIL", "CAPTURE_DONE", "CAPTURE_NO_STICK",
        "CAPTURE_FAIL", "SOLVE_DONE", "SOLVE_FAIL", "DOUBLE_TAP", "SPIN_DONE", "UPRIGHT", "FLAT",
        "DIAL_STEP", "USB_ATTACH", "USB_DETACH", "BATT_LOW", "CAL_DONE", "CAL_FAIL",
        "FAULT", "TIMEOUT", "TOO_HOT", "USB_RESUME", "CAPTURE_SKIPPED", "CAL_ARMED",
        "FORCE_SLEEP", "LIFTED"
    };
    return ((unsigned)ev < (unsigned)GL_EV_COUNT) ? names[ev] : "?";
}

/* ---- dial items --------------------------------------------------------- */

static int item_value_(const gl_ui_t *ui)
{
    if (ui->item >= GL_UI_ITEM_ZERO) {
        return 0; /* "ZERO" always starts at NO, "INFO" at its first page */
    }
    return gl_settings_item_get(&ui->edit, (gl_item_t)ui->item);
}

static int info_pages_(const gl_ui_t *ui)
{
    return (ui->info_pages > 0u) ? (int)ui->info_pages : 1;
}

static bool guard_(const gl_ui_t *ui, uint8_t guard)
{
    switch (guard) {
    case GL_G_ALWAYS: return true;
    case GL_G_PRECISION_REREAD: return ui->read_kind == (uint8_t)GL_READ_PRECISION;
    case GL_G_SURVEY_ACTIVE: return ui->survey_count > 0u;
    case GL_G_SURVEY_ROOM: return ui->survey_count > 0u && ui->survey_count < 4u;
    case GL_G_SURVEY_FULL: return ui->survey_count >= 4u;
    case GL_G_HAS_MANUAL_DIST: return ui->edit.manual_distance_cm != 0u;
    case GL_G_MOVED: return ui->moved;
    case GL_G_USB: return ui->usb;
    case GL_G_ITEM_ZERO_YES:
        return ui->item == GL_UI_ITEM_ZERO && ui->dial_value != 0;
    case GL_G_DIST_PROMPT: return ui->dist_prompt;
    case GL_G_DIST_PROMPT_MOVED: return ui->dist_prompt && ui->moved;
    case GL_G_RECALL: return ui->recall;
    default: return false;
    }
}

void gl_ui_init(gl_ui_t *ui, const gl_settings_t *settings, uint32_t now_ms)
{
    memset(ui, 0, sizeof(*ui));
    ui->state = (uint8_t)GL_UI_SLEEP;
    ui->read_kind = (uint8_t)GL_READ_QUICK;
    ui->state_since_ms = now_ms;
    if (settings != NULL) {
        ui->edit = *settings;
        ui->saved = *settings;
    } else {
        gl_settings_defaults(&ui->edit);
        gl_settings_defaults(&ui->saved);
    }
}

uint32_t gl_ui_dispatch(gl_ui_t *ui, gl_ui_event_t ev, int32_t arg, uint32_t now_ms)
{
    const gl_ui_transition_t *row = NULL;
    const uint8_t from = ui->state;

    /* facts that hold whatever the table says */
    if (ev == GL_EV_USB_ATTACH) {
        ui->usb = true;
    } else if (ev == GL_EV_USB_DETACH) {
        ui->usb = false;
    }
    for (int pass = 0; pass < 2 && row == NULL; pass++) {
        const uint8_t want = (pass == 0) ? from : (uint8_t)GL_UI_ANY;
        for (size_t i = 0; i < GL_ARRAY_LEN(table_); i++) {
            if (table_[i].state == want && table_[i].event == (uint8_t)ev &&
                guard_(ui, table_[i].guard)) {
                row = &table_[i];
                break;
            }
        }
    }
    if (ev == GL_EV_LIFTED) {
        ui->recall = false; /* E30: whatever the state, that result is not shown again */
    }
    if (row == NULL) {
        return 0; /* event not meaningful in this state: ignored */
    }

    /* ---- bookkeeping tied to particular transitions ---- */
    if ((row->actions & GL_ACT_SURVEY_RESET) != 0u) {
        ui->survey_count = 0;
    }
    if ((row->actions & GL_ACT_SURVEY_STORE) != 0u && ui->survey_count < 4u) {
        ui->survey_count++;
    }
    if ((row->actions & GL_ACT_NEW_READ) != 0u) {
        ui->read_kind = (uint8_t)GL_READ_QUICK;
    }
    if (row->next == (uint8_t)GL_UI_READ_TILT) {
        if (from == (uint8_t)GL_UI_PRECISION_WAIT_SPIN) {
            ui->read_kind = (uint8_t)GL_READ_PRECISION;
        } else if (from == (uint8_t)GL_UI_SURVEY_NEXT_DROP) {
            ui->read_kind = (uint8_t)GL_READ_SURVEY;
        }
    }
    if (row->next == (uint8_t)GL_UI_SURVEY_NEXT_DROP) {
        if (from != (uint8_t)GL_UI_SURVEY_NEXT_DROP) {
            /* arriving by picking the marker up counts as "moved" already */
            ui->moved = (ev == GL_EV_MOTION);
        } else if (ev == GL_EV_MOTION) {
            ui->moved = true;
        }
    }
    if (row->next == (uint8_t)GL_UI_SETTINGS_DIAL) {
        if (from != (uint8_t)GL_UI_SETTINGS_DIAL) {
            ui->saved = ui->edit; /* snapshot, restored if the dial is abandoned */
            ui->dist_prompt = (ev == GL_EV_CAPTURE_NO_STICK);
            ui->moved = false;
            ui->item = (uint8_t)(ui->dist_prompt ? GL_ITEM_DISTANCE : GL_ITEM_STIMP);
            ui->dial_value = item_value_(ui);
        } else if (ev == GL_EV_DOUBLE_TAP) {
            ui->item = (uint8_t)((ui->item + 1u) % GL_UI_ITEM_COUNT);
            ui->dial_value = item_value_(ui);
        } else if (ev == GL_EV_DIAL_STEP) {
            if (ui->item < GL_UI_ITEM_ZERO) {
                gl_settings_item_set(&ui->edit, (gl_item_t)ui->item, (int)arg);
                ui->dial_value = item_value_(ui);
            } else if (ui->item == GL_UI_ITEM_INFO) {
                ui->dial_value = gl_clampi((int)arg, 0, info_pages_(ui) - 1);
            } else {
                ui->dial_value = (arg != 0) ? 1 : 0;
            }
        } else if (ev == GL_EV_MOTION) {
            ui->moved = true; /* the distance prompt: the marker was picked up */
        }
    }
    if (from == (uint8_t)GL_UI_SETTINGS_DIAL && row->next != (uint8_t)GL_UI_SETTINGS_DIAL) {
        if ((row->actions & GL_ACT_SAVE_SETTINGS) != 0u) {
            ui->saved = ui->edit;
        } else {
            ui->edit = ui->saved; /* abandoned: discard the edits */
        }
        ui->dist_prompt = false;
    }
    if (row->next == (uint8_t)GL_UI_ERROR) {
        switch (ev) {
        case GL_EV_FAULT:
        case GL_EV_SOLVE_FAIL:
        case GL_EV_CAL_FAIL:
            ui->error_code = (uint16_t)((arg > 0 && arg < 0xFFFF) ? arg : (int32_t)GL_ERR_IO);
            break;
        case GL_EV_TIMEOUT: ui->error_code = (uint16_t)GL_ERR_TIMEOUT; break;
        default: ui->error_code = (uint16_t)GL_ERR_IO; break;
        }
    }

    /* ---- E30: may the result that is going off the screen be recalled? ----
     * Yes when it leaves by its time limit; then only for as long as the
     * marker sleeps, is woken by motion and comes to rest: every other
     * transition ends it (the dial, the cradle, an error, a new read ...). */
    if (from == (uint8_t)GL_UI_SHOW_RESULT && row->next == (uint8_t)GL_UI_SLEEP &&
        ev == GL_EV_TIMEOUT) {
        ui->recall = true;
    } else if (ui->recall) {
        const bool same = (row->next == from) && (row->actions & GL_ACT_NEW_READ) == 0u;
        bool keep = false;
        switch ((gl_ui_state_t)from) {
        case GL_UI_SLEEP:
            keep = same || (row->next == (uint8_t)GL_UI_WAKE && ev == GL_EV_MOTION);
            break;
        case GL_UI_WAKE:
            keep = same || (row->next == (uint8_t)GL_UI_WAIT_STILL && row->guard == (uint8_t)GL_G_RECALL);
            break;
        case GL_UI_WAIT_STILL:
            keep = same || (row->next == (uint8_t)GL_UI_SHOW_RESULT && row->guard == (uint8_t)GL_G_RECALL);
            break;
        default:
            break;
        }
        if (!keep) {
            ui->recall = false;
        }
    }

    /* ---- the transition itself ---- */
    if (row->next != from || row->actions != 0u) {
        /* entering a state, or activity within it, restarts its time limit;
         * pure "ignore" rows do not */
        ui->state_since_ms = now_ms;
    }
    ui->state = row->next;
    ui->transitions++;
    return row->actions;
}

uint32_t gl_ui_tick(gl_ui_t *ui, uint32_t now_ms)
{
    uint32_t limit = gl_ui_timeout_ms((gl_ui_state_t)ui->state);
    if (limit != 0u && (uint32_t)(now_ms - ui->state_since_ms) >= limit) {
        return gl_ui_dispatch(ui, GL_EV_TIMEOUT, 0, now_ms);
    }
    return 0;
}

void gl_ui_keepalive(gl_ui_t *ui, uint32_t now_ms)
{
    ui->state_since_ms = now_ms;
}

void gl_ui_recall_clear(gl_ui_t *ui)
{
    ui->recall = false;
}

/* ======================================================================= */
/* The three display states (DESIGN_SPEC E31, E33)                          */
/* ======================================================================= */

float gl_ui_steep_ratio(float a, float b, float c, float d, float distance_m, float a_r_mps2)
{
    const float s_crit = a_r_mps2 / (GL_UI_ROLL_FACTOR * GL_UI_G_MPS2);
    float g0, g1, r;

    if (!(a_r_mps2 > 0.0f) || !isfinite(s_crit) || !isfinite(distance_m)) {
        return INFINITY;
    }
    g0 = sqrtf(a * a + b * b);
    g1 = sqrtf((a + c * distance_m) * (a + c * distance_m) +
               (b + d * distance_m) * (b + d * distance_m));
    if (!isfinite(g0) || !isfinite(g1)) {
        return INFINITY; /* (a comparison with not-a-number is false: caught here) */
    }
    r = ((g1 > g0) ? g1 : g0) / s_crit;
    return isfinite(r) ? r : INFINITY;
}

gl_ui_show_t gl_ui_classify(const gl_ui_class_in_t *in, gl_ui_note_t *note)
{
    /* (not "ratio < limit" negated: a ratio that is not a number is steep) */
    const bool steep = !(in->steep_ratio < GL_UI_STEEP_RATIO);
    gl_ui_note_t n = GL_UI_NOTE_NONE;
    gl_ui_show_t show;

    if (in->aim_source == (uint8_t)GL_AIM_BEST_EFFORT && in->solve_status <= (uint8_t)GL_SOLVE_NO_CONVERGENCE) {
        show = GL_UI_SHOW_NONE;
        n = steep ? GL_UI_NOTE_TOO_STEEP : GL_UI_NOTE_NOT_SOLVED;
    } else if ((in->aim_source != (uint8_t)GL_AIM_FROM_PATCH && in->aim_source != (uint8_t)GL_AIM_FROM_PLANE) ||
               in->solve_status > (uint8_t)GL_SOLVE_NO_CONVERGENCE) {
        /* straight at the hole, an aim source that does not exist, or a
         * solve that was invalid or never ran */
        show = GL_UI_SHOW_NONE;
        n = GL_UI_NOTE_NO_SOLUTION;
    } else {
        show = GL_UI_SHOW_APPROX;
        if (in->flag_missing) {
            n = GL_UI_NOTE_NO_FLAG;
        } else if (in->range_missing || !in->distance_known) {
            n = GL_UI_NOTE_NO_RANGE;
        } else if (steep) {
            n = GL_UI_NOTE_TOO_STEEP;
        } else if (in->aim_source == (uint8_t)GL_AIM_FROM_PLANE) {
            n = GL_UI_NOTE_APPROX; /* the secant plane's solution */
        } else if (in->solve_status == (uint8_t)GL_SOLVE_PACE_LIMITED) {
            n = GL_UI_NOTE_PACE;
        } else if (in->solve_status != (uint8_t)GL_SOLVE_OK) {
            n = GL_UI_NOTE_APPROX; /* a kept near miss of the patch solve */
        } else if (!in->fit_converged) {
            n = GL_UI_NOTE_FIT;
        } else if (in->poor_horizon) {
            n = GL_UI_NOTE_HORIZON; /* method B2 only */
        } else {
            show = GL_UI_SHOW_NORMAL;
            if (in->one_camera) {
                n = GL_UI_NOTE_ONE_CAMERA;
            } else if (in->ambiguous) {
                n = GL_UI_NOTE_AMBIGUOUS;
            }
        }
    }
    if (note != NULL) {
        *note = n;
    }
    return show;
}

gl_ui_show_t gl_ui_view_show(const gl_ui_view_t *v)
{
    if (!v->solved || v->show >= (uint8_t)GL_UI_SHOW_NONE) {
        return GL_UI_SHOW_NONE;
    }
    if (v->show != (uint8_t)GL_UI_SHOW_NORMAL || !(v->distance_m > 0.0f) || !v->flag_found ||
        v->distance_assumed) {
        return GL_UI_SHOW_APPROX;
    }
    return GL_UI_SHOW_NORMAL;
}

uint32_t gl_ui_time_left_ms(const gl_ui_t *ui, uint32_t now_ms)
{
    uint32_t limit = gl_ui_timeout_ms((gl_ui_state_t)ui->state);
    uint32_t held = (uint32_t)(now_ms - ui->state_since_ms);
    if (limit == 0u || held >= limit) {
        return 0;
    }
    return limit - held;
}

/* ======================================================================= */
/* Screens                                                                  */
/* ======================================================================= */

#define CX 64

/* Text centred on (cx, y) with a white box behind it. */
static void label_(gl_gfx_t *g, int cx, int y, const char *s, int scale)
{
    int w = gl_gfx_text_width(s, scale);
    gl_gfx_rect(g, cx - w / 2 - 2, y - 2, w + 4, GL_FONT_H * scale + 4, GL_INK_WHITE);
    gl_gfx_text_centred(g, cx, y, s, scale, GL_INK_BLACK);
}

static void text_(gl_gfx_t *g, int y, const char *s, int scale)
{
    gl_gfx_text_centred(g, CX, y, s, scale, GL_INK_BLACK);
}

static void battery_small_(gl_gfx_t *g, const gl_ui_view_t *v, int y)
{
    gl_gfx_battery(g, CX - 9, y, (int)v->battery_pct);
}

const char *gl_ui_note_text(gl_ui_note_t note)
{
    static const char *const text[GL_UI_NOTE_COUNT] = {
        "", "2 LINES SEEN", "1 CAMERA", "POOR HORIZON", "FIT NOT DONE", "PACE LIMIT", "APPROX",
        "NO RANGE", "NO FLAG", "NOT SOLVED", "NO SOLUTION", "TOO STEEP"
    };
    return ((unsigned)note < (unsigned)GL_UI_NOTE_COUNT) ? text[note] : "";
}

int gl_ui_conf_boxes(float confidence)
{
    /* a confidence that is not a number shows as none */
    return gl_roundi(gl_clampf(confidence, 0.0f, 1.0f) * 5.0f);
}

/* "45S AGO", "12M AGO", "5H AGO", "3D AGO" (at most 7 characters). */
static void age_text_(uint32_t age_s, char *out, size_t cap)
{
    uint32_t n;
    const char *unit;

    if (age_s < 60u) {
        n = age_s;
        unit = "S AGO";
    } else if (age_s < 3600u) {
        n = age_s / 60u;
        unit = "M AGO";
    } else if (age_s < 48u * 3600u) {
        n = age_s / 3600u;
        unit = "H AGO";
    } else {
        n = age_s / 86400u;
        if (n > 99u) {
            n = 99u;
        }
        unit = "D AGO";
    }
    out[0] = '\0';
    gl_fmt_int(out, cap, (int32_t)n);
    gl_fmt_append(out, cap, unit);
}

void gl_ui_result_text(const gl_ui_t *ui, const gl_ui_view_t *v, gl_ui_result_text_t *t)
{
    const gl_ui_show_t show = gl_ui_view_show(v);
    size_t n;

    memset(t, 0, sizeof(*t));
    if (!v->have_result) {
        return;
    }
    /* distance to the hole in the selected unit; "?" = dialled or assumed */
    if (v->distance_m > 0.0f) {
        gl_settings_format_distance(&ui->edit, v->distance_m, t->distance, sizeof(t->distance) - 1u);
        if (v->distance_assumed) {
            gl_fmt_append(t->distance, sizeof(t->distance), "?");
        }
    } else {
        gl_fmt_append(t->distance, sizeof(t->distance), "--");
    }
    /* plays-like distance: only for a solved putt (it is the launch speed) */
    if (show != GL_UI_SHOW_NONE && v->plays_like_m > 0.0f) {
        gl_fmt_append(t->plays, sizeof(t->plays), "PLAYS ");
        n = strlen(t->plays);
        gl_settings_format_distance(&ui->edit, v->plays_like_m, t->plays + n,
                                    sizeof(t->plays) - n - 1u);
        if (v->plays_uncertain) {
            /* the base of the stick was hidden: the height of the hole, and
             * with it the pace, is only bounded */
            gl_fmt_append(t->plays, sizeof(t->plays), "?");
        }
    }
    /* the one plain message.  NONE: it IS the screen (never empty).  APPROX:
     * the word APPROX stands where the confidence bar would be, so a note
     * that says no more than that is not repeated */
    if (show == GL_UI_SHOW_NONE) {
        const bool own = (v->note == (uint8_t)GL_UI_NOTE_NOT_SOLVED ||
                          v->note == (uint8_t)GL_UI_NOTE_TOO_STEEP);
        gl_fmt_append(t->note, sizeof(t->note),
                      gl_ui_note_text(own ? (gl_ui_note_t)v->note : GL_UI_NOTE_NO_SOLUTION));
    } else if (!(show == GL_UI_SHOW_APPROX && v->note == (uint8_t)GL_UI_NOTE_APPROX)) {
        gl_fmt_append(t->note, sizeof(t->note), gl_ui_note_text((gl_ui_note_t)v->note));
    }
    gl_fmt_fixed(t->slope, sizeof(t->slope), v->slope_pct, 1);
    gl_fmt_append(t->slope, sizeof(t->slope), "%");
    /* break in cup widths, with the side to aim at; none without a solution */
    if (show == GL_UI_SHOW_NONE) {
        t->brk[0] = '\0';
    } else if (!(v->distance_m > 0.0f)) {
        /* (the break in cups is distance x tan(aim): unknown without a distance) */
        gl_fmt_append(t->brk, sizeof(t->brk), "BREAK ?");
    } else if (fabsf(v->break_cups) < 0.05f) {
        gl_fmt_append(t->brk, sizeof(t->brk), "STRAIGHT");
    } else {
        gl_fmt_append(t->brk, sizeof(t->brk), (v->break_cups > 0.0f) ? "<" : "");
        n = strlen(t->brk);
        gl_fmt_fixed(t->brk + n, sizeof(t->brk) - n, fabsf(v->break_cups), 1);
        gl_fmt_append(t->brk, sizeof(t->brk), (v->break_cups > 0.0f) ? " CUP" : " CUP>");
    }
    if (v->drop > 0u) {
        t->mode[0] = 'D';
        t->mode[1] = (char)('0' + (int)((v->drop <= 9u) ? v->drop : 9u));
        if (v->drops_used != 0u && v->drops_used < v->drop) {
            /* the golfer must be able to see that this "Survey result" is
             * made of fewer placements than were stopped at - of ONE, it is
             * a Quick Read (phase-3 review, application finding 3) */
            t->mode[2] = '/';
            t->mode[3] = (char)('0' + (int)v->drops_used);
        }
    } else if (v->precision) {
        t->mode[0] = '2';
        t->mode[1] = 'X';
    }
    if (v->zero_missing) {
        t->zero[0] = 'Z';
        t->zero[1] = '?';
    }
    if (show == GL_UI_SHOW_APPROX) {
        gl_fmt_append(t->state, sizeof(t->state), "APPROX");
    }
    if (v->recalled) {
        age_text_(v->age_s, t->age, sizeof(t->age));
    }
}

/* fall-line rose at (x, y): an arrow downhill, or a ring on a level green */
static void rose_(const gl_ui_view_t *v, gl_gfx_t *g, int x, int y)
{
    gl_gfx_disc(g, (float)x, (float)y, 12.0f, GL_INK_WHITE);
    if (v->slope_pct >= 0.15f) {
        float dx = -sinf(v->fall_line_rad), dy = -cosf(v->fall_line_rad);
        gl_gfx_arrow(g, (float)x - 8.0f * dx, (float)y - 8.0f * dy, v->fall_line_rad, 16.0f, 6.0f,
                     1.0f, GL_INK_BLACK);
    } else {
        gl_gfx_arc(g, (float)x, (float)y, 3.0f, 4.5f, 0.0f, 7.0f, GL_INK_BLACK);
    }
}

/*
 * The result screen in its three states (DESIGN_SPEC E33):
 *
 *   NORMAL   SOLID aim line; distance, plays-like, an optional message,
 *            fall-line rose with the slope, break, CONFIDENCE BAR
 *   APPROX   DASHED aim line; the same numbers; the reason as the message;
 *            the word APPROX where the confidence bar would be
 *   NONE     NO line, no break, no bar: the message in large letters
 *            ("NO SOLUTION", "NOT SOLVED", "TOO STEEP"), the distance and
 *            the slope with its rose (those were measured)
 *
 * They differ in three places of the frame buffer at once: the line
 * (solid / gaps / absent), the box at the bottom (five boxes / a word /
 * nothing) and, for NONE, the whole layout.
 */
static void screen_result_(const gl_ui_t *ui, const gl_ui_view_t *v, gl_gfx_t *g)
{
    const gl_ui_show_t show = gl_ui_view_show(v);
    gl_gfx_aim_info_t info;
    gl_ui_result_text_t t;
    int rose_x = 28;

    if (!v->have_result) {
        text_(g, 60, "NO READ", 1);
        return;
    }
    gl_ui_result_text(ui, v, &t);
    info.on_screen = false;
    info.offset_px = 0.0f;
    if (show == GL_UI_SHOW_NONE) {
        /* the message, in two lines of large letters (each has one space) */
        char line[16];
        const char *sp = strchr(t.note, ' ');
        size_t n1 = (sp != NULL) ? (size_t)(sp - t.note) : strlen(t.note);
        label_(g, CX, 12, t.distance, 1);
        if (n1 >= sizeof(line)) {
            n1 = sizeof(line) - 1u;
        }
        memcpy(line, t.note, n1);
        line[n1] = '\0';
        text_(g, 28, line, 2);
        if (sp != NULL) {
            text_(g, 46, sp + 1, 2);
        }
        rose_(v, g, 44, 82);
        gl_gfx_text(g, 62, 79, t.slope, 1, GL_INK_BLACK);
    } else {
        /* 1. the aim line: the backward extension of the start line through
         * the ball.  SOLID in the NORMAL state only; long dashes (TENTATIVE)
         * in the APPROX state: a fallback solution - an assumed or dialled
         * distance, the flag-out fallback (its direction hangs on how well
         * the golfer pointed the visor at the hole: 2 degrees off are 1.4
         * cups at 4.5 m), the secant plane, a kept near miss, a pace that
         * cannot be met, a slope too close to the critical one.
         * A line that would leave the aperture (aim more than about 13.5
         * degrees off the marker's axis) is drawn PARALLEL through the screen
         * centre in the same style: the direction is what the golfer copies.
         * E12: the line is turned by the stored rotation of the glass. */
        gl_gfx_aim_line_styled(g, v->aim_rad + v->display_rot_rad,
                               v->ball_az_rad + v->display_rot_rad, 3.0f,
                               show != GL_UI_SHOW_NORMAL, &info);
        /* 2. distance (top), 3. plays-like distance, 4. the message */
        label_(g, CX, 12, t.distance, 1);
        if (t.plays[0] != '\0') {
            label_(g, CX, 24, t.plays, 1);
        }
        if (t.note[0] != '\0') {
            label_(g, CX, 36, t.note, 1);
        }
        /* 5. fall-line rose on the side away from the aim line */
        rose_x = (info.on_screen && info.offset_px < -14.0f) ? 100 : 28;
        if (info.on_screen && fabsf(info.offset_px) <= 14.0f) {
            rose_x = (info.offset_px >= 0.0f) ? 28 : 100;
        }
        rose_(v, g, rose_x, 58);
        label_(g, rose_x, 74, t.slope, 1);
        /* 6. break in cup widths */
        label_(g, CX, 92, t.brk, 1);
        /* 7. NORMAL: the confidence bar.  APPROX: the word, in its place */
        gl_gfx_rect(g, CX - 20, 102, 41, 11, GL_INK_WHITE);
        if (show == GL_UI_SHOW_NORMAL) {
            gl_gfx_conf_bar(g, CX - 16, 105, gl_ui_conf_boxes(v->confidence), 5);
        } else {
            gl_gfx_text_centred(g, CX, 104, t.state, 1, GL_INK_BLACK);
        }
        if (!v->flag_found) {
            /* beside the message line, clear of the plays-like label above it */
            gl_gfx_rect(g, 92, 33, 13, 15, GL_INK_WHITE);
            gl_gfx_icon(g, 94, 35, GL_ICON_NOFLAG, GL_INK_BLACK);
        }
    }
    /* mode mark (Survey drop, Precision) and, for a recalled result, its age */
    if (t.zero[0] != '\0') {
        /* lower left, opposite the mode mark: out of the way of the line */
        label_(g, CX - 32, 104, t.zero, 1);
    }
    if (t.mode[0] != '\0') {
        label_(g, CX + 32, 104, t.mode, 1);
    }
    if (t.age[0] != '\0') {
        label_(g, CX, 114, t.age, 1);
    }
}

/* ---- the INFO item ------------------------------------------------------ */

static const uint8_t info_chars_[GL_UI_INFO_LINES] = { 12, 15, 17, 19, 19, 20, 19, 18, 17, 15 };

unsigned gl_ui_info_line_chars(unsigned line, int *x, int *y)
{
    unsigned n;
    if (line >= GL_UI_INFO_LINES) {
        return 0;
    }
    n = info_chars_[line];
    if (x != NULL) {
        *x = CX - ((int)n * GL_FONT_ADVANCE - 1) / 2;
    }
    if (y != NULL) {
        *y = 16 + 9 * (int)line;
    }
    return n;
}

unsigned gl_ui_info_page_chars(void)
{
    unsigned n = 0;
    for (unsigned i = 0; i < GL_UI_INFO_LINES; i++) {
        n += info_chars_[i];
    }
    return n;
}

/*
 * The layout engine of the text block, used for counting and for drawing:
 * walks `text`, calling `emit` (if not NULL) for every line of page `want`
 * (-1: none).  Returns the number of pages; *shown = characters of the text
 * consumed by the first GL_UI_INFO_TEXT_PAGES pages.
 */
static unsigned info_layout_(const char *text, int want, gl_gfx_t *g, size_t *shown)
{
    unsigned line = 0, page = 0;
    size_t pos = 0, shown_n = 0;
    const size_t len = (text != NULL) ? strlen(text) : 0u;

    while (pos < len) {
        int x = 0, y = 0;
        const unsigned cap = gl_ui_info_line_chars(line, &x, &y);
        size_t take = 0, next;
        char buf[GL_UI_INFO_LINE_MAX + 2u];

        /* as many characters as fit, up to a new line */
        while (take < cap && pos + take < len && text[pos + take] != '\n') {
            take++;
        }
        next = pos + take;
        if (next < len && text[next] == '\n') {
            next++; /* the new line is consumed with its line */
        } else {
            if (next < len && text[next] != ' ') {
                /* in the middle of a word: back to the last space, if there is one */
                size_t back = take;
                while (back > 0u && text[pos + back - 1u] != ' ') {
                    back--;
                }
                if (back > 0u) {
                    take = back;
                    next = pos + take;
                }
            }
            while (next < len && text[next] == ' ') {
                next++; /* spaces at a line break are dropped */
            }
        }
        if (next == pos) {
            next = pos + 1u; /* (cannot happen: a line holds 12 characters or more) */
        }
        if (g != NULL && (int)page == want) {
            size_t n = take;
            while (n > 0u && text[pos + n - 1u] == ' ') {
                n--;
            }
            memcpy(buf, &text[pos], n);
            buf[n] = '\0';
            (void)gl_gfx_text(g, x, y, buf, 1, GL_INK_BLACK);
        }
        pos = next;
        if (page < GL_UI_INFO_TEXT_PAGES) {
            shown_n = pos;
        }
        line++;
        if (line >= GL_UI_INFO_LINES && pos < len) {
            line = 0;
            page++;
        }
    }
    if (shown != NULL) {
        *shown = shown_n;
    }
    return (len > 0u) ? page + 1u : 0u;
}

unsigned gl_ui_info_fit(const char *text, size_t *shown)
{
    return info_layout_(text, -1, NULL, shown);
}

unsigned gl_ui_info_pages(const char *text)
{
    unsigned n = info_layout_(text, -1, NULL, NULL);
    if (n > GL_UI_INFO_TEXT_PAGES) {
        n = GL_UI_INFO_TEXT_PAGES;
    }
    return 1u + n;
}

static void screen_info_(const gl_ui_t *ui, const gl_ui_view_t *v, gl_gfx_t *g)
{
    const unsigned pages = gl_ui_info_pages(v->info_text);
    const unsigned page = (ui->dial_value > 0) ? (unsigned)ui->dial_value : 0u;
    char buf[20];

    /* page number, top */
    buf[0] = '\0';
    gl_fmt_int(buf, sizeof(buf), (int32_t)page + 1);
    gl_fmt_append(buf, sizeof(buf), "/");
    gl_fmt_int(buf + strlen(buf), sizeof(buf) - strlen(buf), (int32_t)pages);
    text_(g, 6, buf, 1);
    if (page == 0u || page >= pages) {
        /* what the product is, and which one this is */
        text_(g, 18, "GREENLINE", 1);
        text_(g, 30, "GL-1", 2);
        text_(g, 50, "PRACTICE DEVICE", 1);
        buf[0] = '\0';
        gl_fmt_append(buf, sizeof(buf), "HW ");
        buf[3] = (v->info_hw >= 'A' && v->info_hw <= 'Z') ? v->info_hw : '?';
        buf[4] = '\0';
        gl_fmt_append(buf, sizeof(buf), "  FW ");
        gl_fmt_int(buf + strlen(buf), sizeof(buf) - strlen(buf), (int32_t)(v->info_fw >> 8));
        gl_fmt_append(buf, sizeof(buf), ".");
        gl_fmt_int(buf + strlen(buf), sizeof(buf) - strlen(buf), (int32_t)(v->info_fw & 0xFFu));
        text_(g, 62, buf, 1);
        buf[0] = '\0';
        gl_fmt_append(buf, sizeof(buf), "SN ");
        gl_fmt_append(buf, sizeof(buf), (v->info_serial[0] != '\0') ? v->info_serial : "-------");
        text_(g, 74, buf, 1);
        text_(g, 90, (pages > 1u) ? "ROLL: MORE" : "FLAT = OK", 1);
    } else {
        (void)info_layout_(v->info_text, (int)page - 1, g, NULL);
    }
}

static void screen_settings_(const gl_ui_t *ui, const gl_ui_view_t *v, gl_gfx_t *g)
{
    char buf[16];
    if (ui->item == GL_UI_ITEM_INFO) {
        screen_info_(ui, v, g);
    } else if (ui->item >= GL_UI_ITEM_ZERO) {
        text_(g, 24, "ZERO", 1);
        text_(g, 50, (ui->dial_value != 0) ? "YES" : "NO", 2);
    } else {
        text_(g, 24, gl_settings_item_name((gl_item_t)ui->item), 1);
        gl_settings_item_format(&ui->edit, (gl_item_t)ui->item, buf, sizeof(buf));
        if (ui->item == (uint8_t)GL_ITEM_STIMP) {
            int w = gl_gfx_big_number_width(buf, 28);
            gl_gfx_big_number(g, CX - w / 2, 40, buf, 28, GL_INK_BLACK);
        } else {
            text_(g, 50, buf, (gl_gfx_text_width(buf, 2) <= 100) ? 2 : 1);
        }
    }
    if (ui->item != GL_UI_ITEM_INFO) {
        text_(g, 82, "ROLL TO SET", 1);
    }
    if (ui->item == GL_UI_ITEM_INFO) {
        /* (the page says what rolling does; nothing is set here) */
    } else if (ui->dist_prompt) {
        /* asked because no flagstick was seen: say so, and that putting the
         * marker down again (flagstick in view now) reads again */
        text_(g, 10, "NO FLAG", 1);
        text_(g, 94, "OR PLACE AGAIN", 1);
    } else {
        text_(g, 94, "FLAT = OK", 1);
    }
    /* position within the menu */
    for (unsigned i = 0; i < GL_UI_ITEM_COUNT; i++) {
        int x = CX - (int)GL_UI_ITEM_COUNT * 3 + (int)i * 6;
        if (i == ui->item) {
            gl_gfx_rect(g, x, 107, 4, 4, GL_INK_BLACK);
        } else {
            gl_gfx_rect(g, x + 1, 108, 2, 2, GL_INK_BLACK);
        }
    }
}

/* Why the charge is not running, for the two cradle screens ("" = it runs,
 * or nothing stops it). */
static const char *chg_text_(const gl_ui_view_t *v)
{
    switch (v->chg_blocked) {
    case 1u: return "TOO COLD";
    case 2u: return "TOO HOT";
    case 3u: return "TEMP SENSOR";
    case 4u: return "TIME LIMIT";
    case 5u: return "CHARGE OFF";
    case 6u: return "NOT CHARGING";
    case 7u: return "CHARGER WAITS";
    default: return "";
    }
}

void gl_ui_render(const gl_ui_t *ui, const gl_ui_view_t *v, gl_gfx_t *g)
{
    char buf[16];

    gl_gfx_set_clip(g, true);
    gl_gfx_clear(g, GL_INK_WHITE);
    switch ((gl_ui_state_t)ui->state) {
    case GL_UI_SLEEP:
        break; /* blank: the display is off */
    case GL_UI_WAKE:
        text_(g, 46, "GREENLINE", 1);
        text_(g, 60, "GL-1", 2);
        battery_small_(g, v, 86);
        break;
    case GL_UI_WAIT_STILL:
        text_(g, 38, "HOLD", 2);
        text_(g, 58, "STILL", 2);
        battery_small_(g, v, 86);
        break;
    case GL_UI_READ_TILT:
        text_(g, 44, "LEVEL", 2);
        text_(g, 68, (ui->read_kind == (uint8_t)GL_READ_PRECISION) ? "RE-READING" : "READING", 1);
        break;
    case GL_UI_CAPTURE:
        gl_gfx_icon(g, CX - 4, 32, GL_ICON_FLAG, GL_INK_BLACK);
        text_(g, 50, "FLAG", 2);
        text_(g, 72, "LOOKING", 1);
        break;
    case GL_UI_SOLVE:
        text_(g, 52, "SOLVE", 2);
        break;
    case GL_UI_SHOW_RESULT:
        if (v->have_result && fabsf(v->ball_az_rad) > 0.5f * GL_PI_F) {
            /* The marker faces away from the hole (the half turn of a
             * Precision Read): the golfer behind the ball looks at the
             * screen from its "top".  Draw what a marker facing the hole
             * would show - every angle referred to the opposite direction -
             * and turn the picture round: line and fall-line arrow lie
             * where they did, text and the '<' / '>' of the break are the
             * right way up and on the right side FOR HIM. */
            gl_ui_view_t t = *v;
            t.aim_rad = gl_wrap_pi(v->aim_rad - GL_PI_F);
            t.fall_line_rad = gl_wrap_pi(v->fall_line_rad - GL_PI_F);
            t.ball_az_rad = gl_wrap_pi(v->ball_az_rad - GL_PI_F);
            screen_result_(ui, &t, g);
            gl_gfx_rotate_180(g);
        } else {
            screen_result_(ui, v, g);
        }
        break;
    case GL_UI_PRECISION_WAIT_SPIN:
        /* three-quarter ring with an arrow head: "turn me round" */
        gl_gfx_arc(g, 64.0f, 48.0f, 15.0f, 18.5f, 0.6f, 5.4f, GL_INK_BLACK);
        gl_gfx_triangle(g, 64.0f - 16.75f * sinf(0.6f) - 7.0f, 48.0f - 16.75f * cosf(0.6f) - 5.0f,
                        64.0f - 16.75f * sinf(0.6f) - 7.0f, 48.0f - 16.75f * cosf(0.6f) + 7.0f,
                        64.0f - 16.75f * sinf(0.6f) + 6.0f, 48.0f - 16.75f * cosf(0.6f) - 1.0f,
                        GL_INK_BLACK);
        text_(g, 76, "SPIN 180", 1);
        text_(g, 90, "TAP-TAP:SURVEY", 1);
        break;
    case GL_UI_SURVEY_NEXT_DROP:
        text_(g, 30, "SURVEY", 2);
        buf[0] = '\0';
        gl_fmt_append(buf, sizeof(buf), "DROP ");
        gl_fmt_int(buf + 5, sizeof(buf) - 5, (int32_t)ui->survey_count + 1);
        gl_fmt_append(buf, sizeof(buf), " OF 4");
        text_(g, 56, buf, 1);
        text_(g, 70, "MOVE AND PLACE", 1);
        text_(g, 82, "END AT THE BALL", 1);
        text_(g, 96, "TAP-TAP: QUIT", 1);
        break;
    case GL_UI_SETTINGS_DIAL:
        screen_settings_(ui, v, g);
        break;
    case GL_UI_CRADLE_USB:
        gl_gfx_icon(g, CX - 4, 22, GL_ICON_USB, GL_INK_BLACK);
        text_(g, 40, "USB", 2);
        gl_gfx_battery(g, CX - 14, 66, (int)v->battery_pct);
        if (v->charging) {
            gl_gfx_icon(g, CX + 10, 67, GL_ICON_BOLT, GL_INK_BLACK);
        }
        buf[0] = '\0';
        gl_fmt_int(buf, sizeof(buf), (int32_t)v->battery_pct);
        gl_fmt_append(buf, sizeof(buf), "%");
        text_(g, 82, buf, 1);
        /* a charge that does not run says why */
        if (v->chg_blocked != 0u) {
            text_(g, 96, chg_text_(v), 1);
        } else if (v->chg_full) {
            text_(g, 96, "FULL", 1);
        } else {
            text_(g, 96, v->usb_connected ? "LINKED" : "CHARGER", 1);
        }
        break;
    case GL_UI_CRADLE_SLEEP:
        /* E32: a STATIC picture - it is drawn when the state is entered and
         * again only when what it says changes; the MCU sleeps under it.
         * A large battery: with a bolt = charging, with a tick = full,
         * with a warning sign and the reason = not charging. */
        gl_gfx_frame(g, 36, 34, 52, 28, GL_INK_BLACK);
        gl_gfx_frame(g, 37, 35, 50, 26, GL_INK_BLACK);
        gl_gfx_rect(g, 88, 42, 4, 12, GL_INK_BLACK);
        if (v->chg_blocked != 0u) {
            gl_gfx_icon(g, CX - 5, 42, GL_ICON_WARN, GL_INK_BLACK);
            text_(g, 74, chg_text_(v), 1);
        } else if (v->chg_full) {
            gl_gfx_rect(g, 40, 38, 44, 20, GL_INK_BLACK);
            gl_gfx_icon(g, CX - 4, 43, GL_ICON_CHECK, GL_INK_WHITE);
            text_(g, 74, "FULL", 2);
        } else if (v->charging) {
            gl_gfx_rect(g, 40, 38, 16, 20, GL_INK_BLACK);
            gl_gfx_icon(g, CX + 2, 42, GL_ICON_BOLT, GL_INK_BLACK);
            text_(g, 74, "CHARGING", 1);
        } else {
            text_(g, 74, "IN CRADLE", 1);
        }
        break;
    case GL_UI_TOO_HOT:
        /* E13: a thermometer, and the words */
        gl_gfx_frame(g, CX - 4, 18, 9, 24, GL_INK_BLACK);
        gl_gfx_rect(g, CX - 1, 24, 3, 20, GL_INK_BLACK);
        gl_gfx_disc(g, (float)CX, 46.0f, 7.0f, GL_INK_BLACK);
        text_(g, 60, "TOO HOT", 2);
        text_(g, 84, "NO READ", 1);
        text_(g, 96, "LET IT COOL", 1);
        break;
    case GL_UI_CAL_ZERO:
        /* zeroing: on a hard flat surface, never in the cradle */
        text_(g, 22, "ZEROING", 1);
        if (v->cal_step == 1u) {
            text_(g, 38, "TURN", 2);
            text_(g, 58, "180", 2);
        } else if (v->cal_step >= 3u) {
            gl_gfx_icon(g, CX - 4, 38, GL_ICON_CHECK, GL_INK_BLACK);
            text_(g, 54, "SAVED", 2);
        } else {
            text_(g, 38, "HOLD", 2);
            text_(g, 58, "STILL", 2);
        }
        if (v->cal_step < 3u) {
            text_(g, 80, "HARD FLAT SURFACE", 1);
            text_(g, 94, "TAP-TAP: QUIT", 1);
        }
        break;
    case GL_UI_ERROR:
        gl_gfx_icon(g, CX - 5, 26, GL_ICON_WARN, GL_INK_BLACK);
        text_(g, 44, "ERROR", 2);
        text_(g, 68, gl_status_name((gl_status_t)ui->error_code), 1);
        buf[0] = 'E';
        gl_fmt_int(buf + 1, sizeof(buf) - 1, (int32_t)ui->error_code);
        text_(g, 82, buf, 1);
        break;
    case GL_UI_LOW_BATT:
        gl_gfx_frame(g, 38, 42, 48, 24, GL_INK_BLACK);
        gl_gfx_frame(g, 39, 43, 46, 22, GL_INK_BLACK);
        gl_gfx_rect(g, 86, 49, 4, 10, GL_INK_BLACK);
        gl_gfx_rect(g, 42, 46, 6, 16, GL_INK_BLACK);
        text_(g, 78, "LOW BATTERY", 1);
        break;
    default:
        break;
    }
}
