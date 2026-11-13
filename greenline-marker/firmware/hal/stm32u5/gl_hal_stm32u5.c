/*
 * gl_hal_stm32u5.c - STM32U585RIT6 backend of hal/gl_hal.h, written against
 * the STM32Cube HAL API (STM32CubeU5, stm32u5xx_hal.h).
 *
 * ##########################################################################
 * #  THIS FILE HAS BEEN COMPILED - AND NEVER LINKED, NEVER RUN.            #
 * #  `make cross-hal STM32_HEADERS=<dir>` compiles it (compile only),      #
 * #  warning-free with the firmware's whole warning set, against ST's and  #
 * #  Arm's header files (README, "STM32 backend": which files, which       #
 * #  release tags).  That shows that every identifier used here exists     #
 * #  with the type it is used with.  It shows NOTHING about behaviour: no  #
 * #  HAL source was compiled, no image was linked, and no board exists.    #
 * #  It was written from the HAL API and the reference-manual behaviour as #
 * #  remembered: treat every SEQUENCE in it as unverified until it has run #
 * #  on hardware.  `make cross` does NOT compile it.                       #
 * ##########################################################################
 *
 * What it needs around it (not in this repository): the CMSIS device files
 * and startup code (startup_stm32u585xx.s, system_stm32u5xx.c), a linker
 * script, the HAL sources of the modules ADC, CORTEX, DCMI, DMA, EXTI,
 * FLASH, GPIO, ICACHE, IWDG, LPTIM, OPAMP, PCD, PWR, RCC, RTC, SPI (the
 * project's own stm32u5xx_hal_conf.h, next to this file, enables exactly
 * these), and - for gl_hal_stm32u5_usb.c, which is still uncompiled - ST's
 * USB device library with its CDC class plus the usual usbd_conf.c /
 * usbd_desc.c glue.  README, "STM32 backend", lists what a flashable image
 * takes.
 *
 * DESIGN
 *   clocks    SLOW (the state after init and after every Stop): MSIS 48 MHz
 *             is the system clock, no PLL (fast wake-up from Stop 2),
 *             trimmed against the 32.768 kHz crystal (MSI PLL mode).
 *             FAST (gl_hal_clock_set(GL_CLOCK_FAST), DESIGN_SPEC rev C2:
 *             160 MHz during a read): PLL1 from MSIS, 48 MHz / 3 x 20 / 2 =
 *             160 MHz, which needs voltage range 1, the EPOD booster and 4
 *             flash wait states; switching back stops the PLL and returns
 *             to range 3.  NOTHING else follows the core clock: SPI1, SPI2
 *             and the ADC take their kernel clock from MSIK (48 MHz, on in
 *             both states), XVCLK = MSIS / 4 = 12 MHz on MCO, the tick, the
 *             wake-up timer and EXTCOMIN run from LSE, USB from HSI48 with
 *             the clock-recovery system (PROVISIONAL in DESIGN_SPEC:
 *             crystal-less USB); gl_hal_delay_us() scales its cycle count
 *             with the clock in effect.  WRITTEN BY INSPECTION like the rest
 *             of this file: the PLL / booster sequence in particular is from
 *             memory of RM0456 and of generated code, and has never run.
 *   tick      LPTIM3, clocked by LSE, free running 16 bit at 32768 Hz with
 *             an overflow interrupt every 2 s; it keeps counting in Stop 2,
 *             so gl_hal_tick_ms() is monotonic through sleep.
 *   wake      RTC wake-up timer (LSE).
 *   EXTCOMIN  LPTIM1 channel 1 PWM from LSE, autonomous in Stop 2.
 *   SCCB      bit-banged on three open-drain GPIOs (two clock lines for two
 *             sensors at one address: no I2C peripheral can do that).
 *   DCMI      snapshot of one frame with crop and byte select, GPDMA
 *             channel 0, 32-bit words.  Both strip sizes used by the
 *             application (61440 and 46080 bytes) are below the 65535-byte
 *             block limit of one GPDMA transfer BY DESIGN and are multiples
 *             of 4.
 *   interrupts  handlers only latch a bit in a pending mask (and the
 *             DCMI / USB handlers move data); the main loop does the work.
 *             EVERY read-modify-write of that mask is done with interrupts
 *             masked (PRIMASK), in thread context AND in the handlers: the
 *             handlers run at two priorities (RTC, LPTIM3, DCMI, DMA at 1;
 *             EXTI at 2), so one can preempt another in the middle of an
 *             update, and thread code clears bits (review finding: a lost
 *             latch stopped the IMU sample pump).  The application does
 *             not rely on it alone: it also polls the data-ready line.
 *   guards    every stop / disable function returns at once if its
 *             peripheral was never started (gl_hal.h requires stop before
 *             start to be safe; the HAL de-initialisation functions write
 *             through handle->Instance, which is NULL in a zeroed handle).
 *
 * IDENTIFIERS.  The names that were written from memory are collected in
 * the "identifier map" below.  The first compile against the headers found
 * two that do not exist in this form (the VREFINT macro takes the ADC
 * instance as its first argument; the op-amp power mode is
 * OPAMP_POWERMODE_NORMALPOWER_NORMALSPEED) and two that exist only as
 * aliases in ST's legacy header (GPDMA1_REQUEST_DCMI,
 * ADC_SAMPLETIME_391CYCLES_5); all four are corrected.  The MEANING of the
 * map's entries was then compared with the comments of the headers (MSI
 * range 0 = 48 MHz, the PLL input range, the DCMI byte-select constants,
 * the ADC sampling times, the RTC wake-up clock, the calibration values at
 * 14 bits and 3.0 V).  STILL FROM MEMORY, because no header says it: the
 * ADC channel numbers of PA2 and PC4 (data sheet, table of pin functions),
 * the system-memory address of the ROM bootloader (AN2606), the order of
 * the PLL / booster / flash-latency steps (RM0456), and everything listed
 * next.
 *
 * BEHAVIOUR TO CONFIRM ON HARDWARE (the application depends on it):
 *   - LPTIM1 keeps toggling its PWM pin in Stop 2 (GL_PROV_LPTIM_PWM_RUNS_IN_STOP2)
 *   - LPTIM3 keeps counting in Stop 2 (the tick), the RTC wake-up timer and
 *     the four EXTI lines wake the core from Stop 2, and the wake-up from
 *     Stop 2 is fast enough for a 240 Hz data-ready interrupt
 *   - the DCMI crop / byte-select order and the meaning of the sync
 *     polarity bits (comments at gl_hal_dcmi_start)
 *   - the independent watchdog keeps running in Stop 2 (the application
 *     wakes every 16 s to refresh it)
 */
#include "stm32u5xx_hal.h"

#include <string.h>

#include "gl_hal.h"
#include "gl_hal_stm32u5_priv.h"
#include "gl_pins.h"
#include "gl_provisional.h"

/* ======================================================================= */
/* identifier map (see the file comment)                                    */
/* ======================================================================= */

#define GLH_MSI_RANGE_48MHZ      RCC_MSIRANGE_0          /* MSIS range 0 = 48 MHz */
#define GLH_FLASH_LATENCY_48MHZ  FLASH_LATENCY_3         /* voltage range 3: 12.5 MHz per wait state */
#define GLH_VOLTAGE_SCALE        PWR_REGULATOR_VOLTAGE_SCALE3
#define GLH_MCO_SRC_MSI          RCC_MCO1SOURCE_MSI
#define GLH_MCO_SRC_NONE         RCC_MCO1SOURCE_NOCLOCK
#define GLH_DCMI_DMA_REQUEST     GPDMA1_REQUEST_DCMI_PSSI /* (GPDMA1_REQUEST_DCMI is only a legacy alias) */
#define GLH_DCMI_BSM_ALL         DCMI_BSM_ALL
#define GLH_DCMI_BSM_EVERY_OTHER DCMI_BSM_OTHER          /* keep 1 byte out of 2 */
#define GLH_DCMI_OEBS_FIRST      DCMI_OEBS_ODD           /* keep the 1st byte of each pair */
#define GLH_DCMI_OEBS_SECOND     DCMI_OEBS_EVEN          /* keep the 2nd byte of each pair */
#define GLH_ADC_SMP_SHORT        ADC_SAMPLETIME_12CYCLES     /*   1.0 us at 12 MHz */
#define GLH_ADC_SMP_MEDIUM       ADC_SAMPLETIME_68CYCLES     /*   5.7 us */
#define GLH_ADC_SMP_LONG         ADC_SAMPLETIME_391CYCLES    /*  32.6 us (the _5 name is a legacy alias) */
#define GLH_ADC_SMP_LONGEST      ADC_SAMPLETIME_814CYCLES    /*  67.8 us */
/* ADC channels: the NUMBERS are in the generated gl_pins.h (tools/gen_pins.py),
 * nowhere else: PA3 = OPAMP1_VOUT = ADC1_IN8 (verified), PA2 = ADC1_IN7 and
 * PC4 = ADC1_IN13 (both from memory) */
#define GLH_ADC_CHANNEL__(n)     ADC_CHANNEL_##n
#define GLH_ADC_CHANNEL_(n)      GLH_ADC_CHANNEL__(n)
#define GLH_ADC_CH_GRAIN         GLH_ADC_CHANNEL_(GL_PINS_ADC_CH_GRAIN_TIA)
#define GLH_ADC_CH_VBAT          GLH_ADC_CHANNEL_(GL_PINS_ADC_CH_VBAT_DIV)
#define GLH_ADC_CH_NTC           GLH_ADC_CHANNEL_(GL_PINS_ADC_CH_CELL_NTC)
/* fast clock: PLL1 from MSIS 48 MHz -> 16 MHz -> VCO 320 MHz -> 160 MHz */
#define GLH_PLL_M                3u
#define GLH_PLL_N                20u
#define GLH_PLL_R                2u
#define GLH_PLL_VCI_RANGE        RCC_PLLVCIRANGE_1       /* 8..16 MHz at the phase detector */
#define GLH_PLL_MBOOST           RCC_PLLMBOOST_DIV4      /* EPOD booster clock 48 / 4 = 12 MHz (4..16 MHz allowed) */
#define GLH_VOLTAGE_SCALE_FAST   PWR_REGULATOR_VOLTAGE_SCALE1 /* needed above 110 MHz */
#define GLH_FLASH_LATENCY_160MHZ FLASH_LATENCY_4         /* range 1: 32 MHz per wait state */
#define GLH_MSIK_RANGE_48MHZ     RCC_MSIKRANGE_0         /* MSIK 48 MHz: SPI and ADC kernel clock */
#define GLH_ROM_BOOTLOADER_ADDR  0x0BF90000u             /* AN2606, STM32U575/585 (from memory) */
#define GLH_DFU_MAGIC            0x474C4446u             /* "GLDF" in TAMP backup register 0 */
#define GLH_RTC_SET_MAGIC        0x474C5254u             /* "GLRT" in backup register 1: RTC has been set */

#define GLH_LSE_HZ 32768u
#define GLH_SYSCLK_HZ 48000000u      /* SLOW core clock, and the MSIK kernel clock in both states */
#define GLH_SYSCLK_FAST_HZ 160000000u
#define GLH_IWDG_RELOAD 4000u /* LSI 32 kHz / 256 = 125 Hz -> 32 s */

/* ======================================================================= */
/* pin table (expanded from the generated gl_pins.h)                        */
/* ======================================================================= */

typedef struct {
    GPIO_TypeDef *port;
    uint16_t mask;
    uint8_t fn; /* GL_PINFN_* */
    uint8_t af;
} glh_pin_t;

