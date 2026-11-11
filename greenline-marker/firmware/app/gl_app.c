/* gl_app.c - application main loop and glue.  See gl_app.h. */
#include "gl_app.h"

#include <math.h>
#include <string.h>

#include "gl_config.h"
#include "gl_grain.h"
#include "gl_hal.h"
#include "gl_provisional.h"
#include "grain_frontend.h"

/* The zeroing rule below ("never in the cradle") rests on the cradle seating
 * the marker one way round only (master_params.yaml, cradle.orientations). */
#if GL_CFG_CRADLE_ORIENTATIONS != 1
#error "cradle.orientations changed: revisit where the zeroing routine may run"
#endif

#define ALL_IRQS                                                                          \
    (GL_IRQ_IMU_INT1 | GL_IRQ_IMU_INT2 | GL_IRQ_VBUS_CHANGE | GL_IRQ_CHG_STAT |           \
     GL_IRQ_WAKE_TIMER | GL_IRQ_USB_RX | GL_IRQ_DCMI_DONE | GL_IRQ_TICK)

/* ======================================================================= */
/* small services                                                           */
/* ======================================================================= */

void gl_app_post(gl_app_t *app, gl_ui_event_t ev, int32_t arg)
{
    (void)gl_event_post(&app->events, (uint16_t)ev, arg);
}

gl_status_t gl_app_store_put(gl_app_t *app, uint8_t id, const uint8_t *data, size_t len)
{
    gl_status_t st;
    if (!app->storage_ok) {
        return GL_ERR_NOT_FOUND;
    }
    st = gl_store_put(&app->store, id, data, len);
    if (st != GL_OK) {
        app->last_error = (uint16_t)st;
    }
    return st;
}

void gl_app_log_event(gl_app_t *app, uint16_t code, int32_t arg)
{
    gl_log_event_t ev;
    uint8_t buf[GL_LOG_EVENT_LEN];
    if (!app->storage_ok) {
        return;
    }
    ev.rtc_s = gl_hal_rtc_seconds();
    ev.code = code;
    ev.arg = arg;
    gl_log_event_encode(&ev, buf);
    (void)gl_log_append(&app->log, (uint8_t)GL_LOG_REC_EVENT, 0, buf, sizeof(buf), NULL);
}

/* A device or bus failed: remember, log, show. */
static void fault_(gl_app_t *app, gl_status_t st)
{
    app->last_error = (uint16_t)st;
    gl_app_log_event(app, (uint16_t)GL_APP_LOGEV_FAULT, (int32_t)st);
    gl_app_post(app, GL_EV_FAULT, (int32_t)st);
}

gl_status_t gl_app_set_settings(gl_app_t *app, const gl_settings_t *s)
{
    uint8_t blob[GL_SETTINGS_BLOB_LEN];
    gl_settings_t v = *s;
    gl_status_t st = gl_settings_validate(&v);
    if (st != GL_OK) {
        return st;
    }
    app->settings = v;
    app->ui.edit = v;
    app->ui.saved = v;
    gl_settings_encode(&v, blob);
    st = gl_app_store_put(app, (uint8_t)GL_STORE_ID_SETTINGS, blob, sizeof(blob));
    /* without storage the settings still apply until the next reset */
    return (st == GL_ERR_NOT_FOUND) ? GL_OK : st;
}

/* Enable exactly the interrupt sources the present state needs. */
static void irq_setup_(gl_app_t *app)
{
    uint32_t on = GL_IRQ_VBUS_CHANGE | GL_IRQ_WAKE_TIMER;
    if (app->awake) {
        on |= GL_IRQ_IMU_INT2 | GL_IRQ_CHG_STAT;
    } else {
        on |= GL_IRQ_IMU_INT1;
    }
    if (app->usb_on) {
        on |= GL_IRQ_USB_RX;
    }
    if (app->capture_active) {
        on |= GL_IRQ_DCMI_DONE;
    }
    if (on != app->irq_mask) {
        gl_hal_irq_enable(ALL_IRQS & ~on, false);
        gl_hal_irq_enable(on, true);
        app->irq_mask = on;
    }
}

/* ======================================================================= */
/* storage                                                                  */
/* ======================================================================= */

static void load_store_(gl_app_t *app)
{
    const uint8_t *d = NULL;
    size_t n = 0;
    /* a blob that fails to decode leaves the defaults in place */
    if (gl_store_get(&app->store, (uint8_t)GL_STORE_ID_SETTINGS, &d, &n) == GL_OK) {
        (void)gl_settings_decode(d, n, &app->settings);
    }
    if (gl_store_get(&app->store, (uint8_t)GL_STORE_ID_CAL_TILT, &d, &n) == GL_OK) {
        (void)gl_cal_tilt_decode(d, n, &app->cal_tilt);
    }
    if (gl_store_get(&app->store, (uint8_t)GL_STORE_ID_CAL_CAM_L, &d, &n) == GL_OK) {
        (void)gl_cal_cam_decode(d, n, &app->cal_cam[GL_CAM_LEFT]);
    }
    if (gl_store_get(&app->store, (uint8_t)GL_STORE_ID_CAL_CAM_R, &d, &n) == GL_OK) {
        (void)gl_cal_cam_decode(d, n, &app->cal_cam[GL_CAM_RIGHT]);
    }
    if (gl_store_get(&app->store, (uint8_t)GL_STORE_ID_CAL_GRAIN, &d, &n) == GL_OK) {
        (void)gl_cal_grain_decode(d, n, &app->cal_grain);
    }
    if (gl_store_get(&app->store, (uint8_t)GL_STORE_ID_COURSE, &d, &n) == GL_OK) {
        (void)gl_stick_height_decode(d, n, &app->stick_height);
    }
}

/* One raw-strip log record being assembled (978 bytes: static, not stack). */
static uint8_t raw_chunk_[GL_LOG_RAW_HDR_LEN + GL_APP_RAW_CHUNK_BYTES];

