/*
 * gl_sim.h - control and inspection interface of the HOST SIMULATOR backend
 * of hal/gl_hal.h.  Host tests only; nothing here exists on the target.
 *
 * The simulator is a model of the GL-1 board as seen from the MCU pins:
 *
 *   time        simulated microseconds.  Time passes in gl_hal_delay_*, in
 *               gl_hal_sleep, for the duration of bus transfers and ADC
 *               conversions, and FOR COMPUTATION at the trace points of
 *               gl_hal_trace(point, work): the stage that has just ended is
 *               charged its instruction count (gl_sim_cost.h, measured with
 *               callgrind) x a cycles-per-instruction factor / the core clock
 *               in effect.  The factor is an ESTIMATE with a low and a high
 *               case (GL_SIM_CPI_*, gl_sim_set_cpi); 0 switches the charge
 *               off (the phase-1 behaviour: computation for nothing).  A
 *               test can also fix the time of a trace point
 *               (gl_sim_set_compute_us).  Computation BETWEEN trace points
 *               (the main loop's bookkeeping, a few hundred instructions per
 *               IMU sample) is still free.
 *   supply      the charge drawn from the cell, from a current per state of
 *               the MCU, the camera rail, the IMU and the rest (GL_SIM_I_*:
 *               every one PROVISIONAL, from memory of the datasheets):
 *               gl_sim_stats_t.charge_*.  An ESTIMATE of what a read costs,
 *               not a measurement.
 *   GPIO        mode and output latch of every logical pin, external levels
 *               for inputs, every change recorded in the trace
 *   SPI1        LS013B7DH03 model (decodes frames into a panel memory) and
 *               MX25R6435F model (8 MB of RAM, NOR semantics, busy times)
 *   SPI2        LSM6DSV16X model (register map, sample generator, wake-up
 *               and data-ready interrupts)
 *   SCCB+DCMI   two OVM7692 models on the shared bus; frames come from a
 *               scene callback supplied by the test
 *   ADC/OPAMP   battery divider, the cell-temperature divider (NTC_BIAS,
 *               10.0 kohm, NTC_SENSE, the NTC to ground) and the grain
 *               photodiode stage, driven by the charlieplex pin states
 *   charger     the rev E circuit (DESIGN_SPEC E1): a model of the BQ25101
 *               with ITS OWN thermistor NTC1 on the cell.  It charges
 *               whenever VBUS is present, its own temperature window allows
 *               it and CHG_INHIBIT is not driven HIGH - with the MCU in
 *               reset, in the ROM loader, hung or in ship mode as much as
 *               with firmware running: the firmware's opinion is not asked.
 *               JEITA zones, termination at 10 % of the charge current,
 *               recharge, a safety timer, CHG as an open-drain status output,
 *               TS low = disabled, TS open = no limits.  EVERY THRESHOLD AND
 *               BEHAVIOUR OF IT IS PROVISIONAL (core/gl_provisional.h,
 *               GL_PROV_BQ25101_*): the model encodes this project's reading
 *               of the part, it proves nothing about the chip.  The TRUE
 *               cell temperature is a property of the model
 *   cell        optional (gl_sim_cell_enable): a 43 mAh cell with an
 *               open-circuit voltage curve and an internal resistance, so
 *               that a charge tapers and the charger can - or cannot - see
 *               its termination current.  Off by default: VBAT is then the
 *               fixed value of gl_sim_set_vbat_mv
 *   MCU states  running / idle / Stop 2, held in reset, in the ROM loader
 *               (gl_sim_mcu_enter_rom), and SHUTDOWN = ship mode
 *               (gl_hal_ship_mode_enter): every pin high-impedance, nothing
 *               runs, only VBUS on its wake-up pin restarts the MCU
 *   core clock  SLOW / FAST as set by gl_hal_clock_set: every call is in the
 *               trace, the time spent FAST and the heavy computation done
 *               while SLOW are counted
 *   board pulls the level each pin of GL_PINS_RESET_TABLE has while the MCU
 *               does not drive it (reset, ROM bootloader, ship mode):
 *               gl_sim_pin_level()
 *   USB         byte pipes to an imaginary host that can be absent, active
 *               or suspended; the USB supply of the MCU, which goes away
 *               with VBUS at once while VBUS_SENSE may lag behind
 *               (gl_sim_vbus_remove_lagging)
 *
 * It CHECKS, and counts in gl_sim_violations_t:
 *   - the camera rail rule (every camera-facing pin ANALOG or driven low
 *     while V2V8_CAM is off, and for 1 ms after it is switched on)
 *   - two cameras driving the shared bus at once.  A sensor in power-down
 *     is taken to KEEP its pads enabled unless
 *     GL_PROV_OV7692_PWDN_TRISTATES_OUTPUTS says otherwise, so the overlap
 *     that power-up cannot avoid (both sensors leave reset with their pads
 *     enabled) is visible: it is measured in gl_sim_stats_t
 *     (cam_powerup_overlap_us, ..._streaming_us) as an explicitly accepted
 *     figure, and any overlap AFTER both sensors have been released once is
 *     a violation
 *   - SCCB traffic to an unpowered / unclocked / powered-down camera
 *   - LCD protocol (active-high SCS, LSB first, mode 0, <= 1.1 MHz, frame
 *     length, line addresses, chip-select timing, DISP without EXTCOMIN)
 *   - flash protocol (program / erase without WREN, commands while busy or
 *     in deep power-down, overlong page programs)
 *   - IMU protocol (SPI mode 3, MSB first)
 *   - both SPI1 chip selects active, transfers with no device selected,
 *     bus pins not in ALTERNATE mode
 *   - Stop mode entered with the camera rail on, a capture running, USB
 *     started, the ADC or the op-amp powered, or a chip select asserted
 *   - more than one grain LED lit, ADC use while unpowered
 *   - the watchdog not kicked for longer than its period
 *   - USB left on (started or in standby), at a sleep, without its supply
 *   - the charger rules of rev E (counted as `power`):
 *       Stop mode or ship mode entered with CHG_INHIBIT driven high and VBUS
 *       absent (a stop left behind by a sleeping MCU: the next cradle would
 *       not charge until the firmware wakes, and the gate resistor draws
 *       28 uA meanwhile);
 *       Stop mode entered with VBUS present and no wake-up within
 *       GL_SIM_CHG_SUPERVISE_MAX_MS (the firmware's own supervision - its
 *       narrower window, its time limit - would not come round);
 *       a charge running for longer than GL_SIM_CHG_REACT_MAX_MS at a
 *       stretch with the true cell temperature outside the FIRMWARE's
 *       window, 0..45 C, while firmware runs;
 *       CHG_INHIBIT as an open-drain output or with an internal pull (it
 *       drives a MOSFET gate: push-pull or analog, nothing else);
 *       CHG_STAT driven, or with an internal pull (an input with the board's
 *       pull-up, on a USB Type-C CC pad of the MCU)
 *   - ship mode entered with a device left on: the display, the camera rail,
 *     USB, the ADC or the op-amp, a chip select asserted, NTC_BIAS driven
 *     (counted as `stop_mode`)
 *   - NTC_BIAS still driven at a Stop-mode entry; an NTC conversion before
 *     the divider has settled; OPAMP_VOUT driven while the op-amp is off;
 *     a grain measurement with LCD_DISP low or not yet high for
 *     GL_PINS_GRAIN_BIAS_DISP_MS (counted as `analog`)
 *   - Stop mode entered with the fast core clock (counted as `clock`)
 *
 * The device models encode THIS PROJECT'S UNDERSTANDING of the parts (the
 * same datasheet recollections the drivers are written from, see the README
 * table "from memory - verify against datasheet").  A passing test shows
 * that driver and model agree and that the traffic is self-consistent; it
 * does not show that the real part behaves this way.
 */
