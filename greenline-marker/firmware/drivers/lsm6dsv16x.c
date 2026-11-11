/* lsm6dsv16x.c - LSM6DSV16X driver.  See lsm6dsv16x.h. */
#include "lsm6dsv16x.h"

#include <string.h>

#include "gl_hal.h"
#include "gl_provisional.h"

#define IMU_SPI_HZ 5000000u /* device limit 10 MHz (from memory) */

static gl_status_t select_(void)
{
    const gl_spi_cfg_t spi = { IMU_SPI_HZ, 3u, false };
    gl_status_t st = gl_hal_spi_configure(GL_SPI_BUS_2, &spi);
    if (st == GL_OK) {
        gl_hal_gpio_write(GL_PIN_IMU_CS, false);
    }
    return st;
}

static void deselect_(void)
{
    gl_hal_gpio_write(GL_PIN_IMU_CS, true);
}

gl_status_t gl_imu_reg_read(uint8_t reg, uint8_t *buf, size_t len)
{
    const uint8_t hdr = (uint8_t)(reg | GL_IMU_SPI_READ);
    gl_status_t st = select_();
    if (st != GL_OK) {
        return st;
    }
    st = gl_hal_spi_transfer(GL_SPI_BUS_2, &hdr, NULL, 1);
    if (st == GL_OK) {
        st = gl_hal_spi_transfer(GL_SPI_BUS_2, NULL, buf, len);
    }
    deselect_();
    return st;
}

gl_status_t gl_imu_reg_write(uint8_t reg, uint8_t val)
{
    const uint8_t tx[2] = { (uint8_t)(reg & 0x7Fu), val };
    gl_status_t st = select_();
    if (st != GL_OK) {
        return st;
    }
    st = gl_hal_spi_transfer(GL_SPI_BUS_2, tx, NULL, sizeof(tx));
    deselect_();
    return st;
}

/* Write a list of (register, value) pairs; stops at the first error. */
static gl_status_t write_list_(const uint8_t (*list)[2], size_t n)
{
    gl_status_t st = GL_OK;
    for (size_t i = 0; i < n && st == GL_OK; i++) {
        st = gl_imu_reg_write(list[i][0], list[i][1]);
    }
    return st;
}

void gl_imu_mount_defaults(gl_imu_mount_t *m)
{
    m->axis[0] = (uint8_t)GL_PROV_IMU_MARKER_X_AXIS;
    m->sign[0] = (int8_t)GL_PROV_IMU_MARKER_X_SIGN;
    m->axis[1] = (uint8_t)GL_PROV_IMU_MARKER_Y_AXIS;
    m->sign[1] = (int8_t)GL_PROV_IMU_MARKER_Y_SIGN;
    m->axis[2] = (uint8_t)GL_PROV_IMU_MARKER_Z_AXIS;
    m->sign[2] = (int8_t)GL_PROV_IMU_MARKER_Z_SIGN;
}

static bool mount_valid_(const gl_imu_mount_t *m)
{
    unsigned seen = 0;
    for (unsigned i = 0; i < 3u; i++) {
        if (m->axis[i] > 2u || (m->sign[i] != 1 && m->sign[i] != -1)) {
            return false;
        }
        seen |= 1u << m->axis[i];
    }
    return seen == 0x7u; /* a permutation: each sensor axis used once */
}

gl_status_t gl_imu_init(gl_imu_t *imu, const gl_imu_mount_t *mount)
{
    uint8_t id = 0;
    memset(imu, 0, sizeof(*imu));
    if (mount != NULL) {
        imu->mount = *mount;
    } else {
        gl_imu_mount_defaults(&imu->mount);
    }
    if (!mount_valid_(&imu->mount)) {
        return GL_ERR_PARAM;
    }
    gl_hal_gpio_write(GL_PIN_IMU_CS, true);
    gl_hal_gpio_mode(GL_PIN_IMU_CS, GL_PIN_MODE_OUTPUT_PP);
    gl_hal_gpio_mode(GL_PIN_IMU_INT1, GL_PIN_MODE_INPUT);
    gl_hal_gpio_mode(GL_PIN_IMU_INT2, GL_PIN_MODE_INPUT);

    gl_status_t st = gl_imu_reg_read(GL_IMU_REG_WHO_AM_I, &id, 1);
    if (st != GL_OK) {
        return st;
    }
    imu->who_am_i = id;
    if (id != GL_IMU_WHO_AM_I_VALUE) {
        return GL_ERR_NOT_FOUND;
    }
    st = gl_imu_reg_write(GL_IMU_REG_CTRL3, GL_IMU_CTRL3_SW_RESET);
    if (st != GL_OK) {
        return st;
    }
    gl_hal_delay_ms(1); /* reset time (from memory: tens of microseconds) */
    st = gl_imu_reg_write(GL_IMU_REG_CTRL3, GL_IMU_CTRL3_BDU | GL_IMU_CTRL3_IF_INC);
    if (st != GL_OK) {
        return st;
    }
    return gl_imu_stop(imu);
}

gl_status_t gl_imu_stop(gl_imu_t *imu)
{
    static const uint8_t list[][2] = {
        { GL_IMU_REG_INT2_CTRL, 0x00 },
        { GL_IMU_REG_MD1_CFG, 0x00 },
        { GL_IMU_REG_FUNCTIONS_ENABLE, 0x00 },
        { GL_IMU_REG_CTRL1, 0x00 },
        { GL_IMU_REG_CTRL2, 0x00 },
    };
    gl_status_t st = write_list_(list, GL_ARRAY_LEN(list));
    if (st == GL_OK) {
        imu->mode = (uint8_t)GL_IMU_MODE_OFF;
        imu->sample_hz = 0.0f;
    }
    return st;
}

