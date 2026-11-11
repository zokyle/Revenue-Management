/*
 * gl_read.h - the camera part of a read: camera rail on, one horizon band
 * from the left camera, flagstick strips in the order L R R L repeated N
 * times, vision on every strip, camera rail off, and the combined result.
 *
 * It is a STEP machine for the cooperative main loop: gl_read_start()
 * powers the cameras and arms the first capture, gl_read_step() is called
 * whenever the DCMI reports (or periodically) and never waits for a frame.
 * The work is pipelined over two strip buffers: while strip k + 1 is being
 * captured by DMA into one buffer, strip k is analysed in the other.
 *
 * THE CAMERA RAIL IS OFF whenever gl_read_step() returns anything other
 * than GL_ERR_BUSY, after gl_read_abort(), and after a failed
 * gl_read_start().  The rail is switched off as soon as the last strip has
 * been captured, before that strip is analysed.
 *
 * TIMING OF L R R L.  The two sensors free-run and are not synchronised, so
 * the four strips of a group are not equally spaced in time (measured in
 * the simulator: 42 / 33 / 58 ms with a 9 ms phase offset).  The mean time
 * of the two L strips then differs from that of the two R strips by up to
 * about +-14 ms, and a swaying stick would leave a disparity error of
 * (sway rate x that difference).  The completion time of every strip is
 * recorded and the two left positions are moved, along the left camera's
 * own measured sway rate, to the mean time of the two right strips before
 * the group is handed to gl_vis_disp_acc_add_lrrl().  Linear sway then
 * cancels whatever the spacing.
 *
 * RAM: sizeof(gl_read_t) = 92160 (two strip buffers; the 640 x 96 band uses
 * the same memory) + 37120 (band work) + 4 x 10560 (stick work) + about
 * 1.5 kB of state = about 173 kB.  Stack: gl_read_step() about 250 bytes
 * plus the vision call chains (650 bytes, see core/gl_vision.h).
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
#define GL_READ_IMG_BYTES (2u * GL_READ_STRIP_BYTES) /* >= GL_READ_BAND_BYTES */

/** Result of the camera part of a read. */
typedef struct {
    bool stick_found;
    gl_vis_disparity_t disp;      /**< valid if stick_found */
    gl_vis_angles_t angles;       /**< bearing / elevations from the LEFT camera, rows averaged
                                       over the left strips of the read */
    gl_vis_quality_t quality;
    gl_vis_stick_t stick_left;    /**< averaged left-camera stick the angles came from */
    uint8_t groups_ok;            /**< L R R L groups that entered the disparity */
    uint8_t groups_tried;
    uint8_t strips_captured;
    uint8_t n_candidates;         /**< band candidates */
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
    GL_READ_BAND,   /**< waiting for the horizon band */
    GL_READ_STRIPS  /**< waiting for stick strip `k` */
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
    gl_strip_t cur;               /**< descriptor of the capture in progress */
    gl_vec3_t up;                 /**< unit up vector, marker frame (from the tilt read) */
    uint32_t t_rail_on_ms;
    gl_vis_candidate_t cand;
    uint16_t win_x0[GL_CAM_COUNT];
    /* ---- current L R R L group ---- */
    gl_vis_stick_t stick[4];
    bool stick_ok[4];
    uint32_t t_done_ms[4];
    /* ---- accumulation over the read ---- */
    gl_vis_disp_acc_t acc;
    float d_est_px;               /**< disparity estimate that sizes the segment */
    bool have_d_est;
    gl_vis_stick_t last[GL_CAM_COUNT]; /**< newest good stick per camera (next prior) */
    bool have_last[GL_CAM_COUNT];
    gl_vis_stick_t first[GL_CAM_COUNT];
    gl_vis_stats_t stats[GL_CAM_COUNT];
    bool have_first[GL_CAM_COUNT];
    float sum_bottom, sum_xb, sum_slope, sum_top, sum_horizon;
    uint16_t n_left, n_top, n_horizon_rows;
    gl_read_result_t result;
    /* ---- large work areas ---- */
    gl_vis_band_result_t band;
    gl_vis_band_work_t band_work;
    gl_vis_stick_work_t stick_work[4];
    uint8_t img[GL_READ_IMG_BYTES]; /**< band, or strip buffers 0 and 1 */
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

/** True while a read is in progress (the camera rail is on). */
bool gl_read_busy(const gl_read_t *r);

#endif /* GL_READ_H */