#ifndef GL_SIM_H
#define GL_SIM_H

#include "gl_hal.h"

/* ---- life cycle and time ------------------------------------------------------ */

/** Power-on state of the whole simulated board; empties the trace.  The
 *  flash contents are erased only if `erase_flash` is true (false keeps
 *  them, as a real power cycle would). */
void gl_sim_reset(bool erase_flash);

/** Simulated time since gl_sim_reset(). */
uint64_t gl_sim_now_us(void);

/** Let simulated time pass (devices run, scheduled calls fire). */
void gl_sim_advance_ms(uint32_t ms);

typedef void (*gl_sim_fn_t)(void *arg);

/** Call fn(arg) when simulated time reaches t_ms (absolute, since reset).
 *  Up to 64 pending calls; later registrations at the same time run later.
 *  Returns false if the table is full. */
bool gl_sim_at_ms(uint32_t t_ms, gl_sim_fn_t fn, void *arg);

/* ---- trace --------------------------------------------------------------------- */

typedef enum {
    GL_SIM_TR_GPIO_MODE = 1,  /**< a = pin, b = mode */
    GL_SIM_TR_GPIO_WRITE,     /**< a = pin, b = level */
    GL_SIM_TR_SPI_CFG,        /**< a = bus, b = mode | lsb_first << 8, c = hz */
    GL_SIM_TR_SPI_XFER,       /**< a = bus, b = device (gl_sim_dev_t), c = length, d = offset of the tx bytes in the byte log */
    GL_SIM_TR_SCCB_WRITE,     /**< a = camera, b = register, c = value, d = status */
    GL_SIM_TR_SCCB_READ,      /**< a = camera, b = register, c = value read, d = status */
    GL_SIM_TR_XVCLK,          /**< a = 1 start / 0 stop, c = hz */
    GL_SIM_TR_DCMI_START,     /**< a = driving camera (0, 1; 0xFF none), c = expected bytes */
    GL_SIM_TR_DCMI_DONE,      /**< a = final gl_dcmi_state_t, c = bytes */
    GL_SIM_TR_DCMI_STOP,
    GL_SIM_TR_ADC_POWER,      /**< a = on */
    GL_SIM_TR_ADC_READ,       /**< a = channel, b = counts, c = lit LED mask */
    GL_SIM_TR_OPAMP,          /**< a = on */
    GL_SIM_TR_EXTCOMIN,       /**< a = 1 start / 0 stop, c = period in LSE ticks */
    GL_SIM_TR_USB,            /**< a = 1 start / 0 stop */
    GL_SIM_TR_SLEEP,          /**< a = mode, c = microseconds slept (low 32 bits) */
    GL_SIM_TR_REBOOT,         /**< a = gl_reboot_t */
    GL_SIM_TR_IRQ_ENABLE,     /**< a = enable, c = mask */
    GL_SIM_TR_CLOCK,          /**< a = gl_clock_t asked for, b = gl_clock_t before the call */
    GL_SIM_TR_SHIP,           /**< gl_hal_ship_mode_enter(): a = 1 entered, 0 refused (VBUS present) */
    GL_SIM_TR_USB_STANDBY     /**< gl_hal_usb_standby(): a = 1 entered, 0 refused */
} gl_sim_tr_type_t;

typedef enum {
    GL_SIM_DEV_NONE = 0,
    GL_SIM_DEV_LCD,
    GL_SIM_DEV_FLASH,
    GL_SIM_DEV_IMU,
    GL_SIM_DEV_CONFLICT
} gl_sim_dev_t;

typedef struct {
    uint64_t t_us;
    uint8_t type; /**< gl_sim_tr_type_t */
    uint8_t a;
    uint16_t b;
    uint32_t c;
    uint32_t d;
} gl_sim_trace_t;

/** Number of trace records since the last reset / clear (the trace keeps
 *  the first GL_SIM_TRACE_MAX records and counts the rest as lost). */
#define GL_SIM_TRACE_MAX 262144u
size_t gl_sim_trace_count(void);
size_t gl_sim_trace_lost(void);
const gl_sim_trace_t *gl_sim_trace_at(size_t index);
/** Forget the trace and the SPI byte log (violation counters are kept). */
void gl_sim_trace_clear(void);
/** Transmitted bytes of a GL_SIM_TR_SPI_XFER record (d = offset, c = length).
 *  NULL if the byte log overflowed before that transfer. */
