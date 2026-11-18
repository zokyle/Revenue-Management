/*
 * test_fieldlog.c - the replay records of the field log (core/gl_fieldlog):
 * sizes, limits and the offset of every kind of field.  The records are
 * checked against the application's own values, bit for bit, in
 * tests/test_factory.c, and against the Python decoder and the reference
 * estimator by `make tooltest`.
 */
#include <math.h>
#include <string.h>

#include "gl_buf.h"
#include "gl_fieldlog.h"
#include "gl_log.h"
#include "gl_proto.h"
#include "gl_test.h"

GL_TEST(test_sizes_and_limits)
{
    /* every record fits one LOG_READ response (1014 bytes of payload) and
     * one 4 kB sector, and is a multiple of 4 (no padding on flash) */
    GL_CHECK_EQ(GL_FIELDLOG_MEAS_FIXED, 68);
    GL_CHECK_EQ(GL_FIELDLOG_MEAS_MAX, 396);
    GL_CHECK_EQ(GL_FIELDLOG_READ_LEN, 684);
    GL_CHECK_EQ(GL_FIELDLOG_TILT_LEN, 80);
    GL_CHECK(GL_FIELDLOG_READ_LEN <= GL_PROTO_MAX_PAYLOAD - 2u - 8u);
    GL_CHECK(GL_FIELDLOG_READ_LEN <= GL_LOG_MAX_PAYLOAD(4096u));
    GL_CHECK_EQ(GL_FIELDLOG_READ_LEN % 4u, 0u);
    GL_CHECK_EQ(GL_FIELDLOG_MEAS_MAX % 4u, 0u);
    GL_CHECK_EQ(GL_FIELDLOG_TILT_LEN % 4u, 0u);
    GL_CHECK_EQ(GL_LOG_REC_MEAS, 5);
    GL_CHECK_EQ(GL_LOG_REC_READ2, 6);
    GL_CHECK_EQ(GL_LOG_REC_TILT, 7);
}

