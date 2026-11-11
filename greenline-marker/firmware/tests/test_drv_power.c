/*
 * test_drv_power.c - battery measurement, the cell NTC, charger status and
 * the charge gate of rev C2 against the simulator: pin configuration (the
 * charger keeps its hardware default until a temperature is known), the
 * exact ADC and bias-pin sequence, the B-parameter conversion against a
 * table, open / short / stuck detection, the tolerance budget behind the
 * guard band, and the CHG_INHIBIT level for every combination of VBUS and
 * temperature (window, guard, hysteresis, plausibility).
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

/* True if any trace record since the last clear touches the pin. */
static bool pin_touched_(gl_pin_t pin)
{
    for (size_t i = 0; i < gl_sim_trace_count(); i++) {
        const gl_sim_trace_t *t = gl_sim_trace_at(i);
        if ((t->type == (uint8_t)GL_SIM_TR_GPIO_MODE || t->type == (uint8_t)GL_SIM_TR_GPIO_WRITE) &&
            t->a == (uint8_t)pin) {
            return true;
        }
    }
    return false;
}

GL_TEST(test_init_leaves_the_charger_in_its_hardware_default)
{
    /* in the cradle from the first instant: the charger runs with the MCU
     * in reset, and neither gl_hal_init() nor gl_power_init() stops it */
    gl_sim_reset(true);
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    GL_CHECK(gl_sim_charger_on());
    GL_CHECK(gl_sim_pin_level(GL_PIN_CHG_INHIBIT)); /* gate held up by its divider */
    gl_sim_advance_ms(20);
    (void)gl_hal_init();
    gl_power_init(&pw_);
    GL_CHECK(!pin_touched_(GL_PIN_CHG_INHIBIT));
    GL_CHECK(!pin_touched_(GL_PIN_NTC_BIAS));
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_CHG_INHIBIT), GL_PIN_MODE_ANALOG);
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_NTC_BIAS), GL_PIN_MODE_ANALOG);
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_NTC_SENSE), GL_PIN_MODE_ANALOG);
    GL_CHECK(!gl_sim_pin_drives_low(GL_PIN_CHG_INHIBIT) && !gl_sim_pin_drives_high(GL_PIN_CHG_INHIBIT));
    GL_CHECK(gl_sim_charger_on());
    GL_CHECK(pw_.vbus && pw_.charge_enabled && !pw_.inhibit);
    GL_CHECK_NEAR((double)gl_sim_stats()->chg_in_reset_us, 20000.0, 1.0);
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_CHG_STAT), GL_PIN_MODE_INPUT_PULLUP);
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_VBUS_SENSE), GL_PIN_MODE_INPUT);
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_VBAT_SENSE), GL_PIN_MODE_ANALOG);
    GL_CHECK_EQ(pw_.batt_mv, 0);
    GL_CHECK(!pw_.cell_temp_valid && !pw_.mcu_temp_valid);
    /* outside the cradle: nothing to charge with, nothing enabled */
    fresh_();
    GL_CHECK(!pw_.vbus && !pw_.charging && !pw_.charge_enabled && !pw_.inhibit);
    GL_CHECK(!gl_sim_charger_on());
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_NO_VBUS);
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

/* The B-parameter equation, written out here in double precision and
 * independently of the driver: resistance of the NTC at t, and the fraction
 * of full scale at the mid point of the divider. */
static double ntc_ohm_(double t_c)
{
    return 10000.0 * exp(3380.0 * (1.0 / (t_c + 273.15) - 1.0 / 298.15));
}

static double ntc_counts_(double t_c)
{
    const double r = ntc_ohm_(t_c);
    return 16383.0 * r / (r + 10000.0);
}

