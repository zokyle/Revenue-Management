/*
 * gl_proto.h - framed binary protocol over the USB CDC-ACM port (USB exists
 * only while the marker sits in the charging / data cradle).
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
/* VERSIONS AND NEGOTIATION.  The framing has never changed and will not:
 * a version only adds commands (and may add bytes at the END of a response;
 * a host must accept a response longer than it knows).
 *   1  phases 1 and 2: commands 0x01 .. 0x0F
 *   2  rev E: GL_CMD_SHIP_MODE, GL_CMD_GET_POWER, GL_CMD_SET_CHARGE
 *   3  phase 3: the factory and calibration commands 0x13 .. 0x23; ship mode
 *      needs UNLOCK; calibration records of version 2 (gl_cal.h)
 * A host sends GL_CMD_GET_IDENT with ITS version first.  The answer carries
 * the unit's version, the version both speak (the lower one) and a bit map
 * of the command ids this unit implements; the host uses no command outside
 * it.  A unit of version 1 or 2 answers GET_IDENT with GL_ERR_UNSUPPORTED
 * (as every unit answers every command it does not know): the host then
 * falls back to GL_CMD_GET_INFO, whose first byte is the version.
 *
 * UNLOCK - THE RULE.  GL_CMD_UNLOCK with the four bytes "GLFC" unlocks,
 * anything else locks.  The unit locks itself again when USB goes (lifted
 * out of the cradle, cradle sleep after 30 s without a word from the host)
 * and at every reset.  Locked, the unit refuses with GL_ERR_STATE every
 * command that WRITES CALIBRATION or the serial number, ERASES the log, ARMS
 * a zeroing, the sleep-current test or SHIP MODE, holds the charge stopped,
 * or leaves for the update loader: SET_CAL, START_CAL (but ABORT), LOG_ERASE,
 * REBOOT "DFU!", SHIP_MODE "SHIP", SET_CHARGE, LEVEL_ZERO arm, TILT_TEMPCO,
 * SET_CAM_HORIZON, SET_GRAIN_FLOOR, DISPLAY_ROT write, GRAIN_TEST with
 * "store", SLEEP_TEST, SERIAL commit.  Reading, the tests that change
 * nothing (camera, display, grain, sensors) and the user's own settings
 * need no unlock.  The four bytes are a guard against accidents and stray
 * bytes, NOT a secret: anyone with a cradle and this file can send them.
 *
 * BAD ARGUMENTS.  Every command answers with a status byte: GL_ERR_PARAM
 * for a payload of the wrong length or with a field outside its range,
 * GL_ERR_STATE when it is not allowed now (locked, a read or another test
 * running, no VBUS), GL_ERR_UNSUPPORTED for a command or option this unit
 * does not have, GL_ERR_BUSY when the device it needs is occupied, and the
 * device's own error (GL_ERR_IO, _TIMEOUT, _NOT_FOUND, _RANGE, _CRC)
 * otherwise.  An error response carries the status byte only. */