GL_TEST(test_placement_record)
{
    static uint8_t buf[GL_FIELDLOG_MEAS_MAX + 8];
    gl_measurements_t m;
    size_t n;

    gl_solver_measurements_init(&m);
    /* "nothing measured": 68 bytes, NaN where the estimator takes NaN */
    memset(buf, 0xEE, sizeof(buf));
    n = gl_fieldlog_meas_encode(0x1234, 2, 3, false, &m, buf, sizeof(buf));
    GL_CHECK_EQ(n, 68u);
    GL_CHECK_EQ(buf[68], 0xEE);
    GL_CHECK_EQ(gl_get_u16(&buf[0]), 0x1234);
    GL_CHECK_EQ(buf[2], 2);
    GL_CHECK_EQ(buf[3], 3);
    GL_CHECK_EQ(buf[4], 0);
    GL_CHECK_EQ(buf[6], 0);
    GL_CHECK_EQ(buf[7], GL_FIELDLOG_LAYOUT);
    GL_CHECK(isnan(gl_get_f32(&buf[28])) && isnan(gl_get_f32(&buf[32])) && isnan(gl_get_f32(&buf[36])));
    GL_CHECK_MEM(&buf[8], &m.f_px, 4);
    GL_CHECK_MEM(&buf[12], &m.baseline_m, 4);
    /* everything measured, 41 horizon samples of which some are invalid */
    m.flag_found = true;
    m.flag_base_visible = true;
    m.flag_top_visible = true;
    m.tilt_reads = 2;
    m.tilt_x = 0.0123f;
    m.tilt_y = -0.0201f;
    m.flag_bearing_rad = 0.05f;
    m.flag_disparity_px = 2.19f;
    m.flag_low_elev_rad = -0.004f;
    m.flag_top_elev_rad = 0.31f;
    m.stick_height_est_m = 1.96f;
    m.stick_height_rel_sigma = 0.08f;
    m.grain_kappa = 0.03f;
    m.grain_azimuth_rad = 1.1f;
    m.stimp_ft = 10.5f;
    m.user_distance_m = 4.5f;
    m.n_horizon = 41;
    for (unsigned i = 0; i < 41u; i++) {
        m.horizon_az_rad[i] = -0.4f + 0.02f * (float)i;
        m.horizon_elev_rad[i] = ((i % 7u) == 3u) ? (float)NAN : 0.001f * (float)i;
    }
    memset(buf, 0xEE, sizeof(buf));
    n = gl_fieldlog_meas_encode(7, 0, 1, true, &m, buf, sizeof(buf));
    GL_CHECK_EQ(n, 396u);
    GL_CHECK_EQ(buf[396], 0xEE);
    GL_CHECK_EQ(buf[4], 0x0F);
    GL_CHECK_EQ(buf[5], 2);
    GL_CHECK_EQ(buf[6], 41);
    GL_CHECK_MEM(&buf[20], &m.tilt_x, 4);
    GL_CHECK_MEM(&buf[24], &m.tilt_y, 4);
    GL_CHECK_MEM(&buf[28], &m.flag_bearing_rad, 4);
    GL_CHECK_MEM(&buf[32], &m.flag_disparity_px, 4);
    GL_CHECK_MEM(&buf[36], &m.flag_low_elev_rad, 4);
    GL_CHECK_MEM(&buf[40], &m.flag_top_elev_rad, 4);
    GL_CHECK_MEM(&buf[44], &m.stick_height_est_m, 4);
    GL_CHECK_MEM(&buf[48], &m.stick_height_rel_sigma, 4);
    GL_CHECK_MEM(&buf[52], &m.grain_kappa, 4);
    GL_CHECK_MEM(&buf[56], &m.grain_azimuth_rad, 4);
    GL_CHECK_MEM(&buf[60], &m.stimp_ft, 4);
    GL_CHECK_MEM(&buf[64], &m.user_distance_m, 4);
    GL_CHECK_MEM(&buf[68 + 8 * 40], &m.horizon_az_rad[40], 4);
    GL_CHECK_MEM(&buf[72 + 8 * 40], &m.horizon_elev_rad[40], 4);
    GL_CHECK(isnan(gl_get_f32(&buf[72 + 8 * 3])));
    /* a buffer that is too small, or none: nothing is written */
    memset(buf, 0xEE, sizeof(buf));
    GL_CHECK_EQ(gl_fieldlog_meas_encode(7, 0, 1, true, &m, buf, 395), 0u);
    GL_CHECK_EQ(buf[0], 0xEE);
    GL_CHECK_EQ(gl_fieldlog_meas_encode(7, 0, 1, true, &m, NULL, 500), 0u);
    /* a count beyond the arrays is clamped, not followed off their end */
    m.n_horizon = 200;
    n = gl_fieldlog_meas_encode(7, 0, 1, true, &m, buf, sizeof(buf));
    GL_CHECK_EQ(n, 396u);
    GL_CHECK_EQ(buf[6], 41);
}

