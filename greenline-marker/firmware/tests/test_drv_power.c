/*
 * test_drv_power.c - battery measurement, the MCU's cell thermistor (NTC2),
 * the charger of the rev E board (BQ25101, DESIGN_SPEC E1) and the
 * firmware's supervision of it, against the simulator: pin configuration
 * (the charger keeps its hardware default; CHG_INHIBIT is driven only to
 * stop it), the exact ADC and bias-pin sequence, the B-parameter conversion
 * against a table, open / short / stuck detection, the error budget of a
 * reading at the charge limits and at the read limit of E13, the level of
 * CHG_INHIBIT for every combination of VBUS and temperature (window, guard,
 * hysteresis, plausibility), the 6 h limit of E32, the stop by command, what
 * the firmware infers from the charger's one status output, and the read
 * gate of E13.
 *
 * THE CHARGER ITSELF IS A MODEL (hal/host/gl_sim_core.c): its temperature
 * zones, its termination, its timer and its status output are this project's
 * reading of the part, every threshold PROVISIONAL (core/gl_provisional.h,
 * GL_PROV_BQ25101_*).  The last tests of this file show what THAT MODEL does
 * with no firmware at all.  They prove nothing about the chip.
 */
#include "gl_test.h"

#include "gl_pins.h"
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
    GL_CHECK(!gl_sim_pin_level(GL_PIN_CHG_INHIBIT)); /* the gate of the stop MOSFET: held off */
    GL_CHECK(!gl_sim_pin_level(GL_PIN_CHG_STAT));    /* the charger pulls its status output low */
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
    GL_CHECK(pw_.vbus && pw_.charge_enabled && !pw_.inhibit && pw_.charging);
    GL_CHECK_EQ(pw_.chg_status, GL_CHGST_CHARGING);
    GL_CHECK_NEAR((double)gl_sim_stats()->chg_in_reset_us, 20000.0, 1.0);
    /* inputs WITHOUT an internal pull: CHG_STAT has the board's pull-up (and
     * is a USB Type-C CC pad), VBUS_SENSE its divider */
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_CHG_STAT), GL_PIN_MODE_INPUT);
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_VBUS_SENSE), GL_PIN_MODE_INPUT);
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_VBAT_SENSE), GL_PIN_MODE_ANALOG);
    GL_CHECK_EQ(pw_.batt_mv, 0);
    GL_CHECK(!pw_.cell_temp_valid && !pw_.mcu_temp_valid);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
    /* outside the cradle: nothing to charge with, nothing enabled */
    fresh_();
    GL_CHECK(!pw_.vbus && !pw_.charging && !pw_.charge_enabled && !pw_.inhibit);
    GL_CHECK(!gl_sim_charger_on());
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_NO_VBUS);
    GL_CHECK_EQ(pw_.chg_status, GL_CHGST_NO_INPUT);
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
    /* anchor rows computed outside this program, in double precision, FROM
     * THE B EQUATION R = 10 kohm * exp(3380 K * (1/T - 1/298.15 K)) and from
     * nothing else: no R-T table of the Murata NCU15XH103F60RC has been read
     * (PROVISIONAL).  Temperature [C], NTC resistance [ohm], counts at the
     * sense pin.  (The command: python3 -c "import math; r=lambda t:
     * 10000*math.exp(3380*(1/(t+273.15)-1/298.15)); ..." - the README quotes
     * its output.) */
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

/* The error budget of a reading: every corner unit (NTC 1 %, B 1 %, series
 * resistor 1 %), with and without an ADC error of 0.2 % of full scale, at
 * the two limits of the firmware's charge window and at the read limit of
 * E13.  The guard band of the charge window must cover the first two; the
 * read limit is applied to the reading itself, so its figure is REPORTED. */
GL_TEST(test_ntc_error_budget_at_the_limits)
{
    static const double limit[3] = { (double)GL_PROV_CHARGE_TEMP_MIN_C, (double)GL_PROV_CHARGE_TEMP_MAX_C,
                                     (double)GL_PROV_READ_TEMP_MAX_C };
    double worst[3] = { 0.0, 0.0, 0.0 }, parts[3] = { 0.0, 0.0, 0.0 };

    gl_sim_reset(true);
    for (int k = 0; k < 3; k++) {
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
           "at 0 C, %.2f K at 45 C, %.2f K at 60 C; with an ADC error of 0.2 %% of full scale %.2f K, "
           "%.2f K and %.2f K; guard band of the charge window %.1f K; hysteresis of the read gate "
           "%.1f K\n", parts[0], parts[1], parts[2], worst[0], worst[1], worst[2],
           (double)GL_PROV_CHARGE_TEMP_GUARD_C, (double)GL_PROV_READ_TEMP_HYST_C);
    GL_CHECK(worst[0] < (double)GL_PROV_CHARGE_TEMP_GUARD_C);
    GL_CHECK(worst[1] < (double)GL_PROV_CHARGE_TEMP_GUARD_C);
    GL_CHECK(worst[1] > 1.0); /* why the guard is not 1.0 K */
    /* E13: the hysteresis of the read gate is at least twice the reading's
     * error there, so a cell at the limit does not flicker */
    GL_CHECK(worst[2] < 0.5 * (double)GL_PROV_READ_TEMP_HYST_C);
    /* the resistance figures of NETLIST_NOTES 4.5, from the same equation */
    GL_CHECK_NEAR(ntc_ohm_(0.0) / 1000.0, 28.2, 0.05);
    GL_CHECK_NEAR(ntc_ohm_(45.0) / 1000.0, 4.90, 0.005);
    GL_CHECK_NEAR(ntc_ohm_(60.0) / 1000.0, 3.04, 0.005);
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
        /* driven HIGH, push-pull: the MOSFET pulls the charger's TS pin low */
        GL_CHECK(gl_sim_pin_drives_high(GL_PIN_CHG_INHIBIT));
        GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_CHG_INHIBIT), GL_PIN_MODE_OUTPUT_PP);
        GL_CHECK(gl_sim_pin_level(GL_PIN_CHG_INHIBIT));
    } else {
        /* released: back to the reset state of the pin; the gate resistor
         * holds the MOSFET off */
        GL_CHECK(!gl_sim_pin_drives_high(GL_PIN_CHG_INHIBIT));
        GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_CHG_INHIBIT), GL_PIN_MODE_ANALOG);
        GL_CHECK(!gl_sim_pin_level(GL_PIN_CHG_INHIBIT));
    }
    /* the model's charger: free, it charges (the model's cell is at 25 C
     * and not full); stopped, it does not */
    GL_CHECK_EQ(gl_sim_charger_on(), pw_.vbus && allowed);
}

static uint32_t gate_now_ms_; /* the clock handed to the gate */

/* A gate call with NTC2 at t and both die sensors agreeing with it. */
static bool gate_at_(float t)
{
    gate_now_ms_ += 5000u;
    gl_power_poll_pins(&pw_);
    pw_.cell_temp_c = t;
    pw_.cell_temp_valid = true;
    pw_.ntc_fault = (uint8_t)GL_NTC_OK;
    pw_.mcu_temp_c = t;
    pw_.mcu_temp_valid = true;
    return gl_power_charge_gate(&pw_, gate_now_ms_, true, t, true, true);
}

/* The same with every argument given. */
static bool gate_(bool cell_fresh, float imu_c, bool imu_ok, bool mcu_fresh)
{
    gate_now_ms_ += 5000u;
    return gl_power_charge_gate(&pw_, gate_now_ms_, cell_fresh, imu_c, imu_ok, mcu_fresh);
}

