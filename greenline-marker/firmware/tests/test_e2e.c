/*
 * test_e2e.c - the whole firmware on the host simulator, end to end.
 *
 * The application (app/), the drivers and the portable core run unmodified
 * against the simulated board (hal/host): simulated IMU, two simulated
 * camera cubes fed by the synthetic strip renderer, the LCD, flash, ADC and
 * USB models.  The tests drive the board only from OUTSIDE - how the marker
 * moves, what the cameras see, what the cradle and a USB host do - and
 * check what the firmware does at its pins and on its buses.
 *
 *   complete Quick Read   wake on motion -> still -> 1 s tilt -> camera
 *                         rail on -> horizon band -> L R R L x 8 strips ->
 *                         vision -> range -> solver stub -> screen ->
 *                         camera rail off -> sleep; with an independent
 *                         replay of the pin trace for the camera rail rule
 *   no flagstick          falls back without leaving the rail on
 *   bumped during a read  the read is aborted, rail off at once, re-read
 *   Precision Read        spin 180 degrees, re-read, combined slope, line
 *                         drawn through the ball position behind the marker
 *   zeroing               on a sloped table top (never in the cradle)
 *   cradle / USB          protocol over the simulated CDC port, charge gate,
 *                         reboot to the ROM bootloader, no Stop mode on USB
 */
#include "gl_e2e_world.h"

/* ======================================================================= */
/* 1. a complete Quick Read                                                 */
/* ======================================================================= */

