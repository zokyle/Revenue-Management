/*
 * test_range.c - stereo / monocular / manual range fusion, per-course
 * stick-height learning, camera-to-ball geometry.
 */
#include <stdlib.h>

#include "gl_config.h"
#include "gl_provisional.h"
#include "gl_range.h"
#include "gl_test.h"

static uint32_t rng_state = 17;
static double urand(void)
{
    rng_state = rng_state * 1664525u + 1013904223u;
    return ((double)(rng_state >> 8) + 0.5) / 16777216.0;
}
static double nrand(void)
{
    return sqrt(-2.0 * log(urand())) * cos(6.283185307179586 * urand());
}

static const double F = 657.0, B = 0.0200; /* rev C baseline */

/* Measurement of a stick of true visible height `h_true` at range z. */
static gl_range_input_t measure2(double z, double h_true, double disp_noise, double base_noise,
                                 double top_noise, bool top_in_frame)
{
    gl_range_input_t in;
    memset(&in, 0, sizeof(in));
    in.f_px = (float)F;
    in.baseline_m = (float)B;
    in.have_stereo = true;
    in.disparity_px = (float)(F * B / z + disp_noise);
    in.disparity_sigma_px = 0.08f;
    in.have_height = top_in_frame;
    in.base_visible = true;
    in.tan_base = (float)(-0.0056 / z + base_noise);
    in.tan_top = (float)((h_true - 0.0056) / z + top_noise);
    in.elev_sigma_rad = 0.15f / 657.0f;
    return in;
}

/* Noise-free elevations (or none needed). */
static gl_range_input_t measure(double z, double h_true, double disp_noise, double unused,
                                bool top_in_frame)
{
    (void)unused;
    return measure2(z, h_true, disp_noise, 0.0, 0.0, top_in_frame);
}

GL_TEST(test_prior)
{
    gl_stick_height_t h;
    uint8_t blob[GL_STICK_HEIGHT_BLOB_LEN];
    gl_stick_height_t h2;
    gl_stick_height_reset(&h);
    GL_CHECK_NEAR(h.height_m, 2.13 - 0.17, 1e-6);
    GL_CHECK_NEAR(h.sigma_m, 0.07 * 1.96, 1e-6);
    GL_CHECK_EQ(h.updates, 0);
    gl_stick_height_encode(&h, blob);
    GL_CHECK_EQ(gl_stick_height_decode(blob, sizeof(blob), &h2), GL_OK);
    GL_CHECK(h2.height_m == h.height_m && h2.sigma_m == h.sigma_m);
    GL_CHECK_EQ(gl_stick_height_decode(blob, sizeof(blob) - 1, &h2), GL_ERR_PARAM);
    blob[0] = 9;
    GL_CHECK_EQ(gl_stick_height_decode(blob, sizeof(blob), &h2), GL_ERR_UNSUPPORTED);
    blob[0] = 1;
    gl_put_f32(&blob[1], 9.0f);
    GL_CHECK_EQ(gl_stick_height_decode(blob, sizeof(blob), &h2), GL_ERR_RANGE);
}

GL_TEST(test_stereo_only)
{
    gl_range_result_t r;
    gl_range_input_t in = measure(3.0, 1.96, 0.0, 0.0, false);
    GL_CHECK_EQ(gl_range_fuse(&in, NULL, &r), GL_OK);
    GL_CHECK_EQ(r.sources, GL_RANGE_SRC_STEREO);
    GL_CHECK_NEAR(r.range_m, 3.0, 1e-4);
    /* sigma = Z^2 sigma_d / (f B): 9 * 0.08 / 13.14 = 0.0548 m (1.8 %) */
    GL_CHECK_NEAR(r.sigma_m, 9.0 * 0.08 / (F * B), 1e-4);
    GL_CHECK(r.consistent);
    GL_CHECK_NEAR(r.chi2, 0.0, 1e-9);
    /* 10 m: 6 % */
    in = measure(10.0, 1.96, 0.0, 0.0, false);
    GL_CHECK_EQ(gl_range_fuse(&in, NULL, &r), GL_OK);
    GL_CHECK_NEAR(r.sigma_m / r.range_m, 10.0 * 0.08 / (F * B), 1e-3);
    /* zero or negative disparity alone gives no range */
    in.disparity_px = 0.0f;
    GL_CHECK_EQ(gl_range_fuse(&in, NULL, &r), GL_ERR_NOT_FOUND);
    in.disparity_px = -0.05f;
    GL_CHECK_EQ(gl_range_fuse(&in, NULL, &r), GL_ERR_NOT_FOUND);
    /* nothing at all */
    memset(&in, 0, sizeof(in));
    GL_CHECK_EQ(gl_range_fuse(&in, NULL, &r), GL_ERR_NOT_FOUND);
    GL_CHECK_EQ(gl_range_fuse(NULL, NULL, &r), GL_ERR_PARAM);
}