const uint8_t *gl_sim_trace_bytes(const gl_sim_trace_t *xfer);

/* ---- pins ---------------------------------------------------------------------- */

gl_pin_mode_t gl_sim_pin_mode(gl_pin_t pin);
bool gl_sim_pin_latch(gl_pin_t pin);
/** True if the MCU actively drives the pin high / low right now. */
bool gl_sim_pin_drives_high(gl_pin_t pin);
bool gl_sim_pin_drives_low(gl_pin_t pin);
/**
 * The electrical level of a pin as the BOARD sees it: the MCU's level where
 * it drives, otherwise the level of the board's resistor (GL_PINS_RESET_TABLE,
 * generated from the netlist's pin map: pull-downs on LCD_SCS, LCD_DISP,
 * CAM_PWR_EN, CHG_INHIBIT and the BOOT0 pad, pull-ups on FLASH_CS, IMU_CS
 * and OPAMP_VOUT) or the level an external circuit puts on the pin (the
 * charger on CHG_STAT, the VBUS divider, the IMU).  Valid before
 * gl_hal_init() and in ship mode too.  For a pin with neither driver nor
 * pull the result is false.
 */
bool gl_sim_pin_level(gl_pin_t pin);
/** Set the level an external circuit puts on an input pin.  The IMU
 *  interrupts are driven by the IMU model and CHG_STAT by the CHARGER model
 *  (a level set here lasts until the model next looks).  VBUS_SENSE: the
 *  marker is put into (true) or lifted out of (false) the cradle - the VBUS
 *  pad, the USB supply and the pin together, at once. */
void gl_sim_set_input(gl_pin_t pin, bool level);
/** Lift the marker out of the cradle as the board does it: VBUS and the USB
 *  supply of the MCU are gone NOW, the VBUS_SENSE pin follows `lag_ms` later
 *  (the divider discharges the pad: up to GL_PINS_VBUS_REMOVAL_SEEN_MS). */
void gl_sim_vbus_remove_lagging(uint32_t lag_ms);
/** True while 5 V is on the VBUS pad (whatever VBUS_SENSE reads). */
bool gl_sim_vbus_present(void);

/**
 * An MCU reset WITHOUT a power cycle (reset pin, watchdog, software reset):
 * every pin goes high-Z at the same instant, the peripherals stop, the
 * devices on the board keep their state.  From then until the next
 * gl_hal_init() the model is "MCU in reset": the board's pull resistors and
 * the charger's hardware default are all there is.  `reason`: GL_RESET_*.
 */
/** What the memory LCD draws with DISP low (default GL_SIM_I_LCD_OFF_UA: 0,
 *  "not known").  Counted whenever DISP is low, in every MCU state. */
void gl_sim_set_lcd_off_ua(double ua);
void gl_sim_mcu_reset(uint32_t reason);
/** The boot stub's backup register as the model holds it (TAMP BKP3R). */
uint32_t gl_sim_boot_attempts_reg(void);
/** The same reset, after which ST's ROM loader runs (an update): the pins
 *  stay as the reset left them and the MCU draws GL_SIM_I_MCU_ROM_UA from
 *  the cell node until the next gl_hal_init(). */
void gl_sim_mcu_enter_rom(void);
/** True from gl_hal_ship_mode_enter() until VBUS wakes the MCU (or a reset
 *  ends it for a moment: gl_hal_init() then goes back, see gl_hal.h).
 *  While it is true no firmware runs: a test stops calling the main loop,
 *  and calls gl_app_init() again when this has become false. */
bool gl_sim_mcu_shutdown(void);

/* ---- rule violations ------------------------------------------------------------ */

typedef struct {
    unsigned cam_rail;        /**< camera-facing pin not parked while the rail is off */
    unsigned cam_contention;  /**< both cameras driving the shared bus */
    unsigned cam_sccb;        /**< SCCB to a camera that cannot answer */
    unsigned dcmi;            /**< capture started with no driving camera, bad config, ... */
    unsigned lcd;             /**< LCD protocol or timing */
    unsigned flash;           /**< flash protocol */
    unsigned imu;             /**< IMU protocol */
    unsigned spi;             /**< chip-select overlap, no device selected, pins not ALTERNATE */
    unsigned stop_mode;       /**< Stop entered with something that needs clocks or power */
    unsigned analog;          /**< ADC / op-amp misuse, several grain LEDs lit */
    unsigned watchdog;        /**< not kicked within the watchdog period */
    unsigned deadlock;        /**< gl_hal_sleep with nothing that could ever wake it */
    unsigned power;           /**< USB on without its supply; the charger rules (see above) */
    unsigned clock;           /**< Stop mode with the fast core clock */
    char first[160];          /**< description of the first violation of any kind */
} gl_sim_violations_t;

const gl_sim_violations_t *gl_sim_violations(void);
/** Sum of all counters. */
unsigned gl_sim_violation_total(void);

/* ---- statistics ------------------------------------------------------------------ */

