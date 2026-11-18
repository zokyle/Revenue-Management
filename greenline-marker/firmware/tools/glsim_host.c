/*
 * glsim_host.c - the HOST SIMULATOR build of the firmware as a program a PC
 * tool can talk to: the whole firmware (app/, core/, drivers/) on the
 * simulated board (hal/host), its USB CDC port on stdin / stdout.
 *
 *     build/host/glsim            (`make glsim`; used by tools/glctl --sim
 *                                  and by `make tooltest`)
 *
 * It lets tools/glctl run EVERY protocol command against the real firmware
 * code without hardware.  It is a test instrument, not a product: the
 * cameras see the synthetic scenes of the test suite, the IMU feels what the
 * "world" commands below say, and every current is the supply MODEL's.
 *
 * WIRE FORMAT (both directions): frames of  kind (1)  length (2, LE)  data.
 *   'U'  bytes of the USB CDC stream.  In: sent to the device, which then
 *        runs for 30 ms of simulated time.  Out: what the device sent.
 *   'T'  in only: data = milliseconds (4, LE): just run (talking: the
 *        device is NOT sent anything, so the cradle may fall asleep).
 *   'W'  a world command (text) / its answer (one line of JSON).
 * EVERY input frame is answered by exactly one output frame of kind 'U'
 * (possibly empty) or 'W': the client writes one, reads one.
 *
 * WORLD COMMANDS
 *   dock | undock            the marker into / out of the cradle (VBUS, host port)
 *   doubletap                the double-tap gesture (twice on a result: a Survey;
 *                            the next "place" is then its next placement)
 *   place                    pick the marker up and put it down; runs until a
 *                            result, an error or 12 s; answers the state and,
 *                            for a result, the estimator's inputs and outputs
 *                            as the firmware holds them (for cross-checks of
 *                            the log decoder)
 *   zero <turn_deg>          as place, then - when the armed zeroing has taken
 *                            its first read - turn the marker and wait
 *   run <ms>                 let time pass
 *   set <name> <value>       slope_x slope_y dist bearing height stick
 *                            temp cell_temp bias_x bias_y right_blind face scene
 *                            (scene: 0 green, 1 dark with a leak, 2 gate-2
 *                            bars, 3 ramp) upper lower
 *   state                    UI state, power, counters
 *   reset                    MCU reset (the flash is kept)
 *   quit
 */
#include <stdarg.h>
#include <stdio.h>

#include "gl_e2e_world.h"

#include "gl_pins.h"

static uint32_t now_ms_(void)
{
    return (uint32_t)(gl_sim_now_us() / 1000u);
}

/* ---- the cameras' scenes --------------------------------------------------------- */
static int scene_mode_;
static float bar_upper_ = 180.0f, bar_lower_ = 180.0f;

static void scene_(void *ctx, gl_cam_id_t cam, uint16_t x0, uint16_t y0, uint16_t w, uint16_t h,
                   uint32_t frame_no, uint64_t t_us, uint8_t *luma)
{
    const double f = (double)GL_CFG_CAM_F_PX;
    const int row_up = (int)floor(239.5 - f * tan(13.0 * PI_D / 180.0) + 0.5);
    const int row_lo = (int)floor(239.5 + f * tan(13.0 * PI_D / 180.0) + 0.5);
    if (scene_mode_ == 0) {
        scene_fn_(ctx, cam, x0, y0, w, h, frame_no, t_us, luma);
        return;
    }
    for (unsigned r = 0; r < h; r++) {
        for (unsigned c = 0; c < w; c++) {
            const int sx = (int)x0 + (int)c, sy = (int)y0 + (int)r;
            uint8_t v;
            if (scene_mode_ == 1) {
                v = (cam == GL_CAM_LEFT && sx >= 600 && sx < 612 && sy >= 200 && sy < 206) ? 90u : 3u;
            } else if (scene_mode_ == 2) {
                v = 20u;
                if (abs(sy - row_up) <= 6) {
                    v = (uint8_t)bar_upper_;
                } else if (abs(sy - row_lo) <= 6) {
                    v = (uint8_t)bar_lower_;
                }
            } else {
                v = (uint8_t)((sx + 3 * sy + ((cam == GL_CAM_RIGHT) ? 101 : 0)) & 0xFF);
            }
            luma[r * w + c] = v;
        }
    }
}

