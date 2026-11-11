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
 * about 0.01 px for a noise penalty of 15-30 % on sub-pixel lines.  For a
 * lens SHARPER than that (profile sigma below about 0.6 px) the bias comes
 * back: 0.03-0.09 px for exactly vertical sticks; PHASE_BIAS_* below puts
 * that into the reported uncertainty.  The real blur must be measured at
 * EVT and this constant set from it. */
#define MIN_WINDOW_SIGMA 1.2f
#define MAX_CORE 64 /* residual samples per row: 2 * flank offset - 1 <= 63 */
/* A row is rejected as an edge when |left flank - right flank| exceeds this
 * fraction of the line's peak contrast. */
#define EDGE_ASYMMETRY 0.8f
/* Where single rows are well measured, a fit is a line only if the inlier
 * rows scatter by less than this about it (unweighted rms, px).  Measured:
 * 0.17-0.31 px for a 0.5-0.7 px stick at SNR 20 on a textured background,
 * 0.65-1.2 px for strips with no stick.  Where the rows are faint (binned
 * measurements) the limit is SCATTER_VS_PREDICTED times the scatter their
 * own noise predicts, and the line-significance test decides. */
#define MAX_LINE_SCATTER_PX 0.45f
#define SCATTER_VS_PREDICTED 2.0f
/* ... the final robust cut-off has closed to below this (px) ... */
#define MAX_FINAL_CUT_PX 1.5f
/* ... and at least this fraction of the candidate rows are inliers. */
#define MIN_INLIER_FRACTION 0.5f
/* Rows below the turf horizon examined for the stick's continuation. */
#define TURF_ROWS 80
/* Sub-pixel phase bias of a narrow, exactly vertical line (reviewers'
 * measurement: 0.013 px at a profile sigma of 0.62 px and above, rising to
 * 0.09 px at 0.47 px): added to the static uncertainty when the line does
 * not sweep a pixel across the rows used. */
#define PHASE_BIAS_SIGMA_KNEE_PX 0.62f
#define PHASE_BIAS_FLOOR_PX 0.009f /* per camera: 0.013 px in the disparity */
#define PHASE_BIAS_PER_PX 0.36f
#define PHASE_BIAS_MAX_PX 0.07f

static inline int px_(const gl_strip_t *s, int col, int row)
{
    return (int)s->px[(size_t)row * s->stride + (size_t)col];
}

/* exp(-t) for t >= 0 from a table (linear interpolation, relative error
 * below 2e-4): the Gaussian window weights are the innermost loop of the
 * refinement, and expf() dominated its run time. */
#define EXP_LUT_N 128
#define EXP_LUT_MAX 8.0f
static float exp_neg_(float t)
{
    static const float lut[EXP_LUT_N + 2] = {
        1.00000000f, 0.93941306f, 0.88249690f, 0.82902912f,
        0.77880078f, 0.73161563f, 0.68728928f, 0.64564853f,
        0.60653066f, 0.56978282f, 0.53526143f, 0.50283158f,
        0.47236655f, 0.44374731f, 0.41686202f, 0.39160563f,
        0.36787944f, 0.34559075f, 0.32465247f, 0.30498277f,
        0.28650480f, 0.26914635f, 0.25283960f, 0.23752082f,
        0.22313016f, 0.20961139f, 0.19691168f, 0.18498140f,
        0.17377394f, 0.16324551f, 0.15335497f, 0.14406366f,
        0.13533528f, 0.12713573f, 0.11943297f, 0.11219689f,
        0.10539922f, 0.09901341f, 0.09301449f, 0.08737903f,
        0.08208500f, 0.07711172f, 0.07243976f, 0.06805085f,
        0.06392786f, 0.06005467f, 0.05641614f, 0.05299806f,
        0.04978707f, 0.04677062f, 0.04393693f, 0.04127493f,
        0.03877421f, 0.03642500f, 0.03421812f, 0.03214495f,
        0.03019738f, 0.02836782f, 0.02664910f, 0.02503451f,
        0.02351775f, 0.02209288f, 0.02075434f, 0.01949690f,
        0.01831564f, 0.01720595f, 0.01616349f, 0.01518420f,
        0.01426423f, 0.01340001f, 0.01258814f, 0.01182547f,
        0.01110900f, 0.01043594f, 0.00980366f, 0.00920968f,
        0.00865170f, 0.00812752f, 0.00763509f, 0.00717251f,
        0.00673795f, 0.00632972f, 0.00594622f, 0.00558595f,
        0.00524752f, 0.00492959f, 0.00463092f, 0.00435035f,
        0.00408677f, 0.00383917f, 0.00360656f, 0.00338805f,
        0.00318278f, 0.00298995f, 0.00280879f, 0.00263862f,
        0.00247875f, 0.00232857f, 0.00218749f, 0.00205496f,
        0.00193045f, 0.00181349f, 0.00170362f, 0.00160040f,
        0.00150344f, 0.00141235f, 0.00132678f, 0.00124639f,
        0.00117088f, 0.00109994f, 0.00103330f, 0.00097069f,
        0.00091188f, 0.00085663f, 0.00080473f, 0.00075598f,
        0.00071017f, 0.00066715f, 0.00062673f, 0.00058876f,
        0.00055308f, 0.00051957f, 0.00048810f, 0.00045852f,
        0.00043074f, 0.00040465f, 0.00038013f, 0.00035710f,
        0.00033546f, 0.0f
    };
    float u;
    int i;
    if (!(t < EXP_LUT_MAX)) {
        return 0.0f; /* also NaN */
    }
    if (t < 0.0f) {
        t = 0.0f;
    }
    u = t * ((float)EXP_LUT_N / EXP_LUT_MAX);
    i = (int)u;
    return lut[i] + (lut[i + 1] - lut[i]) * (u - (float)i);
}

/* ======================================================================= */
/* Noise estimate and strip statistics                                      */
/* ======================================================================= */

/* Robust pixel-noise estimate from horizontal second differences sampled
 * on a sparse grid over the first `rows` rows (at most `cap` samples,
 * median via tmp).  The differences are taken between pixels TWO columns
 * apart, so that a period-2 column pattern of the sensor (odd / even column
 * gain) cancels instead of being read as noise.  For white noise of sigma s
 * the second difference has sigma sqrt(6) s. */
