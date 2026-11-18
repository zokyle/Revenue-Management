/*
 * test_factory.c - the factory and calibration commands of phase 3, end to
 * end: the whole firmware on the simulator, a USB host on its CDC port.
 *
 *   identity and version negotiation; the unlock rule; bad arguments
 *   both cameras: identity (also with the other one dead), a band, a dark
 *       frame, download in pieces and out of order, the field test of gate 2
 *   display test patterns; the display rotation of E12, proved from pixels
 *   grain LEDs, photodiode dark offset (assembly step 11a)
 *   the level zero ARMED over USB and run on the seat plate, two seats (E11)
 *   six-face step by step, the temperature fit, CAM_HORIZON, GRAIN_FLOOR,
 *       the serial number
 *   the sleep-current test
 *   the field log: replay records, tilt-only records, download with resume
 *
 * Every current is a figure of the simulator's supply model; nothing here
 * was measured on hardware (there is none).
 */
#include "gl_e2e_world.h"

#include "gl_fieldlog.h"
#include "gl_pins.h"
#include "gl_usb_ids.h"

static uint32_t now_ms_(void)
{
    return (uint32_t)(gl_sim_now_us() / 1000u);
}

static uint8_t seq_no_;

/* One command and its response: returns the payload length (status byte
 * included) or -1; *pl points at the status byte. */
static int cmd_(uint8_t cmd, const void *payload, size_t n, const uint8_t **pl)
{
    uint8_t seq;
    int len;
    seq_no_++;
    host_rx_len_ = 0;
    host_send_(seq_no_, cmd, payload, n);
    len = host_get_((uint8_t)(cmd | GL_PROTO_RESPONSE_FLAG), &seq, pl);
    if (len >= 0) {
        GL_CHECK_EQ(seq, seq_no_);
    }
    return len;
}

/* The status byte of a command (255 = no answer). */
static unsigned st_(uint8_t cmd, const void *payload, size_t n)
{
    const uint8_t *pl;
    const int len = cmd_(cmd, payload, n, &pl);
    return (len >= 1) ? pl[0] : 255u;
}

static void unlock_(void)
{
    GL_CHECK_EQ(st_(GL_CMD_UNLOCK, "GLFC", 4), GL_OK);
    GL_CHECK(app.proto.unlocked);
}

static void dock_(void)
{
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    gl_sim_usb_host_open(true);
    host_rx_len_ = 0;
    run_until_ms_(now_ms_() + 500u);
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_USB);
    GL_CHECK(app.usb_on);
}

static void undock_(void)
{
    gl_sim_set_input(GL_PIN_VBUS_SENSE, false);
    gl_sim_usb_host_open(false);
    run_until_ms_(now_ms_() + 100u);
}

/* Marker powered up in the cradle with a host, lying still. */
static void docked_(bool erase)
{
    world_defaults_();
    W.t_pick_s = 1.0e9;
    W.t_place_s = 1.0e9;
    board_up_(erase);
    gl_sim_set_input(GL_PIN_VBUS_SENSE, true);
    gl_sim_usb_host_open(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    watch_reset_();
    host_rx_len_ = 0;
    run_until_ms_(now_ms_() + 400u);
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_USB);
}

static void no_violation_(void)
{
    if (gl_sim_violation_total() != 0u) {
        printf("    first violation: %s\n", gl_sim_violations()->first);
    }
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* ======================================================================= */
/* 1. identity, versions, the unlock rule, bad arguments                    */
/* ======================================================================= */

GL_TEST(test_identity_and_version_negotiation)
{
    const uint8_t *pl;
    uint8_t v;
    int n;

    docked_(true);
    /* GET_INFO still answers, and says version 3 */
    n = cmd_(GL_CMD_GET_INFO, NULL, 0, &pl);
    GL_CHECK_EQ(n, 1 + (int)GL_PROTO_INFO_LEN);
    GL_CHECK_EQ(pl[1], 3);
    GL_CHECK_EQ(pl[2], 5); /* hardware revision E */
    /* GET_IDENT without a host version, and with 1, 2, 3 and a future 9 */
    n = cmd_(GL_CMD_GET_IDENT, NULL, 0, &pl);
    GL_CHECK_EQ(n, 1 + (int)GL_PROTO_IDENT_LEN);
    GL_CHECK_EQ(pl[0], GL_OK);
    GL_CHECK_EQ(pl[1], GL_PROTO_VERSION);
    GL_CHECK_EQ(pl[2], GL_PROTO_VERSION);
    GL_CHECK_EQ(pl[3], 5);
    GL_CHECK_EQ(pl[4], 'E');
    GL_CHECK(memcmp(&pl[5], "GL-1\0\0\0\0", 8) == 0);
    GL_CHECK_EQ(gl_get_u16(&pl[13]), GL_APP_FW_VERSION);
    GL_CHECK_EQ(pl[15], GL_CAL_VERSION);
    GL_CHECK_EQ(pl[16], GL_FIELDLOG_LAYOUT);
    GL_CHECK_EQ(gl_get_u32(&pl[17]), GL_APP_FW_BUILD);
    GL_CHECK_EQ(gl_get_u32(&pl[21]), gl_solver_version());
    {
        uint8_t uid[12];
        gl_hal_unique_id(uid);
        GL_CHECK_MEM(&pl[25], uid, 12);
        GL_CHECK_EQ(gl_get_u32(&pl[37]), gl_cal_serial_from_uid(uid));
    }
    GL_CHECK_EQ(gl_get_u32(&pl[41]), 0u); /* no serial stored on a fresh unit */
    GL_CHECK_EQ(pl[45] | pl[46] | pl[47] | pl[48] | pl[49], 0); /* no calibration at all */
    /* placeholders for the USB ids: NOT a release build; locked; calibration incomplete */
    GL_CHECK_EQ(pl[50], 0);
    GL_CHECK_EQ(GL_USB_IDS_ARE_PLACEHOLDERS, 1);
    /* the revision string of the parameter file the firmware was generated from */
    GL_CHECK(strncmp((const char *)&pl[51], GL_CFG_PARAMS_REV, 13) == 0);
    {
        /* the command bit map: every command of this protocol version */
        static const uint8_t have[] = {
            GL_CMD_PING, GL_CMD_GET_INFO, GL_CMD_GET_STATUS, GL_CMD_GET_SETTINGS,
            GL_CMD_SET_SETTINGS, GL_CMD_GET_CAL, GL_CMD_SET_CAL, GL_CMD_START_CAL,
            GL_CMD_LOG_INFO, GL_CMD_LOG_READ, GL_CMD_LOG_ERASE, GL_CMD_STREAM, GL_CMD_SET_TIME,
            GL_CMD_UNLOCK, GL_CMD_REBOOT, GL_CMD_SHIP_MODE, GL_CMD_GET_POWER, GL_CMD_SET_CHARGE,
            GL_CMD_GET_IDENT, GL_CMD_GET_SENSORS, GL_CMD_CAM_ID, GL_CMD_CAM_CAPTURE,
            GL_CMD_CAM_DATA, GL_CMD_CAM_FIELD, GL_CMD_DISPLAY_TEST, GL_CMD_GRAIN_TEST,
            GL_CMD_LEVEL_ZERO, GL_CMD_CAL_STATUS, GL_CMD_TILT_TEMPCO, GL_CMD_SET_CAM_HORIZON,
            GL_CMD_SET_GRAIN_FLOOR, GL_CMD_DISPLAY_ROT, GL_CMD_SLEEP_TEST, GL_CMD_LOG_SEEK,
            GL_CMD_SERIAL
        };
        unsigned bits = 0;
        for (size_t i = 0; i < sizeof(have); i++) {
            GL_CHECK(pl[65u + (unsigned)have[i] / 8u] & (1u << ((unsigned)have[i] % 8u)));
        }
        for (unsigned c = 0; c < 64u; c++) {
            bits += ((unsigned)pl[65u + c / 8u] >> (c % 8u)) & 1u;
        }
        GL_CHECK_EQ(bits, sizeof(have)); /* and no other */
        printf("    GET_IDENT: protocol %u, model %.8s rev %c, %u commands in the bit map, "
               "parameters \"%.13s\"\n", pl[1], (const char *)&pl[5], pl[4], bits,
               (const char *)&pl[51]);
    }
    for (v = 1; v <= 3; v++) {
        n = cmd_(GL_CMD_GET_IDENT, &v, 1, &pl);
        GL_CHECK_EQ(pl[0], GL_OK);
        GL_CHECK_EQ(pl[2], v); /* the version both speak */
    }
    v = 9;
    (void)cmd_(GL_CMD_GET_IDENT, &v, 1, &pl);
    GL_CHECK_EQ(pl[2], GL_PROTO_VERSION);
    v = 0;
    GL_CHECK_EQ(st_(GL_CMD_GET_IDENT, &v, 1), GL_ERR_PARAM);
    GL_CHECK_EQ(st_(GL_CMD_GET_IDENT, "ab", 2), GL_ERR_PARAM);
    /* a command this unit does not know */
    GL_CHECK_EQ(st_(0x3F, NULL, 0), GL_ERR_UNSUPPORTED);
    GL_CHECK_EQ(st_(0x24, NULL, 0), GL_ERR_UNSUPPORTED);

    /* GET_SENSORS */
    gl_sim_set_cell_temperature(27.5f);
    gl_sim_set_vdda_mv(2795);
    n = cmd_(GL_CMD_GET_SENSORS, NULL, 0, &pl);
    GL_CHECK_EQ(n, 1 + (int)GL_PROTO_SENSORS_LEN);
    GL_CHECK_EQ(pl[0], GL_OK);
    GL_CHECK_NEAR(gl_get_u16(&pl[1]), 3900.0, 60.0);              /* cell */
    GL_CHECK_NEAR(gl_get_u16(&pl[3]), 2795.0, 3.0);               /* the 2.8 V rail */
    GL_CHECK_NEAR((int16_t)gl_get_u16(&pl[5]), 275.0, 2.0);       /* NTC2 */
    GL_CHECK_NEAR(gl_get_u16(&pl[11]), gl_sim_ntc_counts_at(27.5), 3.0); /* raw */
    GL_CHECK_EQ(gl_get_u16(&pl[13]), GL_HAL_ADC_FULL_SCALE);
    GL_CHECK_EQ(pl[15], 0);                                       /* no thermistor fault */
    GL_CHECK_EQ(pl[16] & 0x07u, 0x03u);                           /* VBUS, USB supply, rail off */
    printf("    GET_SENSORS: cell %u mV, 2.8 V rail %u mV, NTC2 %.1f C (raw %u of %u), MCU %.1f C, "
           "IMU %.1f C\n", gl_get_u16(&pl[1]), gl_get_u16(&pl[3]),
           0.1 * (double)(int16_t)gl_get_u16(&pl[5]), gl_get_u16(&pl[11]), gl_get_u16(&pl[13]),
           0.1 * (double)(int16_t)gl_get_u16(&pl[7]), 0.1 * (double)(int16_t)gl_get_u16(&pl[9]));
    GL_CHECK_EQ(st_(GL_CMD_GET_SENSORS, "x", 1), GL_ERR_PARAM);
    /* a thermistor that has come off: reported, not hidden */
    gl_sim_ntc_set_fault(GL_SIM_NTC_OPEN);
    (void)cmd_(GL_CMD_GET_SENSORS, NULL, 0, &pl);
    GL_CHECK_EQ((int16_t)gl_get_u16(&pl[5]), GL_PROTO_TEMP_NONE);
    GL_CHECK(pl[15] != 0);
    gl_sim_ntc_set_fault(GL_SIM_NTC_NORMAL);
    no_violation_();
}

/* Every command that writes calibration, arms something or leaves for the
 * loader is refused while locked, and changes nothing. */
GL_TEST(test_guarded_commands_need_unlock)
{
    static const struct {
        uint8_t cmd;
        uint8_t n;
        uint8_t p[12];
        const char *what;
    } guarded[] = {
        { GL_CMD_SHIP_MODE, 4, "SHIP", "arm ship mode" },
        { GL_CMD_LEVEL_ZERO, 2, { GL_ZERO_OP_ARM, 0 }, "arm a level zero" },
        { GL_CMD_SET_CAM_HORIZON, 9, { 0, 0, 0, 0x7C, 0x43, 0, 0, 0, 0 }, "set CAM_HORIZON" },
        { GL_CMD_DISPLAY_ROT, 5, { 1, 0, 0, 0, 0 }, "write the display rotation" },
        { GL_CMD_GRAIN_TEST, 1, { GL_GRAIN_MODE_STORE }, "store the dark offset" },
        { GL_CMD_SLEEP_TEST, 3, { GL_PROTO_WAKE_TIMER, 10, 0 }, "arm the sleep test" },
        { GL_CMD_SERIAL, 4, "SNUM", "commit the serial number" },
        { GL_CMD_SET_CHARGE, 1, { 1 }, "hold the charge" },
        { GL_CMD_REBOOT, 4, "DFU!", "leave for the update loader" },
        { GL_CMD_LOG_ERASE, 4, "ERAS", "erase the log" },
        { GL_CMD_START_CAL, 2, { GL_CALPROC_SIX_FACE, 0 }, "six-face step" },
    };
    uint8_t big[1 + 4 * 64];
    const uint8_t *pl;
    uint32_t progs;

    docked_(true);
    progs = gl_sim_flash_stats()->page_programs;
    for (size_t i = 0; i < GL_ARRAY_LEN(guarded); i++) {
        const unsigned st = st_(guarded[i].cmd, guarded[i].p, guarded[i].n);
        if (st != GL_ERR_STATE) {
            printf("    locked, %s: status %u\n", guarded[i].what, st);
        }
        GL_CHECK_EQ(st, GL_ERR_STATE);
        GL_CHECK_EQ(gl_proto_needs_unlock(guarded[i].cmd, guarded[i].p, guarded[i].n), true);
    }
    /* the two with long payloads */
    memset(big, 0, sizeof(big));
    big[0] = 5;
    GL_CHECK_EQ(st_(GL_CMD_TILT_TEMPCO, big, 5 + 16 * 5), GL_ERR_STATE);
    big[0] = 20;
    GL_CHECK_EQ(st_(GL_CMD_SET_GRAIN_FLOOR, big, 1 + 4 * 20), GL_ERR_STATE);
    /* nothing was armed, stored or started */
    GL_CHECK(!app.ship_armed && !app.fac.sleep_armed && !app.six.active && !app.log_erasing);
    GL_CHECK_EQ(app.fac.zero.state, GL_ZERO_STATE_IDLE);
    GL_CHECK_EQ(app.cal_dev.flags | app.cal_grain.flags | app.cal_tilt.flags |
                app.cal_cam[0].flags, 0);
    GL_CHECK_EQ(gl_sim_flash_stats()->page_programs, progs);
    GL_CHECK_EQ(gl_sim_stats()->reboots, 0u);
    /* reading needs no unlock */
    GL_CHECK_EQ(st_(GL_CMD_DISPLAY_ROT, "\0", 1), GL_OK);
    GL_CHECK_EQ(st_(GL_CMD_SERIAL, NULL, 0), GL_OK);
    GL_CHECK_EQ(st_(GL_CMD_SHIP_MODE, "STAY", 4), GL_OK);
    GL_CHECK_EQ(st_(GL_CMD_CAL_STATUS, NULL, 0), GL_OK);
    {
        const uint8_t status[2] = { GL_ZERO_OP_STATUS, 0 };
        GL_CHECK_EQ(st_(GL_CMD_LEVEL_ZERO, status, 2), GL_OK);
    }
    /* a wrong word does not unlock; the right one does; leaving the cradle locks */
    GL_CHECK_EQ(st_(GL_CMD_UNLOCK, "glfc", 4), GL_ERR_PARAM);
    GL_CHECK(!app.proto.unlocked);
    unlock_();
    (void)cmd_(GL_CMD_GET_IDENT, NULL, 0, &pl);
    GL_CHECK(pl[50] & GL_PROTO_IDENT_UNLOCKED);
    GL_CHECK_EQ(st_(GL_CMD_SHIP_MODE, "SHIP", 4), GL_OK);
    GL_CHECK_EQ(st_(GL_CMD_SHIP_MODE, "STAY", 4), GL_OK);
    undock_();
    run_until_ms_(now_ms_() + 300u);
    GL_CHECK(!app.proto.unlocked);
    dock_();
    GL_CHECK_EQ(st_(GL_CMD_SHIP_MODE, "SHIP", 4), GL_ERR_STATE);
    /* the cradle sleep (30 s without a word) locks too */
    unlock_();
    run_until_ms_(now_ms_() + 31000u);
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_SLEEP);
    GL_CHECK(!app.proto.unlocked);
    no_violation_();
}

/* Every factory command answers a defined status to bad arguments, and a bad
 * command changes nothing. */