/* ---- output ------------------------------------------------------------------------ */
static void out_frame_(char kind, const uint8_t *data, size_t n)
{
    uint8_t hdr[3];
    hdr[0] = (uint8_t)kind;
    hdr[1] = (uint8_t)(n & 0xFFu);
    hdr[2] = (uint8_t)(n >> 8);
    fwrite(hdr, 1, 3, stdout);
    if (n != 0u) {
        fwrite(data, 1, n, stdout);
    }
    fflush(stdout);
}

static char json_[32768];
static size_t json_len_;

static void j_(const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    if (json_len_ < sizeof(json_)) {
        const int n = vsnprintf(&json_[json_len_], sizeof(json_) - json_len_, fmt, ap);
        if (n > 0) {
            json_len_ += (size_t)n;
            if (json_len_ > sizeof(json_)) {
                json_len_ = sizeof(json_);
            }
        }
    }
    va_end(ap);
}

static void j_num_(const char *key, double v, bool last)
{
    if (isfinite(v)) {
        j_("\"%s\": %.9g%s", key, v, last ? "" : ", ");
    } else {
        j_("\"%s\": null%s", key, last ? "" : ", ");
    }
}

static void j_meas_(const gl_measurements_t *m)
{
    j_("{");
    j_num_("f_px", (double)m->f_px, false);
    j_num_("baseline", (double)m->baseline_m, false);
    j_num_("h_cam", (double)m->h_cam_m, false);
    j_("\"tilt\": [%.9g, %.9g], \"tilt_reads\": %u, \"flag_found\": %s, ", (double)m->tilt_x,
       (double)m->tilt_y, m->tilt_reads, m->flag_found ? "true" : "false");
    j_num_("flag_bearing", (double)m->flag_bearing_rad, false);
    j_num_("flag_disparity", (double)m->flag_disparity_px, false);
    j_num_("flag_low_elev", (double)m->flag_low_elev_rad, false);
    j_("\"flag_base_visible\": %s, \"flag_top_visible\": %s, ", m->flag_base_visible ? "true" : "false",
       m->flag_top_visible ? "true" : "false");
    j_num_("flag_top_elev", (double)m->flag_top_elev_rad, false);
    j_num_("stick_height_est", (double)m->stick_height_est_m, false);
    j_num_("stick_height_rel_sigma", (double)m->stick_height_rel_sigma, false);
    for (int which = 0; which < 2; which++) {
        j_("\"%s\": [", (which == 0) ? "horizon_az" : "horizon_elev");
        for (unsigned i = 0; i < m->n_horizon; i++) {
            const double v = (double)((which == 0) ? m->horizon_az_rad[i] : m->horizon_elev_rad[i]);
            if (isfinite(v)) {
                j_("%s%.9g", (i > 0u) ? ", " : "", v);
            } else {
                j_("%snull", (i > 0u) ? ", " : "");
            }
        }
        j_("], ");
    }
    j_num_("grain_kappa", (double)m->grain_kappa, false);
    j_num_("grain_azimuth", (double)m->grain_azimuth_rad, false);
    j_num_("stimp_ft", (double)m->stimp_ft, false);
    j_num_("user_distance", (double)m->user_distance_m, true);
    j_("}");
}

