/*
 * power.h - battery measurement, the MCU's cell thermistor, the charger
 * (TI BQ25101, DESIGN_SPEC amendment E1) and the firmware's supervision of
 * it, and the temperature gate of a camera read (E13).
 *
 * Hardware (rev E board; DESIGN_SPEC section 4, electrical/gl1_main):
 *   VBAT_SENSE  ADC input behind a 2 x 1 Mohm divider with 100 nF: the
 *               capacitor is the charge reservoir for the ADC's sampling
 *               capacitor, so a short sampling time is enough, but the
 *               node recovers with a 50 ms time constant: readings are
 *               taken at most a few times per second.
 *   NTC1        the CHARGER's thermistor, from its TS pin to ground.  The
 *               MCU cannot read it.
 *   NTC2        the MCU's thermistor (Murata NCU15XH103F60RC, 10 kohm, B
 *               3380 K nominal), within 1 mm of the cell edge:
 *   NTC_BIAS    GPIO at the top of its divider: 10.0 kohm to
 *   NTC_SENSE   the ADC pin, the NTC from there to ground.  The bias pin is
 *               driven (push-pull high) ONLY while a conversion runs and is
 *               ANALOG otherwise.  The IMU and MCU die temperatures are
 *               plausibility checks only.
 *   CHG_STAT    the charger's open-drain CHG output with 100 kohm to V2V8:
 *               low = a charge is running.  An input without an internal
 *               pull; never driven (the pad is a USB Type-C CC pad).
 *   CHG_INHIBIT PUSH-PULL output on the gate of an N-MOSFET (gate pulled
 *               down with 100 kohm) that pulls the charger's TS pin to
 *               ground, which disables the charger.  HIGH = STOP.  Analog
 *               (the reset state), low or unpowered: the MOSFET is off and
 *               cannot disturb the charger.
 *   VBUS_SENSE  digital input from a 100 k : 100 k divider on the VBUS pad,
 *               high = 5 V present (in the cradle).
 *
 * WHO PROTECTS THE CELL.  The BQ25101 charges on its own whenever VBUS is
 * present - with the MCU unpowered, in reset, hung, in the ROM loader or in
 * ship mode - and enforces its own temperature window with NTC1 (JEITA
 * profile: off below 0 C and above 60 C, half current below 10 C, 4.06 V
 * above 45 C; thresholds PROVISIONAL), terminates at 10 % of 19.8 mA and
 * (from memory of the family) has a safety timer.  THE FIRMWARE CAN ONLY
 * STOP IT, and does so for four reasons:
 *
 *   temperature  its own, NARROWER window on NTC2: 0..45 C less a guard band,
 *                with hysteresis.  "Unknown" is "stop": an NTC2 that is
 *                open, shorted, stuck, stale or contradicted by every die
 *                sensor stops the charge and says why (chg_reason).  This
 *                is also what is left of the temperature protection when
 *                NTC1 is OPEN, which the charger reads as "no thermistor,
 *                no limits" (GL_PROV_BQ25101_TS_OPEN_IS_TTDM).
 *   time         E32: after GL_PROV_CHARGE_MAX_MS (6 h) in which the firmware
 *                has not held the charger stopped (VBUS present,
 *                CHG_INHIBIT released), WHATEVER the charger's status
 *                output said in them: the backstop does not depend on the
 *                line it backs up.  An awake marker draws more than the charger's
 *                2 mA termination current from the node the charger feeds,
 *                so the charger may never see the end of a charge; the
 *                application therefore sleeps in the cradle, and this is
 *                the backstop for when it cannot (a host that keeps
 *                talking).  Released when VBUS goes, or when the cell,
 *                having been at or above GL_PROV_CHARGE_RESTART_MV with the
 *                limit in force, has fallen below it (a cell that is still
 *                under that voltage after 6 h of charging gets no second
 *                6 h: stopped until the marker is lifted out).
 *   a command    the factory's "stop the charge" (gl_power_charge_force):
 *                assembly step 13 proves NTC1 and the MOSFET with it.
 *
 * Two rules that pull in opposite directions, as before:
 *   (A) the firmware does not let a charge continue that it has a reason to
 *       stop, for as long as it runs;
 *   (B) the firmware never leaves the charger stopped when it stops
 *       supervising: without VBUS, and before every sleep without VBUS,
 *       CHG_INHIBIT is released (ANALOG), so that the next cradle charges
 *       the cell even if this firmware never wakes again.  The host
 *       simulator counts Stop mode with the pin high and no VBUS as a
 *       violation.  A reset (watchdog included) releases the pin by itself.
 *
 * The full state table (unpowered, reset, ROM loader, hung, Stop mode, ship
 * mode) is in the README, "Charger and cell temperature".
 *
 * RAM: gl_power_t 44 bytes.  Stack: under 64 bytes.
 */
