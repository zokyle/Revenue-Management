/* gl_vision.c - flagstick detection and measurement.  See gl_vision.h. */
#include "gl_vision.h"

#include <math.h>
#include <string.h>

#define MIN_FIT_ROWS 12u
/* Smallest rms half-width of the Gaussian centroid window.  The centroid's
 * fixed point is the peak of the correlation of the SAMPLED profile with
 * the window; a line narrower than a pixel is undersampled, and a matched
 * (narrow) window lets the aliased part of its spectrum through, which
 * shows up as a bias that depends on the sub-pixel phase ("pixel locking",
 * measured 0.04-0.07 px for 0.5-1 px lines with a matched 0.7 px window and a
 * 0.6 px lens blur).  A window of at least 1.2 px attenuates the alias to
 * about 0.01 px for a noise penalty of 15-30 % on sub-pixel lines. */
#define MIN_WINDOW_SIGMA 1.2f
#define MAX_CORE 64 /* residual samples per row: 2 * flank offset - 1 <= 63 */
/* A row is rejected as an edge when |left flank - right flank| exceeds this
 * fraction of the line's peak contrast. */
#define EDGE_ASYMMETRY 0.8f
/* A fit is accepted as a stick only if the inlier rows scatter by less than
 * this about the line (unweighted rms, px).  Measured on synthetic strips:
 * 0.17-0.31 px for a 0.5-0.7 px stick at SNR 20 on a textured background
 * (the faintest usable case), 0.65-1.2 px for strips with no stick ... */
#define MAX_LINE_SCATTER_PX 0.45f
/* ... the final robust cut-off has closed to below this (px) ... */
#define MAX_FINAL_CUT_PX 1.5f
/* ... and at least this fraction of the candidate rows are inliers. */
#define MIN_INLIER_FRACTION 0.5f

static inline int px_(const gl_strip_t *s, int col, int row)
{
    return (int)s->px[(size_t)row * s->stride + (size_t)col];
}

/* ======================================================================= */
/* Noise estimate and strip statistics                                      */
/* ======================================================================= */

/* Robust pixel-noise estimate from horizontal second differences sampled
 * on a sparse grid (at most `cap` samples, median via tmp).  For white
 * noise of sigma s the second difference has sigma sqrt(6) s. */
static float noise_estimate_(const gl_strip_t *s, float *tmp, unsigned cap)
{
    const int w = (int)s->width, h = (int)s->height;
    int rstep = h / 24, cstep = (w - 2) / 19;
    unsigned n = 0;
    float med, sigma;

    if (w < 3 || h < 1 || cap == 0u) {
        return 1.0f;
    }
    if (rstep < 1) {
        rstep = 1;
    }
    if (cstep < 1) {
        cstep = 1;
    }
    for (int r = rstep / 2; r < h && n < cap; r += rstep) {
        for (int c = cstep / 2; c + 2 < w && n < cap; c += cstep) {
            int d = px_(s, c, r) - 2 * px_(s, c + 1, r) + px_(s, c + 2, r);
            tmp[n++] = (float)((d < 0) ? -d : d);
        }
    }
    if (n == 0u) {
        return 1.0f;
    }
    med = gl_median_inplace(tmp, n);
    sigma = med / (0.6745f * 2.4494897f);
    /* never below the quantisation floor of an 8-bit image */
    return (sigma < 0.5f) ? 0.5f : sigma;
}

void gl_vis_strip_stats(const gl_strip_t *s, float *scratch, gl_vis_stats_t *out)
{
    const int w = (int)s->width, h = (int)s->height;
    uint32_t sum = 0, sat = 0;
    unsigned run_cols = 0;

    out->sun = false;
    for (int c = 0; c < w; c++) {
        unsigned run = 0, max_run = 0;
        for (int r = 0; r < h; r++) {
            int v = px_(s, c, r);
            sum += (uint32_t)v;
            if (v >= (int)GL_VIS_SAT_LEVEL) {
                sat++;
                run++;
                if (run > max_run) {
                    max_run = run;
                }
            } else {
                run = 0;
            }
        }
        /* a blob: enough adjacent columns each with a long saturated run */
        if (max_run >= GL_VIS_SUN_MIN_PX) {
            run_cols++;
            if (run_cols >= GL_VIS_SUN_MIN_PX) {
                out->sun = true;
            }
        } else {
            run_cols = 0;
        }
    }
    if (w > 0 && h > 0) {
        out->mean = (float)sum / ((float)w * (float)h);
        out->sat_fraction = (float)sat / ((float)w * (float)h);
    } else {
        out->mean = 0.0f;
        out->sat_fraction = 0.0f;
    }
    out->noise_sigma = noise_estimate_(s, scratch, 480u);
}

/* ======================================================================= */
/* Horizon band                                                             */
/* ======================================================================= */

static const uint8_t band_core_[GL_VIS_BAND_SCALES] = { 1, 3, 7, 13 };
static const uint8_t band_flank_[GL_VIS_BAND_SCALES] = { 2, 3, 5, 7 };
static const uint8_t band_gap_[GL_VIS_BAND_SCALES] = { 1, 1, 2, 2 };

/* Turf-horizon sample of one column bin: strongest horizontal edge. */
static bool horizon_bin_(const gl_strip_t *band, int col0, int ncols, int rows, float *row_out)
{
    float p[GL_VIS_BAND_MAX_BLOCKS * GL_VIS_BAND_BLOCK_ROWS];
    float best = 0.0f, other = 0.0f;
    int best_r = -1, n_other = 0;
    float dm, dp, d0, off, strength;

    for (int r = 0; r < rows; r++) {
        int acc = 0;
        for (int c = col0; c < col0 + ncols; c++) {
            acc += px_(band, c, r);
        }
        p[r] = (float)acc / (float)ncols;
    }
    /* d[r] = (p[r+1] + p[r+2]) - (p[r-1] + p[r-2]) */
    for (int r = 2; r + 2 < rows; r++) {
        float d = fabsf((p[r + 1] + p[r + 2]) - (p[r - 1] + p[r - 2]));
        if (d > best) {
            best = d;
            best_r = r;
        }
    }
    if (best_r < 3 || best_r + 3 >= rows) {
        return false;
    }
    for (int r = 2; r + 2 < rows; r++) {
        if (r < best_r - 4 || r > best_r + 4) {
            other += fabsf((p[r + 1] + p[r + 2]) - (p[r - 1] + p[r - 2]));
            n_other++;
        }
    }
    strength = 0.5f * best; /* grey-level step */
    if (n_other > 0) {
        other = 0.5f * other / (float)n_other;
    }
    if (strength < 3.0f || strength < 4.0f * other) {
        return false;
    }
    /* sub-row position: parabola through the three responses around the peak */
    d0 = best;
    dm = fabsf((p[best_r] + p[best_r + 1]) - (p[best_r - 2] + p[best_r - 3]));
    dp = fabsf((p[best_r + 2] + p[best_r + 3]) - (p[best_r] + p[best_r - 1]));
    off = 0.0f;
    if (d0 - 0.5f * (dm + dp) > 1e-6f) {
        off = 0.25f * (dp - dm) / (d0 - 0.5f * (dm + dp));
        off = gl_clampf(off, -0.5f, 0.5f);
    }
    *row_out = (float)best_r + off;
    return true;
}