GL_TEST(test_charge_gate_window_guard_and_hysteresis)
{
    const float lo = GL_PROV_CHARGE_TEMP_MIN_C + GL_PROV_CHARGE_TEMP_GUARD_C;
    const float hi = GL_PROV_CHARGE_TEMP_MAX_C - GL_PROV_CHARGE_TEMP_GUARD_C;
    const float hy = GL_PROV_CHARGE_TEMP_HYST_C;

    fresh_();
    /* no VBUS: nothing is stopped, whatever the temperature */
    GL_CHECK(!gate_at_(25.0f));
    expect_gate_(false);
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_NO_VBUS);
    GL_CHECK(!gate_at_(70.0f));
    GL_CHECK(!gl_sim_pin_drives_high(GL_PIN_CHG_INHIBIT));
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_NO_VBUS);

    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    gl_power_poll_pins(&pw_);
    gl_sim_trace_clear();
    GL_CHECK(gate_at_(25.0f));
    expect_gate_(true);
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_ALLOWED);
    /* the pin: on the way to "stop" the latch goes HIGH before the pin
     * becomes an output; on the way back it is written low and then goes
     * analog (never an open-drain moment, never a pull) */
    GL_CHECK(!gate_at_(60.0f));
    expect_gate_(false);
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_TOO_HOT);
    {
        const size_t n = gl_sim_trace_count();
        const gl_sim_trace_t *w = gl_sim_trace_at(n - 2u), *m = gl_sim_trace_at(n - 1u);
        GL_CHECK(w->type == GL_SIM_TR_GPIO_WRITE && w->a == (uint8_t)GL_PIN_CHG_INHIBIT && w->b == 1u);
        GL_CHECK(m->type == GL_SIM_TR_GPIO_MODE && m->a == (uint8_t)GL_PIN_CHG_INHIBIT &&
                 m->b == (uint16_t)GL_PIN_MODE_OUTPUT_PP);
    }
    GL_CHECK_EQ(gl_sim_charger_state(), GL_SIM_CHG_DISABLED);
    /* upper limit: stays stopped until hi - hysteresis */
    GL_CHECK(!gate_at_(hi - 0.1f));
    GL_CHECK(!gate_at_(hi - hy + 0.1f));
    GL_CHECK(gate_at_(hi - hy - 0.1f));
    expect_gate_(true);
    {
        const size_t n = gl_sim_trace_count();
        const gl_sim_trace_t *w = gl_sim_trace_at(n - 2u), *m = gl_sim_trace_at(n - 1u);
        GL_CHECK(w->type == GL_SIM_TR_GPIO_WRITE && w->a == (uint8_t)GL_PIN_CHG_INHIBIT && w->b == 0u);
        GL_CHECK(m->type == GL_SIM_TR_GPIO_MODE && m->a == (uint8_t)GL_PIN_CHG_INHIBIT &&
                 m->b == (uint16_t)GL_PIN_MODE_ANALOG);
    }
    /* once allowed it stays allowed up to the guarded limit itself */
    GL_CHECK(gate_at_(hi - 0.1f));
    GL_CHECK(!gate_at_(hi + 0.1f));
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_TOO_HOT);
    /* the guard: a reading of 44 C is "too hot" (the true cell may be at 45) */
    GL_CHECK(hi < GL_PROV_CHARGE_TEMP_MAX_C && lo > GL_PROV_CHARGE_TEMP_MIN_C);
    /* the firmware's window is NARROWER than the charger's own (which goes
     * on to 60 C at 4.06 V): that is why the firmware has a gate at all */
    GL_CHECK(GL_PROV_CHARGE_TEMP_MAX_C < GL_PROV_BQ25101_T_HOT_C);
    GL_CHECK(GL_PROV_CHARGE_TEMP_MIN_C >= GL_PROV_BQ25101_T_COLD_C);
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
    GL_CHECK(gl_sim_pin_drives_high(GL_PIN_CHG_INHIBIT));
    gl_sim_set_input(GL_PIN_VBUS_SENSE, false);
    GL_CHECK(!gate_at_(60.0f));
    GL_CHECK(!gl_sim_pin_drives_high(GL_PIN_CHG_INHIBIT));
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
                GL_CHECK_EQ(gl_sim_pin_drives_high(GL_PIN_CHG_INHIBIT), !model);
                if (model) {
                    if (pass == 0) {
                        on_up++;
                    } else {
                        on_down++;
                    }
                }
            }
        }
        printf("    firmware's charge gate over a sweep of -10..60 C and back: not stopped for %.1f K "
               "going up (%.1f..%.1f C), %.1f K going down (%.1f..%.1f C)\n", 0.1 * (double)on_up,
               (double)(lo + hy), (double)hi, 0.1 * (double)on_down, (double)lo, (double)(hi - hy));
        GL_CHECK(on_up > 300u && on_down > 300u);
    }
    if (gl_sim_violation_total() != 0u) {
        printf("    first violation: %s\n", gl_sim_violations()->first);
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
    GL_CHECK(!gate_(false, 25.0f, true, true));
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_TEMP_UNKNOWN);
    expect_gate_(false);
    GL_CHECK(gate_at_(25.0f));
    /* NTC faults */
    for (int f = (int)GL_NTC_OPEN; f <= (int)GL_NTC_STUCK; f++) {
        pw_.ntc_fault = (uint8_t)f;
        pw_.cell_temp_valid = false;
        GL_CHECK(!gate_(true, 25.0f, true, true));
        GL_CHECK_EQ(pw_.chg_reason, GL_CHG_NTC_FAULT);
        expect_gate_(false);
    }
    pw_.ntc_fault = (uint8_t)GL_NTC_ADC;
    GL_CHECK(!gate_(true, 25.0f, true, true));
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_TEMP_UNKNOWN);
    GL_CHECK(gate_at_(25.0f));
    /* plausibility: the NTC against the die sensors */
    pw_.cell_temp_c = 25.0f;
    pw_.mcu_temp_c = 25.0f + GL_PROV_CHARGE_TEMP_MAX_DISAGREE_C - 0.5f;
    GL_CHECK(gate_(true, 0.0f, false, true)); /* IMU dead, MCU agrees */
    pw_.mcu_temp_c = 25.0f + GL_PROV_CHARGE_TEMP_MAX_DISAGREE_C + 0.5f;
    GL_CHECK(!gate_(true, 0.0f, false, true)); /* the only one disagrees */
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_IMPLAUSIBLE);
    expect_gate_(false);
    GL_CHECK(gate_(true, 24.0f, true, true)); /* the IMU vouches for it */
    GL_CHECK(!gate_(true, 50.0f, true, true)); /* both disagree */
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_IMPLAUSIBLE);
    /* an NTC that reads a comfortable 25 C on a board that is at 50 C */
    pw_.mcu_temp_c = 50.0f;
    GL_CHECK(!gate_(true, 49.0f, true, true));
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_IMPLAUSIBLE);
    /* no die sensor at all: nothing to check the NTC against */
    pw_.mcu_temp_c = 25.0f;
    pw_.mcu_temp_valid = false;
    GL_CHECK(!gate_(true, 25.0f, false, true));
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_TEMP_UNKNOWN);
    pw_.mcu_temp_valid = true;
    GL_CHECK(!gate_(true, 25.0f, false, false)); /* MCU reading stale */
    GL_CHECK(!gate_(true, NAN, true, false));
    GL_CHECK(gate_(true, 25.0f, false, true));
    /* a die sensor cannot make an out-of-window cell acceptable */
    pw_.cell_temp_c = 50.0f;
    pw_.mcu_temp_c = 25.0f;
    GL_CHECK(!gate_(true, 50.0f, true, true));
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_TOO_HOT);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* DESIGN_SPEC E32: "firmware asserts CHG_INHIBIT after 6 hours of continuous
 * charging as a backstop."  The firmware counts the time in which it has NOT
 * held the charger stopped (VBUS present, CHG_INHIBIT released), whatever
 * the charger's status output says: a backstop must not depend on the line
 * it backs up (phase-3 review, hardware finding 2).  The limit holds until
 * VBUS goes or the cell has fallen below the restart voltage. */
