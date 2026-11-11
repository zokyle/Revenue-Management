/*
 * test_vision.c - flagstick vision on synthetic strips (tests/synth).
 *
 * The numbers printed by these tests are the measured accuracy figures
 * quoted in the README.  Definitions used throughout:
 *   SNR        = |stick grey level - background grey level| / noise sigma,
 *                i.e. the contrast of a fully resolved stick.  A stick
 *                narrower than a pixel has a proportionally lower peak.
 *   lens blur  = Gaussian PSF sigma 0.6 px unless stated.
 *   disparity  = x_left - x_right of the fitted axis at matching rows over
 *                the lowest N rows of the stick (N = 40 unless stated).
 */
#include <stdlib.h>

#include "gl_config.h"
#include "gl_synth.h"
#include "gl_test.h"
#include "gl_vision.h"

#define SW 96
#define SH 480
#define SX0 272 /* strip columns 272..367 */

static uint8_t img[4][SW * SH];
static uint8_t band_img[640 * 96];
static gl_vis_stick_work_t wk[4];
static gl_vis_band_work_t bw;

static gl_strip_t strip_of(int i)
{
    gl_strip_t s = { img[i], SW, SH, SW, SX0, 0 };
    return s;
}

/* Standard stick-strip scene: background 110, turf 70 below row 330, a
 * bright stick ending in front of the far background at `bottom`. */
static void scene_init(gl_synth_scene_t *s, float width, float contrast, float noise)
{
    gl_synth_defaults(s, SW, SH, SX0, 0);
    s->horizon_row = 330.5f;
    s->stick_present = true;
    s->stick_width_px = width;
    s->stick_level = s->bg_level + contrast;
    s->stick_ref_row = 300.0f;
    s->stick_bottom_row = 300.0f;
    s->stick_top_row = -1000.0f;
    s->noise_sigma = noise;
}

/* ---------------------------------------------------------------------- */

GL_TEST(test_renderer_sanity)
{
    gl_synth_scene_t s;
    scene_init(&s, 1.5f, 60.0f, 0.0f);
    s.stick_x = 320.37f;
    gl_synth_render(&s, img[0]);
    /* background and turf levels */
    GL_CHECK_EQ(img[0][10 * SW + 5], 110);
    GL_CHECK_EQ(img[0][400 * SW + 5], 70);
    /* the horizon row itself is a blend */
    GL_CHECK(img[0][331 * SW + 5] > 70 && img[0][330 * SW + 5] <= 110);
    /* stick: flux = contrast x width, centroid at the sub-pixel position */
    for (int row = 50; row < 290; row += 60) {
        double flux = 0, mom = 0;
        for (int c = 0; c < SW; c++) {
            double v = (double)img[0][row * SW + c] - 110.0;
            flux += v;
            mom += v * (SX0 + c);
        }
        GL_CHECK_NEAR(flux, 60.0 * 1.5, 1.5);
        GL_CHECK_NEAR(mom / flux, 320.37, 0.02);
    }
    /* nothing below the bottom end */
    GL_CHECK_EQ(img[0][310 * SW + 48], 110);
    /* a slanted stick moves by slant * rows */
    s.stick_slant = 0.05f;
    gl_synth_render(&s, img[0]);
    {
        double flux = 0, mom = 0;
        for (int c = 0; c < SW; c++) {
            double v = (double)img[0][100 * SW + c] - 110.0;
            flux += v;
            mom += v * (SX0 + c);
        }
        GL_CHECK_NEAR(mom / flux, 320.37 + 0.05 * (100 - 300), 0.02);
    }
    /* noise has the requested sigma */
    s.stick_present = false;
    s.noise_sigma = 3.0f;
    gl_synth_render(&s, img[0]);
    {
        double sum = 0, sum2 = 0;
        int n = 0;
        for (int row = 0; row < 300; row++) {
            for (int c = 0; c < SW; c++) {
                double v = img[0][row * SW + c];
                sum += v;
                sum2 += v * v;
                n++;
            }
        }
        GL_CHECK_NEAR(sum / n, 110.0, 0.1);
        GL_CHECK_NEAR(sqrt(sum2 / n - (sum / n) * (sum / n)), 3.0, 0.1);
    }
}

GL_TEST(test_refine_basic_both_polarities)
{
    for (int pol = 1; pol >= -1; pol -= 2) {
        gl_synth_scene_t s;
        gl_strip_t st = strip_of(0);
        gl_vis_prior_t pr = { 322.0f, 250.0f, 0.0f, 0.0f, 0.0f, false, 0.0f, 0.0f, 0 };
        gl_vis_stick_t r;
        scene_init(&s, 1.5f, 60.0f * (float)pol, 3.0f);
        s.stick_x = 320.37f;
        s.stick_slant = 0.03f;
        s.stick_top_row = 80.4f;
        s.stick_bottom_row = 300.3f;
        gl_synth_render(&s, img[0]);
        GL_CHECK_EQ(gl_vis_stick_refine(&st, &pr, &wk[0], &r), GL_OK);
        GL_CHECK_EQ(r.polarity, pol);
        GL_CHECK_NEAR(gl_vis_stick_x_at(&r, 200.0f), gl_synth_stick_x_at(&s, 200.0f), 0.03);
        GL_CHECK_NEAR(r.slope, 0.03, 0.0005);
        GL_CHECK(r.sigma_x_ref > 0.001f && r.sigma_x_ref < 0.02f);
        GL_CHECK_NEAR(r.bottom_row, 300.3, 0.5);
        GL_CHECK(r.top_in_frame);
        GL_CHECK_NEAR(r.top_row, 80.4, 0.5);
        GL_CHECK(r.rows_used > 200 && r.rows_used <= 221);
        GL_CHECK(r.rows_used_frac > 0.95f);
        GL_CHECK_NEAR(r.noise_sigma, 3.0, 0.7);
        /* peak contrast of a 1.5 px stick behind a 0.6 px blur: about 0.7 x 60 */
        GL_CHECK(r.contrast > 30.0f && r.contrast < 55.0f);
        GL_CHECK(r.width_px > 0.6f && r.width_px < 1.0f);
        GL_CHECK_EQ(r.x0, SX0);
        /* per-row flags: rows of the stick are inliers, rows beyond are not */
        GL_CHECK(wk[0].flag[200] & GL_VIS_ROW_INLIER);
        GL_CHECK(!(wk[0].flag[40] & GL_VIS_ROW_INLIER));
        GL_CHECK(!(wk[0].flag[350] & GL_VIS_ROW_INLIER));
        if (pol < 0) {
            GL_CHECK(wk[0].flag[200] & GL_VIS_ROW_NEG);
        }
    }
    /* parameter checks */
    {
        gl_strip_t st = strip_of(0);
        gl_vis_prior_t pr = { 320.0f, 250.0f, 0.0f, 0.0f, 0.0f, false, 0.0f, 0.0f, 0 };
        gl_vis_stick_t r;
        GL_CHECK_EQ(gl_vis_stick_refine(NULL, &pr, &wk[0], &r), GL_ERR_PARAM);
        st.height = 500;
        GL_CHECK_EQ(gl_vis_stick_refine(&st, &pr, &wk[0], &r), GL_ERR_PARAM);
        st.height = SH;
        pr.x = (float)NAN; /* a non-finite prior is refused, not followed */
        GL_CHECK_EQ(gl_vis_stick_refine(&st, &pr, &wk[0], &r), GL_ERR_PARAM);
        pr.x = 320.0f;
        pr.slant = (float)INFINITY;
        GL_CHECK_EQ(gl_vis_stick_refine(&st, &pr, &wk[0], &r), GL_ERR_PARAM);
        pr.slant = 0.0f;
        pr.x = 5000.0f; /* a prior outside the strip finds nothing */
        GL_CHECK_EQ(gl_vis_stick_refine(&st, &pr, &wk[0], &r), GL_ERR_NO_STICK);
        pr.x = 320.0f;
        st.height = SH;
        st.width = 8;
        GL_CHECK_EQ(gl_vis_stick_refine(&st, &pr, &wk[0], &r), GL_ERR_PARAM);
    }
}

/* ---------------------------------------------------------------------- */
/* Stereo accuracy                                                          */
/* ---------------------------------------------------------------------- */

