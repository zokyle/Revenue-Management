/*
 * gl_scene.h - physically consistent synthetic scenes for tests/test_read.c.
 *
 * Written by the design reviewers, independently of gl_synth.c (it shares
 * no code with it), and adopted as a permanent test fixture.  Everything
 * is in SENSOR pixel coordinates (pixel centres at integers, row 0 at top).
 * An "edge at row e" means the boundary lies at coordinate e (so e = k + 0.5
 * is the boundary between pixel rows k and k + 1).
 *
 * Image formation (double precision, per pixel):
 *   far scene   sky / tree band / turf with anisotropic value-noise textures,
 *               horizontal glare gradient and a radial veiling-glare term;
 *               identical in both cameras (zero disparity)
 *   blobs       people-like soft-edged vertical bars, own disparity
 *   poles       other thin vertical lines, own disparity
 *   flag        cloth attached to the top part of the stick, shape changes
 *               with time (flapping)
 *   stick       box of given width convolved with a Gaussian PSF and the
 *               pixel aperture (closed form), own disparity, slant, sway
 *   grass       turf-coloured occluder with a ragged top in front of the
 *               stick base
 *   optics      per-camera extra Gaussian blur + veiling (dirty window)
 *   sensor      alternating-row gain, per-column fixed-pattern offset and
 *               gain (per camera, fixed over frames), Gaussian noise,
 *               rounding and clipping to 8 bits
 */
#ifndef GL_SCENE_H
#define GL_SCENE_H

#include <stdint.h>

#define GL_SCENE_MAX_BLOB 4
#define GL_SCENE_MAX_POLE 3

typedef struct {
    double x, w;          /* centre column (left camera) and width, px */
    double top, bot;      /* row edges */
    double level;         /* grey */
    double disp;          /* disparity, px (right camera sees it at x - disp) */
    double edge_sigma;    /* softness of the vertical edges, px */
    double tex;           /* rms texture on the blob */
    int front;            /* 1 = in front of the stick (occluder), 0 = behind */
} gl_scene_blob_t;

typedef struct {
    double x, w, top, bot, level, disp, slope;
} gl_scene_pole_t;

typedef struct {
    /* ---- far scene ---- */
    double sky, trees, turf;       /* grey levels */
    double tree_top;               /* row edge sky / trees (<= horizon); = horizon for no trees */
    double horizon;                /* row edge of the turf horizon at column 320 */
    double horizon_tilt;           /* rows per column */
    double sky_tex, tree_tex, turf_tex;  /* rms grey */
    double tree_lx, tree_ly;       /* correlation lengths of the tree texture, px */
    double turf_lx, turf_ly;
    double glare_gx;               /* grey per column, added above the horizon (and x0.3 below) */
    double glare_amp, glare_x, glare_y, glare_r; /* radial veiling: amp * exp(-dist / r) */
    uint32_t seed;                 /* scenery seed */
    /* ---- flagstick ---- */
    int stick;
    double sx;                     /* axis column at row s_bot (left camera, t = 0) */
    double s_slope;                /* columns per row */
    double s_w;                    /* width, px */
    double s_level;                /* grey */
    double s_top, s_bot;           /* row edges (s_top may be < 0) */
    double s_disp;                 /* disparity, px */
    /* motion of the stick: x += lin * t + amp * sin(2 pi hz t + phase) */
    double sway_lin, sway_amp, sway_hz, sway_phase;
    /* ---- flag ---- */
    int flag;
    double f_top, f_h;             /* row edge of the flag's top and its height, px */
    double f_len;                  /* largest horizontal extent, px */
    double f_level;
    double f_hz;                   /* flapping frequency */
    int f_side;                    /* +1 right, -1 left */
    /* ---- clutter ---- */
    int n_blob;
    gl_scene_blob_t blob[GL_SCENE_MAX_BLOB];
    int n_pole;
    gl_scene_pole_t pole[GL_SCENE_MAX_POLE];
    /* ---- grass in front of the base ---- */
    double grass_h;                /* mean height (rows) of the occluder above s_bot; 0 = none */
    double grass_jag;              /* relative raggedness 0..1 */
    /* ---- optics, per camera (0 = left, 1 = right) ---- */
    double psf[2];                 /* Gaussian sigma, px */
    double veil_gain[2];           /* contrast factor (1 = clean) */
    double veil_off[2];            /* added grey */
    /* ---- sensor ---- */
    double row_gain;               /* odd rows multiplied by (1 + row_gain) */
    double fpn_sigma;              /* per-column offset, grey rms */
    double prnu_sigma;             /* per-column gain, relative rms */
    double altcol_gain;            /* odd columns multiplied by (1 + altcol_gain) */
    uint32_t fpn_seed[2];
    double noise;                  /* grey rms, signal independent */
} gl_scene_t;

/* Plain overcast scene: sky 170, no trees, turf 90, horizon edge at 239.5,
 * PSF 0.6 px, noise 2 grey, no stick, no clutter, perfect sensor. */
void gl_scene_defaults(gl_scene_t *s);

/* Render camera `cam` (0 left, 1 right), window (x0, y0, w, h), at time t_s.
 * frame_seed selects the temporal noise. */
void gl_scene_render(const gl_scene_t *s, int cam, int x0, int y0, int w, int h, double t_s,
               uint32_t frame_seed, uint8_t *out);

/* Stick axis column of camera `cam` at row `y` and time t (truth). */
double gl_scene_stick_x(const gl_scene_t *s, int cam, double y, double t_s);

/* Truth: row edge of the lowest visible point of the stick (grass included). */
double gl_scene_stick_lowest(const gl_scene_t *s);

/* RNG helpers (splitmix64 based). */
typedef struct { uint64_t s; } gl_scene_rng_t;
void gl_scene_seed(gl_scene_rng_t *r, uint64_t seed);
double gl_scene_uniform(gl_scene_rng_t *r);            /* [0, 1) */
double gl_scene_normal(gl_scene_rng_t *r);
uint32_t gl_scene_u32(gl_scene_rng_t *r);

#endif
