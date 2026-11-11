/* gl_log.c - ring log and blob store on NOR flash.  See gl_log.h. */
#include "gl_log.h"

#include <string.h>

#include "gl_buf.h"
#include "gl_crc.h"

#define SECTOR_MAGIC 0x31534C47u /* "GLS1" little-endian */
#define REC_MAGIC 0x4C47u        /* "GL" */
#define REC_COMMITTED 0x0000u    /* commit word once the record is complete */
#define SCRATCH 64u

typedef struct {
    uint32_t seq;
    uint32_t first_rec_seq;
} sector_hdr_t;

typedef enum {
    WALK_RECORD = 0, /* a valid record was found; offset is past it */
    WALK_SKIP,       /* damaged bytes were skipped; offset advanced */
    WALK_END         /* nothing but blank flash from offset on (or no room) */
} walk_t;

static uint32_t pad4_(uint32_t n)
{
    return (n + 3u) & ~(uint32_t)3u;
}

static uint32_t sector_addr_(const gl_log_t *log, uint32_t idx)
{
    return log->base_addr + idx * log->fl->sector_size;
}

static bool all_ff_(const uint8_t *p, size_t n)
{
    for (size_t i = 0; i < n; i++) {
        if (p[i] != 0xFFu) {
            return false;
        }
    }
    return true;
}

static void build_sector_hdr_(uint8_t out[GL_LOG_SECTOR_HDR], uint32_t seq, uint32_t first_rec)
{
    gl_put_u32(&out[0], SECTOR_MAGIC);
    gl_put_u32(&out[4], seq);
    gl_put_u32(&out[8], first_rec);
    out[12] = (uint8_t)GL_LOG_VERSION;
    out[13] = 0xFFu;
    gl_put_u16(&out[14], gl_crc16(out, 14));
}

/* Read and classify a sector header. */
static gl_status_t read_sector_hdr_(const gl_log_t *log, uint32_t idx, sector_hdr_t *h,
                                    bool *valid, bool *blank)
{
    uint8_t b[GL_LOG_SECTOR_HDR];
    if (log->fl->read(log->fl->ctx, sector_addr_(log, idx), b, sizeof(b)) != GL_OK) {
        return GL_ERR_IO;
    }
    *blank = all_ff_(b, sizeof(b));
    *valid = (gl_get_u32(&b[0]) == SECTOR_MAGIC) && (b[12] == GL_LOG_VERSION) &&
             (gl_get_u16(&b[14]) == gl_crc16(b, 14)) && (gl_get_u32(&b[4]) != 0u);
    h->seq = gl_get_u32(&b[4]);
    h->first_rec_seq = gl_get_u32(&b[8]);
    return GL_OK;
}

/* CRC of `len` flash bytes at `addr`. */
static gl_status_t flash_crc_(const gl_log_t *log, uint32_t addr, uint32_t len, uint16_t *crc)
{
    uint8_t b[SCRATCH];
    uint16_t c = GL_CRC16_INIT;
    while (len > 0u) {
        uint32_t n = (len < SCRATCH) ? len : SCRATCH;
        if (log->fl->read(log->fl->ctx, addr, b, n) != GL_OK) {
            return GL_ERR_IO;
        }
        c = gl_crc16_update(c, b, n);
        addr += n;
        len -= n;
    }
    *crc = c;
    return GL_OK;
}

/* True if every byte of the sector from `off` to its end is 0xFF. */
static gl_status_t rest_blank_(const gl_log_t *log, uint32_t sector, uint32_t off, bool *blank)
{
    uint8_t b[SCRATCH];
    const uint32_t ss = log->fl->sector_size;
    while (off < ss) {
        uint32_t n = ((ss - off) < SCRATCH) ? (ss - off) : SCRATCH;
        if (log->fl->read(log->fl->ctx, sector_addr_(log, sector) + off, b, n) != GL_OK) {
            return GL_ERR_IO;
        }
        if (!all_ff_(b, n)) {
            *blank = false;
            return GL_OK;
        }
        off += n;
    }
    *blank = true;
    return GL_OK;
}

