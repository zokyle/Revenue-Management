/*
 * gl_factory.c - the factory and calibration commands.  See gl_factory.h and
 * the command list in core/gl_proto.h.
 *
 * Every handler checks its arguments and answers a defined status; none
 * blocks for longer than a camera exposure with its settling (about 0.2 s)
 * or one grain cycle (about 10 ms).
 */
#include "gl_factory.h"

#include <math.h>
#include <string.h>

#include "gl_app.h"
#include "gl_buf.h"
#include "gl_cam.h"
#include "gl_config.h"
#include "gl_crc.h"
#include "gl_hal.h"
#include "gl_provisional.h"
#include "gl_usb_ids.h"
#include "grain_frontend.h"

/* scratch of the two fits (static: not on the stack) */
static float fit_temp_[GL_PROTO_TEMPCO_MAX_POINTS];
static gl_vec3_t fit_off_[GL_PROTO_TEMPCO_MAX_POINTS];
static float floor_mod_[GL_PROTO_FLOOR_MAX_READINGS];
static float floor_scratch_[GL_PROTO_FLOOR_MAX_READINGS];

static int16_t temp_x10_(bool valid, float t)
{
    return valid ? (int16_t)gl_roundi(gl_clampf(t, -100.0f, 200.0f) * 10.0f)
                 : (int16_t)GL_PROTO_TEMP_NONE;
}

/* The factory uses devices the read uses: not while a read or another
 * procedure runs. */
static bool idle_(const gl_app_t *app)
{
    return !app->capture_active && !app->tilt_active && !gl_read_busy(&app->read) &&
           !app->cam.powered && !app->zero.active && !app->six.active && !app->log_erasing;
}

/* ---- identity ----------------------------------------------------------------- */

static bool cal_complete_(const gl_app_t *app)
{
    const uint8_t tilt = GL_CAL_TILT_FLAG_FACTORY | GL_CAL_TILT_FLAG_FLIP | GL_CAL_TILT_FLAG_BASE |
                         GL_CAL_TILT_FLAG_TEMPCO;
    const uint8_t cam = GL_CAL_CAM_FLAG_ALL;
    return (app->cal_tilt.flags & tilt) == tilt &&
           (app->cal_cam[GL_CAM_LEFT].flags & cam) == cam &&
           (app->cal_cam[GL_CAM_RIGHT].flags & cam) == cam &&
           (app->cal_grain.flags & GL_CAL_GRAIN_FLAG_WHITE_REF) != 0u &&
           (app->cal_dev.flags & GL_CAL_DEV_FLAG_ALL) == GL_CAL_DEV_FLAG_ALL;
}

static gl_status_t ident_(gl_app_t *app, const uint8_t *in, size_t n, uint8_t *out, size_t *len)
{
    gl_proto_ident_t id;
    uint16_t crc[5];
    static const char model[8] = "GL-1";
    static const char rev[] = GL_CFG_PARAMS_REV;
    const uint8_t host = (n >= 1u) ? in[0] : (uint8_t)GL_PROTO_VERSION;

    if (n >= 1u && host == 0u) {
        return GL_ERR_PARAM; /* there is no protocol version 0 */
    }
    memset(&id, 0, sizeof(id));
    id.proto_version = (uint8_t)GL_PROTO_VERSION;
    id.agreed_version = (host < GL_PROTO_VERSION) ? host : (uint8_t)GL_PROTO_VERSION;
    id.hw_rev = (uint8_t)GL_APP_HW_REV;
    id.hw_letter = GL_APP_HW_REV_LETTER;
    memcpy(id.model, model, sizeof(id.model));
    id.fw_version = (uint16_t)GL_APP_FW_VERSION;
    id.cal_version = (uint8_t)GL_CAL_VERSION;
    id.log_layout = (uint8_t)GL_FIELDLOG_LAYOUT;
    id.fw_build = GL_APP_FW_BUILD;
    id.solver_version = gl_solver_version();
    gl_hal_unique_id(id.unique_id);
    id.serial = gl_cal_serial_from_uid(id.unique_id);
    gl_app_cal_ids(app, id.cal_flags, crc);
    if ((app->cal_dev.flags & GL_CAL_DEV_FLAG_SERIAL) != 0u) {
        id.serial_stored = app->cal_dev.serial;
        id.flags |= (uint8_t)GL_PROTO_IDENT_SERIAL_STORED;
        if (memcmp(app->cal_dev.unique_id, id.unique_id, sizeof(id.unique_id)) == 0) {
            id.flags |= (uint8_t)GL_PROTO_IDENT_SERIAL_MATCH;
        }
    }
    if (GL_USB_IDS_ARE_PLACEHOLDERS == 0) {
        id.flags |= (uint8_t)GL_PROTO_IDENT_RELEASE;
    }
    if (app->proto.unlocked) {
        id.flags |= (uint8_t)GL_PROTO_IDENT_UNLOCKED;
    }
    if (cal_complete_(app)) {
        id.flags |= (uint8_t)GL_PROTO_IDENT_CAL_COMPLETE;
    }
    for (size_t i = 0; i < sizeof(id.params_rev) - 1u && i < sizeof(rev) - 1u; i++) {
        id.params_rev[i] = rev[i];
    }
    gl_proto_command_map(&app->proto, id.commands);
    gl_proto_ident_encode(&id, out);
    *len = GL_PROTO_IDENT_LEN;
    return GL_OK;
}

static gl_status_t sensors_(gl_app_t *app, uint8_t *out, size_t *len)
{
    gl_proto_sensors_t s;
    const gl_power_t *p = &app->power;
    gl_status_t st;

    if (!idle_(app)) {
        return GL_ERR_BUSY;
    }
    st = gl_app_power_refresh(app); /* battery, VDDA, NTC2, die: measured now */
    if (st == GL_ERR_BUSY) {
        return st;
    }
    memset(&s, 0, sizeof(s));
    s.battery_mv = p->batt_mv;
    s.vdda_mv = p->vdda_mv;
    s.cell_temp_c_x10 = temp_x10_(p->cell_temp_valid, p->cell_temp_c);
    s.mcu_temp_c_x10 = temp_x10_(p->mcu_temp_valid, p->mcu_temp_c);
    s.imu_temp_c_x10 = temp_x10_(app->temp_valid, app->temp_c);
    s.ntc_counts = p->ntc_counts;
    s.ntc_full_scale = (uint16_t)GL_HAL_ADC_FULL_SCALE;
    s.ntc_fault = p->ntc_fault;
    s.flags = (uint8_t)((p->vbus ? 1u : 0u) | (gl_hal_usb_supply_ok() ? 2u : 0u) |
                        (app->cam.powered ? 4u : 0u) | (p->charging ? 8u : 0u) |
                        (p->inhibit ? 16u : 0u) | (app->fac.sleep_armed ? 32u : 0u));
    s.sleep_wake = app->fac.last_wake;
    s.sleep_mask = app->fac.last_mask;
    s.sleep_ms = app->fac.last_sleep_ms;
    s.uptime_ms = gl_hal_tick_ms();
    gl_proto_sensors_encode(&s, out);
    *len = GL_PROTO_SENSORS_LEN;
    return GL_OK;
}

