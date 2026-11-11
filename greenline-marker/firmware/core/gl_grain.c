/* gl_grain.c - see gl_grain.h. */
#include "gl_grain.h"

#include <math.h>
#include <string.h>

#include "gl_config.h"
#include "gl_provisional.h"
#include "gl_tilt.h"

#define GRAVITY_MPS2 9.80665f

/* Azimuth of LED k about +x (rad). */
static float led_az_x_(unsigned led)
{
    unsigned k = led % GL_GRAIN_LEDS_PER_COLOUR;
    return (GL_GRAIN_LED0_AZIMUTH_DEG + GL_GRAIN_LED_STEP_DEG * (float)k) * GL_DEG2RAD_F;
}

float gl_grain_led_azimuth_rad(unsigned led)
{
    /* from "CCW from +x" to "CCW from +y (forward)": subtract 90 degrees */
    return gl_wrap_pi(led_az_x_(led) - 0.5f * GL_PI_F);
}

gl_vec2_t gl_grain_led_position_mm(unsigned led)
{
    gl_vec2_t p;
    float a = led_az_x_(led);
    p.x = GL_CFG_GRAIN_RING_RADIUS_MM * cosf(a);
    p.y = GL_CFG_GRAIN_RING_RADIUS_MM * sinf(a);
    return p;
}

/* Harmonics of 8 samples taken at the LED azimuths. */
static void harmonic_(const float r[GL_GRAIN_LEDS_PER_COLOUR], gl_grain_harmonic_t *h)
{
    float sum = 0.0f, c1 = 0.0f, s1 = 0.0f, c2 = 0.0f, s2 = 0.0f;
    for (unsigned k = 0; k < GL_GRAIN_LEDS_PER_COLOUR; k++) {
        float a = led_az_x_(k);
        sum += r[k];
        c1 += r[k] * cosf(a);
        s1 += r[k] * sinf(a);
        c2 += r[k] * cosf(2.0f * a);
        s2 += r[k] * sinf(2.0f * a);
    }
    h->mean = sum / (float)GL_GRAIN_LEDS_PER_COLOUR;
    h->cos1 = 2.0f * c1 / (float)GL_GRAIN_LEDS_PER_COLOUR;
    h->sin1 = 2.0f * s1 / (float)GL_GRAIN_LEDS_PER_COLOUR;
    c2 = 2.0f * c2 / (float)GL_GRAIN_LEDS_PER_COLOUR;
    s2 = 2.0f * s2 / (float)GL_GRAIN_LEDS_PER_COLOUR;
    if (h->mean > 1e-6f) {
        h->modulation = sqrtf(h->cos1 * h->cos1 + h->sin1 * h->sin1) / h->mean;
        h->second = sqrtf(c2 * c2 + s2 * s2) / h->mean;
    } else {
        h->modulation = 0.0f;
        h->second = 0.0f;
    }
    /* direction about +x is atan2(sin1, cos1); convert to "CCW from forward" */
    h->azimuth_rad = (h->modulation > 0.0f)
                         ? gl_wrap_pi(atan2f(h->sin1, h->cos1) - 0.5f * GL_PI_F)
                         : 0.0f;
}

/* Average on-minus-dark per LED with drift rejection.  Returns reject bits. */
static uint8_t raw_signals_(const gl_grain_raw_t *raw, uint16_t max_drift,
                            float signal[GL_GRAIN_LEDS], uint8_t used[GL_GRAIN_LEDS])
{
    uint8_t reject = 0;
    const uint32_t sat = (uint32_t)raw->adc_full_scale - (uint32_t)raw->adc_full_scale / 50u;
    for (unsigned led = 0; led < GL_GRAIN_LEDS; led++) {
        float acc = 0.0f;
        uint8_t n = 0;
        for (unsigned c = 0; c < raw->cycles; c++) {
            const gl_grain_sample_t *s = &raw->s[c][led];
            int drift = (int)s->dark2 - (int)s->dark1;
            if (drift < 0) {
                drift = -drift;
            }
            if (raw->adc_full_scale != 0u && (uint32_t)s->on >= sat) {
                reject |= GL_GRAIN_REJECT_SATURATED;
            }
            if (drift > (int)max_drift) {
                continue;
            }
            acc += (float)s->on - 0.5f * ((float)s->dark1 + (float)s->dark2);
            n++;
        }
        used[led] = n;
        if (n == 0u) {
            reject |= GL_GRAIN_REJECT_DARK_DRIFT;
            signal[led] = 0.0f;
        } else {
            signal[led] = acc / (float)n;
        }
    }
    if (raw->motion) {
        reject |= GL_GRAIN_REJECT_MOTION;
    }
    return reject;
}

