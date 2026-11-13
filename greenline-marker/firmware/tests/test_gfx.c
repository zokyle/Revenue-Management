/*
 * test_gfx.c - framebuffer format, round clipping, line-angle accuracy,
 * aim line geometry, fonts and icons.
 */
#include <limits.h>
#include <stdlib.h>

#include "gl_config.h"
#include "gl_gfx.h"
#include "gl_test.h"

static gl_gfx_t g;

/* Strict aperture test used as the independent reference for the clip:
 * every corner of pixel (x, y) within radius D/2 of the screen centre. */
static int ref_inside(int x, int y)
{
    double r = 0.5 * (double)GL_CFG_LCD_CLIP_DIA_PX;
    for (int cy = -1; cy <= 1; cy += 2) {
        for (int cx = -1; cx <= 1; cx += 2) {
            double px = (double)x + 0.5 * cx - 63.5;
            double py = (double)y + 0.5 * cy - 63.5;
            if (px * px + py * py > r * r + 1e-9) {
                return 0;
            }
        }
    }
    return 1;
}

/* Total-least-squares direction of the black pixels, returned as an angle
 * in the gfx convention (CCW from up), modulo pi, plus centroid. */
static double fit_angle(const gl_gfx_t *gg, double *mx, double *my, unsigned *n_out)
{
    double sx = 0, sy = 0, sxx = 0, syy = 0, sxy = 0;
    unsigned n = 0;
    for (int y = 0; y < GL_GFX_H; y++) {
        for (int x = 0; x < GL_GFX_W; x++) {
            if (!gl_gfx_get(gg, x, y)) {
                sx += x;
                sy += y;
                sxx += (double)x * x;
                syy += (double)y * y;
                sxy += (double)x * y;
                n++;
            }
        }
    }
    *n_out = n;
    if (n < 3) {
        return 0.0;
    }
    double cx = sx / n, cy = sy / n;
    double cxx = sxx / n - cx * cx, cyy = syy / n - cy * cy, cxy = sxy / n - cx * cy;
    double th = 0.5 * atan2(2.0 * cxy, cxx - cyy); /* principal axis from +x, y down */
    double dx = cos(th), dy = sin(th);
    *mx = cx;
    *my = cy;
    return atan2(-dx, -dy); /* direction (-sin a, -cos a) -> a */
}

static double ang_diff_mod_pi(double a, double b)
{
    double d = a - b;
    while (d > 1.5707963267948966) {
        d -= 3.141592653589793;
    }
    while (d < -1.5707963267948966) {
        d += 3.141592653589793;
    }
    return d;
}

GL_TEST(test_format_and_bit_order)
{
    gl_gfx_init(&g);
    gl_gfx_set_clip(&g, false);
    GL_CHECK_EQ(sizeof(g.px), 2048);
    GL_CHECK_EQ(g.px[0], 0xFF);
    GL_CHECK_EQ(gl_gfx_count_black(&g), 0);
    /* leftmost pixel of a row is bit 0 of its first byte (LSB-first LCD) */
    gl_gfx_pixel(&g, 0, 0, GL_INK_BLACK);
    GL_CHECK_EQ(g.px[0], 0xFE);
    gl_gfx_pixel(&g, 7, 0, GL_INK_BLACK);
    GL_CHECK_EQ(g.px[0], 0x7E);
    gl_gfx_pixel(&g, 8, 0, GL_INK_BLACK);
    GL_CHECK_EQ(g.px[1], 0xFE);
    gl_gfx_pixel(&g, 127, 127, GL_INK_BLACK);
    GL_CHECK_EQ(g.px[2047], 0x7F);
    GL_CHECK(!gl_gfx_get(&g, 127, 127));
    GL_CHECK(gl_gfx_get(&g, 126, 127));
    GL_CHECK(gl_gfx_row(&g, 127) == &g.px[127 * 16]);
    /* hline spanning byte boundaries */
    gl_gfx_clear(&g, GL_INK_WHITE);
    gl_gfx_hline(&g, 5, 18, 3, GL_INK_BLACK);
    GL_CHECK_EQ(g.px[3 * 16 + 0], 0x1F);
    GL_CHECK_EQ(g.px[3 * 16 + 1], 0x00);
    GL_CHECK_EQ(g.px[3 * 16 + 2], 0xF8);
    GL_CHECK_EQ(gl_gfx_count_black(&g), 14);
    gl_gfx_hline(&g, 18, 5, 3, GL_INK_WHITE); /* reversed order, erase */
    GL_CHECK_EQ(gl_gfx_count_black(&g), 0);
    /* out-of-range coordinates are ignored */
    gl_gfx_pixel(&g, -1, 0, GL_INK_BLACK);
    gl_gfx_pixel(&g, 128, 0, GL_INK_BLACK);
    gl_gfx_pixel(&g, 0, -1, GL_INK_BLACK);
    gl_gfx_pixel(&g, 0, 128, GL_INK_BLACK);
    gl_gfx_rect(&g, -50, -50, 20, 20, GL_INK_BLACK);
    gl_gfx_rect(&g, 200, 200, 20, 20, GL_INK_BLACK);
    GL_CHECK_EQ(gl_gfx_count_black(&g), 0);
}

