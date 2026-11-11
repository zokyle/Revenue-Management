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
                          (app->power.charge_enabled ? 4u : 0u) | (app->proto.unlocked ? 8u : 0u));
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
    switch (cal_id) {
    case GL_CAL_ID_TILT:
        if (cap < GL_CAL_TILT_BLOB_LEN) {
            return GL_ERR_FULL;
        }
        gl_cal_tilt_encode(&app->cal_tilt, blob);
        *len = GL_CAL_TILT_BLOB_LEN;
        return GL_OK;
    case GL_CAL_ID_CAM_L:
    case GL_CAL_ID_CAM_R:
        if (cap < GL_CAL_CAM_BLOB_LEN) {
            return GL_ERR_FULL;
        }
        gl_cal_cam_encode(&app->cal_cam[(cal_id == GL_CAL_ID_CAM_L) ? GL_CAM_LEFT : GL_CAM_RIGHT],
                          blob);
        *len = GL_CAL_CAM_BLOB_LEN;
        return GL_OK;
    case GL_CAL_ID_GRAIN:
        if (cap < GL_CAL_GRAIN_BLOB_LEN) {
            return GL_ERR_FULL;
        }
        gl_cal_grain_encode(&app->cal_grain, blob);
        *len = GL_CAL_GRAIN_BLOB_LEN;
        return GL_OK;
    default:
        return GL_ERR_NOT_FOUND;
    }
}

/* SET_CAL.  The record is decoded into a temporary, stored, and adopted in
 * RAM only when the store has acknowledged it: a refused or failed command
 * changes NOTHING (it used to decode straight into the live calibration and
 * then fail in the store when the frame carried trailing bytes, leaving RAM
 * and flash different until the next reset).  The length must be exactly
 * that of the record. */
static gl_status_t set_cal_(void *ctx, uint8_t cal_id, const uint8_t *blob, size_t len)
{
    gl_app_t *app = (gl_app_t *)ctx;
    gl_status_t st;
    gl_cal_tilt_t tilt;
    gl_cal_cam_t cam;
    gl_cal_grain_t grain;

    switch (cal_id) {
    case GL_CAL_ID_TILT:
        if (len != GL_CAL_TILT_BLOB_LEN) {
            return GL_ERR_PARAM;
        }
        st = gl_cal_tilt_decode(blob, len, &tilt);
        if (st == GL_OK) {
            st = gl_app_store_put(app, (uint8_t)GL_STORE_ID_CAL_TILT, blob, len);
        }
        if (st == GL_OK) {
            app->cal_tilt = tilt;
        }
        return st;
    case GL_CAL_ID_CAM_L:
    case GL_CAL_ID_CAM_R: {
        const gl_cam_id_t c = (cal_id == GL_CAL_ID_CAM_L) ? GL_CAM_LEFT : GL_CAM_RIGHT;
        if (len != GL_CAL_CAM_BLOB_LEN) {
            return GL_ERR_PARAM;
        }
        st = gl_cal_cam_decode(blob, len, &cam);
        if (st == GL_OK) {
            st = gl_app_store_put(app, (uint8_t)((c == GL_CAM_LEFT) ? GL_STORE_ID_CAL_CAM_L
                                                                    : GL_STORE_ID_CAL_CAM_R),
                                  blob, len);
        }
        if (st == GL_OK) {
            app->cal_cam[c] = cam;
            gl_read_set_cal(&app->read, &app->cal_cam[GL_CAM_LEFT], &app->cal_cam[GL_CAM_RIGHT]);
        }
        return st;
    }
    case GL_CAL_ID_GRAIN:
        if (len != GL_CAL_GRAIN_BLOB_LEN) {
            return GL_ERR_PARAM;
        }
        st = gl_cal_grain_decode(blob, len, &grain);
        if (st == GL_OK) {
            st = gl_app_store_put(app, (uint8_t)GL_STORE_ID_CAL_GRAIN, blob, len);
        }
        if (st == GL_OK) {
            app->cal_grain = grain;
        }
        return st;
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

/* In the ROM bootloader CHG_INHIBIT is high-Z: the charger runs on its
 * hardware default and NOTHING supervises the cell temperature, for as long
 * as the host keeps the device there.  The firmware cannot change that; what
 * it can do is refuse to go there unless the charge gate is satisfied right
 * now (VBUS present, temperature known, plausible and well inside the
 * window). */
static bool dfu_allowed_(void *ctx)
{
    const gl_app_t *app = (const gl_app_t *)ctx;
    return app->power.vbus && app->power.temp_ok;
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
        gl_put_f32(&p[0], slope.x - app->cal_tilt.flip_bias_x);
        gl_put_f32(&p[4], slope.y - app->cal_tilt.flip_bias_y);
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
        gl_hal_reboot((gl_reboot_t)app->reboot_how);
        /* not reached on the target */
    }
}
