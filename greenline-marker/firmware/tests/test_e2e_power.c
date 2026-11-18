/*
 * test_e2e_power.c - the whole firmware on the host simulator: the power
 * behaviour of the rev E board (firmware phase 3).
 *
 *   E13   no camera read from a cell that reads above 60 C: the "TOO HOT"
 *         screen, 4 s, sleep; 3 K of hysteresis; the die sensors stand in
 *         for a thermistor that has failed
 *   E13   ship mode: armed by a command, entered when the marker is lifted
 *         out of the cradle; the MCU in Shutdown, IMU and flash powered
 *         down, display off; motion does not wake it; VBUS does, through a
 *         reset; a reset without VBUS goes back
 *   E32   the cradle: awake for as long as a host talks; 30 s without a host
 *         (a wall charger) or without a word from it -> asleep in the cradle
 *         with a static symbol; out of that sleep by the host's resume, by
 *         VBUS going, and for a moment whenever the charger's status
 *         changes.  The marker's draw there against the charger's
 *         termination current, and what the charge did before this change
 *   E32   the 6 h backstop, with a host that never stops talking
 *   E14   the sleep current of the supply model, underside dark and lit
 *
 * EVERY CURRENT here is a figure of the simulator's supply model
 * (hal/host/gl_sim.h, GL_SIM_I_*): data-sheet values from memory, PROVISIONAL
 * figures of the netlist notes, or guesses.  Nothing was measured: there is
 * no board.  The charger is a MODEL of the BQ25101 (GL_PROV_BQ25101_*).
 */
#include "gl_e2e_world.h"

#include "gl_pins.h"
#include "ls013b7dh03.h"
#include "lsm6dsv16x.h"

static uint32_t now_ms_(void)
{
    return (uint32_t)(gl_sim_now_us() / 1000u);
}

/* Marker powered up, lying still, never handled. */
static void still_board_(void)
{
    world_defaults_();
    W.t_pick_s = 1.0e9;
    W.t_place_s = 1.0e9;
    board_up_(true);
}

/* Log events with a code: the count, and the argument of the last one. */
static unsigned log_events_(uint16_t code, int32_t *last_arg)
{
    gl_log_iter_t it;
    gl_log_rec_t rec;
    uint8_t buf[128];
    unsigned n = 0;
    gl_log_iter_begin(&app.log, &it);
    while (gl_log_iter_next(&app.log, &it, &rec, buf, sizeof(buf)) == GL_OK) {
        gl_log_event_t ev;
        if (rec.type == GL_LOG_REC_EVENT && gl_log_event_decode(buf, rec.len, &ev) == GL_OK &&
            ev.code == code) {
            n++;
            if (last_arg != NULL) {
                *last_arg = ev.arg;
            }
        }
    }
    return n;
}

static void no_violation_(void)
{
    if (gl_sim_violation_total() != 0u) {
        printf("    first violation: %s\n", gl_sim_violations()->first);
    }
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* Mean current over a stretch, microamperes: what the board drew from the
 * cell's node while docked (the charger's output that is not charge
 * current), and what came out of the cell otherwise. */
typedef struct {
    double docked_uas, cell_uas;
    uint64_t docked_us, t_us, stop_us;
} mark_t;
static mark_t mark_(void)
{
    mark_t m;
    m.docked_uas = gl_sim_stats()->load_docked_uas;
    m.cell_uas = gl_sim_stats()->charge_uas;
    m.docked_us = gl_sim_stats()->docked_us;
    m.stop_us = gl_sim_stats()->stop_us;
    m.t_us = gl_sim_now_us();
    return m;
}
static double docked_ua_since_(mark_t m)
{
    const uint64_t dt = gl_sim_stats()->docked_us - m.docked_us;
    return (dt == 0u) ? 0.0 : (gl_sim_stats()->load_docked_uas - m.docked_uas) / ((double)dt * 1e-6);
}
static double cell_ua_since_(mark_t m)
{
    const uint64_t dt = gl_sim_now_us() - m.t_us;
    return (dt == 0u) ? 0.0 : (gl_sim_stats()->charge_uas - m.cell_uas) / ((double)dt * 1e-6);
}
static double stop_fraction_since_(mark_t m)
{
    const uint64_t dt = gl_sim_now_us() - m.t_us;
    return (dt == 0u) ? 0.0 : (double)(gl_sim_stats()->stop_us - m.stop_us) / (double)dt;
}

/* ======================================================================= */
/* 1. E13: no camera read above 60 C                                        */
/* ======================================================================= */

/* One placement of the marker (picked up 0.5 s from now, down 0.6 s later);
 * returns the state the UI is in when it has either a result or the TOO HOT
 * screen, or has gone back to sleep. */
static gl_ui_state_t place_and_see_(void)
{
    const uint32_t t0 = now_ms_();
    W.t_pick_s = (double)t0 / 1000.0 + 0.5;
    W.t_place_s = W.t_pick_s + 0.6;
    while (now_ms_() < t0 + 12000u) {
        run_until_ms_(now_ms_() + 5u);
        if (app.ui.state == (uint8_t)GL_UI_SHOW_RESULT || app.ui.state == (uint8_t)GL_UI_TOO_HOT ||
            app.ui.state == (uint8_t)GL_UI_ERROR) {
            break;
        }
    }
    return (gl_ui_state_t)app.ui.state;
}

