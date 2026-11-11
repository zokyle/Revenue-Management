/*
 * test_drv_flash.c - MX25R6435F driver against the simulator: exact command
 * bytes, page splitting, erase, deep power-down, and the core's log / blob
 * store running on the real driver.
 */
#include "gl_test.h"

#include "gl_settings.h"
#include "gl_trace_util.h"
#include "mx25r.h"

static gl_mx25r_t fl_;

static void fresh_(void)
{
    gl_sim_reset(true);
    (void)gl_hal_init();
}

/* The transmitted bytes of the n-th chip-select frame (CS low .. CS high)
 * at or after trace index `from`; returns the count, and the index after
 * the frame in *next. */
static size_t cs_frame_(size_t from, uint8_t *out, size_t cap, size_t *next)
{
    const long lo = tr_find_write(from, GL_PIN_FLASH_CS, false);
    if (lo < 0) {
        *next = gl_sim_trace_count();
        return 0;
    }
    long hi = tr_find_write((size_t)lo, GL_PIN_FLASH_CS, true);
    if (hi < 0) {
        hi = (long)gl_sim_trace_count();
    }
    *next = (size_t)hi + 1u;
    return tr_spi_bytes((size_t)lo, (size_t)hi, GL_SIM_DEV_FLASH, out, cap);
}

