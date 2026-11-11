/*
 * gl_hal_stm32u5_usb.c - USB CDC-ACM part of the STM32U585 backend of
 * hal/gl_hal.h, written against ST's USB device library (usbd_core,
 * usbd_cdc) on top of the HAL PCD driver.
 *
 * ##########################################################################
 * #  THIS FILE HAS NEVER BEEN COMPILED OR RUN (see gl_hal_stm32u5.c).      #
 * ##########################################################################
 *
 * Not in this repository and needed to build it: the USB device library
 * itself, and the board glue that STM32CubeMX normally generates -
 * usbd_conf.c (PCD low-level callbacks, HAL_PCD_MspInit, OTG_FS_IRQHandler)
 * and usbd_desc.c (device / string descriptors, here expected to export
 * GL_USBD_Desc).  The VID / PID must be assigned before any unit ships.
 *
 * Data path: two byte rings between the USB interrupt context and the main
 * loop (single producer, single consumer each, so no lock is needed on a
 * single core).  Received bytes raise GL_IRQ_USB_RX.
 *
 * Clock: HSI48 with the clock-recovery system locked to the USB start-of-
 * frame (crystal-less USB: PROVISIONAL in DESIGN_SPEC,
 * GL_PROV_USB_CRYSTALLESS_HSI48_CRS).  The USB supply-valid switch is set
 * only here, i.e. only after the application has seen VBUS: VDDUSB comes
 * from its own 3.3 V regulator fed from VBUS (DESIGN_SPEC section 4).
 *
 * RAM: 2 x 1024-byte rings + one 64-byte packet buffer.
 */
#include "stm32u5xx_hal.h"

#include <string.h>

#include "gl_hal.h"
#include "gl_hal_stm32u5_priv.h"
#include "usbd_cdc.h"
#include "usbd_core.h"

#define RING_SIZE 1024u /* power of two */
#define RING_MASK (RING_SIZE - 1u)

typedef struct {
    uint8_t buf[RING_SIZE];
    volatile uint32_t head; /* written by the producer */
    volatile uint32_t tail; /* written by the consumer */
} ring_t;

extern USBD_DescriptorsTypeDef GL_USBD_Desc; /* usbd_desc.c of the project */

static USBD_HandleTypeDef usbd_;
static ring_t rx_, tx_;
static uint8_t rx_packet_[CDC_DATA_FS_MAX_PACKET_SIZE];
static uint8_t tx_packet_[CDC_DATA_FS_MAX_PACKET_SIZE];
static volatile bool started_, dtr_, tx_busy_, rx_stalled_;
static USBD_CDC_LineCodingTypeDef line_coding_ = { 115200, 0, 0, 8 };

static uint32_t ring_used_(const ring_t *r)
{
    return (r->head - r->tail) & RING_MASK;
}

static uint32_t ring_free_(const ring_t *r)
{
    return RING_MASK - ring_used_(r);
}

/* ---- CDC class interface ---------------------------------------------------- */

static int8_t cdc_init_(void)
{
    (void)USBD_CDC_SetRxBuffer(&usbd_, rx_packet_);
    (void)USBD_CDC_ReceivePacket(&usbd_);
    return (int8_t)USBD_OK;
}

static int8_t cdc_deinit_(void)
{
    dtr_ = false;
    return (int8_t)USBD_OK;
}

static int8_t cdc_control_(uint8_t cmd, uint8_t *pbuf, uint16_t length)
{
    (void)length;
    switch (cmd) {
    case CDC_SET_LINE_CODING:
        memcpy(&line_coding_, pbuf, sizeof(line_coding_)); /* ignored: no UART behind it */
        break;
    case CDC_GET_LINE_CODING:
        memcpy(pbuf, &line_coding_, sizeof(line_coding_));
        break;
    case CDC_SET_CONTROL_LINE_STATE:
        /* wValue bit 0 = DTR: the host has opened the port */
        dtr_ = ((((USBD_SetupReqTypedef *)(void *)pbuf)->wValue) & 0x0001u) != 0u;
        break;
    default:
        break;
    }
    return (int8_t)USBD_OK;
}

