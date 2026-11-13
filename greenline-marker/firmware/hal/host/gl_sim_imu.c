/*
 * gl_sim_imu.c - model of the ST LSM6DSV16X on SPI2 for the host simulator.
 *
 * Register addresses, bit positions, output data rates and sensitivities
 * are FROM MEMORY of the ST datasheet (DS13510) - the same recollection the
 * driver is written from; see the README table.  Modelled:
 *
 *   0Dh INT1_CTRL          0Eh INT2_CTRL (bit 0 DRDY_XL)   0Fh WHO_AM_I = 70h
 *   10h CTRL1 (accel ODR[3:0], mode[6:4])   11h CTRL2 (gyro ODR, mode)
 *   12h CTRL3 (bit 6 BDU, bit 2 IF_INC, bit 0 SW_RESET; reset value 44h)
 *   15h CTRL6 (gyro full scale [3:0])       17h CTRL8 (accel full scale [1:0])
 *   1Eh STATUS_REG (bit 0 XLDA, 1 GDA, 2 TDA)
 *   20h OUT_TEMP_L/H (256 LSB per K, 0 = 25 C)
 *   22h..27h gyro X, Y, Z   28h..2Dh accel X, Y, Z (little-endian int16)
 *   45h WAKE_UP_SRC (bit 3 WU_IA)
 *   50h FUNCTIONS_ENABLE (bit 7 INTERRUPTS_ENABLE)
 *   56h TAP_CFG0   5Bh WAKE_UP_THS ([5:0], 7.8125 mg per LSB)
 *   5Ch WAKE_UP_DUR   5Eh MD1_CFG (bit 5 INT1_WU)
 *
 * SPI: mode 3, MSB first, first byte = R/W (bit 7, 1 = read) + 7-bit
 * address, address auto-increment while IF_INC is set.
 *
 * Samples are generated at the accelerometer ODR from the test's motion
 * function plus offset and white noise; sample k is a pure function of k,
 * so re-reading gives the same value.  The wake-up function compares
 * consecutive samples (slope filter) with the threshold on every axis.
 */
#include <math.h>
#include <string.h>

#include "gl_sim_internal.h"

#define IMU_MAX_HZ 10000000u
#define REG_INT1_CTRL 0x0D
#define REG_INT2_CTRL 0x0E
#define REG_WHO_AM_I 0x0F
#define REG_CTRL1 0x10
#define REG_CTRL2 0x11
#define REG_CTRL3 0x12
#define REG_CTRL4 0x13 /* bit 1 DRDY_PULSED */
#define REG_CTRL6 0x15
#define REG_CTRL8 0x17
#define REG_STATUS 0x1E
#define REG_OUT_TEMP_L 0x20
#define REG_OUTX_L_G 0x22
#define REG_OUTZ_H_A 0x2D
#define REG_WAKE_UP_SRC 0x45
#define REG_FUNCTIONS_ENABLE 0x50
#define REG_WAKE_UP_THS 0x5B
#define REG_MD1_CFG 0x5E

static const float odr_hz_[16] = { 0.0f,   1.875f, 7.5f,   15.0f,  30.0f,  60.0f, 120.0f, 240.0f,
                                   480.0f, 960.0f, 1920.0f, 3840.0f, 7680.0f, 0.0f, 0.0f,  0.0f };

static struct {
    uint8_t reg[128];
    bool present;
    bool selected;
    bool have_addr;
    bool read;
    uint8_t addr;
    /* environment */
    gl_sim_imu_fn_t fn;
    void *fn_ctx;
    float stat_a[3], stat_g[3];
    float noise_a, noise_g;
    float off_a[3], bias_g[3];
    float temp_c;
    int8_t mount_axis[3], mount_sign[3]; /* marker[i] = sign[i] * sensor[axis[i]] */
    /* sampling */
    uint64_t t0;          /* time the accelerometer ODR was last changed */
    uint64_t period_us;   /* 0 = accelerometer off */
    uint64_t k_fired;     /* last sample instant processed for interrupts */
    uint64_t k_read;      /* last sample index returned to the host */
    uint64_t k_cache;
    bool cache_valid;
    int16_t cache_a[3], cache_g[3];
    float prev_a[3];      /* previous sample (marker axes, g) for the slope filter */
    bool have_prev;
    bool wu_latched;
    bool drdy_high;       /* latched data-ready level on INT2 */
} I;