/* Examine the sector at *off and classify what is there (see walk_t). */
static gl_status_t walk_step_(const gl_log_t *log, uint32_t sector, uint32_t *off,
                              gl_log_rec_t *rec, walk_t *result)
{
    const uint32_t ss = log->fl->sector_size;
    const uint32_t base = sector_addr_(log, sector);
    uint8_t h[GL_LOG_REC_HDR];
    uint32_t len, extent;
    bool hdr_ok;

    if (*off + GL_LOG_REC_HDR > ss) {
        *off = ss;
        *result = WALK_END;
        return GL_OK;
    }
    if (log->fl->read(log->fl->ctx, base + *off, h, sizeof(h)) != GL_OK) {
        return GL_ERR_IO;
    }
    len = gl_get_u16(&h[4]);
    extent = GL_LOG_REC_HDR + pad4_(len);
    hdr_ok = (gl_get_u16(&h[0]) == REC_MAGIC) && (gl_get_u16(&h[14]) == gl_crc16(h, 12)) &&
             (*off + extent <= ss);
    if (hdr_ok) {
        /* The commit word is programmed to 0x0000 only after the payload has
         * been written and read back, so an interrupted append can never be
         * mistaken for a record, whatever its CRC happens to be. */
        bool committed = (gl_get_u16(&h[12]) == REC_COMMITTED);
        uint16_t crc = 0;
        if (committed) {
            gl_status_t st = flash_crc_(log, base + *off + GL_LOG_REC_HDR, len, &crc);
            if (st != GL_OK) {
                return st;
            }
        }
        if (committed && crc == gl_get_u16(&h[6])) {
            rec->type = h[2];
            rec->flags = h[3];
            rec->len = (uint16_t)len;
            rec->seq = gl_get_u32(&h[8]);
            rec->addr = base + *off + GL_LOG_REC_HDR;
            *off += extent;
            *result = WALK_RECORD;
        } else {
            /* Valid header but not committed (an append was interrupted) or
             * a payload that no longer matches its CRC.  Skip by the
             * recorded length; never parse payload bytes as headers. */
            *off += extent;
            *result = WALK_SKIP;
        }
        return GL_OK;
    }
    if (all_ff_(h, sizeof(h))) {
        bool blank = false;
        gl_status_t st = rest_blank_(log, sector, *off + GL_LOG_REC_HDR, &blank);
        if (st != GL_OK) {
            return st;
        }
        if (blank) {
            *result = WALK_END;
            return GL_OK;
        }
    }
    *off += 4u; /* damaged header: creep forward to the next aligned position */
    *result = WALK_SKIP;
    return GL_OK;
}

/* ---- ring log ----------------------------------------------------------- */

gl_status_t gl_log_mount(gl_log_t *log, const gl_flash_if_t *fl, uint32_t base_addr,
                         uint32_t n_sectors)
{
    uint32_t best_seq = 0, best_idx = 0, best_first = 1;
    uint32_t off;

    if (log == NULL || fl == NULL || fl->read == NULL || fl->prog == NULL ||
        fl->erase_sector == NULL || n_sectors < 2u || fl->sector_size < 128u ||
        (fl->sector_size & 3u) != 0u || (fl->sector_size - GL_LOG_SECTOR_HDR -
        GL_LOG_REC_HDR) > 0xFFFFu) {
        return GL_ERR_PARAM;
    }
    memset(log, 0, sizeof(*log));
    log->fl = fl;
    log->base_addr = base_addr;
    log->n_sectors = n_sectors;

    for (uint32_t i = 0; i < n_sectors; i++) {
        sector_hdr_t h;
        bool valid = false, blank = false;
        if (read_sector_hdr_(log, i, &h, &valid, &blank) != GL_OK) {
            return GL_ERR_IO;
        }
        if (valid) {
            log->valid_sectors++;
            if (h.seq > best_seq) {
                best_seq = h.seq;
                best_idx = i;
                best_first = h.first_rec_seq;
            }
        }
    }
    if (best_seq == 0u) {
        /* Empty: the first append opens sector 0. */
        log->head_sector = n_sectors - 1u;
        log->head_offset = fl->sector_size;
        log->head_seq = 0;
        log->next_rec_seq = 1;
        log->mounted = true;
        return GL_OK;
    }
    log->head_sector = best_idx;
    log->head_seq = best_seq;
    log->next_rec_seq = (best_first == 0u) ? 1u : best_first;
    off = GL_LOG_SECTOR_HDR;
    for (;;) {
        gl_log_rec_t rec;
        walk_t res;
        gl_status_t st = walk_step_(log, best_idx, &off, &rec, &res);
        if (st != GL_OK) {
            return st;
        }
        if (res == WALK_END) {
            break;
        }
        if (res == WALK_RECORD && rec.seq + 1u > log->next_rec_seq) {
            log->next_rec_seq = rec.seq + 1u;
        }
    }
    log->head_offset = off;
    log->mounted = true;
    return GL_OK;
}

