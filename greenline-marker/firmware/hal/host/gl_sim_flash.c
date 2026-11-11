/*
 * gl_sim_flash.c - model of the Macronix MX25R6435F 64 Mbit SPI NOR flash
 * for the host simulator.
 *
 * Commands modelled (standard SPI-NOR set; opcodes and the JEDEC id are
 * FROM MEMORY, see the README table): RDID 9Fh, RDSR 05h, WREN 06h,
 * WRDI 04h, READ 03h, PP 02h (256-byte pages), SE 20h (4 kB sector),
 * DP B9h, RDP ABh.
 *
 * Behaviour: programming ANDs into the array; PP / SE need a preceding
 * WREN and take time (WIP set in the status register: 1 ms + 8 us per byte
 * for a page program, 40 ms for a sector erase); in deep power-down only
 * ABh is accepted and the device needs 35 us afterwards.  Anything else is
 * counted as a protocol violation and ignored.
 */
#include <string.h>

#include "gl_sim_internal.h"

#define FL_T_PP_BASE_US 1000u
#define FL_T_PP_BYTE_US 8u
#define FL_T_SE_US 40000u
#define FL_T_RES_US 35u
#define FL_MAX_HZ 33000000u

enum { FL_CMD_NONE = 0, FL_CMD_ADDR, FL_CMD_READ, FL_CMD_PP, FL_CMD_SE, FL_CMD_RDID, FL_CMD_RDSR,
       FL_CMD_IGNORE };

static uint8_t mem_[GL_SIM_FLASH_BYTES];
static gl_sim_flash_stats_t stats_;
static struct {
    bool selected;
    uint8_t opcode;
    uint8_t phase;
    uint8_t addr_bytes;
    uint32_t addr;
    uint32_t out_index;
    uint8_t page[256];
    uint32_t page_len;       /* bytes received for a page program */
    bool wel;
    uint64_t busy_until;
    uint64_t ready_at;       /* after release from deep power-down */
    bool pending_wren, pending_wrdi, pending_dp, pending_rdp;
} F;

void sim_flash_reset(bool erase)
{
    if (erase) {
        memset(mem_, 0xFF, sizeof(mem_));
    }
    memset(&stats_, 0, sizeof(stats_));
    memset(&F, 0, sizeof(F));
}

const gl_sim_flash_stats_t *gl_sim_flash_stats(void)
{
    return &stats_;
}

uint8_t *gl_sim_flash_mem(void)
{
    return mem_;
}

static bool busy_(void)
{
    return sim_now() < F.busy_until;
}

static void start_command_(uint8_t op)
{
    F.opcode = op;
    F.addr = 0;
    F.addr_bytes = 0;
    F.out_index = 0;
    F.page_len = 0;
    if (stats_.deep_power_down && op != 0xABu) {
        sim_violation(&sim_viol()->flash, "flash command 0x%02X in deep power-down", op);
        F.phase = FL_CMD_IGNORE;
        return;
    }
    if (sim_now() < F.ready_at) {
        sim_violation(&sim_viol()->flash, "flash command 0x%02X before tRES elapsed", op);
        F.phase = FL_CMD_IGNORE;
        return;
    }
    if (busy_() && op != 0x05u) {
        sim_violation(&sim_viol()->flash, "flash command 0x%02X while a write is in progress", op);
        F.phase = FL_CMD_IGNORE;
        return;
    }
    switch (op) {
    case 0x9F:
        F.phase = FL_CMD_RDID;
        break;
    case 0x05:
        F.phase = FL_CMD_RDSR;
        break;
    case 0x06:
        F.pending_wren = true;
        F.phase = FL_CMD_IGNORE;
        break;
    case 0x04:
        F.pending_wrdi = true;
        F.phase = FL_CMD_IGNORE;
        break;
    case 0x03:
    case 0x02:
    case 0x20:
        F.phase = FL_CMD_ADDR;
        break;
    case 0xB9:
        F.pending_dp = true;
        F.phase = FL_CMD_IGNORE;
        break;
    case 0xAB:
        F.pending_rdp = true;
        F.phase = FL_CMD_IGNORE;
        break;
    default:
        sim_violation(&sim_viol()->flash, "unknown flash command 0x%02X", op);
        F.phase = FL_CMD_IGNORE;
        break;
    }
}

