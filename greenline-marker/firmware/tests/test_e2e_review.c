/*
 * test_e2e_review.c - regression tests of the phase-2 review findings that
 * concern the APPLICATION (the whole firmware on the host simulator).
 *
 * Every test here was written against the code as the review found it and
 * FAILED there; the README section "Phase-2 review: what was fixed" lists
 * the finding behind each test and the figures of the failing run.
 *
 *   product behaviour
 *     test_double_tap_after_precision_starts_a_survey     a second tap-tap on a "2X"
 *                                                         result must not re-arm the spin
 *     test_precision_result_is_upright_for_the_golfer     the result screen after the
 *                                                         half turn is drawn turned round
 *     test_distance_prompt_re_placing_reads_again         the prompt is not a dead end
 *     test_dialled_distance_belongs_to_one_hole           it expires; flag-out is tentative
 *     test_plays_like_is_the_flat_putt                    PLAYS = distance on a flat green
 *     test_spin_abandoned_then_completed                  the gyro angle counts from the read
 *     test_solved_aim_off_the_screen_keeps_its_style      no arrow against the aim
 *     test_grain_setting_reaches_the_solver               GRAIN ON is not a dead setting
 *     test_failed_switch_to_the_slow_clock_is_not_believed
 *     test_near_stick_is_one_candidate                    no group of strips for a shoulder
 *   charger supervision
 *     test_vbus_rising_edge_lost_while_asleep             level, not edge
 *     test_vbus_falling_edge_lost_in_the_cradle
 *     test_stalled_supervision_stops_the_charge           the staleness limit, end to end
 *     test_vbus_bounce_stress                             random edges, no rule violation
 */
#include "gl_e2e_world.h"

static uint32_t now_ms_(void)
{
    return (uint32_t)(gl_sim_now_us() / 1000u);
}

static double wrap_pi_(double a)
{
    while (a > PI_D) {
        a -= 2.0 * PI_D;
    }
    while (a <= -PI_D) {
        a += 2.0 * PI_D;
    }
    return a;
}

/* ---- the marker handled with any number of turns about the vertical -------- */

#define MAX_TURNS 8
static struct {
    double at, len, rad;
} turns_[MAX_TURNS];
static unsigned n_turns_;

static double heading2_(double t, double *rate)
{
    double h = 0.0;
    *rate = 0.0;
    for (unsigned i = 0; i < n_turns_; i++) {
        if (t <= turns_[i].at) {
            continue;
        }
        if (t >= turns_[i].at + turns_[i].len) {
            h += turns_[i].rad;
            continue;
        }
        {
            const double f = (t - turns_[i].at) / turns_[i].len;
            h += turns_[i].rad * 0.5 * (1.0 - cos(PI_D * f));
            *rate += turns_[i].rad * 0.5 * PI_D / turns_[i].len * sin(PI_D * f);
        }
    }
    return h;
}

static void imu2_fn_(void *ctx, uint64_t t_us, float a[3], float g[3])
{
    const double t = (double)t_us * 1e-6;
    double rate;
    const double psi = heading2_(t, &rate);
    const double cx = cos(psi) * W.slope_x + sin(psi) * W.slope_y;
    const double cy = -sin(psi) * W.slope_x + cos(psi) * W.slope_y;
    const gl_vec3_t u = up_of_(cx, cy);
    (void)ctx;
    a[0] = u.x;
    a[1] = u.y;
    a[2] = u.z;
    g[0] = (float)rate * u.x;
    g[1] = (float)rate * u.y;
    g[2] = (float)rate * u.z;
    if (t >= W.t_pick_s && t < W.t_place_s) {
        const double w = 2.0 * PI_D * 3.1 * (t - W.t_pick_s);
        a[0] += (float)(0.35 * sin(w));
        a[1] += (float)(0.25 * cos(1.7 * w));
        a[2] += (float)(0.20 * sin(2.3 * w));
        g[0] += (float)(1.5 * cos(w));
        g[1] += (float)(1.0 * sin(1.3 * w));
    }
}

static void double_tap_(void)
{
    gl_app_post(&app, GL_EV_DOUBLE_TAP, 0);
    run_until_ms_(now_ms_() + 150u);
}

/* a turn of `deg` about the vertical, starting half a second from now */
static void turn_(double deg)
{
    const double t = (double)gl_sim_now_us() * 1e-6;
    turns_[n_turns_].at = t + 0.5;
    turns_[n_turns_].len = 1.2;
    turns_[n_turns_].rad = deg * PI_D / 180.0;
    n_turns_++;
}

/* Boot with the world attached; settings changed where the argument is >= 0. */
static void boot_(int units, int past_cm, int manual_cm, int grain)
{
    gl_settings_t s;
    n_turns_ = 0;
    board_up_(true);
    gl_sim_imu_set_motion(imu2_fn_, NULL);
    (void)gl_app_init(&app);
    s = app.settings;
    if (units >= 0) {
        s.units = (uint8_t)units;
    }
    if (past_cm >= 0) {
        s.past_cm = (uint8_t)past_cm;
    }
    if (manual_cm >= 0) {
        s.manual_distance_cm = (uint16_t)manual_cm;
    }
    if (grain >= 0) {
        s.grain_enable = (uint8_t)grain;
    }
    GL_CHECK_EQ(gl_app_set_settings(&app, &s), GL_OK);
    watch_reset_();
}

/* The scene given in the PUTT frame: the hole `d` from the marker centre at
 * `bearing` (CCW from the visor axis), the green rising `cross_left` to the
 * left of the line and `along` towards the hole. */
static void scene_(double d, double bearing, double cross_left, double along)
{
    const double by = GL_CFG_BALL_CENTRE_Y_MM * 0.001;
    const double hx = -d * sin(bearing), hy = d * cos(bearing);
    const double bb = atan2(-hx, hy - by);
    const double ux = -sin(bb), uy = cos(bb);  /* to the hole (x right, y forward) */
    const double lx = -cos(bb), ly = -sin(bb); /* to its left */
    world_defaults_();
    W.dist_m = d;
    W.bearing_rad = bearing;
    W.slope_x = along * ux + cross_left * lx;
    W.slope_y = along * uy + cross_left * ly;
    project_scene_();
}

