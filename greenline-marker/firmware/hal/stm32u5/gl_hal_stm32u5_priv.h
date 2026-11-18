/*
 * gl_hal_stm32u5_priv.h - shared between the two files of the STM32U5
 * backend.  Compiled only by `make cross-hal` (with gl_hal_stm32u5.c; see
 * there).
 */
#ifndef GL_HAL_STM32U5_PRIV_H
#define GL_HAL_STM32U5_PRIV_H

#include <stdbool.h>
#include <stdint.h>

/** Latch interrupt-source bits (GL_IRQ_*) from an interrupt handler; only
 *  the enabled ones are kept. */
void glh_irq_raise(uint32_t bit);

/** gl_hal_stm32u5_usb.c: the USB device is in standby (attached to a
 *  suspended bus, its clocks stopped): the core then sleeps in a Stop mode
 *  the host's resume can wake it from. */
bool glh_usb_in_standby(void);

#endif /* GL_HAL_STM32U5_PRIV_H */
