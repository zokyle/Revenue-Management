/*
 * gl_sim_cam.c - two OVM7692 models on the shared parallel bus, the SCCB
 * control bus and the DCMI capture, for the host simulator.
 *
 * WHAT THE MODEL ASSUMES ABOUT THE SENSOR (the same provisional reading of
 * the part that the driver is written from; see core/gl_provisional.h):
 *   - SCCB address 3Ch; registers 0Ah/0Bh = 76h/92h (product id), 1Ch/1Dh =
 *     7Fh/A2h (manufacturer id); register FFh selects the bank.
 *   - 12h bit 7: software reset, self-clearing after 2 ms.
 *   - 0Ch: bit 7 vertical flip, bit 6 horizontal mirror, bit 4 YU/YV swap,
 *     bits 2 and 1 = output drivers enabled (1 = driven); reset value 16h.
 *   - 0Eh bit 3: sleep (stops streaming).
 *   - PWDN high = power-down; in power-down the outputs are released.
 *   - Window: column 0 at HSTART (17h) = 69h in units of 4 pixels, row 0 at
 *     VSTART (19h) = 0Ch in units of 2 lines, HSIZE (18h) = (width + 16) / 4,
 *     VSIZE (1Ah) = (height + 12) / 2, output size in CCh..CFh, input size in
 *     C8h..CBh equal to the output size (no scaling).  After a reset the
 *     vertical output size reads 180h (384 lines), as the comments of the
 *     public driver say, so a driver that wants VGA must program it.
 *   - YUV422 with Y as the first byte of each pair while 0Ch bit 4 is clear.
 *   - The image is upright (as the firmware defines it) when the vertical
 *     flip bit is set and the mirror bit clear: the fold prism is assumed to
 *     invert the image top to bottom.
 *   - 30 frames per second, free running from the moment streaming starts;
 *     the first GL_SIM_CAM_BAD_FRAMES frames after that are black.
 *
 * DCMI: snapshot of the next complete frame of whichever camera drives the
 * bus.  Crop is applied to the byte stream first, then the byte select
 * relative to the start of the crop (the contract of gl_hal.h).
 */
#include <string.h>

#include "gl_sim_internal.h"

#define CAM_ADDR7 0x3C
#define CAM_RAIL_SETTLE_US 1000u
#define CAM_RESET_US 2000u
#define CAM_NEEDS_VFLIP 1
#define CAM_NEEDS_MIRROR 0
#define SCCB_WRITE_US 290u
#define SCCB_READ_US 400u

typedef struct {
    bool present;
    uint16_t pid;
    bool reset_stuck;
    uint8_t reg[2][256];
    uint8_t bank;
    bool powered, clocked, pwdn;
    bool streaming, driving;
    uint64_t t_stream0;
    uint32_t phase_us;
    uint64_t reset_done_at;
} cam_t;

static cam_t C[GL_CAM_COUNT];
static bool xvclk_on_;
static bool contention_;
static gl_sim_scene_fn_t scene_fn_;
static void *scene_ctx_;

static struct {
    bool busy;
    gl_dcmi_cfg_t cfg;
    uint8_t *buf;
    size_t expect;
    gl_dcmi_state_t state;
    size_t bytes;
    uint64_t t_event;
    bool will_timeout;
    int cam;
    uint64_t t_frame;
    uint32_t frame_no;
    bool disturbed;
} D;

static void defaults_(cam_t *c)
{
    memset(c->reg, 0, sizeof(c->reg));
    c->bank = 0;
    c->reg[0][0x0A] = (uint8_t)(c->pid >> 8);
    c->reg[0][0x0B] = (uint8_t)(c->pid & 0xFFu);
    c->reg[0][0x1C] = 0x7F;
    c->reg[0][0x1D] = 0xA2;
    c->reg[0][0x0C] = 0x16;
    c->reg[0][0x17] = 0x69;
    c->reg[0][0x18] = 0xA4;
    c->reg[0][0x19] = 0x0C;
    c->reg[0][0x1A] = 0xF6;
    c->reg[0][0xC8] = 0x02;
    c->reg[0][0xC9] = 0x80;
    c->reg[0][0xCA] = 0x01;
    c->reg[0][0xCB] = 0xE0;
    c->reg[0][0xCC] = 0x02;
    c->reg[0][0xCD] = 0x80;
    c->reg[0][0xCE] = 0x01;
    c->reg[0][0xCF] = 0x80; /* 384 lines: see the file comment */
}

