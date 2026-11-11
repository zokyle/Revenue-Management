/*
 * gl_hal_stm32u5_priv.h - shared between the two files of the STM32U5
 * backend.  NOT COMPILED in this repository (see gl_hal_stm32u5.c).
 */
#ifndef GL_HAL_STM32U5_PRIV_H
#define GL_HAL_STM32U5_PRIV_H

#include <stdint.h>

/** Latch interrupt-source bits (GL_IRQ_*) from an interrupt handler; only
 *  the enabled ones are kept. */
void glh_irq_raise(uint32_t bit);

#endif /* GL_HAL_STM32U5_PRIV_H */