#define GL_PROTO_VERSION 3u

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
    GL_CMD_START_CAL = 0x08,    /**< -> procedure (1), arg (1)  <- -   (needs UNLOCK, except
                                     ABORT and ZERO, see gl_proto_calproc_t) */
    GL_CMD_LOG_INFO = 0x09,     /**< -> -                   <- gl_proto_log_info_t, 16 bytes */
    GL_CMD_LOG_READ = 0x0A,     /**< -> restart flag (1)    <- more flag (1) + record stream */
    GL_CMD_LOG_ERASE = 0x0B,    /**< -> "ERAS"              <- -   (needs UNLOCK) */
    GL_CMD_STREAM = 0x0C,       /**< -> source mask (2), period ms (2)  <- - */
    GL_CMD_SET_TIME = 0x0D,     /**< -> RTC seconds (4)     <- - */
    GL_CMD_UNLOCK = 0x0E,       /**< -> "GLFC" unlocks (GL_OK), anything else locks (and
                                     answers GL_ERR_PARAM)  <- - */
    GL_CMD_REBOOT = 0x0F,       /**< -> "BOOT" normal reset, "DFU!" ROM DFU (needs UNLOCK: the ROM
                                     bootloader has no time-out)  <- - (sent before reset) */
    /* rev E: power */
    GL_CMD_SHIP_MODE = 0x10,    /**< -> "SHIP" arms ship mode (needs UNLOCK), "STAY" disarms
                                     it  <- armed (1).
                                     ARMED, the marker enters ship mode (DESIGN_SPEC E13: its
                                     lowest-power state, wake-on-motion off) when it is next
                                     lifted out of the cradle, and leaves it only when VBUS
                                     appears again.  Until then it answers as usual */
    GL_CMD_GET_POWER = 0x11,    /**< -> -                   <- gl_proto_power_t, 16 bytes: the
                                     cell thermistor, the charger, the cradle state */
    GL_CMD_SET_CHARGE = 0x12,   /**< -> 1 = hold the charge stopped, 0 = automatic  <- -
                                     (needs UNLOCK; forgotten when VBUS goes or the MCU
                                     resets).  For the station test that proves the
                                     charger's own thermistor input and its stop */
    /* ---- phase 3: factory and calibration (app/gl_factory.c).  "U" = needs UNLOCK ---- */
    GL_CMD_GET_IDENT = 0x13,    /**< -> [host protocol version (1)]  <- gl_proto_ident_t (72):
                                     model, hardware revision, firmware / solver / calibration
                                     versions, unique number, serial, the command bit map */
    GL_CMD_GET_SENSORS = 0x14,  /**< -> -  <- gl_proto_sensors_t (28): both of the MCU's
                                     temperatures, the cell thermistor NTC2 with its raw
                                     reading, the IMU's, the cell voltage, the 2.8 V rail */
    GL_CMD_CAM_ID = 0x15,       /**< -> camera (1: 0 left, 1 right)  <- camera (1), product id
                                     (2), status of the other camera's power-up (1).  Powers
                                     the camera rail for about 0.1 s */
    GL_CMD_CAM_CAPTURE = 0x16,  /**< -> camera (1), kind (1: gl_proto_capture_kind_t), x0 (2),
                                     y0 (2), width (2), height (2)  <- gl_proto_capture_t (26).
                                     One exposure of a window of at most
                                     GL_PROTO_CAPTURE_MAX_BYTES pixels into the unit's image
                                     memory; the pixels are fetched with GL_CMD_CAM_DATA */
    GL_CMD_CAM_DATA = 0x17,     /**< -> offset (4), length (2, <= 1000)  <- offset (4) + bytes
                                     of the last capture (row-major, 8-bit luma).  Any order,
                                     any number of times: a broken download is resumed at the
                                     offset it stopped at */
    GL_CMD_CAM_FIELD = 0x18,    /**< -> camera (1)  <- gl_proto_field_t (20): TEST GATE 2.  The
                                     brightness of the rows that image bars at +13.0 and at
                                     -13.0 degrees elevation (DESIGN_SPEC E17) */
    GL_CMD_DISPLAY_TEST = 0x19, /**< -> pattern (1: gl_proto_pattern_t), hold seconds (1:
                                     1..120)  <- pattern (1), CRC-32 of the frame buffer shown
                                     (4), black pixels in it (2) */
    GL_CMD_GRAIN_TEST = 0x1A,   /**< -> mode (1: gl_proto_grain_mode_t)  <- gl_proto_grain_t
                                     (108): the photodiode dark offset and one cycle of all
                                     16 LEDs.  Mode STORE (U) also records the dark offset in
                                     the grain calibration record (assembly step 11a) */
    GL_CMD_LEVEL_ZERO = 0x1B,   /**< -> op (1: gl_proto_zero_op_t), seat (1: 0 base face, 1 ball
                                     feet)  <- gl_proto_zero_t (36).  ARM (U): the zeroing for
                                     that seat runs BY ITSELF after the marker has been lifted
                                     off the contacts and has come to rest on the seat plate
                                     (read, turn 180 degrees into the other nest, read), with
                                     nothing on its pads; the result is fetched with STATUS
                                     when it is docked again */
    GL_CMD_CAL_STATUS = 0x1C,   /**< -> -  <- gl_proto_six_t (80): progress of the six-face
                                     calibration (faces captured, the face being averaged, the
                                     six raw means) - the steps themselves are
                                     GL_CMD_START_CAL GL_CALPROC_SIX_FACE */
    GL_CMD_TILT_TEMPCO = 0x1D,  /**< U -> n (1: 3..16), t0 (f32, deg C), n x [temperature
                                     (f32), offset x, y, z (3 x f32, g)]  <- b0 (3 x f32), b1
                                     (3 x f32), b2 (3 x f32), RMS residual of the fit (f32, g).
                                     Fits the offset polynomial and stores it */
    GL_CMD_SET_CAM_HORIZON = 0x1E, /**< U -> camera (1), row (f32), roll (f32, rad)
                                     <- pitch_up_rad (f32).  CAM_HORIZON: gl_cal_cam_set_horizon */
    GL_CMD_SET_GRAIN_FLOOR = 0x1F, /**< U -> n (1: 20..64), n x modulation (f32) of no-grain
                                     readings  <- noise floor (f32), threshold (f32).
                                     GRAIN_FLOOR: gl_grain_noise_floor(), stored */
    GL_CMD_DISPLAY_ROT = 0x20,  /**< -> 0  <- rotation (f32, rad), measured flag (1)
                                     U -> 1, rotation (f32, rad)  <- the same.  The stored
                                     display rotation of E12 (gl_cal_device_t.display_rot_rad:
                                     the angle the drawn line is TURNED by) */
    GL_CMD_SLEEP_TEST = 0x21,   /**< U -> wake mask (1: GL_PROTO_WAKE_*), seconds (2)
                                     <- armed (1), wake mask (1).  Sleep-current test: armed,
                                     the marker goes to sleep 1 s after VBUS has gone, wakes
                                     ONLY on the stated conditions, and reports how long it
                                     slept and what woke it in GL_CMD_GET_SENSORS.  Mask 0
                                     disarms */
    GL_CMD_LOG_SEEK = 0x22,     /**< -> first record sequence number wanted (4)  <- -.  RESUME:
                                     the next GL_CMD_LOG_READ (restart flag 0) returns the
                                     records from that number on */
    GL_CMD_SERIAL = 0x23        /**< -> -  <- serial (4), text (7), stored flag (1)
                                     U -> "SNUM"  <- the same: record the processor's unique
                                     number and the serial derived from it in the device
                                     calibration record */
} gl_proto_cmd_t;