static void show_(const char *tag)
{
    gl_ui_result_text_t t;
    gl_ui_result_text(&app.ui, &app.view, &t);
    printf("    %-40s %-18s [%s | %s | %s | %s | %s | %d/5 %s] phi %+.2f mrad, aim %+.2f mrad, "
           "slope used (%+.4f, %+.4f)\n",
           tag, gl_ui_state_name((gl_ui_state_t)app.ui.state), t.distance,
           (t.plays[0] != '\0') ? t.plays : "-", (t.note[0] != '\0') ? t.note : "-", t.slope, t.brk,
           gl_ui_conf_boxes(app.view.confidence), t.mode, 1000.0 * (double)app.est.phi_rad,
           1000.0 * (double)app.view.aim_rad, (double)app.cur.slope.x, (double)app.cur.slope.y);
}

/* Fraction of the pixels that only a SOLID aim line inks (the gaps of the
 * tentative dashes) that are black on the panel: near 1 solid, near 0 dashed. */
static double ink_in_the_dash_gaps_(float aim_rad, float ball_az_rad)
{
    static gl_gfx_t solid, dashed;
    gl_gfx_aim_info_t info;
    unsigned n = 0, black = 0;

    gl_gfx_init(&solid);
    gl_gfx_set_clip(&solid, true);
    gl_gfx_clear(&solid, GL_INK_WHITE);
    gl_gfx_aim_line_styled(&solid, aim_rad, ball_az_rad, 3.0f, false, &info);
    gl_gfx_init(&dashed);
    gl_gfx_set_clip(&dashed, true);
    gl_gfx_clear(&dashed, GL_INK_WHITE);
    gl_gfx_aim_line_styled(&dashed, aim_rad, ball_az_rad, 3.0f, true, &info);
    for (int y = 0; y < 128; y++) {
        for (int x = 0; x < 128; x++) {
            if (!gl_gfx_get(&solid, x, y) && gl_gfx_get(&dashed, x, y)) {
                n++;
                black += panel_black_(x, y) ? 1u : 0u;
            }
        }
    }
    return (n >= 100u) ? (double)black / (double)n : (double)NAN;
}

/* ======================================================================= */
/* product behaviour                                                        */
/* ======================================================================= */

/* Review finding (critical): a second double tap on a Precision result re-armed
 * the spin with the FIRST read's slope and a gyro integration that started
 * from the already turned marker; the half turn back was then combined as if
 * the two reads were 180 degrees apart: slope 0.0 %, "STRAIGHT", "2X", a
 * solid line straight at the hole.  Now the Precision Read is offered once
 * per placement: the second double tap goes on to the Survey (the prompt of
 * the first one says so), and a marker turned back and re-placed is a new
 * drop, read by the cameras. */
GL_TEST(test_double_tap_after_precision_starts_a_survey)
{
    double phi_quick, aim_quick, t0;
    gl_ui_result_text_t t;

    scene_(6.0, 0.03, 0.020, 0.0); /* 6 m, the green rises LEFT 2 % */
    boot_(GL_UNITS_METRES, -1, -1, -1);
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 14000));
    run_until_ms_(now_ms_() + 100u);
    show_("Quick Read");
    phi_quick = (double)app.est.phi_rad;
    aim_quick = (double)app.view.aim_rad;
    GL_CHECK(phi_quick > 0.080 && phi_quick < 0.140); /* aims LEFT, about 109 mrad */
    GL_CHECK_NEAR(app.est.slope_pct, 2.0, 0.3);

    double_tap_();
    GL_CHECK_EQ(app.ui.state, GL_UI_PRECISION_WAIT_SPIN);
    turn_(180.0);
    t0 = (double)gl_sim_now_us() * 1e-6;
    GL_CHECK(run_until_state_(GL_UI_READ_TILT, (uint32_t)(t0 * 1000.0) + 6000u));
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, (uint32_t)(t0 * 1000.0) + 10000u));
    run_until_ms_(now_ms_() + 100u);
    show_("Precision Read (spun 180 degrees)");
    gl_ui_result_text(&app.ui, &app.view, &t);
    GL_CHECK(app.cur.precision);
    GL_CHECK(strcmp(t.mode, "2X") == 0);
    GL_CHECK_NEAR(app.est.phi_rad, phi_quick, 0.004);
    GL_CHECK_NEAR(app.est.slope_pct, 2.0, 0.3);

    /* the golfer taps twice again ... */
    double_tap_();
    printf("    second tap-tap on the \"2X\" result: state %s, drops stored %u\n",
           gl_ui_state_name((gl_ui_state_t)app.ui.state), (unsigned)app.survey.count);
    GL_CHECK_EQ(app.ui.state, GL_UI_SURVEY_NEXT_DROP);
    GL_CHECK_EQ(app.survey.count, 1);
    /* ... and turns the marker back to face the hole (picked up and put down) */
    t0 = (double)gl_sim_now_us() * 1e-6;
    W.t_pick_s = t0 + 0.4;
    W.t_place_s = t0 + 1.9;
    turn_(180.0);
    run_until_ms_((uint32_t)(t0 * 1000.0) + 2000u);
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, (uint32_t)(t0 * 1000.0) + 16000u));
    run_until_ms_(now_ms_() + 100u);
    show_("after the 2nd tap-tap and the turn back");
    gl_ui_result_text(&app.ui, &app.view, &t);
    /* whatever the result is called, it must be the putt of the scene: a
     * 2 % slope and the aim of the first read, NOT "0.0 %, STRAIGHT" */
    GL_CHECK_NEAR(app.est.slope_pct, 2.0, 0.3);
    GL_CHECK_NEAR(app.est.phi_rad, phi_quick, 0.006);
    GL_CHECK_NEAR(wrap_pi_((double)app.view.aim_rad - aim_quick), 0.0, 0.008);
    GL_CHECK(strcmp(t.brk, "STRAIGHT") != 0);
    GL_CHECK(strcmp(t.mode, "2X") != 0);
    GL_CHECK(fabs((double)app.view.ball_az_rad) < 0.2); /* the marker faces the hole again */
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* Review finding (major): after the half turn of a Precision Read the marker
 * faces AWAY from the hole, and the result screen was drawn upright in the
 * marker's frame: upside down for the golfer behind the ball, with the '<'
 * of the break label on his right.  Now a result whose ball position lies
 * behind the marker is drawn turned round: exactly the picture the screen
 * would show for the same angles referred to the opposite direction, rotated
 * by 180 degrees. */
