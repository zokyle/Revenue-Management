/*
 * gl_e2e_world.h - the world outside the marker, for the end-to-end tests
 * (tests/test_e2e.c, tests/test_e2e_faults.c): the green and the flagstick
 * the cameras see, how the marker is handled (what the IMU feels), the
 * board power-on, helpers that run the main loop and watch it, the
 * independent replay of the camera rail rule and a USB host.
 *
 * Everything is static (one copy per test executable); functions are
 * static inline so that a test file need not use all of them.
 */
#ifndef GL_E2E_WORLD_H
#define GL_E2E_WORLD_H

#include <stdlib.h>

#include "gl_test.h"

#include "gl_app.h"
#include "gl_config.h"
#include "gl_crc.h"
#include "gl_provisional.h"
#include "gl_sim.h"
#include "gl_synth.h"

static gl_app_t app;

/* ======================================================================= */
/* the world outside the marker                                             */
/* ======================================================================= */

#define PI_D 3.14159265358979323846

typedef struct {
    /* the green: a plane; the marker lies in it.  Slope = uphill gradient in
     * the marker frame the marker had at t = 0 ("world") */
    double slope_x, slope_y;
    /* the flagstick */
    bool stick;
    double dist_m;          /* from the marker centre, in the plane of the green */
    double bearing_rad;     /* CCW from marker forward */
    double height_m;        /* visible height */
    double sway_amp_px;     /* the stick sways in the wind: image motion amplitude ... */
    double sway_hz;         /* ... and frequency */
    double drift_px_per_s;  /* steady image motion of the stick from drift_t0_s on */
    double drift_t0_s;
    double drift_turn_s;    /* > 0: the drift reverses every this many seconds (triangle wave) */
    /* camera models the scene is rendered through (the truth) */
    gl_cam_model_t cam[2];
    float ub[2], vb[2], ut[2], vt[2];
    float horizon_row[2];
    uint32_t frames_rendered;
    /* copies of the first stick strip each camera delivered (raw-log test) */
    bool keep_first_strips;
    bool have_first[2];
    uint16_t first_x0[2];
    /* how the marker is handled: wobble between t_pick and t_place, then at
     * rest; optionally a jolt, optionally a turn about the vertical */
    double t_pick_s, t_place_s;
    double jolt_at_s, jolt_len_s;
    double turn_at_s, turn_len_s, turn_rad;
} world_t;

static world_t W;
static uint8_t first_strip_[2][96 * 480];

static inline gl_vec3_t up_of_(double sx, double sy)
{
    const double n = sqrt(sx * sx + sy * sy + 1.0);
    gl_vec3_t u = { (float)(sx / n), (float)(sy / n), (float)(1.0 / n) };
    return u;
}

/* Heading of the marker (rad, CCW) relative to its heading at t = 0. */
static inline double heading_(double t)
{
    double f;
    if (W.turn_len_s <= 0.0 || t <= W.turn_at_s) {
        return 0.0;
    }
    if (t >= W.turn_at_s + W.turn_len_s) {
        return W.turn_rad;
    }
    f = (t - W.turn_at_s) / W.turn_len_s;
    return W.turn_rad * 0.5 * (1.0 - cos(PI_D * f)); /* smooth start and stop */
}

static inline double heading_rate_(double t)
{
    double f;
    if (W.turn_len_s <= 0.0 || t <= W.turn_at_s || t >= W.turn_at_s + W.turn_len_s) {
        return 0.0;
    }
    f = (t - W.turn_at_s) / W.turn_len_s;
    return W.turn_rad * 0.5 * PI_D / W.turn_len_s * sin(PI_D * f);
}

/* What the IMU physically experiences, marker axes. */
static inline void imu_fn_(void *ctx, uint64_t t_us, float a[3], float g[3])
{
    const double t = (double)t_us * 1e-6;
    const double psi = heading_(t);
    /* the slope vector seen from the turned marker: R(-psi) c */
    const double cx = cos(psi) * W.slope_x + sin(psi) * W.slope_y;
    const double cy = -sin(psi) * W.slope_x + cos(psi) * W.slope_y;
    const gl_vec3_t u = up_of_(cx, cy);
    const double rate = heading_rate_(t);
    (void)ctx;
    a[0] = u.x;
    a[1] = u.y;
    a[2] = u.z;
    /* turning about the vertical: angular velocity = rate * up */
    g[0] = (float)rate * u.x;
    g[1] = (float)rate * u.y;
    g[2] = (float)rate * u.z;
    if (t >= W.t_pick_s && t < W.t_place_s) {
        /* in the hand: tilted and wobbling */
        const double w = 2.0 * PI_D * 3.1 * (t - W.t_pick_s);
        a[0] += (float)(0.35 * sin(w));
        a[1] += (float)(0.25 * cos(1.7 * w));
        a[2] += (float)(0.20 * sin(2.3 * w));
        g[0] += (float)(1.5 * cos(w));
        g[1] += (float)(1.0 * sin(1.3 * w));
    }
    if (W.jolt_len_s > 0.0 && t >= W.jolt_at_s && t < W.jolt_at_s + W.jolt_len_s) {
        const double w = 2.0 * PI_D * 9.0 * (t - W.jolt_at_s);
        a[0] += (float)(0.15 * sin(w));
        a[2] += (float)(0.10 * cos(w));
        g[1] += (float)(0.8 * sin(w));
    }
}

