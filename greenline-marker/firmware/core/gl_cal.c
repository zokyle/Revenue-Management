/* gl_cal.c - calibration record defaults and (de)serialisation.  See gl_cal.h
 * for the two layout versions. */
#include "gl_cal.h"

#include <math.h>
#include <string.h>

#include "gl_buf.h"
#include "gl_config.h"
#include "gl_crc.h"
#include "gl_provisional.h"

static bool finite_in(float v, float lo, float hi)
{
    return isfinite(v) && v >= lo && v <= hi;
}

/* Append the CRC of everything written so far (the blob's last two bytes). */
static void seal_(gl_wr_t *w, const uint8_t *blob)
{
    gl_wr_u16(w, gl_crc16(blob, w->len));
}

/* Version and length of a blob to be decoded.  *v1 says which layout.
 * A version-2 blob must carry a matching CRC over len_v2 - 2 bytes. */
static gl_status_t open_(const uint8_t *blob, size_t len, size_t len_v1, size_t len_v2, bool *v1)
{
    if (blob == NULL || len < 1u) {
        return GL_ERR_PARAM;
    }
    if (blob[0] == GL_CAL_VERSION) {
        *v1 = false;
        if (len < len_v2) {
            return GL_ERR_PARAM;
        }
        if (gl_crc16(blob, len_v2 - 2u) != gl_get_u16(&blob[len_v2 - 2u])) {
            return GL_ERR_CRC;
        }
        return GL_OK;
    }
    if (blob[0] == GL_CAL_VERSION_PHASE1 && len_v1 != 0u) {
        *v1 = true;
        return (len < len_v1) ? GL_ERR_PARAM : GL_OK;
    }
    return GL_ERR_UNSUPPORTED;
}

/* ---- tilt --------------------------------------------------------------- */

void gl_cal_tilt_defaults(gl_cal_tilt_t *c)
{
    memset(c, 0, sizeof(*c));
    c->t0_c = 25.0f;
    c->m = gl_mat3_identity();
}

void gl_cal_tilt_encode(const gl_cal_tilt_t *c, uint8_t out[GL_CAL_TILT_BLOB_LEN])
{
    gl_wr_t w;
    gl_wr_init(&w, out, GL_CAL_TILT_BLOB_LEN);
    gl_wr_u8(&w, (uint8_t)GL_CAL_VERSION);
    gl_wr_u8(&w, c->flags);
    for (int i = 0; i < 3; i++) {
        gl_wr_f32(&w, c->offset_g[i]);
    }
    for (int i = 0; i < 3; i++) {
        gl_wr_f32(&w, c->tempco1_g_per_k[i]);
    }
    for (int i = 0; i < 3; i++) {
        gl_wr_f32(&w, c->tempco2_g_per_k2[i]);
    }
    gl_wr_f32(&w, c->t0_c);
    for (int i = 0; i < 3; i++) {
        for (int j = 0; j < 3; j++) {
            gl_wr_f32(&w, c->m.m[i][j]);
        }
    }
    gl_wr_f32(&w, c->flip_bias_x);
    gl_wr_f32(&w, c->flip_bias_y);
    gl_wr_f32(&w, c->flip_temp_c);
    gl_wr_u32(&w, c->flip_time_s);
    /* up to here the layout of version 1: 2 + 36 + 4 + 36 + 16 = 94 bytes */
    gl_wr_f32(&w, c->flip_scatter);
    gl_wr_f32(&w, c->base_bias_x);
    gl_wr_f32(&w, c->base_bias_y);
    gl_wr_f32(&w, c->base_temp_c);
    gl_wr_u32(&w, c->base_time_s);
    gl_wr_f32(&w, c->base_scatter);
    seal_(&w, out); /* 94 + 24 + 2 = 120 bytes */
}