GL_TEST(test_no_camera_read_from_a_hot_cell)
{
    int32_t arg = 0;
    uint32_t t_hot;

    /* the board (cell, IMU, MCU) at 61.5 C when the marker is put down */
    world_defaults_();
    board_up_(true);
    gl_sim_imu_set_temperature(61.5f);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    watch_reset_();
    GL_CHECK(run_until_state_(GL_UI_TOO_HOT, 9000));
    t_hot = now_ms_();
    print_seen_();
    /* no camera was powered, no frame taken, the rail rule never bent */
    GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, 0u);
    GL_CHECK_EQ(gl_sim_stats()->frames_captured, 0u);
    GL_CHECK(!gl_sim_cam_rail_on() && cam_pins_parked_());
    GL_CHECK(app.power.read_hot);
    GL_CHECK(app.power.cell_temp_valid);
    GL_CHECK_NEAR(app.power.cell_temp_c, 61.5, 0.1);
    GL_CHECK_EQ(app.reads_total, 0u);
    /* the screen: on, and what the UI drew is what the panel holds */
    run_until_ms_(now_ms_() + 50u);
    GL_CHECK(gl_sim_lcd()->disp);
    GL_CHECK_EQ(panel_differs_from_framebuffer_(), 0u);
    GL_CHECK(gl_gfx_count_black(&app.gfx) > 400u);
    /* logged, with the temperature that refused the read */
    GL_CHECK(log_events_((uint16_t)GL_APP_LOGEV_TOO_HOT, &arg) >= 1u);
    GL_CHECK_NEAR((double)arg, 615.0, 1.0);
    /* 4 s, then asleep with the display off */
    GL_CHECK(run_until_state_(GL_UI_SLEEP, t_hot + 4300u));
    GL_CHECK(app.ui.state_since_ms >= t_hot + 3900u && app.ui.state_since_ms <= t_hot + 4200u);
    GL_CHECK(!gl_sim_lcd()->disp && !app.awake);
    printf("    cell at 61.5 C: TOO HOT %.0f ms after the wake-up (the cell is measured when the "
           "marker wakes, before the tilt read), no camera powered; asleep %.2f s later\n",
           (double)t_hot - 1000.0 * W.t_pick_s, (double)(app.ui.state_since_ms - t_hot) / 1000.0);

    /* hysteresis (GL_PROV_READ_TEMP_HYST_C = 3 K): cooled to 58.5 C the next
     * placement is still refused; at 56.5 C the read runs */
    gl_sim_imu_set_temperature(58.5f);
    GL_CHECK_EQ(place_and_see_(), GL_UI_TOO_HOT);
    GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, 0u);
    GL_CHECK(run_until_state_(GL_UI_SLEEP, now_ms_() + 5000u));
    gl_sim_imu_set_temperature(56.5f);
    GL_CHECK_EQ(place_and_see_(), GL_UI_SHOW_RESULT);
    GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, 1u);
    GL_CHECK(!app.power.read_hot);
    GL_CHECK_EQ(app.reads_total, 1u);
    GL_CHECK(run_until_state_(GL_UI_SLEEP, now_ms_() + 60000u));
    /* coming from below, 59.5 C is not "above 60 C": the read runs */
    gl_sim_imu_set_temperature(59.5f);
    GL_CHECK_EQ(place_and_see_(), GL_UI_SHOW_RESULT);
    GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, 2u);
    GL_CHECK(run_until_state_(GL_UI_SLEEP, now_ms_() + 60000u));
    /* ... and 60.5 C is */
    gl_sim_imu_set_temperature(60.5f);
    GL_CHECK_EQ(place_and_see_(), GL_UI_TOO_HOT);
    GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, 2u);
    GL_CHECK(run_until_state_(GL_UI_SLEEP, now_ms_() + 5000u));

    /* the thermistor has failed (broken off): the hotter of the die sensors
     * stands in for it - 66 C: no read; 30 C: the read runs */
    gl_sim_ntc_set_fault(GL_SIM_NTC_OPEN);
    gl_sim_imu_set_temperature(66.0f);
    GL_CHECK_EQ(place_and_see_(), GL_UI_TOO_HOT);
    GL_CHECK_EQ(app.power.ntc_fault, GL_NTC_OPEN);
    GL_CHECK(!app.power.cell_temp_valid);
    GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, 2u);
    GL_CHECK(log_events_((uint16_t)GL_APP_LOGEV_TOO_HOT, &arg) >= 4u);
    GL_CHECK_NEAR((double)arg, 660.0, 5.0);
    GL_CHECK(run_until_state_(GL_UI_SLEEP, now_ms_() + 5000u));
    gl_sim_imu_set_temperature(30.0f);
    GL_CHECK_EQ(place_and_see_(), GL_UI_SHOW_RESULT);
    GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, 3u);
    GL_CHECK_EQ(seen.rail_outside_capture, 0u);
    no_violation_();
}

/* The gate is applied again where the cameras would start, on a reading that
 * is at most GL_APP_READ_TEMP_MAX_AGE_MS (5 s) old there - measured again if
 * it is older.  (a) A marker that wakes at 20 C and is carried about for 9 s
 * while its cell goes to 63 C: measured at the camera start, refused.
 * (b) THE LIMIT OF IT, pinned: a cell that jumps by 40 K inside those 5 s is
 * not seen (no cell does that; the reading the gate used is printed). */
GL_TEST(test_read_gate_measures_before_the_cameras)
{
    uint32_t reads0;
    uint64_t bias0;
    /* (a) */
    world_defaults_();
    W.t_pick_s = 1.0;
    W.t_place_s = 10.0; /* handled for 9 s */
    board_up_(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    watch_reset_();
    run_until_ms_(4000u);
    GL_CHECK(app.awake && !app.power.read_hot);
    GL_CHECK_NEAR(app.power.cell_temp_c, 22.0, 0.1); /* as measured at the wake-up */
    gl_sim_set_cell_temperature(63.0f);
    gl_sim_imu_set_temperature(40.0f); /* the board lags behind */
    reads0 = gl_sim_stats()->ntc_reads;
    bias0 = gl_sim_stats()->ntc_bias_us;
    GL_CHECK(run_until_state_(GL_UI_TOO_HOT, 16000u));
    print_seen_();
    GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, 0u);
    GL_CHECK_EQ(gl_sim_stats()->ntc_reads - reads0, 1u);
    GL_CHECK_NEAR(app.power.cell_temp_c, 63.0, 0.1);
    printf("    (a) cell at 63 C when the tilt read ended, last reading 22 C from the wake-up "
           "%.1f s before: measured again at the camera start (%u conversion, NTC_BIAS driven "
           "%.2f ms), read refused\n", (double)(now_ms_() - 1020u) / 1000.0,
           (unsigned)(gl_sim_stats()->ntc_reads - reads0),
           (double)(gl_sim_stats()->ntc_bias_us - bias0) / 1000.0);
    no_violation_();
    /* (b) */
    world_defaults_();
    board_up_(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    watch_reset_();
    GL_CHECK(run_until_state_(GL_UI_READ_TILT, 9000));
    gl_sim_set_cell_temperature(63.0f);
    reads0 = gl_sim_stats()->ntc_reads;
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 9000));
    GL_CHECK_EQ(gl_sim_stats()->ntc_reads, reads0);       /* not measured again */
    GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, 1u);     /* PINNED: the read ran */
    printf("    (b) the same jump during the tilt read of a marker put straight down: NOT seen, the "
           "read ran on the wake-up reading of %.1f C (the gate accepts a reading up to %.0f s old)\n",
           (double)app.power.cell_temp_c, (double)GL_APP_READ_TEMP_MAX_AGE_MS / 1000.0);
    no_violation_();
}

/* ======================================================================= */
/* 2. E13: ship mode                                                        */
/* ======================================================================= */

/* Booted in the cradle with a host that has opened the port. */
static void docked_with_host_(void)
{
    still_board_();
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    gl_sim_usb_host_open(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    watch_reset_();
    host_rx_len_ = 0;
    run_until_ms_(now_ms_() + 400u);
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_USB);
    GL_CHECK(app.usb_on);
}

