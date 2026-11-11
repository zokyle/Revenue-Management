/* gl_range.c - see gl_range.h. */
#include "gl_range.h"

#include <math.h>
#include <string.h>

#include "gl_buf.h"
#include "gl_config.h"
#include "gl_provisional.h"

#define STICK_BLOB_VERSION 1u

void gl_stick_height_reset(gl_stick_height_t *h)
{
    h->height_m = GL_PROV_STICK_TOTAL_HEIGHT_M - GL_PROV_STICK_IN_CUP_M;
    h->sigma_m = GL_PROV_STICK_HEIGHT_REL_SIGMA * h->height_m;
    h->updates = 0;
    h->rejected = 0;
}

void gl_stick_height_encode(const gl_stick_height_t *h, uint8_t out[GL_STICK_HEIGHT_BLOB_LEN])
{
    gl_wr_t w;
    gl_wr_init(&w, out, GL_STICK_HEIGHT_BLOB_LEN);
    gl_wr_u8(&w, (uint8_t)STICK_BLOB_VERSION);
    gl_wr_f32(&w, h->height_m);
    gl_wr_f32(&w, h->sigma_m);
    gl_wr_u16(&w, h->updates);
    gl_wr_u16(&w, h->rejected);
}

gl_status_t gl_stick_height_decode(const uint8_t *blob, size_t len, gl_stick_height_t *h)
{
    gl_rd_t r;
    gl_stick_height_t t;
    if (blob == NULL || len < GL_STICK_HEIGHT_BLOB_LEN) {
        return GL_ERR_PARAM;
    }
    gl_rd_init(&r, blob, len);
    if (gl_rd_u8(&r) != STICK_BLOB_VERSION) {
        return GL_ERR_UNSUPPORTED;
    }
    t.height_m = gl_rd_f32(&r);
    t.sigma_m = gl_rd_f32(&r);
    t.updates = gl_rd_u16(&r);
    t.rejected = gl_rd_u16(&r);
    if (!r.ok || !isfinite(t.height_m) || !isfinite(t.sigma_m) || t.height_m < 1.0f ||
        t.height_m > 3.0f || t.sigma_m <= 0.0f || t.sigma_m > 0.5f) {
        return GL_ERR_RANGE;
    }
    *h = t;
    return GL_OK;
}

/* Stereo as inverse range: rho and its sigma.  Returns false if unusable. */
static bool stereo_rho_(const gl_range_input_t *in, float *rho, float *sig)
{
    float fb = in->f_px * in->baseline_m;
    if (!in->have_stereo || !(fb > 0.0f) || !(in->disparity_sigma_px > 0.0f) ||
        !isfinite(in->disparity_px)) {
        return false;
    }
    {
        /* depth -> horizontal distance: 1 / distance = cos(bearing) / depth */
        float cb = (in->cos_bearing > 0.1f && in->cos_bearing <= 1.0f) ? in->cos_bearing : 1.0f;
        *rho = cb * in->disparity_px / fb;
        *sig = cb * in->disparity_sigma_px / fb;
    }
    return true;
}

/* Angular height as inverse range. */
static bool mono_rho_(const gl_range_input_t *in, const gl_stick_height_t *h, float *rho,
                      float *sig)
{
    float th, s_th;
    if (!in->have_height || !in->base_visible || h == NULL || !(h->height_m > 0.0f) ||
        !(in->elev_sigma_rad > 0.0f)) {
        return false;
    }
    th = in->tan_top - in->tan_base;
    if (!(th > 0.0f) || !isfinite(th)) {
        return false;
    }
    s_th = 1.41421356f * in->elev_sigma_rad; /* difference of two elevations */
    *rho = th / h->height_m;
    *sig = sqrtf((s_th / h->height_m) * (s_th / h->height_m) +
                 (*rho * h->sigma_m / h->height_m) * (*rho * h->sigma_m / h->height_m));
    return true;
}

static void rho_to_range_(float rho, float sig, float *range, float *sigma)
{
    float z;
    if (rho < 1.0f / GL_RANGE_MAX_M) {
        rho = 1.0f / GL_RANGE_MAX_M;
    }
    z = gl_clampf(1.0f / rho, GL_RANGE_MIN_M, GL_RANGE_MAX_M);
    *range = z;
    *sigma = z * z * sig; /* first order: dZ = Z^2 d(rho) */
}

