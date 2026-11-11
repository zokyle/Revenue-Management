/* ov7692.c - OVM7692 camera pair on the shared bus.  See ov7692.h. */
#include "ov7692.h"

#include <string.h>

#include "gl_provisional.h"

/*
 * Register addresses and bit masks.  Source: the public Analog Devices
 * msdk driver, Libraries/MiscDrivers/Camera/ov7692_regs.h and ov7692.c
 * (Apache-2.0), read at
 * raw.githubusercontent.com/analogdevicesinc/msdk/main/Libraries/MiscDrivers/Camera/.
 * The comment after each line says what that source shows.
 */
#define REG_PIDH       0x0Au /* product id, high byte */
#define REG_PIDL       0x0Bu
#define REG_0C         0x0Cu /* bit 7 vertical flip, bit 6 horizontal mirror, bit 4 YU/YV swap;
                                reset value 0x16.  Bits 2, 1: output drive (OV7690 datasheet) */
#define REG_0E         0x0Eu /* bit 3: sleep mode */
#define REG_12         0x12u /* bit 7: software reset; low bits: output format */
#define REG_HSTART     0x17u
#define REG_HSIZE      0x18u
#define REG_VSTART     0x19u
#define REG_VSIZE      0x1Au
#define REG_IN_W_HI    0xC8u /* horizontal input size, high 2 bits */
#define REG_IN_W_LO    0xC9u
#define REG_IN_H_HI    0xCAu /* vertical input size, 9th bit */
#define REG_IN_H_LO    0xCBu
#define REG_OUT_W_HI   0xCCu /* horizontal output size, high 2 bits */
#define REG_OUT_W_LO   0xCDu
#define REG_OUT_H_HI   0xCEu /* vertical output size, 9th bit */
#define REG_OUT_H_LO   0xCFu
#define REG_BANK       0xFFu /* 0x01 selects the MIPI bank, 0x00 the system bank */
#define REG_B1_MIPI_PD 0xB5u /* bank 1: 0x30 powers down MIPI and the low-power transmitter */

#define R0C_VFLIP      0x80u
#define R0C_HMIRROR    0x40u
#define R0C_DRIVE_BITS 0x06u /* bit 2 data pins, bit 1 VSYNC / HREF / PCLK */
#define R0E_SLEEP      0x08u
#define R12_RESET      0x80u
#define R12_YUV422     0x00u
#define MIPI_PD_VALUE  0x30u

/* The pins of the rail rule, by what they become while the rail is on. */
static const gl_pin_t dcmi_pins_[] = {
    GL_PIN_CAM_D0, GL_PIN_CAM_D1, GL_PIN_CAM_D2, GL_PIN_CAM_D3, GL_PIN_CAM_D4, GL_PIN_CAM_D5,
    GL_PIN_CAM_D6, GL_PIN_CAM_D7, GL_PIN_CAM_PIXCLK, GL_PIN_CAM_HREF, GL_PIN_CAM_VSYNC
};
static const gl_pin_t sccb_pins_[] = { GL_PIN_CAM_SCCB_SDA, GL_PIN_CAM_L_SCL, GL_PIN_CAM_R_SCL };

static gl_pin_t pwdn_pin_(gl_cam_id_t cam)
{
    return (cam == GL_CAM_LEFT) ? GL_PIN_CAM_L_PWDN : GL_PIN_CAM_R_PWDN;
}

/* Level on the PWDN pin that powers the sensor down / lets it run. */
static void pwdn_assert_(gl_cam_id_t cam, bool power_down)
{
    const bool high = (GL_PROV_OV7692_PWDN_ACTIVE_HIGH != 0) ? power_down : !power_down;
    gl_hal_gpio_write(pwdn_pin_(cam), high);
}

static gl_status_t wr_(gl_cam_id_t cam, uint8_t reg, uint8_t val)
{
    return gl_hal_sccb_write(cam, GL_OV7692_SCCB_ADDR, reg, val);
}

static gl_status_t rd_(gl_cam_id_t cam, uint8_t reg, uint8_t *val)
{
    return gl_hal_sccb_read(cam, GL_OV7692_SCCB_ADDR, reg, val);
}

