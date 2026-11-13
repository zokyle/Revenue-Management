/*
 * gl_gfx.c - 1-bpp drawing with round clipping.  See gl_gfx.h for the
 * framebuffer format and conventions.
 *
 * Every drawing primitive funnels through span_(), which applies the clip,
 * so no primitive can write outside the aperture circle or the buffer.
 */
#include "gl_gfx.h"

#include <math.h>
#include <string.h>

#include "gl_config.h"

/* Float -> int with clamping first, so an extreme coordinate can never
 * overflow the conversion (undefined behaviour). */
static int clamp_floor_(float v)
{
    if (!(v == v)) {
        return -2000; /* NaN: makes an empty span (upper end below any lower end) */
    }
    v = gl_clampf(v, -1000.0f, 1000.0f);
    return (int)floorf(v);
}

static int clamp_ceil_(float v)
{
    if (!(v == v)) {
        return 2000;
    }
    v = gl_clampf(v, -1000.0f, 1000.0f);
    return (int)ceilf(v);
}

/* Integer coordinates and sizes are clamped to +-GL_GFX_COORD_LIMIT at the
 * entry of every integer primitive, so that no sum of a position and a size
 * can overflow (undefined behaviour for signed int).  The limit is 8000
 * screens wide: nothing that could be visible is changed by it. */
static int coord_(int v)
{
    return gl_clampi(v, -GL_GFX_COORD_LIMIT, GL_GFX_COORD_LIMIT);
}

static unsigned isqrt_(unsigned v)
{
    unsigned r = 0;
    while ((r + 1u) * (r + 1u) <= v) {
        r++;
    }
    return r;
}

static void build_clip_(gl_gfx_t *g)
{
    /* Work in half-pixel units: pixel x spans [2x - 1, 2x + 1] - 127 from the
     * centre.  A pixel is drawable when its FARTHEST corner is inside the
     * circle of diameter D pixels (radius D half-pixel units). */
    const int d = GL_CFG_LCD_CLIP_DIA_PX;
    for (int y = 0; y < GL_GFX_H; y++) {
        int ay = 2 * y - (GL_GFX_H - 1);
        int rem;
        if (ay < 0) {
            ay = -ay;
        }
        ay += 1;
        rem = d * d - ay * ay;
        if (!g->clip_on) {
            g->clip_x0[y] = 0;
            g->clip_x1[y] = (uint8_t)(GL_GFX_W - 1);
        } else if (rem < 4) {
            g->clip_x0[y] = 1; /* empty row: x0 > x1 */
            g->clip_x1[y] = 0;
        } else {
            int ax_max = (int)isqrt_((unsigned)rem); /* |2x - 127| + 1 <= ax_max */
            int half = ax_max - 1;                   /* |2x - 127| <= half */
            int x0 = (GL_GFX_W - 1 - half + 1) / 2;  /* ceil((127 - half) / 2) */
            int x1 = (GL_GFX_W - 1 + half) / 2;      /* floor((127 + half) / 2) */
            if (x0 > x1) {
                g->clip_x0[y] = 1;
                g->clip_x1[y] = 0;
            } else {
                g->clip_x0[y] = (uint8_t)x0;
                g->clip_x1[y] = (uint8_t)x1;
            }
        }
    }
}

/* Fill x0..x1 (inclusive, already ordered) on row y after clipping.
 * Returns the number of pixels written. */
static unsigned span_(gl_gfx_t *g, int x0, int x1, int y, gl_ink_t ink)
{
    uint8_t *row;
    if (y < 0 || y >= GL_GFX_H) {
        return 0;
    }
    if (x0 < (int)g->clip_x0[y]) {
        x0 = (int)g->clip_x0[y];
    }
    if (x1 > (int)g->clip_x1[y]) {
        x1 = (int)g->clip_x1[y];
    }
    if (x0 > x1) {
        return 0;
    }
    row = &g->px[y * GL_GFX_STRIDE];
    for (int b = x0 >> 3; b <= (x1 >> 3); b++) {
        int lo = (b == (x0 >> 3)) ? (x0 & 7) : 0;
        int hi = (b == (x1 >> 3)) ? (x1 & 7) : 7;
        uint8_t mask = (uint8_t)((0xFFu << lo) & (0xFFu >> (7 - hi)));
        if (ink == GL_INK_WHITE) {
            row[b] = (uint8_t)(row[b] | mask);
        } else {
            row[b] = (uint8_t)(row[b] & (uint8_t)~mask);
        }
    }
    return (unsigned)(x1 - x0 + 1);
}

