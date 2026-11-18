/* gl_proto.c - USB protocol framing and command dispatch.  See gl_proto.h. */
#include "gl_proto.h"

#include <string.h>

#include "gl_buf.h"
#include "gl_crc.h"

/* ---- encoding ---------------------------------------------------------- */

size_t gl_proto_encode(uint8_t *out, size_t cap, uint8_t seq, uint8_t cmd, const uint8_t *payload,
                       size_t len)
{
    uint16_t crc;
    if (out == NULL || len > GL_PROTO_MAX_PAYLOAD || cap < len + GL_PROTO_OVERHEAD ||
        (payload == NULL && len != 0u)) {
        return 0;
    }
    out[0] = (uint8_t)GL_PROTO_SOF0;
    out[1] = (uint8_t)GL_PROTO_SOF1;
    gl_put_u16(&out[2], (uint16_t)len);
    out[4] = seq;
    out[5] = cmd;
    if (len != 0u && payload != &out[6]) {
        memmove(&out[6], payload, len);
    }
    crc = gl_crc16(&out[2], len + 4u);
    gl_put_u16(&out[6u + len], crc);
    return len + GL_PROTO_OVERHEAD;
}

void gl_proto_info_encode(const gl_proto_info_t *info, uint8_t out[GL_PROTO_INFO_LEN])
{
    gl_wr_t w;
    gl_wr_init(&w, out, GL_PROTO_INFO_LEN);
    gl_wr_u8(&w, info->proto_version);
    gl_wr_u8(&w, info->hw_rev);
    gl_wr_u16(&w, info->fw_version);
    gl_wr_u32(&w, info->fw_build);
    gl_wr_u32(&w, info->solver_version);
    gl_wr_bytes(&w, info->unique_id, sizeof(info->unique_id));
    gl_wr_u32(&w, info->uptime_s);
}

void gl_proto_status_encode(const gl_proto_status_t *st, uint8_t out[GL_PROTO_STATUS_LEN])
{
    gl_wr_t w;
    gl_wr_init(&w, out, GL_PROTO_STATUS_LEN);
    gl_wr_u16(&w, st->battery_mv);
    gl_wr_i16(&w, st->temperature_c_x10);
    gl_wr_u8(&w, st->ui_state);
    gl_wr_u8(&w, st->flags);
    gl_wr_u16(&w, st->last_error);
    gl_wr_u32(&w, st->reads_total);
    gl_wr_u32(&w, st->rtc_s);
}

void gl_proto_log_info_encode(const gl_proto_log_info_t *li, uint8_t out[GL_PROTO_LOG_INFO_LEN])
{
    gl_wr_t w;
    gl_wr_init(&w, out, GL_PROTO_LOG_INFO_LEN);
    gl_wr_u32(&w, li->record_count);
    gl_wr_u32(&w, li->bytes_used);
    gl_wr_u32(&w, li->bytes_capacity);
    gl_wr_u32(&w, li->newest_seq);
}

void gl_proto_power_encode(const gl_proto_power_t *pw, uint8_t out[GL_PROTO_POWER_LEN])
{
    gl_wr_t w;
    gl_wr_init(&w, out, GL_PROTO_POWER_LEN);
    gl_wr_u16(&w, pw->battery_mv);
    gl_wr_i16(&w, pw->cell_temp_c_x10);
    gl_wr_i16(&w, pw->mcu_temp_c_x10);
    gl_wr_i16(&w, pw->imu_temp_c_x10);
    gl_wr_u8(&w, pw->ntc_fault);
    gl_wr_u8(&w, pw->chg_status);
    gl_wr_u8(&w, pw->chg_reason);
    gl_wr_u8(&w, pw->cradle);
    gl_wr_u16(&w, pw->flags);
    gl_wr_u16(&w, pw->charge_min);
}

void gl_proto_ident_encode(const gl_proto_ident_t *id, uint8_t out[GL_PROTO_IDENT_LEN])
{
    gl_wr_t w;
    gl_wr_init(&w, out, GL_PROTO_IDENT_LEN);
    gl_wr_u8(&w, id->proto_version);
    gl_wr_u8(&w, id->agreed_version);
    gl_wr_u8(&w, id->hw_rev);
    gl_wr_u8(&w, (uint8_t)id->hw_letter);
    gl_wr_bytes(&w, id->model, sizeof(id->model));
    gl_wr_u16(&w, id->fw_version);
    gl_wr_u8(&w, id->cal_version);
    gl_wr_u8(&w, id->log_layout);
    gl_wr_u32(&w, id->fw_build);
    gl_wr_u32(&w, id->solver_version);
    gl_wr_bytes(&w, id->unique_id, sizeof(id->unique_id));
    gl_wr_u32(&w, id->serial);
    gl_wr_u32(&w, id->serial_stored);
    gl_wr_bytes(&w, id->cal_flags, sizeof(id->cal_flags));
    gl_wr_u8(&w, id->flags);
    gl_wr_bytes(&w, id->params_rev, sizeof(id->params_rev));
    gl_wr_bytes(&w, id->commands, sizeof(id->commands));
}

