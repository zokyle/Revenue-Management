/*
 * test_ui.c - the UI transition table (structure, reachability, scenario
 * walks, timeouts, random event fuzz) and the screens.
 */
#include <stdlib.h>

#include "gl_config.h"
#include "gl_test.h"
#include "gl_ui.h"

static gl_ui_t ui;
static gl_settings_t settings;
static uint32_t now;

static void fresh(void)
{
    gl_settings_defaults(&settings);
    now = 1000;
    gl_ui_init(&ui, &settings, now);
}

/* dispatch with a 10 ms step of the clock */
static uint32_t ev(gl_ui_event_t e, int32_t arg)
{
    now += 10;
    return gl_ui_dispatch(&ui, e, arg, now);
}

#define STATE_IS(s) GL_CHECK_EQ(ui.state, (s))

/* Walk SLEEP -> WAIT_STILL. */
static void wake_up(void)
{
    GL_CHECK(ev(GL_EV_MOTION, 0) & GL_ACT_DISPLAY_ON);
    STATE_IS(GL_UI_WAKE);
    now += 900;
    GL_CHECK(gl_ui_tick(&ui, now) & GL_ACT_WATCH_STILL);
    STATE_IS(GL_UI_WAIT_STILL);
}

/* Walk WAIT_STILL -> SHOW_RESULT through a normal read. */
static void quick_read(void)
{
    GL_CHECK(ev(GL_EV_STILL, 0) & GL_ACT_START_TILT);
    STATE_IS(GL_UI_READ_TILT);
    GL_CHECK(ev(GL_EV_TILT_DONE, 0) & GL_ACT_START_CAPTURE);
    STATE_IS(GL_UI_CAPTURE);
    GL_CHECK(ev(GL_EV_CAPTURE_DONE, 0) & GL_ACT_START_SOLVE);
    STATE_IS(GL_UI_SOLVE);
    GL_CHECK(ev(GL_EV_SOLVE_DONE, 0) & GL_ACT_REDRAW);
    STATE_IS(GL_UI_SHOW_RESULT);
}

/* ---- structure of the table ------------------------------------------------ */

GL_TEST(test_table_is_well_formed)
{
    size_t n = 0;
    const gl_ui_transition_t *t = gl_ui_table(&n);
    GL_CHECK(n > 50);
    for (size_t i = 0; i < n; i++) {
        /* valid fields */
        GL_CHECK(t[i].state < GL_UI_STATE_COUNT || t[i].state == GL_UI_ANY);
        GL_CHECK(t[i].event > GL_EV_NONE && t[i].event < GL_EV_COUNT);
        GL_CHECK(t[i].next < GL_UI_STATE_COUNT);
        GL_CHECK(t[i].guard <= GL_G_DIST_PROMPT_MOVED);
        /* no two rows with the same (state, event, guard): the table is
         * deterministic by construction, not by row order alone */
        for (size_t j = i + 1; j < n; j++) {
            GL_CHECK(!(t[i].state == t[j].state && t[i].event == t[j].event &&
                       t[i].guard == t[j].guard));
        }
        /* an unguarded row must be the LAST row of its (state, event): a row
         * after it could never fire */
        if (t[i].guard == GL_G_ALWAYS) {
            for (size_t j = i + 1; j < n; j++) {
                GL_CHECK(!(t[i].state == t[j].state && t[i].event == t[j].event));
            }
        }
        /* going to sleep always tells the application to sleep */
        if (t[i].next == GL_UI_SLEEP && t[i].state != GL_UI_SLEEP) {
            GL_CHECK(t[i].actions & GL_ACT_ENTER_SLEEP);
        }
        /* leaving a measuring state other than by its own completion always
         * aborts the read (camera rail off) */
        if ((t[i].state == GL_UI_READ_TILT || t[i].state == GL_UI_CAPTURE) &&
            t[i].event != GL_EV_TILT_DONE && t[i].event != GL_EV_CAPTURE_DONE &&
            t[i].event != GL_EV_CAPTURE_NO_STICK) {
            GL_CHECK(t[i].actions & GL_ACT_ABORT_READ);
        }
        /* the wildcard rows that can interrupt a read abort it too */
        if (t[i].state == GL_UI_ANY) {
            GL_CHECK(t[i].actions & GL_ACT_ABORT_READ);
        }
        /* a capture is only ever started from READ_TILT */
        if (t[i].actions & GL_ACT_START_CAPTURE) {
            GL_CHECK_EQ(t[i].state, GL_UI_READ_TILT);
        }
    }
    /* every state with a time limit has a TIMEOUT row; the two without a
     * limit are SLEEP and CRADLE_USB */
    for (int s = 0; s < GL_UI_STATE_COUNT; s++) {
        bool has = false;
        for (size_t i = 0; i < n; i++) {
            if (t[i].state == s && t[i].event == GL_EV_TIMEOUT) {
                has = true;
            }
        }
        if (s == GL_UI_SLEEP || s == GL_UI_CRADLE_USB) {
            GL_CHECK_EQ(gl_ui_timeout_ms((gl_ui_state_t)s), 0);
            GL_CHECK(!has);
        } else {
            GL_CHECK(gl_ui_timeout_ms((gl_ui_state_t)s) > 0);
            GL_CHECK(has);
        }
        GL_CHECK(strcmp(gl_ui_state_name((gl_ui_state_t)s), "?") != 0);
    }
    for (int e = 0; e < GL_EV_COUNT; e++) {
        GL_CHECK(strcmp(gl_ui_event_name((gl_ui_event_t)e), "?") != 0);
    }
    GL_CHECK_EQ(gl_ui_timeout_ms(GL_UI_STATE_COUNT), 0);
}

GL_TEST(test_every_state_reachable_and_escapable)
{
    size_t n = 0;
    const gl_ui_transition_t *t = gl_ui_table(&n);
    bool reach[GL_UI_STATE_COUNT] = { false };
    bool to_sleep[GL_UI_STATE_COUNT] = { false };
    bool changed = true;

    /* forward closure from SLEEP (guards ignored: each is satisfiable) */
    reach[GL_UI_SLEEP] = true;
    while (changed) {
        changed = false;
        for (size_t i = 0; i < n; i++) {
            for (int s = 0; s < GL_UI_STATE_COUNT; s++) {
                if (reach[s] && (t[i].state == s || t[i].state == GL_UI_ANY) &&
                    !reach[t[i].next]) {
                    reach[t[i].next] = true;
                    changed = true;
                }
            }
        }
    }
    for (int s = 0; s < GL_UI_STATE_COUNT; s++) {
        GL_CHECK(reach[s]);
    }
    /* backward closure: from every state SLEEP can be reached using only
     * TIMEOUT and USB_DETACH events (i.e. without any help from the user) */
    to_sleep[GL_UI_SLEEP] = true;
    changed = true;
    while (changed) {
        changed = false;
        for (size_t i = 0; i < n; i++) {
            if ((t[i].event == GL_EV_TIMEOUT || t[i].event == GL_EV_USB_DETACH) &&
                t[i].state != GL_UI_ANY && to_sleep[t[i].next] && !to_sleep[t[i].state]) {
                to_sleep[t[i].state] = true;
                changed = true;
            }
        }
    }
    for (int s = 0; s < GL_UI_STATE_COUNT; s++) {
        GL_CHECK(to_sleep[s]);
    }
}

/* ---- scenario walks ---------------------------------------------------------- */

GL_TEST(test_quick_read)
{
    fresh();
    STATE_IS(GL_UI_SLEEP);
    /* nothing but motion and USB wakes it */
    GL_CHECK_EQ(ev(GL_EV_STILL, 0), 0);
    GL_CHECK_EQ(ev(GL_EV_DOUBLE_TAP, 0), 0);
    GL_CHECK_EQ(ev(GL_EV_BATT_LOW, 0), 0);
    STATE_IS(GL_UI_SLEEP);
    wake_up();
    quick_read();
    GL_CHECK_EQ(ui.read_kind, GL_READ_QUICK);
    /* picked up and put down elsewhere: a new read */
    {
        uint32_t a = ev(GL_EV_MOTION, 0);
        GL_CHECK(a & GL_ACT_NEW_READ);
        GL_CHECK(a & GL_ACT_WATCH_STILL);
        STATE_IS(GL_UI_WAIT_STILL);
    }
    quick_read();
    /* left alone: sleeps after 45 s */
    now += 44000;
    GL_CHECK_EQ(gl_ui_tick(&ui, now), 0);
    STATE_IS(GL_UI_SHOW_RESULT);
    now += 1100;
    GL_CHECK(gl_ui_tick(&ui, now) & GL_ACT_ENTER_SLEEP);
    STATE_IS(GL_UI_SLEEP);
    GL_CHECK_EQ(gl_ui_tick(&ui, now + 1000000u), 0); /* sleep has no timeout */
}

