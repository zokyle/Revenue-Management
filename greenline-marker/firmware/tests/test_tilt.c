/*
 * test_tilt.c - block averaging with stillness gating, calibration maths,
 * slope conversion, gyro rotation integrator, flip calibration, Precision
 * Read combining and the Survey store.
 */
#include <stdlib.h>

#include "gl_test.h"
#include "gl_tilt.h"

#define ACC_LSB 0.000061f   /* +-2 g range; value only used inside this test */
#define GYR_LSB 0.00015272f /* 8.75 mdps per LSB in rad/s */

static uint32_t rng_state = 1;
static double urand(void)
{
    rng_state = rng_state * 1664525u + 1013904223u;
    return ((double)(rng_state >> 8) + 0.5) / 16777216.0;
}
static double nrand(void)
{
    return sqrt(-2.0 * log(urand())) * cos(6.283185307179586 * urand());
}

static gl_imu_raw_t sample(double ax, double ay, double az, double noise_g, double gz_rad_s)
{
    gl_imu_raw_t s;
    s.ax = (int16_t)lrint((ax + noise_g * nrand()) / (double)ACC_LSB);
    s.ay = (int16_t)lrint((ay + noise_g * nrand()) / (double)ACC_LSB);
    s.az = (int16_t)lrint((az + noise_g * nrand()) / (double)ACC_LSB);
    s.gx = (int16_t)lrint(0.002 * nrand() / (double)GYR_LSB);
    s.gy = (int16_t)lrint(0.002 * nrand() / (double)GYR_LSB);
    s.gz = (int16_t)lrint((gz_rad_s + 0.002 * nrand()) / (double)GYR_LSB);
    return s;
}

static gl_tilt_cfg_t cfg_default(void)
{
    gl_tilt_cfg_t c;
    gl_tilt_cfg_defaults(&c);
    c.accel_g_per_lsb = ACC_LSB;
    c.gyro_rad_s_per_lsb = GYR_LSB;
    return c;
}

GL_TEST(test_block_average_precision)
{
    gl_tilt_cfg_t cfg = cfg_default();
    gl_tilt_avg_t a;
    gl_tilt_mean_t m;
    gl_imu_raw_t s;
    int blocks = 0;

    /* constant input: the mean is exact to float rounding */
    gl_tilt_avg_init(&a, &cfg);
    s.ax = 123;
    s.ay = -456;
    s.az = 16300;
    s.gx = 5;
    s.gy = -7;
    s.gz = 11;
    for (int i = 0; i < 240; i++) {
        if (gl_tilt_avg_add(&a, &s)) {
            blocks++;
            GL_CHECK(gl_tilt_avg_last_still(&a));
        }
    }
    GL_CHECK_EQ(blocks, 7); /* 240 / 32 */
    GL_CHECK_EQ(gl_tilt_avg_consecutive_still(&a), 7);
    GL_CHECK_EQ(gl_tilt_avg_result(&a, &m), GL_OK);
    GL_CHECK_EQ(m.samples, 224);
    GL_CHECK_NEAR(m.accel_g.x, 123.0 * (double)ACC_LSB, 1e-9);
    GL_CHECK_NEAR(m.accel_g.y, -456.0 * (double)ACC_LSB, 1e-9);
    GL_CHECK_NEAR(m.accel_g.z, 16300.0 * (double)ACC_LSB, 1e-7);
    GL_CHECK_NEAR(m.gyro_rad_s.z, 11.0 * (double)GYR_LSB, 1e-9);
    GL_CHECK_NEAR(m.accel_noise_g, 0.0, 1e-9);

    /* noisy input: 1 s at 240 Hz with 1 mg rms noise -> mean good to
     * 1 mg / sqrt(224) = 0.07 mg (3 sigma = 0.2 mg = 0.2 mrad) */
    {
        double worst = 0;
        rng_state = 42;
        for (int trial = 0; trial < 200; trial++) {
            const double tx = 0.0123, ty = -0.0271;
            const double tz = sqrt(1.0 - tx * tx - ty * ty);
            gl_tilt_avg_reset(&a);
            for (int i = 0; i < 240; i++) {
                gl_imu_raw_t sn = sample(tx, ty, tz, 0.001, 0.0);
                gl_tilt_avg_add(&a, &sn);
            }
            GL_CHECK_EQ(gl_tilt_avg_result(&a, &m), GL_OK);
            GL_CHECK_EQ(m.blocks_still, 7);
            double e = fabs((double)m.accel_g.x - tx);
            if (e > worst) {
                worst = e;
            }
            GL_CHECK_NEAR(m.accel_noise_g, 0.001, 0.0002);
        }
        printf("    1 s average, 1 mg rms noise: worst x error over 200 trials = %.3f mg\n",
               worst * 1000.0);
        GL_CHECK(worst < 0.00030);
    }
}

