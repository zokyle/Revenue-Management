/*
 * gl_boot_stm32u5.c - the STM32U585 part of the boot stub: its vector table
 * and reset handler, reading the inputs of gl_boot_decide(), and the three
 * things it can do.  Written against the device header only (no HAL, no C
 * library, no start-up file): nothing in the stub uses initialised data, so
 * there is no copy loop; the stack is the first thing the core loads.
 *
 * ##########################################################################
 * #  WRITTEN BY INSPECTION.  It compiles and links (`make boot-cross`,     #
 * #  against the vendor's device header) and HAS NEVER RUN: there is no     #
 * #  hardware.  Everything marked PROVISIONAL is from memory of the         #
 * #  reference manual (RM0456) and AN2606 and is a RELEASE GATE.            #
 * ##########################################################################
 *
 * OPTION BYTES AND WRITE PROTECTION (set once at the factory, by SWD on the
 * cradle's service pins, with the programmer - the stub does not write
 * option bytes; it checks them and records the result):
 *
 *   WRP1AR   PSTRT = 0, PEND = 0, UNLOCK = 1   page 0 (this stub) write-
 *            protected.  UNLOCK = 0 would make the protection permanent:
 *            NOT at EVT (a stub with a fault could never be replaced);
 *            a decision for production.
 *   nSWBOOT0 = 0, nBOOT0 = 1   boot from main flash whatever the BOOT0 pin
 *            (PH3) reads: on this board PH3 is CAM_R_PWDN, with a pull-down;
 *            the pin must not decide where the processor starts.
 *   NSBOOTADD0 = 0x08000000 (default)   the stub.
 *   IWDG_SW = 1 (software watchdog; the stub starts it before the image).
 *            IWDG_SW = 0 (hardware watchdog) would also run in the ROM
 *            loader, which does not feed it (PROVISIONAL): not used.
 *   IWDG_STOP = 1, IWDG_STDBY = 0   the watchdog counts in Stop mode (the
 *            application wakes every 16 s to feed it) and is frozen in
 *            Standby; in Shutdown the LSI is off and it does not run
 *            (PROVISIONAL).
 *   RDP level 0 at EVT.  Level 1 for production is a decision; level 2
 *            would end SWD recovery for good.
 *   TZEN = 0  (TrustZone off: with it on, the loader address and the boot
 *            path are different ones).
 *
 * WHAT THE STUB DOES NOT DO: it sets up no clock (it runs on the 4 MHz MSI
 * the core starts with; the CRC of a 400 kB image takes about 1.2 s at
 * that speed - PROVISIONAL, not measured), it does not touch the display,
 * and it verifies no signature: the CRC guards against a broken image, not
 * against a forged one.
 */
#include "gl_boot.h"

#include "stm32u5xx.h"

/* The stub reads ONE board signal, VBUS_SENSE, and wakes on it.  It names the
 * port, the pin and the wake-up line in register macros (GPIOC, ..._MODE13,
 * WUSEL2), which cannot be built from the generated pin table at run time
 * without code the stub does not otherwise need.  So the generated header
 * (hal/stm32u5/gl_pins.h, macros only, from the netlist's pin map) is read
 * here and the build FAILS if the pin map moves VBUS_SENSE: after `make
 * pins` this file then has to follow by hand (vbus_() and wait_vbus_()). */
#include "../hal/stm32u5/gl_pins.h"
#define BOOT_PORT_A_ 0
#define BOOT_PORT_B_ 1
#define BOOT_PORT_C_ 2
#define BOOT_PORT_D_ 3
#define BOOT_PORT_E_ 4
#define BOOT_PORT_F_ 5
#define BOOT_PORT_G_ 6
#define BOOT_PORT_H_ 7
#define BOOT_PIN_ROW_(sig, port, pin, pad, fn, af, pull, brd, exti, rail, sleep, src) \
    BOOT_##sig##_PORT_ = BOOT_PORT_##port##_, BOOT_##sig##_PIN_ = (pin), BOOT_##sig##_BRD_ = (brd),