GL_TEST(test_read_record_sections)
{
    static uint8_t buf[GL_FIELDLOG_READ_LEN + 8];
    gl_fieldlog_ctx_t c;
    gl_solver_options_t opt;
    gl_estimate_t e;
    gl_patch_fit_t f;

    memset(&c, 0, sizeof(c));
    memset(&e, 0, sizeof(e));
    memset(&f, 0, sizeof(f));
    gl_solver_default_options(&opt);
    c.read_id = 0xBEEF;
    c.rtc_s = 0x65432100u;
    c.tick_ms = 123456u;
    c.fw_version = 0x0003;
    c.flags = 0x0155;
    c.hw_rev = 5;
    c.cal_version = 2;
    c.cal_crc[4] = 0xA55A;
    c.settings[11] = 2;
    c.seat = 1;
    c.slope.x = 0.012f;
    c.up.z = 0.9997f;
    c.tilt_scatter = 1.4e-4f;
    c.imu_temp_c_x100 = -1234;
    c.cell_temp_c_x10 = INT16_MIN;
    c.batt_mv = 3987;
    c.grain_signal[15] = 4321;
    c.quality[4] = 1;
    c.tilt_blocks = 8;
    c.stage_ms[GL_FIELDLOG_T_SOLVE_DONE] = 3620;
    c.cam_on_ms = 2424;
    c.display_rot_rad = 0.0209f;
    opt.max_steps = 300000u;
    opt.near_miss_m = 0.005f;
    opt.method = 2;
    opt.use_grain = true;
    e.phi_rad = 0.0107f;
    e.distance_sigma_m = (float)NAN;
    e.patch[4] = -0.0011f;
    e.grain_y = 0.02f;
    e.n_steps = 1017;
    e.n_rolls = 9;
    e.aim_source = 1;
    e.solve_status = 3;
    e.fit_converged = true;
    f.coeffs[0] = -0.0205f;
    f.cov[4][4] = 2.5e-7f;
    f.range.sigma_mono_m = 0.4f;
    f.stations_m[3] = 9.0f;
    f.cost_first_start = 1.25f;
    f.n_iter = 17;
    f.n_drops = 4;
    f.n_starts = 5;
    f.converged = true;

    memset(buf, 0xEE, sizeof(buf));
    GL_CHECK_EQ(gl_fieldlog_read_encode(&c, &opt, &e, &f, buf, sizeof(buf)), GL_FIELDLOG_READ_LEN);
    GL_CHECK_EQ(buf[GL_FIELDLOG_READ_LEN], 0xEE);
    /* context */
    GL_CHECK_EQ(buf[0], GL_FIELDLOG_LAYOUT);
    GL_CHECK_EQ(buf[1], 5);
    GL_CHECK_EQ(gl_get_u16(&buf[2]), 0xBEEF);
    GL_CHECK_EQ(gl_get_u32(&buf[4]), 0x65432100u);
    GL_CHECK_EQ(gl_get_u32(&buf[8]), 123456u);
    GL_CHECK_EQ(gl_get_u16(&buf[12]), 3);
    GL_CHECK_EQ(gl_get_u16(&buf[14]), 0x0155);
    GL_CHECK_EQ(buf[24], 2);
    GL_CHECK_EQ(gl_get_u16(&buf[38]), 0xA55A);
    GL_CHECK_EQ(buf[51], 2);
    GL_CHECK_EQ(buf[57], 1);
    GL_CHECK_MEM(&buf[68], &c.slope.x, 4);
    GL_CHECK_MEM(&buf[112], &c.up.z, 4);
    GL_CHECK_MEM(&buf[128], &c.tilt_scatter, 4);
    GL_CHECK_EQ((int16_t)gl_get_u16(&buf[136]), -1234);
    GL_CHECK_EQ((int16_t)gl_get_u16(&buf[138]), INT16_MIN);
    GL_CHECK_EQ(gl_get_u16(&buf[142]), 3987);
    GL_CHECK_EQ(gl_get_u16(&buf[190]), 4321);
    GL_CHECK_EQ(buf[232], 1);
    GL_CHECK_EQ(buf[234], 8);
    GL_CHECK_EQ(gl_get_u16(&buf[244]), 3620);
    GL_CHECK_EQ(gl_get_u16(&buf[246]), 2424);
    GL_CHECK_MEM(&buf[256], &c.display_rot_rad, 4);
    /* options */
    GL_CHECK_MEM(&buf[264], &opt.past_m, 4);
    GL_CHECK_MEM(&buf[268], &opt.tol_miss_m, 4);
    GL_CHECK_MEM(&buf[280], &opt.near_miss_m, 4);
    GL_CHECK_EQ(gl_get_u32(&buf[284]), 300000u);
    GL_CHECK_EQ(gl_get_u16(&buf[288]), opt.max_rolls);
    GL_CHECK_EQ(gl_get_u16(&buf[290]), opt.lm_max_iter);
    GL_CHECK_EQ(buf[292], 2);
    GL_CHECK_EQ(buf[293], 1);
    /* estimate */
    GL_CHECK_MEM(&buf[296], &e.phi_rad, 4);
    GL_CHECK(isnan(gl_get_f32(&buf[324])));
    GL_CHECK_MEM(&buf[364], &e.patch[4], 4);
    GL_CHECK_MEM(&buf[388], &e.grain_y, 4);
    GL_CHECK_EQ(gl_get_u32(&buf[392]), 1017u);
    GL_CHECK_EQ(gl_get_u16(&buf[396]), 9);
    GL_CHECK_EQ(buf[398], 1);
    GL_CHECK_EQ(buf[399], 3);
    GL_CHECK_EQ(buf[404], 1);
    /* fit */
    GL_CHECK_MEM(&buf[412], &f.coeffs[0], 4);
    GL_CHECK_MEM(&buf[432 + 4 * 24], &f.cov[4][4], 4);
    GL_CHECK_MEM(&buf[572], &f.range.sigma_mono_m, 4);
    GL_CHECK_MEM(&buf[600], &f.stations_m[3], 4);
    GL_CHECK_MEM(&buf[612], &f.cost_first_start, 4);
    GL_CHECK_EQ(gl_get_u16(&buf[616]), 17);
    GL_CHECK_EQ(buf[618], 4);
    GL_CHECK_EQ(buf[619], 5);
    GL_CHECK_EQ(buf[625], 1);
    /* the reserved tail is zero */
    for (unsigned i = 626; i < GL_FIELDLOG_READ_LEN; i++) {
        GL_CHECK_EQ(buf[i], 0);
    }
    /* too small a buffer: nothing */
    memset(buf, 0xEE, sizeof(buf));
    GL_CHECK_EQ(gl_fieldlog_read_encode(&c, &opt, &e, &f, buf, GL_FIELDLOG_READ_LEN - 1u), 0u);
    GL_CHECK_EQ(buf[0], 0xEE);
}

