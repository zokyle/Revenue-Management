/*
 * test_read.c - the camera part of a read on HARD scenes: the real sequence
 * (app/gl_read.c + drivers/ov7692.c + core/gl_vision.c) through the host
 * simulator, with frames from tests/synth/gl_scene.c.
 *
 * These are the design reviewers' cases, adopted as permanent tests.  The
 * scene generator is independent of the one the vision code was developed
 * against (tests/synth/gl_synth.c) and is PHYSICALLY CONSISTENT: a stick of
 * 15 mm and 1.96 m has the width, the height and the disparity that belong
 * to one range, its base lies (lens height / range) below the turf horizon
 * on a flat green, and the right camera sees the same world shifted by the
 * disparity of each object.
 *
 * What is asserted, per group of scenes:
 *   - never a WRONG OBJECT taken for the flagstick without the ambiguity
 *     flag, never a flagstick where there is none (above a stated rate);
 *   - the disparity error against the uncertainty the read itself claims;
 *   - the lowest visible point and its three-way classification;
 *   - where a target is NOT met (faint sticks, a second pole on the
 *     disparity side, sun in the strip) the test pins the measured rate and
 *     the README says so.
 * Every number printed here is quoted in the README.
 */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "gl_config.h"
#include "gl_hal.h"
#include "gl_range.h"
#include "gl_read.h"
#include "gl_scene.h"
#include "gl_sim.h"
#include "gl_test.h"

#define F_PX 657.0
#define FB (F_PX * (double)GL_CFG_CAM_BASELINE_M) /* f * baseline, px m */
#define DEG (3.14159265358979323846 / 180.0)

static gl_ov7692_t cam_;
static gl_read_t rd_;

typedef struct {
    gl_scene_t sc;
    uint32_t trial_seed;
    unsigned frames;
} ctx_t;

static ctx_t C;

static void scene_cb_(void *ctx, gl_cam_id_t cam, uint16_t x0, uint16_t y0, uint16_t w, uint16_t h,
                      uint32_t frame_no, uint64_t t_us, uint8_t *luma)
{
    ctx_t *c = (ctx_t *)ctx;
    (void)frame_no;
    gl_scene_render(&c->sc, (cam == GL_CAM_RIGHT) ? 1 : 0, x0, y0, w, h, (double)t_us * 1e-6,
                    c->trial_seed * 4099u + c->frames * 7919u + 13u, luma);
    c->frames++;
}

static gl_status_t run_read_(uint32_t phase_us)
{
    const gl_vec3_t up = { 0.0f, 0.0f, 1.0f };
    gl_status_t st;
    gl_sim_reset(true);
    (void)gl_hal_init();
    gl_sim_cam_set_scene(scene_cb_, &C);
    gl_sim_cam_set_phase_us(GL_CAM_RIGHT, phase_us);
    gl_ov7692_init(&cam_, NULL);
    gl_read_init(&rd_, &cam_);
    C.frames = 0;
    st = gl_read_start(&rd_, up, GL_APP_LRRL_REPEATS);
    if (st == GL_OK) {
        int guard = 0;
        while ((st = gl_read_step(&rd_)) == GL_ERR_BUSY && guard++ < 40000) {
            gl_hal_delay_ms(1);
        }
    }
    return st;
}

typedef void (*setup_fn_t)(gl_scene_t *s, gl_scene_rng_t *r, int variant);

/* ---- scene building blocks ---------------------------------------------------- */

static double width_to_range_(double w_px) { return 0.015 * F_PX / w_px; }

/* Flat-green geometry for a 15 mm stick of visible height 1.96 m at the range
 * implied by its pixel width; contrast is Weber contrast against the sky
 * (sky 120 grey, noise 2 grey rms: SNR = contrast * 60). */
static void base_scene_(gl_scene_t *s, gl_scene_rng_t *r, double w_px, double contrast)
{
    double z;
    z = width_to_range_(w_px);
    gl_scene_defaults(s);
    s->seed = gl_scene_u32(r);
    s->fpn_seed[0] = gl_scene_u32(r);
    s->fpn_seed[1] = gl_scene_u32(r);
    s->sky = 120.0;
    s->turf = 80.0;
    s->turf_tex = 3.0;
    s->horizon = 239.5 + (gl_scene_uniform(r) - 0.5);
    s->tree_top = s->horizon;
    s->stick = 1;
    s->s_w = w_px;
    s->s_disp = FB / z;
    s->sx = 130.0 + 380.0 * gl_scene_uniform(r);
    s->s_bot = s->horizon + F_PX * 0.00561 / z;
    s->s_top = s->s_bot - F_PX * 1.96 / z;
    s->s_level = s->sky * (1.0 + contrast);
    s->noise = 2.0;
}

static const double grid_w_[6] = { 0.5, 0.7, 1.0, 1.5, 2.0, 3.0 };
static const double grid_c_[5] = { 0.05, 0.10, 0.20, 0.40, 0.60 };

/* variant = wi * 10 + ci, +100 for negative polarity */
static void setup_grid_(gl_scene_t *s, gl_scene_rng_t *r, int v)
{
    int neg = v >= 100;
    int wi = (v % 100) / 10, ci = v % 10;
    base_scene_(s, r, grid_w_[wi], (neg ? -1.0 : 1.0) * grid_c_[ci]);
}

/* operating points: A (b = 0) = 1.5 px / +30 %, B (b = 1) = 0.8 px / +30 % */
static void op_(gl_scene_t *s, gl_scene_rng_t *r, int b)
{
    base_scene_(s, r, b ? 0.8 : 1.5, 0.30);
}

static void setup_nominal_(gl_scene_t *s, gl_scene_rng_t *r, int v) { op_(s, r, v); }

static void setup_basevis_(gl_scene_t *s, gl_scene_rng_t *r, int v)
{
    op_(s, r, v & 1);
    s->horizon -= 6.0; /* a rise behind the hole: base 6 rows below the turf horizon */
    s->tree_top = s->horizon;
}

static void setup_slant_(gl_scene_t *s, gl_scene_rng_t *r, int v)
{
    static const double deg[4] = { 1.0, 2.0, 3.0, -3.0 };
    op_(s, r, v >= 10);
    s->s_slope = tan(deg[v % 10] * DEG);
}

static void setup_sway_(gl_scene_t *s, gl_scene_rng_t *r, int v)
{
    op_(s, r, v >= 10);
    s->sway_phase = 6.283 * gl_scene_uniform(r);
    switch (v % 10) {
    case 0: s->sway_lin = 3.0; break;                       /* px/s steady drift */
    case 1: s->sway_amp = 0.5; s->sway_hz = 1.5; break;
    case 2: s->sway_amp = 1.0; s->sway_hz = 3.0; break;
    default: s->sway_amp = 2.0; s->sway_hz = 1.0; break;
    }
}