GL_TEST(test_bad_arguments)
{
    static const struct {
        uint8_t cmd;
        uint8_t n;
        uint8_t p[12];
        uint8_t want;
    } bad[] = {
        { GL_CMD_CAM_ID, 1, { 2 }, GL_ERR_PARAM },                     /* no camera 2 */
        { GL_CMD_CAM_ID, 0, { 0 }, GL_ERR_PARAM },
        { GL_CMD_CAM_ID, 2, { 0, 0 }, GL_ERR_PARAM },
        { GL_CMD_CAM_CAPTURE, 10, { 2, 0, 0, 0, 0, 0, 0x80, 2, 96, 0 }, GL_ERR_PARAM },
        { GL_CMD_CAM_CAPTURE, 10, { 0, 2, 0, 0, 0, 0, 0x80, 2, 96, 0 }, GL_ERR_PARAM }, /* kind */
        { GL_CMD_CAM_CAPTURE, 10, { 0, 0, 0, 0, 0, 0, 0, 0, 96, 0 }, GL_ERR_PARAM },   /* w = 0 */
        { GL_CMD_CAM_CAPTURE, 10, { 0, 0, 0, 0, 0, 0, 0x82, 2, 96, 0 }, GL_ERR_PARAM },/* w % 4 */
        { GL_CMD_CAM_CAPTURE, 10, { 0, 0, 0, 0, 0, 0, 0x80, 2, 95, 0 }, GL_ERR_PARAM },/* h odd */
        { GL_CMD_CAM_CAPTURE, 10, { 0, 0, 0, 0, 0, 0, 0x80, 2, 0xE0, 1 }, GL_ERR_PARAM }, /* 640x480 */
        { GL_CMD_CAM_CAPTURE, 10, { 0, 0, 0x80, 2, 0, 0, 0x80, 2, 96, 0 }, GL_ERR_PARAM },/* x0 = 640 */
        { GL_CMD_CAM_CAPTURE, 9, { 0 }, GL_ERR_PARAM },
        { GL_CMD_CAM_DATA, 6, { 0, 0, 0, 0, 100, 0 }, GL_ERR_EMPTY },  /* nothing captured */
        { GL_CMD_CAM_DATA, 5, { 0 }, GL_ERR_PARAM },
        { GL_CMD_CAM_FIELD, 1, { 7 }, GL_ERR_PARAM },
        { GL_CMD_DISPLAY_TEST, 2, { GL_DISP_PATTERN_COUNT, 5 }, GL_ERR_PARAM },
        { GL_CMD_DISPLAY_TEST, 2, { GL_DISP_PATTERN_BLACK, 0 }, GL_ERR_PARAM },   /* no time */
        { GL_CMD_DISPLAY_TEST, 2, { GL_DISP_PATTERN_BLACK, 121 }, GL_ERR_PARAM },
        { GL_CMD_DISPLAY_TEST, 1, { 1 }, GL_ERR_PARAM },
        { GL_CMD_GRAIN_TEST, 1, { 3 }, GL_ERR_PARAM },
        { GL_CMD_LEVEL_ZERO, 2, { 3, 0 }, GL_ERR_PARAM },              /* no such operation */
        { GL_CMD_LEVEL_ZERO, 2, { GL_ZERO_OP_ARM, 2 }, GL_ERR_PARAM }, /* no such seat */
        { GL_CMD_LEVEL_ZERO, 1, { 0 }, GL_ERR_PARAM },
        { GL_CMD_CAL_STATUS, 1, { 0 }, GL_ERR_PARAM },
        { GL_CMD_SET_CAM_HORIZON, 9, { 2, 0, 0, 0x7C, 0x43, 0, 0, 0, 0 }, GL_ERR_PARAM },
        { GL_CMD_SET_CAM_HORIZON, 9, { 0, 0, 0, 0xC8, 0x43, 0, 0, 0, 0 }, GL_ERR_RANGE }, /* row 400 */
        { GL_CMD_SET_CAM_HORIZON, 9, { 0, 0, 0, 0xC0, 0x7F, 0, 0, 0, 0 }, GL_ERR_RANGE }, /* NaN */
        { GL_CMD_SET_CAM_HORIZON, 8, { 0 }, GL_ERR_PARAM },
        { GL_CMD_DISPLAY_ROT, 1, { 2 }, GL_ERR_PARAM },
        { GL_CMD_DISPLAY_ROT, 5, { 0, 0, 0, 0, 0 }, GL_ERR_PARAM },    /* read with a value */
        { GL_CMD_DISPLAY_ROT, 1, { 1 }, GL_ERR_PARAM },                /* write without one */
        { GL_CMD_DISPLAY_ROT, 5, { 1, 0xCD, 0xCC, 0x4C, 0x3D }, GL_ERR_RANGE }, /* 0.05 rad */
        { GL_CMD_DISPLAY_ROT, 5, { 1, 0, 0, 0xC0, 0x7F }, GL_ERR_RANGE },       /* NaN */
        { GL_CMD_SLEEP_TEST, 3, { 0x08, 10, 0 }, GL_ERR_PARAM },       /* unknown wake bit */
        { GL_CMD_SLEEP_TEST, 3, { GL_PROTO_WAKE_TIMER, 0, 0 }, GL_ERR_PARAM }, /* timer of 0 s */
        { GL_CMD_SLEEP_TEST, 2, { 1, 1 }, GL_ERR_PARAM },
        { GL_CMD_LOG_SEEK, 3, { 0 }, GL_ERR_PARAM },
        { GL_CMD_SERIAL, 4, "snum", GL_ERR_PARAM },
        { GL_CMD_SERIAL, 3, "SNU", GL_ERR_PARAM },
        { GL_CMD_SHIP_MODE, 4, "ship", GL_ERR_PARAM },
    };
    uint8_t big[5 + 16 * 17];
    uint32_t progs;

    docked_(true);
    unlock_(); /* so that it is the ARGUMENT that is refused, not the lock */
    progs = gl_sim_flash_stats()->page_programs;
    for (size_t i = 0; i < GL_ARRAY_LEN(bad); i++) {
        const unsigned st = st_(bad[i].cmd, bad[i].p, bad[i].n);
        if (st != bad[i].want) {
            printf("    case %u (command 0x%02X): status %u, expected %u\n", (unsigned)i,
                   bad[i].cmd, st, bad[i].want);
        }
        GL_CHECK_EQ(st, bad[i].want);
    }
    /* the temperature fit: too few points (fewer than FIVE since the phase-3
     * review: a quadratic through three is exact and its residual says
     * nothing), too many, a length that does not match the count, a point
     * out of range, a span under 30 K, only two distinct temperatures */
    memset(big, 0, sizeof(big));
    big[0] = 2;
    GL_CHECK_EQ(st_(GL_CMD_TILT_TEMPCO, big, 5 + 16 * 2), GL_ERR_PARAM);
    big[0] = 4;
    GL_CHECK_EQ(st_(GL_CMD_TILT_TEMPCO, big, 5 + 16 * 4), GL_ERR_PARAM);
    big[0] = 17;
    GL_CHECK_EQ(st_(GL_CMD_TILT_TEMPCO, big, 5 + 16 * 17), GL_ERR_PARAM);
    big[0] = 6;
    GL_CHECK_EQ(st_(GL_CMD_TILT_TEMPCO, big, 5 + 16 * 5), GL_ERR_PARAM);
    big[0] = 5;
    gl_put_f32(&big[1], 25.0f);
    gl_put_f32(&big[5], 10.0f);
    gl_put_f32(&big[21], 10.0f);
    gl_put_f32(&big[37], 45.0f);
    gl_put_f32(&big[53], 45.0f);
    gl_put_f32(&big[69], 45.0f);
    GL_CHECK(st_(GL_CMD_TILT_TEMPCO, big, 5 + 16 * 5) != GL_OK); /* two distinct temperatures */
    gl_put_f32(&big[21], 20.0f);
    gl_put_f32(&big[37], 25.0f);
    gl_put_f32(&big[53], 35.0f);
    gl_put_f32(&big[9], 0.9f); /* an offset of 0.9 g */
    GL_CHECK_EQ(st_(GL_CMD_TILT_TEMPCO, big, 5 + 16 * 5), GL_ERR_PARAM);
    gl_put_f32(&big[9], 0.0f);
    gl_put_f32(&big[1], 200.0f); /* t0 */
    GL_CHECK_EQ(st_(GL_CMD_TILT_TEMPCO, big, 5 + 16 * 5), GL_ERR_PARAM);
    gl_put_f32(&big[1], 25.0f);
    gl_put_f32(&big[69], 39.0f); /* five good points, 10 .. 39 C: a span of 29 K */
    GL_CHECK_EQ(st_(GL_CMD_TILT_TEMPCO, big, 5 + 16 * 5), GL_ERR_PARAM);
    /* ... and five good points over 35 K on a unit WITHOUT a six-face
     * calibration: there are no offsets the terms could be added to */
    gl_put_f32(&big[69], 45.0f);
    GL_CHECK(!(app.cal_tilt.flags & GL_CAL_TILT_FLAG_FACTORY));
    GL_CHECK_EQ(st_(GL_CMD_TILT_TEMPCO, big, 5 + 16 * 5), GL_ERR_STATE);
    GL_CHECK(!(app.cal_tilt.flags & GL_CAL_TILT_FLAG_TEMPCO));
    /* the two new optional bytes: values beyond their range */
    {
        const uint8_t dt[3] = { GL_DISP_PATTERN_REF_RAW, 30, 2 };
        const uint8_t dn[3] = { GL_DISP_PATTERN_NORMAL, 0, 1 };
        const uint8_t zr[3] = { GL_ZERO_OP_ARM, 0, 121 };
        const uint8_t zs[3] = { GL_ZERO_OP_STATUS, 0, 30 };
        GL_CHECK_EQ(st_(GL_CMD_DISPLAY_TEST, dt, 3), GL_ERR_PARAM);
        GL_CHECK_EQ(st_(GL_CMD_DISPLAY_TEST, dn, 3), GL_ERR_PARAM);
        GL_CHECK_EQ(st_(GL_CMD_LEVEL_ZERO, zr, 3), GL_ERR_PARAM);
        GL_CHECK_EQ(st_(GL_CMD_LEVEL_ZERO, zs, 3), GL_ERR_PARAM);
        GL_CHECK(!app.fac.plate_armed && app.fac.zero.state == (uint8_t)GL_ZERO_STATE_IDLE);
    }
    /* the grain floor: too few readings, a count that does not match, a NaN */
    memset(big, 0, sizeof(big));
    big[0] = 19;
    GL_CHECK_EQ(st_(GL_CMD_SET_GRAIN_FLOOR, big, 1 + 4 * 19), GL_ERR_PARAM);
    big[0] = 21;
    GL_CHECK_EQ(st_(GL_CMD_SET_GRAIN_FLOOR, big, 1 + 4 * 20), GL_ERR_PARAM);
    big[0] = 20;
    gl_put_f32(&big[1 + 4 * 7], (float)NAN);
    GL_CHECK_EQ(st_(GL_CMD_SET_GRAIN_FLOOR, big, 1 + 4 * 20), GL_ERR_PARAM);
    /* nothing was stored by any of them */
    GL_CHECK_EQ(gl_sim_flash_stats()->page_programs, progs);
    GL_CHECK_EQ(app.cal_dev.flags | app.cal_grain.flags | app.cal_tilt.flags |
                app.cal_cam[0].flags | app.cal_cam[1].flags, 0);
    GL_CHECK(!app.fac.sleep_armed && app.fac.pattern == 0u);
    GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, 0u);
    printf("    %u bad requests of the factory commands: each answered its defined status, "
           "nothing stored, no camera powered\n", (unsigned)GL_ARRAY_LEN(bad) + 9u);
    no_violation_();
}

/* ======================================================================= */
/* 2. cameras                                                               */
/* ======================================================================= */

static struct {
    int mode;          /* 0 = the green, 1 = dark with a light leak, 2 = the gate-2 bars */
    float upper, lower;/* brightness of the two bars */
    uint16_t row_up, row_lo;
} cam_scene_;

/* What the cameras see in the camera tests: a deterministic pattern. */
static void factory_scene_(void *ctx, gl_cam_id_t cam, uint16_t x0, uint16_t y0, uint16_t w,
                           uint16_t h, uint32_t frame_no, uint64_t t_us, uint8_t *luma)
{
    (void)ctx;
    (void)frame_no;
    (void)t_us;
    for (unsigned r = 0; r < h; r++) {
        for (unsigned c = 0; c < w; c++) {
            const unsigned sx = x0 + c, sy = y0 + r;
            uint8_t v;
            if (cam_scene_.mode == 1) {
                /* dark, with a leak of 12 x 6 pixels in the left camera only */
                v = (cam == GL_CAM_LEFT && sx >= 600u && sx < 612u && sy >= 200u && sy < 206u)
                        ? 90u : 3u;
            } else if (cam_scene_.mode == 2) {
                const int du = (int)sy - (int)cam_scene_.row_up, dl = (int)sy - (int)cam_scene_.row_lo;
                v = 20u;
                if (du >= -6 && du <= 6) {
                    v = (uint8_t)cam_scene_.upper;
                } else if (dl >= -6 && dl <= 6) {
                    v = (uint8_t)cam_scene_.lower;
                }
            } else {
                /* a ramp that identifies every pixel and the camera */
                v = (uint8_t)((sx + 3u * sy + ((cam == GL_CAM_RIGHT) ? 101u : 0u)) & 0xFFu);
            }
            luma[r * w + c] = v;
        }
    }
}

static uint8_t picture_[GL_PROTO_CAPTURE_MAX_BYTES];

/* Download `bytes` of the last capture in pieces of `piece` bytes. */
static void download_(uint32_t bytes, uint16_t piece)
{
    for (uint32_t off = 0; off < bytes; off += piece) {
        uint8_t req[6];
        const uint8_t *pl;
        const uint16_t n = (uint16_t)((bytes - off < piece) ? (bytes - off) : piece);
        int len;
        gl_put_u32(&req[0], off);
        gl_put_u16(&req[4], n);
        len = cmd_(GL_CMD_CAM_DATA, req, 6, &pl);
        GL_CHECK_EQ(len, 5 + (int)n);
        GL_CHECK_EQ(pl[0], GL_OK);
        GL_CHECK_EQ(gl_get_u32(&pl[1]), off);
        if (len == 5 + (int)n) {
            memcpy(&picture_[off], &pl[5], n);
        }
    }
}

GL_TEST(test_camera_identity_and_frames)
{
    const uint8_t *pl;
    uint8_t req[10];
    uint8_t cam;
    int n;

    docked_(true);
    gl_sim_cam_set_scene(factory_scene_, NULL);
    cam_scene_.mode = 0;
    /* identity of each camera */
    for (cam = 0; cam < 2; cam++) {
        n = cmd_(GL_CMD_CAM_ID, &cam, 1, &pl);
        GL_CHECK_EQ(n, 5);
        GL_CHECK_EQ(pl[0], GL_OK);
        GL_CHECK_EQ(pl[1], cam);
        GL_CHECK_EQ(gl_get_u16(&pl[2]), 0x7692);
        GL_CHECK_EQ(pl[4], 1);
        GL_CHECK(!gl_sim_cam_rail_on() && cam_pins_parked_());
    }
    GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, 2u);
    /* a dead LEFT camera does not hide the right one (the read's own
     * power-up stops at the first camera that fails) */
    gl_sim_cam_set_present(GL_CAM_LEFT, false);
    cam = 0;
    GL_CHECK_EQ(st_(GL_CMD_CAM_ID, &cam, 1), GL_ERR_IO);
    cam = 1;
    n = cmd_(GL_CMD_CAM_ID, &cam, 1, &pl);
    GL_CHECK_EQ(pl[0], GL_OK);
    GL_CHECK_EQ(gl_get_u16(&pl[2]), 0x7692);
    gl_sim_cam_set_present(GL_CAM_LEFT, true);
    /* a camera with another product id: reported as read, flagged */
    gl_sim_cam_set_pid(GL_CAM_RIGHT, 0x7740);
    n = cmd_(GL_CMD_CAM_ID, &cam, 1, &pl);
    GL_CHECK_EQ(pl[0], GL_OK);
    GL_CHECK_EQ(gl_get_u16(&pl[2]), 0x7740);
    GL_CHECK_EQ(pl[4], 0);
    gl_sim_cam_set_pid(GL_CAM_RIGHT, 0x7692);
    GL_CHECK(!gl_sim_cam_rail_on() && cam_pins_parked_());

    /* a band of the right camera: 640 x 96 from row 192 */
    req[0] = 1;
    req[1] = GL_CAPTURE_NORMAL;
    gl_put_u16(&req[2], 0);
    gl_put_u16(&req[4], 192);
    gl_put_u16(&req[6], 640);
    gl_put_u16(&req[8], 96);
    n = cmd_(GL_CMD_CAM_CAPTURE, req, 10, &pl);
    GL_CHECK_EQ(n, 1 + (int)GL_PROTO_CAPTURE_LEN);
    GL_CHECK_EQ(pl[0], GL_OK);
    GL_CHECK_EQ(pl[1], 1);
    GL_CHECK_EQ(gl_get_u16(&pl[3]), 0);
    GL_CHECK_EQ(gl_get_u16(&pl[5]), 192);
    GL_CHECK_EQ(gl_get_u16(&pl[7]), 640);
    GL_CHECK_EQ(gl_get_u16(&pl[9]), 96);
    GL_CHECK_EQ(gl_get_u32(&pl[11]), 61440u);
    {
        const uint32_t crc = gl_get_u32(&pl[23]);
        unsigned wrong = 0;
        /* downloaded in pieces of 1000, and again in pieces of 333 in the
         * same memory: a broken download is resumed at any offset */
        memset(picture_, 0xEE, sizeof(picture_));
        download_(61440u, 1000);
        GL_CHECK_EQ(gl_crc32(picture_, 61440u), crc);
        for (unsigned r = 0; r < 96u; r++) {
            for (unsigned c = 0; c < 640u; c++) {
                wrong += (picture_[r * 640u + c] != (uint8_t)((c + 3u * (192u + r) + 101u) & 0xFFu));
            }
        }
        GL_CHECK_EQ(wrong, 0u); /* every pixel is the one the right camera's scene put there */
        memset(picture_, 0xEE, 2000);
        download_(2000u, 333);
        GL_CHECK_EQ(gl_crc32(picture_, 61440u), crc);
        printf("    band 640 x 96 of the right camera: 61440 pixels downloaded in 62 pieces, "
               "CRC-32 0x%08X as reported, every pixel as the scene rendered it\n", (unsigned)crc);
    }
    /* beyond the end, and a piece too long */
    {
        uint8_t d[6];
        gl_put_u32(&d[0], 61440u);
        gl_put_u16(&d[4], 1);
        GL_CHECK_EQ(st_(GL_CMD_CAM_DATA, d, 6), GL_ERR_PARAM);
        gl_put_u32(&d[0], 61000u);
        gl_put_u16(&d[4], 441);
        GL_CHECK_EQ(st_(GL_CMD_CAM_DATA, d, 6), GL_ERR_PARAM);
        gl_put_u32(&d[0], 0u);
        gl_put_u16(&d[4], 1001);
        GL_CHECK_EQ(st_(GL_CMD_CAM_DATA, d, 6), GL_ERR_PARAM);
        gl_put_u16(&d[4], 0);
        GL_CHECK_EQ(st_(GL_CMD_CAM_DATA, d, 6), GL_ERR_PARAM);
    }
    /* half a frame in one exposure: the largest window */
    req[0] = 0;
    gl_put_u16(&req[4], 240);
    gl_put_u16(&req[8], 240);
    n = cmd_(GL_CMD_CAM_CAPTURE, req, 10, &pl);
    GL_CHECK_EQ(pl[0], GL_OK);
    GL_CHECK_EQ(gl_get_u32(&pl[11]), 153600u);
    gl_put_u16(&req[8], 290); /* 185600 pixels: more than the image memory */
    GL_CHECK_EQ(st_(GL_CMD_CAM_CAPTURE, req, 10), GL_ERR_PARAM);

    /* DARK FRAMES: the left camera has a light leak, the right one has none */
    cam_scene_.mode = 1;
    for (cam = 0; cam < 2; cam++) {
        req[0] = cam;
        req[1] = GL_CAPTURE_DARK;
        gl_put_u16(&req[4], 96);
        gl_put_u16(&req[8], 288);
        n = cmd_(GL_CMD_CAM_CAPTURE, req, 10, &pl);
        GL_CHECK_EQ(pl[0], GL_OK);
        GL_CHECK_EQ(pl[2], GL_CAPTURE_DARK);
        GL_CHECK_EQ(pl[15], 3);                                 /* darkest */
        GL_CHECK_EQ(pl[16], (cam == 0) ? 90 : 3);               /* brightest */
        GL_CHECK_EQ(gl_get_u32(&pl[19]), (cam == 0) ? 72u : 0u);/* bright pixels: the leak */
        printf("    dark frame of the %s camera (640 x 288): mean %.2f, max %u, %u pixels above "
               "%u\n", (cam == 0) ? "left" : "right", (double)gl_get_u16(&pl[17]) / 16.0, pl[16],
               (unsigned)gl_get_u32(&pl[19]), GL_PROTO_DARK_BRIGHT_LEVEL);
    }
    GL_CHECK(!gl_sim_cam_rail_on() && cam_pins_parked_());
    GL_CHECK_EQ(gl_sim_clock(), GL_CLOCK_SLOW);

    /* E13 holds for the factory too: no camera from a cell above 60 C */
    gl_sim_set_cell_temperature(62.0f);
    gl_sim_imu_set_temperature(62.0f);
    gl_sim_set_mcu_temperature(62.0f);
    {
        const uint32_t cycles = gl_sim_stats()->cam_rail_cycles;
        cam = 0;
        GL_CHECK_EQ(st_(GL_CMD_CAM_ID, &cam, 1), GL_ERR_STATE);
        GL_CHECK_EQ(st_(GL_CMD_CAM_CAPTURE, req, 10), GL_ERR_STATE);
        GL_CHECK_EQ(st_(GL_CMD_CAM_FIELD, &cam, 1), GL_ERR_STATE);
        GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, cycles);
    }
    no_violation_();
}

/* TEST GATE 2: bars at +13.0 and -13.0 degrees; the brightness of the rows
 * that image them. */
/* Phase-3 review, factory finding 9: "CAM_CAPTURE of a narrow window at the
 * right edge writes inconsistent sensor registers and answers IO" - widths 4
 * and 8 at every x0 from 604 to 632, each with a cycle of the camera rail
 * and a simulator rule violation.  The sensor's start register cannot hold
 * a start column beyond 600; such a window is now moved inward, as one that
 * overhangs the edge always was, and the answer says where it lies. */
GL_TEST(test_narrow_window_at_the_right_edge)
{
    static const uint16_t widths[5] = { 4, 8, 36, 40, 96 };
    const uint8_t *pl;
    uint8_t req[10];
    unsigned ok = 0, tried = 0, moved = 0;

    docked_(true);
    for (size_t wi = 0; wi < GL_ARRAY_LEN(widths); wi++) {
        for (uint16_t x0 = 596; x0 <= 636; x0 = (uint16_t)(x0 + 4u)) {
            const uint16_t w = widths[wi];
            const unsigned want = (x0 + w > 640u) ? (640u - w) : x0;
            const unsigned expect = (want > 600u) ? 600u : want;
            int n;
            req[0] = (uint8_t)(tried & 1u);
            req[1] = GL_CAPTURE_NORMAL;
            gl_put_u16(&req[2], x0);
            gl_put_u16(&req[4], 200);
            gl_put_u16(&req[6], w);
            gl_put_u16(&req[8], 2);
            n = cmd_(GL_CMD_CAM_CAPTURE, req, 10, &pl);
            tried++;
            GL_CHECK_EQ(n, 1 + (int)GL_PROTO_CAPTURE_LEN);
            GL_CHECK_EQ(pl[0], GL_OK);
            if (n == 1 + (int)GL_PROTO_CAPTURE_LEN && pl[0] == GL_OK) {
                ok++;
                GL_CHECK_EQ(gl_get_u16(&pl[3]), expect); /* where the window really lies */
                GL_CHECK_EQ(gl_get_u16(&pl[7]), w);
                moved += (expect != x0) ? 1u : 0u;
            }
            GL_CHECK(!gl_sim_cam_rail_on() && cam_pins_parked_());
            run_talking_until_ms_(now_ms_() + 50u);
        }
    }
    printf("    %u windows of 4 to 96 pixels with x0 596 .. 636: %u answered OK (before the fix "
           "widths 4 and 8 from x0 604 answered IO), %u of them moved inward and reported so; "
           "simulator rule violations %u\n", tried, ok, moved, gl_sim_violation_total());
    GL_CHECK_EQ(ok, tried);
    GL_CHECK(moved >= 16u);
    no_violation_();
}

