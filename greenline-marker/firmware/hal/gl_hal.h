/*
 * gl_hal.h - the ONLY hardware interface of the GreenLine GL-1 firmware.
 *
 * Everything in drivers/ and app/ reaches hardware through the functions
 * declared here and through nothing else.  core/ does not include this file
 * at all (core is pure computation).  Two backends implement it:
 *
 *   hal/host     simulator: records bus traffic and pin activity, serves
 *                synthetic frames and sensor data.  Used by the unit tests.
 *   hal/stm32u5  STM32U585RIT6 backend written against the STM32Cube HAL
 *                API.  NOT compiled in this repository's build (no vendor
 *                SDK is available here); see its header comments.
 *
 * Design rules
 *  - Plain C99 functions, no callbacks from interrupt context into the
 *    drivers.  Interrupt sources latch a bit in a pending mask that the
 *    cooperative main loop collects with gl_hal_irq_take().
 *  - Pins are LOGICAL names (gl_pin_t).  The mapping to pads and alternate
 *    functions lives in hal/stm32u5/gl_pins.h (generated from the
 *    DESIGN_SPEC pin table).  A driver never names a port or a pad.
 *  - Chip selects, PWDN, DISP and the charlieplex pins are ordinary GPIOs
 *    driven by the drivers, so that the host simulator can check the exact
 *    pin sequences (camera rail rule, active-high LCD chip select, ...).
 *  - All calls are blocking and bounded; none allocates memory.
 *  - Units are in the names: _ms, _us, _hz, _mv.
 *  - EVERY stop / disable / power-down call (gl_hal_dcmi_stop,
 *    gl_hal_xvclk_stop, gl_hal_extcomin_stop, gl_hal_usb_stop,
 *    gl_hal_adc_power(false), gl_hal_opamp_enable(false),
 *    gl_hal_wake_timer_start(0), gl_hal_clock_set(GL_CLOCK_SLOW)) must be
 *    safe at any time after
 *    gl_hal_init(), in particular BEFORE the matching start has ever been
 *    called: the drivers put their devices into the off state at boot by
 *    calling exactly these.  tests/test_basics.c calls each of them first
 *    on the host backend; a backend with peripheral handles must guard
 *    them (see hal/stm32u5).
 */
#ifndef GL_HAL_H
#define GL_HAL_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "gl_types.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ======================================================================= */
/* System                                                                   */
/* ======================================================================= */

/**
 * Bring up clocks (the SLOW clock, see gl_hal_clock_set), the tick, GPIO
 * defaults and the always-on peripherals.  After this call every
 * camera-facing pin is ANALOG, the camera rail enable is driven low, the LCD
 * chip select and DISP are driven low and all chip selects of active-low
 * devices are driven high - each at the level its board pull resistor
 * already holds during reset (DESIGN_SPEC section 4: 100 kohm pull-down on
 * the LCD chip select and DISP, 100 kohm pull-ups on the flash and IMU chip
 * selects), written to the output latch BEFORE the pin becomes an output, so
 * that no chip select moves at the hand-over.
 *
 * CHG_INHIBIT and NTC_BIAS are NOT touched: they stay ANALOG (high-Z), the
 * MCU's reset state.  The charger is ON BY DEFAULT in hardware; only
 * drivers/power pulls CHG_INHIBIT low, and only as the result of a
 * temperature measurement (see drivers/power.h for the state table).
 */
gl_status_t gl_hal_init(void);

/** Why the MCU last reset (bit mask). */
#define GL_RESET_POWER_ON   (1u << 0)
#define GL_RESET_PIN        (1u << 1)
#define GL_RESET_SOFTWARE   (1u << 2)
#define GL_RESET_WATCHDOG   (1u << 3)
#define GL_RESET_BROWNOUT   (1u << 4)
/** Reset cause flags latched at boot (GL_RESET_*); cleared by reading. */
uint32_t gl_hal_reset_reason(void);

typedef enum {
    GL_REBOOT_NORMAL = 0,  /**< plain system reset */
    GL_REBOOT_ROM_DFU = 1  /**< reset into the ST ROM USB-DFU bootloader */
} gl_reboot_t;