GL_TEST(test_ntc_conversion_against_a_table)
{
    /* anchor rows computed outside this program (Python, double precision):
     * temperature [C], NTC resistance [ohm], counts at the sense pin */
    static const struct {
        double t_c, ohm, counts;
    } table[] = {
        { -40.0, 235830.76, 15716.57 }, { -20.0, 75021.69, 14456.08 }, { -10.0, 45168.27, 13413.36 },
        { 0.0, 28223.73, 12096.92 },    { 5.0, 22594.95, 11356.76 },   { 10.0, 18231.40, 10579.89 },
        { 25.0, 10000.00, 8191.50 },    { 40.0, 5809.87, 6020.49 },    { 45.0, 4903.40, 5390.21 },
        { 50.0, 4160.14, 4813.20 },     { 60.0, 3039.19, 3818.57 },    { 85.0, 1496.90, 2133.07 },
    };
    double worst = 0.0, worst_at = 0.0, worst_model = 0.0;
    uint8_t fault = 99;

    GL_CHECK_NEAR(GL_PROV_NTC_R25_OHM, 10000.0, 1e-6);
    GL_CHECK_NEAR(GL_PROV_NTC_B_K, 3380.0, 1e-6);
    GL_CHECK_NEAR(GL_PROV_NTC_SERIES_OHM, 10000.0, 1e-6);
    for (size_t i = 0; i < GL_ARRAY_LEN(table); i++) {
        /* the table agrees with the formula written out above ... */
        GL_CHECK_NEAR(ntc_ohm_(table[i].t_c), table[i].ohm, 0.01);
        GL_CHECK_NEAR(ntc_counts_(table[i].t_c), table[i].counts, 0.01);
        /* ... with the simulator's model of the divider ... */
        GL_CHECK_NEAR(gl_sim_ntc_counts_at(table[i].t_c), table[i].counts, 0.01);
        /* ... and the driver turns the nearest count back into the temperature */
        {
            const uint16_t c = (uint16_t)(table[i].counts + 0.5);
            const double t = (double)gl_power_ntc_counts_to_c(c, &fault);
            GL_CHECK_EQ(fault, GL_NTC_OK);
            GL_CHECK_NEAR(t, table[i].t_c, 0.02);
        }
    }
    /* every half degree from -40 to +85 C */
    gl_sim_reset(true);
    for (int k = -80; k <= 170; k++) {
        const double t_true = 0.5 * (double)k;
        const double exact = ntc_counts_(t_true);
        const uint16_t c = (uint16_t)(exact + 0.5);
        const double t = (double)gl_power_ntc_counts_to_c(c, &fault);
        const double err = fabs(t - t_true);
        GL_CHECK_EQ(fault, GL_NTC_OK);
        if (err > worst) {
            worst = err;
            worst_at = t_true;
        }
        if (fabs(gl_sim_ntc_counts_at(t_true) - exact) > worst_model) {
            worst_model = fabs(gl_sim_ntc_counts_at(t_true) - exact);
        }
    }
    printf("    B-parameter conversion (single precision) against the table, -40..85 C in 0.5 C "
           "steps: worst error %.4f K at %.1f C (one count is 0.006 K at 25 C, 0.025 K at -40 C); "
           "simulator model within %.2g counts of the table\n", worst, worst_at, worst_model);
    GL_CHECK(worst < 0.02);
    GL_CHECK(worst_model < 1e-6);
    /* monotonic: more counts = colder */
    {
        float prev = gl_power_ntc_counts_to_c(400, NULL);
        for (unsigned c = 401; c < 16000u; c++) {
            const float t = gl_power_ntc_counts_to_c((uint16_t)c, NULL);
            GL_CHECK(t < prev);
            prev = t;
        }
    }
    /* outside the detection thresholds: a fault and not a number */
    GL_CHECK(isnan(gl_power_ntc_counts_to_c(GL_HAL_ADC_FULL_SCALE, &fault)));
    GL_CHECK_EQ(fault, GL_NTC_OPEN);
    GL_CHECK(isnan(gl_power_ntc_counts_to_c((uint16_t)(0.98 * 16383.0 + 1.0), &fault)));
    GL_CHECK_EQ(fault, GL_NTC_OPEN);
    GL_CHECK(isnan(gl_power_ntc_counts_to_c(0, &fault)));
    GL_CHECK_EQ(fault, GL_NTC_SHORT);
    GL_CHECK(isnan(gl_power_ntc_counts_to_c((uint16_t)(0.02 * 16383.0 - 1.0), &fault)));
    GL_CHECK_EQ(fault, GL_NTC_SHORT);
    GL_CHECK(isfinite(gl_power_ntc_counts_to_c((uint16_t)(0.97 * 16383.0), &fault)));
    GL_CHECK_EQ(fault, GL_NTC_OK);
    GL_CHECK(isfinite(gl_power_ntc_counts_to_c((uint16_t)(0.03 * 16383.0), &fault)));
    GL_CHECK_EQ(fault, GL_NTC_OK);
    /* the thresholds lie far outside anything a cell lives through */
    GL_CHECK(gl_power_ntc_counts_to_c((uint16_t)(0.97 * 16383.0), NULL) < -44.0f);
    GL_CHECK(gl_power_ntc_counts_to_c((uint16_t)(0.03 * 16383.0), NULL) > 130.0f);
}

