/*
 * gl_vision.h - flagstick detection and measurement on 8-bit luminance
 * strips.
 *
 * What the cameras are for (docs/research/grazing-vision.md section 2):
 * detect the flagstick, measure its BEARING, its stereo DISPARITY, the
 * elevation of its LOWEST VISIBLE POINT and of its TOP.  Nothing else.
 *
 * Capture plan (driven by the application):
 *   1. a horizon band, 640 x 96 rows around the calibrated horizon row
 *      (gl_cam_base_plane_row()) -> gl_vis_band_analyse(): stick
 *      candidates and turf-horizon samples
 *   2. a stick strip, 96 columns x 480 rows around the best candidate, in
 *      the order L R R L, repeated N times
 *      -> gl_vis_stick_refine() on each strip (sub-pixel line fit, extent)
 *      -> gl_vis_stick_segment() over the lowest 0.3-0.5 m of the stick
 *      -> gl_vis_disp_acc_add_lrrl() / _result(): disparity + uncertainty
 *
 * COORDINATES.  A strip is a window of the sensor: pixel (col, row) of the
 * strip is sensor pixel (x0 + col, y0 + row).  Every result of this module
 * is in SENSOR pixel coordinates (pixel centres at integers, row 0 at the
 * top, rows increasing downward), so results from different strips and
 * the camera model can be combined directly.
 *
 * MEMORY.  No allocation.  The two large work areas are supplied by the
 * caller (static storage in the application):
 *   gl_vis_band_work_t   42240 bytes  (band analysis)
 *   gl_vis_stick_work_t  16644 bytes  (one per strip being refined; keep
 *                        the four of an L R R L group alive until the
 *                        segment fits are done: 66.6 kB)
 * Worst-case stack and the measured cost in instructions are in the README
 * (sections "Memory" and "Run time"); no recursion.
 *
 * WHAT THE RESULTS CLAIM, AND WHAT THEY DO NOT (design review):
 *  - a line found here is a LINE, not yet a flagstick: a trunk, a post or a
 *    leg fits just as well.  The caller (app/gl_read.c) decides, from the
 *    width against the stereo disparity, the height and the position;
 *  - below the local turf horizon the background is turf, whose texture
 *    looks like a line on any single row.  The line fit uses only the rows
 *    above the horizon, and the stick is followed into the turf only as far
 *    as its amplitude there is statistically significant;
 *  - the uncertainty of a disparity has a part that repeats in every strip
 *    of a camera (fixed-pattern noise, background structure behind the
 *    stick): it is estimated per strip and NOT reduced by averaging.
 */
#ifndef GL_VISION_H
#define GL_VISION_H

#include "gl_cam.h"
#include "gl_types.h"

/* ---- strips ---------------------------------------------------------------- */

typedef struct {
    const uint8_t *px;  /**< row-major luminance, px[row * stride + col] */
    uint16_t width;     /**< columns */
    uint16_t height;    /**< rows */
    uint16_t stride;    /**< bytes per row (>= width) */
    uint16_t x0, y0;    /**< sensor coordinates of pixel (0, 0) */
} gl_strip_t;

/* ---- strip statistics (quality inputs) --------------------------------------- */

/** Pixels at or above this grey level count as saturated. */
#define GL_VIS_SAT_LEVEL 250u
/** Sun-in-frame: a saturated blob at least this many pixels wide and tall. */
#define GL_VIS_SUN_MIN_PX 8u

typedef struct {
    float mean;           /**< mean grey level */
    float sat_fraction;   /**< fraction of pixels >= GL_VIS_SAT_LEVEL */
    float noise_sigma;    /**< robust estimate of pixel noise + fine texture, grey rms */
    bool sun;             /**< a compact saturated blob (the sun or a specular glint) is in the strip */
} gl_vis_stats_t;

/** Statistics of the first `rows` rows only (0 = all). */
void gl_vis_strip_stats_rows(const gl_strip_t *s, unsigned rows, float *scratch,
                             gl_vis_stats_t *out);

/** Mean, saturation, noise estimate and sun flag of a strip.  `scratch`
 *  must hold at least max(480, strip width) floats. */
void gl_vis_strip_stats(const gl_strip_t *s, float *scratch, gl_vis_stats_t *out);

/* ---- horizon band analysis ------------------------------------------------------ */

