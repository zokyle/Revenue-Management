/*
 * test_boot.c - the portable part of the boot stub (boot/gl_boot_logic.c,
 * DESIGN_SPEC E34): the image check and the decision rule, exhaustively.
 * The STM32 part (the jump, the option bytes, Shutdown) is written by
 * inspection, links (`make boot-cross`) and has never run.
 */
#include <string.h>

#include "gl_boot.h"
#include "gl_crc.h"
#include "gl_test.h"

static uint8_t img_[64 * 1024];

static void put32_(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16);
    p[3] = (uint8_t)(v >> 24);
}

/* A synthetic application image of `len` bytes, stamped as
 * tools/stamp_image.py stamps one (written here independently). */
static void make_image_(uint32_t len, uint32_t fw_version)
{
    uint8_t *h = &img_[GL_BOOT_HDR_OFFSET];
    uint32_t seed = 12345u + 977u * fw_version, crc; /* (another version: other code) */
    for (uint32_t i = 0; i < sizeof(img_); i++) {
        seed = seed * 1664525u + 1013904223u;
        img_[i] = (i < len) ? (uint8_t)(seed >> 24) : 0xFFu;
    }
    put32_(&img_[0], GL_BOOT_RAM_BASE + 0x10000u);          /* initial stack pointer */
    put32_(&img_[4], (GL_BOOT_APP_BASE + 0x500u) | 1u);     /* reset vector, Thumb */
    memset(h, 0, GL_BOOT_HDR_LEN);
    put32_(&h[0], GL_BOOT_MAGIC);
    h[4] = (uint8_t)GL_BOOT_HDR_VERSION;
    h[6] = (uint8_t)GL_BOOT_HW_REV;
    put32_(&h[8], len);
    put32_(&h[16], fw_version);
    put32_(&h[20], 20261113u);
    crc = gl_boot_crc32(0u, img_, len); /* with both CRC fields still zero */
    put32_(&h[12], crc);
    put32_(&h[28], gl_boot_crc32(0u, h, 28));
}

/* Re-stamp the two CRCs after a header field was changed on purpose. */
static void restamp_(void)
{
    uint8_t *h = &img_[GL_BOOT_HDR_OFFSET];
    const uint32_t len = (uint32_t)h[8] | ((uint32_t)h[9] << 8) | ((uint32_t)h[10] << 16) |
                         ((uint32_t)h[11] << 24);
    put32_(&h[12], 0u);
    put32_(&h[28], 0u);
    if (len <= sizeof(img_)) {
        put32_(&h[12], gl_boot_crc32(0u, img_, len));
    }
    put32_(&h[28], gl_boot_crc32(0u, h, 28));
}

static gl_boot_img_t chk_(void)
{
    return gl_boot_image_check(img_, sizeof(img_), GL_BOOT_APP_BASE, NULL);
}

GL_TEST(test_crc32_is_zlibs)
{
    /* the stub carries its own CRC-32; it is the one of the firmware core,
     * of zlib and of the stamping tool */
    static const uint8_t msg[] = "123456789";
    GL_CHECK_EQ(gl_boot_crc32(0u, msg, 9), 0xCBF43926u);
    GL_CHECK_EQ(gl_boot_crc32(gl_boot_crc32(0u, msg, 4), &msg[4], 5), 0xCBF43926u);
    for (unsigned n = 0; n < 300u; n += 7u) {
        GL_CHECK_EQ(gl_boot_crc32(0u, img_, n), gl_crc32(img_, n));
    }
}