/* The guard band of the charge window against the divider's tolerances:
 * the reading of every corner unit at the two limits. */
GL_TEST(test_ntc_tolerance_budget_is_inside_the_guard_band)
{
    static const double limit[2] = { (double)GL_PROV_CHARGE_TEMP_MIN_C, (double)GL_PROV_CHARGE_TEMP_MAX_C };
    double worst[2] = { 0.0, 0.0 }, parts[2] = { 0.0, 0.0 };

    gl_sim_reset(true);
    for (int k = 0; k < 2; k++) {
        for (int corner = 0; corner < 8; corner++) {
            const float a = (corner & 1) ? 0.01f : -0.01f;
            const float b = (corner & 2) ? 0.01f : -0.01f;
            const float c = (corner & 4) ? 0.01f : -0.01f;
            gl_sim_ntc_set_tolerance(a, b, c);
            for (int adc = -1; adc <= 1; adc++) {
                /* ADC error of 0.2 % of full scale, either way */
                const double counts = gl_sim_ntc_counts_at(limit[k]) + 0.002 * 16383.0 * (double)adc;
                const double err =
                    fabs((double)gl_power_ntc_counts_to_c((uint16_t)(counts + 0.5), NULL) - limit[k]);
                if (err > worst[k]) {
                    worst[k] = err;
                }
                if (adc == 0 && err > parts[k]) {
                    parts[k] = err;
                }
            }
        }
    }
    gl_sim_ntc_set_tolerance(0.0f, 0.0f, 0.0f);
    printf("    reading error of a worst-case unit (NTC 1 %%, B 1 %%, series resistor 1 %%): %.2f K "
           "at 0 C, %.2f K at 45 C; with an ADC error of 0.2 %% of full scale %.2f K and %.2f K; "
           "guard band %.1f K\n", parts[0], parts[1], worst[0], worst[1],
           (double)GL_PROV_CHARGE_TEMP_GUARD_C);
    GL_CHECK(worst[0] < (double)GL_PROV_CHARGE_TEMP_GUARD_C);
    GL_CHECK(worst[1] < (double)GL_PROV_CHARGE_TEMP_GUARD_C);
    GL_CHECK(worst[1] > 1.0); /* why the guard is not 1.0 K */
}

