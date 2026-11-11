/*
 * lsm6dsv16x.h - ST LSM6DSV16X 6-axis IMU on SPI2 (4-wire, mode 3).
 *
 * EVERY register address, bit position, output-data-rate code and
 * sensitivity in this driver is FROM MEMORY of the ST datasheet (DS13510)
 * and must be verified against it; they are listed once, in the README
 * table "from memory - verify against datasheet", and as named constants
 * below.  Only the registers needed for the product's functions are used:
 *
 *   identification          WHO_AM_I
 *   basic configuration     CTRL1 (accel ODR / mode), CTRL2 (gyro ODR /
 *                           mode), CTRL3 (BDU, IF_INC, SW_RESET), CTRL6
 *                           (gyro full scale), CTRL8 (accel full scale)
 *   data                    STATUS_REG, OUT_TEMP, OUTX_L_G .. OUTZ_H_A
 *   data-ready interrupt    INT2_CTRL (accelerometer data ready on INT2)
 *   wake-on-motion          FUNCTIONS_ENABLE, TAP_CFG0, WAKE_UP_THS,
 *                           WAKE_UP_DUR, MD1_CFG (wake-up event on INT1),
 *                           WAKE_UP_SRC
 *
 * Two operating modes:
 *   MEASURE  accelerometer +-2 g high-performance and gyro +-1000 dps, both
 *            at 240 Hz, data-ready pulses on INT2.  Used for tilt reads,
 *            stillness, gestures, the 180-degree flip angle.
 *   WAKE     gyro off, accelerometer low-power at 15 Hz, wake-up interrupt
 *            on INT1 when the slope between samples exceeds the threshold.
 *            Used while the MCU is in Stop mode.
 *
 * Samples are returned in MARKER axes (the mounting map is a provisional
 * constant, GL_PROV_IMU_MARKER_*), together with the scale factors that
 * core/gl_tilt needs.
 *
 * RAM: sizeof(gl_imu_t) = 28 bytes.  Stack: under 64 bytes.
 */
#ifndef GL_LSM6DSV16X_H
#define GL_LSM6DSV16X_H

#include "gl_tilt.h"
#include "gl_types.h"

/* ---- registers (from memory - verify against DS13510) ---------------------- */
#define GL_IMU_REG_INT1_CTRL        0x0Du
#define GL_IMU_REG_INT2_CTRL        0x0Eu /* bit 0: accelerometer data ready on INT2 */
#define GL_IMU_REG_WHO_AM_I         0x0Fu
#define GL_IMU_REG_CTRL1            0x10u /* [3:0] accel ODR, [6:4] accel operating mode */
#define GL_IMU_REG_CTRL2            0x11u /* [3:0] gyro ODR, [6:4] gyro operating mode */
#define GL_IMU_REG_CTRL3            0x12u /* bit 6 BDU, bit 2 IF_INC, bit 0 SW_RESET */
#define GL_IMU_REG_CTRL6            0x15u /* [3:0] gyro full scale */
#define GL_IMU_REG_CTRL8            0x17u /* [1:0] accel full scale */
#define GL_IMU_REG_STATUS           0x1Eu /* bit 0 XLDA, bit 1 GDA, bit 2 TDA */
#define GL_IMU_REG_OUT_TEMP_L       0x20u
#define GL_IMU_REG_OUTX_L_G         0x22u /* gyro X,Y,Z then accel X,Y,Z: 12 bytes */
#define GL_IMU_REG_OUTX_L_A         0x28u
#define GL_IMU_REG_WAKE_UP_SRC      0x45u /* bit 3 WU_IA */
#define GL_IMU_REG_FUNCTIONS_ENABLE 0x50u /* bit 7 INTERRUPTS_ENABLE */
#define GL_IMU_REG_TAP_CFG0         0x56u /* bit 4 SLOPE_FDS (0 = slope filter) */
#define GL_IMU_REG_WAKE_UP_THS      0x5Bu /* [5:0] threshold */
#define GL_IMU_REG_WAKE_UP_DUR      0x5Cu
#define GL_IMU_REG_MD1_CFG          0x5Eu /* bit 5: wake-up event routed to INT1 */

