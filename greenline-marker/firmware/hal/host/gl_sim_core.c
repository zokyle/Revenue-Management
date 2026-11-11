/*
 * gl_sim_core.c - host simulator backend of hal/gl_hal.h: time, trace,
 * GPIO, interrupts, sleep, SPI routing, analog, USB and the board rules.
 * See gl_sim.h for what is modelled and what is checked.
 */
#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#include "gl_sim_internal.h"

/* ---- board constants of the model --------------------------------------------- */

#define SIM_WDG_PERIOD_US (32u * 1000000ull) /* independent watchdog period */
#define SIM_RAIL_RISE_US 1000u               /* pins must stay parked this long after EN */
#define SIM_BYTE_LOG_MAX (4u * 1024u * 1024u)
#define SIM_SCHED_MAX 64
#define SIM_TIA_TAU_US 50.0f                 /* photodiode stage settling */
#define SIM_OPAMP_WAKE_US 1000u
#define SIM_USB_PIPE 65536u

/* Grain LED netlist OF THE MODEL (anode pin, cathode pin as charlieplex pin
 * numbers 0..4).  Pair k = 0..7 on the pin pairs below; red LED k conducts
 * from the lower pin to the higher, NIR LED 8 + k the other way. */
static const uint8_t grain_pair_[8][2] = {
    { 0, 1 }, { 0, 2 }, { 0, 3 }, { 0, 4 }, { 1, 2 }, { 1, 3 }, { 1, 4 }, { 2, 3 }
};

typedef struct {
    uint8_t mode;
    bool latch;
    bool ext; /* level applied from outside while the pin is an input */
} sim_pin_t;

typedef struct {
    uint64_t t_us;
    gl_sim_fn_t fn;
    void *arg;
    uint32_t order;
    bool used;
} sim_sched_t;

static struct {
    uint64_t now_us;
    bool inited;
    /* trace */
    size_t n_trace, lost_trace;
    size_t n_bytes;
    /* pins */
    sim_pin_t pin[GL_PIN_COUNT];
    bool rail_on;
    uint64_t rail_on_since;
    /* irq */
    uint32_t irq_enabled, irq_pending;
    int irq_lock;
    uint64_t wake_timer_at;
    /* scheduled calls */
    sim_sched_t sched[SIM_SCHED_MAX];
    uint32_t sched_order;
    /* spi */
    gl_spi_cfg_t spi_cfg[GL_SPI_BUS_COUNT];
    bool spi_cfg_valid[GL_SPI_BUS_COUNT];
    /* analog */
    bool adc_on, opamp_on;
    uint64_t opamp_on_at;
    uint16_t vbat_mv, vdda_mv;
    gl_sim_grain_t grain;
    float tia_level;        /* settled-so-far photodiode stage output, counts */
    uint64_t tia_t;         /* time tia_level refers to */
    /* lcd timer / clock */
    bool extcomin_on;
    /* usb */
    bool usb_started, usb_host_open;
    uint8_t usb_rx[SIM_USB_PIPE];
    size_t usb_rx_len;
    uint8_t usb_tx[SIM_USB_PIPE];
    size_t usb_tx_len;
    size_t usb_tx_chunk;
    /* system */
    uint32_t reset_reason;
    uint32_t rtc_base_s;
    uint64_t rtc_set_at_us;
    uint64_t wdg_last_kick;
    uint32_t rng;
    gl_sim_violations_t viol;
    gl_sim_stats_t stats;
} S;

static gl_sim_trace_t trace_[GL_SIM_TRACE_MAX];
static uint8_t byte_log_[SIM_BYTE_LOG_MAX];

/* ======================================================================= */
/* services                                                                 */
/* ======================================================================= */

uint64_t sim_now(void)
{
    return S.now_us;
}

gl_sim_violations_t *sim_viol(void)
{
    return &S.viol;
}

gl_sim_stats_t *sim_stat(void)
{
    return &S.stats;
}

void sim_trace(gl_sim_tr_type_t type, unsigned a, unsigned b, uint32_t c, uint32_t d)
{
    if (S.n_trace >= GL_SIM_TRACE_MAX) {
        S.lost_trace++;
        return;
    }
    gl_sim_trace_t *t = &trace_[S.n_trace++];
    t->t_us = S.now_us;
    t->type = (uint8_t)type;
    t->a = (uint8_t)a;
    t->b = (uint16_t)b;
    t->c = c;
    t->d = d;
}

void sim_violation(unsigned *counter, const char *fmt, ...)
{
    (*counter)++;
    if (S.viol.first[0] == '\0') {
        char msg[120];
        va_list ap;
        va_start(ap, fmt);
        vsnprintf(msg, sizeof(msg), fmt, ap);
        va_end(ap);
        snprintf(S.viol.first, sizeof(S.viol.first), "t=%.3f ms: %s", (double)S.now_us / 1000.0,
                 msg);
    }
}

uint32_t sim_rand_u32(void)
{
    /* xorshift32 */
    uint32_t x = S.rng;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    S.rng = x;
    return x;
}

static float u32_to_unit_(uint32_t x)
{
    /* (0, 1) */
    return ((float)(x >> 8) + 0.5f) * (1.0f / 16777216.0f);
}

float sim_rand_normal(void)
{
    float u1 = u32_to_unit_(sim_rand_u32());
    float u2 = u32_to_unit_(sim_rand_u32());
    return sqrtf(-2.0f * logf(u1)) * cosf(6.2831853f * u2);
}