gl_status_t gl_vis_band_analyse(const gl_strip_t *band, gl_vis_band_work_t *work,
                                gl_vis_band_result_t *out)
{
    int w, nb, rows;

    if (band == NULL || work == NULL || out == NULL || band->px == NULL) {
        return GL_ERR_PARAM;
    }
    memset(out, 0, sizeof(*out));
    w = (int)band->width;
    nb = (int)(band->height / GL_VIS_BAND_BLOCK_ROWS);
    if (nb > (int)GL_VIS_BAND_MAX_BLOCKS) {
        nb = (int)GL_VIS_BAND_MAX_BLOCKS;
    }
    if (w < 64 || w > (int)GL_VIS_BAND_MAX_W || nb < 2 || band->stride < band->width) {
        return GL_ERR_PARAM;
    }
    rows = nb * (int)GL_VIS_BAND_BLOCK_ROWS;

    /* --- statistics (work->score is free at this point: use it as scratch) --- */
    gl_vis_strip_stats(band, work->score, &out->stats);

    /* --- block sums and per-column vertical-edge energy --- */
    {
        uint32_t esum = 0;
        for (int x = 0; x < w; x++) {
            uint32_t e = 0;
            for (int b = 0; b < nb; b++) {
                int acc = 0;
                for (int r = b * (int)GL_VIS_BAND_BLOCK_ROWS;
                     r < (b + 1) * (int)GL_VIS_BAND_BLOCK_ROWS; r++) {
                    acc += px_(band, x, r);
                    if (x > 0 && x + 1 < w) {
                        int d = px_(band, x + 1, r) - px_(band, x - 1, r);
                        e += (uint32_t)((d < 0) ? -d : d);
                    }
                }
                work->block[b][x] = (int16_t)acc;
            }
            work->edge_energy[x] = (uint16_t)((e > 65535u) ? 65535u : e);
            esum += e;
            work->score[x] = 0.0f;
            work->best_slant[x] = 0;
            work->best_scale[x] = 0;
            work->best_blocks[x] = 0;
            work->best_pol[x] = 0;
        }
        out->edge_energy_mean = (float)esum / (float)w;
    }

    /* --- matched vertical-line detector --- */
    for (unsigned si = 0; si < GL_VIS_BAND_SCALES; si++) {
        const int core = band_core_[si], flank = band_flank_[si], gap = band_gap_[si];
        const int half = (core - 1) / 2;
        const int margin = half + gap + flank;
        const float kcore = 1.0f / ((float)core * (float)GL_VIS_BAND_BLOCK_ROWS);
        const float kflank = 0.5f / ((float)flank * (float)GL_VIS_BAND_BLOCK_ROWS);
        float inv_norm[GL_VIS_BAND_MAX_BLOCKS + 1];
        float cumvar = 0.0f;

        inv_norm[0] = 0.0f;
        for (int b = 0; b < nb; b++) {
            const int16_t *blk = work->block[b];
            float *rg = work->ridge[b];
            float mad = 0.0f, sigma;
            int n = 0;
            for (int x = 0; x < w; x++) {
                rg[x] = 0.0f;
            }
            for (int x = margin; x < w - margin; x++) {
                int c = 0, f = 0;
                for (int k = -half; k <= half; k++) {
                    c += blk[x + k];
                }
                for (int k = 0; k < flank; k++) {
                    f += blk[x - half - gap - 1 - k] + blk[x + half + gap + 1 + k];
                }
                rg[x] = (float)c * kcore - (float)f * kflank; /* grey levels */
                mad += fabsf(rg[x]);
                n++;
            }
            /* mean absolute value -> sigma of a zero-mean Gaussian */
            sigma = (n > 0) ? (1.2533141f * mad / (float)n) : 1.0f;
            if (sigma < 0.02f) {
                sigma = 0.02f;
            }
            cumvar += sigma * sigma;
            inv_norm[b + 1] = 1.0f / sqrtf(cumvar);
        }

        for (unsigned ji = 0; ji < GL_VIS_BAND_SLANTS; ji++) {
            const float slant = tanf(((float)ji - 6.0f) * 0.5f * GL_DEG2RAD_F);
            const float shift = slant * (float)GL_VIS_BAND_BLOCK_ROWS; /* px per block */
            const int pad = margin + 7; /* total shift over 8 blocks is at most 5 px */
            for (int x = pad; x < w - pad; x++) {
                float s = 0.0f;
                for (int b = 0; b < nb; b++) {
                    float xs = (float)x + shift * (float)b;
                    int i0 = (int)floorf(xs);
                    float fr = xs - (float)i0;
                    const float *rg = work->ridge[b];
                    s += rg[i0] + (rg[i0 + 1] - rg[i0]) * fr;
                    if (b >= 1) {
                        float z = fabsf(s) * inv_norm[b + 1];
                        if (z > work->score[x]) {
                            work->score[x] = z;
                            work->best_slant[x] = (uint8_t)ji;
                            work->best_scale[x] = (uint8_t)si;
                            work->best_blocks[x] = (uint8_t)(b + 1);
                            work->best_pol[x] = (int8_t)((s >= 0.0f) ? 1 : -1);
                        }
                    }
                }
            }
        }
    }

    /* --- candidates: strongest local maxima, non-maximum suppression --- */
    while (out->n_cand < GL_VIS_MAX_CANDIDATES) {
        int best_x = -1;
        float best = GL_VIS_BAND_MIN_SCORE;
        gl_vis_candidate_t *c;
        float off = 0.0f;
        int excl;

        for (int x = 1; x < w - 1; x++) {
            if (work->score[x] > best) {
                best = work->score[x];
                best_x = x;
            }
        }
        if (best_x < 0) {
            break;
        }
        {
            float sm = work->score[best_x - 1], sp = work->score[best_x + 1];
            float den = best - 0.5f * (sm + sp);
            if (den > 1e-6f) {
                off = gl_clampf(0.25f * (sp - sm) / den, -0.5f, 0.5f);
            }
        }
        c = &out->cand[out->n_cand++];
        c->x = (float)band->x0 + (float)best_x + off;
        c->ref_row = (float)band->y0 + 0.5f * ((float)GL_VIS_BAND_BLOCK_ROWS - 1.0f);
        c->slant = tanf(((float)work->best_slant[best_x] - 6.0f) * 0.5f * GL_DEG2RAD_F);
        c->score = best;
        c->width_px = (float)band_core_[work->best_scale[best_x]];
        c->polarity = work->best_pol[best_x];
        c->rows = (uint8_t)(work->best_blocks[best_x] * GL_VIS_BAND_BLOCK_ROWS);
        /* Suppress the whole neighbourhood: a strong narrow line also
         * shows up, with opposite sign, in the FLANKS of the widest
         * template (reach 6 + 2 + 7 px). */
        excl = 24;
        for (int x = best_x - excl; x <= best_x + excl; x++) {
            if (x >= 0 && x < w) {
                work->score[x] = 0.0f;
            }
        }
    }

    /* --- turf-horizon samples --- */
    {
        const int binw = w / (int)GL_VIS_HORIZON_BINS;
        for (unsigned i = 0; i < GL_VIS_HORIZON_BINS; i++) {
            float row = 0.0f;
            out->horizon_col[i] = (float)band->x0 + ((float)i + 0.5f) * (float)binw - 0.5f;
            out->horizon_row[i] = 0.0f;
            if (binw >= 2 && horizon_bin_(band, (int)i * binw, binw, rows, &row)) {
                out->horizon_row[i] = (float)band->y0 + row;
                out->horizon_valid |= (uint32_t)1u << i;
            }
        }
    }
    return (out->n_cand > 0u) ? GL_OK : GL_ERR_NO_STICK;
}

/* ======================================================================= */
/* Row measurement                                                          */
/* ======================================================================= */

typedef struct {
    float x;     /* centroid, strip column */
    float var;   /* variance of x, px^2 */
    float flux;  /* |sum of residual over the core|, grey x px */
    float m2;    /* profile variance estimate, px^2 */
    float peak;  /* largest residual, grey */
    int pol;     /* +1 / -1 */
} row_meas_t;