static inline void project_scene_(void)
{
    const gl_vec3_t u = up_of_(W.slope_x, W.slope_y);
    /* base of the stick on the green (z = 0 of the marker frame), top along
     * gravity-up */
    const gl_vec3_t base = { (float)(-W.dist_m * sin(W.bearing_rad)),
                             (float)(W.dist_m * cos(W.bearing_rad)), 0.0f };
    const gl_vec3_t top = { base.x + (float)W.height_m * u.x, base.y + (float)W.height_m * u.y,
                            base.z + (float)W.height_m * u.z };
    for (int c = 0; c < 2; c++) {
        (void)gl_cam_point_to_pixel(&W.cam[c], base, &W.ub[c], &W.vb[c]);
        (void)gl_cam_point_to_pixel(&W.cam[c], top, &W.ut[c], &W.vt[c]);
        W.horizon_row[c] = gl_cam_base_plane_row(&W.cam[c], 319.5f);
    }
}

/* What a camera sees: synthetic strip of the requested window. */
static inline void scene_fn_(void *ctx, gl_cam_id_t cam, uint16_t x0, uint16_t y0, uint16_t w, uint16_t h,
                      uint32_t frame_no, uint64_t t_us, uint8_t *luma)
{
    gl_synth_scene_t s;
    (void)ctx;
    gl_synth_defaults(&s, w, h, x0, y0);
    s.horizon_row = W.horizon_row[cam];
    s.noise_sigma = 3.0f; /* stick 60 grey above the background: SNR 20 */
    s.noise_seed = 77u + 1000003u * (uint32_t)cam + 7919u * frame_no + (uint32_t)(t_us / 1000u);
    if (W.stick) {
        s.stick_present = true;
        s.stick_width_px = (float)(0.015 / W.dist_m * 657.0);
        s.stick_level = 170.0f;
        s.stick_x = W.ub[cam] +
                    (float)(W.sway_amp_px * sin(2.0 * PI_D * W.sway_hz * (double)t_us * 1e-6));
        if (W.drift_px_per_s != 0.0 && (double)t_us * 1e-6 > W.drift_t0_s) {
            double dt = (double)t_us * 1e-6 - W.drift_t0_s;
            if (W.drift_turn_s > 0.0) {
                /* out for one leg, back for the next: the speed stays, the
                 * stick stays in the strip however long the read takes */
                const double leg = fmod(dt, 2.0 * W.drift_turn_s);
                dt = (leg < W.drift_turn_s) ? leg : (2.0 * W.drift_turn_s - leg);
            }
            s.stick_x += (float)(W.drift_px_per_s * dt);
        }
        s.stick_ref_row = W.vb[cam];
        s.stick_slant = (W.ub[cam] - W.ut[cam]) / (W.vb[cam] - W.vt[cam]);
        s.stick_bottom_row = W.vb[cam];
        s.stick_top_row = W.vt[cam];
    }
    gl_synth_render(&s, luma);
    W.frames_rendered++;
    if (W.keep_first_strips && w == 96u && !W.have_first[cam]) {
        memcpy(first_strip_[cam], luma, sizeof(first_strip_[cam]));
        W.have_first[cam] = true;
        W.first_x0[cam] = x0;
    }
}

static inline void world_defaults_(void)
{
    gl_cal_cam_t cl, cr;
    memset(&W, 0, sizeof(W));
    W.slope_x = 0.012;
    W.slope_y = -0.020;
    W.stick = true;
    W.dist_m = 6.0;
    W.bearing_rad = 0.05;
    W.height_m = 1.96;
    W.sway_amp_px = 0.0;
    W.sway_hz = 1.5;
    W.t_pick_s = 1.0;
    W.t_place_s = 1.6;
    gl_cal_cam_defaults(&cl, 0);
    gl_cal_cam_defaults(&cr, 1);
    gl_cam_model_init(&W.cam[0], &cl);
    gl_cam_model_init(&W.cam[1], &cr);
    project_scene_();
}