/* Raw-strip logging for field data collection (settings.raw_log_level). */
static void strip_hook_(void *ctx, const gl_strip_t *s, gl_cam_id_t cam, uint8_t kind,
                        uint8_t frame_index)
{
    gl_app_t *app = (gl_app_t *)ctx;
    uint8_t *const buf = raw_chunk_;
    gl_log_raw_hdr_t h;
    const uint8_t level = app->settings.raw_log_level;
    const uint32_t total = (uint32_t)s->width * s->height;

    if (!app->storage_ok || level == (uint8_t)GL_RAWLOG_OFF || s->stride != s->width) {
        return;
    }
    if (level == (uint8_t)GL_RAWLOG_FIRST && !(kind == 1u && frame_index < 2u)) {
        return; /* only the first left / right pair of stick strips */
    }
    h.read_id = app->read_id;
    h.camera = (uint8_t)cam;
    h.kind = kind;
    h.frame_index = frame_index;
    h.reserved = 0;
    h.x0 = s->x0;
    h.y0 = s->y0;
    h.width = s->width;
    h.height = s->height;
    for (uint32_t off = 0; off < total; off += GL_APP_RAW_CHUNK_BYTES) {
        const uint32_t n = (total - off < GL_APP_RAW_CHUNK_BYTES) ? (total - off)
                                                                  : GL_APP_RAW_CHUNK_BYTES;
        h.offset = off;
        gl_log_raw_hdr_encode(&h, buf);
        memcpy(&buf[GL_LOG_RAW_HDR_LEN], &s->px[off], n);
        if (gl_log_append(&app->log, (uint8_t)GL_LOG_REC_RAW_CHUNK, 0, buf,
                          GL_LOG_RAW_HDR_LEN + (size_t)n, NULL) != GL_OK) {
            break;
        }
        gl_hal_watchdog_kick();
    }
    /* Writing a strip takes about half a second, so a read with raw logging
     * outlasts the UI's capture time limit: report progress.  (While a strip
     * is being written no IMU sample is processed, so a bump may go
     * unnoticed: acceptable for data collection, where the raw strips are
     * the product.) */
    gl_ui_keepalive(&app->ui, gl_hal_tick_ms());
}

/* ======================================================================= */
/* wake and sleep                                                           */
/* ======================================================================= */

static void usb_start_(gl_app_t *app)
{
    if (!app->usb_on && gl_hal_usb_start() == GL_OK) {
        app->usb_on = true;
        gl_proto_rx_reset(&app->proto);
    }
    irq_setup_(app);
}

static void usb_stop_(gl_app_t *app)
{
    if (app->usb_on) {
        gl_hal_usb_stop();
        app->usb_on = false;
        app->stream_mask = 0;
        app->six.active = false;
        gl_proto_disconnect(&app->proto);
    }
    irq_setup_(app);
}

/* Stop a tilt read / capture.  Afterwards the camera rail is off. */
static void abort_read_(gl_app_t *app)
{
    app->tilt_active = false;
    if (app->capture_active || gl_read_busy(&app->read) || app->cam.powered) {
        gl_read_abort(&app->read);
    }
    app->capture_active = false;
    gl_motion_set_strict(&app->motion, false);
    irq_setup_(app);
}

static void wake_(gl_app_t *app, uint32_t now)
{
    if (!app->lcd.on) {
        const gl_status_t st = gl_lcd_on(&app->lcd);
        if (st != GL_OK) {
            app->last_error = (uint16_t)st;
        }
    }
    if (!app->awake) {
        app->awake = true;
        if (app->imu_ok) {
            const gl_status_t st = gl_imu_start_measure(&app->imu);
            if (st != GL_OK) {
                app->imu_ok = false;
                fault_(app, st);
            }
        }
        gl_motion_init(&app->motion, GL_IMU_ACCEL_G_PER_LSB_2G, GL_IMU_GYRO_RAD_S_PER_LSB_1000);
        app->last_sample_ms = now;
        app->next_batt_ms = now; /* measure the battery at once */
        app->batt_low_sent = false;
    }
    irq_setup_(app);
}

static void enter_sleep_(gl_app_t *app)
{
    abort_read_(app);
    app->zero.active = false;
    app->six.active = false;
    gl_lcd_off(&app->lcd);
    if (app->usb_on) {
        usb_stop_(app);
    }
    if (app->imu_ok &&
        gl_imu_start_wake_on_motion(&app->imu, (uint16_t)GL_PROV_IMU_WAKE_THRESHOLD_MG) != GL_OK) {
        app->last_error = (uint16_t)GL_ERR_IO;
    }
    if (app->flash_ok) {
        (void)gl_mx25r_sleep(&app->flash);
    }
    app->awake = false;
    app->sleep_since_ms = gl_hal_tick_ms();
    irq_setup_(app);
}

/* ======================================================================= */
/* power                                                                    */
/* ======================================================================= */

static void vbus_service_(gl_app_t *app)
{
    gl_power_poll_pins(&app->power);
    if (app->power.vbus != app->ui.usb) {
        gl_app_post(app, app->power.vbus ? GL_EV_USB_ATTACH : GL_EV_USB_DETACH, 0);
    }
    (void)gl_power_charge_gate(&app->power, app->temp_c, app->temp_valid);
    if (app->ui.state == (uint8_t)GL_UI_CRADLE_USB) {
        app->redraw = true;
    }
}

static void battery_service_(gl_app_t *app, uint32_t now)
{
    if ((int32_t)(now - app->next_batt_ms) < 0) {
        return;
    }
    if (app->capture_active || app->tilt_active) {
        return; /* not while the camera rail loads the cell or a read runs */
    }
    app->next_batt_ms = now + GL_APP_BATT_PERIOD_MS;
    gl_power_poll_pins(&app->power);
    if (gl_power_measure(&app->power) != GL_OK) {
        app->last_error = (uint16_t)GL_ERR_IO;
    }
    if (app->imu_ok) {
        app->temp_valid = (gl_imu_read_temperature(&app->imu, &app->temp_c) == GL_OK);
    }
    (void)gl_power_charge_gate(&app->power, app->temp_c, app->temp_valid);
    /* Below the LOW threshold the battery symbol on the screens shows it;
     * the device keeps working.  Below CRITICAL it shows the low-battery
     * screen and goes to sleep (the UI's BATT_LOW event): no camera read is
     * started from a cell that the 90 mA camera rail could brown out. */
    if (app->power.critical && !app->power.vbus && !app->batt_low_sent) {
        app->batt_low_sent = true;
        gl_app_post(app, GL_EV_BATT_LOW, 0);
    }
    if (app->ui.state == (uint8_t)GL_UI_CRADLE_USB) {
        app->redraw = true;
    }
}

/* ======================================================================= */
/* tilt                                                                     */
/* ======================================================================= */

/* Turn the still blocks accumulated in the motion averager into a slope
 * reading (temperature-compensated, calibrated, zeroing bias NOT removed). */
static gl_status_t tilt_measure_(gl_app_t *app, gl_vec2_t *slope_raw, gl_vec3_t *up,
                                 gl_vec3_t *gyro_bias)
{
    gl_tilt_mean_t mean;
    gl_vec3_t acal;
    float temp = app->cal_tilt.t0_c;
    gl_status_t st = gl_tilt_avg_result(&app->motion.avg, &mean);
    if (st != GL_OK) {
        return st;
    }
    app->temp_valid = (gl_imu_read_temperature(&app->imu, &app->temp_c) == GL_OK);
    if (app->temp_valid) {
        temp = app->temp_c;
    }
    acal = gl_tilt_apply_cal(&app->cal_tilt, mean.accel_g, temp);
    st = gl_tilt_slope(acal, slope_raw);
    if (st != GL_OK) {
        return st;
    }
    *up = gl_vec3_unit(acal);
    *gyro_bias = mean.gyro_rad_s;
    return GL_OK;
}