GL_TEST(test_fusion_weights)
{
    gl_stick_height_t h;
    gl_range_result_t r;
    gl_range_input_t in;

    /* Unlearned prior (7 %): at 3 m stereo (1.8 %) dominates */
    gl_stick_height_reset(&h);
    in = measure(3.0, 1.96, 0.0, 0.0, true);
    GL_CHECK_EQ(gl_range_fuse(&in, &h, &r), GL_OK);
    GL_CHECK_EQ(r.sources, GL_RANGE_SRC_STEREO | GL_RANGE_SRC_MONO);
    GL_CHECK_NEAR(r.range_m, 3.0, 1e-3);
    GL_CHECK(r.sigma_m < r.stereo_sigma_m && r.sigma_m > 0.9f * r.stereo_sigma_m);
    GL_CHECK_NEAR(r.mono_m, 3.0, 1e-3);
    GL_CHECK_NEAR(r.mono_sigma_m / r.mono_m, 0.07, 2e-3);
    /* inverse-variance identity in inverse range */
    {
        double ss = 0.08 / (F * B), sm = (double)r.mono_sigma_m / 9.0;
        double expect = 9.0 / sqrt(1.0 / (ss * ss) + 1.0 / (sm * sm));
        GL_CHECK_NEAR(r.sigma_m, expect, 2e-4);
    }
    /* Learned stick (1 %): at 10 m mono (about 1 %) dominates over stereo (6 %) */
    h.sigma_m = 0.0196f;
    in = measure(10.0, 1.96, 0.25, 0.0, true); /* stereo off by +0.25 px = 3 sigma */
    GL_CHECK_EQ(gl_range_fuse(&in, &h, &r), GL_OK);
    GL_CHECK_NEAR(r.range_m, 10.0, 0.08);
    GL_CHECK(fabsf(r.stereo_m - 10.0f) > 1.2f);
    GL_CHECK(r.sigma_m < 0.15f);
    printf("    10 m, learned stick: stereo alone %.2f +- %.2f m, mono %.2f +- %.2f m, "
           "fused %.2f +- %.2f m\n", (double)r.stereo_m, (double)r.stereo_sigma_m,
           (double)r.mono_m, (double)r.mono_sigma_m, (double)r.range_m, (double)r.sigma_m);
    /* base hidden behind a crown: the angular height is not used */
    in.base_visible = false;
    GL_CHECK_EQ(gl_range_fuse(&in, &h, &r), GL_OK);
    GL_CHECK_EQ(r.sources, GL_RANGE_SRC_STEREO);
    /* top out of frame: stereo only */
    in = measure(2.5, 1.96, 0.0, 0.0, false);
    GL_CHECK_EQ(gl_range_fuse(&in, &h, &r), GL_OK);
    GL_CHECK_EQ(r.sources, GL_RANGE_SRC_STEREO);
    /* mono only (stereo lost: one window dirty) */
    in = measure(8.0, 1.96, 0.0, 0.0, true);
    in.have_stereo = false;
    GL_CHECK_EQ(gl_range_fuse(&in, &h, &r), GL_OK);
    GL_CHECK_EQ(r.sources, GL_RANGE_SRC_MONO);
    GL_CHECK_NEAR(r.range_m, 8.0, 1e-3);
}

