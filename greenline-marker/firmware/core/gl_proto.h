/*
 * gl_proto.h - framed binary protocol over the USB CDC-ACM port (cradle).
 *
 * FRAME (little-endian), 8 bytes of overhead:
 *
 *   0    0xA5           start of frame
 *   1    0x5A
 *   2,3  LEN            payload length N, 0..GL_PROTO_MAX_PAYLOAD
 *   4    SEQ            request sequence number, echoed in the response
 *   5    CMD            request: command id (0x01..0x3F)
 *                       response: command id | 0x80
 *                       unsolicited stream frame: 0x40 | source id
 *   6..  payload[N]
 *   6+N  CRC lo, CRC hi CRC-16/CCITT-FALSE over bytes 2 .. 5+N
 *
 * Every RESPONSE payload starts with one status byte (gl_status_t), then
 * the command-specific data listed at each command below.
 *
 * RESYNCHRONISATION.  The receiver keeps the bytes of a candidate frame in
 * a buffer.  If the header is implausible or the CRC fails it discards ONE
 * byte and searches again from the next start-of-frame, so a valid frame
 * that begins inside a damaged one is still found.  gl_proto_rx_reset()
 * (call it when the line has been idle for ~100 ms) drops a stalled
 * partial frame.
 *
 * The module is pure: it reaches the device through the gl_proto_ops_t
 * callbacks supplied by the application and never calls the HAL.
 *
 * RAM: sizeof(gl_proto_t) = 2 * (GL_PROTO_MAX_PAYLOAD + 8) + ~48 bytes
 * (about 2.1 kB).  Worst-case stack: under 200 bytes plus the callbacks.
 */
#ifndef GL_PROTO_H
#define GL_PROTO_H

#include "gl_cal.h"
#include "gl_settings.h"
#include "gl_types.h"

#define GL_PROTO_SOF0 0xA5u
#define GL_PROTO_SOF1 0x5Au
#define GL_PROTO_OVERHEAD 8u
#define GL_PROTO_MAX_PAYLOAD 1024u
#define GL_PROTO_MAX_FRAME (GL_PROTO_MAX_PAYLOAD + GL_PROTO_OVERHEAD)
#define GL_PROTO_VERSION 1u

#define GL_PROTO_RESPONSE_FLAG 0x80u
#define GL_PROTO_STREAM_FLAG 0x40u

/** Command ids.  "->" shows request payload, "<-" response data after the
 *  status byte. */
typedef enum {
    GL_CMD_PING = 0x01,         /**< -> any bytes (<= 64)   <- the same bytes */
    GL_CMD_GET_INFO = 0x02,     /**< -> -                   <- gl_proto_info_t, 28 bytes */
    GL_CMD_GET_STATUS = 0x03,   /**< -> -                   <- gl_proto_status_t, 16 bytes */
    GL_CMD_GET_SETTINGS = 0x04, /**< -> -                   <- settings blob (12) */
    GL_CMD_SET_SETTINGS = 0x05, /**< -> settings blob (12)  <- - */
    GL_CMD_GET_CAL = 0x06,      /**< -> cal id (1)          <- cal id (1) + blob */
    GL_CMD_SET_CAL = 0x07,      /**< -> cal id (1) + blob   <- -   (needs UNLOCK) */
    GL_CMD_START_CAL = 0x08,    /**< -> procedure (1), arg (1)  <- - */
    GL_CMD_LOG_INFO = 0x09,     /**< -> -                   <- gl_proto_log_info_t, 16 bytes */
    GL_CMD_LOG_READ = 0x0A,     /**< -> restart flag (1)    <- more flag (1) + record stream */
    GL_CMD_LOG_ERASE = 0x0B,    /**< -> "ERAS"              <- -   (needs UNLOCK) */
    GL_CMD_STREAM = 0x0C,       /**< -> source mask (2), period ms (2)  <- - */
    GL_CMD_SET_TIME = 0x0D,     /**< -> RTC seconds (4)     <- - */
    GL_CMD_UNLOCK = 0x0E,       /**< -> "GLFC" unlocks, anything else locks  <- - */
    GL_CMD_REBOOT = 0x0F        /**< -> "BOOT" normal reset, "DFU!" ROM DFU  <- - (sent before reset) */
} gl_proto_cmd_t;

/** Calibration procedures for GL_CMD_START_CAL. */
typedef enum {
    GL_CALPROC_FLIP = 1,        /**< user flip calibration in the cradle */
    GL_CALPROC_SIX_FACE = 2,    /**< arg = face 0..5 (+x,-x,+y,-y,+z,-z up); arg 6 = compute and store */
    GL_CALPROC_GRAIN_WHITE = 3, /**< white-tile gain calibration */
    GL_CALPROC_GRAIN_FLOOR = 4, /**< arg = number of no-grain readings to collect (gate 0) */
    GL_CALPROC_CAM_HORIZON = 5, /**< camera pitch / roll against a level target */
    GL_CALPROC_ABORT = 0x7F
} gl_proto_calproc_t;

/** Live stream sources (bit numbers in the GL_CMD_STREAM mask; the frame's
 *  CMD byte is GL_PROTO_STREAM_FLAG | source). */
typedef enum {
    GL_STREAM_IMU = 0,     /**< accel xyz, gyro xyz (int16 raw), temperature */
    GL_STREAM_TILT = 1,    /**< calibrated slope x, y (f32), stillness */
    GL_STREAM_GRAIN = 2,   /**< 16 x (dark, on, dark) uint16 */
    GL_STREAM_POWER = 3,   /**< battery mV, VBUS, STAT, PROG state */
    GL_STREAM_VISION = 4,  /**< per-read vision summary */
    GL_STREAM_STRIP = 5,   /**< raw strip data in chunks */
    GL_STREAM_COUNT
} gl_proto_stream_t;