GL_TEST(test_measure_exact_adc_and_bias_sequence)
{
    static const uint16_t cells[] = { 4180, 3900, 3600, 3450, 3340, 3100 };
    fresh_();
    for (size_t i = 0; i < GL_ARRAY_LEN(cells); i++) {
        const uint64_t bias_before = gl_sim_stats()->ntc_bias_us;
        gl_sim_set_vbat_mv(cells[i]);
        gl_sim_trace_clear();
        GL_CHECK_EQ(gl_power_measure(&pw_), GL_OK);
        /* exactly: ADC on; the battery; the MCU die sensor; the sense pin
         * with the bias released; bias latch high, bias pin push-pull; the
         * NTC; bias pin analog, latch low; ADC off */
        GL_CHECK_EQ(gl_sim_trace_count(), 10);
        if (gl_sim_trace_count() == 10u) {
            const gl_sim_trace_t *t[10];
            for (unsigned k = 0; k < 10u; k++) {
                t[k] = gl_sim_trace_at(k);
            }
            GL_CHECK(t[0]->type == GL_SIM_TR_ADC_POWER && t[0]->a == 1u);
            GL_CHECK(t[1]->type == GL_SIM_TR_ADC_READ && t[1]->a == (uint8_t)GL_ADC_CH_VBAT_DIV);
            GL_CHECK(t[2]->type == GL_SIM_TR_ADC_READ && t[2]->a == (uint8_t)GL_ADC_CH_MCU_TEMP);
            GL_CHECK(t[3]->type == GL_SIM_TR_ADC_READ && t[3]->a == (uint8_t)GL_ADC_CH_CELL_NTC);
            GL_CHECK(t[3]->b <= 3u); /* bias released: the NTC holds the pin at ground */
            GL_CHECK(t[4]->type == GL_SIM_TR_GPIO_WRITE && t[4]->a == (uint8_t)GL_PIN_NTC_BIAS &&
                     t[4]->b == 1u);
            GL_CHECK(t[5]->type == GL_SIM_TR_GPIO_MODE && t[5]->a == (uint8_t)GL_PIN_NTC_BIAS &&
                     t[5]->b == (uint16_t)GL_PIN_MODE_OUTPUT_PP);
            GL_CHECK(t[6]->type == GL_SIM_TR_ADC_READ && t[6]->a == (uint8_t)GL_ADC_CH_CELL_NTC);
            GL_CHECK(t[6]->t_us - t[5]->t_us >= GL_PROV_NTC_SETTLE_US);
            GL_CHECK(t[7]->type == GL_SIM_TR_GPIO_MODE && t[7]->a == (uint8_t)GL_PIN_NTC_BIAS &&
                     t[7]->b == (uint16_t)GL_PIN_MODE_ANALOG);
            GL_CHECK(t[8]->type == GL_SIM_TR_GPIO_WRITE && t[8]->a == (uint8_t)GL_PIN_NTC_BIAS &&
                     t[8]->b == 0u);
            GL_CHECK(t[9]->type == GL_SIM_TR_ADC_POWER && t[9]->a == 0u);
        }
        /* the bias was driven for the settle time and one conversion only */
        {
            const uint64_t on = gl_sim_stats()->ntc_bias_us - bias_before;
            GL_CHECK(on >= GL_PROV_NTC_SETTLE_US && on < 1000u);
            if (i == 0u) {
                printf("    NTC_BIAS driven for %u us per measurement\n", (unsigned)on);
            }
        }
        GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_NTC_BIAS), GL_PIN_MODE_ANALOG);
        GL_CHECK_NEAR(pw_.batt_mv, cells[i], 3.0);
        GL_CHECK_EQ(pw_.percent, gl_power_percent(pw_.batt_mv));
        GL_CHECK_EQ(pw_.low, cells[i] < GL_PROV_BATT_LOW_MV);
        GL_CHECK_EQ(pw_.critical, cells[i] < GL_PROV_BATT_CRITICAL_MV);
        GL_CHECK_EQ(pw_.storage, cells[i] < GL_PROV_BATT_STORAGE_MV);
        GL_CHECK(pw_.mcu_temp_valid && pw_.cell_temp_valid);
        GL_CHECK_EQ(pw_.ntc_fault, GL_NTC_OK);
    }
    /* the temperatures only: no battery conversion */
    gl_sim_trace_clear();
    GL_CHECK_EQ(gl_power_measure_temps(&pw_), GL_OK);
    GL_CHECK_EQ(gl_sim_trace_count(), 9);
    GL_CHECK(tr_find(0, GL_SIM_TR_ADC_READ, (int)GL_ADC_CH_VBAT_DIV) < 0);
    /* the MCU die temperature and the cell temperature: each follows its own
     * sensor, at any VDDA (the NTC divider is ratiometric) */
    {
        static const float temps[] = { -10.0f, 0.0f, 25.0f, 45.0f, 60.0f };
        for (size_t i = 0; i < GL_ARRAY_LEN(temps); i++) {
            gl_sim_set_mcu_temperature(temps[i]);
            gl_sim_set_cell_temperature(temps[GL_ARRAY_LEN(temps) - 1u - i]);
            gl_sim_set_vdda_mv((uint16_t)(2700u + 40u * (unsigned)i));
            GL_CHECK_EQ(gl_power_measure(&pw_), GL_OK);
            GL_CHECK(pw_.mcu_temp_valid && pw_.cell_temp_valid);
            GL_CHECK_NEAR(pw_.mcu_temp_c, temps[i], 0.3);
            GL_CHECK_NEAR(pw_.cell_temp_c, temps[GL_ARRAY_LEN(temps) - 1u - i], 0.05);
        }
        gl_sim_set_vdda_mv(2800);
    }
    /* the reading follows VDDA (measured through VREFINT), so a sagging
     * 2.8 V rail does not falsify the battery voltage */
    gl_sim_set_vbat_mv(3700);
    gl_sim_set_vdda_mv(2710);
    GL_CHECK_EQ(gl_power_measure(&pw_), GL_OK);
    GL_CHECK_NEAR(pw_.batt_mv, 3700.0, 3.0);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