GL_TEST(test_round_clip_matches_reference)
{
    unsigned drawable = 0, mismatch = 0;
    gl_gfx_init(&g);
    for (int y = 0; y < GL_GFX_H; y++) {
        for (int x = 0; x < GL_GFX_W; x++) {
            int in = gl_gfx_in_clip(&g, x, y) ? 1 : 0;
            drawable += (unsigned)in;
            if (in != ref_inside(x, y)) {
                mismatch++;
            }
        }
    }
    GL_CHECK_EQ(mismatch, 0);
    /* area of a 122 px circle is 11690 px; whole-pixel interior is a bit less */
    GL_CHECK(drawable > 11200 && drawable < 11690);
    printf("    clip: %u drawable pixels (circle area %.0f)\n", drawable,
           3.14159265 * 61.0 * 61.0);
    /* a full-screen fill touches exactly the drawable set */
    gl_gfx_rect(&g, 0, 0, 128, 128, GL_INK_BLACK);
    GL_CHECK_EQ(gl_gfx_count_black(&g), drawable);
    /* symmetric under 180 degree rotation and mirror */
    for (int y = 0; y < GL_GFX_H; y++) {
        for (int x = 0; x < GL_GFX_W; x++) {
            GL_CHECK(gl_gfx_get(&g, x, y) == gl_gfx_get(&g, 127 - x, 127 - y));
            GL_CHECK(gl_gfx_get(&g, x, y) == gl_gfx_get(&g, 127 - x, y));
        }
    }
    /* corners of the square are outside */
    GL_CHECK(!gl_gfx_in_clip(&g, 0, 0));
    GL_CHECK(!gl_gfx_in_clip(&g, 3, 63));
    GL_CHECK(gl_gfx_in_clip(&g, 4, 63));
    GL_CHECK(gl_gfx_in_clip(&g, 123, 64));
    GL_CHECK(!gl_gfx_in_clip(&g, 124, 64));
}

/* Throw every primitive at the buffer with wild arguments; afterwards no
 * pixel outside the aperture may be black. */
GL_TEST(test_no_primitive_escapes_clip)
{
    unsigned outside = 0;
    srand(12345);
    gl_gfx_init(&g);
    for (int i = 0; i < 400; i++) {
        float a = (float)(rand() % 6283) / 1000.0f;
        float px = (float)(rand() % 400 - 136) + 0.37f;
        float py = (float)(rand() % 400 - 136) + 0.11f;
        int x = rand() % 180 - 26, y = rand() % 180 - 26;
        gl_gfx_line_style_t st = { 5.0f, 3.0f, (i & 1) != 0 };
        gl_gfx_line_angle(&g, px, py, a, (float)(rand() % 6), NULL, GL_INK_BLACK);
        gl_gfx_line_angle(&g, px, py, a, 2.0f, &st, GL_INK_BLACK);
        gl_gfx_segment(&g, px, py, (float)x, (float)y, 2.5f, GL_INK_BLACK);
        gl_gfx_rect(&g, x, y, rand() % 60, rand() % 60, GL_INK_BLACK);
        gl_gfx_frame(&g, x, y, rand() % 90, rand() % 90, GL_INK_BLACK);
        gl_gfx_disc(&g, px, py, (float)(rand() % 40), GL_INK_BLACK);
        gl_gfx_arc(&g, px, py, 5.0f, 9.0f, a, a + 3.0f, GL_INK_BLACK);
        gl_gfx_triangle(&g, px, py, (float)x, (float)y, (float)(rand() % 128),
                        (float)(rand() % 128), GL_INK_BLACK);
        gl_gfx_arrow(&g, px, py, a, 30.0f, 8.0f, 1.5f, GL_INK_BLACK);
        gl_gfx_text(&g, x, y, "GREENLINE 0123", 1 + rand() % 3, GL_INK_BLACK);
        gl_gfx_big_number(&g, x, y, "-12.5", 9 + rand() % 30, GL_INK_BLACK);
        gl_gfx_icon(&g, x, y, (gl_icon_t)(rand() % GL_ICON_COUNT), GL_INK_BLACK);
        gl_gfx_battery(&g, x, y, rand() % 101);
        gl_gfx_conf_bar(&g, x, y, rand() % 6, 5);
        gl_gfx_vline(&g, x, y - 300, y + 300, GL_INK_BLACK);
        gl_gfx_hline(&g, x - 300, x + 300, y, GL_INK_BLACK);
        gl_gfx_aim_line(&g, a - 3.14f, 3.0f, NULL);
    }
    for (int y = 0; y < GL_GFX_H; y++) {
        for (int x = 0; x < GL_GFX_W; x++) {
            if (!gl_gfx_get(&g, x, y) && !ref_inside(x, y)) {
                outside++;
            }
        }
    }
    GL_CHECK_EQ(outside, 0);
    GL_CHECK(gl_gfx_count_black(&g) > 5000);
    /* extreme / non-finite arguments must not crash or draw outside */
    {
        const float bad[4] = { (float)NAN, (float)INFINITY, -(float)INFINITY, 3e38f };
        gl_gfx_line_style_t st = { 4.0f, 2.0f, true };
        unsigned before = gl_gfx_count_black(&g);
        gl_gfx_clear(&g, GL_INK_WHITE);
        for (int i = 0; i < 4; i++) {
            float b = bad[i];
            gl_gfx_line_angle(&g, b, 10.0f, 0.3f, 3.0f, NULL, GL_INK_BLACK);
            gl_gfx_line_angle(&g, 10.0f, b, 0.3f, 3.0f, &st, GL_INK_BLACK);
            gl_gfx_line_angle(&g, 64.0f, 64.0f, (i == 3) ? 0.0f : b, 3.0f, &st, GL_INK_BLACK);
            gl_gfx_segment(&g, b, 0.0f, 50.0f, 50.0f, 2.0f, GL_INK_BLACK);
            gl_gfx_segment(&g, 10.0f, 10.0f, b, b, 2.0f, GL_INK_BLACK);
            gl_gfx_disc(&g, b, 64.0f, 5.0f, GL_INK_BLACK);
            gl_gfx_disc(&g, 64.0f, 64.0f, (i == 3) ? 2.0f : b, GL_INK_WHITE);
            gl_gfx_arc(&g, b, b, 2.0f, 5.0f, 0.0f, 1.0f, GL_INK_BLACK);
            gl_gfx_triangle(&g, b, 0.0f, 10.0f, b, 20.0f, 20.0f, GL_INK_BLACK);
            gl_gfx_arrow(&g, b, b, b, 10.0f, 4.0f, 1.0f, GL_INK_BLACK);
            gl_gfx_aim_line(&g, (i == 3) ? 0.0f : b, 3.0f, NULL);
        }
        (void)before;
    }
    gl_gfx_line_angle(&g, 1e30f, -1e30f, 1e9f, 3.0f, NULL, GL_INK_BLACK);
    gl_gfx_segment(&g, -1e20f, 0.0f, 1e20f, 5.0f, 2.0f, GL_INK_BLACK);
    gl_gfx_disc(&g, 1e20f, 1e20f, 1e20f, GL_INK_BLACK);
    gl_gfx_triangle(&g, -1e20f, -1e20f, 1e20f, 0.0f, 0.0f, 1e20f, GL_INK_BLACK);
}

