"""Framing, command ids, status codes and the fixed-layout records of
firmware/core/gl_proto.h (protocol version 3).  Pure: no I/O."""
import struct

SOF = b"\xA5\x5A"
MAX_PAYLOAD = 1024
RESPONSE_FLAG = 0x80
STREAM_FLAG = 0x40

CMD = {
    "PING": 0x01, "GET_INFO": 0x02, "GET_STATUS": 0x03, "GET_SETTINGS": 0x04, "SET_SETTINGS": 0x05,
    "GET_CAL": 0x06, "SET_CAL": 0x07, "START_CAL": 0x08, "LOG_INFO": 0x09, "LOG_READ": 0x0A,
    "LOG_ERASE": 0x0B, "STREAM": 0x0C, "SET_TIME": 0x0D, "UNLOCK": 0x0E, "REBOOT": 0x0F,
    "SHIP_MODE": 0x10, "GET_POWER": 0x11, "SET_CHARGE": 0x12,
    "GET_IDENT": 0x13, "GET_SENSORS": 0x14, "CAM_ID": 0x15, "CAM_CAPTURE": 0x16, "CAM_DATA": 0x17,
    "CAM_FIELD": 0x18, "DISPLAY_TEST": 0x19, "GRAIN_TEST": 0x1A, "LEVEL_ZERO": 0x1B,
    "CAL_STATUS": 0x1C, "TILT_TEMPCO": 0x1D, "SET_CAM_HORIZON": 0x1E, "SET_GRAIN_FLOOR": 0x1F,
    "DISPLAY_ROT": 0x20, "SLEEP_TEST": 0x21, "LOG_SEEK": 0x22, "SERIAL": 0x23,
}
CMD_NAME = {v: k for k, v in CMD.items()}

STATUS = ["OK", "PARAM", "NOT_IMPLEMENTED", "TIMEOUT", "IO", "CRC", "FULL", "EMPTY", "RANGE", "BUSY",
          "NOT_FOUND", "NO_STICK", "QUALITY", "MOTION", "CORRUPT", "STATE", "UNSUPPORTED"]

CAL_ID = {"tilt": 1, "cam_l": 2, "cam_r": 3, "grain": 4, "device": 5}
CALPROC = {"ZERO": 1, "SIX_FACE": 2, "GRAIN_WHITE": 3, "GRAIN_FLOOR": 4, "CAM_HORIZON": 5, "ABORT": 0x7F}
PATTERN = {"normal": 0, "white": 1, "black": 2, "checker1": 3, "checker8": 4, "rows": 5, "columns": 6,
           "orient": 7, "ref-raw": 8, "ref-corrected": 9}
SEAT = {"base": 0, "ball": 1}
ZERO_STATE = ["IDLE", "ARMED", "RUNNING", "DONE", "FAILED"]
WAKE = {"motion": 1, "timer": 2, "vbus": 4}
TEMP_NONE = -32768


class ProtocolError(Exception):
    """A frame could not be exchanged (transport, CRC, time-out)."""


class DeviceError(Exception):
    """The unit answered with a status other than OK."""

    def __init__(self, cmd, status):
        self.cmd = cmd
        self.status = status
        name = STATUS[status] if status < len(STATUS) else str(status)
        Exception.__init__(self, "%s answered %s (%d)" % (CMD_NAME.get(cmd, hex(cmd)), name, status))
        self.status_name = name