GL_TEST(test_complete_quick_read)
{
    replay_t rp;
    const gl_sim_stats_t *stats;
    double true_d, true_range, ball_dist, ball_bearing;
    uint32_t t_result_ms = 0, t_capture_ms = 0;

    world_defaults_();
    W.sway_amp_px = 0.3; /* the stick sways +-0.3 px at 1.5 Hz: up to 2.8 px/s, 0.09 px per frame */
    board_up_(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    watch_reset_();

    /* ---- asleep after power-on ---- */
    GL_CHECK_EQ(app.ui.state, GL_UI_SLEEP);
    GL_CHECK(!gl_sim_lcd()->disp && !gl_sim_lcd()->extcomin);
    GL_CHECK(!gl_sim_cam_rail_on() && cam_pins_parked_());
    GL_CHECK(gl_sim_flash_stats()->deep_power_down);
    /* IMU: accelerometer low-power 15 Hz, gyro off, wake-up on INT1 */
    GL_CHECK_EQ(gl_sim_imu_reg(0x10), 0x43);
    GL_CHECK_EQ(gl_sim_imu_reg(0x11), 0x00);
    GL_CHECK_EQ(gl_sim_imu_reg(0x5E), 0x20);
    run_until_ms_(900);
    GL_CHECK_EQ(app.ui.state, GL_UI_SLEEP);
    stats = gl_sim_stats();
    GL_CHECK(stats->stop_us > 850000u); /* in Stop mode practically all the time */
    GL_CHECK_EQ(stats->idle_us, 0u);

    /* ---- the golfer puts the marker down at t = 1.0 .. 1.6 s ---- */
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 9000));
    t_result_ms = (uint32_t)(gl_sim_now_us() / 1000u);
    print_seen_();
    {
        static const uint8_t expect[] = { GL_UI_SLEEP, GL_UI_WAKE, GL_UI_WAIT_STILL,
                                          GL_UI_READ_TILT, GL_UI_CAPTURE, GL_UI_SHOW_RESULT };
        GL_CHECK_EQ(seen.n, GL_ARRAY_LEN(expect));
        for (unsigned i = 0; i < GL_ARRAY_LEN(expect) && i < seen.n; i++) {
            GL_CHECK_EQ(seen.state[i], expect[i]);
        }
        /* SOLVE is entered and left inside one loop iteration: 6 transitions
         * in all (MOTION, TIMEOUT, STILL, TILT_DONE, CAPTURE_DONE, SOLVE_DONE)
         * and nothing else */
        GL_CHECK_EQ(app.ui.transitions, 6u);
        if (seen.n >= 5u) {
            t_capture_ms = seen.t_ms[4];
        }
    }
    GL_CHECK(seen.t_ms[1] >= 1000u && seen.t_ms[1] < 1200u); /* woken by the motion */
    /* stillness for 0.5 s, then 1 s of averaging */
    if (seen.n >= 5u) {
        GL_CHECK(seen.t_ms[3] >= 1600u + 500u && seen.t_ms[3] < 1600u + 1000u);
        GL_CHECK(seen.t_ms[4] - seen.t_ms[3] >= 1000u && seen.t_ms[4] - seen.t_ms[3] < 1300u);
    }
    printf("    marker at rest at 1.60 s; result on the screen at %.2f s (%.2f s after coming to "
           "rest); camera part %.2f s\n", (double)t_result_ms / 1000.0,
           (double)t_result_ms / 1000.0 - 1.6, (double)(t_result_ms - t_capture_ms) / 1000.0);
    GL_CHECK(t_result_ms < 1600u + 4000u);

    /* ---- the camera rail ---- */
    stats = gl_sim_stats();
    GL_CHECK_EQ(stats->cam_rail_cycles, 1u);
    GL_CHECK(!gl_sim_cam_rail_on());
    GL_CHECK(cam_pins_parked_());
    GL_CHECK_EQ(seen.rail_outside_capture, 0u);
    GL_CHECK_EQ(stats->frames_captured, 1u + 4u * GL_APP_LRRL_REPEATS); /* band + 32 strips */
    GL_CHECK(stats->cam_rail_on_us < 2500000u);
    GL_CHECK_EQ(gl_sim_trace_lost(), 0u);
    replay_rail_rule_(&rp);
    printf("    camera rail: on once for %.0f ms; %u SCCB writes, %u captures; independent replay "
           "of %u trace records: %u pin-rule violations, %u bus accesses with the rail off\n",
           (double)rp.rail_on_us / 1000.0, rp.sccb_writes, rp.dcmi_starts,
           (unsigned)gl_sim_trace_count(), rp.pin_violations, rp.bus_violations);
    GL_CHECK_EQ(rp.pin_violations, 0u);
    GL_CHECK_EQ(rp.bus_violations, 0u);
    GL_CHECK_EQ(rp.rail_on_edges, 1u);
    GL_CHECK_EQ(rp.dcmi_starts, 33u);
    GL_CHECK_EQ(rp.rail_on_us, stats->cam_rail_on_us);
    GL_CHECK_NEAR(app.read.result.rail_on_ms, (double)rp.rail_on_us / 1000.0, 1.5);

    /* ---- what was measured ---- */
    true_d = 657.0 * (double)GL_CFG_CAM_BASELINE_M /
             (W.dist_m * cos(W.bearing_rad) - (double)GL_CFG_CAM_LEFT_Y_MM * 0.001);
    {
        /* horizontal distance from the stereo head (0, 15.6 mm) to the stick */
        const double sx = -W.dist_m * sin(W.bearing_rad);
        const double sy = W.dist_m * cos(W.bearing_rad);
        const double hy = (double)GL_CFG_CAM_LEFT_Y_MM * 0.001;
        const double by = (double)GL_CFG_BALL_CENTRE_Y_MM * 0.001;
        true_range = sqrt(sx * sx + (sy - hy) * (sy - hy));
        ball_dist = sqrt(sx * sx + (sy - by) * (sy - by));
        ball_bearing = atan2(-sx, sy - by);
    }
    GL_CHECK(app.cur.tilt_valid && app.cur.flag_found && app.cur.range_valid);
    GL_CHECK_EQ(app.read.result.groups_ok, GL_APP_LRRL_REPEATS);
    printf("    tilt: slope (%.3f, %.3f) %%, true (%.3f, %.3f) %%\n", 100.0 * (double)app.cur.slope.x,
           100.0 * (double)app.cur.slope.y, 100.0 * W.slope_x, 100.0 * W.slope_y);
    GL_CHECK_NEAR(app.cur.slope.x, W.slope_x, 0.0004);
    GL_CHECK_NEAR(app.cur.slope.y, W.slope_y, 0.0004);
    printf("    stereo: disparity %.4f px (true %.4f, claimed sigma %.4f) with the stick swaying "
           "+-0.3 px at 1.5 Hz and a 9 ms sensor phase offset\n", (double)app.cur.disparity_px,
           true_d, (double)app.cur.disparity_sigma_px);
    GL_CHECK_NEAR(app.cur.disparity_px, true_d, 0.03);
    printf("    range %.3f m +- %.3f (true %.3f; stereo %.3f, by angular height %.3f), bearing "
           "%.2f mrad (true from the left camera %.2f)\n", (double)app.cur.range.range_m,
           (double)app.cur.range.sigma_m, true_range, (double)app.cur.range.stereo_m,
           (double)app.cur.range.mono_m,
           1000.0 * (double)app.cur.bearing_rad,
           1000.0 * atan2(-(-W.dist_m * sin(W.bearing_rad) - (double)W.cam[0].pos_m.x),
                          W.dist_m * cos(W.bearing_rad) - (double)W.cam[0].pos_m.y));
    GL_CHECK_NEAR(app.cur.range.range_m, true_range, 0.03 * true_range);
    GL_CHECK(app.cur.top_valid); /* at 6 m the top of a 1.96 m stick is in the frame */
    GL_CHECK(app.cur.range.sources & GL_RANGE_SRC_STEREO);
    (void)ball_dist; /* the estimator's distance is the cameras': checked below */

    /* ---- the putt estimate (method B1) -> result screen ---- */
    GL_CHECK_EQ(app.solver_status, GL_OK);
    GL_CHECK(app.view.have_result && app.view.solved && app.view.flag_found);
    GL_CHECK_EQ(app.est.aim_source, GL_AIM_FROM_PATCH);
    GL_CHECK_EQ(app.est.solve_status, GL_SOLVE_OK);
    GL_CHECK(app.est.fit_converged && !app.est.flag_missing && !app.est.range_missing);
    GL_CHECK_EQ(app.solver_work.fit.n_starts, 1); /* B1: one convex fit, no horizon stage */
    GL_CHECK(!app.solver_work.fit.used_horizon);
    printf("    estimate: aim %.2f mrad from the line to the hole (%.2f cups), launch %.3f m/s, "
           "distance %.3f m, hole %.1f mm above the ball, confidence %.2f; %u trial rolls, %lu RK4 "
           "steps, %u fit iterations\n", 1000.0 * (double)app.est.phi_rad, (double)app.est.break_cups,
           (double)app.est.v0_mps, (double)app.est.distance_m, 1000.0 * (double)app.est.dz_hole_m,
           (double)app.est.confidence, (unsigned)app.est.n_rolls, (unsigned long)app.est.n_steps,
           (unsigned)app.solver_work.fit.n_iter);
    /* the hole as the estimator was given it: bearing referred to the ball,
     * distance from its own range fusion (stereo and angular height) */
    GL_CHECK_NEAR(app.meas_cur.flag_bearing_rad, ball_bearing, 0.001);
    GL_CHECK(fabs((double)app.meas_cur.flag_bearing_rad - (double)app.cur.bearing_rad) > 0.001);
    GL_CHECK_NEAR(app.est.bearing_rad, ball_bearing, 0.001);
    GL_CHECK_NEAR(app.est.distance_m, true_range, 0.03 * true_range);
    GL_CHECK(!isnan(app.est.distance_sigma_m) && app.est.distance_sigma_m > 0.0f);
    /* the disparity handed over is f B / DISTANCE, not a synthesised value */
    GL_CHECK_NEAR(app.meas_cur.flag_disparity_px,
                  (double)app.cur.disparity_px * cos((double)app.cur.bearing_rad), 1e-5);
    /* The green falls 2.0 % toward the hole and rises 1.2 % to the right:
     * the ball breaks left, so the aim is RIGHT of the hole (phi < 0).
     * Small-slope theory with the downhill pace gives about -80 mrad; a
     * downhill putt needs less than the flat-green launch speed of 2.63 m/s. */
    GL_CHECK(app.est.phi_rad < -0.060f && app.est.phi_rad > -0.100f);
    GL_CHECK(app.est.v0_mps > 2.0f && app.est.v0_mps < 2.63f);
    GL_CHECK_NEAR(app.est.break_cups, (double)app.est.distance_m * tan((double)app.est.phi_rad) / 0.10795,
                  1e-3);
    GL_CHECK_NEAR(app.view.aim_rad, ball_bearing + (double)app.est.phi_rad, 0.001);
    GL_CHECK_NEAR(app.view.ball_az_rad, 0.0, 1e-6);
    GL_CHECK_NEAR(app.view.slope_pct, 100.0 * sqrt(W.slope_x * W.slope_x + W.slope_y * W.slope_y),
                  0.05);
    GL_CHECK_NEAR(app.view.break_cups, app.est.break_cups, 1e-6);
    GL_CHECK_NEAR(app.view.distance_m, app.est.distance_m, 1e-6);
    /* the estimator's confidence: one placement at 6 m is a weak read */
    GL_CHECK_NEAR(app.view.confidence, app.est.confidence, 1e-6);
    GL_CHECK(app.view.confidence > 0.05f && app.view.confidence < 0.5f);
    GL_CHECK(app.meas_cur.flag_found && app.meas_cur.n_horizon > 20u);
    GL_CHECK_NEAR(app.meas_cur.tilt_x, W.slope_y, 0.0004); /* device +x = marker +y */
    GL_CHECK_NEAR(app.meas_cur.tilt_y, -W.slope_x, 0.0004);

    /* ---- the screen: the panel shows exactly the framebuffer, DISP is on,
     *      EXTCOMIN runs at 60 Hz, and the aim line is where it must be ---- */
    GL_CHECK(gl_sim_lcd()->disp && gl_sim_lcd()->extcomin);
    GL_CHECK_EQ(gl_sim_lcd()->extcomin_period, 547);
    GL_CHECK_EQ(panel_differs_from_framebuffer_(), 0u);
    {
        /* the line passes through the ball centre (off-screen, straight ahead)
         * in direction aim: at screen row y its column is
         * 63.5 + (y - 63.5 + BALL) * tan(aim) */
        unsigned on_line = 0, rows = 0;
        for (int y = 40; y <= 70; y += 5) {
            const double x = 63.5 + ((double)y - 63.5 + (double)GL_CFG_BALL_CENTRE_Y_PX) *
                                        tan(ball_bearing + (double)app.est.phi_rad);
            rows++;
            if (panel_black_((int)(x + 0.5), y)) {
                on_line++;
            }
        }
        GL_CHECK_EQ(on_line, rows);
        /* and it is a line, not a filled screen */
        GL_CHECK(!panel_black_(30, 45) && !panel_black_(64, 45));
    }
    /* only changed lines are sent: far fewer line writes than 128 per update */
    printf("    LCD: %u frames, %u lines written in %u ms of display-on time\n",
           (unsigned)gl_sim_lcd()->frames, (unsigned)gl_sim_lcd()->lines_written,
           (unsigned)(t_result_ms - seen.t_ms[1]));
    GL_CHECK(gl_sim_lcd()->lines_written < 5u * 128u);

    /* ---- while the result is shown: Stop mode between IMU samples ---- */
    {
        const uint64_t stop0 = gl_sim_stats()->stop_us, t0 = gl_sim_now_us();
        run_until_ms_(t_result_ms + 5000u);
        const double frac = (double)(gl_sim_stats()->stop_us - stop0) / (double)(gl_sim_now_us() - t0);
        printf("    result shown: MCU in Stop mode %.1f %% of the time (IMU at 240 Hz)\n",
               100.0 * frac);
        GL_CHECK(frac > 0.9);
        GL_CHECK_EQ(app.ui.state, GL_UI_SHOW_RESULT);
    }

    /* ---- 45 s later: asleep again ---- */
    GL_CHECK(run_until_state_(GL_UI_SLEEP, t_result_ms + 46000u));
    GL_CHECK(!gl_sim_lcd()->disp && !gl_sim_lcd()->extcomin);
    GL_CHECK(gl_sim_pin_drives_low(GL_PIN_LCD_DISP) && gl_sim_pin_drives_low(GL_PIN_LCD_SCS));
    GL_CHECK(!gl_sim_cam_rail_on() && cam_pins_parked_());
    GL_CHECK_EQ(gl_sim_imu_reg(0x10), 0x43);
    GL_CHECK_EQ(gl_sim_imu_reg(0x11), 0x00);
    GL_CHECK(gl_sim_flash_stats()->deep_power_down);
    {
        /* and it stays asleep, in Stop mode, waking only to kick the watchdog */
        const uint64_t stop0 = gl_sim_stats()->stop_us, t0 = gl_sim_now_us();
        const uint32_t loops0 = app.loops;
        run_until_ms_((uint32_t)(t0 / 1000u) + 60000u);
        GL_CHECK_EQ(app.ui.state, GL_UI_SLEEP);
        GL_CHECK(gl_sim_stats()->stop_us - stop0 > 59900000u);
        GL_CHECK(app.loops - loops0 <= 6u);
    }

    /* ---- the log: boot event + this read ---- */
    {
        gl_log_iter_t it;
        gl_log_rec_t rec;
        gl_log_read_t rd;
        uint8_t buf[128];
        unsigned reads = 0, events = 0, est_events = 0;
        gl_log_iter_begin(&app.log, &it);
        while (gl_log_iter_next(&app.log, &it, &rec, buf, sizeof(buf)) == GL_OK) {
            if (rec.type == GL_LOG_REC_READ) {
                reads++;
                GL_CHECK_EQ(gl_log_read_decode(buf, rec.len, &rd), GL_OK);
                GL_CHECK(rd.flags & GL_LOG_READ_FLAG_STICK_FOUND);
                GL_CHECK(rd.flags & GL_LOG_READ_FLAG_TOP_VISIBLE);
                GL_CHECK(!(rd.flags & GL_LOG_READ_FLAG_PRECISION));
                /* the distance logged is the one solved with and shown */
                GL_CHECK_NEAR(rd.range_m, app.est.distance_m, 1e-6);
                GL_CHECK_NEAR(rd.range_sigma_m, app.est.distance_sigma_m, 1e-6);
                GL_CHECK_NEAR(rd.slope_x, app.cur.slope.x, 1e-9);
                GL_CHECK_NEAR(rd.disparity_px, app.cur.disparity_px, 1e-9);
                GL_CHECK_EQ(rd.solver_status, GL_SOLVE_OK);
                GL_CHECK_NEAR(rd.v0_mps, app.est.v0_mps, 1e-6);
                GL_CHECK_NEAR(rd.aim_offset_m, app.est.break_m, 1e-6);
                GL_CHECK_NEAR(rd.aim_rad, app.view.aim_rad, 1e-6);
                GL_CHECK_EQ(rd.n_repeats, GL_APP_LRRL_REPEATS);
                GL_CHECK_EQ(rd.stimp_x2, 20);
                GL_CHECK_NEAR(rd.batt_mv, 3900.0, 5.0);
                GL_CHECK_NEAR(rd.temp_c_x100, 2200.0, 2.0);
            } else if (rec.type == GL_LOG_REC_EVENT) {
                gl_log_event_t ev;
                events++;
                GL_CHECK_EQ(gl_log_event_decode(buf, rec.len, &ev), GL_OK);
                if (ev.code == GL_APP_LOGEV_ESTIMATE) {
                    /* what the estimator said about the read: solved on the
                     * patch, status OK, fit converged, method B1, a stereo
                     * read, the line applies where the marker lies */
                    const uint32_t a = (uint32_t)ev.arg;
                    est_events++;
                    GL_CHECK_EQ(a & GL_APP_ESTFLAG_SOURCE_MASK, (unsigned)GL_AIM_FROM_PATCH);
                    GL_CHECK_EQ((a >> GL_APP_ESTFLAG_STATUS_SHIFT) & 7u, (unsigned)GL_SOLVE_OK);
                    GL_CHECK((a & GL_APP_ESTFLAG_FIT_CONVERGED) != 0u);
                    GL_CHECK_EQ((a & GL_APP_ESTFLAG_BASE_HIDDEN) != 0u, app.est.base_hidden);
                    GL_CHECK((a & (GL_APP_ESTFLAG_FLAG_MISSING | GL_APP_ESTFLAG_RANGE_MISSING)) == 0u);
                    GL_CHECK_EQ((a >> GL_APP_ESTFLAG_METHOD_SHIFT) & 3u, (unsigned)GL_SOLVER_METHOD_B1);
                    GL_CHECK_EQ((a >> GL_APP_ESTFLAG_TIER_SHIFT) & 3u, (unsigned)GL_READ_TIER_STEREO);
                    GL_CHECK((a & GL_APP_ESTFLAG_LINE_HERE) != 0u);
                    GL_CHECK_EQ(a >> GL_APP_ESTFLAG_ROLLS_SHIFT, (unsigned)app.est.n_rolls);
                }
            }
        }
        GL_CHECK_EQ(reads, 1u);
        GL_CHECK_EQ(events, 2u); /* the boot record and the estimator's flags of the read */
        GL_CHECK_EQ(est_events, 1u);
        (void)gl_mx25r_sleep(&app.flash);
    }
    /* the stick height was learned from this read (stereo range inside 4-7 m,
     * top and base seen) and stored */
    GL_CHECK_EQ(app.stick_height.updates, 1u);

    /* ---- nothing the board model objects to ---- */
    if (gl_sim_violation_total() != 0u) {
        printf("    first violation: %s\n", gl_sim_violations()->first);
    }
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
    GL_CHECK(gl_sim_stats()->watchdog_kicks > 100u);
}

