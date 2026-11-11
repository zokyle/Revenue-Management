/*
 * grain_frontend.h - photometric grain sensor front end (EXPERIMENTAL;
 * the grain function ships disabled).
 *
 * Hardware: 8 red and 8 near-infrared LEDs charlieplexed on 5 MCU pins
 * (one 68 ohm resistor per pin), one photodiode into OPAMP1 as a
 * transimpedance stage (470 kohm || 10 pF, non-inverting input at
 * mid-rail), OPAMP1 output on a 14-bit ADC channel.
 *
 * LED numbering (same as core/gl_grain.h): 0..7 red, 8..15 near-infrared;
 * LED k and LED 8 + k form the antiparallel pair at azimuth 22.5 + 45 k
 * degrees.
 *
 * CHARLIEPLEX WIRING - PROPOSED, no netlist exists (GL_PROV_GRAIN_*): pair
 * k sits between the two pins gl_grain_fe_pair[k]; the red LED conducts
 * from the LOWER-numbered pin to the higher one, the NIR LED the other
 * way.  Lighting LED n means: anode pin push-pull HIGH, cathode pin
 * push-pull LOW, the other three pins ANALOG (high impedance).  All five
 * pins ANALOG = everything off.  The orientation rule makes the red
 * direction acyclic over the pins, so every sneak path (two LEDs in series
 * through a floating pin) that exists while a red LED is lit contains at
 * least one other red LED and cannot conduct at the red forward voltage.
 *
 * NOTE for the hardware review: with the 2.8 V rail and 2 x 68 ohm in the
 * path the LED current is about (2.8 - 2.0) / 136 = 6 mA for red and about
 * 10 mA for NIR, not the 20 mA assumed in docs/research/grain-sensing.md.
 *
 * Measurement (grain-sensing.md section 2.2): per LED dark / on / dark, the
 * whole LED scan repeated for several interleaved cycles; the scan order
 * alternates red / NIR and reverses on odd cycles so that a slow drift
 * averages out across cycles instead of mapping onto the azimuth.  The raw
 * triples go to core/gl_grain (drift rejection, harmonics, validity).  The
 * caller supplies the motion verdict from the IMU.
 *
 * Time: one cycle = 16 LEDs x 3 readings x (settle 0.5 ms + 16 ADC samples)
 * = about 30 ms.  Stack: under 64 bytes.  No static RAM.
 */
#ifndef GL_GRAIN_FRONTEND_H
#define GL_GRAIN_FRONTEND_H

#include "gl_grain.h"
#include "gl_types.h"

#define GL_GRAIN_FE_PINS 5u
#define GL_GRAIN_FE_PAIRS 8u

/** Charlieplex pin numbers (0..4) of each LED pair: [k][0] < [k][1]. */
extern const uint8_t gl_grain_fe_pair[GL_GRAIN_FE_PAIRS][2];

/** Anode and cathode charlieplex pin (0..4) of LED 0..15. */
void gl_grain_fe_led_pins(unsigned led, uint8_t *anode, uint8_t *cathode);

/** All five pins ANALOG: every LED off. */
void gl_grain_fe_all_off(void);

/** Light exactly one LED (0..15); any other value turns everything off. */
void gl_grain_fe_led_on(int led);

/** Power the analog chain (ADC + OPAMP1) up, with its settling time, or
 *  down (LEDs off first). */
gl_status_t gl_grain_fe_power(bool on);

/**
 * Measure one cycle (all 16 LEDs, dark / on / dark each) into
 * raw->s[cycle][].  The analog chain must be powered.  The LEDs are off on
 * return, also on an error.  `cycle` < GL_GRAIN_MAX_CYCLES.
 */
gl_status_t gl_grain_fe_measure_cycle(gl_grain_raw_t *raw, unsigned cycle);

/**
 * Convenience: power up, measure `cycles` cycles (1..GL_GRAIN_MAX_CYCLES),
 * power down, and fill raw->cycles and raw->adc_full_scale.  raw->motion is
 * set to false: the caller ORs in what the IMU saw.
 */
gl_status_t gl_grain_fe_measure(gl_grain_raw_t *raw, unsigned cycles);

#endif /* GL_GRAIN_FRONTEND_H */
