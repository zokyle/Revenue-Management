/*
 * stm32u5xx_hal_conf.h - configuration of ST's STM32U5 HAL for the GL-1.
 *
 * The HAL's umbrella header (stm32u5xx_hal.h) includes a file of this name
 * from the PROJECT; every STM32Cube project supplies its own.  This one is
 * written for the GL-1 backend (hal/stm32u5/gl_hal_stm32u5*.c): it enables
 * exactly the HAL modules that backend calls, states the oscillator values
 * of this board, and includes the module headers.  It is NOT ST's file: no
 * vendor file is part of this repository (see README, "STM32 backend").
 *
 * Checked by `make cross-hal STM32_HEADERS=<dir>` against the real headers of
 * the HAL release named in the README: the backend compiles with it.  Like
 * the backend itself it has never been part of a linked image or run.
 */
#ifndef STM32U5xx_HAL_CONF_H
#define STM32U5xx_HAL_CONF_H

#ifdef __cplusplus
extern "C" {
#endif

/* ---- modules the backend uses ------------------------------------------------ */
#define HAL_MODULE_ENABLED
#define HAL_ADC_MODULE_ENABLED     /* battery, NTC, grain photodiode, die temperature */
#define HAL_CORTEX_MODULE_ENABLED  /* NVIC, SysTick */
#define HAL_DCMI_MODULE_ENABLED    /* camera strips */
#define HAL_DMA_MODULE_ENABLED     /* GPDMA1 channel 0 for the DCMI */
#define HAL_EXTI_MODULE_ENABLED
#define HAL_FLASH_MODULE_ENABLED   /* latency, used by the RCC driver */
#define HAL_GPIO_MODULE_ENABLED
#define HAL_ICACHE_MODULE_ENABLED
#define HAL_IWDG_MODULE_ENABLED
#define HAL_LPTIM_MODULE_ENABLED   /* LPTIM1 EXTCOMIN, LPTIM3 tick */
#define HAL_OPAMP_MODULE_ENABLED   /* OPAMP1, grain transimpedance stage */
#define HAL_PCD_MODULE_ENABLED     /* USB device (gl_hal_stm32u5_usb.c, usbd_conf.c) */
#define HAL_PWR_MODULE_ENABLED
#define HAL_RCC_MODULE_ENABLED
#define HAL_RTC_MODULE_ENABLED     /* calendar, wake-up timer */
#define HAL_SPI_MODULE_ENABLED     /* SPI1 LCD + flash, SPI2 IMU */

/* ---- oscillators of this board (DESIGN_SPEC section 4) ----------------------- */
/* No high-speed crystal is fitted.  HSE_VALUE must still be defined for the
 * RCC driver; nothing in the backend selects HSE. */
#define HSE_VALUE 16000000UL
#define HSE_STARTUP_TIMEOUT 100UL /* ms */
/* MSI_VALUE is the range after reset (4 MHz): SystemCoreClock starts from it. */
#define MSI_VALUE 4000000UL
#define HSI_VALUE 16000000UL
#define HSI48_VALUE 48000000UL        /* USB, with clock recovery */
#define LSI_VALUE 32000UL             /* independent watchdog */
#define LSI_STARTUP_TIMEOUT 130UL     /* us */
#define LSE_VALUE 32768UL             /* Y1: tick, RTC, EXTCOMIN, MSI trimming */
#define LSE_STARTUP_TIMEOUT 5000UL    /* ms */
#define EXTERNAL_SAI1_CLOCK_VALUE 48000UL /* not used; the RCC driver wants the name */

/* ---- system --------------------------------------------------------------- */
#define VDD_VALUE 2800UL /* mV: the always-on rail is 2.8 V (MCP1700-2.8) */
#define TICK_INT_PRIORITY ((1UL << __NVIC_PRIO_BITS) - 1UL) /* SysTick: lowest */
#define USE_RTOS 0U
#define PREFETCH_ENABLE 1U
/* #define USE_FULL_ASSERT 1U */

/* ---- no registered callbacks: the backend overrides the weak ones --------- */
#define USE_HAL_ADC_REGISTER_CALLBACKS 0U
#define USE_HAL_DCMI_REGISTER_CALLBACKS 0U
#define USE_HAL_IWDG_REGISTER_CALLBACKS 0U
#define USE_HAL_LPTIM_REGISTER_CALLBACKS 0U
#define USE_HAL_OPAMP_REGISTER_CALLBACKS 0U
#define USE_HAL_PCD_REGISTER_CALLBACKS 0U
#define USE_HAL_RTC_REGISTER_CALLBACKS 0U
#define USE_HAL_SPI_REGISTER_CALLBACKS 0U

#define USE_SPI_CRC 0U /* no CRC on either bus */

/* ---- module headers --------------------------------------------------------- */
#include "stm32u5xx_hal_rcc.h"
#include "stm32u5xx_hal_gpio.h"
#include "stm32u5xx_hal_icache.h"
#include "stm32u5xx_hal_dma.h"
#include "stm32u5xx_hal_cortex.h"
#include "stm32u5xx_hal_adc.h"
#include "stm32u5xx_hal_flash.h"
#include "stm32u5xx_hal_iwdg.h"
#include "stm32u5xx_hal_lptim.h"
#include "stm32u5xx_hal_opamp.h"
#include "stm32u5xx_hal_pwr.h"
#include "stm32u5xx_hal_rtc.h"
#include "stm32u5xx_hal_spi.h"
#include "stm32u5xx_hal_exti.h"
#include "stm32u5xx_hal_dcmi.h"
#include "stm32u5xx_hal_pcd.h"

/* ---- parameter checks -------------------------------------------------------- */
#ifdef USE_FULL_ASSERT
void assert_failed(uint8_t *file, uint32_t line);
#define assert_param(expr) ((expr) ? (void)0U : assert_failed((uint8_t *)__FILE__, __LINE__))
#else
#define assert_param(expr) ((void)0U)
#endif

#ifdef __cplusplus
}
#endif
#endif /* STM32U5xx_HAL_CONF_H */
