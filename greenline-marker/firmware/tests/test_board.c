/*
 * test_board.c - the rules of the rev E board (DESIGN_SPEC section 4,
 * electrical/gl1_main/NETLIST_NOTES.md section 7) as the HAL and the
 * simulator see them, below the application:
 *
 *   - the lines WITHOUT a board resistor, which float in reset: gl_hal_init()
 *     gives each its level before it touches any other pin;
 *   - the chip selects during reset: the board's pull resistors hold them
 *     inactive, and gl_hal_init() takes each pin over at that very level;
 *   - the pins gl_hal_init() must NOT drive: CHG_INHIBIT, NTC_BIAS, the
 *     charger's status input (no internal pull), the camera-facing pins;
 *   - every pin in its resting state of the pin map when the marker sleeps;
 *   - the core clock: gl_hal_clock_set() is recorded, costs its lock time,
 *     can fail, and the rules about it (pairing, no Stop mode while fast,
 *     no heavy computation while slow) are counted;
 *   - EXTCOMIN: the LCD driver divides 32768 Hz by 547;
 *   - the MCU reset of the model (gl_sim_mcu_reset), which the charger
 *     tests use for "reset" and "watchdog reset".
 *
 * The charger and the cell thermistor are in tests/test_drv_power.c and,
 * with the whole firmware, in tests/test_e2e_faults.c and
 * tests/test_e2e_power.c.
 */
#include "gl_test.h"

#include "gl_pins.h"
#include "gl_provisional.h"
#include "gl_trace_util.h"
#include "ls013b7dh03.h"
#include "lsm6dsv16x.h"
#include "mx25r.h"

typedef struct {
    gl_pin_t pin;
    bool level;    /* the level the board's resistor gives the undriven pin */
    bool handover; /* gl_hal_init() makes it an output at that level */
} reset_row_t;
#define RROW(logical, level, handover) { logical, (level) != 0, (handover) != 0 },
static const reset_row_t reset_[] = { GL_PINS_RESET_TABLE(RROW) };
#undef RROW

#define FROW(logical) logical,
static const gl_pin_t floating_[] = { GL_PINS_FLOATING_TABLE(FROW) };
#undef FROW

typedef struct {
    gl_pin_t pin;
    int fn, pull, rail, sleep;
} pin_row_t;
#define PROW(logical, port, pin, pad, fn, af, pull, board, exti, rail, sleep, src) \
    { logical, fn, pull, rail, sleep },
static const pin_row_t pins_[] = { GL_PINS_TABLE(PROW) };
#undef PROW

