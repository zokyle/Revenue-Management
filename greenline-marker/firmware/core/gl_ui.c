/* gl_ui.c - UI state machine (transition table) and screens.  See gl_ui.h. */
#include "gl_ui.h"

#include <math.h>
#include <string.h>

#include "gl_fmt.h"

/* ======================================================================= */
/* Transition table                                                         */
/* ======================================================================= */

#define T(s, e, g, n, a) { (uint8_t)(s), (uint8_t)(e), (uint8_t)(g), (uint8_t)(n), (uint32_t)(a) }

/* Rows for a specific state take precedence over GL_UI_ANY rows; within a
 * state the first row whose guard holds wins. */
static const gl_ui_transition_t table_[] = {
    /* ---- SLEEP: display off, MCU in Stop mode, IMU wake-on-motion ---- */
    T(GL_UI_SLEEP, GL_EV_MOTION, GL_G_ALWAYS, GL_UI_WAKE, GL_ACT_DISPLAY_ON | GL_ACT_REDRAW),
    T(GL_UI_SLEEP, GL_EV_USB_ATTACH, GL_G_ALWAYS, GL_UI_CRADLE_USB,
      GL_ACT_DISPLAY_ON | GL_ACT_USB_START | GL_ACT_REDRAW),
    T(GL_UI_SLEEP, GL_EV_BATT_LOW, GL_G_ALWAYS, GL_UI_SLEEP, 0),

    /* ---- WAKE: splash ---- */
    T(GL_UI_WAKE, GL_EV_TIMEOUT, GL_G_ALWAYS, GL_UI_WAIT_STILL,
      GL_ACT_WATCH_STILL | GL_ACT_NEW_READ | GL_ACT_REDRAW),
    T(GL_UI_WAKE, GL_EV_UPRIGHT, GL_G_ALWAYS, GL_UI_SETTINGS_DIAL,
      GL_ACT_DIAL_BEGIN | GL_ACT_REDRAW),

    /* ---- WAIT_STILL ---- */
    T(GL_UI_WAIT_STILL, GL_EV_STILL, GL_G_ALWAYS, GL_UI_READ_TILT,
      GL_ACT_START_TILT | GL_ACT_REDRAW),
    T(GL_UI_WAIT_STILL, GL_EV_UPRIGHT, GL_G_ALWAYS, GL_UI_SETTINGS_DIAL,
      GL_ACT_DIAL_BEGIN | GL_ACT_REDRAW),
    T(GL_UI_WAIT_STILL, GL_EV_TIMEOUT, GL_G_ALWAYS, GL_UI_SLEEP,
      GL_ACT_ENTER_SLEEP | GL_ACT_SURVEY_RESET),

    /* ---- READ_TILT: 1 s accelerometer average ---- */
    T(GL_UI_READ_TILT, GL_EV_TILT_DONE, GL_G_PRECISION_REREAD, GL_UI_SOLVE,
      GL_ACT_START_SOLVE | GL_ACT_PRECISION | GL_ACT_REDRAW),
    T(GL_UI_READ_TILT, GL_EV_TILT_DONE, GL_G_ALWAYS, GL_UI_CAPTURE,
      GL_ACT_START_CAPTURE | GL_ACT_REDRAW),
    T(GL_UI_READ_TILT, GL_EV_TILT_FAIL, GL_G_ALWAYS, GL_UI_WAIT_STILL,
      GL_ACT_ABORT_READ | GL_ACT_WATCH_STILL | GL_ACT_REDRAW),
    T(GL_UI_READ_TILT, GL_EV_MOTION, GL_G_ALWAYS, GL_UI_WAIT_STILL,
      GL_ACT_ABORT_READ | GL_ACT_WATCH_STILL | GL_ACT_REDRAW),
    T(GL_UI_READ_TILT, GL_EV_TIMEOUT, GL_G_ALWAYS, GL_UI_ERROR,
      GL_ACT_ABORT_READ | GL_ACT_REDRAW),

    /* ---- CAPTURE: camera rail on ---- */
    T(GL_UI_CAPTURE, GL_EV_CAPTURE_DONE, GL_G_SURVEY_ROOM, GL_UI_SOLVE,
      GL_ACT_SURVEY_STORE | GL_ACT_START_SOLVE | GL_ACT_REDRAW),
    T(GL_UI_CAPTURE, GL_EV_CAPTURE_DONE, GL_G_ALWAYS, GL_UI_SOLVE,
      GL_ACT_START_SOLVE | GL_ACT_REDRAW),
    T(GL_UI_CAPTURE, GL_EV_CAPTURE_NO_STICK, GL_G_HAS_MANUAL_DIST, GL_UI_SOLVE,
      GL_ACT_START_SOLVE | GL_ACT_REDRAW),
    T(GL_UI_CAPTURE, GL_EV_CAPTURE_NO_STICK, GL_G_ALWAYS, GL_UI_SETTINGS_DIAL,
      GL_ACT_DIAL_BEGIN | GL_ACT_REDRAW),
    T(GL_UI_CAPTURE, GL_EV_CAPTURE_FAIL, GL_G_ALWAYS, GL_UI_ERROR,
      GL_ACT_ABORT_READ | GL_ACT_REDRAW),
    T(GL_UI_CAPTURE, GL_EV_MOTION, GL_G_ALWAYS, GL_UI_WAIT_STILL,
      GL_ACT_ABORT_READ | GL_ACT_WATCH_STILL | GL_ACT_REDRAW),
    T(GL_UI_CAPTURE, GL_EV_TIMEOUT, GL_G_ALWAYS, GL_UI_ERROR,
      GL_ACT_ABORT_READ | GL_ACT_REDRAW),

    /* ---- SOLVE ---- */
    T(GL_UI_SOLVE, GL_EV_SOLVE_DONE, GL_G_ALWAYS, GL_UI_SHOW_RESULT, GL_ACT_REDRAW),
    T(GL_UI_SOLVE, GL_EV_SOLVE_FAIL, GL_G_ALWAYS, GL_UI_ERROR, GL_ACT_REDRAW),
    T(GL_UI_SOLVE, GL_EV_TIMEOUT, GL_G_ALWAYS, GL_UI_ERROR, GL_ACT_REDRAW),

    /* ---- SHOW_RESULT ---- */
    T(GL_UI_SHOW_RESULT, GL_EV_DOUBLE_TAP, GL_G_SURVEY_ACTIVE, GL_UI_SHOW_RESULT,
      GL_ACT_SURVEY_RESET | GL_ACT_REDRAW),
    T(GL_UI_SHOW_RESULT, GL_EV_DOUBLE_TAP, GL_G_ALWAYS, GL_UI_PRECISION_WAIT_SPIN,
      GL_ACT_ARM_SPIN | GL_ACT_REDRAW),
    T(GL_UI_SHOW_RESULT, GL_EV_MOTION, GL_G_SURVEY_ROOM, GL_UI_SURVEY_NEXT_DROP,
      GL_ACT_WATCH_STILL | GL_ACT_REDRAW),
    T(GL_UI_SHOW_RESULT, GL_EV_MOTION, GL_G_SURVEY_FULL, GL_UI_WAIT_STILL,
      GL_ACT_SURVEY_RESET | GL_ACT_WATCH_STILL | GL_ACT_NEW_READ | GL_ACT_REDRAW),
    T(GL_UI_SHOW_RESULT, GL_EV_MOTION, GL_G_ALWAYS, GL_UI_WAIT_STILL,
      GL_ACT_WATCH_STILL | GL_ACT_NEW_READ | GL_ACT_REDRAW),
    T(GL_UI_SHOW_RESULT, GL_EV_UPRIGHT, GL_G_ALWAYS, GL_UI_SETTINGS_DIAL,
      GL_ACT_DIAL_BEGIN | GL_ACT_REDRAW),
    T(GL_UI_SHOW_RESULT, GL_EV_TIMEOUT, GL_G_ALWAYS, GL_UI_SLEEP,
      GL_ACT_ENTER_SLEEP | GL_ACT_SURVEY_RESET),

    /* ---- PRECISION_WAIT_SPIN: "spin 180" prompt; motion is expected ---- */
    T(GL_UI_PRECISION_WAIT_SPIN, GL_EV_SPIN_DONE, GL_G_ALWAYS, GL_UI_READ_TILT,
      GL_ACT_START_TILT | GL_ACT_REDRAW),
    T(GL_UI_PRECISION_WAIT_SPIN, GL_EV_DOUBLE_TAP, GL_G_ALWAYS, GL_UI_SURVEY_NEXT_DROP,
      GL_ACT_SURVEY_STORE | GL_ACT_REDRAW),
    T(GL_UI_PRECISION_WAIT_SPIN, GL_EV_UPRIGHT, GL_G_ALWAYS, GL_UI_SETTINGS_DIAL,
      GL_ACT_DIAL_BEGIN | GL_ACT_REDRAW),
    T(GL_UI_PRECISION_WAIT_SPIN, GL_EV_TIMEOUT, GL_G_ALWAYS, GL_UI_SHOW_RESULT, GL_ACT_REDRAW),

    /* ---- SURVEY_NEXT_DROP: waiting for the marker to be moved and re-placed ---- */
    T(GL_UI_SURVEY_NEXT_DROP, GL_EV_MOTION, GL_G_ALWAYS, GL_UI_SURVEY_NEXT_DROP,
      GL_ACT_WATCH_STILL),
    T(GL_UI_SURVEY_NEXT_DROP, GL_EV_STILL, GL_G_MOVED, GL_UI_READ_TILT,
      GL_ACT_START_TILT | GL_ACT_REDRAW),
    T(GL_UI_SURVEY_NEXT_DROP, GL_EV_DOUBLE_TAP, GL_G_ALWAYS, GL_UI_SHOW_RESULT,
      GL_ACT_SURVEY_RESET | GL_ACT_REDRAW),
    T(GL_UI_SURVEY_NEXT_DROP, GL_EV_TIMEOUT, GL_G_ALWAYS, GL_UI_SLEEP,
      GL_ACT_SURVEY_RESET | GL_ACT_ENTER_SLEEP),

    /* ---- SETTINGS_DIAL: upright; roll to change, double tap = next item,
     *      lay flat = confirm ---- */
    T(GL_UI_SETTINGS_DIAL, GL_EV_DIAL_STEP, GL_G_ALWAYS, GL_UI_SETTINGS_DIAL, GL_ACT_REDRAW),
    T(GL_UI_SETTINGS_DIAL, GL_EV_DOUBLE_TAP, GL_G_ALWAYS, GL_UI_SETTINGS_DIAL,
      GL_ACT_DIAL_BEGIN | GL_ACT_REDRAW),
    T(GL_UI_SETTINGS_DIAL, GL_EV_FLAT, GL_G_ITEM_ZERO_YES, GL_UI_CAL_ZERO,
      GL_ACT_SAVE_SETTINGS | GL_ACT_CAL_ZERO_START | GL_ACT_REDRAW),
    T(GL_UI_SETTINGS_DIAL, GL_EV_FLAT, GL_G_ALWAYS, GL_UI_WAIT_STILL,
      GL_ACT_SAVE_SETTINGS | GL_ACT_WATCH_STILL | GL_ACT_NEW_READ | GL_ACT_REDRAW),
    T(GL_UI_SETTINGS_DIAL, GL_EV_TIMEOUT, GL_G_ALWAYS, GL_UI_SLEEP,
      GL_ACT_ENTER_SLEEP | GL_ACT_SURVEY_RESET),

    /* ---- CRADLE_USB: charging and data.  The cradle accepts the marker one
     *      way round only and holds it down: nothing is calibrated here ---- */
    T(GL_UI_CRADLE_USB, GL_EV_USB_DETACH, GL_G_ALWAYS, GL_UI_SLEEP,
      GL_ACT_USB_STOP | GL_ACT_ENTER_SLEEP),
    T(GL_UI_CRADLE_USB, GL_EV_USB_ATTACH, GL_G_ALWAYS, GL_UI_CRADLE_USB, 0),
    T(GL_UI_CRADLE_USB, GL_EV_BATT_LOW, GL_G_ALWAYS, GL_UI_CRADLE_USB, 0),

    /* ---- CAL_ZERO: zeroing on any hard flat surface (read, turn the marker
     *      180 degrees in place, read again).  Entered only from the dial;
     *      the turn is expected motion, so MOTION is ignored here.  Being put
     *      in the cradle abandons the procedure ---- */
    T(GL_UI_CAL_ZERO, GL_EV_CAL_DONE, GL_G_ALWAYS, GL_UI_WAIT_STILL,
      GL_ACT_WATCH_STILL | GL_ACT_NEW_READ | GL_ACT_REDRAW),
    T(GL_UI_CAL_ZERO, GL_EV_CAL_FAIL, GL_G_ALWAYS, GL_UI_ERROR, GL_ACT_CAL_ABORT | GL_ACT_REDRAW),
    T(GL_UI_CAL_ZERO, GL_EV_USB_ATTACH, GL_G_ALWAYS, GL_UI_CRADLE_USB,
      GL_ACT_CAL_ABORT | GL_ACT_USB_START | GL_ACT_DISPLAY_ON | GL_ACT_REDRAW),
    T(GL_UI_CAL_ZERO, GL_EV_DOUBLE_TAP, GL_G_ALWAYS, GL_UI_WAIT_STILL,
      GL_ACT_CAL_ABORT | GL_ACT_WATCH_STILL | GL_ACT_NEW_READ | GL_ACT_REDRAW),
    T(GL_UI_CAL_ZERO, GL_EV_BATT_LOW, GL_G_ALWAYS, GL_UI_CAL_ZERO, 0),
    T(GL_UI_CAL_ZERO, GL_EV_FAULT, GL_G_ALWAYS, GL_UI_ERROR,
      GL_ACT_CAL_ABORT | GL_ACT_ABORT_READ | GL_ACT_REDRAW),
    T(GL_UI_CAL_ZERO, GL_EV_TIMEOUT, GL_G_ALWAYS, GL_UI_ERROR, GL_ACT_CAL_ABORT | GL_ACT_REDRAW),

    /* ---- ERROR ---- */
    T(GL_UI_ERROR, GL_EV_DOUBLE_TAP, GL_G_ALWAYS, GL_UI_WAIT_STILL,
      GL_ACT_WATCH_STILL | GL_ACT_NEW_READ | GL_ACT_REDRAW),
    T(GL_UI_ERROR, GL_EV_TIMEOUT, GL_G_USB, GL_UI_CRADLE_USB, GL_ACT_REDRAW),
    T(GL_UI_ERROR, GL_EV_TIMEOUT, GL_G_ALWAYS, GL_UI_SLEEP,
      GL_ACT_ENTER_SLEEP | GL_ACT_SURVEY_RESET),
    T(GL_UI_ERROR, GL_EV_FAULT, GL_G_ALWAYS, GL_UI_ERROR, GL_ACT_REDRAW),
    T(GL_UI_ERROR, GL_EV_USB_DETACH, GL_G_ALWAYS, GL_UI_ERROR, GL_ACT_USB_STOP),

    /* ---- LOW_BATT ---- */
    T(GL_UI_LOW_BATT, GL_EV_TIMEOUT, GL_G_ALWAYS, GL_UI_SLEEP,
      GL_ACT_ENTER_SLEEP | GL_ACT_SURVEY_RESET),
    T(GL_UI_LOW_BATT, GL_EV_BATT_LOW, GL_G_ALWAYS, GL_UI_LOW_BATT, 0),

    /* ---- from any state ---- */
    T(GL_UI_ANY, GL_EV_USB_ATTACH, GL_G_ALWAYS, GL_UI_CRADLE_USB,
      GL_ACT_ABORT_READ | GL_ACT_SURVEY_RESET | GL_ACT_USB_START | GL_ACT_DISPLAY_ON |
          GL_ACT_REDRAW),
    T(GL_UI_ANY, GL_EV_BATT_LOW, GL_G_ALWAYS, GL_UI_LOW_BATT,
      GL_ACT_ABORT_READ | GL_ACT_SURVEY_RESET | GL_ACT_REDRAW),
    T(GL_UI_ANY, GL_EV_FAULT, GL_G_ALWAYS, GL_UI_ERROR,
      GL_ACT_ABORT_READ | GL_ACT_DISPLAY_ON | GL_ACT_REDRAW),
};