/* ---- cameras ------------------------------------------------------------------ */

/* E13 applies to the factory too: no camera is powered from a cell above
 * 60 C.  The temperature was measured at most 5 s ago in the cradle. */
static bool cam_allowed_(gl_app_t *app)
{
    return gl_app_camera_allowed(app);
}

static gl_status_t cam_id_(gl_app_t *app, const uint8_t *in, uint8_t *out, size_t *len)
{
    uint16_t pid = 0;
    gl_status_t st;
    if (in[0] >= (uint8_t)GL_CAM_COUNT) {
        return GL_ERR_PARAM;
    }
    if (!idle_(app)) {
        return GL_ERR_BUSY;
    }
    if (!cam_allowed_(app)) {
        return GL_ERR_STATE;
    }
    gl_hal_watchdog_kick();
    st = gl_ov7692_probe(&app->cam, (gl_cam_id_t)in[0], &pid);
    if (st != GL_OK) {
        app->last_error = (uint16_t)st;
        return st; /* GL_ERR_IO: the camera does not answer */
    }
    out[0] = in[0];
    gl_put_u16(&out[1], pid);
    out[3] = (pid == GL_PROV_OV7692_PID) ? 1u : 0u; /* 1: the id the driver expects */
    *len = 4;
    return GL_OK;
}

/* One exposure of a window into the image memory of the read. */
static gl_status_t capture_(gl_app_t *app, gl_cam_id_t cam, uint16_t x0, uint16_t y0, uint16_t w,
                            uint16_t h, gl_strip_t *strip)
{
    gl_status_t st;
    if ((uint32_t)w * h > GL_PROTO_CAPTURE_MAX_BYTES || (uint32_t)w * h > sizeof(app->read.img)) {
        return GL_ERR_PARAM;
    }
    app->fac.cap_valid = false;
    gl_hal_watchdog_kick();
    gl_app_clock_fast(app, true);
    st = gl_ov7692_power_up(&app->cam);
    if (st == GL_OK) {
        st = gl_ov7692_select(&app->cam, cam, GL_OV_OTHER_SLEEP);
    }
    if (st == GL_OK) {
        st = gl_ov7692_set_window(&app->cam, cam, x0, y0, w, h);
    }
    if (st == GL_OK) {
        st = gl_ov7692_capture_blocking(&app->cam, cam, app->read.img, sizeof(app->read.img),
                                        strip);
    }
    gl_ov7692_power_down(&app->cam);
    gl_app_clock_fast(app, false);
    gl_hal_watchdog_kick();
    if (st != GL_OK) {
        app->last_error = (uint16_t)st;
    }
    return st;
}

static gl_status_t cam_capture_(gl_app_t *app, const uint8_t *in, uint8_t *out, size_t *len)
{
    gl_proto_capture_t *c = &app->fac.cap;
    gl_strip_t strip;
    const uint16_t x0 = gl_get_u16(&in[2]), y0 = gl_get_u16(&in[4]);
    const uint16_t w = gl_get_u16(&in[6]), h = gl_get_u16(&in[8]);
    uint32_t sum = 0, bright = 0;
    uint8_t lo = 255, hi = 0;
    gl_status_t st;

    if (in[0] >= (uint8_t)GL_CAM_COUNT || in[1] > (uint8_t)GL_CAPTURE_DARK || w == 0u || h == 0u ||
        (w & 3u) != 0u || (h & 1u) != 0u || w > GL_OV7692_SENSOR_W || h > GL_OV7692_SENSOR_H ||
        x0 >= GL_OV7692_SENSOR_W || y0 >= GL_OV7692_SENSOR_H ||
        (uint32_t)w * h > GL_PROTO_CAPTURE_MAX_BYTES) {
        return GL_ERR_PARAM;
    }
    if (!idle_(app)) {
        return GL_ERR_BUSY;
    }
    if (!cam_allowed_(app)) {
        return GL_ERR_STATE;
    }
    memset(&strip, 0, sizeof(strip));
    st = capture_(app, (gl_cam_id_t)in[0], x0, y0, w, h, &strip);
    if (st != GL_OK) {
        return st;
    }
    memset(c, 0, sizeof(*c));
    c->camera = in[0];
    c->kind = in[1];
    c->x0 = strip.x0;
    c->y0 = strip.y0;
    c->width = strip.width;
    c->height = strip.height;
    c->bytes = (uint32_t)strip.width * strip.height;
    for (uint32_t i = 0; i < c->bytes; i++) {
        const uint8_t v = app->read.img[i];
        sum += v;
        lo = (v < lo) ? v : lo;
        hi = (v > hi) ? v : hi;
        bright += (v > GL_PROTO_DARK_BRIGHT_LEVEL) ? 1u : 0u;
    }
    c->min = lo;
    c->max = hi;
    c->mean_x16 = (uint16_t)((16u * (uint64_t)sum + c->bytes / 2u) / c->bytes);
    c->bright = bright;
    c->crc32 = gl_crc32(app->read.img, c->bytes);
    app->fac.cap_valid = true;
    gl_proto_capture_encode(c, out);
    *len = GL_PROTO_CAPTURE_LEN;
    return GL_OK;
}

static gl_status_t cam_data_(gl_app_t *app, const uint8_t *in, uint8_t *out, size_t cap,
                             size_t *len)
{
    const uint32_t off = gl_get_u32(&in[0]);
    const uint16_t n = gl_get_u16(&in[4]);
    if (!app->fac.cap_valid) {
        return GL_ERR_EMPTY; /* no capture, or a read has used the image memory since */
    }
    if (n == 0u || n > GL_PROTO_CAM_DATA_MAX || off >= app->fac.cap.bytes ||
        n > app->fac.cap.bytes - off || (size_t)n + 4u > cap) {
        return GL_ERR_PARAM;
    }
    gl_put_u32(&out[0], off);
    memcpy(&out[4], &app->read.img[off], n);
    *len = 4u + (size_t)n;
    return GL_OK;
}