GL_TEST(test_camera_field_gate_2)
{
    const uint8_t *pl;
    uint8_t cam;
    int n;
    /* where the nominal camera images +-13.0 degrees straight ahead */
    const double f = (double)GL_CFG_CAM_F_PX, cy = 239.5;
    const uint16_t row_up = (uint16_t)floor(cy - f * tan(13.0 * PI_D / 180.0) + 0.5);
    const uint16_t row_lo = (uint16_t)floor(cy + f * tan(13.0 * PI_D / 180.0) + 0.5);

    docked_(true);
    gl_sim_cam_set_scene(factory_scene_, NULL);
    cam_scene_.mode = 2;
    cam_scene_.row_up = row_up;
    cam_scene_.row_lo = row_lo;
    /* a good unit: both bars equally bright */
    cam_scene_.upper = 180.0f;
    cam_scene_.lower = 180.0f;
    for (cam = 0; cam < 2; cam++) {
        n = cmd_(GL_CMD_CAM_FIELD, &cam, 1, &pl);
        GL_CHECK_EQ(n, 1 + (int)GL_PROTO_FIELD_LEN);
        GL_CHECK_EQ(pl[0], GL_OK);
        GL_CHECK_EQ(pl[1], cam);
        GL_CHECK_EQ(gl_get_u16(&pl[3]), row_up);
        GL_CHECK_EQ(gl_get_u16(&pl[5]), row_lo);
        GL_CHECK_EQ(gl_get_u16(&pl[7]), 180u * 16u);
        GL_CHECK_EQ(gl_get_u16(&pl[9]), 180u * 16u);
        GL_CHECK_EQ(gl_get_u16(&pl[11]), 20u * 16u); /* the centre row: background */
        GL_CHECK_EQ(gl_get_u16(&pl[13]), 1000u);
    }
    /* adhesive at the roof edge: the upper bar 25 % darker in the left camera */
    cam_scene_.upper = 135.0f;
    cam = 0;
    n = cmd_(GL_CMD_CAM_FIELD, &cam, 1, &pl);
    GL_CHECK_EQ(pl[0], GL_OK);
    GL_CHECK_EQ(gl_get_u16(&pl[13]), 750u);
    printf("    gate 2 (nominal calibration): +13.0 deg is row %u, -13.0 deg is row %u; equal "
           "bars give ratio 1.000, an upper bar 25 %% darker gives %.3f (proposed limit of the "
           "assembly sequence: not below 0.900)\n", row_up, row_lo,
           (double)gl_get_u16(&pl[13]) / 1000.0);
    /* the rows follow the camera's CALIBRATION: a camera pitched up 1 degree
     * images both bars 11.5 rows lower */
    app.cal_cam[0].pitch_up_rad = (float)(PI_D / 180.0);
    n = cmd_(GL_CMD_CAM_FIELD, &cam, 1, &pl);
    GL_CHECK_EQ(pl[0], GL_OK);
    GL_CHECK_NEAR(gl_get_u16(&pl[3]), (double)row_up + f * (tan(14.0 * PI_D / 180.0) - tan(13.0 * PI_D / 180.0)) , 1.6);
    GL_CHECK(gl_get_u16(&pl[3]) > row_up + 9u);
    app.cal_cam[0].pitch_up_rad = 0.0f;
    GL_CHECK(!gl_sim_cam_rail_on() && cam_pins_parked_());
    no_violation_();
}

/* ======================================================================= */
/* 3. display: test patterns and the rotation of E12                        */
/* ======================================================================= */

/* Direction of the line drawn in a frame buffer that holds nothing but a
 * line: least squares x = a + b y over the centroid of every row that has
 * black pixels.  Returns atan(b): + = the line leans to the LEFT going up
 * the screen, i.e. it is turned counter-clockwise for the viewer.
 * *x_centre receives the line's x at the middle row (y = 63.5). */
static double line_angle_(const gl_gfx_t *g, double *x_centre, unsigned *rows_used)
{
    double sy = 0, sx = 0, syy = 0, sxy = 0;
    unsigned n = 0;
    /* the 96 middle rows: there the round aperture is 80 pixels wide or
     * more, so that it does not cut one side of a line that passes up to 30
     * pixels from the centre (a cut row would pull the centroid inward) */
    for (int y = 16; y < 112; y++) {
        double sum = 0;
        unsigned cnt = 0;
        for (int x = 0; x < GL_GFX_W; x++) {
            if (!gl_gfx_get(g, x, y)) { /* (gl_gfx_get: true = white) */
                sum += x;
                cnt++;
            }
        }
        if (cnt != 0u) {
            const double cx = sum / cnt;
            sy += y;
            sx += cx;
            syy += (double)y * y;
            sxy += (double)y * cx;
            n++;
        }
    }
    {
        const double b = ((double)n * sxy - sy * sx) / ((double)n * syy - sy * sy);
        const double a = (sx - b * sy) / (double)n;
        *x_centre = a + b * 63.5;
        *rows_used = n;
        /* y grows DOWN the screen: going up (y smaller) a line with b > 0
         * moves to smaller x, to the left */
        return atan(b);
    }
}

GL_TEST(test_display_test_patterns)
{
    static const struct {
        uint8_t pattern;
        unsigned black;
        const char *name;
    } pat[] = {
        { GL_DISP_PATTERN_WHITE, 0, "white" },
        { GL_DISP_PATTERN_BLACK, 16384, "black" },
        { GL_DISP_PATTERN_CHECKER_1, 8192, "1-pixel chequer" },
        { GL_DISP_PATTERN_CHECKER_8, 8192, "8-pixel chequer" },
        { GL_DISP_PATTERN_ROWS, 8192, "rows" },
        { GL_DISP_PATTERN_COLUMNS, 8192, "columns" },
    };
    const uint8_t *pl;
    uint8_t req[2];
    int n;

    docked_(true);
    for (size_t i = 0; i < GL_ARRAY_LEN(pat); i++) {
        req[0] = pat[i].pattern;
        req[1] = 20;
        n = cmd_(GL_CMD_DISPLAY_TEST, req, 2, &pl);
        GL_CHECK_EQ(n, 8);
        GL_CHECK_EQ(pl[0], GL_OK);
        GL_CHECK_EQ(pl[1], pat[i].pattern);
        GL_CHECK_EQ(gl_get_u16(&pl[6]), pat[i].black);
        run_until_ms_(now_ms_() + 50u);
        /* the panel shows exactly the frame buffer, whose CRC the answer carried */
        GL_CHECK(gl_sim_lcd()->disp);
        GL_CHECK_EQ(panel_differs_from_framebuffer_(), 0u);
        GL_CHECK_EQ(gl_crc32(app.gfx.px, sizeof(app.gfx.px)), gl_get_u32(&pl[2]));
        GL_CHECK_EQ(gl_gfx_count_black(&app.gfx), pat[i].black);
        /* the WHOLE panel, corners included (the ordinary screen is clipped to the aperture) */
        if (pat[i].pattern == GL_DISP_PATTERN_BLACK) {
            GL_CHECK(panel_black_(0, 0) && panel_black_(127, 0) && panel_black_(0, 127) &&
                     panel_black_(127, 127));
        }
        if (pat[i].pattern == GL_DISP_PATTERN_ROWS) {
            GL_CHECK(panel_black_(5, 0) && !panel_black_(5, 1) && panel_black_(99, 126) &&
                     !panel_black_(99, 127));
        }
        if (pat[i].pattern == GL_DISP_PATTERN_COLUMNS) {
            GL_CHECK(panel_black_(0, 7) && !panel_black_(1, 7) && panel_black_(126, 90) &&
                     !panel_black_(127, 90));
        }
        if (pat[i].pattern == GL_DISP_PATTERN_CHECKER_1) {
            GL_CHECK(!panel_black_(0, 0) && panel_black_(1, 0) && panel_black_(0, 1) &&
                     !panel_black_(1, 1));
        }
    }
    /* the orientation pattern is not symmetric: its mirror images differ */
    req[0] = GL_DISP_PATTERN_ORIENT;
    n = cmd_(GL_CMD_DISPLAY_TEST, req, 2, &pl);
    GL_CHECK_EQ(pl[0], GL_OK);
    run_until_ms_(now_ms_() + 50u);
    {
        unsigned lr = 0, ud = 0;
        for (int y = 0; y < 128; y++) {
            for (int x = 0; x < 128; x++) {
                lr += (panel_black_(x, y) != panel_black_(127 - x, y));
                ud += (panel_black_(x, y) != panel_black_(x, 127 - y));
            }
        }
        GL_CHECK(lr > 20u && ud > 20u);
        printf("    orientation pattern: %u pixels differ from its left-right mirror image, %u "
               "from its top-bottom one\n", lr, ud);
    }
    /* a pattern keeps the marker awake in the cradle for its hold time and
     * no longer; then the ordinary screen is back */
    req[0] = GL_DISP_PATTERN_BLACK;
    req[1] = 40;
    {
        const uint32_t t0 = now_ms_();
        (void)cmd_(GL_CMD_DISPLAY_TEST, req, 2, &pl);
        run_until_ms_(t0 + 39000u);
        GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_USB);
        GL_CHECK_EQ(gl_gfx_count_black(&app.gfx), 16384u);
        run_until_ms_(t0 + 41000u);
        GL_CHECK_EQ(app.fac.pattern, 0);
        GL_CHECK(gl_gfx_count_black(&app.gfx) < 6000u); /* the cradle screen */
        GL_CHECK_EQ(panel_differs_from_framebuffer_(), 0u);
    }
    /* pattern 0 ends a test at once; lifting the marker out does too */
    req[0] = GL_DISP_PATTERN_BLACK;
    req[1] = 100;
    (void)cmd_(GL_CMD_DISPLAY_TEST, req, 2, &pl);
    req[0] = GL_DISP_PATTERN_NORMAL;
    req[1] = 0;
    GL_CHECK_EQ(st_(GL_CMD_DISPLAY_TEST, req, 2), GL_OK);
    run_until_ms_(now_ms_() + 50u);
    GL_CHECK(gl_gfx_count_black(&app.gfx) < 6000u);
    req[0] = GL_DISP_PATTERN_BLACK;
    req[1] = 100;
    (void)cmd_(GL_CMD_DISPLAY_TEST, req, 2, &pl);
    undock_();
    run_until_ms_(now_ms_() + 300u);
    GL_CHECK_EQ(app.fac.pattern, 0);
    no_violation_();
}

/* E12: the stored display rotation turns the drawn line.  A stored +1.2
 * degrees must turn it by 1.2 degrees counter-clockwise (to the viewer's
 * left at the top of the screen), within the display's quantisation.
 *
 * THE QUANTISATION.  The panel has 128 pixels of 0.18 mm; one pixel over the
 * 96 rows the angle is measured on is 0.60 degrees.  The lines are drawn
 * with edge dithering and measured by a least-squares fit over the row
 * centroids, which resolves much less than that: the checks below allow
 * 0.1 degree, and the largest deviation this test has printed is 0.07. */
GL_TEST(test_display_rotation_from_pixels)
{
    const double deg = PI_D / 180.0;
    const uint8_t *pl;
    uint8_t req[5];
    double a_raw, a_cor, a_neg, xc_raw, xc_cor, xc;
    unsigned rows;
    int n;

    docked_(true);
    /* the reference line as the factory camera sees it before anything is stored */
    req[0] = GL_DISP_PATTERN_REF_RAW;
    req[1] = 30;
    GL_CHECK_EQ(st_(GL_CMD_DISPLAY_TEST, req, 2), GL_OK);
    run_until_ms_(now_ms_() + 50u);
    GL_CHECK_EQ(panel_differs_from_framebuffer_(), 0u);
    a_raw = line_angle_(&app.gfx, &xc_raw, &rows);
    GL_CHECK_EQ(rows, 96u);                 /* in every row that was looked at */
    GL_CHECK_NEAR(a_raw, 0.0, 0.02 * deg);  /* straight along the forward axis */
    GL_CHECK_NEAR(xc_raw, 63.5, 0.05);      /* through the screen centre */

    /* nothing stored yet */
    n = cmd_(GL_CMD_DISPLAY_ROT, "\0", 1, &pl);
    GL_CHECK_EQ(n, 6);
    GL_CHECK_NEAR(gl_get_f32(&pl[1]), 0.0, 0.0);
    GL_CHECK_EQ(pl[5], 0);
    /* write +1.2 degrees */
    unlock_();
    req[0] = 1;
    gl_put_f32(&req[1], (float)(1.2 * deg));
    n = cmd_(GL_CMD_DISPLAY_ROT, req, 5, &pl);
    GL_CHECK_EQ(pl[0], GL_OK);
    GL_CHECK_NEAR(gl_get_f32(&pl[1]), 1.2 * deg, 1e-8);
    GL_CHECK_EQ(pl[5], 1);
    GL_CHECK(app.cal_dev.flags & GL_CAL_DEV_FLAG_DISPLAY_ROT);
    /* the corrected reference line: turned by +1.2 degrees, still through the centre */
    req[0] = GL_DISP_PATTERN_REF_CORRECTED;
    req[1] = 30;
    GL_CHECK_EQ(st_(GL_CMD_DISPLAY_TEST, req, 2), GL_OK);
    run_until_ms_(now_ms_() + 50u);
    GL_CHECK_EQ(panel_differs_from_framebuffer_(), 0u);
    a_cor = line_angle_(&app.gfx, &xc_cor, &rows);
    printf("    reference line from the frame buffer: uncorrected %+.3f deg, with +1.200 deg "
           "stored %+.3f deg (turned %+.3f deg counter-clockwise; x at the centre row %.2f and "
           "%.2f)\n", a_raw / deg, a_cor / deg, (a_cor - a_raw) / deg, xc_raw, xc_cor);
    GL_CHECK(a_cor > a_raw);                           /* the stated direction */
    GL_CHECK_NEAR(a_cor - a_raw, 1.2 * deg, 0.1 * deg); /* the stated size */
    GL_CHECK_NEAR(xc_cor, 63.5, 0.1);
    /* the raw pattern stays raw (the factory measures the glass with it) */
    req[0] = GL_DISP_PATTERN_REF_RAW;
    GL_CHECK_EQ(st_(GL_CMD_DISPLAY_TEST, req, 2), GL_OK);
    run_until_ms_(now_ms_() + 50u);
    GL_CHECK_NEAR(line_angle_(&app.gfx, &xc, &rows), a_raw, 1e-9);
    req[0] = GL_DISP_PATTERN_NORMAL;
    req[1] = 0;
    (void)st_(GL_CMD_DISPLAY_TEST, req, 2);

    /* THE AIM LINE.  (a) The drawing primitive: the line of an aim of -3
     * degrees through the ball position, alone in a frame buffer, without
     * and with the rotation applied to both of its directions. */
    {
        static gl_gfx_t g0, g1, g2;
        gl_gfx_aim_info_t info;
        const float aim = (float)(-3.0 * deg), r = (float)(1.2 * deg);
        double x0c, x1c, x2c, a0, a1, a2;
        gl_gfx_init(&g0);
        gl_gfx_init(&g1);
        gl_gfx_init(&g2);
        gl_gfx_clear(&g0, GL_INK_WHITE);
        gl_gfx_clear(&g1, GL_INK_WHITE);
        gl_gfx_clear(&g2, GL_INK_WHITE);
        gl_gfx_aim_line_styled(&g0, aim, 0.0f, 3.0f, false, &info);
        GL_CHECK(info.on_screen);
        gl_gfx_aim_line_styled(&g1, aim + r, r, 3.0f, false, &info);
        GL_CHECK(info.on_screen);
        gl_gfx_aim_line_styled(&g2, aim - r, -r, 3.0f, false, &info);
        a0 = line_angle_(&g0, &x0c, &rows);
        a1 = line_angle_(&g1, &x1c, &rows);
        a2 = line_angle_(&g2, &x2c, &rows);
        a_neg = a2 - a0;
        printf("    aim line of -3.000 deg from the frame buffer: drawn at %+.3f deg; with +1.2 "
               "deg stored %+.3f deg (turned %+.3f); with -1.2 deg stored %+.3f deg (turned "
               "%+.3f); distance of the line from the screen centre %.2f, %.2f, %.2f px\n",
               a0 / deg, a1 / deg, (a1 - a0) / deg, a2 / deg, a_neg / deg,
               (x0c - 63.5) * cos(a0), (x1c - 63.5) * cos(a1), (x2c - 63.5) * cos(a2));
        GL_CHECK_NEAR(a0, -3.0 * deg, 0.1 * deg);
        GL_CHECK(a1 > a0 && a2 < a0);
        GL_CHECK_NEAR(a1 - a0, 1.2 * deg, 0.1 * deg);
        GL_CHECK_NEAR(a_neg, -1.2 * deg, 0.1 * deg);
        /* a rotation about the screen centre: the line stays as far from it */
        GL_CHECK_NEAR((x1c - 63.5) * cos(a1), (x0c - 63.5) * cos(a0), 0.15);
        GL_CHECK_NEAR((x2c - 63.5) * cos(a2), (x0c - 63.5) * cos(a0), 0.15);
    }
    /* (b) The result screen: a real read, then the renderer with the view
     * as composed (stored rotation +1.2 degrees) against the same view with
     * the rotation written into the aim and the ball direction by hand.
     * Pixel for pixel the same; and different from the unrotated screen. */
    undock_();
    world_defaults_();
    W.t_pick_s = (double)now_ms_() / 1000.0 + 0.5;
    W.t_place_s = W.t_pick_s + 0.6;
    project_scene_();
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, now_ms_() + 12000u));
    run_until_ms_(now_ms_() + 50u);
    GL_CHECK(app.view.have_result);
    GL_CHECK_NEAR(app.view.display_rot_rad, 1.2 * deg, 1e-8); /* the composed view carries it */
    GL_CHECK_EQ(panel_differs_from_framebuffer_(), 0u);
    {
        static gl_gfx_t ga, gb, gc;
        gl_ui_view_t v = app.view;
        unsigned d_ab = 0, d_ac = 0;
        gl_gfx_init(&ga);
        gl_gfx_init(&gb);
        gl_gfx_init(&gc);
        gl_ui_render(&app.ui, &v, &ga);            /* as shown */
        v.display_rot_rad = 0.0f;
        gl_ui_render(&app.ui, &v, &gc);            /* without the rotation */
        v.aim_rad += (float)(1.2 * deg);
        v.ball_az_rad += (float)(1.2 * deg);
        gl_ui_render(&app.ui, &v, &gb);            /* turned by hand */
        for (size_t i = 0; i < sizeof(ga.px); i++) {
            d_ab += (ga.px[i] != gb.px[i]);
            d_ac += (ga.px[i] != gc.px[i]);
        }
        GL_CHECK_EQ(memcmp(ga.px, app.gfx.px, sizeof(ga.px)), 0); /* this IS the screen */
        GL_CHECK_EQ(d_ab, 0u);
        GL_CHECK(d_ac > 10u);
        printf("    result screen of a real read with +1.2 deg stored: identical to the screen "
               "with aim and ball direction turned by hand (0 bytes differ), %u bytes differ from "
               "the unrotated screen\n", d_ac);
    }
    /* the stored value survives a reset (flash kept) */
    run_until_ms_(now_ms_() + 60000u);
    gl_sim_mcu_reset(GL_RESET_SOFTWARE);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    GL_CHECK_NEAR(app.cal_dev.display_rot_rad, 1.2 * deg, 1e-8);
    no_violation_();
}

/* ======================================================================= */
/* 4. grain LEDs and the photodiode                                         */
/* ======================================================================= */