/* Experimental grain reading (only when enabled in the settings; ships
 * disabled).  Blocks for about 150 ms; the IMU is compared before and after
 * as the motion verdict. */
/* One raw grain measurement (388 bytes), kept off the stack. */
static gl_grain_raw_t grain_raw_;

static void grain_read_(gl_app_t *app)
{
    gl_grain_raw_t *const raw_p = &grain_raw_;
    gl_grain_reading_t rd;
    gl_imu_raw_t before, after;
    bool moved = true;

    app->grain_valid = false;
    if (app->settings.grain_enable == 0u) {
        return;
    }
    if (gl_imu_read(&app->imu, &before) != GL_OK ||
        gl_grain_fe_measure(raw_p, GL_GRAIN_MAX_CYCLES) != GL_OK) {
        return;
    }
    if (gl_imu_read(&app->imu, &after) == GL_OK) {
        const float k = GL_IMU_ACCEL_G_PER_LSB_2G;
        moved = fabsf((float)(after.ax - before.ax) * k) > 0.02f ||
                fabsf((float)(after.ay - before.ay) * k) > 0.02f ||
                fabsf((float)(after.az - before.az) * k) > 0.02f;
    }
    raw_p->motion = moved;
    if (gl_grain_process(raw_p, &app->cal_grain, &rd) == GL_OK && rd.valid) {
        app->grain_valid = true;
        app->grain_modulation = rd.red.modulation;
        app->grain_azimuth_rad = rd.red.azimuth_rad;
    }
}

static void tilt_start_(gl_app_t *app)
{
    gl_tilt_avg_reset(&app->motion.avg);
    app->tilt_active = true;
    gl_motion_set_strict(&app->motion, true); /* any movement now aborts the read */
}

/* The 1 s average of a read is complete. */
static void tilt_finish_(gl_app_t *app)
{
    gl_vec2_t slope_raw;
    gl_vec3_t up, gyro_bias;
    const gl_status_t st = tilt_measure_(app, &slope_raw, &up, &gyro_bias);

    app->tilt_active = false;
    if (st != GL_OK) {
        app->last_error = (uint16_t)st;
        gl_app_post(app, GL_EV_TILT_FAIL, (int32_t)st);
        return;
    }
    if (app->ui.read_kind == (uint8_t)GL_READ_PRECISION) {
        /* the re-read after the spin: combined with the first one in solve_() */
        app->reread_slope_raw = slope_raw;
    } else {
        memset(&app->cur, 0, sizeof(app->cur));
        app->cur.tilt_valid = true;
        app->cur.up = up;
        app->cur.gyro_bias = gyro_bias;
        app->cur.slope_raw = slope_raw;
        app->cur.slope.x = slope_raw.x - app->cal_tilt.flip_bias_x;
        app->cur.slope.y = slope_raw.y - app->cal_tilt.flip_bias_y;
        app->cur.temp_c = app->temp_c;
        grain_read_(app);
    }
    gl_app_post(app, GL_EV_TILT_DONE, 0);
}

/* ======================================================================= */
/* capture                                                                  */
/* ======================================================================= */

static void capture_start_(gl_app_t *app)
{
    gl_status_t st;
    if (app->power.critical && !app->power.vbus) {
        /* the camera rail draws about 90 mA from a very small cell */
        gl_app_post(app, GL_EV_BATT_LOW, 0);
        return;
    }
    app->read_id++;
    st = gl_read_start(&app->read, app->cur.up, GL_APP_LRRL_REPEATS);
    if (st != GL_OK) {
        app->last_error = (uint16_t)st;
        gl_app_log_event(app, (uint16_t)GL_APP_LOGEV_FAULT, (int32_t)st);
        gl_app_post(app, GL_EV_CAPTURE_FAIL, (int32_t)st);
        return;
    }
    app->capture_active = true;
    irq_setup_(app);
}

/* The camera part found the flagstick: range and target. */
static void flag_measured_(gl_app_t *app)
{
    const gl_read_result_t *res = &app->read.result;
    gl_app_read_t *c = &app->cur;
    gl_range_input_t in;

    c->flag_found = true;
    c->manual_range = false;
    c->bearing_rad = res->angles.bearing_rad;
    c->base_elev_rad = res->angles.base_elev_rad;
    c->top_elev_rad = res->angles.top_elev_rad;
    c->top_valid = res->angles.top_valid;
    c->base = res->angles.base;
    c->disparity_px = res->disp.disparity_px;
    c->disparity_sigma_px = res->disp.sigma_px;

    memset(&in, 0, sizeof(in));
    in.f_px = GL_CFG_CAM_F_PX;
    in.baseline_m = GL_CFG_CAM_BASELINE_M;
    in.have_stereo = true;
    in.disparity_px = res->disp.disparity_px;
    in.disparity_sigma_px = res->disp.sigma_px;
    in.cos_bearing = cosf(c->bearing_rad);
    in.have_height = res->angles.top_valid;
    /* For RANGING the lowest visible point counts as the base also when the
     * stick ends at the turf horizon: on a flat green the base is then within
     * (lens height / distance) of it, and a crown hides centimetres of a
     * 1.96 m stick.  The elevation uncertainty is widened instead.  (For the
     * SLOPE use of the base the solver gets the strict classification.) */
    in.base_visible = (res->angles.base != (uint8_t)GL_VIS_BASE_UNKNOWN);
    in.tan_top = tanf(res->angles.top_elev_rad);
    in.tan_base = tanf(res->angles.base_elev_rad);
    in.elev_sigma_rad = ((res->angles.base == (uint8_t)GL_VIS_BASE_VISIBLE)
                             ? GL_APP_ELEV_SIGMA_ROWS
                             : (GL_APP_ELEV_SIGMA_ROWS + 0.5f)) / GL_CFG_CAM_F_PX;
    c->range_valid = (gl_range_fuse(&in, &app->stick_height, &c->range) == GL_OK);
    if (gl_stick_height_learn(&app->stick_height, &in)) {
        uint8_t blob[GL_STICK_HEIGHT_BLOB_LEN];
        gl_stick_height_encode(&app->stick_height, blob);
        (void)gl_app_store_put(app, (uint8_t)GL_STORE_ID_COURSE, blob, sizeof(blob));
    }
    if (c->range_valid) {
        /* the bearing was measured by the LEFT camera, not at the head centre */
        c->target = gl_range_from_ball_at(c->range.range_m, c->bearing_rad,
                                          GL_CFG_CAM_LEFT_X_MM * 0.001f,
                                          GL_CFG_CAM_LEFT_Y_MM * 0.001f);
    } else {
        c->target.distance_m = 0.0f;
        c->target.bearing_rad = c->bearing_rad;
    }
}