GL_TEST(test_chip_selects_are_inactive_through_reset_and_init)
{
    gl_sim_reset(true);
    /* MCU in reset: every pin analog; the pulls decide */
    for (size_t i = 0; i < GL_ARRAY_LEN(reset_); i++) {
        GL_CHECK_EQ(gl_sim_pin_mode(reset_[i].pin), GL_PIN_MODE_ANALOG);
        GL_CHECK_EQ(gl_sim_pin_level(reset_[i].pin), reset_[i].level);
    }
    /* the gate of the charger's stop MOSFET is held off: the charger is free */
    GL_CHECK(!gl_sim_pin_level(GL_PIN_CHG_INHIBIT));
    GL_CHECK(!gl_sim_pin_level(GL_PIN_LCD_SCS));  /* active high: not selected */
    GL_CHECK(!gl_sim_pin_level(GL_PIN_LCD_DISP)); /* display off */
    GL_CHECK(gl_sim_pin_level(GL_PIN_FLASH_CS));  /* active low: not selected */
    GL_CHECK(gl_sim_pin_level(GL_PIN_IMU_CS));
    GL_CHECK(!gl_sim_pin_level(GL_PIN_CAM_PWR_EN) && !gl_sim_cam_rail_on());
    GL_CHECK(!gl_sim_lcd()->disp);

    /* the hand-over: for each of these pins the FIRST thing gl_hal_init()
     * does is write the latch to the pull's level, the second is to make it
     * an output - so the pin never moves */
    GL_CHECK_EQ(gl_hal_init(), GL_OK);
    for (size_t i = 0; i < GL_ARRAY_LEN(reset_); i++) {
        const long w = tr_find(0, GL_SIM_TR_GPIO_WRITE, (int)reset_[i].pin);
        const long m = tr_find(0, GL_SIM_TR_GPIO_MODE, (int)reset_[i].pin);
        if (!reset_[i].handover) {
            /* an input, an analog pin, or an output that rests analog
             * (CHG_INHIBIT, the PWDN line on the BOOT0 pad): gl_hal_init()
             * never drives it */
            GL_CHECK(w < 0);
            GL_CHECK(!gl_sim_pin_drives_high(reset_[i].pin) && !gl_sim_pin_drives_low(reset_[i].pin));
            GL_CHECK_EQ(gl_sim_pin_level(reset_[i].pin), reset_[i].level);
            continue;
        }
        GL_CHECK(w >= 0 && m > w);
        if (w >= 0 && m > w) {
            GL_CHECK_EQ(gl_sim_trace_at((size_t)w)->b, reset_[i].level ? 1u : 0u);
            GL_CHECK_EQ(gl_sim_trace_at((size_t)m)->b, (unsigned)GL_PIN_MODE_OUTPUT_PP);
            /* nothing touches the pin between the two */
            for (long k = w + 1; k < m; k++) {
                const gl_sim_trace_t *t = gl_sim_trace_at((size_t)k);
                GL_CHECK(!((t->type == (uint8_t)GL_SIM_TR_GPIO_WRITE ||
                            t->type == (uint8_t)GL_SIM_TR_GPIO_MODE) &&
                           t->a == (uint8_t)reset_[i].pin));
            }
        }
        GL_CHECK_EQ(gl_sim_pin_level(reset_[i].pin), reset_[i].level);
    }
    /* the level of every one of them at every record of the trace: replay */
    {
        uint8_t mode[GL_PIN_COUNT];
        bool latch[GL_PIN_COUNT];
        unsigned active = 0;
        memset(latch, 0, sizeof(latch));
        memset(mode, (int)GL_PIN_MODE_ANALOG, sizeof(mode));
        for (size_t k = 0; k < gl_sim_trace_count(); k++) {
            const gl_sim_trace_t *t = gl_sim_trace_at(k);
            if (t->type == (uint8_t)GL_SIM_TR_GPIO_MODE) {
                mode[t->a] = (uint8_t)t->b;
            } else if (t->type == (uint8_t)GL_SIM_TR_GPIO_WRITE) {
                latch[t->a] = (t->b != 0u);
            } else {
                continue;
            }
            for (size_t i = 0; i < GL_ARRAY_LEN(reset_); i++) {
                const gl_pin_t p = reset_[i].pin;
                const bool driven = (mode[p] == (uint8_t)GL_PIN_MODE_OUTPUT_PP);
                const bool level = driven ? latch[p] : reset_[i].level;
                active += (level != reset_[i].level) ? 1u : 0u;
            }
        }
        GL_CHECK_EQ(active, 0u);
        printf("    reset and gl_hal_init(): %u of the %u trace records leave a chip select, DISP, "
               "the camera rail enable or the charger's stop away from its pull level\n", active,
               (unsigned)gl_sim_trace_count());
    }
    GL_CHECK_EQ(gl_sim_violation_total(), 0);

    /* the drivers start from there without a spurious selection: no SPI
     * byte reaches a device that is not addressed */
    {
        static gl_lcd_t lcd;
        static gl_mx25r_t flash;
        static gl_imu_t imu;
        gl_lcd_init(&lcd, NULL);
        GL_CHECK_EQ(gl_mx25r_init(&flash), GL_OK);
        GL_CHECK_EQ(gl_imu_init(&imu, NULL), GL_OK);
        GL_CHECK_EQ(gl_sim_violations()->spi, 0u);
        GL_CHECK_EQ(gl_sim_violations()->lcd, 0u);
    }
    /* an internal pull against the board's resistor is caught */
    gl_hal_gpio_mode(GL_PIN_FLASH_CS, GL_PIN_MODE_INPUT_PULLDOWN);
    GL_CHECK_EQ(gl_sim_violations()->spi, 1u);
    gl_hal_gpio_mode(GL_PIN_LCD_SCS, GL_PIN_MODE_INPUT_PULLUP);
    GL_CHECK_EQ(gl_sim_violations()->spi, 2u);
}

/* Rev E, firmware note 15: six lines have no resistor on the board and float
 * while the MCU is in reset or in the ROM loader (EXTCOMIN, the clock and
 * data-out lines of both SPI buses, the left camera's PWDN).  gl_hal_init()
 * gives each its level BEFORE it configures any other pin, and none of them
 * is left floating afterwards.  Notes 3 and 5: the charger's status input
 * gets no internal pull and is never driven (it is a USB Type-C CC pad). */
