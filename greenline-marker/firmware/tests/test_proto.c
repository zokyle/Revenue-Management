/*
 * test_proto.c - CRC-16, framing, resynchronisation on malformed input and
 * command dispatch of the USB protocol.
 */
#include <stdlib.h>

#include "gl_crc.h"
#include "gl_proto.h"
#include "gl_test.h"

/* ---- mock application --------------------------------------------------- */

static struct {
    uint8_t tx[8192];
    size_t tx_len;
    int tx_frames;
    gl_settings_t settings;
    int set_settings_calls;
    uint8_t cal_id;
    uint8_t cal_blob[300];
    size_t cal_len;
    int set_cal_calls;
    uint8_t calproc, calarg;
    int start_cal_calls;
    int log_erase_calls;
    int log_read_calls;
    bool log_restart;
    uint16_t stream_mask, stream_period;
    uint32_t time_s;
    int reboot_calls;
    bool reboot_dfu;
    int reboot_tx_frames_at_call;
} app;

static void m_tx(void *ctx, const uint8_t *frame, size_t len)
{
    (void)ctx;
    if (app.tx_len + len <= sizeof(app.tx)) {
        memcpy(&app.tx[app.tx_len], frame, len);
        app.tx_len += len;
    }
    app.tx_frames++;
}
static gl_status_t m_get_info(void *ctx, gl_proto_info_t *info)
{
    (void)ctx;
    info->hw_rev = 2;
    info->fw_version = 0x0102;
    info->fw_build = 0xDEADBEEFu;
    info->solver_version = 0;
    for (int i = 0; i < 12; i++) {
        info->unique_id[i] = (uint8_t)(0x10 + i);
    }
    info->uptime_s = 77;
    return GL_OK;
}
static gl_status_t m_get_status(void *ctx, gl_proto_status_t *st)
{
    (void)ctx;
    st->battery_mv = 3912;
    st->temperature_c_x10 = -53;
    st->ui_state = 9;
    st->flags = 0x03;
    st->last_error = 11;
    st->reads_total = 1234;
    st->rtc_s = 1700000000u;
    return GL_OK;
}
static gl_status_t m_get_settings(void *ctx, gl_settings_t *s)
{
    (void)ctx;
    *s = app.settings;
    return GL_OK;
}
static gl_status_t m_set_settings(void *ctx, const gl_settings_t *s)
{
    (void)ctx;
    app.settings = *s;
    app.set_settings_calls++;
    return GL_OK;
}
static gl_status_t m_get_cal(void *ctx, uint8_t id, uint8_t *blob, size_t cap, size_t *len)
{
    (void)ctx;
    if (id == GL_CAL_ID_GRAIN) {
        gl_cal_grain_t c;
        gl_cal_grain_defaults(&c);
        if (cap < GL_CAL_GRAIN_BLOB_LEN) {
            return GL_ERR_FULL;
        }
        gl_cal_grain_encode(&c, blob);
        *len = GL_CAL_GRAIN_BLOB_LEN;
        return GL_OK;
    }
    return GL_ERR_NOT_FOUND;
}
static gl_status_t m_set_cal(void *ctx, uint8_t id, const uint8_t *blob, size_t len)
{
    (void)ctx;
    app.cal_id = id;
    app.cal_len = len;
    memcpy(app.cal_blob, blob, len);
    app.set_cal_calls++;
    return GL_OK;
}
static gl_status_t m_start_cal(void *ctx, uint8_t proc, uint8_t arg)
{
    (void)ctx;
    app.calproc = proc;
    app.calarg = arg;
    app.start_cal_calls++;
    /* like the application: zeroing cannot run in the cradle (and USB exists
     * only there); the factory procedures can */
    return (proc == GL_CALPROC_ZERO) ? GL_ERR_STATE : GL_OK;
}
static gl_status_t m_log_info(void *ctx, gl_proto_log_info_t *li)
{
    (void)ctx;
    li->record_count = 3;
    li->bytes_used = 300;
    li->bytes_capacity = 8000000u;
    li->newest_seq = 42;
    return GL_OK;
}
static gl_status_t m_log_read(void *ctx, bool restart, uint8_t *buf, size_t cap, size_t *len,
                              bool *more)
{
    (void)ctx;
    app.log_read_calls++;
    app.log_restart = restart;
    /* fill the whole response to exercise the maximum frame size */
    memset(buf, 0xA5, cap);
    *len = cap;
    *more = restart;
    return GL_OK;
}
static gl_status_t m_log_erase(void *ctx)
{
    (void)ctx;
    app.log_erase_calls++;
    return GL_OK;
}
static gl_status_t m_stream(void *ctx, uint16_t mask, uint16_t period)
{
    (void)ctx;
    app.stream_mask = mask;
    app.stream_period = period;
    return GL_OK;
}
static gl_status_t m_set_time(void *ctx, uint32_t s)
{
    (void)ctx;
    app.time_s = s;
    return GL_OK;
}
static gl_status_t m_reboot(void *ctx, bool dfu)
{
    (void)ctx;
    app.reboot_calls++;
    app.reboot_dfu = dfu;
    app.reboot_tx_frames_at_call = app.tx_frames;
    return GL_OK;
}