static uint32_t mix32_(uint64_t z)
{
    /* splitmix64 finaliser */
    z += 0x9E3779B97F4A7C15ull;
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ull;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBull;
    z ^= z >> 31;
    return (uint32_t)(z >> 16);
}

float sim_hash_normal(uint32_t stream, uint64_t index)
{
    uint64_t key = ((uint64_t)stream << 48) ^ index;
    float u1 = u32_to_unit_(mix32_(key));
    float u2 = u32_to_unit_(mix32_(key ^ 0xA5A5A5A5DEADBEEFull));
    return sqrtf(-2.0f * logf(u1)) * cosf(6.2831853f * u2);
}

void sim_irq_raise(uint32_t mask)
{
    S.irq_pending |= mask & S.irq_enabled;
}

bool sim_pin_out_high(gl_pin_t pin)
{
    const sim_pin_t *p = &S.pin[pin];
    return p->mode == (uint8_t)GL_PIN_MODE_OUTPUT_PP && p->latch;
}

bool sim_pin_out_low(gl_pin_t pin)
{
    const sim_pin_t *p = &S.pin[pin];
    return (p->mode == (uint8_t)GL_PIN_MODE_OUTPUT_PP || p->mode == (uint8_t)GL_PIN_MODE_OUTPUT_OD) &&
           !p->latch;
}

bool sim_pin_is_alt(gl_pin_t pin)
{
    return S.pin[pin].mode == (uint8_t)GL_PIN_MODE_ALTERNATE;
}

/* ======================================================================= */
/* board rules evaluated on every pin change                                */
/* ======================================================================= */

static bool pin_parked_(gl_pin_t pin)
{
    return S.pin[pin].mode == (uint8_t)GL_PIN_MODE_ANALOG || sim_pin_out_low(pin);
}

static void check_cam_rail_(const char *what)
{
    bool settled = S.rail_on && (S.now_us - S.rail_on_since) >= SIM_RAIL_RISE_US;
    if (settled) {
        return;
    }
    for (int p = (int)GL_PIN_CAM_FACING_FIRST; p <= (int)GL_PIN_CAM_FACING_LAST; p++) {
        if (!pin_parked_((gl_pin_t)p)) {
            sim_violation(&S.viol.cam_rail, "camera-facing pin %d not parked (mode %d, latch %d) %s, %s",
                          p, (int)S.pin[p].mode, (int)S.pin[p].latch,
                          S.rail_on ? "before the rail has settled" : "while the rail is off", what);
            return; /* one count per offending change */
        }
    }
}

static void update_rail_(void)
{
    bool on = sim_pin_out_high(GL_PIN_CAM_PWR_EN);
    if (on && !S.rail_on) {
        S.rail_on = true;
        S.rail_on_since = S.now_us;
        S.stats.cam_rail_cycles++;
    } else if (!on && S.rail_on) {
        S.stats.cam_rail_on_us += S.now_us - S.rail_on_since;
        S.rail_on = false;
    }
}

static void spi_cs_edges_(gl_pin_t pin, bool was_asserted)
{
    bool now_asserted;
    switch (pin) {
    case GL_PIN_LCD_SCS:
        now_asserted = sim_pin_out_high(pin);
        if (now_asserted != was_asserted) {
            sim_lcd_cs(now_asserted);
        }
        break;
    case GL_PIN_FLASH_CS:
        now_asserted = sim_pin_out_low(pin);
        if (now_asserted != was_asserted) {
            sim_flash_cs(now_asserted);
        }
        break;
    case GL_PIN_IMU_CS:
        now_asserted = sim_pin_out_low(pin);
        if (now_asserted != was_asserted) {
            sim_imu_cs(now_asserted);
        }
        break;
    default:
        break;
    }
}

static bool cs_asserted_(gl_pin_t pin)
{
    return (pin == GL_PIN_LCD_SCS) ? sim_pin_out_high(pin) : sim_pin_out_low(pin);
}

static void pin_changed_(gl_pin_t pin, bool cs_before, bool disp_before, const char *what)
{
    if (pin == GL_PIN_CAM_PWR_EN) {
        update_rail_();
    }
    if (pin <= GL_PIN_CAM_VSYNC) {
        check_cam_rail_(what);
        sim_cam_update();
    }
    if (pin == GL_PIN_LCD_SCS || pin == GL_PIN_FLASH_CS || pin == GL_PIN_IMU_CS) {
        spi_cs_edges_(pin, cs_before);
    }
    if (pin == GL_PIN_LCD_DISP) {
        bool disp = sim_pin_out_high(pin);
        if (disp != disp_before) {
            sim_lcd_disp(disp);
        }
    }
    if (pin >= GL_PIN_GRAIN_CP0 && pin <= GL_PIN_GRAIN_CP4) {
        uint32_t lit = gl_sim_grain_lit_mask();
        if ((lit & (lit - 1u)) != 0u) {
            sim_violation(&S.viol.analog, "several grain LEDs lit at once (mask 0x%04x)",
                          (unsigned)lit);
        }
    }
}

/* ======================================================================= */
/* time engine                                                              */
/* ======================================================================= */

