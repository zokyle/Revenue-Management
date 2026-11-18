/*
 * test_e2e_recall.c - DESIGN_SPEC E30, Recall, with the whole firmware on
 * the simulator: a single tap on a marker that has not been lifted since
 * its last result shows that result again for 45 s with its age, without a
 * camera read.
 *
 * The marker is ASLEEP when it is tapped (the result has left the screen
 * after its 45 s): the tap is what the IMU's wake-on-motion fires on.  What
 * "not lifted" means is decided from the motion data (app/gl_app.c,
 * recall_watch_; the constants in app/gl_app_cfg.h).  The boundary is
 * tested here from both sides:
 *
 *   recalled                          a new read instead
 *   a tap (60 ms)                     a shove of 0.6 s
 *   a nudge of 0.2 s                  a nudge after which it lies 6 mrad
 *   ... after which it lies             differently
 *       2 mrad differently            a twist of 5 degrees on the spot
 *   a twist of 1 degree               lifted and put back on the same spot
 *                                     twisted by 10 degrees while the result
 *                                       was still on the screen
 *                                     a Precision spin begun and given up
 *
 * Also here, because it is application behaviour of the same phase: the
 * regulatory and information screen reached from the settings dial.
 *
 * NOT VERIFIED on hardware (there is none): that a tap trips the IMU's
 * wake-on-motion at the provisional threshold, and how long the IMU takes
 * from that interrupt to its first sample (a movement that is over before
 * the first sample is not seen).
 */
#include "gl_e2e_world.h"

static uint32_t now_ms_(void)
{
    return (uint32_t)(gl_sim_now_us() / 1000u);
}

/* Number of records in the log, and a CRC over their payloads. */
static unsigned log_records_(uint32_t *crc_out)
{
    static uint8_t buf[1024];
    gl_log_iter_t it;
    gl_log_rec_t info;
    unsigned n = 0;
    uint32_t crc = 0;
    gl_status_t st;
    gl_log_iter_begin(&app.log, &it);
    while ((st = gl_log_iter_next(&app.log, &it, &info, buf, sizeof(buf))) != GL_ERR_EMPTY) {
        if (st == GL_OK) {
            crc = gl_crc32_update(crc, buf, (info.len <= sizeof(buf)) ? info.len : sizeof(buf));
        }
        n++;
    }
    *crc_out = crc;
    return n;
}

/* A read on the default green, left alone until the marker sleeps. */
static void read_and_sleep_(void)
{
    world_defaults_();
    board_up_(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    watch_reset_();
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 12000));
    GL_CHECK(app.view.have_result && !app.view.recalled);
    GL_CHECK_EQ(gl_ui_view_show(&app.view), GL_UI_SHOW_NORMAL);
    GL_CHECK(run_until_state_(GL_UI_SLEEP, now_ms_() + 47000u));
    GL_CHECK(!app.awake);
    GL_CHECK(app.ui.recall);
    GL_CHECK(!app.recall_spoiled);
    /* some time asleep (housekeeping wake-ups pass: they are not motion) */
    run_until_ms_(now_ms_() + 40000u);
    GL_CHECK_EQ(app.ui.state, GL_UI_SLEEP);
    GL_CHECK(app.ui.recall);
}

/* What the world does to the sleeping marker. */
typedef struct {
    const char *name;
    double jolt_len_s;          /* a tap or a shove of this length (0.15 g at 9 Hz) */
    double tilt_step_mrad;      /* afterwards it lies this much differently */
    double turn_deg, turn_len_s;/* it is turned on the spot */
    double lift_s;              /* it is in the hand for this long, then back on the same spot */
    bool recall;                /* expected: the stored result again (else a new read) */
} act_t;