static const gl_proto_ops_t ops = {
    NULL, m_tx, m_get_info, m_get_status, m_get_settings, m_set_settings, m_get_cal, m_set_cal,
    m_start_cal, m_log_info, m_log_read, m_log_erase, m_stream, m_set_time, m_reboot
};

static gl_proto_t proto;

static void fresh(void)
{
    memset(&app, 0, sizeof(app));
    gl_settings_defaults(&app.settings);
    gl_proto_init(&proto, &ops);
}

/* Send one request frame; returns the frame length. */
static size_t request(uint8_t seq, uint8_t cmd, const void *payload, size_t n)
{
    uint8_t f[GL_PROTO_MAX_FRAME];
    size_t len = gl_proto_encode(f, sizeof(f), seq, cmd, (const uint8_t *)payload, n);
    gl_proto_feed(&proto, f, len);
    return len;
}

/* Parse the idx-th transmitted frame.  Returns payload length or -1. */
static int response(int idx, uint8_t *seq, uint8_t *cmd, const uint8_t **payload)
{
    /* on failure the outputs point at zeros, so a failed check cannot turn
     * into a wild read in the lines that follow it */
    static const uint8_t none[GL_PROTO_MAX_FRAME];
    size_t pos = 0;
    *seq = 0;
    *cmd = 0;
    *payload = none;
    for (int i = 0; pos + GL_PROTO_OVERHEAD <= app.tx_len; i++) {
        size_t n = gl_get_u16(&app.tx[pos + 2]);
        if (app.tx[pos] != 0xA5 || app.tx[pos + 1] != 0x5A || pos + n + 8 > app.tx_len) {
            return -1;
        }
        if (gl_crc16(&app.tx[pos + 2], n + 4) != gl_get_u16(&app.tx[pos + 6 + n])) {
            return -1;
        }
        if (i == idx) {
            *seq = app.tx[pos + 4];
            *cmd = app.tx[pos + 5];
            *payload = &app.tx[pos + 6];
            return (int)n;
        }
        pos += n + 8;
    }
    return -1;
}

/* ---- tests ------------------------------------------------------------- */

GL_TEST(test_crc16_vectors)
{
    GL_CHECK_EQ(gl_crc16((const uint8_t *)"123456789", 9), 0x29B1);
    GL_CHECK_EQ(gl_crc16((const uint8_t *)"", 0), 0xFFFF);
    GL_CHECK_EQ(gl_crc16((const uint8_t *)"A", 1), 0xB915);
    /* incremental == one-shot */
    uint16_t c = gl_crc16_update(GL_CRC16_INIT, (const uint8_t *)"1234", 4);
    c = gl_crc16_update(c, (const uint8_t *)"56789", 5);
    GL_CHECK_EQ(c, 0x29B1);
    /* bitwise reference implementation over random data */
    srand(7);
    for (int t = 0; t < 50; t++) {
        uint8_t buf[97];
        size_t n = (size_t)(rand() % 97);
        uint16_t ref = 0xFFFF;
        for (size_t i = 0; i < n; i++) {
            buf[i] = (uint8_t)rand();
            ref = (uint16_t)(ref ^ ((unsigned)buf[i] << 8));
            for (int b = 0; b < 8; b++) {
                unsigned wide = (unsigned)ref << 1;
                if ((ref & 0x8000u) != 0u) {
                    wide ^= 0x1021u;
                }
                ref = (uint16_t)(wide & 0xFFFFu);
            }
        }
        GL_CHECK_EQ(gl_crc16(buf, n), ref);
    }
}

GL_TEST(test_encode_exact_bytes)
{
    uint8_t f[32];
    const uint8_t pl[3] = { 0x11, 0x22, 0x33 };
    size_t n = gl_proto_encode(f, sizeof(f), 0x07, GL_CMD_PING, pl, 3);
    GL_CHECK_EQ(n, 11);
    const uint8_t head[9] = { 0xA5, 0x5A, 0x03, 0x00, 0x07, 0x01, 0x11, 0x22, 0x33 };
    GL_CHECK_MEM(f, head, 9);
    uint16_t crc = gl_crc16(&f[2], 7);
    GL_CHECK_EQ(f[9], crc & 0xFF);
    GL_CHECK_EQ(f[10], crc >> 8);
    /* empty payload */
    n = gl_proto_encode(f, sizeof(f), 1, GL_CMD_GET_INFO, NULL, 0);
    GL_CHECK_EQ(n, 8);
    /* does not fit / too long / NULL payload with length */
    GL_CHECK_EQ(gl_proto_encode(f, 10, 0, 1, pl, 3), 0);
    GL_CHECK_EQ(gl_proto_encode(f, sizeof(f), 0, 1, NULL, 3), 0);
    {
        static uint8_t big[GL_PROTO_MAX_FRAME + 16], src[GL_PROTO_MAX_PAYLOAD + 1];
        GL_CHECK_EQ(gl_proto_encode(big, sizeof(big), 0, 1, src, GL_PROTO_MAX_PAYLOAD + 1), 0);
        GL_CHECK_EQ(gl_proto_encode(big, sizeof(big), 0, 1, src, GL_PROTO_MAX_PAYLOAD),
                    GL_PROTO_MAX_FRAME);
    }
}

