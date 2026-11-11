/*
 * gl_app_cfg.h - tuning constants and the flash layout of the application.
 *
 * These are OUR choices (timing of gestures, repeat counts, memory layout),
 * not hardware facts; hardware facts that are still provisional live in
 * core/gl_provisional.h.  None of them has been tuned on hardware: no
 * hardware exists yet.
 */
#ifndef GL_APP_CFG_H
#define GL_APP_CFG_H

#define GL_APP_FW_VERSION 0x0001u /* major << 8 | minor: 0.1, phase 1 */
#define GL_APP_FW_BUILD 20261111u
#define GL_APP_HW_REV 3u          /* 'C' */

/* ---- stillness, motion, gestures (IMU at 240 Hz, 32-sample blocks) -------- */

/** Consecutive still blocks that make "still for 0.5 s" (4 x 133 ms). */
#define GL_APP_STILL_BLOCKS 4u
/** Still blocks averaged for one tilt read (8 x 133 ms = 1.07 s). */
#define GL_APP_TILT_BLOCKS 8u
/** While a result is shown, GL_EV_MOTION needs this many moving blocks in a
 *  row (1.07 s: longer than any double tap) ... */
#define GL_APP_MOTION_BLOCKS 8u
/** ... or the block-mean gravity direction displaced by more than this from
 *  where it was when the marker came to rest, for 2 blocks (the marker was
 *  picked up or tilted; a tap does not move the mean), in g. */
#define GL_APP_DISPLACE_G 0.05f
#define GL_APP_DISPLACE_BLOCKS 2u
/** Double-tap detector: sample-to-sample jerk that counts as a tap, in g. */
#define GL_APP_TAP_THRESHOLD_G 0.6f
/** Time a posture (flat / upright) must persist before it is acted on. */
#define GL_APP_POSTURE_DWELL_MS 400u

/* ---- read sequence --------------------------------------------------------- */

/** L R R L groups per read (DESIGN: default 8 -> 32 strips). */
#define GL_APP_LRRL_REPEATS 8u
/** Horizon band and flagstick strip sizes, sensor pixels. */
#define GL_APP_BAND_W 640u
#define GL_APP_BAND_H 96u
#define GL_APP_STRIP_W 96u
#define GL_APP_STRIP_H 480u
/** The right camera sees the stick further LEFT by the disparity (0..16 px
 *  for 0.8 m and beyond): its strip window and its first search are shifted
 *  left by these amounts relative to the left camera's. */
#define GL_APP_RIGHT_WINDOW_SHIFT_PX 8
#define GL_APP_RIGHT_PRIOR_SHIFT_PX 6.0f
#define GL_APP_FIRST_SEARCH_PX 10.0f
/** Length of stick, up from its lowest visible point, used for the
 *  disparity (DESIGN: lowest 0.3-0.5 m). */
#define GL_APP_SEGMENT_LENGTH_M 0.4f
/** Rows ignored at the very bottom of the stick (partly covered rows). */
#define GL_APP_SEGMENT_SKIP_ROWS 2.0f
/** One-sigma of the averaged base / top row used for the elevation
 *  uncertainty (covers the +0.3 row bias at the turf horizon), rows. */
#define GL_APP_ELEV_SIGMA_ROWS 0.3f
/** Groups that must succeed for a read to count as "flagstick measured". */
#define GL_APP_MIN_GROUPS 2u

/* ---- power and housekeeping ------------------------------------------------- */

/** Wake-up interrupts of the IMU are ignored for this long after the device
 *  went to sleep: the first samples after the IMU's mode change may trip its
 *  slope detector (behaviour unknown; without this a spurious wake would
 *  repeat for ever). */
#define GL_APP_WAKE_HOLDOFF_MS 300u
/** While asleep the MCU wakes this often to kick the watchdog. */
#define GL_APP_SLEEP_HOUSEKEEP_MS 16000u
/** Battery measurement interval while awake / in the cradle. */
#define GL_APP_BATT_PERIOD_MS 30000u
/** How long "SAVED" stays on the screen after a zeroing. */
#define GL_APP_ZERO_SAVED_MS 1500u
/** Largest device bias a zeroing may store (rise/run); more means the
 *  marker was not on a hard flat surface or was disturbed. */
#define GL_APP_ZERO_MAX_BIAS 0.05f
/** The turn of a zeroing must have rotated at least this far before the
 *  second read is accepted, rad. */
#define GL_APP_ZERO_MIN_TURN_RAD 1.5f

/* ---- SPI NOR layout (MX25R6435F, 4 kB sectors, 2048 of them) ---------------- */

#define GL_APP_STORE_BASE 0x000000u
#define GL_APP_STORE_SECTORS 4u
#define GL_APP_LOG_BASE (GL_APP_STORE_SECTORS * 4096u)
#define GL_APP_LOG_SECTORS (2048u - GL_APP_STORE_SECTORS)
/** Pixel bytes per raw-strip log record.  A record must fit one LOG_READ
 *  response of the USB protocol (1022 bytes for the 8-byte record prefix +
 *  payload, so the payload limit is 1014): 18-byte chunk header + 960 pixel
 *  bytes = 10 rows of a stick strip; a 96 x 480 strip is 48 records. */
#define GL_APP_RAW_CHUNK_BYTES 960u

/* ---- log event codes (gl_log_event_t.code) ---------------------------------- */

#define GL_APP_LOGEV_BOOT 1u        /* arg = reset reason flags */
#define GL_APP_LOGEV_FAULT 2u       /* arg = gl_status_t */
#define GL_APP_LOGEV_ZEROED 3u      /* arg = bias magnitude in micro-rise/run */
#define GL_APP_LOGEV_SIX_FACE 4u    /* arg = gl_status_t of the solve */
#define GL_APP_LOGEV_GRAIN_WHITE 5u /* arg = gl_status_t */

#endif /* GL_APP_CFG_H */