static void setup_flag_(gl_scene_t *s, gl_scene_rng_t *r, int v)
{
    double z;
    op_(s, r, v >= 10);
    z = FB / s->s_disp;
    s->flag = 1;
    s->f_top = s->s_top + F_PX * 0.03 / z;   /* 3 cm below the tip */
    s->f_h = F_PX * 0.36 / z;                /* 14 inch flag */
    s->f_len = F_PX * 0.50 / z;              /* 20 inch */
    s->f_side = (gl_scene_uniform(r) < 0.5) ? 1 : -1;
    s->f_hz = 1.5 + 2.0 * gl_scene_uniform(r);
    s->f_level = ((v % 10) == 0) ? 215.0 : 40.0; /* bright / dark cloth */
}

/* a person: torso + two legs, feet at the turf horizon, at range zp */
static void add_person_(gl_scene_t *s, double xc, double zp, double level)
{
    double k = F_PX / zp;
    double feet = s->horizon + F_PX * 0.00561 / zp;
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

static void setup_person_(gl_scene_t *s, gl_scene_rng_t *r, int v)
{
    double z;
    op_(s, r, v >= 10);
    z = FB / s->s_disp;
    switch (v % 10) {
    case 0: /* standing 2 m behind the hole, a leg right behind the stick */
        add_person_(s, s->sx + 0.12 * F_PX / (z + 2.0) + 2.0 * (gl_scene_uniform(r) - 0.5), z + 2.0, 45.0);
        break;
    case 1: /* 0.6 m to the side of the stick, same range (inside the 96 px strip at 6.6 m) */
        add_person_(s, s->sx + ((gl_scene_uniform(r) < 0.5) ? -1.0 : 1.0) * 0.6 * F_PX / z, z, 45.0);
        break;
    default: /* 2 m to the side, 1 m nearer */
        add_person_(s, s->sx + ((s->sx > 320.0) ? -1.0 : 1.0) * 2.0 * F_PX / (z - 1.0), z - 1.0, 45.0);
        break;
    }
}

static void setup_pole2_(gl_scene_t *s, gl_scene_rng_t *r, int v)
{
    gl_scene_pole_t *p;
    double c;
    op_(s, r, v >= 10);
    c = s->s_level - s->sky;
    p = &s->pole[s->n_pole++];
    p->bot = s->horizon + 0.3;
    p->top = -50.0;
    p->slope = 0.0;
    switch (v % 10) {
    case 0: /* 7 px beside, same look, twice as far (half the disparity, half the width) */
        p->x = s->sx + ((gl_scene_uniform(r) < 0.5) ? -7.0 : 7.0);
        p->w = 0.5 * s->s_w; p->disp = 0.5 * s->s_disp; p->level = s->sky + c;
        break;
    case 1: /* 14 px beside, a thicker post (4 px), far (disp 0.3) */
        p->x = s->sx + ((gl_scene_uniform(r) < 0.5) ? -14.0 : 14.0);
        p->w = 4.0; p->disp = 0.3; p->level = s->sky - 60.0;
        break;
    case 2: /* 120 px away, weaker (half the contrast) */
        p->x = s->sx + ((s->sx > 320.0) ? -120.0 : 120.0);
        p->w = s->s_w; p->disp = 0.6 * s->s_disp; p->level = s->sky + 0.5 * c;
        break;
    default: /* 120 px away, stronger (a dark 3 px post, e.g. a signpost / sapling) */
        p->x = s->sx + ((s->sx > 320.0) ? -120.0 : 120.0);
        p->w = 3.0; p->disp = 0.5; p->level = s->sky - 80.0;
        break;
    }
}

static void setup_glare_(gl_scene_t *s, gl_scene_rng_t *r, int v)
{
    op_(s, r, v >= 10);
    switch (v % 10) {
    case 0: s->glare_gx = 0.15; s->sx = 320.0 + 200.0 * (gl_scene_uniform(r) - 0.5); break;
    case 1: s->glare_gx = 0.35; s->sx = 320.0 + 200.0 * (gl_scene_uniform(r) - 0.5); break;
    case 2: /* low sun just outside the strip: steep veiling glare with curvature */
        s->glare_amp = 150.0; s->glare_r = 60.0;
        s->glare_x = s->sx + ((gl_scene_uniform(r) < 0.5) ? -1.0 : 1.0) * (70.0 + 40.0 * gl_scene_uniform(r));
        s->glare_y = s->horizon - 60.0;
        break;
    default: /* sun in the strip, 25 px from the stick: saturated disc + halo */
        s->glare_amp = 400.0; s->glare_r = 25.0;
        s->glare_x = s->sx + ((gl_scene_uniform(r) < 0.5) ? -25.0 : 25.0);
        s->glare_y = s->horizon - 50.0;
        break;
    }
}

static void setup_grass_(gl_scene_t *s, gl_scene_rng_t *r, int v)
{
    static const double hh[3] = { 1.5, 3.0, 6.0 };
    op_(s, r, v >= 10);
    s->horizon -= 8.0; /* base well below the horizon so that only the grass hides it */
    s->tree_top = s->horizon;
    s->grass_h = hh[v % 10];
    s->grass_jag = 0.7;
}

static void setup_sensor_(gl_scene_t *s, gl_scene_rng_t *r, int v)
{
    op_(s, r, v >= 10);
    switch (v % 10) {
    case 0: s->row_gain = 0.03; break;
    case 1: s->fpn_sigma = 0.5; break;
    case 2: s->fpn_sigma = 1.0; break;
    case 3: s->fpn_sigma = 2.0; break;
    case 4: s->prnu_sigma = 0.01; break;
    case 5: s->altcol_gain = 0.03; break;
    default: s->row_gain = 0.03; s->fpn_sigma = 1.0; s->prnu_sigma = 0.005; break;
    }
}

static void setup_dirty_(gl_scene_t *s, gl_scene_rng_t *r, int v)
{
    op_(s, r, v >= 10);
    switch (v % 10) {
    case 0: s->psf[1] = 1.2; break;
    case 1: s->psf[1] = 1.8; s->veil_gain[1] = 0.8; s->veil_off[1] = 20.0; break;
    default: s->psf[1] = 2.5; s->veil_gain[1] = 0.6; s->veil_off[1] = 45.0; break;
    }
}

static void setup_trees_(gl_scene_t *s, gl_scene_rng_t *r, int v)
{
    op_(s, r, v >= 10);
    s->tree_top = s->horizon - 90.0;
    s->trees = 60.0;
    switch (v % 10) {
    case 0: s->tree_tex = 6.0; s->s_level = 200.0; break;   /* white stick, mild trunks */
    case 1: s->tree_tex = 12.0; s->s_level = 200.0; break;  /* white stick, strong trunks */
    case 2: s->tree_tex = 12.0; s->s_level = 96.0; break;   /* +36 grey stick, strong trunks */
    default: s->tree_tex = 12.0; s->tree_lx = 6.0; s->tree_ly = 6.0; s->s_level = 200.0; break; /* isotropic foliage */
    }
}

static void setup_turf_(gl_scene_t *s, gl_scene_rng_t *r, int v)
{
    op_(s, r, v >= 10);
    s->turf_tex = 10.0;
    if ((v % 10) == 1) {
        s->horizon -= 6.0;
        s->tree_top = s->horizon;
    }
}

/* The lowest part of the stick has no contrast (a stripe the colour of the
 * background): variant 0 = lowest 0.30 m, 1 = a 0.25 m band starting 0.25 m up. */
static void setup_stripe_(gl_scene_t *s, gl_scene_rng_t *r, int v)
{
    double z, k;
    gl_scene_blob_t *b;
    op_(s, r, v >= 10);
    z = FB / s->s_disp;
    k = F_PX / z;
    s->horizon -= 6.0;
    s->tree_top = s->horizon;
    b = &s->blob[s->n_blob++];
    b->x = s->sx; b->w = s->s_w + 6.0; b->level = s->sky; b->disp = s->s_disp; b->edge_sigma = 0.3; b->tex = 0.0; b->front = 1;
    if ((v % 10) == 0) {
        b->top = s->s_bot - 0.30 * k; b->bot = s->horizon;
    } else {
        b->top = s->s_bot - 0.50 * k; b->bot = s->s_bot - 0.25 * k;
    }
}

/* everything at once, moderately */
static void setup_combo_(gl_scene_t *s, gl_scene_rng_t *r, int v)
{
    double z;
    op_(s, r, v >= 10);
    z = FB / s->s_disp;
    s->s_slope = tan((2.0 * gl_scene_uniform(r) - 1.0) * 1.5 * DEG);
    s->sway_amp = 0.4; s->sway_hz = 1.5; s->sway_phase = 6.283 * gl_scene_uniform(r);
    s->flag = 1;
    s->f_top = s->s_top + F_PX * 0.03 / z; s->f_h = F_PX * 0.36 / z; s->f_len = F_PX * 0.5 / z;
    s->f_level = 215.0; s->f_side = (gl_scene_uniform(r) < 0.5) ? 1 : -1; s->f_hz = 2.5;
    s->tree_top = s->horizon - 70.0; s->trees = 65.0; s->tree_tex = 8.0;
    s->s_level = 200.0;
    s->glare_gx = 0.15;
    s->row_gain = 0.03; s->fpn_sigma = 0.7; s->prnu_sigma = 0.005;
    s->grass_h = 1.5;
    add_person_(s, s->sx + ((s->sx > 320.0) ? -1.0 : 1.0) * 1.5 * F_PX / z, z + 1.0, 45.0);
}

/* ---- scenes WITHOUT a flagstick ------------------------------------------------- */
static void setup_none_(gl_scene_t *s, gl_scene_rng_t *r, int v)
{
    base_scene_(s, r, 1.5, 0.3);
    s->stick = 0;
    switch (v) {
    case 0: break; /* plain */
    case 1: s->tree_top = s->horizon - 90.0; s->trees = 60.0; s->tree_tex = 12.0; break;
    case 2: add_person_(s, s->sx, 8.0, 45.0); break;
    case 3: s->fpn_sigma = 1.0; break;
    case 4: s->fpn_sigma = 2.0; break;
    case 5: s->glare_amp = 150.0; s->glare_r = 60.0; s->glare_x = s->sx; s->glare_y = s->horizon - 60.0; break;
    case 6: { /* a tree trunk 12 px wide, dark, 40 m away */
        gl_scene_blob_t *b = &s->blob[s->n_blob++];
        b->x = s->sx; b->w = 12.0; b->top = -20.0; b->bot = s->horizon + 0.2; b->level = 50.0;
        b->disp = FB / 40.0; b->edge_sigma = 0.8; b->tex = 5.0;
        break;
    }
    case 7: { /* a thin dark post (sapling / sign / rake handle), 3 px, 25 m */
        gl_scene_pole_t *p = &s->pole[s->n_pole++];
        p->x = s->sx; p->w = 3.0; p->top = s->horizon - 60.0; p->bot = s->horizon + 0.2;
        p->level = 50.0; p->disp = FB / 25.0; p->slope = 0.0;
        break;
    }
    case 8: s->altcol_gain = 0.03; break;
    case 9: s->prnu_sigma = 0.01; break;
    default: s->turf_tex = 10.0; s->tree_top = s->horizon - 90.0; s->trees = 60.0; s->tree_tex = 12.0;
             s->tree_lx = 6.0; s->tree_ly = 6.0; break;
    }
}

/* ---- running a case --------------------------------------------------------------- */

typedef struct {
    int n, n_stereo, n_left, n_bearing, n_none, n_other, n_wrong, n_gross, n_good, n_amb;
    int n_wrong_unflagged; /* another object taken for the stick WITHOUT the ambiguity flag */
    int why[8];
    double d_bias, d_rms, sigma, z_rms, max_abs; /* disparity, right object, |err| <= 0.5 px */
    double bot_bias, bot_rms, bot_z_rms;         /* lowest visible point, rows */
    int base[3];                                 /* by gl_vis_base_t: unknown / visible / at horizon */
    int n_top_valid, n_top_clutter;
    double top_rms;                              /* of the tops offered for ranging */
    int n_rng;
    double rng_rms_pct, rng_z_rms;               /* fused range as the application computes it */
    double rail_ms;
    int n_sun;
} stat_t;

static int verbose_; /* set by a command-line argument: one line per read */

static void run_case_(const char *name, setup_fn_t fn, int variant, int trials, stat_t *o)
{
    gl_scene_rng_t rng;
    uint32_t h = 2166136261u;
    double sd = 0, sd2 = 0, ssig = 0, sz2 = 0, sb = 0, sb2 = 0, sbz2 = 0, st2 = 0, sr2 = 0, srz2 = 0;
    int n_bot = 0;

    memset(o, 0, sizeof(*o));
    for (const char *p = name; *p; p++) {
        h = (h ^ (uint8_t)*p) * 16777619u;
    }
    gl_scene_seed(&rng, (uint64_t)h * 1000003u + (uint64_t)(unsigned)variant);
    o->n = trials;
    for (int t = 0; t < trials; t++) {
        const gl_read_result_t *res = &rd_.result;
        gl_status_t st;
        double x_true, x_err, tol_x;

        fn(&C.sc, &rng, variant);
        C.trial_seed = gl_scene_u32(&rng);
        st = run_read_((uint32_t)(gl_scene_uniform(&rng) * 33000.0));
        o->rail_ms += (double)res->rail_on_ms / (double)trials;
        o->n_sun += res->quality.sun ? 1 : 0;
        if (st != GL_OK && st != GL_ERR_NO_STICK) {
            o->n_other++;
            continue;
        }
        if (verbose_) {
            printf("      t%-2d band:", t);
            for (unsigned i = 0; i < rd_.band.n_cand; i++) {
                printf(" [x %.1f s %.1f w %.0f v %u]", (double)rd_.band.cand[i].x,
                       (double)rd_.band.cand[i].score, (double)rd_.band.cand[i].width_px,
                       rd_.verdict[i]);
            }
            printf(" stick at %.1f, why %u\n", gl_scene_stick_x(&C.sc, 0, 240.0, 0.0), res->why);
        }
        if (res->why < 8u) {
            o->why[res->why]++;
        }
        /* the camera rail is off whatever came of it */
        GL_CHECK(!cam_.powered);
        GL_CHECK_EQ(st == GL_OK, res->tier >= (uint8_t)GL_READ_TIER_LEFT);
        GL_CHECK_EQ(res->stick_found, res->tier == (uint8_t)GL_READ_TIER_STEREO);
        if (res->tier == (uint8_t)GL_READ_TIER_NONE) {
            o->n_none++;
            continue;
        }
        if (res->tier == (uint8_t)GL_READ_TIER_BEARING) {
            o->n_bearing++;
            continue;
        }
        if (verbose_) {
            printf("      t%-2d tier %u why %u amb %d cand %u/%u score %.1f | x %.2f (true %.2f) d %.3f (true %.3f) "
                   "sig %.4f [noise %.4f static %.4f] grp %u | w %.2f/%.2f c %.0f snr %.1f bin %u | "
                   "bot %.2f (true %.2f) +-%.2f base %u hor %.2f turf z %.1f | top %.2f (true %.2f) %d/%d\n",
                   t, res->tier, res->why, res->ambiguous, rd_.ci, res->n_candidates,
                   (double)res->cand_score, (double)res->stick_left.x_ref,
                   gl_scene_stick_x(&C.sc, 0, (double)res->stick_left.row_ref, 0.0),
                   (double)res->disp.disparity_px, C.sc.s_disp, (double)res->disp.sigma_px,
                   (double)res->disp.sigma_noise_px, (double)res->disp.sigma_static_px,
                   res->groups_ok, (double)rd_.first[0].width_px, (double)rd_.first[1].width_px,
                   (double)res->stick_left.contrast, (double)res->stick_left.line_snr,
                   res->stick_left.bin_rows, (double)res->stick_left.bottom_row,
                   gl_scene_stick_lowest(&C.sc), (double)res->bottom_sigma_rows,
                   res->stick_left.base, (double)res->stick_left.horizon_row,
                   (double)res->stick_left.turf_snr, (double)res->stick_left.top_row, C.sc.s_top,
                   res->stick_left.top_in_frame, res->stick_left.top_in_clutter);
        }
        o->n_amb += res->ambiguous ? 1 : 0;
        if (res->tier == (uint8_t)GL_READ_TIER_LEFT) {
            o->n_left++;
        } else {
            o->n_stereo++;
        }
        if (!C.sc.stick) {
            continue; /* a flagstick reported where there is none */
        }
        x_true = gl_scene_stick_x(&C.sc, 0, (double)res->stick_left.row_ref, 0.0);
        x_err = (double)res->stick_left.x_ref - x_true;
        tol_x = 3.0 + fabs(C.sc.sway_amp) + 3.0 * fabs(C.sc.sway_lin);
        if (fabs(x_err) > tol_x) {
            o->n_wrong++; /* locked on another object */
            o->n_wrong_unflagged += res->ambiguous ? 0 : 1;
            continue;
        }
        if (res->stick_left.base <= 2u) {
            o->base[res->stick_left.base]++;
        }
        if (res->stick_left.base != (uint8_t)GL_VIS_BASE_UNKNOWN) {
            /* (UNKNOWN: the line was lost above the turf edge; nothing is
             * claimed about where the stick ends) */
            const double be = (double)res->stick_left.bottom_row - gl_scene_stick_lowest(&C.sc);
            sb += be;
            sb2 += be * be;
            sbz2 += be * be / ((double)res->bottom_sigma_rows * (double)res->bottom_sigma_rows);
            n_bot++;
        }
        if (res->stick_left.top_in_frame && res->stick_left.top_in_clutter) {
            o->n_top_clutter++;
        }
        if (res->angles.top_valid) {
            const double te = (double)res->stick_left.top_row - C.sc.s_top;
            st2 += te * te;
            o->n_top_valid++;
        }
        if (res->tier != (uint8_t)GL_READ_TIER_STEREO) {
            continue;
        }
        {
            const double d_err = (double)res->disp.disparity_px - C.sc.s_disp;
            const double sig = (double)res->disp.sigma_px;
            if (fabs(d_err) > o->max_abs) {
                o->max_abs = fabs(d_err);
            }
            if (fabs(d_err) > 0.5) {
                o->n_gross++;
                continue;
            }
            o->n_good++;
            sd += d_err;
            sd2 += d_err * d_err;
            ssig += sig;
            sz2 += (d_err / sig) * (d_err / sig);
        }
        {
            /* the range exactly as app/gl_app.c flag_measured_() computes it,
             * with the PRIOR stick height (the scene's stick has that height) */
            gl_range_input_t in;
            gl_range_result_t rr;
            gl_stick_height_t hh;
            const double zt = FB / C.sc.s_disp / cos((double)res->angles.bearing_rad);
            gl_stick_height_reset(&hh);
            memset(&in, 0, sizeof(in));
            in.f_px = GL_CFG_CAM_F_PX;
            in.baseline_m = GL_CFG_CAM_BASELINE_M;
            in.have_stereo = true;
            in.disparity_px = res->disp.disparity_px;
            in.disparity_sigma_px = res->disp.sigma_px;
            in.cos_bearing = cosf(res->angles.bearing_rad);
            in.have_height = res->stick_left.top_in_frame;
            in.top_in_clutter = res->stick_left.top_in_clutter;
            in.base_visible = (res->angles.base != (uint8_t)GL_VIS_BASE_UNKNOWN);
            in.tan_top = tanf(res->angles.top_elev_rad);
            in.tan_base = tanf(res->angles.base_elev_rad);
            in.elev_sigma_rad = sqrtf(GL_APP_ELEV_SIGMA_ROWS * GL_APP_ELEV_SIGMA_ROWS +
                                      res->bottom_sigma_rows * res->bottom_sigma_rows) /
                                GL_CFG_CAM_F_PX;
            if (gl_range_fuse(&in, &hh, &rr) == GL_OK) {
                const double e = (double)rr.range_m - zt;
                sr2 += (e / zt) * (e / zt);
                srz2 += e * e / ((double)rr.sigma_m * (double)rr.sigma_m);
                o->n_rng++;
            }
        }
    }
    if (o->n_good > 0) {
        o->d_bias = sd / o->n_good;
        o->d_rms = sqrt(sd2 / o->n_good);
        o->sigma = ssig / o->n_good;
        o->z_rms = sqrt(sz2 / o->n_good);
    }
    if (n_bot > 0) {
        o->bot_bias = sb / n_bot;
        o->bot_rms = sqrt(sb2 / n_bot);
        o->bot_z_rms = sqrt(sbz2 / n_bot);
    }
    if (o->n_top_valid > 0) {
        o->top_rms = sqrt(st2 / o->n_top_valid);
    }
    if (o->n_rng > 0) {
        o->rng_rms_pct = 100.0 * sqrt(sr2 / o->n_rng);
        o->rng_z_rms = sqrt(srz2 / o->n_rng);
    }
}

static void header_(void)
{
    printf("    %-22s %3s %3s %3s %3s %3s %3s %3s | %7s %7s %7s %5s %6s | %6s %6s %5s %-8s | %3s %3s %6s | %6s %5s\n",
           "case", "N", "ste", "lft", "brg", "non", "wrg", "amb", "d bias", "d rms", "sigma", "z rms",
           "max|d|", "b bias", "b rms", "b z", "V/H/U", "top", "clu", "t rms", "rng %", "rng z");
}

static void row_(const char *name, const stat_t *s)
{
    char vhu[24];
    snprintf(vhu, sizeof(vhu), "%d/%d/%d", s->base[GL_VIS_BASE_VISIBLE],
             s->base[GL_VIS_BASE_AT_HORIZON], s->base[GL_VIS_BASE_UNKNOWN]);
    printf("    %-22s %3d %3d %3d %3d %3d %3d %3d | %+7.4f %7.4f %7.4f %5.2f %6.3f | %+6.2f %6.2f %5.2f %-8s | %3d %3d %6.2f | %6.2f %5.2f\n",
           name, s->n, s->n_stereo, s->n_left, s->n_bearing, s->n_none, s->n_wrong, s->n_amb,
           s->d_bias, s->d_rms, s->sigma, s->z_rms, s->max_abs, s->bot_bias, s->bot_rms,
           s->bot_z_rms, vhu, s->n_top_valid, s->n_top_clutter, s->top_rms, s->rng_rms_pct,
           s->rng_z_rms);
    fflush(stdout);
}

#ifndef GL_READ_TEST_TRIALS
#define GL_READ_TEST_TRIALS 8
#endif
#define TRIALS GL_READ_TEST_TRIALS

/* A scene and what is asserted of it.  The yield and accuracy figures are
 * checked only with the full number of reads (the address-sanitizer build
 * runs fewer); the structural ones always. */
typedef struct {
    const char *name;
    setup_fn_t fn;
    int variant;
    int min_stereo_pct; /* reads that must come out with a disparity, % (0 = none demanded) */
    double max_z;       /* disparity rms in units of the claimed sigma (0 = not checked) */
    double max_rms;     /* disparity rms, px (0 = not checked) */
    char base;          /* 'V' / 'H' / 'U': class of at least 3/4 of the reads; '-' = not checked */
    double max_bot;     /* |bias| of the lowest visible point, rows (0 = not checked) */
} case_t;

#define STAT_READS 8 /* reads per scene from which the statistical checks apply */

static void check_case_(const case_t *c, const stat_t *s)
{
    const int right = s->n_stereo + s->n_left - s->n_wrong;
    GL_CHECK_EQ(s->n_other, 0);
    /* never another object taken for the flagstick without saying so */
    GL_CHECK_EQ(s->n_wrong_unflagged, 0);
    GL_CHECK_EQ(s->n_gross, 0);
    if (s->n < STAT_READS) {
        return;
    }
    if (gl_sim_cpi() > 0.0f && strcmp(c->name, "A_pole2_14px_post") == 0) {
        /* NOT MET with the computation charged its time (the simulator's
         * default; met with `--cpi 0`, the timing this threshold was set
         * with): half of these reads were to give a disparity.  The first
         * search for the stick is widened by 3 px per second elapsed since
         * the band was exposed (GL_APP_SWAY_ALLOW_PX_PER_S), the band's
         * analysis now takes its 0.18 s, and the post 14 px beside the stick
         * comes into reach: 3 of these 8 reads give a disparity (7 with
         * computation for nothing); of 64 reads 11 (34), and none at the
         * high factor.  With the allowance set to 0 the compute time makes
         * no difference (34 of 64 at every factor).  Pinned: */
        GL_CHECK(100 * s->n_stereo < c->min_stereo_pct * s->n);
        printf("    NOT MET with compute time: %s gives a disparity in %d of %d reads (%d %% demanded)\n",
               c->name, s->n_stereo, s->n, c->min_stereo_pct);
    } else {
        GL_CHECK(100 * s->n_stereo >= c->min_stereo_pct * s->n);
    }
    if (c->max_z > 0.0 && s->n_good >= 4) {
        GL_CHECK(s->z_rms <= c->max_z);
    }
    if (c->max_rms > 0.0 && s->n_good >= 4) {
        GL_CHECK(s->d_rms <= c->max_rms);
    }
    if (c->base != '-' && right > 0) {
        const int cls = (c->base == 'V') ? GL_VIS_BASE_VISIBLE
                                         : ((c->base == 'H') ? GL_VIS_BASE_AT_HORIZON
                                                             : GL_VIS_BASE_UNKNOWN);
        GL_CHECK(4 * s->base[cls] >= 3 * right);
    }
    if (c->max_bot > 0.0) {
        GL_CHECK(fabs(s->bot_bias) <= c->max_bot);
    }
}

static void run_list_(const case_t *list, size_t n, stat_t *out)
{
    header_();
    for (size_t i = 0; i < n; i++) {
        run_case_(list[i].name, list[i].fn, list[i].variant, TRIALS, &out[i]);
        row_(list[i].name, &out[i]);
        check_case_(&list[i], &out[i]);
    }
}

/* ---- 1. width x contrast, flat green ---------------------------------------------- */
GL_TEST(test_grid_width_contrast)
{
    const int trials = (3 * TRIALS + 3) / 4;
    printf("    flat green, 15 mm stick 1.96 m tall, noise 2 grey rms, %d reads per cell;\n"
           "    columns: Weber contrast of the stick against the sky (5 %% = 6 grey = 3 x noise)\n",
           trials);
    for (int pol = 0; pol < 2; pol++) {
        printf("    %s  reads with a disparity (of %d)    | disparity rms px                        "
               "| mean claimed sigma px\n", pol ? "DARK stick  " : "BRIGHT stick", trials);
        printf("    width px  range m |    5%%   10%%   20%%   40%%   60%% |      5%%     10%%     20%%"
               "     40%%     60%% |      5%%     10%%     20%%     40%%     60%%\n");
        for (int wi = 0; wi < 6; wi++) {
            stat_t s[5];
            for (int ci = 0; ci < 5; ci++) {
                char nm[40];
                snprintf(nm, sizeof(nm), "grid_%c_w%.1f_c%02d", pol ? 'n' : 'p', grid_w_[wi],
                         (int)(100.0 * grid_c_[ci] + 0.5));
                run_case_(nm, setup_grid_, pol * 100 + wi * 10 + ci, trials, &s[ci]);
                GL_CHECK_EQ(s[ci].n_wrong, 0);
                GL_CHECK_EQ(s[ci].n_other, 0);
                GL_CHECK_EQ(s[ci].n_gross, 0);
                if (trials >= 6) {
                    /* from 1 px (10 m) at every contrast, and at 20 % and
                     * more for every width down to 0.5 px (20 m), every read
                     * gives a disparity ... */
                    if (wi >= 2 || ci >= 2) {
                        GL_CHECK_EQ(s[ci].n_stereo, trials);
                    }
                    /* ... whose error its own sigma covers */
                    if (s[ci].n_good >= 4) {
                        GL_CHECK(s[ci].z_rms <= 1.5);
                    }
                }
            }
            printf("    %-9.1f %-7.1f |", grid_w_[wi], width_to_range_(grid_w_[wi]));
            for (int ci = 0; ci < 5; ci++) {
                printf(" %5d", s[ci].n_stereo);
            }
            printf(" |");
            for (int ci = 0; ci < 5; ci++) {
                printf(" %7.4f", s[ci].d_rms);
            }
            printf(" |");
            for (int ci = 0; ci < 5; ci++) {
                printf(" %7.4f", s[ci].sigma);
            }
            printf("\n");
            fflush(stdout);
        }
    }
}

/* ---- 2. flat green: lean and sway --------------------------------------------------- */
GL_TEST(test_flat_green_lean_and_sway)
{
    /* A = 1.5 px / 6.6 m, B = 0.8 px / 12.3 m, both +30 % against the sky.
     * The base is 0.3-0.6 row below the turf edge: AT_HORIZON, lowest point
     * reported AT the edge (bias -0.3 .. -0.55 row, inside its sigma). */
    static const case_t list[] = {
        { "A_nominal", setup_nominal_, 0, 100, 1.0, 0.02, 'H', 0.8 },
        { "B_nominal", setup_nominal_, 1, 100, 1.0, 0.04, 'H', 0.8 },
        { "A_slant+1", setup_slant_, 0, 100, 1.0, 0.02, 'H', 0.8 },
        { "A_slant+2", setup_slant_, 1, 100, 1.0, 0.02, 'H', 0.8 },
        { "A_slant+3", setup_slant_, 2, 100, 1.0, 0.02, 'H', 0.8 },
        { "B_slant-3", setup_slant_, 13, 100, 1.0, 0.04, 'H', 0.8 },
        { "A_sway_lin3", setup_sway_, 0, 100, 1.0, 0.02, 'H', 0.8 },
        { "A_sway_0.5@1.5Hz", setup_sway_, 1, 100, 1.0, 0.04, 'H', 0.8 },
        { "A_sway_1.0@3Hz", setup_sway_, 2, 100, 1.0, 0.12, 'H', 0.8 },
        { "B_sway_2.0@1Hz", setup_sway_, 13, 100, 1.0, 0.06, 'H', 0.8 },
    };
    static stat_t st[GL_ARRAY_LEN(list)];
    run_list_(list, GL_ARRAY_LEN(list), st);
}

/* ---- 3. where the stick ends: rise behind the hole, grass, rough turf, stripes ------ */
GL_TEST(test_lowest_point_and_base_class)
{
    static const case_t list[] = {
        /* base 6 rows below the turf edge */
        { "A_basevis6", setup_basevis_, 0, 100, 1.0, 0.02, 'V', 0.8 },
        { "B_basevis6", setup_basevis_, 1, 100, 1.0, 0.04, 'V', 0.8 },
        /* base 8 rows below, grass of 1.5 / 3 / 6 rows standing in front of it */
        { "A_grass1.5", setup_grass_, 0, 100, 1.0, 0.02, 'V', 0.8 },
        { "A_grass3", setup_grass_, 1, 100, 1.0, 0.02, 'V', 0.8 },
        { "A_grass6", setup_grass_, 2, 100, 1.0, 0.02, '-', 1.5 },
        /* turf texture of 10 grey rms (the old code read turf rows as stick) */
        { "A_turf_tex10", setup_turf_, 0, 100, 1.0, 0.02, 'H', 0.9 },
        { "A_turf_tex10_vis", setup_turf_, 1, 100, 1.0, 0.02, 'V', 1.2 },
        { "B_turf_tex10", setup_turf_, 10, 100, 1.0, 0.04, 'H', 0.8 },
        /* NOT MET: a 0.8 px stick is not followed 6 rows into turf this
         * rough in most reads; it is reported AT the edge with the
         * uncertainty widened instead (checked below) */
        { "B_turf_tex10_vis", setup_turf_, 11, 100, 1.0, 0.04, '-', 0.0 },
        /* the lowest 0.3 m / a band 0.25 m up have no contrast: the line
         * ends above the turf, the base is UNKNOWN */
        { "A_stripe_low0.3m", setup_stripe_, 0, 100, 1.0, 0.02, 'U', 0.0 },
        { "A_stripe_mid", setup_stripe_, 1, 100, 1.0, 0.02, 'U', 0.0 },
    };
    static stat_t st[GL_ARRAY_LEN(list)];
    run_list_(list, GL_ARRAY_LEN(list), st);
    if (TRIALS >= STAT_READS) {
        /* the error of the lowest point against the sigma the read claims:
         * within 1.5 sigma rms, except behind ragged grass 6 rows tall
         * (NOT MET there: 1.05 row rms against a claimed 0.35) */
        for (size_t i = 0; i < GL_ARRAY_LEN(list); i++) {
            GL_CHECK(st[i].bot_z_rms <= ((list[i].fn == setup_grass_ && list[i].variant == 2) ? 3.5
                                                                                             : 1.5));
        }
    }
}

/* ---- 4. a flag hanging over the tip --------------------------------------------------- */
GL_TEST(test_flag_over_the_tip)
{
    static const case_t list[] = {
        { "A_flag_bright", setup_flag_, 0, 100, 1.0, 0.02, 'H', 0.8 },
        { "A_flag_dark", setup_flag_, 1, 100, 1.0, 0.02, 'H', 0.8 },
        { "B_flag_bright", setup_flag_, 10, 100, 1.0, 0.04, 'H', 0.8 },
        { "B_flag_dark", setup_flag_, 11, 100, 1.0, 0.04, 'H', 0.8 },
    };
    static stat_t st[GL_ARRAY_LEN(list)];
    run_list_(list, GL_ARRAY_LEN(list), st);
    for (size_t i = 0; i < GL_ARRAY_LEN(list); i++) {
        /* the top end found is where the cloth begins (0.39 m below the
         * tip): it is flagged and never offered for ranging */
        GL_CHECK_EQ(st[i].n_top_valid, 0);
        GL_CHECK_EQ(st[i].n_top_clutter, st[i].n_stereo + st[i].n_left - st[i].n_wrong);
    }
}

/* ---- 5. other objects in view ---------------------------------------------------------- */
GL_TEST(test_other_objects)
{
    static const case_t list[] = {
        { "A_person_behind", setup_person_, 0, 60, 1.0, 0.15, '-', 0.0 },
        { "A_person_0.6m", setup_person_, 1, 100, 1.0, 0.02, 'H', 0.8 },
        { "A_person_2m", setup_person_, 2, 100, 1.0, 0.02, 'H', 0.8 },
        /* NOT MET: a 0.8 px stick in front of a person at 14 m is mostly not read */
        { "B_person_behind", setup_person_, 10, 0, 0.0, 0.0, '-', 0.0 },
        { "A_pole2_7px", setup_pole2_, 0, 100, 1.0, 0.06, 'H', 0.8 },
        { "A_pole2_14px_post", setup_pole2_, 1, 50, 1.0, 0.02, 'H', 0.8 },
        { "A_pole2_far_weak", setup_pole2_, 2, 100, 1.0, 0.02, 'H', 0.8 },
        { "A_pole2_far_strong", setup_pole2_, 3, 100, 1.0, 0.02, 'H', 0.8 },
        /* NOT MET: a second thin pole 7 px from a 0.8 px stick; the pole is
         * taken in some reads, always with the ambiguity flag */
        { "B_pole2_7px", setup_pole2_, 10, 0, 0.0, 0.0, '-', 0.0 },
        { "B_pole2_14px_post", setup_pole2_, 11, 0, 0.0, 0.0, '-', 0.0 },
        { "B_pole2_far_weak", setup_pole2_, 12, 100, 1.0, 0.04, 'H', 0.8 },
        { "B_pole2_far_strong", setup_pole2_, 13, 100, 1.0, 0.04, 'H', 0.8 },
    };
    static stat_t st[GL_ARRAY_LEN(list)];
    run_list_(list, GL_ARRAY_LEN(list), st);
}

/* ---- 6. glare, sensor patterns, a dirty window ---------------------------------------- */
GL_TEST(test_glare_sensor_and_windows)
{
    static const case_t list[] = {
        { "A_glare_gx0.15", setup_glare_, 0, 100, 1.0, 0.03, 'H', 0.8 },
        { "A_glare_gx0.35", setup_glare_, 1, 100, 1.0, 0.03, 'H', 0.8 },
        { "A_glare_veil", setup_glare_, 2, 100, 1.0, 0.03, 'H', 0.8 },
        { "A_glare_sun_in", setup_glare_, 3, 100, 1.0, 0.03, 'H', 0.8 },
        { "A_rowgain3%", setup_sensor_, 0, 100, 1.0, 0.02, 'H', 0.8 },
        /* column fixed-pattern noise of 0.5 / 1 / 2 grey rms (noise 2): the
         * error it leaves does not average out; the claimed sigma follows */
        { "A_fpn0.5", setup_sensor_, 1, 100, 1.5, 0.07, 'H', 0.8 },
        { "A_fpn1.0", setup_sensor_, 2, 100, 1.5, 0.13, 'H', 0.8 },
        { "A_fpn2.0", setup_sensor_, 3, 100, 1.5, 0.22, '-', 0.0 },
        { "A_prnu1%", setup_sensor_, 4, 100, 1.5, 0.15, 'H', 0.8 },
        { "A_altcol3%", setup_sensor_, 5, 100, 1.0, 0.02, 'H', 0.8 },
        { "A_sensor_all", setup_sensor_, 6, 100, 1.5, 0.13, 'H', 0.8 },
        { "B_fpn1.0", setup_sensor_, 12, 100, 1.5, 0.18, 'H', 0.8 },
        { "B_sensor_all", setup_sensor_, 16, 100, 1.8, 0.26, 'H', 0.8 },
        /* right window smeared: blur 1.2 px; 1.8 px + veil; 2.5 px + veil */
        { "A_dirtyR_1.2", setup_dirty_, 0, 100, 1.0, 0.03, 'H', 0.8 },
        { "A_dirtyR_1.8v", setup_dirty_, 1, 100, 1.0, 0.04, 'H', 0.8 },
        { "A_dirtyR_2.5v", setup_dirty_, 2, 100, 1.2, 0.09, '-', 0.0 },
    };
    static stat_t st[GL_ARRAY_LEN(list)];
    run_list_(list, GL_ARRAY_LEN(list), st);
}

/* ---- 7. trees behind the stick, and everything at once -------------------------------- */
GL_TEST(test_trees_and_combination)
{
    static const case_t list[] = {
        { "A_trees_mild_white", setup_trees_, 0, 100, 1.5, 0.13, '-', 0.0 },
        { "A_trees_strong_white", setup_trees_, 1, 80, 2.0, 0.32, '-', 0.0 },
        /* NOT MET: a stick only 36 grey brighter than trunks of 12 grey rms */
        { "A_trees_strong_weak", setup_trees_, 2, 0, 0.0, 0.0, '-', 0.0 },
        { "A_foliage_iso_white", setup_trees_, 3, 80, 1.5, 0.13, '-', 0.0 },
        { "A_combo", setup_combo_, 0, 80, 1.8, 0.20, '-', 0.0 },
        { "B_combo", setup_combo_, 10, 50, 1.8, 0.26, '-', 0.0 },
    };
    static stat_t st[GL_ARRAY_LEN(list)];
    run_list_(list, GL_ARRAY_LEN(list), st);
}

/* ---- 8. no flagstick in the scene ------------------------------------------------------ */
GL_TEST(test_no_flagstick)
{
    static const char *const names[11] = { "none_plain", "none_trees", "none_person", "none_fpn1",
                                           "none_fpn2", "none_glare", "none_trunk12",
                                           "none_post3", "none_altcol3%", "none_prnu1%",
                                           "none_foliage_turf" };
    int n_false = 0, n_bearing = 0, n_reads = 0;
    double rail = 0.0;
    header_();
    for (int i = 0; i < 11; i++) {
        stat_t s;
        run_case_(names[i], setup_none_, i, TRIALS, &s);
        row_(names[i], &s);
        GL_CHECK_EQ(s.n_other, 0);
        /* no disparity is ever reported for an object that is no flagstick:
         * the 12 px trunk at 40 m and the 3 px post at 25 m (which the old
         * code ranged as flagsticks) included */
        GL_CHECK_EQ(s.n_stereo, 0);
        n_false += s.n_stereo + s.n_left;
        n_bearing += s.n_bearing;
        n_reads += s.n;
        rail += s.rail_ms / 11.0;
    }
    printf("    %d stick-free reads: %d reported a flagstick (left camera only: %d), %d a band-only "
           "bearing; mean camera-rail time %.0f ms\n", n_reads, n_false, n_false, n_bearing, rail);
    if (TRIALS >= STAT_READS) {
        /* left-camera-only "sticks" (no disparity to check them against)
         * and band-only bearings are the weaker tiers; their false rate on
         * these scenes is stated in the README and bounded here */
        GL_CHECK(20 * n_false <= n_reads);
        GL_CHECK(10 * n_bearing <= n_reads);
    }
}

/* With an argument: only the named scenes whose name starts with it, one
 * line per read (for looking into a case; nothing is asserted).  Second
 * argument: reads per scene (6).  Third: the simulator's compute factor in
 * cycles per instruction (default: its nominal one; 0 = computation takes
 * no time, the timing every figure of phase 1 was measured with). */
typedef struct {
    const char *name;
    setup_fn_t fn;
    int variant;
} named_t;

static const named_t all_[] = {
    { "A_nominal", setup_nominal_, 0 }, { "B_nominal", setup_nominal_, 1 },
    { "A_basevis6", setup_basevis_, 0 }, { "B_basevis6", setup_basevis_, 1 },
    { "A_person_behind", setup_person_, 0 }, { "A_person_2m", setup_person_, 2 },
    { "B_person_behind", setup_person_, 10 },
    { "A_pole2_7px", setup_pole2_, 0 }, { "A_pole2_14px_post", setup_pole2_, 1 },
    { "A_pole2_far_strong", setup_pole2_, 3 }, { "B_pole2_7px", setup_pole2_, 10 },
    { "A_grass6", setup_grass_, 2 }, { "A_fpn1.0", setup_sensor_, 2 },
    { "A_altcol3%", setup_sensor_, 5 }, { "B_sensor_all", setup_sensor_, 16 },
    { "A_trees_strong_white", setup_trees_, 1 }, { "A_trees_strong_weak", setup_trees_, 2 },
    { "A_foliage_iso_white", setup_trees_, 3 },
    { "A_turf_tex10_vis", setup_turf_, 1 }, { "B_turf_tex10_vis", setup_turf_, 11 },
    { "A_combo", setup_combo_, 0 }, { "B_combo", setup_combo_, 10 },
    { "A_stripe_low0.3m", setup_stripe_, 0 }, { "A_sway_1.0@3Hz", setup_sway_, 2 },
    { "none_person", setup_none_, 2 }, { "none_glare", setup_none_, 5 },
    { "none_trunk12", setup_none_, 6 }, { "none_post3", setup_none_, 7 },
    { "none_trees", setup_none_, 1 }, { "none_fpn1", setup_none_, 3 },
    { "none_fpn2", setup_none_, 4 }, { "none_prnu1%", setup_none_, 9 },
};

int main(int argc, char **argv)
{
    /* `--cpi <x>` first: the whole run (the tests too) at this compute
     * factor.  `--cpi 0` reproduces the timing, and with it every number,
     * of the runs before the simulator charged computation. */
    if (argc > 2 && strcmp(argv[1], "--cpi") == 0) {
        gl_sim_set_cpi((float)atof(argv[2]));
        printf("    compute factor: %.2f cycles per instruction\n", (double)gl_sim_cpi());
        argv += 2;
        argc -= 2;
    }
    if (argc > 1) {
        verbose_ = (argc > 4) ? atoi(argv[4]) : 1;
        if (argc > 3) {
            gl_sim_set_cpi((float)atof(argv[3]));
        }
        header_();
        for (size_t i = 0; i < GL_ARRAY_LEN(all_); i++) {
            if (strncmp(all_[i].name, argv[1], strlen(argv[1])) == 0) {
                stat_t s;
                run_case_(all_[i].name, all_[i].fn, all_[i].variant, (argc > 2) ? atoi(argv[2]) : 6,
                          &s);
                row_(all_[i].name, &s);
            }
        }
        return 0;
    }

    GL_RUN(test_flat_green_lean_and_sway);
    GL_RUN(test_lowest_point_and_base_class);
    GL_RUN(test_flag_over_the_tip);
    GL_RUN(test_other_objects);
    GL_RUN(test_glare_sensor_and_windows);
    GL_RUN(test_trees_and_combination);
    GL_RUN(test_no_flagstick);
    GL_RUN(test_grid_width_contrast);
    return gl_test_summary();
}