GL_TEST(test_precision_result_is_upright_for_the_golfer)
{
    static gl_gfx_t ref;
    gl_ui_view_t v;
    gl_ui_result_text_t t;
    unsigned differ = 0, black = 0;
    double t0;

    scene_(6.0, 0.03, 0.020, 0.0);
    boot_(GL_UNITS_METRES, -1, -1, -1);
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 14000));
    double_tap_();
    turn_(180.0);
    t0 = (double)gl_sim_now_us() * 1e-6;
    GL_CHECK(run_until_state_(GL_UI_READ_TILT, (uint32_t)(t0 * 1000.0) + 6000u));
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, (uint32_t)(t0 * 1000.0) + 10000u));
    run_until_ms_(now_ms_() + 100u);
    GL_CHECK(app.cur.precision);
    GL_CHECK(fabs(fabs((double)app.view.ball_az_rad) - PI_D) < 0.2); /* the ball lies behind */
    gl_ui_result_text(&app.ui, &app.view, &t);
    GL_CHECK(t.brk[0] == '<'); /* aim LEFT of the hole, as the golfer sees it */

    /* what a marker facing the hole would show for this putt ... */
    v = app.view;
    v.aim_rad = (float)wrap_pi_((double)v.aim_rad - PI_D);
    v.fall_line_rad = (float)wrap_pi_((double)v.fall_line_rad - PI_D);
    v.ball_az_rad = (float)wrap_pi_((double)v.ball_az_rad - PI_D);
    gl_gfx_init(&ref);
    gl_ui_render(&app.ui, &v, &ref);
    /* ... is what the golfer must see when he looks at the turned marker */
    for (int y = 0; y < 128; y++) {
        for (int x = 0; x < 128; x++) {
            const bool want_black = !gl_gfx_get(&ref, 127 - x, 127 - y);
            black += want_black ? 1u : 0u;
            differ += (panel_black_(x, y) != want_black) ? 1u : 0u;
        }
    }
    printf("    Precision result on a marker turned by %.1f degrees: %u of 16384 panel pixels differ "
           "from the upright picture turned round (%u black pixels in it)\n",
           (double)app.cur.view_yaw_rad * 180.0 / PI_D, differ, black);
    GL_CHECK(black > 600u);
    GL_CHECK_EQ(differ, 0);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* Review finding (major): the distance prompt after "no flagstick seen" was
 * left only by standing the marker upright, or after 30 s into sleep; a
 * golfer who simply put the marker down again (the flagstick now in view)
 * got nothing.  Now picking the marker up and putting it down is a new read. */
GL_TEST(test_distance_prompt_re_placing_reads_again)
{
    scene_(6.0, 0.05, 0.015, 0.0);
    W.stick = false; /* (a ball in front of the visor, a hand, a miss of the vision) */
    boot_(GL_UNITS_METRES, -1, 0, -1);
    run_until_ms_(7000);
    printf("    no flagstick seen, nothing dialled: at 7.0 s the UI is in %s (distance prompt %d)\n",
           gl_ui_state_name((gl_ui_state_t)app.ui.state), (int)app.ui.dist_prompt);
    GL_CHECK_EQ(app.ui.state, GL_UI_SETTINGS_DIAL);
    GL_CHECK(app.ui.dist_prompt);
    W.stick = true; /* the view is clear now */
    W.t_pick_s = 8.0;
    W.t_place_s = 9.5;
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 20000));
    run_until_ms_(now_ms_() + 100u);
    printf("    picked up at 8.0 s, down again at 9.5 s: at %.1f s the UI is in %s, camera rail "
           "cycles %u\n", (double)now_ms_() / 1000.0, gl_ui_state_name((gl_ui_state_t)app.ui.state),
           (unsigned)gl_sim_stats()->cam_rail_cycles);
    show_("the second read");
    GL_CHECK_EQ(app.ui.state, GL_UI_SHOW_RESULT);
    GL_CHECK(!app.est.flag_missing);
    GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, 2);
    GL_CHECK_EQ(app.settings.manual_distance_cm, 0); /* nothing was dialled, nothing is kept */
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* Review finding (major): a dialled distance stayed in the settings for
 * ever, so that at the next hole any read that missed the flagstick silently
 * became a flag-out result, drawn as a solid line along the visor axis with
 * the confidence of a camera read.  Now
 *   - the flag-out line is TENTATIVE (dashed) and the confidence bar is
 *     empty: the direction is the golfer's pointing, not a measurement;
 *   - the dialled distance belongs to one hole: it is forgotten when the
 *     marker goes to sleep and when a read ranges a flagstick. */