static uint64_t sched_next_(int *slot)
{
    uint64_t best = SIM_NEVER;
    uint32_t best_order = 0;
    *slot = -1;
    for (int i = 0; i < SIM_SCHED_MAX; i++) {
        if (S.sched[i].used &&
            (S.sched[i].t_us < best || (S.sched[i].t_us == best && S.sched[i].order < best_order))) {
            best = S.sched[i].t_us;
            best_order = S.sched[i].order;
            *slot = i;
        }
    }
    return best;
}

static uint64_t next_event_(void)
{
    int slot;
    uint64_t t = sched_next_(&slot);
    uint64_t u = S.wake_timer_at;
    if (u < t) {
        t = u;
    }
    u = sim_imu_next_event();
    if (u < t) {
        t = u;
    }
    u = sim_cam_next_event();
    if (u < t) {
        t = u;
    }
    return t;
}

static void tia_settle_to_now_(void);

static void watchdog_check_(void)
{
    if (S.inited && S.now_us - S.wdg_last_kick > SIM_WDG_PERIOD_US) {
        sim_violation(&S.viol.watchdog, "watchdog not kicked for %.1f s",
                      (double)(S.now_us - S.wdg_last_kick) / 1e6);
        S.wdg_last_kick = S.now_us;
    }
}

/* Process every event up to and including t_target, then set the clock. */
static void run_until_(uint64_t t_target)
{
    for (;;) {
        uint64_t t = next_event_();
        if (t > t_target) {
            break;
        }
        if (t > S.now_us) {
            S.now_us = t;
            watchdog_check_();
        }
        /* fire everything due at this instant, one source at a time */
        int slot;
        if (sched_next_(&slot) <= S.now_us && slot >= 0) {
            gl_sim_fn_t fn = S.sched[slot].fn;
            void *arg = S.sched[slot].arg;
            S.sched[slot].used = false;
            fn(arg);
            continue;
        }
        if (S.wake_timer_at <= S.now_us) {
            S.wake_timer_at = SIM_NEVER;
            sim_irq_raise(GL_IRQ_WAKE_TIMER);
            continue;
        }
        if (sim_imu_next_event() <= S.now_us) {
            sim_imu_fire(S.now_us);
            continue;
        }
        if (sim_cam_next_event() <= S.now_us) {
            sim_cam_fire(S.now_us);
            continue;
        }
    }
    if (t_target > S.now_us) {
        S.now_us = t_target;
        watchdog_check_();
    }
}

/* ======================================================================= */
/* simulator control (gl_sim.h)                                             */
/* ======================================================================= */

void gl_sim_reset(bool erase_flash)
{
    memset(&S, 0, sizeof(S));
    S.wake_timer_at = SIM_NEVER;
    S.rng = 0x1234ABCDu;
    S.vbat_mv = 3900;
    S.vdda_mv = 2800;
    S.reset_reason = GL_RESET_POWER_ON;
    S.grain.dark_counts = 8192.0f;
    S.tia_level = 0.0f;
    for (int p = 0; p < (int)GL_PIN_COUNT; p++) {
        S.pin[p].mode = (uint8_t)GL_PIN_MODE_ANALOG; /* MCU reset state */
    }
    S.pin[GL_PIN_CHG_STAT].ext = true; /* pulled up: not charging */
    sim_lcd_reset();
    sim_flash_reset(erase_flash);
    sim_imu_reset();
    sim_cam_reset();
}

uint64_t gl_sim_now_us(void)
{
    return S.now_us;
}

void gl_sim_advance_ms(uint32_t ms)
{
    run_until_(S.now_us + (uint64_t)ms * 1000u);
}

bool gl_sim_at_ms(uint32_t t_ms, gl_sim_fn_t fn, void *arg)
{
    for (int i = 0; i < SIM_SCHED_MAX; i++) {
        if (!S.sched[i].used) {
            S.sched[i].used = true;
            S.sched[i].t_us = (uint64_t)t_ms * 1000u;
            S.sched[i].fn = fn;
            S.sched[i].arg = arg;
            S.sched[i].order = S.sched_order++;
            return true;
        }
    }
    return false;
}

size_t gl_sim_trace_count(void)
{
    return S.n_trace;
}

size_t gl_sim_trace_lost(void)
{
    return S.lost_trace;
}

const gl_sim_trace_t *gl_sim_trace_at(size_t index)
{
    return (index < S.n_trace) ? &trace_[index] : NULL;
}

void gl_sim_trace_clear(void)
{
    S.n_trace = 0;
    S.lost_trace = 0;
    S.n_bytes = 0;
}

const uint8_t *gl_sim_trace_bytes(const gl_sim_trace_t *xfer)
{
    if (xfer == NULL || xfer->type != (uint8_t)GL_SIM_TR_SPI_XFER || xfer->d == UINT32_MAX) {
        return NULL;
    }
    return &byte_log_[xfer->d];
}

gl_pin_mode_t gl_sim_pin_mode(gl_pin_t pin)
{
    return (gl_pin_mode_t)S.pin[pin].mode;
}

bool gl_sim_pin_latch(gl_pin_t pin)
{
    return S.pin[pin].latch;
}

bool gl_sim_pin_drives_high(gl_pin_t pin)
{
    return sim_pin_out_high(pin);
}

bool gl_sim_pin_drives_low(gl_pin_t pin)
{
    return sim_pin_out_low(pin);
}