/* Geometry of the row template for a line of rms half-width s_w. */
static void row_geom_(float s_w, int *core_h, int *flank_off)
{
    int g = (int)ceilf(2.5f * s_w + 1.5f);
    if (g > MAX_CORE / 2) {
        g = MAX_CORE / 2;
    }
    *flank_off = g;
    *core_h = (int)(s_w + 0.5f);
}

#define FLANK_W 4

/* Signed line flux at a FIXED integer centre c (forced photometry): sum of
 * (I - linear background) over the core.  Returns false if the template
 * does not fit in the row. */
static bool row_flux_at_(const uint8_t *rowp, int width, int c, int g, float *flux, float *left,
                         float *right)
{
    int l = 0, r = 0, core = 0;
    float lm, rm;
    if (c - g - FLANK_W + 1 < 0 || c + g + FLANK_W - 1 >= width) {
        return false;
    }
    for (int k = 0; k < FLANK_W; k++) {
        l += rowp[c - g - k];
        r += rowp[c + g + k];
    }
    for (int k = -(g - 1); k <= g - 1; k++) {
        core += rowp[c + k];
    }
    lm = (float)l / (float)FLANK_W;
    rm = (float)r / (float)FLANK_W;
    /* the linear background integrates to its mean over the symmetric core */
    *flux = (float)core - (float)(2 * g - 1) * 0.5f * (lm + rm);
    *left = lm;
    *right = rm;
    return true;
}

/* Measure the line on one row near the predicted column xp.  Returns false
 * if no significant line is found within +-search. */
static bool measure_row_(const uint8_t *rowp, int width, float xp, float search, float s_w,
                         float noise, row_meas_t *m)
{
    int h, g, c_lo, c_hi, best_c = -1;
    float best_rr = 0.0f, best_l = 0.0f, best_r = 0.0f;
    float p[MAX_CORE];
    float xc, relax = 1.0f, den = 0.0f, var_w = 0.0f, flux = 0.0f, peak = 0.0f;
    const float inv2s2 = 0.5f / (s_w * s_w);
    int n;

    row_geom_(s_w, &h, &g);
    c_lo = (int)ceilf(xp - search);
    c_hi = (int)floorf(xp + search);
    if (c_lo < g + FLANK_W - 1) {
        c_lo = g + FLANK_W - 1;
    }
    if (c_hi > width - g - FLANK_W) {
        c_hi = width - g - FLANK_W;
    }
    /* 1. coarse position: strongest centre-minus-flanks response */
    for (int c = c_lo; c <= c_hi; c++) {
        int core = 0, l = 0, r = 0;
        float rr, lm, rm;
        for (int k = -h; k <= h; k++) {
            core += rowp[c + k];
        }
        for (int k = 0; k < FLANK_W; k++) {
            l += rowp[c - g - k];
            r += rowp[c + g + k];
        }
        lm = (float)l / (float)FLANK_W;
        rm = (float)r / (float)FLANK_W;
        rr = (float)core / (float)(2 * h + 1) - 0.5f * (lm + rm);
        if (fabsf(rr) > fabsf(best_rr)) {
            best_rr = rr;
            best_c = c;
            best_l = lm;
            best_r = rm;
        }
    }
    if (best_c < 0) {
        return false;
    }
    m->pol = (best_rr >= 0.0f) ? 1 : -1;

    /* 2. residual over the core after removing a linear background between
     *    the two flank means (flank centres at +-(g + 1.5) from best_c) */
    n = 2 * g - 1;
    {
        const float span = 2.0f * ((float)g + 0.5f * (float)(FLANK_W - 1));
        const float grad = (best_r - best_l) / span;
        const float mid = 0.5f * (best_l + best_r);
        for (int i = 0; i < n; i++) {
            int k = i - (g - 1);
            float v = ((float)rowp[best_c + k] - (mid + grad * (float)k)) * (float)m->pol;
            p[i] = v;
            flux += v;
            if (v > peak) {
                peak = v;
            }
        }
    }
    /* significance of the line on this row */
    if (flux < 3.0f * noise * sqrtf((float)n)) {
        return false;
    }
    /* A line has the same background on both sides.  If the two flanks
     * differ by about as much as the "line" stands out, this is the edge of
     * something wide (a person, a wall, a tree trunk), not a stick. */
    if (fabsf(best_r - best_l) > EDGE_ASYMMETRY * peak) {
        return false;
    }

    /* 3. iterated Gaussian-weighted centroid.  One step moves the estimate
     *    only part of the way (the window pulls it back toward its own
     *    centre); the gain needed to reach the fixed point in one step is
     *    s_w^2 / (s_w^2 - v) with v the weighted second moment, measured on
     *    the fly, so narrow and wide profiles both converge. */
    xc = 0.0f; /* relative to best_c */
    for (int it = 0; it < 6; it++) {
        float s0 = 0.0f, s1 = 0.0f, s2 = 0.0f, sg2 = 0.0f, step, v;
        for (int i = 0; i < n; i++) {
            float d = (float)(i - (g - 1)) - xc;
            float wgt = expf(-d * d * inv2s2);
            float wp = wgt * p[i];
            s0 += wp;
            s1 += wp * d;
            s2 += wp * d * d;
            sg2 += wgt * wgt * d * d;
        }
        if (!(s0 > 0.0f)) {
            return false;
        }
        step = s1 / s0;
        v = s2 / s0 - step * step;
        if (v < 0.0f) {
            v = 0.0f;
        }
        relax = (v < 0.75f * s_w * s_w) ? (s_w * s_w / (s_w * s_w - v)) : 4.0f;
        den = s0;
        var_w = sg2;
        m->m2 = (v < 0.9f * s_w * s_w) ? (v * s_w * s_w / (s_w * s_w - v)) : (9.0f * s_w * s_w);
        xc += relax * step;
        if (fabsf(xc) > (float)g - 1.0f) {
            return false; /* ran away: not a compact line */
        }
        if (fabsf(relax * step) < 0.002f) {
            break;
        }
    }
    m->x = (float)best_c + xc;
    if (fabsf(m->x - xp) > search + 1.0f) {
        return false;
    }
    /* variance of the fixed point: single-step noise times the same gain */
    m->var = relax * relax * noise * noise * var_w / (den * den);
    if (m->var < 1e-6f) {
        m->var = 1e-6f;
    }
    m->flux = flux;
    m->peak = peak;
    return true;
}

/* ======================================================================= */
/* Robust line fit                                                          */
/* ======================================================================= */

typedef struct {
    float a, b, rc; /* x = a + b * (row - rc), strip coordinates */
} line_t;

static float line_at_(const line_t *l, float row)
{
    return l->a + l->b * (row - l->rc);
}

/* One iteratively-reweighted step with Tukey cut-off c (px).  Candidate
 * rows are MEASURED and not WIDE.  Returns the number of rows with
 * non-zero weight; the line is updated only if that is >= 3. */
