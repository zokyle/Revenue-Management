/*
 * solver_bench.c - HOST ONLY: how much work does one estimate cost?
 *
 *     make bench                         the table below
 *     build/host/solver_bench <case>     one estimate of the named case, for
 *                                        counting instructions:
 *     valgrind --tool=callgrind --collect-atstart=no --toggle-collect=bench_estimate_ \
 *         build/host/solver_bench typical
 *
 * Everything runs in SINGLE precision with the firmware's default options
 * (the build the target runs; here compiled for the host).  The cost driver
 * is the number of RK4 steps of the trial rolls; the program reports it
 * together with the trial rolls and the fit iterations.
 *
 * Cases:
 *   typical   the Quick Read (mode B1) of the simulated reads whose step
 *             count is the median of its mode
 *   survey3   the same for the three-drop Survey
 *   b2        the same for method B2 with a horizon
 *   worst     the costliest estimates anybody has constructed (the phase-2
 *             review's searches; NOT a proven maximum), each without a step
 *             budget (the solver's default, the reference) and with the
 *             application's (GL_APP_SOLVE_MAX_STEPS):
 *               W2  26 m by stereo, method B1, tilt 6.8 %: neither the patch
 *                   nor its secant plane can be solved, both solves run to
 *                   their roll budget
 *               W1  30 m dialled, down a slope at 0.90 of critical: a
 *                   tilt-only plane, which used to be solved twice
 *               W0  the case this table had before the review (20.7 m)
 *   worst-budget   W2 with the application's step budget, for callgrind
 *
 * Not firmware: tools/ is compiled by no firmware target.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <math.h>

#include "gl_app_cfg.h"
#include "gl_solver.h"
#include "gl_solver_run.h"

typedef struct {
    unsigned index;
    uint32_t steps;
} pick_t;

static int cmp_pick_(const void *a, const void *b)
{
    const pick_t *x = (const pick_t *)a, *y = (const pick_t *)b;
    return (x->steps > y->steps) - (x->steps < y->steps);
}

/** Index of the simulated read of `mode` (with or without a horizon) whose
 *  step count is the median of that mode; prints the spread. */
static unsigned median_case_(const char *mode, int need_horizon, int quiet)
{
    static pick_t picks[512];
    unsigned n = 0u;
    double sum_steps = 0.0, sum_rolls = 0.0;
    uint32_t max_iter = 0u;
    for (unsigned i = 0; i < gl_vec_n_est_original && n < 512u; i++) {
        const gl_vec_est_case_t *c = &gl_vec_est[i];
        gl_vec_est_result_t r;
        if (strcmp(c->mode, mode) != 0 || (need_horizon && !c->exp.used_horizon)) {
            continue;
        }
        gl_vec32_estimate(c, GL_VEC_TOL_DEFAULT, 0, &r);
        picks[n].index = i;
        picks[n].steps = r.n_steps;
        sum_steps += (double)r.n_steps;
        sum_rolls += (double)r.n_rolls;
        max_iter = (r.n_iter > max_iter) ? r.n_iter : max_iter;
        n++;
    }
    if (n == 0u) {
        return 0u;
    }
    qsort(picks, n, sizeof(picks[0]), cmp_pick_);
    if (!quiet) {
        printf("  %-10s %3u reads: RK4 steps min %lu, median %lu, max %lu, mean %.0f; trial rolls mean %.1f; "
               "fit iterations at most %lu\n",
               mode, n, (unsigned long)picks[0].steps, (unsigned long)picks[n / 2u].steps,
               (unsigned long)picks[n - 1u].steps, sum_steps / (double)n, sum_rolls / (double)n,
               (unsigned long)max_iter);
    }
    return picks[n / 2u].index;
}

