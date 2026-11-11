/*
 * gl_synth.h - synthetic 8-bit luminance strip renderer for the vision
 * tests.  Host only.
 *
 * Renders what one camera would deliver for a window (strip) of the sensor:
 * a far background above a turf horizon, a flagstick as an anti-aliased
 * near-vertical bar of given SUB-PIXEL position, width, slant and grey
 * level, optional clutter, lens blur, sensor noise and 8-bit quantisation.
 *
 * All scene coordinates are SENSOR coordinates (column, row; pixel centres
 * at integers; row 0 at the top), so that the same scene can be rendered
 * through differently placed strips.  The strip covers columns
 * x0 .. x0 + width - 1 and rows y0 .. y0 + height - 1.
 *
 * Image formation per pixel:
 *   background  bg_level above horizon_row, turf_level below, blended
 *               through the lens blur; plus band-limited texture
 *   stick       coverage = (box of stick_width_px convolved with a Gaussian
 *               PSF of psf_sigma_px, integrated exactly over the pixel
 *               aperture) x (the same along rows between top and bottom);
 *               pixel = background * (1 - coverage) + stick_level * coverage
 *   clutter     opaque bars / boxes composited the same way
 *   noise       additive Gaussian, then rounding and clipping to 0..255
 *
 * Sway and stereo: render successive frames (or the two cameras) with a
 * different stick_x and a different noise_seed; texture_seed stays the same
 * for one scene.
 *
 * NOT modelled: the Bayer mosaic and the sensor's YUV conversion (a
 * sub-pixel line on a colour sensor has chroma aliasing that this renderer
 * does not reproduce), lens distortion, rolling shutter, blooming.
 */
#ifndef GL_SYNTH_H
#define GL_SYNTH_H

#include <stdbool.h>
#include <stdint.h>

#define GL_SYNTH_MAX_CLUTTER 4

typedef struct {
    float x_left, x_right;     /**< sensor columns of the two edges at row_top */
    float row_top, row_bottom; /**< sensor rows */
    float level;               /**< grey level of the object */
    float slant;               /**< columns per row */
} gl_synth_box_t;

typedef struct {
    /* strip */
    uint16_t width, height;
    uint16_t x0, y0;
    /* background */
    float bg_level;            /**< far background (sky, trees), grey */
    float bg_vgrad;            /**< grey per row added to the background (sky gradient) */
    float turf_level;          /**< turf below the horizon, grey */
    float horizon_row;         /**< sensor row of the turf horizon; < -1000 = no turf */
    float bg_texture_amp;      /**< rms grey of the background texture (0 = none) */
    float turf_texture_amp;    /**< rms grey of the turf texture */
    float texture_scale_px;    /**< correlation length of the texture, pixels */
    uint32_t texture_seed;     /**< same seed = same scenery (use one per scene) */
    float texture_shift_x;     /**< shifts the scenery horizontally (parallax of a near background) */
    /* flagstick */
    bool stick_present;
    float stick_x;             /**< sensor column of the stick axis at stick_ref_row */
    float stick_ref_row;
    float stick_slant;         /**< columns per row (tan of the lean) */
    float stick_width_px;
    float stick_level;         /**< grey level of the stick */
    float stick_top_row;       /**< sensor row of the top end (may be above the strip) */
    float stick_bottom_row;    /**< sensor row of the lowest visible point */
    /* clutter */
    int n_clutter;
    gl_synth_box_t clutter[GL_SYNTH_MAX_CLUTTER];
    /* sun */
    bool sun;
    float sun_x, sun_row, sun_radius_px;
    /* optics and sensor */
    float psf_sigma_px;        /**< Gaussian lens blur, pixels */
    float noise_sigma;         /**< grey levels rms */
    uint32_t noise_seed;       /**< different per frame */
} gl_synth_scene_t;

/** A plain scene: mid-grey background 110, turf 70 below sensor row 240,
 *  no texture, no stick, PSF 0.6 px, no noise. */
void gl_synth_defaults(gl_synth_scene_t *s, uint16_t width, uint16_t height, uint16_t x0,
                       uint16_t y0);

/** Render into buf[height * width], row-major. */
void gl_synth_render(const gl_synth_scene_t *s, uint8_t *buf);

/** Stick axis column at a sensor row. */
float gl_synth_stick_x_at(const gl_synth_scene_t *s, float sensor_row);

/** Deterministic generators shared by the tests. */
uint32_t gl_synth_rand_u32(uint32_t *state);
float gl_synth_rand_uniform(uint32_t *state);  /**< [0, 1) */
float gl_synth_rand_normal(uint32_t *state);   /**< zero mean, unit variance */

#endif /* GL_SYNTH_H */
