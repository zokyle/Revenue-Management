/*
 * test_grain.c - grain front-end processing: dark subtraction and drift
 * rejection, white-reference gains, first-harmonic vector, the calibrated
 * (never fixed) validity threshold, the running average and the estimate
 * handed to the solver.
 */
#include <stdlib.h>

#include "gl_grain.h"
#include "gl_provisional.h"
#include "gl_test.h"

static uint32_t rng_state = 3;
static double urand(void)
{
    rng_state = rng_state * 1664525u + 1013904223u;
    return ((double)(rng_state >> 8) + 0.5) / 16777216.0;
}
static double nrand(void)
{
    return sqrt(-2.0 * log(urand())) * cos(6.283185307179586 * urand());
}

/* Synthesise a raw measurement.  The turf response of an LED at azimuth
 * phi (about +x) is base * (1 + mod * cos(phi - dir_x)); each LED has its
 * own brightness; dark level drifts by `drift` counts per sample. */
static void synth(gl_grain_raw_t *raw, double base, double mod, double dir_x_rad,
                  const double *led_gain, double dark, double drift, double noise, int cycles)
{
    double d = dark;
    memset(raw, 0, sizeof(*raw));
    raw->cycles = (uint8_t)cycles;
    raw->adc_full_scale = 16383;
    for (int c = 0; c < cycles; c++) {
        for (unsigned led = 0; led < GL_GRAIN_LEDS; led++) {
            double phi = (22.5 + 45.0 * (led % 8)) * 3.141592653589793 / 180.0;
            double sig = base * (led_gain ? led_gain[led] : 1.0) *
                         (1.0 + mod * cos(phi - dir_x_rad));
            raw->s[c][led].dark1 = (uint16_t)lrint(d + noise * nrand());
            d += drift;
            raw->s[c][led].on = (uint16_t)lrint(d + sig + noise * nrand());
            d += drift;
            raw->s[c][led].dark2 = (uint16_t)lrint(d + noise * nrand());
        }
    }
}

static gl_cal_grain_t calibrated(void)
{
    gl_cal_grain_t cal;
    gl_cal_grain_defaults(&cal);
    cal.flags = GL_CAL_GRAIN_FLAG_WHITE_REF | GL_CAL_GRAIN_FLAG_NOISE_FLOOR;
    cal.mod_threshold = 0.27f;
    return cal;
}

GL_TEST(test_led_geometry)
{
    /* LED 0 at 22.5 deg from +x = -67.5 deg from forward (to the right) */
    GL_CHECK_NEAR(gl_grain_led_azimuth_rad(0), -67.5 * 3.14159265 / 180.0, 1e-5);
    GL_CHECK_NEAR(gl_grain_led_azimuth_rad(2), 22.5 * 3.14159265 / 180.0, 1e-5);
    GL_CHECK_NEAR(gl_grain_led_azimuth_rad(8), gl_grain_led_azimuth_rad(0), 1e-9);
    for (unsigned k = 0; k < 16; k++) {
        gl_vec2_t p = gl_grain_led_position_mm(k);
        GL_CHECK_NEAR(sqrt((double)(p.x * p.x + p.y * p.y)), 5.2, 1e-4);
        /* opposite LEDs are diametrically opposite */
        gl_vec2_t q = gl_grain_led_position_mm((k + 4) % 8);
        GL_CHECK_NEAR(p.x + q.x, 0.0, 1e-4);
        GL_CHECK_NEAR(p.y + q.y, 0.0, 1e-4);
    }
    {
        gl_vec2_t p0 = gl_grain_led_position_mm(0);
        GL_CHECK(p0.x > 4.7f && p0.y > 1.9f && p0.y < 2.1f);
    }
}

