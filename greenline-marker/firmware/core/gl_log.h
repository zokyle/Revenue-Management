/*
 * gl_log.h - power-fail-safe ring log and small blob store on NOR flash.
 *
 * Both sit on an abstract flash interface (gl_flash_if_t) with NOR
 * semantics: erased bytes read 0xFF, programming can only clear bits, a
 * whole sector is erased at once.  drivers/mx25r provides the real one,
 * tests/synth/gl_simflash the simulated one with power cuts.
 *
 * ---------------------------------------------------------------------
 * RING LOG (gl_log_t)
 * ---------------------------------------------------------------------
 * A region of n >= 2 sectors used as a ring.  Layout of a sector:
 *
 *   sector header, 16 bytes
 *     0  u32 magic "GLS1"      4  u32 sector sequence number (grows by 1
 *     8  u32 sequence number of     per sector written; the highest valid
 *            the first record       one marks the head)
 *            written here      12 u8 version, u8 0xFF
 *                              14 u16 CRC-16 of bytes 0..13
 *   records, each 4-byte aligned:
 *     record header, 16 bytes
 *       0  u16 magic 0x4C47    2  u8 type, u8 flags
 *       4  u16 payload length  6  u16 CRC-16 of the payload
 *       8  u32 record sequence number
 *       12 u16 commit word: 0xFFFF while the record is being written,
 *              programmed to 0x0000 as the very last step
 *       14 u16 CRC-16 of bytes 0..11
 *     payload, padded with unprogrammed (0xFF) bytes to a multiple of 4
 *
 * POWER-FAIL SAFETY.  An append programs the header (commit word still
 * blank), then the payload, reads both back, and only then programs the
 * commit word.  A record is valid only if it is committed and both CRCs
 * match, so an interrupted append is rejected by construction and not
 * merely with CRC probability.  It leaves either a damaged header (skipped
 * 4 bytes at a time until blank flash) or a valid, uncommitted header
 * (skipped by its recorded length: payload bytes are never interpreted as
 * headers).  Programming only ever targets blank bytes.  When the head
 * sector is full the NEXT sector is erased - dropping the oldest records -
 * and gets a header with the next sequence number; a cut during that erase
 * or header write leaves the old head in charge.  tests/test_log.c cuts the
 * power at every programmed byte (with a randomly torn byte at the cut) and
 * at every stage of every erase and checks that every previously
 * acknowledged record is still returned intact and in order.
 *
 * Mount reads one 16-byte header per sector plus the head sector (about
 * 2040 short reads for the 8 MB part).
 *
 * ---------------------------------------------------------------------
 * BLOB STORE (gl_store_t) - settings and calibration
 * ---------------------------------------------------------------------
 * A second, small ring log (>= 3 sectors) in which the newest valid record
 * of each id is the current value.  All current values are held in RAM.
 * When the head sector fills, a fresh sector is started and EVERY current
 * value is rewritten into it, so the two newest sectors always hold a full
 * set and the sector erased next never holds the only copy of anything.
 * Mount repairs an interrupted rewrite before any further erase.
 *
 * RAM: gl_log_t 36 bytes; gl_store_t 1084 bytes.  Worst-case stack of
 * any function here: about 200 bytes (one 64-byte scratch buffer) plus the
 * flash callbacks.  No recursion, no allocation.
 */
#ifndef GL_LOG_H
#define GL_LOG_H

#include "gl_types.h"

/* ---- abstract flash ----------------------------------------------------- */

typedef struct {
    void *ctx;
    uint32_t sector_size; /**< bytes; multiple of 4, >= 128 */
    /** Read `len` bytes at absolute address `addr`. */
    gl_status_t (*read)(void *ctx, uint32_t addr, uint8_t *buf, size_t len);
    /** Program `len` bytes (may cross page boundaries; the driver splits).
     *  Only blank bytes are ever programmed by this module. */
    gl_status_t (*prog)(void *ctx, uint32_t addr, const uint8_t *buf, size_t len);
    /** Erase the sector that starts at `addr`. */
    gl_status_t (*erase_sector)(void *ctx, uint32_t addr);
} gl_flash_if_t;

/* ---- ring log ----------------------------------------------------------- */

#define GL_LOG_SECTOR_HDR 16u
#define GL_LOG_REC_HDR 16u
#define GL_LOG_VERSION 1u

