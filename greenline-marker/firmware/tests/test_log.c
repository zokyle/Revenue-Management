/*
 * test_log.c - ring log and blob store over the simulated NOR flash,
 * including a power cut at EVERY programmed byte and every erase stage.
 */
#include <stdlib.h>

#include "gl_log.h"
#include "gl_simflash.h"
#include "gl_test.h"

#define SS 256u        /* small sectors make the ring wrap often */
#define NSEC 5u
#define MAXREC 4096

static uint8_t mem[64 * 1024];
static gl_simflash_t sim;
static gl_flash_if_t fl;
static gl_log_t lg;

/* ---- deterministic test payloads ---------------------------------------- */
/* A payload is fully determined by its index: [u32 index][filler].  Index 0
 * is never used.  Length cycles through 4..103, with a few special ones. */

static size_t payload_len(uint32_t index)
{
    if (index % 17u == 0u) {
        return 4;
    }
    if (index % 23u == 0u) {
        return GL_LOG_MAX_PAYLOAD(SS); /* a record that fills a whole sector */
    }
    return 4u + (size_t)((index * 37u) % 100u);
}

static size_t make_payload(uint32_t index, uint8_t *out)
{
    size_t n = payload_len(index);
    uint32_t x = index * 2654435761u + 12345u;
    gl_put_u32(out, index);
    for (size_t i = 4; i < n; i++) {
        x = x * 1664525u + 1013904223u;
        out[i] = (uint8_t)(x >> 24);
    }
    return n;
}

/* Check that a record read back is exactly the payload of its index. */
static bool payload_ok(const uint8_t *buf, size_t len, uint32_t *index_out)
{
    static uint8_t ref[512];
    uint32_t index;
    if (len < 4) {
        return false;
    }
    index = gl_get_u32(buf);
    *index_out = index;
    if (index == 0u || make_payload(index, ref) != len) {
        return false;
    }
    return memcmp(ref, buf, len) == 0;
}

/* Read the whole log; returns the number of records, their indices in
 * `idx`.  *bad counts records whose content is not a valid test payload
 * and order violations. */
static unsigned read_all(gl_log_t *log, uint32_t *idx, unsigned cap, unsigned *bad)
{
    gl_log_iter_t it;
    gl_log_rec_t rec;
    static uint8_t buf[512];
    unsigned n = 0;
    uint32_t last_seq = 0;
    *bad = 0;
    gl_log_iter_begin(log, &it);
    for (;;) {
        gl_status_t st = gl_log_iter_next(log, &it, &rec, buf, sizeof(buf));
        uint32_t index = 0;
        if (st == GL_ERR_EMPTY) {
            break;
        }
        if (st != GL_OK) {
            (*bad)++;
            break;
        }
        if (!payload_ok(buf, rec.len, &index) || rec.type != 0x42 || rec.seq <= last_seq) {
            (*bad)++;
        }
        last_seq = rec.seq;
        if (n < cap) {
            idx[n] = index;
        }
        n++;
    }
    return n;
}

static void fresh(uint32_t sector_size, uint32_t n_sectors)
{
    gl_simflash_init(&sim, mem, sector_size * n_sectors, sector_size);
    gl_simflash_if(&sim, &fl);
}

/* ---- basic behaviour ----------------------------------------------------- */

GL_TEST(test_empty_and_basic_append)
{
    uint32_t idx[64];
    unsigned bad;
    uint8_t p[512];
    gl_log_stats_t stats;

    fresh(SS, NSEC);
    GL_CHECK_EQ(gl_log_mount(&lg, &fl, 0, NSEC), GL_OK);
    GL_CHECK_EQ(read_all(&lg, idx, 64, &bad), 0);
    GL_CHECK_EQ(bad, 0);
    GL_CHECK_EQ(gl_log_head_free(&lg), 0);
    GL_CHECK_EQ(gl_log_stats(&lg, &stats), GL_OK);
    GL_CHECK_EQ(stats.bytes_used, 0);
    GL_CHECK_EQ(stats.newest_seq, 0);
    GL_CHECK_EQ(stats.bytes_capacity, SS * NSEC);
    GL_CHECK_EQ(sim.n_erases, 0); /* mounting never erases */
    GL_CHECK_EQ(sim.n_prog_bytes, 0);

    for (uint32_t i = 1; i <= 6; i++) {
        uint32_t seq = 0;
        size_t n = make_payload(i, p);
        GL_CHECK_EQ(gl_log_append(&lg, 0x42, (uint8_t)i, p, n, &seq), GL_OK);
        GL_CHECK_EQ(seq, i);
    }
    GL_CHECK_EQ(read_all(&lg, idx, 64, &bad), 6);
    GL_CHECK_EQ(bad, 0);
    for (uint32_t i = 0; i < 6; i++) {
        GL_CHECK_EQ(idx[i], i + 1);
    }
    /* exact on-flash layout of the first sector header and first record */
    GL_CHECK_MEM(&mem[0], "GLS1", 4);
    GL_CHECK_EQ(gl_get_u32(&mem[4]), 1);  /* sector sequence */
    GL_CHECK_EQ(gl_get_u32(&mem[8]), 1);  /* first record sequence */
    GL_CHECK_EQ(mem[12], GL_LOG_VERSION);
    GL_CHECK_EQ(mem[16], 0x47);
    GL_CHECK_EQ(mem[17], 0x4C);
    GL_CHECK_EQ(mem[18], 0x42);                       /* type */
    GL_CHECK_EQ(mem[19], 1);                          /* flags */
    GL_CHECK_EQ(gl_get_u16(&mem[20]), payload_len(1));
    GL_CHECK_EQ(gl_get_u32(&mem[24]), 1);             /* record sequence */
    GL_CHECK_EQ(gl_get_u32(&mem[32]), 1);             /* payload starts with its index */

    /* remount sees the same and continues the numbering */
    {
        gl_log_t l2;
        uint32_t seq = 0;
        GL_CHECK_EQ(gl_log_mount(&l2, &fl, 0, NSEC), GL_OK);
        GL_CHECK_EQ(l2.head_sector, lg.head_sector);
        GL_CHECK_EQ(l2.head_offset, lg.head_offset);
        GL_CHECK_EQ(l2.next_rec_seq, 7);
        GL_CHECK_EQ(read_all(&l2, idx, 64, &bad), 6);
        GL_CHECK_EQ(bad, 0);
        size_t n = make_payload(7, p);
        GL_CHECK_EQ(gl_log_append(&l2, 0x42, 0, p, n, &seq), GL_OK);
        GL_CHECK_EQ(seq, 7);
        GL_CHECK_EQ(gl_log_stats(&l2, &stats), GL_OK);
        GL_CHECK_EQ(stats.newest_seq, 7);
        GL_CHECK_EQ(stats.record_estimate, 7);
        GL_CHECK(stats.bytes_used > 0 && stats.bytes_used <= SS * NSEC);
    }
    GL_CHECK_EQ(sim.prog_violations, 0);
}

