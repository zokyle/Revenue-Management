/*
 * test_board.c - the board changes of DESIGN_SPEC rev C2 section 4 as the
 * HAL and the simulator see them, below the application:
 *
 *   - the chip selects during reset: the board's pull resistors hold them
 *     inactive, and gl_hal_init() takes each pin over at that very level;
 *   - the core clock: gl_hal_clock_set() is recorded, costs its lock time,
 *     can fail, and the rules about it (pairing, no Stop mode while fast,
 *     no heavy computation while slow) are counted;
 *   - EXTCOMIN: the LCD driver divides 32768 Hz by 547;
 *   - the MCU reset of the model (gl_sim_mcu_reset), which the charger
 *     tests use for "reset" and "watchdog reset".
 *
 * The charger and the cell NTC are in tests/test_drv_power.c and, with the
 * whole firmware, in tests/test_e2e_faults.c.
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
    bool level; /* the board's pull = the inactive level */
} reset_row_t;
#define RROW(logical, level) { logical, (level) != 0 },
static const reset_row_t reset_[] = { GL_PINS_RESET_TABLE(RROW) };
#undef RROW

GL_TEST(test_chip_selects_are_inactive_through_reset_and_init)
{
    gl_sim_reset(true);
    /* MCU in reset: every pin analog; the pulls decide */
    for (size_t i = 0; i < GL_ARRAY_LEN(reset_); i++) {
        GL_CHECK_EQ(gl_sim_pin_mode(reset_[i].pin), GL_PIN_MODE_ANALOG);
        GL_CHECK_EQ(gl_sim_pin_level(reset_[i].pin), reset_[i].level);
    }
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
        printf("    reset and gl_hal_init(): %u of the %u trace records leave a chip select, DISP "
               "or the camera rail enable away from its pull level\n", active,
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

int main(void)
{
    GL_RUN(test_chip_selects_are_inactive_through_reset_and_init);
    GL_RUN(test_mcu_reset_of_the_model);
    GL_RUN(test_core_clock_calls_are_recorded_and_checked);
    GL_RUN(test_extcomin_divides_32768_by_547);
    GL_RUN(test_backend_starts_the_watchdog_first);
    return gl_test_summary();
}