static uint8_t ship_cmd_(uint8_t seq_no, const char *word)
{
    uint8_t seq;
    const uint8_t *pl;
    int n;
    host_send_(seq_no, GL_CMD_SHIP_MODE, word, 4);
    n = host_get_(GL_CMD_SHIP_MODE | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
    GL_CHECK_EQ(n, 2);
    GL_CHECK_EQ(pl[0], GL_OK);
    return pl[1];
}

GL_TEST(test_ship_mode_entry_and_wake_on_vbus)
{
    uint8_t seq;
    const uint8_t *pl;
    int n;
    int32_t arg = 0;
    uint32_t t_lift;
    double ship_ua;

    docked_with_host_();
    /* the command arms it; nothing else changes while the marker is docked */
    GL_CHECK_EQ(ship_cmd_(1, "SHIP"), 1);
    GL_CHECK(app.ship_armed && !app.ship_pending);
    host_send_(2, GL_CMD_GET_POWER, NULL, 0);
    n = host_get_(GL_CMD_GET_POWER | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
    GL_CHECK_EQ(n, 1 + (int)GL_PROTO_POWER_LEN);
    GL_CHECK(gl_get_u16(&pl[13]) & GL_PROTO_PWR_SHIP_ARMED);
    GL_CHECK_EQ(pl[12], GL_CRADLE_LINK);
    run_talking_until_ms_(now_ms_() + 3000u);
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_USB);
    GL_CHECK(gl_sim_charger_on());
    GL_CHECK(!gl_sim_mcu_shutdown());

    /* lifted out: the ordinary way out of the cradle first (USB off, the
     * charger's stop released, display off) - but the IMU is powered DOWN,
     * not left in wake-on-motion ... */
    gl_sim_set_input(GL_PIN_VBUS_SENSE, false);
    gl_sim_usb_host_open(false);
    t_lift = now_ms_();
    run_until_ms_(t_lift + 300u);
    GL_CHECK_EQ(app.ui.state, GL_UI_SLEEP);
    GL_CHECK(app.ship_pending && !app.halted);
    GL_CHECK(!gl_sim_mcu_shutdown());
    GL_CHECK_EQ(gl_sim_imu_reg(0x10) & 0x0Fu, 0u); /* accelerometer off */
    GL_CHECK_EQ(gl_sim_imu_reg(0x5E), 0u);         /* no wake-up routed to INT1 */
    /* ... and GL_APP_SHIP_SETTLE_MS after VBUS went, ship mode */
    run_until_ms_(t_lift + GL_APP_SHIP_SETTLE_MS + 200u);
    GL_CHECK(app.halted);
    GL_CHECK(gl_sim_mcu_shutdown());
    GL_CHECK_EQ(gl_sim_stats()->ship_entries, 1u);
    /* the state of the board: every pin of the MCU released, the board's
     * resistors hold the chip selects, DISP, the camera rail and the
     * charger's stop; the devices powered down */
    for (int p = 0; p < (int)GL_PIN_COUNT; p++) {
        GL_CHECK_EQ(gl_sim_pin_mode((gl_pin_t)p), GL_PIN_MODE_ANALOG);
    }
    GL_CHECK(gl_sim_pin_level(GL_PIN_FLASH_CS) && gl_sim_pin_level(GL_PIN_IMU_CS));
    GL_CHECK(!gl_sim_pin_level(GL_PIN_LCD_SCS) && !gl_sim_pin_level(GL_PIN_LCD_DISP));
    GL_CHECK(!gl_sim_pin_level(GL_PIN_CAM_PWR_EN) && !gl_sim_pin_level(GL_PIN_CHG_INHIBIT));
    GL_CHECK(!gl_sim_cam_rail_on());
    GL_CHECK(!gl_sim_lcd()->disp && !gl_sim_lcd()->extcomin);
    GL_CHECK(gl_sim_flash_stats()->deep_power_down);
    GL_CHECK_EQ(gl_sim_imu_reg(0x10) & 0x0Fu, 0u);
    GL_CHECK_EQ(gl_sim_imu_reg(0x11) & 0x0Fu, 0u);
    GL_CHECK_EQ(gl_sim_imu_reg(0x0D), 0u);
    GL_CHECK_EQ(gl_sim_imu_reg(0x0E), 0u);
    no_violation_();

    /* motion does not wake it: the marker is handled for a minute, and even
     * a level forced onto the IMU's interrupt line changes nothing */
    {
        const uint32_t kicks = gl_sim_stats()->watchdog_kicks;
        W.t_pick_s = (double)now_ms_() / 1000.0 + 1.0;
        W.t_place_s = W.t_pick_s + 30.0;
        run_until_ms_(now_ms_() + 60000u);
        gl_sim_set_input(GL_PIN_IMU_INT1, true);
        gl_sim_advance_ms(1000);
        gl_sim_set_input(GL_PIN_IMU_INT1, false);
        GL_CHECK(gl_sim_mcu_shutdown() && app.halted);
        GL_CHECK_EQ(gl_sim_stats()->ship_wakes, 0u);
        GL_CHECK_EQ(gl_sim_stats()->watchdog_kicks, kicks); /* no firmware ran */
        GL_CHECK_EQ(gl_sim_violations()->watchdog, 0u);     /* and no watchdog runs */
    }
    /* what it draws there: 24 h */
    {
        const mark_t m = mark_();
        gl_sim_advance_ms(24u * 3600u * 1000u);
        ship_ua = cell_ua_since_(m);
        GL_CHECK(gl_sim_stats()->shutdown_us >= 24ull * 3600ull * 1000000ull);
    }
    /* a reset from another cause (a glitch on the reset pad) without VBUS:
     * gl_hal_init() goes straight back to ship mode */
    gl_sim_mcu_reset(GL_RESET_PIN);
    GL_CHECK_EQ(gl_app_init(&app), GL_ERR_STATE);
    GL_CHECK(app.halted && gl_sim_mcu_shutdown());
    GL_CHECK_EQ(gl_sim_stats()->ship_wakes, 0u);
    run_until_ms_(now_ms_() + 5000u);
    GL_CHECK(gl_sim_mcu_shutdown());

    /* into a cradle: VBUS on the wake-up pin restarts the MCU.  The charger
     * has started by itself already (no firmware was needed for that) */
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    GL_CHECK(!gl_sim_mcu_shutdown());
    GL_CHECK_EQ(gl_sim_stats()->ship_wakes, 1u);
    GL_CHECK(gl_sim_charger_on());
    gl_sim_advance_ms(3); /* reset and start-up code */
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    watch_reset_();
    GL_CHECK(!app.halted && !app.ship_armed && !app.ship_pending);
    run_until_ms_(now_ms_() + 400u);
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_USB);
    GL_CHECK(gl_sim_charger_on());
    GL_CHECK_EQ(gl_hal_rtc_seconds(), 0u); /* the clock stopped in ship mode: "not set" */
    /* the log: the entry (with the cell voltage) and the boot that left it */
    GL_CHECK_EQ(log_events_((uint16_t)GL_APP_LOGEV_SHIP, &arg), 1u);
    GL_CHECK_NEAR((double)arg, 3900.0, 10.0);
    GL_CHECK(log_events_((uint16_t)GL_APP_LOGEV_BOOT, &arg) >= 2u);
    GL_CHECK(((uint32_t)arg & GL_RESET_SHIP_WAKE) != 0u);
    /* out of the cradle again: an ordinary sleep, wake-on-motion ON, and the
     * marker reads when it is put down */
    gl_sim_set_input(GL_PIN_VBUS_SENSE, false);
    run_until_ms_(now_ms_() + GL_APP_SHIP_SETTLE_MS + 1000u);
    GL_CHECK_EQ(app.ui.state, GL_UI_SLEEP);
    GL_CHECK(!gl_sim_mcu_shutdown() && !app.halted);
    GL_CHECK(gl_sim_imu_reg(0x10) != 0u && (gl_sim_imu_reg(0x5E) & 0x20u) != 0u);
    GL_CHECK_EQ(place_and_see_(), GL_UI_SHOW_RESULT);
    GL_CHECK_EQ(gl_sim_stats()->ship_entries, 1u);
    no_violation_();

    /* THE REQUIREMENT (DESIGN_SPEC section 6): "no more than 5 microamps at
     * the cell, protection circuit included; at least 3 months from a 30 %
     * charge".  The supply model: */
    {
        const double fixed = GL_SIM_I_ALWAYS_UA(3900.0);
        const double days = 0.30 * GL_SIM_CELL_MAH * 1000.0 / ship_ua / 24.0;
        printf("    ship mode, supply model at 3.9 V: %.2f uA at the cell = MCU in Shutdown %.2f + "
               "IMU powered down %.1f + flash %.1f + the board's always-on parts %.2f (regulator "
               "%.1f, battery divider %.2f, protection circuit %.1f, charger leakage %.3f, camera "
               "regulator off %.1f, USB regulator's enable pin %.1f)\n",
               ship_ua, GL_SIM_I_MCU_SHUTDOWN_UA, GL_SIM_I_IMU_OFF_UA, GL_SIM_I_FLASH_DPD_UA, fixed,
               GL_SIM_I_REG_2V8_UA, 3900.0 * 1000.0 / GL_SIM_R_VBAT_DIVIDER_OHM, GL_SIM_I_CELL_PCM_UA,
               GL_SIM_I_CHARGER_LEAK_UA, GL_SIM_I_REG_CAM_OFF_UA, GL_SIM_I_REG_USB_EN_UA);
        printf("    NOT MET: the requirement is 5 uA; the model gives %.1f uA, of which the firmware "
               "controls %.1f (MCU, IMU, flash).  30 %% of the cell (%.1f mAh) lasts %.0f days there, "
               "not 3 months (every figure PROVISIONAL, nothing measured)\n", ship_ua,
               GL_SIM_I_MCU_SHUTDOWN_UA + GL_SIM_I_IMU_OFF_UA + GL_SIM_I_FLASH_DPD_UA,
               0.30 * GL_SIM_CELL_MAH, days);
        /* the pin: the model's figure (a change of the model must be looked at) */
        GL_CHECK_NEAR(ship_ua, fixed + GL_SIM_I_MCU_SHUTDOWN_UA + GL_SIM_I_IMU_OFF_UA + GL_SIM_I_FLASH_DPD_UA,
                      0.05);
        GL_CHECK(ship_ua > 5.0);  /* PINNED: NOT MET */
        GL_CHECK(ship_ua < 14.0);
        GL_CHECK(days < 90.0);    /* PINNED: NOT MET */
    }
}

