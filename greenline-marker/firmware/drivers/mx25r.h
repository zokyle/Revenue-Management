/*
 * mx25r.h - Macronix MX25R6435F 64 Mbit (8 MB) SPI NOR flash on SPI1.
 *
 * Only the standard SPI-NOR command set is used (opcodes FROM MEMORY, see
 * the README table "from memory - verify against datasheet"):
 *
 *   9Fh RDID   -> C2h 28h 17h (manufacturer, type, density)
 *   05h RDSR   -> status: bit 0 WIP (write in progress), bit 1 WEL
 *   06h WREN   set the write-enable latch (needed before every PP / SE)
 *   03h READ   + 3 address bytes, then data
 *   02h PP     + 3 address bytes + 1..256 bytes inside one 256-byte page
 *   20h SE     + 3 address bytes: erase one 4 kB sector
 *   B9h DP     deep power-down          ABh RDP  release from it
 *
 * SPI mode 0, MSB first.  SPI1 is shared with the display, so the bus is
 * reconfigured before every transaction.
 *
 * The driver exposes the gl_flash_if_t that core/gl_log.h needs (sector =
 * 4 kB).  It wakes the device on demand; the application calls
 * gl_mx25r_sleep() before the MCU sleeps.
 *
 * RAM: sizeof(gl_mx25r_t) = 20 bytes.  Stack: under 64 bytes.  A sector
 * erase blocks for its duration (tens of ms; time-out
 * GL_PROV_MX25R_ERASE_TIMEOUT_MS).
 */
#ifndef GL_MX25R_H
#define GL_MX25R_H

#include "gl_log.h"
#include "gl_types.h"

#define GL_MX25R_SIZE_BYTES (8u * 1024u * 1024u)
#define GL_MX25R_SECTOR_BYTES 4096u
#define GL_MX25R_PAGE_BYTES 256u

#define GL_MX25R_CMD_RDID 0x9Fu
#define GL_MX25R_CMD_RDSR 0x05u
#define GL_MX25R_CMD_WREN 0x06u
#define GL_MX25R_CMD_READ 0x03u
#define GL_MX25R_CMD_PP   0x02u
#define GL_MX25R_CMD_SE   0x20u
#define GL_MX25R_CMD_DP   0xB9u
#define GL_MX25R_CMD_RDP  0xABu
#define GL_MX25R_SR_WIP   0x01u
#define GL_MX25R_SR_WEL   0x02u
/** Expected JEDEC id bytes. */
#define GL_MX25R_ID_MFR   0xC2u
#define GL_MX25R_ID_TYPE  0x28u
#define GL_MX25R_ID_DENS  0x17u

typedef struct {
    bool present;
    bool asleep;        /**< in deep power-down */
    uint8_t id[3];      /**< JEDEC id as read */
    uint32_t page_programs;
    uint32_t sector_erases;
} gl_mx25r_t;

/** Release from deep power-down, read and check the JEDEC id.
 *  GL_ERR_NOT_FOUND if the id does not match. */
gl_status_t gl_mx25r_init(gl_mx25r_t *f);

/** Read `len` bytes at `addr`.  GL_ERR_PARAM beyond the end of the device. */
gl_status_t gl_mx25r_read(gl_mx25r_t *f, uint32_t addr, uint8_t *buf, size_t len);

/** Program `len` bytes at `addr`; the data are split at page boundaries.
 *  The target bytes must be erased (the device ANDs).  Blocks until done. */
gl_status_t gl_mx25r_prog(gl_mx25r_t *f, uint32_t addr, const uint8_t *buf, size_t len);

/** Erase the 4 kB sector containing `addr`.  Blocks until done. */
gl_status_t gl_mx25r_erase_sector(gl_mx25r_t *f, uint32_t addr);

/** Enter / leave deep power-down. */
gl_status_t gl_mx25r_sleep(gl_mx25r_t *f);
gl_status_t gl_mx25r_wake(gl_mx25r_t *f);

/** Fill in the flash interface used by gl_log / gl_store (ctx = f). */
void gl_mx25r_flash_if(gl_mx25r_t *f, gl_flash_if_t *out);

#endif /* GL_MX25R_H */