GL_TEST(test_read_interrupted)
{
    fresh();
    wake_up();
    /* moved during the tilt average */
    ev(GL_EV_STILL, 0);
    STATE_IS(GL_UI_READ_TILT);
    {
        uint32_t a = ev(GL_EV_MOTION, 0);
        GL_CHECK(a & GL_ACT_ABORT_READ);
        STATE_IS(GL_UI_WAIT_STILL);
    }
    /* the averager itself reports motion */
    ev(GL_EV_STILL, 0);
    GL_CHECK(ev(GL_EV_TILT_FAIL, 0) & GL_ACT_ABORT_READ);
    STATE_IS(GL_UI_WAIT_STILL);
    /* moved during the capture: the camera rail must go off */
    ev(GL_EV_STILL, 0);
    ev(GL_EV_TILT_DONE, 0);
    STATE_IS(GL_UI_CAPTURE);
    GL_CHECK(ev(GL_EV_MOTION, 0) & GL_ACT_ABORT_READ);
    STATE_IS(GL_UI_WAIT_STILL);
    /* camera never answers */
    ev(GL_EV_STILL, 0);
    ev(GL_EV_TILT_DONE, 0);
    now += 8100;
    GL_CHECK(gl_ui_tick(&ui, now) & GL_ACT_ABORT_READ);
    STATE_IS(GL_UI_ERROR);
    GL_CHECK_EQ(ui.error_code, GL_ERR_TIMEOUT);
    /* double tap acknowledges the error */
    GL_CHECK(ev(GL_EV_DOUBLE_TAP, 0) & GL_ACT_WATCH_STILL);
    STATE_IS(GL_UI_WAIT_STILL);
    /* camera error */
    ev(GL_EV_STILL, 0);
    ev(GL_EV_TILT_DONE, 0);
    GL_CHECK(ev(GL_EV_CAPTURE_FAIL, 0) & GL_ACT_ABORT_READ);
    STATE_IS(GL_UI_ERROR);
    GL_CHECK_EQ(ui.error_code, GL_ERR_IO);
    /* the error screen goes to sleep by itself */
    now += 5100;
    GL_CHECK(gl_ui_tick(&ui, now) & GL_ACT_ENTER_SLEEP);
    STATE_IS(GL_UI_SLEEP);
    /* solver failure carries its status code */
    wake_up();
    ev(GL_EV_STILL, 0);
    ev(GL_EV_TILT_DONE, 0);
    ev(GL_EV_CAPTURE_DONE, 0);
    ev(GL_EV_SOLVE_FAIL, GL_ERR_RANGE);
    STATE_IS(GL_UI_ERROR);
    GL_CHECK_EQ(ui.error_code, GL_ERR_RANGE);
    /* nobody places the marker: back to sleep after 20 s */
    fresh();
    wake_up();
    now += 20100;
    GL_CHECK(gl_ui_tick(&ui, now) & GL_ACT_ENTER_SLEEP);
    STATE_IS(GL_UI_SLEEP);
}

GL_TEST(test_precision_read)
{
    uint32_t a;
    fresh();
    wake_up();
    quick_read();
    /* double tap: prompt for the spin */
    GL_CHECK(ev(GL_EV_DOUBLE_TAP, 0) & GL_ACT_ARM_SPIN);
    STATE_IS(GL_UI_PRECISION_WAIT_SPIN);
    /* motion while spinning is expected and ignored */
    GL_CHECK_EQ(ev(GL_EV_MOTION, 0), 0);
    GL_CHECK_EQ(ev(GL_EV_STILL, 0), 0);
    STATE_IS(GL_UI_PRECISION_WAIT_SPIN);
    /* half turn done: tilt re-read, NO capture (the cameras face away) */
    GL_CHECK(ev(GL_EV_SPIN_DONE, 0) & GL_ACT_START_TILT);
    STATE_IS(GL_UI_READ_TILT);
    GL_CHECK_EQ(ui.read_kind, GL_READ_PRECISION);
    {
        a = ev(GL_EV_TILT_DONE, 0);
        GL_CHECK(a & GL_ACT_PRECISION);
        GL_CHECK(a & GL_ACT_START_SOLVE);
        GL_CHECK(!(a & GL_ACT_START_CAPTURE));
        STATE_IS(GL_UI_SOLVE);
    }
    ev(GL_EV_SOLVE_DONE, 0);
    STATE_IS(GL_UI_SHOW_RESULT);
    /* the next placement is an ordinary quick read again */
    ev(GL_EV_MOTION, 0);
    GL_CHECK_EQ(ui.read_kind, GL_READ_QUICK);
    ev(GL_EV_STILL, 0);
    GL_CHECK(ev(GL_EV_TILT_DONE, 0) & GL_ACT_START_CAPTURE);

    /* no spin within 20 s: the quick result stays, and the application is
     * told that the spin was given up (it stops integrating and redraws the
     * single read for where the marker faces now) */
    fresh();
    wake_up();
    quick_read();
    ev(GL_EV_DOUBLE_TAP, 0);
    now += 20100;
    a = gl_ui_tick(&ui, now);
    GL_CHECK(a & GL_ACT_REDRAW);
    GL_CHECK(a & GL_ACT_SPIN_ABANDON);
    STATE_IS(GL_UI_SHOW_RESULT);

    /* Review finding: a re-read DISTURBED by motion used to go to WAIT_STILL
     * and re-read from there, to be combined with the spin angle measured
     * before the disturbance.  It now goes back to the spin prompt WITHOUT
     * re-arming the integrator: only a marker that comes to rest at a half
     * turn again (a new SPIN_DONE) is re-read. */
    ev(GL_EV_DOUBLE_TAP, 0);
    STATE_IS(GL_UI_PRECISION_WAIT_SPIN);
    ev(GL_EV_SPIN_DONE, 0);
    STATE_IS(GL_UI_READ_TILT);
    a = ev(GL_EV_MOTION, 0);
    STATE_IS(GL_UI_PRECISION_WAIT_SPIN);
    GL_CHECK(a & GL_ACT_ABORT_READ);
    GL_CHECK(!(a & GL_ACT_ARM_SPIN));     /* the angle keeps accumulating */
    GL_CHECK(!(a & GL_ACT_WATCH_STILL));  /* stillness alone must not start a read */
    GL_CHECK_EQ(ev(GL_EV_STILL, 0), 0u);
    STATE_IS(GL_UI_PRECISION_WAIT_SPIN);
    GL_CHECK(ev(GL_EV_SPIN_DONE, 0) & GL_ACT_START_TILT);
    STATE_IS(GL_UI_READ_TILT);
    GL_CHECK_EQ(ui.read_kind, GL_READ_PRECISION);
    /* the same for a failed average */
    a = ev(GL_EV_TILT_FAIL, 0);
    STATE_IS(GL_UI_PRECISION_WAIT_SPIN);
    GL_CHECK(!(a & GL_ACT_ARM_SPIN));
    ev(GL_EV_SPIN_DONE, 0);
    GL_CHECK(ev(GL_EV_TILT_DONE, 0) & GL_ACT_PRECISION);
    STATE_IS(GL_UI_SOLVE);
    /* a marker that never comes to rest at a half turn again: the prompt
     * times out to the single result */
    fresh();
    wake_up();
    quick_read();
    ev(GL_EV_DOUBLE_TAP, 0);
    ev(GL_EV_SPIN_DONE, 0);
    ev(GL_EV_MOTION, 0);
    STATE_IS(GL_UI_PRECISION_WAIT_SPIN);
    now += 20100;
    GL_CHECK(gl_ui_tick(&ui, now) & GL_ACT_SPIN_ABANDON);
    STATE_IS(GL_UI_SHOW_RESULT);
    /* an ordinary (non-precision) read disturbed by motion still goes to
     * WAIT_STILL */
    ev(GL_EV_MOTION, 0);
    STATE_IS(GL_UI_WAIT_STILL);
    ev(GL_EV_STILL, 0);
    a = ev(GL_EV_MOTION, 0);
    STATE_IS(GL_UI_WAIT_STILL);
    GL_CHECK(a & GL_ACT_WATCH_STILL);
}

GL_TEST(test_survey)
{
    uint32_t a;
    fresh();
    wake_up();
    quick_read();
    /* double tap twice: precision prompt, then survey; the shown read is drop 1 */
    ev(GL_EV_DOUBLE_TAP, 0);
    a = ev(GL_EV_DOUBLE_TAP, 0);
    GL_CHECK(a & GL_ACT_SURVEY_STORE);
    STATE_IS(GL_UI_SURVEY_NEXT_DROP);
    GL_CHECK_EQ(ui.survey_count, 1);
    /* still lying where it was: must NOT read the same spot again */
    GL_CHECK_EQ(ev(GL_EV_STILL, 0), 0);
    STATE_IS(GL_UI_SURVEY_NEXT_DROP);
    /* moved, then still: drops 2, 3, 4 */
    for (int drop = 2; drop <= 4; drop++) {
        if (drop == 2) {
            ev(GL_EV_MOTION, 0);
        }
        STATE_IS(GL_UI_SURVEY_NEXT_DROP);
        GL_CHECK(ev(GL_EV_STILL, 0) & GL_ACT_START_TILT);
        GL_CHECK_EQ(ui.read_kind, GL_READ_SURVEY);
        GL_CHECK(ev(GL_EV_TILT_DONE, 0) & GL_ACT_START_CAPTURE);
        a = ev(GL_EV_CAPTURE_DONE, 0);
        GL_CHECK(a & GL_ACT_SURVEY_STORE);
        GL_CHECK(a & GL_ACT_START_SOLVE);
        GL_CHECK_EQ(ui.survey_count, drop);
        ev(GL_EV_SOLVE_DONE, 0);
        STATE_IS(GL_UI_SHOW_RESULT);
        if (drop < 4) {
            /* picked up for the next drop */
            a = ev(GL_EV_MOTION, 0);
            GL_CHECK(!(a & GL_ACT_NEW_READ));
            STATE_IS(GL_UI_SURVEY_NEXT_DROP);
        }
    }
    /* four drops stored: the next placement starts afresh */
    a = ev(GL_EV_MOTION, 0);
    GL_CHECK(a & GL_ACT_SURVEY_RESET);
    GL_CHECK(a & GL_ACT_NEW_READ);
    STATE_IS(GL_UI_WAIT_STILL);
    GL_CHECK_EQ(ui.survey_count, 0);

    /* ending a survey early with a double tap */
    fresh();
    wake_up();
    quick_read();
    ev(GL_EV_DOUBLE_TAP, 0);
    ev(GL_EV_DOUBLE_TAP, 0);
    ev(GL_EV_MOTION, 0);
    ev(GL_EV_STILL, 0);
    ev(GL_EV_TILT_DONE, 0);
    ev(GL_EV_CAPTURE_DONE, 0);
    ev(GL_EV_SOLVE_DONE, 0);
    GL_CHECK_EQ(ui.survey_count, 2);
    a = ev(GL_EV_DOUBLE_TAP, 0);
    GL_CHECK(a & GL_ACT_SURVEY_RESET);
    STATE_IS(GL_UI_SHOW_RESULT);
    GL_CHECK_EQ(ui.survey_count, 0);
    /* ... after which a double tap means "precision" again */
    ev(GL_EV_DOUBLE_TAP, 0);
    STATE_IS(GL_UI_PRECISION_WAIT_SPIN);

    /* abandoning a survey: 60 s without a placement */
    ev(GL_EV_DOUBLE_TAP, 0);
    STATE_IS(GL_UI_SURVEY_NEXT_DROP);
    now += 60100;
    a = gl_ui_tick(&ui, now);
    GL_CHECK(a & GL_ACT_SURVEY_RESET);
    GL_CHECK(a & GL_ACT_ENTER_SLEEP);
    STATE_IS(GL_UI_SLEEP);
    GL_CHECK_EQ(ui.survey_count, 0);
}