static void capture_step_(gl_app_t *app)
{
    const gl_status_t st = gl_read_step(&app->read);
    if (st == GL_ERR_BUSY) {
        return;
    }
    /* finished one way or another: the camera rail is off */
    app->capture_active = false;
    gl_motion_set_strict(&app->motion, false);
    irq_setup_(app);
    if (st == GL_OK) {
        flag_measured_(app);
        gl_app_post(app, GL_EV_CAPTURE_DONE, 0);
    } else if (st == GL_ERR_NO_STICK) {
        app->cur.flag_found = false;
        gl_app_post(app, GL_EV_CAPTURE_NO_STICK, 0);
    } else {
        app->last_error = (uint16_t)st;
        gl_app_log_event(app, (uint16_t)GL_APP_LOGEV_FAULT, (int32_t)st);
        gl_app_post(app, GL_EV_CAPTURE_FAIL, (int32_t)st);
    }
}

/* ======================================================================= */
/* solve, result screen, log                                                */
/* ======================================================================= */

/* The current read as the estimator wants it (device frame = read frame). */
static void build_measurement_(const gl_app_t *app, gl_measurements_t *m)
{
    const gl_app_read_t *c = &app->cur;
    const gl_read_result_t *res = &app->read.result;
    const gl_vec2_t dev = gl_tilt_slope_to_device(c->slope);
    gl_grain_est_t grain;

    gl_solver_measurements_init(m);
    m->tilt_x = dev.x;
    m->tilt_y = dev.y;
    m->tilt_reads = c->precision ? 2u : 1u;
    m->stimp_ft = gl_settings_stimp_ft(&app->settings);
    m->stick_height_est_m = app->stick_height.height_m;
    m->stick_height_rel_sigma =
        (app->stick_height.height_m > 0.0f) ? (app->stick_height.sigma_m / app->stick_height.height_m)
                                            : GL_PROV_STICK_HEIGHT_REL_SIGMA;
    gl_grain_estimate(&app->settings, &app->cal_grain, c->slope, app->grain_valid ? 1u : 0u,
                      app->grain_modulation, app->grain_azimuth_rad, &grain);
    m->grain_kappa = grain.kappa_long;
    m->grain_azimuth_rad = grain.azimuth_rad;
    if (c->flag_found) {
        m->flag_found = true;
        m->flag_bearing_rad = c->bearing_rad;
        /* the reference's disparity is f B / DISTANCE; ours measures depth */
        m->flag_disparity_px = c->disparity_px * cosf(c->bearing_rad);
        m->flag_low_elev_rad = c->base_elev_rad;
        m->flag_base_visible = (c->base == (uint8_t)GL_VIS_BASE_VISIBLE);
        m->flag_top_visible = c->top_valid;
        m->flag_top_elev_rad = c->top_elev_rad;
        m->n_horizon = (res->n_horizon <= GL_SOLVER_MAX_HORIZON) ? res->n_horizon
                                                                  : (uint8_t)GL_SOLVER_MAX_HORIZON;
        for (unsigned i = 0; i < m->n_horizon; i++) {
            m->horizon_az_rad[i] = res->horizon_az_rad[i];
            m->horizon_elev_rad[i] = res->horizon_elev_rad[i];
        }
    } else if (c->manual_range) {
        m->user_distance_m = c->target.distance_m;
    }
}

static void survey_store_(gl_app_t *app)
{
    const gl_app_read_t *c = &app->cur;
    gl_survey_drop_t d;
    memset(&d, 0, sizeof(d));
    d.slope = c->slope;
    d.bearing_rad = c->bearing_rad;
    d.base_elev_rad = c->base_elev_rad;
    if (c->flag_found && c->range_valid) {
        /* distance from the marker centre: stereo head range + its offset */
        d.range_m = c->range.range_m + GL_CFG_CAM_LEFT_Y_MM * 0.001f;
        d.range_sigma_m = c->range.sigma_m;
        d.flags |= (uint8_t)GL_DROP_FLAG_STICK;
    }
    if (c->base == (uint8_t)GL_VIS_BASE_VISIBLE) {
        d.flags |= (uint8_t)GL_DROP_FLAG_BASE_VISIBLE;
    }
    if (c->precision) {
        d.flags |= (uint8_t)GL_DROP_FLAG_PRECISION;
    }
    if (gl_survey_add(&app->survey, &d) == GL_OK) {
        build_measurement_(app, &app->meas[app->survey.count - 1u]);
    }
}

/* Phase-1 confidence figure, 0..1.  A HEURISTIC, not a calibrated
 * probability: the estimator of phase 2 supplies the real one. */
static float confidence_(const gl_app_t *app, bool solved)
{
    const gl_app_read_t *c = &app->cur;
    const gl_vis_quality_t *q = &app->read.result.quality;
    float conf = 1.0f;
    if (!c->flag_found) {
        conf *= 0.4f; /* flag-out fallback */
    } else {
        if (c->range_valid && c->range.range_m > 0.0f) {
            conf *= gl_clampf(1.0f - 4.0f * c->range.sigma_m / c->range.range_m, 0.3f, 1.0f);
            if (!c->range.consistent) {
                conf *= 0.7f;
            }
        } else {
            conf *= 0.5f;
        }
        if (q->sun) {
            conf *= 0.7f;
        }
        if (q->sharpness_match < 0.6f) {
            conf *= 0.7f; /* one window dirty or wet */
        }
        if (q->rows_used_frac < 0.5f) {
            conf *= 0.8f;
        }
    }
    if ((app->cal_tilt.flags & GL_CAL_TILT_FLAG_FACTORY) == 0u) {
        conf *= 0.8f;
    }
    if ((app->cal_tilt.flags & GL_CAL_TILT_FLAG_FLIP) == 0u) {
        conf *= 0.9f; /* never zeroed */
    }
    if (c->precision) {
        conf *= 1.15f;
    }
    if (!solved && conf > 0.5f) {
        conf = 0.5f; /* no putt solution behind the line */
    }
    return gl_clampf(conf, 0.0f, 1.0f);
}

static void compose_view_(gl_app_t *app, bool solved)
{
    const gl_app_read_t *c = &app->cur;
    gl_ui_view_t *v = &app->view;
    float aim, fall;

    v->have_result = true;
    v->solved = solved;
    v->flag_found = c->flag_found;
    v->precision = c->precision;
    if (solved) {
        aim = app->est.aim_azimuth_device_rad;
        fall = app->est.fall_line_azimuth_device_rad;
        v->distance_m = app->est.distance_m;
        v->slope_pct = app->est.slope_pct;
        v->break_cups = app->est.break_cups;
        v->confidence = app->est.confidence;
    } else {
        /* no putt solution: the line points straight at the hole (or along
         * the visor axis when no flag was found) */
        aim = (c->flag_found || c->manual_range) ? c->target.bearing_rad : 0.0f;
        fall = gl_tilt_fall_line_rad(c->slope);
        v->distance_m = c->target.distance_m;
        v->slope_pct = gl_tilt_slope_percent(c->slope);
        v->break_cups = 0.0f;
        v->confidence = confidence_(app, false);
    }
    v->along_pct = 100.0f * gl_tilt_slope_along(c->slope, aim).x;
    /* from the read frame to the marker's present frame */
    v->aim_rad = gl_wrap_pi(aim - c->view_yaw_rad);
    v->fall_line_rad = gl_wrap_pi(fall - c->view_yaw_rad);
    v->ball_az_rad = gl_wrap_pi(-c->view_yaw_rad);
}