void gl_gfx_init(gl_gfx_t *g)
{
    g->clip_on = true;
    build_clip_(g);
    gl_gfx_clear(g, GL_INK_WHITE);
}

void gl_gfx_set_clip(gl_gfx_t *g, bool round_clip)
{
    g->clip_on = round_clip;
    build_clip_(g);
}

void gl_gfx_clear(gl_gfx_t *g, gl_ink_t ink)
{
    memset(g->px, (ink == GL_INK_WHITE) ? 0xFF : 0x00, sizeof(g->px));
}

bool gl_gfx_in_clip(const gl_gfx_t *g, int x, int y)
{
    if (x < 0 || x >= GL_GFX_W || y < 0 || y >= GL_GFX_H) {
        return false;
    }
    return x >= (int)g->clip_x0[y] && x <= (int)g->clip_x1[y];
}

void gl_gfx_pixel(gl_gfx_t *g, int x, int y, gl_ink_t ink)
{
    (void)span_(g, x, x, y, ink);
}

bool gl_gfx_get(const gl_gfx_t *g, int x, int y)
{
    if (x < 0 || x >= GL_GFX_W || y < 0 || y >= GL_GFX_H) {
        return true;
    }
    return (((unsigned)g->px[y * GL_GFX_STRIDE + (x >> 3)] >> (x & 7)) & 1u) != 0u;
}

const uint8_t *gl_gfx_row(const gl_gfx_t *g, int y)
{
    y = gl_clampi(y, 0, GL_GFX_H - 1);
    return &g->px[y * GL_GFX_STRIDE];
}

void gl_gfx_rotate_180(gl_gfx_t *g)
{
    /* pixel (x, y) <-> (127 - x, 127 - y): byte i <-> byte (last - i), each
     * with its bits in reverse order.  The clip circle is centred on the
     * screen, so a clipped picture stays inside it. */
    for (unsigned i = 0; i < GL_GFX_BYTES / 2u; i++) {
        uint8_t a = g->px[i];
        uint8_t b = g->px[GL_GFX_BYTES - 1u - i];
        a = (uint8_t)(((a & 0xF0u) >> 4) | ((a & 0x0Fu) << 4));
        a = (uint8_t)(((a & 0xCCu) >> 2) | ((a & 0x33u) << 2));
        a = (uint8_t)(((a & 0xAAu) >> 1) | ((a & 0x55u) << 1));
        b = (uint8_t)(((b & 0xF0u) >> 4) | ((b & 0x0Fu) << 4));
        b = (uint8_t)(((b & 0xCCu) >> 2) | ((b & 0x33u) << 2));
        b = (uint8_t)(((b & 0xAAu) >> 1) | ((b & 0x55u) << 1));
        g->px[i] = b;
        g->px[GL_GFX_BYTES - 1u - i] = a;
    }
}

unsigned gl_gfx_count_black(const gl_gfx_t *g)
{
    unsigned n = 0;
    for (size_t i = 0; i < sizeof(g->px); i++) {
        uint8_t v = (uint8_t)~g->px[i];
        while (v != 0u) {
            n += (unsigned)(v & 1u);
            v = (uint8_t)(v >> 1);
        }
    }
    return n;
}

unsigned gl_gfx_changed_rows(const gl_gfx_t *g, const uint8_t shadow[GL_GFX_BYTES],
                             uint8_t rows[GL_GFX_H])
{
    unsigned n = 0;
    for (int y = 0; y < GL_GFX_H; y++) {
        if (memcmp(&g->px[y * GL_GFX_STRIDE], &shadow[y * GL_GFX_STRIDE], GL_GFX_STRIDE) != 0) {
            rows[n++] = (uint8_t)y;
        }
    }
    return n;
}

void gl_gfx_hline(gl_gfx_t *g, int x0, int x1, int y, gl_ink_t ink)
{
    x0 = coord_(x0);
    x1 = coord_(x1);
    if (x0 > x1) {
        int t = x0;
        x0 = x1;
        x1 = t;
    }
    (void)span_(g, x0, x1, y, ink);
}