#define GL_VIS_BAND_MAX_W 640u
#define GL_VIS_BAND_BLOCK_ROWS 12u
#define GL_VIS_BAND_MAX_BLOCKS 8u   /* 96 rows */
#define GL_VIS_MAX_CANDIDATES 4u
#define GL_VIS_HORIZON_BINS 32u
#define GL_VIS_BAND_SCALES 4u
#define GL_VIS_BAND_SLANTS 13u      /* -3 .. +3 degrees in 0.5 degree steps */

/** Detection threshold on the matched-line score (in noise sigmas). */
#define GL_VIS_BAND_MIN_SCORE 7.0f
/** Columns sampled to measure the spread of a path response across the band. */
#define GL_VIS_BAND_PATH_SAMPLES 160u

typedef struct {
    float x;          /**< sensor column of the line at ref_row (sub-pixel) */
    float ref_row;    /**< sensor row at which x is given */
    float slant;      /**< columns per row (tan of the lean), |slant| <= tan(3 deg) */
    float score;      /**< matched-line response in units of its noise sigma */
    float width_px;   /**< width of the best-matching line template */
    int8_t polarity;  /**< +1 bright on dark, -1 dark on bright */
    uint8_t rows;     /**< rows from the top of the band over which the line was integrated */
} gl_vis_candidate_t;

typedef struct {
    int16_t block[GL_VIS_BAND_MAX_BLOCKS][GL_VIS_BAND_MAX_W];  /**< 12-row column sums */
    float ridge[GL_VIS_BAND_MAX_BLOCKS][GL_VIS_BAND_MAX_W];    /**< line response, one scale */
    float path[GL_VIS_BAND_MAX_BLOCKS][GL_VIS_BAND_PATH_SAMPLES]; /**< sampled path sums (spread) */
    float score[GL_VIS_BAND_MAX_W];                            /**< best score per column */
    uint16_t edge_energy[GL_VIS_BAND_MAX_W];                   /**< OUTPUT, see below */
    uint8_t best_slant[GL_VIS_BAND_MAX_W];
    uint8_t best_scale[GL_VIS_BAND_MAX_W];
    uint8_t best_blocks[GL_VIS_BAND_MAX_W];
    int8_t best_pol[GL_VIS_BAND_MAX_W];
} gl_vis_band_work_t;

typedef struct {
    gl_vis_candidate_t cand[GL_VIS_MAX_CANDIDATES]; /**< strongest first */
    uint8_t n_cand;
    /** Turf-horizon samples: for each of GL_VIS_HORIZON_BINS equal column
     *  bins, the sensor row of the strongest horizontal edge (sub-row), and
     *  the sensor column of the bin centre.  Bit i of horizon_valid says
     *  whether bin i has a significant edge. */
    float horizon_row[GL_VIS_HORIZON_BINS];
    float horizon_col[GL_VIS_HORIZON_BINS];
    uint32_t horizon_valid;
    float edge_energy_mean; /**< mean of work->edge_energy: scene vertical-edge clutter */
    gl_vis_stats_t stats;
} gl_vis_band_result_t;

/**
 * Analyse a horizon band (width <= 640, height a multiple of 12 up to 96;
 * extra rows are ignored).
 *
 *  - work->edge_energy[col] = sum over rows of |I(col+1) - I(col-1)|: the
 *    per-column vertical-edge energy.
 *  - Matched vertical-line detector: a centre-minus-flanks line filter at
 *    4 widths (1, 3, 7, 13 px) is integrated along rows, top-down, along
 *    straight paths leaning -3..+3 degrees.  The integrated response of
 *    every (width, lean, length) is normalised by ITS OWN SPREAD ACROSS THE
 *    COLUMNS of the band (median / MAD of a sample of columns), never by
 *    less than the white-noise prediction: column-coherent structure
 *    (sensor fixed pattern, a tree line) adds up along a path like a line
 *    does, and the old normalisation by independent blocks then reported
 *    lines in most stick-free bands.  Local maxima above
 *    GL_VIS_BAND_MIN_SCORE become candidates; around a winner only its own
 *    footprint and its opposite-polarity side lobes are suppressed, so a
 *    second line a few pixels away remains a candidate.
 *  - Turf-horizon samples per column bin.
 *
 * Returns GL_OK if at least one candidate was found, GL_ERR_NO_STICK if
 * none (the horizon samples and statistics are still valid),
 * GL_ERR_PARAM for an unusable strip.
 */