GL_TEST(test_parameter_checks)
{
    uint8_t p[512];
    gl_flash_if_t bad_fl;
    memset(p, 0, sizeof(p));
    fresh(SS, NSEC);
    GL_CHECK_EQ(gl_log_mount(&lg, &fl, 0, 1), GL_ERR_PARAM);
    bad_fl = fl;
    bad_fl.sector_size = 126;
    GL_CHECK_EQ(gl_log_mount(&lg, &bad_fl, 0, NSEC), GL_ERR_PARAM);
    bad_fl = fl;
    bad_fl.prog = NULL;
    GL_CHECK_EQ(gl_log_mount(&lg, &bad_fl, 0, NSEC), GL_ERR_PARAM);
    memset(&lg, 0, sizeof(lg));
    GL_CHECK_EQ(gl_log_append(&lg, 1, 0, p, 4, NULL), GL_ERR_STATE);
    GL_CHECK_EQ(gl_log_mount(&lg, &fl, 0, NSEC), GL_OK);
    GL_CHECK_EQ(gl_log_append(&lg, 1, 0, p, GL_LOG_MAX_PAYLOAD(SS) + 1, NULL), GL_ERR_PARAM);
    GL_CHECK_EQ(gl_log_append(&lg, 1, 0, NULL, 4, NULL), GL_ERR_PARAM);
    GL_CHECK_EQ(gl_log_append(&lg, 1, 0, NULL, 0, NULL), GL_OK); /* empty record is legal */
    GL_CHECK_EQ(gl_log_append(&lg, 1, 0, p, GL_LOG_MAX_PAYLOAD(SS), NULL), GL_OK);
    {
        gl_log_iter_t it;
        gl_log_rec_t rec;
        uint8_t small[8];
        gl_log_iter_begin(&lg, &it);
        GL_CHECK_EQ(gl_log_iter_next(&lg, &it, &rec, small, sizeof(small)), GL_OK);
        GL_CHECK_EQ(rec.len, 0);
        /* buffer too small: reported, iterator still advances */
        GL_CHECK_EQ(gl_log_iter_next(&lg, &it, &rec, small, sizeof(small)), GL_ERR_FULL);
        GL_CHECK_EQ(rec.len, GL_LOG_MAX_PAYLOAD(SS));
        /* partial payload reads */
        GL_CHECK_EQ(gl_log_read_payload(&lg, &rec, rec.len - 8u, small, 8), GL_OK);
        GL_CHECK_EQ(gl_log_read_payload(&lg, &rec, rec.len - 7u, small, 8), GL_ERR_PARAM);
        GL_CHECK_EQ(gl_log_iter_next(&lg, &it, &rec, small, sizeof(small)), GL_ERR_EMPTY);
        GL_CHECK_EQ(gl_log_iter_next(&lg, &it, &rec, small, sizeof(small)), GL_ERR_EMPTY);
    }
}

GL_TEST(test_wrap_keeps_newest_in_order)
{
    static uint32_t idx[MAXREC];
    unsigned bad, n;
    uint8_t p[512];
    gl_log_stats_t stats;

    fresh(SS, NSEC);
    GL_CHECK_EQ(gl_log_mount(&lg, &fl, 0, NSEC), GL_OK);
    for (uint32_t i = 1; i <= 400; i++) {
        size_t len = make_payload(i, p);
        GL_CHECK_EQ(gl_log_append(&lg, 0x42, 0, p, len, NULL), GL_OK);
        if (i % 50u == 0u) {
            /* the retained records are always a contiguous newest run */
            n = read_all(&lg, idx, MAXREC, &bad);
            GL_CHECK_EQ(bad, 0);
            GL_CHECK(n >= 1);
            GL_CHECK_EQ(idx[n - 1], i);
            for (unsigned k = 1; k < n; k++) {
                GL_CHECK_EQ(idx[k], idx[k - 1] + 1);
            }
        }
    }
    GL_CHECK(sim.n_erases > 3 * NSEC); /* wrapped several times */
    GL_CHECK_EQ(sim.prog_violations, 0);
    n = read_all(&lg, idx, MAXREC, &bad);
    /* at least (NSEC - 1) sectors' worth of records is retained */
    GL_CHECK(n >= 6);
    GL_CHECK_EQ(gl_log_stats(&lg, &stats), GL_OK);
    GL_CHECK_EQ(stats.newest_seq, 400);
    GL_CHECK_EQ(stats.record_estimate, n);
    GL_CHECK(stats.bytes_used <= SS * NSEC && stats.bytes_used > SS * (NSEC - 2));
    /* remount after many wraps */
    {
        gl_log_t l2;
        static uint32_t idx2[MAXREC];
        GL_CHECK_EQ(gl_log_mount(&l2, &fl, 0, NSEC), GL_OK);
        GL_CHECK_EQ(read_all(&l2, idx2, MAXREC, &bad), n);
        GL_CHECK_EQ(bad, 0);
        GL_CHECK_EQ(l2.next_rec_seq, 401);
        GL_CHECK_EQ(l2.head_offset, lg.head_offset);
        GL_CHECK_EQ(l2.head_seq, lg.head_seq);
    }
    /* a region that does not start at address 0 */
    fresh(SS, 8);
    GL_CHECK_EQ(gl_log_mount(&lg, &fl, 3 * SS, 4), GL_OK);
    for (uint32_t i = 1; i <= 100; i++) {
        size_t len = make_payload(i, p);
        GL_CHECK_EQ(gl_log_append(&lg, 0x42, 0, p, len, NULL), GL_OK);
    }
    for (uint32_t a = 0; a < 3 * SS; a++) {
        if (mem[a] != 0xFF || mem[7 * SS + a % SS] != 0xFF) {
            GL_CHECK(false); /* wrote outside its region */
            break;
        }
    }
}

/* ---- power cuts ----------------------------------------------------------- */

/* Run the standard scenario: append records with index first..last until
 * one fails.  Returns the number acknowledged (GL_OK). */
static uint32_t run_appends(gl_log_t *log, uint32_t first, uint32_t last)
{
    uint8_t p[512];
    uint32_t acked = 0;
    for (uint32_t i = first; i <= last; i++) {
        size_t len = make_payload(i, p);
        if (gl_log_append(log, 0x42, 0, p, len, NULL) != GL_OK) {
            break;
        }
        acked++;
    }
    return acked;
}

/* After a cut: remount and check the invariants.  `acked` = number of
 * records (indices 1..acked) acknowledged before the cut.  Returns the
 * number of invariant violations. */
