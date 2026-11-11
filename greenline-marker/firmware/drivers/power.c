/* power.c - battery, charger status, charge gating.  See power.h. */
#include "power.h"

#include <string.h>

#include "gl_hal.h"
#include "gl_provisional.h"

/* 4 samples of 20 us: the 100 nF reservoir supplies the sampling charge. */
#define BATT_ADC_AVG 4u
#define BATT_ADC_SAMPLE_US 20u

void gl_power_init(gl_power_t *p)
{
    memset(p, 0, sizeof(*p));
    gl_hal_gpio_write(GL_PIN_CHG_PROG_EN, true); /* released: charging off */
    gl_hal_gpio_mode(GL_PIN_CHG_PROG_EN, GL_PIN_MODE_OUTPUT_OD);
    gl_hal_gpio_mode(GL_PIN_CHG_STAT, GL_PIN_MODE_INPUT_PULLUP);
    gl_hal_gpio_mode(GL_PIN_VBUS_SENSE, GL_PIN_MODE_INPUT);
    gl_hal_gpio_mode(GL_PIN_VBAT_SENSE, GL_PIN_MODE_ANALOG);
    gl_power_poll_pins(p);
}

uint16_t gl_power_counts_to_mv(uint16_t counts, uint16_t vdda_mv)
{
    const float mv = (float)counts / (float)GL_HAL_ADC_FULL_SCALE * (float)vdda_mv *
                     GL_PROV_BATT_DIVIDER_RATIO;
    return (mv > 65535.0f) ? (uint16_t)65535u : (uint16_t)(mv + 0.5f);
}

uint8_t gl_power_percent(uint16_t batt_mv)
{
    if (batt_mv <= GL_PROV_BATT_EMPTY_MV) {
        return 0;
    }
    if (batt_mv >= GL_PROV_BATT_FULL_MV) {
        return 100;
    }
    return (uint8_t)(((uint32_t)(batt_mv - GL_PROV_BATT_EMPTY_MV) * 100u) /
                     (GL_PROV_BATT_FULL_MV - GL_PROV_BATT_EMPTY_MV));
}

gl_status_t gl_power_measure(gl_power_t *p)
{
    uint16_t counts = 0;
    gl_status_t st = gl_hal_adc_power(true);
    if (st != GL_OK) {
        return st;
    }
    const uint16_t vdda = gl_hal_adc_vdda_mv();
    st = gl_hal_adc_read(GL_ADC_CH_VBAT_DIV, BATT_ADC_AVG, BATT_ADC_SAMPLE_US, &counts);
    (void)gl_hal_adc_power(false);
    if (st != GL_OK) {
        return st;
    }
    if (vdda == 0u) {
        return GL_ERR_IO;
    }
    p->batt_mv = gl_power_counts_to_mv(counts, vdda);
    p->percent = gl_power_percent(p->batt_mv);
    p->low = p->batt_mv < GL_PROV_BATT_LOW_MV;
    p->critical = p->batt_mv < GL_PROV_BATT_CRITICAL_MV;
    return GL_OK;
}

void gl_power_poll_pins(gl_power_t *p)
{
    p->vbus = gl_hal_gpio_read(GL_PIN_VBUS_SENSE);
    p->charging = !gl_hal_gpio_read(GL_PIN_CHG_STAT);
}

bool gl_power_charge_gate(gl_power_t *p, float temp_c, bool temp_valid)
{
    if (!temp_valid) {
        p->temp_ok = false;
    } else if (p->temp_ok) {
        /* stay enabled until the limit itself is crossed */
        p->temp_ok = (temp_c >= GL_PROV_CHARGE_TEMP_MIN_C) && (temp_c <= GL_PROV_CHARGE_TEMP_MAX_C);
    } else {
        /* re-enable only well inside the window */
        p->temp_ok = (temp_c >= GL_PROV_CHARGE_TEMP_MIN_C + GL_PROV_CHARGE_TEMP_HYST_C) &&
                     (temp_c <= GL_PROV_CHARGE_TEMP_MAX_C - GL_PROV_CHARGE_TEMP_HYST_C);
    }
    const bool enable = p->vbus && p->temp_ok;
    gl_hal_gpio_write(GL_PIN_CHG_PROG_EN, !enable); /* low = allowed */
    p->charge_enabled = enable;
    return enable;
}
