/*
 * test_cal.c - calibration records of version 2 (phase 3): the CRC, the
 * migration of version-1 records byte for byte as phase 2 wrote them, the
 * two level zeros of DESIGN_SPEC E11 and the rule that picks one, the
 * camera horizon row, the device record (display rotation, serial number).
 */
#include <math.h>
#include <string.h>

#include "gl_buf.h"
#include "gl_cal.h"
#include "gl_cam.h"
#include "gl_config.h"
#include "gl_crc.h"
#include "gl_log.h"
#include "gl_test.h"

static void reseal_(uint8_t *blob, size_t len)
{
    gl_put_u16(&blob[len - 2u], gl_crc16(blob, len - 2u));
}

/* A version-1 tilt record written field by field from the phase-2 layout
 * (NOT with the present encoder): version, flags, offset[3], tempco1[3],
 * tempco2[3], t0, m[9], flip x, flip y, flip temperature, flip time. */
static void tilt_v1_(uint8_t out[GL_CAL_TILT_BLOB_LEN_V1], uint8_t flags, float tc1z)
{
    size_t p = 0;
    out[p++] = 1;
    out[p++] = flags;
    gl_put_f32(&out[p], 0.011f); p += 4;
    gl_put_f32(&out[p], -0.004f); p += 4;
    gl_put_f32(&out[p], 0.021f); p += 4;
    gl_put_f32(&out[p], 0.0f); p += 4;
    gl_put_f32(&out[p], 0.0f); p += 4;
    gl_put_f32(&out[p], tc1z); p += 4;
    for (int i = 0; i < 3; i++) {
        gl_put_f32(&out[p], 0.0f); p += 4;
    }
    gl_put_f32(&out[p], 23.5f); p += 4;
    for (int i = 0; i < 3; i++) {
        for (int j = 0; j < 3; j++) {
            gl_put_f32(&out[p], (i == j) ? 1.002f : 0.003f); p += 4;
        }
    }
    gl_put_f32(&out[p], 0.0035f); p += 4;
    gl_put_f32(&out[p], -0.0025f); p += 4;
    gl_put_f32(&out[p], 21.0f); p += 4;
    gl_put_u32(&out[p], 1731312000u); p += 4;
    GL_CHECK_EQ(p, GL_CAL_TILT_BLOB_LEN_V1);
}

