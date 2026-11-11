/*
 * gl_fmt.h - minimal number-to-text formatting for the display (no stdio,
 * no double).  All functions NUL-terminate within `cap` and return the
 * number of characters written (excluding the NUL).
 */
#ifndef GL_FMT_H
#define GL_FMT_H

#include "gl_types.h"

/** Decimal integer, optional leading '-'. */
size_t gl_fmt_int(char *out, size_t cap, int32_t v);

/** Fixed-point decimal with 0..3 decimals, rounded half away from zero.
 *  |v| is clamped to 9999999.  Example: (1.25, 1) -> "1.3", (-0.04, 1) -> "0.0". */
size_t gl_fmt_fixed(char *out, size_t cap, float v, unsigned decimals);

/** Append `s` to the NUL-terminated string in `out` (truncating). Returns
 *  the new length. */
size_t gl_fmt_append(char *out, size_t cap, const char *s);

#endif /* GL_FMT_H */
