/*
 * gl_gfx.h - 1-bit-per-pixel graphics for the 128 x 128 memory LCD.
 *
 * FRAMEBUFFER FORMAT (contract with drivers/ls013b7dh03)
 *   px[y * 16 + (x >> 3)], bit (x & 7); bit value 1 = WHITE (reflective),
 *   0 = BLACK (ink).  Bit 0 of a byte is its leftmost pixel, so a row can be
 *   sent to the LCD as-is on an LSB-first SPI bus: the first bit on the wire
 *   is the leftmost pixel.  gl_gfx_row() returns the 16 bytes of one line.
 *
 * SCREEN COORDINATES
 *   x right (0..127), y DOWN (0..127); integer (x, y) is the CENTRE of a
 *   pixel, so the screen centre is (63.5, 63.5).  Screen +x is marker +x;
 *   screen "up" (-y) is marker +y (forward, toward the ball and the hole).
 *   Panel mounting flips are the LCD driver's business (gl_provisional.h).
 *
 * ROUND APERTURE
 *   The display is seen through a 22 mm round aperture.  With the clip
 *   enabled (default) no drawing call can touch a pixel any part of which
 *   lies outside a circle of GL_CFG_LCD_CLIP_DIA_PX (122) pixels diameter
 *   centred on the screen.  gl_gfx_clear() ignores the clip.
 *
 * ANGLES
 *   Radians, counter-clockwise positive, measured from "up" on the screen
 *   (marker forward).  Angle 0 points up, +90 deg points left.
 *
 * RAM: sizeof(gl_gfx_t) = 2305 bytes (2048 framebuffer + 256 clip table).
 * Worst-case stack of any function here: under 250 bytes including callees
 * (arm-none-eabi-gcc -Os).  No recursion, no allocation.
 */
#ifndef GL_GFX_H_INCLUDED
#define GL_GFX_H_INCLUDED

#include "gl_types.h"

#define GL_GFX_W 128
#define GL_GFX_H 128
#define GL_GFX_STRIDE 16
#define GL_GFX_BYTES (GL_GFX_STRIDE * GL_GFX_H)

#define GL_GFX_CENTRE_F 63.5f

typedef enum {
    GL_INK_BLACK = 0, /**< draw: pixel becomes dark */
    GL_INK_WHITE = 1  /**< erase: pixel becomes reflective white */
} gl_ink_t;

typedef struct {
    uint8_t px[GL_GFX_BYTES];
    uint8_t clip_x0[GL_GFX_H]; /**< first drawable column of each row */
    uint8_t clip_x1[GL_GFX_H]; /**< last drawable column; x0 > x1 means empty row */
    bool clip_on;
} gl_gfx_t;

/* ---- basics ------------------------------------------------------------ */

/** White screen, round clip enabled. */
void gl_gfx_init(gl_gfx_t *g);

/** Enable / disable the round clip (disabled = full 128 x 128 square). */
void gl_gfx_set_clip(gl_gfx_t *g, bool round_clip);

/** Fill the whole buffer, ignoring the clip. */
void gl_gfx_clear(gl_gfx_t *g, gl_ink_t ink);

/** True if pixel (x, y) may be drawn under the current clip. */
bool gl_gfx_in_clip(const gl_gfx_t *g, int x, int y);

/** Set one pixel (ignored outside the clip / screen). */
void gl_gfx_pixel(gl_gfx_t *g, int x, int y, gl_ink_t ink);

/** Read one pixel: true = white.  Outside the screen returns true. */
bool gl_gfx_get(const gl_gfx_t *g, int x, int y);

/** The 16 bytes of line y (0..127) in LCD bit order. */
const uint8_t *gl_gfx_row(const gl_gfx_t *g, int y);

/** Number of black pixels on the whole screen (tests, diagnostics). */
unsigned gl_gfx_count_black(const gl_gfx_t *g);

/**
 * Compare with a shadow copy of what the LCD currently shows.  Writes the
 * indices of differing lines (ascending) to `rows` and returns their count
 * (0..128).  The LCD driver sends exactly these lines and then copies px to
 * its shadow.
 */
unsigned gl_gfx_changed_rows(const gl_gfx_t *g, const uint8_t shadow[GL_GFX_BYTES],
                             uint8_t rows[GL_GFX_H]);

/* ---- primitives -------------------------------------------------------- */

/** Integer coordinates and sizes given to the primitives below are clamped
 *  to +-GL_GFX_COORD_LIMIT pixels, text scale to 1..GL_GFX_TEXT_SCALE_MAX,
 *  large-digit height to 9..GL_GFX_BIG_H_MAX and strings to
 *  GL_GFX_TEXT_LEN_MAX characters.  Every value that could put ink on the
 *  128 x 128 screen is far inside these limits; they exist so that no
 *  argument, however extreme, can overflow an int. */
