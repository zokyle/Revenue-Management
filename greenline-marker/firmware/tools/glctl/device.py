"""The unit as an object: one method per protocol command."""
import struct
import time
import zlib

from . import proto
from .proto import CMD, DeviceError, ProtocolError


class Device:
    def __init__(self, transport, host_version=None):
        self.t = transport
        self.parser = proto.Parser()
        self.seq = 0
        self.host_version = host_version or 3
        self.ident_cache = None

    # ---- one exchange ---------------------------------------------------------
    def raw(self, cmd, payload=b"", timeout=2.0):
        """Send a command; return (status, data after the status byte)."""
        self.seq = (self.seq + 1) & 0xFF
        self.t.write(proto.encode(self.seq, cmd, payload))
        deadline = time.monotonic() + timeout
        tries = 0
        while True:
            for seq, rcmd, body in self.parser.feed(self.t.read(0.05)):
                if rcmd == (cmd | proto.RESPONSE_FLAG) and seq == self.seq and body:
                    return body[0], body[1:]
            tries += 1
            # the simulator's clock is not this PC's: count exchanges there
            if time.monotonic() > deadline or tries > 200:
                raise ProtocolError("no answer to %s" % proto.CMD_NAME.get(cmd, hex(cmd)))

    def cmd(self, name, payload=b"", timeout=2.0):
        """Send a command by name; return its data or raise DeviceError."""
        status, data = self.raw(CMD[name], payload, timeout)
        if status != 0:
            raise DeviceError(CMD[name], status)
        return data

    # ---- negotiation -------------------------------------------------------------
    def negotiate(self):
        """GET_IDENT with our version; on a unit of protocol 1 or 2 fall back to GET_INFO.
        Returns the identity and remembers which commands the unit has."""
        status, data = self.raw(CMD["GET_IDENT"], bytes([self.host_version]))
        if status == 0:
            self.ident_cache = proto.parse_ident(data)
        elif status == proto.STATUS.index("UNSUPPORTED"):
            info = proto.parse_info(self.cmd("GET_INFO"))
            first = {1: 0x0F, 2: 0x12}.get(info["proto_version"], 0x0F)
            self.ident_cache = dict(info, agreed_version=info["proto_version"], model="GL-1",
                                    command_ids=list(range(1, first + 1)),
                                    commands=[proto.CMD_NAME[c] for c in range(1, first + 1)])
        else:
            raise DeviceError(CMD["GET_IDENT"], status)
        return self.ident_cache

    def has(self, name):
        if self.ident_cache is None:
            self.negotiate()
        return CMD[name] in self.ident_cache["command_ids"]

    # ---- phases 1 and 2 ---------------------------------------------------------------
    def ping(self, data=b"glctl"):
        return self.cmd("PING", data) == data

    def info(self):
        return proto.parse_info(self.cmd("GET_INFO"))

    def status(self):
        return proto.parse_status(self.cmd("GET_STATUS"))

    def power(self):
        return proto.parse_power(self.cmd("GET_POWER"))

    def unlock(self):
        self.cmd("UNLOCK", b"GLFC")

    def lock(self):
        """The explicit lock of the final test: UNLOCK with the word LOCK answers OK, locked."""
        self.cmd("UNLOCK", b"LOCK")

    def stream(self, sources, period_ms=100, count=10, timeout=10.0):
        """Switch live streams on (sources: names of proto.STREAM_SOURCE), collect `count`
        frames, switch them off again.  The unit must be talked to at least every 30 s to
        stay awake in its cradle: a stream it was asked for counts as talking."""
        mask = 0
        for name in sources:
            mask |= 1 << proto.STREAM_SOURCE[name]
        self.cmd("STREAM", struct.pack("<HH", mask, period_ms))
        frames = []
        deadline = time.monotonic() + timeout
        tries = 0
        try:
            while len(frames) < count:
                for _seq, rcmd, body in self.parser.feed(self.t.read(0.05)):
                    if rcmd & proto.STREAM_FLAG and not rcmd & proto.RESPONSE_FLAG:
                        frames.append(proto.parse_stream(rcmd & 0x3F, body))
                tries += 1
                if time.monotonic() > deadline or tries > 2000:
                    raise ProtocolError("the unit sent %d of %d stream frames" % (len(frames), count))
        finally:
            self.cmd("STREAM", struct.pack("<HH", 0, 0))
        return frames[:count]

    def get_settings(self):
        return proto.parse_settings(self.cmd("GET_SETTINGS"))

    def set_settings(self, **changes):
        s = self.get_settings()
        for k, v in changes.items():
            if k not in s or k == "version":
                raise ValueError("no setting %r (have: %s)" % (k, ", ".join(proto.SETTINGS_KEYS[1:])))
            s[k] = int(v)
        self.cmd("SET_SETTINGS", proto.build_settings(s))
        return self.get_settings()

    def get_cal(self, which):
        data = self.cmd("GET_CAL", bytes([proto.CAL_ID[which]]))
        return data[1:]

    def set_cal(self, which, blob):
        self.cmd("SET_CAL", bytes([proto.CAL_ID[which]]) + bytes(blob))

    def set_time(self, seconds=None):
        self.cmd("SET_TIME", struct.pack("<I", int(time.time() if seconds is None else seconds)))

    def ship_mode(self, arm=True):
        return self.cmd("SHIP_MODE", b"SHIP" if arm else b"STAY")[0] == 1

    def set_charge(self, stop):
        self.cmd("SET_CHARGE", bytes([1 if stop else 0]))

    def reboot(self, loader=False):
        """loader=True: request the update loader (needs unlock; the boot stub starts it)."""
        self.cmd("REBOOT", b"DFU!" if loader else b"BOOT")

    def start_cal(self, procedure, arg=0):
        self.cmd("START_CAL", bytes([proto.CALPROC[procedure], arg]))

    # ---- factory and calibration ---------------------------------------------------------
    def ident(self):
        return self.negotiate()

    def sensors(self):
        return proto.parse_sensors(self.cmd("GET_SENSORS"))

    def cam_id(self, cam):
        d = self.cmd("CAM_ID", bytes([cam]))
        return {"camera": d[0], "product_id": "0x%04X" % struct.unpack_from("<H", d, 1)[0],
                "as_expected": bool(d[3])}

    def capture(self, cam, x0, y0, w, h, dark=False):
        return proto.parse_capture(self.cmd("CAM_CAPTURE", struct.pack("<BBHHHH", cam, 1 if dark else 0,
                                                                        x0, y0, w, h), timeout=5.0))

    def cam_data(self, total, start=0, piece=1000, have=b""):
        """Download the pixels of the last capture from offset `start` (a resumed download
        passes what it has in `have`)."""
        out = bytearray(have)
        off = start
        while off < total:
            n = min(piece, total - off)
            d = self.cmd("CAM_DATA", struct.pack("<IH", off, n))
            if struct.unpack_from("<I", d, 0)[0] != off or len(d) != 4 + n:
                raise ProtocolError("CAM_DATA answered another piece than was asked for")
            out += d[4:]
            off += n
        return bytes(out)

    def picture(self, cam, x0, y0, w, h, dark=False):
        """One exposure, downloaded and checked against the CRC the unit reported."""
        info = self.capture(cam, x0, y0, w, h, dark)
        pixels = self.cam_data(info["bytes"])
        if zlib.crc32(pixels) & 0xFFFFFFFF != info["crc32"]:
            raise ProtocolError("downloaded picture does not match the CRC of the capture")
        return info, pixels

    def frame(self, cam, dark=False):
        """A whole 640 x 480 frame: two exposures of 640 x 240 (the unit's image memory
        holds 640 x 288)."""
        top_info, top = self.picture(cam, 0, 0, 640, 240, dark)
        bot_info, bot = self.picture(cam, 0, 240, 640, 240, dark)
        return {"width": 640, "height": 480, "exposures": [top_info, bot_info]}, top + bot

    def cam_field(self, cam):
        return proto.parse_field(self.cmd("CAM_FIELD", bytes([cam]), timeout=5.0))

    def display_test(self, pattern, hold_s=30, plate=False):
        """plate=True (needs unlock): also ARM the pattern for the seat plate - it is shown
        again, for hold_s, when the marker is next put down out of the cradle."""
        req = bytes([proto.PATTERN[pattern], hold_s if pattern != "normal" else 0])
        d = self.cmd("DISPLAY_TEST", req + (b"\x01" if plate else b""))
        return {"pattern": d[0], "frame_crc32": struct.unpack_from("<I", d, 1)[0],
                "black_pixels": struct.unpack_from("<H", d, 5)[0]}

    def grain_test(self, mode="cycle"):
        return proto.parse_grain(self.cmd("GRAIN_TEST", bytes([{"dark": 0, "cycle": 1, "store": 2}[mode]])))

    def level_zero(self, op="status", seat="base", rest_min=0):
        """rest_min (with arm): the zeroing does not start before the marker has been off
        VBUS for that many minutes (assembly step 19: 30)."""
        req = bytes([{"status": 0, "arm": 1, "cancel": 2}[op], proto.SEAT[seat]])
        d = self.cmd("LEVEL_ZERO", req + (bytes([rest_min]) if rest_min else b""))
        return proto.parse_zero(d)

    def grain_white(self):
        """The white reference of the grain reader (the marker on the white tile)."""
        self.start_cal("GRAIN_WHITE", 0)
        return {"grain_cal_flags": self.get_cal("grain")[1]}

    def cal_status(self):
        return proto.parse_six(self.cmd("CAL_STATUS"))

    def six_face(self, face, wait=None):
        """Start the average of one face (0..5: +x -x +y -y +z -z up) and wait for it."""
        self.start_cal("SIX_FACE", face)
        for _ in range(60):
            st = self.cal_status()
            if not st["active"]:
                return st
            if wait:
                wait(0.2)
        raise ProtocolError("the face average did not finish (the unit is not still)")

    def six_face_solve(self):
        self.start_cal("SIX_FACE", 6)
        return self.cal_status()

    def tilt_tempco(self, points, t0=25.0):
        """points: [(temperature C, offset x, y, z in g), ...], at least 5 over at least 30 K.
        The unit stores the TEMPERATURE TERMS b1, b2 about its six-face temperature and KEEPS
        its six-face offsets: the points may be absolute offsets or drift against any
        reference (0 for an axis that was not measured).  t0 = the six-face temperature the
        host believes in; the unit refuses (RANGE) if its record says otherwise by 3 K.
        b0, the fitted value at t0, comes back for comparison and is not stored."""
        payload = struct.pack("<Bf", len(points), t0) + b"".join(struct.pack("<ffff", *p) for p in points)
        d = self.cmd("TILT_TEMPCO", payload)
        f = struct.unpack_from("<10f", d, 0)
        out = {"b0_fit_g_not_stored": list(f[0:3]), "b1_g_per_k": list(f[3:6]), "b2_g_per_k2": list(f[6:9]),
               "rms_residual_g": f[9]}
        if len(d) >= 44:
            out["max_residual_g"] = struct.unpack_from("<f", d, 40)[0]
        return out

    def set_cam_horizon(self, cam, row, roll_rad=0.0):
        d = self.cmd("SET_CAM_HORIZON", struct.pack("<Bff", cam, row, roll_rad))
        return {"pitch_up_rad": struct.unpack_from("<f", d, 0)[0]}

    def set_grain_floor(self, modulations):
        payload = bytes([len(modulations)]) + b"".join(struct.pack("<f", m) for m in modulations)
        d = self.cmd("SET_GRAIN_FLOOR", payload)
        return dict(zip(("noise_floor", "threshold"), struct.unpack_from("<ff", d, 0)))

    def display_rot(self, write_rad=None):
        payload = b"\0" if write_rad is None else b"\1" + struct.pack("<f", write_rad)
        d = self.cmd("DISPLAY_ROT", payload)
        return {"rotation_rad": struct.unpack_from("<f", d, 0)[0], "measured": bool(d[4])}

    def sleep_test(self, motion=False, timer_s=0):
        mask = (1 if motion else 0) | (2 if timer_s else 0)
        d = self.cmd("SLEEP_TEST", struct.pack("<BH", mask, timer_s))
        return {"armed": bool(d[0]), "wake_mask": d[1]}

    def serial(self, commit=False):
        d = self.cmd("SERIAL", b"SNUM" if commit else b"")
        return {"serial": struct.unpack_from("<I", d, 0)[0], "text": d[4:11].decode("ascii"),
                "stored_for_this_processor": bool(d[11])}

    # ---- the log ------------------------------------------------------------------------
    def log_info(self):
        return dict(zip(("record_count", "bytes_used", "bytes_capacity", "newest_seq"),
                        struct.unpack_from("<IIII", self.cmd("LOG_INFO"), 0)))

    def log_erase(self):
        self.cmd("LOG_ERASE", b"ERAS")

    def log_download(self, resume_after=None, progress=None, sink=None):
        """The raw record stream (type, flags, length, sequence number, payload per record).
        resume_after = the sequence number of the last record a broken download already has.
        sink(bytes), if given, receives every response's records AS THEY ARRIVE (each
        response holds whole records): what has arrived is kept if the link then drops."""
        if resume_after is None:
            restart = 1
        else:
            self.cmd("LOG_SEEK", struct.pack("<I", resume_after + 1))
            restart = 0
        out = bytearray()
        while True:
            d = self.cmd("LOG_READ", bytes([restart]), timeout=5.0)
            restart = 0
            out += d[1:]
            if sink:
                sink(d[1:])
            if progress:
                progress(len(out))
            if d[0] == 0:
                return bytes(out)

    def log_download_to(self, path, resume=False):
        """Download the log INTO A FILE, writing it as the responses arrive: a link that
        drops leaves a file that ends at a record boundary, and resume=True continues it
        (LOG_SEEK after its last complete record).  Until the phase-3 review the file was
        written only after a complete download, so a broken one left nothing to resume."""
        from . import logdec  # noqa: PLC0415
        have, after = 0, None
        if resume:
            with open(path, "rb") as fh:
                data = fh.read()
            after, have = logdec.last_seq(data)
            if have != len(data):
                with open(path, "r+b") as fh:
                    fh.truncate(have)  # a record cut in half at the end of the file
        new = [0]
        with open(path, "ab" if resume else "wb") as fh:
            def sink(chunk):
                fh.write(chunk)
                fh.flush()
                new[0] += len(chunk)
            self.log_download(after if resume else None, sink=sink)
        return {"bytes": have + new[0], "new_bytes": new[0], "resumed_after_seq": after, "written": path}
