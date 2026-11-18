/*
 * gl_usb.c - the USB side of the application: binds the callbacks of
 * core/gl_proto (settings, calibration, log dump, live streams, reboot to
 * the ROM bootloader) to the device, and moves bytes between the CDC port
 * of the HAL and the protocol parser.
 *
 * USB exists only while the marker sits in the charging / data cradle.
 *
 * Stack: gl_usb_service() about 200 bytes + the protocol's dispatch (the
 * frame buffers live in gl_proto_t, not on the stack).
 */
#include <string.h>

#include "gl_app.h"
#include "gl_config.h"
#include "gl_hal.h"
#include "grain_frontend.h"

/* ---- transport ------------------------------------------------------------------ */

static void tx_(void *ctx, const uint8_t *frame, size_t len)
{
    const uint32_t t0 = gl_hal_tick_ms();
    size_t done = 0;
    (void)ctx;
    /* the CDC layer may take a frame in pieces; give up after 50 ms (host
     * gone or not reading): frames are self-delimiting and CRC-protected */
    while (done < len) {
        const size_t n = gl_hal_usb_write(frame + done, len - done);
        done += n;
        if (n == 0u) {
            if (!gl_hal_usb_connected() || (uint32_t)(gl_hal_tick_ms() - t0) > 50u) {
                break;
            }
            gl_hal_delay_ms(1);
        }
    }
}

/* ---- protocol callbacks ------------------------------------------------------------ */

static gl_status_t get_info_(void *ctx, gl_proto_info_t *info)
{
    (void)ctx;
    memset(info, 0, sizeof(*info));
    info->proto_version = (uint8_t)GL_PROTO_VERSION;
    info->hw_rev = (uint8_t)GL_APP_HW_REV;
    info->fw_version = (uint16_t)GL_APP_FW_VERSION;
    info->fw_build = GL_APP_FW_BUILD;
    info->solver_version = gl_solver_version();
    gl_hal_unique_id(info->unique_id);
    info->uptime_s = gl_hal_tick_ms() / 1000u;
    return GL_OK;
}

static gl_status_t get_status_(void *ctx, gl_proto_status_t *st)
{
    const gl_app_t *app = (const gl_app_t *)ctx;
    memset(st, 0, sizeof(*st));
    st->battery_mv = app->power.batt_mv;
    st->temperature_c_x10 =
        app->temp_valid ? (int16_t)gl_roundi(gl_clampf(app->temp_c, -100.0f, 200.0f) * 10.0f)
                        : (int16_t)INT16_MIN;
    st->ui_state = app->ui.state;
    st->flags = (uint8_t)((app->power.vbus ? 1u : 0u) | (app->power.charging ? 2u : 0u) |
                          (app->power.charge_enabled ? 4u : 0u) | (app->proto.unlocked ? 8u : 0u) |
                          (app->ship_armed ? 16u : 0u));
    st->last_error = app->last_error;
    st->reads_total = app->reads_total;
    st->rtc_s = gl_hal_rtc_seconds();
    return GL_OK;
}

static gl_status_t get_settings_(void *ctx, gl_settings_t *s)
{
    *s = ((const gl_app_t *)ctx)->settings;
    return GL_OK;
}

static gl_status_t set_settings_(void *ctx, const gl_settings_t *s)
{
    gl_app_t *app = (gl_app_t *)ctx;
    app->redraw = true;
    return gl_app_set_settings(app, s);
}

static gl_status_t get_cal_(void *ctx, uint8_t cal_id, uint8_t *blob, size_t cap, size_t *len)
{
    const gl_app_t *app = (const gl_app_t *)ctx;
    if (cap < GL_CAL_MAX_BLOB_LEN) {
        return GL_ERR_FULL;
    }
    switch (cal_id) {
    case GL_CAL_ID_TILT:
        gl_cal_tilt_encode(&app->cal_tilt, blob);
        *len = GL_CAL_TILT_BLOB_LEN;
        return GL_OK;
    case GL_CAL_ID_CAM_L:
    case GL_CAL_ID_CAM_R:
        gl_cal_cam_encode(&app->cal_cam[(cal_id == GL_CAL_ID_CAM_L) ? GL_CAM_LEFT : GL_CAM_RIGHT],
                          blob);
        *len = GL_CAL_CAM_BLOB_LEN;
        return GL_OK;
    case GL_CAL_ID_GRAIN:
        gl_cal_grain_encode(&app->cal_grain, blob);
        *len = GL_CAL_GRAIN_BLOB_LEN;
        return GL_OK;
    case GL_CAL_ID_DEVICE:
        gl_cal_device_encode(&app->cal_dev, blob);
        *len = GL_CAL_DEVICE_BLOB_LEN;
        return GL_OK;
    default:
        return GL_ERR_NOT_FOUND;
    }
}