gl_status_t gl_cal_tilt_decode(const uint8_t *blob, size_t len, gl_cal_tilt_t *c)
{
    gl_rd_t r;
    gl_cal_tilt_t t;
    bool ok = true;
    bool v1 = false;
    const gl_status_t st =
        open_(blob, len, GL_CAL_TILT_BLOB_LEN_V1, GL_CAL_TILT_BLOB_LEN, &v1);

    if (st != GL_OK) {
        return st;
    }
    gl_rd_init(&r, blob, len);
    (void)gl_rd_u8(&r);
    memset(&t, 0, sizeof(t));
    t.flags = gl_rd_u8(&r);
    for (int i = 0; i < 3; i++) {
        t.offset_g[i] = gl_rd_f32(&r);
        ok = ok && finite_in(t.offset_g[i], -0.5f, 0.5f);
    }
    for (int i = 0; i < 3; i++) {
        t.tempco1_g_per_k[i] = gl_rd_f32(&r);
        ok = ok && finite_in(t.tempco1_g_per_k[i], -0.01f, 0.01f);
    }
    for (int i = 0; i < 3; i++) {
        t.tempco2_g_per_k2[i] = gl_rd_f32(&r);
        ok = ok && finite_in(t.tempco2_g_per_k2[i], -0.001f, 0.001f);
    }
    t.t0_c = gl_rd_f32(&r);
    ok = ok && finite_in(t.t0_c, -40.0f, 85.0f);
    for (int i = 0; i < 3; i++) {
        for (int j = 0; j < 3; j++) {
            t.m.m[i][j] = gl_rd_f32(&r);
            ok = ok && finite_in(t.m.m[i][j], (i == j) ? 0.8f : -0.2f, (i == j) ? 1.2f : 0.2f);
        }
    }
    t.flip_bias_x = gl_rd_f32(&r);
    t.flip_bias_y = gl_rd_f32(&r);
    t.flip_temp_c = gl_rd_f32(&r);
    t.flip_time_s = gl_rd_u32(&r);
    ok = ok && finite_in(t.flip_bias_x, -0.2f, 0.2f) && finite_in(t.flip_bias_y, -0.2f, 0.2f) &&
         finite_in(t.flip_temp_c, -40.0f, 85.0f);
    if (v1) {
        /* MIGRATION.  Version 1 had the flags FACTORY and FLIP only; its one
         * zero was taken on a hard flat surface: the ball seat.  No base-face
         * zero, no scatter.  Whether the temperature terms were fitted is
         * read off the terms themselves. */
        t.flags &= (uint8_t)(GL_CAL_TILT_FLAG_FACTORY | GL_CAL_TILT_FLAG_FLIP);
        for (int i = 0; i < 3; i++) {
            if (t.tempco1_g_per_k[i] != 0.0f || t.tempco2_g_per_k2[i] != 0.0f) {
                t.flags |= (uint8_t)GL_CAL_TILT_FLAG_TEMPCO;
            }
        }
        t.base_temp_c = t.t0_c;
    } else {
        t.flip_scatter = gl_rd_f32(&r);
        t.base_bias_x = gl_rd_f32(&r);
        t.base_bias_y = gl_rd_f32(&r);
        t.base_temp_c = gl_rd_f32(&r);
        t.base_time_s = gl_rd_u32(&r);
        t.base_scatter = gl_rd_f32(&r);
        ok = ok && (t.flags & (uint8_t)~GL_CAL_TILT_FLAG_ALL) == 0u &&
             finite_in(t.flip_scatter, 0.0f, 0.2f) && finite_in(t.base_bias_x, -0.2f, 0.2f) &&
             finite_in(t.base_bias_y, -0.2f, 0.2f) && finite_in(t.base_temp_c, -40.0f, 85.0f) &&
             finite_in(t.base_scatter, 0.0f, 0.2f);
    }
    if (!r.ok || !ok) {
        return GL_ERR_RANGE;
    }
    *c = t;
    return GL_OK;
}

gl_cal_seat_t gl_cal_tilt_zero(const gl_cal_tilt_t *cal, gl_cal_seat_t wanted, gl_vec2_t *bias)
{
    bool ball, base;
    bias->x = 0.0f;
    bias->y = 0.0f;
    if (cal == NULL) {
        return GL_CAL_SEAT_NONE;
    }
    ball = (cal->flags & GL_CAL_TILT_FLAG_FLIP) != 0u;
    base = (cal->flags & GL_CAL_TILT_FLAG_BASE) != 0u;
    if (!ball && !base) {
        return GL_CAL_SEAT_NONE;
    }
    if ((wanted == GL_CAL_SEAT_BALL && ball) || !base) {
        bias->x = cal->flip_bias_x;
        bias->y = cal->flip_bias_y;
        return GL_CAL_SEAT_BALL;
    }
    bias->x = cal->base_bias_x;
    bias->y = cal->base_bias_y;
    return GL_CAL_SEAT_BASE;
}

