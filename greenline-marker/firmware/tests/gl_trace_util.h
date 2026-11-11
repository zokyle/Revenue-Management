/*
 * gl_trace_util.h - helpers for tests that inspect the host simulator's
 * bus / pin trace (hal/host/gl_sim.h).  Header only.
 */
#ifndef GL_TRACE_UTIL_H
#define GL_TRACE_UTIL_H

#include <string.h>

#include "gl_sim.h"

/** Index of the first record at or after `from` with the given type (and,
 *  if a >= 0, the given `a` field); -1 if none. */
static inline long tr_find(size_t from, gl_sim_tr_type_t type, int a)
{
    const size_t n = gl_sim_trace_count();
    for (size_t i = from; i < n; i++) {
        const gl_sim_trace_t *t = gl_sim_trace_at(i);
        if (t->type == (uint8_t)type && (a < 0 || t->a == (uint8_t)a)) {
            return (long)i;
        }
    }
    return -1;
}

/** Index of the first GPIO_WRITE of `pin` to `level` at or after `from`. */
static inline long tr_find_write(size_t from, gl_pin_t pin, bool level)
{
    const size_t n = gl_sim_trace_count();
    for (size_t i = from; i < n; i++) {
        const gl_sim_trace_t *t = gl_sim_trace_at(i);
        if (t->type == (uint8_t)GL_SIM_TR_GPIO_WRITE && t->a == (uint8_t)pin &&
            t->b == (level ? 1u : 0u)) {
            return (long)i;
        }
    }
    return -1;
}

/** Index of the first GPIO_MODE of `pin` to `mode` at or after `from`. */
static inline long tr_find_mode(size_t from, gl_pin_t pin, gl_pin_mode_t mode)
{
    const size_t n = gl_sim_trace_count();
    for (size_t i = from; i < n; i++) {
        const gl_sim_trace_t *t = gl_sim_trace_at(i);
        if (t->type == (uint8_t)GL_SIM_TR_GPIO_MODE && t->a == (uint8_t)pin &&
            t->b == (uint16_t)mode) {
            return (long)i;
        }
    }
    return -1;
}

/** Number of records of a type in [from, to). */
static inline size_t tr_count(size_t from, size_t to, gl_sim_tr_type_t type)
{
    size_t c = 0;
    for (size_t i = from; i < to && i < gl_sim_trace_count(); i++) {
        if (gl_sim_trace_at(i)->type == (uint8_t)type) {
            c++;
        }
    }
    return c;
}

/** Concatenate the transmitted bytes of all SPI transfers to `dev` in
 *  [from, to) into out[cap].  Returns the number of bytes (may exceed cap:
 *  then only cap were stored). */
static inline size_t tr_spi_bytes(size_t from, size_t to, gl_sim_dev_t dev, uint8_t *out, size_t cap)
{
    size_t n = 0;
    for (size_t i = from; i < to && i < gl_sim_trace_count(); i++) {
        const gl_sim_trace_t *t = gl_sim_trace_at(i);
        if (t->type != (uint8_t)GL_SIM_TR_SPI_XFER || t->b != (uint16_t)dev) {
            continue;
        }
        const uint8_t *p = gl_sim_trace_bytes(t);
        for (uint32_t k = 0; k < t->c; k++) {
            if (n < cap && p != NULL) {
                out[n] = p[k];
            }
            n++;
        }
    }
    return n;
}

#endif /* GL_TRACE_UTIL_H */