/* A packet has arrived (interrupt context). */
static int8_t cdc_receive_(uint8_t *buf, uint32_t *len)
{
    const uint32_t n = *len;
    if (n <= ring_free_(&rx_)) {
        for (uint32_t i = 0; i < n; i++) {
            rx_.buf[(rx_.head + i) & RING_MASK] = buf[i];
        }
        rx_.head = (rx_.head + n) & RING_MASK;
        glh_irq_raise(GL_IRQ_USB_RX);
        (void)USBD_CDC_ReceivePacket(&usbd_); /* ready for the next one */
    } else {
        /* no room: leave the endpoint NAKing (flow control) until
         * gl_hal_usb_read() has made room; the packet stays in rx_packet_ */
        rx_stalled_ = true;
        glh_irq_raise(GL_IRQ_USB_RX);
    }
    return (int8_t)USBD_OK;
}

/* Start sending the next piece of the transmit ring, if any. */
static void tx_kick_(void)
{
    uint32_t n = ring_used_(&tx_);
    if (tx_busy_ || n == 0u) {
        return;
    }
    if (n > sizeof(tx_packet_) - 1u) {
        n = sizeof(tx_packet_) - 1u; /* never a full-size packet: no zero-length packet needed */
    }
    for (uint32_t i = 0; i < n; i++) {
        tx_packet_[i] = tx_.buf[(tx_.tail + i) & RING_MASK];
    }
    tx_busy_ = true;
    (void)USBD_CDC_SetTxBuffer(&usbd_, tx_packet_, (uint16_t)n);
    if (USBD_CDC_TransmitPacket(&usbd_) == (uint8_t)USBD_OK) {
        tx_.tail = (tx_.tail + n) & RING_MASK;
    } else {
        tx_busy_ = false; /* not configured or busy: retried at the next write */
    }
}

static int8_t cdc_tx_done_(uint8_t *buf, uint32_t *len, uint8_t epnum)
{
    (void)buf;
    (void)len;
    (void)epnum;
    tx_busy_ = false;
    tx_kick_();
    return (int8_t)USBD_OK;
}

static USBD_CDC_ItfTypeDef cdc_itf_ = { cdc_init_, cdc_deinit_, cdc_control_, cdc_receive_,
                                         cdc_tx_done_ };

/* ---- gl_hal.h ------------------------------------------------------------------ */

gl_status_t gl_hal_usb_start(void)
{
    RCC_OscInitTypeDef osc;
    RCC_PeriphCLKInitTypeDef pclk;
    RCC_CRSInitTypeDef crs;

    if (started_) {
        return GL_OK;
    }
    /* The application has seen VBUS, so the 3.3 V VDDUSB regulator should
     * be up.  It is not taken on trust: the USB voltage monitor must report
     * the supply ready before the supply-valid bit is set (spring pins
     * bounce; a pin that is not powered must not be declared valid).  The
     * monitor API (HAL_PWREx_EnableUVM, PWR_FLAG_VDDUSBRDY) is from memory. */
    HAL_PWREx_EnableUVM();
    {
        uint32_t tries = 0;
        while (!__HAL_PWR_GET_FLAG(PWR_FLAG_VDDUSBRDY)) {
            if (++tries > 10u) {
                HAL_PWREx_DisableUVM();
                return GL_ERR_STATE; /* VDDUSB not present: the application retries on the next VBUS edge */
            }
            gl_hal_delay_ms(1);
        }
    }
    HAL_PWREx_EnableVddUSB();

    memset(&osc, 0, sizeof(osc));
    osc.OscillatorType = RCC_OSCILLATORTYPE_HSI48;
    osc.HSI48State = RCC_HSI48_ON;
    osc.PLL.PLLState = RCC_PLL_NONE;
    if (HAL_RCC_OscConfig(&osc) != HAL_OK) {
        return GL_ERR_IO;
    }
    memset(&pclk, 0, sizeof(pclk));
    pclk.PeriphClockSelection = RCC_PERIPHCLK_ICLK; /* the 48 MHz kernel clock of OTG_FS */
    pclk.IclkClockSelection = RCC_ICLK_CLKSOURCE_HSI48;
    if (HAL_RCCEx_PeriphCLKConfig(&pclk) != HAL_OK) {
        return GL_ERR_IO;
    }
    /* trim HSI48 on the 1 kHz start-of-frame */
    __HAL_RCC_CRS_CLK_ENABLE();
    memset(&crs, 0, sizeof(crs));
    crs.Prescaler = RCC_CRS_SYNC_DIV1;
    crs.Source = RCC_CRS_SYNC_SOURCE_USB;
    crs.Polarity = RCC_CRS_SYNC_POLARITY_RISING;
    crs.ReloadValue = __HAL_RCC_CRS_RELOADVALUE_CALCULATE(48000000u, 1000u);
    crs.ErrorLimitValue = RCC_CRS_ERRORLIMIT_DEFAULT;
    crs.HSI48CalibrationValue = RCC_CRS_HSI48CALIBRATION_DEFAULT;
    HAL_RCCEx_CRSConfig(&crs);

    gl_hal_gpio_mode(GL_PIN_USB_DM, GL_PIN_MODE_ALTERNATE);
    gl_hal_gpio_mode(GL_PIN_USB_DP, GL_PIN_MODE_ALTERNATE);

    rx_.head = rx_.tail = 0;
    tx_.head = tx_.tail = 0;
    dtr_ = false;
    tx_busy_ = false;
    rx_stalled_ = false;
    if (USBD_Init(&usbd_, &GL_USBD_Desc, 0) != USBD_OK ||
        USBD_RegisterClass(&usbd_, &USBD_CDC) != USBD_OK ||
        USBD_CDC_RegisterInterface(&usbd_, &cdc_itf_) != USBD_OK || USBD_Start(&usbd_) != USBD_OK) {
        return GL_ERR_IO;
    }
    started_ = true;
    return GL_OK;
}

