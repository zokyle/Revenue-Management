/*
 * test_drv_power.c - battery measurement, charger status and the charge
 * gate against the simulator: pin configuration, the exact ADC sequence,
 * conversion to millivolts, thresholds, and the PROG-enable pin level for
 * every combination of VBUS and temperature (0-45 C window with
 * hysteresis).
 */
#include "gl_test.h"

#include "gl_provisional.h"
#include "gl_trace_util.h"
#include "power.h"

static gl_power_t pw_;

static void fresh_(void)
{
    gl_sim_reset(true);
    (void)gl_hal_init();
    gl_power_init(&pw_);
}

GL_TEST(test_init_pin_configuration)
{
    fresh_();
    /* PROG enable: open drain, released (charging stopped) */
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_CHG_PROG_EN), GL_PIN_MODE_OUTPUT_OD);
    GL_CHECK(gl_sim_pin_latch(GL_PIN_CHG_PROG_EN));
    GL_CHECK(!gl_sim_pin_drives_low(GL_PIN_CHG_PROG_EN));
    /* it is never driven HIGH: an open-drain pin cannot */
    GL_CHECK(!gl_sim_pin_drives_high(GL_PIN_CHG_PROG_EN));
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_CHG_STAT), GL_PIN_MODE_INPUT_PULLUP);
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_VBUS_SENSE), GL_PIN_MODE_INPUT);
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_VBAT_SENSE), GL_PIN_MODE_ANALOG);
    GL_CHECK(!pw_.vbus && !pw_.charging && !pw_.charge_enabled);
    GL_CHECK_EQ(pw_.batt_mv, 0);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

GL_TEST(test_conversion_and_percent)
{
    /* half of full scale at VDDA 2.8 V behind the 1:2 divider = 2.8 V */
    GL_CHECK_NEAR(gl_power_counts_to_mv(8192, 2800), 2800.0, 1.0);
    GL_CHECK_EQ(gl_power_counts_to_mv(0, 2800), 0);
    GL_CHECK_NEAR(gl_power_counts_to_mv(GL_HAL_ADC_FULL_SCALE, 2800), 5600.0, 1.0);
    /* 3.9 V cell: 1.95 V at the pin */
    GL_CHECK_NEAR(gl_power_counts_to_mv((uint16_t)(1950.0 / 2800.0 * 16383.0 + 0.5), 2800), 3900.0,
                  1.0);
    GL_CHECK_EQ(gl_power_percent(0), 0);
    GL_CHECK_EQ(gl_power_percent((uint16_t)GL_PROV_BATT_EMPTY_MV), 0);
    GL_CHECK_EQ(gl_power_percent((uint16_t)GL_PROV_BATT_FULL_MV), 100);
    GL_CHECK_EQ(gl_power_percent(5000), 100);
    GL_CHECK_EQ(gl_power_percent((uint16_t)((GL_PROV_BATT_EMPTY_MV + GL_PROV_BATT_FULL_MV) / 2u)), 50);
    for (unsigned mv = 3000; mv < 4300u; mv += 7u) {
        GL_CHECK(gl_power_percent((uint16_t)mv) <= gl_power_percent((uint16_t)(mv + 7u)));
    }
}

GL_TEST(test_measure_exact_adc_sequence)
{
    static const uint16_t cells[] = { 4180, 3900, 3600, 3450, 3340, 3100 };
    fresh_();
    for (size_t i = 0; i < GL_ARRAY_LEN(cells); i++) {
        gl_sim_set_vbat_mv(cells[i]);
        gl_sim_trace_clear();
        GL_CHECK_EQ(gl_power_measure(&pw_), GL_OK);
        /* exactly: ADC on, ONE conversion of the battery channel, ADC off */
        GL_CHECK_EQ(gl_sim_trace_count(), 3);
        if (gl_sim_trace_count() == 3u) {
            const gl_sim_trace_t *t0 = gl_sim_trace_at(0), *t1 = gl_sim_trace_at(1);
            const gl_sim_trace_t *t2 = gl_sim_trace_at(2);
            GL_CHECK(t0->type == GL_SIM_TR_ADC_POWER && t0->a == 1u);
            GL_CHECK(t1->type == GL_SIM_TR_ADC_READ && t1->a == (uint8_t)GL_ADC_CH_VBAT_DIV);
            GL_CHECK(t2->type == GL_SIM_TR_ADC_POWER && t2->a == 0u);
        }
        GL_CHECK_NEAR(pw_.batt_mv, cells[i], 3.0);
        GL_CHECK_EQ(pw_.percent, gl_power_percent(pw_.batt_mv));
        GL_CHECK_EQ(pw_.low, cells[i] < GL_PROV_BATT_LOW_MV);
        GL_CHECK_EQ(pw_.critical, cells[i] < GL_PROV_BATT_CRITICAL_MV);
    }
    /* the reading follows VDDA (measured through VREFINT), so a sagging
     * 2.8 V rail does not falsify the battery voltage */
    gl_sim_set_vbat_mv(3700);
    gl_sim_set_vdda_mv(2710);
    GL_CHECK_EQ(gl_power_measure(&pw_), GL_OK);
    GL_CHECK_NEAR(pw_.batt_mv, 3700.0, 3.0);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

GL_TEST(test_status_pins_and_interrupts)
{
    fresh_();
    gl_hal_irq_enable(GL_IRQ_VBUS_CHANGE | GL_IRQ_CHG_STAT, true);
    GL_CHECK_EQ(gl_hal_irq_take(), 0u);
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    GL_CHECK_EQ(gl_hal_irq_take(), GL_IRQ_VBUS_CHANGE);
    gl_power_poll_pins(&pw_);
    GL_CHECK(pw_.vbus && !pw_.charging);
    gl_sim_set_input(GL_PIN_CHG_STAT, false); /* STAT pulled low: charging */
    GL_CHECK_EQ(gl_hal_irq_take(), GL_IRQ_CHG_STAT);
    gl_power_poll_pins(&pw_);
    GL_CHECK(pw_.vbus && pw_.charging);
    gl_sim_set_input(GL_PIN_CHG_STAT, true);
    gl_sim_set_input(GL_PIN_VBUS_SENSE, false);
    GL_CHECK_EQ(gl_hal_irq_take(), GL_IRQ_VBUS_CHANGE | GL_IRQ_CHG_STAT);
    gl_power_poll_pins(&pw_);
    GL_CHECK(!pw_.vbus && !pw_.charging);
}

/* PROG enable level expected after a gate call. */
static void expect_gate_(bool enabled)
{
    GL_CHECK_EQ(pw_.charge_enabled, enabled);
    if (enabled) {
        GL_CHECK(gl_sim_pin_drives_low(GL_PIN_CHG_PROG_EN)); /* LOW = charging allowed */
    } else {
        GL_CHECK(!gl_sim_pin_drives_low(GL_PIN_CHG_PROG_EN)); /* released */
        GL_CHECK(gl_sim_pin_latch(GL_PIN_CHG_PROG_EN));
    }
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_CHG_PROG_EN), GL_PIN_MODE_OUTPUT_OD);
}