void gl_proto_sensors_encode(const gl_proto_sensors_t *s, uint8_t out[GL_PROTO_SENSORS_LEN])
{
    gl_wr_t w;
    gl_wr_init(&w, out, GL_PROTO_SENSORS_LEN);
    gl_wr_u16(&w, s->battery_mv);
    gl_wr_u16(&w, s->vdda_mv);
    gl_wr_i16(&w, s->cell_temp_c_x10);
    gl_wr_i16(&w, s->mcu_temp_c_x10);
    gl_wr_i16(&w, s->imu_temp_c_x10);
    gl_wr_u16(&w, s->ntc_counts);
    gl_wr_u16(&w, s->ntc_full_scale);
    gl_wr_u8(&w, s->ntc_fault);
    gl_wr_u8(&w, s->flags);
    gl_wr_u8(&w, s->sleep_wake);
    gl_wr_u8(&w, s->sleep_mask);
    gl_wr_u32(&w, s->sleep_ms);
    gl_wr_u32(&w, s->uptime_ms);
    gl_wr_u16(&w, 0);
}

void gl_proto_capture_encode(const gl_proto_capture_t *c, uint8_t out[GL_PROTO_CAPTURE_LEN])
{
    gl_wr_t w;
    gl_wr_init(&w, out, GL_PROTO_CAPTURE_LEN);
    gl_wr_u8(&w, c->camera);
    gl_wr_u8(&w, c->kind);
    gl_wr_u16(&w, c->x0);
    gl_wr_u16(&w, c->y0);
    gl_wr_u16(&w, c->width);
    gl_wr_u16(&w, c->height);
    gl_wr_u32(&w, c->bytes);
    gl_wr_u8(&w, c->min);
    gl_wr_u8(&w, c->max);
    gl_wr_u16(&w, c->mean_x16);
    gl_wr_u32(&w, c->bright);
    gl_wr_u32(&w, c->crc32);
}

void gl_proto_field_encode(const gl_proto_field_t *f, uint8_t out[GL_PROTO_FIELD_LEN])
{
    gl_wr_t w;
    gl_wr_init(&w, out, GL_PROTO_FIELD_LEN);
    gl_wr_u8(&w, f->camera);
    gl_wr_u8(&w, f->status);
    gl_wr_u16(&w, f->row_upper);
    gl_wr_u16(&w, f->row_lower);
    gl_wr_u16(&w, f->mean_upper_x16);
    gl_wr_u16(&w, f->mean_lower_x16);
    gl_wr_u16(&w, f->mean_centre_x16);
    gl_wr_u16(&w, f->ratio_x1000);
    gl_wr_u8(&w, f->max_upper);
    gl_wr_u8(&w, f->max_lower);
    gl_wr_u32(&w, 0);
}

void gl_proto_grain_encode(const gl_proto_grain_t *g, uint8_t out[GL_PROTO_GRAIN_LEN])
{
    gl_wr_t w;
    gl_wr_init(&w, out, GL_PROTO_GRAIN_LEN);
    gl_wr_u8(&w, g->mode);
    gl_wr_u8(&w, g->status);
    gl_wr_u16(&w, g->dark_mean);
    gl_wr_u16(&w, g->dark_min);
    gl_wr_u16(&w, g->dark_max);
    gl_wr_u16(&w, g->full_scale);
    gl_wr_u16(&w, g->stored_dark);
    for (int i = 0; i < 16; i++) {
        for (int j = 0; j < 3; j++) {
            gl_wr_u16(&w, g->led[i][j]);
        }
    }
}