static const uint32_t timeout_ms_[GL_UI_STATE_COUNT] = {
    0,      /* SLEEP */
    800,    /* WAKE */
    20000,  /* WAIT_STILL */
    4000,   /* READ_TILT */
    8000,   /* CAPTURE */
    3000,   /* SOLVE */
    45000,  /* SHOW_RESULT */
    20000,  /* PRECISION_WAIT_SPIN */
    60000,  /* SURVEY_NEXT_DROP */
    30000,  /* SETTINGS_DIAL */
    0,      /* CRADLE_USB */
    120000, /* CAL_ZERO */
    5000,   /* ERROR */
    4000,   /* LOW_BATT */
};

const gl_ui_transition_t *gl_ui_table(size_t *rows)
{
    if (rows != NULL) {
        *rows = GL_ARRAY_LEN(table_);
    }
    return table_;
}

uint32_t gl_ui_timeout_ms(gl_ui_state_t state)
{
    return ((unsigned)state < (unsigned)GL_UI_STATE_COUNT) ? timeout_ms_[state] : 0u;
}

const char *gl_ui_state_name(gl_ui_state_t state)
{
    static const char *const names[GL_UI_STATE_COUNT] = {
        "SLEEP", "WAKE", "WAIT_STILL", "READ_TILT", "CAPTURE", "SOLVE", "SHOW_RESULT",
        "PRECISION_WAIT_SPIN", "SURVEY_NEXT_DROP", "SETTINGS_DIAL", "CRADLE_USB", "CAL_ZERO",
        "ERROR", "LOW_BATT"
    };
    return ((unsigned)state < (unsigned)GL_UI_STATE_COUNT) ? names[state] : "?";
}

