/* gl_tilt.c - see gl_tilt.h. */
#include "gl_tilt.h"

#include <math.h>
#include <string.h>

/* ---- block averaging ------------------------------------------------------ */

void gl_tilt_cfg_defaults(gl_tilt_cfg_t *cfg)
{
    cfg->accel_g_per_lsb = 0.0f;
    cfg->gyro_rad_s_per_lsb = 0.0f;
    cfg->block_samples = 32;
    cfg->still_accel_std_g = 0.004f;
    cfg->still_gyro_std_rad_s = 0.02f;
    cfg->still_step_g = 0.003f;
}

void gl_tilt_avg_init(gl_tilt_avg_t *a, const gl_tilt_cfg_t *cfg)
{
    memset(a, 0, sizeof(*a));
    a->cfg = *cfg;
    if (a->cfg.block_samples < 4u) {
        a->cfg.block_samples = 4u;
    }
    if (a->cfg.block_samples > 256u) {
        a->cfg.block_samples = 256u;
    }
}

void gl_tilt_avg_reset(gl_tilt_avg_t *a)
{
    gl_tilt_cfg_t cfg = a->cfg;
    memset(a, 0, sizeof(*a));
    a->cfg = cfg;
}

/* Variance in LSB^2 of n samples from exact integer sums. */
static float block_var_(int32_t sum, int64_t sq, uint16_t n)
{
    int64_t num = (int64_t)n * sq - (int64_t)sum * (int64_t)sum; /* n^2 * variance, >= 0 */
    if (num < 0) {
        num = 0;
    }
    return (float)num / ((float)n * (float)n);
}

bool gl_tilt_avg_add(gl_tilt_avg_t *a, const gl_imu_raw_t *s)
{
    const int16_t acc[3] = { s->ax, s->ay, s->az };
    const int16_t gyr[3] = { s->gx, s->gy, s->gz };
    const float ka = a->cfg.accel_g_per_lsb;
    const float kg = a->cfg.gyro_rad_s_per_lsb;
    bool still = true;
    float var_sum = 0.0f;

    for (int i = 0; i < 3; i++) {
        a->sum_a[i] += acc[i];
        a->sum_g[i] += gyr[i];
        a->sq_a[i] += (int64_t)acc[i] * acc[i];
        a->sq_g[i] += (int64_t)gyr[i] * gyr[i];
    }
    a->n++;
    if (a->n < a->cfg.block_samples) {
        return false;
    }

    /* A block is complete: judge it. */
    for (int i = 0; i < 3; i++) {
        float va = block_var_(a->sum_a[i], a->sq_a[i], a->n) * ka * ka;
        float vg = block_var_(a->sum_g[i], a->sq_g[i], a->n) * kg * kg;
        float mean = (float)a->sum_a[i] / (float)a->n * ka;
        if (va > a->cfg.still_accel_std_g * a->cfg.still_accel_std_g ||
            vg > a->cfg.still_gyro_std_rad_s * a->cfg.still_gyro_std_rad_s) {
            still = false;
        }
        if (a->have_prev && fabsf(mean - a->prev_mean_a[i]) > a->cfg.still_step_g) {
            still = false;
        }
        a->prev_mean_a[i] = mean;
        var_sum += va;
    }
    a->have_prev = true;
    a->blocks_total++;
    a->last_still = still;
    if (still) {
        for (int i = 0; i < 3; i++) {
            a->acc_a[i] += a->sum_a[i];
            a->acc_g[i] += a->sum_g[i];
        }
        a->acc_n += a->n;
        a->acc_var_a += var_sum / 3.0f;
        a->blocks_still++;
        if (a->consecutive_still < 0xFFFFu) {
            a->consecutive_still++;
        }
    } else {
        a->consecutive_still = 0;
    }
    for (int i = 0; i < 3; i++) {
        a->sum_a[i] = 0;
        a->sum_g[i] = 0;
        a->sq_a[i] = 0;
        a->sq_g[i] = 0;
    }
    a->n = 0;
    return true;
}

bool gl_tilt_avg_last_still(const gl_tilt_avg_t *a)
{
    return a->last_still;
}

uint16_t gl_tilt_avg_consecutive_still(const gl_tilt_avg_t *a)
{
    return a->consecutive_still;
}

/* Exact integer part plus fractional part: no precision lost in the float. */
static float mean_i64_(int64_t sum, uint32_t n)
{
    int64_t q = sum / (int64_t)n;
    int64_t r = sum % (int64_t)n;
    return (float)q + (float)r / (float)n;
}

