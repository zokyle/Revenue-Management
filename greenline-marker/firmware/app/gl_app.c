/* gl_app.c - application main loop and glue.  See gl_app.h. */
#include "gl_app.h"

#include <math.h>
#include <string.h>

#include "gl_config.h"
#include "gl_grain.h"
#include "gl_hal.h"
#include "gl_provisional.h"
#include "grain_frontend.h"

/* The blob store is power-fail safe only if a full set of values fits one
 * sector (core/gl_log.h). */
typedef char gl_app_store_sector_holds_a_full_set_[
    (GL_MX25R_SECTOR_BYTES >= GL_STORE_MIN_SECTOR_BYTES) ? 1 : -1];

/* The zeroing rule below ("never in the cradle") rests on the cradle seating
 * the marker one way round only (master_params.yaml, cradle.orientations). */
#if GL_CFG_CRADLE_ORIENTATIONS != 1
#error "cradle.orientations changed: revisit where the zeroing routine may run"
#endif

/* The method setting is stored with the solver's own codes. */
typedef char gl_app_method_codes_match_[
    ((int)GL_METHOD_B1 == (int)GL_SOLVER_METHOD_B1 && (int)GL_METHOD_B2 == (int)GL_SOLVER_METHOD_B2)
        ? 1 : -1];

#define ALL_IRQS                                                                          \
    (GL_IRQ_IMU_INT1 | GL_IRQ_IMU_INT2 | GL_IRQ_VBUS_CHANGE | GL_IRQ_CHG_STAT |           \
     GL_IRQ_WAKE_TIMER | GL_IRQ_USB_RX | GL_IRQ_DCMI_DONE | GL_IRQ_TICK)

/* ======================================================================= */
/* small services                                                           */
/* ======================================================================= */

void gl_app_post(gl_app_t *app, gl_ui_event_t ev, int32_t arg)
{
    (void)gl_event_post(&app->events, (uint16_t)ev, arg);
}

gl_status_t gl_app_store_put(gl_app_t *app, uint8_t id, const uint8_t *data, size_t len)
{
    gl_status_t st;
    if (!app->storage_ok) {
        return GL_ERR_NOT_FOUND;
    }
    st = gl_store_put(&app->store, id, data, len);
    if (st != GL_OK) {
        app->last_error = (uint16_t)st;
    }
    return st;
}

void gl_app_log_event(gl_app_t *app, uint16_t code, int32_t arg)
{
    gl_log_event_t ev;
    uint8_t buf[GL_LOG_EVENT_LEN];
    if (!app->storage_ok) {
        return;
    }
    ev.rtc_s = gl_hal_rtc_seconds();
    ev.code = code;
    ev.arg = arg;
    gl_log_event_encode(&ev, buf);
    (void)gl_log_append(&app->log, (uint8_t)GL_LOG_REC_EVENT, 0, buf, sizeof(buf), NULL);
}

/* A device or bus failed: remember, log, show. */
static void fault_(gl_app_t *app, gl_status_t st)
{
    app->last_error = (uint16_t)st;
    gl_app_log_event(app, (uint16_t)GL_APP_LOGEV_FAULT, (int32_t)st);
    gl_app_post(app, GL_EV_FAULT, (int32_t)st);
}

gl_status_t gl_app_set_settings(gl_app_t *app, const gl_settings_t *s)
{
    uint8_t blob[GL_SETTINGS_BLOB_LEN];
    gl_settings_t v = *s;
    gl_status_t st = gl_settings_validate(&v);
    if (st != GL_OK) {
        return st;
    }
    app->settings = v;
    app->ui.edit = v;
    app->ui.saved = v;
    gl_settings_encode(&v, blob);
    st = gl_app_store_put(app, (uint8_t)GL_STORE_ID_SETTINGS, blob, sizeof(blob));
    /* without storage the settings still apply until the next reset */
    return (st == GL_ERR_NOT_FOUND) ? GL_OK : st;
}

/* Enable exactly the interrupt sources the present state needs. */
static void irq_setup_(gl_app_t *app)
{
    uint32_t on = GL_IRQ_VBUS_CHANGE | GL_IRQ_WAKE_TIMER;
    if (app->awake) {
        on |= GL_IRQ_IMU_INT2 | GL_IRQ_CHG_STAT;
    } else {
        on |= GL_IRQ_IMU_INT1;
    }
    if (app->usb_on) {
        on |= GL_IRQ_USB_RX;
    }
    if (app->capture_active) {
        on |= GL_IRQ_DCMI_DONE;
    }
    if (on != app->irq_mask) {
        gl_hal_irq_enable(ALL_IRQS & ~on, false);
        gl_hal_irq_enable(on, true);
        app->irq_mask = on;
    }
}

/* ======================================================================= */
/* storage                                                                  */
/* ======================================================================= */

static void load_store_(gl_app_t *app)
{
    const uint8_t *d = NULL;
    size_t n = 0;
    /* a blob that fails to decode leaves the defaults in place */
    if (gl_store_get(&app->store, (uint8_t)GL_STORE_ID_SETTINGS, &d, &n) == GL_OK) {
        (void)gl_settings_decode(d, n, &app->settings);
    }
    if (gl_store_get(&app->store, (uint8_t)GL_STORE_ID_CAL_TILT, &d, &n) == GL_OK) {
        (void)gl_cal_tilt_decode(d, n, &app->cal_tilt);
    }
    if (gl_store_get(&app->store, (uint8_t)GL_STORE_ID_CAL_CAM_L, &d, &n) == GL_OK) {
        (void)gl_cal_cam_decode(d, n, &app->cal_cam[GL_CAM_LEFT]);
    }
    if (gl_store_get(&app->store, (uint8_t)GL_STORE_ID_CAL_CAM_R, &d, &n) == GL_OK) {
        (void)gl_cal_cam_decode(d, n, &app->cal_cam[GL_CAM_RIGHT]);
    }
    if (gl_store_get(&app->store, (uint8_t)GL_STORE_ID_CAL_GRAIN, &d, &n) == GL_OK) {
        (void)gl_cal_grain_decode(d, n, &app->cal_grain);
    }
    if (gl_store_get(&app->store, (uint8_t)GL_STORE_ID_COURSE, &d, &n) == GL_OK) {
        (void)gl_stick_height_decode(d, n, &app->stick_height);
    }
}

/* One raw-strip log record being assembled (978 bytes: static, not stack). */
static uint8_t raw_chunk_[GL_LOG_RAW_HDR_LEN + GL_APP_RAW_CHUNK_BYTES];

/* Raw-strip logging for field data collection (settings.raw_log_level). */
static void strip_hook_(void *ctx, const gl_strip_t *s, gl_cam_id_t cam, uint8_t kind,
                        uint8_t frame_index)
{
    gl_app_t *app = (gl_app_t *)ctx;
    uint8_t *const buf = raw_chunk_;
    gl_log_raw_hdr_t h;
    const uint8_t level = app->settings.raw_log_level;
    const uint32_t total = (uint32_t)s->width * s->height;

    if (!app->storage_ok || level == (uint8_t)GL_RAWLOG_OFF || s->stride != s->width) {
        return;
    }
    if (level == (uint8_t)GL_RAWLOG_FIRST && !(kind == 1u && frame_index < 2u)) {
        return; /* only the first left / right pair of stick strips */
    }
    h.read_id = app->read_id;
    h.camera = (uint8_t)cam;
    h.kind = kind;
    h.frame_index = frame_index;
    h.reserved = 0;
    h.x0 = s->x0;
    h.y0 = s->y0;
    h.width = s->width;
    h.height = s->height;
    for (uint32_t off = 0; off < total; off += GL_APP_RAW_CHUNK_BYTES) {
        const uint32_t n = (total - off < GL_APP_RAW_CHUNK_BYTES) ? (total - off)
                                                                  : GL_APP_RAW_CHUNK_BYTES;
        h.offset = off;
        gl_log_raw_hdr_encode(&h, buf);
        memcpy(&buf[GL_LOG_RAW_HDR_LEN], &s->px[off], n);
        if (gl_log_append(&app->log, (uint8_t)GL_LOG_REC_RAW_CHUNK, 0, buf,
                          GL_LOG_RAW_HDR_LEN + (size_t)n, NULL) != GL_OK) {
            break;
        }
        gl_hal_watchdog_kick();
    }
    /* Writing a strip takes about half a second, so a read with raw logging
     * outlasts the UI's capture time limit: report progress.  (While a strip
     * is being written no IMU sample is processed, so a bump may go
     * unnoticed: acceptable for data collection, where the raw strips are
     * the product.) */
    gl_ui_keepalive(&app->ui, gl_hal_tick_ms());
}

/* ======================================================================= */
/* temperature and the charge gate                                          */
/* ======================================================================= */

/* Read the IMU's die temperature (with the driver's liveness check).  Any
 * failure leaves the temperature UNKNOWN: temp_valid is never left over
 * from an earlier read. */
static void temp_refresh_(gl_app_t *app, uint32_t now)
{
    float t = 0.0f;
    if (app->imu_ok && gl_imu_read_temperature(&app->imu, &t) == GL_OK) {
        app->temp_c = t;
        app->temp_valid = true;
        app->temp_ms = now;
    } else {
        app->temp_valid = false;
    }
}

/* Apply the charge gate from what is known NOW (drivers/power.h has the
 * rules).  The cell NTC is the input; the IMU's and the MCU's die sensors
 * only vouch for it.  A reading counts as known only if it is fresh. */
static void charge_gate_(gl_app_t *app, uint32_t now)
{
    const bool cell_fresh = app->cell_seen &&
                            (uint32_t)(now - app->cell_temp_ms) <= GL_APP_CELL_TEMP_MAX_AGE_MS;
    const bool imu_t = app->imu_ok && app->temp_valid &&
                       (uint32_t)(now - app->temp_ms) <= GL_APP_TEMP_MAX_AGE_MS;
    const bool mcu_t = app->cell_seen && app->power.mcu_temp_valid &&
                       (uint32_t)(now - app->mcu_temp_ms) <= GL_APP_CELL_TEMP_MAX_AGE_MS;
    const uint8_t before = app->power.chg_reason;

    (void)gl_power_charge_gate(&app->power, cell_fresh, app->temp_c, imu_t, mcu_t);
    if (app->power.chg_reason != before) {
        if (app->awake) {
            /* reason in the low byte, the cell temperature in 0.1 C above it
             * (not logged while asleep: the flash is in deep power-down) */
            const int32_t t10 = app->power.cell_temp_valid
                                    ? (int32_t)gl_roundi(gl_clampf(app->power.cell_temp_c, -100.0f,
                                                                   200.0f) * 10.0f)
                                    : -9999;
            gl_app_log_event(app, (uint16_t)GL_APP_LOGEV_CHARGE,
                             (int32_t)app->power.chg_reason | (int32_t)((uint32_t)t10 << 8));
        }
        if (app->ui.state == (uint8_t)GL_UI_CRADLE_USB) {
            app->redraw = true;
        }
    }
}

