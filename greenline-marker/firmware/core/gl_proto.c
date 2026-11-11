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
    return GL_OK; /* the reboot itself happens after the response is sent */
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
};

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
        if (n < e->min_len || n > e->max_len) {
            st = GL_ERR_PARAM;
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
