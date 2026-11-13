/*
 * gl_math.c - status names, small linear algebra, median, float packing.
 * Portable C99, single-precision only, no allocation, no recursion.
 */
#include "gl_types.h"

#include <math.h>
#include <string.h>

const char *gl_status_name(gl_status_t st)
{
    switch (st) {
    case GL_OK: return "OK";
    case GL_ERR_PARAM: return "PARAM";
    case GL_ERR_NOT_IMPLEMENTED: return "NOT_IMPLEMENTED";
    case GL_ERR_TIMEOUT: return "TIMEOUT";
    case GL_ERR_IO: return "IO";
    case GL_ERR_CRC: return "CRC";
    case GL_ERR_FULL: return "FULL";
    case GL_ERR_EMPTY: return "EMPTY";
    case GL_ERR_RANGE: return "RANGE";
    case GL_ERR_BUSY: return "BUSY";
    case GL_ERR_NOT_FOUND: return "NOT_FOUND";
    case GL_ERR_NO_STICK: return "NO_STICK";
    case GL_ERR_QUALITY: return "QUALITY";
    case GL_ERR_MOTION: return "MOTION";
    case GL_ERR_CORRUPT: return "CORRUPT";
    case GL_ERR_STATE: return "STATE";
    case GL_ERR_UNSUPPORTED: return "UNSUPPORTED";
    default: return "?";
    }
}

float gl_wrap_pi(float a_rad)
{
    /* Bounded loops: callers pass angles within a few turns. */
    int guard = 0;
    while (a_rad > GL_PI_F && guard < 64) {
        a_rad -= GL_TWO_PI_F;
        guard++;
    }
    while (a_rad <= -GL_PI_F && guard < 128) {
        a_rad += GL_TWO_PI_F;
        guard++;
    }
    return a_rad;
}

gl_vec3_t gl_mat3_mul_vec(const gl_mat3_t *m, gl_vec3_t x)
{
    gl_vec3_t y;
    y.x = m->m[0][0] * x.x + m->m[0][1] * x.y + m->m[0][2] * x.z;
    y.y = m->m[1][0] * x.x + m->m[1][1] * x.y + m->m[1][2] * x.z;
    y.z = m->m[2][0] * x.x + m->m[2][1] * x.y + m->m[2][2] * x.z;
    return y;
}

gl_mat3_t gl_mat3_mul(const gl_mat3_t *a, const gl_mat3_t *b)
{
    gl_mat3_t c;
    for (int i = 0; i < 3; i++) {
        for (int j = 0; j < 3; j++) {
            c.m[i][j] = a->m[i][0] * b->m[0][j] + a->m[i][1] * b->m[1][j] +
                        a->m[i][2] * b->m[2][j];
        }
    }
    return c;
}

gl_mat3_t gl_mat3_transpose(const gl_mat3_t *a)
{
    gl_mat3_t t;
    for (int i = 0; i < 3; i++) {
        for (int j = 0; j < 3; j++) {
            t.m[i][j] = a->m[j][i];
        }
    }
    return t;
}

gl_mat3_t gl_mat3_identity(void)
{
    gl_mat3_t i3;
    memset(&i3, 0, sizeof(i3));
    i3.m[0][0] = 1.0f;
    i3.m[1][1] = 1.0f;
    i3.m[2][2] = 1.0f;
    return i3;
}

gl_status_t gl_mat3_inverse(const gl_mat3_t *a, gl_mat3_t *out)
{
    const float (*m)[3] = a->m;
    float c00 = m[1][1] * m[2][2] - m[1][2] * m[2][1];
    float c01 = m[1][2] * m[2][0] - m[1][0] * m[2][2];
    float c02 = m[1][0] * m[2][1] - m[1][1] * m[2][0];
    float det = m[0][0] * c00 + m[0][1] * c01 + m[0][2] * c02;
    if (fabsf(det) < 1e-9f) {
        return GL_ERR_RANGE;
    }
    float inv = 1.0f / det;
    out->m[0][0] = c00 * inv;
    out->m[0][1] = (m[0][2] * m[2][1] - m[0][1] * m[2][2]) * inv;
    out->m[0][2] = (m[0][1] * m[1][2] - m[0][2] * m[1][1]) * inv;
    out->m[1][0] = c01 * inv;
    out->m[1][1] = (m[0][0] * m[2][2] - m[0][2] * m[2][0]) * inv;
    out->m[1][2] = (m[0][2] * m[1][0] - m[0][0] * m[1][2]) * inv;
    out->m[2][0] = c02 * inv;
    out->m[2][1] = (m[0][1] * m[2][0] - m[0][0] * m[2][1]) * inv;
    out->m[2][2] = (m[0][0] * m[1][1] - m[0][1] * m[1][0]) * inv;
    return GL_OK;
}

