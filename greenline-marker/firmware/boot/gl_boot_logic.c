/* gl_boot_logic.c - the portable part of the boot stub: the image check and
 * the decision.  See gl_boot.h.  No library call, no static data but the
 * 16-entry CRC table: this file is all the "thinking" of the stub. */
#include "gl_boot.h"

static const uint32_t crc_nibble_[16] = {
    0x00000000u, 0x1DB71064u, 0x3B6E20C8u, 0x26D930ACu, 0x76DC4190u, 0x6B6B51F4u,
    0x4DB26158u, 0x5005713Cu, 0xEDB88320u, 0xF00F9344u, 0xD6D6A3E8u, 0xCB61B38Cu,
    0x9B64C2B0u, 0x86D3D2D4u, 0xA00AE278u, 0xBDBDF21Cu,
};

uint32_t gl_boot_crc32(uint32_t crc, const uint8_t *data, size_t len)
{
    crc = ~crc;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        crc = (crc >> 4) ^ crc_nibble_[crc & 0x0Fu];
        crc = (crc >> 4) ^ crc_nibble_[crc & 0x0Fu];
    }
    return ~crc;
}

static uint32_t u32_(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

void gl_boot_header_parse(const uint8_t *hdr, gl_boot_header_t *out)
{
    out->magic = u32_(&hdr[0]);
    out->hdr_version = (uint16_t)(hdr[4] | ((uint16_t)hdr[5] << 8));
    out->hw_rev = (uint16_t)(hdr[6] | ((uint16_t)hdr[7] << 8));
    out->length = u32_(&hdr[8]);
    out->crc32 = u32_(&hdr[12]);
    out->fw_version = u32_(&hdr[16]);
    out->fw_build = u32_(&hdr[20]);
    out->reserved = u32_(&hdr[24]);
    out->hdr_crc = u32_(&hdr[28]);
}

gl_boot_img_t gl_boot_image_check(const uint8_t *image, size_t region_len, uint32_t load_addr,
                                  gl_boot_header_t *out)
{
    static const uint8_t zero4[4] = { 0, 0, 0, 0 };
    gl_boot_header_t h;
    const uint8_t *hdr;
    uint32_t sp, pc, crc;

    if (image == NULL || region_len < GL_BOOT_HDR_OFFSET + GL_BOOT_HDR_LEN) {
        return GL_BOOT_IMG_NO_HEADER;
    }
    hdr = &image[GL_BOOT_HDR_OFFSET];
    gl_boot_header_parse(hdr, &h);
    if (h.magic != GL_BOOT_MAGIC || gl_boot_crc32(0u, hdr, GL_BOOT_HDR_LEN - 4u) != h.hdr_crc) {
        return GL_BOOT_IMG_NO_HEADER;
    }
    if (out != NULL) {
        *out = h;
    }
    if (h.hdr_version != GL_BOOT_HDR_VERSION) {
        return GL_BOOT_IMG_BAD_VERSION;
    }
    if (h.hw_rev != GL_BOOT_HW_REV) {
        return GL_BOOT_IMG_BAD_HW;
    }
    if (h.length < GL_BOOT_HDR_OFFSET + GL_BOOT_HDR_LEN || h.length > region_len ||
        (h.length & 3u) != 0u) {
        return GL_BOOT_IMG_BAD_LENGTH;
    }
    sp = u32_(&image[0]);
    pc = u32_(&image[4]);
    if (sp < GL_BOOT_RAM_BASE + 0x100u || sp > GL_BOOT_RAM_BASE + GL_BOOT_RAM_BYTES ||
        (sp & 7u) != 0u || (pc & 1u) == 0u || pc < load_addr + GL_BOOT_HDR_OFFSET + GL_BOOT_HDR_LEN ||
        pc >= load_addr + h.length) {
        return GL_BOOT_IMG_BAD_VECTORS;
    }
    /* the whole image, the two CRC fields of the header taken as zero */
    crc = gl_boot_crc32(0u, image, GL_BOOT_HDR_OFFSET + 12u);
    crc = gl_boot_crc32(crc, zero4, 4u);
    crc = gl_boot_crc32(crc, &image[GL_BOOT_HDR_OFFSET + 16u], 12u);
    crc = gl_boot_crc32(crc, zero4, 4u);
    crc = gl_boot_crc32(crc, &image[GL_BOOT_HDR_OFFSET + GL_BOOT_HDR_LEN],
                        (size_t)h.length - (GL_BOOT_HDR_OFFSET + GL_BOOT_HDR_LEN));
    return (crc == h.crc32) ? GL_BOOT_IMG_OK : GL_BOOT_IMG_BAD_CRC;
}

void gl_boot_decide(const gl_boot_inputs_t *in, gl_boot_decision_t *out)
{
    const bool counted = (in->attempts_reg & 0xFFFFFF00u) == GL_BOOT_ATTEMPTS_MAGIC;
    uint32_t count = counted ? (in->attempts_reg & GL_BOOT_ATTEMPTS_COUNT_MASK) : 0u;
    const bool pending = counted && (in->attempts_reg & GL_BOOT_ATTEMPTS_TO_LOADER) != 0u;
    uint8_t why = (uint8_t)GL_BOOT_WHY_NORMAL;

    out->clear_request = in->update_requested; /* one attempt, whatever comes of it */
    out->attempts_reg = 0u;
    out->action = (uint8_t)GL_BOOT_START_APP;
    out->why = (uint8_t)GL_BOOT_WHY_NORMAL;

    if (in->update_requested && in->vbus) {
        why = (uint8_t)GL_BOOT_WHY_UPDATE_REQUESTED;
    } else if (pending) {
        why = (uint8_t)GL_BOOT_WHY_PENDING;
    } else if (!in->image_valid) {
        why = (uint8_t)GL_BOOT_WHY_IMAGE_INVALID;
    } else if (in->ship_mode && !in->vbus) {
        /* rule 6: back to Shutdown through the application, nothing counted,
         * no watchdog, the register left exactly as it was found */
        out->action = (uint8_t)GL_BOOT_START_APP_QUIET;
        out->why = (uint8_t)GL_BOOT_WHY_SHIP_MODE;
        out->attempts_reg = in->attempts_reg;
        return;
    } else {
        if (count != 0u && !in->abnormal_reset) {
            count = 0u; /* the unconfirmed start ended for a reason that says nothing about the image */
        }
        if (count >= GL_BOOT_MAX_FAILED_STARTS) {
            why = (uint8_t)GL_BOOT_WHY_FAILED_STARTS;
        }
    }
    out->why = why;
    if (why == (uint8_t)GL_BOOT_WHY_NORMAL) {
        out->action = (uint8_t)GL_BOOT_START_APP;
        out->attempts_reg = GL_BOOT_ATTEMPTS_MAGIC | (count + 1u);
        return;
    }
    if (in->vbus) {
        out->action = (uint8_t)GL_BOOT_LOADER;
        out->attempts_reg = 0u; /* a fresh count for whatever image comes out of the loader */
    } else {
        out->action = (uint8_t)GL_BOOT_WAIT_VBUS;
        out->attempts_reg = GL_BOOT_ATTEMPTS_MAGIC | GL_BOOT_ATTEMPTS_TO_LOADER;
    }
}

/* ---- faults inside the stub ---------------------------------------------------------- */

static uint32_t faults_count_(uint32_t reg)
{
    return ((reg & 0xFFFFFF00u) == GL_BOOT_FAULTS_MAGIC) ? (reg & GL_BOOT_FAULTS_COUNT_MASK) : 0u;
}

static bool faults_ecc_(uint32_t reg)
{
    return (reg & 0xFFFFFF00u) == GL_BOOT_FAULTS_MAGIC && (reg & GL_BOOT_FAULTS_ECC) != 0u;
}

bool gl_boot_may_read_image(uint32_t faults_reg)
{
    return !faults_ecc_(faults_reg) && faults_count_(faults_reg) < GL_BOOT_MAX_STUB_FAULTS;
}

uint32_t gl_boot_fault_note(uint32_t faults_reg, bool ecc)
{
    uint32_t n = faults_count_(faults_reg);
    const bool e = ecc || faults_ecc_(faults_reg);
    if (n < GL_BOOT_FAULTS_COUNT_MASK) {
        n++;
    }
    return GL_BOOT_FAULTS_MAGIC | n | (e ? GL_BOOT_FAULTS_ECC : 0u);
}

uint32_t gl_boot_faults_after(uint32_t faults_reg, bool image_was_read, uint8_t action)
{
    if (image_was_read && !faults_ecc_(faults_reg)) {
        return 0u; /* read to its end, no fault: the passes before say nothing any more */
    }
    if (action == (uint8_t)GL_BOOT_LOADER) {
        return 0u;
    }
    return faults_reg;
}