void gl_proto_zero_encode(const gl_proto_zero_t *z, uint8_t out[GL_PROTO_ZERO_LEN])
{
    gl_wr_t w;
    gl_wr_init(&w, out, GL_PROTO_ZERO_LEN);
    gl_wr_u8(&w, z->state);
    gl_wr_u8(&w, z->seat);
    gl_wr_u8(&w, z->status);
    gl_wr_u8(&w, z->attempts);
    gl_wr_f32(&w, z->bias_x);
    gl_wr_f32(&w, z->bias_y);
    gl_wr_f32(&w, z->scatter);
    gl_wr_f32(&w, z->turn_rad);
    gl_wr_f32(&w, z->surface_x);
    gl_wr_f32(&w, z->surface_y);
    gl_wr_f32(&w, z->temp_c);
    gl_wr_u32(&w, z->time_s);
}

void gl_proto_six_encode(const gl_proto_six_t *x, uint8_t out[GL_PROTO_SIX_LEN])
{
    gl_wr_t w;
    gl_wr_init(&w, out, GL_PROTO_SIX_LEN);
    gl_wr_u8(&w, x->done_mask);
    gl_wr_u8(&w, x->active);
    gl_wr_u8(&w, x->face);
    gl_wr_u8(&w, x->cal_flags);
    for (int i = 0; i < 6; i++) {
        for (int j = 0; j < 3; j++) {
            gl_wr_f32(&w, x->mean[i][j]);
        }
    }
    gl_wr_f32(&w, x->temp_c);
}

/* ---- command handlers --------------------------------------------------- */
/* Each handler reads the request payload (in, n) and appends response data
 * to `out` (positioned after the status byte).  It returns the status. */

typedef gl_status_t (*handler_fn)(gl_proto_t *p, const uint8_t *in, size_t n, gl_wr_t *out);

static gl_status_t h_ping(gl_proto_t *p, const uint8_t *in, size_t n, gl_wr_t *out)
{
    (void)p;
    gl_wr_bytes(out, in, n);
    return GL_OK;
}

static gl_status_t h_get_info(gl_proto_t *p, const uint8_t *in, size_t n, gl_wr_t *out)
{
    gl_proto_info_t info;
    uint8_t blob[GL_PROTO_INFO_LEN];
    gl_status_t st;
    (void)in;
    (void)n;
    if (p->ops->get_info == NULL) {
        return GL_ERR_UNSUPPORTED;
    }
    memset(&info, 0, sizeof(info));
    st = p->ops->get_info(p->ops->ctx, &info);
    if (st == GL_OK) {
        info.proto_version = (uint8_t)GL_PROTO_VERSION;
        gl_proto_info_encode(&info, blob);
        gl_wr_bytes(out, blob, sizeof(blob));
    }
    return st;
}

static gl_status_t h_get_status(gl_proto_t *p, const uint8_t *in, size_t n, gl_wr_t *out)
{
    gl_proto_status_t s;
    uint8_t blob[GL_PROTO_STATUS_LEN];
    gl_status_t st;
    (void)in;
    (void)n;
    if (p->ops->get_status == NULL) {
        return GL_ERR_UNSUPPORTED;
    }
    memset(&s, 0, sizeof(s));
    st = p->ops->get_status(p->ops->ctx, &s);
    if (st == GL_OK) {
        s.flags = (uint8_t)((s.flags & 0xF7u) | (p->unlocked ? 0x08u : 0u));
        gl_proto_status_encode(&s, blob);
        gl_wr_bytes(out, blob, sizeof(blob));
    }
    return st;
}

static gl_status_t h_get_settings(gl_proto_t *p, const uint8_t *in, size_t n, gl_wr_t *out)
{
    gl_settings_t s;
    uint8_t blob[GL_SETTINGS_BLOB_LEN];
    gl_status_t st;
    (void)in;
    (void)n;
    if (p->ops->get_settings == NULL) {
        return GL_ERR_UNSUPPORTED;
    }
    gl_settings_defaults(&s);
    st = p->ops->get_settings(p->ops->ctx, &s);
    if (st == GL_OK) {
        gl_settings_encode(&s, blob);
        gl_wr_bytes(out, blob, sizeof(blob));
    }
    return st;
}

static gl_status_t h_set_settings(gl_proto_t *p, const uint8_t *in, size_t n, gl_wr_t *out)
{
    gl_settings_t s;
    gl_status_t st;
    (void)out;
    if (p->ops->set_settings == NULL) {
        return GL_ERR_UNSUPPORTED;
    }
    st = gl_settings_decode(in, n, &s);
    if (st != GL_OK) {
        return st;
    }
    return p->ops->set_settings(p->ops->ctx, &s);
}