/** Reset the MCU.  Does not return on target; the host backend records the
 *  request and returns so that tests can observe it. */
void gl_hal_reboot(gl_reboot_t how);

/** Refresh the independent watchdog (period chosen by the backend, >= 4 s). */
void gl_hal_watchdog_kick(void);

/** 96-bit unique device identifier, little-endian words. */
void gl_hal_unique_id(uint8_t out[12]);

/* ======================================================================= */
/* Time                                                                     */
/* ======================================================================= */

/** Monotonic milliseconds since boot.  Keeps counting through Stop mode
 *  (LSE-clocked).  Wraps after 49.7 days; use unsigned differences. */
uint32_t gl_hal_tick_ms(void);

/** Microsecond time stamp from a free-running counter (the tick's own
 *  clock: 30.5 us resolution on the target).  Wraps after 71.6 minutes: use
 *  unsigned DIFFERENCES only.  Keeps counting through Stop mode. */
uint32_t gl_hal_time_us(void);

/** Busy/idle wait.  Resolution 1 ms; may sleep the core between ticks. */
void gl_hal_delay_ms(uint32_t ms);

/** Short busy wait, 1..10000 us, accuracy +-(1 us + 5 %). */
void gl_hal_delay_us(uint32_t us);

/** Seconds from the RTC (runs as long as the cell has charge; 0 = unset). */
uint32_t gl_hal_rtc_seconds(void);

/** Set the RTC (from the USB host). */
void gl_hal_rtc_set_seconds(uint32_t seconds);

/* ======================================================================= */
/* GPIO                                                                     */
/* ======================================================================= */

/** Logical pins.  Order is part of the host-simulator trace format: append
 *  only. */
typedef enum {
    /* --- camera rail and camera-facing pins (see the rail rule below) --- */
    GL_PIN_CAM_PWR_EN = 0, /**< LP5907 enable, high = V2V8_CAM on; NOT camera-facing */
    GL_PIN_CAM_L_PWDN,     /**< left camera PWDN (active level: gl_provisional.h) */
    GL_PIN_CAM_R_PWDN,     /**< right camera PWDN */
    GL_PIN_CAM_SCCB_SDA,   /**< shared SCCB data, pulled up to V2V8_CAM */
    GL_PIN_CAM_L_SCL,      /**< left camera SCCB clock */
    GL_PIN_CAM_R_SCL,      /**< right camera SCCB clock */
    GL_PIN_CAM_XVCLK,      /**< MCO output, 12 MHz */
    GL_PIN_CAM_D0,
    GL_PIN_CAM_D1,
    GL_PIN_CAM_D2,
    GL_PIN_CAM_D3,
    GL_PIN_CAM_D4,
    GL_PIN_CAM_D5,
    GL_PIN_CAM_D6,
    GL_PIN_CAM_D7,
    GL_PIN_CAM_PIXCLK,
    GL_PIN_CAM_HREF,
    GL_PIN_CAM_VSYNC,
    /* --- display --- */
    GL_PIN_LCD_SCS,        /**< chip select, ACTIVE HIGH */
    GL_PIN_LCD_DISP,       /**< display on, active high (external pull-down) */
    GL_PIN_LCD_EXTCOMIN,   /**< LPTIM1_CH1 60 Hz square wave */
    /* --- SPI1 (LCD + flash) and SPI2 (IMU) bus pins --- */
    GL_PIN_SPI1_SCK,
    GL_PIN_SPI1_MOSI,
    GL_PIN_SPI1_MISO,
    GL_PIN_SPI2_SCK,
    GL_PIN_SPI2_MOSI,
    GL_PIN_SPI2_MISO,
    /* --- chip selects and interrupts --- */
    GL_PIN_FLASH_CS,       /**< MX25R6435F CS#, active low */
    GL_PIN_IMU_CS,         /**< LSM6DSV16X CS, active low */
    GL_PIN_IMU_INT1,       /**< wake-on-motion, wake-capable pin */
    GL_PIN_IMU_INT2,
    /* --- grain sensor --- */
    GL_PIN_GRAIN_CP0,      /**< charlieplex pins, one 68 ohm resistor each */
    GL_PIN_GRAIN_CP1,
    GL_PIN_GRAIN_CP2,
    GL_PIN_GRAIN_CP3,
    GL_PIN_GRAIN_CP4,
    GL_PIN_OPAMP_VINP,     /**< OPAMP1 non-inverting input (mid-rail bias) */
    GL_PIN_OPAMP_VINM,     /**< OPAMP1 inverting input (photodiode cathode) */
    GL_PIN_OPAMP_VOUT,     /**< OPAMP1 output = ADC1 input */
    /* --- power --- */
    GL_PIN_VBAT_SENSE,     /**< ADC input behind the 2 x 1 Mohm divider */
    GL_PIN_CHG_STAT,       /**< MCP73831 STAT, input with pull-up, low = charging */
    GL_PIN_CHG_INHIBIT,    /**< rev C2: open-drain MCU pin on the gate of the PROG MOSFET.
                                LOW = charging STOPPED; released (high-Z) = the hardware
                                default, charging ON whenever VBUS is present.  Never
                                push-pull, never driven high (drivers/power.h) */
    GL_PIN_VBUS_SENSE,     /**< digital input from the VBUS divider, high = in cradle */
    /* --- USB --- */
    GL_PIN_USB_DM,
    GL_PIN_USB_DP,
    /* --- cell temperature (rev C2), appended: the order is the trace format --- */
    GL_PIN_NTC_BIAS,       /**< top of the NTC divider (10.0 kohm to NTC_SENSE, the 10 kohm
                                NTC from there to ground): push-pull HIGH only while a
                                conversion runs, ANALOG otherwise */
    GL_PIN_NTC_SENSE,      /**< ADC input at the divider's mid point */
    GL_PIN_COUNT
} gl_pin_t;

