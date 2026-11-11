/*
 * gl_range.h - distance to the flagstick.
 *
 * Two optical estimates and one manual one:
 *   stereo     range = f * B / disparity          (good to ~5 m)
 *   monocular  range = H / (tan(top) - tan(base)) (needs the visible stick
 *              height H; good once H has been learned for the course)
 *   manual     dialled in by the golfer (flag-out fallback); overrides.
 *
 * Fusion is inverse-variance weighted in INVERSE RANGE (rho = 1 / Z),
 * because both optical measurements are linear in rho with roughly
 * Gaussian errors: disparity = f B rho and angular height = H rho.
 *
 * "Range" everywhere in this module is the HORIZONTAL DISTANCE from the
 * stereo head to the stick.  Stereo measures depth along the forward axis,
 * which is shorter by cos(bearing) for a stick off to one side (6 % at 20
 * degrees), so the caller supplies cos_bearing.
 *
 * The visible stick height H is learned per course by a scalar Kalman
 * filter: whenever stereo and angular height are both available with the
 * stereo range between 4 and 7 m (and the base and top visible), the
 * product (angular height * stereo range) updates H.  Prior: 2.13 m total
 * minus 0.17 m in the cup = 1.96 m, 7 % one-sigma.
 *
 * RAM: all structures are a few tens of bytes.  Stack: under 100 bytes.
 */
#ifndef GL_RANGE_H
#define GL_RANGE_H

#include "gl_types.h"

/* ---- learned stick height ---------------------------------------------------- */

typedef struct {
    float height_m;       /**< visible stick height above the green */
    float sigma_m;        /**< one-sigma uncertainty */
    uint16_t updates;     /**< accepted learning updates */
    uint16_t rejected;    /**< updates refused by the 3-sigma gate */
} gl_stick_height_t;

#define GL_STICK_HEIGHT_BLOB_LEN 13u

/** Range window in which stereo is trusted to teach the stick height. */
#define GL_RANGE_LEARN_MIN_M 4.0f
#define GL_RANGE_LEARN_MAX_M 7.0f
/** The learned sigma never drops below this fraction of the height (cups
 *  are cut to slightly different depths, sticks lean). */
#define GL_STICK_HEIGHT_SIGMA_FLOOR_REL 0.01f

/** Reset to the prior (new course). */
void gl_stick_height_reset(gl_stick_height_t *h);

/** Serialise to GL_STICK_HEIGHT_BLOB_LEN bytes for the blob store. */
void gl_stick_height_encode(const gl_stick_height_t *h, uint8_t out[GL_STICK_HEIGHT_BLOB_LEN]);
/** GL_ERR_PARAM / GL_ERR_UNSUPPORTED / GL_ERR_RANGE; `h` only modified on GL_OK. */
gl_status_t gl_stick_height_decode(const uint8_t *blob, size_t len, gl_stick_height_t *h);

/* ---- fusion -------------------------------------------------------------------- */

#define GL_RANGE_SRC_STEREO (1u << 0)
#define GL_RANGE_SRC_MONO   (1u << 1)
#define GL_RANGE_SRC_MANUAL (1u << 2)

typedef struct {
    float f_px;               /**< focal length used for the disparity */
    float baseline_m;
    bool have_stereo;
    float disparity_px;       /**< rectified disparity: f * B / DEPTH along the forward axis */
    float disparity_sigma_px;
    float cos_bearing;        /**< cosine of the stick's bearing; converts stereo depth to the
                                   horizontal DISTANCE that the angular height measures
                                   (distance = depth / cos).  0 = not given, treated as 1. */
    bool have_height;         /**< top AND base of the stick were measured */
    bool base_visible;        /**< false: the base is hidden behind a crown */
    float tan_top;            /**< tangent of the elevation of the stick top */
    float tan_base;           /**< tangent of the elevation of the lowest visible point */
    float elev_sigma_rad;     /**< one-sigma of EACH of the two elevations */
    float manual_m;           /**< > 0: manual distance, overrides the optics */
} gl_range_input_t;

typedef struct {
    float range_m;
    float sigma_m;
    float stereo_m, stereo_sigma_m;  /**< 0 if not available */
    float mono_m, mono_sigma_m;      /**< 0 if not available */
    float chi2;                      /**< stereo-vs-mono disagreement (1 dof); 0 if < 2 sources */
    uint8_t sources;                 /**< GL_RANGE_SRC_* that went into range_m */
    bool consistent;                 /**< chi2 <= 9 */
} gl_range_result_t;

/** Relative uncertainty assigned to a manually entered distance. */
#define GL_RANGE_MANUAL_REL_SIGMA 0.10f
/** Ranges are clamped to this interval. */
#define GL_RANGE_MIN_M 0.3f
#define GL_RANGE_MAX_M 60.0f

/**
 * Fuse the available estimates.  The monocular estimate is used only when
 * the base of the stick is visible.  When stereo and mono disagree by more
 * than 3 sigma the fused sigma is inflated by sqrt(chi2 / 9) and
 * `consistent` is false.  GL_ERR_NOT_FOUND if no source is usable.
 */
gl_status_t gl_range_fuse(const gl_range_input_t *in, const gl_stick_height_t *h,
                          gl_range_result_t *out);

/**
 * Learn the stick height from this read if the conditions hold (stereo and
 * height both present, base visible, stereo range within the learning
 * window, no manual override).  Returns true if `h` was updated.
 */
bool gl_stick_height_learn(gl_stick_height_t *h, const gl_range_input_t *in);

/* ---- geometry: from the camera to the ball -------------------------------------- */

typedef struct {
    float distance_m;   /**< ball centre to flagstick */
    float bearing_rad;  /**< direction ball -> flagstick, CCW from marker forward */
} gl_ball_target_t;

/**
 * The cameras measure range and bearing from the stereo head (on the
 * marker's forward axis at GL_CFG_CAM_LEFT_Y_MM); the putt starts at the
 * ball centre, GL_CFG_BALL_CENTRE_Y_MM ahead of the marker centre.  Convert.
 * `bearing_cam_rad` must be the bearing seen from the CENTRE of the stereo
 * head; for a bearing measured by one camera use gl_range_from_ball_at().
 */
gl_ball_target_t gl_range_from_ball(float range_cam_m, float bearing_cam_rad);

/**
 * The same for a bearing measured from a point (view_x_m, view_y_m) of the
 * marker frame, e.g. the left camera at (-10.0 mm, 15.6 mm): at 3 m the
 * 10.0 mm offset is 3.35 mrad of bearing, more than the camera's own error.
 */
gl_ball_target_t gl_range_from_ball_at(float range_m, float bearing_rad, float view_x_m,
                                       float view_y_m);

#endif /* GL_RANGE_H */
