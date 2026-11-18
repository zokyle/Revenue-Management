"""Decode a log dump (the record stream of LOG_READ) into JSON-ready
dictionaries.  Mirrors firmware/core/gl_log.c (read summary, event, raw
chunk header) and firmware/core/gl_fieldlog.c (placement, read, tilt)
field by field: a change there is a change here, and of the layout number."""
import math
import struct

LAYOUT = 1
REC_NAME = {1: "read_summary", 2: "raw_chunk", 3: "event", 4: "grain_raw", 5: "placement", 6: "read", 7: "tilt"}
EVENT_NAME = {1: "BOOT", 2: "FAULT", 3: "ZEROED", 4: "SIX_FACE", 5: "GRAIN_WHITE", 6: "IMU_RECOVERED",
              7: "STORAGE", 8: "ESTIMATE", 9: "CHARGE", 10: "SHIP", 11: "TOO_HOT", 12: "CHARGER"}
TILT_KIND = ["placement", "reread", "zero_1", "zero_2", "too_hot", "not_solved"]
STAGES = ("tilt_done", "camera_on", "capture_done", "solve_start", "solve_done")


class LogError(Exception):
    pass


def _num(v):
    """A float32 as JSON: not-a-number and infinities become None (as Measurements.to_dict)."""
    return float(v) if math.isfinite(v) else None


def _f(p, off, n=1):
    v = struct.unpack_from("<%df" % n, p, off)
    return _num(v[0]) if n == 1 else [_num(x) for x in v]


def _t10(v):
    return None if v == -32768 else v / 10.0


def split(stream):
    """The records of a dump: (type, flags, seq, payload)."""
    pos = 0
    while pos < len(stream):
        if pos + 8 > len(stream):
            raise LogError("the dump ends inside a record header at byte %d" % pos)
        typ, flags, n, seq = struct.unpack_from("<BBHI", stream, pos)
        if pos + 8 + n > len(stream):
            raise LogError("the dump ends inside record %d" % seq)
        yield typ, flags, seq, stream[pos + 8:pos + 8 + n]
        pos += 8 + n


def last_seq(stream):
    """Sequence number of the last COMPLETE record of a (possibly cut) dump, and the length
    of the stream up to its end: what a resumed download continues from."""
    pos, last, good = 0, None, 0
    while pos + 8 <= len(stream):
        n, seq = struct.unpack_from("<HI", stream, pos + 2)
        if pos + 8 + n > len(stream):
            break
        last, pos = seq, pos + 8 + n
        good = pos
    return last, good


def dec_placement(p):
    if len(p) < 68 or p[7] != LAYOUT:
        raise LogError("placement record of an unknown layout (%d)" % (p[7] if len(p) > 7 else -1))
    read_id, drop, n_drops, flags, tilt_reads, n_h = struct.unpack_from("<HBBBBB", p, 0)
    f = struct.unpack_from("<15f", p, 8)
    if len(p) != 68 + 8 * n_h:
        raise LogError("placement record length %d does not match its %d horizon samples" % (len(p), n_h))
    hz = struct.unpack_from("<%df" % (2 * n_h), p, 68)
    meas = {
        "f_px": _num(f[0]), "baseline": _num(f[1]), "h_cam": _num(f[2]),
        "tilt": [_num(f[3]), _num(f[4])], "tilt_reads": tilt_reads, "flag_found": bool(flags & 2),
        "flag_bearing": _num(f[5]), "flag_disparity": _num(f[6]), "flag_low_elev": _num(f[7]),
        "flag_base_visible": bool(flags & 4), "flag_top_visible": bool(flags & 8),
        "flag_top_elev": _num(f[8]), "stick_height_est": _num(f[9]),
        "stick_height_rel_sigma": _num(f[10]),
        "horizon_az": [_num(v) for v in hz[0::2]], "horizon_elev": [_num(v) for v in hz[1::2]],
        "grain_kappa": _num(f[11]), "grain_azimuth": _num(f[12]), "stimp_ft": _num(f[13]),
        "user_distance": _num(f[14]),
    }
    return {"read_id": read_id, "drop": drop, "n_drops": n_drops, "is_ball": bool(flags & 1),
            "measurements": meas}


