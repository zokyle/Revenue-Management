/*
 * gl_buf.h - bounded little-endian writer / reader for record and frame
 * (de)serialisation.  No struct packing is relied on anywhere: every stored
 * or transmitted record is built field by field with these helpers.
 *
 * Both cursors are "sticky": after an overflow / underflow the `ok` flag is
 * false, further writes are ignored and further reads return 0, so a caller
 * checks once at the end.
 */
#ifndef GL_BUF_H
#define GL_BUF_H

#include <string.h>

#include "gl_types.h"

typedef struct {
    uint8_t *p;
    size_t cap;
    size_t len;
    bool ok;
} gl_wr_t;

typedef struct {
    const uint8_t *p;
    size_t len;
    size_t pos;
    bool ok;
} gl_rd_t;

/** Start writing into buf[cap]. */
static inline void gl_wr_init(gl_wr_t *w, uint8_t *buf, size_t cap)
{
    w->p = buf;
    w->cap = cap;
    w->len = 0;
    w->ok = true;
}

/** Append n raw bytes; on overflow nothing is written and w->ok becomes false. */
static inline void gl_wr_bytes(gl_wr_t *w, const void *src, size_t n)
{
    if (!w->ok || n > w->cap - w->len) {
        w->ok = false;
        return;
    }
    if (n > 0u) {
        memcpy(w->p + w->len, src, n);
    }
    w->len += n;
}

/** Append one value, little-endian: u8, u16, i16, u32, IEEE-754 float. */
static inline void gl_wr_u8(gl_wr_t *w, uint8_t v)
{
    gl_wr_bytes(w, &v, 1);
}
static inline void gl_wr_u16(gl_wr_t *w, uint16_t v)
{
    uint8_t b[2];
    gl_put_u16(b, v);
    gl_wr_bytes(w, b, 2);
}
static inline void gl_wr_i16(gl_wr_t *w, int16_t v)
{
    gl_wr_u16(w, (uint16_t)v);
}
static inline void gl_wr_u32(gl_wr_t *w, uint32_t v)
{
    uint8_t b[4];
    gl_put_u32(b, v);
    gl_wr_bytes(w, b, 4);
}
static inline void gl_wr_f32(gl_wr_t *w, float v)
{
    uint8_t b[4];
    gl_put_f32(b, v);
    gl_wr_bytes(w, b, 4);
}

/** Start reading buf[len]. */
static inline void gl_rd_init(gl_rd_t *r, const uint8_t *buf, size_t len)
{
    r->p = buf;
    r->len = len;
    r->pos = 0;
    r->ok = true;
}

/** Bytes not yet read (0 after an underflow). */
static inline size_t gl_rd_left(const gl_rd_t *r)
{
    return r->ok ? (r->len - r->pos) : 0u;
}

/** Read n raw bytes; on underflow dst is zero-filled and r->ok becomes false. */
static inline void gl_rd_bytes(gl_rd_t *r, void *dst, size_t n)
{
    if (!r->ok || n > r->len - r->pos) {
        r->ok = false;
        if (n > 0u) {
            memset(dst, 0, n);
        }
        return;
    }
    if (n > 0u) {
        memcpy(dst, r->p + r->pos, n);
    }
    r->pos += n;
}

/** Read one value, little-endian: u8, u16, i16, u32, IEEE-754 float (0 on underflow). */
static inline uint8_t gl_rd_u8(gl_rd_t *r)
{
    uint8_t v;
    gl_rd_bytes(r, &v, 1);
    return v;
}
static inline uint16_t gl_rd_u16(gl_rd_t *r)
{
    uint8_t b[2];
    gl_rd_bytes(r, b, 2);
    return gl_get_u16(b);
}
static inline int16_t gl_rd_i16(gl_rd_t *r)
{
    return (int16_t)gl_rd_u16(r);
}
static inline uint32_t gl_rd_u32(gl_rd_t *r)
{
    uint8_t b[4];
    gl_rd_bytes(r, b, 4);
    return gl_get_u32(b);
}
static inline float gl_rd_f32(gl_rd_t *r)
{
    uint8_t b[4];
    gl_rd_bytes(r, b, 4);
    return gl_get_f32(b);
}

#endif /* GL_BUF_H */