GL_TEST(test_flag_out_fallback)
{
    uint32_t a;
    fresh();
    wake_up();
    ev(GL_EV_STILL, 0);
    ev(GL_EV_TILT_DONE, 0);
    /* no flag and no distance known: ask for it */
    a = ev(GL_EV_CAPTURE_NO_STICK, 0);
    GL_CHECK(a & GL_ACT_DIAL_BEGIN);
    STATE_IS(GL_UI_SETTINGS_DIAL);
    GL_CHECK_EQ(ui.item, GL_ITEM_DISTANCE);
    GL_CHECK_EQ(ui.dial_value, 0);
    /* dial 24 half-feet = 12 ft */
    ev(GL_EV_DIAL_STEP, 24);
    GL_CHECK_EQ(ui.dial_value, 24);
    GL_CHECK_NEAR(gl_settings_manual_distance_m(&ui.edit), 12.0 * 0.3048, 0.01);
    a = ev(GL_EV_FLAT, 0);
    GL_CHECK(a & GL_ACT_SAVE_SETTINGS);
    STATE_IS(GL_UI_WAIT_STILL);
    /* re-placed pointing at the hole: this time the read goes through */
    ev(GL_EV_STILL, 0);
    ev(GL_EV_TILT_DONE, 0);
    a = ev(GL_EV_CAPTURE_NO_STICK, 0);
    GL_CHECK(a & GL_ACT_START_SOLVE);
    STATE_IS(GL_UI_SOLVE);
    ev(GL_EV_SOLVE_DONE, 0);
    STATE_IS(GL_UI_SHOW_RESULT);
}

GL_TEST(test_settings_dial)
{
    uint32_t a;
    fresh();
    wake_up();
    /* held upright: the dial opens on STIMP at the current value */
    a = ev(GL_EV_UPRIGHT, 0);
    GL_CHECK(a & GL_ACT_DIAL_BEGIN);
    STATE_IS(GL_UI_SETTINGS_DIAL);
    GL_CHECK_EQ(ui.item, GL_ITEM_STIMP);
    GL_CHECK_EQ(ui.dial_value, 20);
    ev(GL_EV_DIAL_STEP, 23);
    GL_CHECK_EQ(ui.edit.stimp_x2, 23);
    ev(GL_EV_DIAL_STEP, 99); /* clamped to Stimp 14 */
    GL_CHECK_EQ(ui.edit.stimp_x2, 28);
    GL_CHECK_EQ(ui.dial_value, 28);
    ev(GL_EV_DIAL_STEP, 21);
    /* double tap steps through the items, wrapping round */
    {
        const uint8_t order[] = { GL_ITEM_UNITS, GL_ITEM_PACE, GL_ITEM_GRASS, GL_ITEM_GRAIN,
                                  GL_ITEM_DISTANCE, GL_ITEM_RAWLOG, GL_ITEM_METHOD, GL_UI_ITEM_ZERO,
                                  GL_ITEM_STIMP, GL_ITEM_UNITS, GL_ITEM_PACE, GL_ITEM_GRASS };
        for (size_t i = 0; i < sizeof(order); i++) {
            a = ev(GL_EV_DOUBLE_TAP, 0);
            GL_CHECK(a & GL_ACT_DIAL_BEGIN);
            GL_CHECK_EQ(ui.item, order[i]);
        }
    }
    GL_CHECK_EQ(ui.dial_value, GL_GRASS_BENT);
    ev(GL_EV_DIAL_STEP, GL_GRASS_BERMUDA);
    ev(GL_EV_DOUBLE_TAP, 0); /* GRAIN: off by default */
    GL_CHECK_EQ(ui.dial_value, 0);
    ev(GL_EV_DIAL_STEP, 1);
    GL_CHECK_EQ(ui.edit.grain_enable, 1);
    /* laid flat: saved */
    a = ev(GL_EV_FLAT, 0);
    GL_CHECK(a & GL_ACT_SAVE_SETTINGS);
    STATE_IS(GL_UI_WAIT_STILL);
    GL_CHECK_EQ(ui.edit.stimp_x2, 21);
    GL_CHECK_EQ(ui.edit.grass, GL_GRASS_BERMUDA);
    GL_CHECK_EQ(ui.saved.grain_enable, 1);

    /* abandoned dial (30 s): edits are discarded */
    ev(GL_EV_UPRIGHT, 0);
    ev(GL_EV_DIAL_STEP, 14);
    GL_CHECK_EQ(ui.edit.stimp_x2, 14);
    now += 30100;
    a = gl_ui_tick(&ui, now);
    GL_CHECK(a & GL_ACT_ENTER_SLEEP);
    GL_CHECK(!(a & GL_ACT_SAVE_SETTINGS));
    STATE_IS(GL_UI_SLEEP);
    GL_CHECK_EQ(ui.edit.stimp_x2, 21);
    /* activity in the dial restarts its 30 s limit */
    wake_up();
    ev(GL_EV_UPRIGHT, 0);
    for (int i = 0; i < 5; i++) {
        now += 20000;
        GL_CHECK_EQ(gl_ui_tick(&ui, now), 0);
        ev(GL_EV_DIAL_STEP, 18 + i);
    }
    STATE_IS(GL_UI_SETTINGS_DIAL);
    /* zeroing from the menu */
    for (int i = 0; i < (int)GL_UI_ITEM_ZERO; i++) {
        ev(GL_EV_DOUBLE_TAP, 0);
    }
    GL_CHECK_EQ(ui.item, GL_UI_ITEM_ZERO);
    GL_CHECK_EQ(ui.dial_value, 0);
    ev(GL_EV_DIAL_STEP, 1);
    a = ev(GL_EV_FLAT, 0);
    GL_CHECK(a & GL_ACT_CAL_ZERO_START);
    GL_CHECK(a & GL_ACT_SAVE_SETTINGS);
    STATE_IS(GL_UI_CAL_ZERO);
    /* when done, back to normal use */
    a = ev(GL_EV_CAL_DONE, 0);
    GL_CHECK(a & GL_ACT_WATCH_STILL);
    STATE_IS(GL_UI_WAIT_STILL);
    /* with "NO" selected, laying flat just leaves the menu */
    ev(GL_EV_UPRIGHT, 0);
    for (int i = 0; i < (int)GL_UI_ITEM_ZERO; i++) {
        ev(GL_EV_DOUBLE_TAP, 0);
    }
    a = ev(GL_EV_FLAT, 0);
    GL_CHECK(!(a & GL_ACT_CAL_ZERO_START));
    STATE_IS(GL_UI_WAIT_STILL);
}

/* SLEEP -> ... -> CAL_ZERO through the only way in: the dial item "ZERO". */
static void enter_zeroing(void)
{
    wake_up();
    ev(GL_EV_UPRIGHT, 0);
    for (int i = 0; i < (int)GL_UI_ITEM_ZERO; i++) {
        ev(GL_EV_DOUBLE_TAP, 0);
    }
    GL_CHECK_EQ(ui.item, GL_UI_ITEM_ZERO);
    ev(GL_EV_DIAL_STEP, 1);
    GL_CHECK(ev(GL_EV_FLAT, 0) & GL_ACT_CAL_ZERO_START);
    STATE_IS(GL_UI_CAL_ZERO);
}