GL_TEST(test_grain_leds_and_dark_offset)
{
    gl_sim_grain_t g;
    const uint8_t *pl;
    uint8_t mode;
    int n;

    docked_(true);
    memset(&g, 0, sizeof(g));
    g.dark_counts = 8200.0f; /* mid-rail bias */
    g.noise_counts = 2.0f;
    for (int i = 0; i < 16; i++) {
        g.response[i] = 1500.0f + 40.0f * (float)i;
    }
    g.response[5] = 0.0f;    /* LED 5 is missing (or reversed) */
    gl_sim_grain_set(&g);
    /* the bare-board test of step 11a: dark offset only, no LED is lit */
    mode = GL_GRAIN_MODE_DARK;
    n = cmd_(GL_CMD_GRAIN_TEST, &mode, 1, &pl);
    GL_CHECK_EQ(n, 1 + (int)GL_PROTO_GRAIN_LEN);
    GL_CHECK_EQ(pl[0], GL_OK);
    GL_CHECK_EQ(pl[2], GL_ERR_EMPTY); /* no LED cycle was run */
    GL_CHECK_NEAR(gl_get_u16(&pl[3]), 8200.0, 3.0);
    GL_CHECK((unsigned)(gl_get_u16(&pl[7]) - gl_get_u16(&pl[5])) < 12u); /* max - min: the noise */
    GL_CHECK_EQ(gl_get_u16(&pl[9]), GL_HAL_ADC_FULL_SCALE);
    GL_CHECK_EQ(gl_get_u16(&pl[11]), 0); /* nothing stored */
    GL_CHECK_EQ(gl_sim_grain_lit_mask(), 0u);
    printf("    photodiode dark offset: mean %u counts of %u, spread %u (16 readings)\n",
           gl_get_u16(&pl[3]), gl_get_u16(&pl[9]), gl_get_u16(&pl[7]) - gl_get_u16(&pl[5]));
    /* a leaky input shows as an offset */
    g.dark_counts = 11000.0f;
    gl_sim_grain_set(&g);
    (void)cmd_(GL_CMD_GRAIN_TEST, &mode, 1, &pl);
    GL_CHECK_NEAR(gl_get_u16(&pl[3]), 11000.0, 3.0);
    g.dark_counts = 8200.0f;
    gl_sim_grain_set(&g);
    /* one cycle of all 16 LEDs: the dead one is seen */
    mode = GL_GRAIN_MODE_CYCLE;
    n = cmd_(GL_CMD_GRAIN_TEST, &mode, 1, &pl);
    GL_CHECK_EQ(pl[0], GL_OK);
    GL_CHECK_EQ(pl[2], GL_OK);
    {
        unsigned dead = 0;
        for (unsigned i = 0; i < 16u; i++) {
            const unsigned d1 = gl_get_u16(&pl[13 + 6 * i]), on = gl_get_u16(&pl[15 + 6 * i]),
                           d2 = gl_get_u16(&pl[17 + 6 * i]);
            GL_CHECK_NEAR(d1, 8200.0, 8.0);
            GL_CHECK_NEAR(d2, 8200.0, 8.0);
            if (i == 5u) {
                GL_CHECK_NEAR(on, 8200.0, 8.0);
                dead++;
            } else {
                GL_CHECK_NEAR((double)on - 0.5 * (d1 + d2), 1500.0 + 40.0 * i, 12.0);
            }
        }
        GL_CHECK_EQ(dead, 1u);
    }
    GL_CHECK_EQ(gl_sim_grain_lit_mask(), 0u); /* all off afterwards */
    /* STORE: guarded; records the dark offset in the grain record */
    mode = GL_GRAIN_MODE_STORE;
    GL_CHECK_EQ(st_(GL_CMD_GRAIN_TEST, &mode, 1), GL_ERR_STATE);
    unlock_();
    n = cmd_(GL_CMD_GRAIN_TEST, &mode, 1, &pl);
    GL_CHECK_EQ(pl[0], GL_OK);
    GL_CHECK_NEAR(gl_get_u16(&pl[11]), 8200.0, 3.0);
    GL_CHECK(app.cal_grain.flags & GL_CAL_GRAIN_FLAG_DARK_OFFSET);
    GL_CHECK_NEAR(app.cal_grain.pd_dark_counts, 8200.0, 3.0);
    {
        const uint8_t *d;
        size_t len = 0;
        gl_cal_grain_t stored;
        GL_CHECK_EQ(gl_store_get(&app.store, GL_STORE_ID_CAL_GRAIN, &d, &len), GL_OK);
        GL_CHECK_EQ(len, GL_CAL_GRAIN_BLOB_LEN);
        GL_CHECK_EQ(gl_cal_grain_decode(d, len, &stored), GL_OK);
        GL_CHECK_EQ(stored.pd_dark_counts, app.cal_grain.pd_dark_counts);
    }
    no_violation_();
}

/* ======================================================================= */
/* 5. the level zero, armed over USB, run on the seat plate (E11)           */
/* ======================================================================= */

/* Lift the marker off the contacts, put it on the plate (0.5 s from now, at
 * rest 0.6 s later), let the armed zeroing take its first read, turn the
 * marker by `turn_deg` and wait for the zeroing to end.  Returns the state
 * of the armed zeroing afterwards. */
static uint8_t zero_placed_(double turn_deg);

static uint8_t zero_on_the_plate_(double turn_deg)
{
    undock_();
    return zero_placed_(turn_deg);
}

/* the same without the lifting off the contacts (the marker is out already) */
static uint8_t zero_placed_(double turn_deg)
{
    double t_now;
    W.turn_len_s = 0.0;
    W.t_pick_s = (double)now_ms_() / 1000.0 + 0.5;
    W.t_place_s = W.t_pick_s + 0.6;
    GL_CHECK(run_until_state_(GL_UI_CAL_ZERO, now_ms_() + 6000u));
    GL_CHECK(app.zero.active && app.zero.armed);
    t_now = (double)gl_sim_now_us() * 1e-6;
    while (app.zero.active && app.zero.step == 0u && (double)gl_sim_now_us() * 1e-6 < t_now + 5.0) {
        run_until_ms_(now_ms_() + 10u);
    }
    GL_CHECK_EQ(app.zero.step, 1);
    t_now = (double)gl_sim_now_us() * 1e-6;
    W.turn_at_s = t_now + 0.4;
    W.turn_len_s = 1.5;
    W.turn_rad = turn_deg * PI_D / 180.0;
    t_now = (double)gl_sim_now_us() * 1e-6;
    while (app.ui.state == (uint8_t)GL_UI_CAL_ZERO && (double)gl_sim_now_us() * 1e-6 < t_now + 10.0) {
        run_until_ms_(now_ms_() + 10u);
    }
    return app.fac.zero.state;
}

GL_TEST(test_level_zero_armed_on_two_seats)
{
    /* what the IMU reads wrong on each seat: on the BASE face 3.5 / -2.5
     * mrad; on the ball feet 1.2 / -0.8 mrad more (the two planes differ by
     * up to 1.6 mrad, DESIGN_SPEC E11) */
    static const float bias_base[3] = { 0.0035f, -0.0025f, 0.0f };
    static const float bias_ball[3] = { 0.0047f, -0.0033f, 0.0f };
    static const float gyro_bias[3] = { 0.004f, -0.002f, 0.001f };
    const uint8_t arm_base[2] = { GL_ZERO_OP_ARM, GL_CAL_SEAT_BASE };
    const uint8_t arm_ball[2] = { GL_ZERO_OP_ARM, GL_CAL_SEAT_BALL };
    const uint8_t status[2] = { GL_ZERO_OP_STATUS, 0 };
    const uint8_t cancel[2] = { GL_ZERO_OP_CANCEL, 0 };
    const uint8_t *pl;
    int n;

    docked_(true);
    W.stick = false;
    W.slope_x = 0.004; /* the surface plate under the seat plate is not level */
    W.slope_y = -0.007;
    /* arm, look, cancel */
    unlock_();
    n = cmd_(GL_CMD_LEVEL_ZERO, arm_base, 2, &pl);
    GL_CHECK_EQ(n, 1 + (int)GL_PROTO_ZERO_LEN);
    GL_CHECK_EQ(pl[0], GL_OK);
    GL_CHECK_EQ(pl[1], GL_ZERO_STATE_ARMED);
    GL_CHECK_EQ(pl[2], GL_CAL_SEAT_BASE);
    (void)cmd_(GL_CMD_LEVEL_ZERO, cancel, 2, &pl);
    GL_CHECK_EQ(pl[1], GL_ZERO_STATE_IDLE);
    /* armed, the marker stays in the cradle: nothing runs there */
    (void)cmd_(GL_CMD_LEVEL_ZERO, arm_base, 2, &pl);
    run_talking_until_ms_(now_ms_() + 5000u);
    GL_CHECK_EQ(app.ui.state, GL_UI_CRADLE_USB);
    GL_CHECK_EQ(app.fac.zero.state, GL_ZERO_STATE_ARMED);
    GL_CHECK(!app.zero.active);

    /* ---- base-face seat: lifted off the contacts, onto the plate with the
     *      ball pockets, read, turned 180 degrees into the other nest, read ---- */
    gl_sim_imu_set_errors(0.0008f, 0.002f, bias_base, gyro_bias);
    GL_CHECK_EQ(zero_on_the_plate_(180.0), GL_ZERO_STATE_DONE);
    print_seen_();
    GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, 0u); /* no camera read got in before it */
    GL_CHECK_EQ(app.cal_tilt.flags, GL_CAL_TILT_FLAG_BASE);
    GL_CHECK_NEAR(app.cal_tilt.base_bias_x, 0.0035, 0.0004);
    GL_CHECK_NEAR(app.cal_tilt.base_bias_y, -0.0025, 0.0004);
    GL_CHECK_NEAR(app.cal_tilt.base_temp_c, 22.0, 0.1);
    /* docked again: the result and its scatter are there to be fetched */
    run_until_ms_(now_ms_() + 3000u);
    dock_();
    n = cmd_(GL_CMD_LEVEL_ZERO, status, 2, &pl);
    GL_CHECK_EQ(pl[0], GL_OK);
    GL_CHECK_EQ(pl[1], GL_ZERO_STATE_DONE);
    GL_CHECK_EQ(pl[2], GL_CAL_SEAT_BASE);
    GL_CHECK_EQ(pl[3], GL_OK);
    GL_CHECK_EQ(pl[4], 1); /* first attempt */
    GL_CHECK_NEAR(gl_get_f32(&pl[5]), app.cal_tilt.base_bias_x, 0.0);
    GL_CHECK_NEAR(gl_get_f32(&pl[9]), app.cal_tilt.base_bias_y, 0.0);
    GL_CHECK(gl_get_f32(&pl[13]) > 0.0f && gl_get_f32(&pl[13]) < 0.0005f); /* scatter */
    GL_CHECK_NEAR(fabsf(gl_get_f32(&pl[17])), PI_D, 0.03);                  /* the turn */
    GL_CHECK_NEAR(gl_get_f32(&pl[21]), 0.004, 0.0004);                      /* the plate itself */
    GL_CHECK_NEAR(gl_get_f32(&pl[25]), -0.007, 0.0004);
    GL_CHECK_NEAR(gl_get_f32(&pl[29]), 22.0, 0.1);
    printf("    BASE-FACE zero, armed over USB and run on the plate: (%.3f, %.3f) mrad, true "
           "(3.500, -2.500); scatter %.3f mrad; turn %.1f deg; plate slope found (%.2f, %.2f) "
           "mrad, true (4.00, -7.00)\n", 1000.0 * (double)gl_get_f32(&pl[5]),
           1000.0 * (double)gl_get_f32(&pl[9]), 1000.0 * (double)gl_get_f32(&pl[13]),
           (double)gl_get_f32(&pl[17]) * 180.0 / PI_D, 1000.0 * (double)gl_get_f32(&pl[21]),
           1000.0 * (double)gl_get_f32(&pl[25]));

    /* ---- ball seat ---- */
    unlock_();
    (void)cmd_(GL_CMD_LEVEL_ZERO, arm_ball, 2, &pl);
    GL_CHECK_EQ(pl[1], GL_ZERO_STATE_ARMED);
    gl_sim_imu_set_errors(0.0008f, 0.002f, bias_ball, gyro_bias);
    GL_CHECK_EQ(zero_on_the_plate_(-176.0), GL_ZERO_STATE_DONE);
    GL_CHECK_EQ(app.cal_tilt.flags, GL_CAL_TILT_FLAG_BASE | GL_CAL_TILT_FLAG_FLIP);
    GL_CHECK_NEAR(app.cal_tilt.flip_bias_x, 0.0047, 0.0004);
    GL_CHECK_NEAR(app.cal_tilt.flip_bias_y, -0.0033, 0.0004);
    GL_CHECK_NEAR(app.cal_tilt.base_bias_x, 0.0035, 0.0004); /* untouched */
    printf("    BALL-seat zero: (%.3f, %.3f) mrad, true (4.700, -3.300); the two seats differ by "
           "(%.3f, %.3f) mrad, true (1.200, -0.800)\n", 1000.0 * (double)app.cal_tilt.flip_bias_x,
           1000.0 * (double)app.cal_tilt.flip_bias_y,
           1000.0 * (double)(app.cal_tilt.flip_bias_x - app.cal_tilt.base_bias_x),
           1000.0 * (double)(app.cal_tilt.flip_bias_y - app.cal_tilt.base_bias_y));
    GL_CHECK_NEAR(app.cal_tilt.flip_bias_x - app.cal_tilt.base_bias_x, 0.0012, 0.0003);
    /* both are in the flash store, in a version-2 record */
    {
        const uint8_t *d;
        size_t len = 0;
        gl_cal_tilt_t stored;
        GL_CHECK_EQ(gl_store_get(&app.store, GL_STORE_ID_CAL_TILT, &d, &len), GL_OK);
        GL_CHECK_EQ(len, GL_CAL_TILT_BLOB_LEN);
        GL_CHECK_EQ(gl_cal_tilt_decode(d, len, &stored), GL_OK);
        GL_CHECK(stored.base_bias_x == app.cal_tilt.base_bias_x &&
                 stored.flip_bias_y == app.cal_tilt.flip_bias_y &&
                 stored.flags == app.cal_tilt.flags && stored.base_scatter > 0.0f);
    }

    /* ---- which zero a read uses.  On turf the marker rests on its base
     *      face: the IMU is wrong by bias_base there.  The default (TURF)
     *      removes the base-face zero and finds the true slope ---- */
    run_until_ms_(now_ms_() + 60000u);
    GL_CHECK_EQ(app.ui.state, GL_UI_SLEEP);
    gl_sim_imu_set_errors(0.0008f, 0.002f, bias_base, gyro_bias);
    world_defaults_(); /* the green: slope (1.2, -2.0) %, a flagstick at 6 m */
    W.t_pick_s = (double)now_ms_() / 1000.0 + 0.5;
    W.t_place_s = W.t_pick_s + 0.6;
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, now_ms_() + 12000u));
    GL_CHECK_EQ(app.settings.surface, GL_SURFACE_TURF);
    GL_CHECK_EQ(app.seat_used, GL_CAL_SEAT_BASE);
    GL_CHECK_NEAR(app.cur.slope.x, app.cur.slope_raw.x - app.cal_tilt.base_bias_x, 1e-9);
    GL_CHECK_NEAR(app.cur.slope.y, app.cur.slope_raw.y - app.cal_tilt.base_bias_y, 1e-9);
    printf("    read on turf (SURFACE = TURF, the default): slope used (%.3f, %.3f) mrad, true "
           "(12.000, -20.000)\n", 1000.0 * (double)app.cur.slope.x, 1000.0 * (double)app.cur.slope.y);
    GL_CHECK_NEAR(app.cur.slope.x, 0.012, 0.0005);
    GL_CHECK_NEAR(app.cur.slope.y, -0.020, 0.0005);
    /* SURFACE = HARD selects the ball-seat zero */
    run_until_ms_(now_ms_() + 60000u);
    {
        gl_settings_t s = app.settings;
        s.surface = (uint8_t)GL_SURFACE_HARD;
        GL_CHECK_EQ(gl_app_set_settings(&app, &s), GL_OK);
    }
    gl_sim_imu_set_errors(0.0008f, 0.002f, bias_ball, gyro_bias);
    W.t_pick_s = (double)now_ms_() / 1000.0 + 0.5;
    W.t_place_s = W.t_pick_s + 0.6;
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, now_ms_() + 12000u));
    GL_CHECK_EQ(app.seat_used, GL_CAL_SEAT_BALL);
    GL_CHECK_NEAR(app.cur.slope.x, app.cur.slope_raw.x - app.cal_tilt.flip_bias_x, 1e-9);
    GL_CHECK_NEAR(app.cur.slope.x, 0.012, 0.0005);
    GL_CHECK_NEAR(app.cur.slope.y, -0.020, 0.0005);

    /* ---- a zeroing that goes wrong: a quarter turn instead of a half turn.
     *      Three attempts, then it gives up; nothing is stored ---- */
    run_until_ms_(now_ms_() + 60000u);
    dock_();
    unlock_();
    (void)cmd_(GL_CMD_LEVEL_ZERO, arm_base, 2, &pl);
    {
        const gl_cal_tilt_t before = app.cal_tilt;
        W.stick = false;
        GL_CHECK_EQ(zero_on_the_plate_(90.0), GL_ZERO_STATE_ARMED); /* will try again */
        GL_CHECK_EQ(app.fac.zero.status, GL_ERR_RANGE);
        GL_CHECK_EQ(app.fac.zero.attempts, 1);
        GL_CHECK_EQ(memcmp(&before, &app.cal_tilt, sizeof(before)), 0);
        dock_();
        (void)cmd_(GL_CMD_LEVEL_ZERO, status, 2, &pl);
        GL_CHECK_EQ(pl[1], GL_ZERO_STATE_ARMED);
        GL_CHECK_EQ(pl[3], GL_ERR_RANGE);
        (void)cmd_(GL_CMD_LEVEL_ZERO, cancel, 2, &pl);
        GL_CHECK_EQ(pl[1], GL_ZERO_STATE_IDLE);
    }
    no_violation_();
}

static float face_g_[3];
static void face_imu_(void *ctx, uint64_t t_us, float a[3], float g[3])
{
    (void)ctx;
    (void)t_us;
    /* an IMU with an offset and a scale error per axis */
    a[0] = 1.004f * face_g_[0] + 0.012f;
    a[1] = 0.997f * face_g_[1] - 0.007f;
    a[2] = 1.002f * face_g_[2] + 0.020f;
    g[0] = g[1] = g[2] = 0.0f;
}

/* Phase-3 review, factory finding 3: assembly step 19 rests the marker at
 * least 30 minutes OFF THE PADS before the zeros (six-face on USB,
 * disconnect, rest, zero with nothing on the pads).  The arming lasted ten
 * minutes: "rest 900 s and 1800 s: state FAILED, status 3 (TIMEOUT)".  And
 * the base-face zero - the default of every read - can only be taken this
 * way.  The arming now lasts 60 minutes; ARM can carry the rest, and the
 * zeroing then does not start before the marker has been off VBUS that long;
 * the result carries NTC2 (the soak rule of step 19 is on that sensor) and
 * how long the marker had rested. */
GL_TEST(test_level_zero_after_the_30_minute_rest)
{
    static const float bias_base[3] = { 0.0035f, -0.0025f, 0.0f };
    static const float gyro_bias[3] = { 0.004f, -0.002f, 0.001f };
    const uint8_t arm_plain[2] = { GL_ZERO_OP_ARM, GL_CAL_SEAT_BASE };
    const uint8_t arm_rest[3] = { GL_ZERO_OP_ARM, GL_CAL_SEAT_BASE, 30 };
    const uint8_t status[2] = { GL_ZERO_OP_STATUS, 0 };
    const uint8_t *pl;
    uint32_t t_off;
    int n;

    /* (a) the reviewer's sequence: armed, undocked, 1800 s of rest, then onto the plate */
    docked_(true);
    W.stick = false;
    gl_sim_imu_set_errors(0.0008f, 0.002f, bias_base, gyro_bias);
    unlock_();
    (void)cmd_(GL_CMD_LEVEL_ZERO, arm_plain, 2, &pl);
    GL_CHECK_EQ(pl[1], GL_ZERO_STATE_ARMED);
    undock_();
    run_until_ms_(now_ms_() + 1800u * 1000u);
    GL_CHECK_EQ(app.fac.zero.state, GL_ZERO_STATE_ARMED); /* (FAILED / TIMEOUT before the fix) */
    GL_CHECK_EQ(zero_placed_(180.0), GL_ZERO_STATE_DONE);
    GL_CHECK_EQ(app.fac.zero.attempts, 1);
    GL_CHECK(app.cal_tilt.flags & GL_CAL_TILT_FLAG_BASE);
    GL_CHECK_NEAR(app.cal_tilt.base_bias_x, 0.0035, 0.0004);
    printf("    armed, undocked, 1800 s of rest, onto the plate: state DONE, attempts %u, bias "
           "(%.3f, %.3f) mrad (before the fix: FAILED, status TIMEOUT, attempts 0)\n",
           (unsigned)app.fac.zero.attempts, 1000.0 * (double)app.cal_tilt.base_bias_x,
           1000.0 * (double)app.cal_tilt.base_bias_y);

    /* (b) ARM with a rest of 30 minutes: a placement BEFORE the rest is over
     * is not the zeroing (an ordinary placement; the arming stays), the
     * placement after it is */
    docked_(true);
    W.stick = false;
    gl_sim_imu_set_errors(0.0008f, 0.002f, bias_base, gyro_bias);
    gl_sim_imu_set_temperature(23.5f);
    unlock_();
    n = cmd_(GL_CMD_LEVEL_ZERO, arm_rest, 3, &pl);
    GL_CHECK_EQ(n, 1 + (int)GL_PROTO_ZERO_LEN);
    GL_CHECK_EQ(pl[1], GL_ZERO_STATE_ARMED);
    GL_CHECK_EQ(pl[39], 30); /* the rest asked for */
    undock_();
    t_off = now_ms_();
    run_until_ms_(t_off + 5u * 60000u);
    W.t_pick_s = (double)now_ms_() / 1000.0 + 0.5;
    W.t_place_s = W.t_pick_s + 0.6;
    run_until_ms_(now_ms_() + 8000u);
    GL_CHECK(!app.zero.active);
    GL_CHECK_EQ(app.fac.zero.state, GL_ZERO_STATE_ARMED);
    GL_CHECK_EQ(app.fac.zero.attempts, 0);
    GL_CHECK(!(app.cal_tilt.flags & GL_CAL_TILT_FLAG_BASE));
    (void)run_until_state_(GL_UI_SLEEP, now_ms_() + 70000u);
    run_until_ms_(t_off + 31u * 60000u);
    GL_CHECK_EQ(app.fac.zero.state, GL_ZERO_STATE_ARMED);
    GL_CHECK_EQ(zero_placed_(180.0), GL_ZERO_STATE_DONE);
    GL_CHECK(app.cal_tilt.flags & GL_CAL_TILT_FLAG_BASE);
    run_until_ms_(now_ms_() + 3000u);
    dock_();
    n = cmd_(GL_CMD_LEVEL_ZERO, status, 2, &pl);
    GL_CHECK_EQ(pl[1], GL_ZERO_STATE_DONE);
    GL_CHECK_NEAR((double)(int16_t)gl_get_u16(&pl[37]), 235.0, 3.0); /* NTC2 at the zeroing, 0.1 C */
    GL_CHECK_NEAR(gl_get_f32(&pl[29]), 23.5, 0.1);                   /* the IMU's, as before */
    GL_CHECK_EQ(pl[39], 30);
    GL_CHECK(pl[40] >= 30u && pl[40] <= 33u);                         /* minutes it had rested */
    printf("    ARM with 30 min of rest: placed after 5 min -> not zeroed, still armed; placed "
           "after %u min -> DONE; result carries NTC2 %.1f C and IMU %.1f C\n", (unsigned)pl[40],
           0.1 * (double)(int16_t)gl_get_u16(&pl[37]), (double)gl_get_f32(&pl[29]));

    /* (c) the arming does end: 60 minutes (plus the rest) without a zeroing */
    unlock_();
    (void)cmd_(GL_CMD_LEVEL_ZERO, arm_plain, 2, &pl);
    undock_();
    run_until_ms_(now_ms_() + GL_FACTORY_ZERO_ARM_TIMEOUT_MS - 120000u);
    GL_CHECK_EQ(app.fac.zero.state, GL_ZERO_STATE_ARMED);
    run_until_ms_(now_ms_() + 240000u);
    GL_CHECK_EQ(app.fac.zero.state, GL_ZERO_STATE_FAILED);
    GL_CHECK_EQ(app.fac.zero.status, GL_ERR_TIMEOUT);
    no_violation_();
}

