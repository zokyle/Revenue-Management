/*
 * test_cam.c - camera model: pixel <-> ray, distortion, extrinsics,
 * bearing / elevation relative to gravity, rectification, horizon row.
 */
#include "gl_cam.h"
#include "gl_config.h"
#include "gl_test.h"

static gl_vec3_t v3(float x, float y, float z)
{
    gl_vec3_t v = { x, y, z };
    return v;
}

GL_TEST(test_nominal_camera)
{
    gl_cal_cam_t cal;
    gl_cam_model_t m;
    float b, e, u, v;
    const gl_vec3_t up = v3(0, 0, 1);

    gl_cal_cam_defaults(&cal, 0);
    GL_CHECK_NEAR(cal.fx_px, 657.0, 1e-6);
    GL_CHECK_NEAR(cal.cx_px, 319.5, 1e-6);
    GL_CHECK_NEAR(cal.cy_px, 239.5, 1e-6);
    GL_CHECK_NEAR(cal.pos_mm[0], -10.2, 1e-5);
    GL_CHECK_NEAR(cal.pos_mm[2], 5.61, 1e-5);
    gl_cam_model_init(&m, &cal);

    /* principal point looks straight ahead and level */
    gl_cam_pixel_to_bearing_elev(&m, 319.5f, 239.5f, up, &b, &e);
    GL_CHECK_NEAR(b, 0.0, 1e-6);
    GL_CHECK_NEAR(e, 0.0, 1e-6);
    {
        gl_vec3_t r = gl_cam_pixel_to_ray(&m, 319.5f, 239.5f);
        GL_CHECK_NEAR(r.x, 0.0, 1e-6);
        GL_CHECK_NEAR(r.y, 1.0, 1e-6);
        GL_CHECK_NEAR(r.z, 0.0, 1e-6);
    }
    /* 100 px to the RIGHT is a NEGATIVE bearing (left is positive) */
    gl_cam_pixel_to_bearing_elev(&m, 419.5f, 239.5f, up, &b, &e);
    GL_CHECK_NEAR(b, -atan(100.0 / 657.0), 1e-6);
    GL_CHECK_NEAR(e, 0.0, 1e-6);
    /* 50 rows UP (smaller row number) is a positive elevation */
    gl_cam_pixel_to_bearing_elev(&m, 319.5f, 189.5f, up, &b, &e);
    GL_CHECK_NEAR(e, atan(50.0 / 657.0), 1e-6);
    GL_CHECK_NEAR(b, 0.0, 1e-6);
    /* one pixel is 1.52 mrad: a 15 mm stick at 10 m is about one pixel */
    GL_CHECK_NEAR(0.015 / 10.0 * 657.0, 0.9855, 1e-3);

    /* a point 5 m ahead, 0.3 m left, 1 m up, seen from the left camera */
    GL_CHECK(gl_cam_point_to_pixel(&m, v3(-0.3f, 5.0f, 1.0f), &u, &v));
    {
        double dx = -0.3 + 0.0102, dy = 5.0 - 0.0156, dz = 1.0 - 0.00561;
        GL_CHECK_NEAR(u, 319.5 + 657.0 * dx / dy, 2e-3);
        GL_CHECK_NEAR(v, 239.5 - 657.0 * dz / dy, 2e-3);
    }
    /* behind the camera */
    GL_CHECK(!gl_cam_point_to_pixel(&m, v3(0.0f, -1.0f, 0.0f), &u, &v));
    /* horizon row of the base plane = principal row for a nominal camera */
    GL_CHECK_NEAR(gl_cam_base_plane_row(&m, 100.0f), 239.5, 1e-3);
    GL_CHECK_NEAR(gl_cam_base_plane_row(&m, 600.0f), 239.5, 1e-3);
}