uint32_t gl_log_head_free(const gl_log_t *log)
{
    if (!log->mounted || log->head_seq == 0u || log->head_offset >= log->fl->sector_size) {
        return 0;
    }
    return log->fl->sector_size - log->head_offset;
}

gl_status_t gl_log_new_sector(gl_log_t *log)
{
    uint8_t hdr[GL_LOG_SECTOR_HDR], back[GL_LOG_SECTOR_HDR];
    sector_hdr_t old;
    bool was_valid = false, was_blank = false;
    uint32_t next, addr, new_seq;

    if (!log->mounted) {
        return GL_ERR_STATE;
    }
    if (log->erasing) {
        return GL_ERR_BUSY;
    }
    next = (log->head_sector + 1u) % log->n_sectors;
    addr = sector_addr_(log, next);
    if (read_sector_hdr_(log, next, &old, &was_valid, &was_blank) != GL_OK) {
        return GL_ERR_IO;
    }
    if (log->fl->erase_sector(log->fl->ctx, addr) != GL_OK) {
        return GL_ERR_IO;
    }
    if (was_valid && log->valid_sectors > 0u) {
        log->valid_sectors--; /* the oldest sector is gone */
    }
    /* never below the numbering used before an erase (seq_floor) */
    new_seq = ((log->head_seq > log->seq_floor) ? log->head_seq : log->seq_floor) + 1u;
    build_sector_hdr_(hdr, new_seq, log->next_rec_seq);
    if (log->fl->prog(log->fl->ctx, addr, hdr, sizeof(hdr)) != GL_OK ||
        log->fl->read(log->fl->ctx, addr, back, sizeof(back)) != GL_OK ||
        memcmp(hdr, back, sizeof(hdr)) != 0) {
        return GL_ERR_IO;
    }
    log->head_sector = next;
    log->head_seq = new_seq;
    log->head_offset = GL_LOG_SECTOR_HDR;
    log->valid_sectors++;
    return GL_OK;
}