gl_status_t gl_range_fuse(const gl_range_input_t *in, const gl_stick_height_t *h,
                          gl_range_result_t *out)
{
    float rs = 0.0f, ss = 0.0f, rm = 0.0f, sm = 0.0f;
    bool have_s, have_m;

    if (in == NULL || out == NULL) {
        return GL_ERR_PARAM;
    }
    memset(out, 0, sizeof(*out));
    out->consistent = true;
    have_s = stereo_rho_(in, &rs, &ss);
    have_m = mono_rho_(in, h, &rm, &sm);
    /* A disparity at or below zero carries no range by itself. */
    if (have_s && rs > 0.0f) {
        rho_to_range_(rs, ss, &out->stereo_m, &out->stereo_sigma_m);
    }
    if (have_m) {
        rho_to_range_(rm, sm, &out->mono_m, &out->mono_sigma_m);
    }
    if (have_s && have_m) {
        float d = rs - rm;
        out->chi2 = d * d / (ss * ss + sm * sm);
        out->consistent = (out->chi2 <= 9.0f);
    }

    if (in->manual_m > 0.0f && isfinite(in->manual_m)) {
        out->range_m = gl_clampf(in->manual_m, GL_RANGE_MIN_M, GL_RANGE_MAX_M);
        out->sigma_m = GL_RANGE_MANUAL_REL_SIGMA * out->range_m;
        out->sources = GL_RANGE_SRC_MANUAL;
        return GL_OK;
    }
    if (have_s && have_m) {
        float ws = 1.0f / (ss * ss), wm = 1.0f / (sm * sm);
        float rho = (ws * rs + wm * rm) / (ws + wm);
        float sig = 1.0f / sqrtf(ws + wm);
        if (!out->consistent) {
            sig *= sqrtf(out->chi2 / 9.0f);
        }
        if (!(rho > 0.0f)) {
            return GL_ERR_NOT_FOUND;
        }
        rho_to_range_(rho, sig, &out->range_m, &out->sigma_m);
        out->sources = GL_RANGE_SRC_STEREO | GL_RANGE_SRC_MONO;
        return GL_OK;
    }
    if (have_m) {
        out->range_m = out->mono_m;
        out->sigma_m = out->mono_sigma_m;
        out->sources = GL_RANGE_SRC_MONO;
        return GL_OK;
    }
    if (have_s && rs > 0.0f) {
        out->range_m = out->stereo_m;
        out->sigma_m = out->stereo_sigma_m;
        out->sources = GL_RANGE_SRC_STEREO;
        return GL_OK;
    }
    return GL_ERR_NOT_FOUND;
}

bool gl_stick_height_learn(gl_stick_height_t *h, const gl_range_input_t *in)
{
    float rs, ss, z, sz, th, s_th, meas, r_var, p_var, innov, k, floor_sigma;

    if (h == NULL || in == NULL || in->manual_m > 0.0f || !in->have_height ||
        !in->base_visible || !stereo_rho_(in, &rs, &ss) || !(rs > 0.0f) ||
        !(in->elev_sigma_rad > 0.0f)) {
        return false;
    }
    z = 1.0f / rs;
    if (z < GL_RANGE_LEARN_MIN_M || z > GL_RANGE_LEARN_MAX_M) {
        return false;
    }
    th = in->tan_top - in->tan_base;
    if (!(th > 0.0f)) {
        return false;
    }
    sz = z * z * ss;
    s_th = 1.41421356f * in->elev_sigma_rad;
    meas = th * z;
    r_var = (th * sz) * (th * sz) + (z * s_th) * (z * s_th);
    p_var = h->sigma_m * h->sigma_m;
    innov = meas - h->height_m;
    if (innov * innov > 9.0f * (p_var + r_var)) {
        if (h->rejected < 0xFFFFu) {
            h->rejected++;
        }
        return false; /* a different stick, a mis-detection, or a bad disparity */
    }
    k = p_var / (p_var + r_var);
    h->height_m += k * innov;
    h->sigma_m = sqrtf((1.0f - k) * p_var);
    floor_sigma = GL_STICK_HEIGHT_SIGMA_FLOOR_REL * h->height_m;
    if (h->sigma_m < floor_sigma) {
        h->sigma_m = floor_sigma;
    }
    if (h->updates < 0xFFFFu) {
        h->updates++;
    }
    return true;
}

gl_ball_target_t gl_range_from_ball_at(float range_m, float bearing_rad, float view_x_m,
                                       float view_y_m)
{
    const float ball_y = 0.001f * GL_CFG_BALL_CENTRE_Y_MM;
    /* stick position in the marker frame (x right, y forward) */
    const float sx = view_x_m - range_m * sinf(bearing_rad);
    const float sy = view_y_m + range_m * cosf(bearing_rad);
    const float dx = sx, dy = sy - ball_y;
    gl_ball_target_t t;
    t.distance_m = sqrtf(dx * dx + dy * dy);
    t.bearing_rad = atan2f(-dx, dy);
    return t;
}

gl_ball_target_t gl_range_from_ball(float range_cam_m, float bearing_cam_rad)
{
    return gl_range_from_ball_at(range_cam_m, bearing_cam_rad, 0.0f,
                                 0.001f * GL_CFG_CAM_LEFT_Y_MM);
}
