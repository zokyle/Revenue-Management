/*
 * gl_grain.h - photometric grain sensor processing (EXPERIMENTAL).
 *
 * Hardware: 8 red and 8 near-infrared LEDs on a ring under the puck, one
 * photodiode at the centre into a transimpedance stage and the ADC.  The
 * driver (drivers/grain_frontend) measures, per LED and per cycle, the
 * triple dark / on / dark and hands the raw counts to this module.
 *
 * Processing (docs/research/grain-sensing.md section 2.2):
 *   signal  = on - (dark1 + dark2) / 2, a cycle is dropped when the two
 *             darks differ by more than the calibrated limit, cycles are
 *             averaged, each LED is divided by its white-tile gain
 *   output  = first-harmonic vector of the 8 azimuth samples of each
 *             colour, modulation depth, and a validity flag
 *   VALID   only if: no motion, no saturation, enough signal, white
 *             reference present, and modulation >= the threshold stored in
 *             the CALIBRATION RECORD (set from the measured no-grain noise
 *             floor).  There is no fixed threshold in this code.
 *
 * LED geometry: LED k (0..7) of each colour sits at azimuth
 * GL_GRAIN_LED0_AZIMUTH_DEG + 45 k degrees, measured counter-clockwise
 * from marker +x seen from above (the angle atan2(y, x) of the LED position
 * about the ring centre).  Indices 0..7 are red, 8..15 near-infrared.
 * Both numbers and the "counter-clockwise from +x seen from above"
 * convention come from design/master_params.yaml (rev C states them at
 * bottom_side_parts.grain_led_ring); the PCB layout must follow the YAML.
 *
 * Results are reported in the firmware's usual convention: radians,
 * counter-clockwise from marker FORWARD (+y).
 *
 * Grain ships DISABLED (settings.grain_enable = 0): gl_grain_estimate()
 * then returns zero strength whatever the sensor says.
 *
 * RAM: gl_grain_raw_t 388 bytes, gl_grain_reading_t 156 bytes.  Stack: under 300 bytes.
 */
#ifndef GL_GRAIN_H
#define GL_GRAIN_H

#include "gl_cal.h"
#include "gl_config.h"
#include "gl_settings.h"
#include "gl_types.h"

#define GL_GRAIN_LEDS_PER_COLOUR 8u
#define GL_GRAIN_MAX_CYCLES 4u
#define GL_GRAIN_LED0_AZIMUTH_DEG GL_CFG_GRAIN_LED0_AZIMUTH_DEG
#define GL_GRAIN_LED_STEP_DEG GL_CFG_GRAIN_LED_STEP_DEG

/** Azimuth of LED index 0..15 in the firmware convention (rad, CCW from
 *  marker forward), wrapped to (-pi, pi]. */
float gl_grain_led_azimuth_rad(unsigned led);

/** Position of LED index 0..15 relative to the ring centre, marker axes, mm. */
gl_vec2_t gl_grain_led_position_mm(unsigned led);

typedef struct {
    uint16_t dark1, on, dark2; /**< ADC counts */
} gl_grain_sample_t;

typedef struct {
    gl_grain_sample_t s[GL_GRAIN_MAX_CYCLES][GL_GRAIN_LEDS];
    uint8_t cycles;            /**< 1..GL_GRAIN_MAX_CYCLES complete cycles */
    bool motion;               /**< the IMU saw motion during the measurement */
    uint16_t adc_full_scale;   /**< counts; readings within 2 % of it are saturated */
} gl_grain_raw_t;

/** Reasons a reading is not valid (bit mask). */
#define GL_GRAIN_REJECT_MOTION        (1u << 0)
#define GL_GRAIN_REJECT_DARK_DRIFT    (1u << 1) /**< an LED had no cycle with stable darks */
#define GL_GRAIN_REJECT_SATURATED     (1u << 2)
#define GL_GRAIN_REJECT_LOW_SIGNAL    (1u << 3)
#define GL_GRAIN_REJECT_NO_WHITE_REF  (1u << 4) /**< gain calibration missing */
#define GL_GRAIN_REJECT_BELOW_FLOOR   (1u << 5) /**< modulation under the calibrated threshold */
#define GL_GRAIN_REJECT_BAD_INPUT     (1u << 6)

typedef struct {
    float mean;         /**< mean gain-corrected signal, counts */
    float cos1, sin1;   /**< first harmonic about the +x axis, counts */
    float modulation;   /**< first-harmonic amplitude / mean */
    float azimuth_rad;  /**< direction of the brightest illumination, CCW from forward */
    float second;       /**< second-harmonic amplitude / mean (tilt / specular diagnostic) */
} gl_grain_harmonic_t;

typedef struct {
    gl_grain_harmonic_t red;
    gl_grain_harmonic_t nir;
    gl_grain_harmonic_t ratio;  /**< harmonic of red_k / nir_k (geometry largely cancels) */
    float signal[GL_GRAIN_LEDS];/**< per-LED gain-corrected signal, counts */
    uint8_t cycles_used[GL_GRAIN_LEDS];
    uint8_t reject;             /**< GL_GRAIN_REJECT_* bits, 0 = valid */
    bool valid;
} gl_grain_reading_t;