gl_status_t gl_grain_process(const gl_grain_raw_t *raw, const gl_cal_grain_t *cal,
                             gl_grain_reading_t *out)
{
    float ratio[GL_GRAIN_LEDS_PER_COLOUR];
    if (raw == NULL || cal == NULL || out == NULL) {
        return GL_ERR_PARAM;
    }
    memset(out, 0, sizeof(*out));
    if (raw->cycles == 0u || raw->cycles > GL_GRAIN_MAX_CYCLES) {
        out->reject = GL_GRAIN_REJECT_BAD_INPUT;
        return GL_ERR_PARAM;
    }
    out->reject = raw_signals_(raw, cal->max_dark_drift_counts, out->signal, out->cycles_used);
    for (unsigned led = 0; led < GL_GRAIN_LEDS; led++) {
        float g = cal->gain[led];
        out->signal[led] = (g > 1e-6f) ? (out->signal[led] / g) : 0.0f;
    }
    harmonic_(&out->signal[0], &out->red);
    harmonic_(&out->signal[GL_GRAIN_LEDS_PER_COLOUR], &out->nir);
    for (unsigned k = 0; k < GL_GRAIN_LEDS_PER_COLOUR; k++) {
        float n = out->signal[GL_GRAIN_LEDS_PER_COLOUR + k];
        ratio[k] = (n > 1.0f) ? (out->signal[k] / n) : 0.0f;
    }
    harmonic_(ratio, &out->ratio);

    if (out->red.mean < (float)cal->min_signal_counts ||
        out->nir.mean < (float)cal->min_signal_counts) {
        out->reject |= GL_GRAIN_REJECT_LOW_SIGNAL;
    }
    if ((cal->flags & GL_CAL_GRAIN_FLAG_WHITE_REF) == 0u) {
        out->reject |= GL_GRAIN_REJECT_NO_WHITE_REF;
    }
    /* The threshold is a calibration constant (gate 0), never a literal. */
    if (!(out->red.modulation >= cal->mod_threshold)) {
        out->reject |= GL_GRAIN_REJECT_BELOW_FLOOR;
    }
    out->valid = (out->reject == 0u);
    return out->valid ? GL_OK : GL_ERR_QUALITY;
}

gl_status_t gl_grain_white_reference(const gl_grain_raw_t *raw, gl_cal_grain_t *cal)
{
    float signal[GL_GRAIN_LEDS];
    uint8_t used[GL_GRAIN_LEDS];
    uint8_t reject;

    if (raw == NULL || cal == NULL || raw->cycles == 0u || raw->cycles > GL_GRAIN_MAX_CYCLES) {
        return GL_ERR_PARAM;
    }
    reject = raw_signals_(raw, cal->max_dark_drift_counts, signal, used);
    if (reject != 0u) {
        return GL_ERR_QUALITY;
    }
    for (unsigned colour = 0; colour < 2u; colour++) {
        const unsigned base = colour * GL_GRAIN_LEDS_PER_COLOUR;
        float mean = 0.0f;
        for (unsigned k = 0; k < GL_GRAIN_LEDS_PER_COLOUR; k++) {
            mean += signal[base + k];
        }
        mean /= (float)GL_GRAIN_LEDS_PER_COLOUR;
        if (mean < (float)cal->min_signal_counts) {
            return GL_ERR_QUALITY;
        }
        for (unsigned k = 0; k < GL_GRAIN_LEDS_PER_COLOUR; k++) {
            float g = signal[base + k] / mean;
            if (!(g > 0.05f && g < 20.0f)) {
                return GL_ERR_QUALITY; /* dead or wildly bright LED */
            }
        }
    }
    for (unsigned colour = 0; colour < 2u; colour++) {
        const unsigned base = colour * GL_GRAIN_LEDS_PER_COLOUR;
        float mean = 0.0f;
        for (unsigned k = 0; k < GL_GRAIN_LEDS_PER_COLOUR; k++) {
            mean += signal[base + k];
        }
        mean /= (float)GL_GRAIN_LEDS_PER_COLOUR;
        for (unsigned k = 0; k < GL_GRAIN_LEDS_PER_COLOUR; k++) {
            cal->gain[base + k] = signal[base + k] / mean;
        }
    }
    cal->flags |= GL_CAL_GRAIN_FLAG_WHITE_REF;
    return GL_OK;
}