/** Largest payload that fits one sector of the given size. */
#define GL_LOG_MAX_PAYLOAD(sector_size) ((sector_size) - GL_LOG_SECTOR_HDR - GL_LOG_REC_HDR)

typedef struct {
    const gl_flash_if_t *fl;
    uint32_t base_addr;       /**< address of the first sector of the region */
    uint32_t n_sectors;
    uint32_t head_sector;     /**< index of the sector being written */
    uint32_t head_offset;     /**< next free offset in it (== sector_size: full) */
    uint32_t head_seq;        /**< its sequence number (0 = no valid sector yet) */
    uint32_t next_rec_seq;    /**< sequence number the next record will get */
    uint32_t valid_sectors;   /**< sectors with a valid header at mount / since */
    uint32_t seq_floor;       /**< highest sector sequence number used before the last complete
                                   gl_log_erase_all(): numbering continues above it */
    uint32_t erase_origin;    /**< first sector of the erase in progress (absolute index) */
    bool erasing;             /**< gl_log_erase_all() has started and not finished */
    bool mounted;
} gl_log_t;

typedef struct {
    uint8_t type;
    uint8_t flags;
    uint16_t len;      /**< payload length */
    uint32_t seq;      /**< record sequence number */
    uint32_t addr;     /**< absolute flash address of the payload */
} gl_log_rec_t;

typedef struct {
    uint32_t sectors_left; /**< sectors still to visit, including the current one */
    uint32_t sector;       /**< current sector index */
    uint32_t offset;       /**< next offset to examine; 0 = sector not opened yet */
    uint32_t expect_seq;   /**< sector sequence number the current sector must have */
} gl_log_iter_t;

/**
 * Attach to a region and find the head.  Never erases or programs.
 * GL_ERR_PARAM for a bad geometry (n_sectors < 2, sector size not a
 * multiple of 4 or < 128), GL_ERR_IO if the flash cannot be read.
 * A blank or garbage region mounts as an empty log.
 */
gl_status_t gl_log_mount(gl_log_t *log, const gl_flash_if_t *fl, uint32_t base_addr,
                         uint32_t n_sectors);

/**
 * Append one record.  `len` <= GL_LOG_MAX_PAYLOAD(sector_size), else
 * GL_ERR_PARAM.  Returns GL_OK only after the record has been programmed
 * and read back correctly; `seq_out` (may be NULL) receives its sequence
 * number.  GL_ERR_IO: flash failure (the damaged space is skipped; the
 * call may be retried).  GL_ERR_BUSY while an incremental erase
 * (gl_log_erase_all) is in progress: nothing is written.
 */
gl_status_t gl_log_append(gl_log_t *log, uint8_t type, uint8_t flags, const uint8_t *payload,
                          size_t len, uint32_t *seq_out);

/** Close the head sector and start a fresh one now (drops the oldest
 *  sector).  Used by the blob store.  GL_ERR_BUSY during an incremental
 *  erase. */
gl_status_t gl_log_new_sector(gl_log_t *log);

/** Free bytes left in the head sector for record headers + payloads. */
uint32_t gl_log_head_free(const gl_log_t *log);

/** Start reading at the oldest record. */
void gl_log_iter_begin(const gl_log_t *log, gl_log_iter_t *it);

/**
 * Next valid record, oldest first.  Damaged records are skipped silently.
 * If `buf` is not NULL the payload is copied into it (GL_ERR_FULL if
 * cap < len; the iterator still advances and `rec` is filled).
 * Returns GL_ERR_EMPTY after the newest record.
 */
gl_status_t gl_log_iter_next(const gl_log_t *log, gl_log_iter_t *it, gl_log_rec_t *rec,
                             uint8_t *buf, size_t cap);

/** Read part of a record's payload (for records larger than the caller's
 *  buffer). */
gl_status_t gl_log_read_payload(const gl_log_t *log, const gl_log_rec_t *rec, uint32_t offset,
                                uint8_t *buf, size_t len);

/**
 * Erase the log incrementally, oldest sector first, at most `max_sectors`
 * per call (a sector erase blocks for tens of ms).  Start with *cursor = 0.
 * Returns GL_ERR_BUSY while sectors remain, GL_OK when the log is empty.
 * Only sectors that are not already blank at their header are erased.
 *
 * The order of the sectors is fixed when the erase starts (*cursor == 0)
 * and gl_log_append() / gl_log_new_sector() answer GL_ERR_BUSY until it has
 * finished or been cancelled, so no record can be written into the middle
 * of it.  Sector sequence numbers continue above the highest one used
 * before the erase: a sector that survived for any reason can never
 * outrank a newer one at the next mount.
 */