typedef struct {
    uint8_t proto_version;
    uint8_t hw_rev;
    uint16_t fw_version;      /**< major << 8 | minor */
    uint32_t fw_build;        /**< build counter or date code */
    uint32_t solver_version;  /**< gl_solver_version(); 0 = stub */
    uint8_t unique_id[12];
    uint32_t uptime_s;
} gl_proto_info_t;
#define GL_PROTO_INFO_LEN 28u

typedef struct {
    uint16_t battery_mv;
    int16_t temperature_c_x10;
    uint8_t ui_state;          /**< gl_ui_state_t */
    uint8_t flags;             /**< bit0 VBUS, bit1 charging, bit2 charge enabled, bit3 unlocked */
    uint16_t last_error;       /**< gl_status_t of the last failed operation */
    uint32_t reads_total;
    uint32_t rtc_s;
} gl_proto_status_t;
#define GL_PROTO_STATUS_LEN 16u

typedef struct {
    uint32_t record_count;
    uint32_t bytes_used;
    uint32_t bytes_capacity;
    uint32_t newest_seq;
} gl_proto_log_info_t;
#define GL_PROTO_LOG_INFO_LEN 16u

/** Application callbacks.  Any pointer may be NULL: the command then
 *  answers GL_ERR_UNSUPPORTED.  All are called from gl_proto_feed(). */
typedef struct {
    void *ctx;
    /** Transmit `len` bytes of a complete frame (mandatory). */
    void (*tx)(void *ctx, const uint8_t *frame, size_t len);
    gl_status_t (*get_info)(void *ctx, gl_proto_info_t *info);
    gl_status_t (*get_status)(void *ctx, gl_proto_status_t *st);
    gl_status_t (*get_settings)(void *ctx, gl_settings_t *s);
    /** Receives settings that already passed gl_settings_decode(). */
    gl_status_t (*set_settings)(void *ctx, const gl_settings_t *s);
    gl_status_t (*get_cal)(void *ctx, uint8_t cal_id, uint8_t *blob, size_t cap, size_t *len);
    /** The blob has NOT been validated: the callee decodes it. */
    gl_status_t (*set_cal)(void *ctx, uint8_t cal_id, const uint8_t *blob, size_t len);
    gl_status_t (*start_cal)(void *ctx, uint8_t procedure, uint8_t arg);
    gl_status_t (*log_info)(void *ctx, gl_proto_log_info_t *info);
    /** Fill `buf` with whole log records, each as: type (1), flags (1),
     *  len (2), seq (4), payload (len).  restart = begin at the oldest
     *  record.  *more = false after the newest record has been returned. */
    gl_status_t (*log_read)(void *ctx, bool restart, uint8_t *buf, size_t cap, size_t *len,
                            bool *more);
    gl_status_t (*log_erase)(void *ctx);
    gl_status_t (*stream)(void *ctx, uint16_t source_mask, uint16_t period_ms);
    gl_status_t (*set_time)(void *ctx, uint32_t rtc_s);
    /** Called AFTER the response has been handed to tx(). */
    gl_status_t (*reboot)(void *ctx, bool rom_dfu);
} gl_proto_ops_t;

typedef struct {
    uint32_t frames_ok;
    uint32_t crc_errors;
    uint32_t length_errors;
    uint32_t bytes_discarded;
} gl_proto_stats_t;

typedef struct {
    uint8_t rx[GL_PROTO_MAX_FRAME];
    uint8_t tx[GL_PROTO_MAX_FRAME];
    size_t rx_start; /**< first unconsumed byte in rx */
    size_t rx_end;   /**< one past the last received byte */
    const gl_proto_ops_t *ops;
    gl_proto_stats_t stats;
    uint8_t stream_seq;
    bool unlocked;
} gl_proto_t;

/** Prepare a protocol instance.  `ops` and ops->tx must be non-NULL and
 *  outlive the instance. */
void gl_proto_init(gl_proto_t *p, const gl_proto_ops_t *ops);

/** Push received bytes.  Complete valid frames are dispatched (and their
 *  responses transmitted) before this returns. */
void gl_proto_feed(gl_proto_t *p, const uint8_t *data, size_t len);

/** Drop any partial frame.  Call when the line has been idle ~100 ms. */
void gl_proto_rx_reset(gl_proto_t *p);

/** USB detached: drop any partial frame and re-lock the factory commands. */
void gl_proto_disconnect(gl_proto_t *p);

/** Send an unsolicited stream frame.  GL_ERR_PARAM if too long. */
gl_status_t gl_proto_send_stream(gl_proto_t *p, gl_proto_stream_t source, const uint8_t *payload,
                                 size_t len);

/** Build a frame into `out`.  Returns the frame length, or 0 if it does
 *  not fit or len > GL_PROTO_MAX_PAYLOAD.  `payload` may be NULL if len is 0. */
size_t gl_proto_encode(uint8_t *out, size_t cap, uint8_t seq, uint8_t cmd, const uint8_t *payload,
                       size_t len);

/** Serialise / parse the fixed-layout records (also used by host tools). */
void gl_proto_info_encode(const gl_proto_info_t *info, uint8_t out[GL_PROTO_INFO_LEN]);
void gl_proto_status_encode(const gl_proto_status_t *st, uint8_t out[GL_PROTO_STATUS_LEN]);
void gl_proto_log_info_encode(const gl_proto_log_info_t *li, uint8_t out[GL_PROTO_LOG_INFO_LEN]);

#endif /* GL_PROTO_H */