gl_status_t gl_vis_band_analyse(const gl_strip_t *band, gl_vis_band_work_t *work,
                                gl_vis_band_result_t *out);

/* ---- stick refinement on the tall strip ----------------------------------------- */

#define GL_VIS_STRIP_MAX_H 480u
#define GL_VIS_STRIP_MAX_W 160u
#define GL_VIS_FLANK_COLS 12u

/** Per-row flags in gl_vis_stick_work_t.flag. */
#define GL_VIS_ROW_MEASURED (1u << 0) /**< a line was found near the prediction */
#define GL_VIS_ROW_INLIER   (1u << 1) /**< used by the final line fit */
#define GL_VIS_ROW_WIDE     (1u << 2) /**< much wider / brighter than the stick: cloth, person */
#define GL_VIS_ROW_NEG      (1u << 3) /**< dark-on-bright on this row */
#define GL_VIS_ROW_PRESENT  (1u << 4) /**< counted as part of the stick's extent */

typedef struct {
    float x[GL_VIS_STRIP_MAX_H];     /**< line centre, STRIP column, sub-pixel */
    float w[GL_VIS_STRIP_MAX_H];     /**< weight = 1 / variance of x (px^-2) */
    float flux[GL_VIS_STRIP_MAX_H];  /**< after refinement: signed line amplitude along the fit, grey */
    float m2[GL_VIS_STRIP_MAX_H];    /**< after refinement: local background level of the row, grey */
    float tmp[GL_VIS_STRIP_MAX_H];   /**< scratch */
    uint8_t peak[GL_VIS_STRIP_MAX_H];/**< after refinement: |left flank - right flank| of the row,
                                          grey (clipped to 255); before: peak contrast */
    uint8_t flag[GL_VIS_STRIP_MAX_H];
    /** Flank pixels of each measured row minus the row's linear background,
     *  in half grey levels: 6 left (nearest the line last) and 6 right
     *  (nearest first).  What repeats from row to row in them is background
     *  structure / fixed pattern: the static part of the uncertainty. */
    int8_t flank[GL_VIS_STRIP_MAX_H][GL_VIS_FLANK_COLS];
    uint16_t rowsum[GL_VIS_STRIP_MAX_W]; /**< scratch: one (binned) row */
    uint8_t flank_off;                   /**< columns from the line to the nearest flank pixel */
} gl_vis_stick_work_t;

/** What is known about the stick before refinement (from the band). */
typedef struct {
    float x;          /**< sensor column at `row` */
    float row;        /**< sensor row */
    float slant;      /**< columns per row */
    float width_px;   /**< expected line width (0 = unknown: 1.5 px assumed) */
    float search_px;  /**< half-width of the search around the prediction (0 = 6 px;
                           clamped to 0.5 .. strip width) */
    /** Where the turf horizon is expected beside the stick (sensor row):
     *  from the band's horizon samples or the calibrated base-plane row.
     *  The refinement looks for the actual turf edge within
     *  +-horizon_tol_rows of it (0 = 40) and, failing that, uses the row
     *  given.  have_horizon = false: no knowledge; the whole strip is
     *  treated as clean background (unit tests of the line fit only). */
    bool have_horizon;
    float horizon_row;
    float horizon_tol_rows;
    /** Rows averaged along the predicted line before a row is measured:
     *  1 (0 is taken as 1), 4 or 16.  Binning recovers sticks whose single
     *  rows are below the noise; the caller retries with it when the
     *  unbinned refinement finds nothing. */
    uint8_t bin_rows;
} gl_vis_prior_t;

typedef enum {
    GL_VIS_BASE_UNKNOWN = 0,    /**< no usable turf horizon next to the stick */
    GL_VIS_BASE_VISIBLE = 1,    /**< the stick continues BELOW the local turf horizon */
    GL_VIS_BASE_AT_HORIZON = 2  /**< the stick ends AT the turf horizon: the base may be hidden */
} gl_vis_base_t;

/** Rows by which the stick must extend below the turf horizon to be
 *  classified GL_VIS_BASE_VISIBLE (single-strip noise of the difference is
 *  0.1-0.4 row; within +-this margin the result is GL_VIS_BASE_AT_HORIZON). */
#define GL_VIS_BASE_MARGIN_ROWS 1.5f

