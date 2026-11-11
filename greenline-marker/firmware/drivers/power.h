/*
 * power.h - battery measurement, charger status and charge gating.
 *
 * Hardware (DESIGN_SPEC section 4):
 *   VBAT_SENSE  ADC input behind a 2 x 1 Mohm divider with 100 nF: the
 *               capacitor is the charge reservoir for the ADC's sampling
 *               capacitor, so a short sampling time is enough, but the
 *               node recovers with a 50 ms time constant: readings are
 *               taken at most a few times per second.
 *   CHG_STAT    MCP73831 STAT, open drain with a pull-up: low = charging.
 *   CHG_PROG_EN open-drain MCU pin in series with the PROG resistor:
 *               LOW = charging allowed, released = charger off (rev C
 *               circuit; the polarity is GL_PROV_CHG_PROG_LOW_ALLOWS_CHARGE,
 *               see core/gl_provisional.h for why it may have to change).
 *   VBUS_SENSE  digital input, high = 5 V present (in the cradle).
 *
 * CHARGE GATE.  Charging is allowed only while VBUS is present and the
 * temperature is KNOWN to be inside 0..45 C, with hysteresis.  The gate
 * takes the coldest and the hottest of the available readings (the
 * application gives it the IMU's die temperature and the MCU's own, which
 * must both be valid and agree): both ends must be inside the window.  An
 * unknown temperature stops charging.  The MCP73831 has no NTC input: this
 * gate is the only cell-temperature protection of the product, so every
 * doubt resolves to "stop".
 *
 * RAM: gl_power_t 24 bytes.  Stack: under 48 bytes.
 */
#ifndef GL_POWER_H
#define GL_POWER_H

#include "gl_types.h"

typedef struct {
    uint16_t batt_mv;     /**< last battery reading, 0 = none yet */
    uint8_t percent;      /**< 0..100 from the provisional voltage thresholds */
    bool vbus;            /**< in the cradle */
    bool charging;        /**< charger STAT says charging */
    bool charge_enabled;  /**< PROG enable driven low */
    bool temp_ok;         /**< inside the charging window (with hysteresis) */
    bool low;             /**< below GL_PROV_BATT_LOW_MV */
    bool critical;        /**< below GL_PROV_BATT_CRITICAL_MV: no camera reads */
    bool storage;         /**< below GL_PROV_BATT_STORAGE_MV: stop everything */
    bool mcu_temp_valid;  /**< mcu_temp_c is from the last gl_power_measure() */
    float mcu_temp_c;     /**< MCU die temperature, degrees C */
} gl_power_t;

/** Configure the pins; charging disabled until gl_power_charge_gate(). */
void gl_power_init(gl_power_t *p);

/** Measure the battery and the MCU die temperature (powers the ADC for the
 *  two conversions), update batt_mv, percent, low, critical, storage,
 *  mcu_temp_c / mcu_temp_valid.  On an error mcu_temp_valid is false. */
gl_status_t gl_power_measure(gl_power_t *p);

/** Battery voltage for a raw ADC reading (pure; used by the tests):
 *  counts / full scale * VDDA * divider ratio. */
uint16_t gl_power_counts_to_mv(uint16_t counts, uint16_t vdda_mv);

/** State of charge estimate, 0..100, linear between the provisional empty
 *  and full voltages. */
uint8_t gl_power_percent(uint16_t batt_mv);

/** Read VBUS and STAT into `p`. */
void gl_power_poll_pins(gl_power_t *p);

/**
 * Apply the charge gate.  `temp_cold_c` / `temp_hot_c` are the lowest and
 * the highest of the temperature readings the caller trusts (the same
 * value twice for a single sensor); `temp_valid` false - any doubt about
 * the temperature - stops charging, as does a non-finite value.  Call after
 * gl_power_poll_pins() whenever the temperature has been read, and on every
 * VBUS change.  Returns true if charging is enabled afterwards.
 */
bool gl_power_charge_gate(gl_power_t *p, float temp_cold_c, float temp_hot_c, bool temp_valid);

/** Stop charging now, whatever the temperature (going to sleep: nothing
 *  supervises the gate then).  The hysteresis state is reset, so charging
 *  resumes only well inside the window. */
void gl_power_charge_stop(gl_power_t *p);

#endif /* GL_POWER_H */
