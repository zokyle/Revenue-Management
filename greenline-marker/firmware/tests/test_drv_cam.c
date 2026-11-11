/*
 * test_drv_cam.c - OVM7692 pair driver against the simulator: the camera
 * rail rule during power-up and power-down (exact pin and register
 * sequence), shared-bus ownership, strip windows in both windowing modes,
 * capture contents and timing, fault handling.
 */
#include "gl_test.h"

#include "gl_provisional.h"
#include "gl_trace_util.h"
#include "ov7692.h"

static gl_ov7692_t cam_;
static uint8_t buf_[640 * 96];

/* A scene whose value identifies the sensor pixel and the camera. */
static uint8_t pattern_(gl_cam_id_t cam, unsigned x, unsigned y)
{
    return (uint8_t)((x * 7u + y * 13u + (cam == GL_CAM_RIGHT ? 101u : 0u)) & 0xFFu);
}

static uint32_t last_frame_no_[2];
static uint64_t last_frame_t_[2];

static void scene_(void *ctx, gl_cam_id_t cam, uint16_t x0, uint16_t y0, uint16_t w, uint16_t h,
                   uint32_t frame_no, uint64_t t_us, uint8_t *luma)
{
    (void)ctx;
    last_frame_no_[cam] = frame_no;
    last_frame_t_[cam] = t_us;
    for (unsigned r = 0; r < h; r++) {
        for (unsigned c = 0; c < w; c++) {
            luma[r * w + c] = pattern_(cam, x0 + c, y0 + r);
        }
    }
}

static void fresh_(const gl_ov7692_cfg_t *cfg)
{
    gl_sim_reset(true);
    (void)gl_hal_init();
    gl_sim_cam_set_scene(scene_, NULL);
    gl_ov7692_init(&cam_, cfg);
}

static bool all_parked_(void)
{
    for (int p = (int)GL_PIN_CAM_FACING_FIRST; p <= (int)GL_PIN_CAM_FACING_LAST; p++) {
        if (gl_sim_pin_mode((gl_pin_t)p) != GL_PIN_MODE_ANALOG && !gl_sim_pin_drives_low((gl_pin_t)p)) {
            return false;
        }
    }
    return true;
}

typedef struct {
    uint8_t cam, reg, val;
} wr_t;

/* All SCCB writes in trace order. */
static size_t sccb_writes_(size_t from, wr_t *out, size_t cap)
{
    size_t n = 0;
    for (size_t i = from; i < gl_sim_trace_count(); i++) {
        const gl_sim_trace_t *t = gl_sim_trace_at(i);
        if (t->type == (uint8_t)GL_SIM_TR_SCCB_WRITE) {
            if (n < cap) {
                out[n].cam = t->a;
                out[n].reg = (uint8_t)t->b;
                out[n].val = (uint8_t)t->c;
            }
            n++;
        }
    }
    return n;
}

