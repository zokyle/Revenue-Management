/*
 * test_drv_imu.c - LSM6DSV16X driver against the simulator: exact SPI
 * bytes, configuration registers of both modes, sample scaling and axis
 * mapping, data-ready and wake-on-motion interrupts, and the core's tilt
 * pipeline fed from the driver.
 */
#include "gl_test.h"

#include "gl_provisional.h"
#include "gl_tilt.h"
#include "gl_trace_util.h"
#include "lsm6dsv16x.h"

static gl_imu_t imu_;

static void fresh_(void)
{
    gl_sim_reset(true);
    (void)gl_hal_init();
}

GL_TEST(test_init_exact_bytes)
{
    /* every byte the driver sends during gl_imu_init(), in order */
    static const uint8_t expect[] = {
        0x8F, 0xFF, /* read WHO_AM_I (0x0F | 0x80), one byte clocked in */
        0x12, 0x01, /* CTRL3: SW_RESET */
        0x12, 0x44, /* CTRL3: BDU | IF_INC */
        0x0E, 0x00, /* INT2_CTRL: no interrupts */
        0x5E, 0x00, /* MD1_CFG */
        0x50, 0x00, /* FUNCTIONS_ENABLE */
        0x10, 0x00, /* CTRL1: accelerometer off */
        0x11, 0x00  /* CTRL2: gyro off */
    };
    uint8_t bus[64];
    fresh_();
    gl_sim_trace_clear();
    GL_CHECK_EQ(gl_imu_init(&imu_, NULL), GL_OK);
    GL_CHECK_EQ(imu_.who_am_i, 0x70);
    GL_CHECK_EQ(tr_spi_bytes(0, gl_sim_trace_count(), GL_SIM_DEV_IMU, bus, sizeof(bus)),
                sizeof(expect));
    GL_CHECK_MEM(bus, expect, sizeof(expect));
    /* SPI mode 3, MSB first */
    const long i_cfg = tr_find(0, GL_SIM_TR_SPI_CFG, GL_SPI_BUS_2);
    GL_CHECK(i_cfg >= 0);
    GL_CHECK_EQ(gl_sim_trace_at((size_t)i_cfg)->b, 3u);
    /* every transfer happened with the chip select low, and it is high now */
    GL_CHECK_EQ(tr_spi_bytes(0, gl_sim_trace_count(), GL_SIM_DEV_NONE, bus, 0), 0);
    GL_CHECK(gl_sim_pin_drives_high(GL_PIN_IMU_CS));
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

GL_TEST(test_measure_mode_registers_and_scaling)
{
    const float a[3] = { 0.0125f, -0.0200f, 0.9990f };
    const float g[3] = { 0.10f, 0.0f, -0.25f };
    gl_imu_raw_t s;
    uint8_t bus[32];
    fresh_();
    GL_CHECK_EQ(gl_imu_init(&imu_, NULL), GL_OK);
    GL_CHECK_EQ(gl_imu_start_measure(&imu_), GL_OK);
    GL_CHECK_EQ(gl_sim_imu_reg(0x10), 0x07); /* CTRL1: 240 Hz, high-performance */
    GL_CHECK_EQ(gl_sim_imu_reg(0x11), 0x07); /* CTRL2: 240 Hz */
    GL_CHECK_EQ(gl_sim_imu_reg(0x12), 0x44); /* BDU | IF_INC */
    GL_CHECK_EQ(gl_sim_imu_reg(0x15), 0x03); /* +-1000 dps */
    GL_CHECK_EQ(gl_sim_imu_reg(0x17), 0x00); /* +-2 g */
    GL_CHECK_EQ(gl_sim_imu_reg(0x0E), 0x01); /* accel data ready on INT2 */
    /* CTRL4 is WRITTEN (not left to its reset value): latched data-ready
     * unless GL_PROV_IMU_DRDY_PULSED */
    GL_CHECK_EQ(gl_sim_imu_reg(0x13), (GL_PROV_IMU_DRDY_PULSED != 0) ? 0x02 : 0x00);
    {
        bool ctrl4_written = false;
        for (size_t i = 0; i < gl_sim_trace_count(); i++) {
            const gl_sim_trace_t *t = gl_sim_trace_at(i);
            const uint8_t *b = (t->type == (uint8_t)GL_SIM_TR_SPI_XFER) ? gl_sim_trace_bytes(t) : NULL;
            if (b != NULL && t->b == (uint16_t)GL_SIM_DEV_IMU && t->c == 2u && b[0] == 0x13u) {
                ctrl4_written = true;
            }
        }
        GL_CHECK(ctrl4_written);
    }
    GL_CHECK_NEAR(imu_.accel_g_per_lsb, 0.061e-3, 1e-9);
    GL_CHECK_NEAR(imu_.gyro_rad_s_per_lsb, 35.0e-3 * 3.14159265358979 / 180.0, 1e-9);
    GL_CHECK_NEAR(imu_.sample_hz, 240.0, 1e-6);

    gl_sim_imu_set_static(a, g);
    gl_hal_delay_ms(20);
    gl_sim_trace_clear();
    GL_CHECK_EQ(gl_imu_read(&imu_, &s), GL_OK);
    /* one burst: address 0x22 | read, then 12 data bytes */
    GL_CHECK_EQ(tr_spi_bytes(0, gl_sim_trace_count(), GL_SIM_DEV_IMU, bus, sizeof(bus)), 13);
    GL_CHECK_EQ(bus[0], 0xA2);
    GL_CHECK_NEAR((float)s.ax * imu_.accel_g_per_lsb, a[0], 0.7e-4);
    GL_CHECK_NEAR((float)s.ay * imu_.accel_g_per_lsb, a[1], 0.7e-4);
    GL_CHECK_NEAR((float)s.az * imu_.accel_g_per_lsb, a[2], 0.7e-4);
    GL_CHECK_NEAR((float)s.gx * imu_.gyro_rad_s_per_lsb, g[0], 7e-4);
    GL_CHECK_NEAR((float)s.gy * imu_.gyro_rad_s_per_lsb, g[1], 7e-4);
    GL_CHECK_NEAR((float)s.gz * imu_.gyro_rad_s_per_lsb, g[2], 7e-4);

    float t = 0.0f;
    gl_sim_imu_set_temperature(31.5f);
    GL_CHECK_EQ(gl_imu_read_temperature(&imu_, &t), GL_OK);
    GL_CHECK_NEAR(t, 31.5, 0.01);
    gl_sim_imu_set_temperature(-4.25f);
    GL_CHECK_EQ(gl_imu_read_temperature(&imu_, &t), GL_OK);
    GL_CHECK_NEAR(t, -4.25, 0.01);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* Review findings: the temperature read converted whatever two bytes the
 * bus returned (all-ones = 24.996 C, all-zeros = 25.000 C, both "valid");
 * the charge gate hangs on it.  It now proves the sensor is alive in the
 * same call.  gl_imu_read() likewise refuses a burst nobody drove, and
 * gl_imu_verify() finds a part that has lost its configuration. */
GL_TEST(test_liveness_checks)
{
    float t = -99.0f;
    gl_imu_raw_t s;
    bool ready = true;
    uint8_t bus[16];

    fresh_();
    GL_CHECK_EQ(gl_imu_init(&imu_, NULL), GL_OK);
    GL_CHECK_EQ(gl_imu_start_measure(&imu_), GL_OK);
    gl_sim_imu_set_temperature(31.5f);
    gl_hal_delay_ms(20);
    /* exact traffic of a good temperature read: WHO_AM_I, CTRL1, OUT_TEMP */
    gl_sim_trace_clear();
    GL_CHECK_EQ(gl_imu_read_temperature(&imu_, &t), GL_OK);
    GL_CHECK_EQ(tr_spi_bytes(0, gl_sim_trace_count(), GL_SIM_DEV_IMU, bus, sizeof(bus)), 2 + 2 + 3);
    GL_CHECK_EQ(bus[0], 0x8F); /* WHO_AM_I | read */
    GL_CHECK_EQ(bus[2], 0x90); /* CTRL1 | read */
    GL_CHECK_EQ(bus[4], 0xA0); /* OUT_TEMP_L | read */
    GL_CHECK_NEAR(t, 31.5, 0.01);
    GL_CHECK_EQ(gl_imu_verify(&imu_), GL_OK);

    /* a silent bus (MISO reads 0xFF): not 24.996 C */
    gl_sim_imu_set_present(false);
    t = -99.0f;
    GL_CHECK_EQ(gl_imu_read_temperature(&imu_, &t), GL_ERR_NOT_FOUND);
    GL_CHECK_NEAR(t, -99.0, 1e-9); /* not written */
    GL_CHECK_EQ(gl_imu_read(&imu_, &s), GL_ERR_NOT_FOUND);
    GL_CHECK_EQ(gl_imu_data_ready(&imu_, &ready), GL_OK);
    GL_CHECK(!ready); /* a status byte of 0xFF is not "data ready" */
    GL_CHECK_EQ(gl_imu_verify(&imu_), GL_ERR_NOT_FOUND);
    gl_sim_imu_set_present(true);
    gl_hal_delay_ms(10);
    GL_CHECK_EQ(gl_imu_read(&imu_, &s), GL_OK);

    /* a bus error is passed on, and nothing is written */
    gl_sim_spi_fail(GL_SPI_BUS_2, 1, GL_ERR_TIMEOUT);
    GL_CHECK_EQ(gl_imu_read_temperature(&imu_, &t), GL_ERR_TIMEOUT);
    GL_CHECK_NEAR(t, -99.0, 1e-9);

    /* the part was reset by a supply glitch: it answers, but its sensors
     * are off and its temperature output is frozen at 0 (= 25.000 C) */
    gl_sim_imu_power_glitch();
    GL_CHECK_EQ(gl_imu_read_temperature(&imu_, &t), GL_ERR_STATE);
    GL_CHECK_EQ(gl_imu_verify(&imu_), GL_ERR_STATE);
    GL_CHECK_NEAR(t, -99.0, 1e-9);
    GL_CHECK_EQ(gl_imu_start_measure(&imu_), GL_OK);
    GL_CHECK_EQ(gl_imu_verify(&imu_), GL_OK);
    /* raw 0x0000 and 0xFFFF are refused even from a live part: exactly what
     * a frozen or floating output reads as */
    gl_sim_imu_set_temperature(25.0f);
    GL_CHECK_EQ(gl_imu_read_temperature(&imu_, &t), GL_ERR_QUALITY);
    gl_sim_imu_set_temperature(25.0f - 1.0f / 256.0f);
    GL_CHECK_EQ(gl_imu_read_temperature(&imu_, &t), GL_ERR_QUALITY);
    gl_sim_imu_set_temperature(25.0f + 2.0f / 256.0f);
    GL_CHECK_EQ(gl_imu_read_temperature(&imu_, &t), GL_OK);
    GL_CHECK_NEAR(t, 25.008, 0.002);

    /* verify in the wake-on-motion mode: a lost MD1_CFG is found */
    GL_CHECK_EQ(gl_imu_start_wake_on_motion(&imu_, 62), GL_OK);
    GL_CHECK_EQ(gl_imu_verify(&imu_), GL_OK);
    GL_CHECK_EQ(gl_imu_reg_write(0x5E, 0x00), GL_OK);
    GL_CHECK_EQ(gl_imu_verify(&imu_), GL_ERR_STATE);
    GL_CHECK_EQ(gl_imu_stop(&imu_), GL_OK);
    GL_CHECK_EQ(gl_imu_verify(&imu_), GL_OK);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* Review finding: the model pulsed INT2 on every sample whether or not the
 * output was read; the part's reset behaviour (as remembered) is LATCHED.
 * The model now follows CTRL4: latched by default, pulsed with DRDY_PULSED. */
GL_TEST(test_data_ready_is_latched)
{
    gl_imu_raw_t s;
    unsigned edges = 0;
    fresh_();
    GL_CHECK_EQ(gl_imu_init(&imu_, NULL), GL_OK);
    GL_CHECK_EQ(gl_imu_start_measure(&imu_), GL_OK);
    gl_hal_irq_enable(GL_IRQ_IMU_INT2, true);
    gl_hal_delay_ms(10);
    /* the line is high and stays high; without a read there is ONE edge */
    GL_CHECK(gl_hal_gpio_read(GL_PIN_IMU_INT2));
    GL_CHECK_EQ(gl_hal_irq_take(), GL_IRQ_IMU_INT2);
    gl_hal_delay_ms(100); /* 24 more samples */
    GL_CHECK(gl_hal_gpio_read(GL_PIN_IMU_INT2));
    GL_CHECK_EQ(gl_hal_irq_take(), 0u); /* no new edge: this is how a lost latch stalls */
    /* reading the accelerometer output releases it; the next sample raises it */
    GL_CHECK_EQ(gl_imu_read(&imu_, &s), GL_OK);
    GL_CHECK(!gl_hal_gpio_read(GL_PIN_IMU_INT2));
    gl_hal_delay_ms(5);
    GL_CHECK(gl_hal_gpio_read(GL_PIN_IMU_INT2));
    GL_CHECK_EQ(gl_hal_irq_take(), GL_IRQ_IMU_INT2);
    /* pulsed mode (CTRL4 bit 1), for comparison: an edge per sample, line low */
    GL_CHECK_EQ(gl_imu_read(&imu_, &s), GL_OK);
    GL_CHECK_EQ(gl_imu_reg_write(0x13, 0x02), GL_OK);
    (void)gl_hal_irq_take();
    for (unsigned i = 0; i < 24u; i++) {
        gl_hal_delay_us(4167);
        if ((gl_hal_irq_take() & GL_IRQ_IMU_INT2) != 0u) {
            edges++;
        }
        GL_CHECK(!gl_hal_gpio_read(GL_PIN_IMU_INT2));
    }
    GL_CHECK(edges >= 23u);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

GL_TEST(test_axis_mapping)
{
    /* a board on which marker x = -sensor Y, marker y = +sensor X, marker
     * z = +sensor Z */
    const int8_t sim_axis[3] = { 1, 0, 2 };
    const int8_t sim_sign[3] = { -1, 1, 1 };
    const gl_imu_mount_t mount = { { 1, 0, 2 }, { -1, 1, 1 } };
    const gl_imu_mount_t bad = { { 0, 0, 2 }, { 1, 1, 1 } };
    const float a[3] = { 0.30f, -0.10f, 0.90f };
    const float g[3] = { 1.0f, 2.0f, -3.0f };
    gl_imu_raw_t s;
    fresh_();
    GL_CHECK_EQ(gl_imu_init(&imu_, &bad), GL_ERR_PARAM);
    gl_sim_imu_set_mounting(sim_axis, sim_sign);
    GL_CHECK_EQ(gl_imu_init(&imu_, &mount), GL_OK);
    GL_CHECK_EQ(gl_imu_start_measure(&imu_), GL_OK);
    gl_sim_imu_set_static(a, g);
    gl_hal_delay_ms(10);
    GL_CHECK_EQ(gl_imu_read(&imu_, &s), GL_OK);
    GL_CHECK_NEAR((float)s.ax * imu_.accel_g_per_lsb, a[0], 1e-4);
    GL_CHECK_NEAR((float)s.ay * imu_.accel_g_per_lsb, a[1], 1e-4);
    GL_CHECK_NEAR((float)s.az * imu_.accel_g_per_lsb, a[2], 1e-4);
    GL_CHECK_NEAR((float)s.gx * imu_.gyro_rad_s_per_lsb, g[0], 1e-3);
    GL_CHECK_NEAR((float)s.gy * imu_.gyro_rad_s_per_lsb, g[1], 1e-3);
    GL_CHECK_NEAR((float)s.gz * imu_.gyro_rad_s_per_lsb, g[2], 1e-3);
    /* with the identity map the same board would read wrongly */
    GL_CHECK_EQ(gl_imu_init(&imu_, NULL), GL_OK);
    GL_CHECK_EQ(gl_imu_start_measure(&imu_), GL_OK);
    gl_hal_delay_ms(10);
    GL_CHECK_EQ(gl_imu_read(&imu_, &s), GL_OK);
    GL_CHECK(fabsf((float)s.ax * imu_.accel_g_per_lsb - a[0]) > 0.1f);
}

GL_TEST(test_data_ready_interrupt_rate)
{
    gl_imu_raw_t s;
    bool ready = true;
    unsigned n = 0;
    fresh_();
    GL_CHECK_EQ(gl_imu_init(&imu_, NULL), GL_OK);
    GL_CHECK_EQ(gl_imu_start_measure(&imu_), GL_OK);
    gl_hal_irq_enable(GL_IRQ_IMU_INT2, true);
    const uint32_t t0 = gl_hal_tick_ms();
    while ((uint32_t)(gl_hal_tick_ms() - t0) < 1000u) {
        const uint32_t pend = gl_hal_sleep(GL_SLEEP_IDLE);
        (void)gl_hal_irq_take();
        if ((pend & GL_IRQ_IMU_INT2) != 0u) {
            if (gl_imu_read(&imu_, &s) == GL_OK) {
                n++;
            }
        }
    }
    printf("    data-ready interrupts in 1 s at the 240 Hz setting: %u\n", n);
    GL_CHECK(n >= 239u && n <= 241u);
    /* the status register follows the reads */
    GL_CHECK_EQ(gl_imu_data_ready(&imu_, &ready), GL_OK);
    GL_CHECK(!ready);
    gl_hal_delay_ms(5);
    GL_CHECK_EQ(gl_imu_data_ready(&imu_, &ready), GL_OK);
    GL_CHECK(ready);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

static uint64_t bump_at_us_;

static void bump_motion_(void *ctx, uint64_t t_us, float a[3], float g[3])
{
    (void)ctx;
    a[0] = 0.0f;
    a[1] = 0.0f;
    a[2] = 1.0f;
    g[0] = g[1] = g[2] = 0.0f;
    /* picked up at bump_at_us_: 0.3 g for 200 ms */
    if (t_us >= bump_at_us_ && t_us < bump_at_us_ + 200000u) {
        a[0] = 0.3f;
    }
}

GL_TEST(test_wake_on_motion)
{
    bool woke = true;
    fresh_();
    GL_CHECK_EQ(gl_imu_init(&imu_, NULL), GL_OK);
    bump_at_us_ = UINT64_MAX;
    gl_sim_imu_set_motion(bump_motion_, NULL);
    GL_CHECK_EQ(gl_imu_start_wake_on_motion(&imu_, 62), GL_OK);
    GL_CHECK_EQ(gl_sim_imu_reg(0x10), 0x43); /* CTRL1: low-power mode 1, 15 Hz */
    GL_CHECK_EQ(gl_sim_imu_reg(0x11), 0x00); /* gyro off */
    GL_CHECK_EQ(gl_sim_imu_reg(0x0E), 0x00); /* no data-ready pulses */
    GL_CHECK_EQ(gl_sim_imu_reg(0x5B), 8);    /* 62 mg / 7.8125 mg */
    GL_CHECK_EQ(gl_sim_imu_reg(0x50), 0x80); /* INTERRUPTS_ENABLE */
    GL_CHECK_EQ(gl_sim_imu_reg(0x5E), 0x20); /* wake-up on INT1 */

    /* at rest for 5 s in Stop mode: only the timer wakes the MCU */
    gl_hal_irq_enable(GL_IRQ_IMU_INT1 | GL_IRQ_WAKE_TIMER, true);
    gl_hal_wake_timer_start(5000);
    uint32_t pend = gl_hal_sleep(GL_SLEEP_STOP);
    (void)gl_hal_irq_take();
    GL_CHECK_EQ(pend, GL_IRQ_WAKE_TIMER);
    GL_CHECK_EQ(gl_imu_wake_source(&imu_, &woke), GL_OK);
    GL_CHECK(!woke);

    /* picked up 1.5 s later: INT1 wakes it within a sample period or two */
    bump_at_us_ = gl_sim_now_us() + 1500000u;
    gl_hal_wake_timer_start(10000);
    const uint64_t t0 = gl_sim_now_us();
    pend = gl_hal_sleep(GL_SLEEP_STOP);
    (void)gl_hal_irq_take();
    const double latency_ms = ((double)(gl_sim_now_us() - t0) - 1500000.0) / 1000.0;
    printf("    wake-on-motion latency after a 0.3 g step: %.0f ms (15 Hz sampling)\n", latency_ms);
    GL_CHECK((pend & GL_IRQ_IMU_INT1) != 0u);
    GL_CHECK(latency_ms >= 0.0 && latency_ms < 140.0);
    GL_CHECK_EQ(gl_imu_wake_source(&imu_, &woke), GL_OK);
    GL_CHECK(woke);
    GL_CHECK_EQ(gl_imu_wake_source(&imu_, &woke), GL_OK);
    GL_CHECK(!woke); /* cleared by reading */

    /* threshold clamps */
    GL_CHECK_EQ(gl_imu_start_wake_on_motion(&imu_, 0), GL_OK);
    GL_CHECK_EQ(gl_sim_imu_reg(0x5B), 1);
    GL_CHECK_EQ(gl_imu_start_wake_on_motion(&imu_, 5000), GL_OK);
    GL_CHECK_EQ(gl_sim_imu_reg(0x5B), 63);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

GL_TEST(test_absent_device)
{
    fresh_();
    gl_sim_imu_set_present(false);
    GL_CHECK_EQ(gl_imu_init(&imu_, NULL), GL_ERR_NOT_FOUND);
    GL_CHECK_EQ(imu_.who_am_i, 0xFF);
}

GL_TEST(test_tilt_pipeline_from_the_driver)
{
    /* the marker lies on a 2.0 % / -1.2 % slope; 1 mg rms sensor noise and a
     * small gyro bias; 1.07 s of samples through the core's block averager */
    const float sx = 0.020f, sy = -0.012f;
    const float norm = sqrtf(1.0f + sx * sx + sy * sy);
    const float a[3] = { sx / norm, sy / norm, 1.0f / norm };
    const float gb[3] = { 0.004f, -0.002f, 0.001f };
    gl_tilt_cfg_t cfg;
    gl_tilt_avg_t avg;
    gl_tilt_mean_t mean;
    gl_cal_tilt_t cal;
    gl_vec2_t slope;
    gl_imu_raw_t s;
    unsigned samples = 0;

    fresh_();
    GL_CHECK_EQ(gl_imu_init(&imu_, NULL), GL_OK);
    GL_CHECK_EQ(gl_imu_start_measure(&imu_), GL_OK);
    gl_sim_imu_set_static(a, NULL);
    gl_sim_imu_set_errors(0.001f, 0.002f, NULL, gb);
    gl_tilt_cfg_defaults(&cfg);
    cfg.accel_g_per_lsb = imu_.accel_g_per_lsb;
    cfg.gyro_rad_s_per_lsb = imu_.gyro_rad_s_per_lsb;
    gl_tilt_avg_init(&avg, &cfg);
    gl_cal_tilt_defaults(&cal);
    gl_hal_irq_enable(GL_IRQ_IMU_INT2, true);
    while (samples < 256u) {
        (void)gl_hal_sleep(GL_SLEEP_IDLE);
        if ((gl_hal_irq_take() & GL_IRQ_IMU_INT2) != 0u && gl_imu_read(&imu_, &s) == GL_OK) {
            (void)gl_tilt_avg_add(&avg, &s);
            samples++;
        }
    }
    GL_CHECK_EQ(gl_tilt_avg_result(&avg, &mean), GL_OK);
    GL_CHECK_EQ(mean.blocks_still, 8);
    GL_CHECK_EQ(mean.blocks_total, 8);
    GL_CHECK_EQ(gl_tilt_slope(gl_tilt_apply_cal(&cal, mean.accel_g, 25.0f), &slope), GL_OK);
    printf("    slope from 256 driver samples: (%.4f, %.4f), true (%.4f, %.4f); gyro bias seen"
           " (%.4f, %.4f, %.4f) rad/s\n",
           (double)slope.x, (double)slope.y, (double)sx, (double)sy, (double)mean.gyro_rad_s.x,
           (double)mean.gyro_rad_s.y, (double)mean.gyro_rad_s.z);
    GL_CHECK_NEAR(slope.x, sx, 0.0003);
    GL_CHECK_NEAR(slope.y, sy, 0.0003);
    GL_CHECK_NEAR(mean.gyro_rad_s.x, gb[0], 0.001);
    GL_CHECK_NEAR(mean.gyro_rad_s.y, gb[1], 0.001);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

GL_TEST(test_model_catches_wrong_spi_mode)
{
    const gl_spi_cfg_t mode0 = { 1000000u, 0u, false };
    const uint8_t rd[2] = { 0x8F, 0xFF };
    fresh_();
    (void)gl_hal_spi_configure(GL_SPI_BUS_2, &mode0);
    gl_hal_gpio_write(GL_PIN_IMU_CS, false);
    (void)gl_hal_spi_transfer(GL_SPI_BUS_2, rd, NULL, 2);
    gl_hal_gpio_write(GL_PIN_IMU_CS, true);
    GL_CHECK_EQ(gl_sim_violations()->imu, 1u);
}

int main(void)
{
    GL_RUN(test_init_exact_bytes);
    GL_RUN(test_measure_mode_registers_and_scaling);
    GL_RUN(test_liveness_checks);
    GL_RUN(test_data_ready_is_latched);
    GL_RUN(test_axis_mapping);
    GL_RUN(test_data_ready_interrupt_rate);
    GL_RUN(test_wake_on_motion);
    GL_RUN(test_absent_device);
    GL_RUN(test_tilt_pipeline_from_the_driver);
    GL_RUN(test_model_catches_wrong_spi_mode);
    return gl_test_summary();
}