enum { GL_PINS_TABLE(BOOT_PIN_ROW_) BOOT_PIN_ROWS_END_ };
#undef BOOT_PIN_ROW_
/* C99 has no _Static_assert: an array type of size -1 stops the compiler. */
#define BOOT_REQUIRE_(name, cond) typedef char boot_require_##name##_[(cond) ? 1 : -1]
/* pin map: VBUS_SENSE must be PC13 - else change vbus_() and wait_vbus_() below */
BOOT_REQUIRE_(vbus_sense_is_pc13, (int)BOOT_GL_PIN_VBUS_SENSE_PORT_ == BOOT_PORT_C_ && (int)BOOT_GL_PIN_VBUS_SENSE_PIN_ == 13);
/* pin map: VBUS_SENSE must be held by the divider - vbus_() sets no pull */
BOOT_REQUIRE_(vbus_sense_has_the_divider, (int)BOOT_GL_PIN_VBUS_SENSE_BRD_ == GL_PINBRD_DIVIDER);
/* pin map: VBUS_SENSE must be wake-up pin 2 - else change wait_vbus_() below */
BOOT_REQUIRE_(vbus_sense_is_wkup2, GL_PINS_WKUP_VBUS_SENSE == 2);

extern uint32_t gl_boot_stack_top_; /* from the linker script */

void Reset_Handler(void);
void Default_Handler(void);
void NMI_Handler(void);

/* ---- small services ------------------------------------------------------------- */

static void backup_access_(void)
{
    RCC->AHB3ENR |= RCC_AHB3ENR_PWREN;
    (void)RCC->AHB3ENR;
    PWR->DBPR |= PWR_DBPR_DBP;
    RCC->APB3ENR |= RCC_APB3ENR_RTCAPBEN; /* the TAMP registers' bus clock */
    (void)RCC->APB3ENR;
}

/* VBUS_SENSE: PC13, the divider on the VBUS pad (pin map; GL_PIN_VBUS_SENSE).
 * The static assertions at the top of this file tie port, pin, board circuit
 * and wake-up line to the generated gl_pins.h. */
static bool vbus_(void)
{
    RCC->AHB2ENR1 |= RCC_AHB2ENR1_GPIOCEN;
    (void)RCC->AHB2ENR1;
    GPIOC->MODER &= ~GPIO_MODER_MODE13; /* input */
    GPIOC->PUPDR &= ~GPIO_PUPDR_PUPD13; /* no pull: the divider holds it */
    for (volatile int i = 0; i < 64; i++) {
    }
    return (GPIOC->IDR & GPIO_IDR_ID13) != 0u;
}

static bool wrp_ok_(void)
{
    const uint32_t w = FLASH->WRP1AR;
    const uint32_t start = (w & FLASH_WRP1AR_WRP1A_PSTRT) >> FLASH_WRP1AR_WRP1A_PSTRT_Pos;
    const uint32_t end = (w & FLASH_WRP1AR_WRP1A_PEND) >> FLASH_WRP1AR_WRP1A_PEND_Pos;
    /* protected area A of bank 1 = pages start .. end (none if start > end:
     * the erased state is start 0x7F, end 0 - PROVISIONAL) */
    return start == 0u && end + 1u >= (GL_BOOT_STUB_BYTES / FLASH_PAGE_SIZE) && end < 0x7Fu;
}

/* ---- the three actions ------------------------------------------------------------ */

static void jump_(uint32_t vectors_at)
{
    const uint32_t *v = (const uint32_t *)vectors_at;
    const uint32_t sp = v[0];
    void (*entry)(void) = (void (*)(void))v[1];
    __disable_irq();
    SCB->VTOR = vectors_at; /* (the application sets it again in its own start-up) */
    __set_MSP(sp);
    __enable_irq();
    entry();
    for (;;) {
    }
}