GL_TEST(test_stillness_gating)
{
    gl_tilt_cfg_t cfg = cfg_default();
    gl_tilt_avg_t a;
    gl_tilt_mean_t m;
    int verdicts[10], nb = 0;

    rng_state = 7;
    gl_tilt_avg_init(&a, &cfg);
    /* blocks 0-2 still, block 3 shaken (accel), block 4 rotating (gyro
     * noise), blocks 5-6 still but at a different tilt (step test fires on
     * block 5 only), block 7 still */
    for (int i = 0; i < 8 * 32; i++) {
        int blk = i / 32;
        gl_imu_raw_t s;
        if (blk == 3) {
            s = sample(0.01, 0.0, 1.0, 0.03, 0.0);
        } else if (blk == 4) {
            s = sample(0.01, 0.0, 1.0, 0.001, 0.0);
            s.gz = (int16_t)((i & 1) ? 800 : -800); /* +-0.12 rad/s chatter */
        } else if (blk >= 5) {
            s = sample(0.02, 0.0, 1.0, 0.001, 0.0);
        } else {
            s = sample(0.01, 0.0, 1.0, 0.001, 0.0);
        }
        if (gl_tilt_avg_add(&a, &s)) {
            verdicts[nb++] = gl_tilt_avg_last_still(&a) ? 1 : 0;
            if (blk == 2) {
                GL_CHECK_EQ(gl_tilt_avg_consecutive_still(&a), 3);
            }
            if (blk == 3 || blk == 4 || blk == 5) {
                GL_CHECK_EQ(gl_tilt_avg_consecutive_still(&a), 0);
            }
        }
    }
    GL_CHECK_EQ(nb, 8);
    {
        const int expect[8] = { 1, 1, 1, 0, 0, 0, 1, 1 };
        for (int i = 0; i < 8; i++) {
            GL_CHECK_EQ(verdicts[i], expect[i]);
        }
    }
    GL_CHECK_EQ(gl_tilt_avg_consecutive_still(&a), 2);
    GL_CHECK_EQ(gl_tilt_avg_result(&a, &m), GL_OK);
    GL_CHECK_EQ(m.blocks_still, 5);
    GL_CHECK_EQ(m.blocks_total, 8);
    /* mean of 3 blocks at 0.010 and 2 at 0.020 */
    GL_CHECK_NEAR(m.accel_g.x, 0.014, 0.0003);

    /* nothing still -> GL_ERR_MOTION */
    gl_tilt_avg_reset(&a);
    for (int i = 0; i < 64; i++) {
        gl_imu_raw_t s = sample(0.0, 0.0, 1.0, 0.05, 0.0);
        gl_tilt_avg_add(&a, &s);
    }
    GL_CHECK_EQ(gl_tilt_avg_result(&a, &m), GL_ERR_MOTION);
    GL_CHECK_EQ(m.blocks_total, 2);
    /* no complete block yet -> GL_ERR_MOTION as well */
    gl_tilt_avg_reset(&a);
    GL_CHECK_EQ(gl_tilt_avg_result(&a, &m), GL_ERR_MOTION);
    /* a constant gyro bias (1 dps) is NOT motion: only its noise counts */
    gl_tilt_avg_reset(&a);
    for (int i = 0; i < 64; i++) {
        gl_imu_raw_t s = sample(0.0, 0.0, 1.0, 0.001, 0.01745);
        gl_tilt_avg_add(&a, &s);
    }
    GL_CHECK_EQ(gl_tilt_avg_result(&a, &m), GL_OK);
    GL_CHECK_NEAR(m.gyro_rad_s.z, 0.01745, 0.001);
}

