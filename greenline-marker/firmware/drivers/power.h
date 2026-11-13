/*
 * power.h - battery measurement, cell temperature, charger status and the
 * charge-temperature gate.
 *
 * Hardware (DESIGN_SPEC section 4, rev C2):
 *   VBAT_SENSE  ADC input behind a 2 x 1 Mohm divider with 100 nF: the
 *               capacitor is the charge reservoir for the ADC's sampling
 *               capacitor, so a short sampling time is enough, but the
 *               node recovers with a 50 ms time constant: readings are
 *               taken at most a few times per second.
 *   NTC_BIAS    GPIO at the top of the cell-temperature divider: 10.0 kohm
 *   NTC_SENSE   to the ADC pin, the 10 kohm NTC (B 3380) from there to
 *               ground; the NTC sits within 1 mm of the cell edge.  The bias
 *               pin is driven (push-pull high) ONLY while a conversion runs
 *               and is ANALOG otherwise.  This is the charge-temperature
 *               input; the IMU and MCU die temperatures are plausibility
 *               checks only.
 *   CHG_STAT    MCP73831 STAT with a pull-up: low = charging.
 *   CHG_INHIBIT open-drain MCU pin on the gate of the N-MOSFET in the PROG
 *               path.  The gate is fed from a divider on the charger supply,
 *               so the charger is ON BY DEFAULT whenever VBUS is present,
 *               also with the MCU unpowered, in reset or in the ROM
 *               bootloader.  LOW = charging stopped.  The MCU can only stop
 *               the charge, never start it.
 *   VBUS_SENSE  digital input, high = 5 V present (in the cradle).
 *
 * CHARGE GATE.  The MCP73831 has no temperature input, so this gate is the
 * only cell-temperature protection while the firmware runs.  Two rules, and
 * they pull in opposite directions:
 *
 *   (A) charging must never continue outside 0..45 C while the MCU is alive;
 *   (B) charging must never be left inhibited by an MCU that has crashed or
 *       gone to sleep - a cell at its protection cut-off must come back.
 *
 * What the driver does about them:
 *
 *   - CHG_INHIBIT is pulled low ONLY by gl_power_charge_gate(), i.e. only as
 *     the outcome of an evaluation made with VBUS present.  gl_power_init()
 *     does not touch the pin (reset state: analog, charger on).
 *   - With VBUS present the gate inhibits unless ALL of these hold: the NTC
 *     reading is fresh and passed its open / short / idle checks; at least
 *     one die sensor is alive and within GL_PROV_CHARGE_TEMP_MAX_DISAGREE_C
 *     of it; the NTC temperature is inside the window narrowed by
 *     GL_PROV_CHARGE_TEMP_GUARD_C, with hysteresis.  "Unknown" is "stop",
 *     and that is INTENTIONAL: a unit whose NTC is broken does not charge
 *     above what the MCU needs to run, and says why (chg_reason).
 *   - With VBUS absent the pin is RELEASED (gl_power_charge_release, also
 *     called by the gate itself): nothing can charge, and the next time the
 *     marker meets a cradle the charger starts by itself even if the MCU
 *     never wakes.  The application releases the pin before every Stop-mode
 *     sleep without VBUS; the host simulator counts Stop mode with the pin
 *     low and no VBUS as a violation.
 *
 * The full state table (unpowered, reset, watchdog reset, ROM bootloader,
 * Stop mode, hung firmware) is in the README, "Charger and cell temperature".
 *
 * RAM: gl_power_t 28 bytes.  Stack: under 64 bytes.
 */
#ifndef GL_POWER_H
#define GL_POWER_H

#include "gl_types.h"

/** The circuit this driver is written for: rev C2 of the phase-2 brief.
 *  CHG_INHIBIT is an OPEN-DRAIN pin and LOW stops the charger (0 here); the
 *  charger has no temperature input of its own (0).  DESIGN_SPEC has since
 *  been amended (rev D, E1: BQ25101 with its own NTC input, CHG_INHIBIT
 *  push-pull, HIGH = stop).  hal/stm32u5/gl_pins.h carries what the
 *  specification's text says (GL_PINS_SPEC_CHG_INHIBIT_ACTIVE_HIGH); the two
 *  are compared by tests/test_pins.c.  On an E1 board THIS DRIVER'S STOP
 *  STOPS NOTHING (the pin is never driven high). */
#define GL_POWER_CHG_INHIBIT_ACTIVE_HIGH 0
#define GL_POWER_CHARGER_HAS_NTC_INPUT 0

/** Why a cell-temperature reading is not valid. */
typedef enum {
    GL_NTC_OK = 0,
    GL_NTC_OPEN,      /**< reads above GL_PROV_NTC_OPEN_FRACTION: NTC missing or broken off */
    GL_NTC_SHORT,     /**< reads below GL_PROV_NTC_SHORT_FRACTION: shorted, or no bias */
    GL_NTC_STUCK,     /**< the sense pin is not near ground with the bias released */
    GL_NTC_ADC        /**< the conversion itself failed */
} gl_ntc_fault_t;