/* Power-on of the simulated board with the world attached. */
static inline void board_up_(bool erase_flash)
{
    static const float gyro_bias[3] = { 0.004f, -0.002f, 0.001f };
    gl_sim_reset(erase_flash);
    gl_sim_imu_set_motion(imu_fn_, NULL);
    gl_sim_imu_set_errors(0.0008f, 0.002f, NULL, gyro_bias);
    gl_sim_imu_set_temperature(22.0f);
    gl_sim_cam_set_scene(scene_fn_, NULL);
    gl_sim_cam_set_phase_us(GL_CAM_RIGHT, 9000); /* the two sensors are not synchronised */
    gl_sim_set_vbat_mv(3900);
}

/* ---- running the main loop and watching it -------------------------------- */

#define MAX_SEEN 64
static struct {
    uint8_t state[MAX_SEEN];
    uint32_t t_ms[MAX_SEEN];
    unsigned n;
    unsigned rail_outside_capture; /* loop iterations that ended with the rail on outside CAPTURE */
    unsigned stop_violations_seen;
} seen;

static inline void watch_reset_(void)
{
    memset(&seen, 0, sizeof(seen));
    seen.state[0] = app.ui.state;
    seen.n = 1;
}

static inline void run_until_ms_(uint32_t t_ms)
{
    while (gl_sim_now_us() < (uint64_t)t_ms * 1000u) {
        gl_app_run_once(&app);
        if (seen.n < MAX_SEEN && app.ui.state != seen.state[seen.n - 1u]) {
            seen.state[seen.n] = app.ui.state;
            /* the UI's own time stamp of the transition: one loop iteration
             * ends with a sleep, which can be long (16 s when asleep) */
            seen.t_ms[seen.n] = app.ui.state_since_ms;
            seen.n++;
        }
        if (gl_sim_cam_rail_on() && app.ui.state != GL_UI_CAPTURE) {
            seen.rail_outside_capture++;
        }
    }
}

/* Run until the UI reaches `state` (true) or t_ms passes (false). */
static inline bool run_until_state_(gl_ui_state_t state, uint32_t t_ms)
{
    while (gl_sim_now_us() < (uint64_t)t_ms * 1000u) {
        if (app.ui.state == (uint8_t)state) {
            return true;
        }
        run_until_ms_((uint32_t)(gl_sim_now_us() / 1000u) + 1u);
    }
    return app.ui.state == (uint8_t)state;
}

static inline void print_seen_(void)
{
    printf("    states:");
    for (unsigned i = 0; i < seen.n; i++) {
        printf(" %s@%.2fs", gl_ui_state_name((gl_ui_state_t)seen.state[i]),
               (double)seen.t_ms[i] / 1000.0);
    }
    printf("\n");
}

static inline bool cam_pins_parked_(void)
{
    for (int p = (int)GL_PIN_CAM_FACING_FIRST; p <= (int)GL_PIN_CAM_FACING_LAST; p++) {
        if (gl_sim_pin_mode((gl_pin_t)p) != GL_PIN_MODE_ANALOG && !gl_sim_pin_drives_low((gl_pin_t)p)) {
            return false;
        }
    }
    return true;
}

/*
 * INDEPENDENT check of the camera rail rule: replay the recorded pin trace
 * with a model written here (not the simulator's checker) and count every
 * moment at which a camera-facing pin is neither analog nor driven low
 * while the rail enable is not driving high (or was raised less than 1 ms
 * ago).  Also: no SCCB, clock or DCMI activity while the rail is off.
 * Initial pin state: everything analog (MCU reset state).
 */
typedef struct {
    unsigned pin_violations;
    unsigned bus_violations;
    unsigned rail_on_edges;
    unsigned sccb_writes, dcmi_starts;
    uint64_t rail_on_us;
} replay_t;

