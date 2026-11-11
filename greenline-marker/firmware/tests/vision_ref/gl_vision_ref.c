/*
 * gl_vision_ref.c - builds the frozen phase-1 vision code (see
 * gl_vision_ref.h) under the names glp1_*.  The body is NOT edited: it is
 * the phase-1 core/gl_vision.c, included below.
 */
#include "gl_vision_ref.h"

/* The median as phase 1 computed it: a full Shell sort (Ciura gaps). */
float glp1_median_inplace(float *v, size_t n)
{
    if (n == 0u) {
        return 0.0f;
    }
    static const uint16_t gaps[8] = { 701, 301, 132, 57, 23, 10, 4, 1 };
    for (unsigned g = 0; g < 8u; g++) {
        const size_t gap = gaps[g];
        for (size_t i = gap; i < n; i++) {
            float t = v[i];
            size_t j = i;
            while (j >= gap && v[j - gap] > t) {
                v[j] = v[j - gap];
                j -= gap;
            }
            v[j] = t;
        }
    }
    if ((n & 1u) != 0u) {
        return v[n / 2u];
    }
    return 0.5f * (v[n / 2u - 1u] + v[n / 2u]);
}

#define gl_median_inplace glp1_median_inplace
#define gl_vis_strip_stats_rows glp1_vis_strip_stats_rows
#define gl_vis_strip_stats glp1_vis_strip_stats
#define gl_vis_band_analyse glp1_vis_band_analyse
#define gl_vis_stick_refine glp1_vis_stick_refine
#define gl_vis_stick_x_at glp1_vis_stick_x_at
#define gl_vis_stick_segment glp1_vis_stick_segment
#define gl_vis_segment_rows glp1_vis_segment_rows
#define gl_vis_stereo_pair glp1_vis_stereo_pair
#define gl_vis_disp_acc_reset glp1_vis_disp_acc_reset
#define gl_vis_disp_acc_add_lrrl glp1_vis_disp_acc_add_lrrl
#define gl_vis_disp_acc_result glp1_vis_disp_acc_result
#define gl_vis_stick_angles glp1_vis_stick_angles
#define gl_vis_quality glp1_vis_quality

#include "gl_vision_p1_body.inc"