void gl_gfx_vline(gl_gfx_t *g, int x, int y0, int y1, gl_ink_t ink)
{
    x = coord_(x);
    if (y0 > y1) {
        int t = y0;
        y0 = y1;
        y1 = t;
    }
    y0 = gl_clampi(y0, 0, GL_GFX_H - 1);
    y1 = gl_clampi(y1, -1, GL_GFX_H - 1);
    for (int y = y0; y <= y1; y++) {
        (void)span_(g, x, x, y, ink);
    }
}

void gl_gfx_rect(gl_gfx_t *g, int x, int y, int w, int h, gl_ink_t ink)
{
    int y0, y1;
    if (w <= 0 || h <= 0) {
        return;
    }
    x = coord_(x);
    y = coord_(y);
    w = coord_(w);
    h = coord_(h);
    y0 = gl_clampi(y, 0, GL_GFX_H);
    y1 = gl_clampi(y + h, 0, GL_GFX_H);
    for (int yy = y0; yy < y1; yy++) {
        (void)span_(g, x, x + w - 1, yy, ink);
    }
}

void gl_gfx_frame(gl_gfx_t *g, int x, int y, int w, int h, gl_ink_t ink)
{
    if (w <= 0 || h <= 0) {
        return;
    }
    x = coord_(x);
    y = coord_(y);
    w = coord_(w);
    h = coord_(h);
    gl_gfx_hline(g, x, x + w - 1, y, ink);
    gl_gfx_hline(g, x, x + w - 1, y + h - 1, ink);
    gl_gfx_vline(g, x, y, y + h - 1, ink);
    gl_gfx_vline(g, x + w - 1, y, y + h - 1, ink);
}

void gl_gfx_disc(gl_gfx_t *g, float cx, float cy, float r, gl_ink_t ink)
{
    int y0, y1;
    if (!(r >= 0.0f)) {
        return;
    }
    y0 = gl_clampi(clamp_ceil_(cy - r), 0, GL_GFX_H - 1);
    y1 = gl_clampi(clamp_floor_(cy + r), -1, GL_GFX_H - 1);
    for (int y = y0; y <= y1; y++) {
        float dy = (float)y - cy;
        float rem = r * r - dy * dy;
        if (rem >= 0.0f) {
            float half = sqrtf(rem);
            (void)span_(g, clamp_ceil_(cx - half), clamp_floor_(cx + half), y, ink);
        }
    }
}

void gl_gfx_arc(gl_gfx_t *g, float cx, float cy, float r_in, float r_out, float a0_rad,
                float a1_rad, gl_ink_t ink)
{
    float sweep = a1_rad - a0_rad;
    int y0, y1, x0, x1;
    if (!(r_out >= 0.0f) || !(sweep >= 0.0f)) {
        return;
    }
    y0 = gl_clampi(clamp_ceil_(cy - r_out), 0, GL_GFX_H - 1);
    y1 = gl_clampi(clamp_floor_(cy + r_out), -1, GL_GFX_H - 1);
    x0 = gl_clampi(clamp_ceil_(cx - r_out), 0, GL_GFX_W - 1);
    x1 = gl_clampi(clamp_floor_(cx + r_out), -1, GL_GFX_W - 1);
    for (int y = y0; y <= y1; y++) {
        for (int x = x0; x <= x1; x++) {
            float dx = (float)x - cx;
            float dy = (float)y - cy;
            float d2 = dx * dx + dy * dy;
            if (d2 < r_in * r_in || d2 > r_out * r_out) {
                continue;
            }
            if (sweep < GL_TWO_PI_F) {
                /* direction angle of this pixel, CCW from up */
                float a = atan2f(-dx, -dy) - a0_rad;
                a -= GL_TWO_PI_F * floorf(a / GL_TWO_PI_F); /* -> [0, 2 pi) */
                if (a > sweep) {
                    continue;
                }
            }
            (void)span_(g, x, x, y, ink);
        }
    }
}