/* Measure the cell and the die temperatures and apply the gate: at a VBUS
 * edge (the charger has just started by itself), at boot in the cradle, and
 * every GL_APP_CHG_TEMP_PERIOD_MS while VBUS is present. */
static void charge_supervise_(gl_app_t *app, uint32_t now)
{
    app->next_chg_ms = now + GL_APP_CHG_TEMP_PERIOD_MS;
    gl_power_poll_pins(&app->power);
    if (gl_power_measure_temps(&app->power) != GL_OK) {
        app->last_error = (uint16_t)GL_ERR_IO;
    }
    app->cell_seen = true;
    app->cell_temp_ms = now;
    app->mcu_temp_ms = now;
    temp_refresh_(app, now);
    charge_gate_(app, now);
}

/* ======================================================================= */
/* core clock: fast only for the compute-heavy part of a read               */
/* ======================================================================= */

/* DESIGN_SPEC rev C2: 160 MHz from the PLL during a read, slow otherwise.
 * "During a read" is: from the start of the capture (the vision runs on
 * every strip) to the end of the putt solve.  A PLL that does not lock is
 * not an error: everything works at the slow clock, only later. */
static void clock_(gl_app_t *app, bool fast)
{
    if (fast == app->clock_fast) {
        return;
    }
    if (fast) {
        if (gl_hal_clock_set(GL_CLOCK_FAST) == GL_OK) {
            app->clock_fast = true;
        } else {
            app->clock_fails++;
        }
    } else {
        (void)gl_hal_clock_set(GL_CLOCK_SLOW);
        app->clock_fast = false;
    }
}

/* ======================================================================= */
/* IMU supervision: motion is the only user input                           */
/* ======================================================================= */

/* One attempt to bring the IMU back: probe, reset, and the mode the device
 * needs right now.  On failure the part is at least asked to stop (it must
 * not be left measuring at full rate with its interrupts unrouted). */
static void imu_recover_(gl_app_t *app, uint32_t now)
{
    gl_status_t st = gl_imu_init(&app->imu, NULL);
    if (st == GL_OK) {
        if (!app->awake && app->storage_mode) {
            st = GL_OK; /* gl_imu_init() leaves both sensors off: what storage mode wants */
        } else if (app->awake) {
            st = gl_imu_start_measure(&app->imu);
        } else {
            st = gl_imu_start_wake_on_motion(&app->imu, (uint16_t)GL_PROV_IMU_WAKE_THRESHOLD_MG);
        }
    }
    if (st == GL_OK) {
        if (!app->imu_ok || app->imu_fails != 0u) {
            gl_app_log_event(app, (uint16_t)GL_APP_LOGEV_IMU_RECOVERED, (int32_t)app->imu_fails);
            app->imu_recoveries++;
        }
        app->imu_ok = true;
        app->imu_fails = 0;
        app->imu_fault_shown = false;
        app->imu_backoff_ms = 0;
        app->wdg_hold = false;
        if (app->awake) {
            /* the sample stream starts afresh: stillness history, gestures */
            gl_motion_restart(&app->motion);
            app->last_sample_ms = now;
            app->next_batt_ms = now; /* and the temperature is read again at once */
        }
        return;
    }
    app->imu_ok = false;
    app->temp_valid = false;
    (void)gl_imu_stop(&app->imu); /* best effort */
    if (app->imu_fails < 255u) {
        app->imu_fails++;
    }
    app->imu_backoff_ms = (app->imu_backoff_ms == 0u) ? GL_APP_IMU_RETRY_MIN_MS
                                                      : (2u * app->imu_backoff_ms);
    if (app->imu_backoff_ms > GL_APP_IMU_RETRY_MAX_MS) {
        app->imu_backoff_ms = GL_APP_IMU_RETRY_MAX_MS;
    }
    app->imu_retry_ms = now + app->imu_backoff_ms;
    if (app->imu_fails >= GL_APP_IMU_MAX_FAILS && !app->usb_on) {
        /* the last thing left to try is a clean reset (SPI peripheral, pins) */
        app->wdg_hold = true;
    }
}

/* The IMU failed a transfer, a check or a mode change.  The failure is
 * treated as TRANSIENT: one recovery attempt at once; only if that fails is
 * the fault shown (once per episode), and the retries go on with back-off
 * while awake and at every housekeeping wake-up while asleep. */
static void imu_failed_(gl_app_t *app, gl_status_t st, uint32_t now)
{
    const bool was_reading = app->tilt_active || app->capture_active;
    app->imu_ok = false;
    app->temp_valid = false; /* no temperature: the charge gate closes */
    charge_gate_(app, now);
    imu_recover_(app, now);
    if (app->imu_ok) {
        if (was_reading) {
            /* samples were lost: the read in progress starts again */
            gl_app_post(app, GL_EV_MOTION, 0);
        }
        return;
    }
    if (!app->imu_fault_shown) {
        app->imu_fault_shown = true;
        fault_(app, st);
    }
}

/* ======================================================================= */
/* wake and sleep                                                           */
/* ======================================================================= */

static void usb_start_(gl_app_t *app)
{
    if (!app->usb_on && gl_hal_usb_start() == GL_OK) {
        app->usb_on = true;
        gl_proto_rx_reset(&app->proto);
    }
    irq_setup_(app);
}

static void usb_stop_(gl_app_t *app)
{
    if (app->usb_on) {
        gl_hal_usb_stop();
        app->usb_on = false;
        app->stream_mask = 0;
        app->six.active = false;
        gl_proto_disconnect(&app->proto);
    }
    if (app->log_erasing) {
        /* the erase is driven from the USB service: without it, give up.
         * The oldest sectors are gone, the rest of the log is intact and
         * accepts records again; the host starts the erase anew. */
        app->log_erasing = false;
        gl_log_erase_cancel(&app->log);
    }
    irq_setup_(app);
}

/* Stop a tilt read / capture.  Afterwards the camera rail is off. */
static void abort_read_(gl_app_t *app)
{
    app->tilt_active = false;
    if (app->capture_active || gl_read_busy(&app->read) || app->cam.powered) {
        gl_read_abort(&app->read);
    }
    app->capture_active = false;
    clock_(app, false);
    gl_motion_set_strict(&app->motion, false);
    irq_setup_(app);
}

static void wake_(gl_app_t *app, uint32_t now)
{
    if (!app->lcd.on) {
        const gl_status_t st = gl_lcd_on(&app->lcd);
        if (st != GL_OK) {
            app->last_error = (uint16_t)st;
        }
    }
    if (!app->awake) {
        app->awake = true;
        app->storage_mode = false;
        gl_motion_init(&app->motion, GL_IMU_ACCEL_G_PER_LSB_2G, GL_IMU_GYRO_RAD_S_PER_LSB_1000);
        app->last_sample_ms = now;
        if (!app->imu_ok) {
            imu_recover_(app, now); /* every wake-up is a chance to get it back */
        } else {
            const gl_status_t st = gl_imu_start_measure(&app->imu);
            if (st != GL_OK) {
                imu_failed_(app, st, now);
            }
        }
        app->next_batt_ms = now; /* measure the battery at once */
        app->batt_low_sent = false;
    }
    irq_setup_(app);
}

static void enter_sleep_(gl_app_t *app)
{
    const uint32_t now = gl_hal_tick_ms();
    abort_read_(app);
    app->zero.active = false;
    app->six.active = false;
    gl_motion_spin_end(&app->motion);
    gl_lcd_off(&app->lcd);
    if (app->usb_on) {
        usb_stop_(app);
    }
    /* Rev C2: the charger is on by default in hardware and CHG_INHIBIT can
     * only stop it.  A sleeping MCU must not leave it stopped: without VBUS
     * the pin is released here, so that the next cradle charges the cell
     * even if this firmware never wakes again.  (With VBUS present the
     * device does not sleep: see the end of this function; the gate keeps
     * whatever it decided.) */
    gl_power_poll_pins(&app->power);
    if (!app->power.vbus) {
        gl_power_charge_release(&app->power);
        app->power.chg_reason = (uint8_t)GL_CHG_NO_VBUS;
    }
    app->awake = false;
    app->sleep_since_ms = now;
    app->sleep_ticks = 0;
    /* A cell that is nearly empty is left alone: IMU off (no wake-on-motion,
     * only the cradle wakes the device), so that the sleep drain does not
     * take it to its protection cut-off (GL_PROV_BATT_STORAGE_MV). */
    app->storage_mode = app->power.storage && !app->power.vbus;
    if (app->storage_mode) {
        gl_app_log_event(app, (uint16_t)GL_APP_LOGEV_STORAGE, (int32_t)app->power.batt_mv);
        if (gl_imu_stop(&app->imu) != GL_OK) {
            app->imu_ok = false; /* retried at the housekeeping wake-ups */
        }
    } else if (!app->imu_ok) {
        imu_recover_(app, now);
    } else {
        const gl_status_t st =
            gl_imu_start_wake_on_motion(&app->imu, (uint16_t)GL_PROV_IMU_WAKE_THRESHOLD_MG);
        if (st != GL_OK) {
            /* without the wake-up interrupt the device would never wake */
            imu_failed_(app, st, now);
        }
    }
    if (app->flash_ok) {
        (void)gl_mx25r_sleep(&app->flash);
    }
    irq_setup_(app);
    /* The device does not sleep in the cradle: whatever brought the UI here
     * (an error, the low-battery screen), VBUS takes it back to the cradle
     * state, where charging is supervised. */
    if (app->power.vbus) {
        gl_app_post(app, GL_EV_USB_ATTACH, 0);
    }
}

/* ======================================================================= */
/* power                                                                    */
/* ======================================================================= */

/* A VBUS or charger-STAT edge.  The HARDWARE rules are applied here, at
 * once and whatever the UI is doing.  With VBUS gone, USB is stopped (the
 * USB-supply-valid bit must not stay set with VDDUSB unpowered) and
 * CHG_INHIBIT is released.  With VBUS there, the charger has ALREADY
 * started by itself (rev C2): the cell temperature is measured in this very
 * loop pass and the charge is stopped if it must be.  What the UI is told
 * is debounced. */