GL_TEST(test_usb_cradle)
{
    uint32_t a;
    /* attach while asleep */
    fresh();
    a = ev(GL_EV_USB_ATTACH, 0);
    GL_CHECK((a & GL_ACT_USB_START) && (a & GL_ACT_DISPLAY_ON));
    STATE_IS(GL_UI_CRADLE_USB);
    /* in the cradle nothing else disturbs it */
    GL_CHECK_EQ(ev(GL_EV_MOTION, 0), 0);
    GL_CHECK_EQ(ev(GL_EV_BATT_LOW, 0), 0);
    GL_CHECK_EQ(ev(GL_EV_DOUBLE_TAP, 0), 0);
    GL_CHECK_EQ(ev(GL_EV_UPRIGHT, 0), 0);
    GL_CHECK_EQ(ev(GL_EV_FLAT, 0), 0);
    GL_CHECK_EQ(ev(GL_EV_CAL_DONE, 0), 0);
    GL_CHECK_EQ(gl_ui_tick(&ui, now + 10000000u), 0);
    STATE_IS(GL_UI_CRADLE_USB);
    /* lifted out of the cradle */
    a = ev(GL_EV_USB_DETACH, 0);
    GL_CHECK((a & GL_ACT_USB_STOP) && (a & GL_ACT_ENTER_SLEEP));
    STATE_IS(GL_UI_SLEEP);

    /* attach in the middle of a capture: the read is aborted first */
    fresh();
    wake_up();
    ev(GL_EV_STILL, 0);
    ev(GL_EV_TILT_DONE, 0);
    STATE_IS(GL_UI_CAPTURE);
    a = ev(GL_EV_USB_ATTACH, 0);
    GL_CHECK((a & GL_ACT_ABORT_READ) && (a & GL_ACT_USB_START));
    STATE_IS(GL_UI_CRADLE_USB);

    /* Review finding: a fault in the cradle followed by a double tap used
     * to start a read with VBUS present; from there no state stopped USB
     * when the marker was lifted out, and the charge gate was no longer
     * serviced.  In the cradle a double tap on the error screen now goes
     * back to the cradle state ... */
    a = ev(GL_EV_FAULT, GL_ERR_IO);
    STATE_IS(GL_UI_ERROR);
    GL_CHECK(ui.usb);
    a = ev(GL_EV_DOUBLE_TAP, 0);
    STATE_IS(GL_UI_CRADLE_USB);
    GL_CHECK(!(a & GL_ACT_WATCH_STILL));
    /* ... out of the cradle it still starts a read */
    fresh();
    wake_up();
    ev(GL_EV_FAULT, GL_ERR_IO);
    STATE_IS(GL_UI_ERROR);
    a = ev(GL_EV_DOUBLE_TAP, 0);
    STATE_IS(GL_UI_WAIT_STILL);
    GL_CHECK(a & GL_ACT_WATCH_STILL);

    /* ... and EVERY state has an answer to USB_DETACH that stops USB: with
     * VBUS known present, no sequence of events leaves the UI in a state
     * from which a detach does not end in USB_STOP */
    {
        size_t n = 0;
        const gl_ui_transition_t *t = gl_ui_table(&n);
        for (unsigned st = 0; st < GL_UI_STATE_COUNT; st++) {
            bool found = false;
            for (int pass = 0; pass < 2 && !found; pass++) {
                for (size_t i = 0; i < n; i++) {
                    if (t[i].event == GL_EV_USB_DETACH &&
                        t[i].state == ((pass == 0) ? st : (unsigned)GL_UI_ANY)) {
                        GL_CHECK(t[i].actions & GL_ACT_USB_STOP);
                        GL_CHECK(t[i].guard == GL_G_ALWAYS);
                        found = true;
                        break;
                    }
                }
            }
            GL_CHECK(found);
        }
        /* walk every state with ui.usb set and detach */
        for (unsigned st = 0; st < GL_UI_STATE_COUNT; st++) {
            fresh();
            ui.state = (uint8_t)st;
            ui.usb = true;
            a = ev(GL_EV_USB_DETACH, 0);
            GL_CHECK(a & GL_ACT_USB_STOP);
            GL_CHECK(!ui.usb);
            GL_CHECK(ui.state == GL_UI_SLEEP || ui.state == GL_UI_ERROR);
            if (ui.state == GL_UI_SLEEP) {
                GL_CHECK(a & GL_ACT_ENTER_SLEEP);
            }
        }
    }
}

/* Rev C: zeroing is done on any hard flat surface, NEVER in the cradle (the
 * cradle takes the marker one way round only and holds it down). */
GL_TEST(test_zeroing_is_never_done_in_the_cradle)
{
    size_t n = 0;
    const gl_ui_transition_t *t = gl_ui_table(&n);
    uint32_t a;
    unsigned ways_in = 0;

    /* structure: the only row that starts the zeroing leaves the settings
     * dial; no row leads from the cradle state to it; no row lets it finish
     * into the cradle state */
    for (size_t i = 0; i < n; i++) {
        if (t[i].actions & GL_ACT_CAL_ZERO_START) {
            ways_in++;
            GL_CHECK_EQ(t[i].state, GL_UI_SETTINGS_DIAL);
            GL_CHECK_EQ(t[i].event, GL_EV_FLAT);
            GL_CHECK_EQ(t[i].guard, GL_G_ITEM_ZERO_YES);
            GL_CHECK_EQ(t[i].next, GL_UI_CAL_ZERO);
        }
        if (t[i].next == GL_UI_CAL_ZERO && t[i].state != GL_UI_CAL_ZERO) {
            GL_CHECK(t[i].actions & GL_ACT_CAL_ZERO_START);
        }
        if (t[i].state == GL_UI_CRADLE_USB) {
            GL_CHECK(t[i].next != GL_UI_CAL_ZERO);
            GL_CHECK(!(t[i].actions & GL_ACT_CAL_ZERO_START));
        }
        if (t[i].state == GL_UI_CAL_ZERO && t[i].next == GL_UI_CRADLE_USB) {
            GL_CHECK_EQ(t[i].event, GL_EV_USB_ATTACH);
            GL_CHECK(t[i].actions & GL_ACT_CAL_ABORT);
        }
        /* no guard on USB inside the zeroing state: it cannot be on USB */
        if (t[i].state == GL_UI_CAL_ZERO) {
            GL_CHECK(t[i].guard != GL_G_USB);
        }
    }
    GL_CHECK_EQ(ways_in, 1);

    /* the settings dial cannot be opened in the cradle, so the zeroing
     * cannot be started there */
    fresh();
    ev(GL_EV_USB_ATTACH, 0);
    ev(GL_EV_UPRIGHT, 0);
    STATE_IS(GL_UI_CRADLE_USB);

    /* normal course: the turn is expected motion and is ignored */
    fresh();
    enter_zeroing();
    GL_CHECK(!ui.usb);
    GL_CHECK_EQ(ev(GL_EV_MOTION, 0), 0);
    GL_CHECK_EQ(ev(GL_EV_STILL, 0), 0);
    GL_CHECK_EQ(ev(GL_EV_UPRIGHT, 0), 0);
    STATE_IS(GL_UI_CAL_ZERO);
    a = ev(GL_EV_CAL_DONE, 0);
    GL_CHECK((a & GL_ACT_WATCH_STILL) && (a & GL_ACT_NEW_READ));
    STATE_IS(GL_UI_WAIT_STILL);

    /* put into the cradle half way: abandoned, USB screen */
    fresh();
    enter_zeroing();
    a = ev(GL_EV_USB_ATTACH, 0);
    GL_CHECK((a & GL_ACT_CAL_ABORT) && (a & GL_ACT_USB_START));
    STATE_IS(GL_UI_CRADLE_USB);
    /* a late completion report changes nothing */
    GL_CHECK_EQ(ev(GL_EV_CAL_DONE, 0), 0);
    STATE_IS(GL_UI_CRADLE_USB);

    /* failed (moved during a read, turn not near 180 degrees) */
    fresh();
    enter_zeroing();
    a = ev(GL_EV_CAL_FAIL, GL_ERR_MOTION);
    GL_CHECK(a & GL_ACT_CAL_ABORT);
    STATE_IS(GL_UI_ERROR);
    GL_CHECK_EQ(ui.error_code, GL_ERR_MOTION);
    now += 5100;
    GL_CHECK(gl_ui_tick(&ui, now) & GL_ACT_ENTER_SLEEP);
    STATE_IS(GL_UI_SLEEP);

    /* abandoned by a double tap, and by the 2-minute limit */
    fresh();
    enter_zeroing();
    a = ev(GL_EV_DOUBLE_TAP, 0);
    GL_CHECK((a & GL_ACT_CAL_ABORT) && (a & GL_ACT_WATCH_STILL));
    STATE_IS(GL_UI_WAIT_STILL);
    fresh();
    enter_zeroing();
    now += 120100;
    a = gl_ui_tick(&ui, now);
    GL_CHECK(a & GL_ACT_CAL_ABORT);
    STATE_IS(GL_UI_ERROR);
    GL_CHECK_EQ(ui.error_code, GL_ERR_TIMEOUT);
}

GL_TEST(test_low_battery_and_faults_from_every_state)
{
    /* Drive the machine into each state in turn, then hit it with BATT_LOW,
     * FAULT and USB_ATTACH. */
    static const gl_ui_event_t paths[GL_UI_STATE_COUNT][8] = {
        /* SLEEP */ { GL_EV_NONE },
        /* WAKE */ { GL_EV_MOTION, GL_EV_NONE },
        /* WAIT_STILL */ { GL_EV_MOTION, GL_EV_TIMEOUT, GL_EV_NONE },
        /* READ_TILT */ { GL_EV_MOTION, GL_EV_TIMEOUT, GL_EV_STILL, GL_EV_NONE },
        /* CAPTURE */ { GL_EV_MOTION, GL_EV_TIMEOUT, GL_EV_STILL, GL_EV_TILT_DONE, GL_EV_NONE },
        /* SOLVE */ { GL_EV_MOTION, GL_EV_TIMEOUT, GL_EV_STILL, GL_EV_TILT_DONE,
                      GL_EV_CAPTURE_DONE, GL_EV_NONE },
        /* SHOW_RESULT */ { GL_EV_MOTION, GL_EV_TIMEOUT, GL_EV_STILL, GL_EV_TILT_DONE,
                            GL_EV_CAPTURE_DONE, GL_EV_SOLVE_DONE, GL_EV_NONE },
        /* PRECISION_WAIT_SPIN */ { GL_EV_MOTION, GL_EV_TIMEOUT, GL_EV_STILL, GL_EV_TILT_DONE,
                                    GL_EV_CAPTURE_DONE, GL_EV_SOLVE_DONE, GL_EV_DOUBLE_TAP,
                                    GL_EV_NONE },
        /* SURVEY_NEXT_DROP */ { GL_EV_MOTION, GL_EV_TIMEOUT, GL_EV_STILL, GL_EV_TILT_DONE,
                                 GL_EV_CAPTURE_DONE, GL_EV_SOLVE_DONE, GL_EV_DOUBLE_TAP,
                                 GL_EV_DOUBLE_TAP },
        /* SETTINGS_DIAL */ { GL_EV_MOTION, GL_EV_UPRIGHT, GL_EV_NONE },
        /* CRADLE_USB */ { GL_EV_USB_ATTACH, GL_EV_NONE },
        /* CAL_ZERO */ { GL_EV_NONE }, /* reached through enter_zeroing() */
        /* ERROR */ { GL_EV_MOTION, GL_EV_FAULT, GL_EV_NONE },
        /* LOW_BATT */ { GL_EV_MOTION, GL_EV_BATT_LOW, GL_EV_NONE },
    };
    for (int s = 0; s < GL_UI_STATE_COUNT; s++) {
        for (int hit = 0; hit < 3; hit++) {
            uint32_t a;
            fresh();
            if (s == GL_UI_CAL_ZERO) {
                enter_zeroing();
            }
            for (int i = 0; i < 8 && paths[s][i] != GL_EV_NONE; i++) {
                if (paths[s][i] == GL_EV_TIMEOUT) {
                    now += 900;
                    gl_ui_tick(&ui, now);
                } else {
                    ev(paths[s][i], GL_ERR_IO);
                }
            }
            STATE_IS(s);
            if (hit == 0) {
                a = ev(GL_EV_BATT_LOW, 0);
                if (s == GL_UI_SLEEP || s == GL_UI_CRADLE_USB || s == GL_UI_CAL_ZERO) {
                    STATE_IS(s); /* asleep, or powered / calibrating: no warning */
                } else {
                    STATE_IS(GL_UI_LOW_BATT);
                    if (s != GL_UI_LOW_BATT) {
                        GL_CHECK(a & GL_ACT_ABORT_READ);
                    }
                    /* the warning shows for 4 s, then the device sleeps */
                    now += 4100;
                    GL_CHECK(gl_ui_tick(&ui, now) & GL_ACT_ENTER_SLEEP);
                    STATE_IS(GL_UI_SLEEP);
                }
            } else if (hit == 1) {
                a = ev(GL_EV_FAULT, GL_ERR_CORRUPT);
                STATE_IS(GL_UI_ERROR);
                GL_CHECK_EQ(ui.error_code, GL_ERR_CORRUPT);
                if (s == GL_UI_SLEEP) {
                    GL_CHECK(a & GL_ACT_DISPLAY_ON);
                }
            } else {
                a = ev(GL_EV_USB_ATTACH, 0);
                /* from every state, also from the zeroing (which is abandoned) */
                STATE_IS(GL_UI_CRADLE_USB);
                if (s == GL_UI_CAL_ZERO) {
                    GL_CHECK(a & GL_ACT_CAL_ABORT);
                }
                if (s != GL_UI_CRADLE_USB) {
                    GL_CHECK(a & GL_ACT_USB_START);
                }
            }
        }
    }
}