void gl_gfx_triangle(gl_gfx_t *g, float x0, float y0, float x1, float y1, float x2, float y2,
                     gl_ink_t ink)
{
    const float vx[3] = { x0, x1, x2 };
    const float vy[3] = { y0, y1, y2 };
    float ymin = fminf(y0, fminf(y1, y2));
    float ymax = fmaxf(y0, fmaxf(y1, y2));
    int ya = gl_clampi(clamp_ceil_(ymin), 0, GL_GFX_H - 1);
    int yb = gl_clampi(clamp_floor_(ymax), -1, GL_GFX_H - 1);

    for (int y = ya; y <= yb; y++) {
        float fy = (float)y;
        float lo = 1e9f, hi = -1e9f;
        for (int e = 0; e < 3; e++) {
            float ax = vx[e], ay = vy[e];
            float bx = vx[(e + 1) % 3], by = vy[(e + 1) % 3];
            float emin = fminf(ay, by), emax = fmaxf(ay, by);
            if (fy < emin || fy > emax) {
                continue;
            }
            if (emax - emin < 1e-6f) { /* horizontal edge on this row */
                lo = fminf(lo, fminf(ax, bx));
                hi = fmaxf(hi, fmaxf(ax, bx));
            } else {
                float x = ax + (bx - ax) * (fy - ay) / (by - ay);
                lo = fminf(lo, x);
                hi = fmaxf(hi, x);
            }
        }
        if (hi >= lo) {
            (void)span_(g, clamp_ceil_(lo), clamp_floor_(hi), y, ink);
        }
    }
}

unsigned gl_gfx_line_angle(gl_gfx_t *g, float px, float py, float angle_rad,
                           float half_width_px, const gl_gfx_line_style_t *style,
                           gl_ink_t ink)
{
    /* Direction d = (-sin a, -cos a) (screen y is down); normal n = (cos a, -sin a).
     * Signed distance of pixel centre (x, y): (x - px) cos a - (y - py) sin a. */
    static const float dither_[4] = { -0.375f, 0.125f, -0.125f, 0.375f };
    const float ca = cosf(angle_rad);
    const float sa = sinf(angle_rad);
    const float dash_on = (style != NULL) ? style->dash_on_px : 0.0f;
    const float dash_off = (style != NULL) ? style->dash_off_px : 0.0f;
    const bool dither = (style != NULL) && style->edge_dither;
    const bool dashed = (dash_on > 0.0f && dash_off > 0.0f);
    const float period = dash_on + dash_off;
    /* Rows are scanned with a slightly wider band when per-pixel decisions
     * (dither or dashes) follow. */
    const float band = half_width_px + (dither ? 0.375f : 0.0f);
    unsigned count = 0;

    if (!(half_width_px >= 0.0f) || !(ca == ca) || !(sa == sa) || !(px == px) || !(py == py)) {
        return 0; /* negative width or NaN argument */
    }
    for (int y = 0; y < GL_GFX_H; y++) {
        float c = -((float)y - py) * sa;
        int xi0, xi1;
        if (g->clip_x0[y] > g->clip_x1[y]) {
            continue;
        }
        if (fabsf(ca) < 1e-6f) {
            if (fabsf(c) > band) {
                continue;
            }
            xi0 = 0;
            xi1 = GL_GFX_W - 1;
        } else {
            float xa = px + (-band - c) / ca;
            float xb = px + (band - c) / ca;
            xi0 = clamp_ceil_(fminf(xa, xb));
            xi1 = clamp_floor_(fmaxf(xa, xb));
        }
        if (xi0 < (int)g->clip_x0[y]) {
            xi0 = (int)g->clip_x0[y];
        }
        if (xi1 > (int)g->clip_x1[y]) {
            xi1 = (int)g->clip_x1[y];
        }
        if (xi0 > xi1) {
            continue;
        }
        if (!dashed && !dither) {
            count += span_(g, xi0, xi1, y, ink);
            continue;
        }
        for (int x = xi0; x <= xi1; x++) {
            float rx = (float)x - px;
            if (dither) {
                float dist = rx * ca + c;
                float hw = half_width_px + dither_[(unsigned)(x + 3 * y) & 3u];
                if (fabsf(dist) > hw) {
                    continue;
                }
            }
            if (dashed) {
                /* along-line coordinate from (px, py), one dash centred there */
                float s = -rx * sa - ((float)y - py) * ca + 0.5f * dash_on;
                float m = s - period * floorf(s / period);
                if (m >= dash_on) {
                    continue;
                }
            }
            count += span_(g, x, x, y, ink);
        }
    }
    return count;
}