typedef struct {
    const char *name;
    float width, contrast, noise, slant, tex, psf;
    int seg_rows;
} cond_t;

typedef struct {
    double rms, bias, worst, mean_sigma;
    int n, fails;
} stat_t;

/* One left/right pair at a random position and disparity.  Returns false
 * if any stage refused.  phase_l / phase_r >= 0 force the sub-pixel phase
 * of the stick in each image. */
static bool stereo_trial(const cond_t *c, uint32_t *rng, float phase_l, float phase_r,
                         float *err, float *sigma)
{
    gl_synth_scene_t s;
    gl_strip_t sl = strip_of(0), sr = strip_of(1);
    gl_vis_prior_t pr = { 0.0f, 250.0f, 0.0f, 0.0f, 0.0f, false, 0.0f, 0.0f, 0 };
    gl_vis_stick_t rl, rr;
    gl_vis_segment_t gl, gr;
    float xl, xr, d, sg, bottom, bot;

    if (phase_l >= 0.0f) {
        xl = 321.0f + phase_l;
        xr = 318.0f + phase_r;
    } else {
        float dt = 1.0f + 3.0f * gl_synth_rand_uniform(rng);
        float xc = 315.0f + 10.0f * gl_synth_rand_uniform(rng);
        xl = xc + 0.5f * dt;
        xr = xc - 0.5f * dt;
    }
    bottom = 300.0f + gl_synth_rand_uniform(rng);
    scene_init(&s, c->width, c->contrast, c->noise);
    s.bg_texture_amp = c->tex;
    s.turf_texture_amp = 0.5f * c->tex;
    s.texture_seed = gl_synth_rand_u32(rng);
    s.stick_slant = c->slant;
    s.stick_bottom_row = bottom;
    s.psf_sigma_px = c->psf;
    s.stick_x = xl;
    s.noise_seed = gl_synth_rand_u32(rng);
    gl_synth_render(&s, img[0]);
    s.stick_x = xr;
    s.noise_seed = gl_synth_rand_u32(rng);
    gl_synth_render(&s, img[1]);
    /* the prior from the band is good to a couple of pixels */
    pr.x = xl - c->slant * 50.0f + 4.0f * (gl_synth_rand_uniform(rng) - 0.5f);
    if (gl_vis_stick_refine(&sl, &pr, &wk[0], &rl) != GL_OK) {
        return false;
    }
    pr.x = xr - c->slant * 50.0f + 4.0f * (gl_synth_rand_uniform(rng) - 0.5f);
    if (gl_vis_stick_refine(&sr, &pr, &wk[1], &rr) != GL_OK) {
        return false;
    }
    bot = (rl.bottom_row < rr.bottom_row) ? rl.bottom_row : rr.bottom_row;
    if (gl_vis_stick_segment(&wk[0], &rl, bot - 2.0f - (float)c->seg_rows, bot - 2.0f, &gl) !=
            GL_OK ||
        gl_vis_stick_segment(&wk[1], &rr, bot - 2.0f - (float)c->seg_rows, bot - 2.0f, &gr) !=
            GL_OK ||
        gl_vis_stereo_pair(&gl, &gr, NULL, NULL, GL_CFG_CAM_F_PX, &d, &sg) != GL_OK) {
        return false;
    }
    *err = d - (xl - xr);
    *sigma = sg;
    return true;
}

static stat_t run_cond(const cond_t *c, int trials, uint32_t seed)
{
    stat_t st = { 0, 0, 0, 0, 0, 0 };
    double s1 = 0, s2 = 0, ss = 0;
    uint32_t rng = seed;
    for (int t = 0; t < trials; t++) {
        float e, sg;
        if (!stereo_trial(c, &rng, -1.0f, -1.0f, &e, &sg)) {
            st.fails++;
            continue;
        }
        s1 += e;
        s2 += (double)e * e;
        ss += sg;
        if (fabs((double)e) > st.worst) {
            st.worst = fabs((double)e);
        }
        st.n++;
    }
    if (st.n > 0) {
        st.rms = sqrt(s2 / st.n);
        st.bias = s1 / st.n;
        st.mean_sigma = ss / st.n;
    }
    return st;
}

GL_TEST(test_disparity_accuracy_table)
{
    static const cond_t conds[] = {
        { "1.5 px, SNR 20, vertical", 1.5f, 60, 3, 0.000f, 0, 0.6f, 40 },
        { "1.5 px, SNR 20, leaning 2 deg", 1.5f, 60, 3, 0.035f, 0, 0.6f, 40 },
        { "1.5 px, SNR 20, dark on bright", 1.5f, -60, 3, 0.010f, 0, 0.6f, 40 },
        { "1.5 px, SNR 20, 26 rows (0.4 m at 10 m)", 1.5f, 60, 3, 0.010f, 0, 0.6f, 26 },
        { "1.5 px, SNR 20, textured background", 1.5f, 60, 3, 0.020f, 4, 0.6f, 40 },
        { "1.5 px, SNR 10", 1.5f, 30, 3, 0.010f, 0, 0.6f, 40 },
        { "1.5 px, SNR 20, lens blur 1.0 px", 1.5f, 60, 3, 0.010f, 0, 1.0f, 40 },
        { "0.7 px, SNR 20, vertical", 0.7f, 60, 3, 0.000f, 0, 0.6f, 40 },
        { "0.7 px, SNR 20, leaning 0.6 deg", 0.7f, 60, 3, 0.010f, 0, 0.6f, 40 },
        { "0.7 px, SNR 20, 26 rows", 0.7f, 60, 3, 0.010f, 0, 0.6f, 26 },
        { "0.7 px, SNR 20, textured background", 0.7f, 60, 3, 0.020f, 4, 0.6f, 40 },
        { "0.7 px, SNR 20, lens blur 0.4 px", 0.7f, 60, 3, 0.000f, 0, 0.4f, 40 },
        { "0.5 px, SNR 20, 26 rows", 0.5f, 60, 3, 0.010f, 0, 0.6f, 26 },
        { "4 px (3 m), SNR 20, 100 rows", 4.0f, 60, 3, 0.010f, 0, 0.6f, 100 },
        { "8 px (1.5 m), SNR 20, 200 rows", 8.0f, 60, 3, 0.010f, 0, 0.6f, 200 },
    };
    const int trials = 120;
    stat_t st[sizeof(conds) / sizeof(conds[0])];

    printf("    single L/R pair, %d trials per row, random position / disparity / phase:\n",
           trials);
    printf("    %-42s %8s %8s %8s %9s %5s\n", "condition", "RMS px", "bias px", "worst px",
           "claimed", "fail");
    for (size_t i = 0; i < sizeof(conds) / sizeof(conds[0]); i++) {
        st[i] = run_cond(&conds[i], trials, 1000u + (uint32_t)i);
        printf("    %-42s %8.4f %+8.4f %8.3f %9.4f %5d\n", conds[i].name, st[i].rms, st[i].bias,
               st[i].worst, st[i].mean_sigma, st[i].fails);
    }
    /* requirements: <= 0.08 px RMS for a 1.5 px stick at SNR 20 ... */
    for (int i = 0; i <= 3; i++) {
        GL_CHECK(st[i].rms <= 0.08);
        GL_CHECK_EQ(st[i].fails, 0);
        GL_CHECK(fabs(st[i].bias) < 0.01);
    }
    /* ... and <= 0.15 px RMS for a 0.7 px stick */
    for (int i = 7; i <= 9; i++) {
        GL_CHECK(st[i].rms <= 0.15);
        GL_CHECK_EQ(st[i].fails, 0);
        GL_CHECK(fabs(st[i].bias) < 0.02);
    }
    /* The claimed sigma is honest on the plain conditions: never below the
     * scatter by more than a factor 1.6, and not above it by more than 2.2.
     * (It is deliberately on the high side for a vertical stick: the
     * sub-pixel phase bias, 0.009 px per camera and more for a sharp lens,
     * is a systematic error of the pair that the scatter over random phases
     * shows only in part.) */
    for (int i = 0; i <= 3; i++) {
        GL_CHECK(st[i].mean_sigma > st[i].rms / 1.6 && st[i].mean_sigma < st[i].rms * 2.2);
    }
    /* wide, close sticks are the easy case */
    GL_CHECK(st[13].rms < 0.03 && st[14].rms < 0.03);
}