static void vbus_edge_(gl_app_t *app, uint32_t now)
{
    gl_power_poll_pins(&app->power);
    if (!app->power.vbus) {
        if (app->usb_on) {
            usb_stop_(app);
        }
        charge_gate_(app, now); /* no VBUS: releases the pin */
    } else {
        charge_supervise_(app, now);
    }
    app->vbus_pending = true;
    app->vbus_settle_ms = now + GL_APP_VBUS_DEBOUNCE_MS;
    if (app->ui.state == (uint8_t)GL_UI_CRADLE_USB) {
        app->redraw = true;
    }
}

/* The VBUS level has been stable for the debounce time: tell the UI. */
static void vbus_settled_(gl_app_t *app, uint32_t now)
{
    app->vbus_pending = false;
    gl_power_poll_pins(&app->power);
    if (app->power.vbus != app->ui.usb) {
        gl_app_post(app, app->power.vbus ? GL_EV_USB_ATTACH : GL_EV_USB_DETACH, 0);
    } else if (app->power.vbus && app->ui.state == (uint8_t)GL_UI_CRADLE_USB && !app->usb_on) {
        usb_start_(app); /* VBUS bounced: USB was stopped at the first low */
    }
    if (!app->power.vbus && app->usb_on) {
        usb_stop_(app);
    }
    charge_gate_(app, now);
    if (app->ui.state == (uint8_t)GL_UI_CRADLE_USB) {
        app->redraw = true;
    }
}

static void battery_service_(gl_app_t *app, uint32_t now)
{
    if ((int32_t)(now - app->next_batt_ms) < 0) {
        return;
    }
    if (app->capture_active || app->tilt_active) {
        return; /* not while the camera rail loads the cell or a read runs */
    }
    app->next_batt_ms = now + GL_APP_BATT_PERIOD_MS;
    gl_power_poll_pins(&app->power);
    if (gl_power_measure(&app->power) != GL_OK) {
        app->last_error = (uint16_t)GL_ERR_IO;
    }
    app->cell_seen = true; /* gl_power_measure() reads both temperatures too */
    app->cell_temp_ms = now;
    app->mcu_temp_ms = now;
    app->next_chg_ms = now + GL_APP_CHG_TEMP_PERIOD_MS;
    temp_refresh_(app, now);
    charge_gate_(app, now);
    /* Below the LOW threshold the battery symbol on the screens shows it;
     * the device keeps working.  Below CRITICAL it shows the low-battery
     * screen and goes to sleep (the UI's BATT_LOW event): no camera read is
     * started from a cell that the 90 mA camera rail could brown out. */
    if (app->power.critical && !app->power.vbus && !app->batt_low_sent) {
        app->batt_low_sent = true;
        gl_app_post(app, GL_EV_BATT_LOW, 0);
    }
    if (app->ui.state == (uint8_t)GL_UI_CRADLE_USB) {
        app->redraw = true;
    }
}

/* ======================================================================= */
/* tilt                                                                     */
/* ======================================================================= */

/* Turn the still blocks accumulated in the motion averager into a slope
 * reading (temperature-compensated, calibrated, zeroing bias NOT removed). */
static gl_status_t tilt_measure_(gl_app_t *app, gl_vec2_t *slope_raw, gl_vec3_t *up,
                                 gl_vec3_t *gyro_bias)
{
    gl_tilt_mean_t mean;
    gl_vec3_t acal;
    float temp = app->cal_tilt.t0_c;
    gl_status_t st = gl_tilt_avg_result(&app->motion.avg, &mean);
    if (st != GL_OK) {
        return st;
    }
    temp_refresh_(app, gl_hal_tick_ms());
    if (app->temp_valid) {
        temp = app->temp_c;
    }
    acal = gl_tilt_apply_cal(&app->cal_tilt, mean.accel_g, temp);
    st = gl_tilt_slope(acal, slope_raw);
    if (st != GL_OK) {
        return st;
    }
    *up = gl_vec3_unit(acal);
    *gyro_bias = mean.gyro_rad_s;
    return GL_OK;
}

/* Experimental grain reading (only when enabled in the settings; ships
 * disabled).  Blocks for about 150 ms; the IMU is compared before and after
 * as the motion verdict. */
/* One raw grain measurement (388 bytes), kept off the stack. */
static gl_grain_raw_t grain_raw_;

static void grain_read_(gl_app_t *app)
{
    gl_grain_raw_t *const raw_p = &grain_raw_;
    gl_grain_reading_t rd;
    gl_imu_raw_t before, after;
    bool moved = true;

    app->grain_valid = false;
    if (app->settings.grain_enable == 0u) {
        return;
    }
    if (gl_imu_read(&app->imu, &before) != GL_OK ||
        gl_grain_fe_measure(raw_p, GL_GRAIN_MAX_CYCLES) != GL_OK) {
        return;
    }
    if (gl_imu_read(&app->imu, &after) == GL_OK) {
        const float k = GL_IMU_ACCEL_G_PER_LSB_2G;
        moved = fabsf((float)(after.ax - before.ax) * k) > 0.02f ||
                fabsf((float)(after.ay - before.ay) * k) > 0.02f ||
                fabsf((float)(after.az - before.az) * k) > 0.02f;
    }
    raw_p->motion = moved;
    if (gl_grain_process(raw_p, &app->cal_grain, &rd) == GL_OK && rd.valid) {
        app->grain_valid = true;
        app->grain_modulation = rd.red.modulation;
        app->grain_azimuth_rad = rd.red.azimuth_rad;
    }
}

static void tilt_start_(gl_app_t *app)
{
    gl_tilt_avg_reset(&app->motion.avg);
    app->tilt_active = true;
    gl_motion_set_strict(&app->motion, true); /* any movement now aborts the read */
}

/* The 1 s average of a read is complete. */
static void tilt_finish_(gl_app_t *app)
{
    gl_vec2_t slope_raw;
    gl_vec3_t up, gyro_bias;
    const gl_status_t st = tilt_measure_(app, &slope_raw, &up, &gyro_bias);

    app->tilt_active = false;
    if (st != GL_OK) {
        app->last_error = (uint16_t)st;
        gl_app_post(app, GL_EV_TILT_FAIL, (int32_t)st);
        return;
    }
    if (app->ui.read_kind == (uint8_t)GL_READ_PRECISION) {
        /* the re-read after the spin: combined with the first one in solve_() */
        app->reread_slope_raw = slope_raw;
    } else {
        memset(&app->cur, 0, sizeof(app->cur));
        app->cur.tilt_valid = true;
        app->cur.up = up;
        app->cur.gyro_bias = gyro_bias;
        app->cur.slope_raw = slope_raw;
        app->cur.slope.x = slope_raw.x - app->cal_tilt.flip_bias_x;
        app->cur.slope.y = slope_raw.y - app->cal_tilt.flip_bias_y;
        app->cur.temp_c = app->temp_c;
        grain_read_(app);
    }
    gl_app_post(app, GL_EV_TILT_DONE, 0);
}

/* ======================================================================= */
/* capture                                                                  */
/* ======================================================================= */

static void capture_start_(gl_app_t *app)
{
    gl_status_t st;
    if (app->power.critical && !app->power.vbus) {
        /* the camera rail draws about 90 mA from a very small cell */
        gl_app_post(app, GL_EV_BATT_LOW, 0);
        return;
    }
    app->read_id++;
    clock_(app, true); /* the vision of a read is about 145 million instructions */
    st = gl_read_start(&app->read, app->cur.up, GL_APP_LRRL_REPEATS);
    if (st != GL_OK) {
        clock_(app, false);
        app->last_error = (uint16_t)st;
        gl_app_log_event(app, (uint16_t)GL_APP_LOGEV_FAULT, (int32_t)st);
        gl_app_post(app, GL_EV_CAPTURE_FAIL, (int32_t)st);
        return;
    }
    app->capture_active = true;
    irq_setup_(app);
}

/* The left camera measured the flagstick (with or without a disparity).
 *
 * The application's own range fusion (core/gl_range) still runs here, but
 * NOT on the way to the aim: it learns the stick height of the course and
 * fills diagnostic fields.  The number shown and the number solved with are
 * the estimator's (build_measurement_, solve_). */
static void flag_measured_(gl_app_t *app)
{
    const gl_read_result_t *res = &app->read.result;
    gl_app_read_t *c = &app->cur;
    gl_range_input_t in;

    c->flag_found = true;
    c->bearing_valid = true;
    c->bearing_rad = res->angles.bearing_rad;
    c->base_elev_rad = res->angles.base_elev_rad;
    c->top_elev_rad = res->angles.top_elev_rad;
    c->top_valid = res->angles.top_valid;
    c->base = res->angles.base;
    c->tier = res->tier;
    c->ambiguous = res->ambiguous;
    /* GL_READ_TIER_LEFT: no disparity */
    c->disparity_px = res->stick_found ? res->disp.disparity_px : 0.0f;
    c->disparity_sigma_px = res->stick_found ? res->disp.sigma_px : 0.0f;

    memset(&in, 0, sizeof(in));
    in.f_px = GL_CFG_CAM_F_PX;
    in.baseline_m = GL_CFG_CAM_BASELINE_M;
    in.have_stereo = res->stick_found;
    in.disparity_px = c->disparity_px;
    in.disparity_sigma_px = c->disparity_sigma_px; /* noise + static + calibration */
    in.cos_bearing = cosf(c->bearing_rad);
    in.have_height = res->stick_left.top_in_frame;
    in.top_in_clutter = res->stick_left.top_in_clutter; /* a flag over the tip: not for ranging */
    /* For LEARNING THE STICK HEIGHT the lowest visible point counts as the
     * base also when the stick ends at the turf horizon: on a flat green the
     * base is then within (lens height / distance) of it, and a crown hides
     * centimetres of a 1.96 m stick.  The elevation uncertainty is widened
     * instead.  (The estimator gets the strict classification.) */
    in.base_visible = (res->angles.base != (uint8_t)GL_VIS_BASE_UNKNOWN);
    in.tan_top = tanf(res->angles.top_elev_rad);
    in.tan_base = tanf(res->angles.base_elev_rad);
    /* the read's own figure for the lowest point (0.5 row and more when it
     * was placed at the turf edge) on top of the top end's */
    in.elev_sigma_rad = sqrtf(GL_APP_ELEV_SIGMA_ROWS * GL_APP_ELEV_SIGMA_ROWS +
                              res->bottom_sigma_rows * res->bottom_sigma_rows) / GL_CFG_CAM_F_PX;
    c->range_valid = (gl_range_fuse(&in, &app->stick_height, &c->range) == GL_OK);
    if (gl_stick_height_learn(&app->stick_height, &in)) {
        uint8_t blob[GL_STICK_HEIGHT_BLOB_LEN];
        gl_stick_height_encode(&app->stick_height, blob);
        (void)gl_app_store_put(app, (uint8_t)GL_STORE_ID_COURSE, blob, sizeof(blob));
    }
}