typedef struct {
    /* fitted axis: x(row) = x_ref + slope * (row - row_ref), sensor coordinates */
    float x_ref, row_ref, slope;
    float sigma_x_ref;     /**< one-sigma of x_ref, px (includes the fit's chi-square scale) */
    float sigma_slope;     /**< one-sigma of slope, px per row */
    float resid_rms_px;    /**< weighted rms residual of the inlier rows */
    float sigma_scale;     /**< sqrt(reduced chi-square) of the fit, >= 1: factor by which the
                                per-row formal errors were found too optimistic */
    /* extent */
    float top_row;         /**< sensor row of the top end (valid if top_in_frame) */
    bool top_in_frame;
    bool top_in_clutter;   /**< the rows just beyond the top end are not clean background (a
                                flag hanging over the stick, foliage): the "top" may be where
                                the clutter begins, not the tip.  Do not range with it. */
    float bottom_row;      /**< sensor row of the lowest visible point (sub-row) */
    float bottom_sigma_rows; /**< one-sigma of bottom_row from the way it was found (model term;
                                  the scatter over strips is added by the caller) */
    bool below_horizon_significant; /**< the stick was followed into the turf below the horizon
                                         with statistical significance (the base is visible) */
    float turf_snr;        /**< significance (sigmas) of the stick's amplitude below the horizon */
    float horizon_row;     /**< local turf horizon beside the stick (valid if horizon_found) */
    bool horizon_found;    /**< the turf edge itself was located in this strip */
    uint8_t base;          /**< gl_vis_base_t */
    /* quality */
    float contrast;        /**< median peak contrast of the inlier rows, grey levels */
    float width_px;        /**< median rms half-width (sigma) of the line profile, px */
    float noise_sigma;     /**< pixel noise estimate (rows above the horizon), grey rms */
    float line_snr;        /**< significance of the whole line: mean forced amplitude over the
                                rows between its ends x sqrt(rows) / amplitude noise */
    float chi2_red;        /**< reduced chi-square of the row positions about the fit */
    uint8_t bin_rows;      /**< rows averaged per measurement (1, 4 or 16) */
    float rows_used_frac;  /**< inlier rows / rows between top and bottom */
    uint16_t rows_used;
    uint16_t rows_measured;
    int8_t polarity;       /**< dominant: +1 bright on dark, -1 dark on bright */
    uint16_t x0, y0;       /**< origin of the strip this came from */
    uint16_t strip_rows;   /**< height of that strip (rows of the work area that are valid) */
} gl_vis_stick_t;

/**
 * Sub-pixel measurement of a near-vertical line on a tall strip.
 *
 * Per row: local linear background from flanks either side, polarity from
 * the sign of the residual (bright-on-dark and dark-on-bright both work,
 * also mixed along the stick), iterated Gaussian-weighted centroid (window
 * never narrower than 1.2 px rms, which keeps the sub-pixel phase bias of
 * undersampled lines near 0.01 px), weight from the local contrast-to-
 * noise.  Rows whose two flanks differ like the edge of a wide object, and
 * rows much wider or brighter than the median (flag cloth, people), are set
 * aside.  A straight line is fitted by iteratively reweighted least squares
 * (Tukey biweight, cut-off annealed from the search radius down to the
 * data's own scatter; no random sampling), the rows are re-measured along
 * the fit and fitted again.  The fit is ACCEPTED as a line only if the
 * inlier rows scatter no more than their own predicted errors allow (and
 * never more than 0.45 px rms where single rows are well measured), at
 * least half of the candidate rows are inliers, and the LINE AS A WHOLE is
 * significant: the amplitude measured along the fit, summed over the rows
 * between its ends, is at least GL_VIS_MIN_LINE_SNR sigmas.
 *
 * TURF.  With prior->have_horizon the local turf edge is located first.
 * Only rows above it are measured and fitted (the rows below show the
 * stick against textured turf).  The top end is a change point of the line
 * amplitude along the fit.  The lower end is found in two steps: above the
 * horizon like the top; below it the stick is followed only if its
 * amplitude there - whatever its sign and size - is significant against
 * the turf's own fluctuations, which are measured on two parallel lines
 * beside the stick (GL_VIS_TURF_MIN_SNR).  If it is not, the lowest visible
 * point is reported AT the horizon (GL_VIS_BASE_AT_HORIZON) with a wider
 * uncertainty: on a flat green the base lies only (lens height / distance)
 * below the turf horizon - 0.7 px at 5 m - and cannot be resolved.
 *
 * Accuracy and limits measured on synthetic strips: tests/test_vision.c,
 * tests/test_read.c and the README.  About the lowest visible point:
 *  - GL_VIS_BASE_VISIBLE is reported only when the stick is followed, with
 *    significance, more than GL_VIS_BASE_MARGIN_ROWS below the turf edge (a
 *    rise behind the hole); GL_VIS_BASE_AT_HORIZON covers both "base just
 *    visible on a flat green" and "base hidden behind a crown" - telling
 *    those apart needs information this module does not have;
 *  - a stick that loses its contrast above the horizon (a stripe the colour
 *    of the background) ends there: GL_VIS_BASE_UNKNOWN.
 *
 * Returns GL_OK, or GL_ERR_NO_STICK if no line passes the acceptance
 * tests (out->rows_used tells how many rows supported the attempt),
 * GL_ERR_PARAM for an unusable strip or a non-finite prior.  On
 * GL_ERR_NO_STICK `out` must not be used as a measurement.
 */