static uint8_t pct_(float x)
{
    return (uint8_t)gl_roundi(100.0f * gl_clampf(x, 0.0f, 1.0f));
}

static void log_read_(gl_app_t *app, bool solved)
{
    const gl_app_read_t *c = &app->cur;
    const gl_read_result_t *res = &app->read.result;
    gl_log_read_t r;
    uint8_t buf[GL_LOG_READ_LEN];

    if (!app->storage_ok) {
        return;
    }
    memset(&r, 0, sizeof(r));
    r.rtc_s = gl_hal_rtc_seconds();
    r.read_id = app->read_id;
    r.flags = (uint8_t)((c->flag_found ? GL_LOG_READ_FLAG_STICK_FOUND : 0u) |
                        ((c->flag_found && c->base == (uint8_t)GL_VIS_BASE_VISIBLE)
                             ? GL_LOG_READ_FLAG_BASE_VISIBLE : 0u) |
                        ((c->flag_found && c->top_valid) ? GL_LOG_READ_FLAG_TOP_VISIBLE : 0u) |
                        (c->manual_range ? GL_LOG_READ_FLAG_MANUAL_RANGE : 0u) |
                        (c->precision ? GL_LOG_READ_FLAG_PRECISION : 0u) |
                        ((app->survey.count > 0u) ? GL_LOG_READ_FLAG_SURVEY : 0u) |
                        (app->grain_valid ? GL_LOG_READ_FLAG_GRAIN_VALID : 0u) |
                        ((c->flag_found && res->quality.sun) ? GL_LOG_READ_FLAG_SUN : 0u));
    r.drop_index = app->survey.count;
    r.temp_c_x100 = (int16_t)gl_roundi(gl_clampf(c->temp_c, -300.0f, 300.0f) * 100.0f);
    r.batt_mv = app->power.batt_mv;
    r.slope_x = c->slope.x;
    r.slope_y = c->slope.y;
    r.aim_rad = app->view.aim_rad;
    r.stimp_x2 = app->settings.stimp_x2;
    r.confidence_pct = pct_(app->view.confidence);
    r.solver_status = solved ? app->est.solve_status : (uint8_t)GL_SOLVE_NOT_RUN;
    r.stick_height_m = app->stick_height.height_m;
    if (c->flag_found) {
        r.bearing_rad = c->bearing_rad;
        r.disparity_px = c->disparity_px;
        r.disparity_sigma_px = c->disparity_sigma_px;
        r.base_elev_rad = c->base_elev_rad;
        r.top_elev_rad = c->top_valid ? c->top_elev_rad : 0.0f;
        r.rows_used_pct = pct_(res->quality.rows_used_frac);
        r.line_contrast = (uint8_t)gl_clampi(gl_roundi(res->quality.line_contrast), 0, 255);
        r.sharp_match_pct = pct_(res->quality.sharpness_match);
        r.saturation_pct = pct_(res->quality.sat_fraction);
        r.n_repeats = res->groups_ok;
    }
    if (c->range_valid || c->manual_range) {
        r.range_m = c->manual_range ? c->target.distance_m : c->range.range_m;
        r.range_sigma_m = c->manual_range ? (GL_RANGE_MANUAL_REL_SIGMA * c->target.distance_m)
                                          : c->range.sigma_m;
    }
    if (solved) {
        r.v0_mps = app->est.v0_mps;
        r.aim_offset_m = app->est.break_m;
    }
    gl_log_read_encode(&r, buf);
    if (gl_log_append(&app->log, (uint8_t)GL_LOG_REC_READ, 0, buf, sizeof(buf), NULL) != GL_OK) {
        app->last_error = (uint16_t)GL_ERR_IO;
    }
}

static void solve_(gl_app_t *app, bool precision_reread)
{
    gl_app_read_t *c = &app->cur;
    gl_solver_options_t opt;
    gl_status_t st;
    bool solved;

    if (precision_reread) {
        /* combine the read at the ball with the re-read after the spin */
        gl_precision_t p;
        const float yaw = gl_spin_yaw(&app->motion.spin);
        if (gl_tilt_precision_combine(app->spin_slope_raw, app->reread_slope_raw, yaw,
                                      &app->cal_tilt, &p) == GL_OK) {
            c->slope = p.slope; /* in the frame of the first read */
            c->precision = true;
        }
        c->view_yaw_rad = yaw; /* the marker now faces the other way */
    }
    if (!c->flag_found) {
        /* flag-out fallback: tilt only, along the visor axis, with the
         * dialled distance if there is one */
        const float manual = gl_settings_manual_distance_m(&app->settings);
        c->manual_range = (manual > 0.0f);
        c->target.bearing_rad = 0.0f;
        c->target.distance_m = c->manual_range ? manual : 0.0f;
    }
    build_measurement_(app, &app->meas_cur);
    gl_solver_default_options(&opt);
    opt.past_m = gl_settings_past_m(&app->settings);
    if (app->survey.count >= 2u) {
        st = gl_solver_estimate_survey(app->meas, app->survey.count, 0u, &opt, &app->est);
    } else {
        st = gl_solver_estimate(&app->meas_cur, &opt, &app->est);
    }
    app->solver_status = st;
    if (st != GL_OK && st != GL_ERR_NOT_IMPLEMENTED) {
        app->last_error = (uint16_t)st;
        gl_app_post(app, GL_EV_SOLVE_FAIL, (int32_t)st);
        return;
    }
    /* GL_ERR_NOT_IMPLEMENTED is the phase-1 stub: show the tilt-and-bearing
     * screen ("TILT ONLY"), which is a result, not a failure */
    solved = (st == GL_OK);
    compose_view_(app, solved);
    log_read_(app, solved);
    app->reads_total++;
    gl_app_post(app, GL_EV_SOLVE_DONE, 0);
}

/* ======================================================================= */
/* zeroing: read, turn 180 degrees in place, read (hard flat surface)       */
/* ======================================================================= */

static void zero_start_(gl_app_t *app)
{
    memset(&app->zero, 0, sizeof(app->zero));
    if (app->power.vbus) {
        /* never in the cradle: it takes the marker one way round only */
        gl_app_post(app, GL_EV_CAL_FAIL, (int32_t)GL_ERR_STATE);
        return;
    }
    app->zero.active = true;
    gl_motion_set_strict(&app->motion, false);
    app->redraw = true;
}