const char *gl_ui_event_name(gl_ui_event_t ev)
{
    static const char *const names[GL_EV_COUNT] = {
        "NONE", "MOTION", "STILL", "TILT_DONE", "TILT_FAIL", "CAPTURE_DONE", "CAPTURE_NO_STICK",
        "CAPTURE_FAIL", "SOLVE_DONE", "SOLVE_FAIL", "DOUBLE_TAP", "SPIN_DONE", "UPRIGHT", "FLAT",
        "DIAL_STEP", "USB_ATTACH", "USB_DETACH", "BATT_LOW", "CAL_DONE", "CAL_FAIL",
        "FAULT", "TIMEOUT"
    };
    return ((unsigned)ev < (unsigned)GL_EV_COUNT) ? names[ev] : "?";
}

/* ---- dial items --------------------------------------------------------- */

static int item_value_(const gl_ui_t *ui)
{
    if (ui->item >= GL_UI_ITEM_ZERO) {
        return 0; /* "ZERO" always starts at NO */
    }
    return gl_settings_item_get(&ui->edit, (gl_item_t)ui->item);
}

static bool guard_(const gl_ui_t *ui, uint8_t guard)
{
    switch (guard) {
    case GL_G_ALWAYS: return true;
    case GL_G_PRECISION_REREAD: return ui->read_kind == (uint8_t)GL_READ_PRECISION;
    case GL_G_SURVEY_ACTIVE: return ui->survey_count > 0u;
    case GL_G_SURVEY_ROOM: return ui->survey_count > 0u && ui->survey_count < 4u;
    case GL_G_SURVEY_FULL: return ui->survey_count >= 4u;
    case GL_G_HAS_MANUAL_DIST: return ui->edit.manual_distance_cm != 0u;
    case GL_G_MOVED: return ui->moved;
    case GL_G_USB: return ui->usb;
    case GL_G_ITEM_ZERO_YES:
        return ui->item == GL_UI_ITEM_ZERO && ui->dial_value != 0;
    default: return false;
    }
}