GL_TEST(test_charge_time_limit_of_6_hours)
{
    const uint32_t step = 5000u;
    uint32_t t = 1000u, stopped_at = 0;
    unsigned calls = 0;

    GL_CHECK_EQ(GL_PROV_CHARGE_MAX_MS, 6u * 3600u * 1000u);
    fresh_();
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    pw_.cell_temp_c = 25.0f;
    pw_.cell_temp_valid = true;
    pw_.ntc_fault = (uint8_t)GL_NTC_OK;
    pw_.mcu_temp_c = 25.0f;
    pw_.mcu_temp_valid = true;
    pw_.batt_mv = 4150; /* a cell that hangs at the top without the charge ending */
    /* a gate call every 5 s, as the application makes them */
    for (; t < 7u * 3600u * 1000u; t += step) {
        gl_power_poll_pins(&pw_);
        calls++;
        if (!gl_power_charge_gate(&pw_, t, true, 25.0f, true, true)) {
            stopped_at = t;
            break;
        }
        GL_CHECK(pw_.charging);
    }
    GL_CHECK(stopped_at != 0u);
    printf("    continuous charging: stopped by the firmware after %.4f h (%u gate calls 5 s apart)\n",
           (double)(stopped_at - 1000u) / 3.6e6, calls);
    GL_CHECK(stopped_at - 1000u >= GL_PROV_CHARGE_MAX_MS && stopped_at - 1000u <= GL_PROV_CHARGE_MAX_MS + step);
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_TIME_LIMIT);
    GL_CHECK(pw_.time_limit && pw_.temp_ok);
    expect_gate_(false);
    gl_power_poll_pins(&pw_);
    GL_CHECK_EQ(pw_.chg_status, GL_CHGST_INHIBITED);
    /* it holds: hours later, with the cell still up, nothing has changed */
    for (int k = 0; k < 1000; k++) {
        t += step;
        gl_power_poll_pins(&pw_);
        GL_CHECK(!gl_power_charge_gate(&pw_, t, true, 25.0f, true, true));
    }
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_TIME_LIMIT);
    /* a temperature reason comes first, and does not lift the limit */
    pw_.cell_temp_c = 50.0f;
    pw_.mcu_temp_c = 50.0f;
    t += step;
    GL_CHECK(!gl_power_charge_gate(&pw_, t, true, 50.0f, true, true));
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_TOO_HOT);
    pw_.cell_temp_c = 25.0f;
    pw_.mcu_temp_c = 25.0f;
    t += step;
    GL_CHECK(!gl_power_charge_gate(&pw_, t, true, 25.0f, true, true));
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_TIME_LIMIT);
    /* the cell has run down behind the stopped charger: charging again, with
     * a fresh limit */
    pw_.batt_mv = (uint16_t)(GL_PROV_CHARGE_RESTART_MV - 10u);
    t += step;
    GL_CHECK(gl_power_charge_gate(&pw_, t, true, 25.0f, true, true));
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_ALLOWED);
    GL_CHECK(!pw_.time_limit);
    expect_gate_(true);
    gl_power_poll_pins(&pw_);
    GL_CHECK(pw_.charging);
    GL_CHECK(pw_.chg_run_ms < 60000u);
    /* The status line does NOT start the count again (until the phase-3
     * review it did, and one released sample every few hours kept the
     * backstop from ever firing): 5 h 59 min, the status output released for
     * one call, and the limit still comes at six hours. */
    {
        const uint32_t almost = GL_PROV_CHARGE_MAX_MS - 60000u;
        const uint32_t t0 = t;
        for (; t - t0 < almost; t += step) {
            gl_power_poll_pins(&pw_);
            GL_CHECK(gl_power_charge_gate(&pw_, t, true, 25.0f, true, true));
        }
        GL_CHECK(pw_.chg_run_ms > almost - 2u * step);
        gl_sim_set_vbat_mv(4200); /* the model's charge is done: CHG released */
        gl_power_poll_pins(&pw_);
        GL_CHECK(!pw_.charging);
        GL_CHECK(gl_power_charge_gate(&pw_, t, true, 25.0f, true, true));
        GL_CHECK(pw_.chg_run_ms > almost - 2u * step); /* kept */
        gl_sim_set_vbat_mv(3900); /* recharge */
    }
    /* A cell that is STILL below the restart voltage after six hours of
     * charging gets no second six hours: the limit fires and holds, however
     * low the cell reads, until the marker is lifted out. */
    pw_.batt_mv = (uint16_t)(GL_PROV_CHARGE_RESTART_MV - 100u);
    for (uint32_t t1 = t; t - t1 < 120000u; t += step) {
        gl_power_poll_pins(&pw_);
        (void)gl_power_charge_gate(&pw_, t, true, 25.0f, true, true);
    }
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_TIME_LIMIT);
    GL_CHECK(pw_.time_limit && !pw_.limit_cell_was_up);
    for (int k = 0; k < 5000; k++) { /* 7 h more */
        t += step;
        gl_power_poll_pins(&pw_);
        GL_CHECK(!gl_power_charge_gate(&pw_, t, true, 25.0f, true, true));
    }
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_TIME_LIMIT);
    expect_gate_(false);
    /* VBUS removed: everything about the limit is forgotten */
    gl_sim_set_input(GL_PIN_VBUS_SENSE, false);
    gl_power_poll_pins(&pw_);
    GL_CHECK(!gl_power_charge_gate(&pw_, t, true, 25.0f, true, true));
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_NO_VBUS);
    GL_CHECK(!pw_.time_limit && pw_.chg_run_ms == 0u);
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_CHG_INHIBIT), GL_PIN_MODE_ANALOG);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* Phase-3 review, hardware finding 2, as the reviewer ran it: VBUS present,
 * 25 C, a gate call every 5 s for 48 h, the charger's status output read as
 * "not charging" for one sample every 5 h.  Before the fix: "time limit
 * NEVER reached".  And the other reading of the status line (first cycle
 * only): CHG released all the time while the charger charges. */