GL_TEST(test_distortion_roundtrip)
{
    gl_cal_cam_t cal;
    gl_cam_model_t m;
    double worst = 0;
    gl_cal_cam_defaults(&cal, 1);
    cal.k1 = -0.12f;
    cal.fx_px = 661.0f;
    cal.fy_px = 655.0f;
    cal.cx_px = 325.2f;
    cal.cy_px = 233.7f;
    cal.pitch_up_rad = 0.012f;
    cal.yaw_left_rad = -0.007f;
    cal.roll_rad = 0.004f;
    gl_cam_model_init(&m, &cal);
    for (int vv = 0; vv < 480; vv += 37) {
        for (int uu = 0; uu < 640; uu += 41) {
            float u2 = 0, v2 = 0;
            gl_vec3_t r = gl_cam_pixel_to_ray(&m, (float)uu, (float)vv);
            GL_CHECK_NEAR(gl_vec3_norm(r), 1.0, 1e-5);
            GL_CHECK(gl_cam_ray_to_pixel(&m, r, &u2, &v2));
            double e = fabs((double)u2 - uu) + fabs((double)v2 - vv);
            if (e > worst) {
                worst = e;
            }
        }
    }
    printf("    pixel -> ray -> pixel with k1 = -0.12 and misalignment: worst error %.4f px\n",
           worst);
    GL_CHECK(worst < 0.01);
    /* barrel distortion (k1 < 0): a corner pixel looks further out than a
     * pinhole would say */
    {
        float xu, yu;
        gl_cam_undistort(&m, 0.0f, 0.0f, &xu, &yu);
        GL_CHECK(fabsf(xu) > 325.2f / 661.0f);
    }
}

GL_TEST(test_extrinsics_signs)
{
    gl_cal_cam_t cal;
    gl_cam_model_t m;
    float b, e;
    const gl_vec3_t up = v3(0, 0, 1);

    /* camera pitched UP by 10 mrad: the principal point looks up */
    gl_cal_cam_defaults(&cal, 0);
    cal.pitch_up_rad = 0.010f;
    gl_cam_model_init(&m, &cal);
    gl_cam_pixel_to_bearing_elev(&m, 319.5f, 239.5f, up, &b, &e);
    GL_CHECK_NEAR(e, 0.010, 1e-6);
    GL_CHECK_NEAR(b, 0.0, 1e-6);
    /* ... so the base plane appears BELOW the principal row */
    GL_CHECK_NEAR(gl_cam_base_plane_row(&m, 319.5f), 239.5 + 657.0 * tan(0.010), 2e-3);

    /* camera yawed LEFT by 20 mrad: the principal point has bearing +20 mrad */
    gl_cal_cam_defaults(&cal, 0);
    cal.yaw_left_rad = 0.020f;
    gl_cam_model_init(&m, &cal);
    gl_cam_pixel_to_bearing_elev(&m, 319.5f, 239.5f, up, &b, &e);
    GL_CHECK_NEAR(b, 0.020, 1e-6);
    GL_CHECK_NEAR(e, 0.0, 1e-6);

    /* roll: a pixel to the right of centre moves up or down, the centre stays */
    gl_cal_cam_defaults(&cal, 0);
    cal.roll_rad = 0.010f;
    gl_cam_model_init(&m, &cal);
    gl_cam_pixel_to_bearing_elev(&m, 319.5f, 239.5f, up, &b, &e);
    GL_CHECK_NEAR(e, 0.0, 1e-6);
    gl_cam_pixel_to_bearing_elev(&m, 519.5f, 239.5f, up, &b, &e);
    GL_CHECK_NEAR(fabs((double)e), 0.010 * 200.0 / 657.0 * cos(atan(200.0 / 657.0)), 3e-5);
}

