/*
 * vision_bench.c - HOST ONLY: what does the camera part of a read cost, and
 * does the simulator's cost table (hal/host/gl_sim_cost.h) say the same?
 *
 *     make bench-vision                   work done by one read of each scene
 *                                         and what the cost table charges for it
 *     make profile                        the same under valgrind's callgrind:
 *                                         MEASURED instructions against the table
 *                                         (tools/vision_cost.sh)
 *     build/host/vision_bench read <scene>            one whole read
 *     build/host/vision_bench refine <scene> <bin> <n>  n strip refinements
 *     build/host/vision_bench band <scene> <n>        n band analyses
 *     build/host/vision_bench stats <scene> <n>       n strip statistics
 *     build/host/vision_bench render <n>              n result screens
 *     build/host/vision_bench list                    the scene names
 *
 * Each mode does its work inside one function whose name starts with
 * bench_, so that callgrind can count that function alone:
 *     valgrind --tool=callgrind --collect-atstart=no \
 *         --toggle-collect=bench_refine_ build/host/vision_bench refine A 1 32
 *
 * Scenes are the physically consistent ones of tests/test_read.c
 * (tests/synth/gl_scene.c): a 15 mm stick 1.96 m tall on a flat green, sky
 * 120 grey, turf 80, noise 2 grey rms.
 *   A       1.5 px wide (6.6 m), 30 % brighter than the sky: the nominal read
 *   B       0.8 px (12.3 m), 30 %
 *   near3   3.3 px (3.0 m), 30 %
 *   near1   6.6 px (1.5 m), 30 %: the refinement's second pass uses a wider
 *           window than the first and measures every row twice
 *   faint   0.7 px (14 m), 10 %: single rows are below the noise, the read
 *           falls back on 4 rows averaged
 *   faint2  0.5 px (20 m), 20 %: 16 rows averaged
 *   person  A with a person standing 2 m behind the hole (several candidates)
 *   none    no flagstick
 *
 * Not firmware: tools/ is compiled by no firmware target.
 */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "gl_config.h"
#include "gl_hal.h"
#include "gl_read.h"
#include "gl_scene.h"
#include "gl_sim.h"
#include "gl_sim_cost.h"
#include "gl_ui.h"

#define F_PX 657.0
#define FB (F_PX * (double)GL_CFG_CAM_BASELINE_M)

/* The functions callgrind is pointed at must exist as functions. */
#if defined(__GNUC__)
#define BENCH_FN __attribute__((noinline)) static
#else
#define BENCH_FN static
#endif

static gl_ov7692_t cam_;
static gl_read_t rd_;
static gl_scene_t sc_;
static unsigned frames_;

static const char *const scenes_[] = { "A", "B", "near3", "near1", "faint", "faint2", "person",
                                       "none" };

