/*
 * test_pins.c - consistency of the generated STM32U585 pin map
 * (hal/stm32u5/gl_pins.h) with the logical pins of hal/gl_hal.h and with
 * the pin facts of DESIGN_SPEC section 4.
 *
 * The STM32 backend itself is not compiled in this repository; its pin
 * table is, because it is plain data.  The DESIGN_SPEC rows are written out
 * again here by hand, independently of tools/gen_pins.py.
 */
#include "gl_test.h"

#include "gl_hal.h"
#include "gl_pins.h"
#include "gl_provisional.h"

typedef struct {
    int logical;
    char port;
    int pin;
    int pad;
    int fn;
    int af;
    int src;
} pin_row_t;

#define ROW(logical, port, pin, pad, fn, af, src) { (int)(logical), #port[0], pin, pad, fn, af, src },
static const pin_row_t rows_[] = { GL_PINS_TABLE(ROW) };

static const pin_row_t *find_(gl_pin_t p)
{
    return &rows_[(int)p];
}

GL_TEST(test_table_matches_the_logical_pins)
{
    GL_CHECK_EQ(GL_ARRAY_LEN(rows_), GL_PIN_COUNT);
    GL_CHECK_EQ(GL_PINS_COUNT, GL_PIN_COUNT);
    for (size_t i = 0; i < GL_ARRAY_LEN(rows_); i++) {
        GL_CHECK_EQ(rows_[i].logical, (int)i); /* rows in the order of gl_pin_t */
        GL_CHECK(rows_[i].port >= 'A' && rows_[i].port <= 'H');
        GL_CHECK(rows_[i].pin >= 0 && rows_[i].pin <= 15);
        GL_CHECK(rows_[i].pad >= 1 && rows_[i].pad <= 64);
        GL_CHECK(rows_[i].af >= 0 && rows_[i].af <= 15);
    }
}

GL_TEST(test_no_pad_or_port_pin_used_twice)
{
    /* supply, reset, crystal and debug pads of the LQFP-64.  (Pad 60, PH3-BOOT0,
     * was in this list until rev C2: it now carries NTC_BIAS, see below.) */
    static const int reserved[] = { 1, 3, 4, 7, 12, 13, 18, 19, 30, 31, 32, 46, 47, 48, 49, 63, 64 };
    for (size_t i = 0; i < GL_ARRAY_LEN(rows_); i++) {
        for (size_t j = i + 1; j < GL_ARRAY_LEN(rows_); j++) {
            GL_CHECK(rows_[i].pad != rows_[j].pad);
            GL_CHECK(!(rows_[i].port == rows_[j].port && rows_[i].pin == rows_[j].pin));
            /* one EXTI line per pin NUMBER: two interrupt pins must differ in it */
            if (rows_[i].fn == GL_PINFN_EXTI && rows_[j].fn == GL_PINFN_EXTI) {
                GL_CHECK(rows_[i].pin != rows_[j].pin);
            }
        }
        for (size_t k = 0; k < GL_ARRAY_LEN(reserved); k++) {
            GL_CHECK(rows_[i].pad != reserved[k]);
        }
        /* SWD (PA13, PA14) and the 32 kHz crystal (PC14, PC15) stay free.
         * BOOT0 (PH3) was free until rev C2; the only signal allowed on it
         * is NTC_BIAS (test_rev_c2_pwdn_charger_and_ntc_pins says why) */
        GL_CHECK(!(rows_[i].port == 'A' && (rows_[i].pin == 13 || rows_[i].pin == 14)));
        GL_CHECK(!(rows_[i].port == 'C' && (rows_[i].pin == 14 || rows_[i].pin == 15)));
        if (rows_[i].port == 'H' && rows_[i].pin == 3) {
            GL_CHECK_EQ(rows_[i].logical, (int)GL_PIN_NTC_BIAS);
        }
    }
}

