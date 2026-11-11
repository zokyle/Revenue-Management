/*
 * test_e2e_faults.c - the whole firmware on the host simulator in the
 * situations the design review found it unprepared for.  Each test is a
 * regression test for one review finding and states what used to happen.
 *
 *   charge gate     IMU failed / silent / reset / disagreeing with the MCU's
 *                   own temperature sensor / stale: charging stops
 *   IMU supervision one bus error, an IMU absent at boot, a supply glitch,
 *                   a lost data-ready interrupt: the device recovers; a
 *                   dead IMU ends in a watchdog reset, not in a device that
 *                   sleeps for ever with the part left measuring
 *   Precision Read  marker turned again during the re-read
 *   cradle          fault + double tap in the cradle, VBUS removed outside
 *                   the cradle state, SET_CAL with trailing bytes, LOG_ERASE
 *                   interleaved with a log append, a nearly empty cell
 *   capture timing  L R R L sway cancellation and the capture time limit
 *                   with a realistic vision run time charged in the
 *                   simulator (computation used to take zero simulated time)
 *
 * The scaffolding (world model, board power-on, run helpers, USB host) is
 * shared with tests/test_e2e.c: tests/gl_e2e_world.h.
 */
#include "gl_e2e_world.h"

#include "lsm6dsv16x.h"

static uint32_t now_ms_(void)
{
    return (uint32_t)(gl_sim_now_us() / 1000u);
}

static bool charging_allowed_(void)
{
#if GL_PROV_CHG_PROG_LOW_ALLOWS_CHARGE
    return gl_sim_pin_drives_low(GL_PIN_CHG_PROG_EN);
#else
    return !gl_sim_pin_drives_low(GL_PIN_CHG_PROG_EN);
#endif
}

/* Marker with one completed read, then asleep. */
static void read_then_sleep_(void)
{
    world_defaults_();
    board_up_(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    watch_reset_();
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 12000));
    GL_CHECK(run_until_state_(GL_UI_SLEEP, now_ms_() + 60000u));
}

/* Marker booted and put into the cradle with a host. */
static void into_cradle_(void)
{
    world_defaults_();
    board_up_(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    watch_reset_();
    host_rx_len_ = 0;
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    gl_sim_usb_host_open(true);
    run_until_ms_(now_ms_() + 400u);
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_USB);
}

/* Pick the marker up and put it down `cycles` times, 20 s apart; returns
 * how often that woke the device. */
static unsigned pick_up_cycles_(unsigned cycles)
{
    unsigned wakes = 0;
    for (unsigned k = 0; k < cycles; k++) {
        const uint32_t t = now_ms_();
        W.t_pick_s = (double)t / 1000.0 + 1.0;
        W.t_place_s = W.t_pick_s + 0.8;
        while (now_ms_() < t + 20000u) {
            run_until_ms_(now_ms_() + 100u);
            if (app.ui.state != (uint8_t)GL_UI_SLEEP) {
                wakes++;
                break;
            }
        }
        /* let it finish whatever it started and go back to sleep */
        (void)run_until_state_(GL_UI_SLEEP, now_ms_() + 70000u);
    }
    return wakes;
}

/* ======================================================================= */
/* 1. the charge-temperature gate                                           */
/* ======================================================================= */

/* Review (critical): after one IMU bus error imu_ok stayed false for ever
 * and the gate ran on the last good temperature: a cell at 60 C was charged
 * ("temp_c=22.0 temp_valid=1 charge_enabled=1").  Now the failure is
 * transient (the IMU recovers), and while it is not recovered there is no
 * temperature and no charging. */
GL_TEST(test_charge_gate_after_an_imu_bus_error)
{
    read_then_sleep_();
    /* awake again, showing a result */
    W.t_pick_s = (double)now_ms_() / 1000.0 + 0.5;
    W.t_place_s = W.t_pick_s + 0.6;
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, now_ms_() + 12000u));
    gl_sim_spi_fail(GL_SPI_BUS_2, 1, GL_ERR_TIMEOUT); /* ESD hit, marginal contact, ... */
    run_until_ms_(now_ms_() + 50u);
    /* one failed transfer: recovered at once, silently, no error screen */
    GL_CHECK(app.imu_ok);
    GL_CHECK_EQ(app.imu_recoveries, 1u);
    GL_CHECK(app.ui.state != (uint8_t)GL_UI_ERROR);
    GL_CHECK(run_until_state_(GL_UI_SLEEP, now_ms_() + 60000u));

    /* left in a hot car, then put on the cradle */
    gl_sim_imu_set_temperature(60.0f);
    run_until_ms_(now_ms_() + 20000u);
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    gl_sim_set_input(GL_PIN_CHG_STAT, false);
    for (unsigned i = 0; i < 300u; i++) { /* 5 minutes, checked every second */
        run_until_ms_(now_ms_() + 1000u);
        GL_CHECK(!charging_allowed_());
        GL_CHECK(!app.power.charge_enabled);
    }
    printf("    one SPI error earlier, cell at 60 C on the cradle for 5 min: imu_ok=%d temp %.1f C "
           "(valid %d), charging allowed: %s\n", (int)app.imu_ok, (double)app.temp_c,
           (int)app.temp_valid, charging_allowed_() ? "YES" : "no");
    GL_CHECK_NEAR(app.temp_c, 60.0, 0.1);
    /* cooled down: charging resumes */
    gl_sim_imu_set_temperature(30.0f);
    run_until_ms_(now_ms_() + GL_APP_BATT_PERIOD_MS + 2000u);
    GL_CHECK(charging_allowed_());
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* Review (critical / major): a silent IMU (MISO reads 0xFF) decoded to
 * 24.996 C and counted as a valid temperature: "imu_ok=1 temp_valid=1
 * temp_c=24.996 charge_enabled=1" at a true 60 C. */