/* Phase-3 review, factory finding 2: step 19 measures the reference line
 * with the marker on a seat plate against the fence, a camera above, "no
 * contacts on either plate".  A display test ended at once when the marker
 * left the cradle ("100 ms after undocking the state is SLEEP ... the
 * pattern is gone").  A pattern can now be ARMED for the seat plate: it is
 * shown in the cradle as before, and shown again when the marker is next
 * put down out of the cradle - instead of a read, for the hold time, with
 * nothing on the pads. */
GL_TEST(test_reference_line_on_the_seat_plate)
{
    const double deg = PI_D / 180.0;
    const uint8_t armed[3] = { GL_DISP_PATTERN_REF_RAW, 60, 1 };
    const uint8_t plain[2] = { GL_DISP_PATTERN_REF_RAW, 60 };
    const uint8_t *pl;
    double a_cradle, a_plate, xc;
    unsigned rows, black;
    uint32_t t_shown, crc;
    int n;

    docked_(true);
    W.stick = false;
    /* locked: an armed pattern is refused, a plain one is not */
    GL_CHECK_EQ(st_(GL_CMD_DISPLAY_TEST, armed, 3), GL_ERR_STATE);
    GL_CHECK(!app.fac.plate_armed);
    /* the reviewer's measurement, unchanged: a plain pattern ends at the undocking */
    GL_CHECK_EQ(st_(GL_CMD_DISPLAY_TEST, plain, 2), GL_OK);
    run_until_ms_(now_ms_() + 50u);
    undock_();
    GL_CHECK_EQ(app.ui.state, GL_UI_SLEEP);
    GL_CHECK_EQ(app.fac.pattern, GL_DISP_PATTERN_NORMAL);
    W.t_pick_s = (double)now_ms_() / 1000.0 + 20.5;
    W.t_place_s = W.t_pick_s + 0.6;
    run_until_ms_(now_ms_() + 20000u);
    dock_();
    /* armed */
    unlock_();
    n = cmd_(GL_CMD_DISPLAY_TEST, armed, 3, &pl);
    GL_CHECK_EQ(n, 8);
    GL_CHECK_EQ(pl[0], GL_OK);
    crc = gl_get_u32(&pl[2]);
    black = gl_get_u16(&pl[6]);
    run_until_ms_(now_ms_() + 50u);
    GL_CHECK_EQ(panel_differs_from_framebuffer_(), 0u);
    a_cradle = line_angle_(&app.gfx, &xc, &rows);
    GL_CHECK_EQ(rows, 96u);
    undock_();
    GL_CHECK_EQ(app.ui.state, GL_UI_SLEEP); /* asleep on the way to the plate, display off */
    GL_CHECK(!gl_sim_lcd()->disp);
    GL_CHECK(app.fac.plate_armed && !app.fac.plate_showing);
    run_until_ms_(now_ms_() + 40000u); /* carried over, 40 s */
    W.t_pick_s = (double)now_ms_() / 1000.0 + 0.5;
    W.t_place_s = W.t_pick_s + 0.6;
    {
        const uint32_t t0 = now_ms_();
        while (!app.fac.plate_showing && now_ms_() < t0 + 6000u) {
            run_until_ms_(now_ms_() + 10u);
        }
    }
    GL_CHECK(app.fac.plate_showing);
    t_shown = now_ms_();
    run_until_ms_(now_ms_() + 100u);
    /* on the plate: the SAME frame the cradle showed, on the panel, display on */
    GL_CHECK(gl_sim_lcd()->disp);
    GL_CHECK_EQ(panel_differs_from_framebuffer_(), 0u);
    GL_CHECK_EQ(gl_crc32(app.gfx.px, sizeof(app.gfx.px)), crc);
    GL_CHECK_EQ(gl_gfx_count_black(&app.gfx), black);
    a_plate = line_angle_(&app.gfx, &xc, &rows);
    GL_CHECK_EQ(rows, 96u);
    GL_CHECK_NEAR(a_plate, a_cradle, 1e-9);
    GL_CHECK_NEAR(xc, 63.5, 0.05);
    /* held: 30 s and 55 s later it is still there, no read has started, no
     * camera was powered, nothing was put on the pads */
    run_until_ms_(t_shown + 30000u);
    GL_CHECK(app.fac.plate_showing && gl_sim_lcd()->disp);
    GL_CHECK_EQ(app.ui.state, GL_UI_WAIT_STILL);
    run_until_ms_(t_shown + 55000u);
    GL_CHECK(app.fac.plate_showing);
    GL_CHECK_EQ(gl_crc32(app.gfx.px, sizeof(app.gfx.px)), crc);
    GL_CHECK_EQ(panel_differs_from_framebuffer_(), 0u);
    GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, 0u);
    GL_CHECK_EQ(app.reads_total, 0u);
    GL_CHECK(!app.power.vbus && !app.usb_on);
    /* ... and after the hold: asleep, display off, disarmed */
    run_until_ms_(t_shown + 61500u);
    GL_CHECK_EQ(app.ui.state, GL_UI_SLEEP);
    GL_CHECK(!gl_sim_lcd()->disp && !app.fac.plate_showing && !app.fac.plate_armed);
    GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, 0u);
    GL_CHECK_EQ(app.fac.plate_shown, 1u);
    printf("    reference line armed for the seat plate: shown %.1f s after the marker was put "
           "down out of the cradle, the frame of the cradle (CRC %08lx, %u black pixels, line "
           "at %+.3f deg), held 60 s with no camera read, then asleep\n",
           ((double)t_shown - 1000.0 * W.t_place_s) / 1000.0, (unsigned long)crc, black,
           a_plate / deg);
    /* the next placement is an ordinary one again (no flagstick here: the
     * cameras do run) */
    W.t_pick_s = (double)now_ms_() / 1000.0 + 0.5;
    W.t_place_s = W.t_pick_s + 0.6;
    run_until_ms_(now_ms_() + 9000u);
    GL_CHECK_EQ(app.fac.plate_shown, 1u);
    GL_CHECK(gl_sim_stats()->cam_rail_cycles >= 1u);
    /* docking ends a pattern that is being shown; "normal" cancels an arming */
    (void)run_until_state_(GL_UI_SLEEP, now_ms_() + 70000u);
    dock_();
    unlock_();
    GL_CHECK_EQ(st_(GL_CMD_DISPLAY_TEST, armed, 3), GL_OK);
    GL_CHECK(app.fac.plate_armed);
    GL_CHECK_EQ(st_(GL_CMD_DISPLAY_TEST, "\0\0", 2), GL_OK);
    GL_CHECK(!app.fac.plate_armed);
    GL_CHECK_EQ(st_(GL_CMD_DISPLAY_TEST, armed, 3), GL_OK);
    undock_();
    W.t_pick_s = (double)now_ms_() / 1000.0 + 0.5;
    W.t_place_s = W.t_pick_s + 0.6;
    {
        const uint32_t t0 = now_ms_();
        while (!app.fac.plate_showing && now_ms_() < t0 + 6000u) {
            run_until_ms_(now_ms_() + 10u);
        }
    }
    GL_CHECK(app.fac.plate_showing);
    dock_();
    run_until_ms_(now_ms_() + 200u);
    GL_CHECK(!app.fac.plate_showing && !app.fac.plate_armed);
    GL_CHECK_EQ(app.fac.pattern, GL_DISP_PATTERN_NORMAL);
    no_violation_();
}

/* Phase-3 review, factory findings 10 and 11 (seeds S09, S12): a store that
 * REFUSES - a flash that does not program - must leave every calibration
 * value as it was, in RAM and in the store's own RAM copy, for every command
 * that writes one; and the "calibration complete" flag of GET_IDENT, on
 * which the final test relies, needs every flag. */
GL_TEST(test_a_refused_store_changes_nothing)
{
    static const float face[6][3] = { { 1, 0, 0 }, { -1, 0, 0 }, { 0, 1, 0 },
                                      { 0, -1, 0 }, { 0, 0, 1 }, { 0, 0, -1 } };
    const uint8_t solve[2] = { GL_CALPROC_SIX_FACE, 6 };
    const uint8_t white[2] = { GL_CALPROC_GRAIN_WHITE, 0 };
    const uint8_t *pl, *d;
    uint8_t req[1 + 200];
    gl_cal_tilt_t tilt0;
    gl_cal_cam_t cam0, c;
    gl_cal_grain_t grain0;
    gl_cal_device_t dev0;
    size_t len;
    unsigned refused = 0;
    int n;

    docked_(true);
    memcpy(face_g_, face[4], sizeof(face_g_));
    gl_sim_imu_set_motion(face_imu_, NULL);
    gl_sim_imu_set_errors(0.0008f, 0.002f, NULL, NULL);
    unlock_();
    for (unsigned f = 0; f < 6u; f++) {
        const uint8_t step[2] = { GL_CALPROC_SIX_FACE, (uint8_t)f };
        uint32_t t0;
        memcpy(face_g_, face[f], sizeof(face_g_));
        run_talking_until_ms_(now_ms_() + 1500u);
        GL_CHECK_EQ(st_(GL_CMD_START_CAL, step, 2), GL_OK);
        t0 = now_ms_();
        do {
            run_until_ms_(now_ms_() + 200u);
            (void)cmd_(GL_CMD_CAL_STATUS, NULL, 0, &pl);
        } while (pl[2] != 0u && now_ms_() < t0 + 5000u);
    }
    GL_CHECK_EQ(app.six.done_mask, 0x3Fu);
    tilt0 = app.cal_tilt;
    cam0 = app.cal_cam[GL_CAM_LEFT];
    grain0 = app.cal_grain;
    dev0 = app.cal_dev;

    gl_sim_flash_fail_programs(true);
    /* six-face solve (before the fix: status 10, but "RAM tilt flags are 0x01
     * and offset_g is (0.0120, -0.0070, 0.0200) ... and the six captured
     * faces are discarded") */
    n = (int)st_(GL_CMD_START_CAL, solve, 2);
    GL_CHECK(n != GL_OK);
    refused += (n != GL_OK) ? 1u : 0u;
    GL_CHECK_EQ(memcmp(&tilt0, &app.cal_tilt, sizeof(tilt0)), 0);
    GL_CHECK_EQ(app.six.done_mask, 0x3Fu); /* the faces are kept: solve again */
    (void)cmd_(GL_CMD_GET_IDENT, NULL, 0, &pl);
    GL_CHECK_EQ(pl[0], GL_OK);
    printf("    flash that does not program: six-face solve answers %d, RAM tilt flags 0x%02X, "
           "offset (%.4f, %.4f, %.4f), faces kept 0x%02X\n", n, (unsigned)app.cal_tilt.flags,
           (double)app.cal_tilt.offset_g[0], (double)app.cal_tilt.offset_g[1],
           (double)app.cal_tilt.offset_g[2], (unsigned)app.six.done_mask);
    /* grain white reference */
    n = (int)st_(GL_CMD_START_CAL, white, 2);
    GL_CHECK(n != GL_OK);
    refused += (n != GL_OK) ? 1u : 0u;
    GL_CHECK_EQ(memcmp(&grain0, &app.cal_grain, sizeof(grain0)), 0);
    /* SET_CAL (seed S09: the RAM copy kept although the store refused) */
    gl_cal_cam_defaults(&c, 0);
    c.fx_px = 700.0f;
    req[0] = (uint8_t)GL_CAL_ID_CAM_L;
    gl_cal_cam_encode(&c, &req[1]);
    n = (int)st_(GL_CMD_SET_CAL, req, 1u + GL_CAL_CAM_BLOB_LEN);
    GL_CHECK(n != GL_OK);
    refused += (n != GL_OK) ? 1u : 0u;
    GL_CHECK_EQ(memcmp(&cam0, &app.cal_cam[GL_CAM_LEFT], sizeof(cam0)), 0);
    GL_CHECK_NEAR(app.read.model[GL_CAM_LEFT].fx, cam0.fx_px, 1e-6);
    /* ... and the store's own RAM copy does not hold the refused value
     * either (a sector change-over would have written it to flash later) */
    GL_CHECK_EQ(gl_store_get(&app.store, (uint8_t)GL_STORE_ID_CAL_CAM_L, &d, &len), GL_ERR_NOT_FOUND);
    /* display rotation, serial, camera horizon, grain floor */
    req[0] = 1;
    gl_put_f32(&req[1], 0.01f);
    n = (int)st_(GL_CMD_DISPLAY_ROT, req, 5);
    GL_CHECK(n != GL_OK);
    refused += (n != GL_OK) ? 1u : 0u;
    n = (int)st_(GL_CMD_SERIAL, "SNUM", 4);
    GL_CHECK(n != GL_OK);
    refused += (n != GL_OK) ? 1u : 0u;
    GL_CHECK_EQ(memcmp(&dev0, &app.cal_dev, sizeof(dev0)), 0);
    req[0] = 0;
    gl_put_f32(&req[1], 247.25f);
    gl_put_f32(&req[5], 0.0f);
    n = (int)st_(GL_CMD_SET_CAM_HORIZON, req, 9);
    GL_CHECK(n != GL_OK);
    refused += (n != GL_OK) ? 1u : 0u;
    GL_CHECK_EQ(memcmp(&cam0, &app.cal_cam[GL_CAM_LEFT], sizeof(cam0)), 0);
    req[0] = 20;
    for (int i = 0; i < 20; i++) {
        gl_put_f32(&req[1 + 4 * i], 0.02f + 0.002f * (float)i);
    }
    n = (int)st_(GL_CMD_SET_GRAIN_FLOOR, req, 1 + 4 * 20);
    GL_CHECK(n != GL_OK);
    refused += (n != GL_OK) ? 1u : 0u;
    GL_CHECK_EQ(memcmp(&grain0, &app.cal_grain, sizeof(grain0)), 0);
    GL_CHECK(gl_sim_flash_stats()->programs_dropped >= 7u);
    gl_sim_flash_fail_programs(false);

    /* the flash works again: the SAME six faces solve and are stored */
    GL_CHECK_EQ(st_(GL_CMD_START_CAL, solve, 2), GL_OK);
    GL_CHECK(app.cal_tilt.flags & GL_CAL_TILT_FLAG_FACTORY);
    GL_CHECK_NEAR(app.cal_tilt.offset_g[0], 0.012, 0.0005);
    GL_CHECK_EQ(app.six.done_mask, 0u);
    printf("    %u writing commands refused with the flash not programming: tilt, camera, grain "
           "and device records unchanged in RAM, nothing in the store; with the flash back the "
           "kept faces solve: offset (%.4f, %.4f, %.4f)\n", refused, (double)app.cal_tilt.offset_g[0],
           (double)app.cal_tilt.offset_g[1], (double)app.cal_tilt.offset_g[2]);
    /* nothing of what was refused comes back after a reset */
    gl_sim_mcu_reset(GL_RESET_SOFTWARE);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    GL_CHECK_NEAR(app.cal_cam[GL_CAM_LEFT].fx_px, cam0.fx_px, 1e-6);
    GL_CHECK_EQ(app.cal_dev.flags, dev0.flags);
    GL_CHECK(app.cal_tilt.flags & GL_CAL_TILT_FLAG_FACTORY);

    /* ---- seed S12: "calibration complete" needs EVERY flag ---- */
    run_until_ms_(now_ms_() + 500u);
    host_rx_len_ = 0;
    {
        gl_cal_tilt_t t = app.cal_tilt;
        gl_cal_cam_t cl = app.cal_cam[GL_CAM_LEFT], cr = app.cal_cam[GL_CAM_RIGHT];
        gl_cal_grain_t g = app.cal_grain;
        gl_cal_device_t dv = app.cal_dev;
        unsigned missing_seen = 0;
        t.flags = GL_CAL_TILT_FLAG_FACTORY | GL_CAL_TILT_FLAG_FLIP | GL_CAL_TILT_FLAG_BASE |
                  GL_CAL_TILT_FLAG_TEMPCO;
        cl.flags = GL_CAL_CAM_FLAG_ALL;
        cr.flags = GL_CAL_CAM_FLAG_ALL;
        g.flags = GL_CAL_GRAIN_FLAG_WHITE_REF;
        dv.flags = GL_CAL_DEV_FLAG_ALL;
        app.cal_tilt = t;
        app.cal_cam[GL_CAM_LEFT] = cl;
        app.cal_cam[GL_CAM_RIGHT] = cr;
        app.cal_grain = g;
        app.cal_dev = dv;
        (void)cmd_(GL_CMD_GET_IDENT, NULL, 0, &pl);
        GL_CHECK(pl[50] & GL_PROTO_IDENT_CAL_COMPLETE); /* all there: complete */
        for (unsigned k = 0; k < 12u; k++) {
            app.cal_tilt = t;
            app.cal_cam[GL_CAM_LEFT] = cl;
            app.cal_cam[GL_CAM_RIGHT] = cr;
            app.cal_grain = g;
            app.cal_dev = dv;
            switch (k) {
            case 0: app.cal_tilt.flags &= (uint8_t)~GL_CAL_TILT_FLAG_FACTORY; break;
            case 1: app.cal_tilt.flags &= (uint8_t)~GL_CAL_TILT_FLAG_FLIP; break;
            case 2: app.cal_tilt.flags &= (uint8_t)~GL_CAL_TILT_FLAG_BASE; break;
            case 3: app.cal_tilt.flags &= (uint8_t)~GL_CAL_TILT_FLAG_TEMPCO; break;
            case 4: app.cal_cam[GL_CAM_LEFT].flags &= (uint8_t)~GL_CAL_CAM_FLAG_INTRINSICS; break;
            case 5: app.cal_cam[GL_CAM_LEFT].flags &= (uint8_t)~GL_CAL_CAM_FLAG_EXTRINSICS; break;
            case 6: app.cal_cam[GL_CAM_LEFT].flags &= (uint8_t)~GL_CAL_CAM_FLAG_HORIZON; break;
            case 7: app.cal_cam[GL_CAM_RIGHT].flags &= (uint8_t)~GL_CAL_CAM_FLAG_INTRINSICS; break;
            case 8: app.cal_cam[GL_CAM_RIGHT].flags &= (uint8_t)~GL_CAL_CAM_FLAG_EXTRINSICS; break;
            case 9: app.cal_cam[GL_CAM_RIGHT].flags &= (uint8_t)~GL_CAL_CAM_FLAG_HORIZON; break;
            case 10: app.cal_grain.flags &= (uint8_t)~GL_CAL_GRAIN_FLAG_WHITE_REF; break;
            default: app.cal_dev.flags &= (uint8_t)~GL_CAL_DEV_FLAG_DISPLAY_ROT; break;
            }
            (void)cmd_(GL_CMD_GET_IDENT, NULL, 0, &pl);
            GL_CHECK(!(pl[50] & GL_PROTO_IDENT_CAL_COMPLETE));
            missing_seen += (pl[50] & GL_PROTO_IDENT_CAL_COMPLETE) ? 0u : 1u;
        }
        app.cal_tilt = t;
        app.cal_dev = dv;
        app.cal_dev.flags &= (uint8_t)~GL_CAL_DEV_FLAG_SERIAL;
        (void)cmd_(GL_CMD_GET_IDENT, NULL, 0, &pl);
        GL_CHECK(!(pl[50] & GL_PROTO_IDENT_CAL_COMPLETE));
        printf("    GET_IDENT \"calibration complete\": set with every flag, cleared with each of "
               "%u single flags missing (right camera included)\n", missing_seen + 1u);
    }
    no_violation_();
}

/* ======================================================================= */
/* 6. six-face step by step, temperature fit, horizon, floor, serial        */
/* ======================================================================= */