unsigned gl_gfx_segment(gl_gfx_t *g, float x0, float y0, float x1, float y1,
                        float half_width_px, gl_ink_t ink)
{
    float dx = x1 - x0, dy = y1 - y0;
    float len = sqrtf(dx * dx + dy * dy);
    unsigned count = 0;
    int ya, yb, xa, xb;

    if (!(half_width_px >= 0.0f) || !(len >= 1e-6f) || !(x0 == x0) || !(y0 == y0)) {
        return 0; /* also rejects NaN coordinates */
    }
    dx /= len;
    dy /= len;
    ya = gl_clampi(clamp_floor_(fminf(y0, y1) - half_width_px), 0, GL_GFX_H - 1);
    yb = gl_clampi(clamp_ceil_(fmaxf(y0, y1) + half_width_px), -1, GL_GFX_H - 1);
    xa = gl_clampi(clamp_floor_(fminf(x0, x1) - half_width_px), 0, GL_GFX_W - 1);
    xb = gl_clampi(clamp_ceil_(fmaxf(x0, x1) + half_width_px), -1, GL_GFX_W - 1);
    for (int y = ya; y <= yb; y++) {
        for (int x = xa; x <= xb; x++) {
            float rx = (float)x - x0, ry = (float)y - y0;
            float along = rx * dx + ry * dy;
            float across = rx * dy - ry * dx;
            if (along >= 0.0f && along <= len && fabsf(across) <= half_width_px) {
                count += span_(g, x, x, y, ink);
            }
        }
    }
    return count;
}

void gl_gfx_arrow(gl_gfx_t *g, float x, float y, float angle_rad, float len_px, float head_px,
                  float half_width_px, gl_ink_t ink)
{
    float dx = -sinf(angle_rad), dy = -cosf(angle_rad);
    float tx = x + len_px * dx, ty = y + len_px * dy;       /* tip */
    float bx = tx - head_px * dx, by = ty - head_px * dy;   /* head base centre */
    float hw = 0.6f * head_px;
    (void)gl_gfx_segment(g, x, y, bx, by, half_width_px, ink);
    gl_gfx_triangle(g, tx, ty, bx - hw * dy, by + hw * dx, bx + hw * dy, by - hw * dx, ink);
}

void gl_gfx_aim_line_styled(gl_gfx_t *g, float aim_rad, float ball_az_rad, float half_width_px,
                            bool tentative, gl_gfx_aim_info_t *info)
{
    /* Ball centre in screen coordinates (x right = marker +x, y down =
     * marker -y): a marker direction at angle t CCW from forward is the
     * screen vector (-sin t, -cos t).  For ball_az = 0 the ball is straight
     * "up" from the centre. */
    const float bx = GL_GFX_CENTRE_F - GL_CFG_BALL_CENTRE_Y_PX * sinf(ball_az_rad);
    const float by = GL_GFX_CENTRE_F - GL_CFG_BALL_CENTRE_Y_PX * cosf(ball_az_rad);
    const float r = 0.5f * (float)GL_CFG_LCD_CLIP_DIA_PX;
    /* With n = (cos a, -sin a) the screen centre lies at signed distance
     * n . (centre - ball) = BALL_Y * sin(az - a) from the line, so the line
     * passes BALL_Y * sin(a - az) to the RIGHT of the centre: for the ball
     * straight ahead and a positive (aim-left) angle that is the backward
     * extension of a start line that goes forward-left. */
    float offset = GL_CFG_BALL_CENTRE_Y_PX * sinf(aim_rad - ball_az_rad);
    float rem = r * r - offset * offset;
    float chord = (rem > 0.0f) ? 2.0f * sqrtf(rem) : 0.0f;
    gl_gfx_aim_info_t local;

    local.offset_px = offset;
    local.chord_px = chord;
    /* cos(aim - ball_az) <= 0 would mean the putt starts back across the
     * marker: never on screen. */
    if (chord >= GL_GFX_AIM_MIN_CHORD_PX && cosf(aim_rad - ball_az_rad) > 0.0f) {
        local.on_screen = true;
        const gl_gfx_line_style_t solid = { 0.0f, 0.0f, true };
        const gl_gfx_line_style_t tent = { GL_GFX_AIM_TENTATIVE_DASH_PX,
                                           GL_GFX_AIM_TENTATIVE_GAP_PX, true };
        local.pixels = gl_gfx_line_angle(g, bx, by, aim_rad, half_width_px,
                                         tentative ? &tent : &solid, GL_INK_BLACK);
    } else {
        /* The true line leaves the aperture: the PARALLEL through the screen
         * centre, in the style the true line would have had (the direction
         * is what the golfer copies; solid stays solid, tentative stays
         * tentative). */
        local.on_screen = false;
        const gl_gfx_line_style_t solid = { 0.0f, 0.0f, true };
        const gl_gfx_line_style_t tent = { GL_GFX_AIM_TENTATIVE_DASH_PX,
                                           GL_GFX_AIM_TENTATIVE_GAP_PX, true };
        local.pixels = gl_gfx_line_angle(g, GL_GFX_CENTRE_F, GL_GFX_CENTRE_F, aim_rad,
                                         half_width_px, tentative ? &tent : &solid, GL_INK_BLACK);
    }
    if (info != NULL) {
        *info = local;
    }
}

