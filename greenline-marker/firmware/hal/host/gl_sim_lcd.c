/*
 * gl_sim_lcd.c - model of the Sharp LS013B7DH03 memory LCD for the host
 * simulator.
 *
 * Protocol as documented in docs/research/display.md (confirmed there from
 * four independent open-source drivers, not from the Sharp datasheet):
 * SPI mode 0, chip select ACTIVE HIGH, least significant bit first, at most
 * 1.1 MHz; a frame is
 *     mode byte (first bit M0 = write lines, second M1 = VCOM, third M2 = clear)
 *     for each line: address 1..128, 16 data bytes (1 = white), 8 dummy bits
 *     8 more dummy bits
 * so a k-line update is 1 + 18 k + 1 bytes and a clear is 2 bytes.
 *
 * Timing limits checked (Sharp figures as remembered, NOT verified):
 * chip-select set-up >= 6 us before the first clock, hold >= 2 us after the
 * last, low time >= 2 us between frames.
 *
 * The model stores bytes as the panel would see them: if the bus is
 * (wrongly) configured MSB first, every byte is bit-reversed first, so a
 * driver error shows up as wrong addresses and mirrored pixels and is
 * counted as a violation.
 */
#include <string.h>

#include "gl_sim_internal.h"

#define LCD_MAX_HZ 1100000u
#define LCD_T_SETUP_US 6u
#define LCD_T_HOLD_US 2u
#define LCD_T_LOW_US 2u

static gl_sim_lcd_t L;
static struct {
    bool selected;
    uint64_t t_select;      /* when SCS rose */
    uint64_t t_last_clock;  /* end of the last transfer */
    uint64_t t_deselect;
    bool any_clock;
    bool overflow;
} st_;

static uint8_t rev8_(uint8_t b)
{
    b = (uint8_t)(((b & 0xF0u) >> 4) | ((b & 0x0Fu) << 4));
    b = (uint8_t)(((b & 0xCCu) >> 2) | ((b & 0x33u) << 2));
    b = (uint8_t)(((b & 0xAAu) >> 1) | ((b & 0x55u) << 1));
    return b;
}

void sim_lcd_reset(void)
{
    memset(&L, 0, sizeof(L));
    memset(&st_, 0, sizeof(st_));
    /* the panel memory powers up undefined; use a recognisable pattern */
    memset(L.mem, 0xA5, sizeof(L.mem));
}

const gl_sim_lcd_t *gl_sim_lcd(void)
{
    return &L;
}

void sim_lcd_disp(bool high)
{
    if (high && !L.extcomin) {
        sim_violation(&sim_viol()->lcd, "DISP raised while EXTCOMIN is not running");
    }
    L.disp = high;
}

void sim_lcd_extcomin(bool running, uint16_t period_ticks)
{
    if (!running && L.disp) {
        sim_violation(&sim_viol()->lcd, "EXTCOMIN stopped while DISP is high");
    }
    if (running && (period_ticks < 504u || period_ticks > 607u)) {
        /* 32768 / 607 = 54 Hz, 32768 / 504 = 65 Hz */
        sim_violation(&sim_viol()->lcd, "EXTCOMIN period %u ticks is outside 54-65 Hz",
                      (unsigned)period_ticks);
    }
    L.extcomin = running;
    L.extcomin_period = period_ticks;
}

static void frame_end_(void)
{
    const uint8_t *f = L.last_frame;
    const unsigned n = L.last_frame_len;

    L.frames++;
    if (st_.overflow || n < 2u) {
        sim_violation(&sim_viol()->lcd, "LCD frame of %u bytes%s", n,
                      st_.overflow ? " (overflow)" : "");
        return;
    }
    const uint8_t mode = f[0];
    if ((mode & 0xF8u) != 0u) {
        sim_violation(&sim_viol()->lcd, "LCD mode byte 0x%02X has unknown bits", mode);
        return;
    }
    if ((mode & 0x01u) != 0u) { /* M0: write lines */
        if ((n - 2u) % 18u != 0u || n < 20u) {
            sim_violation(&sim_viol()->lcd, "LCD write frame length %u is not 1 + 18 k + 1", n);
            return;
        }
        const unsigned lines = (n - 2u) / 18u;
        for (unsigned i = 0; i < lines; i++) {
            const uint8_t *ln = &f[1u + 18u * i];
            if (ln[0] < 1u || ln[0] > 128u) {
                sim_violation(&sim_viol()->lcd, "LCD line address %u out of range", ln[0]);
                continue;
            }
            memcpy(&L.mem[(unsigned)(ln[0] - 1u) * 16u], &ln[1], 16);
            L.lines_written++;
        }
    } else if ((mode & 0x04u) != 0u) { /* M2: clear all */
        if (n != 2u) {
            sim_violation(&sim_viol()->lcd, "LCD clear frame of %u bytes (expected 2)", n);
        }
        memset(L.mem, 0xFF, sizeof(L.mem));
        L.clears++;
    } else if (n != 2u) { /* maintain / VCOM */
        sim_violation(&sim_viol()->lcd, "LCD maintain frame of %u bytes (expected 2)", n);
    }
}

void sim_lcd_cs(bool asserted)
{
    const uint64_t now = sim_now();
    if (asserted) {
        if (st_.t_deselect != 0u && now - st_.t_deselect < LCD_T_LOW_US) {
            sim_violation(&sim_viol()->lcd, "LCD chip select low for only %u us",
                          (unsigned)(now - st_.t_deselect));
        }
        st_.selected = true;
        st_.t_select = now;
        st_.any_clock = false;
        st_.overflow = false;
        L.last_frame_len = 0;
    } else if (st_.selected) {
        if (st_.any_clock && now - st_.t_last_clock < LCD_T_HOLD_US) {
            sim_violation(&sim_viol()->lcd, "LCD chip-select hold time %u us",
                          (unsigned)(now - st_.t_last_clock));
        }
        st_.selected = false;
        st_.t_deselect = now;
        frame_end_();
    }
}

void sim_lcd_xfer(const gl_spi_cfg_t *cfg, const uint8_t *tx, uint8_t *rx, size_t len)
{
    const uint64_t now = sim_now();
    (void)rx; /* the panel has no data output */
    if (!st_.any_clock) {
        if (now - st_.t_select < LCD_T_SETUP_US) {
            sim_violation(&sim_viol()->lcd, "LCD chip-select set-up time %u us",
                          (unsigned)(now - st_.t_select));
        }
        if (cfg->mode != 0u) {
            sim_violation(&sim_viol()->lcd, "LCD addressed in SPI mode %u (needs 0)", cfg->mode);
        }
        if (!cfg->lsb_first) {
            sim_violation(&sim_viol()->lcd, "LCD addressed MSB first");
        }
        if (cfg->max_hz > LCD_MAX_HZ) {
            sim_violation(&sim_viol()->lcd, "LCD clocked at %u Hz", (unsigned)cfg->max_hz);
        }
    }
    st_.any_clock = true;
    for (size_t i = 0; i < len; i++) {
        if (L.last_frame_len >= sizeof(L.last_frame)) {
            st_.overflow = true;
            break;
        }
        L.last_frame[L.last_frame_len++] = cfg->lsb_first ? tx[i] : rev8_(tx[i]);
    }
    /* the transfer ends len * 8 clocks later; the core advances the clock
     * after this call, so remember the END time for the hold check */
    st_.t_last_clock = now + ((uint64_t)len * 8u * 1000000u + cfg->max_hz - 1u) / cfg->max_hz;
}