static void start_app_(void)
{
    /* the independent watchdog, as the application sets it up (LSI / 256,
     * 4000 counts: 32 s): an image that hangs before it has configured
     * anything is reset and counted */
    IWDG->KR = 0x0000CCCCu;
    IWDG->KR = 0x00005555u;
    IWDG->PR = 6u;
    IWDG->RLR = 4000u;
    for (volatile uint32_t i = 0; i < 100000u && IWDG->SR != 0u; i++) {
    }
    IWDG->KR = 0x0000AAAAu;
    jump_(GL_BOOT_APP_BASE);
}

static void start_app_quiet_(void)
{
    /* rule 6, ship mode without VBUS: the application's first act is to go
     * back to Shutdown (hal/stm32u5 ship_check_).  NO watchdog is started
     * here and nothing is counted. */
    jump_(GL_BOOT_APP_BASE);
}

static void loader_(void)
{
    /* ST's loader in system memory.  Nothing has been configured that it
     * would have to find undone: no clock change, no peripheral but GPIOC
     * pin 13 as an input, the watchdog NOT started.  UCPD_DBDIS is set (the
     * first statement of Reset_Handler) and survives the jump. */
    jump_(GL_BOOT_ROM_LOADER);
}

static void wait_vbus_(void)
{
    /* Shutdown, woken by a rising edge on VBUS_SENSE = wake-up pin 2 on
     * PC13, which is a reset: the stub runs again.  (The application's own
     * ship mode adds pull-downs for floating lines; a unit that is parked
     * here has no working application and is on its way to the factory.) */
    __disable_irq();
    PWR->WUCR3 = (PWR->WUCR3 & ~PWR_WUCR3_WUSEL2) | PWR_WUCR3_WUSEL2_0; /* PC13 (PROVISIONAL) */
    PWR->WUCR2 &= ~PWR_WUCR2_WUPP2;                                     /* high level */
    PWR->WUCR1 |= PWR_WUCR1_WUPEN2;
    PWR->WUSCR = PWR_WUSCR_CWUF2;
    PWR->CR1 = (PWR->CR1 & ~PWR_CR1_LPMS) | (PWR_CR1_LPMS_2 | PWR_CR1_LPMS_1); /* Shutdown */
    /* The wake-up is an edge.  VBUS may have come between the check that
     * led here and the arming above, and that edge is lost: look again now
     * that the pin is armed, and decide again through a reset if it is
     * there (phase-3 review, hardware finding 7) */
    if (vbus_()) {
        NVIC_SystemReset();
    }
    SCB->SCR |= SCB_SCR_SLEEPDEEP_Msk;
    __WFI();
    NVIC_SystemReset(); /* the entry fell through: a wake-up event was pending */
    for (;;) {
    }
}

/* ---- reset ----------------------------------------------------------------------- */