void gl_gfx_aim_line_at(gl_gfx_t *g, float aim_rad, float ball_az_rad, float half_width_px,
                        gl_gfx_aim_info_t *info)
{
    gl_gfx_aim_line_styled(g, aim_rad, ball_az_rad, half_width_px, false, info);
}

void gl_gfx_aim_line(gl_gfx_t *g, float aim_rad, float half_width_px, gl_gfx_aim_info_t *info)
{
    gl_gfx_aim_line_at(g, aim_rad, 0.0f, half_width_px, info);
}

/* ---- text -------------------------------------------------------------- */

static unsigned glyph_index_(char ch)
{
    unsigned c = (unsigned char)ch;
    if (c >= (unsigned)'a' && c <= (unsigned)'z') {
        c = c - (unsigned)'a' + (unsigned)'A';
    }
    if (c < (unsigned)GL_FONT_FIRST || c > (unsigned)GL_FONT_LAST) {
        c = (unsigned)'?';
    }
    return c - (unsigned)GL_FONT_FIRST;
}

int gl_gfx_text(gl_gfx_t *g, int x, int y, const char *s, int scale, gl_ink_t ink)
{
    /* one glyph at scale 32 is wider than the screen */
    scale = gl_clampi(scale, 1, GL_GFX_TEXT_SCALE_MAX);
    x = coord_(x);
    y = coord_(y);
    for (int n = 0; *s != '\0' && n < GL_GFX_TEXT_LEN_MAX; s++, n++) {
        const uint8_t *rows = gl_font5x7[glyph_index_(*s)];
        if (x > GL_GFX_W) {
            break; /* nothing further can be visible */
        }
        for (int r = 0; r < GL_FONT_H; r++) {
            uint8_t bits = rows[r];
            for (int c = 0; c < GL_FONT_W; c++) {
                if ((bits & (uint8_t)(0x10u >> c)) != 0u) {
                    gl_gfx_rect(g, x + c * scale, y + r * scale, scale, scale, ink);
                }
            }
        }
        x += GL_FONT_ADVANCE * scale;
    }
    return x;
}

int gl_gfx_text_width(const char *s, int scale)
{
    /* bounded scan: a string that could be visible is far shorter */
    int n = 0;
    while (n < GL_GFX_TEXT_LEN_MAX && s[n] != '\0') {
        n++;
    }
    scale = gl_clampi(scale, 1, GL_GFX_TEXT_SCALE_MAX);
    return (n == 0) ? 0 : (n * GL_FONT_ADVANCE - 1) * scale;
}

void gl_gfx_text_centred(gl_gfx_t *g, int cx, int y, const char *s, int scale, gl_ink_t ink)
{
    (void)gl_gfx_text(g, coord_(cx) - gl_gfx_text_width(s, scale) / 2, y, s, scale, ink);
}

/* Seven-segment masks, bit 0 = a (top) ... bit 6 = g (middle). */
static const uint8_t seg7_[10] = { 0x3Fu, 0x06u, 0x5Bu, 0x4Fu, 0x66u,
                                   0x6Du, 0x7Du, 0x07u, 0x7Fu, 0x6Fu };

static void big_metrics_(int h, int *w, int *t, int *gap)
{
    h = gl_clampi(h, 9, GL_GFX_BIG_H_MAX);
    *w = (h + 1) / 2;
    *t = (h / 6 < 2) ? 2 : h / 6;
    *gap = *t;
}

int gl_gfx_big_number_width(const char *s, int h_px)
{
    int w, t, gap, x = 0;
    big_metrics_(h_px, &w, &t, &gap);
    for (int n = 0; *s != '\0' && n < GL_GFX_TEXT_LEN_MAX; s++, n++) {
        if (*s >= '0' && *s <= '9') {
            x += w + gap;
        } else if (*s == '-') {
            x += w + gap;
        } else if (*s == '.') {
            x += t + gap;
        } else if (*s == ' ') {
            x += w / 2 + gap;
        }
    }
    return (x > 0) ? (x - gap) : 0;
}