/* Value of register 0x0C for a camera that does / does not drive the bus. */
static uint8_t reg0c_(const gl_ov7692_t *d, bool drive)
{
    /* bits this driver does not own keep their reset values */
    uint8_t v = (uint8_t)(GL_PROV_OV7692_REG0C_KEEP_BITS &
                          (uint8_t)~(R0C_VFLIP | R0C_HMIRROR | R0C_DRIVE_BITS));
    if (d->cfg.vflip) {
        v |= R0C_VFLIP;
    }
    if (d->cfg.hmirror) {
        v |= R0C_HMIRROR;
    }
    if (drive == (GL_PROV_OV7692_REG0C_BIT_SET_MEANS_DRIVEN != 0)) {
        v |= R0C_DRIVE_BITS;
    }
    return v;
}

void gl_ov7692_cfg_defaults(gl_ov7692_cfg_t *cfg)
{
    cfg->sensor_windowing = (GL_PROV_OV7692_SENSOR_WINDOWING != 0);
    cfg->sleep_idle_on_switch = (GL_PROV_CAM_SLEEP_IDLE_ON_EVERY_SWITCH != 0);
    cfg->vflip = (GL_PROV_CAM_SENSOR_VFLIP != 0);
    cfg->hmirror = (GL_PROV_CAM_SENSOR_HMIRROR != 0);
    cfg->enforce_pid = (GL_PROV_OV7692_ENFORCE_PID != 0);
    cfg->xvclk_hz = GL_PROV_CAM_XVCLK_HZ;
    cfg->frame_period_ms = (uint16_t)GL_PROV_CAM_FRAME_PERIOD_MS;
    cfg->settle_frames = (uint8_t)GL_PROV_CAM_SETTLE_FRAMES;
}

/* ---- power ------------------------------------------------------------------- */

void gl_ov7692_power_down(gl_ov7692_t *d)
{
    gl_hal_dcmi_stop();
    gl_hal_xvclk_stop();
    /* park every camera-facing pin BEFORE the rail goes away */
    for (size_t i = 0; i < GL_ARRAY_LEN(dcmi_pins_); i++) {
        gl_hal_gpio_mode(dcmi_pins_[i], GL_PIN_MODE_ANALOG);
    }
    gl_hal_gpio_write(GL_PIN_CAM_XVCLK, false);
    gl_hal_gpio_mode(GL_PIN_CAM_XVCLK, GL_PIN_MODE_OUTPUT_PP);
    for (size_t i = 0; i < GL_ARRAY_LEN(sccb_pins_); i++) {
        /* the SCCB pull-ups go to the camera rail: hold the lines low */
        gl_hal_gpio_write(sccb_pins_[i], false);
        gl_hal_gpio_mode(sccb_pins_[i], GL_PIN_MODE_OUTPUT_PP);
    }
    gl_hal_gpio_write(GL_PIN_CAM_L_PWDN, false);
    gl_hal_gpio_mode(GL_PIN_CAM_L_PWDN, GL_PIN_MODE_OUTPUT_PP);
    gl_hal_gpio_write(GL_PIN_CAM_R_PWDN, false);
    gl_hal_gpio_mode(GL_PIN_CAM_R_PWDN, GL_PIN_MODE_OUTPUT_PP);
    /* now the rail */
    gl_hal_gpio_write(GL_PIN_CAM_PWR_EN, false);
    gl_hal_gpio_mode(GL_PIN_CAM_PWR_EN, GL_PIN_MODE_OUTPUT_PP);

    d->powered = false;
    d->capturing = false;
    d->active = -1;
    memset(d->cam, 0, sizeof(d->cam));
}

void gl_ov7692_init(gl_ov7692_t *d, const gl_ov7692_cfg_t *cfg)
{
    memset(d, 0, sizeof(*d));
    if (cfg != NULL) {
        d->cfg = *cfg;
    } else {
        gl_ov7692_cfg_defaults(&d->cfg);
    }
    gl_ov7692_power_down(d);
}