gl_status_t gl_tilt_avg_result(const gl_tilt_avg_t *a, gl_tilt_mean_t *out)
{
    memset(out, 0, sizeof(*out));
    out->blocks_still = a->blocks_still;
    out->blocks_total = a->blocks_total;
    if (a->acc_n == 0u || a->blocks_still == 0u) {
        return GL_ERR_MOTION;
    }
    out->accel_g.x = mean_i64_(a->acc_a[0], a->acc_n) * a->cfg.accel_g_per_lsb;
    out->accel_g.y = mean_i64_(a->acc_a[1], a->acc_n) * a->cfg.accel_g_per_lsb;
    out->accel_g.z = mean_i64_(a->acc_a[2], a->acc_n) * a->cfg.accel_g_per_lsb;
    out->gyro_rad_s.x = mean_i64_(a->acc_g[0], a->acc_n) * a->cfg.gyro_rad_s_per_lsb;
    out->gyro_rad_s.y = mean_i64_(a->acc_g[1], a->acc_n) * a->cfg.gyro_rad_s_per_lsb;
    out->gyro_rad_s.z = mean_i64_(a->acc_g[2], a->acc_n) * a->cfg.gyro_rad_s_per_lsb;
    out->accel_noise_g = sqrtf(a->acc_var_a / (float)a->blocks_still);
    out->samples = a->acc_n;
    return GL_OK;
}

/* ---- calibration ---------------------------------------------------------- */

gl_vec3_t gl_tilt_apply_cal(const gl_cal_tilt_t *cal, gl_vec3_t accel_g, float temp_c)
{
    const float dt = temp_c - cal->t0_c;
    gl_vec3_t v;
    v.x = accel_g.x - (cal->offset_g[0] + dt * (cal->tempco1_g_per_k[0] +
                                                dt * cal->tempco2_g_per_k2[0]));
    v.y = accel_g.y - (cal->offset_g[1] + dt * (cal->tempco1_g_per_k[1] +
                                                dt * cal->tempco2_g_per_k2[1]));
    v.z = accel_g.z - (cal->offset_g[2] + dt * (cal->tempco1_g_per_k[2] +
                                                dt * cal->tempco2_g_per_k2[2]));
    return gl_mat3_mul_vec(&cal->m, v);
}

gl_status_t gl_tilt_six_face_solve(const gl_vec3_t meas[6], gl_vec3_t *offset_g, gl_mat3_t *m)
{
    gl_vec3_t b = { 0.0f, 0.0f, 0.0f };
    gl_mat3_t s; /* measured = S * true + b; columns of S from the face pairs */
    gl_mat3_t inv;

    for (int k = 0; k < 6; k++) {
        b.x += meas[k].x;
        b.y += meas[k].y;
        b.z += meas[k].z;
    }
    b.x /= 6.0f;
    b.y /= 6.0f;
    b.z /= 6.0f;
    for (int axis = 0; axis < 3; axis++) {
        const gl_vec3_t *p = &meas[2 * axis];     /* +axis up */
        const gl_vec3_t *n = &meas[2 * axis + 1]; /* -axis up */
        s.m[0][axis] = 0.5f * (p->x - n->x);
        s.m[1][axis] = 0.5f * (p->y - n->y);
        s.m[2][axis] = 0.5f * (p->z - n->z);
    }
    if (fabsf(b.x) > 0.2f || fabsf(b.y) > 0.2f || fabsf(b.z) > 0.2f) {
        return GL_ERR_RANGE;
    }
    for (int i = 0; i < 3; i++) {
        if (!(s.m[i][i] > 0.8f && s.m[i][i] < 1.2f)) {
            return GL_ERR_RANGE;
        }
    }
    if (gl_mat3_inverse(&s, &inv) != GL_OK) {
        return GL_ERR_RANGE;
    }
    *offset_g = b;
    *m = inv;
    return GL_OK;
}

gl_status_t gl_tilt_tempco_fit(const float *temp_c, const gl_vec3_t *offset_g, unsigned n,
                               float t0_c, gl_cal_tilt_t *cal)
{
    /* Quadratic least squares in the scaled variable x = (T - t0) / 40 K to
     * keep the normal equations well conditioned in single precision. */
    const float scale = 1.0f / 40.0f;
    gl_mat3_t ata, inv;
    float aty[3][3]; /* [axis][power] */
    float s[5] = { 0.0f, 0.0f, 0.0f, 0.0f, 0.0f };

    if (temp_c == NULL || offset_g == NULL || cal == NULL || n < 3u) {
        return GL_ERR_PARAM;
    }
    memset(aty, 0, sizeof(aty));
    for (unsigned k = 0; k < n; k++) {
        float x = (temp_c[k] - t0_c) * scale;
        float xp[5];
        const float y[3] = { offset_g[k].x, offset_g[k].y, offset_g[k].z };
        xp[0] = 1.0f;
        for (int p = 1; p < 5; p++) {
            xp[p] = xp[p - 1] * x;
        }
        for (int p = 0; p < 5; p++) {
            s[p] += xp[p];
        }
        for (int axis = 0; axis < 3; axis++) {
            for (int p = 0; p < 3; p++) {
                aty[axis][p] += xp[p] * y[axis];
            }
        }
    }
    for (int i = 0; i < 3; i++) {
        for (int j = 0; j < 3; j++) {
            ata.m[i][j] = s[i + j];
        }
    }
    if (gl_mat3_inverse(&ata, &inv) != GL_OK) {
        return GL_ERR_RANGE; /* fewer than three distinct temperatures */
    }
    for (int axis = 0; axis < 3; axis++) {
        gl_vec3_t rhs = { aty[axis][0], aty[axis][1], aty[axis][2] };
        gl_vec3_t c = gl_mat3_mul_vec(&inv, rhs);
        cal->offset_g[axis] = c.x;
        cal->tempco1_g_per_k[axis] = c.y * scale;
        cal->tempco2_g_per_k2[axis] = c.z * scale * scale;
    }
    cal->t0_c = t0_c;
    return GL_OK;
}