GL_TEST(test_ping_roundtrip)
{
    uint8_t seq, cmd;
    const uint8_t *pl;
    fresh();
    request(0x42, GL_CMD_PING, "hello", 5);
    GL_CHECK_EQ(app.tx_frames, 1);
    GL_CHECK_EQ(response(0, &seq, &cmd, &pl), 6);
    GL_CHECK_EQ(seq, 0x42);
    GL_CHECK_EQ(cmd, GL_CMD_PING | 0x80);
    GL_CHECK_EQ(pl[0], GL_OK);
    GL_CHECK_MEM(&pl[1], "hello", 5);
    GL_CHECK_EQ(proto.stats.frames_ok, 1);
    GL_CHECK_EQ(proto.stats.crc_errors, 0);
}

GL_TEST(test_commands)
{
    uint8_t seq, cmd;
    const uint8_t *pl;
    uint8_t blob[GL_SETTINGS_BLOB_LEN];
    fresh();

    /* GET_INFO */
    request(1, GL_CMD_GET_INFO, NULL, 0);
    GL_CHECK_EQ(response(0, &seq, &cmd, &pl), 1 + (int)GL_PROTO_INFO_LEN);
    GL_CHECK_EQ(pl[0], GL_OK);
    GL_CHECK_EQ(pl[1], GL_PROTO_VERSION);
    GL_CHECK_EQ(pl[2], 2);
    GL_CHECK_EQ(gl_get_u16(&pl[3]), 0x0102);
    GL_CHECK_EQ(gl_get_u32(&pl[5]), 0xDEADBEEFu);
    GL_CHECK_EQ(pl[13], 0x10);
    GL_CHECK_EQ(gl_get_u32(&pl[25]), 77);

    /* GET_STATUS (locked: bit 3 clear) */
    request(2, GL_CMD_GET_STATUS, NULL, 0);
    GL_CHECK_EQ(response(1, &seq, &cmd, &pl), 1 + (int)GL_PROTO_STATUS_LEN);
    GL_CHECK_EQ(gl_get_u16(&pl[1]), 3912);
    GL_CHECK_EQ((int16_t)gl_get_u16(&pl[3]), -53);
    GL_CHECK_EQ(pl[5], 9);
    GL_CHECK_EQ(pl[6], 0x03);
    GL_CHECK_EQ(gl_get_u32(&pl[13]), 1700000000u);

    /* GET_SETTINGS returns the defaults */
    request(3, GL_CMD_GET_SETTINGS, NULL, 0);
    GL_CHECK_EQ(response(2, &seq, &cmd, &pl), 1 + (int)GL_SETTINGS_BLOB_LEN);
    GL_CHECK_EQ(pl[1], GL_SETTINGS_VERSION);
    GL_CHECK_EQ(pl[2], 20);  /* stimp 10.0 */
    GL_CHECK_EQ(pl[6], 0);   /* grain disabled by default */

    /* SET_SETTINGS valid */
    {
        gl_settings_t s;
        gl_settings_defaults(&s);
        s.stimp_x2 = 23;
        s.grass = GL_GRASS_BERMUDA;
        s.units = GL_UNITS_METRES;
        gl_settings_encode(&s, blob);
        request(4, GL_CMD_SET_SETTINGS, blob, sizeof(blob));
        GL_CHECK_EQ(response(3, &seq, &cmd, &pl), 1);
        GL_CHECK_EQ(pl[0], GL_OK);
        GL_CHECK_EQ(app.set_settings_calls, 1);
        GL_CHECK_EQ(app.settings.stimp_x2, 23);
        GL_CHECK_EQ(app.settings.grass, GL_GRASS_BERMUDA);
    }
    /* SET_SETTINGS out of range: rejected before reaching the app */
    blob[1] = 40;
    request(5, GL_CMD_SET_SETTINGS, blob, sizeof(blob));
    GL_CHECK_EQ(response(4, &seq, &cmd, &pl), 1);
    GL_CHECK_EQ(pl[0], GL_ERR_RANGE);
    GL_CHECK_EQ(app.set_settings_calls, 1);
    /* wrong payload size */
    request(6, GL_CMD_SET_SETTINGS, blob, 5);
    GL_CHECK_EQ(response(5, &seq, &cmd, &pl), 1);
    GL_CHECK_EQ(pl[0], GL_ERR_PARAM);
    GL_CHECK_EQ(seq, 6);
    GL_CHECK_EQ(cmd, GL_CMD_SET_SETTINGS | 0x80);

    /* GET_CAL: known and unknown id */
    {
        uint8_t id = GL_CAL_ID_GRAIN;
        gl_cal_grain_t c;
        request(7, GL_CMD_GET_CAL, &id, 1);
        GL_CHECK_EQ(response(6, &seq, &cmd, &pl), 2 + (int)GL_CAL_GRAIN_BLOB_LEN);
        GL_CHECK_EQ(pl[1], GL_CAL_ID_GRAIN);
        GL_CHECK_EQ(gl_cal_grain_decode(&pl[2], GL_CAL_GRAIN_BLOB_LEN, &c), GL_OK);
        GL_CHECK(c.mod_threshold > 0.2f);
        id = 99;
        request(8, GL_CMD_GET_CAL, &id, 1);
        GL_CHECK_EQ(response(7, &seq, &cmd, &pl), 1);
        GL_CHECK_EQ(pl[0], GL_ERR_NOT_FOUND);
    }

    /* START_CAL passes through, including the app's refusal (the session
     * is unlocked for the factory procedure; the lock itself is tested in
     * test_locked_commands_and_reboot) */
    {
        const uint8_t a[2] = { GL_CALPROC_ZERO, 0 }, b[2] = { GL_CALPROC_SIX_FACE, 4 };
        request(9, GL_CMD_START_CAL, a, 2);
        GL_CHECK_EQ(response(8, &seq, &cmd, &pl), 1);
        GL_CHECK_EQ(pl[0], GL_ERR_STATE);
        proto.unlocked = true;
        request(10, GL_CMD_START_CAL, b, 2);
        proto.unlocked = false;
        GL_CHECK_EQ(response(9, &seq, &cmd, &pl), 1);
        GL_CHECK_EQ(pl[0], GL_OK);
        GL_CHECK_EQ(app.calproc, GL_CALPROC_SIX_FACE);
        GL_CHECK_EQ(app.calarg, 4);
    }

    /* LOG_INFO, LOG_READ (maximum-size response) */
    request(11, GL_CMD_LOG_INFO, NULL, 0);
    GL_CHECK_EQ(response(10, &seq, &cmd, &pl), 1 + (int)GL_PROTO_LOG_INFO_LEN);
    GL_CHECK_EQ(gl_get_u32(&pl[13]), 42);
    {
        uint8_t restart = 1;
        request(12, GL_CMD_LOG_READ, &restart, 1);
        GL_CHECK_EQ(response(11, &seq, &cmd, &pl), (int)GL_PROTO_MAX_PAYLOAD);
        GL_CHECK_EQ(pl[0], GL_OK);
        GL_CHECK_EQ(pl[1], 1); /* more */
        GL_CHECK_EQ(pl[2], 0xA5);
        GL_CHECK_EQ(pl[GL_PROTO_MAX_PAYLOAD - 1], 0xA5);
        GL_CHECK(app.log_restart);
    }

    /* STREAM: mask validation */
    {
        uint8_t a[4];
        gl_put_u16(&a[0], (1u << GL_STREAM_IMU) | (1u << GL_STREAM_GRAIN));
        gl_put_u16(&a[2], 20);
        request(13, GL_CMD_STREAM, a, 4);
        GL_CHECK_EQ(response(12, &seq, &cmd, &pl), 1);
        GL_CHECK_EQ(pl[0], GL_OK);
        GL_CHECK_EQ(app.stream_mask, 0x05);
        GL_CHECK_EQ(app.stream_period, 20);
        gl_put_u16(&a[0], 0x8000);
        request(14, GL_CMD_STREAM, a, 4);
        GL_CHECK_EQ(response(13, &seq, &cmd, &pl), 1);
        GL_CHECK_EQ(pl[0], GL_ERR_RANGE);
        gl_put_u16(&a[0], 1);
        gl_put_u16(&a[2], 1); /* too fast */
        request(15, GL_CMD_STREAM, a, 4);
        GL_CHECK_EQ(response(14, &seq, &cmd, &pl), 1);
        GL_CHECK_EQ(pl[0], GL_ERR_RANGE);
        GL_CHECK_EQ(app.stream_mask, 0x05);
    }

    /* SET_TIME */
    {
        uint8_t a[4];
        gl_put_u32(a, 1731312000u);
        request(16, GL_CMD_SET_TIME, a, 4);
        GL_CHECK_EQ(app.time_s, 1731312000u);
    }

    /* unknown command */
    request(17, 0x3F, NULL, 0);
    GL_CHECK_EQ(response(16, &seq, &cmd, &pl), 1);
    GL_CHECK_EQ(pl[0], GL_ERR_UNSUPPORTED);
    GL_CHECK_EQ(cmd, 0x3F | 0x80);
    GL_CHECK_EQ(app.tx_frames, 17);
}