#define GL_PROTO_CMD_FACTORY_FIRST GL_CMD_GET_IDENT
#define GL_PROTO_CMD_FACTORY_LAST GL_CMD_SERIAL

/** GL_CMD_CAM_CAPTURE kinds. */
typedef enum {
    GL_CAPTURE_NORMAL = 0, /**< a picture */
    GL_CAPTURE_DARK = 1    /**< a DARK FRAME: the same exposure (the driver has no exposure
                                control: the sensor's own loop runs), reported with the
                                statistics a light-leak test needs (bright-pixel count) */
} gl_proto_capture_kind_t;
/** Largest window of one capture, pixels = bytes (640 x 288, or 640 x 240 for
 *  half a frame: a whole 640 x 480 frame is two exposures). */
#define GL_PROTO_CAPTURE_MAX_BYTES 184320u
#define GL_PROTO_CAM_DATA_MAX 1000u
/** A dark-frame pixel above this many grey levels counts as bright. */
#define GL_PROTO_DARK_BRIGHT_LEVEL 32u

typedef struct {
    uint8_t camera, kind;
    uint16_t x0, y0, width, height; /**< the window ACTUALLY captured */
    uint32_t bytes;                 /**< width * height */
    uint8_t min, max;
    uint16_t mean_x16;              /**< mean grey level x 16 */
    uint32_t bright;                /**< pixels above GL_PROTO_DARK_BRIGHT_LEVEL */
    uint32_t crc32;                 /**< CRC-32 of the pixel bytes */
} gl_proto_capture_t;
#define GL_PROTO_CAPTURE_LEN 26u

/** GL_CMD_CAM_FIELD: test gate 2.  Elevations in the marker frame (above the
 *  base plane), converted to sensor rows with the camera's calibration
 *  record. */