#define GL_GFX_COORD_LIMIT 1000000
#define GL_GFX_TEXT_SCALE_MAX 32
#define GL_GFX_BIG_H_MAX 256
#define GL_GFX_TEXT_LEN_MAX 64

/** Horizontal run x0..x1 inclusive (any order). */
void gl_gfx_hline(gl_gfx_t *g, int x0, int x1, int y, gl_ink_t ink);
/** Vertical run y0..y1 inclusive (any order). */
void gl_gfx_vline(gl_gfx_t *g, int x, int y0, int y1, gl_ink_t ink);
/** Filled rectangle, top-left (x, y), size w x h. */
void gl_gfx_rect(gl_gfx_t *g, int x, int y, int w, int h, gl_ink_t ink);
/** One-pixel rectangle outline. */
void gl_gfx_frame(gl_gfx_t *g, int x, int y, int w, int h, gl_ink_t ink);
/** Filled disc: pixels whose centre is within r of (cx, cy). */
void gl_gfx_disc(gl_gfx_t *g, float cx, float cy, float r, gl_ink_t ink);
/** Ring: pixels with r_in <= distance <= r_out, restricted to directions
 *  between a0 and a1 (rad, CCW from up, a1 >= a0; a1 - a0 >= 2 pi = full ring). */
void gl_gfx_arc(gl_gfx_t *g, float cx, float cy, float r_in, float r_out, float a0_rad,
                float a1_rad, gl_ink_t ink);
/** Filled triangle with real-valued vertices (pixel-centre sampling). */
void gl_gfx_triangle(gl_gfx_t *g, float x0, float y0, float x1, float y1, float x2, float y2,
                     gl_ink_t ink);

/** Optional style of gl_gfx_line_angle(). */
typedef struct {
    float dash_on_px;   /**< dashed line: length of a dash (0 = solid) */
    float dash_off_px;  /**< dashed line: length of a gap (0 = solid) */
    /** Edge dithering.  Without it a pixel is drawn when its centre is within
     *  half_width of the ideal line, which leaves a dead zone: a line within
     *  about 0.5 degree of a pixel axis can render exactly on-axis.  With it
     *  the half width is varied by -3/8, -1/8, +1/8, +3/8 px in a 4-pixel
     *  ordered pattern along the edges, so the edges encode the direction to
     *  a quarter of a pixel at the cost of slightly rough edges. */
    bool edge_dither;
} gl_gfx_line_style_t;

/**
 * Thick straight line through the real-valued point (px, py) in direction
 * `angle_rad`, extended to the clip boundary in both directions.  A pixel
 * is drawn when its centre is within `half_width_px` of the ideal line, so
 * the direction is carried by the stair-step pattern along the whole length
 * and is NOT quantised to pixel end points.
 *
 * style: NULL = solid, no edge dithering.  A dashed line has one dash
 * centred on (px, py).
 *
 * Returns the number of pixels drawn.
 */
unsigned gl_gfx_line_angle(gl_gfx_t *g, float px, float py, float angle_rad,
                           float half_width_px, const gl_gfx_line_style_t *style,
                           gl_ink_t ink);

/** Thick segment between two real-valued points (butt ends).  Returns the
 *  number of pixels drawn. */
unsigned gl_gfx_segment(gl_gfx_t *g, float x0, float y0, float x1, float y1,
                        float half_width_px, gl_ink_t ink);

/** Arrow from (x, y): shaft of length `len_px` in direction `angle_rad`
 *  with a filled head of size `head_px`. */
void gl_gfx_arrow(gl_gfx_t *g, float x, float y, float angle_rad, float len_px, float head_px,
                  float half_width_px, gl_ink_t ink);

/* ---- aim line ---------------------------------------------------------- */

/** Minimum chord (px) inside the clip circle for the true aim line to be
 *  drawn; below this the line is reported as off-screen. */
#define GL_GFX_AIM_MIN_CHORD_PX 40.0f

typedef struct {
    bool on_screen;   /**< true: the true line was drawn */
    float offset_px;  /**< signed lateral distance of the line from the screen centre, + = right */
    float chord_px;   /**< length of the line inside the clip circle (0 if it misses) */
    unsigned pixels;  /**< pixels drawn */
} gl_gfx_aim_info_t;