typedef struct {
    uint64_t stop_us;          /**< time spent in gl_hal_sleep(GL_SLEEP_STOP) */
    uint64_t idle_us;          /**< time spent in gl_hal_sleep(GL_SLEEP_IDLE) */
    uint64_t cam_rail_on_us;   /**< total time V2V8_CAM was on */
    uint32_t cam_rail_cycles;  /**< off -> on transitions */
    uint32_t watchdog_kicks;
    uint32_t reboots;
    uint8_t last_reboot;       /**< gl_reboot_t of the most recent request */
    uint32_t boot_confirms;    /**< gl_hal_boot_confirm() calls */
    /** The boot stub of E34, modelled at every gl_sim_mcu_reset(): how many
     *  resets passed through it, what it decided at the last one
     *  (gl_boot_action_t, gl_boot_why_t), and at how many resets it would
     *  NOT have started the application (loader, or waiting for VBUS). */
    uint32_t boot_stub_passes;
    uint8_t boot_last_action;
    uint8_t boot_last_why;
    uint32_t boot_not_started;
    uint32_t frames_captured;  /**< completed DCMI captures */
    /** Time both sensors had their pads enabled before both had been
     *  released once since the rail came on (the power-up window that
     *  firmware cannot close if PWDN does not tri-state the pads), and the
     *  part of it during which one of the two was streaming. */
    uint64_t cam_powerup_overlap_us;
    uint64_t cam_powerup_overlap_streaming_us;
    uint32_t trace_points[GL_TRACE_COUNT]; /**< gl_hal_trace() calls per point */
    uint64_t compute_us;       /**< simulated time charged for computation */
    uint64_t stage_us[GL_TRACE_COUNT];    /**< ... per trace point */
    uint64_t stage_instr[GL_TRACE_COUNT]; /**< instructions the cost table gives for the work
                                               reported at each trace point (whatever the
                                               time charged for them) */
    /* supply (the current model below).  Unit: microampere-seconds = microcoulombs.
     * The board hangs on the cell's node (the charger has no power path): what it
     * draws comes out of the cell, unless a charge is running - then the charger
     * supplies it, and it is counted as load_docked_uas instead */
    double charge_uas;         /**< drawn from the cell in all (the protection circuit's own
                                    GL_SIM_I_CELL_PCM_UA included) */
    double charge_cam_uas;     /**< of it: the camera rail */
    double charge_mcu_uas;     /**< the MCU (run, idle sleep, Stop 2, Shutdown) */
    double charge_imu_uas;     /**< the IMU */
    double load_docked_uas;    /**< what the board drew from the cell's node while VBUS was
                                    present, charging or not: the part of the charger's
                                    output current that is NOT charge current, and the
                                    figure its termination threshold is up against */
    uint64_t docked_us;        /**< time VBUS was present */
    uint64_t run_us;           /**< MCU running (not in gl_hal_sleep / gl_hal_delay_ms) */
    uint64_t run_fast_us;      /**< ... of it with the fast clock */
    uint64_t idle_fast_us;     /**< idle sleep (or a millisecond delay) with the fast clock */
    /* core clock */
    uint32_t clock_to_fast;    /**< SLOW -> FAST switches */
    uint32_t clock_to_slow;    /**< FAST -> SLOW switches */
    uint32_t clock_calls;      /**< gl_hal_clock_set() calls, including the ones that change nothing */
    uint64_t clock_fast_us;    /**< time spent with the fast clock */
    uint32_t heavy_while_slow; /**< vision / solve trace points reached with the SLOW clock
                                    (GL_TRACE_RENDER is light and belongs to the slow clock) */
    /* cell temperature divider */
    uint32_t ntc_reads;        /**< conversions of GL_ADC_CH_CELL_NTC with the bias driven */
    uint64_t ntc_bias_us;      /**< total time NTC_BIAS was driven high */
    /* charger (the MODEL of the BQ25101, not what the firmware believes) */
    uint64_t chg_on_us;        /**< time a charge ran while firmware was running */
    uint64_t chg_outside_us;   /**< of it, with the true cell temperature outside the
                                    FIRMWARE's window, 0..45 C */
    uint64_t chg_outside_longest_us; /**< the longest single stretch of that */
    uint64_t chg_in_reset_us;  /**< time a charge ran with NO firmware: MCU in reset, in the
                                    ROM loader or in ship mode */
    uint64_t chg_alone_outside_us; /**< of THAT, with the cell outside 0..45 C: the charger's
                                    WARM zone (45..60 C, 4.06 V) on its own */
    uint64_t chg_hw_outside_us; /**< time a charge ran with the cell outside the CHARGER's own
                                    window, 0..60 C, whoever was running: 0 unless its
                                    thermistor NTC1 is open */
    uint64_t chg_warm_us;      /**< time a charge ran in the charger's WARM zone (4.06 V) */
    uint64_t chg_cool_us;      /**< ... in its COOL zone (half current) */
    uint32_t chg_terminations; /**< charges the charger ended by itself (termination current) */
    uint32_t chg_timer_faults; /**< charges its safety timer ended */
    uint64_t inhibit_us;       /**< time CHG_INHIBIT was driven high */
    uint32_t ship_entries;     /**< gl_hal_ship_mode_enter() calls that entered ship mode */
    uint32_t ship_wakes;       /**< times VBUS woke the MCU from ship mode */
    uint64_t shutdown_us;      /**< time spent in ship mode */
    uint64_t grain_bias_short_us; /**< shortest DISP-high time seen before a grain conversion
                                    (UINT64_MAX: none measured) */
} gl_sim_stats_t;

const gl_sim_stats_t *gl_sim_stats(void);

/** True while V2V8_CAM is on (CAM_PWR_EN driven high). */
bool gl_sim_cam_rail_on(void);

/* ---- LCD model -------------------------------------------------------------------- */

typedef struct {
    /** Panel memory: 128 lines of 16 bytes; line address n (1..128) is at
     *  mem[(n - 1) * 16], bytes and bits as received (first bit on the wire
     *  = bit 0 of the first byte). */
    uint8_t mem[128 * 16];
    bool disp;                /**< DISP pin high */
    bool extcomin;            /**< EXTCOMIN square wave running */
    uint16_t extcomin_period; /**< in LSE ticks */
    uint32_t frames;          /**< chip-select frames received */
    uint32_t lines_written;
    uint32_t clears;
    uint8_t last_frame[2400]; /**< bytes of the most recent frame */
    uint16_t last_frame_len;
} gl_sim_lcd_t;

const gl_sim_lcd_t *gl_sim_lcd(void);

/* ---- flash model ------------------------------------------------------------------ */

#define GL_SIM_FLASH_BYTES (8u * 1024u * 1024u)

typedef struct {
    uint32_t reads, page_programs, sector_erases;
    uint32_t bytes_programmed;
    uint32_t overwrite_bytes; /**< programmed bytes that were not blank (NOR AND) */
    uint32_t programs_dropped; /**< page programs that did nothing (gl_sim_flash_fail_programs) */
    bool deep_power_down;
} gl_sim_flash_stats_t;

const gl_sim_flash_stats_t *gl_sim_flash_stats(void);
/** A flash that does not program: every page program is accepted and leaves
 *  the cells as they were, until switched off again (or gl_sim_reset).  For
 *  the tests of "a refused store changes nothing". */