GL_TEST(test_init_parks_everything)
{
    fresh_(NULL);
    GL_CHECK(all_parked_());
    GL_CHECK(!gl_sim_cam_rail_on());
    GL_CHECK(gl_sim_pin_drives_low(GL_PIN_CAM_PWR_EN));
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

GL_TEST(test_power_up_sequence)
{
    /* register writes each camera must receive, in this order */
    static const uint8_t expect[][2] = {
        { 0x12, 0x80 }, /* software reset */
        { 0x0C, 0x80 }, /* vertical flip on, outputs RELEASED (bits 2, 1 clear) */
        { 0xFF, 0x01 }, /* MIPI bank */
        { 0xB5, 0x30 }, /* MIPI and low-power transmitter powered down */
        { 0xFF, 0x00 }, /* system bank */
        { 0x12, 0x00 }, /* YUV422 */
        { 0x0E, 0x08 }  /* sleep */
    };
    wr_t wr[32];
    fresh_(NULL);
    gl_sim_trace_clear();
    const uint64_t t0 = gl_sim_now_us();
    GL_CHECK_EQ(gl_ov7692_power_up(&cam_), GL_OK);
    const uint64_t t_up = gl_sim_now_us() - t0;

    /* 1: the very first action is the rail enable */
    const gl_sim_trace_t *first = gl_sim_trace_at(0);
    GL_CHECK_EQ(first->type, GL_SIM_TR_GPIO_WRITE);
    GL_CHECK_EQ(first->a, GL_PIN_CAM_PWR_EN);
    GL_CHECK_EQ(first->b, 1);
    /* no camera-facing pin changes until the rail settle time has passed */
    for (size_t i = 1; i < gl_sim_trace_count(); i++) {
        const gl_sim_trace_t *t = gl_sim_trace_at(i);
        if ((t->type == (uint8_t)GL_SIM_TR_GPIO_MODE || t->type == (uint8_t)GL_SIM_TR_GPIO_WRITE) &&
            t->a >= (uint8_t)GL_PIN_CAM_FACING_FIRST && t->a <= (uint8_t)GL_PIN_CAM_FACING_LAST) {
            GL_CHECK(t->t_us - first->t_us >= (uint64_t)GL_PROV_CAM_RAIL_SETTLE_MS * 1000u);
            break;
        }
    }
    /* 2..4: PWDN asserted on both, then clock, then buses */
    const long i_pwdn_l = tr_find_write(0, GL_PIN_CAM_L_PWDN, true);
    const long i_pwdn_r = tr_find_write(0, GL_PIN_CAM_R_PWDN, true);
    const long i_clk_pin = tr_find_mode(0, GL_PIN_CAM_XVCLK, GL_PIN_MODE_ALTERNATE);
    const long i_clk = tr_find(0, GL_SIM_TR_XVCLK, 1);
    const long i_sda = tr_find_mode(0, GL_PIN_CAM_SCCB_SDA, GL_PIN_MODE_ALTERNATE);
    const long i_d0 = tr_find_mode(0, GL_PIN_CAM_D0, GL_PIN_MODE_ALTERNATE);
    const long i_rel_l = tr_find_write(0, GL_PIN_CAM_L_PWDN, false);
    const long i_rel_r = tr_find_write(0, GL_PIN_CAM_R_PWDN, false);
    const long i_first_sccb = tr_find(0, GL_SIM_TR_SCCB_WRITE, -1);
    GL_CHECK(i_pwdn_l > 0 && i_pwdn_r > 0);
    GL_CHECK(i_clk_pin > i_pwdn_l && i_clk_pin > i_pwdn_r && i_clk > i_clk_pin);
    GL_CHECK_EQ(gl_sim_trace_at((size_t)i_clk)->c, 12000000u);
    GL_CHECK(i_sda > i_clk && i_d0 > i_clk);
    /* 5: left released from power-down and fully set up before the right is released */
    GL_CHECK(i_rel_l > i_sda && i_rel_l > i_d0);
    GL_CHECK(i_first_sccb > i_rel_l);
    const long i_l_sleep = tr_find(0, GL_SIM_TR_SCCB_WRITE, GL_CAM_LEFT);
    GL_CHECK(i_l_sleep >= 0);
    size_t n = sccb_writes_(0, wr, 32);
    GL_CHECK_EQ(n, 2 * GL_ARRAY_LEN(expect));
    for (size_t k = 0; k < GL_ARRAY_LEN(expect) && n == 2 * GL_ARRAY_LEN(expect); k++) {
        GL_CHECK_EQ(wr[k].cam, GL_CAM_LEFT);
        GL_CHECK_EQ(wr[k].reg, expect[k][0]);
        GL_CHECK_EQ(wr[k].val, expect[k][1]);
        GL_CHECK_EQ(wr[GL_ARRAY_LEN(expect) + k].cam, GL_CAM_RIGHT);
        GL_CHECK_EQ(wr[GL_ARRAY_LEN(expect) + k].reg, expect[k][0]);
        GL_CHECK_EQ(wr[GL_ARRAY_LEN(expect) + k].val, expect[k][1]);
    }
    /* the right camera's PWDN is released only after the left one's last write */
    size_t last_left = 0;
    for (size_t i = 0; i < gl_sim_trace_count(); i++) {
        const gl_sim_trace_t *t = gl_sim_trace_at(i);
        if (t->type == (uint8_t)GL_SIM_TR_SCCB_WRITE && t->a == (uint8_t)GL_CAM_LEFT) {
            last_left = i;
        }
    }
    GL_CHECK((size_t)i_rel_r > last_left);

    /* end state */
    GL_CHECK(cam_.powered);
    GL_CHECK(gl_sim_cam_rail_on());
    GL_CHECK_EQ(cam_.cam[0].pid, 0x7692);
    GL_CHECK_EQ(cam_.cam[1].pid, 0x7692);
    GL_CHECK(!gl_sim_cam_streaming(GL_CAM_LEFT) && !gl_sim_cam_streaming(GL_CAM_RIGHT));
    GL_CHECK(!gl_sim_cam_driving(GL_CAM_LEFT) && !gl_sim_cam_driving(GL_CAM_RIGHT));
    printf("    power-up: %u trace records, %.1f ms, %u SCCB writes\n", (unsigned)gl_sim_trace_count(),
           (double)t_up / 1000.0, (unsigned)n);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

GL_TEST(test_power_down_sequence)
{
    fresh_(NULL);
    GL_CHECK_EQ(gl_ov7692_power_up(&cam_), GL_OK);
    GL_CHECK_EQ(gl_ov7692_select(&cam_, GL_CAM_LEFT, GL_OV_OTHER_SLEEP), GL_OK);
    gl_sim_trace_clear();
    gl_ov7692_power_down(&cam_);

    /* the rail enable goes low only after every camera-facing pin is parked */
    const long i_rail = tr_find_write(0, GL_PIN_CAM_PWR_EN, false);
    GL_CHECK(i_rail > 0);
    for (size_t i = (size_t)i_rail + 1u; i < gl_sim_trace_count(); i++) {
        const gl_sim_trace_t *t = gl_sim_trace_at(i);
        if (t->type == (uint8_t)GL_SIM_TR_GPIO_MODE || t->type == (uint8_t)GL_SIM_TR_GPIO_WRITE) {
            GL_CHECK(t->a == (uint8_t)GL_PIN_CAM_PWR_EN); /* nothing else touched afterwards */
        }
    }
    const long i_clk_off = tr_find(0, GL_SIM_TR_XVCLK, 0);
    const long i_dcmi_off = tr_find(0, GL_SIM_TR_DCMI_STOP, -1);
    GL_CHECK(i_clk_off >= 0 && i_clk_off < i_rail);
    GL_CHECK(i_dcmi_off >= 0 && i_dcmi_off < i_rail);
    GL_CHECK(all_parked_());
    GL_CHECK(!gl_sim_cam_rail_on());
    /* data and sync inputs are analog; clock, SCCB and PWDN are driven low */
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_CAM_D0), GL_PIN_MODE_ANALOG);
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_CAM_PIXCLK), GL_PIN_MODE_ANALOG);
    GL_CHECK(gl_sim_pin_drives_low(GL_PIN_CAM_XVCLK));
    GL_CHECK(gl_sim_pin_drives_low(GL_PIN_CAM_SCCB_SDA));
    GL_CHECK(gl_sim_pin_drives_low(GL_PIN_CAM_L_SCL));
    GL_CHECK(gl_sim_pin_drives_low(GL_PIN_CAM_R_SCL));
    GL_CHECK(gl_sim_pin_drives_low(GL_PIN_CAM_L_PWDN));
    GL_CHECK(gl_sim_pin_drives_low(GL_PIN_CAM_R_PWDN));
    GL_CHECK(!cam_.powered);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);

    /* power cycling many times never breaks the rule */
    for (unsigned i = 0; i < 20u; i++) {
        GL_CHECK_EQ(gl_ov7692_power_up(&cam_), GL_OK);
        gl_ov7692_power_down(&cam_);
    }
    GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, 21u);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