GL_TEST(test_inconsistency_flag)
{
    gl_stick_height_t h;
    gl_range_result_t r, r0;
    gl_range_input_t in;
    gl_stick_height_reset(&h);
    h.sigma_m = 0.02f;
    in = measure(5.0, 1.96, 0.0, 0.0, true);
    GL_CHECK_EQ(gl_range_fuse(&in, &h, &r0), GL_OK);
    GL_CHECK(r0.consistent);
    /* stereo calibration has drifted by 0.6 px (7.5 sigma) */
    in = measure(5.0, 1.96, 0.6, 0.0, true);
    GL_CHECK_EQ(gl_range_fuse(&in, &h, &r), GL_OK);
    GL_CHECK(!r.consistent);
    GL_CHECK(r.chi2 > 9.0f);
    GL_CHECK(r.sigma_m > 1.5f * r0.sigma_m); /* uncertainty inflated, not hidden */
}

GL_TEST(test_manual_override)
{
    gl_stick_height_t h;
    gl_range_result_t r;
    gl_range_input_t in = measure(5.0, 1.96, 0.0, 0.0, true);
    gl_stick_height_reset(&h);
    in.manual_m = 7.5f;
    GL_CHECK_EQ(gl_range_fuse(&in, &h, &r), GL_OK);
    GL_CHECK_EQ(r.sources, GL_RANGE_SRC_MANUAL);
    GL_CHECK_NEAR(r.range_m, 7.5, 1e-6);
    GL_CHECK_NEAR(r.sigma_m, 0.75, 1e-6);
    GL_CHECK_NEAR(r.stereo_m, 5.0, 1e-3); /* still reported for comparison */
    /* manual with no optics at all: the flag-out fallback */
    memset(&in, 0, sizeof(in));
    in.manual_m = 4.0f;
    GL_CHECK_EQ(gl_range_fuse(&in, &h, &r), GL_OK);
    GL_CHECK_NEAR(r.range_m, 4.0, 1e-6);
    /* a manual entry never teaches the stick height */
    in = measure(5.0, 2.3, 0.0, 0.0, true);
    in.manual_m = 5.0f;
    GL_CHECK(!gl_stick_height_learn(&h, &in));
    GL_CHECK_EQ(h.updates, 0);
}

GL_TEST(test_stick_height_learning)
{
    gl_stick_height_t h;
    const double h_true = 2.05; /* this course's sticks are 9 cm taller than the prior */
    gl_range_input_t in;
    double err_before, err_after;

    rng_state = 77;
    gl_stick_height_reset(&h);
    /* outside the 4..7 m window nothing is learned */
    in = measure(3.0, h_true, 0.0, 0.0, true);
    GL_CHECK(!gl_stick_height_learn(&h, &in));
    in = measure(8.0, h_true, 0.0, 0.0, true);
    GL_CHECK(!gl_stick_height_learn(&h, &in));
    /* nor without the top, nor with a hidden base */
    in = measure(5.0, h_true, 0.0, 0.0, false);
    GL_CHECK(!gl_stick_height_learn(&h, &in));
    in = measure(5.0, h_true, 0.0, 0.0, true);
    in.base_visible = false;
    GL_CHECK(!gl_stick_height_learn(&h, &in));
    GL_CHECK_EQ(h.updates, 0);
    GL_CHECK_NEAR(h.height_m, 1.96, 1e-6);

    /* 18 holes, one qualifying putt each, realistic noise */
    printf("    learning a %.2f m stick from the %.2f m prior:\n", h_true, (double)h.height_m);
    for (int hole = 1; hole <= 18; hole++) {
        double z = 4.6 + 1.8 * urand(); /* measured range stays inside the 4..7 m window */
        in = measure2(z, h_true, 0.08 * nrand(), 0.15 / 657.0 * nrand(), 0.15 / 657.0 * nrand(),
                      true);
        (void)gl_stick_height_learn(&h, &in); /* a rare 3-sigma draw may be gated out */
        if (hole == 1 || hole == 3 || hole == 9 || hole == 18) {
            printf("      after %2d holes: %.3f +- %.3f m\n", hole, (double)h.height_m,
                   (double)h.sigma_m);
        }
    }
    GL_CHECK_EQ(h.updates + h.rejected, 18);
    GL_CHECK(h.updates >= 16);
    GL_CHECK_NEAR(h.height_m, h_true, 0.04);
    GL_CHECK(h.sigma_m < 0.03f);
    GL_CHECK(h.sigma_m >= 0.01f * h.height_m * 0.999f); /* floor */

    /* long-putt ranging error with the default prior vs the learned height */
    {
        gl_stick_height_t prior;
        gl_range_result_t r;
        gl_stick_height_reset(&prior);
        in = measure(12.0, h_true, 0.0, 0.0, true);
        in.have_stereo = false;
        gl_range_fuse(&in, &prior, &r);
        err_before = fabs((double)r.range_m - 12.0);
        gl_range_fuse(&in, &h, &r);
        err_after = fabs((double)r.range_m - 12.0);
        printf("    12 m by angular height: error %.2f m with the prior, %.2f m once learned\n",
               err_before, err_after);
        GL_CHECK(err_before > 0.4);
        GL_CHECK(err_after < 0.25);
    }

    /* a wildly different reading (someone's alignment rod, a mis-detected
     * top) is gated out and counted */
    {
        float before = h.height_m;
        uint16_t rejected_before = h.rejected;
        in = measure(5.0, 1.2, 0.0, 0.0, true);
        GL_CHECK(!gl_stick_height_learn(&h, &in));
        GL_CHECK_EQ(h.rejected, rejected_before + 1);
        GL_CHECK_NEAR(h.height_m, before, 1e-9);
    }
    /* new course */
    gl_stick_height_reset(&h);
    GL_CHECK_NEAR(h.height_m, 1.96, 1e-6);
    GL_CHECK_EQ(h.updates, 0);
}