GL_TEST(test_six_face_calibration)
{
    /* true sensor model: measured = S * true + b */
    const gl_mat3_t s = { { { 1.021f, 0.008f, -0.004f },
                            { -0.006f, 0.983f, 0.011f },
                            { 0.003f, -0.009f, 1.012f } } };
    const gl_vec3_t b = { 0.021f, -0.034f, 0.047f };
    const gl_vec3_t faces[6] = { { 1, 0, 0 }, { -1, 0, 0 }, { 0, 1, 0 },
                                 { 0, -1, 0 }, { 0, 0, 1 }, { 0, 0, -1 } };
    gl_vec3_t meas[6];
    gl_cal_tilt_t cal;
    double worst = 0;

    for (int k = 0; k < 6; k++) {
        meas[k] = gl_mat3_mul_vec(&s, faces[k]);
        meas[k].x += b.x;
        meas[k].y += b.y;
        meas[k].z += b.z;
    }
    gl_cal_tilt_defaults(&cal);
    {
        gl_vec3_t off;
        GL_CHECK_EQ(gl_tilt_six_face_solve(meas, &off, &cal.m), GL_OK);
        cal.offset_g[0] = off.x;
        cal.offset_g[1] = off.y;
        cal.offset_g[2] = off.z;
        GL_CHECK_NEAR(off.x, b.x, 1e-6);
        GL_CHECK_NEAR(off.y, b.y, 1e-6);
        GL_CHECK_NEAR(off.z, b.z, 1e-6);
    }
    /* random orientations: the calibrated vector equals the true one */
    rng_state = 99;
    for (int t = 0; t < 500; t++) {
        gl_vec3_t tr = { (float)nrand(), (float)nrand(), (float)nrand() };
        gl_vec3_t ms, c;
        tr = gl_vec3_unit(tr);
        ms = gl_mat3_mul_vec(&s, tr);
        ms.x += b.x;
        ms.y += b.y;
        ms.z += b.z;
        c = gl_tilt_apply_cal(&cal, ms, 25.0f);
        double e = fabs((double)(c.x - tr.x)) + fabs((double)(c.y - tr.y)) +
                   fabs((double)(c.z - tr.z));
        if (e > worst) {
            worst = e;
        }
    }
    printf("    six-face: worst residual over 500 orientations = %.2e g\n", worst);
    GL_CHECK(worst < 5e-6);
    /* implausible data are refused */
    meas[0].x = 3.0f;
    {
        gl_vec3_t off;
        gl_mat3_t m;
        GL_CHECK_EQ(gl_tilt_six_face_solve(meas, &off, &m), GL_ERR_RANGE);
    }
}

GL_TEST(test_temperature_polynomial)
{
    const float t0 = 25.0f;
    const double b0[3] = { 0.010, -0.020, 0.030 };
    const double b1[3] = { 1.5e-4, -0.8e-4, 2.2e-4 }; /* g / K */
    const double b2[3] = { 2.0e-6, 1.0e-6, -3.0e-6 }; /* g / K^2 */
    float temps[9];
    gl_vec3_t offs[9];
    gl_cal_tilt_t cal;
    double worst = 0;

    for (int i = 0; i < 9; i++) {
        double t = 0.0 + 5.0 * i, d = t - 25.0;
        temps[i] = (float)t;
        offs[i].x = (float)(b0[0] + b1[0] * d + b2[0] * d * d);
        offs[i].y = (float)(b0[1] + b1[1] * d + b2[1] * d * d);
        offs[i].z = (float)(b0[2] + b1[2] * d + b2[2] * d * d);
    }
    gl_cal_tilt_defaults(&cal);
    GL_CHECK_EQ(gl_tilt_tempco_fit(temps, offs, 9, t0, &cal), GL_OK);
    for (int a = 0; a < 3; a++) {
        GL_CHECK_NEAR(cal.offset_g[a], b0[a], 2e-6);
        GL_CHECK_NEAR(cal.tempco1_g_per_k[a], b1[a], 2e-7);
        GL_CHECK_NEAR(cal.tempco2_g_per_k2[a], b2[a], 2e-8);
    }
    /* applying the calibration removes the drift from -5 to 50 C */
    for (double t = -5.0; t <= 50.0; t += 2.5) {
        double d = t - 25.0;
        gl_vec3_t raw = { (float)(0.02 + b0[0] + b1[0] * d + b2[0] * d * d),
                          (float)(-0.01 + b0[1] + b1[1] * d + b2[1] * d * d),
                          (float)(0.9997 + b0[2] + b1[2] * d + b2[2] * d * d) };
        gl_vec3_t c = gl_tilt_apply_cal(&cal, raw, (float)t);
        double e = fabs((double)c.x - 0.02) + fabs((double)c.y + 0.01);
        if (e > worst) {
            worst = e;
        }
    }
    printf("    temperature polynomial: worst x+y residual -5..50 C = %.2e g "
           "(uncompensated drift %.1e g)\n", worst, fabs(b1[0]) * 30.0);
    GL_CHECK(worst < 2e-5);
    /* degenerate inputs */
    GL_CHECK_EQ(gl_tilt_tempco_fit(temps, offs, 2, t0, &cal), GL_ERR_PARAM);
    temps[1] = temps[0];
    temps[2] = temps[0];
    GL_CHECK_EQ(gl_tilt_tempco_fit(temps, offs, 3, t0, &cal), GL_ERR_RANGE);
}