static unsigned irls_step_(gl_vis_stick_work_t *wk, int rows, line_t *l, float c)
{
    float sw = 0.0f, swy = 0.0f, swx = 0.0f;
    float syy = 0.0f, sxy = 0.0f, ybar, xbar;
    unsigned n = 0;

    for (int r = 0; r < rows; r++) {
        if ((wk->flag[r] & (GL_VIS_ROW_MEASURED | GL_VIS_ROW_WIDE)) == GL_VIS_ROW_MEASURED) {
            float res = (wk->x[r] - line_at_(l, (float)r)) / c;
            if (fabsf(res) < 1.0f) {
                float t = 1.0f - res * res;
                float w = wk->w[r] * t * t;
                sw += w;
                swy += w * (float)r;
                swx += w * wk->x[r];
                n++;
            }
        }
    }
    if (n < 3u || !(sw > 0.0f)) {
        return n;
    }
    ybar = swy / sw;
    xbar = swx / sw;
    for (int r = 0; r < rows; r++) {
        if ((wk->flag[r] & (GL_VIS_ROW_MEASURED | GL_VIS_ROW_WIDE)) == GL_VIS_ROW_MEASURED) {
            float res = (wk->x[r] - line_at_(l, (float)r)) / c;
            if (fabsf(res) < 1.0f) {
                float t = 1.0f - res * res;
                float w = wk->w[r] * t * t;
                float dy = (float)r - ybar;
                syy += w * dy * dy;
                sxy += w * dy * (wk->x[r] - xbar);
            }
        }
    }
    l->rc = ybar;
    l->a = xbar;
    if (syy > 1e-6f) {
        l->b = sxy / syy;
    }
    return n;
}

/* Tukey cut-off from the data: 4.685 * 1.4826 * median |residual| over the
 * rows currently inside the cut-off c_prev, floored. */
static float robust_cut_(gl_vis_stick_work_t *wk, int rows, const line_t *l, float c_prev)
{
    unsigned n = 0;
    float med;
    for (int r = 0; r < rows; r++) {
        if ((wk->flag[r] & (GL_VIS_ROW_MEASURED | GL_VIS_ROW_WIDE)) == GL_VIS_ROW_MEASURED) {
            float res = fabsf(wk->x[r] - line_at_(l, (float)r));
            if (res < c_prev) {
                wk->tmp[n++] = res;
            }
        }
    }
    if (n < 3u) {
        return c_prev;
    }
    med = gl_median_inplace(wk->tmp, n);
    return gl_clampf(4.685f * 1.4826f * med, 0.30f, c_prev);
}

/* Flag rows that are much brighter or wider than the typical stick row. */
static void flag_wide_(gl_vis_stick_work_t *wk, int rows)
{
    unsigned n = 0;
    float med_flux, med_m2;
    for (int r = 0; r < rows; r++) {
        if ((wk->flag[r] & GL_VIS_ROW_MEASURED) != 0u) {
            wk->tmp[n++] = wk->flux[r];
        }
    }
    if (n < 5u) {
        return;
    }
    med_flux = gl_median_inplace(wk->tmp, n);
    n = 0;
    for (int r = 0; r < rows; r++) {
        if ((wk->flag[r] & GL_VIS_ROW_MEASURED) != 0u) {
            wk->tmp[n++] = wk->m2[r];
        }
    }
    med_m2 = gl_median_inplace(wk->tmp, n);
    for (int r = 0; r < rows; r++) {
        if ((wk->flag[r] & GL_VIS_ROW_MEASURED) != 0u) {
            float lim_m2 = 3.0f * med_m2;
            if (lim_m2 < med_m2 + 1.0f) {
                lim_m2 = med_m2 + 1.0f;
            }
            if (wk->flux[r] > 3.0f * med_flux || wk->m2[r] > lim_m2) {
                wk->flag[r] |= GL_VIS_ROW_WIDE;
            }
        }
    }
}

/* Measure every row along a predicted line. */
static unsigned measure_all_(const gl_strip_t *s, gl_vis_stick_work_t *wk, const line_t *l,
                             float search, float s_w, float noise)
{
    const int rows = (int)s->height, w = (int)s->width;
    unsigned n = 0;
    for (int r = 0; r < rows; r++) {
        row_meas_t m;
        float xp = line_at_(l, (float)r);
        wk->flag[r] = 0;
        wk->w[r] = 0.0f;
        wk->x[r] = xp;
        wk->flux[r] = 0.0f;
        wk->m2[r] = 0.0f;
        wk->peak[r] = 0;
        if (!(xp >= 0.0f && xp <= (float)(w - 1))) {
            continue; /* outside the strip (or not a number) */
        }
        if (measure_row_(&s->px[(size_t)r * s->stride], w, xp, search, s_w, noise, &m)) {
            wk->x[r] = m.x;
            wk->w[r] = 1.0f / m.var;
            wk->flux[r] = m.flux;
            wk->m2[r] = m.m2;
            wk->peak[r] = (uint8_t)((m.peak > 255.0f) ? 255.0f : m.peak);
            wk->flag[r] = (uint8_t)(GL_VIS_ROW_MEASURED | ((m.pol < 0) ? GL_VIS_ROW_NEG : 0u));
            n++;
        }
    }
    return n;
}

/* ======================================================================= */
/* Extent: top, bottom, local horizon                                       */
/* ======================================================================= */

#define ROW_FORCED (1u << 5) /* internal: wk->flux[r] holds a forced line amplitude */

/* Forced photometry on one row: amplitude (grey levels) of the best-fitting
 * Gaussian line of rms half-width s_w centred at column xline, after
 * removing the linear background between the flanks.  Signed: positive for
 * bright-on-dark. */
static bool row_amp_at_(const uint8_t *rowp, int width, float xline, int g, float s_w, float *amp,
                        float *background)
{
    const int c = gl_roundi(gl_clampf(xline, -1000.0f, 1000.0f));
    const float dx = xline - (float)c;
    const float inv2s2 = 0.5f / (s_w * s_w);
    float lm, rm, f, mid, grad, num = 0.0f, den = 0.0f;
    if (!row_flux_at_(rowp, width, c, g, &f, &lm, &rm)) {
        return false;
    }
    mid = 0.5f * (lm + rm);
    grad = (rm - lm) / (2.0f * ((float)g + 0.5f * (float)(FLANK_W - 1)));
    for (int k = -(g - 1); k <= g - 1; k++) {
        float d = (float)k - dx;
        float wgt = expf(-d * d * inv2s2);
        num += wgt * ((float)rowp[c + k] - (mid + grad * (float)k));
        den += wgt * wgt;
    }
    *amp = num / den;
    *background = mid;
    return true;
}

/* Forced amplitude along the fitted line on every row -> wk->flux, and the
 * local background level of the row -> wk->m2 (these replace the per-row
 * measured flux and second moment, which are no longer needed). */
static void forced_amp_(const gl_strip_t *s, gl_vis_stick_work_t *wk, const line_t *l, int g,
                        float s_w)
{
    const int rows = (int)s->height, w = (int)s->width;
    for (int r = 0; r < rows; r++) {
        float a = 0.0f, bg = 0.0f;
        if (row_amp_at_(&s->px[(size_t)r * s->stride], w, line_at_(l, (float)r), g, s_w, &a,
                        &bg)) {
            wk->flux[r] = a;
            wk->m2[r] = bg;
            wk->flag[r] |= (uint8_t)ROW_FORCED;
        } else {
            wk->flux[r] = 0.0f;
            wk->m2[r] = 0.0f;
        }
    }
}

/*
 * Locate one end of the line as a change point of the forced amplitude:
 * walking from row `mid` in direction `dir`, the running sum of
 * (|A| - ref / 2) is largest at the row where the amplitude drops from
 * "about ref" to "about zero" (the maximum-likelihood step position for a
 * known step height; a few weak rows inside the stick do not matter).
 * The position is then refined below one row from the partial coverage of
 * the three rows either side of the step, measured against the amplitude
 * of the rows right next to the end (the stick's contrast changes where
 * its background changes, e.g. from far scenery to turf).
 *
 * Known limitation: if the background changes within about one row of the
 * end itself (stick base exactly at the turf horizon), the partially
 * covered row is seen with a different contrast than the reference rows
 * and the result is off by up to about 0.4 row.
 *
 * Returns 1 = found (*row_out sub-row end, *edge_out first row beyond the
 * end), 0 = the line continues to the edge of the strip, -1 = unusable.
 */