void sim_set_input(gl_pin_t pin, bool level)
{
    bool before = S.pin[pin].ext;
    S.pin[pin].ext = level;
    if (before == level) {
        return;
    }
    switch (pin) {
    case GL_PIN_IMU_INT1:
        if (level) {
            sim_irq_raise(GL_IRQ_IMU_INT1);
        }
        break;
    case GL_PIN_IMU_INT2:
        if (level) {
            sim_irq_raise(GL_IRQ_IMU_INT2);
        }
        break;
    case GL_PIN_VBUS_SENSE:
        sim_irq_raise(GL_IRQ_VBUS_CHANGE);
        break;
    case GL_PIN_CHG_STAT:
        sim_irq_raise(GL_IRQ_CHG_STAT);
        break;
    default:
        break;
    }
}

void gl_sim_set_input(gl_pin_t pin, bool level)
{
    sim_set_input(pin, level);
}

const gl_sim_violations_t *gl_sim_violations(void)
{
    return &S.viol;
}

unsigned gl_sim_violation_total(void)
{
    const gl_sim_violations_t *v = &S.viol;
    return v->cam_rail + v->cam_contention + v->cam_sccb + v->dcmi + v->lcd + v->flash + v->imu +
           v->spi + v->stop_mode + v->analog + v->watchdog + v->deadlock;
}

const gl_sim_stats_t *gl_sim_stats(void)
{
    static gl_sim_stats_t snapshot;
    snapshot = S.stats;
    if (S.rail_on) {
        snapshot.cam_rail_on_us += S.now_us - S.rail_on_since;
    }
    return &snapshot;
}

bool gl_sim_cam_rail_on(void)
{
    return S.rail_on;
}

void gl_sim_set_vbat_mv(uint16_t mv)
{
    S.vbat_mv = mv;
}

void gl_sim_set_vdda_mv(uint16_t mv)
{
    S.vdda_mv = mv;
}

void gl_sim_grain_set(const gl_sim_grain_t *g)
{
    tia_settle_to_now_();
    S.grain = *g;
}

uint32_t gl_sim_grain_lit_mask(void)
{
    uint32_t mask = 0;
    for (unsigned k = 0; k < 8u; k++) {
        gl_pin_t lo = (gl_pin_t)((int)GL_PIN_GRAIN_CP0 + grain_pair_[k][0]);
        gl_pin_t hi = (gl_pin_t)((int)GL_PIN_GRAIN_CP0 + grain_pair_[k][1]);
        if (sim_pin_out_high(lo) && S.pin[hi].mode == (uint8_t)GL_PIN_MODE_OUTPUT_PP &&
            !S.pin[hi].latch) {
            mask |= 1u << k; /* red: low pin -> high pin */
        }
        if (sim_pin_out_high(hi) && S.pin[lo].mode == (uint8_t)GL_PIN_MODE_OUTPUT_PP &&
            !S.pin[lo].latch) {
            mask |= 1u << (8u + k); /* NIR: high pin -> low pin */
        }
    }
    return mask;
}

void gl_sim_usb_host_open(bool open)
{
    S.usb_host_open = open;
}

void gl_sim_usb_host_send(const uint8_t *data, size_t len)
{
    if (!S.usb_started) {
        return;
    }
    if (len > SIM_USB_PIPE - S.usb_rx_len) {
        len = SIM_USB_PIPE - S.usb_rx_len;
    }
    memcpy(&S.usb_rx[S.usb_rx_len], data, len);
    S.usb_rx_len += len;
    if (len > 0u) {
        sim_irq_raise(GL_IRQ_USB_RX);
    }
}

size_t gl_sim_usb_host_recv(uint8_t *buf, size_t max)
{
    size_t n = (S.usb_tx_len < max) ? S.usb_tx_len : max;
    memcpy(buf, S.usb_tx, n);
    memmove(S.usb_tx, &S.usb_tx[n], S.usb_tx_len - n);
    S.usb_tx_len -= n;
    return n;
}

void gl_sim_usb_set_tx_chunk(size_t max)
{
    S.usb_tx_chunk = max;
}

void gl_sim_set_reset_reason(uint32_t flags)
{
    S.reset_reason = flags;
}

void gl_sim_set_rtc(uint32_t seconds)
{
    S.rtc_base_s = seconds;
    S.rtc_set_at_us = S.now_us;
}

/* ======================================================================= */
/* gl_hal.h: system and time                                                */
/* ======================================================================= */

