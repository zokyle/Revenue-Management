/* gl_read.c - camera sequence of a read and the vision on it.  See gl_read.h. */
#include "gl_read.h"

#include <math.h>
#include <string.h>

#include <stddef.h>

#include "gl_cal.h"
#include "gl_config.h"
#include "gl_hal.h"

/* The STM32 backend captures by DMA in 32-bit words: both strip buffers must
 * start on a 4-byte boundary and every capture must be a multiple of 4 bytes
 * and fit one DMA block (below 64 kB).  Checked at compile time. */
typedef char gl_read_img_is_word_aligned_[(offsetof(gl_read_t, img) % 4u == 0u) ? 1 : -1];
typedef char gl_read_strip_is_whole_words_[(GL_READ_STRIP_BYTES % 4u == 0u) ? 1 : -1];
typedef char gl_read_band_is_whole_words_[(GL_READ_BAND_BYTES % 4u == 0u) ? 1 : -1];
typedef char gl_read_band_fits_[(GL_READ_BAND_BYTES <= GL_READ_IMG_BYTES) ? 1 : -1];
typedef char gl_read_captures_fit_one_dma_block_[
    (GL_READ_BAND_BYTES < 65536u && GL_READ_STRIP_BYTES < 65536u) ? 1 : -1];

/* Camera of stick strip k: L R R L, L R R L, ... */
static gl_cam_id_t cam_of_(unsigned k)
{
    static const uint8_t order[4] = { GL_CAM_LEFT, GL_CAM_RIGHT, GL_CAM_RIGHT, GL_CAM_LEFT };
    return (gl_cam_id_t)order[k & 3u];
}

/* Strip k is captured into buffer k mod 2, so that strip k can be analysed
 * while strip k + 1 is being captured. */
static uint8_t *strip_buf_(gl_read_t *r, unsigned k)
{
    return &r->img[(k & 1u) * GL_READ_STRIP_BYTES];
}

void gl_read_set_cal(gl_read_t *r, const gl_cal_cam_t *left, const gl_cal_cam_t *right)
{
    gl_cam_model_init(&r->model[GL_CAM_LEFT], left);
    gl_cam_model_init(&r->model[GL_CAM_RIGHT], right);
}

void gl_read_set_strip_hook(gl_read_t *r, gl_read_strip_fn_t fn, void *ctx)
{
    r->strip_fn = fn;
    r->strip_ctx = ctx;
}

void gl_read_init(gl_read_t *r, gl_ov7692_t *cam)
{
    gl_cal_cam_t cl, cr;
    /* the large buffers need no clearing: every byte is written before use */
    r->cam = cam;
    r->strip_fn = NULL;
    r->strip_ctx = NULL;
    r->time_correction = true;
    r->phase = (uint8_t)GL_READ_IDLE;
    memset(&r->result, 0, sizeof(r->result));
    gl_cal_cam_defaults(&cl, 0);
    gl_cal_cam_defaults(&cr, 1);
    gl_read_set_cal(r, &cl, &cr);
}

bool gl_read_busy(const gl_read_t *r)
{
    return r->phase != (uint8_t)GL_READ_IDLE;
}

/* Rail off, sequence idle.  Safe in any state. */
static void rail_off_(gl_read_t *r)
{
    const bool was_on = r->cam->powered;
    gl_ov7692_power_down(r->cam);
    if (was_on) {
        r->result.rail_on_ms = (uint32_t)(gl_hal_tick_ms() - r->t_rail_on_ms);
    }
}

void gl_read_abort(gl_read_t *r)
{
    rail_off_(r);
    r->phase = (uint8_t)GL_READ_IDLE;
}