static void capture_step_(gl_app_t *app)
{
    const uint32_t progress = app->read.progress;
    const gl_status_t st = gl_read_step(&app->read);
    if (st == GL_ERR_BUSY) {
        if (app->read.progress != progress) {
            /* The UI's limit on the CAPTURE state is a limit on the time
             * WITHOUT PROGRESS, not on the whole sequence: how long that
             * takes depends on the vision's run time on the target, which is
             * not known yet (measured cost: README).  The sequence is still
             * bounded: every strip capture has its own time-out in the
             * driver, every analysis step is a bounded computation and the
             * number of steps is fixed. */
            gl_ui_keepalive(&app->ui, gl_hal_tick_ms());
            gl_hal_watchdog_kick();
        }
        return;
    }
    /* finished one way or another: the camera rail is off */
    app->capture_active = false;
    gl_motion_set_strict(&app->motion, false);
    irq_setup_(app);
    if (st == GL_OK) {
        /* The flagstick was measured by the left camera at least.  A read
         * without a disparity (GL_READ_TIER_LEFT) is NOT turned into "no
         * flag" any more: the estimator keeps its bearing and takes the
         * distance from the stick's angular height if it can, else from the
         * dial ("flag found, range not available": gl_estimate_t.range_missing). */
        flag_measured_(app);
        gl_app_post(app, GL_EV_CAPTURE_DONE, 0);
    } else if (st == GL_ERR_NO_STICK) {
        app->cur.flag_found = false;
        app->cur.bearing_valid = false; /* a band-only bearing is logged, not aimed at */
        gl_app_post(app, GL_EV_CAPTURE_NO_STICK, 0);
    } else {
        app->last_error = (uint16_t)st;
        gl_app_log_event(app, (uint16_t)GL_APP_LOGEV_FAULT, (int32_t)st);
        gl_app_post(app, GL_EV_CAPTURE_FAIL, (int32_t)st);
    }
}

/* ======================================================================= */
/* solve, result screen, log                                                */
/* ======================================================================= */

/*
 * The current read as the estimator wants it (device frame = read frame).
 *
 * THIS IS THE ONE PLACE where firmware quantities become solver inputs, and
 * it follows one rule: GATE, DO NOT SYNTHESISE.  What was not measured, or
 * is not significant, is marked "not available"; nothing is passed that the
 * cameras did not measure.
 *
 *   disparity      only from a stereo pair (GL_READ_TIER_STEREO) and only if
 *                  it is GL_RANGE_MIN_DISPARITY_SNR sigmas above zero; else
 *                  not-a-number.  A left-camera-only read is therefore "flag
 *                  found, range not available" unless top and base of the
 *                  stick are visible (the estimator then ranges from the
 *                  angular height itself).
 *   stick top      visible only if in the frame and not in clutter.
 *   stick base     the strict classification (followed into the turf).
 *   dialled dist.  always handed over; the estimator uses it only when the
 *                  cameras give no range.
 *
 * ONE range fusion feeds the aim: the estimator's (gl_solver_fuse_range, the
 * reference's fuse_range).  It is also what refers the bearing to the ball
 * here: the bearing was measured by the left camera, 10 mm beside the
 * marker's axis and 28.7 mm behind the ball (3.4 mrad at 3 m).
 */
static void build_measurement_(const gl_app_t *app, gl_measurements_t *m)
{
    const gl_app_read_t *c = &app->cur;
    const gl_read_result_t *res = &app->read.result;
    const gl_vec2_t dev = gl_tilt_slope_to_device(c->slope);
    const float dialled = gl_settings_manual_distance_m(&app->settings);
    gl_grain_est_t grain;

    gl_solver_measurements_init(m);
    m->tilt_x = dev.x;
    m->tilt_y = dev.y;
    m->tilt_reads = c->precision ? 2u : 1u;
    m->stimp_ft = gl_settings_stimp_ft(&app->settings);
    m->stick_height_est_m = app->stick_height.height_m;
    m->stick_height_rel_sigma =
        (app->stick_height.height_m > 0.0f) ? (app->stick_height.sigma_m / app->stick_height.height_m)
                                            : GL_PROV_STICK_HEIGHT_REL_SIGMA;
    gl_grain_estimate(&app->settings, &app->cal_grain, c->slope, app->grain_valid ? 1u : 0u,
                      app->grain_modulation, app->grain_azimuth_rad, &grain);
    m->grain_kappa = grain.kappa_long;
    m->grain_azimuth_rad = grain.azimuth_rad;
    if (dialled > 0.0f) {
        m->user_distance_m = dialled;
    }
    if (c->flag_found) {
        gl_range_estimate_t rng;
        float d_ref;

        m->flag_found = true;
        m->flag_bearing_rad = c->bearing_rad; /* as the left camera saw it, for now */
        if (c->tier >= (uint8_t)GL_READ_TIER_STEREO && c->disparity_sigma_px > 0.0f &&
            c->disparity_px >= GL_RANGE_MIN_DISPARITY_SNR * c->disparity_sigma_px) {
            /* the reference's disparity is f B / DISTANCE; ours measures depth */
            m->flag_disparity_px = c->disparity_px * cosf(c->bearing_rad);
        }
        m->flag_low_elev_rad = c->base_elev_rad;
        m->flag_base_visible = (c->base == (uint8_t)GL_VIS_BASE_VISIBLE);
        m->flag_top_visible = c->top_valid;
        m->flag_top_elev_rad = c->top_elev_rad;
        m->n_horizon = (res->n_horizon <= GL_SOLVER_MAX_HORIZON) ? res->n_horizon
                                                                  : (uint8_t)GL_SOLVER_MAX_HORIZON;
        for (unsigned i = 0; i < m->n_horizon; i++) {
            m->horizon_az_rad[i] = res->horizon_az_rad[i];
            m->horizon_elev_rad[i] = res->horizon_elev_rad[i];
        }
        /* Refer the bearing to the ball with the distance THE ESTIMATOR will
         * use: its own fusion of what has just been gated, else the dialled
         * distance, else its default.  (Pure geometry; the correction is
         * 10 mm / distance, so the choice among the three hardly matters.) */
        gl_solver_fuse_range(m, &rng);
        if (isfinite(rng.distance_m) && rng.distance_m > 0.0f) {
            d_ref = rng.distance_m;
        } else {
            d_ref = (dialled > 0.0f) ? dialled : GL_APP_DEFAULT_DISTANCE_M;
        }
        m->flag_bearing_rad = gl_range_from_ball_at(d_ref, c->bearing_rad,
                                                    GL_CFG_CAM_LEFT_X_MM * 0.001f,
                                                    GL_CFG_CAM_LEFT_Y_MM * 0.001f).bearing_rad;
    }
}

/* The estimator's range for one stored placement, or a negative number. */
static float drop_range_(const gl_measurements_t *m)
{
    gl_range_estimate_t r;
    gl_solver_fuse_range(m, &r);
    return (m->flag_found && isfinite(r.distance_m) && r.distance_m > 0.0f) ? r.distance_m : -1.0f;
}

/* Append the current read to the Survey: its solver input, and a summary
 * record for diagnostics whose range is the ESTIMATOR's for that drop. */
static void survey_store_(gl_app_t *app)
{
    gl_app_read_t *c = &app->cur;
    gl_survey_drop_t d;
    float range;

    if (app->survey.count >= GL_SURVEY_MAX_DROPS || c->stored) {
        return;
    }
    build_measurement_(app, &app->meas[app->survey.count]);
    range = drop_range_(&app->meas[app->survey.count]);
    memset(&d, 0, sizeof(d));
    d.slope = c->slope;
    d.bearing_rad = c->bearing_rad;
    d.base_elev_rad = c->base_elev_rad;
    if (c->flag_found) {
        d.flags |= (uint8_t)GL_DROP_FLAG_STICK;
    }
    if (range > 0.0f) {
        d.range_m = range;
        d.range_sigma_m = range * range * GL_APP_EST_SIGMA_DISP_PX /
                          (GL_CFG_CAM_F_PX * GL_CFG_CAM_BASELINE_M);
    }
    if (c->base == (uint8_t)GL_VIS_BASE_VISIBLE) {
        d.flags |= (uint8_t)GL_DROP_FLAG_BASE_VISIBLE;
    }
    if (c->precision) {
        d.flags |= (uint8_t)GL_DROP_FLAG_PRECISION;
    }
    /* (gl_survey_add() refuses a drop without a range; since phase 2 such a
     * drop is kept as a placement and the estimator ignores it, as the
     * reference does) */
    app->survey.drop[app->survey.count++] = d;
    c->stored = true;
}

/*
 * Which stored drop is the ball, and does the marker lie there now?
 *
 * The estimator takes the Survey "ball first": the drop FARTHEST from the
 * flagstick defines the putt, the others are samples along the line.  The
 * marker lies wherever the golfer put it down last, and the aim line on the
 * screen means something only if that is the ball.  So:
 *   - the ball is the stored drop with the largest estimator range;
 *   - if the newest drop is that one, or is within
 *     GL_APP_SURVEY_AT_BALL_FRACTION of its range (the golfer came back to
 *     the ball; two drops this close are not two stations), the newest drop
 *     IS taken as the ball, and the result is in its frame: the line can be
 *     drawn;
 *   - otherwise the marker lies somewhere along the line: the numbers are
 *     shown, no line (gl_ui_view_t.line_here false);
 *   - if no drop was ranged, the newest one is a plain tilt-only read.
 */
static unsigned survey_ball_(const gl_app_t *app, bool *at_ball)
{
    const unsigned n = app->survey.count;
    float far = -1.0f, newest = -1.0f;
    unsigned ball = 0;

    for (unsigned i = 0; i < n; i++) {
        const float r = drop_range_(&app->meas[i]);
        if (r > far) {
            far = r;
            ball = i;
        }
        if (i + 1u == n) {
            newest = r;
        }
    }
    if (!(far > 0.0f) || newest >= GL_APP_SURVEY_AT_BALL_FRACTION * far) {
        *at_ball = true;
        return n - 1u;
    }
    *at_ball = false;
    return ball;
}