static unsigned check_after_cut(uint32_t acked, uint32_t min_retained)
{
    static uint32_t idx[MAXREC];
    unsigned bad = 0, viol = 0, n;
    gl_log_t l2;

    if (gl_log_mount(&l2, &fl, 0, NSEC) != GL_OK) {
        return 1000;
    }
    n = read_all(&l2, idx, MAXREC, &bad);
    viol += bad; /* garbage or out-of-order records */
    if (n > 0) {
        /* contiguous run of indices ... */
        for (unsigned k = 1; k < n; k++) {
            if (idx[k] != idx[k - 1] + 1u) {
                viol++;
            }
        }
        /* ... that ends at the last acknowledged record, or at the one that
         * was in flight if it happened to be completed */
        if (idx[n - 1] != acked && idx[n - 1] != acked + 1u) {
            viol++;
        }
    } else if (acked > 0) {
        viol++; /* acknowledged data lost */
    }
    if (acked >= min_retained && n < min_retained) {
        viol++; /* lost more old records than one sector change-over explains */
    }
    /* the log must keep working: append more, everything still consistent */
    {
        uint32_t next = (n > 0) ? (idx[n - 1] + 1u) : (acked + 1u);
        unsigned n2;
        if (run_appends(&l2, next, next + 7u) != 8u) {
            viol++;
        }
        n2 = read_all(&l2, idx, MAXREC, &bad);
        viol += bad;
        if (n2 == 0 || idx[n2 - 1] != next + 7u) {
            viol++;
        }
        for (unsigned k = 1; k < n2; k++) {
            if (idx[k] != idx[k - 1] + 1u) {
                viol++;
            }
        }
        /* and a further remount agrees */
        {
            gl_log_t l3;
            static uint32_t idx3[MAXREC];
            unsigned n3;
            if (gl_log_mount(&l3, &fl, 0, NSEC) != GL_OK) {
                viol++;
            }
            n3 = read_all(&l3, idx3, MAXREC, &bad);
            viol += bad;
            if (n3 != n2 || l3.head_offset != l2.head_offset || l3.head_seq != l2.head_seq) {
                viol++;
            }
        }
    }
    viol += sim.prog_violations;
    return viol;
}

GL_TEST(test_power_cut_at_every_event)
{
    const uint32_t total_records = 90; /* about 2.5 laps of the ring */
    unsigned long long total_events;
    unsigned failures = 0, cuts_during_erase = 0;
    long long first_bad = -1;

    /* dry run to count events */
    fresh(SS, NSEC);
    GL_CHECK_EQ(gl_log_mount(&lg, &fl, 0, NSEC), GL_OK);
    GL_CHECK_EQ(run_appends(&lg, 1, total_records), total_records);
    total_events = sim.events_total;
    GL_CHECK(sim.n_erases >= 2 * NSEC);

    for (unsigned long long k = 0; k < total_events; k++) {
        uint32_t acked;
        uint32_t erases_before;
        unsigned v;
        fresh(SS, NSEC);
        sim.rng = (uint32_t)(k * 2654435761u + 1u);
        gl_log_mount(&lg, &fl, 0, NSEC);
        gl_simflash_arm_cut(&sim, (long long)k);
        acked = run_appends(&lg, 1, total_records);
        if (!sim.dead) {
            failures++; /* the cut must have fired */
            continue;
        }
        erases_before = sim.n_erases;
        (void)erases_before;
        if (sim.cut_in_erase) {
            cuts_during_erase++;
        }
        gl_simflash_power_on(&sim);
        /* 2 records always survive: a full sector holds at least 1 maximum
         * record, and with 5 sectors at least 3 full ones are retained */
        v = check_after_cut(acked, 2);
        if (v != 0) {
            failures++;
            if (first_bad < 0) {
                first_bad = (long long)k;
            }
        }
    }
    printf("    %llu cut points (every programmed byte and every erase stage, %u records, "
           "%u-byte sectors x %u): %u failures\n", total_events, (unsigned)total_records,
           (unsigned)SS, (unsigned)NSEC, failures);
    if (first_bad >= 0) {
        printf("    first failing cut point: %lld\n", first_bad);
    }
    GL_CHECK_EQ(failures, 0);
    /* the sweep really did interrupt erases: three stages of each one */
    GL_CHECK(cuts_during_erase >= 3u * 2u * NSEC);
    printf("    of which %u interrupted a sector erase\n", cuts_during_erase);
}

/* A second cut during the recovery appends that follow the first one. */
GL_TEST(test_double_power_cut)
{
    unsigned failures = 0, runs = 0;
    for (long long k1 = 3; k1 < 6000; k1 += 97) {
        for (long long k2 = 0; k2 < 400; k2 += 7) {
            uint32_t acked, acked2;
            static uint32_t idx[MAXREC];
            unsigned bad, n;
            gl_log_t l2;

            fresh(SS, NSEC);
            sim.rng = (uint32_t)(k1 * 7919 + k2 * 104729 + 1);
            gl_log_mount(&lg, &fl, 0, NSEC);
            gl_simflash_arm_cut(&sim, k1);
            acked = run_appends(&lg, 1, 90);
            gl_simflash_power_on(&sim);
            if (gl_log_mount(&l2, &fl, 0, NSEC) != GL_OK) {
                failures++;
                continue;
            }
            n = read_all(&l2, idx, MAXREC, &bad);
            if (bad != 0) {
                failures++;
            }
            /* continue with the next index, second cut armed */
            {
                uint32_t next = (n > 0) ? (idx[n - 1] + 1u) : (acked + 1u);
                gl_simflash_arm_cut(&sim, k2);
                acked2 = run_appends(&l2, next, next + 20u);
                gl_simflash_power_on(&sim);
                /* now the last acknowledged index is next - 1 + acked2 */
                if (check_after_cut(next - 1u + acked2, 0) != 0) {
                    failures++;
                }
            }
            runs++;
        }
    }
    printf("    %u double-cut runs: %u failures\n", runs, failures);
    GL_CHECK_EQ(failures, 0);
}

GL_TEST(test_io_error_without_power_loss)
{
    static uint32_t idx[MAXREC];
    uint8_t p[512];
    unsigned bad, n;
    unsigned errors = 0;

    fresh(SS, NSEC);
    GL_CHECK_EQ(gl_log_mount(&lg, &fl, 0, NSEC), GL_OK);
    for (uint32_t i = 1; i <= 120; i++) {
        size_t len = make_payload(i, p);
        gl_status_t st;
        if (i % 9u == 0u) {
            sim.fail_prog_in = 1u + (i % 2u); /* header or payload program fails */
        }
        st = gl_log_append(&lg, 0x42, 0, p, len, NULL);
        if (st != GL_OK) {
            errors++;
            GL_CHECK_EQ(st, GL_ERR_IO);
            /* retry must succeed and must not disturb earlier records */
            GL_CHECK_EQ(gl_log_append(&lg, 0x42, 0, p, len, NULL), GL_OK);
        }
    }
    GL_CHECK(errors >= 10);
    n = read_all(&lg, idx, MAXREC, &bad);
    GL_CHECK_EQ(bad, 0);
    GL_CHECK(n > 0);
    GL_CHECK_EQ(idx[n - 1], 120);
    for (unsigned k = 1; k < n; k++) {
        GL_CHECK_EQ(idx[k], idx[k - 1] + 1);
    }
    GL_CHECK_EQ(sim.prog_violations, 0);
    {
        gl_log_t l2;
        GL_CHECK_EQ(gl_log_mount(&l2, &fl, 0, NSEC), GL_OK);
        GL_CHECK_EQ(read_all(&l2, idx, MAXREC, &bad), n);
        GL_CHECK_EQ(bad, 0);
    }
}