GL_TEST(test_ntc_open_short_and_stuck_are_detected)
{
    fresh_();
    gl_sim_set_cell_temperature(22.0f);
    GL_CHECK_EQ(gl_power_measure_temps(&pw_), GL_OK);
    GL_CHECK(pw_.cell_temp_valid);
    GL_CHECK_EQ(pw_.ntc_fault, GL_NTC_OK);
    GL_CHECK_NEAR(pw_.cell_temp_c, 22.0, 0.05);

    gl_sim_ntc_set_fault(GL_SIM_NTC_OPEN); /* broken off: the pin follows the bias */
    GL_CHECK_EQ(gl_power_measure_temps(&pw_), GL_OK);
    GL_CHECK(!pw_.cell_temp_valid);
    GL_CHECK_EQ(pw_.ntc_fault, GL_NTC_OPEN);

    gl_sim_ntc_set_fault(GL_SIM_NTC_SHORT);
    GL_CHECK_EQ(gl_power_measure_temps(&pw_), GL_OK);
    GL_CHECK(!pw_.cell_temp_valid);
    GL_CHECK_EQ(pw_.ntc_fault, GL_NTC_SHORT);

    gl_sim_ntc_set_fault(GL_SIM_NTC_STUCK_HIGH); /* bridged to the rail: reads as open */
    GL_CHECK_EQ(gl_power_measure_temps(&pw_), GL_OK);
    GL_CHECK(!pw_.cell_temp_valid);
    GL_CHECK_EQ(pw_.ntc_fault, GL_NTC_OPEN);

    gl_sim_ntc_set_fault(GL_SIM_NTC_NORMAL);
    GL_CHECK_EQ(gl_power_measure_temps(&pw_), GL_OK);
    GL_CHECK(pw_.cell_temp_valid);
    GL_CHECK_EQ(pw_.ntc_fault, GL_NTC_OK);
    /* whatever was found, the bias is released again and nothing was left on */
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_NTC_BIAS), GL_PIN_MODE_ANALOG);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
    /* a conversion right after the bias is switched on is caught by the
     * model (the driver waits GL_PROV_NTC_SETTLE_US) */
    {
        uint16_t counts = 0;
        (void)gl_hal_adc_power(true);
        gl_hal_gpio_write(GL_PIN_NTC_BIAS, true);
        gl_hal_gpio_mode(GL_PIN_NTC_BIAS, GL_PIN_MODE_OUTPUT_PP);
        gl_hal_delay_us(30);
        GL_CHECK_EQ(gl_hal_adc_read(GL_ADC_CH_CELL_NTC, 1, 5, &counts), GL_OK);
        GL_CHECK_EQ(gl_sim_violations()->analog, 1u);
        GL_CHECK((double)counts < 0.6 * ntc_counts_(22.0)); /* and it reads low */
        /* and so is a bias pin left on into Stop mode */
        (void)gl_hal_adc_power(false);
        gl_hal_wake_timer_start(5);
        gl_hal_irq_enable(GL_IRQ_WAKE_TIMER, true);
        (void)gl_hal_sleep(GL_SLEEP_STOP);
        GL_CHECK_EQ(gl_sim_violations()->analog, 2u);
    }
}

/* What a gate call must leave on the pin. */
static void expect_gate_(bool allowed)
{
    GL_CHECK_EQ(pw_.charge_enabled, allowed);
    GL_CHECK_EQ(pw_.inhibit, pw_.vbus && !allowed);
    if (pw_.vbus && !allowed) {
        /* pulled LOW through an open-drain output */
        GL_CHECK(gl_sim_pin_drives_low(GL_PIN_CHG_INHIBIT));
        GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_CHG_INHIBIT), GL_PIN_MODE_OUTPUT_OD);
    } else {
        /* released: back to the reset state of the pin */
        GL_CHECK(!gl_sim_pin_drives_low(GL_PIN_CHG_INHIBIT));
        GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_CHG_INHIBIT), GL_PIN_MODE_ANALOG);
    }
    GL_CHECK(!gl_sim_pin_drives_high(GL_PIN_CHG_INHIBIT)); /* never */
    GL_CHECK_EQ(gl_sim_charger_on(), pw_.vbus && allowed);
}

/* A gate call with the NTC at t and both die sensors agreeing with it. */
static bool gate_at_(float t)
{
    pw_.cell_temp_c = t;
    pw_.cell_temp_valid = true;
    pw_.ntc_fault = (uint8_t)GL_NTC_OK;
    pw_.mcu_temp_c = t;
    pw_.mcu_temp_valid = true;
    return gl_power_charge_gate(&pw_, true, t, true, true);
}