void gl_ui_init(gl_ui_t *ui, const gl_settings_t *settings, uint32_t now_ms)
{
    memset(ui, 0, sizeof(*ui));
    ui->state = (uint8_t)GL_UI_SLEEP;
    ui->read_kind = (uint8_t)GL_READ_QUICK;
    ui->state_since_ms = now_ms;
    if (settings != NULL) {
        ui->edit = *settings;
        ui->saved = *settings;
    } else {
        gl_settings_defaults(&ui->edit);
        gl_settings_defaults(&ui->saved);
    }
}

uint32_t gl_ui_dispatch(gl_ui_t *ui, gl_ui_event_t ev, int32_t arg, uint32_t now_ms)
{
    const gl_ui_transition_t *row = NULL;
    const uint8_t from = ui->state;

    /* facts that hold whatever the table says */
    if (ev == GL_EV_USB_ATTACH) {
        ui->usb = true;
    } else if (ev == GL_EV_USB_DETACH) {
        ui->usb = false;
    }
    for (int pass = 0; pass < 2 && row == NULL; pass++) {
        const uint8_t want = (pass == 0) ? from : (uint8_t)GL_UI_ANY;
        for (size_t i = 0; i < GL_ARRAY_LEN(table_); i++) {
            if (table_[i].state == want && table_[i].event == (uint8_t)ev &&
                guard_(ui, table_[i].guard)) {
                row = &table_[i];
                break;
            }
        }
    }
    if (row == NULL) {
        return 0; /* event not meaningful in this state: ignored */
    }

    /* ---- bookkeeping tied to particular transitions ---- */
    if ((row->actions & GL_ACT_SURVEY_RESET) != 0u) {
        ui->survey_count = 0;
    }
    if ((row->actions & GL_ACT_SURVEY_STORE) != 0u && ui->survey_count < 4u) {
        ui->survey_count++;
    }
    if ((row->actions & GL_ACT_NEW_READ) != 0u) {
        ui->read_kind = (uint8_t)GL_READ_QUICK;
    }
    if (row->next == (uint8_t)GL_UI_READ_TILT) {
        if (from == (uint8_t)GL_UI_PRECISION_WAIT_SPIN) {
            ui->read_kind = (uint8_t)GL_READ_PRECISION;
        } else if (from == (uint8_t)GL_UI_SURVEY_NEXT_DROP) {
            ui->read_kind = (uint8_t)GL_READ_SURVEY;
        }
    }
    if (row->next == (uint8_t)GL_UI_SURVEY_NEXT_DROP) {
        if (from != (uint8_t)GL_UI_SURVEY_NEXT_DROP) {
            /* arriving by picking the marker up counts as "moved" already */
            ui->moved = (ev == GL_EV_MOTION);
        } else if (ev == GL_EV_MOTION) {
            ui->moved = true;
        }
    }
    if (row->next == (uint8_t)GL_UI_SETTINGS_DIAL) {
        if (from != (uint8_t)GL_UI_SETTINGS_DIAL) {
            ui->saved = ui->edit; /* snapshot, restored if the dial is abandoned */
            ui->dist_prompt = (ev == GL_EV_CAPTURE_NO_STICK);
            ui->item = (uint8_t)(ui->dist_prompt ? GL_ITEM_DISTANCE : GL_ITEM_STIMP);
            ui->dial_value = item_value_(ui);
        } else if (ev == GL_EV_DOUBLE_TAP) {
            ui->item = (uint8_t)((ui->item + 1u) % GL_UI_ITEM_COUNT);
            ui->dial_value = item_value_(ui);
        } else if (ev == GL_EV_DIAL_STEP) {
            if (ui->item < GL_UI_ITEM_ZERO) {
                gl_settings_item_set(&ui->edit, (gl_item_t)ui->item, (int)arg);
                ui->dial_value = item_value_(ui);
            } else {
                ui->dial_value = (arg != 0) ? 1 : 0;
            }
        }
    }
    if (from == (uint8_t)GL_UI_SETTINGS_DIAL && row->next != (uint8_t)GL_UI_SETTINGS_DIAL) {
        if ((row->actions & GL_ACT_SAVE_SETTINGS) != 0u) {
            ui->saved = ui->edit;
        } else {
            ui->edit = ui->saved; /* abandoned: discard the edits */
        }
        ui->dist_prompt = false;
    }
    if (row->next == (uint8_t)GL_UI_ERROR) {
        switch (ev) {
        case GL_EV_FAULT:
        case GL_EV_SOLVE_FAIL:
        case GL_EV_CAL_FAIL:
            ui->error_code = (uint16_t)((arg > 0 && arg < 0xFFFF) ? arg : (int32_t)GL_ERR_IO);
            break;
        case GL_EV_TIMEOUT: ui->error_code = (uint16_t)GL_ERR_TIMEOUT; break;
        default: ui->error_code = (uint16_t)GL_ERR_IO; break;
        }
    }

    /* ---- the transition itself ---- */
    if (row->next != from || row->actions != 0u) {
        /* entering a state, or activity within it, restarts its time limit;
         * pure "ignore" rows do not */
        ui->state_since_ms = now_ms;
    }
    ui->state = row->next;
    ui->transitions++;
    return row->actions;
}