GL_TEST(test_ship_mode_disarm_bounce_and_asleep_in_the_cradle)
{
    /* "STAY" disarms: lifted out, the marker sleeps the ordinary way */
    docked_with_host_();
    GL_CHECK_EQ(ship_cmd_(1, "SHIP"), 1);
    GL_CHECK_EQ(ship_cmd_(2, "STAY"), 0);
    GL_CHECK(!app.ship_armed);
    gl_sim_set_input(GL_PIN_VBUS_SENSE, false);
    gl_sim_usb_host_open(false);
    run_until_ms_(now_ms_() + GL_APP_SHIP_SETTLE_MS + 2000u);
    GL_CHECK_EQ(app.ui.state, GL_UI_SLEEP);
    GL_CHECK(!gl_sim_mcu_shutdown() && !app.halted);
    GL_CHECK_EQ(gl_sim_stats()->ship_entries, 0u);
    GL_CHECK((gl_sim_imu_reg(0x5E) & 0x20u) != 0u); /* wake-on-motion */
    no_violation_();

    /* armed, lifted for 0.3 s and put back (the operator fumbles; the pins
     * bounce): not entered, still armed, charging again */
    docked_with_host_();
    GL_CHECK_EQ(ship_cmd_(1, "SHIP"), 1);
    gl_sim_set_input(GL_PIN_VBUS_SENSE, false);
    run_until_ms_(now_ms_() + 300u);
    GL_CHECK(app.ship_pending);
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    run_until_ms_(now_ms_() + GL_APP_SHIP_SETTLE_MS + 2000u);
    GL_CHECK(!gl_sim_mcu_shutdown() && !app.halted);
    GL_CHECK_EQ(gl_sim_stats()->ship_entries, 0u);
    GL_CHECK(app.ship_armed && !app.ship_pending);
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_USB);
    GL_CHECK(gl_sim_charger_on());
    /* armed, then left in the cradle until it sleeps there (the box is
     * packed an hour later): lifted out of THAT sleep it goes to ship mode */
    gl_sim_usb_host_open(false);
    gl_sim_usb_host_bus(GL_USB_BUS_NONE);
    run_until_ms_(now_ms_() + 3600u * 1000u);
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_SLEEP);
    GL_CHECK(app.ship_armed);
    gl_sim_set_input(GL_PIN_VBUS_SENSE, false);
    run_until_ms_(now_ms_() + GL_APP_SHIP_SETTLE_MS + 500u);
    GL_CHECK(gl_sim_mcu_shutdown() && app.halted);
    GL_CHECK_EQ(gl_sim_stats()->ship_entries, 1u);
    GL_CHECK(!gl_sim_lcd()->disp);
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_CHG_INHIBIT), GL_PIN_MODE_ANALOG);
    no_violation_();

    /* a cell that the firmware had stopped charging (too hot for its window)
     * goes into ship mode with the stop RELEASED: the next cradle charges it
     * whatever this firmware does */
    docked_with_host_();
    GL_CHECK_EQ(ship_cmd_(1, "SHIP"), 1);
    gl_sim_imu_set_temperature(50.0f);
    run_talking_until_ms_(now_ms_() + GL_APP_CHG_TEMP_PERIOD_MS + 500u);
    GL_CHECK(gl_sim_pin_drives_high(GL_PIN_CHG_INHIBIT));
    gl_sim_set_input(GL_PIN_VBUS_SENSE, false);
    gl_sim_usb_host_open(false);
    run_until_ms_(now_ms_() + GL_APP_SHIP_SETTLE_MS + 500u);
    GL_CHECK(gl_sim_mcu_shutdown());
    GL_CHECK(!gl_sim_pin_drives_high(GL_PIN_CHG_INHIBIT) && !gl_sim_pin_level(GL_PIN_CHG_INHIBIT));
    gl_sim_imu_set_temperature(22.0f);
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    GL_CHECK(gl_sim_charger_on()); /* before any firmware has run */
    no_violation_();
}

/* The simulator's ship-mode rules fire when they should (a rule that cannot
 * fail proves nothing), and with VBUS present the call does nothing. */
