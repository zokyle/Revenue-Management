/*
 * gl_settings.h - user settings: values, limits, defaults, storage format
 * and the item table used by the roll-to-set dial.
 *
 * Settings required by the brief: Stimp (6-14 in 0.5), units, the stopping
 * distance past the hole, grass type, grain on/off.  Added: raw-strip
 * logging level (field data collection), the manual distance used by the
 * flag-out fallback and, in phase 2, the estimator method.
 *
 * Storage / wire format (GL_SETTINGS_BLOB_LEN bytes, little-endian).  The
 * first byte is the VERSION OF THE LAYOUT; a record is never interpreted
 * with the fields of another version:
 *
 *   version 2 (written by this firmware)
 *   0 version = 2      1 stimp_x2        2 units          3 past_cm
 *   4 grass            5 grain_enable    6 raw_log_level  7 method
 *   8..9 manual_distance_cm              10..11 reserved (0)
 *
 *   version 1 (phase 1; still READ, and converted)
 *   0 version = 1      1 stimp_x2        2 units          3 pace (0 die, 1 normal, 2 firm)
 *   4 grass            5 grain_enable    6 raw_log_level  7 reserved (0)
 *   8..9 manual_distance_cm              10..11 reserved (0)
 *
 * Byte 3 is why the version matters: read with the version-2 meaning, a
 * version-1 "firm" (2) would be 2 cm past the hole.  gl_settings_decode()
 * converts a version-1 record (die / normal / firm -> 0 / 30 / 45 cm, method
 * B1) and refuses every other version; the application then keeps its
 * defaults.  A record of this firmware read by phase-1 firmware is refused
 * there the same way (unknown version).
 */
#ifndef GL_SETTINGS_H
#define GL_SETTINGS_H

#include "gl_types.h"

#define GL_SETTINGS_VERSION 2u
#define GL_SETTINGS_VERSION_PHASE1 1u
#define GL_SETTINGS_BLOB_LEN 12u

#define GL_STIMP_X2_MIN 12u /* 6.0 ft */
#define GL_STIMP_X2_MAX 28u /* 14.0 ft */
#define GL_STIMP_X2_DEFAULT 20u /* 10.0 ft */

#define GL_MANUAL_DISTANCE_MAX_CM 3000u /* 30 m */

/** Length of one pace used when distances are shown or dialled in paces. */
#define GL_PACE_LENGTH_M 0.9144f /* one yard */

typedef enum {
    GL_UNITS_FEET = 0,
    GL_UNITS_METRES = 1,
    GL_UNITS_PACES = 2,
    GL_UNITS_COUNT
} gl_units_t;

/** Stopping distance: how far past the hole the solved putt would roll on a
 *  flat green, in centimetres.  0 = dies at the hole; 30 is the reference
 *  default.  Dialled in steps of 5 cm. */
#define GL_PAST_CM_MAX 90u
#define GL_PAST_CM_STEP 5u
#define GL_PAST_CM_DEFAULT 30u

/** The pace option of the version-1 record (phase 1), for the conversion. */
typedef enum {
    GL_PACE_V1_DIE = 0,    /**< 0.00 m */
    GL_PACE_V1_NORMAL = 1, /**< 0.30 m */
    GL_PACE_V1_FIRM = 2,   /**< 0.45 m */
    GL_PACE_V1_COUNT
} gl_pace_v1_t;

/** Estimator method.  The values are those of gl_solver_method_t for the two
 *  methods a golfer may select (checked at compile time in app/gl_app.c). */
typedef enum {
    GL_METHOD_B1 = 0, /**< DEFAULT: tilt + flag-base height */
    GL_METHOD_B2 = 2, /**< B1 + turf horizon (anchored fit).  Optional: in simulation it
                           only helps on greens without a fringe */
} gl_method_t;
#define GL_METHOD_CHOICES 2

typedef enum {
    GL_GRASS_BENT = 0,
    GL_GRASS_POA = 1,
    GL_GRASS_BERMUDA = 2,
    GL_GRASS_COUNT
} gl_grass_t;

typedef enum {
    GL_RAWLOG_OFF = 0,
    GL_RAWLOG_FIRST = 1, /**< stick strips of the first L/R pair of each read */
    GL_RAWLOG_ALL = 2,   /**< every captured strip */
    GL_RAWLOG_COUNT
} gl_rawlog_t;

