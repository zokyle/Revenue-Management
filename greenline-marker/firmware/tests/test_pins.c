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
    /* supply, reset, crystal, debug and boot pads of the LQFP-64 */
    static const int reserved[] = { 1, 3, 4, 7, 12, 13, 18, 19, 30, 31, 32, 46, 47, 48, 49, 60, 63, 64 };
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
        /* SWD (PA13, PA14), the 32 kHz crystal (PC14, PC15) and BOOT0 (PH3) stay free */
        GL_CHECK(!(rows_[i].port == 'A' && (rows_[i].pin == 13 || rows_[i].pin == 14)));
        GL_CHECK(!(rows_[i].port == 'C' && (rows_[i].pin == 14 || rows_[i].pin == 15)));
        GL_CHECK(!(rows_[i].port == 'H' && rows_[i].pin == 3));
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

int main(void)
{
    GL_RUN(test_table_matches_the_logical_pins);
    GL_RUN(test_no_pad_or_port_pin_used_twice);
    GL_RUN(test_design_spec_rows);
    GL_RUN(test_function_kinds);
    return gl_test_summary();
}