GL_TEST(test_gravity_reference)
{
    gl_cal_cam_t cal;
    gl_cam_model_t m;
    float b, e;
    gl_cal_cam_defaults(&cal, 0);
    gl_cam_model_init(&m, &cal);

    /* Marker on a 3 % upslope along its forward axis: its nose points up, so
     * world "up" has a positive forward component in marker axes. */
    {
        const float t = atanf(0.03f);
        const gl_vec3_t up = v3(0.0f, sinf(t), cosf(t));
        /* the optical axis is then elevated by t against gravity */
        gl_cam_pixel_to_bearing_elev(&m, 319.5f, 239.5f, up, &b, &e);
        GL_CHECK_NEAR(e, t, 1e-6);
        GL_CHECK_NEAR(b, 0.0, 1e-6);
        /* a flagstick base on the same plane 6 m ahead is seen 5.6 mm below
         * the lens: -0.93 mrad relative to the PLANE, i.e. t - 0.93 mrad
         * relative to gravity: the uphill is visible in the elevation */
        {
            float u, v;
            GL_CHECK(gl_cam_point_to_pixel(&m, v3(-0.0102f, 6.0f, 0.0f), &u, &v));
            gl_cam_pixel_to_bearing_elev(&m, u, v, up, &b, &e);
            GL_CHECK_NEAR(e, (double)t - 0.00561 / (6.0 - 0.0156), 1e-5);
        }
    }
    /* Marker rolled (cross slope 2 %, uphill to the right): a level target
     * dead ahead is still at elevation 0 and bearing 0 */
    {
        const float t = atanf(0.02f);
        const gl_vec3_t up = v3(sinf(t), 0.0f, cosf(t));
        gl_cam_pixel_to_bearing_elev(&m, 319.5f, 239.5f, up, &b, &e);
        GL_CHECK_NEAR(e, 0.0, 1e-6);
        GL_CHECK_NEAR(b, 0.0, 1e-6);
        /* but a pixel 200 px to the right is BELOW the level plane by
         * about 2 % of its sideways angle, although it is on the image's
         * principal row: the image horizon is tilted */
        gl_cam_pixel_to_bearing_elev(&m, 519.5f, 239.5f, up, &b, &e);
        GL_CHECK(e > 0.0f); /* right side of the marker is uphill -> looks up */
        GL_CHECK_NEAR(e, 0.02 * (200.0 / 657.0) / sqrt(1.0 + (200.0 / 657.0) * (200.0 / 657.0)),
                      2e-4);
    }
    /* bearing / elevation -> ray -> bearing / elevation */
    {
        const gl_vec3_t up = gl_vec3_unit(v3(0.02f, -0.03f, 1.0f));
        for (float bb = -0.4f; bb <= 0.4f; bb += 0.1f) {
            for (float ee = -0.05f; ee <= 0.3f; ee += 0.07f) {
                gl_vec3_t r = gl_cam_bearing_elev_to_ray(bb, ee, up);
                gl_cam_ray_to_bearing_elev(r, up, &b, &e);
                GL_CHECK_NEAR(b, bb, 2e-6);
                GL_CHECK_NEAR(e, ee, 2e-6);
            }
        }
    }
}

GL_TEST(test_rectified_stereo)
{
    gl_cal_cam_t cl, cr;
    gl_cam_model_t ml, mr;
    double worst = 0, worst_raw = 0;
    gl_cal_cam_defaults(&cl, 0);
    gl_cal_cam_defaults(&cr, 1);
    /* a realistic mis-mounting of the right camera */
    cr.yaw_left_rad = 0.006f;
    cr.pitch_up_rad = -0.004f;
    cr.roll_rad = 0.008f;
    cr.k1 = -0.05f;
    cl.k1 = -0.04f;
    cr.cx_px = 323.0f;
    cr.cy_px = 236.0f;
    gl_cam_model_init(&ml, &cl);
    gl_cam_model_init(&mr, &cr);
    for (float z = 2.0f; z <= 12.0f; z += 2.5f) {
        for (float x = -1.0f; x <= 1.0f; x += 0.5f) {
            for (float h = 0.0f; h <= 0.5f; h += 0.25f) {
                float ul, vl, ur, vr, xl, yl, xr, yr;
                const gl_vec3_t p = v3(x, z, h);
                GL_CHECK(gl_cam_point_to_pixel(&ml, p, &ul, &vl));
                GL_CHECK(gl_cam_point_to_pixel(&mr, p, &ur, &vr));
                gl_cam_pixel_to_rectified(&ml, ul, vl, &xl, &yl);
                gl_cam_pixel_to_rectified(&mr, ur, vr, &xr, &yr);
                /* rectified disparity = f B / depth, rows match */
                double depth = (double)z - 0.0156;
                double d = 657.0 * (double)(xl - xr);
                double e = fabs(d - 657.0 * 0.0204 / depth);
                if (e > worst) {
                    worst = e;
                }
                GL_CHECK_NEAR(yl, yr, 2e-5);
                e = fabs((double)(ul - ur) - 657.0 * 0.0204 / depth);
                if (e > worst_raw) {
                    worst_raw = e;
                }
            }
        }
    }
    printf("    rectified disparity error with a mis-mounted, distorted right camera: "
           "%.4f px (raw column difference: %.1f px)\n", worst, worst_raw);
    GL_CHECK(worst < 0.01);
    GL_CHECK(worst_raw > 2.0);
}

int main(void)
{
    GL_RUN(test_nominal_camera);
    GL_RUN(test_distortion_roundtrip);
    GL_RUN(test_extrinsics_signs);
    GL_RUN(test_gravity_reference);
    GL_RUN(test_rectified_stereo);
    return gl_test_summary();
}