/* Mean (x 16) and maximum of 2 * half + 1 rows about `row` of a band that
 * starts at sensor row `y0`, over GL_PROTO_FIELD_COLS centred columns. */
static uint16_t band_rows_(const uint8_t *img, uint16_t width, uint16_t height, uint16_t y0,
                           uint16_t row, uint8_t *max)
{
    const uint16_t c0 = (uint16_t)((width - GL_PROTO_FIELD_COLS) / 2u);
    uint32_t sum = 0, n = 0;
    uint8_t hi = 0;
    for (int r = (int)row - (int)GL_PROTO_FIELD_HALF_ROWS;
         r <= (int)row + (int)GL_PROTO_FIELD_HALF_ROWS; r++) {
        if (r < (int)y0 || r >= (int)y0 + (int)height) {
            continue;
        }
        for (uint16_t c = c0; c < c0 + GL_PROTO_FIELD_COLS; c++) {
            const uint8_t v = img[(uint32_t)(r - (int)y0) * width + c];
            sum += v;
            hi = (v > hi) ? v : hi;
            n++;
        }
    }
    *max = hi;
    return (uint16_t)((n == 0u) ? 0u : ((16u * sum + n / 2u) / n));
}

/* TEST GATE 2: where does this camera image +13.0 and -13.0 degrees of
 * elevation (straight ahead), and how bright are those rows? */
static gl_status_t cam_field_(gl_app_t *app, const uint8_t *in, uint8_t *out, size_t *len)
{
    gl_proto_field_t f;
    gl_cam_model_t model;
    gl_strip_t strip;
    const gl_vec3_t up = { 0.0f, 0.0f, 1.0f };
    const float e = GL_PROTO_FIELD_ELEV_DEG * (GL_PI_F / 180.0f);
    float u = 0.0f, v_up = 0.0f, v_lo = 0.0f;
    uint16_t rows[3];
    uint16_t means[3];
    uint8_t maxs[3];
    gl_status_t st;

    if (in[0] >= (uint8_t)GL_CAM_COUNT) {
        return GL_ERR_PARAM;
    }
    if (!idle_(app)) {
        return GL_ERR_BUSY;
    }
    if (!cam_allowed_(app)) {
        return GL_ERR_STATE;
    }
    gl_cam_model_init(&model, &app->cal_cam[in[0]]);
    if (!gl_cam_ray_to_pixel(&model, gl_cam_bearing_elev_to_ray(0.0f, e, up), &u, &v_up) ||
        !gl_cam_ray_to_pixel(&model, gl_cam_bearing_elev_to_ray(0.0f, -e, up), &u, &v_lo) ||
        v_up < (float)GL_PROTO_FIELD_HALF_ROWS ||
        v_lo > (float)(GL_OV7692_SENSOR_H - 1u - GL_PROTO_FIELD_HALF_ROWS) || v_up >= v_lo) {
        return GL_ERR_RANGE; /* with this calibration a bar is not on the sensor */
    }
    memset(&f, 0, sizeof(f));
    f.camera = in[0];
    rows[0] = (uint16_t)gl_roundi(v_up);
    rows[1] = (uint16_t)gl_roundi(v_lo);
    rows[2] = (uint16_t)gl_roundi(app->cal_cam[in[0]].cy_px);
    /* three exposures of an 8-row band each (the driver's rows come in
     * pairs): upper bar, lower bar, the centre as a reference */
    for (int i = 0; i < 3; i++) {
        const uint16_t y0 = (uint16_t)((rows[i] - GL_PROTO_FIELD_HALF_ROWS) & ~1u);
        memset(&strip, 0, sizeof(strip));
        st = capture_(app, (gl_cam_id_t)in[0], 0, y0, GL_OV7692_SENSOR_W, 8, &strip);
        if (st != GL_OK) {
            return st;
        }
        means[i] = band_rows_(app->read.img, strip.width, strip.height, strip.y0, rows[i],
                              &maxs[i]);
    }
    f.row_upper = rows[0];
    f.row_lower = rows[1];
    f.mean_upper_x16 = means[0];
    f.mean_lower_x16 = means[1];
    f.mean_centre_x16 = means[2];
    f.max_upper = maxs[0];
    f.max_lower = maxs[1];
    if (means[1] == 0u) {
        f.ratio_x1000 = 65535u;
    } else {
        const uint32_t r = (1000u * (uint32_t)means[0] + means[1] / 2u) / means[1];
        f.ratio_x1000 = (uint16_t)((r < 65535u) ? r : 65535u);
    }
    gl_proto_field_encode(&f, out);
    *len = GL_PROTO_FIELD_LEN;
    return GL_OK;
}

/* ---- display ------------------------------------------------------------------ */

static void pattern_draw_(gl_app_t *app, uint8_t pattern)
{
    gl_gfx_t *g = &app->gfx;
    gl_gfx_set_clip(g, false); /* the whole panel: the corners are tested too */
    gl_gfx_clear(g, GL_INK_WHITE);
    switch (pattern) {
    case GL_DISP_PATTERN_BLACK:
        gl_gfx_clear(g, GL_INK_BLACK);
        break;
    case GL_DISP_PATTERN_CHECKER_1:
    case GL_DISP_PATTERN_CHECKER_8: {
        const int sh = (pattern == (uint8_t)GL_DISP_PATTERN_CHECKER_8) ? 3 : 0;
        for (int y = 0; y < GL_GFX_H; y++) {
            for (int x = 0; x < GL_GFX_W; x++) {
                if ((((x >> sh) + (y >> sh)) & 1) != 0) {
                    gl_gfx_pixel(g, x, y, GL_INK_BLACK);
                }
            }
        }
        break;
    }
    case GL_DISP_PATTERN_ROWS:
        for (int y = 0; y < GL_GFX_H; y += 2) {
            gl_gfx_hline(g, 0, GL_GFX_W - 1, y, GL_INK_BLACK);
        }
        break;
    case GL_DISP_PATTERN_COLUMNS:
        for (int x = 0; x < GL_GFX_W; x += 2) {
            gl_gfx_vline(g, x, 0, GL_GFX_H - 1, GL_INK_BLACK);
        }
        break;
    case GL_DISP_PATTERN_ORIENT:
        gl_gfx_frame(g, 0, 0, GL_GFX_W, GL_GFX_H, GL_INK_BLACK);
        gl_gfx_hline(g, 44, 83, 63, GL_INK_BLACK);
        gl_gfx_hline(g, 44, 83, 64, GL_INK_BLACK);
        gl_gfx_vline(g, 63, 44, 83, GL_INK_BLACK);
        gl_gfx_vline(g, 64, 44, 83, GL_INK_BLACK);
        gl_gfx_text_centred(g, 64, 20, "F", 3, GL_INK_BLACK); /* top = toward the visor */
        break;
    case GL_DISP_PATTERN_REF_RAW:
    case GL_DISP_PATTERN_REF_CORRECTED: {
        /* the reference line: along the marker's forward axis through the
         * screen centre, 3 pixels wide, with the edge dithering of the aim
         * line (its direction is resolved finer than a pixel); CORRECTED:
         * turned by the stored rotation, exactly as the aim line is */
        const float rot = (pattern == (uint8_t)GL_DISP_PATTERN_REF_CORRECTED)
                              ? app->cal_dev.display_rot_rad : 0.0f;
        const gl_gfx_line_style_t style = { 0.0f, 0.0f, true };
        gl_gfx_set_clip(g, true);
        (void)gl_gfx_line_angle(g, GL_GFX_CENTRE_F, GL_GFX_CENTRE_F, rot, 1.5f, &style,
                                GL_INK_BLACK);
        break;
    }
    default: /* WHITE */
        break;
    }
    gl_gfx_set_clip(g, true);
}