gl_status_t gl_log_append(gl_log_t *log, uint8_t type, uint8_t flags, const uint8_t *payload,
                          size_t len, uint32_t *seq_out)
{
    uint8_t hdr[GL_LOG_REC_HDR], back[GL_LOG_REC_HDR], commit[2];
    uint32_t ss, need, addr, seq;
    uint16_t pcrc, vcrc = 0;
    gl_status_t st;

    if (log == NULL || !log->mounted) {
        return GL_ERR_STATE;
    }
    if (log->erasing) {
        return GL_ERR_BUSY; /* see gl_log_erase_all() */
    }
    ss = log->fl->sector_size;
    if (len > GL_LOG_MAX_PAYLOAD(ss) || (payload == NULL && len != 0u)) {
        return GL_ERR_PARAM;
    }
    need = GL_LOG_REC_HDR + pad4_((uint32_t)len);
    if (log->head_seq == 0u || log->head_offset + need > ss) {
        st = gl_log_new_sector(log);
        if (st != GL_OK) {
            return st;
        }
    }
    addr = sector_addr_(log, log->head_sector) + log->head_offset;
    seq = log->next_rec_seq;
    pcrc = gl_crc16(payload, len);
    gl_put_u16(&hdr[0], REC_MAGIC);
    hdr[2] = type;
    hdr[3] = flags;
    gl_put_u16(&hdr[4], (uint16_t)len);
    gl_put_u16(&hdr[6], pcrc);
    gl_put_u32(&hdr[8], seq);
    gl_put_u16(&hdr[12], 0xFFFFu); /* commit word: left blank for now */
    gl_put_u16(&hdr[14], gl_crc16(hdr, 12));

    /* The space is consumed and the sequence number used whatever happens
     * next: after a failed program it may be partly written. */
    log->head_offset += need;
    if (ss - log->head_offset < GL_LOG_REC_HDR) {
        log->head_offset = ss; /* no room for another header: same as mount reports */
    }
    log->next_rec_seq = seq + 1u;

    st = log->fl->prog(log->fl->ctx, addr, hdr, sizeof(hdr));
    if (st == GL_OK && len != 0u) {
        st = log->fl->prog(log->fl->ctx, addr + GL_LOG_REC_HDR, payload, len);
    }
    if (st != GL_OK) {
        return GL_ERR_IO;
    }
    /* Read back: header byte for byte, payload by CRC. */
    if (log->fl->read(log->fl->ctx, addr, back, sizeof(back)) != GL_OK ||
        memcmp(hdr, back, sizeof(hdr)) != 0 ||
        flash_crc_(log, addr + GL_LOG_REC_HDR, (uint32_t)len, &vcrc) != GL_OK || vcrc != pcrc) {
        return GL_ERR_IO;
    }
    /* Commit: the record exists from the moment both bytes read zero. */
    gl_put_u16(commit, REC_COMMITTED);
    if (log->fl->prog(log->fl->ctx, addr + 12u, commit, sizeof(commit)) != GL_OK ||
        log->fl->read(log->fl->ctx, addr + 12u, back, sizeof(commit)) != GL_OK ||
        gl_get_u16(back) != REC_COMMITTED) {
        return GL_ERR_IO;
    }
    if (seq_out != NULL) {
        *seq_out = seq;
    }
    return GL_OK;
}

void gl_log_iter_begin(const gl_log_t *log, gl_log_iter_t *it)
{
    memset(it, 0, sizeof(*it));
    if (!log->mounted || log->head_seq == 0u) {
        return; /* empty: sectors_left = 0 */
    }
    it->sectors_left = log->n_sectors;
    it->sector = (log->head_sector + 1u) % log->n_sectors;
    it->offset = 0;
    /* The sector d places before the head must carry head_seq - d. */
    it->expect_seq = log->head_seq - (log->n_sectors - 1u);
}

static void iter_advance_(const gl_log_t *log, gl_log_iter_t *it)
{
    it->sector = (it->sector + 1u) % log->n_sectors;
    it->offset = 0;
    it->expect_seq += 1u;
    it->sectors_left -= 1u;
}

gl_status_t gl_log_iter_next(const gl_log_t *log, gl_log_iter_t *it, gl_log_rec_t *rec,
                             uint8_t *buf, size_t cap)
{
    while (it->sectors_left > 0u) {
        walk_t res;
        gl_status_t st;
        if (it->offset == 0u) {
            sector_hdr_t h;
            bool valid = false, blank = false;
            if (read_sector_hdr_(log, it->sector, &h, &valid, &blank) != GL_OK) {
                return GL_ERR_IO;
            }
            if (!valid || h.seq != it->expect_seq) {
                iter_advance_(log, it); /* blank, damaged or stale sector */
                continue;
            }
            it->offset = GL_LOG_SECTOR_HDR;
        }
        st = walk_step_(log, it->sector, &it->offset, rec, &res);
        if (st != GL_OK) {
            return st;
        }
        if (res == WALK_END) {
            iter_advance_(log, it);
        } else if (res == WALK_RECORD) {
            if (buf != NULL) {
                if (cap < rec->len) {
                    return GL_ERR_FULL;
                }
                if (rec->len != 0u &&
                    log->fl->read(log->fl->ctx, rec->addr, buf, rec->len) != GL_OK) {
                    return GL_ERR_IO;
                }
            }
            return GL_OK;
        }
    }
    return GL_ERR_EMPTY;
}