GL_TEST(test_dialled_distance_belongs_to_one_hole)
{
    gl_ui_result_text_t t;
    double ink;

    /* 1. a deliberate flag-out read: 4.5 m dialled, the green rises LEFT 1.5 % */
    scene_(4.5, 0.0, 0.015, 0.0);
    W.stick = false;
    boot_(GL_UNITS_METRES, -1, 450, -1);
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 14000));
    run_until_ms_(now_ms_() + 100u);
    show_("flag out, 4.5 m dialled");
    gl_ui_result_text(&app.ui, &app.view, &t);
    GL_CHECK(app.est.flag_missing);
    GL_CHECK(strcmp(t.distance, "4.5M?") == 0);
    GL_CHECK(strcmp(t.note, "NO FLAG") == 0);
    ink = ink_in_the_dash_gaps_(app.view.aim_rad, app.view.ball_az_rad);
    printf("    the flag-out line: %.2f of the dash-gap pixels are inked (solid > 0.45, dashed < 0.15); "
           "confidence %.3f -> %d of 5 boxes\n", ink, (double)app.view.confidence,
           gl_ui_conf_boxes(app.view.confidence));
    GL_CHECK(ink < 0.15);
    GL_CHECK_EQ(gl_ui_conf_boxes(app.view.confidence), 0);
    GL_CHECK(app.view.confidence > 0.0f); /* (0 is "no solution at all") */
    GL_CHECK(t.brk[0] == '<');            /* the break relative to the visor axis is still quoted */

    /* 2. the result times out, the marker sleeps: the distance is forgotten */
    GL_CHECK(run_until_state_(GL_UI_SLEEP, now_ms_() + 50000u));
    printf("    asleep at %.1f s: DIST setting %u cm (stored copy %u cm)\n", (double)now_ms_() / 1000.0,
           (unsigned)app.settings.manual_distance_cm, (unsigned)app.ui.edit.manual_distance_cm);
    GL_CHECK_EQ(app.settings.manual_distance_cm, 0);
    GL_CHECK_EQ(app.ui.edit.manual_distance_cm, 0);

    /* 3. the next hole: the flagstick is not seen -> the prompt, not a line */
    {
        const double t0 = (double)gl_sim_now_us() * 1e-6;
        scene_(6.0, 0.05, 0.015, 0.0);
        W.stick = false;
        W.t_pick_s = t0 + 1.0;
        W.t_place_s = t0 + 1.6;
        run_until_ms_((uint32_t)(t0 * 1000.0) + 8000u);
        printf("    next placement, flagstick not seen: the UI is in %s (distance prompt %d)\n",
               gl_ui_state_name((gl_ui_state_t)app.ui.state), (int)app.ui.dist_prompt);
        GL_CHECK_EQ(app.ui.state, GL_UI_SETTINGS_DIAL);
        GL_CHECK(app.ui.dist_prompt);
    }
    GL_CHECK_EQ(gl_sim_violation_total(), 0);

    /* 4. a read that ranges the flagstick has no use for an old dialled distance */
    scene_(6.0, 0.05, 0.015, 0.0);
    boot_(GL_UNITS_METRES, -1, 450, -1);
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 14000));
    run_until_ms_(now_ms_() + 100u);
    show_("flag in, 4.5 m left in DIST");
    GL_CHECK(!app.est.flag_missing && !app.est.range_missing);
    GL_CHECK_NEAR(app.est.distance_m, 6.0, 0.2);
    GL_CHECK_EQ(app.settings.manual_distance_cm, 0);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* Review finding (minor): "PLAYS" was the roll-out distance v0^2 / (2 a_r),
 * which contains the PAST setting: a dead-flat 6 m putt "played" 6.3 m.  Now
 * it is the flat putt that needs the same stroke: PAST is taken off. */
GL_TEST(test_plays_like_is_the_flat_putt)
{
    static const int past_cm[3] = { 30, 90, 0 };
    for (int k = 0; k < 3; k++) {
        gl_ui_result_text_t t;
        scene_(6.0, 0.0, 0.0, 0.0);
        boot_(GL_UNITS_METRES, past_cm[k], -1, -1);
        GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 14000));
        run_until_ms_(now_ms_() + 100u);
        gl_ui_result_text(&app.ui, &app.view, &t);
        printf("    6 m, dead flat, PAST %2d cm: shown [%s | %s], estimator roll-out %.3f m\n", past_cm[k],
               t.distance, t.plays, (double)app.est.plays_like_m);
        GL_CHECK_NEAR(app.view.plays_like_m, app.view.distance_m, 0.03);
        GL_CHECK_NEAR(app.est.plays_like_m, app.est.distance_m + 0.01f * (float)past_cm[k], 0.03);
    }
    /* and a slope still shows: 5 m, 2 % uphill plays about 6.2 m (6.52 m of roll-out less 0.30) */
    {
        gl_ui_result_text_t t;
        scene_(5.0, 0.0, 0.0, 0.020);
        boot_(GL_UNITS_METRES, 30, -1, -1);
        GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 14000));
        run_until_ms_(now_ms_() + 100u);
        gl_ui_result_text(&app.ui, &app.view, &t);
        printf("    5 m, 2 %% uphill, PAST 30 cm: shown [%s | %s]\n", t.distance, t.plays);
        GL_CHECK_NEAR(app.view.plays_like_m, 6.52 - 0.30, 0.12);
    }
}


/* Review finding (critical, second half): an ABANDONED spin had the same
 * frame error.  The marker is turned a quarter turn, the prompt times out,
 * the single read is shown again for where the marker faces now; the golfer
 * taps twice again and completes the half turn.  The gyro angle must count
 * from the frame of the camera read all the way: the combination is then a
 * true Precision Read.  (The integration used to restart from zero at the
 * second double tap, so the quarter turn that completes the half turn was
 * never recognised, and a further half turn - 270 degrees from the read -
 * was combined as if it were 180.) */
GL_TEST(test_spin_abandoned_then_completed)
{
    double phi_quick, t0;
    gl_ui_result_text_t t;

    scene_(6.0, 0.03, 0.020, 0.0);
    boot_(GL_UNITS_METRES, -1, -1, -1);
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 14000));
    run_until_ms_(now_ms_() + 100u);
    phi_quick = (double)app.est.phi_rad;
    double_tap_();
    GL_CHECK_EQ(app.ui.state, GL_UI_PRECISION_WAIT_SPIN);
    turn_(90.0); /* only a quarter turn: no half turn is reported */
    t0 = (double)gl_sim_now_us() * 1e-6;
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, (uint32_t)(t0 * 1000.0) + 22000u)); /* time-out */
    run_until_ms_(now_ms_() + 100u);
    show_("spin abandoned at a quarter turn");
    GL_CHECK(!app.cur.precision);
    GL_CHECK_NEAR(app.cur.view_yaw_rad, 0.5 * PI_D, 0.05);
    GL_CHECK_NEAR(app.est.slope_pct, 2.0, 0.3);

    double_tap_(); /* asks for the spin again ... */
    GL_CHECK_EQ(app.ui.state, GL_UI_PRECISION_WAIT_SPIN);
    turn_(90.0);   /* ... and completes the half turn */
    t0 = (double)gl_sim_now_us() * 1e-6;
    GL_CHECK(run_until_state_(GL_UI_READ_TILT, (uint32_t)(t0 * 1000.0) + 6000u));
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, (uint32_t)(t0 * 1000.0) + 10000u));
    run_until_ms_(now_ms_() + 100u);
    show_("the half turn completed");
    gl_ui_result_text(&app.ui, &app.view, &t);
    GL_CHECK(app.cur.precision);
    GL_CHECK(strcmp(t.mode, "2X") == 0);
    GL_CHECK_NEAR(fabs((double)app.cur.view_yaw_rad), PI_D, 0.05);
    GL_CHECK_NEAR(app.est.slope_pct, 2.0, 0.3);
    GL_CHECK_NEAR(app.est.phi_rad, phi_quick, 0.004);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* Review finding (minor): a SOLVED aim more than about 13.5 degrees off the
 * marker's axis leaves the aperture.  Its substitute was drawn in short
 * dashes (like "not a solution") with a large arrow on the side the true
 * line lies on: for an aim to the LEFT the arrow pointed RIGHT.  Now the
 * parallel through the screen centre keeps the style of the result (solid
 * here) and there is no arrow. */