GL_TEST(test_erase_all_incremental_and_cut)
{
    static uint32_t idx[MAXREC];
    unsigned bad;
    uint32_t cursor = 0;
    unsigned calls = 0;

    fresh(SS, NSEC);
    GL_CHECK_EQ(gl_log_mount(&lg, &fl, 0, NSEC), GL_OK);
    GL_CHECK_EQ(run_appends(&lg, 1, 60), 60);
    for (;;) {
        gl_status_t st = gl_log_erase_all(&lg, &cursor, 2);
        calls++;
        if (st == GL_OK) {
            break;
        }
        GL_CHECK_EQ(st, GL_ERR_BUSY);
        if (calls > 20) {
            GL_CHECK(false);
            break;
        }
    }
    GL_CHECK(calls >= 3); /* 5 sectors, 2 per call */
    GL_CHECK_EQ(read_all(&lg, idx, MAXREC, &bad), 0);
    for (uint32_t a = 0; a < SS * NSEC; a++) {
        if (mem[a] != 0xFF) {
            GL_CHECK(false);
            break;
        }
    }
    /* usable again, numbering restarts */
    GL_CHECK_EQ(run_appends(&lg, 1, 10), 10);
    GL_CHECK_EQ(read_all(&lg, idx, MAXREC, &bad), 10);
    GL_CHECK_EQ(bad, 0);

    /* power cut at every stage of an erase-all: what remains is a valid log */
    for (long long k = 0; k < 3 * (long long)NSEC; k++) {
        gl_log_t l2;
        unsigned n;
        fresh(SS, NSEC);
        gl_log_mount(&lg, &fl, 0, NSEC);
        run_appends(&lg, 1, 60);
        gl_simflash_arm_cut(&sim, k);
        cursor = 0;
        GL_CHECK_EQ(gl_log_erase_all(&lg, &cursor, 100), GL_ERR_IO);
        gl_simflash_power_on(&sim);
        GL_CHECK_EQ(gl_log_mount(&l2, &fl, 0, NSEC), GL_OK);
        n = read_all(&l2, idx, MAXREC, &bad);
        GL_CHECK_EQ(bad, 0);
        if (n > 0) {
            GL_CHECK_EQ(idx[n - 1], 60); /* newest part survives, oldest goes first */
            for (unsigned i = 1; i < n; i++) {
                GL_CHECK_EQ(idx[i], idx[i - 1] + 1);
            }
        }
        /* finishing the erase works */
        cursor = 0;
        GL_CHECK_EQ(gl_log_erase_all(&l2, &cursor, 100), GL_OK);
        GL_CHECK_EQ(read_all(&l2, idx, MAXREC, &bad), 0);
    }
}


/* Review finding: gl_log_erase_all() recomputed the sector order from the
 * head on every call, so an append that opened a new sector between two
 * calls made it skip one old sector; numbering then restarted at 1 and the
 * stale sector won at the next mount ("erased" records came back, records
 * acknowledged after the erase vanished). */
GL_TEST(test_erase_all_with_appends_in_between)
{
    static uint32_t idx[MAXREC];
    unsigned bad, n;
    uint32_t cursor;
    uint8_t p[512];
    size_t len;
    uint32_t seq_before;

    /* exactly the reviewer's sequence: the head sector is full when the
     * erase starts, one sector is erased, then an append arrives */
    fresh(SS, NSEC);
    GL_CHECK_EQ(gl_log_mount(&lg, &fl, 0, NSEC), GL_OK);
    GL_CHECK_EQ(run_appends(&lg, 1, 60), 60);
    while (gl_log_head_free(&lg) >= GL_LOG_REC_HDR + 4u) {
        len = make_payload(17, p); /* index 17: a 4-byte payload */
        GL_CHECK_EQ(gl_log_append(&lg, 0x42, 0, p, len, NULL), GL_OK);
    }
    seq_before = lg.head_seq;
    cursor = 0;
    GL_CHECK_EQ(gl_log_erase_all(&lg, &cursor, 1), GL_ERR_BUSY);
    /* the append is refused, and so is a forced sector change */
    len = make_payload(1000, p);
    GL_CHECK_EQ(gl_log_append(&lg, 0x42, 0, p, len, NULL), GL_ERR_BUSY);
    GL_CHECK_EQ(gl_log_new_sector(&lg), GL_ERR_BUSY);
    GL_CHECK_EQ(sim.prog_violations, 0);
    for (unsigned calls = 0; calls < 20u; calls++) {
        const gl_status_t st = gl_log_erase_all(&lg, &cursor, 1);
        if (st == GL_OK) {
            break;
        }
        GL_CHECK_EQ(st, GL_ERR_BUSY);
        /* appends stay refused until the erase has finished */
        GL_CHECK_EQ(gl_log_append(&lg, 0x42, 0, p, len, NULL), GL_ERR_BUSY);
    }
    GL_CHECK_EQ(read_all(&lg, idx, MAXREC, &bad), 0);
    for (uint32_t a = 0; a < SS * NSEC; a++) {
        if (mem[a] != 0xFF) {
            GL_CHECK(false); /* a sector survived the erase */
            break;
        }
    }
    /* four records after the erase; after a power cycle they are the log */
    GL_CHECK_EQ(run_appends(&lg, 2001, 2004), 4);
    GL_CHECK(lg.head_seq > seq_before); /* sector numbering continued above the old one */
    {
        gl_log_t l2;
        GL_CHECK_EQ(gl_log_mount(&l2, &fl, 0, NSEC), GL_OK);
        n = read_all(&l2, idx, MAXREC, &bad);
        GL_CHECK_EQ(bad, 0);
        GL_CHECK_EQ(n, 4);
        for (unsigned i = 0; i < n && i < 4u; i++) {
            GL_CHECK_EQ(idx[i], 2001u + i);
        }
    }

    /* every interleaving: k sectors erased, then an append attempt, then
     * the rest; with the head at every fill level */
    for (uint32_t fill = 55; fill <= 75; fill++) {
        for (uint32_t k = 0; k < NSEC; k++) {
            gl_log_t l2;
            fresh(SS, NSEC);
            gl_log_mount(&lg, &fl, 0, NSEC);
            run_appends(&lg, 1, fill);
            cursor = 0;
            if (k > 0u) {
                (void)gl_log_erase_all(&lg, &cursor, k);
                len = make_payload(3000, p);
                GL_CHECK_EQ(gl_log_append(&lg, 0x42, 0, p, len, NULL), GL_ERR_BUSY);
            }
            while (gl_log_erase_all(&lg, &cursor, 1) == GL_ERR_BUSY) {
            }
            GL_CHECK_EQ(run_appends(&lg, 4001, 4003), 3);
            GL_CHECK_EQ(gl_log_mount(&l2, &fl, 0, NSEC), GL_OK);
            n = read_all(&l2, idx, MAXREC, &bad);
            GL_CHECK_EQ(bad, 0);
            GL_CHECK_EQ(n, 3);
            GL_CHECK(n == 3u && idx[0] == 4001u && idx[2] == 4003u);
        }
    }

    /* a cancelled erase: the oldest sectors are gone, the newest part is
     * intact and the log accepts records again */
    fresh(SS, NSEC);
    gl_log_mount(&lg, &fl, 0, NSEC);
    run_appends(&lg, 1, 60);
    cursor = 0;
    GL_CHECK_EQ(gl_log_erase_all(&lg, &cursor, 2), GL_ERR_BUSY);
    gl_log_erase_cancel(&lg);
    GL_CHECK_EQ(run_appends(&lg, 61, 64), 4);
    n = read_all(&lg, idx, MAXREC, &bad);
    GL_CHECK_EQ(bad, 0);
    GL_CHECK(n >= 5u && idx[n - 1u] == 64u);
    for (unsigned i = 1; i < n; i++) {
        GL_CHECK_EQ(idx[i], idx[i - 1] + 1);
    }
    {
        gl_log_t l2;
        gl_log_stats_t stats;
        GL_CHECK_EQ(gl_log_mount(&l2, &fl, 0, NSEC), GL_OK);
        GL_CHECK_EQ(read_all(&l2, idx, MAXREC, &bad), n);
        GL_CHECK_EQ(bad, 0);
        GL_CHECK_EQ(gl_log_stats(&lg, &stats), GL_OK);
        GL_CHECK(stats.bytes_used <= SS * NSEC);
    }
    /* a new erase after a cancel starts from the present head */
    cursor = 0;
    while (gl_log_erase_all(&lg, &cursor, 1) == GL_ERR_BUSY) {
    }
    GL_CHECK_EQ(read_all(&lg, idx, MAXREC, &bad), 0);
}