/* ---- slope ---------------------------------------------------------------- */

gl_status_t gl_tilt_slope(gl_vec3_t accel_cal_g, gl_vec2_t *slope)
{
    float norm = gl_vec3_norm(accel_cal_g);
    float uz;
    if (!(norm > 0.9f && norm < 1.1f)) {
        return GL_ERR_RANGE;
    }
    uz = accel_cal_g.z / norm;
    if (uz < 0.866f) { /* more than 30 degrees from flat */
        return GL_ERR_RANGE;
    }
    slope->x = accel_cal_g.x / accel_cal_g.z;
    slope->y = accel_cal_g.y / accel_cal_g.z;
    return GL_OK;
}

float gl_tilt_slope_percent(gl_vec2_t slope)
{
    return 100.0f * sqrtf(slope.x * slope.x + slope.y * slope.y);
}

float gl_tilt_fall_line_rad(gl_vec2_t slope)
{
    /* Downhill direction d = -slope.  A direction at angle a (CCW from
     * forward = +y) is (-sin a, cos a), so a = atan2(-d.x, d.y). */
    if (slope.x == 0.0f && slope.y == 0.0f) {
        return 0.0f;
    }
    return atan2f(slope.x, -slope.y);
}

gl_vec2_t gl_tilt_slope_along(gl_vec2_t slope_marker, float bearing_rad)
{
    const float sb = sinf(bearing_rad), cb = cosf(bearing_rad);
    gl_vec2_t out;
    /* unit vector toward the target: (-sb, cb); to its left: (-cb, -sb) */
    out.x = -slope_marker.x * sb + slope_marker.y * cb;
    out.y = -slope_marker.x * cb - slope_marker.y * sb;
    return out;
}

gl_vec2_t gl_tilt_slope_to_device(gl_vec2_t slope_marker)
{
    gl_vec2_t out;
    out.x = slope_marker.y;
    out.y = -slope_marker.x;
    return out;
}

/* ---- rotation integrator --------------------------------------------------- */

void gl_rot_int_start(gl_rot_int_t *r, gl_vec3_t gyro_bias_rad_s)
{
    r->q[0] = 1.0f;
    r->q[1] = 0.0f;
    r->q[2] = 0.0f;
    r->q[3] = 0.0f;
    r->bias = gyro_bias_rad_s;
}

void gl_rot_int_add(gl_rot_int_t *r, gl_vec3_t gyro_rad_s, float dt_s)
{
    const float wx = gyro_rad_s.x - r->bias.x;
    const float wy = gyro_rad_s.y - r->bias.y;
    const float wz = gyro_rad_s.z - r->bias.z;
    const float rate = sqrtf(wx * wx + wy * wy + wz * wz);
    const float half = 0.5f * rate * dt_s;
    float dw, k, q0, q1, q2, q3, n;

    if (rate < 1e-9f) {
        return;
    }
    dw = cosf(half);
    k = sinf(half) / rate;
    /* q <- q * dq, dq = (dw, k w): body-frame increment */
    q0 = r->q[0] * dw - k * (r->q[1] * wx + r->q[2] * wy + r->q[3] * wz);
    q1 = r->q[1] * dw + k * (r->q[0] * wx + r->q[2] * wz - r->q[3] * wy);
    q2 = r->q[2] * dw + k * (r->q[0] * wy - r->q[1] * wz + r->q[3] * wx);
    q3 = r->q[3] * dw + k * (r->q[0] * wz + r->q[1] * wy - r->q[2] * wx);
    n = sqrtf(q0 * q0 + q1 * q1 + q2 * q2 + q3 * q3);
    r->q[0] = q0 / n;
    r->q[1] = q1 / n;
    r->q[2] = q2 / n;
    r->q[3] = q3 / n;
}