/* Bring one camera from power-down to "configured, asleep, bus released". */
static gl_status_t cam_bring_up_(gl_ov7692_t *d, gl_cam_id_t cam)
{
    uint8_t v = 0, hi = 0, lo = 0;
    gl_status_t st;

    pwdn_assert_(cam, false);
    gl_hal_delay_ms(GL_PROV_CAM_CLOCK_SETTLE_MS);

    /* The sensor has left its power-on reset with its pads ENABLED (0x0C =
     * 0x16) and is streaming now.  The very first register write takes it
     * off the shared bus; until this moment the other sensor's pads are
     * kept off by PWDN alone, if PWDN does that at all (see ov7692.h). */
    st = wr_(cam, REG_0C, reg0c_(d, false));
    if (st != GL_OK) {
        return st;
    }
    st = wr_(cam, REG_12, R12_RESET);
    if (st != GL_OK) {
        return st;
    }
    /* the reset bit clears itself when the reset is done */
    const uint32_t t0 = gl_hal_tick_ms();
    for (;;) {
        gl_hal_delay_ms(1);
        st = rd_(cam, REG_12, &v);
        if (st != GL_OK) {
            return st;
        }
        if ((v & R12_RESET) == 0u) {
            break;
        }
        if ((uint32_t)(gl_hal_tick_ms() - t0) > GL_PROV_OV7692_RESET_TIMEOUT_MS) {
            return GL_ERR_TIMEOUT;
        }
    }
    /* the reset has enabled the outputs again (0x0C = 0x16): release the
     * shared bus before anything else */
    st = wr_(cam, REG_0C, reg0c_(d, false));
    if (st != GL_OK) {
        return st;
    }
    st = rd_(cam, REG_PIDH, &hi);
    if (st == GL_OK) {
        st = rd_(cam, REG_PIDL, &lo);
    }
    if (st != GL_OK) {
        return st;
    }
    d->cam[cam].pid = (uint16_t)(((uint16_t)hi << 8) | lo);
    if (d->cfg.enforce_pid && d->cam[cam].pid != GL_PROV_OV7692_PID) {
        return GL_ERR_NOT_FOUND;
    }
    /* the MIPI transmitter is not used on this board */
    st = wr_(cam, REG_BANK, 0x01);
    if (st == GL_OK) {
        st = wr_(cam, REG_B1_MIPI_PD, MIPI_PD_VALUE);
    }
    if (st == GL_OK) {
        st = wr_(cam, REG_BANK, 0x00);
    }
    if (st == GL_OK) {
        st = wr_(cam, REG_12, R12_YUV422);
    }
    if (st == GL_OK && !d->cfg.sensor_windowing) {
        /* MCU-side windowing crops a full VGA frame: program the full input
         * and output size explicitly instead of trusting the reset values
         * (the comments of the public driver give 0x180 = 384 lines as the
         * reset value of the vertical output size) */
        static const uint8_t vga[][2] = {
            { REG_IN_W_HI, (uint8_t)(GL_OV7692_SENSOR_W >> 8) },
            { REG_IN_W_LO, (uint8_t)(GL_OV7692_SENSOR_W & 0xFFu) },
            { REG_IN_H_HI, (uint8_t)(GL_OV7692_SENSOR_H >> 8) },
            { REG_IN_H_LO, (uint8_t)(GL_OV7692_SENSOR_H & 0xFFu) },
            { REG_OUT_W_HI, (uint8_t)(GL_OV7692_SENSOR_W >> 8) },
            { REG_OUT_W_LO, (uint8_t)(GL_OV7692_SENSOR_W & 0xFFu) },
            { REG_OUT_H_HI, (uint8_t)(GL_OV7692_SENSOR_H >> 8) },
            { REG_OUT_H_LO, (uint8_t)(GL_OV7692_SENSOR_H & 0xFFu) },
        };
        for (size_t i = 0; i < GL_ARRAY_LEN(vga) && st == GL_OK; i++) {
            st = wr_(cam, vga[i][0], vga[i][1]);
        }
    }
    if (st == GL_OK) {
        st = wr_(cam, REG_0E, R0E_SLEEP);
    }
    if (st == GL_OK) {
        d->cam[cam].awake = false;
        d->cam[cam].driving = false;
        d->cam[cam].w = 0;
    }
    return st;
}