GL_TEST(test_backstop_does_not_depend_on_the_status_line)
{
    const uint32_t step = 5000u;
    for (int variant = 0; variant < 2; variant++) {
        uint32_t t = 1000u, stopped_at = 0, glitches = 0, low = 0, calls = 0;
        fresh_();
        gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
        pw_.cell_temp_c = 25.0f;
        pw_.cell_temp_valid = true;
        pw_.ntc_fault = (uint8_t)GL_NTC_OK;
        pw_.mcu_temp_c = 25.0f;
        pw_.mcu_temp_valid = true;
        pw_.batt_mv = 4150;
        for (; t < 48u * 3600u * 1000u; t += step) {
            const bool glitch = (variant == 1) || (((t - 1000u) % (5u * 3600u * 1000u)) == 2u * 3600u * 1000u);
            /* the pin read as high: the model's cell at its end voltage
             * releases CHG; the driver's own cell reading is left alone */
            gl_sim_set_vbat_mv(glitch ? 4200 : 3900);
            gl_power_poll_pins(&pw_);
            glitches += pw_.charging ? 0u : 1u;
            low += pw_.charging ? 1u : 0u;
            calls++;
            if (!gl_power_charge_gate(&pw_, t, true, 25.0f, true, true)) {
                stopped_at = t;
                break;
            }
        }
        GL_CHECK(stopped_at != 0u);
        GL_CHECK(glitches >= 1u);
        if (variant == 1) {
            GL_CHECK_EQ(low, 0u); /* the firmware never saw "charging" */
        }
        GL_CHECK(stopped_at - 1000u >= GL_PROV_CHARGE_MAX_MS &&
                 stopped_at - 1000u <= GL_PROV_CHARGE_MAX_MS + step);
        GL_CHECK_EQ(pw_.chg_reason, GL_CHG_TIME_LIMIT);
        expect_gate_(false);
        printf("    %s: stopped by the firmware after %.4f h (%u gate calls, CHG read high in %u "
               "of them)\n",
               variant == 0 ? "status output released for one 5 s sample every 5 h"
                            : "status output never low (a charger that shows the first cycle only, on a recharge)",
               (double)(stopped_at - 1000u) / 3.6e6, (unsigned)calls, (unsigned)glitches);
        /* time in which the firmware itself holds the charger is not counted */
        gl_sim_set_input(GL_PIN_VBUS_SENSE, false);
        gl_power_poll_pins(&pw_);
        (void)gl_power_charge_gate(&pw_, t, true, 25.0f, true, true);
        gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
        gl_power_poll_pins(&pw_);
        GL_CHECK(gl_power_charge_gate(&pw_, t, true, 25.0f, true, true));
        gl_power_charge_force(&pw_, true);
        for (uint32_t t1 = t; t - t1 < 8u * 3600u * 1000u; t += step) {
            gl_power_poll_pins(&pw_);
            GL_CHECK(!gl_power_charge_gate(&pw_, t, true, 25.0f, true, true));
        }
        GL_CHECK_EQ(pw_.chg_reason, GL_CHG_FORCED);
        GL_CHECK(!pw_.time_limit && pw_.chg_run_ms <= 2u * step);
    }
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* Phase-3 review, hardware finding 10: the read gate (E13) believes NTC2 only
 * as the charge gate does.  NTC2 at 25 C beside two die sensors at 75 C was
 * "read ALLOWED" while the charge gate called the same reading IMPLAUSIBLE. */
GL_TEST(test_read_gate_does_not_believe_an_implausible_ntc)
{
    fresh_();
    pw_.cell_temp_c = 25.0f;
    pw_.cell_temp_valid = true;
    pw_.ntc_fault = (uint8_t)GL_NTC_OK;
    pw_.mcu_temp_c = 75.0f;
    pw_.mcu_temp_valid = true;
    /* both die sensors contradict it: the hotter die sensor decides */
    GL_CHECK(!gl_power_read_allowed(&pw_, true, 75.0f, true, true));
    GL_CHECK(pw_.read_hot);
    /* the charge gate's verdict on the same inputs */
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    gl_power_poll_pins(&pw_);
    GL_CHECK(!gl_power_charge_gate(&pw_, 1000u, true, 75.0f, true, true));
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_IMPLAUSIBLE);
    /* one die sensor near NTC2 vouches for it (the other may be wrong) */
    pw_.read_hot = false;
    pw_.mcu_temp_c = 30.0f;
    GL_CHECK(gl_power_read_allowed(&pw_, true, 75.0f, true, true));
    /* a hot NTC2 that a die sensor confirms refuses, as before */
    pw_.cell_temp_c = 62.0f;
    pw_.mcu_temp_c = 58.0f;
    GL_CHECK(!gl_power_read_allowed(&pw_, true, 55.0f, true, true));
    /* a hot NTC2 contradicted by two cool dies still refuses: the hottest
     * reading decides when they do not agree */
    pw_.read_hot = false;
    pw_.cell_temp_c = 70.0f;
    pw_.mcu_temp_c = 24.0f;
    GL_CHECK(!gl_power_read_allowed(&pw_, true, 25.0f, true, true));
    /* no die sensor alive: NTC2 is taken as it reads */
    pw_.read_hot = false;
    pw_.cell_temp_c = 63.0f;
    GL_CHECK(!gl_power_read_allowed(&pw_, true, 0.0f, false, false));
    pw_.read_hot = false;
    pw_.cell_temp_c = 25.0f;
    GL_CHECK(gl_power_read_allowed(&pw_, true, 0.0f, false, false));
    printf("    NTC2 25 C, both die sensors 75 C: read REFUSED (was allowed), charge gate "
           "IMPLAUSIBLE; one die sensor within %.0f K of NTC2: NTC2 believed\n",
           (double)GL_PROV_CHARGE_TEMP_MAX_DISAGREE_C);
}

/* The factory's "stop the charge" (GL_CMD_SET_CHARGE): held until released,
 * until VBUS goes, or a reset.  Assembly step 13 proves the charger's own
 * thermistor input and the stop MOSFET with it: the charge must stop when
 * the firmware pulls TS low. */
GL_TEST(test_charge_stop_by_command)
{
    fresh_();
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    GL_CHECK(gate_at_(25.0f));
    gl_power_poll_pins(&pw_);
    GL_CHECK(pw_.charging);
    gl_power_charge_force(&pw_, true);
    GL_CHECK(!gate_at_(25.0f));
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_FORCED);
    expect_gate_(false);
    gl_power_poll_pins(&pw_);
    GL_CHECK(!pw_.charging);
    GL_CHECK_EQ(pw_.chg_status, GL_CHGST_INHIBITED);
    GL_CHECK(pw_.temp_ok); /* the temperature has nothing against it */
    /* a temperature reason is named in preference */
    GL_CHECK(!gate_at_(-3.0f));
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_TOO_COLD);
    GL_CHECK(!gate_at_(25.0f));
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_FORCED);
    gl_power_charge_force(&pw_, false);
    GL_CHECK(gate_at_(25.0f));
    expect_gate_(true);
    /* VBUS gone: forgotten */
    gl_power_charge_force(&pw_, true);
    GL_CHECK(!gate_at_(25.0f));
    gl_sim_set_input(GL_PIN_VBUS_SENSE, false);
    GL_CHECK(!gate_at_(25.0f));
    GL_CHECK(!pw_.forced);
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    GL_CHECK(gate_at_(25.0f));
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* What the firmware infers from the charger's ONE status output: a defined
 * answer for every case the data sheet may give - charging, done, stopped
 * by its own thermistor, no input - and for the two that do not add up. */