/** Outcome of the charge gate. */
typedef enum {
    GL_CHG_ALLOWED = 0,      /**< VBUS present, CHG_INHIBIT released */
    GL_CHG_NO_VBUS,          /**< nothing to gate: CHG_INHIBIT released */
    GL_CHG_TEMP_UNKNOWN,     /**< no fresh NTC reading, or no die sensor to check it against */
    GL_CHG_NTC_FAULT,        /**< NTC open / short / stuck (ntc_fault says which) */
    GL_CHG_IMPLAUSIBLE,      /**< the NTC disagrees with every die sensor that is alive */
    GL_CHG_TOO_COLD,
    GL_CHG_TOO_HOT
} gl_chg_reason_t;

typedef struct {
    uint16_t batt_mv;     /**< last battery reading, 0 = none yet */
    uint8_t percent;      /**< 0..100 from the provisional voltage thresholds */
    bool vbus;            /**< in the cradle */
    bool charging;        /**< charger STAT says charging */
    bool charge_enabled;  /**< VBUS present and CHG_INHIBIT released by the gate */
    bool inhibit;         /**< CHG_INHIBIT is being pulled low */
    bool temp_ok;         /**< inside the charging window (with guard and hysteresis) */
    uint8_t chg_reason;   /**< gl_chg_reason_t of the last gate evaluation */
    bool low;             /**< below GL_PROV_BATT_LOW_MV */
    bool critical;        /**< below GL_PROV_BATT_CRITICAL_MV: no camera reads */
    bool storage;         /**< below GL_PROV_BATT_STORAGE_MV: stop everything */
    bool mcu_temp_valid;  /**< mcu_temp_c is from the last measurement */
    float mcu_temp_c;     /**< MCU die temperature, degrees C */
    bool cell_temp_valid; /**< cell_temp_c is from the last measurement and passed its checks */
    uint8_t ntc_fault;    /**< gl_ntc_fault_t of the last measurement */
    float cell_temp_c;    /**< cell temperature from the NTC, degrees C */
} gl_power_t;

/** Configure the pins.  CHG_INHIBIT and NTC_BIAS are left as they are
 *  (analog after reset): the charger stays in its hardware default until
 *  gl_power_charge_gate() has been given a measurement. */
void gl_power_init(gl_power_t *p);

/** Measure the battery, the MCU die temperature and the cell temperature
 *  (one ADC session), update batt_mv, percent, low, critical, storage,
 *  mcu_temp_*, cell_temp_* / ntc_fault.  On an error the temperatures it
 *  could not read are marked not valid. */
gl_status_t gl_power_measure(gl_power_t *p);

/** The two temperatures only (what the charge supervision repeats every few
 *  seconds in the cradle): 1.1 ms of bus and conversion time on the
 *  simulator, NTC_BIAS high for 0.68 ms of it. */
gl_status_t gl_power_measure_temps(gl_power_t *p);

/** Battery voltage for a raw ADC reading (pure; used by the tests):
 *  counts / full scale * VDDA * divider ratio. */
uint16_t gl_power_counts_to_mv(uint16_t counts, uint16_t vdda_mv);

/** State of charge estimate, 0..100, linear between the provisional empty
 *  and full voltages. */
uint8_t gl_power_percent(uint16_t batt_mv);

/**
 * Cell temperature for a raw GL_ADC_CH_CELL_NTC reading (pure): the divider
 * is ratiometric, R = R_series * x / (1 - x) with x = counts / full scale,
 * then the B-parameter equation.  `fault` (may be NULL) receives GL_NTC_OPEN
 * / GL_NTC_SHORT when the reading is outside the detection thresholds; the
 * returned temperature is then not-a-number.
 */
float gl_power_ntc_counts_to_c(uint16_t counts, uint8_t *fault);

/** Read VBUS and STAT into `p`. */
void gl_power_poll_pins(gl_power_t *p);

/**
 * Apply the charge gate (see the file comment).  `cell_fresh`: the caller
 * vouches that p->cell_temp_c was measured recently enough; the IMU's die
 * temperature and whether it is alive and fresh; whether p->mcu_temp_c is
 * fresh.  Call after gl_power_poll_pins() whenever the temperature has been
 * measured and on every VBUS change.  Returns true if charging is allowed
 * afterwards (VBUS present and CHG_INHIBIT released).
 */
bool gl_power_charge_gate(gl_power_t *p, bool cell_fresh, float imu_temp_c, bool imu_temp_valid,
                          bool mcu_temp_fresh);

/** Release CHG_INHIBIT (the hardware default: the charger runs whenever
 *  VBUS is present).  For every moment at which the firmware stops
 *  supervising: VBUS gone, going to sleep.  The hysteresis state is reset,
 *  so the next gate evaluation starts from "well inside the window". */
void gl_power_charge_release(gl_power_t *p);

#endif /* GL_POWER_H */