#ifndef GL_POWER_H
#define GL_POWER_H

#include "gl_types.h"

/** The circuit this driver is written for: amendment E1.  CHG_INHIBIT is a
 *  PUSH-PULL pin and HIGH stops the charger (1); the charger has a
 *  temperature input of its own (1).  hal/stm32u5/gl_pins.h carries what
 *  the netlist's pin map says (GL_PINS_CHG_INHIBIT_ACTIVE_HIGH); the two
 *  are compared by tests/test_pins.c. */
#define GL_POWER_CHG_INHIBIT_ACTIVE_HIGH 1
#define GL_POWER_CHARGER_HAS_NTC_INPUT 1

/** Why a cell-temperature reading (NTC2) is not valid. */
typedef enum {
    GL_NTC_OK = 0,
    GL_NTC_OPEN,      /**< reads above GL_PROV_NTC_OPEN_FRACTION: NTC missing or broken off */
    GL_NTC_SHORT,     /**< reads below GL_PROV_NTC_SHORT_FRACTION: shorted, or no bias */
    GL_NTC_STUCK,     /**< the sense pin is not near ground with the bias released */
    GL_NTC_ADC        /**< the conversion itself failed, or nothing measured yet */
} gl_ntc_fault_t;

/** Outcome of the firmware's charge gate: why it stops the charge, or that
 *  it does not.  (Values are logged: append only.) */
typedef enum {
    GL_CHG_ALLOWED = 0,      /**< VBUS present, CHG_INHIBIT released: the charger decides */
    GL_CHG_NO_VBUS,          /**< nothing to gate: CHG_INHIBIT released */
    GL_CHG_TEMP_UNKNOWN,     /**< no fresh NTC2 reading, or no die sensor to check it against */
    GL_CHG_NTC_FAULT,        /**< NTC2 open / short / stuck (ntc_fault says which) */
    GL_CHG_IMPLAUSIBLE,      /**< NTC2 disagrees with every die sensor that is alive */
    GL_CHG_TOO_COLD,
    GL_CHG_TOO_HOT,
    GL_CHG_TIME_LIMIT,       /**< E32: GL_PROV_CHARGE_MAX_MS of continuous charging */
    GL_CHG_FORCED            /**< stopped by a command (gl_power_charge_force) */
} gl_chg_reason_t;

/**
 * What the charger is doing, AS FAR AS THE FIRMWARE CAN TELL from CHG_STAT,
 * VBUS, its own CHG_INHIBIT, the cell voltage and NTC2.  The charger has one
 * status output; everything beyond "a charge is running" is an inference,
 * and the last two are what does not add up.  (Values are sent to the host:
 * append only.)
 */
typedef enum {
    GL_CHGST_NO_INPUT = 0,   /**< no VBUS */
    GL_CHGST_CHARGING,       /**< CHG low: pre-charge, fast charge or taper */
    GL_CHGST_DONE,           /**< CHG released, nothing holding the charger, the cell at its
                                  end voltage: the charge has terminated */
    GL_CHGST_INHIBITED,      /**< the firmware holds CHG_INHIBIT high (chg_reason says why)
                                  and CHG is released */
    GL_CHGST_TEMP_HOLD,      /**< CHG released, not inhibited, NTC2 outside the charger's own
                                  window: the charger's thermistor holds it */
    GL_CHGST_NOT_CHARGING,   /**< CHG released although nothing the firmware knows of holds
                                  the charger and the cell is not full: the input is too
                                  low for the charger, its safety timer has expired, NTC1
                                  is shorted, or the part is dead.  Also seen for a moment
                                  after docking, before the charger has detected its input:
                                  the application calls it a fault only when it persists */
    GL_CHGST_STOP_FAILED     /**< CHG LOW although the firmware holds CHG_INHIBIT high: its
                                  stop does not stop (the MOSFET or its gate) */
} gl_chg_status_t;