static void act_(const act_t *a, double at_s)
{
    if (a->lift_s > 0.0) {
        W.t_pick_s = at_s;
        W.t_place_s = at_s + a->lift_s;
    } else {
        W.jolt_at_s = at_s;
        W.jolt_len_s = a->jolt_len_s;
    }
    if (a->tilt_step_mrad != 0.0) {
        W.tilt_step_at_s = at_s + 0.5 * a->jolt_len_s;
        W.tilt_step_x = 0.001 * a->tilt_step_mrad;
        W.tilt_step_y = 0.0;
    }
    if (a->turn_deg != 0.0) {
        W.turn_at_s = at_s;
        W.turn_len_s = a->turn_len_s;
        W.turn_rad = a->turn_deg * PI_D / 180.0;
    }
}

/* ======================================================================= */
/* 1. the tap                                                               */
/* ======================================================================= */

GL_TEST(test_tap_recalls_the_result_without_a_read)
{
    static uint8_t shown_first[GL_GFX_BYTES];
    gl_ui_view_t first;
    gl_estimate_t est_first;
    gl_ui_result_text_t t;
    uint32_t crc0 = 0, crc1 = 0, t_result_ms, t_tap_ms, t_shown_ms;
    unsigned n0, reads0;
    uint64_t rail0;
    const act_t tap = { "tap", 0.06, 0.0, 0.0, 0.0, 0.0, true };

    world_defaults_();
    board_up_(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    watch_reset_();
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 12000));
    run_until_ms_(now_ms_() + 50u);
    t_result_ms = app.ui.state_since_ms;
    first = app.view;
    est_first = app.est;
    memcpy(shown_first, gl_sim_lcd()->mem, sizeof(shown_first));
    GL_CHECK(run_until_state_(GL_UI_SLEEP, now_ms_() + 47000u));
    GL_CHECK_NEAR((double)(app.ui.state_since_ms - t_result_ms), 45000.0, 60.0);
    run_until_ms_(now_ms_() + 75000u); /* two minutes after the result */
    GL_CHECK_EQ(app.ui.state, GL_UI_SLEEP);
    n0 = log_records_(&crc0);
    reads0 = app.reads_total;
    rail0 = gl_sim_stats()->cam_rail_cycles;
    GL_CHECK_EQ(rail0, 1u);

    /* ---- the tap ---- */
    t_tap_ms = now_ms_() + 500u;
    act_(&tap, 0.001 * (double)t_tap_ms);
    watch_reset_();
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, t_tap_ms + 5000u));
    t_shown_ms = app.ui.state_since_ms;
    run_until_ms_(now_ms_() + 50u);
    print_seen_();
    /* SLEEP -> WAKE -> WAIT_STILL -> SHOW_RESULT: no tilt read, no capture, no solve */
    GL_CHECK_EQ(seen.n, 4u);
    GL_CHECK_EQ(seen.state[1], GL_UI_WAKE);
    GL_CHECK_EQ(seen.state[2], GL_UI_WAIT_STILL);
    GL_CHECK_EQ(seen.state[3], GL_UI_SHOW_RESULT);
    printf("    result back on the screen %.2f s after the tap\n", 0.001 * (double)(t_shown_ms - t_tap_ms));
    GL_CHECK(t_shown_ms - t_tap_ms < 2000u);
    /* NO CAMERA: the rail was never switched on, no frame was rendered, the
     * fast clock was not asked for, the estimator did not run */
    GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, rail0);
    GL_CHECK(!gl_sim_cam_rail_on());
    GL_CHECK_EQ(seen.rail_outside_capture, 0u);
    GL_CHECK_EQ(gl_sim_stats()->trace_points[GL_TRACE_SOLVE], 1u);
    GL_CHECK_EQ(app.reads_total, reads0);
    GL_CHECK_EQ(app.recalls, 1u);
    /* nothing was written to the log */
    GL_CHECK_EQ(log_records_(&crc1), n0);
    GL_CHECK_EQ(crc1, crc0);
    /* THE SAME RESULT: every field of the view but the recall mark and the age */
    {
        gl_ui_view_t v = app.view;
        GL_CHECK(v.recalled);
        GL_CHECK_NEAR((double)v.age_s, 0.001 * (double)(t_shown_ms - t_result_ms), 1.5);
        v.recalled = first.recalled;
        v.age_s = first.age_s;
        v.battery_pct = first.battery_pct;
        GL_CHECK(memcmp(&v, &first, sizeof(v)) == 0);
        GL_CHECK(memcmp(&app.est, &est_first, sizeof(est_first)) == 0);
    }
    /* ... and on the panel: the first screen, plus the age in its own rows */
    {
        unsigned other_rows = 0, age_rows = 0;
        GL_CHECK_EQ(panel_differs_from_framebuffer_(), 0u);
        for (unsigned y = 0; y < 128u; y++) {
            if (memcmp(&gl_sim_lcd()->mem[y * 16u], &shown_first[y * 16u], 16) != 0) {
                if (y >= 112u && y <= 122u) {
                    age_rows++;
                } else {
                    other_rows++;
                }
            }
        }
        GL_CHECK_EQ(other_rows, 0u);
        GL_CHECK(age_rows >= 7u);
        gl_ui_result_text(&app.ui, &app.view, &t);
        printf("    age shown: \"%s\" (the result was made %.0f s before)\n", t.age,
               0.001 * (double)(t_shown_ms - t_result_ms));
        GL_CHECK(strcmp(t.age, "2M AGO") == 0);
    }
    /* shown for 45 s, then asleep again */
    GL_CHECK(run_until_state_(GL_UI_SLEEP, now_ms_() + 47000u));
    GL_CHECK_NEAR((double)(app.ui.state_since_ms - t_shown_ms), 45000.0, 60.0);
    /* tapped again a quarter of an hour later: the same result, older */
    run_until_ms_(now_ms_() + 900000u);
    t_tap_ms = now_ms_() + 500u;
    act_(&tap, 0.001 * (double)t_tap_ms);
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, t_tap_ms + 5000u));
    run_until_ms_(now_ms_() + 50u);
    gl_ui_result_text(&app.ui, &app.view, &t);
    GL_CHECK(app.view.recalled);
    GL_CHECK(strcmp(t.age, "17M AGO") == 0 || strcmp(t.age, "18M AGO") == 0);
    GL_CHECK_EQ(app.recalls, 2u);
    GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, rail0);
    GL_CHECK_EQ(log_records_(&crc1), n0);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
    /* picked up from the recalled result: a new read, like from any result */
    {
        const double t0 = 0.001 * (double)now_ms_();
        W.jolt_len_s = 0.0;
        W.t_pick_s = t0 + 0.5;
        W.t_place_s = t0 + 1.5;
        GL_CHECK(run_until_state_(GL_UI_CAPTURE, now_ms_() + 8000u));
        GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, now_ms_() + 8000u));
        GL_CHECK(!app.view.recalled);
        GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, rail0 + 1u);
        GL_CHECK_EQ(app.reads_total, reads0 + 1u);
    }
}