GL_TEST(test_harmonic_recovery)
{
    gl_cal_grain_t cal = calibrated();
    gl_grain_raw_t raw;
    gl_grain_reading_t r;
    double worst_dir = 0, worst_mod = 0;

    rng_state = 11;
    /* noise-free: exact recovery of modulation and direction at any angle */
    for (int deg = 0; deg < 360; deg += 7) {
        double dir = deg * 3.141592653589793 / 180.0;
        synth(&raw, 3000.0, 0.40, dir, NULL, 500.0, 0.0, 0.0, 3);
        GL_CHECK_EQ(gl_grain_process(&raw, &cal, &r), GL_OK);
        GL_CHECK(r.valid);
        GL_CHECK_NEAR(r.red.modulation, 0.40, 2e-3);
        GL_CHECK_NEAR(r.nir.modulation, 0.40, 2e-3);
        GL_CHECK_NEAR(r.red.mean, 3000.0, 2.0);
        GL_CHECK_NEAR(r.red.second, 0.0, 2e-3);
        /* direction reported CCW from forward = about +x minus 90 degrees */
        double e = (double)gl_wrap_pi(r.red.azimuth_rad - (float)(dir - 1.5707963267948966));
        GL_CHECK_NEAR(e, 0.0, 2e-3);
        /* a pure common-mode pattern cancels in the red / nir ratio */
        GL_CHECK_NEAR(r.ratio.modulation, 0.0, 2e-3);
    }
    /* with noise (5 counts rms on a 3000-count signal) */
    for (int t = 0; t < 300; t++) {
        double dir = 6.283185307179586 * urand();
        double mod = 0.3 + 0.4 * urand();
        synth(&raw, 3000.0, mod, dir, NULL, 400.0, 0.0, 5.0, 4);
        GL_CHECK_EQ(gl_grain_process(&raw, &cal, &r), GL_OK);
        double e = fabs((double)gl_wrap_pi(r.red.azimuth_rad - (float)(dir - 1.5707963267948966)));
        if (e > worst_dir) {
            worst_dir = e;
        }
        if (fabs((double)r.red.modulation - mod) > worst_mod) {
            worst_mod = fabs((double)r.red.modulation - mod);
        }
    }
    printf("    harmonic recovery, 5-count noise, 300 trials: worst direction error %.2f deg, "
           "worst modulation error %.4f\n", worst_dir * 57.29578, worst_mod);
    GL_CHECK(worst_dir < 0.02);
    GL_CHECK(worst_mod < 0.005);
}

GL_TEST(test_threshold_is_a_calibration_constant)
{
    gl_cal_grain_t cal = calibrated();
    gl_grain_raw_t raw;
    gl_grain_reading_t r;

    /* modulation 0.15: above the forbidden fixed 0.10, below this unit's
     * calibrated threshold of 0.27 -> rejected */
    synth(&raw, 3000.0, 0.15, 1.0, NULL, 500.0, 0.0, 0.0, 3);
    GL_CHECK_EQ(gl_grain_process(&raw, &cal, &r), GL_ERR_QUALITY);
    GL_CHECK(!r.valid);
    GL_CHECK_EQ(r.reject, GL_GRAIN_REJECT_BELOW_FLOOR);
    GL_CHECK_NEAR(r.red.modulation, 0.15, 2e-3); /* still reported */
    /* the same data on a unit whose noise floor calibrated lower -> accepted */
    cal.mod_threshold = 0.12f;
    GL_CHECK_EQ(gl_grain_process(&raw, &cal, &r), GL_OK);
    /* and on one calibrated higher, even 0.4 is refused */
    cal.mod_threshold = 0.45f;
    synth(&raw, 3000.0, 0.40, 1.0, NULL, 500.0, 0.0, 0.0, 3);
    GL_CHECK_EQ(gl_grain_process(&raw, &cal, &r), GL_ERR_QUALITY);
    /* the uncalibrated default is the provisional constant, not 0.10 */
    gl_cal_grain_defaults(&cal);
    GL_CHECK_NEAR(cal.mod_threshold, GL_PROV_GRAIN_MOD_THRESHOLD_DEFAULT, 1e-9);
    GL_CHECK(cal.mod_threshold > 0.2f);
    /* without the white reference a reading is never valid */
    synth(&raw, 3000.0, 0.60, 1.0, NULL, 500.0, 0.0, 0.0, 3);
    GL_CHECK_EQ(gl_grain_process(&raw, &cal, &r), GL_ERR_QUALITY);
    GL_CHECK_EQ(r.reject, GL_GRAIN_REJECT_NO_WHITE_REF);
}