uint32_t gl_ui_tick(gl_ui_t *ui, uint32_t now_ms)
{
    uint32_t limit = gl_ui_timeout_ms((gl_ui_state_t)ui->state);
    if (limit != 0u && (uint32_t)(now_ms - ui->state_since_ms) >= limit) {
        return gl_ui_dispatch(ui, GL_EV_TIMEOUT, 0, now_ms);
    }
    return 0;
}

void gl_ui_keepalive(gl_ui_t *ui, uint32_t now_ms)
{
    ui->state_since_ms = now_ms;
}

uint32_t gl_ui_time_left_ms(const gl_ui_t *ui, uint32_t now_ms)
{
    uint32_t limit = gl_ui_timeout_ms((gl_ui_state_t)ui->state);
    uint32_t held = (uint32_t)(now_ms - ui->state_since_ms);
    if (limit == 0u || held >= limit) {
        return 0;
    }
    return limit - held;
}

/* ======================================================================= */
/* Screens                                                                  */
/* ======================================================================= */

#define CX 64

/* Text centred on (cx, y) with a white box behind it. */
static void label_(gl_gfx_t *g, int cx, int y, const char *s, int scale)
{
    int w = gl_gfx_text_width(s, scale);
    gl_gfx_rect(g, cx - w / 2 - 2, y - 2, w + 4, GL_FONT_H * scale + 4, GL_INK_WHITE);
    gl_gfx_text_centred(g, cx, y, s, scale, GL_INK_BLACK);
}

