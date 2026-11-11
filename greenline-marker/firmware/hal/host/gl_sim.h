/*
 * gl_sim.h - control and inspection interface of the HOST SIMULATOR backend
 * of hal/gl_hal.h.  Host tests only; nothing here exists on the target.
 *
 * The simulator is a model of the GL-1 board as seen from the MCU pins:
 *
 *   time        simulated microseconds.  Time passes ONLY in gl_hal_delay_*,
 *               in gl_hal_sleep and for the duration of bus transfers and ADC
 *               conversions.  Computation takes zero simulated time.
 *   GPIO        mode and output latch of every logical pin, external levels
 *               for inputs, every change recorded in the trace
 *   SPI1        LS013B7DH03 model (decodes frames into a panel memory) and
 *               MX25R6435F model (8 MB of RAM, NOR semantics, busy times)
 *   SPI2        LSM6DSV16X model (register map, sample generator, wake-up
 *               and data-ready interrupts)
 *   SCCB+DCMI   two OVM7692 models on the shared bus; frames come from a
 *               scene callback supplied by the test
 *   ADC/OPAMP   battery divider and the grain photodiode stage, driven by
 *               the charlieplex pin states
 *   USB         byte pipes to an imaginary host
 *
 * It CHECKS, and counts in gl_sim_violations_t:
 *   - the camera rail rule (every camera-facing pin ANALOG or driven low
 *     while V2V8_CAM is off, and for 1 ms after it is switched on)
 *   - two cameras driving the shared bus at once
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
    GL_SIM_TR_IRQ_ENABLE      /**< a = enable, c = mask */
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
/** Set the level an external circuit puts on an input pin (IMU interrupts
 *  are driven by the IMU model; use this for CHG_STAT and VBUS_SENSE). */
void gl_sim_set_input(gl_pin_t pin, bool level);

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
    uint32_t frames_captured;  /**< completed DCMI captures */
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
    bool deep_power_down;
} gl_sim_flash_stats_t;

const gl_sim_flash_stats_t *gl_sim_flash_stats(void);
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

/** The imaginary host opens / closes the CDC port. */
void gl_sim_usb_host_open(bool open);
/** Host -> device bytes (dropped if the device has not started USB). */
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