void gl_hal_usb_stop(void)
{
    RCC_OscInitTypeDef osc;
    if (!started_) {
        return;
    }
    (void)USBD_Stop(&usbd_);
    (void)USBD_DeInit(&usbd_);
    started_ = false;
    dtr_ = false;
    /* D+ / D- high impedance, 48 MHz oscillator and USB supply switch off */
    gl_hal_gpio_mode(GL_PIN_USB_DM, GL_PIN_MODE_ANALOG);
    gl_hal_gpio_mode(GL_PIN_USB_DP, GL_PIN_MODE_ANALOG);
    __HAL_RCC_CRS_CLK_DISABLE();
    memset(&osc, 0, sizeof(osc));
    osc.OscillatorType = RCC_OSCILLATORTYPE_HSI48;
    osc.HSI48State = RCC_HSI48_OFF;
    osc.PLL.PLLState = RCC_PLL_NONE;
    (void)HAL_RCC_OscConfig(&osc);
    HAL_PWREx_DisableVddUSB();
    HAL_PWREx_DisableUVM();
}

bool gl_hal_usb_connected(void)
{
    return started_ && dtr_ && usbd_.dev_state == USBD_STATE_CONFIGURED;
}

size_t gl_hal_usb_read(uint8_t *buf, size_t max)
{
    uint32_t n = ring_used_(&rx_);
    if (!started_ || buf == NULL) {
        return 0;
    }
    if (n > max) {
        n = (uint32_t)max;
    }
    for (uint32_t i = 0; i < n; i++) {
        buf[i] = rx_.buf[(rx_.tail + i) & RING_MASK];
    }
    rx_.tail = (rx_.tail + n) & RING_MASK;
    /* a packet that found no room earlier: take it now and re-arm the endpoint */
    if (rx_stalled_ && ring_free_(&rx_) >= sizeof(rx_packet_)) {
        uint32_t len = USBD_LL_GetRxDataSize(&usbd_, CDC_OUT_EP);
        gl_hal_irq_lock();
        rx_stalled_ = false;
        (void)cdc_receive_(rx_packet_, &len);
        gl_hal_irq_unlock();
    }
    return n;
}

size_t gl_hal_usb_write(const uint8_t *buf, size_t len)
{
    uint32_t n = ring_free_(&tx_);
    if (!gl_hal_usb_connected() || buf == NULL) {
        return 0;
    }
    if (n > len) {
        n = (uint32_t)len;
    }
    for (uint32_t i = 0; i < n; i++) {
        tx_.buf[(tx_.head + i) & RING_MASK] = buf[i];
    }
    tx_.head = (tx_.head + n) & RING_MASK;
    gl_hal_irq_lock(); /* tx_kick_() is also called from the USB interrupt */
    tx_kick_();
    gl_hal_irq_unlock();
    return n;
}