void gl_sim_flash_fail_programs(bool fail);
/** Direct access to the simulated memory array (GL_SIM_FLASH_BYTES). */
uint8_t *gl_sim_flash_mem(void);

/* ---- IMU model -------------------------------------------------------------------- */

/** What the IMU physically experiences at time t_us, in MARKER axes:
 *  specific force in g (at rest: +1 g along up) and angular rate in rad/s. */
typedef void (*gl_sim_imu_fn_t)(void *ctx, uint64_t t_us, float accel_g[3], float gyro_rad_s[3]);

/** Install a motion function (NULL = the static state below). */
void gl_sim_imu_set_motion(gl_sim_imu_fn_t fn, void *ctx);
/** Static state used when no motion function is installed. */
void gl_sim_imu_set_static(const float accel_g[3], const float gyro_rad_s[3]);
/** Sensor imperfections: white noise per sample (accel in g rms, gyro in
 *  rad/s rms), a constant accelerometer offset in g and gyro bias in rad/s
 *  (marker axes), and the die temperature. */
void gl_sim_imu_set_errors(float accel_noise_g, float gyro_noise_rad_s, const float accel_offset_g[3],
                           const float gyro_bias_rad_s[3]);
void gl_sim_imu_set_temperature(float temp_c);
/** How the simulated board mounts the sensor: marker axis i reads
 *  sign[i] * (sensor axis axis[i]).  Default: identity. */
void gl_sim_imu_set_mounting(const int8_t axis[3], const int8_t sign[3]);
/** Make the IMU absent (no answer on SPI: MISO reads 0xFF). */
void gl_sim_imu_set_present(bool present);
/** Power glitch of the IMU alone: every register back to its reset value
 *  (both sensors off, interrupts unrouted); the device still answers. */
void gl_sim_imu_power_glitch(void);
/** Die temperature the MCU's own sensor reports.  By default it follows
 *  the IMU's (one board, one temperature); calling this pins it. */
void gl_sim_set_mcu_temperature(float temp_c);

/* ---- cell temperature, the two thermistors, charger and cell ------------------- */

/** The TRUE cell temperature (what both NTCs sit on, what the charger model
 *  acts on and what the charge rules are judged by).  By default it follows
 *  the IMU's temperature (one board, one temperature); calling this pins it. */
void gl_sim_set_cell_temperature(float temp_c);
float gl_sim_cell_temperature(void);

typedef enum {
    GL_SIM_NTC_NORMAL = 0,
    GL_SIM_NTC_OPEN,      /**< NTC broken off: the sense pin floats / follows the bias */
    GL_SIM_NTC_SHORT,     /**< NTC shorted: the sense pin stays at ground */
    GL_SIM_NTC_STUCK_HIGH /**< the sense pin is bridged to the 2.8 V rail */
} gl_sim_ntc_fault_t;

void gl_sim_ntc_set_fault(gl_sim_ntc_fault_t fault);
/** Part tolerances of the divider of THIS simulated unit, as relative errors
 *  (0.01 = +1 %): NTC resistance at 25 C, B constant, series resistor. */
void gl_sim_ntc_set_tolerance(float r25_rel, float b_rel, float series_rel);
/** Counts GL_ADC_CH_CELL_NTC would read (noise-free) at a cell temperature
 *  with the bias driven: the model's own forward calculation, in double
 *  precision, for the tests of the driver's conversion. */
double gl_sim_ntc_counts_at(double temp_c);

/** NTC2 is the MCU's thermistor (the functions above).  NTC1 is the
 *  CHARGER's, on its TS pin; the MCU cannot see it. */
typedef enum {
    GL_SIM_NTC1_NORMAL = 0,
    GL_SIM_NTC1_OPEN,     /**< a cracked joint: TS floats.  The charger then has NO temperature
                               window, no safety timer and no termination
                               (GL_PROV_BQ25101_TS_OPEN_IS_TTDM) */
    GL_SIM_NTC1_SHORT     /**< TS at ground: the charger is disabled */
} gl_sim_ntc1_fault_t;
void gl_sim_ntc1_set_fault(gl_sim_ntc1_fault_t fault);

/** What the charger of the model is doing. */
typedef enum {
    GL_SIM_CHG_NO_INPUT = 0,  /**< no VBUS, or an input below what the charger needs */
    GL_SIM_CHG_DISABLED,      /**< TS held at ground: CHG_INHIBIT is driven high (or NTC1 shorted) */
    GL_SIM_CHG_COLD,          /**< its thermistor below 0 C: no charge */
    GL_SIM_CHG_HOT,           /**< its thermistor above 60 C: no charge */
    GL_SIM_CHG_DONE,          /**< terminated; starts again when the cell has fallen 100 mV */
    GL_SIM_CHG_TIMER,         /**< its safety timer has expired; cleared by VBUS or TS toggling */
    GL_SIM_CHG_FAST,          /**< charging: 19.8 mA, to 4.20 V */
    GL_SIM_CHG_COOL,          /**< charging at half current (0..10 C) */
    GL_SIM_CHG_WARM,          /**< charging to 4.06 V (45..60 C) */
    GL_SIM_CHG_TTDM           /**< charging with NTC1 open: no limits of any kind */
} gl_sim_chg_state_t;
gl_sim_chg_state_t gl_sim_charger_state(void);
const char *gl_sim_charger_state_name(gl_sim_chg_state_t state);
/** True while a charge runs (one of the last four states): the charger's
 *  CHG output is low then. */
bool gl_sim_charger_on(void);
/** Current out of the charger right now, microamperes (cell + board). */
double gl_sim_charger_out_ua(void);
/** Make the charger's input too low for it (a weak USB source behind the
 *  cradle's fuse: NETLIST_NOTES 4.1): VBUS_SENSE reads high, the charger
 *  does not charge. */
void gl_sim_charger_input_low(bool low);
/** Break the firmware's stop: the MOSFET on the charger's TS pin (or its gate
 *  connection) is open, CHG_INHIBIT high pulls nothing. */