void Reset_Handler(void)
{
    gl_boot_inputs_t in;
    gl_boot_decision_t d;
    uint32_t csr, faults;
    bool read_image;

    /* FIRST, before any pin is configured (pin map, firmware note 5): the
     * dead-battery pull-downs of the UCPD pads off - PA15 is CHG_STAT,
     * PB15 is SPI2_MOSI */
    RCC->AHB3ENR |= RCC_AHB3ENR_PWREN;
    (void)RCC->AHB3ENR;
    PWR->UCPDR |= PWR_UCPDR_UCPD_DBDIS;

    backup_access_();
    /* the reset flags are READ, not cleared: the application reads and
     * clears them when it starts (hal/stm32u5, read_reset_flags_).  If an
     * image never gets that far a stale watchdog flag stays set, and every
     * later unconfirmed start counts as failed: the safe side */
    csr = RCC->CSR;
    in.abnormal_reset = (csr & (RCC_CSR_IWDGRSTF | RCC_CSR_WWDGRSTF | RCC_CSR_SFTRSTF)) != 0u;
    in.update_requested = (TAMP->BKP0R == GL_BOOT_UPDATE_MAGIC);
    in.attempts_reg = TAMP->BKP3R;
    in.vbus = vbus_();
    in.ship_mode = (TAMP->BKP2R == GL_BOOT_SHIP_MAGIC);
    /* rule 0: the image is read only if earlier passes have not shown that
     * reading it faults.  A flash word that cannot be read raises NMI in
     * the middle of the check below; NMI_Handler notes it in BKP5R and
     * returns, and the verdict is taken from there, whatever the CRC of the
     * garbage came to */
    faults = TAMP->BKP5R;
    read_image = gl_boot_may_read_image(faults);
    in.image_valid = false;
    if (read_image) {
        in.image_valid = gl_boot_image_check((const uint8_t *)GL_BOOT_APP_BASE, GL_BOOT_APP_MAX_BYTES,
                                             GL_BOOT_APP_BASE, NULL) == GL_BOOT_IMG_OK;
        faults = TAMP->BKP5R; /* as the handler may have left it */
        if (!gl_boot_may_read_image(faults)) {
            in.image_valid = false;
        }
    }
    gl_boot_decide(&in, &d);
    TAMP->BKP5R = gl_boot_faults_after(faults, read_image, d.action);

    if (d.clear_request) {
        TAMP->BKP0R = 0u;
    }
    TAMP->BKP3R = d.attempts_reg;
    /* for the application and for the factory: what the stub found and did.
     * BKP4R: bits 0..7 why, 8..15 action, 16 write protection of the stub
     * in place, 24..31 the reset flags as the stub found them */
    TAMP->BKP4R = (uint32_t)d.why | ((uint32_t)d.action << 8) | (wrp_ok_() ? 0x10000u : 0u) |
                  (csr & 0xFF000000u);

    if (d.action == (uint8_t)GL_BOOT_LOADER) {
        loader_();
    } else if (d.action == (uint8_t)GL_BOOT_WAIT_VBUS) {
        wait_vbus_();
    } else if (d.action == (uint8_t)GL_BOOT_START_APP_QUIET) {
        start_app_quiet_();
    }
    start_app_();
}

/* A fault inside the stub (rule 0): COUNT it in BKP5R, then reset.  An
 * unconditional reset here - what this handler did until the phase-3 review
 * - loops for ever on anything that faults on every pass, and never reaches
 * gl_boot_decide(): after GL_BOOT_MAX_STUB_FAULTS passes the stub stops
 * reading the image and treats it as invalid. */
void Default_Handler(void)
{
    backup_access_();
    TAMP->BKP5R = gl_boot_fault_note(TAMP->BKP5R, false);
    NVIC_SystemReset();
    for (;;) {
    }
}

/* NMI.  On the STM32U5 an uncorrectable (double-bit) error of a flash word
 * that is being READ sets ECCD in FLASH_ECCR and raises NMI (PROVISIONAL:
 * from memory of RM0456, not read; a release gate).  That is the image
 * whose programming was cut short.  Note it, clear the flag (write 1) and
 * RETURN: the read that raised it completes with whatever data, the check
 * in Reset_Handler runs to its end, finds the note and calls the image
 * invalid.  An NMI from anything else is a fault like any other. */
void NMI_Handler(void)
{
    if ((FLASH->ECCR & FLASH_ECCR_ECCD) != 0u) {
        FLASH->ECCR |= FLASH_ECCR_ECCD;
        backup_access_();
        TAMP->BKP5R = gl_boot_fault_note(TAMP->BKP5R, true);
        return;
    }
    Default_Handler();
}

/* The stub's own vector table: stack, reset, and the same handler for
 * every fault but NMI (no interrupt is ever enabled). */
__attribute__((section(".isr_vector"), used))
static const void *const vectors_[16] = {
    &gl_boot_stack_top_,
    (const void *)Reset_Handler,
    (const void *)NMI_Handler,     /* NMI: the flash's "uncorrectable word" (rule 0) */
    (const void *)Default_Handler, /* HardFault */
    (const void *)Default_Handler, /* MemManage */
    (const void *)Default_Handler, /* BusFault */
    (const void *)Default_Handler, /* UsageFault */
    (const void *)Default_Handler, /* SecureFault */
    0, 0, 0,
    (const void *)Default_Handler, /* SVCall */
    (const void *)Default_Handler, /* DebugMon */
    0,
    (const void *)Default_Handler, /* PendSV */
    (const void *)Default_Handler, /* SysTick */
};