GL_TEST(test_lengths_and_crc_of_every_record)
{
    uint8_t blob[GL_CAL_MAX_BLOB_LEN + 4];
    gl_cal_tilt_t t, t2;
    gl_cal_cam_t c, c2;
    gl_cal_grain_t g, g2;
    gl_cal_device_t d, d2;

    GL_CHECK_EQ(GL_CAL_VERSION, 2);
    GL_CHECK_EQ(GL_CAL_TILT_BLOB_LEN, 120);
    GL_CHECK_EQ(GL_CAL_CAM_BLOB_LEN, 52);
    GL_CHECK_EQ(GL_CAL_GRAIN_BLOB_LEN, 82);
    GL_CHECK_EQ(GL_CAL_DEVICE_BLOB_LEN, 28);
    GL_CHECK(GL_CAL_MAX_BLOB_LEN >= GL_CAL_TILT_BLOB_LEN);
    GL_CHECK(GL_CAL_MAX_BLOB_LEN <= GL_STORE_MAX_ITEM_LEN); /* every record fits a store item */

    /* tilt: every byte before the CRC is covered - flip each bit in turn */
    gl_cal_tilt_defaults(&t);
    t.base_bias_x = 0.0012f;
    t.base_bias_y = -0.0007f;
    t.base_temp_c = 22.5f;
    t.base_time_s = 1790000000u;
    t.base_scatter = 0.00011f;
    t.flip_scatter = 0.00009f;
    t.flags = GL_CAL_TILT_FLAG_ALL;
    memset(blob, 0xEE, sizeof(blob));
    gl_cal_tilt_encode(&t, blob);
    GL_CHECK_EQ(blob[GL_CAL_TILT_BLOB_LEN], 0xEE);
    GL_CHECK_EQ(gl_cal_tilt_decode(blob, GL_CAL_TILT_BLOB_LEN, &t2), GL_OK);
    GL_CHECK(t2.base_bias_x == t.base_bias_x && t2.base_bias_y == t.base_bias_y &&
             t2.base_temp_c == t.base_temp_c && t2.base_time_s == t.base_time_s &&
             t2.base_scatter == t.base_scatter && t2.flip_scatter == t.flip_scatter &&
             t2.flags == t.flags);
    {
        unsigned refused = 0, by_crc = 0;
        for (unsigned bit = 0; bit < 8u * GL_CAL_TILT_BLOB_LEN; bit++) {
            gl_status_t st;
            blob[bit / 8u] ^= (uint8_t)(1u << (bit % 8u));
            st = gl_cal_tilt_decode(blob, GL_CAL_TILT_BLOB_LEN, &t2);
            refused += (st != GL_OK) ? 1u : 0u;
            by_crc += (st == GL_ERR_CRC) ? 1u : 0u;
            blob[bit / 8u] ^= (uint8_t)(1u << (bit % 8u));
        }
        printf("    tilt record, each of its %u bits flipped in turn: %u refused (%u by the CRC, "
               "the rest by the version byte)\n", 8u * GL_CAL_TILT_BLOB_LEN, refused, by_crc);
        GL_CHECK_EQ(refused, 8u * GL_CAL_TILT_BLOB_LEN);
        GL_CHECK(by_crc >= 8u * (GL_CAL_TILT_BLOB_LEN - 1u) - 2u);
    }
    GL_CHECK_EQ(gl_cal_tilt_decode(blob, GL_CAL_TILT_BLOB_LEN - 1u, &t2), GL_ERR_PARAM);
    GL_CHECK_EQ(gl_cal_tilt_decode(NULL, GL_CAL_TILT_BLOB_LEN, &t2), GL_ERR_PARAM);
    /* an unknown flag bit, with a correct CRC, is refused by the range check */
    blob[1] |= 0x80u;
    reseal_(blob, GL_CAL_TILT_BLOB_LEN);
    GL_CHECK_EQ(gl_cal_tilt_decode(blob, GL_CAL_TILT_BLOB_LEN, &t2), GL_ERR_RANGE);

    /* camera */
    gl_cal_cam_defaults(&c, 0);
    GL_CHECK_NEAR(c.horizon_row, 239.5, 1e-6);
    c.horizon_row = 251.25f;
    c.flags = GL_CAL_CAM_FLAG_ALL;
    memset(blob, 0xEE, sizeof(blob));
    gl_cal_cam_encode(&c, blob);
    GL_CHECK_EQ(blob[GL_CAL_CAM_BLOB_LEN], 0xEE);
    GL_CHECK_EQ(gl_cal_cam_decode(blob, GL_CAL_CAM_BLOB_LEN, &c2), GL_OK);
    GL_CHECK(c2.horizon_row == c.horizon_row && c2.flags == c.flags);
    blob[10] ^= 1u;
    GL_CHECK_EQ(gl_cal_cam_decode(blob, GL_CAL_CAM_BLOB_LEN, &c2), GL_ERR_CRC);

    /* grain */
    gl_cal_grain_defaults(&g);
    g.pd_dark_counts = 412;
    g.flags = GL_CAL_GRAIN_FLAG_ALL;
    memset(blob, 0xEE, sizeof(blob));
    gl_cal_grain_encode(&g, blob);
    GL_CHECK_EQ(blob[GL_CAL_GRAIN_BLOB_LEN], 0xEE);
    GL_CHECK_EQ(gl_cal_grain_decode(blob, GL_CAL_GRAIN_BLOB_LEN, &g2), GL_OK);
    GL_CHECK(g2.pd_dark_counts == 412 && g2.flags == g.flags);
    blob[79] ^= 4u;
    GL_CHECK_EQ(gl_cal_grain_decode(blob, GL_CAL_GRAIN_BLOB_LEN, &g2), GL_ERR_CRC);

    /* device */
    gl_cal_device_defaults(&d);
    GL_CHECK_EQ(d.flags, 0);
    GL_CHECK_NEAR(d.display_rot_rad, 0.0, 0.0);
    d.display_rot_rad = -0.0209f;
    for (unsigned i = 0; i < 12u; i++) {
        d.unique_id[i] = (uint8_t)(0x31u + 7u * i);
    }
    d.serial = gl_cal_serial_from_uid(d.unique_id);
    d.time_s = 1790001234u;
    d.flags = GL_CAL_DEV_FLAG_ALL;
    memset(blob, 0xEE, sizeof(blob));
    gl_cal_device_encode(&d, blob);
    GL_CHECK_EQ(blob[GL_CAL_DEVICE_BLOB_LEN], 0xEE);
    GL_CHECK_EQ(gl_cal_device_decode(blob, GL_CAL_DEVICE_BLOB_LEN, &d2), GL_OK);
    GL_CHECK(d2.display_rot_rad == d.display_rot_rad && d2.serial == d.serial &&
             d2.time_s == d.time_s && d2.flags == d.flags &&
             memcmp(d2.unique_id, d.unique_id, 12) == 0);
    /* a rotation beyond 2 degrees is refused; so is a serial that is not
     * the one of the unique number beside it; so is a version-1 "device" */
    gl_put_f32(&blob[2], 0.05f);
    reseal_(blob, GL_CAL_DEVICE_BLOB_LEN);
    GL_CHECK_EQ(gl_cal_device_decode(blob, GL_CAL_DEVICE_BLOB_LEN, &d2), GL_ERR_RANGE);
    gl_cal_device_encode(&d, blob);
    blob[6] ^= 1u; /* first byte of the unique number */
    reseal_(blob, GL_CAL_DEVICE_BLOB_LEN);
    GL_CHECK_EQ(gl_cal_device_decode(blob, GL_CAL_DEVICE_BLOB_LEN, &d2), GL_ERR_RANGE);
    gl_cal_device_encode(&d, blob);
    blob[0] = 1;
    GL_CHECK_EQ(gl_cal_device_decode(blob, GL_CAL_DEVICE_BLOB_LEN, &d2), GL_ERR_UNSUPPORTED);
}