gl_status_t gl_read_start(gl_read_t *r, gl_vec3_t up_marker, unsigned repeats)
{
    gl_status_t st;
    int y0;

    if (r->phase != (uint8_t)GL_READ_IDLE) {
        return GL_ERR_BUSY;
    }
    if (repeats < 1u || repeats > 32u) {
        return GL_ERR_PARAM;
    }
    memset(&r->result, 0, sizeof(r->result));
    memset(r->stick_ok, 0, sizeof(r->stick_ok));
    memset(r->have_last, 0, sizeof(r->have_last));
    memset(r->have_first, 0, sizeof(r->have_first));
    r->repeats = (uint8_t)repeats;
    r->k = 0;
    r->up = up_marker;
    r->have_d_est = false;
    r->d_est_px = 0.0f;
    r->sum_bottom = r->sum_xb = r->sum_slope = r->sum_top = r->sum_horizon = 0.0f;
    r->n_left = r->n_top = r->n_horizon_rows = 0;
    gl_vis_disp_acc_reset(&r->acc);

    r->t_rail_on_ms = gl_hal_tick_ms();
    st = gl_ov7692_power_up(r->cam); /* on failure the driver has switched the rail off */
    if (st != GL_OK) {
        return st;
    }

    /* horizon band of the left camera, centred on its calibrated horizon row */
    y0 = gl_roundi(gl_cam_base_plane_row(&r->model[GL_CAM_LEFT],
                                         0.5f * (float)(GL_OV7692_SENSOR_W - 1u))) -
         (int)(GL_APP_BAND_H / 2u);
    y0 = gl_clampi(y0, 0, (int)(GL_OV7692_SENSOR_H - GL_APP_BAND_H));
    /* both sensors are woken now, so that the right one has settled by the
     * time its first strip is wanted */
    st = gl_ov7692_select(r->cam, GL_CAM_LEFT, GL_OV_OTHER_AWAKE);
    if (st == GL_OK) {
        st = gl_ov7692_set_window(r->cam, GL_CAM_LEFT, 0, (uint16_t)y0, (uint16_t)GL_APP_BAND_W,
                                  (uint16_t)GL_APP_BAND_H);
    }
    if (st == GL_OK) {
        st = gl_ov7692_capture_start(r->cam, GL_CAM_LEFT, r->img, GL_READ_IMG_BYTES, &r->cur);
    }
    if (st != GL_OK) {
        gl_read_abort(r);
        return st;
    }
    r->phase = (uint8_t)GL_READ_BAND;
    return GL_OK;
}

/* Select the camera of strip r->k and arm its capture. */
static gl_status_t start_strip_(gl_read_t *r)
{
    const gl_cam_id_t c = cam_of_(r->k);
    gl_status_t st = gl_ov7692_select(r->cam, c, GL_OV_OTHER_AWAKE);
    if (st == GL_OK) {
        st = gl_ov7692_capture_start(r->cam, c, strip_buf_(r, r->k), GL_READ_STRIP_BYTES, &r->cur);
    }
    if (st != GL_OK) {
        gl_read_abort(r);
        return st;
    }
    return GL_ERR_BUSY;
}

static gl_status_t band_done_(gl_read_t *r)
{
    gl_status_t st;
    int xl, xr;

    if (r->strip_fn != NULL) {
        r->strip_fn(r->strip_ctx, &r->cur, GL_CAM_LEFT, 0, 0);
    }
    st = gl_vis_band_analyse(&r->cur, &r->band_work, &r->band);
    r->result.n_candidates = r->band.n_cand;
    r->result.band_noise = r->band.stats.noise_sigma;
    /* turf-horizon samples as angles relative to gravity */
    r->result.n_horizon = 0;
    if (st == GL_OK || st == GL_ERR_NO_STICK) {
        for (unsigned i = 0; i < GL_VIS_HORIZON_BINS; i++) {
            if ((r->band.horizon_valid & (1u << i)) != 0u) {
                const unsigned n = r->result.n_horizon;
                gl_cam_pixel_to_bearing_elev(&r->model[GL_CAM_LEFT], r->band.horizon_col[i],
                                             r->band.horizon_row[i], r->up,
                                             &r->result.horizon_az_rad[n],
                                             &r->result.horizon_elev_rad[n]);
                r->result.n_horizon = (uint8_t)(n + 1u);
            }
        }
    }
    if (st != GL_OK) {
        gl_read_abort(r);
        return st; /* GL_ERR_NO_STICK: nothing to follow */
    }
    r->cand = r->band.cand[0];
    r->result.cand_score = r->cand.score;

    /* strip windows: 96 columns around the candidate; the right camera's
     * shifted left by the expected disparity */
    xl = gl_clampi(gl_roundi(r->cand.x) - (int)(GL_APP_STRIP_W / 2u), 0,
                   (int)(GL_OV7692_SENSOR_W - GL_APP_STRIP_W));
    xr = gl_clampi(xl - GL_APP_RIGHT_WINDOW_SHIFT_PX, 0, (int)(GL_OV7692_SENSOR_W - GL_APP_STRIP_W));
    st = gl_ov7692_set_window(r->cam, GL_CAM_LEFT, (uint16_t)xl, 0, (uint16_t)GL_APP_STRIP_W,
                              (uint16_t)GL_APP_STRIP_H);
    if (st == GL_OK) {
        st = gl_ov7692_set_window(r->cam, GL_CAM_RIGHT, (uint16_t)xr, 0, (uint16_t)GL_APP_STRIP_W,
                                  (uint16_t)GL_APP_STRIP_H);
    }
    if (st != GL_OK) {
        gl_read_abort(r);
        return st;
    }
    r->win_x0[GL_CAM_LEFT] = r->cam->cam[GL_CAM_LEFT].x0;
    r->win_x0[GL_CAM_RIGHT] = r->cam->cam[GL_CAM_RIGHT].x0;
    r->k = 0;
    r->phase = (uint8_t)GL_READ_STRIPS;
    return start_strip_(r);
}