GL_TEST(test_charge_gate_with_a_silent_imu)
{
    into_cradle_();
    run_until_ms_(now_ms_() + GL_APP_BATT_PERIOD_MS + 1000u);
    GL_CHECK(charging_allowed_()); /* 22 C, healthy: charging */
    GL_CHECK(app.temp_valid);

    gl_sim_imu_set_present(false); /* dead part / open joint: every byte reads 0xFF */
    gl_sim_imu_set_temperature(60.0f);
    gl_sim_set_mcu_temperature(60.0f);
    /* the sample pump notices within a tenth of a second */
    run_until_ms_(now_ms_() + 300u);
    GL_CHECK(!app.imu_ok);
    GL_CHECK(!app.temp_valid);
    GL_CHECK(!charging_allowed_());
    for (unsigned i = 0; i < 120u; i++) {
        run_until_ms_(now_ms_() + 1000u);
        GL_CHECK(!charging_allowed_());
    }
    printf("    IMU silent in the cradle at a true 60 C: imu_ok=%d temp_valid=%d charging allowed: "
           "%s, error shown: %s\n", (int)app.imu_ok, (int)app.temp_valid,
           charging_allowed_() ? "YES" : "no", gl_status_name((gl_status_t)app.ui.error_code));
    /* the driver itself refuses the read */
    {
        float t = -1.0f;
        GL_CHECK_EQ(gl_imu_read_temperature(&app.imu, &t), GL_ERR_NOT_FOUND);
        GL_CHECK_NEAR(t, -1.0, 1e-9); /* not written */
    }
    /* in a USB session the device is not reset for it (the factory must be
     * able to talk to a unit with a dead IMU) */
    GL_CHECK(!app.wdg_hold);
    GL_CHECK_EQ(gl_sim_violations()->watchdog, 0u);

    /* the part comes back (it was a contact): the IMU is recovered and, at a
     * permitted temperature, charging resumes by itself */
    gl_sim_imu_set_present(true);
    gl_sim_imu_set_temperature(24.0f);
    gl_sim_set_mcu_temperature(26.0f);
    run_until_ms_(now_ms_() + GL_APP_IMU_RETRY_MAX_MS + GL_APP_BATT_PERIOD_MS + 2000u);
    GL_CHECK(app.imu_ok);
    GL_CHECK(charging_allowed_());
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* The other ways the temperature can be wrong or missing. */
GL_TEST(test_charge_gate_second_opinion_and_staleness)
{
    into_cradle_();
    run_until_ms_(now_ms_() + GL_APP_BATT_PERIOD_MS + 1000u);
    GL_CHECK(charging_allowed_());

    /* the IMU's sensor reads 25 C while the board is at 50 C (a stuck or
     * offset sensor): the MCU's own sensor disagrees -> stop */
    gl_sim_set_mcu_temperature(50.0f);
    run_until_ms_(now_ms_() + GL_APP_BATT_PERIOD_MS + 1000u);
    GL_CHECK(!charging_allowed_());
    printf("    IMU says %.1f C, MCU die sensor says %.1f C: charging allowed: %s\n",
           (double)app.temp_c, (double)app.power.mcu_temp_c, charging_allowed_() ? "YES" : "no");
    /* they agree within the limit, but the hotter one is above 45 C -> stop */
    gl_sim_imu_set_temperature(40.0f);
    gl_sim_set_mcu_temperature(46.5f);
    run_until_ms_(now_ms_() + GL_APP_BATT_PERIOD_MS + 1000u);
    GL_CHECK(!charging_allowed_());
    /* both inside, in agreement: on again (inside the hysteresis) */
    gl_sim_imu_set_temperature(30.0f);
    gl_sim_set_mcu_temperature(32.0f);
    run_until_ms_(now_ms_() + GL_APP_BATT_PERIOD_MS + 1000u);
    GL_CHECK(charging_allowed_());

    /* a supply glitch resets the IMU alone: it answers, but both sensors
     * are off and its temperature output is frozen.  The sample pump sees
     * the silence and re-initialises it; meanwhile no charging on a
     * temperature that is not being measured */
    {
        const uint32_t rec = app.imu_recoveries;
        gl_sim_imu_power_glitch();
        run_until_ms_(now_ms_() + 60u);
        GL_CHECK(!charging_allowed_() || app.imu_recoveries == rec + 1u);
        run_until_ms_(now_ms_() + 400u);
        GL_CHECK_EQ(app.imu_recoveries, rec + 1u);
        GL_CHECK(app.imu_ok);
        GL_CHECK_EQ(gl_sim_imu_reg(0x10), 0x07); /* measuring again */
    }
    run_until_ms_(now_ms_() + GL_APP_BATT_PERIOD_MS + 1000u);
    GL_CHECK(charging_allowed_());

    /* an IMU in power-down is not a thermometer (driver level) */
    {
        float t = 0.0f;
        GL_CHECK_EQ(gl_imu_read_temperature(&app.imu, &t), GL_OK);
        GL_CHECK_EQ(gl_imu_stop(&app.imu), GL_OK);
        GL_CHECK_EQ(gl_imu_read_temperature(&app.imu, &t), GL_ERR_STATE);
        GL_CHECK_EQ(gl_imu_start_measure(&app.imu), GL_OK);
        /* exactly 25.000 C is what a silent bus or a frozen output reads as */
        gl_sim_imu_set_temperature(25.0f);
        GL_CHECK_EQ(gl_imu_read_temperature(&app.imu, &t), GL_ERR_QUALITY);
        gl_sim_imu_set_temperature(25.01f);
        GL_CHECK_EQ(gl_imu_read_temperature(&app.imu, &t), GL_OK);
        gl_sim_imu_set_temperature(30.0f);
    }

    /* staleness: if the periodic temperature read stops happening the gate
     * must not live on the old value.  (Simulated by ageing the time stamp:
     * the gate is evaluated on a VBUS / STAT edge.) */
    run_until_ms_(now_ms_() + GL_APP_BATT_PERIOD_MS + 1000u);
    GL_CHECK(charging_allowed_());
    app.temp_ms -= GL_APP_TEMP_MAX_AGE_MS + 1000u;
    gl_sim_set_input(GL_PIN_CHG_STAT, false);
    run_until_ms_(now_ms_() + GL_APP_VBUS_DEBOUNCE_MS + 20u);
    GL_CHECK(!charging_allowed_());
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* ======================================================================= */
/* 2. IMU supervision                                                       */
/* ======================================================================= */

/* Review (major): one SPI2 transfer returning GL_ERR_TIMEOUT -> ERROR ->
 * SLEEP, then "15 pick-up / put-down cycles over 480 s: woke 0 times;
 * imu_ok=0" with CTRL1 = CTRL2 = 0x07 (240 Hz, gyro on) while "asleep". */
GL_TEST(test_one_imu_bus_error_is_not_permanent)
{
    unsigned wakes;
    world_defaults_();
    board_up_(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    watch_reset_();
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 12000));
    GL_CHECK(app.imu_ok);

    gl_sim_spi_fail(GL_SPI_BUS_2, 1, GL_ERR_TIMEOUT);
    run_until_ms_(now_ms_() + 50u);
    printf("    after one failed SPI2 transfer: imu_ok=%d, state %s, recoveries %u\n", (int)app.imu_ok,
           gl_ui_state_name((gl_ui_state_t)app.ui.state), (unsigned)app.imu_recoveries);
    GL_CHECK(app.imu_ok);
    GL_CHECK_EQ(app.ui.state, GL_UI_SHOW_RESULT); /* not even an error screen */
    GL_CHECK(run_until_state_(GL_UI_SLEEP, now_ms_() + 60000u));
    /* asleep: wake-on-motion configured, gyro off */
    GL_CHECK_EQ(gl_sim_imu_reg(0x10), 0x43);
    GL_CHECK_EQ(gl_sim_imu_reg(0x11), 0x00);
    GL_CHECK_EQ(gl_sim_imu_reg(0x5E), 0x20);

    wakes = pick_up_cycles_(15);
    printf("    15 pick-up / put-down cycles afterwards: woke %u times\n", wakes);
    GL_CHECK_EQ(wakes, 15u);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);

    /* a burst that outlasts the immediate retry: error shown, retried with
     * back-off, recovered */
    W.t_pick_s = (double)now_ms_() / 1000.0 + 0.5;
    W.t_place_s = W.t_pick_s + 0.6;
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, now_ms_() + 12000u));
    gl_sim_spi_fail(GL_SPI_BUS_2, 5, GL_ERR_IO); /* outlasts the first two attempts */
    run_until_ms_(now_ms_() + 50u);
    GL_CHECK(!app.imu_ok);
    GL_CHECK_EQ(app.ui.state, GL_UI_ERROR);
    run_until_ms_(now_ms_() + 4500u);
    GL_CHECK(app.imu_ok); /* the retries at 1 s and 2 s later got through */
    GL_CHECK(run_until_state_(GL_UI_SLEEP, now_ms_() + 60000u));
    GL_CHECK_EQ(pick_up_cycles_(3), 3u);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* Review (major): "IMU not answering only during gl_app_init(), present
 * afterwards: 6 pick-up cycles, 0 wakes". */