GL_TEST(test_solved_aim_off_the_screen_keeps_its_style)
{
    static gl_gfx_t ref;
    gl_ui_result_text_t t;
    unsigned n = 0, black = 0, arrow_zone = 0;

    scene_(3.0, 9.0 * PI_D / 180.0, 0.020, 0.0); /* the hole 9 degrees left of the visor axis */
    boot_(GL_UNITS_METRES, -1, -1, -1);
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 14000));
    run_until_ms_(now_ms_() + 100u);
    show_("3 m, rises LEFT 2 %, visor 9 deg right of the hole");
    gl_ui_result_text(&app.ui, &app.view, &t);
    GL_CHECK(app.view.solved && app.view.line_here);
    GL_CHECK(app.view.aim_rad > 0.2365f); /* more than 13.55 degrees to the LEFT: off the screen */
    GL_CHECK(t.brk[0] == '<');
    /* the line: solid, through the screen centre, parallel to the aim */
    gl_gfx_init(&ref);
    gl_gfx_set_clip(&ref, true);
    gl_gfx_clear(&ref, GL_INK_WHITE);
    (void)gl_gfx_line_angle(&ref, GL_GFX_CENTRE_F, GL_GFX_CENTRE_F, app.view.aim_rad, 2.0f, NULL,
                            GL_INK_BLACK);
    for (int y = 0; y < 128; y++) {
        for (int x = 0; x < 128; x++) {
            if (!gl_gfx_get(&ref, x, y)) {
                n++;
                black += panel_black_(x, y) ? 1u : 0u;
            }
            /* where the arrow for "the true line lies to the right" used to be */
            if (x >= 86 && x <= 118 && y >= 54 && y <= 74 && panel_black_(x, y)) {
                arrow_zone++;
            }
        }
    }
    printf("    aim %+.1f mrad (%.1f degrees LEFT): %.2f of the core of a solid parallel through the "
           "screen centre is inked (labels cover the rest); black pixels where the arrow to the RIGHT "
           "used to be: %u\n", 1000.0 * (double)app.view.aim_rad,
           (double)app.view.aim_rad * 180.0 / PI_D, (n > 0u) ? (double)black / (double)n : 0.0,
           arrow_zone);
    GL_CHECK(n > 300u);
    GL_CHECK((double)black / (double)n > 0.70); /* the 6 / 4 dashes inked 0.6 of it at most */
    GL_CHECK_EQ(arrow_zone, 0);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* Review finding (minor): GRAIN and GRASS were dead settings: GRAIN ON made
 * the read 0.14 s longer (the LED measurement) and the solver ignored the
 * estimate.  Now GRAIN OFF (the default: the sensor ships disabled) hands
 * over nothing and measures nothing, and GRAIN ON reaches the solve: the
 * grass type's strength along the fall line (no optical calibration here). */
static unsigned grain_adc_reads_(void)
{
    unsigned n = 0;
    for (size_t i = 0; i < gl_sim_trace_count(); i++) {
        const gl_sim_trace_t *tr = gl_sim_trace_at(i);
        if (tr->type == (uint8_t)GL_SIM_TR_ADC_READ && tr->a == (uint8_t)GL_ADC_CH_GRAIN_TIA) {
            n++;
        }
    }
    return n;
}

GL_TEST(test_grain_setting_reaches_the_solver)
{
    double phi[3], kappa[3];
    unsigned reads[3];
    static const char *const name[3] = { "GRAIN OFF (default)", "GRAIN ON, bentgrass",
                                         "GRAIN ON, bermuda" };
    for (int k = 0; k < 3; k++) {
        gl_settings_t s;
        scene_(6.0, 0.03, 0.020, 0.0);
        boot_(GL_UNITS_METRES, -1, -1, (k == 0) ? 0 : 1);
        s = app.settings;
        s.grass = (uint8_t)((k == 2) ? GL_GRASS_BERMUDA : GL_GRASS_BENT);
        GL_CHECK_EQ(gl_app_set_settings(&app, &s), GL_OK);
        GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 14000));
        run_until_ms_(now_ms_() + 100u);
        phi[k] = (double)app.est.phi_rad;
        kappa[k] = hypot((double)app.est.grain_x, (double)app.est.grain_y);
        reads[k] = grain_adc_reads_();
        printf("    %-22s solver use_grain %d, grain used |kappa| %.4f, phi %+8.3f mrad, grain ADC "
               "conversions %u\n", name[k], (int)app.solve_opt.use_grain, kappa[k], 1000.0 * phi[k],
               reads[k]);
    }
    GL_CHECK_NEAR(kappa[0], 0.0, 1e-9);
    GL_CHECK_EQ(reads[0], 0); /* OFF: no LED measurement at all */
    GL_CHECK(reads[1] > 0u && reads[2] > 0u);
    GL_CHECK(kappa[1] > 0.005 && kappa[2] > kappa[1] + 0.02);
    /* the grain runs down the fall line: it adds to the break */
    GL_CHECK(phi[1] > phi[0] && phi[2] > phi[1] + 0.002);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* Review finding (backend, by inspection): a switch back to the slow clock
 * that fails was ignored - the backend said SLOW, switched the PLL off under
 * the running core and lowered the voltage.  The backend now reports it,
 * and the application must not believe the clock is slow: no Stop mode with
 * the fast clock, and it tries again.  Here the first three switches back
 * fail (simulator hook); the read itself is not affected. */