gl_status_t gl_log_erase_all(gl_log_t *log, uint32_t *cursor, uint32_t max_sectors);

/** Give up an incremental erase.  The sectors erased so far stay erased
 *  (they were the oldest); the rest of the log, including the head, is
 *  intact and appends work again.  No effect if none is in progress. */
void gl_log_erase_cancel(gl_log_t *log);

typedef struct {
    uint32_t bytes_capacity; /**< n_sectors * sector_size */
    uint32_t bytes_used;     /**< sectors in use, the head one counted to its fill level */
    uint32_t newest_seq;     /**< sequence number of the newest record (0 = none) */
    uint32_t record_estimate;/**< newest - oldest retained + 1 (counts skipped ones) */
} gl_log_stats_t;

/** Cheap statistics (reads the oldest valid sector's header only). */
gl_status_t gl_log_stats(const gl_log_t *log, gl_log_stats_t *out);

/* ---- blob store --------------------------------------------------------- */

#define GL_STORE_MAX_ITEMS 8u
#define GL_STORE_MAX_ITEM_LEN 128u
#define GL_STORE_REC_TYPE 0x53u /* 'S' */

/** Blob ids used by the application (the store itself accepts any 1..255). */
#define GL_STORE_ID_SETTINGS 0x10u
#define GL_STORE_ID_CAL_TILT 0x11u
#define GL_STORE_ID_CAL_CAM_L 0x12u
#define GL_STORE_ID_CAL_CAM_R 0x13u
#define GL_STORE_ID_CAL_GRAIN 0x14u
#define GL_STORE_ID_COURSE 0x15u  /* learned stick height */

typedef struct {
    uint8_t id;            /**< 0 = slot free */
    uint8_t len;
    bool in_head;          /**< newest copy is in the current head sector */
    uint8_t data[GL_STORE_MAX_ITEM_LEN];
} gl_store_item_t;

typedef struct {
    gl_log_t log;
    gl_store_item_t item[GL_STORE_MAX_ITEMS];
} gl_store_t;

/** Sector size from which EVERY set of values the store can hold fits one
 *  sector: its header plus one record of the largest size for every item
 *  (1168 bytes).  The power-fail guarantee ("the two newest sectors always
 *  hold a full set") needs the set in use to fit one sector; with smaller
 *  sectors gl_store_put() enforces that per call (GL_ERR_FULL), from this
 *  size on it can never refuse for that reason.  The application's layout
 *  is checked against it at compile time (app/gl_app.c). */
#define GL_STORE_MIN_SECTOR_BYTES \
    (GL_LOG_SECTOR_HDR + GL_STORE_MAX_ITEMS * (GL_LOG_REC_HDR + GL_STORE_MAX_ITEM_LEN))

/**
 * Mount the store region (n_sectors >= 3), load the newest valid value of
 * every id into RAM and repair an interrupted sector change-over.
 * GL_OK even when the region is blank (no items).
 */
gl_status_t gl_store_mount(gl_store_t *st, const gl_flash_if_t *fl, uint32_t base_addr,
                           uint32_t n_sectors);

/** Pointer to the current value of `id`.  GL_ERR_NOT_FOUND if never stored. */
gl_status_t gl_store_get(const gl_store_t *st, uint8_t id, const uint8_t **data, size_t *len);

/**
 * Store a new value (1 <= len <= GL_STORE_MAX_ITEM_LEN, id != 0).  On GL_OK
 * the value is durable.  On an error the previous durable value is still
 * what a remount would load, but RAM already holds the new one.
 * GL_ERR_FULL: more than GL_STORE_MAX_ITEMS distinct ids, or the set of
 * values including this one would no longer fit one sector (nothing is
 * changed in that case: an acknowledged value must survive any power cut,
 * and that needs the whole set in one sector).
 */
gl_status_t gl_store_put(gl_store_t *st, uint8_t id, const uint8_t *data, size_t len);

/* ---- record formats of the read log ------------------------------------- */

