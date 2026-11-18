/*
 * gl_factory.h - the factory and calibration commands of the USB protocol
 * (GL_CMD_GET_IDENT .. GL_CMD_SERIAL, core/gl_proto.h) and the three things
 * they leave running in the application: a display test pattern that holds
 * the screen, a level zero that is ARMED over USB and runs by itself when
 * the marker lies on the seat plate with nothing on its pads, and the
 * sleep-current test.
 *
 * Nothing here runs unless a host sends a command: the product behaves as
 * it does without this file.  The state is RAM only: a reset forgets an
 * armed zero, an armed sleep test and a capture.
 *
 * RAM: gl_factory_t is about 110 bytes (inside gl_app_t); gl_factory.c adds
 * 1156 bytes of static scratch (the points of the temperature fit 256, the
 * readings of the grain floor 512, one raw grain cycle 388: `make cross`,
 * bss of gl_factory).  The picture of a capture lies in the image memory of
 * the read (gl_read_t.img): a camera read overwrites it, and it is marked
 * invalid then.  Stack (-fstack-usage): gl_factory_cmd() 376 bytes below
 * the protocol's dispatch, the temperature fit 432 below that - about
 * 1.5 kB below main() with the main loop's and the USB service's frames.
 */
#ifndef GL_FACTORY_H
#define GL_FACTORY_H

#include "gl_proto.h"
#include "gl_types.h"

/** How long the armed zeroing waits for the marker to be lifted off the
 *  contacts and put down before it gives up (GL_ERR_TIMEOUT). */
#define GL_FACTORY_ZERO_ARM_TIMEOUT_MS 600000u
/** Attempts of an armed zeroing before it disarms itself. */
#define GL_FACTORY_ZERO_MAX_ATTEMPTS 3u
/** The sleep test starts this long after VBUS has gone (pin bounce). */
#define GL_FACTORY_SLEEP_SETTLE_MS 1000u

typedef struct {
    /* camera capture */
    bool cap_valid;
    gl_proto_capture_t cap;
    /* display test */
    uint8_t pattern;            /**< gl_proto_pattern_t, 0 = the ordinary screen */
    uint32_t pattern_until_ms;
    uint32_t pattern_crc;
    uint16_t pattern_black;
    /* armed level zero */
    gl_proto_zero_t zero;       /**< state, seat, and the last result */
    uint32_t zero_armed_ms;
    /* sleep-current test */
    bool sleep_armed;           /**< will start when VBUS has gone */
    bool sleep_running;         /**< asleep in the test now */
    uint8_t sleep_mask;         /**< GL_PROTO_WAKE_* asked for */
    uint16_t sleep_seconds;
    uint32_t sleep_start_ms;
    uint32_t sleep_due_ms;      /**< when it starts (after VBUS went) */
    bool sleep_due_valid;
    uint8_t last_wake;          /**< GL_PROTO_WAKE_* that ended the last test */
    uint8_t last_mask;
    uint32_t last_sleep_ms;
} gl_factory_t;

struct gl_app; /* gl_app_t (app/gl_app.h includes this file) */

/** The protocol's `factory` callback (ctx = the application). */
gl_status_t gl_factory_cmd(void *ctx, uint8_t cmd, const uint8_t *in, size_t n, uint8_t *out,
                           size_t cap, size_t *len);

/** Once per pass of the main loop, before the UI's events are handled:
 *  ends a display test, starts an armed zeroing or sleep test when its
 *  moment has come, ends a sleep test on its timer. */
void gl_factory_service(struct gl_app *app, uint32_t now_ms);

/** Called by the screen update.  If a display test is on, draws its pattern
 *  into the frame buffer and returns true (the ordinary screen is then not
 *  drawn). */
bool gl_factory_draw(struct gl_app *app);

/** The zeroing procedure reports how it ended.  `st` GL_OK: stored. */
void gl_factory_zero_result(struct gl_app *app, gl_status_t st, gl_vec2_t bias, gl_vec2_t surface,
                            float yaw_rad, float scatter);

/** The marker went to sleep / woke up (for the sleep test's bookkeeping).
 *  `cause` is the GL_PROTO_WAKE_* that woke it, 0 if it is not known yet. */
void gl_factory_on_sleep(struct gl_app *app, uint32_t now_ms);
void gl_factory_on_wake(struct gl_app *app, uint32_t now_ms);

/** True while the sleep test wants the IMU's wake-on-motion OFF. */
bool gl_factory_sleep_no_motion(const struct gl_app *app);

/** Milliseconds until the factory code needs the main loop again
 *  (0 = nothing pending). */
uint32_t gl_factory_time_left_ms(const struct gl_app *app, uint32_t now_ms);

#endif /* GL_FACTORY_H */