/*
 * The confidence SHOWN.  The estimator's own score knows the tilt readings,
 * the distance and the flags of gl_estimate_t; it cannot know how the
 * cameras came by their numbers.  The rule (each factor multiplies):
 *
 *   x 0.6   the flagstick was measured by the left camera only
 *           (GL_READ_TIER_LEFT): a line that was never checked against a
 *           disparity is weaker evidence of a flagstick
 *   x 0.6   ambiguous: another line in view also passed as a flagstick
 *   x s     the read's own disparity uncertainty against the 0.08 px the
 *           estimator assumes: s = 0.08 / sigma, limited to 0.5 .. 1 (a
 *           disparity read behind a person, 0.34 px, halves the score; the
 *           usual 0.05 px changes nothing)
 *   x 0.7   the fit stopped on its iteration limit
 * and two caps for an aim that is not a solution:
 *   <= 0.2  aim_source 2, the estimator's best effort (at most one box)
 *   =  0    aim_source 3, straight at the hole for want of anything
 * A Survey result takes the camera factors of the read at the marker's
 * present placement.
 */
static float shown_confidence_(const gl_app_t *app)
{
    const gl_app_read_t *c = &app->cur;
    const gl_estimate_t *e = &app->est;
    float conf = e->confidence;

    if (c->flag_found) {
        if (c->tier == (uint8_t)GL_READ_TIER_LEFT) {
            conf *= GL_APP_CONF_ONE_CAMERA;
        }
        if (c->ambiguous) {
            conf *= GL_APP_CONF_AMBIGUOUS;
        }
        if (c->tier >= (uint8_t)GL_READ_TIER_STEREO && c->disparity_sigma_px > GL_APP_EST_SIGMA_DISP_PX) {
            conf *= gl_clampf(GL_APP_EST_SIGMA_DISP_PX / c->disparity_sigma_px, 0.5f, 1.0f);
        }
    }
    if (!e->fit_converged) {
        conf *= GL_APP_CONF_FIT_NOT_DONE;
    }
    if (e->aim_source == (uint8_t)GL_AIM_STRAIGHT) {
        conf = 0.0f;
    } else if (e->aim_source == (uint8_t)GL_AIM_BEST_EFFORT && conf > GL_APP_CONF_BEST_EFFORT_MAX) {
        conf = GL_APP_CONF_BEST_EFFORT_MAX;
    }
    return gl_clampf(conf, 0.0f, 1.0f);
}

/* The one plain message of a result: the most serious condition wins. */
static uint8_t note_(const gl_app_t *app)
{
    const gl_app_read_t *c = &app->cur;
    const gl_estimate_t *e = &app->est;

    if (e->aim_source == (uint8_t)GL_AIM_STRAIGHT) {
        return (uint8_t)GL_UI_NOTE_NO_SOLUTION;
    }
    if (e->aim_source == (uint8_t)GL_AIM_BEST_EFFORT) {
        return (uint8_t)GL_UI_NOTE_NOT_SOLVED;
    }
    if (e->flag_missing) {
        return (uint8_t)GL_UI_NOTE_NO_FLAG;
    }
    if (e->range_missing) {
        return (uint8_t)GL_UI_NOTE_NO_RANGE;
    }
    if (e->aim_source == (uint8_t)GL_AIM_FROM_PLANE) {
        return (uint8_t)GL_UI_NOTE_APPROX;
    }
    if (e->solve_status == (uint8_t)GL_SOLVE_PACE_LIMITED) {
        return (uint8_t)GL_UI_NOTE_PACE;
    }
    if (!e->fit_converged) {
        return (uint8_t)GL_UI_NOTE_FIT;
    }
    if (c->flag_found && c->tier == (uint8_t)GL_READ_TIER_LEFT) {
        return (uint8_t)GL_UI_NOTE_ONE_CAMERA;
    }
    if (c->flag_found && c->ambiguous) {
        return (uint8_t)GL_UI_NOTE_AMBIGUOUS;
    }
    return (uint8_t)GL_UI_NOTE_NONE;
}

/*
 * gl_estimate_t -> what the screen shows.
 *
 * FRAMES.  The estimate is in the reference's DEVICE frame of the placement
 * at the ball: +x out of the visor, +y left, azimuths counter-clockwise from
 * +x.  The firmware's angles are counter-clockwise from marker FORWARD (out
 * of the visor), so a device-frame azimuth IS a firmware angle - no sign
 * change, no offset.  The screen measures the same way from "up" (gl_gfx.h:
 * angle 0 up, +90 degrees left), and "up" on the screen is marker forward
 * for a golfer standing behind the marker and looking at the hole.  Hence:
 *   aim_azimuth_device > bearing  <=>  phi > 0  <=>  aim LEFT of the hole
 *   <=>  the line leans to the left towards the top of the screen and its
 *   backward extension crosses the screen to the RIGHT of the centre
 *   <=>  break label "<n CUP"  <=>  the ground rises to the left.
 * view_yaw_rad takes the read frame to the marker's present frame (the
 * 180-degree spin of a Precision Read).  tests/test_e2e_putt.c checks every
 * link of this chain with numbers, from the scene to the pixels.
 */
static void compose_view_(gl_app_t *app)
{
    const gl_app_read_t *c = &app->cur;
    const gl_estimate_t *e = &app->est;
    gl_ui_view_t *v = &app->view;
    const bool dialled = gl_settings_manual_distance_m(&app->settings) > 0.0f;
    const bool assumed = e->flag_missing || e->range_missing;

    v->have_result = true;
    /* a solution of the putt on the estimated surface (patch or its secant
     * plane); anything else is drawn as a tentative line */
    v->solved = (e->aim_source == (uint8_t)GL_AIM_FROM_PATCH ||
                 e->aim_source == (uint8_t)GL_AIM_FROM_PLANE);
    v->line_here = app->line_here;
    v->flag_found = !e->flag_missing;
    v->precision = c->precision;
    v->distance_assumed = assumed;
    /* the estimator's numbers; a distance nobody measured or dialled (the
     * estimator's 3 m default) is not shown as if it were known */
    v->distance_m = (assumed && !dialled) ? 0.0f : e->distance_m;
    v->plays_like_m = (assumed && !dialled) ? 0.0f : e->plays_like_m;
    v->slope_pct = e->slope_pct;
    v->break_cups = e->break_cups;
    v->confidence = shown_confidence_(app);
    v->note = note_(app);
    v->drop = (c->stored && app->survey.count > 0u) ? app->survey.count : 0u;
    /* from the read frame to the marker's present frame */
    v->aim_rad = gl_wrap_pi(e->aim_azimuth_device_rad - c->view_yaw_rad);
    v->fall_line_rad = gl_wrap_pi(e->fall_line_azimuth_device_rad - c->view_yaw_rad);
    v->ball_az_rad = gl_wrap_pi(-c->view_yaw_rad);
}

void gl_app_recompose_view(gl_app_t *app)
{
    compose_view_(app);
    app->redraw = true;
}

static uint8_t pct_(float x)
{
    return (uint8_t)gl_roundi(100.0f * gl_clampf(x, 0.0f, 1.0f));
}

static void log_read_(gl_app_t *app)
{
    const gl_app_read_t *c = &app->cur;
    const gl_read_result_t *res = &app->read.result;
    const gl_estimate_t *e = &app->est;
    gl_log_read_t r;
    uint8_t buf[GL_LOG_READ_LEN];

    if (!app->storage_ok) {
        return;
    }
    memset(&r, 0, sizeof(r));
    r.rtc_s = gl_hal_rtc_seconds();
    r.read_id = app->read_id;
    r.flags = (uint8_t)((c->flag_found ? GL_LOG_READ_FLAG_STICK_FOUND : 0u) |
                        ((c->flag_found && c->base == (uint8_t)GL_VIS_BASE_VISIBLE)
                             ? GL_LOG_READ_FLAG_BASE_VISIBLE : 0u) |
                        ((c->flag_found && c->top_valid) ? GL_LOG_READ_FLAG_TOP_VISIBLE : 0u) |
                        ((e->flag_missing || e->range_missing) ? GL_LOG_READ_FLAG_MANUAL_RANGE : 0u) |
                        (c->precision ? GL_LOG_READ_FLAG_PRECISION : 0u) |
                        ((app->survey.count > 0u) ? GL_LOG_READ_FLAG_SURVEY : 0u) |
                        (app->grain_valid ? GL_LOG_READ_FLAG_GRAIN_VALID : 0u) |
                        ((c->flag_found && res->quality.sun) ? GL_LOG_READ_FLAG_SUN : 0u));
    r.drop_index = app->survey.count;
    r.temp_c_x100 = (int16_t)gl_roundi(gl_clampf(c->temp_c, -300.0f, 300.0f) * 100.0f);
    r.batt_mv = app->power.batt_mv;
    r.slope_x = c->slope.x;
    r.slope_y = c->slope.y;
    r.aim_rad = app->view.aim_rad;
    r.stimp_x2 = app->settings.stimp_x2;
    r.confidence_pct = pct_(app->view.confidence);
    r.solver_status = e->solve_status;
    r.stick_height_m = app->stick_height.height_m;
    if (c->flag_found) {
        r.bearing_rad = c->bearing_rad;
        r.disparity_px = c->disparity_px;
        r.disparity_sigma_px = c->disparity_sigma_px;
        r.base_elev_rad = c->base_elev_rad;
        r.top_elev_rad = c->top_valid ? c->top_elev_rad : 0.0f;
        r.rows_used_pct = pct_(res->quality.rows_used_frac);
        r.line_contrast = (uint8_t)gl_clampi(gl_roundi(res->quality.line_contrast), 0, 255);
        r.sharp_match_pct = pct_(res->quality.sharpness_match);
        r.saturation_pct = pct_(res->quality.sat_fraction);
        r.n_repeats = res->groups_ok;
    }
    /* the distance solved with and shown: the estimator's (0 sigma = unknown) */
    r.range_m = e->distance_m;
    r.range_sigma_m = isfinite(e->distance_sigma_m) ? e->distance_sigma_m : 0.0f;
    r.v0_mps = e->v0_mps;
    r.aim_offset_m = e->break_m;
    gl_log_read_encode(&r, buf);
    if (gl_log_append(&app->log, (uint8_t)GL_LOG_REC_READ, 0, buf, sizeof(buf), NULL) != GL_OK) {
        app->last_error = (uint16_t)GL_ERR_IO;
    }
    /* what the read record has no room for: the estimator's flags and cost
     * (layout: GL_APP_ESTFLAG_* in gl_app_cfg.h) */
    gl_app_log_event(app, (uint16_t)GL_APP_LOGEV_ESTIMATE,
                     (int32_t)(((uint32_t)e->aim_source & 3u) |
                               (((uint32_t)e->solve_status & 7u) << GL_APP_ESTFLAG_STATUS_SHIFT) |
                               (e->fit_converged ? GL_APP_ESTFLAG_FIT_CONVERGED : 0u) |
                               (e->base_hidden ? GL_APP_ESTFLAG_BASE_HIDDEN : 0u) |
                               (e->flag_missing ? GL_APP_ESTFLAG_FLAG_MISSING : 0u) |
                               (e->range_missing ? GL_APP_ESTFLAG_RANGE_MISSING : 0u) |
                               (e->poor_horizon ? GL_APP_ESTFLAG_POOR_HORIZON : 0u) |
                               (((uint32_t)app->solve_opt.method & 3u) << GL_APP_ESTFLAG_METHOD_SHIFT) |
                               (((uint32_t)c->tier & 3u) << GL_APP_ESTFLAG_TIER_SHIFT) |
                               (c->ambiguous ? GL_APP_ESTFLAG_AMBIGUOUS : 0u) |
                               (app->line_here ? GL_APP_ESTFLAG_LINE_HERE : 0u) |
                               (((uint32_t)((e->n_rolls < 0x7FFFu) ? e->n_rolls : 0x7FFFu))
                                << GL_APP_ESTFLAG_ROLLS_SHIFT)));
}