GL_TEST(test_tilt_record)
{
    uint8_t buf[GL_FIELDLOG_TILT_LEN + 4];
    gl_fieldlog_tilt_t t;
    memset(&t, 0, sizeof(t));
    t.kind = GL_FIELDLOG_TILT_ZERO_2;
    t.seat = 1;
    t.read_id = 77;
    t.rtc_s = 1790000000u;
    t.tick_ms = 987654u;
    t.slope_raw.x = 0.0155f;
    t.slope.y = -0.02f;
    t.accel_g.z = 0.9998f;
    t.gyro_bias.x = 0.004f;
    t.tilt_scatter = 1.2e-4f;
    t.accel_noise_g = 8e-4f;
    t.yaw_rad = 3.13f;
    t.imu_temp_c_x100 = 2204;
    t.cell_temp_c_x10 = 221;
    t.mcu_temp_c_x10 = INT16_MIN;
    t.batt_mv = 3901;
    t.cal_tilt_crc = 0xC0DE;
    t.cal_tilt_flags = 0x07;
    t.tilt_blocks = 8;
    memset(buf, 0xEE, sizeof(buf));
    gl_fieldlog_tilt_encode(&t, buf);
    GL_CHECK_EQ(buf[GL_FIELDLOG_TILT_LEN], 0xEE);
    GL_CHECK_EQ(buf[0], GL_FIELDLOG_LAYOUT);
    GL_CHECK_EQ(buf[1], GL_FIELDLOG_TILT_ZERO_2);
    GL_CHECK_EQ(gl_get_u16(&buf[2]), 77);
    GL_CHECK_EQ(gl_get_u32(&buf[4]), 1790000000u);
    GL_CHECK_EQ(gl_get_u32(&buf[8]), 987654u);
    GL_CHECK_MEM(&buf[12], &t.slope_raw.x, 4);
    GL_CHECK_MEM(&buf[24], &t.slope.y, 4);
    GL_CHECK_MEM(&buf[36], &t.accel_g.z, 4);
    GL_CHECK_MEM(&buf[40], &t.gyro_bias.x, 4);
    GL_CHECK_MEM(&buf[52], &t.tilt_scatter, 4);
    GL_CHECK_MEM(&buf[56], &t.accel_noise_g, 4);
    GL_CHECK_MEM(&buf[60], &t.yaw_rad, 4);
    GL_CHECK_EQ((int16_t)gl_get_u16(&buf[64]), 2204);
    GL_CHECK_EQ((int16_t)gl_get_u16(&buf[66]), 221);
    GL_CHECK_EQ((int16_t)gl_get_u16(&buf[68]), INT16_MIN);
    GL_CHECK_EQ(gl_get_u16(&buf[70]), 3901);
    GL_CHECK_EQ(gl_get_u16(&buf[72]), 0xC0DE);
    GL_CHECK_EQ(buf[74], 0x07);
    GL_CHECK_EQ(buf[75], 8);
    GL_CHECK_EQ(buf[76], 1);
    GL_CHECK_EQ(buf[77] | buf[78] | buf[79], 0);
}

int main(void)
{
    GL_RUN(test_sizes_and_limits);
    GL_RUN(test_placement_record);
    GL_RUN(test_read_record_sections);
    GL_RUN(test_tilt_record);
    return gl_test_summary();
}