void gl_cal_tilt_set_zero(gl_cal_tilt_t *cal, gl_cal_seat_t seat, gl_vec2_t bias, float temp_c,
                          uint32_t time_s, float scatter)
{
    if (seat == GL_CAL_SEAT_BASE) {
        cal->base_bias_x = bias.x;
        cal->base_bias_y = bias.y;
        cal->base_temp_c = temp_c;
        cal->base_time_s = time_s;
        cal->base_scatter = scatter;
        cal->flags |= (uint8_t)GL_CAL_TILT_FLAG_BASE;
        cal->flags &= (uint8_t)~GL_CAL_TILT_FLAG_BASE_DERIVED;
        return;
    }
    if ((cal->flags & GL_CAL_TILT_FLAG_BASE) != 0u && (cal->flags & GL_CAL_TILT_FLAG_FLIP) != 0u) {
        /* keep the difference between the seats */
        cal->base_bias_x += bias.x - cal->flip_bias_x;
        cal->base_bias_y += bias.y - cal->flip_bias_y;
        cal->flags |= (uint8_t)GL_CAL_TILT_FLAG_BASE_DERIVED;
    }
    cal->flip_bias_x = bias.x;
    cal->flip_bias_y = bias.y;
    cal->flip_temp_c = temp_c;
    cal->flip_time_s = time_s;
    cal->flip_scatter = scatter;
    cal->flags |= (uint8_t)GL_CAL_TILT_FLAG_FLIP;
}

/* ---- camera ------------------------------------------------------------- */

void gl_cal_cam_defaults(gl_cal_cam_t *c, unsigned cam_index)
{
    memset(c, 0, sizeof(*c));
    c->fx_px = GL_CFG_CAM_F_PX;
    c->fy_px = GL_CFG_CAM_F_PX;
    c->cx_px = 0.5f * ((float)GL_CFG_CAM_SENSOR_COLS - 1.0f);
    c->cy_px = 0.5f * ((float)GL_CFG_CAM_SENSOR_ROWS - 1.0f);
    c->pos_mm[0] = (cam_index == 0u) ? GL_CFG_CAM_LEFT_X_MM : GL_CFG_CAM_RIGHT_X_MM;
    c->pos_mm[1] = (cam_index == 0u) ? GL_CFG_CAM_LEFT_Y_MM : GL_CFG_CAM_RIGHT_Y_MM;
    c->pos_mm[2] = GL_CFG_CAM_AXIS_HEIGHT_MM;
    c->horizon_row = c->cy_px; /* nominal: a level optical axis */
}

void gl_cal_cam_encode(const gl_cal_cam_t *c, uint8_t out[GL_CAL_CAM_BLOB_LEN])
{
    gl_wr_t w;
    gl_wr_init(&w, out, GL_CAL_CAM_BLOB_LEN);
    gl_wr_u8(&w, (uint8_t)GL_CAL_VERSION);
    gl_wr_u8(&w, c->flags);
    gl_wr_f32(&w, c->fx_px);
    gl_wr_f32(&w, c->fy_px);
    gl_wr_f32(&w, c->cx_px);
    gl_wr_f32(&w, c->cy_px);
    gl_wr_f32(&w, c->k1);
    gl_wr_f32(&w, c->pitch_up_rad);
    gl_wr_f32(&w, c->yaw_left_rad);
    gl_wr_f32(&w, c->roll_rad);
    for (int i = 0; i < 3; i++) {
        gl_wr_f32(&w, c->pos_mm[i]);
    }
    /* up to here the layout of version 1: 2 + 11 * 4 = 46 bytes */
    gl_wr_f32(&w, c->horizon_row);
    seal_(&w, out); /* 46 + 4 + 2 = 52 bytes */
}