static int find_end_(gl_vis_stick_work_t *wk, int rows, int mid, int dir, float ref_global,
                     float amp_noise, float bg_tol, float *row_out, int *edge_out)
{
    float ref = ref_global;
    float c = 0.0f, best = 0.0f;
    float pol_sum = 0.0f, sum_out = 0.0f, sum_in = 0.0f, pol;
    unsigned n = 0;
    int e = mid, r;

    if (!(ref > 3.0f * amp_noise)) {
        return -1; /* too faint to tell where it ends */
    }
    for (r = mid; r >= 0 && r < rows; r += dir) {
        if ((wk->flag[r] & ROW_FORCED) == 0u) {
            break;
        }
        c += fabsf(wk->flux[r]) - 0.5f * ref;
        if (c > best) {
            best = c;
            e = r + dir;
        }
    }
    if (dir * (r - e) <= 2) {
        return 0; /* still present where the strip (or its side) ends */
    }
    /* Local reference: fully covered rows near the end that have the SAME
     * background as the row just beyond the end (wk->m2 holds the row
     * background), so that a stick whose last rows stand in front of turf
     * is compared with its contrast against turf.  Fall back to the six
     * nearest rows if fewer than two qualify. */
    if (e >= 0 && e < rows && (wk->flag[e] & ROW_FORCED) != 0u) {
        const float bg_end = wk->m2[e];
        for (int k = 2; k <= 12 && n < 6u; k++) {
            int rr = e - dir * k;
            if (rr >= 0 && rr < rows && (wk->flag[rr] & ROW_FORCED) != 0u &&
                fabsf(wk->m2[rr] - bg_end) <= bg_tol) {
                wk->tmp[n++] = fabsf(wk->flux[rr]);
            }
        }
    }
    if (n < 2u) {
        n = 0;
        for (int k = 2; k <= 7; k++) {
            int rr = e - dir * k;
            if (rr >= 0 && rr < rows && (wk->flag[rr] & ROW_FORCED) != 0u) {
                wk->tmp[n++] = fabsf(wk->flux[rr]);
            }
        }
    }
    if (n >= 2u) {
        float local = gl_median_inplace(wk->tmp, n);
        if (local > 3.0f * amp_noise) {
            ref = local;
        }
    }
    for (int k = 1; k <= 3; k++) {
        int rr = e - dir * k;
        if (rr >= 0 && rr < rows) {
            pol_sum += wk->flux[rr];
        }
    }
    pol = (pol_sum >= 0.0f) ? 1.0f : -1.0f;
    for (int k = 0; k < 3; k++) {
        int ro = e + dir * k;       /* rows beyond the step */
        int ri = e - dir * (k + 1); /* rows inside */
        if (ro >= 0 && ro < rows && (wk->flag[ro] & ROW_FORCED) != 0u) {
            sum_out += gl_clampf(pol * wk->flux[ro] / ref, 0.0f, 1.0f);
        }
        if (ri >= 0 && ri < rows && (wk->flag[ri] & ROW_FORCED) != 0u) {
            sum_in += 1.0f - gl_clampf(pol * wk->flux[ri] / ref, 0.0f, 1.0f);
        }
    }
    /* the step lies between rows e - dir and e, shifted by the net partial
     * coverage (clipping errors on the two sides cancel on average) */
    *row_out = (float)e - 0.5f * (float)dir + (float)dir * (sum_out - sum_in);
    *edge_out = e;
    return 1;
}

/* Local turf horizon beside the stick near strip row `near`: strongest
 * horizontal edge of the flank columns within +-40 rows. */
static bool local_horizon_(const gl_strip_t *s, gl_vis_stick_work_t *wk, const line_t *l,
                           int near, float noise, float *row_out)
{
    const int rows = (int)s->height, w = (int)s->width;
    const int xc = gl_roundi(line_at_(l, (float)near));
    int r0 = near - 40, r1 = near + 40;
    int ncols = 0, best_r = -1;
    float best = 0.0f, other = 0.0f;
    int n_other = 0;
    float *p = wk->tmp;

    if (r0 < 0) {
        r0 = 0;
    }
    if (r1 > rows - 1) {
        r1 = rows - 1;
    }
    if (r1 - r0 < 8) {
        return false;
    }
    for (int r = r0; r <= r1; r++) {
        int acc = 0;
        ncols = 0;
        for (int c = xc - 26; c <= xc + 26; c++) {
            if ((c <= xc - 8 || c >= xc + 8) && c >= 0 && c < w) {
                acc += px_(s, c, r);
                ncols++;
            }
        }
        if (ncols < 8) {
            return false;
        }
        p[r] = (float)acc / (float)ncols;
    }
    for (int r = r0 + 2; r + 2 <= r1; r++) {
        float d = fabsf((p[r + 1] + p[r + 2]) - (p[r - 1] + p[r - 2]));
        if (d > best) {
            best = d;
            best_r = r;
        }
    }
    if (best_r < r0 + 3 || best_r + 3 > r1) {
        return false;
    }
    for (int r = r0 + 2; r + 2 <= r1; r++) {
        if (r < best_r - 4 || r > best_r + 4) {
            other += fabsf((p[r + 1] + p[r + 2]) - (p[r - 1] + p[r - 2]));
            n_other++;
        }
    }
    if (n_other > 0) {
        other /= (float)n_other;
    }
    /* a grey step of at least 3 levels, clear of noise and of the other rows */
    if (0.5f * best < 3.0f || 0.5f * best < 6.0f * noise / sqrtf((float)ncols) ||
        best < 4.0f * other) {
        return false;
    }
    {
        float dm = fabsf((p[best_r] + p[best_r + 1]) - (p[best_r - 2] + p[best_r - 3]));
        float dp = fabsf((p[best_r + 2] + p[best_r + 3]) - (p[best_r] + p[best_r - 1]));
        float den = best - 0.5f * (dm + dp);
        float off = (den > 1e-6f) ? gl_clampf(0.25f * (dp - dm) / den, -0.5f, 0.5f) : 0.0f;
        /* for an edge between rows k and k + 1 the response has a two-row
         * plateau at k and k + 1 and the parabola peaks at k + 0.5 */
        *row_out = (float)best_r + off;
    }
    return true;
}

/* ======================================================================= */
/* Stick refinement                                                         */
/* ======================================================================= */

