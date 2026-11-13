/*
 * gl_read.h - the camera part of a read: camera rail on, one horizon band
 * from the left camera, flagstick strips in the order L R R L repeated N
 * times, vision on every strip, camera rail off, and the combined result.
 *
 * It is a STEP machine for the cooperative main loop: gl_read_start()
 * powers the cameras and arms the first capture, gl_read_step() is called
 * whenever the DCMI reports (or periodically) and never waits for a frame.
 * A whole L R R L group is captured into four strip buffers before any of
 * it is analysed, so that the spacing of the four exposures is set by the
 * sensors and never by how long the vision takes; the analysis then runs
 * one strip per step (gl_read_has_work()), the main loop in between.
 *
 * THE CAMERA RAIL IS OFF whenever gl_read_step() returns anything other
 * than GL_ERR_BUSY, after gl_read_abort(), and after a failed
 * gl_read_start().  The rail is switched off as soon as the last strip has
 * been captured, before the last group is analysed.
 *
 * WHICH LINE.  The band analysis offers up to four lines.  One line: it is
 * followed for N groups.  Several: each gets ONE group of its own first and
 * is judged (see verdict_() in gl_read.c): no line in the strips / a line
 * in the left camera only / measured in both but not a flagstick (width
 * against disparity, height against disparity, height against width,
 * structure in the background) / a flagstick.  The best flagstick - the
 * stronger one nearer the middle of the picture - is then read for N
 * groups, and result.ambiguous says if another line passed too, or if a
 * stronger line right beside the one taken could not be measured.  Each
 * extra candidate costs one group: about 0.17 s of camera time plus its
 * analysis.  If the first group of the line being followed shows nothing
 * in the left camera the read ends there (rail off after 5 captures).
 *
 * WHAT COMES OUT (result.tier): the stereo read; or the left camera alone
 * (bearing, elevations, the top for a monocular range) when the right
 * camera's strips gave nothing; or a bearing only; or nothing, with the
 * reason in result.why.  result.disp.sigma_px is the whole uncertainty of
 * the disparity: frame noise (shrinks with N), the static part estimated
 * from the background beside the line (does not), and the stereo
 * calibration (GL_PROV_STEREO_CAL_SIGMA_PX, the same in every read).
 *
 * TIMING OF L R R L.  The two sensors free-run and are not synchronised, so
 * the four strips of a group are not equally spaced in time (measured in
 * the simulator: 42 / 33 / 58 ms with a 9 ms phase offset).  The mean time
 * of the two L strips then differs from that of the two R strips by up to
 * about +-14 ms, and a swaying stick would leave a disparity error of
 * (sway rate x that difference).  The frame-end time of every strip is
 * latched by the HAL in the DCMI interrupt and the two left positions are
 * moved, along the left camera's own measured sway rate, to the mean time
 * of the two right strips before the group is handed to
 * gl_vis_disp_acc_add_lrrl().  Linear sway then cancels whatever the
 * spacing.
 *
 * RAM and stack: README, section "Memory" (sizeof(gl_read_t) is dominated
 * by the four strip buffers, 184320 bytes, the band work area and the four
 * stick work areas).
 */
#ifndef GL_READ_H
#define GL_READ_H

#include "gl_app_cfg.h"
#include "gl_cam.h"
#include "gl_types.h"
#include "gl_vision.h"
#include "ov7692.h"

#define GL_READ_STRIP_BYTES (GL_APP_STRIP_W * GL_APP_STRIP_H)
#define GL_READ_BAND_BYTES (GL_APP_BAND_W * GL_APP_BAND_H)
#define GL_READ_IMG_BYTES (4u * GL_READ_STRIP_BYTES) /* one L R R L group; >= GL_READ_BAND_BYTES */

/** How much of a read came out.  Each tier includes the ones below it. */
typedef enum {
    GL_READ_TIER_NONE = 0,    /**< nothing usable */
    GL_READ_TIER_BEARING = 1, /**< a strong line in the horizon band that the strips could not
                                   confirm for lack of signal: angles.bearing_rad only */
    GL_READ_TIER_LEFT = 2,    /**< the left camera measured the stick: bearing, elevations, top
                                   (monocular range inputs).  NO disparity: the line could not be
                                   checked against one, so this is weaker evidence of a flagstick */
    GL_READ_TIER_STEREO = 3   /**< as LEFT plus a disparity whose size fits the line's width */
} gl_read_tier_t;