void sim_imu_reset(void)
{
    memset(&I, 0, sizeof(I));
    I.present = true;
    I.reg[REG_WHO_AM_I] = 0x70;
    I.reg[REG_CTRL3] = 0x44;
    I.stat_a[2] = 1.0f;
    I.temp_c = 25.0f;
    for (int i = 0; i < 3; i++) {
        I.mount_axis[i] = (int8_t)i;
        I.mount_sign[i] = 1;
    }
}

void gl_sim_imu_set_motion(gl_sim_imu_fn_t fn, void *ctx)
{
    I.fn = fn;
    I.fn_ctx = ctx;
    I.cache_valid = false;
}

void gl_sim_imu_set_static(const float accel_g[3], const float gyro_rad_s[3])
{
    for (int i = 0; i < 3; i++) {
        I.stat_a[i] = accel_g[i];
        I.stat_g[i] = (gyro_rad_s != NULL) ? gyro_rad_s[i] : 0.0f;
    }
    I.cache_valid = false;
}

void gl_sim_imu_set_errors(float accel_noise_g, float gyro_noise_rad_s,
                           const float accel_offset_g[3], const float gyro_bias_rad_s[3])
{
    I.noise_a = accel_noise_g;
    I.noise_g = gyro_noise_rad_s;
    for (int i = 0; i < 3; i++) {
        I.off_a[i] = (accel_offset_g != NULL) ? accel_offset_g[i] : 0.0f;
        I.bias_g[i] = (gyro_bias_rad_s != NULL) ? gyro_bias_rad_s[i] : 0.0f;
    }
    I.cache_valid = false;
}

void gl_sim_imu_set_temperature(float temp_c)
{
    I.temp_c = temp_c;
}

void gl_sim_imu_set_present(bool present)
{
    I.present = present;
}

float sim_imu_temperature(void)
{
    return I.temp_c;
}

static void odr_changed_(void);

static void drdy_set_(bool high)
{
    if (I.drdy_high != high) {
        I.drdy_high = high;
        sim_set_input(GL_PIN_IMU_INT2, high);
    }
}

void gl_sim_imu_power_glitch(void)
{
    memset(I.reg, 0, sizeof(I.reg));
    I.reg[REG_WHO_AM_I] = 0x70;
    I.reg[REG_CTRL3] = 0x44;
    I.wu_latched = false;
    drdy_set_(false);
    odr_changed_();
}

void gl_sim_imu_set_mounting(const int8_t axis[3], const int8_t sign[3])
{
    for (int i = 0; i < 3; i++) {
        I.mount_axis[i] = axis[i];
        I.mount_sign[i] = sign[i];
    }
    I.cache_valid = false;
}

uint8_t gl_sim_imu_reg(uint8_t addr)
{
    return I.reg[addr & 0x7Fu];
}

/* ---- samples ---------------------------------------------------------------- */

static float accel_lsb_g_(void)
{
    /* datasheet sensitivities: 0.061, 0.122, 0.244, 0.488 mg per LSB */
    static const float mg[4] = { 0.061f, 0.122f, 0.244f, 0.488f };
    return mg[I.reg[REG_CTRL8] & 0x03u] * 0.001f;
}

static float gyro_lsb_rad_s_(void)
{
    static const float mdps[5] = { 4.375f, 8.75f, 17.5f, 35.0f, 70.0f };
    unsigned code = I.reg[REG_CTRL6] & 0x0Fu;
    if (code > 4u) {
        code = 4u;
    }
    return mdps[code] * 0.001f * 0.0174532925f;
}

static int16_t sat16_(float v)
{
    if (v > 32767.0f) {
        return 32767;
    }
    if (v < -32768.0f) {
        return -32768;
    }
    return (int16_t)lrintf(v);
}

/* Truth plus sensor errors for sample k, in MARKER axes. */
static void truth_(uint64_t k, float a[3], float g[3])
{
    const uint64_t t = I.t0 + k * I.period_us;
    if (I.fn != NULL) {
        I.fn(I.fn_ctx, t, a, g);
    } else {
        memcpy(a, I.stat_a, sizeof(I.stat_a));
        memcpy(g, I.stat_g, sizeof(I.stat_g));
    }
    for (unsigned i = 0; i < 3u; i++) {
        a[i] += I.off_a[i] + I.noise_a * sim_hash_normal(1u + i, t);
        g[i] += I.bias_g[i] + I.noise_g * sim_hash_normal(4u + i, t);
    }
}