GL_TEST(test_version_1_records_are_migrated)
{
    uint8_t v1[GL_CAL_TILT_BLOB_LEN_V1];
    uint8_t v2[GL_CAL_TILT_BLOB_LEN];
    gl_cal_tilt_t t, u;
    gl_vec2_t zero;

    /* tilt: factory + user zero, one temperature term */
    tilt_v1_(v1, 0x03, -1.5e-4f);
    gl_cal_tilt_defaults(&t);
    GL_CHECK_EQ(gl_cal_tilt_decode(v1, sizeof(v1), &t), GL_OK);
    GL_CHECK_NEAR(t.offset_g[0], 0.011, 1e-9);
    GL_CHECK_NEAR(t.offset_g[2], 0.021, 1e-9);
    GL_CHECK_NEAR(t.tempco1_g_per_k[2], -1.5e-4, 1e-10);
    GL_CHECK_NEAR(t.t0_c, 23.5, 1e-6);
    GL_CHECK_NEAR(t.m.m[1][1], 1.002, 1e-6);
    GL_CHECK_NEAR(t.m.m[2][0], 0.003, 1e-7);
    /* the one zero of version 1 is the BALL-seat zero; there is no
     * base-face zero; the temperature flag is read off the terms */
    GL_CHECK_NEAR(t.flip_bias_x, 0.0035, 1e-9);
    GL_CHECK_NEAR(t.flip_bias_y, -0.0025, 1e-9);
    GL_CHECK_NEAR(t.flip_temp_c, 21.0, 1e-6);
    GL_CHECK_EQ(t.flip_time_s, 1731312000u);
    GL_CHECK_EQ(t.flags, GL_CAL_TILT_FLAG_FACTORY | GL_CAL_TILT_FLAG_FLIP | GL_CAL_TILT_FLAG_TEMPCO);
    GL_CHECK_NEAR(t.base_bias_x, 0.0, 0.0);
    GL_CHECK_NEAR(t.flip_scatter, 0.0, 0.0);
    /* a read on turf (the default) falls back on the only zero there is */
    GL_CHECK_EQ(gl_cal_tilt_zero(&t, GL_CAL_SEAT_BASE, &zero), GL_CAL_SEAT_BALL);
    GL_CHECK_NEAR(zero.x, 0.0035, 1e-9);
    GL_CHECK_NEAR(zero.y, -0.0025, 1e-9);
    /* short by one byte: refused; stored again it is a version-2 record */
    GL_CHECK_EQ(gl_cal_tilt_decode(v1, sizeof(v1) - 1u, &u), GL_ERR_PARAM);
    gl_cal_tilt_encode(&t, v2);
    GL_CHECK_EQ(v2[0], 2);
    GL_CHECK_EQ(gl_cal_tilt_decode(v2, sizeof(v2), &u), GL_OK);
    GL_CHECK(u.flip_bias_x == t.flip_bias_x && u.flags == t.flags && u.t0_c == t.t0_c);
    /* the first 94 bytes of the new record are the old layout (but for the
     * version byte and the migrated flag) */
    GL_CHECK_MEM(&v2[2], &v1[2], GL_CAL_TILT_BLOB_LEN_V1 - 2u);
    /* version-1 flag bits that did not exist then are dropped, not adopted */
    tilt_v1_(v1, 0xFF, 0.0f);
    GL_CHECK_EQ(gl_cal_tilt_decode(v1, sizeof(v1), &t), GL_OK);
    GL_CHECK_EQ(t.flags, GL_CAL_TILT_FLAG_FACTORY | GL_CAL_TILT_FLAG_FLIP);
    /* a version-1 record with an absurd field is still refused */
    tilt_v1_(v1, 0x01, 0.0f);
    gl_put_f32(&v1[2], 7.0f);
    GL_CHECK_EQ(gl_cal_tilt_decode(v1, sizeof(v1), &t), GL_ERR_RANGE);

    /* camera: 46 bytes of version 1 */
    {
        uint8_t c1[GL_CAL_CAM_BLOB_LEN_V1];
        const float f[11] = { 661.0f, 659.0f, 322.0f, 236.5f, -0.05f, 0.01f, -0.004f, 0.002f,
                              -10.0f, 16.6f, 3.2f };
        gl_cal_cam_t c;
        c1[0] = 1;
        c1[1] = 0xFF;
        for (int i = 0; i < 11; i++) {
            gl_put_f32(&c1[2 + 4 * i], f[i]);
        }
        GL_CHECK_EQ(gl_cal_cam_decode(c1, sizeof(c1), &c), GL_OK);
        GL_CHECK_EQ(c.flags, GL_CAL_CAM_FLAG_INTRINSICS | GL_CAL_CAM_FLAG_EXTRINSICS);
        GL_CHECK_NEAR(c.fy_px, 659.0, 1e-4);
        GL_CHECK_NEAR(c.pitch_up_rad, 0.01, 1e-8);
        /* the horizon row is the one the stored pitch implies */
        GL_CHECK_NEAR(c.horizon_row, 236.5 + 659.0 * tan(0.01), 1e-3);
        GL_CHECK_EQ(gl_cal_cam_decode(c1, sizeof(c1) - 1u, &c), GL_ERR_PARAM);
    }
    /* grain: 78 bytes of version 1 */
    {
        uint8_t g1[GL_CAL_GRAIN_BLOB_LEN_V1];
        gl_cal_grain_t g;
        g1[0] = 1;
        g1[1] = 0x03;
        for (int i = 0; i < 16; i++) {
            gl_put_f32(&g1[2 + 4 * i], 1.0f + 0.01f * (float)i);
        }
        gl_put_f32(&g1[66], 0.31f);
        gl_put_f32(&g1[70], 0.07f);
        gl_put_u16(&g1[74], 210);
        gl_put_u16(&g1[76], 44);
        GL_CHECK_EQ(gl_cal_grain_decode(g1, sizeof(g1), &g), GL_OK);
        GL_CHECK_NEAR(g.gain[15], 1.15, 1e-6);
        GL_CHECK_NEAR(g.mod_threshold, 0.31, 1e-7);
        GL_CHECK_EQ(g.min_signal_counts, 210);
        GL_CHECK_EQ(g.max_dark_drift_counts, 44);
        GL_CHECK_EQ(g.flags, GL_CAL_GRAIN_FLAG_WHITE_REF | GL_CAL_GRAIN_FLAG_NOISE_FLOOR);
        GL_CHECK_EQ(g.pd_dark_counts, 0);
    }
}