GL_TEST(test_noise_floor_gate)
{
    gl_cal_grain_t cal;
    float mods[60], scratch[60];
    gl_cal_grain_defaults(&cal);
    for (int i = 0; i < 60; i++) {
        mods[i] = 0.05f + 0.004f * (float)i; /* 0.05 .. 0.286 */
    }
    GL_CHECK_EQ(gl_grain_noise_floor(mods, 19, scratch, &cal), GL_ERR_PARAM);
    GL_CHECK_EQ(cal.flags & GL_CAL_GRAIN_FLAG_NOISE_FLOOR, 0);
    GL_CHECK_EQ(gl_grain_noise_floor(mods, 60, scratch, &cal), GL_OK);
    GL_CHECK(cal.flags & GL_CAL_GRAIN_FLAG_NOISE_FLOOR);
    GL_CHECK_NEAR(cal.noise_floor_mod, 0.5 * (mods[29] + mods[30]), 1e-6);
    GL_CHECK_NEAR(cal.mod_threshold, mods[57], 1e-6); /* 95th percentile of 60 */
    GL_CHECK_NEAR(mods[0], 0.05, 1e-7);               /* input untouched */
    /* the record survives the storage round trip */
    {
        uint8_t blob[GL_CAL_GRAIN_BLOB_LEN];
        gl_cal_grain_t c2;
        gl_cal_grain_encode(&cal, blob);
        GL_CHECK_EQ(gl_cal_grain_decode(blob, sizeof(blob), &c2), GL_OK);
        GL_CHECK(c2.mod_threshold == cal.mod_threshold && c2.flags == cal.flags);
        /* a zero threshold in storage is refused */
        gl_put_f32(&blob[2 + 64], 0.0f);
        GL_CHECK_EQ(gl_cal_grain_decode(blob, sizeof(blob), &c2), GL_ERR_RANGE);
    }
}