/** W2 (the safety review's search, seed 11): 26.0 m by stereo, method B1. */
static float worst_w2_(gl_measurements_t *m)
{
    gl_solver_measurements_init(m);
    m->tilt_x = (float)0.0041603158475774019;
    m->tilt_y = (float)-0.06771927674515206;
    m->stimp_ft = 12.0f;
    m->flag_found = true;
    m->flag_bearing_rad = (float)-0.3758663894382302;
    m->flag_disparity_px = (float)(657.0 * 0.02 / 26.014521134960443);
    m->flag_low_elev_rad = (float)(-0.023759670697298448 - 0.0056 / 26.014521134960443);
    m->flag_base_visible = false;
    m->stick_height_est_m = 2.1f;
    m->stick_height_rel_sigma = 0.05f;
    return 0.64f; /* the pace of the case: 64 cm past */
}

/** W1 (the safety review's search, seed 21): 30 m dialled, down a slope at
 *  0.90 of critical, Stimp 12.5; flag found but not ranged. */
static float worst_w1_(gl_measurements_t *m)
{
    const double stimp = 12.5, a_r = 1.83 * 1.83 / (2.0 * stimp * 0.3048), crit = a_r / (5.0 / 7.0 * 9.80665);
    const double b = 0.33910485203911905, sx = -0.89850998513005353 * crit, sy = -0.27816065634007064 * crit;
    const double d = 29.985267577435099;
    gl_solver_measurements_init(m);
    m->tilt_x = (float)(sx * cos(b) - sy * sin(b));
    m->tilt_y = (float)(sx * sin(b) + sy * cos(b));
    m->stimp_ft = (float)stimp;
    m->flag_found = true;
    m->flag_bearing_rad = (float)b;
    m->user_distance_m = 0.01f * (float)floor(d * 100.0 + 0.5);
    m->flag_low_elev_rad = (float)(0.024216351276332825 - 0.0056 / d);
    m->flag_base_visible = false;
    m->stick_height_est_m = 2.1f;
    m->stick_height_rel_sigma = 0.05f;
    return 0.38f;
}

/** W0, the worst case of this table before the review: 20.74 m, tilt
 *  (-0.74 %, -6.61 %), Stimp 12.72; the stick's base where a patch with
 *  c = 0.0008 /m puts it. */
static void worst_case_(gl_measurements_t *m)
{
    gl_solver_measurements_init(m);
    m->h_cam_m = 0.0056f; /* the lens height of the reference's camera, with which the case was found */
    m->tilt_x = -0.0074f;
    m->tilt_y = -0.0661f;
    m->flag_found = true;
    m->flag_bearing_rad = 0.0f;
    m->flag_disparity_px = 0.6336f;       /* f b / 20.74 m */
    m->flag_low_elev_rad = 0.000662152f;
    m->flag_base_visible = true;
    m->stimp_ft = 12.7245f;
}

/**
 * ONE estimate, and nothing else: the function to collect under callgrind
 * (--toggle-collect=bench_estimate_).  `c` != NULL: a vector case; else the
 * placement `m`.
 */
static float bench_past_ = 0.30f;
static uint32_t bench_max_steps_ = 0u;

#if defined(__GNUC__)
__attribute__((noinline))
#endif
static void bench_estimate_(const gl_vec_est_case_t *c, const gl_measurements_t *m, gl_vec_est_result_t *r)
{
    static gl_solver_work_t work;
    if (c != NULL) {
        gl_vec32_estimate(c, GL_VEC_TOL_DEFAULT, 0, r);
    } else {
        gl_solver_options_t opt;
        gl_estimate_t e;
        gl_solver_default_options(&opt);
        opt.past_m = bench_past_;
        opt.max_steps = bench_max_steps_;
        r->status = (int)gl_solver_estimate(m, &opt, &work, &e);
        r->aim_source = e.aim_source;
        r->solve_status = e.solve_status;
        r->n_rolls = e.n_rolls;
        r->n_steps = e.n_steps;
        r->n_iter = work.fit.n_iter;
        r->distance = (double)e.distance_m;
    }
}