GL_TEST(test_design_spec_rows)
{
    /* DESIGN_SPEC rev C section 4, copied by hand: pin, pad, AF */
    static const struct {
        gl_pin_t logical;
        char port;
        int pin, pad, af;
    } spec[] = {
        { GL_PIN_CAM_D0, 'C', 6, 37, 10 },     { GL_PIN_CAM_D1, 'C', 7, 38, 10 },
        { GL_PIN_CAM_D2, 'C', 8, 39, 10 },     { GL_PIN_CAM_D3, 'C', 9, 40, 4 },
        { GL_PIN_CAM_D4, 'C', 11, 52, 10 },    { GL_PIN_CAM_D5, 'B', 6, 58, 10 },
        { GL_PIN_CAM_D6, 'B', 8, 61, 10 },     { GL_PIN_CAM_D7, 'B', 9, 62, 10 },
        { GL_PIN_CAM_PIXCLK, 'A', 6, 22, 4 },  { GL_PIN_CAM_HREF, 'A', 4, 20, 10 },
        { GL_PIN_CAM_VSYNC, 'B', 7, 59, 10 },  { GL_PIN_CAM_XVCLK, 'A', 8, 41, 0 },
        { GL_PIN_SPI1_MISO, 'B', 4, 56, 5 },   { GL_PIN_USB_DM, 'A', 11, 44, 10 },
        { GL_PIN_USB_DP, 'A', 12, 45, 10 },    { GL_PIN_LCD_EXTCOMIN, 'B', 2, 28, 1 },
    };
    for (size_t i = 0; i < GL_ARRAY_LEN(spec); i++) {
        const pin_row_t *r = find_(spec[i].logical);
        GL_CHECK_EQ(r->port, spec[i].port);
        GL_CHECK_EQ(r->pin, spec[i].pin);
        GL_CHECK_EQ(r->pad, spec[i].pad);
        GL_CHECK_EQ(r->af, spec[i].af);
        GL_CHECK_EQ(r->fn, GL_PINFN_AF);
        GL_CHECK_EQ(r->src, GL_PINSRC_SPEC);
    }
    /* op-amp pins (verified in docs/research/bom-verification-ics.md) */
    GL_CHECK(find_(GL_PIN_OPAMP_VINP)->port == 'A' && find_(GL_PIN_OPAMP_VINP)->pin == 0 &&
             find_(GL_PIN_OPAMP_VINP)->pad == 14);
    GL_CHECK(find_(GL_PIN_OPAMP_VINM)->port == 'A' && find_(GL_PIN_OPAMP_VINM)->pin == 1 &&
             find_(GL_PIN_OPAMP_VINM)->pad == 15);
    GL_CHECK(find_(GL_PIN_OPAMP_VOUT)->port == 'A' && find_(GL_PIN_OPAMP_VOUT)->pin == 3 &&
             find_(GL_PIN_OPAMP_VOUT)->pad == 17);
    GL_CHECK_EQ(GL_PINS_ADC_CH_GRAIN_TIA, 8); /* PA3 = ADC1_IN8 */
}