GL_TEST(test_charger_status_inference)
{
    gl_power_t p;
    memset(&p, 0, sizeof(p));
    /* the pure function, case by case */
    GL_CHECK_EQ(gl_power_charger_status(&p), GL_CHGST_NO_INPUT);
    p.charging = true; /* (a status line that reads low without VBUS) */
    GL_CHECK_EQ(gl_power_charger_status(&p), GL_CHGST_NO_INPUT);
    p.vbus = true;
    GL_CHECK_EQ(gl_power_charger_status(&p), GL_CHGST_CHARGING);
    p.inhibit = true;
    GL_CHECK_EQ(gl_power_charger_status(&p), GL_CHGST_STOP_FAILED);
    p.charging = false;
    GL_CHECK_EQ(gl_power_charger_status(&p), GL_CHGST_INHIBITED);
    p.inhibit = false;
    p.batt_mv = 4150;
    GL_CHECK_EQ(gl_power_charger_status(&p), GL_CHGST_DONE);
    p.batt_mv = (uint16_t)GL_PROV_CHARGE_DONE_MIN_MV;
    GL_CHECK_EQ(gl_power_charger_status(&p), GL_CHGST_DONE);
    p.batt_mv = (uint16_t)(GL_PROV_CHARGE_DONE_MIN_MV - 1u);
    GL_CHECK_EQ(gl_power_charger_status(&p), GL_CHGST_NOT_CHARGING);
    p.batt_mv = 0; /* not measured yet */
    GL_CHECK_EQ(gl_power_charger_status(&p), GL_CHGST_NOT_CHARGING);
    p.batt_mv = 3800;
    p.cell_temp_valid = true;
    p.cell_temp_c = GL_PROV_BQ25101_T_COLD_C - 0.5f;
    GL_CHECK_EQ(gl_power_charger_status(&p), GL_CHGST_TEMP_HOLD);
    p.cell_temp_c = GL_PROV_BQ25101_T_HOT_C + 0.5f;
    GL_CHECK_EQ(gl_power_charger_status(&p), GL_CHGST_TEMP_HOLD);
    p.cell_temp_c = 50.0f; /* inside the charger's window: it should charge */
    GL_CHECK_EQ(gl_power_charger_status(&p), GL_CHGST_NOT_CHARGING);
    p.cell_temp_c = NAN;
    GL_CHECK_EQ(gl_power_charger_status(&p), GL_CHGST_NOT_CHARGING);
    /* the done threshold lies under the voltage at which the model's charger
     * starts a recharge, with room for the divider and the ADC */
    GL_CHECK(GL_PROV_CHARGE_DONE_MIN_MV < GL_PROV_BQ25101_VREG_MV - GL_PROV_BQ25101_RECHARGE_DROP_MV);
    GL_CHECK(GL_PROV_CHARGE_RESTART_MV < GL_PROV_CHARGE_DONE_MIN_MV);

    /* and against the MODEL, through the pins and the ADC */
    fresh_();
    gl_sim_set_cell_temperature(25.0f);
    gl_sim_set_mcu_temperature(25.0f);
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    GL_CHECK_EQ(gl_power_measure(&pw_), GL_OK);
    gl_power_poll_pins(&pw_);
    GL_CHECK_EQ(gl_sim_charger_state(), GL_SIM_CHG_FAST);
    GL_CHECK_EQ(pw_.chg_status, GL_CHGST_CHARGING);
    /* done: the model's cell at the regulation voltage */
    gl_sim_set_vbat_mv(4200);
    GL_CHECK_EQ(gl_sim_charger_state(), GL_SIM_CHG_DONE);
    GL_CHECK_EQ(gl_power_measure(&pw_), GL_OK);
    gl_power_poll_pins(&pw_);
    GL_CHECK_EQ(pw_.chg_status, GL_CHGST_DONE);
    /* ... still done just above the recharge threshold, charging below it */
    gl_sim_set_vbat_mv(4110);
    GL_CHECK_EQ(gl_sim_charger_state(), GL_SIM_CHG_DONE);
    GL_CHECK_EQ(gl_power_measure(&pw_), GL_OK);
    gl_power_poll_pins(&pw_);
    GL_CHECK_EQ(pw_.chg_status, GL_CHGST_DONE);
    gl_sim_set_vbat_mv(4090);
    GL_CHECK_EQ(gl_sim_charger_state(), GL_SIM_CHG_FAST);
    gl_power_poll_pins(&pw_);
    GL_CHECK_EQ(pw_.chg_status, GL_CHGST_CHARGING);
    gl_sim_set_vbat_mv(3900);
    /* the charger's own thermistor holds it: too cold, too hot */
    gl_sim_set_cell_temperature(-4.0f);
    GL_CHECK_EQ(gl_sim_charger_state(), GL_SIM_CHG_COLD);
    GL_CHECK_EQ(gl_power_measure(&pw_), GL_OK);
    gl_power_poll_pins(&pw_);
    GL_CHECK_EQ(pw_.chg_status, GL_CHGST_TEMP_HOLD);
    gl_sim_set_cell_temperature(63.0f);
    GL_CHECK_EQ(gl_sim_charger_state(), GL_SIM_CHG_HOT);
    GL_CHECK_EQ(gl_power_measure(&pw_), GL_OK);
    gl_power_poll_pins(&pw_);
    GL_CHECK_EQ(pw_.chg_status, GL_CHGST_TEMP_HOLD);
    gl_sim_set_cell_temperature(25.0f);
    GL_CHECK_EQ(gl_power_measure(&pw_), GL_OK);
    /* an input too low for the charger (a weak source behind the cradle's
     * fuse): VBUS_SENSE reads high, nothing charges */
    gl_sim_charger_input_low(true);
    GL_CHECK_EQ(gl_sim_charger_state(), GL_SIM_CHG_NO_INPUT);
    gl_power_poll_pins(&pw_);
    GL_CHECK(pw_.vbus);
    GL_CHECK_EQ(pw_.chg_status, GL_CHGST_NOT_CHARGING);
    gl_sim_charger_input_low(false);
    /* the charger's thermistor shorted: its TS input at ground, disabled */
    gl_sim_ntc1_set_fault(GL_SIM_NTC1_SHORT);
    GL_CHECK_EQ(gl_sim_charger_state(), GL_SIM_CHG_DISABLED);
    gl_power_poll_pins(&pw_);
    GL_CHECK_EQ(pw_.chg_status, GL_CHGST_NOT_CHARGING);
    gl_sim_ntc1_set_fault(GL_SIM_NTC1_NORMAL);
    /* the firmware stops it: inhibited; with the stop MOSFET open the stop
     * does not stop, and the status says so */
    gl_power_charge_force(&pw_, true);
    GL_CHECK(!gl_power_charge_gate(&pw_, 1000u, true, 25.0f, true, true));
    gl_power_poll_pins(&pw_);
    GL_CHECK_EQ(pw_.chg_status, GL_CHGST_INHIBITED);
    gl_sim_charger_stop_broken(true);
    GL_CHECK(gl_sim_charger_on());
    gl_power_poll_pins(&pw_);
    GL_CHECK_EQ(pw_.chg_status, GL_CHGST_STOP_FAILED);
    gl_sim_charger_stop_broken(false);
    gl_power_charge_force(&pw_, false);
    GL_CHECK(gl_power_charge_gate(&pw_, 2000u, true, 25.0f, true, true));
    /* the charger's thermistor OPEN: by GL_PROV_BQ25101_TS_OPEN_IS_TTDM it
     * then has no temperature window.  At 70 C it charges; the firmware's
     * gate on NTC2 stops it (TS pulled low wins) and flags the charger */
    gl_sim_ntc1_set_fault(GL_SIM_NTC1_OPEN);
    gl_sim_set_cell_temperature(70.0f);
    gl_sim_set_mcu_temperature(70.0f);
    GL_CHECK_EQ(gl_sim_charger_state(), GL_SIM_CHG_TTDM);
    GL_CHECK_EQ(gl_power_measure(&pw_), GL_OK);
    gl_power_poll_pins(&pw_);
    GL_CHECK_EQ(pw_.chg_status, GL_CHGST_CHARGING);
    GL_CHECK(!pw_.ntc1_suspect);
    GL_CHECK(!gl_power_charge_gate(&pw_, 3000u, true, 70.0f, true, true));
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_TOO_HOT);
    GL_CHECK(pw_.ntc1_suspect);
    GL_CHECK_EQ(gl_sim_charger_state(), GL_SIM_CHG_DISABLED);
    gl_power_poll_pins(&pw_);
    GL_CHECK_EQ(pw_.chg_status, GL_CHGST_INHIBITED);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* DESIGN_SPEC E13: no camera read is started when the cell thermistor reads
 * above 60 C. */