GL_TEST(test_charge_gate_window_guard_and_hysteresis)
{
    const float lo = GL_PROV_CHARGE_TEMP_MIN_C + GL_PROV_CHARGE_TEMP_GUARD_C;
    const float hi = GL_PROV_CHARGE_TEMP_MAX_C - GL_PROV_CHARGE_TEMP_GUARD_C;
    const float hy = GL_PROV_CHARGE_TEMP_HYST_C;

    fresh_();
    /* no VBUS: nothing is inhibited, whatever the temperature */
    GL_CHECK(!gate_at_(25.0f));
    expect_gate_(false);
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_NO_VBUS);
    GL_CHECK(!gate_at_(70.0f));
    GL_CHECK(!gl_sim_pin_drives_low(GL_PIN_CHG_INHIBIT));
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_NO_VBUS);

    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    gl_power_poll_pins(&pw_);
    gl_sim_trace_clear();
    GL_CHECK(gate_at_(25.0f));
    expect_gate_(true);
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_ALLOWED);
    /* the pin: on the way to "stop" the latch goes low BEFORE the pin
     * becomes an output; on the way back it is released before it goes
     * analog (never a push-pull or a driven-high moment) */
    GL_CHECK(!gate_at_(60.0f));
    expect_gate_(false);
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_TOO_HOT);
    {
        const size_t n = gl_sim_trace_count();
        const gl_sim_trace_t *w = gl_sim_trace_at(n - 2u), *m = gl_sim_trace_at(n - 1u);
        GL_CHECK(w->type == GL_SIM_TR_GPIO_WRITE && w->a == (uint8_t)GL_PIN_CHG_INHIBIT && w->b == 0u);
        GL_CHECK(m->type == GL_SIM_TR_GPIO_MODE && m->a == (uint8_t)GL_PIN_CHG_INHIBIT &&
                 m->b == (uint16_t)GL_PIN_MODE_OUTPUT_OD);
    }
    /* upper limit: stays stopped until hi - hysteresis */
    GL_CHECK(!gate_at_(hi - 0.1f));
    GL_CHECK(!gate_at_(hi - hy + 0.1f));
    GL_CHECK(gate_at_(hi - hy - 0.1f));
    expect_gate_(true);
    /* once allowed it stays allowed up to the guarded limit itself */
    GL_CHECK(gate_at_(hi - 0.1f));
    GL_CHECK(!gate_at_(hi + 0.1f));
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_TOO_HOT);
    /* the guard: a reading of 44 C is "too hot" (the true cell may be at 45) */
    GL_CHECK(hi < GL_PROV_CHARGE_TEMP_MAX_C && lo > GL_PROV_CHARGE_TEMP_MIN_C);
    /* lower limit */
    GL_CHECK(gate_at_(20.0f));
    GL_CHECK(gate_at_(lo + 0.1f));
    GL_CHECK(!gate_at_(lo - 0.1f));
    expect_gate_(false);
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_TOO_COLD);
    GL_CHECK(!gate_at_(lo + hy - 0.1f));
    GL_CHECK(gate_at_(lo + hy + 0.1f));
    expect_gate_(true);
    /* not a number, infinite */
    GL_CHECK(!gate_at_(NAN));
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_TEMP_UNKNOWN);
    expect_gate_(false);
    GL_CHECK(!gate_at_(INFINITY));
    GL_CHECK(gate_at_(25.0f));
    /* a release resets the hysteresis: the next evaluation must be well
     * inside the window again */
    GL_CHECK(gate_at_(hi - 0.5f));
    gl_power_charge_release(&pw_);
    expect_gate_(true); /* the hardware default: VBUS present, pin released */
    GL_CHECK(!gate_at_(hi - 0.5f));
    GL_CHECK(gate_at_(hi - hy - 0.5f));
    /* VBUS removed: the pin is released by the gate itself */
    GL_CHECK(!gate_at_(60.0f));
    expect_gate_(false);
    GL_CHECK(gl_sim_pin_drives_low(GL_PIN_CHG_INHIBIT));
    gl_sim_set_input(GL_PIN_VBUS_SENSE, false);
    gl_power_poll_pins(&pw_);
    GL_CHECK(!gate_at_(60.0f));
    GL_CHECK(!gl_sim_pin_drives_low(GL_PIN_CHG_INHIBIT));
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_CHG_INHIBIT), GL_PIN_MODE_ANALOG);
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_NO_VBUS);

    /* full sweep both ways against an independent model of the rule */
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    gl_power_poll_pins(&pw_);
    gl_power_charge_release(&pw_);
    {
        bool model = false;
        unsigned on_up = 0, on_down = 0;
        for (int pass = 0; pass < 2; pass++) {
            for (int k = 0; k <= 700; k++) {
                const float t = (pass == 0) ? (-10.0f + 0.1f * (float)k) : (60.0f - 0.1f * (float)k);
                model = model ? (t >= lo && t <= hi) : (t >= lo + hy && t <= hi - hy);
                GL_CHECK_EQ(gate_at_(t), model);
                GL_CHECK_EQ(gl_sim_pin_drives_low(GL_PIN_CHG_INHIBIT), !model);
                if (model) {
                    if (pass == 0) {
                        on_up++;
                    } else {
                        on_down++;
                    }
                }
            }
        }
        printf("    charge gate over a sweep of -10..60 C and back: allowed for %.1f K going up "
               "(%.1f..%.1f C), %.1f K going down (%.1f..%.1f C)\n", 0.1 * (double)on_up,
               (double)(lo + hy), (double)hi, 0.1 * (double)on_down, (double)lo, (double)(hi - hy));
        GL_CHECK(on_up > 300u && on_down > 300u);
    }
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