GL_TEST(test_two_level_zeros_and_the_rule_that_picks_one)
{
    gl_cal_tilt_t t;
    gl_vec2_t z;
    const gl_vec2_t ball = { 0.0031f, -0.0012f }, base = { 0.0020f, -0.0002f };
    const gl_vec2_t ball2 = { 0.0035f, -0.0015f };

    gl_cal_tilt_defaults(&t);
    /* nothing stored: zero, and it says so */
    z.x = z.y = 9.0f;
    GL_CHECK_EQ(gl_cal_tilt_zero(&t, GL_CAL_SEAT_BASE, &z), GL_CAL_SEAT_NONE);
    GL_CHECK(z.x == 0.0f && z.y == 0.0f);
    GL_CHECK_EQ(gl_cal_tilt_zero(NULL, GL_CAL_SEAT_BALL, &z), GL_CAL_SEAT_NONE);
    /* factory: ball seat, then base face */
    gl_cal_tilt_set_zero(&t, GL_CAL_SEAT_BALL, ball, 22.0f, 100u, 0.0001f);
    GL_CHECK_EQ(t.flags, GL_CAL_TILT_FLAG_FLIP);
    GL_CHECK_EQ(gl_cal_tilt_zero(&t, GL_CAL_SEAT_BASE, &z), GL_CAL_SEAT_BALL); /* the only one */
    gl_cal_tilt_set_zero(&t, GL_CAL_SEAT_BASE, base, 22.5f, 200u, 0.0002f);
    GL_CHECK_EQ(t.flags, GL_CAL_TILT_FLAG_FLIP | GL_CAL_TILT_FLAG_BASE);
    /* the default for a read is the base face; the setting selects the ball seat */
    GL_CHECK_EQ(gl_cal_tilt_zero(&t, GL_CAL_SEAT_BASE, &z), GL_CAL_SEAT_BASE);
    GL_CHECK(z.x == base.x && z.y == base.y);
    GL_CHECK_EQ(gl_cal_tilt_zero(&t, GL_CAL_SEAT_BALL, &z), GL_CAL_SEAT_BALL);
    GL_CHECK(z.x == ball.x && z.y == ball.y);
    GL_CHECK_NEAR(t.base_temp_c, 22.5, 1e-6);
    GL_CHECK_EQ(t.base_time_s, 200u);
    GL_CHECK_NEAR(t.base_scatter, 0.0002, 1e-9);
    GL_CHECK_NEAR(t.flip_scatter, 0.0001, 1e-9);
    /* the user zeroes again on a hard surface (ball seat): the base-face
     * zero moves WITH it - the difference between the seats is kept - and
     * the record says that it was not measured again */
    gl_cal_tilt_set_zero(&t, GL_CAL_SEAT_BALL, ball2, 30.0f, 300u, 0.0003f);
    GL_CHECK(t.flags & GL_CAL_TILT_FLAG_BASE_DERIVED);
    GL_CHECK_NEAR(t.base_bias_x - t.flip_bias_x, (double)base.x - (double)ball.x, 1e-8);
    GL_CHECK_NEAR(t.base_bias_y - t.flip_bias_y, (double)base.y - (double)ball.y, 1e-8);
    GL_CHECK_NEAR(t.base_temp_c, 22.5, 1e-6); /* when the base face was MEASURED */
    /* measured again at the factory: no longer derived */
    gl_cal_tilt_set_zero(&t, GL_CAL_SEAT_BASE, base, 23.0f, 400u, 0.0001f);
    GL_CHECK(!(t.flags & GL_CAL_TILT_FLAG_BASE_DERIVED));
    /* a base-face zero alone (no ball seat): used for both */
    gl_cal_tilt_defaults(&t);
    gl_cal_tilt_set_zero(&t, GL_CAL_SEAT_BASE, base, 23.0f, 400u, 0.0f);
    GL_CHECK_EQ(gl_cal_tilt_zero(&t, GL_CAL_SEAT_BALL, &z), GL_CAL_SEAT_BASE);
    GL_CHECK(z.x == base.x);
}