gl_status_t gl_hal_init(void)
{
    static const gl_pin_t alt[] = { GL_PIN_SPI1_SCK, GL_PIN_SPI1_MOSI, GL_PIN_SPI1_MISO,
                                    GL_PIN_SPI2_SCK, GL_PIN_SPI2_MOSI, GL_PIN_SPI2_MISO };
    for (int p = 0; p < (int)GL_PIN_COUNT; p++) {
        S.pin[p].mode = (uint8_t)GL_PIN_MODE_ANALOG;
        S.pin[p].latch = false;
    }
    update_rail_();
    gl_hal_gpio_write(GL_PIN_CAM_PWR_EN, false);
    gl_hal_gpio_mode(GL_PIN_CAM_PWR_EN, GL_PIN_MODE_OUTPUT_PP);
    gl_hal_gpio_write(GL_PIN_LCD_SCS, false);
    gl_hal_gpio_mode(GL_PIN_LCD_SCS, GL_PIN_MODE_OUTPUT_PP);
    gl_hal_gpio_write(GL_PIN_LCD_DISP, false);
    gl_hal_gpio_mode(GL_PIN_LCD_DISP, GL_PIN_MODE_OUTPUT_PP);
    gl_hal_gpio_write(GL_PIN_LCD_EXTCOMIN, false);
    gl_hal_gpio_mode(GL_PIN_LCD_EXTCOMIN, GL_PIN_MODE_OUTPUT_PP);
    gl_hal_gpio_write(GL_PIN_FLASH_CS, true);
    gl_hal_gpio_mode(GL_PIN_FLASH_CS, GL_PIN_MODE_OUTPUT_PP);
    gl_hal_gpio_write(GL_PIN_IMU_CS, true);
    gl_hal_gpio_mode(GL_PIN_IMU_CS, GL_PIN_MODE_OUTPUT_PP);
    gl_hal_gpio_write(GL_PIN_CHG_PROG_EN, true); /* released: charging stopped */
    gl_hal_gpio_mode(GL_PIN_CHG_PROG_EN, GL_PIN_MODE_OUTPUT_OD);
    gl_hal_gpio_mode(GL_PIN_CHG_STAT, GL_PIN_MODE_INPUT_PULLUP);
    gl_hal_gpio_mode(GL_PIN_VBUS_SENSE, GL_PIN_MODE_INPUT);
    gl_hal_gpio_mode(GL_PIN_IMU_INT1, GL_PIN_MODE_INPUT);
    gl_hal_gpio_mode(GL_PIN_IMU_INT2, GL_PIN_MODE_INPUT);
    for (size_t i = 0; i < sizeof(alt) / sizeof(alt[0]); i++) {
        gl_hal_gpio_mode(alt[i], GL_PIN_MODE_ALTERNATE);
    }
    S.irq_enabled = 0;
    S.irq_pending = 0;
    S.inited = true;
    S.wdg_last_kick = S.now_us;
    return GL_OK;
}

uint32_t gl_hal_reset_reason(void)
{
    uint32_t r = S.reset_reason;
    S.reset_reason = 0;
    return r;
}

void gl_hal_reboot(gl_reboot_t how)
{
    S.stats.reboots++;
    S.stats.last_reboot = (uint8_t)how;
    sim_trace(GL_SIM_TR_REBOOT, (unsigned)how, 0, 0, 0);
}

void gl_hal_watchdog_kick(void)
{
    S.wdg_last_kick = S.now_us;
    S.stats.watchdog_kicks++;
}

void gl_hal_unique_id(uint8_t out[12])
{
    for (unsigned i = 0; i < 12u; i++) {
        out[i] = (uint8_t)(0xA0u + i);
    }
}

uint32_t gl_hal_tick_ms(void)
{
    return (uint32_t)(S.now_us / 1000u);
}

void gl_hal_delay_ms(uint32_t ms)
{
    run_until_(S.now_us + (uint64_t)ms * 1000u);
}

void gl_hal_delay_us(uint32_t us)
{
    run_until_(S.now_us + us);
}

uint32_t gl_hal_rtc_seconds(void)
{
    if (S.rtc_base_s == 0u) {
        return 0;
    }
    return S.rtc_base_s + (uint32_t)((S.now_us - S.rtc_set_at_us) / 1000000u);
}

void gl_hal_rtc_set_seconds(uint32_t seconds)
{
    gl_sim_set_rtc(seconds);
}

/* ======================================================================= */
/* gl_hal.h: GPIO                                                           */
/* ======================================================================= */

void gl_hal_gpio_mode(gl_pin_t pin, gl_pin_mode_t mode)
{
    if ((unsigned)pin >= (unsigned)GL_PIN_COUNT) {
        return;
    }
    bool cs_before = cs_asserted_(pin);
    bool disp_before = sim_pin_out_high(GL_PIN_LCD_DISP);
    tia_settle_to_now_();
    S.pin[pin].mode = (uint8_t)mode;
    sim_trace(GL_SIM_TR_GPIO_MODE, (unsigned)pin, (unsigned)mode, 0, 0);
    pin_changed_(pin, cs_before, disp_before, "on a mode change");
}

void gl_hal_gpio_write(gl_pin_t pin, bool high)
{
    if ((unsigned)pin >= (unsigned)GL_PIN_COUNT) {
        return;
    }
    bool cs_before = cs_asserted_(pin);
    bool disp_before = sim_pin_out_high(GL_PIN_LCD_DISP);
    tia_settle_to_now_();
    S.pin[pin].latch = high;
    sim_trace(GL_SIM_TR_GPIO_WRITE, (unsigned)pin, high ? 1u : 0u, 0, 0);
    pin_changed_(pin, cs_before, disp_before, "on a write");
}

bool gl_hal_gpio_read(gl_pin_t pin)
{
    if ((unsigned)pin >= (unsigned)GL_PIN_COUNT) {
        return false;
    }
    const sim_pin_t *p = &S.pin[pin];
    switch ((gl_pin_mode_t)p->mode) {
    case GL_PIN_MODE_OUTPUT_PP:
        return p->latch;
    case GL_PIN_MODE_OUTPUT_OD:
        return p->latch ? p->ext : false;
    case GL_PIN_MODE_INPUT:
    case GL_PIN_MODE_INPUT_PULLUP:
    case GL_PIN_MODE_INPUT_PULLDOWN:
        return p->ext;
    default:
        return false;
    }
}

