/* gl_scene.c - physically consistent synthetic scenes for tests/test_read.c.  See gl_scene.h.
 * (Written by the design reviewers, independently of gl_synth.c, and adopted as a fixture.) */
#include "gl_scene.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>

#define PI 3.14159265358979323846

/* ---- RNG ------------------------------------------------------------------ */

static uint64_t splitmix_(uint64_t *s)
{
    uint64_t z = (*s += 0x9E3779B97F4A7C15ull);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ull;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBull;
    return z ^ (z >> 31);
}
void gl_scene_seed(gl_scene_rng_t *r, uint64_t seed) { r->s = seed * 0x2545F4914F6CDD1Dull + 0x1234567ull; }
uint32_t gl_scene_u32(gl_scene_rng_t *r) { return (uint32_t)(splitmix_(&r->s) >> 32); }
double gl_scene_uniform(gl_scene_rng_t *r) { return (double)(splitmix_(&r->s) >> 11) * (1.0 / 9007199254740992.0); }
double gl_scene_normal(gl_scene_rng_t *r)
{
    double u1 = gl_scene_uniform(r), u2 = gl_scene_uniform(r);
    if (u1 < 1e-300) {
        u1 = 1e-300;
    }
    return sqrt(-2.0 * log(u1)) * cos(2.0 * PI * u2);
}

/* ---- hashing and value noise ------------------------------------------------ */

static uint64_t mix3_(int64_t a, int64_t b, uint64_t seed)
{
    uint64_t z = (uint64_t)a * 0x9E3779B97F4A7C15ull ^ ((uint64_t)b + 0x7F4A7C15ull) * 0xC2B2AE3D27D4EB4Full ^
                 (seed + 0x165667B19E3779F9ull) * 0xD6E8FEB86659FD93ull;
    z = (z ^ (z >> 32)) * 0xBF58476D1CE4E5B9ull;
    z = (z ^ (z >> 29)) * 0x94D049BB133111EBull;
    return z ^ (z >> 32);
}
static double hash_pm1_(int64_t a, int64_t b, uint64_t seed)
{
    return (double)(mix3_(a, b, seed) >> 11) * (2.0 / 9007199254740992.0) - 1.0;
}
static double hash_normal_(int64_t a, int64_t b, uint64_t seed)
{
    double u1 = (double)(mix3_(a, b, seed) >> 11) * (1.0 / 9007199254740992.0);
    double u2 = (double)(mix3_(a, b, seed ^ 0xABCDEF12345ull) >> 11) * (1.0 / 9007199254740992.0);
    if (u1 < 1e-300) {
        u1 = 1e-300;
    }
    return sqrt(-2.0 * log(u1)) * cos(2.0 * PI * u2);
}

static double vnoise_(double x, double y, uint64_t seed)
{
    double fx = floor(x), fy = floor(y);
    int64_t ix = (int64_t)fx, iy = (int64_t)fy;
    double tx = x - fx, ty = y - fy;
    double sx = tx * tx * tx * (tx * (tx * 6.0 - 15.0) + 10.0);
    double sy = ty * ty * ty * (ty * (ty * 6.0 - 15.0) + 10.0);
    double a = hash_pm1_(ix, iy, seed), b = hash_pm1_(ix + 1, iy, seed);
    double c = hash_pm1_(ix, iy + 1, seed), d = hash_pm1_(ix + 1, iy + 1, seed);
    return (a + (b - a) * sx) + ((c + (d - c) * sx) - (a + (b - a) * sx)) * sy;
}

/* Two-octave texture, scaled to unit rms (factor found numerically once). */
static double tex_raw_(double x, double y, double lx, double ly, uint64_t seed)
{
    return 0.75 * vnoise_(x / lx, y / ly, seed) +
           0.45 * vnoise_(2.17 * x / lx + 31.7, 2.17 * y / ly + 11.3, seed + 0x51ull);
}
static double tex_norm_ = 0.0;
static double tex_(double x, double y, double lx, double ly, uint64_t seed)
{
    if (tex_norm_ == 0.0) {
        double s2 = 0.0;
        int n = 0;
        for (int i = 0; i < 200; i++) {
            for (int j = 0; j < 200; j++) {
                double v = tex_raw_(0.37 * i + 0.11, 0.41 * j + 0.23, 1.0, 1.0, 777u);
                s2 += v * v;
                n++;
            }
        }
        tex_norm_ = 1.0 / sqrt(s2 / n);
    }
    return tex_norm_ * tex_raw_(x, y, lx, ly, seed);
}

/* ---- blurred, pixel-integrated step ------------------------------------------ */