/** First and last camera-facing pin (inclusive), for loops that park them. */
#define GL_PIN_CAM_FACING_FIRST GL_PIN_CAM_L_PWDN
#define GL_PIN_CAM_FACING_LAST  GL_PIN_CAM_VSYNC

typedef enum {
    GL_PIN_MODE_ANALOG = 0,     /**< high impedance, input buffer off (lowest leakage) */
    GL_PIN_MODE_INPUT,          /**< digital input, no pull */
    GL_PIN_MODE_INPUT_PULLUP,
    GL_PIN_MODE_INPUT_PULLDOWN,
    GL_PIN_MODE_OUTPUT_PP,      /**< push-pull output; level from gl_hal_gpio_write */
    GL_PIN_MODE_OUTPUT_OD,      /**< open-drain output: write(false) pulls low, write(true) releases */
    GL_PIN_MODE_ALTERNATE       /**< routed to its peripheral (SPI, DCMI, MCO, I2C/SCCB, LPTIM, USB) */
} gl_pin_mode_t;

/**
 * CAMERA RAIL RULE (DESIGN_SPEC section 4): while V2V8_CAM is off every pin
 * from GL_PIN_CAM_FACING_FIRST to GL_PIN_CAM_FACING_LAST must be either
 * GL_PIN_MODE_ANALOG or an output driven LOW, so the sensors are not
 * back-powered through their protection diodes.  drivers/ov7692 enforces the
 * order; the host backend asserts it on every pin and rail change.
 */

/** Set the mode of a pin.  For outputs the level set by the most recent
 *  gl_hal_gpio_write() applies (default low), so write-then-mode is the
 *  glitch-free order. */
void gl_hal_gpio_mode(gl_pin_t pin, gl_pin_mode_t mode);

/** Set the output latch.  Has no electrical effect until the pin is an output. */
void gl_hal_gpio_write(gl_pin_t pin, bool high);

/** Read the pin level (valid in INPUT* and OUTPUT* modes). */
bool gl_hal_gpio_read(gl_pin_t pin);

/* ======================================================================= */
/* Interrupt / wake sources                                                 */
/* ======================================================================= */

