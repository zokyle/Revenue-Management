/*
 * ls013b7dh03.h - Sharp LS013B7DH03 128 x 128 memory LCD on SPI1.
 *
 * Protocol (docs/research/display.md; confirmed there from four open-source
 * drivers, not from the Sharp datasheet): SPI mode 0, chip select ACTIVE
 * HIGH, bits LSB first, at most 1 MHz.  One chip-select frame is
 *
 *     mode byte      first bit on the wire M0 = write lines (0x01 on an
 *                    LSB-first bus), second M1 = VCOM (0x02, ignored
 *                    because EXTMODE is strapped high), third M2 = clear
 *                    all (0x04)
 *     per line       line address 1..128, 16 data bytes (1 = white),
 *                    8 dummy bits
 *     at the end     8 more dummy bits
 *
 * so an update of k lines is 1 + 18 k + 1 bytes (2306 for a full frame,
 * 18.4 ms at 1 MHz) and a clear is 2 bytes.  Only lines that differ from
 * what the panel already shows are sent.
 *
 * VCOM: EXTMODE is strapped high and EXTCOMIN is a hardware 60 Hz square
 * wave from LPTIM1 (gl_hal_extcomin_start); the driver only starts and
 * stops that timer and drives DISP.  The inversion never stops while DISP
 * is high: on = start the timer, then DISP high; off = DISP low, then stop
 * the timer.
 *
 * The framebuffer contract with core/gl_gfx.h: row y of gl_gfx_t is 16
 * bytes whose bit 0 is the leftmost pixel, so a row goes out unchanged on
 * the LSB-first bus.  How screen rows / columns map to line addresses and
 * bit order depends on how the panel is mounted (PROVISIONAL:
 * GL_PROV_LCD_ROW0_AT_FRONT, GL_PROV_LCD_COL0_AT_LEFT); both mappings are
 * implemented and selected in gl_lcd_cfg_t.
 *
 * The driver keeps a shadow copy of the panel contents (2048 bytes).
 * RAM: sizeof(gl_lcd_t) = 2060 bytes.  Stack: gl_lcd_update() about 170
 * bytes (128-entry row list + one 18-byte line buffer).
 */
#ifndef GL_LS013B7DH03_H
#define GL_LS013B7DH03_H

#include "gl_gfx.h"
#include "gl_types.h"

#define GL_LCD_MODE_WRITE 0x01u /* M0, first bit on the wire */
#define GL_LCD_MODE_VCOM  0x02u /* M1 */
#define GL_LCD_MODE_CLEAR 0x04u /* M2 */
#define GL_LCD_LINES 128u
#define GL_LCD_LINE_BYTES 16u

typedef struct {
    bool row0_at_front; /**< screen row 0 (top = marker front) is line address 1 */
    bool col0_at_left;  /**< screen column 0 is the first bit of a line */
} gl_lcd_cfg_t;

typedef struct {
    gl_lcd_cfg_t cfg;
    uint8_t shadow[GL_GFX_BYTES]; /**< what the panel shows, in SCREEN orientation */
    bool on;
    uint32_t frames;              /**< chip-select frames sent */
    uint32_t lines;               /**< lines sent */
} gl_lcd_t;

/** Mounting from core/gl_provisional.h. */
void gl_lcd_cfg_defaults(gl_lcd_cfg_t *cfg);

/** Drive SCS, DISP and EXTCOMIN low (display off).  `cfg` NULL = defaults. */
void gl_lcd_init(gl_lcd_t *lcd, const gl_lcd_cfg_t *cfg);

/** Clear the panel memory, start EXTCOMIN, raise DISP.  The shadow is all
 *  white afterwards. */
gl_status_t gl_lcd_on(gl_lcd_t *lcd);

/** DISP low, EXTCOMIN stopped and driven low.  The panel memory is kept by
 *  the panel but the driver does not rely on it. */
void gl_lcd_off(gl_lcd_t *lcd);

/** Send the lines of `g` that differ from the shadow, in one frame, and
 *  update the shadow.  `lines_sent` may be NULL.  GL_ERR_STATE if the
 *  display is off. */
gl_status_t gl_lcd_update(gl_lcd_t *lcd, const gl_gfx_t *g, unsigned *lines_sent);

/** Clear-all command; shadow becomes all white.  Works with DISP low. */
gl_status_t gl_lcd_clear(gl_lcd_t *lcd);

#endif /* GL_LS013B7DH03_H */
