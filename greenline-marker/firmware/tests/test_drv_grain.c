/*
 * test_drv_grain.c - grain front end (charlieplexed LED ring + photodiode
 * stage) against the simulator: exact charlieplex pin states for each of
 * the 16 LEDs, break-before-make switching, sneak-path property of the
 * proposed wiring, the dark / on / dark sequence and scan order on the ADC,
 * the power sequence of the analog chain, and the data handed to
 * core/gl_grain.
 */
#include <stdlib.h>

#include "gl_test.h"

#include "gl_provisional.h"
#include "gl_trace_util.h"
#include "grain_frontend.h"

static void fresh_(void)
{
    gl_sim_reset(true);
    (void)gl_hal_init();
}

static gl_pin_t cp_(unsigned n)
{
    return (gl_pin_t)((unsigned)GL_PIN_GRAIN_CP0 + n);
}

/*
 * The wiring this firmware PROPOSES (no netlist exists), written out
 * independently of the driver's table: for LED 0..15 the charlieplex pin
 * that must be driven HIGH (anode) and the one driven LOW (cathode).
 * LEDs 0..7 are red (anode on the lower-numbered pin of the pair),
 * 8..15 the antiparallel near-infrared ones.
 */
static const uint8_t expect_[16][2] = {
    /* red  k = 0..7 */ { 0, 1 }, { 0, 2 }, { 0, 3 }, { 0, 4 }, { 1, 2 }, { 1, 3 }, { 1, 4 }, { 2, 3 },
    /* NIR  k = 0..7 */ { 1, 0 }, { 2, 0 }, { 3, 0 }, { 4, 0 }, { 2, 1 }, { 3, 1 }, { 4, 1 }, { 3, 2 }
};

