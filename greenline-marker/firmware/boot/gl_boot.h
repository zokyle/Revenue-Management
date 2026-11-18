/*
 * gl_boot.h - the boot stub of the GL-1 (DESIGN_SPEC E34).
 *
 * WHY.  The cell is sealed in and there is no reset button.  A firmware
 * update that is interrupted, or an image that does not run, must not
 * strand the unit: a small program that is never rewritten sits at the
 * start of flash, checks the application image before it starts it, and
 * hands the processor to ST's built-in USB loader (system memory) when the
 * image is not valid, when the application asked for an update, or when the
 * image has been started three times and each start ended in a reset
 * without the application saying that it runs.
 *
 * FLASH LAYOUT (STM32U585, 2 MB, pages of 8 kB)
 *
 *   0x08000000  boot stub: page 0 (8 kB), WRITE-PROTECTED (WRP1A = pages
 *               0..0).  Never touched by an update: the loader is told to
 *               write from 0x08002000 on.
 *   0x08002000  application image:
 *                 +0x000  vector table of the application (its own)
 *                 +0x400  image header, 32 bytes (gl_boot_header_t)
 *                 +0x420  code and data
 *               The STM32U585 has 16 + 126 vectors (568 bytes): the header
 *               lies behind the table, at a fixed offset.
 *
 * IMAGE HEADER (little-endian), written by tools/stamp_image.py:
 *
 *   0   u32 magic      "GLIM" = 0x4D494C47
 *   4   u16 hdr_version  1
 *   6   u16 hw_rev       board revision the image is for (5 = rev E)
 *   8   u32 length     bytes of the image from 0x08002000, header included;
 *                      a multiple of 4, at least 0x420, at most the region
 *   12  u32 crc32      CRC-32 (zlib) of the `length` bytes with THE TWO CRC
 *                      FIELDS OF THIS HEADER (bytes 12..15, 28..31) TAKEN AS
 *                      ZERO
 *   16  u32 fw_version major << 8 | minor (GL_APP_FW_VERSION)
 *   20  u32 fw_build   GL_APP_FW_BUILD
 *   24  u32 reserved (0)
 *   28  u32 hdr_crc    CRC-32 of header bytes 0..27 with the crc32 field as
 *                      stamped: a header that was half written is refused
 *                      before its length is believed
 *
 * AN IMAGE IS VALID when: the header's own CRC is right; magic, header
 * version and board revision are the stub's; the length is plausible; the
 * initial stack pointer lies in the RAM and the reset vector inside the
 * image, odd (Thumb); and the CRC-32 over the whole length is right.
 *
 * THE RULE (gl_boot_decide(), the whole of it):
 *
 *   1. An UPDATE WAS REQUESTED (the application wrote GL_BOOT_UPDATE_MAGIC
 *      into backup register GL_BOOT_BKP_REQUEST and reset): the request is
 *      cleared - one attempt - and, if VBUS is present, the USB loader is
 *      started.  Without VBUS there is no host: the request is dropped.
 *   2. The stub decided earlier that this unit must go to the loader and
 *      could not (no VBUS): it goes now if VBUS is there, else back to
 *      waiting.
 *   3. The IMAGE IS NOT VALID: the loader if VBUS is present; otherwise the
 *      stub waits for VBUS in Shutdown (a loader without a host would only
 *      empty the cell) and remembers (2).
 *   4. THE WATCHDOG LOOP.  The stub counts the starts of the application in
 *      backup register GL_BOOT_BKP_ATTEMPTS; the application clears the
 *      count when its main loop has run for 10 s (gl_hal_boot_confirm) and
 *      before every reset it makes on purpose.  If the stub finds the count
 *      not cleared, the last start was NOT confirmed.  It counts as FAILED
 *      if the reset that ended it was a watchdog or a software reset (a
 *      hang, a fault handler, an assertion); a power-on, brown-out, pin or
 *      wake-up reset says nothing about the image and clears the count.
 *      At GL_BOOT_MAX_FAILED_STARTS failed starts in a row the image is
 *      treated as in (3): loader, or wait for VBUS.  The count is cleared
 *      when the loader is entered: after an update, or after the host let
 *      the unit go, the image gets its three starts again.
 *   5. Otherwise the stub starts the INDEPENDENT WATCHDOG (so that an image
 *      that hangs before it has set up anything still comes back), counts
 *      the start and jumps to the application.
 *
 * A bad image therefore shows itself as a unit that sits in the USB loader
 * in its cradle - seen by the PC as ST's DFU device - after at most three
 * watchdog periods, instead of resetting for ever behind a dark display.
 *
 * NOT VERIFIED - no hardware exists (README, release gates): the entry
 * conditions of the ROM loader (address, that a jump from a running stub
 * with these pins works, which interfaces it listens on), the write
 * protection and option bytes, the relocation of the vector table by the
 * application, what the backup registers and the watchdog do across
 * Shutdown.  The decision logic and the image check are tested on the host
 * (tests/test_boot.c); the STM32 part compiles and links against the
 * vendor's device header (`make boot-cross`) and has never run.
 */