GL_TEST(test_function_kinds)
{
    unsigned proposed = 0, spec = 0;
    /* the three SCCB lines are bit-banged open-drain pins */
    GL_CHECK_EQ(find_(GL_PIN_CAM_SCCB_SDA)->fn, GL_PINFN_SCCB);
    GL_CHECK_EQ(find_(GL_PIN_CAM_L_SCL)->fn, GL_PINFN_SCCB);
    GL_CHECK_EQ(find_(GL_PIN_CAM_R_SCL)->fn, GL_PINFN_SCCB);
    /* interrupt inputs */
    GL_CHECK_EQ(find_(GL_PIN_IMU_INT1)->fn, GL_PINFN_EXTI);
    GL_CHECK_EQ(find_(GL_PIN_IMU_INT2)->fn, GL_PINFN_EXTI);
    GL_CHECK_EQ(find_(GL_PIN_VBUS_SENSE)->fn, GL_PINFN_EXTI);
    GL_CHECK_EQ(find_(GL_PIN_CHG_STAT)->fn, GL_PINFN_EXTI);
    /* analog */
    GL_CHECK_EQ(find_(GL_PIN_VBAT_SENSE)->fn, GL_PINFN_ANALOG);
    GL_CHECK_EQ(find_(GL_PIN_OPAMP_VOUT)->fn, GL_PINFN_ANALOG);
    /* every camera-facing pin exists and none of them is an interrupt pin */
    for (int p = (int)GL_PIN_CAM_FACING_FIRST; p <= (int)GL_PIN_CAM_FACING_LAST; p++) {
        GL_CHECK(find_((gl_pin_t)p)->fn != GL_PINFN_EXTI);
    }
    /* both SPI buses are complete alternate-function groups */
    GL_CHECK(find_(GL_PIN_SPI1_SCK)->fn == GL_PINFN_AF && find_(GL_PIN_SPI1_MOSI)->fn == GL_PINFN_AF);
    GL_CHECK(find_(GL_PIN_SPI2_SCK)->fn == GL_PINFN_AF && find_(GL_PIN_SPI2_MOSI)->fn == GL_PINFN_AF &&
             find_(GL_PIN_SPI2_MISO)->fn == GL_PINFN_AF);
    for (size_t i = 0; i < GL_ARRAY_LEN(rows_); i++) {
        if (rows_[i].src == GL_PINSRC_PROPOSED) {
            proposed++;
        } else {
            spec++;
        }
    }
    printf("    %u pins: %u from DESIGN_SPEC (verified pads and alternate functions), %u PROPOSED "
           "by this firmware (no netlist yet)\n", (unsigned)GL_ARRAY_LEN(rows_), spec, proposed);
    GL_CHECK_EQ(spec, 19u);
}

/* Review finding: the firmware offers "reboot to ROM DFU"; the ROM
 * bootloader drives some pins as push-pull outputs (idle-high TX, MISO)
 * while the camera rail is off.  CAM_L_PWDN was proposed on PC10
 * (USART3_TX).  The pin list is from memory of AN2606 in both the generator
 * and here (written out again by hand): it must be checked against the
 * document, which is why the table also lives in the generated header. */
GL_TEST(test_rom_bootloader_pins_are_not_camera_facing_outputs)
{
    typedef struct {
        char port;
        int pin;
        const char *fn;
        int drives;
    } boot_row_t;
#define BROW(port, pin, fn, drives) { #port[0], pin, #fn, drives },
    static const boot_row_t boot[] = { GL_PINS_BOOTLOADER_TABLE(BROW) };
#undef BROW
    /* the outputs, by hand: USART1/2/3 TX, SPI1/SPI2 MISO, FDCAN1 TX */
    static const struct {
        char port;
        int pin;
    } outputs[] = { { 'A', 9 }, { 'A', 2 }, { 'C', 10 }, { 'A', 6 }, { 'B', 14 }, { 'B', 9 } };
    unsigned n_out = 0, spec_conflicts = 0;

    for (size_t i = 0; i < GL_ARRAY_LEN(boot); i++) {
        bool by_hand = false;
        for (size_t k = 0; k < GL_ARRAY_LEN(outputs); k++) {
            by_hand = by_hand || (boot[i].port == outputs[k].port && boot[i].pin == outputs[k].pin);
        }
        GL_CHECK_EQ(boot[i].drives != 0, by_hand);
        n_out += (boot[i].drives != 0) ? 1u : 0u;
    }
    GL_CHECK_EQ(n_out, GL_ARRAY_LEN(outputs));

    for (int p = (int)GL_PIN_CAM_FACING_FIRST; p <= (int)GL_PIN_CAM_FACING_LAST; p++) {
        const pin_row_t *r = find_((gl_pin_t)p);
        for (size_t k = 0; k < GL_ARRAY_LEN(outputs); k++) {
            if (r->port == outputs[k].port && r->pin == outputs[k].pin) {
                /* only the two rows DESIGN_SPEC fixes may be here */
                GL_CHECK_EQ(r->src, GL_PINSRC_SPEC);
                GL_CHECK(p == (int)GL_PIN_CAM_D7 || p == (int)GL_PIN_CAM_PIXCLK);
                spec_conflicts++;
            }
        }
    }
    GL_CHECK_EQ(spec_conflicts, 2u); /* PB9 = D7 and PA6 = PIXCLK: release-gate items */
    /* the pin that used to be CAM_L_PWDN (PC10, USART3_TX) carries no
     * camera-facing net: since rev C2 it is a grain charlieplex pin */
    for (size_t i = 0; i < GL_ARRAY_LEN(rows_); i++) {
        if (rows_[i].port == 'C' && rows_[i].pin == 10) {
            GL_CHECK_EQ(rows_[i].logical, (int)GL_PIN_GRAIN_CP4);
        }
    }
    GL_CHECK(find_(GL_PIN_CAM_L_PWDN)->port == 'H' && find_(GL_PIN_CAM_L_PWDN)->pin == 0 &&
             find_(GL_PIN_CAM_L_PWDN)->pad == 5);
    printf("    %u ROM-bootloader pins (from memory of AN2606), %u driven as outputs; no PROPOSED "
           "camera-facing pin on them; %u SPEC rows are (PB9 = D7, PA6 = PIXCLK): release gate\n",
           (unsigned)GL_ARRAY_LEN(boot), n_out, spec_conflicts);
}

