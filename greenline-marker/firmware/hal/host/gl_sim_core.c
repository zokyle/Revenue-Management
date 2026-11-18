/*
 * gl_sim_core.c - host simulator backend of hal/gl_hal.h: time, trace,
 * GPIO, interrupts, sleep, SPI routing, analog, USB and the board rules.
 * See gl_sim.h for what is modelled and what is checked.
 */
#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#include "gl_boot.h"
#include "gl_pins.h"
#include "gl_provisional.h"
#include "gl_sim_cost.h"
#include "gl_sim_internal.h"

/* ---- board constants of the model --------------------------------------------- */

#define SIM_WDG_PERIOD_US (32u * 1000000ull) /* independent watchdog period */
#define SIM_RAIL_RISE_US 1000u               /* pins must stay parked this long after EN */
#define SIM_BYTE_LOG_MAX (4u * 1024u * 1024u)
#define SIM_SCHED_MAX 64
#define SIM_TIA_TAU_US 50.0f                 /* photodiode stage settling */
#define SIM_OPAMP_WAKE_US 1000u
#define SIM_USB_PIPE 65536u
/* MCU temperature sensor of the model: counts at 30 C with VDDA = 3.0 V and
 * the slope (2.5 mV/K at 14 bits), like the factory calibration points */
#define SIM_TS_CAL_30C 4000.0f
#define SIM_TS_COUNTS_PER_K 13.65f
#define SIM_TS_CAL_VDDA_MV 3000.0f
/* Cell-temperature divider of the model: the nominal parts (the simulated
 * unit's tolerances are added by gl_sim_ntc_set_tolerance), the time
 * constant of the sense node and how long the firmware must wait for it. */
#define SIM_NTC_R25_OHM 10000.0
#define SIM_NTC_B_K 3380.0
#define SIM_NTC_SERIES_OHM 10000.0
#define SIM_NTC_TAU_US 50.0
#define SIM_NTC_SETTLE_MIN_US 300u
#define SIM_PLL_LOCK_US 100u                 /* a switch to the fast clock takes this long */
/* The window the FIRMWARE's supervision is judged by (DESIGN_SPEC section 4:
 * 0..45 C for charging).  The charger's own window is GL_PROV_BQ25101_T_*. */
#define SIM_CELL_T_MIN_C 0.0f
#define SIM_CELL_T_MAX_C 45.0f
#define SIM_CHG_STEP_US 2000000u             /* longest step of the charger / cell integration */

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
    /* fault injection, compute time */
    unsigned spi_fail_count[GL_SPI_BUS_COUNT];
    gl_status_t spi_fail_status[GL_SPI_BUS_COUNT];
    uint32_t compute_us[GL_TRACE_COUNT];
    bool mcu_temp_pinned;
    float mcu_temp_c;
    /* cell temperature, NTC divider, charger */
    bool cell_temp_pinned;
    float cell_temp_c;
    uint8_t ntc_fault;
    float ntc_r25_rel, ntc_b_rel, ntc_series_rel;
    bool ntc_bias_on;
    uint64_t ntc_bias_since;
    uint64_t chg_t;              /* time up to which the charger has been accounted */
    uint64_t chg_stretch_us;     /* current stretch of charging outside the window */
    bool chg_stretch_reported;
    /* the board in the cradle: the VBUS pad (the VBUS_SENSE pin may lag) */
    bool vbus_pad;
    uint64_t vbus_sense_fall_at; /* when VBUS_SENSE follows a pad that has gone (SIM_NEVER: -) */
    /* charger model (BQ25101, PROVISIONAL: gl_provisional.h) */
    uint8_t ntc1_fault;
    bool chg_input_low;
    bool chg_stop_broken;
    uint8_t chg_state;           /* gl_sim_chg_state_t */
    bool chg_done;               /* terminated: waits for the recharge threshold */
    bool chg_cycle_ended;        /* a charge has terminated since the input appeared or the
                                    charger was last enabled: what follows is a RE-charge */
    bool chg_stat_first_only;    /* variant of the model: CHG is low in the first cycle only */
    bool chg_timer_fault;
    uint64_t chg_timer_us;       /* its safety timer */
    double chg_out_ua;           /* current out of the charger during the last step */
    /* cell model */
    bool cell_on;
    double cell_soc;             /* 0..1 */
    /* supply model */
    double load_ua;              /* the board's draw from the cell node in the last interval */
    bool underside_lit;
    uint64_t disp_high_since;    /* when LCD_DISP last went high (the grain bias) */
    /* MCU states without firmware */
    bool rom;                    /* ST's ROM loader is running */
    bool shutdown;               /* ship mode */
    bool ship_marker;            /* the backend's marker in the backup domain */
    uint32_t boot_attempts_reg;  /* the boot stub's count of unconfirmed starts (TAMP BKP3R) */
    double lcd_off_ua;           /* the panel with DISP low (gl_sim_set_lcd_off_ua) */
    uint64_t shutdown_since;
    /* core clock */
    uint8_t clock;
    uint64_t clock_fast_since;
    unsigned clock_fail;
    unsigned clock_fail_slow;
    uint8_t mcu_mode;            /* SIM_MCU_RUN / _IDLE / _STOP: for the supply model */
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
    bool usb_standby;
    uint8_t usb_bus;             /* gl_usb_bus_t: what the host does */
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

/* Cycles per instruction of the compute-time model: kept across gl_sim_reset
 * (gl_sim.h). */
static float cpi_ = GL_SIM_CPI_NOMINAL;

enum { SIM_MCU_RUN = 0, SIM_MCU_IDLE = 1, SIM_MCU_STOP = 2 };

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
/* cell temperature, the charger of rev E (BQ25101) and the cell            */
/* ======================================================================= */

static float cell_temp_(void)
{
    return S.cell_temp_pinned ? S.cell_temp_c : sim_imu_temperature();
}

/* The MOSFET on the charger's TS pin conducts: CHG_INHIBIT is DRIVEN high.
 * An open-drain "high" is high impedance and the 100 kohm on the gate wins;
 * so does it with the pin analog, the MCU in reset or unpowered. */
static bool inhibit_on_(void)
{
    return sim_pin_out_high(GL_PIN_CHG_INHIBIT);
}

/* ... and the MOSFET does what its gate says (a fault of the model: the
 * MOSFET or its gate connection open). */
static bool ts_pulled_low_(void)
{
    return inhibit_on_() && !S.chg_stop_broken;
}

static bool chg_charging_state_(uint8_t st)
{
    return st == (uint8_t)GL_SIM_CHG_FAST || st == (uint8_t)GL_SIM_CHG_COOL ||
           st == (uint8_t)GL_SIM_CHG_WARM || st == (uint8_t)GL_SIM_CHG_TTDM;
}

/* Open-circuit voltage of the cell model, mV, for a state of charge 0..1.
 * A GUESS for a 43 mAh pouch cell (no data sheet). */
static double cell_ocv_mv_(double soc)
{
    static const double pt[][2] = { { 0.00, 3000.0 }, { 0.03, 3300.0 }, { 0.10, 3550.0 },
                                    { 0.30, 3700.0 }, { 0.60, 3850.0 }, { 0.85, 4050.0 },
                                    { 1.00, 4200.0 } };
    const size_t n = sizeof(pt) / sizeof(pt[0]);
    if (soc <= pt[0][0]) {
        return pt[0][1];
    }
    for (size_t i = 1; i < n; i++) {
        if (soc <= pt[i][0]) {
            const double f = (soc - pt[i - 1u][0]) / (pt[i][0] - pt[i - 1u][0]);
            return pt[i - 1u][1] + f * (pt[i][1] - pt[i - 1u][1]);
        }
    }
    /* above "full": the curve goes on with its last slope (a cell can be
     * pushed a little past it; the charger's voltage limit is what stops) */
    return pt[n - 1u][1] + (soc - 1.0) * (pt[n - 1u][1] - pt[n - 2u][1]) / (pt[n - 1u][0] - pt[n - 2u][0]);
}