/* Bias against sub-pixel phase: exactly vertical sticks, so every row has
 * the same phase and nothing averages out along the stick.  Two phase
 * relations between the cameras: equal phase and opposite phase (the worst
 * case for an odd bias curve). */
GL_TEST(test_no_bias_across_subpixel_phase)
{
    static const cond_t conds[] = {
        { "1.5 px", 1.5f, 60, 3, 0.0f, 0, 0.6f, 40 },
        { "0.7 px", 0.7f, 60, 3, 0.0f, 0, 0.6f, 40 },
        /* reported for information: a lens sharper than assumed leaves a
         * sub-pixel line more undersampled */
        { "0.7 px, blur 0.4 px", 0.7f, 60, 3, 0.0f, 0, 0.4f, 40 },
    };
    const int per_phase = 36;
    printf("    mean disparity error vs sub-pixel phase (vertical stick, SNR 20, %d trials "
           "per phase):\n", per_phase);
    for (size_t ci = 0; ci < sizeof(conds) / sizeof(conds[0]); ci++) {
        double worst = 0, worst_se = 0;
        uint32_t rng = 4242u + (uint32_t)ci;
        printf("    %s:", conds[ci].name);
        for (int rel = 0; rel < 2; rel++) {
            for (int ph = 0; ph < 10; ph++) {
                double s1 = 0, s2 = 0;
                int n = 0;
                float pl = 0.1f * (float)ph;
                float prr = pl + ((rel == 0) ? 0.0f : 0.5f);
                for (int t = 0; t < per_phase; t++) {
                    float e, sg;
                    if (stereo_trial(&conds[ci], &rng, pl, prr, &e, &sg)) {
                        s1 += e;
                        s2 += (double)e * e;
                        n++;
                    }
                }
                GL_CHECK_EQ(n, per_phase);
                {
                    double mean = s1 / n;
                    double se = sqrt((s2 / n - mean * mean) / n);
                    if (rel == 1) {
                        printf(" %+.3f", mean);
                    }
                    if (fabs(mean) > worst) {
                        worst = fabs(mean);
                        worst_se = se;
                    }
                }
            }
        }
        printf("  (opposite phase)\n");
        printf("    %s: largest |mean error| over 20 phase combinations = %.4f px "
               "(standard error of that mean %.4f)\n", conds[ci].name, worst, worst_se);
        /* requirement: no bias across sub-pixel phase beyond 0.03 px (at
         * the design lens blur); the sharper-lens row is only bounded */
        GL_CHECK(worst <= ((ci < 2) ? 0.03 : 0.08));
    }
}

/* L R R L repeated 8 times with a swaying stick. */
GL_TEST(test_lrrl_cancels_sway)
{
    const float d_true = 2.234f; /* 6 m */
    const cond_t c = { "sway", 1.5f, 60, 3, 0.01f, 0, 0.6f, 40 };
    double e_lrrl = 0, e_naive = 0, e_lrrl2 = 0;
    const int runs = 12;
    uint32_t rng = 9001;

    for (int run = 0; run < runs; run++) {
        gl_vis_disp_acc_t acc;
        gl_vis_disparity_t res;
        const float sway = 0.20f; /* px per frame interval: a steady lean in the wind */
        const float xc = 318.0f + 4.0f * gl_synth_rand_uniform(&rng);
        double naive = 0;
        gl_vis_disp_acc_reset(&acc);
        for (int grp = 0; grp < 8; grp++) {
            gl_vis_segment_t seg[4];
            gl_synth_scene_t s;
            for (int f = 0; f < 4; f++) {
                const bool left = (f == 0 || f == 3);
                const float t = (float)(grp * 4 + f);
                gl_strip_t st = strip_of(f);
                gl_vis_prior_t pr = { 0.0f, 250.0f, 0.0f, 0.0f, 0.0f, false, 0.0f, 0.0f, 0 };
                gl_vis_stick_t r;
                scene_init(&s, c.width, c.contrast, c.noise);
                s.stick_slant = c.slant;
                s.stick_bottom_row = 300.4f;
                /* linear drift plus a slow oscillation */
                s.stick_x = xc + (left ? 0.5f : -0.5f) * d_true + sway * t +
                            0.3f * sinf(0.05f * t);
                s.noise_seed = gl_synth_rand_u32(&rng);
                gl_synth_render(&s, img[f]);
                pr.x = s.stick_x + 1.0f;
                GL_CHECK_EQ(gl_vis_stick_refine(&st, &pr, &wk[f], &r), GL_OK);
                GL_CHECK_EQ(gl_vis_stick_segment(&wk[f], &r, 258.0f, 298.0f, &seg[f]), GL_OK);
            }
            GL_CHECK_EQ(gl_vis_disp_acc_add_lrrl(&acc, seg, NULL, NULL, GL_CFG_CAM_F_PX), GL_OK);
            /* what pairing L1 with R1 only would give */
            naive += (double)(seg[0].x_mid + seg[0].slope * (seg[1].row_mid - seg[0].row_mid)) -
                     (double)seg[1].x_mid;
        }
        GL_CHECK_EQ(gl_vis_disp_acc_result(&acc, &res), GL_OK);
        GL_CHECK_EQ(res.groups, 8);
        e_lrrl += (double)res.disparity_px - d_true;
        e_lrrl2 += ((double)res.disparity_px - d_true) * ((double)res.disparity_px - d_true);
        e_naive += naive / 8.0 - d_true;
        GL_CHECK(res.sigma_px > 0.002f && res.sigma_px < 0.03f);
        GL_CHECK_NEAR(res.sway_px, sway, 0.05);
        GL_CHECK(fabs((double)res.disparity_px - d_true) < 4.0 * (double)res.sigma_px + 0.01);
    }
    printf("    stick swaying 0.20 px per frame, 8 x LRRL: mean error %+.4f px, rms %.4f px; "
           "pairing L with the next R only: mean error %+.4f px\n", e_lrrl / runs,
           sqrt(e_lrrl2 / runs), e_naive / runs);
    GL_CHECK(fabs(e_lrrl / runs) < 0.01);
    GL_CHECK(sqrt(e_lrrl2 / runs) < 0.02);
    GL_CHECK(fabs(e_naive / runs + 0.20) < 0.03); /* the naive pairing carries the sway */
    /* accumulator edge cases */
    {
        gl_vis_disp_acc_t acc;
        gl_vis_disparity_t res;
        gl_vis_segment_t seg[4];
        memset(seg, 0, sizeof(seg));
        gl_vis_disp_acc_reset(&acc);
        GL_CHECK_EQ(gl_vis_disp_acc_result(&acc, &res), GL_ERR_NO_STICK);
        GL_CHECK_EQ(gl_vis_disp_acc_add_lrrl(&acc, seg, NULL, NULL, 657.0f), GL_ERR_PARAM);
    }
}

/* The stick is bright against dark trees in its upper part and dark
 * against a bright sky patch lower down. */
GL_TEST(test_polarity_flips_along_the_stick)
{
    gl_synth_scene_t s;
    gl_strip_t st = strip_of(0);
    gl_vis_prior_t pr = { 321.5f, 250.0f, 0.0f, 0.0f, 0.0f, false, 0.0f, 0.0f, 0 };
    gl_vis_stick_t r;
    int neg = 0, pos = 0;
    scene_init(&s, 1.5f, 60.0f, 3.0f); /* stick level 170 on background 110 */
    s.stick_x = 320.6f;
    s.stick_slant = 0.02f;
    s.stick_bottom_row = 300.3f;
    s.n_clutter = 1; /* a bright wall behind the stick between rows 120 and 220 */
    s.clutter[0].x_left = 200.0f;
    s.clutter[0].x_right = 450.0f;
    s.clutter[0].row_top = 120.0f;
    s.clutter[0].row_bottom = 220.0f;
    s.clutter[0].level = 235.0f;
    gl_synth_render(&s, img[0]);
    GL_CHECK_EQ(gl_vis_stick_refine(&st, &pr, &wk[0], &r), GL_OK);
    for (int row = 0; row < 300; row++) {
        if (wk[0].flag[row] & GL_VIS_ROW_INLIER) {
            if (wk[0].flag[row] & GL_VIS_ROW_NEG) {
                neg++;
            } else {
                pos++;
            }
        }
    }
    GL_CHECK(neg > 80 && pos > 150); /* both parts contribute */
    GL_CHECK_NEAR(gl_vis_stick_x_at(&r, 170.0f), gl_synth_stick_x_at(&s, 170.0f), 0.04);
    GL_CHECK_NEAR(gl_vis_stick_x_at(&r, 280.0f), gl_synth_stick_x_at(&s, 280.0f), 0.04);
    GL_CHECK_NEAR(r.bottom_row, 300.3, 0.6);
    GL_CHECK_EQ(r.polarity, 1);
}