/* Rasterise lines at `n` angles (step_deg apart, starting at start_deg) and
 * return RMS and worst angle error of the fitted lit pixels, in degrees. */
static void sweep_(double start_deg, double step_deg, int n, float half_w, bool dither,
                   double *rms_deg, double *worst_deg)
{
    double sum2 = 0, worst = 0, mx, my;
    unsigned npx;
    gl_gfx_line_style_t st = { 0.0f, 0.0f, dither };
    for (int i = 0; i < n; i++) {
        double a = (start_deg + (double)i * step_deg) * 3.141592653589793 / 180.0;
        float px = 63.5f + 0.37f * (float)((i * 7) % 11 - 5);
        float py = 63.5f + 0.29f * (float)((i * 3) % 13 - 6);
        gl_gfx_init(&g);
        gl_gfx_line_angle(&g, px, py, (float)a, half_w, &st, GL_INK_BLACK);
        double fit = fit_angle(&g, &mx, &my, &npx);
        double e = ang_diff_mod_pi(fit, a) * 180.0 / 3.141592653589793;
        GL_CHECK(npx > 200);
        sum2 += e * e;
        if (fabs(e) > worst) {
            worst = fabs(e);
        }
    }
    *rms_deg = sqrt(sum2 / n);
    *worst_deg = worst;
}

/* The headline requirement: rasterise at many angles, fit the lit pixels,
 * recovered angle error below 0.15 degree RMS. */
GL_TEST(test_line_angle_accuracy)
{
    double rms, worst;

    printf("    recovered-angle error of rasterised lines (fit of lit pixels):\n");
    printf("    %-58s %9s %9s\n", "case", "RMS deg", "worst deg");

    sweep_(0.0, 0.1, 1800, 3.0f, false, &rms, &worst);
    printf("    %-58s %9.4f %9.4f\n", "7 px wide, all 1800 angles, plain edges", rms, worst);
    GL_CHECK(rms < 0.15);

    sweep_(0.0, 0.1, 1800, 3.0f, true, &rms, &worst);
    printf("    %-58s %9.4f %9.4f\n", "7 px wide, all 1800 angles, dithered edges", rms, worst);
    GL_CHECK(rms < 0.15);
    GL_CHECK(worst < 0.45);

    sweep_(0.0, 0.1, 1800, 1.0f, false, &rms, &worst);
    printf("    %-58s %9.4f %9.4f\n", "3 px wide, all 1800 angles, plain edges", rms, worst);
    GL_CHECK(rms < 0.15);

    /* The hard case for a 1-bit display: within +-1 deg of a pixel axis the
     * plain rule can render several distinct angles identically. */
    sweep_(-1.0, 0.01, 201, 3.0f, false, &rms, &worst);
    printf("    %-58s %9.4f %9.4f\n", "7 px wide, -1..+1 deg in 0.01 steps, plain edges", rms,
           worst);
    sweep_(-1.0, 0.01, 201, 3.0f, true, &rms, &worst);
    printf("    %-58s %9.4f %9.4f\n", "7 px wide, -1..+1 deg in 0.01 steps, dithered edges", rms,
           worst);
    GL_CHECK(rms < 0.15);
    sweep_(89.0, 0.01, 201, 3.0f, true, &rms, &worst);
    printf("    %-58s %9.4f %9.4f\n", "7 px wide, 89..91 deg in 0.01 steps, dithered edges", rms,
           worst);
    GL_CHECK(rms < 0.15);
}

