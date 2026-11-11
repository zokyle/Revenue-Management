/* gl_synth.c - see gl_synth.h. */
#include "gl_synth.h"

#include <math.h>
#include <string.h>

uint32_t gl_synth_rand_u32(uint32_t *state)
{
    uint32_t x = *state;
    if (x == 0u) {
        x = 0x6D2B79F5u;
    }
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    *state = x;
    return x;
}

float gl_synth_rand_uniform(uint32_t *state)
{
    return (float)(gl_synth_rand_u32(state) >> 8) * (1.0f / 16777216.0f);
}

float gl_synth_rand_normal(uint32_t *state)
{
    /* Box-Muller, one value per call */
    float u1 = (float)((gl_synth_rand_u32(state) >> 8) + 1u) * (1.0f / 16777217.0f);
    float u2 = gl_synth_rand_uniform(state);
    return sqrtf(-2.0f * logf(u1)) * cosf(6.2831853f * u2);
}

void gl_synth_defaults(gl_synth_scene_t *s, uint16_t width, uint16_t height, uint16_t x0,
                       uint16_t y0)
{
    memset(s, 0, sizeof(*s));
    s->width = width;
    s->height = height;
    s->x0 = x0;
    s->y0 = y0;
    s->bg_level = 110.0f;
    s->turf_level = 70.0f;
    s->horizon_row = 240.0f;
    s->texture_scale_px = 6.0f;
    s->texture_seed = 1u;
    s->stick_width_px = 1.5f;
    s->stick_level = 170.0f;
    s->stick_top_row = -1000.0f;
    s->stick_bottom_row = 240.0f;
    s->stick_ref_row = 240.0f;
    s->psf_sigma_px = 0.6f;
    s->noise_seed = 12345u;
}

float gl_synth_stick_x_at(const gl_synth_scene_t *s, float sensor_row)
{
    return s->stick_x + s->stick_slant * (sensor_row - s->stick_ref_row);
}

/* Antiderivative of the Gaussian-blurred unit step: E(t) = integral of
 * Phi(t / sigma).  With sigma -> 0 it is max(t, 0). */
static float step_integral_(float t, float sigma)
{
    if (sigma < 1e-3f) {
        return (t > 0.0f) ? t : 0.0f;
    }
    {
        float z = t / sigma;
        float cdf = 0.5f * (1.0f + erff(z * 0.70710678f));
        float pdf = 0.39894228f * expf(-0.5f * z * z);
        return t * cdf + sigma * pdf;
    }
}

/* Mean over the pixel [p - 0.5, p + 0.5] of a blurred step that turns on at
 * position `edge`. */
static float step_cover_(float p, float edge, float sigma)
{
    return step_integral_(p + 0.5f - edge, sigma) - step_integral_(p - 0.5f - edge, sigma);
}

/* Mean over the pixel of a blurred box [a, b]. */
static float box_cover_(float p, float a, float b, float sigma)
{
    float c = step_cover_(p, a, sigma) - step_cover_(p, b, sigma);
    return (c < 0.0f) ? 0.0f : ((c > 1.0f) ? 1.0f : c);
}

static uint32_t hash_(int32_t ix, int32_t iy, uint32_t seed)
{
    uint32_t h = (uint32_t)ix * 0x9E3779B1u ^ (uint32_t)iy * 0x85EBCA77u ^ seed * 0xC2B2AE3Du;
    h ^= h >> 15;
    h *= 0x2C1B3C6Du;
    h ^= h >> 12;
    h *= 0x297A2D39u;
    h ^= h >> 15;
    return h;
}

static float lattice_(int32_t ix, int32_t iy, uint32_t seed)
{
    return (float)(hash_(ix, iy, seed) >> 8) * (2.0f / 16777216.0f) - 1.0f; /* [-1, 1) */
}

