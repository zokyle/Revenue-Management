/* mx25r.c - MX25R6435F SPI NOR flash driver.  See mx25r.h. */
#include "mx25r.h"

#include <string.h>

#include "gl_hal.h"
#include "gl_provisional.h"

static gl_status_t select_(void)
{
    const gl_spi_cfg_t spi = { GL_PROV_MX25R_SPI_HZ, 0u, false };
    gl_status_t st = gl_hal_spi_configure(GL_SPI_BUS_1, &spi);
    if (st == GL_OK) {
        gl_hal_gpio_write(GL_PIN_FLASH_CS, false);
    }
    return st;
}

static void deselect_(void)
{
    gl_hal_gpio_write(GL_PIN_FLASH_CS, true);
}

/* One-byte command with no data. */
static gl_status_t command_(uint8_t op)
{
    gl_status_t st = select_();
    if (st != GL_OK) {
        return st;
    }
    st = gl_hal_spi_transfer(GL_SPI_BUS_1, &op, NULL, 1);
    deselect_();
    return st;
}

static gl_status_t read_status_(uint8_t *sr)
{
    const uint8_t tx[2] = { GL_MX25R_CMD_RDSR, 0xFF };
    uint8_t rx[2] = { 0, 0 };
    gl_status_t st = select_();
    if (st != GL_OK) {
        return st;
    }
    st = gl_hal_spi_transfer(GL_SPI_BUS_1, tx, rx, sizeof(tx));
    deselect_();
    *sr = rx[1];
    return st;
}

/* Wait for WIP to clear.  poll_us is the interval between status reads. */
static gl_status_t wait_ready_(uint32_t timeout_ms, uint32_t poll_us)
{
    const uint32_t t0 = gl_hal_tick_ms();
    for (;;) {
        uint8_t sr = 0xFF;
        gl_status_t st = read_status_(&sr);
        if (st != GL_OK) {
            return st;
        }
        if ((sr & GL_MX25R_SR_WIP) == 0u) {
            return GL_OK;
        }
        if ((uint32_t)(gl_hal_tick_ms() - t0) > timeout_ms) {
            return GL_ERR_TIMEOUT;
        }
        gl_hal_delay_us(poll_us);
    }
}

static void put_addr_(uint8_t *hdr, uint8_t op, uint32_t addr)
{
    hdr[0] = op;
    hdr[1] = (uint8_t)(addr >> 16);
    hdr[2] = (uint8_t)(addr >> 8);
    hdr[3] = (uint8_t)addr;
}

gl_status_t gl_mx25r_wake(gl_mx25r_t *f)
{
    gl_status_t st = command_(GL_MX25R_CMD_RDP);
    gl_hal_delay_us(GL_PROV_MX25R_DP_DELAY_US);
    if (st == GL_OK) {
        f->asleep = false;
    }
    return st;
}

gl_status_t gl_mx25r_sleep(gl_mx25r_t *f)
{
    if (f->asleep) {
        return GL_OK;
    }
    gl_status_t st = command_(GL_MX25R_CMD_DP);
    gl_hal_delay_us(GL_PROV_MX25R_DP_DELAY_US);
    if (st == GL_OK) {
        f->asleep = true;
    }
    return st;
}

static gl_status_t ensure_awake_(gl_mx25r_t *f)
{
    return f->asleep ? gl_mx25r_wake(f) : GL_OK;
}

gl_status_t gl_mx25r_init(gl_mx25r_t *f)
{
    const uint8_t tx[4] = { GL_MX25R_CMD_RDID, 0xFF, 0xFF, 0xFF };
    uint8_t rx[4] = { 0, 0, 0, 0 };

    memset(f, 0, sizeof(*f));
    gl_hal_gpio_write(GL_PIN_FLASH_CS, true);
    gl_hal_gpio_mode(GL_PIN_FLASH_CS, GL_PIN_MODE_OUTPUT_PP);
    /* the device may have been left in deep power-down by a previous run */
    gl_status_t st = gl_mx25r_wake(f);
    if (st != GL_OK) {
        return st;
    }
    st = select_();
    if (st != GL_OK) {
        return st;
    }
    st = gl_hal_spi_transfer(GL_SPI_BUS_1, tx, rx, sizeof(tx));
    deselect_();
    if (st != GL_OK) {
        return st;
    }
    memcpy(f->id, &rx[1], 3);
    if (rx[1] != GL_MX25R_ID_MFR || rx[2] != GL_MX25R_ID_TYPE || rx[3] != GL_MX25R_ID_DENS) {
        return GL_ERR_NOT_FOUND;
    }
    f->present = true;
    /* a write interrupted by the last reset may still be running */
    return wait_ready_(GL_PROV_MX25R_ERASE_TIMEOUT_MS, 1000u);
}