GL_TEST(test_keepalive_extends_only_the_current_state)
{
    fresh();
    wake_up();
    ev(GL_EV_STILL, 0);
    ev(GL_EV_TILT_DONE, 0);
    STATE_IS(GL_UI_CAPTURE);
    /* 7 s into an 8 s limit: progress reported -> 8 s more, no transition */
    now += 7000;
    GL_CHECK_EQ(gl_ui_tick(&ui, now), 0);
    gl_ui_keepalive(&ui, now);
    STATE_IS(GL_UI_CAPTURE);
    GL_CHECK_EQ(gl_ui_time_left_ms(&ui, now), 8000u);
    now += 7900;
    GL_CHECK_EQ(gl_ui_tick(&ui, now), 0);
    STATE_IS(GL_UI_CAPTURE);
    /* without further reports the limit applies again */
    now += 200;
    GL_CHECK(gl_ui_tick(&ui, now) & GL_ACT_ABORT_READ);
    STATE_IS(GL_UI_ERROR);
}

GL_TEST(test_timeouts_and_tick_wraparound)
{
    /* the 32-bit millisecond clock wraps after 49.7 days */
    gl_settings_defaults(&settings);
    now = 0xFFFFFF00u;
    gl_ui_init(&ui, &settings, now);
    ev(GL_EV_MOTION, 0);
    STATE_IS(GL_UI_WAKE);
    now += 500; /* wraps past zero */
    GL_CHECK(now < 1000u);
    GL_CHECK_EQ(gl_ui_tick(&ui, now), 0);
    GL_CHECK(gl_ui_time_left_ms(&ui, now) > 0 && gl_ui_time_left_ms(&ui, now) <= 300);
    now += 400;
    GL_CHECK(gl_ui_tick(&ui, now) != 0);
    STATE_IS(GL_UI_WAIT_STILL);
    GL_CHECK_EQ(gl_ui_time_left_ms(&ui, now), 20000);
    GL_CHECK_EQ(gl_ui_time_left_ms(&ui, now + 30000), 0);
    /* ignored events do not extend a time limit */
    fresh();
    ev(GL_EV_MOTION, 0);
    ev(GL_EV_BATT_LOW, 0);
    STATE_IS(GL_UI_LOW_BATT);
    for (int i = 0; i < 9; i++) {
        now += 390;
        ev(GL_EV_BATT_LOW, 0); /* keeps arriving every 400 ms */
        gl_ui_tick(&ui, now);
    }
    STATE_IS(GL_UI_LOW_BATT); /* 3.6 s so far */
    now += 500;
    gl_ui_tick(&ui, now);
    STATE_IS(GL_UI_SLEEP);    /* 4 s after the warning first appeared */
}

/* Random events for a long time: the machine must stay in a valid state,
 * keep its invariants, and always find its way back to sleep. */
GL_TEST(test_random_event_fuzz)
{
    unsigned visits[GL_UI_STATE_COUNT] = { 0 };
    uint32_t seed = 0xC0FFEEu;
    bool camera_on = false;
    unsigned camera_violations = 0;
    fresh();
    for (int i = 0; i < 300000; i++) {
        uint32_t a;
        uint8_t before = ui.state;
        gl_ui_event_t e;
        seed = seed * 1664525u + 1013904223u;
        e = (gl_ui_event_t)(1 + (seed >> 8) % (GL_EV_COUNT - 2)); /* any event but TIMEOUT */
        if ((seed >> 28) < 10u) {
            /* most of the time pick an event that means something in the
             * current state, so that the deep states are reached often */
            size_t n_rows = 0;
            const gl_ui_transition_t *t = gl_ui_table(&n_rows);
            size_t k = (seed >> 4) % n_rows;
            for (size_t j = 0; j < n_rows; j++) {
                const gl_ui_transition_t *row = &t[(k + j) % n_rows];
                if (row->state == ui.state && row->event != GL_EV_TIMEOUT) {
                    e = (gl_ui_event_t)row->event;
                    break;
                }
            }
        }
        if (ui.state == GL_UI_SETTINGS_DIAL && ((seed >> 20) & 3u) != 0u) {
            /* the zeroing state lies behind seven double taps, a dial step
             * and laying the marker flat: steer toward it some of the time,
             * or a random walk hardly ever gets there */
            if (ui.item != GL_UI_ITEM_ZERO) {
                e = GL_EV_DOUBLE_TAP;
            } else {
                e = (ui.dial_value != 0) ? GL_EV_FLAT : GL_EV_DIAL_STEP;
            }
        }
        seed = seed * 1664525u + 1013904223u;
        now += (seed >> 20) % 700;
        a = gl_ui_dispatch(&ui, e, (int32_t)((seed >> 4) % 40), now);
        a |= gl_ui_tick(&ui, now);
        GL_CHECK(ui.state < GL_UI_STATE_COUNT);
        GL_CHECK(ui.survey_count <= 4);
        GL_CHECK(ui.item < GL_UI_ITEM_COUNT);
        GL_CHECK_EQ(gl_settings_validate(&ui.edit), GL_OK);
        visits[ui.state]++;
        /* model of the camera rail: on from START_CAPTURE until the capture
         * completes or anything aborts it; it must never stay on outside
         * the CAPTURE state */
        if (a & GL_ACT_START_CAPTURE) {
            camera_on = true;
        }
        if ((a & GL_ACT_ABORT_READ) ||
            (before == GL_UI_CAPTURE && ui.state != GL_UI_CAPTURE)) {
            if (before == GL_UI_CAPTURE && ui.state != GL_UI_CAPTURE &&
                !(a & (GL_ACT_ABORT_READ | GL_ACT_START_SOLVE | GL_ACT_DIAL_BEGIN))) {
                camera_violations++;
            }
            camera_on = false;
        }
        if (camera_on && ui.state != GL_UI_CAPTURE) {
            camera_violations++;
        }
    }
    GL_CHECK_EQ(camera_violations, 0);
    for (int s = 0; s < GL_UI_STATE_COUNT; s++) {
        GL_CHECK(visits[s] > 100); /* the fuzz reached every state */
    }
    printf("    fuzz: 300000 events; visits to CAL_ZERO %u, CRADLE_USB %u, SHOW_RESULT %u\n",
           visits[GL_UI_CAL_ZERO], visits[GL_UI_CRADLE_USB], visits[GL_UI_SHOW_RESULT]);
    /* from wherever it ended: with no more input it sleeps (unless on USB) */
    ev(GL_EV_USB_DETACH, 0);
    for (int i = 0; i < 20; i++) {
        now += 130000;
        gl_ui_tick(&ui, now);
    }
    STATE_IS(GL_UI_SLEEP);
}

/* ---- screens ------------------------------------------------------------------- */

static gl_gfx_t gfx;

static int inside_aperture(int x, int y)
{
    double r = 0.5 * (double)GL_CFG_LCD_CLIP_DIA_PX;
    for (int cy = -1; cy <= 1; cy += 2) {
        for (int cx = -1; cx <= 1; cx += 2) {
            double px = (double)x + 0.5 * cx - 63.5, py = (double)y + 0.5 * cy - 63.5;
            if (px * px + py * py > r * r + 1e-9) {
                return 0;
            }
        }
    }
    return 1;
}

static unsigned ink_outside(void)
{
    unsigned n = 0;
    for (int y = 0; y < GL_GFX_H; y++) {
        for (int x = 0; x < GL_GFX_W; x++) {
            if (!gl_gfx_get(&gfx, x, y) && !inside_aperture(x, y)) {
                n++;
            }
        }
    }
    return n;
}