bool gl_factory_draw(gl_app_t *app)
{
    if (app->fac.pattern == (uint8_t)GL_DISP_PATTERN_NORMAL) {
        return false;
    }
    pattern_draw_(app, app->fac.pattern);
    app->fac.pattern_black = (uint16_t)gl_gfx_count_black(&app->gfx);
    app->fac.pattern_crc = gl_crc32(app->gfx.px, sizeof(app->gfx.px));
    return true;
}

static gl_status_t display_test_(gl_app_t *app, const uint8_t *in, size_t n, uint8_t *out,
                                 size_t *len)
{
    const bool plate = (n >= 3u && in[2] != 0u);
    if (in[0] >= (uint8_t)GL_DISP_PATTERN_COUNT ||
        (in[0] != (uint8_t)GL_DISP_PATTERN_NORMAL && (in[1] == 0u || in[1] > 120u)) ||
        (n >= 3u && in[2] > 1u) || (plate && in[0] == (uint8_t)GL_DISP_PATTERN_NORMAL)) {
        return GL_ERR_PARAM;
    }
    if (!app->lcd.on) {
        return GL_ERR_STATE;
    }
    app->fac.pattern = in[0];
    app->fac.pattern_until_ms = gl_hal_tick_ms() + 1000u * (uint32_t)in[1];
    app->fac.pattern_crc = 0;
    app->fac.pattern_black = 0;
    /* every new command replaces an arming; "normal" cancels it */
    app->fac.plate_armed = plate;
    app->fac.plate_showing = false;
    if (plate) {
        app->fac.plate_pattern = in[0];
        app->fac.plate_hold_s = in[1];
        app->fac.plate_armed_ms = gl_hal_tick_ms();
    }
    if (in[0] != (uint8_t)GL_DISP_PATTERN_NORMAL) {
        /* drawn into the frame buffer now, so that the answer can describe
         * it; the screen update of this loop pass sends it to the panel */
        (void)gl_factory_draw(app);
    }
    app->redraw = true;
    out[0] = in[0];
    gl_put_u32(&out[1], app->fac.pattern_crc);
    gl_put_u16(&out[5], app->fac.pattern_black);
    *len = 7;
    return GL_OK;
}

bool gl_factory_holds_ui(const gl_app_t *app)
{
    return app->fac.plate_showing;
}

/* ---- grain LEDs and the photodiode ---------------------------------------------- */

static gl_grain_raw_t grain_raw_;

static gl_status_t grain_test_(gl_app_t *app, const uint8_t *in, uint8_t *out, size_t *len)
{
    gl_proto_grain_t g;
    gl_status_t st;

    if (in[0] > (uint8_t)GL_GRAIN_MODE_STORE) {
        return GL_ERR_PARAM;
    }
    if (!idle_(app)) {
        return GL_ERR_BUSY;
    }
    memset(&g, 0, sizeof(g));
    g.mode = in[0];
    g.status = (uint8_t)GL_ERR_EMPTY;
    g.full_scale = (uint16_t)GL_HAL_ADC_FULL_SCALE;
    st = gl_grain_fe_power(true); /* GL_ERR_STATE if the display is off: it feeds the bias */
    if (st == GL_OK) {
        st = gl_grain_fe_dark(GL_PROTO_GRAIN_DARK_SAMPLES, &g.dark_mean, &g.dark_min, &g.dark_max);
    }
    if (st == GL_OK && in[0] == (uint8_t)GL_GRAIN_MODE_CYCLE) {
        const gl_status_t cs = gl_grain_fe_measure_cycle(&grain_raw_, 0);
        g.status = (uint8_t)cs;
        if (cs == GL_OK) {
            for (unsigned i = 0; i < GL_GRAIN_LEDS; i++) {
                g.led[i][0] = grain_raw_.s[0][i].dark1;
                g.led[i][1] = grain_raw_.s[0][i].on;
                g.led[i][2] = grain_raw_.s[0][i].dark2;
            }
        }
    }
    (void)gl_grain_fe_power(false);
    if (st != GL_OK) {
        app->last_error = (uint16_t)st;
        return st;
    }
    if (in[0] == (uint8_t)GL_GRAIN_MODE_STORE) {
        const gl_cal_grain_t before = app->cal_grain;
        app->cal_grain.pd_dark_counts = g.dark_mean;
        app->cal_grain.flags |= (uint8_t)GL_CAL_GRAIN_FLAG_DARK_OFFSET;
        st = gl_app_cal_store(app, (uint8_t)GL_CAL_ID_GRAIN);
        if (st != GL_OK) {
            app->cal_grain = before;
            return st;
        }
    }
    g.stored_dark = ((app->cal_grain.flags & GL_CAL_GRAIN_FLAG_DARK_OFFSET) != 0u)
                        ? app->cal_grain.pd_dark_counts : 0u;
    gl_proto_grain_encode(&g, out);
    *len = GL_PROTO_GRAIN_LEN;
    return GL_OK;
}

/* ---- level zero, armed ------------------------------------------------------------ */