gl_status_t gl_grain_noise_floor(const float *modulation, unsigned n, float *scratch,
                                 gl_cal_grain_t *cal)
{
    unsigned i95;
    if (modulation == NULL || scratch == NULL || cal == NULL || n < 20u) {
        return GL_ERR_PARAM;
    }
    memcpy(scratch, modulation, n * sizeof(float));
    cal->noise_floor_mod = gl_median_inplace(scratch, n); /* sorts scratch */
    i95 = (unsigned)((95u * (n - 1u) + 99u) / 100u);      /* ceil(0.95 (n - 1)) */
    cal->mod_threshold = scratch[i95];
    if (cal->mod_threshold < 0.01f) {
        cal->mod_threshold = 0.01f; /* gl_cal_grain_decode refuses less */
    }
    cal->flags |= GL_CAL_GRAIN_FLAG_NOISE_FLOOR;
    return GL_OK;
}

void gl_grain_avg_reset(gl_grain_avg_t *a)
{
    memset(a, 0, sizeof(*a));
}

void gl_grain_avg_add(gl_grain_avg_t *a, float modulation, float azimuth_ref_rad)
{
    /* a direction at angle t (CCW from the reference) is (-sin t, cos t) */
    a->sum_x += -modulation * sinf(azimuth_ref_rad);
    a->sum_y += modulation * cosf(azimuth_ref_rad);
    a->sum_mod += modulation;
    if (a->n < 0xFFFFu) {
        a->n++;
    }
}

unsigned gl_grain_avg_result(const gl_grain_avg_t *a, float *modulation, float *azimuth_ref_rad)
{
    if (a->n == 0u) {
        *modulation = 0.0f;
        *azimuth_ref_rad = 0.0f;
        return 0;
    }
    *modulation = sqrtf(a->sum_x * a->sum_x + a->sum_y * a->sum_y) / (float)a->n;
    *azimuth_ref_rad = (*modulation > 0.0f) ? atan2f(-a->sum_x, a->sum_y) : 0.0f;
    return a->n;
}

void gl_grain_estimate(const gl_settings_t *settings, const gl_cal_grain_t *cal,
                       gl_vec2_t slope_marker, unsigned optical_n, float optical_modulation,
                       float optical_azimuth_rad, gl_grain_est_t *out)
{
    float kappa, cap, slope_mag;
    const uint8_t both = GL_CAL_GRAIN_FLAG_WHITE_REF | GL_CAL_GRAIN_FLAG_NOISE_FLOOR;

    out->kappa_long = 0.0f;
    out->kappa_lat = 0.0f;
    out->azimuth_rad = 0.0f;
    out->source = (uint8_t)GL_GRAIN_SRC_NONE;
    if (settings == NULL || settings->grain_enable == 0u) {
        return;
    }
    switch (settings->grass) {
    case GL_GRASS_BERMUDA: kappa = GL_PROV_GRAIN_KAPPA_BERMUDA; break;
    case GL_GRASS_POA: kappa = GL_PROV_GRAIN_KAPPA_POA; break;
    default: kappa = GL_PROV_GRAIN_KAPPA_BENT; break;
    }
    /* cap at an equivalent slope: kappa a_r = (5/7) g s  ->  kappa = (5/7) g s / a_r */
    cap = (5.0f / 7.0f) * GRAVITY_MPS2 * GL_PROV_GRAIN_MAX_EQUIV_SLOPE /
          gl_settings_decel_mps2(settings);
    if (kappa > cap) {
        kappa = cap;
    }
    slope_mag = sqrtf(slope_marker.x * slope_marker.x + slope_marker.y * slope_marker.y);

    if (cal != NULL && optical_n > 0u && (cal->flags & both) == both &&
        optical_modulation >= GL_GRAIN_OPTICAL_MARGIN * cal->mod_threshold) {
        out->azimuth_rad = (GL_PROV_GRAIN_HARMONIC_SIGN > 0.0f)
                               ? gl_wrap_pi(optical_azimuth_rad)
                               : gl_wrap_pi(optical_azimuth_rad + GL_PI_F);
        out->source = (uint8_t)GL_GRAIN_SRC_OPTICAL;
    } else if (slope_mag >= GL_GRAIN_MIN_PRIOR_SLOPE) {
        out->azimuth_rad = gl_tilt_fall_line_rad(slope_marker);
        out->source = (uint8_t)GL_GRAIN_SRC_PRIOR;
    } else {
        return; /* flat and no optical reading: no direction, no correction */
    }
    out->kappa_long = kappa;
    out->kappa_lat = GL_GRAIN_KLAT_FRACTION * kappa;
}
