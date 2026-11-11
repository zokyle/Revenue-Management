/*
 * test_basics.c - the small shared pieces: maths helpers, number
 * formatting, event queue, settings, calibration records, generated
 * configuration, provisional constants and the phase-1 solver stub.
 */
#include <stdlib.h>

#include "gl_cal.h"
#include "gl_config.h"
#include "gl_event.h"
#include "gl_fmt.h"
#include "gl_hal.h"
#include "gl_provisional.h"
#include "gl_settings.h"
#include "gl_sim.h"
#include "gl_solver.h"
#include "gl_test.h"
#include "grain_frontend.h"
#include "ls013b7dh03.h"

GL_TEST(test_math_helpers)
{
    float v[9] = { 5, 1, 9, 3, 7, 2, 8, 6, 4 };
    float w[4] = { 4, 1, 3, 2 };
    gl_mat3_t m = { { { 2, 0.1f, 0 }, { -0.2f, 1.5f, 0.3f }, { 0.05f, 0, 0.8f } } }, inv, prod;
    GL_CHECK_NEAR(gl_median_inplace(v, 9), 5.0, 1e-9);
    GL_CHECK_NEAR(gl_median_inplace(w, 4), 2.5, 1e-9);
    GL_CHECK_NEAR(gl_median_inplace(w, 1), 1.0, 1e-9); /* sorted now: smallest first */
    GL_CHECK_NEAR(gl_median_inplace(w, 0), 0.0, 1e-9);
    /* large array against a reference sort */
    {
        static float big[480], ref[480];
        uint32_t s = 1;
        for (int i = 0; i < 480; i++) {
            s = s * 1664525u + 1013904223u;
            big[i] = ref[i] = (float)(s >> 8) / 1e6f;
        }
        for (int i = 1; i < 480; i++) { /* insertion sort */
            float t = ref[i];
            int j = i;
            while (j > 0 && ref[j - 1] > t) {
                ref[j] = ref[j - 1];
                j--;
            }
            ref[j] = t;
        }
        GL_CHECK_NEAR(gl_median_inplace(big, 480), 0.5 * ((double)ref[239] + (double)ref[240]),
                      1e-6);
        GL_CHECK_MEM(big, ref, sizeof(big));
    }
    GL_CHECK_EQ(gl_mat3_inverse(&m, &inv), GL_OK);
    prod = gl_mat3_mul(&m, &inv);
    for (int i = 0; i < 3; i++) {
        for (int j = 0; j < 3; j++) {
            GL_CHECK_NEAR(prod.m[i][j], (i == j) ? 1.0 : 0.0, 1e-6);
        }
    }
    {
        gl_mat3_t sing = { { { 1, 2, 3 }, { 2, 4, 6 }, { 0, 1, 0 } } };
        GL_CHECK_EQ(gl_mat3_inverse(&sing, &inv), GL_ERR_RANGE);
    }
    /* Euler matrix is a rotation: R R^T = I, and small angles act as expected */
    {
        gl_mat3_t r = gl_mat3_from_euler(0.1f, -0.2f, 0.3f);
        gl_mat3_t rt = gl_mat3_transpose(&r);
        gl_vec3_t x = { 1, 0, 0 }, y;
        prod = gl_mat3_mul(&r, &rt);
        for (int i = 0; i < 3; i++) {
            GL_CHECK_NEAR(prod.m[i][i], 1.0, 1e-6);
        }
        r = gl_mat3_from_euler(0.0f, 0.0f, 0.01f); /* yaw: +x turns toward +y */
        y = gl_mat3_mul_vec(&r, x);
        GL_CHECK_NEAR(y.y, 0.01, 1e-6);
    }
    GL_CHECK_NEAR(gl_wrap_pi(3.5f), 3.5 - 6.2831853, 1e-5);
    GL_CHECK_NEAR(gl_wrap_pi(-3.5f), -3.5 + 6.2831853, 1e-5);
    GL_CHECK_NEAR(gl_wrap_pi(0.5f), 0.5, 1e-7);
    GL_CHECK_NEAR(gl_wrap_pi(7.0f * 6.2831853f + 0.25f), 0.25, 1e-4);
    GL_CHECK_EQ(gl_roundi(2.5f), 3);
    GL_CHECK_EQ(gl_roundi(-2.5f), -3);
    GL_CHECK_EQ(gl_roundi(-0.4f), 0);
    GL_CHECK_NEAR(gl_clampf(5.0f, 0.0f, 1.0f), 1.0, 0);
    {
        uint8_t b[4];
        gl_put_f32(b, -1.5f);
        GL_CHECK_EQ(b[3], 0xBF); /* IEEE-754, little-endian */
        GL_CHECK_EQ(b[2], 0xC0);
        GL_CHECK(gl_get_f32(b) == -1.5f);
        gl_put_u32(b, 0x11223344u);
        GL_CHECK_EQ(b[0], 0x44);
        GL_CHECK_EQ(gl_get_u16(&b[2]), 0x1122);
    }
    GL_CHECK(strcmp(gl_status_name(GL_OK), "OK") == 0);
    GL_CHECK(strcmp(gl_status_name(GL_ERR_NO_STICK), "NO_STICK") == 0);
    GL_CHECK(strcmp(gl_status_name((gl_status_t)99), "?") == 0);
}