gl_status_t gl_log_read_payload(const gl_log_t *log, const gl_log_rec_t *rec, uint32_t offset,
                                uint8_t *buf, size_t len)
{
    if (offset > rec->len || len > (size_t)(rec->len - offset)) {
        return GL_ERR_PARAM;
    }
    if (len == 0u) {
        return GL_OK;
    }
    return (log->fl->read(log->fl->ctx, rec->addr + offset, buf, len) == GL_OK) ? GL_OK
                                                                              : GL_ERR_IO;
}

gl_status_t gl_log_erase_all(gl_log_t *log, uint32_t *cursor, uint32_t max_sectors)
{
    if (log == NULL || !log->mounted || cursor == NULL) {
        return GL_ERR_STATE;
    }
    if (*cursor == 0u || !log->erasing) {
        /* The order is fixed HERE, once.  (It used to be recomputed from the
         * head on every call: an append that opened a new sector in between
         * shifted it, one old sector was skipped and outranked everything
         * written after the erase at the next mount.) */
        *cursor = 0;
        log->erase_origin = (log->head_sector + 1u) % log->n_sectors;
        log->erasing = true;
    }
    while (*cursor < log->n_sectors && max_sectors > 0u) {
        /* oldest first, the head last: an interrupted erase leaves a
         * consistent newest part */
        uint32_t idx = (log->erase_origin + *cursor) % log->n_sectors;
        uint8_t b[GL_LOG_SECTOR_HDR];
        if (log->fl->read(log->fl->ctx, sector_addr_(log, idx), b, sizeof(b)) != GL_OK) {
            return GL_ERR_IO;
        }
        if (!all_ff_(b, sizeof(b))) {
            if (log->fl->erase_sector(log->fl->ctx, sector_addr_(log, idx)) != GL_OK) {
                return GL_ERR_IO;
            }
            if (log->valid_sectors > 0u) {
                log->valid_sectors--;
            }
            max_sectors--;
        }
        (*cursor)++;
    }
    if (*cursor < log->n_sectors) {
        return GL_ERR_BUSY;
    }
    /* Empty.  Sector numbering continues above everything used so far. */
    if (log->head_seq > log->seq_floor) {
        log->seq_floor = log->head_seq;
    }
    log->head_sector = log->n_sectors - 1u;
    log->head_offset = log->fl->sector_size;
    log->head_seq = 0;
    log->next_rec_seq = 1;
    log->valid_sectors = 0;
    log->erasing = false;
    return GL_OK;
}

void gl_log_erase_cancel(gl_log_t *log)
{
    if (log != NULL) {
        log->erasing = false;
    }
}

gl_status_t gl_log_stats(const gl_log_t *log, gl_log_stats_t *out)
{
    const uint32_t ss = log->fl->sector_size;
    uint32_t oldest_first = log->next_rec_seq;

    memset(out, 0, sizeof(*out));
    out->bytes_capacity = log->n_sectors * ss;
    if (!log->mounted) {
        return GL_ERR_STATE;
    }
    if (log->head_seq == 0u) {
        return GL_OK;
    }
    out->bytes_used = ((log->valid_sectors > 0u) ? (log->valid_sectors - 1u) : 0u) * ss +
                      ((log->head_offset > ss) ? ss : log->head_offset);
    out->newest_seq = log->next_rec_seq - 1u;
    /* first record of the oldest sector that belongs to the current lap */
    for (uint32_t d = log->n_sectors - 1u;; d--) {
        uint32_t idx = (log->head_sector + log->n_sectors - d) % log->n_sectors;
        sector_hdr_t h;
        bool valid = false, blank = false;
        if (read_sector_hdr_(log, idx, &h, &valid, &blank) != GL_OK) {
            return GL_ERR_IO;
        }
        if (valid && h.seq == log->head_seq - d) {
            oldest_first = h.first_rec_seq;
            break;
        }
        if (d == 0u) {
            break;
        }
    }
    out->record_estimate = (log->next_rec_seq > oldest_first) ? (log->next_rec_seq - oldest_first)
                                                              : 0u;
    return GL_OK;
}