/* SET_CAL.  The record is decoded into a temporary, stored, and adopted in
 * RAM only when the store has acknowledged it: a refused or failed command
 * changes NOTHING.  The length must be exactly that of the record in ITS
 * version: a version-1 record (a backup made with phase-2 firmware) is
 * accepted and converted, and what is stored is always the present version
 * (encoded again from the decoded values, CRC and all).  The device record
 * must carry the serial of the unique number IT carries (checked by its
 * decoder); that number need not be this processor's - GET_IDENT says
 * whether it is. */
static gl_status_t set_cal_(void *ctx, uint8_t cal_id, const uint8_t *blob, size_t len)
{
    gl_app_t *app = (gl_app_t *)ctx;
    const bool v1 = (len >= 1u && blob[0] == GL_CAL_VERSION_PHASE1);
    gl_status_t st;

    switch (cal_id) {
    case GL_CAL_ID_TILT: {
        const gl_cal_tilt_t before = app->cal_tilt;
        gl_cal_tilt_t tilt;
        if (len != (v1 ? GL_CAL_TILT_BLOB_LEN_V1 : GL_CAL_TILT_BLOB_LEN)) {
            return GL_ERR_PARAM;
        }
        st = gl_cal_tilt_decode(blob, len, &tilt);
        if (st != GL_OK) {
            return st;
        }
        app->cal_tilt = tilt;
        st = gl_app_cal_store(app, cal_id);
        if (st != GL_OK) {
            app->cal_tilt = before;
        }
        return st;
    }
    case GL_CAL_ID_CAM_L:
    case GL_CAL_ID_CAM_R: {
        const gl_cam_id_t c = (cal_id == GL_CAL_ID_CAM_L) ? GL_CAM_LEFT : GL_CAM_RIGHT;
        const gl_cal_cam_t before = app->cal_cam[c];
        gl_cal_cam_t cam;
        if (len != (v1 ? GL_CAL_CAM_BLOB_LEN_V1 : GL_CAL_CAM_BLOB_LEN)) {
            return GL_ERR_PARAM;
        }
        st = gl_cal_cam_decode(blob, len, &cam);
        if (st != GL_OK) {
            return st;
        }
        app->cal_cam[c] = cam;
        st = gl_app_cal_store(app, cal_id);
        if (st != GL_OK) {
            app->cal_cam[c] = before;
            return st;
        }
        gl_read_set_cal(&app->read, &app->cal_cam[GL_CAM_LEFT], &app->cal_cam[GL_CAM_RIGHT]);
        return GL_OK;
    }
    case GL_CAL_ID_GRAIN: {
        const gl_cal_grain_t before = app->cal_grain;
        gl_cal_grain_t grain;
        if (len != (v1 ? GL_CAL_GRAIN_BLOB_LEN_V1 : GL_CAL_GRAIN_BLOB_LEN)) {
            return GL_ERR_PARAM;
        }
        st = gl_cal_grain_decode(blob, len, &grain);
        if (st != GL_OK) {
            return st;
        }
        app->cal_grain = grain;
        st = gl_app_cal_store(app, cal_id);
        if (st != GL_OK) {
            app->cal_grain = before;
        }
        return st;
    }
    case GL_CAL_ID_DEVICE: {
        const gl_cal_device_t before = app->cal_dev;
        gl_cal_device_t dev;
        if (len != GL_CAL_DEVICE_BLOB_LEN) {
            return GL_ERR_PARAM;
        }
        st = gl_cal_device_decode(blob, len, &dev);
        if (st != GL_OK) {
            return st;
        }
        app->cal_dev = dev;
        st = gl_app_cal_store(app, cal_id);
        if (st != GL_OK) {
            app->cal_dev = before;
            return st;
        }
        app->view.display_rot_rad = dev.display_rot_rad;
        app->redraw = true;
        return GL_OK;
    }
    default:
        return GL_ERR_NOT_FOUND;
    }
}