static int make_scene_(const char *name, gl_scene_t *s)
{
    gl_scene_rng_t r;
    double w_px = 1.5, contrast = 0.30, z;
    int stick = 1, person = 0;

    if (strcmp(name, "A") == 0) {
    } else if (strcmp(name, "B") == 0) {
        w_px = 0.8;
    } else if (strcmp(name, "near3") == 0) {
        w_px = 3.3;
    } else if (strcmp(name, "near1") == 0) {
        w_px = 6.6;
    } else if (strcmp(name, "faint") == 0) {
        w_px = 0.7;
        contrast = 0.10;
    } else if (strcmp(name, "faint2") == 0) {
        w_px = 0.5;
        contrast = 0.20;
    } else if (strcmp(name, "person") == 0) {
        person = 1;
    } else if (strcmp(name, "none") == 0) {
        stick = 0;
    } else {
        return 0;
    }
    gl_scene_seed(&r, 20261111u);
    z = 0.015 * F_PX / w_px;
    gl_scene_defaults(s);
    s->seed = gl_scene_u32(&r);
    s->fpn_seed[0] = gl_scene_u32(&r);
    s->fpn_seed[1] = gl_scene_u32(&r);
    s->sky = 120.0;
    s->turf = 80.0;
    s->turf_tex = 3.0;
    s->horizon = 239.5 + (gl_scene_uniform(&r) - 0.5);
    s->tree_top = s->horizon;
    s->stick = stick;
    s->s_w = w_px;
    s->s_disp = FB / z;
    s->sx = 130.0 + 380.0 * gl_scene_uniform(&r);
    s->s_bot = s->horizon + F_PX * 0.00561 / z;
    s->s_top = s->s_bot - F_PX * 1.96 / z;
    s->s_level = s->sky * (1.0 + contrast);
    s->noise = 2.0;
    if (person) {
        /* a person 2 m behind the hole, 60 px beside the stick: torso and legs */
        const double zp = z + 2.0, k = F_PX / zp, xc = s->sx + 60.0;
        const double feet = s->horizon + F_PX * 0.00561 / zp;
        gl_scene_blob_t *b = &s->blob[s->n_blob++];
        b->x = xc; b->w = 0.42 * k; b->top = feet - 1.50 * k; b->bot = feet - 0.80 * k;
        b->level = 45.0; b->disp = FB / zp; b->edge_sigma = 1.0; b->tex = 5.0;
        b = &s->blob[s->n_blob++];
        b->x = xc - 0.12 * k; b->w = 0.13 * k; b->top = feet - 0.82 * k; b->bot = feet;
        b->level = 36.0; b->disp = FB / zp; b->edge_sigma = 0.9; b->tex = 4.0;
        b = &s->blob[s->n_blob++];
        b->x = xc + 0.12 * k; b->w = 0.13 * k; b->top = feet - 0.82 * k; b->bot = feet;
        b->level = 36.0; b->disp = FB / zp; b->edge_sigma = 0.9; b->tex = 4.0;
    }
    return 1;
}

static void scene_cb_(void *ctx, gl_cam_id_t cam, uint16_t x0, uint16_t y0, uint16_t w, uint16_t h,
                      uint32_t frame_no, uint64_t t_us, uint8_t *luma)
{
    (void)ctx;
    (void)frame_no;
    gl_scene_render(&sc_, (cam == GL_CAM_RIGHT) ? 1 : 0, x0, y0, w, h, (double)t_us * 1e-6,
                    977u + frames_ * 7919u, luma);
    frames_++;
}

/* ---- one whole read through the simulator ------------------------------------------ */

BENCH_FN gl_status_t bench_read_(void)
{
    gl_status_t st;
    int guard = 0;
    while ((st = gl_read_step(&rd_)) == GL_ERR_BUSY && guard++ < 40000) {
        gl_hal_delay_ms(1);
    }
    return st;
}

static int run_read_(const char *scene, int quiet)
{
    const gl_vec3_t up = { 0.0f, 0.0f, 1.0f };
    const gl_sim_stats_t *st;
    gl_status_t rs;
    uint64_t model = 0;

    if (!make_scene_(scene, &sc_)) {
        return 2;
    }
    gl_sim_reset(true);
    (void)gl_hal_init();
    gl_sim_cam_set_scene(scene_cb_, NULL);
    gl_sim_cam_set_phase_us(GL_CAM_RIGHT, 9000u);
    gl_ov7692_init(&cam_, NULL);
    gl_read_init(&rd_, &cam_);
    frames_ = 0;
    (void)gl_hal_clock_set(GL_CLOCK_FAST);
    rs = gl_read_start(&rd_, up, GL_APP_LRRL_REPEATS);
    if (rs == GL_OK) {
        rs = bench_read_();
    }
    (void)gl_hal_clock_set(GL_CLOCK_SLOW);
    st = gl_sim_stats();
    for (unsigned p = 0; p < (unsigned)GL_TRACE_COUNT; p++) {
        model += st->stage_instr[p];
    }
    if (!quiet) {
        printf("scene %-7s: %s, tier %u, %u candidates (%u probed), %u strips, bins L %u R %u\n",
               scene, gl_status_name(rs), rd_.result.tier, rd_.result.n_candidates,
               rd_.result.n_probed, rd_.result.strips_captured, rd_.bin[GL_CAM_LEFT],
               rd_.bin[GL_CAM_RIGHT]);
    }
    printf("  %-7s trace points: band %u, strip %u, group %u | cost table: band %.2f M, strips "
           "%.2f M, groups %.2f M, total %.2f M instructions | rail on %.0f ms, compute %.0f ms\n",
           scene, st->trace_points[GL_TRACE_VISION_BAND], st->trace_points[GL_TRACE_VISION_STRIP],
           st->trace_points[GL_TRACE_VISION_GROUP],
           (double)st->stage_instr[GL_TRACE_VISION_BAND] / 1e6,
           (double)st->stage_instr[GL_TRACE_VISION_STRIP] / 1e6,
           (double)st->stage_instr[GL_TRACE_VISION_GROUP] / 1e6, (double)model / 1e6,
           (double)st->cam_rail_on_us / 1e3, (double)st->compute_us / 1e3);
    return 0;
}