GL_TEST(test_charge_gate_window_and_hysteresis)
{
    fresh_();
    /* no VBUS: never enabled, whatever the temperature */
    GL_CHECK(!gl_power_charge_gate(&pw_, 25.0f, true));
    expect_gate_(false);

    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    gl_power_poll_pins(&pw_);
    /* exact pin traffic of one gate call: a single write of the PROG pin */
    gl_sim_trace_clear();
    GL_CHECK(gl_power_charge_gate(&pw_, 25.0f, true));
    GL_CHECK_EQ(gl_sim_trace_count(), 1);
    {
        const gl_sim_trace_t *t = gl_sim_trace_at(0);
        GL_CHECK(t != NULL && t->type == GL_SIM_TR_GPIO_WRITE &&
                 t->a == (uint8_t)GL_PIN_CHG_PROG_EN && t->b == 0u);
    }
    expect_gate_(true);

    /* hot side: stays on up to 45.0 C, off above; back on only at <= 43 C */
    GL_CHECK(gl_power_charge_gate(&pw_, 44.9f, true));
    GL_CHECK(gl_power_charge_gate(&pw_, 45.0f, true));
    expect_gate_(true);
    GL_CHECK(!gl_power_charge_gate(&pw_, 45.1f, true));
    expect_gate_(false);
    GL_CHECK(!gl_power_charge_gate(&pw_, 44.0f, true));
    GL_CHECK(!gl_power_charge_gate(&pw_, 43.1f, true));
    expect_gate_(false);
    GL_CHECK(gl_power_charge_gate(&pw_, 43.0f, true));
    expect_gate_(true);

    /* cold side: off below 0 C, back on only at >= 2 C */
    GL_CHECK(gl_power_charge_gate(&pw_, 0.0f, true));
    GL_CHECK(!gl_power_charge_gate(&pw_, -0.1f, true));
    expect_gate_(false);
    GL_CHECK(!gl_power_charge_gate(&pw_, 1.9f, true));
    GL_CHECK(gl_power_charge_gate(&pw_, 2.0f, true));
    expect_gate_(true);

    /* temperature unknown (IMU not readable): stop */
    GL_CHECK(!gl_power_charge_gate(&pw_, 25.0f, false));
    expect_gate_(false);
    /* and a first valid reading at the edge of the window does not start it */
    GL_CHECK(!gl_power_charge_gate(&pw_, 44.5f, true));
    GL_CHECK(gl_power_charge_gate(&pw_, 30.0f, true));
    expect_gate_(true);

    /* VBUS removed: released at the next gate call */
    gl_sim_set_input(GL_PIN_VBUS_SENSE, false);
    gl_power_poll_pins(&pw_);
    GL_CHECK(!gl_power_charge_gate(&pw_, 30.0f, true));
    expect_gate_(false);

    /* sweep: the pin is low exactly when VBUS is present and the gate says so */
    {
        unsigned on = 0, off = 0;
        for (int vb = 0; vb < 2; vb++) {
            gl_sim_set_input(GL_PIN_VBUS_SENSE, vb != 0);
            gl_power_poll_pins(&pw_);
            for (int t = -200; t <= 600; t += 5) {
                const bool en = gl_power_charge_gate(&pw_, (float)t * 0.1f, true);
                GL_CHECK_EQ(gl_sim_pin_drives_low(GL_PIN_CHG_PROG_EN), en);
                if (en) {
                    GL_CHECK(vb != 0 && t >= 0 && t <= 450);
                    on++;
                } else {
                    off++;
                }
            }
        }
        GL_CHECK(on > 50u && off > 150u);
    }
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

int main(void)
{
    GL_RUN(test_init_pin_configuration);
    GL_RUN(test_conversion_and_percent);
    GL_RUN(test_measure_exact_adc_sequence);
    GL_RUN(test_status_pins_and_interrupts);
    GL_RUN(test_charge_gate_window_and_hysteresis);
    return gl_test_summary();
}