#define GL_PROTO_FIELD_ELEV_DEG 13.0f
#define GL_PROTO_FIELD_HALF_ROWS 3u    /**< rows averaged either side of each bar's row */
#define GL_PROTO_FIELD_COLS 320u       /**< columns averaged, centred */
typedef struct {
    uint8_t camera;
    uint8_t status;         /**< 0 = both bars inside the sensor */
    uint16_t row_upper;     /**< sensor row that images +13.0 degrees */
    uint16_t row_lower;     /**< ... -13.0 degrees */
    uint16_t mean_upper_x16;/**< mean grey level x 16 of the rows about row_upper */
    uint16_t mean_lower_x16;
    uint16_t mean_centre_x16; /**< the same about the optical centre row (reference) */
    uint16_t ratio_x1000;   /**< upper / lower x 1000 (65535 = lower bar black) */
    uint8_t max_upper, max_lower;
    uint32_t reserved;
} gl_proto_field_t;
#define GL_PROTO_FIELD_LEN 20u

/** GL_CMD_DISPLAY_TEST patterns.  All fill the whole 128 x 128 panel (the
 *  round aperture hides the corners). */
typedef enum {
    GL_DISP_PATTERN_NORMAL = 0,   /**< back to the ordinary screen */
    GL_DISP_PATTERN_WHITE = 1,    /**< all pixels reflective */
    GL_DISP_PATTERN_BLACK = 2,
    GL_DISP_PATTERN_CHECKER_1 = 3,/**< 1-pixel chequerboard: every line and column toggles */
    GL_DISP_PATTERN_CHECKER_8 = 4,/**< 8-pixel chequerboard */
    GL_DISP_PATTERN_ROWS = 5,     /**< every other ROW black: a dead or shorted gate line shows */
    GL_DISP_PATTERN_COLUMNS = 6,  /**< every other COLUMN black */
    GL_DISP_PATTERN_ORIENT = 7,   /**< a frame, a centre cross and an "F": mirrored or turned
                                       panels are seen at once */
    GL_DISP_PATTERN_REF_RAW = 8,  /**< THE REFERENCE LINE for measuring the display rotation: a
                                       3-pixel line along the marker's forward axis through
                                       the screen centre, drawn WITHOUT the stored rotation */
    GL_DISP_PATTERN_REF_CORRECTED = 9, /**< the same line turned by the stored rotation: after
                                       the factory has written it, this line must lie along
                                       the visor flat's normal */
    GL_DISP_PATTERN_COUNT
} gl_proto_pattern_t;

typedef enum {
    GL_GRAIN_MODE_DARK = 0,   /**< dark offset only (LEDs off): the bare-board test of step 11a */
    GL_GRAIN_MODE_CYCLE = 1,  /**< dark offset, then all 16 LEDs once (dark, on, dark) */
    GL_GRAIN_MODE_STORE = 2   /**< as DARK, and the offset is stored (needs UNLOCK) */
} gl_proto_grain_mode_t;
#define GL_PROTO_GRAIN_DARK_SAMPLES 16u
typedef struct {
    uint8_t mode;
    uint8_t status;             /**< gl_status_t of the LED cycle (GL_ERR_EMPTY: not run) */
    uint16_t dark_mean;         /**< mean of GL_PROTO_GRAIN_DARK_SAMPLES readings, LEDs off, counts */
    uint16_t dark_min, dark_max;
    uint16_t full_scale;        /**< ADC full scale, counts */
    uint16_t stored_dark;       /**< the dark offset in the calibration record (0 = none) */
    uint16_t led[16][3];        /**< dark, on, dark per LED (0..7 red, 8..15 near-infrared) */
} gl_proto_grain_t;
#define GL_PROTO_GRAIN_LEN 108u