/* Vision on one stick strip: slot f (0..3) of the current group. */
static void analyse_strip_(gl_read_t *r, const gl_strip_t *strip, unsigned f, gl_cam_id_t c)
{
    gl_vis_prior_t prior;
    gl_vis_stick_t *s = &r->stick[f];

    if (r->have_last[c]) {
        /* follow the stick from this camera's previous strip (it may sway) */
        prior.x = r->last[c].x_ref;
        prior.row = r->last[c].row_ref;
        prior.slant = r->last[c].slope;
        prior.search_px = 0.0f; /* default */
    } else {
        prior.x = r->cand.x - ((c == GL_CAM_RIGHT) ? GL_APP_RIGHT_PRIOR_SHIFT_PX : 0.0f);
        prior.row = r->cand.ref_row;
        prior.slant = r->cand.slant;
        prior.search_px = GL_APP_FIRST_SEARCH_PX;
    }
    prior.width_px = r->cand.width_px;

    r->stick_ok[f] = (gl_vis_stick_refine(strip, &prior, &r->stick_work[f], s) == GL_OK);
    if (!r->stick_ok[f]) {
        return;
    }
    r->last[c] = *s;
    r->have_last[c] = true;
    if (!r->have_first[c]) {
        r->first[c] = *s;
        /* tmp is free scratch once the refinement is done (480 floats >= max(480, width)) */
        gl_vis_strip_stats(strip, r->stick_work[f].tmp, &r->stats[c]);
        r->have_first[c] = true;
    }
    if (c == GL_CAM_LEFT) {
        r->sum_bottom += s->bottom_row;
        r->sum_xb += gl_vis_stick_x_at(s, s->bottom_row);
        r->sum_slope += s->slope;
        r->n_left++;
        if (s->top_in_frame) {
            r->sum_top += s->top_row;
            r->n_top++;
        }
        if (s->horizon_found) {
            r->sum_horizon += s->horizon_row;
            r->n_horizon_rows++;
        }
    }
}

/* The four strips of a group are in: segment fits over the lowest part of
 * the stick, timing correction, disparity of the group. */
static void group_done_(gl_read_t *r)
{
    gl_vis_segment_t seg[4];
    float bot = 1.0e9f;
    unsigned nrows;

    r->result.groups_tried++;
    for (unsigned f = 0; f < 4u; f++) {
        if (!r->stick_ok[f]) {
            return;
        }
        if (r->stick[f].bottom_row < bot) {
            bot = r->stick[f].bottom_row;
        }
    }
    bot -= GL_APP_SEGMENT_SKIP_ROWS;
    if (!r->have_d_est) {
        /* first estimate from 60 rows of the first pair: sizes the segment */
        gl_vis_segment_t a, b;
        float d0 = 0.0f, s0 = 0.0f;
        if (gl_vis_stick_segment(&r->stick_work[0], &r->stick[0], bot - 58.0f, bot, &a) == GL_OK &&
            gl_vis_stick_segment(&r->stick_work[1], &r->stick[1], bot - 58.0f, bot, &b) == GL_OK &&
            gl_vis_stereo_pair(&a, &b, &r->model[GL_CAM_LEFT], &r->model[GL_CAM_RIGHT],
                               GL_CFG_CAM_F_PX, &d0, &s0) == GL_OK &&
            d0 > 0.0f) {
            r->d_est_px = d0;
            r->have_d_est = true;
        }
    }
    nrows = gl_vis_segment_rows(r->have_d_est ? r->d_est_px : -1.0f, GL_CFG_CAM_BASELINE_M,
                                GL_APP_SEGMENT_LENGTH_M);
    for (unsigned f = 0; f < 4u; f++) {
        if (gl_vis_stick_segment(&r->stick_work[f], &r->stick[f], bot - (float)nrows, bot,
                                 &seg[f]) != GL_OK) {
            return;
        }
    }
    /* Timing: move the two LEFT positions to the mean time of the two RIGHT
     * strips along the left camera's own sway rate (see gl_read.h). */
    {
        const int32_t dt_l = (int32_t)(r->t_done_ms[3] - r->t_done_ms[0]);
        const int32_t t_r1 = (int32_t)(r->t_done_ms[1] - r->t_done_ms[0]);
        const int32_t t_r2 = (int32_t)(r->t_done_ms[2] - r->t_done_ms[0]);
        if (r->time_correction && dt_l > 0) {
            const float row_c = 0.5f * (seg[0].row_mid + seg[3].row_mid);
            const float x0 = seg[0].x_mid + seg[0].slope * (row_c - seg[0].row_mid);
            const float x3 = seg[3].x_mid + seg[3].slope * (row_c - seg[3].row_mid);
            const float rate_px_per_ms = (x3 - x0) / (float)dt_l;
            const float shift_ms = 0.5f * (float)(t_r1 + t_r2) - 0.5f * (float)dt_l;
            const float delta = gl_clampf(rate_px_per_ms * shift_ms, -2.0f, 2.0f);
            seg[0].x_mid += delta;
            seg[3].x_mid += delta;
        }
    }
    if (gl_vis_disp_acc_add_lrrl(&r->acc, seg, &r->model[GL_CAM_LEFT], &r->model[GL_CAM_RIGHT],
                                 GL_CFG_CAM_F_PX) == GL_OK) {
        r->result.groups_ok++;
    }
}