/* ---- strips and bands rendered directly --------------------------------------------- */

static uint8_t px_[640 * 96 > 96 * 480 ? 640 * 96 : 96 * 480];
static gl_vis_stick_work_t wk_;
static gl_vis_band_work_t bw_;

static void strip_for_(gl_strip_t *strip, gl_vis_prior_t *p, unsigned i, unsigned bin)
{
    const int cam = (int)(i & 1u);
    const double xs = sc_.stick ? gl_scene_stick_x(&sc_, cam, 240.0, 0.0) : (200.0 + 7.0 * (double)i);
    int x0 = (int)floor(xs + 0.5) - 48 + (int)(i % 9u) - 4;
    if (x0 < 0) {
        x0 = 0;
    }
    if (x0 > 640 - 96) {
        x0 = 640 - 96;
    }
    gl_scene_render(&sc_, cam, x0, 0, 96, 480, 0.03 * (double)i, 4099u + 7919u * i, px_);
    strip->px = px_;
    strip->width = 96;
    strip->height = 480;
    strip->stride = 96;
    strip->x0 = (uint16_t)x0;
    strip->y0 = 0;
    /* the prior of a strip in the middle of a read: the line of the camera's
     * previous strip (here: the truth, a fraction of a pixel off), the
     * default search, the turf edge known to a row */
    memset(p, 0, sizeof(*p));
    p->row = 200.0f;
    p->x = (float)(sc_.stick ? gl_scene_stick_x(&sc_, cam, 200.0, 0.0) : xs) +
           0.3f * (float)((int)(i % 5u) - 2);
    p->slant = (float)sc_.s_slope;
    p->width_px = (sc_.s_w < 2.0) ? 1.0f : ((sc_.s_w < 5.0) ? 3.0f : 7.0f);
    p->search_px = 0.0f;
    p->have_horizon = true;
    p->horizon_row = (float)sc_.horizon;
    p->horizon_tol_rows = 6.0f;
    p->bin_rows = (uint8_t)bin;
}

BENCH_FN unsigned bench_refine_(const gl_strip_t *strip, const gl_vis_prior_t *p)
{
    gl_vis_stick_t out;
    return (gl_vis_stick_refine(strip, p, &wk_, &out) == GL_OK) ? 1u : 0u;
}

BENCH_FN void bench_stats_(const gl_strip_t *strip)
{
    gl_vis_stats_t st;
    gl_vis_strip_stats(strip, wk_.tmp, &st);
}

BENCH_FN unsigned bench_band_(const gl_strip_t *band)
{
    gl_vis_band_result_t out;
    return (gl_vis_band_analyse(band, &bw_, &out) == GL_OK) ? out.n_cand : 0u;
}

static gl_ui_t ui_;
static gl_gfx_t gfx_;

BENCH_FN void bench_render_(const gl_ui_view_t *v)
{
    gl_ui_render(&ui_, v, &gfx_);
}

