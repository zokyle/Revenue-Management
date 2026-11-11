/*
 * gl_types.h - common types, status codes and small numeric helpers.
 *
 * GreenLine GL-1 firmware, portable core.  C99, no dynamic allocation,
 * single-precision float only.
 *
 * FRAMES AND SIGN CONVENTIONS (used by every core module)
 * -------------------------------------------------------
 * Marker frame "m" (same as design/master_params.yaml): origin at the puck
 * centre on the base plane, +x right, +y forward (out of the visor, toward
 * the ball and the hole), +z up, as seen from above.
 *
 * Camera frame "c": +x right along image columns, +y DOWN along image rows,
 * +z along the optical axis (nominally marker +y).  Pixel (u, v) = (column,
 * row), row 0 at the top of the upright image.
 *
 * Solver ("device") frame "d", identical to the Python reference
 * (sim/greenline_sim/measurements.py): +x out of the visor (marker +y),
 * +y to the left (marker -x), angles counter-clockwise from +x.
 *
 * Horizontal angles (bearing, aim, azimuth of a slope) are in radians,
 * COUNTER-CLOCKWISE POSITIVE seen from above, so "positive = left".
 * A bearing is measured from the marker's forward axis (+y_m) projected on
 * the gravity-level plane.  Elevation angles are positive upward from the
 * gravity-level plane through the lens.
 *
 * Slopes are rise/run (dimensionless, 0.01 = 1 %), expressed as the uphill
 * gradient vector (dz/dx, dz/dy).
 */
#ifndef GL_TYPES_H
#define GL_TYPES_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/** Status code returned by every fallible function.  0 = success. */
typedef enum {
    GL_OK = 0,
    GL_ERR_PARAM = 1,           /**< invalid argument */
    GL_ERR_NOT_IMPLEMENTED = 2, /**< phase-2 function (solver stub) */
    GL_ERR_TIMEOUT = 3,
    GL_ERR_IO = 4,              /**< bus or device error */
    GL_ERR_CRC = 5,
    GL_ERR_FULL = 6,            /**< buffer, queue or storage full */
    GL_ERR_EMPTY = 7,           /**< nothing to read */
    GL_ERR_RANGE = 8,           /**< value outside its valid range */
    GL_ERR_BUSY = 9,
    GL_ERR_NOT_FOUND = 10,      /**< record, device or target absent */
    GL_ERR_NO_STICK = 11,       /**< vision: no flagstick detected */
    GL_ERR_QUALITY = 12,        /**< measurement made but rejected */
    GL_ERR_MOTION = 13,         /**< device moved during a measurement */
    GL_ERR_CORRUPT = 14,        /**< stored data failed validation */
    GL_ERR_STATE = 15,          /**< call not allowed in this state */
    GL_ERR_UNSUPPORTED = 16
} gl_status_t;

/** Short constant name of a status code ("OK", "TIMEOUT", ...). Never NULL. */
const char *gl_status_name(gl_status_t st);

/** 2-vector and 3-vector of single-precision floats. */
typedef struct { float x, y; } gl_vec2_t;
typedef struct { float x, y, z; } gl_vec3_t;

/** Row-major 3x3 matrix: m[row][col]. */
typedef struct { float m[3][3]; } gl_mat3_t;

#define GL_PI_F        3.14159265358979f
#define GL_TWO_PI_F    6.28318530717959f
#define GL_DEG2RAD_F   0.0174532925199433f
#define GL_RAD2DEG_F   57.2957795130823f

#define GL_ARRAY_LEN(a) (sizeof(a) / sizeof((a)[0]))

/** Clamp x to [lo, hi].  A NaN comes back as `lo`, never as NaN, so that
 *  the result can always be converted to an integer. */
static inline float gl_clampf(float x, float lo, float hi)
{
    return !(x >= lo) ? lo : ((x > hi) ? hi : x);
}

/** Clamp an int to [lo, hi]. */
static inline int gl_clampi(int x, int lo, int hi)
{
    return (x < lo) ? lo : ((x > hi) ? hi : x);
}

/** Wrap an angle to (-pi, pi]. Input must be finite and within a few turns. */
float gl_wrap_pi(float a_rad);

/** Largest magnitude gl_roundi() returns (a float exactly representable
 *  as an int). */
#define GL_ROUNDI_LIMIT 2000000000

/** Round to nearest int (half away from zero) without calling libm.
 *  Saturates at +-GL_ROUNDI_LIMIT and returns 0 for NaN, so the conversion
 *  is defined for every input (C leaves an out-of-range float-to-int
 *  conversion undefined). */