GL_TEST(test_fusion_monte_carlo)
{
    /* The reported sigma must be honest: the normalised error of the fused
     * range should have unit variance (within sampling error). */
    gl_stick_height_t h;
    double sum2 = 0, sum = 0;
    int n = 0;
    rng_state = 4242;
    gl_stick_height_reset(&h);
    h.height_m = 2.0f;
    h.sigma_m = 0.04f;
    for (int t = 0; t < 4000; t++) {
        double z = 2.0 + 10.0 * urand();
        double h_true = 2.0 + 0.04 * nrand();
        gl_range_result_t r;
        gl_range_input_t in = measure2(z, h_true, 0.08 * nrand(), 0.15 / 657.0 * nrand(),
                                       0.15 / 657.0 * nrand(), z > 4.6);
        if (gl_range_fuse(&in, &h, &r) != GL_OK) {
            continue;
        }
        /* compare in inverse range, where the error is Gaussian */
        double e = (1.0 / (double)r.range_m - 1.0 / z) /
                   ((double)r.sigma_m / ((double)r.range_m * (double)r.range_m));
        sum += e;
        sum2 += e * e;
        n++;
    }
    printf("    fused range, 4000 trials 2-12 m: normalised error mean %.3f, rms %.3f "
           "(ideal 0, 1)\n", sum / n, sqrt(sum2 / n));
    GL_CHECK(n > 3900);
    GL_CHECK_NEAR(sum / n, 0.0, 0.08);
    GL_CHECK_NEAR(sqrt(sum2 / n), 1.0, 0.1);
}