/* ---- blob store --------------------------------------------------------- */

static gl_store_item_t *store_find_(gl_store_t *st, uint8_t id, bool alloc)
{
    gl_store_item_t *free_slot = NULL;
    for (unsigned i = 0; i < GL_STORE_MAX_ITEMS; i++) {
        if (st->item[i].id == id) {
            return &st->item[i];
        }
        if (st->item[i].id == 0u && free_slot == NULL) {
            free_slot = &st->item[i];
        }
    }
    return alloc ? free_slot : NULL;
}

/* Start a fresh sector and rewrite every current value into it. */
static gl_status_t store_rewrite_all_(gl_store_t *st)
{
    gl_status_t first = gl_log_new_sector(&st->log);
    if (first != GL_OK) {
        return first;
    }
    for (unsigned i = 0; i < GL_STORE_MAX_ITEMS; i++) {
        st->item[i].in_head = false;
    }
    for (unsigned i = 0; i < GL_STORE_MAX_ITEMS; i++) {
        gl_store_item_t *it = &st->item[i];
        if (it->id != 0u) {
            gl_status_t s = gl_log_append(&st->log, (uint8_t)GL_STORE_REC_TYPE, it->id, it->data,
                                          it->len, NULL);
            if (s == GL_OK) {
                it->in_head = true;
            } else if (first == GL_OK) {
                first = s;
            }
        }
    }
    return first;
}

/* Make one item durable in the head sector. */
static gl_status_t store_write_(gl_store_t *st, gl_store_item_t *it)
{
    uint32_t need = GL_LOG_REC_HDR + pad4_(it->len);
    gl_status_t s;
    if (gl_log_head_free(&st->log) < need) {
        return store_rewrite_all_(st);
    }
    s = gl_log_append(&st->log, (uint8_t)GL_STORE_REC_TYPE, it->id, it->data, it->len, NULL);
    if (s == GL_OK) {
        it->in_head = true;
    }
    return s;
}

gl_status_t gl_store_mount(gl_store_t *st, const gl_flash_if_t *fl, uint32_t base_addr,
                           uint32_t n_sectors)
{
    gl_log_iter_t it;
    gl_log_rec_t rec;
    uint8_t buf[GL_STORE_MAX_ITEM_LEN];
    gl_status_t s;

    if (st == NULL || n_sectors < 3u) {
        return GL_ERR_PARAM;
    }
    memset(st->item, 0, sizeof(st->item));
    s = gl_log_mount(&st->log, fl, base_addr, n_sectors);
    if (s != GL_OK) {
        return s;
    }
    gl_log_iter_begin(&st->log, &it);
    for (;;) {
        s = gl_log_iter_next(&st->log, &it, &rec, NULL, 0);
        if (s == GL_ERR_EMPTY) {
            break;
        }
        if (s != GL_OK) {
            return s;
        }
        if (rec.type != GL_STORE_REC_TYPE || rec.flags == 0u || rec.len == 0u ||
            rec.len > GL_STORE_MAX_ITEM_LEN) {
            continue;
        }
        if (gl_log_read_payload(&st->log, &rec, 0, buf, rec.len) != GL_OK) {
            return GL_ERR_IO;
        }
        {
            gl_store_item_t *slot = store_find_(st, rec.flags, true);
            if (slot != NULL) {
                slot->id = rec.flags;
                slot->len = (uint8_t)rec.len;
                memcpy(slot->data, buf, rec.len);
                slot->in_head = (it.sector == st->log.head_sector);
            }
        }
    }
    /* Repair: after an interrupted change-over some values live only in the
     * previous sector.  Bring them into the head before anything else can
     * trigger an erase. */
    for (unsigned i = 0; i < GL_STORE_MAX_ITEMS; i++) {
        if (st->item[i].id != 0u && !st->item[i].in_head) {
            s = store_write_(st, &st->item[i]);
            if (s != GL_OK) {
                return s;
            }
        }
    }
    return GL_OK;
}