int gl_gfx_big_number(gl_gfx_t *g, int x, int y, const char *s, int h_px, gl_ink_t ink)
{
    int w, t, gap;
    const int h = gl_clampi(h_px, 9, GL_GFX_BIG_H_MAX);
    big_metrics_(h, &w, &t, &gap);
    x = coord_(x);
    y = coord_(y);
    {
        const int mid = (h - t) / 2;    /* top of the middle bar */
        const int half = h / 2;         /* split between upper and lower verticals */
        for (; *s != '\0'; s++) {
            uint8_t m = 0;
            if (x > GL_GFX_W) {
                break; /* nothing further can be visible */
            }
            if (*s >= '0' && *s <= '9') {
                m = seg7_[*s - '0'];
            } else if (*s == '-') {
                m = 0x40u;
            } else if (*s == '.') {
                gl_gfx_rect(g, x, y + h - t, t, t, ink);
                x += t + gap;
                continue;
            } else if (*s == ' ') {
                x += w / 2 + gap;
                continue;
            } else {
                continue;
            }
            if ((m & 0x01u) != 0u) { /* a */
                gl_gfx_rect(g, x + 1, y, w - 2, t, ink);
            }
            if ((m & 0x02u) != 0u) { /* b */
                gl_gfx_rect(g, x + w - t, y + 1, t, half - 1, ink);
            }
            if ((m & 0x04u) != 0u) { /* c */
                gl_gfx_rect(g, x + w - t, y + half, t, h - half - 1, ink);
            }
            if ((m & 0x08u) != 0u) { /* d */
                gl_gfx_rect(g, x + 1, y + h - t, w - 2, t, ink);
            }
            if ((m & 0x10u) != 0u) { /* e */
                gl_gfx_rect(g, x, y + half, t, h - half - 1, ink);
            }
            if ((m & 0x20u) != 0u) { /* f */
                gl_gfx_rect(g, x, y + 1, t, half - 1, ink);
            }
            if ((m & 0x40u) != 0u) { /* g */
                gl_gfx_rect(g, x + 1, y + mid, w - 2, t, ink);
            }
            x += w + gap;
        }
    }
    return x;
}

/* ---- icons ------------------------------------------------------------- */

void gl_gfx_icon(gl_gfx_t *g, int x, int y, gl_icon_t icon, gl_ink_t ink)
{
    const gl_icon_bitmap_t *bm;
    if ((unsigned)icon >= (unsigned)GL_ICON_COUNT) {
        return;
    }
    bm = &gl_icons[icon];
    x = coord_(x);
    y = coord_(y);
    for (int r = 0; r < (int)bm->h; r++) {
        uint16_t bits = bm->rows[r];
        for (int c = 0; c < (int)bm->w; c++) {
            if ((bits & (uint16_t)(0x8000u >> c)) != 0u) {
                (void)span_(g, x + c, x + c, y + r, ink);
            }
        }
    }
}

void gl_gfx_battery(gl_gfx_t *g, int x, int y, int percent)
{
    int fill;
    percent = gl_clampi(percent, 0, 100);
    x = coord_(x);
    y = coord_(y);
    fill = (percent * 13 + 50) / 100;
    gl_gfx_frame(g, x, y, 17, 9, GL_INK_BLACK);
    gl_gfx_rect(g, x + 17, y + 2, 2, 5, GL_INK_BLACK);
    gl_gfx_rect(g, x + 1, y + 1, 15, 7, GL_INK_WHITE);
    gl_gfx_rect(g, x + 2, y + 2, fill, 5, GL_INK_BLACK);
}

void gl_gfx_conf_bar(gl_gfx_t *g, int x, int y, int filled, int total)
{
    total = gl_clampi(total, 0, 10);
    filled = gl_clampi(filled, 0, total);
    x = coord_(x);
    y = coord_(y);
    for (int i = 0; i < total; i++) {
        int bx = x + i * 7;
        if (i < filled) {
            gl_gfx_rect(g, bx, y, 5, 6, GL_INK_BLACK);
        } else {
            gl_gfx_rect(g, bx, y, 5, 6, GL_INK_WHITE);
            gl_gfx_frame(g, bx, y, 5, 6, GL_INK_BLACK);
        }
    }
}
