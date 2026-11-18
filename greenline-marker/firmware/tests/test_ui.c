/*
 * test_ui.c - the UI transition table (structure, reachability, scenario
 * walks, timeouts, random event fuzz) and the screens.
 */
#include <stdlib.h>

#include "gl_config.h"
#include "gl_regulatory.h"
#include "gl_solver.h"
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
        GL_CHECK(t[i].guard <= GL_G_RECALL);
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
            t[i].event != GL_EV_CAPTURE_NO_STICK &&
            /* phase 3: tilt-only mode - the capture "completes" without the
             * cameras ever having been switched on */
            t[i].event != GL_EV_CAPTURE_SKIPPED) {
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
     * limit are the two in which the MCU sleeps: SLEEP and CRADLE_SLEEP
     * (rev E: CRADLE_USB has the 30 s of DESIGN_SPEC E32) */
    for (int s = 0; s < GL_UI_STATE_COUNT; s++) {
        bool has = false;
        for (size_t i = 0; i < n; i++) {
            if (t[i].state == s && t[i].event == GL_EV_TIMEOUT) {
                has = true;
            }
        }
        if (s == GL_UI_SLEEP || s == GL_UI_CRADLE_SLEEP) {
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
                                  GL_ITEM_DISTANCE, GL_ITEM_RAWLOG, GL_ITEM_METHOD,
                                  GL_ITEM_SURFACE, GL_ITEM_TILTLOG, /* phase 3: E11, tilt logger */
                                  GL_UI_ITEM_ZERO,
                                  GL_UI_ITEM_INFO, /* phase 3: regulatory and information screen */
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
    GL_CHECK_EQ(ev(GL_EV_TOO_HOT, 0), 0);
    /* DESIGN_SPEC E32: the state lasts 30 s without host activity ... */
    GL_CHECK_EQ(gl_ui_timeout_ms(GL_UI_CRADLE_USB), 30000);
    now += 29900;
    GL_CHECK_EQ(gl_ui_tick(&ui, now), 0);
    STATE_IS(GL_UI_CRADLE_USB);
    /* ... counted again from every sign of a host (the application calls
     * gl_ui_keepalive when one has sent something) */
    gl_ui_keepalive(&ui, now);
    now += 29900;
    GL_CHECK_EQ(gl_ui_tick(&ui, now), 0);
    STATE_IS(GL_UI_CRADLE_USB);
    /* then: asleep in the cradle.  Not the ordinary sleep (the display
     * stays on with the symbol), and what happens to USB is the
     * application's decision (standby under a suspended bus, else off) */
    now += 200;
    a = gl_ui_tick(&ui, now);
    STATE_IS(GL_UI_CRADLE_SLEEP);
    GL_CHECK((a & GL_ACT_CRADLE_SLEEP) && (a & GL_ACT_REDRAW));
    GL_CHECK(!(a & GL_ACT_ENTER_SLEEP) && !(a & GL_ACT_USB_STOP));
    /* nothing but the host and the cradle ends it: no time limit, and
     * motion, taps, a low cell, a hot cell and a bouncing VBUS change nothing */
    GL_CHECK_EQ(gl_ui_timeout_ms(GL_UI_CRADLE_SLEEP), 0);
    GL_CHECK_EQ(gl_ui_tick(&ui, now + 100000000u), 0);
    GL_CHECK_EQ(ev(GL_EV_MOTION, 0), 0);
    GL_CHECK_EQ(ev(GL_EV_DOUBLE_TAP, 0), 0);
    GL_CHECK_EQ(ev(GL_EV_BATT_LOW, 0), 0);
    GL_CHECK_EQ(ev(GL_EV_TOO_HOT, 0), 0);
    GL_CHECK_EQ(ev(GL_EV_USB_ATTACH, 0), 0);
    GL_CHECK_EQ(ev(GL_EV_TIMEOUT, 0), 0);
    STATE_IS(GL_UI_CRADLE_SLEEP);
    /* the host resumes the bus: awake again, USB started, 30 s more */
    a = ev(GL_EV_USB_RESUME, 0);
    STATE_IS(GL_UI_CRADLE_USB);
    GL_CHECK((a & GL_ACT_DISPLAY_ON) && (a & GL_ACT_USB_START) && (a & GL_ACT_REDRAW));
    GL_CHECK_EQ(gl_ui_time_left_ms(&ui, now), 30000u);
    /* a resume means nothing anywhere else */
    GL_CHECK_EQ(ev(GL_EV_USB_RESUME, 0), 0);
    STATE_IS(GL_UI_CRADLE_USB);
    /* lifted out of the cradle while asleep in it: the ordinary sleep */
    now += 30100;
    (void)gl_ui_tick(&ui, now);
    STATE_IS(GL_UI_CRADLE_SLEEP);
    a = ev(GL_EV_USB_DETACH, 0);
    GL_CHECK((a & GL_ACT_USB_STOP) && (a & GL_ACT_ENTER_SLEEP));
    STATE_IS(GL_UI_SLEEP);
    GL_CHECK(!ui.usb);
    /* lifted out of the cradle while awake in it */
    a = ev(GL_EV_USB_ATTACH, 0);
    STATE_IS(GL_UI_CRADLE_USB);
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

    /* structure: the rows that start the zeroing leave the settings dial
     * (the user's zeroing) or the state in which a read would start (phase
     * 3: the factory's ARMED zeroing, which runs on the seat plate with
     * nothing on the pads - mechanical/README step 19); no row leads from a
     * cradle state to it; no row lets it finish into the cradle state */
    for (size_t i = 0; i < n; i++) {
        if (t[i].actions & GL_ACT_CAL_ZERO_START) {
            ways_in++;
            if (t[i].event == GL_EV_CAL_ARMED) {
                GL_CHECK_EQ(t[i].state, GL_UI_WAIT_STILL);
            } else {
                GL_CHECK_EQ(t[i].state, GL_UI_SETTINGS_DIAL);
                GL_CHECK_EQ(t[i].event, GL_EV_FLAT);
                GL_CHECK_EQ(t[i].guard, GL_G_ITEM_ZERO_YES);
            }
            GL_CHECK_EQ(t[i].next, GL_UI_CAL_ZERO);
        }
        if (t[i].state == GL_UI_CRADLE_SLEEP) {
            GL_CHECK(t[i].next != GL_UI_CAL_ZERO);
            GL_CHECK(!(t[i].actions & GL_ACT_CAL_ZERO_START));
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
    GL_CHECK_EQ(ways_in, 2);

    /* the armed zeroing does not start in the cradle either: the event
     * changes nothing there */
    fresh();
    ev(GL_EV_USB_ATTACH, 0);
    STATE_IS(GL_UI_CRADLE_USB);
    GL_CHECK_EQ(ev(GL_EV_CAL_ARMED, 0), 0);
    STATE_IS(GL_UI_CRADLE_USB);

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
        /* TOO_HOT */ { GL_EV_MOTION, GL_EV_TOO_HOT, GL_EV_NONE },
        /* CRADLE_SLEEP */ { GL_EV_USB_ATTACH, GL_EV_NONE }, /* and 30 s, below */
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
            if (s == GL_UI_CRADLE_SLEEP) {
                now += 30100; /* 30 s without a host */
                gl_ui_tick(&ui, now);
            }
            STATE_IS(s);
            if (hit == 0) {
                a = ev(GL_EV_BATT_LOW, 0);
                if (s == GL_UI_SLEEP || s == GL_UI_CRADLE_USB || s == GL_UI_CRADLE_SLEEP ||
                    s == GL_UI_CAL_ZERO) {
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
                /* from every state, also from the zeroing (which is abandoned);
                 * asleep in the cradle it is VBUS bouncing and changes nothing */
                STATE_IS(s == GL_UI_CRADLE_SLEEP ? GL_UI_CRADLE_SLEEP : GL_UI_CRADLE_USB);
                if (s == GL_UI_CAL_ZERO) {
                    GL_CHECK(a & GL_ACT_CAL_ABORT);
                }
                if (s == GL_UI_CRADLE_SLEEP) {
                    GL_CHECK_EQ(a, 0);
                } else if (s != GL_UI_CRADLE_USB) {
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
        v.show = (uint8_t)(i % 4); /* the three states and a value that does not exist */
        v.recalled = (i % 7) == 3;
        v.age_s = 977u * (uint32_t)i * (uint32_t)i;
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
    v.info_hw = 'E';
    v.info_fw = 0x0003u;
    memcpy(v.info_serial, "1A2B3C4", 8);
    v.info_text = "THIS TEXT STANDS FOR THE REGULATORY TEXT. IT IS LONG ENOUGH TO NEED A SECOND PAGE: "
                  "0123456789 0123456789 0123456789 0123456789 0123456789 0123456789 0123456789 "
                  "0123456789 0123456789 0123456789 0123456789 0123456789 0123456789.";
    ui.info_pages = (uint8_t)gl_ui_info_pages(v.info_text);
    GL_CHECK_EQ(ui.info_pages, 3);
    for (uint8_t item = 0; item < GL_UI_ITEM_COUNT; item++) {
        int lo = 0, hi = 1;
        ui.item = item;
        if (item < GL_UI_ITEM_ZERO) {
            gl_settings_item_range((gl_item_t)item, &lo, &hi);
        } else if (item == GL_UI_ITEM_INFO) {
            hi = (int)ui.info_pages; /* one beyond the last page as well */
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

/* Rev E screens.  E32: the static picture of the cradle sleep says what the
 * charge is doing - charging, full, or why it is stopped - and each of those
 * is a different picture; so does the awake cradle screen.  E13: "TOO HOT".
 * All of them stay inside the round aperture. */
GL_TEST(test_cradle_and_too_hot_screens)
{
    static uint8_t pic[2][12][GL_GFX_BYTES];
    gl_ui_view_t v;
    int n = 0;
    gl_gfx_init(&gfx);
    for (int st = 0; st < 2; st++) {
        n = 0;
        fresh();
        ui.state = (uint8_t)(st == 0 ? GL_UI_CRADLE_SLEEP : GL_UI_CRADLE_USB);
        /* charging, full, idle, then every reason a charge is stopped for */
        for (int k = 0; k < 3 + 7; k++) {
            view_default(&v);
            v.have_result = false;
            v.charging = (k == 0);
            v.chg_full = (k == 1);
            v.chg_blocked = (uint8_t)(k >= 3 ? k - 2 : 0);
            gl_ui_render(&ui, &v, &gfx);
            GL_CHECK_EQ(ink_outside(), 0);
            GL_CHECK(gl_gfx_count_black(&gfx) > 150);
            memcpy(pic[st][n], gfx.px, GL_GFX_BYTES);
            for (int j = 0; j < n; j++) {
                GL_CHECK(memcmp(pic[st][j], pic[st][n], GL_GFX_BYTES) != 0);
            }
            n++;
        }
        /* a value of chg_blocked nobody defined still draws something sane */
        view_default(&v);
        v.chg_blocked = 200;
        gl_ui_render(&ui, &v, &gfx);
        GL_CHECK_EQ(ink_outside(), 0);
    }
    /* the sleep picture is not the awake one */
    GL_CHECK(memcmp(pic[0][0], pic[1][0], GL_GFX_BYTES) != 0);
    /* TOO HOT: one picture, whatever the view holds */
    fresh();
    ui.state = (uint8_t)GL_UI_TOO_HOT;
    view_default(&v);
    gl_ui_render(&ui, &v, &gfx);
    GL_CHECK_EQ(ink_outside(), 0);
    GL_CHECK(gl_gfx_count_black(&gfx) > 400);
    memcpy(pic[0][0], gfx.px, GL_GFX_BYTES);
    v.have_result = false;
    v.charging = true;
    gl_ui_render(&ui, &v, &gfx);
    GL_CHECK(memcmp(pic[0][0], gfx.px, GL_GFX_BYTES) == 0);
}

/* E13 in the state machine: the event stops a read that is on its way to the
 * cameras, the screen shows for 4 s, then the marker sleeps; a result that
 * is already shown, the dial and the zeroing are left alone. */
GL_TEST(test_too_hot_stops_a_read_and_sleeps)
{
    uint32_t a;
    static const gl_ui_state_t untouched[] = { GL_UI_SLEEP, GL_UI_SHOW_RESULT,
                                               GL_UI_PRECISION_WAIT_SPIN, GL_UI_SETTINGS_DIAL,
                                               GL_UI_ERROR, GL_UI_LOW_BATT, GL_UI_CRADLE_USB,
                                               GL_UI_CRADLE_SLEEP, GL_UI_CAL_ZERO };
    /* the tilt read is done, the cameras would start now */
    fresh();
    wake_up();
    ev(GL_EV_STILL, 0);
    STATE_IS(GL_UI_READ_TILT);
    a = ev(GL_EV_TOO_HOT, 0);
    STATE_IS(GL_UI_TOO_HOT);
    GL_CHECK((a & GL_ACT_ABORT_READ) && (a & GL_ACT_REDRAW) && (a & GL_ACT_DISPLAY_ON));
    GL_CHECK(!(a & GL_ACT_START_CAPTURE));
    /* nothing starts a read from here */
    GL_CHECK_EQ(ev(GL_EV_STILL, 0) & (GL_ACT_START_TILT | GL_ACT_START_CAPTURE), 0);
    GL_CHECK_EQ(ev(GL_EV_TILT_DONE, 0) & GL_ACT_START_CAPTURE, 0);
    GL_CHECK_EQ(ev(GL_EV_DOUBLE_TAP, 0) & (GL_ACT_START_TILT | GL_ACT_START_CAPTURE), 0);
    STATE_IS(GL_UI_TOO_HOT);
    GL_CHECK_EQ(gl_ui_timeout_ms(GL_UI_TOO_HOT), 4000);
    now += 3900;
    GL_CHECK_EQ(gl_ui_tick(&ui, now), 0);
    now += 200;
    a = gl_ui_tick(&ui, now);
    GL_CHECK(a & GL_ACT_ENTER_SLEEP);
    STATE_IS(GL_UI_SLEEP);
    /* from the capture itself (a read in a group of several) and while waking */
    fresh();
    wake_up();
    ev(GL_EV_STILL, 0);
    ev(GL_EV_TILT_DONE, 0);
    STATE_IS(GL_UI_CAPTURE);
    GL_CHECK(ev(GL_EV_TOO_HOT, 0) & GL_ACT_ABORT_READ);
    STATE_IS(GL_UI_TOO_HOT);
    fresh();
    wake_up();
    GL_CHECK(ev(GL_EV_TOO_HOT, 0) & GL_ACT_ABORT_READ);
    STATE_IS(GL_UI_TOO_HOT);
    /* the cradle takes it from there as from anywhere */
    a = ev(GL_EV_USB_ATTACH, 0);
    STATE_IS(GL_UI_CRADLE_USB);
    /* states the event leaves alone */
    for (size_t i = 0; i < sizeof(untouched) / sizeof(untouched[0]); i++) {
        fresh();
        ui.state = (uint8_t)untouched[i];
        GL_CHECK_EQ(ev(GL_EV_TOO_HOT, 0), 0);
        STATE_IS(untouched[i]);
    }
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
        v.solved = true;
        gl_ui_render(&ui, &v, &gfx);
        memcpy(first, gfx.px, sizeof(first));
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
    /* a fallback solution (E33, APPROX): long dashes, the numbers stay */
    v.show = GL_UI_SHOW_APPROX;
    v.note = GL_UI_NOTE_PACE;
    gl_ui_render(&ui, &v, &gfx);
    gl_ui_result_text(&ui, &v, &t);
    GL_CHECK(strcmp(t.brk, "<2.5 CUP") == 0);
    GL_CHECK(strcmp(t.plays, "PLAYS 16.1FT") == 0);
    GL_CHECK(strcmp(t.state, "APPROX") == 0);
    GL_CHECK(black_in_rows_(46, 88) < solid_mid - 60u); /* the line lost its gaps' worth of ink */
    GL_CHECK(black_in_rows_(46, 88) > solid_mid / 3u);  /* but it is there */
    v.show = GL_UI_SHOW_NORMAL;
    /* an aim that is not a solution (E33, NONE): the message, no line, no
     * break, no plays-like */
    v.solved = false;
    v.note = GL_UI_NOTE_NOT_SOLVED;
    gl_ui_render(&ui, &v, &gfx);
    gl_ui_result_text(&ui, &v, &t);
    GL_CHECK(t.brk[0] == '\0');
    GL_CHECK(t.plays[0] == '\0');
    GL_CHECK(t.state[0] == '\0');
    GL_CHECK(strcmp(t.note, "NOT SOLVED") == 0);
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
    /* Survey (E29): the drop number - and the line, at EVERY drop: the
     * placement the marker stands on is the ball.  The mark only touches
     * its own corner of the screen */
    v.drop = 3;
    gl_ui_result_text(&ui, &v, &t);
    GL_CHECK(strcmp(t.mode, "D3") == 0);
    GL_CHECK(t.note[0] == '\0');
    gl_ui_render(&ui, &v, &gfx);
    GL_CHECK_EQ(black_in_rows_(46, 88), solid_mid);
    n = gl_gfx_changed_rows(&gfx, plain.px, rows);
    GL_CHECK(n >= 7 && n <= 11);
    GL_CHECK(rows[0] >= 102 && rows[n - 1] <= 112);
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

/* ======================================================================= */
/* phase 3: E29 Survey, E30 Recall, E31 TOO STEEP, E33 three states, INFO   */
/* ======================================================================= */

/* The pixels an aim line of the given kind puts on an otherwise empty
 * screen, and of those the ones that lie in rows 46 .. 88 within 20 px of
 * the screen centre: there the result screen draws nothing over the line
 * when the fall-line rose is on a side (it is, for these aims). */
static gl_gfx_t line_solid_, line_dashed_;

static void line_ink_(const gl_ui_view_t *v, double *dash_ink, double *gap_ink)
{
    unsigned n_dash = 0, n_gap = 0, k_dash = 0, k_gap = 0;
    gl_gfx_init(&line_solid_);
    gl_gfx_init(&line_dashed_);
    gl_gfx_set_clip(&line_solid_, true);
    gl_gfx_set_clip(&line_dashed_, true);
    gl_gfx_aim_line_styled(&line_solid_, v->aim_rad + v->display_rot_rad,
                           v->ball_az_rad + v->display_rot_rad, 3.0f, false, NULL);
    gl_gfx_aim_line_styled(&line_dashed_, v->aim_rad + v->display_rot_rad,
                           v->ball_az_rad + v->display_rot_rad, 3.0f, true, NULL);
    for (int y = 46; y <= 88; y++) {
        for (int x = 44; x <= 84; x++) {
            const bool solid = !gl_gfx_get(&line_solid_, x, y);
            const bool dash = !gl_gfx_get(&line_dashed_, x, y);
            const bool here = !gl_gfx_get(&gfx, x, y);
            if (dash) {
                n_dash++;
                k_dash += here ? 1u : 0u;
            } else if (solid) {
                n_gap++;
                k_gap += here ? 1u : 0u;
            }
        }
    }
    *dash_ink = (n_dash > 0u) ? (double)k_dash / (double)n_dash : -1.0;
    *gap_ink = (n_gap > 0u) ? (double)k_gap / (double)n_gap : -1.0;
}

/* What stands where the confidence bar is: 'B' the five boxes (with this
 * many filled), 'A' the word APPROX, 'N' nothing, '?' anything else. */
static char bar_place_(int *filled)
{
    static gl_gfx_t ref;
    bool match;
    *filled = -1;
    for (int f = 0; f <= 5; f++) {
        gl_gfx_init(&ref);
        gl_gfx_conf_bar(&ref, 64 - 16, 105, f, 5);
        match = true;
        for (int y = 102; y <= 112 && match; y++) {
            for (int x = 44; x <= 84; x++) {
                if (gl_gfx_get(&ref, x, y) != gl_gfx_get(&gfx, x, y)) {
                    match = false;
                    break;
                }
            }
        }
        if (match) {
            *filled = f;
            return 'B';
        }
    }
    for (int pass = 0; pass < 2; pass++) {
        gl_gfx_init(&ref);
        if (pass == 0) {
            gl_gfx_text_centred(&ref, 64, 104, "APPROX", 1, GL_INK_BLACK);
        }
        match = true;
        for (int y = 102; y <= 112 && match; y++) {
            for (int x = 44; x <= 84; x++) {
                if (gl_gfx_get(&ref, x, y) != gl_gfx_get(&gfx, x, y)) {
                    match = false;
                    break;
                }
            }
        }
        if (match) {
            return (pass == 0) ? 'A' : 'N';
        }
    }
    return '?';
}

/* The state of the result screen, READ FROM THE FRAME BUFFER ALONE:
 *   NORMAL  ink in the dashes AND in the gaps of the line, the five boxes
 *   APPROX  ink in the dashes, none in the gaps, the word APPROX
 *   NONE    no ink where the line would be dashed (but for the letters of
 *           the message), nothing where the bar would be, AND the picture
 *           does not change when the aim does
 * Returns -1 if the screen is none of the three. */
static int state_from_pixels_(const gl_ui_view_t *v)
{
    static uint8_t first[GL_GFX_BYTES];
    double dash, gap;
    int filled;
    char bar;
    gl_ui_view_t w = *v;
    bool aim_matters;

    gl_ui_render(&ui, v, &gfx);
    memcpy(first, gfx.px, sizeof(first));
    w.aim_rad = v->aim_rad + 0.09f;
    gl_ui_render(&ui, &w, &gfx);
    aim_matters = memcmp(first, gfx.px, sizeof(first)) != 0;
    gl_ui_render(&ui, v, &gfx);
    line_ink_(v, &dash, &gap);
    bar = bar_place_(&filled);
    if (aim_matters && dash > 0.97 && gap > 0.97 && bar == 'B') {
        return GL_UI_SHOW_NORMAL;
    }
    if (aim_matters && dash > 0.97 && gap < 0.03 && bar == 'A') {
        return GL_UI_SHOW_APPROX;
    }
    if (!aim_matters && bar == 'N') {
        return GL_UI_SHOW_NONE;
    }
    return -1;
}

GL_TEST(test_three_display_states_are_unmistakable)
{
    static const float aims[] = { -0.05f, -0.02f, 0.0f, 0.013f, 0.05f };
    static const float rots[] = { 0.0f, 0.0209f, -0.0209f }; /* E12: up to 1.2 degrees */
    gl_ui_view_t v;
    unsigned n[3] = { 0, 0, 0 }, wrong = 0;
    double least_solid_gap = 1.0, most_dashed_gap = 0.0;

    gl_gfx_init(&gfx);
    fresh();
    ui.state = GL_UI_SHOW_RESULT;
    for (unsigned ai = 0; ai < sizeof(aims) / sizeof(aims[0]); ai++) {
        for (unsigned ri = 0; ri < sizeof(rots) / sizeof(rots[0]); ri++) {
            for (int show = 0; show < (int)GL_UI_SHOW_COUNT; show++) {
                for (int note = 0; note < (int)GL_UI_NOTE_COUNT; note++) {
                    for (int extra = 0; extra < 8; extra++) {
                        double dash, gap;
                        int got;
                        view_default(&v);
                        v.aim_rad = aims[ai];
                        v.display_rot_rad = rots[ri];
                        v.show = (uint8_t)show;
                        v.note = (uint8_t)note;
                        v.confidence = 0.2f * (float)(extra % 6);
                        v.drop = (extra & 1) ? 3u : 0u;
                        v.precision = (extra & 2) != 0;
                        v.recalled = (extra & 4) != 0;
                        v.age_s = 754u;
                        if (show == (int)GL_UI_SHOW_NONE) {
                            v.solved = false; /* (as the application composes it) */
                        }
                        got = state_from_pixels_(&v);
                        if (got != show) {
                            wrong++;
                        }
                        n[show]++;
                        line_ink_(&v, &dash, &gap);
                        if (show == (int)GL_UI_SHOW_NORMAL && gap < least_solid_gap) {
                            least_solid_gap = gap;
                        }
                        if (show == (int)GL_UI_SHOW_APPROX && gap > most_dashed_gap) {
                            most_dashed_gap = gap;
                        }
                    }
                }
            }
        }
    }
    GL_CHECK_EQ(wrong, 0u);
    printf("    %u NORMAL, %u APPROX and %u NONE result screens (5 aims, 3 display rotations, every "
           "message, with and without the Survey / Precision / recall marks): the state read from the "
           "frame buffer alone is the state rendered in every one\n", n[0], n[1], n[2]);
    printf("    ink in the gaps of the dash pattern: at least %.0f %% on a NORMAL screen, at most "
           "%.0f %% on an APPROX one\n", 100.0 * least_solid_gap, 100.0 * most_dashed_gap);
    GL_CHECK(least_solid_gap > 0.97 && most_dashed_gap < 0.03);

    /* THE RENDERER CAN ONLY BE MORE CAUTIOUS than the view says: a view
     * marked NORMAL is not drawn as one unless the aim is a solution of a
     * putt with a known distance and a measured flagstick */
    view_default(&v);
    GL_CHECK_EQ(gl_ui_view_show(&v), GL_UI_SHOW_NORMAL);
    v.flag_found = false;
    GL_CHECK_EQ(gl_ui_view_show(&v), GL_UI_SHOW_APPROX);
    GL_CHECK_EQ(state_from_pixels_(&v), GL_UI_SHOW_APPROX);
    view_default(&v);
    v.distance_assumed = true;
    GL_CHECK_EQ(gl_ui_view_show(&v), GL_UI_SHOW_APPROX);
    GL_CHECK_EQ(state_from_pixels_(&v), GL_UI_SHOW_APPROX);
    view_default(&v);
    v.distance_m = 0.0f;
    GL_CHECK_EQ(gl_ui_view_show(&v), GL_UI_SHOW_APPROX);
    v.distance_m = (float)NAN;
    GL_CHECK_EQ(gl_ui_view_show(&v), GL_UI_SHOW_APPROX);
    view_default(&v);
    v.solved = false;
    GL_CHECK_EQ(gl_ui_view_show(&v), GL_UI_SHOW_NONE);
    GL_CHECK_EQ(state_from_pixels_(&v), GL_UI_SHOW_NONE);
    view_default(&v);
    v.show = 7; /* a state that does not exist */
    GL_CHECK_EQ(gl_ui_view_show(&v), GL_UI_SHOW_NONE);
    GL_CHECK_EQ(state_from_pixels_(&v), GL_UI_SHOW_NONE);
    /* NONE never has an empty message */
    {
        gl_ui_result_text_t t;
        v.note = GL_UI_NOTE_NONE;
        gl_ui_result_text(&ui, &v, &t);
        GL_CHECK(strcmp(t.note, "NO SOLUTION") == 0);
        v.note = GL_UI_NOTE_ONE_CAMERA;
        gl_ui_result_text(&ui, &v, &t);
        GL_CHECK(strcmp(t.note, "NO SOLUTION") == 0);
        v.note = GL_UI_NOTE_TOO_STEEP;
        gl_ui_result_text(&ui, &v, &t);
        GL_CHECK(strcmp(t.note, "TOO STEEP") == 0);
    }
}

/* E33: every (aim source, solve status, flags) maps to exactly one state,
 * and no fallback maps to NORMAL.  The rule is written out here a second
 * time, as a list of what a NORMAL result must be. */
GL_TEST(test_every_estimate_maps_to_one_state)
{
    static const uint8_t sources[] = { 0, 1, 2, 3, 4, 77, 255 };
    static const uint8_t statuses[] = { 0, 1, 2, 3, 4, 5, 6, 100, 255 };
    static const float ratios[] = { 0.0f, 0.5f, 0.7999f, 0.80f, 0.95f, 3.0f, (float)INFINITY, (float)NAN };
    unsigned total = 0, by_state[3] = { 0, 0, 0 };
    unsigned by_cell[7][9][3];
    gl_ui_view_t v;

    memset(by_cell, 0, sizeof(by_cell));
    gl_gfx_init(&gfx);
    fresh();
    ui.state = GL_UI_SHOW_RESULT;
    for (unsigned si = 0; si < sizeof(sources); si++) {
        for (unsigned ti = 0; ti < sizeof(statuses); ti++) {
            for (unsigned flags = 0; flags < 128u; flags++) {
                for (unsigned ri = 0; ri < sizeof(ratios) / sizeof(ratios[0]); ri++) {
                    gl_ui_class_in_t in;
                    gl_ui_note_t note = GL_UI_NOTE_COUNT;
                    gl_ui_show_t show;
                    bool normal_allowed;

                    memset(&in, 0, sizeof(in));
                    in.aim_source = sources[si];
                    in.solve_status = statuses[ti];
                    in.flag_missing = (flags & 1u) != 0u;
                    in.range_missing = (flags & 2u) != 0u;
                    in.fit_converged = (flags & 4u) == 0u;
                    in.poor_horizon = (flags & 8u) != 0u;
                    in.distance_known = (flags & 16u) == 0u;
                    in.one_camera = (flags & 32u) != 0u;
                    in.ambiguous = (flags & 64u) != 0u;
                    in.steep_ratio = ratios[ri];
                    show = gl_ui_classify(&in, &note);
                    total++;
                    /* exactly one of the three, with a message that exists */
                    GL_CHECK((unsigned)show < (unsigned)GL_UI_SHOW_COUNT);
                    GL_CHECK((unsigned)note < (unsigned)GL_UI_NOTE_COUNT);
                    by_state[show]++;
                    by_cell[si][ti][show]++;
                    /* WHAT A NORMAL RESULT IS: solved on the fitted patch, at
                     * the pace set, flag and range measured, distance known,
                     * the fit converged, the horizon (if used) fitted, and
                     * not near the critical slope.  Nothing else. */
                    normal_allowed = in.aim_source == GL_AIM_FROM_PATCH &&
                                     in.solve_status == GL_SOLVE_OK && !in.flag_missing &&
                                     !in.range_missing && in.fit_converged && !in.poor_horizon &&
                                     in.distance_known && in.steep_ratio < GL_UI_STEEP_RATIO;
                    GL_CHECK_EQ(show == GL_UI_SHOW_NORMAL, normal_allowed);
                    /* a line only for a solution: aim source 0 or 1 with a
                     * status a solve can end with */
                    GL_CHECK_EQ(show != GL_UI_SHOW_NONE,
                                in.aim_source <= GL_AIM_FROM_PLANE && in.solve_status <= GL_SOLVE_NO_CONVERGENCE);
                    /* the message says why it is not normal */
                    if (show == GL_UI_SHOW_NORMAL) {
                        GL_CHECK(note == GL_UI_NOTE_NONE || note == GL_UI_NOTE_ONE_CAMERA ||
                                 note == GL_UI_NOTE_AMBIGUOUS);
                    } else {
                        GL_CHECK(note != GL_UI_NOTE_NONE && note != GL_UI_NOTE_ONE_CAMERA &&
                                 note != GL_UI_NOTE_AMBIGUOUS);
                    }
                    /* ... and the frame buffer shows that state (one ratio
                     * and one camera flag per cell: the screen does not
                     * depend on more) */
                    if (ri == 1u && (flags & 96u) == 0u) {
                        view_default(&v);
                        v.solved = (in.aim_source == GL_AIM_FROM_PATCH || in.aim_source == GL_AIM_FROM_PLANE);
                        v.show = (uint8_t)show;
                        v.note = (uint8_t)note;
                        v.flag_found = !in.flag_missing;
                        v.distance_assumed = in.flag_missing || in.range_missing;
                        v.distance_m = in.distance_known ? 4.4f : 0.0f;
                        GL_CHECK_EQ(state_from_pixels_(&v), (int)show);
                    }
                }
            }
        }
    }
    printf("    %u combinations of aim source (0-3 and 3 values that do not exist), solve status (0-5, "
           "NOT_RUN and 2 others), 7 flags and 8 steepness ratios: each maps to exactly one state - "
           "%u NORMAL, %u APPROX, %u NONE; NORMAL only for patch + OK with nothing missing\n",
           total, by_state[0], by_state[1], by_state[2]);
    printf("      aim source x solve status -> states reached (N normal, A approx, - none):\n");
    for (unsigned si = 0; si < 4u; si++) {
        printf("        source %u:", (unsigned)sources[si]);
        for (unsigned ti = 0; ti < 6u; ti++) {
            printf("  status %u %s%s%s", (unsigned)statuses[ti], by_cell[si][ti][0] ? "N" : "",
                   by_cell[si][ti][1] ? "A" : "", by_cell[si][ti][2] ? "-" : "");
        }
        printf("\n");
    }
    /* the knife-edge pair of the phase-2 final check: a kept near miss
     * (NO_CONVERGENCE) and PACE_LIMITED are the same state */
    {
        gl_ui_class_in_t in;
        gl_ui_note_t n1, n2;
        memset(&in, 0, sizeof(in));
        in.fit_converged = true;
        in.distance_known = true;
        in.steep_ratio = 0.5f;
        in.solve_status = GL_SOLVE_NO_CONVERGENCE;
        GL_CHECK_EQ(gl_ui_classify(&in, &n1), GL_UI_SHOW_APPROX);
        in.solve_status = GL_SOLVE_PACE_LIMITED;
        GL_CHECK_EQ(gl_ui_classify(&in, &n2), GL_UI_SHOW_APPROX);
        GL_CHECK_EQ(n1, GL_UI_NOTE_APPROX);
        GL_CHECK_EQ(n2, GL_UI_NOTE_PACE);
    }
}

/* E31: the ratio is the larger of the patch's slope at the ball and at the
 * hole over the critical slope a_r / ((5/7) g). */
GL_TEST(test_steep_ratio)
{
    const float a_r = 0.549f; /* Stimp 10 */
    const float s_crit = a_r / ((5.0f / 7.0f) * 9.80665f);
    GL_CHECK_NEAR(s_crit, 0.07838, 1e-4);
    GL_CHECK_NEAR(gl_ui_steep_ratio(0.03f, 0.04f, 0.0f, 0.0f, 5.0f, a_r), 0.05 / 0.07838, 1e-3);
    /* steeper at the hole: (0.03 + 0.004 * 5, 0.04) */
    GL_CHECK_NEAR(gl_ui_steep_ratio(0.03f, 0.04f, 0.004f, 0.0f, 5.0f, a_r),
                  sqrt(0.05 * 0.05 + 0.04 * 0.04) / 0.07838, 1e-3);
    /* flatter at the hole: the ball's slope counts */
    GL_CHECK_NEAR(gl_ui_steep_ratio(0.03f, 0.04f, -0.004f, 0.0f, 5.0f, a_r), 0.05 / 0.07838, 1e-3);
    GL_CHECK_NEAR(gl_ui_steep_ratio(0.0f, 0.02f, 0.0f, 0.008f, 5.0f, a_r), 0.06 / 0.07838, 1e-3);
    /* a faster green has a lower critical slope */
    GL_CHECK(gl_ui_steep_ratio(0.05f, 0.0f, 0.0f, 0.0f, 3.0f, 0.39f) >
             gl_ui_steep_ratio(0.05f, 0.0f, 0.0f, 0.0f, 3.0f, 0.92f));
    /* anything that is not a number, or no deceleration: steep */
    GL_CHECK(isinf(gl_ui_steep_ratio(0.01f, 0.0f, 0.0f, 0.0f, 3.0f, 0.0f)));
    GL_CHECK(isinf(gl_ui_steep_ratio(0.01f, 0.0f, 0.0f, 0.0f, 3.0f, -1.0f)));
    GL_CHECK(isinf(gl_ui_steep_ratio((float)NAN, 0.0f, 0.0f, 0.0f, 3.0f, a_r)));
    GL_CHECK(isinf(gl_ui_steep_ratio(0.01f, 0.0f, (float)NAN, 0.0f, 3.0f, a_r)));
    GL_CHECK(isinf(gl_ui_steep_ratio(0.01f, 0.0f, 0.0f, 0.0f, (float)NAN, a_r)));
    GL_CHECK(isinf(gl_ui_steep_ratio(0.01f, 0.0f, 0.0f, 0.0f, 3.0f, (float)NAN)));
    GL_CHECK(isinf(gl_ui_steep_ratio(1e30f, 1e30f, 0.0f, 0.0f, 3.0f, a_r)));
    /* the threshold in slope terms, for the record */
    printf("    TOO STEEP from %.2f of the critical slope: %.1f %% at Stimp 8, %.1f %% at Stimp 10, "
           "%.1f %% at Stimp 13\n", (double)GL_UI_STEEP_RATIO,
           100.0 * 0.80 * (1.83 * 1.83 / (2.0 * 8.0 * 0.3048)) / 7.00475,
           100.0 * 0.80 * (1.83 * 1.83 / (2.0 * 10.0 * 0.3048)) / 7.00475,
           100.0 * 0.80 * (1.83 * 1.83 / (2.0 * 13.0 * 0.3048)) / 7.00475);
}

/* Phase-3 review, application findings 7 (seed S30: the threshold moved
 * from 0.80 to 0.83 passed every test - none had a result between the two),
 * 9, 3, 4 and 10.
 *   - the TOO STEEP threshold from both sides: 0.79 is NORMAL, 0.81 and 0.82
 *     are TOO STEEP, through gl_ui_steep_ratio() on a patch of that slope;
 *   - THE EDGES OF E31, PINNED AS THEY ARE (owner decisions, README open
 *     issues): at and above the critical slope (ratio 1.03) a dashed line is
 *     still drawn; nothing in the classification lowers the confidence as
 *     the ratio rises toward the threshold;
 *   - the Survey mark says how many placements the result is made of;
 *   - "Z?" on a result whose seat has no level zero;
 *   - the PLAYS label and an aim line at the edge of the aperture: the white
 *     margin between them, measured. */
GL_TEST(test_result_screen_marks_of_the_review)
{
    const float a_r = 0.549f; /* Stimp 10 */
    const float s_crit = a_r / ((5.0f / 7.0f) * 9.80665f);
    static const float r_in[5] = { 0.79f, 0.81f, 0.82f, 1.03f, 1.30f };
    gl_ui_class_in_t in;
    gl_ui_result_text_t t;
    gl_ui_view_t v;
    gl_ui_note_t note;

    GL_CHECK_NEAR(GL_UI_STEEP_RATIO, 0.80, 1e-7);
    for (int i = 0; i < 5; i++) {
        const float ratio = gl_ui_steep_ratio(r_in[i] * s_crit, 0.0f, 0.0f, 0.0f, 4.0f, a_r);
        gl_ui_show_t show;
        GL_CHECK_NEAR(ratio, r_in[i], 1e-4);
        memset(&in, 0, sizeof(in));
        in.aim_source = (uint8_t)GL_AIM_FROM_PATCH;
        in.solve_status = (uint8_t)GL_SOLVE_OK;
        in.fit_converged = true;
        in.distance_known = true;
        in.steep_ratio = ratio;
        show = gl_ui_classify(&in, &note);
        if (i == 0) {
            GL_CHECK_EQ(show, GL_UI_SHOW_NORMAL);
            GL_CHECK_EQ(note, GL_UI_NOTE_NONE);
        } else {
            /* 0.81 and 0.82 (seed S30), and - PINNED, an owner decision -
             * 1.03 and 1.30, steeper than the slope a ball stops on: still a
             * line, dashed, "TOO STEEP" */
            GL_CHECK_EQ(show, GL_UI_SHOW_APPROX);
            GL_CHECK_EQ(note, GL_UI_NOTE_TOO_STEEP);
        }
    }
    printf("    ratio 0.79: NORMAL; 0.81, 0.82: TOO STEEP (dashed); PINNED, owner decision: 1.03 "
           "and 1.30 of the critical slope also draw a dashed TOO STEEP line (E31 names only "
           "\"close to\" that slope), and the confidence shown does not depend on the ratio\n");

    /* the Survey mark */
    fresh();
    ui.state = (uint8_t)GL_UI_SHOW_RESULT;
    view_default(&v);
    v.show = (uint8_t)GL_UI_SHOW_NORMAL;
    v.drop = 3;
    v.drops_used = 3;
    gl_ui_result_text(&ui, &v, &t);
    GL_CHECK(strcmp(t.mode, "D3") == 0);
    v.drops_used = 0; /* "not said": all of them */
    gl_ui_result_text(&ui, &v, &t);
    GL_CHECK(strcmp(t.mode, "D3") == 0);
    v.drops_used = 1;
    gl_ui_result_text(&ui, &v, &t);
    GL_CHECK(strcmp(t.mode, "D3/1") == 0);
    v.drop = 4;
    v.drops_used = 2;
    gl_ui_result_text(&ui, &v, &t);
    GL_CHECK(strcmp(t.mode, "D4/2") == 0);
    gl_ui_render(&ui, &v, &gfx);
    GL_CHECK_EQ(ink_outside(), 0u);

    /* "Z?": the zero of the seat is missing */
    view_default(&v);
    v.show = (uint8_t)GL_UI_SHOW_NORMAL;
    gl_ui_result_text(&ui, &v, &t);
    GL_CHECK(t.zero[0] == '\0');
    gl_ui_render(&ui, &v, &gfx);
    {
        static uint8_t without[GL_GFX_BYTES];
        unsigned diff = 0, diff_outside_box = 0;
        memcpy(without, gfx.px, sizeof(without));
        v.zero_missing = true;
        gl_ui_result_text(&ui, &v, &t);
        GL_CHECK(strcmp(t.zero, "Z?") == 0);
        gl_ui_render(&ui, &v, &gfx);
        for (int y = 0; y < GL_GFX_H; y++) {
            for (int x = 0; x < GL_GFX_W; x++) {
                static gl_gfx_t other;
                memcpy(other.px, without, sizeof(without));
                if (gl_gfx_get(&gfx, x, y) != gl_gfx_get(&other, x, y)) {
                    diff++;
                    if (x < 18 || x > 46 || y < 100 || y > 116) {
                        diff_outside_box++;
                    }
                }
            }
        }
        GL_CHECK(diff >= 10u);               /* it is on the screen */
        GL_CHECK_EQ(diff_outside_box, 0u);   /* ... at the lower left, and nowhere else */
        GL_CHECK_EQ(ink_outside(), 0u);
        GL_CHECK_EQ(gl_ui_view_show(&v), GL_UI_SHOW_NORMAL); /* the state is not changed by it */
    }

    /* the PLAYS label against a line at the edge of the aperture (the
     * reviewer's picture: 8 m, aim +200 mrad, "PLAYS 26.3FT") */
    {
        int w, x_end, x_start;
        unsigned min_gap = 999, rows_with_line = 0;
        view_default(&v);
        v.show = (uint8_t)GL_UI_SHOW_NORMAL;
        v.distance_m = 8.0f;
        v.plays_like_m = 8.02f;
        v.aim_rad = 0.200f;
        ui.edit.units = GL_UNITS_FEET;
        gl_ui_result_text(&ui, &v, &t);
        gl_ui_render(&ui, &v, &gfx);
        GL_CHECK(strstr(t.plays, "26.3FT") != NULL);
        w = gl_gfx_text_width(t.plays, 1);
        x_start = 64 - w / 2;
        x_end = x_start + w; /* first column right of the text */
        /* in the rows of the label (drawn at y 24): the first ink to the
         * right of the text and to its left - that is the aim line (or
         * nothing); its distance from the text */
        for (int y = 24; y < 24 + GL_FONT_H; y++) {
            for (int x = x_end; x < x_end + 12 && x < GL_GFX_W; x++) {
                if (!gl_gfx_get(&gfx, x, y)) {
                    const unsigned gap = (unsigned)(x - x_end);
                    min_gap = (gap < min_gap) ? gap : min_gap;
                    rows_with_line++;
                    break;
                }
            }
            for (int x = x_start - 1; x > x_start - 12 && x >= 0; x--) {
                if (!gl_gfx_get(&gfx, x, y)) {
                    const unsigned gap = (unsigned)(x_start - 1 - x);
                    min_gap = (gap < min_gap) ? gap : min_gap;
                    rows_with_line++;
                    break;
                }
            }
        }
        printf("    \"%s\" (%d pixels wide) with an aim line of +200 mrad: the line comes within "
               "%u white pixel%s of the label's text in %u of its rows (the label's box clears 2 "
               "pixels beside the text).  PINNED as measured; legibility on the real panel is NOT "
               "VERIFIED\n", t.plays, w, min_gap, (min_gap == 1u) ? "" : "s", rows_with_line);
        GL_CHECK(rows_with_line >= 1u); /* the line does pass the label in this picture */
        GL_CHECK(min_gap >= 2u);        /* ... and the box keeps its 2 white pixels */
        ui.edit.units = GL_UNITS_METRES;
    }
}

/* E29: the Survey on the table - 2 to 4 placements, a fifth is a new read,
 * a lift without a placement and a result left alone both end it. */
GL_TEST(test_survey_e29_flow)
{
    uint32_t a;
    fresh();
    wake_up();
    quick_read();
    ev(GL_EV_DOUBLE_TAP, 0);
    a = ev(GL_EV_DOUBLE_TAP, 0); /* Survey: the shown read is placement 1 */
    GL_CHECK(a & GL_ACT_SURVEY_STORE);
    STATE_IS(GL_UI_SURVEY_NEXT_DROP);
    GL_CHECK_EQ(ui.survey_count, 1);
    for (int k = 2; k <= 4; k++) {
        ev(GL_EV_MOTION, 0);
        a = ev(GL_EV_STILL, 0);
        GL_CHECK(a & GL_ACT_START_TILT);
        GL_CHECK_EQ(ui.read_kind, GL_READ_SURVEY);
        ev(GL_EV_TILT_DONE, 0);
        a = ev(GL_EV_CAPTURE_DONE, 0);
        GL_CHECK((a & GL_ACT_SURVEY_STORE) && (a & GL_ACT_START_SOLVE));
        GL_CHECK_EQ(ui.survey_count, k);
        ev(GL_EV_SOLVE_DONE, 0);
        STATE_IS(GL_UI_SHOW_RESULT); /* a result - with its line - after every placement */
        if (k < 4) {
            a = ev(GL_EV_MOTION, 0); /* picked up: on to the next */
            STATE_IS(GL_UI_SURVEY_NEXT_DROP);
            GL_CHECK(!(a & GL_ACT_NEW_READ));
        }
    }
    /* a FIFTH placement: the Survey is over, a new plain read */
    a = ev(GL_EV_MOTION, 0);
    STATE_IS(GL_UI_WAIT_STILL);
    GL_CHECK((a & GL_ACT_SURVEY_RESET) && (a & GL_ACT_NEW_READ));
    GL_CHECK_EQ(ui.survey_count, 0);
    GL_CHECK_EQ(ui.read_kind, GL_READ_QUICK);
    /* a lift without a new placement: 60 s, then asleep, the Survey gone,
     * and nothing to recall (it was lifted) */
    fresh();
    wake_up();
    quick_read();
    ev(GL_EV_DOUBLE_TAP, 0);
    ev(GL_EV_DOUBLE_TAP, 0);
    ev(GL_EV_MOTION, 0);
    now += 59000;
    GL_CHECK_EQ(gl_ui_tick(&ui, now), 0);
    now += 1100;
    a = gl_ui_tick(&ui, now);
    GL_CHECK((a & GL_ACT_SURVEY_RESET) && (a & GL_ACT_ENTER_SLEEP));
    STATE_IS(GL_UI_SLEEP);
    GL_CHECK(!ui.recall);
    /* a Survey result left for its 45 s: asleep, the Survey over; that
     * result can be recalled */
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
    now += 45100;
    a = gl_ui_tick(&ui, now);
    GL_CHECK((a & GL_ACT_SURVEY_RESET) && (a & GL_ACT_ENTER_SLEEP));
    GL_CHECK_EQ(ui.survey_count, 0);
    GL_CHECK(ui.recall);
    /* double tap on a Survey result ends the Survey and keeps the result */
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
    a = ev(GL_EV_DOUBLE_TAP, 0);
    GL_CHECK(a & GL_ACT_SURVEY_RESET);
    STATE_IS(GL_UI_SHOW_RESULT);
    /* the prompt no longer sends the golfer back: no "PUT AT BALL" anywhere */
    {
        gl_ui_view_t v;
        gl_ui_result_text_t t;
        view_default(&v);
        for (int d = 0; d <= 4; d++) {
            v.drop = (uint8_t)d;
            gl_ui_result_text(&ui, &v, &t);
            GL_CHECK(strstr(t.note, "PUT") == NULL);
        }
    }
}

/* E30 on the table: which paths keep the stored result recallable. */
GL_TEST(test_recall_table)
{
    uint32_t a;
    /* result -> 45 s -> sleep -> tap (wake-on-motion) -> at rest: recall */
    fresh();
    wake_up();
    quick_read();
    GL_CHECK(!ui.recall);
    now += 45100;
    a = gl_ui_tick(&ui, now);
    GL_CHECK(a & GL_ACT_ENTER_SLEEP);
    STATE_IS(GL_UI_SLEEP);
    GL_CHECK(ui.recall);
    a = ev(GL_EV_MOTION, 0);
    STATE_IS(GL_UI_WAKE);
    GL_CHECK(a & GL_ACT_DISPLAY_ON);
    GL_CHECK(ui.recall);
    now += 900;
    a = gl_ui_tick(&ui, now);
    STATE_IS(GL_UI_WAIT_STILL);
    GL_CHECK((a & GL_ACT_WATCH_STILL) && !(a & GL_ACT_NEW_READ)); /* the result is kept */
    a = ev(GL_EV_STILL, 0);
    STATE_IS(GL_UI_SHOW_RESULT);
    GL_CHECK(a & GL_ACT_RECALL);
    /* no read of any kind was started */
    GL_CHECK(!(a & (GL_ACT_START_TILT | GL_ACT_START_CAPTURE | GL_ACT_START_SOLVE)));
    /* shown for 45 s, then asleep again - and it can be recalled again */
    now += 44000;
    GL_CHECK_EQ(gl_ui_tick(&ui, now), 0);
    now += 1100;
    a = gl_ui_tick(&ui, now);
    GL_CHECK(a & GL_ACT_ENTER_SLEEP);
    GL_CHECK(ui.recall);

    /* LIFTED during the splash, or while waiting for stillness: a new read */
    for (int where = 0; where < 2; where++) {
        ev(GL_EV_MOTION, 0);
        if (where == 1) {
            now += 900;
            (void)gl_ui_tick(&ui, now);
        }
        a = ev(GL_EV_LIFTED, 0);
        GL_CHECK(a & GL_ACT_NEW_READ);
        GL_CHECK(!ui.recall);
        if (where == 0) {
            now += 900;
            a = gl_ui_tick(&ui, now);
            GL_CHECK(a & GL_ACT_NEW_READ);
        }
        STATE_IS(GL_UI_WAIT_STILL);
        a = ev(GL_EV_STILL, 0);
        GL_CHECK(a & GL_ACT_START_TILT);
        GL_CHECK(!(a & GL_ACT_RECALL));
        STATE_IS(GL_UI_READ_TILT);
        GL_CHECK_EQ(ui.read_kind, GL_READ_QUICK);
        ev(GL_EV_TILT_DONE, 0);
        ev(GL_EV_CAPTURE_DONE, 0);
        ev(GL_EV_SOLVE_DONE, 0);
        now += 45100;
        (void)gl_ui_tick(&ui, now);
        STATE_IS(GL_UI_SLEEP);
        GL_CHECK(ui.recall);
    }
    /* LIFTED is honoured in every state, also where it has no row */
    for (int s = 0; s < GL_UI_STATE_COUNT; s++) {
        fresh();
        ui.state = (uint8_t)s;
        ui.recall = true;
        (void)ev(GL_EV_LIFTED, 0);
        GL_CHECK(!ui.recall);
    }
    /* everything else that happens between the result and the tap ends it:
     * a result that left the screen any other way, the cradle, the dial,
     * low battery, a fault, too hot, the time limit of the wait */
    {
        static const gl_ui_event_t killers[] = { GL_EV_USB_ATTACH, GL_EV_BATT_LOW, GL_EV_FAULT,
                                                 GL_EV_UPRIGHT, GL_EV_TOO_HOT, GL_EV_FORCE_SLEEP };
        for (unsigned k = 0; k < sizeof(killers) / sizeof(killers[0]); k++) {
            for (int where = 0; where < 3; where++) { /* asleep, splash, waiting */
                fresh();
                wake_up();
                quick_read();
                now += 45100;
                (void)gl_ui_tick(&ui, now);
                GL_CHECK(ui.recall);
                if (where >= 1) {
                    ev(GL_EV_MOTION, 0);
                }
                if (where >= 2) {
                    now += 900;
                    (void)gl_ui_tick(&ui, now);
                }
                if (where == 0 && (killers[k] == GL_EV_UPRIGHT || killers[k] == GL_EV_BATT_LOW ||
                                   killers[k] == GL_EV_TOO_HOT || killers[k] == GL_EV_FORCE_SLEEP)) {
                    continue; /* (ignored while asleep: nothing has changed) */
                }
                (void)ev(killers[k], GL_ERR_IO);
                GL_CHECK(!ui.recall);
            }
        }
        /* the marker never came to rest (20 s) */
        fresh();
        wake_up();
        quick_read();
        now += 45100;
        (void)gl_ui_tick(&ui, now);
        ev(GL_EV_MOTION, 0);
        now += 900;
        (void)gl_ui_tick(&ui, now);
        now += 20100;
        (void)gl_ui_tick(&ui, now);
        STATE_IS(GL_UI_SLEEP);
        GL_CHECK(!ui.recall);
        /* picked up while the result was shown: a new read, no recall */
        fresh();
        wake_up();
        quick_read();
        ev(GL_EV_MOTION, 0);
        STATE_IS(GL_UI_WAIT_STILL);
        GL_CHECK(!ui.recall);
        now += 20100;
        (void)gl_ui_tick(&ui, now);
        STATE_IS(GL_UI_SLEEP);
        GL_CHECK(!ui.recall);
        ev(GL_EV_MOTION, 0);
        now += 900;
        a = gl_ui_tick(&ui, now);
        GL_CHECK(a & GL_ACT_NEW_READ);
    }
    /* the age on the screen */
    {
        gl_ui_view_t v;
        gl_ui_result_text_t t;
        static const struct { uint32_t s; const char *text; } ages[] = {
            { 0u, "0S AGO" }, { 59u, "59S AGO" }, { 60u, "1M AGO" }, { 754u, "12M AGO" },
            { 3599u, "59M AGO" }, { 3600u, "1H AGO" }, { 172799u, "47H AGO" }, { 172800u, "2D AGO" },
            { 8640000u, "99D AGO" }, { 0xFFFFFFFFu, "99D AGO" },
        };
        view_default(&v);
        gl_ui_result_text(&ui, &v, &t);
        GL_CHECK(t.age[0] == '\0');
        v.recalled = true;
        gl_gfx_init(&gfx);
        ui.state = GL_UI_SHOW_RESULT;
        for (unsigned i = 0; i < sizeof(ages) / sizeof(ages[0]); i++) {
            static gl_gfx_t plain;
            uint8_t rows[GL_GFX_H];
            unsigned n;
            v.age_s = ages[i].s;
            gl_ui_result_text(&ui, &v, &t);
            GL_CHECK(strcmp(t.age, ages[i].text) == 0);
            GL_CHECK(strlen(t.age) <= 7u);
            /* drawn whole (nothing of it is cut by the round aperture), and
             * it only touches its own rows */
            v.recalled = false;
            gl_ui_render(&ui, &v, &plain);
            v.recalled = true;
            gl_ui_render(&ui, &v, &gfx);
            GL_CHECK_EQ(ink_outside(), 0);
            n = gl_gfx_changed_rows(&gfx, plain.px, rows);
            GL_CHECK(n >= 7u && n <= 11u);
            GL_CHECK(rows[0] >= 112 && rows[n - 1u] <= 122);
            {
                static gl_gfx_t ref;
                unsigned differ = 0;
                gl_gfx_init(&ref);
                gl_gfx_set_clip(&ref, false);
                gl_gfx_text_centred(&ref, 64, 114, t.age, 1, GL_INK_BLACK);
                for (int y = 114; y < 114 + GL_FONT_H; y++) {
                    for (int x = 64 - 22; x <= 64 + 22; x++) {
                        differ += (gl_gfx_get(&ref, x, y) != gl_gfx_get(&gfx, x, y)) ? 1u : 0u;
                    }
                }
                GL_CHECK_EQ(differ, 0u);
            }
        }
    }
}

/* The regulatory and information screen (the INFO item of the dial). */
GL_TEST(test_info_screen)
{
    static const unsigned want[GL_UI_INFO_LINES] = { 12, 15, 17, 19, 19, 20, 19, 18, 17, 15 };
    gl_ui_view_t v;
    unsigned cells = 0;
    uint32_t a;

    /* ---- how many characters fit: every line holds what the table says,
     *      whole, and one character more would be cut by the aperture ---- */
    for (unsigned line = 0; line < GL_UI_INFO_LINES; line++) {
        static gl_gfx_t clipped, open_;
        char buf[GL_UI_INFO_LINE_MAX + 3u];
        int x = 0, y = 0;
        const unsigned n = gl_ui_info_line_chars(line, &x, &y);
        GL_CHECK_EQ(n, want[line]);
        GL_CHECK(n <= GL_UI_INFO_LINE_MAX);
        cells += n;
        for (unsigned extra = 0; extra <= 2u; extra += 2u) {
            memset(buf, '#', n + extra);
            buf[n + extra] = '\0';
            gl_gfx_init(&clipped);
            gl_gfx_init(&open_);
            gl_gfx_set_clip(&clipped, true);
            gl_gfx_set_clip(&open_, false);
            (void)gl_gfx_text(&clipped, x - (int)extra * GL_FONT_ADVANCE / 2, y, buf, 1, GL_INK_BLACK);
            (void)gl_gfx_text(&open_, x - (int)extra * GL_FONT_ADVANCE / 2, y, buf, 1, GL_INK_BLACK);
            if (extra == 0u) {
                GL_CHECK_EQ(gl_gfx_count_black(&clipped), gl_gfx_count_black(&open_));
            } else {
                /* one more on each side: no longer whole */
                GL_CHECK(gl_gfx_count_black(&clipped) < gl_gfx_count_black(&open_));
            }
        }
    }
    GL_CHECK_EQ(gl_ui_info_line_chars(GL_UI_INFO_LINES, NULL, NULL), 0u);
    GL_CHECK_EQ(cells, 171u);
    GL_CHECK_EQ(gl_ui_info_page_chars(), 171u);
    printf("    regulatory text: 10 lines of 12/15/17/19/19/20/19/18/17/15 characters = %u cells per "
           "page, %u text pages = %u cells (words are not broken, so a text needs a little less)\n",
           cells, (unsigned)GL_UI_INFO_TEXT_PAGES, cells * (unsigned)GL_UI_INFO_TEXT_PAGES);

    /* ---- layout: counting ---- */
    {
        static char text[1200];
        size_t shown = 0;
        GL_CHECK_EQ(gl_ui_info_fit(NULL, &shown), 0u);
        GL_CHECK_EQ(shown, 0u);
        GL_CHECK_EQ(gl_ui_info_fit("", &shown), 0u);
        GL_CHECK_EQ(gl_ui_info_pages(NULL), 1u);
        /* one unbroken run of 171 characters is exactly one page; 172 need two */
        memset(text, 'X', 171);
        text[171] = '\0';
        GL_CHECK_EQ(gl_ui_info_fit(text, &shown), 1u);
        GL_CHECK_EQ(shown, 171u);
        text[171] = 'X';
        text[172] = '\0';
        GL_CHECK_EQ(gl_ui_info_fit(text, &shown), 2u);
        GL_CHECK_EQ(gl_ui_info_pages(text), 3u);
        /* 684 fit the four pages; of 700 only 684 are shown and the caller is told */
        memset(text, 'X', 700);
        text[684] = '\0';
        GL_CHECK_EQ(gl_ui_info_fit(text, &shown), 4u);
        GL_CHECK_EQ(shown, 684u);
        text[684] = 'X';
        text[700] = '\0';
        GL_CHECK_EQ(gl_ui_info_fit(text, &shown), 5u);
        GL_CHECK_EQ(shown, 684u);
        GL_CHECK_EQ(gl_ui_info_pages(text), 1u + GL_UI_INFO_TEXT_PAGES);
        /* words are kept whole; a new line is honoured */
        GL_CHECK_EQ(gl_ui_info_fit("AB\nCD\nEF", &shown), 1u);
        GL_CHECK_EQ(shown, 8u);
        /* the placeholder that ships fits, whole, on one page */
        GL_CHECK_EQ(gl_ui_info_fit(GL_REGULATORY_TEXT, &shown), 1u);
        GL_CHECK_EQ(shown, strlen(GL_REGULATORY_TEXT));
        GL_CHECK_EQ(GL_REGULATORY_TEXT_IS_PLACEHOLDER, 1);
        /* a statement of the length DESIGN_SPEC E18 gives a legend block
         * (88 characters) four times over, as ordinary words */
        text[0] = '\0';
        for (int k = 0; k < 4; k++) {
            strcat(text, "THIS IS A STATEMENT OF EIGHTY-EIGHT CHARACTERS, SPACES COUNTED, AS A "
                         "LEGEND BLOCK HOLDS. ");
        }
        GL_CHECK_EQ(strlen(text), 4u * 89u);
        GL_CHECK(gl_ui_info_fit(text, &shown) <= 3u);
        GL_CHECK_EQ(shown, strlen(text));
        printf("    four statements of 88 characters (DESIGN_SPEC E18's legend block) need %u of the %u "
               "text pages\n", gl_ui_info_fit(text, NULL), (unsigned)GL_UI_INFO_TEXT_PAGES);
    }

    /* ---- the dial reaches it, rolling turns its pages, nothing is set ---- */
    fresh();
    wake_up();
    ev(GL_EV_UPRIGHT, 0);
    for (int i = 0; i < (int)GL_UI_ITEM_INFO; i++) {
        a = ev(GL_EV_DOUBLE_TAP, 0);
        GL_CHECK(a & GL_ACT_DIAL_BEGIN);
    }
    GL_CHECK_EQ(ui.item, GL_UI_ITEM_INFO);
    GL_CHECK_EQ(ui.dial_value, 0);
    view_default(&v);
    v.info_hw = 'E';
    v.info_fw = 0x0003u;
    memcpy(v.info_serial, "1A2B3C4", 8);
    v.info_text = "FIRST PAGE OF TEXT.";
    ui.info_pages = (uint8_t)gl_ui_info_pages(v.info_text);
    GL_CHECK_EQ(ui.info_pages, 2);
    {
        static gl_gfx_t ref;
        static const struct { int y, scale; const char *s; } lines[] = {
            { 6, 1, "1/2" }, { 18, 1, "GREENLINE" }, { 30, 2, "GL-1" }, { 50, 1, "PRACTICE DEVICE" },
            { 62, 1, "HW E  FW 0.3" }, { 74, 1, "SN 1A2B3C4" }, { 90, 1, "ROLL: MORE" },
        };
        gl_gfx_init(&gfx);
        gl_ui_render(&ui, &v, &gfx);
        GL_CHECK_EQ(ink_outside(), 0);
        /* page 1: every line is on the screen, glyph for glyph, uncut */
        for (unsigned i = 0; i < sizeof(lines) / sizeof(lines[0]); i++) {
            unsigned differ = 0;
            gl_gfx_init(&ref);
            gl_gfx_set_clip(&ref, false);
            gl_gfx_text_centred(&ref, 64, lines[i].y, lines[i].s, lines[i].scale, GL_INK_BLACK);
            for (int y = lines[i].y; y < lines[i].y + GL_FONT_H * lines[i].scale; y++) {
                for (int x = 0; x < 128; x++) {
                    differ += (gl_gfx_get(&ref, x, y) != gl_gfx_get(&gfx, x, y)) ? 1u : 0u;
                }
            }
            GL_CHECK_EQ(differ, 0u);
        }
        /* rolled on: the text page */
        a = ev(GL_EV_DIAL_STEP, 1);
        GL_CHECK(a & GL_ACT_REDRAW);
        GL_CHECK_EQ(ui.dial_value, 1);
        gl_ui_render(&ui, &v, &gfx);
        GL_CHECK_EQ(ink_outside(), 0);
        {
            int x = 0, y = 0;
            unsigned differ = 0;
            (void)gl_ui_info_line_chars(0, &x, &y);
            gl_gfx_init(&ref);
            gl_gfx_set_clip(&ref, false);
            (void)gl_gfx_text(&ref, x, y, "FIRST PAGE", 1, GL_INK_BLACK);
            (void)gl_ui_info_line_chars(1, &x, &y);
            (void)gl_gfx_text(&ref, x, y, "OF TEXT.", 1, GL_INK_BLACK);
            for (int yy = 16; yy < 16 + 18; yy++) {
                for (int xx = 0; xx < 128; xx++) {
                    differ += (gl_gfx_get(&ref, xx, yy) != gl_gfx_get(&gfx, xx, yy)) ? 1u : 0u;
                }
            }
            GL_CHECK_EQ(differ, 0u);
        }
        /* the dial stops at the last page */
        ev(GL_EV_DIAL_STEP, 9);
        GL_CHECK_EQ(ui.dial_value, 1);
        ev(GL_EV_DIAL_STEP, -3);
        GL_CHECK_EQ(ui.dial_value, 0);
    }
    /* no serial known: dashes, not garbage; a hardware letter that is none: '?' */
    {
        static gl_gfx_t ref;
        unsigned differ = 0;
        v.info_serial[0] = '\0';
        v.info_hw = 0;
        gl_ui_render(&ui, &v, &gfx);
        gl_gfx_init(&ref);
        gl_gfx_set_clip(&ref, false);
        gl_gfx_text_centred(&ref, 64, 62, "HW ?  FW 0.3", 1, GL_INK_BLACK);
        gl_gfx_text_centred(&ref, 64, 74, "SN -------", 1, GL_INK_BLACK);
        for (int y = 62; y < 81; y++) {
            for (int x = 0; x < 128; x++) {
                differ += (gl_gfx_get(&ref, x, y) != gl_gfx_get(&gfx, x, y)) ? 1u : 0u;
            }
        }
        GL_CHECK_EQ(differ, 0u);
    }
    /* laid flat: out of the dial as from any item; settings unchanged */
    {
        const gl_settings_t before = ui.saved;
        a = ev(GL_EV_FLAT, 0);
        STATE_IS(GL_UI_WAIT_STILL);
        GL_CHECK(!(a & GL_ACT_CAL_ZERO_START));
        GL_CHECK(memcmp(&before, &ui.edit, sizeof(before)) == 0);
    }
    /* double tap on INFO wraps round to the first item */
    ev(GL_EV_UPRIGHT, 0);
    for (int i = 0; i < (int)GL_UI_ITEM_COUNT; i++) {
        ev(GL_EV_DOUBLE_TAP, 0);
    }
    GL_CHECK_EQ(ui.item, GL_ITEM_STIMP);
    /* the sizes the README quotes */
    printf("    sizeof(gl_ui_t) %u, sizeof(gl_ui_view_t) %u\n", (unsigned)sizeof(gl_ui_t),
           (unsigned)sizeof(gl_ui_view_t));
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
    GL_RUN(test_cradle_and_too_hot_screens);
    GL_RUN(test_too_hot_stops_a_read_and_sleeps);
    GL_RUN(test_result_screen_shows_the_aim_line);
    GL_RUN(test_result_screen_messages_and_tentative_line);
    GL_RUN(test_render_with_hostile_view_values);
    GL_RUN(test_double_tap_on_a_precision_result_is_a_survey);
    GL_RUN(test_distance_prompt_is_left_by_re_placing);
    GL_RUN(test_result_screen_is_turned_round_with_the_marker);
    GL_RUN(test_notes_of_the_review);
    GL_RUN(test_three_display_states_are_unmistakable);
    GL_RUN(test_every_estimate_maps_to_one_state);
    GL_RUN(test_steep_ratio);
    GL_RUN(test_result_screen_marks_of_the_review);
    GL_RUN(test_survey_e29_flow);
    GL_RUN(test_recall_table);
    GL_RUN(test_info_screen);
    return gl_test_summary();
}
