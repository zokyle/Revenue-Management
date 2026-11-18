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

/* build_measurement_() copies the read's horizon samples into the solver's
 * record: the read must not have more of them than the solver takes. */
typedef char gl_app_horizon_samples_fit_the_solver_[
    (GL_VIS_HORIZON_BINS <= GL_SOLVER_MAX_HORIZON) ? 1 : -1];

#define ALL_IRQS                                                                          \
    (GL_IRQ_IMU_INT1 | GL_IRQ_IMU_INT2 | GL_IRQ_VBUS_CHANGE | GL_IRQ_CHG_STAT |           \
     GL_IRQ_WAKE_TIMER | GL_IRQ_USB_RX | GL_IRQ_DCMI_DONE | GL_IRQ_TICK | GL_IRQ_USB_WAKE)

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
    } else if (app->cradle_sleep) {
        /* asleep in the cradle (E32): the charger's status, and the host's
         * resume if USB is in standby; motion does not wake it (the IMU is
         * off) */
        on |= GL_IRQ_CHG_STAT;
        if (app->usb_standby) {
            on |= GL_IRQ_USB_WAKE;
        }
    } else if (!app->ship_pending) {
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
    if (gl_store_get(&app->store, (uint8_t)GL_STORE_ID_CAL_DEVICE, &d, &n) == GL_OK) {
        (void)gl_cal_device_decode(d, n, &app->cal_dev);
    }
}

/* ---- calibration records: identity and storage (also for app/gl_factory.c) ---- */

void gl_app_cal_ids(const gl_app_t *app, uint8_t flags[5], uint16_t crc[5])
{
    uint8_t blob[GL_CAL_MAX_BLOB_LEN];
    /* the CRC of a version-2 record is its last two bytes */
    gl_cal_tilt_encode(&app->cal_tilt, blob);
    crc[0] = gl_get_u16(&blob[GL_CAL_TILT_BLOB_LEN - 2u]);
    gl_cal_cam_encode(&app->cal_cam[GL_CAM_LEFT], blob);
    crc[1] = gl_get_u16(&blob[GL_CAL_CAM_BLOB_LEN - 2u]);
    gl_cal_cam_encode(&app->cal_cam[GL_CAM_RIGHT], blob);
    crc[2] = gl_get_u16(&blob[GL_CAL_CAM_BLOB_LEN - 2u]);
    gl_cal_grain_encode(&app->cal_grain, blob);
    crc[3] = gl_get_u16(&blob[GL_CAL_GRAIN_BLOB_LEN - 2u]);
    gl_cal_device_encode(&app->cal_dev, blob);
    crc[4] = gl_get_u16(&blob[GL_CAL_DEVICE_BLOB_LEN - 2u]);
    flags[0] = app->cal_tilt.flags;
    flags[1] = app->cal_cam[GL_CAM_LEFT].flags;
    flags[2] = app->cal_cam[GL_CAM_RIGHT].flags;
    flags[3] = app->cal_grain.flags;
    flags[4] = app->cal_dev.flags;
}