void sim_cam_reset(void)
{
    memset(C, 0, sizeof(C));
    memset(&D, 0, sizeof(D));
    D.cam = -1;
    xvclk_on_ = false;
    contention_ = false;
    scene_fn_ = NULL;
    scene_ctx_ = NULL;
    for (int i = 0; i < (int)GL_CAM_COUNT; i++) {
        C[i].present = true;
        C[i].pid = 0x7692u;
        defaults_(&C[i]);
    }
}

void gl_sim_cam_set_scene(gl_sim_scene_fn_t fn, void *ctx)
{
    scene_fn_ = fn;
    scene_ctx_ = ctx;
}

void gl_sim_cam_set_present(gl_cam_id_t cam, bool present)
{
    C[cam].present = present;
}

void gl_sim_cam_set_pid(gl_cam_id_t cam, uint16_t pid)
{
    C[cam].pid = pid;
    C[cam].reg[0][0x0A] = (uint8_t)(pid >> 8);
    C[cam].reg[0][0x0B] = (uint8_t)(pid & 0xFFu);
}

void gl_sim_cam_set_reset_stuck(gl_cam_id_t cam, bool stuck)
{
    C[cam].reset_stuck = stuck;
}

void gl_sim_cam_set_phase_us(gl_cam_id_t cam, uint32_t phase_us)
{
    C[cam].phase_us = phase_us % GL_SIM_CAM_FRAME_US;
}

uint8_t gl_sim_cam_reg(gl_cam_id_t cam, uint8_t reg)
{
    return C[cam].reg[0][reg];
}

bool gl_sim_cam_driving(gl_cam_id_t cam)
{
    return C[cam].driving;
}

bool gl_sim_cam_streaming(gl_cam_id_t cam)
{
    return C[cam].streaming;
}

bool sim_cam_capture_busy(void)
{
    return D.busy;
}

/* Re-evaluate everything that depends on pins, the rail, the clock and the
 * registers. */
void sim_cam_update(void)
{
    const bool rail = gl_sim_cam_rail_on();
    for (int i = 0; i < (int)GL_CAM_COUNT; i++) {
        cam_t *c = &C[i];
        const gl_pin_t pwdn_pin = (i == 0) ? GL_PIN_CAM_L_PWDN : GL_PIN_CAM_R_PWDN;
        if (!rail && c->powered) {
            defaults_(c); /* registers are lost with the supply */
            c->reset_done_at = 0;
        }
        c->powered = rail;
        c->clocked = xvclk_on_;
        c->pwdn = sim_pin_out_high(pwdn_pin);
        const bool streaming = c->present && c->powered && c->clocked && !c->pwdn &&
                               c->reset_done_at != SIM_NEVER && (c->reg[0][0x0E] & 0x08u) == 0u;
        if (streaming && !c->streaming) {
            uint64_t t = sim_now();
            if (c->reset_done_at > t) {
                t = c->reset_done_at;
            }
            c->t_stream0 = t + c->phase_us;
        }
        c->streaming = streaming;
        const bool driving = streaming && (c->reg[0][0x0C] & 0x06u) != 0u;
        if (driving != c->driving && D.busy) {
            D.disturbed = true;
        }
        c->driving = driving;
    }
    const bool both = C[0].driving && C[1].driving;
    if (both && !contention_) {
        sim_violation(&sim_viol()->cam_contention, "both cameras drive the shared bus");
    }
    contention_ = both;
}

void sim_cam_xvclk(bool running, uint32_t hz)
{
    (void)hz;
    xvclk_on_ = running;
    sim_cam_update();
}

/* ---- SCCB ---------------------------------------------------------------------- */