def dec_read(p):
    if len(p) != 684 or p[0] != LAYOUT:
        raise LogError("read record of an unknown layout or length (%d, %d bytes)" % (p[0] if p else -1, len(p)))
    flags = struct.unpack_from("<H", p, 14)[0]
    fwv = struct.unpack_from("<H", p, 12)[0]
    settings = dict(zip(("version", "stimp_x2", "units", "past_cm", "grass", "grain_enable", "raw_log_level",
                         "method", "manual_distance_cm", "surface", "tilt_log"),
                        struct.unpack_from("<BBBBBBBBHBB", p, 40)))
    stage = struct.unpack_from("<5H", p, 236)
    grain_ran = bool(flags & 32)
    ctx = {
        "hw_rev": p[1], "read_id": struct.unpack_from("<H", p, 2)[0],
        "rtc_s": struct.unpack_from("<I", p, 4)[0], "tick_ms": struct.unpack_from("<I", p, 8)[0],
        "fw_version": "%d.%d" % (fwv >> 8, fwv & 0xFF), "fw_build": struct.unpack_from("<I", p, 16)[0],
        "solver_version": "0x%08X" % struct.unpack_from("<I", p, 20)[0], "cal_version": p[24],
        "cal_flags": dict(zip(("tilt", "cam_l", "cam_r", "grain", "device"), p[25:30])),
        "cal_crc": dict(zip(("tilt", "cam_l", "cam_r", "grain", "device"),
                            ["0x%04X" % v for v in struct.unpack_from("<5H", p, 30)])),
        "settings": settings,
        "n_drops": p[52], "ball_index": p[53], "solver_ret": p[54], "tier": p[55], "base": p[56],
        "seat": {0: "base", 1: "ball"}.get(p[57], "none"), "note": p[58], "groups_ok": p[59],
        "precision": bool(flags & 1), "survey": bool(flags & 2), "flag_found": bool(flags & 4),
        "ambiguous": bool(flags & 8), "top_valid": bool(flags & 16), "grain_ran": grain_ran,
        "grain_valid": bool(flags & 64), "line_here": bool(flags & 128), "cameras_off": bool(flags & 256),
        "solid_line": bool(flags & 512),
        "tilt": {
            "slope_raw": _f(p, 60, 2), "slope": _f(p, 68, 2), "zero": _f(p, 76, 2),
            "spin_slope_raw": _f(p, 84, 2), "reread_slope_raw": _f(p, 92, 2), "view_yaw_rad": _f(p, 100),
            "up": _f(p, 104, 3), "gyro_bias": _f(p, 116, 3), "scatter": _f(p, 128),
            "accel_noise_g": _f(p, 132), "blocks": p[234],
        },
        "temperatures": {"imu_c": struct.unpack_from("<h", p, 136)[0] / 100.0,
                         "cell_c": _t10(struct.unpack_from("<h", p, 138)[0]),
                         "mcu_c": _t10(struct.unpack_from("<h", p, 140)[0])},
        "battery_mv": struct.unpack_from("<H", p, 142)[0],
        "grain": ({"red_modulation": _f(p, 144), "red_azimuth": _f(p, 148), "nir_modulation": _f(p, 152),
                   "nir_azimuth": _f(p, 156), "reject": p[233],
                   "signal": list(struct.unpack_from("<16H", p, 160))} if grain_ran else None),
        "vision": {"bearing": _f(p, 192), "disparity_px": _f(p, 196), "disparity_sigma_px": _f(p, 200),
                   "base_elev": _f(p, 204), "top_elev": _f(p, 208), "diag_range_m": _f(p, 212),
                   "diag_range_sigma_m": _f(p, 216), "stick_height_m": _f(p, 220),
                   "stick_height_sigma_m": _f(p, 224), "rows_used_pct": p[228], "line_contrast": p[229],
                   "sharp_match_pct": p[230], "saturation_pct": p[231], "sun": bool(p[232])},
        "timing_ms": dict({k: (None if v == 0xFFFF else v) for k, v in zip(STAGES, stage)},
                          camera_rail_on=struct.unpack_from("<H", p, 246)[0]),
        "shown": {"aim_rad": _f(p, 248), "confidence": _f(p, 252), "display_rot_rad": _f(p, 256)},
    }
    o = struct.unpack_from("<5fIHHBB", p, 264)
    options = {"past": _num(o[0]), "tol_miss": _num(o[1]), "tol_pace": _num(o[2]), "lm_tol": _num(o[3]),
               "near_miss": _num(o[4]), "max_steps": o[5], "max_rolls": o[6], "lm_max_iter": o[7],
               "method": o[8], "use_grain": bool(o[9])}
    e = struct.unpack_from("<24f", p, 296)
    est = {
        "phi": _num(e[0]), "aim_azimuth_device": _num(e[1]), "v0": _num(e[2]), "plays_like": _num(e[3]),
        "break_m": _num(e[4]), "break_cups": _num(e[5]), "distance": _num(e[6]),
        "distance_sigma": _num(e[7]), "bearing": _num(e[8]), "slope_pct": _num(e[9]),
        "fall_line_azimuth": _num(e[10]), "fall_line_azimuth_device": _num(e[11]), "dz_hole": _num(e[12]),
        "patch": [_num(v) for v in e[13:18]], "cross_slope_sigma": _num(e[18]), "confidence": _num(e[19]),
        "a_r": _num(e[20]), "stimp_ft": _num(e[21]), "grain": [_num(e[22]), _num(e[23])],
        "n_steps": struct.unpack_from("<I", p, 392)[0], "n_rolls": struct.unpack_from("<H", p, 396)[0],
        "aim_source": p[398], "solve_status": p[399], "base_hidden": p[400], "flag_missing": p[401],
        "range_missing": p[402], "poor_horizon": p[403], "fit_converged": p[404],
    }
    c = struct.unpack_from("<25f", p, 432)
    fit = {
        "coeffs": _f(p, 412, 5), "cov": [[_num(c[5 * i + j]) for j in range(5)] for i in range(5)],
        "level_offsets": _f(p, 532, 2), "distance": _f(p, 540), "distance_sigma": _f(p, 544),
        "bearing": _f(p, 548),
        "range": dict(zip(("distance", "sigma", "stereo", "sigma_stereo", "mono", "sigma_mono"), _f(p, 552, 6))),
        "tilt_slopes": _f(p, 576, 2), "cross_sigma_read": _f(p, 584), "stations": _f(p, 588, 4),
        "horizon_rms": _f(p, 604), "cost": _f(p, 608), "cost_first_start": _f(p, 612),
        "n_iter": struct.unpack_from("<H", p, 616)[0], "n_drops": p[618], "n_starts": p[619],
        "base_hidden": p[620], "flag_missing": p[621], "range_missing": p[622], "used_horizon": p[623],
        "poor_horizon": p[624], "converged": p[625],
    }
    return dict(ctx, options=options, estimate=est, fit=fit)