typedef enum {
    GL_ZERO_OP_STATUS = 0,
    GL_ZERO_OP_ARM = 1,     /**< needs UNLOCK */
    GL_ZERO_OP_CANCEL = 2
} gl_proto_zero_op_t;
typedef enum {
    GL_ZERO_STATE_IDLE = 0,    /**< nothing armed, no result */
    GL_ZERO_STATE_ARMED = 1,   /**< will run when the marker lies still out of the cradle */
    GL_ZERO_STATE_RUNNING = 2,
    GL_ZERO_STATE_DONE = 3,    /**< stored: the fields below are its result */
    GL_ZERO_STATE_FAILED = 4   /**< `status` says why (GL_ERR_MOTION, _RANGE: turn not near 180
                                    degrees or bias above 5 %, _TIMEOUT); nothing was stored */
} gl_proto_zero_state_t;
typedef struct {
    uint8_t state;          /**< gl_proto_zero_state_t */
    uint8_t seat;           /**< seat armed / of the result */
    uint8_t status;         /**< gl_status_t of the last attempt */
    uint8_t attempts;       /**< attempts made since it was armed */
    float bias_x, bias_y;   /**< the zero found, rise/run, marker axes */
    float scatter;          /**< RMS of the block slopes about their mean, the worse read */
    float turn_rad;         /**< the turn the gyroscope measured between the two reads */
    float surface_x, surface_y; /**< slope of the plate itself (what the reversal removed) */
    float temp_c;           /**< IMU temperature at the zeroing */
    uint32_t time_s;        /**< RTC seconds at the zeroing */
} gl_proto_zero_t;
#define GL_PROTO_ZERO_LEN 36u

typedef struct {
    uint8_t done_mask;      /**< bit f: face f captured */
    uint8_t active;         /**< 1: an average is running */
    uint8_t face;           /**< the face being / last averaged */
    uint8_t cal_flags;      /**< flags of the tilt record (bit 0: six-face stored) */
    float mean[6][3];       /**< raw mean acceleration per captured face, g */
    float temp_c;           /**< IMU temperature now */
} gl_proto_six_t;
#define GL_PROTO_SIX_LEN 80u

#define GL_PROTO_TEMPCO_MIN_POINTS 3u
#define GL_PROTO_TEMPCO_MAX_POINTS 16u
#define GL_PROTO_FLOOR_MIN_READINGS 20u /* what gl_grain_noise_floor() needs */
#define GL_PROTO_FLOOR_MAX_READINGS 64u

/** GL_CMD_SLEEP_TEST wake conditions. */
#define GL_PROTO_WAKE_MOTION (1u << 0)  /**< the IMU's wake-on-motion, as in the product */
#define GL_PROTO_WAKE_TIMER (1u << 1)   /**< after `seconds` */
#define GL_PROTO_WAKE_VBUS (1u << 2)    /**< VBUS: always a wake condition (it cannot be masked:
                                             the way back to the PC), set in the answer */

typedef struct {
    uint8_t proto_version;
    uint8_t agreed_version;   /**< min(host's, ours); ours if the host sent none */
    uint8_t hw_rev;           /**< 5 */
    char hw_letter;           /**< 'E' */
    char model[8];            /**< "GL-1", NUL padded */
    uint16_t fw_version;
    uint8_t cal_version;      /**< GL_CAL_VERSION */
    uint8_t log_layout;       /**< GL_FIELDLOG_LAYOUT */
    uint32_t fw_build;
    uint32_t solver_version;
    uint8_t unique_id[12];
    uint32_t serial;          /**< derived from unique_id now */
    uint32_t serial_stored;   /**< the one in the device calibration record, 0 = none */
    uint8_t cal_flags[5];     /**< tilt, left camera, right camera, grain, device */
    uint8_t flags;            /**< GL_PROTO_IDENT_* */
    char params_rev[14];      /**< revision string of design/master_params.yaml the firmware
                                   was generated from, NUL padded */
    uint8_t commands[8];      /**< bit c of byte c / 8: command id c is implemented */
} gl_proto_ident_t;
#define GL_PROTO_IDENT_LEN 72u
#define GL_PROTO_IDENT_SERIAL_STORED (1u << 0)
#define GL_PROTO_IDENT_SERIAL_MATCH (1u << 1)  /**< the stored unique number is this processor's:
                                                    the calibration was made on THIS board */