GL_TEST(test_white_reference)
{
    gl_cal_grain_t cal;
    gl_grain_raw_t raw;
    gl_grain_reading_t r;
    double gains[16];

    /* LED-to-LED brightness spread of +-30 % looks like strong grain ... */
    rng_state = 21;
    for (int i = 0; i < 16; i++) {
        gains[i] = 0.7 + 0.6 * urand();
    }
    gl_cal_grain_defaults(&cal);
    cal.flags = GL_CAL_GRAIN_FLAG_WHITE_REF; /* pretend, to see the raw effect */
    cal.mod_threshold = 0.05f;
    synth(&raw, 3000.0, 0.0, 0.0, gains, 500.0, 0.0, 0.0, 3);
    gl_grain_process(&raw, &cal, &r);
    GL_CHECK(r.red.modulation > 0.03f);
    {
        float false_mod = r.red.modulation;
        /* ... until the white tile has been measured */
        gl_cal_grain_defaults(&cal);
        cal.mod_threshold = 0.05f;
        GL_CHECK_EQ(gl_grain_white_reference(&raw, &cal), GL_OK);
        GL_CHECK(cal.flags & GL_CAL_GRAIN_FLAG_WHITE_REF);
        gl_grain_process(&raw, &cal, &r);
        printf("    white tile: false modulation %.3f before gain calibration, %.5f after\n",
               (double)false_mod, (double)r.red.modulation);
        GL_CHECK(r.red.modulation < 0.002f);
        GL_CHECK(r.nir.modulation < 0.002f);
    }
    /* gains average to 1 per colour */
    {
        float sr = 0, sn = 0;
        for (int k = 0; k < 8; k++) {
            sr += cal.gain[k];
            sn += cal.gain[8 + k];
        }
        GL_CHECK_NEAR(sr, 8.0, 1e-4);
        GL_CHECK_NEAR(sn, 8.0, 1e-4);
    }
    /* real grain is then recovered through the unequal LEDs */
    synth(&raw, 3000.0, 0.35, 2.0, gains, 500.0, 0.0, 0.0, 3);
    GL_CHECK_EQ(gl_grain_process(&raw, &cal, &r), GL_OK);
    GL_CHECK_NEAR(r.red.modulation, 0.35, 3e-3);
    GL_CHECK_NEAR(gl_wrap_pi(r.red.azimuth_rad - (2.0f - 1.5707963f)), 0.0, 3e-3);
    /* a dead LED makes the white reference fail and leaves the record alone */
    {
        gl_cal_grain_t c2;
        gl_cal_grain_defaults(&c2);
        gains[5] = 0.0;
        synth(&raw, 3000.0, 0.0, 0.0, gains, 500.0, 0.0, 0.0, 3);
        GL_CHECK_EQ(gl_grain_white_reference(&raw, &c2), GL_ERR_QUALITY);
        GL_CHECK_EQ(c2.flags, 0);
        GL_CHECK_NEAR(c2.gain[5], 1.0, 1e-9);
    }
}

GL_TEST(test_rejections)
{
    gl_cal_grain_t cal = calibrated();
    gl_grain_raw_t raw;
    gl_grain_reading_t r;

    /* motion */
    synth(&raw, 3000.0, 0.5, 1.0, NULL, 500.0, 0.0, 0.0, 3);
    raw.motion = true;
    GL_CHECK_EQ(gl_grain_process(&raw, &cal, &r), GL_ERR_QUALITY);
    GL_CHECK_EQ(r.reject, GL_GRAIN_REJECT_MOTION);

    /* dark drift: ambient light changing fast.  The dark/on/dark triple
     * cancels a LINEAR drift exactly, but beyond the calibrated limit the
     * cycle is dropped. */
    synth(&raw, 3000.0, 0.5, 1.0, NULL, 500.0, 3.0, 0.0, 3); /* 6 counts between darks: ok */
    GL_CHECK_EQ(gl_grain_process(&raw, &cal, &r), GL_OK);
    GL_CHECK_NEAR(r.red.modulation, 0.5, 3e-3);
    GL_CHECK_EQ(r.cycles_used[0], 3);
    synth(&raw, 3000.0, 0.5, 1.0, NULL, 500.0, 30.0, 0.0, 3); /* 60 counts: over the limit of 40 */
    GL_CHECK_EQ(gl_grain_process(&raw, &cal, &r), GL_ERR_QUALITY);
    GL_CHECK(r.reject & GL_GRAIN_REJECT_DARK_DRIFT);
    /* a single disturbed cycle is dropped, the others carry the reading */
    synth(&raw, 3000.0, 0.5, 1.0, NULL, 500.0, 0.0, 0.0, 4);
    raw.s[2][6].dark2 = (uint16_t)(raw.s[2][6].dark2 + 300);
    GL_CHECK_EQ(gl_grain_process(&raw, &cal, &r), GL_OK);
    GL_CHECK_EQ(r.cycles_used[6], 3);
    GL_CHECK_EQ(r.cycles_used[5], 4);
    GL_CHECK_NEAR(r.red.modulation, 0.5, 3e-3);

    /* saturation */
    synth(&raw, 3000.0, 0.5, 1.0, NULL, 500.0, 0.0, 0.0, 3);
    raw.s[1][3].on = 16383;
    GL_CHECK_EQ(gl_grain_process(&raw, &cal, &r), GL_ERR_QUALITY);
    GL_CHECK(r.reject & GL_GRAIN_REJECT_SATURATED);

    /* too little light (lifted off the turf, dirty window) */
    synth(&raw, 80.0, 0.5, 1.0, NULL, 500.0, 0.0, 0.0, 3);
    GL_CHECK_EQ(gl_grain_process(&raw, &cal, &r), GL_ERR_QUALITY);
    GL_CHECK(r.reject & GL_GRAIN_REJECT_LOW_SIGNAL);

    /* bad arguments */
    raw.cycles = 0;
    GL_CHECK_EQ(gl_grain_process(&raw, &cal, &r), GL_ERR_PARAM);
    raw.cycles = 5;
    GL_CHECK_EQ(gl_grain_process(&raw, &cal, &r), GL_ERR_PARAM);
    GL_CHECK_EQ(gl_grain_process(NULL, &cal, &r), GL_ERR_PARAM);
}