def dec_tilt(p):
    if len(p) != 80 or p[0] != LAYOUT:
        raise LogError("tilt record of an unknown layout or length")
    return {
        "kind": TILT_KIND[p[1]] if p[1] < len(TILT_KIND) else p[1],
        "read_id": struct.unpack_from("<H", p, 2)[0], "rtc_s": struct.unpack_from("<I", p, 4)[0],
        "tick_ms": struct.unpack_from("<I", p, 8)[0], "slope_raw": _f(p, 12, 2), "slope": _f(p, 20, 2),
        "accel_g": _f(p, 28, 3), "gyro_bias": _f(p, 40, 3), "scatter": _f(p, 52),
        "accel_noise_g": _f(p, 56), "yaw_rad": _f(p, 60),
        "imu_temp_c": struct.unpack_from("<h", p, 64)[0] / 100.0,
        "cell_temp_c": _t10(struct.unpack_from("<h", p, 66)[0]),
        "mcu_temp_c": _t10(struct.unpack_from("<h", p, 68)[0]),
        "battery_mv": struct.unpack_from("<H", p, 70)[0],
        "cal_tilt_crc": "0x%04X" % struct.unpack_from("<H", p, 72)[0], "cal_tilt_flags": p[74],
        "blocks": p[75], "seat": {0: "base", 1: "ball"}.get(p[76], "none"),
    }