GL_TEST(test_ship_mode_rules_of_the_simulator)
{
    gl_sim_reset(true);
    GL_CHECK_EQ(gl_hal_init(), GL_OK);
    /* VBUS present: there would be no edge to wake on - refused */
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    gl_hal_ship_mode_enter();
    GL_CHECK(!gl_sim_mcu_shutdown());
    GL_CHECK_EQ(gl_sim_stats()->ship_entries, 0u);
    gl_sim_set_input(GL_PIN_VBUS_SENSE, false);
    /* entered with the charger's stop still driven: counted */
    gl_hal_gpio_write(GL_PIN_CHG_INHIBIT, true);
    gl_hal_gpio_mode(GL_PIN_CHG_INHIBIT, GL_PIN_MODE_OUTPUT_PP);
    gl_hal_ship_mode_enter();
    GL_CHECK(gl_sim_mcu_shutdown());
    GL_CHECK_EQ(gl_sim_violations()->power, 1u);
    /* Shutdown releases the pin all the same: the charger is free */
    GL_CHECK(!gl_sim_pin_drives_high(GL_PIN_CHG_INHIBIT));
    /* entered with the display on: counted */
    gl_sim_reset(true);
    GL_CHECK_EQ(gl_hal_init(), GL_OK);
    {
        static gl_lcd_t lcd;
        gl_lcd_init(&lcd, NULL);
        GL_CHECK_EQ(gl_lcd_on(&lcd), GL_OK);
    }
    gl_hal_ship_mode_enter();
    GL_CHECK(gl_sim_violations()->stop_mode >= 1u);
}

/* ======================================================================= */
/* 3. E32: the cradle                                                       */
/* ======================================================================= */

/* A wall charger: VBUS, nobody on the data lines.  30 s after docking the
 * marker is asleep in the cradle; the charge ENDS there, the charger's
 * status change wakes the marker for a moment and the symbol says FULL. */
GL_TEST(test_cradle_sleep_on_a_wall_charger_lets_the_charge_end)
{
    const double i_term = (double)GL_PROV_BQ25101_TERM_FRACTION * (double)GL_PROV_BQ25101_ICHG_UA;
    mark_t m;
    double awake_ua, sleep_ua;
    uint32_t t_sleep, frames, ntc0;
    double hours = 0.0;

    still_board_();
    gl_sim_cell_enable(0.90f);
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    watch_reset_();
    run_until_ms_(1000u);
    /* awake in the cradle state: USB started (nobody answers), display on */
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_USB);
    GL_CHECK(app.usb_on && !gl_hal_usb_connected());
    GL_CHECK_EQ(gl_hal_usb_bus(), GL_USB_BUS_NONE);
    GL_CHECK_EQ(gl_app_cradle_state(&app), GL_CRADLE_LINK);
    GL_CHECK(gl_sim_charger_on());
    m = mark_();
    run_until_ms_(29000u);
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_USB);
    awake_ua = docked_ua_since_(m);
    /* 30 s without a host */
    GL_CHECK(run_until_state_(GL_UI_CRADLE_SLEEP, 31000u));
    t_sleep = app.ui.state_since_ms;
    GL_CHECK(t_sleep >= 29900u && t_sleep <= 30600u);
    run_until_ms_(now_ms_() + 200u);
    GL_CHECK_EQ(gl_app_cradle_state(&app), GL_CRADLE_SLEEP);
    GL_CHECK(app.cradle_sleep && !app.awake && !app.usb_on && !app.usb_standby);
    /* the display stays ON with the static symbol; its polarity signal runs */
    GL_CHECK(gl_sim_lcd()->disp && gl_sim_lcd()->extcomin);
    GL_CHECK_EQ(gl_sim_lcd()->extcomin_period, GL_PINS_EXTCOMIN_LSE_TICKS);
    GL_CHECK_EQ(panel_differs_from_framebuffer_(), 0u);
    GL_CHECK(app.view.charging && !app.view.chg_full && app.view.chg_blocked == 0u);
    /* IMU and flash powered down, the camera rail off */
    GL_CHECK_EQ(gl_sim_imu_reg(0x10) & 0x0Fu, 0u);
    GL_CHECK_EQ(gl_sim_imu_reg(0x11) & 0x0Fu, 0u);
    GL_CHECK(gl_sim_flash_stats()->deep_power_down);
    GL_CHECK(!gl_sim_cam_rail_on());
    /* ten minutes of it: Stop mode nearly all the time, the picture is not
     * redrawn, the cell is still measured every 5 s, motion wakes nothing */
    frames = gl_sim_lcd()->frames;
    ntc0 = gl_sim_stats()->ntc_reads;
    m = mark_();
    W.t_pick_s = (double)now_ms_() / 1000.0 + 5.0; /* the cradle is knocked about */
    W.t_place_s = W.t_pick_s + 3.0;
    run_until_ms_(now_ms_() + 600000u);
    sleep_ua = docked_ua_since_(m);
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_SLEEP);
    GL_CHECK(stop_fraction_since_(m) > 0.995);
    GL_CHECK_EQ(gl_sim_lcd()->frames, frames);
    GL_CHECK(gl_sim_stats()->ntc_reads - ntc0 >= 110u && gl_sim_stats()->ntc_reads - ntc0 <= 130u);
    GL_CHECK(gl_sim_charger_on());
    printf("    wall charger: awake in the cradle state the marker draws %.2f mA from the node the "
           "charger feeds (termination threshold %.2f mA): the charge could not end.  Asleep in the "
           "cradle, from %.1f s after docking: %.1f uA (Stop mode %.2f %% of the time, cell measured "
           "every %u s)\n", awake_ua / 1000.0, i_term / 1000.0, (double)t_sleep / 1000.0, sleep_ua,
           100.0 * stop_fraction_since_(m), (unsigned)(GL_APP_CHG_TEMP_PERIOD_MS / 1000u));
    GL_CHECK(awake_ua > i_term);       /* why E32 exists */
    GL_CHECK(sleep_ua < 0.10 * i_term); /* asleep: under a tenth of the threshold */
    /* the charge runs to its end */
    while (gl_sim_charger_on() && hours < 6.0) {
        run_until_ms_(now_ms_() + 60000u);
        hours += 1.0 / 60.0;
    }
    GL_CHECK_EQ(gl_sim_charger_state(), GL_SIM_CHG_DONE);
    GL_CHECK_EQ(gl_sim_stats()->chg_terminations, 1u);
    /* the status edge woke the marker for the new picture, and only for that */
    run_until_ms_(now_ms_() + 6000u);
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_SLEEP);
    GL_CHECK_EQ(app.power.chg_status, GL_CHGST_DONE);
    GL_CHECK(app.view.chg_full && !app.view.charging);
    GL_CHECK(gl_sim_lcd()->frames > frames);
    GL_CHECK_EQ(panel_differs_from_framebuffer_(), 0u);
    GL_CHECK_EQ(app.power.chg_reason, GL_CHG_ALLOWED);
    GL_CHECK(!gl_sim_pin_drives_high(GL_PIN_CHG_INHIBIT));
    GL_CHECK(!app.power.time_limit);
    printf("    ... and the charge terminated by itself %.2f h after docking at %.1f %% (from 90 %%; "
           "the cell is a guess); symbol FULL; the firmware's 6 h backstop was not needed\n",
           (double)now_ms_() / 3.6e6, 100.0 * (double)gl_sim_cell_soc());
    GL_CHECK_EQ(log_events_((uint16_t)GL_APP_LOGEV_CHARGER, NULL), 1u);
    /* a day later: still asleep, still supervised, nothing odd */
    m = mark_();
    run_until_ms_(now_ms_() + 24u * 3600u * 1000u);
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_SLEEP);
    GL_CHECK(stop_fraction_since_(m) > 0.995);
    GL_CHECK_EQ(gl_sim_violations()->watchdog, 0u);

    /* lifted out of the cradle sleep: the ordinary sleep - display off,
     * wake-on-motion on - and the marker reads when it is put down */
    gl_sim_set_input(GL_PIN_VBUS_SENSE, false);
    run_until_ms_(now_ms_() + 500u);
    GL_CHECK_EQ(app.ui.state, GL_UI_SLEEP);
    GL_CHECK(!app.cradle_sleep && !gl_sim_lcd()->disp && !gl_sim_lcd()->extcomin);
    GL_CHECK((gl_sim_imu_reg(0x5E) & 0x20u) != 0u);
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_CHG_INHIBIT), GL_PIN_MODE_ANALOG);
    run_until_ms_(now_ms_() + 2000u);
    GL_CHECK_EQ(place_and_see_(), GL_UI_SHOW_RESULT);
    no_violation_();
}