/* Real geometry: 4 kB sectors, 2000-byte raw chunks, sampled cut points. */
GL_TEST(test_real_geometry_raw_chunks)
{
    static uint8_t chunk[GL_LOG_RAW_HDR_LEN + 2000];
    static uint8_t back[GL_LOG_RAW_HDR_LEN + 2000];
    const uint32_t ss = 4096, nsec = 8;
    unsigned failures = 0, runs = 0;

    for (long long k = -1; k < 120000; k += (k < 0) ? 1 : 1009) {
        gl_log_t l2;
        gl_log_iter_t it;
        gl_log_rec_t rec;
        uint32_t acked = 0, expect = 0, count = 0;
        bool first = true;

        fresh(ss, nsec);
        sim.rng = (uint32_t)(k + 77);
        GL_CHECK_EQ(gl_log_mount(&lg, &fl, 0, nsec), GL_OK);
        if (k >= 0) {
            gl_simflash_arm_cut(&sim, k);
        }
        for (uint32_t i = 0; i < 60; i++) {
            gl_log_raw_hdr_t h = { 7, (uint8_t)(i & 1u), 1, (uint8_t)i, 0, 272, 0, 96, 480, 0 };
            h.offset = i * 2000u;
            gl_log_raw_hdr_encode(&h, chunk);
            for (size_t j = 0; j < 2000; j++) {
                chunk[GL_LOG_RAW_HDR_LEN + j] = (uint8_t)(i * 31u + j * 7u);
            }
            if (gl_log_append(&lg, GL_LOG_REC_RAW_CHUNK, 0, chunk, sizeof(chunk), NULL) != GL_OK) {
                break;
            }
            acked++;
        }
        gl_simflash_power_on(&sim);
        if (gl_log_mount(&l2, &fl, 0, nsec) != GL_OK) {
            failures++;
            continue;
        }
        gl_log_iter_begin(&l2, &it);
        while (gl_log_iter_next(&l2, &it, &rec, back, sizeof(back)) == GL_OK) {
            gl_log_raw_hdr_t h;
            if (rec.type != GL_LOG_REC_RAW_CHUNK || rec.len != sizeof(chunk) ||
                gl_log_raw_hdr_decode(back, rec.len, &h) != GL_OK) {
                failures++;
                break;
            }
            if (first) {
                expect = h.frame_index;
                first = false;
            }
            if (h.frame_index != expect || h.offset != expect * 2000u ||
                back[GL_LOG_RAW_HDR_LEN + 1999] != (uint8_t)(expect * 31u + 1999u * 7u)) {
                failures++;
                break;
            }
            expect++;
            count++;
        }
        if (acked > 0 && (count == 0 || (expect != acked && expect != acked + 1u))) {
            failures++;
        }
        if (k < 0) {
            GL_CHECK_EQ(acked, 60);
            /* two 2034-byte records per 4096-byte sector; 7 or 8 of the 8
             * sectors are retained */
            GL_CHECK(count >= 14 && count <= 16);
        }
        failures += sim.prog_violations;
        runs++;
    }
    printf("    4096-byte sectors, 2018-byte records: %u runs, %u failures\n", runs, failures);
    GL_CHECK_EQ(failures, 0);
}

/* ---- blob store ----------------------------------------------------------- */

#define ST_NSEC 3u

static void blob_value(uint8_t id, uint32_t version, uint8_t *out, size_t *len)
{
    /* length depends on the id, content on id and version */
    size_t n = 8u + (size_t)id * 9u;
    gl_put_u32(out, version);
    for (size_t i = 4; i < n; i++) {
        out[i] = (uint8_t)(id * 16u + version * 3u + i);
    }
    *len = n;
}

/* Which version of `id` does the store currently hold?  0 = absent,
 * 0xFFFFFFFF = present but corrupt. */
static uint32_t store_version(const gl_store_t *st, uint8_t id)
{
    const uint8_t *d;
    size_t len, rlen;
    uint8_t ref[GL_STORE_MAX_ITEM_LEN];
    uint32_t v;
    if (gl_store_get(st, id, &d, &len) != GL_OK) {
        return 0;
    }
    if (len < 4) {
        return 0xFFFFFFFFu;
    }
    v = gl_get_u32(d);
    blob_value(id, v, ref, &rlen);
    return (rlen == len && memcmp(ref, d, len) == 0) ? v : 0xFFFFFFFFu;
}

