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
 *   worst     the costliest estimate that could be constructed: a 20.7 m
 *             putt across a slope near the limit of what the green holds,
 *             on which neither the patch nor its secant plane can be
 *             solved (both solves run to their roll budget)
 *
 * Not firmware: tools/ is compiled by no firmware target.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

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

/** The costliest estimate that could be constructed (see the header):
 *  20.74 m, tilt (-0.74 %, -6.61 %), Stimp 12.72; the stick's base where a
 *  patch with c = 0.0008 /m puts it. */
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
        r->status = (int)gl_solver_estimate(m, &opt, &work, &e);
        r->aim_source = e.aim_source;
        r->solve_status = e.solve_status;
        r->n_rolls = e.n_rolls;
        r->n_steps = e.n_steps;
        r->n_iter = work.fit.n_iter;
        r->distance = (double)e.distance_m;
    }
}

static void run_worst_(void)
{
    gl_measurements_t m;
    gl_vec_est_result_t r;
    memset(&r, 0, sizeof(r));
    worst_case_(&m);
    bench_estimate_(NULL, &m, &r);
    printf("  %-10s 20.7 m across a slope near the limit: status %d, aim_source %u, solve_status %u, %lu trial "
           "rolls, %lu RK4 steps, %lu fit iterations\n",
           "worst", r.status, (unsigned)r.aim_source, (unsigned)r.solve_status, (unsigned long)r.n_rolls,
           (unsigned long)r.n_steps, (unsigned long)r.n_iter);
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
        run_worst_();
        return 0;
    }
    if (strcmp(which, "typical") == 0) {
        run_one_(median_case_("B1", 0, 1), which);
    } else if (strcmp(which, "survey3") == 0) {
        run_one_(median_case_("SURVEY3", 0, 1), which);
    } else if (strcmp(which, "b2") == 0) {
        run_one_(median_case_("B2", 1, 1), which);
    } else if (strcmp(which, "worst") == 0) {
        run_worst_();
    } else {
        fprintf(stderr, "usage: solver_bench [all | typical | survey3 | b2 | worst]\n");
        return 2;
    }
    return 0;
}