GL_TEST(test_slope_conversion)
{
    gl_vec2_t s;
    /* A plane z = sx x + sy y: the marker's axes lie in the plane, so world
     * up has components (sx, sy, 1) / norm along (x_m, y_m, z_m) to first
     * order.  Build the exact up vector from exact in-plane axes. */
    for (double sx = -0.05; sx <= 0.05; sx += 0.0125) {
        for (double sy = -0.05; sy <= 0.05; sy += 0.0125) {
            double xm[3] = { 1, 0, sx }, ym[3], zm[3], n;
            /* z_m = plane normal */
            zm[0] = -sx;
            zm[1] = -sy;
            zm[2] = 1;
            n = sqrt(zm[0] * zm[0] + zm[1] * zm[1] + zm[2] * zm[2]);
            zm[0] /= n;
            zm[1] /= n;
            zm[2] /= n;
            n = sqrt(1 + sx * sx);
            xm[0] /= n;
            xm[2] /= n;
            /* y_m = z_m x x_m */
            ym[0] = zm[1] * xm[2] - zm[2] * xm[1];
            ym[1] = zm[2] * xm[0] - zm[0] * xm[2];
            ym[2] = zm[0] * xm[1] - zm[1] * xm[0];
            gl_vec3_t up = { (float)xm[2], (float)ym[2], (float)zm[2] };
            GL_CHECK_EQ(gl_tilt_slope(up, &s), GL_OK);
            GL_CHECK_NEAR(s.x, sx, 2e-4);
            GL_CHECK_NEAR(s.y, sy, 2e-4);
            GL_CHECK_NEAR(gl_tilt_slope_percent(s), 100.0 * sqrt(sx * sx + sy * sy), 0.02);
        }
    }
    /* fall line: the downhill direction, CCW from forward */
    s.x = 0.02f;
    s.y = 0.0f; /* uphill to the right -> ball falls to the left */
    GL_CHECK_NEAR(gl_tilt_fall_line_rad(s), 1.5707963, 1e-6);
    s.x = -0.02f; /* uphill to the left -> falls right */
    GL_CHECK_NEAR(gl_tilt_fall_line_rad(s), -1.5707963, 1e-6);
    s.x = 0.0f;
    s.y = -0.02f; /* downhill straight ahead */
    GL_CHECK_NEAR(gl_tilt_fall_line_rad(s), 0.0, 1e-6);
    s.y = 0.02f; /* uphill ahead -> falls back toward the golfer */
    GL_CHECK_NEAR(fabs((double)gl_tilt_fall_line_rad(s)), 3.14159265, 1e-6);
    s.y = 0.0f;
    GL_CHECK_NEAR(gl_tilt_fall_line_rad(s), 0.0, 1e-9);
    GL_CHECK_NEAR(gl_tilt_slope_percent(s), 0.0, 1e-9);

    /* along / cross decomposition */
    s.x = 0.03f;
    s.y = 0.01f;
    {
        gl_vec2_t a0 = gl_tilt_slope_along(s, 0.0f);
        gl_vec2_t a90 = gl_tilt_slope_along(s, 1.5707963f); /* target to the left */
        gl_vec2_t d = gl_tilt_slope_to_device(s);
        GL_CHECK_NEAR(a0.x, 0.01, 1e-7);   /* uphill toward the target */
        GL_CHECK_NEAR(a0.y, -0.03, 1e-7);  /* left of the line is downhill */
        GL_CHECK_NEAR(a90.x, -0.03, 1e-7);
        GL_CHECK_NEAR(a90.y, -0.01, 1e-7);
        GL_CHECK_NEAR(d.x, a0.x, 1e-9);
        GL_CHECK_NEAR(d.y, a0.y, 1e-9);
    }
    /* not on a green: refused */
    {
        gl_vec3_t side = { 1.0f, 0.0f, 0.05f }, heavy = { 0.0f, 0.0f, 1.3f },
                  steep = { 0.6f, 0.0f, 0.8f };
        GL_CHECK_EQ(gl_tilt_slope(side, &s), GL_ERR_RANGE);
        GL_CHECK_EQ(gl_tilt_slope(heavy, &s), GL_ERR_RANGE);
        GL_CHECK_EQ(gl_tilt_slope(steep, &s), GL_ERR_RANGE);
    }
}