void gl_sim_charger_stop_broken(bool broken);
/** The other reading of the charger's status output (gl_provisional.h,
 *  GL_PROV_BQ25101_CHG_LOW_ON_RECHARGE: NOT CONFIRMED which is right): CHG is
 *  low during the FIRST charge cycle only; a recharge after a termination
 *  runs with CHG released, until VBUS goes or the charger is disabled
 *  through TS.  The reset default is !GL_PROV_BQ25101_CHG_LOW_ON_RECHARGE.
 *  gl_sim_charger_on() and the statistics keep telling what the charger
 *  DOES; only the pin differs. */
void gl_sim_charger_stat_first_cycle_only(bool first_only);
/** Longest stretch a charge may run with the cell outside the firmware's
 *  window (0..45 C) while firmware runs before it counts as a violation,
 *  and the longest Stop-mode sleep allowed in the cradle. */
#define GL_SIM_CHG_REACT_MAX_MS 10000u
#define GL_SIM_CHG_SUPERVISE_MAX_MS 10000u

/** Switch the CELL model on, at a state of charge of 0..1.  From then on
 *  VBAT follows the cell (open-circuit voltage curve, GL_SIM_CELL_R_OHM)
 *  and the charge that goes into it and out of it; gl_sim_set_vbat_mv() is
 *  ignored.  The curve and the resistance are guesses for a 43 mAh pouch
 *  cell (no data sheet): good for "does the charge terminate", not for a
 *  charge time. */
void gl_sim_cell_enable(float soc);
float gl_sim_cell_soc(void);
#define GL_SIM_CELL_MAH 43.0
#define GL_SIM_CELL_R_OHM 1.5
/** What the board draws from the cell's node right now, microamperes (the
 *  supply model below, with the MCU in its present mode). */
double gl_sim_load_ua(void);
/** Light on the underside (the grain opening): with the op-amp off the
 *  photodiode then draws GL_SIM_I_WAKE_PULLUP_LIT_UA through the 150 kohm
 *  that holds the wake line of the ROM loader high (NETLIST_NOTES 4.10). */
void gl_sim_set_underside_lit(bool lit);

/* ---- core clock ----------------------------------------------------------------- */

/** The clock the firmware last asked for. */
gl_clock_t gl_sim_clock(void);
/** Make the next `count` switches to GL_CLOCK_FAST fail (PLL does not lock). */
void gl_sim_clock_fail(unsigned count);
/** Make the next `count` switches back to GL_CLOCK_SLOW fail: the call
 *  returns an error and the core is STILL fast (what the STM32 backend
 *  reports when the system clock could not be switched back to MSIS). */
void gl_sim_clock_fail_slow(unsigned count);
/** Make the next `count` transfers on an SPI bus fail with `st` AFTER they
 *  have taken place (what a HAL time-out looks like to the driver). */
void gl_sim_spi_fail(gl_spi_bus_t bus, unsigned count, gl_status_t st);
/** Lose pending interrupt latches: the bits in `mask` are cleared as if the
 *  latch had been overwritten (the race the STM32 backend must not have). */
void gl_sim_irq_drop(uint32_t mask);
/** Charge a FIXED `us` of simulated time at every gl_hal_trace(point, ...)
 *  instead of what the cost model gives (0 = back to the model; cleared by
 *  gl_sim_reset). */
void gl_sim_set_compute_us(gl_trace_point_t point, uint32_t us);

/* ---- computation time: the cost model --------------------------------------------- */

/**
 * MCU clock cycles per instruction of the cost table (gl_sim_cost.h counts
 * instructions of the x86-64 host build).  NOT MEASURED - no board exists.
 * What it stands for: a Cortex-M33 runs about as many Thumb-2 instructions
 * as the host runs x86-64 ones for this code (more loads and stores, no
 * memory operands; fewer instructions for rounding and conversions), and
 * needs 1 cycle for most of them, 2 for a load, 2-3 for a taken branch and
 * 14 for each single-precision division or square root (the row measurement
 * has about 15 of those per row).  LOW assumes the code behaves like plain
 * integer code with the instruction cache hitting; HIGH leaves room for
 * flash wait states behind cache misses, -Os code that is longer than the
 * host's -O2 code, and the library routines (newlib's sqrtf with errno,
 * memset).  The honest statement is the range; NOMINAL is where the tests
 * run.
 */
#define GL_SIM_CPI_LOW 1.5f
#define GL_SIM_CPI_NOMINAL 2.0f
#define GL_SIM_CPI_HIGH 3.0f
/** Core clock of the two settings of gl_hal_clock_set() (hal/stm32u5: PLL
 *  160 MHz, MSIS 48 MHz). */
#define GL_SIM_CLOCK_FAST_HZ 160000000u
#define GL_SIM_CLOCK_SLOW_HZ 48000000u

/** Set the cycles-per-instruction factor (0 = computation takes no time).
 *  STICKY: gl_sim_reset() does not change it, so that one scenario can be
 *  run at several factors; a test that changes it puts GL_SIM_CPI_NOMINAL
 *  back.  The default is GL_SIM_CPI_NOMINAL. */
void gl_sim_set_cpi(float cycles_per_instr);
float gl_sim_cpi(void);

/** Instructions the cost table gives for `work` at a trace point. */
uint64_t gl_sim_stage_instr(gl_trace_point_t point, uint32_t work);

/* ---- supply current model (ESTIMATE; every figure PROVISIONAL) ----------------------
 *
 * Currents at the cell, microamperes (all rails are linear regulators, so
 * load current = cell current).  EVERY ONE IS A DATA-SHEET FIGURE FROM
 * MEMORY, a figure of docs/research (unverified there) or of
 * electrical/gl1_main/NETLIST_NOTES.md (PROVISIONAL there), or a plain
 * guess, as each line says.  None is a measurement: no board exists.
 */
/** Both OVM7692 awake: 2 x 120 mW from 2.8 V (docs/research/micro-cameras.md,
 *  unverified), for as long as the camera rail is on. */