GL_TEST(test_number_formatting)
{
    char b[16];
    GL_CHECK_EQ(gl_fmt_int(b, sizeof(b), 0), 1);
    GL_CHECK(strcmp(b, "0") == 0);
    gl_fmt_int(b, sizeof(b), -12345);
    GL_CHECK(strcmp(b, "-12345") == 0);
    gl_fmt_int(b, sizeof(b), 2147483647);
    GL_CHECK(strcmp(b, "2147483647") == 0);
    gl_fmt_int(b, sizeof(b), (-2147483647 - 1));
    GL_CHECK(strcmp(b, "-2147483648") == 0);
    gl_fmt_fixed(b, sizeof(b), 10.5f, 1);
    GL_CHECK(strcmp(b, "10.5") == 0);
    gl_fmt_fixed(b, sizeof(b), 1.25f, 1); /* half away from zero */
    GL_CHECK(strcmp(b, "1.3") == 0);
    gl_fmt_fixed(b, sizeof(b), -0.04f, 1); /* no negative zero */
    GL_CHECK(strcmp(b, "0.0") == 0);
    gl_fmt_fixed(b, sizeof(b), -2.36f, 1);
    GL_CHECK(strcmp(b, "-2.4") == 0);
    gl_fmt_fixed(b, sizeof(b), 3.14159f, 3);
    GL_CHECK(strcmp(b, "3.142") == 0);
    gl_fmt_fixed(b, sizeof(b), 7.0f, 0);
    GL_CHECK(strcmp(b, "7") == 0);
    gl_fmt_fixed(b, sizeof(b), 0.05f, 2);
    GL_CHECK(strcmp(b, "0.05") == 0);
    gl_fmt_fixed(b, sizeof(b), 1e30f, 1); /* clamped, no overflow */
    GL_CHECK(strlen(b) < sizeof(b));
    gl_fmt_fixed(b, sizeof(b), (float)NAN, 1);
    GL_CHECK(strcmp(b, "--") == 0);
    /* truncation never overruns */
    {
        char small[4] = { 'x', 'x', 'x', 'x' };
        gl_fmt_int(small, 3, 123456);
        GL_CHECK_EQ(small[2], '\0');
        GL_CHECK_EQ(small[3], 'x');
        small[0] = '\0';
        gl_fmt_append(small, 4, "ABCDEFG");
        GL_CHECK(strcmp(small, "ABC") == 0);
    }
}