static gl_status_t level_zero_(gl_app_t *app, const uint8_t *in, size_t n, uint8_t *out,
                               size_t *len)
{
    gl_proto_zero_t *z = &app->fac.zero;
    const uint8_t rest = (n >= 3u) ? in[2] : 0u;
    if (in[0] > (uint8_t)GL_ZERO_OP_CANCEL || in[1] >= (uint8_t)GL_CAL_SEAT_COUNT || rest > 120u ||
        (rest != 0u && in[0] != (uint8_t)GL_ZERO_OP_ARM)) {
        return GL_ERR_PARAM;
    }
    if (in[0] == (uint8_t)GL_ZERO_OP_ARM) {
        if (!app->imu_ok || !app->storage_ok) {
            return GL_ERR_STATE; /* nothing to measure with, or nowhere to store it */
        }
        memset(z, 0, sizeof(*z));
        z->state = (uint8_t)GL_ZERO_STATE_ARMED;
        z->seat = in[1];
        z->rest_min = rest;
        z->ntc2_x10 = GL_PROTO_TEMP_NONE;
        app->fac.zero_armed_ms = gl_hal_tick_ms();
    } else if (in[0] == (uint8_t)GL_ZERO_OP_CANCEL) {
        if (z->state == (uint8_t)GL_ZERO_STATE_ARMED) {
            z->state = (uint8_t)GL_ZERO_STATE_IDLE;
        }
    }
    gl_proto_zero_encode(z, out);
    *len = GL_PROTO_ZERO_LEN;
    return GL_OK;
}

void gl_factory_zero_result(gl_app_t *app, gl_status_t st, gl_vec2_t bias, gl_vec2_t surface,
                            float yaw_rad, float scatter)
{
    gl_proto_zero_t *z = &app->fac.zero;
    z->status = (uint8_t)st;
    z->scatter = scatter;
    z->turn_rad = yaw_rad;
    if (st == GL_OK) {
        z->state = (uint8_t)GL_ZERO_STATE_DONE;
        z->bias_x = bias.x;
        z->bias_y = bias.y;
        z->surface_x = surface.x;
        z->surface_y = surface.y;
        z->temp_c = app->temp_valid ? app->temp_c : app->cal_tilt.t0_c;
        z->time_s = gl_hal_rtc_seconds();
        /* the cell thermistor, as the read gate measured it when the marker
         * woke for this placement (the soak rule of step 19 is on NTC2) */
        z->ntc2_x10 = temp_x10_(app->cell_seen && app->power.cell_temp_valid &&
                                    app->power.ntc_fault == (uint8_t)GL_NTC_OK,
                                app->power.cell_temp_c);
    } else if (z->attempts < GL_FACTORY_ZERO_MAX_ATTEMPTS && st != GL_ERR_STATE) {
        z->state = (uint8_t)GL_ZERO_STATE_ARMED; /* the operator tries again on the plate */
    } else {
        z->state = (uint8_t)GL_ZERO_STATE_FAILED;
    }
}

/* ---- six-face progress, temperature fit, horizon, grain floor, rotation, serial ---- */

static gl_status_t cal_status_(gl_app_t *app, uint8_t *out, size_t *len)
{
    gl_proto_six_t x;
    memset(&x, 0, sizeof(x));
    x.done_mask = app->six.done_mask;
    x.active = app->six.active ? 1u : 0u;
    x.face = app->six.face;
    x.cal_flags = app->cal_tilt.flags;
    for (unsigned f = 0; f < 6u; f++) {
        if ((app->six.done_mask & (1u << f)) != 0u) {
            x.mean[f][0] = app->six.meas[f].x;
            x.mean[f][1] = app->six.meas[f].y;
            x.mean[f][2] = app->six.meas[f].z;
        }
    }
    x.temp_c = app->temp_valid ? app->temp_c : 0.0f;
    gl_proto_six_encode(&x, out);
    *len = GL_PROTO_SIX_LEN;
    return GL_OK;
}

/* The temperature terms of the tilt record (the convention is at
 * GL_CMD_TILT_TEMPCO in core/gl_proto.h).  Until the phase-3 review this
 * command also REPLACED the six-face offsets by the constant term of the
 * fit: drift data (which is what the chamber procedure of the manufacturing
 * plan yields) then wiped 12 and 7 mg of offset - 12 and 7 mrad of tilt -
 * with status 0 and the FACTORY flag still set (factory finding 1). */