GL_TEST(test_rotation_integrator)
{
    gl_rot_int_t r;
    const gl_vec3_t zero = { 0, 0, 0 };
    const gl_vec3_t up = { 0, 0, 1 };

    /* pure yaw of 172 degrees CCW at 2 rad/s, 240 Hz */
    {
        const double target = 172.0 * 3.141592653589793 / 180.0;
        const double dt = 1.0 / 240.0;
        const gl_vec3_t w = { 0.0f, 0.0f, 2.0f };
        int n = (int)(target / (2.0 * dt));
        gl_rot_int_start(&r, zero);
        for (int i = 0; i < n; i++) {
            gl_rot_int_add(&r, w, (float)dt);
        }
        GL_CHECK_NEAR(gl_rot_int_yaw(&r, up), n * 2.0 * dt, 2e-4);
        GL_CHECK_NEAR(gl_rot_int_angle(&r), n * 2.0 * dt, 2e-4);
    }
    /* clockwise turn gives a negative yaw; gyro bias is removed */
    {
        const gl_vec3_t bias = { 0.01f, -0.02f, 0.015f };
        const gl_vec3_t w = { 0.01f, -0.02f, 0.015f - 3.0f };
        gl_rot_int_start(&r, bias);
        for (int i = 0; i < 240; i++) {
            gl_rot_int_add(&r, w, 1.0f / 240.0f);
        }
        GL_CHECK_NEAR(gl_rot_int_yaw(&r, up), -3.0, 5e-4);
    }
    /* lift, turn, re-seat: tilt 25 deg about x, yaw 180 deg about the
     * WORLD vertical, tilt back.  Only the heading change must remain. */
    {
        const float dt = 1.0f / 480.0f;
        const float tilt = 25.0f * GL_DEG2RAD_F;
        gl_rot_int_start(&r, zero);
        for (int i = 0; i < 480; i++) { /* tilt up about body x */
            gl_vec3_t w = { tilt, 0.0f, 0.0f };
            gl_rot_int_add(&r, w, dt);
        }
        for (int i = 0; i < 480; i++) { /* world vertical in the tilted body frame */
            gl_vec3_t w = { 0.0f, GL_PI_F * sinf(tilt), GL_PI_F * cosf(tilt) };
            gl_rot_int_add(&r, w, dt);
        }
        for (int i = 0; i < 480; i++) { /* tilt back */
            gl_vec3_t w = { -tilt, 0.0f, 0.0f };
            gl_rot_int_add(&r, w, dt);
        }
        GL_CHECK_NEAR(fabs((double)gl_rot_int_yaw(&r, up)), 3.14159265, 2e-3);
    }
    /* on a 3 % slope the heading is measured about the true vertical */
    {
        gl_vec3_t up_s = { 0.03f, 0.0f, 1.0f };
        gl_vec3_t u = gl_vec3_unit(up_s);
        gl_rot_int_start(&r, zero);
        for (int i = 0; i < 1000; i++) {
            gl_vec3_t w = { 1.5f * u.x, 1.5f * u.y, 1.5f * u.z };
            gl_rot_int_add(&r, w, 0.001f);
        }
        GL_CHECK_NEAR(gl_rot_int_yaw(&r, up_s), 1.5, 5e-4);
    }
}