gl_status_t gl_vis_stick_refine(const gl_strip_t *strip, const gl_vis_prior_t *prior,
                                gl_vis_stick_work_t *wk, gl_vis_stick_t *out)
{
    int rows, w, g, core_h;
    float noise, s_w, search, cut;
    line_t line;
    unsigned n_meas, n_in = 0;
    int bot_idx, top_idx;
    bool bottom_known = false;
    float sw = 0.0f, syy = 0.0f, sres = 0.0f, sres_unw = 0.0f, chi = 1.0f, pol_sum = 0.0f;

    if (strip == NULL || prior == NULL || wk == NULL || out == NULL || strip->px == NULL) {
        return GL_ERR_PARAM;
    }
    memset(out, 0, sizeof(*out));
    rows = (int)strip->height;
    w = (int)strip->width;
    if (rows < 32 || rows > (int)GL_VIS_STRIP_MAX_H || w < 24 || w > (int)GL_VIS_STRIP_MAX_W ||
        strip->stride < strip->width || !isfinite(prior->x) || !isfinite(prior->row) ||
        !isfinite(prior->slant) || !isfinite(prior->width_px) || !isfinite(prior->search_px) ||
        fabsf(prior->slant) > 0.2f) {
        return GL_ERR_PARAM;
    }
    out->x0 = strip->x0;
    out->y0 = strip->y0;
    out->strip_rows = strip->height;

    noise = noise_estimate_(strip, wk->tmp, GL_VIS_STRIP_MAX_H);
    out->noise_sigma = noise;
    {
        float wpx = (prior->width_px > 0.0f) ? prior->width_px : 1.5f;
        s_w = gl_clampf(sqrtf(wpx * wpx / 12.0f + 0.45f), MIN_WINDOW_SIGMA, 5.0f);
    }
    search = (prior->search_px > 0.0f) ? prior->search_px : 6.0f;

    /* prior line in strip coordinates */
    line.rc = 0.5f * (float)(rows - 1);
    line.b = prior->slant;
    line.a = (prior->x - (float)strip->x0) +
             prior->slant * (((float)strip->y0 + line.rc) - prior->row);

    /* ---- pass A: wide search along the prior ---- */
    n_meas = measure_all_(strip, wk, &line, search, s_w, noise);
    if (n_meas < MIN_FIT_ROWS) {
        out->rows_measured = (uint16_t)n_meas;
        return GL_ERR_NO_STICK;
    }
    flag_wide_(wk, rows);
    cut = (search > 2.0f) ? search : 2.0f;
    (void)irls_step_(wk, rows, &line, cut);
    (void)irls_step_(wk, rows, &line, cut);
    (void)irls_step_(wk, rows, &line, 1.5f);
    cut = 1.5f;
    for (int it = 0; it < 4; it++) {
        cut = robust_cut_(wk, rows, &line, cut);
        n_in = irls_step_(wk, rows, &line, cut);
    }
    if (n_in < MIN_FIT_ROWS || fabsf(line.b) > 0.15f) {
        out->rows_measured = (uint16_t)n_meas;
        out->rows_used = (uint16_t)n_in;
        return GL_ERR_NO_STICK;
    }

    /* ---- pass B: re-measure along the fit with a matched window ---- */
    {
        unsigned n = 0;
        for (int r = 0; r < rows; r++) {
            if ((wk->flag[r] & (GL_VIS_ROW_MEASURED | GL_VIS_ROW_WIDE)) == GL_VIS_ROW_MEASURED &&
                fabsf(wk->x[r] - line_at_(&line, (float)r)) < cut) {
                wk->tmp[n++] = wk->m2[r];
            }
        }
        if (n >= 3u) {
            s_w = gl_clampf(sqrtf(gl_median_inplace(wk->tmp, n)), MIN_WINDOW_SIGMA, 6.0f);
        }
    }
    search = (s_w > 1.5f) ? s_w : 1.5f;
    n_meas = measure_all_(strip, wk, &line, search, s_w, noise);
    if (n_meas < MIN_FIT_ROWS) {
        out->rows_measured = (uint16_t)n_meas;
        return GL_ERR_NO_STICK;
    }
    flag_wide_(wk, rows);
    cut = search;
    for (int it = 0; it < 5; it++) {
        cut = robust_cut_(wk, rows, &line, cut);
        n_in = irls_step_(wk, rows, &line, cut);
    }
    out->rows_measured = (uint16_t)n_meas;
    if (n_in < MIN_FIT_ROWS || fabsf(line.b) > 0.15f) {
        out->rows_used = (uint16_t)n_in;
        return GL_ERR_NO_STICK;
    }

    /* ---- inliers, covariance ---- */
    n_in = 0;
    for (int r = 0; r < rows; r++) {
        if ((wk->flag[r] & (GL_VIS_ROW_MEASURED | GL_VIS_ROW_WIDE)) == GL_VIS_ROW_MEASURED) {
            float res = wk->x[r] - line_at_(&line, (float)r);
            if (fabsf(res) < cut) {
                float dy = (float)r - line.rc;
                wk->flag[r] |= GL_VIS_ROW_INLIER;
                sw += wk->w[r];
                syy += wk->w[r] * dy * dy;
                sres += wk->w[r] * res * res;
                sres_unw += res * res;
                pol_sum += ((wk->flag[r] & GL_VIS_ROW_NEG) != 0u) ? -wk->flux[r] : wk->flux[r];
                n_in++;
            }
        }
    }
    if (n_in < MIN_FIT_ROWS || !(sw > 0.0f)) {
        out->rows_used = (uint16_t)n_in;
        return GL_ERR_NO_STICK;
    }
    /* Is this a line at all?  Random row centroids (noise, turf texture)
     * also "fit" a line if the cut-off stays wide: demand a tight scatter
     * and that most of the candidate rows agree. */
    {
        unsigned n_cand = 0;
        for (int r = 0; r < rows; r++) {
            if ((wk->flag[r] & (GL_VIS_ROW_MEASURED | GL_VIS_ROW_WIDE)) == GL_VIS_ROW_MEASURED) {
                n_cand++;
            }
        }
        out->rows_used = (uint16_t)n_in;
        if (cut > MAX_FINAL_CUT_PX || sqrtf(sres_unw / (float)n_in) > MAX_LINE_SCATTER_PX ||
            (float)n_in < MIN_INLIER_FRACTION * (float)n_cand) {
            return GL_ERR_NO_STICK;
        }
    }
    chi = sres / (float)(n_in - 2u);
    if (chi < 1.0f) {
        chi = 1.0f;
    }
    /* Background texture makes the errors of neighbouring rows alike, so n
     * rows are worth fewer than n independent ones.  Inflate the variance
     * by (1 + rho) / (1 - rho) with rho the lag-one autocorrelation of the
     * residuals (AR(1) effective sample size). */
    {
        float num = 0.0f, den = 0.0f, rho;
        for (int r = 0; r + 1 < rows; r++) {
            if ((wk->flag[r] & wk->flag[r + 1] & GL_VIS_ROW_INLIER) != 0u) {
                float ra = wk->x[r] - line_at_(&line, (float)r);
                float rb = wk->x[r + 1] - line_at_(&line, (float)(r + 1));
                num += ra * rb;
                den += 0.5f * (ra * ra + rb * rb);
            }
        }
        rho = (den > 0.0f) ? gl_clampf(num / den, 0.0f, 0.9f) : 0.0f;
        chi *= (1.0f + rho) / (1.0f - rho);
    }
    out->sigma_scale = sqrtf(chi);
    out->sigma_x_ref = sqrtf(chi / sw);
    out->sigma_slope = (syy > 1e-6f) ? sqrtf(chi / syy) : 1.0f;
    out->resid_rms_px = sqrtf(sres / sw);
    out->x_ref = line.a + (float)strip->x0;
    out->row_ref = line.rc + (float)strip->y0;
    out->slope = line.b;
    out->polarity = (int8_t)((pol_sum >= 0.0f) ? 1 : -1);

    /* ---- quality: medians over the inlier rows ---- */
    {
        unsigned n = 0;
        for (int r = 0; r < rows; r++) {
            if ((wk->flag[r] & GL_VIS_ROW_INLIER) != 0u) {
                wk->tmp[n++] = (float)wk->peak[r];
            }
        }
        out->contrast = gl_median_inplace(wk->tmp, n);
        n = 0;
        for (int r = 0; r < rows; r++) {
            if ((wk->flag[r] & GL_VIS_ROW_INLIER) != 0u) {
                wk->tmp[n++] = wk->m2[r];
            }
        }
        out->width_px = sqrtf(gl_median_inplace(wk->tmp, n));
    }
    out->rows_used = (uint16_t)n_in;

    /* ---- extent: ends of the line from the forced amplitude profile ---- */
    row_geom_(s_w, &core_h, &g);
    (void)core_h;
    forced_amp_(strip, wk, &line, g, s_w);
    {
        unsigned n = 0;
        float ref, amp_noise, bg_tol, cross = 0.0f;
        int mid = gl_clampi(gl_roundi(line.rc), 0, rows - 1);
        int edge = 0, res;

        for (int r = 0; r < rows; r++) {
            if ((wk->flag[r] & (GL_VIS_ROW_INLIER | ROW_FORCED)) ==
                (GL_VIS_ROW_INLIER | ROW_FORCED)) {
                wk->tmp[n++] = fabsf(wk->flux[r]);
            }
        }
        ref = (n >= 3u) ? gl_median_inplace(wk->tmp, n) : 0.0f;
        /* noise of a matched amplitude: sigma / sqrt(sum g^2), sum g^2 ~ sqrt(pi) s_w */
        amp_noise = noise / sqrtf(1.7724539f * s_w);
        /* two rows have "the same background" within the noise of a flank
         * mean, or a small fraction of the line amplitude */
        bg_tol = 2.0f * noise + 0.15f * ref;

        bot_idx = rows - 1;
        top_idx = 0;
        for (int r = rows - 1; r >= 0; r--) {
            if ((wk->flag[r] & GL_VIS_ROW_INLIER) != 0u) {
                bot_idx = r;
                break;
            }
        }
        for (int r = 0; r < rows; r++) {
            if ((wk->flag[r] & GL_VIS_ROW_INLIER) != 0u) {
                top_idx = r;
                break;
            }
        }
        res = find_end_(wk, rows, mid, 1, ref, amp_noise, bg_tol, &cross, &edge);
        if (res < 0) {
            return GL_ERR_NO_STICK; /* too faint to be told from the noise */
        }
        bottom_known = (res == 1);
        if (res == 1) {
            out->bottom_row = cross + (float)strip->y0;
            bot_idx = gl_clampi(edge - 1, mid, rows - 1);
        } else {
            /* the line runs out of the strip, or is too faint to tell:
             * report the last row that supported the fit */
            out->bottom_row = (float)bot_idx + 0.5f + (float)strip->y0;
        }
        res = find_end_(wk, rows, mid, -1, ref, amp_noise, bg_tol, &cross, &edge);
        out->top_in_frame = (res == 1);
        if (res == 1) {
            out->top_row = cross + (float)strip->y0;
            top_idx = gl_clampi(edge + 1, 0, mid);
        } else {
            out->top_row = (float)strip->y0; /* not valid: top_in_frame is false */
        }
    }
    {
        unsigned inl = 0;
        for (int r = top_idx; r <= bot_idx; r++) {
            if ((wk->flag[r] & GL_VIS_ROW_MEASURED) != 0u) {
                wk->flag[r] |= GL_VIS_ROW_PRESENT;
            }
            if ((wk->flag[r] & GL_VIS_ROW_INLIER) != 0u) {
                inl++;
            }
        }
        out->rows_used_frac = (float)inl / (float)(bot_idx - top_idx + 1);
        if (inl < MIN_FIT_ROWS || out->rows_used_frac < MIN_INLIER_FRACTION) {
            out->rows_used = (uint16_t)inl;
            return GL_ERR_NO_STICK; /* scattered rows, not a continuous stick */
        }
    }

    /* ---- local turf horizon and base classification ---- */
    {
        float hrow = 0.0f;
        out->base = (uint8_t)GL_VIS_BASE_UNKNOWN;
        out->horizon_found = false;
        if (bottom_known && local_horizon_(strip, wk, &line, bot_idx, noise, &hrow)) {
            float delta;
            out->horizon_found = true;
            out->horizon_row = hrow + (float)strip->y0;
            delta = out->bottom_row - out->horizon_row; /* + = stick goes below the horizon */
            if (delta > GL_VIS_BASE_MARGIN_ROWS) {
                out->base = (uint8_t)GL_VIS_BASE_VISIBLE;
            } else if (delta >= -GL_VIS_BASE_MARGIN_ROWS) {
                out->base = (uint8_t)GL_VIS_BASE_AT_HORIZON;
            }
        }
    }
    return GL_OK;
}