GL_TEST(test_six_face_tempco_horizon_floor_serial)
{
    static const float face[6][3] = { { 1, 0, 0 }, { -1, 0, 0 }, { 0, 1, 0 },
                                      { 0, -1, 0 }, { 0, 0, 1 }, { 0, 0, -1 } };
    const uint8_t *pl;
    uint8_t req[5 + 16 * 16];
    int n;

    docked_(true);
    memcpy(face_g_, face[4], sizeof(face_g_));
    gl_sim_imu_set_motion(face_imu_, NULL);
    gl_sim_imu_set_errors(0.0008f, 0.002f, NULL, NULL);
    unlock_();
    /* ---- six-face, each step from the PC, progress from CAL_STATUS ---- */
    for (unsigned f = 0; f < 6u; f++) {
        uint8_t step[2] = { GL_CALPROC_SIX_FACE, (uint8_t)f };
        uint32_t t0;
        memcpy(face_g_, face[f], sizeof(face_g_));
        run_talking_until_ms_(now_ms_() + 1500u); /* turned into the new attitude, at rest */
        GL_CHECK_EQ(st_(GL_CMD_START_CAL, step, 2), GL_OK);
        (void)cmd_(GL_CMD_CAL_STATUS, NULL, 0, &pl);
        GL_CHECK_EQ(pl[2], 1); /* averaging */
        GL_CHECK_EQ(pl[3], f);
        t0 = now_ms_();
        do {
            run_until_ms_(now_ms_() + 200u);
            n = cmd_(GL_CMD_CAL_STATUS, NULL, 0, &pl);
        } while (pl[2] != 0u && now_ms_() < t0 + 5000u);
        GL_CHECK_EQ(n, 1 + (int)GL_PROTO_SIX_LEN);
        GL_CHECK_EQ(pl[1], (1u << (f + 1u)) - 1u); /* faces captured so far */
        /* the raw mean of this face, as the IMU (with its errors) gave it */
        GL_CHECK_NEAR(gl_get_f32(&pl[5 + 12 * f + 4 * (f / 2u)]),
                      ((f / 2u) == 0u ? 1.004 : (f / 2u) == 1u ? 0.997 : 1.002) * face[f][f / 2u] +
                          ((f / 2u) == 0u ? 0.012 : (f / 2u) == 1u ? -0.007 : 0.020), 0.001);
    }
    {
        const uint8_t solve[2] = { GL_CALPROC_SIX_FACE, 6 };
        GL_CHECK_EQ(st_(GL_CMD_START_CAL, solve, 2), GL_OK);
    }
    GL_CHECK(app.cal_tilt.flags & GL_CAL_TILT_FLAG_FACTORY);
    GL_CHECK_NEAR(app.cal_tilt.offset_g[0], 0.012, 0.0005);
    GL_CHECK_NEAR(app.cal_tilt.offset_g[1], -0.007, 0.0005);
    GL_CHECK_NEAR(app.cal_tilt.offset_g[2], 0.020, 0.0005);
    GL_CHECK_NEAR(app.cal_tilt.m.m[0][0], 1.0 / 1.004, 0.0005);
    (void)cmd_(GL_CMD_CAL_STATUS, NULL, 0, &pl);
    GL_CHECK_EQ(pl[1], 0);                              /* done: the mask is cleared */
    GL_CHECK(pl[4] & GL_CAL_TILT_FLAG_FACTORY);
    printf("    six-face from the PC, one step per face: offset (%.4f, %.4f, %.4f) g, true "
           "(0.0120, -0.0070, 0.0200)\n", (double)app.cal_tilt.offset_g[0],
           (double)app.cal_tilt.offset_g[1], (double)app.cal_tilt.offset_g[2]);

    /* ---- temperature fit from points the PC supplies ----
     * The command stores ONLY the temperature terms, about the record's own
     * t0 (the six-face temperature), and keeps the six-face offsets
     * (phase-3 review, factory finding 1).  The points below are ABSOLUTE
     * offsets b(T) = b0 + b1 (T - 23) + b2 (T - 23)^2; about the record's
     * t0 the same curve has the linear term b1 + 2 b2 (t0 - 23). */
    {
        static const float temps[6] = { -10.0f, 0.0f, 10.0f, 23.0f, 35.0f, 50.0f };
        const double b0[3] = { 0.012, -0.007, 0.020 }, b1[3] = { 2.0e-4, -1.0e-4, 3.0e-4 },
                     b2[3] = { -2.0e-6, 1.0e-6, 4.0e-6 };
        const gl_cal_tilt_t six = app.cal_tilt;
        const double t0 = (double)six.t0_c;
        GL_CHECK_NEAR(t0, 22.0, 0.5); /* the board's temperature at the six-face solve */
        req[0] = 6;
        gl_put_f32(&req[1], 23.0f);
        for (int i = 0; i < 6; i++) {
            const double dt = (double)temps[i] - 23.0;
            gl_put_f32(&req[5 + 16 * i], temps[i]);
            for (int a = 0; a < 3; a++) {
                gl_put_f32(&req[9 + 16 * i + 4 * a], (float)(b0[a] + b1[a] * dt + b2[a] * dt * dt));
            }
        }
        n = cmd_(GL_CMD_TILT_TEMPCO, req, 5 + 16 * 6, &pl);
        GL_CHECK_EQ(n, 45);
        GL_CHECK_EQ(pl[0], GL_OK);
        for (int a = 0; a < 3; a++) {
            const double d0 = t0 - 23.0;
            const double b0_at = b0[a] + b1[a] * d0 + b2[a] * d0 * d0, b1_at = b1[a] + 2.0 * b2[a] * d0;
            GL_CHECK_NEAR(gl_get_f32(&pl[1 + 4 * a]), b0_at, 2e-6);
            GL_CHECK_NEAR(gl_get_f32(&pl[13 + 4 * a]), b1_at, 2e-7);
            GL_CHECK_NEAR(gl_get_f32(&pl[25 + 4 * a]), b2[a], 2e-8);
            GL_CHECK_NEAR(app.cal_tilt.tempco1_g_per_k[a], b1_at, 2e-7);
            GL_CHECK_NEAR(app.cal_tilt.tempco2_g_per_k2[a], b2[a], 2e-8);
            /* THE SIX-FACE OFFSETS ARE KEPT, bit for bit */
            GL_CHECK(app.cal_tilt.offset_g[a] == six.offset_g[a]);
        }
        GL_CHECK(gl_get_f32(&pl[37]) < 2e-6f); /* RMS residual of an exact quadratic */
        GL_CHECK(gl_get_f32(&pl[41]) < 6e-6f); /* ... and the largest single one */
        GL_CHECK(app.cal_tilt.flags & GL_CAL_TILT_FLAG_TEMPCO);
        GL_CHECK(app.cal_tilt.flags & GL_CAL_TILT_FLAG_FACTORY);
        GL_CHECK(app.cal_tilt.t0_c == six.t0_c); /* the record's t0 stays the six-face temperature */
        GL_CHECK_EQ(memcmp(&app.cal_tilt.m, &six.m, sizeof(six.m)), 0);
        printf("    temperature fit of 6 points -10 .. 50 C: b1 (%.2e, %.2e, %.2e) g/K about the "
               "record's t0 %.1f C; RMS residual %.1e g, largest %.1e g; six-face offsets kept\n",
               (double)gl_get_f32(&pl[13]), (double)gl_get_f32(&pl[17]),
               (double)gl_get_f32(&pl[21]), t0, (double)gl_get_f32(&pl[37]),
               (double)gl_get_f32(&pl[41]));
        /* a fit whose coefficients the record does not accept is refused
         * and changes nothing: 0.012 g/K (the record takes 0.01) */
        {
            const gl_cal_tilt_t before = app.cal_tilt;
            for (int i = 0; i < 6; i++) {
                gl_put_f32(&req[9 + 16 * i], (float)(0.012 * ((double)temps[i] - 23.0)));
            }
            GL_CHECK_EQ(st_(GL_CMD_TILT_TEMPCO, req, 5 + 16 * 6), GL_ERR_RANGE);
            GL_CHECK_EQ(memcmp(&before, &app.cal_tilt, sizeof(before)), 0);
        }
        /* THE REVIEWER'S CASE: five points of pure DRIFT, 2e-4 g/K x (T - 23)
         * on x and y, nothing for z - what a 0 / 180 degree pair on a flat at
         * each chamber stop yields.  Before the fix: status 0, the record's
         * offsets became (-1.2e-10, 1.2e-10, 0.0), "the six-face offsets of
         * 12 and 7 mg are gone, FACTORY is still set, and nothing warns". */
        {
            static const float tc[5] = { 0.0f, 12.0f, 23.0f, 34.0f, 45.0f };
            req[0] = 5;
            gl_put_f32(&req[1], 23.0f);
            for (int i = 0; i < 5; i++) {
                const float d = 2.0e-4f * (tc[i] - 23.0f);
                gl_put_f32(&req[5 + 16 * i], tc[i]);
                gl_put_f32(&req[9 + 16 * i], d);
                gl_put_f32(&req[13 + 16 * i], -d);
                gl_put_f32(&req[17 + 16 * i], 0.0f);
            }
            n = cmd_(GL_CMD_TILT_TEMPCO, req, 5 + 16 * 5, &pl);
            GL_CHECK_EQ(n, 45);
            GL_CHECK_EQ(pl[0], GL_OK);
            for (int a = 0; a < 3; a++) {
                GL_CHECK(app.cal_tilt.offset_g[a] == six.offset_g[a]);
            }
            GL_CHECK_NEAR(app.cal_tilt.tempco1_g_per_k[0], 2.0e-4, 2e-7);
            GL_CHECK_NEAR(app.cal_tilt.tempco1_g_per_k[1], -2.0e-4, 2e-7);
            GL_CHECK_NEAR(app.cal_tilt.tempco1_g_per_k[2], 0.0, 2e-7);
            printf("    five points of pure drift (2e-4 g/K, z not measured): status 0, offsets "
                   "still (%.4f, %.4f, %.4f) g (before the fix: (-1.2e-10, 1.2e-10, 0.0)), "
                   "b1 (%.2e, %.2e, %.2e)\n", (double)app.cal_tilt.offset_g[0],
                   (double)app.cal_tilt.offset_g[1], (double)app.cal_tilt.offset_g[2],
                   (double)app.cal_tilt.tempco1_g_per_k[0], (double)app.cal_tilt.tempco1_g_per_k[1],
                   (double)app.cal_tilt.tempco1_g_per_k[2]);
            /* six-face, then the fit, then what a tilt read does with it: a
             * sensor with the six-face errors AND that drift, level, at five
             * temperatures - the corrected gravity is level within 0.1 mg */
            for (int i = 0; i < 5; i++) {
                const float d = 2.0e-4f * (tc[i] - six.t0_c);
                const gl_vec3_t raw = { 0.012f + d, -0.007f - d, 1.002f * 1.0f + 0.020f };
                const gl_vec3_t c = gl_tilt_apply_cal(&app.cal_tilt, raw, tc[i]);
                GL_CHECK_NEAR(c.x, 0.0, 2.5e-4); /* (the six-face solve itself is good to 0.2 mg here) */
                GL_CHECK_NEAR(c.y, 0.0, 2.5e-4);
                GL_CHECK_NEAR(c.z, 1.0, 1e-3);
            }
            {
                /* without the temperature terms the same sensor at 45 C reads 4.6 mrad of slope */
                gl_cal_tilt_t no = app.cal_tilt;
                const float d = 2.0e-4f * (45.0f - six.t0_c);
                const gl_vec3_t raw = { 0.012f + d, -0.007f - d, 1.022f };
                memset(no.tempco1_g_per_k, 0, sizeof(no.tempco1_g_per_k));
                GL_CHECK(fabsf(gl_tilt_apply_cal(&no, raw, 45.0f).x) > 4.0e-3f);
            }
            /* outside the window of gl_provisional.h the terms are not
             * extrapolated: 85 C corrects as 60 C does */
            {
                const gl_vec3_t raw = { 0.02f, 0.0f, 1.0f };
                const gl_vec3_t a60 = gl_tilt_apply_cal(&app.cal_tilt, raw, GL_PROV_TILT_TEMPCO_T_MAX_C);
                const gl_vec3_t a85 = gl_tilt_apply_cal(&app.cal_tilt, raw, 85.0f);
                const gl_vec3_t a50 = gl_tilt_apply_cal(&app.cal_tilt, raw, 50.0f);
                GL_CHECK(a60.x == a85.x && a60.y == a85.y);
                GL_CHECK(fabsf(a60.x - a50.x) > 1.0e-3f);
            }
        }
        /* the host's t0 must be the record's: 5 K off is refused */
        {
            const gl_cal_tilt_t before = app.cal_tilt;
            gl_put_f32(&req[1], six.t0_c + 5.0f);
            GL_CHECK_EQ(st_(GL_CMD_TILT_TEMPCO, req, 5 + 16 * 5), GL_ERR_RANGE);
            GL_CHECK_EQ(memcmp(&before, &app.cal_tilt, sizeof(before)), 0);
            gl_put_f32(&req[1], 23.0f);
        }
        /* a level zero that is already stored, taken 13 K from t0: the new
         * terms would change the correction there by 2.6 mg - refused,
         * nothing changed; taken at t0 it is untouched and the fit is stored */
        {
            gl_cal_tilt_t before;
            app.cal_tilt.flags |= GL_CAL_TILT_FLAG_BASE;
            app.cal_tilt.base_temp_c = six.t0_c + 13.0f;
            memset(app.cal_tilt.tempco1_g_per_k, 0, sizeof(app.cal_tilt.tempco1_g_per_k));
            memset(app.cal_tilt.tempco2_g_per_k2, 0, sizeof(app.cal_tilt.tempco2_g_per_k2));
            before = app.cal_tilt;
            GL_CHECK_EQ(st_(GL_CMD_TILT_TEMPCO, req, 5 + 16 * 5), GL_ERR_STATE);
            GL_CHECK_EQ(memcmp(&before, &app.cal_tilt, sizeof(before)), 0);
            app.cal_tilt.base_temp_c = six.t0_c;
            GL_CHECK_EQ(st_(GL_CMD_TILT_TEMPCO, req, 5 + 16 * 5), GL_OK);
            app.cal_tilt.flags &= (uint8_t)~GL_CAL_TILT_FLAG_BASE;
            GL_CHECK_EQ(gl_app_cal_store(&app, GL_CAL_ID_TILT), GL_OK);
        }
        /* CONDITIONING (factory finding 7).  The reviewer's case - three
         * points over 16 K with 0.2 mg of noise, accepted with a residual
         * of 0 and 3 mg wrong at 0 and 45 C - is refused twice over: three
         * points, and a span under 30 K.  And a point that does not fit
         * shows in the largest residual, which the RMS waters down */
        {
            static const float tc[5] = { 15.0f, 19.0f, 23.0f, 27.0f, 31.0f };
            const gl_cal_tilt_t before = app.cal_tilt;
            for (int i = 0; i < 5; i++) {
                gl_put_f32(&req[5 + 16 * i], tc[i]);
            }
            GL_CHECK_EQ(st_(GL_CMD_TILT_TEMPCO, req, 5 + 16 * 5), GL_ERR_PARAM);
            GL_CHECK_EQ(memcmp(&before, &app.cal_tilt, sizeof(before)), 0);
            req[0] = 6;
            for (int i = 0; i < 6; i++) {
                gl_put_f32(&req[5 + 16 * i], temps[i]);
                gl_put_f32(&req[9 + 16 * i], 2.0e-4f * (temps[i] - 23.0f) + ((i == 2) ? 1.0e-3f : 0.0f));
                gl_put_f32(&req[13 + 16 * i], 0.0f);
                gl_put_f32(&req[17 + 16 * i], 0.0f);
            }
            n = cmd_(GL_CMD_TILT_TEMPCO, req, 5 + 16 * 6, &pl);
            GL_CHECK_EQ(pl[0], GL_OK);
            GL_CHECK(gl_get_f32(&pl[41]) > 5.0e-4f);                         /* the point that is 1 mg out */
            GL_CHECK(gl_get_f32(&pl[41]) > 2.5f * gl_get_f32(&pl[37]));      /* the RMS hides it */
            printf("    one point of six 1 mg out: RMS residual %.2f mg, largest %.2f mg\n",
                   1000.0 * (double)gl_get_f32(&pl[37]), 1000.0 * (double)gl_get_f32(&pl[41]));
        }
    }
    /* ---- CAM_HORIZON ---- */
    req[0] = 1;
    gl_put_f32(&req[1], 247.25f);
    gl_put_f32(&req[5], 0.003f);
    n = cmd_(GL_CMD_SET_CAM_HORIZON, req, 9, &pl);
    GL_CHECK_EQ(n, 5);
    GL_CHECK_EQ(pl[0], GL_OK);
    GL_CHECK_NEAR(gl_get_f32(&pl[1]), atan((247.25 - 239.5) / (double)GL_CFG_CAM_F_PX), 1e-7);
    GL_CHECK(app.cal_cam[1].flags & GL_CAL_CAM_FLAG_HORIZON);
    GL_CHECK_NEAR(app.cal_cam[1].horizon_row, 247.25, 1e-5);
    GL_CHECK_NEAR(app.cal_cam[1].roll_rad, 0.003, 1e-8);
    GL_CHECK_EQ(app.cal_cam[0].flags, 0);
    /* the read's camera model has it at once */
    GL_CHECK_NEAR(gl_cam_base_plane_row(&app.read.model[GL_CAM_RIGHT], 319.5f) -
                      gl_cam_base_plane_row(&app.read.model[GL_CAM_LEFT], 319.5f), 7.75, 0.3);
    /* ---- GRAIN_FLOOR from 50 no-grain readings ---- */
    {
        float sorted[50];
        req[0] = 50;
        for (int i = 0; i < 50; i++) {
            const float m = 0.02f + 0.002f * (float)((i * 37) % 50);
            gl_put_f32(&req[1 + 4 * i], m);
            sorted[(i * 37) % 50] = m;
        }
        n = cmd_(GL_CMD_SET_GRAIN_FLOOR, req, 1 + 4 * 50, &pl);
        GL_CHECK_EQ(n, 9);
        GL_CHECK_EQ(pl[0], GL_OK);
        GL_CHECK_NEAR(gl_get_f32(&pl[1]), 0.5 * ((double)sorted[24] + (double)sorted[25]), 1e-6);
        GL_CHECK_NEAR(gl_get_f32(&pl[5]), sorted[47], 1e-7); /* the 95th percentile */
        GL_CHECK(app.cal_grain.flags & GL_CAL_GRAIN_FLAG_NOISE_FLOOR);
        GL_CHECK_NEAR(app.cal_grain.mod_threshold, sorted[47], 1e-7);
    }
    /* ---- the serial number ---- */
    n = cmd_(GL_CMD_SERIAL, NULL, 0, &pl);
    GL_CHECK_EQ(n, 13);
    GL_CHECK_EQ(pl[12], 0); /* not stored yet */
    n = cmd_(GL_CMD_SERIAL, "SNUM", 4, &pl);
    GL_CHECK_EQ(pl[0], GL_OK);
    GL_CHECK_EQ(pl[12], 1);
    {
        uint8_t uid[12];
        char text[8];
        gl_hal_unique_id(uid);
        gl_cal_serial_text(gl_cal_serial_from_uid(uid), text);
        GL_CHECK_EQ(gl_get_u32(&pl[1]), gl_cal_serial_from_uid(uid));
        GL_CHECK_MEM(&pl[5], text, 7);
        GL_CHECK_MEM(app.cal_dev.unique_id, uid, 12);
        printf("    serial number from the unique number: %s\n", text);
    }
    (void)cmd_(GL_CMD_GET_IDENT, NULL, 0, &pl);
    GL_CHECK_EQ(gl_get_u32(&pl[41]), gl_get_u32(&pl[37]));
    GL_CHECK((pl[50] & GL_PROTO_IDENT_SERIAL_STORED) && (pl[50] & GL_PROTO_IDENT_SERIAL_MATCH));
    GL_CHECK(!(pl[50] & GL_PROTO_IDENT_CAL_COMPLETE)); /* zeros, cameras, rotation are missing */
    /* GET_CAL returns the device record; SET_CAL of it must be self-consistent */
    {
        const uint8_t id = GL_CAL_ID_DEVICE;
        uint8_t set[1 + GL_CAL_DEVICE_BLOB_LEN];
        gl_cal_device_t d;
        n = cmd_(GL_CMD_GET_CAL, &id, 1, &pl);
        GL_CHECK_EQ(n, 2 + (int)GL_CAL_DEVICE_BLOB_LEN);
        GL_CHECK_EQ(gl_cal_device_decode(&pl[2], GL_CAL_DEVICE_BLOB_LEN, &d), GL_OK);
        GL_CHECK(d.flags & GL_CAL_DEV_FLAG_SERIAL);
        set[0] = id;
        memcpy(&set[1], &pl[2], GL_CAL_DEVICE_BLOB_LEN);
        GL_CHECK_EQ(st_(GL_CMD_SET_CAL, set, sizeof(set)), GL_OK);
        set[5] ^= 0x10u; /* a byte changed in transit: the CRC refuses it */
        GL_CHECK_EQ(st_(GL_CMD_SET_CAL, set, sizeof(set)), GL_ERR_CRC);
        GL_CHECK_EQ(st_(GL_CMD_SET_CAL, set, sizeof(set) - 1u), GL_ERR_PARAM);
    }
    /* a calibration record of phase 2 (version 1, 46 bytes) restored from a
     * backup: accepted, and stored as version 2 */
    {
        uint8_t set[1 + GL_CAL_CAM_BLOB_LEN_V1];
        const float f[11] = { 661.0f, 659.0f, 322.0f, 236.5f, -0.05f, 0.0f, -0.004f, 0.002f,
                              -10.0f, 16.6f, 3.2f };
        const uint8_t *d;
        size_t len = 0;
        set[0] = GL_CAL_ID_CAM_L;
        set[1] = 1;
        set[2] = 3;
        for (int i = 0; i < 11; i++) {
            gl_put_f32(&set[3 + 4 * i], f[i]);
        }
        GL_CHECK_EQ(st_(GL_CMD_SET_CAL, set, sizeof(set)), GL_OK);
        GL_CHECK_NEAR(app.cal_cam[0].fx_px, 661.0, 1e-4);
        GL_CHECK_EQ(gl_store_get(&app.store, GL_STORE_ID_CAL_CAM_L, &d, &len), GL_OK);
        GL_CHECK_EQ(len, GL_CAL_CAM_BLOB_LEN);
        GL_CHECK_EQ(d[0], 2);
    }
    /* everything written here survives a reset */
    gl_sim_mcu_reset(GL_RESET_SOFTWARE);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    GL_CHECK(app.cal_tilt.flags & GL_CAL_TILT_FLAG_TEMPCO);
    GL_CHECK(app.cal_cam[1].flags & GL_CAL_CAM_FLAG_HORIZON);
    GL_CHECK(app.cal_grain.flags & GL_CAL_GRAIN_FLAG_NOISE_FLOOR);
    GL_CHECK(app.cal_dev.flags & GL_CAL_DEV_FLAG_SERIAL);
    no_violation_();
}