GL_TEST(test_flip_solve)
{
    gl_vec2_t bias, surf;
    rng_state = 5;
    for (int t = 0; t < 500; t++) {
        const double cx = 0.02 * nrand(), cy = 0.02 * nrand();
        const double bx = 0.004 * nrand(), by = 0.004 * nrand();
        const double yaw = (150.0 + 60.0 * urand()) * 3.141592653589793 / 180.0 *
                           ((t & 1) ? 1.0 : -1.0);
        /* m2 = R(-yaw) c + b */
        const gl_vec2_t m1 = { (float)(cx + bx), (float)(cy + by) };
        const gl_vec2_t m2 = { (float)(cos(yaw) * cx + sin(yaw) * cy + bx),
                               (float)(-sin(yaw) * cx + cos(yaw) * cy + by) };
        GL_CHECK_EQ(gl_tilt_flip_solve(m1, m2, (float)yaw, &bias, &surf), GL_OK);
        GL_CHECK_NEAR(bias.x, bx, 2e-6);
        GL_CHECK_NEAR(bias.y, by, 2e-6);
        GL_CHECK_NEAR(surf.x, cx, 2e-6);
        GL_CHECK_NEAR(surf.y, cy, 2e-6);
    }
    /* exactly 180 degrees: mean and half-difference */
    {
        const gl_vec2_t m1 = { 0.012f, -0.003f }, m2 = { -0.006f, 0.005f };
        GL_CHECK_EQ(gl_tilt_flip_solve(m1, m2, GL_PI_F, &bias, &surf), GL_OK);
        GL_CHECK_NEAR(bias.x, 0.003, 1e-6);
        GL_CHECK_NEAR(bias.y, 0.001, 1e-6);
        GL_CHECK_NEAR(surf.x, 0.009, 1e-6);
        GL_CHECK_NEAR(surf.y, -0.004, 1e-6);
        /* not a flip */
        GL_CHECK_EQ(gl_tilt_flip_solve(m1, m2, 1.5707963f, &bias, &surf), GL_ERR_RANGE);
        GL_CHECK_EQ(gl_tilt_flip_solve(m1, m2, 0.0f, &bias, &surf), GL_ERR_RANGE);
        GL_CHECK_EQ(gl_tilt_flip_solve(m1, m2, 149.0f * GL_DEG2RAD_F, &bias, &surf),
                    GL_ERR_RANGE);
        GL_CHECK_EQ(gl_tilt_flip_solve(m1, m2, -151.0f * GL_DEG2RAD_F, &bias, &surf), GL_OK);
    }
    /* What ignoring the measured yaw would cost: a 172-degree flip treated
     * as 180 on a cradle sloped 1 %. */
    {
        const double yaw = 172.0 * 3.141592653589793 / 180.0, cx = 0.01, cy = 0.0;
        const gl_vec2_t m1 = { (float)cx, (float)cy };
        const gl_vec2_t m2 = { (float)(cos(yaw) * cx), (float)(-sin(yaw) * cx) };
        gl_vec2_t b180, bmeas;
        gl_tilt_flip_solve(m1, m2, GL_PI_F, &b180, NULL);
        gl_tilt_flip_solve(m1, m2, (float)yaw, &bmeas, NULL);
        printf("    flip 172 deg on a 1 %% cradle: bias error %.2f mrad if yaw assumed 180, "
               "%.4f mrad with the gyro yaw\n",
               1000.0 * sqrt((double)(b180.x * b180.x + b180.y * b180.y)),
               1000.0 * sqrt((double)(bmeas.x * bmeas.x + bmeas.y * bmeas.y)));
        GL_CHECK(sqrtf(b180.x * b180.x + b180.y * b180.y) > 0.0005f);
        GL_CHECK(sqrtf(bmeas.x * bmeas.x + bmeas.y * bmeas.y) < 0.00001f);
    }
}

/* End to end: biased accelerometer, flip calibration in a sloped cradle
 * with a gyro-measured 174-degree turn, then a read on a green. */