/* The aim line proper: through the off-screen ball position. */
GL_TEST(test_aim_line_geometry_and_accuracy)
{
    double sum2 = 0, worst = 0, sum2_ball = 0, worst_ball = 0;
    unsigned n = 0, npx;
    double mx, my;
    const double ball_x = 63.5, ball_y = 63.5 - (double)GL_CFG_BALL_CENTRE_Y_PX;
    gl_gfx_aim_info_t info;

    for (int i = -1300; i <= 1300; i++) {
        double a_deg = 0.01 * (double)i + 0.0013;
        double a = a_deg * 3.141592653589793 / 180.0;
        gl_gfx_init(&g);
        gl_gfx_aim_line(&g, (float)a, 3.0f, &info);
        GL_CHECK(info.on_screen);
        GL_CHECK_EQ(info.pixels, gl_gfx_count_black(&g));
        GL_CHECK_NEAR(info.offset_px, (double)GL_CFG_BALL_CENTRE_Y_PX * sin(a), 1e-3);
        double fit = fit_angle(&g, &mx, &my, &npx);
        double e = ang_diff_mod_pi(fit, a) * 180.0 / 3.141592653589793;
        /* perpendicular distance from the ball centre to the fitted line */
        double dx = -sin(fit), dy = -cos(fit);
        double perp = (ball_x - mx) * dy - (ball_y - my) * dx;
        sum2 += e * e;
        sum2_ball += perp * perp;
        if (fabs(e) > worst) {
            worst = fabs(e);
        }
        if (fabs(perp) > worst_ball) {
            worst_ball = fabs(perp);
        }
        n++;
        /* the line is on the right half for aim-left (positive) angles */
        if (a_deg > 1.0) {
            GL_CHECK(mx > 63.5);
        } else if (a_deg < -1.0) {
            GL_CHECK(mx < 63.5);
        }
    }
    double rms = sqrt(sum2 / n);
    printf("    aim line through the ball (%.1f px off-screen), -13..+13 deg, 2601 angles: "
           "RMS %.4f deg, worst %.4f deg\n", (double)GL_CFG_BALL_CENTRE_Y_PX, rms, worst);
    printf("    fitted line misses the ball centre by RMS %.3f px (%.3f mm), worst %.3f px\n",
           sqrt(sum2_ball / n), sqrt(sum2_ball / n) * (double)GL_CFG_LCD_PIXEL_PITCH_MM,
           worst_ball);
    GL_CHECK(rms < 0.15);
    GL_CHECK(sqrt(sum2_ball / n) < 1.0);

    /* aim = 0: the line is the vertical centre line */
    gl_gfx_init(&g);
    gl_gfx_aim_line(&g, 0.0f, 3.0f, &info);
    GL_CHECK(info.on_screen);
    GL_CHECK_NEAR(info.chord_px, 122.0, 1e-3);
    GL_CHECK(!gl_gfx_get(&g, 63, 64) && !gl_gfx_get(&g, 64, 64));
    GL_CHECK(!gl_gfx_get(&g, 61, 20) && !gl_gfx_get(&g, 66, 100));
    GL_CHECK(gl_gfx_get(&g, 60, 64) && gl_gfx_get(&g, 67, 64));
}

/* After the 180-degree spin of a Precision Read the marker faces away from
 * the hole: the ball position lies BEHIND it (not exactly, the spin is
 * rarely exactly 180 degrees) and the line must still pass through it. */
GL_TEST(test_aim_line_with_the_ball_behind)
{
    double sum2 = 0, sum2_ball = 0, worst = 0;
    unsigned n = 0, npx;
    double mx, my;
    gl_gfx_aim_info_t info;

    for (int spin = -8; spin <= 8; spin += 4) {
        /* the marker was turned by 180 + spin degrees: the ball is at this
         * azimuth in its current frame */
        const double az = (180.0 - (double)spin) * 3.141592653589793 / 180.0;
        const double ball_x = 63.5 - (double)GL_CFG_BALL_CENTRE_Y_PX * sin(az);
        const double ball_y = 63.5 - (double)GL_CFG_BALL_CENTRE_Y_PX * cos(az);
        for (int i = -100; i <= 100; i++) {
            /* putt direction: up to +-10 degrees off the line marker -> ball */
            const double a = az + 0.1 * (double)i * 3.141592653589793 / 180.0;
            gl_gfx_init(&g);
            gl_gfx_aim_line_at(&g, (float)a, (float)az, 3.0f, &info);
            GL_CHECK(info.on_screen);
            double fit = fit_angle(&g, &mx, &my, &npx);
            double e = ang_diff_mod_pi(fit, a) * 180.0 / 3.141592653589793;
            double dx = -sin(fit), dy = -cos(fit);
            double perp = (ball_x - mx) * dy - (ball_y - my) * dx;
            sum2 += e * e;
            sum2_ball += perp * perp;
            if (fabs(e) > worst) {
                worst = fabs(e);
            }
            n++;
        }
    }
    printf("    aim line with the ball behind (spin 172..188 deg), 1005 lines: RMS %.4f deg, "
           "worst %.4f deg; misses the ball centre by RMS %.3f px\n", sqrt(sum2 / n), worst,
           sqrt(sum2_ball / n));
    GL_CHECK(sqrt(sum2 / n) < 0.15);
    GL_CHECK(sqrt(sum2_ball / n) < 1.0);
    /* ball exactly behind, putt exactly along the axis: the same vertical
     * centre line as the normal case */
    {
        static gl_gfx_t ref;
        gl_gfx_init(&ref);
        gl_gfx_aim_line(&ref, 0.0f, 3.0f, NULL);
        gl_gfx_init(&g);
        gl_gfx_aim_line_at(&g, 3.14159265f, 3.14159265f, 3.0f, &info);
        GL_CHECK(info.on_screen);
        GL_CHECK(!gl_gfx_get(&g, 63, 64) && !gl_gfx_get(&g, 64, 64));
        GL_CHECK(gl_gfx_get(&g, 60, 64) && gl_gfx_get(&g, 67, 64));
        GL_CHECK(abs((int)gl_gfx_count_black(&g) - (int)gl_gfx_count_black(&ref)) < 40);
    }
    /* a "putt" that would start back across the marker is never drawn as
     * the true line */
    gl_gfx_init(&g);
    gl_gfx_aim_line_at(&g, 0.0f, 3.14159265f, 3.0f, &info);
    GL_CHECK(!info.on_screen);
}