float gl_vis_stick_x_at(const gl_vis_stick_t *s, float sensor_row)
{
    return s->x_ref + s->slope * (sensor_row - s->row_ref);
}

/* ======================================================================= */
/* Segment fit and stereo                                                   */
/* ======================================================================= */

gl_status_t gl_vis_stick_segment(const gl_vis_stick_work_t *wk, const gl_vis_stick_t *stick,
                                 float sensor_row_lo, float sensor_row_hi, gl_vis_segment_t *out)
{
    int r0, r1;
    float sw = 0.0f, swy = 0.0f, swx = 0.0f, syy = 0.0f, sxy = 0.0f, ybar, xbar;
    unsigned n = 0;

    if (wk == NULL || stick == NULL || out == NULL) {
        return GL_ERR_PARAM;
    }
    memset(out, 0, sizeof(*out));
    r0 = (int)ceilf(gl_clampf(sensor_row_lo - (float)stick->y0, -1.0f, 1000.0f));
    r1 = (int)floorf(gl_clampf(sensor_row_hi - (float)stick->y0, -1.0f, 1000.0f));
    if (r0 < 0) {
        r0 = 0;
    }
    /* only the rows written by the refinement of THIS strip are valid */
    if (r1 > (int)stick->strip_rows - 1) {
        r1 = (int)stick->strip_rows - 1;
    }
    if (r1 > (int)GL_VIS_STRIP_MAX_H - 1) {
        r1 = (int)GL_VIS_STRIP_MAX_H - 1;
    }
    for (int r = r0; r <= r1; r++) {
        if ((wk->flag[r] & GL_VIS_ROW_INLIER) != 0u) {
            sw += wk->w[r];
            swy += wk->w[r] * (float)r;
            swx += wk->w[r] * wk->x[r];
            n++;
        }
    }
    out->rows = (uint16_t)n;
    if (n < GL_VIS_SEGMENT_MIN_ROWS || !(sw > 0.0f)) {
        return GL_ERR_NO_STICK;
    }
    ybar = swy / sw;
    xbar = swx / sw;
    out->slope = stick->slope;
    if (n >= 24u) {
        for (int r = r0; r <= r1; r++) {
            if ((wk->flag[r] & GL_VIS_ROW_INLIER) != 0u) {
                float dy = (float)r - ybar;
                syy += wk->w[r] * dy * dy;
                sxy += wk->w[r] * dy * (wk->x[r] - xbar);
            }
        }
        if (syy > 1e-6f) {
            out->slope = sxy / syy;
        }
    }
    out->x_mid = xbar + (float)stick->x0;
    out->row_mid = ybar + (float)stick->y0;
    out->sigma_x = ((stick->sigma_scale > 1.0f) ? stick->sigma_scale : 1.0f) / sqrtf(sw);
    return GL_OK;
}

unsigned gl_vis_segment_rows(float disparity_px, float baseline_m, float length_m)
{
    float rows;
    if (!(disparity_px > 0.0f) || !(baseline_m > 0.0f)) {
        return 40u;
    }
    /* rows = f * L / Z with Z = f * B / d  ->  L * d / B */
    rows = length_m * disparity_px / baseline_m;
    return (unsigned)gl_clampf(rows, 12.0f, 400.0f);
}

/* A segment as a line in rectified coordinates: xr at yr_mid and dxr/dyr.
 * Without a camera model the "rectified" coordinates are plain pixels. */
typedef struct {
    float xr, yr, slope, sigma;
} rect_line_t;

