/*
 * gl_simflash.h - RAM-backed NOR flash with power-cut and fault injection,
 * behind the gl_flash_if_t interface of core/gl_log.h.  Host tests only.
 *
 * NOR semantics: erase sets a sector to 0xFF, programming ANDs.  Every
 * attempt to program a byte that is not blank is counted in
 * `prog_violations` (the log must never do it).
 *
 * POWER-CUT MODEL.  Work is counted in "events": one per programmed byte,
 * three per sector erase.  gl_simflash_arm_cut(f, k) lets k events complete
 * and interrupts the next one:
 *   - a programmed byte is TORN: a random subset of its 0-bits is written
 *     (possibly none, possibly all);
 *   - an erase interrupted at its 1st event has no effect, at its 2nd
 *     leaves the sector partly erased (each byte independently: untouched,
 *     0xFF, or old value with random extra 1-bits), at its 3rd is complete
 *     but the call still reports failure.
 * After the cut every operation fails with GL_ERR_IO until
 * gl_simflash_power_on().
 */
#ifndef GL_SIMFLASH_H
#define GL_SIMFLASH_H

#include "gl_log.h"

typedef struct {
    uint8_t *mem;
    uint32_t size;
    uint32_t sector_size;
    long long events_until_cut; /**< < 0: no cut armed */
    bool dead;
    bool cut_in_erase;          /**< the power cut that made it dead hit a sector erase */
    uint32_t rng;
    unsigned long long events_total;
    uint32_t prog_violations;
    uint32_t n_prog_bytes;
    uint32_t n_erases;
    uint32_t n_reads;
    /** Fault injection without power loss: the Nth next prog call (1 = the
     *  very next) fails with GL_ERR_IO after writing half of its bytes.
     *  0 = off. */
    uint32_t fail_prog_in;
} gl_simflash_t;

/** Attach to `mem` (size bytes, a multiple of sector_size) and blank it. */
void gl_simflash_init(gl_simflash_t *f, uint8_t *mem, uint32_t size, uint32_t sector_size);

/** Fill in a gl_flash_if_t that operates on `f`. */
void gl_simflash_if(gl_simflash_t *f, gl_flash_if_t *out);

/** Arm a power cut after `events` more events (see above). */
void gl_simflash_arm_cut(gl_simflash_t *f, long long events);

/** Power restored: operations work again, no cut armed.  Contents kept. */
void gl_simflash_power_on(gl_simflash_t *f);

#endif /* GL_SIMFLASH_H */
