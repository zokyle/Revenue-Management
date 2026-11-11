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
 *               LOW = charging allowed, released = charger off.
 *   VBUS_SENSE  digital input, high = 5 V present (in the cradle).
 *
 * Charging is allowed only while VBUS is present and the temperature (from
 * the IMU) is inside 0..45 C, with hysteresis; an unknown temperature
 * stops charging.
 *
 * RAM: gl_power_t 16 bytes.  Stack: under 48 bytes.
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
} gl_power_t;

/** Configure the pins; charging disabled until gl_power_charge_gate(). */
void gl_power_init(gl_power_t *p);

/** Measure the battery (powers the ADC for the measurement), update
 *  batt_mv, percent, low, critical. */
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
 * Apply the charge gate.  `temp_valid` false (IMU not readable) stops
 * charging.  Call after gl_power_poll_pins() whenever the temperature has
 * been read, and on every VBUS change.  Returns true if charging is
 * enabled afterwards.
 */
bool gl_power_charge_gate(gl_power_t *p, float temp_c, bool temp_valid);

#endif /* GL_POWER_H */