/* ======================================================================= */
/* 7. the sleep-current test                                                */
/* ======================================================================= */

GL_TEST(test_sleep_current_test_mode)
{
    const uint8_t *pl;
    uint8_t req[3];
    uint32_t t_undock;
    double ua_timer, ua_motion;
    double q0;
    uint64_t t0;
    int n;

    docked_(true);
    unlock_();
    /* ---- wake on the timer only: 40 s, wake-on-motion OFF ---- */
    req[0] = GL_PROTO_WAKE_TIMER;
    gl_put_u16(&req[1], 40);
    n = cmd_(GL_CMD_SLEEP_TEST, req, 3, &pl);
    GL_CHECK_EQ(n, 3);
    GL_CHECK_EQ(pl[0], GL_OK);
    GL_CHECK_EQ(pl[1], 1);
    GL_CHECK_EQ(pl[2], GL_PROTO_WAKE_TIMER | GL_PROTO_WAKE_VBUS); /* VBUS always wakes */
    /* nothing happens while VBUS is there */
    run_talking_until_ms_(now_ms_() + 3000u);
    GL_CHECK(app.awake && !app.fac.sleep_running);
    t_undock = now_ms_();
    undock_(); /* (one pass of the main loop: it ends asleep, 16 s later) */
    GL_CHECK(!app.awake && app.fac.sleep_running);
    GL_CHECK_EQ(app.ui.state, GL_UI_SLEEP);
    GL_CHECK(app.ui.state_since_ms - t_undock < 100u); /* asleep as soon as VBUS has gone */
    GL_CHECK(!gl_sim_lcd()->disp);
    GL_CHECK_EQ(gl_sim_imu_reg(0x10) & 0x0Fu, 0u); /* accelerometer powered down: no wake-on-motion */
    /* the marker is handled during the test: it does NOT wake */
    W.t_pick_s = (double)now_ms_() / 1000.0 + 2.0;
    W.t_place_s = W.t_pick_s + 1.0;
    t0 = gl_sim_now_us();
    q0 = gl_sim_stats()->charge_uas;
    run_until_ms_(t_undock + 38000u);
    GL_CHECK(!app.awake);
    GL_CHECK((double)gl_sim_now_us() * 1e-6 > W.t_place_s); /* (the handling is over) */
    ua_timer = (gl_sim_stats()->charge_uas - q0) / ((double)(gl_sim_now_us() - t0) * 1e-6);
    /* ... and wakes by its timer, 40 s after it went to sleep */
    run_until_ms_(t_undock + 41000u);
    GL_CHECK(app.awake);
    GL_CHECK(!app.fac.sleep_running && !app.fac.sleep_armed);
    GL_CHECK_EQ(app.fac.last_wake, GL_PROTO_WAKE_TIMER);
    GL_CHECK_NEAR(app.fac.last_sleep_ms, 40000.0, 300.0);
    /* docked again, the PC reads what happened */
    run_until_ms_(now_ms_() + 40000u);
    dock_();
    n = cmd_(GL_CMD_GET_SENSORS, NULL, 0, &pl);
    GL_CHECK_EQ(pl[17], GL_PROTO_WAKE_TIMER);
    GL_CHECK_EQ(pl[18], GL_PROTO_WAKE_TIMER | GL_PROTO_WAKE_VBUS);
    GL_CHECK_NEAR(gl_get_u32(&pl[19]), 40000.0, 300.0);

    /* ---- wake on motion, as in the product: the marker sleeps at once
     *      (not after the 20 s it would otherwise wait for a placement) and
     *      wakes when it is picked up ---- */
    unlock_();
    req[0] = GL_PROTO_WAKE_MOTION;
    gl_put_u16(&req[1], 0);
    GL_CHECK_EQ(st_(GL_CMD_SLEEP_TEST, req, 3), GL_OK);
    W.t_pick_s = 1.0e9;
    W.t_place_s = 1.0e9;
    t_undock = now_ms_();
    undock_();
    GL_CHECK(!app.awake && app.fac.sleep_running);
    GL_CHECK((gl_sim_imu_reg(0x10) & 0x0Fu) != 0u); /* accelerometer on, low power */
    t0 = gl_sim_now_us();
    q0 = gl_sim_stats()->charge_uas;
    run_until_ms_(t_undock + 30000u);
    GL_CHECK(!app.awake);
    ua_motion = (gl_sim_stats()->charge_uas - q0) / ((double)(gl_sim_now_us() - t0) * 1e-6);
    W.t_pick_s = (double)now_ms_() / 1000.0 + 1.0;
    W.t_place_s = W.t_pick_s + 0.6;
    run_until_ms_(now_ms_() + 2500u);
    GL_CHECK(app.awake && !app.fac.sleep_running);
    GL_CHECK_EQ(app.fac.last_wake, GL_PROTO_WAKE_MOTION);
    printf("    sleep-current test, supply MODEL (no hardware): wake on motion %.2f uA at the "
           "cell (the product's sleep); wake on the timer only %.2f uA (IMU powered down); "
           "asleep as soon as VBUS has gone\n", ua_motion, ua_timer);
    GL_CHECK_NEAR(ua_motion - ua_timer, GL_SIM_I_IMU_WAKE_UA - GL_SIM_I_IMU_OFF_UA, 0.3);
    /* without VBUS the test cannot be armed (there is no USB then anyway);
     * mask 0 disarms */
    run_until_ms_(now_ms_() + 60000u);
    dock_();
    unlock_();
    req[0] = GL_PROTO_WAKE_TIMER;
    gl_put_u16(&req[1], 5);
    GL_CHECK_EQ(st_(GL_CMD_SLEEP_TEST, req, 3), GL_OK);
    req[0] = 0;
    n = cmd_(GL_CMD_SLEEP_TEST, req, 3, &pl);
    GL_CHECK_EQ(pl[1], 0);
    GL_CHECK(!app.fac.sleep_armed);
    no_violation_();
}

/* ======================================================================= */
/* 8. the field log: replay records, tilt records, download with resume     */
/* ======================================================================= */

static uint8_t dump_[2][24000];
static size_t dump_len_[2];

/* Download the log with LOG_READ into dump_[which]: restart, or continue
 * after a LOG_SEEK.  Returns the number of responses. */
static unsigned log_download_(int which, bool restart)
{
    uint8_t r = restart ? 1u : 0u;
    unsigned responses = 0;
    bool more = true;
    dump_len_[which] = 0;
    while (more && responses < 64u) {
        const uint8_t *pl;
        const int n = cmd_(GL_CMD_LOG_READ, &r, 1, &pl);
        GL_CHECK(n >= 2);
        GL_CHECK_EQ(pl[0], GL_OK);
        if (n < 2 || pl[0] != GL_OK) {
            break;
        }
        more = (pl[1] != 0u);
        if (dump_len_[which] + (size_t)n - 2u <= sizeof(dump_[which])) {
            memcpy(&dump_[which][dump_len_[which]], &pl[2], (size_t)n - 2u);
            dump_len_[which] += (size_t)n - 2u;
        }
        r = 0;
        responses++;
    }
    return responses;
}

/* Find the k-th record of a type in a dump; returns its payload or NULL. */
static const uint8_t *dump_find_(int which, uint8_t type, unsigned k, unsigned *len, uint32_t *seq)
{
    for (size_t pos = 0; pos + 8u <= dump_len_[which];) {
        const unsigned n = gl_get_u16(&dump_[which][pos + 2u]);
        if (dump_[which][pos] == type) {
            if (k == 0u) {
                *len = n;
                *seq = gl_get_u32(&dump_[which][pos + 4u]);
                return &dump_[which][pos + 8u];
            }
            k--;
        }
        pos += 8u + n;
    }
    return NULL;
}

static unsigned dump_count_(int which, uint8_t type)
{
    unsigned k = 0, len;
    uint32_t seq;
    while (dump_find_(which, type, k, &len, &seq) != NULL) {
        k++;
    }
    return k;
}

static void place_(void)
{
    W.t_pick_s = (double)now_ms_() / 1000.0 + 0.5;
    W.t_place_s = W.t_pick_s + 0.6;
}

GL_TEST(test_field_log_records_and_resume)
{
    const uint8_t *p;
    unsigned len = 0;
    uint32_t seq = 0, used0, used1;
    gl_log_stats_t ls;

    /* ---- one Quick Read ---- */
    world_defaults_();
    board_up_(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    watch_reset_();
    GL_CHECK_EQ(gl_log_stats(&app.log, &ls), GL_OK);
    used0 = ls.bytes_used;
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 9000));
    GL_CHECK_EQ(gl_log_stats(&app.log, &ls), GL_OK);
    used1 = ls.bytes_used;
    {
        const gl_measurements_t m = app.meas_cur;
        const gl_estimate_t e = app.est;
        const gl_patch_fit_t fit = app.solver_work.fit;
        const uint16_t read_id = app.read_id;
        /* asleep, docked, downloaded */
        run_until_ms_(now_ms_() + 60000u);
        dock_();
        GL_CHECK_EQ(log_download_(0, true), 2u);
        GL_CHECK_EQ(dump_count_(0, GL_LOG_REC_MEAS), 1u);
        GL_CHECK_EQ(dump_count_(0, GL_LOG_REC_READ), 1u);
        GL_CHECK_EQ(dump_count_(0, GL_LOG_REC_READ2), 1u);
        GL_CHECK_EQ(dump_count_(0, GL_LOG_REC_TILT), 0u); /* the tilt logger is off */
        /* the placement record: every field the estimator was handed */
        p = dump_find_(0, GL_LOG_REC_MEAS, 0, &len, &seq);
        GL_CHECK(p != NULL);
        GL_CHECK_EQ(len, GL_FIELDLOG_MEAS_FIXED + 8u * m.n_horizon);
        GL_CHECK_EQ(gl_get_u16(&p[0]), read_id);
        GL_CHECK_EQ(p[2], 0);
        GL_CHECK_EQ(p[3], 1);
        {
            const unsigned want = GL_FIELDLOG_MEAS_F_BALL | GL_FIELDLOG_MEAS_F_FLAG_FOUND |
                                  (m.flag_base_visible ? GL_FIELDLOG_MEAS_F_BASE_VISIBLE : 0u) |
                                  (m.flag_top_visible ? GL_FIELDLOG_MEAS_F_TOP_VISIBLE : 0u);
            GL_CHECK_EQ(p[4], want);
        }
        GL_CHECK_EQ(p[5], m.tilt_reads);
        GL_CHECK_EQ(p[6], m.n_horizon);
        GL_CHECK_EQ(p[7], GL_FIELDLOG_LAYOUT);
        {
            const float want[15] = { m.f_px, m.baseline_m, m.h_cam_m, m.tilt_x, m.tilt_y,
                                     m.flag_bearing_rad, m.flag_disparity_px, m.flag_low_elev_rad,
                                     m.flag_top_elev_rad, m.stick_height_est_m,
                                     m.stick_height_rel_sigma, m.grain_kappa, m.grain_azimuth_rad,
                                     m.stimp_ft, m.user_distance_m };
            for (int i = 0; i < 15; i++) {
                /* bit for bit (a NaN stays the NaN it was) */
                GL_CHECK_MEM(&p[8 + 4 * i], &want[i], 4);
            }
            for (unsigned i = 0; i < m.n_horizon; i++) {
                GL_CHECK_MEM(&p[68u + 8u * i], &m.horizon_az_rad[i], 4);
                GL_CHECK_MEM(&p[72u + 8u * i], &m.horizon_elev_rad[i], 4);
            }
        }
        /* the read record: context, options, estimate, fit */
        p = dump_find_(0, GL_LOG_REC_READ2, 0, &len, &seq);
        GL_CHECK(p != NULL);
        GL_CHECK_EQ(len, GL_FIELDLOG_READ_LEN);
        GL_CHECK_EQ(p[0], GL_FIELDLOG_LAYOUT);
        GL_CHECK_EQ(p[1], 5);
        GL_CHECK_EQ(gl_get_u16(&p[2]), read_id);
        GL_CHECK_EQ(gl_get_u16(&p[12]), GL_APP_FW_VERSION);
        GL_CHECK_EQ(gl_get_u32(&p[16]), GL_APP_FW_BUILD);
        GL_CHECK_EQ(gl_get_u32(&p[20]), gl_solver_version());
        GL_CHECK_EQ(p[24], GL_CAL_VERSION);
        {
            uint8_t flags[5];
            uint16_t crc[5];
            uint8_t sblob[GL_SETTINGS_BLOB_LEN];
            gl_app_cal_ids(&app, flags, crc);
            GL_CHECK_MEM(&p[25], flags, 5);
            for (int i = 0; i < 5; i++) {
                GL_CHECK_EQ(gl_get_u16(&p[30 + 2 * i]), crc[i]);
            }
            gl_settings_encode(&app.settings, sblob);
            GL_CHECK_MEM(&p[40], sblob, GL_SETTINGS_BLOB_LEN);
        }
        GL_CHECK_EQ(p[52], 1);
        GL_CHECK_EQ(p[54], GL_OK);
        GL_CHECK_EQ(p[57], GL_CAL_SEAT_NONE); /* no zero stored on this unit */
        GL_CHECK(gl_get_u16(&p[14]) & GL_FIELDLOG_F_FLAG_FOUND);
        GL_CHECK(gl_get_u16(&p[14]) & GL_FIELDLOG_F_LINE_HERE);
        GL_CHECK(gl_get_u16(&p[14]) & GL_FIELDLOG_F_SOLID_LINE);
        GL_CHECK(!(gl_get_u16(&p[14]) & (GL_FIELDLOG_F_CAMERAS_OFF | GL_FIELDLOG_F_GRAIN_RAN)));
        GL_CHECK_NEAR(gl_get_f32(&p[60]), 0.012, 0.0005); /* slope_raw: the green */
        GL_CHECK_NEAR(gl_get_f32(&p[72]), -0.020, 0.0005);
        GL_CHECK(gl_get_f32(&p[128]) > 0.0f && gl_get_f32(&p[128]) < 0.0005f); /* tilt scatter */
        GL_CHECK_EQ(p[234], GL_APP_TILT_BLOCKS);
        GL_CHECK_NEAR((int16_t)gl_get_u16(&p[136]), 2200.0, 3.0);  /* IMU 22.00 C */
        GL_CHECK_NEAR((int16_t)gl_get_u16(&p[138]), 220.0, 15.0);  /* cell thermistor */
        GL_CHECK_NEAR(gl_get_u16(&p[142]), 3900.0, 60.0);
        {
            /* the stages, in order, in milliseconds after the marker was still */
            const unsigned t_tilt = gl_get_u16(&p[236]), t_cam = gl_get_u16(&p[238]),
                           t_cap = gl_get_u16(&p[240]), t_s0 = gl_get_u16(&p[242]),
                           t_s1 = gl_get_u16(&p[244]), cam_on = gl_get_u16(&p[246]);
            printf("    stage times of the read in the log [ms after still]: tilt done %u, camera "
                   "rail on %u, capture done %u, solve %u .. %u; rail on for %u ms\n", t_tilt,
                   t_cam, t_cap, t_s0, t_s1, cam_on);
            GL_CHECK(t_tilt >= 1000u && t_tilt < 1400u);
            GL_CHECK(t_cam >= t_tilt && t_cap > t_cam && t_s0 >= t_cap && t_s1 >= t_s0);
            GL_CHECK(t_s1 < 6000u);
            /* the rail goes off when the last strip is in memory, before the
             * last group has been analysed; the logged time is the board
             * model's own rail-on time to within a loop pass */
            GL_CHECK(cam_on <= t_cap - t_cam && cam_on + 200u > t_cap - t_cam);
            GL_CHECK_NEAR((double)cam_on * 1000.0, (double)gl_sim_stats()->cam_rail_on_us, 6000.0);
        }
        /* options of the call */
        GL_CHECK_NEAR(gl_get_f32(&p[264]), 0.30, 1e-7);
        GL_CHECK_NEAR(gl_get_f32(&p[280]), GL_APP_NEAR_MISS_M, 1e-9);
        GL_CHECK_EQ(gl_get_u32(&p[284]), GL_APP_SOLVE_MAX_STEPS);
        GL_CHECK_EQ(p[292], GL_SOLVER_METHOD_B1);
        GL_CHECK_EQ(p[293], 0); /* grain not used */
        /* the estimate, bit for bit */
        {
            const float want[] = { e.phi_rad, e.aim_azimuth_device_rad, e.v0_mps, e.plays_like_m,
                                   e.break_m, e.break_cups, e.distance_m, e.distance_sigma_m,
                                   e.bearing_rad, e.slope_pct, e.fall_line_azimuth_rad,
                                   e.fall_line_azimuth_device_rad, e.dz_hole_m, e.patch[0],
                                   e.patch[1], e.patch[2], e.patch[3], e.patch[4],
                                   e.cross_slope_sigma, e.confidence, e.a_r_mps2, e.stimp_ft,
                                   e.grain_x, e.grain_y };
            for (size_t i = 0; i < GL_ARRAY_LEN(want); i++) {
                GL_CHECK_MEM(&p[296u + 4u * i], &want[i], 4);
            }
            GL_CHECK_EQ(gl_get_u32(&p[392]), e.n_steps);
            GL_CHECK_EQ(gl_get_u16(&p[396]), e.n_rolls);
            GL_CHECK_EQ(p[398], e.aim_source);
            GL_CHECK_EQ(p[399], e.solve_status);
            GL_CHECK_EQ(p[404], e.fit_converged ? 1 : 0);
        }
        /* the fit record */
        for (int i = 0; i < 5; i++) {
            GL_CHECK_MEM(&p[412 + 4 * i], &fit.coeffs[i], 4);
            for (int j = 0; j < 5; j++) {
                GL_CHECK_MEM(&p[432 + 4 * (5 * i + j)], &fit.cov[i][j], 4);
            }
        }
        GL_CHECK_MEM(&p[540], &fit.distance_m, 4);
        GL_CHECK_MEM(&p[560], &fit.range.stereo_m, 4);
        GL_CHECK_MEM(&p[608], &fit.cost, 4);
        GL_CHECK_EQ(gl_get_u16(&p[616]), fit.n_iter);
        GL_CHECK_EQ(p[618], fit.n_drops);
        GL_CHECK_EQ(p[625], fit.converged ? 1 : 0);
        printf("    one Quick Read in the log: placement record %u bytes (%u horizon samples), "
               "summary 72, read record %u; with their 16-byte headers %u bytes of flash (the "
               "log grew by %u bytes, the estimator's event included)\n",
               (unsigned)(GL_FIELDLOG_MEAS_FIXED + 8u * m.n_horizon), m.n_horizon,
               GL_FIELDLOG_READ_LEN,
               (unsigned)(16u + GL_FIELDLOG_MEAS_FIXED + 8u * m.n_horizon + 16u + 72u + 16u +
                          GL_FIELDLOG_READ_LEN),
               (unsigned)(used1 - used0));
    }

    /* ---- download with RESUME: the link breaks, the host asks for the
     *      records from the first one it does not have ---- */
    {
        uint32_t k_seq = 0, last = 0;
        uint8_t s[4];
        unsigned k_len = 0, n_all = 0, n_tail = 0;
        size_t tail_at = 0;
        /* the 3rd record of the full dump onward */
        for (size_t pos = 0; pos + 8u <= dump_len_[0]; n_all++) {
            if (n_all == 2u) {
                k_seq = gl_get_u32(&dump_[0][pos + 4u]);
                tail_at = pos;
            }
            last = gl_get_u32(&dump_[0][pos + 4u]);
            pos += 8u + gl_get_u16(&dump_[0][pos + 2u]);
        }
        (void)k_len;
        gl_put_u32(s, k_seq);
        GL_CHECK_EQ(st_(GL_CMD_LOG_SEEK, s, 4), GL_OK);
        (void)log_download_(1, false);
        GL_CHECK_EQ(dump_len_[1], dump_len_[0] - tail_at);
        GL_CHECK_MEM(dump_[1], &dump_[0][tail_at], dump_len_[1]); /* byte for byte the rest */
        for (size_t pos = 0; pos + 8u <= dump_len_[1]; n_tail++) {
            pos += 8u + gl_get_u16(&dump_[1][pos + 2u]);
        }
        GL_CHECK_EQ(n_tail, n_all - 2u);
        /* from beyond the newest record: nothing; from 0: everything */
        gl_put_u32(s, last + 1u);
        GL_CHECK_EQ(st_(GL_CMD_LOG_SEEK, s, 4), GL_OK);
        (void)log_download_(1, false);
        GL_CHECK_EQ(dump_len_[1], 0u);
        gl_put_u32(s, 0u);
        GL_CHECK_EQ(st_(GL_CMD_LOG_SEEK, s, 4), GL_OK);
        (void)log_download_(1, false);
        GL_CHECK_EQ(dump_len_[1], dump_len_[0]);
        GL_CHECK_MEM(dump_[1], dump_[0], dump_len_[0]);
        printf("    log of %u records downloaded twice, identical; resumed at record %u: the "
               "remaining %u records, byte for byte\n", n_all, (unsigned)k_seq, n_tail);
    }

    /* ---- the tilt logger ON: every placement writes a tilt record, also
     *      one whose camera read finds no flagstick ---- */
    {
        gl_settings_t s = app.settings;
        s.tilt_log = (uint8_t)GL_TILTLOG_ON;
        GL_CHECK_EQ(gl_app_set_settings(&app, &s), GL_OK);
    }
    undock_();
    W.stick = false;
    project_scene_();
    place_();
    run_until_ms_(now_ms_() + 9000u);
    GL_CHECK_EQ(app.ui.state, GL_UI_SETTINGS_DIAL); /* no flagstick, nothing dialled: it asks */
    run_until_ms_(now_ms_() + 90000u);
    /* ---- TILT ONLY: the cameras stay off, the placement is solved as a
     *      flag-out read ---- */
    {
        gl_settings_t s = app.settings;
        const uint32_t rail = gl_sim_stats()->cam_rail_cycles;
        const uint16_t id0 = app.read_id;
        s.tilt_log = (uint8_t)GL_TILTLOG_ONLY;
        GL_CHECK_EQ(gl_app_set_settings(&app, &s), GL_OK);
        W.stick = true;
        project_scene_();
        place_();
        GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, now_ms_() + 9000u));
        GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, rail); /* no camera was powered */
        GL_CHECK_EQ(app.read_id, (uint16_t)(id0 + 1u));
        GL_CHECK(app.est.flag_missing);
        GL_CHECK(app.view.have_result && !app.view.flag_found);
        GL_CHECK_NEAR(app.est.slope_pct, 100.0 * sqrt(0.012 * 0.012 + 0.020 * 0.020), 0.06);
        printf("    TILT ONLY: result %.2f s after the marker was put down, no camera powered, "
               "slope shown %.2f %% (true 2.33)\n",
               (double)app.ui.state_since_ms / 1000.0 - W.t_place_s, (double)app.est.slope_pct);
    }
    run_until_ms_(now_ms_() + 60000u);
    dock_();
    (void)log_download_(0, true);
    GL_CHECK_EQ(dump_count_(0, GL_LOG_REC_TILT), 2u);
    GL_CHECK_EQ(dump_count_(0, GL_LOG_REC_READ2), 2u);
    p = dump_find_(0, GL_LOG_REC_TILT, 0, &len, &seq);
    GL_CHECK(p != NULL);
    GL_CHECK_EQ(len, GL_FIELDLOG_TILT_LEN);
    GL_CHECK_EQ(p[0], GL_FIELDLOG_LAYOUT);
    GL_CHECK_EQ(p[1], GL_FIELDLOG_TILT_PLACEMENT);
    GL_CHECK_NEAR(gl_get_f32(&p[12]), 0.012, 0.0005);
    GL_CHECK_NEAR(gl_get_f32(&p[16]), -0.020, 0.0005);
    GL_CHECK_NEAR(gl_get_f32(&p[36]), 1.0, 0.002); /* accel z, uncalibrated, g */
    GL_CHECK(gl_get_f32(&p[52]) > 0.0f && gl_get_f32(&p[52]) < 0.0005f);
    GL_CHECK_NEAR((int16_t)gl_get_u16(&p[64]), 2200.0, 3.0);
    GL_CHECK_EQ(p[75], GL_APP_TILT_BLOCKS);
    p = dump_find_(0, GL_LOG_REC_READ2, 1, &len, &seq);
    GL_CHECK(p != NULL);
    GL_CHECK(gl_get_u16(&p[14]) & GL_FIELDLOG_F_CAMERAS_OFF);
    GL_CHECK(!(gl_get_u16(&p[14]) & GL_FIELDLOG_F_SOLID_LINE)); /* a tentative line */
    GL_CHECK_EQ(p[401], 1); /* flag_missing */
    GL_CHECK_EQ(gl_get_u16(&p[238]), 0xFFFF); /* the camera rail never came on */
    no_violation_();
}