GL_TEST(test_floating_lines_get_their_level_first)
{
    size_t first_other = SIZE_MAX, last_floating = 0;
    unsigned n_float_records = 0;

    gl_sim_reset(true);
    for (size_t i = 0; i < GL_ARRAY_LEN(floating_); i++) {
        /* in reset: analog, and nothing on the board holds them */
        GL_CHECK_EQ(gl_sim_pin_mode(floating_[i]), GL_PIN_MODE_ANALOG);
    }
    GL_CHECK_EQ(gl_hal_init(), GL_OK);
    for (size_t k = 0; k < gl_sim_trace_count(); k++) {
        const gl_sim_trace_t *t = gl_sim_trace_at(k);
        bool is_floating = false;
        if (t->type != (uint8_t)GL_SIM_TR_GPIO_MODE && t->type != (uint8_t)GL_SIM_TR_GPIO_WRITE) {
            continue;
        }
        for (size_t i = 0; i < GL_ARRAY_LEN(floating_); i++) {
            is_floating = is_floating || (t->a == (uint8_t)floating_[i]);
        }
        if (is_floating && first_other == SIZE_MAX) {
            n_float_records++;
            last_floating = k;
        } else if (!is_floating && first_other == SIZE_MAX) {
            first_other = k;
        }
    }
    /* each of them written low and made an output (2 records each) before
     * the first record of any other pin */
    GL_CHECK_EQ(n_float_records, 2u * (unsigned)GL_ARRAY_LEN(floating_));
    GL_CHECK(first_other != SIZE_MAX && last_floating < first_other);
    for (size_t i = 0; i < GL_ARRAY_LEN(floating_); i++) {
        const long w = tr_find(0, GL_SIM_TR_GPIO_WRITE, (int)floating_[i]);
        const long m = tr_find(0, GL_SIM_TR_GPIO_MODE, (int)floating_[i]);
        const gl_pin_mode_t mode = gl_sim_pin_mode(floating_[i]);
        GL_CHECK(w >= 0 && m > w && (size_t)m < first_other);
        if (w >= 0 && m > w) {
            GL_CHECK_EQ(gl_sim_trace_at((size_t)w)->b, 0u);
            GL_CHECK_EQ(gl_sim_trace_at((size_t)m)->b, (unsigned)GL_PIN_MODE_OUTPUT_PP);
        }
        /* afterwards: driven low, or handed to its bus peripheral */
        GL_CHECK(gl_sim_pin_drives_low(floating_[i]) || mode == GL_PIN_MODE_ALTERNATE);
    }
    printf("    gl_hal_init(): the first %u pin records are the %u lines that float in reset, each "
           "written low and then made an output\n", n_float_records, (unsigned)GL_ARRAY_LEN(floating_));
    /* the pins gl_hal_init() must leave alone */
    GL_CHECK(tr_find(0, GL_SIM_TR_GPIO_WRITE, (int)GL_PIN_CHG_INHIBIT) < 0);
    GL_CHECK(tr_find(0, GL_SIM_TR_GPIO_MODE, (int)GL_PIN_CHG_INHIBIT) < 0);
    GL_CHECK(tr_find(0, GL_SIM_TR_GPIO_WRITE, (int)GL_PIN_NTC_BIAS) < 0);
    GL_CHECK(tr_find(0, GL_SIM_TR_GPIO_MODE, (int)GL_PIN_NTC_BIAS) < 0);
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_CHG_INHIBIT), GL_PIN_MODE_ANALOG);
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_NTC_BIAS), GL_PIN_MODE_ANALOG);
    /* interrupt inputs: plain inputs, no internal pull */
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_CHG_STAT), GL_PIN_MODE_INPUT);
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_VBUS_SENSE), GL_PIN_MODE_INPUT);
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_IMU_INT1), GL_PIN_MODE_INPUT);
    GL_CHECK_EQ(gl_sim_pin_mode(GL_PIN_IMU_INT2), GL_PIN_MODE_INPUT);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
    /* every camera-facing pin is parked: analog, or driven low */
    for (size_t i = 0; i < GL_ARRAY_LEN(pins_); i++) {
        if (pins_[i].rail == GL_PINRAIL_PARKED) {
            GL_CHECK(gl_sim_pin_mode(pins_[i].pin) == GL_PIN_MODE_ANALOG || gl_sim_pin_drives_low(pins_[i].pin));
        }
    }
    /* the rules the model has for the two charger pins */
    gl_hal_gpio_mode(GL_PIN_CHG_STAT, GL_PIN_MODE_INPUT_PULLUP); /* an internal pull on the CC pad */
    GL_CHECK_EQ(gl_sim_violations()->power, 1u);
    gl_hal_gpio_mode(GL_PIN_CHG_STAT, GL_PIN_MODE_OUTPUT_PP);    /* driven */
    GL_CHECK_EQ(gl_sim_violations()->power, 2u);
    gl_hal_gpio_mode(GL_PIN_CHG_STAT, GL_PIN_MODE_INPUT);
    GL_CHECK_EQ(gl_sim_violations()->power, 2u);
    gl_hal_gpio_write(GL_PIN_CHG_INHIBIT, true);
    gl_hal_gpio_mode(GL_PIN_CHG_INHIBIT, GL_PIN_MODE_OUTPUT_OD); /* an open-drain "high" stops nothing */
    GL_CHECK_EQ(gl_sim_violations()->power, 3u);
    GL_CHECK(!gl_sim_pin_level(GL_PIN_CHG_INHIBIT));
    gl_hal_gpio_mode(GL_PIN_CHG_INHIBIT, GL_PIN_MODE_OUTPUT_PP); /* push-pull high: the stop */
    GL_CHECK_EQ(gl_sim_violations()->power, 3u);
    GL_CHECK(gl_sim_pin_level(GL_PIN_CHG_INHIBIT));
    gl_hal_gpio_write(GL_PIN_CHG_INHIBIT, false);
    gl_hal_gpio_mode(GL_PIN_CHG_INHIBIT, GL_PIN_MODE_ANALOG);
    /* the op-amp output has a 150 kohm to the rail: driven while the op-amp
     * is off it draws through it */
    GL_CHECK_EQ(gl_sim_violations()->analog, 0u);
    gl_hal_gpio_write(GL_PIN_OPAMP_VOUT, false);
    gl_hal_gpio_mode(GL_PIN_OPAMP_VOUT, GL_PIN_MODE_OUTPUT_PP);
    GL_CHECK_EQ(gl_sim_violations()->analog, 1u);
}