GL_TEST(test_init_reads_jedec_id)
{
    uint8_t f[16];
    size_t next = 0, n;
    fresh_();
    gl_sim_trace_clear();
    GL_CHECK_EQ(gl_mx25r_init(&fl_), GL_OK);
    GL_CHECK(fl_.present);
    GL_CHECK_EQ(fl_.id[0], 0xC2);
    GL_CHECK_EQ(fl_.id[1], 0x28);
    GL_CHECK_EQ(fl_.id[2], 0x17);

    /* frame 1: release from deep power-down; frame 2: RDID + 3 dummy bytes;
     * frame 3: status */
    n = cs_frame_(next, f, sizeof(f), &next);
    GL_CHECK_EQ(n, 1);
    GL_CHECK_EQ(f[0], 0xAB);
    n = cs_frame_(next, f, sizeof(f), &next);
    GL_CHECK_EQ(n, 4);
    GL_CHECK_EQ(f[0], 0x9F);
    n = cs_frame_(next, f, sizeof(f), &next);
    GL_CHECK_EQ(n, 2);
    GL_CHECK_EQ(f[0], 0x05);

    /* SPI settings: mode 0, MSB first */
    const long i_cfg = tr_find(0, GL_SIM_TR_SPI_CFG, GL_SPI_BUS_1);
    GL_CHECK(i_cfg >= 0);
    GL_CHECK_EQ(gl_sim_trace_at((size_t)i_cfg)->b, 0x000u);
    GL_CHECK(gl_sim_trace_at((size_t)i_cfg)->c <= 33000000u);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

GL_TEST(test_program_exact_bytes_and_page_split)
{
    uint8_t data[48], back[48], f[300];
    size_t next = 0, n;
    fresh_();
    GL_CHECK_EQ(gl_mx25r_init(&fl_), GL_OK);
    for (unsigned i = 0; i < sizeof(data); i++) {
        data[i] = (uint8_t)(i * 5u + 3u);
    }
    /* 48 bytes at 0x0010F0 cross the page boundary at 0x001100: 16 + 32 */
    gl_sim_trace_clear();
    GL_CHECK_EQ(gl_mx25r_prog(&fl_, 0x0010F0u, data, sizeof(data)), GL_OK);

    n = cs_frame_(next, f, sizeof(f), &next); /* WREN */
    GL_CHECK_EQ(n, 1);
    GL_CHECK_EQ(f[0], 0x06);
    n = cs_frame_(next, f, sizeof(f), &next); /* PP, 3 address bytes, 16 data bytes */
    GL_CHECK_EQ(n, 4 + 16);
    GL_CHECK_EQ(f[0], 0x02);
    GL_CHECK_EQ(f[1], 0x00);
    GL_CHECK_EQ(f[2], 0x10);
    GL_CHECK_EQ(f[3], 0xF0);
    GL_CHECK_MEM(&f[4], data, 16);
    /* status polls until the write completes */
    unsigned polls = 0;
    for (;;) {
        n = cs_frame_(next, f, sizeof(f), &next);
        if (n != 2 || f[0] != 0x05) {
            break;
        }
        polls++;
    }
    GL_CHECK(polls >= 2u); /* it really waited for the write-in-progress bit */
    GL_CHECK_EQ(n, 1);
    GL_CHECK_EQ(f[0], 0x06); /* WREN for the second page */
    n = cs_frame_(next, f, sizeof(f), &next);
    GL_CHECK_EQ(n, 4 + 32);
    GL_CHECK_EQ(f[0], 0x02);
    GL_CHECK_EQ(f[1], 0x00);
    GL_CHECK_EQ(f[2], 0x11);
    GL_CHECK_EQ(f[3], 0x00);
    GL_CHECK_MEM(&f[4], &data[16], 32);

    GL_CHECK_MEM(&gl_sim_flash_mem()[0x10F0], data, sizeof(data));
    GL_CHECK_EQ(gl_sim_flash_stats()->page_programs, 2u);
    GL_CHECK_EQ(gl_sim_flash_stats()->overwrite_bytes, 0u);

    /* read back: 03h + address, then the data */
    gl_sim_trace_clear();
    GL_CHECK_EQ(gl_mx25r_read(&fl_, 0x0010F0u, back, sizeof(back)), GL_OK);
    GL_CHECK_MEM(back, data, sizeof(data));
    next = 0;
    n = cs_frame_(next, f, 4, &next);
    GL_CHECK_EQ(n, 4 + 48);
    GL_CHECK_EQ(f[0], 0x03);
    GL_CHECK_EQ(f[1], 0x00);
    GL_CHECK_EQ(f[2], 0x10);
    GL_CHECK_EQ(f[3], 0xF0);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

GL_TEST(test_sector_erase)
{
    uint8_t f[8];
    size_t next = 0, n;
    fresh_();
    GL_CHECK_EQ(gl_mx25r_init(&fl_), GL_OK);
    memset(&gl_sim_flash_mem()[0x7000], 0x00, 3u * 4096u);
    gl_sim_trace_clear();
    const uint64_t t0 = gl_sim_now_us();
    GL_CHECK_EQ(gl_mx25r_erase_sector(&fl_, 0x008123u), GL_OK); /* inside the sector at 0x8000 */
    GL_CHECK(gl_sim_now_us() - t0 >= 40000u);                   /* waited for the erase */

    n = cs_frame_(next, f, sizeof(f), &next);
    GL_CHECK_EQ(n, 1);
    GL_CHECK_EQ(f[0], 0x06);
    n = cs_frame_(next, f, sizeof(f), &next);
    GL_CHECK_EQ(n, 4);
    GL_CHECK_EQ(f[0], 0x20);
    GL_CHECK_EQ(f[1], 0x00);
    GL_CHECK_EQ(f[2], 0x80);
    GL_CHECK_EQ(f[3], 0x00);

    /* exactly one sector erased */
    GL_CHECK_EQ(gl_sim_flash_mem()[0x7FFF], 0x00);
    GL_CHECK_EQ(gl_sim_flash_mem()[0x8000], 0xFF);
    GL_CHECK_EQ(gl_sim_flash_mem()[0x8FFF], 0xFF);
    GL_CHECK_EQ(gl_sim_flash_mem()[0x9000], 0x00);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

GL_TEST(test_deep_power_down_and_auto_wake)
{
    uint8_t f[8], b[4];
    size_t next = 0, n;
    fresh_();
    GL_CHECK_EQ(gl_mx25r_init(&fl_), GL_OK);
    gl_sim_trace_clear();
    GL_CHECK_EQ(gl_mx25r_sleep(&fl_), GL_OK);
    GL_CHECK(gl_sim_flash_stats()->deep_power_down);
    n = cs_frame_(next, f, sizeof(f), &next);
    GL_CHECK_EQ(n, 1);
    GL_CHECK_EQ(f[0], 0xB9);
    GL_CHECK_EQ(gl_mx25r_sleep(&fl_), GL_OK); /* idempotent: no second command */
    GL_CHECK_EQ(cs_frame_(next, f, sizeof(f), &next), 0);

    /* any access wakes it first */
    gl_sim_trace_clear();
    GL_CHECK_EQ(gl_mx25r_read(&fl_, 0, b, sizeof(b)), GL_OK);
    next = 0;
    n = cs_frame_(next, f, sizeof(f), &next);
    GL_CHECK_EQ(n, 1);
    GL_CHECK_EQ(f[0], 0xAB);
    GL_CHECK(!gl_sim_flash_stats()->deep_power_down);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);

    /* a driver start-up with the device left asleep by the previous run */
    GL_CHECK_EQ(gl_mx25r_sleep(&fl_), GL_OK);
    GL_CHECK_EQ(gl_mx25r_init(&fl_), GL_OK);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

GL_TEST(test_parameter_errors)
{
    uint8_t b[4] = { 0, 0, 0, 0 };
    gl_mx25r_t absent;
    fresh_();
    GL_CHECK_EQ(gl_mx25r_init(&fl_), GL_OK);
    GL_CHECK_EQ(gl_mx25r_read(&fl_, GL_MX25R_SIZE_BYTES, b, 1), GL_ERR_PARAM);
    GL_CHECK_EQ(gl_mx25r_read(&fl_, GL_MX25R_SIZE_BYTES - 2u, b, 4), GL_ERR_PARAM);
    GL_CHECK_EQ(gl_mx25r_prog(&fl_, GL_MX25R_SIZE_BYTES - 2u, b, 4), GL_ERR_PARAM);
    GL_CHECK_EQ(gl_mx25r_erase_sector(&fl_, GL_MX25R_SIZE_BYTES), GL_ERR_PARAM);
    GL_CHECK_EQ(gl_mx25r_read(&fl_, GL_MX25R_SIZE_BYTES - 4u, b, 4), GL_OK);
    memset(&absent, 0, sizeof(absent));
    GL_CHECK_EQ(gl_mx25r_read(&absent, 0, b, 4), GL_ERR_NOT_FOUND);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

GL_TEST(test_log_and_store_on_the_driver)
{
    gl_flash_if_t fi;
    gl_store_t store;
    gl_log_t log;
    gl_settings_t set, got;
    uint8_t blob[GL_SETTINGS_BLOB_LEN];
    const uint8_t *p = NULL;
    size_t len = 0;

    fresh_();
    GL_CHECK_EQ(gl_mx25r_init(&fl_), GL_OK);
    gl_mx25r_flash_if(&fl_, &fi);
    GL_CHECK_EQ(fi.sector_size, 4096u);

    /* blob store in sectors 0..3 */
    GL_CHECK_EQ(gl_store_mount(&store, &fi, 0, 4), GL_OK);
    GL_CHECK_EQ(gl_store_get(&store, GL_STORE_ID_SETTINGS, &p, &len), GL_ERR_NOT_FOUND);
    gl_settings_defaults(&set);
    set.stimp_x2 = 23;
    set.units = (uint8_t)GL_UNITS_METRES;
    for (unsigned i = 0; i < 300u; i++) { /* enough rewrites to roll over several sectors */
        set.manual_distance_cm = (uint16_t)(100u + i);
        gl_settings_encode(&set, blob);
        if (gl_store_put(&store, GL_STORE_ID_SETTINGS, blob, sizeof(blob)) != GL_OK) {
            GL_CHECK(false);
            break;
        }
    }
    /* "power cycle": new driver and store instances, same flash contents */
    GL_CHECK_EQ(gl_mx25r_sleep(&fl_), GL_OK);
    GL_CHECK_EQ(gl_mx25r_init(&fl_), GL_OK);
    gl_mx25r_flash_if(&fl_, &fi);
    GL_CHECK_EQ(gl_store_mount(&store, &fi, 0, 4), GL_OK);
    GL_CHECK_EQ(gl_store_get(&store, GL_STORE_ID_SETTINGS, &p, &len), GL_OK);
    GL_CHECK_EQ(len, GL_SETTINGS_BLOB_LEN);
    GL_CHECK_EQ(gl_settings_decode(p, len, &got), GL_OK);
    GL_CHECK_EQ(got.stimp_x2, 23);
    GL_CHECK_EQ(got.manual_distance_cm, 399);

    /* ring log in the 6 sectors after the store, wrapped several times */
    GL_CHECK_EQ(gl_log_mount(&log, &fi, 4u * 4096u, 6), GL_OK);
    uint32_t last_seq = 0;
    for (unsigned i = 0; i < 700u; i++) {
        uint8_t rec[72];
        memset(rec, (int)(i & 0xFFu), sizeof(rec));
        if (gl_log_append(&log, GL_LOG_REC_READ, 0, rec, sizeof(rec), &last_seq) != GL_OK) {
            GL_CHECK(false);
            break;
        }
    }
    GL_CHECK_EQ(gl_log_mount(&log, &fi, 4u * 4096u, 6), GL_OK);
    gl_log_iter_t it;
    gl_log_rec_t rec;
    uint8_t buf[72];
    unsigned count = 0;
    uint32_t prev = 0;
    bool ordered = true, content = true;
    gl_log_iter_begin(&log, &it);
    while (gl_log_iter_next(&log, &it, &rec, buf, sizeof(buf)) == GL_OK) {
        if (count > 0u && rec.seq != prev + 1u) {
            ordered = false;
        }
        /* record i got sequence number i + 1 */
        if (buf[0] != (uint8_t)((rec.seq - 1u) & 0xFFu) || buf[71] != buf[0]) {
            content = false;
        }
        prev = rec.seq;
        count++;
    }
    GL_CHECK(ordered);
    GL_CHECK(content);
    GL_CHECK_EQ(prev, last_seq);
    GL_CHECK(count >= 200u && count < 700u); /* the ring kept the newest records */

    const gl_sim_flash_stats_t *s = gl_sim_flash_stats();
    printf("    store + log on the driver: %u page programs, %u sector erases, %u records kept of 700,"
           " %u non-blank bytes programmed\n",
           (unsigned)s->page_programs, (unsigned)s->sector_erases, count,
           (unsigned)s->overwrite_bytes);
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

GL_TEST(test_model_catches_protocol_errors)
{
    const gl_spi_cfg_t spi = { 8000000u, 0u, false };
    const uint8_t pp[6] = { 0x02, 0x00, 0x00, 0x00, 0x12, 0x34 };
    const uint8_t rd[4] = { 0x03, 0x00, 0x00, 0x00 };
    const uint8_t dp = 0xB9;
    fresh_();
    (void)gl_hal_spi_configure(GL_SPI_BUS_1, &spi);
    /* page program without WREN */
    gl_hal_gpio_write(GL_PIN_FLASH_CS, false);
    (void)gl_hal_spi_transfer(GL_SPI_BUS_1, pp, NULL, sizeof(pp));
    gl_hal_gpio_write(GL_PIN_FLASH_CS, true);
    GL_CHECK_EQ(gl_sim_violations()->flash, 1u);
    GL_CHECK_EQ(gl_sim_flash_mem()[0], 0xFF);
    /* a command while in deep power-down */
    gl_hal_gpio_write(GL_PIN_FLASH_CS, false);
    (void)gl_hal_spi_transfer(GL_SPI_BUS_1, &dp, NULL, 1);
    gl_hal_gpio_write(GL_PIN_FLASH_CS, true);
    gl_hal_gpio_write(GL_PIN_FLASH_CS, false);
    (void)gl_hal_spi_transfer(GL_SPI_BUS_1, rd, NULL, sizeof(rd));
    gl_hal_gpio_write(GL_PIN_FLASH_CS, true);
    GL_CHECK_EQ(gl_sim_violations()->flash, 2u);
    /* LCD and flash selected together */
    gl_hal_gpio_write(GL_PIN_FLASH_CS, false);
    gl_hal_gpio_write(GL_PIN_LCD_SCS, true);
    (void)gl_hal_spi_transfer(GL_SPI_BUS_1, rd, NULL, 1);
    GL_CHECK_EQ(gl_sim_violations()->spi, 1u);
    gl_hal_gpio_write(GL_PIN_LCD_SCS, false);
    gl_hal_gpio_write(GL_PIN_FLASH_CS, true);
    /* a transfer with nothing selected */
    (void)gl_hal_spi_transfer(GL_SPI_BUS_1, rd, NULL, 1);
    GL_CHECK_EQ(gl_sim_violations()->spi, 2u);
}

int main(void)
{
    GL_RUN(test_init_reads_jedec_id);
    GL_RUN(test_program_exact_bytes_and_page_split);
    GL_RUN(test_sector_erase);
    GL_RUN(test_deep_power_down_and_auto_wake);
    GL_RUN(test_parameter_errors);
    GL_RUN(test_log_and_store_on_the_driver);
    GL_RUN(test_model_catches_protocol_errors);
    return gl_test_summary();
}