GL_TEST(test_flip_calibration_end_to_end)
{
    gl_tilt_cfg_t cfg = cfg_default();
    gl_tilt_avg_t a;
    gl_tilt_mean_t m1, m2, m3;
    gl_cal_tilt_t cal;
    gl_rot_int_t rot;
    gl_vec2_t s1, s2, s3, bias, cradle;
    const double acc_bias_x = 0.0031, acc_bias_y = -0.0022; /* g: 3 mrad of tilt error */
    const double cradle_x = 0.006, cradle_y = -0.011;       /* cradle is not level */
    const double yaw = 174.0 * 3.141592653589793 / 180.0;
    const double gyro_bias_z = 0.012;
    float yaw_meas;

    rng_state = 31337;
    gl_cal_tilt_defaults(&cal);
    gl_tilt_avg_init(&a, &cfg);

    /* read 1 */
    for (int i = 0; i < 256; i++) {
        gl_imu_raw_t s = sample(cradle_x + acc_bias_x, cradle_y + acc_bias_y, 1.0, 0.0008,
                                gyro_bias_z);
        gl_tilt_avg_add(&a, &s);
    }
    GL_CHECK_EQ(gl_tilt_avg_result(&a, &m1), GL_OK);
    GL_CHECK_EQ(gl_tilt_slope(gl_tilt_apply_cal(&cal, m1.accel_g, 25.0f), &s1), GL_OK);

    /* the turn, integrated from the gyro with the bias from read 1 */
    gl_rot_int_start(&rot, m1.gyro_rad_s);
    {
        const int n = 300;
        const double rate = yaw / (n / 240.0);
        for (int i = 0; i < n; i++) {
            gl_vec3_t w = { (float)(0.002 * nrand()), (float)(0.002 * nrand()),
                            (float)(rate + gyro_bias_z + 0.002 * nrand()) };
            gl_rot_int_add(&rot, w, 1.0f / 240.0f);
        }
    }
    yaw_meas = gl_rot_int_yaw(&rot, m1.accel_g);
    GL_CHECK_NEAR(yaw_meas, yaw, 0.003);

    /* read 2: the cradle slope seen from the turned marker */
    {
        const double c2x = cos(yaw) * cradle_x + sin(yaw) * cradle_y;
        const double c2y = -sin(yaw) * cradle_x + cos(yaw) * cradle_y;
        gl_tilt_avg_reset(&a);
        for (int i = 0; i < 256; i++) {
            gl_imu_raw_t s = sample(c2x + acc_bias_x, c2y + acc_bias_y, 1.0, 0.0008, gyro_bias_z);
            gl_tilt_avg_add(&a, &s);
        }
    }
    GL_CHECK_EQ(gl_tilt_avg_result(&a, &m2), GL_OK);
    GL_CHECK_EQ(gl_tilt_slope(gl_tilt_apply_cal(&cal, m2.accel_g, 25.0f), &s2), GL_OK);

    GL_CHECK_EQ(gl_tilt_flip_solve(s1, s2, yaw_meas, &bias, &cradle), GL_OK);
    printf("    flip cal: bias found (%.3f, %.3f) mrad, true (%.3f, %.3f); cradle slope "
           "(%.3f, %.3f) mrad, true (%.3f, %.3f)\n", 1e3 * (double)bias.x, 1e3 * (double)bias.y,
           1e3 * acc_bias_x, 1e3 * acc_bias_y, 1e3 * (double)cradle.x, 1e3 * (double)cradle.y,
           1e3 * cradle_x, 1e3 * cradle_y);
    GL_CHECK_NEAR(bias.x, acc_bias_x, 0.00025);
    GL_CHECK_NEAR(bias.y, acc_bias_y, 0.00025);
    GL_CHECK_NEAR(cradle.x, cradle_x, 0.00025);
    GL_CHECK_NEAR(cradle.y, cradle_y, 0.00025);
    cal.flip_bias_x = bias.x;
    cal.flip_bias_y = bias.y;
    cal.flags |= GL_CAL_TILT_FLAG_FLIP;

    /* a read on a 2 % / -1 % green is now correct to a fraction of a mrad */
    gl_tilt_avg_reset(&a);
    for (int i = 0; i < 256; i++) {
        gl_imu_raw_t s = sample(0.02 + acc_bias_x, -0.01 + acc_bias_y, 1.0, 0.0008, gyro_bias_z);
        gl_tilt_avg_add(&a, &s);
    }
    GL_CHECK_EQ(gl_tilt_avg_result(&a, &m3), GL_OK);
    GL_CHECK_EQ(gl_tilt_slope(gl_tilt_apply_cal(&cal, m3.accel_g, 25.0f), &s3), GL_OK);
    s3.x -= cal.flip_bias_x;
    s3.y -= cal.flip_bias_y;
    GL_CHECK_NEAR(s3.x, 0.02, 0.0004);
    GL_CHECK_NEAR(s3.y, -0.01, 0.0004);
}

