/*
 * test_drv_lcd.c - LS013B7DH03 driver against the simulator: exact frame
 * bytes for known images, power sequencing, changed-lines-only updates,
 * both panel mountings, protocol timing.
 */
#include "gl_test.h"

#include "gl_provisional.h"
#include "gl_trace_util.h"
#include "gl_ui.h"
#include "ls013b7dh03.h"

static gl_lcd_t lcd_;
static gl_gfx_t gfx_;

static void fresh_(const gl_lcd_cfg_t *cfg)
{
    gl_sim_reset(true);
    (void)gl_hal_init();
    gl_lcd_init(&lcd_, cfg);
    gl_gfx_init(&gfx_);
    gl_gfx_set_clip(&gfx_, false);
}

GL_TEST(test_init_drives_inputs_low)
{
    fresh_(NULL);
    GL_CHECK(gl_sim_pin_drives_low(GL_PIN_LCD_SCS));
    GL_CHECK(gl_sim_pin_drives_low(GL_PIN_LCD_DISP));
    GL_CHECK(gl_sim_pin_drives_low(GL_PIN_LCD_EXTCOMIN));
    GL_CHECK(!gl_sim_lcd()->disp);
    GL_CHECK(!gl_sim_lcd()->extcomin);
    GL_CHECK_EQ(tr_count(0, gl_sim_trace_count(), GL_SIM_TR_SPI_XFER), 0);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

GL_TEST(test_power_on_sequence)
{
    fresh_(NULL);
    gl_sim_trace_clear();
    GL_CHECK_EQ(gl_lcd_on(&lcd_), GL_OK);

    /* order: SPI configured, SCS high, clear command, SCS low, EXTCOMIN
     * pin to the timer, timer started, DISP high */
    const long i_cfg = tr_find(0, GL_SIM_TR_SPI_CFG, GL_SPI_BUS_1);
    const long i_cs_hi = tr_find_write(0, GL_PIN_LCD_SCS, true);
    const long i_xfer = tr_find(0, GL_SIM_TR_SPI_XFER, GL_SPI_BUS_1);
    const long i_cs_lo = tr_find_write((size_t)i_cs_hi, GL_PIN_LCD_SCS, false);
    const long i_alt = tr_find_mode(0, GL_PIN_LCD_EXTCOMIN, GL_PIN_MODE_ALTERNATE);
    const long i_tim = tr_find(0, GL_SIM_TR_EXTCOMIN, 1);
    const long i_disp = tr_find_write(0, GL_PIN_LCD_DISP, true);
    GL_CHECK(i_cfg >= 0 && i_cs_hi > i_cfg && i_xfer > i_cs_hi && i_cs_lo > i_xfer);
    GL_CHECK(i_alt > i_cs_lo && i_tim > i_alt && i_disp > i_tim);

    /* SPI settings: mode 0, LSB first, 1 MHz */
    const gl_sim_trace_t *cfg = gl_sim_trace_at((size_t)i_cfg);
    GL_CHECK_EQ(cfg->b, 0x100u);
    GL_CHECK_EQ(cfg->c, 1000000u);
    /* EXTCOMIN: 32768 / 547 = 59.905 Hz, inside both published ranges */
    GL_CHECK_EQ(gl_sim_trace_at((size_t)i_tim)->c, 547u);

    /* the clear command is exactly M2 + 8 dummy bits */
    const gl_sim_lcd_t *p = gl_sim_lcd();
    GL_CHECK_EQ(p->last_frame_len, 2);
    GL_CHECK_EQ(p->last_frame[0], 0x04);
    GL_CHECK_EQ(p->last_frame[1], 0x00);
    GL_CHECK_EQ(p->clears, 1u);
    for (unsigned i = 0; i < sizeof(p->mem); i++) {
        if (p->mem[i] != 0xFF) {
            GL_CHECK(p->mem[i] == 0xFF);
            break;
        }
    }
    GL_CHECK(p->disp && p->extcomin);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

GL_TEST(test_known_image_exact_bytes)
{
    /* black pixels at (0,0) and (127,0), and columns 8..15 of row 5 */
    static const uint8_t expect[] = {
        0x01,                                           /* mode: M0 = write */
        0x01,                                           /* line address 1 = screen row 0 */
        0xFE, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, /* bit 0 of byte 0 = pixel x 0 */
        0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x7F, /* bit 7 of byte 15 = pixel x 127 */
        0x00,                                           /* 8 dummy bits */
        0x06,                                           /* line address 6 = screen row 5 */
        0xFF, 0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
        0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
        0x00,                                           /* 8 dummy bits */
        0x00                                            /* 8 more at the end */
    };
    unsigned sent = 99;
    fresh_(NULL);
    GL_CHECK_EQ(gl_lcd_on(&lcd_), GL_OK);
    gl_gfx_pixel(&gfx_, 0, 0, GL_INK_BLACK);
    gl_gfx_pixel(&gfx_, 127, 0, GL_INK_BLACK);
    gl_gfx_hline(&gfx_, 8, 15, 5, GL_INK_BLACK);

    gl_sim_trace_clear();
    GL_CHECK_EQ(gl_lcd_update(&lcd_, &gfx_, &sent), GL_OK);
    GL_CHECK_EQ(sent, 2);

    const gl_sim_lcd_t *p = gl_sim_lcd();
    GL_CHECK_EQ(p->last_frame_len, sizeof(expect));
    GL_CHECK_MEM(p->last_frame, expect, sizeof(expect));

    /* the same bytes as seen on the bus, all inside one chip-select frame */
    uint8_t bus[64];
    const long i_hi = tr_find_write(0, GL_PIN_LCD_SCS, true);
    const long i_lo = tr_find_write((size_t)i_hi, GL_PIN_LCD_SCS, false);
    GL_CHECK(i_hi >= 0 && i_lo > i_hi);
    GL_CHECK_EQ(tr_spi_bytes((size_t)i_hi, (size_t)i_lo, GL_SIM_DEV_LCD, bus, sizeof(bus)),
                sizeof(expect));
    GL_CHECK_MEM(bus, expect, sizeof(expect));
    GL_CHECK_EQ(tr_spi_bytes(0, gl_sim_trace_count(), GL_SIM_DEV_LCD, bus, 0), sizeof(expect));
    GL_CHECK_EQ(tr_spi_bytes(0, gl_sim_trace_count(), GL_SIM_DEV_NONE, bus, 0), 0);

    /* panel memory */
    GL_CHECK_EQ(p->mem[0], 0xFE);
    GL_CHECK_EQ(p->mem[15], 0x7F);
    GL_CHECK_EQ(p->mem[5 * 16 + 1], 0x00);
    GL_CHECK_EQ(p->lines_written, 2u);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

GL_TEST(test_only_changed_lines_are_sent)
{
    unsigned sent = 99;
    fresh_(NULL);
    GL_CHECK_EQ(gl_lcd_on(&lcd_), GL_OK);
    gl_gfx_rect(&gfx_, 10, 20, 30, 3, GL_INK_BLACK);
    GL_CHECK_EQ(gl_lcd_update(&lcd_, &gfx_, &sent), GL_OK);
    GL_CHECK_EQ(sent, 3);

    /* nothing changed: no frame at all */
    const uint32_t frames = gl_sim_lcd()->frames;
    gl_sim_trace_clear();
    GL_CHECK_EQ(gl_lcd_update(&lcd_, &gfx_, &sent), GL_OK);
    GL_CHECK_EQ(sent, 0);
    GL_CHECK_EQ(gl_sim_lcd()->frames, frames);
    GL_CHECK_EQ(gl_sim_trace_count(), 0);

    /* one pixel changed on row 100: 1 + 18 + 1 bytes, address 101 */
    gl_gfx_pixel(&gfx_, 64, 100, GL_INK_BLACK);
    GL_CHECK_EQ(gl_lcd_update(&lcd_, &gfx_, &sent), GL_OK);
    GL_CHECK_EQ(sent, 1);
    GL_CHECK_EQ(gl_sim_lcd()->last_frame_len, 20);
    GL_CHECK_EQ(gl_sim_lcd()->last_frame[0], 0x01);
    GL_CHECK_EQ(gl_sim_lcd()->last_frame[1], 101);
    GL_CHECK_EQ(gl_sim_lcd()->last_frame[2 + 8], 0xFE); /* x 64 = bit 0 of byte 8 */
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

GL_TEST(test_full_frame_length_and_time)
{
    unsigned sent = 0;
    fresh_(NULL);
    GL_CHECK_EQ(gl_lcd_on(&lcd_), GL_OK);
    gl_gfx_clear(&gfx_, GL_INK_BLACK);
    const uint64_t t0 = gl_sim_now_us();
    GL_CHECK_EQ(gl_lcd_update(&lcd_, &gfx_, &sent), GL_OK);
    const uint64_t dt = gl_sim_now_us() - t0;
    GL_CHECK_EQ(sent, 128);
    GL_CHECK_EQ(gl_sim_lcd()->last_frame_len, 2306); /* 1 + 128 * 18 + 1 */
    printf("    full frame: 2306 bytes, %.2f ms at 1 MHz including chip-select timing\n",
           (double)dt / 1000.0);
    GL_CHECK(dt >= 18448u && dt < 18600u);
    for (unsigned i = 0; i < 2048u; i++) {
        if (gl_sim_lcd()->mem[i] != 0x00) {
            GL_CHECK(gl_sim_lcd()->mem[i] == 0x00);
            break;
        }
    }
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* Panel memory bit for screen pixel (x, y) under a mounting. */
static bool panel_pixel_(const gl_lcd_cfg_t *cfg, int x, int y)
{
    const unsigned line = (unsigned)(cfg->row0_at_front ? y : (127 - y));
    const unsigned col = (unsigned)(cfg->col0_at_left ? x : (127 - x));
    return (((unsigned)gl_sim_lcd()->mem[line * 16u + (col >> 3)] >> (col & 7u)) & 1u) != 0u;
}

GL_TEST(test_random_images_all_mountings)
{
    uint32_t rng = 12345u;
    unsigned mismatches = 0;
    for (unsigned m = 0; m < 4u; m++) {
        gl_lcd_cfg_t cfg;
        cfg.row0_at_front = (m & 1u) != 0u;
        cfg.col0_at_left = (m & 2u) != 0u;
        fresh_(&cfg);
        GL_CHECK_EQ(gl_lcd_on(&lcd_), GL_OK);
        for (unsigned trial = 0; trial < 6u; trial++) {
            for (unsigned k = 0; k < 900u; k++) {
                rng = rng * 1664525u + 1013904223u;
                gl_gfx_pixel(&gfx_, (int)((rng >> 8) & 127u), (int)((rng >> 16) & 127u),
                             ((rng >> 30) & 1u) ? GL_INK_BLACK : GL_INK_WHITE);
            }
            GL_CHECK_EQ(gl_lcd_update(&lcd_, &gfx_, NULL), GL_OK);
            for (int y = 0; y < 128; y++) {
                for (int x = 0; x < 128; x++) {
                    if (panel_pixel_(&cfg, x, y) != gl_gfx_get(&gfx_, x, y)) {
                        mismatches++;
                    }
                }
            }
        }
        GL_CHECK_EQ(gl_sim_violation_total(), 0);
    }
    GL_CHECK_EQ(mismatches, 0);
}

GL_TEST(test_mounting_addresses)
{
    gl_lcd_cfg_t cfg = { false, false }; /* row 0 at the rear, column 0 at the right */
    fresh_(&cfg);
    GL_CHECK_EQ(gl_lcd_on(&lcd_), GL_OK);
    gl_gfx_pixel(&gfx_, 0, 0, GL_INK_BLACK);
    GL_CHECK_EQ(gl_lcd_update(&lcd_, &gfx_, NULL), GL_OK);
    /* screen (0,0) -> line address 128, last bit of the line */
    GL_CHECK_EQ(gl_sim_lcd()->last_frame[1], 128);
    GL_CHECK_EQ(gl_sim_lcd()->last_frame[2 + 15], 0x7F);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

GL_TEST(test_ui_screen_reaches_panel_inside_aperture)
{
    gl_ui_t ui;
    gl_ui_view_t view;
    gl_settings_t set;
    fresh_(NULL);
    gl_settings_defaults(&set);
    gl_ui_init(&ui, &set, 0);
    memset(&view, 0, sizeof(view));
    view.have_result = true;
    view.flag_found = true;
    view.aim_rad = 0.05f;
    view.distance_m = 4.2f;
    view.slope_pct = 1.8f;
    view.fall_line_rad = 2.0f;
    view.confidence = 0.7f;
    view.battery_pct = 80;
    ui.state = (uint8_t)GL_UI_SHOW_RESULT;
    gl_gfx_init(&gfx_);
    gl_ui_render(&ui, &view, &gfx_);
    GL_CHECK(gl_gfx_count_black(&gfx_) > 300u);

    GL_CHECK_EQ(gl_lcd_on(&lcd_), GL_OK);
    GL_CHECK_EQ(gl_lcd_update(&lcd_, &gfx_, NULL), GL_OK);
    GL_CHECK_MEM(gl_sim_lcd()->mem, gfx_.px, sizeof(gfx_.px));
    /* nothing outside the 122-pixel circle is black on the panel */
    unsigned outside = 0;
    for (int y = 0; y < 128; y++) {
        for (int x = 0; x < 128; x++) {
            const float dx = (float)x - 63.5f, dy = (float)y - 63.5f;
            if (dx * dx + dy * dy > 61.0f * 61.0f && !panel_pixel_(&lcd_.cfg, x, y)) {
                outside++;
            }
        }
    }
    GL_CHECK_EQ(outside, 0);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

GL_TEST(test_power_off_sequence_and_state)
{
    unsigned sent = 5;
    fresh_(NULL);
    GL_CHECK_EQ(gl_lcd_on(&lcd_), GL_OK);
    gl_sim_trace_clear();
    gl_lcd_off(&lcd_);
    /* DISP goes low BEFORE the inversion stops */
    const long i_disp = tr_find_write(0, GL_PIN_LCD_DISP, false);
    const long i_tim = tr_find(0, GL_SIM_TR_EXTCOMIN, 0);
    GL_CHECK(i_disp >= 0 && i_tim > i_disp);
    GL_CHECK(gl_sim_pin_drives_low(GL_PIN_LCD_EXTCOMIN));
    GL_CHECK(gl_sim_pin_drives_low(GL_PIN_LCD_DISP));
    GL_CHECK(!gl_sim_lcd()->disp && !gl_sim_lcd()->extcomin);

    /* no traffic while off */
    gl_sim_trace_clear();
    gl_gfx_pixel(&gfx_, 3, 3, GL_INK_BLACK);
    GL_CHECK_EQ(gl_lcd_update(&lcd_, &gfx_, &sent), GL_ERR_STATE);
    GL_CHECK_EQ(sent, 0);
    GL_CHECK_EQ(gl_sim_trace_count(), 0);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);

    /* on again: the panel is cleared and the whole image is resent */
    GL_CHECK_EQ(gl_lcd_on(&lcd_), GL_OK);
    GL_CHECK_EQ(gl_lcd_update(&lcd_, &gfx_, &sent), GL_OK);
    GL_CHECK_EQ(sent, 1);
    GL_CHECK_MEM(gl_sim_lcd()->mem, gfx_.px, sizeof(gfx_.px));
}

GL_TEST(test_model_catches_protocol_errors)
{
    /* the checks this file relies on do fire: drive the bus wrongly by hand */
    const gl_spi_cfg_t msb = { 1000000u, 0u, false };
    const gl_spi_cfg_t fast = { 2000000u, 0u, true };
    const uint8_t bad_len[3] = { 0x01, 0x05, 0xFF };
    const uint8_t clr[2] = { 0x04, 0x00 };

    fresh_(NULL);
    (void)gl_hal_spi_configure(GL_SPI_BUS_1, &msb);
    gl_hal_gpio_write(GL_PIN_LCD_SCS, true);
    gl_hal_delay_us(10);
    (void)gl_hal_spi_transfer(GL_SPI_BUS_1, clr, NULL, 2);
    gl_hal_delay_us(10);
    gl_hal_gpio_write(GL_PIN_LCD_SCS, false);
    GL_CHECK(gl_sim_violations()->lcd >= 1u); /* MSB first */

    unsigned before = gl_sim_violations()->lcd;
    (void)gl_hal_spi_configure(GL_SPI_BUS_1, &fast);
    gl_hal_delay_us(10);
    gl_hal_gpio_write(GL_PIN_LCD_SCS, true);
    gl_hal_delay_us(10);
    (void)gl_hal_spi_transfer(GL_SPI_BUS_1, bad_len, NULL, 3);
    gl_hal_delay_us(10);
    gl_hal_gpio_write(GL_PIN_LCD_SCS, false);
    GL_CHECK(gl_sim_violations()->lcd >= before + 2u); /* too fast + bad frame length */

    before = gl_sim_violations()->lcd;
    gl_hal_gpio_write(GL_PIN_LCD_DISP, true); /* DISP without EXTCOMIN */
    GL_CHECK_EQ(gl_sim_violations()->lcd, before + 1u);

    /* no set-up time after chip select */
    const gl_spi_cfg_t ok = { 1000000u, 0u, true };
    before = gl_sim_violations()->lcd;
    (void)gl_hal_spi_configure(GL_SPI_BUS_1, &ok);
    gl_hal_delay_us(10);
    gl_hal_gpio_write(GL_PIN_LCD_SCS, true);
    (void)gl_hal_spi_transfer(GL_SPI_BUS_1, clr, NULL, 2);
    gl_hal_delay_us(10);
    gl_hal_gpio_write(GL_PIN_LCD_SCS, false);
    GL_CHECK_EQ(gl_sim_violations()->lcd, before + 1u);
    printf("    first violation text: %s\n", gl_sim_violations()->first);
}

int main(void)
{
    GL_RUN(test_init_drives_inputs_low);
    GL_RUN(test_power_on_sequence);
    GL_RUN(test_known_image_exact_bytes);
    GL_RUN(test_only_changed_lines_are_sent);
    GL_RUN(test_full_frame_length_and_time);
    GL_RUN(test_random_images_all_mountings);
    GL_RUN(test_mounting_addresses);
    GL_RUN(test_ui_screen_reaches_panel_inside_aperture);
    GL_RUN(test_power_off_sequence_and_state);
    GL_RUN(test_model_catches_protocol_errors);
    return gl_test_summary();
}