static gl_status_t h_get_cal(gl_proto_t *p, const uint8_t *in, size_t n, gl_wr_t *out)
{
    size_t len = 0;
    size_t room;
    gl_status_t st;
    (void)n;
    if (p->ops->get_cal == NULL) {
        return GL_ERR_UNSUPPORTED;
    }
    gl_wr_u8(out, in[0]);
    room = out->cap - out->len;
    st = p->ops->get_cal(p->ops->ctx, in[0], out->p + out->len, room, &len);
    if (st == GL_OK) {
        if (len > room) {
            return GL_ERR_FULL;
        }
        out->len += len;
    }
    return st;
}

static gl_status_t h_set_cal(gl_proto_t *p, const uint8_t *in, size_t n, gl_wr_t *out)
{
    (void)out;
    if (p->ops->set_cal == NULL) {
        return GL_ERR_UNSUPPORTED;
    }
    if (!p->unlocked) {
        return GL_ERR_STATE;
    }
    return p->ops->set_cal(p->ops->ctx, in[0], &in[1], n - 1u);
}

static gl_status_t h_start_cal(gl_proto_t *p, const uint8_t *in, size_t n, gl_wr_t *out)
{
    (void)n;
    (void)out;
    if (p->ops->start_cal == NULL) {
        return GL_ERR_UNSUPPORTED;
    }
    /* Every procedure that measures for, or writes, stored calibration is a
     * factory operation and needs UNLOCK, like SET_CAL.  ABORT only stops
     * one, and ZERO is passed on so that the host gets the application's
     * defined refusal (it cannot run in the cradle). */
    if (!p->unlocked && in[0] != (uint8_t)GL_CALPROC_ABORT && in[0] != (uint8_t)GL_CALPROC_ZERO) {
        return GL_ERR_STATE;
    }
    return p->ops->start_cal(p->ops->ctx, in[0], in[1]);
}

static gl_status_t h_log_info(gl_proto_t *p, const uint8_t *in, size_t n, gl_wr_t *out)
{
    gl_proto_log_info_t li;
    uint8_t blob[GL_PROTO_LOG_INFO_LEN];
    gl_status_t st;
    (void)in;
    (void)n;
    if (p->ops->log_info == NULL) {
        return GL_ERR_UNSUPPORTED;
    }
    memset(&li, 0, sizeof(li));
    st = p->ops->log_info(p->ops->ctx, &li);
    if (st == GL_OK) {
        gl_proto_log_info_encode(&li, blob);
        gl_wr_bytes(out, blob, sizeof(blob));
    }
    return st;
}

static gl_status_t h_log_read(gl_proto_t *p, const uint8_t *in, size_t n, gl_wr_t *out)
{
    size_t len = 0;
    size_t room;
    bool more = false;
    gl_status_t st;
    (void)n;
    if (p->ops->log_read == NULL) {
        return GL_ERR_UNSUPPORTED;
    }
    room = out->cap - out->len - 1u; /* one byte for the "more" flag */
    st = p->ops->log_read(p->ops->ctx, in[0] != 0u, out->p + out->len + 1u, room, &len, &more);
    if (st == GL_OK) {
        if (len > room) {
            return GL_ERR_FULL;
        }
        out->p[out->len] = more ? 1u : 0u;
        out->len += 1u + len;
    }
    return st;
}

static gl_status_t h_log_erase(gl_proto_t *p, const uint8_t *in, size_t n, gl_wr_t *out)
{
    (void)n;
    (void)out;
    if (p->ops->log_erase == NULL) {
        return GL_ERR_UNSUPPORTED;
    }
    if (!p->unlocked) {
        return GL_ERR_STATE;
    }
    if (memcmp(in, "ERAS", 4) != 0) {
        return GL_ERR_PARAM;
    }
    return p->ops->log_erase(p->ops->ctx);
}

static gl_status_t h_stream(gl_proto_t *p, const uint8_t *in, size_t n, gl_wr_t *out)
{
    uint16_t mask = gl_get_u16(&in[0]);
    uint16_t period = gl_get_u16(&in[2]);
    (void)n;
    (void)out;
    if (p->ops->stream == NULL) {
        return GL_ERR_UNSUPPORTED;
    }
    if ((mask >> GL_STREAM_COUNT) != 0u || (mask != 0u && period < 5u)) {
        return GL_ERR_RANGE;
    }
    return p->ops->stream(p->ops->ctx, mask, period);
}

static gl_status_t h_set_time(gl_proto_t *p, const uint8_t *in, size_t n, gl_wr_t *out)
{
    (void)n;
    (void)out;
    if (p->ops->set_time == NULL) {
        return GL_ERR_UNSUPPORTED;
    }
    return p->ops->set_time(p->ops->ctx, gl_get_u32(in));
}

