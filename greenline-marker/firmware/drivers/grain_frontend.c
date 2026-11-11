/* grain_frontend.c - charlieplexed LED ring + photodiode front end.  See
 * grain_frontend.h. */
#include "grain_frontend.h"

#include <string.h>

#include "gl_hal.h"
#include "gl_provisional.h"

/* PROPOSED wiring: the 8 LED pairs use 8 of the 10 pin pairs of 5 pins, in
 * lexicographic order; (2,4) and (3,4) are unused. */
const uint8_t gl_grain_fe_pair[GL_GRAIN_FE_PAIRS][2] = {
    { 0, 1 }, { 0, 2 }, { 0, 3 }, { 0, 4 }, { 1, 2 }, { 1, 3 }, { 1, 4 }, { 2, 3 }
};

static gl_pin_t cp_pin_(unsigned n)
{
    return (gl_pin_t)((unsigned)GL_PIN_GRAIN_CP0 + n);
}

void gl_grain_fe_led_pins(unsigned led, uint8_t *anode, uint8_t *cathode)
{
    const unsigned k = led % GL_GRAIN_FE_PAIRS;
    const bool red = (led % 16u) < 8u;
    const bool low_is_anode = (red == (GL_PROV_GRAIN_RED_ANODE_ON_LOW_PIN != 0));
    *anode = low_is_anode ? gl_grain_fe_pair[k][0] : gl_grain_fe_pair[k][1];
    *cathode = low_is_anode ? gl_grain_fe_pair[k][1] : gl_grain_fe_pair[k][0];
}

void gl_grain_fe_all_off(void)
{
    for (unsigned n = 0; n < GL_GRAIN_FE_PINS; n++) {
        gl_hal_gpio_mode(cp_pin_(n), GL_PIN_MODE_ANALOG);
    }
}

void gl_grain_fe_led_on(int led)
{
    uint8_t anode, cathode;
    /* break before make: never two LEDs lit, not even for an instant */
    gl_grain_fe_all_off();
    if (led < 0 || led >= (int)GL_GRAIN_LEDS) {
        return;
    }
    gl_grain_fe_led_pins((unsigned)led, &anode, &cathode);
    gl_hal_gpio_write(cp_pin_(cathode), false);
    gl_hal_gpio_mode(cp_pin_(cathode), GL_PIN_MODE_OUTPUT_PP);
    gl_hal_gpio_write(cp_pin_(anode), true);
    gl_hal_gpio_mode(cp_pin_(anode), GL_PIN_MODE_OUTPUT_PP);
}

gl_status_t gl_grain_fe_power(bool on)
{
    gl_status_t st;
    if (!on) {
        gl_grain_fe_all_off();
        (void)gl_hal_opamp_enable(false);
        return gl_hal_adc_power(false);
    }
    gl_grain_fe_all_off();
    gl_hal_gpio_mode(GL_PIN_OPAMP_VINP, GL_PIN_MODE_ANALOG);
    gl_hal_gpio_mode(GL_PIN_OPAMP_VINM, GL_PIN_MODE_ANALOG);
    gl_hal_gpio_mode(GL_PIN_OPAMP_VOUT, GL_PIN_MODE_ANALOG);
    st = gl_hal_adc_power(true);
    if (st == GL_OK) {
        st = gl_hal_opamp_enable(true);
    }
    if (st != GL_OK) {
        (void)gl_hal_opamp_enable(false);
        (void)gl_hal_adc_power(false);
        return st;
    }
    gl_hal_delay_ms(GL_PROV_GRAIN_POWER_SETTLE_MS);
    return GL_OK;
}

static gl_status_t sample_(uint16_t *counts)
{
    gl_hal_delay_us(GL_PROV_GRAIN_SETTLE_US);
    return gl_hal_adc_read(GL_ADC_CH_GRAIN_TIA, (uint16_t)GL_PROV_GRAIN_ADC_AVG,
                           (uint16_t)GL_PROV_GRAIN_ADC_SAMPLE_US, counts);
}

/* LED measured at step i (0..15) of a cycle: red and NIR of a pair back to
 * back, pairs ascending on even cycles and descending on odd ones. */
static unsigned scan_led_(unsigned cycle, unsigned i)
{
    const unsigned step = ((cycle & 1u) == 0u) ? i : (15u - i);
    const unsigned pair = step / 2u;
    return ((step & 1u) == 0u) ? pair : (8u + pair);
}

gl_status_t gl_grain_fe_measure_cycle(gl_grain_raw_t *raw, unsigned cycle)
{
    gl_status_t st = GL_OK;
    if (raw == NULL || cycle >= GL_GRAIN_MAX_CYCLES) {
        return GL_ERR_PARAM;
    }
    for (unsigned i = 0; i < GL_GRAIN_LEDS && st == GL_OK; i++) {
        const unsigned led = scan_led_(cycle, i);
        gl_grain_sample_t *s = &raw->s[cycle][led];
        gl_grain_fe_all_off();
        st = sample_(&s->dark1);
        if (st == GL_OK) {
            gl_grain_fe_led_on((int)led);
            st = sample_(&s->on);
        }
        gl_grain_fe_all_off();
        if (st == GL_OK) {
            st = sample_(&s->dark2);
        }
    }
    gl_grain_fe_all_off();
    return st;
}

gl_status_t gl_grain_fe_measure(gl_grain_raw_t *raw, unsigned cycles)
{
    if (raw == NULL || cycles < 1u || cycles > GL_GRAIN_MAX_CYCLES) {
        return GL_ERR_PARAM;
    }
    memset(raw, 0, sizeof(*raw));
    raw->adc_full_scale = (uint16_t)GL_HAL_ADC_FULL_SCALE;
    gl_status_t st = gl_grain_fe_power(true);
    for (unsigned c = 0; c < cycles && st == GL_OK; c++) {
        st = gl_grain_fe_measure_cycle(raw, c);
        if (st == GL_OK) {
            raw->cycles = (uint8_t)(c + 1u);
        }
    }
    (void)gl_grain_fe_power(false);
    return st;
}