static void text_(gl_gfx_t *g, int y, const char *s, int scale)
{
    gl_gfx_text_centred(g, CX, y, s, scale, GL_INK_BLACK);
}

static void battery_small_(gl_gfx_t *g, const gl_ui_view_t *v, int y)
{
    gl_gfx_battery(g, CX - 9, y, (int)v->battery_pct);
}

static void screen_result_(const gl_ui_t *ui, const gl_ui_view_t *v, gl_gfx_t *g)
{
    gl_gfx_aim_info_t info;
    char buf[16];
    int rose_x;

    if (!v->have_result) {
        text_(g, 60, "NO READ", 1);
        return;
    }
    /* 1. the aim line: the backward extension of the start line through the ball */
    gl_gfx_aim_line_at(g, v->aim_rad, v->ball_az_rad, 3.0f, &info);
    if (!info.on_screen) {
        /* the true line passes outside the aperture: the dashed line shows
         * its direction, the arrow the side it lies on */
        if (info.offset_px > 0.0f) {
            gl_gfx_arrow(g, 96.0f, 64.0f, -0.5f * GL_PI_F, 16.0f, 7.0f, 1.5f, GL_INK_BLACK);
        } else {
            gl_gfx_arrow(g, 32.0f, 64.0f, 0.5f * GL_PI_F, 16.0f, 7.0f, 1.5f, GL_INK_BLACK);
        }
    }
    /* 2. distance (top) */
    if (v->distance_m > 0.0f) {
        gl_settings_format_distance(&ui->edit, v->distance_m, buf, sizeof(buf));
    } else {
        buf[0] = '\0';
        gl_fmt_append(buf, sizeof(buf), "--");
    }
    label_(g, CX, 12, buf, 1);
    /* 3. slope along the line to the hole */
    buf[0] = '\0';
    if (fabsf(v->along_pct) < 0.1f) {
        gl_fmt_append(buf, sizeof(buf), "LEVEL");
    } else {
        size_t n;
        gl_fmt_append(buf, sizeof(buf), (v->along_pct > 0.0f) ? "UP " : "DN ");
        n = strlen(buf);
        gl_fmt_fixed(buf + n, sizeof(buf) - n, fabsf(v->along_pct), 1);
        gl_fmt_append(buf, sizeof(buf), "%");
    }
    label_(g, CX, 24, buf, 1);
    /* 4. fall-line rose on the side away from the aim line */
    rose_x = (info.on_screen && info.offset_px < -14.0f) ? 100 : 28;
    if (info.on_screen && fabsf(info.offset_px) <= 14.0f) {
        rose_x = (info.offset_px >= 0.0f) ? 28 : 100;
    }
    gl_gfx_disc(g, (float)rose_x, 58.0f, 12.0f, GL_INK_WHITE);
    if (v->slope_pct >= 0.15f) {
        float dx = -sinf(v->fall_line_rad), dy = -cosf(v->fall_line_rad);
        gl_gfx_arrow(g, (float)rose_x - 8.0f * dx, 58.0f - 8.0f * dy, v->fall_line_rad, 16.0f,
                     6.0f, 1.0f, GL_INK_BLACK);
    } else {
        gl_gfx_arc(g, (float)rose_x, 58.0f, 3.0f, 4.5f, 0.0f, 7.0f, GL_INK_BLACK);
    }
    buf[0] = '\0';
    gl_fmt_fixed(buf, sizeof(buf), v->slope_pct, 1);
    gl_fmt_append(buf, sizeof(buf), "%");
    label_(g, rose_x, 74, buf, 1);
    /* 5. break in cup widths, or the reason there is none */
    buf[0] = '\0';
    if (!v->solved) {
        gl_fmt_append(buf, sizeof(buf), "TILT ONLY");
    } else if (fabsf(v->break_cups) < 0.05f) {
        gl_fmt_append(buf, sizeof(buf), "STRAIGHT");
    } else {
        size_t n;
        gl_fmt_append(buf, sizeof(buf), (v->break_cups > 0.0f) ? "<" : "");
        n = strlen(buf);
        gl_fmt_fixed(buf + n, sizeof(buf) - n, fabsf(v->break_cups), 1);
        gl_fmt_append(buf, sizeof(buf), (v->break_cups > 0.0f) ? " CUP" : " CUP>");
    }
    label_(g, CX, 92, buf, 1);
    /* 6. confidence bar, flag / mode marks */
    {
        int filled = gl_roundi(gl_clampf(v->confidence, 0.0f, 1.0f) * 5.0f);
        gl_gfx_rect(g, CX - 18, 103, 37, 10, GL_INK_WHITE);
        gl_gfx_conf_bar(g, CX - 16, 105, filled, 5);
    }
    if (!v->flag_found) {
        gl_gfx_rect(g, 92, 30, 13, 15, GL_INK_WHITE);
        gl_gfx_icon(g, 94, 32, GL_ICON_NOFLAG, GL_INK_BLACK);
    }
    if (ui->survey_count > 0u) {
        buf[0] = 'D';
        buf[1] = (char)('0' + (int)ui->survey_count);
        buf[2] = '\0';
        label_(g, CX, 36, buf, 1);
    } else if (v->precision) {
        label_(g, CX, 36, "2X", 1);
    }
}