gl_status_t gl_store_get(const gl_store_t *st, uint8_t id, const uint8_t **data, size_t *len)
{
    if (id == 0u) {
        return GL_ERR_PARAM;
    }
    for (unsigned i = 0; i < GL_STORE_MAX_ITEMS; i++) {
        if (st->item[i].id == id) {
            *data = st->item[i].data;
            *len = st->item[i].len;
            return GL_OK;
        }
    }
    return GL_ERR_NOT_FOUND;
}

gl_status_t gl_store_put(gl_store_t *st, uint8_t id, const uint8_t *data, size_t len)
{
    gl_store_item_t *slot;
    if (st == NULL || id == 0u || data == NULL || len == 0u || len > GL_STORE_MAX_ITEM_LEN) {
        return GL_ERR_PARAM;
    }
    if (!st->log.mounted) {
        return GL_ERR_STATE;
    }
    slot = store_find_(st, id, true);
    if (slot == NULL) {
        return GL_ERR_FULL;
    }
    /* The whole set of values, with this one, must fit ONE sector: a sector
     * change-over rewrites the set into the fresh sector, and the power-fail
     * guarantee ("the two newest sectors always hold every value") holds
     * only then.  Refused before anything is changed. */
    {
        uint32_t set_bytes = GL_LOG_SECTOR_HDR + GL_LOG_REC_HDR + pad4_((uint32_t)len);
        for (unsigned i = 0; i < GL_STORE_MAX_ITEMS; i++) {
            if (st->item[i].id != 0u && &st->item[i] != slot) {
                set_bytes += GL_LOG_REC_HDR + pad4_(st->item[i].len);
            }
        }
        if (set_bytes > st->log.fl->sector_size) {
            return GL_ERR_FULL;
        }
    }
    slot->id = id;
    slot->len = (uint8_t)len;
    memcpy(slot->data, data, len);
    slot->in_head = false;
    return store_write_(st, slot);
}

/* ---- record formats ----------------------------------------------------- */

void gl_log_read_encode(const gl_log_read_t *r, uint8_t out[GL_LOG_READ_LEN])
{
    gl_wr_t w;
    gl_wr_init(&w, out, GL_LOG_READ_LEN);
    gl_wr_u32(&w, r->rtc_s);
    gl_wr_u16(&w, r->read_id);
    gl_wr_u8(&w, r->flags);
    gl_wr_u8(&w, r->drop_index);
    gl_wr_i16(&w, r->temp_c_x100);
    gl_wr_u16(&w, r->batt_mv);
    gl_wr_f32(&w, r->slope_x);
    gl_wr_f32(&w, r->slope_y);
    gl_wr_f32(&w, r->bearing_rad);
    gl_wr_f32(&w, r->disparity_px);
    gl_wr_f32(&w, r->disparity_sigma_px);
    gl_wr_f32(&w, r->base_elev_rad);
    gl_wr_f32(&w, r->top_elev_rad);
    gl_wr_f32(&w, r->range_m);
    gl_wr_f32(&w, r->range_sigma_m);
    gl_wr_f32(&w, r->stick_height_m);
    gl_wr_f32(&w, r->aim_rad);
    gl_wr_f32(&w, r->v0_mps);
    gl_wr_f32(&w, r->aim_offset_m);
    gl_wr_u8(&w, r->stimp_x2);
    gl_wr_u8(&w, r->confidence_pct);
    gl_wr_u8(&w, r->solver_status);
    gl_wr_u8(&w, r->rows_used_pct);
    gl_wr_u8(&w, r->line_contrast);
    gl_wr_u8(&w, r->sharp_match_pct);
    gl_wr_u8(&w, r->saturation_pct);
    gl_wr_u8(&w, r->n_repeats);
}