static gl_status_t start_cal_(void *ctx, uint8_t procedure, uint8_t arg)
{
    return gl_app_start_cal((gl_app_t *)ctx, procedure, arg);
}

static gl_status_t log_info_(void *ctx, gl_proto_log_info_t *info)
{
    const gl_app_t *app = (const gl_app_t *)ctx;
    gl_log_stats_t s;
    gl_status_t st;
    if (!app->storage_ok) {
        return GL_ERR_NOT_FOUND;
    }
    st = gl_log_stats(&app->log, &s);
    if (st != GL_OK) {
        return st;
    }
    info->record_count = s.record_estimate;
    info->bytes_used = s.bytes_used;
    info->bytes_capacity = s.bytes_capacity;
    info->newest_seq = s.newest_seq;
    return GL_OK;
}

static gl_status_t log_read_(void *ctx, bool restart, uint8_t *buf, size_t cap, size_t *len,
                             bool *more)
{
    gl_app_t *app = (gl_app_t *)ctx;
    *len = 0;
    *more = false;
    if (!app->storage_ok) {
        return GL_ERR_NOT_FOUND;
    }
    if (app->log_erasing) {
        return GL_ERR_BUSY;
    }
    if (restart) {
        app->log_seek_seq = 0; /* from the oldest record */
    }
    if (restart || !app->log_iter_valid) {
        gl_log_iter_begin(&app->log, &app->log_iter);
        app->log_iter_valid = true;
    }
    for (;;) {
        const gl_log_iter_t before = app->log_iter;
        gl_log_rec_t rec;
        size_t need;
        gl_status_t st = gl_log_iter_next(&app->log, &app->log_iter, &rec, NULL, 0);
        if (st == GL_ERR_EMPTY) {
            app->log_iter_valid = false; /* the newest record has been returned */
            return GL_OK;
        }
        if (st != GL_OK) {
            return st;
        }
        if (rec.seq < app->log_seek_seq) {
            continue; /* GL_CMD_LOG_SEEK: the host has this record already */
        }
        need = 8u + (size_t)rec.len;
        if (need > cap) {
            continue; /* can never fit one response: skipped (none are written that large) */
        }
        if (*len + need > cap) {
            app->log_iter = before; /* next call starts with this record */
            *more = true;
            return GL_OK;
        }
        buf[*len] = rec.type;
        buf[*len + 1u] = rec.flags;
        gl_put_u16(&buf[*len + 2u], rec.len);
        gl_put_u32(&buf[*len + 4u], rec.seq);
        st = gl_log_read_payload(&app->log, &rec, 0, &buf[*len + 8u], rec.len);
        if (st != GL_OK) {
            return st;
        }
        *len += need;
    }
}

/* LOG_SEEK: the download resumes at record `seq`.  The iterator is put on
 * the sector that holds it (2044 header reads at most, as at the mount);
 * the records in front of it in that sector are skipped by log_read_(). */
static gl_status_t log_seek_(void *ctx, uint32_t seq)
{
    gl_app_t *app = (gl_app_t *)ctx;
    gl_status_t st;
    if (!app->storage_ok) {
        return GL_ERR_NOT_FOUND;
    }
    if (app->log_erasing) {
        return GL_ERR_BUSY;
    }
    st = gl_log_iter_seek(&app->log, &app->log_iter, seq);
    app->log_iter_valid = (st == GL_OK);
    app->log_seek_seq = seq;
    return st;
}

static gl_status_t log_erase_(void *ctx)
{
    gl_app_t *app = (gl_app_t *)ctx;
    if (!app->storage_ok) {
        return GL_ERR_NOT_FOUND;
    }
    /* 2044 sectors at tens of ms each: done a sector at a time from the main
     * loop; LOG_READ answers GL_ERR_BUSY until it has finished, and so does
     * every append to the log (core/gl_log: an append in the middle of an
     * erase used to leave a stale sector that came back after a reset).
     * Events and reads that happen meanwhile are not logged. */
    app->log_erasing = true;
    app->log_erase_cursor = 0;
    app->log_iter_valid = false;
    return GL_OK;
}