GL_TEST(test_aim_line_off_screen_fallback)
{
    gl_gfx_aim_info_t info;
    unsigned npx;
    double mx, my;
    /* 20 degrees: the true line misses the aperture entirely */
    gl_gfx_init(&g);
    gl_gfx_aim_line(&g, 20.0f * GL_DEG2RAD_F, 3.0f, &info);
    GL_CHECK(!info.on_screen);
    GL_CHECK(info.offset_px > 61.0f);
    GL_CHECK_NEAR(info.chord_px, 0.0, 1e-6);
    GL_CHECK(info.pixels > 100);
    /* the substitute is parallel to the aim direction, through the centre */
    double fit = fit_angle(&g, &mx, &my, &npx);
    GL_CHECK_NEAR(ang_diff_mod_pi(fit, 20.0 * 3.14159265 / 180.0) * 57.29578, 0.0, 0.6);
    GL_CHECK_NEAR(mx, 63.5, 1.0);
    GL_CHECK_NEAR(my, 63.5, 1.0);
    /* It has the STYLE of the line it stands for.  The solid aim line gives a
     * solid parallel (as many pixels as a plain solid line, give or take the
     * edge dithering); the tentative one gives the long dashes, 9 on / 7 off.
     * (It used to be a third style, 6 / 4 dashes, for both: a solved aim off
     * the screen looked like "not a solution".) */
    {
        const unsigned sub_solid = info.pixels;
        unsigned sub_tent, solid;
        gl_gfx_init(&g);
        gl_gfx_aim_line_styled(&g, 20.0f * GL_DEG2RAD_F, 0.0f, 3.0f, true, &info);
        GL_CHECK(!info.on_screen);
        sub_tent = info.pixels;
        fit = fit_angle(&g, &mx, &my, &npx);
        GL_CHECK_NEAR(ang_diff_mod_pi(fit, 20.0 * 3.14159265 / 180.0) * 57.29578, 0.0, 0.8);
        gl_gfx_init(&g);
        solid = gl_gfx_line_angle(&g, 63.5f, 63.5f, 20.0f * GL_DEG2RAD_F, 3.0f, NULL, GL_INK_BLACK);
        GL_CHECK(sub_solid > solid * 19 / 20 && sub_solid < solid * 21 / 20);
        GL_CHECK(sub_tent < solid * 13 / 20 && sub_tent > solid * 9 / 20);
    }
    /* negative side */
    gl_gfx_init(&g);
    gl_gfx_aim_line(&g, -16.0f * GL_DEG2RAD_F, 3.0f, &info);
    GL_CHECK(!info.on_screen);
    GL_CHECK(info.offset_px < -61.0f);
    /* just inside the limit the true line is still drawn */
    gl_gfx_init(&g);
    gl_gfx_aim_line(&g, 13.0f * GL_DEG2RAD_F, 3.0f, &info);
    GL_CHECK(info.on_screen);
    GL_CHECK(info.chord_px >= GL_GFX_AIM_MIN_CHORD_PX);
    /* a backwards aim is never "on screen" */
    gl_gfx_init(&g);
    gl_gfx_aim_line(&g, 3.1f, 3.0f, &info);
    GL_CHECK(!info.on_screen);
}

GL_TEST(test_text_and_fonts)
{
    gl_gfx_init(&g);
    gl_gfx_set_clip(&g, false);
    /* 'A' at (10, 20): row 0 = .###. , row 4 = ##### */
    int xe = gl_gfx_text(&g, 10, 20, "A", 1, GL_INK_BLACK);
    GL_CHECK_EQ(xe, 16);
    GL_CHECK(gl_gfx_get(&g, 10, 20));
    GL_CHECK(!gl_gfx_get(&g, 11, 20) && !gl_gfx_get(&g, 12, 20) && !gl_gfx_get(&g, 13, 20));
    GL_CHECK(gl_gfx_get(&g, 14, 20));
    for (int c = 0; c < 5; c++) {
        GL_CHECK(!gl_gfx_get(&g, 10 + c, 24));
    }
    GL_CHECK_EQ(gl_gfx_count_black(&g), 3 + 2 + 2 + 2 + 5 + 2 + 2);
    /* lower case maps to upper case, unknown maps to '?' */
    {
        static gl_gfx_t g2;
        gl_gfx_init(&g2);
        gl_gfx_set_clip(&g2, false);
        gl_gfx_text(&g2, 10, 20, "a", 1, GL_INK_BLACK);
        GL_CHECK_MEM(g.px, g2.px, sizeof(g.px));
        gl_gfx_clear(&g, GL_INK_WHITE);
        gl_gfx_clear(&g2, GL_INK_WHITE);
        gl_gfx_text(&g, 0, 0, "?", 1, GL_INK_BLACK);
        gl_gfx_text(&g2, 0, 0, "\x7f", 1, GL_INK_BLACK);
        GL_CHECK_MEM(g.px, g2.px, sizeof(g.px));
    }
    GL_CHECK_EQ(gl_gfx_text_width("", 1), 0);
    GL_CHECK_EQ(gl_gfx_text_width("AB", 1), 11);
    GL_CHECK_EQ(gl_gfx_text_width("AB", 2), 22);
    /* every glyph except space has ink, and fits 5 columns */
    for (int ch = GL_FONT_FIRST; ch <= GL_FONT_LAST; ch++) {
        unsigned ink = 0;
        for (int r = 0; r < GL_FONT_H; r++) {
            uint8_t b = gl_font5x7[ch - GL_FONT_FIRST][r];
            GL_CHECK((b & 0xE0u) == 0);
            ink += (unsigned)b;
        }
        GL_CHECK((ch == ' ') ? (ink == 0) : (ink != 0));
    }
    /* scaled text: scale 3 draws 9x the pixels */
    gl_gfx_clear(&g, GL_INK_WHITE);
    gl_gfx_text(&g, 5, 5, "8", 1, GL_INK_BLACK);
    unsigned n1 = gl_gfx_count_black(&g);
    gl_gfx_clear(&g, GL_INK_WHITE);
    gl_gfx_text(&g, 5, 5, "8", 3, GL_INK_BLACK);
    GL_CHECK_EQ(gl_gfx_count_black(&g), 9 * n1);
    /* centred text is centred */
    gl_gfx_clear(&g, GL_INK_WHITE);
    gl_gfx_text_centred(&g, 64, 30, "HOLD STILL", 1, GL_INK_BLACK);
    {
        int minx = 999, maxx = -1;
        for (int y = 30; y < 37; y++) {
            for (int x = 0; x < 128; x++) {
                if (!gl_gfx_get(&g, x, y)) {
                    if (x < minx) {
                        minx = x;
                    }
                    if (x > maxx) {
                        maxx = x;
                    }
                }
            }
        }
        GL_CHECK_EQ(maxx - minx + 1, gl_gfx_text_width("HOLD STILL", 1));
        GL_CHECK(abs((minx + maxx + 1) / 2 - 64) <= 1);
    }
}

