/*
 * ov7692.h - the two OmniVision OVM7692 VGA camera cubes.
 *
 * BOARD (DESIGN_SPEC rev C, section 4)
 *   - both cubes share the 8 data lines, PIXCLK, HREF and VSYNC into the
 *     MCU's DCMI; only one may drive them at a time
 *   - each has its own SCCB clock and its own PWDN; SCCB data is shared;
 *     both answer at address 0x3C
 *   - XVCLK 12 MHz from the MCU's MCO pin
 *   - the 2.8 V camera rail is switched by the MCU and is OFF outside a read
 *
 * THE RAIL RULE, enforced by gl_ov7692_power_up() / gl_ov7692_power_down():
 * every MCU pin facing the cameras is driven low or analog while the rail
 * is off.
 *
 *   power-up     1 rail enable high, wait GL_PROV_CAM_RAIL_SETTLE_MS
 *                2 both PWDN asserted (now that the rail can take it)
 *                3 XVCLK pin to the clock output, clock started
 *                4 SCCB and DCMI pins to their peripherals, wait
 *                  GL_PROV_CAM_CLOCK_SETTLE_MS
 *                5 for LEFT then RIGHT: release PWDN, release the bus
 *                  (register 0x0C) as the FIRST register write, software
 *                  reset, wait for it, release the bus AGAIN at once (the
 *                  reset re-enables the pads), check the product id, power
 *                  the MIPI block down, select YUV422, put the camera to
 *                  sleep (register 0x0E)
 *                  -> both cameras configured, asleep, bus released
 *   power-down   1 stop any capture, stop the clock
 *                2 every camera-facing pin to ANALOG or driven low
 *                3 rail enable low
 *   Any error during power-up runs the power-down sequence before
 *   returning.
 *
 * SHARED BUS.  gl_ov7692_select() makes one camera drive the bus: the other
 * one is released FIRST (break before make).  The idle camera's outputs are
 * tri-stated with register 0x0C bits 2 and 1 (bit polarity PROVISIONAL:
 * GL_PROV_OV7692_REG0C_BIT_SET_MEANS_DRIVEN; both bits always change
 * together) and it is put to sleep with register 0x0E bit 3 when asked to.
 * Once both cameras are configured, PWDN is never relied on to free the bus.
 *
 * WHAT POWER-UP CANNOT AVOID.  Both sensors leave their power-on reset with
 * 0x0C = 0x16: pads ENABLED.  They can be told otherwise only over SCCB,
 * one at a time, after PWDN release and the clock settle time.  Until then
 * the bring-up of the first camera RELIES ON PWDN holding the second one's
 * pads off - which is not confirmed for this part
 * (GL_PROV_OV7692_PWDN_TRISTATES_OUTPUTS = 0).  If PWDN does not tri-state
 * the pads, both sensors have their pads enabled for about 12 ms per rail
 * cycle (5 ms of it while the rail settles, unclocked and static), and for
 * about 6 ms one of them is streaming against the other's static levels.
 * The driver keeps that window as short as the sequence allows (0x0C is the
 * first write after PWDN release and the first after the reset); it cannot
 * close it.  The camera model measures it and tests/test_drv_cam.c asserts
 * the figure; closing it needs the datasheet or a board change (see the
 * constant's comment in core/gl_provisional.h and the README).
 *
 * STRIPS.  The cameras deliver YUV422; the DCMI byte-select keeps only the
 * Y byte, so a strip is 8-bit luminance, one byte per pixel.  A strip is a
 * window of the sensor: a horizon band (640 x 96) or a flagstick strip
 * (96 x 480).  The window is applied on the sensor (default) or by the DCMI
 * crop (GL_PROV_OV7692_SENSOR_WINDOWING; see core/gl_provisional.h for how
 * uncertain the sensor-side register meanings are).  In the DCMI-crop mode
 * the driver programs the full 640 x 480 input and output size at power-up
 * and touches no start / size register.  Window origin and size
 * are rounded to the sensor's window granularity (4 columns, 2 rows); the
 * strip descriptor returned by a capture carries the ACTUAL origin.
 *
 * REGISTERS.  Register addresses and the bit masks named in ov7692.c were
 * taken from the public Apache-2.0 Analog Devices msdk driver
 * (Libraries/MiscDrivers/Camera/ov7692_regs.h and ov7692.c, read for this
 * purpose; no code was copied).  The driver writes only registers whose
 * address and purpose appear there, and does NOT write clock-tree, exposure
 * or image-processing registers, for which this project has no verified
 * values: those stay at the sensor's reset defaults.  In register 0x0C it
 * owns bits 7, 6, 2 and 1 only; the others are written with their reset
 * values (GL_PROV_OV7692_REG0C_KEEP_BITS: bit 4, YU/YV swap, stays set as
 * it is after reset and in the public driver's 0xD6).
 *
 * RAM: sizeof(gl_ov7692_t) about 72 bytes.  Stack: under 96 bytes.
 * Blocking times: power-up about 2 x 15 ms of register traffic plus the
 * settle delays; a capture is started and then polled (no blocking wait)
 * except for the settle time after a wake-up or a window change.
 */
#ifndef GL_OV7692_H
#define GL_OV7692_H

#include "gl_hal.h"
#include "gl_types.h"
#include "gl_vision.h"