GL_TEST(test_mcu_reset_of_the_model)
{
    static gl_lcd_t lcd;
    gl_sim_reset(true);
    GL_CHECK_EQ(gl_hal_init(), GL_OK);
    gl_lcd_init(&lcd, NULL);
    GL_CHECK_EQ(gl_lcd_on(&lcd), GL_OK);
    GL_CHECK(gl_sim_lcd()->disp && gl_sim_lcd()->extcomin);
    GL_CHECK_EQ(gl_hal_clock_set(GL_CLOCK_FAST), GL_OK);
    gl_hal_gpio_write(GL_PIN_CAM_PWR_EN, true); /* rail on */
    GL_CHECK(gl_sim_cam_rail_on());
    gl_sim_advance_ms(2);
    /* a watchdog reset in the middle of everything */
    gl_sim_mcu_reset(GL_RESET_WATCHDOG);
    for (int p = 0; p < (int)GL_PIN_COUNT; p++) {
        GL_CHECK_EQ(gl_sim_pin_mode((gl_pin_t)p), GL_PIN_MODE_ANALOG);
    }
    GL_CHECK(!gl_sim_cam_rail_on());                         /* pull-down on the enable */
    GL_CHECK(!gl_sim_lcd()->disp && !gl_sim_lcd()->extcomin); /* pull-down, LPTIM reset */
    for (size_t i = 0; i < GL_ARRAY_LEN(reset_); i++) {
        if (reset_[i].pin == GL_PIN_CHG_STAT) {
            continue; /* the charger's open drain decides against the pull-up */
        }
        GL_CHECK_EQ(gl_sim_pin_level(reset_[i].pin), reset_[i].level);
    }
    GL_CHECK_EQ(gl_sim_clock(), GL_CLOCK_SLOW);
    GL_CHECK_EQ(gl_sim_violation_total(), 0); /* all pins at once: no rail-rule violation */
    GL_CHECK_EQ(gl_hal_init(), GL_OK);
    GL_CHECK_EQ(gl_hal_reset_reason(), GL_RESET_WATCHDOG);
    GL_CHECK_EQ(gl_hal_clock_get(), GL_CLOCK_SLOW);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

GL_TEST(test_core_clock_calls_are_recorded_and_checked)
{
    const gl_sim_stats_t *st;
    uint64_t t0;

    gl_sim_reset(true);
    GL_CHECK_EQ(gl_hal_init(), GL_OK);
    GL_CHECK_EQ(gl_hal_clock_get(), GL_CLOCK_SLOW);
    /* stop before start, twice: safe */
    GL_CHECK_EQ(gl_hal_clock_set(GL_CLOCK_SLOW), GL_OK);
    GL_CHECK_EQ(gl_hal_clock_set(GL_CLOCK_SLOW), GL_OK);
    GL_CHECK_EQ(gl_sim_stats()->clock_to_fast, 0u);
    GL_CHECK_EQ(gl_sim_stats()->clock_calls, 2u);

    /* up: takes the PLL lock time; idempotent */
    t0 = gl_sim_now_us();
    GL_CHECK_EQ(gl_hal_clock_set(GL_CLOCK_FAST), GL_OK);
    GL_CHECK(gl_sim_now_us() - t0 >= 50u && gl_sim_now_us() - t0 <= 1000u);
    GL_CHECK_EQ(gl_hal_clock_get(), GL_CLOCK_FAST);
    GL_CHECK_EQ(gl_hal_clock_set(GL_CLOCK_FAST), GL_OK);
    GL_CHECK_EQ(gl_sim_stats()->clock_to_fast, 1u);
    gl_hal_delay_ms(7);
    /* heavy work while fast is fine ... */
    gl_hal_trace(GL_TRACE_VISION_STRIP, 0u);
    gl_hal_trace(GL_TRACE_SOLVE, 0u);
    GL_CHECK_EQ(gl_sim_stats()->heavy_while_slow, 0u);
    /* ... Stop mode is not */
    gl_hal_irq_enable(GL_IRQ_WAKE_TIMER, true);
    gl_hal_wake_timer_start(3);
    (void)gl_hal_sleep(GL_SLEEP_IDLE);
    GL_CHECK_EQ(gl_sim_violations()->clock, 0u);
    (void)gl_hal_irq_take();
    gl_hal_wake_timer_start(3);
    (void)gl_hal_sleep(GL_SLEEP_STOP);
    GL_CHECK_EQ(gl_sim_violations()->clock, 1u);
    (void)gl_hal_irq_take();
    /* down */
    GL_CHECK_EQ(gl_hal_clock_set(GL_CLOCK_SLOW), GL_OK);
    st = gl_sim_stats();
    GL_CHECK_EQ(st->clock_to_fast, 1u);
    GL_CHECK_EQ(st->clock_to_slow, 1u);
    /* 7 ms + two 3 ms sleeps + the lock time, and the computation the two
     * trace points above were charged (the cost model, gl_sim_cost.h) */
    GL_CHECK(st->compute_us == st->stage_us[GL_TRACE_VISION_STRIP] + st->stage_us[GL_TRACE_SOLVE]);
    GL_CHECK(st->clock_fast_us - st->compute_us >= 13000u &&
             st->clock_fast_us - st->compute_us < 14500u);
    gl_hal_wake_timer_start(3);
    (void)gl_hal_sleep(GL_SLEEP_STOP);
    GL_CHECK_EQ(gl_sim_violations()->clock, 1u);
    (void)gl_hal_irq_take();
    /* heavy work at the slow clock is counted (a statistic, not a rule: the
     * driver-level tests run the vision without an application) */
    gl_hal_trace(GL_TRACE_VISION_BAND, 0u);
    GL_CHECK_EQ(gl_sim_stats()->heavy_while_slow, 1u);

    /* the trace: every call, with the clock before it */
    {
        unsigned calls = 0;
        gl_clock_t clock = GL_CLOCK_SLOW;
        for (size_t i = 0; i < gl_sim_trace_count(); i++) {
            const gl_sim_trace_t *t = gl_sim_trace_at(i);
            if (t->type != (uint8_t)GL_SIM_TR_CLOCK) {
                continue;
            }
            calls++;
            GL_CHECK_EQ(t->b, (unsigned)clock);
            clock = (gl_clock_t)t->a;
        }
        GL_CHECK_EQ(calls, gl_sim_stats()->clock_calls);
        GL_CHECK_EQ(calls, 5u);
        GL_CHECK_EQ(clock, GL_CLOCK_SLOW);
    }
    /* a PLL that does not lock: an error, and the clock is still slow */
    gl_sim_clock_fail(1);
    GL_CHECK_EQ(gl_hal_clock_set(GL_CLOCK_FAST), GL_ERR_IO);
    GL_CHECK_EQ(gl_hal_clock_get(), GL_CLOCK_SLOW);
    GL_CHECK_EQ(gl_hal_clock_set(GL_CLOCK_FAST), GL_OK);
    GL_CHECK_EQ(gl_hal_clock_set(GL_CLOCK_SLOW), GL_OK);
    GL_CHECK_EQ(gl_sim_stats()->clock_to_fast, gl_sim_stats()->clock_to_slow);
    /* a switch BACK that does not take place: an error, and the clock is
     * still fast (the caller must not believe otherwise) */
    GL_CHECK_EQ(gl_hal_clock_set(GL_CLOCK_FAST), GL_OK);
    gl_sim_clock_fail_slow(1);
    GL_CHECK_EQ(gl_hal_clock_set(GL_CLOCK_SLOW), GL_ERR_IO);
    GL_CHECK_EQ(gl_hal_clock_get(), GL_CLOCK_FAST);
    GL_CHECK_EQ(gl_hal_clock_set(GL_CLOCK_SLOW), GL_OK);
    GL_CHECK_EQ(gl_hal_clock_get(), GL_CLOCK_SLOW);
    GL_CHECK_EQ(gl_sim_stats()->clock_to_fast, gl_sim_stats()->clock_to_slow);
    /* bus timing does not follow the core clock: the same SPI transfer takes
     * the same time either way */
    {
        static gl_mx25r_t flash;
        uint64_t slow_us, fast_us;
        uint8_t buf[64];
        GL_CHECK_EQ(gl_mx25r_init(&flash), GL_OK);
        t0 = gl_sim_now_us();
        GL_CHECK_EQ(gl_mx25r_read(&flash, 0, buf, sizeof(buf)), GL_OK);
        slow_us = gl_sim_now_us() - t0;
        GL_CHECK_EQ(gl_hal_clock_set(GL_CLOCK_FAST), GL_OK);
        t0 = gl_sim_now_us();
        GL_CHECK_EQ(gl_mx25r_read(&flash, 0, buf, sizeof(buf)), GL_OK);
        fast_us = gl_sim_now_us() - t0;
        GL_CHECK_EQ(gl_hal_clock_set(GL_CLOCK_SLOW), GL_OK);
        GL_CHECK_EQ(slow_us, fast_us);
    }
}

GL_TEST(test_extcomin_divides_32768_by_547)
{
    static gl_lcd_t lcd;
    long i;
    gl_sim_reset(true);
    GL_CHECK_EQ(gl_hal_init(), GL_OK);
    gl_lcd_init(&lcd, NULL);
    gl_sim_trace_clear();
    GL_CHECK_EQ(gl_lcd_on(&lcd), GL_OK);
    i = tr_find(0, GL_SIM_TR_EXTCOMIN, 1);
    GL_CHECK(i >= 0);
    if (i >= 0) {
        GL_CHECK_EQ(gl_sim_trace_at((size_t)i)->c, 547u);
    }
    GL_CHECK_EQ(gl_sim_lcd()->extcomin_period, 547);
    GL_CHECK_EQ(GL_PINS_EXTCOMIN_LSE_TICKS, 547);
    printf("    EXTCOMIN: 32768 / %u = %.3f Hz\n", (unsigned)gl_sim_lcd()->extcomin_period,
           32768.0 / (double)gl_sim_lcd()->extcomin_period);
    gl_lcd_off(&lcd);
    /* the divider of the old spec text (546 -> 60.015 Hz) is outside the
     * 1-60 Hz range and the model says so */
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
    gl_hal_gpio_mode(GL_PIN_LCD_EXTCOMIN, GL_PIN_MODE_ALTERNATE);
    GL_CHECK_EQ(gl_hal_extcomin_start(546), GL_OK);
    GL_CHECK(gl_sim_violations()->lcd >= 1u);
    gl_hal_extcomin_stop();
}

/*
 * The STM32 backend cannot be run here (no vendor sources, no target).  Two
 * properties of its start-up are checked on its SOURCE TEXT, because the
 * review found them violated and a compile cannot show them:
 *
 *   - gl_hal_init() starts the independent watchdog before the clock set-up
 *     and before anything that can return or hang (it used to start it
 *     LAST, and a clock error returned before it: the application's first
 *     delay then waited for ever, with no watchdog);
 *   - gl_hal_init() has ONE return statement, at its end: no error path
 *     leaves before the pins, the cycle counter and the tick exist.
 *
 * This is a check of the text, not of behaviour: it says the order is as
 * written, not that the order works on the part.
 */
static char backend_src_[160000];

static const char *after_(const char *from, const char *what)
{
    const char *p = (from != NULL) ? strstr(from, what) : NULL;
    return p;
}

GL_TEST(test_backend_starts_the_watchdog_first)
{
    FILE *f = fopen("hal/stm32u5/gl_hal_stm32u5.c", "rb");
    size_t n = 0;
    const char *body, *end, *wdg, *clocks, *dfu, *halinit, *p;
    unsigned returns = 0;

    GL_CHECK(f != NULL); /* the tests are run from the firmware directory (make test) */
    if (f == NULL) {
        return;
    }
    n = fread(backend_src_, 1, sizeof(backend_src_) - 1u, f);
    fclose(f);
    backend_src_[n] = '\0';
    GL_CHECK(n > 30000u && n < sizeof(backend_src_) - 1u);
    body = after_(backend_src_, "\ngl_status_t gl_hal_init(void)\n{");
    GL_CHECK(body != NULL);
    end = after_(body, "\n}\n");
    GL_CHECK(end != NULL);
    if (body == NULL || end == NULL) {
        return;
    }
    dfu = after_(body, "dfu_check_();");
    halinit = after_(body, "HAL_Init()");
    wdg = after_(body, "HAL_IWDG_Init(&hiwdg_)");
    clocks = after_(body, "clocks_init_();");
    GL_CHECK(dfu != NULL && halinit != NULL && wdg != NULL && clocks != NULL);
    if (dfu == NULL || halinit == NULL || wdg == NULL || clocks == NULL) {
        return;
    }
    GL_CHECK(dfu < halinit && halinit < wdg && wdg < clocks && clocks < end);
    for (p = body; (p = strstr(p, "return ")) != NULL && p < end; p++) {
        /* a statement: only blanks between the start of the line and it */
        const char *q = p;
        while (q > body && q[-1] == ' ') {
            q--;
        }
        if (q[-1] != '\n') {
            continue; /* the word in a comment */
        }
        returns++;
        GL_CHECK(p > clocks); /* nothing returns before the watchdog runs */
    }
    printf("    hal/stm32u5/gl_hal_stm32u5.c, gl_hal_init(): the watchdog is started %ld characters "
           "before the clock set-up; %u return statement(s) in the function\n", (long)(clocks - wdg),
           returns);
    GL_CHECK_EQ(returns, 1);
    /* the delays have a second exit */
    p = after_(backend_src_, "\nvoid gl_hal_delay_us(uint32_t us)\n{");
    GL_CHECK(p != NULL && after_(p, "pass < cycles") != NULL &&
             after_(p, "pass < cycles") < after_(p, "\n}\n"));
    p = after_(backend_src_, "\nvoid gl_hal_delay_ms(uint32_t ms)\n{");
    GL_CHECK(p != NULL && after_(p, "HAL_GetTick()") != NULL &&
             after_(p, "HAL_GetTick()") < after_(p, "\n}\n"));
}

/* The same kind of check for what the rev E board asks of the backend
 * (electrical/gl1_main, firmware notes 4, 5, 7, 13, 15): the ORDER of
 * gl_hal_init() and the absence of things that were right for the old board.
 * A check of the TEXT of a file that has been compiled and never run. */
GL_TEST(test_backend_follows_the_rev_e_notes_in_text)
{
    FILE *f = fopen("hal/stm32u5/gl_hal_stm32u5.c", "rb");
    size_t n = 0;
    const char *body, *end, *ucpd, *dfu, *ship, *floating, *reset, *analog, *inputs;

    GL_CHECK(f != NULL);
    if (f == NULL) {
        return;
    }
    n = fread(backend_src_, 1, sizeof(backend_src_) - 1u, f);
    fclose(f);
    backend_src_[n] = '\0';
    body = after_(backend_src_, "\ngl_status_t gl_hal_init(void)\n{");
    end = after_(body, "\n}\n");
    GL_CHECK(body != NULL && end != NULL);
    if (body == NULL || end == NULL) {
        return;
    }
    /* note 5: UCPD_DBDIS before anything else, the ROM hand-over included */
    ucpd = after_(body, "HAL_PWREx_DisableUCPDDeadBattery();");
    dfu = after_(body, "dfu_check_();");
    ship = after_(body, "ship_check_();");
    GL_CHECK(ucpd != NULL && dfu != NULL && ship != NULL);
    GL_CHECK(ucpd < dfu && dfu < ship && ship < after_(body, "HAL_Init()"));
    GL_CHECK(after_(body, "gl_hal_gpio_mode(") > ucpd && after_(body, "HAL_GPIO_") > ucpd);
    /* note 15 and the order of gl_hal.h: floating lines, then the lines a
     * resistor holds, then everything else analog, then the inputs */
    floating = after_(body, "GL_PINS_FLOATING_TABLE(");
    reset = after_(body, "GL_PINS_RESET_TABLE(");
    analog = after_(body, "GL_PIN_MODE_ANALOG);");
    inputs = after_(body, "gl_hal_gpio_mode(GL_PIN_CHG_STAT, GL_PIN_MODE_INPUT);");
    GL_CHECK(floating != NULL && reset != NULL && analog != NULL && inputs != NULL);
    GL_CHECK(floating < reset && reset < analog && analog < inputs && inputs < end);
    /* note 3: no internal pull on CHG_STAT, anywhere in the file */
    GL_CHECK(after_(backend_src_, "GL_PIN_CHG_STAT, GL_PIN_MODE_INPUT_PULLUP") == NULL);
    GL_CHECK(after_(backend_src_, "GL_PIN_CHG_STAT, GL_PIN_MODE_INPUT_PULLDOWN") == NULL);
    /* nothing in gl_hal_init() drives CHG_INHIBIT or NTC_BIAS */
    {
        const char *p1 = after_(body, "GL_PIN_CHG_INHIBIT,"), *p2 = after_(body, "GL_PIN_NTC_BIAS,");
        GL_CHECK(p1 == NULL || p1 > end);
        GL_CHECK(p2 == NULL || p2 > end);
    }
    /* note 4: no interrupt line named by a number - vectors, NVIC lines and
     * pin masks are built from the generated GL_PINS_EXTI_* */
    {
        static const char *const banned[] = { "EXTI0_IRQ", "EXTI5_IRQ", "EXTI7_IRQ", "EXTI9_IRQ",
                                              "EXTI13_IRQ", "EXTI15_IRQ", "GPIO_PIN_13", "GPIO_PIN_15",
                                              "GPIO_PIN_5)", "GPIO_PIN_7)", "GPIO_PIN_9", "GPIO_PIN_0)" };
        for (size_t i = 0; i < sizeof(banned) / sizeof(banned[0]); i++) {
            GL_CHECK(after_(backend_src_, banned[i]) == NULL);
        }
        GL_CHECK(after_(backend_src_, "GLH_EXTI_HANDLER(GL_PINS_EXTI_IMU_INT1)") != NULL);
        GL_CHECK(after_(backend_src_, "GLH_EXTI_HANDLER(GL_PINS_EXTI_IMU_INT2)") != NULL);
        GL_CHECK(after_(backend_src_, "GLH_EXTI_HANDLER(GL_PINS_EXTI_VBUS_SENSE)") != NULL);
        GL_CHECK(after_(backend_src_, "GLH_EXTI_HANDLER(GL_PINS_EXTI_CHG_STAT)") != NULL);
    }
    /* note 7: the supply-valid condition is VBUS_SENSE AND the monitor of
     * the supply pin, and the valid bit is cleared in both handlers */
    {
        const char *fn = after_(backend_src_, "\nbool gl_hal_usb_supply_ok(void)\n{");
        const char *fe = after_(fn, "\n}\n");
        GL_CHECK(fn != NULL && fe != NULL);
        if (fn != NULL && fe != NULL) {
            const char *a = after_(fn, "gl_hal_gpio_read(GL_PIN_VBUS_SENSE)");
            const char *b = after_(fn, "PWR_FLAG_VDDUSBRDY");
            GL_CHECK(a != NULL && a < fe && b != NULL && b < fe);
        }
        fn = after_(backend_src_, "\nvoid HAL_PWREx_UVMCallback(void)\n{");
        GL_CHECK(fn != NULL && after_(fn, "HAL_PWREx_DisableVddUSB();") < after_(fn, "\n}\n"));
        fn = after_(backend_src_, "\nstatic void exti_event_(uint16_t gpio_pin, bool rising)\n{");
        GL_CHECK(fn != NULL && after_(fn, "HAL_PWREx_DisableVddUSB();") < after_(fn, "\n}\n"));
    }
    /* ship mode: Shutdown through the wake-up pin, the marker written first */
    {
        const char *fn = after_(backend_src_, "\nvoid gl_hal_ship_mode_enter(void)\n{");
        const char *fe = after_(fn, "\n}\n");
        GL_CHECK(fn != NULL && fe != NULL);
        if (fn != NULL && fe != NULL) {
            const char *vb = after_(fn, "gl_hal_gpio_read(GL_PIN_VBUS_SENSE)");
            const char *mk = after_(fn, "TAMP->BKP2R = GLH_SHIP_MAGIC;");
            const char *sd = after_(fn, "ship_shutdown_();");
            GL_CHECK(vb != NULL && mk != NULL && sd != NULL && vb < mk && mk < sd && sd < fe);
        }
        fn = after_(backend_src_, "\nstatic void ship_shutdown_(void)\n{");
        GL_CHECK(fn != NULL && after_(fn, "HAL_PWR_EnableWakeUpPin(GLH_WKUP_VBUS_HIGH);") != NULL &&
                 after_(fn, "HAL_PWR_EnableWakeUpPin(GLH_WKUP_VBUS_HIGH);") <
                     after_(fn, "HAL_PWREx_EnterSHUTDOWNMode();"));
    }
    printf("    hal/stm32u5/gl_hal_stm32u5.c: UCPD_DBDIS is the first call of gl_hal_init(), %ld "
           "characters before the first pin is configured; pin order floating / held / analog / "
           "inputs as written (TEXT only: compiled, never run)\n",
           (long)(after_(body, "gl_hal_gpio_mode(") - ucpd));
}

int main(void)
{
    GL_RUN(test_chip_selects_are_inactive_through_reset_and_init);
    GL_RUN(test_floating_lines_get_their_level_first);
    GL_RUN(test_mcu_reset_of_the_model);
    GL_RUN(test_core_clock_calls_are_recorded_and_checked);
    GL_RUN(test_extcomin_divides_32768_by_547);
    GL_RUN(test_backend_starts_the_watchdog_first);
    GL_RUN(test_backend_follows_the_rev_e_notes_in_text);
    return gl_test_summary();
}