/* ======================================================================= */
/* 2. the boundary of "not lifted"                                          */
/* ======================================================================= */

GL_TEST(test_what_is_a_lift_and_what_is_not)
{
    static const act_t acts[] = {
        /* name                                         jolt  step  turn  len  lift  recall */
        { "a tap (60 ms)",                               0.06, 0.0,  0.0, 0.0,  0.0, true },
        { "a nudge of 0.2 s",                            0.20, 0.0,  0.0, 0.0,  0.0, true },
        { "a nudge, then lying 2 mrad differently",      0.20, 2.0,  0.0, 0.0,  0.0, true },
        { "a tap and a twist of 1 degree",               0.06, 0.0,  1.0, 0.15, 0.0, true },
        { "a shove of 0.6 s",                            0.60, 0.0,  0.0, 0.0,  0.0, false },
        { "a nudge, then lying 6 mrad differently",      0.20, 6.0,  0.0, 0.0,  0.0, false },
        { "a tap and a twist of 5 degrees",              0.06, 0.0,  5.0, 0.20, 0.0, false },
        { "a slow twist of 5 degrees (1.5 s)",           0.06, 0.0,  5.0, 1.50, 0.0, false },
        { "lifted for 1.2 s, back on the same spot",     0.0,  0.0,  0.0, 0.0,  1.2, false },
        { "lifted for 0.5 s, back on the same spot",     0.0,  0.0,  0.0, 0.0,  0.5, false },
        { "lifted for 4 s, back, turned by 0.5 degree",  0.0,  0.0,  0.5, 4.0,  4.0, false },
    };
    printf("    %-44s | outcome        | rail cycles |\n", "what happens to the sleeping marker");
    for (size_t i = 0; i < GL_ARRAY_LEN(acts); i++) {
        const act_t *a = &acts[i];
        uint32_t t0;
        bool recalled;
        read_and_sleep_();
        t0 = now_ms_() + 400u;
        act_(a, 0.001 * (double)t0);
        watch_reset_();
        GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, t0 + 14000u));
        run_until_ms_(now_ms_() + 30u);
        recalled = app.view.recalled;
        printf("    %-44s | %-14s | %11lu |", a->name, recalled ? "RECALL" : "a new read",
               (unsigned long)gl_sim_stats()->cam_rail_cycles);
        if (recalled) {
            printf(" %u moving block%s after the wake-up (limit %u)", (unsigned)app.recall_moving,
                   (app.recall_moving == 1u) ? "" : "s", (unsigned)GL_APP_RECALL_MOVING_BLOCKS);
        }
        printf("\n");
        GL_CHECK_EQ(recalled, a->recall);
        if (a->recall) {
            GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, 1u);
            GL_CHECK_EQ(app.reads_total, 1u);
            GL_CHECK_EQ(seen.n, 4u);
        } else {
            /* a complete new read: tilt, cameras, solve */
            GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, 2u);
            GL_CHECK_EQ(app.reads_total, 2u);
            GL_CHECK_EQ(app.view.age_s, 0u);
            GL_CHECK_EQ(app.ui.read_kind, GL_READ_QUICK);
        }
        GL_CHECK_EQ(gl_sim_violation_total(), 0);
    }
}