GL_TEST(test_event_queue)
{
    gl_event_queue_t q;
    gl_event_t e;
    gl_event_init(&q);
    GL_CHECK_EQ(gl_event_count(&q), 0);
    GL_CHECK(!gl_event_get(&q, &e));
    /* capacity is LEN - 1; order is first in, first out */
    for (int i = 0; i < (int)GL_EVENT_QUEUE_LEN - 1; i++) {
        GL_CHECK(gl_event_post(&q, (uint16_t)(100 + i), -i));
    }
    GL_CHECK_EQ(gl_event_count(&q), GL_EVENT_QUEUE_LEN - 1);
    GL_CHECK(!gl_event_post(&q, 999, 0));
    GL_CHECK_EQ(q.dropped, 1);
    for (int i = 0; i < (int)GL_EVENT_QUEUE_LEN - 1; i++) {
        GL_CHECK(gl_event_get(&q, &e));
        GL_CHECK_EQ(e.type, 100 + i);
        GL_CHECK_EQ(e.arg, -i);
    }
    GL_CHECK(!gl_event_get(&q, &e));
    /* wraps around many times */
    for (int i = 0; i < 1000; i++) {
        GL_CHECK(gl_event_post(&q, (uint16_t)i, i));
        GL_CHECK(gl_event_post(&q, (uint16_t)(i + 1), i + 1));
        GL_CHECK(gl_event_get(&q, &e));
        GL_CHECK_EQ(e.arg, i);
        GL_CHECK(gl_event_get(&q, &e));
        GL_CHECK_EQ(e.arg, i + 1);
    }
    GL_CHECK_EQ(gl_event_count(&q), 0);
}