float gl_rot_int_angle(const gl_rot_int_t *r)
{
    float v = sqrtf(r->q[1] * r->q[1] + r->q[2] * r->q[2] + r->q[3] * r->q[3]);
    return 2.0f * atan2f(v, fabsf(r->q[0]));
}

float gl_rot_int_yaw(const gl_rot_int_t *r, gl_vec3_t up_start)
{
    const gl_vec3_t fwd = { 0.0f, 1.0f, 0.0f };
    const gl_vec3_t qv = { r->q[1], r->q[2], r->q[3] };
    const gl_vec3_t u = gl_vec3_unit(up_start);
    gl_vec3_t t, tt, f_end, f0, f1, c;
    float d0, d1;

    /* forward axis now, expressed in the start frame: v + 2 w (qv x v) + 2 qv x (qv x v) */
    t = gl_vec3_cross(qv, fwd);
    tt = gl_vec3_cross(qv, t);
    f_end.x = fwd.x + 2.0f * (r->q[0] * t.x + tt.x);
    f_end.y = fwd.y + 2.0f * (r->q[0] * t.y + tt.y);
    f_end.z = fwd.z + 2.0f * (r->q[0] * t.z + tt.z);
    /* project both onto the horizontal plane */
    d0 = gl_vec3_dot(fwd, u);
    d1 = gl_vec3_dot(f_end, u);
    f0.x = fwd.x - d0 * u.x;
    f0.y = fwd.y - d0 * u.y;
    f0.z = fwd.z - d0 * u.z;
    f1.x = f_end.x - d1 * u.x;
    f1.y = f_end.y - d1 * u.y;
    f1.z = f_end.z - d1 * u.z;
    c = gl_vec3_cross(f0, f1);
    return atan2f(gl_vec3_dot(c, u), gl_vec3_dot(f0, f1));
}

/* ---- flip calibration and Precision Read ---------------------------------- */

gl_status_t gl_tilt_flip_solve(gl_vec2_t m1, gl_vec2_t m2, float yaw_rad, gl_vec2_t *bias,
                               gl_vec2_t *surface_slope)
{
    const float c = cosf(yaw_rad), s = sinf(yaw_rad);
    const float det = 2.0f * (1.0f - c);
    const float dx = m1.x - m2.x, dy = m1.y - m2.y;
    gl_vec2_t surf;

    if (!(fabsf(fabsf(gl_wrap_pi(yaw_rad)) - GL_PI_F) <= GL_TILT_FLIP_YAW_TOL_RAD)) {
        return GL_ERR_RANGE;
    }
    /* (I - R(-yaw))^-1 = [[1 - c, s], [-s, 1 - c]] / det */
    surf.x = ((1.0f - c) * dx + s * dy) / det;
    surf.y = (-s * dx + (1.0f - c) * dy) / det;
    if (surface_slope != NULL) {
        *surface_slope = surf;
    }
    if (bias != NULL) {
        bias->x = m1.x - surf.x;
        bias->y = m1.y - surf.y;
    }
    return GL_OK;
}

gl_status_t gl_tilt_precision_combine(gl_vec2_t m1, gl_vec2_t m2, float yaw_rad,
                                      const gl_cal_tilt_t *cal, gl_precision_t *out)
{
    gl_status_t st = gl_tilt_flip_solve(m1, m2, yaw_rad, &out->implied_bias, &out->slope);
    float bx = 0.0f, by = 0.0f;
    if (st != GL_OK) {
        return st;
    }
    if (cal != NULL && (cal->flags & GL_CAL_TILT_FLAG_FLIP) != 0u) {
        bx = cal->flip_bias_x;
        by = cal->flip_bias_y;
    }
    bx = out->implied_bias.x - bx;
    by = out->implied_bias.y - by;
    out->bias_mismatch = sqrtf(bx * bx + by * by);
    out->yaw_rad = yaw_rad;
    return GL_OK;
}

/* ---- Survey ---------------------------------------------------------------- */

void gl_survey_reset(gl_survey_t *s)
{
    memset(s, 0, sizeof(*s));
}

gl_status_t gl_survey_add(gl_survey_t *s, const gl_survey_drop_t *d)
{
    if (s->count >= GL_SURVEY_MAX_DROPS) {
        return GL_ERR_FULL;
    }
    if ((d->flags & GL_DROP_FLAG_STICK) == 0u || !(d->range_m > 0.0f)) {
        return GL_ERR_PARAM;
    }
    s->drop[s->count++] = *d;
    return GL_OK;
}

int gl_survey_farthest(const gl_survey_t *s)
{
    int best = -1;
    float far = -1.0f;
    for (unsigned i = 0; i < s->count; i++) {
        if (s->drop[i].range_m > far) {
            far = s->drop[i].range_m;
            best = (int)i;
        }
    }
    return best;
}