#define GLH_ROW(logical, port_letter, pin_no, pad, fn_kind, af_no, src) \
    [logical] = { GPIO##port_letter, (uint16_t)(1u << (pin_no)), (uint8_t)(fn_kind), (uint8_t)(af_no) },
static const glh_pin_t pin_[GL_PIN_COUNT] = { GL_PINS_TABLE(GLH_ROW) };

/* The interrupt vectors (EXTI13 / 5 / 9 / 0), their NVIC lines and the EXTI
 * callback further down name four pins by their line NUMBER.  The numbers
 * come from the generated pin table: if tools/gen_pins.py moves one of the
 * four pins, this stops compiling instead of silently listening on the old
 * line. */
#define GLH_LINE(logical, port_letter, pin_no, pad, fn_kind, af_no, src) GLH_LINE_##logical = (pin_no),
enum { GL_PINS_TABLE(GLH_LINE) GLH_LINE_COUNT_ };
typedef char glh_imu_int1_is_exti13_[(GLH_LINE_GL_PIN_IMU_INT1 == 13) ? 1 : -1];
typedef char glh_imu_int2_is_exti5_[(GLH_LINE_GL_PIN_IMU_INT2 == 5) ? 1 : -1];
typedef char glh_vbus_sense_is_exti9_[(GLH_LINE_GL_PIN_VBUS_SENSE == 9) ? 1 : -1];
typedef char glh_chg_stat_is_exti0_[(GLH_LINE_GL_PIN_CHG_STAT == 0) ? 1 : -1];

static bool latch_[GL_PIN_COUNT];
static uint8_t mode_[GL_PIN_COUNT];

/* ======================================================================= */
/* handles and state                                                        */
/* ======================================================================= */

static SPI_HandleTypeDef hspi_[GL_SPI_BUS_COUNT];
static gl_spi_cfg_t spi_cfg_[GL_SPI_BUS_COUNT];
static bool spi_ready_[GL_SPI_BUS_COUNT];
static DCMI_HandleTypeDef hdcmi_;
static DMA_HandleTypeDef hdma_dcmi_;
static ADC_HandleTypeDef hadc_;
static OPAMP_HandleTypeDef hopamp_;
static LPTIM_HandleTypeDef hlptim1_; /* EXTCOMIN */
static LPTIM_HandleTypeDef hlptim3_; /* tick */
static RTC_HandleTypeDef hrtc_;
static IWDG_HandleTypeDef hiwdg_;

static volatile uint32_t irq_pending_;
static volatile uint32_t irq_enabled_;
static volatile uint32_t tick_overflows_; /* LPTIM3 wraps (2 s each) */
static uint32_t irq_lock_depth_;
static uint32_t reset_flags_;
static bool adc_on_;

static volatile gl_dcmi_state_t dcmi_state_ = GL_DCMI_IDLE;
static size_t dcmi_expect_;
static uint32_t dcmi_deadline_ms_;
static volatile uint32_t dcmi_done_us_; /* gl_hal_time_us() at the frame-end interrupt */
static bool extcomin_on_;               /* LPTIM1 initialised and running */
static bool opamp_on_;                  /* OPAMP1 initialised and running */

/* Latch interrupt-source bits.  Called from handlers of two priorities and
 * from thread context: the update is one critical section, so no bit set by
 * a preempting handler between the load and the store can be lost. */
static void raise_(uint32_t bit)
{
    const uint32_t primask = __get_PRIMASK();
    __disable_irq();
    irq_pending_ |= bit & irq_enabled_;
    if (primask == 0u) {
        __enable_irq();
    }
}

/* Clear latched bits (thread context), atomically for the same reason. */
static void clear_pending_(uint32_t bits)
{
    const uint32_t primask = __get_PRIMASK();
    __disable_irq();
    irq_pending_ &= ~bits;
    if (primask == 0u) {
        __enable_irq();
    }
}

/* For gl_hal_stm32u5_usb.c (received bytes). */
void glh_irq_raise(uint32_t bit)
{
    raise_(bit);
}

/* ======================================================================= */
/* clocks                                                                   */
/* ======================================================================= */

/* Core clock in effect (gl_hal_delay_us scales with it). */
static gl_clock_t clock_ = GL_CLOCK_SLOW;
static uint32_t sysclk_hz_ = GLH_SYSCLK_HZ;
/* false: the 32.768 kHz crystal did not start (or stopped).  The low-speed
 * side then runs from LSI: the tick, the RTC and EXTCOMIN are about 2.4 %
 * slow (LSI is nominally 32.000 kHz, and is not trimmed), MSIS is not
 * locked.  DEGRADED but alive: gl_hal_init() reports GL_ERR_TIMEOUT once,
 * the application shows it and carries on.  Stays false until the next
 * reset.  BY INSPECTION ONLY, like everything in this file. */
static bool lse_ok_ = true;

static HAL_StatusTypeDef clocks_osc_(bool with_lse)
{
    RCC_OscInitTypeDef osc;
    /* LSE (32.768 kHz, 6 pF crystal: low drive) and MSIS 48 MHz locked to it */
    memset(&osc, 0, sizeof(osc));
    osc.OscillatorType = RCC_OSCILLATORTYPE_LSE | RCC_OSCILLATORTYPE_MSI | RCC_OSCILLATORTYPE_LSI |
                         RCC_OSCILLATORTYPE_MSIK;
    osc.LSEState = with_lse ? RCC_LSE_ON : RCC_LSE_OFF;
    osc.LSIState = RCC_LSI_ON; /* independent watchdog; the low-speed clock without LSE */
    osc.MSIState = RCC_MSI_ON;
    osc.MSICalibrationValue = RCC_MSICALIBRATION_DEFAULT;
    osc.MSIClockRange = GLH_MSI_RANGE_48MHZ;
    /* MSIK: the kernel clock of SPI1, SPI2 and the ADC, so that their
     * timing does not move when the core clock is switched */
    osc.MSIKState = RCC_MSIK_ON;
    osc.MSIKClockRange = GLH_MSIK_RANGE_48MHZ;
    osc.PLL.PLLState = RCC_PLL_NONE;
    return HAL_RCC_OscConfig(&osc);
}

/* Returns GL_OK when the system clock tree is up - WITH OR WITHOUT the
 * crystal (lse_ok_ says which).  GL_ERR_IO only if the internal oscillators
 * themselves could not be configured. */
static gl_status_t clocks_init_(void)
{
    RCC_ClkInitTypeDef clk;
    RCC_PeriphCLKInitTypeDef pclk;

    clock_ = GL_CLOCK_SLOW;
    sysclk_hz_ = GLH_SYSCLK_HZ;

    __HAL_RCC_PWR_CLK_ENABLE();
    HAL_PWR_EnableBkUpAccess();
    if (HAL_PWREx_ControlVoltageScaling(GLH_VOLTAGE_SCALE) != HAL_OK) {
        return GL_ERR_IO;
    }
    /* The crystal is the one external part of the clock tree and the one
     * that can fail to start (LSE_STARTUP_TIMEOUT, 5 s).  That must not take
     * the device down: without a tick the application's first delay would
     * never return.  Fall back to LSI and say so. */
    if (lse_ok_ && clocks_osc_(true) != HAL_OK) {
        lse_ok_ = false;
    }
    if (!lse_ok_ && clocks_osc_(false) != HAL_OK) {
        return GL_ERR_IO;
    }
    if (lse_ok_) {
        HAL_RCCEx_EnableMSIPLLMode(); /* trim MSI against LSE */
    }

    memset(&clk, 0, sizeof(clk));
    clk.ClockType = RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_PCLK1 |
                    RCC_CLOCKTYPE_PCLK2 | RCC_CLOCKTYPE_PCLK3;
    clk.SYSCLKSource = RCC_SYSCLKSOURCE_MSI;
    clk.AHBCLKDivider = RCC_SYSCLK_DIV1;
    clk.APB1CLKDivider = RCC_HCLK_DIV1;
    clk.APB2CLKDivider = RCC_HCLK_DIV1;
    clk.APB3CLKDivider = RCC_HCLK_DIV1;
    if (HAL_RCC_ClockConfig(&clk, GLH_FLASH_LATENCY_48MHZ) != HAL_OK) {
        return GL_ERR_IO;
    }
    /* wake from Stop on MSI, keeping its range */
    __HAL_RCC_WAKEUPSTOP_CLK_CONFIG(RCC_STOP_WAKEUPCLOCK_MSI);

    /* kernel clocks: LPTIM1 and LPTIM3 from LSE (they must run in Stop 2),
     * RTC from LSE; ADC, SPI1 and SPI2 from MSIK (48 MHz whatever the core
     * clock is: gl_hal.h promises that bit rates and ADC timing do not
     * change with gl_hal_clock_set) */
    memset(&pclk, 0, sizeof(pclk));
    pclk.PeriphClockSelection = RCC_PERIPHCLK_LPTIM1 | RCC_PERIPHCLK_LPTIM34 | RCC_PERIPHCLK_RTC |
                                RCC_PERIPHCLK_ADCDAC | RCC_PERIPHCLK_SPI1 | RCC_PERIPHCLK_SPI2;
    pclk.Lptim1ClockSelection = lse_ok_ ? RCC_LPTIM1CLKSOURCE_LSE : RCC_LPTIM1CLKSOURCE_LSI;
    pclk.Lptim34ClockSelection = lse_ok_ ? RCC_LPTIM34CLKSOURCE_LSE : RCC_LPTIM34CLKSOURCE_LSI;
    pclk.RTCClockSelection = lse_ok_ ? RCC_RTCCLKSOURCE_LSE : RCC_RTCCLKSOURCE_LSI;
    pclk.AdcDacClockSelection = RCC_ADCDACCLKSOURCE_MSIK;
    pclk.Spi1ClockSelection = RCC_SPI1CLKSOURCE_MSIK;
    pclk.Spi2ClockSelection = RCC_SPI2CLKSOURCE_MSIK;
    if (HAL_RCCEx_PeriphCLKConfig(&pclk) != HAL_OK) {
        return GL_ERR_IO;
    }
    return GL_OK;
}

/* ---- core clock: SLOW (MSIS 48 MHz) <-> FAST (PLL1 160 MHz) ----------------------
 * BY INSPECTION ONLY.  Order when going up: voltage range 1 (with the EPOD
 * booster, which the U5 HAL enables from PLLMBOOST when the PLL is the
 * system clock - from memory), PLL on and locked, then SYSCLK with the
 * higher flash latency.  Order when going down: SYSCLK back to MSIS first,
 * then PLL off, then the lower voltage range.  HAL_RCC_ClockConfig() updates
 * SystemCoreClock and the HAL's SysTick time base itself. */
static gl_status_t clock_fast_(void)
{
    RCC_OscInitTypeDef osc;
    RCC_ClkInitTypeDef clk;

    if (HAL_PWREx_ControlVoltageScaling(GLH_VOLTAGE_SCALE_FAST) != HAL_OK) {
        return GL_ERR_IO;
    }
    memset(&osc, 0, sizeof(osc));
    osc.OscillatorType = RCC_OSCILLATORTYPE_NONE;
    osc.PLL.PLLState = RCC_PLL_ON;
    osc.PLL.PLLSource = RCC_PLLSOURCE_MSI;
    osc.PLL.PLLMBOOST = GLH_PLL_MBOOST;
    osc.PLL.PLLM = GLH_PLL_M;
    osc.PLL.PLLN = GLH_PLL_N;
    osc.PLL.PLLP = 2;
    osc.PLL.PLLQ = 2;
    osc.PLL.PLLR = GLH_PLL_R;
    osc.PLL.PLLRGE = GLH_PLL_VCI_RANGE;
    osc.PLL.PLLFRACN = 0;
    if (HAL_RCC_OscConfig(&osc) != HAL_OK) {
        (void)HAL_PWREx_ControlVoltageScaling(GLH_VOLTAGE_SCALE);
        return GL_ERR_IO; /* no lock: still on MSIS */
    }
    memset(&clk, 0, sizeof(clk));
    clk.ClockType = RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_PCLK1 |
                    RCC_CLOCKTYPE_PCLK2 | RCC_CLOCKTYPE_PCLK3;
    clk.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
    clk.AHBCLKDivider = RCC_SYSCLK_DIV1;
    clk.APB1CLKDivider = RCC_HCLK_DIV1; /* the APB buses take 160 MHz on this family */
    clk.APB2CLKDivider = RCC_HCLK_DIV1;
    clk.APB3CLKDivider = RCC_HCLK_DIV1;
    if (HAL_RCC_ClockConfig(&clk, GLH_FLASH_LATENCY_160MHZ) != HAL_OK) {
        (void)clocks_init_(); /* back to a known state: MSIS, PLL off */
        return GL_ERR_IO;
    }
    clock_ = GL_CLOCK_FAST;
    sysclk_hz_ = GLH_SYSCLK_FAST_HZ;
    return GL_OK;
}

/* Returns GL_ERR_IO if the switch back to MSIS did not take place: the core
 * then STILL runs from the PLL in voltage range 1, and this module keeps
 * saying so (clock_ stays FAST, the PLL and the range are left alone).  The
 * application retries; it never enters Stop mode with the fast clock. */
static gl_status_t clock_slow_(void)
{
    RCC_OscInitTypeDef osc;
    RCC_ClkInitTypeDef clk;

    memset(&clk, 0, sizeof(clk));
    clk.ClockType = RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_PCLK1 |
                    RCC_CLOCKTYPE_PCLK2 | RCC_CLOCKTYPE_PCLK3;
    clk.SYSCLKSource = RCC_SYSCLKSOURCE_MSI;
    clk.AHBCLKDivider = RCC_SYSCLK_DIV1;
    clk.APB1CLKDivider = RCC_HCLK_DIV1;
    clk.APB2CLKDivider = RCC_HCLK_DIV1;
    clk.APB3CLKDivider = RCC_HCLK_DIV1;
    /* still in range 1 here: the latency of range 3 at 48 MHz is safe in both */
    if (HAL_RCC_ClockConfig(&clk, GLH_FLASH_LATENCY_48MHZ) != HAL_OK) {
        /* (the result used to be discarded: clock_ said SLOW, the PLL was
         * switched off under the running core and the voltage lowered) */
        return GL_ERR_IO;
    }
    clock_ = GL_CLOCK_SLOW;
    sysclk_hz_ = GLH_SYSCLK_HZ;
    memset(&osc, 0, sizeof(osc));
    osc.OscillatorType = RCC_OSCILLATORTYPE_NONE;
    osc.PLL.PLLState = RCC_PLL_OFF;
    (void)HAL_RCC_OscConfig(&osc);
    (void)HAL_PWREx_ControlVoltageScaling(GLH_VOLTAGE_SCALE);
    return GL_OK;
}

gl_status_t gl_hal_clock_set(gl_clock_t speed)
{
    if (speed == GL_CLOCK_FAST) {
        return (clock_ == GL_CLOCK_FAST) ? GL_OK : clock_fast_();
    }
    if (clock_ == GL_CLOCK_FAST) {
        return clock_slow_();
    }
    return GL_OK;
}

gl_clock_t gl_hal_clock_get(void)
{
    return clock_;
}

/* ======================================================================= */
/* ROM bootloader hand-over and reset bookkeeping                           */
/* ======================================================================= */

static void gpio_clocks_(void);

/* Called first thing after reset, before any clock or peripheral set-up:
 * if the previous run asked for the ROM DFU bootloader, jump to it. */
static void dfu_check_(void)
{
    __HAL_RCC_PWR_CLK_ENABLE();
    __HAL_RCC_RTCAPB_CLK_ENABLE();
    HAL_PWR_EnableBkUpAccess();
    if (TAMP->BKP0R == GLH_DFU_MAGIC) {
        const uint32_t *vectors = (const uint32_t *)GLH_ROM_BOOTLOADER_ADDR;
        void (*entry)(void);
        TAMP->BKP0R = 0; /* one attempt: the next reset boots the application */
        /* The ROM bootloader has no time-out and the consumer cradle has no
         * reset contact.  Enter it only with VBUS present (in the cradle);
         * with VBUS gone there is no USB host to talk to and the device
         * would sit in the bootloader until the cell is flat.  The pin is
         * read as a plain input: nothing else is configured yet.
         * LIMIT: a marker left in a powered cradle whose host never issues
         * a DFU "leave" stays in the bootloader until it is lifted out and
         * put back (a power cycle of VBUS alone does not reset the MCU) -
         * and it KEEPS CHARGING there: with the rev C2 circuit the charger
         * runs whenever VBUS is present, and in the ROM bootloader nobody
         * watches the cell temperature (CHG_INHIBIT is high-Z after the
         * reset).  The firmware only refuses to come here outside the
         * charging window (gl_usb.c).  README, charger state table: NOT MET
         * without hardware. */
        {
            const glh_pin_t *vb = &pin_[GL_PIN_VBUS_SENSE];
            GPIO_InitTypeDef g;
            gpio_clocks_();
            memset(&g, 0, sizeof(g));
            g.Pin = vb->mask;
            g.Mode = GPIO_MODE_INPUT;
            g.Pull = GPIO_NOPULL;
            HAL_GPIO_Init(vb->port, &g);
            if (HAL_GPIO_ReadPin(vb->port, vb->mask) != GPIO_PIN_SET) {
                return; /* not in the cradle: boot the application */
            }
        }
        entry = (void (*)(void))vectors[1];
        __set_MSP(vectors[0]);
        entry();
        for (;;) {
        }
    }
}

static uint32_t read_reset_flags_(void)
{
    uint32_t f = 0;
    if (__HAL_RCC_GET_FLAG(RCC_FLAG_BORRST)) {
        f |= GL_RESET_POWER_ON | GL_RESET_BROWNOUT; /* the U5 has one flag for both */
    }
    if (__HAL_RCC_GET_FLAG(RCC_FLAG_PINRST)) {
        f |= GL_RESET_PIN;
    }
    if (__HAL_RCC_GET_FLAG(RCC_FLAG_SFTRST)) {
        f |= GL_RESET_SOFTWARE;
    }
    if (__HAL_RCC_GET_FLAG(RCC_FLAG_IWDGRST) || __HAL_RCC_GET_FLAG(RCC_FLAG_WWDGRST)) {
        f |= GL_RESET_WATCHDOG;
    }
    __HAL_RCC_CLEAR_RESET_FLAGS();
    return f;
}

/* ======================================================================= */
/* tick (LPTIM3), RTC, delays                                               */
/* ======================================================================= */

static gl_status_t tick_init_(void)
{
    __HAL_RCC_LPTIM3_CLK_ENABLE();
    __HAL_RCC_LPTIM3_CLKAM_ENABLE(); /* autonomous mode: keeps its clock in Stop 2 */
    memset(&hlptim3_, 0, sizeof(hlptim3_));
    hlptim3_.Instance = LPTIM3;
    hlptim3_.Init.Clock.Source = LPTIM_CLOCKSOURCE_APBCLOCK_LPOSC;
    hlptim3_.Init.Clock.Prescaler = LPTIM_PRESCALER_DIV1;
    hlptim3_.Init.Trigger.Source = LPTIM_TRIGSOURCE_SOFTWARE;
    hlptim3_.Init.Period = 0xFFFFu;
    hlptim3_.Init.UpdateMode = LPTIM_UPDATE_IMMEDIATE;
    hlptim3_.Init.CounterSource = LPTIM_COUNTERSOURCE_INTERNAL;
    hlptim3_.Init.Input1Source = LPTIM_INPUT1SOURCE_GPIO;
    hlptim3_.Init.Input2Source = LPTIM_INPUT2SOURCE_GPIO;
    hlptim3_.Init.RepetitionCounter = 0;
    if (HAL_LPTIM_Init(&hlptim3_) != HAL_OK) {
        return GL_ERR_IO;
    }
    HAL_NVIC_SetPriority(LPTIM3_IRQn, 1, 0);
    HAL_NVIC_EnableIRQ(LPTIM3_IRQn);
    /* continuous counting with the auto-reload (overflow) interrupt */
    if (HAL_LPTIM_Counter_Start_IT(&hlptim3_) != HAL_OK) {
        return GL_ERR_IO;
    }
    return GL_OK;
}

void LPTIM3_IRQHandler(void);
void LPTIM3_IRQHandler(void)
{
    HAL_LPTIM_IRQHandler(&hlptim3_);
}

void HAL_LPTIM_AutoReloadMatchCallback(LPTIM_HandleTypeDef *h)
{
    if (h->Instance == LPTIM3) {
        tick_overflows_++;
    }
}

/* LPTIM counter read: the counter is asynchronous to the bus clock, so it
 * is read until two consecutive reads agree (reference manual). */
static uint32_t lptim3_count_(void)
{
    uint32_t a = LPTIM3->CNT, b = LPTIM3->CNT;
    while (a != b) {
        a = b;
        b = LPTIM3->CNT;
    }
    return a & 0xFFFFu;
}

/* 32768 Hz ticks since boot, 48 bits. */
static uint64_t lse_ticks_(void)
{
    uint32_t hi, lo, primask = __get_PRIMASK();
    __disable_irq();
    lo = lptim3_count_();
    hi = tick_overflows_;
    /* an overflow that has happened but whose interrupt is still pending */
    if ((LPTIM3->ISR & LPTIM_ISR_ARRM) != 0u && lo < 0x8000u) {
        hi++;
    }
    if (primask == 0u) {
        __enable_irq();
    }
    return ((uint64_t)hi << 16) | lo;
}

uint32_t gl_hal_time_us(void)
{
    /* ticks * 1e6 / 32768 = ticks * 15625 / 512; 30.5 us resolution */
    return (uint32_t)((lse_ticks_() * 15625u) >> 9);
}

void gl_hal_trace(gl_trace_point_t point, uint32_t work)
{
    /* Timing instrumentation.  Nothing by default.  For a run-time
     * measurement on the bench, write `point`, `work` and gl_hal_time_us()
     * to an ITM channel here (or toggle a spare pad): the time between two
     * marks against the instruction count that hal/host/gl_sim_cost.h gives
     * for (point, work) is the cycles-per-instruction factor the simulator's
     * timing figures rest on, which nobody has measured yet. */
    (void)point;
    (void)work;
}

uint32_t gl_hal_tick_ms(void)
{
    /* ticks * 1000 / 32768 = ticks * 125 / 4096 */
    return (uint32_t)((lse_ticks_() * 125u) >> 12);
}

/* Both delays have a BOUNDED EXIT that does not depend on the clock they
 * measure with: a low-speed timer that does not count (crystal dead) or a
 * cycle counter that was never enabled must cost time, never the device.
 * (They used to wait on that one clock alone; gl_hal_init() returned early
 * on a clock error, before the counter, the tick and the watchdog existed,
 * and the application's first delay then never came back.) */
void gl_hal_delay_ms(uint32_t ms)
{
    const uint64_t end = lse_ticks_() + ((uint64_t)ms * GLH_LSE_HZ + 999u) / 1000u;
    /* second opinion: the HAL's SysTick time base (core clock), with margin */
    const uint32_t t0 = HAL_GetTick();
    const uint32_t limit = ms + ms / 8u + 2u;
    while (lse_ticks_() < end && (uint32_t)(HAL_GetTick() - t0) < limit) {
        __WFI(); /* SysTick (1 ms) or any other interrupt ends the wait */
    }
}

void gl_hal_delay_us(uint32_t us)
{
    /* DWT cycle counter: 48 cycles per microsecond with the slow clock, 160
     * with the fast one (10000 us x 160 = 1.6e6 cycles: no overflow).  One
     * pass of the loop takes several cycles, so with a counter that runs
     * the pass limit is never reached; with one that does not, the wait
     * ends after `cycles` passes (a few times too long, not for ever). */
    const uint32_t start = DWT->CYCCNT;
    const uint32_t cycles = us * (sysclk_hz_ / 1000000u);
    for (uint32_t pass = 0; pass < cycles && (uint32_t)(DWT->CYCCNT - start) < cycles; pass++) {
    }
}

/* SysTick keeps the HAL's own time base (HAL time-outs) while awake. */
void SysTick_Handler(void);
void SysTick_Handler(void)
{
    HAL_IncTick();
}

/* ---- RTC: seconds since 2000-01-01 from the calendar ---- */

static uint32_t days_from_2000_(uint32_t year2, uint32_t month, uint32_t day)
{
    /* year2 = years since 2000 (0..99), valid 2000-2099 (2000 is a leap year) */
    static const uint16_t before[12] = { 0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334 };
    uint32_t d = year2 * 365u + (year2 + 3u) / 4u + before[(month - 1u) % 12u] + (day - 1u);
    if ((year2 % 4u) == 0u && month > 2u) {
        d++;
    }
    return d;
}

static gl_status_t rtc_init_(void)
{
    __HAL_RCC_RTC_ENABLE();
    __HAL_RCC_RTCAPB_CLK_ENABLE();
    memset(&hrtc_, 0, sizeof(hrtc_));
    hrtc_.Instance = RTC;
    hrtc_.Init.HourFormat = RTC_HOURFORMAT_24;
    hrtc_.Init.AsynchPrediv = 127;
    hrtc_.Init.SynchPrediv = 255;
    hrtc_.Init.OutPut = RTC_OUTPUT_DISABLE;
    hrtc_.Init.BinMode = RTC_BINARY_NONE;
    if (HAL_RTC_Init(&hrtc_) != HAL_OK) {
        return GL_ERR_IO;
    }
    HAL_NVIC_SetPriority(RTC_IRQn, 1, 0);
    HAL_NVIC_EnableIRQ(RTC_IRQn);
    return GL_OK;
}

uint32_t gl_hal_rtc_seconds(void)
{
    RTC_TimeTypeDef t;
    RTC_DateTypeDef d;
    if (HAL_RTCEx_BKUPRead(&hrtc_, RTC_BKP_DR1) != GLH_RTC_SET_MAGIC) {
        return 0; /* never set */
    }
    /* the date must be read after the time to unlock the shadow registers */
    if (HAL_RTC_GetTime(&hrtc_, &t, RTC_FORMAT_BIN) != HAL_OK ||
        HAL_RTC_GetDate(&hrtc_, &d, RTC_FORMAT_BIN) != HAL_OK) {
        return 0;
    }
    /* 946684800 = 2000-01-01 00:00:00 UTC as Unix time */
    return 946684800u + days_from_2000_(d.Year, d.Month, d.Date) * 86400u + t.Hours * 3600u +
           t.Minutes * 60u + t.Seconds;
}

void gl_hal_rtc_set_seconds(uint32_t seconds)
{
    RTC_TimeTypeDef t;
    RTC_DateTypeDef d;
    uint32_t s = (seconds > 946684800u) ? (seconds - 946684800u) : 0u;
    uint32_t days = s / 86400u, rem = s % 86400u, year = 0, month = 1;

    memset(&t, 0, sizeof(t));
    memset(&d, 0, sizeof(d));
    while (year < 99u && days >= (((year % 4u) == 0u) ? 366u : 365u)) {
        days -= ((year % 4u) == 0u) ? 366u : 365u;
        year++;
    }
    for (;;) {
        static const uint8_t len[12] = { 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31 };
        uint32_t n = len[month - 1u];
        if (month == 2u && (year % 4u) == 0u) {
            n = 29;
        }
        if (days < n || month == 12u) {
            break;
        }
        days -= n;
        month++;
    }
    d.Year = (uint8_t)year;
    d.Month = (uint8_t)month;
    d.Date = (uint8_t)(days + 1u);
    d.WeekDay = RTC_WEEKDAY_MONDAY; /* not used */
    t.Hours = (uint8_t)(rem / 3600u);
    t.Minutes = (uint8_t)((rem % 3600u) / 60u);
    t.Seconds = (uint8_t)(rem % 60u);
    (void)HAL_RTC_SetTime(&hrtc_, &t, RTC_FORMAT_BIN);
    (void)HAL_RTC_SetDate(&hrtc_, &d, RTC_FORMAT_BIN);
    HAL_RTCEx_BKUPWrite(&hrtc_, RTC_BKP_DR1, GLH_RTC_SET_MAGIC);
}

/* ---- one-shot wake-up timer: RTC wake-up timer ---- */

void gl_hal_wake_timer_start(uint32_t ms)
{
    (void)HAL_RTCEx_DeactivateWakeUpTimer(&hrtc_);
    /* called before every sleep, up to 240 times a second: this clear must
     * not lose a bit that a handler sets at the same moment */
    clear_pending_(GL_IRQ_WAKE_TIMER);
    if (ms == 0u) {
        return;
    }
    if (ms <= 30000u) {
        /* RTCCLK / 16 = 2048 Hz: 0.49 ms resolution, up to 32 s */
        uint32_t counts = (ms * 2048u + 999u) / 1000u;
        if (counts < 2u) {
            counts = 2u;
        }
        (void)HAL_RTCEx_SetWakeUpTimer_IT(&hrtc_, counts - 1u, RTC_WAKEUPCLOCK_RTCCLK_DIV16, 0);
    } else {
        /* 1 Hz clock: up to 18 h; 24 h is clamped */
        uint32_t s = (ms + 999u) / 1000u;
        if (s > 65536u) {
            s = 65536u;
        }
        (void)HAL_RTCEx_SetWakeUpTimer_IT(&hrtc_, s - 1u, RTC_WAKEUPCLOCK_CK_SPRE_16BITS, 0);
    }
}

void RTC_IRQHandler(void);
void RTC_IRQHandler(void)
{
    HAL_RTCEx_WakeUpTimerIRQHandler(&hrtc_);
}

void HAL_RTCEx_WakeUpTimerEventCallback(RTC_HandleTypeDef *h)
{
    (void)h;
    (void)HAL_RTCEx_DeactivateWakeUpTimer(&hrtc_); /* one shot */
    raise_(GL_IRQ_WAKE_TIMER);
}

/* ======================================================================= */
/* GPIO                                                                     */
/* ======================================================================= */

static void gpio_clocks_(void)
{
    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_GPIOB_CLK_ENABLE();
    __HAL_RCC_GPIOC_CLK_ENABLE();
    __HAL_RCC_GPIOD_CLK_ENABLE();
    __HAL_RCC_GPIOH_CLK_ENABLE();
}

/* EXTI trigger of an interrupt pin: the IMU lines on the rising edge, VBUS
 * and the charger STAT line on both.  INT2 (data ready) is LATCHED by the
 * sensor unless GL_PROV_IMU_DRDY_PULSED: it stays high until the output is
 * read, so a sample that is not fetched produces no further edge.  The
 * application therefore also polls the line (gl_hal_gpio_read) when no
 * interrupt has arrived for two sample periods. */
static uint32_t exti_mode_(gl_pin_t pin)
{
    return (pin == GL_PIN_IMU_INT1 || pin == GL_PIN_IMU_INT2) ? GPIO_MODE_IT_RISING
                                                              : GPIO_MODE_IT_RISING_FALLING;
}

void gl_hal_gpio_mode(gl_pin_t pin, gl_pin_mode_t mode)
{
    GPIO_InitTypeDef g;
    const glh_pin_t *p;
    if ((unsigned)pin >= (unsigned)GL_PIN_COUNT) {
        return;
    }
    p = &pin_[pin];
    memset(&g, 0, sizeof(g));
    g.Pin = p->mask;
    g.Pull = GPIO_NOPULL;
    g.Speed = GPIO_SPEED_FREQ_LOW;
    switch (mode) {
    case GL_PIN_MODE_ANALOG:
        g.Mode = GPIO_MODE_ANALOG;
        break;
    case GL_PIN_MODE_INPUT:
    case GL_PIN_MODE_INPUT_PULLUP:
    case GL_PIN_MODE_INPUT_PULLDOWN:
        /* interrupt pins keep their EXTI configuration */
        g.Mode = (p->fn == GL_PINFN_EXTI) ? exti_mode_(pin) : GPIO_MODE_INPUT;
        g.Pull = (mode == GL_PIN_MODE_INPUT_PULLUP)
                     ? GPIO_PULLUP
                     : ((mode == GL_PIN_MODE_INPUT_PULLDOWN) ? GPIO_PULLDOWN : GPIO_NOPULL);
        break;
    case GL_PIN_MODE_OUTPUT_PP:
        g.Mode = GPIO_MODE_OUTPUT_PP;
        break;
    case GL_PIN_MODE_OUTPUT_OD:
        g.Mode = GPIO_MODE_OUTPUT_OD;
        break;
    case GL_PIN_MODE_ALTERNATE:
    default:
        if (p->fn == GL_PINFN_AF) {
            g.Mode = GPIO_MODE_AF_PP;
            g.Alternate = p->af;
            /* camera bus, SPI and MCO edges: up to 24 MHz */
            g.Speed = GPIO_SPEED_FREQ_HIGH;
        } else if (p->fn == GL_PINFN_ANALOG) {
            g.Mode = GPIO_MODE_ANALOG;
        } else if (p->fn == GL_PINFN_SCCB) {
            /* bit-banged SCCB: open drain, released (the pull-ups go to the
             * camera rail, which is on whenever this mode is selected) */
            HAL_GPIO_WritePin(p->port, p->mask, GPIO_PIN_SET);
            latch_[pin] = true;
            g.Mode = GPIO_MODE_OUTPUT_OD;
        } else {
            g.Mode = GPIO_MODE_OUTPUT_PP;
        }
        break;
    }
    HAL_GPIO_Init(p->port, &g);
    mode_[pin] = (uint8_t)mode;
}

void gl_hal_gpio_write(gl_pin_t pin, bool high)
{
    if ((unsigned)pin >= (unsigned)GL_PIN_COUNT) {
        return;
    }
    /* the output data register keeps its value in analog / input mode, so
     * write-then-mode switches on without a glitch */
    HAL_GPIO_WritePin(pin_[pin].port, pin_[pin].mask, high ? GPIO_PIN_SET : GPIO_PIN_RESET);
    latch_[pin] = high;
}

bool gl_hal_gpio_read(gl_pin_t pin)
{
    if ((unsigned)pin >= (unsigned)GL_PIN_COUNT) {
        return false;
    }
    return HAL_GPIO_ReadPin(pin_[pin].port, pin_[pin].mask) == GPIO_PIN_SET;
}

/* ======================================================================= */
/* interrupts and sleep                                                     */
/* ======================================================================= */

/* EXTI lines: IMU_INT1 = PC13, IMU_INT2 = PC5, VBUS = PA9, CHG_STAT = PB0
 * (hal/stm32u5/gl_pins.h).  The U5 has one vector per line. */
void EXTI0_IRQHandler(void);
void EXTI5_IRQHandler(void);
void EXTI9_IRQHandler(void);
void EXTI13_IRQHandler(void);
void EXTI0_IRQHandler(void) { HAL_GPIO_EXTI_IRQHandler(GPIO_PIN_0); }
void EXTI5_IRQHandler(void) { HAL_GPIO_EXTI_IRQHandler(GPIO_PIN_5); }
void EXTI9_IRQHandler(void) { HAL_GPIO_EXTI_IRQHandler(GPIO_PIN_9); }
void EXTI13_IRQHandler(void) { HAL_GPIO_EXTI_IRQHandler(GPIO_PIN_13); }

static void exti_event_(uint16_t gpio_pin, bool rising)
{
    if (gpio_pin == GPIO_PIN_13) {
        if (rising) {
            raise_(GL_IRQ_IMU_INT1);
        }
    } else if (gpio_pin == GPIO_PIN_5) {
        if (rising) {
            raise_(GL_IRQ_IMU_INT2);
        }
    } else if (gpio_pin == GPIO_PIN_9) {
        raise_(GL_IRQ_VBUS_CHANGE);
    } else if (gpio_pin == GPIO_PIN_0) {
        raise_(GL_IRQ_CHG_STAT);
    }
}

void HAL_GPIO_EXTI_Rising_Callback(uint16_t gpio_pin)
{
    exti_event_(gpio_pin, true);
}

void HAL_GPIO_EXTI_Falling_Callback(uint16_t gpio_pin)
{
    exti_event_(gpio_pin, false);
}

static void nvic_(IRQn_Type irq, bool enable)
{
    if (enable) {
        HAL_NVIC_SetPriority(irq, 2, 0);
        HAL_NVIC_EnableIRQ(irq);
    } else {
        HAL_NVIC_DisableIRQ(irq);
    }
}

void gl_hal_irq_enable(uint32_t mask, bool enable)
{
    const uint32_t primask = __get_PRIMASK();
    __disable_irq();
    if (enable) {
        irq_enabled_ |= mask;
    } else {
        irq_enabled_ &= ~mask;
        irq_pending_ &= ~mask;
    }
    if (primask == 0u) {
        __enable_irq();
    }
    if ((mask & GL_IRQ_IMU_INT1) != 0u) {
        nvic_(EXTI13_IRQn, enable);
    }
    if ((mask & GL_IRQ_IMU_INT2) != 0u) {
        nvic_(EXTI5_IRQn, enable);
    }
    if ((mask & GL_IRQ_VBUS_CHANGE) != 0u) {
        nvic_(EXTI9_IRQn, enable);
    }
    if ((mask & GL_IRQ_CHG_STAT) != 0u) {
        nvic_(EXTI0_IRQn, enable);
    }
    /* WAKE_TIMER (RTC), DCMI_DONE and USB_RX vectors stay enabled; the mask
     * decides whether their events are latched */
}

uint32_t gl_hal_irq_take(void)
{
    uint32_t p, primask = __get_PRIMASK();
    __disable_irq();
    p = irq_pending_;
    irq_pending_ = 0;
    if (primask == 0u) {
        __enable_irq();
    }
    return p;
}

void gl_hal_irq_lock(void)
{
    __disable_irq();
    irq_lock_depth_++;
}

void gl_hal_irq_unlock(void)
{
    if (irq_lock_depth_ > 0u && --irq_lock_depth_ == 0u) {
        __enable_irq();
    }
}

uint32_t gl_hal_sleep(gl_sleep_mode_t mode)
{
    bool stopped = false;
    /* Sleep until an ENABLED source is pending.  Other interrupts (the 2 s
     * overflow of the tick timer) wake the core, are served, and the core
     * goes back to sleep without returning to the application.
     *
     * The check and the WFI are done with interrupts masked: a source that
     * fires in between still wakes the core (WFI wakes on a pending
     * interrupt even when PRIMASK is set) and its handler runs when the
     * mask is lifted, so no wake-up is lost. */
    HAL_SuspendTick();
    for (;;) {
        __disable_irq();
        if (irq_pending_ != 0u) {
            __enable_irq();
            break;
        }
        if (mode == GL_SLEEP_STOP && clock_ != GL_CLOCK_FAST) {
            HAL_PWREx_EnterSTOP2Mode(PWR_STOPENTRY_WFI);
            stopped = true;
        } else {
            /* idle sleep; also what Stop becomes while the PLL runs (the
             * application never asks for that: gl_hal.h) */
            HAL_PWR_EnterSLEEPMode(PWR_MAINREGULATOR_ON, PWR_SLEEPENTRY_WFI);
        }
        __enable_irq(); /* the handler of whatever woke the core runs here */
    }
    /* The HAL's time base first: the oscillator and clock set-up below waits
     * on flags with HAL time-outs, which cannot expire while SysTick is
     * suspended (it used to be resumed AFTER: a flag that never set ended in
     * the watchdog). */
    HAL_ResumeTick();
    if (stopped) {
        /* the core woke on MSIS (the wake-up clock): re-apply the clock
         * set-up.  Stop is only entered from the SLOW clock, so that is the
         * state to restore.  NOT MEASURED: what this costs.  It runs after
         * every Stop exit - up to 240 times a second while a result is
         * shown - and the simulator's "Stop 2 for 99.5 %" does not include
         * it; if it is expensive, restore only what Stop 2 loses (README,
         * open issues). */
        (void)clocks_init_();
    }
    return irq_pending_;
}

/* ======================================================================= */
/* SPI                                                                      */
/* ======================================================================= */

static uint32_t spi_prescaler_(uint32_t max_hz)
{
    static const uint32_t code[8] = { SPI_BAUDRATEPRESCALER_2,  SPI_BAUDRATEPRESCALER_4,
                                      SPI_BAUDRATEPRESCALER_8,  SPI_BAUDRATEPRESCALER_16,
                                      SPI_BAUDRATEPRESCALER_32, SPI_BAUDRATEPRESCALER_64,
                                      SPI_BAUDRATEPRESCALER_128, SPI_BAUDRATEPRESCALER_256 };
    uint32_t hz = GLH_SYSCLK_HZ / 2u; /* kernel clock MSIK, 48 MHz with either core clock */
    unsigned i = 0;
    while (i < 7u && hz > max_hz) {
        hz /= 2u;
        i++;
    }
    return code[i]; /* 48 MHz / 256 = 187.5 kHz is the slowest */
}

gl_status_t gl_hal_spi_configure(gl_spi_bus_t bus, const gl_spi_cfg_t *cfg)
{
    SPI_HandleTypeDef *h;
    if ((unsigned)bus >= (unsigned)GL_SPI_BUS_COUNT || cfg == NULL || cfg->mode > 3u ||
        cfg->max_hz < GLH_SYSCLK_HZ / 256u) {
        return GL_ERR_PARAM;
    }
    if (spi_ready_[bus] && spi_cfg_[bus].max_hz == cfg->max_hz && spi_cfg_[bus].mode == cfg->mode &&
        spi_cfg_[bus].lsb_first == cfg->lsb_first) {
        return GL_OK; /* unchanged: nothing to do */
    }
    h = &hspi_[bus];
    if (spi_ready_[bus]) {
        (void)HAL_SPI_DeInit(h);
    }
    memset(h, 0, sizeof(*h));
    if (bus == GL_SPI_BUS_1) {
        __HAL_RCC_SPI1_CLK_ENABLE();
        h->Instance = SPI1;
    } else {
        __HAL_RCC_SPI2_CLK_ENABLE();
        h->Instance = SPI2;
    }
    h->Init.Mode = SPI_MODE_MASTER;
    h->Init.Direction = SPI_DIRECTION_2LINES;
    h->Init.DataSize = SPI_DATASIZE_8BIT;
    h->Init.CLKPolarity = ((cfg->mode & 2u) != 0u) ? SPI_POLARITY_HIGH : SPI_POLARITY_LOW;
    h->Init.CLKPhase = ((cfg->mode & 1u) != 0u) ? SPI_PHASE_2EDGE : SPI_PHASE_1EDGE;
    h->Init.NSS = SPI_NSS_SOFT; /* chip selects are GPIOs driven by the drivers */
    h->Init.BaudRatePrescaler = spi_prescaler_(cfg->max_hz);
    h->Init.FirstBit = cfg->lsb_first ? SPI_FIRSTBIT_LSB : SPI_FIRSTBIT_MSB;
    h->Init.TIMode = SPI_TIMODE_DISABLE;
    h->Init.CRCCalculation = SPI_CRCCALCULATION_DISABLE;
    h->Init.NSSPMode = SPI_NSS_PULSE_DISABLE;
    h->Init.NSSPolarity = SPI_NSS_POLARITY_LOW;
    h->Init.FifoThreshold = SPI_FIFO_THRESHOLD_01DATA;
    h->Init.MasterSSIdleness = SPI_MASTER_SS_IDLENESS_00CYCLE;
    h->Init.MasterInterDataIdleness = SPI_MASTER_INTERDATA_IDLENESS_00CYCLE;
    h->Init.MasterReceiverAutoSusp = SPI_MASTER_RX_AUTOSUSP_DISABLE;
    /* keep SCK / MOSI driven between transfers: the LCD needs the clock to
     * idle LOW while its (active-high) chip select rises */
    h->Init.MasterKeepIOState = SPI_MASTER_KEEP_IO_STATE_ENABLE;
    h->Init.IOSwap = SPI_IO_SWAP_DISABLE;
    h->Init.ReadyMasterManagement = SPI_RDY_MASTER_MANAGEMENT_INTERNALLY;
    h->Init.ReadyPolarity = SPI_RDY_POLARITY_HIGH;
    if (HAL_SPI_Init(h) != HAL_OK) {
        spi_ready_[bus] = false;
        return GL_ERR_IO;
    }
    spi_cfg_[bus] = *cfg;
    spi_ready_[bus] = true;
    return GL_OK;
}

gl_status_t gl_hal_spi_transfer(gl_spi_bus_t bus, const uint8_t *tx, uint8_t *rx, size_t len)
{
    static const uint8_t ones[32] = {
        0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
        0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF
    };
    SPI_HandleTypeDef *h;
    if ((unsigned)bus >= (unsigned)GL_SPI_BUS_COUNT) {
        return GL_ERR_PARAM;
    }
    if (!spi_ready_[bus]) {
        return GL_ERR_STATE;
    }
    h = &hspi_[bus];
    while (len > 0u) {
        HAL_StatusTypeDef st;
        uint16_t n = (len > 0x8000u) ? (uint16_t)0x8000u : (uint16_t)len;
        if (tx != NULL && rx != NULL) {
            st = HAL_SPI_TransmitReceive(h, (uint8_t *)(uintptr_t)tx, rx, n, 100u + n / 8u);
        } else if (tx != NULL) {
            st = HAL_SPI_Transmit(h, (uint8_t *)(uintptr_t)tx, n, 100u + n / 8u);
        } else if (rx != NULL) {
            /* read: 0xFF must go out on MOSI, in pieces of the 0xFF buffer */
            if (n > sizeof(ones)) {
                n = (uint16_t)sizeof(ones);
            }
            st = HAL_SPI_TransmitReceive(h, (uint8_t *)(uintptr_t)ones, rx, n, 100u);
        } else {
            if (n > sizeof(ones)) {
                n = (uint16_t)sizeof(ones);
            }
            st = HAL_SPI_Transmit(h, (uint8_t *)(uintptr_t)ones, n, 100u);
        }
        if (st != HAL_OK) {
            return (st == HAL_TIMEOUT) ? GL_ERR_TIMEOUT : GL_ERR_IO;
        }
        if (tx != NULL) {
            tx += n;
        }
        if (rx != NULL) {
            rx += n;
        }
        len -= n;
    }
    return GL_OK;
}

/* ======================================================================= */
/* SCCB, bit-banged (about 100 kHz)                                         */
/* ======================================================================= */

#define SCCB_HALF_US 5u

static gl_pin_t sccb_scl_;

static void scl_(bool high)
{
    HAL_GPIO_WritePin(pin_[sccb_scl_].port, pin_[sccb_scl_].mask, high ? GPIO_PIN_SET : GPIO_PIN_RESET);
    gl_hal_delay_us(SCCB_HALF_US);
}

static void sda_(bool high)
{
    HAL_GPIO_WritePin(pin_[GL_PIN_CAM_SCCB_SDA].port, pin_[GL_PIN_CAM_SCCB_SDA].mask,
                      high ? GPIO_PIN_SET : GPIO_PIN_RESET);
}

static bool sda_read_(void)
{
    return HAL_GPIO_ReadPin(pin_[GL_PIN_CAM_SCCB_SDA].port, pin_[GL_PIN_CAM_SCCB_SDA].mask) ==
           GPIO_PIN_SET;
}

static void sccb_start_(void)
{
    sda_(true);
    scl_(true);
    sda_(false);
    gl_hal_delay_us(SCCB_HALF_US);
    scl_(false);
}

static void sccb_stop_(void)
{
    sda_(false);
    scl_(true);
    sda_(true);
    gl_hal_delay_us(SCCB_HALF_US);
}

/* Send one byte; returns true if the 9th bit was pulled low.  (SCCB calls
 * the 9th bit "don't care"; OmniVision sensors drive it low like an I2C
 * acknowledge, and a missing or unpowered sensor leaves it high.) */
static bool sccb_tx_(uint8_t b)
{
    bool ack;
    for (unsigned i = 0; i < 8u; i++) {
        sda_((b & 0x80u) != 0u);
        b = (uint8_t)(b << 1);
        gl_hal_delay_us(1);
        scl_(true);
        scl_(false);
    }
    sda_(true); /* release for the 9th bit */
    gl_hal_delay_us(1);
    scl_(true);
    ack = !sda_read_();
    scl_(false);
    return ack;
}

static uint8_t sccb_rx_(void)
{
    uint8_t b = 0;
    sda_(true);
    for (unsigned i = 0; i < 8u; i++) {
        gl_hal_delay_us(1);
        scl_(true);
        b = (uint8_t)((b << 1) | (sda_read_() ? 1u : 0u));
        scl_(false);
    }
    /* master leaves the 9th bit high (NACK): single-byte read */
    scl_(true);
    scl_(false);
    return b;
}

static bool sccb_select_(gl_cam_id_t cam)
{
    if ((unsigned)cam >= (unsigned)GL_CAM_COUNT) {
        return false;
    }
    sccb_scl_ = (cam == GL_CAM_LEFT) ? GL_PIN_CAM_L_SCL : GL_PIN_CAM_R_SCL;
    /* the bus must have been handed over by the driver (rail on) */
    return mode_[sccb_scl_] == (uint8_t)GL_PIN_MODE_ALTERNATE &&
           mode_[GL_PIN_CAM_SCCB_SDA] == (uint8_t)GL_PIN_MODE_ALTERNATE;
}

gl_status_t gl_hal_sccb_write(gl_cam_id_t cam, uint8_t addr7, uint8_t reg, uint8_t val)
{
    bool ok;
    if (!sccb_select_(cam)) {
        return GL_ERR_STATE;
    }
    sccb_start_();
    ok = sccb_tx_((uint8_t)(addr7 << 1));
    ok = sccb_tx_(reg) && ok;
    ok = sccb_tx_(val) && ok;
    sccb_stop_();
    return (ok || GL_PROV_OV7692_SCCB_ACKS == 0) ? GL_OK : GL_ERR_IO;
}

gl_status_t gl_hal_sccb_read(gl_cam_id_t cam, uint8_t addr7, uint8_t reg, uint8_t *val)
{
    bool ok;
    if (val == NULL || !sccb_select_(cam)) {
        return GL_ERR_STATE;
    }
    /* 2-phase write, then 2-phase read (SCCB has no repeated start) */
    sccb_start_();
    ok = sccb_tx_((uint8_t)(addr7 << 1));
    ok = sccb_tx_(reg) && ok;
    sccb_stop_();
    sccb_start_();
    ok = sccb_tx_((uint8_t)((addr7 << 1) | 1u)) && ok;
    *val = sccb_rx_();
    sccb_stop_();
    return (ok || GL_PROV_OV7692_SCCB_ACKS == 0) ? GL_OK : GL_ERR_IO;
}

/* ======================================================================= */
/* camera clock (MCO) and DCMI                                              */
/* ======================================================================= */

gl_status_t gl_hal_xvclk_start(uint32_t hz)
{
    /* MSI 48 MHz / 2, 4, 8 */
    uint32_t div;
    if (hz >= 11760000u && hz <= 12240000u) {
        div = RCC_MCODIV_4;
    } else if (hz >= 23520000u && hz <= 24480000u) {
        div = RCC_MCODIV_2;
    } else if (hz >= 5880000u && hz <= 6120000u) {
        div = RCC_MCODIV_8;
    } else {
        return GL_ERR_RANGE;
    }
    /* HAL_RCC_MCOConfig also (re)configures PA8 as the MCO alternate function */
    HAL_RCC_MCOConfig(RCC_MCO1, GLH_MCO_SRC_MSI, div);
    return GL_OK;
}

void gl_hal_xvclk_stop(void)
{
    HAL_RCC_MCOConfig(RCC_MCO1, GLH_MCO_SRC_NONE, RCC_MCODIV_1);
    /* the driver now drives the pin low as a plain output */
}

void DCMI_PSSI_IRQHandler(void);
void DCMI_PSSI_IRQHandler(void)
{
    HAL_DCMI_IRQHandler(&hdcmi_);
}

void GPDMA1_Channel0_IRQHandler(void);
void GPDMA1_Channel0_IRQHandler(void)
{
    HAL_DMA_IRQHandler(&hdma_dcmi_);
}

void HAL_DCMI_FrameEventCallback(DCMI_HandleTypeDef *h)
{
    /* end of the snapshot frame: complete only if the DMA took every byte.
     * The time is latched HERE, in the interrupt: the application times the
     * L R R L strips with it and may poll much later. */
    if (dcmi_state_ == GL_DCMI_BUSY) {
        dcmi_done_us_ = gl_hal_time_us();
        dcmi_state_ = (__HAL_DMA_GET_COUNTER(h->DMA_Handle) == 0u) ? GL_DCMI_DONE
                                                                   : GL_DCMI_ERROR_SIZE;
        raise_(GL_IRQ_DCMI_DONE);
    }
}

void HAL_DCMI_ErrorCallback(DCMI_HandleTypeDef *h)
{
    (void)h;
    if (dcmi_state_ == GL_DCMI_BUSY) {
        dcmi_state_ = GL_DCMI_ERROR_OVERRUN;
        raise_(GL_IRQ_DCMI_DONE);
    }
}

gl_status_t gl_hal_dcmi_start(const gl_dcmi_cfg_t *cfg, uint8_t *buf, size_t buf_len)
{
    size_t expect;
    if (cfg == NULL || buf == NULL || (cfg->byte_select_every != 1u && cfg->byte_select_every != 2u) ||
        cfg->width_bytes == 0u || cfg->height_lines == 0u ||
        (cfg->width_bytes % cfg->byte_select_every) != 0u) {
        return GL_ERR_PARAM;
    }
    expect = (size_t)(cfg->width_bytes / cfg->byte_select_every) * cfg->height_lines;
    /* one GPDMA block (< 64 kB) of whole 32-bit words into a word-aligned buffer */
    if (expect > buf_len || expect > 0xFFFCu || (expect % 4u) != 0u || ((uintptr_t)buf % 4u) != 0u) {
        return GL_ERR_PARAM;
    }
    if (dcmi_state_ == GL_DCMI_BUSY) {
        return GL_ERR_BUSY;
    }
    __HAL_RCC_DCMI_PSSI_CLK_ENABLE();
    __HAL_RCC_GPDMA1_CLK_ENABLE();

    memset(&hdma_dcmi_, 0, sizeof(hdma_dcmi_));
    hdma_dcmi_.Instance = GPDMA1_Channel0;
    hdma_dcmi_.Init.Request = GLH_DCMI_DMA_REQUEST;
    hdma_dcmi_.Init.BlkHWRequest = DMA_BREQ_SINGLE_BURST;
    hdma_dcmi_.Init.Direction = DMA_PERIPH_TO_MEMORY;
    hdma_dcmi_.Init.SrcInc = DMA_SINC_FIXED;
    hdma_dcmi_.Init.DestInc = DMA_DINC_INCREMENTED;
    hdma_dcmi_.Init.SrcDataWidth = DMA_SRC_DATAWIDTH_WORD;
    hdma_dcmi_.Init.DestDataWidth = DMA_DEST_DATAWIDTH_WORD;
    hdma_dcmi_.Init.Priority = DMA_HIGH_PRIORITY;
    hdma_dcmi_.Init.SrcBurstLength = 1;
    hdma_dcmi_.Init.DestBurstLength = 1;
    hdma_dcmi_.Init.TransferAllocatedPort = DMA_SRC_ALLOCATED_PORT0 | DMA_DEST_ALLOCATED_PORT1;
    hdma_dcmi_.Init.TransferEventMode = DMA_TCEM_BLOCK_TRANSFER;
    hdma_dcmi_.Init.Mode = DMA_NORMAL;
    if (HAL_DMA_Init(&hdma_dcmi_) != HAL_OK) {
        return GL_ERR_IO;
    }

    memset(&hdcmi_, 0, sizeof(hdcmi_));
    hdcmi_.Instance = DCMI;
    __HAL_LINKDMA(&hdcmi_, DMA_Handle, hdma_dcmi_);
    hdcmi_.Init.SynchroMode = DCMI_SYNCHRO_HARDWARE;
    hdcmi_.Init.PCKPolarity = cfg->pclk_rising_edge ? DCMI_PCKPOLARITY_RISING : DCMI_PCKPOLARITY_FALLING;
    /* The DCMI polarity bits give the level of a sync line while data are
     * NOT valid.  gl_dcmi_cfg_t: vsync_active_high = the VSYNC pulse (during
     * which there is no data) is high; href_active_high = HREF is high WHILE
     * data are valid, i.e. low when they are not.  PROVISIONAL for the
     * OVM7692 (GL_PROV_OV7692_*). */
    hdcmi_.Init.VSPolarity = cfg->vsync_active_high ? DCMI_VSPOLARITY_HIGH : DCMI_VSPOLARITY_LOW;
    hdcmi_.Init.HSPolarity = cfg->href_active_high ? DCMI_HSPOLARITY_LOW : DCMI_HSPOLARITY_HIGH;
    hdcmi_.Init.CaptureRate = DCMI_CR_ALL_FRAME;
    hdcmi_.Init.ExtendedDataMode = DCMI_EXTEND_DATA_8B;
    hdcmi_.Init.JPEGMode = DCMI_JPEG_DISABLE;
    hdcmi_.Init.ByteSelectMode =
        (cfg->byte_select_every == 2u) ? GLH_DCMI_BSM_EVERY_OTHER : GLH_DCMI_BSM_ALL;
    hdcmi_.Init.ByteSelectStart = cfg->byte_select_odd ? GLH_DCMI_OEBS_SECOND : GLH_DCMI_OEBS_FIRST;
    hdcmi_.Init.LineSelectMode = DCMI_LSM_ALL;
    hdcmi_.Init.LineSelectStart = DCMI_OELS_ODD;
    if (HAL_DCMI_Init(&hdcmi_) != HAL_OK) {
        return GL_ERR_IO;
    }
    /* Crop window in pixel clocks and lines; the size registers hold
     * (count - 1).  Whether the byte select counts from the start of the
     * LINE or of the crop window is not stated clearly in the reference
     * manual as remembered; the driver only ever uses an EVEN x0_bytes, for
     * which both readings select the same bytes. */
    if (HAL_DCMI_ConfigCrop(&hdcmi_, cfg->x0_bytes, cfg->y0_lines, (uint32_t)cfg->width_bytes - 1u,
                            (uint32_t)cfg->height_lines - 1u) != HAL_OK ||
        HAL_DCMI_EnableCrop(&hdcmi_) != HAL_OK) {
        return GL_ERR_IO;
    }
    HAL_NVIC_SetPriority(DCMI_PSSI_IRQn, 1, 0);
    HAL_NVIC_EnableIRQ(DCMI_PSSI_IRQn);
    HAL_NVIC_SetPriority(GPDMA1_Channel0_IRQn, 1, 0);
    HAL_NVIC_EnableIRQ(GPDMA1_Channel0_IRQn);

    dcmi_expect_ = expect;
    dcmi_deadline_ms_ = gl_hal_tick_ms() + cfg->timeout_ms;
    dcmi_state_ = GL_DCMI_BUSY;
    /* length in 32-bit words (HAL convention) */
    if (HAL_DCMI_Start_DMA(&hdcmi_, DCMI_MODE_SNAPSHOT, (uint32_t)(uintptr_t)buf,
                           (uint32_t)(expect / 4u)) != HAL_OK) {
        dcmi_state_ = GL_DCMI_IDLE;
        return GL_ERR_IO;
    }
    return GL_OK;
}

gl_dcmi_state_t gl_hal_dcmi_poll(size_t *bytes)
{
    gl_dcmi_state_t st = dcmi_state_;
    if (st == GL_DCMI_BUSY && (int32_t)(gl_hal_tick_ms() - dcmi_deadline_ms_) >= 0) {
        (void)HAL_DCMI_Stop(&hdcmi_);
        dcmi_state_ = GL_DCMI_ERROR_TIMEOUT;
        st = GL_DCMI_ERROR_TIMEOUT;
        raise_(GL_IRQ_DCMI_DONE);
    }
    if (bytes != NULL) {
        *bytes = (st == GL_DCMI_DONE) ? dcmi_expect_ : 0u;
    }
    return st;
}

uint32_t gl_hal_dcmi_done_us(void)
{
    return dcmi_done_us_;
}

void gl_hal_dcmi_stop(void)
{
    if (dcmi_state_ != GL_DCMI_IDLE) {
        (void)HAL_DCMI_Stop(&hdcmi_);
        (void)HAL_DCMI_DeInit(&hdcmi_);
        (void)HAL_DMA_DeInit(&hdma_dcmi_);
        __HAL_RCC_DCMI_PSSI_CLK_DISABLE();
    }
    dcmi_state_ = GL_DCMI_IDLE;
}

/* ======================================================================= */
/* ADC and op-amp                                                           */
/* ======================================================================= */

gl_status_t gl_hal_adc_power(bool on)
{
    if (on == adc_on_) {
        return GL_OK;
    }
    if (!on) {
        (void)HAL_ADC_DeInit(&hadc_);
        __HAL_RCC_ADC12_CLK_DISABLE();
        adc_on_ = false;
        return GL_OK;
    }
    HAL_PWREx_EnableVddA(); /* analog supply isolation switch */
    __HAL_RCC_ADC12_CLK_ENABLE();
    memset(&hadc_, 0, sizeof(hadc_));
    hadc_.Instance = ADC1;
    hadc_.Init.ClockPrescaler = ADC_CLOCK_ASYNC_DIV4; /* MSIK 48 MHz / 4 = 12 MHz, with either core clock */
    hadc_.Init.Resolution = ADC_RESOLUTION_14B;
    hadc_.Init.GainCompensation = 0;
    hadc_.Init.ScanConvMode = ADC_SCAN_DISABLE;
    hadc_.Init.EOCSelection = ADC_EOC_SINGLE_CONV;
    hadc_.Init.LowPowerAutoWait = DISABLE;
    hadc_.Init.ContinuousConvMode = DISABLE;
    hadc_.Init.NbrOfConversion = 1;
    hadc_.Init.DiscontinuousConvMode = DISABLE;
    hadc_.Init.ExternalTrigConv = ADC_SOFTWARE_START;
    hadc_.Init.ExternalTrigConvEdge = ADC_EXTERNALTRIGCONVEDGE_NONE;
    hadc_.Init.DMAContinuousRequests = DISABLE;
    hadc_.Init.TriggerFrequencyMode = ADC_TRIGGER_FREQ_HIGH;
    hadc_.Init.Overrun = ADC_OVR_DATA_OVERWRITTEN;
    hadc_.Init.LeftBitShift = ADC_LEFTBITSHIFT_NONE;
    hadc_.Init.ConversionDataManagement = ADC_CONVERSIONDATA_DR;
    hadc_.Init.OversamplingMode = DISABLE;
    if (HAL_ADC_Init(&hadc_) != HAL_OK ||
        HAL_ADCEx_Calibration_Start(&hadc_, ADC_CALIB_OFFSET, ADC_SINGLE_ENDED) != HAL_OK) {
        (void)HAL_ADC_DeInit(&hadc_);
        __HAL_RCC_ADC12_CLK_DISABLE();
        return GL_ERR_IO;
    }
    adc_on_ = true;
    return GL_OK;
}

static gl_status_t adc_convert_(uint32_t channel, uint32_t sampling, uint16_t n_avg, uint32_t *mean)
{
    ADC_ChannelConfTypeDef ch;
    uint32_t sum = 0;
    memset(&ch, 0, sizeof(ch));
    ch.Channel = channel;
    ch.Rank = ADC_REGULAR_RANK_1;
    ch.SamplingTime = sampling;
    ch.SingleDiff = ADC_SINGLE_ENDED;
    ch.OffsetNumber = ADC_OFFSET_NONE;
    ch.Offset = 0;
    if (HAL_ADC_ConfigChannel(&hadc_, &ch) != HAL_OK) {
        return GL_ERR_IO;
    }
    for (uint16_t i = 0; i < n_avg; i++) {
        if (HAL_ADC_Start(&hadc_) != HAL_OK || HAL_ADC_PollForConversion(&hadc_, 10) != HAL_OK) {
            (void)HAL_ADC_Stop(&hadc_);
            return GL_ERR_IO;
        }
        sum += HAL_ADC_GetValue(&hadc_);
    }
    (void)HAL_ADC_Stop(&hadc_);
    *mean = (sum + n_avg / 2u) / n_avg;
    return GL_OK;
}

gl_status_t gl_hal_adc_read(gl_adc_ch_t ch, uint16_t n_avg, uint16_t sample_time_us, uint16_t *counts)
{
    uint32_t channel, sampling, mean = 0;
    gl_status_t st;
    if (counts == NULL || n_avg == 0u || n_avg > 256u) {
        return GL_ERR_PARAM;
    }
    if (!adc_on_) {
        return GL_ERR_STATE;
    }
    switch (ch) {
    case GL_ADC_CH_GRAIN_TIA: channel = GLH_ADC_CH_GRAIN; break;
    case GL_ADC_CH_VBAT_DIV: channel = GLH_ADC_CH_VBAT; break;
    case GL_ADC_CH_VREFINT: channel = ADC_CHANNEL_VREFINT; break;
    case GL_ADC_CH_MCU_TEMP: channel = ADC_CHANNEL_TEMPSENSOR; break;
    case GL_ADC_CH_CELL_NTC: channel = GLH_ADC_CH_NTC; break; /* 5 kohm source: any setting >= 5 us */
    default: return GL_ERR_PARAM;
    }
    /* shortest setting that is at least the requested time (ADC clock 12 MHz) */
    if (sample_time_us <= 1u) {
        sampling = GLH_ADC_SMP_SHORT;
    } else if (sample_time_us <= 5u) {
        sampling = GLH_ADC_SMP_MEDIUM;
    } else if (sample_time_us <= 32u) {
        sampling = GLH_ADC_SMP_LONG;
    } else {
        sampling = GLH_ADC_SMP_LONGEST;
    }
    if (ch == GL_ADC_CH_VREFINT || ch == GL_ADC_CH_MCU_TEMP) {
        sampling = GLH_ADC_SMP_LONGEST; /* internal channels need long sampling */
    }
    st = adc_convert_(channel, sampling, n_avg, &mean);
    if (st == GL_OK) {
        *counts = (uint16_t)((mean > GL_HAL_ADC_FULL_SCALE) ? GL_HAL_ADC_FULL_SCALE : mean);
    }
    return st;
}

float gl_hal_adc_mcu_temp_c(uint16_t counts, uint16_t vdda_mv)
{
    /* Two-point factory calibration (30 C and 130 C at VREF+ = 3.0 V).  The
     * macros and the resolution of the stored values are from memory. */
    const float cal1 = (float)*TEMPSENSOR_CAL1_ADDR;
    const float cal2 = (float)*TEMPSENSOR_CAL2_ADDR;
    const float at_cal = (float)counts * (float)vdda_mv / (float)TEMPSENSOR_CAL_VREFANALOG;
    if (!(cal2 > cal1)) {
        return 1000.0f; /* blank calibration: drivers/power.c rejects the value */
    }
    return (float)TEMPSENSOR_CAL1_TEMP +
           (at_cal - cal1) * (float)(TEMPSENSOR_CAL2_TEMP - TEMPSENSOR_CAL1_TEMP) / (cal2 - cal1);
}

uint16_t gl_hal_adc_vdda_mv(void)
{
    uint32_t raw = 0, mv;
    if (!adc_on_ || adc_convert_(ADC_CHANNEL_VREFINT, GLH_ADC_SMP_LONGEST, 4, &raw) != GL_OK ||
        raw == 0u) {
        return 0;
    }
    mv = __HAL_ADC_CALC_VREFANALOG_VOLTAGE(ADC1, raw, ADC_RESOLUTION_14B);
    return (uint16_t)((mv > 65535u) ? 65535u : mv);
}

gl_status_t gl_hal_opamp_enable(bool on)
{
    if (!on) {
        /* never touch a handle that was not initialised: HAL_OPAMP_DeInit
         * writes through hopamp_.Instance (NULL in a zeroed handle).  This
         * path is taken when the ADC failed to power up before the op-amp
         * was ever enabled (drivers/grain_frontend.c). */
        if (opamp_on_) {
            (void)HAL_OPAMP_Stop(&hopamp_);
            (void)HAL_OPAMP_DeInit(&hopamp_);
            opamp_on_ = false;
        }
        return GL_OK;
    }
    if (opamp_on_) {
        return GL_OK;
    }
    HAL_PWREx_EnableVddA();
    __HAL_RCC_OPAMP_CLK_ENABLE();
    memset(&hopamp_, 0, sizeof(hopamp_));
    hopamp_.Instance = OPAMP1;
    hopamp_.Init.PowerMode = OPAMP_POWERMODE_NORMALPOWER_NORMALSPEED;
    /* standalone: the 470 kohm || 10 pF feedback and the mid-rail bias are
     * external (transimpedance stage) */
    hopamp_.Init.Mode = OPAMP_STANDALONE_MODE;
    hopamp_.Init.InvertingInput = OPAMP_INVERTINGINPUT_IO0;       /* PA1 */
    hopamp_.Init.NonInvertingInput = OPAMP_NONINVERTINGINPUT_IO0; /* PA0 */
    hopamp_.Init.UserTrimming = OPAMP_TRIMMING_FACTORY;
    if (HAL_OPAMP_Init(&hopamp_) != HAL_OK) {
        return GL_ERR_IO;
    }
    if (HAL_OPAMP_Start(&hopamp_) != HAL_OK) {
        (void)HAL_OPAMP_DeInit(&hopamp_); /* Instance is valid here */
        return GL_ERR_IO;
    }
    opamp_on_ = true;
    return GL_OK;
}

/* ======================================================================= */
/* LCD VCOM: LPTIM1 channel 1 PWM, 50 % duty, runs in Stop 2                */
/* ======================================================================= */

gl_status_t gl_hal_extcomin_start(uint16_t period_lse_ticks)
{
    LPTIM_OC_ConfigTypeDef oc;
    if (period_lse_ticks < 2u) {
        return GL_ERR_PARAM;
    }
    if (extcomin_on_) {
        gl_hal_extcomin_stop(); /* restart with the new period */
    }
    __HAL_RCC_LPTIM1_CLK_ENABLE();
    __HAL_RCC_LPTIM1_CLKAM_ENABLE(); /* keep the kernel clock in Stop 2 */
    memset(&hlptim1_, 0, sizeof(hlptim1_));
    hlptim1_.Instance = LPTIM1;
    hlptim1_.Init.Clock.Source = LPTIM_CLOCKSOURCE_APBCLOCK_LPOSC;
    hlptim1_.Init.Clock.Prescaler = LPTIM_PRESCALER_DIV1;
    hlptim1_.Init.Trigger.Source = LPTIM_TRIGSOURCE_SOFTWARE;
    hlptim1_.Init.Period = (uint32_t)period_lse_ticks - 1u;
    hlptim1_.Init.UpdateMode = LPTIM_UPDATE_IMMEDIATE;
    hlptim1_.Init.CounterSource = LPTIM_COUNTERSOURCE_INTERNAL;
    hlptim1_.Init.Input1Source = LPTIM_INPUT1SOURCE_GPIO;
    hlptim1_.Init.Input2Source = LPTIM_INPUT2SOURCE_GPIO;
    hlptim1_.Init.RepetitionCounter = 0;
    if (HAL_LPTIM_Init(&hlptim1_) != HAL_OK) {
        __HAL_RCC_LPTIM1_CLK_DISABLE();
        return GL_ERR_IO;
    }
    memset(&oc, 0, sizeof(oc));
    oc.Pulse = (uint32_t)period_lse_ticks / 2u;
    oc.OCPolarity = LPTIM_OCPOLARITY_HIGH;
    if (HAL_LPTIM_OC_ConfigChannel(&hlptim1_, &oc, LPTIM_CHANNEL_1) != HAL_OK ||
        HAL_LPTIM_PWM_Start(&hlptim1_, LPTIM_CHANNEL_1) != HAL_OK) {
        (void)HAL_LPTIM_DeInit(&hlptim1_); /* Instance is valid here */
        __HAL_RCC_LPTIM1_CLK_DISABLE();
        return GL_ERR_IO;
    }
    extcomin_on_ = true;
    /* Whether the PWM pin keeps toggling in Stop 2 is PROVISIONAL
     * (GL_PROV_LPTIM_PWM_RUNS_IN_STOP2): if it does not, the application
     * stays out of Stop mode while the display is on. */
    return GL_OK;
}

void gl_hal_extcomin_stop(void)
{
    /* The display driver calls this unconditionally when it switches the
     * panel off, which the application does at EVERY BOOT before the timer
     * has ever been started.  hlptim1_ is then a zeroed handle and
     * HAL_LPTIM_PWM_Stop / HAL_LPTIM_DeInit would write through a NULL
     * Instance (a bus fault on the first boot of the target). */
    if (!extcomin_on_) {
        return;
    }
    (void)HAL_LPTIM_PWM_Stop(&hlptim1_, LPTIM_CHANNEL_1);
    (void)HAL_LPTIM_DeInit(&hlptim1_);
    __HAL_RCC_LPTIM1_CLK_DISABLE();
    extcomin_on_ = false;
}

/* ======================================================================= */
/* system                                                                   */
/* ======================================================================= */

/*
 * ORDER MATTERS, and nothing here may return before the application has what
 * it relies on.  The application carries on after an error from this
 * function by design ("a device that failed its start-up checks still
 * runs"): so whatever fails, there must be a watchdog, pins in their safe
 * states, a cycle counter and a tick.
 *
 *   1. the independent watchdog FIRST.  It needs only LSI, which the
 *      hardware starts with it.  From here on a hang anywhere - in the clock
 *      set-up below, in the application's start-up - ends in a reset after
 *      32 s at the latest.  (It used to be started LAST, and a clock error
 *      returned before it: the first delay of the application then waited
 *      for ever on a counter that was never enabled, with no watchdog, and
 *      in a cradle the default-on charger ran with nobody supervising.)
 *   2. clocks.  A crystal that does not start is survived on LSI
 *      (clocks_init_); an error of the internal oscillators leaves the core
 *      on whatever clock it has (SystemCoreClock says which).
 *   3. cycle counter, pins, RTC, tick - always.
 * Returns the FIRST error; GL_ERR_TIMEOUT for "running without the crystal".
 * A hang BEFORE step 1 (dfu_check_, HAL_Init) is not covered by the software
 * start; the IWDG_SW option bit (hardware watchdog) would cover it and is a
 * production decision (README).
 */
gl_status_t gl_hal_init(void)
{
    gl_status_t st, first = GL_OK;

    dfu_check_(); /* may not return */
    if (HAL_Init() != HAL_OK) {
        first = GL_ERR_IO; /* (the tick could not be set up; carry on) */
    }
    /* 1. independent watchdog, about 32 s; it keeps running in Stop mode,
     * so the application wakes every 16 s to refresh it.  HAL_IWDG_Init()
     * starts it with its first write; a time-out of the prescaler update
     * that follows does not stop it. */
    memset(&hiwdg_, 0, sizeof(hiwdg_));
    hiwdg_.Instance = IWDG;
    hiwdg_.Init.Prescaler = IWDG_PRESCALER_256;
    hiwdg_.Init.Reload = GLH_IWDG_RELOAD;
    hiwdg_.Init.Window = IWDG_WINDOW_DISABLE;
    hiwdg_.Init.EWI = 0;
    if (HAL_IWDG_Init(&hiwdg_) != HAL_OK && first == GL_OK) {
        first = GL_ERR_IO;
    }
    reset_flags_ = read_reset_flags_();
    /* 2. clocks */
    st = clocks_init_();
    if (st != GL_OK) {
        /* not even the internal oscillators: stay on the clock there is */
        SystemCoreClockUpdate();
        sysclk_hz_ = (SystemCoreClock >= 1000000u) ? SystemCoreClock : 1000000u;
        if (first == GL_OK) {
            first = st;
        }
    } else if (!lse_ok_ && first == GL_OK) {
        first = GL_ERR_TIMEOUT; /* running on LSI: degraded, reported */
    }
    (void)HAL_IWDG_Refresh(&hiwdg_); /* the crystal's time-out is 5 s of the 32 */
    /* 3. Instruction cache: the vision code is several million instructions
     * per strip; without the cache every flash access pays the wait states.
     * (1-way mode is the reset default; from memory.) */
    (void)HAL_ICACHE_Enable();
    /* cycle counter for gl_hal_delay_us() */
    DCB->DEMCR |= DCB_DEMCR_TRCENA_Msk;
    DWT->CYCCNT = 0;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;

    gpio_clocks_();
    /* every signal pin analog (lowest leakage; also the camera rail rule) */
    for (int p = 0; p < (int)GL_PIN_COUNT; p++) {
        latch_[p] = false;
        HAL_GPIO_WritePin(pin_[p].port, pin_[p].mask, GPIO_PIN_RESET);
        gl_hal_gpio_mode((gl_pin_t)p, GL_PIN_MODE_ANALOG);
    }
    /* the states gl_hal.h promises after init */
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
    /* CHG_INHIBIT (rev C2: the charger is on by default in hardware, the pin
     * can only stop it) and NTC_BIAS are left ANALOG, as the loop above and
     * the reset before it put them: drivers/power pulls CHG_INHIBIT low only
     * as the result of a temperature measurement, and drives NTC_BIAS only
     * while a conversion runs.  NOTE for the pin choice: CHG_INHIBIT must be
     * a pin without a protection diode to VDD (an FT pin), or the unpowered
     * MCU clamps the MOSFET gate and defeats the default (gl_pins.h). */
    extcomin_on_ = false;
    opamp_on_ = false;
    gl_hal_gpio_mode(GL_PIN_CHG_STAT, GL_PIN_MODE_INPUT_PULLUP);
    gl_hal_gpio_mode(GL_PIN_VBUS_SENSE, GL_PIN_MODE_INPUT);
    gl_hal_gpio_mode(GL_PIN_IMU_INT1, GL_PIN_MODE_INPUT);
    gl_hal_gpio_mode(GL_PIN_IMU_INT2, GL_PIN_MODE_INPUT);
    gl_hal_gpio_mode(GL_PIN_SPI1_SCK, GL_PIN_MODE_ALTERNATE);
    gl_hal_gpio_mode(GL_PIN_SPI1_MOSI, GL_PIN_MODE_ALTERNATE);
    gl_hal_gpio_mode(GL_PIN_SPI1_MISO, GL_PIN_MODE_ALTERNATE);
    gl_hal_gpio_mode(GL_PIN_SPI2_SCK, GL_PIN_MODE_ALTERNATE);
    gl_hal_gpio_mode(GL_PIN_SPI2_MOSI, GL_PIN_MODE_ALTERNATE);
    gl_hal_gpio_mode(GL_PIN_SPI2_MISO, GL_PIN_MODE_ALTERNATE);

    irq_enabled_ = 0;
    irq_pending_ = 0;
    /* the tick does not depend on the RTC: both are attempted */
    st = rtc_init_();
    if (st != GL_OK && first == GL_OK) {
        first = st;
    }
    st = tick_init_();
    if (st != GL_OK && first == GL_OK) {
        first = st;
    }
    return first;
}

uint32_t gl_hal_reset_reason(void)
{
    const uint32_t f = reset_flags_;
    reset_flags_ = 0;
    return f;
}

void gl_hal_reboot(gl_reboot_t how)
{
    if (how == GL_REBOOT_ROM_DFU) {
        /* survive the reset in a backup register; dfu_check_() acts on it */
        HAL_PWR_EnableBkUpAccess();
        TAMP->BKP0R = GLH_DFU_MAGIC;
    }
    NVIC_SystemReset();
    for (;;) {
    }
}

void gl_hal_watchdog_kick(void)
{
    (void)HAL_IWDG_Refresh(&hiwdg_);
}

void gl_hal_unique_id(uint8_t out[12])
{
    const uint32_t w[3] = { HAL_GetUIDw0(), HAL_GetUIDw1(), HAL_GetUIDw2() };
    for (unsigned i = 0; i < 3u; i++) {
        gl_put_u32(&out[4u * i], w[i]);
    }
}