GL_TEST(test_failed_switch_to_the_slow_clock_is_not_believed)
{
    scene_(6.0, 0.03, 0.020, 0.0);
    boot_(GL_UNITS_METRES, -1, -1, -1);
    gl_sim_clock_fail_slow(3);
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 14000));
    run_until_ms_(now_ms_() + 2000u);
    printf("    three switches back to the slow clock fail during a Quick Read: clock_fails %u, core "
           "clock now %s, simulator 'clock' violations (Stop mode with the fast clock) %u, switches "
           "up / down %u / %u\n", (unsigned)app.clock_fails,
           (gl_sim_clock() == GL_CLOCK_SLOW) ? "SLOW" : "FAST", gl_sim_violations()->clock,
           (unsigned)gl_sim_stats()->clock_to_fast, (unsigned)gl_sim_stats()->clock_to_slow);
    GL_CHECK_EQ(app.clock_fails, 3);
    GL_CHECK_EQ(gl_sim_clock(), GL_CLOCK_SLOW);
    GL_CHECK(!app.clock_fast);
    GL_CHECK_EQ(gl_sim_stats()->clock_to_fast, gl_sim_stats()->clock_to_slow);
    GL_CHECK_NEAR(app.est.slope_pct, 2.0, 0.3);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* Review finding (major): a third of the Quick Reads between 2.25 and 4.5 m
 * kept the camera rail on 3.0 to 3.1 s and showed the result 4.9 to 5.1 s
 * after the marker came to rest, against 2.4 s / 4.4 s for the others: the
 * band listed the stick twice (a weak, 13 px wide "line" 9 px beside the
 * real one), and each entry got an L R R L group of its own before the read
 * proper.  The shoulder is dropped now (app/gl_read.c).  Every read of this
 * sweep must take the 33 captures of a read with one candidate. */
GL_TEST(test_near_stick_is_one_candidate)
{
    static const double bearings[3] = { -0.20, 0.0, 0.17 };
    unsigned n = 0, shoulders = 0;
    double rail_max = 0.0, rail_min = 1e9, result_max = 0.0;

    for (double d = 2.25; d < 3.76; d += 0.25) {
        for (int b = 0; b < 3; b++) {
            world_defaults_();
            W.dist_m = d;
            W.bearing_rad = bearings[b];
            W.slope_x = 0.010;
            W.slope_y = -0.005;
            project_scene_();
            board_up_(true);
            (void)gl_app_init(&app);
            watch_reset_();
            GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 14000));
            {
                const double rail = (double)gl_sim_stats()->cam_rail_on_us / 1e6;
                const double result = (double)app.ui.state_since_ms / 1000.0 - W.t_place_s;
                n++;
                shoulders += app.read.result.n_shoulders;
                rail_max = (rail > rail_max) ? rail : rail_max;
                rail_min = (rail < rail_min) ? rail : rail_min;
                result_max = (result > result_max) ? result : result_max;
                GL_CHECK_EQ(app.read.result.n_candidates, 1);
                GL_CHECK_EQ(app.read.result.n_probed, 0);
                GL_CHECK_EQ(gl_sim_stats()->frames_captured, 33); /* the band and 8 x L R R L */
                GL_CHECK(app.cur.flag_found && !app.est.range_missing);
                GL_CHECK_NEAR(app.est.distance_m, d, 0.03 * d);
                GL_CHECK(!app.cur.ambiguous);
                GL_CHECK_EQ(gl_sim_violation_total(), 0);
            }
        }
    }
    printf("    %u Quick Reads of a flagstick 2.25 to 3.75 m away (2.6 to 4.4 px wide): %u band shoulders dropped; "
           "every read took 33 captures; camera rail on %.2f to %.2f s, result at most %.2f s after the marker "
           "came to rest (the review measured 3.02 to 3.12 s and 4.94 to 5.07 s on the reads with a shoulder)\n",
           n, shoulders, rail_min, rail_max, result_max);
    GL_CHECK(shoulders >= 10u); /* the sweep does contain the case */
    GL_CHECK(rail_max < 2.60);
    GL_CHECK(result_max < 4.60);
}

/* ======================================================================= */
/* charger supervision                                                      */
/* ======================================================================= */

static void vbus_up_and_lose_edge_(void *arg)
{
    (void)arg;
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    gl_sim_irq_drop(GL_IRQ_VBUS_CHANGE);
}

static void vbus_down_and_lose_edge_(void *arg)
{
    (void)arg;
    gl_sim_set_input(GL_PIN_VBUS_SENSE, false);
    gl_sim_irq_drop(GL_IRQ_VBUS_CHANGE);
}

/* Review finding (major): the firmware learned about VBUS only from the edge
 * interrupt.  Asleep, put into a cradle at 50 C with that one latch lost:
 * the charger ran unsupervised for good (600 s of 600 s).  Now the LEVEL is
 * acted on at every loop pass, so the 16 s housekeeping wake-up finds it.
 * The edge is placed at four phases of the housekeeping period. */
GL_TEST(test_vbus_rising_edge_lost_while_asleep)
{
    static const uint32_t phase_ms[4] = { 500u, 4500u, 8500u, 12500u };
    double worst_s = 0.0;

    for (int k = 0; k < 4; k++) {
        uint64_t out0;
        uint32_t t_edge;
        double ran_s;

        world_defaults_();
        W.t_pick_s = 1.0e9; /* never handled */
        W.t_place_s = 1.0e9;
        board_up_(true);
        (void)gl_app_init(&app);
        watch_reset_();
        run_until_ms_(60000u);
        GL_CHECK_EQ(app.ui.state, GL_UI_SLEEP);
        GL_CHECK_EQ(gl_sim_violation_total(), 0);
        gl_sim_imu_set_temperature(50.0f);
        out0 = gl_sim_stats()->chg_outside_us;
        t_edge = now_ms_() + phase_ms[k];
        GL_CHECK(gl_sim_at_ms(t_edge, vbus_up_and_lose_edge_, NULL));
        run_until_ms_(t_edge + 600000u); /* ten minutes in the cradle */
        ran_s = (double)(gl_sim_stats()->chg_outside_us - out0) / 1e6;
        worst_s = (ran_s > worst_s) ? ran_s : worst_s;
        printf("    asleep, into a cradle at 50 C %5.1f s after a housekeeping wake-up, the VBUS edge "
               "latch lost: charger ran %6.2f s of 600 s outside 0..45 C; then UI %s, awake %d, "
               "CHG_INHIBIT %s, charger %s\n",
               (double)phase_ms[k] / 1000.0, ran_s, gl_ui_state_name((gl_ui_state_t)app.ui.state),
               (int)app.awake, gl_sim_pin_drives_low(GL_PIN_CHG_INHIBIT) ? "LOW" : "released",
               gl_sim_charger_on() ? "RUNNING" : "stopped");
        GL_CHECK(!gl_sim_charger_on());
        GL_CHECK(gl_sim_pin_drives_low(GL_PIN_CHG_INHIBIT));
        GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_USB);
        GL_CHECK(app.awake && app.power.vbus);
        /* found by the next housekeeping wake-up at the latest */
        GL_CHECK(ran_s <= 0.001 * (double)GL_APP_SLEEP_HOUSEKEEP_MS + 0.1);
        /* nothing else is wrong; the simulator's own "10 s" reaction rule can
         * fire once in this FAULT case (the wake-up period is 16 s) */
        GL_CHECK_EQ(gl_sim_violation_total(), gl_sim_violations()->power);
        GL_CHECK(gl_sim_violations()->power <= 1u);
    }
    printf("    worst of the four: %.2f s (bound: the %u s housekeeping period)\n", worst_s,
           (unsigned)(GL_APP_SLEEP_HOUSEKEEP_MS / 1000u));
}