static gl_status_t tempco_(gl_app_t *app, const uint8_t *in, size_t n, uint8_t *out, size_t *len)
{
    const unsigned pts = in[0];
    const float t0 = gl_get_f32(&in[1]);
    gl_cal_tilt_t cal = app->cal_tilt;
    gl_cal_tilt_t fit;
    float sq = 0.0f, worst = 0.0f, t_min = 1000.0f, t_max = -1000.0f;
    gl_status_t st;

    if (pts < GL_PROTO_TEMPCO_MIN_POINTS || pts > GL_PROTO_TEMPCO_MAX_POINTS ||
        n != 5u + 16u * (size_t)pts || !isfinite(t0) || t0 < -40.0f || t0 > 85.0f) {
        return GL_ERR_PARAM;
    }
    for (unsigned i = 0; i < pts; i++) {
        const uint8_t *p = &in[5u + 16u * i];
        fit_temp_[i] = gl_get_f32(&p[0]);
        fit_off_[i].x = gl_get_f32(&p[4]);
        fit_off_[i].y = gl_get_f32(&p[8]);
        fit_off_[i].z = gl_get_f32(&p[12]);
        if (!isfinite(fit_temp_[i]) || fit_temp_[i] < -40.0f || fit_temp_[i] > 85.0f ||
            !isfinite(fit_off_[i].x) || !isfinite(fit_off_[i].y) || !isfinite(fit_off_[i].z) ||
            fabsf(fit_off_[i].x) > 0.5f || fabsf(fit_off_[i].y) > 0.5f ||
            fabsf(fit_off_[i].z) > 0.5f) {
            return GL_ERR_PARAM;
        }
        t_min = (fit_temp_[i] < t_min) ? fit_temp_[i] : t_min;
        t_max = (fit_temp_[i] > t_max) ? fit_temp_[i] : t_max;
    }
    if (t_max - t_min < GL_PROTO_TEMPCO_MIN_SPAN_K) {
        return GL_ERR_PARAM; /* a quadratic over a short span: its ends are anybody's guess */
    }
    /* the terms are added to offsets that must be there, about THEIR temperature */
    if ((cal.flags & (uint8_t)GL_CAL_TILT_FLAG_FACTORY) == 0u) {
        return GL_ERR_STATE;
    }
    if (fabsf(t0 - cal.t0_c) > GL_PROTO_TEMPCO_T0_TOL_K) {
        return GL_ERR_RANGE; /* the host's idea of the six-face temperature is not the record's */
    }
    fit = cal;
    st = gl_tilt_tempco_fit(fit_temp_, fit_off_, pts, cal.t0_c, &fit);
    if (st != GL_OK) {
        return st; /* fewer than three distinct temperatures */
    }
    /* ONLY the temperature terms are taken; offset_g and t0_c stay */
    for (int a = 0; a < 3; a++) {
        cal.tempco1_g_per_k[a] = fit.tempco1_g_per_k[a];
        cal.tempco2_g_per_k2[a] = fit.tempco2_g_per_k2[a];
    }
    cal.flags |= (uint8_t)GL_CAL_TILT_FLAG_TEMPCO;
    {
        /* what the stored record would hold must pass its own range check */
        uint8_t blob[GL_CAL_TILT_BLOB_LEN];
        gl_cal_tilt_t chk;
        gl_cal_tilt_encode(&cal, blob);
        st = gl_cal_tilt_decode(blob, sizeof(blob), &chk);
        if (st != GL_OK) {
            return st; /* GL_ERR_RANGE: a coefficient beyond what the record accepts */
        }
    }
    /* A level zero that is already stored was measured with the OLD
     * correction at its own temperature.  If the new terms change the
     * correction there by more than half a milli-g, that zero would be
     * silently wrong by as much: refused - the zeros are taken after the fit. */
    {
        const uint8_t zf[2] = { GL_CAL_TILT_FLAG_FLIP, GL_CAL_TILT_FLAG_BASE };
        const float zt[2] = { cal.flip_temp_c, cal.base_temp_c };
        for (int k = 0; k < 2; k++) {
            if ((cal.flags & zf[k]) != 0u) {
                const float dt = zt[k] - cal.t0_c, dt0 = zt[k] - app->cal_tilt.t0_c;
                for (int a = 0; a < 2; a++) {
                    const float now = dt * (cal.tempco1_g_per_k[a] + dt * cal.tempco2_g_per_k2[a]);
                    const float was = dt0 * (app->cal_tilt.tempco1_g_per_k[a] +
                                             dt0 * app->cal_tilt.tempco2_g_per_k2[a]);
                    if (fabsf(now - was) > GL_FACTORY_TEMPCO_ZERO_SHIFT_MAX_G) {
                        return GL_ERR_STATE;
                    }
                }
            }
        }
    }
    for (unsigned i = 0; i < pts; i++) {
        const float dt = fit_temp_[i] - cal.t0_c;
        const float v[3] = { fit_off_[i].x, fit_off_[i].y, fit_off_[i].z };
        for (int a = 0; a < 3; a++) {
            const float r = v[a] - (fit.offset_g[a] + fit.tempco1_g_per_k[a] * dt +
                                    fit.tempco2_g_per_k2[a] * dt * dt);
            sq += r * r;
            worst = (fabsf(r) > worst) ? fabsf(r) : worst;
        }
    }
    {
        const gl_cal_tilt_t before = app->cal_tilt;
        app->cal_tilt = cal;
        st = gl_app_cal_store(app, (uint8_t)GL_CAL_ID_TILT);
        if (st != GL_OK) {
            app->cal_tilt = before;
            return st;
        }
    }
    for (int a = 0; a < 3; a++) {
        gl_put_f32(&out[4 * a], fit.offset_g[a]); /* b0: the fit at t0, NOT stored */
        gl_put_f32(&out[12 + 4 * a], cal.tempco1_g_per_k[a]);
        gl_put_f32(&out[24 + 4 * a], cal.tempco2_g_per_k2[a]);
    }
    gl_put_f32(&out[36], sqrtf(sq / (3.0f * (float)pts)));
    gl_put_f32(&out[40], worst);
    *len = 44;
    return GL_OK;
}

static gl_status_t cam_horizon_(gl_app_t *app, const uint8_t *in, uint8_t *out, size_t *len)
{
    gl_cal_cam_t cal;
    gl_status_t st;
    if (in[0] >= (uint8_t)GL_CAM_COUNT) {
        return GL_ERR_PARAM;
    }
    cal = app->cal_cam[in[0]];
    st = gl_cal_cam_set_horizon(&cal, gl_get_f32(&in[1]), gl_get_f32(&in[5]));
    if (st != GL_OK) {
        return st;
    }
    {
        const gl_cal_cam_t before = app->cal_cam[in[0]];
        app->cal_cam[in[0]] = cal;
        st = gl_app_cal_store(app, (uint8_t)((in[0] == 0u) ? GL_CAL_ID_CAM_L : GL_CAL_ID_CAM_R));
        if (st != GL_OK) {
            app->cal_cam[in[0]] = before;
            return st;
        }
    }
    gl_read_set_cal(&app->read, &app->cal_cam[GL_CAM_LEFT], &app->cal_cam[GL_CAM_RIGHT]);
    gl_put_f32(out, cal.pitch_up_rad);
    *len = 4;
    return GL_OK;
}

static gl_status_t grain_floor_(gl_app_t *app, const uint8_t *in, size_t n, uint8_t *out,
                                size_t *len)
{
    const unsigned cnt = in[0];
    gl_cal_grain_t cal = app->cal_grain;
    gl_status_t st;
    if (cnt < GL_PROTO_FLOOR_MIN_READINGS || cnt > GL_PROTO_FLOOR_MAX_READINGS ||
        n != 1u + 4u * (size_t)cnt) {
        return GL_ERR_PARAM;
    }
    for (unsigned i = 0; i < cnt; i++) {
        floor_mod_[i] = gl_get_f32(&in[1u + 4u * i]);
        if (!isfinite(floor_mod_[i]) || floor_mod_[i] < 0.0f || floor_mod_[i] > 2.0f) {
            return GL_ERR_PARAM;
        }
    }
    st = gl_grain_noise_floor(floor_mod_, cnt, floor_scratch_, &cal);
    if (st != GL_OK) {
        return st;
    }
    {
        const gl_cal_grain_t before = app->cal_grain;
        app->cal_grain = cal;
        st = gl_app_cal_store(app, (uint8_t)GL_CAL_ID_GRAIN);
        if (st != GL_OK) {
            app->cal_grain = before;
            return st;
        }
    }
    gl_put_f32(&out[0], cal.noise_floor_mod);
    gl_put_f32(&out[4], cal.mod_threshold);
    *len = 8;
    return GL_OK;
}