/* ---------------------------------------------------------------------- */
/* Failure modes: nothing there, or something that is not a stick           */
/* ---------------------------------------------------------------------- */

GL_TEST(test_no_stick_fails_gracefully)
{
    int false_strip = 0, false_band = 0;
    const int trials = 60;
    uint32_t rng = 555;

    /* (a) tall strip without a stick: noise, texture, turf horizon */
    for (int t = 0; t < trials; t++) {
        gl_synth_scene_t s;
        gl_strip_t st = strip_of(0);
        gl_vis_prior_t pr = { 300.0f + 40.0f * gl_synth_rand_uniform(&rng), 250.0f, 0.0f, 0.0f,
                              0.0f, false, 0.0f, 0.0f, 0 };
        gl_vis_stick_t r;
        scene_init(&s, 1.5f, 60.0f, 3.0f);
        s.stick_present = false;
        s.bg_texture_amp = (t & 1) ? 6.0f : 0.0f;
        s.turf_texture_amp = 3.0f;
        s.texture_seed = gl_synth_rand_u32(&rng);
        s.noise_seed = gl_synth_rand_u32(&rng);
        gl_synth_render(&s, img[0]);
        if (gl_vis_stick_refine(&st, &pr, &wk[0], &r) != GL_ERR_NO_STICK) {
            false_strip++;
        }
    }
    /* (b) horizon band without a stick */
    for (int t = 0; t < trials; t++) {
        gl_synth_scene_t s;
        gl_strip_t b = { band_img, 640, 96, 640, 0, 192 };
        gl_vis_band_result_t res;
        gl_synth_defaults(&s, 640, 96, 0, 192);
        s.horizon_row = 240.3f;
        s.noise_sigma = 3.0f;
        s.bg_texture_amp = (t % 3 == 0) ? 0.0f : 6.0f;
        s.turf_texture_amp = 3.0f;
        s.texture_scale_px = (t & 1) ? 6.0f : 15.0f;
        s.texture_seed = gl_synth_rand_u32(&rng);
        s.noise_seed = gl_synth_rand_u32(&rng);
        gl_synth_render(&s, band_img);
        gl_status_t stt = gl_vis_band_analyse(&b, &bw, &res);
        if (stt != GL_ERR_NO_STICK || res.n_cand != 0) {
            false_band++;
        }
    }
    printf("    no stick in the scene: %d false sticks in %d tall strips, %d false candidates "
           "in %d horizon bands\n", false_strip, trials, false_band, trials);
    GL_CHECK_EQ(false_strip, 0);
    GL_CHECK_EQ(false_band, 0);

    /* (c) things that are not sticks: a person (40 px wide), the edge of a
     * building (a step), a tree trunk 22 px wide.  Refinement started on
     * their edges must refuse. */
    {
        int accepted = 0;
        for (int kind = 0; kind < 3; kind++) {
            gl_synth_scene_t s;
            gl_strip_t st = strip_of(0);
            gl_vis_stick_t r;
            scene_init(&s, 1.5f, 60.0f, 3.0f);
            s.stick_present = false;
            s.n_clutter = 1;
            s.clutter[0].row_top = -10.0f;
            s.clutter[0].row_bottom = 310.0f;
            s.clutter[0].level = (kind == 1) ? 200.0f : 60.0f;
            s.clutter[0].x_left = 305.3f;
            s.clutter[0].x_right = (kind == 0) ? 345.0f : ((kind == 1) ? 900.0f : 327.6f);
            s.clutter[0].slant = 0.01f;
            gl_synth_render(&s, img[0]);
            for (int edge = 0; edge < 2; edge++) {
                gl_vis_prior_t pr = { edge ? s.clutter[0].x_right : s.clutter[0].x_left, 250.0f,
                                      0.0f, 0.0f, 0.0f, false, 0.0f, 0.0f, 0 };
                if (pr.x > 360.0f) {
                    continue;
                }
                if (gl_vis_stick_refine(&st, &pr, &wk[0], &r) == GL_OK) {
                    accepted++;
                }
            }
        }
        printf("    edges of a person, a wall and a tree trunk accepted as sticks: %d of 5\n",
               accepted);
        GL_CHECK_EQ(accepted, 0);
    }
    /* (d) segment fit and stereo refuse instead of inventing numbers */
    {
        gl_vis_stick_t r;
        gl_vis_segment_t seg, seg2;
        float d, sg;
        gl_synth_scene_t s;
        gl_strip_t st = strip_of(0);
        gl_vis_prior_t pr = { 321.0f, 250.0f, 0.0f, 0.0f, 0.0f, false, 0.0f, 0.0f, 0 };
        scene_init(&s, 1.5f, 60.0f, 3.0f);
        s.stick_x = 320.2f;
        gl_synth_render(&s, img[0]);
        GL_CHECK_EQ(gl_vis_stick_refine(&st, &pr, &wk[0], &r), GL_OK);
        /* rows below the end of the stick: nothing to fit */
        GL_CHECK_EQ(gl_vis_stick_segment(&wk[0], &r, 340.0f, 400.0f, &seg), GL_ERR_NO_STICK);
        GL_CHECK_EQ(gl_vis_stick_segment(&wk[0], &r, 296.0f, 299.0f, &seg), GL_ERR_NO_STICK);
        GL_CHECK_EQ(gl_vis_stick_segment(&wk[0], &r, 250.0f, 290.0f, &seg2), GL_OK);
        GL_CHECK_EQ(gl_vis_stereo_pair(&seg, &seg2, NULL, NULL, 657.0f, &d, &sg), GL_ERR_PARAM);
        /* a shorter strip refined in the same work area: rows beyond its
         * height still hold the previous strip's data and must be ignored */
        st.height = 200;
        GL_CHECK_EQ(gl_vis_stick_refine(&st, &pr, &wk[0], &r), GL_OK);
        GL_CHECK_EQ(r.strip_rows, 200);
        GL_CHECK(!r.top_in_frame && r.bottom_row > 190.0f); /* runs out of the short strip */
        GL_CHECK_EQ(gl_vis_stick_segment(&wk[0], &r, 210.0f, 290.0f, &seg), GL_ERR_NO_STICK);
        GL_CHECK_EQ(gl_vis_stick_segment(&wk[0], &r, 150.0f, 290.0f, &seg), GL_OK);
        GL_CHECK(seg.rows <= 50);
    }
}

/* Flag cloth at the top, a person standing behind the lower part, a shadow
 * band: the fit must come from the clean rows. */