GL_TEST(test_settings)
{
    gl_settings_t s, t;
    uint8_t blob[GL_SETTINGS_BLOB_LEN];
    char b[16];

    gl_settings_defaults(&s);
    GL_CHECK_EQ(gl_settings_validate(&s), GL_OK);
    GL_CHECK_NEAR(gl_settings_stimp_ft(&s), 10.0, 1e-6);
    GL_CHECK_EQ(s.grain_enable, 0); /* grain ships disabled */
    GL_CHECK_NEAR(gl_settings_decel_mps2(&s), 0.549, 0.001); /* reference: Stimp 10 */
    GL_CHECK_NEAR(gl_settings_past_m(&s), 0.30, 1e-6);
    /* Stimp range 6..14 in 0.5 steps */
    {
        int lo, hi;
        gl_settings_item_range(GL_ITEM_STIMP, &lo, &hi);
        GL_CHECK_NEAR(0.5 * lo, 6.0, 1e-9);
        GL_CHECK_NEAR(0.5 * hi, 14.0, 1e-9);
        gl_settings_item_set(&s, GL_ITEM_STIMP, 21);
        gl_settings_item_format(&s, GL_ITEM_STIMP, b, sizeof(b));
        GL_CHECK(strcmp(b, "10.5") == 0);
        gl_settings_item_set(&s, GL_ITEM_STIMP, 3); /* clamped */
        GL_CHECK_EQ(s.stimp_x2, 12);
        gl_settings_item_set(&s, GL_ITEM_STIMP, 20);
    }
    /* every item: range, set/get round trip, printable value */
    for (int item = 0; item < GL_ITEM_COUNT; item++) {
        int lo, hi;
        gl_settings_item_range((gl_item_t)item, &lo, &hi);
        GL_CHECK(hi > lo);
        GL_CHECK(strlen(gl_settings_item_name((gl_item_t)item)) <= 8);
        for (int v = lo; v <= hi; v++) {
            gl_settings_item_set(&s, (gl_item_t)item, v);
            GL_CHECK_EQ(gl_settings_validate(&s), GL_OK);
            if (item != GL_ITEM_DISTANCE || v < hi) {
                GL_CHECK_EQ(gl_settings_item_get(&s, (gl_item_t)item), v);
            }
            gl_settings_item_format(&s, (gl_item_t)item, b, sizeof(b));
            GL_CHECK(strlen(b) >= 1 && strlen(b) <= 9);
        }
        gl_settings_item_set(&s, (gl_item_t)item, lo);
    }
    /* distance in each unit */
    gl_settings_defaults(&s);
    gl_settings_format_distance(&s, 4.42f, b, sizeof(b));
    GL_CHECK(strcmp(b, "14.5FT") == 0);
    s.units = GL_UNITS_METRES;
    gl_settings_format_distance(&s, 4.42f, b, sizeof(b));
    GL_CHECK(strcmp(b, "4.4M") == 0);
    s.units = GL_UNITS_PACES;
    gl_settings_format_distance(&s, 4.572f, b, sizeof(b));
    GL_CHECK(strcmp(b, "5.0P") == 0);
    /* manual distance dialled in metres: 0.2 m steps */
    s.units = GL_UNITS_METRES;
    gl_settings_item_set(&s, GL_ITEM_DISTANCE, 22);
    GL_CHECK_EQ(s.manual_distance_cm, 440);
    gl_settings_item_format(&s, GL_ITEM_DISTANCE, b, sizeof(b));
    GL_CHECK(strcmp(b, "4.4M") == 0);
    gl_settings_item_set(&s, GL_ITEM_DISTANCE, 0);
    gl_settings_item_format(&s, GL_ITEM_DISTANCE, b, sizeof(b));
    GL_CHECK(strcmp(b, "--") == 0);
    /* storage round trip and rejection of bad blobs */
    s.stimp_x2 = 25;
    s.pace = GL_PACE_FIRM;
    s.grass = GL_GRASS_POA;
    s.manual_distance_cm = 731;
    gl_settings_encode(&s, blob);
    GL_CHECK_EQ(gl_settings_decode(blob, sizeof(blob), &t), GL_OK);
    GL_CHECK(memcmp(&s, &t, sizeof(s)) == 0);
    GL_CHECK_NEAR(gl_settings_past_m(&t), 0.45, 1e-6);
    GL_CHECK_EQ(gl_settings_decode(blob, sizeof(blob) - 1, &t), GL_ERR_PARAM);
    blob[0] = 7;
    GL_CHECK_EQ(gl_settings_decode(blob, sizeof(blob), &t), GL_ERR_UNSUPPORTED);
    blob[0] = GL_SETTINGS_VERSION;
    for (int field = 1; field <= 6; field++) {
        uint8_t keep = blob[field];
        blob[field] = 200;
        gl_settings_defaults(&t);
        GL_CHECK_EQ(gl_settings_decode(blob, sizeof(blob), &t), GL_ERR_RANGE);
        GL_CHECK_EQ(t.stimp_x2, 20); /* untouched on error */
        blob[field] = keep;
    }
    gl_put_u16(&blob[8], 3001);
    GL_CHECK_EQ(gl_settings_decode(blob, sizeof(blob), &t), GL_ERR_RANGE);
}