static inline void replay_rail_rule_(replay_t *out)
{
    uint8_t mode[GL_PIN_COUNT];
    bool latch[GL_PIN_COUNT];
    bool rail = false;
    uint64_t rail_since = 0;

    memset(out, 0, sizeof(*out));
    memset(latch, 0, sizeof(latch));
    for (int p = 0; p < (int)GL_PIN_COUNT; p++) {
        mode[p] = (uint8_t)GL_PIN_MODE_ANALOG;
    }
    for (size_t i = 0; i < gl_sim_trace_count(); i++) {
        const gl_sim_trace_t *t = gl_sim_trace_at(i);
        bool pin_event = false;
        switch ((gl_sim_tr_type_t)t->type) {
        case GL_SIM_TR_GPIO_MODE:
            mode[t->a] = (uint8_t)t->b;
            pin_event = true;
            break;
        case GL_SIM_TR_GPIO_WRITE:
            latch[t->a] = (t->b != 0u);
            pin_event = true;
            break;
        case GL_SIM_TR_SCCB_WRITE:
        case GL_SIM_TR_SCCB_READ:
            out->sccb_writes += (t->type == (uint8_t)GL_SIM_TR_SCCB_WRITE) ? 1u : 0u;
            if (!rail) {
                out->bus_violations++;
            }
            break;
        case GL_SIM_TR_DCMI_START:
            out->dcmi_starts++;
            if (!rail) {
                out->bus_violations++;
            }
            break;
        case GL_SIM_TR_XVCLK:
            if (t->a == 1u && !rail) {
                out->bus_violations++;
            }
            break;
        default:
            break;
        }
        if (!pin_event) {
            continue;
        }
        {
            const bool en = (mode[GL_PIN_CAM_PWR_EN] == (uint8_t)GL_PIN_MODE_OUTPUT_PP) &&
                            latch[GL_PIN_CAM_PWR_EN];
            if (en && !rail) {
                rail = true;
                rail_since = t->t_us;
                out->rail_on_edges++;
            } else if (!en && rail) {
                rail = false;
                out->rail_on_us += t->t_us - rail_since;
            }
        }
        if (!rail || t->t_us - rail_since < 1000u) {
            for (int p = (int)GL_PIN_CAM_FACING_FIRST; p <= (int)GL_PIN_CAM_FACING_LAST; p++) {
                const bool analog = (mode[p] == (uint8_t)GL_PIN_MODE_ANALOG);
                const bool low = (mode[p] == (uint8_t)GL_PIN_MODE_OUTPUT_PP ||
                                  mode[p] == (uint8_t)GL_PIN_MODE_OUTPUT_OD) && !latch[p];
                if (!analog && !low) {
                    out->pin_violations++;
                    break;
                }
            }
        }
    }
}

/* The panel memory of the LCD model as a pixel test: true = black. */
static inline bool panel_black_(int x, int y)
{
    const gl_sim_lcd_t *lcd = gl_sim_lcd();
    return (lcd->mem[(unsigned)y * 16u + ((unsigned)x >> 3)] & (1u << ((unsigned)x & 7u))) == 0u;
}

static inline unsigned panel_differs_from_framebuffer_(void)
{
    const gl_sim_lcd_t *lcd = gl_sim_lcd();
    unsigned bad = 0;
    for (unsigned i = 0; i < sizeof(lcd->mem); i++) {
        if (lcd->mem[i] != app.gfx.px[i]) {
            bad++;
        }
    }
    return bad;
}

/* ---- a USB host on the simulated CDC port ---------------------------------- */

static uint8_t host_rx_[4096];
static size_t host_rx_len_;

static inline void host_send_(uint8_t seq, uint8_t cmd, const void *payload, size_t n)
{
    uint8_t f[GL_PROTO_MAX_FRAME];
    const size_t len = gl_proto_encode(f, sizeof(f), seq, cmd, (const uint8_t *)payload, n);
    gl_sim_usb_host_send(f, len);
}

/* Run the device for a moment, then take the first complete frame with the
 * given CMD byte out of what the host received.  Returns the payload length
 * or -1. */
static inline int host_get_(uint8_t want_cmd, uint8_t *seq, const uint8_t **payload)
{
    static const uint8_t none[8];
    *payload = none;
    *seq = 0;
    run_until_ms_((uint32_t)(gl_sim_now_us() / 1000u) + 30u);
    host_rx_len_ += gl_sim_usb_host_recv(&host_rx_[host_rx_len_], sizeof(host_rx_) - host_rx_len_);
    for (size_t pos = 0; pos + GL_PROTO_OVERHEAD <= host_rx_len_;) {
        const size_t n = gl_get_u16(&host_rx_[pos + 2]);
        if (host_rx_[pos] != 0xA5 || host_rx_[pos + 1] != 0x5A || pos + n + 8u > host_rx_len_ ||
            gl_crc16(&host_rx_[pos + 2], n + 4u) != gl_get_u16(&host_rx_[pos + 6u + n])) {
            pos++;
            continue;
        }
        if (host_rx_[pos + 5] == want_cmd) {
            static uint8_t copy[GL_PROTO_MAX_PAYLOAD];
            *seq = host_rx_[pos + 4];
            memcpy(copy, &host_rx_[pos + 6], n);
            *payload = copy;
            host_rx_len_ = 0; /* everything up to here is consumed */
            return (int)n;
        }
        pos += n + 8u;
    }
    return -1;
}

#endif /* GL_E2E_WORLD_H */