GL_TEST(test_running_average)
{
    gl_grain_avg_t a;
    float mod, az;
    gl_grain_avg_reset(&a);
    GL_CHECK_EQ(gl_grain_avg_result(&a, &mod, &az), 0);
    /* consistent readings reinforce */
    for (int i = 0; i < 5; i++) {
        gl_grain_avg_add(&a, 0.4f, 0.5f + 0.02f * (float)(i - 2));
    }
    GL_CHECK_EQ(gl_grain_avg_result(&a, &mod, &az), 5);
    GL_CHECK_NEAR(mod, 0.4, 2e-3);
    GL_CHECK_NEAR(az, 0.5, 1e-3);
    /* opposite readings cancel: a single reading is weak evidence */
    gl_grain_avg_reset(&a);
    gl_grain_avg_add(&a, 0.4f, 0.3f);
    gl_grain_avg_add(&a, 0.4f, 0.3f + GL_PI_F);
    GL_CHECK_EQ(gl_grain_avg_result(&a, &mod, &az), 2);
    GL_CHECK_NEAR(mod, 0.0, 1e-6);
    /* random directions: the mean shrinks roughly as 1 / sqrt(n) */
    gl_grain_avg_reset(&a);
    rng_state = 9;
    for (int i = 0; i < 400; i++) {
        gl_grain_avg_add(&a, 0.3f, (float)(6.283185307 * urand()));
    }
    gl_grain_avg_result(&a, &mod, &az);
    GL_CHECK(mod < 0.3f * 3.0f / 20.0f);
}