/* WHAT HAPPENED BEFORE THIS CHANGE, and the backstop.  Until phase 3 the
 * marker stayed awake in the cradle state for as long as VBUS was there.
 * The same thing still happens, legitimately, under a host that never stops
 * talking: the marker draws more than the termination current, the charger
 * never sees the end of the charge, and the firmware stops it after 6 h of
 * continuous charging (DESIGN_SPEC E32). */
GL_TEST(test_awake_in_the_cradle_the_charge_never_ends_until_the_backstop)
{
    const double i_term = (double)GL_PROV_BQ25101_TERM_FRACTION * (double)GL_PROV_BQ25101_ICHG_UA;
    mark_t m;
    uint32_t t_stop = 0;
    double soc_3h, out_3h;
    uint8_t seq;
    const uint8_t *pl;
    int n;

    still_board_();
    gl_sim_cell_enable(0.90f);
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    gl_sim_usb_host_open(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    watch_reset_();
    host_rx_len_ = 0;
    m = mark_();
    run_talking_until_ms_(3u * 3600u * 1000u);
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_USB);
    soc_3h = (double)gl_sim_cell_soc();
    out_3h = gl_sim_charger_out_ua();
    /* three hours on: the cell is full, the charger still "charging" - its
     * output feeds the marker and never falls to the threshold */
    GL_CHECK(gl_sim_charger_on());
    GL_CHECK_EQ(gl_sim_stats()->chg_terminations, 0u);
    GL_CHECK(out_3h > i_term);
    GL_CHECK(app.power.charging && app.view.charging && !app.view.chg_full);
    printf("    a host that keeps talking (the marker awake, as it always was before phase 3): mean "
           "draw %.2f mA; after 3 h the cell is at %.1f %% and the charger still delivers %.2f mA "
           "(threshold %.2f mA): no termination, the symbol says CHARGING\n",
           docked_ua_since_(m) / 1000.0, 100.0 * soc_3h, out_3h / 1000.0, i_term / 1000.0);
    /* ... until the firmware's backstop */
    while (now_ms_() < 7u * 3600u * 1000u) {
        run_talking_until_ms_(now_ms_() + 10000u);
        if (t_stop == 0u && app.power.time_limit) {
            t_stop = now_ms_();
            break;
        }
    }
    GL_CHECK(t_stop != 0u);
    GL_CHECK(t_stop >= GL_PROV_CHARGE_MAX_MS && t_stop <= GL_PROV_CHARGE_MAX_MS + 30000u);
    GL_CHECK_EQ(app.power.chg_reason, GL_CHG_TIME_LIMIT);
    GL_CHECK(gl_sim_pin_drives_high(GL_PIN_CHG_INHIBIT));
    GL_CHECK(!gl_sim_charger_on());
    GL_CHECK_EQ(gl_sim_charger_state(), GL_SIM_CHG_DISABLED);
    GL_CHECK_EQ(gl_sim_stats()->chg_terminations, 0u);
    run_talking_until_ms_(now_ms_() + 1000u);
    GL_CHECK_EQ(app.view.chg_blocked, 4); /* "TIME LIMIT" on the cradle screen */
    printf("    ... stopped by the firmware %.3f h after docking (CHG_INHIBIT high, reason TIME "
           "LIMIT)\n", (double)t_stop / 3.6e6);
    /* the host can see all of it */
    host_rx_len_ = 0;
    host_send_(7, GL_CMD_GET_POWER, NULL, 0);
    n = host_get_(GL_CMD_GET_POWER | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
    GL_CHECK_EQ(n, 1 + (int)GL_PROTO_POWER_LEN);
    GL_CHECK_EQ(pl[10], GL_CHGST_INHIBITED);
    GL_CHECK_EQ(pl[11], GL_CHG_TIME_LIMIT);
    GL_CHECK(gl_get_u16(&pl[13]) & GL_PROTO_PWR_TIME_LIMIT);
    GL_CHECK(gl_get_u16(&pl[13]) & GL_PROTO_PWR_INHIBIT);
    /* the stop holds while the cell is up; the awake marker now runs from
     * the cell, and when that has fallen below the restart voltage the
     * charge starts again with a fresh limit */
    {
        uint32_t t_again = 0;
        const uint32_t t_end = now_ms_() + 12u * 3600u * 1000u;
        while (now_ms_() < t_end) {
            run_talking_until_ms_(now_ms_() + 60000u);
            if (gl_sim_charger_on()) {
                t_again = now_ms_();
                break;
            }
        }
        GL_CHECK(t_again != 0u);
        /* (measured with the charge running again: 20 mA through the cell's
         * resistance lift it by 30 mV) */
        GL_CHECK(app.power.batt_mv < GL_PROV_CHARGE_RESTART_MV + 50u);
        GL_CHECK_EQ(app.power.chg_reason, GL_CHG_ALLOWED);
        GL_CHECK(!app.power.time_limit);
        printf("    ... and released %.2f h later, when the awake marker had run the cell down to "
               "%u mV (%.1f %%): charging again\n", (double)(t_again - t_stop) / 3.6e6,
               (unsigned)app.power.batt_mv, 100.0 * (double)gl_sim_cell_soc());
    }
    no_violation_();
}

/* A PC.  While it talks: awake, USB running.  When it suspends the bus (it
 * has gone to sleep): 30 s later the marker sleeps in the cradle with USB in
 * standby, and the PC's resume wakes it.  When it leaves the bus running
 * but says nothing: 30 s later the marker detaches and sleeps (a device may
 * not sleep under a running bus) - and THEN ONLY RE-DOCKING BRINGS IT BACK:
 * pinned below as a limitation. */
GL_TEST(test_cradle_sleep_under_a_host_standby_resume_and_silence)
{
    uint8_t seq;
    const uint8_t *pl;
    int n;
    mark_t m;
    uint32_t t0;
    const double i_term = (double)GL_PROV_BQ25101_TERM_FRACTION * (double)GL_PROV_BQ25101_ICHG_UA;

    docked_with_host_();
    /* five minutes of a talking host: awake all the time, never in Stop mode */
    m = mark_();
    run_talking_until_ms_(now_ms_() + 300000u);
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_USB);
    GL_CHECK_EQ(gl_sim_stats()->stop_us - m.stop_us, 0u);
    GL_CHECK(app.usb_on && gl_hal_usb_connected());
    GL_CHECK_EQ(gl_hal_usb_bus(), GL_USB_BUS_ACTIVE);

    /* the PC goes to sleep: bus suspended */
    gl_sim_usb_host_bus(GL_USB_BUS_SUSPENDED);
    t0 = now_ms_();
    GL_CHECK(run_until_state_(GL_UI_CRADLE_SLEEP, t0 + 31000u));
    GL_CHECK(now_ms_() - t0 >= 19000u); /* 30 s after the last word, which was up to 10 s ago */
    run_until_ms_(now_ms_() + 200u);
    GL_CHECK(app.usb_standby && !app.usb_on);
    GL_CHECK(!gl_hal_usb_connected());
    GL_CHECK(gl_sim_lcd()->disp && gl_sim_lcd()->extcomin);
    m = mark_();
    run_until_ms_(now_ms_() + 600000u);
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_SLEEP);
    GL_CHECK(app.usb_standby);
    GL_CHECK(stop_fraction_since_(m) > 0.995);
    printf("    host suspended: asleep in the cradle with USB in standby, %.1f uA (the MCU in Stop 1 "
           "there, GL_PROV_USB_WAKE_FROM_STOP2 = %d: %.0f uA + %.0f uA for the USB core, both from "
           "memory / guessed); threshold %.0f uA\n", docked_ua_since_(m), GL_PROV_USB_WAKE_FROM_STOP2,
           GL_SIM_I_MCU_STOP1_UA, GL_SIM_I_USB_STANDBY_UA, i_term);
    GL_CHECK(docked_ua_since_(m) < 0.15 * i_term);
    /* the PC wakes up and resumes the bus: awake again within a few
     * milliseconds, no new enumeration, and it answers */
    t0 = now_ms_();
    gl_sim_usb_host_bus(GL_USB_BUS_ACTIVE);
    GL_CHECK(run_until_state_(GL_UI_CRADLE_USB, t0 + 100u));
    printf("    host resumed the bus: back in the cradle state %u ms later\n", (unsigned)(now_ms_() - t0));
    run_until_ms_(now_ms_() + 50u);
    GL_CHECK(app.usb_on && !app.usb_standby && app.awake);
    GL_CHECK(gl_hal_usb_connected());
    GL_CHECK(app.imu_ok);
    host_rx_len_ = 0;
    host_send_(21, GL_CMD_PING, "back", 4);
    n = host_get_(GL_CMD_PING | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
    GL_CHECK_EQ(n, 5);
    GL_CHECK_EQ(seq, 21);
    host_send_(22, GL_CMD_GET_POWER, NULL, 0);
    n = host_get_(GL_CMD_GET_POWER | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
    GL_CHECK_EQ(pl[12], GL_CRADLE_LINK);
    no_violation_();

    /* the bus keeps running, the host says nothing: 30 s, then detached and
     * asleep */
    t0 = now_ms_();
    GL_CHECK(run_until_state_(GL_UI_CRADLE_SLEEP, t0 + 31000u));
    GL_CHECK(now_ms_() - t0 >= 29000u);
    run_until_ms_(now_ms_() + 200u);
    GL_CHECK(!app.usb_on && !app.usb_standby);
    GL_CHECK(!gl_hal_usb_connected());
    m = mark_();
    run_until_ms_(now_ms_() + 60000u);
    GL_CHECK(stop_fraction_since_(m) > 0.995);
    /* LIMITATION, pinned: the host now sends something - nobody is there to
     * hear it (the device is off the bus), and nothing wakes the marker.
     * A host that wants the marker has to talk at least every 30 s, or the
     * marker has to be taken out of the cradle and put back. */
    host_rx_len_ = 0;
    host_send_(23, GL_CMD_PING, "late", 4);
    n = host_get_(GL_CMD_PING | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
    GL_CHECK_EQ(n, -1);
    run_until_ms_(now_ms_() + 20000u);
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_SLEEP); /* PINNED: NOT MET "the host can always reach it" */
    printf("    host silent on a running bus: detached and asleep after 30 s; a command sent then "
           "is NOT answered (the marker is off the bus) - NOT MET: reachable again only by "
           "re-docking\n");
    /* re-docked: the cradle state again, and it answers */
    gl_sim_set_input(GL_PIN_VBUS_SENSE, false);
    run_until_ms_(now_ms_() + 1500u);
    GL_CHECK_EQ(app.ui.state, GL_UI_SLEEP);
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    run_until_ms_(now_ms_() + 400u);
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_USB);
    GL_CHECK(app.usb_on);
    host_rx_len_ = 0;
    host_send_(24, GL_CMD_PING, "dock", 4);
    n = host_get_(GL_CMD_PING | GL_PROTO_RESPONSE_FLAG, &seq, &pl);
    GL_CHECK_EQ(n, 5);
    no_violation_();
}