typedef enum {
    GL_LOG_REC_READ = 0x01,      /**< one completed read: gl_log_read_t */
    GL_LOG_REC_RAW_CHUNK = 0x02, /**< part of a raw image strip: gl_log_raw_hdr_t + pixels */
    GL_LOG_REC_EVENT = 0x03,     /**< boot, error, calibration: gl_log_event_t */
    GL_LOG_REC_GRAIN = 0x04      /**< raw grain measurement (16 x dark, on, dark) */
} gl_log_rec_type_t;

#define GL_LOG_READ_FLAG_STICK_FOUND   (1u << 0)
#define GL_LOG_READ_FLAG_BASE_VISIBLE  (1u << 1)
#define GL_LOG_READ_FLAG_TOP_VISIBLE   (1u << 2)
#define GL_LOG_READ_FLAG_MANUAL_RANGE  (1u << 3)
#define GL_LOG_READ_FLAG_PRECISION     (1u << 4)
#define GL_LOG_READ_FLAG_SURVEY        (1u << 5)
#define GL_LOG_READ_FLAG_GRAIN_VALID   (1u << 6)
#define GL_LOG_READ_FLAG_SUN           (1u << 7)

/** Compact summary of one read (GL_LOG_READ_LEN bytes on flash). */
typedef struct {
    uint32_t rtc_s;
    uint16_t read_id;          /**< links raw chunks to this read */
    uint8_t flags;             /**< GL_LOG_READ_FLAG_* */
    uint8_t drop_index;        /**< survey drop number, 0 otherwise */
    int16_t temp_c_x100;
    uint16_t batt_mv;
    float slope_x, slope_y;    /**< calibrated slope, rise/run, marker frame */
    float bearing_rad;
    float disparity_px, disparity_sigma_px;
    float base_elev_rad, top_elev_rad;
    float range_m, range_sigma_m;
    float stick_height_m;
    float aim_rad;             /**< displayed aim direction, marker frame */
    float v0_mps;
    float aim_offset_m;
    uint8_t stimp_x2;
    uint8_t confidence_pct;
    uint8_t solver_status;
    uint8_t rows_used_pct;
    uint8_t line_contrast;     /**< grey levels */
    uint8_t sharp_match_pct;
    uint8_t saturation_pct;
    uint8_t n_repeats;
} gl_log_read_t;
#define GL_LOG_READ_LEN 72u

/** Serialise a read summary to GL_LOG_READ_LEN bytes, little-endian, in
 *  the field order of the structure. */
void gl_log_read_encode(const gl_log_read_t *r, uint8_t out[GL_LOG_READ_LEN]);
/** GL_ERR_PARAM if len < GL_LOG_READ_LEN. */
gl_status_t gl_log_read_decode(const uint8_t *buf, size_t len, gl_log_read_t *r);

/** Header in front of the pixel data of a raw-strip chunk. */
typedef struct {
    uint16_t read_id;
    uint8_t camera;       /**< 0 = left, 1 = right */
    uint8_t kind;         /**< 0 = horizon band, 1 = stick strip */
    uint8_t frame_index;  /**< position in the L R R L ... sequence */
    uint8_t reserved;
    uint16_t x0, y0;      /**< sensor coordinates of the strip's first pixel */
    uint16_t width, height;
    uint32_t offset;      /**< byte offset of this chunk within the strip */
} gl_log_raw_hdr_t;
#define GL_LOG_RAW_HDR_LEN 18u

/** Serialise a raw-chunk header to GL_LOG_RAW_HDR_LEN bytes. */
void gl_log_raw_hdr_encode(const gl_log_raw_hdr_t *h, uint8_t out[GL_LOG_RAW_HDR_LEN]);
/** GL_ERR_PARAM if len < GL_LOG_RAW_HDR_LEN. */
gl_status_t gl_log_raw_hdr_decode(const uint8_t *buf, size_t len, gl_log_raw_hdr_t *h);

typedef struct {
    uint32_t rtc_s;
    uint16_t code;        /**< application event code */
    int32_t arg;
} gl_log_event_t;
#define GL_LOG_EVENT_LEN 10u

/** Serialise an event record to GL_LOG_EVENT_LEN bytes. */
void gl_log_event_encode(const gl_log_event_t *e, uint8_t out[GL_LOG_EVENT_LEN]);
/** GL_ERR_PARAM if len < GL_LOG_EVENT_LEN. */
gl_status_t gl_log_event_decode(const uint8_t *buf, size_t len, gl_log_event_t *e);

#endif /* GL_LOG_H */