GL_TEST(test_locked_commands_and_reboot)
{
    uint8_t seq, cmd;
    const uint8_t *pl;
    uint8_t cal[1 + GL_CAL_GRAIN_BLOB_LEN];
    gl_cal_grain_t c;
    fresh();
    gl_cal_grain_defaults(&c);
    cal[0] = GL_CAL_ID_GRAIN;
    gl_cal_grain_encode(&c, &cal[1]);

    /* locked: SET_CAL and LOG_ERASE refused */
    request(1, GL_CMD_SET_CAL, cal, sizeof(cal));
    GL_CHECK_EQ(response(0, &seq, &cmd, &pl), 1);
    GL_CHECK_EQ(pl[0], GL_ERR_STATE);
    request(2, GL_CMD_LOG_ERASE, "ERAS", 4);
    GL_CHECK_EQ(response(1, &seq, &cmd, &pl), 1);
    GL_CHECK_EQ(pl[0], GL_ERR_STATE);
    GL_CHECK_EQ(app.set_cal_calls, 0);
    GL_CHECK_EQ(app.log_erase_calls, 0);
    /* wrong key */
    request(3, GL_CMD_UNLOCK, "nope", 4);
    GL_CHECK_EQ(response(2, &seq, &cmd, &pl), 1);
    GL_CHECK_EQ(pl[0], GL_ERR_PARAM);
    GL_CHECK(!proto.unlocked);
    /* right key */
    request(4, GL_CMD_UNLOCK, "GLFC", 4);
    GL_CHECK(proto.unlocked);
    request(5, GL_CMD_SET_CAL, cal, sizeof(cal));
    GL_CHECK_EQ(response(4, &seq, &cmd, &pl), 1);
    GL_CHECK_EQ(pl[0], GL_OK);
    GL_CHECK_EQ(app.set_cal_calls, 1);
    GL_CHECK_EQ(app.cal_id, GL_CAL_ID_GRAIN);
    GL_CHECK_EQ(app.cal_len, GL_CAL_GRAIN_BLOB_LEN);
    GL_CHECK_MEM(app.cal_blob, &cal[1], GL_CAL_GRAIN_BLOB_LEN);
    /* status shows unlocked */
    request(6, GL_CMD_GET_STATUS, NULL, 0);
    GL_CHECK_EQ(response(5, &seq, &cmd, &pl), 17);
    GL_CHECK_EQ(pl[6] & 0x08, 0x08);
    /* erase needs the magic too */
    request(7, GL_CMD_LOG_ERASE, "ERAX", 4);
    GL_CHECK_EQ(app.log_erase_calls, 0);
    request(8, GL_CMD_LOG_ERASE, "ERAS", 4);
    GL_CHECK_EQ(app.log_erase_calls, 1);
    /* an idle reset keeps the lock state, a disconnect re-locks */
    gl_proto_rx_reset(&proto);
    GL_CHECK(proto.unlocked);
    gl_proto_disconnect(&proto);
    GL_CHECK(!proto.unlocked);

    /* START_CAL: ZERO passes through to the app's refusal; the procedures
     * that measure for or write stored calibration need UNLOCK (review
     * finding: GRAIN_WHITE and the six-face solve overwrote calibration
     * from a locked session); ABORT is always allowed */
    fresh();
    {
        const uint8_t a[2] = { GL_CALPROC_ZERO, 0 }, b[2] = { GL_CALPROC_SIX_FACE, 4 };
        const uint8_t locked[][2] = { { GL_CALPROC_SIX_FACE, 0 }, { GL_CALPROC_SIX_FACE, 6 },
                                      { GL_CALPROC_GRAIN_WHITE, 0 }, { GL_CALPROC_GRAIN_FLOOR, 8 },
                                      { GL_CALPROC_CAM_HORIZON, 0 }, { 0x55, 0 } };
        const uint8_t stop[2] = { GL_CALPROC_ABORT, 0 };
        int r = 0;
        request(9, GL_CMD_START_CAL, a, 2);
        GL_CHECK_EQ(response(r++, &seq, &cmd, &pl), 1);
        GL_CHECK_EQ(pl[0], GL_ERR_STATE);
        GL_CHECK_EQ(app.calproc, GL_CALPROC_ZERO); /* it was the app that refused */
        app.calproc = 0;
        for (size_t i = 0; i < sizeof(locked) / sizeof(locked[0]); i++) {
            request((uint8_t)(20 + i), GL_CMD_START_CAL, locked[i], 2);
            GL_CHECK_EQ(response(r++, &seq, &cmd, &pl), 1);
            GL_CHECK_EQ(pl[0], GL_ERR_STATE);
            GL_CHECK_EQ(app.calproc, 0); /* never reached the application */
        }
        request(30, GL_CMD_START_CAL, stop, 2);
        GL_CHECK_EQ(response(r++, &seq, &cmd, &pl), 1);
        GL_CHECK_EQ(app.calproc, GL_CALPROC_ABORT);
        request(31, GL_CMD_UNLOCK, "GLFC", 4);
        GL_CHECK_EQ(response(r++, &seq, &cmd, &pl), 1);
        request(10, GL_CMD_START_CAL, b, 2);
        GL_CHECK_EQ(response(r++, &seq, &cmd, &pl), 1);
        GL_CHECK_EQ(pl[0], GL_OK);
        GL_CHECK_EQ(app.calproc, GL_CALPROC_SIX_FACE);
        GL_CHECK_EQ(app.calarg, 4);
    }

    /* reboot: bad magic does nothing; "DFU!" needs UNLOCK (review finding:
     * the ROM bootloader has no time-out and the consumer cradle no reset
     * contact), answers first, then reboots; a plain reset needs no unlock */
    fresh();
    request(1, GL_CMD_REBOOT, "XXXX", 4);
    GL_CHECK_EQ(response(0, &seq, &cmd, &pl), 1);
    GL_CHECK_EQ(pl[0], GL_ERR_PARAM);
    GL_CHECK_EQ(app.reboot_calls, 0);
    request(2, GL_CMD_REBOOT, "DFU!", 4);
    GL_CHECK_EQ(response(1, &seq, &cmd, &pl), 1);
    GL_CHECK_EQ(pl[0], GL_ERR_STATE);
    GL_CHECK_EQ(app.reboot_calls, 0);
    request(3, GL_CMD_UNLOCK, "GLFC", 4);
    GL_CHECK_EQ(response(2, &seq, &cmd, &pl), 1);
    request(4, GL_CMD_REBOOT, "DFU!", 4);
    GL_CHECK_EQ(response(3, &seq, &cmd, &pl), 1);
    GL_CHECK_EQ(pl[0], GL_OK);
    GL_CHECK_EQ(app.reboot_calls, 1);
    GL_CHECK(app.reboot_dfu);
    GL_CHECK_EQ(app.reboot_tx_frames_at_call, 4); /* response already sent */
    gl_proto_disconnect(&proto); /* locked again */
    request(5, GL_CMD_REBOOT, "BOOT", 4);
    GL_CHECK_EQ(app.reboot_calls, 2);
    GL_CHECK(!app.reboot_dfu);
}