GL_TEST(test_big_digits_and_icons)
{
    gl_gfx_init(&g);
    gl_gfx_set_clip(&g, false);
    /* the drawn extent equals the reported width, for several sizes */
    for (int h = 9; h <= 40; h += 7) {
        const char *s = "-12.5 8";
        int minx = 999, maxx = -1, miny = 999, maxy = -1;
        gl_gfx_clear(&g, GL_INK_WHITE);
        int xe = gl_gfx_big_number(&g, 3, 4, s, h, GL_INK_BLACK);
        for (int y = 0; y < 128; y++) {
            for (int x = 0; x < 128; x++) {
                if (!gl_gfx_get(&g, x, y)) {
                    minx = (x < minx) ? x : minx;
                    maxx = (x > maxx) ? x : maxx;
                    miny = (y < miny) ? y : miny;
                    maxy = (y > maxy) ? y : maxy;
                }
            }
        }
        if (3 + gl_gfx_big_number_width(s, h) <= 128) { /* not truncated by the screen */
            GL_CHECK_EQ(maxx - 3 + 1, gl_gfx_big_number_width(s, h));
            GL_CHECK(xe > maxx);
        }
        GL_CHECK(miny >= 4 && maxy <= 4 + h - 1);
    }
    /* '8' lights all seven segments, '1' only two: pixel counts ordered */
    {
        unsigned n8, n1, n0;
        gl_gfx_clear(&g, GL_INK_WHITE);
        gl_gfx_big_number(&g, 10, 10, "8", 24, GL_INK_BLACK);
        n8 = gl_gfx_count_black(&g);
        gl_gfx_clear(&g, GL_INK_WHITE);
        gl_gfx_big_number(&g, 10, 10, "1", 24, GL_INK_BLACK);
        n1 = gl_gfx_count_black(&g);
        gl_gfx_clear(&g, GL_INK_WHITE);
        gl_gfx_big_number(&g, 10, 10, "0", 24, GL_INK_BLACK);
        n0 = gl_gfx_count_black(&g);
        GL_CHECK(n8 > n0 && n0 > n1 && n1 > 0);
    }
    /* icons: each draws exactly the number of set bits of its bitmap */
    for (int i = 0; i < GL_ICON_COUNT; i++) {
        unsigned bits = 0;
        for (int r = 0; r < gl_icons[i].h; r++) {
            uint16_t v = gl_icons[i].rows[r];
            while (v) {
                bits += v & 1u;
                v = (uint16_t)(v >> 1);
            }
        }
        gl_gfx_clear(&g, GL_INK_WHITE);
        gl_gfx_icon(&g, 40, 40, (gl_icon_t)i, GL_INK_BLACK);
        GL_CHECK(bits > 0);
        GL_CHECK_EQ(gl_gfx_count_black(&g), bits);
    }
    /* battery fill grows with charge */
    {
        unsigned prev = 0;
        for (int p = 0; p <= 100; p += 25) {
            gl_gfx_clear(&g, GL_INK_WHITE);
            gl_gfx_battery(&g, 50, 50, p);
            unsigned n = gl_gfx_count_black(&g);
            GL_CHECK(p == 0 || n > prev);
            prev = n;
        }
    }
    /* confidence bar */
    gl_gfx_clear(&g, GL_INK_WHITE);
    gl_gfx_conf_bar(&g, 40, 60, 0, 5);
    unsigned empty = gl_gfx_count_black(&g);
    gl_gfx_conf_bar(&g, 40, 60, 5, 5);
    GL_CHECK_EQ(gl_gfx_count_black(&g), 5 * 30);
    GL_CHECK_EQ(empty, 5 * (30 - 3 * 4));
}