GL_TEST(test_calibration_records)
{
    /* tilt */
    {
        gl_cal_tilt_t c, d;
        uint8_t blob[GL_CAL_TILT_BLOB_LEN];
        gl_cal_tilt_defaults(&c);
        GL_CHECK_EQ(c.flags, 0);
        GL_CHECK_NEAR(c.m.m[1][1], 1.0, 0);
        c.offset_g[0] = 0.012f;
        c.tempco1_g_per_k[2] = -1.5e-4f;
        c.m.m[0][1] = 0.008f;
        c.flip_bias_y = -0.0031f;
        c.flip_time_s = 1731312000u;
        c.flags = GL_CAL_TILT_FLAG_FACTORY | GL_CAL_TILT_FLAG_FLIP;
        gl_cal_tilt_encode(&c, blob);
        GL_CHECK_EQ(blob[0], GL_CAL_VERSION);
        GL_CHECK_EQ(gl_cal_tilt_decode(blob, sizeof(blob), &d), GL_OK);
        GL_CHECK(d.offset_g[0] == c.offset_g[0] && d.m.m[0][1] == c.m.m[0][1] &&
                 d.flip_bias_y == c.flip_bias_y && d.flip_time_s == c.flip_time_s &&
                 d.flags == c.flags && d.tempco1_g_per_k[2] == c.tempco1_g_per_k[2]);
        GL_CHECK_EQ(gl_cal_tilt_decode(blob, sizeof(blob) - 1, &d), GL_ERR_PARAM);
        /* a NaN or an absurd matrix is refused */
        gl_put_f32(&blob[2], (float)NAN);
        GL_CHECK_EQ(gl_cal_tilt_decode(blob, sizeof(blob), &d), GL_ERR_RANGE);
        gl_cal_tilt_encode(&c, blob);
        gl_put_f32(&blob[2 + 36 + 4], 3.0f); /* m[0][0] */
        GL_CHECK_EQ(gl_cal_tilt_decode(blob, sizeof(blob), &d), GL_ERR_RANGE);
        blob[0] = 2;
        GL_CHECK_EQ(gl_cal_tilt_decode(blob, sizeof(blob), &d), GL_ERR_UNSUPPORTED);
    }
    /* camera */
    {
        gl_cal_cam_t c, d;
        uint8_t blob[GL_CAL_CAM_BLOB_LEN];
        gl_cal_cam_defaults(&c, 1);
        GL_CHECK_NEAR(c.pos_mm[0], 10.0, 1e-5);
        c.k1 = -0.07f;
        c.roll_rad = 0.004f;
        c.flags = GL_CAL_CAM_FLAG_INTRINSICS;
        gl_cal_cam_encode(&c, blob);
        GL_CHECK_EQ(gl_cal_cam_decode(blob, sizeof(blob), &d), GL_OK);
        GL_CHECK(d.k1 == c.k1 && d.roll_rad == c.roll_rad && d.pos_mm[0] == c.pos_mm[0] &&
                 d.fx_px == c.fx_px && d.flags == c.flags);
        gl_put_f32(&blob[2], 5000.0f); /* fx */
        GL_CHECK_EQ(gl_cal_cam_decode(blob, sizeof(blob), &d), GL_ERR_RANGE);
    }
    /* grain: covered in test_grain.c; lengths agree with what is written */
    {
        gl_cal_grain_t c;
        uint8_t blob[GL_CAL_GRAIN_BLOB_LEN + 4];
        memset(blob, 0xEE, sizeof(blob));
        gl_cal_grain_defaults(&c);
        gl_cal_grain_encode(&c, blob);
        GL_CHECK_EQ(blob[GL_CAL_GRAIN_BLOB_LEN], 0xEE); /* nothing written past the end */
    }
    {
        uint8_t blob[GL_CAL_TILT_BLOB_LEN + 4];
        gl_cal_tilt_t c;
        memset(blob, 0xEE, sizeof(blob));
        gl_cal_tilt_defaults(&c);
        gl_cal_tilt_encode(&c, blob);
        GL_CHECK_EQ(blob[GL_CAL_TILT_BLOB_LEN], 0xEE);
        GL_CHECK(blob[GL_CAL_TILT_BLOB_LEN - 1] != 0xEE || blob[GL_CAL_TILT_BLOB_LEN - 2] != 0xEE ||
                 blob[GL_CAL_TILT_BLOB_LEN - 3] != 0xEE);
    }
    {
        uint8_t blob[GL_CAL_CAM_BLOB_LEN + 4];
        gl_cal_cam_t c;
        memset(blob, 0xEE, sizeof(blob));
        gl_cal_cam_defaults(&c, 0);
        gl_cal_cam_encode(&c, blob);
        GL_CHECK_EQ(blob[GL_CAL_CAM_BLOB_LEN], 0xEE);
    }
}