typedef struct {
    uint16_t batt_mv;     /**< last battery reading, 0 = none yet */
    uint8_t percent;      /**< 0..100 from the provisional voltage thresholds */
    bool vbus;            /**< in the cradle */
    bool charging;        /**< the charger's CHG output is low: a charge is running */
    bool charge_enabled;  /**< VBUS present and CHG_INHIBIT not asserted: the charger is free
                               to charge (whether it does is `charging`) */
    bool inhibit;         /**< CHG_INHIBIT is being driven high */
    bool temp_ok;         /**< NTC2 inside the firmware's window (with guard and hysteresis) */
    uint8_t chg_reason;   /**< gl_chg_reason_t of the last gate evaluation */
    uint8_t chg_status;   /**< gl_chg_status_t, updated with every poll of the pins and gate */
    bool low;             /**< below GL_PROV_BATT_LOW_MV */
    bool critical;        /**< below GL_PROV_BATT_CRITICAL_MV: no camera reads */
    bool storage;         /**< below GL_PROV_BATT_STORAGE_MV: stop everything */
    bool mcu_temp_valid;  /**< mcu_temp_c is from the last measurement */
    float mcu_temp_c;     /**< MCU die temperature, degrees C */
    bool cell_temp_valid; /**< cell_temp_c is from the last measurement and passed its checks */
    uint8_t ntc_fault;    /**< gl_ntc_fault_t of the last measurement */
    float cell_temp_c;    /**< cell temperature from NTC2, degrees C */
    uint16_t ntc_counts;  /**< raw NTC2 conversion of the last measurement (bias on), counts
                               of GL_HAL_ADC_FULL_SCALE; for the factory (GL_CMD_GET_SENSORS) */
    uint16_t vdda_mv;     /**< VDDA (the 2.8 V rail) at the last gl_power_measure(), 0 = none */
    /* the firmware's own limits on a charge */
    bool time_limit;      /**< the E32 backstop has fired and still holds */
    bool limit_cell_was_up; /**< ... and the cell has been seen at or above
                               GL_PROV_CHARGE_RESTART_MV since: only then does a fall
                               below it lift the limit */
    bool forced;          /**< a command holds the charge stopped */
    bool ntc1_suspect;    /**< a charge was running with NTC2 (valid, plausible) outside the
                               charger's OWN window: the charger's thermistor is not
                               doing its job (open: see GL_PROV_BQ25101_TS_OPEN_IS_TTDM).
                               Sticky until the next gl_power_init() */
    bool read_hot;        /**< E13: too hot for a camera read (with hysteresis) */
    bool gate_timed;      /**< chg_last_ms is valid */
    uint32_t chg_run_ms;  /**< E32: time docked with the charger free to charge (not held by
                           *   the firmware) since VBUS came or the limit was last lifted */
    uint32_t chg_last_ms; /**< time of the last gate call */
} gl_power_t;

/** Configure the pins.  CHG_INHIBIT and NTC_BIAS are left as they are
 *  (analog after reset): the charger stays in its hardware default.
 *  CHG_STAT and VBUS_SENSE become inputs WITHOUT an internal pull. */
void gl_power_init(gl_power_t *p);

/** Measure the battery, the MCU die temperature and the cell temperature
 *  (one ADC session), update batt_mv, percent, low, critical, storage,
 *  mcu_temp_*, cell_temp_* / ntc_fault.  On an error the temperatures it
 *  could not read are marked not valid. */
gl_status_t gl_power_measure(gl_power_t *p);

/** The two temperatures only: 1.1 ms of bus and conversion time on the
 *  simulator, NTC_BIAS high for 0.68 ms of it. */
gl_status_t gl_power_measure_temps(gl_power_t *p);

/** Battery voltage for a raw ADC reading (pure; used by the tests):
 *  counts / full scale * VDDA * divider ratio. */
uint16_t gl_power_counts_to_mv(uint16_t counts, uint16_t vdda_mv);

/** State of charge estimate, 0..100, linear between the provisional empty
 *  and full voltages. */
uint8_t gl_power_percent(uint16_t batt_mv);