static void j_state_(void)
{
    j_("\"state\": \"%s\", \"t_ms\": %u, \"awake\": %s, \"vbus\": %s, \"read_id\": %u, "
       "\"reads_total\": %u, \"rail_cycles\": %u, \"violations\": %u, \"halted\": %s, "
       "\"zero_state\": %u, \"sleep_running\": %s, \"load_ua\": %.3f, \"reboots\": %u, "
       "\"last_reboot\": %u, \"black_pixels\": %u, \"flag_found\": %s",
       gl_ui_state_name((gl_ui_state_t)app.ui.state), now_ms_(), app.awake ? "true" : "false",
       app.power.vbus ? "true" : "false", app.read_id, (unsigned)app.reads_total,
       (unsigned)gl_sim_stats()->cam_rail_cycles, gl_sim_violation_total(),
       app.halted ? "true" : "false", app.fac.zero.state, app.fac.sleep_running ? "true" : "false",
       gl_sim_load_ua(), (unsigned)gl_sim_stats()->reboots, gl_sim_stats()->last_reboot,
       gl_gfx_count_black(&app.gfx), app.cur.flag_found ? "true" : "false");
}

/* The result on the screen, as the firmware holds it. */
static void j_result_(void)
{
    const gl_estimate_t *e = &app.est;
    j_(", \"solver_ret\": %d, \"n_drops\": %u, \"ball_index\": %u, \"drops\": [", (int)app.solver_status,
       app.solve_drops, app.solve_ball);
    for (unsigned i = 0; i < app.solve_drops; i++) {
        j_("%s", (i > 0u) ? ", " : "");
        j_meas_(app.solve_survey ? &app.solve_meas[i] : &app.meas_cur);
    }
    j_("], \"estimate\": {");
    j_num_("phi", (double)e->phi_rad, false);
    j_num_("aim_azimuth_device", (double)e->aim_azimuth_device_rad, false);
    j_num_("v0", (double)e->v0_mps, false);
    j_num_("plays_like", (double)e->plays_like_m, false);
    j_num_("break_cups", (double)e->break_cups, false);
    j_num_("distance", (double)e->distance_m, false);
    j_num_("bearing", (double)e->bearing_rad, false);
    j_num_("slope_pct", (double)e->slope_pct, false);
    j_num_("dz_hole", (double)e->dz_hole_m, false);
    j_num_("confidence", (double)e->confidence, false);
    j_("\"base_hidden\": %d, \"flag_missing\": %d, \"range_missing\": %d, \"poor_horizon\": %d, "
       "\"fit_converged\": %d, \"aim_source\": %u, \"solve_status\": %u}",
       e->base_hidden, e->flag_missing, e->range_missing, e->poor_horizon, e->fit_converged,
       e->aim_source, e->solve_status);
    /* the options of the call, as the application handed them over (the
     * self-test compares the log decoder's options with these, field by
     * field: phase-3 review, seed S15) */
    j_(", \"options\": {");
    j_num_("past", (double)app.solve_opt.past_m, false);
    j_num_("tol_miss", (double)app.solve_opt.tol_miss_m, false);
    j_num_("tol_pace", (double)app.solve_opt.tol_pace_m, false);
    j_num_("lm_tol", (double)app.solve_opt.lm_tol, false);
    j_num_("near_miss", (double)app.solve_opt.near_miss_m, false);
    j_("\"max_steps\": %u, \"max_rolls\": %u, \"lm_max_iter\": %u, \"method\": %u, "
       "\"use_grain\": %s}",
       (unsigned)app.solve_opt.max_steps, (unsigned)app.solve_opt.max_rolls,
       (unsigned)app.solve_opt.lm_max_iter, (unsigned)app.solve_opt.method,
       app.solve_opt.use_grain ? "true" : "false");
}

/* ---- the world ---------------------------------------------------------------------- */
static float bias_[3];

/* the marker clamped in the six-face fixture: gravity along one axis; an
 * IMU with an offset and a scale error per axis */
static int face_;
static void face_imu_(void *ctx, uint64_t t_us, float a[3], float g[3])
{
    static const float up[6][3] = { { 1, 0, 0 }, { -1, 0, 0 }, { 0, 1, 0 },
                                    { 0, -1, 0 }, { 0, 0, 1 }, { 0, 0, -1 } };
    (void)ctx;
    (void)t_us;
    a[0] = 1.004f * up[face_][0] + 0.012f;
    a[1] = 0.997f * up[face_][1] - 0.007f;
    a[2] = 1.002f * up[face_][2] + 0.020f;
    g[0] = g[1] = g[2] = 0.0f;
}