/* ======================================================================= */
/* gl_hal.h: interrupts and sleep                                           */
/* ======================================================================= */

void gl_hal_irq_enable(uint32_t mask, bool enable)
{
    if (enable) {
        S.irq_enabled |= mask;
        /* data already waiting counts as pending */
        if ((mask & GL_IRQ_USB_RX) != 0u && S.usb_rx_len > 0u) {
            S.irq_pending |= GL_IRQ_USB_RX;
        }
    } else {
        S.irq_enabled &= ~mask;
        S.irq_pending &= ~mask;
    }
    sim_trace(GL_SIM_TR_IRQ_ENABLE, enable ? 1u : 0u, 0, mask, 0);
}

uint32_t gl_hal_irq_take(void)
{
    uint32_t p = S.irq_pending;
    S.irq_pending = 0;
    return p;
}

void gl_hal_irq_lock(void)
{
    S.irq_lock++;
}

void gl_hal_irq_unlock(void)
{
    if (S.irq_lock > 0) {
        S.irq_lock--;
    }
}

void gl_hal_wake_timer_start(uint32_t ms)
{
    S.wake_timer_at = (ms == 0u) ? SIM_NEVER : S.now_us + (uint64_t)ms * 1000u;
    if (ms == 0u) {
        S.irq_pending &= ~GL_IRQ_WAKE_TIMER;
    }
}

#define SIM_STOP_WAKE_MASK \
    (GL_IRQ_IMU_INT1 | GL_IRQ_IMU_INT2 | GL_IRQ_VBUS_CHANGE | GL_IRQ_CHG_STAT | GL_IRQ_WAKE_TIMER)

uint32_t gl_hal_sleep(gl_sleep_mode_t mode)
{
    uint64_t t0 = S.now_us;
    uint32_t wake_mask = (mode == GL_SLEEP_STOP) ? SIM_STOP_WAKE_MASK : 0xFFFFFFFFu;

    if (mode == GL_SLEEP_STOP) {
        if (S.rail_on) {
            sim_violation(&S.viol.stop_mode, "Stop mode with the camera rail on");
        }
        if (sim_cam_capture_busy()) {
            sim_violation(&S.viol.stop_mode, "Stop mode during a DCMI capture");
        }
        if (S.usb_started) {
            sim_violation(&S.viol.stop_mode, "Stop mode with USB started");
        }
        if (S.adc_on || S.opamp_on) {
            sim_violation(&S.viol.stop_mode, "Stop mode with the ADC or the op-amp powered");
        }
        if (cs_asserted_(GL_PIN_LCD_SCS) || cs_asserted_(GL_PIN_FLASH_CS) ||
            cs_asserted_(GL_PIN_IMU_CS)) {
            sim_violation(&S.viol.stop_mode, "Stop mode with a chip select asserted");
        }
    }
    while ((S.irq_pending & wake_mask) == 0u) {
        uint64_t t = next_event_();
        if (t == SIM_NEVER) {
            sim_violation(&S.viol.deadlock, "gl_hal_sleep(%d) with no event that could wake it",
                          (int)mode);
            break;
        }
        run_until_(t);
    }
    if (mode == GL_SLEEP_STOP) {
        S.stats.stop_us += S.now_us - t0;
    } else {
        S.stats.idle_us += S.now_us - t0;
    }
    sim_trace(GL_SIM_TR_SLEEP, (unsigned)mode, 0, (uint32_t)(S.now_us - t0), 0);
    return S.irq_pending;
}

/* ======================================================================= */
/* gl_hal.h: SPI                                                            */
/* ======================================================================= */

gl_status_t gl_hal_spi_configure(gl_spi_bus_t bus, const gl_spi_cfg_t *cfg)
{
    if ((unsigned)bus >= (unsigned)GL_SPI_BUS_COUNT || cfg == NULL || cfg->mode > 3u ||
        cfg->max_hz == 0u) {
        return GL_ERR_PARAM;
    }
    S.spi_cfg[bus] = *cfg;
    S.spi_cfg_valid[bus] = true;
    sim_trace(GL_SIM_TR_SPI_CFG, (unsigned)bus, (unsigned)cfg->mode | (cfg->lsb_first ? 0x100u : 0u),
              cfg->max_hz, 0);
    return GL_OK;
}