static void zero_fail_(gl_app_t *app, gl_status_t st)
{
    app->zero.active = false;
    app->last_error = (uint16_t)st;
    gl_app_post(app, GL_EV_CAL_FAIL, (int32_t)st);
}

static void zero_sample_(gl_app_t *app, unsigned flags, uint32_t dt_ms, uint32_t now)
{
    gl_app_zero_t *z = &app->zero;
    gl_vec2_t slope_raw;
    gl_vec3_t up, gyro_bias;
    gl_status_t st;

    if (z->step >= 3u) {
        return;
    }
    if (z->step >= 1u) {
        gl_rot_int_add(&z->rot, app->motion.gyro_rad_s, (float)dt_ms * 0.001f);
        if (!z->turned && gl_rot_int_angle(&z->rot) > GL_APP_ZERO_MIN_TURN_RAD) {
            z->turned = true;
        }
    }
    if ((flags & GL_MOTION_F_BLOCK) == 0u) {
        return;
    }
    if (z->step == 1u) {
        if (!(z->turned && (flags & GL_MOTION_F_AT_REST) != 0u)) {
            return;
        }
        z->step = 2;
        z->averaging = false;
        app->redraw = true;
    }
    /* steps 0 and 2: a 1 s read once the marker is at rest */
    if (!z->averaging) {
        if ((flags & GL_MOTION_F_AT_REST) != 0u) {
            gl_tilt_avg_reset(&app->motion.avg);
            z->averaging = true;
        }
        return;
    }
    if ((flags & GL_MOTION_F_BLOCK_STILL) == 0u) {
        z->averaging = false; /* disturbed: take the read again */
        return;
    }
    if (app->motion.avg.blocks_still < GL_APP_TILT_BLOCKS) {
        return;
    }
    z->averaging = false;
    st = tilt_measure_(app, &slope_raw, &up, &gyro_bias);
    if (st != GL_OK) {
        zero_fail_(app, st);
        return;
    }
    if (z->step == 0u) {
        z->m1 = slope_raw;
        z->up1 = up;
        gl_rot_int_start(&z->rot, gyro_bias);
        z->turned = false;
        z->step = 1;
        app->redraw = true;
    } else {
        gl_vec2_t bias, surface;
        uint8_t blob[GL_CAL_TILT_BLOB_LEN];
        const float yaw = gl_rot_int_yaw(&z->rot, z->up1);
        st = gl_tilt_flip_solve(z->m1, slope_raw, yaw, &bias, &surface);
        if (st == GL_OK &&
            (fabsf(bias.x) > GL_APP_ZERO_MAX_BIAS || fabsf(bias.y) > GL_APP_ZERO_MAX_BIAS)) {
            st = GL_ERR_RANGE;
        }
        if (st != GL_OK) {
            zero_fail_(app, st); /* turn not near 180 degrees, or implausible */
            return;
        }
        app->cal_tilt.flip_bias_x = bias.x;
        app->cal_tilt.flip_bias_y = bias.y;
        app->cal_tilt.flip_temp_c = app->temp_valid ? app->temp_c : app->cal_tilt.t0_c;
        app->cal_tilt.flip_time_s = gl_hal_rtc_seconds();
        app->cal_tilt.flags |= (uint8_t)GL_CAL_TILT_FLAG_FLIP;
        gl_cal_tilt_encode(&app->cal_tilt, blob);
        st = gl_app_store_put(app, (uint8_t)GL_STORE_ID_CAL_TILT, blob, sizeof(blob));
        if (st != GL_OK && st != GL_ERR_NOT_FOUND) {
            zero_fail_(app, st);
            return;
        }
        gl_app_log_event(app, (uint16_t)GL_APP_LOGEV_ZEROED,
                         (int32_t)gl_roundi(1.0e6f * sqrtf(bias.x * bias.x + bias.y * bias.y)));
        z->step = 3;
        z->saved_at_ms = now;
        app->redraw = true;
    }
}

/* ======================================================================= */
/* factory calibration procedures (USB START_CAL)                           */
/* ======================================================================= */

gl_status_t gl_app_start_cal(gl_app_t *app, uint8_t procedure, uint8_t arg)
{
    switch (procedure) {
    case GL_CALPROC_ZERO:
        /* the zeroing needs a 180-degree turn on a flat surface; the cradle
         * (the only place with USB) holds the marker one way round */
        return GL_ERR_STATE;
    case GL_CALPROC_SIX_FACE:
        if (!app->imu_ok || !app->awake) {
            return GL_ERR_STATE;
        }
        if (arg < 6u) {
            if (app->six.active) {
                return GL_ERR_BUSY; /* the previous face is still being averaged */
            }
            app->six.face = arg;
            app->six.active = true;
            gl_tilt_avg_reset(&app->motion.avg);
            return GL_OK;
        }
        if (arg == 6u) {
            gl_vec3_t offset;
            gl_mat3_t m;
            uint8_t blob[GL_CAL_TILT_BLOB_LEN];
            gl_status_t st;
            if (app->six.done_mask != 0x3Fu) {
                return GL_ERR_STATE;
            }
            st = gl_tilt_six_face_solve(app->six.meas, &offset, &m);
            gl_app_log_event(app, (uint16_t)GL_APP_LOGEV_SIX_FACE, (int32_t)st);
            if (st != GL_OK) {
                return st;
            }
            app->cal_tilt.offset_g[0] = offset.x;
            app->cal_tilt.offset_g[1] = offset.y;
            app->cal_tilt.offset_g[2] = offset.z;
            app->cal_tilt.m = m;
            if (app->temp_valid) {
                app->cal_tilt.t0_c = app->temp_c;
            }
            app->cal_tilt.flags |= (uint8_t)GL_CAL_TILT_FLAG_FACTORY;
            gl_cal_tilt_encode(&app->cal_tilt, blob);
            app->six.done_mask = 0;
            return gl_app_store_put(app, (uint8_t)GL_STORE_ID_CAL_TILT, blob, sizeof(blob));
        }
        return GL_ERR_PARAM;
    case GL_CALPROC_GRAIN_WHITE: {
        uint8_t blob[GL_CAL_GRAIN_BLOB_LEN];
        gl_status_t st = gl_grain_fe_measure(&grain_raw_, GL_GRAIN_MAX_CYCLES);
        if (st == GL_OK) {
            st = gl_grain_white_reference(&grain_raw_, &app->cal_grain);
        }
        gl_app_log_event(app, (uint16_t)GL_APP_LOGEV_GRAIN_WHITE, (int32_t)st);
        if (st != GL_OK) {
            return st;
        }
        gl_cal_grain_encode(&app->cal_grain, blob);
        return gl_app_store_put(app, (uint8_t)GL_STORE_ID_CAL_GRAIN, blob, sizeof(blob));
    }
    case GL_CALPROC_ABORT:
        app->six.active = false;
        return GL_OK;
    default:
        /* GL_CALPROC_GRAIN_FLOOR (needs readings on turf, outside the cradle)
         * and GL_CALPROC_CAM_HORIZON (needs the factory target) are not
         * implemented in phase 1 */
        return GL_ERR_UNSUPPORTED;
    }
}