GL_TEST(test_outlier_rejection)
{
    double worst = 0;
    uint32_t rng = 31;
    int wide_rows = 0, trials = 30;
    float frac_sum = 0.0f;
    for (int t = 0; t < trials; t++) {
        gl_synth_scene_t s;
        gl_strip_t st = strip_of(0);
        gl_vis_prior_t pr = { 0.0f, 250.0f, 0.0f, 0.0f, 0.0f, false, 0.0f, 0.0f, 0 };
        gl_vis_stick_t r;
        scene_init(&s, 1.5f, 60.0f, 3.0f);
        s.stick_x = 318.0f + 4.0f * gl_synth_rand_uniform(&rng);
        s.stick_slant = 0.04f * (gl_synth_rand_uniform(&rng) - 0.5f);
        s.stick_top_row = 40.0f;
        s.stick_bottom_row = 300.4f;
        s.n_clutter = 3;
        /* flag cloth: bright, 16 px wide, attached to one side of the top */
        s.clutter[0].x_left = gl_synth_stick_x_at(&s, 60.0f);
        s.clutter[0].x_right = s.clutter[0].x_left + 16.0f;
        s.clutter[0].row_top = 42.0f;
        s.clutter[0].row_bottom = 85.0f;
        s.clutter[0].level = 200.0f;
        /* a dark person 30 px wide whose edge crosses the stick obliquely */
        s.clutter[1].x_left = s.stick_x - 2.0f;
        s.clutter[1].x_right = s.stick_x + 28.0f;
        s.clutter[1].row_top = 150.0f;
        s.clutter[1].row_bottom = 200.0f;
        s.clutter[1].level = 40.0f;
        s.clutter[1].slant = 0.08f;
        /* a thin bright rail right next to the stick for 20 rows */
        s.clutter[2].x_left = s.stick_x + 2.2f;
        s.clutter[2].x_right = s.stick_x + 3.4f;
        s.clutter[2].row_top = 230.0f;
        s.clutter[2].row_bottom = 250.0f;
        s.clutter[2].level = 180.0f;
        s.noise_seed = gl_synth_rand_u32(&rng);
        gl_synth_render(&s, img[0]);
        pr.x = s.stick_x + 2.0f * (gl_synth_rand_uniform(&rng) - 0.5f);
        GL_CHECK_EQ(gl_vis_stick_refine(&st, &pr, &wk[0], &r), GL_OK);
        for (float row = 100.0f; row <= 290.0f; row += 95.0f) {
            double e = fabs((double)gl_vis_stick_x_at(&r, row) -
                            (double)gl_synth_stick_x_at(&s, row));
            if (e > worst) {
                worst = e;
            }
        }
        for (int row = 0; row < SH; row++) {
            if (wk[0].flag[row] & GL_VIS_ROW_WIDE) {
                wide_rows++;
            }
        }
        frac_sum += r.rows_used_frac;
        GL_CHECK(r.rows_used_frac < 0.97f); /* the clutter is visible in the quality figure */
        GL_CHECK(r.rows_used > 120);
    }
    printf("    flag cloth + person + rail: worst axis error %.3f px over %d scenes; "
           "%.0f rows per scene set aside as too wide; mean fraction of rows used %.2f\n",
           worst, trials, (double)wide_rows / trials, (double)frac_sum / trials);
    GL_CHECK(worst < 0.08);
    GL_CHECK(wide_rows > trials * 10);
}

/* ---------------------------------------------------------------------- */
/* Ends of the stick                                                        */
/* ---------------------------------------------------------------------- */

GL_TEST(test_lowest_point_and_base_flag)
{
    uint32_t rng = 77;
    const int trials = 60;
    struct {
        const char *name;
        float below_horizon; /* rows by which the stick continues below the turf horizon */
        float width;
        double s1, s2, hs2;
        int n, visible, at_horizon, unknown;
    } cases[] = {
        { "base 8 rows below the turf horizon, 1.5 px", 8.0f, 1.5f, 0, 0, 0, 0, 0, 0, 0 },
        { "base 3 rows below the turf horizon, 1.5 px", 3.0f, 1.5f, 0, 0, 0, 0, 0, 0, 0 },
        { "stick ends at the turf horizon,     1.5 px", 0.0f, 1.5f, 0, 0, 0, 0, 0, 0, 0 },
        { "base 8 rows below the turf horizon, 0.7 px", 8.0f, 0.7f, 0, 0, 0, 0, 0, 0, 0 },
        { "stick ends at the turf horizon,     0.7 px", 0.0f, 0.7f, 0, 0, 0, 0, 0, 0, 0 },
    };

    for (size_t ci = 0; ci < sizeof(cases) / sizeof(cases[0]); ci++) {
        for (int t = 0; t < trials; t++) {
            gl_synth_scene_t s;
            gl_strip_t st = strip_of(0);
            gl_vis_prior_t pr = { 0.0f, 250.0f, 0.0f, 0.0f, 0.0f, false, 0.0f, 0.0f, 0 };
            gl_vis_stick_t r;
            scene_init(&s, cases[ci].width, 60.0f, 3.0f);
            s.horizon_row = 300.0f + gl_synth_rand_uniform(&rng);
            s.stick_bottom_row = s.horizon_row + cases[ci].below_horizon +
                                 ((cases[ci].below_horizon > 0.0f)
                                      ? (gl_synth_rand_uniform(&rng) - 0.5f)
                                      : 0.0f);
            s.stick_x = 318.0f + 4.0f * gl_synth_rand_uniform(&rng);
            s.stick_slant = 0.02f;
            s.noise_seed = gl_synth_rand_u32(&rng);
            gl_synth_render(&s, img[0]);
            pr.x = s.stick_x - 1.0f;
            if (gl_vis_stick_refine(&st, &pr, &wk[0], &r) != GL_OK) {
                continue;
            }
            cases[ci].n++;
            cases[ci].s1 += (double)r.bottom_row - (double)s.stick_bottom_row;
            cases[ci].s2 += ((double)r.bottom_row - (double)s.stick_bottom_row) *
                            ((double)r.bottom_row - (double)s.stick_bottom_row);
            if (r.horizon_found) {
                cases[ci].hs2 += ((double)r.horizon_row - (double)s.horizon_row) *
                                 ((double)r.horizon_row - (double)s.horizon_row);
            }
            cases[ci].visible += (r.base == GL_VIS_BASE_VISIBLE);
            cases[ci].at_horizon += (r.base == GL_VIS_BASE_AT_HORIZON);
            cases[ci].unknown += (r.base == GL_VIS_BASE_UNKNOWN);
        }
    }
    printf("    lowest visible point, single strip, SNR 20, %d trials each:\n", trials);
    printf("    %-44s %8s %8s %9s  %s\n", "case", "bias row", "RMS row", "horiz RMS",
           "visible/at-horizon/unknown");
    for (size_t ci = 0; ci < sizeof(cases) / sizeof(cases[0]); ci++) {
        int n = cases[ci].n;
        printf("    %-44s %+8.3f %8.3f %9.3f  %d/%d/%d\n", cases[ci].name, cases[ci].s1 / n,
               sqrt(cases[ci].s2 / n), sqrt(cases[ci].hs2 / n), cases[ci].visible,
               cases[ci].at_horizon, cases[ci].unknown);
        GL_CHECK_EQ(n, trials);
    }
    /* base clearly below the horizon: classified visible, position good */
    GL_CHECK(cases[0].visible >= trials - 1);
    GL_CHECK(sqrt(cases[0].s2 / trials) < 0.35);
    GL_CHECK(fabs(cases[0].s1 / trials) < 0.15);
    GL_CHECK(cases[1].visible >= trials - 3);
    /* ends at the horizon: classified "at horizon" */
    GL_CHECK(cases[2].at_horizon >= trials - 1);
    GL_CHECK(sqrt(cases[2].s2 / trials) < 0.5);
    GL_CHECK(cases[3].visible >= trials - 6);
    GL_CHECK(cases[4].at_horizon >= trials - 6);
    GL_CHECK(sqrt(cases[3].s2 / trials) < 0.8);

    /* the stick runs out of the bottom of the strip: no end, base unknown */
    {
        gl_synth_scene_t s;
        gl_strip_t st = strip_of(0);
        gl_vis_prior_t pr = { 320.0f, 250.0f, 0.0f, 0.0f, 0.0f, false, 0.0f, 0.0f, 0 };
        gl_vis_stick_t r;
        scene_init(&s, 1.5f, 60.0f, 3.0f);
        s.horizon_row = -5000.0f;
        s.stick_x = 320.4f;
        s.stick_bottom_row = 2000.0f;
        gl_synth_render(&s, img[0]);
        GL_CHECK_EQ(gl_vis_stick_refine(&st, &pr, &wk[0], &r), GL_OK);
        GL_CHECK_EQ(r.base, GL_VIS_BASE_UNKNOWN);
        GL_CHECK(!r.horizon_found);
        GL_CHECK(!r.top_in_frame);
        GL_CHECK(r.bottom_row > 470.0f);
        GL_CHECK(r.rows_used > 440);
    }
}