static void solve_(gl_app_t *app, bool precision_reread)
{
    gl_app_read_t *c = &app->cur;
    gl_solver_options_t *opt = &app->solve_opt;
    gl_status_t st;

    if (precision_reread) {
        /* Combine the read at the ball with the re-read after the spin.  The
         * gyro has been integrated UP TO NOW, through the re-read (it used to
         * stop when the spin was first seen complete: a marker turned again
         * during the re-read was then combined with the stale angle and the
         * wrong result shown as "2X").  The half-turn test is made again
         * here, on the angle the re-read was really taken at. */
        gl_precision_t p;
        const float yaw = gl_spin_yaw(&app->motion.spin);
        c->precision = false;
        if (gl_spin_is_half_turn(&app->motion.spin) &&
            gl_tilt_precision_combine(app->spin_slope_raw, app->reread_slope_raw, yaw,
                                      &app->cal_tilt, &p) == GL_OK) {
            c->slope = p.slope; /* in the frame of the first read */
            c->precision = true;
        }
        c->view_yaw_rad = yaw; /* where the marker faces now, whatever came of it */
        gl_motion_spin_end(&app->motion);
    }
    /* the solve needs the fast clock as much as the vision does: a typical
     * estimate is 0.3 million instructions, the worst that could be
     * constructed 173 million (README "Solver") */
    clock_(app, true);
    build_measurement_(app, &app->meas_cur);
    gl_solver_default_options(opt);
    opt->past_m = gl_settings_past_m(&app->settings);
    opt->method = app->settings.method; /* B1 by default; B2 is a setting */
    /* the grain reading is not used (gl_solver_default_options) */
    app->solve_drops = 1;
    app->solve_ball = 0;
    app->line_here = true;
    if (c->stored && app->survey.count >= 2u) {
        /* the newest drop is the current read: keep its record in step with
         * what has just been built (a Precision combination changes it) */
        bool at_ball = true;
        app->meas[app->survey.count - 1u] = app->meas_cur;
        app->solve_drops = app->survey.count;
        app->solve_ball = (uint8_t)survey_ball_(app, &at_ball);
        app->line_here = at_ball;
        st = gl_solver_estimate_survey(app->meas, app->solve_drops, app->solve_ball, opt,
                                       &app->solver_work, &app->est);
    } else {
        st = gl_solver_estimate(&app->meas_cur, opt, &app->solver_work, &app->est);
    }
    gl_hal_trace(GL_TRACE_SOLVE, (st == GL_OK) ? app->est.n_steps : 0u);
    clock_(app, false);
    app->solver_status = st;
    if (st != GL_OK) {
        /* GL_ERR_PARAM / GL_ERR_RANGE: an input no placement should produce,
         * or arithmetic that left the finite range.  (The solver's own
         * fallbacks - flag missing, not ranged, secant plane, best iterate -
         * are results: GL_OK with the flags of gl_estimate_t, shown as a
         * message and as reduced confidence.) */
        app->last_error = (uint16_t)st;
        gl_app_post(app, GL_EV_SOLVE_FAIL, (int32_t)st);
        return;
    }
    compose_view_(app);
    log_read_(app);
    app->reads_total++;
    gl_app_post(app, GL_EV_SOLVE_DONE, 0);
}

/* ======================================================================= */
/* zeroing: read, turn 180 degrees in place, read (hard flat surface)       */
/* ======================================================================= */

static void zero_start_(gl_app_t *app)
{
    memset(&app->zero, 0, sizeof(app->zero));
    if (app->power.vbus) {
        /* never in the cradle: it takes the marker one way round only */
        gl_app_post(app, GL_EV_CAL_FAIL, (int32_t)GL_ERR_STATE);
        return;
    }
    app->zero.active = true;
    gl_motion_set_strict(&app->motion, false);
    app->redraw = true;
}

static void zero_fail_(gl_app_t *app, gl_status_t st)
{
    app->zero.active = false;
    app->last_error = (uint16_t)st;
    gl_app_post(app, GL_EV_CAL_FAIL, (int32_t)st);
}

static void zero_sample_(gl_app_t *app, unsigned flags, uint32_t dt_ms, uint32_t now)
{
    gl_app_zero_t *z = &app->zero;
    gl_vec2_t slope_raw;
    gl_vec3_t up, gyro_bias;
    gl_status_t st;

    if (z->step >= 3u) {
        return;
    }
    if (z->step >= 1u) {
        gl_rot_int_add(&z->rot, app->motion.gyro_rad_s, (float)dt_ms * 0.001f);
        if (!z->turned && gl_rot_int_angle(&z->rot) > GL_APP_ZERO_MIN_TURN_RAD) {
            z->turned = true;
        }
    }
    if ((flags & GL_MOTION_F_BLOCK) == 0u) {
        return;
    }
    if (z->step == 1u) {
        if (!(z->turned && (flags & GL_MOTION_F_AT_REST) != 0u)) {
            return;
        }
        z->step = 2;
        z->averaging = false;
        app->redraw = true;
    }
    /* steps 0 and 2: a 1 s read once the marker is at rest */
    if (!z->averaging) {
        if ((flags & GL_MOTION_F_AT_REST) != 0u) {
            gl_tilt_avg_reset(&app->motion.avg);
            z->averaging = true;
        }
        return;
    }
    if ((flags & GL_MOTION_F_BLOCK_STILL) == 0u) {
        z->averaging = false; /* disturbed: take the read again */
        return;
    }
    if (app->motion.avg.blocks_still < GL_APP_TILT_BLOCKS) {
        return;
    }
    z->averaging = false;
    st = tilt_measure_(app, &slope_raw, &up, &gyro_bias);
    if (st != GL_OK) {
        zero_fail_(app, st);
        return;
    }
    if (z->step == 0u) {
        z->m1 = slope_raw;
        z->up1 = up;
        gl_rot_int_start(&z->rot, gyro_bias);
        z->turned = false;
        z->step = 1;
        app->redraw = true;
    } else {
        gl_vec2_t bias, surface;
        uint8_t blob[GL_CAL_TILT_BLOB_LEN];
        const float yaw = gl_rot_int_yaw(&z->rot, z->up1);
        st = gl_tilt_flip_solve(z->m1, slope_raw, yaw, &bias, &surface);
        if (st == GL_OK &&
            (fabsf(bias.x) > GL_APP_ZERO_MAX_BIAS || fabsf(bias.y) > GL_APP_ZERO_MAX_BIAS)) {
            st = GL_ERR_RANGE;
        }
        if (st != GL_OK) {
            zero_fail_(app, st); /* turn not near 180 degrees, or implausible */
            return;
        }
        app->cal_tilt.flip_bias_x = bias.x;
        app->cal_tilt.flip_bias_y = bias.y;
        app->cal_tilt.flip_temp_c = app->temp_valid ? app->temp_c : app->cal_tilt.t0_c;
        app->cal_tilt.flip_time_s = gl_hal_rtc_seconds();
        app->cal_tilt.flags |= (uint8_t)GL_CAL_TILT_FLAG_FLIP;
        gl_cal_tilt_encode(&app->cal_tilt, blob);
        st = gl_app_store_put(app, (uint8_t)GL_STORE_ID_CAL_TILT, blob, sizeof(blob));
        if (st != GL_OK && st != GL_ERR_NOT_FOUND) {
            zero_fail_(app, st);
            return;
        }
        gl_app_log_event(app, (uint16_t)GL_APP_LOGEV_ZEROED,
                         (int32_t)gl_roundi(1.0e6f * sqrtf(bias.x * bias.x + bias.y * bias.y)));
        z->step = 3;
        z->saved_at_ms = now;
        app->redraw = true;
    }
}

/* ======================================================================= */
/* factory calibration procedures (USB START_CAL)                           */
/* ======================================================================= */

gl_status_t gl_app_start_cal(gl_app_t *app, uint8_t procedure, uint8_t arg)
{
    switch (procedure) {
    case GL_CALPROC_ZERO:
        /* the zeroing needs a 180-degree turn on a flat surface; the cradle
         * (the only place with USB) holds the marker one way round */
        return GL_ERR_STATE;
    case GL_CALPROC_SIX_FACE:
        if (!app->imu_ok || !app->awake) {
            return GL_ERR_STATE;
        }
        if (arg < 6u) {
            if (app->six.active) {
                return GL_ERR_BUSY; /* the previous face is still being averaged */
            }
            app->six.face = arg;
            app->six.active = true;
            gl_tilt_avg_reset(&app->motion.avg);
            return GL_OK;
        }
        if (arg == 6u) {
            gl_vec3_t offset;
            gl_mat3_t m;
            uint8_t blob[GL_CAL_TILT_BLOB_LEN];
            gl_status_t st;
            if (app->six.done_mask != 0x3Fu) {
                return GL_ERR_STATE;
            }
            st = gl_tilt_six_face_solve(app->six.meas, &offset, &m);
            gl_app_log_event(app, (uint16_t)GL_APP_LOGEV_SIX_FACE, (int32_t)st);
            if (st != GL_OK) {
                return st;
            }
            app->cal_tilt.offset_g[0] = offset.x;
            app->cal_tilt.offset_g[1] = offset.y;
            app->cal_tilt.offset_g[2] = offset.z;
            app->cal_tilt.m = m;
            if (app->temp_valid) {
                app->cal_tilt.t0_c = app->temp_c;
            }
            app->cal_tilt.flags |= (uint8_t)GL_CAL_TILT_FLAG_FACTORY;
            gl_cal_tilt_encode(&app->cal_tilt, blob);
            app->six.done_mask = 0;
            return gl_app_store_put(app, (uint8_t)GL_STORE_ID_CAL_TILT, blob, sizeof(blob));
        }
        return GL_ERR_PARAM;
    case GL_CALPROC_GRAIN_WHITE: {
        uint8_t blob[GL_CAL_GRAIN_BLOB_LEN];
        gl_status_t st = gl_grain_fe_measure(&grain_raw_, GL_GRAIN_MAX_CYCLES);
        if (st == GL_OK) {
            st = gl_grain_white_reference(&grain_raw_, &app->cal_grain);
        }
        gl_app_log_event(app, (uint16_t)GL_APP_LOGEV_GRAIN_WHITE, (int32_t)st);
        if (st != GL_OK) {
            return st;
        }
        gl_cal_grain_encode(&app->cal_grain, blob);
        return gl_app_store_put(app, (uint8_t)GL_STORE_ID_CAL_GRAIN, blob, sizeof(blob));
    }
    case GL_CALPROC_ABORT:
        app->six.active = false;
        return GL_OK;
    default:
        /* GL_CALPROC_GRAIN_FLOOR (needs readings on turf, outside the cradle)
         * and GL_CALPROC_CAM_HORIZON (needs the factory target) are not
         * implemented in phase 1 */
        return GL_ERR_UNSUPPORTED;
    }
}

