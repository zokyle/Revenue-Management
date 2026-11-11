/* ls013b7dh03.c - Sharp memory LCD driver.  See ls013b7dh03.h. */
#include "ls013b7dh03.h"

#include <string.h>

#include "gl_hal.h"
#include "gl_provisional.h"

void gl_lcd_cfg_defaults(gl_lcd_cfg_t *cfg)
{
    cfg->row0_at_front = (GL_PROV_LCD_ROW0_AT_FRONT != 0);
    cfg->col0_at_left = (GL_PROV_LCD_COL0_AT_LEFT != 0);
}

void gl_lcd_init(gl_lcd_t *lcd, const gl_lcd_cfg_t *cfg)
{
    memset(lcd, 0, sizeof(*lcd));
    if (cfg != NULL) {
        lcd->cfg = *cfg;
    } else {
        gl_lcd_cfg_defaults(&lcd->cfg);
    }
    memset(lcd->shadow, 0xFF, sizeof(lcd->shadow));
    /* all panel inputs low: display off, no inversion needed */
    gl_hal_gpio_write(GL_PIN_LCD_SCS, false);
    gl_hal_gpio_mode(GL_PIN_LCD_SCS, GL_PIN_MODE_OUTPUT_PP);
    gl_hal_gpio_write(GL_PIN_LCD_DISP, false);
    gl_hal_gpio_mode(GL_PIN_LCD_DISP, GL_PIN_MODE_OUTPUT_PP);
    gl_hal_gpio_write(GL_PIN_LCD_EXTCOMIN, false);
    gl_hal_gpio_mode(GL_PIN_LCD_EXTCOMIN, GL_PIN_MODE_OUTPUT_PP);
}

static gl_status_t frame_begin_(void)
{
    const gl_spi_cfg_t spi = { GL_PROV_LCD_SPI_MAX_HZ, 0u, true };
    gl_status_t st = gl_hal_spi_configure(GL_SPI_BUS_1, &spi);
    if (st != GL_OK) {
        return st;
    }
    gl_hal_gpio_write(GL_PIN_LCD_SCS, true);
    gl_hal_delay_us(GL_PROV_LCD_SCS_SETUP_US);
    return GL_OK;
}

static void frame_end_(gl_lcd_t *lcd)
{
    gl_hal_delay_us(GL_PROV_LCD_SCS_HOLD_US);
    gl_hal_gpio_write(GL_PIN_LCD_SCS, false);
    gl_hal_delay_us(GL_PROV_LCD_SCS_LOW_US);
    lcd->frames++;
}

gl_status_t gl_lcd_clear(gl_lcd_t *lcd)
{
    static const uint8_t cmd[2] = { GL_LCD_MODE_CLEAR, 0x00 };
    gl_status_t st = frame_begin_();
    if (st != GL_OK) {
        return st;
    }
    st = gl_hal_spi_transfer(GL_SPI_BUS_1, cmd, NULL, sizeof(cmd));
    frame_end_(lcd);
    if (st == GL_OK) {
        memset(lcd->shadow, 0xFF, sizeof(lcd->shadow));
    }
    return st;
}

gl_status_t gl_lcd_on(gl_lcd_t *lcd)
{
    gl_status_t st = gl_lcd_clear(lcd);
    if (st != GL_OK) {
        return st;
    }
    gl_hal_gpio_mode(GL_PIN_LCD_EXTCOMIN, GL_PIN_MODE_ALTERNATE);
    st = gl_hal_extcomin_start((uint16_t)GL_PROV_LCD_EXTCOMIN_PERIOD_LSE_TICKS);
    if (st != GL_OK) {
        gl_hal_gpio_mode(GL_PIN_LCD_EXTCOMIN, GL_PIN_MODE_OUTPUT_PP);
        return st;
    }
    gl_hal_gpio_write(GL_PIN_LCD_DISP, true);
    lcd->on = true;
    return GL_OK;
}

void gl_lcd_off(gl_lcd_t *lcd)
{
    gl_hal_gpio_write(GL_PIN_LCD_DISP, false);
    gl_hal_extcomin_stop();
    gl_hal_gpio_write(GL_PIN_LCD_EXTCOMIN, false);
    gl_hal_gpio_mode(GL_PIN_LCD_EXTCOMIN, GL_PIN_MODE_OUTPUT_PP);
    lcd->on = false;
}

static uint8_t rev8_(uint8_t b)
{
    b = (uint8_t)(((b & 0xF0u) >> 4) | ((b & 0x0Fu) << 4));
    b = (uint8_t)(((b & 0xCCu) >> 2) | ((b & 0x33u) << 2));
    b = (uint8_t)(((b & 0xAAu) >> 1) | ((b & 0x55u) << 1));
    return b;
}

gl_status_t gl_lcd_update(gl_lcd_t *lcd, const gl_gfx_t *g, unsigned *lines_sent)
{
    uint8_t rows[GL_GFX_H];
    uint8_t line[2u + GL_LCD_LINE_BYTES];
    const uint8_t mode = GL_LCD_MODE_WRITE;
    const uint8_t tail = 0x00;

    if (lines_sent != NULL) {
        *lines_sent = 0;
    }
    if (!lcd->on) {
        return GL_ERR_STATE;
    }
    const unsigned n = gl_gfx_changed_rows(g, lcd->shadow, rows);
    if (n == 0u) {
        return GL_OK;
    }
    gl_status_t st = frame_begin_();
    if (st != GL_OK) {
        return st;
    }
    st = gl_hal_spi_transfer(GL_SPI_BUS_1, &mode, NULL, 1);
    for (unsigned i = 0; i < n && st == GL_OK; i++) {
        const unsigned y = rows[i];
        const uint8_t *src = gl_gfx_row(g, (int)y);
        line[0] = (uint8_t)(lcd->cfg.row0_at_front ? (y + 1u) : (GL_LCD_LINES - y));
        if (lcd->cfg.col0_at_left) {
            memcpy(&line[1], src, GL_LCD_LINE_BYTES);
        } else {
            for (unsigned b = 0; b < GL_LCD_LINE_BYTES; b++) {
                line[1u + b] = rev8_(src[GL_LCD_LINE_BYTES - 1u - b]);
            }
        }
        line[1u + GL_LCD_LINE_BYTES] = 0x00; /* 8 dummy bits */
        st = gl_hal_spi_transfer(GL_SPI_BUS_1, line, NULL, sizeof(line));
        if (st == GL_OK) {
            memcpy(&lcd->shadow[y * (unsigned)GL_GFX_STRIDE], src, GL_LCD_LINE_BYTES);
            lcd->lines++;
        }
    }
    if (st == GL_OK) {
        st = gl_hal_spi_transfer(GL_SPI_BUS_1, &tail, NULL, 1);
    }
    frame_end_(lcd);
    if (st == GL_OK && lines_sent != NULL) {
        *lines_sent = n;
    }
    return st;
}
