/*
 * gl_event.h - small fixed-size event queue for the cooperative main loop.
 *
 * Single producer / single consumer ring: an interrupt handler (or the main
 * loop itself) posts, the main loop gets.  On a single-core MCU this needs
 * no lock as long as there is ONE posting context; if both an ISR and the
 * main loop post, the caller wraps gl_event_post() in
 * gl_hal_irq_lock()/unlock().  The core never calls the HAL.
 *
 * RAM: 132 bytes (8 bytes per slot, GL_EVENT_QUEUE_LEN slots, + 4).  The
 * queue holds at most GL_EVENT_QUEUE_LEN - 1 events.
 */
#ifndef GL_EVENT_H
#define GL_EVENT_H

#include "gl_types.h"

#define GL_EVENT_QUEUE_LEN 16u /* must be a power of two */

typedef struct {
    uint16_t type; /**< application-defined (gl_ui_event_t for the UI) */
    uint16_t pad;
    int32_t arg;   /**< event argument (angle in mdeg, error code, ...) */
} gl_event_t;

typedef struct {
    gl_event_t slot[GL_EVENT_QUEUE_LEN];
    volatile uint8_t head; /**< next slot to write (producer) */
    volatile uint8_t tail; /**< next slot to read (consumer) */
    uint16_t dropped;      /**< events lost because the queue was full */
} gl_event_queue_t;

/** Empty the queue. */
void gl_event_init(gl_event_queue_t *q);

/** Append an event.  Returns false (and counts a drop) if the queue is full. */
bool gl_event_post(gl_event_queue_t *q, uint16_t type, int32_t arg);

/** Remove the oldest event.  Returns false if the queue is empty. */
bool gl_event_get(gl_event_queue_t *q, gl_event_t *out);

/** Number of queued events. */
unsigned gl_event_count(const gl_event_queue_t *q);

#endif /* GL_EVENT_H */