/* One block of the six-face average. */
static void six_face_block_(gl_app_t *app, unsigned flags)
{
    gl_tilt_mean_t mean;
    if ((flags & GL_MOTION_F_BLOCK_STILL) == 0u) {
        gl_tilt_avg_reset(&app->motion.avg); /* moved: start this face again */
        return;
    }
    if (app->motion.avg.blocks_still < GL_APP_TILT_BLOCKS) {
        return;
    }
    if (gl_tilt_avg_result(&app->motion.avg, &mean) == GL_OK) {
        app->six.meas[app->six.face] = mean.accel_g; /* RAW: the solve finds offset and matrix */
        app->six.done_mask |= (uint8_t)(1u << app->six.face);
    }
    app->six.active = false;
}

/* ======================================================================= */
/* IMU sample pump                                                          */
/* ======================================================================= */

static void imu_sample_(gl_app_t *app, uint32_t now)
{
    gl_imu_raw_t raw;
    unsigned flags;
    uint32_t dt_ms = (uint32_t)(now - app->last_sample_ms);
    const gl_status_t st = gl_imu_read(&app->imu, &raw);

    if (st != GL_OK) {
        imu_failed_(app, st, now); /* transient until proven otherwise */
        return;
    }
    app->last_sample_ms = now;
    if (dt_ms < 1u) {
        dt_ms = 1u;
    } else if (dt_ms > 100u) {
        dt_ms = 100u; /* the loop was busy (capture start, flash): do not over-integrate */
    }
    flags = gl_motion_sample(&app->motion, &raw, dt_ms, &app->events);
    if (app->tilt_active && (flags & GL_MOTION_F_BLOCK_STILL) != 0u &&
        app->motion.avg.blocks_still >= GL_APP_TILT_BLOCKS) {
        tilt_finish_(app);
    }
    if (app->zero.active) {
        zero_sample_(app, flags, dt_ms, now);
    }
    if (app->six.active && (flags & GL_MOTION_F_BLOCK) != 0u) {
        six_face_block_(app, flags);
    }
    if (app->usb_on) {
        gl_usb_stream_imu(app, &raw);
    }
}

/* ======================================================================= */
/* UI actions                                                               */
/* ======================================================================= */

static void do_actions_(gl_app_t *app, uint32_t a, uint32_t now)
{
    if (a == 0u) {
        return;
    }
    /* things that stop come first, sleep last */
    if ((a & GL_ACT_ABORT_READ) != 0u) {
        abort_read_(app);
    }
    if ((a & GL_ACT_CAL_ABORT) != 0u) {
        app->zero.active = false;
    }
    if ((a & GL_ACT_USB_STOP) != 0u) {
        usb_stop_(app);
    }
    if ((a & GL_ACT_SURVEY_RESET) != 0u) {
        gl_survey_reset(&app->survey);
    }
    if ((a & GL_ACT_NEW_READ) != 0u) {
        app->view.have_result = false;
        gl_motion_spin_end(&app->motion);
    }
    if ((a & GL_ACT_DISPLAY_ON) != 0u) {
        wake_(app, now);
    }
    if ((a & GL_ACT_USB_START) != 0u) {
        usb_start_(app);
    }
    if ((a & GL_ACT_SAVE_SETTINGS) != 0u) {
        (void)gl_app_set_settings(app, &app->ui.edit);
    }
    if ((a & GL_ACT_DIAL_BEGIN) != 0u) {
        int lo = 0, hi = 1; /* the "ZERO" item: NO / YES */
        if (app->ui.item < GL_UI_ITEM_ZERO) {
            gl_settings_item_range((gl_item_t)app->ui.item, &lo, &hi);
        }
        gl_motion_dial_begin(&app->motion, (int)app->ui.dial_value, lo, hi);
    }
    if ((a & GL_ACT_WATCH_STILL) != 0u) {
        gl_motion_watch_still(&app->motion);
    }
    if ((a & GL_ACT_START_TILT) != 0u) {
        tilt_start_(app);
    }
    if ((a & GL_ACT_START_CAPTURE) != 0u) {
        capture_start_(app);
    }
    if ((a & GL_ACT_SURVEY_STORE) != 0u) {
        survey_store_(app);
    }
    if ((a & GL_ACT_START_SOLVE) != 0u) {
        solve_(app, (a & GL_ACT_PRECISION) != 0u);
    }
    if ((a & GL_ACT_ARM_SPIN) != 0u) {
        app->spin_slope_raw = app->cur.slope_raw;
        gl_motion_spin_begin(&app->motion, app->cur.up, app->cur.gyro_bias);
    }
    if ((a & GL_ACT_SPIN_ABANDON) != 0u) {
        /* The Precision spin was not completed (time-out).  The single read
         * is shown again, but the marker may have been turned by any angle
         * meanwhile: the screen is drawn for where it faces NOW. */
        if (app->motion.spin_active && app->view.have_result) {
            app->cur.view_yaw_rad = gl_spin_yaw(&app->motion.spin);
            app->cur.precision = false;
            compose_view_(app);
        }
        gl_motion_spin_end(&app->motion);
    }
    if ((a & GL_ACT_CAL_ZERO_START) != 0u) {
        zero_start_(app);
    }
    if ((a & GL_ACT_REDRAW) != 0u) {
        app->redraw = true;
    }
    if ((a & GL_ACT_ENTER_SLEEP) != 0u) {
        enter_sleep_(app);
    }
}

static void draw_(gl_app_t *app)
{
    app->redraw = false;
    if (!app->lcd.on) {
        return;
    }
    app->view.battery_pct = app->power.percent;
    app->view.charging = app->power.charging;
    app->view.usb_connected = app->usb_on && gl_hal_usb_connected();
    switch ((gl_chg_reason_t)app->power.chg_reason) {
    case GL_CHG_ALLOWED:
    case GL_CHG_NO_VBUS: app->view.chg_blocked = 0u; break;
    case GL_CHG_TOO_COLD: app->view.chg_blocked = 1u; break;
    case GL_CHG_TOO_HOT: app->view.chg_blocked = 2u; break;
    default: app->view.chg_blocked = 3u; break; /* unknown, NTC fault, implausible */
    }
    app->view.cal_step = app->zero.active ? app->zero.step : 0u;
    gl_ui_render(&app->ui, &app->view, &app->gfx);
    gl_hal_trace(GL_TRACE_RENDER, 0u);
    if (gl_lcd_update(&app->lcd, &app->gfx, NULL) != GL_OK) {
        app->last_error = (uint16_t)GL_ERR_IO;
    }
}

/* ======================================================================= */
/* init and main loop                                                       */
/* ======================================================================= */

gl_status_t gl_app_init(gl_app_t *app)
{
    gl_status_t first_err = GL_OK, st;
    uint32_t reset;

    memset(app, 0, sizeof(*app));
    st = gl_hal_init();
    if (st != GL_OK) {
        first_err = st;
    }
    reset = gl_hal_reset_reason();
    gl_event_init(&app->events);

    gl_settings_defaults(&app->settings);
    gl_cal_tilt_defaults(&app->cal_tilt);
    gl_cal_cam_defaults(&app->cal_cam[GL_CAM_LEFT], 0);
    gl_cal_cam_defaults(&app->cal_cam[GL_CAM_RIGHT], 1);
    gl_cal_grain_defaults(&app->cal_grain);
    gl_stick_height_reset(&app->stick_height);

    /* drivers: every one first puts its pins into the safe state */
    gl_ov7692_init(&app->cam, NULL); /* camera rail off, camera-facing pins parked */
    gl_lcd_init(&app->lcd, NULL);
    gl_grain_fe_all_off();
    gl_power_init(&app->power);
    if (app->power.vbus) {
        /* booted in the cradle: the charger is already running (hardware
         * default); measure the cell before anything slower is done */
        charge_supervise_(app, gl_hal_tick_ms());
    }
    gl_gfx_init(&app->gfx);

    st = gl_mx25r_init(&app->flash);
    app->flash_ok = (st == GL_OK);
    if (st != GL_OK && first_err == GL_OK) {
        first_err = st;
    }
    if (app->flash_ok) {
        gl_mx25r_flash_if(&app->flash, &app->flash_if);
        app->storage_ok =
            gl_store_mount(&app->store, &app->flash_if, GL_APP_STORE_BASE, GL_APP_STORE_SECTORS) ==
                GL_OK &&
            gl_log_mount(&app->log, &app->flash_if, GL_APP_LOG_BASE, GL_APP_LOG_SECTORS) == GL_OK;
        if (app->storage_ok) {
            load_store_(app);
        } else if (first_err == GL_OK) {
            first_err = GL_ERR_CORRUPT;
        }
    }
    /* A probe that fails here is retried (imu_recover_): at the first
     * sleep entry below, at every wake-up and every 16 s while asleep. */
    st = gl_imu_init(&app->imu, NULL);
    app->imu_ok = (st == GL_OK);
    if (st != GL_OK) {
        app->imu_fails = 1;
        app->imu_fault_shown = true; /* reported below as the boot error */
        if (first_err == GL_OK) {
            first_err = st;
        }
    }

    gl_read_init(&app->read, &app->cam);
    gl_read_set_cal(&app->read, &app->cal_cam[GL_CAM_LEFT], &app->cal_cam[GL_CAM_RIGHT]);
    gl_read_set_strip_hook(&app->read, strip_hook_, app);
    gl_motion_init(&app->motion, GL_IMU_ACCEL_G_PER_LSB_2G, GL_IMU_GYRO_RAD_S_PER_LSB_1000);
    gl_ui_init(&app->ui, &app->settings, gl_hal_tick_ms());
    gl_usb_bind(app);
    app->solver_status = GL_ERR_STATE; /* no read solved yet */

    gl_app_log_event(app, (uint16_t)GL_APP_LOGEV_BOOT, (int32_t)reset);

    /* asleep: display off, IMU waiting for motion, flash in deep power-down */
    app->awake = true; /* so that enter_sleep_() configures everything once */
    enter_sleep_(app);
    if (first_err != GL_OK) {
        fault_(app, first_err); /* shows the error screen, then sleeps again */
    }
    /* (already in the cradle at power-up: enter_sleep_() has posted the
     * attach event) */
    return first_err;
}