/* ======================================================================= */
/* 3. what happened while the result was still on the screen                */
/* ======================================================================= */

GL_TEST(test_turned_while_shown_or_spin_given_up_is_not_recalled)
{
    const act_t tap = { "tap", 0.06, 0.0, 0.0, 0.0, 0.0, true };
    uint32_t t0;

    /* ---- twisted by 10 degrees in 0.4 s while the result is shown: too
     *      quick and too flat for the read's own motion rule (the result
     *      stays), but the marker no longer faces where it read ---- */
    world_defaults_();
    board_up_(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 12000));
    W.turn_at_s = 0.001 * (double)now_ms_() + 5.0;
    W.turn_len_s = 0.4;
    W.turn_rad = 10.0 * PI_D / 180.0;
    run_until_ms_(now_ms_() + 8000u);
    GL_CHECK_EQ(app.ui.state, GL_UI_SHOW_RESULT); /* (it did not count as picking it up) */
    GL_CHECK(app.recall_spoiled);
    GL_CHECK(run_until_state_(GL_UI_SLEEP, now_ms_() + 47000u));
    run_until_ms_(now_ms_() + 20000u);
    t0 = now_ms_() + 400u;
    act_(&tap, 0.001 * (double)t0);
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, t0 + 14000u));
    GL_CHECK(!app.view.recalled);
    GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, 2u);
    printf("    twisted 10 degrees in 0.4 s while the result was shown, tapped after it slept: a new read\n");

    /* ---- the Precision spin begun and given up (20 s): the marker may lie
     *      anywhere; the single read is shown again, and not offered later ---- */
    world_defaults_();
    board_up_(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 12000));
    gl_app_post(&app, GL_EV_DOUBLE_TAP, 0);
    run_until_ms_(now_ms_() + 200u);
    GL_CHECK_EQ(app.ui.state, GL_UI_PRECISION_WAIT_SPIN);
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, now_ms_() + 21000u));
    GL_CHECK(app.recall_spoiled);
    GL_CHECK(run_until_state_(GL_UI_SLEEP, now_ms_() + 47000u));
    run_until_ms_(now_ms_() + 20000u);
    t0 = now_ms_() + 400u;
    act_(&tap, 0.001 * (double)t0);
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, t0 + 14000u));
    GL_CHECK(!app.view.recalled);
    GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, 2u);
    printf("    Precision spin begun and given up, tapped after it slept: a new read\n");

    /* ---- a Precision Read completed: ITS result is recalled, drawn turned
     *      round as it was ---- */
    world_defaults_();
    board_up_(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 12000));
    gl_app_post(&app, GL_EV_DOUBLE_TAP, 0);
    run_until_ms_(now_ms_() + 300u);
    W.turn_at_s = 0.001 * (double)now_ms_() + 0.5;
    W.turn_len_s = 1.2;
    W.turn_rad = 176.0 * PI_D / 180.0;
    GL_CHECK(run_until_state_(GL_UI_READ_TILT, now_ms_() + 5000u));
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, now_ms_() + 8000u));
    GL_CHECK(app.view.precision);
    {
        static uint8_t shown[GL_GFX_BYTES];
        gl_ui_view_t first;
        unsigned other_rows = 0;
        run_until_ms_(now_ms_() + 50u);
        first = app.view;
        memcpy(shown, gl_sim_lcd()->mem, sizeof(shown));
        GL_CHECK(run_until_state_(GL_UI_SLEEP, now_ms_() + 47000u));
        GL_CHECK(!app.recall_spoiled);
        run_until_ms_(now_ms_() + 20000u);
        t0 = now_ms_() + 400u;
        act_(&tap, 0.001 * (double)t0);
        GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, t0 + 5000u));
        run_until_ms_(now_ms_() + 50u);
        GL_CHECK(app.view.recalled && app.view.precision);
        GL_CHECK_NEAR(app.view.aim_rad, first.aim_rad, 0.0);
        GL_CHECK_NEAR(app.view.ball_az_rad, first.ball_az_rad, 0.0);
        GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, 1u);
        /* the screen is turned round (the marker faces away): the age is at
         * the top of the panel, everything else as it was */
        for (unsigned y = 0; y < 128u; y++) {
            if (memcmp(&gl_sim_lcd()->mem[y * 16u], &shown[y * 16u], 16) != 0 && y > 15u) {
                other_rows++;
            }
        }
        GL_CHECK_EQ(other_rows, 0u);
        printf("    Precision result recalled after a tap: aim %.2f mrad, drawn turned round as before\n",
               1000.0 * (double)app.view.aim_rad);
    }
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* ======================================================================= */
/* 4. nothing to recall                                                     */
/* ======================================================================= */