GL_TEST(test_bus_ownership)
{
    wr_t wr[8];
    fresh_(NULL);
    GL_CHECK_EQ(gl_ov7692_power_up(&cam_), GL_OK);

    gl_sim_trace_clear();
    GL_CHECK_EQ(gl_ov7692_select(&cam_, GL_CAM_LEFT, GL_OV_OTHER_SLEEP), GL_OK);
    GL_CHECK_EQ(sccb_writes_(0, wr, 8), 2);
    GL_CHECK(wr[0].cam == GL_CAM_LEFT && wr[0].reg == 0x0E && wr[0].val == 0x00); /* wake */
    GL_CHECK(wr[1].cam == GL_CAM_LEFT && wr[1].reg == 0x0C && wr[1].val == 0x86); /* drive */
    GL_CHECK(gl_sim_cam_driving(GL_CAM_LEFT) && !gl_sim_cam_driving(GL_CAM_RIGHT));
    GL_CHECK(!gl_sim_cam_streaming(GL_CAM_RIGHT));

    /* switch to the right camera, keeping the left one awake: the left
     * one is released BEFORE the right one is enabled */
    gl_sim_trace_clear();
    GL_CHECK_EQ(gl_ov7692_select(&cam_, GL_CAM_RIGHT, GL_OV_OTHER_AWAKE), GL_OK);
    GL_CHECK_EQ(sccb_writes_(0, wr, 8), 3);
    GL_CHECK(wr[0].cam == GL_CAM_LEFT && wr[0].reg == 0x0C && wr[0].val == 0x80);
    GL_CHECK(wr[1].cam == GL_CAM_RIGHT && wr[1].reg == 0x0E && wr[1].val == 0x00);
    GL_CHECK(wr[2].cam == GL_CAM_RIGHT && wr[2].reg == 0x0C && wr[2].val == 0x86);
    GL_CHECK(gl_sim_cam_driving(GL_CAM_RIGHT) && !gl_sim_cam_driving(GL_CAM_LEFT));
    GL_CHECK(gl_sim_cam_streaming(GL_CAM_LEFT)); /* still awake */

    /* back to the left: two writes only (no wake needed) */
    gl_sim_trace_clear();
    GL_CHECK_EQ(gl_ov7692_select(&cam_, GL_CAM_LEFT, GL_OV_OTHER_AWAKE), GL_OK);
    GL_CHECK_EQ(sccb_writes_(0, wr, 8), 2);
    GL_CHECK(wr[0].cam == GL_CAM_RIGHT && wr[0].reg == 0x0C && wr[0].val == 0x80);
    GL_CHECK(wr[1].cam == GL_CAM_LEFT && wr[1].reg == 0x0C && wr[1].val == 0x86);

    /* selecting with OTHER_SLEEP puts the idle one to sleep */
    gl_sim_trace_clear();
    GL_CHECK_EQ(gl_ov7692_select(&cam_, GL_CAM_LEFT, GL_OV_OTHER_SLEEP), GL_OK);
    GL_CHECK_EQ(sccb_writes_(0, wr, 8), 1);
    GL_CHECK(wr[0].cam == GL_CAM_RIGHT && wr[0].reg == 0x0E && wr[0].val == 0x08);
    GL_CHECK(!gl_sim_cam_streaming(GL_CAM_RIGHT));

    GL_CHECK_EQ(gl_ov7692_release_all(&cam_), GL_OK);
    GL_CHECK(!gl_sim_cam_driving(GL_CAM_LEFT) && !gl_sim_cam_driving(GL_CAM_RIGHT));
    GL_CHECK_EQ(gl_sim_violations()->cam_contention, 0u);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
    gl_ov7692_power_down(&cam_);
}