GL_TEST(test_top_of_stick_and_angular_height)
{
    uint32_t rng = 78;
    double s2 = 0, s1 = 0, h2 = 0;
    const int trials = 60;
    gl_cal_cam_t cal;
    gl_cam_model_t cam;
    gl_cal_cam_defaults(&cal, 0);
    gl_cam_model_init(&cam, &cal);

    for (int t = 0; t < trials; t++) {
        gl_synth_scene_t s;
        gl_strip_t st = strip_of(0);
        gl_vis_prior_t pr = { 0.0f, 250.0f, 0.0f, 0.0f, 0.0f, false, 0.0f, 0.0f, 0 };
        gl_vis_stick_t r;
        gl_vis_angles_t a;
        const gl_vec3_t up = { 0.0f, 0.0f, 1.0f };
        scene_init(&s, 1.5f, 60.0f, 3.0f);
        s.horizon_row = 232.0f;
        s.stick_top_row = 60.0f + 20.0f * gl_synth_rand_uniform(&rng);
        s.stick_bottom_row = 240.0f + gl_synth_rand_uniform(&rng);
        s.stick_x = 318.0f + 4.0f * gl_synth_rand_uniform(&rng);
        s.stick_slant = 0.02f;
        s.noise_seed = gl_synth_rand_u32(&rng);
        gl_synth_render(&s, img[0]);
        pr.x = s.stick_x + 1.0f;
        GL_CHECK_EQ(gl_vis_stick_refine(&st, &pr, &wk[0], &r), GL_OK);
        GL_CHECK(r.top_in_frame);
        s1 += (double)r.top_row - (double)s.stick_top_row;
        s2 += ((double)r.top_row - (double)s.stick_top_row) *
              ((double)r.top_row - (double)s.stick_top_row);
        /* angular height through the camera model (level marker) */
        gl_vis_stick_angles(&r, &cam, up, &a);
        GL_CHECK(a.top_valid);
        {
            double truth = ((double)s.stick_bottom_row - (double)s.stick_top_row) / 657.0;
            h2 += ((double)a.tan_height - truth) * ((double)a.tan_height - truth);
        }
        GL_CHECK_NEAR(a.base_elev_rad, atan((239.5 - (double)r.bottom_row) / 657.0), 1e-4);
        GL_CHECK_NEAR(a.bearing_rad,
                      -atan(((double)gl_vis_stick_x_at(&r, r.bottom_row) - 319.5) / 657.0), 2e-4);
        GL_CHECK(a.top_elev_rad > 0.2f);
    }
    printf("    top of the stick: bias %+.3f row, RMS %.3f row; angular height RMS error "
           "%.2f mrad (%.2f %% of a 1.96 m stick at 7.3 m)\n", s1 / trials, sqrt(s2 / trials),
           1000.0 * sqrt(h2 / trials), 100.0 * sqrt(h2 / trials) / (175.0 / 657.0));
    GL_CHECK(sqrt(s2 / trials) < 0.35);
    GL_CHECK(sqrt(h2 / trials) < 0.0008);
}

/* ---------------------------------------------------------------------- */
/* Horizon band                                                             */
/* ---------------------------------------------------------------------- */

GL_TEST(test_band_detection)
{
    static const float widths[] = { 0.7f, 1.5f, 3.0f, 6.0f, 10.0f };
    uint32_t rng = 2468;
    const int per_width = 24;
    printf("    horizon band 640 x 96, SNR 20, lean -3..+3 deg, textured background half the "
           "time:\n");
    printf("    %-10s %9s %10s %12s %12s\n", "width px", "detected", "x RMS px", "lean RMS deg",
           "mean score");
    for (size_t wi = 0; wi < sizeof(widths) / sizeof(widths[0]); wi++) {
        int found = 0;
        double ex2 = 0, es2 = 0, score = 0;
        for (int t = 0; t < per_width; t++) {
            gl_synth_scene_t s;
            gl_strip_t b = { band_img, 640, 96, 640, 0, 192 };
            gl_vis_band_result_t res;
            gl_synth_defaults(&s, 640, 96, 0, 192);
            s.horizon_row = 236.0f + 8.0f * gl_synth_rand_uniform(&rng);
            s.noise_sigma = 3.0f;
            s.bg_texture_amp = (t & 1) ? 4.0f : 0.0f;
            s.turf_texture_amp = 2.0f;
            s.texture_seed = gl_synth_rand_u32(&rng);
            s.noise_seed = gl_synth_rand_u32(&rng);
            s.stick_present = true;
            s.stick_width_px = widths[wi];
            s.stick_level = 170.0f;
            s.stick_ref_row = 197.5f; /* where the band reports the candidate */
            s.stick_x = 40.0f + 560.0f * gl_synth_rand_uniform(&rng);
            s.stick_slant = 0.104f * (gl_synth_rand_uniform(&rng) - 0.5f); /* +-3 deg */
            s.stick_bottom_row = s.horizon_row + 0.3f;
            gl_synth_render(&s, band_img);
            if (gl_vis_band_analyse(&b, &bw, &res) == GL_OK && res.n_cand >= 1 &&
                fabsf(res.cand[0].x - s.stick_x) < 3.0f) {
                found++;
                ex2 += ((double)res.cand[0].x - (double)s.stick_x) *
                       ((double)res.cand[0].x - (double)s.stick_x);
                es2 += ((double)atanf(res.cand[0].slant) - (double)atanf(s.stick_slant)) *
                       ((double)atanf(res.cand[0].slant) - (double)atanf(s.stick_slant));
                score += res.cand[0].score;
                GL_CHECK_EQ(res.cand[0].polarity, 1);
                GL_CHECK_NEAR(res.cand[0].ref_row, 197.5, 1e-3);
            }
        }
        printf("    %-10.1f %6d/%-2d %10.3f %12.2f %12.1f\n", (double)widths[wi], found,
               per_width, found ? sqrt(ex2 / found) : 0.0,
               found ? sqrt(es2 / found) * 57.29578 : 0.0, found ? score / found : 0.0);
        GL_CHECK_EQ(found, per_width);
        GL_CHECK(sqrt(ex2 / per_width) < 0.8);
    }
}

GL_TEST(test_band_outputs)
{
    gl_synth_scene_t s;
    gl_strip_t b = { band_img, 640, 96, 640, 0, 192 };
    gl_vis_band_result_t res;
    int valid = 0;
    double h2 = 0;

    /* two sticks of different strength, a dark one and a bright one, on a
     * tilted turf horizon */
    gl_synth_defaults(&s, 640, 96, 0, 192);
    s.horizon_row = 240.3f;
    s.noise_sigma = 3.0f;
    s.stick_present = true;
    s.stick_width_px = 1.5f;
    s.stick_level = 180.0f;
    s.stick_ref_row = 197.5f;
    s.stick_x = 400.4f;
    s.stick_bottom_row = 240.3f;
    s.n_clutter = 1; /* second, weaker, dark line: a distant post */
    s.clutter[0].x_left = 150.0f;
    s.clutter[0].x_right = 151.2f;
    s.clutter[0].row_top = 100.0f;
    s.clutter[0].row_bottom = 240.3f;
    s.clutter[0].level = 75.0f;
    gl_synth_render(&s, band_img);
    GL_CHECK_EQ(gl_vis_band_analyse(&b, &bw, &res), GL_OK);
    GL_CHECK_EQ(res.n_cand, 2);
    GL_CHECK_NEAR(res.cand[0].x, 400.4, 0.5);     /* strongest first */
    GL_CHECK_EQ(res.cand[0].polarity, 1);
    GL_CHECK_NEAR(res.cand[1].x, 150.6, 0.5);
    GL_CHECK_EQ(res.cand[1].polarity, -1);
    GL_CHECK(res.cand[0].score > res.cand[1].score);
    GL_CHECK(res.cand[0].rows >= 36 && res.cand[0].rows <= 60); /* stick is in the upper half */
    /* per-column vertical-edge energy peaks at the stick */
    GL_CHECK(bw.edge_energy[400] > 3.0f * res.edge_energy_mean ||
             bw.edge_energy[401] > 3.0f * res.edge_energy_mean);
    GL_CHECK(bw.edge_energy[300] < 2.0f * res.edge_energy_mean);
    /* turf-horizon samples */
    for (unsigned i = 0; i < GL_VIS_HORIZON_BINS; i++) {
        if (res.horizon_valid & (1u << i)) {
            valid++;
            h2 += ((double)res.horizon_row[i] - 240.3) * ((double)res.horizon_row[i] - 240.3);
            GL_CHECK_NEAR(res.horizon_col[i], 9.5 + 20.0 * i, 1e-3);
        }
    }
    printf("    turf horizon samples: %d of %u bins valid, RMS error %.3f row\n", valid,
           (unsigned)GL_VIS_HORIZON_BINS, sqrt(h2 / (valid ? valid : 1)));
    GL_CHECK(valid >= 30);
    GL_CHECK(sqrt(h2 / valid) < 0.2);
    GL_CHECK_NEAR(res.stats.noise_sigma, 3.0, 0.7);
    GL_CHECK(!res.stats.sun);

    /* no turf edge in view (all sky): no horizon samples, no candidates */
    gl_synth_defaults(&s, 640, 96, 0, 192);
    s.horizon_row = -5000.0f;
    s.noise_sigma = 3.0f;
    gl_synth_render(&s, band_img);
    GL_CHECK_EQ(gl_vis_band_analyse(&b, &bw, &res), GL_ERR_NO_STICK);
    GL_CHECK_EQ(res.horizon_valid, 0);
    /* parameter checks */
    b.width = 32;
    GL_CHECK_EQ(gl_vis_band_analyse(&b, &bw, &res), GL_ERR_PARAM);
    b.width = 640;
    b.height = 12;
    GL_CHECK_EQ(gl_vis_band_analyse(&b, &bw, &res), GL_ERR_PARAM);
}