static void view_default(gl_ui_view_t *v)
{
    memset(v, 0, sizeof(*v));
    v->have_result = true;
    v->solved = true;
    v->line_here = true;
    v->flag_found = true;
    v->aim_rad = 0.03f;
    v->distance_m = 4.4f;
    v->plays_like_m = 4.9f;
    v->slope_pct = 2.1f;
    v->fall_line_rad = 1.2f;
    v->break_cups = 2.5f;
    v->confidence = 0.7f;
    v->battery_pct = 80;
}

GL_TEST(test_every_screen_stays_in_the_aperture)
{
    gl_ui_view_t v;
    unsigned outside = 0;
    static uint8_t prev[GL_GFX_BYTES];
    gl_gfx_init(&gfx);
    view_default(&v);
    for (int s = 0; s < GL_UI_STATE_COUNT; s++) {
        fresh();
        ui.state = (uint8_t)s;
        ui.error_code = GL_ERR_NOT_IMPLEMENTED; /* the longest status name */
        gl_ui_render(&ui, &v, &gfx);
        outside += ink_outside();
        if (s == GL_UI_SLEEP) {
            GL_CHECK_EQ(gl_gfx_count_black(&gfx), 0);
        } else {
            GL_CHECK(gl_gfx_count_black(&gfx) > 150);
            /* every state has its own screen */
            GL_CHECK(memcmp(prev, gfx.px, sizeof(prev)) != 0);
        }
        memcpy(prev, gfx.px, sizeof(prev));
    }
    GL_CHECK_EQ(outside, 0);
    /* extreme view models on the result screen */
    fresh();
    ui.state = GL_UI_SHOW_RESULT;
    for (int i = 0; i < 400; i++) {
        v.aim_rad = -1.6f + 0.008f * (float)i;
        v.fall_line_rad = 0.31f * (float)i;
        v.slope_pct = (float)(i % 9);
        v.plays_like_m = (float)(i % 13) - 2.0f;
        v.line_here = (i % 5) != 0;
        v.note = (uint8_t)(i % ((int)GL_UI_NOTE_COUNT + 2));
        v.drop = (uint8_t)((i / 3) % 6);
        v.distance_assumed = (i % 4) == 1;
        v.chg_blocked = (uint8_t)(i % 5);
        v.break_cups = (float)(i % 31) - 15.0f;
        v.distance_m = (i % 7 == 0) ? 0.0f : (0.3f * (float)i);
        v.confidence = (float)(i % 6) / 5.0f;
        v.flag_found = (i & 1) != 0;
        v.solved = (i & 2) != 0;
        v.precision = (i & 4) != 0;
        ui.survey_count = (uint8_t)(i % 5);
        ui.edit.units = (uint8_t)(i % 3);
        gl_ui_render(&ui, &v, &gfx);
        outside += ink_outside();
    }
    GL_CHECK_EQ(outside, 0);
    /* every settings item, every value */
    fresh();
    ui.state = GL_UI_SETTINGS_DIAL;
    for (uint8_t item = 0; item < GL_UI_ITEM_COUNT; item++) {
        int lo = 0, hi = 1;
        ui.item = item;
        if (item < GL_UI_ITEM_ZERO) {
            gl_settings_item_range((gl_item_t)item, &lo, &hi);
        }
        for (int val = lo; val <= hi; val++) {
            unsigned ink;
            if (item < GL_UI_ITEM_ZERO) {
                gl_settings_item_set(&ui.edit, (gl_item_t)item, val);
            }
            ui.dial_value = val;
            gl_ui_render(&ui, &v, &gfx);
            outside += ink_outside();
            ink = gl_gfx_count_black(&gfx);
            GL_CHECK(ink > 300);
        }
    }
    GL_CHECK_EQ(outside, 0);
}

/* Fit the direction of the aim line from the rendered result screen, using
 * only pixels of the band 44..86 rows that belong to the long line. */
GL_TEST(test_result_screen_shows_the_aim_line)
{
    gl_ui_view_t v;
    gl_gfx_init(&gfx);
    view_default(&v);
    fresh();
    ui.state = GL_UI_SHOW_RESULT;
    for (int k = -10; k <= 10; k += 2) {
        double a = 0.5 * k * 3.14159265358979 / 180.0; /* -5 .. +5 degrees */
        double sx = 0, sy = 0, sxx = 0, syy = 0, sxy = 0;
        int n = 0;
        const double offset = (double)GL_CFG_BALL_CENTRE_Y_PX * sin(a);
        v.aim_rad = (float)a;
        gl_ui_render(&ui, &v, &gfx);
        for (int y = 40; y <= 88; y++) {
            for (int x = 0; x < 128; x++) {
                /* the line is expected near x = 63.5 + offset - (y - 63.5) tan(a) */
                double xl = 63.5 + offset + (y - 63.5) * tan(a);
                if (!gl_gfx_get(&gfx, x, y) && fabs(x - xl) < 4.5) {
                    sx += x;
                    sy += y;
                    sxx += (double)x * x;
                    syy += (double)y * y;
                    sxy += (double)x * y;
                    n++;
                }
            }
        }
        GL_CHECK(n > 250);
        {
            double cx = sx / n, cy = sy / n;
            double cxy = sxy / n - cx * cy, cyy = syy / n - cy * cy;
            double slope = cxy / cyy; /* dx/dy of the drawn line */
            /* direction (-sin a, -cos a): dx/dy = tan(a) */
            GL_CHECK_NEAR(atan(slope) * 57.29578, a * 57.29578, 0.5);
            GL_CHECK_NEAR(cx + (63.5 - cy) * slope, 63.5 + offset, 0.6);
        }
    }
    /* far-off aim: the dashed substitute and a side arrow are drawn instead */
    v.aim_rad = 0.5f;
    gl_ui_render(&ui, &v, &gfx);
    GL_CHECK(gl_gfx_count_black(&gfx) > 400);
    /* tilt-only result (the phase-1 solver stub): says so */
    {
        unsigned with, without;
        v.aim_rad = 0.0f;
        v.solved = true;
        gl_ui_render(&ui, &v, &gfx);
        with = gl_gfx_count_black(&gfx);
        v.solved = false;
        gl_ui_render(&ui, &v, &gfx);
        without = gl_gfx_count_black(&gfx);
        GL_CHECK(with != without);
    }
    /* rendering is deterministic */
    {
        static uint8_t first[GL_GFX_BYTES];
        uint8_t rows[GL_GFX_H];
        gl_ui_render(&ui, &v, &gfx);
        memcpy(first, gfx.px, sizeof(first));
        gl_ui_render(&ui, &v, &gfx);
        GL_CHECK_EQ(gl_gfx_changed_rows(&gfx, first, rows), 0);
        /* a changed confidence only touches the rows of the bar */
        v.confidence = 0.2f;
        gl_ui_render(&ui, &v, &gfx);
        {
            unsigned n = gl_gfx_changed_rows(&gfx, first, rows);
            GL_CHECK(n > 0 && n <= 6);
            GL_CHECK(rows[0] >= 105 && rows[n - 1] <= 110);
        }
    }
}

/* Phase 2: the result screen says what kind of result it is.  A fallback
 * or a weak read is a plain message and a tentative (dashed) line, never
 * only a normal-looking line; a Survey drop that is not at the ball has no
 * line at all. */
static unsigned black_in_rows_(int y0, int y1)
{
    unsigned n = 0;
    for (int y = y0; y <= y1; y++) {
        for (int x = 0; x < 128; x++) {
            n += gl_gfx_get(&gfx, x, y) ? 0u : 1u;
        }
    }
    return n;
}