GL_TEST(test_generated_config)
{
    /* values that must agree with design/master_params.yaml rev C */
    GL_CHECK(strcmp(GL_CFG_PARAMS_REV, "C-EVT1") == 0);
    GL_CHECK_NEAR(GL_CFG_CAM_F_PX, 657.0, 1e-6);
    GL_CHECK_NEAR(GL_CFG_CAM_BASELINE_MM, 20.0, 1e-5);
    GL_CHECK_NEAR(GL_CFG_CAM_AXIS_HEIGHT_MM, 5.61, 1e-5);
    GL_CHECK_NEAR(GL_CFG_CAM_RIGHT_X_MM - GL_CFG_CAM_LEFT_X_MM, GL_CFG_CAM_BASELINE_MM, 1e-5);
    /* f = efl / pixel: 1.15 mm / 1.75 um = 657 px */
    GL_CHECK_NEAR(GL_CFG_CAM_EFL_MM * 1000.0f / GL_CFG_CAM_PIXEL_UM, GL_CFG_CAM_F_PX, 0.5);
    /* horizontal field: 2 atan(320 / 657) = 51.9 deg */
    GL_CHECK_NEAR(2.0 * atan(320.0 / 657.0) * 57.29578, GL_CFG_CAM_FOV_H_DEG, 0.1);
    /* display: 23.04 mm / 128 = 0.18 mm; 22 mm aperture = 122 px */
    GL_CHECK_NEAR(GL_CFG_LCD_PIXEL_PITCH_MM, 0.18, 1e-6);
    GL_CHECK_EQ(GL_CFG_LCD_CLIP_DIA_PX, 122);
    /* ball centre 23.0 + 21.3 mm ahead of the marker centre */
    GL_CHECK_NEAR(GL_CFG_BALL_CENTRE_Y_MM, 23.0 + 21.335, 1e-4);
    GL_CHECK_NEAR(GL_CFG_BALL_CENTRE_Y_PX, 44.335 / 0.18, 0.01);
    GL_CHECK_NEAR(GL_CFG_STEREO_F_TIMES_B_PX_M, 657.0 * 0.0200, 1e-4);
    GL_CHECK_EQ(GL_CFG_GRAIN_LED_PAIRS, 8);
    /* rev C additions: camera positions, grain LED azimuths, cradle */
    GL_CHECK_NEAR(GL_CFG_CAM_LEFT_X_MM, -10.0, 1e-6);
    GL_CHECK_NEAR(GL_CFG_CAM_RIGHT_X_MM, 10.0, 1e-6);
    GL_CHECK_NEAR(GL_CFG_GRAIN_LED0_AZIMUTH_DEG, 22.5, 1e-6);
    GL_CHECK_NEAR(GL_CFG_GRAIN_LED_STEP_DEG, 45.0, 1e-6);
    GL_CHECK_EQ(GL_CFG_CRADLE_ORIENTATIONS, 1); /* one way round: no zeroing in the cradle */
    /* provisional constants exist with the documented meanings */
    GL_CHECK_EQ(GL_PROV_OV7692_REG0C_BIT_SET_MEANS_DRIVEN, 1);
    GL_CHECK_EQ(GL_PROV_LCD_FPC_PIN_SCLK, 1);
    GL_CHECK_EQ(GL_PROV_LCD_FPC_PIN_VSSA, 10);
    /* EXTCOMIN inside BOTH ranges Sharp publishes (54-65 Hz and 1-60 Hz),
     * with a 100 ppm crystal either way (546 ticks was 60.015 Hz: outside) */
    GL_CHECK(32768.0 * 1.0001 / GL_PROV_LCD_EXTCOMIN_PERIOD_LSE_TICKS <= 60.0);
    GL_CHECK(32768.0 * 0.9999 / GL_PROV_LCD_EXTCOMIN_PERIOD_LSE_TICKS >= 54.0);
    GL_CHECK_EQ(GL_PROV_LCD_EXTCOMIN_PERIOD_LSE_TICKS, 547);
    GL_CHECK(GL_PROV_GRAIN_MOD_THRESHOLD_DEFAULT > 0.2f); /* not the forbidden 0.10 */
    GL_CHECK_NEAR(GL_PROV_STICK_TOTAL_HEIGHT_M - GL_PROV_STICK_IN_CUP_M, 1.96, 1e-6);
}