static gl_status_t stream_(void *ctx, uint16_t source_mask, uint16_t period_ms)
{
    gl_app_t *app = (gl_app_t *)ctx;
    const uint16_t supported = (uint16_t)((1u << GL_STREAM_IMU) | (1u << GL_STREAM_TILT) |
                                          (1u << GL_STREAM_GRAIN) | (1u << GL_STREAM_POWER));
    if ((source_mask & (uint16_t)~supported) != 0u) {
        return GL_ERR_UNSUPPORTED; /* VISION and STRIP: nothing to look at in the cradle */
    }
    app->stream_mask = source_mask;
    app->stream_period_ms = period_ms;
    app->stream_next_ms = gl_hal_tick_ms() + period_ms;
    return GL_OK;
}

static gl_status_t set_time_(void *ctx, uint32_t rtc_s)
{
    (void)ctx;
    gl_hal_rtc_set_seconds(rtc_s);
    return GL_OK;
}

/* In the ROM bootloader CHG_INHIBIT is high-Z: the charger runs on its own,
 * inside ITS temperature window (rev E: it has a thermistor of its own),
 * which is wider than the firmware's - it goes on to 60 C at a reduced
 * voltage - and with no time limit but the charger's.  The firmware cannot
 * change that; what it does is refuse to go there unless its own gate is
 * satisfied right now (VBUS present, temperature known, plausible and well
 * inside ITS window), so that an update starts from a permitted
 * temperature. */
static bool dfu_allowed_(void *ctx)
{
    const gl_app_t *app = (const gl_app_t *)ctx;
    return app->power.vbus && app->power.temp_ok;
}

/* ---- rev E: ship mode, the power report, the factory's charge stop ----------------- */

static gl_status_t ship_mode_(void *ctx, bool arm, bool *armed)
{
    *armed = gl_app_ship_mode_arm((gl_app_t *)ctx, arm);
    return GL_OK;
}

static int16_t temp_x10_(bool valid, float t)
{
    return valid ? (int16_t)gl_roundi(gl_clampf(t, -100.0f, 200.0f) * 10.0f)
                 : (int16_t)GL_PROTO_TEMP_NONE;
}

static gl_status_t get_power_(void *ctx, gl_proto_power_t *pw)
{
    gl_app_t *app = (gl_app_t *)ctx;
    const gl_power_t *p = &app->power;
    const gl_status_t st = gl_app_power_refresh(app); /* measured now (not during a read) */
    const bool fresh = (st == GL_OK);
    const uint32_t minutes = p->chg_run_ms / 60000u;

    pw->battery_mv = p->batt_mv;
    pw->cell_temp_c_x10 = temp_x10_(p->cell_temp_valid, p->cell_temp_c);
    pw->mcu_temp_c_x10 = temp_x10_(p->mcu_temp_valid, p->mcu_temp_c);
    pw->imu_temp_c_x10 = temp_x10_(app->temp_valid, app->temp_c);
    pw->ntc_fault = p->ntc_fault;
    pw->chg_status = p->chg_status;
    pw->chg_reason = p->chg_reason;
    pw->cradle = (uint8_t)gl_app_cradle_state(app);
    pw->flags = (uint16_t)((p->vbus ? GL_PROTO_PWR_VBUS : 0u) |
                           (p->charging ? GL_PROTO_PWR_CHG_LOW : 0u) |
                           (p->inhibit ? GL_PROTO_PWR_INHIBIT : 0u) |
                           (gl_hal_usb_supply_ok() ? GL_PROTO_PWR_USB_SUPPLY : 0u) |
                           (app->ship_armed ? GL_PROTO_PWR_SHIP_ARMED : 0u) |
                           (p->read_hot ? GL_PROTO_PWR_READ_HOT : 0u) |
                           (p->ntc1_suspect ? GL_PROTO_PWR_NTC1_SUSPECT : 0u) |
                           (p->time_limit ? GL_PROTO_PWR_TIME_LIMIT : 0u) |
                           (p->forced ? GL_PROTO_PWR_FORCED : 0u) |
                           (fresh ? GL_PROTO_PWR_CELL_FRESH : 0u));
    pw->charge_min = (uint16_t)((minutes > 65535u) ? 65535u : minutes);
    /* a measurement that failed still gets an answer: the fields say what
     * is not valid (ntc_fault, GL_PROTO_TEMP_NONE) */
    return (st == GL_ERR_BUSY) ? GL_ERR_BUSY : GL_OK;
}