gl_status_t gl_ov7692_power_up(gl_ov7692_t *d)
{
    gl_status_t st;

    if (d->powered) {
        return GL_OK;
    }
    /* 1: the rail.  Every camera-facing pin is still parked. */
    gl_hal_gpio_write(GL_PIN_CAM_PWR_EN, true);
    gl_hal_gpio_mode(GL_PIN_CAM_PWR_EN, GL_PIN_MODE_OUTPUT_PP);
    gl_hal_delay_ms(GL_PROV_CAM_RAIL_SETTLE_MS);

    /* 2: hold both sensors in power-down */
    pwdn_assert_(GL_CAM_LEFT, true);
    pwdn_assert_(GL_CAM_RIGHT, true);
    gl_hal_gpio_mode(GL_PIN_CAM_L_PWDN, GL_PIN_MODE_OUTPUT_PP);
    gl_hal_gpio_mode(GL_PIN_CAM_R_PWDN, GL_PIN_MODE_OUTPUT_PP);

    /* 3: the clock */
    gl_hal_gpio_mode(GL_PIN_CAM_XVCLK, GL_PIN_MODE_ALTERNATE);
    st = gl_hal_xvclk_start(d->cfg.xvclk_hz);
    if (st != GL_OK) {
        gl_ov7692_power_down(d);
        return st;
    }
    /* 4: the buses */
    for (size_t i = 0; i < GL_ARRAY_LEN(sccb_pins_); i++) {
        gl_hal_gpio_mode(sccb_pins_[i], GL_PIN_MODE_ALTERNATE);
    }
    for (size_t i = 0; i < GL_ARRAY_LEN(dcmi_pins_); i++) {
        gl_hal_gpio_mode(dcmi_pins_[i], GL_PIN_MODE_ALTERNATE);
    }
    gl_hal_delay_ms(GL_PROV_CAM_CLOCK_SETTLE_MS);

    /* 5: one camera at a time, so that the one being reset is the only one
     * that can be driving the shared bus */
    st = cam_bring_up_(d, GL_CAM_LEFT);
    if (st == GL_OK) {
        st = cam_bring_up_(d, GL_CAM_RIGHT);
    }
    if (st != GL_OK) {
        gl_ov7692_power_down(d);
        return st;
    }
    d->powered = true;
    d->active = -1;
    d->frames = 0;
    return GL_OK;
}

/* ---- bus ownership ------------------------------------------------------------ */

static gl_status_t set_drive_(gl_ov7692_t *d, gl_cam_id_t cam, bool drive)
{
    if (d->cam[cam].driving == drive) {
        return GL_OK;
    }
    gl_status_t st = wr_(cam, REG_0C, reg0c_(d, drive));
    if (st == GL_OK) {
        d->cam[cam].driving = drive;
    }
    return st;
}

static gl_status_t set_awake_(gl_ov7692_t *d, gl_cam_id_t cam, bool awake)
{
    if (d->cam[cam].awake == awake) {
        return GL_OK;
    }
    gl_status_t st = wr_(cam, REG_0E, awake ? 0x00u : R0E_SLEEP);
    if (st == GL_OK) {
        d->cam[cam].awake = awake;
        if (awake) {
            d->cam[cam].ready_at_ms =
                gl_hal_tick_ms() + (uint32_t)d->cfg.settle_frames * d->cfg.frame_period_ms;
        }
    }
    return st;
}

gl_status_t gl_ov7692_release_all(gl_ov7692_t *d)
{
    if (!d->powered) {
        return GL_ERR_STATE;
    }
    gl_status_t st = set_drive_(d, GL_CAM_LEFT, false);
    if (st == GL_OK) {
        st = set_drive_(d, GL_CAM_RIGHT, false);
    }
    d->active = -1;
    return st;
}

gl_status_t gl_ov7692_select(gl_ov7692_t *d, gl_cam_id_t cam, gl_ov7692_other_t other_mode)
{
    if (!d->powered || d->capturing) {
        return GL_ERR_STATE;
    }
    if ((unsigned)cam >= (unsigned)GL_CAM_COUNT) {
        return GL_ERR_PARAM;
    }
    const gl_cam_id_t other = (cam == GL_CAM_LEFT) ? GL_CAM_RIGHT : GL_CAM_LEFT;
    const bool other_awake = (other_mode == GL_OV_OTHER_AWAKE) && !d->cfg.sleep_idle_on_switch;

    /* break ... */
    gl_status_t st = set_drive_(d, other, false);
    d->active = -1;
    if (st == GL_OK) {
        st = set_awake_(d, other, other_awake);
    }
    /* ... before make */
    if (st == GL_OK) {
        st = set_awake_(d, cam, true);
    }
    if (st == GL_OK) {
        st = set_drive_(d, cam, true);
    }
    if (st == GL_OK) {
        d->active = (int8_t)cam;
    }
    return st;
}