GL_TEST(test_ball_geometry)
{
    const double cam_y = (double)GL_CFG_CAM_LEFT_Y_MM / 1000.0;
    const double ball_y = (double)GL_CFG_BALL_CENTRE_Y_MM / 1000.0;
    /* straight ahead: the ball is (ball_y - cam_y) closer to the hole */
    gl_ball_target_t t = gl_range_from_ball(3.0f, 0.0f);
    GL_CHECK_NEAR(t.distance_m, 3.0 - (ball_y - cam_y), 1e-6);
    GL_CHECK_NEAR(t.bearing_rad, 0.0, 1e-7);
    GL_CHECK_NEAR(ball_y, 0.044335, 1e-6);
    /* stick 10 degrees to the left at 2 m: seen from the ball the bearing is
     * slightly larger (parallax of 28.7 mm) */
    {
        const double b = 10.0 * 3.14159265358979 / 180.0, z = 2.0;
        const double sx = -z * sin(b), sy = cam_y + z * cos(b);
        t = gl_range_from_ball((float)z, (float)b);
        GL_CHECK_NEAR(t.distance_m, sqrt(sx * sx + (sy - ball_y) * (sy - ball_y)), 1e-6);
        GL_CHECK_NEAR(t.bearing_rad, atan2(-sx, sy - ball_y), 1e-6);
        GL_CHECK(t.bearing_rad > (float)b);
        printf("    bearing 10.000 deg at 2 m from the cameras is %.3f deg from the ball\n",
               (double)t.bearing_rad * 57.29578);
    }
    /* right is negative */
    t = gl_range_from_ball(5.0f, -0.1f);
    GL_CHECK(t.bearing_rad < -0.1f);
    /* a bearing measured by the LEFT camera (10.0 mm off the axis): a stick
     * dead ahead of the marker centre at 3 m is seen 3.35 mrad to the right */
    {
        const double cam_x = (double)GL_CFG_CAM_LEFT_X_MM / 1000.0;
        const double b_left = atan2(-(0.0 - cam_x), 3.0 - cam_y); /* negative: to the right */
        const double r_left = sqrt(cam_x * cam_x + (3.0 - cam_y) * (3.0 - cam_y));
        GL_CHECK_NEAR(b_left, -0.00335, 0.00002);
        t = gl_range_from_ball_at((float)r_left, (float)b_left, (float)cam_x, (float)cam_y);
        GL_CHECK_NEAR(t.bearing_rad, 0.0, 2e-5);
        GL_CHECK_NEAR(t.distance_m, 3.0 - ball_y, 1e-5);
        /* using the centre formula with the left camera's bearing is wrong by that much */
        t = gl_range_from_ball((float)r_left, (float)b_left);
        GL_CHECK(fabsf(t.bearing_rad) > 0.003f);
    }
}

GL_TEST(test_depth_versus_distance)
{
    /* A stick 20 degrees off the axis at a horizontal distance of 6 m: stereo
     * sees the DEPTH 6 cos(20) = 5.64 m, the angular height sees 6 m. */
    gl_stick_height_t h;
    gl_range_result_t r;
    gl_range_input_t in;
    const double dist = 6.0, bearing = 20.0 * 3.14159265358979 / 180.0;
    gl_stick_height_reset(&h);
    h.sigma_m = 0.02f;
    memset(&in, 0, sizeof(in));
    in.f_px = (float)F;
    in.baseline_m = (float)B;
    in.have_stereo = true;
    in.disparity_px = (float)(F * B / (dist * cos(bearing)));
    in.disparity_sigma_px = 0.02f;
    in.have_height = true;
    in.base_visible = true;
    in.tan_base = 0.0f;
    in.tan_top = (float)(1.96 / dist);
    in.elev_sigma_rad = 0.15f / 657.0f;
    /* without the bearing the two disagree by 6 % ... */
    GL_CHECK_EQ(gl_range_fuse(&in, &h, &r), GL_OK);
    GL_CHECK_NEAR(r.stereo_m, dist * cos(bearing), 1e-3);
    GL_CHECK(!r.consistent);
    /* ... with it they agree and the result is the distance */
    in.cos_bearing = (float)cos(bearing);
    GL_CHECK_EQ(gl_range_fuse(&in, &h, &r), GL_OK);
    GL_CHECK_NEAR(r.stereo_m, dist, 1e-3);
    GL_CHECK_NEAR(r.mono_m, dist, 1e-3);
    GL_CHECK_NEAR(r.range_m, dist, 1e-3);
    GL_CHECK(r.consistent);
    /* the stick-height learning uses the distance too */
    gl_stick_height_reset(&h);
    in.tan_top = (float)(2.05 / dist);
    GL_CHECK(gl_stick_height_learn(&h, &in));
    GL_CHECK(h.height_m > 1.96f && h.height_m < 2.06f);
}

int main(void)
{
    GL_RUN(test_prior);
    GL_RUN(test_stereo_only);
    GL_RUN(test_fusion_weights);
    GL_RUN(test_inconsistency_flag);
    GL_RUN(test_manual_override);
    GL_RUN(test_stick_height_learning);
    GL_RUN(test_fusion_monte_carlo);
    GL_RUN(test_ball_geometry);
    GL_RUN(test_depth_versus_distance);
    return gl_test_summary();
}
