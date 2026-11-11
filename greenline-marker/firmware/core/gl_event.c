/* gl_event.c - SPSC ring of events.  See gl_event.h. */
#include "gl_event.h"

#define QMASK ((uint8_t)(GL_EVENT_QUEUE_LEN - 1u))

void gl_event_init(gl_event_queue_t *q)
{
    q->head = 0;
    q->tail = 0;
    q->dropped = 0;
}

bool gl_event_post(gl_event_queue_t *q, uint16_t type, int32_t arg)
{
    uint8_t head = q->head;
    uint8_t next = (uint8_t)((head + 1u) & QMASK);
    if (next == q->tail) {
        if (q->dropped < 0xFFFFu) {
            q->dropped++;
        }
        return false;
    }
    q->slot[head].type = type;
    q->slot[head].pad = 0;
    q->slot[head].arg = arg;
    q->head = next; /* publish after the slot is complete */
    return true;
}

bool gl_event_get(gl_event_queue_t *q, gl_event_t *out)
{
    uint8_t tail = q->tail;
    if (tail == q->head) {
        return false;
    }
    *out = q->slot[tail];
    q->tail = (uint8_t)((tail + 1u) & QMASK);
    return true;
}

unsigned gl_event_count(const gl_event_queue_t *q)
{
    return (unsigned)((uint8_t)(q->head - q->tail) & QMASK);
}