static void screen_settings_(const gl_ui_t *ui, gl_gfx_t *g)
{
    char buf[16];
    if (ui->item >= GL_UI_ITEM_ZERO) {
        text_(g, 24, "ZERO", 1);
        text_(g, 50, (ui->dial_value != 0) ? "YES" : "NO", 2);
    } else {
        text_(g, 24, gl_settings_item_name((gl_item_t)ui->item), 1);
        gl_settings_item_format(&ui->edit, (gl_item_t)ui->item, buf, sizeof(buf));
        if (ui->item == (uint8_t)GL_ITEM_STIMP) {
            int w = gl_gfx_big_number_width(buf, 28);
            gl_gfx_big_number(g, CX - w / 2, 40, buf, 28, GL_INK_BLACK);
        } else {
            text_(g, 50, buf, (gl_gfx_text_width(buf, 2) <= 100) ? 2 : 1);
        }
    }
    text_(g, 82, "ROLL TO SET", 1);
    text_(g, 94, "FLAT = OK", 1);
    /* position within the menu */
    for (unsigned i = 0; i < GL_UI_ITEM_COUNT; i++) {
        int x = CX - (int)GL_UI_ITEM_COUNT * 3 + (int)i * 6;
        if (i == ui->item) {
            gl_gfx_rect(g, x, 107, 4, 4, GL_INK_BLACK);
        } else {
            gl_gfx_rect(g, x + 1, 108, 2, 2, GL_INK_BLACK);
        }
    }
}