static bool sccb_ok_(gl_cam_id_t cam, uint8_t addr7, const char *what)
{
    const cam_t *c = &C[cam];
    const gl_pin_t scl = (cam == GL_CAM_LEFT) ? GL_PIN_CAM_L_SCL : GL_PIN_CAM_R_SCL;
    if (!sim_pin_is_alt(scl) || !sim_pin_is_alt(GL_PIN_CAM_SCCB_SDA)) {
        sim_violation(&sim_viol()->cam_sccb, "SCCB %s with the bus pins not in ALTERNATE mode", what);
        return false;
    }
    if (!c->powered || !c->clocked || c->pwdn) {
        sim_violation(&sim_viol()->cam_sccb, "SCCB %s to camera %d which is %s", what, (int)cam,
                      !c->powered ? "unpowered" : (!c->clocked ? "not clocked" : "in power-down"));
        return false;
    }
    return c->present && addr7 == CAM_ADDR7; /* an absent camera simply does not acknowledge */
}

gl_status_t gl_hal_sccb_write(gl_cam_id_t cam, uint8_t addr7, uint8_t reg, uint8_t val)
{
    gl_status_t st = GL_OK;
    if ((unsigned)cam >= (unsigned)GL_CAM_COUNT) {
        return GL_ERR_PARAM;
    }
    cam_t *c = &C[cam];
    if (!sccb_ok_(cam, addr7, "write")) {
        st = GL_ERR_IO;
    } else if (sim_now() < c->reset_done_at) {
        sim_violation(&sim_viol()->cam_sccb, "SCCB write of register 0x%02X during the software reset",
                      reg);
        st = GL_ERR_IO;
    } else if (reg == 0xFFu) {
        c->bank = val & 0x01u;
    } else if (c->bank == 0u && reg == 0x12u && (val & 0x80u) != 0u) {
        defaults_(c);
        c->reset_done_at = c->reset_stuck ? SIM_NEVER : sim_now() + SCCB_WRITE_US + CAM_RESET_US;
        c->streaming = false; /* restarts when the reset completes */
    } else if (c->bank == 0u && (reg == 0x0Au || reg == 0x0Bu || reg == 0x1Cu || reg == 0x1Du)) {
        sim_violation(&sim_viol()->cam_sccb, "write to read-only camera register 0x%02X", reg);
    } else {
        c->reg[c->bank][reg] = val;
    }
    sim_trace(GL_SIM_TR_SCCB_WRITE, (unsigned)cam, reg, val, (uint32_t)st);
    gl_hal_delay_us(SCCB_WRITE_US);
    sim_cam_update();
    return st;
}

gl_status_t gl_hal_sccb_read(gl_cam_id_t cam, uint8_t addr7, uint8_t reg, uint8_t *val)
{
    gl_status_t st = GL_OK;
    uint8_t v = 0xFF;
    if ((unsigned)cam >= (unsigned)GL_CAM_COUNT || val == NULL) {
        return GL_ERR_PARAM;
    }
    cam_t *c = &C[cam];
    if (!sccb_ok_(cam, addr7, "read")) {
        st = GL_ERR_IO;
    } else if (c->bank == 0u && reg == 0x12u && sim_now() < c->reset_done_at) {
        v = 0x80; /* reset still in progress */
    } else {
        v = c->reg[c->bank][reg];
    }
    *val = v;
    sim_trace(GL_SIM_TR_SCCB_READ, (unsigned)cam, reg, v, (uint32_t)st);
    gl_hal_delay_us(SCCB_READ_US);
    sim_cam_update();
    return st;
}

/* ---- DCMI ---------------------------------------------------------------------- */