/* ======================================================================= */
/* 1b. what the L R R L timing correction is worth                          */
/* ======================================================================= */

/* The stick leans over steadily at 6 px/s (0.2 px per frame) during the
 * capture.  The two sensors are 9 ms out of phase, so the L and R strips of
 * a group are not symmetric in time; without the correction the disparity
 * picks up (rate x mean time difference). */
static double drift_error_px_(bool correction, double phase_ms)
{
    double true_d;
    world_defaults_();
    W.dist_m = 5.0;
    W.bearing_rad = -0.03;
    project_scene_();
    board_up_(true);
    gl_sim_cam_set_phase_us(GL_CAM_RIGHT, (uint32_t)(phase_ms * 1000.0));
    (void)gl_app_init(&app);
    app.read.time_correction = correction;
    watch_reset_();
    if (!run_until_state_(GL_UI_CAPTURE, 6000)) {
        return 99.0;
    }
    W.drift_t0_s = (double)gl_sim_now_us() * 1e-6;
    W.drift_px_per_s = 6.0;
    if (!run_until_state_(GL_UI_SHOW_RESULT, 9000) || !app.cur.flag_found) {
        return 99.0;
    }
    true_d = 657.0 * (double)GL_CFG_CAM_BASELINE_M /
             (W.dist_m * cos(W.bearing_rad) - (double)GL_CFG_CAM_LEFT_Y_MM * 0.001);
    return (double)app.cur.disparity_px - true_d;
}