gl_status_t gl_mx25r_read(gl_mx25r_t *f, uint32_t addr, uint8_t *buf, size_t len)
{
    uint8_t hdr[4];
    if (!f->present) {
        return GL_ERR_NOT_FOUND;
    }
    if (addr >= GL_MX25R_SIZE_BYTES || len > GL_MX25R_SIZE_BYTES - addr) {
        return GL_ERR_PARAM;
    }
    if (len == 0u) {
        return GL_OK;
    }
    gl_status_t st = ensure_awake_(f);
    if (st != GL_OK) {
        return st;
    }
    put_addr_(hdr, GL_MX25R_CMD_READ, addr);
    st = select_();
    if (st != GL_OK) {
        return st;
    }
    st = gl_hal_spi_transfer(GL_SPI_BUS_1, hdr, NULL, sizeof(hdr));
    if (st == GL_OK) {
        st = gl_hal_spi_transfer(GL_SPI_BUS_1, NULL, buf, len);
    }
    deselect_();
    return st;
}

gl_status_t gl_mx25r_prog(gl_mx25r_t *f, uint32_t addr, const uint8_t *buf, size_t len)
{
    uint8_t hdr[4];
    if (!f->present) {
        return GL_ERR_NOT_FOUND;
    }
    if (addr >= GL_MX25R_SIZE_BYTES || len > GL_MX25R_SIZE_BYTES - addr) {
        return GL_ERR_PARAM;
    }
    gl_status_t st = ensure_awake_(f);
    while (st == GL_OK && len > 0u) {
        size_t n = GL_MX25R_PAGE_BYTES - (addr % GL_MX25R_PAGE_BYTES);
        if (n > len) {
            n = len;
        }
        st = command_(GL_MX25R_CMD_WREN);
        if (st != GL_OK) {
            break;
        }
        put_addr_(hdr, GL_MX25R_CMD_PP, addr);
        st = select_();
        if (st != GL_OK) {
            break;
        }
        st = gl_hal_spi_transfer(GL_SPI_BUS_1, hdr, NULL, sizeof(hdr));
        if (st == GL_OK) {
            st = gl_hal_spi_transfer(GL_SPI_BUS_1, buf, NULL, n);
        }
        deselect_();
        if (st != GL_OK) {
            break;
        }
        st = wait_ready_(GL_PROV_MX25R_PROG_TIMEOUT_MS, 100u);
        f->page_programs++;
        addr += (uint32_t)n;
        buf += n;
        len -= n;
    }
    return st;
}

gl_status_t gl_mx25r_erase_sector(gl_mx25r_t *f, uint32_t addr)
{
    uint8_t hdr[4];
    if (!f->present) {
        return GL_ERR_NOT_FOUND;
    }
    if (addr >= GL_MX25R_SIZE_BYTES) {
        return GL_ERR_PARAM;
    }
    gl_status_t st = ensure_awake_(f);
    if (st != GL_OK) {
        return st;
    }
    st = command_(GL_MX25R_CMD_WREN);
    if (st != GL_OK) {
        return st;
    }
    put_addr_(hdr, GL_MX25R_CMD_SE, addr & ~(GL_MX25R_SECTOR_BYTES - 1u));
    st = select_();
    if (st != GL_OK) {
        return st;
    }
    st = gl_hal_spi_transfer(GL_SPI_BUS_1, hdr, NULL, sizeof(hdr));
    deselect_();
    if (st != GL_OK) {
        return st;
    }
    f->sector_erases++;
    gl_hal_watchdog_kick();
    return wait_ready_(GL_PROV_MX25R_ERASE_TIMEOUT_MS, 1000u);
}

/* ---- gl_flash_if_t adapter ----------------------------------------------------- */

static gl_status_t if_read_(void *ctx, uint32_t addr, uint8_t *buf, size_t len)
{
    return gl_mx25r_read((gl_mx25r_t *)ctx, addr, buf, len);
}

static gl_status_t if_prog_(void *ctx, uint32_t addr, const uint8_t *buf, size_t len)
{
    return gl_mx25r_prog((gl_mx25r_t *)ctx, addr, buf, len);
}

static gl_status_t if_erase_(void *ctx, uint32_t addr)
{
    return gl_mx25r_erase_sector((gl_mx25r_t *)ctx, addr);
}

void gl_mx25r_flash_if(gl_mx25r_t *f, gl_flash_if_t *out)
{
    out->ctx = f;
    out->sector_size = GL_MX25R_SECTOR_BYTES;
    out->read = if_read_;
    out->prog = if_prog_;
    out->erase_sector = if_erase_;
}