GL_TEST(test_result_screen_messages_and_tentative_line)
{
    static gl_gfx_t plain;
    gl_ui_view_t v;
    gl_ui_result_text_t t;
    unsigned solid_mid, n;
    uint8_t rows[GL_GFX_H];

    gl_gfx_init(&gfx);
    gl_gfx_init(&plain);
    fresh();
    ui.state = GL_UI_SHOW_RESULT;
    view_default(&v);
    gl_ui_render(&ui, &v, &plain);
    gl_ui_render(&ui, &v, &gfx);
    solid_mid = black_in_rows_(46, 88);
    gl_ui_result_text(&ui, &v, &t);
    GL_CHECK(strcmp(t.distance, "14.4FT") == 0);
    GL_CHECK(strcmp(t.plays, "PLAYS 16.1FT") == 0);
    GL_CHECK(strcmp(t.brk, "<2.5 CUP") == 0);
    GL_CHECK(strcmp(t.slope, "2.1%") == 0);
    GL_CHECK(t.note[0] == '\0' && t.mode[0] == '\0');
    /* every message: its text, and it only touches the message line */
    for (int note = 1; note < (int)GL_UI_NOTE_COUNT; note++) {
        v.note = (uint8_t)note;
        gl_ui_render(&ui, &v, &gfx);
        gl_ui_result_text(&ui, &v, &t);
        GL_CHECK(strlen(t.note) >= 6 && strlen(t.note) <= 14);
        GL_CHECK(strcmp(t.note, gl_ui_note_text((gl_ui_note_t)note)) == 0);
        n = gl_gfx_changed_rows(&gfx, plain.px, rows);
        GL_CHECK(n >= 7 && n <= 11);
        GL_CHECK(rows[0] >= 34 && rows[n - 1] <= 44);
        for (int other = 1; other < note; other++) {
            GL_CHECK(strcmp(gl_ui_note_text((gl_ui_note_t)other), t.note) != 0);
        }
    }
    GL_CHECK(gl_ui_note_text(GL_UI_NOTE_NONE)[0] == '\0');
    GL_CHECK(gl_ui_note_text((gl_ui_note_t)200)[0] == '\0');
    v.note = GL_UI_NOTE_NONE;
    /* an aim that is not a solution: long dashes, no break, no plays-like */
    v.solved = false;
    v.note = GL_UI_NOTE_NOT_SOLVED;
    gl_ui_render(&ui, &v, &gfx);
    gl_ui_result_text(&ui, &v, &t);
    GL_CHECK(strcmp(t.brk, "BREAK ?") == 0);
    GL_CHECK(t.plays[0] == '\0');
    GL_CHECK(black_in_rows_(46, 88) < solid_mid - 60u); /* the line lost its gaps' worth of ink */
    GL_CHECK(black_in_rows_(46, 88) > solid_mid / 3u);  /* but it is there */
    v.solved = true;
    v.note = GL_UI_NOTE_NONE;
    /* a distance that was dialled or assumed is marked; an unknown one is
     * not shown, and neither is a break in cups that would need it */
    v.distance_assumed = true;
    gl_ui_result_text(&ui, &v, &t);
    GL_CHECK(strcmp(t.distance, "14.4FT?") == 0);
    v.distance_m = 0.0f;
    v.plays_like_m = 0.0f;
    gl_ui_result_text(&ui, &v, &t);
    GL_CHECK(strcmp(t.distance, "--") == 0);
    GL_CHECK(strcmp(t.brk, "BREAK ?") == 0);
    GL_CHECK(t.plays[0] == '\0');
    view_default(&v);
    /* the side of the break and the units */
    v.break_cups = -1.26f;
    ui.edit.units = GL_UNITS_METRES;
    gl_ui_result_text(&ui, &v, &t);
    GL_CHECK(strcmp(t.brk, "1.3 CUP>") == 0);
    GL_CHECK(strcmp(t.distance, "4.4M") == 0);
    GL_CHECK(strcmp(t.plays, "PLAYS 4.9M") == 0);
    v.break_cups = 0.03f;
    gl_ui_result_text(&ui, &v, &t);
    GL_CHECK(strcmp(t.brk, "STRAIGHT") == 0);
    ui.edit.units = GL_UNITS_FEET;
    view_default(&v);
    /* Survey: the drop number; not at the ball = no line, the prompt */
    v.drop = 3;
    gl_ui_result_text(&ui, &v, &t);
    GL_CHECK(strcmp(t.mode, "D3") == 0);
    v.line_here = false;
    v.note = GL_UI_NOTE_APPROX; /* the prompt takes the message line */
    gl_ui_render(&ui, &v, &gfx);
    gl_ui_result_text(&ui, &v, &t);
    GL_CHECK(strcmp(t.note, "PUT AT BALL") == 0);
    {
        /* no column of the middle band carries a line: the tallest run of
         * black in any column is a glyph, 7 px */
        int tallest = 0;
        for (int x = 0; x < 128; x++) {
            int run = 0;
            for (int y = 46; y <= 88; y++) {
                run = gl_gfx_get(&gfx, x, y) ? 0 : run + 1;
                if (run > tallest) {
                    tallest = run;
                }
            }
        }
        GL_CHECK(tallest <= GL_FONT_H);
    }
    view_default(&v);
    v.precision = true;
    gl_ui_result_text(&ui, &v, &t);
    GL_CHECK(strcmp(t.mode, "2X") == 0);
    /* confidence boxes */
    GL_CHECK_EQ(gl_ui_conf_boxes(0.0f), 0);
    GL_CHECK_EQ(gl_ui_conf_boxes(0.09f), 0);
    GL_CHECK_EQ(gl_ui_conf_boxes(0.11f), 1);
    GL_CHECK_EQ(gl_ui_conf_boxes(0.2f), 1);
    GL_CHECK_EQ(gl_ui_conf_boxes(0.95f), 5);
    GL_CHECK_EQ(gl_ui_conf_boxes(7.0f), 5);
    GL_CHECK_EQ(gl_ui_conf_boxes(-1.0f), 0);
    GL_CHECK_EQ(gl_ui_conf_boxes((float)NAN), 0);
    /* the cradle screen says why the charge is stopped */
    ui.state = GL_UI_CRADLE_USB;
    view_default(&v);
    gl_ui_render(&ui, &v, &plain);
    for (int blocked = 1; blocked <= 3; blocked++) {
        v.chg_blocked = (uint8_t)blocked;
        gl_ui_render(&ui, &v, &gfx);
        n = gl_gfx_changed_rows(&gfx, plain.px, rows);
        GL_CHECK(n >= 5 && n <= 7);
        GL_CHECK(rows[0] >= 96 && rows[n - 1] <= 102);
        GL_CHECK_EQ(ink_outside(), 0);
    }
}

/* Review finding: gl_ui_render() with view.confidence = NaN was undefined
 * behaviour ("nan is outside the range of representable values of type
 * 'int'", gl_ui.c:479); phase 2 will feed solver output into the view.
 * Every float of the view is given every hostile value, in every state;
 * runs under UBSan in `make asan`, and the ink must stay in the aperture. */
GL_TEST(test_render_with_hostile_view_values)
{
    static const float bad[] = { (float)NAN, (float)INFINITY, -(float)INFINITY, 3.0e9f, -3.0e9f,
                                 3.4e38f, -3.4e38f, 1.0e-30f };
    unsigned renders = 0;
    fresh();
    for (int st = 0; st < GL_UI_STATE_COUNT; st++) {
        ui.state = (uint8_t)st;
        for (size_t k = 0; k < sizeof(bad) / sizeof(bad[0]); k++) {
            for (int field = 0; field < 8; field++) {
                gl_ui_view_t v;
                view_default(&v);
                v.have_result = true;
                v.solved = (field & 1) != 0;
                switch (field) {
                case 0: v.confidence = bad[k]; break;
                case 1: v.aim_rad = bad[k]; break;
                case 2: v.ball_az_rad = bad[k]; break;
                case 3: v.distance_m = bad[k]; break;
                case 4: v.slope_pct = bad[k]; break;
                case 5: v.fall_line_rad = bad[k]; break;
                case 6: v.plays_like_m = bad[k]; break;
                default: v.break_cups = bad[k]; break;
                }
                gl_ui_render(&ui, &v, &gfx);
                GL_CHECK_EQ(ink_outside(), 0);
                renders++;
            }
            /* all of them at once */
            {
                gl_ui_view_t v;
                view_default(&v);
                v.have_result = true;
                v.solved = true;
                v.confidence = v.aim_rad = v.ball_az_rad = v.distance_m = v.slope_pct = bad[k];
                v.fall_line_rad = v.plays_like_m = v.break_cups = bad[k];
                v.line_here = true;
                v.battery_pct = 255;
                v.cal_step = 255;
                gl_ui_render(&ui, &v, &gfx);
                GL_CHECK_EQ(ink_outside(), 0);
                renders++;
            }
        }
    }
    printf("    %u renders with NaN / infinite / huge view values: no ink outside the aperture\n",
           renders);
}

/* ---- phase-2 review: the rows added to the table --------------------------- */

/* A second double tap on a Precision result goes on to the Survey; it never
 * arms another spin (the marker has been turned since its cameras read). */
GL_TEST(test_double_tap_on_a_precision_result_is_a_survey)
{
    uint32_t a;
    fresh();
    wake_up();
    quick_read();
    a = ev(GL_EV_DOUBLE_TAP, 0);
    GL_CHECK(a & GL_ACT_ARM_SPIN);
    STATE_IS(GL_UI_PRECISION_WAIT_SPIN);
    GL_CHECK(ev(GL_EV_SPIN_DONE, 0) & GL_ACT_START_TILT);
    STATE_IS(GL_UI_READ_TILT);
    GL_CHECK_EQ(ui.read_kind, GL_READ_PRECISION);
    a = ev(GL_EV_TILT_DONE, 0);
    GL_CHECK((a & GL_ACT_START_SOLVE) && (a & GL_ACT_PRECISION));
    (void)ev(GL_EV_SOLVE_DONE, 0);
    STATE_IS(GL_UI_SHOW_RESULT);
    /* the second double tap */
    a = ev(GL_EV_DOUBLE_TAP, 0);
    GL_CHECK((a & GL_ACT_ARM_SPIN) == 0u);
    GL_CHECK(a & GL_ACT_SURVEY_STORE);
    STATE_IS(GL_UI_SURVEY_NEXT_DROP);
    GL_CHECK_EQ(ui.survey_count, 1);
    /* ending the Survey there and tapping again still arms no spin: the
     * result shown is the same spun read */
    a = ev(GL_EV_DOUBLE_TAP, 0);
    GL_CHECK(a & GL_ACT_SURVEY_RESET);
    STATE_IS(GL_UI_SHOW_RESULT);
    a = ev(GL_EV_DOUBLE_TAP, 0);
    GL_CHECK((a & GL_ACT_ARM_SPIN) == 0u);
    STATE_IS(GL_UI_SURVEY_NEXT_DROP);
    /* an ABANDONED spin leaves a Quick result: the spin may be asked for again */
    fresh();
    wake_up();
    quick_read();
    (void)ev(GL_EV_DOUBLE_TAP, 0);
    STATE_IS(GL_UI_PRECISION_WAIT_SPIN);
    now += 21000;
    GL_CHECK(gl_ui_tick(&ui, now) & GL_ACT_SPIN_ABANDON);
    STATE_IS(GL_UI_SHOW_RESULT);
    GL_CHECK(ev(GL_EV_DOUBLE_TAP, 0) & GL_ACT_ARM_SPIN);
    STATE_IS(GL_UI_PRECISION_WAIT_SPIN);
    /* a new placement makes the next result a Quick one again */
    fresh();
    wake_up();
    quick_read();
    (void)ev(GL_EV_DOUBLE_TAP, 0);
    (void)ev(GL_EV_SPIN_DONE, 0);
    (void)ev(GL_EV_TILT_DONE, 0);
    (void)ev(GL_EV_SOLVE_DONE, 0);
    GL_CHECK(ev(GL_EV_MOTION, 0) & GL_ACT_NEW_READ);
    STATE_IS(GL_UI_WAIT_STILL);
    quick_read();
    GL_CHECK(ev(GL_EV_DOUBLE_TAP, 0) & GL_ACT_ARM_SPIN);
}

/* The distance prompt (no flagstick seen): picking the marker up and putting
 * it down again is a new read; it used to be ignored for 30 s. */