/** Why the read is not GL_READ_TIER_STEREO. */
typedef enum {
    GL_READ_WHY_OK = 0,
    GL_READ_WHY_NO_CANDIDATE, /**< no line in the horizon band */
    GL_READ_WHY_NO_LINE,      /**< the left camera's strips do not confirm the band's line */
    GL_READ_WHY_RIGHT_FAILED, /**< left measured, right found no line (dirty window, glare) */
    GL_READ_WHY_NOT_A_STICK,  /**< measured in both, but width and disparity do not fit a
                                   12.7-19 mm stick within 40 m (a trunk, a post, a far mast) */
    GL_READ_WHY_FEW_GROUPS    /**< fewer than GL_APP_MIN_GROUPS groups gave a disparity */
} gl_read_why_t;

/** Result of the camera part of a read. */
typedef struct {
    bool stick_found;             /**< tier == GL_READ_TIER_STEREO: `disp` is valid */
    uint8_t tier;                 /**< gl_read_tier_t */
    uint8_t why;                  /**< gl_read_why_t */
    bool ambiguous;               /**< another line in the band also passed as a flagstick; the
                                       one nearer the image centre / stronger was taken */
    gl_vis_disparity_t disp;      /**< valid if stick_found; sigma_px INCLUDES cal_sigma_px */
    float cal_sigma_px;           /**< stereo calibration term added to disp.sigma_px */
    gl_vis_angles_t angles;       /**< bearing / elevations from the LEFT camera, rows averaged
                                       over the left strips of the read (tier >= LEFT; tier
                                       BEARING: bearing_rad only) */
    float bottom_sigma_rows;      /**< one-sigma of the lowest visible point: the way it was
                                       found plus its scatter over the strips */
    gl_vis_quality_t quality;     /**< tier >= LEFT: of the stick; below: sun / saturation of
                                       the horizon band */
    gl_vis_stick_t stick_left;    /**< averaged left-camera stick the angles came from */
    uint8_t groups_ok;            /**< L R R L groups that entered the disparity */
    uint8_t groups_tried;
    uint8_t strips_captured;
    uint8_t n_candidates;         /**< band candidates (after the shoulders of strong lines
                                       have been dropped) */
    uint8_t n_shoulders;          /**< band "lines" dropped as the shoulder of a much stronger
                                       line inside their own template width */
    uint8_t n_probed;             /**< candidates examined with an L R R L group of their own */
    float cand_score;             /**< score of the candidate followed */
    float band_noise;             /**< pixel noise of the band, grey rms */
    /** Turf-horizon samples of the band as angles relative to gravity
     *  (bearing CCW from forward, elevation up), left camera. */
    uint8_t n_horizon;
    float horizon_az_rad[GL_VIS_HORIZON_BINS];
    float horizon_elev_rad[GL_VIS_HORIZON_BINS];
    uint32_t rail_on_ms;          /**< how long the camera rail was on */
} gl_read_result_t;

/** Called for every captured strip after its capture completed (raw-strip
 *  logging, factory stream).  kind 0 = horizon band, 1 = stick strip;
 *  frame_index = position in the L R R L ... sequence. */
typedef void (*gl_read_strip_fn_t)(void *ctx, const gl_strip_t *strip, gl_cam_id_t cam,
                                   uint8_t kind, uint8_t frame_index);

typedef enum {
    GL_READ_IDLE = 0,
    GL_READ_BAND,    /**< waiting for the horizon band */
    GL_READ_STRIPS,  /**< waiting for stick strip `k` of the group being captured */
    GL_READ_ANALYSE  /**< the group is in memory: one strip is analysed per step */
} gl_read_phase_t;

