/* power.c - battery, cell temperature, charger status, charge gate.  See power.h. */
#include "power.h"

#include <math.h>
#include <string.h>

#include "gl_hal.h"
#include "gl_provisional.h"

/* 4 samples of 20 us: the 100 nF reservoir supplies the sampling charge. */
#define BATT_ADC_AVG 4u
#define BATT_ADC_SAMPLE_US 20u
/* The internal temperature sensor needs a long sampling time (5 us minimum
 * on this family, from memory); 8 samples of 20 us. */
#define MCU_TEMP_ADC_AVG 8u
#define MCU_TEMP_ADC_SAMPLE_US 20u
/* The check of the sense pin with the bias released: 2 samples. */
#define NTC_IDLE_ADC_AVG 2u

#define KELVIN_0C 273.15f
#define KELVIN_25C 298.15f

/* CHG_INHIBIT.  Stop: latch low first, then open drain (the pin never
 * drives high).  Release: latch high (high-Z while still open drain), then
 * back to analog, the state the pin has after reset. */
static void inhibit_(gl_power_t *p, bool stop)
{
    if (stop) {
        gl_hal_gpio_write(GL_PIN_CHG_INHIBIT, false);
        gl_hal_gpio_mode(GL_PIN_CHG_INHIBIT, GL_PIN_MODE_OUTPUT_OD);
    } else {
        gl_hal_gpio_write(GL_PIN_CHG_INHIBIT, true);
        gl_hal_gpio_mode(GL_PIN_CHG_INHIBIT, GL_PIN_MODE_ANALOG);
    }
    p->inhibit = stop;
    p->charge_enabled = p->vbus && !stop;
}

void gl_power_init(gl_power_t *p)
{
    memset(p, 0, sizeof(*p));
    p->chg_reason = (uint8_t)GL_CHG_NO_VBUS;
    p->ntc_fault = (uint8_t)GL_NTC_ADC; /* nothing measured yet */
    /* CHG_INHIBIT and NTC_BIAS: not touched (see power.h) */
    gl_hal_gpio_mode(GL_PIN_CHG_STAT, GL_PIN_MODE_INPUT_PULLUP);
    gl_hal_gpio_mode(GL_PIN_VBUS_SENSE, GL_PIN_MODE_INPUT);
    gl_hal_gpio_mode(GL_PIN_VBAT_SENSE, GL_PIN_MODE_ANALOG);
    gl_hal_gpio_mode(GL_PIN_NTC_SENSE, GL_PIN_MODE_ANALOG);
    gl_power_poll_pins(p);
    p->charge_enabled = p->vbus; /* the hardware default */
}