#define GL_SIM_I_CAM_RAIL_UA 86000.0
/** STM32U585 on its internal LDO (no SMPS on the RIT6): run at 160 MHz in
 *  voltage range 1 (about 55 uA/MHz + PLL), run at 48 MHz in range 3, the
 *  same in sleep mode (core clock gated), Stop 2 with all RAM retained and
 *  the RTC / LSE / LPTIM running (docs/research/processor-radio.md: about
 *  9 uA, reviewer recollection). */
#define GL_SIM_I_MCU_RUN_FAST_UA 9500.0
#define GL_SIM_I_MCU_IDLE_FAST_UA 3500.0
#define GL_SIM_I_MCU_RUN_SLOW_UA 2800.0
#define GL_SIM_I_MCU_IDLE_SLOW_UA 900.0
#define GL_SIM_I_MCU_STOP_UA 9.0
/** Stop 1 instead of Stop 2 while the USB device is in standby
 *  (GL_PROV_USB_WAKE_FROM_STOP2 = 0).  From memory, LOW CONFIDENCE. */
#define GL_SIM_I_MCU_STOP1_UA 70.0
/** Shutdown mode (ship mode), no RTC, low-speed oscillator off: 0.11 to
 *  0.21 uA in the data sheet as remembered. */
#define GL_SIM_I_MCU_SHUTDOWN_UA 0.2
/** ST's ROM loader running with USB: a GUESS (the core at a few MHz, the
 *  48 MHz oscillator and the USB core). */
#define GL_SIM_I_MCU_ROM_UA 4000.0
/** USB started: the 48 MHz oscillator with clock recovery (0.38 mA) and the
 *  USB core (about 1.3 mA), both on VDD = the cell's node (the transceiver
 *  itself is fed from VBUS).  From memory, LOW CONFIDENCE.  In standby (bus
 *  suspended, clocks stopped): a guess. */
#define GL_SIM_I_USB_UA 1700.0
#define GL_SIM_I_USB_STANDBY_UA 20.0
/** LSM6DSV16X: accelerometer + gyroscope in high-performance mode, the
 *  accelerometer alone in high-performance mode, in low-power mode (the
 *  wake-on-motion setting, 15 Hz), both off. */
#define GL_SIM_I_IMU_COMBO_UA 650.0
#define GL_SIM_I_IMU_ACCEL_UA 190.0
#define GL_SIM_I_IMU_WAKE_UA 5.0
#define GL_SIM_I_IMU_OFF_UA 3.0
/** What is always there on the rev E board (NETLIST_NOTES 4.12), part by
 *  part:
 *    the 2.8 V regulator MCP1700, quiescent (docs/research: 1.6 uA);
 *    the battery divider, 2 x 1 Mohm across the cell: 1.9 uA at 3.8 V
 *      (computed from the cell voltage of the model);
 *    the cell's protection circuit (docs/research/power.md: 3 uA).  It sits
 *      between the cell and the board's pads: a bench supply on the pads
 *      does not see it, the cell does;
 *    the charger with no input: leakage out of the cell (75 nA: the title of
 *      a data-sheet copy seen in a search, NETLIST_NOTES 4.2);
 *    the camera regulator LP5907, disabled (from memory: 0.2 uA typical,
 *      1 uA at most);
 *    E26: the USB-supply regulator is an LP5907 whose ENABLE pin is held at
 *      the 2.8 V rail.  That part has, from memory of its data sheet, an
 *      internal 1 Mohm pull-down on the enable pin: 2.8 uA, always.  NOT
 *      CONFIRMED (NETLIST_NOTES section 11 states the same figure, also
 *      from memory): if it is wrong, every sleep figure is 2.8 uA lower.
 *  The two thermistors draw nothing asleep: NTC1 is biased by the charger
 *  from VBUS only, NTC2 only while NTC_BIAS is driven (2.8 V across 10 kohm
 *  + the NTC: 140 uA at 25 C, computed by the model). */
#define GL_SIM_I_REG_2V8_UA 1.6
#define GL_SIM_R_VBAT_DIVIDER_OHM 2.0e6
#define GL_SIM_I_CELL_PCM_UA 3.0
#define GL_SIM_I_CHARGER_LEAK_UA 0.075
#define GL_SIM_I_REG_CAM_OFF_UA 0.2
#define GL_SIM_I_REG_USB_EN_UA 2.8
/** The always-on parts at a cell voltage (the sum of the list above). */
#define GL_SIM_I_ALWAYS_UA(vbat_mv)                                                         \
    (GL_SIM_I_REG_2V8_UA + (double)(vbat_mv) * 1000.0 / GL_SIM_R_VBAT_DIVIDER_OHM +          \
     GL_SIM_I_CELL_PCM_UA + GL_SIM_I_CHARGER_LEAK_UA + GL_SIM_I_REG_CAM_OFF_UA +             \
     GL_SIM_I_REG_USB_EN_UA)
/** The 150 kohm on the op-amp output (it holds a ROM-loader input high) with
 *  LIGHT on the photodiode and the op-amp off: 4.5 to 5.2 uA (NETLIST_NOTES
 *  4.10); nothing in the dark. */
#define GL_SIM_I_WAKE_PULLUP_LIT_UA 5.2
/** Resistors that draw only while a pin is driven against them (NETLIST_NOTES
 *  4.2, 4.6, 4.8, 4.10): DISP high (100 kohm pull-down) and the grain bias
 *  divider that hangs on DISP (200 kohm); CHG pulled low by the charger
 *  (100 kohm pull-up); CHG_INHIBIT high (100 kohm on the gate); the right
 *  camera's PWDN high (the 10 kohm BOOT0 resistor); the op-amp output driven
 *  low against its 150 kohm. */
#define GL_SIM_I_DISP_PULLDOWN_UA 28.0
#define GL_SIM_I_GRAIN_BIAS_UA 14.0
#define GL_SIM_I_CHG_STAT_PULLUP_UA 28.0
#define GL_SIM_I_CHG_INHIBIT_UA 28.0
#define GL_SIM_I_BOOT0_PULLDOWN_UA 280.0
#define GL_SIM_I_OPAMP_OUT_LOW_UA 19.0
/** Memory LCD with DISP on (15 uW static + EXTCOMIN); flash in standby / in
 *  deep power-down / while programming or erasing; ADC and op-amp powered;
 *  one grain LED lit. */