void gl_ui_render(const gl_ui_t *ui, const gl_ui_view_t *v, gl_gfx_t *g)
{
    char buf[16];

    gl_gfx_set_clip(g, true);
    gl_gfx_clear(g, GL_INK_WHITE);
    switch ((gl_ui_state_t)ui->state) {
    case GL_UI_SLEEP:
        break; /* blank: the display is off */
    case GL_UI_WAKE:
        text_(g, 46, "GREENLINE", 1);
        text_(g, 60, "GL-1", 2);
        battery_small_(g, v, 86);
        break;
    case GL_UI_WAIT_STILL:
        text_(g, 38, "HOLD", 2);
        text_(g, 58, "STILL", 2);
        battery_small_(g, v, 86);
        break;
    case GL_UI_READ_TILT:
        text_(g, 44, "LEVEL", 2);
        text_(g, 68, (ui->read_kind == (uint8_t)GL_READ_PRECISION) ? "RE-READING" : "READING", 1);
        break;
    case GL_UI_CAPTURE:
        gl_gfx_icon(g, CX - 4, 32, GL_ICON_FLAG, GL_INK_BLACK);
        text_(g, 50, "FLAG", 2);
        text_(g, 72, "LOOKING", 1);
        break;
    case GL_UI_SOLVE:
        text_(g, 52, "SOLVE", 2);
        break;
    case GL_UI_SHOW_RESULT:
        screen_result_(ui, v, g);
        break;
    case GL_UI_PRECISION_WAIT_SPIN:
        /* three-quarter ring with an arrow head: "turn me round" */
        gl_gfx_arc(g, 64.0f, 48.0f, 15.0f, 18.5f, 0.6f, 5.4f, GL_INK_BLACK);
        gl_gfx_triangle(g, 64.0f - 16.75f * sinf(0.6f) - 7.0f, 48.0f - 16.75f * cosf(0.6f) - 5.0f,
                        64.0f - 16.75f * sinf(0.6f) - 7.0f, 48.0f - 16.75f * cosf(0.6f) + 7.0f,
                        64.0f - 16.75f * sinf(0.6f) + 6.0f, 48.0f - 16.75f * cosf(0.6f) - 1.0f,
                        GL_INK_BLACK);
        text_(g, 76, "SPIN 180", 1);
        text_(g, 90, "TAP-TAP:SURVEY", 1);
        break;
    case GL_UI_SURVEY_NEXT_DROP:
        text_(g, 30, "SURVEY", 2);
        buf[0] = '\0';
        gl_fmt_append(buf, sizeof(buf), "DROP ");
        gl_fmt_int(buf + 5, sizeof(buf) - 5, (int32_t)ui->survey_count + 1);
        gl_fmt_append(buf, sizeof(buf), " OF 4");
        text_(g, 56, buf, 1);
        text_(g, 70, "MOVE AND PLACE", 1);
        text_(g, 86, "TAP-TAP: END", 1);
        break;
    case GL_UI_SETTINGS_DIAL:
        screen_settings_(ui, g);
        break;
    case GL_UI_CRADLE_USB:
        gl_gfx_icon(g, CX - 4, 22, GL_ICON_USB, GL_INK_BLACK);
        text_(g, 40, "USB", 2);
        gl_gfx_battery(g, CX - 14, 66, (int)v->battery_pct);
        if (v->charging) {
            gl_gfx_icon(g, CX + 10, 67, GL_ICON_BOLT, GL_INK_BLACK);
        }
        buf[0] = '\0';
        gl_fmt_int(buf, sizeof(buf), (int32_t)v->battery_pct);
        gl_fmt_append(buf, sizeof(buf), "%");
        text_(g, 82, buf, 1);
        text_(g, 96, v->usb_connected ? "LINKED" : "CHARGER", 1);
        break;
    case GL_UI_CAL_ZERO:
        /* zeroing: on a hard flat surface, never in the cradle */
        text_(g, 22, "ZEROING", 1);
        if (v->cal_step == 1u) {
            text_(g, 38, "TURN", 2);
            text_(g, 58, "180", 2);
        } else if (v->cal_step >= 3u) {
            gl_gfx_icon(g, CX - 4, 38, GL_ICON_CHECK, GL_INK_BLACK);
            text_(g, 54, "SAVED", 2);
        } else {
            text_(g, 38, "HOLD", 2);
            text_(g, 58, "STILL", 2);
        }
        if (v->cal_step < 3u) {
            text_(g, 80, "HARD FLAT SURFACE", 1);
            text_(g, 94, "TAP-TAP: QUIT", 1);
        }
        break;
    case GL_UI_ERROR:
        gl_gfx_icon(g, CX - 5, 26, GL_ICON_WARN, GL_INK_BLACK);
        text_(g, 44, "ERROR", 2);
        text_(g, 68, gl_status_name((gl_status_t)ui->error_code), 1);
        buf[0] = 'E';
        gl_fmt_int(buf + 1, sizeof(buf) - 1, (int32_t)ui->error_code);
        text_(g, 82, buf, 1);
        break;
    case GL_UI_LOW_BATT:
        gl_gfx_frame(g, 38, 42, 48, 24, GL_INK_BLACK);
        gl_gfx_frame(g, 39, 43, 46, 22, GL_INK_BLACK);
        gl_gfx_rect(g, 86, 49, 4, 10, GL_INK_BLACK);
        gl_gfx_rect(g, 42, 46, 6, 16, GL_INK_BLACK);
        text_(g, 78, "LOW BATTERY", 1);
        break;
    default:
        break;
    }
}