static gl_status_t h_unlock(gl_proto_t *p, const uint8_t *in, size_t n, gl_wr_t *out)
{
    (void)n;
    (void)out;
    p->unlocked = (memcmp(in, "GLFC", 4) == 0);
    return p->unlocked ? GL_OK : GL_ERR_PARAM;
}

static gl_status_t h_reboot(gl_proto_t *p, const uint8_t *in, size_t n, gl_wr_t *out)
{
    (void)n;
    (void)out;
    if (p->ops->reboot == NULL) {
        return GL_ERR_UNSUPPORTED;
    }
    if (memcmp(in, "BOOT", 4) != 0 && memcmp(in, "DFU!", 4) != 0) {
        return GL_ERR_PARAM;
    }
    /* The ROM bootloader has no time-out and the consumer cradle has no
     * reset contact: a device sent there stays there until a host makes it
     * leave.  Only an unlocked (factory / service) session may do that.  A
     * plain reset is harmless and stays open. */
    if (memcmp(in, "DFU!", 4) == 0 && !p->unlocked) {
        return GL_ERR_STATE;
    }
    /* The application may have a reason of its own to refuse the ROM
     * bootloader right now. */
    if (memcmp(in, "DFU!", 4) == 0 && p->ops->dfu_allowed != NULL &&
        !p->ops->dfu_allowed(p->ops->ctx)) {
        return GL_ERR_STATE;
    }
    return GL_OK; /* the reboot itself happens after the response is sent */
}

static gl_status_t h_ship_mode(gl_proto_t *p, const uint8_t *in, size_t n, gl_wr_t *out)
{
    bool armed = false;
    gl_status_t st;
    (void)n;
    if (p->ops->ship_mode == NULL) {
        return GL_ERR_UNSUPPORTED;
    }
    if (memcmp(in, "SHIP", 4) != 0 && memcmp(in, "STAY", 4) != 0) {
        return GL_ERR_PARAM;
    }
    st = p->ops->ship_mode(p->ops->ctx, memcmp(in, "SHIP", 4) == 0, &armed);
    if (st == GL_OK) {
        gl_wr_u8(out, armed ? 1u : 0u);
    }
    return st;
}

static gl_status_t h_get_power(gl_proto_t *p, const uint8_t *in, size_t n, gl_wr_t *out)
{
    gl_proto_power_t pw;
    uint8_t blob[GL_PROTO_POWER_LEN];
    gl_status_t st;
    (void)in;
    (void)n;
    if (p->ops->get_power == NULL) {
        return GL_ERR_UNSUPPORTED;
    }
    memset(&pw, 0, sizeof(pw));
    st = p->ops->get_power(p->ops->ctx, &pw);
    if (st == GL_OK) {
        gl_proto_power_encode(&pw, blob);
        gl_wr_bytes(out, blob, sizeof(blob));
    }
    return st;
}

static gl_status_t h_set_charge(gl_proto_t *p, const uint8_t *in, size_t n, gl_wr_t *out)
{
    (void)n;
    (void)out;
    if (p->ops->set_charge == NULL) {
        return GL_ERR_UNSUPPORTED;
    }
    if (!p->unlocked) {
        return GL_ERR_STATE; /* a factory operation, like SET_CAL */
    }
    if (in[0] > 1u) {
        return GL_ERR_PARAM;
    }
    return p->ops->set_charge(p->ops->ctx, in[0] != 0u);
}

static gl_status_t h_log_seek(gl_proto_t *p, const uint8_t *in, size_t n, gl_wr_t *out)
{
    (void)n;
    (void)out;
    if (p->ops->log_seek == NULL) {
        return GL_ERR_UNSUPPORTED;
    }
    return p->ops->log_seek(p->ops->ctx, gl_get_u32(in));
}

/* The factory and calibration commands: length and unlock were checked by
 * the dispatcher, the application does the rest. */
static gl_status_t h_factory(gl_proto_t *p, const uint8_t *in, size_t n, gl_wr_t *out)
{
    (void)p;
    (void)in;
    (void)n;
    (void)out;
    return GL_ERR_UNSUPPORTED; /* never called: dispatch_() routes these itself */
}

typedef struct {
    uint8_t cmd;
    uint16_t min_len;
    uint16_t max_len;
    handler_fn fn;
} cmd_entry_t;