GL_TEST(test_lrrl_timing_correction)
{
    static const double phases_ms[] = { 2.0, 9.0, 16.0, 24.0, 31.0 };
    double worst_on = 0.0, worst_off = 0.0;
    printf("    stick drifting 6 px/s, disparity error (px) by sensor phase offset:\n");
    printf("    %-12s %12s %12s\n", "phase ms", "corrected", "uncorrected");
    for (size_t i = 0; i < GL_ARRAY_LEN(phases_ms); i++) {
        const double e_on = drift_error_px_(true, phases_ms[i]);
        const double e_off = drift_error_px_(false, phases_ms[i]);
        printf("    %-12.0f %+12.4f %+12.4f\n", phases_ms[i], e_on, e_off);
        if (fabs(e_on) > worst_on) {
            worst_on = fabs(e_on);
        }
        if (fabs(e_off) > worst_off) {
            worst_off = fabs(e_off);
        }
        GL_CHECK(fabs(e_on) < 0.02);
    }
    printf("    worst: %.4f px corrected, %.4f px uncorrected\n", worst_on, worst_off);
    GL_CHECK(worst_off > 3.0 * worst_on);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* ======================================================================= */
/* 1c. the fallback windowing mode: full VGA from the sensor, DCMI crop     */
/* ======================================================================= */

GL_TEST(test_quick_read_with_dcmi_crop_windowing)
{
    double true_range;
    world_defaults_();
    W.dist_m = 3.0; /* a short putt: the top of the stick is above the frame */
    W.bearing_rad = -0.08;
    project_scene_();
    board_up_(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    /* GL_PROV_OV7692_SENSOR_WINDOWING = 0: no sensor start / size register
     * is touched, the DCMI cuts the strips out of full frames */
    app.cam.cfg.sensor_windowing = false;
    watch_reset_();
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 9000));
    {
        const double sx = -W.dist_m * sin(W.bearing_rad), sy = W.dist_m * cos(W.bearing_rad);
        const double hy = (double)GL_CFG_CAM_LEFT_Y_MM * 0.001;
        true_range = sqrt(sx * sx + (sy - hy) * (sy - hy));
    }
    printf("    DCMI-crop windowing, stick at 3 m, 4.6 deg right: range %.3f m (true %.3f), "
           "bearing %.2f mrad, top in frame: %s, sources 0x%X\n", (double)app.cur.range.range_m,
           true_range, 1000.0 * (double)app.cur.bearing_rad, app.cur.top_valid ? "yes" : "no",
           (unsigned)app.cur.range.sources);
    GL_CHECK(app.cur.flag_found && app.cur.range_valid);
    GL_CHECK_NEAR(app.cur.range.range_m, true_range, 0.02 * true_range);
    GL_CHECK(app.cur.bearing_rad < -0.07f); /* to the right */
    GL_CHECK(!app.cur.top_valid);
    GL_CHECK_EQ(app.cur.range.sources, GL_RANGE_SRC_STEREO);
    GL_CHECK_EQ(app.stick_height.updates, 0u); /* nothing to learn from without the top */
    GL_CHECK_EQ(gl_sim_stats()->frames_captured, 33u);
    /* the sensors' window start / size registers still hold their reset values */
    GL_CHECK_EQ(seen.rail_outside_capture, 0u);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* ======================================================================= */
/* 1d. raw-strip logging for field data collection                          */
/* ======================================================================= */

static uint8_t logged_strip_[96 * 480];

GL_TEST(test_raw_strip_logging)
{
    gl_log_iter_t it;
    gl_log_rec_t rec;
    gl_log_raw_hdr_t h;
    static uint8_t buf[1024];
    unsigned chunks[2] = { 0, 0 }, other = 0, reads = 0;
    uint32_t t_result;

    /* level FIRST: the first left and the first right stick strip of a read */
    world_defaults_();
    W.keep_first_strips = true;
    board_up_(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    {
        gl_settings_t s = app.settings;
        s.raw_log_level = GL_RAWLOG_FIRST;
        GL_CHECK_EQ(gl_app_set_settings(&app, &s), GL_OK);
    }
    watch_reset_();
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 12000));
    t_result = (uint32_t)(gl_sim_now_us() / 1000u);
    GL_CHECK(app.cur.flag_found);
    GL_CHECK(W.have_first[0] && W.have_first[1]);
    for (int c = 0; c < 2; c++) {
        unsigned n = 0;
        uint32_t next_off = 0;
        memset(logged_strip_, 0, sizeof(logged_strip_));
        gl_log_iter_begin(&app.log, &it);
        while (gl_log_iter_next(&app.log, &it, &rec, buf, sizeof(buf)) == GL_OK) {
            if (rec.type != GL_LOG_REC_RAW_CHUNK) {
                continue;
            }
            GL_CHECK_EQ(gl_log_raw_hdr_decode(buf, rec.len, &h), GL_OK);
            if (h.camera != (uint8_t)c) {
                continue;
            }
            GL_CHECK_EQ(h.read_id, app.read_id);
            GL_CHECK_EQ(h.kind, 1);
            GL_CHECK_EQ(h.frame_index, c); /* strip 0 is the first left, strip 1 the first right */
            GL_CHECK(h.width == 96u && h.height == 480u && h.y0 == 0u);
            GL_CHECK_EQ(h.x0, W.first_x0[c]);
            GL_CHECK_EQ(h.offset, next_off); /* chunks in order, no gap */
            GL_CHECK(rec.len > GL_LOG_RAW_HDR_LEN && h.offset + (rec.len - GL_LOG_RAW_HDR_LEN) <=
                                                     sizeof(logged_strip_));
            memcpy(&logged_strip_[h.offset], &buf[GL_LOG_RAW_HDR_LEN], rec.len - GL_LOG_RAW_HDR_LEN);
            next_off = h.offset + (uint32_t)(rec.len - GL_LOG_RAW_HDR_LEN);
            n++;
        }
        chunks[c] = n;
        GL_CHECK_EQ(next_off, 96u * 480u);
        /* byte for byte what the camera delivered */
        GL_CHECK_MEM(logged_strip_, first_strip_[c], sizeof(logged_strip_));
    }
    gl_log_iter_begin(&app.log, &it);
    while (gl_log_iter_next(&app.log, &it, &rec, buf, sizeof(buf)) == GL_OK) {
        if (rec.type == GL_LOG_REC_READ) {
            reads++;
        } else if (rec.type != GL_LOG_REC_RAW_CHUNK) {
            other++;
        }
        GL_CHECK(rec.len <= 1014u); /* every record fits one LOG_READ response */
    }
    printf("    raw log level FIRST: %u + %u chunks of 960 pixels, read took %.2f s (3.44 s "
           "without logging)\n", chunks[0], chunks[1], (double)t_result / 1000.0 - 1.6);
    GL_CHECK_EQ(chunks[0], 48u);
    GL_CHECK_EQ(chunks[1], 48u);
    GL_CHECK_EQ(reads, 1u);
    GL_CHECK_EQ(other, 2u); /* the boot event and the estimator's flags of the read */
    GL_CHECK_EQ(gl_sim_violation_total(), 0);

    /* level ALL: the band and all 32 strips; the read outlasts the 8 s
     * capture limit of the UI and must still complete */
    world_defaults_();
    board_up_(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    {
        gl_settings_t s = app.settings;
        s.raw_log_level = GL_RAWLOG_ALL;
        GL_CHECK_EQ(gl_app_set_settings(&app, &s), GL_OK);
    }
    watch_reset_();
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 60000));
    t_result = (uint32_t)(gl_sim_now_us() / 1000u);
    GL_CHECK(app.cur.flag_found && app.cur.range_valid);
    {
        unsigned n = 0, bands = 0;
        gl_log_iter_begin(&app.log, &it);
        while (gl_log_iter_next(&app.log, &it, &rec, buf, sizeof(buf)) == GL_OK) {
            if (rec.type == GL_LOG_REC_RAW_CHUNK) {
                n++;
                GL_CHECK_EQ(gl_log_raw_hdr_decode(buf, rec.len, &h), GL_OK);
                if (h.kind == 0u) {
                    bands++;
                }
            }
        }
        printf("    raw log level ALL: %u chunks (%u of the band), %.1f kB of flash, read took "
               "%.1f s, camera rail on %.1f s\n", n, bands,
               (double)gl_sim_flash_stats()->bytes_programmed / 1000.0,
               (double)t_result / 1000.0 - 1.6, (double)gl_sim_stats()->cam_rail_on_us / 1e6);
        GL_CHECK_EQ(bands, 64u);          /* 640 x 96 / 960 */
        GL_CHECK_EQ(n, 64u + 32u * 48u);
    }
    GL_CHECK_EQ(seen.rail_outside_capture, 0u);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* ======================================================================= */
/* 2. no flagstick in view                                                  */
/* ======================================================================= */

GL_TEST(test_no_flagstick_falls_back)
{
    world_defaults_();
    W.stick = false;
    board_up_(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    watch_reset_();
    /* no flag and no dialled distance: the UI asks for the distance */
    GL_CHECK(run_until_state_(GL_UI_SETTINGS_DIAL, 9000));
    print_seen_();
    GL_CHECK(app.ui.dist_prompt);
    GL_CHECK_EQ(app.ui.item, GL_ITEM_DISTANCE);
    GL_CHECK(!app.cur.flag_found);
    /* the cameras were on for the horizon band only */
    GL_CHECK_EQ(gl_sim_stats()->frames_captured, 1u);
    GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, 1u);
    GL_CHECK(!gl_sim_cam_rail_on() && cam_pins_parked_());
    GL_CHECK(gl_sim_stats()->cam_rail_on_us < 400000u);
    GL_CHECK_EQ(seen.rail_outside_capture, 0u);
    GL_CHECK(app.read.result.n_horizon > 20u); /* the turf horizon was still measured */
    printf("    no stick: camera rail on for %.0f ms (band only), %u horizon samples kept\n",
           (double)gl_sim_stats()->cam_rail_on_us / 1000.0, (unsigned)app.read.result.n_horizon);

    /* with a dialled distance the same situation gives a tilt-only result */
    world_defaults_();
    W.stick = false;
    board_up_(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    {
        gl_settings_t s = app.settings;
        s.manual_distance_cm = 450;
        GL_CHECK_EQ(gl_app_set_settings(&app, &s), GL_OK);
    }
    watch_reset_();
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 9000));
    /* the estimator's flag-out fallback: a tilt-only plane along the visor
     * axis at the dialled distance, flagged, with low confidence */
    GL_CHECK_EQ(app.solver_status, GL_OK);
    GL_CHECK(app.view.have_result && !app.view.flag_found && app.view.solved);
    GL_CHECK(app.est.flag_missing && !app.est.range_missing);
    GL_CHECK_EQ(app.est.aim_source, GL_AIM_FROM_PATCH);
    GL_CHECK_EQ(app.solver_work.fit.n_starts, 0); /* no fit: the tilt plane itself */
    GL_CHECK_NEAR(app.view.distance_m, 4.5, 1e-4);
    GL_CHECK_NEAR(app.est.bearing_rad, 0.0, 0.0); /* along the visor axis */
    GL_CHECK(isnan(app.est.distance_sigma_m));    /* a dialled distance has no sigma */
    /* same green as before: aim right of the axis */
    GL_CHECK(app.est.phi_rad < -0.050f && app.est.phi_rad > -0.110f);
    GL_CHECK_NEAR(app.view.aim_rad, app.est.phi_rad, 1e-6);
    printf("    dialled 4.5 m, no flag: aim %.1f mrad from the visor axis, confidence %.2f\n",
           1000.0 * (double)app.est.phi_rad, (double)app.est.confidence);
    GL_CHECK(app.view.confidence > 0.0f && app.view.confidence <= 0.4f);
    GL_CHECK(isnan(app.meas_cur.flag_bearing_rad) && !app.meas_cur.flag_found);
    GL_CHECK_NEAR(app.meas_cur.user_distance_m, 4.5, 1e-4);
    GL_CHECK_EQ(panel_differs_from_framebuffer_(), 0u);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* ======================================================================= */
/* 3. bumped during the capture                                             */
/* ======================================================================= */

GL_TEST(test_bump_during_capture_aborts_and_rereads)
{
    uint32_t t_abort_ms = 0;
    world_defaults_();
    board_up_(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    watch_reset_();
    GL_CHECK(run_until_state_(GL_UI_CAPTURE, 6000));
    /* 0.4 s into the capture somebody kicks the marker */
    W.jolt_at_s = (double)gl_sim_now_us() * 1e-6 + 0.4;
    W.jolt_len_s = 0.25;
    GL_CHECK(run_until_state_(GL_UI_WAIT_STILL, 8000));
    t_abort_ms = (uint32_t)(gl_sim_now_us() / 1000u);
    /* aborted within one stillness block of the jolt, and the rail is off NOW */
    GL_CHECK((double)t_abort_ms / 1000.0 < W.jolt_at_s + 0.30);
    GL_CHECK(!gl_sim_cam_rail_on() && cam_pins_parked_());
    GL_CHECK(!app.capture_active && !gl_read_busy(&app.read));
    GL_CHECK(gl_sim_stats()->frames_captured < 33u);
    /* it settles and reads again by itself */
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 14000));
    print_seen_();
    GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, 2u);
    GL_CHECK(app.cur.flag_found && app.view.have_result);
    GL_CHECK_EQ(seen.rail_outside_capture, 0u);
    {
        replay_t rp;
        replay_rail_rule_(&rp);
        GL_CHECK_EQ(rp.pin_violations, 0u);
        GL_CHECK_EQ(rp.bus_violations, 0u);
        GL_CHECK_EQ(rp.rail_on_edges, 2u);
    }
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* ======================================================================= */
/* 4. Precision Read: spin 180 degrees, re-read                             */
/* ======================================================================= */