GL_TEST(test_image_check)
{
    gl_boot_header_t h;
    uint8_t *hdr = &img_[GL_BOOT_HDR_OFFSET];

    /* layout facts the linker script, the tool and the stub share */
    GL_CHECK_EQ(GL_BOOT_APP_BASE, 0x08002000u);
    GL_CHECK_EQ(GL_BOOT_STUB_BYTES, 8192u);
    GL_CHECK(GL_BOOT_HDR_OFFSET >= 4u * (16u + 126u)); /* behind the 142 vectors of the U585 */
    GL_CHECK_EQ(GL_BOOT_HDR_LEN, 32u);

    make_image_(40000u, 0x0003u);
    GL_CHECK_EQ(gl_boot_image_check(img_, sizeof(img_), GL_BOOT_APP_BASE, &h), GL_BOOT_IMG_OK);
    GL_CHECK(h.magic == GL_BOOT_MAGIC && h.length == 40000u && h.fw_version == 3u &&
             h.fw_build == 20261113u && h.hw_rev == 5u);
    /* blank flash, and all zeros */
    memset(img_, 0xFF, sizeof(img_));
    GL_CHECK_EQ(chk_(), GL_BOOT_IMG_NO_HEADER);
    memset(img_, 0x00, sizeof(img_));
    GL_CHECK_EQ(chk_(), GL_BOOT_IMG_NO_HEADER);
    GL_CHECK_EQ(gl_boot_image_check(NULL, sizeof(img_), GL_BOOT_APP_BASE, NULL), GL_BOOT_IMG_NO_HEADER);
    GL_CHECK_EQ(gl_boot_image_check(img_, 100, GL_BOOT_APP_BASE, NULL), GL_BOOT_IMG_NO_HEADER);

    /* EVERY SINGLE-BIT ERROR anywhere in the image is refused: a write that
     * was interrupted or a cell that did not take cannot be started */
    make_image_(6000u, 0x0003u);
    {
        unsigned accepted = 0;
        for (uint32_t bit = 0; bit < 8u * 6000u; bit++) {
            img_[bit / 8u] ^= (uint8_t)(1u << (bit % 8u));
            accepted += (chk_() == GL_BOOT_IMG_OK) ? 1u : 0u;
            img_[bit / 8u] ^= (uint8_t)(1u << (bit % 8u));
        }
        printf("    image of 6000 bytes: each of its 48000 bits flipped in turn, %u accepted\n",
               accepted);
        GL_CHECK_EQ(accepted, 0u);
        GL_CHECK_EQ(chk_(), GL_BOOT_IMG_OK);
    }
    /* AN UPDATE INTERRUPTED AT ANY POINT: the first n bytes are the new
     * image, the rest is erased flash (the loader erases, then writes
     * upward).  No prefix but the whole image is accepted */
    {
        static uint8_t full[6000];
        unsigned accepted = 0;
        make_image_(6000u, 0x0004u);
        memcpy(full, img_, sizeof(full));
        for (uint32_t n = 0; n < 6000u; n += 1u) {
            memset(img_, 0xFF, 6000u);
            memcpy(img_, full, n);
            accepted += (chk_() == GL_BOOT_IMG_OK) ? 1u : 0u;
        }
        GL_CHECK_EQ(accepted, 0u);
        /* ... nor a new image whose tail is still the OLD one (written over
         * without an erase of the last pages) */
        make_image_(6000u, 0x0003u);
        memcpy(img_, full, 5000u);
        GL_CHECK(chk_() != GL_BOOT_IMG_OK);
        memcpy(img_, full, 6000u);
        GL_CHECK_EQ(chk_(), GL_BOOT_IMG_OK);
        printf("    update interrupted after each of 6000 byte counts: none of the partial images "
               "is accepted\n");
    }
    /* header fields, each with CORRECT CRCs (an image that was built wrong,
     * not damaged) */
    make_image_(6000u, 3u);
    hdr[4] = 2;
    restamp_();
    GL_CHECK_EQ(chk_(), GL_BOOT_IMG_BAD_VERSION);
    make_image_(6000u, 3u);
    hdr[6] = 4; /* an image for the rev D board */
    restamp_();
    GL_CHECK_EQ(chk_(), GL_BOOT_IMG_BAD_HW);
    {
        static const uint32_t bad_len[] = { 0u, 1024u, 0x41Fu, 6002u, sizeof(img_) + 4u, 0xFFFFFFFCu };
        for (size_t i = 0; i < sizeof(bad_len) / sizeof(bad_len[0]); i++) {
            make_image_(6000u, 3u);
            put32_(&hdr[8], bad_len[i]);
            restamp_();
            GL_CHECK_EQ(chk_(), GL_BOOT_IMG_BAD_LENGTH);
        }
    }
    {
        /* vectors: stack pointer outside the RAM or misaligned; reset vector
         * even, in the stub, in the header, behind the image */
        static const uint32_t bad_sp[] = { 0u, 0x08002000u, GL_BOOT_RAM_BASE, GL_BOOT_RAM_BASE + 0x1004u,
                                           GL_BOOT_RAM_BASE + GL_BOOT_RAM_BYTES + 8u };
        static const uint32_t bad_pc[] = { 0u, GL_BOOT_APP_BASE + 0x500u, 0x08000089u,
                                           (GL_BOOT_APP_BASE + 0x404u) | 1u,
                                           (GL_BOOT_APP_BASE + 6000u) | 1u, 0x0BF90001u };
        for (size_t i = 0; i < sizeof(bad_sp) / sizeof(bad_sp[0]); i++) {
            make_image_(6000u, 3u);
            put32_(&img_[0], bad_sp[i]);
            restamp_();
            GL_CHECK_EQ(chk_(), GL_BOOT_IMG_BAD_VECTORS);
        }
        for (size_t i = 0; i < sizeof(bad_pc) / sizeof(bad_pc[0]); i++) {
            make_image_(6000u, 3u);
            put32_(&img_[4], bad_pc[i]);
            restamp_();
            GL_CHECK_EQ(chk_(), GL_BOOT_IMG_BAD_VECTORS);
        }
        /* the top of the RAM is a valid stack pointer */
        make_image_(6000u, 3u);
        put32_(&img_[0], GL_BOOT_RAM_BASE + GL_BOOT_RAM_BYTES);
        restamp_();
        GL_CHECK_EQ(chk_(), GL_BOOT_IMG_OK);
    }
    /* the smallest and the largest image this buffer can hold */
    make_image_(GL_BOOT_HDR_OFFSET + GL_BOOT_HDR_LEN + 0x100u, 3u);
    GL_CHECK_EQ(chk_(), GL_BOOT_IMG_OK);
    make_image_((uint32_t)sizeof(img_), 3u);
    GL_CHECK_EQ(chk_(), GL_BOOT_IMG_OK);
    /* the region is shorter than the image says */
    GL_CHECK_EQ(gl_boot_image_check(img_, sizeof(img_) - 4u, GL_BOOT_APP_BASE, NULL),
                GL_BOOT_IMG_BAD_LENGTH);
}