void sim_flash_cs(bool asserted)
{
    if (asserted) {
        F.selected = true;
        F.phase = FL_CMD_NONE;
        F.pending_wren = F.pending_wrdi = F.pending_dp = F.pending_rdp = false;
        return;
    }
    if (!F.selected) {
        return;
    }
    F.selected = false;
    /* commands take effect on the rising edge of CS# */
    if (F.pending_wren) {
        F.wel = true;
    }
    if (F.pending_wrdi) {
        F.wel = false;
    }
    if (F.pending_dp) {
        stats_.deep_power_down = true;
    }
    if (F.pending_rdp) {
        if (stats_.deep_power_down) {
            F.ready_at = sim_now() + FL_T_RES_US;
        }
        stats_.deep_power_down = false;
    }
    if (F.opcode == 0x02u && F.phase == FL_CMD_PP) {
        if (!F.wel) {
            sim_violation(&sim_viol()->flash, "page program at 0x%06X without WREN",
                          (unsigned)F.addr);
        } else if (F.page_len == 0u) {
            sim_violation(&sim_viol()->flash, "page program with no data");
        } else {
            const uint32_t page_base = F.addr & ~0xFFu;
            uint32_t off = F.addr & 0xFFu;
            for (uint32_t i = 0; i < F.page_len; i++) {
                uint8_t *cell = &mem_[(page_base + off) % GL_SIM_FLASH_BYTES];
                if (*cell != 0xFFu) {
                    stats_.overwrite_bytes++;
                }
                *cell &= F.page[i];
                off = (off + 1u) & 0xFFu;
            }
            stats_.page_programs++;
            stats_.bytes_programmed += F.page_len;
            F.busy_until = sim_now() + FL_T_PP_BASE_US + (uint64_t)F.page_len * FL_T_PP_BYTE_US;
            F.wel = false;
        }
    } else if (F.opcode == 0x20u && F.phase == FL_CMD_SE) {
        if (!F.wel) {
            sim_violation(&sim_viol()->flash, "sector erase at 0x%06X without WREN",
                          (unsigned)F.addr);
        } else {
            memset(&mem_[(F.addr % GL_SIM_FLASH_BYTES) & ~0xFFFu], 0xFF, 4096);
            stats_.sector_erases++;
            F.busy_until = sim_now() + FL_T_SE_US;
            F.wel = false;
        }
    } else if ((F.opcode == 0x02u || F.opcode == 0x20u) && F.phase == FL_CMD_ADDR) {
        sim_violation(&sim_viol()->flash, "flash command 0x%02X ended inside its address",
                      F.opcode);
    }
}

void sim_flash_xfer(const gl_spi_cfg_t *cfg, const uint8_t *tx, uint8_t *rx, size_t len)
{
    if (cfg->lsb_first || (cfg->mode != 0u && cfg->mode != 3u)) {
        sim_violation(&sim_viol()->flash, "flash addressed with SPI mode %u, lsb_first %d",
                      cfg->mode, (int)cfg->lsb_first);
        return;
    }
    if (cfg->max_hz > FL_MAX_HZ) {
        sim_violation(&sim_viol()->flash, "flash clocked at %u Hz", (unsigned)cfg->max_hz);
    }
    for (size_t i = 0; i < len; i++) {
        uint8_t out = 0xFF;
        const uint8_t in = tx[i];
        switch (F.phase) {
        case FL_CMD_NONE:
            start_command_(in);
            break;
        case FL_CMD_ADDR:
            F.addr = (F.addr << 8) | in;
            if (++F.addr_bytes == 3u) {
                F.addr %= GL_SIM_FLASH_BYTES;
                if (F.opcode == 0x03u) {
                    F.phase = FL_CMD_READ;
                    stats_.reads++;
                } else if (F.opcode == 0x02u) {
                    F.phase = FL_CMD_PP;
                } else {
                    F.phase = FL_CMD_SE;
                }
            }
            break;
        case FL_CMD_READ:
            out = mem_[F.addr];
            F.addr = (F.addr + 1u) % GL_SIM_FLASH_BYTES;
            break;
        case FL_CMD_PP:
            if (F.page_len < 256u) {
                F.page[F.page_len++] = in;
            } else if (F.page_len == 256u) {
                sim_violation(&sim_viol()->flash, "page program of more than 256 bytes");
                F.page_len++;
            }
            break;
        case FL_CMD_SE:
            sim_violation(&sim_viol()->flash, "data after a sector-erase address");
            F.phase = FL_CMD_IGNORE;
            break;
        case FL_CMD_RDID: {
            static const uint8_t id[3] = { 0xC2, 0x28, 0x17 };
            out = id[F.out_index % 3u];
            F.out_index++;
            break;
        }
        case FL_CMD_RDSR:
            out = (uint8_t)((busy_() ? 0x01u : 0x00u) | (F.wel ? 0x02u : 0x00u));
            break;
        default:
            break;
        }
        if (rx != NULL) {
            rx[i] = out;
        }
    }
    if (F.phase == FL_CMD_PP && F.page_len > 256u) {
        F.page_len = 256u; /* keep the frame programmable but flagged */
    }
}