GL_TEST(test_precision_read_spin_and_reread)
{
    static const float acc_bias[3] = { 0.004f, -0.003f, 0.0f }; /* a device bias of 4 / 3 mrad */
    static const float gyro_bias[3] = { 0.004f, -0.002f, 0.001f };
    double t_now;

    world_defaults_();
    board_up_(true);
    gl_sim_imu_set_errors(0.0008f, 0.002f, acc_bias, gyro_bias);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    watch_reset_();
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 9000));
    /* the single read carries the device bias */
    GL_CHECK_NEAR(app.cur.slope.x, W.slope_x + 0.004, 0.0005);
    GL_CHECK_NEAR(app.cur.slope.y, W.slope_y - 0.003, 0.0005);
    printf("    single read: slope (%.3f, %.3f) %% with a device bias of (0.4, -0.3) %%; true "
           "(%.3f, %.3f) %%\n", 100.0 * (double)app.cur.slope.x, 100.0 * (double)app.cur.slope.y,
           100.0 * W.slope_x, 100.0 * W.slope_y);

    /* double tap -> "SPIN 180" prompt */
    gl_app_post(&app, GL_EV_DOUBLE_TAP, 0);
    run_until_ms_((uint32_t)(gl_sim_now_us() / 1000u) + 300u);
    GL_CHECK_EQ(app.ui.state, GL_UI_PRECISION_WAIT_SPIN);
    /* the golfer turns the marker by 176 degrees in 1.2 s */
    t_now = (double)gl_sim_now_us() * 1e-6;
    W.turn_at_s = t_now + 0.5;
    W.turn_len_s = 1.2;
    W.turn_rad = 176.0 * PI_D / 180.0;
    GL_CHECK(run_until_state_(GL_UI_READ_TILT, (uint32_t)(t_now * 1000.0) + 5000u));
    GL_CHECK_EQ(app.ui.read_kind, GL_READ_PRECISION);
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, (uint32_t)(t_now * 1000.0) + 8000u));
    print_seen_();
    /* no second camera read: the rail was on once */
    GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, 1u);
    GL_CHECK(app.cur.precision && app.view.precision);
    printf("    spin measured %.2f deg (true 176.00); combined slope (%.3f, %.3f) %%, true "
           "(%.3f, %.3f) %%\n", (double)app.cur.view_yaw_rad * 57.29578,
           100.0 * (double)app.cur.slope.x, 100.0 * (double)app.cur.slope.y, 100.0 * W.slope_x,
           100.0 * W.slope_y);
    GL_CHECK_NEAR(app.cur.view_yaw_rad, W.turn_rad, 0.02);
    /* the device bias has cancelled */
    GL_CHECK_NEAR(app.cur.slope.x, W.slope_x, 0.0006);
    GL_CHECK_NEAR(app.cur.slope.y, W.slope_y, 0.0006);
    /* the marker now faces away from the hole: the ball position is behind
     * it and the line is drawn through that point */
    GL_CHECK_NEAR(fabs((double)app.view.ball_az_rad), 176.0 * PI_D / 180.0, 0.02);
    GL_CHECK_EQ(app.solver_status, GL_OK);
    GL_CHECK_NEAR(app.est.bearing_rad, app.meas_cur.flag_bearing_rad, 1e-6);
    GL_CHECK_EQ(app.meas_cur.tilt_reads, 2); /* the estimator is told it is a Precision Read */
    GL_CHECK(app.est.phi_rad < -0.060f && app.est.phi_rad > -0.100f);
    GL_CHECK_NEAR(gl_wrap_pi(app.view.aim_rad - app.view.ball_az_rad),
                  (double)app.est.bearing_rad + (double)app.est.phi_rad, 1e-4);
    GL_CHECK_EQ(panel_differs_from_framebuffer_(), 0u);
    {
        gl_gfx_aim_info_t info;
        static gl_gfx_t tmp;
        gl_gfx_init(&tmp);
        gl_gfx_set_clip(&tmp, true);
        gl_gfx_aim_line_at(&tmp, app.view.aim_rad, app.view.ball_az_rad, 3.0f, &info);
        GL_CHECK(info.on_screen); /* a solid line through the ball, not the dashed fallback */
    }
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* ======================================================================= */
/* 4b. Survey: a second drop along the line                                 */
/* ======================================================================= */

GL_TEST(test_survey_second_drop)
{
    double t_now;
    world_defaults_();
    board_up_(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    watch_reset_();
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 9000));
    /* double tap twice: Precision prompt, then Survey (the shown read is drop 1) */
    gl_app_post(&app, GL_EV_DOUBLE_TAP, 0);
    run_until_ms_((uint32_t)(gl_sim_now_us() / 1000u) + 100u);
    GL_CHECK_EQ(app.ui.state, GL_UI_PRECISION_WAIT_SPIN);
    gl_app_post(&app, GL_EV_DOUBLE_TAP, 0);
    run_until_ms_((uint32_t)(gl_sim_now_us() / 1000u) + 100u);
    GL_CHECK_EQ(app.ui.state, GL_UI_SURVEY_NEXT_DROP);
    GL_CHECK_EQ(app.survey.count, 1);
    GL_CHECK(app.survey.drop[0].flags & GL_DROP_FLAG_STICK);
    GL_CHECK_NEAR(app.survey.drop[0].range_m, 6.0, 0.15);
    GL_CHECK(app.meas[0].flag_found);

    /* the golfer carries the marker 3 m along the line and puts it down:
     * the stick is now 3 m away, the green there slopes differently */
    t_now = (double)gl_sim_now_us() * 1e-6;
    W.t_pick_s = t_now + 0.5;
    W.t_place_s = t_now + 2.0;
    run_until_ms_((uint32_t)((t_now + 1.0) * 1000.0));
    W.dist_m = 3.0;
    W.bearing_rad = -0.02;
    W.slope_x = -0.004;
    W.slope_y = -0.015;
    project_scene_();
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, (uint32_t)(t_now * 1000.0) + 9000u));
    print_seen_();
    GL_CHECK_EQ(app.ui.read_kind, GL_READ_SURVEY);
    GL_CHECK_EQ(app.ui.survey_count, 2);
    GL_CHECK_EQ(app.survey.count, 2);
    GL_CHECK_NEAR(app.survey.drop[1].range_m, 3.0, 0.08);
    GL_CHECK_NEAR(app.survey.drop[1].slope.y, -0.015, 0.0005);
    GL_CHECK_NEAR(app.meas[1].tilt_x, -0.015, 0.0005); /* device +x = marker +y */
    GL_CHECK_NEAR(app.meas[0].tilt_x, -0.020, 0.0005);
    GL_CHECK_EQ(gl_survey_farthest(&app.survey), 0);   /* drop 1 is the ball end */
    /* ... and the estimator was told so: the putt starts at drop 1, and the
     * marker, which now lies 3 m short of the hole, is NOT at the ball: the
     * numbers are shown, no aim line (the full Survey flows, with the line
     * measured from the pixels, are in tests/test_e2e_putt.c) */
    GL_CHECK_EQ(app.solve_drops, 2);
    GL_CHECK_EQ(app.solve_ball, 0);
    GL_CHECK(!app.line_here && !app.view.line_here);
    GL_CHECK_EQ(app.view.drop, 2);
    GL_CHECK_NEAR(app.view.distance_m, app.est.distance_m, 1e-6);
    GL_CHECK_NEAR(app.est.distance_m, 6.0, 0.15); /* from the BALL, not from where it lies */
    /* the Survey estimate: both drops located on the line, the second one
     * about 3 m along it; the slope toward the hole eases from -2.0 % to
     * -1.5 % (curvature c > 0) and the cross slope changes sign (twist) */
    GL_CHECK_EQ(app.solver_status, GL_OK);
    GL_CHECK(app.view.have_result && app.view.solved);
    GL_CHECK_EQ(app.solver_work.fit.n_drops, 2);
    GL_CHECK_NEAR(app.solver_work.fit.stations_m[0], 0.0, 0.0);
    GL_CHECK_NEAR(app.solver_work.fit.stations_m[1], 3.0, 0.15);
    GL_CHECK(app.est.fit_converged && !app.est.flag_missing && !app.est.range_missing);
    GL_CHECK(app.est.patch[2] > 0.0005f && app.est.patch[2] < 0.003f);
    GL_CHECK(app.est.patch[3] > 0.001f);
    printf("    Survey estimate from 2 drops: patch a %.4f b %.4f c %.5f d %.5f, aim %.1f mrad, "
           "status %u, aim source %u\n", (double)app.est.patch[0], (double)app.est.patch[1],
           (double)app.est.patch[2], (double)app.est.patch[3], 1000.0 * (double)app.est.phi_rad,
           (unsigned)app.est.solve_status, (unsigned)app.est.aim_source);
    GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, 2u);
    GL_CHECK_EQ(seen.rail_outside_capture, 0u);
    /* double tap ends the survey */
    gl_app_post(&app, GL_EV_DOUBLE_TAP, 0);
    run_until_ms_((uint32_t)(gl_sim_now_us() / 1000u) + 100u);
    GL_CHECK_EQ(app.ui.survey_count, 0);
    GL_CHECK_EQ(app.survey.count, 0);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* ======================================================================= */