/* One block of the six-face average. */
static void six_face_block_(gl_app_t *app, unsigned flags)
{
    gl_tilt_mean_t mean;
    if ((flags & GL_MOTION_F_BLOCK_STILL) == 0u) {
        gl_tilt_avg_reset(&app->motion.avg); /* moved: start this face again */
        return;
    }
    if (app->motion.avg.blocks_still < GL_APP_TILT_BLOCKS) {
        return;
    }
    if (gl_tilt_avg_result(&app->motion.avg, &mean) == GL_OK) {
        app->six.meas[app->six.face] = mean.accel_g; /* RAW: the solve finds offset and matrix */
        app->six.done_mask |= (uint8_t)(1u << app->six.face);
    }
    app->six.active = false;
}

/* ======================================================================= */
/* IMU sample pump                                                          */
/* ======================================================================= */

static void imu_sample_(gl_app_t *app, uint32_t now)
{
    gl_imu_raw_t raw;
    unsigned flags;
    uint32_t dt_ms = (uint32_t)(now - app->last_sample_ms);
    const gl_status_t st = gl_imu_read(&app->imu, &raw);

    if (st != GL_OK) {
        app->imu_ok = false; /* reported once */
        fault_(app, st);
        return;
    }
    app->last_sample_ms = now;
    if (dt_ms < 1u) {
        dt_ms = 1u;
    } else if (dt_ms > 100u) {
        dt_ms = 100u; /* the loop was busy (capture start, flash): do not over-integrate */
    }
    flags = gl_motion_sample(&app->motion, &raw, dt_ms, &app->events);
    if (app->tilt_active && (flags & GL_MOTION_F_BLOCK_STILL) != 0u &&
        app->motion.avg.blocks_still >= GL_APP_TILT_BLOCKS) {
        tilt_finish_(app);
    }
    if (app->zero.active) {
        zero_sample_(app, flags, dt_ms, now);
    }
    if (app->six.active && (flags & GL_MOTION_F_BLOCK) != 0u) {
        six_face_block_(app, flags);
    }
    if (app->usb_on) {
        gl_usb_stream_imu(app, &raw);
    }
}

/* ======================================================================= */
/* UI actions                                                               */
/* ======================================================================= */

static void do_actions_(gl_app_t *app, uint32_t a, uint32_t now)
{
    if (a == 0u) {
        return;
    }
    /* things that stop come first, sleep last */
    if ((a & GL_ACT_ABORT_READ) != 0u) {
        abort_read_(app);
    }
    if ((a & GL_ACT_CAL_ABORT) != 0u) {
        app->zero.active = false;
    }
    if ((a & GL_ACT_USB_STOP) != 0u) {
        usb_stop_(app);
    }
    if ((a & GL_ACT_SURVEY_RESET) != 0u) {
        gl_survey_reset(&app->survey);
    }
    if ((a & GL_ACT_NEW_READ) != 0u) {
        app->view.have_result = false;
        gl_motion_spin_end(&app->motion);
    }
    if ((a & GL_ACT_DISPLAY_ON) != 0u) {
        wake_(app, now);
    }
    if ((a & GL_ACT_USB_START) != 0u) {
        usb_start_(app);
    }
    if ((a & GL_ACT_SAVE_SETTINGS) != 0u) {
        (void)gl_app_set_settings(app, &app->ui.edit);
    }
    if ((a & GL_ACT_DIAL_BEGIN) != 0u) {
        int lo = 0, hi = 1; /* the "ZERO" item: NO / YES */
        if (app->ui.item < GL_UI_ITEM_ZERO) {
            gl_settings_item_range((gl_item_t)app->ui.item, &lo, &hi);
        }
        gl_motion_dial_begin(&app->motion, (int)app->ui.dial_value, lo, hi);
    }
    if ((a & GL_ACT_WATCH_STILL) != 0u) {
        gl_motion_watch_still(&app->motion);
    }
    if ((a & GL_ACT_START_TILT) != 0u) {
        tilt_start_(app);
    }
    if ((a & GL_ACT_START_CAPTURE) != 0u) {
        capture_start_(app);
    }
    if ((a & GL_ACT_SURVEY_STORE) != 0u) {
        survey_store_(app);
    }
    if ((a & GL_ACT_START_SOLVE) != 0u) {
        solve_(app, (a & GL_ACT_PRECISION) != 0u);
    }
    if ((a & GL_ACT_ARM_SPIN) != 0u) {
        app->spin_slope_raw = app->cur.slope_raw;
        gl_motion_spin_begin(&app->motion, app->cur.up, app->cur.gyro_bias);
    }
    if ((a & GL_ACT_CAL_ZERO_START) != 0u) {
        zero_start_(app);
    }
    if ((a & GL_ACT_REDRAW) != 0u) {
        app->redraw = true;
    }
    if ((a & GL_ACT_ENTER_SLEEP) != 0u) {
        enter_sleep_(app);
    }
}

static void draw_(gl_app_t *app)
{
    app->redraw = false;
    if (!app->lcd.on) {
        return;
    }
    app->view.battery_pct = app->power.percent;
    app->view.charging = app->power.charging;
    app->view.usb_connected = app->usb_on && gl_hal_usb_connected();
    app->view.cal_step = app->zero.active ? app->zero.step : 0u;
    gl_ui_render(&app->ui, &app->view, &app->gfx);
    if (gl_lcd_update(&app->lcd, &app->gfx, NULL) != GL_OK) {
        app->last_error = (uint16_t)GL_ERR_IO;
    }
}

/* ======================================================================= */
/* init and main loop                                                       */
/* ======================================================================= */