GL_TEST(test_all_off_is_all_analog)
{
    fresh_();
    gl_grain_fe_all_off();
    for (unsigned n = 0; n < 5u; n++) {
        GL_CHECK_EQ(gl_sim_pin_mode(cp_(n)), GL_PIN_MODE_ANALOG);
    }
    GL_CHECK_EQ(gl_sim_grain_lit_mask(), 0u);
    /* an out-of-range LED number turns everything off */
    gl_grain_fe_led_on(3);
    GL_CHECK(gl_sim_grain_lit_mask() != 0u);
    gl_grain_fe_led_on(16);
    GL_CHECK_EQ(gl_sim_grain_lit_mask(), 0u);
    gl_grain_fe_led_on(5);
    gl_grain_fe_led_on(-1);
    GL_CHECK_EQ(gl_sim_grain_lit_mask(), 0u);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

GL_TEST(test_charlieplex_pin_states_for_each_led)
{
    fresh_();
    for (unsigned led = 0; led < 16u; led++) {
        uint8_t an = 9, ca = 9;
        const unsigned a = expect_[led][0], c = expect_[led][1];
        gl_grain_fe_led_pins(led, &an, &ca);
        GL_CHECK_EQ(an, a);
        GL_CHECK_EQ(ca, c);

        gl_sim_trace_clear();
        gl_grain_fe_led_on((int)led);
        /* pin states: anode push-pull HIGH, cathode push-pull LOW, the other
         * three high impedance (ANALOG) */
        for (unsigned n = 0; n < 5u; n++) {
            if (n == a) {
                GL_CHECK_EQ(gl_sim_pin_mode(cp_(n)), GL_PIN_MODE_OUTPUT_PP);
                GL_CHECK(gl_sim_pin_drives_high(cp_(n)));
            } else if (n == c) {
                GL_CHECK_EQ(gl_sim_pin_mode(cp_(n)), GL_PIN_MODE_OUTPUT_PP);
                GL_CHECK(gl_sim_pin_drives_low(cp_(n)));
            } else {
                GL_CHECK_EQ(gl_sim_pin_mode(cp_(n)), GL_PIN_MODE_ANALOG);
            }
        }
        /* exactly this LED is lit in the model's netlist */
        GL_CHECK_EQ(gl_sim_grain_lit_mask(), 1u << led);

        /* exact pin traffic: all five pins released first (break), then the
         * cathode (latch low, then output), then the anode (latch high, then
         * output): 5 + 4 records and nothing else */
        GL_CHECK_EQ(gl_sim_trace_count(), 9);
        for (size_t i = 0; i < 5u && gl_sim_trace_count() == 9u; i++) {
            const gl_sim_trace_t *t = gl_sim_trace_at(i);
            GL_CHECK_EQ(t->type, GL_SIM_TR_GPIO_MODE);
            GL_CHECK_EQ(t->a, cp_((unsigned)i));
            GL_CHECK_EQ(t->b, GL_PIN_MODE_ANALOG);
        }
        if (gl_sim_trace_count() == 9u) {
            const gl_sim_trace_t *t5 = gl_sim_trace_at(5), *t6 = gl_sim_trace_at(6);
            const gl_sim_trace_t *t7 = gl_sim_trace_at(7), *t8 = gl_sim_trace_at(8);
            GL_CHECK(t5->type == GL_SIM_TR_GPIO_WRITE && t5->a == cp_(c) && t5->b == 0u);
            GL_CHECK(t6->type == GL_SIM_TR_GPIO_MODE && t6->a == cp_(c) &&
                     t6->b == (uint16_t)GL_PIN_MODE_OUTPUT_PP);
            GL_CHECK(t7->type == GL_SIM_TR_GPIO_WRITE && t7->a == cp_(a) && t7->b == 1u);
            GL_CHECK(t8->type == GL_SIM_TR_GPIO_MODE && t8->a == cp_(a) &&
                     t8->b == (uint16_t)GL_PIN_MODE_OUTPUT_PP);
        }
    }
    /* switching straight from one LED to the next never lights two */
    for (unsigned led = 0; led < 16u; led++) {
        gl_grain_fe_led_on((int)led);
        gl_grain_fe_led_on((int)((led * 7u + 3u) % 16u));
    }
    gl_grain_fe_all_off();
    GL_CHECK_EQ(gl_sim_violations()->analog, 0u);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* Property of the proposed wiring, checked on the driver's own tables: every
 * LED uses a distinct ordered pin pair, the two LEDs of a pair are
 * antiparallel, and no two-LED series path through a floating pin can
 * conduct in parallel with a lit LED without containing a red LED. */
GL_TEST(test_wiring_has_no_low_voltage_sneak_path)
{
    uint8_t an[16], ca[16];
    unsigned nir_paths_beside_red = 0, nir_only_paths = 0, paths = 0;
    for (unsigned led = 0; led < 16u; led++) {
        gl_grain_fe_led_pins(led, &an[led], &ca[led]);
        GL_CHECK(an[led] < 5u && ca[led] < 5u && an[led] != ca[led]);
    }
    for (unsigned i = 0; i < 16u; i++) {
        for (unsigned j = i + 1u; j < 16u; j++) {
            GL_CHECK(!(an[i] == an[j] && ca[i] == ca[j])); /* distinct */
        }
    }
    for (unsigned k = 0; k < 8u; k++) {
        GL_CHECK(an[k] == ca[8u + k] && ca[k] == an[8u + k]); /* antiparallel pair */
        GL_CHECK(an[k] < ca[k]); /* red: anode on the lower pin (GL_PROV_GRAIN_RED_ANODE_ON_LOW_PIN) */
    }
    /* sneak paths: lit LED i (a -> c); two other LEDs p (a -> m) and q (m -> c) */
    for (unsigned i = 0; i < 16u; i++) {
        for (unsigned p = 0; p < 16u; p++) {
            for (unsigned q = 0; q < 16u; q++) {
                if (p == i || q == i || p == q || an[p] != an[i] || ca[q] != ca[i] ||
                    ca[p] != an[q] || ca[p] == an[i] || ca[p] == ca[i]) {
                    continue;
                }
                paths++;
                if (p >= 8u && q >= 8u) {
                    nir_only_paths++;
                    /* two NIR LEDs in series conduct from about 2 x 1.2 V.
                     * Beside a lit NIR LED (which clamps the nodes to ONE NIR
                     * forward voltage) that is harmless; beside a lit RED LED
                     * (about 1.9 V) it would glow.  The wiring rule must leave
                     * no such path. */
                    if (i < 8u) {
                        nir_paths_beside_red++;
                    }
                }
            }
        }
    }
    printf("    proposed charlieplex wiring: %u two-LED sneak paths, %u of them NIR-only, "
           "%u NIR-only paths in parallel with a lit RED LED\n", paths, nir_only_paths,
           nir_paths_beside_red);
    GL_CHECK(paths > 0u);
    GL_CHECK_EQ(nir_paths_beside_red, 0u);
}

static void set_response_(gl_sim_grain_t *g, float mod, float az_deg)
{
    memset(g, 0, sizeof(*g));
    g->dark_counts = 8000.0f;
    g->noise_counts = 2.0f;
    for (unsigned k = 0; k < 8u; k++) {
        const float az = (22.5f + 45.0f * (float)k - az_deg) * 0.0174532925f;
        g->response[k] = 2000.0f * (1.0f + mod * cosf(az));         /* red */
        g->response[8u + k] = 1500.0f * (1.0f + 0.5f * mod * cosf(az)); /* NIR */
    }
}

GL_TEST(test_measure_sequence_on_the_adc)
{
    static gl_grain_raw_t raw;
    gl_sim_grain_t g;
    fresh_();
    set_response_(&g, 0.2f, 60.0f);
    gl_sim_grain_set(&g);
    gl_sim_trace_clear();
    const uint64_t t0 = gl_sim_now_us();
    GL_CHECK_EQ(gl_grain_fe_measure(&raw, 2), GL_OK);
    const uint64_t dt = gl_sim_now_us() - t0;
    GL_CHECK_EQ(raw.cycles, 2);
    GL_CHECK_EQ(raw.adc_full_scale, GL_HAL_ADC_FULL_SCALE);
    GL_CHECK(!raw.motion);

    /* power sequence: ADC on, then OPAMP1 on, then the settle time, then the
     * first conversion; at the end op-amp off, then ADC off */
    const long i_adc_on = tr_find(0, GL_SIM_TR_ADC_POWER, 1);
    const long i_op_on = tr_find(0, GL_SIM_TR_OPAMP, 1);
    const long i_first = tr_find(0, GL_SIM_TR_ADC_READ, -1);
    const long i_op_off = tr_find(0, GL_SIM_TR_OPAMP, 0);
    const long i_adc_off = tr_find(0, GL_SIM_TR_ADC_POWER, 0);
    GL_CHECK(i_adc_on >= 0 && i_op_on > i_adc_on && i_first > i_op_on);
    GL_CHECK(i_op_off > i_first && i_adc_off > i_op_off);
    if (i_first > 0 && i_op_on > 0) {
        GL_CHECK(gl_sim_trace_at((size_t)i_first)->t_us - gl_sim_trace_at((size_t)i_op_on)->t_us >=
                 (uint64_t)GL_PROV_GRAIN_POWER_SETTLE_MS * 1000u);
    }
    /* the op-amp pins are analog while it runs */
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_OPAMP_VINP), GL_PIN_MODE_ANALOG);
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_OPAMP_VINM), GL_PIN_MODE_ANALOG);
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_OPAMP_VOUT), GL_PIN_MODE_ANALOG);

    /* conversions: 2 cycles x 16 LEDs x (dark, on, dark), all on the TIA
     * channel; the lit-LED mask recorded with each conversion gives the
     * exact scan: red k, NIR k, ascending pairs on cycle 0, the reverse on
     * cycle 1 */
    {
        unsigned n = 0;
        uint64_t t_prev_gpio = 0;
        for (size_t i = 0; i < gl_sim_trace_count(); i++) {
            const gl_sim_trace_t *t = gl_sim_trace_at(i);
            if (t->type == (uint8_t)GL_SIM_TR_GPIO_MODE || t->type == (uint8_t)GL_SIM_TR_GPIO_WRITE) {
                t_prev_gpio = t->t_us;
            }
            if (t->type != (uint8_t)GL_SIM_TR_ADC_READ) {
                continue;
            }
            const unsigned cycle = n / 48u, step = (n % 48u) / 3u, phase = n % 3u;
            const unsigned s = (cycle == 0u) ? step : (15u - step);
            const unsigned led = ((s & 1u) == 0u) ? (s / 2u) : (8u + s / 2u);
            GL_CHECK_EQ(t->a, GL_ADC_CH_GRAIN_TIA);
            GL_CHECK_EQ(t->c, (phase == 1u) ? (1u << led) : 0u);
            /* the reading is taken only after the settle time since the last
             * pin change */
            GL_CHECK(t->t_us - t_prev_gpio >= GL_PROV_GRAIN_SETTLE_US);
            /* and it is what ended up in the raw record */
            {
                const gl_grain_sample_t *smp = &raw.s[cycle][led];
                const uint16_t v = (phase == 0u) ? smp->dark1 : ((phase == 1u) ? smp->on : smp->dark2);
                GL_CHECK_EQ(t->b, v);
            }
            n++;
        }
        GL_CHECK_EQ(n, 2u * 16u * 3u);
    }
    /* values: dark near the model's dark level, on = dark + response */
    for (unsigned c = 0; c < 2u; c++) {
        for (unsigned led = 0; led < 16u; led++) {
            const gl_grain_sample_t *s = &raw.s[c][led];
            GL_CHECK_NEAR(s->dark1, 8000.0, 6.0);
            GL_CHECK_NEAR(s->dark2, 8000.0, 6.0);
            GL_CHECK_NEAR((double)s->on - 0.5 * ((double)s->dark1 + (double)s->dark2),
                          (double)g.response[led], 8.0);
        }
    }
    /* end state: everything off */
    for (unsigned n = 0; n < 5u; n++) {
        GL_CHECK_EQ(gl_sim_pin_mode(cp_(n)), GL_PIN_MODE_ANALOG);
    }
    printf("    2 cycles (96 conversions of 16 averaged samples): %.1f ms including %u ms power settle\n",
           (double)dt / 1000.0, (unsigned)GL_PROV_GRAIN_POWER_SETTLE_MS);
    GL_CHECK(dt < 120000u);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