typedef struct {
    uint8_t stimp_x2;            /**< green speed in half feet, 12..28 */
    uint8_t units;               /**< gl_units_t */
    uint8_t past_cm;             /**< stopping distance past the hole, 0..GL_PAST_CM_MAX */
    uint8_t grass;               /**< gl_grass_t */
    uint8_t grain_enable;        /**< 0 = off (factory default), 1 = on */
    uint8_t raw_log_level;       /**< gl_rawlog_t */
    uint8_t method;              /**< gl_method_t */
    uint16_t manual_distance_cm; /**< 0 = none; else the dialled distance */
} gl_settings_t;

/** Factory defaults: Stimp 10, feet, 30 cm past the hole, bentgrass, grain
 *  OFF, method B1. */
void gl_settings_defaults(gl_settings_t *s);

/** GL_OK if every field is inside its range. */
gl_status_t gl_settings_validate(const gl_settings_t *s);

/** Serialise to GL_SETTINGS_BLOB_LEN bytes. */
void gl_settings_encode(const gl_settings_t *s, uint8_t out[GL_SETTINGS_BLOB_LEN]);

/** Parse and validate a version-2 record, or convert a version-1 one (see
 *  the file comment).  GL_ERR_PARAM on a short buffer, GL_ERR_UNSUPPORTED on
 *  any other version, GL_ERR_RANGE on an out-of-range field (of the record's
 *  OWN version).  `s` is only modified on GL_OK. */
gl_status_t gl_settings_decode(const uint8_t *blob, size_t len, gl_settings_t *s);

/** Green speed in feet (Stimpmeter reading). */
float gl_settings_stimp_ft(const gl_settings_t *s);

/** Rolling deceleration a_r in m/s^2, same formula as the Python reference:
 *  a_r = 1.83^2 / (2 * stimp_ft * 0.3048).  Stimp 10 -> 0.549 m/s^2. */
float gl_settings_decel_mps2(const gl_settings_t *s);

/** Stopping distance past the hole in metres. */
float gl_settings_past_m(const gl_settings_t *s);

/** Manual distance in metres, or 0 if none is set. */
float gl_settings_manual_distance_m(const gl_settings_t *s);

/* ---- dial item table --------------------------------------------------- */

typedef enum {
    GL_ITEM_STIMP = 0,
    GL_ITEM_UNITS,
    GL_ITEM_PACE,     /**< stopping distance past the hole ("PAST") */
    GL_ITEM_GRASS,
    GL_ITEM_GRAIN,
    GL_ITEM_DISTANCE, /**< manual distance for the flag-out fallback */
    GL_ITEM_RAWLOG,
    GL_ITEM_METHOD,   /**< estimator method: B1 (default) or B2 */
    GL_ITEM_COUNT
} gl_item_t;

/** Short upper-case label, at most 8 characters ("STIMP", "UNITS", ...). */
const char *gl_settings_item_name(gl_item_t item);

/** Inclusive range of the item's integer dial value. */
void gl_settings_item_range(gl_item_t item, int *min, int *max);

/** Current dial value of an item.  DISTANCE is in display steps: half
 *  feet, 0.2 m or half paces depending on the units; 0 = "none". */
int gl_settings_item_get(const gl_settings_t *s, gl_item_t item);

/** Set an item from a dial value (clamped to the item's range). */
void gl_settings_item_set(gl_settings_t *s, gl_item_t item, int value);

/**
 * Text of an item's value for the display, upper case, NUL terminated, at
 * most 9 characters + NUL ("10.5", "FEET", "12IN", "30CM", "BERMUDA", "OFF",
 * "12.5FT", "--", "B2 HORIZ").  `cap` must be >= 10.
 */
void gl_settings_item_format(const gl_settings_t *s, gl_item_t item, char *out, size_t cap);

/** Format a distance for the display in the selected units ("14.5FT",
 *  "4.4M", "5P").  `cap` must be >= 10. */
void gl_settings_format_distance(const gl_settings_t *s, float metres, char *out, size_t cap);

#endif /* GL_SETTINGS_H */
