/*
 * gl_sim_internal.h - shared between the files of the host simulator.
 * Not for tests (they use gl_sim.h).
 */
#ifndef GL_SIM_INTERNAL_H
#define GL_SIM_INTERNAL_H

#include "gl_sim.h"

#define SIM_NEVER UINT64_MAX

/* ---- services of gl_sim_core.c ------------------------------------------------- */

uint64_t sim_now(void);
void sim_trace(gl_sim_tr_type_t type, unsigned a, unsigned b, uint32_t c, uint32_t d);
/** Count a violation and remember the first description. */
void sim_violation(unsigned *counter, const char *fmt, ...)
#if defined(__GNUC__)
    __attribute__((format(printf, 2, 3)))
#endif
    ;
gl_sim_violations_t *sim_viol(void);
gl_sim_stats_t *sim_stat(void);
/** Latch interrupt sources (only the enabled ones are kept). */
void sim_irq_raise(uint32_t mask);
/** Drive an input pin from a device model (raises the pin's interrupt on a
 *  rising edge for the IMU lines, on any edge for VBUS / STAT). */
void sim_set_input(gl_pin_t pin, bool level);
bool sim_pin_out_high(gl_pin_t pin);
bool sim_pin_out_low(gl_pin_t pin);
bool sim_pin_is_alt(gl_pin_t pin);
/** Deterministic pseudo-random numbers (reseeded by gl_sim_reset). */
uint32_t sim_rand_u32(void);
float sim_rand_normal(void);
/** Hash-based normal deviate for sample `index` of stream `stream`: the
 *  same every time it is asked for. */
float sim_hash_normal(uint32_t stream, uint64_t index);

/* ---- LCD model (gl_sim_lcd.c) --------------------------------------------------- */

void sim_lcd_reset(void);
void sim_lcd_cs(bool asserted);
void sim_lcd_xfer(const gl_spi_cfg_t *cfg, const uint8_t *tx, uint8_t *rx, size_t len);
void sim_lcd_disp(bool high);
void sim_lcd_extcomin(bool running, uint16_t period_ticks);

/* ---- flash model (gl_sim_flash.c) ------------------------------------------------ */

void sim_flash_reset(bool erase);
void sim_flash_cs(bool asserted);
void sim_flash_xfer(const gl_spi_cfg_t *cfg, const uint8_t *tx, uint8_t *rx, size_t len);
/** Supply current of the flash right now, microamperes. */
double sim_flash_supply_ua(void);

/* ---- IMU model (gl_sim_imu.c) ----------------------------------------------------- */

void sim_imu_reset(void);
void sim_imu_cs(bool asserted);
void sim_imu_xfer(const gl_spi_cfg_t *cfg, const uint8_t *tx, uint8_t *rx, size_t len);
/** Absolute time of the next sample instant that can raise an interrupt,
 *  or SIM_NEVER. */
uint64_t sim_imu_next_event(void);
/** Process the sample instant at time t (== sim_imu_next_event()). */
void sim_imu_fire(uint64_t t);
/** Die temperature of the IMU model, degrees C. */
float sim_imu_temperature(void);
/** Supply current of the IMU in its present mode, microamperes. */
double sim_imu_supply_ua(void);

/* ---- camera models (gl_sim_cam.c) -------------------------------------------------- */

void sim_cam_reset(void);
/** A camera-related pin or the clock changed: re-evaluate power, PWDN,
 *  streaming and bus contention. */
void sim_cam_update(void);
void sim_cam_xvclk(bool running, uint32_t hz);
uint64_t sim_cam_next_event(void);
void sim_cam_fire(uint64_t t);
/** True while a DCMI capture is armed. */
bool sim_cam_capture_busy(void);

#endif /* GL_SIM_INTERNAL_H */