/**
 * Draw the aim line: the backward extension, across the screen, of the
 * putt's start line.  The start line passes through the BALL centre, which
 * is GL_CFG_BALL_CENTRE_Y_PX above the screen centre on the forward axis
 * (off-screen), in direction `aim_rad` (CCW from marker forward: + = aim
 * left of where the visor points).
 *
 * The true line is drawn with edge dithering (see gl_gfx_line_style_t).
 *
 * If the line's chord inside the clip circle is shorter than
 * GL_GFX_AIM_MIN_CHORD_PX (aim more than about 13.5 deg off the visor axis)
 * the true line is NOT drawn; instead a DASHED parallel line through the
 * screen centre is drawn, info->on_screen is false, and the caller should
 * add an arrow on the side given by the sign of info->offset_px.
 */
void gl_gfx_aim_line(gl_gfx_t *g, float aim_rad, float half_width_px, gl_gfx_aim_info_t *info);

/**
 * The same with the ball centre in a general direction: `ball_az_rad` is the
 * direction from the marker centre to the ball centre, CCW from marker
 * forward, in the marker's CURRENT frame (0 = straight ahead, the normal
 * case and what gl_gfx_aim_line() draws).  After the 180-degree spin of a
 * Precision Read the marker faces away from the hole and the ball position
 * lies BEHIND it (ball_az_rad near pi, aim_rad near pi): the line is then
 * drawn through that point.  The true line is drawn when its chord is long
 * enough and the putt starts away from the marker (cos(aim - ball_az) > 0).
 * info->offset_px is positive when the line passes to the right of the
 * screen centre.
 */
void gl_gfx_aim_line_at(gl_gfx_t *g, float aim_rad, float ball_az_rad, float half_width_px,
                        gl_gfx_aim_info_t *info);

/* ---- text -------------------------------------------------------------- */

#define GL_FONT_W 5
#define GL_FONT_H 7
#define GL_FONT_ADVANCE 6
#define GL_FONT_FIRST 0x20
#define GL_FONT_LAST 0x5F
#define GL_FONT_GLYPHS (GL_FONT_LAST - GL_FONT_FIRST + 1)

/** Generated glyph table (gl_font_data.c). */
extern const uint8_t gl_font5x7[GL_FONT_GLYPHS][GL_FONT_H];

/** Draw a string with the 5x7 font, top-left at (x, y), integer `scale`
 *  >= 1.  Lower case is drawn as upper case; unknown characters as '?'.
 *  Returns the x coordinate after the last character. */
int gl_gfx_text(gl_gfx_t *g, int x, int y, const char *s, int scale, gl_ink_t ink);

/** Pixel width of a string at `scale` (no trailing gap). */
int gl_gfx_text_width(const char *s, int scale);

/** Draw a string horizontally centred on cx. */
void gl_gfx_text_centred(gl_gfx_t *g, int cx, int y, const char *s, int scale, gl_ink_t ink);

/**
 * Large-digit font: seven-segment style numerals of height `h_px` (>= 9),
 * digit width = h/2 rounded, stroke = max(2, h/6).  Supports "0123456789",
 * '-', '.', ' ' and '%'-less numeric text; other characters are skipped.
 * Top-left at (x, y).  Returns the x coordinate after the last character.
 */
int gl_gfx_big_number(gl_gfx_t *g, int x, int y, const char *s, int h_px, gl_ink_t ink);

/** Pixel width gl_gfx_big_number() would use. */
int gl_gfx_big_number_width(const char *s, int h_px);

/* ---- icons ------------------------------------------------------------- */

typedef enum {
    GL_ICON_FLAG = 0,
    GL_ICON_NOFLAG,
    GL_ICON_BOLT,
    GL_ICON_CHECK,
    GL_ICON_CROSS,
    GL_ICON_WARN,
    GL_ICON_USB,
    GL_ICON_COUNT
} gl_icon_t;

typedef struct {
    uint8_t w, h;
    const uint16_t *rows; /**< bit 15 = leftmost column */
} gl_icon_bitmap_t;

/** Generated icon table (gl_font_data.c). */
extern const gl_icon_bitmap_t gl_icons[GL_ICON_COUNT];

/** Draw a bitmap icon, top-left at (x, y). */
void gl_gfx_icon(gl_gfx_t *g, int x, int y, gl_icon_t icon, gl_ink_t ink);

/** Battery symbol 19 x 9 px, top-left at (x, y): outline, terminal nub and
 *  a fill proportional to `percent` (0..100). */
void gl_gfx_battery(gl_gfx_t *g, int x, int y, int percent);

/** Confidence bar: `total` boxes of 5 x 6 px with 2 px gaps, the first
 *  `filled` solid.  Top-left at (x, y).  Width = total * 7 - 2. */
void gl_gfx_conf_bar(gl_gfx_t *g, int x, int y, int filled, int total);

#endif /* GL_GFX_H_INCLUDED */