/** Smallest significance (sigmas) of the line as a whole. */
#define GL_VIS_MIN_LINE_SNR 8.0f
/** Smallest significance of the stick's amplitude below the turf horizon
 *  for it to be followed there. */
#define GL_VIS_TURF_MIN_SNR 4.5f
gl_status_t gl_vis_stick_refine(const gl_strip_t *strip, const gl_vis_prior_t *prior,
                                gl_vis_stick_work_t *work, gl_vis_stick_t *out);

/** Axis column (sensor) at a sensor row. */
float gl_vis_stick_x_at(const gl_vis_stick_t *s, float sensor_row);

/* ---- segment fit and stereo -------------------------------------------------------- */

typedef struct {
    float x_mid;     /**< sensor column of the axis at row_mid */
    float row_mid;   /**< weighted mean sensor row of the rows used */
    float slope;     /**< columns per row within the segment */
    float sigma_x;   /**< one-sigma of x_mid from the noise of this strip, px */
    float sigma_static_px; /**< one-sigma of the part of the error that is the SAME in every
                                strip of this camera: background structure and fixed pattern
                                under the line (estimated from the flanks) and the sub-pixel
                                phase bias of a narrow vertical line.  Not reduced by repeats. */
    float static_var_px2;  /**< the unbiased estimate behind sigma_static_px (px^2).  It is
                                noisy and may be NEGATIVE on a clean strip; the disparity
                                accumulator averages it over the strips before clipping. */
    uint16_t rows;   /**< inlier rows used */
} gl_vis_segment_t;

/** Minimum inlier rows for a segment fit. */
#define GL_VIS_SEGMENT_MIN_ROWS 8u

/**
 * Weighted straight-line fit restricted to the inlier rows between two
 * sensor rows (inclusive), using the per-row measurements left in `work`
 * by gl_vis_stick_refine() for `stick`.  The slope is taken from the whole
 * stick when the segment has fewer than 24 rows.  GL_ERR_NO_STICK if fewer
 * than GL_VIS_SEGMENT_MIN_ROWS inlier rows fall in the range.
 */
gl_status_t gl_vis_stick_segment(const gl_vis_stick_work_t *work, const gl_vis_stick_t *stick,
                                 float sensor_row_lo, float sensor_row_hi,
                                 gl_vis_segment_t *out);

/**
 * Rows of the stick, counted up from its lowest visible point, that span
 * `length_m` of stick at the range implied by `disparity_px`:
 * rows = f L / Z with Z = f B / d, i.e. L d / B (clamped to 12 .. 400 rows;
 * 40 rows if the disparity is not positive).
 */
unsigned gl_vis_segment_rows(float disparity_px, float baseline_m, float length_m);

typedef struct {
    float disparity_px;   /**< rectified disparity scaled to focal length f_ref */
    float sigma_px;       /**< one-sigma uncertainty: sqrt(sigma_noise^2 + sigma_static^2).  The
                               caller adds the stereo calibration term. */
    float sigma_noise_px; /**< frame-to-frame part: shrinks with the number of groups */
    float sigma_static_px;/**< part common to all strips of a camera: does not shrink */
    float jitter_px;      /**< rms scatter between L R R L groups (0 if fewer than 2) */
    float sway_px;        /**< mean stick motion per frame interval seen in the left camera */
    uint16_t groups;      /**< L R R L groups combined */
} gl_vis_disparity_t;