static void run_worst_one_(const char *name, const char *what, const gl_measurements_t *m, float past,
                           uint32_t max_steps)
{
    gl_vec_est_result_t r;
    memset(&r, 0, sizeof(r));
    bench_past_ = past;
    bench_max_steps_ = max_steps;
    bench_estimate_(NULL, m, &r);
    bench_past_ = 0.30f;
    bench_max_steps_ = 0u;
    printf("  %-10s %s, %s: status %d, aim_source %u, solve_status %u, %lu trial rolls, %lu RK4 steps, %lu fit "
           "iterations\n", name, what, (max_steps != 0u) ? "application's step budget" : "no step budget", r.status,
           (unsigned)r.aim_source, (unsigned)r.solve_status, (unsigned long)r.n_rolls, (unsigned long)r.n_steps,
           (unsigned long)r.n_iter);
}

static void run_worst_(int budget_only)
{
    gl_measurements_t m;
    float past = worst_w2_(&m);
    if (budget_only) {
        run_worst_one_("worst", "W2, 26 m by stereo, B1", &m, past, GL_APP_SOLVE_MAX_STEPS);
        return;
    }
    run_worst_one_("worst", "W2, 26 m by stereo, B1", &m, past, 0u);
    run_worst_one_("worst", "W2, 26 m by stereo, B1", &m, past, GL_APP_SOLVE_MAX_STEPS);
    past = worst_w1_(&m);
    run_worst_one_("worst", "W1, 30 m dialled, 0.90 of critical", &m, past, 0u);
    run_worst_one_("worst", "W1, 30 m dialled, 0.90 of critical", &m, past, GL_APP_SOLVE_MAX_STEPS);
    worst_case_(&m);
    run_worst_one_("worst", "W0, 20.7 m (this table before the review)", &m, 0.30f, 0u);
}

static void run_one_(unsigned index, const char *name)
{
    gl_vec_est_result_t r;
    bench_estimate_(&gl_vec_est[index], NULL, &r);
    printf("  %-10s case %u (%s, %u drop(s)): status %d, %lu trial rolls, %lu RK4 steps, %lu fit iterations\n", name,
           gl_vec_est[index].id, gl_vec_est[index].mode, gl_vec_est[index].n_drops, r.status,
           (unsigned long)r.n_rolls, (unsigned long)r.n_steps, (unsigned long)r.n_iter);
}

int main(int argc, char **argv)
{
    const char *which = (argc > 1) ? argv[1] : "all";
    if (strcmp(which, "all") == 0) {
        printf("single precision, firmware default options; spread over the simulated reads of each mode:\n");
        (void)median_case_("B1", 0, 0);
        (void)median_case_("PRECISION", 0, 0);
        (void)median_case_("SURVEY2", 0, 0);
        (void)median_case_("SURVEY3", 0, 0);
        (void)median_case_("B2", 1, 0);
        (void)median_case_("B0", 0, 0);
        (void)median_case_("FLAG_OUT", 0, 0);
        printf("the cases measured one at a time:\n");
        run_one_(median_case_("B1", 0, 1), "typical");
        run_one_(median_case_("SURVEY3", 0, 1), "survey3");
        run_one_(median_case_("B2", 1, 1), "b2");
        run_worst_(0);
        return 0;
    }
    if (strcmp(which, "typical") == 0) {
        run_one_(median_case_("B1", 0, 1), which);
    } else if (strcmp(which, "survey3") == 0) {
        run_one_(median_case_("SURVEY3", 0, 1), which);
    } else if (strcmp(which, "b2") == 0) {
        run_one_(median_case_("B2", 1, 1), which);
    } else if (strcmp(which, "worst") == 0) {
        run_worst_(0);
    } else if (strcmp(which, "worst-budget") == 0) {
        run_worst_(1);
    } else {
        fprintf(stderr, "usage: solver_bench [all | typical | survey3 | b2 | worst | worst-budget]\n");
        return 2;
    }
    return 0;
}