gl_status_t gl_cal_cam_decode(const uint8_t *blob, size_t len, gl_cal_cam_t *c)
{
    gl_rd_t r;
    gl_cal_cam_t t;
    bool ok;
    bool v1 = false;
    const gl_status_t st = open_(blob, len, GL_CAL_CAM_BLOB_LEN_V1, GL_CAL_CAM_BLOB_LEN, &v1);

    if (st != GL_OK) {
        return st;
    }
    gl_rd_init(&r, blob, len);
    (void)gl_rd_u8(&r);
    memset(&t, 0, sizeof(t));
    t.flags = gl_rd_u8(&r);
    t.fx_px = gl_rd_f32(&r);
    t.fy_px = gl_rd_f32(&r);
    t.cx_px = gl_rd_f32(&r);
    t.cy_px = gl_rd_f32(&r);
    t.k1 = gl_rd_f32(&r);
    t.pitch_up_rad = gl_rd_f32(&r);
    t.yaw_left_rad = gl_rd_f32(&r);
    t.roll_rad = gl_rd_f32(&r);
    for (int i = 0; i < 3; i++) {
        t.pos_mm[i] = gl_rd_f32(&r);
    }
    ok = finite_in(t.fx_px, 300.0f, 1500.0f) && finite_in(t.fy_px, 300.0f, 1500.0f) &&
         finite_in(t.cx_px, 0.0f, (float)GL_CFG_CAM_SENSOR_COLS) &&
         finite_in(t.cy_px, 0.0f, (float)GL_CFG_CAM_SENSOR_ROWS) && finite_in(t.k1, -1.0f, 1.0f) &&
         finite_in(t.pitch_up_rad, -0.2f, 0.2f) && finite_in(t.yaw_left_rad, -0.2f, 0.2f) &&
         finite_in(t.roll_rad, -0.2f, 0.2f) && finite_in(t.pos_mm[0], -30.0f, 30.0f) &&
         finite_in(t.pos_mm[1], -30.0f, 30.0f) && finite_in(t.pos_mm[2], 0.0f, 10.0f);
    if (v1) {
        /* MIGRATION: no horizon row was measured; the row the stored pitch
         * implies is filled in so that the field is never meaningless */
        t.flags &= (uint8_t)(GL_CAL_CAM_FLAG_INTRINSICS | GL_CAL_CAM_FLAG_EXTRINSICS);
        t.horizon_row = ok ? (t.cy_px + t.fy_px * tanf(t.pitch_up_rad)) : 0.0f;
    } else {
        t.horizon_row = gl_rd_f32(&r);
        ok = ok && (t.flags & (uint8_t)~GL_CAL_CAM_FLAG_ALL) == 0u &&
             finite_in(t.horizon_row, -300.0f, (float)GL_CFG_CAM_SENSOR_ROWS + 300.0f);
    }
    if (!r.ok || !ok) {
        return GL_ERR_RANGE;
    }
    *c = t;
    return GL_OK;
}

gl_status_t gl_cal_cam_set_horizon(gl_cal_cam_t *c, float row, float roll_rad)
{
    float pitch;
    if (!finite_in(row, 0.0f, (float)GL_CFG_CAM_SENSOR_ROWS - 1.0f) ||
        !finite_in(roll_rad, -0.2f, 0.2f)) {
        return GL_ERR_RANGE;
    }
    pitch = atanf((row - c->cy_px) / c->fy_px);
    if (!finite_in(pitch, -0.2f, 0.2f)) {
        return GL_ERR_RANGE;
    }
    c->horizon_row = row;
    c->pitch_up_rad = pitch;
    c->roll_rad = roll_rad;
    c->flags |= (uint8_t)GL_CAL_CAM_FLAG_HORIZON;
    return GL_OK;
}

/* ---- grain -------------------------------------------------------------- */

void gl_cal_grain_defaults(gl_cal_grain_t *c)
{
    memset(c, 0, sizeof(*c));
    for (unsigned i = 0; i < GL_GRAIN_LEDS; i++) {
        c->gain[i] = 1.0f;
    }
    c->mod_threshold = GL_PROV_GRAIN_MOD_THRESHOLD_DEFAULT;
    c->noise_floor_mod = 0.0f;
    c->min_signal_counts = 200;
    c->max_dark_drift_counts = 40;
}

void gl_cal_grain_encode(const gl_cal_grain_t *c, uint8_t out[GL_CAL_GRAIN_BLOB_LEN])
{
    gl_wr_t w;
    gl_wr_init(&w, out, GL_CAL_GRAIN_BLOB_LEN);
    gl_wr_u8(&w, (uint8_t)GL_CAL_VERSION);
    gl_wr_u8(&w, c->flags);
    for (unsigned i = 0; i < GL_GRAIN_LEDS; i++) {
        gl_wr_f32(&w, c->gain[i]);
    }
    gl_wr_f32(&w, c->mod_threshold);
    gl_wr_f32(&w, c->noise_floor_mod);
    gl_wr_u16(&w, c->min_signal_counts);
    gl_wr_u16(&w, c->max_dark_drift_counts);
    /* up to here the layout of version 1: 2 + 64 + 8 + 4 = 78 bytes */
    gl_wr_u16(&w, c->pd_dark_counts);
    seal_(&w, out); /* 78 + 2 + 2 = 82 bytes */
}

