/* gl_simflash.c - see gl_simflash.h. */
#include "gl_simflash.h"

#include <string.h>

static uint32_t rnd_(gl_simflash_t *f)
{
    uint32_t x = f->rng;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    f->rng = x;
    return x;
}

static gl_status_t sf_read_(void *ctx, uint32_t addr, uint8_t *buf, size_t len)
{
    gl_simflash_t *f = (gl_simflash_t *)ctx;
    if (f->dead || addr > f->size || len > f->size - addr) {
        return GL_ERR_IO;
    }
    memcpy(buf, &f->mem[addr], len);
    f->n_reads++;
    return GL_OK;
}

static gl_status_t sf_prog_(void *ctx, uint32_t addr, const uint8_t *buf, size_t len)
{
    gl_simflash_t *f = (gl_simflash_t *)ctx;
    size_t limit = len;
    bool inject = false;
    if (f->dead || addr > f->size || len > f->size - addr) {
        return GL_ERR_IO;
    }
    if (f->fail_prog_in != 0u) {
        f->fail_prog_in--;
        if (f->fail_prog_in == 0u) {
            inject = true;
            limit = len / 2u;
        }
    }
    for (size_t i = 0; i < limit; i++) {
        uint8_t old = f->mem[addr + i];
        if (old != 0xFFu) {
            f->prog_violations++;
        }
        if (f->events_until_cut == 0) {
            uint8_t mask = (uint8_t)rnd_(f); /* bits that did NOT get programmed */
            f->mem[addr + i] = (uint8_t)(old & (buf[i] | mask));
            f->dead = true;
            return GL_ERR_IO;
        }
        f->mem[addr + i] = (uint8_t)(old & buf[i]);
        f->n_prog_bytes++;
        f->events_total++;
        if (f->events_until_cut > 0) {
            f->events_until_cut--;
        }
    }
    return inject ? GL_ERR_IO : GL_OK;
}

static gl_status_t sf_erase_(void *ctx, uint32_t addr)
{
    gl_simflash_t *f = (gl_simflash_t *)ctx;
    if (f->dead || addr >= f->size || (addr % f->sector_size) != 0u) {
        return GL_ERR_IO;
    }
    for (int stage = 0; stage < 3; stage++) {
        if (f->events_until_cut == 0) {
            if (stage == 1) {
                for (uint32_t i = 0; i < f->sector_size; i++) {
                    uint32_t r = rnd_(f);
                    if ((r & 3u) == 0u) {
                        f->mem[addr + i] = 0xFFu;
                    } else if ((r & 3u) == 1u) {
                        f->mem[addr + i] = (uint8_t)(f->mem[addr + i] | (uint8_t)(r >> 8));
                    }
                }
            } else if (stage == 2) {
                memset(&f->mem[addr], 0xFF, f->sector_size);
            }
            f->dead = true;
            f->cut_in_erase = true;
            return GL_ERR_IO;
        }
        f->events_total++;
        if (f->events_until_cut > 0) {
            f->events_until_cut--;
        }
    }
    memset(&f->mem[addr], 0xFF, f->sector_size);
    f->n_erases++;
    return GL_OK;
}

void gl_simflash_init(gl_simflash_t *f, uint8_t *mem, uint32_t size, uint32_t sector_size)
{
    memset(f, 0, sizeof(*f));
    f->mem = mem;
    f->size = size;
    f->sector_size = sector_size;
    f->events_until_cut = -1;
    f->rng = 0x9E3779B9u;
    memset(mem, 0xFF, size);
}

void gl_simflash_if(gl_simflash_t *f, gl_flash_if_t *out)
{
    out->ctx = f;
    out->sector_size = f->sector_size;
    out->read = sf_read_;
    out->prog = sf_prog_;
    out->erase_sector = sf_erase_;
}

void gl_simflash_arm_cut(gl_simflash_t *f, long long events)
{
    f->events_until_cut = events;
}

void gl_simflash_power_on(gl_simflash_t *f)
{
    f->dead = false;
    f->cut_in_erase = false;
    f->events_until_cut = -1;
}