gl_status_t gl_hal_dcmi_start(const gl_dcmi_cfg_t *cfg, uint8_t *buf, size_t buf_len)
{
    if (cfg == NULL || buf == NULL || (cfg->byte_select_every != 1u && cfg->byte_select_every != 2u) ||
        cfg->width_bytes == 0u || cfg->height_lines == 0u ||
        (cfg->width_bytes % cfg->byte_select_every) != 0u) {
        return GL_ERR_PARAM;
    }
    const size_t expect = (size_t)(cfg->width_bytes / cfg->byte_select_every) * cfg->height_lines;
    if (expect > buf_len) {
        return GL_ERR_PARAM;
    }
    if (D.busy) {
        return GL_ERR_BUSY;
    }
    for (int p = (int)GL_PIN_CAM_D0; p <= (int)GL_PIN_CAM_VSYNC; p++) {
        if (!sim_pin_is_alt((gl_pin_t)p)) {
            sim_violation(&sim_viol()->dcmi, "DCMI started with pin %d not in ALTERNATE mode", p);
            break;
        }
    }
    sim_cam_update();
    D.cfg = *cfg;
    D.buf = buf;
    D.expect = expect;
    D.bytes = 0;
    D.busy = true;
    D.disturbed = false;
    D.state = GL_DCMI_BUSY;
    D.cam = -1;
    if (C[0].driving != C[1].driving) {
        D.cam = C[0].driving ? 0 : 1;
    }
    if (D.cam < 0) {
        sim_violation(&sim_viol()->dcmi, "DCMI capture started with %s",
                      C[0].driving ? "both cameras driving the bus" : "no camera driving the bus");
        D.will_timeout = true;
        D.t_event = sim_now() + (uint64_t)cfg->timeout_ms * 1000u;
    } else {
        const cam_t *c = &C[D.cam];
        uint64_t t = sim_now() + 100u; /* arming latency */
        uint64_t k = 0;
        if (t > c->t_stream0) {
            k = (t - c->t_stream0 + GL_SIM_CAM_FRAME_US - 1u) / GL_SIM_CAM_FRAME_US;
        }
        D.t_frame = c->t_stream0 + k * GL_SIM_CAM_FRAME_US;
        D.frame_no = (uint32_t)k;
        D.t_event = D.t_frame + (GL_SIM_CAM_FRAME_US * 92u) / 100u;
        D.will_timeout = false;
        if (D.t_event > sim_now() + (uint64_t)cfg->timeout_ms * 1000u) {
            D.will_timeout = true;
            D.t_event = sim_now() + (uint64_t)cfg->timeout_ms * 1000u;
        }
    }
    sim_trace(GL_SIM_TR_DCMI_START, (unsigned)(D.cam < 0 ? 0xFF : D.cam), 0, (uint32_t)expect, 0);
    return GL_OK;
}

gl_dcmi_state_t gl_hal_dcmi_poll(size_t *bytes)
{
    if (bytes != NULL) {
        *bytes = D.bytes;
    }
    return D.state;
}

void gl_hal_dcmi_stop(void)
{
    D.busy = false;
    D.state = GL_DCMI_IDLE;
    D.bytes = 0;
    sim_trace(GL_SIM_TR_DCMI_STOP, 0, 0, 0, 0);
}

uint64_t sim_cam_next_event(void)
{
    return D.busy ? D.t_event : SIM_NEVER;
}

static void finish_(gl_dcmi_state_t st, size_t bytes)
{
    D.busy = false;
    D.state = st;
    D.bytes = bytes;
    if (st == GL_DCMI_DONE) {
        sim_stat()->frames_captured++;
    }
    sim_trace(GL_SIM_TR_DCMI_DONE, (unsigned)st, 0, (uint32_t)bytes, 0);
    sim_irq_raise(GL_IRQ_DCMI_DONE);
}

static void flip_rows_(uint8_t *img, unsigned w, unsigned h)
{
    for (unsigned y = 0; y < h / 2u; y++) {
        uint8_t *a = &img[(size_t)y * w];
        uint8_t *b = &img[(size_t)(h - 1u - y) * w];
        for (unsigned x = 0; x < w; x++) {
            const uint8_t t = a[x];
            a[x] = b[x];
            b[x] = t;
        }
    }
}

static void flip_cols_(uint8_t *img, unsigned w, unsigned h)
{
    for (unsigned y = 0; y < h; y++) {
        uint8_t *r = &img[(size_t)y * w];
        for (unsigned x = 0; x < w / 2u; x++) {
            const uint8_t t = r[x];
            r[x] = r[w - 1u - x];
            r[w - 1u - x] = t;
        }
    }
}