GL_TEST(test_estimate_for_solver)
{
    gl_settings_t s;
    gl_cal_grain_t cal = calibrated();
    gl_grain_est_t e;
    const gl_vec2_t slope = { 0.02f, 0.0f }; /* uphill to the right: fall line to the left */
    const gl_vec2_t flat = { 0.001f, 0.0f };

    gl_settings_defaults(&s);
    /* ships disabled: nothing, whatever the sensor says */
    GL_CHECK_EQ(s.grain_enable, 0);
    gl_grain_estimate(&s, &cal, slope, 5, 0.9f, 1.0f, &e);
    GL_CHECK_EQ(e.source, GL_GRAIN_SRC_NONE);
    GL_CHECK_NEAR(e.kappa_long, 0.0, 1e-12);
    GL_CHECK_NEAR(e.kappa_lat, 0.0, 1e-12);

    /* enabled, no optical reading: prior down the fall line, strength by grass */
    s.grain_enable = 1;
    s.grass = GL_GRASS_BERMUDA;
    gl_grain_estimate(&s, &cal, slope, 0, 0.0f, 0.0f, &e);
    GL_CHECK_EQ(e.source, GL_GRAIN_SRC_PRIOR);
    GL_CHECK_NEAR(e.azimuth_rad, 1.5707963, 1e-5);
    GL_CHECK_NEAR(e.kappa_long, GL_PROV_GRAIN_KAPPA_BERMUDA, 1e-9);
    GL_CHECK_NEAR(e.kappa_lat, 0.5 * (double)GL_PROV_GRAIN_KAPPA_BERMUDA, 1e-9);
    s.grass = GL_GRASS_BENT;
    gl_grain_estimate(&s, &cal, slope, 0, 0.0f, 0.0f, &e);
    GL_CHECK_NEAR(e.kappa_long, GL_PROV_GRAIN_KAPPA_BENT, 1e-9);
    /* flat green and no optical reading: no direction, no correction */
    gl_grain_estimate(&s, &cal, flat, 0, 0.0f, 0.0f, &e);
    GL_CHECK_EQ(e.source, GL_GRAIN_SRC_NONE);
    GL_CHECK_NEAR(e.kappa_long, 0.0, 1e-12);

    /* optical reading well above the floor replaces the direction ... */
    s.grass = GL_GRASS_BERMUDA;
    gl_grain_estimate(&s, &cal, slope, 3, 1.5f * 0.27f + 0.01f, -0.7f, &e);
    GL_CHECK_EQ(e.source, GL_GRAIN_SRC_OPTICAL);
    GL_CHECK_NEAR(e.azimuth_rad, -0.7, 1e-6);
    /* ... but one only just above the threshold does not */
    gl_grain_estimate(&s, &cal, slope, 3, 0.30f, -0.7f, &e);
    GL_CHECK_EQ(e.source, GL_GRAIN_SRC_PRIOR);
    /* ... and neither does any reading while a calibration gate is open */
    cal.flags = GL_CAL_GRAIN_FLAG_WHITE_REF;
    gl_grain_estimate(&s, &cal, slope, 3, 0.9f, -0.7f, &e);
    GL_CHECK_EQ(e.source, GL_GRAIN_SRC_PRIOR);

    /* Cap: the equivalent slope kappa * a_r / ((5/7) g) never exceeds
     * 0.8 %, for every green speed and grass type.  (With the present
     * provisional kappa values the cap is only approached, at Stimp 6 on
     * bermuda; it exists so that a later, larger kappa cannot run away.) */
    cal = calibrated();
    {
        double worst = 0;
        int worst_stimp = 0;
        for (int stimp = GL_STIMP_X2_MIN; stimp <= (int)GL_STIMP_X2_MAX; stimp++) {
            for (int grass = 0; grass < GL_GRASS_COUNT; grass++) {
                s.stimp_x2 = (uint8_t)stimp;
                s.grass = (uint8_t)grass;
                gl_grain_estimate(&s, &cal, slope, 0, 0.0f, 0.0f, &e);
                double a_r = (double)gl_settings_decel_mps2(&s);
                double equiv = (double)e.kappa_long * a_r / ((5.0 / 7.0) * 9.80665);
                GL_CHECK(equiv <= (double)GL_PROV_GRAIN_MAX_EQUIV_SLOPE * 1.0001);
                GL_CHECK(e.kappa_lat <= e.kappa_long);
                if (equiv > worst) {
                    worst = equiv;
                    worst_stimp = stimp;
                }
            }
        }
        printf("    largest grain correction: equivalent slope %.3f %% at Stimp %.1f "
               "(cap %.1f %%)\n", 100.0 * worst, 0.5 * worst_stimp,
               100.0 * (double)GL_PROV_GRAIN_MAX_EQUIV_SLOPE);
    }
}

int main(void)
{
    GL_RUN(test_led_geometry);
    GL_RUN(test_harmonic_recovery);
    GL_RUN(test_threshold_is_a_calibration_constant);
    GL_RUN(test_noise_floor_gate);
    GL_RUN(test_white_reference);
    GL_RUN(test_rejections);
    GL_RUN(test_running_average);
    GL_RUN(test_estimate_for_solver);
    return gl_test_summary();
}