#define GL_SIM_I_LCD_ON_UA 6.0
/** Memory LCD with DISP LOW.  The netlist puts the panel's VDD and VDDA on
 *  the always-on 2.8 V rail (NETLIST_NOTES, rail V2V8), so the panel is
 *  POWERED asleep and in ship mode.  NO FIGURE IS KNOWN for that state (the
 *  Sharp data sheet was not read): the term exists, its default is 0, and
 *  every sleep and ship-mode figure of the model is therefore "plus what the
 *  panel draws with DISP low".  gl_sim_set_lcd_off_ua() sets it; the test
 *  of E14 (tests/test_e2e_power.c) states how much the panel may draw
 *  before the 25 uA limit is missed.  PROVISIONAL / NEEDS A DATA SHEET
 *  (phase-3 review, hardware finding 5). */
#define GL_SIM_I_LCD_OFF_UA 0.0
#define GL_SIM_I_FLASH_STANDBY_UA 5.0
#define GL_SIM_I_FLASH_DPD_UA 0.1
#define GL_SIM_I_FLASH_BUSY_UA 5000.0
#define GL_SIM_I_ADC_UA 300.0
#define GL_SIM_I_OPAMP_UA 150.0
#define GL_SIM_I_GRAIN_LED_UA 6000.0
/** Register value as the model currently holds it (tests of the driver's
 *  configuration writes). */
uint8_t gl_sim_imu_reg(uint8_t addr);

/* ---- camera model ------------------------------------------------------------------ */

/**
 * Scene callback: fill luma[h * w] (row-major) with the UPRIGHT image of
 * camera `cam` for the sensor window with top-left pixel (x0, y0).
 * `frame_no` counts the frames of that camera since it started streaming;
 * t_us is the simulated time at which the frame's exposure starts.
 */
typedef void (*gl_sim_scene_fn_t)(void *ctx, gl_cam_id_t cam, uint16_t x0, uint16_t y0,
                                  uint16_t w, uint16_t h, uint32_t frame_no, uint64_t t_us,
                                  uint8_t *luma);

void gl_sim_cam_set_scene(gl_sim_scene_fn_t fn, void *ctx);
/** Make a camera absent (SCCB is not acknowledged). */
void gl_sim_cam_set_present(gl_cam_id_t cam, bool present);
/** Product id the camera reports in registers 0x0A / 0x0B (default 0x7692;
 *  survives gl_hal-level power cycles, reset by gl_sim_reset). */
void gl_sim_cam_set_pid(gl_cam_id_t cam, uint16_t pid);
/** Make the camera's software reset never complete (register 0x12 bit 7
 *  stays set): a part that hangs in reset. */
void gl_sim_cam_set_reset_stuck(gl_cam_id_t cam, bool stuck);
/** Extra delay of camera `cam`'s frame timing, 0..frame period: the two
 *  free-running sensors are not synchronised on the real board. */
void gl_sim_cam_set_phase_us(gl_cam_id_t cam, uint32_t phase_us);
/** Register value of a camera (bank 0). */
uint8_t gl_sim_cam_reg(gl_cam_id_t cam, uint8_t reg);
/** True if the camera is powered, clocked, out of PWDN, awake and has its
 *  outputs enabled: it drives the shared bus. */
bool gl_sim_cam_driving(gl_cam_id_t cam);
/** True if the camera is streaming (powered, clocked, out of PWDN, awake). */
bool gl_sim_cam_streaming(gl_cam_id_t cam);
/** Frame period of the camera models, microseconds. */
#define GL_SIM_CAM_FRAME_US 33333u
/** Frames after stream start that the model delivers as black (unsettled). */
#define GL_SIM_CAM_BAD_FRAMES 2u

/* ---- analog model ------------------------------------------------------------------ */

void gl_sim_set_vbat_mv(uint16_t mv);
void gl_sim_set_vdda_mv(uint16_t mv);

typedef struct {
    float response[16];     /**< counts added while LED k is lit (0..7 red, 8..15 NIR) */
    float dark_counts;      /**< output with no LED (mid-rail bias + ambient) */
    float noise_counts;     /**< rms noise of one ADC sample */
    float drift_counts_per_ms; /**< ambient drift */
} gl_sim_grain_t;

void gl_sim_grain_set(const gl_sim_grain_t *g);
/** Bit k set = grain LED k is lit by the present charlieplex pin states
 *  (model netlist: see hal/host/gl_sim_core.c). */
uint32_t gl_sim_grain_lit_mask(void);

/* ---- USB model ---------------------------------------------------------------------- */

/** The imaginary host opens / closes the CDC port.  Opening it also makes
 *  the bus ACTIVE (a host is there and talks). */
void gl_sim_usb_host_open(bool open);
/** What the host does on the bus: GL_USB_BUS_NONE (no host: a wall charger;
 *  the state after gl_sim_reset), GL_USB_BUS_ACTIVE, GL_USB_BUS_SUSPENDED
 *  (the PC has gone to sleep).  Going to ACTIVE while the device is in
 *  standby is the "resume": it raises GL_IRQ_USB_WAKE. */
void gl_sim_usb_host_bus(gl_usb_bus_t bus);
/** Host -> device bytes.  Dropped if the device has not started USB; if it
 *  is in standby the host resumes the bus first and the bytes wait in the
 *  pipe (a real host repeats what is not acknowledged). */
void gl_sim_usb_host_send(const uint8_t *data, size_t len);
/** Device -> host bytes received so far; returns the count copied and
 *  removes them from the pipe. */
size_t gl_sim_usb_host_recv(uint8_t *buf, size_t max);
/** Limit how many bytes one gl_hal_usb_write() call accepts (0 = no limit),
 *  to exercise partial writes. */
void gl_sim_usb_set_tx_chunk(size_t max);

/* ---- system -------------------------------------------------------------------------- */

void gl_sim_set_reset_reason(uint32_t flags);
void gl_sim_set_rtc(uint32_t seconds);

#endif /* GL_SIM_H */