int main(int argc, char **argv)
{
    if (argc >= 2 && strcmp(argv[1], "list") == 0) {
        for (size_t i = 0; i < sizeof(scenes_) / sizeof(scenes_[0]); i++) {
            printf("%s\n", scenes_[i]);
        }
        return 0;
    }
    if (argc >= 3 && strcmp(argv[1], "read") == 0) {
        return run_read_(argv[2], 0);
    }
    if (argc >= 2 && strcmp(argv[1], "all") == 0) {
        printf("one read of each scene on the simulator (cycles per instruction %.1f, %u MHz):\n",
               (double)GL_SIM_CPI_NOMINAL, (unsigned)(GL_SIM_CLOCK_FAST_HZ / 1000000u));
        for (size_t i = 0; i < sizeof(scenes_) / sizeof(scenes_[0]); i++) {
            (void)run_read_(scenes_[i], 1);
        }
        return 0;
    }
    if (argc >= 5 && strcmp(argv[1], "refine") == 0) {
        const unsigned bin = (unsigned)atoi(argv[3]), n = (unsigned)atoi(argv[4]);
        unsigned ok = 0;
        if (!make_scene_(argv[2], &sc_)) {
            return 2;
        }
        for (unsigned i = 0; i < n; i++) {
            gl_strip_t strip;
            gl_vis_prior_t p;
            strip_for_(&strip, &p, i, bin);
            ok += bench_refine_(&strip, &p);
        }
        printf("refine %s bin %u: %u calls, %u found a line, %u did not\n", argv[2], bin, n, ok,
               n - ok);
        return 0;
    }
    if (argc >= 4 && strcmp(argv[1], "stats") == 0) {
        const unsigned n = (unsigned)atoi(argv[3]);
        if (!make_scene_(argv[2], &sc_)) {
            return 2;
        }
        for (unsigned i = 0; i < n; i++) {
            gl_strip_t strip;
            gl_vis_prior_t p;
            strip_for_(&strip, &p, i, 1);
            bench_stats_(&strip);
        }
        printf("stats %s: %u calls\n", argv[2], n);
        return 0;
    }
    if (argc >= 4 && strcmp(argv[1], "band") == 0) {
        const unsigned n = (unsigned)atoi(argv[3]);
        unsigned cand = 0;
        if (!make_scene_(argv[2], &sc_)) {
            return 2;
        }
        for (unsigned i = 0; i < n; i++) {
            gl_strip_t band;
            const int y0 = (int)floor(sc_.horizon + 0.5) - 48;
            gl_scene_render(&sc_, 0, 0, y0, 640, 96, 0.0, 31u + 7919u * i, px_);
            band.px = px_;
            band.width = 640;
            band.height = 96;
            band.stride = 640;
            band.x0 = 0;
            band.y0 = (uint16_t)y0;
            cand += bench_band_(&band);
        }
        printf("band %s: %u calls, %u candidates in all\n", argv[2], n, cand);
        return 0;
    }
    if (argc >= 3 && strcmp(argv[1], "render") == 0) {
        const unsigned n = (unsigned)atoi(argv[2]);
        gl_settings_t set;
        gl_ui_view_t v;
        gl_settings_defaults(&set);
        gl_ui_init(&ui_, &set, 0);
        gl_gfx_init(&gfx_);
        ui_.state = (uint8_t)GL_UI_SHOW_RESULT;
        memset(&v, 0, sizeof(v));
        v.have_result = true;
        v.solved = true;
        v.line_here = true;
        v.flag_found = true;
        v.distance_m = 6.0f;
        v.plays_like_m = 7.4f;
        v.slope_pct = 2.3f;
        v.break_cups = 2.7f;
        v.confidence = 0.6f;
        v.aim_rad = 0.08f;
        v.fall_line_rad = -1.2f;
        v.battery_pct = 80;
        for (unsigned i = 0; i < n; i++) {
            v.aim_rad = 0.08f + 0.01f * (float)(i % 7u);
            bench_render_(&v);
        }
        printf("render: %u result screens\n", n);
        return 0;
    }
    fprintf(stderr, "usage: vision_bench all | list | read <scene> | refine <scene> <bin> <n> | "
                    "band <scene> <n> | stats <scene> <n> | render <n>\n");
    return 2;
}
