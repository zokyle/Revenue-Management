/*
 * test_vision_equiv.c - the run-time work of phase 2 on core/gl_vision.c
 * changed HOW things are computed and must not have changed WHAT is
 * computed.  This test runs the present code and the frozen phase-1 code
 * (tests/vision_ref, symbols glp1_*) on the same pixels with the same
 * priors and demands results that are identical BIT FOR BIT: status codes,
 * every field of the result structures, the per-row measurements the
 * segment fits read, and the segment fits themselves.
 *
 * Scenes come from the reviewers' generator (tests/synth/gl_scene.c): sticks
 * of 0.5 to 9 px at 5 to 60 % contrast in both polarities, leaning, on flat
 * and rising greens, with turf texture, tree lines, people, second poles,
 * flags, glare, fixed-pattern noise, dirty windows, and scenes with no
 * stick at all.  Every strip is refined with several priors: unbinned and
 * with 4 and 16 rows averaged, with and without a horizon prior, with tight
 * and with wide searches, and chained from a previous strip as the read
 * sequence does.
 *
 * Also here: gl_select_inplace() / gl_median_select() against a full sort.
 */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "gl_scene.h"
#include "gl_test.h"
#include "gl_vision.h"
#include "gl_vision_ref.h"

#define F_PX 657.0
#define FB (F_PX * 0.020)
#define DEG (3.14159265358979323846 / 180.0)

#ifndef GL_EQUIV_SCENES
#define GL_EQUIV_SCENES 160
#endif

/* ---- bitwise comparison helpers -------------------------------------------------- */

static int same_f_(float a, float b)
{
    return memcmp(&a, &b, sizeof(a)) == 0;
}

static unsigned n_cmp_, n_diff_;

static void report_(const char *what, const char *field, double a, double b)
{
    n_diff_++;
    if (n_diff_ <= 25u) {
        printf("    DIFF %s.%s: now %.9g, phase 1 %.9g\n", what, field, a, b);
    }
}