gl_status_t gl_imu_start_measure(gl_imu_t *imu)
{
    static const uint8_t list[][2] = {
        { GL_IMU_REG_MD1_CFG, 0x00 },
        { GL_IMU_REG_FUNCTIONS_ENABLE, 0x00 },
        { GL_IMU_REG_CTRL3, GL_IMU_CTRL3_BDU | GL_IMU_CTRL3_IF_INC },
        { GL_IMU_REG_CTRL8, GL_IMU_FS_XL_2G },
        { GL_IMU_REG_CTRL6, GL_IMU_FS_G_1000DPS },
        { GL_IMU_REG_CTRL1, GL_IMU_XL_MODE_HIGH_PERF | GL_IMU_ODR_240HZ },
        { GL_IMU_REG_CTRL2, GL_IMU_ODR_240HZ },
        { GL_IMU_REG_INT2_CTRL, GL_IMU_INT2_DRDY_XL },
    };
    gl_status_t st = write_list_(list, GL_ARRAY_LEN(list));
    if (st == GL_OK) {
        imu->mode = (uint8_t)GL_IMU_MODE_MEASURE;
        imu->accel_g_per_lsb = GL_IMU_ACCEL_G_PER_LSB_2G;
        imu->gyro_rad_s_per_lsb = GL_IMU_GYRO_RAD_S_PER_LSB_1000;
        imu->sample_hz = GL_IMU_MEASURE_HZ;
    }
    return st;
}

gl_status_t gl_imu_start_wake_on_motion(gl_imu_t *imu, uint16_t threshold_mg)
{
    uint8_t list[][2] = {
        { GL_IMU_REG_INT2_CTRL, 0x00 },
        { GL_IMU_REG_CTRL2, 0x00 }, /* gyro off */
        { GL_IMU_REG_CTRL8, GL_IMU_FS_XL_2G },
        { GL_IMU_REG_CTRL1, GL_IMU_XL_MODE_LOW_POWER_1 | GL_IMU_ODR_15HZ },
        { GL_IMU_REG_TAP_CFG0, 0x00 }, /* slope filter, interrupt not latched */
        { GL_IMU_REG_WAKE_UP_DUR, 0x00 },
        { GL_IMU_REG_WAKE_UP_THS, 0x00 },
        { GL_IMU_REG_FUNCTIONS_ENABLE, GL_IMU_FUNC_INTERRUPTS_EN },
        { GL_IMU_REG_MD1_CFG, GL_IMU_MD1_INT1_WU },
    };
    unsigned code = (unsigned)(((float)threshold_mg / GL_IMU_WAKE_THS_MG_PER_LSB) + 0.5f);
    if (code < 1u) {
        code = 1u;
    }
    if (code > 63u) {
        code = 63u;
    }
    list[6][1] = (uint8_t)code;
    gl_status_t st = write_list_((const uint8_t (*)[2])list, GL_ARRAY_LEN(list));
    if (st == GL_OK) {
        bool dummy;
        imu->mode = (uint8_t)GL_IMU_MODE_WAKE;
        imu->sample_hz = 0.0f;
        st = gl_imu_wake_source(imu, &dummy); /* clear anything latched */
    }
    return st;
}

gl_status_t gl_imu_read(gl_imu_t *imu, gl_imu_raw_t *out)
{
    uint8_t b[12];
    int16_t g[3], a[3];
    gl_status_t st = gl_imu_reg_read(GL_IMU_REG_OUTX_L_G, b, sizeof(b));
    if (st != GL_OK) {
        return st;
    }
    for (unsigned i = 0; i < 3u; i++) {
        g[i] = (int16_t)gl_get_u16(&b[2u * i]);
        a[i] = (int16_t)gl_get_u16(&b[6u + 2u * i]);
    }
    int16_t gm[3], am[3];
    for (unsigned i = 0; i < 3u; i++) {
        const int16_t gs = g[imu->mount.axis[i]];
        const int16_t as = a[imu->mount.axis[i]];
        if (imu->mount.sign[i] > 0) {
            gm[i] = gs;
            am[i] = as;
        } else {
            /* -(-32768) does not fit: saturate */
            gm[i] = (gs == INT16_MIN) ? INT16_MAX : (int16_t)-gs;
            am[i] = (as == INT16_MIN) ? INT16_MAX : (int16_t)-as;
        }
    }
    out->ax = am[0];
    out->ay = am[1];
    out->az = am[2];
    out->gx = gm[0];
    out->gy = gm[1];
    out->gz = gm[2];
    return GL_OK;
}

gl_status_t gl_imu_data_ready(gl_imu_t *imu, bool *ready)
{
    uint8_t s = 0;
    (void)imu;
    gl_status_t st = gl_imu_reg_read(GL_IMU_REG_STATUS, &s, 1);
    *ready = (st == GL_OK) && (s & 0x01u) != 0u;
    return st;
}

gl_status_t gl_imu_read_temperature(gl_imu_t *imu, float *temp_c)
{
    uint8_t b[2] = { 0, 0 };
    (void)imu;
    gl_status_t st = gl_imu_reg_read(GL_IMU_REG_OUT_TEMP_L, b, sizeof(b));
    if (st == GL_OK) {
        *temp_c = 25.0f + (float)(int16_t)gl_get_u16(b) / GL_IMU_TEMP_LSB_PER_C;
    }
    return st;
}

gl_status_t gl_imu_wake_source(gl_imu_t *imu, bool *woke)
{
    uint8_t s = 0;
    (void)imu;
    gl_status_t st = gl_imu_reg_read(GL_IMU_REG_WAKE_UP_SRC, &s, 1);
    *woke = (st == GL_OK) && (s & GL_IMU_WAKE_SRC_WU_IA) != 0u;
    return st;
}