static void sample_(uint64_t k)
{
    float a[3], g[3];
    if (I.cache_valid && I.k_cache == k) {
        return;
    }
    truth_(k, a, g);
    const bool gyro_on = (I.reg[REG_CTRL2] & 0x0Fu) != 0u;
    for (unsigned i = 0; i < 3u; i++) {
        /* marker[i] = sign[i] * sensor[axis[i]]  =>  sensor[axis[i]] = sign[i] * marker[i] */
        const unsigned s = (unsigned)I.mount_axis[i];
        I.cache_a[s] = sat16_((float)I.mount_sign[i] * a[i] / accel_lsb_g_());
        I.cache_g[s] = gyro_on ? sat16_((float)I.mount_sign[i] * g[i] / gyro_lsb_rad_s_()) : 0;
    }
    I.k_cache = k;
    I.cache_valid = true;
}

static uint64_t k_now_(void)
{
    if (I.period_us == 0u) {
        return 0;
    }
    return (sim_now() - I.t0) / I.period_us;
}

static void odr_changed_(void)
{
    /* note: declared above for gl_sim_imu_power_glitch() */
    const float hz = odr_hz_[I.reg[REG_CTRL1] & 0x0Fu];
    I.t0 = sim_now();
    I.period_us = (hz > 0.0f) ? (uint64_t)(1.0e6f / hz + 0.5f) : 0u;
    I.k_fired = 0;
    I.k_read = 0;
    I.cache_valid = false;
    I.have_prev = false;
}

double sim_imu_supply_ua(void)
{
    const bool gyro_on = (I.reg[REG_CTRL2] & 0x0Fu) != 0u;
    const bool accel_on = (I.reg[REG_CTRL1] & 0x0Fu) != 0u;
    const bool accel_lp = (I.reg[REG_CTRL1] & 0x70u) != 0u; /* any mode but high performance */
    if (!I.present) {
        return 0.0;
    }
    if (gyro_on) {
        return GL_SIM_I_IMU_COMBO_UA;
    }
    if (accel_on) {
        return accel_lp ? GL_SIM_I_IMU_WAKE_UA : GL_SIM_I_IMU_ACCEL_UA;
    }
    return GL_SIM_I_IMU_OFF_UA;
}

static bool wu_enabled_(void)
{
    return (I.reg[REG_FUNCTIONS_ENABLE] & 0x80u) != 0u && (I.reg[REG_MD1_CFG] & 0x20u) != 0u;
}

uint64_t sim_imu_next_event(void)
{
    if (!I.present || I.period_us == 0u) {
        return SIM_NEVER;
    }
    if ((I.reg[REG_INT2_CTRL] & 0x01u) == 0u && !wu_enabled_()) {
        return SIM_NEVER;
    }
    uint64_t k = k_now_();
    if (k < I.k_fired) {
        k = I.k_fired;
    }
    /* next instant strictly after the last one handled */
    return I.t0 + (I.k_fired + 1u > k ? I.k_fired + 1u : k) * I.period_us;
}

void sim_imu_fire(uint64_t t)
{
    const uint64_t k = (t - I.t0) / I.period_us;
    I.k_fired = k;
    if (wu_enabled_()) {
        float a[3], g[3];
        truth_(k, a, g);
        if (I.have_prev) {
            const float ths = (float)(I.reg[REG_WAKE_UP_THS] & 0x3Fu) * 0.0078125f;
            for (unsigned i = 0; i < 3u; i++) {
                if (fabsf(a[i] - I.prev_a[i]) > ths) {
                    I.wu_latched = true;
                    sim_set_input(GL_PIN_IMU_INT1, true);
                    sim_set_input(GL_PIN_IMU_INT1, false);
                    break;
                }
            }
        }
        memcpy(I.prev_a, a, sizeof(a));
        I.have_prev = true;
    }
    if ((I.reg[REG_INT2_CTRL] & 0x01u) != 0u) {
        if ((I.reg[REG_CTRL4] & 0x02u) != 0u) {
            /* DRDY_PULSED: one short pulse per sample, read or not */
            I.drdy_high = false;
            sim_set_input(GL_PIN_IMU_INT2, true);
            sim_set_input(GL_PIN_IMU_INT2, false);
        } else {
            /* latched (the reset behaviour): high until the accelerometer
             * output is read.  If the host does not read, the line simply
             * stays high: there is NO further edge. */
            drdy_set_(true);
        }
    }
}

/* ---- register access ---------------------------------------------------------- */