gl_status_t gl_log_read_decode(const uint8_t *buf, size_t len, gl_log_read_t *r)
{
    gl_rd_t d;
    if (buf == NULL || len < GL_LOG_READ_LEN) {
        return GL_ERR_PARAM;
    }
    gl_rd_init(&d, buf, len);
    r->rtc_s = gl_rd_u32(&d);
    r->read_id = gl_rd_u16(&d);
    r->flags = gl_rd_u8(&d);
    r->drop_index = gl_rd_u8(&d);
    r->temp_c_x100 = gl_rd_i16(&d);
    r->batt_mv = gl_rd_u16(&d);
    r->slope_x = gl_rd_f32(&d);
    r->slope_y = gl_rd_f32(&d);
    r->bearing_rad = gl_rd_f32(&d);
    r->disparity_px = gl_rd_f32(&d);
    r->disparity_sigma_px = gl_rd_f32(&d);
    r->base_elev_rad = gl_rd_f32(&d);
    r->top_elev_rad = gl_rd_f32(&d);
    r->range_m = gl_rd_f32(&d);
    r->range_sigma_m = gl_rd_f32(&d);
    r->stick_height_m = gl_rd_f32(&d);
    r->aim_rad = gl_rd_f32(&d);
    r->v0_mps = gl_rd_f32(&d);
    r->aim_offset_m = gl_rd_f32(&d);
    r->stimp_x2 = gl_rd_u8(&d);
    r->confidence_pct = gl_rd_u8(&d);
    r->solver_status = gl_rd_u8(&d);
    r->rows_used_pct = gl_rd_u8(&d);
    r->line_contrast = gl_rd_u8(&d);
    r->sharp_match_pct = gl_rd_u8(&d);
    r->saturation_pct = gl_rd_u8(&d);
    r->n_repeats = gl_rd_u8(&d);
    return d.ok ? GL_OK : GL_ERR_PARAM;
}

void gl_log_raw_hdr_encode(const gl_log_raw_hdr_t *h, uint8_t out[GL_LOG_RAW_HDR_LEN])
{
    gl_wr_t w;
    gl_wr_init(&w, out, GL_LOG_RAW_HDR_LEN);
    gl_wr_u16(&w, h->read_id);
    gl_wr_u8(&w, h->camera);
    gl_wr_u8(&w, h->kind);
    gl_wr_u8(&w, h->frame_index);
    gl_wr_u8(&w, 0);
    gl_wr_u16(&w, h->x0);
    gl_wr_u16(&w, h->y0);
    gl_wr_u16(&w, h->width);
    gl_wr_u16(&w, h->height);
    gl_wr_u32(&w, h->offset);
}

gl_status_t gl_log_raw_hdr_decode(const uint8_t *buf, size_t len, gl_log_raw_hdr_t *h)
{
    gl_rd_t d;
    if (buf == NULL || len < GL_LOG_RAW_HDR_LEN) {
        return GL_ERR_PARAM;
    }
    gl_rd_init(&d, buf, len);
    h->read_id = gl_rd_u16(&d);
    h->camera = gl_rd_u8(&d);
    h->kind = gl_rd_u8(&d);
    h->frame_index = gl_rd_u8(&d);
    h->reserved = gl_rd_u8(&d);
    h->x0 = gl_rd_u16(&d);
    h->y0 = gl_rd_u16(&d);
    h->width = gl_rd_u16(&d);
    h->height = gl_rd_u16(&d);
    h->offset = gl_rd_u32(&d);
    return d.ok ? GL_OK : GL_ERR_PARAM;
}

void gl_log_event_encode(const gl_log_event_t *e, uint8_t out[GL_LOG_EVENT_LEN])
{
    gl_wr_t w;
    gl_wr_init(&w, out, GL_LOG_EVENT_LEN);
    gl_wr_u32(&w, e->rtc_s);
    gl_wr_u16(&w, e->code);
    gl_wr_u32(&w, (uint32_t)e->arg);
}

gl_status_t gl_log_event_decode(const uint8_t *buf, size_t len, gl_log_event_t *e)
{
    gl_rd_t d;
    if (buf == NULL || len < GL_LOG_EVENT_LEN) {
        return GL_ERR_PARAM;
    }
    gl_rd_init(&d, buf, len);
    e->rtc_s = gl_rd_u32(&d);
    e->code = gl_rd_u16(&d);
    e->arg = (int32_t)gl_rd_u32(&d);
    return d.ok ? GL_OK : GL_ERR_PARAM;
}