typedef struct {
    /* ---- configuration ---- */
    gl_ov7692_t *cam;
    gl_cam_model_t model[GL_CAM_COUNT];
    gl_read_strip_fn_t strip_fn;
    void *strip_ctx;
    bool time_correction;         /**< apply the L R R L timing correction (default true; the
                                       switch exists so that tests can show what it is worth) */
    /* ---- sequence state ---- */
    uint8_t phase;                /**< gl_read_phase_t */
    uint8_t repeats;              /**< N */
    uint16_t k;                   /**< stick strip being captured, 0 .. 4 N - 1 */
    uint8_t an;                   /**< GL_READ_ANALYSE: next strip of the group to analyse, 0..4 */
    uint32_t progress;            /**< counts every completed capture and analysis step: the
                                       caller's evidence that the read is alive */
    gl_strip_t cur;               /**< descriptor of the capture in progress */
    gl_strip_t grp[4];            /**< descriptors of the four strips of the group in memory */
    gl_vec3_t up;                 /**< unit up vector, marker frame (from the tilt read) */
    uint32_t t_rail_on_ms;
    gl_vis_candidate_t cand;
    uint16_t win_x0[GL_CAM_COUNT];
    /* ---- current L R R L group ---- */
    gl_vis_stick_t stick[4];
    bool stick_ok[4];
    uint32_t t_done_us[4];        /**< frame-end time of each strip (gl_hal_dcmi_done_us) */
    uint32_t t_band_us;           /**< frame-end time of the horizon band */
    /* ---- candidates ---- */
    uint8_t ci;                   /**< band candidate being followed */
    bool probing;                 /**< several candidates: one group each, then choose */
    uint8_t verdict[GL_VIS_MAX_CANDIDATES];
    float rank[GL_VIS_MAX_CANDIDATES];
    float cand_x[GL_VIS_MAX_CANDIDATES]; /**< where the strips found each candidate's line */
    /* ---- accumulation over the read (per candidate) ---- */
    gl_vis_disp_acc_t acc;
    float d_est_px;               /**< disparity estimate that sizes the segment */
    bool have_d_est;
    gl_vis_stick_t last[GL_CAM_COUNT]; /**< newest good stick per camera (next prior) */
    bool have_last[GL_CAM_COUNT];
    gl_vis_stick_t first[GL_CAM_COUNT];
    gl_vis_stats_t stats[GL_CAM_COUNT];
    bool have_first[GL_CAM_COUNT];
    uint8_t bin[GL_CAM_COUNT];    /**< row binning that worked last for each camera */
    float sum_bottom[3], sum_bottom2[3], sum_bsig2[3]; /**< per gl_vis_base_t class */
    uint16_t n_base[3];
    float sum_xref, sum_slope, sum_top, sum_horizon;
    uint16_t n_left, n_right, n_top, n_top_clutter, n_horizon_rows;
    gl_read_result_t result;
    /* ---- large work areas ---- */
    gl_vis_band_result_t band;
    gl_vis_band_work_t band_work;
    gl_vis_stick_work_t stick_work[4];
    uint8_t img[GL_READ_IMG_BYTES]; /**< band, or the four strip buffers of one group */
} gl_read_t;

/** Bind to the camera driver and take nominal camera models. */
void gl_read_init(gl_read_t *r, gl_ov7692_t *cam);

/** Use these calibration records (factory intrinsics / extrinsics). */
void gl_read_set_cal(gl_read_t *r, const gl_cal_cam_t *left, const gl_cal_cam_t *right);

/** Optional per-strip hook (NULL = none). */
void gl_read_set_strip_hook(gl_read_t *r, gl_read_strip_fn_t fn, void *ctx);

/**
 * Power the cameras up and arm the horizon-band capture.  `up_marker` is
 * the unit up vector from the tilt read just done; `repeats` the number of
 * L R R L groups (1..32).  Blocks for the camera power-up sequence (about
 * 25 ms of delays and register traffic) plus the sensor's settle frames.
 * On any error the rail is off again.
 */
gl_status_t gl_read_start(gl_read_t *r, gl_vec3_t up_marker, unsigned repeats);

/**
 * Advance.  GL_ERR_BUSY: still capturing (call again on GL_IRQ_DCMI_DONE or
 * after a few ms).  GL_OK: finished, r->result.stick_found is true.
 * GL_ERR_NO_STICK: finished, no flagstick (r->result holds the horizon
 * samples and the band statistics).  Anything else: camera / bus failure.
 */
gl_status_t gl_read_step(gl_read_t *r);

/** Stop at once: capture aborted, camera rail off.  Always safe. */
void gl_read_abort(gl_read_t *r);

/** True while a read is in progress (until gl_read_step() has returned
 *  something other than GL_ERR_BUSY). */
bool gl_read_busy(const gl_read_t *r);

/** True if the next gl_read_step() has computation to do rather than a
 *  capture to wait for: the main loop then calls it again without sleeping. */
bool gl_read_has_work(const gl_read_t *r);

#endif /* GL_READ_H */