gl_status_t gl_hal_spi_transfer(gl_spi_bus_t bus, const uint8_t *tx, uint8_t *rx, size_t len)
{
    static uint8_t ff[256];
    if ((unsigned)bus >= (unsigned)GL_SPI_BUS_COUNT) {
        return GL_ERR_PARAM;
    }
    if (!S.spi_cfg_valid[bus]) {
        sim_violation(&S.viol.spi, "SPI%d transfer before gl_hal_spi_configure", (int)bus + 1);
        return GL_ERR_STATE;
    }
    if (len == 0u) {
        return GL_OK;
    }
    const gl_pin_t sck = (bus == GL_SPI_BUS_1) ? GL_PIN_SPI1_SCK : GL_PIN_SPI2_SCK;
    const gl_pin_t mosi = (bus == GL_SPI_BUS_1) ? GL_PIN_SPI1_MOSI : GL_PIN_SPI2_MOSI;
    const gl_pin_t miso = (bus == GL_SPI_BUS_1) ? GL_PIN_SPI1_MISO : GL_PIN_SPI2_MISO;
    if (!sim_pin_is_alt(sck) || !sim_pin_is_alt(mosi) || !sim_pin_is_alt(miso)) {
        sim_violation(&S.viol.spi, "SPI%d transfer with bus pins not in ALTERNATE mode",
                      (int)bus + 1);
    }

    gl_sim_dev_t dev = GL_SIM_DEV_NONE;
    if (bus == GL_SPI_BUS_1) {
        bool lcd = cs_asserted_(GL_PIN_LCD_SCS);
        bool fl = cs_asserted_(GL_PIN_FLASH_CS);
        if (lcd && fl) {
            dev = GL_SIM_DEV_CONFLICT;
            sim_violation(&S.viol.spi, "LCD and flash selected together on SPI1");
        } else if (lcd) {
            dev = GL_SIM_DEV_LCD;
        } else if (fl) {
            dev = GL_SIM_DEV_FLASH;
        }
    } else if (cs_asserted_(GL_PIN_IMU_CS)) {
        dev = GL_SIM_DEV_IMU;
    }
    if (dev == GL_SIM_DEV_NONE) {
        sim_violation(&S.viol.spi, "SPI%d transfer of %u bytes with no device selected",
                      (int)bus + 1, (unsigned)len);
    }

    /* log the transmitted bytes */
    uint32_t off = UINT32_MAX;
    if (len <= SIM_BYTE_LOG_MAX - S.n_bytes) {
        off = (uint32_t)S.n_bytes;
        if (tx != NULL) {
            memcpy(&byte_log_[S.n_bytes], tx, len);
        } else {
            memset(&byte_log_[S.n_bytes], 0xFF, len);
        }
        S.n_bytes += len;
    }
    sim_trace(GL_SIM_TR_SPI_XFER, (unsigned)bus, (unsigned)dev, (uint32_t)len, off);

    if (rx != NULL) {
        memset(rx, 0xFF, len);
    }
    /* devices see 0xFF when the master sends nothing */
    size_t done = 0;
    while (done < len) {
        size_t n = len - done;
        const uint8_t *src;
        if (tx != NULL) {
            src = tx + done;
        } else {
            if (n > sizeof(ff)) {
                n = sizeof(ff);
            }
            memset(ff, 0xFF, n);
            src = ff;
        }
        uint8_t *dst = (rx != NULL) ? rx + done : NULL;
        switch (dev) {
        case GL_SIM_DEV_LCD:
            sim_lcd_xfer(&S.spi_cfg[bus], src, dst, n);
            break;
        case GL_SIM_DEV_FLASH:
            sim_flash_xfer(&S.spi_cfg[bus], src, dst, n);
            break;
        case GL_SIM_DEV_IMU:
            sim_imu_xfer(&S.spi_cfg[bus], src, dst, n);
            break;
        default:
            break;
        }
        done += n;
    }
    /* the clocks take time */
    run_until_(S.now_us + ((uint64_t)len * 8u * 1000000u + S.spi_cfg[bus].max_hz - 1u) /
                              S.spi_cfg[bus].max_hz);
    return GL_OK;
}

/* ======================================================================= */
/* gl_hal.h: ADC and op-amp                                                 */
/* ======================================================================= */

static float tia_target_(void)
{
    if (!S.opamp_on || S.now_us - S.opamp_on_at < SIM_OPAMP_WAKE_US) {
        return 0.0f;
    }
    float v = S.grain.dark_counts + S.grain.drift_counts_per_ms * ((float)S.now_us / 1000.0f);
    uint32_t lit = gl_sim_grain_lit_mask();
    for (unsigned k = 0; k < 16u; k++) {
        if ((lit & (1u << k)) != 0u) {
            v += S.grain.response[k];
        }
    }
    return v;
}

/* First-order settling of the photodiode stage: bring tia_level up to date
 * with the conditions that held since tia_t.  Called before any change of
 * those conditions and before a conversion. */
static void tia_settle_to_now_(void)
{
    float target = tia_target_();
    float dt = (float)(S.now_us - S.tia_t);
    if (dt > 0.0f) {
        float k = (dt > 20.0f * SIM_TIA_TAU_US) ? 0.0f : expf(-dt / SIM_TIA_TAU_US);
        S.tia_level = target + (S.tia_level - target) * k;
    }
    S.tia_t = S.now_us;
}

gl_status_t gl_hal_adc_power(bool on)
{
    S.adc_on = on;
    sim_trace(GL_SIM_TR_ADC_POWER, on ? 1u : 0u, 0, 0, 0);
    if (on) {
        run_until_(S.now_us + 200u); /* regulator start-up and calibration */
    }
    return GL_OK;
}

gl_status_t gl_hal_opamp_enable(bool on)
{
    tia_settle_to_now_();
    if (on && !S.opamp_on) {
        S.opamp_on_at = S.now_us;
    }
    S.opamp_on = on;
    sim_trace(GL_SIM_TR_OPAMP, on ? 1u : 0u, 0, 0, 0);
    return GL_OK;
}