GL_TEST(test_camera_horizon_row)
{
    gl_cal_cam_t c;
    gl_cam_model_t m;
    const gl_vec3_t up = { 0.0f, 0.0f, 1.0f };
    float u = 0.0f, v = 0.0f;

    gl_cal_cam_defaults(&c, 0);
    /* refused values change nothing */
    GL_CHECK_EQ(gl_cal_cam_set_horizon(&c, (float)NAN, 0.0f), GL_ERR_RANGE);
    GL_CHECK_EQ(gl_cal_cam_set_horizon(&c, -1.0f, 0.0f), GL_ERR_RANGE);
    GL_CHECK_EQ(gl_cal_cam_set_horizon(&c, 480.0f, 0.0f), GL_ERR_RANGE);
    GL_CHECK_EQ(gl_cal_cam_set_horizon(&c, 250.0f, 0.3f), GL_ERR_RANGE);
    GL_CHECK_EQ(gl_cal_cam_set_horizon(&c, 400.0f, 0.0f), GL_ERR_RANGE); /* pitch 0.24 rad */
    GL_CHECK_EQ(c.flags, 0);
    GL_CHECK_NEAR(c.pitch_up_rad, 0.0, 0.0);
    /* a level target imaged 12.5 rows BELOW the centre: the axis points up */
    GL_CHECK_EQ(gl_cal_cam_set_horizon(&c, 252.0f, 0.0f), GL_OK);
    GL_CHECK(c.flags & GL_CAL_CAM_FLAG_HORIZON);
    GL_CHECK_NEAR(c.pitch_up_rad, atan(12.5 / (double)GL_CFG_CAM_F_PX), 1e-7);
    GL_CHECK(c.pitch_up_rad > 0.0f);
    /* THE PROOF OF THE SIGN: through the camera model, a level ray straight
     * ahead lands on the row that was given */
    gl_cam_model_init(&m, &c);
    GL_CHECK(gl_cam_ray_to_pixel(&m, gl_cam_bearing_elev_to_ray(0.0f, 0.0f, up), &u, &v));
    printf("    CAM_HORIZON row 252.0 -> pitch_up %.3f mrad; the camera model images a level ray "
           "at row %.3f\n", 1000.0 * (double)c.pitch_up_rad, (double)v);
    GL_CHECK_NEAR(v, 252.0, 0.01);
    GL_CHECK_EQ(gl_cal_cam_set_horizon(&c, 230.0f, 0.0f), GL_OK);
    GL_CHECK(c.pitch_up_rad < 0.0f);
    gl_cam_model_init(&m, &c);
    GL_CHECK(gl_cam_ray_to_pixel(&m, gl_cam_bearing_elev_to_ray(0.0f, 0.0f, up), &u, &v));
    GL_CHECK_NEAR(v, 230.0, 0.01);
}

