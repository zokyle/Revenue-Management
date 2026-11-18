/*
 * test_pins.c - the generated pin map (hal/stm32u5/gl_pins.h) proved against
 * its source, the netlist's pin map electrical/gl1_main/pinmap.json, and
 * against the rules of the rev E board.
 *
 * THE PINS THEMSELVES ARE NOT ASSERTED HERE.  The layout step may still
 * exchange PROPOSED and CHANGED pins; then `make pins` regenerates the header
 * and this test must pass unchanged.  What is asserted:
 *
 *   - every row of the header equals the row of pinmap.json, which this file
 *     READS AGAIN ITSELF with a scanner of its own (not through the Python
 *     generator): signal, port, pin, pad, mode, alternate function, source,
 *     and the columns the generator derives from the pin map's words (pull,
 *     board circuit, EXTI line, state with the camera rail off, state
 *     asleep), derived here a second time by hand;
 *   - the rules: no two signals on one pin or pad; supply, crystal and debug
 *     pads free; one EXTI line per interrupt signal; no PWDN line on a pin
 *     the ROM loader transmits on; the charger and thermistor signals and the
 *     camera rail enable on no ROM-loader pin at all; nothing but an input or
 *     an alternate-function output on a USB Type-C CC pad; the BOOT0 pad
 *     shared with one output that rests low; the lines that float in reset
 *     listed; the reset levels; VBUS on a wake-up pin;
 *   - the 16 assignments DESIGN_SPEC section 4 fixes (they cannot move),
 *     written out by hand;
 *   - the charger circuit: what the pin map says, what drivers/power.c does;
 *   - the grain LEDs: the netlist's wiring against the driver's table.
 *
 * The test is run from the firmware directory (make test); the pin map is
 * found relative to it, or at the path given as the first argument.
 */
#include "gl_test.h"
#include "power.h"

#include <ctype.h>
#include <stdlib.h>

#include "gl_hal.h"
#include "gl_pins.h"
#include "gl_provisional.h"
#include "grain_frontend.h"
#include "gl_sim.h"
#include "lsm6dsv16x.h"

/* ---- the generated table ------------------------------------------------------- */

typedef struct {
    int logical;
    const char *name; /* "GL_PIN_..." */
    char port;
    int pin;
    int pad;
    int fn;
    int af;
    int pull;
    int board;
    int exti;
    int rail;
    int sleep;
    int src;
} pin_row_t;