#define GL_IRQ_IMU_INT1     (1u << 0)  /**< rising edge on IMU INT1 (wake-on-motion) */
#define GL_IRQ_IMU_INT2     (1u << 1)  /**< rising edge on IMU INT2 (data ready / tap) */
#define GL_IRQ_VBUS_CHANGE  (1u << 2)  /**< either edge on VBUS sense */
#define GL_IRQ_CHG_STAT     (1u << 3)  /**< either edge on charger STAT */
#define GL_IRQ_WAKE_TIMER   (1u << 4)  /**< gl_hal_wake_timer_start() expired */
#define GL_IRQ_USB_RX       (1u << 5)  /**< bytes waiting in the CDC receive buffer */
#define GL_IRQ_DCMI_DONE    (1u << 6)  /**< strip capture finished or failed */
#define GL_IRQ_TICK         (1u << 7)  /**< periodic tick while awake (optional) */

/** Enable or disable the sources in `mask` (all are disabled after init).
 *  Enabled sources also wake the MCU from Stop mode where the hardware
 *  allows it (INT1, VBUS, STAT, wake timer: yes; USB_RX, DCMI: Sleep only). */
void gl_hal_irq_enable(uint32_t mask, bool enable);

/** Atomically fetch and clear the pending-source mask. */
uint32_t gl_hal_irq_take(void);

/** Nestable global interrupt mask for short critical sections. */
void gl_hal_irq_lock(void);
void gl_hal_irq_unlock(void);

/** One-shot wake-up timer, 1 ms .. 24 h; restarts if already running.
 *  ms = 0 cancels. */
void gl_hal_wake_timer_start(uint32_t ms);

/* ======================================================================= */
/* Sleep                                                                    */
/* ======================================================================= */

typedef enum {
    GL_SLEEP_IDLE = 0, /**< WFI: core stopped, all peripherals running */
    GL_SLEEP_STOP = 1  /**< Stop 2: only LSE domain (tick, RTC, LPTIM1), EXTI wake */
} gl_sleep_mode_t;

/**
 * Sleep until an enabled interrupt source is pending.  Returns immediately
 * if one already is.  Returns the pending mask WITHOUT clearing it (use
 * gl_hal_irq_take()).  In GL_SLEEP_STOP the backend restores the system
 * clock before returning.  The LCD EXTCOMIN output keeps running in both
 * modes (PROVISIONAL for Stop 2: see GL_PROV_LPTIM_PWM_RUNS_IN_STOP2).
 */
uint32_t gl_hal_sleep(gl_sleep_mode_t mode);

/* ======================================================================= */
/* Core clock                                                               */
/* ======================================================================= */

/**
 * DESIGN_SPEC section 4 (rev C2): no high-speed crystal; the MCU runs from
 * its internal oscillators.  During a read the PLL raises the core clock to
 * 160 MHz (the vision needs 58 to 88 million instructions per read, the
 * costliest putt solve found 221 million), otherwise it runs slowly or sleeps
 * in Stop 2.
 */
typedef enum {
    GL_CLOCK_SLOW = 0, /**< the base clock of the backend (STM32: MSIS, no PLL) */
    GL_CLOCK_FAST = 1  /**< 160 MHz from the PLL */
} gl_clock_t;

/**
 * Switch the CORE clock.  Blocks until the switch is complete (PLL locked:
 * of the order of 100 us on the target).  Idempotent; safe at any time after
 * gl_hal_init(), which leaves the clock SLOW.
 *
 * What does NOT change with it (a backend must guarantee this): the tick and
 * gl_hal_time_us(), gl_hal_delay_*, the SPI and SCCB bit rates, XVCLK, the
 * ADC timing, EXTCOMIN, USB.  Drivers never need to know which clock runs.
 *
 * Rules for the caller (the host simulator checks them):
 *  - every switch to GL_CLOCK_FAST is paired with a switch back to
 *    GL_CLOCK_SLOW when the compute-heavy work is done or abandoned;
 *  - GL_SLEEP_STOP is never entered with the fast clock (the PLL does not
 *    survive Stop mode; a backend may treat it as GL_SLEEP_IDLE).
 *
 * Returns GL_ERR_IO if the PLL did not lock: the clock is then still SLOW
 * and everything works, only slower.  Returns GL_ERR_IO also if a switch
 * BACK to GL_CLOCK_SLOW did not take place: the clock is then still FAST
 * (gl_hal_clock_get() says so); the caller must not assume otherwise - it
 * stays out of GL_SLEEP_STOP and tries again.
 */