static const cmd_entry_t cmd_table_[] = {
    { GL_CMD_PING, 0, 64, h_ping },
    { GL_CMD_GET_INFO, 0, 0, h_get_info },
    { GL_CMD_GET_STATUS, 0, 0, h_get_status },
    { GL_CMD_GET_SETTINGS, 0, 0, h_get_settings },
    { GL_CMD_SET_SETTINGS, GL_SETTINGS_BLOB_LEN, GL_SETTINGS_BLOB_LEN, h_set_settings },
    { GL_CMD_GET_CAL, 1, 1, h_get_cal },
    { GL_CMD_SET_CAL, 2, 257, h_set_cal },
    { GL_CMD_START_CAL, 2, 2, h_start_cal },
    { GL_CMD_LOG_INFO, 0, 0, h_log_info },
    { GL_CMD_LOG_READ, 1, 1, h_log_read },
    { GL_CMD_LOG_ERASE, 4, 4, h_log_erase },
    { GL_CMD_STREAM, 4, 4, h_stream },
    { GL_CMD_SET_TIME, 4, 4, h_set_time },
    { GL_CMD_UNLOCK, 4, 4, h_unlock },
    { GL_CMD_REBOOT, 4, 4, h_reboot },
    { GL_CMD_SHIP_MODE, 4, 4, h_ship_mode },
    { GL_CMD_GET_POWER, 0, 0, h_get_power },
    { GL_CMD_SET_CHARGE, 1, 1, h_set_charge },
    /* phase 3 (payload lengths; the values are checked by the application) */
    { GL_CMD_GET_IDENT, 0, 1, h_factory },
    { GL_CMD_GET_SENSORS, 0, 0, h_factory },
    { GL_CMD_CAM_ID, 1, 1, h_factory },
    { GL_CMD_CAM_CAPTURE, 10, 10, h_factory },
    { GL_CMD_CAM_DATA, 6, 6, h_factory },
    { GL_CMD_CAM_FIELD, 1, 1, h_factory },
    { GL_CMD_DISPLAY_TEST, 2, 2, h_factory },
    { GL_CMD_GRAIN_TEST, 1, 1, h_factory },
    { GL_CMD_LEVEL_ZERO, 2, 2, h_factory },
    { GL_CMD_CAL_STATUS, 0, 0, h_factory },
    { GL_CMD_TILT_TEMPCO, 5u + 16u * GL_PROTO_TEMPCO_MIN_POINTS,
      5u + 16u * GL_PROTO_TEMPCO_MAX_POINTS, h_factory },
    { GL_CMD_SET_CAM_HORIZON, 9, 9, h_factory },
    { GL_CMD_SET_GRAIN_FLOOR, 1u + 4u * GL_PROTO_FLOOR_MIN_READINGS,
      1u + 4u * GL_PROTO_FLOOR_MAX_READINGS, h_factory },
    { GL_CMD_DISPLAY_ROT, 1, 5, h_factory },
    { GL_CMD_SLEEP_TEST, 3, 3, h_factory },
    { GL_CMD_LOG_SEEK, 4, 4, h_log_seek },
    { GL_CMD_SERIAL, 0, 4, h_factory },
};

/* What each command needs to exist at all (the command bit map). */
static bool has_callback_(const gl_proto_t *p, uint8_t cmd)
{
    const gl_proto_ops_t *o = p->ops;
    switch (cmd) {
    case GL_CMD_PING: return true;
    case GL_CMD_GET_INFO: return o->get_info != NULL;
    case GL_CMD_GET_STATUS: return o->get_status != NULL;
    case GL_CMD_GET_SETTINGS: return o->get_settings != NULL;
    case GL_CMD_SET_SETTINGS: return o->set_settings != NULL;
    case GL_CMD_GET_CAL: return o->get_cal != NULL;
    case GL_CMD_SET_CAL: return o->set_cal != NULL;
    case GL_CMD_START_CAL: return o->start_cal != NULL;
    case GL_CMD_LOG_INFO: return o->log_info != NULL;
    case GL_CMD_LOG_READ: return o->log_read != NULL;
    case GL_CMD_LOG_ERASE: return o->log_erase != NULL;
    case GL_CMD_STREAM: return o->stream != NULL;
    case GL_CMD_SET_TIME: return o->set_time != NULL;
    case GL_CMD_UNLOCK: return true;
    case GL_CMD_REBOOT: return o->reboot != NULL;
    case GL_CMD_SHIP_MODE: return o->ship_mode != NULL;
    case GL_CMD_GET_POWER: return o->get_power != NULL;
    case GL_CMD_SET_CHARGE: return o->set_charge != NULL;
    case GL_CMD_LOG_SEEK: return o->log_seek != NULL;
    default:
        return cmd >= (uint8_t)GL_PROTO_CMD_FACTORY_FIRST &&
               cmd <= (uint8_t)GL_PROTO_CMD_FACTORY_LAST && o->factory != NULL;
    }
}