GL_TEST(test_distance_prompt_is_left_by_re_placing)
{
    uint32_t a;
    fresh();
    wake_up();
    (void)ev(GL_EV_STILL, 0);
    (void)ev(GL_EV_TILT_DONE, 0);
    a = ev(GL_EV_CAPTURE_NO_STICK, 0);
    GL_CHECK(a & GL_ACT_DIAL_BEGIN);
    STATE_IS(GL_UI_SETTINGS_DIAL);
    GL_CHECK(ui.dist_prompt);
    GL_CHECK_EQ(ui.item, GL_ITEM_DISTANCE);
    /* lying still: nothing happens (a STILL that was already under way) */
    GL_CHECK_EQ(ev(GL_EV_STILL, 0), 0u);
    STATE_IS(GL_UI_SETTINGS_DIAL);
    /* picked up ... */
    a = ev(GL_EV_MOTION, 0);
    GL_CHECK_EQ(a, GL_ACT_WATCH_STILL);
    STATE_IS(GL_UI_SETTINGS_DIAL);
    /* ... and put down: a new Quick Read, the prompt gone, nothing saved */
    a = ev(GL_EV_STILL, 0);
    GL_CHECK((a & GL_ACT_START_TILT) && (a & GL_ACT_NEW_READ));
    GL_CHECK((a & GL_ACT_SAVE_SETTINGS) == 0u);
    STATE_IS(GL_UI_READ_TILT);
    GL_CHECK(!ui.dist_prompt);
    GL_CHECK_EQ(ui.read_kind, GL_READ_QUICK);
    GL_CHECK_EQ(ui.edit.manual_distance_cm, 0);

    /* the golfer who dials: upright, roll, flat - FLAT saves, as before */
    fresh();
    wake_up();
    (void)ev(GL_EV_STILL, 0);
    (void)ev(GL_EV_TILT_DONE, 0);
    (void)ev(GL_EV_CAPTURE_NO_STICK, 0);
    (void)ev(GL_EV_MOTION, 0);
    (void)ev(GL_EV_UPRIGHT, 0);
    (void)ev(GL_EV_DIAL_STEP, 9);
    GL_CHECK(ui.edit.manual_distance_cm != 0u);
    a = ev(GL_EV_FLAT, 0);
    GL_CHECK(a & GL_ACT_SAVE_SETTINGS);
    STATE_IS(GL_UI_WAIT_STILL);
    GL_CHECK(ui.saved.manual_distance_cm != 0u);
    GL_CHECK(ev(GL_EV_STILL, 0) & GL_ACT_START_TILT); /* the STILL that follows the FLAT */

    /* an ordinary visit to the dial (not the prompt) has no such exit */
    fresh();
    wake_up();
    GL_CHECK(ev(GL_EV_UPRIGHT, 0) & GL_ACT_DIAL_BEGIN);
    STATE_IS(GL_UI_SETTINGS_DIAL);
    GL_CHECK(!ui.dist_prompt);
    GL_CHECK_EQ(ev(GL_EV_MOTION, 0), 0u);
    GL_CHECK_EQ(ev(GL_EV_STILL, 0), 0u);
    STATE_IS(GL_UI_SETTINGS_DIAL);
}

/* The result screen of a marker that faces away from the hole is the screen
 * of one that faces it, turned round; the texts are the same strings. */
GL_TEST(test_result_screen_is_turned_round_with_the_marker)
{
    static gl_gfx_t g1, g2;
    gl_ui_view_t v, w;
    gl_ui_result_text_t t;
    static const float yaw[5] = { 3.10f, -3.0f, 2.2f, -1.7f, 3.14159f };

    fresh();
    wake_up();
    quick_read();
    memset(&v, 0, sizeof(v));
    v.have_result = true;
    v.solved = true;
    v.line_here = true;
    v.flag_found = true;
    v.precision = true;
    v.distance_m = 6.0f;
    v.plays_like_m = 6.4f;
    v.plays_uncertain = true;
    v.slope_pct = 2.0f;
    v.break_cups = 2.9f;
    v.confidence = 0.4f;
    v.battery_pct = 80;
    for (unsigned k = 0; k < 5u; k++) {
        unsigned differ = 0;
        /* the marker has been turned by yaw[k] since the read */
        v.aim_rad = gl_wrap_pi(0.10f - yaw[k]);
        v.fall_line_rad = gl_wrap_pi(-1.3f - yaw[k]);
        v.ball_az_rad = gl_wrap_pi(-yaw[k]);
        gl_gfx_init(&g1);
        gl_ui_render(&ui, &v, &g1);
        /* the same putt on a marker turned by yaw - pi: within 90 degrees of facing the hole */
        w = v;
        w.aim_rad = gl_wrap_pi(v.aim_rad - GL_PI_F);
        w.fall_line_rad = gl_wrap_pi(v.fall_line_rad - GL_PI_F);
        w.ball_az_rad = gl_wrap_pi(v.ball_az_rad - GL_PI_F);
        GL_CHECK(fabsf(w.ball_az_rad) <= 0.5f * GL_PI_F);
        gl_gfx_init(&g2);
        gl_ui_render(&ui, &w, &g2);
        for (int y = 0; y < 128; y++) {
            for (int x = 0; x < 128; x++) {
                differ += (gl_gfx_get(&g1, x, y) != gl_gfx_get(&g2, 127 - x, 127 - y)) ? 1u : 0u;
                if (!gl_gfx_get(&g1, x, y)) {
                    GL_CHECK(gl_gfx_in_clip(&g1, x, y)); /* still inside the aperture */
                }
            }
        }
        GL_CHECK_EQ(differ, 0);
        GL_CHECK(gl_gfx_count_black(&g1) > 600u);
    }
    /* facing the hole (within 90 degrees): drawn as it always was, and the
     * two pictures are NOT each other's rotation (the text is upright in both) */
    v.aim_rad = 0.10f;
    v.fall_line_rad = -1.3f;
    v.ball_az_rad = 0.0f;
    gl_gfx_init(&g1);
    gl_ui_render(&ui, &v, &g1);
    gl_ui_result_text(&ui, &v, &t);
    GL_CHECK(strcmp(t.brk, "<2.9 CUP") == 0);
    GL_CHECK(strcmp(t.plays, "PLAYS 21.0FT?") == 0);
    GL_CHECK(strcmp(t.mode, "2X") == 0);
    /* the break label is where it is drawn for an upright screen: a white
     * box with the glyphs at y = 92 */
    {
        unsigned black = 0;
        for (int y = 92; y < 92 + GL_FONT_H; y++) {
            for (int x = 64 - 24; x < 64 + 24; x++) {
                black += gl_gfx_get(&g1, x, y) ? 0u : 1u;
            }
        }
        GL_CHECK(black > 40u && black < 160u);
    }
}

/* The notes added by the review, and "PLAYS" with its question mark. */
GL_TEST(test_notes_of_the_review)
{
    gl_ui_view_t v;
    gl_ui_result_text_t t;
    GL_CHECK(strcmp(gl_ui_note_text(GL_UI_NOTE_HORIZON), "POOR HORIZON") == 0);
    GL_CHECK(strcmp(gl_ui_note_text(GL_UI_NOTE_NO_SOLUTION), "NO SOLUTION") == 0);
    GL_CHECK(strcmp(gl_ui_note_text(GL_UI_NOTE_COUNT), "") == 0);
    for (unsigned n = 1; n < GL_UI_NOTE_COUNT; n++) {
        /* every message fits its buffer and the aperture at the message line */
        GL_CHECK(strlen(gl_ui_note_text((gl_ui_note_t)n)) <= 15u);
        GL_CHECK(strlen(gl_ui_note_text((gl_ui_note_t)n)) > 0u);
    }
    fresh();
    memset(&v, 0, sizeof(v));
    v.have_result = true;
    v.solved = true;
    v.line_here = true;
    v.flag_found = true;
    v.distance_m = 29.87f; /* the longest dial distance, in feet: 98.0FT */
    v.plays_like_m = 31.0f;
    v.plays_uncertain = true;
    gl_ui_result_text(&ui, &v, &t);
    GL_CHECK(strcmp(t.plays, "PLAYS 101.7FT?") == 0);
    v.plays_uncertain = false;
    gl_ui_result_text(&ui, &v, &t);
    GL_CHECK(strcmp(t.plays, "PLAYS 101.7FT") == 0);
    v.note = (uint8_t)GL_UI_NOTE_HORIZON;
    gl_ui_result_text(&ui, &v, &t);
    GL_CHECK(strcmp(t.note, "POOR HORIZON") == 0);
}

int main(void)
{
    GL_RUN(test_table_is_well_formed);
    GL_RUN(test_every_state_reachable_and_escapable);
    GL_RUN(test_quick_read);
    GL_RUN(test_read_interrupted);
    GL_RUN(test_precision_read);
    GL_RUN(test_survey);
    GL_RUN(test_flag_out_fallback);
    GL_RUN(test_settings_dial);
    GL_RUN(test_usb_cradle);
    GL_RUN(test_zeroing_is_never_done_in_the_cradle);
    GL_RUN(test_low_battery_and_faults_from_every_state);
    GL_RUN(test_keepalive_extends_only_the_current_state);
    GL_RUN(test_timeouts_and_tick_wraparound);
    GL_RUN(test_random_event_fuzz);
    GL_RUN(test_every_screen_stays_in_the_aperture);
    GL_RUN(test_result_screen_shows_the_aim_line);
    GL_RUN(test_result_screen_messages_and_tentative_line);
    GL_RUN(test_render_with_hostile_view_values);
    GL_RUN(test_double_tap_on_a_precision_result_is_a_survey);
    GL_RUN(test_distance_prompt_is_left_by_re_placing);
    GL_RUN(test_result_screen_is_turned_round_with_the_marker);
    GL_RUN(test_notes_of_the_review);
    return gl_test_summary();
}