static inline int gl_roundi(float x)
{
    if (!(x > -2.0e9f)) {
        return (x != x) ? 0 : -GL_ROUNDI_LIMIT;
    }
    if (x > 2.0e9f) {
        return GL_ROUNDI_LIMIT;
    }
    return (int)((x >= 0.0f) ? (x + 0.5f) : (x - 0.5f));
}

/* ---- tiny linear algebra (gl_math.c) ---------------------------------- */

/** y = M x. */
gl_vec3_t gl_mat3_mul_vec(const gl_mat3_t *m, gl_vec3_t x);
/** C = A B. */
gl_mat3_t gl_mat3_mul(const gl_mat3_t *a, const gl_mat3_t *b);
/** Transpose. */
gl_mat3_t gl_mat3_transpose(const gl_mat3_t *a);
/** Identity matrix. */
gl_mat3_t gl_mat3_identity(void);
/** Inverse by cofactors. Returns GL_ERR_RANGE if |det| < 1e-9. */
gl_status_t gl_mat3_inverse(const gl_mat3_t *a, gl_mat3_t *out);
/** Rotation matrix from small or large Euler angles: R = Rz(yaw) Ry(pitch) Rx(roll)
 *  (angles in rad, right-handed about the frame's own z, y, x axes). */
gl_mat3_t gl_mat3_from_euler(float roll_x_rad, float pitch_y_rad, float yaw_z_rad);

/** Dot product. */
float gl_vec3_dot(gl_vec3_t a, gl_vec3_t b);
/** Cross product a x b. */
gl_vec3_t gl_vec3_cross(gl_vec3_t a, gl_vec3_t b);
/** Euclidean length. */
float gl_vec3_norm(gl_vec3_t a);
/** Unit vector; returns (0,0,1) if the norm is below 1e-12. */
gl_vec3_t gl_vec3_unit(gl_vec3_t a);

/**
 * Median of n floats (n >= 1).  SORTS `v` in place, ascending (callers may
 * read other percentiles from it afterwards), with a non-recursive Shell
 * sort (O(n^1.3)); for even n returns the mean of the two middle values.
 * Stack use: a few words.
 */
float gl_median_inplace(float *v, size_t n);

/**
 * The k-th smallest (k = 0 .. n - 1; larger k are taken as n - 1) of n
 * floats, n >= 1, by selection instead of a full sort (Wirth's algorithm:
 * non-recursive, in place).  `v` is PERMUTED, not sorted: afterwards v[k]
 * holds the result, no element before it is larger and none after it is
 * smaller.  The value returned is exactly the one a full sort would put at
 * index k.  Run time: about 3 n comparisons on average; bounded - after
 * GL_SELECT_MAX_ROUNDS partition rounds the remaining range is Shell-sorted,
 * so the worst case is that many passes over the data plus one sort.
 */
#define GL_SELECT_MAX_ROUNDS 24u
float gl_select_inplace(float *v, size_t n, size_t k);

/**
 * Median of n floats (n >= 1) by selection: the same VALUE as
 * gl_median_inplace() (for even n the mean of the two middle values) at a
 * fraction of the cost; `v` is permuted, NOT sorted.  This is what the
 * vision code uses: its medians were a quarter of its run time.
 */
float gl_median_select(float *v, size_t n);

/* ---- little-endian (de)serialisation helpers --------------------------- */

/** Store / load 16- and 32-bit unsigned values as little-endian bytes. */
static inline void gl_put_u16(uint8_t *p, uint16_t v)
{
    p[0] = (uint8_t)(v & 0xFFu);
    p[1] = (uint8_t)(v >> 8);
}
static inline void gl_put_u32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)(v & 0xFFu);
    p[1] = (uint8_t)((v >> 8) & 0xFFu);
    p[2] = (uint8_t)((v >> 16) & 0xFFu);
    p[3] = (uint8_t)(v >> 24);
}
static inline uint16_t gl_get_u16(const uint8_t *p)
{
    return (uint16_t)((uint16_t)p[0] | ((uint16_t)p[1] << 8));
}
static inline uint32_t gl_get_u32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) |
           ((uint32_t)p[3] << 24);
}
/** Store / load an IEEE-754 single as 4 little-endian bytes. */
void gl_put_f32(uint8_t *p, float v);
float gl_get_f32(const uint8_t *p);

#ifdef __cplusplus
}
#endif
#endif /* GL_TYPES_H */