/* Sleep until the next interrupt source or deadline. */
static void sleep_(gl_app_t *app)
{
    const uint32_t now = gl_hal_tick_ms();
    uint32_t wait = app->awake ? 1000u : GL_APP_SLEEP_HOUSEKEEP_MS;
    uint32_t left;
    gl_sleep_mode_t mode = GL_SLEEP_STOP;

    if (gl_event_count(&app->events) != 0u || app->redraw || app->reboot_pending) {
        return; /* more to do right away */
    }
    if (app->capture_active && gl_read_has_work(&app->read)) {
        return; /* a group of strips is waiting to be analysed (rail on) */
    }
    left = gl_ui_time_left_ms(&app->ui, now);
    if (left != 0u && left < wait) {
        wait = left;
    }
    if (app->vbus_pending) {
        const int32_t v = (int32_t)(app->vbus_settle_ms - now);
        if (v < (int32_t)wait) {
            wait = (v > 0) ? (uint32_t)v : 1u;
        }
    }
    if (app->awake) {
        const int32_t batt = (int32_t)(app->next_batt_ms - now);
        if (batt < (int32_t)wait && !app->capture_active && !app->tilt_active) {
            wait = (batt > 0) ? (uint32_t)batt : 1u;
        }
        if (app->zero.active && app->zero.step >= 3u) {
            const int32_t z = (int32_t)(app->zero.saved_at_ms + GL_APP_ZERO_SAVED_MS - now);
            if (z < (int32_t)wait) {
                wait = (z > 0) ? (uint32_t)z : 1u;
            }
        }
        if (app->capture_active && wait > 5u) {
            wait = 5u; /* poll the capture even if its interrupt is lost */
        }
        if (app->imu_ok && wait > GL_APP_IMU_STALL_MS) {
            /* the data-ready interrupt normally ends the sleep after 4 ms;
             * if its latch is lost, the line is polled after this long */
            wait = GL_APP_IMU_STALL_MS;
        }
        if (!app->imu_ok) {
            const int32_t r = (int32_t)(app->imu_retry_ms - now);
            if (r < (int32_t)wait) {
                wait = (r > 0) ? (uint32_t)r : 1u;
            }
        }
        if (app->usb_on && app->stream_mask != 0u) {
            const int32_t s = (int32_t)(app->stream_next_ms - now);
            if (s < (int32_t)wait) {
                wait = (s > 0) ? (uint32_t)s : 1u;
            }
        }
        if (app->usb_on && app->log_erasing) {
            wait = 1u;
        }
    }
    if (app->power.vbus) {
        /* in the cradle the charge is supervised on its own period */
        const int32_t g = (int32_t)(app->next_chg_ms - now);
        if (g < (int32_t)wait) {
            wait = (g > 0) ? (uint32_t)g : 1u;
        }
    }
    /* Stop mode needs: no USB (48 MHz clock), no camera activity (DCMI,
     * XVCLK), and an EXTCOMIN output that keeps running in Stop 2 while the
     * display is on (PROVISIONAL) */
    if (app->usb_on || app->capture_active || gl_read_busy(&app->read) || app->cam.powered ||
        app->clock_fast || (app->lcd.on && GL_PROV_LPTIM_PWM_RUNS_IN_STOP2 == 0)) {
        mode = GL_SLEEP_IDLE; /* (the fast clock is never left on here: see gl_app_run_once) */
    }
    gl_hal_wake_timer_start(wait);
    (void)gl_hal_sleep(mode);
}

/* The 16 s wake-up while asleep: the IMU is the only way the user can wake
 * the device, so its presence and its wake-up configuration are checked,
 * and a failed IMU is retried.  Every GL_APP_SLEEP_BATT_EVERY-th time the
 * cell is measured, to catch it falling to the storage threshold. */
static void sleep_housekeeping_(gl_app_t *app, uint32_t now)
{
    app->sleep_ticks++;
    if (!app->imu_ok) {
        imu_recover_(app, now);
    } else if (!app->storage_mode) {
        const gl_status_t st = gl_imu_verify(&app->imu);
        if (st != GL_OK) {
            imu_failed_(app, st, now);
        }
    }
    if (!app->storage_mode && (app->sleep_ticks % GL_APP_SLEEP_BATT_EVERY) == 0u) {
        gl_power_poll_pins(&app->power);
        if (gl_power_measure(&app->power) == GL_OK && app->power.storage && !app->power.vbus) {
            app->storage_mode = true;
            gl_app_log_event(app, (uint16_t)GL_APP_LOGEV_STORAGE, (int32_t)app->power.batt_mv);
            if (app->flash_ok) {
                (void)gl_mx25r_sleep(&app->flash); /* the log append woke it */
            }
            if (gl_imu_stop(&app->imu) != GL_OK) {
                app->imu_ok = false;
            }
            irq_setup_(app);
        }
    }
}

/* While measuring: fetch a sample when the interrupt announced one, and
 * when it did not for too long.  A lost interrupt latch (or a latched
 * data-ready line that was already high) must not stop the sample pump:
 * stillness, motion, taps and the dial all hang on it. */
static void imu_pump_(gl_app_t *app, uint32_t irq, uint32_t now)
{
    bool sample = (irq & GL_IRQ_IMU_INT2) != 0u;
    const uint32_t quiet_ms = (uint32_t)(now - app->last_sample_ms);

    if (!app->imu_ok) {
        if ((int32_t)(now - app->imu_retry_ms) >= 0) {
            imu_recover_(app, now);
        }
        return;
    }
    if (!sample && quiet_ms >= GL_APP_IMU_STALL_MS) {
        if (gl_hal_gpio_read(GL_PIN_IMU_INT2)) {
            sample = true; /* latched data-ready: the line is still high, the edge was missed */
        } else {
            bool ready = false;
            const gl_status_t st = gl_imu_data_ready(&app->imu, &ready);
            if (st != GL_OK) {
                imu_failed_(app, st, now);
                return;
            }
            sample = ready;
        }
        if (sample) {
            app->imu_polls++;
        } else if (quiet_ms >= GL_APP_IMU_SILENT_MS) {
            /* no data at all: the part has lost its configuration (a supply
             * glitch resets it) or has died */
            imu_failed_(app, GL_ERR_TIMEOUT, now);
            return;
        }
    }
    if (sample) {
        imu_sample_(app, now);
    }
}

void gl_app_run_once(gl_app_t *app)
{
    const uint32_t irq = gl_hal_irq_take();
    uint32_t now = gl_hal_tick_ms();
    gl_event_t e;

    app->loops++;
    if (!app->wdg_hold) {
        gl_hal_watchdog_kick();
    }

    /* 1. interrupt sources -> work */
    if ((irq & (GL_IRQ_VBUS_CHANGE | GL_IRQ_CHG_STAT)) != 0u) {
        vbus_edge_(app, now);
    }
    if (app->vbus_pending && (int32_t)(now - app->vbus_settle_ms) >= 0) {
        vbus_settled_(app, now);
    }
    if (!app->awake) {
        if ((irq & GL_IRQ_IMU_INT1) != 0u) {
            bool woke = false;
            if (app->imu_ok) {
                (void)gl_imu_wake_source(&app->imu, &woke); /* reading clears the latch */
            }
            if ((uint32_t)(now - app->sleep_since_ms) >= GL_APP_WAKE_HOLDOFF_MS) {
                gl_app_post(app, GL_EV_MOTION, 0);
            }
        }
        if ((irq & GL_IRQ_WAKE_TIMER) != 0u &&
            (uint32_t)(now - app->sleep_since_ms) >= GL_APP_SLEEP_HOUSEKEEP_MS / 2u) {
            sleep_housekeeping_(app, now);
        }
    } else {
        imu_pump_(app, irq, now);
        if (app->capture_active) {
            capture_step_(app);
        }
        /* 2. timers */
        battery_service_(app, now);
        if (app->power.vbus && (int32_t)(now - app->next_chg_ms) >= 0 && !app->capture_active &&
            !app->tilt_active) {
            charge_supervise_(app, now);
        }
        if (app->zero.active && app->zero.step >= 3u &&
            (uint32_t)(now - app->zero.saved_at_ms) >= GL_APP_ZERO_SAVED_MS) {
            app->zero.active = false;
            gl_app_post(app, GL_EV_CAL_DONE, 0);
        }
    }
    if (app->usb_on) {
        gl_usb_service(app, now);
    }
    /* the work above can take real time (a capture start waits for the
     * sensor, a raw strip takes half a second to log): the UI is given the
     * time as it is NOW, never an older one than it has already seen */
    now = gl_hal_tick_ms();
    do_actions_(app, gl_ui_tick(&app->ui, now), now);

    /* 3. events -> transition table -> actions */
    while (gl_event_get(&app->events, &e)) {
        const uint32_t a = gl_ui_dispatch(&app->ui, (gl_ui_event_t)e.type, e.arg, now);
        do_actions_(app, a, now);
        if (app->ui.state != (uint8_t)GL_UI_SETTINGS_DIAL) {
            gl_motion_dial_end(&app->motion);
        }
    }
    /* The fast clock belongs to the capture and to the solve, which has
     * run inside the actions above if it was due.  Whatever way a read ended
     * (no flagstick and nothing dialled, a camera fault), it does not
     * outlive this point. */
    if (app->clock_fast && !app->capture_active && !gl_read_busy(&app->read)) {
        clock_(app, false);
    }
    /* 4. screen */
    if (app->redraw) {
        draw_(app);
    }
    /* 5. sleep */
    sleep_(app);
}