GL_TEST(test_solver_is_a_stub)
{
    gl_measurements_t m;
    gl_estimate_t e;
    gl_aim_solution_t a;
    gl_solver_options_t opt;
    gl_quad_surface_t surf = { 0.01f, 0.02f, 0, 0, 0, 0 };
    gl_vec2_t p0 = { 0, 0 }, p1 = { 3, 0 }, grain = { 0, 0 };

    GL_CHECK_EQ(gl_solver_version(), 0);
    gl_solver_default_options(&opt);
    GL_CHECK_NEAR(opt.past_m, 0.30, 1e-6);
    GL_CHECK_EQ(opt.max_rolls, 200);
    gl_solver_measurements_init(&m);
    GL_CHECK_NEAR(m.f_px, 657.0, 1e-6);
    GL_CHECK_NEAR(m.baseline_m, 0.0200, 1e-7);
    GL_CHECK_NEAR(m.h_cam_m, 0.00561, 1e-7);
    GL_CHECK(!m.flag_found);
    GL_CHECK(isnan(m.user_distance_m) && isnan(m.flag_disparity_px));
    GL_CHECK_EQ(m.n_horizon, 0);
    GL_CHECK_EQ(m.tilt_reads, 1);
    /* every solving entry point says "not implemented" and marks its output */
    memset(&e, 0x55, sizeof(e));
    GL_CHECK_EQ(gl_solver_estimate(&m, &opt, &e), GL_ERR_NOT_IMPLEMENTED);
    GL_CHECK_EQ(e.solve_status, GL_SOLVE_NOT_RUN);
    GL_CHECK_NEAR(e.phi_rad, 0.0, 0);
    GL_CHECK_EQ(gl_solver_estimate_survey(&m, 1, 0, &opt, &e), GL_ERR_NOT_IMPLEMENTED);
    GL_CHECK_EQ(gl_solver_solve_aim(&surf, p0, p1, 0.549f, grain, &opt, &a),
                GL_ERR_NOT_IMPLEMENTED);
    GL_CHECK_EQ(a.status, GL_SOLVE_NOT_RUN);
    GL_CHECK_EQ(gl_solver_estimate(&m, &opt, NULL), GL_ERR_NOT_IMPLEMENTED); /* NULL is safe */
    /* status values mirror the Python reference */
    GL_CHECK_EQ(GL_SOLVE_OK, 0);
    GL_CHECK_EQ(GL_SOLVE_PACE_LIMITED, 1);
    GL_CHECK_EQ(GL_SOLVE_INVALID, 5);
    GL_CHECK_NEAR(GL_SOLVER_HOLE_RADIUS_M, 0.053975, 1e-7);
}

/* Review finding: gl_roundi(gl_clampf(x, ...)) was undefined behaviour for
 * a NaN (gl_clampf passed it through) and for values beyond the int range.
 * Runs under -fsanitize=float-cast-overflow in `make asan`. */
