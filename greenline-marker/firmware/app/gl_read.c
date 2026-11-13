/* gl_read.c - camera sequence of a read and the vision on it.  See gl_read.h. */
#include "gl_read.h"

#include <math.h>
#include <string.h>

#include <stddef.h>

#include "gl_cal.h"
#include "gl_config.h"
#include "gl_hal.h"
#include "gl_provisional.h"
#include "gl_range.h"

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

/* Strip k is captured into buffer k mod 4: a whole L R R L group is in
 * memory before any of it is analysed, so that the spacing of the four
 * exposures is set by the sensors and never by how long the vision takes. */
static uint8_t *strip_buf_(gl_read_t *r, unsigned k)
{
    return &r->img[(k & 3u) * GL_READ_STRIP_BYTES];
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

bool gl_read_has_work(const gl_read_t *r)
{
    return r->phase == (uint8_t)GL_READ_ANALYSE;
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

/* Forget everything measured on the candidate followed so far. */
static void reset_candidate_(gl_read_t *r)
{
    memset(r->stick_ok, 0, sizeof(r->stick_ok));
    memset(r->have_last, 0, sizeof(r->have_last));
    memset(r->have_first, 0, sizeof(r->have_first));
    memset(r->sum_bottom, 0, sizeof(r->sum_bottom));
    memset(r->sum_bottom2, 0, sizeof(r->sum_bottom2));
    memset(r->sum_bsig2, 0, sizeof(r->sum_bsig2));
    memset(r->n_base, 0, sizeof(r->n_base));
    r->bin[GL_CAM_LEFT] = r->bin[GL_CAM_RIGHT] = 1;
    r->have_d_est = false;
    r->d_est_px = 0.0f;
    r->sum_xref = r->sum_slope = r->sum_top = r->sum_horizon = 0.0f;
    r->n_left = r->n_right = r->n_top = r->n_top_clutter = r->n_horizon_rows = 0;
    r->result.groups_ok = 0;
    r->result.groups_tried = 0;
    gl_vis_disp_acc_reset(&r->acc);
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
    r->repeats = (uint8_t)repeats;
    r->k = 0;
    r->an = 0;
    r->progress = 0;
    r->up = up_marker;
    r->ci = 0;
    r->probing = false;
    memset(r->verdict, 0, sizeof(r->verdict));
    memset(r->rank, 0, sizeof(r->rank));
    reset_candidate_(r);

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

/* Verdicts on a band candidate after at least one L R R L group. */
#define V_NONE 0u /* the left camera's strips show no line */
#define V_LEFT 1u /* a line in the left camera, no disparity */
#define V_BAD 2u  /* measured in both cameras: not a flagstick */
#define V_OK 3u   /* width and disparity fit a flagstick */

/* Set both strip windows for band candidate ci and arm the first strip. */
static gl_status_t start_candidate_(gl_read_t *r, unsigned ci)
{
    gl_status_t st;
    int xl, xr;

    reset_candidate_(r);
    r->ci = (uint8_t)ci;
    r->cand = r->band.cand[ci];
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

/* Nothing measured: what the horizon band alone says. */
static gl_status_t finish_nothing_(gl_read_t *r, gl_read_why_t why, bool bearing_only)
{
    rail_off_(r);
    r->phase = (uint8_t)GL_READ_IDLE;
    r->result.stick_found = false;
    r->result.why = (uint8_t)why;
    r->result.tier = (uint8_t)GL_READ_TIER_NONE;
    memset(&r->result.quality, 0, sizeof(r->result.quality));
    r->result.quality.sun = r->band.stats.sun;
    r->result.quality.sat_fraction = r->band.stats.sat_fraction;
    if (bearing_only && r->cand.score >= GL_APP_BEARING_ONLY_MIN_SCORE) {
        float elev = 0.0f;
        memset(&r->result.angles, 0, sizeof(r->result.angles));
        gl_cam_pixel_to_bearing_elev(&r->model[GL_CAM_LEFT], r->cand.x, r->cand.ref_row, r->up,
                                     &r->result.angles.bearing_rad, &elev);
        r->result.tier = (uint8_t)GL_READ_TIER_BEARING;
    }
    return GL_ERR_NO_STICK;
}

static gl_status_t band_done_(gl_read_t *r)
{
    gl_status_t st;

    if (r->strip_fn != NULL) {
        r->strip_fn(r->strip_ctx, &r->cur, GL_CAM_LEFT, 0, 0);
    }
    r->t_band_us = r->cam->last_done_us;
    st = gl_vis_band_analyse(&r->cur, &r->band_work, &r->band);
    gl_hal_trace(GL_TRACE_VISION_BAND, (uint32_t)r->cur.width * r->cur.height);
    r->progress++;
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
    if (st == GL_ERR_NO_STICK) {
        memset(&r->cand, 0, sizeof(r->cand));
        return finish_nothing_(r, GL_READ_WHY_NO_CANDIDATE, false);
    }
    if (st != GL_OK) {
        gl_read_abort(r);
        return st;
    }
    /* Several lines in the band: each gets one L R R L group of its own
     * before one is chosen (the strongest line is not always the flagstick). */
    r->probing = (r->band.n_cand > 1u);
    return start_candidate_(r, 0);
}

/* Where the turf horizon is expected in camera c beside the candidate. */
static void horizon_prior_(const gl_read_t *r, gl_cam_id_t c, gl_vis_prior_t *p)
{
    p->have_horizon = true;
    if (r->have_last[c] && r->last[c].horizon_found) {
        p->horizon_row = r->last[c].horizon_row;
        p->horizon_tol_rows = 6.0f;
        return;
    }
    {
        const float base_l = gl_cam_base_plane_row(&r->model[GL_CAM_LEFT], r->cand.x);
        float best = 1.0e9f;
        int bi = -1;
        for (unsigned i = 0; i < GL_VIS_HORIZON_BINS; i++) {
            if ((r->band.horizon_valid & (1u << i)) != 0u) {
                const float dx = fabsf(r->band.horizon_col[i] - r->cand.x);
                if (dx < best) {
                    best = dx;
                    bi = (int)i;
                }
            }
        }
        if (bi >= 0 && best <= 60.0f) {
            p->horizon_row = r->band.horizon_row[bi]; /* the band saw the turf edge here */
            p->horizon_tol_rows = 6.0f;
        } else {
            p->horizon_row = base_l; /* the calibrated horizon row: a planar green */
            p->horizon_tol_rows = 48.0f;
        }
        if (c == GL_CAM_RIGHT) {
            /* the two cameras' rows differ by their mounting */
            p->horizon_row += gl_cam_base_plane_row(&r->model[GL_CAM_RIGHT], r->cand.x) - base_l;
            p->horizon_tol_rows += 4.0f;
        }
    }
}

/* Vision on one stick strip: slot f (0..3) of the current group.  Returns
 * what was done, as GL_TRACE_STRIP_* bits (the run time of a strip depends
 * on it: hal/gl_hal.h, gl_hal_trace). */
static uint32_t analyse_strip_(gl_read_t *r, const gl_strip_t *strip, unsigned f, gl_cam_id_t c)
{
    static const uint8_t bins[3] = { 1, 4, 16 };
    gl_vis_prior_t prior;
    gl_vis_stick_t *s = &r->stick[f];
    unsigned b0 = 0;
    uint32_t work = 0;
    /* the stick may have swayed since the band was exposed (its analysis
     * takes time): widen the first search accordingly */
    const float sway = gl_clampf(GL_APP_SWAY_ALLOW_PX_PER_S * 1.0e-6f *
                                     (float)(uint32_t)(r->t_done_us[f] - r->t_band_us),
                                 0.0f, GL_APP_SWAY_ALLOW_MAX_PX);

    memset(&prior, 0, sizeof(prior));
    if (r->have_last[c]) {
        /* follow the stick from this camera's previous strip (it may sway) */
        prior.x = r->last[c].x_ref;
        prior.row = r->last[c].row_ref;
        prior.slant = r->last[c].slope;
        prior.search_px = 0.0f; /* default */
    } else if (c == GL_CAM_LEFT) {
        prior.x = r->cand.x;
        prior.row = r->cand.ref_row;
        prior.slant = r->cand.slant;
        prior.search_px = GL_APP_FIRST_SEARCH_PX + sway;
    } else {
        /* Right camera: where the band's line would be if it were infinitely
         * far (through both camera models), and from there only to the LEFT,
         * by the disparity of 40 m .. 0.8 m.  A second line on the other
         * side of the stick is then outside the search. */
        float u = r->cand.x, v = r->cand.ref_row;
        (void)gl_cam_ray_to_pixel(&r->model[GL_CAM_RIGHT],
                                  gl_cam_pixel_to_ray(&r->model[GL_CAM_LEFT], u, v), &u, &v);
        prior.x = u - GL_APP_RIGHT_PRIOR_SHIFT_PX;
        prior.row = v;
        prior.slant = r->cand.slant;
        prior.search_px = GL_APP_RIGHT_SEARCH_PX + sway;
    }
    prior.width_px = r->cand.width_px;
    horizon_prior_(r, c, &prior);

    /* Unbinned first; a stick too faint for single rows is tried with 4 and
     * then 16 rows averaged along the line.  What worked is kept for the
     * camera's next strips. */
    while (b0 < 2u && bins[b0] < r->bin[c]) {
        b0++;
    }
    r->stick_ok[f] = false;
    for (unsigned b = b0; b < 3u && !r->stick_ok[f]; b++) {
        prior.bin_rows = bins[b];
        work |= GL_TRACE_STRIP_TRIED_1 << b;
        r->stick_ok[f] = (gl_vis_stick_refine(strip, &prior, &r->stick_work[f], s) == GL_OK);
        if (r->stick_ok[f]) {
            r->bin[c] = bins[b];
        }
    }
    if (!r->stick_ok[f]) {
        return work;
    }
    work |= GL_TRACE_STRIP_FOUND;
    if (s->width_px > GL_VIS_MIN_WINDOW_SIGMA_PX) {
        work |= GL_TRACE_STRIP_WIDE;
    }
    r->last[c] = *s;
    r->have_last[c] = true;
    if (!r->have_first[c]) {
        r->first[c] = *s;
        /* tmp is free scratch once the refinement is done (480 floats >= max(480, width)) */
        gl_vis_strip_stats(strip, r->stick_work[f].tmp, &r->stats[c]);
        r->have_first[c] = true;
        work |= GL_TRACE_STRIP_STATS;
    }
    if (c == GL_CAM_RIGHT) {
        r->n_right++;
    } else {
        const unsigned cls = (s->base <= 2u) ? (unsigned)s->base : 0u;
        r->sum_bottom[cls] += s->bottom_row;
        r->sum_bottom2[cls] += s->bottom_row * s->bottom_row;
        r->sum_bsig2[cls] += s->bottom_sigma_rows * s->bottom_sigma_rows;
        r->n_base[cls]++;
        r->sum_xref += gl_vis_stick_x_at(s, r->cand.ref_row);
        r->sum_slope += s->slope;
        r->n_left++;
        if (s->top_in_frame) {
            r->sum_top += s->top_row;
            r->n_top++;
            if (s->top_in_clutter) {
                r->n_top_clutter++;
            }
        }
        if (s->horizon_found) {
            r->sum_horizon += s->horizon_row;
            r->n_horizon_rows++;
        }
    }
    return work;
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
    /* The lowest GL_APP_SEGMENT_LENGTH_M of the stick, where it sways least.
     * If those rows are not usable in all four strips (something behind the
     * stick there), the same length further up, up to three times. */
    {
        bool ok = false;
        for (unsigned up = 0; up < 4u && !ok; up++) {
            const float hi = bot - (float)(up * nrows);
            ok = true;
            for (unsigned f = 0; f < 4u && ok; f++) {
                ok = (gl_vis_stick_segment(&r->stick_work[f], &r->stick[f], hi - (float)nrows, hi,
                                           &seg[f]) == GL_OK);
            }
        }
        if (!ok) {
            return;
        }
    }
    /* Timing: move the two LEFT positions to the mean time of the two RIGHT
     * strips along the left camera's own sway rate (see gl_read.h). */
    {
        /* frame-end times latched by the HAL, in microseconds (differences) */
        const int32_t dt_l = (int32_t)(r->t_done_us[3] - r->t_done_us[0]);
        const int32_t t_r1 = (int32_t)(r->t_done_us[1] - r->t_done_us[0]);
        const int32_t t_r2 = (int32_t)(r->t_done_us[2] - r->t_done_us[0]);
        if (r->time_correction && dt_l > 0) {
            const float row_c = 0.5f * (seg[0].row_mid + seg[3].row_mid);
            const float x0 = seg[0].x_mid + seg[0].slope * (row_c - seg[0].row_mid);
            const float x3 = seg[3].x_mid + seg[3].slope * (row_c - seg[3].row_mid);
            const float rate_px_per_us = (x3 - x0) / (float)dt_l;
            const float shift_us = 0.5f * (float)(t_r1 + t_r2) - 0.5f * (float)dt_l;
            const float delta = gl_clampf(rate_px_per_us * shift_us, -2.0f, 2.0f);
            seg[0].x_mid += delta;
            seg[3].x_mid += delta;
        }
    }
    if (gl_vis_disp_acc_add_lrrl(&r->acc, seg, &r->model[GL_CAM_LEFT], &r->model[GL_CAM_RIGHT],
                                 GL_CFG_CAM_F_PX) == GL_OK) {
        r->result.groups_ok++;
    }
}

/*
 * Is the line being followed a flagstick?  A stick of 12.7-19 mm seen with
 * a 20 mm baseline is between 0.64 and 0.95 times as wide (in pixels) as
 * its disparity, at any range: a line much wider than its disparity allows
 * is a trunk or a post far away, one much narrower is a wire close by.  The
 * width comes from the line profile's rms half-width minus the lens blur,
 * which is only known to lie in a range (PROVISIONAL), so the test catches
 * only clear cases; both bounds are evaluated in the direction that ACCEPTS.
 * A disparity that puts the line beyond the range limit is not accepted
 * either.
 */
static unsigned verdict_(const gl_read_t *r, gl_vis_disparity_t *d)
{
    const gl_vis_stick_t *fl = &r->first[GL_CAM_LEFT];
    float sp, lo, hi, w_min, w_max, tol, height_rows;

    memset(d, 0, sizeof(*d));
    if (r->n_left == 0u || !r->have_first[GL_CAM_LEFT]) {
        return V_NONE;
    }
    /* rows from the top end to the lowest point, if both are in the strip
     * (a flag hanging over the tip only shortens it by 0.4 m) */
    height_rows = fl->top_in_frame ? (fl->bottom_row - fl->top_row) : -1.0f;
    /* the LEFT camera's line: it is the one whose bearing and elevations are
     * reported (the right camera may be looking at something else, which is
     * what this test is for; a smeared LEFT window therefore fails it) */
    sp = fl->width_px;
    if (sp < 0.15f) {
        return V_BAD; /* no profile at all: an artefact at an edge, not a line */
    }
    lo = 0.90f * sp - 0.05f;
    hi = 1.15f * sp + 0.1f;
    w_min = (lo > GL_PROV_LENS_BLUR_SIGMA_MAX_PX)
                ? sqrtf(12.0f * (lo * lo - GL_PROV_LENS_BLUR_SIGMA_MAX_PX *
                                                GL_PROV_LENS_BLUR_SIGMA_MAX_PX)) : 0.0f;
    w_max = hi * hi - GL_PROV_LENS_BLUR_SIGMA_MIN_PX * GL_PROV_LENS_BLUR_SIGMA_MIN_PX;
    w_max = sqrtf(12.0f * ((w_max > 0.05f) ? w_max : 0.05f));
    /* wider than a stick at the nearest range the strips can hold (0.8 m) */
    if (w_min > GL_PROV_STICK_DIA_MAX_M * GL_CFG_CAM_F_PX / GL_APP_MIN_RANGE_M) {
        return V_BAD;
    }
    /* a flagstick is at least 60 times as tall as it is wide (1.2 m of a
     * 19 mm stick): a leg, a bollard or a sign post is not */
    if (height_rows > 0.0f && height_rows < GL_APP_STICK_MIN_ASPECT * w_min) {
        return V_BAD;
    }
    if (r->result.groups_ok == 0u || gl_vis_disp_acc_result(&r->acc, d) != GL_OK) {
        return V_LEFT;
    }
    /* a line so embedded in structure of its own strength that the flanks
     * put half a pixel on its position is not a measurement of a stick */
    if (d->sigma_static_px > GL_APP_MAX_STATIC_SIGMA_PX) {
        return V_BAD;
    }
    tol = 3.0f * sqrtf(d->sigma_px * d->sigma_px +
                       GL_PROV_STEREO_CAL_SIGMA_PX * GL_PROV_STEREO_CAL_SIGMA_PX) + 0.15f;
    if (d->disparity_px + tol < w_min * GL_CFG_CAM_BASELINE_M / GL_PROV_STICK_DIA_MAX_M ||
        d->disparity_px - tol > w_max * GL_CFG_CAM_BASELINE_M / GL_PROV_STICK_DIA_MIN_M ||
        d->disparity_px + tol < GL_CFG_CAM_F_PX * GL_CFG_CAM_BASELINE_M / GL_RANGE_MAX_M) {
        return V_BAD;
    }
    /* Height against disparity: rows / disparity = height / baseline at any
     * range.  A "stick" under 1.0 m or over 3.2 m tall is something else -
     * or the two cameras are not looking at the same line (two legs). */
    if (height_rows > 0.0f &&
        ((d->disparity_px > tol &&
          height_rows < (GL_APP_STICK_MIN_HEIGHT_M / GL_CFG_CAM_BASELINE_M) *
                            (d->disparity_px - tol)) ||
         height_rows > (GL_APP_STICK_MAX_HEIGHT_M / GL_CFG_CAM_BASELINE_M) *
                           (d->disparity_px + tol))) {
        return V_BAD;
    }
    return V_OK;
}

/* All strips of the candidate analysed: combine. */
static gl_status_t finish_(gl_read_t *r)
{
    gl_vis_stick_t *s = &r->result.stick_left;
    gl_vis_disparity_t d;
    const unsigned v = verdict_(r, &d);
    unsigned cls = 0;
    float n;

    rail_off_(r);
    if (v == V_NONE) {
        return finish_nothing_(r, GL_READ_WHY_NO_LINE, true);
    }
    if (v == V_BAD) {
        return finish_nothing_(r, GL_READ_WHY_NOT_A_STICK, false);
    }
    r->phase = (uint8_t)GL_READ_IDLE;
    r->result.tier = (uint8_t)GL_READ_TIER_LEFT;
    r->result.why = (uint8_t)((r->n_right == 0u) ? GL_READ_WHY_RIGHT_FAILED
                                                 : GL_READ_WHY_FEW_GROUPS);
    r->result.stick_found = false;
    if (v == V_OK && r->result.groups_ok >= GL_APP_MIN_GROUPS) {
        r->result.tier = (uint8_t)GL_READ_TIER_STEREO;
        r->result.why = (uint8_t)GL_READ_WHY_OK;
        r->result.stick_found = true;
        r->result.disp = d;
        /* what no number of strips averages out: the stereo calibration */
        r->result.cal_sigma_px = GL_PROV_STEREO_CAL_SIGMA_PX;
        r->result.disp.sigma_px = sqrtf(d.sigma_px * d.sigma_px +
                                        GL_PROV_STEREO_CAL_SIGMA_PX * GL_PROV_STEREO_CAL_SIGMA_PX);
    }
    /* The geometry of the stick from the LEFT camera over all its strips.
     * The base class is the one most strips agree on (a tie goes to the
     * less committal one); the lowest point is averaged over those strips,
     * and its uncertainty is the way it was found (not reduced by
     * averaging: the same in every strip) plus the scatter of the mean. */
    *s = r->first[GL_CAM_LEFT];
    for (unsigned c = 1; c < 3u; c++) {
        static const uint8_t order[3] = { GL_VIS_BASE_VISIBLE, GL_VIS_BASE_AT_HORIZON,
                                          GL_VIS_BASE_UNKNOWN };
        if (c == 1u) {
            cls = order[0];
        }
        if (r->n_base[order[c]] >= r->n_base[cls]) {
            cls = order[c];
        }
    }
    n = (float)r->n_base[cls];
    s->base = (uint8_t)cls;
    s->bottom_row = r->sum_bottom[cls] / n;
    {
        float var = r->sum_bottom2[cls] / n - s->bottom_row * s->bottom_row;
        if (var < 0.0f) {
            var = 0.0f;
        }
        s->bottom_sigma_rows = sqrtf(r->sum_bsig2[cls] / n + var / n);
        r->result.bottom_sigma_rows = s->bottom_sigma_rows;
    }
    s->slope = r->sum_slope / (float)r->n_left;
    s->row_ref = s->bottom_row;
    s->x_ref = r->sum_xref / (float)r->n_left + s->slope * (s->bottom_row - r->cand.ref_row);
    s->top_in_frame = (2u * (unsigned)r->n_top > (unsigned)r->n_left);
    s->top_in_clutter = false;
    if (s->top_in_frame) {
        s->top_row = r->sum_top / (float)r->n_top;
        s->top_in_clutter = (4u * (unsigned)r->n_top_clutter >= (unsigned)r->n_top);
    }
    s->horizon_found = (2u * (unsigned)r->n_horizon_rows > (unsigned)r->n_left);
    if (s->horizon_found) {
        s->horizon_row = r->sum_horizon / (float)r->n_horizon_rows;
    } else {
        s->base = (uint8_t)GL_VIS_BASE_UNKNOWN;
    }
    gl_vis_stick_angles(s, &r->model[GL_CAM_LEFT], r->up, &r->result.angles);
    gl_vis_quality(&r->first[GL_CAM_LEFT], r->have_first[GL_CAM_RIGHT] ? &r->first[GL_CAM_RIGHT]
                                                                       : NULL,
                   &r->stats[GL_CAM_LEFT], r->have_first[GL_CAM_RIGHT] ? &r->stats[GL_CAM_RIGHT]
                                                                       : NULL,
                   &r->result.quality);
    if (r->band.stats.sun) {
        r->result.quality.sun = true;
    }
    return GL_OK;
}

/* A candidate has had its group: note the verdict, go on to the next, or
 * choose. */
static gl_status_t probe_done_(gl_read_t *r)
{
    gl_vis_disparity_t d;
    unsigned best = 0, n_ok = 0;
    float best_rank = -1.0f;

    r->verdict[r->ci] = (uint8_t)verdict_(r, &d);
    /* stronger, and nearer the middle of the picture (the player aims) */
    r->rank[r->ci] = r->cand.score *
                     (1.25f - fabsf(r->cand.x - 0.5f * (float)(GL_OV7692_SENSOR_W - 1u)) /
                                  (0.5f * (float)GL_OV7692_SENSOR_W));
    r->cand_x[r->ci] = r->have_first[GL_CAM_LEFT]
                           ? gl_vis_stick_x_at(&r->first[GL_CAM_LEFT], r->cand.ref_row) : r->cand.x;
    r->result.n_probed++;
    if ((unsigned)r->ci + 1u < (unsigned)r->band.n_cand) {
        return start_candidate_(r, (unsigned)r->ci + 1u);
    }
    for (unsigned pass = 0; pass < 2u && best_rank < 0.0f; pass++) {
        const unsigned want = (pass == 0u) ? V_OK : V_LEFT;
        for (unsigned i = 0; i < (unsigned)r->band.n_cand; i++) {
            if (r->verdict[i] == want && r->rank[i] > best_rank) {
                best_rank = r->rank[i];
                best = i;
            }
        }
    }
    if (best_rank < 0.0f) {
        /* none is a flagstick: report the first one's reason */
        bool any_bad = false;
        for (unsigned i = 0; i < (unsigned)r->band.n_cand; i++) {
            any_bad = any_bad || (r->verdict[i] == V_BAD);
        }
        r->cand = r->band.cand[0];
        r->result.cand_score = r->cand.score;
        return finish_nothing_(r, any_bad ? GL_READ_WHY_NOT_A_STICK : GL_READ_WHY_NO_LINE,
                               !any_bad);
    }
    for (unsigned i = 0; i < (unsigned)r->band.n_cand; i++) {
        /* (two candidates that led to the same line are one object) */
        if (r->verdict[i] == V_OK && r->rank[i] >= 0.5f * best_rank &&
            (i == best || fabsf(r->cand_x[i] - r->cand_x[best]) > 3.0f)) {
            n_ok++;
        }
    }
    r->result.ambiguous = (n_ok >= 2u);
    /* a STRONGER line right beside the one taken that could not be measured
     * (two lines within each other's background) is not ruled out either */
    for (unsigned i = 0; i < (unsigned)r->band.n_cand; i++) {
        if (i != best && r->verdict[i] != V_OK &&
            r->band.cand[i].score > r->band.cand[best].score &&
            fabsf(r->band.cand[i].x - r->band.cand[best].x) < GL_APP_NEIGHBOUR_PX) {
            r->result.ambiguous = true;
        }
    }
    r->probing = false;
    return start_candidate_(r, best);
}

/* A strip of the group has been captured.  Nothing is analysed here: the
 * next strip is armed at once, so that the four exposures of the group are
 * spaced by the sensors' own frame timing (the analysis of one strip can
 * take longer than a frame on the target).  The time of each strip is the
 * frame-end time latched by the HAL in its interrupt, not the time of this
 * call. */
static gl_status_t strip_done_(gl_read_t *r)
{
    const unsigned kd = r->k;
    const unsigned f = kd & 3u;
    const bool last = !r->probing && (kd + 1u >= 4u * (unsigned)r->repeats);

    r->grp[f] = r->cur;
    r->t_done_us[f] = r->cam->last_done_us;
    if (r->result.strips_captured < 255u) {
        r->result.strips_captured++;
    }
    r->progress++;
    if (f < 3u) {
        r->k = (uint16_t)(kd + 1u);
        return start_strip_(r); /* GL_ERR_BUSY, or aborted with the rail off */
    }
    /* the group is complete */
    if (last) {
        /* every strip is in memory: the cameras are no longer needed */
        rail_off_(r);
    }
    if (r->strip_fn != NULL) {
        /* the hook (raw-strip logging) may take long: it runs only now, when
         * it can no longer disturb the spacing of the group's exposures */
        for (unsigned i = 0; i < 4u; i++) {
            r->strip_fn(r->strip_ctx, &r->grp[i], cam_of_(i), 1, (uint8_t)((kd & ~3u) + i));
        }
    }
    r->an = 0;
    r->phase = (uint8_t)GL_READ_ANALYSE;
    return GL_ERR_BUSY;
}

/* One step of the analysis of the group in memory: one strip per call, so
 * that the main loop (IMU samples: a bump must abort the read) runs in
 * between. */
static gl_status_t analyse_step_(gl_read_t *r)
{
    const unsigned group_k0 = (unsigned)r->k & ~3u;
    const bool last_group = (group_k0 + 4u >= 4u * (unsigned)r->repeats);

    if (r->an < 4u) {
        const uint32_t work = analyse_strip_(r, &r->grp[r->an], r->an, cam_of_(r->an));
        gl_hal_trace(GL_TRACE_VISION_STRIP, work);
        r->an++;
        r->progress++;
        return GL_ERR_BUSY;
    }
    group_done_(r);
    gl_hal_trace(GL_TRACE_VISION_GROUP, 0u);
    r->progress++;
    if (r->probing) {
        return probe_done_(r);
    }
    /* the first group shows no line in the left camera: there will be none
     * in the others either; do not keep the cameras on for nothing */
    if (last_group || (group_k0 == 0u && r->n_left == 0u)) {
        return finish_(r);
    }
    r->k = (uint16_t)(group_k0 + 4u);
    r->phase = (uint8_t)GL_READ_STRIPS;
    return start_strip_(r);
}

gl_status_t gl_read_step(gl_read_t *r)
{
    gl_status_t st;
    if (r->phase == (uint8_t)GL_READ_IDLE) {
        return GL_ERR_STATE;
    }
    if (r->phase == (uint8_t)GL_READ_ANALYSE) {
        return analyse_step_(r);
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