gl_status_t gl_cal_grain_decode(const uint8_t *blob, size_t len, gl_cal_grain_t *c)
{
    gl_rd_t r;
    gl_cal_grain_t t;
    bool ok = true;
    bool v1 = false;
    const gl_status_t st =
        open_(blob, len, GL_CAL_GRAIN_BLOB_LEN_V1, GL_CAL_GRAIN_BLOB_LEN, &v1);

    if (st != GL_OK) {
        return st;
    }
    gl_rd_init(&r, blob, len);
    (void)gl_rd_u8(&r);
    memset(&t, 0, sizeof(t));
    t.flags = gl_rd_u8(&r);
    for (unsigned i = 0; i < GL_GRAIN_LEDS; i++) {
        t.gain[i] = gl_rd_f32(&r);
        ok = ok && finite_in(t.gain[i], 0.05f, 20.0f);
    }
    t.mod_threshold = gl_rd_f32(&r);
    t.noise_floor_mod = gl_rd_f32(&r);
    t.min_signal_counts = gl_rd_u16(&r);
    t.max_dark_drift_counts = gl_rd_u16(&r);
    /* A threshold of zero would accept noise as grain: refuse it. */
    ok = ok && finite_in(t.mod_threshold, 0.01f, 2.0f) && finite_in(t.noise_floor_mod, 0.0f, 2.0f);
    /* The two integer limits are limits too: a minimum signal of 0 counts
     * accepts a dead photodiode, a dark drift of 65535 counts accepts any
     * drift (phase-3 review, factory finding 11: SET_CAL took both).  The
     * windows are wide (defaults 200 and 40 counts of a 14-bit reading) */
    ok = ok && t.min_signal_counts >= GL_CAL_GRAIN_MIN_SIGNAL_LO &&
         t.min_signal_counts <= GL_CAL_GRAIN_MIN_SIGNAL_HI &&
         t.max_dark_drift_counts >= GL_CAL_GRAIN_DARK_DRIFT_LO &&
         t.max_dark_drift_counts <= GL_CAL_GRAIN_DARK_DRIFT_HI;
    if (v1) {
        t.flags &= (uint8_t)(GL_CAL_GRAIN_FLAG_WHITE_REF | GL_CAL_GRAIN_FLAG_NOISE_FLOOR);
    } else {
        t.pd_dark_counts = gl_rd_u16(&r);
        ok = ok && (t.flags & (uint8_t)~GL_CAL_GRAIN_FLAG_ALL) == 0u;
    }
    if (!r.ok || !ok) {
        return GL_ERR_RANGE;
    }
    *c = t;
    return GL_OK;
}

/* ---- device ------------------------------------------------------------- */

void gl_cal_device_defaults(gl_cal_device_t *c)
{
    memset(c, 0, sizeof(*c));
}

void gl_cal_device_encode(const gl_cal_device_t *c, uint8_t out[GL_CAL_DEVICE_BLOB_LEN])
{
    gl_wr_t w;
    gl_wr_init(&w, out, GL_CAL_DEVICE_BLOB_LEN);
    gl_wr_u8(&w, (uint8_t)GL_CAL_VERSION);
    gl_wr_u8(&w, c->flags);
    gl_wr_f32(&w, c->display_rot_rad);
    gl_wr_bytes(&w, c->unique_id, sizeof(c->unique_id));
    gl_wr_u32(&w, c->serial);
    gl_wr_u32(&w, c->time_s);
    seal_(&w, out); /* 2 + 4 + 12 + 4 + 4 + 2 = 28 bytes */
}

gl_status_t gl_cal_device_decode(const uint8_t *blob, size_t len, gl_cal_device_t *c)
{
    gl_rd_t r;
    gl_cal_device_t t;
    bool v1 = false;
    const gl_status_t st = open_(blob, len, 0u, GL_CAL_DEVICE_BLOB_LEN, &v1);

    if (st != GL_OK) {
        return st;
    }
    gl_rd_init(&r, blob, len);
    (void)gl_rd_u8(&r);
    memset(&t, 0, sizeof(t));
    t.flags = gl_rd_u8(&r);
    t.display_rot_rad = gl_rd_f32(&r);
    gl_rd_bytes(&r, t.unique_id, sizeof(t.unique_id));
    t.serial = gl_rd_u32(&r);
    t.time_s = gl_rd_u32(&r);
    if (!r.ok || (t.flags & (uint8_t)~GL_CAL_DEV_FLAG_ALL) != 0u ||
        !finite_in(t.display_rot_rad, -GL_CAL_DISPLAY_ROT_MAX_RAD, GL_CAL_DISPLAY_ROT_MAX_RAD) ||
        ((t.flags & GL_CAL_DEV_FLAG_SERIAL) != 0u &&
         t.serial != gl_cal_serial_from_uid(t.unique_id))) {
        return GL_ERR_RANGE;
    }
    *c = t;
    return GL_OK;
}

uint32_t gl_cal_serial_from_uid(const uint8_t unique_id[12])
{
    const uint32_t s = gl_crc32(unique_id, 12u);
    return (s == 0u) ? 1u : s;
}

void gl_cal_serial_text(uint32_t serial, char out[8])
{
    static const char alphabet[33] = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";
    for (int i = 6; i >= 0; i--) {
        out[i] = alphabet[serial & 31u];
        serial >>= 5;
    }
    out[7] = '\0';
}