GL_TEST(test_changed_rows)
{
    static uint8_t shadow[GL_GFX_BYTES];
    uint8_t rows[GL_GFX_H];
    gl_gfx_init(&g);
    memcpy(shadow, g.px, sizeof(shadow));
    GL_CHECK_EQ(gl_gfx_changed_rows(&g, shadow, rows), 0);
    gl_gfx_hline(&g, 30, 90, 17, GL_INK_BLACK);
    gl_gfx_pixel(&g, 64, 99, GL_INK_BLACK);
    GL_CHECK_EQ(gl_gfx_changed_rows(&g, shadow, rows), 2);
    GL_CHECK_EQ(rows[0], 17);
    GL_CHECK_EQ(rows[1], 99);
    /* redrawing identical content changes nothing */
    memcpy(shadow, g.px, sizeof(shadow));
    gl_gfx_clear(&g, GL_INK_WHITE);
    gl_gfx_hline(&g, 30, 90, 17, GL_INK_BLACK);
    gl_gfx_pixel(&g, 64, 99, GL_INK_BLACK);
    GL_CHECK_EQ(gl_gfx_changed_rows(&g, shadow, rows), 0);
}

GL_TEST(test_shapes)
{
    gl_gfx_init(&g);
    gl_gfx_set_clip(&g, false);
    /* disc area ~ pi r^2 */
    gl_gfx_disc(&g, 64.0f, 64.0f, 20.0f, GL_INK_BLACK);
    GL_CHECK_NEAR(gl_gfx_count_black(&g), 3.14159 * 400.0, 30.0);
    /* triangle area = 0.5 * base * height */
    gl_gfx_clear(&g, GL_INK_WHITE);
    gl_gfx_triangle(&g, 10.0f, 10.0f, 70.0f, 10.0f, 10.0f, 50.0f, GL_INK_BLACK);
    /* inclusive edges add about half the perimeter: 1200 + 86 */
    GL_CHECK_NEAR(gl_gfx_count_black(&g), 0.5 * 60.0 * 40.0 + 86.0, 40.0);
    /* a full ring equals disc(out) - disc(in) */
    gl_gfx_clear(&g, GL_INK_WHITE);
    gl_gfx_arc(&g, 64.0f, 64.0f, 10.0f, 14.0f, 0.0f, 7.0f, GL_INK_BLACK);
    GL_CHECK_NEAR(gl_gfx_count_black(&g), 3.14159 * (196.0 - 100.0), 30.0);
    /* a quarter arc starting at "up" going CCW covers the upper-left quadrant */
    gl_gfx_clear(&g, GL_INK_WHITE);
    gl_gfx_arc(&g, 64.0f, 64.0f, 10.0f, 14.0f, 0.0f, GL_PI_F * 0.5f, GL_INK_BLACK);
    GL_CHECK(!gl_gfx_get(&g, 56, 56)); /* upper-left: drawn */
    GL_CHECK(gl_gfx_get(&g, 72, 56));  /* upper-right: not drawn */
    GL_CHECK(gl_gfx_get(&g, 56, 72));
    /* segment: length x width */
    gl_gfx_clear(&g, GL_INK_WHITE);
    unsigned n = gl_gfx_segment(&g, 20.0f, 30.0f, 100.0f, 30.0f, 2.0f, GL_INK_BLACK);
    GL_CHECK_EQ(n, 81 * 5);
    /* arrow at angle 0 points up: tip above the start */
    gl_gfx_clear(&g, GL_INK_WHITE);
    gl_gfx_arrow(&g, 64.0f, 100.0f, 0.0f, 40.0f, 10.0f, 1.0f, GL_INK_BLACK);
    GL_CHECK(!gl_gfx_get(&g, 64, 61));
    GL_CHECK(gl_gfx_get(&g, 64, 58));
    GL_CHECK(!gl_gfx_get(&g, 60, 69)); /* head is wider than the shaft */
    GL_CHECK(gl_gfx_get(&g, 60, 90));
}

/* Review finding: the integer primitives added positions and sizes without
 * bounds (signed overflow, undefined behaviour) while the float ones were
 * clamped.  Runs under UBSan in `make asan`; here the visible result of
 * every call is checked as well. */