#define GL_PROTO_IDENT_RELEASE (1u << 2)       /**< release build (assigned USB ids) */
#define GL_PROTO_IDENT_UNLOCKED (1u << 3)
#define GL_PROTO_IDENT_CAL_COMPLETE (1u << 4)  /**< every flag the final test asks for is set:
                                                    six-face, both zeros, temperature fit, both
                                                    cameras' intrinsics / extrinsics / horizon,
                                                    white reference, display rotation, serial */

typedef struct {
    uint16_t battery_mv;
    uint16_t vdda_mv;          /**< the 2.8 V rail, measured against the MCU's reference */
    int16_t cell_temp_c_x10;   /**< NTC2, GL_PROTO_TEMP_NONE if not valid */
    int16_t mcu_temp_c_x10;
    int16_t imu_temp_c_x10;
    uint16_t ntc_counts;       /**< raw NTC2 reading, counts of ntc_full_scale */
    uint16_t ntc_full_scale;
    uint8_t ntc_fault;         /**< gl_ntc_fault_t */
    uint8_t flags;             /**< bit0 VBUS, bit1 USB supply valid, bit2 camera rail on, bit3
                                    charger status output low, bit4 CHG_INHIBIT driven, bit5 a
                                    sleep test is armed */
    uint8_t sleep_wake;        /**< what ended the last sleep test: GL_PROTO_WAKE_* (0 = none
                                    has run) */
    uint8_t sleep_mask;        /**< its wake mask */
    uint32_t sleep_ms;         /**< how long it slept */
    uint32_t uptime_ms;
    uint16_t reserved;
} gl_proto_sensors_t;
#define GL_PROTO_SENSORS_LEN 28u