void sim_cam_fire(uint64_t t)
{
    (void)t;
    if (!D.busy) {
        return;
    }
    if (D.will_timeout) {
        finish_(GL_DCMI_ERROR_TIMEOUT, 0);
        return;
    }
    const cam_t *c = &C[D.cam];
    const uint8_t *r = c->reg[0];
    if (D.disturbed || !c->driving) {
        sim_violation(&sim_viol()->dcmi, "the driving camera changed during a capture");
        memset(D.buf, 0xEE, D.expect);
        finish_(GL_DCMI_DONE, D.expect);
        return;
    }
    /* sensor output window from the registers */
    const unsigned ww = ((unsigned)(r[0xCC] & 0x03u) << 8) | r[0xCD];
    const unsigned wh = ((unsigned)(r[0xCE] & 0x01u) << 8) | r[0xCF];
    const unsigned iw = ((unsigned)(r[0xC8] & 0x03u) << 8) | r[0xC9];
    const unsigned ih = ((unsigned)(r[0xCA] & 0x01u) << 8) | r[0xCB];
    const int wx0 = ((int)r[0x17] - 0x69) * 4;
    const int wy0 = ((int)r[0x19] - 0x0C) * 2;
    if (ww == 0u || wh == 0u || iw != ww || ih != wh || wx0 < 0 || wy0 < 0 ||
        (unsigned)wx0 + ww > 640u || (unsigned)wy0 + wh > 480u ||
        (unsigned)r[0x18] * 4u != ww + 16u || (unsigned)r[0x1A] * 2u != wh + 12u) {
        sim_violation(&sim_viol()->dcmi,
                      "camera %d window registers inconsistent (x0 %d y0 %d out %ux%u in %ux%u "
                      "HSIZE 0x%02X VSIZE 0x%02X)",
                      D.cam, wx0, wy0, ww, wh, iw, ih, r[0x18], r[0x1A]);
        finish_(GL_DCMI_ERROR_SIZE, 0);
        return;
    }
    if ((r[0x12] & 0x0Fu) != 0u) {
        sim_violation(&sim_viol()->dcmi, "camera %d is not in YUV422 output format (0x12 = 0x%02X)",
                      D.cam, r[0x12]);
    }
    const gl_dcmi_cfg_t *cfg = &D.cfg;
    if ((unsigned)cfg->x0_bytes + cfg->width_bytes > 2u * ww ||
        (unsigned)cfg->y0_lines + cfg->height_lines > wh) {
        finish_(GL_DCMI_ERROR_SIZE, 0); /* the frame is smaller than the crop window */
        return;
    }
    if (cfg->vsync_active_high != true || cfg->href_active_high != true ||
        cfg->pclk_rising_edge != true) {
        sim_violation(&sim_viol()->dcmi, "DCMI sync polarity / clock edge do not match the model");
    }
    const unsigned y_phase = ((r[0x0C] & 0x10u) != 0u) ? 1u : 0u; /* which byte of a pair is Y */
    const unsigned out_w = (unsigned)cfg->width_bytes / cfg->byte_select_every;
    const unsigned out_h = cfg->height_lines;
    const bool upright_v = (((r[0x0C] & 0x80u) != 0u) == (CAM_NEEDS_VFLIP != 0));
    const bool upright_h = (((r[0x0C] & 0x40u) != 0u) == (CAM_NEEDS_MIRROR != 0));

    if (D.frame_no < GL_SIM_CAM_BAD_FRAMES) {
        memset(D.buf, 0, D.expect);
    } else if (cfg->byte_select_every == 2u) {
        const unsigned first = (unsigned)cfg->x0_bytes + (cfg->byte_select_odd ? 1u : 0u);
        if ((first & 1u) != y_phase) {
            memset(D.buf, 0x80, D.expect); /* the chroma bytes were selected */
        } else if (scene_fn_ == NULL) {
            memset(D.buf, 0x40, D.expect);
        } else {
            scene_fn_(scene_ctx_, (gl_cam_id_t)D.cam, (uint16_t)((unsigned)wx0 + first / 2u),
                      (uint16_t)((unsigned)wy0 + cfg->y0_lines), (uint16_t)out_w, (uint16_t)out_h,
                      D.frame_no, D.t_frame, D.buf);
            if (!upright_v) {
                flip_rows_(D.buf, out_w, out_h);
            }
            if (!upright_h) {
                flip_cols_(D.buf, out_w, out_h);
            }
        }
    } else {
        /* all bytes kept: not used by the firmware; deliver luma in the Y
         * positions of a flat grey image */
        for (size_t i = 0; i < D.expect; i++) {
            const unsigned j = (unsigned)cfg->x0_bytes + (unsigned)(i % out_w);
            D.buf[i] = ((j & 1u) == y_phase) ? 0x40u : 0x80u;
        }
    }
    finish_(GL_DCMI_DONE, D.expect);
}
