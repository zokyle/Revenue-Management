/*
 * diff_solver_abi.c - HOST ONLY, part of the shared library that
 * tools/diff_solver.py loads (make diff).  Not firmware: it is in tools/,
 * which no firmware target compiles.
 *
 * Python describes the structures of core/gl_solver.h a second time (as
 * ctypes classes).  This file lets it check that description against the
 * compiler's: one size per structure and a few offsets.  It is compiled
 * with or without -DGL_SOLVER_DOUBLE like the solver itself.
 */
#include <stddef.h>

#include "gl_solver.h"

#ifdef GL_SOLVER_DOUBLE
#define ABI_NAME gl_solver64_diff_abi
#else
#define ABI_NAME gl_solver_diff_abi
#endif

unsigned long ABI_NAME(unsigned which);

unsigned long ABI_NAME(unsigned which)
{
    switch (which) {
    case 0u: return (unsigned long)sizeof(gl_real_t);
    case 1u: return (unsigned long)sizeof(gl_measurements_t);
    case 2u: return (unsigned long)sizeof(gl_solver_options_t);
    case 3u: return (unsigned long)sizeof(gl_quad_surface_t);
    case 4u: return (unsigned long)sizeof(gl_aim_solution_t);
    case 5u: return (unsigned long)sizeof(gl_range_estimate_t);
    case 6u: return (unsigned long)sizeof(gl_patch_fit_t);
    case 7u: return (unsigned long)sizeof(gl_estimate_t);
    case 8u: return (unsigned long)sizeof(gl_solver_work_t);
    case 9u: return (unsigned long)sizeof(gl_roll_result_t);
    case 10u: return (unsigned long)sizeof(gl_rvec2_t);
    case 11u: return (unsigned long)offsetof(gl_measurements_t, user_distance_m);
    case 12u: return (unsigned long)offsetof(gl_estimate_t, n_steps);
    case 13u: return (unsigned long)offsetof(gl_patch_fit_t, n_starts);
    case 14u: return (unsigned long)offsetof(gl_solver_work_t, mat);
    case 15u: return (unsigned long)offsetof(gl_roll_result_t, n_steps);
    case 16u: return (unsigned long)offsetof(gl_aim_solution_t, n_steps);
    case 17u: return (unsigned long)offsetof(gl_solver_options_t, lm_max_iter);
    default: return 0ul;
    }
}