/* All strips analysed: combine. */
static gl_status_t finish_(gl_read_t *r)
{
    gl_vis_stick_t *s = &r->result.stick_left;
    const float n = (float)r->n_left;

    r->phase = (uint8_t)GL_READ_IDLE;
    r->result.stick_found = false;
    if (r->result.groups_ok < GL_APP_MIN_GROUPS || r->n_left == 0u || !r->have_first[GL_CAM_LEFT] ||
        !r->have_first[GL_CAM_RIGHT]) {
        return GL_ERR_NO_STICK;
    }
    if (gl_vis_disp_acc_result(&r->acc, &r->result.disp) != GL_OK) {
        return GL_ERR_NO_STICK;
    }
    /* The geometry of the stick from the LEFT camera, averaged over its
     * strips BEFORE the base is classified: a single strip's lowest point
     * has 0.1-0.4 row of noise, the margin is 1.5 rows. */
    *s = r->first[GL_CAM_LEFT];
    s->bottom_row = r->sum_bottom / n;
    s->row_ref = s->bottom_row;
    s->x_ref = r->sum_xb / n;
    s->slope = r->sum_slope / n;
    s->top_in_frame = (2u * (unsigned)r->n_top > (unsigned)r->n_left);
    if (s->top_in_frame) {
        s->top_row = r->sum_top / (float)r->n_top;
    }
    s->horizon_found = (2u * (unsigned)r->n_horizon_rows > (unsigned)r->n_left);
    if (!s->horizon_found) {
        s->base = (uint8_t)GL_VIS_BASE_UNKNOWN;
    } else {
        s->horizon_row = r->sum_horizon / (float)r->n_horizon_rows;
        s->base = (uint8_t)((s->bottom_row - s->horizon_row > GL_VIS_BASE_MARGIN_ROWS)
                                ? GL_VIS_BASE_VISIBLE
                                : GL_VIS_BASE_AT_HORIZON);
    }
    gl_vis_stick_angles(s, &r->model[GL_CAM_LEFT], r->up, &r->result.angles);
    gl_vis_quality(&r->first[GL_CAM_LEFT], &r->first[GL_CAM_RIGHT], &r->stats[GL_CAM_LEFT],
                   &r->stats[GL_CAM_RIGHT], &r->result.quality);
    r->result.stick_found = true;
    return GL_OK;
}

static gl_status_t strip_done_(gl_read_t *r)
{
    const gl_strip_t done = r->cur;
    const unsigned kd = r->k;
    const unsigned f = kd & 3u;
    const gl_cam_id_t c = cam_of_(kd);
    const bool last = (kd + 1u >= 4u * (unsigned)r->repeats);

    r->t_done_ms[f] = r->cam->last_done_ms;
    r->result.strips_captured++;
    if (last) {
        /* every strip is in memory: the cameras are no longer needed */
        rail_off_(r);
    } else {
        /* arm the next capture first; this strip is analysed meanwhile */
        r->k = (uint16_t)(kd + 1u);
        const gl_status_t st = start_strip_(r);
        if (st != GL_ERR_BUSY) {
            return st; /* aborted, rail off */
        }
    }
    if (r->strip_fn != NULL) {
        r->strip_fn(r->strip_ctx, &done, c, 1, (uint8_t)kd);
    }
    analyse_strip_(r, &done, f, c);
    if (f == 3u) {
        group_done_(r);
    }
    return last ? finish_(r) : GL_ERR_BUSY;
}

gl_status_t gl_read_step(gl_read_t *r)
{
    gl_status_t st;
    if (r->phase == (uint8_t)GL_READ_IDLE) {
        return GL_ERR_STATE;
    }
    st = gl_ov7692_capture_poll(r->cam);
    if (st == GL_ERR_BUSY) {
        return GL_ERR_BUSY;
    }
    if (st != GL_OK) {
        gl_read_abort(r);
        return st;
    }
    return (r->phase == (uint8_t)GL_READ_BAND) ? band_done_(r) : strip_done_(r);
}