/* The other way round: lifted out of the cradle with the falling edge lost.
 * The marker stayed awake in CRADLE_USB with USB started until the cell was
 * flat (1.58 mAh in the first hour of the simulator's supply model). */
GL_TEST(test_vbus_falling_edge_lost_in_the_cradle)
{
    uint32_t t0;
    uint64_t stop0, idle0;
    double q0;

    world_defaults_();
    W.t_pick_s = 1.0e9;
    W.t_place_s = 1.0e9;
    board_up_(true);
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    (void)gl_app_init(&app);
    watch_reset_();
    run_until_ms_(20000u);
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_USB);
    GL_CHECK(gl_sim_charger_on());
    t0 = now_ms_();
    GL_CHECK(gl_sim_at_ms(t0 + 2000u, vbus_down_and_lose_edge_, NULL));
    run_until_ms_(t0 + 2000u + 1000u);
    printf("    lifted out of the cradle, the VBUS edge latch lost: one second later the UI is in %s, "
           "awake %d, usb_on %d, power.vbus %d\n", gl_ui_state_name((gl_ui_state_t)app.ui.state),
           (int)app.awake, (int)app.usb_on, (int)app.power.vbus);
    GL_CHECK_EQ(app.ui.state, GL_UI_SLEEP);
    GL_CHECK(!app.awake && !app.usb_on && !app.power.vbus);
    GL_CHECK(!gl_sim_pin_drives_low(GL_PIN_CHG_INHIBIT));
    stop0 = gl_sim_stats()->stop_us;
    idle0 = gl_sim_stats()->idle_us;
    q0 = gl_sim_stats()->charge_uas;
    run_until_ms_(t0 + 3000u + 3600u * 1000u); /* one hour on the shelf */
    printf("    the hour after: Stop mode %.1f s, idle sleep %.1f s, %.4f mAh from the cell (supply "
           "model, all currents provisional)\n", (double)(gl_sim_stats()->stop_us - stop0) / 1e6,
           (double)(gl_sim_stats()->idle_us - idle0) / 1e6, (gl_sim_stats()->charge_uas - q0) / 3.6e6);
    GL_CHECK((double)(gl_sim_stats()->stop_us - stop0) > 3590.0e6);
    GL_CHECK((gl_sim_stats()->charge_uas - q0) / 3.6e6 < 0.05);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* Review finding (test audit): the 12 s staleness limit of the cell
 * temperature was never evaluated when the supervision itself stopped (the
 * gate was only called right after a measurement).  Here the supervision is
 * made to stall while the main loop keeps running (its deadlines pushed far
 * away: what a lost timer, or a code path that never comes back to it, looks
 * like): the charge must be stopped when the last reading is too old. */
GL_TEST(test_stalled_supervision_stops_the_charge)
{
    uint32_t t0, t_stop = 0;

    world_defaults_();
    W.t_pick_s = 1.0e9;
    W.t_place_s = 1.0e9;
    board_up_(true);
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    (void)gl_app_init(&app);
    watch_reset_();
    run_until_ms_(20000u);
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_USB);
    GL_CHECK(gl_sim_charger_on());
    t0 = now_ms_();
    while (now_ms_() < t0 + 30000u) {
        app.next_chg_ms = now_ms_() + 3600000u; /* the supervision never comes round */
        app.next_batt_ms = now_ms_() + 3600000u;
        run_until_ms_(now_ms_() + 20u);
        if (t_stop == 0u && !gl_sim_charger_on()) {
            t_stop = now_ms_();
        }
    }
    printf("    supervision stalled in the cradle at 22 C: the charger was %s; last cell reading %.1f s "
           "old then; reason %u\n", (t_stop != 0u) ? "stopped" : "LEFT RUNNING for the 30 s watched",
           (t_stop != 0u) ? (double)(t_stop - app.cell_temp_ms) / 1000.0 : 0.0,
           (unsigned)app.power.chg_reason);
    GL_CHECK(t_stop != 0u);
    GL_CHECK(t_stop != 0u && (t_stop - t0) <= GL_APP_CELL_TEMP_MAX_AGE_MS + 1000u);
    GL_CHECK_EQ(app.power.chg_reason, GL_CHG_TEMP_UNKNOWN);
    /* and it comes back by itself when the supervision does */
    app.next_chg_ms = now_ms_();
    app.next_batt_ms = now_ms_();
    run_until_ms_(now_ms_() + 6000u);
    GL_CHECK(gl_sim_charger_on());
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* Review finding (minor): the simulator's power rules fired in about two
 * thirds of random VBUS-bounce scenarios (USB still started, or CHG_INHIBIT
 * still low, at a sleep entry while the edge that would have dealt with it
 * was still pending).  The level is now dealt with before every sleep.
 * Random scenarios: VBUS edges singly and in bursts, temperature jumps, MCU
 * resets, reads in progress.  No fault is injected. */
#ifndef GL_REVIEW_STRESS_SCENARIOS
#define GL_REVIEW_STRESS_SCENARIOS 300u
#endif

static uint64_t rs_[2];
static uint64_t rnd64_(void)
{
    uint64_t s1 = rs_[0];
    const uint64_t s0 = rs_[1];
    rs_[0] = s0;
    s1 ^= s1 << 23;
    rs_[1] = s1 ^ s0 ^ (s1 >> 17) ^ (s0 >> 26);
    return rs_[1] + s0;
}
static uint32_t rnd_(void)
{
    return (uint32_t)(rnd64_() >> 32);
}