static gl_status_t set_charge_(void *ctx, bool stop)
{
    gl_app_t *app = (gl_app_t *)ctx;
    if (!app->power.vbus) {
        return GL_ERR_STATE;
    }
    gl_power_charge_force(&app->power, stop);
    (void)gl_app_power_refresh(app); /* takes effect, and is seen, at once */
    return GL_OK;
}

static gl_status_t reboot_(void *ctx, bool rom_dfu)
{
    gl_app_t *app = (gl_app_t *)ctx;
    if (rom_dfu && !dfu_allowed_(ctx)) {
        return GL_ERR_STATE; /* (already refused by the protocol layer) */
    }
    /* carried out from the main loop, after the response has had time to
     * leave the transmit buffer */
    app->reboot_pending = true;
    app->reboot_how = (uint8_t)(rom_dfu ? GL_REBOOT_ROM_DFU : GL_REBOOT_NORMAL);
    return GL_OK;
}

void gl_usb_bind(gl_app_t *app)
{
    memset(&app->ops, 0, sizeof(app->ops));
    app->ops.ctx = app;
    app->ops.tx = tx_;
    app->ops.get_info = get_info_;
    app->ops.get_status = get_status_;
    app->ops.get_settings = get_settings_;
    app->ops.set_settings = set_settings_;
    app->ops.get_cal = get_cal_;
    app->ops.set_cal = set_cal_;
    app->ops.start_cal = start_cal_;
    app->ops.log_info = log_info_;
    app->ops.log_read = log_read_;
    app->ops.log_erase = log_erase_;
    app->ops.stream = stream_;
    app->ops.set_time = set_time_;
    app->ops.reboot = reboot_;
    app->ops.dfu_allowed = dfu_allowed_;
    app->ops.ship_mode = ship_mode_;
    app->ops.get_power = get_power_;
    app->ops.set_charge = set_charge_;
    app->ops.factory = gl_factory_cmd;
    app->ops.log_seek = log_seek_;
    gl_proto_init(&app->proto, &app->ops);
}

/* ---- live streams for the factory ------------------------------------------------- */

void gl_usb_stream_imu(gl_app_t *app, const gl_imu_raw_t *s)
{
    app->last_raw = *s;
}

static void streams_(gl_app_t *app)
{
    uint8_t p[96];
    if ((app->stream_mask & (1u << GL_STREAM_IMU)) != 0u) {
        /* accel xyz, gyro xyz (raw counts, marker axes), temperature x 100 */
        gl_put_u16(&p[0], (uint16_t)app->last_raw.ax);
        gl_put_u16(&p[2], (uint16_t)app->last_raw.ay);
        gl_put_u16(&p[4], (uint16_t)app->last_raw.az);
        gl_put_u16(&p[6], (uint16_t)app->last_raw.gx);
        gl_put_u16(&p[8], (uint16_t)app->last_raw.gy);
        gl_put_u16(&p[10], (uint16_t)app->last_raw.gz);
        gl_put_u16(&p[12], (uint16_t)(int16_t)gl_roundi(gl_clampf(app->temp_c, -300.0f, 300.0f) *
                                                         100.0f));
        (void)gl_proto_send_stream(&app->proto, GL_STREAM_IMU, p, 14);
    }
    if ((app->stream_mask & (1u << GL_STREAM_TILT)) != 0u) {
        /* calibrated slope of the newest 133 ms block (x, y as f32, rise/run),
         * 1 = that block was still */
        gl_vec3_t a;
        gl_vec2_t slope = { 0.0f, 0.0f };
        a.x = app->motion.avg.prev_mean_a[0];
        a.y = app->motion.avg.prev_mean_a[1];
        a.z = app->motion.avg.prev_mean_a[2];
        a = gl_tilt_apply_cal(&app->cal_tilt, a, app->temp_valid ? app->temp_c : app->cal_tilt.t0_c);
        (void)gl_tilt_slope(a, &slope);
        {
            /* the zero a read would remove now (the SURFACE setting, E11) */
            gl_vec2_t zero;
            (void)gl_cal_tilt_zero(&app->cal_tilt, (gl_cal_seat_t)app->settings.surface, &zero);
            gl_put_f32(&p[0], slope.x - zero.x);
            gl_put_f32(&p[4], slope.y - zero.y);
        }
        p[8] = gl_tilt_avg_last_still(&app->motion.avg) ? 1u : 0u;
        (void)gl_proto_send_stream(&app->proto, GL_STREAM_TILT, p, 9);
    }
    if ((app->stream_mask & (1u << GL_STREAM_POWER)) != 0u) {
        gl_power_poll_pins(&app->power);
        (void)gl_power_measure(&app->power);
        gl_put_u16(&p[0], app->power.batt_mv);
        p[2] = (uint8_t)((app->power.vbus ? 1u : 0u) | (app->power.charging ? 2u : 0u) |
                         (app->power.charge_enabled ? 4u : 0u));
        p[3] = app->power.percent;
        (void)gl_proto_send_stream(&app->proto, GL_STREAM_POWER, p, 4);
    }
    if ((app->stream_mask & (1u << GL_STREAM_GRAIN)) != 0u) {
        /* one cycle: 16 x (dark, on, dark) as uint16 */
        static gl_grain_raw_t raw;
        if (gl_grain_fe_measure(&raw, 1) == GL_OK) {
            for (unsigned led = 0; led < GL_GRAIN_LEDS; led++) {
                gl_put_u16(&p[6u * led], raw.s[0][led].dark1);
                gl_put_u16(&p[6u * led + 2u], raw.s[0][led].on);
                gl_put_u16(&p[6u * led + 4u], raw.s[0][led].dark2);
            }
            (void)gl_proto_send_stream(&app->proto, GL_STREAM_GRAIN, p, 96);
        }
    }
}