/* DESIGN_SPEC rev C2, section 4: "Each PWDN line ... must not use a pin that
 * the ROM bootloader drives as an output (the USART transmit pins PA9, PA2
 * and PC10 ...)".  The generator reads the three pins from the spec text;
 * here they are written out by hand. */
GL_TEST(test_rev_c2_pwdn_charger_and_ntc_pins)
{
    static const struct {
        char port;
        int pin;
    } usart_tx[] = { { 'A', 9 }, { 'A', 2 }, { 'C', 10 } };
    static const gl_pin_t pwdn[] = { GL_PIN_CAM_L_PWDN, GL_PIN_CAM_R_PWDN };
    static const gl_pin_t chg[] = { GL_PIN_CHG_INHIBIT, GL_PIN_NTC_BIAS, GL_PIN_NTC_SENSE };
    typedef struct {
        char port;
        int pin;
        const char *fn;
        int drives;
    } boot_row_t;
#define BROW(port, pin, fn, drives) { #port[0], pin, #fn, drives },
    static const boot_row_t boot[] = { GL_PINS_BOOTLOADER_TABLE(BROW) };
#undef BROW
    unsigned io_pads = 0;

    for (size_t i = 0; i < GL_ARRAY_LEN(pwdn); i++) {
        const pin_row_t *r = find_(pwdn[i]);
        for (size_t k = 0; k < GL_ARRAY_LEN(usart_tx); k++) {
            GL_CHECK(!(r->port == usart_tx[k].port && r->pin == usart_tx[k].pin));
        }
        GL_CHECK_EQ(r->fn, GL_PINFN_GPIO);
    }
    /* the charger and temperature signals: PROPOSED rows, on no ROM
     * bootloader pin at all (driven or sampled) */
    for (size_t i = 0; i < GL_ARRAY_LEN(chg); i++) {
        const pin_row_t *r = find_(chg[i]);
        GL_CHECK_EQ(r->src, GL_PINSRC_PROPOSED);
        for (size_t k = 0; k < GL_ARRAY_LEN(boot); k++) {
            GL_CHECK(!(r->port == boot[k].port && r->pin == boot[k].pin));
        }
    }
    GL_CHECK_EQ(find_(GL_PIN_CHG_INHIBIT)->fn, GL_PINFN_GPIO);
    GL_CHECK_EQ(find_(GL_PIN_NTC_BIAS)->fn, GL_PINFN_GPIO);
    GL_CHECK_EQ(find_(GL_PIN_NTC_SENSE)->fn, GL_PINFN_ANALOG);
    GL_CHECK_EQ(GL_PINS_ADC_CH_CELL_NTC, 13); /* PC4 = ADC1_IN13, from memory */
    GL_CHECK(find_(GL_PIN_NTC_SENSE)->port == 'C' && find_(GL_PIN_NTC_SENSE)->pin == 4);
    /* the pin budget: 46 I/O pads plus PH3-BOOT0, which takes NTC_BIAS */
    for (size_t i = 0; i < GL_ARRAY_LEN(rows_); i++) {
        io_pads += (rows_[i].pad != 60) ? 1u : 0u;
    }
    GL_CHECK_EQ(io_pads, 46u);
    GL_CHECK(find_(GL_PIN_NTC_BIAS)->port == 'H' && find_(GL_PIN_NTC_BIAS)->pin == 3 &&
             find_(GL_PIN_NTC_BIAS)->pad == 60);
    printf("    rev C2: PWDN on P%c%d and P%c%d (not PA9 / PA2 / PC10); CHG_INHIBIT P%c%d, NTC_BIAS "
           "P%c%d (BOOT0), NTC_SENSE P%c%d: PROPOSED, on no ROM bootloader pin; %u signals on the "
           "46 I/O pads, 1 on BOOT0\n",
           find_(GL_PIN_CAM_L_PWDN)->port, find_(GL_PIN_CAM_L_PWDN)->pin,
           find_(GL_PIN_CAM_R_PWDN)->port, find_(GL_PIN_CAM_R_PWDN)->pin,
           find_(GL_PIN_CHG_INHIBIT)->port, find_(GL_PIN_CHG_INHIBIT)->pin,
           find_(GL_PIN_NTC_BIAS)->port, find_(GL_PIN_NTC_BIAS)->pin, find_(GL_PIN_NTC_SENSE)->port,
           find_(GL_PIN_NTC_SENSE)->pin, io_pads);
}

