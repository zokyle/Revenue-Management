/* gl_fmt.c - see gl_fmt.h. */
#include "gl_fmt.h"

#include <string.h>

size_t gl_fmt_int(char *out, size_t cap, int32_t v)
{
    char tmp[12];
    size_t n = 0;
    uint32_t u = (v < 0) ? (uint32_t)(-(int64_t)v) : (uint32_t)v;
    size_t len = 0;

    if (cap == 0u) {
        return 0;
    }
    do {
        tmp[n++] = (char)('0' + (int)(u % 10u));
        u /= 10u;
    } while (u != 0u && n < sizeof(tmp));
    if (v < 0 && len + 1u < cap) {
        out[len++] = '-';
    }
    while (n > 0u && len + 1u < cap) {
        out[len++] = tmp[--n];
    }
    out[len] = '\0';
    return len;
}

size_t gl_fmt_fixed(char *out, size_t cap, float v, unsigned decimals)
{
    static const int32_t pow10[4] = { 1, 10, 100, 1000 };
    size_t len = 0;
    bool neg;
    int32_t scaled, ip, fp;

    if (cap == 0u) {
        return 0;
    }
    if (decimals > 3u) {
        decimals = 3u;
    }
    if (!(v == v)) { /* NaN */
        out[0] = '\0';
        return gl_fmt_append(out, cap, "--");
    }
    v = gl_clampf(v, -9999999.0f / (float)pow10[decimals], 9999999.0f / (float)pow10[decimals]);
    neg = (v < 0.0f);
    scaled = (int32_t)(((neg ? -v : v) * (float)pow10[decimals]) + 0.5f);
    if (scaled == 0) {
        neg = false; /* no "-0.0" */
    }
    ip = scaled / pow10[decimals];
    fp = scaled % pow10[decimals];
    if (neg && len + 1u < cap) {
        out[len++] = '-';
    }
    out[len] = '\0';
    len += gl_fmt_int(out + len, cap - len, ip);
    if (decimals > 0u && len + 1u < cap) {
        out[len++] = '.';
        for (unsigned d = decimals; d > 0u && len + 1u < cap; d--) {
            out[len++] = (char)('0' + (int)((fp / pow10[d - 1u]) % 10));
        }
        out[len] = '\0';
    }
    return len;
}

size_t gl_fmt_append(char *out, size_t cap, const char *s)
{
    size_t len;
    if (cap == 0u) {
        return 0;
    }
    len = strlen(out);
    while (*s != '\0' && len + 1u < cap) {
        out[len++] = *s++;
    }
    out[len] = '\0';
    return len;
}
