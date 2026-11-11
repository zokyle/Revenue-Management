/*
 * gl_vision_ref.h - the PHASE-1 vision code, frozen, as a test oracle.
 *
 * Phase 2 reduced the run time of core/gl_vision.c (medians by selection,
 * sliding sums, pixels fetched only where they are read, the second pass of
 * the refinement taking over unchanged centroids, ...) under the rule that
 * WHAT IS MEASURED DOES NOT CHANGE.  To make that checkable, the vision code
 * as it was before those changes is kept here, byte for byte
 * (gl_vision_p1_body.inc = core/gl_vision.c of phase 1), compiled with every
 * external symbol renamed gl_vis_* -> glp1_vis_* and with the sorting median
 * it used (glp1_median_inplace).  tests/test_vision_equiv.c runs both
 * implementations on the same strips and demands identical results.
 *
 * Host tests only.  Never part of the firmware, never cross-compiled.
 */
#ifndef GL_VISION_REF_H
#define GL_VISION_REF_H

#include "gl_vision.h"

float glp1_median_inplace(float *v, size_t n);

void glp1_vis_strip_stats_rows(const gl_strip_t *s, unsigned rows, float *scratch,
                               gl_vis_stats_t *out);
void glp1_vis_strip_stats(const gl_strip_t *s, float *scratch, gl_vis_stats_t *out);
gl_status_t glp1_vis_band_analyse(const gl_strip_t *band, gl_vis_band_work_t *work,
                                  gl_vis_band_result_t *out);
gl_status_t glp1_vis_stick_refine(const gl_strip_t *strip, const gl_vis_prior_t *prior,
                                  gl_vis_stick_work_t *work, gl_vis_stick_t *out);
float glp1_vis_stick_x_at(const gl_vis_stick_t *s, float sensor_row);
gl_status_t glp1_vis_stick_segment(const gl_vis_stick_work_t *work, const gl_vis_stick_t *stick,
                                   float sensor_row_lo, float sensor_row_hi,
                                   gl_vis_segment_t *out);
unsigned glp1_vis_segment_rows(float disparity_px, float baseline_m, float length_m);
gl_status_t glp1_vis_stereo_pair(const gl_vis_segment_t *left, const gl_vis_segment_t *right,
                                 const gl_cam_model_t *cam_l, const gl_cam_model_t *cam_r,
                                 float f_ref, float *disparity_px, float *sigma_px);
void glp1_vis_disp_acc_reset(gl_vis_disp_acc_t *a);
gl_status_t glp1_vis_disp_acc_add_lrrl(gl_vis_disp_acc_t *a, const gl_vis_segment_t seg[4],
                                       const gl_cam_model_t *cam_l, const gl_cam_model_t *cam_r,
                                       float f_ref);
gl_status_t glp1_vis_disp_acc_result(const gl_vis_disp_acc_t *a, gl_vis_disparity_t *out);
void glp1_vis_stick_angles(const gl_vis_stick_t *s, const gl_cam_model_t *cam, gl_vec3_t up_marker,
                           gl_vis_angles_t *out);
void glp1_vis_quality(const gl_vis_stick_t *left, const gl_vis_stick_t *right,
                      const gl_vis_stats_t *stats_left, const gl_vis_stats_t *stats_right,
                      gl_vis_quality_t *out);

#endif /* GL_VISION_REF_H */