/* ---------------------------------------------------------------------- */
/* Quality metrics                                                          */
/* ---------------------------------------------------------------------- */

GL_TEST(test_quality_metrics)
{
    gl_synth_scene_t s;
    gl_strip_t sl = strip_of(0), sr = strip_of(1);
    gl_vis_prior_t pr = { 321.0f, 250.0f, 0.0f, 0.0f, 0.0f, false, 0.0f, 0.0f, 0 };
    gl_vis_stick_t rl, rr;
    gl_vis_stats_t stl, str;
    gl_vis_quality_t q;
    float clean_match;

    /* both windows clean */
    scene_init(&s, 1.5f, 60.0f, 3.0f);
    s.stick_x = 320.3f;
    gl_synth_render(&s, img[0]);
    s.noise_seed = 99;
    gl_synth_render(&s, img[1]);
    GL_CHECK_EQ(gl_vis_stick_refine(&sl, &pr, &wk[0], &rl), GL_OK);
    GL_CHECK_EQ(gl_vis_stick_refine(&sr, &pr, &wk[1], &rr), GL_OK);
    gl_vis_strip_stats(&sl, wk[0].tmp, &stl);
    gl_vis_strip_stats(&sr, wk[1].tmp, &str);
    gl_vis_quality(&rl, &rr, &stl, &str, &q);
    clean_match = q.sharpness_match;
    GL_CHECK(q.sharpness_match > 0.85f);
    GL_CHECK(q.line_contrast > 30.0f);
    GL_CHECK(q.contrast_snr > 8.0f);
    GL_CHECK(q.rows_used_frac > 0.95f);
    GL_CHECK(!q.sun);
    GL_CHECK_NEAR(q.sat_fraction, 0.0, 1e-6);
    GL_CHECK_NEAR(stl.mean, 110.0 * 330.5 / 480.0 + 70.0 * 149.5 / 480.0, 1.5);

    /* right window smeared: wider, fainter line */
    s.psf_sigma_px = 1.6f;
    gl_synth_render(&s, img[1]);
    GL_CHECK_EQ(gl_vis_stick_refine(&sr, &pr, &wk[1], &rr), GL_OK);
    gl_vis_strip_stats(&sr, wk[1].tmp, &str);
    gl_vis_quality(&rl, &rr, &stl, &str, &q);
    printf("    left/right sharpness match: %.2f with clean windows, %.2f with the right "
           "window smeared (blur 0.6 -> 1.6 px)\n", (double)clean_match,
           (double)q.sharpness_match);
    GL_CHECK(q.sharpness_match < 0.6f);

    /* the sun in the strip: flag and saturated fraction */
    s.psf_sigma_px = 0.6f;
    s.sun = true;
    s.sun_x = 350.0f;
    s.sun_row = 120.0f;
    s.sun_radius_px = 14.0f;
    gl_synth_render(&s, img[1]);
    gl_vis_strip_stats(&sr, wk[1].tmp, &str);
    GL_CHECK(str.sun);
    GL_CHECK(str.sat_fraction > 0.01f && str.sat_fraction < 0.2f);
    gl_vis_quality(&rl, &rr, &stl, &str, &q);
    GL_CHECK(q.sun);
    GL_CHECK(q.sat_fraction > 0.01f);
    /* a few isolated hot pixels are not "the sun" */
    s.sun = false;
    gl_synth_render(&s, img[1]);
    for (int i = 0; i < 12; i++) {
        img[1][(40 + 17 * i) * SW + (5 + 7 * i)] = 255;
    }
    gl_vis_strip_stats(&sr, wk[1].tmp, &str);
    GL_CHECK(!str.sun);
    GL_CHECK(str.sat_fraction > 0.0f && str.sat_fraction < 0.001f);
}

/* ---------------------------------------------------------------------- */
/* End to end: band -> strips -> disparity -> angles, through the camera     */
/* models                                                                   */
/* ---------------------------------------------------------------------- */