static bool st_vbus_;
static void st_toggle_(void *arg)
{
    (void)arg;
    st_vbus_ = !st_vbus_;
    gl_sim_set_input(GL_PIN_VBUS_SENSE, st_vbus_);
}
static const float st_temps_[8] = { -8.0f, -1.0f, 1.0f, 22.0f, 40.0f, 44.0f, 46.5f, 55.0f };
static void st_temp_(void *arg)
{
    gl_sim_imu_set_temperature(st_temps_[(uintptr_t)arg % 8u]);
}

GL_TEST(test_vbus_bounce_stress)
{
    const unsigned n = GL_REVIEW_STRESS_SCENARIOS;
    unsigned bad = 0, bad_end = 0, resets = 0, reads = 0, fast_left = 0;
    unsigned long toggles = 0, violations = 0;
    uint64_t worst_outside = 0;

    rs_[0] = 0x9E3779B97F4A7C15ull ^ 20261113u;
    rs_[1] = 0xD1B54A32D192ED03ull + 20261113u * 7919u;
    for (int i = 0; i < 20; i++) {
        (void)rnd64_();
    }
    for (unsigned sc = 0; sc < n; sc++) {
        const uint32_t dur = 30000u + rnd_() % 30000u;
        uint32_t t;
        unsigned n_ev = 0;

        world_defaults_();
        W.t_pick_s = 1.0 + 0.001 * (double)(rnd_() % 4000u);
        W.t_place_s = W.t_pick_s + 0.6;
        if (rnd_() % 3u == 0u) {
            W.jolt_at_s = W.t_place_s + 0.001 * (double)(rnd_() % 6000u); /* disturbed mid-read */
            W.jolt_len_s = 0.3;
        }
        board_up_(true);
        gl_sim_imu_set_temperature(st_temps_[rnd_() % 8u]);
        st_vbus_ = (rnd_() % 4u) == 0u;
        gl_sim_set_input(GL_PIN_VBUS_SENSE, st_vbus_);
        (void)gl_app_init(&app);
        watch_reset_();
        t = 200u + rnd_() % 3000u;
        while (t < dur && n_ev < 56u) {
            if (rnd_() % 3u == 0u) {
                (void)gl_sim_at_ms(t, st_temp_, (void *)(uintptr_t)(rnd_() % 8u));
                n_ev++;
            } else {
                const unsigned burst = (rnd_() % 3u == 0u) ? (1u + rnd_() % 6u) : 1u;
                for (unsigned k = 0; k < burst && n_ev < 56u; k++) {
                    (void)gl_sim_at_ms(t, st_toggle_, NULL);
                    n_ev++;
                    toggles++;
                    t += 1u + rnd_() % 40u;
                }
            }
            t += (rnd_() % 4u == 0u) ? (1u + rnd_() % 60u) : (300u + rnd_() % 9000u);
        }
        if (rnd_() % 3u == 0u) {
            const uint32_t t_rst = 500u + rnd_() % (dur - 1000u);
            run_until_ms_(t_rst);
            gl_sim_mcu_reset(GL_RESET_WATCHDOG);
            gl_sim_advance_ms(3);
            (void)gl_app_init(&app);
            resets++;
        }
        run_until_ms_(dur);
        run_until_ms_(dur + 12000u); /* one supervision period and a debounce after the last event */
        reads += app.reads_total;
        if (gl_sim_stats()->chg_outside_longest_us > worst_outside) {
            worst_outside = gl_sim_stats()->chg_outside_longest_us;
        }
        if ((app.clock_fast || gl_sim_clock() != GL_CLOCK_SLOW) &&
            !(app.capture_active || gl_read_busy(&app.read))) {
            fast_left++;
        }
        violations += gl_sim_violation_total();
        if ((st_vbus_ && app.ui.state != (uint8_t)GL_UI_CRADLE_USB) || (!st_vbus_ && app.usb_on) ||
            (st_vbus_ != app.power.vbus) || (!st_vbus_ && gl_sim_pin_drives_low(GL_PIN_CHG_INHIBIT))) {
            bad_end++;
        }
        if (gl_sim_violation_total() != 0u) {
            bad++;
            if (bad <= 3u) {
                printf("    scenario %u: %u violations (%s); at the end VBUS %d, UI %s, usb_on %d\n", sc,
                       gl_sim_violation_total(), gl_sim_violations()->first, (int)st_vbus_,
                       gl_ui_state_name((gl_ui_state_t)app.ui.state), (int)app.usb_on);
            }
        }
    }
    printf("    %u random scenarios, %lu VBUS edges, %u MCU resets, %u reads completed: %u scenarios with a "
           "simulator rule violation (%lu violations), %u with an inconsistent end state, %u left with "
           "the fast clock; longest charging outside 0..45 C: %.2f s\n",
           n, toggles, resets, reads, bad, violations, bad_end, fast_left, (double)worst_outside / 1e6);
    GL_CHECK_EQ(bad, 0);
    GL_CHECK_EQ(bad_end, 0);
    GL_CHECK_EQ(fast_left, 0);
    GL_CHECK((double)worst_outside / 1e6 <= 0.001 * (double)GL_SIM_CHG_REACT_MAX_MS);
}

int main(void)
{
    GL_RUN(test_double_tap_after_precision_starts_a_survey);
    GL_RUN(test_precision_result_is_upright_for_the_golfer);
    GL_RUN(test_distance_prompt_re_placing_reads_again);
    GL_RUN(test_dialled_distance_belongs_to_one_hole);
    GL_RUN(test_plays_like_is_the_flat_putt);
    GL_RUN(test_spin_abandoned_then_completed);
    GL_RUN(test_solved_aim_off_the_screen_keeps_its_style);
    GL_RUN(test_grain_setting_reaches_the_solver);
    GL_RUN(test_failed_switch_to_the_slow_clock_is_not_believed);
    GL_RUN(test_near_stick_is_one_candidate);
    GL_RUN(test_vbus_rising_edge_lost_while_asleep);
    GL_RUN(test_vbus_falling_edge_lost_in_the_cradle);
    GL_RUN(test_stalled_supervision_stops_the_charge);
    GL_RUN(test_vbus_bounce_stress);
    return gl_test_summary();
}
