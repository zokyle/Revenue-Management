/*
 * gl_main.c - firmware entry point.
 *
 * The whole firmware is one statically allocated application object and a
 * cooperative loop; there is no RTOS, no heap and no second thread of
 * execution.  Interrupt handlers (in the HAL backend) only latch a source
 * bit; all work happens in gl_app_run_once(), which also puts the MCU into
 * Stop mode between events.
 *
 * Left out of the host test library (the tests have their own main()); the
 * cross build compiles it, so the size table shows the application object
 * as the bss of this module.
 */
#include "gl_app.h"

/** The application: about 186 kB, almost all of it image buffers and
 *  vision work areas (see gl_app.h / gl_read.h for the breakdown). */
static gl_app_t app_;

int main(void)
{
    /* A device that failed its start-up checks still runs: the fault is on
     * the screen and in the log, and USB (in the cradle) stays usable. */
    (void)gl_app_init(&app_);
    for (;;) {
        gl_app_run_once(&app_);
    }
}