static gl_status_t display_rot_(gl_app_t *app, const uint8_t *in, size_t n, uint8_t *out,
                                size_t *len)
{
    if (in[0] > 1u || n != ((in[0] == 0u) ? 1u : 5u)) {
        return GL_ERR_PARAM;
    }
    if (in[0] == 1u) {
        const float rot = gl_get_f32(&in[1]);
        const gl_cal_device_t before = app->cal_dev;
        gl_status_t st;
        if (!isfinite(rot) || fabsf(rot) > GL_CAL_DISPLAY_ROT_MAX_RAD) {
            return GL_ERR_RANGE;
        }
        app->cal_dev.display_rot_rad = rot;
        app->cal_dev.flags |= (uint8_t)GL_CAL_DEV_FLAG_DISPLAY_ROT;
        app->cal_dev.time_s = gl_hal_rtc_seconds();
        st = gl_app_cal_store(app, (uint8_t)GL_CAL_ID_DEVICE);
        if (st != GL_OK) {
            app->cal_dev = before;
            return st;
        }
        app->view.display_rot_rad = rot;
        app->redraw = true;
    }
    gl_put_f32(&out[0], app->cal_dev.display_rot_rad);
    out[4] = ((app->cal_dev.flags & GL_CAL_DEV_FLAG_DISPLAY_ROT) != 0u) ? 1u : 0u;
    *len = 5;
    return GL_OK;
}

static gl_status_t serial_(gl_app_t *app, const uint8_t *in, size_t n, uint8_t *out, size_t *len)
{
    uint8_t uid[12];
    char text[8];
    uint32_t serial;
    if (n != 0u && (n != 4u || memcmp(in, "SNUM", 4) != 0)) {
        return GL_ERR_PARAM;
    }
    gl_hal_unique_id(uid);
    serial = gl_cal_serial_from_uid(uid);
    if (n == 4u) {
        const gl_cal_device_t before = app->cal_dev;
        gl_status_t st;
        memcpy(app->cal_dev.unique_id, uid, sizeof(uid));
        app->cal_dev.serial = serial;
        app->cal_dev.flags |= (uint8_t)GL_CAL_DEV_FLAG_SERIAL;
        app->cal_dev.time_s = gl_hal_rtc_seconds();
        st = gl_app_cal_store(app, (uint8_t)GL_CAL_ID_DEVICE);
        if (st != GL_OK) {
            app->cal_dev = before;
            return st;
        }
    }
    gl_cal_serial_text(serial, text);
    gl_put_u32(&out[0], serial);
    memcpy(&out[4], text, 7);
    out[11] = ((app->cal_dev.flags & GL_CAL_DEV_FLAG_SERIAL) != 0u &&
               memcmp(app->cal_dev.unique_id, uid, sizeof(uid)) == 0) ? 1u : 0u;
    *len = 12;
    return GL_OK;
}

/* ---- sleep-current test ------------------------------------------------------------- */

static gl_status_t sleep_test_(gl_app_t *app, const uint8_t *in, uint8_t *out, size_t *len)
{
    const uint8_t mask = in[0];
    const uint16_t seconds = gl_get_u16(&in[1]);
    if ((mask & (uint8_t)~(GL_PROTO_WAKE_MOTION | GL_PROTO_WAKE_TIMER | GL_PROTO_WAKE_VBUS)) != 0u ||
        ((mask & GL_PROTO_WAKE_TIMER) != 0u && seconds == 0u)) {
        return GL_ERR_PARAM;
    }
    if (mask == 0u) {
        app->fac.sleep_armed = false;
    } else {
        if (!app->power.vbus) {
            return GL_ERR_STATE;
        }
        app->fac.sleep_armed = true;
        app->fac.sleep_running = false;
        app->fac.sleep_due_valid = false;
        app->fac.sleep_mask = (uint8_t)(mask | GL_PROTO_WAKE_VBUS);
        app->fac.sleep_seconds = seconds;
    }
    out[0] = app->fac.sleep_armed ? 1u : 0u;
    out[1] = app->fac.sleep_armed ? app->fac.sleep_mask : 0u;
    *len = 2;
    return GL_OK;
}

bool gl_factory_sleep_no_motion(const gl_app_t *app)
{
    return app->fac.sleep_running && (app->fac.sleep_mask & GL_PROTO_WAKE_MOTION) == 0u;
}

void gl_factory_on_sleep(gl_app_t *app, uint32_t now_ms)
{
    if (app->fac.sleep_armed && !app->power.vbus && !app->fac.sleep_running) {
        app->fac.sleep_running = true;
        app->fac.sleep_start_ms = now_ms;
    }
}

void gl_factory_on_wake(gl_app_t *app, uint32_t now_ms)
{
    gl_factory_t *f = &app->fac;
    if (!f->sleep_running) {
        return;
    }
    f->last_sleep_ms = (uint32_t)(now_ms - f->sleep_start_ms);
    f->last_mask = f->sleep_mask;
    if (app->power.vbus) {
        f->last_wake = (uint8_t)GL_PROTO_WAKE_VBUS;
    } else if ((f->sleep_mask & GL_PROTO_WAKE_TIMER) != 0u &&
               f->last_sleep_ms >= 1000u * (uint32_t)f->sleep_seconds) {
        f->last_wake = (uint8_t)GL_PROTO_WAKE_TIMER;
    } else {
        f->last_wake = (uint8_t)GL_PROTO_WAKE_MOTION;
    }
    f->sleep_running = false;
    f->sleep_armed = false; /* one test per arming */
}

uint32_t gl_factory_time_left_ms(const gl_app_t *app, uint32_t now_ms)
{
    const gl_factory_t *f = &app->fac;
    int32_t left = 0;
    if (f->pattern != (uint8_t)GL_DISP_PATTERN_NORMAL) {
        left = (int32_t)(f->pattern_until_ms - now_ms);
    } else if (f->sleep_running && (f->sleep_mask & GL_PROTO_WAKE_TIMER) != 0u) {
        left = (int32_t)(f->sleep_start_ms + 1000u * (uint32_t)f->sleep_seconds - now_ms);
    } else if (f->sleep_armed && f->sleep_due_valid && !f->sleep_running) {
        left = (int32_t)(f->sleep_due_ms - now_ms);
    } else {
        return 0;
    }
    return (left > 0) ? (uint32_t)left : 1u;
}