def crc16(data, crc=0xFFFF):
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF)."""
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def encode(seq, cmd, payload=b""):
    if len(payload) > MAX_PAYLOAD:
        raise ProtocolError("payload of %d bytes exceeds %d" % (len(payload), MAX_PAYLOAD))
    body = struct.pack("<HBB", len(payload), seq & 0xFF, cmd) + bytes(payload)
    return SOF + body + struct.pack("<H", crc16(body))


class Parser:
    """Finds frames in a byte stream; resynchronises as the firmware does
    (drop one byte after a bad header or CRC)."""

    def __init__(self):
        self.buf = bytearray()
        self.crc_errors = 0

    def feed(self, data):
        self.buf += data
        frames = []
        while True:
            i = self.buf.find(SOF)
            if i < 0:
                del self.buf[:max(0, len(self.buf) - 1)]
                break
            del self.buf[:i]
            if len(self.buf) < 6:
                break
            n, seq, cmd = struct.unpack_from("<HBB", self.buf, 2)
            if n > MAX_PAYLOAD:
                del self.buf[:1]
                continue
            if len(self.buf) < n + 8:
                break
            if crc16(self.buf[2:6 + n]) != struct.unpack_from("<H", self.buf, 6 + n)[0]:
                self.crc_errors += 1
                del self.buf[:1]
                continue
            frames.append((seq, cmd, bytes(self.buf[6:6 + n])))
            del self.buf[:n + 8]
        return frames


def _t10(v):
    return None if v == TEMP_NONE else v / 10.0


def parse_info(p):
    proto, hw, fw, build, solver = struct.unpack_from("<BBHII", p, 0)
    return {"proto_version": proto, "hw_rev": hw, "fw_version": "%d.%d" % (fw >> 8, fw & 0xFF),
            "fw_build": build, "solver_version": "0x%08X" % solver, "unique_id": p[12:24].hex(),
            "uptime_s": struct.unpack_from("<I", p, 24)[0]}


def parse_status(p):
    mv, t, ui, flags, err, reads, rtc = struct.unpack_from("<HhBBHII", p, 0)
    return {"battery_mv": mv, "imu_temp_c": _t10(t), "ui_state": ui, "vbus": bool(flags & 1),
            "charging": bool(flags & 2), "charge_free": bool(flags & 4), "unlocked": bool(flags & 8),
            "ship_armed": bool(flags & 16), "last_error": err, "reads_total": reads, "rtc_s": rtc}


def parse_power(p):
    mv, cell, mcu, imu, fault, st, why, cradle, flags, mins = struct.unpack_from("<HhhhBBBBHH", p, 0)
    return {"battery_mv": mv, "cell_temp_c": _t10(cell), "mcu_temp_c": _t10(mcu), "imu_temp_c": _t10(imu),
            "ntc_fault": fault, "chg_status": st, "chg_reason": why,
            "cradle": ["out", "link", "sleep"][cradle] if cradle < 3 else cradle, "flags": flags,
            "charge_min": mins}


def parse_ident(p):
    f = struct.unpack_from("<BBBc8sHBBII12sII5sB14s8s", p, 0)
    serial = f[11]
    commands = [c for c in range(64) if f[16][c // 8] >> (c % 8) & 1]
    fl = f[14]
    return {
        "proto_version": f[0], "agreed_version": f[1], "hw_rev": f[2], "hw_letter": f[3].decode("ascii"),
        "model": f[4].rstrip(b"\0").decode("ascii"), "fw_version": "%d.%d" % (f[5] >> 8, f[5] & 0xFF),
        "cal_version": f[6], "log_layout": f[7], "fw_build": f[8], "solver_version": "0x%08X" % f[9],
        "unique_id": f[10].hex(), "serial": serial, "serial_text": serial_text(serial),
        "serial_stored": f[12],
        "cal_flags": dict(zip(("tilt", "cam_l", "cam_r", "grain", "device"), f[13])),
        "serial_is_stored": bool(fl & 1), "serial_matches_this_processor": bool(fl & 2),
        "release_build": bool(fl & 4), "unlocked": bool(fl & 8), "calibration_complete": bool(fl & 16),
        "params_rev": f[15].rstrip(b"\0").decode("ascii"),
        "commands": [CMD_NAME.get(c, hex(c)) for c in commands], "command_ids": commands,
    }


def parse_sensors(p):
    mv, vdda, cell, mcu, imu, counts, full, fault, flags, wake, mask, sleep_ms, up = \
        struct.unpack_from("<HHhhhHHBBBBII", p, 0)
    return {"battery_mv": mv, "rail_2v8_mv": vdda, "cell_temp_c": _t10(cell), "mcu_temp_c": _t10(mcu),
            "imu_temp_c": _t10(imu), "ntc_counts": counts, "ntc_full_scale": full, "ntc_fault": fault,
            "vbus": bool(flags & 1), "usb_supply": bool(flags & 2), "cam_rail": bool(flags & 4),
            "chg_stat_low": bool(flags & 8), "chg_inhibit": bool(flags & 16),
            "sleep_test_armed": bool(flags & 32), "sleep_test_woke_by": wake, "sleep_test_mask": mask,
            "sleep_test_ms": sleep_ms, "uptime_ms": up}


def parse_capture(p):
    cam, kind, x0, y0, w, h, n, lo, hi, mean, bright, crc = struct.unpack_from("<BBHHHHIBBHII", p, 0)
    return {"camera": cam, "kind": kind, "x0": x0, "y0": y0, "width": w, "height": h, "bytes": n,
            "min": lo, "max": hi, "mean": mean / 16.0, "bright_pixels": bright, "crc32": crc}


def parse_field(p):
    cam, st, ru, rl, mu, ml, mc, ratio, xu, xl = struct.unpack_from("<BBHHHHHHBB", p, 0)
    return {"camera": cam, "status": st, "row_upper": ru, "row_lower": rl, "mean_upper": mu / 16.0,
            "mean_lower": ml / 16.0, "mean_centre": mc / 16.0,
            "ratio": None if ratio == 65535 else ratio / 1000.0, "max_upper": xu, "max_lower": xl}


def parse_grain(p):
    mode, st, mean, lo, hi, full, stored = struct.unpack_from("<BBHHHHH", p, 0)
    leds = [struct.unpack_from("<HHH", p, 12 + 6 * i) for i in range(16)]
    return {"mode": mode, "cycle_status": STATUS[st] if st < len(STATUS) else st, "dark_mean": mean,
            "dark_min": lo, "dark_max": hi, "full_scale": full, "stored_dark": stored,
            "leds": [{"led": i, "dark1": a, "on": b, "dark2": c, "signal": b - (a + c) / 2.0}
                     for i, (a, b, c) in enumerate(leds)] if st == 0 else []}


def parse_zero(p):
    state, seat, st, attempts, bx, by, scatter, turn, sx, sy, temp, t = struct.unpack_from("<BBBBfffffffI", p, 0)
    return {"state": ZERO_STATE[state] if state < len(ZERO_STATE) else state,
            "seat": "base" if seat == 0 else "ball", "status": STATUS[st] if st < len(STATUS) else st,
            "attempts": attempts, "bias_x": bx, "bias_y": by, "scatter": scatter, "turn_rad": turn,
            "surface_x": sx, "surface_y": sy, "temp_c": temp, "time_s": t}


def parse_six(p):
    mask, active, face, flags = struct.unpack_from("<BBBB", p, 0)
    means = [list(struct.unpack_from("<fff", p, 4 + 12 * f)) for f in range(6)]
    return {"done_mask": mask, "active": bool(active), "face": face, "tilt_cal_flags": flags,
            "means_g": {f: means[f] for f in range(6) if mask >> f & 1},
            "temp_c": struct.unpack_from("<f", p, 76)[0]}


SETTINGS_KEYS = ("version", "stimp_x2", "units", "past_cm", "grass", "grain_enable", "raw_log_level",
                 "method", "manual_distance_cm", "surface", "tilt_log")


def parse_settings(p):
    return dict(zip(SETTINGS_KEYS, struct.unpack_from("<BBBBBBBBHBB", p, 0)))


def build_settings(s):
    return struct.pack("<BBBBBBBBHBB", *[int(s[k]) for k in SETTINGS_KEYS])


def serial_text(serial):
    """The 7 characters marked on the base plate (gl_cal_serial_text)."""
    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    out = ""
    for _ in range(7):
        out = alphabet[serial & 31] + out
        serial >>= 5
    return out
