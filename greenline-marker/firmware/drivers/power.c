/* power.c - battery, the MCU's cell thermistor, the BQ25101's status, the
 * firmware's charge gate and the temperature gate of a read.  See power.h. */
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

/* CHG_INHIBIT (E1): a push-pull output on the gate of the MOSFET that pulls
 * the charger's TS pin to ground.  Stop: latch HIGH first, then push-pull.
 * Release: latch low (the gate is discharged actively if the pin is still an
 * output), then back to ANALOG, the state the pin has after reset; the
 * 100 kohm on the gate holds the MOSFET off from there.  Both are written
 * every time, whatever this module believes the pin to be. */
static void inhibit_(gl_power_t *p, bool stop)
{
    if (stop) {
        gl_hal_gpio_write(GL_PIN_CHG_INHIBIT, true);
        gl_hal_gpio_mode(GL_PIN_CHG_INHIBIT, GL_PIN_MODE_OUTPUT_PP);
    } else {
        gl_hal_gpio_write(GL_PIN_CHG_INHIBIT, false);
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
    /* CHG_INHIBIT and NTC_BIAS: not touched (see power.h).  CHG_STAT has the
     * board's pull-up and VBUS_SENSE its divider: no internal pull on either */
    gl_hal_gpio_mode(GL_PIN_CHG_STAT, GL_PIN_MODE_INPUT);
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

gl_chg_status_t gl_power_charger_status(const gl_power_t *p)
{
    if (!p->vbus) {
        return GL_CHGST_NO_INPUT;
    }
    if (p->charging) {
        /* CHG low: a charge runs.  With CHG_INHIBIT high that cannot be */
        return p->inhibit ? GL_CHGST_STOP_FAILED : GL_CHGST_CHARGING;
    }
    if (p->inhibit) {
        return GL_CHGST_INHIBITED;
    }
    if (p->cell_temp_valid && isfinite(p->cell_temp_c) &&
        (p->cell_temp_c < GL_PROV_BQ25101_T_COLD_C || p->cell_temp_c > GL_PROV_BQ25101_T_HOT_C)) {
        return GL_CHGST_TEMP_HOLD; /* the charger's own thermistor, as far as NTC2 can tell */
    }
    if (p->batt_mv >= GL_PROV_CHARGE_DONE_MIN_MV) {
        return GL_CHGST_DONE;
    }
    /* (a cell voltage that has not been measured yet, 0, also ends here:
     * the application measures before it believes this answer) */
    return GL_CHGST_NOT_CHARGING;
}

void gl_power_poll_pins(gl_power_t *p)
{
    p->vbus = gl_hal_gpio_read(GL_PIN_VBUS_SENSE);
    /* the charger's CHG output pulls the line low while a charge runs; with
     * no VBUS the board's pull-up holds it high */
    p->charging = !gl_hal_gpio_read(GL_PIN_CHG_STAT);
    p->charge_enabled = p->vbus && !p->inhibit;
    p->chg_status = (uint8_t)gl_power_charger_status(p);
}

void gl_power_charge_force(gl_power_t *p, bool stop)
{
    p->forced = stop;
}

/* E32: account the time since the last gate call as charging if the charger
 * said "charging" then and says so now; anything else starts the count
 * again.  Returns true while the limit holds. */
static bool time_limit_(gl_power_t *p, uint32_t now_ms)
{
    if (p->gate_timed && p->charging && !p->inhibit) {
        const uint32_t dt = (uint32_t)(now_ms - p->chg_last_ms);
        p->chg_run_ms = (dt > UINT32_MAX - p->chg_run_ms) ? UINT32_MAX : (p->chg_run_ms + dt);
    } else if (!p->charging) {
        p->chg_run_ms = 0;
    }
    p->gate_timed = true;
    p->chg_last_ms = now_ms;
    if (p->chg_run_ms >= GL_PROV_CHARGE_MAX_MS) {
        p->time_limit = true;
    } else if (p->time_limit && p->batt_mv != 0u && p->batt_mv < GL_PROV_CHARGE_RESTART_MV) {
        /* the cell has run down behind the stopped charger: let it charge
         * again, with a fresh limit */
        p->time_limit = false;
    }
    return p->time_limit;
}

bool gl_power_charge_gate(gl_power_t *p, uint32_t now_ms, bool cell_fresh, float imu_temp_c,
                          bool imu_temp_valid, bool mcu_temp_fresh)
{
    const float lo = GL_PROV_CHARGE_TEMP_MIN_C + GL_PROV_CHARGE_TEMP_GUARD_C;
    const float hi = GL_PROV_CHARGE_TEMP_MAX_C - GL_PROV_CHARGE_TEMP_GUARD_C;
    const float t = p->cell_temp_c;
    uint8_t reason;
    bool limit;

    if (!p->vbus) {
        /* nothing to gate; never leave the charger stopped without VBUS */
        gl_power_charge_release(p);
        p->chg_reason = (uint8_t)GL_CHG_NO_VBUS;
        p->chg_status = (uint8_t)gl_power_charger_status(p);
        return false;
    }
    limit = time_limit_(p, now_ms);
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
            /* The charger's own thermistor should have stopped this charge:
             * NTC2, believed by a die sensor, is outside the charger's window
             * by more than the two readings can differ, and CHG still says
             * "charging".  The gate stops it (the reason above); the flag
             * says that the hardware window is not there. */
            if (p->charging && !p->inhibit &&
                (t < GL_PROV_BQ25101_T_COLD_C - 2.0f * GL_PROV_CHARGE_TEMP_GUARD_C ||
                 t > GL_PROV_BQ25101_T_HOT_C + 2.0f * GL_PROV_CHARGE_TEMP_GUARD_C)) {
                p->ntc1_suspect = true;
            }
        }
    }
    p->temp_ok = (reason == (uint8_t)GL_CHG_ALLOWED);
    /* a temperature reason comes first (it is the one that says something
     * about the cell); then the command, then the time limit */
    if (p->temp_ok && p->forced) {
        reason = (uint8_t)GL_CHG_FORCED;
    } else if (p->temp_ok && limit) {
        reason = (uint8_t)GL_CHG_TIME_LIMIT;
    }
    p->chg_reason = reason;
    inhibit_(p, reason != (uint8_t)GL_CHG_ALLOWED);
    p->chg_status = (uint8_t)gl_power_charger_status(p);
    return p->charge_enabled;
}