gl_status_t gl_app_init(gl_app_t *app)
{
    gl_status_t first_err = GL_OK, st;
    uint32_t reset;

    memset(app, 0, sizeof(*app));
    st = gl_hal_init();
    if (st != GL_OK) {
        first_err = st;
    }
    reset = gl_hal_reset_reason();
    gl_event_init(&app->events);

    gl_settings_defaults(&app->settings);
    gl_cal_tilt_defaults(&app->cal_tilt);
    gl_cal_cam_defaults(&app->cal_cam[GL_CAM_LEFT], 0);
    gl_cal_cam_defaults(&app->cal_cam[GL_CAM_RIGHT], 1);
    gl_cal_grain_defaults(&app->cal_grain);
    gl_stick_height_reset(&app->stick_height);

    /* drivers: every one first puts its pins into the safe state */
    gl_ov7692_init(&app->cam, NULL); /* camera rail off, camera-facing pins parked */
    gl_lcd_init(&app->lcd, NULL);
    gl_grain_fe_all_off();
    gl_power_init(&app->power);
    gl_gfx_init(&app->gfx);

    st = gl_mx25r_init(&app->flash);
    app->flash_ok = (st == GL_OK);
    if (st != GL_OK && first_err == GL_OK) {
        first_err = st;
    }
    if (app->flash_ok) {
        gl_mx25r_flash_if(&app->flash, &app->flash_if);
        app->storage_ok =
            gl_store_mount(&app->store, &app->flash_if, GL_APP_STORE_BASE, GL_APP_STORE_SECTORS) ==
                GL_OK &&
            gl_log_mount(&app->log, &app->flash_if, GL_APP_LOG_BASE, GL_APP_LOG_SECTORS) == GL_OK;
        if (app->storage_ok) {
            load_store_(app);
        } else if (first_err == GL_OK) {
            first_err = GL_ERR_CORRUPT;
        }
    }
    st = gl_imu_init(&app->imu, NULL);
    app->imu_ok = (st == GL_OK);
    if (st != GL_OK && first_err == GL_OK) {
        first_err = st;
    }

    gl_read_init(&app->read, &app->cam);
    gl_read_set_cal(&app->read, &app->cal_cam[GL_CAM_LEFT], &app->cal_cam[GL_CAM_RIGHT]);
    gl_read_set_strip_hook(&app->read, strip_hook_, app);
    gl_motion_init(&app->motion, GL_IMU_ACCEL_G_PER_LSB_2G, GL_IMU_GYRO_RAD_S_PER_LSB_1000);
    gl_ui_init(&app->ui, &app->settings, gl_hal_tick_ms());
    gl_usb_bind(app);
    app->solver_status = GL_ERR_NOT_IMPLEMENTED;

    gl_app_log_event(app, (uint16_t)GL_APP_LOGEV_BOOT, (int32_t)reset);

    /* asleep: display off, IMU waiting for motion, flash in deep power-down */
    app->awake = true; /* so that enter_sleep_() configures everything once */
    enter_sleep_(app);
    if (first_err != GL_OK) {
        fault_(app, first_err); /* shows the error screen, then sleeps again */
    }
    /* already in the cradle at power-up? */
    gl_power_poll_pins(&app->power);
    if (app->power.vbus) {
        gl_app_post(app, GL_EV_USB_ATTACH, 0);
    }
    return first_err;
}

/* Sleep until the next interrupt source or deadline. */
static void sleep_(gl_app_t *app)
{
    const uint32_t now = gl_hal_tick_ms();
    uint32_t wait = app->awake ? 1000u : GL_APP_SLEEP_HOUSEKEEP_MS;
    uint32_t left;
    gl_sleep_mode_t mode = GL_SLEEP_STOP;

    if (gl_event_count(&app->events) != 0u || app->redraw || app->reboot_pending) {
        return; /* more to do right away */
    }
    left = gl_ui_time_left_ms(&app->ui, now);
    if (left != 0u && left < wait) {
        wait = left;
    }
    if (app->awake) {
        const int32_t batt = (int32_t)(app->next_batt_ms - now);
        if (batt < (int32_t)wait && !app->capture_active && !app->tilt_active) {
            wait = (batt > 0) ? (uint32_t)batt : 1u;
        }
        if (app->zero.active && app->zero.step >= 3u) {
            const int32_t z = (int32_t)(app->zero.saved_at_ms + GL_APP_ZERO_SAVED_MS - now);
            if (z < (int32_t)wait) {
                wait = (z > 0) ? (uint32_t)z : 1u;
            }
        }
        if (app->capture_active && wait > 5u) {
            wait = 5u; /* poll the capture even if its interrupt is lost */
        }
        if (app->usb_on && app->stream_mask != 0u) {
            const int32_t s = (int32_t)(app->stream_next_ms - now);
            if (s < (int32_t)wait) {
                wait = (s > 0) ? (uint32_t)s : 1u;
            }
        }
        if (app->usb_on && app->log_erasing) {
            wait = 1u;
        }
    }
    /* Stop mode needs: no USB (48 MHz clock), no camera activity (DCMI,
     * XVCLK), and an EXTCOMIN output that keeps running in Stop 2 while the
     * display is on (PROVISIONAL) */
    if (app->usb_on || app->capture_active || gl_read_busy(&app->read) || app->cam.powered ||
        (app->lcd.on && GL_PROV_LPTIM_PWM_RUNS_IN_STOP2 == 0)) {
        mode = GL_SLEEP_IDLE;
    }
    gl_hal_wake_timer_start(wait);
    (void)gl_hal_sleep(mode);
}

void gl_app_run_once(gl_app_t *app)
{
    const uint32_t irq = gl_hal_irq_take();
    uint32_t now = gl_hal_tick_ms();
    gl_event_t e;

    app->loops++;
    gl_hal_watchdog_kick();

    /* 1. interrupt sources -> work */
    if ((irq & (GL_IRQ_VBUS_CHANGE | GL_IRQ_CHG_STAT)) != 0u) {
        vbus_service_(app);
    }
    if (!app->awake) {
        if ((irq & GL_IRQ_IMU_INT1) != 0u) {
            bool woke = false;
            if (app->imu_ok) {
                (void)gl_imu_wake_source(&app->imu, &woke); /* reading clears the latch */
            }
            if ((uint32_t)(now - app->sleep_since_ms) >= GL_APP_WAKE_HOLDOFF_MS) {
                gl_app_post(app, GL_EV_MOTION, 0);
            }
        }
    } else {
        if (app->imu_ok && (irq & GL_IRQ_IMU_INT2) != 0u) {
            imu_sample_(app, now);
        }
        if (app->capture_active) {
            capture_step_(app);
        }
        /* 2. timers */
        battery_service_(app, now);
        if (app->zero.active && app->zero.step >= 3u &&
            (uint32_t)(now - app->zero.saved_at_ms) >= GL_APP_ZERO_SAVED_MS) {
            app->zero.active = false;
            gl_app_post(app, GL_EV_CAL_DONE, 0);
        }
    }
    if (app->usb_on) {
        gl_usb_service(app, now);
    }
    /* the work above can take real time (a capture start waits for the
     * sensor, a raw strip takes half a second to log): the UI is given the
     * time as it is NOW, never an older one than it has already seen */
    now = gl_hal_tick_ms();
    do_actions_(app, gl_ui_tick(&app->ui, now), now);

    /* 3. events -> transition table -> actions */
    while (gl_event_get(&app->events, &e)) {
        const uint32_t a = gl_ui_dispatch(&app->ui, (gl_ui_event_t)e.type, e.arg, now);
        do_actions_(app, a, now);
        if (app->ui.state != (uint8_t)GL_UI_SETTINGS_DIAL) {
            gl_motion_dial_end(&app->motion);
        }
    }
    /* 4. screen */
    if (app->redraw) {
        draw_(app);
    }
    /* 5. sleep */
    sleep_(app);
}