void gl_usb_service(gl_app_t *app, uint32_t now_ms)
{
    uint8_t buf[64];
    /* bounded: at most 1 kB per loop iteration, so the IMU pump is not starved */
    for (unsigned i = 0; i < 16u; i++) {
        const size_t n = gl_hal_usb_read(buf, sizeof(buf));
        if (n == 0u) {
            break;
        }
        app->usb_last_rx_ms = now_ms;
        app->usb_activity = true;
        gl_proto_feed(&app->proto, buf, n);
    }
    /* a partial frame left behind by a host that stopped mid-frame */
    if (app->proto.rx_end != app->proto.rx_start &&
        (uint32_t)(now_ms - app->usb_last_rx_ms) > 100u) {
        gl_proto_rx_reset(&app->proto);
    }
    if (app->stream_mask != 0u && (int32_t)(now_ms - app->stream_next_ms) >= 0) {
        app->stream_next_ms = now_ms + app->stream_period_ms;
        if (gl_hal_usb_connected()) {
            streams_(app);
        }
    }
    if (app->log_erasing) {
        const gl_status_t est = gl_log_erase_all(&app->log, &app->log_erase_cursor, 1);
        if (est != GL_ERR_BUSY) {
            app->log_erasing = false;
            if (est != GL_OK) {
                /* flash error: give the log back to its users in whatever
                 * consistent state it is in (oldest sectors gone) */
                gl_log_erase_cancel(&app->log);
                app->last_error = (uint16_t)est;
            }
        }
    }
    if (app->reboot_pending) {
        gl_hal_delay_ms(20); /* let the response leave */
        app->reboot_pending = false;
        if (app->reboot_how == (uint8_t)GL_REBOOT_ROM_DFU) {
            /* Rev E board: the IMU's two interrupt lines sit on pins the ROM
             * loader listens on as an SPI clock and data input (NETLIST_NOTES
             * 3.5, firmware note 11).  Leave them STATIC: the IMU is powered
             * down, which unroutes data-ready from INT2 and the wake-up from
             * INT1.  The display goes off too (its pull-down would do that at
             * the reset anyway). */
            (void)gl_imu_stop(&app->imu);
            gl_lcd_off(&app->lcd);
        }
        gl_hal_reboot((gl_reboot_t)app->reboot_how);
        /* NOT REACHED ON THE TARGET.  The host backend records the request
         * and returns: put back what was switched off for the ROM loader, so
         * that a test can go on with the same application object. */
        if (app->reboot_how == (uint8_t)GL_REBOOT_ROM_DFU && app->awake) {
            (void)gl_lcd_on(&app->lcd);
            if (app->imu_ok && gl_imu_start_measure(&app->imu) != GL_OK) {
                app->imu_ok = false;
            }
            app->last_sample_ms = gl_hal_tick_ms();
            app->redraw = true;
        }
    }
}