static void heat_to_50_(void *arg)
{
    (void)arg;
    gl_sim_imu_set_temperature(50.0f);
}

/* Asleep in the cradle the firmware still supervises: the cell heats up to
 * 50 C (inside the charger's own window, outside the firmware's) - stopped
 * within the supervision period, the symbol says why; cool again - released. */
GL_TEST(test_cradle_sleep_supervises_the_charge)
{
    uint64_t out0;
    uint32_t frames, t_set;
    still_board_();
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    watch_reset_();
    run_until_ms_(120000u);
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_SLEEP);
    GL_CHECK(gl_sim_charger_on());
    out0 = gl_sim_stats()->chg_outside_us;
    frames = gl_sim_lcd()->frames;
    /* in the middle of a Stop-mode stretch (the IMU is off: the MCU's die
     * sensor is what vouches for the thermistor) */
    t_set = now_ms_() + GL_APP_CHG_TEMP_PERIOD_MS + 200u;
    GL_CHECK(gl_sim_at_ms(t_set, heat_to_50_, NULL));
    run_until_ms_(t_set + GL_APP_CHG_TEMP_PERIOD_MS + 500u);
    GL_CHECK(!gl_sim_charger_on());
    GL_CHECK(gl_sim_pin_drives_high(GL_PIN_CHG_INHIBIT));
    GL_CHECK_EQ(app.power.chg_reason, GL_CHG_TOO_HOT);
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_SLEEP);
    GL_CHECK(gl_sim_stats()->chg_outside_us - out0 <= (uint64_t)GL_APP_CHG_TEMP_PERIOD_MS * 1000u + 50000u);
    GL_CHECK_EQ(app.view.chg_blocked, 2);
    GL_CHECK(gl_sim_lcd()->frames > frames); /* the picture was drawn again: it says why */
    GL_CHECK_EQ(panel_differs_from_framebuffer_(), 0u);
    printf("    asleep in the cradle, cell to 50 C: the charger ran %.2f s in its WARM zone before "
           "the firmware stopped it\n", (double)(gl_sim_stats()->chg_outside_us - out0) / 1e6);
    /* an hour of that: still stopped, still asleep (the stop draws 28 uA
     * through the gate resistor) */
    {
        const mark_t m = mark_();
        run_until_ms_(now_ms_() + 3600u * 1000u);
        GL_CHECK(gl_sim_pin_drives_high(GL_PIN_CHG_INHIBIT));
        GL_CHECK(stop_fraction_since_(m) > 0.995);
        GL_CHECK(gl_sim_stats()->chg_outside_us - out0 <= (uint64_t)GL_APP_CHG_TEMP_PERIOD_MS * 1000u + 50000u);
    }
    gl_sim_imu_set_temperature(25.0f);
    run_until_ms_(now_ms_() + GL_APP_CHG_TEMP_PERIOD_MS + 500u);
    GL_CHECK(gl_sim_charger_on());
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_CHG_INHIBIT), GL_PIN_MODE_ANALOG);
    GL_CHECK_EQ(app.view.chg_blocked, 0);
    GL_CHECK(app.view.charging);
    /* the charger does not charge although it should (a weak source behind
     * the cradle's fuse): shown and logged as a fault after 30 s */
    gl_sim_charger_input_low(true);
    run_until_ms_(now_ms_() + GL_APP_CHG_FAULT_AFTER_MS + 2u * GL_APP_CHG_TEMP_PERIOD_MS + 1000u);
    GL_CHECK_EQ(app.power.chg_status, GL_CHGST_NOT_CHARGING);
    GL_CHECK(app.chg_fault);
    GL_CHECK_EQ(app.view.chg_blocked, 6);
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_SLEEP);
    gl_sim_charger_input_low(false);
    run_until_ms_(now_ms_() + 2u * GL_APP_CHG_TEMP_PERIOD_MS);
    GL_CHECK(!app.chg_fault);
    GL_CHECK_EQ(app.view.chg_blocked, 0);
    no_violation_();
}