GL_TEST(test_clamp_and_round_are_defined_for_every_float)
{
    const float nan = (float)NAN, inf = (float)INFINITY;
    GL_CHECK_NEAR(gl_clampf(nan, -1.0f, 2.0f), -1.0, 1e-9); /* the lower bound, never NaN */
    GL_CHECK_NEAR(gl_clampf(inf, -1.0f, 2.0f), 2.0, 1e-9);
    GL_CHECK_NEAR(gl_clampf(-inf, -1.0f, 2.0f), -1.0, 1e-9);
    GL_CHECK_NEAR(gl_clampf(0.5f, -1.0f, 2.0f), 0.5, 1e-9);
    GL_CHECK_NEAR(gl_clampf(-3.0f, -1.0f, 2.0f), -1.0, 1e-9);
    GL_CHECK_EQ(gl_roundi(nan), 0);
    GL_CHECK_EQ(gl_roundi(inf), GL_ROUNDI_LIMIT);
    GL_CHECK_EQ(gl_roundi(-inf), -GL_ROUNDI_LIMIT);
    GL_CHECK_EQ(gl_roundi(3.0e9f), GL_ROUNDI_LIMIT);
    GL_CHECK_EQ(gl_roundi(-3.0e9f), -GL_ROUNDI_LIMIT);
    GL_CHECK_EQ(gl_roundi(3.4e38f), GL_ROUNDI_LIMIT);
    GL_CHECK_EQ(gl_roundi(2.5f), 3);
    GL_CHECK_EQ(gl_roundi(-2.5f), -3);
    GL_CHECK_EQ(gl_roundi(0.49f), 0);
    GL_CHECK_EQ(gl_roundi(1.0e9f), 1000000000);
    GL_CHECK_EQ(gl_roundi(gl_clampf(nan, 0.0f, 1.0f) * 5.0f), 0); /* the pattern of gl_ui.c */
}

/* Review finding (STM32 backend, found by inspection): the application
 * calls gl_lcd_off() - and with it gl_hal_extcomin_stop() - at every boot
 * before the timer was ever started, which on the target ran the HAL's
 * de-initialisation on a zeroed handle (NULL Instance).  gl_hal.h now
 * REQUIRES every stop / disable call to be safe before the matching start;
 * this test calls each of them first, on the host backend, and then checks
 * that the drivers' own "off" entry points do nothing else.  (The target
 * backend carries the matching guards; it is not compiled here.) */
GL_TEST(test_every_stop_is_safe_before_its_start)
{
    gl_lcd_t lcd;
    gl_sim_reset(true);
    GL_CHECK_EQ(gl_hal_init(), GL_OK);
    /* straight after init, in every order */
    for (int pass = 0; pass < 2; pass++) {
        gl_hal_extcomin_stop();
        gl_hal_dcmi_stop();
        gl_hal_xvclk_stop();
        gl_hal_usb_stop();
        GL_CHECK_EQ(gl_hal_adc_power(false), GL_OK);
        GL_CHECK_EQ(gl_hal_opamp_enable(false), GL_OK);
        gl_hal_wake_timer_start(0);
        GL_CHECK_EQ(gl_hal_dcmi_poll(NULL), GL_DCMI_IDLE);
    }
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
    /* what the application does at boot */
    gl_lcd_init(&lcd, NULL);
    gl_lcd_off(&lcd);
    gl_grain_fe_all_off();
    GL_CHECK(!gl_sim_lcd()->extcomin && !gl_sim_lcd()->disp);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
    /* and stop after a real start still stops */
    GL_CHECK_EQ(gl_lcd_on(&lcd), GL_OK);
    GL_CHECK(gl_sim_lcd()->extcomin);
    gl_lcd_off(&lcd);
    gl_lcd_off(&lcd); /* twice */
    GL_CHECK(!gl_sim_lcd()->extcomin);
    GL_CHECK_EQ(gl_hal_opamp_enable(true), GL_OK);
    GL_CHECK_EQ(gl_hal_opamp_enable(false), GL_OK);
    GL_CHECK_EQ(gl_hal_opamp_enable(false), GL_OK);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

int main(void)
{
    GL_RUN(test_clamp_and_round_are_defined_for_every_float);
    GL_RUN(test_every_stop_is_safe_before_its_start);
    GL_RUN(test_math_helpers);
    GL_RUN(test_number_formatting);
    GL_RUN(test_event_queue);
    GL_RUN(test_settings);
    GL_RUN(test_calibration_records);
    GL_RUN(test_generated_config);
    GL_RUN(test_solver_is_a_stub);
    return gl_test_summary();
}