GL_TEST(test_imu_absent_at_boot_only)
{
    unsigned wakes;
    world_defaults_();
    board_up_(true);
    gl_sim_imu_set_present(false);
    GL_CHECK_EQ(gl_app_init(&app), GL_ERR_NOT_FOUND);
    gl_sim_imu_set_present(true);
    watch_reset_();
    GL_CHECK(!app.imu_ok);
    run_until_ms_(now_ms_() + 30000u); /* error screen, sleep, first housekeeping wake-up */
    GL_CHECK(app.imu_ok);
    GL_CHECK_EQ(gl_sim_imu_reg(0x5E), 0x20); /* wake-up routed to INT1 */
    wakes = pick_up_cycles_(6);
    printf("    IMU absent only during gl_app_init(): 6 pick-up cycles afterwards woke the device "
           "%u times\n", wakes);
    GL_CHECK_EQ(wakes, 6u);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* A supply glitch resets the IMU while the device sleeps: it answers but
 * has lost its wake-up configuration.  The 16 s housekeeping check finds
 * and repairs it. */
GL_TEST(test_imu_reset_while_asleep_is_repaired)
{
    read_then_sleep_();
    gl_sim_imu_power_glitch();
    GL_CHECK_EQ(gl_sim_imu_reg(0x5E), 0x00);
    run_until_ms_(now_ms_() + 2u * GL_APP_SLEEP_HOUSEKEEP_MS + 1000u);
    GL_CHECK(app.imu_ok);
    GL_CHECK_EQ(gl_sim_imu_reg(0x10), 0x43);
    GL_CHECK_EQ(gl_sim_imu_reg(0x5E), 0x20);
    GL_CHECK_EQ(app.ui.state, GL_UI_SLEEP); /* without waking the display */
    GL_CHECK_EQ(pick_up_cycles_(2), 2u);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* An IMU that never answers again.  The device must not sit there for ever
 * with a part that may still be measuring: it asks the part to stop at
 * every failed attempt and, after GL_APP_IMU_MAX_FAILS attempts, stops
 * refreshing the watchdog so that a clean reset re-initialises the bus. */
GL_TEST(test_dead_imu_ends_in_a_watchdog_reset)
{
    uint32_t t_dead;
    read_then_sleep_();
    gl_sim_imu_set_present(false);
    t_dead = now_ms_();
    /* found at the next housekeeping check (16 s at most); the error is
     * shown, the retries back off */
    run_until_ms_(t_dead + GL_APP_SLEEP_HOUSEKEEP_MS + 2000u);
    GL_CHECK(!app.imu_ok);
    GL_CHECK(app.imu_fault_shown);
    GL_CHECK_EQ(gl_sim_violations()->watchdog, 0u); /* not yet */
    while (!app.wdg_hold && now_ms_() < t_dead + 400000u) {
        run_until_ms_(now_ms_() + 1000u);
    }
    GL_CHECK(app.wdg_hold);
    GL_CHECK(app.imu_fails >= GL_APP_IMU_MAX_FAILS);
    GL_CHECK_EQ(gl_sim_violations()->watchdog, 0u); /* still not */
    run_until_ms_(now_ms_() + 50000u);
    printf("    IMU dead while asleep: %u failed recoveries, then the watchdog is left to expire: "
           "simulator reports %u watchdog expiry (a reset on the target)\n",
           (unsigned)app.imu_fails, gl_sim_violations()->watchdog);
    GL_CHECK(gl_sim_violations()->watchdog >= 1u);
    /* nothing else went wrong on the way */
    GL_CHECK_EQ(gl_sim_violation_total(), gl_sim_violations()->watchdog);
}

/* Review (major, two reviewers): the sample pump was purely edge driven.
 * With the part's latched data-ready (INT2 stays high until the output is
 * read) one lost interrupt latch meant no further edge: "no IMU sample for
 * 36 s; the marker sits in WAIT_STILL until its time-out and goes to sleep
 * without a read".  The simulator now models latched data-ready and can
 * drop a latch; the application polls when the interrupt stays away. */
GL_TEST(test_a_lost_data_ready_interrupt_does_not_stall)
{
    unsigned dropped = 0;
    uint32_t longest_gap_ms = 0, last = 0;
    world_defaults_();
    board_up_(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    watch_reset_();
    GL_CHECK_EQ(GL_PROV_IMU_DRDY_PULSED, 0);
    GL_CHECK(run_until_state_(GL_UI_WAIT_STILL, 5000));
    GL_CHECK_EQ(gl_sim_imu_reg(0x13) & 0x02u, 0u); /* CTRL4: latched data-ready */

    /* the latched line really behaves as the finding says: high until read */
    last = app.last_sample_ms;
    for (unsigned i = 0; i < 4000u && app.ui.state != (uint8_t)GL_UI_SHOW_RESULT; i++) {
        gl_app_run_once(&app); /* returns from its sleep with the wake cause pending */
        if (dropped < 25u && (i % 40u) == 20u && gl_hal_gpio_read(GL_PIN_IMU_INT2)) {
            gl_sim_irq_drop(GL_IRQ_IMU_INT2); /* the latch is lost; the line stays high */
            dropped++;
        }
        if (app.last_sample_ms != last) {
            /* (the camera part blocks the loop for the sensors' settle time
             * by design: gaps are measured while waiting and reading tilt) */
            if (app.last_sample_ms - last > longest_gap_ms &&
                (app.ui.state == (uint8_t)GL_UI_WAIT_STILL ||
                 app.ui.state == (uint8_t)GL_UI_READ_TILT)) {
                longest_gap_ms = app.last_sample_ms - last;
            }
            last = app.last_sample_ms;
        }
    }
    printf("    %u data-ready latches dropped during a read: longest time without a sample %u ms, "
           "%u samples fetched by polling, state %s\n", dropped, (unsigned)longest_gap_ms,
           (unsigned)app.imu_polls, gl_ui_state_name((gl_ui_state_t)app.ui.state));
    GL_CHECK(dropped >= 10u);
    GL_CHECK(app.imu_polls >= dropped);
    GL_CHECK(longest_gap_ms <= 2u * GL_APP_IMU_STALL_MS + 5u);
    GL_CHECK_EQ(app.ui.state, GL_UI_SHOW_RESULT); /* the read went through */
    GL_CHECK_NEAR(app.cur.slope.x, W.slope_x, 2e-4);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* ======================================================================= */
/* 3. Precision Read: the marker is turned again during the re-read         */
/* ======================================================================= */

static double turn2_at_s_, turn2_len_s_, turn2_rad_;

static double heading2_(double t)
{
    double f;
    if (turn2_len_s_ <= 0.0 || t <= turn2_at_s_) {
        return 0.0;
    }
    if (t >= turn2_at_s_ + turn2_len_s_) {
        return turn2_rad_;
    }
    f = (t - turn2_at_s_) / turn2_len_s_;
    return turn2_rad_ * 0.5 * (1.0 - cos(PI_D * f));
}

static double heading2_rate_(double t)
{
    double f;
    if (turn2_len_s_ <= 0.0 || t <= turn2_at_s_ || t >= turn2_at_s_ + turn2_len_s_) {
        return 0.0;
    }
    f = (t - turn2_at_s_) / turn2_len_s_;
    return turn2_rad_ * 0.5 * PI_D / turn2_len_s_ * sin(PI_D * f);
}

/* imu_fn_ of the scaffold with a second turn about the vertical added */
static void imu_fn2_(void *ctx, uint64_t t_us, float a[3], float g[3])
{
    const double t = (double)t_us * 1e-6;
    const double psi = heading_(t) + heading2_(t);
    const double cx = cos(psi) * W.slope_x + sin(psi) * W.slope_y;
    const double cy = -sin(psi) * W.slope_x + cos(psi) * W.slope_y;
    const gl_vec3_t u = up_of_(cx, cy);
    const double rate = heading_rate_(t) + heading2_rate_(t);
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

/* Spin by `spin_deg`, then `extra_deg` more starting 0.3 s into the
 * re-read.  Returns the slope error of what is shown, in percent of slope. */
static double precision_with_second_turn_(double spin_deg, double extra_deg)
{
    double t_now;
    world_defaults_();
    board_up_(true);
    turn2_len_s_ = 0.0;
    gl_sim_imu_set_motion(imu_fn2_, NULL);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    watch_reset_();
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 12000));
    gl_app_post(&app, GL_EV_DOUBLE_TAP, 0);
    run_until_ms_(now_ms_() + 300u);
    GL_CHECK_EQ(app.ui.state, GL_UI_PRECISION_WAIT_SPIN);
    t_now = (double)gl_sim_now_us() * 1e-6;
    W.turn_at_s = t_now + 0.5;
    W.turn_len_s = 1.2;
    W.turn_rad = spin_deg * PI_D / 180.0;
    GL_CHECK(run_until_state_(GL_UI_READ_TILT, (uint32_t)(t_now * 1000.0) + 5000u));
    GL_CHECK_EQ(app.ui.read_kind, GL_READ_PRECISION);
    t_now = (double)gl_sim_now_us() * 1e-6;
    turn2_at_s_ = t_now + 0.3;
    turn2_len_s_ = 0.6;
    turn2_rad_ = extra_deg * PI_D / 180.0;
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, (uint32_t)(t_now * 1000.0) + 30000u));
    return 100.0 * sqrt(pow((double)app.cur.slope.x - W.slope_x, 2.0) +
                        pow((double)app.cur.slope.y - W.slope_y, 2.0));
}

/* Review (major): "marker turned 176 + 40 = 216 deg in all; firmware used
 * yaw 176.0 deg; shown as Precision: YES", combined slope off by 0.80 % of
 * slope on a 2.33 % slope. */
GL_TEST(test_precision_reread_with_a_second_turn)
{
    double err;
    /* 176 + 40 = 216 degrees: not a half turn any more.  The re-read is
     * abandoned, the single read stays, drawn for where the marker faces */
    err = precision_with_second_turn_(176.0, 40.0);
    print_seen_();
    printf("    turned 176 + 40 = 216 deg: yaw used %.1f deg, shown as Precision: %s, slope error "
           "%.3f %% of slope\n", (double)app.cur.view_yaw_rad * 57.29578,
           app.view.precision ? "YES" : "no", err);
    GL_CHECK(!app.view.precision);
    GL_CHECK(!app.cur.precision);
    GL_CHECK(err < 0.05); /* the single read: (1.200, -2.007) % */
    /* the yaw the screen is drawn with is the marker's real heading
     * (216 degrees = -144 degrees), not the stale 176 */
    GL_CHECK_NEAR(fabs((double)app.cur.view_yaw_rad) * 57.29578, 144.0, 1.5);
    GL_CHECK_NEAR(fabs((double)app.view.ball_az_rad) * 57.29578, 144.0, 1.5);
    GL_CHECK(!app.motion.spin_active);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);

    /* 170 + 12 = 182 degrees: still a half turn.  The re-read is repeated at
     * the new rest position and combined with the angle it was taken at */
    err = precision_with_second_turn_(170.0, 12.0);
    print_seen_();
    printf("    turned 170 + 12 = 182 deg: yaw used %.1f deg, shown as Precision: %s, slope error "
           "%.3f %% of slope\n", (double)app.cur.view_yaw_rad * 57.29578,
           app.view.precision ? "YES" : "no", err);
    GL_CHECK(app.view.precision);
    GL_CHECK_NEAR(fabs((double)app.cur.view_yaw_rad) * 57.29578, 178.0, 0.6); /* 182 = -178 */
    GL_CHECK(err < 0.05);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);

    /* undisturbed, for comparison */
    err = precision_with_second_turn_(176.0, 0.0);
    GL_CHECK(app.view.precision);
    GL_CHECK_NEAR((double)app.cur.view_yaw_rad * 57.29578, 176.0, 0.6);
    GL_CHECK(err < 0.05);
}