GL_TEST(test_null_ops_are_unsupported)
{
    static gl_proto_ops_t bare;
    uint8_t seq, cmd;
    const uint8_t *pl;
    uint8_t f[64];
    static const uint8_t cmds[] = { GL_CMD_GET_INFO, GL_CMD_GET_STATUS, GL_CMD_GET_SETTINGS,
                                    GL_CMD_LOG_INFO };
    memset(&app, 0, sizeof(app));
    memset(&bare, 0, sizeof(bare));
    bare.tx = m_tx;
    gl_proto_init(&proto, &bare);
    for (size_t i = 0; i < sizeof(cmds); i++) {
        size_t n = gl_proto_encode(f, sizeof(f), (uint8_t)i, cmds[i], NULL, 0);
        gl_proto_feed(&proto, f, n);
        GL_CHECK_EQ(response((int)i, &seq, &cmd, &pl), 1);
        GL_CHECK_EQ(pl[0], GL_ERR_UNSUPPORTED);
    }
    /* reboot without a callback must not crash */
    {
        size_t n = gl_proto_encode(f, sizeof(f), 9, GL_CMD_REBOOT, (const uint8_t *)"DFU!", 4);
        gl_proto_feed(&proto, f, n);
        GL_CHECK_EQ(response(4, &seq, &cmd, &pl), 1);
        GL_CHECK_EQ(pl[0], GL_ERR_UNSUPPORTED);
    }
}