GL_TEST(test_read_gate_at_60_c)
{
    const float lim = GL_PROV_READ_TEMP_MAX_C, hy = GL_PROV_READ_TEMP_HYST_C;
    gl_power_t p;

    GL_CHECK_NEAR(lim, 60.0, 1e-6);
    memset(&p, 0, sizeof(p));
    p.cell_temp_valid = true;
    p.ntc_fault = (uint8_t)GL_NTC_OK;
    /* the limit is on the reading: at 60.0 a read still starts, above it not */
    p.cell_temp_c = lim;
    GL_CHECK(gl_power_read_allowed(&p, true, 20.0f, true, true));
    p.cell_temp_c = lim + 0.1f;
    GL_CHECK(!gl_power_read_allowed(&p, true, 20.0f, true, true));
    GL_CHECK(p.read_hot);
    /* hysteresis: allowed again only below limit - hysteresis */
    p.cell_temp_c = lim - 0.1f;
    GL_CHECK(!gl_power_read_allowed(&p, true, 20.0f, true, true));
    p.cell_temp_c = lim - hy + 0.1f;
    GL_CHECK(!gl_power_read_allowed(&p, true, 20.0f, true, true));
    p.cell_temp_c = lim - hy - 0.1f;
    GL_CHECK(gl_power_read_allowed(&p, true, 20.0f, true, true));
    GL_CHECK(!p.read_hot);
    p.cell_temp_c = lim - 0.1f; /* and stays allowed up to the limit */
    GL_CHECK(gl_power_read_allowed(&p, true, 20.0f, true, true));
    /* a sweep up and down against an independent model of the rule */
    {
        bool hot = false;
        for (int pass = 0; pass < 2; pass++) {
            for (int k = 0; k <= 400; k++) {
                const float t = (pass == 0) ? (40.0f + 0.1f * (float)k) : (80.0f - 0.1f * (float)k);
                hot = hot ? !(t < lim - hy) : (t > lim);
                p.cell_temp_c = t;
                GL_CHECK_EQ(gl_power_read_allowed(&p, true, 20.0f, true, true), !hot);
            }
        }
    }
    /* The die sensors cannot make a hot NTC2 acceptable.  The other way
     * round this test pinned, until the phase-3 review, that an NTC2 at
     * 30 C was believed beside two die sensors at 90 C; the charge gate
     * calls that reading IMPLAUSIBLE, and the read gate now does not believe
     * it either (test_read_gate_does_not_believe_an_implausible_ntc) */
    p.cell_temp_c = 30.0f;
    p.mcu_temp_c = 90.0f;
    p.mcu_temp_valid = true;
    GL_CHECK(!gl_power_read_allowed(&p, true, 90.0f, true, true));
    p.read_hot = false;
    p.mcu_temp_c = 36.0f; /* one die sensor within 10 K vouches for NTC2 */
    GL_CHECK(gl_power_read_allowed(&p, true, 90.0f, true, true));
    p.cell_temp_c = 65.0f;
    p.mcu_temp_c = 20.0f;
    GL_CHECK(!gl_power_read_allowed(&p, true, 20.0f, true, true));
    /* NTC2 with nothing to say (stale, or a fault): the hotter die sensor
     * that is alive stands in */
    memset(&p, 0, sizeof(p));
    p.cell_temp_c = 20.0f;
    p.cell_temp_valid = true;
    p.mcu_temp_valid = true;
    p.mcu_temp_c = 61.0f;
    GL_CHECK(!gl_power_read_allowed(&p, false, 30.0f, true, true)); /* stale NTC2; MCU die 61 */
    p.read_hot = false;
    p.mcu_temp_c = 30.0f;
    GL_CHECK(!gl_power_read_allowed(&p, false, 62.0f, true, true)); /* IMU die 62 */
    p.read_hot = false;
    GL_CHECK(gl_power_read_allowed(&p, false, 40.0f, true, true));
    p.ntc_fault = (uint8_t)GL_NTC_OPEN;
    p.cell_temp_valid = false;
    p.cell_temp_c = NAN;
    GL_CHECK(gl_power_read_allowed(&p, true, 40.0f, true, true));
    GL_CHECK(!gl_power_read_allowed(&p, true, 70.0f, true, false)); /* only the IMU's is fresh */
    p.read_hot = false;
    GL_CHECK(!gl_power_read_allowed(&p, true, 0.0f, false, true) == (p.mcu_temp_c > lim));
    /* no temperature at all: allowed (power.h says why) */
    p.read_hot = false;
    GL_CHECK(gl_power_read_allowed(&p, false, NAN, false, false));
    GL_CHECK(gl_power_read_allowed(&p, true, 99.0f, false, false));
}

/* The rules the simulator has for the charger pins and for sleeping with a
 * charger around: each is made to fire here. */
GL_TEST(test_charger_rules_of_the_simulator)
{
    fresh_();
    gl_sim_set_cell_temperature(50.0f); /* inside the charger's window, outside the firmware's */
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    gl_power_poll_pins(&pw_);
    /* the charger started by itself, in its WARM zone; the firmware's
     * measurement stops it */
    GL_CHECK_EQ(gl_sim_charger_state(), GL_SIM_CHG_WARM);
    gl_sim_advance_ms(3);
    GL_CHECK_EQ(gl_power_measure_temps(&pw_), GL_OK);
    GL_CHECK(!gl_power_charge_gate(&pw_, 0u, true, 50.0f, true, true));
    GL_CHECK(!gl_sim_charger_on());
    GL_CHECK_EQ(pw_.chg_reason, GL_CHG_TOO_HOT);
    {
        const gl_sim_stats_t *st = gl_sim_stats();
        GL_CHECK(st->chg_outside_us >= 3000u && st->chg_outside_us < 6000u);
        GL_CHECK_EQ(st->chg_outside_longest_us, st->chg_outside_us);
        GL_CHECK_EQ(st->chg_warm_us, st->chg_outside_us);
        GL_CHECK_EQ(st->chg_hw_outside_us, 0u); /* never outside the charger's own window */
    }
    for (int k = 0; k < 6; k++) {
        gl_sim_advance_ms(10000);
        gl_hal_watchdog_kick();
    }
    GL_CHECK(gl_sim_stats()->chg_outside_us < 6000u); /* stopped: nothing added */
    GL_CHECK(gl_sim_stats()->inhibit_us >= 60000000u);
    if (gl_sim_violation_total() != 0u) {
        printf("    first violation: %s\n", gl_sim_violations()->first);
    }
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
    /* rule: a charge running outside the firmware's window for longer than
     * the limit while firmware runs */
    gl_power_charge_release(&pw_);
    gl_sim_advance_ms(GL_SIM_CHG_REACT_MAX_MS + 100u);
    GL_CHECK_EQ(gl_sim_violations()->power, 1u);
    GL_CHECK(strstr(gl_sim_violations()->first, "charging for") != NULL);
    /* rule: CHG_INHIBIT is push-pull or analog - an open-drain output stops
     * nothing, a pull half opens the MOSFET */
    gl_hal_gpio_write(GL_PIN_CHG_INHIBIT, true);
    gl_hal_gpio_mode(GL_PIN_CHG_INHIBIT, GL_PIN_MODE_OUTPUT_OD);
    GL_CHECK_EQ(gl_sim_violations()->power, 2u);
    GL_CHECK(gl_sim_charger_on()); /* released open drain: the charger is not stopped */
    gl_hal_gpio_mode(GL_PIN_CHG_INHIBIT, GL_PIN_MODE_INPUT_PULLUP);
    GL_CHECK_EQ(gl_sim_violations()->power, 3u);
    gl_hal_gpio_mode(GL_PIN_CHG_INHIBIT, GL_PIN_MODE_OUTPUT_PP);
    GL_CHECK_EQ(gl_sim_violations()->power, 3u);
    GL_CHECK(!gl_sim_charger_on());
    /* rule: Stop mode with the pin high and VBUS gone */
    gl_sim_set_input(GL_PIN_VBUS_SENSE, false);
    gl_hal_irq_enable(GL_IRQ_WAKE_TIMER, true);
    gl_hal_wake_timer_start(5);
    (void)gl_hal_sleep(GL_SLEEP_STOP);
    GL_CHECK_EQ(gl_sim_violations()->power, 4u);
    /* the driver's own way out of that state is clean */
    gl_power_poll_pins(&pw_);
    (void)gl_power_charge_gate(&pw_, 0u, true, 25.0f, true, true);
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_CHG_INHIBIT), GL_PIN_MODE_ANALOG);
    (void)gl_hal_irq_take();
    gl_hal_wake_timer_start(5);
    (void)gl_hal_sleep(GL_SLEEP_STOP);
    GL_CHECK_EQ(gl_sim_violations()->power, 4u);
    /* rule: Stop mode in the cradle without a wake-up soon enough */
    gl_sim_set_cell_temperature(22.0f);
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    (void)gl_hal_irq_take();
    gl_hal_wake_timer_start(GL_SIM_CHG_SUPERVISE_MAX_MS + 2000u);
    (void)gl_hal_sleep(GL_SLEEP_STOP);
    GL_CHECK_EQ(gl_sim_violations()->power, 5u);
    (void)gl_hal_irq_take();
    gl_hal_wake_timer_start(GL_SIM_CHG_SUPERVISE_MAX_MS - 2000u);
    (void)gl_hal_sleep(GL_SLEEP_STOP);
    GL_CHECK_EQ(gl_sim_violations()->power, 5u);
}