/* ---- window -------------------------------------------------------------------- */

gl_status_t gl_ov7692_set_window(gl_ov7692_t *d, gl_cam_id_t cam, uint16_t x0, uint16_t y0,
                                 uint16_t w, uint16_t h)
{
    const unsigned hu = GL_PROV_OV7692_H_UNIT_PX;
    const unsigned vu = GL_PROV_OV7692_V_UNIT_LINES;

    if (!d->powered || d->capturing) {
        return GL_ERR_STATE;
    }
    if ((unsigned)cam >= (unsigned)GL_CAM_COUNT || w == 0u || h == 0u || w > GL_OV7692_SENSOR_W ||
        h > GL_OV7692_SENSOR_H || (w % hu) != 0u || (h % vu) != 0u) {
        return GL_ERR_PARAM;
    }
    /* shift inward, then round the origin down to the window granularity */
    unsigned x = x0, y = y0;
    if (x + w > GL_OV7692_SENSOR_W) {
        x = GL_OV7692_SENSOR_W - w;
    }
    if (y + h > GL_OV7692_SENSOR_H) {
        y = GL_OV7692_SENSOR_H - h;
    }
    x -= x % hu;
    y -= y % vu;

    gl_ov7692_cam_t *c = &d->cam[cam];
    if (c->w == w && c->h == h && c->x0 == x && c->y0 == y) {
        return GL_OK;
    }
    if (d->cfg.sensor_windowing) {
        const uint8_t list[][2] = {
            { REG_HSTART, (uint8_t)(GL_PROV_OV7692_HSTART_FULL + x / hu) },
            { REG_HSIZE, (uint8_t)((w + GL_PROV_OV7692_H_BORDER_PX) / hu) },
            { REG_VSTART, (uint8_t)(GL_PROV_OV7692_VSTART_FULL + y / vu) },
            { REG_VSIZE, (uint8_t)((h + GL_PROV_OV7692_V_BORDER_LINES) / vu) },
            { REG_IN_W_HI, (uint8_t)(w >> 8) },
            { REG_IN_W_LO, (uint8_t)(w & 0xFFu) },
            { REG_IN_H_HI, (uint8_t)(h >> 8) },
            { REG_IN_H_LO, (uint8_t)(h & 0xFFu) },
            { REG_OUT_W_HI, (uint8_t)(w >> 8) },
            { REG_OUT_W_LO, (uint8_t)(w & 0xFFu) },
            { REG_OUT_H_HI, (uint8_t)(h >> 8) },
            { REG_OUT_H_LO, (uint8_t)(h & 0xFFu) },
        };
        for (size_t i = 0; i < GL_ARRAY_LEN(list); i++) {
            gl_status_t st = wr_(cam, list[i][0], list[i][1]);
            if (st != GL_OK) {
                c->w = 0; /* the sensor's window is now unknown */
                return st;
            }
        }
        /* the frame in progress still has the old geometry */
        if (c->awake) {
            const uint32_t t = gl_hal_tick_ms() + d->cfg.frame_period_ms;
            if ((int32_t)(t - c->ready_at_ms) > 0) {
                c->ready_at_ms = t;
            }
        }
    }
    c->x0 = (uint16_t)x;
    c->y0 = (uint16_t)y;
    c->w = w;
    c->h = h;
    return GL_OK;
}

/* ---- capture -------------------------------------------------------------------- */