uint16_t gl_power_counts_to_mv(uint16_t counts, uint16_t vdda_mv)
{
    const float mv = (float)counts / (float)GL_HAL_ADC_FULL_SCALE * (float)vdda_mv *
                     GL_PROV_BATT_DIVIDER_RATIO;
    uint16_t out = 65535u;
    if (mv < 65535.0f) {
        out = (uint16_t)(mv + 0.5f);
    }
    return out;
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

float gl_power_ntc_counts_to_c(uint16_t counts, uint8_t *fault)
{
    const float x = (float)counts / (float)GL_HAL_ADC_FULL_SCALE;
    uint8_t f = (uint8_t)GL_NTC_OK;
    float t = NAN;
    if (x >= GL_PROV_NTC_OPEN_FRACTION) {
        f = (uint8_t)GL_NTC_OPEN;
    } else if (x <= GL_PROV_NTC_SHORT_FRACTION) {
        f = (uint8_t)GL_NTC_SHORT;
    } else {
        /* R / R25, then 1 / T = 1 / T25 + ln(R / R25) / B */
        const float ratio = (GL_PROV_NTC_SERIES_OHM / GL_PROV_NTC_R25_OHM) * x / (1.0f - x);
        t = 1.0f / (1.0f / KELVIN_25C + logf(ratio) / GL_PROV_NTC_B_K) - KELVIN_0C;
    }
    if (fault != NULL) {
        *fault = f;
    }
    return t;
}

/* One MCU die temperature reading (the ADC is on, VDDA is known). */
static gl_status_t mcu_temp_(gl_power_t *p, uint16_t vdda)
{
    uint16_t counts = 0;
    const gl_status_t st =
        gl_hal_adc_read(GL_ADC_CH_MCU_TEMP, MCU_TEMP_ADC_AVG, MCU_TEMP_ADC_SAMPLE_US, &counts);
    p->mcu_temp_valid = false;
    if (st == GL_OK && vdda != 0u) {
        const float t = gl_hal_adc_mcu_temp_c(counts, vdda);
        /* a reading outside what silicon survives is a broken measurement */
        if (isfinite(t) && t > -60.0f && t < 150.0f) {
            p->mcu_temp_c = t;
            p->mcu_temp_valid = true;
        }
    }
    return st;
}

/* One cell temperature reading (the ADC is on).  The bias is driven only
 * between the two gpio calls below; whatever happens it is released again. */
static gl_status_t ntc_(gl_power_t *p)
{
    uint16_t idle = 0, counts = 0;
    uint8_t fault = (uint8_t)GL_NTC_OK;
    gl_status_t st, st_idle;
    float t;

    p->cell_temp_valid = false;
    /* 1. bias released: the NTC holds the pin at ground */
    st_idle = gl_hal_adc_read(GL_ADC_CH_CELL_NTC, NTC_IDLE_ADC_AVG, GL_PROV_NTC_ADC_SAMPLE_US, &idle);
    /* 2. bias on, settle, convert, bias off */
    gl_hal_gpio_write(GL_PIN_NTC_BIAS, true);
    gl_hal_gpio_mode(GL_PIN_NTC_BIAS, GL_PIN_MODE_OUTPUT_PP);
    gl_hal_delay_us(GL_PROV_NTC_SETTLE_US);
    st = gl_hal_adc_read(GL_ADC_CH_CELL_NTC, GL_PROV_NTC_ADC_AVG, GL_PROV_NTC_ADC_SAMPLE_US, &counts);
    gl_hal_gpio_mode(GL_PIN_NTC_BIAS, GL_PIN_MODE_ANALOG);
    gl_hal_gpio_write(GL_PIN_NTC_BIAS, false);
    if (st != GL_OK || st_idle != GL_OK) {
        p->ntc_fault = (uint8_t)GL_NTC_ADC;
        return (st != GL_OK) ? st : st_idle;
    }
    t = gl_power_ntc_counts_to_c(counts, &fault);
    if (fault == (uint8_t)GL_NTC_OK &&
        (float)idle > GL_PROV_NTC_IDLE_MAX_FRACTION * (float)GL_HAL_ADC_FULL_SCALE) {
        fault = (uint8_t)GL_NTC_STUCK;
    }
    p->ntc_fault = fault;
    if (fault == (uint8_t)GL_NTC_OK && isfinite(t)) {
        p->cell_temp_c = t;
        p->cell_temp_valid = true;
    }
    return GL_OK;
}

gl_status_t gl_power_measure_temps(gl_power_t *p)
{
    gl_status_t st, st_t, st_n;

    p->mcu_temp_valid = false;
    p->cell_temp_valid = false;
    p->ntc_fault = (uint8_t)GL_NTC_ADC;
    st = gl_hal_adc_power(true);
    if (st != GL_OK) {
        return st;
    }
    const uint16_t vdda = gl_hal_adc_vdda_mv();
    st_t = mcu_temp_(p, vdda);
    st_n = ntc_(p);
    (void)gl_hal_adc_power(false);
    if (vdda == 0u) {
        return GL_ERR_IO;
    }
    return (st_t != GL_OK) ? st_t : st_n;
}

gl_status_t gl_power_measure(gl_power_t *p)
{
    uint16_t counts = 0;
    gl_status_t st, st_t, st_n;

    p->mcu_temp_valid = false;
    p->cell_temp_valid = false;
    p->ntc_fault = (uint8_t)GL_NTC_ADC;
    st = gl_hal_adc_power(true);
    if (st != GL_OK) {
        return st;
    }
    const uint16_t vdda = gl_hal_adc_vdda_mv();
    st = gl_hal_adc_read(GL_ADC_CH_VBAT_DIV, BATT_ADC_AVG, BATT_ADC_SAMPLE_US, &counts);
    st_t = mcu_temp_(p, vdda);
    st_n = ntc_(p);
    (void)gl_hal_adc_power(false);
    if (vdda == 0u) {
        return GL_ERR_IO;
    }
    if (st != GL_OK) {
        return st;
    }
    p->batt_mv = gl_power_counts_to_mv(counts, vdda);
    p->percent = gl_power_percent(p->batt_mv);
    p->low = p->batt_mv < GL_PROV_BATT_LOW_MV;
    p->critical = p->batt_mv < GL_PROV_BATT_CRITICAL_MV;
    p->storage = p->batt_mv < GL_PROV_BATT_STORAGE_MV;
    return (st_t != GL_OK) ? st_t : st_n;
}

void gl_power_poll_pins(gl_power_t *p)
{
    p->vbus = gl_hal_gpio_read(GL_PIN_VBUS_SENSE);
    p->charging = !gl_hal_gpio_read(GL_PIN_CHG_STAT);
    p->charge_enabled = p->vbus && !p->inhibit;
}

bool gl_power_charge_gate(gl_power_t *p, bool cell_fresh, float imu_temp_c, bool imu_temp_valid,
                          bool mcu_temp_fresh)
{
    const float lo = GL_PROV_CHARGE_TEMP_MIN_C + GL_PROV_CHARGE_TEMP_GUARD_C;
    const float hi = GL_PROV_CHARGE_TEMP_MAX_C - GL_PROV_CHARGE_TEMP_GUARD_C;
    const float t = p->cell_temp_c;
    uint8_t reason;

    if (!p->vbus) {
        /* nothing to gate; never leave the pin low without VBUS */
        gl_power_charge_release(p);
        p->chg_reason = (uint8_t)GL_CHG_NO_VBUS;
        return false;
    }
    if (!cell_fresh) {
        reason = (uint8_t)GL_CHG_TEMP_UNKNOWN;
    } else if (p->ntc_fault != (uint8_t)GL_NTC_OK) {
        reason = (p->ntc_fault == (uint8_t)GL_NTC_ADC) ? (uint8_t)GL_CHG_TEMP_UNKNOWN
                                                       : (uint8_t)GL_CHG_NTC_FAULT;
    } else if (!p->cell_temp_valid || !isfinite(t)) {
        reason = (uint8_t)GL_CHG_TEMP_UNKNOWN;
    } else {
        const bool have_imu = imu_temp_valid && isfinite(imu_temp_c);
        const bool have_mcu = mcu_temp_fresh && p->mcu_temp_valid && isfinite(p->mcu_temp_c);
        const bool near_imu =
            have_imu && fabsf(t - imu_temp_c) <= GL_PROV_CHARGE_TEMP_MAX_DISAGREE_C;
        const bool near_mcu =
            have_mcu && fabsf(t - p->mcu_temp_c) <= GL_PROV_CHARGE_TEMP_MAX_DISAGREE_C;
        if (!have_imu && !have_mcu) {
            reason = (uint8_t)GL_CHG_TEMP_UNKNOWN; /* nothing to check the NTC against */
        } else if (!near_imu && !near_mcu) {
            reason = (uint8_t)GL_CHG_IMPLAUSIBLE;
        } else {
            bool ok;
            if (p->temp_ok) {
                ok = (t >= lo) && (t <= hi); /* stay enabled until a limit is crossed */
            } else {
                /* (re-)enable only well inside the window */
                ok = (t >= lo + GL_PROV_CHARGE_TEMP_HYST_C) && (t <= hi - GL_PROV_CHARGE_TEMP_HYST_C);
            }
            if (ok) {
                reason = (uint8_t)GL_CHG_ALLOWED;
            } else {
                reason = (t < 0.5f * (lo + hi)) ? (uint8_t)GL_CHG_TOO_COLD : (uint8_t)GL_CHG_TOO_HOT;
            }
        }
    }
    p->temp_ok = (reason == (uint8_t)GL_CHG_ALLOWED);
    p->chg_reason = reason;
    inhibit_(p, !p->temp_ok);
    return p->charge_enabled;
}

void gl_power_charge_release(gl_power_t *p)
{
    p->temp_ok = false;
    inhibit_(p, false);
}
