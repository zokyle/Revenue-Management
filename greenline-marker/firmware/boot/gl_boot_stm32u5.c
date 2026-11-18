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

extern uint32_t gl_boot_stack_top_; /* from the linker script */

void Reset_Handler(void);
void Default_Handler(void);

/* ---- small services ------------------------------------------------------------- */

static void backup_access_(void)
{
    RCC->AHB3ENR |= RCC_AHB3ENR_PWREN;
    (void)RCC->AHB3ENR;
    PWR->DBPR |= PWR_DBPR_DBP;
    RCC->APB3ENR |= RCC_APB3ENR_RTCAPBEN; /* the TAMP registers' bus clock */
    (void)RCC->APB3ENR;
}

/* VBUS_SENSE: PC13, the divider on the VBUS pad (pin map; GL_PIN_VBUS_SENSE). */
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
    SCB->SCR |= SCB_SCR_SLEEPDEEP_Msk;
    __WFI();
    NVIC_SystemReset(); /* VBUS came between the check and the WFI */
    for (;;) {
    }
}

/* ---- reset ----------------------------------------------------------------------- */

void Reset_Handler(void)
{
    gl_boot_inputs_t in;
    gl_boot_decision_t d;
    uint32_t csr;

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
    in.image_valid = gl_boot_image_check((const uint8_t *)GL_BOOT_APP_BASE, GL_BOOT_APP_MAX_BYTES,
                                         GL_BOOT_APP_BASE, NULL) == GL_BOOT_IMG_OK;
    gl_boot_decide(&in, &d);

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
    }
    start_app_();
}

void Default_Handler(void)
{
    /* a fault inside the stub: reset and try again (the stub has no state
     * that a second pass could make worse) */
    NVIC_SystemReset();
    for (;;) {
    }
}

/* The stub's own vector table: stack, reset, and the same handler for
 * every fault (no interrupt is ever enabled). */
__attribute__((section(".isr_vector"), used))
static const void *const vectors_[16] = {
    &gl_boot_stack_top_,
    (const void *)Reset_Handler,
    (const void *)Default_Handler, /* NMI */
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