static void apply_bias_(void)
{
    static const float gyro_bias[3] = { 0.004f, -0.002f, 0.001f };
    gl_sim_imu_set_errors(0.0008f, 0.002f, bias_, gyro_bias);
}

static void dock_(bool in)
{
    gl_sim_set_input(GL_PIN_VBUS_SENSE, in);
    gl_sim_usb_host_open(in);
    run_until_ms_(now_ms_() + (in ? 500u : 100u));
}

static void place_(void)
{
    const uint32_t t0 = now_ms_();
    W.turn_len_s = 0.0;
    W.t_pick_s = (double)t0 / 1000.0 + 0.5;
    W.t_place_s = W.t_pick_s + 0.6;
    project_scene_();
    while (now_ms_() < t0 + 12000u) {
        run_until_ms_(now_ms_() + 5u);
        if ((now_ms_() > t0 + 1200u) &&
            (app.ui.state == (uint8_t)GL_UI_SHOW_RESULT || app.ui.state == (uint8_t)GL_UI_TOO_HOT ||
             app.ui.state == (uint8_t)GL_UI_ERROR || app.ui.state == (uint8_t)GL_UI_SETTINGS_DIAL ||
             app.ui.state == (uint8_t)GL_UI_CAL_ZERO)) {
            break;
        }
    }
    run_until_ms_(now_ms_() + 30u);
}

static void zero_(double turn_deg)
{
    double t;
    place_();
    if (app.ui.state != (uint8_t)GL_UI_CAL_ZERO) {
        return;
    }
    t = (double)now_ms_() / 1000.0;
    while (app.zero.active && app.zero.step == 0u && (double)now_ms_() / 1000.0 < t + 5.0) {
        run_until_ms_(now_ms_() + 10u);
    }
    t = (double)now_ms_() / 1000.0;
    W.turn_at_s = t + 0.4;
    W.turn_len_s = 1.5;
    W.turn_rad = turn_deg * PI_D / 180.0;
    while (app.ui.state == (uint8_t)GL_UI_CAL_ZERO && (double)now_ms_() / 1000.0 < t + 10.0) {
        run_until_ms_(now_ms_() + 10u);
    }
}

static bool set_(const char *name, double v)
{
    if (strcmp(name, "slope_x") == 0) {
        W.slope_x = v;
    } else if (strcmp(name, "slope_y") == 0) {
        W.slope_y = v;
    } else if (strcmp(name, "dist") == 0) {
        W.dist_m = v;
    } else if (strcmp(name, "bearing") == 0) {
        W.bearing_rad = v;
    } else if (strcmp(name, "height") == 0) {
        W.height_m = v;
    } else if (strcmp(name, "stick") == 0) {
        W.stick = (v != 0.0);
    } else if (strcmp(name, "temp") == 0) {
        gl_sim_imu_set_temperature((float)v);
        gl_sim_set_mcu_temperature((float)v);
        gl_sim_set_cell_temperature((float)v);
    } else if (strcmp(name, "cell_temp") == 0) {
        gl_sim_set_cell_temperature((float)v);
    } else if (strcmp(name, "bias_x") == 0) {
        bias_[0] = (float)v;
        apply_bias_();
    } else if (strcmp(name, "bias_y") == 0) {
        bias_[1] = (float)v;
        apply_bias_();
    } else if (strcmp(name, "right_blind") == 0) {
        W.right_blind = (v != 0.0);
    } else if (strcmp(name, "face") == 0) {
        /* six-face fixture: face 0..5 up (+x -x +y -y +z -z); -1: back on the green */
        if (v < 0.0) {
            gl_sim_imu_set_motion(imu_fn_, NULL);
        } else if (v <= 5.0) {
            face_ = (int)v;
            gl_sim_imu_set_motion(face_imu_, NULL);
        } else {
            return false;
        }
    } else if (strcmp(name, "scene") == 0) {
        scene_mode_ = (int)v;
    } else if (strcmp(name, "upper") == 0) {
        bar_upper_ = (float)v;
    } else if (strcmp(name, "lower") == 0) {
        bar_lower_ = (float)v;
    } else {
        return false;
    }
    project_scene_();
    return true;
}