void gl_proto_command_map(const gl_proto_t *p, uint8_t out[8])
{
    memset(out, 0, 8);
    for (size_t i = 0; i < GL_ARRAY_LEN(cmd_table_); i++) {
        const uint8_t c = cmd_table_[i].cmd;
        if (c < 64u && has_callback_(p, c)) {
            out[c >> 3] |= (uint8_t)(1u << (c & 7u));
        }
    }
}

bool gl_proto_needs_unlock(uint8_t cmd, const uint8_t *payload, size_t n)
{
    switch (cmd) {
    case GL_CMD_SET_CAL:
    case GL_CMD_LOG_ERASE:
    case GL_CMD_SET_CHARGE:
    case GL_CMD_TILT_TEMPCO:
    case GL_CMD_SET_CAM_HORIZON:
    case GL_CMD_SET_GRAIN_FLOOR:
    case GL_CMD_SLEEP_TEST:
        return true;
    case GL_CMD_START_CAL:
        /* ABORT only stops a procedure; ZERO is passed on so that the host
         * gets the application's defined refusal */
        return n >= 1u && payload[0] != (uint8_t)GL_CALPROC_ABORT &&
               payload[0] != (uint8_t)GL_CALPROC_ZERO;
    case GL_CMD_REBOOT:
        return n == 4u && memcmp(payload, "DFU!", 4) == 0;
    case GL_CMD_SHIP_MODE:
        return n == 4u && memcmp(payload, "SHIP", 4) == 0;
    case GL_CMD_LEVEL_ZERO:
        return n >= 1u && payload[0] == (uint8_t)GL_ZERO_OP_ARM;
    case GL_CMD_GRAIN_TEST:
        return n >= 1u && payload[0] == (uint8_t)GL_GRAIN_MODE_STORE;
    case GL_CMD_DISPLAY_ROT:
        return n >= 1u && payload[0] != 0u;
    case GL_CMD_SERIAL:
        return n != 0u;
    default:
        return false;
    }
}

static void dispatch_(gl_proto_t *p, uint8_t seq, uint8_t cmd, const uint8_t *payload, size_t n)
{
    gl_status_t st = GL_ERR_UNSUPPORTED;
    const cmd_entry_t *e = NULL;
    gl_wr_t w;
    size_t flen;

    /* Responses and stream frames arriving on our input are ignored. */
    if ((cmd & (GL_PROTO_RESPONSE_FLAG | GL_PROTO_STREAM_FLAG)) != 0u) {
        return;
    }
    /* Response data is built in place after the header and the status byte. */
    gl_wr_init(&w, &p->tx[7], GL_PROTO_MAX_PAYLOAD - 1u);
    for (size_t i = 0; i < GL_ARRAY_LEN(cmd_table_); i++) {
        if (cmd_table_[i].cmd == cmd) {
            e = &cmd_table_[i];
            break;
        }
    }
    if (e != NULL) {
        if (!has_callback_(p, cmd)) {
            st = GL_ERR_UNSUPPORTED;
        } else if (n < e->min_len || n > e->max_len) {
            st = GL_ERR_PARAM;
        } else if (!p->unlocked && gl_proto_needs_unlock(cmd, payload, n)) {
            st = GL_ERR_STATE; /* the unlock rule (gl_proto.h) */
        } else if (e->fn == h_factory) {
            size_t len = 0;
            st = p->ops->factory(p->ops->ctx, cmd, payload, n, w.p, w.cap, &len);
            if (st == GL_OK) {
                if (len > w.cap) {
                    st = GL_ERR_FULL;
                } else {
                    w.len = len;
                }
            }
        } else {
            st = e->fn(p, payload, n, &w);
        }
    }
    if (st != GL_OK || !w.ok) {
        if (st == GL_OK) {
            st = GL_ERR_FULL;
        }
        w.len = 0; /* errors carry the status byte only */
    }
    p->tx[6] = (uint8_t)st;
    flen = gl_proto_encode(p->tx, sizeof(p->tx), seq, (uint8_t)(cmd | GL_PROTO_RESPONSE_FLAG),
                           &p->tx[6], w.len + 1u);
    if (flen != 0u) {
        p->ops->tx(p->ops->ctx, p->tx, flen);
    }
    if (cmd == GL_CMD_REBOOT && st == GL_OK) {
        (void)p->ops->reboot(p->ops->ctx, memcmp(payload, "DFU!", 4) == 0);
    }
}

