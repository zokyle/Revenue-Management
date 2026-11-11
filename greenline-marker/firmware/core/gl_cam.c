/* gl_cam.c - see gl_cam.h. */
#include "gl_cam.h"

#include <math.h>

void gl_cam_model_init(gl_cam_model_t *m, const gl_cal_cam_t *cal)
{
    /* nominal mounting: camera (x right, y down, z forward) -> marker
     * (x right, y forward, z up) */
    const gl_mat3_t r_nom = { { { 1.0f, 0.0f, 0.0f }, { 0.0f, 0.0f, 1.0f }, { 0.0f, -1.0f, 0.0f } } };
    const float cy = cosf(cal->yaw_left_rad), sy = sinf(cal->yaw_left_rad);
    const float cp = cosf(cal->pitch_up_rad), sp = sinf(cal->pitch_up_rad);
    const float cr = cosf(cal->roll_rad), sr = sinf(cal->roll_rad);
    const gl_mat3_t rz_yaw = { { { cy, -sy, 0.0f }, { sy, cy, 0.0f }, { 0.0f, 0.0f, 1.0f } } };
    const gl_mat3_t rx_pitch = { { { 1.0f, 0.0f, 0.0f }, { 0.0f, cp, -sp }, { 0.0f, sp, cp } } };
    const gl_mat3_t rz_roll = { { { cr, -sr, 0.0f }, { sr, cr, 0.0f }, { 0.0f, 0.0f, 1.0f } } };
    gl_mat3_t t1 = gl_mat3_mul(&r_nom, &rz_roll);
    gl_mat3_t t2 = gl_mat3_mul(&rx_pitch, &t1);

    m->fx = cal->fx_px;
    m->fy = cal->fy_px;
    m->cx = cal->cx_px;
    m->cy = cal->cy_px;
    m->k1 = cal->k1;
    m->r_cm = gl_mat3_mul(&rz_yaw, &t2);
    m->pos_m.x = 0.001f * cal->pos_mm[0];
    m->pos_m.y = 0.001f * cal->pos_mm[1];
    m->pos_m.z = 0.001f * cal->pos_mm[2];
}

void gl_cam_undistort(const gl_cam_model_t *m, float u, float v, float *xu, float *yu)
{
    const float xd = (u - m->cx) / m->fx;
    const float yd = (v - m->cy) / m->fy;
    float x = xd, y = yd;
    if (m->k1 != 0.0f) {
        /* fixed-point inversion of (xd, yd) = (x, y) (1 + k1 r^2); converges
         * quickly for the |k1 r^2| < 0.3 this lens can have */
        for (int i = 0; i < 6; i++) {
            float s = 1.0f + m->k1 * (x * x + y * y);
            x = xd / s;
            y = yd / s;
        }
    }
    *xu = x;
    *yu = y;
}

gl_vec3_t gl_cam_pixel_to_ray(const gl_cam_model_t *m, float u, float v)
{
    gl_vec3_t c;
    gl_cam_undistort(m, u, v, &c.x, &c.y);
    c.z = 1.0f;
    return gl_vec3_unit(gl_mat3_mul_vec(&m->r_cm, c));
}

bool gl_cam_ray_to_pixel(const gl_cam_model_t *m, gl_vec3_t ray_marker, float *u, float *v)
{
    /* marker -> camera: transpose of r_cm */
    const gl_mat3_t r_mc = gl_mat3_transpose(&m->r_cm);
    const gl_vec3_t c = gl_mat3_mul_vec(&r_mc, ray_marker);
    float x, y, s;
    if (!(c.z > 1e-6f)) {
        return false;
    }
    x = c.x / c.z;
    y = c.y / c.z;
    s = 1.0f + m->k1 * (x * x + y * y);
    *u = m->cx + m->fx * x * s;
    *v = m->cy + m->fy * y * s;
    return true;
}

bool gl_cam_point_to_pixel(const gl_cam_model_t *m, gl_vec3_t p, float *u, float *v)
{
    gl_vec3_t d;
    d.x = p.x - m->pos_m.x;
    d.y = p.y - m->pos_m.y;
    d.z = p.z - m->pos_m.z;
    return gl_cam_ray_to_pixel(m, d, u, v);
}

/* Level forward and right unit vectors for a given up vector. */
static void level_axes_(gl_vec3_t up, gl_vec3_t *u, gl_vec3_t *fwd, gl_vec3_t *right)
{
    const gl_vec3_t y = { 0.0f, 1.0f, 0.0f };
    float d;
    *u = gl_vec3_unit(up);
    d = gl_vec3_dot(y, *u);
    fwd->x = y.x - d * u->x;
    fwd->y = y.y - d * u->y;
    fwd->z = y.z - d * u->z;
    *fwd = gl_vec3_unit(*fwd);
    *right = gl_vec3_cross(*fwd, *u);
}

void gl_cam_ray_to_bearing_elev(gl_vec3_t ray_marker, gl_vec3_t up_marker, float *bearing_rad,
                                float *elev_rad)
{
    gl_vec3_t u, f, r;
    const gl_vec3_t d = gl_vec3_unit(ray_marker);
    level_axes_(up_marker, &u, &f, &r);
    *elev_rad = asinf(gl_clampf(gl_vec3_dot(d, u), -1.0f, 1.0f));
    *bearing_rad = atan2f(-gl_vec3_dot(d, r), gl_vec3_dot(d, f));
}

void gl_cam_pixel_to_bearing_elev(const gl_cam_model_t *m, float u, float v, gl_vec3_t up_marker,
                                  float *bearing_rad, float *elev_rad)
{
    gl_cam_ray_to_bearing_elev(gl_cam_pixel_to_ray(m, u, v), up_marker, bearing_rad, elev_rad);
}

gl_vec3_t gl_cam_bearing_elev_to_ray(float bearing_rad, float elev_rad, gl_vec3_t up_marker)
{
    gl_vec3_t u, f, r, d;
    const float ce = cosf(elev_rad), se = sinf(elev_rad);
    const float cb = cosf(bearing_rad), sb = sinf(bearing_rad);
    level_axes_(up_marker, &u, &f, &r);
    /* level direction at bearing b (CCW = toward -right): cb * fwd - sb * right */
    d.x = ce * (cb * f.x - sb * r.x) + se * u.x;
    d.y = ce * (cb * f.y - sb * r.y) + se * u.y;
    d.z = ce * (cb * f.z - sb * r.z) + se * u.z;
    return d;
}

void gl_cam_pixel_to_rectified(const gl_cam_model_t *m, float u, float v, float *xr, float *yr)
{
    gl_vec3_t c, r;
    gl_cam_undistort(m, u, v, &c.x, &c.y);
    c.z = 1.0f;
    r = gl_mat3_mul_vec(&m->r_cm, c);
    *xr = r.x / r.y;
    *yr = -r.z / r.y;
}

float gl_cam_base_plane_row(const gl_cam_model_t *m, float u)
{
    /* Find v such that the ray through (u, v) has zero marker z.  One Newton
     * step from the principal row is exact for an undistorted camera and
     * accurate to a small fraction of a row otherwise; two are used. */
    float v = m->cy;
    for (int i = 0; i < 3; i++) {
        float xr, yr0, yr1;
        gl_cam_pixel_to_rectified(m, u, v, &xr, &yr0);
        gl_cam_pixel_to_rectified(m, u, v + 1.0f, &xr, &yr1);
        if (fabsf(yr1 - yr0) < 1e-9f) {
            break;
        }
        v -= yr0 / (yr1 - yr0);
    }
    return v;
}