GL_TEST(test_store_basic)
{
    static gl_store_t st;
    uint8_t v[GL_STORE_MAX_ITEM_LEN];
    size_t len;
    const uint8_t *d;

    fresh(SS, ST_NSEC);
    GL_CHECK_EQ(gl_store_mount(&st, &fl, 0, 2), GL_ERR_PARAM);
    GL_CHECK_EQ(gl_store_mount(&st, &fl, 0, ST_NSEC), GL_OK);
    GL_CHECK_EQ(gl_store_get(&st, 1, &d, &len), GL_ERR_NOT_FOUND);
    GL_CHECK_EQ(gl_store_put(&st, 0, v, 4), GL_ERR_PARAM);
    GL_CHECK_EQ(gl_store_put(&st, 1, v, 0), GL_ERR_PARAM);
    GL_CHECK_EQ(gl_store_put(&st, 1, v, GL_STORE_MAX_ITEM_LEN + 1), GL_ERR_PARAM);

    /* many updates of 4 ids force repeated sector change-overs */
    for (uint32_t ver = 1; ver <= 60; ver++) {
        for (uint8_t id = 1; id <= 4; id++) {
            if ((ver + id) % 3u != 0u) {
                blob_value(id, ver, v, &len);
                GL_CHECK_EQ(gl_store_put(&st, id, v, len), GL_OK);
                GL_CHECK_EQ(store_version(&st, id), ver);
            }
        }
    }
    GL_CHECK(sim.n_erases > 6);
    GL_CHECK_EQ(sim.prog_violations, 0);
    {
        static gl_store_t st2;
        GL_CHECK_EQ(gl_store_mount(&st2, &fl, 0, ST_NSEC), GL_OK);
        for (uint8_t id = 1; id <= 4; id++) {
            GL_CHECK_EQ(store_version(&st2, id), store_version(&st, id));
            GL_CHECK(store_version(&st2, id) >= 59);
        }
        /* a clean mount writes nothing */
        uint32_t prog = sim.n_prog_bytes;
        GL_CHECK_EQ(gl_store_mount(&st2, &fl, 0, ST_NSEC), GL_OK);
        GL_CHECK_EQ(sim.n_prog_bytes, prog);
    }
    /* capacity: the 9th distinct id is refused */
    fresh(4096, ST_NSEC);
    GL_CHECK_EQ(gl_store_mount(&st, &fl, 0, ST_NSEC), GL_OK);
    for (uint8_t id = 1; id <= 8; id++) {
        memset(v, id, sizeof(v));
        GL_CHECK_EQ(gl_store_put(&st, id, v, GL_STORE_MAX_ITEM_LEN), GL_OK);
    }
    GL_CHECK_EQ(gl_store_put(&st, 9, v, 4), GL_ERR_FULL);
    GL_CHECK_EQ(gl_store_put(&st, 3, v, 4), GL_OK); /* updating an existing id still works */
}

/* Cut the power at every event of a long put sequence, and again at every
 * event of the mount-time repair. */
GL_TEST(test_store_power_cut_everywhere)
{
    static gl_store_t st, st2;
    unsigned long long total_events;
    unsigned failures = 0, nested = 0;
    long long first_bad = -1;
    const uint32_t versions = 14;

    fresh(SS, ST_NSEC);
    gl_store_mount(&st, &fl, 0, ST_NSEC);
    for (uint32_t ver = 1; ver <= versions; ver++) {
        for (uint8_t id = 1; id <= 4; id++) {
            uint8_t v[GL_STORE_MAX_ITEM_LEN];
            size_t len;
            blob_value(id, ver, v, &len);
            GL_CHECK_EQ(gl_store_put(&st, id, v, len), GL_OK);
        }
    }
    total_events = sim.events_total;
    GL_CHECK(sim.n_erases >= 6);

    for (unsigned long long k = 0; k < total_events; k++) {
        uint32_t acked[5] = { 0, 0, 0, 0, 0 };
        uint8_t flying_id = 0;
        uint32_t flying_ver = 0;
        bool bad = false;

        fresh(SS, ST_NSEC);
        sim.rng = (uint32_t)(k * 2246822519u + 3u);
        gl_store_mount(&st, &fl, 0, ST_NSEC);
        gl_simflash_arm_cut(&sim, (long long)k);
        for (uint32_t ver = 1; ver <= versions && !sim.dead; ver++) {
            for (uint8_t id = 1; id <= 4 && !sim.dead; id++) {
                uint8_t v[GL_STORE_MAX_ITEM_LEN];
                size_t len;
                blob_value(id, ver, v, &len);
                if (gl_store_put(&st, id, v, len) == GL_OK) {
                    acked[id] = ver;
                } else {
                    flying_id = id;
                    flying_ver = ver;
                }
            }
        }
        if (!sim.dead) {
            failures++;
            continue;
        }
        /* nested: cut again at the j-th event of the repairing mount */
        /* (every 4th cut point gets the full nested sweep; the others only
         * the plain remount, to keep the run time reasonable) */
        for (long long j = -1; j < ((k % 4u == 0u) ? 400 : 0); j++) {
            static uint8_t snapshot[SS * ST_NSEC];
            bool again;
            if (j == -1) {
                memcpy(snapshot, mem, sizeof(snapshot));
            } else {
                memcpy(mem, snapshot, sizeof(snapshot));
            }
            gl_simflash_power_on(&sim);
            if (j >= 0) {
                gl_simflash_arm_cut(&sim, j);
                (void)gl_store_mount(&st2, &fl, 0, ST_NSEC);
                again = sim.dead;
                gl_simflash_power_on(&sim);
                if (!again) {
                    break; /* the repair needed fewer than j events: done */
                }
                nested++;
            }
            if (gl_store_mount(&st2, &fl, 0, ST_NSEC) != GL_OK) {
                bad = true;
                break;
            }
            for (uint8_t id = 1; id <= 4; id++) {
                uint32_t have = store_version(&st2, id);
                bool ok = (have == acked[id]) || (id == flying_id && have == flying_ver);
                if (!ok) {
                    bad = true;
                }
            }
            /* still writable, and durable across one more mount */
            {
                uint8_t v[GL_STORE_MAX_ITEM_LEN];
                size_t len;
                static gl_store_t st3;
                blob_value(2, 999, v, &len);
                if (gl_store_put(&st2, 2, v, len) != GL_OK ||
                    gl_store_mount(&st3, &fl, 0, ST_NSEC) != GL_OK ||
                    store_version(&st3, 2) != 999) {
                    bad = true;
                }
                for (uint8_t id = 1; id <= 4; id++) {
                    if (id != 2 && store_version(&st3, id) != store_version(&st2, id)) {
                        bad = true;
                    }
                }
            }
            if (sim.prog_violations != 0) {
                bad = true;
            }
            if (bad) {
                break;
            }
        }
        if (bad) {
            failures++;
            if (first_bad < 0) {
                first_bad = (long long)k;
            }
        }
    }
    printf("    store: %llu cut points during puts, %u nested cuts during repair: %u failures\n",
           total_events, nested, failures);
    if (first_bad >= 0) {
        printf("    first failing cut point: %lld\n", first_bad);
    }
    GL_CHECK_EQ(failures, 0);
}