GL_TEST(test_status_pins_and_interrupts)
{
    fresh_();
    gl_hal_irq_enable(GL_IRQ_VBUS_CHANGE | GL_IRQ_CHG_STAT, true);
    GL_CHECK_EQ(gl_hal_irq_take(), 0u);
    /* into the cradle: VBUS rises, and the charger pulls its status low */
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    GL_CHECK_EQ(gl_hal_irq_take(), GL_IRQ_VBUS_CHANGE | GL_IRQ_CHG_STAT);
    gl_power_poll_pins(&pw_);
    GL_CHECK(pw_.vbus && pw_.charging);
    /* the charge ends: an edge on the status line, nothing on VBUS */
    gl_sim_set_vbat_mv(4200);
    GL_CHECK_EQ(gl_hal_irq_take(), GL_IRQ_CHG_STAT);
    gl_power_poll_pins(&pw_);
    GL_CHECK(pw_.vbus && !pw_.charging);
    /* a recharge */
    gl_sim_set_vbat_mv(4000);
    GL_CHECK_EQ(gl_hal_irq_take(), GL_IRQ_CHG_STAT);
    /* out of the cradle: both */
    gl_sim_set_input(GL_PIN_VBUS_SENSE, false);
    GL_CHECK_EQ(gl_hal_irq_take(), GL_IRQ_VBUS_CHANGE | GL_IRQ_CHG_STAT);
    gl_power_poll_pins(&pw_);
    GL_CHECK(!pw_.vbus && !pw_.charging);
    /* the board as it leaves the cradle: the USB supply of the MCU goes at
     * once (its monitor is an interrupt source of its own), the VBUS_SENSE
     * pin follows when the divider has discharged the pad */
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    (void)gl_hal_irq_take();
    GL_CHECK(gl_hal_usb_supply_ok());
    gl_sim_vbus_remove_lagging((uint32_t)GL_PINS_VBUS_REMOVAL_SEEN_MS);
    GL_CHECK((gl_hal_irq_take() & GL_IRQ_VBUS_CHANGE) != 0u);
    GL_CHECK(gl_hal_gpio_read(GL_PIN_VBUS_SENSE)); /* still reads high ... */
    GL_CHECK(!gl_hal_usb_supply_ok());             /* ... and the supply is gone */
    GL_CHECK(!gl_sim_charger_on());
    GL_CHECK_EQ(gl_hal_usb_start(), GL_ERR_STATE); /* the supply-valid bit is not set on it */
    gl_sim_advance_ms((uint32_t)GL_PINS_VBUS_REMOVAL_SEEN_MS - 1u);
    GL_CHECK(gl_hal_gpio_read(GL_PIN_VBUS_SENSE));
    gl_sim_advance_ms(1);
    GL_CHECK(!gl_hal_gpio_read(GL_PIN_VBUS_SENSE));
    GL_CHECK((gl_hal_irq_take() & GL_IRQ_VBUS_CHANGE) != 0u);
}

/*
 * THE HARDWARE MODEL ON ITS OWN: the MCU is held in reset the whole time, no
 * firmware runs, CHG_INHIBIT is high impedance.  What the model's BQ25101
 * does with its own thermistor across the temperature range - which is what
 * protects the cell in the ROM loader, behind a hung firmware, in ship mode
 * and with the MCU unpowered.  This is a test of THE MODEL (thresholds
 * PROVISIONAL): it shows what the firmware is entitled to expect of the
 * hardware, not what the chip does.
 */
GL_TEST(test_hardware_model_charger_alone_over_temperature)
{
    static const struct {
        float t_c;
        gl_sim_chg_state_t want;
        const char *what;
    } row[] = {
        { -20.0f, GL_SIM_CHG_COLD, "no charge" },      { -0.5f, GL_SIM_CHG_COLD, "no charge" },
        { 0.5f, GL_SIM_CHG_COOL, "half current" },     { 9.5f, GL_SIM_CHG_COOL, "half current" },
        { 10.5f, GL_SIM_CHG_FAST, "19.8 mA to 4.20 V" }, { 25.0f, GL_SIM_CHG_FAST, "19.8 mA to 4.20 V" },
        { 44.5f, GL_SIM_CHG_FAST, "19.8 mA to 4.20 V" }, { 45.5f, GL_SIM_CHG_WARM, "to 4.06 V only" },
        { 59.5f, GL_SIM_CHG_WARM, "to 4.06 V only" },  { 60.5f, GL_SIM_CHG_HOT, "no charge" },
        { 85.0f, GL_SIM_CHG_HOT, "no charge" },
    };
    gl_sim_reset(true); /* and NO gl_hal_init(): the MCU stays in reset */
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    for (size_t i = 0; i < GL_ARRAY_LEN(row); i++) {
        const gl_sim_stats_t *st;
        uint64_t on0, alone0, warm0, cool0;
        gl_sim_set_cell_temperature(row[i].t_c);
        st = gl_sim_stats();
        on0 = st->chg_in_reset_us;
        alone0 = st->chg_alone_outside_us;
        warm0 = st->chg_warm_us;
        cool0 = st->chg_cool_us;
        gl_sim_advance_ms(60000);
        st = gl_sim_stats();
        GL_CHECK_EQ(gl_sim_charger_state(), row[i].want);
        printf("    cell at %5.1f C, no firmware: %-5s (%s); charged for %2.0f of 60 s\n",
               (double)row[i].t_c, gl_sim_charger_state_name(gl_sim_charger_state()), row[i].what,
               (double)(st->chg_in_reset_us - on0) / 1e6);
        if (row[i].want == GL_SIM_CHG_COLD || row[i].want == GL_SIM_CHG_HOT) {
            GL_CHECK_EQ(st->chg_in_reset_us - on0, 0u);
            GL_CHECK(gl_sim_pin_level(GL_PIN_CHG_STAT)); /* status released */
        } else {
            GL_CHECK_EQ(st->chg_in_reset_us - on0, 60000000u);
            GL_CHECK(!gl_sim_pin_level(GL_PIN_CHG_STAT));
        }
        GL_CHECK_EQ(st->chg_warm_us - warm0, (row[i].want == GL_SIM_CHG_WARM) ? 60000000u : 0u);
        GL_CHECK_EQ(st->chg_cool_us - cool0, (row[i].want == GL_SIM_CHG_COOL) ? 60000000u : 0u);
        /* charging outside the firmware's 0..45 C with nobody there: only in
         * the charger's WARM zone */
        GL_CHECK_EQ(st->chg_alone_outside_us - alone0, (row[i].want == GL_SIM_CHG_WARM) ? 60000000u : 0u);
    }
    /* never a charge outside the charger's own window, and nothing counted
     * against a firmware that was not running */
    GL_CHECK_EQ(gl_sim_stats()->chg_hw_outside_us, 0u);
    GL_CHECK_EQ(gl_sim_stats()->chg_outside_us, 0u);
    GL_CHECK_EQ(gl_sim_stats()->chg_on_us, 0u);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
    /* in the WARM zone the charger regulates to 4.06 V: a cell above that
     * gets nothing */
    gl_sim_set_cell_temperature(50.0f);
    gl_sim_set_vbat_mv(4100);
    GL_CHECK_EQ(gl_sim_charger_state(), GL_SIM_CHG_DONE);
    gl_sim_set_vbat_mv(3900);
    GL_CHECK_EQ(gl_sim_charger_state(), GL_SIM_CHG_WARM);
    /* WHAT THE MODEL DOES NOT PROTECT AGAINST: its thermistor open.  The
     * charger then has no window (GL_PROV_BQ25101_TS_OPEN_IS_TTDM), and with
     * no firmware nothing else has one */
    gl_sim_ntc1_set_fault(GL_SIM_NTC1_OPEN);
    gl_sim_set_cell_temperature(70.0f);
    gl_sim_advance_ms(60000);
    GL_CHECK_EQ(gl_sim_charger_state(), GL_SIM_CHG_TTDM);
    printf("    cell at  70.0 C, no firmware, the charger's thermistor OPEN: %s - charged for %.0f of "
           "60 s outside its own window (NOT MET in hardware alone; the firmware's gate covers it "
           "while it runs)\n", gl_sim_charger_state_name(gl_sim_charger_state()),
           (double)gl_sim_stats()->chg_hw_outside_us / 1e6);
    GL_CHECK_EQ(gl_sim_stats()->chg_hw_outside_us, 60000000u); /* PINNED: NOT MET */
}