gl_status_t gl_hal_adc_read(gl_adc_ch_t ch, uint16_t n_avg, uint16_t sample_time_us,
                            uint16_t *counts)
{
    if (counts == NULL || n_avg == 0u || n_avg > 256u || (unsigned)ch >= (unsigned)GL_ADC_CH_COUNT) {
        return GL_ERR_PARAM;
    }
    if (!S.adc_on) {
        sim_violation(&S.viol.analog, "ADC read (channel %d) while the ADC is powered down",
                      (int)ch);
        return GL_ERR_STATE;
    }
    float v = 0.0f;
    float noise = 1.0f;
    switch (ch) {
    case GL_ADC_CH_GRAIN_TIA:
        if (!S.opamp_on) {
            sim_violation(&S.viol.analog, "grain channel read with OPAMP1 off");
        }
        tia_settle_to_now_();
        v = S.tia_level;
        noise = S.grain.noise_counts;
        break;
    case GL_ADC_CH_VBAT_DIV:
        v = (float)S.vbat_mv * 0.5f / (float)S.vdda_mv * (float)GL_HAL_ADC_FULL_SCALE;
        break;
    case GL_ADC_CH_VREFINT:
        v = 1212.0f / (float)S.vdda_mv * (float)GL_HAL_ADC_FULL_SCALE;
        break;
    case GL_ADC_CH_MCU_TEMP:
    default:
        v = 4000.0f;
        break;
    }
    v += noise * sim_rand_normal() / sqrtf((float)n_avg);
    if (v < 0.0f) {
        v = 0.0f;
    }
    if (v > (float)GL_HAL_ADC_FULL_SCALE) {
        v = (float)GL_HAL_ADC_FULL_SCALE;
    }
    *counts = (uint16_t)(v + 0.5f);
    sim_trace(GL_SIM_TR_ADC_READ, (unsigned)ch, *counts, gl_sim_grain_lit_mask(), 0);
    run_until_(S.now_us + (uint64_t)n_avg * ((uint64_t)sample_time_us + 3u));
    return GL_OK;
}

uint16_t gl_hal_adc_vdda_mv(void)
{
    if (!S.adc_on) {
        sim_violation(&S.viol.analog, "VDDA measurement while the ADC is powered down");
        return 0;
    }
    return S.vdda_mv;
}

/* ======================================================================= */
/* gl_hal.h: LCD VCOM timer, camera clock                                   */
/* ======================================================================= */

gl_status_t gl_hal_extcomin_start(uint16_t period_lse_ticks)
{
    if (period_lse_ticks < 2u) {
        return GL_ERR_PARAM;
    }
    if (!sim_pin_is_alt(GL_PIN_LCD_EXTCOMIN)) {
        sim_violation(&S.viol.lcd, "EXTCOMIN timer started with its pin not in ALTERNATE mode");
    }
    S.extcomin_on = true;
    sim_trace(GL_SIM_TR_EXTCOMIN, 1, 0, period_lse_ticks, 0);
    sim_lcd_extcomin(true, period_lse_ticks);
    return GL_OK;
}

void gl_hal_extcomin_stop(void)
{
    S.extcomin_on = false;
    sim_trace(GL_SIM_TR_EXTCOMIN, 0, 0, 0, 0);
    sim_lcd_extcomin(false, 0);
}

gl_status_t gl_hal_xvclk_start(uint32_t hz)
{
    if (hz < 6000000u || hz > 27000000u) {
        return GL_ERR_RANGE;
    }
    sim_trace(GL_SIM_TR_XVCLK, 1, 0, hz, 0);
    if (!sim_pin_is_alt(GL_PIN_CAM_XVCLK)) {
        sim_violation(&S.viol.dcmi, "XVCLK started with its pin not in ALTERNATE mode");
    }
    sim_cam_xvclk(true, hz);
    return GL_OK;
}

void gl_hal_xvclk_stop(void)
{
    sim_trace(GL_SIM_TR_XVCLK, 0, 0, 0, 0);
    sim_cam_xvclk(false, 0);
}

/* ======================================================================= */
/* gl_hal.h: USB                                                            */
/* ======================================================================= */

gl_status_t gl_hal_usb_start(void)
{
    S.usb_started = true;
    sim_trace(GL_SIM_TR_USB, 1, 0, 0, 0);
    return GL_OK;
}

void gl_hal_usb_stop(void)
{
    S.usb_started = false;
    S.usb_rx_len = 0;
    S.irq_pending &= ~GL_IRQ_USB_RX;
    sim_trace(GL_SIM_TR_USB, 0, 0, 0, 0);
}

bool gl_hal_usb_connected(void)
{
    return S.usb_started && S.usb_host_open;
}

size_t gl_hal_usb_read(uint8_t *buf, size_t max)
{
    size_t n = (S.usb_rx_len < max) ? S.usb_rx_len : max;
    if (!S.usb_started) {
        return 0;
    }
    memcpy(buf, S.usb_rx, n);
    memmove(S.usb_rx, &S.usb_rx[n], S.usb_rx_len - n);
    S.usb_rx_len -= n;
    return n;
}

size_t gl_hal_usb_write(const uint8_t *buf, size_t len)
{
    if (!S.usb_started || !S.usb_host_open) {
        return 0;
    }
    if (S.usb_tx_chunk != 0u && len > S.usb_tx_chunk) {
        len = S.usb_tx_chunk;
    }
    if (len > SIM_USB_PIPE - S.usb_tx_len) {
        len = SIM_USB_PIPE - S.usb_tx_len;
    }
    memcpy(&S.usb_tx[S.usb_tx_len], buf, len);
    S.usb_tx_len += len;
    return len;
}