/* EXTCOMIN divider and the pull resistors of the reset state, as the
 * generator read them from DESIGN_SPEC rev C2. */
GL_TEST(test_rev_c2_extcomin_divider_and_reset_levels)
{
    typedef struct {
        int logical;
        int level;
    } reset_row_t;
#define RROW(logical, level) { (int)(logical), level },
    static const reset_row_t reset[] = { GL_PINS_RESET_TABLE(RROW) };
#undef RROW
    bool seen[GL_PIN_COUNT];

    GL_CHECK_EQ(GL_PINS_EXTCOMIN_LSE_TICKS, 547);
    GL_CHECK_EQ(GL_PINS_EXTCOMIN_LSE_TICKS, GL_PROV_LCD_EXTCOMIN_PERIOD_LSE_TICKS);
    /* 32768 / 547 = 59.905 Hz: inside 54-65 Hz and inside 1-60 Hz */
    GL_CHECK(32768.0 / (double)GL_PINS_EXTCOMIN_LSE_TICKS > 54.0);
    GL_CHECK(32768.0 / (double)GL_PINS_EXTCOMIN_LSE_TICKS < 60.0);
    GL_CHECK(32768.0 / 546.0 > 60.0); /* why it is not 546 */

    memset(seen, 0, sizeof(seen));
    for (size_t i = 0; i < GL_ARRAY_LEN(reset); i++) {
        seen[reset[i].logical] = true;
        GL_CHECK_EQ(find_((gl_pin_t)reset[i].logical)->fn, GL_PINFN_GPIO);
    }
    GL_CHECK(seen[GL_PIN_LCD_SCS] && seen[GL_PIN_LCD_DISP] && seen[GL_PIN_FLASH_CS] &&
             seen[GL_PIN_IMU_CS] && seen[GL_PIN_CAM_PWR_EN]);
    for (size_t i = 0; i < GL_ARRAY_LEN(reset); i++) {
        /* the inactive level of each: LCD chip select and DISP are active
         * high, the flash and IMU chip selects active low, the rail off */
        const bool want = (reset[i].logical == (int)GL_PIN_FLASH_CS ||
                           reset[i].logical == (int)GL_PIN_IMU_CS);
        GL_CHECK_EQ(reset[i].level != 0, want);
    }
}

int main(void)
{
    GL_RUN(test_table_matches_the_logical_pins);
    GL_RUN(test_no_pad_or_port_pin_used_twice);
    GL_RUN(test_design_spec_rows);
    GL_RUN(test_function_kinds);
    GL_RUN(test_rom_bootloader_pins_are_not_camera_facing_outputs);
    GL_RUN(test_rev_c2_pwdn_charger_and_ntc_pins);
    GL_RUN(test_rev_c2_extcomin_divider_and_reset_levels);
    return gl_test_summary();
}