/* 5. zeroing on a hard flat surface (never in the cradle)                  */
/* ======================================================================= */

/* Drive the UI into the zeroing state the way the golfer does (the
 * gestures themselves are tested in test_gesture.c; here their events are
 * injected). */
static void start_zeroing_(void)
{
    gl_app_post(&app, GL_EV_UPRIGHT, 0);
    for (int i = 0; i < (int)GL_UI_ITEM_ZERO; i++) {
        gl_app_post(&app, GL_EV_DOUBLE_TAP, 0);
    }
    gl_app_post(&app, GL_EV_DIAL_STEP, 1);
    gl_app_post(&app, GL_EV_FLAT, 0);
    run_until_ms_((uint32_t)(gl_sim_now_us() / 1000u) + 50u);
}

GL_TEST(test_zeroing_on_a_table_top)
{
    static const float acc_bias[3] = { 0.0035f, -0.0025f, 0.0f };
    static const float gyro_bias[3] = { 0.004f, -0.002f, 0.001f };
    double t_now;

    world_defaults_();
    W.stick = false;
    W.slope_x = 0.006; /* the table top is not level: 0.6 % and -1.1 % */
    W.slope_y = -0.011;
    board_up_(true);
    gl_sim_imu_set_errors(0.0008f, 0.002f, acc_bias, gyro_bias);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    watch_reset_();
    GL_CHECK(run_until_state_(GL_UI_WAIT_STILL, 4000));
    GL_CHECK_EQ(app.cal_tilt.flags & GL_CAL_TILT_FLAG_FLIP, 0);

    start_zeroing_();
    GL_CHECK_EQ(app.ui.state, GL_UI_CAL_ZERO);
    GL_CHECK(app.zero.active);
    GL_CHECK_EQ(app.zero.step, 0);
    /* first read done -> "TURN 180" */
    t_now = (double)gl_sim_now_us() * 1e-6;
    while (app.zero.active && app.zero.step == 0u && (double)gl_sim_now_us() * 1e-6 < t_now + 4.0) {
        run_until_ms_((uint32_t)(gl_sim_now_us() / 1000u) + 10u);
    }
    GL_CHECK_EQ(app.zero.step, 1);
    GL_CHECK_EQ(app.view.cal_step, 1);
    /* turned by 171 degrees (it need not be exact: the gyro measures it) */
    t_now = (double)gl_sim_now_us() * 1e-6;
    W.turn_at_s = t_now + 0.4;
    W.turn_len_s = 1.5;
    W.turn_rad = -171.0 * PI_D / 180.0;
    GL_CHECK(run_until_state_(GL_UI_WAIT_STILL, (uint32_t)(t_now * 1000.0) + 9000u));
    print_seen_();
    GL_CHECK(app.cal_tilt.flags & GL_CAL_TILT_FLAG_FLIP);
    printf("    zeroing on a table sloped (0.6, -1.1) %%, turn of -171 deg: stored bias (%.3f, "
           "%.3f) mrad, true (3.500, -2.500)\n", 1000.0 * (double)app.cal_tilt.flip_bias_x,
           1000.0 * (double)app.cal_tilt.flip_bias_y);
    GL_CHECK_NEAR(app.cal_tilt.flip_bias_x, 0.0035, 0.0004);
    GL_CHECK_NEAR(app.cal_tilt.flip_bias_y, -0.0025, 0.0004);
    GL_CHECK_NEAR(app.cal_tilt.flip_temp_c, 22.0, 0.1);
    /* it is in the flash store: a fresh boot loads it */
    {
        const float bx = app.cal_tilt.flip_bias_x, by = app.cal_tilt.flip_bias_y;
        world_defaults_();
        W.stick = false;
        W.t_pick_s = 1e9; /* left alone */
        W.t_place_s = 1e9;
        board_up_(false); /* power cycle: the flash keeps its contents */
        GL_CHECK_EQ(gl_app_init(&app), GL_OK);
        GL_CHECK(app.cal_tilt.flags & GL_CAL_TILT_FLAG_FLIP);
        GL_CHECK(app.cal_tilt.flip_bias_x == bx && app.cal_tilt.flip_bias_y == by);
    }
    GL_CHECK_EQ(gl_sim_violation_total(), 0);

    /* a turn of only 120 degrees is refused and nothing is stored */
    world_defaults_();
    W.stick = false;
    board_up_(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    watch_reset_();
    GL_CHECK(run_until_state_(GL_UI_WAIT_STILL, 4000));
    start_zeroing_();
    t_now = (double)gl_sim_now_us() * 1e-6;
    while (app.zero.active && app.zero.step == 0u && (double)gl_sim_now_us() * 1e-6 < t_now + 4.0) {
        run_until_ms_((uint32_t)(gl_sim_now_us() / 1000u) + 10u);
    }
    t_now = (double)gl_sim_now_us() * 1e-6;
    W.turn_at_s = t_now + 0.4;
    W.turn_len_s = 1.2;
    W.turn_rad = 120.0 * PI_D / 180.0;
    GL_CHECK(run_until_state_(GL_UI_ERROR, (uint32_t)(t_now * 1000.0) + 9000u));
    GL_CHECK_EQ(app.ui.error_code, GL_ERR_RANGE);
    GL_CHECK_EQ(app.cal_tilt.flags & GL_CAL_TILT_FLAG_FLIP, 0);

    /* put into the cradle half way through: abandoned, nothing stored */
    world_defaults_();
    W.stick = false;
    board_up_(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    watch_reset_();
    GL_CHECK(run_until_state_(GL_UI_WAIT_STILL, 4000));
    start_zeroing_();
    GL_CHECK_EQ(app.ui.state, GL_UI_CAL_ZERO);
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    run_until_ms_((uint32_t)(gl_sim_now_us() / 1000u) + 100u);
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_USB);
    GL_CHECK(!app.zero.active);
    run_until_ms_((uint32_t)(gl_sim_now_us() / 1000u) + 4000u);
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_USB);
    GL_CHECK_EQ(app.cal_tilt.flags & GL_CAL_TILT_FLAG_FLIP, 0);
    /* and it cannot be started there, neither by gesture nor over USB */
    start_zeroing_();
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_USB);
    GL_CHECK_EQ(gl_app_start_cal(&app, GL_CALPROC_ZERO, 0), GL_ERR_STATE);
    GL_CHECK(!app.zero.active);
}

/* ======================================================================= */
/* 6. cradle: USB protocol, charging, reboot to the ROM bootloader          */
/* ======================================================================= */