gl_status_t gl_hal_clock_set(gl_clock_t speed);

/** The clock in effect. */
gl_clock_t gl_hal_clock_get(void);

/* ======================================================================= */
/* SPI                                                                      */
/* ======================================================================= */

typedef enum {
    GL_SPI_BUS_1 = 0, /**< LCD (write only) + NOR flash; SCK PA5/PB3, MOSI, MISO PB4 */
    GL_SPI_BUS_2 = 1, /**< IMU, 4-wire */
    GL_SPI_BUS_COUNT
} gl_spi_bus_t;

typedef struct {
    uint32_t max_hz;  /**< backend picks the fastest prescaler not above this */
    uint8_t mode;     /**< SPI mode 0..3 (CPOL << 1 | CPHA) */
    bool lsb_first;   /**< true: least significant bit of each byte first */
} gl_spi_cfg_t;

/** (Re)configure a bus.  Cheap; drivers that share SPI1 call it before each
 *  transaction burst because the LCD and the flash use different settings. */
gl_status_t gl_hal_spi_configure(gl_spi_bus_t bus, const gl_spi_cfg_t *cfg);

/**
 * Full-duplex transfer of `len` bytes.  `tx` may be NULL (0xFF is clocked
 * out), `rx` may be NULL (input discarded).  Chip select is NOT touched:
 * the driver frames the transaction with gl_hal_gpio_write().
 */
gl_status_t gl_hal_spi_transfer(gl_spi_bus_t bus, const uint8_t *tx, uint8_t *rx,
                                size_t len);

/* ======================================================================= */
/* SCCB (camera control bus, I2C-like)                                      */
/* ======================================================================= */

typedef enum {
    GL_CAM_LEFT = 0,
    GL_CAM_RIGHT = 1,
    GL_CAM_COUNT
} gl_cam_id_t;

/**
 * Both cameras answer at the same 7-bit address, so each has its own clock
 * line and they share the data line.  The backend clocks only the selected
 * camera's SCL.  The pins must already be in GL_PIN_MODE_ALTERNATE (rail on).
 * Write: START, addr<<1, reg, val, STOP.  Read: 2-phase write (addr<<1, reg,
 * STOP) then read (addr<<1|1, data, NACK, STOP), as SCCB requires.
 */
gl_status_t gl_hal_sccb_write(gl_cam_id_t cam, uint8_t addr7, uint8_t reg, uint8_t val);
gl_status_t gl_hal_sccb_read(gl_cam_id_t cam, uint8_t addr7, uint8_t reg, uint8_t *val);

/* ======================================================================= */
/* Camera clock and DCMI strip capture                                      */
/* ======================================================================= */

/** Start XVCLK on the MCO pin (pin must be ALTERNATE).  Returns GL_ERR_RANGE
 *  if the backend cannot produce `hz` within 2 %. */
gl_status_t gl_hal_xvclk_start(uint32_t hz);
void gl_hal_xvclk_stop(void);

typedef struct {
    /** Capture window in units of the sensor's output frame AFTER the
     *  sensor-side windowing: bytes per line to skip / keep and lines to
     *  skip / keep (DCMI crop).  For YUV422 one pixel is two bytes. */
    uint16_t x0_bytes;
    uint16_t width_bytes;   /**< bytes per line passed to the byte-select stage */
    uint16_t y0_lines;
    uint16_t height_lines;
    /** DCMI byte select: keep 1 byte out of `byte_select_every` (1 = all,
     *  2 = every other byte: the Y byte of YUV422). */
    uint8_t byte_select_every;
    /** true: the first kept byte is the 2nd byte of the group (DCMI OEBS). */
    bool byte_select_odd;
    bool vsync_active_high;
    bool href_active_high;
    bool pclk_rising_edge;
    uint32_t timeout_ms;    /**< give up if no complete frame within this time */
} gl_dcmi_cfg_t;