/* Review finding: the store accepted any geometry, but its power-fail
 * guarantee needs the whole set of values to fit one sector.  6 items of
 * 100 bytes in 256-byte sectors: every put was acknowledged and 35099
 * acknowledged values were lost over the cut points.  Now the put that
 * would make the set too large is refused, before anything is changed. */
GL_TEST(test_store_refuses_a_set_that_does_not_fit_one_sector)
{
    static gl_store_t st, st2;
    uint8_t v[GL_STORE_MAX_ITEM_LEN];
    const uint8_t *d;
    size_t len;
    unsigned long long total_events;
    unsigned lost = 0, refused = 0;

    fresh(SS, ST_NSEC);
    GL_CHECK_EQ(gl_store_mount(&st, &fl, 0, ST_NSEC), GL_OK);
    for (uint32_t ver = 1; ver <= 6; ver++) {
        for (uint8_t id = 1; id <= 6; id++) {
            memset(v, (int)(id * 16u + ver), sizeof(v));
            const gl_status_t s = gl_store_put(&st, id, v, 100);
            /* 16 + 2 x 116 = 248 <= 256; a third 100-byte item cannot fit */
            GL_CHECK_EQ(s, (id <= 2u) ? GL_OK : GL_ERR_FULL);
            if (s == GL_ERR_FULL) {
                refused++;
                GL_CHECK_EQ(gl_store_get(&st, id, &d, &len), GL_ERR_NOT_FOUND); /* RAM unchanged */
            }
        }
    }
    GL_CHECK_EQ(refused, 6u * 4u);
    /* growing an existing item is refused the same way and leaves its value */
    memset(v, 0x77, sizeof(v));
    GL_CHECK_EQ(gl_store_put(&st, 2, v, 120), GL_ERR_FULL);
    GL_CHECK_EQ(gl_store_get(&st, 2, &d, &len), GL_OK);
    GL_CHECK_EQ(len, 100);
    GL_CHECK_EQ(d[0], 2u * 16u + 6u);
    total_events = sim.events_total;

    /* every acknowledged value survives a cut at every event */
    for (unsigned long long k = 0; k < total_events; k++) {
        uint32_t acked[7] = { 0, 0, 0, 0, 0, 0, 0 };
        uint8_t fly_id = 0;
        uint32_t fly_ver = 0;
        fresh(SS, ST_NSEC);
        sim.rng = (uint32_t)(k * 40503u + 7u);
        gl_store_mount(&st, &fl, 0, ST_NSEC);
        gl_simflash_arm_cut(&sim, (long long)k);
        for (uint32_t ver = 1; ver <= 6 && !sim.dead; ver++) {
            for (uint8_t id = 1; id <= 6 && !sim.dead; id++) {
                memset(v, (int)(id * 16u + ver), sizeof(v));
                const gl_status_t s = gl_store_put(&st, id, v, 100);
                if (s == GL_OK) {
                    acked[id] = ver;
                } else if (s != GL_ERR_FULL) {
                    fly_id = id;
                    fly_ver = ver;
                }
            }
        }
        gl_simflash_power_on(&sim);
        if (gl_store_mount(&st2, &fl, 0, ST_NSEC) != GL_OK) {
            lost++;
            continue;
        }
        for (uint8_t id = 1; id <= 6; id++) {
            uint32_t have = 0;
            if (gl_store_get(&st2, id, &d, &len) == GL_OK && len == 100u) {
                have = (uint32_t)d[0] - (uint32_t)id * 16u;
            }
            if (have != acked[id] && !(id == fly_id && have == fly_ver)) {
                lost++;
            }
        }
    }
    printf("    6 x 100-byte items offered to 3 x 256-byte sectors: 2 accepted, 4 refused "
           "(GL_ERR_FULL); %llu cut points, %u acknowledged values lost\n", total_events, lost);
    GL_CHECK_EQ(lost, 0);
    /* from GL_STORE_MIN_SECTOR_BYTES on, the largest possible set fits */
    GL_CHECK_EQ(GL_STORE_MIN_SECTOR_BYTES, 1168u);
    fresh(GL_STORE_MIN_SECTOR_BYTES, ST_NSEC);
    GL_CHECK_EQ(gl_store_mount(&st, &fl, 0, ST_NSEC), GL_OK);
    for (uint8_t id = 1; id <= 8; id++) {
        memset(v, id, sizeof(v));
        GL_CHECK_EQ(gl_store_put(&st, id, v, GL_STORE_MAX_ITEM_LEN), GL_OK);
    }
    for (uint8_t id = 1; id <= 8; id++) {
        memset(v, id + 100, sizeof(v));
        GL_CHECK_EQ(gl_store_put(&st, id, v, GL_STORE_MAX_ITEM_LEN), GL_OK);
    }
    GL_CHECK_EQ(gl_store_mount(&st2, &fl, 0, ST_NSEC), GL_OK);
    for (uint8_t id = 1; id <= 8; id++) {
        GL_CHECK(gl_store_get(&st2, id, &d, &len) == GL_OK && len == GL_STORE_MAX_ITEM_LEN &&
                 d[5] == id + 100);
    }
}

/* Review finding (mutation test): with the repair loop of gl_store_mount()
 * disabled every test still passed, because the repair only matters after
 * three power cuts in a row, each during a sector change-over: the value
 * that was not yet rewritten then lives only in the sector that the third
 * change-over erases.  This test makes such triples: random cut points,
 * biased by construction toward change-overs (4 items fill a 256-byte
 * sector, so most programmed bytes belong to one).  Verified by hand: with
 * the repair disabled it reports lost values. */