/* ---- receiver ----------------------------------------------------------- */

void gl_proto_init(gl_proto_t *p, const gl_proto_ops_t *ops)
{
    memset(p, 0, sizeof(*p));
    p->ops = ops;
}

void gl_proto_rx_reset(gl_proto_t *p)
{
    p->stats.bytes_discarded += (uint32_t)(p->rx_end - p->rx_start);
    p->rx_start = 0;
    p->rx_end = 0;
}

void gl_proto_disconnect(gl_proto_t *p)
{
    gl_proto_rx_reset(p);
    p->unlocked = false;
    p->stream_seq = 0;
}

/* Extract and dispatch every complete frame currently buffered. */
static void process_(gl_proto_t *p)
{
    for (;;) {
        size_t avail = p->rx_end - p->rx_start;
        const uint8_t *b = &p->rx[p->rx_start];
        size_t n;
        uint16_t crc;

        if (avail == 0u) {
            break;
        }
        if (b[0] != GL_PROTO_SOF0) {
            /* skip to the next possible start of frame */
            const uint8_t *q = memchr(b, (int)GL_PROTO_SOF0, avail);
            size_t skip = (q == NULL) ? avail : (size_t)(q - b);
            p->rx_start += skip;
            p->stats.bytes_discarded += (uint32_t)skip;
            continue;
        }
        if (avail < 2u) {
            break;
        }
        if (b[1] != GL_PROTO_SOF1) {
            p->rx_start += 1u;
            p->stats.bytes_discarded += 1u;
            continue;
        }
        if (avail < 6u) {
            break;
        }
        n = gl_get_u16(&b[2]);
        if (n > GL_PROTO_MAX_PAYLOAD) {
            p->rx_start += 1u;
            p->stats.bytes_discarded += 1u;
            p->stats.length_errors++;
            continue;
        }
        if (avail < n + GL_PROTO_OVERHEAD) {
            break; /* wait for the rest */
        }
        crc = gl_crc16(&b[2], n + 4u);
        if (crc != gl_get_u16(&b[6u + n])) {
            p->rx_start += 1u;
            p->stats.bytes_discarded += 1u;
            p->stats.crc_errors++;
            continue;
        }
        p->stats.frames_ok++;
        /* Consume before dispatching: a handler may call gl_proto_rx_reset(). */
        p->rx_start += n + GL_PROTO_OVERHEAD;
        dispatch_(p, b[4], b[5], &b[6], n);
    }
    if (p->rx_start == p->rx_end) {
        p->rx_start = 0;
        p->rx_end = 0;
    }
}

void gl_proto_feed(gl_proto_t *p, const uint8_t *data, size_t len)
{
    while (len > 0u) {
        size_t room;
        size_t take;
        if (p->rx_end == sizeof(p->rx) && p->rx_start > 0u) {
            /* compact: move the partial frame to the front */
            memmove(p->rx, &p->rx[p->rx_start], p->rx_end - p->rx_start);
            p->rx_end -= p->rx_start;
            p->rx_start = 0;
        }
        room = sizeof(p->rx) - p->rx_end;
        if (room == 0u) {
            /* Cannot happen: a buffer full from rx_start = 0 always holds a
             * complete candidate frame, which process_() consumes or
             * rejects.  Defensive: drop one byte rather than spin. */
            p->rx_start = 1u;
            p->stats.bytes_discarded += 1u;
            process_(p);
            continue;
        }
        take = (len < room) ? len : room;
        memcpy(&p->rx[p->rx_end], data, take);
        p->rx_end += take;
        data += take;
        len -= take;
        process_(p);
    }
}

gl_status_t gl_proto_send_stream(gl_proto_t *p, gl_proto_stream_t source, const uint8_t *payload,
                                 size_t len)
{
    size_t flen;
    if ((unsigned)source >= (unsigned)GL_STREAM_COUNT) {
        return GL_ERR_PARAM;
    }
    flen = gl_proto_encode(p->tx, sizeof(p->tx), p->stream_seq,
                           (uint8_t)(GL_PROTO_STREAM_FLAG | (uint8_t)source), payload, len);
    if (flen == 0u) {
        return GL_ERR_PARAM;
    }
    p->stream_seq++;
    p->ops->tx(p->ops->ctx, p->tx, flen);
    return GL_OK;
}
