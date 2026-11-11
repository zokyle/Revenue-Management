/*
 * gl_crc.h - CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF, no reflection,
 * no final XOR).  Check value: gl_crc16("123456789", 9) == 0x29B1.
 * Used by the USB protocol (gl_proto) and the flash log (gl_log).
 */
#ifndef GL_CRC_H
#define GL_CRC_H

#include <stddef.h>
#include <stdint.h>

#define GL_CRC16_INIT 0xFFFFu

/** Continue a CRC over `len` more bytes.  Start with GL_CRC16_INIT. */
uint16_t gl_crc16_update(uint16_t crc, const uint8_t *data, size_t len);

/** CRC of one buffer. */
uint16_t gl_crc16(const uint8_t *data, size_t len);

#endif /* GL_CRC_H */