static uint8_t read_reg_(uint8_t addr)
{
    if (addr == REG_STATUS) {
        const uint64_t k = k_now_();
        uint8_t s = 0x04; /* temperature always available */
        if (k > I.k_read) {
            s |= 0x01u;
            if ((I.reg[REG_CTRL2] & 0x0Fu) != 0u) {
                s |= 0x02u;
            }
        }
        return s;
    }
    if (addr == REG_OUT_TEMP_L || addr == REG_OUT_TEMP_L + 1u) {
        const int16_t t = sat16_((I.temp_c - 25.0f) * 256.0f);
        return (addr == REG_OUT_TEMP_L) ? (uint8_t)((uint16_t)t & 0xFFu)
                                        : (uint8_t)((uint16_t)t >> 8);
    }
    if (addr >= REG_OUTX_L_G && addr <= REG_OUTZ_H_A) {
        const uint64_t k = k_now_();
        if (k == 0u) {
            return 0; /* no sample yet */
        }
        sample_(k);
        I.k_read = k;
        if (addr >= REG_OUTX_L_G + 6u) {
            drdy_set_(false); /* reading the accelerometer output releases INT2 */
        }
        const unsigned idx = (unsigned)(addr - REG_OUTX_L_G);
        const int16_t v = (idx < 6u) ? I.cache_g[idx / 2u] : I.cache_a[(idx - 6u) / 2u];
        return ((idx & 1u) == 0u) ? (uint8_t)((uint16_t)v & 0xFFu) : (uint8_t)((uint16_t)v >> 8);
    }
    if (addr == REG_WAKE_UP_SRC) {
        const uint8_t v = I.wu_latched ? 0x08u : 0x00u;
        I.wu_latched = false;
        return v;
    }
    return I.reg[addr];
}

static void write_reg_(uint8_t addr, uint8_t val)
{
    if (addr == REG_WHO_AM_I || addr == REG_STATUS || (addr >= REG_OUT_TEMP_L && addr <= REG_OUTZ_H_A)) {
        sim_violation(&sim_viol()->imu, "write to read-only IMU register 0x%02X", addr);
        return;
    }
    if (addr == REG_CTRL3 && (val & 0x01u) != 0u) {
        /* software reset: all registers to their defaults */
        memset(I.reg, 0, sizeof(I.reg));
        I.reg[REG_WHO_AM_I] = 0x70;
        I.reg[REG_CTRL3] = 0x44;
        drdy_set_(false);
        odr_changed_();
        return;
    }
    const uint8_t before = I.reg[addr];
    I.reg[addr] = val;
    if (addr == REG_CTRL1 && ((before ^ val) & 0x0Fu) != 0u) {
        odr_changed_();
    }
    if (addr == REG_CTRL8 || addr == REG_CTRL6 || addr == REG_CTRL2) {
        I.cache_valid = false;
    }
    if (addr == REG_MD1_CFG || addr == REG_FUNCTIONS_ENABLE || addr == REG_INT2_CTRL) {
        /* interrupts start with the next sample, not with a backlog */
        I.have_prev = false;
        I.k_fired = k_now_();
    }
    if ((addr == REG_INT2_CTRL && (val & 0x01u) == 0u) || (addr == REG_CTRL1 && (val & 0x0Fu) == 0u)) {
        drdy_set_(false); /* data-ready no longer routed / no data */
    }
}

void sim_imu_cs(bool asserted)
{
    I.selected = asserted;
    I.have_addr = false;
}

void sim_imu_xfer(const gl_spi_cfg_t *cfg, const uint8_t *tx, uint8_t *rx, size_t len)
{
    if (!I.present) {
        return; /* MISO floats: rx stays 0xFF */
    }
    if (cfg->mode != 3u || cfg->lsb_first) {
        sim_violation(&sim_viol()->imu, "IMU addressed with SPI mode %u, lsb_first %d (needs mode 3, MSB)",
                      cfg->mode, (int)cfg->lsb_first);
        return;
    }
    if (cfg->max_hz > IMU_MAX_HZ) {
        sim_violation(&sim_viol()->imu, "IMU clocked at %u Hz", (unsigned)cfg->max_hz);
    }
    for (size_t i = 0; i < len; i++) {
        if (!I.have_addr) {
            I.read = (tx[i] & 0x80u) != 0u;
            I.addr = tx[i] & 0x7Fu;
            I.have_addr = true;
            continue;
        }
        if (I.read) {
            if (rx != NULL) {
                rx[i] = read_reg_(I.addr);
            }
        } else {
            write_reg_(I.addr, tx[i]);
        }
        if ((I.reg[REG_CTRL3] & 0x04u) != 0u) {
            I.addr = (uint8_t)((I.addr + 1u) & 0x7Fu);
        }
    }
}