/* ======================================================================= */
/* 4. the cradle                                                            */
/* ======================================================================= */

/* Review (minor, hw-interface): a fault in the cradle followed by a double
 * tap took the UI out of CRADLE_USB with VBUS present.  Scenario A: the
 * marker lifted out then: "USB stays started for 47.2 s without VBUS".
 * Scenario B: the marker left in: asleep with the charge enable still on,
 * "charging is still enabled 10 minutes later" at 60 C. */
GL_TEST(test_fault_and_double_tap_in_the_cradle)
{
    /* A */
    into_cradle_();
    run_until_ms_(now_ms_() + GL_APP_BATT_PERIOD_MS + 500u);
    GL_CHECK(charging_allowed_());
    gl_app_post(&app, GL_EV_FAULT, (int32_t)GL_ERR_IO);
    run_until_ms_(now_ms_() + 100u);
    GL_CHECK_EQ(app.ui.state, GL_UI_ERROR);
    gl_app_post(&app, GL_EV_DOUBLE_TAP, 0);
    run_until_ms_(now_ms_() + 100u);
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_USB); /* not a read */
    GL_CHECK(app.usb_on);
    gl_sim_set_input(GL_PIN_VBUS_SENSE, false); /* lifted out */
    gl_sim_usb_host_open(false);
    gl_app_run_once(&app);
    GL_CHECK(!app.usb_on); /* stopped in the very next loop pass, before it sleeps */
    printf("    A: lifted out of the cradle: USB stopped in the next main-loop pass (it used to "
           "stay started for 47 s)\n");
    run_until_ms_(now_ms_() + 300u);
    GL_CHECK_EQ(app.ui.state, GL_UI_SLEEP);
    GL_CHECK(!charging_allowed_());
    GL_CHECK_EQ(gl_sim_violation_total(), 0);

    /* the hardware rule holds even if the UI is somewhere else: force the
     * UI into a read state with VBUS present, then remove VBUS */
    into_cradle_();
    app.ui.state = (uint8_t)GL_UI_WAIT_STILL; /* what the old table could reach */
    gl_sim_set_input(GL_PIN_VBUS_SENSE, false);
    gl_sim_usb_host_open(false);
    gl_app_run_once(&app);
    GL_CHECK(!app.usb_on); /* stopped below the UI, in the same loop pass */
    run_until_ms_(now_ms_() + 300u);
    GL_CHECK_EQ(app.ui.state, GL_UI_SLEEP);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);

    /* B: the marker stays in the cradle; whatever the UI does, it ends up
     * back in the cradle state with the gate supervised */
    into_cradle_();
    gl_app_post(&app, GL_EV_FAULT, (int32_t)GL_ERR_IO);
    run_until_ms_(now_ms_() + 100u);
    gl_app_post(&app, GL_EV_DOUBLE_TAP, 0);
    run_until_ms_(now_ms_() + 100u);
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_USB);
    /* even a UI that reaches SLEEP with VBUS present does not stay there */
    app.ui.state = (uint8_t)GL_UI_LOW_BATT;
    app.ui.state_since_ms = now_ms_();
    run_until_ms_(now_ms_() + 6000u);
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_USB);
    GL_CHECK(app.awake && app.usb_on);
    gl_sim_imu_set_temperature(60.0f);
    run_until_ms_(now_ms_() + 10u * 60u * 1000u);
    printf("    B: 10 min in the cradle at 60 C after fault + double tap: state %s, charging "
           "allowed: %s\n", gl_ui_state_name((gl_ui_state_t)app.ui.state),
           charging_allowed_() ? "YES" : "no");
    GL_CHECK(!charging_allowed_());
    GL_CHECK_EQ(gl_sim_violations()->power, 0u);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* Spring-pin bounce: VBUS toggles a few times within the debounce time.
 * USB is stopped at the first low and the UI is not thrown about. */