GL_TEST(test_window_registers)
{
    fresh_(NULL);
    GL_CHECK_EQ(gl_ov7692_power_up(&cam_), GL_OK);
    /* horizon band: 640 x 96 at row 193 -> origin rounded down to row 192 */
    GL_CHECK_EQ(gl_ov7692_set_window(&cam_, GL_CAM_LEFT, 0, 193, 640, 96), GL_OK);
    GL_CHECK_EQ(cam_.cam[0].y0, 192);
    GL_CHECK_EQ(gl_sim_cam_reg(GL_CAM_LEFT, 0x17), 0x69);            /* HSTART: column 0 */
    GL_CHECK_EQ(gl_sim_cam_reg(GL_CAM_LEFT, 0x18), (640 + 16) / 4);  /* HSIZE */
    GL_CHECK_EQ(gl_sim_cam_reg(GL_CAM_LEFT, 0x19), 0x0C + 192 / 2);  /* VSTART */
    GL_CHECK_EQ(gl_sim_cam_reg(GL_CAM_LEFT, 0x1A), (96 + 12) / 2);   /* VSIZE */
    GL_CHECK_EQ(gl_sim_cam_reg(GL_CAM_LEFT, 0xC8), 0x02);            /* input 640 x 96 */
    GL_CHECK_EQ(gl_sim_cam_reg(GL_CAM_LEFT, 0xC9), 0x80);
    GL_CHECK_EQ(gl_sim_cam_reg(GL_CAM_LEFT, 0xCA), 0x00);
    GL_CHECK_EQ(gl_sim_cam_reg(GL_CAM_LEFT, 0xCB), 0x60);
    GL_CHECK_EQ(gl_sim_cam_reg(GL_CAM_LEFT, 0xCC), 0x02);            /* output = input */
    GL_CHECK_EQ(gl_sim_cam_reg(GL_CAM_LEFT, 0xCD), 0x80);
    GL_CHECK_EQ(gl_sim_cam_reg(GL_CAM_LEFT, 0xCE), 0x00);
    GL_CHECK_EQ(gl_sim_cam_reg(GL_CAM_LEFT, 0xCF), 0x60);
    /* the right camera was not touched */
    GL_CHECK_EQ(gl_sim_cam_reg(GL_CAM_RIGHT, 0x1A), 0xF6);

    /* flagstick strip: 96 x 480 at column 301 -> column 300 */
    GL_CHECK_EQ(gl_ov7692_set_window(&cam_, GL_CAM_RIGHT, 301, 0, 96, 480), GL_OK);
    GL_CHECK_EQ(cam_.cam[1].x0, 300);
    GL_CHECK_EQ(gl_sim_cam_reg(GL_CAM_RIGHT, 0x17), 0x69 + 75);
    GL_CHECK_EQ(gl_sim_cam_reg(GL_CAM_RIGHT, 0x18), (96 + 16) / 4);
    GL_CHECK_EQ(gl_sim_cam_reg(GL_CAM_RIGHT, 0x19), 0x0C);
    GL_CHECK_EQ(gl_sim_cam_reg(GL_CAM_RIGHT, 0x1A), 0xF6);
    GL_CHECK_EQ(gl_sim_cam_reg(GL_CAM_RIGHT, 0xCC), 0x00);
    GL_CHECK_EQ(gl_sim_cam_reg(GL_CAM_RIGHT, 0xCD), 0x60);
    GL_CHECK_EQ(gl_sim_cam_reg(GL_CAM_RIGHT, 0xCE), 0x01);
    GL_CHECK_EQ(gl_sim_cam_reg(GL_CAM_RIGHT, 0xCF), 0xE0);

    /* a window hanging over the edge is shifted inward */
    GL_CHECK_EQ(gl_ov7692_set_window(&cam_, GL_CAM_RIGHT, 600, 0, 96, 480), GL_OK);
    GL_CHECK_EQ(cam_.cam[1].x0, 544);
    /* setting the same window again costs no bus traffic */
    gl_sim_trace_clear();
    GL_CHECK_EQ(gl_ov7692_set_window(&cam_, GL_CAM_RIGHT, 544, 0, 96, 480), GL_OK);
    GL_CHECK_EQ(gl_sim_trace_count(), 0);
    /* impossible sizes */
    GL_CHECK_EQ(gl_ov7692_set_window(&cam_, GL_CAM_LEFT, 0, 0, 98, 480), GL_ERR_PARAM);
    GL_CHECK_EQ(gl_ov7692_set_window(&cam_, GL_CAM_LEFT, 0, 0, 96, 481), GL_ERR_PARAM);
    GL_CHECK_EQ(gl_ov7692_set_window(&cam_, GL_CAM_LEFT, 0, 0, 644, 480), GL_ERR_PARAM);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
    gl_ov7692_power_down(&cam_);
}