void gl_power_charge_release(gl_power_t *p)
{
    p->temp_ok = false;
    p->time_limit = false;
    p->forced = false;
    p->chg_run_ms = 0;
    p->gate_timed = false;
    inhibit_(p, false);
    p->chg_status = (uint8_t)gl_power_charger_status(p);
}

bool gl_power_read_allowed(gl_power_t *p, bool cell_fresh, float imu_temp_c, bool imu_temp_valid,
                           bool mcu_temp_fresh)
{
    const bool have_cell = cell_fresh && p->cell_temp_valid &&
                           p->ntc_fault == (uint8_t)GL_NTC_OK && isfinite(p->cell_temp_c);
    const bool have_imu = imu_temp_valid && isfinite(imu_temp_c);
    const bool have_mcu = mcu_temp_fresh && p->mcu_temp_valid && isfinite(p->mcu_temp_c);
    float t;

    if (have_cell) {
        t = p->cell_temp_c;
    } else if (have_imu || have_mcu) {
        /* NTC2 has nothing to say: the hotter die sensor stands in */
        t = have_imu ? imu_temp_c : p->mcu_temp_c;
        if (have_imu && have_mcu && p->mcu_temp_c > t) {
            t = p->mcu_temp_c;
        }
    } else {
        p->read_hot = false; /* no temperature at all: see power.h */
        return true;
    }
    if (p->read_hot) {
        p->read_hot = !(t < GL_PROV_READ_TEMP_MAX_C - GL_PROV_READ_TEMP_HYST_C);
    } else {
        p->read_hot = (t > GL_PROV_READ_TEMP_MAX_C);
    }
    return !p->read_hot;
}