#define CMP_F(what, a, b, f)                                   \
    do {                                                       \
        n_cmp_++;                                              \
        if (!same_f_((a).f, (b).f)) {                          \
            report_(what, #f, (double)(a).f, (double)(b).f);   \
        }                                                      \
    } while (0)
#define CMP_I(what, a, b, f)                                   \
    do {                                                       \
        n_cmp_++;                                              \
        if ((a).f != (b).f) {                                  \
            report_(what, #f, (double)(a).f, (double)(b).f);   \
        }                                                      \
    } while (0)

static void cmp_stick_(const gl_vis_stick_t *a, const gl_vis_stick_t *b)
{
    CMP_F("stick", *a, *b, x_ref);
    CMP_F("stick", *a, *b, row_ref);
    CMP_F("stick", *a, *b, slope);
    CMP_F("stick", *a, *b, sigma_x_ref);
    CMP_F("stick", *a, *b, sigma_slope);
    CMP_F("stick", *a, *b, resid_rms_px);
    CMP_F("stick", *a, *b, sigma_scale);
    CMP_F("stick", *a, *b, top_row);
    CMP_I("stick", *a, *b, top_in_frame);
    CMP_I("stick", *a, *b, top_in_clutter);
    CMP_F("stick", *a, *b, bottom_row);
    CMP_F("stick", *a, *b, bottom_sigma_rows);
    CMP_I("stick", *a, *b, below_horizon_significant);
    CMP_F("stick", *a, *b, turf_snr);
    CMP_F("stick", *a, *b, horizon_row);
    CMP_I("stick", *a, *b, horizon_found);
    CMP_I("stick", *a, *b, base);
    CMP_F("stick", *a, *b, contrast);
    CMP_F("stick", *a, *b, width_px);
    CMP_F("stick", *a, *b, noise_sigma);
    CMP_F("stick", *a, *b, line_snr);
    CMP_F("stick", *a, *b, chi2_red);
    CMP_I("stick", *a, *b, bin_rows);
    CMP_F("stick", *a, *b, rows_used_frac);
    CMP_I("stick", *a, *b, rows_used);
    CMP_I("stick", *a, *b, rows_measured);
    CMP_I("stick", *a, *b, polarity);
    CMP_I("stick", *a, *b, x0);
    CMP_I("stick", *a, *b, y0);
    CMP_I("stick", *a, *b, strip_rows);
}

static void cmp_segment_(const gl_vis_segment_t *a, const gl_vis_segment_t *b)
{
    CMP_F("segment", *a, *b, x_mid);
    CMP_F("segment", *a, *b, row_mid);
    CMP_F("segment", *a, *b, slope);
    CMP_F("segment", *a, *b, sigma_x);
    CMP_F("segment", *a, *b, sigma_static_px);
    CMP_F("segment", *a, *b, static_var_px2);
    CMP_I("segment", *a, *b, rows);
}

static void cmp_stats_(const gl_vis_stats_t *a, const gl_vis_stats_t *b)
{
    CMP_F("stats", *a, *b, mean);
    CMP_F("stats", *a, *b, sat_fraction);
    CMP_F("stats", *a, *b, noise_sigma);
    CMP_I("stats", *a, *b, sun);
}

/* ---- 1. selection against a full sort ----------------------------------------------- */

static int cmp_float_(const void *a, const void *b)
{
    const float x = *(const float *)a, y = *(const float *)b;
    return (x > y) - (x < y);
}

static uint32_t lcg_ = 12345u;
static uint32_t rnd_(void)
{
    lcg_ = lcg_ * 1664525u + 1013904223u;
    return lcg_ >> 8;
}

GL_TEST(test_selection_equals_sorting)
{
    static float v[480], w[480], ref[480];
    unsigned cases = 0, bad = 0;

    for (unsigned t = 0; t < 6000u; t++) {
        const unsigned n = 1u + rnd_() % 480u;
        const unsigned kind = t % 8u;
        for (unsigned i = 0; i < n; i++) {
            switch (kind) {
            case 0: v[i] = (float)(rnd_() % 100000u) * 0.001f - 50.0f; break;   /* plain */
            case 1: v[i] = (float)(rnd_() % 7u); break;                       /* many ties */
            case 2: v[i] = (float)i; break;                                   /* sorted */
            case 3: v[i] = (float)(n - i); break;                             /* reversed */
            case 4: v[i] = 3.5f; break;                                       /* constant */
            case 5: v[i] = (rnd_() % 3u == 0u) ? 0.0f : (float)(rnd_() % 512u); break; /* half zero */
            case 6: v[i] = (float)((i < n / 2u) ? i : (n - i)); break;        /* organ pipe */
            default: v[i] = fabsf((float)(rnd_() % 2001u) - 1000.0f) * 0.25f; break;
            }
        }
        memcpy(ref, v, n * sizeof(float));
        qsort(ref, n, sizeof(float), cmp_float_);
        /* the median */
        memcpy(w, v, n * sizeof(float));
        {
            const float m_sel = gl_median_select(w, n);
            float m_old;
            memcpy(w, v, n * sizeof(float));
            m_old = glp1_median_inplace(w, n);
            bad += !same_f_(m_sel, m_old);
        }
        /* a few order statistics */
        for (unsigned q = 0; q < 4u; q++) {
            const unsigned k = (q == 0u) ? 0u : ((q == 1u) ? (n - 1u) : (rnd_() % n));
            float s;
            memcpy(w, v, n * sizeof(float));
            s = gl_select_inplace(w, n, k);
            bad += !same_f_(s, ref[k]);
            bad += !same_f_(w[k], ref[k]);
            /* partitioned about k */
            for (unsigned i = 0; i < n; i++) {
                if ((i < k && w[i] > w[k]) || (i > k && w[i] < w[k])) {
                    bad++;
                    break;
                }
            }
        }
        cases++;
    }
    /* A worst case for this selection: the value at k is always the largest
     * of what is left, so each round removes one element; after
     * GL_SELECT_MAX_ROUNDS rounds the rest is sorted instead.  The result
     * must still be the order statistic. */
    for (unsigned n = 60u; n <= 480u; n += 60u) {
        const unsigned k = n / 2u;
        for (unsigned i = 0; i < n; i++) {
            v[i] = (i < k) ? (float)i : ((i == k) ? 1.0e6f : (float)(1000u + i));
        }
        memcpy(ref, v, n * sizeof(float));
        qsort(ref, n, sizeof(float), cmp_float_);
        memcpy(w, v, n * sizeof(float));
        bad += !same_f_(gl_select_inplace(w, n, k), ref[k]);
        memcpy(w, v, n * sizeof(float));
        bad += !same_f_(gl_median_select(w, n), 0.5f * (ref[n / 2u - 1u] + ref[n / 2u]));
        cases++;
    }
    /* out-of-range k is taken as the largest; n = 0 gives 0 */
    v[0] = 2.0f; v[1] = 1.0f; v[2] = 3.0f;
    GL_CHECK(same_f_(gl_select_inplace(v, 3, 99), 3.0f));
    GL_CHECK(same_f_(gl_select_inplace(v, 0, 0), 0.0f));
    GL_CHECK(same_f_(gl_median_select(v, 0), 0.0f));
    printf("    %u arrays of 1..480 values (ties, sorted, reversed, constant, a worst case): "
           "%u differences from a full sort\n", cases, bad);
    GL_CHECK_EQ(bad, 0u);
}

/* ---- scenes --------------------------------------------------------------------------- */

static gl_scene_t sc_;
static uint8_t band_px_[640 * 96];
static uint8_t strip_px_[2][96 * 480];
static gl_vis_band_work_t bw_new_, bw_old_;
static gl_vis_stick_work_t wk_new_, wk_old_;

static void add_person_(gl_scene_t *s, double xc, double zp, double level)
{
    const double k = F_PX / zp;
    const double feet = s->horizon + F_PX * 0.00561 / zp;
    gl_scene_blob_t *b;
    if (s->n_blob + 3 > GL_SCENE_MAX_BLOB) {
        return;
    }
    b = &s->blob[s->n_blob++];
    b->x = xc; b->w = 0.42 * k; b->top = feet - 1.50 * k; b->bot = feet - 0.80 * k;
    b->level = level; b->disp = FB / zp; b->edge_sigma = 1.0; b->tex = 5.0;
    b = &s->blob[s->n_blob++];
    b->x = xc - 0.12 * k; b->w = 0.13 * k; b->top = feet - 0.82 * k; b->bot = feet;
    b->level = level * 0.8; b->disp = FB / zp; b->edge_sigma = 0.9; b->tex = 4.0;
    b = &s->blob[s->n_blob++];
    b->x = xc + 0.12 * k; b->w = 0.13 * k; b->top = feet - 0.82 * k; b->bot = feet;
    b->level = level * 0.8; b->disp = FB / zp; b->edge_sigma = 0.9; b->tex = 4.0;
}

/* A random scene; returns 1 if it holds a stick. */
static int make_scene_(gl_scene_t *s, gl_scene_rng_t *r, unsigned idx)
{
    static const double widths[10] = { 0.5, 0.7, 0.8, 1.0, 1.5, 2.0, 3.0, 4.5, 6.5, 9.0 };
    static const double contrasts[6] = { 0.05, 0.10, 0.20, 0.30, 0.40, 0.60 };
    const double w_px = widths[idx % 10u];
    const double c = contrasts[(idx / 10u) % 6u] * ((gl_scene_uniform(r) < 0.5) ? 1.0 : -1.0);
    const double z = 0.015 * F_PX / w_px;
    const unsigned extra = (unsigned)(gl_scene_uniform(r) * 14.0);

    gl_scene_defaults(s);
    s->seed = gl_scene_u32(r);
    s->fpn_seed[0] = gl_scene_u32(r);
    s->fpn_seed[1] = gl_scene_u32(r);
    s->sky = 120.0;
    s->turf = 80.0;
    s->turf_tex = (gl_scene_uniform(r) < 0.25) ? 10.0 : 3.0;
    s->horizon = 239.5 + (gl_scene_uniform(r) - 0.5);
    if (gl_scene_uniform(r) < 0.35) {
        s->horizon -= 2.0 + 8.0 * gl_scene_uniform(r); /* a rise behind the hole: base visible */
    }
    s->tree_top = s->horizon;
    s->stick = (idx % 7u != 6u);
    s->s_w = w_px;
    s->s_disp = FB / z;
    s->sx = 130.0 + 380.0 * gl_scene_uniform(r);
    s->s_bot = 239.5 + F_PX * 0.00561 / z + (gl_scene_uniform(r) - 0.5);
    if (s->s_bot < s->horizon) {
        s->s_bot = s->horizon + 0.3;
    }
    s->s_top = s->s_bot - F_PX * 1.96 / z;
    s->s_level = s->sky * (1.0 + c);
    s->s_slope = tan((2.0 * gl_scene_uniform(r) - 1.0) * 3.0 * DEG);
    s->noise = 2.0;
    switch (extra) {
    case 0: s->tree_top = s->horizon - 90.0; s->trees = 60.0; s->tree_tex = 6.0; break;
    case 1: s->tree_top = s->horizon - 90.0; s->trees = 60.0; s->tree_tex = 12.0; break;
    case 2: add_person_(s, s->sx + 0.12 * F_PX / (z + 2.0), z + 2.0, 45.0); break;
    case 3: add_person_(s, s->sx + 0.6 * F_PX / z, z, 45.0); break;
    case 4: {
        gl_scene_pole_t *p = &s->pole[s->n_pole++];
        p->bot = s->horizon + 0.3; p->top = -50.0; p->slope = 0.0;
        p->x = s->sx + ((gl_scene_uniform(r) < 0.5) ? -7.0 : 14.0);
        p->w = 0.5 * s->s_w + 0.5; p->disp = 0.5 * s->s_disp; p->level = s->sky - 50.0;
        break;
    }
    case 5:
        s->flag = 1;
        s->f_top = s->s_top + F_PX * 0.03 / z; s->f_h = F_PX * 0.36 / z; s->f_len = F_PX * 0.5 / z;
        s->f_side = (gl_scene_uniform(r) < 0.5) ? 1 : -1; s->f_hz = 2.0;
        s->f_level = (gl_scene_uniform(r) < 0.5) ? 215.0 : 40.0;
        break;
    case 6: s->fpn_sigma = 1.0; break;
    case 7: s->prnu_sigma = 0.01; s->row_gain = 0.03; break;
    case 8: s->altcol_gain = 0.03; break;
    case 9: s->glare_gx = 0.25; break;
    case 10:
        s->glare_amp = 400.0; s->glare_r = 25.0; s->glare_x = s->sx + 25.0;
        s->glare_y = s->horizon - 50.0;
        break;
    case 11: s->grass_h = 3.0; s->grass_jag = 0.7; break;
    case 12: s->psf[1] = 1.8; s->veil_gain[1] = 0.8; s->veil_off[1] = 20.0; break;
    default: break;
    }
    return s->stick;
}

/* ---- 2. the horizon band ---------------------------------------------------------------- */

static unsigned band_cases_, band_found_;

static void compare_band_(uint32_t seed)
{
    gl_strip_t band;
    gl_vis_band_result_t rn, ro;
    gl_status_t sn, so;
    const int y0 = (int)floor(sc_.horizon + 0.5) - 48;

    gl_scene_render(&sc_, 0, 0, y0, 640, 96, 0.0, seed, band_px_);
    band.px = band_px_;
    band.width = 640;
    band.height = 96;
    band.stride = 640;
    band.x0 = 0;
    band.y0 = (uint16_t)y0;
    memset(&rn, 0, sizeof(rn));
    memset(&ro, 0, sizeof(ro));
    sn = gl_vis_band_analyse(&band, &bw_new_, &rn);
    so = glp1_vis_band_analyse(&band, &bw_old_, &ro);
    band_cases_++;
    band_found_ += (sn == GL_OK) ? 1u : 0u;
    n_cmp_++;
    if (sn != so) {
        report_("band", "status", (double)sn, (double)so);
    }
    CMP_I("band", rn, ro, n_cand);
    for (unsigned i = 0; i < GL_VIS_MAX_CANDIDATES; i++) {
        CMP_F("band.cand", rn.cand[i], ro.cand[i], x);
        CMP_F("band.cand", rn.cand[i], ro.cand[i], ref_row);
        CMP_F("band.cand", rn.cand[i], ro.cand[i], slant);
        CMP_F("band.cand", rn.cand[i], ro.cand[i], score);
        CMP_F("band.cand", rn.cand[i], ro.cand[i], width_px);
        CMP_I("band.cand", rn.cand[i], ro.cand[i], polarity);
        CMP_I("band.cand", rn.cand[i], ro.cand[i], rows);
    }
    for (unsigned i = 0; i < GL_VIS_HORIZON_BINS; i++) {
        n_cmp_ += 2u;
        if (!same_f_(rn.horizon_row[i], ro.horizon_row[i])) {
            report_("band", "horizon_row", (double)rn.horizon_row[i], (double)ro.horizon_row[i]);
        }
        if (!same_f_(rn.horizon_col[i], ro.horizon_col[i])) {
            report_("band", "horizon_col", (double)rn.horizon_col[i], (double)ro.horizon_col[i]);
        }
    }
    CMP_I("band", rn, ro, horizon_valid);
    CMP_F("band", rn, ro, edge_energy_mean);
    cmp_stats_(&rn.stats, &ro.stats);
    /* the work area's documented output and what the search left in it */
    n_cmp_ += 6u;
    if (memcmp(bw_new_.edge_energy, bw_old_.edge_energy, sizeof(bw_new_.edge_energy)) != 0) {
        report_("band", "edge_energy[]", 0.0, 0.0);
    }
    if (memcmp(bw_new_.score, bw_old_.score, sizeof(bw_new_.score)) != 0) {
        report_("band", "score[]", 0.0, 0.0);
    }
    if (memcmp(bw_new_.best_slant, bw_old_.best_slant, sizeof(bw_new_.best_slant)) != 0 ||
        memcmp(bw_new_.best_scale, bw_old_.best_scale, sizeof(bw_new_.best_scale)) != 0 ||
        memcmp(bw_new_.best_blocks, bw_old_.best_blocks, sizeof(bw_new_.best_blocks)) != 0 ||
        memcmp(bw_new_.best_pol, bw_old_.best_pol, sizeof(bw_new_.best_pol)) != 0) {
        report_("band", "best_*[]", 0.0, 0.0);
    }
}

/* ---- 3. the refinement and the segment fits ---------------------------------------------- */

static unsigned ref_cases_, ref_ok_[3], ref_nostick_, seg_cases_, rows_cmp_;

/* Refine one strip with one prior in both implementations and compare
 * everything a caller can see.  Returns the status; *out_new = the result. */
static gl_status_t compare_refine_(const gl_strip_t *strip, const gl_vis_prior_t *prior,
                                   gl_vis_stick_t *out_new)
{
    gl_vis_stick_t sn, so;
    gl_status_t stn, sto;

    memset(&sn, 0, sizeof(sn));
    memset(&so, 0, sizeof(so));
    /* a work area as the read sequence leaves it: whatever the previous
     * strip put there (the second pass must not take over stale rows) */
    stn = gl_vis_stick_refine(strip, prior, &wk_new_, &sn);
    sto = glp1_vis_stick_refine(strip, prior, &wk_old_, &so);
    ref_cases_++;
    n_cmp_++;
    if (stn != sto) {
        report_("refine", "status", (double)stn, (double)sto);
    }
    cmp_stick_(&sn, &so);
    if (stn == GL_OK && sto == GL_OK) {
        const unsigned bi = (sn.bin_rows >= 16u) ? 2u : ((sn.bin_rows >= 4u) ? 1u : 0u);
        const uint8_t pub = (uint8_t)(GL_VIS_ROW_MEASURED | GL_VIS_ROW_INLIER | GL_VIS_ROW_WIDE |
                                      GL_VIS_ROW_NEG | GL_VIS_ROW_PRESENT);
        static const float span[4][2] = { { 60.0f, 2.0f }, { 200.0f, 2.0f }, { 30.0f, 0.0f },
                                          { 400.0f, 120.0f } };
        ref_ok_[bi]++;
        /* per-row measurements: flags, position and weight of every row */
        for (unsigned r = 0; r < strip->height; r++) {
            rows_cmp_++;
            if ((wk_new_.flag[r] & pub) != (wk_old_.flag[r] & pub)) {
                report_("row", "flag", (double)(wk_new_.flag[r] & pub),
                        (double)(wk_old_.flag[r] & pub));
            }
            if (!same_f_(wk_new_.x[r], wk_old_.x[r]) || !same_f_(wk_new_.w[r], wk_old_.w[r])) {
                report_("row", "x / w", (double)wk_new_.x[r], (double)wk_old_.x[r]);
            }
        }
        n_cmp_ += 2u * strip->height;
        CMP_I("work", wk_new_, wk_old_, flank_off);
        /* segment fits over the lowest part, a long part, a short part and
         * a part higher up: values and the static-error estimate (which
         * reads the stored flank pixels) */
        for (unsigned k = 0; k < 4u; k++) {
            gl_vis_segment_t gn, go;
            gl_status_t a, b;
            const float hi = sn.bottom_row - span[k][1];
            memset(&gn, 0, sizeof(gn));
            memset(&go, 0, sizeof(go));
            a = gl_vis_stick_segment(&wk_new_, &sn, hi - span[k][0], hi, &gn);
            b = glp1_vis_stick_segment(&wk_old_, &so, hi - span[k][0], hi, &go);
            seg_cases_++;
            n_cmp_++;
            if (a != b) {
                report_("segment", "status", (double)a, (double)b);
            }
            cmp_segment_(&gn, &go);
        }
    } else {
        ref_nostick_++;
    }
    *out_new = sn;
    return stn;
}

static float band_width_(double w_px)
{
    return (w_px < 2.0) ? 1.0f : ((w_px < 5.0) ? 3.0f : ((w_px < 10.0) ? 7.0f : 13.0f));
}

GL_TEST(test_band_and_refinement_are_bit_identical)
{
    gl_scene_rng_t rng;
    unsigned n_stick = 0;

    gl_scene_seed(&rng, 0x5EED2026ull);
    memset(&wk_new_, 0, sizeof(wk_new_));
    memset(&wk_old_, 0, sizeof(wk_old_));
    for (unsigned i = 0; i < (unsigned)GL_EQUIV_SCENES; i++) {
        const int has = make_scene_(&sc_, &rng, i);
        const uint32_t fs = gl_scene_u32(&rng);
        n_stick += (unsigned)has;
        compare_band_(fs);
        for (int cam = 0; cam < 2; cam++) {
            const double xs = has ? gl_scene_stick_x(&sc_, cam, 240.0, 0.0)
                                  : (100.0 + 400.0 * gl_scene_uniform(&rng));
            int x0 = (int)floor(xs + 0.5) - 48 + (int)(gl_scene_uniform(&rng) * 20.0) - 10;
            gl_strip_t strip;
            gl_vis_prior_t p;
            gl_vis_stick_t first, tmp;
            gl_status_t st;

            if (x0 < 0) {
                x0 = 0;
            }
            if (x0 > 640 - 96) {
                x0 = 640 - 96;
            }
            for (int f = 0; f < 2; f++) {
                gl_scene_render(&sc_, cam, x0, 0, 96, 480, 0.033 * (double)f,
                                fs + 17u * (unsigned)(cam + 1) + 101u * (unsigned)f, strip_px_[f]);
            }
            strip.px = strip_px_[0];
            strip.width = 96;
            strip.height = 480;
            strip.stride = 96;
            strip.x0 = (uint16_t)x0;
            strip.y0 = 0;

            /* a) as the read sequence starts: from the band's candidate,
             *    with the band's horizon, unbinned, then 4 and 16 rows */
            memset(&p, 0, sizeof(p));
            p.row = (float)floor(sc_.horizon + 0.5) - 48.0f + 5.5f;
            p.x = (float)(has ? gl_scene_stick_x(&sc_, cam, (double)p.row, 0.0) : xs) +
                  (float)(4.0 * gl_scene_uniform(&rng) - 2.0);
            p.slant = (float)sc_.s_slope + (float)(0.01 * (gl_scene_uniform(&rng) - 0.5));
            p.width_px = band_width_(sc_.s_w);
            p.search_px = (cam == 0) ? 5.0f : 8.5f;
            p.have_horizon = true;
            p.horizon_row = (float)sc_.horizon + (float)(3.0 * gl_scene_uniform(&rng) - 1.5);
            p.horizon_tol_rows = 6.0f;
            p.bin_rows = 1;
            st = compare_refine_(&strip, &p, &first);
            p.bin_rows = 4;
            (void)compare_refine_(&strip, &p, &tmp);
            p.bin_rows = 16;
            (void)compare_refine_(&strip, &p, &tmp);

            /* b) the next strip of the same camera, prior from the previous
             *    result, default search (the read sequence's steady state) */
            if (st == GL_OK) {
                gl_vis_prior_t q = p;
                q.x = first.x_ref;
                q.row = first.row_ref;
                q.slant = first.slope;
                q.search_px = 0.0f;
                q.horizon_row = first.horizon_found ? first.horizon_row : p.horizon_row;
                q.bin_rows = first.bin_rows;
                strip.px = strip_px_[1];
                (void)compare_refine_(&strip, &q, &tmp);
                strip.px = strip_px_[0];
            }

            /* c) the calibrated horizon row only (wide tolerance), a wide
             *    search from a prediction 9 px off */
            p.bin_rows = 1;
            p.x += 9.0f;
            p.search_px = 12.0f;
            p.horizon_row = 239.5f;
            p.horizon_tol_rows = 48.0f;
            (void)compare_refine_(&strip, &p, &tmp);

            /* d) no horizon knowledge at all (the line fit's unit-test mode) */
            p.x -= 9.0f;
            p.search_px = 0.0f;
            p.have_horizon = false;
            (void)compare_refine_(&strip, &p, &tmp);
            p.bin_rows = 4;
            (void)compare_refine_(&strip, &p, &tmp);

            /* e) strip statistics */
            {
                gl_vis_stats_t a, b;
                memset(&a, 0, sizeof(a));
                memset(&b, 0, sizeof(b));
                gl_vis_strip_stats(&strip, wk_new_.tmp, &a);
                glp1_vis_strip_stats(&strip, wk_old_.tmp, &b);
                cmp_stats_(&a, &b);
            }
        }
    }
    printf("    %u scenes (%u with a stick): %u bands (%u with a candidate), %u refinements "
           "(a line in %u unbinned, %u with 4 rows, %u with 16 rows; %u none), %u segment fits,\n"
           "    %u rows compared; %u values compared in all: %u differ from the phase-1 code\n",
           (unsigned)GL_EQUIV_SCENES, n_stick, band_cases_, band_found_, ref_cases_, ref_ok_[0],
           ref_ok_[1], ref_ok_[2], ref_nostick_, seg_cases_, rows_cmp_, n_cmp_, n_diff_);
    GL_CHECK_EQ(n_diff_, 0u);
    /* the comparison must have had something to compare */
    GL_CHECK(band_found_ * 2u > band_cases_);
    GL_CHECK(ref_ok_[0] > 100u);
    GL_CHECK(ref_ok_[1] > 50u);
    GL_CHECK(ref_ok_[2] > 20u);
    GL_CHECK(ref_nostick_ > 50u);
}

int main(void)
{
    GL_RUN(test_selection_equals_sorting);
    GL_RUN(test_band_and_refinement_are_bit_identical);
    return gl_test_summary();
}