GL_TEST(test_no_recall_without_a_result_or_after_the_cradle)
{
    const act_t tap = { "tap", 0.06, 0.0, 0.0, 0.0, 0.0, true };
    uint32_t t0;

    /* a fresh marker that is tapped awake makes a read */
    world_defaults_();
    W.t_pick_s = 1000.0; /* never picked up */
    W.t_place_s = 1000.0;
    board_up_(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    run_until_ms_(2000u);
    GL_CHECK_EQ(app.ui.state, GL_UI_SLEEP);
    GL_CHECK(!app.ui.recall);
    t0 = now_ms_() + 400u;
    act_(&tap, 0.001 * (double)t0);
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, t0 + 14000u));
    GL_CHECK(!app.view.recalled);
    GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, 1u);

    /* a result, then the cradle, then out and tapped: a new read */
    read_and_sleep_();
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    GL_CHECK(run_until_state_(GL_UI_CRADLE_USB, now_ms_() + 20000u));
    GL_CHECK(!app.ui.recall);
    gl_sim_set_input(GL_PIN_VBUS_SENSE, false);
    GL_CHECK(run_until_state_(GL_UI_SLEEP, now_ms_() + 20000u));
    run_until_ms_(now_ms_() + 20000u);
    t0 = now_ms_() + 400u;
    act_(&tap, 0.001 * (double)t0);
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, t0 + 14000u));
    GL_CHECK(!app.view.recalled);
    GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, 2u);

    /* a reset in between: nothing is kept (the result lives in RAM) */
    read_and_sleep_();
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    GL_CHECK(!app.ui.recall && !app.view.have_result);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);

    /* a result older than 24 h is not offered again: 23 h 50 min after it a
     * tap recalls it ("23H AGO"), 25 h after it a tap makes a new read */
    for (int late = 0; late < 2; late++) {
        gl_ui_result_text_t t;
        read_and_sleep_();
        run_until_ms_(now_ms_() + (late ? 90000000u : 85700000u));
        GL_CHECK_EQ(app.ui.state, GL_UI_SLEEP);
        t0 = now_ms_() + 400u;
        act_(&tap, 0.001 * (double)t0);
        GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, t0 + 14000u));
        run_until_ms_(now_ms_() + 30u);
        GL_CHECK_EQ(app.view.recalled, late == 0);
        GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, late ? 2u : 1u);
        gl_ui_result_text(&app.ui, &app.view, &t);
        if (late == 0) {
            GL_CHECK(strcmp(t.age, "23H AGO") == 0);
        }
        printf("    tapped %s after the result: %s\n", late ? "25 h" : "23 h 50 min",
               app.view.recalled ? t.age : "a new read");
    }
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* ======================================================================= */
/* 5. the regulatory and information screen, through the application        */
/* ======================================================================= */