GL_TEST(test_cradle_usb_charging_and_dfu)
{
    uint8_t seq;
    const uint8_t *pl;
    int n;

    /* a device that has done one read, so that the log holds something */
    world_defaults_();
    board_up_(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    watch_reset_();
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 9000));

    /* into the cradle: VBUS appears */
    host_rx_len_ = 0;
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    gl_sim_usb_host_open(true);
    run_until_ms_((uint32_t)(gl_sim_now_us() / 1000u) + 200u);
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_USB);
    GL_CHECK(app.usb_on && gl_hal_usb_connected());
    /* charging allowed: the cell NTC reads 22 C, inside the window, and the
     * die sensors vouch for it -> CHG_INHIBIT stays released (the charger of
     * rev C2 runs by default; the firmware can only stop it) */
    GL_CHECK(!gl_sim_pin_drives_low(GL_PIN_CHG_INHIBIT));
    GL_CHECK(gl_sim_charger_on());
    GL_CHECK(app.power.charge_enabled && !app.power.inhibit);
    GL_CHECK_EQ(app.power.chg_reason, GL_CHG_ALLOWED);
    GL_CHECK(app.power.cell_temp_valid);
    GL_CHECK_NEAR(app.power.cell_temp_c, 22.0, 0.1);

    /* PING */
    host_send_(1, GL_CMD_PING, "hello", 5);
    n = host_get_(GL_CMD_PING | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
    GL_CHECK_EQ(n, 6);
    GL_CHECK_EQ(seq, 1);
    GL_CHECK(pl[0] == GL_OK && memcmp(&pl[1], "hello", 5) == 0);
    /* GET_INFO: protocol 1, hardware rev C, the version of the ported solver */
    host_send_(2, GL_CMD_GET_INFO, NULL, 0);
    n = host_get_(GL_CMD_GET_INFO | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
    GL_CHECK_EQ(n, 1 + (int)GL_PROTO_INFO_LEN);
    GL_CHECK_EQ(pl[1], GL_PROTO_VERSION);
    GL_CHECK_EQ(pl[2], GL_APP_HW_REV);
    GL_CHECK_EQ(gl_get_u32(&pl[9]), GL_SOLVER_VERSION);
    GL_CHECK(GL_SOLVER_VERSION != 0u);
    /* GET_STATUS */
    host_send_(3, GL_CMD_GET_STATUS, NULL, 0);
    n = host_get_(GL_CMD_GET_STATUS | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
    GL_CHECK_EQ(n, 1 + (int)GL_PROTO_STATUS_LEN);
    GL_CHECK_NEAR(gl_get_u16(&pl[1]), 3900.0, 5.0);          /* battery mV */
    GL_CHECK_NEAR((int16_t)gl_get_u16(&pl[3]), 220.0, 1.0);  /* 22.0 C */
    GL_CHECK_EQ(pl[5], GL_UI_CRADLE_USB);
    GL_CHECK_EQ(pl[6] & 0x05u, 0x05u);                       /* VBUS, charge enabled */
    GL_CHECK_EQ(gl_get_u32(&pl[9]), 1u);                     /* one read so far */
    /* SET_SETTINGS: Stimp 11.5, metres -> applied and stored */
    {
        gl_settings_t s = app.settings;
        uint8_t blob[GL_SETTINGS_BLOB_LEN];
        s.stimp_x2 = 23;
        s.units = GL_UNITS_METRES;
        gl_settings_encode(&s, blob);
        host_send_(4, GL_CMD_SET_SETTINGS, blob, sizeof(blob));
        n = host_get_(GL_CMD_SET_SETTINGS | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
        GL_CHECK_EQ(n, 1);
        GL_CHECK_EQ(pl[0], GL_OK);
        GL_CHECK_EQ(app.settings.stimp_x2, 23);
        GL_CHECK_EQ(app.ui.edit.units, GL_UNITS_METRES);
    }
    /* GET_CAL tilt */
    {
        const uint8_t id = GL_CAL_ID_TILT;
        host_send_(5, GL_CMD_GET_CAL, &id, 1);
        n = host_get_(GL_CMD_GET_CAL | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
        GL_CHECK_EQ(n, 2 + (int)GL_CAL_TILT_BLOB_LEN);
        GL_CHECK_EQ(pl[1], GL_CAL_ID_TILT);
    }
    /* START_CAL: the zeroing is refused in the cradle; an unimplemented
     * factory procedure says so */
    {
        const uint8_t zero[2] = { GL_CALPROC_ZERO, 0 }, hor[2] = { GL_CALPROC_CAM_HORIZON, 0 };
        host_send_(6, GL_CMD_START_CAL, zero, 2);
        n = host_get_(GL_CMD_START_CAL | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
        GL_CHECK_EQ(n, 1);
        GL_CHECK_EQ(pl[0], GL_ERR_STATE);
        GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_USB);
        /* a factory procedure from a LOCKED session is refused by the
         * protocol; unlocked, the unimplemented one says so */
        host_send_(7, GL_CMD_START_CAL, hor, 2);
        n = host_get_(GL_CMD_START_CAL | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
        GL_CHECK_EQ(pl[0], GL_ERR_STATE);
        host_send_(70, GL_CMD_UNLOCK, "GLFC", 4);
        n = host_get_(GL_CMD_UNLOCK | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
        GL_CHECK_EQ(pl[0], GL_OK);
        host_send_(71, GL_CMD_START_CAL, hor, 2);
        n = host_get_(GL_CMD_START_CAL | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
        GL_CHECK_EQ(pl[0], GL_ERR_UNSUPPORTED);
        host_send_(72, GL_CMD_UNLOCK, "lock", 4);
        (void)host_get_(GL_CMD_UNLOCK | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
        GL_CHECK(!app.proto.unlocked);
    }
    /* LOG_READ from the start: the boot event and the read record */
    {
        const uint8_t restart = 1;
        size_t pos = 2;
        unsigned reads = 0, events = 0;
        host_send_(8, GL_CMD_LOG_READ, &restart, 1);
        n = host_get_(GL_CMD_LOG_READ | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
        GL_CHECK(n > 2);
        GL_CHECK_EQ(pl[0], GL_OK);
        GL_CHECK_EQ(pl[1], 0); /* no more */
        while (n > 0 && pos + 8u <= (size_t)n) {
            const unsigned len = gl_get_u16(&pl[pos + 2u]);
            if (pl[pos] == GL_LOG_REC_READ) {
                gl_log_read_t rd;
                reads++;
                GL_CHECK_EQ(len, GL_LOG_READ_LEN);
                GL_CHECK_EQ(gl_log_read_decode(&pl[pos + 8u], len, &rd), GL_OK);
                GL_CHECK_NEAR(rd.range_m, app.est.distance_m, 1e-6);
            } else if (pl[pos] == GL_LOG_REC_EVENT) {
                events++;
            }
            pos += 8u + len;
        }
        GL_CHECK_EQ(reads, 1u);
        /* boot, the estimator's flags of the read, and the charge gate
         * changing its mind when the marker met the cradle */
        GL_CHECK_EQ(events, 3u);
    }
    /* live stream for the factory: IMU and power every 20 ms */
    {
        const uint8_t req[4] = { (uint8_t)((1u << GL_STREAM_IMU) | (1u << GL_STREAM_POWER)), 0, 20, 0 };
        const uint8_t off[4] = { 0, 0, 0, 0 };
        host_send_(9, GL_CMD_STREAM, req, 4);
        n = host_get_(GL_CMD_STREAM | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
        GL_CHECK_EQ(pl[0], GL_OK);
        n = host_get_(GL_PROTO_STREAM_FLAG | GL_STREAM_IMU, &seq, &pl);
        GL_CHECK_EQ(n, 14);
        /* at rest on a green sloped (1.2, -2.0) %: az near 1 g = 16393 counts */
        GL_CHECK_NEAR((int16_t)gl_get_u16(&pl[4]), 16389.0, 60.0);
        GL_CHECK_NEAR((int16_t)gl_get_u16(&pl[0]), 0.012 * 16389.0, 60.0);
        n = host_get_(GL_PROTO_STREAM_FLAG | GL_STREAM_POWER, &seq, &pl);
        GL_CHECK_EQ(n, 4);
        GL_CHECK_NEAR(gl_get_u16(&pl[0]), 3900.0, 5.0);
        host_send_(10, GL_CMD_STREAM, off, 4);
        (void)host_get_(GL_CMD_STREAM | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
    }
    /* too hot to charge: the board (cell, IMU, MCU) goes to 47 C; the gate
     * pulls CHG_INHIBIT low at its next check, within the supervision period */
    {
        const uint64_t out0 = gl_sim_stats()->chg_outside_us;
        gl_sim_imu_set_temperature(47.0f);
        run_until_ms_((uint32_t)(gl_sim_now_us() / 1000u) + GL_APP_CHG_TEMP_PERIOD_MS + 200u);
        GL_CHECK(gl_sim_pin_drives_low(GL_PIN_CHG_INHIBIT));
        GL_CHECK(!gl_sim_charger_on());
        GL_CHECK(!app.power.charge_enabled && app.power.inhibit);
        GL_CHECK_EQ(app.power.chg_reason, GL_CHG_TOO_HOT);
        GL_CHECK_EQ(app.view.chg_blocked, 2);
        printf("    cradle at 47 C: the charger ran for %.2f s before the firmware stopped it "
               "(supervision period %.0f s)\n",
               (double)(gl_sim_stats()->chg_outside_us - out0) / 1e6,
               (double)GL_APP_CHG_TEMP_PERIOD_MS / 1000.0);
        GL_CHECK(gl_sim_stats()->chg_outside_us - out0 <= (uint64_t)GL_APP_CHG_TEMP_PERIOD_MS * 1000u + 50000u);
        /* and it stays stopped for as long as it is hot */
        run_until_ms_((uint32_t)(gl_sim_now_us() / 1000u) + 60000u);
        GL_CHECK(gl_sim_pin_drives_low(GL_PIN_CHG_INHIBIT));
        GL_CHECK(gl_sim_stats()->chg_outside_us - out0 <= (uint64_t)GL_APP_CHG_TEMP_PERIOD_MS * 1000u + 50000u);
        /* back to 30 C: released again */
        gl_sim_imu_set_temperature(30.0f);
        run_until_ms_((uint32_t)(gl_sim_now_us() / 1000u) + GL_APP_CHG_TEMP_PERIOD_MS + 200u);
        GL_CHECK(!gl_sim_pin_drives_low(GL_PIN_CHG_INHIBIT));
        GL_CHECK(gl_sim_charger_on());
        GL_CHECK_EQ(app.power.chg_reason, GL_CHG_ALLOWED);
    }

    /* on USB the MCU never enters Stop mode (the simulator would count it) */
    GL_CHECK_EQ(gl_sim_violations()->stop_mode, 0u);
    GL_CHECK(gl_sim_stats()->idle_us > 60000000u);

    /* REBOOT to the ROM DFU bootloader: refused from a locked session (the
     * ROM bootloader has no time-out and the consumer cradle no reset
     * contact), carried out after UNLOCK */
    host_rx_len_ = 0;
    host_send_(11, GL_CMD_REBOOT, "DFU!", 4);
    n = host_get_(GL_CMD_REBOOT | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
    GL_CHECK_EQ(n, 1);
    GL_CHECK_EQ(pl[0], GL_ERR_STATE);
    run_until_ms_((uint32_t)(gl_sim_now_us() / 1000u) + 100u);
    GL_CHECK_EQ(gl_sim_stats()->reboots, 0u);
    host_send_(12, GL_CMD_UNLOCK, "GLFC", 4);
    n = host_get_(GL_CMD_UNLOCK | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
    host_send_(13, GL_CMD_REBOOT, "DFU!", 4);
    n = host_get_(GL_CMD_REBOOT | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
    GL_CHECK_EQ(n, 1);
    GL_CHECK_EQ(pl[0], GL_OK);
    run_until_ms_((uint32_t)(gl_sim_now_us() / 1000u) + 100u);
    GL_CHECK_EQ(gl_sim_stats()->reboots, 1u);
    GL_CHECK_EQ(gl_sim_stats()->last_reboot, GL_REBOOT_ROM_DFU);

    /* out of the cradle: USB off, asleep, charging path released */
    gl_sim_set_input(GL_PIN_VBUS_SENSE, false);
    gl_sim_usb_host_open(false);
    run_until_ms_((uint32_t)(gl_sim_now_us() / 1000u) + 300u);
    GL_CHECK_EQ(app.ui.state, GL_UI_SLEEP);
    GL_CHECK(!app.usb_on && !gl_hal_usb_connected());
    GL_CHECK(!gl_sim_pin_drives_low(GL_PIN_CHG_INHIBIT));
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_CHG_INHIBIT), GL_PIN_MODE_ANALOG);
    GL_CHECK(!gl_sim_lcd()->disp);
    if (gl_sim_violation_total() != 0u) {
        printf("    first violation: %s\n", gl_sim_violations()->first);
    }
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* ======================================================================= */
/* 7. start-up with a device missing                                        */
/* ======================================================================= */

GL_TEST(test_missing_devices_are_reported_not_fatal)
{
    /* no IMU: fault screen, then asleep; the cradle still works */
    world_defaults_();
    board_up_(true);
    gl_sim_imu_set_present(false);
    GL_CHECK(gl_app_init(&app) != GL_OK);
    watch_reset_();
    run_until_ms_(200);
    GL_CHECK_EQ(app.ui.state, GL_UI_ERROR);
    GL_CHECK(gl_sim_lcd()->disp);
    GL_CHECK_EQ(panel_differs_from_framebuffer_(), 0u);
    GL_CHECK(run_until_state_(GL_UI_SLEEP, 7000));
    GL_CHECK(!gl_sim_lcd()->disp);
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    run_until_ms_((uint32_t)(gl_sim_now_us() / 1000u) + 200u);
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_USB);
    /* The IMU is missing, but since rev C2 the IMU's die sensor is only a
     * plausibility check: the cell NTC reads 22 C and the MCU's own sensor
     * vouches for it, so the charger keeps running (phase 1, whose gate
     * needed the IMU, stopped the charge here) */
    run_until_ms_((uint32_t)(gl_sim_now_us() / 1000u) + 2000u);
    GL_CHECK(!gl_sim_pin_drives_low(GL_PIN_CHG_INHIBIT));
    GL_CHECK(gl_sim_charger_on());
    GL_CHECK_EQ(app.power.chg_reason, GL_CHG_ALLOWED);
    GL_CHECK(!app.temp_valid && app.power.mcu_temp_valid && app.power.cell_temp_valid);
    GL_CHECK(!gl_sim_cam_rail_on() && cam_pins_parked_());

    /* a camera that does not answer: CAPTURE fails, the rail is off again */
    world_defaults_();
    board_up_(true);
    gl_sim_cam_set_present(GL_CAM_RIGHT, false);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    watch_reset_();
    GL_CHECK(run_until_state_(GL_UI_ERROR, 9000));
    print_seen_();
    GL_CHECK_EQ(app.last_error, GL_ERR_IO);
    GL_CHECK(!gl_sim_cam_rail_on() && cam_pins_parked_());
    GL_CHECK_EQ(gl_sim_violations()->cam_rail, 0u);
    GL_CHECK(run_until_state_(GL_UI_SLEEP, (uint32_t)(gl_sim_now_us() / 1000u) + 6000u));
}

/* Battery: below the LOW threshold the device still reads; below CRITICAL
 * it shows the warning and sleeps without ever switching the cameras on. */
GL_TEST(test_low_and_critical_battery)
{
    world_defaults_();
    board_up_(true);
    gl_sim_set_vbat_mv(3450); /* low (< 3500), not critical (>= 3350) */
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    watch_reset_();
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 9000));
    GL_CHECK(app.power.low && !app.power.critical);
    GL_CHECK(app.cur.flag_found);
    GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, 1u);

    world_defaults_();
    board_up_(true);
    gl_sim_set_vbat_mv(3300); /* critical */
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    watch_reset_();
    GL_CHECK(run_until_state_(GL_UI_LOW_BATT, 3000));
    GL_CHECK(gl_sim_lcd()->disp);
    GL_CHECK_EQ(panel_differs_from_framebuffer_(), 0u);
    GL_CHECK(run_until_state_(GL_UI_SLEEP, (uint32_t)(gl_sim_now_us() / 1000u) + 5000u));
    print_seen_();
    GL_CHECK(!gl_sim_lcd()->disp);
    GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, 0u); /* the cameras were never powered */
    GL_CHECK(cam_pins_parked_());
    /* in the cradle the same cell is no obstacle (and gets charged) */
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    run_until_ms_((uint32_t)(gl_sim_now_us() / 1000u) + 500u);
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_USB);
    GL_CHECK(!gl_sim_pin_drives_low(GL_PIN_CHG_INHIBIT));
    GL_CHECK(gl_sim_charger_on() && app.power.charge_enabled);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* A wake-up interrupt right after the device has gone to sleep (the IMU's
 * slope detector may trip on its own mode change) must not wake it. */
static void int1_pulse_(void *arg)
{
    (void)arg;
    gl_sim_set_input(GL_PIN_IMU_INT1, true);
    gl_sim_set_input(GL_PIN_IMU_INT1, false);
}

static struct {
    uint8_t state;
    bool disp;
    uint32_t loops;
} snap_;

static void snapshot_(void *arg)
{
    (void)arg;
    snap_.state = app.ui.state;
    snap_.disp = gl_sim_lcd()->disp;
    snap_.loops = app.loops;
}

GL_TEST(test_spurious_wake_right_after_sleep_is_ignored)
{
    world_defaults_();
    W.t_pick_s = 1e9; /* nobody touches the marker */
    W.t_place_s = 1e9;
    board_up_(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    watch_reset_();
    /* the device sleeps in Stop mode, so the outside world acts at
     * scheduled simulated times: a wake-up pulse 50 ms after it went to
     * sleep, a look at it at 250 ms, a second pulse at 600 ms */
    GL_CHECK(gl_sim_at_ms(50, int1_pulse_, NULL));
    GL_CHECK(gl_sim_at_ms(250, snapshot_, NULL));
    GL_CHECK(gl_sim_at_ms(600, int1_pulse_, NULL));
    snap_.state = 0xFF;
    run_until_ms_(700);
    GL_CHECK_EQ(snap_.state, GL_UI_SLEEP); /* the early pulse did not wake it ... */
    GL_CHECK(!snap_.disp);
    GL_CHECK(snap_.loops >= 2u);           /* ... although the loop ran for it */
    GL_CHECK_EQ(app.ui.state, GL_UI_WAKE); /* the later one did */
    GL_CHECK(app.ui.state_since_ms >= 600u && app.ui.state_since_ms < 620u);
    GL_CHECK(gl_sim_lcd()->disp);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

int main(void)
{
    GL_RUN(test_complete_quick_read);
    GL_RUN(test_lrrl_timing_correction);
    GL_RUN(test_quick_read_with_dcmi_crop_windowing);
    GL_RUN(test_raw_strip_logging);
    GL_RUN(test_no_flagstick_falls_back);
    GL_RUN(test_bump_during_capture_aborts_and_rereads);
    GL_RUN(test_precision_read_spin_and_reread);
    GL_RUN(test_survey_second_drop);
    GL_RUN(test_zeroing_on_a_table_top);
    GL_RUN(test_cradle_usb_charging_and_dfu);
    GL_RUN(test_missing_devices_are_reported_not_fatal);
    GL_RUN(test_low_and_critical_battery);
    GL_RUN(test_spurious_wake_right_after_sleep_is_ignored);
    return gl_test_summary();
}