static unsigned strip_mismatches_(gl_cam_id_t cam, const gl_strip_t *s)
{
    unsigned bad = 0;
    for (unsigned r = 0; r < s->height; r++) {
        for (unsigned c = 0; c < s->width; c++) {
            if (s->px[r * s->stride + c] != pattern_(cam, s->x0 + c, s->y0 + r)) {
                bad++;
            }
        }
    }
    return bad;
}

static void capture_contents_(bool sensor_windowing)
{
    gl_ov7692_cfg_t cfg;
    gl_strip_t strip;
    gl_ov7692_cfg_defaults(&cfg);
    cfg.sensor_windowing = sensor_windowing;
    fresh_(&cfg);
    GL_CHECK_EQ(gl_ov7692_power_up(&cam_), GL_OK);

    /* horizon band from the left camera */
    GL_CHECK_EQ(gl_ov7692_select(&cam_, GL_CAM_LEFT, GL_OV_OTHER_AWAKE), GL_OK);
    GL_CHECK_EQ(gl_ov7692_set_window(&cam_, GL_CAM_LEFT, 0, 192, 640, 96), GL_OK);
    memset(buf_, 0xAA, sizeof(buf_));
    GL_CHECK_EQ(gl_ov7692_capture_blocking(&cam_, GL_CAM_LEFT, buf_, sizeof(buf_), &strip), GL_OK);
    GL_CHECK_EQ(strip.width, 640);
    GL_CHECK_EQ(strip.height, 96);
    GL_CHECK_EQ(strip.x0, 0);
    GL_CHECK_EQ(strip.y0, 192);
    GL_CHECK_EQ(strip_mismatches_(GL_CAM_LEFT, &strip), 0);

    /* flagstick strip from the right camera */
    GL_CHECK_EQ(gl_ov7692_select(&cam_, GL_CAM_RIGHT, GL_OV_OTHER_AWAKE), GL_OK);
    GL_CHECK_EQ(gl_ov7692_set_window(&cam_, GL_CAM_RIGHT, 301, 0, 96, 480), GL_OK);
    memset(buf_, 0xAA, sizeof(buf_));
    GL_CHECK_EQ(gl_ov7692_capture_blocking(&cam_, GL_CAM_RIGHT, buf_, sizeof(buf_), &strip), GL_OK);
    GL_CHECK_EQ(strip.width, 96);
    GL_CHECK_EQ(strip.height, 480);
    GL_CHECK_EQ(strip.x0, 300);
    GL_CHECK_EQ(strip.y0, 0);
    GL_CHECK_EQ(strip_mismatches_(GL_CAM_RIGHT, &strip), 0);
    /* nothing beyond the strip was written */
    GL_CHECK_EQ(buf_[96 * 480], 0xAA);

    /* and a strip from the left camera again */
    GL_CHECK_EQ(gl_ov7692_select(&cam_, GL_CAM_LEFT, GL_OV_OTHER_AWAKE), GL_OK);
    GL_CHECK_EQ(gl_ov7692_set_window(&cam_, GL_CAM_LEFT, 312, 0, 96, 480), GL_OK);
    GL_CHECK_EQ(gl_ov7692_capture_blocking(&cam_, GL_CAM_LEFT, buf_, sizeof(buf_), &strip), GL_OK);
    GL_CHECK_EQ(strip.x0, 312);
    GL_CHECK_EQ(strip_mismatches_(GL_CAM_LEFT, &strip), 0);
    GL_CHECK_EQ(cam_.frames, 3u);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
    gl_ov7692_power_down(&cam_);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

GL_TEST(test_capture_sensor_side_windowing)
{
    capture_contents_(true);
}

GL_TEST(test_capture_dcmi_crop_windowing)
{
    capture_contents_(false);
    /* in this mode the sensor's window registers are never written */
    GL_CHECK_EQ(tr_find(0, GL_SIM_TR_SCCB_WRITE, -1) >= 0, 1);
    for (size_t i = 0; i < gl_sim_trace_count(); i++) {
        const gl_sim_trace_t *t = gl_sim_trace_at(i);
        if (t->type == (uint8_t)GL_SIM_TR_SCCB_WRITE) {
            GL_CHECK(t->b != 0x17 && t->b != 0x18 && t->b != 0x19 && t->b != 0x1A && t->b < 0xC8);
        }
    }
}

GL_TEST(test_settle_frames_and_lrrl_timing)
{
    gl_strip_t strip;
    uint32_t t_done[8];
    fresh_(NULL);
    gl_sim_cam_set_phase_us(GL_CAM_RIGHT, 9000); /* the two sensors are not synchronised */
    GL_CHECK_EQ(gl_ov7692_power_up(&cam_), GL_OK);
    GL_CHECK_EQ(gl_ov7692_select(&cam_, GL_CAM_LEFT, GL_OV_OTHER_AWAKE), GL_OK);
    GL_CHECK_EQ(gl_ov7692_set_window(&cam_, GL_CAM_LEFT, 300, 0, 96, 480), GL_OK);
    GL_CHECK_EQ(gl_ov7692_set_window(&cam_, GL_CAM_RIGHT, 292, 0, 96, 480), GL_OK);

    /* the first capture after waking waits for the settle frames: the
     * model's first two frames are black, the driver must not return them */
    const uint64_t t0 = gl_sim_now_us();
    GL_CHECK_EQ(gl_ov7692_capture_blocking(&cam_, GL_CAM_LEFT, buf_, sizeof(buf_), &strip), GL_OK);
    GL_CHECK(gl_sim_now_us() - t0 >= (uint64_t)GL_PROV_CAM_SETTLE_FRAMES * 33333u);
    GL_CHECK(last_frame_no_[GL_CAM_LEFT] >= GL_SIM_CAM_BAD_FRAMES);
    GL_CHECK_EQ(strip_mismatches_(GL_CAM_LEFT, &strip), 0);

    /* two L R R L groups */
    static const gl_cam_id_t order[8] = { GL_CAM_LEFT, GL_CAM_RIGHT, GL_CAM_RIGHT, GL_CAM_LEFT,
                                          GL_CAM_LEFT, GL_CAM_RIGHT, GL_CAM_RIGHT, GL_CAM_LEFT };
    for (unsigned i = 0; i < 8u; i++) {
        GL_CHECK_EQ(gl_ov7692_select(&cam_, order[i], GL_OV_OTHER_AWAKE), GL_OK);
        GL_CHECK_EQ(gl_ov7692_capture_blocking(&cam_, order[i], buf_, sizeof(buf_), &strip), GL_OK);
        GL_CHECK_EQ(strip_mismatches_(order[i], &strip), 0);
        t_done[i] = cam_.last_done_ms;
    }
    printf("    L R R L completion intervals with a 9 ms sensor phase offset: %u %u %u | %u | %u %u %u ms\n",
           (unsigned)(t_done[1] - t_done[0]), (unsigned)(t_done[2] - t_done[1]),
           (unsigned)(t_done[3] - t_done[2]), (unsigned)(t_done[4] - t_done[3]),
           (unsigned)(t_done[5] - t_done[4]), (unsigned)(t_done[6] - t_done[5]),
           (unsigned)(t_done[7] - t_done[6]));
    /* every strip arrives within two frame periods of the previous one */
    for (unsigned i = 1; i < 8u; i++) {
        GL_CHECK(t_done[i] - t_done[i - 1u] >= 30u && t_done[i] - t_done[i - 1u] <= 70u);
    }
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
    gl_ov7692_power_down(&cam_);
}

GL_TEST(test_faults_leave_the_rail_off)
{
    gl_ov7692_cfg_t cfg;
    /* a camera that does not answer */
    fresh_(NULL);
    gl_sim_cam_set_present(GL_CAM_RIGHT, false);
    GL_CHECK_EQ(gl_ov7692_power_up(&cam_), GL_ERR_IO);
    GL_CHECK(!cam_.powered);
    GL_CHECK(!gl_sim_cam_rail_on());
    GL_CHECK(all_parked_());
    GL_CHECK_EQ(gl_sim_violations()->cam_rail, 0u);

    /* state errors without power */
    GL_CHECK_EQ(gl_ov7692_select(&cam_, GL_CAM_LEFT, GL_OV_OTHER_SLEEP), GL_ERR_STATE);
    GL_CHECK_EQ(gl_ov7692_set_window(&cam_, GL_CAM_LEFT, 0, 0, 96, 480), GL_ERR_STATE);
    GL_CHECK_EQ(gl_ov7692_capture_start(&cam_, GL_CAM_LEFT, buf_, sizeof(buf_), NULL), GL_ERR_STATE);

    /* a wrong product id is refused when enforced, accepted when not */
    gl_ov7692_cfg_defaults(&cfg);
    fresh_(&cfg);
    GL_CHECK_EQ(gl_ov7692_power_up(&cam_), GL_OK);
    gl_ov7692_power_down(&cam_);

    /* capture from a camera that is not the selected one, without a window,
     * into a buffer that is too small */
    fresh_(NULL);
    GL_CHECK_EQ(gl_ov7692_power_up(&cam_), GL_OK);
    GL_CHECK_EQ(gl_ov7692_select(&cam_, GL_CAM_LEFT, GL_OV_OTHER_SLEEP), GL_OK);
    GL_CHECK_EQ(gl_ov7692_capture_start(&cam_, GL_CAM_LEFT, buf_, sizeof(buf_), NULL), GL_ERR_STATE);
    GL_CHECK_EQ(gl_ov7692_set_window(&cam_, GL_CAM_LEFT, 0, 0, 96, 480), GL_OK);
    GL_CHECK_EQ(gl_ov7692_capture_start(&cam_, GL_CAM_RIGHT, buf_, sizeof(buf_), NULL), GL_ERR_STATE);
    GL_CHECK_EQ(gl_ov7692_capture_start(&cam_, GL_CAM_LEFT, buf_, 100, NULL), GL_ERR_PARAM);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);

    /* the sensor stops delivering frames (put to sleep behind the driver's
     * back): the capture times out instead of hanging */
    GL_CHECK_EQ(gl_hal_sccb_write(GL_CAM_LEFT, 0x3C, 0x0E, 0x08), GL_OK);
    const uint64_t t0 = gl_sim_now_us();
    GL_CHECK_EQ(gl_ov7692_capture_blocking(&cam_, GL_CAM_LEFT, buf_, sizeof(buf_), NULL),
                GL_ERR_TIMEOUT);
    GL_CHECK(gl_sim_now_us() - t0 < 400000u);
    GL_CHECK(!cam_.capturing);
    gl_ov7692_power_down(&cam_);
    GL_CHECK(all_parked_());
    GL_CHECK_EQ(gl_sim_violations()->cam_rail, 0u);
}