GL_TEST(test_precision_read_combine)
{
    gl_cal_tilt_t cal;
    gl_precision_t p;
    /* true slope (1.5 %, -0.8 %), device bias 2 mrad, two different seatings */
    const double sx = 0.015, sy = -0.008, bx = 0.002, by = -0.001;
    const double e1x = 0.0030, e1y = -0.0020, e2x = -0.0010, e2y = 0.0025; /* world frame */
    const gl_vec2_t m1 = { (float)(sx + e1x + bx), (float)(sy + e1y + by) };
    /* after a 180-degree spin the world vector appears negated */
    const gl_vec2_t m2 = { (float)(-(sx + e2x) + bx), (float)(-(sy + e2y) + by) };

    gl_cal_tilt_defaults(&cal);
    cal.flip_bias_x = (float)bx;
    cal.flip_bias_y = (float)by;
    cal.flags = GL_CAL_TILT_FLAG_FLIP;
    GL_CHECK_EQ(gl_tilt_precision_combine(m1, m2, GL_PI_F, &cal, &p), GL_OK);
    /* the result is the true slope plus the MEAN of the two seating errors */
    GL_CHECK_NEAR(p.slope.x, sx + 0.5 * (e1x + e2x), 1e-6);
    GL_CHECK_NEAR(p.slope.y, sy + 0.5 * (e1y + e2y), 1e-6);
    /* the device bias dropped out entirely: same answer with a wrong cal */
    {
        gl_precision_t p2;
        cal.flip_bias_x = 0.05f;
        GL_CHECK_EQ(gl_tilt_precision_combine(m1, m2, GL_PI_F, &cal, &p2), GL_OK);
        GL_CHECK_NEAR(p2.slope.x, p.slope.x, 1e-9);
        GL_CHECK(p2.bias_mismatch > 0.04f);
        cal.flip_bias_x = (float)bx;
    }
    /* implied bias = true bias + half the DIFFERENCE of the seatings */
    GL_CHECK_NEAR(p.implied_bias.x, bx + 0.5 * (e1x - e2x), 1e-6);
    GL_CHECK_NEAR(p.bias_mismatch,
                  0.5 * sqrt((e1x - e2x) * (e1x - e2x) + (e1y - e2y) * (e1y - e2y)), 1e-6);
    /* a spin that was not a half turn is refused */
    GL_CHECK_EQ(gl_tilt_precision_combine(m1, m2, 2.0f, &cal, &p), GL_ERR_RANGE);
    /* single read for comparison: error = one full seating error */
    printf("    precision read: single-read error %.2f mrad, combined %.2f mrad\n",
           1e3 * sqrt(e1x * e1x + e1y * e1y),
           1e3 * 0.5 * sqrt((e1x + e2x) * (e1x + e2x) + (e1y + e2y) * (e1y + e2y)));
}

GL_TEST(test_survey_store)
{
    gl_survey_t s;
    gl_survey_drop_t d;
    memset(&d, 0, sizeof(d));
    gl_survey_reset(&s);
    GL_CHECK_EQ(gl_survey_farthest(&s), -1);
    d.flags = 0;
    d.range_m = 5.0f;
    GL_CHECK_EQ(gl_survey_add(&s, &d), GL_ERR_PARAM); /* no flagstick fix */
    d.flags = GL_DROP_FLAG_STICK;
    d.range_m = 0.0f;
    GL_CHECK_EQ(gl_survey_add(&s, &d), GL_ERR_PARAM);
    {
        const float ranges[4] = { 1.0f, 9.2f, 4.5f, 6.0f };
        for (int i = 0; i < 4; i++) {
            d.range_m = ranges[i];
            d.slope.x = 0.01f * (float)i;
            GL_CHECK_EQ(gl_survey_add(&s, &d), GL_OK);
        }
    }
    GL_CHECK_EQ(s.count, 4);
    GL_CHECK_EQ(gl_survey_add(&s, &d), GL_ERR_FULL);
    GL_CHECK_EQ(gl_survey_farthest(&s), 1);
    GL_CHECK_NEAR(s.drop[2].slope.x, 0.02, 1e-9);
    gl_survey_reset(&s);
    GL_CHECK_EQ(s.count, 0);
}

int main(void)
{
    GL_RUN(test_block_average_precision);
    GL_RUN(test_stillness_gating);
    GL_RUN(test_six_face_calibration);
    GL_RUN(test_temperature_polynomial);
    GL_RUN(test_slope_conversion);
    GL_RUN(test_rotation_integrator);
    GL_RUN(test_flip_solve);
    GL_RUN(test_flip_calibration_end_to_end);
    GL_RUN(test_precision_read_combine);
    GL_RUN(test_survey_store);
    return gl_test_summary();
}