#define ROW(logical, port, pin, pad, fn, af, pull, board, exti, rail, sleep, src) \
    { (int)(logical), #logical, #port[0], pin, pad, fn, af, pull, board, exti, rail, sleep, src },
static const pin_row_t rows_[] = { GL_PINS_TABLE(ROW) };
#undef ROW

static const pin_row_t *find_(gl_pin_t p)
{
    return &rows_[(int)p];
}

typedef struct {
    int logical;
    char port;
    int pin;
    const char *fn;
    int drives;
} boot_row_t;
#define BROW(logical, port, pin, fn, drives) { (int)(logical), #port[0], pin, #fn, drives },
static const boot_row_t boot_[] = { GL_PINS_BOOTLOADER_TABLE(BROW) };
#undef BROW

typedef struct {
    int logical;
    int level;
    int handover;
} reset_row_t;
#define RROW(logical, level, handover) { (int)(logical), level, handover },
static const reset_row_t reset_[] = { GL_PINS_RESET_TABLE(RROW) };
#undef RROW

#define FROW(logical) (int)(logical),
static const int floating_[] = { GL_PINS_FLOATING_TABLE(FROW) };
#undef FROW

typedef struct {
    const char *role;
    char port;
    int pin;
    int logical;
} ucpd_row_t;
#define UROW(role, port, pin, logical) { #role, #port[0], pin, (int)(logical) },
static const ucpd_row_t ucpd_[] = { GL_PINS_UCPD_TABLE(UROW) };
#undef UROW

/* ---- pinmap.json, read here independently ---------------------------------------- */

static const char *json_path_ = "../electrical/gl1_main/pinmap.json";
static char json_[200000];
static size_t json_len_;

typedef struct {
    char signal[24];
    char port_pin[8];
    int pad;
    char mode[12];
    char function[48];
    int af; /* -1 = null */
    char pull[72];
    char state[72];
    char source[12];
    char boot_fn[24];   /* "" = no bootloader function */
    char boot_role[12]; /* "drive" / "listen" */
    char wakeup[48];    /* the raw text of the list */
    char adc[32];
} jrow_t;

static jrow_t jrows_[64];
static size_t n_jrows_;

/* Position just after `"key":` (and blanks) inside [from, end), or NULL. */
static const char *jkey_(const char *from, const char *end, const char *key)
{
    char pat[48];
    const char *p;
    size_t n = strlen(key);
    pat[0] = '"';
    memcpy(&pat[1], key, n);
    pat[n + 1u] = '"';
    pat[n + 2u] = '\0';
    for (p = from; (p = strstr(p, pat)) != NULL && p < end; p += n + 2u) {
        const char *q = p + n + 2u;
        while (q < end && isspace((unsigned char)*q)) {
            q++;
        }
        if (q < end && *q == ':') {
            q++;
            while (q < end && isspace((unsigned char)*q)) {
                q++;
            }
            return q;
        }
    }
    return NULL;
}

/* Copy a JSON string value at p (after the key) into out; "" for null. */
static bool jstr_(const char *p, const char *end, char *out, size_t cap)
{
    size_t n = 0;
    out[0] = '\0';
    if (p == NULL) {
        return false;
    }
    if (strncmp(p, "null", 4) == 0) {
        return true;
    }
    if (*p != '"') {
        return false;
    }
    for (p++; p < end && *p != '"'; p++) {
        if (*p == '\\' && p + 1 < end) {
            p++;
        }
        if (n + 1u < cap) {
            out[n++] = *p;
        }
    }
    out[n] = '\0';
    return p < end;
}

/* Copy the raw text of a JSON list value ("[ ... ]") into out. */
static bool jlist_(const char *p, const char *end, char *out, size_t cap)
{
    size_t n = 0;
    out[0] = '\0';
    if (p == NULL) {
        return false;
    }
    if (strncmp(p, "null", 4) == 0) {
        return true;
    }
    if (*p != '[') {
        return false;
    }
    for (p++; p < end && *p != ']'; p++) {
        if (!isspace((unsigned char)*p) && n + 1u < cap) {
            out[n++] = *p;
        }
    }
    out[n] = '\0';
    return p < end;
}

static bool load_json_(void)
{
    FILE *f = fopen(json_path_, "rb");
    const char *pins, *end, *p;
    if (f == NULL) {
        return false;
    }
    json_len_ = fread(json_, 1, sizeof(json_) - 1u, f);
    fclose(f);
    json_[json_len_] = '\0';
    if (json_len_ == 0u || json_len_ >= sizeof(json_) - 1u) {
        return false;
    }
    pins = jkey_(json_, json_ + json_len_, "pins");
    end = strstr(json_, "\"supply_pads\"");
    if (pins == NULL || end == NULL || *pins != '[' || end < pins) {
        return false;
    }
    n_jrows_ = 0;
    /* a row is the text from one "signal" key to the next */
    p = strstr(pins, "\"signal\"");
    while (p != NULL && p < end) {
        const char *next = strstr(p + 8, "\"signal\"");
        const char *stop = (next != NULL && next < end) ? next : end;
        jrow_t *r;
        const char *v;
        char list[64];
        if (n_jrows_ >= GL_ARRAY_LEN(jrows_)) {
            return false;
        }
        r = &jrows_[n_jrows_];
        memset(r, 0, sizeof(*r));
        if (!jstr_(jkey_(p, stop, "signal"), stop, r->signal, sizeof(r->signal)) ||
            !jstr_(jkey_(p, stop, "port_pin"), stop, r->port_pin, sizeof(r->port_pin)) ||
            !jstr_(jkey_(p, stop, "mode"), stop, r->mode, sizeof(r->mode)) ||
            !jstr_(jkey_(p, stop, "function"), stop, r->function, sizeof(r->function)) ||
            !jstr_(jkey_(p, stop, "pull"), stop, r->pull, sizeof(r->pull)) ||
            !jstr_(jkey_(p, stop, "initial_state"), stop, r->state, sizeof(r->state)) ||
            !jstr_(jkey_(p, stop, "source"), stop, r->source, sizeof(r->source)) ||
            !jlist_(jkey_(p, stop, "wakeup"), stop, r->wakeup, sizeof(r->wakeup)) ||
            !jlist_(jkey_(p, stop, "adc"), stop, r->adc, sizeof(r->adc)) ||
            !jlist_(jkey_(p, stop, "bootloader"), stop, list, sizeof(list))) {
            return false;
        }
        v = jkey_(p, stop, "pad");
        if (v == NULL) {
            return false;
        }
        r->pad = atoi(v);
        v = jkey_(p, stop, "af");
        if (v == NULL) {
            return false;
        }
        r->af = (strncmp(v, "null", 4) == 0) ? -1 : atoi(v);
        if (list[0] != '\0') {
            /* "FN","role" with the blanks removed */
            const char *c = strchr(list, ',');
            size_t n;
            if (c == NULL || list[0] != '"' || c - list < 3) {
                return false;
            }
            n = (size_t)(c - list) - 2u;
            if (n >= sizeof(r->boot_fn)) {
                return false;
            }
            memcpy(r->boot_fn, &list[1], n);
            r->boot_fn[n] = '\0';
            strncpy(r->boot_role, c + 2, sizeof(r->boot_role) - 1u);
            r->boot_role[strcspn(r->boot_role, "\"")] = '\0';
        }
        n_jrows_++;
        p = (next != NULL && next < end) ? next : NULL;
    }
    return n_jrows_ > 0u;
}

static const jrow_t *jfind_(const char *signal)
{
    for (size_t i = 0; i < n_jrows_; i++) {
        if (strcmp(jrows_[i].signal, signal) == 0) {
            return &jrows_[i];
        }
    }
    return NULL;
}

static bool jport_pin_(const jrow_t *r, char *port, int *pin)
{
    if (r->port_pin[0] != 'P' || r->port_pin[1] < 'A' || r->port_pin[1] > 'H' ||
        !isdigit((unsigned char)r->port_pin[2])) {
        return false;
    }
    *port = r->port_pin[1];
    *pin = atoi(&r->port_pin[2]);
    return *pin >= 0 && *pin <= 15;
}

/* ---- tests ----------------------------------------------------------------------- */

GL_TEST(test_table_matches_the_logical_pins)
{
    GL_CHECK_EQ(GL_ARRAY_LEN(rows_), GL_PIN_COUNT);
    GL_CHECK_EQ(GL_PINS_COUNT, GL_PIN_COUNT);
    for (size_t i = 0; i < GL_ARRAY_LEN(rows_); i++) {
        GL_CHECK_EQ(rows_[i].logical, (int)i); /* rows in the order of gl_pin_t */
        GL_CHECK(rows_[i].port >= 'A' && rows_[i].port <= 'H');
        GL_CHECK(rows_[i].pin >= 0 && rows_[i].pin <= 15);
        GL_CHECK(rows_[i].pad >= 1 && rows_[i].pad <= 64);
        GL_CHECK(rows_[i].af >= 0 && rows_[i].af <= 15);
        GL_CHECK(strncmp(rows_[i].name, "GL_PIN_", 7) == 0);
    }
}

/* Every row of the header against the row of pinmap.json, with the derived
 * columns derived again here.  This is the test that makes "regenerated by
 * one command" safe: a header that was edited by hand, or generated from
 * another file, fails it. */
GL_TEST(test_every_row_equals_the_netlists_pin_map)
{
    unsigned spec = 0, proposed = 0, changed = 0;

    GL_CHECK(load_json_()); /* the pin map must be there: it is the proof's other half */
    if (n_jrows_ == 0u) {
        printf("    CANNOT READ %s\n", json_path_);
        return;
    }
    /* 47 signals of gl_pin_t plus the crystal, SWD and the BOOT0 strap */
    GL_CHECK_EQ(n_jrows_, (size_t)GL_PIN_COUNT + 5u);
    for (size_t i = 0; i < GL_ARRAY_LEN(rows_); i++) {
        const pin_row_t *r = &rows_[i];
        const jrow_t *j = jfind_(r->name + 7); /* without "GL_PIN_" */
        char port = '?';
        int pin = -1, want;
        GL_CHECK(j != NULL);
        if (j == NULL) {
            printf("    %s is not in the pin map\n", r->name);
            continue;
        }
        GL_CHECK(jport_pin_(j, &port, &pin));
        GL_CHECK_EQ(r->port, port);
        GL_CHECK_EQ(r->pin, pin);
        GL_CHECK_EQ(r->pad, j->pad);
        /* mode -> function kind */
        want = (strcmp(j->mode, "OUT_PP") == 0)    ? GL_PINFN_GPIO
               : (strcmp(j->mode, "AF") == 0)      ? GL_PINFN_AF
               : (strcmp(j->mode, "ANALOG") == 0)  ? GL_PINFN_ANALOG
               : (strcmp(j->mode, "SCCB_OD") == 0) ? GL_PINFN_SCCB
               : (strcmp(j->mode, "EXTI") == 0)    ? GL_PINFN_EXTI
                                                   : -1;
        GL_CHECK_EQ(r->fn, want);
        GL_CHECK_EQ(r->af, (j->af < 0) ? 0 : j->af);
        GL_CHECK_EQ(j->af >= 0, r->fn == GL_PINFN_AF);
        want = (strcmp(j->source, "SPEC") == 0)       ? GL_PINSRC_SPEC
               : (strcmp(j->source, "PROPOSED") == 0) ? GL_PINSRC_PROPOSED
               : (strcmp(j->source, "CHANGED") == 0)  ? GL_PINSRC_CHANGED
                                                      : -1;
        GL_CHECK_EQ(r->src, want);
        spec += (r->src == GL_PINSRC_SPEC) ? 1u : 0u;
        proposed += (r->src == GL_PINSRC_PROPOSED) ? 1u : 0u;
        changed += (r->src == GL_PINSRC_CHANGED) ? 1u : 0u;
        /* EXTI line = pin number, for interrupt inputs only */
        GL_CHECK_EQ(r->exti, (r->fn == GL_PINFN_EXTI) ? pin : GL_PINS_NO_EXTI);
        /* state with the camera rail off: what the pin map's words say */
        GL_CHECK_EQ(r->rail, (strstr(j->state, "while V2V8_CAM is off") != NULL) ? GL_PINRAIL_PARKED
                                                                              : GL_PINRAIL_ANY);
        /* state asleep */
        want = (r->rail == GL_PINRAIL_PARKED || strncmp(j->state, "analog or low", 13) == 0)
                   ? GL_PINSLEEP_PARKED
                   : (strncmp(j->state, "analog", 6) == 0) ? GL_PINSLEEP_ANALOG
                   : (strncmp(j->state, "input", 5) == 0)  ? GL_PINSLEEP_INPUT
                   : (strncmp(j->state, "high", 4) == 0)   ? GL_PINSLEEP_HIGH
                   : (strncmp(j->state, "low", 3) == 0)    ? GL_PINSLEEP_LOW
                                                           : -1;
        GL_CHECK_EQ(r->sleep, want);
        /* the board's circuit on the net: the part of "pull" after the slash */
        {
            const char *b = strstr(j->pull, " / ");
            b = (b != NULL) ? b + 3 : "";
            want = (b[0] == '\0')                        ? GL_PINBRD_NONE
                   : (strncmp(b, "divider", 7) == 0)     ? GL_PINBRD_DIVIDER
                   : (strstr(b, "to GND") != NULL)       ? GL_PINBRD_DOWN
                   : (strstr(b, "to V2V8_CAM") != NULL)  ? GL_PINBRD_UP_CAM
                   : (strstr(b, "to V2V8") != NULL)      ? GL_PINBRD_UP
                   : (strstr(b, "series") != NULL)       ? GL_PINBRD_SERIES
                                                         : -1;
            GL_CHECK_EQ(r->board, want);
            GL_CHECK(strncmp(j->pull, "none", 4) == 0); /* no signal asks for an internal pull */
        }
        /* internal pull: none, but for the two bus inputs that float between
         * transfers (firmware note 15) */
        GL_CHECK_EQ(r->pull, (strstr(j->function, "_MISO") != NULL) ? GL_PINPULL_DOWN : GL_PINPULL_NONE);
    }
    GL_CHECK_EQ(spec + proposed + changed, (unsigned)GL_PIN_COUNT);
    /* the five fixed rows are there and are not signals of the table */
    {
        static const char *const fixed[] = { "OSC32_IN", "OSC32_OUT", "SWDIO", "SWCLK", "BOOT0" };
        for (size_t k = 0; k < GL_ARRAY_LEN(fixed); k++) {
            const jrow_t *j = jfind_(fixed[k]);
            char port = '?';
            int pin = -1;
            GL_CHECK(j != NULL);
            if (j == NULL) {
                continue;
            }
            GL_CHECK(jport_pin_(j, &port, &pin));
            for (size_t i = 0; i < GL_ARRAY_LEN(rows_); i++) {
                if (rows_[i].port == port && rows_[i].pin == pin) {
                    /* only the BOOT0 strap shares its pad, with the one declared signal */
                    GL_CHECK(strcmp(fixed[k], "BOOT0") == 0);
                    GL_CHECK_EQ(rows_[i].logical, (int)GL_PINS_BOOT0_SHARED_WITH);
                    GL_CHECK_EQ(rows_[i].pad, j->pad);
                }
            }
        }
        GL_CHECK(strcmp(jfind_("BOOT0") != NULL ? jfind_("BOOT0")->mode : "", "STRAP") == 0);
    }
    printf("    %u signals of %s: every row of hal/stm32u5/gl_pins.h equals it (%u SPEC, %u PROPOSED, "
           "%u CHANGED by the netlist); header generated from sha256 %.12s...\n",
           (unsigned)GL_ARRAY_LEN(rows_), json_path_, spec, proposed, changed, GL_PINS_SOURCE_SHA256);
}

GL_TEST(test_no_pad_or_port_pin_used_twice)
{
    /* supply and reset pads of the LQFP-64, read from the pin map's
     * "supply_pads"; crystal and debug pads are checked by name below */
    int supply[32];
    size_t n_supply = 0;
    const char *p = (json_len_ != 0u) ? strstr(json_, "\"supply_pads\"") : NULL;
    const char *end = (p != NULL) ? strstr(p, "]") : NULL;

    GL_CHECK(p != NULL && end != NULL);
    while (p != NULL && end != NULL && (p = jkey_(p, end, "pad")) != NULL && n_supply < GL_ARRAY_LEN(supply)) {
        supply[n_supply++] = atoi(p);
    }
    GL_CHECK_EQ(n_supply, 13u); /* VBAT, NRST, VSSA, VDDA, 4 x VSS, 3 x VDD, VCAP, VDDUSB */
    for (size_t i = 0; i < GL_ARRAY_LEN(rows_); i++) {
        for (size_t j = i + 1; j < GL_ARRAY_LEN(rows_); j++) {
            GL_CHECK(rows_[i].pad != rows_[j].pad);
            GL_CHECK(!(rows_[i].port == rows_[j].port && rows_[i].pin == rows_[j].pin));
            /* one EXTI line per pin NUMBER: two interrupt pins must differ in it */
            if (rows_[i].fn == GL_PINFN_EXTI && rows_[j].fn == GL_PINFN_EXTI) {
                GL_CHECK(rows_[i].pin != rows_[j].pin);
                GL_CHECK(rows_[i].exti != rows_[j].exti);
            }
        }
        for (size_t k = 0; k < n_supply; k++) {
            GL_CHECK(rows_[i].pad != supply[k]);
        }
        /* SWD (PA13, PA14) and the 32 kHz crystal (PC14, PC15) stay free */
        GL_CHECK(!(rows_[i].port == 'A' && (rows_[i].pin == 13 || rows_[i].pin == 14)));
        GL_CHECK(!(rows_[i].port == 'C' && (rows_[i].pin == 14 || rows_[i].pin == 15)));
    }
    /* the four interrupt signals, and the lines the backend builds its
     * vectors from */
    GL_CHECK_EQ(find_(GL_PIN_IMU_INT1)->fn, GL_PINFN_EXTI);
    GL_CHECK_EQ(find_(GL_PIN_IMU_INT2)->fn, GL_PINFN_EXTI);
    GL_CHECK_EQ(find_(GL_PIN_VBUS_SENSE)->fn, GL_PINFN_EXTI);
    GL_CHECK_EQ(find_(GL_PIN_CHG_STAT)->fn, GL_PINFN_EXTI);
    GL_CHECK_EQ(GL_PINS_EXTI_IMU_INT1, find_(GL_PIN_IMU_INT1)->pin);
    GL_CHECK_EQ(GL_PINS_EXTI_IMU_INT2, find_(GL_PIN_IMU_INT2)->pin);
    GL_CHECK_EQ(GL_PINS_EXTI_VBUS_SENSE, find_(GL_PIN_VBUS_SENSE)->pin);
    GL_CHECK_EQ(GL_PINS_EXTI_CHG_STAT, find_(GL_PIN_CHG_STAT)->pin);
    {
        unsigned n_exti = 0;
        for (size_t i = 0; i < GL_ARRAY_LEN(rows_); i++) {
            n_exti += (rows_[i].fn == GL_PINFN_EXTI) ? 1u : 0u;
        }
        GL_CHECK_EQ(n_exti, 4u);
    }
    printf("    interrupt lines: IMU_INT1 EXTI%d, IMU_INT2 EXTI%d, VBUS_SENSE EXTI%d, CHG_STAT EXTI%d "
           "(all different)\n", GL_PINS_EXTI_IMU_INT1, GL_PINS_EXTI_IMU_INT2, GL_PINS_EXTI_VBUS_SENSE,
           GL_PINS_EXTI_CHG_STAT);
}

GL_TEST(test_design_spec_rows)
{
    /* DESIGN_SPEC section 4, copied by hand: pin, pad, AF.  These are fixed
     * by the specification (verified there against ST's open pin data) and
     * are the only pins this test names. */
    static const struct {
        gl_pin_t logical;
        char port;
        int pin, pad, af;
    } spec[] = {
        { GL_PIN_CAM_D0, 'C', 6, 37, 10 },     { GL_PIN_CAM_D1, 'C', 7, 38, 10 },
        { GL_PIN_CAM_D2, 'C', 8, 39, 10 },     { GL_PIN_CAM_D3, 'C', 9, 40, 4 },
        { GL_PIN_CAM_D4, 'C', 11, 52, 10 },    { GL_PIN_CAM_D5, 'B', 6, 58, 10 },
        { GL_PIN_CAM_D6, 'B', 8, 61, 10 },     { GL_PIN_CAM_D7, 'B', 9, 62, 10 },
        { GL_PIN_CAM_PIXCLK, 'A', 6, 22, 4 },  { GL_PIN_CAM_HREF, 'A', 4, 20, 10 },
        { GL_PIN_CAM_VSYNC, 'B', 7, 59, 10 },  { GL_PIN_CAM_XVCLK, 'A', 8, 41, 0 },
        { GL_PIN_SPI1_MISO, 'B', 4, 56, 5 },   { GL_PIN_USB_DM, 'A', 11, 44, 10 },
        { GL_PIN_USB_DP, 'A', 12, 45, 10 },    { GL_PIN_LCD_EXTCOMIN, 'B', 2, 28, 1 },
    };
    for (size_t i = 0; i < GL_ARRAY_LEN(spec); i++) {
        const pin_row_t *r = find_(spec[i].logical);
        GL_CHECK_EQ(r->port, spec[i].port);
        GL_CHECK_EQ(r->pin, spec[i].pin);
        GL_CHECK_EQ(r->pad, spec[i].pad);
        GL_CHECK_EQ(r->af, spec[i].af);
        GL_CHECK_EQ(r->fn, GL_PINFN_AF);
        GL_CHECK_EQ(r->src, GL_PINSRC_SPEC);
    }
    /* op-amp pins: OPAMP1 has one set of pads */
    GL_CHECK(find_(GL_PIN_OPAMP_VINP)->port == 'A' && find_(GL_PIN_OPAMP_VINP)->pin == 0 &&
             find_(GL_PIN_OPAMP_VINP)->pad == 14);
    GL_CHECK(find_(GL_PIN_OPAMP_VINM)->port == 'A' && find_(GL_PIN_OPAMP_VINM)->pin == 1 &&
             find_(GL_PIN_OPAMP_VINM)->pad == 15);
    GL_CHECK(find_(GL_PIN_OPAMP_VOUT)->port == 'A' && find_(GL_PIN_OPAMP_VOUT)->pin == 3 &&
             find_(GL_PIN_OPAMP_VOUT)->pad == 17);
    GL_CHECK_EQ(GL_PINS_ADC_CH_GRAIN_TIA, 8); /* PA3 = ADC1_IN8 */
}

GL_TEST(test_function_kinds_and_analog_channels)
{
    /* the three SCCB lines are bit-banged open-drain pins */
    GL_CHECK_EQ(find_(GL_PIN_CAM_SCCB_SDA)->fn, GL_PINFN_SCCB);
    GL_CHECK_EQ(find_(GL_PIN_CAM_L_SCL)->fn, GL_PINFN_SCCB);
    GL_CHECK_EQ(find_(GL_PIN_CAM_R_SCL)->fn, GL_PINFN_SCCB);
    /* their pull-ups go to the camera rail, not to the always-on rail */
    GL_CHECK_EQ(find_(GL_PIN_CAM_SCCB_SDA)->board, GL_PINBRD_UP_CAM);
    GL_CHECK_EQ(find_(GL_PIN_CAM_L_SCL)->board, GL_PINBRD_UP_CAM);
    GL_CHECK_EQ(find_(GL_PIN_CAM_R_SCL)->board, GL_PINBRD_UP_CAM);
    /* analog */
    GL_CHECK_EQ(find_(GL_PIN_VBAT_SENSE)->fn, GL_PINFN_ANALOG);
    GL_CHECK_EQ(find_(GL_PIN_OPAMP_VOUT)->fn, GL_PINFN_ANALOG);
    GL_CHECK_EQ(find_(GL_PIN_NTC_SENSE)->fn, GL_PINFN_ANALOG);
    /* the ADC channels are the pin map's: "ADC1_IN<n>" in the row's function
     * and in its list of the pad's channels */
    if (n_jrows_ != 0u) {
        static const struct {
            const char *signal;
            int channel;
        } adc[] = { { "OPAMP_VOUT", GL_PINS_ADC_CH_GRAIN_TIA },
                    { "VBAT_SENSE", GL_PINS_ADC_CH_VBAT_DIV },
                    { "NTC_SENSE", GL_PINS_ADC_CH_CELL_NTC } };
        for (size_t i = 0; i < GL_ARRAY_LEN(adc); i++) {
            const jrow_t *j = jfind_(adc[i].signal);
            char want[24];
            snprintf(want, sizeof(want), "ADC1_IN%d", adc[i].channel);
            GL_CHECK(j != NULL && strstr(j->function, want) != NULL && strstr(j->adc, want) != NULL);
        }
        /* VBUS_SENSE and IMU_INT1 sit on PWR wake-up pins; VBUS's is what
         * ends ship mode */
        {
            const jrow_t *v = jfind_("VBUS_SENSE"), *m = jfind_("IMU_INT1");
            char want[24];
            snprintf(want, sizeof(want), "PWR_WKUP%d", GL_PINS_WKUP_VBUS_SENSE);
            GL_CHECK(v != NULL && strstr(v->function, want) != NULL && strstr(v->wakeup, want) != NULL);
            snprintf(want, sizeof(want), "PWR_WKUP%d", GL_PINS_WKUP_IMU_INT1);
            GL_CHECK(m != NULL && strstr(m->function, want) != NULL && strstr(m->wakeup, want) != NULL);
            GL_CHECK(GL_PINS_WKUP_VBUS_SENSE != GL_PINS_WKUP_IMU_INT1);
        }
    }
    /* every camera-facing pin exists, is parked with the rail off, and none
     * of them is an interrupt pin; nothing else is "camera-facing" */
    for (int p = 0; p < (int)GL_PIN_COUNT; p++) {
        const bool facing = (p >= (int)GL_PIN_CAM_FACING_FIRST && p <= (int)GL_PIN_CAM_FACING_LAST);
        GL_CHECK_EQ(find_((gl_pin_t)p)->rail == GL_PINRAIL_PARKED, facing);
        if (facing) {
            GL_CHECK(find_((gl_pin_t)p)->fn != GL_PINFN_EXTI);
            GL_CHECK_EQ(find_((gl_pin_t)p)->sleep, GL_PINSLEEP_PARKED);
        }
    }
    /* both SPI buses are complete alternate-function groups; the two MISO
     * lines keep an internal pull-down (they float between transfers) */
    GL_CHECK(find_(GL_PIN_SPI1_SCK)->fn == GL_PINFN_AF && find_(GL_PIN_SPI1_MOSI)->fn == GL_PINFN_AF &&
             find_(GL_PIN_SPI1_MISO)->fn == GL_PINFN_AF);
    GL_CHECK(find_(GL_PIN_SPI2_SCK)->fn == GL_PINFN_AF && find_(GL_PIN_SPI2_MOSI)->fn == GL_PINFN_AF &&
             find_(GL_PIN_SPI2_MISO)->fn == GL_PINFN_AF);
    GL_CHECK_EQ(find_(GL_PIN_SPI1_MISO)->pull, GL_PINPULL_DOWN);
    GL_CHECK_EQ(find_(GL_PIN_SPI2_MISO)->pull, GL_PINPULL_DOWN);
    for (size_t i = 0; i < GL_ARRAY_LEN(rows_); i++) {
        if (rows_[i].logical != (int)GL_PIN_SPI1_MISO && rows_[i].logical != (int)GL_PIN_SPI2_MISO) {
            GL_CHECK_EQ(rows_[i].pull, GL_PINPULL_NONE);
        }
    }
}

/* The ROM loader (an update, or a board that was never programmed) runs with
 * the camera rail off and the charger on its hardware default.  The list of
 * its pins is PROVISIONAL in the pin map (memory of ST AN2606); what is
 * checked here is that the generated table equals the pin map's and that the
 * rules hold on it. */
GL_TEST(test_rom_bootloader_pins)
{
    static const gl_pin_t pwdn[] = { GL_PIN_CAM_L_PWDN, GL_PIN_CAM_R_PWDN };
    static const gl_pin_t never[] = { GL_PIN_CHG_INHIBIT, GL_PIN_NTC_BIAS, GL_PIN_NTC_SENSE,
                                      GL_PIN_CAM_PWR_EN };
    unsigned n_out = 0, spec_conflicts = 0, n_json = 0;

    /* the table against the pin map, both ways */
    for (size_t i = 0; i < GL_ARRAY_LEN(boot_); i++) {
        const pin_row_t *r = find_((gl_pin_t)boot_[i].logical);
        const jrow_t *j = jfind_(r->name + 7);
        GL_CHECK_EQ(r->port, boot_[i].port);
        GL_CHECK_EQ(r->pin, boot_[i].pin);
        GL_CHECK(j != NULL && strcmp(j->boot_fn, boot_[i].fn) == 0);
        GL_CHECK(j != NULL && (strcmp(j->boot_role, "drive") == 0) == (boot_[i].drives != 0));
        n_out += (boot_[i].drives != 0) ? 1u : 0u;
    }
    for (size_t i = 0; i < n_jrows_; i++) {
        n_json += (jrows_[i].boot_fn[0] != '\0') ? 1u : 0u;
    }
    GL_CHECK_EQ(n_json, (unsigned)GL_ARRAY_LEN(boot_));
    /* the loader transmits on its USART TX pins and its SPI / CAN outputs:
     * no PWDN line there (DESIGN_SPEC section 4) */
    for (size_t i = 0; i < GL_ARRAY_LEN(boot_); i++) {
        for (size_t k = 0; k < GL_ARRAY_LEN(pwdn); k++) {
            GL_CHECK(!(boot_[i].drives != 0 && boot_[i].logical == (int)pwdn[k]));
        }
        /* the charger stop, the two thermistor pins and the camera rail
         * enable are on no loader pin at all, driven or listened on */
        for (size_t k = 0; k < GL_ARRAY_LEN(never); k++) {
            GL_CHECK(boot_[i].logical != (int)never[k]);
        }
        /* a camera-facing pin the loader DRIVES back-powers the unpowered
         * sensors: only the rows the specification fixes may be there */
        if (boot_[i].drives != 0 && find_((gl_pin_t)boot_[i].logical)->rail == GL_PINRAIL_PARKED) {
            GL_CHECK_EQ(find_((gl_pin_t)boot_[i].logical)->src, GL_PINSRC_SPEC);
            spec_conflicts++;
        }
    }
    for (size_t k = 0; k < GL_ARRAY_LEN(pwdn); k++) {
        GL_CHECK_EQ(find_(pwdn[k])->fn, GL_PINFN_GPIO);
    }
    printf("    %u signals on ROM-loader pins (pin list PROVISIONAL), %u of them driven by the loader; "
           "no PWDN, charger, thermistor or rail-enable signal among them; %u camera-facing SPEC "
           "row(s) on a driven pin (behind their 220 ohm resistors: release gate)\n",
           (unsigned)GL_ARRAY_LEN(boot_), n_out, spec_conflicts);
    GL_CHECK(spec_conflicts <= 2u); /* D7 and PIXCLK, fixed by DESIGN_SPEC */
}

/* PA15 and PB15 are USB Type-C CC pads of the processor; PB5 and PB14 switch
 * their dead-battery pull-downs (what they do is PROVISIONAL in the pin map).
 * A CC pad carries an input or an alternate-function output and nothing
 * else: never a GPIO output, an LED line or a signal that switches power. */
GL_TEST(test_usb_type_c_cc_pads)
{
    unsigned n_cc = 0, n_db = 0;
    GL_CHECK_EQ(GL_ARRAY_LEN(ucpd_), 4u);
    for (size_t i = 0; i < GL_ARRAY_LEN(ucpd_); i++) {
        const bool cc = strstr(ucpd_[i].role, "_CC") != NULL && strstr(ucpd_[i].role, "DBCC") == NULL;
        /* the pad named is the pad of the signal named, if a signal is there */
        if (ucpd_[i].logical < (int)GL_PIN_COUNT) {
            const pin_row_t *r = find_((gl_pin_t)ucpd_[i].logical);
            GL_CHECK_EQ(r->port, ucpd_[i].port);
            GL_CHECK_EQ(r->pin, ucpd_[i].pin);
            if (cc) {
                GL_CHECK(r->fn == GL_PINFN_EXTI || r->fn == GL_PINFN_ANALOG || r->fn == GL_PINFN_AF);
                GL_CHECK(r->fn != GL_PINFN_GPIO && r->fn != GL_PINFN_SCCB);
            }
        }
        /* and no OTHER signal is on that pad */
        for (size_t k = 0; k < GL_ARRAY_LEN(rows_); k++) {
            if (rows_[k].port == ucpd_[i].port && rows_[k].pin == ucpd_[i].pin) {
                GL_CHECK_EQ(rows_[k].logical, ucpd_[i].logical);
            }
        }
        n_cc += cc ? 1u : 0u;
        n_db += cc ? 0u : 1u;
        /* the pin map says the same */
        GL_CHECK(json_len_ != 0u && strstr(json_, ucpd_[i].role) != NULL);
    }
    GL_CHECK_EQ(n_cc, 2u);
    GL_CHECK_EQ(n_db, 2u);
    GL_CHECK_EQ(GL_PINS_UCPD_DBDIS_FIRST, 1);
    /* the status input of the charger is one of them: an input, with the
     * board's pull-up and no internal pull */
    GL_CHECK_EQ(find_(GL_PIN_CHG_STAT)->fn, GL_PINFN_EXTI);
    GL_CHECK_EQ(find_(GL_PIN_CHG_STAT)->board, GL_PINBRD_UP);
    GL_CHECK_EQ(find_(GL_PIN_CHG_STAT)->pull, GL_PINPULL_NONE);
    printf("    CC pads: %s on P%c%d, %s on P%c%d (an input and an alternate-function output)\n",
           find_((gl_pin_t)ucpd_[0].logical)->name + 7, ucpd_[0].port, ucpd_[0].pin,
           find_((gl_pin_t)ucpd_[1].logical)->name + 7, ucpd_[1].port, ucpd_[1].pin);
}

/* The BOOT0 strap, the levels the board gives undriven pins, and the lines
 * that have none. */
GL_TEST(test_boot0_reset_levels_and_floating_lines)
{
    bool seen[GL_PIN_COUNT];
    unsigned handover = 0;
    const pin_row_t *b0 = find_(GL_PINS_BOOT0_SHARED_WITH);

    /* the one signal on the BOOT0 pad: an output that rests low or analog on
     * a pulled-down net, so the strap reads 0 at every reset */
    GL_CHECK_EQ(b0->fn, GL_PINFN_GPIO);
    GL_CHECK_EQ(b0->sleep, GL_PINSLEEP_PARKED);
    GL_CHECK_EQ(b0->board, GL_PINBRD_DOWN);
    GL_CHECK(b0->logical == (int)GL_PIN_CAM_L_PWDN || b0->logical == (int)GL_PIN_CAM_R_PWDN ||
             b0->logical == (int)GL_PIN_NTC_BIAS || b0->logical == (int)GL_PIN_CAM_PWR_EN ||
             b0->logical == (int)GL_PIN_CHG_INHIBIT); /* NETLIST_NOTES 3.4: the candidates */

    /* reset levels: exactly the rows with a resistor to ground or to the
     * always-on rail; hand-over for outputs with a resting level */
    memset(seen, 0, sizeof(seen));
    for (size_t i = 0; i < GL_ARRAY_LEN(reset_); i++) {
        const pin_row_t *r = find_((gl_pin_t)reset_[i].logical);
        seen[reset_[i].logical] = true;
        GL_CHECK(r->board == GL_PINBRD_DOWN || r->board == GL_PINBRD_UP);
        GL_CHECK_EQ(reset_[i].level, (r->board == GL_PINBRD_UP) ? 1 : 0);
        GL_CHECK_EQ(reset_[i].handover,
                    (r->fn == GL_PINFN_GPIO && (r->sleep == GL_PINSLEEP_LOW || r->sleep == GL_PINSLEEP_HIGH))
                        ? 1 : 0);
        if (reset_[i].handover != 0) {
            /* the resistor holds the pin at its resting, inactive level */
            GL_CHECK_EQ(reset_[i].level, (r->sleep == GL_PINSLEEP_HIGH) ? 1 : 0);
            handover++;
        }
    }
    for (size_t i = 0; i < GL_ARRAY_LEN(rows_); i++) {
        GL_CHECK_EQ(seen[i], rows_[i].board == GL_PINBRD_DOWN || rows_[i].board == GL_PINBRD_UP);
    }
    /* the four chip selects / DISP and the camera rail enable (DESIGN_SPEC
     * section 4, "Defined states during reset"), each at its inactive level */
    GL_CHECK(seen[GL_PIN_LCD_SCS] && seen[GL_PIN_LCD_DISP] && seen[GL_PIN_FLASH_CS] &&
             seen[GL_PIN_IMU_CS] && seen[GL_PIN_CAM_PWR_EN]);
    for (size_t i = 0; i < GL_ARRAY_LEN(reset_); i++) {
        if (reset_[i].handover != 0) {
            const bool active_low_cs = (reset_[i].logical == (int)GL_PIN_FLASH_CS ||
                                        reset_[i].logical == (int)GL_PIN_IMU_CS);
            GL_CHECK_EQ(reset_[i].level != 0, active_low_cs);
        }
    }
    GL_CHECK_EQ(handover, 5u);
    /* the gate of the charger's stop MOSFET is held OFF with the MCU in
     * reset, in the loader or unpowered: the charger runs by itself */
    GL_CHECK(seen[GL_PIN_CHG_INHIBIT]);
    GL_CHECK_EQ(find_(GL_PIN_CHG_INHIBIT)->board, GL_PINBRD_DOWN);
    GL_CHECK_EQ(find_(GL_PIN_CHG_INHIBIT)->fn, GL_PINFN_GPIO); /* push-pull */
    GL_CHECK_EQ(find_(GL_PIN_CHG_INHIBIT)->sleep, GL_PINSLEEP_PARKED);

    /* lines without a board resistor that float in reset (firmware note 15):
     * outputs or bus outputs with nothing on the net, each named in the note */
    GL_CHECK(GL_ARRAY_LEN(floating_) >= 1u);
    for (size_t i = 0; i < GL_ARRAY_LEN(floating_); i++) {
        const pin_row_t *r = find_((gl_pin_t)floating_[i]);
        char pp[8];
        GL_CHECK(r->board == GL_PINBRD_NONE || r->board == GL_PINBRD_SERIES);
        GL_CHECK(r->fn == GL_PINFN_GPIO || r->fn == GL_PINFN_AF);
        GL_CHECK(r->sleep == GL_PINSLEEP_LOW || r->sleep == GL_PINSLEEP_PARKED);
        snprintf(pp, sizeof(pp), "P%c%d", r->port, r->pin);
        if (json_len_ != 0u) {
            const char *note = strstr(json_, "Lines without a board pull float");
            GL_CHECK(note != NULL && strstr(note, pp) != NULL &&
                     strstr(note, pp) < strstr(note, "gl_hal_init() must give each its level"));
        }
    }
    printf("    BOOT0 pad shared with %s; %u pins with a board resistor (%u taken over at its level by "
           "gl_hal_init); %u lines float in reset and get their level first\n", b0->name + 7,
           (unsigned)GL_ARRAY_LEN(reset_), handover, (unsigned)GL_ARRAY_LEN(floating_));
}

/* EXTCOMIN divider, the grain bias time and the firmware notes. */
GL_TEST(test_constants_carried_by_the_pin_map)
{
    GL_CHECK_EQ(GL_PINS_EXTCOMIN_LSE_TICKS, 547);
    GL_CHECK_EQ(GL_PINS_EXTCOMIN_LSE_TICKS, GL_PROV_LCD_EXTCOMIN_PERIOD_LSE_TICKS);
    /* 32768 / 547 = 59.905 Hz: inside 54-65 Hz and inside 1-60 Hz */
    GL_CHECK(32768.0 / (double)GL_PINS_EXTCOMIN_LSE_TICKS > 54.0);
    GL_CHECK(32768.0 / (double)GL_PINS_EXTCOMIN_LSE_TICKS < 60.0);
    GL_CHECK(32768.0 / 546.0 > 60.0); /* why it is not 546 */
    /* the grain bias hangs on LCD_DISP: the driver's settling time covers
     * what the netlist asks for */
    GL_CHECK_EQ(GL_PINS_GRAIN_BIAS_DISP_MS, 35);
    GL_CHECK(GL_PROV_GRAIN_POWER_SETTLE_MS >= (unsigned)GL_PINS_GRAIN_BIAS_DISP_MS);
    /* VBUS removal is seen on the pin within this time; the simulator can
     * lag the pin by as much */
    GL_CHECK(GL_PINS_VBUS_REMOVAL_SEEN_MS >= 1 && GL_PINS_VBUS_REMOVAL_SEEN_MS <= 100);
    GL_CHECK_EQ(GL_PINS_USB_VBUS_SENSING_OFF, 1);
    GL_CHECK_EQ(GL_PINS_LSE_DRIVE_MEDIUM_LOW, 1);
    /* every firmware note of the pin map is known to the generator (it stops
     * otherwise); the count in the header is the count in the file */
    if (json_len_ != 0u) {
        const char *p = jkey_(json_, json_ + json_len_, "firmware_notes");
        const char *end = (p != NULL) ? strstr(p, "\"grain_leds\"") : NULL;
        unsigned notes = 0;
        GL_CHECK(p != NULL && end != NULL && *p == '[');
        for (p = (p != NULL) ? p + 1 : NULL; p != NULL && end != NULL && p < end; p++) {
            if (*p == '"') {
                notes++;
                for (p++; p < end && *p != '"'; p++) {
                    if (*p == '\\') {
                        p++;
                    }
                }
            }
        }
        /* (the key "grain_leds" itself is the last string counted) */
        GL_CHECK_EQ(notes, (unsigned)GL_PINS_FIRMWARE_NOTES);
        printf("    %u firmware notes in the pin map, each known to tools/gen_pins.py and listed in "
               "the header with the place that acts on it\n", (unsigned)GL_PINS_FIRMWARE_NOTES);
    }
}

/*
 * The IMU's mounting (phase-3 review, hardware finding 1).  The pin map says
 * how U4 lies on the board; until this test existed the firmware kept an
 * identity placeholder and every slope on the real board would have come out
 * turned by 90 degrees, with all tests passing (the simulator's board was
 * identity too).  Three things are proved here, each against the JSON read
 * by this file's own scanner:
 *   - the generated header carries the pin map's mounting;
 *   - the driver's default mounting IS that mounting;
 *   - on a simulated board mounted as the JSON says, a marker tilted
 *     toward +x reads as +x through the driver's default, and with the old
 *     identity placeholder it reads on the wrong axis.
 * NOT VERIFIED: that the pin map's statement is right (it marks itself
 * PROVISIONAL: ST's axis drawing of the LSM6DSV16X was not read).
 */
static gl_imu_t pins_imu_;

GL_TEST(test_imu_mounting_is_the_pin_maps)
{
    static const char *const keys[3] = { "marker_x", "marker_y", "marker_z" };
    const int h_axis[3] = { GL_PINS_IMU_MARKER_X_AXIS, GL_PINS_IMU_MARKER_Y_AXIS,
                            GL_PINS_IMU_MARKER_Z_AXIS };
    const int h_sign[3] = { GL_PINS_IMU_MARKER_X_SIGN, GL_PINS_IMU_MARKER_Y_SIGN,
                            GL_PINS_IMU_MARKER_Z_SIGN };
    const gl_imu_mount_t identity = { { 0, 1, 2 }, { 1, 1, 1 } };
    const float a[3] = { 0.050f, -0.020f, 0.9985f }; /* tilted: marker +x up-slope */
    const float g[3] = { 0.0f, 0.0f, 0.0f };
    int8_t j_axis[3] = { 0, 0, 0 }, j_sign[3] = { 0, 0, 0 };
    gl_imu_mount_t def;
    gl_imu_raw_t s;
    const char *m, *end;

    GL_CHECK(json_len_ != 0u);
    m = jkey_(json_, json_ + json_len_, "imu_mounting");
    end = (m != NULL) ? strstr(m, "\"open_items_for_firmware\"") : NULL;
    GL_CHECK(m != NULL && end != NULL);
    if (m == NULL || end == NULL) {
        return;
    }
    for (unsigned i = 0; i < 3u; i++) {
        const char *row = jkey_(m, end, keys[i]);
        const char *stop = (row != NULL) ? strchr(row, '}') : NULL;
        const char *v;
        GL_CHECK(row != NULL && stop != NULL && stop < end);
        if (row == NULL || stop == NULL) {
            return;
        }
        v = jkey_(row, stop, "sensor_axis");
        GL_CHECK(v != NULL);
        j_axis[i] = (int8_t)((v != NULL) ? atoi(v) : -1);
        v = jkey_(row, stop, "sign");
        GL_CHECK(v != NULL);
        j_sign[i] = (int8_t)((v != NULL) ? atoi(v) : 0);
        GL_CHECK_EQ(h_axis[i], j_axis[i]);
        GL_CHECK_EQ(h_sign[i], j_sign[i]);
    }
    gl_imu_mount_defaults(&def);
    for (unsigned i = 0; i < 3u; i++) {
        GL_CHECK_EQ(def.axis[i], (uint8_t)j_axis[i]);
        GL_CHECK_EQ(def.sign[i], j_sign[i]);
    }
    /* behaviour: the board of the JSON, the driver's default */
    gl_sim_reset(true);
    (void)gl_hal_init();
    gl_sim_imu_set_mounting(j_axis, j_sign);
    GL_CHECK_EQ(gl_imu_init(&pins_imu_, NULL), GL_OK);
    GL_CHECK_EQ(gl_imu_start_measure(&pins_imu_), GL_OK);
    gl_sim_imu_set_static(a, g);
    gl_hal_delay_ms(10);
    GL_CHECK_EQ(gl_imu_read(&pins_imu_, &s), GL_OK);
    GL_CHECK_NEAR((float)s.ax * pins_imu_.accel_g_per_lsb, a[0], 1e-3);
    GL_CHECK_NEAR((float)s.ay * pins_imu_.accel_g_per_lsb, a[1], 1e-3);
    GL_CHECK_NEAR((float)s.az * pins_imu_.accel_g_per_lsb, a[2], 1e-3);
    {
        const float ok_x = (float)s.ax * pins_imu_.accel_g_per_lsb;
        float bad_x, bad_y;
        /* the placeholder the firmware had until this review */
        GL_CHECK_EQ(gl_imu_init(&pins_imu_, &identity), GL_OK);
        GL_CHECK_EQ(gl_imu_start_measure(&pins_imu_), GL_OK);
        gl_hal_delay_ms(10);
        GL_CHECK_EQ(gl_imu_read(&pins_imu_, &s), GL_OK);
        bad_x = (float)s.ax * pins_imu_.accel_g_per_lsb;
        bad_y = (float)s.ay * pins_imu_.accel_g_per_lsb;
        if (j_axis[0] != 0 || j_sign[0] != 1 || j_axis[1] != 1 || j_sign[1] != 1) {
            GL_CHECK(fabsf(bad_x - a[0]) > 0.02f || fabsf(bad_y - a[1]) > 0.02f);
        }
        printf("    pin map: marker x = %+d * sensor %c, y = %+d * sensor %c, z = %+d * sensor %c; "
               "header and driver default equal to it.  A 50 / -20 mg tilt on that board reads "
               "x %+.1f mg through the driver's default; the old identity placeholder read "
               "x %+.1f, y %+.1f mg\n",
               j_sign[0], "XYZ"[j_axis[0]], j_sign[1], "XYZ"[j_axis[1]], j_sign[2], "XYZ"[j_axis[2]],
               (double)(1000.0f * ok_x), (double)(1000.0f * bad_x), (double)(1000.0f * bad_y));
    }
    /* the open items: the header's count is the file's (an unknown one stops
     * the generator; its self-test seeds one) */
    {
        const char *p = jkey_(json_, json_ + json_len_, "open_items_for_firmware");
        const char *e2 = (p != NULL) ? strstr(p, "\"verification\"") : NULL;
        unsigned items = 0;
        GL_CHECK(p != NULL && e2 != NULL && *p == '[');
        for (p = (p != NULL) ? p + 1 : NULL; p != NULL && e2 != NULL && p < e2 && *p != ']'; p++) {
            if (*p == '"') {
                items++;
                for (p++; p < e2 && *p != '"'; p++) {
                    if (*p == '\\') {
                        p++;
                    }
                }
            }
        }
        GL_CHECK_EQ(items, (unsigned)GL_PINS_OPEN_ITEMS);
    }
}

/*
 * The charger circuit: what the netlist's pin map states and what the driver
 * does.  Until phase 3 this test PINNED A DIFFERENCE as NOT MET (the driver
 * was written for the rev C2 charger: CHG_INHIBIT open drain, LOW = stop).
 * The driver now follows amendment E1; the check below is the MET form of
 * the same comparison, and tests/test_drv_power.c exercises the behaviour:
 * the pin is driven push-pull HIGH to stop and is analog otherwise.
 */
GL_TEST(test_charger_of_the_pin_map_is_the_drivers)
{
    printf("    pin map: CHG_INHIBIT active %s, charger status %s = charging; drivers/power.c: "
           "CHG_INHIBIT active %s, charger %s a temperature input of its own\n",
           GL_PINS_CHG_INHIBIT_ACTIVE_HIGH ? "HIGH" : "LOW",
           GL_PINS_CHG_STAT_LOW_IS_CHARGING ? "LOW" : "HIGH",
           GL_POWER_CHG_INHIBIT_ACTIVE_HIGH ? "HIGH" : "LOW",
           GL_POWER_CHARGER_HAS_NTC_INPUT ? "with" : "without");
    GL_CHECK_EQ(GL_PINS_CHG_INHIBIT_ACTIVE_HIGH, 1);
    GL_CHECK_EQ(GL_PINS_CHG_STAT_LOW_IS_CHARGING, 1);
    GL_CHECK_EQ(GL_POWER_CHG_INHIBIT_ACTIVE_HIGH, GL_PINS_CHG_INHIBIT_ACTIVE_HIGH);
    GL_CHECK_EQ(GL_POWER_CHARGER_HAS_NTC_INPUT, 1);
    GL_CHECK_EQ(GL_PROV_BQ25101_TS_LOW_DISABLES, 1); /* what makes HIGH = stop */
    /* the signals of the old circuit are gone from the pin map */
    GL_CHECK(json_len_ != 0u && jfind_("CHG_PROG_EN") == NULL);
    /* both thermistor pins of the MCU: the bias a plain output that rests
     * analog, the sense an ADC input, next to nothing else */
    GL_CHECK_EQ(find_(GL_PIN_NTC_BIAS)->fn, GL_PINFN_GPIO);
    GL_CHECK_EQ(find_(GL_PIN_NTC_BIAS)->sleep, GL_PINSLEEP_ANALOG);
    GL_CHECK_EQ(find_(GL_PIN_NTC_BIAS)->board, GL_PINBRD_NONE);
    GL_CHECK_EQ(find_(GL_PIN_NTC_SENSE)->fn, GL_PINFN_ANALOG);
    GL_CHECK_EQ(find_(GL_PIN_VBUS_SENSE)->board, GL_PINBRD_DIVIDER);
}

/* The grain LEDs as the netlist wires them against the table the driver
 * lights them by: LED k of the firmware (0..7 red, 8..15 NIR, pair k % 8 at
 * azimuth 22.5 + 45 k degrees) must be the netlist's LED at that azimuth and
 * of that colour, anode and cathode on the same charlieplex lines. */
GL_TEST(test_grain_leds_of_the_netlist_are_the_drivers)
{
    typedef struct {
        int index;
        const char *ref;
        int red;
        int az10;
        int anode, cathode;
    } led_row_t;
#define LROW(index, ref, red, az10, anode, cathode) { index, #ref, red, az10, anode, cathode },
    static const led_row_t leds[] = { GL_PINS_GRAIN_LED_TABLE(LROW) };
#undef LROW
    unsigned matched = 0;
    GL_CHECK_EQ(GL_ARRAY_LEN(leds), GL_GRAIN_LEDS);
    for (unsigned led = 0; led < GL_GRAIN_LEDS; led++) {
        const int want_az10 = 225 + 450 * (int)(led % 8u);
        const int want_red = (led < 8u) ? 1 : 0;
        uint8_t anode = 255, cathode = 255;
        bool found = false;
        gl_grain_fe_led_pins(led, &anode, &cathode);
        for (size_t i = 0; i < GL_ARRAY_LEN(leds); i++) {
            if (leds[i].az10 == want_az10 && leds[i].red == want_red) {
                GL_CHECK(!found); /* one LED of each colour per azimuth */
                found = true;
                GL_CHECK_EQ(leds[i].anode, (int)anode);
                GL_CHECK_EQ(leds[i].cathode, (int)cathode);
                matched += (leds[i].anode == (int)anode && leds[i].cathode == (int)cathode) ? 1u : 0u;
            }
        }
        GL_CHECK(found);
    }
    /* the five lines are plain outputs behind their series resistors, on
     * ordinary pads (not a CC pad: checked above) */
    for (int p = (int)GL_PIN_GRAIN_CP0; p <= (int)GL_PIN_GRAIN_CP4; p++) {
        GL_CHECK_EQ(find_((gl_pin_t)p)->fn, GL_PINFN_GPIO);
        GL_CHECK_EQ(find_((gl_pin_t)p)->board, GL_PINBRD_SERIES);
        GL_CHECK_EQ(find_((gl_pin_t)p)->sleep, GL_PINSLEEP_ANALOG);
    }
    printf("    %u of 16 grain LEDs: the netlist's anode and cathode lines are the driver's\n", matched);
}

/* The table as generated, for the record (README, hand-over). */
GL_TEST(test_print_the_generated_table)
{
    static const char *const fn[] = { "OUT_PP", "AF", "ANALOG", "SCCB_OD", "EXTI" };
    static const char *const pull[] = { "-", "up", "down" };
    static const char *const brd[] = { "-", "to GND", "to V2V8", "to V2V8_CAM", "series", "VBUS divider" };
    static const char *const sleep[] = { "analog", "input", "low", "high", "analog/low" };
    static const char *const src[] = { "SPEC", "PROPOSED", "CHANGED" };
    printf("    %-13s %-5s %-3s %-8s %-3s %-5s %-13s %-5s %-9s %-10s %s\n", "signal", "pin", "pad", "mode",
           "AF", "pull", "board", "EXTI", "rail off", "asleep", "source");
    for (size_t i = 0; i < GL_ARRAY_LEN(rows_); i++) {
        const pin_row_t *r = &rows_[i];
        char pp[8], af[8], ex[8];
        snprintf(pp, sizeof(pp), "P%c%d", r->port, r->pin);
        snprintf(af, sizeof(af), (r->fn == GL_PINFN_AF) ? "%d" : "-", r->af);
        snprintf(ex, sizeof(ex), (r->exti != GL_PINS_NO_EXTI) ? "%d" : "-", r->exti);
        printf("    %-13s %-5s %-3d %-8s %-3s %-5s %-13s %-5s %-9s %-10s %s\n", r->name + 7, pp, r->pad,
               fn[r->fn], af, pull[r->pull], brd[r->board], ex,
               (r->rail == GL_PINRAIL_PARKED) ? "parked" : "-", sleep[r->sleep], src[r->src]);
        GL_CHECK(r->fn >= 0 && r->fn <= 4 && r->board >= 0 && r->board <= 5);
    }
}

int main(int argc, char **argv)
{
    if (argc > 1) {
        json_path_ = argv[1];
    }
    GL_RUN(test_table_matches_the_logical_pins);
    GL_RUN(test_every_row_equals_the_netlists_pin_map);
    GL_RUN(test_no_pad_or_port_pin_used_twice);
    GL_RUN(test_design_spec_rows);
    GL_RUN(test_function_kinds_and_analog_channels);
    GL_RUN(test_rom_bootloader_pins);
    GL_RUN(test_usb_type_c_cc_pads);
    GL_RUN(test_boot0_reset_levels_and_floating_lines);
    GL_RUN(test_constants_carried_by_the_pin_map);
    GL_RUN(test_imu_mounting_is_the_pin_maps);
    GL_RUN(test_charger_of_the_pin_map_is_the_drivers);
    GL_RUN(test_grain_leds_of_the_netlist_are_the_drivers);
    GL_RUN(test_print_the_generated_table);
    return gl_test_summary();
}