/**
 * Disparity of one left / right pair of segment fits: the difference of
 * the two axis positions at MATCHING rows.  With camera models the two
 * lines are first mapped to rectified coordinates (lens distortion and the
 * cameras' relative rotation removed) and compared at the same rectified
 * row; with cam_l == cam_r == NULL the raw columns are compared at the
 * same sensor row.  f_ref scales the rectified difference back to pixels
 * (use GL_CFG_CAM_F_PX).  Positive for a finite distance.
 */
gl_status_t gl_vis_stereo_pair(const gl_vis_segment_t *left, const gl_vis_segment_t *right,
                               const gl_cam_model_t *cam_l, const gl_cam_model_t *cam_r,
                               float f_ref, float *disparity_px, float *sigma_px);

typedef struct {
    float sum_w, sum_wd, sum_d, sum_d2, sum_sway;
    float sum_static2_l, sum_static2_r; /**< sums of the per-strip static variances */
    uint16_t n;
} gl_vis_disp_acc_t;

/** Empty the accumulator before the first group of a read. */
void gl_vis_disp_acc_reset(gl_vis_disp_acc_t *a);

/**
 * Add one L R R L group: seg[0] = first left, seg[1] = first right, seg[2] =
 * second right, seg[3] = second left, captured at equal time intervals.
 * The group disparity is mean(L) - mean(R) at matching rows, which cancels
 * any LINEAR motion of the stick (sway) because both means refer to the
 * same instant.  GL_ERR_PARAM if a segment is unusable.
 */
gl_status_t gl_vis_disp_acc_add_lrrl(gl_vis_disp_acc_t *a, const gl_vis_segment_t seg[4],
                                     const gl_cam_model_t *cam_l, const gl_cam_model_t *cam_r,
                                     float f_ref);

/**
 * Combined disparity: inverse-variance weighted mean over the groups.
 * sigma_noise is the larger of the formal one and (with 3 or more groups)
 * the standard error of the mean from the observed scatter; sigma_static
 * is the root of the two cameras' mean static variances and is NOT divided
 * by the number of groups (it is the same error in every one of them).
 * GL_ERR_NO_STICK if no group was added.
 */
gl_status_t gl_vis_disp_acc_result(const gl_vis_disp_acc_t *a, gl_vis_disparity_t *out);

/* ---- angles for the estimator ------------------------------------------------------- */

typedef struct {
    float bearing_rad;      /**< of the lowest visible point, relative to gravity-levelled forward */
    float base_elev_rad;    /**< elevation of the lowest visible point */
    float top_elev_rad;     /**< elevation of the top (valid if top_valid) */
    bool top_valid;         /**< the top is in the frame AND not in clutter */
    float tan_height;       /**< tan(top) - tan(base): angular height for monocular ranging */
    uint8_t base;           /**< gl_vis_base_t */
} gl_vis_angles_t;

/** Convert a refined stick to bearing / elevations relative to gravity with
 *  the camera model and the tilt estimate (`up_marker`: unit up vector in
 *  the marker frame). */
void gl_vis_stick_angles(const gl_vis_stick_t *s, const gl_cam_model_t *cam, gl_vec3_t up_marker,
                         gl_vis_angles_t *out);

/* ---- quality ------------------------------------------------------------------------- */

typedef struct {
    float line_contrast;    /**< smaller of the two cameras' median line contrast, grey */
    float contrast_snr;     /**< line_contrast / noise sigma */
    float rows_used_frac;   /**< smaller of the two cameras' fraction of rows used */
    float sharpness_match;  /**< 0..1: min over (width ratio, contrast ratio) of left vs right;
                                 well below 1 = one window is dirty or wet */
    float sat_fraction;     /**< larger of the two strips' saturated fraction */
    bool sun;               /**< sun (saturated blob) in either strip */
} gl_vis_quality_t;

/** Combine the two cameras' results into the quality metrics.  `right` may
 *  be NULL (the right camera found no line: sharpness_match is then 0, the
 *  rest describes the left camera alone). */
void gl_vis_quality(const gl_vis_stick_t *left, const gl_vis_stick_t *right,
                    const gl_vis_stats_t *stats_left, const gl_vis_stats_t *stats_right,
                    gl_vis_quality_t *out);

#endif /* GL_VISION_H */