GL_TEST(test_store_three_cuts_in_a_row)
{
    static gl_store_t st;
    unsigned lost = 0, trials = 0, all_three = 0;
    uint32_t r = 0xC0FFEEu;

    for (unsigned t = 0; t < 4000u; t++) {
        uint32_t acked[5] = { 0, 0, 0, 0, 0 };
        uint8_t fly_id[4] = { 0, 0, 0, 0 };
        uint32_t fly_ver[4] = { 0, 0, 0, 0 };
        uint32_t ver = 1;
        uint8_t id = 1;
        unsigned cuts = 0;
        bool bad = false;

        fresh(SS, ST_NSEC);
        sim.rng = t * 2654435761u + 11u;
        if (gl_store_mount(&st, &fl, 0, ST_NSEC) != GL_OK) {
            lost++;
            continue;
        }
        /* some history first, so that all three sectors are in use */
        for (; ver <= 6u; ver++) {
            for (id = 1; id <= 4; id++) {
                uint8_t v[GL_STORE_MAX_ITEM_LEN];
                size_t len;
                blob_value(id, ver, v, &len);
                if (gl_store_put(&st, id, v, len) == GL_OK) {
                    acked[id] = ver;
                }
            }
        }
        id = 1;
        for (unsigned c = 0; c < 3u; c++) {
            r = r * 1664525u + 1013904223u;
            gl_simflash_arm_cut(&sim, (long long)((r >> 8) % 330u));
            while (!sim.dead && ver < 200u) {
                uint8_t v[GL_STORE_MAX_ITEM_LEN];
                size_t len;
                blob_value(id, ver, v, &len);
                if (gl_store_put(&st, id, v, len) == GL_OK) {
                    acked[id] = ver;
                } else {
                    fly_id[c] = id;
                    fly_ver[c] = ver;
                }
                if (++id > 4u) {
                    id = 1;
                    ver++;
                }
            }
            if (sim.dead) {
                cuts++;
            }
            gl_simflash_power_on(&sim);
            /* the mount after the cut repairs; values in flight may or may
             * not have made it */
            if (gl_store_mount(&st, &fl, 0, ST_NSEC) != GL_OK) {
                bad = true;
                break;
            }
            for (uint8_t i = 1; i <= 4; i++) {
                const uint32_t have = store_version(&st, i);
                bool ok = (have == acked[i]);
                for (unsigned q = 0; q <= c; q++) {
                    if (i == fly_id[q] && have == fly_ver[q]) {
                        ok = true;
                        acked[i] = have; /* it is durable now */
                    }
                }
                if (!ok) {
                    bad = true;
                }
            }
        }
        trials++;
        if (cuts == 3u) {
            all_three++;
        }
        if (bad || sim.prog_violations != 0u) {
            lost++;
        }
    }
    printf("    store: %u runs with three power cuts in a row (%u with all three during "
           "writes): %u with a lost value\n", trials, all_three, lost);
    GL_CHECK_EQ(lost, 0);
    GL_CHECK(all_three > 3000u);
}

/* ---- record codecs -------------------------------------------------------- */

GL_TEST(test_record_codecs)
{
    gl_log_read_t r, r2;
    gl_log_event_t e = { 1700000123u, 0x1234, -987654 }, e2;
    gl_log_raw_hdr_t h = { 513, 1, 1, 9, 0, 272, 0, 96, 480, 46000 }, h2;
    uint8_t b[GL_LOG_READ_LEN], eb[GL_LOG_EVENT_LEN], hb[GL_LOG_RAW_HDR_LEN];

    memset(&r, 0, sizeof(r));
    r.rtc_s = 1731312000u;
    r.read_id = 0xBEEF;
    r.flags = GL_LOG_READ_FLAG_STICK_FOUND | GL_LOG_READ_FLAG_BASE_VISIBLE;
    r.drop_index = 2;
    r.temp_c_x100 = -1234;
    r.batt_mv = 3987;
    r.slope_x = 0.0123f;
    r.slope_y = -0.0045f;
    r.bearing_rad = 0.05f;
    r.disparity_px = 2.68f;
    r.disparity_sigma_px = 0.07f;
    r.base_elev_rad = -0.001f;
    r.top_elev_rad = 0.38f;
    r.range_m = 5.0f;
    r.range_sigma_m = 0.13f;
    r.stick_height_m = 1.96f;
    r.aim_rad = 0.031f;
    r.v0_mps = 2.5f;
    r.aim_offset_m = 0.155f;
    r.stimp_x2 = 21;
    r.confidence_pct = 70;
    r.solver_status = 1;
    r.rows_used_pct = 93;
    r.line_contrast = 61;
    r.sharp_match_pct = 97;
    r.saturation_pct = 1;
    r.n_repeats = 8;
    gl_log_read_encode(&r, b);
    GL_CHECK_EQ(gl_log_read_decode(b, sizeof(b), &r2), GL_OK);
    GL_CHECK_EQ(r2.rtc_s, r.rtc_s);
    GL_CHECK_EQ(r2.read_id, r.read_id);
    GL_CHECK_EQ(r2.flags, r.flags);
    GL_CHECK_EQ(r2.temp_c_x100, r.temp_c_x100);
    GL_CHECK(r2.slope_y == r.slope_y && r2.aim_offset_m == r.aim_offset_m);
    GL_CHECK(r2.disparity_px == r.disparity_px && r2.range_sigma_m == r.range_sigma_m);
    GL_CHECK_EQ(r2.n_repeats, 8);
    GL_CHECK_EQ(r2.sharp_match_pct, 97);
    /* layout is fixed: spot-check byte positions */
    GL_CHECK_EQ(gl_get_u32(&b[0]), 1731312000u);
    GL_CHECK_EQ(gl_get_u16(&b[4]), 0xBEEF);
    GL_CHECK_EQ(b[64], 21);
    GL_CHECK_EQ(b[71], 8);
    GL_CHECK_EQ(gl_log_read_decode(b, GL_LOG_READ_LEN - 1, &r2), GL_ERR_PARAM);

    gl_log_event_encode(&e, eb);
    GL_CHECK_EQ(gl_log_event_decode(eb, sizeof(eb), &e2), GL_OK);
    GL_CHECK(e2.rtc_s == e.rtc_s && e2.code == e.code && e2.arg == e.arg);
    GL_CHECK_EQ(gl_log_event_decode(eb, 9, &e2), GL_ERR_PARAM);

    gl_log_raw_hdr_encode(&h, hb);
    GL_CHECK_EQ(gl_log_raw_hdr_decode(hb, sizeof(hb), &h2), GL_OK);
    GL_CHECK(h2.read_id == 513 && h2.camera == 1 && h2.frame_index == 9 && h2.x0 == 272 &&
             h2.width == 96 && h2.height == 480 && h2.offset == 46000);
}

int main(void)
{
    GL_RUN(test_empty_and_basic_append);
    GL_RUN(test_parameter_checks);
    GL_RUN(test_wrap_keeps_newest_in_order);
    GL_RUN(test_power_cut_at_every_event);
    GL_RUN(test_double_power_cut);
    GL_RUN(test_io_error_without_power_loss);
    GL_RUN(test_erase_all_incremental_and_cut);
    GL_RUN(test_erase_all_with_appends_in_between);
    GL_RUN(test_real_geometry_raw_chunks);
    GL_RUN(test_store_basic);
    GL_RUN(test_store_power_cut_everywhere);
    GL_RUN(test_store_refuses_a_set_that_does_not_fit_one_sector);
    GL_RUN(test_store_three_cuts_in_a_row);
    GL_RUN(test_record_codecs);
    return gl_test_summary();
}