static void rect_line_(const gl_vis_segment_t *s, const gl_cam_model_t *cam, float f_ref,
                       rect_line_t *out)
{
    if (cam == NULL) {
        out->xr = s->x_mid;
        out->yr = s->row_mid;
        out->slope = s->slope;
        out->sigma = s->sigma_x;
        return;
    }
    {
        const float h = 8.0f;
        float xa, ya, xb, yb, xm, ym;
        gl_cam_pixel_to_rectified(cam, s->x_mid - s->slope * h, s->row_mid - h, &xa, &ya);
        gl_cam_pixel_to_rectified(cam, s->x_mid + s->slope * h, s->row_mid + h, &xb, &yb);
        gl_cam_pixel_to_rectified(cam, s->x_mid, s->row_mid, &xm, &ym);
        /* scale to pixels of the reference focal length */
        out->xr = f_ref * xm;
        out->yr = f_ref * ym;
        out->slope = (fabsf(yb - ya) > 1e-9f) ? ((xb - xa) / (yb - ya)) : 0.0f;
        out->sigma = s->sigma_x * f_ref / cam->fx;
    }
}

static float rect_at_(const rect_line_t *l, float yr)
{
    return l->xr + l->slope * (yr - l->yr);
}

gl_status_t gl_vis_stereo_pair(const gl_vis_segment_t *left, const gl_vis_segment_t *right,
                               const gl_cam_model_t *cam_l, const gl_cam_model_t *cam_r,
                               float f_ref, float *disparity_px, float *sigma_px)
{
    rect_line_t l, r;
    float y;
    if (left == NULL || right == NULL || disparity_px == NULL || sigma_px == NULL ||
        left->rows < GL_VIS_SEGMENT_MIN_ROWS || right->rows < GL_VIS_SEGMENT_MIN_ROWS ||
        ((cam_l == NULL) != (cam_r == NULL))) {
        return GL_ERR_PARAM;
    }
    rect_line_(left, cam_l, f_ref, &l);
    rect_line_(right, cam_r, f_ref, &r);
    y = 0.5f * (l.yr + r.yr);
    *disparity_px = rect_at_(&l, y) - rect_at_(&r, y);
    *sigma_px = sqrtf(l.sigma * l.sigma + r.sigma * r.sigma);
    return GL_OK;
}

void gl_vis_disp_acc_reset(gl_vis_disp_acc_t *a)
{
    memset(a, 0, sizeof(*a));
}

gl_status_t gl_vis_disp_acc_add_lrrl(gl_vis_disp_acc_t *a, const gl_vis_segment_t seg[4],
                                     const gl_cam_model_t *cam_l, const gl_cam_model_t *cam_r,
                                     float f_ref)
{
    rect_line_t l1, r1, r2, l2;
    float y, d, var, w;
    if (a == NULL || seg == NULL || ((cam_l == NULL) != (cam_r == NULL))) {
        return GL_ERR_PARAM;
    }
    for (int i = 0; i < 4; i++) {
        if (seg[i].rows < GL_VIS_SEGMENT_MIN_ROWS || !(seg[i].sigma_x > 0.0f)) {
            return GL_ERR_PARAM;
        }
    }
    rect_line_(&seg[0], cam_l, f_ref, &l1);
    rect_line_(&seg[1], cam_r, f_ref, &r1);
    rect_line_(&seg[2], cam_r, f_ref, &r2);
    rect_line_(&seg[3], cam_l, f_ref, &l2);
    y = 0.25f * (l1.yr + r1.yr + r2.yr + l2.yr);
    d = 0.5f * (rect_at_(&l1, y) + rect_at_(&l2, y)) - 0.5f * (rect_at_(&r1, y) + rect_at_(&r2, y));
    var = 0.25f * (l1.sigma * l1.sigma + l2.sigma * l2.sigma + r1.sigma * r1.sigma +
                   r2.sigma * r2.sigma);
    w = 1.0f / var;
    a->sum_w += w;
    a->sum_wd += w * d;
    a->sum_d += d;
    a->sum_d2 += d * d;
    /* L1 and L2 are three frame intervals apart */
    a->sum_sway += (rect_at_(&l2, y) - rect_at_(&l1, y)) / 3.0f;
    if (a->n < 0xFFFFu) {
        a->n++;
    }
    return GL_OK;
}

gl_status_t gl_vis_disp_acc_result(const gl_vis_disp_acc_t *a, gl_vis_disparity_t *out)
{
    float formal, n;
    if (a == NULL || out == NULL) {
        return GL_ERR_PARAM;
    }
    memset(out, 0, sizeof(*out));
    if (a->n == 0u || !(a->sum_w > 0.0f)) {
        return GL_ERR_NO_STICK;
    }
    n = (float)a->n;
    out->groups = a->n;
    out->disparity_px = a->sum_wd / a->sum_w;
    formal = 1.0f / sqrtf(a->sum_w);
    out->sigma_px = formal;
    out->sway_px = a->sum_sway / n;
    if (a->n >= 2u) {
        float mean = a->sum_d / n;
        float var = (a->sum_d2 - n * mean * mean) / (n - 1.0f);
        if (var < 0.0f) {
            var = 0.0f;
        }
        out->jitter_px = sqrtf(var);
        if (a->n >= 3u) {
            float sem = out->jitter_px / sqrtf(n);
            if (sem > out->sigma_px) {
                out->sigma_px = sem;
            }
        }
    }
    return GL_OK;
}

/* ======================================================================= */
/* Angles and quality                                                       */
/* ======================================================================= */

void gl_vis_stick_angles(const gl_vis_stick_t *s, const gl_cam_model_t *cam, gl_vec3_t up_marker,
                         gl_vis_angles_t *out)
{
    float b_top = 0.0f;
    memset(out, 0, sizeof(*out));
    gl_cam_pixel_to_bearing_elev(cam, gl_vis_stick_x_at(s, s->bottom_row), s->bottom_row,
                                 up_marker, &out->bearing_rad, &out->base_elev_rad);
    out->base = s->base;
    out->top_valid = s->top_in_frame;
    if (s->top_in_frame) {
        gl_cam_pixel_to_bearing_elev(cam, gl_vis_stick_x_at(s, s->top_row), s->top_row, up_marker,
                                     &b_top, &out->top_elev_rad);
        out->tan_height = tanf(out->top_elev_rad) - tanf(out->base_elev_rad);
    }
}

void gl_vis_quality(const gl_vis_stick_t *left, const gl_vis_stick_t *right,
                    const gl_vis_stats_t *stats_left, const gl_vis_stats_t *stats_right,
                    gl_vis_quality_t *out)
{
    float wl = left->width_px, wr = right->width_px;
    float cl = left->contrast, cr = right->contrast;
    float wm, cm, noise;
    memset(out, 0, sizeof(*out));
    out->line_contrast = (cl < cr) ? cl : cr;
    noise = (left->noise_sigma > right->noise_sigma) ? left->noise_sigma : right->noise_sigma;
    out->contrast_snr = (noise > 0.0f) ? (out->line_contrast / noise) : 0.0f;
    out->rows_used_frac = (left->rows_used_frac < right->rows_used_frac) ? left->rows_used_frac
                                                                         : right->rows_used_frac;
    wm = (wl > 0.0f && wr > 0.0f) ? ((wl < wr) ? (wl / wr) : (wr / wl)) : 0.0f;
    cm = (cl > 0.0f && cr > 0.0f) ? ((cl < cr) ? (cl / cr) : (cr / cl)) : 0.0f;
    out->sharpness_match = (wm < cm) ? wm : cm;
    if (stats_left != NULL && stats_right != NULL) {
        out->sat_fraction = (stats_left->sat_fraction > stats_right->sat_fraction)
                                ? stats_left->sat_fraction
                                : stats_right->sat_fraction;
        out->sun = stats_left->sun || stats_right->sun;
    }
}