/*
 * What the BQ25101 of the model does RIGHT NOW (no time passes): from VBUS,
 * its TS pin (its own thermistor NTC1 on the cell, or the MOSFET), its
 * latches and the cell voltage.  Every rule here is PROVISIONAL
 * (gl_provisional.h, GL_PROV_BQ25101_*).  Then the level of its CHG output.
 */
static void charger_update_(void)
{
    const float t = cell_temp_();
    const bool input = S.vbus_pad && !S.chg_input_low;
    const bool ts_low = ((GL_PROV_BQ25101_TS_LOW_DISABLES != 0) && ts_pulled_low_()) ||
                        S.ntc1_fault == (uint8_t)GL_SIM_NTC1_SHORT;
    const bool ttdm = (GL_PROV_BQ25101_TS_OPEN_IS_TTDM != 0) &&
                      S.ntc1_fault == (uint8_t)GL_SIM_NTC1_OPEN && !ts_low;
    const bool warm = !ttdm && t > GL_PROV_BQ25101_T_WARM_C;
    const double vreg = warm ? (double)GL_PROV_BQ25101_VREG_WARM_MV : (double)GL_PROV_BQ25101_VREG_MV;
    uint8_t st;

    if (!input || ts_low) {
        /* input gone, or disabled through TS: both restart the charger's
         * cycle, its termination latch and its timer */
        S.chg_done = false;
        S.chg_cycle_ended = false;
        S.chg_timer_fault = false;
        S.chg_timer_us = 0;
        st = (uint8_t)(input ? GL_SIM_CHG_DISABLED : GL_SIM_CHG_NO_INPUT);
    } else if (!ttdm && t < GL_PROV_BQ25101_T_COLD_C) {
        st = (uint8_t)GL_SIM_CHG_COLD;
    } else if (!ttdm && t > GL_PROV_BQ25101_T_HOT_C) {
        st = (uint8_t)GL_SIM_CHG_HOT;
    } else if (ttdm) {
        st = (uint8_t)GL_SIM_CHG_TTDM; /* no termination, no timer, no window */
    } else if (S.chg_timer_fault) {
        st = (uint8_t)GL_SIM_CHG_TIMER;
    } else {
        if (S.chg_done && (double)S.vbat_mv < vreg - (double)GL_PROV_BQ25101_RECHARGE_DROP_MV) {
            S.chg_done = false; /* recharge */
        }
        if (!S.cell_on && !S.chg_done && (double)S.vbat_mv >= vreg) {
            /* fixed-voltage mode of the model (no cell dynamics): a cell AT
             * the regulation voltage is a finished charge */
            S.chg_done = true;
            S.chg_cycle_ended = true;
            S.stats.chg_terminations++;
        }
        if (S.chg_done) {
            st = (uint8_t)GL_SIM_CHG_DONE;
        } else if (warm) {
            st = (uint8_t)GL_SIM_CHG_WARM;
        } else if (t < GL_PROV_BQ25101_T_COOL_C) {
            st = (uint8_t)GL_SIM_CHG_COOL;
        } else {
            st = (uint8_t)GL_SIM_CHG_FAST;
        }
    }
    S.chg_state = st;
    if (!chg_charging_state_(st)) {
        S.chg_out_ua = 0.0;
    }
    /* CHG: open drain, low while a charge runs; the board's pull-up otherwise.
     * Variant (GL_PROV_BQ25101_CHG_LOW_ON_RECHARGE = 0, or the test's switch):
     * low in the FIRST cycle only - a recharge after a termination runs with
     * CHG released, until the input goes or the charger is disabled through
     * TS.  In the test mode of an open TS nothing terminates, so the question
     * does not arise there. */
    sim_set_input(GL_PIN_CHG_STAT,
                  !(chg_charging_state_(st) && !(S.chg_stat_first_only && S.chg_cycle_ended)));
}

/* One step of the charger and the cell: the conditions (state, load) held
 * for dt.  Returns nothing; updates the cell, the latches and the charger
 * statistics. */
static void charger_step_(uint64_t dt)
{
    const double s = (double)dt * 1e-6;
    const double sys = S.load_ua; /* the board, on the same node */
    const uint8_t st = S.chg_state;
    const float t = cell_temp_();
    double icell;

    if (inhibit_on_()) {
        S.stats.inhibit_us += dt;
    }
    if (S.vbus_pad) {
        S.stats.docked_us += dt;
        S.stats.load_docked_uas += sys * s;
    }
    if (!chg_charging_state_(st)) {
        icell = -sys;
        S.chg_out_ua = 0.0;
        S.chg_stretch_us = 0;
        S.chg_stretch_reported = false;
    } else {
        const bool ttdm = (st == (uint8_t)GL_SIM_CHG_TTDM);
        const double iset = (double)GL_PROV_BQ25101_ICHG_UA * ((st == (uint8_t)GL_SIM_CHG_COOL) ? 0.5 : 1.0);
        const double vreg = (st == (uint8_t)GL_SIM_CHG_WARM) ? (double)GL_PROV_BQ25101_VREG_WARM_MV
                                                             : (double)GL_PROV_BQ25101_VREG_MV;
        double iout = iset;
        icell = iset - sys;
        if (S.cell_on) {
            const double ocv = cell_ocv_mv_(S.cell_soc);
            if (ocv + icell * 1e-3 * GL_SIM_CELL_R_OHM >= vreg) {
                /* constant voltage: the cell takes what the voltage gives it */
                icell = (vreg - ocv) * 1e3 / GL_SIM_CELL_R_OHM;
                iout = icell + sys;
                if (iout < 0.0) {
                    iout = 0.0; /* a linear charger cannot sink: the cell feeds the board */
                    icell = -sys;
                }
                if (!ttdm && iout < (double)GL_PROV_BQ25101_TERM_FRACTION * (double)GL_PROV_BQ25101_ICHG_UA) {
                    S.chg_done = true; /* termination: it takes effect at the next update */
                    S.chg_cycle_ended = true;
                    S.stats.chg_terminations++;
                }
            }
        }
        S.chg_out_ua = iout;
        /* statistics: who was there, and where the cell was */
        if (t < GL_PROV_BQ25101_T_COLD_C || t > GL_PROV_BQ25101_T_HOT_C) {
            S.stats.chg_hw_outside_us += dt;
        }
        if (st == (uint8_t)GL_SIM_CHG_WARM) {
            S.stats.chg_warm_us += dt;
        } else if (st == (uint8_t)GL_SIM_CHG_COOL) {
            S.stats.chg_cool_us += dt;
        }
        if (!ttdm && GL_PROV_BQ25101_SAFETY_TIMER_H != 0u) {
            S.chg_timer_us += dt;
            if (S.chg_timer_us >= (uint64_t)GL_PROV_BQ25101_SAFETY_TIMER_H * 3600u * 1000000u) {
                S.chg_timer_fault = true;
                S.stats.chg_timer_faults++;
            }
        }
        if (!S.inited) {
            /* no firmware (reset, ROM loader, ship mode): the charger alone */
            S.stats.chg_in_reset_us += dt;
            if (t < SIM_CELL_T_MIN_C || t > SIM_CELL_T_MAX_C) {
                S.stats.chg_alone_outside_us += dt;
            }
            S.chg_stretch_us = 0;
            S.chg_stretch_reported = false;
        } else {
            S.stats.chg_on_us += dt;
            if (t < SIM_CELL_T_MIN_C || t > SIM_CELL_T_MAX_C) {
                S.stats.chg_outside_us += dt;
                S.chg_stretch_us += dt;
                if (S.chg_stretch_us > S.stats.chg_outside_longest_us) {
                    S.stats.chg_outside_longest_us = S.chg_stretch_us;
                }
                if (S.chg_stretch_us > (uint64_t)GL_SIM_CHG_REACT_MAX_MS * 1000u && !S.chg_stretch_reported) {
                    S.chg_stretch_reported = true;
                    sim_violation(&S.viol.power,
                                  "charging for %.1f s with the cell at %.1f C (outside the firmware's "
                                  "0..45 C) while firmware runs", (double)S.chg_stretch_us / 1e6, (double)t);
                }
            } else {
                S.chg_stretch_us = 0;
                S.chg_stretch_reported = false;
            }
        }
    }
    if (S.cell_on) {
        /* the charge that went into the cell, or out of it */
        S.cell_soc += icell * s / (GL_SIM_CELL_MAH * 3.6e6);
        if (S.cell_soc < 0.0) {
            S.cell_soc = 0.0;
        }
        {
            double v = cell_ocv_mv_(S.cell_soc) + icell * 1e-3 * GL_SIM_CELL_R_OHM;
            if (v < 0.0) {
                v = 0.0;
            }
            S.vbat_mv = (uint16_t)(v + 0.5);
        }
    }
}