/* What the log holds, and for how long: record sizes, capacity, wear.  The
 * numbers the README quotes are computed and printed here. */
/* Phase-3 review, factory finding 5: "Survey log records are untested: four
 * seeded defects in them pass every test" - ball_index always 0 in the read
 * record (S06), the "ball" flag always on placement 0 (S19), the placements
 * logged in reverse order (S22), the removed zero not logged (S21).  The
 * first three make every replay of an E29-order Survey wrong, because the
 * ball is the LAST placement.
 * A Survey of three placements in the E29 order on a unit with a base-face
 * zero; after the second and after the third placement the log must hold,
 * for that read: one placement record per placement handed to the
 * estimator, in the estimator's order, each bit-identical to the record it
 * was handed, the ball flag on the ball's record and on no other; and a
 * read record with the same count, the ball's index, the zero that was
 * removed and the estimate. */
static void survey_place_(double dist, double bearing, double sx, double sy)
{
    const double t = (double)gl_sim_now_us() * 1e-6;
    W.t_pick_s = t + 0.5;
    W.t_place_s = t + 2.0;
    run_until_ms_((uint32_t)((t + 1.0) * 1000.0));
    W.dist_m = dist;
    W.bearing_rad = bearing;
    W.slope_x = sx;
    W.slope_y = sy;
    project_scene_();
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, (uint32_t)(t * 1000.0) + 12000u));
}

GL_TEST(test_survey_in_the_field_log)
{
    static struct {
        uint16_t read_id;
        uint8_t n, ball;
        gl_measurements_t m[GL_SOLVER_MAX_DROPS];
        gl_vec2_t zero;
        gl_estimate_t est;
    } want[2];
    unsigned len = 0, checked = 0;
    uint32_t seq = 0;

    world_defaults_();
    W.dist_m = 3.0;
    W.bearing_rad = -0.02;
    W.slope_x = -0.006;
    W.slope_y = -0.014;
    project_scene_();
    board_up_(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    watch_reset_();
    /* a unit with its base-face zero: what a read on turf removes */
    app.cal_tilt.flags |= GL_CAL_TILT_FLAG_BASE;
    app.cal_tilt.base_bias_x = 0.0015f;
    app.cal_tilt.base_bias_y = -0.0010f;
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 12000));
    gl_app_post(&app, GL_EV_DOUBLE_TAP, 0);
    run_until_ms_(now_ms_() + 150u);
    gl_app_post(&app, GL_EV_DOUBLE_TAP, 0);
    run_until_ms_(now_ms_() + 150u);
    GL_CHECK_EQ(app.ui.state, GL_UI_SURVEY_NEXT_DROP);
    for (int k = 0; k < 2; k++) {
        if (k == 0) {
            survey_place_(6.0, 0.03, 0.010, -0.020);
        } else {
            survey_place_(8.0, 0.01, 0.012, -0.016);
        }
        GL_CHECK(app.solve_survey);
        GL_CHECK_EQ(app.solve_drops, 2 + k);
        GL_CHECK_EQ(app.solve_ball, 1 + k); /* E29: the ball is the LAST placement */
        want[k].read_id = app.read_id;
        want[k].n = app.solve_drops;
        want[k].ball = app.solve_ball;
        memcpy(want[k].m, app.solve_meas, sizeof(want[k].m));
        want[k].zero = app.zero_used;
        want[k].est = app.est;
        GL_CHECK_NEAR(app.zero_used.x, 0.0015, 1e-9);
        GL_CHECK_NEAR(app.zero_used.y, -0.0010, 1e-9);
    }
    GL_CHECK(want[0].read_id != want[1].read_id);
    GL_CHECK(run_until_state_(GL_UI_SLEEP, now_ms_() + 130000u));
    dock_();
    GL_CHECK(log_download_(0, true) >= 2u);
    for (int k = 0; k < 2; k++) {
        unsigned found = 0, balls = 0, n_meas = dump_count_(0, GL_LOG_REC_MEAS);
        const uint8_t *p;
        for (unsigned j = 0; j < n_meas; j++) {
            p = dump_find_(0, GL_LOG_REC_MEAS, j, &len, &seq);
            if (p == NULL || gl_get_u16(&p[0]) != want[k].read_id) {
                continue;
            }
            /* the records of one read come in the estimator's order */
            GL_CHECK_EQ(p[2], found);
            GL_CHECK_EQ(p[3], want[k].n);
            if (p[2] < want[k].n) {
                const gl_measurements_t *m = &want[k].m[p[2]];
                const float f[15] = { m->f_px, m->baseline_m, m->h_cam_m, m->tilt_x, m->tilt_y,
                                      m->flag_bearing_rad, m->flag_disparity_px, m->flag_low_elev_rad,
                                      m->flag_top_elev_rad, m->stick_height_est_m,
                                      m->stick_height_rel_sigma, m->grain_kappa, m->grain_azimuth_rad,
                                      m->stimp_ft, m->user_distance_m };
                GL_CHECK_EQ(len, GL_FIELDLOG_MEAS_FIXED + 8u * m->n_horizon);
                for (int i = 0; i < 15; i++) {
                    GL_CHECK_MEM(&p[8 + 4 * i], &f[i], 4);
                }
                /* the ball's record, and only it, carries the ball flag */
                GL_CHECK_EQ((p[4] & GL_FIELDLOG_MEAS_F_BALL) != 0u, p[2] == want[k].ball);
                balls += (p[4] & GL_FIELDLOG_MEAS_F_BALL) ? 1u : 0u;
                checked++;
            }
            found++;
        }
        GL_CHECK_EQ(found, want[k].n);
        GL_CHECK_EQ(balls, 1u);
        /* the placements are different ones: an exchanged order cannot pass */
        GL_CHECK(want[k].m[0].flag_disparity_px != want[k].m[want[k].ball].flag_disparity_px);
        GL_CHECK(want[k].m[0].tilt_y != want[k].m[want[k].ball].tilt_y);
        /* the read record of this read */
        p = NULL;
        for (unsigned j = 0; j < dump_count_(0, GL_LOG_REC_READ2); j++) {
            const uint8_t *q = dump_find_(0, GL_LOG_REC_READ2, j, &len, &seq);
            if (q != NULL && gl_get_u16(&q[2]) == want[k].read_id) {
                p = q;
            }
        }
        GL_CHECK(p != NULL);
        if (p != NULL) {
            const float e7[7] = { want[k].est.phi_rad, want[k].est.aim_azimuth_device_rad,
                                  want[k].est.v0_mps, want[k].est.plays_like_m, want[k].est.break_m,
                                  want[k].est.break_cups, want[k].est.distance_m };
            GL_CHECK_EQ(p[52], want[k].n);    /* n_drops */
            GL_CHECK_EQ(p[53], want[k].ball); /* ball_index: NOT 0 in the E29 order */
            GL_CHECK(p[53] != 0u);
            GL_CHECK(gl_get_u16(&p[14]) & GL_FIELDLOG_F_SURVEY);
            GL_CHECK_EQ(p[57], GL_CAL_SEAT_BASE);
            GL_CHECK_MEM(&p[76], &want[k].zero.x, 4); /* the zero that was removed */
            GL_CHECK_MEM(&p[80], &want[k].zero.y, 4);
            GL_CHECK(gl_get_f32(&p[76]) != 0.0f && gl_get_f32(&p[80]) != 0.0f);
            /* slope used = raw slope less that zero */
            GL_CHECK_NEAR(gl_get_f32(&p[68]), gl_get_f32(&p[60]) - gl_get_f32(&p[76]), 1e-7);
            GL_CHECK_NEAR(gl_get_f32(&p[72]), gl_get_f32(&p[64]) - gl_get_f32(&p[80]), 1e-7);
            for (int i = 0; i < 7; i++) {
                GL_CHECK_MEM(&p[296 + 4 * i], &e7[i], 4);
            }
        }
    }
    GL_CHECK_EQ(checked, 5u);
    printf("    Survey of 3 placements (3 m, 6 m, the ball at 8 m) in the log: the reads after the "
           "2nd and 3rd placement hold 2 and 3 placement records in the estimator's order, "
           "bit-identical to what it was handed, ball flag on record 1 and 2, read records with "
           "ball_index 1 and 2 and the removed base-face zero (%.2f, %.2f) mrad\n",
           1000.0 * (double)want[1].zero.x, 1000.0 * (double)want[1].zero.y);
    no_violation_();
}

GL_TEST(test_log_capacity_and_wear)
{
    const double sector = 4096.0 - GL_LOG_SECTOR_HDR;
    const double sectors = (double)GL_APP_LOG_SECTORS;
    const unsigned hdr = GL_LOG_REC_HDR;
    /* a Quick Read as test_field_log_records_and_resume measured it: 32
     * horizon samples; the worst case has 41 */
    const unsigned meas = GL_FIELDLOG_MEAS_FIXED + 8u * GL_VIS_HORIZON_BINS;
    const unsigned quick = (hdr + meas) + (hdr + GL_LOG_READ_LEN) + (hdr + 12u) +
                           (hdr + GL_FIELDLOG_READ_LEN);
    const unsigned survey4 = 4u * (hdr + meas) + (hdr + GL_LOG_READ_LEN) + (hdr + 12u) +
                             (hdr + GL_FIELDLOG_READ_LEN);
    const unsigned tilt = hdr + GL_FIELDLOG_TILT_LEN;
    const double reads_if_split = floor(sectors * sector / (double)quick);
    const double tilts = floor(sectors * floor(sector / (double)tilt));
    /* wear: the ring erases each sector once per pass through the log */
    const double cycles = 100000.0; /* PROVISIONAL: the endurance class of the MX25R family */
    double reads;

    GL_CHECK_EQ(GL_FIELDLOG_READ_LEN % 4u, 0u);
    GL_CHECK_EQ(GL_FIELDLOG_TILT_LEN % 4u, 0u);
    GL_CHECK(GL_FIELDLOG_MEAS_MAX <= 1014u && GL_FIELDLOG_READ_LEN <= 1014u); /* one LOG_READ */
    GL_CHECK_EQ(meas, 324u);
    GL_CHECK_EQ(quick, 1156u); /* = what test_field_log_records_and_resume saw the log grow by */
    printf("    record sizes on flash (16-byte header included): placement %u (68 + 8 per horizon "
           "sample; %u with the 32 of a read), summary %u, estimator event %u, read record %u, "
           "tilt record %u\n", hdr + GL_FIELDLOG_MEAS_FIXED, hdr + meas, hdr + GL_LOG_READ_LEN,
           hdr + 12u, hdr + GL_FIELDLOG_READ_LEN, tilt);
    /* E29: a Survey is solved after every placement from the second on, and
     * every solve logs all the placements it used: a session of four
     * placements writes a Quick Read, then reads of 2, 3 and 4 placements */
    printf("    a Quick Read: %u bytes; the last read of a Survey of 4 placements: %u bytes; the "
           "whole Survey session (reads of 1, 2, 3 and 4 placements): %u bytes\n", quick, survey4,
           4u * quick + 6u * (hdr + meas));
    GL_CHECK_EQ(4u * quick + 6u * (hdr + meas), 6664u);
    /* THE CAPACITY, MEASURED (phase-3 review, factory finding 6).  Until the
     * review this test pinned floor(2044 x 4080 / 1156) = 7214 Quick Reads -
     * arithmetic that splits records across sectors, which the log does not
     * do.  The log of the booted application is filled here with the real
     * record pattern of a Quick Read (payloads 324, 72, 12 and 684 bytes)
     * until the oldest sector is dropped for the first time. */
    {
        static uint8_t rec[GL_FIELDLOG_READ_LEN];
        static const struct {
            uint8_t type;
            uint16_t len;
        } pat[4] = { { GL_LOG_REC_MEAS, 324 }, { GL_LOG_REC_READ, GL_LOG_READ_LEN },
                     { GL_LOG_REC_EVENT, 12 }, { GL_LOG_REC_READ2, GL_FIELDLOG_READ_LEN } };
        gl_log_stats_t ls;
        uint32_t base, written = 0, retained_reads = 0, used = 0;
        bool dropped = false;

        world_defaults_();
        W.t_pick_s = 1.0e9;
        W.t_place_s = 1.0e9;
        board_up_(true);
        GL_CHECK_EQ(gl_app_init(&app), GL_OK);
        GL_CHECK_EQ(GL_LOG_READ_LEN, 72u);
        memset(rec, 0x5A, sizeof(rec));
        GL_CHECK_EQ(gl_log_stats(&app.log, &ls), GL_OK);
        base = ls.record_estimate;
        while (!dropped && written < 9000u) {
            for (int k = 0; k < 4; k++) {
                GL_CHECK_EQ(gl_log_append(&app.log, pat[k].type, 0, rec, pat[k].len, NULL), GL_OK);
            }
            written++;
            if ((written & 0xFFu) == 0u) {
                gl_hal_watchdog_kick();
            }
            GL_CHECK_EQ(gl_log_stats(&app.log, &ls), GL_OK);
            if (ls.record_estimate < base + 4u * written) {
                dropped = true;
                retained_reads = ls.record_estimate / 4u;
            } else {
                used = ls.bytes_used;
            }
        }
        GL_CHECK(dropped);
        reads = (double)retained_reads;
        printf("    log region: %u sectors of 4096 bytes = %.2f MB.  FILLED with the record pattern "
               "of a Quick Read until the oldest sector was first dropped: %u patterns written, "
               "%.0f read records then retained, %u of %u bytes used (records are not split "
               "across sectors: 3 reads per sector, 612 bytes of each left empty; the arithmetic "
               "that splits them gave %.0f).  Or %.0f tilt records\n",
               (unsigned)GL_APP_LOG_SECTORS, sectors * 4096.0 / 1.0e6, (unsigned)written, reads,
               (unsigned)used, (unsigned)ls.bytes_capacity, reads_if_split, tilts);
        /* three reads per sector, one sector of the ring always being the
         * erased one ahead of the head */
        GL_CHECK_NEAR((double)written, 3.0 * sectors, 3.0 * 3.0);
        GL_CHECK(reads >= 3.0 * (sectors - 2.0) - 4.0 && reads <= 3.0 * sectors);
        GL_CHECK(reads < 0.86 * reads_if_split); /* the old figure overstated it by 15 % and more */
    }
    printf("    wear: one erase per sector per %.0f reads; at 200 reads a day the ring turns "
           "once in %.1f days, and %.0f erase cycles (PROVISIONAL endurance) last %.0f years\n",
           reads, reads / 200.0, cycles, cycles * reads / 200.0 / 365.0);
    GL_CHECK(tilts > 80000.0);
}

int main(void)
{
    GL_RUN(test_identity_and_version_negotiation);
    GL_RUN(test_guarded_commands_need_unlock);
    GL_RUN(test_bad_arguments);
    GL_RUN(test_camera_identity_and_frames);
    GL_RUN(test_narrow_window_at_the_right_edge);
    GL_RUN(test_camera_field_gate_2);
    GL_RUN(test_display_test_patterns);
    GL_RUN(test_display_rotation_from_pixels);
    GL_RUN(test_grain_leds_and_dark_offset);
    GL_RUN(test_level_zero_armed_on_two_seats);
    GL_RUN(test_level_zero_after_the_30_minute_rest);
    GL_RUN(test_reference_line_on_the_seat_plate);
    GL_RUN(test_a_refused_store_changes_nothing);
    GL_RUN(test_six_face_tempco_horizon_floor_serial);
    GL_RUN(test_sleep_current_test_mode);
    GL_RUN(test_field_log_records_and_resume);
    GL_RUN(test_survey_in_the_field_log);
    GL_RUN(test_log_capacity_and_wear);
    return gl_test_summary();
}