gl_status_t gl_app_cal_store(gl_app_t *app, uint8_t cal_id)
{
    uint8_t blob[GL_CAL_MAX_BLOB_LEN];
    switch (cal_id) {
    case GL_CAL_ID_TILT:
        gl_cal_tilt_encode(&app->cal_tilt, blob);
        return gl_app_store_put(app, (uint8_t)GL_STORE_ID_CAL_TILT, blob, GL_CAL_TILT_BLOB_LEN);
    case GL_CAL_ID_CAM_L:
        gl_cal_cam_encode(&app->cal_cam[GL_CAM_LEFT], blob);
        return gl_app_store_put(app, (uint8_t)GL_STORE_ID_CAL_CAM_L, blob, GL_CAL_CAM_BLOB_LEN);
    case GL_CAL_ID_CAM_R:
        gl_cal_cam_encode(&app->cal_cam[GL_CAM_RIGHT], blob);
        return gl_app_store_put(app, (uint8_t)GL_STORE_ID_CAL_CAM_R, blob, GL_CAL_CAM_BLOB_LEN);
    case GL_CAL_ID_GRAIN:
        gl_cal_grain_encode(&app->cal_grain, blob);
        return gl_app_store_put(app, (uint8_t)GL_STORE_ID_CAL_GRAIN, blob, GL_CAL_GRAIN_BLOB_LEN);
    case GL_CAL_ID_DEVICE:
        gl_cal_device_encode(&app->cal_dev, blob);
        return gl_app_store_put(app, (uint8_t)GL_STORE_ID_CAL_DEVICE, blob,
                                GL_CAL_DEVICE_BLOB_LEN);
    default:
        return GL_ERR_NOT_FOUND;
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

/* What the two cradle screens show about the charge, as one number (a
 * change of it is a reason to draw again): gl_ui_view_t.chg_blocked in the
 * low bits, then "charging" and "full". */
static uint8_t chg_view_(const gl_app_t *app, uint8_t *blocked, bool *full)
{
    uint8_t b;
    bool f = false;
    switch ((gl_chg_reason_t)app->power.chg_reason) {
    case GL_CHG_ALLOWED:
    case GL_CHG_NO_VBUS: b = 0u; break;
    case GL_CHG_TOO_COLD: b = 1u; break;
    case GL_CHG_TOO_HOT: b = 2u; break;
    case GL_CHG_TIME_LIMIT:
        /* The backstop counts docked time whatever the charger's status
         * says, so it also comes round on a marker that finished its charge
         * hours ago and sleeps in the cradle.  With the cell seen at or
         * above the restart voltage that is simply FULL; "TIME LIMIT" is
         * for the cell that six hours did not bring up. */
        if (app->power.limit_cell_was_up) {
            b = 0u;
            f = true;
        } else {
            b = 4u;
        }
        break;
    case GL_CHG_FORCED: b = 5u; break;
    default: b = 3u; break; /* unknown, NTC fault, implausible */
    }
    if (b == 0u && app->power.vbus) {
        /* the firmware stops nothing: what does the charger do? */
        switch ((gl_chg_status_t)app->power.chg_status) {
        case GL_CHGST_DONE: f = true; break;
        case GL_CHGST_TEMP_HOLD: b = 7u; break;
        case GL_CHGST_NOT_CHARGING:
        case GL_CHGST_STOP_FAILED: b = app->chg_fault ? 6u : 0u; break;
        default: break;
        }
    } else if (app->chg_fault && app->power.chg_status == (uint8_t)GL_CHGST_STOP_FAILED) {
        b = 6u; /* the firmware's stop does not stop */
    }
    if (blocked != NULL) {
        *blocked = b;
        *full = f;
    }
    return (uint8_t)(b | (app->power.charging ? 0x10u : 0u) | (f ? 0x20u : 0u));
}

/* Append a record to the log from wherever the marker is: asleep the flash
 * is in deep power-down (the driver wakes it for the append) and is put
 * back afterwards. */
static void log_event_any_(gl_app_t *app, uint16_t code, int32_t arg)
{
    gl_app_log_event(app, code, arg);
    if (!app->awake && app->flash_ok) {
        (void)gl_mx25r_sleep(&app->flash);
    }
}

/* Apply the firmware's charge gate from what is known NOW (drivers/power.h
 * has the rules), and look at what the charger makes of it.  NTC2 is the
 * input; the IMU's and the MCU's die sensors only vouch for it.  A reading
 * counts as known only if it is fresh. */
static void charge_gate_(gl_app_t *app, uint32_t now)
{
    /* The factory's "hold the charge stopped" (GL_CMD_SET_CHARGE 1) belongs
     * to the unlocked session that asked for it.  When that session is over
     * - USB gone, the cradle sleep, a wrong UNLOCK word, "LOCK", a reset -
     * the stop is over too: a station program that died after assembly
     * step 13 must not leave a docked marker that runs its cell down behind
     * a charger held off (phase-3 review, hardware finding 3: 50.0 % to
     * 44.5 % in 24 h in the model). */
    if (app->power.forced && !app->proto.unlocked) {
        gl_power_charge_force(&app->power, false);
    }
    const bool cell_fresh = app->cell_seen &&
                            (uint32_t)(now - app->cell_temp_ms) <= GL_APP_CELL_TEMP_MAX_AGE_MS;
    const bool imu_t = app->imu_ok && app->temp_valid &&
                       (uint32_t)(now - app->temp_ms) <= GL_APP_TEMP_MAX_AGE_MS;
    const bool mcu_t = app->cell_seen && app->power.mcu_temp_valid &&
                       (uint32_t)(now - app->mcu_temp_ms) <= GL_APP_CELL_TEMP_MAX_AGE_MS;
    const uint8_t before = app->power.chg_reason;
    uint8_t status, shown;
    bool odd;

    (void)gl_power_charge_gate(&app->power, now, cell_fresh, app->temp_c, imu_t, mcu_t);
    /* the pin has just moved, perhaps: the charger's answer */
    gl_power_poll_pins(&app->power);
    status = app->power.chg_status;
    if (app->power.chg_reason != before) {
        /* reason in the low byte, the cell temperature in 0.1 C above it */
        const int32_t t10 = app->power.cell_temp_valid
                                ? (int32_t)gl_roundi(gl_clampf(app->power.cell_temp_c, -100.0f,
                                                               200.0f) * 10.0f)
                                : -9999;
        log_event_any_(app, (uint16_t)GL_APP_LOGEV_CHARGE,
                       (int32_t)app->power.chg_reason | (int32_t)((uint32_t)t10 << 8));
    }
    /* A charger that does not do what everything the firmware knows says it
     * should: for a moment that is the charger finding its input; when it
     * lasts it is a fault (input too low for it, its safety timer, its
     * thermistor shorted, the part dead - or a stop that does not stop). */
    odd = app->power.vbus &&
          (status == (uint8_t)GL_CHGST_NOT_CHARGING || status == (uint8_t)GL_CHGST_STOP_FAILED) &&
          (app->power.batt_mv != 0u || status == (uint8_t)GL_CHGST_STOP_FAILED);
    if (!odd) {
        app->chg_odd = false;
        app->chg_fault = false;
    } else if (!app->chg_odd) {
        app->chg_odd = true;
        app->chg_odd_since_ms = now;
    } else if (!app->chg_fault &&
               (uint32_t)(now - app->chg_odd_since_ms) >= GL_APP_CHG_FAULT_AFTER_MS) {
        app->chg_fault = true;
    }
    /* the log: a charge that ended by itself, and the faults, once each */
    if (!app->power.vbus) {
        app->chg_status_logged = (uint8_t)GL_CHGST_NO_INPUT;
    } else if ((status == (uint8_t)GL_CHGST_DONE || (app->chg_fault && odd)) &&
               status != app->chg_status_logged) {
        app->chg_status_logged = status;
        log_event_any_(app, (uint16_t)GL_APP_LOGEV_CHARGER,
                       (int32_t)status | (int32_t)((uint32_t)app->power.batt_mv << 8));
    } else if (status == (uint8_t)GL_CHGST_CHARGING) {
        app->chg_status_logged = status;
    }
    if (app->power.ntc1_suspect && !app->ntc1_logged) {
        /* a charge was running outside the charger's own window: its
         * thermistor is not doing its job.  The gate has stopped it */
        app->ntc1_logged = true;
        log_event_any_(app, (uint16_t)GL_APP_LOGEV_CHARGER,
                       (int32_t)0x80 | (int32_t)((uint32_t)app->power.batt_mv << 8));
    }
    shown = chg_view_(app, NULL, NULL);
    if (shown != app->chg_shown) {
        app->chg_shown = shown;
        if (app->ui.state == (uint8_t)GL_UI_CRADLE_USB || app->ui.state == (uint8_t)GL_UI_CRADLE_SLEEP) {
            app->redraw = true;
        }
    }
}

/* Measure the cell and the die temperatures and apply the gate: at a VBUS
 * edge, at boot in the cradle, and every GL_APP_CHG_TEMP_PERIOD_MS while
 * VBUS is present - awake or asleep in the cradle.  Asleep there the cell
 * voltage is measured with them (nothing else does it then, and "full" and
 * the restart after the time limit are judged by it). */
static void charge_supervise_(gl_app_t *app, uint32_t now)
{
    gl_status_t st;
    app->next_chg_ms = now + GL_APP_CHG_TEMP_PERIOD_MS;
    gl_power_poll_pins(&app->power);
    st = (app->awake && app->power.batt_mv != 0u) ? gl_power_measure_temps(&app->power)
                                                  : gl_power_measure(&app->power);
    if (st != GL_OK) {
        app->last_error = (uint16_t)GL_ERR_IO;
    }
    app->cell_seen = true;
    app->cell_temp_ms = now;
    app->mcu_temp_ms = now;
    temp_refresh_(app, now);
    charge_gate_(app, now);
}

gl_status_t gl_app_power_refresh(gl_app_t *app)
{
    const uint32_t now = gl_hal_tick_ms();
    gl_status_t st;
    if (app->capture_active || app->tilt_active) {
        return GL_ERR_BUSY; /* not while the camera rail loads the cell or a read runs */
    }
    gl_power_poll_pins(&app->power);
    st = gl_power_measure(&app->power);
    app->cell_seen = true;
    app->cell_temp_ms = now;
    app->mcu_temp_ms = now;
    app->next_chg_ms = now + GL_APP_CHG_TEMP_PERIOD_MS;
    temp_refresh_(app, now);
    charge_gate_(app, now);
    return st;
}

bool gl_app_cell_temperature(const gl_app_t *app, uint32_t now_ms, float *temp_c)
{
    if (!app->cell_seen || !app->power.cell_temp_valid ||
        (uint32_t)(now_ms - app->cell_temp_ms) > GL_APP_CELL_TEMP_MAX_AGE_MS) {
        return false;
    }
    if (temp_c != NULL) {
        *temp_c = app->power.cell_temp_c;
    }
    return true;
}

gl_cradle_state_t gl_app_cradle_state(const gl_app_t *app)
{
    if (!app->power.vbus) {
        return GL_CRADLE_OUT;
    }
    return app->cradle_sleep ? GL_CRADLE_SLEEP : GL_CRADLE_LINK;
}

bool gl_app_ship_mode_arm(gl_app_t *app, bool arm)
{
    app->ship_armed = arm;
    if (!arm) {
        app->ship_pending = false;
    }
    return app->ship_armed;
}

/* E13: no camera read from a cell above 60 C.  The temperature it is judged
 * by is at most GL_APP_READ_TEMP_MAX_AGE_MS old (measured here if not).
 * Returns false, logs and tells the UI if the read must not start. */
static bool read_temp_ok_(gl_app_t *app, uint32_t now, bool measure)
{
    bool imu_t, mcu_t, cell_fresh;
    if (measure && (!app->cell_seen ||
                    (uint32_t)(now - app->cell_temp_ms) > GL_APP_READ_TEMP_MAX_AGE_MS)) {
        if (gl_power_measure_temps(&app->power) != GL_OK) {
            app->last_error = (uint16_t)GL_ERR_IO;
        }
        app->cell_seen = true;
        app->cell_temp_ms = now;
        app->mcu_temp_ms = now;
    }
    cell_fresh = app->cell_seen &&
                 (uint32_t)(now - app->cell_temp_ms) <= GL_APP_CELL_TEMP_MAX_AGE_MS;
    imu_t = app->imu_ok && app->temp_valid &&
            (uint32_t)(now - app->temp_ms) <= GL_APP_TEMP_MAX_AGE_MS;
    mcu_t = cell_fresh && app->power.mcu_temp_valid;
    if (gl_power_read_allowed(&app->power, cell_fresh, app->temp_c, imu_t, mcu_t)) {
        return true;
    }
    {
        float t = app->power.cell_temp_c;
        if (!(cell_fresh && app->power.cell_temp_valid)) {
            t = (mcu_t && (!imu_t || app->power.mcu_temp_c > app->temp_c)) ? app->power.mcu_temp_c
                                                                         : app->temp_c;
        }
        gl_app_log_event(app, (uint16_t)GL_APP_LOGEV_TOO_HOT,
                         (int32_t)gl_roundi(gl_clampf(t, -100.0f, 200.0f) * 10.0f));
    }
    gl_app_post(app, GL_EV_TOO_HOT, 0);
    return false;
}

/* ======================================================================= */
/* core clock: fast only for the compute-heavy part of a read               */
/* ======================================================================= */

/* DESIGN_SPEC section 4: 160 MHz from the PLL during a read, slow otherwise.
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
    } else if (gl_hal_clock_set(GL_CLOCK_SLOW) == GL_OK) {
        app->clock_fast = false;
    } else {
        /* still fast (the backend says so): no Stop mode until a later pass
         * gets it down (gl_app_run_once tries again at every pass) */
        app->clock_fails++;
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

/* Start USB, or bring it back from standby.  The backend refuses while the
 * MCU's USB supply is not valid (gl_hal_usb_supply_ok): the cradle state
 * then tries again with every supervision period. */
static void usb_start_(gl_app_t *app)
{
    if (!app->usb_on && gl_hal_usb_start() == GL_OK) {
        app->usb_on = true;
        app->usb_standby = false;
        app->usb_activity = false;
        gl_proto_rx_reset(&app->proto);
    }
    irq_setup_(app);
}

/* The host side of a USB session is over (stopped, or parked in standby). */
static void usb_session_end_(gl_app_t *app)
{
    app->usb_on = false;
    app->stream_mask = 0;
    app->six.active = false;
    /* a download position belongs to the session that sought it: the next
     * session's LOG_READ "continue" without a LOG_SEEK starts at the oldest
     * record (phase-3 review, factory finding 8) */
    app->log_seek_seq = 0;
    app->log_iter_valid = false;
    gl_proto_disconnect(&app->proto);
}

static void usb_stop_(gl_app_t *app)
{
    if (app->usb_on || app->usb_standby) {
        gl_hal_usb_stop();
        app->usb_standby = false;
        usb_session_end_(app);
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
bool gl_app_camera_allowed(gl_app_t *app)
{
    return read_temp_ok_(app, gl_hal_tick_ms(), true);
}

void gl_app_clock_fast(gl_app_t *app, bool fast)
{
    clock_(app, fast);
}

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
        gl_factory_on_wake(app, now);
        app->awake = true;
        app->storage_mode = false;
        app->cradle_sleep = false;
        app->ship_pending = false;
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
    if (app->usb_on || app->usb_standby) {
        usb_stop_(app);
    }
    /* The charger runs by itself and CHG_INHIBIT can only stop it.  A
     * sleeping MCU must not leave it stopped: without VBUS the pin is
     * released here, so that the next cradle charges the cell even if this
     * firmware never wakes again.  (With VBUS present the marker does not
     * take this sleep: see the end of this function; the gate keeps whatever
     * it decided.) */
    gl_power_poll_pins(&app->power);
    if (!app->power.vbus) {
        gl_power_charge_release(&app->power);
        app->power.chg_reason = (uint8_t)GL_CHG_NO_VBUS;
        app->vbus_acted = false; /* "no VBUS" is dealt with: USB stopped above, pin released */
    }
    app->awake = false;
    app->cradle_sleep = false;
    app->sleep_since_ms = now;
    app->sleep_ticks = 0;
    /* Ship mode has been armed and the marker is out of the cradle: no
     * wake-on-motion from here on (lifting it out IS motion); the MCU
     * follows into its lowest-power state when the contacts have stopped
     * bouncing (gl_app_run_once). */
    app->ship_pending = app->ship_armed && !app->power.vbus;
    app->ship_due_ms = now + GL_APP_SHIP_SETTLE_MS;
    /* A cell that is nearly empty is left alone: IMU off (no wake-on-motion,
     * only the cradle wakes the device), so that the sleep drain does not
     * take it to its protection cut-off (GL_PROV_BATT_STORAGE_MV). */
    app->storage_mode = app->power.storage && !app->power.vbus;
    gl_factory_on_sleep(app, now);
    if (app->storage_mode || app->ship_pending || gl_factory_sleep_no_motion(app)) {
        if (app->storage_mode) {
            gl_app_log_event(app, (uint16_t)GL_APP_LOGEV_STORAGE, (int32_t)app->power.batt_mv);
        }
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
    /* This sleep is not for the cradle: whatever brought the UI here (an
     * error, the low-battery screen), VBUS takes it back to the cradle
     * state, which has its own sleep (cradle_sleep_) and its supervision. */
    if (app->power.vbus) {
        gl_app_post(app, GL_EV_USB_ATTACH, 0);
    }
}

/* E32: asleep IN the cradle.  An awake marker draws more than the charger's
 * termination current from the node the charger feeds, so the charge would
 * never end.  After 30 s without a word from a host (the UI's time limit on
 * the cradle state) the marker therefore goes down to what a charging
 * symbol needs: MCU in Stop mode, the display ON with a static picture (the
 * memory LCD keeps it; its polarity signal keeps running from the low-power
 * timer), IMU and flash powered down.  USB: under a host that has suspended
 * the bus the device stays attached in standby and the host's resume wakes
 * the marker; under a host that is merely silent, or with none (a wall
 * charger), it detaches - a device may not sleep under a running bus.  The
 * cell temperature and the charger are still looked at every
 * GL_APP_CHG_TEMP_PERIOD_MS; a change of the charger's status and the
 * removal of VBUS wake it at once. */
static void cradle_sleep_(gl_app_t *app, uint32_t now)
{
    abort_read_(app);
    app->zero.active = false;
    app->six.active = false;
    gl_motion_spin_end(&app->motion);
    if (app->usb_on) {
        if (gl_hal_usb_bus() == GL_USB_BUS_SUSPENDED && gl_hal_usb_standby() == GL_OK) {
            app->usb_standby = true;
            usb_session_end_(app);
            if (app->log_erasing) {
                app->log_erasing = false;
                gl_log_erase_cancel(&app->log);
            }
        } else {
            usb_stop_(app);
        }
    }
    if (!app->lcd.on) {
        const gl_status_t st = gl_lcd_on(&app->lcd);
        if (st != GL_OK) {
            app->last_error = (uint16_t)st;
        }
    }
    app->awake = false;
    app->cradle_sleep = true;
    app->storage_mode = false;
    app->ship_pending = false;
    app->sleep_since_ms = now;
    app->sleep_ticks = 0;
    /* nothing to sense in the cradle: the IMU is powered down (it comes back
     * with every way out: wake_() and enter_sleep_() configure it) */
    if (app->imu_ok && gl_imu_stop(&app->imu) != GL_OK) {
        app->imu_ok = false;
    }
    app->temp_valid = false; /* the IMU's die sensor is off with it */
    if (app->flash_ok) {
        (void)gl_mx25r_sleep(&app->flash);
    }
    app->next_chg_ms = now; /* a full measurement at once: the symbol is drawn from it */
    app->redraw = true;
    irq_setup_(app);
}

/* Ship mode (E13): everything off, the MCU in its lowest-power state; only
 * VBUS brings the marker back, through a reset.  Called when ship mode has
 * been armed, the marker has left the cradle and VBUS has stayed away for
 * GL_APP_SHIP_SETTLE_MS. */
static void ship_enter_(gl_app_t *app)
{
    gl_power_poll_pins(&app->power);
    if (app->power.vbus) {
        return; /* back in the cradle: stays armed for the next lift */
    }
    /* the last record of this life (the flash is woken for it) */
    gl_app_log_event(app, (uint16_t)GL_APP_LOGEV_SHIP, (int32_t)app->power.batt_mv);
    abort_read_(app);
    gl_lcd_off(&app->lcd);
    if (app->usb_on || app->usb_standby) {
        usb_stop_(app);
    }
    (void)gl_imu_stop(&app->imu); /* power-down: no wake-on-motion, both interrupt lines static */
    if (app->flash_ok) {
        (void)gl_mx25r_sleep(&app->flash);
    }
    gl_grain_fe_all_off();
    (void)gl_hal_opamp_enable(false);
    (void)gl_hal_adc_power(false);
    gl_power_charge_release(&app->power); /* CHG_INHIBIT analog: the charger is free */
    gl_hal_wake_timer_start(0);
    gl_hal_irq_enable(ALL_IRQS, false);
    app->irq_mask = 0;
    gl_hal_ship_mode_enter();
    /* NOT REACHED ON THE TARGET.  The host backend returns: nothing more
     * runs until gl_app_init() is called again (as after the wake-up reset) */
    app->halted = true;
}

/* ======================================================================= */
/* power                                                                    */
/* ======================================================================= */

/* A VBUS or charger-STAT edge - or a VBUS LEVEL that differs from the one
 * last dealt with (gl_app_run_once compares at every loop pass: the edge
 * interrupt only makes the loop run sooner, a lost latch costs time, not
 * the supervision).  The HARDWARE rules are applied here, at once and
 * whatever the UI is doing.  With VBUS gone, USB is stopped (the
 * USB-supply-valid bit must not stay set with the supply pin unpowered) and
 * CHG_INHIBIT is released.  With VBUS there, the charger has ALREADY
 * started by itself if its own thermistor lets it: the cell temperature is
 * measured in this very loop pass and the firmware stops the charge if it
 * has a reason to.  What the UI is told is debounced. */
static void vbus_edge_(gl_app_t *app, uint32_t now)
{
    gl_power_poll_pins(&app->power);
    app->vbus_acted = app->power.vbus; /* this level has now been dealt with */
    if (!app->power.vbus) {
        if (app->usb_on || app->usb_standby) {
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
    if (!app->power.vbus && (app->usb_on || app->usb_standby)) {
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
    /* E13: a marker that wakes too hot says so at once, before the tilt read
     * (the read itself is gated again where the cameras would start) */
    /* ... unless what this wake-up may lead to is a RECALL (E30): that shows
     * a stored result and uses no camera, and E13 is about camera reads.  A
     * hot marker that is tapped shows its result again; if it turns out to
     * have been lifted, the new read is refused where its cameras would
     * start (phase-3 review, application finding 6: the stored result was
     * refused AND lost). */
    if (!app->power.vbus && !app->ui.recall &&
        (app->ui.state == (uint8_t)GL_UI_WAKE || app->ui.state == (uint8_t)GL_UI_WAIT_STILL)) {
        (void)read_temp_ok_(app, now, false);
    }
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
/* Block-slope statistics of a tilt average: one calibrated slope per still
 * 133 ms block; their RMS about the mean is the "scatter". */
static void tstat_reset_(gl_app_tilt_stat_t *s)
{
    memset(s, 0, sizeof(*s));
}

static void tstat_add_(gl_app_t *app)
{
    gl_app_tilt_stat_t *s = &app->tstat;
    gl_vec3_t a;
    gl_vec2_t slope;
    a.x = app->motion.avg.prev_mean_a[0];
    a.y = app->motion.avg.prev_mean_a[1];
    a.z = app->motion.avg.prev_mean_a[2];
    a = gl_tilt_apply_cal(&app->cal_tilt, a, app->temp_valid ? app->temp_c : app->cal_tilt.t0_c);
    if (gl_tilt_slope(a, &slope) != GL_OK || s->n == 0xFFFFu) {
        return;
    }
    s->sum_x += slope.x;
    s->sum_y += slope.y;
    s->sq_x += slope.x * slope.x;
    s->sq_y += slope.y * slope.y;
    s->n++;
}

static float tstat_scatter_(const gl_app_tilt_stat_t *s)
{
    float n, vx, vy;
    if (s->n < 2u) {
        return 0.0f;
    }
    n = (float)s->n;
    vx = s->sq_x / n - (s->sum_x / n) * (s->sum_x / n);
    vy = s->sq_y / n - (s->sum_y / n) * (s->sum_y / n);
    vx = (vx > 0.0f) ? vx : 0.0f;
    vy = (vy > 0.0f) ? vy : 0.0f;
    return sqrtf(0.5f * (vx + vy));
}

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
    /* for the field log: the uncalibrated mean and the scatter of the block
     * slopes that went into it */
    app->tilt_accel_g = mean.accel_g;
    app->tilt_noise_g = mean.accel_noise_g;
    app->tilt_blocks = (uint8_t)((mean.blocks_still < 255u) ? mean.blocks_still : 255u);
    app->tilt_scatter = tstat_scatter_(&app->tstat);
    return GL_OK;
}

/* A tilt record of the field log (core/gl_fieldlog.h): a placement without
 * a camera read. */
static int16_t t_x10_(bool valid, float t)
{
    return valid ? (int16_t)gl_roundi(gl_clampf(t, -100.0f, 200.0f) * 10.0f) : (int16_t)INT16_MIN;
}

static void tilt_log_(gl_app_t *app, uint8_t kind, uint16_t read_id, uint8_t seat,
                      gl_vec2_t slope_raw, gl_vec2_t slope, gl_vec3_t gyro_bias, float yaw_rad)
{
    gl_fieldlog_tilt_t t;
    uint8_t buf[GL_FIELDLOG_TILT_LEN];
    uint8_t flags[5];
    uint16_t crc[5];

    if (!app->storage_ok) {
        return;
    }
    gl_app_cal_ids(app, flags, crc);
    memset(&t, 0, sizeof(t));
    t.kind = kind;
    t.seat = seat;
    t.read_id = read_id;
    t.rtc_s = gl_hal_rtc_seconds();
    t.tick_ms = gl_hal_tick_ms();
    t.slope_raw = slope_raw;
    t.slope = slope;
    t.accel_g = app->tilt_accel_g;
    t.gyro_bias = gyro_bias;
    t.tilt_scatter = app->tilt_scatter;
    t.accel_noise_g = app->tilt_noise_g;
    t.yaw_rad = yaw_rad;
    t.imu_temp_c_x100 = (int16_t)gl_roundi(gl_clampf(app->temp_c, -300.0f, 300.0f) * 100.0f);
    t.cell_temp_c_x10 = t_x10_(app->power.cell_temp_valid, app->power.cell_temp_c);
    t.mcu_temp_c_x10 = t_x10_(app->power.mcu_temp_valid, app->power.mcu_temp_c);
    t.batt_mv = app->power.batt_mv;
    t.cal_tilt_crc = crc[0];
    t.cal_tilt_flags = flags[0];
    t.tilt_blocks = app->tilt_blocks;
    gl_fieldlog_tilt_encode(&t, buf);
    if (gl_log_append(&app->log, (uint8_t)GL_LOG_REC_TILT, 0, buf, sizeof(buf), NULL) != GL_OK) {
        app->last_error = (uint16_t)GL_ERR_IO;
    }
}

/* The placement in app->cur ended without a result (too hot, no flagstick,
 * a camera or solver fault): its tilt is logged all the same, once. */
static void tilt_log_unsolved_(gl_app_t *app, uint8_t kind)
{
    if (app->tilt_logged || !app->cur.tilt_valid) {
        return;
    }
    app->tilt_logged = true;
    tilt_log_(app, kind, app->read_id, app->seat_used, app->cur.slope_raw, app->cur.slope,
              app->cur.gyro_bias, 0.0f);
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
    app->grain_ran = false;
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
    memset(&rd, 0, sizeof(rd));
    if (gl_grain_process(raw_p, &app->cal_grain, &rd) == GL_OK && rd.valid) {
        app->grain_valid = true;
    }
    /* the values are kept for the field log whether or not they are valid */
    app->grain_ran = true;
    app->grain_modulation = rd.red.modulation;
    app->grain_azimuth_rad = rd.red.azimuth_rad;
    app->grain_nir_mod = rd.nir.modulation;
    app->grain_nir_az = rd.nir.azimuth_rad;
    app->grain_reject = rd.reject;
    for (unsigned i = 0; i < GL_GRAIN_LEDS; i++) {
        app->grain_signal[i] = (uint16_t)gl_clampi(gl_roundi(rd.signal[i]), 0, 65535);
    }
}

static void tilt_start_(gl_app_t *app)
{
    tstat_reset_(&app->tstat);
    app->still_ms = gl_hal_tick_ms();
    for (unsigned i = 0; i < (unsigned)GL_FIELDLOG_T_COUNT; i++) {
        app->stage_ms[i] = 0xFFFFu;
    }
    app->cam_on_ms = 0;
    gl_tilt_avg_reset(&app->motion.avg);
    app->tilt_active = true;
    gl_motion_set_strict(&app->motion, true); /* any movement now aborts the read */
}

/* Milliseconds since the tilt average of the current read started (the
 * stage times of the field log), 0xFFFE at most. */
static uint16_t stage_now_(const gl_app_t *app)
{
    const uint32_t d = (uint32_t)(gl_hal_tick_ms() - app->still_ms);
    return (uint16_t)((d < 0xFFFEu) ? d : 0xFFFEu);
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
        if (app->settings.tilt_log != (uint8_t)GL_TILTLOG_OFF) {
            gl_vec2_t s2;
            s2.x = slope_raw.x - app->zero_used.x;
            s2.y = slope_raw.y - app->zero_used.y;
            tilt_log_(app, (uint8_t)GL_FIELDLOG_TILT_REREAD, app->read_id, app->seat_used,
                      slope_raw, s2, gyro_bias, gl_spin_yaw(&app->motion.spin));
        }
    } else {
        /* E11: the zero of the seat the SURFACE setting names (TURF = the
         * base face, the default), or the only one there is */
        gl_vec2_t zero;
        app->seat_used = (uint8_t)gl_cal_tilt_zero(
            &app->cal_tilt, (gl_cal_seat_t)app->settings.surface, &zero);
        app->zero_used = zero;
        memset(&app->cur, 0, sizeof(app->cur));
        app->cur.tilt_valid = true;
        app->cur.up = up;
        app->cur.gyro_bias = gyro_bias;
        app->cur.slope_raw = slope_raw;
        app->cur.slope.x = slope_raw.x - zero.x;
        app->cur.slope.y = slope_raw.y - zero.y;
        app->cur.temp_c = app->temp_c;
        app->cameras_off = false;
        app->tilt_logged = false;
        grain_read_(app);
        if (app->settings.tilt_log != (uint8_t)GL_TILTLOG_OFF) {
            /* the tilt logger: every placement, with the id the read that
             * follows will carry */
            app->tilt_logged = true;
            tilt_log_(app, (uint8_t)GL_FIELDLOG_TILT_PLACEMENT, (uint16_t)(app->read_id + 1u),
                      app->seat_used, slope_raw, app->cur.slope, gyro_bias, 0.0f);
        }
    }
    app->stage_ms[GL_FIELDLOG_T_TILT_DONE] = stage_now_(app);
    gl_app_post(app, GL_EV_TILT_DONE, 0);
}

/* ======================================================================= */
/* capture                                                                  */
/* ======================================================================= */

/* For the field log: when the camera rail came on in this read, and for
 * how long it was on (it goes off when the last strip has been captured,
 * before the last group has been analysed).  Looked at once per loop pass
 * while a capture runs: resolution a few milliseconds. */
static void cam_rail_watch_(gl_app_t *app)
{
    if (!app->cam_seen_on && app->cam.powered) {
        app->cam_seen_on = true;
    } else if (app->cam_seen_on && !app->cam.powered && app->cam_on_ms == 0u) {
        const uint32_t on = (uint32_t)(gl_hal_tick_ms() - app->cam_on_at_ms);
        app->cam_on_ms = (uint16_t)((on < 0xFFFFu) ? ((on != 0u) ? on : 1u) : 0xFFFFu);
    }
}

static void capture_start_(gl_app_t *app)
{
    gl_status_t st;
    if (app->power.critical && !app->power.vbus) {
        /* the camera rail draws about 90 mA from a very small cell */
        gl_app_post(app, GL_EV_BATT_LOW, 0);
        return;
    }
    app->fac.cap_valid = false; /* the read uses the image memory a factory capture lies in */
    if (app->settings.tilt_log == (uint8_t)GL_TILTLOG_ONLY) {
        /* TILT-ONLY MODE: the cameras stay off (no rail, no E13 gate to
         * ask); the placement is solved as a flag-out read */
        app->read_id++;
        app->cameras_off = true;
        app->cur.flag_found = false;
        app->cur.bearing_valid = false;
        gl_app_post(app, GL_EV_CAPTURE_SKIPPED, 0);
        return;
    }
    if (!read_temp_ok_(app, gl_hal_tick_ms(), true)) {
        app->read_id++; /* the refused read has an id of its own in the log */
        tilt_log_unsolved_(app, (uint8_t)GL_FIELDLOG_TILT_TOO_HOT);
        return; /* E13: no camera read above 60 C; the UI has been told */
    }
    app->read_id++;
    clock_(app, true); /* the vision of a read is 58 to 88 million instructions (README) */
    /* the rail comes on at the start of gl_read_start() (the power-up
     * sequence takes about 0.1 s of it) */
    app->cam_seen_on = false;
    app->cam_on_at_ms = gl_hal_tick_ms();
    app->stage_ms[GL_FIELDLOG_T_CAM_ON] = stage_now_(app);
    st = gl_read_start(&app->read, app->cur.up, GL_APP_LRRL_REPEATS);
    if (st != GL_OK) {
        clock_(app, false);
        app->last_error = (uint16_t)st;
        gl_app_log_event(app, (uint16_t)GL_APP_LOGEV_FAULT, (int32_t)st);
        gl_app_post(app, GL_EV_CAPTURE_FAIL, (int32_t)st);
        return;
    }
    app->capture_active = true;
    cam_rail_watch_(app);
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
    cam_rail_watch_(app);
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
    app->stage_ms[GL_FIELDLOG_T_CAPTURE_DONE] = stage_now_(app);
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
        /* a band-only bearing (GL_READ_TIER_BEARING) is not aimed at - and
         * not logged either: a read without a flagstick writes no record */
        app->cur.bearing_valid = false;
        /* ... but its tilt is (a READ2 record with the same id follows if a
         * dialled distance lets the placement be solved) */
        tilt_log_unsolved_(app, (uint8_t)GL_FIELDLOG_TILT_NOT_SOLVED);
        gl_app_post(app, GL_EV_CAPTURE_NO_STICK, 0);
    } else {
        tilt_log_unsolved_(app, (uint8_t)GL_FIELDLOG_TILT_NOT_SOLVED);
        app->last_error = (uint16_t)st;
        gl_app_log_event(app, (uint16_t)GL_APP_LOGEV_FAULT, (int32_t)st);
        gl_app_post(app, GL_EV_CAPTURE_FAIL, (int32_t)st);
    }
}

/* ======================================================================= */
/* solve, result screen, log                                                */
/* ======================================================================= */

/*
 * The dialled distance belongs to ONE hole.  It is forgotten
 *   - when a read ranges a flagstick (the cameras work here: whatever is
 *     left in the DIST setting is from somewhere else), and
 *   - when the marker goes to sleep (the next placement is another putt).
 * It used to stay until the golfer dialled it back to "--": at the next
 * hole every read that missed the flagstick then became, without a word, a
 * flag-out result for the old distance.  Now such a read asks.
 */
static void forget_dialled_(gl_app_t *app)
{
    if (app->settings.manual_distance_cm != 0u) {
        gl_settings_t s = app->settings;
        s.manual_distance_cm = 0u;
        (void)gl_app_set_settings(app, &s);
    }
}

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
        /* at most what the READ's arrays hold (the count used to be limited
         * to the solver's 41 and the copy then ran off arrays of 32) */
        m->n_horizon = (res->n_horizon <= GL_VIS_HORIZON_BINS) ? res->n_horizon
                                                                : (uint8_t)GL_VIS_HORIZON_BINS;
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
 * Which stored placements go to the estimator with the ball's (E29: the
 * newest).  GATE, DO NOT SYNTHESISE applies here too: the estimator - which
 * is frozen - puts every placement at a station min(max(D - range, 0), D)
 * along the line from the ball to the hole.  A placement FARTHER from the
 * hole than the ball has no station there; clamped to 0 its tilt and its
 * hole height would be taken as measured AT the ball (two placements 3 m
 * apart gave a curvature of -0.011 /m that way, tests/test_e2e.c).  So:
 *   - a placement nearer the hole than the ball: used (a station on the line);
 *   - one about as far as the ball - the ball within
 *     GL_APP_SURVEY_AT_BALL_FRACTION of its range - is another reading at the
 *     ball (the golfer came back to it): used, at station 0;
 *   - one clearly farther than the ball: NOT handed over.  The result shown
 *     at the marker's place is then made of the placements from there to the
 *     hole only (a golfer who walks from the ball toward the hole gets, at
 *     each stop, the putt from that stop; "Dn" still counts the stops);
 *   - one that was not ranged cannot be judged: handed over, the estimator
 *     ignores it (as the reference does).
 * The ball's record is last in what is handed over; the estimator does not
 * care where it is (tests/test_solver.c; tests/test_e2e_putt.c runs the same
 * placements ball first and ball last).
 */
static void survey_select_(gl_app_t *app)
{
    const unsigned n = app->survey.count;
    const float ball = drop_range_(&app->meas[n - 1u]);
    unsigned k = 0;

    for (unsigned i = 0; i + 1u < n; i++) {
        const float r = drop_range_(&app->meas[i]);
        if (r > 0.0f && ball > 0.0f && ball < GL_APP_SURVEY_AT_BALL_FRACTION * r) {
            continue; /* behind the ball */
        }
        app->solve_meas[k] = app->meas[i];
        app->solve_src[k] = (uint8_t)i;
        k++;
    }
    app->solve_meas[k] = app->meas[n - 1u];
    app->solve_src[k] = (uint8_t)(n - 1u);
    app->solve_ball = (uint8_t)k;
    app->solve_drops = (uint8_t)(k + 1u);
    app->solve_survey = true;
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
 * and one for the flag-out fallback:
 *   <= 0.09 flag missing: NO box.  The line is solved for the dialled
 *           distance along the visor axis; its direction is the golfer's
 *           pointing, which no sensor checked (the estimator's own score for
 *           it was one box at 4.5 m, the same as a camera read of that putt)
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
    if (e->flag_missing && conf > GL_APP_CONF_FLAG_OUT_MAX) {
        conf = GL_APP_CONF_FLAG_OUT_MAX;
    }
    return gl_clampf(conf, 0.0f, 1.0f);
}

/* The display state of the result (DESIGN_SPEC E33) and its one plain
 * message: core/gl_ui.c, gl_ui_classify(), fed from the estimate. */
static gl_ui_show_t classify_(gl_app_t *app, bool distance_known, gl_ui_note_t *note)
{
    const gl_app_read_t *c = &app->cur;
    const gl_estimate_t *e = &app->est;
    gl_ui_class_in_t in;

    memset(&in, 0, sizeof(in));
    in.aim_source = e->aim_source;
    in.solve_status = e->solve_status;
    in.flag_missing = e->flag_missing;
    in.range_missing = e->range_missing;
    in.fit_converged = e->fit_converged;
    in.poor_horizon = e->poor_horizon;
    in.distance_known = distance_known;
    /* E31: from what the estimator returned, nothing else */
    app->steep_ratio = gl_ui_steep_ratio(e->patch[0], e->patch[1], e->patch[2], e->patch[3],
                                         e->distance_m, e->a_r_mps2);
    in.steep_ratio = app->steep_ratio;
    in.one_camera = c->flag_found && c->tier == (uint8_t)GL_READ_TIER_LEFT;
    in.ambiguous = c->flag_found && c->ambiguous;
    return gl_ui_classify(&in, note);
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

    gl_ui_note_t note = GL_UI_NOTE_NONE;

    v->have_result = true;
    v->recalled = false;
    v->age_s = 0;
    /* a solution of the putt on the estimated surface (patch or its secant
     * plane); anything else has no line */
    v->solved = (e->aim_source == (uint8_t)GL_AIM_FROM_PATCH ||
                 e->aim_source == (uint8_t)GL_AIM_FROM_PLANE);
    /* E33: normal / approximate / no solution, and the one message */
    v->show = (uint8_t)classify_(app, !(assumed && !dialled), &note);
    v->note = (uint8_t)note;
    v->flag_found = !e->flag_missing;
    v->precision = c->precision;
    v->distance_assumed = assumed;
    /* the estimator's numbers; a distance nobody measured or dialled (the
     * estimator's 3 m default) is not shown as if it were known */
    v->distance_m = (assumed && !dialled) ? 0.0f : e->distance_m;
    /* "PLAYS": the flat putt that needs the same stroke.  The estimator's
     * plays_like_m is the roll-out distance v0^2 / (2 a_r), which contains
     * the PAST setting; a flat putt of length L is struck to roll L + PAST,
     * so PAST is taken off (a dead-flat putt then plays its own length; it
     * used to "play" 30 cm more). */
    v->plays_like_m = 0.0f;
    if (!(assumed && !dialled) && e->plays_like_m > app->solve_opt.past_m) {
        v->plays_like_m = e->plays_like_m - app->solve_opt.past_m;
    }
    v->plays_uncertain = e->base_hidden;
    v->slope_pct = e->slope_pct;
    v->break_cups = e->break_cups;
    v->confidence = shown_confidence_(app);
    v->drop = (c->stored && app->survey.count > 0u) ? app->survey.count : 0u;
    v->drops_used = (v->drop != 0u && app->solve_survey) ? app->solve_drops : v->drop;
    /* E11: the zero that was removed is the one of the seat the SURFACE
     * setting names - or it is the other seat's, or none at all (phase-3
     * review, application finding 4: nothing on the screen said so) */
    v->zero_missing = (app->seat_used != app->settings.surface);
    /* from the read frame to the marker's present frame */
    v->aim_rad = gl_wrap_pi(e->aim_azimuth_device_rad - c->view_yaw_rad);
    /* E12: the renderer turns the line by the stored rotation of the glass */
    v->display_rot_rad = app->cal_dev.display_rot_rad;
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

/* The replay records of the read just solved (core/gl_fieldlog.h): every
 * placement the estimator was handed, then context, estimate and fit.
 * One record at a time is assembled in a static buffer (684 bytes: not on
 * the stack). */
static uint8_t fieldlog_buf_[GL_FIELDLOG_READ_LEN];

typedef char gl_app_fieldlog_buf_holds_a_placement_[
    (GL_FIELDLOG_MEAS_MAX <= GL_FIELDLOG_READ_LEN) ? 1 : -1];

static void fieldlog_meas_(gl_app_t *app)
{
    if (!app->storage_ok) {
        return;
    }
    for (unsigned i = 0; i < app->solve_drops; i++) {
        const gl_measurements_t *m = app->solve_survey ? &app->solve_meas[i] : &app->meas_cur;
        const size_t n = gl_fieldlog_meas_encode(app->read_id, (uint8_t)i, app->solve_drops,
                                                 i == app->solve_ball, m, fieldlog_buf_,
                                                 sizeof(fieldlog_buf_));
        if (n == 0u || gl_log_append(&app->log, (uint8_t)GL_LOG_REC_MEAS, 0, fieldlog_buf_, n,
                                     NULL) != GL_OK) {
            app->last_error = (uint16_t)GL_ERR_IO;
        }
    }
}

static void fieldlog_read_(gl_app_t *app, gl_status_t solver_ret)
{
    const gl_app_read_t *c = &app->cur;
    const gl_read_result_t *res = &app->read.result;
    gl_fieldlog_ctx_t x;

    if (!app->storage_ok) {
        return;
    }
    memset(&x, 0, sizeof(x));
    x.read_id = app->read_id;
    x.rtc_s = gl_hal_rtc_seconds();
    x.tick_ms = gl_hal_tick_ms();
    x.fw_version = (uint16_t)GL_APP_FW_VERSION;
    x.fw_build = GL_APP_FW_BUILD;
    x.solver_version = gl_solver_version();
    x.hw_rev = (uint8_t)GL_APP_HW_REV;
    x.cal_version = (uint8_t)GL_CAL_VERSION;
    gl_app_cal_ids(app, x.cal_flags, x.cal_crc);
    gl_settings_encode(&app->settings, x.settings);
    x.n_drops = app->solve_drops;
    x.ball_index = app->solve_ball;
    x.solver_ret = (uint8_t)solver_ret;
    x.tier = c->tier;
    x.base = c->base;
    x.seat = app->seat_used;
    x.note = app->view.note;
    x.groups_ok = c->flag_found ? res->groups_ok : 0u;
    x.flags = (uint16_t)((c->precision ? GL_FIELDLOG_F_PRECISION : 0u) |
                         ((app->solve_drops > 1u) ? GL_FIELDLOG_F_SURVEY : 0u) |
                         (c->flag_found ? GL_FIELDLOG_F_FLAG_FOUND : 0u) |
                         (c->ambiguous ? GL_FIELDLOG_F_AMBIGUOUS : 0u) |
                         ((c->flag_found && c->top_valid) ? GL_FIELDLOG_F_TOP_VALID : 0u) |
                         (app->grain_ran ? GL_FIELDLOG_F_GRAIN_RAN : 0u) |
                         (app->grain_valid ? GL_FIELDLOG_F_GRAIN_VALID : 0u) |
                         (app->line_here ? GL_FIELDLOG_F_LINE_HERE : 0u) |
                         (app->cameras_off ? GL_FIELDLOG_F_CAMERAS_OFF : 0u) |
                         /* solid exactly when the renderer draws it solid: the NORMAL
                          * state of DESIGN_SPEC E33 (core/gl_ui.c) */
                         ((solver_ret == GL_OK && gl_ui_view_show(&app->view) == GL_UI_SHOW_NORMAL)
                              ? GL_FIELDLOG_F_SOLID_LINE : 0u));
    x.slope_raw = c->slope_raw;
    x.slope = c->slope;
    x.zero = app->zero_used;
    if (c->precision) {
        x.spin_slope_raw = app->spin_slope_raw;
        x.reread_slope_raw = app->reread_slope_raw;
    }
    x.view_yaw_rad = c->view_yaw_rad;
    x.up = c->up;
    x.gyro_bias = c->gyro_bias;
    x.tilt_scatter = app->tilt_scatter;
    x.accel_noise_g = app->tilt_noise_g;
    x.tilt_blocks = app->tilt_blocks;
    x.imu_temp_c_x100 = (int16_t)gl_roundi(gl_clampf(c->temp_c, -300.0f, 300.0f) * 100.0f);
    x.cell_temp_c_x10 = t_x10_(app->power.cell_temp_valid, app->power.cell_temp_c);
    x.mcu_temp_c_x10 = t_x10_(app->power.mcu_temp_valid, app->power.mcu_temp_c);
    x.batt_mv = app->power.batt_mv;
    if (app->grain_ran) {
        x.grain_red_mod = app->grain_modulation;
        x.grain_red_az = app->grain_azimuth_rad;
        x.grain_nir_mod = app->grain_nir_mod;
        x.grain_nir_az = app->grain_nir_az;
        x.grain_reject = app->grain_reject;
        memcpy(x.grain_signal, app->grain_signal, sizeof(x.grain_signal));
    }
    if (c->flag_found) {
        x.bearing_rad = c->bearing_rad;
        x.disparity_px = c->disparity_px;
        x.disparity_sigma_px = c->disparity_sigma_px;
        x.base_elev_rad = c->base_elev_rad;
        x.top_elev_rad = c->top_valid ? c->top_elev_rad : 0.0f;
        x.quality[0] = pct_(res->quality.rows_used_frac);
        x.quality[1] = (uint8_t)gl_clampi(gl_roundi(res->quality.line_contrast), 0, 255);
        x.quality[2] = pct_(res->quality.sharpness_match);
        x.quality[3] = pct_(res->quality.sat_fraction);
        x.quality[4] = res->quality.sun ? 1u : 0u;
    }
    if (c->range_valid) {
        x.diag_range_m = c->range.range_m;
        x.diag_range_sigma_m = c->range.sigma_m;
    }
    x.stick_height_m = app->stick_height.height_m;
    x.stick_height_sigma_m = app->stick_height.sigma_m;
    memcpy(x.stage_ms, app->stage_ms, sizeof(x.stage_ms));
    x.cam_on_ms = app->cam_on_ms;
    x.shown_aim_rad = app->view.aim_rad;
    x.shown_confidence = app->view.confidence;
    x.display_rot_rad = app->cal_dev.display_rot_rad;
    if (gl_fieldlog_read_encode(&x, &app->solve_opt, &app->est, &app->solver_work.fit,
                                fieldlog_buf_, sizeof(fieldlog_buf_)) == 0u ||
        gl_log_append(&app->log, (uint8_t)GL_LOG_REC_READ2, 0, fieldlog_buf_,
                      GL_FIELDLOG_READ_LEN, NULL) != GL_OK) {
        app->last_error = (uint16_t)GL_ERR_IO;
    }
}

/* ======================================================================= */
/* Recall (DESIGN_SPEC E30)                                                  */
/* ======================================================================= */

/* A result has just been made and goes onto the screen: from here on the
 * marker is watched (the rule is with its constants in gl_app_cfg.h). */
static void recall_result_made_(gl_app_t *app)
{
    app->result_ms = gl_hal_tick_ms();
    app->recall_rest_x = app->motion.rest_x;
    app->recall_rest_y = app->motion.rest_y;
    /* (a result made without the marker ever having been seen at rest
     * cannot be compared with anything later) */
    app->recall_spoiled = !app->motion.have_rest;
    app->recall_checking = false;
    gl_rot_int_start(&app->recall_rot, app->cur.gyro_bias);
}

/* One IMU sample, while a result is on the screen or the marker has just
 * been woken with a result that may be recalled. */
static void recall_watch_(gl_app_t *app, unsigned flags, uint32_t dt_ms)
{
    const bool shown = (app->ui.state == (uint8_t)GL_UI_SHOW_RESULT) && app->view.have_result;
    bool gone = false;

    if (!shown && !app->recall_checking) {
        return;
    }
    gl_rot_int_add(&app->recall_rot, app->motion.gyro_rad_s, (float)dt_ms * 0.001f);
    if (gl_rot_int_angle(&app->recall_rot) > GL_APP_RECALL_MAX_TURN_RAD) {
        gone = true; /* turned on the spot */
    }
    if ((flags & GL_MOTION_F_BLOCK_STILL) != 0u &&
        (fabsf(app->motion.avg.prev_mean_a[0] - app->recall_rest_x) > GL_APP_RECALL_DISPLACE_G ||
         fabsf(app->motion.avg.prev_mean_a[1] - app->recall_rest_y) > GL_APP_RECALL_DISPLACE_G)) {
        gone = true; /* it lies differently now */
    }
    if (app->recall_checking) {
        if (app->motion.posture.stable == GL_POSTURE_UPRIGHT ||
            app->motion.posture.stable == GL_POSTURE_OTHER) {
            gone = true; /* in the hand */
        }
        if ((flags & GL_MOTION_F_BLOCK) != 0u && (flags & GL_MOTION_F_BLOCK_STILL) == 0u) {
            if (app->recall_moving < 255u) {
                app->recall_moving++;
            }
            if (app->recall_moving > GL_APP_RECALL_MOVING_BLOCKS) {
                gone = true; /* more movement than a tap leaves behind */
            }
            app->recall_still = 0;
            app->recall_sum_x = 0.0f;
            app->recall_sum_y = 0.0f;
        } else if ((flags & GL_MOTION_F_BLOCK_STILL) != 0u) {
            /* RESEATED?  The mean of the still blocks before the one that
             * would show the result, against where the marker lay at its
             * read, at the noise of that comparison (gl_app_cfg.h).  Decided
             * one block BEFORE the UI's "at rest", so that a new read is
             * what follows, not a stale line that is taken back */
            app->recall_sum_x += app->motion.avg.prev_mean_a[0];
            app->recall_sum_y += app->motion.avg.prev_mean_a[1];
            if (app->recall_still < 255u) {
                app->recall_still++;
            }
            if (app->recall_still == GL_APP_STILL_BLOCKS - 1u) {
                const float n = (float)app->recall_still;
                if (fabsf(app->recall_sum_x / n - app->recall_rest_x) > GL_APP_RECALL_RESEAT_G ||
                    fabsf(app->recall_sum_y / n - app->recall_rest_y) > GL_APP_RECALL_RESEAT_G) {
                    gone = true; /* it has seated itself anew: the stored line is not this one's */
                }
            }
        }
    }
    if (gone) {
        app->recall_spoiled = true;
        if (app->recall_checking) {
            app->recall_checking = false;
            gl_app_post(app, GL_EV_LIFTED, 0); /* the UI: forget it, a new read follows */
        }
    }
}

/* The marker has been woken (wake_() has restarted the IMU): if the UI
 * still offers the stored result, start watching for a lift. */
static void recall_wake_(gl_app_t *app)
{
    app->recall_checking = false;
    if (!app->ui.recall) {
        return;
    }
    if (app->recall_spoiled || !app->view.have_result || !app->imu_ok ||
        (uint32_t)(gl_hal_tick_ms() - app->result_ms) > GL_APP_RECALL_MAX_AGE_MS) {
        gl_app_post(app, GL_EV_LIFTED, 0);
        return;
    }
    app->recall_checking = true;
    app->recall_moving = 0;
    app->recall_still = 0;
    app->recall_sum_x = 0.0f;
    app->recall_sum_y = 0.0f;
    gl_rot_int_start(&app->recall_rot, app->cur.gyro_bias);
}

/* GL_ACT_RECALL: tapped awake, at rest, not lifted - the stored result
 * again, with its age.  No read: no tilt average, no camera, no solve, and
 * nothing is written to the log. */
static void recall_show_(gl_app_t *app)
{
    /* (the tick counts through Stop mode; the RTC is not used: it reads 0
     * until a host has set it) */
    app->recall_checking = false;
    app->view.recalled = true;
    app->view.age_s = (uint32_t)(gl_hal_tick_ms() - app->result_ms) / 1000u;
    app->recalls++;
    /* the watch goes on while it is on the screen again */
    gl_rot_int_start(&app->recall_rot, app->cur.gyro_bias);
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
     * estimate is 0.3 million instructions, the step budget below allows
     * 105 million (351 per RK4 step by the cost table; README "Run time") */
    clock_(app, true);
    build_measurement_(app, &app->meas_cur);
    gl_solver_default_options(opt);
    opt->past_m = gl_settings_past_m(&app->settings);
    opt->method = app->settings.method; /* B1 by default; B2 is a setting */
    /* The grain is NOT used by default: the GRAIN setting ships OFF, and
     * gl_grain_estimate() then hands over zero strength.  Switched ON
     * (experimental), the estimate - the grass type's strength along the
     * fall line, or along the optical reading when that is valid - is used
     * by the solve.  (GRAIN ON used to lengthen the read and change
     * nothing.) */
    opt->use_grain = (app->settings.grain_enable != 0u);
    /* A patch iterate that passes within 5 mm of the hole centre IS the putt
     * (the search stopped at a jump of the miss): it is kept, flagged, and
     * the secant plane - which misses the hole on the fitted patch by
     * decimetres in most of those cases - is not shown instead. */
    opt->near_miss_m = GL_APP_NEAR_MISS_M;
    /* The one deliberate difference from the reference: a budget on the
     * work.  The costliest estimate found needs 575,247 RK4 steps without
     * it (tests/test_solver.c: 202 million instructions by the cost table,
     * 1.9 to 3.8 s at 160 MHz and 6.3 to 12.6 s at 48 MHz over the range of
     * the timing model), the bound from the loop counters is 3.84 million
     * steps - beyond the 32 s watchdog without the PLL.  With the budget an
     * estimate integrates at most 306 004 steps; a solve that is cut ends
     * as what these putts end as anyway: no solution (DESIGN_SPEC E33: the
     * message "NOT SOLVED" or "TOO STEEP", and no line). */
    opt->max_steps = GL_APP_SOLVE_MAX_STEPS;
    gl_hal_watchdog_kick(); /* the solve blocks the loop: start it with a fresh period */
    app->stage_ms[GL_FIELDLOG_T_SOLVE_START] = stage_now_(app);
    app->solve_drops = 1;
    app->solve_ball = 0;
    app->solve_src[0] = (uint8_t)((app->survey.count > 0u) ? (app->survey.count - 1u) : 0u);
    app->solve_survey = false;
    app->line_here = true;
    if (c->stored && app->survey.count >= 2u) {
        /* the newest drop is the current read: keep its record in step with
         * what has just been built (a Precision combination changes it).
         * DESIGN_SPEC E29: THE PLACEMENT THE MARKER STANDS ON IS THE BALL -
         * the newest drop defines the putt, the earlier ones are samples
         * along its line.  So every result of a Survey has its line.  (Until
         * phase 3 the ball was the drop farthest from the flagstick, and at
         * any other drop the screen said "PUT AT BALL" without a line.) */
        app->meas[app->survey.count - 1u] = app->meas_cur;
        survey_select_(app);
        st = gl_solver_estimate_survey(app->solve_meas, app->solve_drops, app->solve_ball, opt,
                                       &app->solver_work, &app->est);
    } else {
        st = gl_solver_estimate(&app->meas_cur, opt, &app->solver_work, &app->est);
    }
    gl_hal_trace(GL_TRACE_SOLVE, (st == GL_OK) ? app->est.n_steps : 0u);
    clock_(app, false);
    app->stage_ms[GL_FIELDLOG_T_SOLVE_DONE] = stage_now_(app);
    app->solver_status = st;
    /* what the estimator was handed is logged whatever it made of it: a
     * read that could not be solved is the one most worth replaying */
    fieldlog_meas_(app);
    if (st != GL_OK) {
        tilt_log_unsolved_(app, (uint8_t)GL_FIELDLOG_TILT_NOT_SOLVED);
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
    recall_result_made_(app);
    log_read_(app);
    fieldlog_read_(app, st);
    app->tilt_logged = true; /* the READ2 record carries the tilt */
    app->reads_total++;
    if (!app->est.flag_missing && !app->est.range_missing) {
        forget_dialled_(app); /* (after the view: it has no use for it either) */
    }
    gl_app_post(app, GL_EV_SOLVE_DONE, 0);
}

/* ======================================================================= */
/* zeroing: read, turn 180 degrees in place, read (hard flat surface)       */
/* ======================================================================= */

static void zero_start_(gl_app_t *app)
{
    memset(&app->zero, 0, sizeof(app->zero));
    /* From the menu: the user's zeroing on a hard flat surface - the BALL
     * seat (E11).  Armed by the factory (GL_CMD_LEVEL_ZERO): the seat it
     * named; the marker lies on that seat plate now. */
    app->zero.seat = (uint8_t)GL_CAL_SEAT_BALL;
    if (app->fac.zero.state == (uint8_t)GL_ZERO_STATE_ARMED) {
        app->zero.seat = app->fac.zero.seat;
        app->zero.armed = true;
        app->fac.zero.state = (uint8_t)GL_ZERO_STATE_RUNNING;
        app->fac.zero.attempts++;
    }
    if (app->power.vbus) {
        /* never in the cradle: it takes the marker one way round only */
        if (app->zero.armed) {
            gl_factory_zero_result(app, GL_ERR_STATE, app->zero.m1, app->zero.m1, 0.0f, 0.0f);
        }
        gl_app_post(app, GL_EV_CAL_FAIL, (int32_t)GL_ERR_STATE);
        return;
    }
    app->zero.active = true;
    gl_motion_set_strict(&app->motion, false);
    app->redraw = true;
}

static void zero_fail_(gl_app_t *app, gl_status_t st)
{
    if (app->zero.armed) {
        gl_factory_zero_result(app, st, app->zero.m1, app->zero.m1, 0.0f, app->zero.scatter);
    }
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
            tstat_reset_(&app->tstat);
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
    if (app->tilt_scatter > z->scatter) {
        z->scatter = app->tilt_scatter;
    }
    {
        /* both reads of a zeroing go to the field log (the two separate
         * tilt readings VALIDATION_PLAN 3.3 asks for) */
        gl_vec2_t zero_now, s2;
        (void)gl_cal_tilt_zero(&app->cal_tilt, (gl_cal_seat_t)z->seat, &zero_now);
        s2.x = slope_raw.x - zero_now.x;
        s2.y = slope_raw.y - zero_now.y;
        tilt_log_(app, (uint8_t)((z->step == 0u) ? GL_FIELDLOG_TILT_ZERO_1 : GL_FIELDLOG_TILT_ZERO_2),
                  app->read_id, z->seat, slope_raw, s2, gyro_bias,
                  (z->step == 0u) ? 0.0f : gl_rot_int_yaw(&z->rot, z->up1));
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
        const gl_cal_tilt_t before = app->cal_tilt;
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
        gl_cal_tilt_set_zero(&app->cal_tilt, (gl_cal_seat_t)z->seat, bias,
                             app->temp_valid ? app->temp_c : app->cal_tilt.t0_c,
                             gl_hal_rtc_seconds(), z->scatter);
        st = gl_app_cal_store(app, (uint8_t)GL_CAL_ID_TILT);
        if (st != GL_OK && st != GL_ERR_NOT_FOUND) {
            app->cal_tilt = before; /* not stored: not adopted either */
            zero_fail_(app, st);
            return;
        }
        if (z->armed) {
            if (st != GL_OK) {
                /* the factory wants it STORED: a unit without storage fails */
                app->cal_tilt = before;
                zero_fail_(app, st);
                return;
            }
            gl_factory_zero_result(app, GL_OK, bias, surface, yaw, z->scatter);
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
            gl_status_t st;
            if (app->six.done_mask != 0x3Fu) {
                return GL_ERR_STATE;
            }
            st = gl_tilt_six_face_solve(app->six.meas, &offset, &m);
            gl_app_log_event(app, (uint16_t)GL_APP_LOGEV_SIX_FACE, (int32_t)st);
            if (st != GL_OK) {
                return st;
            }
            /* Solved into a COPY; the copy must pass the record's own range
             * check (a matrix element the decoder refuses would be stored
             * and then dropped to defaults at the next boot), must be
             * stored, and only then is it the unit's calibration.  If any of
             * that fails nothing has changed - the RAM record, the flags
             * GET_IDENT reports, and the six captured faces, which the
             * operator can solve again (phase-3 review, factory finding 10:
             * a refused store left the new offsets and the FACTORY flag in
             * RAM until the next reset). */
            {
                const gl_cal_tilt_t before = app->cal_tilt;
                gl_cal_tilt_t cal = app->cal_tilt, chk;
                uint8_t blob[GL_CAL_TILT_BLOB_LEN];
                cal.offset_g[0] = offset.x;
                cal.offset_g[1] = offset.y;
                cal.offset_g[2] = offset.z;
                cal.m = m;
                if (app->temp_valid) {
                    cal.t0_c = app->temp_c;
                }
                cal.flags |= (uint8_t)GL_CAL_TILT_FLAG_FACTORY;
                gl_cal_tilt_encode(&cal, blob);
                st = gl_cal_tilt_decode(blob, sizeof(blob), &chk);
                if (st != GL_OK) {
                    return st;
                }
                app->cal_tilt = cal;
                st = gl_app_cal_store(app, (uint8_t)GL_CAL_ID_TILT);
                if (st != GL_OK) {
                    app->cal_tilt = before;
                    return st;
                }
            }
            app->six.done_mask = 0;
            return GL_OK;
        }
        return GL_ERR_PARAM;
    case GL_CALPROC_GRAIN_WHITE: {
        const gl_cal_grain_t before = app->cal_grain;
        gl_cal_grain_t cal = app->cal_grain, chk;
        uint8_t blob[GL_CAL_GRAIN_BLOB_LEN];
        gl_status_t st = gl_grain_fe_measure(&grain_raw_, GL_GRAIN_MAX_CYCLES);
        if (st == GL_OK) {
            st = gl_grain_white_reference(&grain_raw_, &cal);
        }
        gl_app_log_event(app, (uint16_t)GL_APP_LOGEV_GRAIN_WHITE, (int32_t)st);
        if (st != GL_OK) {
            return st;
        }
        /* as for the six-face solve: checked, stored, and only then adopted */
        gl_cal_grain_encode(&cal, blob);
        st = gl_cal_grain_decode(blob, sizeof(blob), &chk);
        if (st != GL_OK) {
            return st;
        }
        app->cal_grain = cal;
        st = gl_app_cal_store(app, (uint8_t)GL_CAL_ID_GRAIN);
        if (st != GL_OK) {
            app->cal_grain = before;
        }
        return st;
    }
    case GL_CALPROC_ABORT:
        app->six.active = false;
        return GL_OK;
    default:
        /* GL_CALPROC_GRAIN_FLOOR (readings on turf, outside the cradle) and
         * GL_CALPROC_CAM_HORIZON (a frame of the factory target) are not
         * procedures of the unit: the PC measures and writes the result with
         * GL_CMD_SET_GRAIN_FLOOR / GL_CMD_SET_CAM_HORIZON (app/gl_factory.c) */
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
    if ((flags & GL_MOTION_F_BLOCK_STILL) != 0u &&
        (app->tilt_active || (app->zero.active && app->zero.averaging))) {
        tstat_add_(app); /* one block slope more for the scatter of this average */
    }
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
    recall_watch_(app, flags, dt_ms);
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
        /* The read on the screen is no longer a placement of any Survey.  If
         * the golfer starts one again on this same result it must be stored
         * again: survey_store_() refuses a read that is marked as stored,
         * and until the phase-3 review the mark outlived the Survey it
         * belonged to - the restarted Survey silently lost its first
         * placement, showed "D1" at the next one, and the UI counted one
         * placement more than the application held (application finding 1). */
        app->cur.stored = false;
    }
    if ((a & GL_ACT_NEW_READ) != 0u) {
        app->view.have_result = false;
        app->recall_checking = false;
        gl_motion_spin_end(&app->motion);
    }
    if ((a & GL_ACT_DISPLAY_ON) != 0u) {
        const bool was_asleep = !app->awake;
        wake_(app, now);
        if (was_asleep) {
            recall_wake_(app); /* E30 */
        }
    }
    if ((a & GL_ACT_RECALL) != 0u) {
        recall_show_(app);
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
        } else if (app->ui.item == GL_UI_ITEM_INFO) {
            hi = (int)app->ui.info_pages - 1; /* the pages of the INFO screen */
            if (hi < 0) {
                hi = 0;
            }
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
        if (app->motion.spin_active) {
            /* An abandoned spin of THIS read is still being integrated (see
             * below): the angle goes on counting from the frame the cameras
             * read in.  Only the report of a half turn is armed again. */
            gl_motion_spin_rearm(&app->motion);
        } else {
            app->spin_slope_raw = app->cur.slope_raw;
            gl_motion_spin_begin(&app->motion, app->cur.up, app->cur.gyro_bias);
        }
    }
    if ((a & GL_ACT_SPIN_ABANDON) != 0u) {
        /* The Precision spin was not completed (time-out).  The single read
         * is shown again, but the marker may have been turned by any angle
         * meanwhile: the screen is drawn for where it faces NOW.
         * The gyro integration is NOT stopped: if the golfer asks for the
         * spin again, the half turn must still be measured from the frame of
         * the read, not from wherever the marker was left.  (It used to
         * restart from zero there, with the first read's slope: the same
         * frame error as a second double tap on a "2X" result.)  It ends
         * with the read: a new placement, sleep, or the combination. */
        if (app->motion.spin_active && app->view.have_result) {
            app->cur.view_yaw_rad = gl_spin_yaw(&app->motion.spin);
            app->cur.precision = false;
            compose_view_(app);
        }
        /* E30: where the marker lies now, and how, is not what it was when
         * the result was made: this result is not offered again later */
        app->recall_spoiled = true;
    }
    if ((a & GL_ACT_CAL_ZERO_START) != 0u) {
        zero_start_(app);
    }
    if ((a & GL_ACT_REDRAW) != 0u) {
        app->redraw = true;
    }
    if ((a & GL_ACT_CRADLE_SLEEP) != 0u) {
        cradle_sleep_(app, now);
    }
    if ((a & GL_ACT_ENTER_SLEEP) != 0u) {
        if (app->awake) {
            forget_dialled_(app); /* while the flash is still awake */
        }
        enter_sleep_(app);
    }
}

/* What the INFO item of the dial shows (regulatory and information screen):
 * hardware and firmware version, the serial number - the stored one, else
 * the one derived from the processor's unique number - and the text block. */
static void info_view_(gl_app_t *app)
{
    gl_ui_view_t *v = &app->view;
    uint32_t serial = app->cal_dev.serial;

    if ((app->cal_dev.flags & GL_CAL_DEV_FLAG_SERIAL) == 0u) {
        uint8_t uid[12];
        gl_hal_unique_id(uid);
        serial = gl_cal_serial_from_uid(uid);
    }
    v->info_hw = GL_APP_HW_REV_LETTER;
    v->info_fw = (uint16_t)GL_APP_FW_VERSION;
    gl_cal_serial_text(serial, v->info_serial);
    v->info_text = GL_REGULATORY_TEXT;
    app->ui.info_pages = (uint8_t)gl_ui_info_pages(v->info_text);
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
    app->chg_shown = chg_view_(app, &app->view.chg_blocked, &app->view.chg_full);
    app->view.cal_step = app->zero.active ? app->zero.step : 0u;
    info_view_(app);
    if (!gl_factory_draw(app)) { /* a display test pattern holds the screen */
        gl_ui_render(&app->ui, &app->view, &app->gfx);
    }
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
    if ((reset & GL_RESET_SHIP_HELD) != 0u) {
        /* HOST BACKEND ONLY: the marker is in ship mode and VBUS is not
         * there; a target backend has gone back to ship mode inside
         * gl_hal_init() and never comes here */
        app->halted = true;
        return GL_ERR_STATE;
    }
    gl_event_init(&app->events);
    app->boot_ms = gl_hal_tick_ms(); /* the 10 s of E34's confirmation count from here */

    gl_settings_defaults(&app->settings);
    gl_cal_tilt_defaults(&app->cal_tilt);
    gl_cal_cam_defaults(&app->cal_cam[GL_CAM_LEFT], 0);
    gl_cal_cam_defaults(&app->cal_cam[GL_CAM_RIGHT], 1);
    gl_cal_grain_defaults(&app->cal_grain);
    gl_cal_device_defaults(&app->cal_dev);
    gl_stick_height_reset(&app->stick_height);
    app->seat_used = (uint8_t)GL_CAL_SEAT_NONE;

    /* drivers: every one first puts its pins into the safe state */
    gl_ov7692_init(&app->cam, NULL); /* camera rail off, camera-facing pins parked */
    gl_lcd_init(&app->lcd, NULL);
    gl_grain_fe_all_off();
    gl_power_init(&app->power);
    app->vbus_acted = app->power.vbus;
    if (app->power.vbus) {
        /* booted in the cradle: the charger is already running if its own
         * thermistor lets it (hardware default); measure the cell before
         * anything slower is done */
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
            /* a distance dialled before a reset is not this putt's (RAM
             * only: the stored copy goes at the next change of the settings) */
            app->settings.manual_distance_cm = 0u;
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
    info_view_(app);
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
    if (app->ship_pending) {
        const int32_t d = (int32_t)(app->ship_due_ms - now);
        if (d < (int32_t)wait) {
            wait = (d > 0) ? (uint32_t)d : 1u;
        }
    }
    {
        const uint32_t f = gl_factory_time_left_ms(app, now);
        if (f != 0u && f < wait) {
            wait = f;
        }
    }
    /* Never sleep over a VBUS level that has not been dealt with: if it
     * changed during this pass (spring-pin bounce, a marker lifted out while
     * the loop was busy), the next pass handles it first - USB is not left
     * started and CHG_INHIBIT is not left asserted into a sleep, not even
     * one that the pending edge would end at once. */
    gl_power_poll_pins(&app->power);
    if (!app->power.vbus && app->power.inhibit) {
        /* Rule (B) of drivers/power.h, at the last place it can be applied:
         * VBUS went away between the reading the gate decided on and now
         * (the measurement before the gate takes a millisecond; found by the
         * bounce stress of tests/test_e2e_review.c).  The stop is released
         * here, whatever else is pending. */
        charge_gate_(app, now);
    }
    if (app->power.vbus != app->vbus_acted) {
        return;
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
    /* E30: a result older than GL_APP_RECALL_MAX_AGE_MS is not offered again
     * (decided here, every 16 s, so that the 49.7-day wrap of the tick can
     * never make an old result young) */
    if (app->view.have_result && !app->recall_spoiled &&
        (uint32_t)(now - app->result_ms) > GL_APP_RECALL_MAX_AGE_MS) {
        app->recall_spoiled = true;
    }
    /* the IMU is switched off on purpose in storage mode, asleep in the
     * cradle and on the way into ship mode */
    const bool imu_off = app->storage_mode || app->cradle_sleep || app->ship_pending ||
                         gl_factory_sleep_no_motion(app);
    app->sleep_ticks++;
    if (!app->imu_ok) {
        imu_recover_(app, now);
    } else if (!imu_off) {
        const gl_status_t st = gl_imu_verify(&app->imu);
        if (st != GL_OK) {
            imu_failed_(app, st, now);
        }
    }
    /* (VBUS itself is looked at on EVERY wake-up, by gl_app_run_once; in the
     * cradle the supervision measures the cell every few seconds) */
    if (!imu_off && (app->sleep_ticks % GL_APP_SLEEP_BATT_EVERY) == 0u) {
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
    uint32_t irq;
    uint32_t now;
    gl_event_t e;

    if (app->halted) {
        return; /* HOST BUILD ONLY: in ship mode; the target is in Shutdown */
    }
    irq = gl_hal_irq_take();
    now = gl_hal_tick_ms();
    app->loops++;
    if (!app->wdg_hold) {
        gl_hal_watchdog_kick();
    }

    /* 1. interrupt sources -> work.  VBUS is acted on by its LEVEL: the
     * pin is read at every pass (awake: every few milliseconds; asleep: at
     * the 16 s housekeeping wake-up at the latest) and compared with the
     * level last dealt with.  With the edge interrupt alone, one lost latch
     * left the charger unsupervised for good, or the marker awake in the
     * cradle state until the cell was flat. */
    gl_power_poll_pins(&app->power);
    if ((irq & (GL_IRQ_VBUS_CHANGE | GL_IRQ_CHG_STAT)) != 0u || app->power.vbus != app->vbus_acted) {
        vbus_edge_(app, now);
    }
    if (app->vbus_pending && (int32_t)(now - app->vbus_settle_ms) >= 0) {
        vbus_settled_(app, now);
    }
    /* The USB supply of the MCU, by its LEVEL like VBUS: the supply-valid bit
     * must not stay set when the supply has gone - and the supply goes about
     * 20 ms before VBUS_SENSE says so (gl_hal_usb_supply_ok). */
    if ((app->usb_on || app->usb_standby) && !gl_hal_usb_supply_ok()) {
        usb_stop_(app);
    }
    if ((irq & GL_IRQ_USB_WAKE) != 0u && app->usb_standby) {
        gl_app_post(app, GL_EV_USB_RESUME, 0); /* the host has resumed the bus */
    }
    if (app->ship_pending && !app->awake && !app->vbus_pending &&
        app->ui.state == (uint8_t)GL_UI_SLEEP && (int32_t)(now - app->ship_due_ms) >= 0) {
        ship_enter_(app);
        if (app->halted) {
            return;
        }
        /* VBUS was back: not entered */
        app->ship_pending = false;
    }
    if (!app->awake) {
        if ((irq & GL_IRQ_IMU_INT1) != 0u && !app->cradle_sleep && !app->ship_pending) {
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
        if (app->zero.active && app->zero.step >= 3u &&
            (uint32_t)(now - app->zero.saved_at_ms) >= GL_APP_ZERO_SAVED_MS) {
            app->zero.active = false;
            gl_app_post(app, GL_EV_CAL_DONE, 0);
        }
    }
    /* Charge supervision: every GL_APP_CHG_TEMP_PERIOD_MS for as long as
     * VBUS is SEEN, awake or not (it used to hang on `awake`, which a lost
     * edge never set).  And the staleness limit is a limit on the loop, not
     * on the measurement: if the supervision does not come round, for
     * whatever reason, the reading it left behind goes stale and the gate
     * stops the charge ("unknown" is "stop"). */
    if (app->power.vbus) {
        if ((int32_t)(now - app->next_chg_ms) >= 0 && !app->capture_active && !app->tilt_active) {
            charge_supervise_(app, now);
            /* USB could not be started when the cradle state was entered (its
             * supply was not up yet): try again */
            if (app->ui.state == (uint8_t)GL_UI_CRADLE_USB && !app->usb_on && gl_hal_usb_supply_ok()) {
                usb_start_(app);
            }
        } else if (!app->power.inhibit &&
                   (!app->cell_seen ||
                    (uint32_t)(now - app->cell_temp_ms) > GL_APP_CELL_TEMP_MAX_AGE_MS)) {
            charge_gate_(app, now);
        }
    }
    if (app->usb_on) {
        gl_usb_service(app, now);
        /* E32: the cradle state lasts for as long as a host talks.  "Talks":
         * it has sent something, it is being sent a stream it asked for, or
         * a log erase it started is running. */
        if (app->ui.state == (uint8_t)GL_UI_CRADLE_USB &&
            (app->usb_activity || app->log_erasing || app->six.active || app->fac.pattern != 0u ||
             (app->stream_mask != 0u && gl_hal_usb_connected()))) {
            gl_ui_keepalive(&app->ui, now);
        }
        app->usb_activity = false;
    }
    /* E34: this image has run its main loop for a while - tell the boot stub
     * (it would otherwise count this start as one that ended badly if a
     * watchdog reset follows) */
    if (!app->boot_confirmed && (uint32_t)(now - app->boot_ms) >= GL_APP_BOOT_CONFIRM_MS) {
        app->boot_confirmed = true;
        gl_hal_boot_confirm();
    }
    gl_factory_service(app, now);
    /* the work above can take real time (a capture start waits for the
     * sensor, a raw strip takes half a second to log): the UI is given the
     * time as it is NOW, never an older one than it has already seen */
    now = gl_hal_tick_ms();
    do_actions_(app, gl_ui_tick(&app->ui, now), now);

    /* 3. events -> transition table -> actions */
    while (gl_event_get(&app->events, &e)) {
        uint32_t a;
        if (gl_factory_holds_ui(app) && e.type != (uint8_t)GL_EV_USB_ATTACH &&
            e.type != (uint8_t)GL_EV_USB_DETACH && e.type != (uint8_t)GL_EV_FORCE_SLEEP &&
            e.type != (uint8_t)GL_EV_BATT_LOW && e.type != (uint8_t)GL_EV_FAULT) {
            /* a display pattern is being shown on the factory's seat plate:
             * the marker lies under a camera with nothing on its pads, and
             * neither stillness nor a gesture starts a read (app/gl_factory.c) */
            continue;
        }
        a = gl_ui_dispatch(&app->ui, (gl_ui_event_t)e.type, e.arg, now);
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