void gl_factory_service(gl_app_t *app, uint32_t now_ms)
{
    gl_factory_t *f = &app->fac;

    /* how long the marker has been off VBUS (the rest of an armed zeroing) */
    if (app->power.vbus) {
        f->off_vbus_valid = false;
    } else if (!f->off_vbus_valid) {
        f->off_vbus_valid = true;
        f->off_vbus_since_ms = now_ms;
    }
    /* a display test ends by its time, and at once when the marker leaves
     * the cradle - unless it is the one being shown on the seat plate */
    if (f->pattern != (uint8_t)GL_DISP_PATTERN_NORMAL && !f->plate_showing &&
        ((int32_t)(now_ms - f->pattern_until_ms) >= 0 || !app->power.vbus)) {
        f->pattern = (uint8_t)GL_DISP_PATTERN_NORMAL;
        app->redraw = true;
    }
    /* a pattern armed for the seat plate (assembly step 19: the reference
     * line measured under the plate's camera, nothing on the pads) */
    if (f->plate_showing) {
        if ((int32_t)(now_ms - f->pattern_until_ms) >= 0 || app->power.vbus || !app->awake) {
            f->plate_showing = false;
            f->plate_armed = false;
            f->pattern = (uint8_t)GL_DISP_PATTERN_NORMAL;
            app->redraw = true;
            if (!app->power.vbus && app->awake) {
                gl_app_post(app, GL_EV_FORCE_SLEEP, 0);
            }
        } else {
            gl_ui_keepalive(&app->ui, now_ms); /* held where it is: no time-out, no read */
        }
    } else if (f->plate_armed) {
        if ((uint32_t)(now_ms - f->plate_armed_ms) > GL_FACTORY_PATTERN_ARM_TIMEOUT_MS) {
            f->plate_armed = false;
        } else if (app->awake && !app->power.vbus && app->lcd.on &&
                   app->ui.state == (uint8_t)GL_UI_WAIT_STILL) {
            f->plate_showing = true;
            f->plate_shown++;
            f->pattern = f->plate_pattern;
            f->pattern_until_ms = now_ms + 1000u * (uint32_t)f->plate_hold_s;
            app->redraw = true;
            gl_ui_keepalive(&app->ui, now_ms);
        }
    }
    /* the armed zeroing: when the marker lies out of the cradle, where a
     * read would start - and not before it has rested off VBUS for as long
     * as the ARM asked */
    if (f->zero.state == (uint8_t)GL_ZERO_STATE_ARMED) {
        const uint32_t rest_ms = 60000u * (uint32_t)f->zero.rest_min;
        if ((uint32_t)(now_ms - f->zero_armed_ms) > GL_FACTORY_ZERO_ARM_TIMEOUT_MS + rest_ms) {
            f->zero.state = (uint8_t)GL_ZERO_STATE_FAILED;
            f->zero.status = (uint8_t)GL_ERR_TIMEOUT;
        } else if (app->awake && !app->power.vbus && !app->zero.active && !f->plate_showing &&
                   f->off_vbus_valid && (uint32_t)(now_ms - f->off_vbus_since_ms) >= rest_ms &&
                   app->ui.state == (uint8_t)GL_UI_WAIT_STILL) {
            const uint32_t rested = (uint32_t)(now_ms - f->off_vbus_since_ms) / 60000u;
            f->zero.rested_min = (uint8_t)((rested > 255u) ? 255u : rested);
            gl_app_post(app, GL_EV_CAL_ARMED, 0);
        }
    }
    /* the sleep-current test */
    if (f->sleep_armed && !f->sleep_running) {
        if (app->power.vbus || app->vbus_pending) {
            f->sleep_due_valid = false;
        } else if (!f->sleep_due_valid) {
            f->sleep_due_valid = true;
            f->sleep_due_ms = now_ms + GL_FACTORY_SLEEP_SETTLE_MS;
        } else if ((int32_t)(now_ms - f->sleep_due_ms) >= 0 && app->awake) {
            gl_app_post(app, GL_EV_FORCE_SLEEP, 0);
        }
    }
    if (f->sleep_running && !app->awake && (f->sleep_mask & GL_PROTO_WAKE_TIMER) != 0u &&
        (uint32_t)(now_ms - f->sleep_start_ms) >= 1000u * (uint32_t)f->sleep_seconds) {
        gl_app_post(app, GL_EV_MOTION, 0); /* the UI's wake-up event */
    }
}

/* ---- dispatch ------------------------------------------------------------------------ */

gl_status_t gl_factory_cmd(void *ctx, uint8_t cmd, const uint8_t *in, size_t n, uint8_t *out,
                           size_t cap, size_t *len)
{
    gl_app_t *app = (gl_app_t *)ctx;
    *len = 0;
    if (cap < GL_PROTO_GRAIN_LEN) {
        return GL_ERR_FULL; /* (the protocol's response buffer is 1023 bytes) */
    }
    switch (cmd) {
    case GL_CMD_GET_IDENT: return ident_(app, in, n, out, len);
    case GL_CMD_GET_SENSORS: return sensors_(app, out, len);
    case GL_CMD_CAM_ID: return cam_id_(app, in, out, len);
    case GL_CMD_CAM_CAPTURE: return cam_capture_(app, in, out, len);
    case GL_CMD_CAM_DATA: return cam_data_(app, in, out, cap, len);
    case GL_CMD_CAM_FIELD: return cam_field_(app, in, out, len);
    case GL_CMD_DISPLAY_TEST: return display_test_(app, in, n, out, len);
    case GL_CMD_GRAIN_TEST: return grain_test_(app, in, out, len);
    case GL_CMD_LEVEL_ZERO: return level_zero_(app, in, n, out, len);
    case GL_CMD_CAL_STATUS: return cal_status_(app, out, len);
    case GL_CMD_TILT_TEMPCO: return tempco_(app, in, n, out, len);
    case GL_CMD_SET_CAM_HORIZON: return cam_horizon_(app, in, out, len);
    case GL_CMD_SET_GRAIN_FLOOR: return grain_floor_(app, in, n, out, len);
    case GL_CMD_DISPLAY_ROT: return display_rot_(app, in, n, out, len);
    case GL_CMD_SLEEP_TEST: return sleep_test_(app, in, out, len);
    case GL_CMD_SERIAL: return serial_(app, in, n, out, len);
    default: return GL_ERR_UNSUPPORTED;
    }
}