def dec_summary(p):
    f = struct.unpack_from("<IHBBhH13f8B", p, 0)
    keys = ("rtc_s", "read_id", "flags", "drop_index", "temp_c_x100", "batt_mv", "slope_x", "slope_y",
            "bearing_rad", "disparity_px", "disparity_sigma_px", "base_elev_rad", "top_elev_rad", "range_m",
            "range_sigma_m", "stick_height_m", "aim_rad", "v0_mps", "aim_offset_m", "stimp_x2",
            "confidence_pct", "solver_status", "rows_used_pct", "line_contrast", "sharp_match_pct",
            "saturation_pct", "n_repeats")
    return {k: (_num(v) if isinstance(v, float) else v) for k, v in zip(keys, f)}


def dec_event(p):
    rtc, code, arg = struct.unpack_from("<IHi", p, 0)
    return {"rtc_s": rtc, "code": code, "name": EVENT_NAME.get(code, "?"), "arg": arg}


def dec_raw_chunk(p):
    f = struct.unpack_from("<HBBBBHHHHI", p, 0)
    keys = ("read_id", "camera", "kind", "frame_index", "reserved", "x0", "y0", "width", "height", "offset")
    return dict(zip(keys, f), pixel_bytes=len(p) - 18)


DECODERS = {1: dec_summary, 2: dec_raw_chunk, 3: dec_event, 5: dec_placement, 6: dec_read, 7: dec_tilt}


def decode(stream):
    """The whole dump: {"records": [...], "reads": [...]}.

    "records" is every record in log order with its sequence number.
    "reads" joins each read record with the placements logged in front of it
    (same read_id): the form greenline_sim.replay takes - drops, ball_index,
    method, past, use_grain, near_miss, estimate - plus everything else the
    read record holds.
    """
    records, reads, pending = [], [], {}
    for typ, flags, seq, payload in split(stream):
        name = REC_NAME.get(typ, "type_%d" % typ)
        dec = DECODERS.get(typ)
        body = dec(payload) if dec else {"bytes": len(payload)}
        records.append({"seq": seq, "type": name, "data": body})
        if typ == 5:
            pending.setdefault(body["read_id"], []).append(body)
        elif typ == 6:
            drops = sorted(pending.pop(body["read_id"], []), key=lambda d: d["drop"])
            complete = len(drops) == body["n_drops"] and [d["drop"] for d in drops] == list(range(len(drops)))
            read = dict(body)
            read.update({
                "seq": seq, "replayable": complete and body["solver_ret"] == 0,
                "drops": [d["measurements"] for d in drops], "ball_index": body["ball_index"],
                "method": body["options"]["method"], "past": body["options"]["past"],
                "use_grain": body["options"]["use_grain"], "near_miss": body["options"]["near_miss"],
            })
            reads.append(read)
    return {"layout": LAYOUT, "records": records, "reads": reads,
            "unsolved_placements": sum(len(v) for v in pending.values())}