/* ---- malformed input ---------------------------------------------------- */

GL_TEST(test_bad_crc_is_dropped_and_next_frame_survives)
{
    uint8_t f[64], seq, cmd;
    const uint8_t *pl;
    fresh();
    size_t n = gl_proto_encode(f, sizeof(f), 1, GL_CMD_PING, (const uint8_t *)"abc", 3);
    /* every single-bit corruption of the frame must be rejected */
    for (size_t byte = 0; byte < n; byte++) {
        for (int bit = 0; bit < 8; bit++) {
            uint8_t bad[64];
            fresh();
            memcpy(bad, f, n);
            bad[byte] ^= (uint8_t)(1u << bit);
            gl_proto_feed(&proto, bad, n);
            /* a flipped LEN bit can make the parser wait for more bytes; in
             * every case no frame may have been accepted */
            GL_CHECK_EQ(proto.stats.frames_ok, 0);
            GL_CHECK_EQ(app.tx_frames, 0);
            /* a good frame right behind it is still decoded */
            gl_proto_feed(&proto, f, n);
            if (!(byte == 2 || byte == 3)) {
                GL_CHECK_EQ(proto.stats.frames_ok, 1);
                GL_CHECK_EQ(app.tx_frames, 1);
            }
        }
    }
    /* corrupted LEN (claims 259 bytes): the parser waits, then recovers the
     * following good frames once enough bytes have arrived */
    fresh();
    {
        uint8_t bad[64];
        memcpy(bad, f, n);
        bad[3] ^= 0x01; /* LEN 3 -> 259 */
        gl_proto_feed(&proto, bad, n);
        GL_CHECK_EQ(proto.stats.frames_ok, 0);
        for (int i = 0; i < 30; i++) {
            f[4] = (uint8_t)(i + 1);
            n = gl_proto_encode(f, sizeof(f), (uint8_t)(i + 1), GL_CMD_PING,
                                (const uint8_t *)"abc", 3);
            gl_proto_feed(&proto, f, n);
        }
        GL_CHECK_EQ(proto.stats.frames_ok, 30); /* none lost */
        GL_CHECK_EQ(app.tx_frames, 30);
        GL_CHECK_EQ(response(0, &seq, &cmd, &pl), 4);
        GL_CHECK_EQ(seq, 1);
        GL_CHECK_EQ(response(29, &seq, &cmd, &pl), 4);
        GL_CHECK_EQ(seq, 30);
        GL_CHECK(proto.stats.crc_errors >= 1);
    }
    /* same corruption, but the line goes idle: reset recovers immediately */
    fresh();
    {
        uint8_t bad[64];
        n = gl_proto_encode(f, sizeof(f), 5, GL_CMD_PING, (const uint8_t *)"abc", 3);
        memcpy(bad, f, n);
        bad[3] ^= 0x01;
        gl_proto_feed(&proto, bad, n);
        gl_proto_rx_reset(&proto);
        gl_proto_feed(&proto, f, n);
        GL_CHECK_EQ(proto.stats.frames_ok, 1);
        GL_CHECK_EQ(proto.stats.bytes_discarded, n);
    }
}