static void world_(char *cmd)
{
    char name[32];
    double v = 0.0;
    bool ok = true, result = false;
    json_len_ = 0;
    if (strcmp(cmd, "dock") == 0) {
        dock_(true);
    } else if (strcmp(cmd, "undock") == 0) {
        dock_(false);
    } else if (strcmp(cmd, "place") == 0) {
        place_();
        result = (app.ui.state == (uint8_t)GL_UI_SHOW_RESULT);
    } else if (strcmp(cmd, "doubletap") == 0) {
        /* the gesture as the gesture detector reports it (the end-to-end
         * tests post it the same way) */
        gl_app_post(&app, GL_EV_DOUBLE_TAP, 0);
        run_until_ms_(now_ms_() + 150u);
    } else if (sscanf(cmd, "zero %lf", &v) == 1) {
        zero_(v);
    } else if (sscanf(cmd, "run %lf", &v) == 1 && v >= 0.0 && v <= 4.0e6) {
        run_until_ms_(now_ms_() + (uint32_t)v);
    } else if (sscanf(cmd, "set %31s %lf", name, &v) == 2) {
        ok = set_(name, v);
    } else if (strcmp(cmd, "state") == 0) {
        /* nothing to do */
    } else if (strcmp(cmd, "reset") == 0) {
        gl_sim_mcu_reset(GL_RESET_SOFTWARE);
        (void)gl_app_init(&app);
        run_until_ms_(now_ms_() + 200u);
    } else {
        ok = false;
    }
    j_("{\"ok\": %s, ", ok ? "true" : "false");
    j_state_();
    if (result) {
        j_result_();
    }
    j_("}");
    out_frame_('W', (const uint8_t *)json_, json_len_);
}

int main(void)
{
    static uint8_t in[70000];
    static uint8_t out[70000];

    world_defaults_();
    W.t_pick_s = 1.0e9;
    W.t_place_s = 1.0e9;
    board_up_(true);
    gl_sim_cam_set_scene(scene_, NULL);
    apply_bias_();
    gl_sim_set_rtc(1795000000u);
    (void)gl_app_init(&app);
    watch_reset_();
    run_until_ms_(200u);

    for (;;) {
        uint8_t hdr[3];
        size_t n, got;
        if (fread(hdr, 1, 3, stdin) != 3u) {
            break;
        }
        n = (size_t)hdr[1] | ((size_t)hdr[2] << 8);
        if (n != 0u && fread(in, 1, n, stdin) != n) {
            break;
        }
        if (hdr[0] == (uint8_t)'U' || hdr[0] == (uint8_t)'T') {
            uint32_t ms = 30u;
            if (hdr[0] == (uint8_t)'U') {
                gl_sim_usb_host_send(in, n);
            } else if (n == 4u) {
                ms = gl_get_u32(in);
            }
            run_until_ms_(now_ms_() + ms);
            got = gl_sim_usb_host_recv(out, sizeof(out) - 1u);
            out_frame_('U', out, (got > 65535u) ? 65535u : got);
        } else if (hdr[0] == (uint8_t)'W') {
            in[n] = 0;
            if (strcmp((const char *)in, "quit") == 0) {
                json_len_ = 0;
                j_("{\"ok\": true, \"violations\": %u}", gl_sim_violation_total());
                out_frame_('W', (const uint8_t *)json_, json_len_);
                break;
            }
            world_((char *)in);
        } else {
            break; /* not this program's protocol */
        }
    }
    return 0;
}