typedef enum {
    GL_DCMI_IDLE = 0,
    GL_DCMI_BUSY,
    GL_DCMI_DONE,
    GL_DCMI_ERROR_TIMEOUT,
    GL_DCMI_ERROR_OVERRUN,
    GL_DCMI_ERROR_SIZE      /**< frame did not match the requested size */
} gl_dcmi_state_t;

/**
 * Arm a snapshot capture of ONE frame into `buf` (DMA).  The expected byte
 * count is (width_bytes / byte_select_every) * height_lines and must be
 * <= buf_len.  Returns immediately; completion raises GL_IRQ_DCMI_DONE.
 * Portable callers keep to what the STM32 backend can do: `buf` aligned to
 * 4 bytes, an expected byte count that is a multiple of 4 and below 65536
 * (one DMA block of 32-bit words); otherwise GL_ERR_PARAM on that backend.
 */
gl_status_t gl_hal_dcmi_start(const gl_dcmi_cfg_t *cfg, uint8_t *buf, size_t buf_len);

/** Capture state; `bytes` (may be NULL) receives the bytes stored so far. */
gl_dcmi_state_t gl_hal_dcmi_poll(size_t *bytes);

/**
 * gl_hal_time_us() value latched AT THE END OF THE FRAME of the most recent
 * capture that reached GL_DCMI_DONE (in the frame interrupt, not when the
 * application gets round to polling: the read sequence times the L R R L
 * strips with it, and the main loop may be busy for longer than a frame).
 * Valid from GL_DCMI_DONE until the next gl_hal_dcmi_start().
 */
uint32_t gl_hal_dcmi_done_us(void);

/** Abort a capture and return the peripheral to idle. */
void gl_hal_dcmi_stop(void);

/* ======================================================================= */
/* ADC and op-amp                                                           */
/* ======================================================================= */

typedef enum {
    GL_ADC_CH_GRAIN_TIA = 0, /**< OPAMP1 output (photodiode transimpedance stage) */
    GL_ADC_CH_VBAT_DIV,      /**< battery through the 2 x 1 Mohm divider (100 nF) */
    GL_ADC_CH_VREFINT,       /**< internal reference, for VDDA measurement */
    GL_ADC_CH_MCU_TEMP,      /**< MCU die temperature sensor */
    GL_ADC_CH_CELL_NTC,      /**< NTC_SENSE: mid point of the cell-temperature divider.
                                  Ratiometric (the divider is fed from a GPIO at VDDA):
                                  counts / full scale = R_ntc / (R_ntc + 10.0 kohm).  Reads
                                  near zero unless GL_PIN_NTC_BIAS is driven high */
    GL_ADC_CH_COUNT
} gl_adc_ch_t;

/** Full scale of gl_hal_adc_read() results: 14 bits. */
#define GL_HAL_ADC_FULL_SCALE 16383u

/** Power the ADC up (and run its calibration) or down. */
gl_status_t gl_hal_adc_power(bool on);

/**
 * One blocking conversion result: the mean of `n_avg` consecutive samples
 * (1..256), right-aligned 14-bit.  `sample_time_us` is the minimum sampling
 * time per sample (the VBAT divider needs a long one: 2 Mohm source with a
 * 100 nF reservoir).
 */
gl_status_t gl_hal_adc_read(gl_adc_ch_t ch, uint16_t n_avg, uint16_t sample_time_us,
                            uint16_t *counts);

/** VDDA in millivolts computed from VREFINT and the factory calibration. */
uint16_t gl_hal_adc_vdda_mv(void);

/**
 * MCU die temperature in degrees C for a GL_ADC_CH_MCU_TEMP reading taken at
 * the given VDDA, from the factory calibration points of the part.  Used as
 * an INDEPENDENT second opinion for the charge-temperature gate (the IMU's
 * temperature sensor is the first); accuracy a few kelvin.
 */
float gl_hal_adc_mcu_temp_c(uint16_t counts, uint16_t vdda_mv);

/** Enable OPAMP1 in standalone mode (external 470 kohm || 10 pF feedback,
 *  non-inverting input on the external mid-rail divider), or power it down. */
gl_status_t gl_hal_opamp_enable(bool on);