GL_TEST(test_driver_data_through_core_processing)
{
    static gl_grain_raw_t raw;
    gl_grain_reading_t rd;
    gl_cal_grain_t cal;
    gl_sim_grain_t g;
    /* direction of the brightest illumination: 60 degrees CCW from marker +x
     * = -30 degrees from marker forward (+y) in the firmware convention */
    fresh_();
    set_response_(&g, 0.4f, 60.0f);
    gl_sim_grain_set(&g);
    gl_cal_grain_defaults(&cal);
    cal.flags = GL_CAL_GRAIN_FLAG_WHITE_REF | GL_CAL_GRAIN_FLAG_NOISE_FLOOR;
    cal.mod_threshold = 0.25f; /* from the calibration record, as always */
    cal.min_signal_counts = 200;
    cal.max_dark_drift_counts = 30;
    GL_CHECK_EQ(gl_grain_fe_measure(&raw, GL_GRAIN_MAX_CYCLES), GL_OK);
    GL_CHECK_EQ(gl_grain_process(&raw, &cal, &rd), GL_OK);
    GL_CHECK(rd.valid);
    GL_CHECK_NEAR(rd.red.modulation, 0.4, 0.01);
    GL_CHECK_NEAR(rd.nir.modulation, 0.2, 0.01);
    GL_CHECK_NEAR(rd.red.azimuth_rad, -30.0 * 0.0174532925, 0.02);
    GL_CHECK_NEAR(rd.red.mean, 2000.0, 10.0);
    printf("    ring -> ADC -> core: modulation %.3f (true 0.400), azimuth %.1f deg from forward "
           "(true -30.0)\n", (double)rd.red.modulation, (double)rd.red.azimuth_rad * 57.29578);

    /* the same turf with a weak modulation is refused by the CALIBRATED
     * threshold */
    set_response_(&g, 0.1f, 60.0f);
    gl_sim_grain_set(&g);
    GL_CHECK_EQ(gl_grain_fe_measure(&raw, 2), GL_OK);
    GL_CHECK_EQ(gl_grain_process(&raw, &cal, &rd), GL_ERR_QUALITY);
    GL_CHECK(rd.reject & GL_GRAIN_REJECT_BELOW_FLOOR);

    /* ambient light ramping during the measurement: the darks either side of
     * an LED differ, the core drops those cycles */
    set_response_(&g, 0.4f, 60.0f);
    g.dark_counts = 15500.0f;          /* falling, so that nothing saturates */
    g.drift_counts_per_ms = -30.0f;    /* 38 counts between the two darks of one LED */
    gl_sim_grain_set(&g);
    GL_CHECK_EQ(gl_grain_fe_measure(&raw, 2), GL_OK);
    GL_CHECK(abs((int)raw.s[0][0].dark2 - (int)raw.s[0][0].dark1) > 30);
    GL_CHECK_EQ(gl_grain_process(&raw, &cal, &rd), GL_ERR_QUALITY);
    GL_CHECK(rd.reject & GL_GRAIN_REJECT_DARK_DRIFT);
    GL_CHECK(!(rd.reject & GL_GRAIN_REJECT_SATURATED));

    /* the motion verdict comes from the caller (IMU) */
    set_response_(&g, 0.4f, 60.0f);
    gl_sim_grain_set(&g);
    GL_CHECK_EQ(gl_grain_fe_measure(&raw, 2), GL_OK);
    raw.motion = true;
    GL_CHECK_EQ(gl_grain_process(&raw, &cal, &rd), GL_ERR_QUALITY);
    GL_CHECK(rd.reject & GL_GRAIN_REJECT_MOTION);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

GL_TEST(test_parameter_errors_and_model_checks)
{
    static gl_grain_raw_t raw;
    fresh_();
    GL_CHECK_EQ(gl_grain_fe_measure(NULL, 1), GL_ERR_PARAM);
    GL_CHECK_EQ(gl_grain_fe_measure(&raw, 0), GL_ERR_PARAM);
    GL_CHECK_EQ(gl_grain_fe_measure(&raw, GL_GRAIN_MAX_CYCLES + 1u), GL_ERR_PARAM);
    GL_CHECK_EQ(gl_grain_fe_measure_cycle(&raw, GL_GRAIN_MAX_CYCLES), GL_ERR_PARAM);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);

    /* measuring a cycle without powering the chain is reported by the HAL */
    GL_CHECK_EQ(gl_grain_fe_measure_cycle(&raw, 0), GL_ERR_STATE);
    GL_CHECK(gl_sim_violations()->analog >= 1u);
    GL_CHECK_EQ(gl_sim_grain_lit_mask(), 0u); /* LEDs off after the error */

    /* the checker this file relies on: two LEDs lit at once is caught */
    fresh_();
    gl_hal_gpio_write(cp_(0), true);
    gl_hal_gpio_mode(cp_(0), GL_PIN_MODE_OUTPUT_PP);
    gl_hal_gpio_write(cp_(1), false);
    gl_hal_gpio_mode(cp_(1), GL_PIN_MODE_OUTPUT_PP);
    GL_CHECK_EQ(gl_sim_violations()->analog, 0u);
    gl_hal_gpio_write(cp_(2), false);
    gl_hal_gpio_mode(cp_(2), GL_PIN_MODE_OUTPUT_PP); /* red 0 and red 1 both lit */
    GL_CHECK(gl_sim_violations()->analog >= 1u);
    printf("    first violation text: %s\n", gl_sim_violations()->first);
}

int main(void)
{
    GL_RUN(test_all_off_is_all_analog);
    GL_RUN(test_charlieplex_pin_states_for_each_led);
    GL_RUN(test_wiring_has_no_low_voltage_sneak_path);
    GL_RUN(test_measure_sequence_on_the_adc);
    GL_RUN(test_driver_data_through_core_processing);
    GL_RUN(test_parameter_errors_and_model_checks);
    return gl_test_summary();
}