static float noise_estimate_(const gl_strip_t *s, int rows, float *tmp, unsigned cap)
{
    const int w = (int)s->width;
    const int h = (rows > 0 && rows < (int)s->height) ? rows : (int)s->height;
    int rstep = h / 24, cstep = (w - 4) / 19;
    unsigned n = 0;
    float med, sigma;

    if (w < 5 || h < 1 || cap == 0u) {
        return 1.0f;
    }
    if (rstep < 1) {
        rstep = 1;
    }
    if (cstep < 1) {
        cstep = 1;
    }
    for (int r = rstep / 2; r < h && n < cap; r += rstep) {
        for (int c = cstep / 2; c + 4 < w && n < cap; c += cstep) {
            int d = px_(s, c, r) - 2 * px_(s, c + 2, r) + px_(s, c + 4, r);
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

void gl_vis_strip_stats_rows(const gl_strip_t *s, unsigned rows, float *scratch,
                             gl_vis_stats_t *out)
{
    const int w = (int)s->width;
    const int h = (rows > 0u && rows < (unsigned)s->height) ? (int)rows : (int)s->height;
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
    out->noise_sigma = noise_estimate_(s, h, scratch, 480u);
}

void gl_vis_strip_stats(const gl_strip_t *s, float *scratch, gl_vis_stats_t *out)
{
    gl_vis_strip_stats_rows(s, 0u, scratch, out);
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

/* Median and robust spread of v[0..n-1]; v is destroyed.  The spread is the
 * 80th percentile of the absolute deviations (1.2816 sigma for a Gaussian),
 * not the median one: the edge-blind response is exactly zero in more than
 * half of the columns of a plain band, where a median deviation collapses
 * (and every fixed-pattern column then scores as a line); 80 % still
 * ignores objects that fill up to a fifth of the band. */
static void med_spread_(float *v, unsigned n, float *med, float *spread)
{
    const float m = gl_median_inplace(v, n);
    for (unsigned i = 0; i < n; i++) {
        v[i] = fabsf(v[i] - m);
    }
    (void)gl_median_inplace(v, n); /* sorts */
    *med = m;
    *spread = v[(4u * (n - 1u)) / 5u] / 1.2816f;
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
        float white[GL_VIS_BAND_MAX_BLOCKS + 1]; /* white-noise sigma of a sum of b blocks */
        float cumvar = 0.0f;

        white[0] = 1.0f;
        for (int b = 0; b < nb; b++) {
            const int16_t *blk = work->block[b];
            float *rg = work->ridge[b];
            float sigma = 1.0f;
            unsigned n = 0;
            int sstep = (w - 2 * margin + (int)GL_VIS_BAND_PATH_SAMPLES - 1) /
                        (int)GL_VIS_BAND_PATH_SAMPLES;
            if (sstep < 1) {
                sstep = 1;
            }
            for (int x = 0; x < w; x++) {
                rg[x] = 0.0f;
            }
            for (int x = margin; x < w - margin; x++) {
                int c = 0, fl = 0, fr = 0;
                float v, asym;
                for (int k = -half; k <= half; k++) {
                    c += blk[x + k];
                }
                for (int k = 0; k < flank; k++) {
                    fl += blk[x - half - gap - 1 - k];
                    fr += blk[x + half + gap + 1 + k];
                }
                v = (float)c * kcore - (float)(fl + fr) * kflank; /* grey levels */
                /* the noise figure is taken from the response as it is,
                 * before the edge term below shrinks it */
                if ((x - margin) % sstep == 0 && n < GL_VIS_BAND_PATH_SAMPLES) {
                    work->path[b][n++] = fabsf(v);
                }
                /* A line has the same background on both sides; at the EDGE
                 * of something wide the centre differs from the mean of the
                 * flanks by half the step, and the flanks from each other by
                 * the whole step.  Taking half the flank difference off the
                 * response makes the detector blind to edges (a person's
                 * outline used to fill every candidate slot). */
                asym = fabsf((float)(fl - fr)) * kflank;
                v = (v > asym) ? (v - asym) : ((v < -asym) ? (v + asym) : 0.0f);
                rg[x] = v;
            }
            /* robust sigma of the response of this block: the median of its
             * absolute value over a sample of columns (a mean would be
             * inflated by any strong object in the band) */
            if (n >= 8u) {
                sigma = gl_median_inplace(work->path[b], n) / 0.6745f;
            }
            if (sigma < 0.02f) {
                sigma = 0.02f;
            }
            cumvar += sigma * sigma;
            white[b + 1] = sqrtf(cumvar);
        }

        for (unsigned ji = 0; ji < GL_VIS_BAND_SLANTS; ji++) {
            const float slant = tanf(((float)ji - 6.0f) * 0.5f * GL_DEG2RAD_F);
            const float shift = slant * (float)GL_VIS_BAND_BLOCK_ROWS; /* px per block */
            const int pad = margin + 7; /* total shift over 8 blocks is at most 5 px */
            float centre[GL_VIS_BAND_MAX_BLOCKS], inv_spread[GL_VIS_BAND_MAX_BLOCKS];
            unsigned ns = 0;
            int step = (w - 2 * pad + (int)GL_VIS_BAND_PATH_SAMPLES - 1) /
                       (int)GL_VIS_BAND_PATH_SAMPLES; /* over the whole width */

            if (step < 1) {
                step = 1;
            }
            /* Pass 1: the response of THIS path shape, for every length, at a
             * sample of columns.  Its spread across the band is what a line
             * has to stand out from: it contains whatever adds up along the
             * path (fixed pattern, vertical scenery), which the white-noise
             * figure does not. */
            for (int x = pad; x < w - pad && ns < GL_VIS_BAND_PATH_SAMPLES; x += step) {
                float s = 0.0f;
                for (int b = 0; b < nb; b++) {
                    float xs = (float)x + shift * (float)b;
                    int i0 = (int)floorf(xs);
                    float fr = xs - (float)i0;
                    const float *rg = work->ridge[b];
                    s += rg[i0] + (rg[i0 + 1] - rg[i0]) * fr;
                    work->path[b][ns] = s;
                }
                ns++;
            }
            for (int b = 0; b < nb; b++) {
                float spread = 0.0f;
                centre[b] = 0.0f;
                if (ns >= 8u) {
                    med_spread_(work->path[b], ns, &centre[b], &spread);
                }
                if (spread < white[b + 1]) {
                    spread = white[b + 1]; /* never more sensitive than the noise allows */
                }
                inv_spread[b] = 1.0f / spread;
            }
            /* Pass 2: every column. */
            for (int x = pad; x < w - pad; x++) {
                float s = 0.0f;
                for (int b = 0; b < nb; b++) {
                    float xs = (float)x + shift * (float)b;
                    int i0 = (int)floorf(xs);
                    float fr = xs - (float)i0;
                    const float *rg = work->ridge[b];
                    s += rg[i0] + (rg[i0 + 1] - rg[i0]) * fr;
                    if (b >= 1) {
                        float z = fabsf(s - centre[b]) * inv_spread[b];
                        if (z > work->score[x]) {
                            work->score[x] = z;
                            work->best_slant[x] = (uint8_t)ji;
                            work->best_scale[x] = (uint8_t)si;
                            work->best_blocks[x] = (uint8_t)(b + 1);
                            work->best_pol[x] = (int8_t)((s >= centre[b]) ? 1 : -1);
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
        int own, lobes, scale, pol;

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
        scale = (int)work->best_scale[best_x];
        pol = (int)work->best_pol[best_x];
        c = &out->cand[out->n_cand++];
        c->x = (float)band->x0 + (float)best_x + off;
        c->ref_row = (float)band->y0 + 0.5f * ((float)GL_VIS_BAND_BLOCK_ROWS - 1.0f);
        c->slant = tanf(((float)work->best_slant[best_x] - 6.0f) * 0.5f * GL_DEG2RAD_F);
        c->score = best;
        c->width_px = (float)band_core_[scale];
        c->polarity = (int8_t)pol;
        c->rows = (uint8_t)(work->best_blocks[best_x] * GL_VIS_BAND_BLOCK_ROWS);
        /* Suppress what belongs to the winner, and nothing else (the whole
         * neighbourhood of +-24 px used to be blanked: a flagstick 14 px from
         * a post was then not even a candidate):
         *  - its own footprint: its template plus the lean it may have;
         *  - SAME polarity further out: columns whose best template is wide
         *    enough to have the winner inside its core (the same line seen
         *    by a wider template off-centre);
         *  - OPPOSITE polarity: columns whose best template is wide enough
         *    to have the winner in a FLANK (its side lobes).
         * A second line of its own a few pixels away has its best response
         * in a narrow template and stays. */
        {
            static const uint8_t reach[GL_VIS_BAND_SCALES] = { 3, 5, 10, 15 }; /* half core + gap + flank */
            const int half_w = (band_core_[scale] - 1) / 2;
            const int span = 15 + half_w + 3;
            own = half_w + band_gap_[scale] + 3;
            lobes = span;
            for (int x = best_x - lobes; x <= best_x + lobes; x++) {
                if (x >= 0 && x < w) {
                    const int dx = (x > best_x) ? (x - best_x) : (best_x - x);
                    const int sx = (int)work->best_scale[x];
                    const int lim = ((int)work->best_pol[x] == pol)
                                        ? ((band_core_[sx] - 1) / 2 + half_w + 1)
                                        : ((int)reach[sx] + half_w + 1);
                    if (dx <= own || dx <= lim) {
                        work->score[x] = 0.0f;
                    }
                }
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
    float flux;  /* sum of the residual over the core, grey x px */
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

#define FLANK_W 4      /* pixels per side that define the row's linear background */
#define FLANK_STORE 6  /* pixels per side kept for the static-error estimate */
#define FLANK_INVALID (-128)

/* Measure the line on one row near the predicted column xp.  `row` holds
 * the SUM of nb image rows (nb = 1: the row itself); `noise` is the pixel
 * noise of a single row.  Returns false if no significant line is found
 * within +-search. */
static bool measure_row_(const uint16_t *row, int nb, int width, float xp, float search,
                         float s_w, float noise, row_meas_t *m)
{
    int h, g, c_lo, c_hi, best_c = -1;
    float best_rr = 0.0f, best_l = 0.0f, best_r = 0.0f;
    float p[MAX_CORE];
    float xc, relax = 1.0f, den = 0.0f, var_w = 0.0f, flux = 0.0f, peak = 0.0f;
    const float inv2s2 = 0.5f / (s_w * s_w);
    const float inv = 1.0f / (float)nb;
    const float noise_b = noise * sqrtf(inv);
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
            core += row[c + k];
        }
        for (int k = 0; k < FLANK_W; k++) {
            l += row[c - g - k];
            r += row[c + g + k];
        }
        lm = (float)l * inv / (float)FLANK_W;
        rm = (float)r * inv / (float)FLANK_W;
        rr = (float)core * inv / (float)(2 * h + 1) - 0.5f * (lm + rm);
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
            float v = ((float)row[best_c + k] * inv - (mid + grad * (float)k)) * (float)m->pol;
            p[i] = v;
            flux += v;
            if (v > peak) {
                peak = v;
            }
        }
    }
    /* A line has the same background on both sides.  If the two flanks
     * differ by about as much as the "line" stands out, this is the edge of
     * something wide (a person, a wall, a tree trunk), not a stick. */
    if (fabsf(best_r - best_l) > EDGE_ASYMMETRY * peak + 1.5f * noise_b) {
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
            float wgt = exp_neg_(d * d * inv2s2);
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
    /* 4. significance: amplitude of the matched Gaussian at the fixed point
     *    against its noise (pixel noise under the template plus the noise
     *    of the background taken from 2 x FLANK_W pixels).  The test used to
     *    be on the plain sum over the core, which needs 1.5 times the
     *    contrast for the same decision. */
    {
        float sg = 0.0f, sgg = 0.0f, sgp = 0.0f, amp, amp_sigma;
        for (int i = 0; i < n; i++) {
            float d = (float)(i - (g - 1)) - xc;
            float wgt = exp_neg_(d * d * inv2s2);
            sg += wgt;
            sgg += wgt * wgt;
            sgp += wgt * p[i];
        }
        amp = sgp / sgg;
        amp_sigma = noise_b * sqrtf(1.0f / sgg + sg * sg / (sgg * sgg * (float)(2 * FLANK_W)));
        if (!(amp >= 3.0f * amp_sigma)) {
            return false;
        }
    }
    /* variance of the fixed point: single-step noise times the same gain */
    m->var = relax * relax * noise_b * noise_b * var_w / (den * den);
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

/* Measure along a predicted line, on the rows [0, row_end) only, nb rows at
 * a time: the nb rows are summed along the line (whole-pixel shifts) and
 * the result is stored at the middle row of the group. */
static unsigned measure_all_(const gl_strip_t *s, gl_vis_stick_work_t *wk, const line_t *l,
                             int row_end, int nb, float search, float s_w, float noise)
{
    const int rows = (int)s->height, w = (int)s->width;
    unsigned n = 0;

    for (int r = 0; r < rows; r++) {
        wk->flag[r] = 0;
        wk->w[r] = 0.0f;
        wk->x[r] = line_at_(l, (float)r);
        wk->flux[r] = 0.0f;
        wk->m2[r] = 0.0f;
        wk->peak[r] = 0;
    }
    for (int r0 = 0; r0 + nb <= row_end; r0 += nb) {
        const int rc = r0 + nb / 2;
        const float rmid = (float)r0 + 0.5f * (float)(nb - 1);
        const float xp = line_at_(l, rmid);
        row_meas_t m;

        if (!(xp >= 0.0f && xp <= (float)(w - 1))) {
            continue; /* outside the strip (or not a number) */
        }
        for (int c = 0; c < w; c++) {
            wk->rowsum[c] = 0;
        }
        for (int i = 0; i < nb; i++) {
            const uint8_t *rowp = &s->px[(size_t)(r0 + i) * s->stride];
            const int sh = gl_roundi(l->b * ((float)(r0 + i) - rmid));
            for (int c = 0; c < w; c++) {
                const int cc = gl_clampi(c + sh, 0, w - 1);
                wk->rowsum[c] = (uint16_t)(wk->rowsum[c] + rowp[cc]);
            }
        }
        if (measure_row_(wk->rowsum, nb, w, xp, search, s_w, noise, &m)) {
            wk->x[rc] = m.x + l->b * ((float)rc - rmid);
            wk->w[rc] = 1.0f / m.var;
            wk->flux[rc] = m.flux;
            wk->m2[rc] = m.m2;
            wk->peak[rc] = (uint8_t)((m.peak > 255.0f) ? 255.0f : m.peak);
            wk->flag[rc] = (uint8_t)(GL_VIS_ROW_MEASURED | ((m.pol < 0) ? GL_VIS_ROW_NEG : 0u));
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
 * bright-on-dark.  Optionally the flank means and the FLANK_STORE flank
 * pixels per side minus that background (half grey levels). */
static bool row_amp_at_(const uint8_t *rowp, int width, float xline, int g, float s_w, float *amp,
                        float *background, float *asym, int8_t *flank)
{
    const int c = gl_roundi(gl_clampf(xline, -1000.0f, 1000.0f));
    const float dx = xline - (float)c;
    const float inv2s2 = 0.5f / (s_w * s_w);
    float lm, rm, mid, grad, num = 0.0f, den = 0.0f;
    int l = 0, r = 0;

    if (c - g - FLANK_W + 1 < 0 || c + g + FLANK_W - 1 >= width) {
        return false;
    }
    for (int k = 0; k < FLANK_W; k++) {
        l += rowp[c - g - k];
        r += rowp[c + g + k];
    }
    lm = (float)l / (float)FLANK_W;
    rm = (float)r / (float)FLANK_W;
    mid = 0.5f * (lm + rm);
    grad = (rm - lm) / (2.0f * ((float)g + 0.5f * (float)(FLANK_W - 1)));
    for (int k = -(g - 1); k <= g - 1; k++) {
        float d = (float)k - dx;
        float wgt = exp_neg_(d * d * inv2s2);
        num += wgt * ((float)rowp[c + k] - (mid + grad * (float)k));
        den += wgt * wgt;
    }
    *amp = num / den;
    *background = mid;
    if (asym != NULL) {
        *asym = fabsf(rm - lm);
    }
    if (flank != NULL) {
        if (c - g - FLANK_STORE + 1 < 0 || c + g + FLANK_STORE - 1 >= width) {
            flank[0] = (int8_t)FLANK_INVALID;
        } else {
            for (int k = 0; k < FLANK_STORE; k++) {
                const int kl = -(g + FLANK_STORE - 1 - k), kr = g + k;
                float vl = 2.0f * ((float)rowp[c + kl] - (mid + grad * (float)kl));
                float vr = 2.0f * ((float)rowp[c + kr] - (mid + grad * (float)kr));
                flank[k] = (int8_t)gl_roundi(gl_clampf(vl, -127.0f, 127.0f));
                flank[FLANK_STORE + k] = (int8_t)gl_roundi(gl_clampf(vr, -127.0f, 127.0f));
            }
        }
    }
    return true;
}

/* Forced amplitude along the fitted line on every row -> wk->flux, the
 * local background level of the row -> wk->m2, |left - right flank| ->
 * wk->peak and the flank residuals -> wk->flank (these replace the per-row
 * measured flux, second moment and peak, which are no longer needed). */
static void forced_amp_(const gl_strip_t *s, gl_vis_stick_work_t *wk, const line_t *l, int g,
                        float s_w)
{
    const int rows = (int)s->height, w = (int)s->width;
    for (int r = 0; r < rows; r++) {
        float a = 0.0f, bg = 0.0f, as = 0.0f;
        wk->flank[r][0] = (int8_t)FLANK_INVALID;
        if (row_amp_at_(&s->px[(size_t)r * s->stride], w, line_at_(l, (float)r), g, s_w, &a, &bg,
                        &as, wk->flank[r])) {
            wk->flux[r] = a;
            wk->m2[r] = bg;
            wk->peak[r] = (uint8_t)((as > 255.0f) ? 255.0f : as);
            wk->flag[r] |= (uint8_t)ROW_FORCED;
        } else {
            wk->flux[r] = 0.0f;
            wk->m2[r] = 0.0f;
            wk->peak[r] = 0;
        }
    }
}

/*
 * Locate one end of the line as a change point of the forced amplitude:
 * walking from row `mid` in direction `dir` (not beyond [lo, hi]), the
 * running sum of (a - ref / 2) is largest at the row where the amplitude
 * drops from "about ref" to "about zero" (the maximum-likelihood step
 * position for a known step height; a few weak rows inside the stick do not
 * matter).  a = |A| when pol == 0 (strong sticks; the polarity may change
 * along the stick), else pol * A (faint sticks: |A| of pure noise does not
 * average to zero).  For strong sticks the position is then refined below
 * one row from the partial coverage of the three rows either side of the
 * step, measured against the amplitude of the rows right next to the end
 * that have the same background.
 *
 * Returns 1 = found (*row_out sub-row end, *edge_out first row beyond the
 * end), 0 = the line continues to where the walk stopped, -1 = unusable.
 */
static int find_end_(gl_vis_stick_work_t *wk, int lo, int hi, int mid, int dir, float ref_global,
                     float pol_in, float amp_noise, float bg_tol, float *row_out, int *edge_out)
{
    float ref = ref_global;
    float c = 0.0f, best = 0.0f;
    float pol_sum = 0.0f, sum_out = 0.0f, sum_in = 0.0f, pol;
    const bool strong = (pol_in == 0.0f);
    unsigned n = 0;
    int e = mid, r, slack;

    if (!(ref > 0.0f) || (strong && !(ref > 3.0f * amp_noise))) {
        return -1;
    }
    for (r = mid; r >= lo && r <= hi; r += dir) {
        if ((wk->flag[r] & ROW_FORCED) == 0u) {
            break;
        }
        c += (strong ? fabsf(wk->flux[r]) : (pol_in * wk->flux[r])) - 0.5f * ref;
        if (c > best) {
            best = c;
            e = r + dir;
        }
    }
    /* how well the step can be located at this signal-to-noise ratio */
    slack = 2 + (int)gl_clampf(4.0f * (amp_noise / ref) * (amp_noise / ref), 0.0f, 24.0f);
    if (dir * (r - e) <= slack) {
        return 0; /* still present where the walk ends */
    }
    *edge_out = e;
    *row_out = (float)e - 0.5f * (float)dir;
    if (!strong) {
        return 1;
    }
    /* Local reference: fully covered rows near the end that have the SAME
     * background as the row just beyond the end (wk->m2 holds the row
     * background).  Fall back to the six nearest rows. */
    if (e >= lo && e <= hi && (wk->flag[e] & ROW_FORCED) != 0u) {
        const float bg_end = wk->m2[e];
        for (int k = 2; k <= 12 && n < 6u; k++) {
            int rr = e - dir * k;
            if (rr >= lo && rr <= hi && (wk->flag[rr] & ROW_FORCED) != 0u &&
                fabsf(wk->m2[rr] - bg_end) <= bg_tol) {
                wk->tmp[n++] = fabsf(wk->flux[rr]);
            }
        }
    }
    if (n < 2u) {
        n = 0;
        for (int k = 2; k <= 7; k++) {
            int rr = e - dir * k;
            if (rr >= lo && rr <= hi && (wk->flag[rr] & ROW_FORCED) != 0u) {
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
        if (rr >= lo && rr <= hi) {
            pol_sum += wk->flux[rr];
        }
    }
    pol = (pol_sum >= 0.0f) ? 1.0f : -1.0f;
    for (int k = 0; k < 3; k++) {
        int ro = e + dir * k;       /* rows beyond the step */
        int ri = e - dir * (k + 1); /* rows inside */
        if (ro >= lo && ro <= hi && (wk->flag[ro] & ROW_FORCED) != 0u) {
            sum_out += gl_clampf(pol * wk->flux[ro] / ref, 0.0f, 1.0f);
        }
        if (ri >= lo && ri <= hi && (wk->flag[ri] & ROW_FORCED) != 0u) {
            sum_in += 1.0f - gl_clampf(pol * wk->flux[ri] / ref, 0.0f, 1.0f);
        }
    }
    /* the step lies between rows e - dir and e, shifted by the net partial
     * coverage (clipping errors on the two sides cancel on average) */
    *row_out = (float)e - 0.5f * (float)dir + (float)dir * (sum_out - sum_in);
    return 1;
}

/* Local turf horizon beside the stick near strip row `near`: strongest
 * horizontal edge of the flank columns within +-tol rows. */
static bool local_horizon_(const gl_strip_t *s, gl_vis_stick_work_t *wk, const line_t *l,
                           int near, int tol, float noise, float *row_out)
{
    const int rows = (int)s->height, w = (int)s->width;
    const int xc = gl_roundi(gl_clampf(line_at_(l, (float)near), -1000.0f, 1000.0f));
    int r0 = near - tol, r1 = near + tol;
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

/*
 * Follow the stick into the turf: rows t0 .. t1 (below the turf edge).
 * The turf's texture gives every line through it an "amplitude" on every
 * row; whether the amplitude along the stick's axis means anything is
 * judged against the same sum taken along GHOST lines parallel to it (up
 * to six, 11 / 22 / 33 px either side): their cumulative sums show what
 * turf alone produces, including the part that is correlated from row to
 * row.  Returns the largest significance found (0 if it cannot be judged);
 * if it reaches GL_VIS_TURF_MIN_SNR, *end_out is the sub-row end of the
 * stick (strip rows) and *sigma_out its uncertainty.
 */
#define TURF_GHOSTS 6
/* Below GL_VIS_TURF_MIN_SNR but above this, the end is still worked out:
 * the caller widens the uncertainty of the lowest point by it. */
#define TURF_HINT_SNR 3.3f
static float turf_follow_(const gl_strip_t *s, gl_vis_stick_work_t *wk, const line_t *l, int g,
                          float s_w, int t0, int t1, float amp_noise, float *end_out,
                          float *sigma_out)
{
    const int w = (int)s->width;
    const int pitch = g + FLANK_W + 2;
    float gsum[TURF_GHOSTS] = { 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f };
    bool gok[TURF_GHOSTS];
    float var_row = 0.0f, csum = 0.0f, zmax = 0.0f, amp, q = 0.0f, qbest = 0.0f, sgn;
    unsigned ng = 0, nvar = 0;
    int kmax = 0, kend = 0, K;

    if (t1 > (int)s->height - 1) {
        t1 = (int)s->height - 1;
    }
    K = t1 - t0 + 1;
    if (K < 1 || t0 < 0) {
        return 0.0f;
    }
    /* a ghost must fit beside the line on every row examined */
    for (int j = 0; j < TURF_GHOSTS; j++) {
        const float off = (float)(((j & 1) != 0) ? pitch : -pitch) * (float)(j / 2 + 1);
        const float xa = line_at_(l, (float)t0) + off, xb = line_at_(l, (float)t1) + off;
        const float lo = (float)(g + FLANK_W), hi = (float)(w - 1 - g - FLANK_W);
        gok[j] = (xa >= lo && xa <= hi && xb >= lo && xb <= hi);
        if (gok[j]) {
            ng++;
        }
    }
    if (ng < 3u) {
        return 0.0f; /* the turf beside the stick cannot be sampled */
    }
    for (int k = 0; k < K; k++) {
        const int r = t0 + k;
        const uint8_t *rowp = &s->px[(size_t)r * s->stride];
        float ss = 0.0f;
        if ((wk->flag[r] & ROW_FORCED) == 0u) {
            K = k;
            break;
        }
        for (int j = 0; j < TURF_GHOSTS; j++) {
            if (gok[j]) {
                const float off = (float)(((j & 1) != 0) ? pitch : -pitch) * (float)(j / 2 + 1);
                float a = 0.0f, bg = 0.0f;
                (void)row_amp_at_(rowp, w, line_at_(l, (float)r) + off, g, s_w, &a, &bg, NULL,
                                  NULL);
                gsum[j] += a;
                var_row += a * a;
                nvar++;
                ss += gsum[j] * gsum[j];
            }
        }
        wk->tmp[k] = ss / (float)ng; /* mean square of the ghosts' sums of k + 1 rows */
    }
    if (K < 1 || nvar == 0u) {
        return 0.0f;
    }
    var_row /= (float)nvar;
    if (var_row < amp_noise * amp_noise) {
        var_row = amp_noise * amp_noise;
    }
    for (int k = 0; k < K; k++) {
        float v = (float)(k + 1) * var_row, z;
        if (wk->tmp[k] > v) {
            v = wk->tmp[k];
        }
        csum += wk->flux[t0 + k];
        z = fabsf(csum) / sqrtf(v);
        if (z > zmax) {
            zmax = z;
            kmax = k + 1;
        }
    }
    if (zmax < TURF_HINT_SNR || kmax < 1) {
        return zmax;
    }
    csum = 0.0f;
    for (int k = 0; k < kmax; k++) {
        csum += wk->flux[t0 + k];
    }
    amp = fabsf(csum) / (float)kmax;
    sgn = (csum >= 0.0f) ? 1.0f : -1.0f;
    for (int k = 0; k < K; k++) {
        q += sgn * wk->flux[t0 + k] - 0.5f * amp;
        if (q > qbest) {
            qbest = q;
            kend = k + 1;
        }
    }
    if (kend < 1) {
        kend = 1;
    }
    /* rows t0 .. t0 + kend - 1 are covered; the next one partly */
    *end_out = (float)(t0 + kend) - 0.5f;
    if (kend < K) {
        *end_out += gl_clampf(sgn * wk->flux[t0 + kend] / amp, 0.0f, 1.0f);
    }
    *sigma_out = gl_clampf(0.25f + 2.0f * var_row / (amp * amp), 0.3f, 6.0f);
    return zmax;
}

/* ======================================================================= */
/* Stick refinement                                                         */
/* ======================================================================= */

gl_status_t gl_vis_stick_refine(const gl_strip_t *strip, const gl_vis_prior_t *prior,
                                gl_vis_stick_work_t *wk, gl_vis_stick_t *out)
{
    int rows, w, g, core_h, nb, rows_clean, bot_idx, top_idx, first_in = -1, last_in = -1;
    float noise, s_w, search, cut, h_row = 0.0f, h_sigma = 1.0e3f;
    line_t line;
    unsigned n_meas, n_in = 0, n_cand = 0, min_meas;
    bool have_h, bottom_known = false;
    float sw = 0.0f, syy = 0.0f, sres = 0.0f, sres_unw = 0.0f, svar = 0.0f, chi = 1.0f;
    float pol_sum = 0.0f;

    if (strip == NULL || prior == NULL || wk == NULL || out == NULL || strip->px == NULL) {
        return GL_ERR_PARAM;
    }
    memset(out, 0, sizeof(*out));
    rows = (int)strip->height;
    w = (int)strip->width;
    have_h = prior->have_horizon;
    if (rows < 32 || rows > (int)GL_VIS_STRIP_MAX_H || w < 24 || w > (int)GL_VIS_STRIP_MAX_W ||
        strip->stride < strip->width || !isfinite(prior->x) || !isfinite(prior->row) ||
        !isfinite(prior->slant) || !isfinite(prior->width_px) || !isfinite(prior->search_px) ||
        fabsf(prior->slant) > 0.2f ||
        (have_h && (!isfinite(prior->horizon_row) || !isfinite(prior->horizon_tol_rows)))) {
        return GL_ERR_PARAM;
    }
    nb = (prior->bin_rows >= 16u) ? 16 : ((prior->bin_rows >= 4u) ? 4 : 1);
    min_meas = (nb == 1) ? MIN_FIT_ROWS : ((nb == 4) ? 6u : 4u);
    out->x0 = strip->x0;
    out->y0 = strip->y0;
    out->strip_rows = strip->height;
    out->bin_rows = (uint8_t)nb;
    out->base = (uint8_t)GL_VIS_BASE_UNKNOWN;

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

    /* ---- the turf edge beside the stick: only the rows above it are clean ---- */
    noise = noise_estimate_(strip, 0, wk->tmp, GL_VIS_STRIP_MAX_H);
    rows_clean = rows;
    if (have_h) {
        const float tol = gl_clampf((prior->horizon_tol_rows > 0.0f) ? prior->horizon_tol_rows
                                                                      : 40.0f, 4.0f, 240.0f);
        const float hp = gl_clampf(prior->horizon_row - (float)strip->y0, -1000.0f, 1000.0f);
        float hl = 0.0f;
        if (local_horizon_(strip, wk, &line, gl_roundi(hp), (int)tol, noise, &hl) &&
            fabsf(hl - hp) <= tol) {
            h_row = hl;
            h_sigma = 0.3f;
            out->horizon_found = true;
        } else {
            h_row = hp;
            h_sigma = 0.5f * tol;
            /* a tight prior (from the band's own horizon samples) is as good */
            out->horizon_found = (h_sigma <= 3.0f);
        }
        out->horizon_row = h_row + (float)strip->y0;
        rows_clean = gl_clampi((int)floorf(h_row - 0.5f), 0, rows);
        if (rows_clean < 32) {
            return GL_ERR_NO_STICK; /* nothing but turf in this strip */
        }
        noise = noise_estimate_(strip, rows_clean, wk->tmp, GL_VIS_STRIP_MAX_H);
    }
    out->noise_sigma = noise;

    /* ---- pass A: wide search along the prior ---- */
    n_meas = measure_all_(strip, wk, &line, rows_clean, nb, search, s_w, noise);
    out->rows_measured = (uint16_t)(n_meas * (unsigned)nb);
    if (n_meas < min_meas) {
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
    if (n_in < min_meas || fabsf(line.b) > 0.15f) {
        out->rows_used = (uint16_t)(n_in * (unsigned)nb);
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
    n_meas = measure_all_(strip, wk, &line, rows_clean, nb, search, s_w, noise);
    out->rows_measured = (uint16_t)(n_meas * (unsigned)nb);
    if (n_meas < min_meas) {
        return GL_ERR_NO_STICK;
    }
    flag_wide_(wk, rows);
    cut = search;
    for (int it = 0; it < 5; it++) {
        cut = robust_cut_(wk, rows, &line, cut);
        n_in = irls_step_(wk, rows, &line, cut);
    }
    if (n_in < min_meas || fabsf(line.b) > 0.15f) {
        out->rows_used = (uint16_t)(n_in * (unsigned)nb);
        return GL_ERR_NO_STICK;
    }

    /* ---- inliers, covariance ---- */
    n_in = 0;
    for (int r = 0; r < rows; r++) {
        if ((wk->flag[r] & (GL_VIS_ROW_MEASURED | GL_VIS_ROW_WIDE)) == GL_VIS_ROW_MEASURED) {
            float res = wk->x[r] - line_at_(&line, (float)r);
            n_cand++;
            if (fabsf(res) < cut) {
                float dy = (float)r - line.rc;
                wk->flag[r] |= GL_VIS_ROW_INLIER;
                sw += wk->w[r];
                syy += wk->w[r] * dy * dy;
                sres += wk->w[r] * res * res;
                sres_unw += res * res;
                svar += 1.0f / wk->w[r];
                pol_sum += ((wk->flag[r] & GL_VIS_ROW_NEG) != 0u) ? -wk->flux[r] : wk->flux[r];
                if (first_in < 0) {
                    first_in = r;
                }
                last_in = r;
                n_in++;
            }
        }
    }
    out->rows_used = (uint16_t)(n_in * (unsigned)nb);
    if (n_in < min_meas || n_in < 3u || !(sw > 0.0f)) {
        return GL_ERR_NO_STICK;
    }
    /* Is this a line at all?  Random row centroids (noise, texture) also
     * "fit" a line if the cut-off stays wide: demand that the rows scatter
     * no more than their own errors allow and that most of them agree. */
    {
        const float pred = sqrtf(svar / (float)n_in);
        const float lim = (SCATTER_VS_PREDICTED * pred > MAX_LINE_SCATTER_PX)
                              ? (SCATTER_VS_PREDICTED * pred) : MAX_LINE_SCATTER_PX;
        const float cut_lim = (5.0f * pred > MAX_FINAL_CUT_PX) ? (5.0f * pred) : MAX_FINAL_CUT_PX;
        if (cut > cut_lim || sqrtf(sres_unw / (float)n_in) > lim ||
            (float)n_in < MIN_INLIER_FRACTION * (float)n_cand) {
            return GL_ERR_NO_STICK;
        }
    }
    chi = sres / (float)(n_in - 2u);
    out->chi2_red = chi;
    if (chi < 1.0f) {
        chi = 1.0f;
    }
    /* Background texture makes the errors of neighbouring rows alike, so n
     * rows are worth fewer than n independent ones.  Inflate the variance
     * by (1 + rho) / (1 - rho) with rho the lag-one autocorrelation of the
     * residuals (AR(1) effective sample size). */
    {
        float num = 0.0f, den = 0.0f, rho;
        for (int r = 0; r + nb < rows; r++) {
            if ((wk->flag[r] & wk->flag[r + nb] & GL_VIS_ROW_INLIER) != 0u) {
                float ra = wk->x[r] - line_at_(&line, (float)r);
                float rb = wk->x[r + nb] - line_at_(&line, (float)(r + nb));
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

    /* ---- extent: ends of the line from the forced amplitude profile ---- */
    row_geom_(s_w, &core_h, &g);
    (void)core_h;
    wk->flank_off = (uint8_t)g;
    forced_amp_(strip, wk, &line, g, s_w);
    {
        /* noise of a matched amplitude: pixel noise under the template
         * (sum g^2 ~ sqrt(pi) s_w) plus that of the background (1 / FLANK_W) */
        const float amp_noise = noise * sqrtf(1.0f / (1.7724539f * s_w) + 1.0f / (float)FLANK_W);
        const int mid = gl_clampi(gl_roundi(line.rc), 0, rows_clean - 1);
        unsigned n = 0;
        float ref, pol = 0.0f, bg_tol, cross = 0.0f, end_sigma;
        int edge = 0, res_t, res_b;

        for (int r = 0; r < rows; r++) {
            if ((wk->flag[r] & (GL_VIS_ROW_INLIER | ROW_FORCED)) ==
                (GL_VIS_ROW_INLIER | ROW_FORCED)) {
                wk->tmp[n++] = fabsf(wk->flux[r]);
            }
        }
        ref = (n >= 3u) ? gl_median_inplace(wk->tmp, n) : 0.0f;
        if (nb > 1 || !(ref > 4.0f * amp_noise)) {
            /* faint: the mean SIGNED amplitude between the outermost inliers */
            float sum = 0.0f;
            n = 0;
            for (int r = first_in - nb / 2; r <= last_in + (nb - 1) / 2; r++) {
                if (r >= 0 && r < rows_clean && (wk->flag[r] & ROW_FORCED) != 0u) {
                    sum += wk->flux[r];
                    n++;
                }
            }
            ref = (n > 0u) ? fabsf(sum) / (float)n : 0.0f;
            pol = (sum >= 0.0f) ? 1.0f : -1.0f;
        }
        if (!(ref > 0.0f)) {
            return GL_ERR_NO_STICK;
        }
        end_sigma = gl_clampf(0.15f + 2.0f * (amp_noise / ref) * (amp_noise / ref), 0.15f, 8.0f);
        /* two rows have "the same background" within the noise of a flank
         * mean, or a small fraction of the line amplitude */
        bg_tol = 2.0f * noise + 0.15f * ref;

        bot_idx = (last_in >= 0) ? last_in : (rows_clean - 1);
        top_idx = (first_in >= 0) ? first_in : 0;

        /* -- top -- */
        res_t = find_end_(wk, 0, rows_clean - 1, mid, -1, ref, pol, amp_noise, bg_tol, &cross,
                          &edge);
        if (res_t < 0) {
            return GL_ERR_NO_STICK; /* too faint to be told from the noise */
        }
        out->top_in_frame = (res_t == 1);
        out->top_row = (float)strip->y0; /* not valid unless top_in_frame */
        if (res_t == 1) {
            /* What is beyond the top?  Clean background has equal flanks and
             * the level it has behind the stick's upper rows; cloth or
             * foliage does not. */
            const float thr = (4.0f * noise > 0.3f * ref) ? (4.0f * noise) : (0.3f * ref);
            unsigned bad = 0, seen = 0;
            float bg_in = 0.0f;
            n = 0;
            for (int k = 2; k <= 9; k++) {
                const int rr = edge + k;
                if (rr < rows_clean && (wk->flag[rr] & ROW_FORCED) != 0u) {
                    wk->tmp[n++] = wk->m2[rr];
                }
            }
            if (n >= 3u) {
                bg_in = gl_median_inplace(wk->tmp, n);
            }
            for (int k = 1; k <= 10; k++) {
                const int rr = edge - k;
                if (rr >= 0 && (wk->flag[rr] & ROW_FORCED) != 0u) {
                    seen++;
                    if ((float)wk->peak[rr] > thr || (n >= 3u && fabsf(wk->m2[rr] - bg_in) > thr)) {
                        bad++;
                    }
                }
            }
            out->top_in_clutter = (seen < 3u || bad >= 3u);
            out->top_row = cross + (float)strip->y0;
            top_idx = gl_clampi(edge + 1, 0, mid);
        }

        /* -- lower end, above the turf edge -- */
        res_b = find_end_(wk, 0, rows_clean - 1, mid, 1, ref, pol, amp_noise, bg_tol, &cross,
                          &edge);
        if (res_b < 0) {
            return GL_ERR_NO_STICK;
        }
        if (!have_h) {
            /* no horizon knowledge: the strip is taken as clean throughout */
            bottom_known = (res_b == 1);
            if (res_b == 1) {
                out->bottom_row = cross + (float)strip->y0;
                out->bottom_sigma_rows = end_sigma;
                bot_idx = gl_clampi(edge - 1, mid, rows - 1);
            } else {
                /* the line runs out of the strip: the last row that supported the fit */
                out->bottom_row = (float)bot_idx + 0.5f + (float)strip->y0;
                out->bottom_sigma_rows = 1.0f;
            }
        } else if (res_b == 1 && edge < rows_clean - 2) {
            /* the line ends ABOVE the turf edge (it lost its contrast there,
             * or it is not standing on this ground): base unknown */
            out->bottom_row = cross + (float)strip->y0;
            out->bottom_sigma_rows = end_sigma;
            bot_idx = gl_clampi(edge - 1, mid, rows_clean - 1);
        } else {
            /* the line reaches the turf edge: is it seen in the turf below? */
            const int t0 = (int)ceilf(h_row + 0.5f);
            float end = 0.0f, sig = 0.5f, z = 0.0f;
            bot_idx = rows_clean - 1;
            if (t0 < rows) {
                z = turf_follow_(strip, wk, &line, g, s_w, t0, t0 + TURF_ROWS - 1, amp_noise, &end,
                                 &sig);
            }
            out->turf_snr = z;
            if (z >= GL_VIS_TURF_MIN_SNR) {
                out->below_horizon_significant = true;
                if (end < (float)t0 + 0.6f) {
                    /* one row, the next one empty: that row may be covered
                     * fully or partly (unknown contrast against turf) */
                    end = (float)t0;
                    if (sig < 0.35f) {
                        sig = 0.35f;
                    }
                }
                out->bottom_row = end + (float)strip->y0;
                out->bottom_sigma_rows = sig;
            } else {
                out->bottom_row = h_row + (float)strip->y0;
                out->bottom_sigma_rows = sqrtf(0.25f + h_sigma * h_sigma);
                if (z >= TURF_HINT_SNR && end - h_row > out->bottom_sigma_rows) {
                    /* not significant, but a hint that the stick goes on
                     * below the edge: the lowest point is that uncertain */
                    out->bottom_sigma_rows = gl_clampf(end - h_row, 0.5f, 12.0f);
                }
            }
            if (h_sigma <= 3.0f) {
                out->base = (uint8_t)((out->below_horizon_significant &&
                                       out->bottom_row - out->horizon_row > GL_VIS_BASE_MARGIN_ROWS)
                                          ? GL_VIS_BASE_VISIBLE : GL_VIS_BASE_AT_HORIZON);
            }
        }

        /* -- rows of the stick, and the significance of the line as a whole -- */
        {
            unsigned inl = 0, nrow = 0, nblk = 0, inblk = 0;
            float sum = 0.0f, blk = 0.0f, sum_blk = 0.0f, z_coh, z_blk = 0.0f;
            for (int r = top_idx; r <= bot_idx; r++) {
                if ((wk->flag[r] & GL_VIS_ROW_MEASURED) != 0u) {
                    wk->flag[r] |= GL_VIS_ROW_PRESENT;
                }
                if ((wk->flag[r] & GL_VIS_ROW_INLIER) != 0u) {
                    inl++;
                }
                if ((wk->flag[r] & ROW_FORCED) != 0u) {
                    sum += wk->flux[r];
                    blk += wk->flux[r];
                    nrow++;
                    if (++inblk == 16u) {
                        sum_blk += fabsf(blk);
                        blk = 0.0f;
                        inblk = 0;
                        nblk++;
                    }
                }
            }
            out->rows_used_frac = gl_clampf((float)(inl * (unsigned)nb) /
                                            (float)(bot_idx - top_idx + 1), 0.0f, 1.0f);
            if (inl < min_meas || out->rows_used_frac < MIN_INLIER_FRACTION) {
                out->rows_used = (uint16_t)(inl * (unsigned)nb);
                return GL_ERR_NO_STICK; /* scattered rows, not a continuous stick */
            }
            /* coherent sum (one polarity), or sums of 16-row blocks whatever
             * their sign (|N(0,1)| has mean 0.798 and sigma 0.603) */
            z_coh = (nrow > 0u) ? fabsf(sum) / (amp_noise * sqrtf((float)nrow)) : 0.0f;
            if (nblk > 0u) {
                const float sb = 4.0f * amp_noise;
                z_blk = (sum_blk - 0.798f * sb * (float)nblk) / (0.603f * sb * sqrtf((float)nblk));
            }
            out->line_snr = (z_coh > z_blk) ? z_coh : z_blk;
            if (out->line_snr < GL_VIS_MIN_LINE_SNR) {
                return GL_ERR_NO_STICK;
            }
        }
    }

    /* ---- without a prior: look for the turf edge at the lower end ---- */
    if (!have_h) {
        float hrow = 0.0f;
        if (bottom_known && local_horizon_(strip, wk, &line, bot_idx, 40, noise, &hrow)) {
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
    int r0, r1, ra = -1, rb = -1;
    float sw = 0.0f, swy = 0.0f, swx = 0.0f, syy = 0.0f, sxy = 0.0f, ybar, xbar;
    unsigned n = 0, nb;

    if (wk == NULL || stick == NULL || out == NULL) {
        return GL_ERR_PARAM;
    }
    memset(out, 0, sizeof(*out));
    nb = (stick->bin_rows > 1u) ? (unsigned)stick->bin_rows : 1u;
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
            if (ra < 0) {
                ra = r;
            }
            rb = r;
            n++;
        }
    }
    out->rows = (uint16_t)(n * nb);
    if (n * nb < GL_VIS_SEGMENT_MIN_ROWS || n < 1u || !(sw > 0.0f)) {
        return GL_ERR_NO_STICK;
    }
    ybar = swy / sw;
    xbar = swx / sw;
    out->slope = stick->slope;
    if (n * nb >= 24u && n >= 4u) {
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

    /* ---- the part of the error that repeats in every strip ----
     * The flank pixels either side of the line, averaged along the line
     * over the rows of the segment, would be flat if the background were
     * clean: frame noise averages down as 1 / rows.  What remains after a
     * straight line across the 12 columns is taken out is structure that
     * moves with the scene or the sensor, not with the frame; the same
     * structure lies under the line, where it shifts the centroid like
     * noise of that size that never averages out. */
    {
        const float g = (float)wk->flank_off;
        float m[GL_VIS_FLANK_COLS], xs[GL_VIS_FLANK_COLS];
        float sx = 0.0f, sy = 0.0f, sxx = 0.0f, sxy2 = 0.0f, rss = 0.0f, var = 0.0f;
        unsigned cnt = 0;

        for (unsigned j = 0; j < GL_VIS_FLANK_COLS; j++) {
            m[j] = 0.0f;
            xs[j] = (j < FLANK_STORE) ? -(g + (float)(FLANK_STORE - 1u - j))
                                      : (g + (float)(j - FLANK_STORE));
        }
        for (int r = ra - (int)(nb / 2u); r <= rb + (int)((nb - 1u) / 2u); r++) {
            if (r >= 0 && r < (int)stick->strip_rows && (wk->flag[r] & ROW_FORCED) != 0u &&
                wk->flank[r][0] != (int8_t)FLANK_INVALID) {
                for (unsigned j = 0; j < GL_VIS_FLANK_COLS; j++) {
                    m[j] += (float)wk->flank[r][j];
                }
                cnt++;
            }
        }
        if (cnt >= GL_VIS_SEGMENT_MIN_ROWS && stick->noise_sigma > 0.0f) {
            const float nn = (float)GL_VIS_FLANK_COLS;
            float a, b, den, s2, kx;
            for (unsigned j = 0; j < GL_VIS_FLANK_COLS; j++) {
                m[j] *= 0.5f / (float)cnt; /* half grey levels -> grey */
                sx += xs[j];
                sy += m[j];
                sxx += xs[j] * xs[j];
                sxy2 += xs[j] * m[j];
            }
            den = nn * sxx - sx * sx;
            b = (den > 1e-6f) ? ((nn * sxy2 - sx * sy) / den) : 0.0f;
            a = (sy - b * sx) / nn;
            for (unsigned j = 0; j < GL_VIS_FLANK_COLS; j++) {
                const float e = m[j] - (a + b * xs[j]);
                rss += e * e;
            }
            /* unbiased: minus what frame noise (and the half-grey rounding
             * of the stored flanks) leaves in a mean of cnt rows */
            s2 = rss / (nn - 2.0f) -
                 (stick->noise_sigma * stick->noise_sigma + 0.0208f) / (float)cnt;
            /* px^2 of centroid error per grey^2 of per-row pixel noise */
            kx = (float)(n * nb) / (stick->noise_sigma * stick->noise_sigma * sw);
            var = s2 * kx;
        }
        /* sub-pixel phase bias of a narrow line that stays on one column */
        if (fabsf(out->slope) * (float)(rb - ra + (int)nb) < 1.0f) {
            float d = PHASE_BIAS_SIGMA_KNEE_PX - stick->width_px;
            float bias = PHASE_BIAS_FLOOR_PX + PHASE_BIAS_PER_PX * ((d > 0.0f) ? d : 0.0f);
            if (bias > PHASE_BIAS_MAX_PX) {
                bias = PHASE_BIAS_MAX_PX;
            }
            var += bias * bias;
        }
        out->static_var_px2 = var;
        out->sigma_static_px = (var > 0.0f) ? sqrtf(var) : 0.0f;
    }
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
    float xr, yr, slope, sigma, static_var;
} rect_line_t;

static void rect_line_(const gl_vis_segment_t *s, const gl_cam_model_t *cam, float f_ref,
                       rect_line_t *out)
{
    if (cam == NULL) {
        out->xr = s->x_mid;
        out->yr = s->row_mid;
        out->slope = s->slope;
        out->sigma = s->sigma_x;
        out->static_var = s->static_var_px2;
        return;
    }
    {
        const float h = 8.0f;
        const float k = f_ref / cam->fx;
        float xa, ya, xb, yb, xm, ym;
        gl_cam_pixel_to_rectified(cam, s->x_mid - s->slope * h, s->row_mid - h, &xa, &ya);
        gl_cam_pixel_to_rectified(cam, s->x_mid + s->slope * h, s->row_mid + h, &xb, &yb);
        gl_cam_pixel_to_rectified(cam, s->x_mid, s->row_mid, &xm, &ym);
        /* scale to pixels of the reference focal length */
        out->xr = f_ref * xm;
        out->yr = f_ref * ym;
        out->slope = (fabsf(yb - ya) > 1e-9f) ? ((xb - xa) / (yb - ya)) : 0.0f;
        out->sigma = s->sigma_x * k;
        out->static_var = s->static_var_px2 * k * k;
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
    float y, st;
    if (left == NULL || right == NULL || disparity_px == NULL || sigma_px == NULL ||
        left->rows < GL_VIS_SEGMENT_MIN_ROWS || right->rows < GL_VIS_SEGMENT_MIN_ROWS ||
        ((cam_l == NULL) != (cam_r == NULL))) {
        return GL_ERR_PARAM;
    }
    rect_line_(left, cam_l, f_ref, &l);
    rect_line_(right, cam_r, f_ref, &r);
    y = 0.5f * (l.yr + r.yr);
    *disparity_px = rect_at_(&l, y) - rect_at_(&r, y);
    st = ((l.static_var > 0.0f) ? l.static_var : 0.0f) + ((r.static_var > 0.0f) ? r.static_var : 0.0f);
    *sigma_px = sqrtf(l.sigma * l.sigma + r.sigma * r.sigma + st);
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
    /* the static parts: the same error in both strips of a camera, and in
     * every group.  The per-strip estimates are unbiased but noisy (they
     * may be negative): they are averaged here and clipped in the result. */
    a->sum_static2_l += 0.5f * (l1.static_var + l2.static_var);
    a->sum_static2_r += 0.5f * (r1.static_var + r2.static_var);
    /* L1 and L2 are three frame intervals apart */
    a->sum_sway += (rect_at_(&l2, y) - rect_at_(&l1, y)) / 3.0f;
    if (a->n < 0xFFFFu) {
        a->n++;
    }
    return GL_OK;
}

gl_status_t gl_vis_disp_acc_result(const gl_vis_disp_acc_t *a, gl_vis_disparity_t *out)
{
    float formal, n, sl, sr;
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
    out->sigma_noise_px = formal;
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
            if (sem > out->sigma_noise_px) {
                out->sigma_noise_px = sem;
            }
        }
    }
    sl = a->sum_static2_l / n;
    sr = a->sum_static2_r / n;
    out->sigma_static_px = sqrtf(((sl > 0.0f) ? sl : 0.0f) + ((sr > 0.0f) ? sr : 0.0f));
    out->sigma_px = sqrtf(out->sigma_noise_px * out->sigma_noise_px +
                          out->sigma_static_px * out->sigma_static_px);
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
    out->top_valid = s->top_in_frame && !s->top_in_clutter;
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
    memset(out, 0, sizeof(*out));
    if (left == NULL) {
        return;
    }
    out->line_contrast = left->contrast;
    out->rows_used_frac = left->rows_used_frac;
    out->contrast_snr = (left->noise_sigma > 0.0f) ? (left->contrast / left->noise_sigma) : 0.0f;
    if (right != NULL) {
        const float wl = left->width_px, wr = right->width_px;
        const float cl = left->contrast, cr = right->contrast;
        const float noise = (left->noise_sigma > right->noise_sigma) ? left->noise_sigma
                                                                     : right->noise_sigma;
        const float wm = (wl > 0.0f && wr > 0.0f) ? ((wl < wr) ? (wl / wr) : (wr / wl)) : 0.0f;
        const float cm = (cl > 0.0f && cr > 0.0f) ? ((cl < cr) ? (cl / cr) : (cr / cl)) : 0.0f;
        out->line_contrast = (cl < cr) ? cl : cr;
        out->contrast_snr = (noise > 0.0f) ? (out->line_contrast / noise) : 0.0f;
        if (right->rows_used_frac < out->rows_used_frac) {
            out->rows_used_frac = right->rows_used_frac;
        }
        out->sharpness_match = (wm < cm) ? wm : cm;
    }
    if (stats_left != NULL) {
        out->sat_fraction = stats_left->sat_fraction;
        out->sun = stats_left->sun;
    }
    if (stats_right != NULL) {
        if (stats_right->sat_fraction > out->sat_fraction) {
            out->sat_fraction = stats_right->sat_fraction;
        }
        out->sun = out->sun || stats_right->sun;
    }
}