/** Calibration procedures for GL_CMD_START_CAL. */
typedef enum {
    GL_CALPROC_ZERO = 1,        /**< user zeroing (read, turn 180 degrees, read) on a hard flat
                                     surface.  It CANNOT run in the cradle, and USB exists only
                                     in the cradle, so the application answers GL_ERR_STATE;
                                     the routine is started from the settings dial.  The id is
                                     kept so that a host gets a defined answer. */
    GL_CALPROC_SIX_FACE = 2,    /**< arg = face 0..5 (+x,-x,+y,-y,+z,-z up); arg 6 = compute and store */
    GL_CALPROC_GRAIN_WHITE = 3, /**< white-tile gain calibration */
    GL_CALPROC_GRAIN_FLOOR = 4, /**< GL_ERR_UNSUPPORTED: the readings are taken on turf, out
                                     of the cradle; the PC sends them with
                                     GL_CMD_SET_GRAIN_FLOOR */
    GL_CALPROC_CAM_HORIZON = 5, /**< GL_ERR_UNSUPPORTED: the PC measures the row in a frame
                                     (GL_CMD_CAM_CAPTURE) and writes it with
                                     GL_CMD_SET_CAM_HORIZON */
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
    uint8_t flags;             /**< bit0 VBUS, bit1 charging (the charger says so), bit2 the
                                    firmware does not stop the charge, bit3 unlocked, bit4 ship
                                    mode armed */
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

/** Temperature that could not be measured, in the x10 fields below. */
#define GL_PROTO_TEMP_NONE INT16_MIN

/** GL_CMD_GET_POWER.  The enumerations are those of drivers/power.h; they
 *  are carried as bytes (this module does not include drivers). */
typedef struct {
    uint16_t battery_mv;
    int16_t cell_temp_c_x10;   /**< the MCU's cell thermistor (NTC2), GL_PROTO_TEMP_NONE if not valid */
    int16_t mcu_temp_c_x10;    /**< MCU die sensor */
    int16_t imu_temp_c_x10;    /**< IMU die sensor */
    uint8_t ntc_fault;         /**< gl_ntc_fault_t of the last NTC2 measurement */
    uint8_t chg_status;        /**< gl_chg_status_t: what the charger does, as far as known */
    uint8_t chg_reason;        /**< gl_chg_reason_t: why the firmware stops the charge, if it does */
    uint8_t cradle;            /**< 0 out of the cradle, 1 in it and awake (USB), 2 asleep in it */
    uint16_t flags;            /**< GL_PROTO_PWR_* */
    uint16_t charge_min;       /**< minutes of continuous charging so far */
} gl_proto_power_t;
#define GL_PROTO_POWER_LEN 16u
#define GL_PROTO_PWR_VBUS (1u << 0)
#define GL_PROTO_PWR_CHG_LOW (1u << 1)      /**< the charger's status output is low: charging */
#define GL_PROTO_PWR_INHIBIT (1u << 2)      /**< the firmware drives CHG_INHIBIT high */
#define GL_PROTO_PWR_USB_SUPPLY (1u << 3)   /**< the MCU's USB supply is valid */
#define GL_PROTO_PWR_SHIP_ARMED (1u << 4)
#define GL_PROTO_PWR_READ_HOT (1u << 5)     /**< E13: too hot for a camera read */
#define GL_PROTO_PWR_NTC1_SUSPECT (1u << 6) /**< a charge ran outside the charger's own window */
#define GL_PROTO_PWR_TIME_LIMIT (1u << 7)   /**< the 6 h limit holds the charge stopped */
#define GL_PROTO_PWR_FORCED (1u << 8)       /**< a command holds the charge stopped */
#define GL_PROTO_PWR_CELL_FRESH (1u << 9)   /**< the temperatures were measured within the last
                                                 supervision period */

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
    /** Optional: may the device go to the ROM bootloader NOW?  Asked before
     *  the answer to GL_CMD_REBOOT "DFU!" is sent; false answers
     *  GL_ERR_STATE.  NULL = always. */
    bool (*dfu_allowed)(void *ctx);
    /** Arm (true) or disarm ship mode; *armed receives the state afterwards. */
    gl_status_t (*ship_mode)(void *ctx, bool arm, bool *armed);
    /** Measure and report the power state. */
    gl_status_t (*get_power)(void *ctx, gl_proto_power_t *pw);
    /** Hold the charge stopped (true) or give it back to the gate (false). */
    gl_status_t (*set_charge)(void *ctx, bool stop);
    /** The factory and calibration commands GL_PROTO_CMD_FACTORY_FIRST ..
     *  _LAST.  The protocol layer has checked the payload LENGTH against its
     *  table and the UNLOCK rule; the callee checks the values, writes the
     *  response data (after the status byte) to `out` and its length to
     *  *len (<= cap).  NULL: all of them answer GL_ERR_UNSUPPORTED and are
     *  absent from the command bit map. */
    gl_status_t (*factory)(void *ctx, uint8_t cmd, const uint8_t *in, size_t n, uint8_t *out,
                           size_t cap, size_t *len);
    /** GL_CMD_LOG_SEEK. */
    gl_status_t (*log_seek)(void *ctx, uint32_t seq);
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
void gl_proto_power_encode(const gl_proto_power_t *pw, uint8_t out[GL_PROTO_POWER_LEN]);
void gl_proto_ident_encode(const gl_proto_ident_t *id, uint8_t out[GL_PROTO_IDENT_LEN]);
void gl_proto_sensors_encode(const gl_proto_sensors_t *s, uint8_t out[GL_PROTO_SENSORS_LEN]);
void gl_proto_capture_encode(const gl_proto_capture_t *c, uint8_t out[GL_PROTO_CAPTURE_LEN]);
void gl_proto_field_encode(const gl_proto_field_t *f, uint8_t out[GL_PROTO_FIELD_LEN]);
void gl_proto_grain_encode(const gl_proto_grain_t *g, uint8_t out[GL_PROTO_GRAIN_LEN]);
void gl_proto_zero_encode(const gl_proto_zero_t *z, uint8_t out[GL_PROTO_ZERO_LEN]);
void gl_proto_six_encode(const gl_proto_six_t *x, uint8_t out[GL_PROTO_SIX_LEN]);

/** The command bit map of an instance: bit c of out[c / 8] is set when
 *  command id c would not answer GL_ERR_UNSUPPORTED for want of a callback. */
void gl_proto_command_map(const gl_proto_t *p, uint8_t out[8]);

/** True when `cmd` with this payload is refused while locked (the rule in
 *  the file comment).  For hosts and tests. */
bool gl_proto_needs_unlock(uint8_t cmd, const uint8_t *payload, size_t n);

#endif /* GL_PROTO_H */