GL_TEST(test_vbus_bounce)
{
    uint32_t transitions;
    into_cradle_();
    transitions = app.ui.transitions;
    for (unsigned i = 0; i < 4u; i++) {
        gl_sim_set_input(GL_PIN_VBUS_SENSE, false);
        run_until_ms_(now_ms_() + 3u);
        GL_CHECK(!app.usb_on);
        gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
        run_until_ms_(now_ms_() + 4u);
    }
    run_until_ms_(now_ms_() + 200u);
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_USB);
    GL_CHECK_EQ(app.ui.transitions, transitions); /* the UI never heard of it */
    GL_CHECK(app.usb_on);                         /* and USB is back */
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* The simulator's new rules do fire (a rule that cannot fail proves nothing). */
GL_TEST(test_the_power_rules_of_the_simulator_fire)
{
    gl_power_t p;
    gl_sim_reset(true);
    GL_CHECK_EQ(gl_hal_init(), GL_OK);
    gl_power_init(&p);
    gl_hal_irq_enable(GL_IRQ_WAKE_TIMER, true);
    /* USB started with VBUS absent, at a sleep */
    GL_CHECK_EQ(gl_hal_usb_start(), GL_OK);
    gl_hal_wake_timer_start(5);
    (void)gl_hal_sleep(GL_SLEEP_IDLE);
    GL_CHECK_EQ(gl_sim_violations()->power, 1u);
    gl_hal_usb_stop();
    (void)gl_hal_irq_take();
    /* charger enabled at the entry of Stop mode */
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    gl_power_poll_pins(&p);
    GL_CHECK(gl_power_charge_gate(&p, 25.0f, 25.0f, true));
    gl_hal_wake_timer_start(5);
    (void)gl_hal_sleep(GL_SLEEP_STOP);
    GL_CHECK_EQ(gl_sim_violations()->power, 2u);
    (void)gl_hal_irq_take();
    gl_power_charge_stop(&p);
    gl_hal_wake_timer_start(5);
    (void)gl_hal_sleep(GL_SLEEP_STOP);
    GL_CHECK_EQ(gl_sim_violations()->power, 2u);
}