GL_TEST(test_oversize_length_resyncs)
{
    uint8_t f[64];
    fresh();
    /* header claiming 0xFFFF bytes, then a valid frame */
    const uint8_t junk[6] = { 0xA5, 0x5A, 0xFF, 0xFF, 0x00, 0x01 };
    gl_proto_feed(&proto, junk, sizeof(junk));
    GL_CHECK_EQ(proto.stats.length_errors, 1);
    size_t n = gl_proto_encode(f, sizeof(f), 1, GL_CMD_PING, NULL, 0);
    gl_proto_feed(&proto, f, n);
    GL_CHECK_EQ(proto.stats.frames_ok, 1);
    /* LEN = MAX + 1 is rejected, LEN = MAX is accepted */
    fresh();
    {
        static uint8_t big[GL_PROTO_MAX_FRAME], pl[GL_PROTO_MAX_PAYLOAD];
        const uint8_t over[6] = { 0xA5, 0x5A, 0x01, 0x04, 0x00, 0x01 }; /* 1025 */
        gl_proto_feed(&proto, over, sizeof(over));
        GL_CHECK_EQ(proto.stats.length_errors, 1);
        memset(pl, 0x5A, sizeof(pl));
        n = gl_proto_encode(big, sizeof(big), 3, 0x3E, pl, sizeof(pl));
        GL_CHECK_EQ(n, GL_PROTO_MAX_FRAME);
        gl_proto_feed(&proto, big, n);
        GL_CHECK_EQ(proto.stats.frames_ok, 1);
        GL_CHECK_EQ(app.tx_frames, 1); /* "unsupported" response */
    }
}

GL_TEST(test_garbage_split_and_back_to_back)
{
    uint8_t f[3][64];
    size_t n[3];
    uint8_t stream[400];
    size_t len = 0;
    uint8_t seq, cmd;
    const uint8_t *pl;

    n[0] = gl_proto_encode(f[0], 64, 1, GL_CMD_PING, (const uint8_t *)"one", 3);
    /* payload containing start-of-frame bytes */
    n[1] = gl_proto_encode(f[1], 64, 2, GL_CMD_PING, (const uint8_t *)"\xA5\x5A\xA5\x5A\x00", 5);
    n[2] = gl_proto_encode(f[2], 64, 3, GL_CMD_PING, (const uint8_t *)"three", 5);

    /* garbage (including lone SOF bytes), frame, frame, garbage, frame */
    const uint8_t g1[] = { 0x00, 0xA5, 0xA5, 0x5A, 0x13, 0xA5, 0x00, 0xFF };
    memcpy(&stream[len], g1, sizeof(g1));
    len += sizeof(g1);
    memcpy(&stream[len], f[0], n[0]);
    len += n[0];
    memcpy(&stream[len], f[1], n[1]);
    len += n[1];
    memcpy(&stream[len], "\x5A\x5A\xA5", 3);
    len += 3;
    memcpy(&stream[len], f[2], n[2]);
    len += n[2];

    /* (a) all at once.  The junk "A5 5A 13 A5 .." looks like a header
     * with a huge length, so the parser must resync inside it. */
    fresh();
    gl_proto_feed(&proto, stream, len);
    GL_CHECK_EQ(proto.stats.frames_ok, 3);
    GL_CHECK_EQ(app.tx_frames, 3);
    GL_CHECK_EQ(response(1, &seq, &cmd, &pl), 6);
    GL_CHECK_EQ(seq, 2);
    GL_CHECK_MEM(&pl[1], "\xA5\x5A\xA5\x5A\x00", 5);
    GL_CHECK_EQ(response(2, &seq, &cmd, &pl), 6);
    GL_CHECK_EQ(seq, 3);

    /* (b) one byte at a time */
    fresh();
    for (size_t i = 0; i < len; i++) {
        gl_proto_feed(&proto, &stream[i], 1);
    }
    GL_CHECK_EQ(proto.stats.frames_ok, 3);
    GL_CHECK_EQ(app.tx_frames, 3);

    /* (c) every possible split point into two chunks */
    for (size_t cut = 0; cut <= len; cut++) {
        fresh();
        gl_proto_feed(&proto, stream, cut);
        gl_proto_feed(&proto, &stream[cut], len - cut);
        GL_CHECK_EQ(proto.stats.frames_ok, 3);
    }

    /* (d) truncated frame followed by a complete one */
    fresh();
    gl_proto_feed(&proto, f[0], n[0] - 3);
    gl_proto_feed(&proto, f[2], n[2]);
    gl_proto_feed(&proto, f[1], n[1]);
    GL_CHECK_EQ(proto.stats.frames_ok, 2);
    GL_CHECK_EQ(response(0, &seq, &cmd, &pl), 6);
    GL_CHECK_EQ(seq, 3);
    GL_CHECK_EQ(response(1, &seq, &cmd, &pl), 6);
    GL_CHECK_EQ(seq, 2);

    /* (e) responses / stream frames arriving on the input are ignored */
    fresh();
    {
        uint8_t r[64];
        size_t rn = gl_proto_encode(r, 64, 1, GL_CMD_PING | 0x80, (const uint8_t *)"x", 1);
        gl_proto_feed(&proto, r, rn);
        rn = gl_proto_encode(r, 64, 1, 0x40 | 2, (const uint8_t *)"x", 1);
        gl_proto_feed(&proto, r, rn);
        GL_CHECK_EQ(proto.stats.frames_ok, 2);
        GL_CHECK_EQ(app.tx_frames, 0);
    }
}