static double phi_(double t) { return exp(-0.5 * t * t) * 0.3989422804014327; }
static double Phi_(double t) { return 0.5 * erfc(-t * 0.7071067811865476); }
static double G_(double t) { return t * Phi_(t) + phi_(t); }

/* Fraction of pixel centred at p (aperture 1) lying beyond edge e (p > e side),
 * after a Gaussian blur of sigma. */
static double fpix_(double p, double e, double sigma)
{
    double d = p - e;
    if (d > 0.5 + 6.0 * sigma) {
        return 1.0;
    }
    if (d < -0.5 - 6.0 * sigma) {
        return 0.0;
    }
    if (sigma < 1e-6) {
        double f = d + 0.5;
        return (f < 0.0) ? 0.0 : ((f > 1.0) ? 1.0 : f);
    }
    return sigma * (G_((d + 0.5) / sigma) - G_((d - 0.5) / sigma));
}

/* ---- scene -------------------------------------------------------------------- */

void gl_scene_defaults(gl_scene_t *s)
{
    memset(s, 0, sizeof(*s));
    s->sky = 170.0;
    s->trees = 70.0;
    s->turf = 90.0;
    s->horizon = 239.5;
    s->tree_top = 239.5;
    s->tree_lx = 4.0;
    s->tree_ly = 60.0;
    s->turf_lx = 2.0;
    s->turf_ly = 1.2;
    s->glare_r = 200.0;
    s->seed = 1u;
    s->s_level = 230.0;
    s->s_w = 1.5;
    s->s_top = -50.0;
    s->s_bot = 242.0;
    s->f_side = 1;
    s->f_hz = 2.0;
    s->grass_jag = 0.6;
    s->psf[0] = s->psf[1] = 0.6;
    s->veil_gain[0] = s->veil_gain[1] = 1.0;
    s->fpn_seed[0] = 101u;
    s->fpn_seed[1] = 202u;
    s->noise = 2.0;
}

static double sway_(const gl_scene_t *s, double t)
{
    return s->sway_lin * t + s->sway_amp * sin(2.0 * PI * s->sway_hz * t + s->sway_phase);
}

double gl_scene_stick_x(const gl_scene_t *s, int cam, double y, double t)
{
    return s->sx + s->s_slope * (y - s->s_bot) + sway_(s, t) - (cam ? s->s_disp : 0.0);
}

/* top edge (row) of the grass occluder at left-camera column xl */
static double grass_edge_(const gl_scene_t *s, double xl)
{
    double h = s->grass_h * (1.0 + s->grass_jag * vnoise_(xl / 1.3, 0.5, s->seed + 0x9999ull));
    if (h < 0.0) {
        h = 0.0;
    }
    return s->s_bot - h;
}

double gl_scene_stick_lowest(const gl_scene_t *s)
{
    if (!(s->grass_h > 0.0)) {
        return s->s_bot;
    }
    {
        double acc = 0.0;
        int n = 0;
        double hw = 0.5 * s->s_w;
        for (int i = -4; i <= 4; i++) {
            acc += grass_edge_(s, s->sx + hw * (double)i / 4.0);
            n++;
        }
        return acc / n;
    }
}

static void blur_sep_(double *img, int w, int h, double sigma, double *tmp)
{
    double k[33];
    int r = (int)ceil(3.5 * sigma);
    double sum = 0.0;
    if (r > 16) {
        r = 16;
    }
    for (int i = -r; i <= r; i++) {
        k[i + r] = exp(-0.5 * (double)i * (double)i / (sigma * sigma));
        sum += k[i + r];
    }
    for (int i = 0; i <= 2 * r; i++) {
        k[i] /= sum;
    }
    for (int y = 0; y < h; y++) {
        for (int x = 0; x < w; x++) {
            double a = 0.0;
            for (int i = -r; i <= r; i++) {
                int xx = x + i;
                xx = (xx < 0) ? 0 : ((xx >= w) ? w - 1 : xx);
                a += k[i + r] * img[y * w + xx];
            }
            tmp[y * w + x] = a;
        }
    }
    for (int y = 0; y < h; y++) {
        for (int x = 0; x < w; x++) {
            double a = 0.0;
            for (int i = -r; i <= r; i++) {
                int yy = y + i;
                yy = (yy < 0) ? 0 : ((yy >= h) ? h - 1 : yy);
                a += k[i + r] * tmp[yy * w + x];
            }
            img[y * w + x] = a;
        }
    }
}