GL_TEST(test_end_to_end_with_camera_models)
{
    gl_cal_cam_t cal_l, cal_r;
    gl_cam_model_t cam[2];
    const gl_vec3_t up = { 0.0f, 0.0f, 1.0f };
    uint32_t rng = 1357;
    static const float ranges[] = { 3.0f, 6.0f, 10.0f };

    gl_cal_cam_defaults(&cal_l, 0);
    gl_cal_cam_defaults(&cal_r, 1);
    /* mis-mounted right camera: the calibration record knows about it */
    cal_r.yaw_left_rad = 0.004f;
    cal_r.roll_rad = 0.006f;
    cal_r.pitch_up_rad = -0.003f;
    gl_cam_model_init(&cam[0], &cal_l);
    gl_cam_model_init(&cam[1], &cal_r);

    printf("    full chain (band, 8 x LRRL strips, rectified disparity), stick 15 mm wide, "
           "SNR 20, 1.2 deg lean, right camera mis-mounted by 4-6 mrad:\n");
    printf("    %8s %12s %12s %10s %12s %14s\n", "range m", "disparity", "true", "sigma",
           "range err %", "bearing err mrad");
    for (size_t ri = 0; ri < sizeof(ranges) / sizeof(ranges[0]); ri++) {
        const float z = ranges[ri];
        const float lateral = 0.08f * z; /* stick 4.6 deg to the right */
        /* a leaning stick: base on the ground, 1.9 m tall, top displaced */
        const gl_vec3_t base = { lateral, z, -0.004f };
        const gl_vec3_t top = { lateral + 0.04f, z, 1.9f };
        float ub[2], vb[2], ut[2], vt[2];
        gl_vis_band_result_t bres;
        gl_vis_disp_acc_t acc;
        gl_vis_disparity_t disp;
        gl_vis_stick_t first_left;
        gl_vis_angles_t ang;
        float d_true, bearing_true, elev_true;
        uint16_t x0s[2];
        bool have_first = false;

        for (int c = 0; c < 2; c++) {
            GL_CHECK(gl_cam_point_to_pixel(&cam[c], base, &ub[c], &vb[c]));
            GL_CHECK(gl_cam_point_to_pixel(&cam[c], top, &ut[c], &vt[c]));
        }
        d_true = GL_CFG_STEREO_F_TIMES_B_PX_M / (z - 0.0156f);

        /* 1. horizon band from the left camera, centred on its horizon row */
        {
            gl_synth_scene_t s;
            int y0 = gl_roundi(gl_cam_base_plane_row(&cam[0], 320.0f)) - 48;
            gl_strip_t b = { band_img, 640, 96, 640, 0, (uint16_t)y0 };
            gl_synth_defaults(&s, 640, 96, 0, (uint16_t)y0);
            s.horizon_row = vb[0] - 0.4f;
            s.noise_sigma = 3.0f;
            s.stick_present = true;
            s.stick_width_px = 0.015f / z * 657.0f;
            s.stick_level = 170.0f;
            s.stick_x = ub[0];
            s.stick_ref_row = vb[0];
            s.stick_slant = (ub[0] - ut[0]) / (vb[0] - vt[0]);
            s.stick_bottom_row = vb[0];
            s.noise_seed = gl_synth_rand_u32(&rng);
            gl_synth_render(&s, band_img);
            GL_CHECK_EQ(gl_vis_band_analyse(&b, &bw, &bres), GL_OK);
            GL_CHECK(bres.n_cand >= 1);
            GL_CHECK_NEAR(bres.cand[0].x, gl_synth_stick_x_at(&s, bres.cand[0].ref_row), 1.0);
        }
        /* 2. strips: 96 columns around the candidate in each camera (the
         *    right camera's window is shifted by the expected disparity range) */
        x0s[0] = (uint16_t)gl_clampi(gl_roundi(bres.cand[0].x) - 48, 0, 640 - SW);
        x0s[1] = (uint16_t)gl_clampi(gl_roundi(bres.cand[0].x) - 48 - 4, 0, 640 - SW);
        gl_vis_disp_acc_reset(&acc);
        for (int grp = 0; grp < 8; grp++) {
            gl_vis_segment_t seg[4];
            gl_vis_stick_t sticks[4];
            static const int cam_of[4] = { 0, 1, 1, 0 };
            bool ok = true;
            float bot = 1e9f, d0 = 0.0f, sg0 = 0.0f;
            unsigned nrows;
            for (int f = 0; f < 4; f++) {
                const int c = cam_of[f];
                gl_synth_scene_t s;
                gl_strip_t st = { img[f], SW, SH, SW, x0s[c], 0 };
                gl_vis_prior_t pr;
                memset(&pr, 0, sizeof(pr));
                gl_synth_defaults(&s, SW, SH, x0s[c], 0);
                s.horizon_row = vb[c] - 0.4f;
                s.noise_sigma = 3.0f;
                s.stick_present = true;
                s.stick_width_px = 0.015f / z * 657.0f;
                s.stick_level = 170.0f;
                s.stick_x = ub[c];
                s.stick_ref_row = vb[c];
                s.stick_slant = (ub[c] - ut[c]) / (vb[c] - vt[c]);
                s.stick_bottom_row = vb[c];
                s.stick_top_row = vt[c];
                s.noise_seed = gl_synth_rand_u32(&rng);
                gl_synth_render(&s, img[f]);
                /* prior: the band candidate (left image); the right image is
                 * searched a little wider because of the unknown disparity */
                pr.x = bres.cand[0].x - ((c == 1) ? 2.0f : 0.0f);
                pr.row = bres.cand[0].ref_row;
                pr.slant = bres.cand[0].slant;
                pr.width_px = bres.cand[0].width_px;
                pr.search_px = 8.0f;
                if (gl_vis_stick_refine(&st, &pr, &wk[f], &sticks[f]) != GL_OK) {
                    ok = false;
                    break;
                }
                if (sticks[f].bottom_row < bot) {
                    bot = sticks[f].bottom_row;
                }
            }
            GL_CHECK(ok);
            if (!ok) {
                continue;
            }
            if (!have_first) {
                first_left = sticks[0];
                have_first = true;
            }
            /* 3. the lowest 0.4 m: rows from a first full-length estimate */
            {
                gl_vis_segment_t a, b2;
                GL_CHECK_EQ(gl_vis_stick_segment(&wk[0], &sticks[0], bot - 60.0f, bot - 2.0f, &a),
                            GL_OK);
                GL_CHECK_EQ(gl_vis_stick_segment(&wk[1], &sticks[1], bot - 60.0f, bot - 2.0f, &b2),
                            GL_OK);
                GL_CHECK_EQ(gl_vis_stereo_pair(&a, &b2, &cam[0], &cam[1], GL_CFG_CAM_F_PX, &d0,
                                               &sg0), GL_OK);
            }
            nrows = gl_vis_segment_rows(d0, GL_CFG_CAM_BASELINE_M, 0.4f);
            for (int f = 0; f < 4; f++) {
                if (gl_vis_stick_segment(&wk[f], &sticks[f], bot - 2.0f - (float)nrows,
                                         bot - 2.0f, &seg[f]) != GL_OK) {
                    ok = false;
                }
            }
            GL_CHECK(ok);
            if (ok) {
                GL_CHECK_EQ(gl_vis_disp_acc_add_lrrl(&acc, seg, &cam[0], &cam[1],
                                                     GL_CFG_CAM_F_PX), GL_OK);
            }
        }
        GL_CHECK_EQ(gl_vis_disp_acc_result(&acc, &disp), GL_OK);
        GL_CHECK(have_first);
        gl_vis_stick_angles(&first_left, &cam[0], up, &ang);
        bearing_true = atan2f(-(base.x - cam[0].pos_m.x), base.y - cam[0].pos_m.y);
        elev_true = atanf((base.z - cam[0].pos_m.z) / (z - cam[0].pos_m.y));
        {
            float z_meas = GL_CFG_STEREO_F_TIMES_B_PX_M / disp.disparity_px + 0.0156f;
            printf("    %8.1f %12.4f %12.4f %10.4f %+12.2f %+14.3f\n", (double)z,
                   (double)disp.disparity_px, (double)d_true, (double)disp.sigma_px,
                   100.0 * ((double)z_meas - (double)z) / (double)z,
                   1000.0 * ((double)ang.bearing_rad - (double)bearing_true));
            GL_CHECK(fabsf(disp.disparity_px - d_true) < 4.0f * disp.sigma_px + 0.02f);
            GL_CHECK(fabsf(disp.disparity_px - d_true) < 0.06f);
            GL_CHECK_NEAR(ang.bearing_rad, bearing_true, 0.0005);
            GL_CHECK_NEAR(ang.base_elev_rad, elev_true, 0.0015);
            GL_CHECK(ang.bearing_rad < 0.0f); /* the stick is to the right */
        }
        if (z > 5.0f) {
            /* top in frame beyond about 4.4 m: angular height gives the range too */
            GL_CHECK(ang.top_valid);
            GL_CHECK_NEAR(1.904 / (double)ang.tan_height, (double)z - 0.0156, 0.02 * (double)z);
        } else {
            GL_CHECK(!ang.top_valid);
        }
    }
    /* how many rows is 0.4 m of stick? */
    GL_CHECK_EQ(gl_vis_segment_rows(GL_CFG_STEREO_F_TIMES_B_PX_M / 10.0f, GL_CFG_CAM_BASELINE_M, 0.4f), 26);
    GL_CHECK_EQ(gl_vis_segment_rows(GL_CFG_STEREO_F_TIMES_B_PX_M / 3.0f, GL_CFG_CAM_BASELINE_M, 0.4f), 87);
    GL_CHECK_EQ(gl_vis_segment_rows(0.2f, GL_CFG_CAM_BASELINE_M, 0.4f), 12);  /* clamped */
    GL_CHECK_EQ(gl_vis_segment_rows(-1.0f, GL_CFG_CAM_BASELINE_M, 0.4f), 40); /* unknown */
}

int main(void)
{
    GL_RUN(test_renderer_sanity);
    GL_RUN(test_refine_basic_both_polarities);
    GL_RUN(test_disparity_accuracy_table);
    GL_RUN(test_no_bias_across_subpixel_phase);
    GL_RUN(test_lrrl_cancels_sway);
    GL_RUN(test_polarity_flips_along_the_stick);
    GL_RUN(test_no_stick_fails_gracefully);
    GL_RUN(test_outlier_rejection);
    GL_RUN(test_lowest_point_and_base_flag);
    GL_RUN(test_top_of_stick_and_angular_height);
    GL_RUN(test_band_detection);
    GL_RUN(test_band_outputs);
    GL_RUN(test_quality_metrics);
    GL_RUN(test_end_to_end_with_camera_models);
    return gl_test_summary();
}