/* ======================================================================= */
/* LCD VCOM timer (LPTIM1)                                                  */
/* ======================================================================= */

/**
 * Start a 50 % duty square wave on GL_PIN_LCD_EXTCOMIN with a period of
 * `period_lse_ticks` cycles of the 32.768 kHz clock (547 -> 59.905 Hz).  The
 * pin must be in GL_PIN_MODE_ALTERNATE.  The output keeps running in Stop.
 */
gl_status_t gl_hal_extcomin_start(uint16_t period_lse_ticks);
void gl_hal_extcomin_stop(void);

/* ======================================================================= */
/* USB CDC-ACM device                                                       */
/* ======================================================================= */

/** Enable the USB device (sets the USB-supply-valid bit; only call while
 *  VBUS is present) / disable it and power the transceiver down.  The
 *  application stops USB as soon as it sees VBUS gone, whatever its UI is
 *  doing; the host backend counts USB left started without VBUS as a
 *  violation. */
gl_status_t gl_hal_usb_start(void);
void gl_hal_usb_stop(void);

/** True once the host has configured the device and opened the port (DTR). */
bool gl_hal_usb_connected(void);

/** Non-blocking read of up to `max` received bytes.  Returns the count. */
size_t gl_hal_usb_read(uint8_t *buf, size_t max);

/** Queue up to `len` bytes for transmission.  Returns the count accepted
 *  (may be less than `len` when the transmit buffer is full). */
size_t gl_hal_usb_write(const uint8_t *buf, size_t len);

/* ======================================================================= */
/* Trace points (timing instrumentation)                                    */
/* ======================================================================= */

typedef enum {
    GL_TRACE_VISION_BAND = 0,  /**< a horizon band has just been analysed.
                                    work = pixels of the band */
    GL_TRACE_VISION_STRIP,     /**< one flagstick strip has just been analysed.
                                    work = GL_TRACE_STRIP_* bits: what was tried */
    GL_TRACE_VISION_GROUP,     /**< one L R R L group has just been combined.  work = 0 */
    GL_TRACE_SOLVE,            /**< one putt estimate has just been computed.
                                    work = RK4 steps of its trial rolls
                                    (gl_estimate_t.n_steps; 0 if it was refused) */
    GL_TRACE_RENDER,           /**< a screen has just been drawn into the framebuffer (the
                                    transfer to the panel is bus time, not this).  work = 0 */
    GL_TRACE_COUNT
} gl_trace_point_t;

/** `work` of GL_TRACE_VISION_STRIP: the refinements made on the strip, each
 *  with 1, 4 or 16 rows averaged along the line (app/gl_read.c tries them in
 *  that order until one finds the line), whether the last one found it, how
 *  wide the line is, and whether the strip's statistics were computed as
 *  well. */
#define GL_TRACE_STRIP_TRIED_1  (1u << 0)
#define GL_TRACE_STRIP_TRIED_4  (1u << 1)
#define GL_TRACE_STRIP_TRIED_16 (1u << 2)
#define GL_TRACE_STRIP_FOUND    (1u << 3)
#define GL_TRACE_STRIP_STATS    (1u << 4)
#define GL_TRACE_STRIP_WIDE     (1u << 5) /**< the line found is wider than the narrowest window
                                               (a stick within about 4 m): its two passes share
                                               no work */

/**
 * Mark the END of a piece of heavy computation and say how much of it there
 * was: `work` in the unit given with each trace point.  On the target this
 * is for measuring run times on the bench (a test pad or an ITM channel; it
 * may do nothing): the pair (point, work) and the time since the previous
 * mark are what calibrates the simulator's compute-time model.  The host
 * simulator, in which computation otherwise takes no simulated time, CHARGES
 * the stage's run time here: by default from its table of instruction counts
 * (hal/host/gl_sim_cost.h), a cycles-per-instruction factor and the core
 * clock in effect; a test can set a fixed time per point instead
 * (gl_sim_set_compute_us).  Must be cheap and callable from the main loop
 * only.
 */
void gl_hal_trace(gl_trace_point_t point, uint32_t work);

#ifdef __cplusplus
}
#endif
#endif /* GL_HAL_H */