GL_TEST(test_extreme_integer_arguments)
{
    static const int ext[] = { INT_MIN, INT_MIN + 1, -GL_GFX_COORD_LIMIT - 1, -5000, -1, 0, 1,
                               127, 128, 5000, GL_GFX_COORD_LIMIT + 1, INT_MAX - 3, INT_MAX };
    const size_t n = sizeof(ext) / sizeof(ext[0]);
    struct {
        uint8_t guard0[64];
        gl_gfx_t gg;
        uint8_t guard1[64];
    } box;
    unsigned calls = 0;

    memset(&box, 0xA5, sizeof(box));
    gl_gfx_init(&box.gg);
    gl_gfx_set_clip(&box.gg, true);
    for (size_t i = 0; i < n; i++) {
        for (size_t j = 0; j < n; j++) {
            for (size_t k = 0; k < n; k++) {
                const int a = ext[i], b = ext[j], c = ext[k];
                gl_gfx_rect(&box.gg, a, b, c, 4, GL_INK_BLACK);
                gl_gfx_rect(&box.gg, a, b, 4, c, GL_INK_BLACK);
                gl_gfx_frame(&box.gg, a, b, c, 9, GL_INK_BLACK);
                gl_gfx_frame(&box.gg, a, b, 9, c, GL_INK_BLACK);
                gl_gfx_hline(&box.gg, a, b, c, GL_INK_BLACK);
                gl_gfx_vline(&box.gg, a, b, c, GL_INK_BLACK);
                (void)gl_gfx_text(&box.gg, a, b, "A?", c, GL_INK_BLACK);
                gl_gfx_text_centred(&box.gg, a, b, "0.5", c, GL_INK_BLACK);
                (void)gl_gfx_big_number(&box.gg, a, b, "-1.5 8", c, GL_INK_BLACK);
                (void)gl_gfx_big_number_width("-1.5 8", c);
                (void)gl_gfx_text_width("0.5", c);
                gl_gfx_icon(&box.gg, a, b, GL_ICON_FLAG, GL_INK_BLACK);
                gl_gfx_battery(&box.gg, a, b, c);
                gl_gfx_conf_bar(&box.gg, a, b, c, c);
                calls += 14u;
            }
        }
    }
    for (size_t i = 0; i < sizeof(box.guard0); i++) {
        GL_CHECK(box.guard0[i] == 0xA5u && box.guard1[i] == 0xA5u);
    }
    /* nothing outside the aperture circle was touched */
    {
        unsigned outside = 0;
        for (int y = 0; y < GL_GFX_H; y++) {
            for (int x = 0; x < GL_GFX_W; x++) {
                if (!ref_inside(x, y) && !gl_gfx_get(&box.gg, x, y)) {
                    outside++;
                }
            }
        }
        GL_CHECK_EQ(outside, 0);
    }
    /* the clamp changes nothing that can be seen: a rectangle that starts
     * far off-screen and is very large still covers the whole aperture, one
     * that lies entirely off-screen draws nothing */
    gl_gfx_clear(&box.gg, GL_INK_WHITE);
    gl_gfx_rect(&box.gg, -5000, -5000, 10000, 10000, GL_INK_BLACK);
    {
        unsigned all = gl_gfx_count_black(&box.gg);
        gl_gfx_clear(&box.gg, GL_INK_WHITE);
        gl_gfx_rect(&box.gg, INT_MIN, INT_MIN, INT_MAX, INT_MAX, GL_INK_BLACK);
        GL_CHECK_EQ(gl_gfx_count_black(&box.gg), 0); /* ends at -1: left of the screen */
        gl_gfx_rect(&box.gg, -GL_GFX_COORD_LIMIT / 2, -GL_GFX_COORD_LIMIT / 2, INT_MAX, INT_MAX,
                    GL_INK_BLACK); /* size clamped to the limit: still spans the screen */
        GL_CHECK_EQ(gl_gfx_count_black(&box.gg), all);
        GL_CHECK(all > 11000u); /* pi * 61^2 = 11690 */
    }
    printf("    %u calls of the integer primitives with arguments from INT_MIN to INT_MAX: "
           "no pixel outside the aperture, no guard byte changed\n", calls);
}

/* gl_gfx_rotate_180(): pixel (x, y) <-> (127 - x, 127 - y); twice = nothing. */
GL_TEST(test_rotate_180)
{
    static gl_gfx_t a, b;
    unsigned bad = 0;
    gl_gfx_init(&a);
    gl_gfx_set_clip(&a, false);
    /* an asymmetric picture: single pixels in the corners, text, a line */
    gl_gfx_pixel(&a, 0, 0, GL_INK_BLACK);
    gl_gfx_pixel(&a, 127, 0, GL_INK_BLACK);
    gl_gfx_pixel(&a, 5, 127, GL_INK_BLACK);
    gl_gfx_pixel(&a, 8, 3, GL_INK_BLACK);
    (void)gl_gfx_text(&a, 10, 20, "<2.9 CUP 7", 1, GL_INK_BLACK);
    (void)gl_gfx_text(&a, 3, 70, "GL-1", 2, GL_INK_BLACK);
    (void)gl_gfx_line_angle(&a, 40.0f, 90.0f, 0.3f, 2.0f, NULL, GL_INK_BLACK);
    b = a;
    gl_gfx_rotate_180(&b);
    for (int y = 0; y < 128; y++) {
        for (int x = 0; x < 128; x++) {
            bad += (gl_gfx_get(&a, x, y) != gl_gfx_get(&b, 127 - x, 127 - y)) ? 1u : 0u;
        }
    }
    GL_CHECK_EQ(bad, 0);
    GL_CHECK(!gl_gfx_get(&b, 127, 127) && !gl_gfx_get(&b, 0, 127) && !gl_gfx_get(&b, 122, 0) &&
             !gl_gfx_get(&b, 119, 124));
    GL_CHECK_EQ(gl_gfx_count_black(&a), gl_gfx_count_black(&b));
    GL_CHECK(memcmp(a.px, b.px, sizeof(a.px)) != 0);
    gl_gfx_rotate_180(&b);
    GL_CHECK_MEM(a.px, b.px, sizeof(a.px));
    /* a picture drawn under the round clip stays inside it */
    gl_gfx_init(&a);
    gl_gfx_set_clip(&a, true);
    gl_gfx_rect(&a, 0, 0, 128, 128, GL_INK_BLACK);
    b = a;
    gl_gfx_rotate_180(&b);
    GL_CHECK_MEM(a.px, b.px, sizeof(a.px)); /* the aperture is symmetric about the centre */
}

int main(void)
{
    GL_RUN(test_format_and_bit_order);
    GL_RUN(test_round_clip_matches_reference);
    GL_RUN(test_no_primitive_escapes_clip);
    GL_RUN(test_line_angle_accuracy);
    GL_RUN(test_aim_line_geometry_and_accuracy);
    GL_RUN(test_aim_line_with_the_ball_behind);
    GL_RUN(test_aim_line_off_screen_fallback);
    GL_RUN(test_text_and_fonts);
    GL_RUN(test_big_digits_and_icons);
    GL_RUN(test_changed_rows);
    GL_RUN(test_shapes);
    GL_RUN(test_extreme_integer_arguments);
    GL_RUN(test_rotate_180);
    return gl_test_summary();
}