void gl_scene_render(const gl_scene_t *s, int cam, int x0, int y0, int w, int h, double t,
               uint32_t frame_seed, uint8_t *out)
{
    const double psf = (s->psf[0] < s->psf[1]) ? s->psf[0] : s->psf[1];
    const double extra2 = s->psf[cam] * s->psf[cam] - psf * psf;
    const double extra = (extra2 > 1e-6) ? sqrt(extra2) : 0.0;
    const int M = (extra > 0.0) ? 10 : 0;
    const int W = w + 2 * M, H = h + 2 * M;
    double *img = (double *)malloc(sizeof(double) * (size_t)W * (size_t)H * 2u);
    double *tmp = img + (size_t)W * (size_t)H;
    gl_scene_rng_t rng;
    const double camshift = cam ? 1.0 : 0.0;

    for (int j = 0; j < H; j++) {
        const double y = (double)(y0 - M + j);
        /* stick axis for this row: two sub-rows */
        double xc_a = 0.0, xc_b = 0.0, av_stick = 0.0;
        if (s->stick) {
            xc_a = gl_scene_stick_x(s, cam, y - 0.2887, t);
            xc_b = gl_scene_stick_x(s, cam, y + 0.2887, t);
            av_stick = fpix_(y, s->s_top, psf) - fpix_(y, s->s_bot, psf);
        }
        for (int i = 0; i < W; i++) {
            const double x = (double)(x0 - M + i);
            const double hrow = s->horizon + s->horizon_tilt * (x - 320.0);
            const double a_turf = fpix_(y, hrow, psf);
            double a_tree = 0.0, a_sky, v = 0.0, glare, turf_v;

            if (s->tree_top < hrow - 1e-9) {
                a_tree = fpix_(y, s->tree_top, psf) - a_turf;
                if (a_tree < 0.0) {
                    a_tree = 0.0;
                }
            }
            a_sky = 1.0 - a_turf - a_tree;
            glare = 0.0;
            if (s->glare_amp != 0.0) {
                double dx = x - s->glare_x, dy = y - s->glare_y;
                glare = s->glare_amp * exp(-sqrt(dx * dx + dy * dy) / s->glare_r);
            }
            turf_v = s->turf + 0.3 * s->glare_gx * (x - 320.0);
            if (s->turf_tex > 0.0) {
                /* texture gets coarser toward the camera (lower rows) */
                double sc = 1.0 + 0.02 * ((y > hrow) ? (y - hrow) : 0.0);
                turf_v += s->turf_tex * tex_(x, y, s->turf_lx * sc, s->turf_ly * sc, s->seed + 3u);
            }
            if (a_sky > 1e-6) {
                double sv = s->sky + s->glare_gx * (x - 320.0);
                if (s->sky_tex > 0.0) {
                    sv += s->sky_tex * tex_(x, y, 60.0, 30.0, s->seed + 1u);
                }
                v += a_sky * sv;
            }
            if (a_tree > 1e-6) {
                double tv = s->trees + 0.5 * s->glare_gx * (x - 320.0);
                if (s->tree_tex > 0.0) {
                    tv += s->tree_tex * tex_(x, y, s->tree_lx, s->tree_ly, s->seed + 2u);
                }
                v += a_tree * tv;
            }
            if (a_turf > 1e-6) {
                v += a_turf * turf_v;
            }

            /* people-like blobs behind the stick */
            for (int b = 0; b < s->n_blob; b++) {
                const gl_scene_blob_t *bl = &s->blob[b];
                if (bl->front) {
                    continue;
                }
                const double bx = bl->x - camshift * bl->disp;
                const double es = (bl->edge_sigma > psf) ? bl->edge_sigma : psf;
                if (fabs(x - bx) < 0.5 * bl->w + 6.0 * es + 1.0) {
                    double ah = fpix_(x, bx - 0.5 * bl->w, es) - fpix_(x, bx + 0.5 * bl->w, es);
                    double avv = fpix_(y, bl->top, es) - fpix_(y, bl->bot, es);
                    double a = ah * avv;
                    if (a > 1e-6) {
                        double lv = bl->level;
                        if (bl->tex > 0.0) {
                            lv += bl->tex * tex_(x + camshift * bl->disp, y, 3.0, 9.0,
                                                 s->seed + 40u + (uint32_t)b);
                        }
                        v = v * (1.0 - a) + a * lv;
                    }
                }
            }
            /* other poles */
            for (int p = 0; p < s->n_pole; p++) {
                const gl_scene_pole_t *pl = &s->pole[p];
                const double px = pl->x + pl->slope * (y - pl->bot) - camshift * pl->disp;
                if (fabs(x - px) < 0.5 * pl->w + 6.0 * psf + 1.0) {
                    double ah = fpix_(x, px - 0.5 * pl->w, psf) - fpix_(x, px + 0.5 * pl->w, psf);
                    double avv = fpix_(y, pl->top, psf) - fpix_(y, pl->bot, psf);
                    double a = ah * avv;
                    if (a > 1e-6) {
                        v = v * (1.0 - a) + a * pl->level;
                    }
                }
            }
            if (s->stick) {
                /* flag behind the stick */
                if (s->flag && y > s->f_top - 4.0 && y < s->f_top + s->f_h + 4.0) {
                    double xc = 0.5 * (xc_a + xc_b);
                    double L = s->f_len * (0.35 + 0.65 * fabs(sin(2.0 * PI * s->f_hz * t +
                                                                 0.15 * (y - s->f_top))));
                    double xl = (s->f_side > 0) ? xc : (xc - L);
                    double xr = (s->f_side > 0) ? (xc + L) : xc;
                    if (x > xl - 5.0 && x < xr + 5.0) {
                        double ah = fpix_(x, xl, psf) - fpix_(x, xr, psf);
                        double avv = fpix_(y, s->f_top, psf) - fpix_(y, s->f_top + s->f_h, psf);
                        double a = ah * avv;
                        if (a > 1e-6) {
                            v = v * (1.0 - a) + a * s->f_level;
                        }
                    }
                }
                if (av_stick > 1e-6 && fabs(x - xc_a) < 0.5 * s->s_w + 6.0 * psf + 1.5) {
                    double ah = 0.5 * (fpix_(x, xc_a - 0.5 * s->s_w, psf) - fpix_(x, xc_a + 0.5 * s->s_w, psf)) +
                                0.5 * (fpix_(x, xc_b - 0.5 * s->s_w, psf) - fpix_(x, xc_b + 0.5 * s->s_w, psf));
                    double a = ah * av_stick;
                    v = v * (1.0 - a) + a * s->s_level;
                }
                /* grass in front of the base, at the stick's depth */
                if (s->grass_h > 0.0 && y > s->s_bot - 3.0 * s->grass_h - 4.0) {
                    double e = grass_edge_(s, x + camshift * s->s_disp);
                    double a = fpix_(y, e, psf);
                    if (a > 1e-6) {
                        v = v * (1.0 - a) + a * turf_v;
                    }
                }
            }
            /* occluders in front of the stick */
            for (int b = 0; b < s->n_blob; b++) {
                const gl_scene_blob_t *bl = &s->blob[b];
                if (!bl->front) {
                    continue;
                }
                const double bx = bl->x - camshift * bl->disp;
                const double es = (bl->edge_sigma > psf) ? bl->edge_sigma : psf;
                if (fabs(x - bx) < 0.5 * bl->w + 6.0 * es + 1.0) {
                    double ah = fpix_(x, bx - 0.5 * bl->w, es) - fpix_(x, bx + 0.5 * bl->w, es);
                    double avv = fpix_(y, bl->top, es) - fpix_(y, bl->bot, es);
                    double a = ah * avv;
                    if (a > 1e-6) {
                        double lv = bl->level;
                        if (bl->tex > 0.0) {
                            lv += bl->tex * tex_(x + camshift * bl->disp, y, 3.0, 9.0,
                                                 s->seed + 40u + (uint32_t)b);
                        }
                        v = v * (1.0 - a) + a * lv;
                    }
                }
            }
            v += glare;
            img[j * W + i] = v;
        }
    }
    if (extra > 0.0) {
        blur_sep_(img, W, H, extra, tmp);
    }
    gl_scene_seed(&rng, ((uint64_t)frame_seed << 20) ^ ((uint64_t)cam << 5) ^ 0x5DEECE66Dull);
    for (int j = 0; j < h; j++) {
        const int ys = y0 + j;
        const double rg = 1.0 + ((ys & 1) ? s->row_gain : 0.0);
        for (int i = 0; i < w; i++) {
            const int xs = x0 + i;
            double v = img[(j + M) * W + (i + M)];
            v = s->veil_off[cam] + s->veil_gain[cam] * v;
            v *= rg;
            if (s->altcol_gain != 0.0 && (xs & 1)) {
                v *= 1.0 + s->altcol_gain;
            }
            if (s->prnu_sigma > 0.0) {
                v *= 1.0 + s->prnu_sigma * hash_normal_(xs, 7, s->fpn_seed[cam] + 0x777ull);
            }
            if (s->fpn_sigma > 0.0) {
                v += s->fpn_sigma * hash_normal_(xs, 3, s->fpn_seed[cam]);
            }
            if (s->noise > 0.0) {
                v += s->noise * gl_scene_normal(&rng);
            }
            v = floor(v + 0.5);
            out[j * w + i] = (uint8_t)((v < 0.0) ? 0.0 : ((v > 255.0) ? 255.0 : v));
        }
    }
    free(img);
}