/* Bring the charger and the cell up to now.  The conditions (VBUS, the pin,
 * the temperature, the load) change only between two advances of the clock,
 * so this is called wherever the clock advances; it integrates in steps of
 * at most SIM_CHG_STEP_US, because the cell's voltage moves the charger. */
static void charger_account_(void)
{
    uint64_t left = S.now_us - S.chg_t;
    S.chg_t = S.now_us;
    while (left != 0u) {
        const uint64_t dt = (left > SIM_CHG_STEP_US && S.cell_on) ? SIM_CHG_STEP_US : left;
        charger_step_(dt);
        left -= dt;
        if (S.cell_on || left == 0u) {
            charger_update_();
        }
    }
}

/* Fraction of full scale at the sense pin with the bias driven. */
static double ntc_fraction_(double temp_c)
{
    const double r = SIM_NTC_R25_OHM * (1.0 + (double)S.ntc_r25_rel) *
                     exp(SIM_NTC_B_K * (1.0 + (double)S.ntc_b_rel) *
                         (1.0 / (temp_c + 273.15) - 1.0 / 298.15));
    return r / (r + SIM_NTC_SERIES_OHM * (1.0 + (double)S.ntc_series_rel));
}

static double ntc2_ohm_(void)
{
    return SIM_NTC_R25_OHM * (1.0 + (double)S.ntc_r25_rel) *
           exp(SIM_NTC_B_K * (1.0 + (double)S.ntc_b_rel) *
               (1.0 / ((double)cell_temp_() + 273.15) - 1.0 / 298.15));
}