/* Review (minor): SET_CAL with trailing bytes: "response status 1 (PARAM);
 * fx in RAM 657 -> 700; model fx 700", nothing stored. */
GL_TEST(test_set_cal_that_fails_changes_nothing)
{
    uint8_t seq;
    const uint8_t *pl;
    uint8_t req[1 + 200];
    gl_cal_cam_t c;
    const uint8_t *d;
    size_t len;
    float fx_before;
    int n;

    into_cradle_();
    host_send_(1, GL_CMD_UNLOCK, "GLFC", 4);
    (void)host_get_(GL_CMD_UNLOCK | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
    fx_before = app.cal_cam[GL_CAM_LEFT].fx_px;
    gl_cal_cam_defaults(&c, 0);
    c.fx_px = 700.0f;
    memset(req, 0, sizeof(req));
    req[0] = (uint8_t)GL_CAL_ID_CAM_L;
    gl_cal_cam_encode(&c, &req[1]);
    /* a valid record followed by padding */
    host_send_(2, GL_CMD_SET_CAL, req, sizeof(req));
    n = host_get_(GL_CMD_SET_CAL | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
    GL_CHECK(n >= 1 && pl[0] == GL_ERR_PARAM);
    GL_CHECK_NEAR(app.cal_cam[GL_CAM_LEFT].fx_px, fx_before, 1e-6);
    GL_CHECK_NEAR(app.read.model[GL_CAM_LEFT].fx, fx_before, 1e-6);
    GL_CHECK_EQ(gl_store_get(&app.store, (uint8_t)GL_STORE_ID_CAL_CAM_L, &d, &len), GL_ERR_NOT_FOUND);
    /* one byte too many, one too few */
    host_send_(3, GL_CMD_SET_CAL, req, 1u + GL_CAL_CAM_BLOB_LEN + 1u);
    n = host_get_(GL_CMD_SET_CAL | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
    GL_CHECK(n >= 1 && pl[0] == GL_ERR_PARAM);
    host_send_(4, GL_CMD_SET_CAL, req, GL_CAL_CAM_BLOB_LEN);
    n = host_get_(GL_CMD_SET_CAL | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
    GL_CHECK(n >= 1 && pl[0] == GL_ERR_PARAM);
    GL_CHECK_NEAR(app.cal_cam[GL_CAM_LEFT].fx_px, fx_before, 1e-6);
    /* a record that does not validate */
    {
        uint8_t bad[1 + GL_CAL_CAM_BLOB_LEN];
        memcpy(bad, req, sizeof(bad));
        bad[1] ^= 0x7Fu; /* the version byte */
        host_send_(5, GL_CMD_SET_CAL, bad, sizeof(bad));
        n = host_get_(GL_CMD_SET_CAL | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
        GL_CHECK(n >= 1 && pl[0] != GL_OK);
        GL_CHECK_NEAR(app.cal_cam[GL_CAM_LEFT].fx_px, fx_before, 1e-6);
    }
    /* the exact record: stored, then adopted, RAM and flash agree */
    host_send_(6, GL_CMD_SET_CAL, req, 1u + GL_CAL_CAM_BLOB_LEN);
    n = host_get_(GL_CMD_SET_CAL | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
    GL_CHECK(n >= 1 && pl[0] == GL_OK);
    GL_CHECK_NEAR(app.cal_cam[GL_CAM_LEFT].fx_px, 700.0, 1e-4);
    GL_CHECK_NEAR(app.read.model[GL_CAM_LEFT].fx, 700.0, 1e-4);
    GL_CHECK_EQ(gl_store_get(&app.store, (uint8_t)GL_STORE_ID_CAL_CAM_L, &d, &len), GL_OK);
    GL_CHECK_EQ(len, GL_CAL_CAM_BLOB_LEN);
    GL_CHECK_MEM(d, &req[1], GL_CAL_CAM_BLOB_LEN);
    printf("    SET_CAL with trailing bytes: PARAM, fx in RAM unchanged (%.0f), nothing stored; the "
           "exact record: stored and adopted (fx %.0f)\n", (double)fx_before,
           (double)app.cal_cam[GL_CAM_LEFT].fx_px);
    /* a store that fails: RAM keeps the old value */
    app.storage_ok = false;
    c.fx_px = 640.0f;
    gl_cal_cam_encode(&c, &req[1]);
    host_send_(7, GL_CMD_SET_CAL, req, 1u + GL_CAL_CAM_BLOB_LEN);
    n = host_get_(GL_CMD_SET_CAL | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
    GL_CHECK(n >= 1 && pl[0] != GL_OK);
    GL_CHECK_NEAR(app.cal_cam[GL_CAM_LEFT].fx_px, 700.0, 1e-4);
    app.storage_ok = true;
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

static unsigned count_log_(unsigned *n_filler, unsigned *n_events)
{
    gl_log_iter_t it;
    gl_log_rec_t rec;
    unsigned n = 0;
    *n_filler = 0;
    *n_events = 0;
    gl_log_iter_begin(&app.log, &it);
    while (gl_log_iter_next(&app.log, &it, &rec, NULL, 0) == GL_OK) {
        n++;
        if (rec.type == 0x7Fu) {
            (*n_filler)++;
        }
        if (rec.type == (uint8_t)GL_LOG_REC_EVENT) {
            (*n_events)++;
        }
    }
    return n;
}

/* Review (major): UNLOCK, LOG_ERASE, START_CAL(GRAIN_WHITE) while erasing
 * with the head sector full: "the erase finishes with 0 records; after a
 * reset 102 'erased' field records are back". */
GL_TEST(test_log_erase_with_an_event_in_between)
{
    uint8_t seq;
    const uint8_t *pl;
    uint8_t filler[24];
    const uint8_t white[2] = { GL_CALPROC_GRAIN_WHITE, 0 };
    unsigned nf, ne, n, guard = 0;

    into_cradle_();
    /* field data in the log: about six sectors, the head sector full */
    memset(filler, 0x5A, sizeof(filler));
    while (app.log.head_sector < 6u || gl_log_head_free(&app.log) >= 28u) {
        GL_CHECK_EQ(gl_log_append(&app.log, 0x7F, 0, filler, sizeof(filler), NULL), GL_OK);
        if (++guard > 5000u) {
            break;
        }
    }
    n = count_log_(&nf, &ne);
    GL_CHECK(nf > 500u);
    host_send_(1, GL_CMD_UNLOCK, "GLFC", 4);
    (void)host_get_(GL_CMD_UNLOCK | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
    host_send_(2, GL_CMD_LOG_ERASE, "ERAS", 4);
    (void)host_get_(GL_CMD_LOG_ERASE | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
    GL_CHECK_EQ(pl[0], GL_OK);
    GL_CHECK(app.log_erasing);
    /* the factory script goes on with the next step while the erase runs:
     * the procedure works, its log event is not written into the middle of
     * the erase */
    host_send_(3, GL_CMD_START_CAL, white, 2);
    (void)host_get_(GL_CMD_START_CAL | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
    GL_CHECK(app.log_erasing); /* it arrived in the middle of the erase */
    guard = 0;
    while (app.log_erasing && ++guard < 5000u) {
        run_until_ms_(now_ms_() + 20u);
    }
    GL_CHECK(!app.log_erasing);
    n = count_log_(&nf, &ne);
    GL_CHECK_EQ(n, 0u);
    for (uint8_t k = 0; k < 3u; k++) {
        host_send_((uint8_t)(10u + k), GL_CMD_START_CAL, white, 2);
        (void)host_get_(GL_CMD_START_CAL | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
    }
    n = count_log_(&nf, &ne);
    GL_CHECK_EQ(nf, 0u);
    GL_CHECK_EQ(ne, 3u);
    /* reset: flash contents kept */
    gl_sim_reset(false);
    gl_sim_imu_set_motion(imu_fn_, NULL);
    gl_sim_cam_set_scene(scene_fn_, NULL);
    gl_sim_set_vbat_mv(3900);
    (void)gl_app_init(&app);
    n = count_log_(&nf, &ne);
    printf("    LOG_ERASE with a calibration event in between, then a reset: %u 'erased' records "
           "back, %u event records (3 after the erase + 1 boot)\n", nf, ne);
    GL_CHECK_EQ(nf, 0u); /* erased data stays erased */
    GL_CHECK_EQ(ne, 4u); /* the records acknowledged after the erase are there */

    /* the marker is lifted out in the middle of an erase: the erase is
     * given up cleanly and the log works */
    into_cradle_();
    guard = 0;
    while (app.log.head_sector < 6u && ++guard < 5000u) {
        (void)gl_log_append(&app.log, 0x7F, 0, filler, sizeof(filler), NULL);
    }
    host_send_(1, GL_CMD_UNLOCK, "GLFC", 4);
    (void)host_get_(GL_CMD_UNLOCK | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
    host_send_(2, GL_CMD_LOG_ERASE, "ERAS", 4);
    (void)host_get_(GL_CMD_LOG_ERASE | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
    GL_CHECK(app.log_erasing);
    gl_sim_set_input(GL_PIN_VBUS_SENSE, false);
    gl_sim_usb_host_open(false);
    run_until_ms_(now_ms_() + 300u);
    GL_CHECK(!app.log_erasing && !app.log.erasing);
    GL_CHECK_EQ(gl_log_append(&app.log, 0x7F, 0, filler, sizeof(filler), NULL), GL_OK);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* Review (major, design level): the rev C charger is off whenever the MCU
 * is unpowered, so a cell that reaches its protection cut-off cannot be
 * recharged.  The firmware part of the answer: below the storage threshold
 * it stops everything it can - the IMU is powered down, motion no longer
 * wakes the device - and waits for the cradle. */
GL_TEST(test_storage_mode_for_a_nearly_empty_cell)
{
    unsigned wakes;
    read_then_sleep_();
    GL_CHECK(!app.storage_mode);
    /* the cell sags below the storage threshold while the device sleeps */
    gl_sim_set_vbat_mv((uint16_t)(GL_PROV_BATT_STORAGE_MV - 60u));
    run_until_ms_(now_ms_() + (GL_APP_SLEEP_BATT_EVERY + 1u) * GL_APP_SLEEP_HOUSEKEEP_MS);
    GL_CHECK(app.storage_mode);
    GL_CHECK_EQ(gl_sim_imu_reg(0x10), 0x00); /* accelerometer off */
    GL_CHECK_EQ(gl_sim_imu_reg(0x11), 0x00);
    GL_CHECK_EQ(gl_sim_imu_reg(0x5E), 0x00);
    GL_CHECK(gl_sim_flash_stats()->deep_power_down);
    wakes = pick_up_cycles_(2);
    GL_CHECK_EQ(wakes, 0u); /* motion does not wake it any more */
    {
        const uint64_t stop0 = gl_sim_stats()->stop_us, t0 = gl_sim_now_us();
        run_until_ms_(now_ms_() + 120000u);
        printf("    storage mode at %u mV: IMU off, motion ignored, MCU in Stop mode %.2f %% of the "
               "time\n", (unsigned)app.power.batt_mv,
               100.0 * (double)(gl_sim_stats()->stop_us - stop0) / (double)(gl_sim_now_us() - t0));
        GL_CHECK((double)(gl_sim_stats()->stop_us - stop0) > 0.999 * (double)(gl_sim_now_us() - t0));
    }
    /* the cradle wakes it and it charges */
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    run_until_ms_(now_ms_() + GL_APP_BATT_PERIOD_MS + 1000u);
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_USB);
    GL_CHECK(!app.storage_mode);
    GL_CHECK(app.imu_ok);
    GL_CHECK(charging_allowed_());
    /* charged and lifted out: an ordinary sleep again */
    gl_sim_set_vbat_mv(3900);
    run_until_ms_(now_ms_() + GL_APP_BATT_PERIOD_MS + 1000u);
    gl_sim_set_input(GL_PIN_VBUS_SENSE, false);
    run_until_ms_(now_ms_() + 500u);
    GL_CHECK_EQ(app.ui.state, GL_UI_SLEEP);
    GL_CHECK(!app.storage_mode);
    GL_CHECK_EQ(gl_sim_imu_reg(0x5E), 0x20);
    GL_CHECK_EQ(pick_up_cycles_(1), 1u);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* ======================================================================= */
/* 5. capture timing with a realistic vision run time                       */
/* ======================================================================= */

/* One read of a stick drifting at 6 px/s with `strip_ms` of computation
 * charged per analysed strip (and 8 x that for the band).  Returns the
 * disparity error in px, 99 if the read failed. */
static double drift_error_px_(bool correction, double phase_ms, uint32_t strip_ms,
                              uint32_t *capture_ms, uint8_t *final_state)
{
    double true_d;
    uint32_t t_cap;
    world_defaults_();
    W.dist_m = 5.0;
    W.bearing_rad = -0.03;
    project_scene_();
    board_up_(true);
    gl_sim_cam_set_phase_us(GL_CAM_RIGHT, (uint32_t)(phase_ms * 1000.0));
    gl_sim_set_compute_us(GL_TRACE_VISION_STRIP, strip_ms * 1000u);
    gl_sim_set_compute_us(GL_TRACE_VISION_BAND, 8u * strip_ms * 1000u);
    (void)gl_app_init(&app);
    app.read.time_correction = correction;
    watch_reset_();
    *capture_ms = 0;
    if (!run_until_state_(GL_UI_CAPTURE, 6000)) {
        *final_state = app.ui.state;
        return 99.0;
    }
    t_cap = now_ms_();
    W.drift_t0_s = (double)gl_sim_now_us() * 1e-6;
    W.drift_px_per_s = 6.0;
    W.drift_turn_s = 1.7; /* out and back: stays in the strip however long the read takes */
    while (app.ui.state == (uint8_t)GL_UI_CAPTURE && now_ms_() < t_cap + 60000u) {
        run_until_ms_(now_ms_() + 1u);
    }
    *capture_ms = now_ms_() - t_cap;
    *final_state = app.ui.state;
    if (app.ui.state != (uint8_t)GL_UI_SHOW_RESULT || !app.cur.flag_found) {
        return 99.0;
    }
    true_d = 657.0 * (double)GL_CFG_CAM_BASELINE_M /
             (W.dist_m * cos(W.bearing_rad) - (double)GL_CFG_CAM_LEFT_Y_MM * 0.001);
    return (double)app.cur.disparity_px - true_d;
}

/* Review (major): with the analysis of a strip taking longer than a frame
 * the exposures of an L R R L group were no longer evenly spaced, the time
 * stamps (taken when the application polled) hid it, and the timing
 * correction computed zero: "worst corrected disparity error 0.0076 px at
 * 0-30 ms, 0.0251 px at 60 ms, 0.112 px at 100 ms".  And with 260 ms per
 * strip "the UI leaves CAPTURE with ERROR (TIMEOUT) at 7.97 s". */
GL_TEST(test_lrrl_timing_with_vision_run_time)
{
    static const uint32_t compute[] = { 0, 30, 60, 100, 200, 300 };
    static const double phases[] = { 2.0, 9.0, 16.0, 24.0, 31.0 };
    double worst0 = 0.0;
    printf("    stick drifting 6 px/s, 5 sensor phases; vision run time charged per strip:\n");
    printf("    %-9s %-23s %-25s %-13s %s\n", "per strip", "worst |err| corrected",
           "worst |err| uncorrected", "capture", "camera rail on");
    for (size_t c = 0; c < GL_ARRAY_LEN(compute); c++) {
        double w_on = 0.0, w_off = 0.0;
        uint32_t cap_max = 0;
        uint64_t rail_us = 0;
        for (size_t i = 0; i < GL_ARRAY_LEN(phases); i++) {
            uint8_t fs = 0;
            uint32_t cap = 0;
            const double e_on = drift_error_px_(true, phases[i], compute[c], &cap, &fs);
            GL_CHECK_EQ(fs, GL_UI_SHOW_RESULT); /* never a time-out, however slow */
            rail_us = gl_sim_stats()->cam_rail_on_us;
            GL_CHECK_EQ(gl_sim_stats()->trace_points[GL_TRACE_VISION_STRIP], 32u);
            GL_CHECK_EQ(gl_sim_stats()->trace_points[GL_TRACE_VISION_BAND], 1u);
            GL_CHECK_EQ(gl_sim_violation_total(), 0);
            if (cap > cap_max) {
                cap_max = cap;
            }
            if (fabs(e_on) > w_on) {
                w_on = fabs(e_on);
            }
            if (c == 0u || c == 3u) {
                const double e_off = drift_error_px_(false, phases[i], compute[c], &cap, &fs);
                if (fabs(e_off) > w_off) {
                    w_off = fabs(e_off);
                }
            }
        }
        if (c == 0u || c == 3u) {
            printf("    %3u ms    %-23.4f %-25.4f %5.2f s       %.2f s\n", (unsigned)compute[c], w_on,
                   w_off, (double)cap_max / 1000.0, (double)rail_us / 1e6);
        } else {
            printf("    %3u ms    %-23.4f %-25s %5.2f s       %.2f s\n", (unsigned)compute[c], w_on,
                   "-", (double)cap_max / 1000.0, (double)rail_us / 1e6);
        }
        if (c == 0u) {
            worst0 = w_on;
        }
        /* the correction is as good with a slow CPU as with an infinitely
         * fast one: the exposure spacing no longer depends on it */
        GL_CHECK(w_on < 0.02);
        GL_CHECK(w_on < worst0 + 0.01);
    }
}

int main(void)
{
    GL_RUN(test_charge_gate_after_an_imu_bus_error);
    GL_RUN(test_charge_gate_with_a_silent_imu);
    GL_RUN(test_charge_gate_second_opinion_and_staleness);
    GL_RUN(test_one_imu_bus_error_is_not_permanent);
    GL_RUN(test_imu_absent_at_boot_only);
    GL_RUN(test_imu_reset_while_asleep_is_repaired);
    GL_RUN(test_dead_imu_ends_in_a_watchdog_reset);
    GL_RUN(test_a_lost_data_ready_interrupt_does_not_stall);
    GL_RUN(test_precision_reread_with_a_second_turn);
    GL_RUN(test_fault_and_double_tap_in_the_cradle);
    GL_RUN(test_vbus_bounce);
    GL_RUN(test_the_power_rules_of_the_simulator_fire);
    GL_RUN(test_set_cal_that_fails_changes_nothing);
    GL_RUN(test_log_erase_with_an_event_in_between);
    GL_RUN(test_storage_mode_for_a_nearly_empty_cell);
    GL_RUN(test_lrrl_timing_with_vision_run_time);
    return gl_test_summary();
}