#define GL_IMU_WHO_AM_I_VALUE       0x70u
#define GL_IMU_CTRL3_BDU            0x40u
#define GL_IMU_CTRL3_IF_INC         0x04u
#define GL_IMU_CTRL3_SW_RESET       0x01u
#define GL_IMU_ODR_15HZ             0x03u
#define GL_IMU_ODR_240HZ            0x07u
#define GL_IMU_XL_MODE_HIGH_PERF    0x00u /* CTRL1 [6:4] = 000 */
#define GL_IMU_XL_MODE_LOW_POWER_1  0x40u /* CTRL1 [6:4] = 100 */
#define GL_IMU_FS_XL_2G             0x00u
#define GL_IMU_FS_G_1000DPS         0x03u
#define GL_IMU_INT2_DRDY_XL         0x01u
#define GL_IMU_FUNC_INTERRUPTS_EN   0x80u
#define GL_IMU_MD1_INT1_WU          0x20u
#define GL_IMU_WAKE_SRC_WU_IA       0x08u
#define GL_IMU_SPI_READ             0x80u

/** Sensitivities for the ranges this driver selects. */
#define GL_IMU_ACCEL_G_PER_LSB_2G       (0.061e-3f)                 /* 0.061 mg / LSB */
#define GL_IMU_GYRO_RAD_S_PER_LSB_1000  (35.0e-3f * GL_DEG2RAD_F)   /* 35 mdps / LSB */
#define GL_IMU_TEMP_LSB_PER_C           256.0f                      /* 0 LSB = 25 C */
/** Wake-up threshold resolution at the reset setting of the threshold
 *  weight, mg per LSB. */
#define GL_IMU_WAKE_THS_MG_PER_LSB      7.8125f
/** Sample rate in MEASURE mode. */
#define GL_IMU_MEASURE_HZ               240.0f

typedef struct {
    uint8_t axis[3]; /**< sensor axis (0 X, 1 Y, 2 Z) that feeds marker x, y, z */
    int8_t sign[3];  /**< +1 or -1 */
} gl_imu_mount_t;

typedef enum {
    GL_IMU_MODE_OFF = 0,
    GL_IMU_MODE_MEASURE,
    GL_IMU_MODE_WAKE
} gl_imu_mode_t;

typedef struct {
    gl_imu_mount_t mount;
    uint8_t mode;               /**< gl_imu_mode_t */
    uint8_t who_am_i;           /**< value read at init */
    float accel_g_per_lsb;      /**< for gl_tilt_cfg_t */
    float gyro_rad_s_per_lsb;
    float sample_hz;            /**< 0 when not measuring */
} gl_imu_t;

/** Mounting from core/gl_provisional.h. */
void gl_imu_mount_defaults(gl_imu_mount_t *m);

/** Probe (WHO_AM_I), software reset, set BDU + IF_INC, both sensors off.
 *  `mount` NULL = defaults.  GL_ERR_NOT_FOUND if the id is wrong (who_am_i
 *  holds what was read), GL_ERR_PARAM for an invalid mounting map. */
gl_status_t gl_imu_init(gl_imu_t *imu, const gl_imu_mount_t *mount);

/** Enter MEASURE mode (see the file comment). */
gl_status_t gl_imu_start_measure(gl_imu_t *imu);

/** Enter WAKE mode; the threshold is rounded to the register resolution
 *  and clamped to its range. */
gl_status_t gl_imu_start_wake_on_motion(gl_imu_t *imu, uint16_t threshold_mg);

/** Both sensors to power-down, interrupts off. */
gl_status_t gl_imu_stop(gl_imu_t *imu);

/** Read the newest gyro + accelerometer sample (one 12-byte burst), mapped
 *  into marker axes. */
gl_status_t gl_imu_read(gl_imu_t *imu, gl_imu_raw_t *out);

/** True if a new accelerometer sample is waiting (STATUS_REG). */
gl_status_t gl_imu_data_ready(gl_imu_t *imu, bool *ready);

/** Die temperature in degrees C. */
gl_status_t gl_imu_read_temperature(gl_imu_t *imu, float *temp_c);

/** Read and clear the wake-up source: *woke = true if a wake-up event was
 *  latched. */
gl_status_t gl_imu_wake_source(gl_imu_t *imu, bool *woke);

/** Raw register access (factory diagnostics, tests). */
gl_status_t gl_imu_reg_read(uint8_t reg, uint8_t *buf, size_t len);
gl_status_t gl_imu_reg_write(uint8_t reg, uint8_t val);

#endif /* GL_LSM6DSV16X_H */