/* ======================================================================= */
/* 4. E14: the sleep current of the supply model                            */
/* ======================================================================= */

GL_TEST(test_sleep_current_dark_and_lit_against_25_microamps)
{
    mark_t m;
    double dark, lit, fixed, pads, bias_ms;
    uint64_t bias0;

    still_board_();
    gl_sim_set_vbat_mv(3800); /* the cell voltage E14 names */
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    watch_reset_();
    run_until_ms_(60000u);
    GL_CHECK_EQ(app.ui.state, GL_UI_SLEEP);
    /* both thermistors unpowered: NTC_BIAS analog (NTC1 is fed by the
     * charger, from VBUS only) */
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_NTC_BIAS), GL_PIN_MODE_ANALOG);
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_NTC_SENSE), GL_PIN_MODE_ANALOG);
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_OPAMP_VOUT), GL_PIN_MODE_ANALOG);
    m = mark_();
    bias0 = gl_sim_stats()->ntc_bias_us;
    run_until_ms_(now_ms_() + 3600u * 1000u);
    dark = cell_ua_since_(m);
    GL_CHECK(stop_fraction_since_(m) > 0.9995);
    /* NTC2 is biased only for the cell measurement the housekeeping makes
     * every GL_APP_SLEEP_BATT_EVERY wake-ups (11 minutes): under a millisecond each */
    GL_CHECK(gl_sim_stats()->ntc_bias_us - bias0 <= 6u * 700u);
    bias_ms = (double)(gl_sim_stats()->ntc_bias_us - bias0) / 1000.0;
    gl_sim_set_underside_lit(true);
    m = mark_();
    run_until_ms_(now_ms_() + 3600u * 1000u);
    lit = cell_ua_since_(m);
    fixed = GL_SIM_I_ALWAYS_UA(3800.0);
    pads = dark - GL_SIM_I_CELL_PCM_UA;
    printf("    asleep out of the cradle, supply model at 3.8 V, underside DARK: %.2f uA at the cell\n"
           "      MCU in Stop 2 %.1f, IMU in wake-on-motion %.1f, flash in deep power-down %.1f,\n"
           "      2.8 V regulator %.1f, battery divider %.2f, cell protection circuit %.1f, charger "
           "leakage %.3f,\n"
           "      camera regulator (off) %.1f, USB regulator's enable pin %.1f (E26, NOT CONFIRMED), "
           "housekeeping %.2f;\n"
           "      both thermistors 0 (NTC1 is biased by the charger from VBUS only; NTC_BIAS analog but "
           "for %.2f ms in the hour), wake pull-up 150 kohm 0 in the dark\n",
           dark, GL_SIM_I_MCU_STOP_UA, GL_SIM_I_IMU_WAKE_UA, GL_SIM_I_FLASH_DPD_UA, GL_SIM_I_REG_2V8_UA,
           3800.0 * 1000.0 / GL_SIM_R_VBAT_DIVIDER_OHM, GL_SIM_I_CELL_PCM_UA, GL_SIM_I_CHARGER_LEAK_UA,
           GL_SIM_I_REG_CAM_OFF_UA, GL_SIM_I_REG_USB_EN_UA,
           dark - fixed - GL_SIM_I_MCU_STOP_UA - GL_SIM_I_IMU_WAKE_UA - GL_SIM_I_FLASH_DPD_UA, bias_ms);
    printf("    underside LIT: %.2f uA at the cell (+%.2f through the 150 kohm wake pull-up)\n", lit,
           lit - dark);
    printf("    E14 limit 25 uA, measured through the cell-lead pads (the protection circuit is not "
           "in that path): model %.2f uA dark -> %s; %.2f uA lit -> %s (E27: the limit is for a dark "
           "underside).  Every figure PROVISIONAL, nothing measured\n", pads,
           (pads <= 25.0) ? "MET (model)" : "NOT MET", lit - GL_SIM_I_CELL_PCM_UA,
           (lit - GL_SIM_I_CELL_PCM_UA <= 25.0) ? "met" : "NOT MET");
    /* the model's sum, pinned (a change of the model must be looked at) */
    GL_CHECK_NEAR(dark, fixed + GL_SIM_I_MCU_STOP_UA + GL_SIM_I_IMU_WAKE_UA + GL_SIM_I_FLASH_DPD_UA, 0.15);
    GL_CHECK_NEAR(lit - dark, GL_SIM_I_WAKE_PULLUP_LIT_UA, 0.01);
    GL_CHECK(pads <= 25.0);                              /* E14, dark: MET by the model */
    GL_CHECK(lit - GL_SIM_I_CELL_PCM_UA > 25.0);         /* PINNED: with a lit underside it is not */
    printf("    standby from a full cell (%.0f mAh) at %.1f uA: %.0f days to empty; from 30 %%: %.0f "
           "days (ship mode exists for that)\n", GL_SIM_CELL_MAH, dark,
           GL_SIM_CELL_MAH * 1000.0 / dark / 24.0, 0.30 * GL_SIM_CELL_MAH * 1000.0 / dark / 24.0);
    no_violation_();
}

int main(void)
{
    GL_RUN(test_no_camera_read_from_a_hot_cell);
    GL_RUN(test_read_gate_measures_before_the_cameras);
    GL_RUN(test_ship_mode_entry_and_wake_on_vbus);
    GL_RUN(test_ship_mode_disarm_bounce_and_asleep_in_the_cradle);
    GL_RUN(test_ship_mode_rules_of_the_simulator);
    GL_RUN(test_cradle_sleep_on_a_wall_charger_lets_the_charge_end);
    GL_RUN(test_awake_in_the_cradle_the_charge_never_ends_until_the_backstop);
    GL_RUN(test_cradle_sleep_under_a_host_standby_resume_and_silence);
    GL_RUN(test_cradle_sleep_supervises_the_charge);
    GL_RUN(test_sleep_current_dark_and_lit_against_25_microamps);
    return gl_test_summary();
}