GL_TEST(test_random_noise_fuzz)
{
    static uint8_t noise[4096];
    uint8_t f[64];
    unsigned good = 0;
    fresh();
    srand(2024);
    /* About 1 MB of noise biased toward protocol bytes, with 500 valid frames
     * sprinkled in.  The parser must never crash, must find EVERY valid
     * frame, and must not accept anything else. */
    for (int block = 0; block < 500; block++) {
        for (size_t i = 0; i < sizeof(noise); i++) {
            int r = rand();
            noise[i] = (r % 7 == 0) ? 0xA5 : ((r % 11 == 0) ? 0x5A : ((r % 5 == 0) ? 0x00
                                                                                    : (uint8_t)(r >> 8)));
        }
        size_t chunk = (size_t)(1 + rand() % (int)sizeof(noise));
        gl_proto_feed(&proto, noise, chunk);
        /* The noise may have left a plausible partial header; real traffic
         * is separated by idle gaps, modelled by the reset. */
        gl_proto_rx_reset(&proto);
        size_t n = gl_proto_encode(f, sizeof(f), (uint8_t)block, GL_CMD_PING,
                                   (const uint8_t *)"fuzz", 4);
        gl_proto_feed(&proto, f, n);
        good++;
    }
    printf("    fuzz: %u valid frames sent, %u accepted, %u crc errors, %u length errors, "
           "%u bytes discarded\n", good, (unsigned)proto.stats.frames_ok,
           (unsigned)proto.stats.crc_errors, (unsigned)proto.stats.length_errors,
           (unsigned)proto.stats.bytes_discarded);
    GL_CHECK_EQ(proto.stats.frames_ok, good);
    GL_CHECK_EQ(app.tx_frames, (int)good);
    GL_CHECK(proto.stats.crc_errors > 0);
}

GL_TEST(test_stream_frames)
{
    uint8_t seq, cmd;
    const uint8_t *pl;
    static uint8_t big[GL_PROTO_MAX_PAYLOAD + 1];
    fresh();
    GL_CHECK_EQ(gl_proto_send_stream(&proto, GL_STREAM_GRAIN, (const uint8_t *)"abcd", 4), GL_OK);
    GL_CHECK_EQ(gl_proto_send_stream(&proto, GL_STREAM_IMU, (const uint8_t *)"xy", 2), GL_OK);
    GL_CHECK_EQ(response(0, &seq, &cmd, &pl), 4);
    GL_CHECK_EQ(cmd, 0x40 | GL_STREAM_GRAIN);
    GL_CHECK_EQ(seq, 0);
    GL_CHECK_MEM(pl, "abcd", 4);
    GL_CHECK_EQ(response(1, &seq, &cmd, &pl), 2);
    GL_CHECK_EQ(cmd, 0x40 | GL_STREAM_IMU);
    GL_CHECK_EQ(seq, 1);
    GL_CHECK_EQ(gl_proto_send_stream(&proto, GL_STREAM_COUNT, big, 1), GL_ERR_PARAM);
    GL_CHECK_EQ(gl_proto_send_stream(&proto, GL_STREAM_IMU, big, sizeof(big)), GL_ERR_PARAM);
    GL_CHECK_EQ(app.tx_frames, 2);
}

int main(void)
{
    GL_RUN(test_crc16_vectors);
    GL_RUN(test_encode_exact_bytes);
    GL_RUN(test_ping_roundtrip);
    GL_RUN(test_commands);
    GL_RUN(test_locked_commands_and_reboot);
    GL_RUN(test_null_ops_are_unsupported);
    GL_RUN(test_bad_crc_is_dropped_and_next_frame_survives);
    GL_RUN(test_oversize_length_resyncs);
    GL_RUN(test_garbage_split_and_back_to_back);
    GL_RUN(test_random_noise_fuzz);
    GL_RUN(test_stream_frames);
    return gl_test_summary();
}