/* Smooth value noise, roughly unit rms, correlation length `scale`. */
static float texture_(float x, float y, float scale, uint32_t seed)
{
    float sum = 0.0f;
    float amp = 1.0f;
    for (int oct = 0; oct < 2; oct++) {
        float fx = x / scale, fy = y / scale;
        float flx = floorf(fx), fly = floorf(fy);
        int32_t ix = (int32_t)flx, iy = (int32_t)fly;
        float tx = fx - flx, ty = fy - fly;
        float sx = tx * tx * (3.0f - 2.0f * tx), sy = ty * ty * (3.0f - 2.0f * ty);
        float v00 = lattice_(ix, iy, seed + (uint32_t)oct);
        float v10 = lattice_(ix + 1, iy, seed + (uint32_t)oct);
        float v01 = lattice_(ix, iy + 1, seed + (uint32_t)oct);
        float v11 = lattice_(ix + 1, iy + 1, seed + (uint32_t)oct);
        float a = v00 + (v10 - v00) * sx;
        float b = v01 + (v11 - v01) * sx;
        sum += amp * (a + (b - a) * sy);
        amp *= 0.5f;
        scale *= 0.5f;
    }
    /* a bilinear blend of uniform [-1, 1] lattice values has rms about 0.4;
     * two octaves at 1 and 0.5: about 0.45 */
    return sum * (1.0f / 0.45f);
}

void gl_synth_render(const gl_synth_scene_t *s, uint8_t *buf)
{
    uint32_t noise_state = s->noise_seed * 2654435761u + 0x1234567u;
    const float sig = s->psf_sigma_px;
    const float reach = 0.5f * s->stick_width_px + 4.0f * sig + 1.5f;

    for (uint32_t r = 0; r < s->height; r++) {
        const float row = (float)(s->y0 + r);
        /* fraction of this pixel row that is turf */
        const float turf = (s->horizon_row < -1000.0f) ? 0.0f
                                                       : step_cover_(row, s->horizon_row, sig);
        /* vertical coverage of the stick on this row */
        const float vcov = s->stick_present
                               ? box_cover_(row, s->stick_top_row, s->stick_bottom_row, sig)
                               : 0.0f;
        for (uint32_t c = 0; c < s->width; c++) {
            const float col = (float)(s->x0 + c);
            float bg = s->bg_level + s->bg_vgrad * row;
            float tf = s->turf_level;
            float v;

            if (s->bg_texture_amp > 0.0f) {
                bg += s->bg_texture_amp *
                      texture_(col + s->texture_shift_x, row, s->texture_scale_px, s->texture_seed);
            }
            if (s->turf_texture_amp > 0.0f) {
                tf += s->turf_texture_amp *
                      texture_(col, row * 3.0f, s->texture_scale_px, s->texture_seed + 77u);
            }
            v = bg + (tf - bg) * turf;

            for (int k = 0; k < s->n_clutter && k < GL_SYNTH_MAX_CLUTTER; k++) {
                const gl_synth_box_t *b = &s->clutter[k];
                float vc = box_cover_(row, b->row_top, b->row_bottom, sig);
                if (vc > 0.0f) {
                    float shift = b->slant * (row - b->row_top);
                    float hc = box_cover_(col, b->x_left + shift, b->x_right + shift, sig);
                    v += (b->level - v) * hc * vc;
                }
            }
            if (vcov > 0.0f) {
                /* three sub-rows so that a slanted stick is integrated over
                 * the pixel height */
                float cover = 0.0f;
                for (int sub = -1; sub <= 1; sub++) {
                    float xa = gl_synth_stick_x_at(s, row + (float)sub / 3.0f);
                    if (fabsf(col - xa) < reach) {
                        cover += box_cover_(col, xa - 0.5f * s->stick_width_px,
                                            xa + 0.5f * s->stick_width_px, sig);
                    }
                }
                cover *= vcov / 3.0f;
                v += (s->stick_level - v) * cover;
            }
            if (s->sun) {
                float dx = col - s->sun_x, dy = row - s->sun_row;
                float d2 = (dx * dx + dy * dy) / (s->sun_radius_px * s->sun_radius_px);
                v += 2000.0f * expf(-d2); /* disc far beyond full scale, with a glare skirt */
            }
            if (s->noise_sigma > 0.0f) {
                v += s->noise_sigma * gl_synth_rand_normal(&noise_state);
            }
            v = floorf(v + 0.5f);
            buf[r * s->width + c] = (uint8_t)((v < 0.0f) ? 0.0f : ((v > 255.0f) ? 255.0f : v));
        }
    }
}