/* The gestures themselves are tested in test_gesture.c; here their events
 * are posted, as tests/test_e2e.c does for the zeroing. */
GL_TEST(test_info_screen_from_the_dial)
{
    static gl_gfx_t again, ref;
    gl_settings_t before;
    uint8_t uid[12];
    char serial[8];
    unsigned bad = 0, differ = 0;

    const act_t tap = { "tap", 0.06, 0.0, 0.0, 0.0, 0.0, true };

    /* the marker lies flat and is tapped awake; half a second into the
     * splash (its real posture, flat, has been reported by then and nothing
     * more will come from the IMU) the golfer's gestures are posted */
    world_defaults_();
    W.t_pick_s = 1.0e9;
    W.t_place_s = 1.0e9;
    board_up_(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    before = app.settings;
    act_(&tap, 0.4);
    GL_CHECK(run_until_state_(GL_UI_WAKE, 4000));
    run_until_ms_(now_ms_() + 550u);
    GL_CHECK_EQ(app.ui.state, GL_UI_WAKE);
    gl_app_post(&app, GL_EV_UPRIGHT, 0);
    run_until_ms_(now_ms_() + 50u);
    GL_CHECK_EQ(app.ui.state, GL_UI_SETTINGS_DIAL);
    for (unsigned i = 0; i < (unsigned)GL_UI_ITEM_INFO; i++) {
        gl_app_post(&app, GL_EV_DOUBLE_TAP, 0);
        run_until_ms_(now_ms_() + 20u);
    }
    GL_CHECK_EQ(app.ui.item, GL_UI_ITEM_INFO);
    GL_CHECK_EQ(app.ui.dial_value, 0);
    /* what the application put into the view */
    gl_hal_unique_id(uid);
    gl_cal_serial_text(gl_cal_serial_from_uid(uid), serial);
    GL_CHECK_EQ(app.view.info_hw, 'E');
    GL_CHECK_EQ(app.view.info_fw, GL_APP_FW_VERSION);
    GL_CHECK(strcmp(app.view.info_serial, serial) == 0);
    GL_CHECK_EQ(strlen(app.view.info_serial), 7u);
    GL_CHECK(app.view.info_text != NULL && strcmp(app.view.info_text, GL_REGULATORY_TEXT) == 0);
    GL_CHECK_EQ(app.ui.info_pages, gl_ui_info_pages(GL_REGULATORY_TEXT));
    GL_CHECK_EQ(app.ui.info_pages, 2);
    /* the panel shows it: model, PRACTICE DEVICE, versions, serial */
    GL_CHECK_EQ(panel_differs_from_framebuffer_(), 0u);
    gl_gfx_init(&again);
    gl_ui_render(&app.ui, &app.view, &again);
    for (unsigned i = 0; i < GL_GFX_BYTES; i++) {
        bad += (again.px[i] != gl_sim_lcd()->mem[i]) ? 1u : 0u;
    }
    GL_CHECK_EQ(bad, 0u);
    {
        char line[20];
        static const struct { int y, scale; const char *s; } fixed[] = {
            { 6, 1, "1/2" }, { 18, 1, "GREENLINE" }, { 30, 2, "GL-1" }, { 50, 1, "PRACTICE DEVICE" },
            { 62, 1, "HW E  FW 0.3" }, { 90, 1, "ROLL: MORE" },
        };
        gl_gfx_init(&ref);
        gl_gfx_set_clip(&ref, false);
        for (unsigned i = 0; i < GL_ARRAY_LEN(fixed); i++) {
            gl_gfx_text_centred(&ref, 64, fixed[i].y, fixed[i].s, fixed[i].scale, GL_INK_BLACK);
        }
        snprintf(line, sizeof(line), "SN %s", serial);
        gl_gfx_text_centred(&ref, 64, 74, line, 1, GL_INK_BLACK);
        for (int y = 0; y < 100; y++) {
            for (int x = 0; x < 128; x++) {
                differ += (gl_gfx_get(&ref, x, y) != !panel_black_(x, y)) ? 1u : 0u;
            }
        }
        GL_CHECK_EQ(differ, 0u);
        printf("    INFO screen: \"GREENLINE\", \"GL-1\", \"PRACTICE DEVICE\", \"HW E  FW 0.3\", \"%s\" "
               "- on the panel, pixel for pixel\n", line);
    }
    /* rolled on: the text block (here: the placeholder) */
    gl_app_post(&app, GL_EV_DIAL_STEP, 1);
    run_until_ms_(now_ms_() + 30u);
    GL_CHECK_EQ(app.ui.dial_value, 1);
    GL_CHECK_EQ(panel_differs_from_framebuffer_(), 0u);
    {
        int x = 0, y = 0;
        differ = 0;
        gl_gfx_init(&ref);
        gl_gfx_set_clip(&ref, false);
        (void)gl_ui_info_line_chars(0, &x, &y);
        (void)gl_gfx_text(&ref, x, y, "REGULATORY", 1, GL_INK_BLACK);
        (void)gl_ui_info_line_chars(1, &x, &y);
        (void)gl_gfx_text(&ref, x, y, "TEXT", 1, GL_INK_BLACK);
        for (int yy = 16; yy < 16 + 16; yy++) {
            for (int xx = 0; xx < 128; xx++) {
                differ += (gl_gfx_get(&ref, xx, yy) != !panel_black_(xx, yy)) ? 1u : 0u;
            }
        }
        GL_CHECK_EQ(differ, 0u);
    }
    /* laid flat: out of the dial; nothing was changed, nothing was stored anew */
    gl_app_post(&app, GL_EV_FLAT, 0);
    run_until_ms_(now_ms_() + 30u);
    GL_CHECK_EQ(app.ui.state, GL_UI_WAIT_STILL);
    GL_CHECK(memcmp(&before, &app.settings, sizeof(before)) == 0);
    /* with a serial stored at the factory, that one is shown */
    app.cal_dev.flags |= (uint8_t)GL_CAL_DEV_FLAG_SERIAL;
    app.cal_dev.serial = 0x01234567u;
    gl_app_post(&app, GL_EV_UPRIGHT, 0);
    run_until_ms_(now_ms_() + 50u);
    gl_cal_serial_text(0x01234567u, serial);
    GL_CHECK(strcmp(app.view.info_serial, serial) == 0);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

int main(void)
{
    GL_RUN(test_tap_recalls_the_result_without_a_read);
    GL_RUN(test_what_is_a_lift_and_what_is_not);
    GL_RUN(test_turned_while_shown_or_spin_given_up_is_not_recalled);
    GL_RUN(test_no_recall_without_a_result_or_after_the_cradle);
    GL_RUN(test_info_screen_from_the_dial);
    return gl_test_summary();
}
