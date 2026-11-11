/* gl_cal.c - calibration record defaults and (de)serialisation. */
#include "gl_cal.h"

#include <math.h>
#include <string.h>

#include "gl_buf.h"
#include "gl_config.h"
#include "gl_provisional.h"

static bool finite_in(float v, float lo, float hi)
{
    return isfinite(v) && v >= lo && v <= hi;
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
    /* 2 + 36 + 4 + 36 + 12 + 4 = 94 bytes */
}

gl_status_t gl_cal_tilt_decode(const uint8_t *blob, size_t len, gl_cal_tilt_t *c)
{
    gl_rd_t r;
    gl_cal_tilt_t t;
    bool ok = true;

    if (blob == NULL || len < GL_CAL_TILT_BLOB_LEN) {
        return GL_ERR_PARAM;
    }
    gl_rd_init(&r, blob, len);
    if (gl_rd_u8(&r) != GL_CAL_VERSION) {
        return GL_ERR_UNSUPPORTED;
    }
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
    if (!r.ok || !ok) {
        return GL_ERR_RANGE;
    }
    *c = t;
    return GL_OK;
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
    /* 2 + 11 * 4 = 46 bytes */
}

gl_status_t gl_cal_cam_decode(const uint8_t *blob, size_t len, gl_cal_cam_t *c)
{
    gl_rd_t r;
    gl_cal_cam_t t;
    bool ok;

    if (blob == NULL || len < GL_CAL_CAM_BLOB_LEN) {
        return GL_ERR_PARAM;
    }
    gl_rd_init(&r, blob, len);
    if (gl_rd_u8(&r) != GL_CAL_VERSION) {
        return GL_ERR_UNSUPPORTED;
    }
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
    if (!r.ok || !ok) {
        return GL_ERR_RANGE;
    }
    *c = t;
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
    /* 2 + 64 + 8 + 4 = 78 bytes */
}

gl_status_t gl_cal_grain_decode(const uint8_t *blob, size_t len, gl_cal_grain_t *c)
{
    gl_rd_t r;
    gl_cal_grain_t t;
    bool ok = true;

    if (blob == NULL || len < GL_CAL_GRAIN_BLOB_LEN) {
        return GL_ERR_PARAM;
    }
    gl_rd_init(&r, blob, len);
    if (gl_rd_u8(&r) != GL_CAL_VERSION) {
        return GL_ERR_UNSUPPORTED;
    }
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
    if (!r.ok || !ok) {
        return GL_ERR_RANGE;
    }
    *c = t;
    return GL_OK;
}