/* The hardware model and the END of a charge (the reason for E32): the
 * charger terminates when ITS OUTPUT current falls below 10 % of 19.8 mA,
 * and the board hangs on the same node as the cell.  With the MCU drawing
 * nothing (held in reset) the model's charge ends; with the ROM loader
 * running (several milliamperes, a guess) it never does, and what ends it
 * is the charger's own timer - if it has one (from memory).  A MODEL: the
 * cell is a guess too. */
GL_TEST(test_hardware_model_termination_needs_a_small_load)
{
    const double i_term = (double)GL_PROV_BQ25101_TERM_FRACTION * (double)GL_PROV_BQ25101_ICHG_UA;
    double hours = 0.0;

    /* (a) MCU in reset: nothing but the always-on parts on the node */
    gl_sim_reset(true);
    gl_sim_cell_enable(0.90f);
    gl_sim_set_cell_temperature(25.0f);
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    GL_CHECK_EQ(gl_sim_charger_state(), GL_SIM_CHG_FAST);
    /* the always-on parts, the flash and the IMU as the reset left them, and
     * the 28 uA of CHG's pull-up while the charger holds its status low */
    GL_CHECK(gl_sim_load_ua() < 20.0 + GL_SIM_I_CHG_STAT_PULLUP_UA);
    GL_CHECK(gl_sim_load_ua() > GL_SIM_I_CHG_STAT_PULLUP_UA);
    for (int k = 0; k < 6 * 60 && gl_sim_charger_on(); k++) {
        gl_sim_advance_ms(60000);
        hours += 1.0 / 60.0;
    }
    GL_CHECK_EQ(gl_sim_charger_state(), GL_SIM_CHG_DONE);
    GL_CHECK_EQ(gl_sim_stats()->chg_terminations, 1u);
    GL_CHECK(gl_sim_pin_level(GL_PIN_CHG_STAT));
    printf("    model, MCU in reset (load %.1f uA): from 90 %% the charge terminates after %.2f h at "
           "%.1f %%; termination threshold %.2f mA\n", gl_sim_load_ua(), hours,
           100.0 * (double)gl_sim_cell_soc(), i_term / 1000.0);
    GL_CHECK(hours > 0.1 && hours < 3.0);
    GL_CHECK(gl_sim_cell_soc() > 0.97f);

    /* (b) the ROM loader running: its draw is above the termination current */
    gl_sim_reset(true);
    gl_sim_cell_enable(0.90f);
    gl_sim_set_cell_temperature(25.0f);
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    gl_sim_mcu_enter_rom();
    GL_CHECK(gl_sim_load_ua() > i_term);
    for (int k = 0; k < 9 * 60; k++) {
        gl_sim_advance_ms(60000);
    }
    GL_CHECK(gl_sim_charger_on()); /* 9 h later: still "charging", the cell held at 4.2 V */
    GL_CHECK_EQ(gl_sim_stats()->chg_terminations, 0u);
    GL_CHECK(!gl_sim_pin_level(GL_PIN_CHG_STAT));
    GL_CHECK(gl_sim_charger_out_ua() > i_term);
    printf("    model, ROM loader running (load %.1f mA, a guess): after 9 h the charger still charges, "
           "%.2f mA out, cell held at %.1f %% - NO termination (NOT MET in hardware alone)\n",
           gl_sim_load_ua() / 1000.0, gl_sim_charger_out_ua() / 1000.0, 100.0 * (double)gl_sim_cell_soc());
    for (int k = 0; k < 90; k++) {
        gl_sim_advance_ms(60000);
    }
    if (GL_PROV_BQ25101_SAFETY_TIMER_H != 0u) {
        /* the charger's own timer (GL_PROV_BQ25101_SAFETY_TIMER_H, FROM MEMORY) */
        GL_CHECK_EQ(gl_sim_charger_state(), GL_SIM_CHG_TIMER);
        GL_CHECK_EQ(gl_sim_stats()->chg_timer_faults, 1u);
        printf("    ... until the charger's own safety timer (%u h, from memory of the family: "
               "PROVISIONAL) ends it\n", (unsigned)GL_PROV_BQ25101_SAFETY_TIMER_H);
    } else {
        GL_CHECK(gl_sim_charger_on());
    }
    GL_CHECK_EQ(gl_sim_stats()->chg_hw_outside_us, 0u);
}

int main(void)
{
    GL_RUN(test_init_leaves_the_charger_in_its_hardware_default);
    GL_RUN(test_conversion_and_percent);
    GL_RUN(test_ntc_conversion_against_a_table);
    GL_RUN(test_ntc_error_budget_at_the_limits);
    GL_RUN(test_measure_exact_adc_and_bias_sequence);
    GL_RUN(test_ntc_open_short_and_stuck_are_detected);
    GL_RUN(test_charge_gate_window_guard_and_hysteresis);
    GL_RUN(test_charge_gate_unknown_faulty_and_implausible_temperatures);
    GL_RUN(test_charge_time_limit_of_6_hours);
    GL_RUN(test_backstop_does_not_depend_on_the_status_line);
    GL_RUN(test_read_gate_does_not_believe_an_implausible_ntc);
    GL_RUN(test_charge_stop_by_command);
    GL_RUN(test_charger_status_inference);
    GL_RUN(test_read_gate_at_60_c);
    GL_RUN(test_charger_rules_of_the_simulator);
    GL_RUN(test_status_pins_and_interrupts);
    GL_RUN(test_hardware_model_charger_alone_over_temperature);
    GL_RUN(test_hardware_model_termination_needs_a_small_load);
    return gl_test_summary();
}