GL_TEST(test_charge_gate_unknown_faulty_and_implausible_temperatures)
{
    fresh_();
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    gl_power_poll_pins(&pw_);
    GL_CHECK(gate_at_(25.0f));
    /* the NTC reading is stale */
    GL_CHECK(!gl_power_charge_gate(&pw_, false, 25.0f, true, true));
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_TEMP_UNKNOWN);
    expect_gate_(false);
    GL_CHECK(gate_at_(25.0f));
    /* NTC faults */
    for (int f = (int)GL_NTC_OPEN; f <= (int)GL_NTC_STUCK; f++) {
        pw_.ntc_fault = (uint8_t)f;
        pw_.cell_temp_valid = false;
        GL_CHECK(!gl_power_charge_gate(&pw_, true, 25.0f, true, true));
        GL_CHECK_EQ(pw_.chg_reason, GL_CHG_NTC_FAULT);
        expect_gate_(false);
    }
    pw_.ntc_fault = (uint8_t)GL_NTC_ADC;
    GL_CHECK(!gl_power_charge_gate(&pw_, true, 25.0f, true, true));
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_TEMP_UNKNOWN);
    GL_CHECK(gate_at_(25.0f));
    /* plausibility: the NTC against the die sensors */
    pw_.cell_temp_c = 25.0f;
    pw_.mcu_temp_c = 25.0f + GL_PROV_CHARGE_TEMP_MAX_DISAGREE_C - 0.5f;
    GL_CHECK(gl_power_charge_gate(&pw_, true, 0.0f, false, true)); /* IMU dead, MCU agrees */
    pw_.mcu_temp_c = 25.0f + GL_PROV_CHARGE_TEMP_MAX_DISAGREE_C + 0.5f;
    GL_CHECK(!gl_power_charge_gate(&pw_, true, 0.0f, false, true)); /* the only one disagrees */
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_IMPLAUSIBLE);
    expect_gate_(false);
    GL_CHECK(gl_power_charge_gate(&pw_, true, 24.0f, true, true)); /* the IMU vouches for it */
    GL_CHECK(!gl_power_charge_gate(&pw_, true, 50.0f, true, true)); /* both disagree */
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_IMPLAUSIBLE);
    /* an NTC that reads a comfortable 25 C on a board that is at 50 C */
    pw_.mcu_temp_c = 50.0f;
    GL_CHECK(!gl_power_charge_gate(&pw_, true, 49.0f, true, true));
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_IMPLAUSIBLE);
    /* no die sensor at all: nothing to check the NTC against */
    pw_.mcu_temp_c = 25.0f;
    pw_.mcu_temp_valid = false;
    GL_CHECK(!gl_power_charge_gate(&pw_, true, 25.0f, false, true));
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_TEMP_UNKNOWN);
    pw_.mcu_temp_valid = true;
    GL_CHECK(!gl_power_charge_gate(&pw_, true, 25.0f, false, false)); /* MCU reading stale */
    GL_CHECK(!gl_power_charge_gate(&pw_, true, NAN, true, false));
    GL_CHECK(gl_power_charge_gate(&pw_, true, 25.0f, false, true));
    /* a die sensor cannot make an out-of-window cell acceptable */
    pw_.cell_temp_c = 50.0f;
    pw_.mcu_temp_c = 25.0f;
    GL_CHECK(!gl_power_charge_gate(&pw_, true, 50.0f, true, true));
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_TOO_HOT);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* The charger model and its rules: what the simulator counts. */
GL_TEST(test_charger_model_and_rules)
{
    fresh_();
    gl_sim_set_cell_temperature(50.0f);
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    gl_power_poll_pins(&pw_);
    /* the charger started by itself; the measurement stops it */
    GL_CHECK(gl_sim_charger_on());
    gl_sim_advance_ms(3);
    GL_CHECK_EQ(gl_power_measure_temps(&pw_), GL_OK);
    GL_CHECK(!gl_power_charge_gate(&pw_, true, 50.0f, true, true));
    GL_CHECK(!gl_sim_charger_on());
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_TOO_HOT);
    {
        const gl_sim_stats_t *st = gl_sim_stats();
        GL_CHECK(st->chg_outside_us >= 3000u && st->chg_outside_us < 6000u);
        GL_CHECK_EQ(st->chg_outside_longest_us, st->chg_outside_us);
    }
    for (int k = 0; k < 6; k++) {
        gl_sim_advance_ms(10000);
        gl_hal_watchdog_kick();
    }
    GL_CHECK(gl_sim_stats()->chg_outside_us < 6000u); /* inhibited: nothing added */
    GL_CHECK(gl_sim_stats()->inhibit_us >= 60000000u);
    if (gl_sim_violation_total() != 0u) {
        printf("    first violation: %s\n", gl_sim_violations()->first);
    }
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
    /* rule: charging on outside the window for longer than the limit */
    gl_power_charge_release(&pw_);
    gl_sim_advance_ms(GL_SIM_CHG_REACT_MAX_MS + 100u);
    GL_CHECK_EQ(gl_sim_violations()->power, 1u);
    GL_CHECK(strstr(gl_sim_violations()->first, "charging for") != NULL);
    /* rule: CHG_INHIBIT may only pull low */
    gl_hal_gpio_write(GL_PIN_CHG_INHIBIT, false);
    gl_hal_gpio_mode(GL_PIN_CHG_INHIBIT, GL_PIN_MODE_OUTPUT_PP);
    GL_CHECK_EQ(gl_sim_violations()->power, 2u);
    gl_hal_gpio_mode(GL_PIN_CHG_INHIBIT, GL_PIN_MODE_OUTPUT_OD);
    /* rule: Stop mode with the pin low and VBUS gone */
    gl_sim_set_input(GL_PIN_VBUS_SENSE, false);
    gl_hal_irq_enable(GL_IRQ_WAKE_TIMER, true);
    gl_hal_wake_timer_start(5);
    (void)gl_hal_sleep(GL_SLEEP_STOP);
    GL_CHECK_EQ(gl_sim_violations()->power, 3u);
    /* the driver's own way out of that state is clean */
    gl_power_poll_pins(&pw_);
    (void)gl_power_charge_gate(&pw_, true, 25.0f, true, true);
    (void)gl_hal_irq_take();
    gl_hal_wake_timer_start(5);
    (void)gl_hal_sleep(GL_SLEEP_STOP);
    GL_CHECK_EQ(gl_sim_violations()->power, 3u);
    /* rule: Stop mode in the cradle without a wake-up soon enough */
    gl_sim_set_cell_temperature(22.0f);
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    (void)gl_hal_irq_take();
    gl_hal_wake_timer_start(GL_SIM_CHG_SUPERVISE_MAX_MS + 2000u);
    (void)gl_hal_sleep(GL_SLEEP_STOP);
    GL_CHECK_EQ(gl_sim_violations()->power, 4u);
    (void)gl_hal_irq_take();
    gl_hal_wake_timer_start(GL_SIM_CHG_SUPERVISE_MAX_MS - 2000u);
    (void)gl_hal_sleep(GL_SLEEP_STOP);
    GL_CHECK_EQ(gl_sim_violations()->power, 4u);
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

int main(void)
{
    GL_RUN(test_init_leaves_the_charger_in_its_hardware_default);
    GL_RUN(test_conversion_and_percent);
    GL_RUN(test_ntc_conversion_against_a_table);
    GL_RUN(test_ntc_tolerance_budget_is_inside_the_guard_band);
    GL_RUN(test_measure_exact_adc_and_bias_sequence);
    GL_RUN(test_ntc_open_short_and_stuck_are_detected);
    GL_RUN(test_charge_gate_window_guard_and_hysteresis);
    GL_RUN(test_charge_gate_unknown_faulty_and_implausible_temperatures);
    GL_RUN(test_charger_model_and_rules);
    GL_RUN(test_status_pins_and_interrupts);
    return gl_test_summary();
}