gl_mat3_t gl_mat3_from_euler(float roll_x_rad, float pitch_y_rad, float yaw_z_rad)
{
    float cr = cosf(roll_x_rad), sr = sinf(roll_x_rad);
    float cp = cosf(pitch_y_rad), sp = sinf(pitch_y_rad);
    float cy = cosf(yaw_z_rad), sy = sinf(yaw_z_rad);
    gl_mat3_t r;
    /* R = Rz(yaw) * Ry(pitch) * Rx(roll) */
    r.m[0][0] = cy * cp;
    r.m[0][1] = cy * sp * sr - sy * cr;
    r.m[0][2] = cy * sp * cr + sy * sr;
    r.m[1][0] = sy * cp;
    r.m[1][1] = sy * sp * sr + cy * cr;
    r.m[1][2] = sy * sp * cr - cy * sr;
    r.m[2][0] = -sp;
    r.m[2][1] = cp * sr;
    r.m[2][2] = cp * cr;
    return r;
}

float gl_vec3_dot(gl_vec3_t a, gl_vec3_t b)
{
    return a.x * b.x + a.y * b.y + a.z * b.z;
}

gl_vec3_t gl_vec3_cross(gl_vec3_t a, gl_vec3_t b)
{
    gl_vec3_t c;
    c.x = a.y * b.z - a.z * b.y;
    c.y = a.z * b.x - a.x * b.z;
    c.z = a.x * b.y - a.y * b.x;
    return c;
}

float gl_vec3_norm(gl_vec3_t a)
{
    return sqrtf(gl_vec3_dot(a, a));
}

gl_vec3_t gl_vec3_unit(gl_vec3_t a)
{
    float n = gl_vec3_norm(a);
    gl_vec3_t u;
    if (n < 1e-12f) {
        u.x = 0.0f;
        u.y = 0.0f;
        u.z = 1.0f;
        return u;
    }
    u.x = a.x / n;
    u.y = a.y / n;
    u.z = a.z / n;
    return u;
}

/* Shell sort (non-recursive) with Ciura's gap sequence: about half the
 * moves of the n/2, n/4, ... sequence for the 150-480 element arrays of the
 * vision code. */
static void shell_sort_(float *v, size_t n)
{
    static const uint16_t gaps[8] = { 701, 301, 132, 57, 23, 10, 4, 1 };
    for (unsigned g = 0; g < 8u; g++) {
        const size_t gap = gaps[g];
        for (size_t i = gap; i < n; i++) {
            float t = v[i];
            size_t j = i;
            while (j >= gap && v[j - gap] > t) {
                v[j] = v[j - gap];
                j -= gap;
            }
            v[j] = t;
        }
    }
}

float gl_median_inplace(float *v, size_t n)
{
    if (n == 0u) {
        return 0.0f;
    }
    shell_sort_(v, n);
    if ((n & 1u) != 0u) {
        return v[n / 2u];
    }
    return 0.5f * (v[n / 2u - 1u] + v[n / 2u]);
}

float gl_select_inplace(float *v, size_t n, size_t k)
{
    ptrdiff_t lo = 0, hi, kk;
    unsigned rounds = 0;

    if (n == 0u) {
        return 0.0f;
    }
    if (k >= n) {
        k = n - 1u;
    }
    kk = (ptrdiff_t)k;
    hi = (ptrdiff_t)n - 1;
    /* Wirth's selection: partition v[lo..hi] about a value x taken from it,
     * then keep the side that holds index k.  Invariant: nothing left of lo
     * is larger and nothing right of hi is smaller than any element of
     * v[lo..hi].  The two scans cannot leave [lo, hi]: the first time they
     * are stopped by an element equal to x, afterwards by an element the
     * previous swap put there; and every round takes at least one element
     * off each end it keeps. */
    while (lo < hi) {
        /* pivot: the median of the first, the k-th and the last element */
        const float a = v[lo], b = v[kk], c = v[hi];
        const float x = (a < b) ? ((b < c) ? b : ((a < c) ? c : a))
                                : ((a < c) ? a : ((b < c) ? c : b));
        ptrdiff_t i = lo, j = hi;
        if (++rounds > GL_SELECT_MAX_ROUNDS) {
            /* a pathological order: finish with the sort, on what is left */
            shell_sort_(&v[lo], (size_t)(hi - lo + 1));
            break;
        }
        do {
            while (v[i] < x) {
                i++;
            }
            while (x < v[j]) {
                j--;
            }
            if (i <= j) {
                const float t = v[i];
                v[i] = v[j];
                v[j] = t;
                i++;
                j--;
            }
        } while (i <= j);
        if (j < kk) {
            lo = i;
        }
        if (kk < i) {
            hi = j;
        }
    }
    return v[kk];
}

float gl_median_select(float *v, size_t n)
{
    float hi_mid, lo_mid;
    if (n == 0u) {
        return 0.0f;
    }
    hi_mid = gl_select_inplace(v, n, n / 2u);
    if ((n & 1u) != 0u) {
        return hi_mid;
    }
    /* even n: the other middle value is the largest of the lower half */
    lo_mid = v[0];
    for (size_t i = 1; i < n / 2u; i++) {
        if (v[i] > lo_mid) {
            lo_mid = v[i];
        }
    }
    return 0.5f * (lo_mid + hi_mid);
}

void gl_put_f32(uint8_t *p, float v)
{
    uint32_t u;
    memcpy(&u, &v, sizeof(u));
    gl_put_u32(p, u);
}

float gl_get_f32(const uint8_t *p)
{
    uint32_t u = gl_get_u32(p);
    float v;
    memcpy(&v, &u, sizeof(v));
    return v;
}