/**
 * Process one raw measurement.  Always fills `out` as far as the data
 * allow; out->valid says whether it may be used.  Returns GL_OK when valid,
 * GL_ERR_QUALITY when rejected (see out->reject), GL_ERR_PARAM for NULL or
 * zero cycles.  The validity threshold is cal->mod_threshold, applied to
 * the red channel.
 */
gl_status_t gl_grain_process(const gl_grain_raw_t *raw, const gl_cal_grain_t *cal,
                             gl_grain_reading_t *out);

/**
 * White-tile gain calibration: sets cal->gain[] so that a uniform white
 * target reads the same on every LED of a colour, and sets the WHITE_REF
 * flag.  GL_ERR_QUALITY if the measurement itself is unusable (motion,
 * drift, saturation, low signal).
 */
gl_status_t gl_grain_white_reference(const gl_grain_raw_t *raw, gl_cal_grain_t *cal);

/**
 * Noise-floor gate ("gate 0"): from n >= 20 red-channel modulation depths
 * measured on turf with no deliberate lean, store the median as the noise
 * floor and the 95th percentile as the acceptance threshold, and set the
 * NOISE_FLOOR flag.  `scratch` must hold n floats (the input is not
 * modified).  GL_ERR_PARAM if n < 20.
 */
gl_status_t gl_grain_noise_floor(const float *modulation, unsigned n, float *scratch,
                                 gl_cal_grain_t *cal);

/* ---- running vector average over one green --------------------------------- */

typedef struct {
    float sum_x, sum_y;   /**< sum of modulation-weighted unit vectors */
    float sum_mod;        /**< sum of modulation depths */
    uint16_t n;
} gl_grain_avg_t;

/** Start a new average (new green / new putt). */
void gl_grain_avg_reset(gl_grain_avg_t *a);

/** Add a valid reading.  `azimuth_ref_rad` is the reading's azimuth
 *  expressed relative to a reference that is common to all readings of the
 *  average (the device does not know its compass heading; the application
 *  uses the line of sight to the flagstick of the current putt). */
void gl_grain_avg_add(gl_grain_avg_t *a, float modulation, float azimuth_ref_rad);

/** Mean vector: *modulation = |sum| / n (shrinks when readings disagree),
 *  *azimuth_ref_rad its direction.  Returns the number of readings. */
unsigned gl_grain_avg_result(const gl_grain_avg_t *a, float *modulation, float *azimuth_ref_rad);

/* ---- what the putt solver receives ------------------------------------------ */

typedef enum {
    GL_GRAIN_SRC_NONE = 0,   /**< disabled or nothing known: no correction */
    GL_GRAIN_SRC_PRIOR = 1,  /**< down the fall line, strength from the grass type */
    GL_GRAIN_SRC_OPTICAL = 2 /**< direction from the sensor, strength from the grass type */
} gl_grain_source_t;

typedef struct {
    float kappa_long;    /**< along-grain strength: push = kappa * rolling deceleration */
    float kappa_lat;     /**< strength used for the sideways (aim) correction */
    float azimuth_rad;   /**< direction the grain pushes the ball, CCW from marker forward */
    uint8_t source;      /**< gl_grain_source_t */
} gl_grain_est_t;

/** Fraction of kappa_long used for the sideways correction until k_lat has
 *  been measured ("bound it between 0 and k_long"): the midpoint. */
#define GL_GRAIN_KLAT_FRACTION 0.5f

/** Slopes flatter than this give no fall-line prior (direction undefined). */
#define GL_GRAIN_MIN_PRIOR_SLOPE 0.003f

/** An optical reading is used only if its averaged modulation is at least
 *  this many times the calibrated threshold ("well above the noise floor"). */
#define GL_GRAIN_OPTICAL_MARGIN 1.5f

/**
 * Grain estimate for the solver.
 *   settings->grain_enable == 0  -> SRC_NONE, zero strength.
 *   otherwise: prior = down the fall line of `slope_marker`, strength from
 *   settings->grass (GL_PROV_GRAIN_KAPPA_*).  If `optical_n` > 0, the
 *   calibration has both flags set and optical_modulation >=
 *   GL_GRAIN_OPTICAL_MARGIN * cal->mod_threshold, the DIRECTION is taken
 *   from the sensor (optical_azimuth_rad, marker frame, times
 *   GL_PROV_GRAIN_HARMONIC_SIGN) instead of the fall line.
 * Both strengths are capped so that the equivalent slope
 * kappa * a_r / ((5/7) g) does not exceed GL_PROV_GRAIN_MAX_EQUIV_SLOPE.
 */
void gl_grain_estimate(const gl_settings_t *settings, const gl_cal_grain_t *cal,
                       gl_vec2_t slope_marker, unsigned optical_n, float optical_modulation,
                       float optical_azimuth_rad, gl_grain_est_t *out);

#endif /* GL_GRAIN_H */