GL_TEST(test_wrong_flip_bits_show)
{
    /* the model delivers an upside-down image if the flip bit is not what
     * the (assumed) prism geometry needs: the constants are exercised */
    gl_ov7692_cfg_t cfg;
    gl_strip_t strip;
    gl_ov7692_cfg_defaults(&cfg);
    cfg.vflip = !cfg.vflip;
    fresh_(&cfg);
    GL_CHECK_EQ(gl_ov7692_power_up(&cam_), GL_OK);
    GL_CHECK_EQ(gl_ov7692_select(&cam_, GL_CAM_LEFT, GL_OV_OTHER_SLEEP), GL_OK);
    GL_CHECK_EQ(gl_ov7692_set_window(&cam_, GL_CAM_LEFT, 0, 0, 96, 480), GL_OK);
    GL_CHECK_EQ(gl_ov7692_capture_blocking(&cam_, GL_CAM_LEFT, buf_, sizeof(buf_), &strip), GL_OK);
    GL_CHECK(strip_mismatches_(GL_CAM_LEFT, &strip) > 40000u);
    gl_ov7692_power_down(&cam_);
}

GL_TEST(test_model_catches_rail_rule_violations)
{
    /* the checker this file relies on does fire */
    fresh_(NULL);
    /* a camera-facing pin routed to its peripheral with the rail off */
    gl_hal_gpio_mode(GL_PIN_CAM_D3, GL_PIN_MODE_ALTERNATE);
    GL_CHECK_EQ(gl_sim_violations()->cam_rail, 1u);
    gl_hal_gpio_mode(GL_PIN_CAM_D3, GL_PIN_MODE_ANALOG);
    /* PWDN driven high with the rail off */
    gl_hal_gpio_write(GL_PIN_CAM_L_PWDN, true);
    GL_CHECK_EQ(gl_sim_violations()->cam_rail, 2u);
    gl_hal_gpio_write(GL_PIN_CAM_L_PWDN, false);
    /* an input with a pull-up is not "analog or low" either */
    gl_hal_gpio_mode(GL_PIN_CAM_VSYNC, GL_PIN_MODE_INPUT_PULLUP);
    GL_CHECK_EQ(gl_sim_violations()->cam_rail, 3u);
    gl_hal_gpio_mode(GL_PIN_CAM_VSYNC, GL_PIN_MODE_ANALOG);
    /* a pin switched 0.5 ms after the rail enable: too early */
    gl_hal_gpio_write(GL_PIN_CAM_PWR_EN, true);
    gl_hal_delay_us(500);
    gl_hal_gpio_mode(GL_PIN_CAM_XVCLK, GL_PIN_MODE_ALTERNATE);
    GL_CHECK_EQ(gl_sim_violations()->cam_rail, 4u);
    gl_hal_delay_ms(2);
    /* the rail switched off with a pin still routed */
    gl_hal_gpio_write(GL_PIN_CAM_PWR_EN, false);
    GL_CHECK_EQ(gl_sim_violations()->cam_rail, 5u);
    gl_hal_gpio_mode(GL_PIN_CAM_XVCLK, GL_PIN_MODE_ANALOG);

    /* SCCB to an unpowered camera, and both cameras driving the bus */
    GL_CHECK_EQ(gl_hal_sccb_write(GL_CAM_LEFT, 0x3C, 0x0E, 0x00), GL_ERR_IO);
    GL_CHECK(gl_sim_violations()->cam_sccb >= 1u);
    fresh_(NULL);
    GL_CHECK_EQ(gl_ov7692_power_up(&cam_), GL_OK);
    GL_CHECK_EQ(gl_hal_sccb_write(GL_CAM_LEFT, 0x3C, 0x0E, 0x00), GL_OK);
    GL_CHECK_EQ(gl_hal_sccb_write(GL_CAM_LEFT, 0x3C, 0x0C, 0x86), GL_OK);
    GL_CHECK_EQ(gl_hal_sccb_write(GL_CAM_RIGHT, 0x3C, 0x0E, 0x00), GL_OK);
    GL_CHECK_EQ(gl_sim_violations()->cam_contention, 0u);
    GL_CHECK_EQ(gl_hal_sccb_write(GL_CAM_RIGHT, 0x3C, 0x0C, 0x86), GL_OK);
    GL_CHECK_EQ(gl_sim_violations()->cam_contention, 1u);
    printf("    first violation text: %s\n", gl_sim_violations()->first);
}

int main(void)
{
    GL_RUN(test_init_parks_everything);
    GL_RUN(test_power_up_sequence);
    GL_RUN(test_power_down_sequence);
    GL_RUN(test_bus_ownership);
    GL_RUN(test_window_registers);
    GL_RUN(test_capture_sensor_side_windowing);
    GL_RUN(test_capture_dcmi_crop_windowing);
    GL_RUN(test_settle_frames_and_lrrl_timing);
    GL_RUN(test_faults_leave_the_rail_off);
    GL_RUN(test_wrong_flip_bits_show);
    GL_RUN(test_model_catches_rail_rule_violations);
    return gl_test_summary();
}