/**
 * Cell temperature for a raw GL_ADC_CH_CELL_NTC reading (pure).  The divider
 * is ratiometric: with x = counts / full scale,
 *     R = R_series * x / (1 - x)
 *     T = 1 / (1 / 298.15 K + ln(R / R25) / B) - 273.15       (B equation)
 * with R_series = R25 = 10.0 kohm and B = 3380 K (gl_provisional.h; NOMINAL
 * figures, no R-T table of the part has been read).  `fault` (may be NULL)
 * receives GL_NTC_OPEN / GL_NTC_SHORT when the reading is outside the
 * detection thresholds; the returned temperature is then not-a-number.
 *
 * ERROR BUDGET of a reading (tests/test_drv_power.c computes and prints
 * it again; the figures below are its output):
 *   arithmetic, single precision          0.011 K at worst (-40..85 C)
 *   NTC 1 %, B 1 %, series resistor 1 %,  0.67 K at 0 C, 0.81 K at 45 C,
 *     worst of the eight corners          1.05 K at 60 C
 *   ... with an ADC error of 0.2 % of     0.90 K at 0 C, 1.09 K at 45 C,
 *     full scale                          1.43 K at 60 C
 *   bias pin's output resistance (50 ohm  0.11 K at 0 C, 0.16 K at 60 C
 *     at most, PROVISIONAL)               (NETLIST_NOTES 4.5; not in the test)
 * NOT in it: the part's R-T curve against the one-B equation, and the
 * temperature difference between the cell and the NTC beside it.
 */
float gl_power_ntc_counts_to_c(uint16_t counts, uint8_t *fault);

/** Read VBUS and CHG_STAT into `p` and update chg_status. */
void gl_power_poll_pins(gl_power_t *p);

/**
 * Apply the firmware's charge gate (see the file comment).  `now_ms`: the
 * tick, for the E32 time limit (the time between two calls counts as
 * charging if CHG was low at both).  `cell_fresh`: the caller vouches that
 * p->cell_temp_c was measured recently enough; the IMU's die temperature
 * and whether it is alive and fresh; whether p->mcu_temp_c is fresh.  Call
 * after gl_power_poll_pins() whenever the temperature has been measured and
 * on every VBUS change.  Returns true if the charger is free to charge
 * afterwards (VBUS present and CHG_INHIBIT released).
 */
bool gl_power_charge_gate(gl_power_t *p, uint32_t now_ms, bool cell_fresh, float imu_temp_c,
                          bool imu_temp_valid, bool mcu_temp_fresh);

/** Release CHG_INHIBIT (the hardware default: the charger decides by
 *  itself).  For every moment at which the firmware stops supervising: VBUS
 *  gone, going to sleep without VBUS.  The hysteresis, the time limit and a
 *  forced stop are reset. */
void gl_power_charge_release(gl_power_t *p);

/** Factory command: hold the charge stopped (true) until released (false),
 *  VBUS goes or the MCU resets.  Takes effect at the next gate call. */
void gl_power_charge_force(gl_power_t *p, bool stop);

/** The inference described at gl_chg_status_t, from the fields of `p`
 *  (pure). */
gl_chg_status_t gl_power_charger_status(const gl_power_t *p);

/**
 * E13: may a camera read start?  False while the cell is too hot: NTC2 reads
 * above GL_PROV_READ_TEMP_MAX_C, and until it has fallen
 * GL_PROV_READ_TEMP_HYST_C below it again.  If NTC2 has no valid reading
 * (`cell_fresh` false, or a fault) the hotter of the die sensors that are
 * alive stands in for it; with no temperature at all the read is allowed
 * (a marker whose three sensors are all dead has other problems, and the
 * tilt read that precedes every camera read needs the IMU alive).  NTC2 is
 * believed as the charge gate believes it: if every live die sensor is more
 * than GL_PROV_CHARGE_TEMP_MAX_DISAGREE_C away from it, the HOTTEST of the
 * readings decides (an NTC2 stuck at 25 C does not let a 75 C marker read).
 * Updates p->read_hot.
 */
bool gl_power_read_allowed(gl_power_t *p, bool cell_fresh, float imu_temp_c, bool imu_temp_valid,
                           bool mcu_temp_fresh);

#endif /* GL_POWER_H */