gl_status_t gl_ov7692_capture_start(gl_ov7692_t *d, gl_cam_id_t cam, uint8_t *buf, size_t buf_len,
                                    gl_strip_t *strip)
{
    gl_dcmi_cfg_t dc;

    if (!d->powered || d->capturing || (unsigned)cam >= (unsigned)GL_CAM_COUNT ||
        d->active != (int8_t)cam || d->cam[cam].w == 0u) {
        return GL_ERR_STATE;
    }
    const gl_ov7692_cam_t *c = &d->cam[cam];
    if (buf == NULL || buf_len < (size_t)c->w * c->h) {
        return GL_ERR_PARAM;
    }
    /* let the exposure loop / the new window settle */
    const int32_t wait_ms = (int32_t)(c->ready_at_ms - gl_hal_tick_ms());
    if (wait_ms > 0) {
        gl_hal_delay_ms((uint32_t)wait_ms);
    }

    memset(&dc, 0, sizeof(dc));
    if (d->cfg.sensor_windowing) {
        /* the sensor already delivers only the window */
        dc.x0_bytes = 0;
        dc.y0_lines = 0;
    } else {
        dc.x0_bytes = (uint16_t)(2u * c->x0);
        dc.y0_lines = c->y0;
    }
    dc.width_bytes = (uint16_t)(2u * c->w); /* YUV422: two bytes per pixel */
    dc.height_lines = c->h;
    dc.byte_select_every = 2;
    dc.byte_select_odd = (GL_PROV_OV7692_Y_IS_FIRST_BYTE == 0);
    dc.vsync_active_high = (GL_PROV_OV7692_VSYNC_ACTIVE_HIGH != 0);
    dc.href_active_high = (GL_PROV_OV7692_HREF_ACTIVE_HIGH != 0);
    dc.pclk_rising_edge = (GL_PROV_OV7692_PCLK_RISING != 0);
    dc.timeout_ms = 3u * (uint32_t)d->cfg.frame_period_ms + 100u;

    gl_status_t st = gl_hal_dcmi_start(&dc, buf, buf_len);
    if (st != GL_OK) {
        return st;
    }
    d->capturing = true;
    d->cap_w = c->w;
    d->cap_h = c->h;
    d->cap_deadline_ms = gl_hal_tick_ms() + dc.timeout_ms + 50u;
    if (strip != NULL) {
        strip->px = buf;
        strip->width = c->w;
        strip->height = c->h;
        strip->stride = c->w;
        strip->x0 = c->x0;
        strip->y0 = c->y0;
    }
    return GL_OK;
}

gl_status_t gl_ov7692_capture_poll(gl_ov7692_t *d)
{
    size_t bytes = 0;
    if (!d->capturing) {
        return GL_ERR_STATE;
    }
    switch (gl_hal_dcmi_poll(&bytes)) {
    case GL_DCMI_BUSY:
        if ((int32_t)(gl_hal_tick_ms() - d->cap_deadline_ms) < 0) {
            return GL_ERR_BUSY;
        }
        gl_ov7692_capture_abort(d);
        return GL_ERR_TIMEOUT;
    case GL_DCMI_DONE:
        d->capturing = false;
        gl_hal_dcmi_stop();
        if (bytes != (size_t)d->cap_w * d->cap_h) {
            return GL_ERR_IO;
        }
        d->last_done_ms = gl_hal_tick_ms();
        d->last_done_us = gl_hal_dcmi_done_us();
        d->frames++;
        return GL_OK;
    case GL_DCMI_ERROR_TIMEOUT:
        gl_ov7692_capture_abort(d);
        return GL_ERR_TIMEOUT;
    default:
        gl_ov7692_capture_abort(d);
        return GL_ERR_IO;
    }
}

void gl_ov7692_capture_abort(gl_ov7692_t *d)
{
    gl_hal_dcmi_stop();
    d->capturing = false;
}

gl_status_t gl_ov7692_capture_blocking(gl_ov7692_t *d, gl_cam_id_t cam, uint8_t *buf,
                                       size_t buf_len, gl_strip_t *strip)
{
    gl_status_t st = gl_ov7692_capture_start(d, cam, buf, buf_len, strip);
    if (st != GL_OK) {
        return st;
    }
    /* plain 1 ms polling: does not touch the application's interrupt state */
    for (;;) {
        st = gl_ov7692_capture_poll(d);
        if (st != GL_ERR_BUSY) {
            return st;
        }
        gl_hal_delay_ms(1);
    }
}