GL_TEST(test_serial_number)
{
    static const uint8_t uid[12] = { 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5,
                                     0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xAB };
    static const uint8_t zeros[12] = { 0 };
    uint8_t other[12];
    char text[8];
    uint32_t s;

    /* CRC-32 as zlib computes it: the standard check value */
    GL_CHECK_EQ(gl_crc32((const uint8_t *)"123456789", 9), 0xCBF43926u);
    GL_CHECK_EQ(gl_crc32_update(gl_crc32((const uint8_t *)"1234", 4), (const uint8_t *)"56789", 5),
                0xCBF43926u);
    GL_CHECK_EQ(gl_crc32(NULL, 0), 0u);
    s = gl_cal_serial_from_uid(uid);
    GL_CHECK_EQ(s, gl_crc32(uid, 12));
    GL_CHECK(s != 0u);
    GL_CHECK(gl_cal_serial_from_uid(zeros) != 0u);
    memcpy(other, uid, 12);
    other[11] ^= 1u;
    GL_CHECK(gl_cal_serial_from_uid(other) != s);
    /* 7 characters, most significant first, no I L O U */
    gl_cal_serial_text(s, text);
    GL_CHECK_EQ(strlen(text), 7u);
    GL_CHECK(strpbrk(text, "ILOUilou") == NULL);
    {
        static const char alphabet[] = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";
        uint32_t back = 0;
        for (int i = 0; i < 7; i++) {
            const char *q = strchr(alphabet, text[i]);
            GL_CHECK(q != NULL);
            back = (back << 5) | (uint32_t)(q - alphabet);
        }
        GL_CHECK_EQ(back, s);
        printf("    unique number A0..AB -> serial 0x%08X = \"%s\"\n", (unsigned)s, text);
    }
    gl_cal_serial_text(0u, text);
    GL_CHECK(strcmp(text, "0000000") == 0);
    gl_cal_serial_text(0xFFFFFFFFu, text);
    GL_CHECK(strcmp(text, "3ZZZZZZ") == 0);
}

int main(void)
{
    GL_RUN(test_lengths_and_crc_of_every_record);
    GL_RUN(test_version_1_records_are_migrated);
    GL_RUN(test_two_level_zeros_and_the_rule_that_picks_one);
    GL_RUN(test_camera_horizon_row);
    GL_RUN(test_serial_number);
    return gl_test_summary();
}