#ifndef GL_BOOT_H
#define GL_BOOT_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* ---- layout ----------------------------------------------------------------- */
#define GL_BOOT_FLASH_BASE 0x08000000u
#define GL_BOOT_STUB_BYTES 0x2000u                       /* page 0: 8 kB */
#define GL_BOOT_APP_BASE (GL_BOOT_FLASH_BASE + GL_BOOT_STUB_BYTES)
#define GL_BOOT_FLASH_BYTES 0x200000u                    /* 2 MB */
#define GL_BOOT_APP_MAX_BYTES (GL_BOOT_FLASH_BYTES - GL_BOOT_STUB_BYTES)
#define GL_BOOT_HDR_OFFSET 0x400u
#define GL_BOOT_HDR_LEN 32u
#define GL_BOOT_RAM_BASE 0x20000000u
#define GL_BOOT_RAM_BYTES 0x000C0000u                    /* 768 kB of SRAM1..3 */
#define GL_BOOT_ROM_LOADER 0x0BF90000u                   /* system memory (AN2606; from memory:
                                                            PROVISIONAL, a release gate) */

#define GL_BOOT_MAGIC 0x4D494C47u /* "GLIM" */
#define GL_BOOT_HDR_VERSION 1u
#define GL_BOOT_HW_REV 5u

/* ---- retained state: TAMP backup registers ------------------------------------ */
#define GL_BOOT_BKP_REQUEST 0u  /* BKP0R: the application's request for the loader */
#define GL_BOOT_BKP_ATTEMPTS 3u /* BKP3R: the stub's count of unconfirmed starts */
#define GL_BOOT_UPDATE_MAGIC 0x474C4446u /* "GLDF" (hal/stm32u5: GLH_DFU_MAGIC) */
#define GL_BOOT_ATTEMPTS_MAGIC 0x474C4200u /* "GLB" in the upper 24 bits of BKP3R ... */
#define GL_BOOT_ATTEMPTS_COUNT_MASK 0x7Fu  /* ... the count in the low 7 ... */
#define GL_BOOT_ATTEMPTS_TO_LOADER 0x80u   /* ... and "go to the loader when VBUS is there" */
#define GL_BOOT_MAX_FAILED_STARTS 3u

/* ---- the image ------------------------------------------------------------------ */
typedef struct {
    uint32_t magic;
    uint16_t hdr_version;
    uint16_t hw_rev;
    uint32_t length;
    uint32_t crc32;
    uint32_t fw_version;
    uint32_t fw_build;
    uint32_t reserved;
    uint32_t hdr_crc;
} gl_boot_header_t;

typedef enum {
    GL_BOOT_IMG_OK = 0,
    GL_BOOT_IMG_NO_HEADER,    /**< magic or the header's own CRC wrong (blank or half-written flash) */
    GL_BOOT_IMG_BAD_VERSION,  /**< a header layout this stub does not know */
    GL_BOOT_IMG_BAD_HW,       /**< an image for another board revision */
    GL_BOOT_IMG_BAD_LENGTH,
    GL_BOOT_IMG_BAD_VECTORS,  /**< stack pointer outside the RAM, or reset vector outside the image / even */
    GL_BOOT_IMG_BAD_CRC
} gl_boot_img_t;

/** CRC-32 (zlib).  Start with 0, chain to continue. */
uint32_t gl_boot_crc32(uint32_t crc, const uint8_t *data, size_t len);

/** Read the header at `hdr` (GL_BOOT_HDR_LEN bytes, little-endian). */
void gl_boot_header_parse(const uint8_t *hdr, gl_boot_header_t *out);

/**
 * Check the application image.  `image` points at the first byte of the
 * application region as the processor sees it (GL_BOOT_APP_BASE on the
 * target; a buffer on the host), `region_len` is the size of that region
 * and `load_addr` the address it runs at (GL_BOOT_APP_BASE), against which
 * the reset vector is checked.  `out` (may be NULL) receives the header
 * whenever one was found.
 */
gl_boot_img_t gl_boot_image_check(const uint8_t *image, size_t region_len, uint32_t load_addr,
                                  gl_boot_header_t *out);

/* ---- the decision ------------------------------------------------------------------ */
typedef enum {
    GL_BOOT_START_APP = 0, /**< start the watchdog, jump to the application */
    GL_BOOT_LOADER,        /**< jump to ST's USB loader in system memory */
    GL_BOOT_WAIT_VBUS      /**< Shutdown until VBUS appears (which is a reset: the stub again) */
} gl_boot_action_t;

typedef enum {
    GL_BOOT_WHY_NORMAL = 0,
    GL_BOOT_WHY_UPDATE_REQUESTED,
    GL_BOOT_WHY_IMAGE_INVALID,
    GL_BOOT_WHY_FAILED_STARTS,
    GL_BOOT_WHY_PENDING       /**< an earlier decision for the loader, carried out now (or still waiting) */
} gl_boot_why_t;

typedef struct {
    bool image_valid;
    bool update_requested;   /**< BKP_REQUEST == GL_BOOT_UPDATE_MAGIC */
    bool abnormal_reset;     /**< this reset was a watchdog or a software reset */
    bool vbus;               /**< VBUS_SENSE is high */
    uint32_t attempts_reg;   /**< BKP_ATTEMPTS as found */
} gl_boot_inputs_t;

typedef struct {
    uint8_t action;          /**< gl_boot_action_t */
    uint8_t why;             /**< gl_boot_why_t */
    bool clear_request;      /**< write 0 to BKP_REQUEST */
    uint32_t attempts_reg;   /**< write this to BKP_ATTEMPTS before acting */
} gl_boot_decision_t;

/** The rule in the file comment.  Pure. */
void gl_boot_decide(const gl_boot_inputs_t *in, gl_boot_decision_t *out);

#endif /* GL_BOOT_H */