static void ntc_bias_update_(void)
{
    const bool on = sim_pin_out_high(GL_PIN_NTC_BIAS);
    if (on && !S.ntc_bias_on) {
        S.ntc_bias_since = S.now_us;
    } else if (!on && S.ntc_bias_on) {
        S.stats.ntc_bias_us += S.now_us - S.ntc_bias_since;
    }
    S.ntc_bias_on = on;
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
            if (disp) {
                S.disp_high_since = S.now_us; /* the grain bias divider hangs on this line */
            }
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
    if (pin == GL_PIN_NTC_BIAS) {
        ntc_bias_update_();
    }
    if (pin == GL_PIN_CHG_INHIBIT) {
        /* the pin drives the gate of the MOSFET on the charger's TS input
         * (100 kohm to ground on the gate): push-pull or analog.  An
         * open-drain "high" stops nothing; an internal pull-up half opens
         * the MOSFET with the MCU believing the charger free */
        const uint8_t m = S.pin[pin].mode;
        if (m == (uint8_t)GL_PIN_MODE_OUTPUT_OD || m == (uint8_t)GL_PIN_MODE_INPUT_PULLUP ||
            m == (uint8_t)GL_PIN_MODE_INPUT_PULLDOWN) {
            sim_violation(&S.viol.power, "CHG_INHIBIT in mode %d %s: push-pull or analog only", (int)m,
                          what);
        }
        charger_account_();
        charger_update_();
    }
    if (pin == GL_PIN_CHG_STAT) {
        /* the charger's open-drain output with the board's pull-up, on a USB
         * Type-C CC pad of the MCU: an input without an internal pull */
        const uint8_t m = S.pin[pin].mode;
        if (m != (uint8_t)GL_PIN_MODE_ANALOG && m != (uint8_t)GL_PIN_MODE_INPUT) {
            sim_violation(&S.viol.power, "CHG_STAT in mode %d %s: input without a pull only", (int)m,
                          what);
        }
    }
    if (pin == GL_PIN_OPAMP_VOUT && !S.opamp_on &&
        (S.pin[pin].mode == (uint8_t)GL_PIN_MODE_OUTPUT_PP ||
         S.pin[pin].mode == (uint8_t)GL_PIN_MODE_OUTPUT_OD)) {
        sim_violation(&S.viol.analog, "OPAMP_VOUT driven with the op-amp off (150 kohm to the rail)");
    }
    /* the board's pull resistors hold the chip selects inactive; an internal
     * pull the other way would fight them */
    if (((pin == GL_PIN_FLASH_CS || pin == GL_PIN_IMU_CS) &&
         S.pin[pin].mode == (uint8_t)GL_PIN_MODE_INPUT_PULLDOWN) ||
        ((pin == GL_PIN_LCD_SCS || pin == GL_PIN_LCD_DISP) &&
         S.pin[pin].mode == (uint8_t)GL_PIN_MODE_INPUT_PULLUP)) {
        sim_violation(&S.viol.spi, "pin %d: internal pull against the board's pull resistor",
                      (int)pin);
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
    if (S.vbus_sense_fall_at < t) {
        t = S.vbus_sense_fall_at;
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

/* Resistance of NTC2 at the cell temperature (the divider of the model). */
static double ntc2_ohm_(void);

/* The supply model: what the board draws from the cell's node RIGHT NOW,
 * microamperes, with the MCU in its present state; the parts of it.  0 for
 * an MCU held in reset (not modelled). */
static double load_now_(double *mcu_out, double *imu_out, double *cam_out)
{
    const bool fast = (S.clock == (uint8_t)GL_CLOCK_FAST);
    const bool disp = sim_pin_out_high(GL_PIN_LCD_DISP);
    double mcu, imu, cam = 0.0, rest;

    if (S.shutdown) {
        mcu = GL_SIM_I_MCU_SHUTDOWN_UA;
    } else if (S.rom) {
        mcu = GL_SIM_I_MCU_ROM_UA;
    } else if (!S.inited) {
        mcu = 0.0; /* held in reset: not modelled */
    } else if (S.mcu_mode == (uint8_t)SIM_MCU_STOP) {
        mcu = (S.usb_standby && GL_PROV_USB_WAKE_FROM_STOP2 == 0) ? GL_SIM_I_MCU_STOP1_UA
                                                                 : GL_SIM_I_MCU_STOP_UA;
    } else if (S.mcu_mode == (uint8_t)SIM_MCU_IDLE) {
        mcu = fast ? GL_SIM_I_MCU_IDLE_FAST_UA : GL_SIM_I_MCU_IDLE_SLOW_UA;
    } else {
        mcu = fast ? GL_SIM_I_MCU_RUN_FAST_UA : GL_SIM_I_MCU_RUN_SLOW_UA;
    }
    imu = sim_imu_supply_ua();
    /* always there (the charger's leakage out of the cell only without an
     * input: with VBUS it is fed from there) */
    rest = GL_SIM_I_ALWAYS_UA(S.vbat_mv) - (S.vbus_pad ? GL_SIM_I_CHARGER_LEAK_UA : 0.0);
    rest += sim_flash_supply_ua();
    /* the display, and the two resistors that hang on DISP */
    if (disp) {
        rest += GL_SIM_I_LCD_ON_UA + GL_SIM_I_DISP_PULLDOWN_UA + GL_SIM_I_GRAIN_BIAS_UA;
    } else {
        rest += S.lcd_off_ua; /* the panel stays on the always-on rail (see gl_sim.h) */
    }
    rest += (S.adc_on ? GL_SIM_I_ADC_UA : 0.0) + (S.opamp_on ? GL_SIM_I_OPAMP_UA : 0.0) +
            ((gl_sim_grain_lit_mask() != 0u) ? GL_SIM_I_GRAIN_LED_UA : 0.0);
    if (S.usb_started) {
        rest += GL_SIM_I_USB_UA;
    } else if (S.usb_standby) {
        rest += GL_SIM_I_USB_STANDBY_UA;
    }
    /* pins driven against a resistor of the board */
    if (!S.pin[GL_PIN_CHG_STAT].ext) {
        rest += GL_SIM_I_CHG_STAT_PULLUP_UA; /* the charger pulls CHG low */
    }
    if (sim_pin_out_high(GL_PIN_CHG_INHIBIT)) {
        rest += GL_SIM_I_CHG_INHIBIT_UA;
    }
    if (sim_pin_out_high(GL_PINS_BOOT0_SHARED_WITH)) {
        rest += GL_SIM_I_BOOT0_PULLDOWN_UA;
    }
    if (sim_pin_out_low(GL_PIN_OPAMP_VOUT)) {
        rest += GL_SIM_I_OPAMP_OUT_LOW_UA;
    } else if (S.underside_lit && !S.opamp_on) {
        rest += GL_SIM_I_WAKE_PULLUP_LIT_UA;
    }
    if (sim_pin_out_high(GL_PIN_NTC_BIAS)) {
        rest += (double)S.vdda_mv * 1000.0 / (SIM_NTC_SERIES_OHM + ntc2_ohm_());
    }
    if (S.rail_on) {
        cam = GL_SIM_I_CAM_RAIL_UA;
    }
    if (mcu_out != NULL) {
        *mcu_out = mcu;
        *imu_out = imu;
        *cam_out = cam;
    }
    return mcu + imu + cam + rest;
}

/* Charge drawn from the cell while the clock advances by dt with everything
 * in its present state (states change only between two advances).  The
 * board hangs on the cell's node: what it draws comes out of the cell
 * unless a charge is running (the charger then supplies it; charger_step_
 * books that as the docked load).  Nothing is counted for an MCU held in
 * reset. */
static void supply_account_(uint64_t dt)
{
    const bool fast = (S.clock == (uint8_t)GL_CLOCK_FAST);
    const double s = (double)dt * 1e-6;
    double mcu = 0.0, imu = 0.0, cam = 0.0, total;

    if (S.shutdown) {
        S.stats.shutdown_us += dt;
    } else if (S.mcu_mode == (uint8_t)SIM_MCU_RUN) {
        S.stats.run_us += dt;
        if (fast) {
            S.stats.run_fast_us += dt;
        }
    } else if (S.mcu_mode == (uint8_t)SIM_MCU_IDLE && fast) {
        S.stats.idle_fast_us += dt;
    }
    total = load_now_(&mcu, &imu, &cam);
    S.load_ua = total;
    if ((!S.inited && !S.shutdown && !S.rom) || chg_charging_state_(S.chg_state)) {
        return;
    }
    S.stats.charge_mcu_uas += mcu * s;
    S.stats.charge_imu_uas += imu * s;
    S.stats.charge_cam_uas += cam * s;
    S.stats.charge_uas += total * s;
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
            supply_account_(t - S.now_us);
            S.now_us = t;
            watchdog_check_();
            charger_account_();
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
        if (S.vbus_sense_fall_at <= S.now_us) {
            S.vbus_sense_fall_at = SIM_NEVER;
            sim_set_input(GL_PIN_VBUS_SENSE, false); /* the divider has discharged the pad */
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
        supply_account_(t_target - S.now_us);
        S.now_us = t_target;
        watchdog_check_();
        charger_account_();
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
    S.chg_stat_first_only = (GL_PROV_BQ25101_CHG_LOW_ON_RECHARGE == 0);
    S.vbus_sense_fall_at = SIM_NEVER;
    S.stats.grain_bias_short_us = UINT64_MAX;
    S.lcd_off_ua = GL_SIM_I_LCD_OFF_UA;
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

bool gl_sim_pin_level(gl_pin_t pin)
{
    if ((unsigned)pin >= (unsigned)GL_PIN_COUNT) {
        return false;
    }
    if (sim_pin_out_high(pin)) {
        return true;
    }
    if (sim_pin_out_low(pin)) {
        return false;
    }
    /* not driven by the MCU: the board's resistor decides where there is one
     * (the generated table of the netlist's pin map) ... */
    {
        typedef struct {
            gl_pin_t pin;
            bool level;
        } pull_t;
#define SIM_PULL(logical, level, handover) { logical, (level) != 0 },
        static const pull_t pulls[] = { GL_PINS_RESET_TABLE(SIM_PULL) };
#undef SIM_PULL
        /* (CHG_STAT is in the table for its pull-up; the charger's open drain
         * wins against it, and the model keeps that in `ext`) */
        if (pin != GL_PIN_CHG_STAT) {
            for (size_t i = 0; i < sizeof(pulls) / sizeof(pulls[0]); i++) {
                if (pulls[i].pin == pin) {
                    return pulls[i].level;
                }
            }
        }
    }
    /* ... otherwise whatever is connected from outside */
    return S.pin[pin].ext;
}

/* Every pin high impedance and every peripheral stopped, at one instant:
 * what a reset and the entry into Shutdown have in common. */
static void mcu_pins_release_(void)
{
    const bool lcd_cs = cs_asserted_(GL_PIN_LCD_SCS);
    const bool flash_cs = cs_asserted_(GL_PIN_FLASH_CS);
    const bool imu_cs = cs_asserted_(GL_PIN_IMU_CS);
    const bool disp = sim_pin_out_high(GL_PIN_LCD_DISP);

    charger_account_();
    for (int p = 0; p < (int)GL_PIN_COUNT; p++) {
        S.pin[p].mode = (uint8_t)GL_PIN_MODE_ANALOG;
        S.pin[p].latch = false;
    }
    update_rail_();
    sim_cam_update();
    spi_cs_edges_(GL_PIN_LCD_SCS, lcd_cs);
    spi_cs_edges_(GL_PIN_FLASH_CS, flash_cs);
    spi_cs_edges_(GL_PIN_IMU_CS, imu_cs);
    if (disp) {
        sim_lcd_disp(false);
    }
    ntc_bias_update_();
    if (S.clock == (uint8_t)GL_CLOCK_FAST) {
        S.stats.clock_fast_us += S.now_us - S.clock_fast_since;
        S.clock = (uint8_t)GL_CLOCK_SLOW;
    }
    S.extcomin_on = false;
    sim_lcd_extcomin(false, 0);
    S.usb_started = false;
    S.usb_standby = false;
    S.adc_on = false;
    S.opamp_on = false;
    S.irq_enabled = 0;
    S.irq_pending = 0;
    S.irq_lock = 0;
    S.wake_timer_at = SIM_NEVER;
    S.inited = false;
    S.mcu_mode = (uint8_t)SIM_MCU_RUN;
    charger_update_(); /* CHG_INHIBIT is released with the rest */
}

void gl_sim_mcu_reset(uint32_t reason)
{
    mcu_pins_release_();
    /* "the peripherals stop": a camera capture that was running is over
     * (until the phase-3 review the capture model stayed busy and judged a
     * frame that no peripheral was receiving: a false "the driving camera
     * changed during a capture" about 7 ms after a reset inside an exposure) */
    sim_cam_mcu_reset();
    S.rom = false;
    /* DESIGN_SPEC E34: every reset passes through the boot stub.  The model
     * runs the stub's own decision (boot/gl_boot_logic.c) on its backup
     * register, with a valid image, and records what the stub would do; it
     * does not act on it (a test that wants the ROM loader says so with
     * gl_sim_mcu_enter_rom).  The application's half of the contract -
     * gl_hal_boot_confirm(), the cleared count before a deliberate reset -
     * is what moves the register between two resets. */
    {
        gl_boot_inputs_t in;
        gl_boot_decision_t d;
        in.image_valid = true;
        in.update_requested = false;
        in.abnormal_reset = (reason & (GL_RESET_WATCHDOG | GL_RESET_SOFTWARE)) != 0u;
        in.vbus = S.vbus_pad;
        in.attempts_reg = S.boot_attempts_reg;
        in.ship_mode = S.ship_marker;
        gl_boot_decide(&in, &d);
        S.boot_attempts_reg = d.attempts_reg;
        S.stats.boot_last_action = d.action;
        S.stats.boot_last_why = d.why;
        S.stats.boot_stub_passes++;
        if (d.action != (uint8_t)GL_BOOT_START_APP && d.action != (uint8_t)GL_BOOT_START_APP_QUIET) {
            S.stats.boot_not_started++;
        }
    }
    if (S.shutdown) {
        /* a reset ends Shutdown; the backend's marker decides at the next
         * gl_hal_init() whether the marker goes straight back */
        S.shutdown = false;
    }
    S.reset_reason = reason;
    sim_trace(GL_SIM_TR_REBOOT, 0xFFu, 0, reason, 0);
}

void gl_sim_set_lcd_off_ua(double ua)
{
    S.lcd_off_ua = ua;
}

uint32_t gl_sim_boot_attempts_reg(void)
{
    return S.boot_attempts_reg;
}

void gl_sim_mcu_enter_rom(void)
{
    gl_sim_mcu_reset(GL_RESET_SOFTWARE);
    S.rom = true;
}

bool gl_sim_mcu_shutdown(void)
{
    return S.shutdown;
}

/* The VBUS pad: 5 V present or not.  The charger and the USB supply of the
 * MCU follow it at once; the monitor of that supply is an interrupt source
 * of its own (GL_IRQ_VBUS_CHANGE), whatever the VBUS_SENSE pin reads. */
static void vbus_pad_set_(bool present)
{
    if (present == S.vbus_pad) {
        return;
    }
    charger_account_();
    S.vbus_pad = present;
    charger_update_();
    sim_irq_raise(GL_IRQ_VBUS_CHANGE);
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
        if (level && S.shutdown) {
            /* ship mode: a rising edge on the wake-up pin restarts the MCU */
            S.shutdown = false;
            S.reset_reason = GL_RESET_SHIP_WAKE;
            S.stats.ship_wakes++;
            sim_trace(GL_SIM_TR_REBOOT, 0xFEu, 0, GL_RESET_SHIP_WAKE, 0);
        }
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
    if (pin == GL_PIN_VBUS_SENSE) {
        /* into / out of the cradle: the pad and the pin together */
        S.vbus_sense_fall_at = SIM_NEVER;
        vbus_pad_set_(level);
    }
    sim_set_input(pin, level);
}

void gl_sim_vbus_remove_lagging(uint32_t lag_ms)
{
    vbus_pad_set_(false);
    if (lag_ms == 0u) {
        sim_set_input(GL_PIN_VBUS_SENSE, false);
    } else if (S.pin[GL_PIN_VBUS_SENSE].ext) {
        S.vbus_sense_fall_at = S.now_us + (uint64_t)lag_ms * 1000u;
    }
}

bool gl_sim_vbus_present(void)
{
    return S.vbus_pad;
}

const gl_sim_violations_t *gl_sim_violations(void)
{
    return &S.viol;
}

unsigned gl_sim_violation_total(void)
{
    const gl_sim_violations_t *v = &S.viol;
    return v->cam_rail + v->cam_contention + v->cam_sccb + v->dcmi + v->lcd + v->flash + v->imu +
           v->spi + v->stop_mode + v->analog + v->watchdog + v->deadlock + v->power + v->clock;
}

const gl_sim_stats_t *gl_sim_stats(void)
{
    static gl_sim_stats_t snapshot;
    charger_account_();
    charger_update_();
    snapshot = S.stats;
    if (S.rail_on) {
        snapshot.cam_rail_on_us += S.now_us - S.rail_on_since;
    }
    if (S.clock == (uint8_t)GL_CLOCK_FAST) {
        snapshot.clock_fast_us += S.now_us - S.clock_fast_since;
    }
    if (S.ntc_bias_on) {
        snapshot.ntc_bias_us += S.now_us - S.ntc_bias_since;
    }
    return &snapshot;
}

bool gl_sim_cam_rail_on(void)
{
    return S.rail_on;
}

void gl_sim_set_vbat_mv(uint16_t mv)
{
    if (S.cell_on) {
        return; /* the cell model owns the voltage */
    }
    charger_account_();
    S.vbat_mv = mv;
    charger_update_();
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

void gl_sim_usb_host_bus(gl_usb_bus_t bus)
{
    const uint8_t before = S.usb_bus;
    S.usb_bus = (uint8_t)bus;
    if (bus == GL_USB_BUS_ACTIVE && before != (uint8_t)GL_USB_BUS_ACTIVE && S.usb_standby) {
        sim_irq_raise(GL_IRQ_USB_WAKE); /* the host resumes the bus */
    }
    if (bus == GL_USB_BUS_NONE) {
        S.usb_host_open = false;
    }
}

void gl_sim_usb_host_open(bool open)
{
    S.usb_host_open = open;
    if (open) {
        gl_sim_usb_host_bus(GL_USB_BUS_ACTIVE);
    }
}

void gl_sim_usb_host_send(const uint8_t *data, size_t len)
{
    if (!S.usb_started && !S.usb_standby) {
        return;
    }
    /* a host that sends is on the bus; out of standby that is the resume,
     * and the bytes wait until the device has its clocks back */
    gl_sim_usb_host_bus(GL_USB_BUS_ACTIVE);
    if (len > SIM_USB_PIPE - S.usb_rx_len) {
        len = SIM_USB_PIPE - S.usb_rx_len;
    }
    memcpy(&S.usb_rx[S.usb_rx_len], data, len);
    S.usb_rx_len += len;
    if (len > 0u && S.usb_started) {
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

void gl_sim_set_mcu_temperature(float temp_c)
{
    S.mcu_temp_pinned = true;
    S.mcu_temp_c = temp_c;
}

void sim_cell_temp_change(bool before)
{
    if (before) {
        charger_account_();
    } else {
        charger_update_();
    }
}

void gl_sim_set_cell_temperature(float temp_c)
{
    charger_account_();
    S.cell_temp_pinned = true;
    S.cell_temp_c = temp_c;
    charger_update_();
}

float gl_sim_cell_temperature(void)
{
    return cell_temp_();
}

void gl_sim_ntc_set_fault(gl_sim_ntc_fault_t fault)
{
    S.ntc_fault = (uint8_t)fault;
}

void gl_sim_ntc_set_tolerance(float r25_rel, float b_rel, float series_rel)
{
    S.ntc_r25_rel = r25_rel;
    S.ntc_b_rel = b_rel;
    S.ntc_series_rel = series_rel;
}

double gl_sim_ntc_counts_at(double temp_c)
{
    return ntc_fraction_(temp_c) * (double)GL_HAL_ADC_FULL_SCALE;
}

void gl_sim_ntc1_set_fault(gl_sim_ntc1_fault_t fault)
{
    charger_account_();
    S.ntc1_fault = (uint8_t)fault;
    charger_update_();
}

void gl_sim_charger_stop_broken(bool broken)
{
    charger_account_();
    S.chg_stop_broken = broken;
    charger_update_();
}

void gl_sim_charger_stat_first_cycle_only(bool first_only)
{
    charger_account_();
    S.chg_stat_first_only = first_only;
    charger_update_();
}

void gl_sim_charger_input_low(bool low)
{
    charger_account_();
    S.chg_input_low = low;
    charger_update_();
}

gl_sim_chg_state_t gl_sim_charger_state(void)
{
    charger_account_();
    charger_update_(); /* (the board temperature may have been changed through the IMU model) */
    return (gl_sim_chg_state_t)S.chg_state;
}

const char *gl_sim_charger_state_name(gl_sim_chg_state_t state)
{
    static const char *const names[] = { "NO_INPUT", "DISABLED", "COLD", "HOT", "DONE", "TIMER",
                                         "FAST", "COOL", "WARM", "TTDM" };
    return ((unsigned)state < sizeof(names) / sizeof(names[0])) ? names[state] : "?";
}

bool gl_sim_charger_on(void)
{
    return chg_charging_state_((uint8_t)gl_sim_charger_state());
}

double gl_sim_charger_out_ua(void)
{
    return chg_charging_state_((uint8_t)gl_sim_charger_state()) ? S.chg_out_ua : 0.0;
}

void gl_sim_cell_enable(float soc)
{
    charger_account_();
    S.cell_on = true;
    S.cell_soc = (soc < 0.0f) ? 0.0 : (double)soc;
    S.vbat_mv = (uint16_t)(cell_ocv_mv_(S.cell_soc) + 0.5);
    charger_update_();
}

float gl_sim_cell_soc(void)
{
    charger_account_();
    return (float)S.cell_soc;
}

double gl_sim_load_ua(void)
{
    return load_now_(NULL, NULL, NULL);
}

void gl_sim_set_underside_lit(bool lit)
{
    S.underside_lit = lit;
}

gl_clock_t gl_sim_clock(void)
{
    return (gl_clock_t)S.clock;
}

void gl_sim_clock_fail_slow(unsigned count)
{
    S.clock_fail_slow = count;
}

void gl_sim_clock_fail(unsigned count)
{
    S.clock_fail = count;
}

void gl_sim_spi_fail(gl_spi_bus_t bus, unsigned count, gl_status_t st)
{
    if ((unsigned)bus < (unsigned)GL_SPI_BUS_COUNT) {
        S.spi_fail_count[bus] = count;
        S.spi_fail_status[bus] = st;
    }
}

void gl_sim_irq_drop(uint32_t mask)
{
    S.irq_pending &= ~mask;
}

void gl_sim_set_compute_us(gl_trace_point_t point, uint32_t us)
{
    if ((unsigned)point < (unsigned)GL_TRACE_COUNT) {
        S.compute_us[point] = us;
    }
}

void gl_sim_set_cpi(float cycles_per_instr)
{
    cpi_ = (cycles_per_instr > 0.0f && cycles_per_instr < 1000.0f) ? cycles_per_instr : 0.0f;
}

float gl_sim_cpi(void)
{
    return cpi_;
}

uint64_t gl_sim_stage_instr(gl_trace_point_t point, uint32_t work)
{
    static const uint32_t found[3] = GL_SIM_COST_REFINE_FOUND_IR;
    static const uint32_t none[3] = GL_SIM_COST_REFINE_NONE_IR;
    switch (point) {
    case GL_TRACE_VISION_BAND:
        return ((uint64_t)GL_SIM_COST_BAND_IR * work) / GL_SIM_COST_BAND_PX;
    case GL_TRACE_VISION_STRIP: {
        uint64_t ir = 0;
        int last = -1;
        for (int b = 0; b < 3; b++) {
            if ((work & (GL_TRACE_STRIP_TRIED_1 << b)) != 0u) {
                ir += none[b];
                last = b;
            }
        }
        if (last >= 0 && (work & GL_TRACE_STRIP_FOUND) != 0u) {
            /* the last attempt found the line */
            const uint64_t f = (last == 0 && (work & GL_TRACE_STRIP_WIDE) != 0u)
                                   ? (uint64_t)GL_SIM_COST_REFINE_WIDE_IR : (uint64_t)found[last];
            ir += f - none[last];
        }
        if ((work & GL_TRACE_STRIP_STATS) != 0u) {
            ir += GL_SIM_COST_STRIP_STATS_IR;
        }
        return ir;
    }
    case GL_TRACE_VISION_GROUP:
        return GL_SIM_COST_GROUP_IR;
    case GL_TRACE_SOLVE:
        return (uint64_t)GL_SIM_COST_SOLVE_BASE_IR + (uint64_t)GL_SIM_COST_SOLVE_STEP_IR * work;
    case GL_TRACE_RENDER:
        return GL_SIM_COST_RENDER_IR;
    default:
        return 0;
    }
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
#define SIM_FLOAT(logical) logical,
    static const gl_pin_t floating[] = { GL_PINS_FLOATING_TABLE(SIM_FLOAT) };
#undef SIM_FLOAT
    typedef struct {
        gl_pin_t pin;
        bool level, handover;
    } reset_t;
#define SIM_RESET(logical, level, handover) { logical, (level) != 0, (handover) != 0 },
    static const reset_t reset[] = { GL_PINS_RESET_TABLE(SIM_RESET) };
#undef SIM_RESET

    charger_account_();
    S.rom = false;
    /* SHIP MODE (gl_hal.h): the marker in the backup domain.  With VBUS the
     * marker has left ship mode; without it (a reset from any other cause)
     * it goes straight back - a target backend does not return from here */
    if (S.ship_marker) {
        if (S.pin[GL_PIN_VBUS_SENSE].ext) {
            S.ship_marker = false;
        } else {
            for (int p = 0; p < (int)GL_PIN_COUNT; p++) {
                S.pin[p].mode = (uint8_t)GL_PIN_MODE_ANALOG;
                S.pin[p].latch = false;
            }
            S.shutdown = true;
            S.inited = false;
            S.reset_reason = GL_RESET_SHIP_HELD;
            return GL_ERR_STATE;
        }
    }
    S.shutdown = false;
    for (int p = 0; p < (int)GL_PIN_COUNT; p++) {
        S.pin[p].mode = (uint8_t)GL_PIN_MODE_ANALOG;
        S.pin[p].latch = false;
    }
    update_rail_();
    ntc_bias_update_();
    if (S.clock == (uint8_t)GL_CLOCK_FAST) {
        S.stats.clock_fast_us += S.now_us - S.clock_fast_since;
    }
    S.clock = (uint8_t)GL_CLOCK_SLOW;
    S.usb_started = false;
    S.usb_standby = false;
    /* 1. the lines that float in reset get their level first */
    for (size_t i = 0; i < sizeof(floating) / sizeof(floating[0]); i++) {
        gl_hal_gpio_write(floating[i], false);
        gl_hal_gpio_mode(floating[i], GL_PIN_MODE_OUTPUT_PP);
    }
    /* 2. the pins a board resistor holds: taken over at that level */
    for (size_t i = 0; i < sizeof(reset) / sizeof(reset[0]); i++) {
        if (reset[i].handover) {
            gl_hal_gpio_write(reset[i].pin, reset[i].level);
            gl_hal_gpio_mode(reset[i].pin, GL_PIN_MODE_OUTPUT_PP);
        }
    }
    /* CHG_INHIBIT and NTC_BIAS stay analog: the charger keeps its hardware
     * default until drivers/power has a reason to stop it (gl_hal.h) */
    /* 3. inputs without an internal pull; the buses to their peripherals */
    gl_hal_gpio_mode(GL_PIN_CHG_STAT, GL_PIN_MODE_INPUT);
    gl_hal_gpio_mode(GL_PIN_VBUS_SENSE, GL_PIN_MODE_INPUT);
    gl_hal_gpio_mode(GL_PIN_IMU_INT1, GL_PIN_MODE_INPUT);
    gl_hal_gpio_mode(GL_PIN_IMU_INT2, GL_PIN_MODE_INPUT);
    for (size_t i = 0; i < sizeof(alt) / sizeof(alt[0]); i++) {
        gl_hal_gpio_mode(alt[i], GL_PIN_MODE_ALTERNATE);
    }
    S.irq_enabled = 0;
    S.irq_pending = 0;
    S.inited = true;
    S.mcu_mode = (uint8_t)SIM_MCU_RUN;
    S.wdg_last_kick = S.now_us;
    charger_update_();
    return GL_OK;
}

void gl_hal_ship_mode_enter(void)
{
    if (S.pin[GL_PIN_VBUS_SENSE].ext) {
        /* the wake-up is an edge: with VBUS present there would be none */
        sim_trace(GL_SIM_TR_SHIP, 0, 0, 0, 0);
        return;
    }
    /* what the caller must have switched off (gl_hal.h) */
    if (sim_pin_out_high(GL_PIN_LCD_DISP) || S.extcomin_on) {
        sim_violation(&S.viol.stop_mode, "ship mode entered with the display on");
    }
    if (S.rail_on || S.usb_started || S.usb_standby || S.adc_on || S.opamp_on) {
        sim_violation(&S.viol.stop_mode, "ship mode entered with the camera rail, USB, the ADC or "
                                         "the op-amp on");
    }
    if (cs_asserted_(GL_PIN_LCD_SCS) || cs_asserted_(GL_PIN_FLASH_CS) || cs_asserted_(GL_PIN_IMU_CS)) {
        sim_violation(&S.viol.stop_mode, "ship mode entered with a chip select asserted");
    }
    if (sim_pin_out_high(GL_PIN_NTC_BIAS)) {
        sim_violation(&S.viol.stop_mode, "ship mode entered with NTC_BIAS driven");
    }
    if (inhibit_on_()) {
        sim_violation(&S.viol.power, "ship mode entered with CHG_INHIBIT driven high");
    }
    if (S.clock == (uint8_t)GL_CLOCK_FAST) {
        sim_violation(&S.viol.clock, "ship mode entered with the fast core clock");
    }
    sim_trace(GL_SIM_TR_SHIP, 1, 0, 0, 0);
    mcu_pins_release_();
    S.shutdown = true;
    S.ship_marker = true;
    S.shutdown_since = S.now_us;
    S.rtc_base_s = 0; /* the low-speed oscillator stops: the clock is "not set" afterwards */
    S.stats.ship_entries++;
}

uint32_t gl_hal_reset_reason(void)
{
    uint32_t r = S.reset_reason;
    S.reset_reason = 0;
    return r;
}

void gl_hal_reboot(gl_reboot_t how)
{
    if (how == GL_REBOOT_ROM_DFU) {
        /* rev E board (firmware note 11 of the pin map): the IMU's INT1 and
         * INT2 are the ROM loader's SPI1 data and clock inputs.  They must be
         * STATIC when the ROM starts: no interrupt routed, and the display
         * off (its pull-down takes DISP low at the reset anyway) */
        if (sim_imu_ints_routed()) {
            sim_violation(&S.viol.imu, "reboot to the ROM loader with an IMU interrupt still "
                                       "routed: INT1 / INT2 are the ROM's SPI1 inputs");
        }
    }
    S.boot_attempts_reg = 0; /* a reset made on purpose: not an unconfirmed start (E34) */
    S.stats.reboots++;
    S.stats.last_reboot = (uint8_t)how;
    sim_trace(GL_SIM_TR_REBOOT, (unsigned)how, 0, 0, 0);
}

void gl_hal_boot_confirm(void)
{
    S.boot_attempts_reg = 0;
    S.stats.boot_confirms++;
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

uint32_t gl_hal_time_us(void)
{
    return (uint32_t)S.now_us;
}

void gl_hal_trace(gl_trace_point_t point, uint32_t work)
{
    uint64_t instr, us;
    if ((unsigned)point >= (unsigned)GL_TRACE_COUNT) {
        return;
    }
    S.stats.trace_points[point]++;
    if (S.clock != (uint8_t)GL_CLOCK_FAST && point != GL_TRACE_RENDER) {
        S.stats.heavy_while_slow++; /* compute-heavy work at the slow clock */
    }
    instr = gl_sim_stage_instr(point, work);
    S.stats.stage_instr[point] += instr;
    if (S.compute_us[point] != 0u) {
        us = S.compute_us[point]; /* a time fixed by the test */
    } else {
        /* the cost model: instructions x cycles per instruction / core clock */
        const double hz = (S.clock == (uint8_t)GL_CLOCK_FAST) ? (double)GL_SIM_CLOCK_FAST_HZ
                                                              : (double)GL_SIM_CLOCK_SLOW_HZ;
        us = (uint64_t)((double)instr * (double)cpi_ * 1.0e6 / hz + 0.5);
    }
    if (us != 0u) {
        /* the computation that has just ended took this long (the MCU ran) */
        S.stats.compute_us += us;
        S.stats.stage_us[point] += us;
        run_until_(S.now_us + us);
    }
}

void gl_hal_delay_ms(uint32_t ms)
{
    /* (the core sleeps between ticks: gl_hal.h) */
    const uint8_t mode = S.mcu_mode;
    S.mcu_mode = (uint8_t)SIM_MCU_IDLE;
    run_until_(S.now_us + (uint64_t)ms * 1000u);
    S.mcu_mode = mode;
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

gl_status_t gl_hal_clock_set(gl_clock_t speed)
{
    const uint8_t before = S.clock;
    S.stats.clock_calls++;
    sim_trace(GL_SIM_TR_CLOCK, (unsigned)speed, before, 0, 0);
    if (speed == GL_CLOCK_FAST && before != (uint8_t)GL_CLOCK_FAST) {
        if (S.clock_fail > 0u) {
            S.clock_fail--;
            return GL_ERR_IO; /* the PLL did not lock: still slow */
        }
        run_until_(S.now_us + SIM_PLL_LOCK_US);
        S.clock = (uint8_t)GL_CLOCK_FAST;
        S.clock_fast_since = S.now_us;
        S.stats.clock_to_fast++;
    } else if (speed != GL_CLOCK_FAST && before == (uint8_t)GL_CLOCK_FAST) {
        if (S.clock_fail_slow > 0u) {
            S.clock_fail_slow--;
            return GL_ERR_IO; /* the switch back did not take place: still fast */
        }
        S.stats.clock_fast_us += S.now_us - S.clock_fast_since;
        S.clock = (uint8_t)GL_CLOCK_SLOW;
        S.stats.clock_to_slow++;
    }
    return GL_OK;
}

gl_clock_t gl_hal_clock_get(void)
{
    return (gl_clock_t)S.clock;
}

#define SIM_STOP_WAKE_MASK                                                                      \
    (GL_IRQ_IMU_INT1 | GL_IRQ_IMU_INT2 | GL_IRQ_VBUS_CHANGE | GL_IRQ_CHG_STAT | GL_IRQ_WAKE_TIMER | \
     GL_IRQ_USB_WAKE)

uint32_t gl_hal_sleep(gl_sleep_mode_t mode)
{
    uint64_t t0 = S.now_us;
    uint32_t wake_mask = (mode == GL_SLEEP_STOP) ? SIM_STOP_WAKE_MASK : 0xFFFFFFFFu;

    /* board rules that hold at every sleep: by the time the main loop goes
     * to sleep it must have dealt with a VBUS that went away */
    if ((S.usb_started || S.usb_standby) && !S.vbus_pad) {
        sim_violation(&S.viol.power, "USB still on with VBUS absent (its supply pin unpowered)");
    }
    if (mode == GL_SLEEP_STOP) {
        const bool vbus = S.pin[GL_PIN_VBUS_SENSE].ext;
        if (!vbus && inhibit_on_()) {
            sim_violation(&S.viol.power, "Stop mode with CHG_INHIBIT driven high and no VBUS: a "
                                         "stop left behind by a sleeping MCU");
        }
        if (vbus && (S.wake_timer_at == SIM_NEVER ||
                     S.wake_timer_at - S.now_us > (uint64_t)GL_SIM_CHG_SUPERVISE_MAX_MS * 1000u)) {
            sim_violation(&S.viol.power, "Stop mode in the cradle with no wake-up within %u s: "
                                         "nobody supervises the charge",
                          (unsigned)(GL_SIM_CHG_SUPERVISE_MAX_MS / 1000u));
        }
        if (sim_pin_out_high(GL_PIN_NTC_BIAS)) {
            sim_violation(&S.viol.analog, "Stop mode with NTC_BIAS still driven");
        }
        if (S.clock == (uint8_t)GL_CLOCK_FAST) {
            sim_violation(&S.viol.clock, "Stop mode with the fast core clock (PLL on)");
        }
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
    S.mcu_mode = (uint8_t)((mode == GL_SLEEP_STOP) ? SIM_MCU_STOP : SIM_MCU_IDLE);
    while ((S.irq_pending & wake_mask) == 0u) {
        uint64_t t = next_event_();
        if (t == SIM_NEVER) {
            sim_violation(&S.viol.deadlock, "gl_hal_sleep(%d) with no event that could wake it",
                          (int)mode);
            break;
        }
        run_until_(t);
    }
    S.mcu_mode = (uint8_t)SIM_MCU_RUN;
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
    if (S.spi_fail_count[bus] > 0u) {
        S.spi_fail_count[bus]--;
        return S.spi_fail_status[bus]; /* injected fault (gl_sim_spi_fail) */
    }
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
        /* rev E: the mid-rail bias of the stage is a divider fed from the
         * LCD_DISP line (it draws nothing asleep): DISP must be high, and
         * must have been for GL_PINS_GRAIN_BIAS_DISP_MS */
        if (!sim_pin_out_high(GL_PIN_LCD_DISP)) {
            sim_violation(&S.viol.analog, "grain conversion with LCD_DISP low: the bias divider "
                                          "is not fed");
        } else {
            const uint64_t since = S.now_us - S.disp_high_since;
            if (since < S.stats.grain_bias_short_us) {
                S.stats.grain_bias_short_us = since;
            }
            if (since < (uint64_t)GL_PINS_GRAIN_BIAS_DISP_MS * 1000u) {
                sim_violation(&S.viol.analog, "grain conversion %u ms after LCD_DISP went high "
                                              "(the bias needs %u ms)", (unsigned)(since / 1000u),
                              (unsigned)GL_PINS_GRAIN_BIAS_DISP_MS);
            }
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
    case GL_ADC_CH_CELL_NTC: {
        /* ratiometric: the divider is fed from a GPIO at VDDA */
        double x;
        if (S.ntc_fault == (uint8_t)GL_SIM_NTC_STUCK_HIGH) {
            x = 1.0;
        } else if (!sim_pin_out_high(GL_PIN_NTC_BIAS)) {
            /* bias released: the NTC holds the pin at ground; a pin with no
             * NTC floats somewhere */
            x = (S.ntc_fault == (uint8_t)GL_SIM_NTC_OPEN) ? 0.4 : 0.0;
        } else if (S.ntc_fault == (uint8_t)GL_SIM_NTC_OPEN) {
            x = 1.0;
        } else if (S.ntc_fault == (uint8_t)GL_SIM_NTC_SHORT) {
            x = 0.0;
        } else {
            const uint64_t since = S.now_us - S.ntc_bias_since;
            x = ntc_fraction_((double)cell_temp_());
            if (since < SIM_NTC_SETTLE_MIN_US) {
                sim_violation(&S.viol.analog, "NTC conversion %u us after the bias was switched on",
                              (unsigned)since);
                x *= 1.0 - exp(-(double)since / SIM_NTC_TAU_US);
            }
            S.stats.ntc_reads++;
        }
        v = (float)(x * (double)GL_HAL_ADC_FULL_SCALE);
        break;
    }
    case GL_ADC_CH_MCU_TEMP:
    default: {
        const float t = S.mcu_temp_pinned ? S.mcu_temp_c : sim_imu_temperature();
        v = (SIM_TS_CAL_30C + (t - 30.0f) * SIM_TS_COUNTS_PER_K) * SIM_TS_CAL_VDDA_MV /
            (float)S.vdda_mv;
        noise = 2.0f;
        break;
    }
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

float gl_hal_adc_mcu_temp_c(uint16_t counts, uint16_t vdda_mv)
{
    const float at_cal = (float)counts * (float)vdda_mv / SIM_TS_CAL_VDDA_MV;
    return 30.0f + (at_cal - SIM_TS_CAL_30C) / SIM_TS_COUNTS_PER_K;
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

bool gl_hal_usb_supply_ok(void)
{
    /* VBUS_SENSE high AND the MCU's own monitor of its USB supply pin (rev E:
     * a regulator fed from VBUS and enabled by the 2.8 V rail) */
    return S.pin[GL_PIN_VBUS_SENSE].ext && S.vbus_pad;
}

gl_status_t gl_hal_usb_start(void)
{
    if (!gl_hal_usb_supply_ok()) {
        sim_trace(GL_SIM_TR_USB, 2, 0, 0, 0); /* refused: no supply */
        return GL_ERR_STATE;
    }
    S.usb_started = true;
    S.usb_standby = false; /* back from standby: same configuration, no new enumeration */
    sim_trace(GL_SIM_TR_USB, 1, 0, 0, 0);
    if (S.usb_rx_len > 0u) {
        sim_irq_raise(GL_IRQ_USB_RX);
    }
    return GL_OK;
}

void gl_hal_usb_stop(void)
{
    S.usb_started = false;
    S.usb_standby = false;
    S.usb_rx_len = 0;
    S.irq_pending &= ~(GL_IRQ_USB_RX | GL_IRQ_USB_WAKE);
    sim_trace(GL_SIM_TR_USB, 0, 0, 0, 0);
}

gl_usb_bus_t gl_hal_usb_bus(void)
{
    return (S.usb_started || S.usb_standby) ? (gl_usb_bus_t)S.usb_bus : GL_USB_BUS_NONE;
}

gl_status_t gl_hal_usb_standby(void)
{
    if (!S.usb_started || S.usb_bus != (uint8_t)GL_USB_BUS_SUSPENDED) {
        sim_trace(GL_SIM_TR_USB_STANDBY, 0, 0, 0, 0);
        return GL_ERR_STATE; /* not started, no host, or a host that is talking */
    }
    S.usb_started = false;
    S.usb_standby = true;
    S.irq_pending &= ~GL_IRQ_USB_RX;
    sim_trace(GL_SIM_TR_USB_STANDBY, 1, 0, 0, 0);
    return GL_OK;
}

bool gl_hal_usb_connected(void)
{
    return S.usb_started && S.usb_host_open && S.usb_bus == (uint8_t)GL_USB_BUS_ACTIVE;
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