static gl_boot_decision_t decide_(bool valid, bool request, bool abnormal, bool vbus, uint32_t reg)
{
    gl_boot_inputs_t in;
    gl_boot_decision_t d;
    in.image_valid = valid;
    in.update_requested = request;
    in.abnormal_reset = abnormal;
    in.vbus = vbus;
    in.attempts_reg = reg;
    memset(&d, 0xEE, sizeof(d));
    gl_boot_decide(&in, &d);
    return d;
}

#define REG(count) (GL_BOOT_ATTEMPTS_MAGIC | (uint32_t)(count))
#define REG_PENDING (GL_BOOT_ATTEMPTS_MAGIC | GL_BOOT_ATTEMPTS_TO_LOADER)

GL_TEST(test_decision_rule)
{
    gl_boot_decision_t d;

    /* 5. the ordinary start: valid image, nothing asked, nothing counted */
    d = decide_(true, false, false, false, 0u);
    GL_CHECK_EQ(d.action, GL_BOOT_START_APP);
    GL_CHECK_EQ(d.why, GL_BOOT_WHY_NORMAL);
    GL_CHECK_EQ(d.attempts_reg, REG(1));
    GL_CHECK(!d.clear_request);
    /* a register that holds something else (first power-up: undefined) is "no count" */
    d = decide_(true, false, true, true, 0xDEADBEEFu);
    GL_CHECK_EQ(d.action, GL_BOOT_START_APP);
    GL_CHECK_EQ(d.attempts_reg, REG(1));

    /* 1. an update was requested: the loader, in the cradle only; one attempt */
    d = decide_(true, true, true, true, 0u);
    GL_CHECK_EQ(d.action, GL_BOOT_LOADER);
    GL_CHECK_EQ(d.why, GL_BOOT_WHY_UPDATE_REQUESTED);
    GL_CHECK(d.clear_request);
    GL_CHECK_EQ(d.attempts_reg, 0u);
    d = decide_(true, true, true, false, 0u); /* lifted out before the reset: no host */
    GL_CHECK_EQ(d.action, GL_BOOT_START_APP);
    GL_CHECK(d.clear_request); /* the request is dropped, not kept for later */
    /* ... also when the image is not valid (an update that failed is asked for again) */
    d = decide_(false, true, false, true, 0u);
    GL_CHECK_EQ(d.action, GL_BOOT_LOADER);

    /* 3. the image is not valid */
    d = decide_(false, false, false, true, 0u);
    GL_CHECK_EQ(d.action, GL_BOOT_LOADER);
    GL_CHECK_EQ(d.why, GL_BOOT_WHY_IMAGE_INVALID);
    GL_CHECK_EQ(d.attempts_reg, 0u);
    d = decide_(false, false, false, false, 0u);
    GL_CHECK_EQ(d.action, GL_BOOT_WAIT_VBUS); /* no host: do not empty the cell in the loader */
    GL_CHECK_EQ(d.attempts_reg, REG_PENDING);
    /* 2. ... and when VBUS comes (a reset through the wake-up pin): the loader */
    d = decide_(false, false, false, true, REG_PENDING);
    GL_CHECK_EQ(d.action, GL_BOOT_LOADER);
    GL_CHECK_EQ(d.why, GL_BOOT_WHY_PENDING);
    GL_CHECK_EQ(d.attempts_reg, 0u);
    d = decide_(false, false, false, false, REG_PENDING); /* a glitch on NRST meanwhile */
    GL_CHECK_EQ(d.action, GL_BOOT_WAIT_VBUS);
    GL_CHECK_EQ(d.attempts_reg, REG_PENDING);

    /* 4. THE WATCHDOG LOOP.  An image that is valid by its CRC but does not
     * run: start, watchdog reset, start, watchdog reset, start, watchdog
     * reset - and then no fourth start */
    {
        uint32_t reg = 0u;
        unsigned starts = 0;
        for (int boot = 0; boot < 10; boot++) {
            d = decide_(true, false, boot > 0, true, reg);
            reg = d.attempts_reg;
            if (d.action != GL_BOOT_START_APP) {
                break;
            }
            starts++;
        }
        printf("    a valid image that never confirms: started %u times, then %s\n", starts,
               (d.action == GL_BOOT_LOADER) ? "the USB loader" : "?");
        GL_CHECK_EQ(starts, GL_BOOT_MAX_FAILED_STARTS);
        GL_CHECK_EQ(d.action, GL_BOOT_LOADER);
        GL_CHECK_EQ(d.why, GL_BOOT_WHY_FAILED_STARTS);
        GL_CHECK_EQ(d.attempts_reg, 0u); /* a fresh count after the loader */
        /* out of the cradle the same loop ends in the wait for VBUS, and
         * VBUS then leads to the loader, not to a fourth start */
        reg = 0u;
        starts = 0;
        for (int boot = 0; boot < 10; boot++) {
            d = decide_(true, false, boot > 0, false, reg);
            reg = d.attempts_reg;
            if (d.action != GL_BOOT_START_APP) {
                break;
            }
            starts++;
        }
        GL_CHECK_EQ(starts, GL_BOOT_MAX_FAILED_STARTS);
        GL_CHECK_EQ(d.action, GL_BOOT_WAIT_VBUS);
        d = decide_(true, false, false, true, reg);
        GL_CHECK_EQ(d.action, GL_BOOT_LOADER);
        GL_CHECK_EQ(d.why, GL_BOOT_WHY_PENDING);
    }
    /* a software reset counts as a watchdog reset does (a fault handler that
     * resets); the application clears the count before a reset it makes on
     * purpose, so those never arrive here with a count */
    d = decide_(true, false, true, true, REG(2));
    GL_CHECK_EQ(d.action, GL_BOOT_START_APP);
    GL_CHECK_EQ(d.attempts_reg, REG(3));
    d = decide_(true, false, true, true, REG(3));
    GL_CHECK_EQ(d.action, GL_BOOT_LOADER);
    /* an image that works: it confirms (the register is 0 again), and no
     * number of later watchdog resets, each after a confirmed run, adds up */
    {
        uint32_t reg = 0u;
        for (int boot = 0; boot < 20; boot++) {
            d = decide_(true, false, true, true, reg);
            GL_CHECK_EQ(d.action, GL_BOOT_START_APP);
            GL_CHECK_EQ(d.attempts_reg, REG(1));
            reg = 0u; /* gl_hal_boot_confirm() */
        }
    }
    /* an unconfirmed start that ended in a power-on, pin or wake-up reset
     * says nothing about the image: the count starts again */
    d = decide_(true, false, false, true, REG(2));
    GL_CHECK_EQ(d.action, GL_BOOT_START_APP);
    GL_CHECK_EQ(d.attempts_reg, REG(1));
    d = decide_(true, false, false, true, REG(3));
    GL_CHECK_EQ(d.action, GL_BOOT_START_APP);

    /* EVERY combination: the loader is entered only with VBUS; an invalid
     * image is never started; a start always leaves a count behind; the
     * request is always cleared */
    {
        static const uint32_t regs[] = { 0u, 0xFFFFFFFFu, REG(0), REG(1), REG(2), REG(3), REG(4),
                                         REG(127), REG_PENDING, REG_PENDING | 2u };
        unsigned cases = 0;
        for (unsigned m = 0; m < 16u; m++) {
            for (size_t r = 0; r < sizeof(regs) / sizeof(regs[0]); r++) {
                const bool valid = (m & 1u) != 0u, request = (m & 2u) != 0u,
                           abnormal = (m & 4u) != 0u, vbus = (m & 8u) != 0u;
                d = decide_(valid, request, abnormal, vbus, regs[r]);
                cases++;
                GL_CHECK(d.action <= GL_BOOT_WAIT_VBUS);
                GL_CHECK_EQ(d.clear_request, request);
                if (d.action == GL_BOOT_LOADER) {
                    GL_CHECK(vbus);
                    GL_CHECK_EQ(d.attempts_reg, 0u);
                }
                if (d.action == GL_BOOT_WAIT_VBUS) {
                    GL_CHECK(!vbus);
                    GL_CHECK_EQ(d.attempts_reg, REG_PENDING);
                }
                if (d.action == GL_BOOT_START_APP) {
                    GL_CHECK(valid);
                    GL_CHECK((d.attempts_reg & 0xFFFFFF00u) == GL_BOOT_ATTEMPTS_MAGIC);
                    GL_CHECK((d.attempts_reg & GL_BOOT_ATTEMPTS_COUNT_MASK) >= 1u &&
                             (d.attempts_reg & GL_BOOT_ATTEMPTS_COUNT_MASK) <= GL_BOOT_MAX_FAILED_STARTS);
                }
                if (!valid) {
                    GL_CHECK(d.action != GL_BOOT_START_APP);
                }
                if (request && vbus) {
                    GL_CHECK_EQ(d.action, GL_BOOT_LOADER);
                }
            }
        }
        printf("    %u combinations of the stub's inputs: the loader only with VBUS, an invalid "
               "image never started, a request always cleared\n", cases);
    }
}

int main(void)
{
    GL_RUN(test_crc32_is_zlibs);
    GL_RUN(test_image_check);
    GL_RUN(test_decision_rule);
    return gl_test_summary();
}