#define GL_OV7692_SCCB_ADDR 0x3Cu
#define GL_OV7692_SENSOR_W 640u
#define GL_OV7692_SENSOR_H 480u

typedef struct {
    bool sensor_windowing;    /**< true: window on the sensor; false: DCMI crop of full VGA */
    bool sleep_idle_on_switch;/**< true: gl_ov7692_select() always sleeps the idle camera */
    bool vflip, hmirror;      /**< flip bits that make the delivered image upright */
    bool enforce_pid;         /**< refuse a camera whose product id is not GL_PROV_OV7692_PID */
    uint32_t xvclk_hz;
    uint16_t frame_period_ms;
    uint8_t settle_frames;    /**< frames to let pass after a camera starts streaming */
} gl_ov7692_cfg_t;

typedef struct {
    uint16_t x0, y0, w, h;    /**< window (sensor pixels); w == 0: none set */
    bool awake;               /**< not in software sleep */
    bool driving;             /**< outputs enabled on the shared bus */
    uint32_t ready_at_ms;     /**< tick from which a frame may be trusted */
    uint16_t pid;             /**< product id read at power-up */
} gl_ov7692_cam_t;

typedef enum {
    GL_OV_OTHER_SLEEP = 0, /**< put the other camera to sleep (it is idle for a while) */
    GL_OV_OTHER_AWAKE = 1  /**< keep / make the other camera awake but released (L R R L sequence) */
} gl_ov7692_other_t;

typedef struct {
    gl_ov7692_cfg_t cfg;
    gl_ov7692_cam_t cam[GL_CAM_COUNT];
    bool powered;
    bool capturing;
    int8_t active;                 /**< camera driving the bus, -1 = none */
    uint16_t cap_w, cap_h;         /**< size of the capture in progress */
    uint32_t cap_deadline_ms;
    uint32_t last_done_ms;         /**< tick at which the last capture was SEEN complete */
    uint32_t last_done_us;         /**< gl_hal_time_us() at the END OF THE FRAME of the last
                                        completed capture (latched by the HAL in the frame
                                        interrupt): the exposure timing of a strip */
    uint32_t frames;               /**< captures completed since power-up */
} gl_ov7692_t;

/** Configuration from core/gl_provisional.h. */
void gl_ov7692_cfg_defaults(gl_ov7692_cfg_t *cfg);

/** Reset the driver state and run the power-down sequence (pins parked,
 *  rail off) whatever the previous state was.  `cfg` NULL = defaults. */
void gl_ov7692_init(gl_ov7692_t *d, const gl_ov7692_cfg_t *cfg);

/** Power-up sequence (see above).  GL_ERR_IO if a camera does not answer,
 *  GL_ERR_NOT_FOUND for a wrong product id, GL_ERR_TIMEOUT if the software
 *  reset does not complete; in every error case the rail is off again. */
gl_status_t gl_ov7692_power_up(gl_ov7692_t *d);

/** Power-down sequence.  Always safe to call. */
void gl_ov7692_power_down(gl_ov7692_t *d);

/** Make `cam` drive the shared bus (wakes it if needed) after releasing the
 *  other camera. */
gl_status_t gl_ov7692_select(gl_ov7692_t *d, gl_cam_id_t cam, gl_ov7692_other_t other);

/** Release both cameras from the bus (neither drives it). */
gl_status_t gl_ov7692_release_all(gl_ov7692_t *d);

/**
 * Set the strip window of one camera.  x0 is rounded down to a multiple of
 * 4 and y0 to a multiple of 2; w must be a multiple of 4 and h of 2, and
 * the window must lie inside the 640 x 480 sensor (it is shifted inward if
 * it does not).  GL_ERR_PARAM for an impossible size.
 */
gl_status_t gl_ov7692_set_window(gl_ov7692_t *d, gl_cam_id_t cam, uint16_t x0, uint16_t y0,
                                 uint16_t w, uint16_t h);

/**
 * Arm the capture of one strip from the selected camera into `buf`
 * (>= w * h bytes of its window).  Waits out the camera's settle time
 * first if it has just been woken or re-windowed.  `strip` (may be NULL) is
 * filled with the descriptor of the strip that WILL be in `buf` once the
 * capture completes.  GL_ERR_STATE if `cam` is not the selected camera or
 * has no window.
 */
gl_status_t gl_ov7692_capture_start(gl_ov7692_t *d, gl_cam_id_t cam, uint8_t *buf, size_t buf_len,
                                    gl_strip_t *strip);

/** GL_ERR_BUSY while the capture runs, GL_OK when the strip is complete,
 *  GL_ERR_TIMEOUT / GL_ERR_IO if it failed (the capture is then stopped). */
gl_status_t gl_ov7692_capture_poll(gl_ov7692_t *d);

/** Stop a running capture. */
void gl_ov7692_capture_abort(gl_ov7692_t *d);

/** capture_start + poll every millisecond until done.  For calibration and
 *  tests; the read sequence uses start / poll from the main loop. */
gl_status_t gl_ov7692_capture_blocking(gl_ov7692_t *d, gl_cam_id_t cam, uint8_t *buf,
                                       size_t buf_len, gl_strip_t *strip);

#endif /* GL_OV7692_H */
