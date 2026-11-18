#!/usr/bin/env python3
"""`make tooltest`: glctl against the HOST SIMULATOR build of the firmware.

Every protocol command goes through tools/glctl (its Device class and, for a
few, its command line) to build/host/glsim - the whole firmware on the
simulated board - and is checked.  Then:

  * the log is downloaded (once whole, once cut and RESUMED), decoded, and
    the decoded reads are compared with what the firmware itself held when it
    showed each result (the simulator prints its estimator records);
  * THE REPLAY: the Python reference estimator (sim/greenline_sim) is run on
    every logged measurement record and its estimate compared with the
    estimate the firmware logged;
  * the image stamping tool against the boot stub's own image check;
  * the release gate (a release build fails while the USB ids are placeholders).

Nothing here touches hardware: there is none.  Currents are the supply
MODEL's.  Exit status 0 only if every check passed.
"""
import json
import math
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from glctl import logdec, proto, replay  # noqa: E402
from glctl.device import Device  # noqa: E402
from glctl.proto import DeviceError  # noqa: E402
from glctl.transport import SimTransport  # noqa: E402

FW = os.path.normpath(os.path.join(HERE, "..", ".."))
DEG = math.pi / 180.0
checks = 0
failed = []


def check(cond, what):
    global checks
    checks += 1
    if not cond:
        failed.append(what)
        print("    FAIL: %s" % what)
    return cond


def near(a, b, tol, what):
    return check(a is not None and b is not None and abs(a - b) <= tol, "%s: %r vs %r (tolerance %g)" % (what, a, b, tol))


def refused(fn, status, what):
    try:
        fn()
    except DeviceError as exc:
        return check(exc.status_name == status, "%s: refused with %s, expected %s" % (what, exc.status_name, status))
    return check(False, "%s: was not refused" % what)


def section(title):
    print("== %s" % title)


# ---------------------------------------------------------------------------------------
def make_reads(t, dev):
    """Reads for the log: a Quick Read, another distance and slope, a read whose right
    camera is blind at 3 m (no range: a FALLBACK), a tilt-only read (cameras off: a
    FALLBACK).  Returns what the firmware held at each result, by read id."""
    truth = {}

    def place(label):
        r = t.world("place")
        check(r["state"] == "SHOW_RESULT", "%s: the read ended in %s" % (label, r["state"]))
        if r["state"] == "SHOW_RESULT":
            truth[r["read_id"]] = dict(r, label=label)
        return r

    t.world("undock")
    place("quick read, 6 m")
    for k, v in (("dist", 4.0), ("bearing", -0.08), ("slope_x", -0.015), ("slope_y", 0.010)):
        t.world("set %s %g" % (k, v))
    place("quick read, 4 m")
    t.world("set dist 3")
    t.world("set right_blind 1")
    r = place("right camera blind at 3 m")
    check(r.get("estimate", {}).get("range_missing") == 1, "the blind-camera read is a range-missing fallback")
    t.world("set right_blind 0")
    # A SURVEY in the order of DESIGN_SPEC E29 (phase-3 review, factory finding 5: no test
    # or demonstration decoded a Survey from the log): 3 m from the hole, 6 m, then the
    # ball at 8 m.  The read at 3 m is its first placement; two double taps start it.
    for k, v in (("dist", 3.0), ("bearing", -0.02), ("slope_x", -0.006), ("slope_y", -0.014)):
        t.world("set %s %g" % (k, v))
    t.world("run 50000")
    place("quick read, 3 m (first placement of the Survey)")
    t.world("doubletap")
    w = t.world("doubletap")
    check(w["state"] == "SURVEY_NEXT_DROP", "two double taps on a result start a Survey (%s)" % w["state"])
    for k, v in (("dist", 6.0), ("bearing", 0.03), ("slope_x", 0.010), ("slope_y", -0.020)):
        t.world("set %s %g" % (k, v))
    r = place("Survey, 2 placements: 3 m, the ball at 6 m")
    check(r.get("n_drops") == 2 and r.get("ball_index") == 1, "Survey of 2: the ball is the LAST placement")
    for k, v in (("dist", 8.0), ("bearing", 0.01), ("slope_x", 0.012), ("slope_y", -0.016)):
        t.world("set %s %g" % (k, v))
    r = place("Survey, 3 placements: 3 m, 6 m, the ball at 8 m")
    check(r.get("n_drops") == 3 and r.get("ball_index") == 2, "Survey of 3: the ball is the LAST placement")
    # back to the scene the tilt-only read below has always had
    for k, v in (("dist", 6.0), ("bearing", -0.08), ("slope_x", -0.015), ("slope_y", 0.010)):
        t.world("set %s %g" % (k, v))
    t.world("run 130000")
    t.world("dock")
    s = dev.set_settings(tilt_log=2)
    check(s["tilt_log"] == 2 and s["version"] == 3, "SET_SETTINGS tilt_log = ONLY (settings version 3)")
    t.world("undock")
    rail = t.world("state")["rail_cycles"]
    r = place("tilt only (cameras off)")
    check(r["rail_cycles"] == rail, "tilt-only read: no camera was powered")
    check(r.get("estimate", {}).get("flag_missing") == 1, "the tilt-only read is a flag-missing fallback")
    t.world("run 60000")
    t.world("dock")
    dev.set_settings(tilt_log=0)
    return truth


def test_log_and_replay(t, dev, out_dir, truth):
    section("field log: download, resume, decode, cross-check, replay")
    info = dev.log_info()
    full = dev.log_download()
    check(len(full) > 4000 and info["newest_seq"] > 10, "LOG_INFO / LOG_READ: %d bytes, newest record %d"
          % (len(full), info["newest_seq"]))
    again = dev.log_download()
    check(again == full, "the log downloaded twice is identical")
    # a download that broke in the middle of a record: resume after the last complete one
    cut = full[:int(len(full) * 0.6)]
    last, good = logdec.last_seq(cut)
    check(last is not None and good < len(cut), "the cut dump ends inside a record (after record %r)" % last)
    rest = dev.log_download(resume_after=last)
    check(cut[:good] + rest == full, "LOG_SEEK: the resumed download completes the cut one, byte for byte")
    check(dev.log_download(resume_after=info["newest_seq"] + 5) == b"", "LOG_SEEK beyond the newest record: nothing")
    # A DOWNLOAD THAT REALLY BREAKS (phase-3 review, factory finding 8): the link fails at
    # the 4th LOG_READ.  The tool used to write its file only after a complete download:
    # nothing was written, and --resume failed with FileNotFoundError.

    class Flaky:
        """The transport, failing once at the n-th LOG_READ frame it is asked to send."""
        def __init__(self, inner, fail_at):
            self.inner, self.fail_at, self.n = inner, fail_at, 0

        def write(self, data):
            if len(data) > 5 and data[5] == proto.CMD["LOG_READ"]:
                self.n += 1
                if self.n == self.fail_at:
                    raise proto.ProtocolError("link lost (injected)")
            self.inner.write(data)

        def read(self, wait_s):
            return self.inner.read(wait_s)

    path = os.path.join(out_dir, "log_broken.bin")
    if os.path.exists(path):
        os.remove(path)
    broken = Device(Flaky(t, 4))
    broken.seq = 40
    try:
        broken.log_download_to(path)
        check(False, "the injected link fault was not seen")
    except proto.ProtocolError:
        pass
    part = open(path, "rb").read() if os.path.exists(path) else b""
    check(0 < len(part) < len(full) and full.startswith(part) and logdec.last_seq(part)[1] == len(part),
          "link lost at the 4th LOG_READ: %d of %d bytes are in the file, ending at a record boundary"
          % (len(part), len(full)))
    res = dev.log_download_to(path, resume=True)
    check(open(path, "rb").read() == full and res["new_bytes"] == len(full) - len(part),
          "log-download --resume completes that file, byte for byte (%d new bytes)" % res["new_bytes"])
    # a file that was cut inside a record (copied half): resume cuts it back and completes it
    with open(path, "wb") as fh:
        fh.write(cut)
    dev.log_download_to(path, resume=True)
    check(open(path, "rb").read() == full, "--resume of a file cut inside a record completes it too")
    # THE FIRMWARE'S SIDE: a download position belongs to its session.  LOG_SEEK, then the
    # marker leaves the cradle and comes back; LOG_READ "continue" without a new LOG_SEEK
    # starts at the oldest record (it returned 2990 of 5162 bytes: the old seek persisted)
    dev.cmd("LOG_SEEK", struct.pack("<I", last + 1))
    t.world("undock")
    t.world("run 2000")
    t.world("dock")
    out, more = bytearray(), 1
    while more:
        d = dev.cmd("LOG_READ", b"\0", timeout=5.0)
        more = d[0]
        out += d[1:]
    check(bytes(out).startswith(full) and logdec.last_seq(bytes(out))[1] == len(out),
          "LOG_READ \"continue\" in a new session, with no LOG_SEEK: the whole log from its oldest "
          "record (%d bytes, %d of them the log as it was)" % (len(out), len(full)))
    refused(lambda: dev.cmd("LOG_SEEK", b"\0\0\0"), "PARAM", "LOG_SEEK with 3 bytes")

    with open(os.path.join(out_dir, "log.bin"), "wb") as fh:
        fh.write(full)
    decoded = logdec.decode(full)
    with open(os.path.join(out_dir, "log.json"), "w", encoding="utf-8") as fh:
        json.dump(decoded, fh, indent=1)
    kinds = {}
    for rec in decoded["records"]:
        kinds[rec["type"]] = kinds.get(rec["type"], 0) + 1
    print("    %d bytes, %d records: %s" % (len(full), len(decoded["records"]),
                                             ", ".join("%d %s" % (v, k) for k, v in sorted(kinds.items()))))
    n_placements = sum(tr["n_drops"] for tr in truth.values())
    check(kinds.get("read", 0) == len(truth) and kinds.get("placement", 0) == n_placements,
          "one read record per result (%d) and one placement record per placement handed to the "
          "estimator (%d)" % (len(truth), n_placements))
    surveys = [r for r in decoded["reads"] if r["survey"]]
    check(sorted((r["n_drops"], r["ball_index"]) for r in surveys) == [(2, 1), (3, 2)],
          "the log holds the Survey reads of 2 and of 3 placements, the ball last")
    check(kinds.get("tilt", 0) == 1, "one tilt record (the tilt-only placement)")
    seqs = [r["seq"] for r in decoded["records"]]
    check(seqs == sorted(seqs) and len(set(seqs)) == len(seqs), "sequence numbers ascending, none twice")

    # the decoder against the firmware's own values (the simulator printed them at each result)
    worst = 0.0
    for read in decoded["reads"]:
        tr = truth.get(read["read_id"])
        if not check(tr is not None, "read %d of the log was a result of this session" % read["read_id"]):
            continue
        check(read["replayable"], "read %d is replayable" % read["read_id"])
        check(read["n_drops"] == tr["n_drops"] and read["ball_index"] == tr["ball_index"], "placements of read %d"
              % read["read_id"])
        for drop, ref in zip(read["drops"], tr["drops"]):
            for key, want in ref.items():
                got = drop[key]
                pairs = zip(got, want) if isinstance(want, list) else [(got, want)]
                for g, w in pairs:
                    if isinstance(w, bool) or w is None or g is None:
                        check(g == w, "read %d %s: %r, firmware %r" % (read["read_id"], key, g, w))
                    else:
                        d = abs(g - w) / max(1e-12, abs(w)) if w else abs(g)
                        worst = max(worst, d)
                        check(d < 5e-8, "read %d %s: %r, firmware %r" % (read["read_id"], key, g, w))
        # ... the placement records carry the ball flag on the ball's record and no other
        ball_flags = [rec["data"]["is_ball"] for rec in decoded["records"]
                      if rec["type"] == "placement" and rec["data"]["read_id"] == read["read_id"]]
        check(ball_flags == [i == tr["ball_index"] for i in range(tr["n_drops"])],
              "read %d: ball flag on placement %d only (%r)" % (read["read_id"], tr["ball_index"], ball_flags))
        # ... and the OPTIONS of the call, field by field (seed S15: near_miss read from the
        # wrong field passed every check)
        for key, w in tr["options"].items():
            g = read["options"][key]
            if isinstance(w, (bool, int)):
                check(g == w, "read %d option %s: %r, firmware %r" % (read["read_id"], key, g, w))
            else:
                check(g is not None and abs(g - w) <= 5e-8 * max(1e-12, abs(w)),
                      "read %d option %s: %r, firmware %r" % (read["read_id"], key, g, w))
        check(len({read["options"][k] for k in ("past", "tol_miss", "tol_pace", "lm_tol", "near_miss")}) == 5,
              "read %d: the five real options have five different values (a mixed-up field shows)"
              % read["read_id"])
        for key, w in tr["estimate"].items():
            g = read["estimate"][key]
            if w is None or g is None or isinstance(w, int) and key not in ("phi",):
                check(g == w or (isinstance(w, float) and abs(g - w) < 1e-12), "read %d estimate %s: %r, firmware %r"
                      % (read["read_id"], key, g, w))
            else:
                d = abs(g - w) / max(1e-12, abs(w)) if w else abs(g)
                worst = max(worst, d)
                check(d < 5e-8, "read %d estimate %s: %r, firmware %r" % (read["read_id"], key, g, w))
        tm = read["timing_ms"]
        order = [tm[k] for k in ("tilt_done", "camera_on", "capture_done", "solve_start", "solve_done")
                 if tm[k] is not None]
        check(order == sorted(order), "read %d: stage times in order %r" % (read["read_id"], tm))
        check(read["fw_version"] == "0.3" and read["cal_version"] == 2 and read["settings"]["version"] == 3,
              "read %d: firmware, calibration and settings versions" % read["read_id"])
    print("    decoded placements and estimates against the firmware's own values: largest relative "
          "difference %.1e (9 printed digits)" % worst)
    tilt = [r["data"] for r in decoded["records"] if r["type"] == "tilt"]
    if tilt:
        check(tilt[0]["kind"] == "placement" and tilt[0]["blocks"] == 8, "the tilt record: a placement of 8 blocks")
        near(tilt[0]["slope_raw"][0], -0.015, 0.0006, "tilt record slope x")
        near(tilt[0]["imu_temp_c"], 22.0, 0.05, "tilt record temperature")

    # THE REPLAY
    section("replay: the Python reference estimator on the logged measurement records")
    n, bad, rows = replay.replay_log(decoded)
    check(n == len(truth) and bad == 0, "every logged read replays to the estimate the firmware logged")
    fallbacks = [r for r in decoded["reads"] if r["estimate"]["flag_missing"] or r["estimate"]["range_missing"]]
    check(len(fallbacks) >= 2, "the replayed reads include fallbacks (%d)" % len(fallbacks))
    # a logged estimate that is wrong IS found: turn one aim by 2 mrad and replay again
    tampered = json.loads(json.dumps(decoded))
    tampered["reads"] = tampered["reads"][:1]
    tampered["reads"][0]["estimate"]["aim_azimuth_device"] += 0.002

    class Sink:
        def write(self, _):
            pass
    n2, bad2, _ = replay.replay_log(tampered, out=Sink())
    check(n2 == 1 and bad2 == 1, "a logged aim that is 2 mrad off is reported by the replay")
    return decoded


def test_commands(t, dev, out_dir):
    section("identity, negotiation, status")
    ident = dev.negotiate()
    check(ident["proto_version"] == 3 and ident["agreed_version"] == 3 and ident["model"] == "GL-1" and
          ident["hw_rev"] == 5 and ident["hw_letter"] == "E", "GET_IDENT: GL-1 rev E, protocol 3")
    check(len(ident["commands"]) == 35 and "SERIAL" in ident["commands"], "35 commands in the bit map")
    check(not ident["release_build"] and not ident["calibration_complete"], "placeholder USB ids, not calibrated")
    old = Device(t, host_version=2)
    old.seq = 100
    check(old.negotiate()["agreed_version"] == 2, "a host of protocol 2 is told: version 2")
    check(dev.ping() and dev.info()["proto_version"] == 3, "PING, GET_INFO")
    st = dev.status()
    check(st["vbus"] and not st["unlocked"], "GET_STATUS: in the cradle, locked")
    sn = dev.sensors()
    near(sn["cell_temp_c"], 22.0, 0.3, "GET_SENSORS NTC2")
    near(sn["rail_2v8_mv"], 2800, 5, "GET_SENSORS 2.8 V rail")
    near(sn["battery_mv"], 3900, 60, "GET_SENSORS cell")
    check(dev.power()["cradle"] == "link", "GET_POWER: cradle link")
    check(dev.serial()["text"] == ident["serial_text"] and len(ident["serial_text"]) == 7, "SERIAL (read)")

    section("the unlock rule")
    refused(lambda: dev.ship_mode(True), "STATE", "SHIP_MODE while locked")
    refused(lambda: dev.display_rot(0.01), "STATE", "DISPLAY_ROT write while locked")
    refused(lambda: dev.level_zero("arm", "base"), "STATE", "LEVEL_ZERO arm while locked")
    refused(lambda: dev.serial(commit=True), "STATE", "SERIAL commit while locked")
    refused(lambda: dev.reboot(loader=True), "STATE", "update loader while locked")
    refused(lambda: dev.cmd("UNLOCK", b"nope"), "PARAM", "UNLOCK with a wrong word")
    dev.unlock()
    check(dev.status()["unlocked"], "UNLOCK")

    section("cameras")
    t.world("set scene 3")
    for cam in (0, 1):
        check(dev.cam_id(cam) == {"camera": cam, "product_id": "0x7692", "as_expected": True}, "CAM_ID %d" % cam)
    info, px = dev.picture(1, 0, 192, 640, 96)
    ok = all(px[r * 640 + c] == (c + 3 * (192 + r) + 101) & 0xFF for r in range(0, 96, 5) for c in range(0, 640, 7))
    check(info["bytes"] == 61440 and ok, "CAM_CAPTURE + CAM_DATA: a band of the right camera, pixel for pixel")
    part = dev.cam_data(20000)               # a download that stopped ...
    whole = dev.cam_data(61440, start=20000, have=part)   # ... and was resumed at its offset
    check(whole == px, "CAM_DATA resumed at an offset")
    finfo, frame = dev.frame(0)
    ok = all(frame[r * 640 + c] == (c + 3 * r) & 0xFF for r in range(0, 480, 13) for c in range(0, 640, 11))
    check(len(frame) == 307200 and ok, "a whole frame of the left camera (two exposures of 640 x 240)")
    refused(lambda: dev.capture(0, 0, 0, 640, 480), "PARAM", "a 640 x 480 capture (more than the image memory)")
    refused(lambda: dev.cam_id(2), "PARAM", "CAM_ID 2")
    t.world("set scene 1")
    left, _ = dev.picture(0, 0, 96, 640, 288, dark=True)
    right, _ = dev.picture(1, 0, 96, 640, 288, dark=True)
    check(left["bright_pixels"] == 72 and right["bright_pixels"] == 0 and left["max"] == 90,
          "dark frames: the leak in the left camera is counted (72 pixels), none in the right")
    t.world("set scene 2")
    f = dev.cam_field(0)
    check(f["row_upper"] == 88 and f["row_lower"] == 391 and f["ratio"] == 1.0, "CAM_FIELD: bars at +-13.0 deg, ratio 1")
    t.world("set upper 135")
    near(dev.cam_field(1)["ratio"], 0.75, 0.001, "CAM_FIELD: an upper bar 25 % darker")
    t.world("set scene 0")
    with open(os.path.join(out_dir, "band.pgm"), "wb") as fh:
        fh.write(b"P5\n640 96\n255\n" + px)

    section("display")
    for name, black in (("white", 0), ("black", 16384), ("checker1", 8192), ("checker8", 8192),
                        ("rows", 8192), ("columns", 8192)):
        d = dev.display_test(name, 20)
        check(d["black_pixels"] == black, "DISPLAY_TEST %s: %d black pixels" % (name, d["black_pixels"]))
    check(t.world("state")["black_pixels"] == 8192, "the frame buffer holds the pattern")
    raw = dev.display_test("ref-raw", 20)
    check(300 < raw["black_pixels"] < 420, "the reference line: %d pixels" % raw["black_pixels"])
    check(not dev.display_rot()["measured"], "DISPLAY_ROT: nothing stored")
    r = dev.display_rot(1.2 * DEG)
    near(r["rotation_rad"], 1.2 * DEG, 1e-8, "DISPLAY_ROT write 1.2 deg")
    cor = dev.display_test("ref-corrected", 20)
    check(cor["frame_crc32"] != raw["frame_crc32"], "the corrected reference line is another picture")
    refused(lambda: dev.display_rot(3.0 * DEG), "RANGE", "DISPLAY_ROT 3 deg")
    refused(lambda: dev.cmd("DISPLAY_TEST", bytes([10, 5])), "PARAM", "DISPLAY_TEST pattern 10")
    dev.display_test("normal")

    section("grain LEDs and photodiode")
    g = dev.grain_test("dark")
    check(g["cycle_status"] == "EMPTY" and g["dark_max"] - g["dark_min"] < 40, "GRAIN_TEST dark: offset %d counts"
          % g["dark_mean"])
    g = dev.grain_test("cycle")
    check(len(g["leds"]) == 16, "GRAIN_TEST cycle: 16 LEDs")
    g = dev.grain_test("store")
    check(g["stored_dark"] == g["dark_mean"] or abs(g["stored_dark"] - g["dark_mean"]) < 40, "GRAIN_TEST store")
    refused(lambda: dev.cmd("GRAIN_TEST", b"\x07"), "PARAM", "GRAIN_TEST mode 7")

    section("six-face, temperature fit, horizon, grain floor, serial, records")
    for face in range(6):
        t.world("set face %d" % face)
        t.world("run 600")
        dev.ping()
        st = dev.six_face(face, wait=lambda s: t.world("run %d" % int(1000 * s)))
        check(st["done_mask"] == (1 << (face + 1)) - 1, "six-face: face %d captured (mask 0x%02X)" % (face, st["done_mask"]))
        dev.ping()
    st = dev.six_face_solve()
    check(st["tilt_cal_flags"] & 1 and st["done_mask"] == 0, "six-face solved and stored")
    t.world("set face -1")
    pts = [(tc, 0.012 + 2e-4 * (tc - 23), -0.007 - 1e-4 * (tc - 23), 0.020 + 3e-4 * (tc - 23))
           for tc in (-10, 0, 10, 23, 35, 50)]
    before = struct.unpack_from("<3f", dev.get_cal("tilt"), 2)
    fit = dev.tilt_tempco(pts, t0=23.0)
    near(fit["b1_g_per_k"][0], 2e-4, 2e-7, "TILT_TEMPCO b1 x")
    near(fit["b1_g_per_k"][2], 3e-4, 2e-7, "TILT_TEMPCO b1 z")
    check(fit["rms_residual_g"] < 1e-6 and fit["max_residual_g"] < 3e-6, "TILT_TEMPCO residuals (RMS and largest)")
    rec = dev.get_cal("tilt")
    check(struct.unpack_from("<3f", rec, 2) == before and abs(before[0] - 0.012) < 0.0005 and rec[1] & 0x09 == 0x09,
          "TILT_TEMPCO keeps the six-face offsets (%.4f, %.4f, %.4f) g and sets its flag" % before)
    # pure DRIFT (what a 0 / 180 degree pair per chamber stop gives; z not measured): the same
    drift = [(tc, 2e-4 * (tc - 23), -1e-4 * (tc - 23), 0.0) for tc in (0, 12, 23, 34, 45)]
    fit = dev.tilt_tempco(drift, t0=23.0)
    near(fit["b1_g_per_k"][1], -1e-4, 2e-7, "TILT_TEMPCO with drift points: b1 y")
    check(struct.unpack_from("<3f", dev.get_cal("tilt"), 2) == before,
          "TILT_TEMPCO with drift points: the six-face offsets are still there")
    fit = dev.tilt_tempco(pts, t0=23.0)
    refused(lambda: dev.tilt_tempco(pts[:2]), "PARAM", "TILT_TEMPCO with 2 points")
    refused(lambda: dev.tilt_tempco(pts[:4]), "PARAM", "TILT_TEMPCO with 4 points (at least 5)")
    refused(lambda: dev.tilt_tempco([(tc, 0.0, 0.0, 0.0) for tc in (15, 19, 23, 27, 31)]), "PARAM",
            "TILT_TEMPCO over a span of 16 K (at least 30)")
    refused(lambda: dev.tilt_tempco(pts, t0=30.0), "RANGE", "TILT_TEMPCO with a t0 that is not the record's")
    near(dev.set_cam_horizon(1, 247.25)["pitch_up_rad"], math.atan(7.75 / 657.0), 1e-6, "SET_CAM_HORIZON")
    refused(lambda: dev.set_cam_horizon(0, 400.0), "RANGE", "SET_CAM_HORIZON row 400")
    mods = [0.02 + 0.002 * ((i * 37) % 50) for i in range(50)]
    fl = dev.set_grain_floor(mods)
    near(fl["threshold"], sorted(mods)[47], 1e-6, "SET_GRAIN_FLOOR threshold (95th percentile)")
    refused(lambda: dev.set_grain_floor(mods[:10]), "PARAM", "SET_GRAIN_FLOOR with 10 readings")
    s = dev.serial(commit=True)
    check(s["stored_for_this_processor"], "SERIAL commit")
    ident = dev.negotiate()
    check(ident["serial_is_stored"] and ident["serial_matches_this_processor"] and
          ident["serial_stored"] == ident["serial"], "GET_IDENT: the serial is stored and is this processor's")
    sizes = {"tilt": 120, "cam_l": 52, "cam_r": 52, "grain": 82, "device": 28}
    for name, size in sizes.items():
        blob = dev.get_cal(name)
        check(len(blob) == size and blob[0] == 2 and proto.crc16(blob[:-2]) == struct.unpack("<H", blob[-2:])[0],
              "GET_CAL %s: %d bytes, version 2, CRC right" % (name, size))
        dev.set_cal(name, blob)
        bad = bytearray(blob)
        bad[3] ^= 0x40
        refused(lambda: dev.set_cal(name, bad), "CRC", "SET_CAL %s with a changed byte" % name)
    check(dev.get_cal("cam_r")[1] & 4, "the horizon flag is in the right camera's record")

    section("the level zero, armed over USB, run on the seat plate")
    for seat, bx, by, turn in (("base", 0.0035, -0.0025, 180.0), ("ball", 0.0047, -0.0033, -176.0)):
        dev.unlock()
        z = dev.level_zero("arm", seat)
        check(z["state"] == "ARMED" and z["seat"] == seat, "LEVEL_ZERO arm %s" % seat)
        # the unit carries the six-face calibration made above (offsets 12 and -7 mg at 23 C):
        # what the IMU reads wrong on the seat is that offset plus the seat's own error
        t.world("set stick 0")
        t.world("set temp 23")
        t.world("set bias_x %g" % (0.012 + bx))
        t.world("set bias_y %g" % (-0.007 + by))
        t.world("undock")
        w = t.world("zero %g" % turn)
        check(w["zero_state"] == 3, "the armed zeroing ran by itself on the plate (%s seat)" % seat)
        t.world("run 3000")
        t.world("dock")
        z = dev.level_zero("status")
        check(z["state"] == "DONE" and z["status"] == "OK", "LEVEL_ZERO status: DONE")
        near(z["bias_x"], bx, 0.0004, "%s-seat zero x" % seat)
        near(z["bias_y"], by, 0.0004, "%s-seat zero y" % seat)
        check(0 < z["scatter"] < 0.0005 and abs(abs(z["turn_rad"]) - math.pi) < 0.1, "scatter %.2e, turn %.1f deg"
              % (z["scatter"], z["turn_rad"] / DEG))
        print("    %s seat: zero (%.3f, %.3f) mrad, true (%.3f, %.3f); scatter %.3f mrad; turn %.1f deg"
              % (seat, 1000 * z["bias_x"], 1000 * z["bias_y"], 1000 * bx, 1000 * by, 1000 * z["scatter"],
                 z["turn_rad"] / DEG))
    check(dev.get_cal("tilt")[1] & 0x06 == 0x06, "both zeros are in the tilt record")
    t.world("set stick 1")
    t.world("set temp 22")
    dev.unlock()
    check(dev.level_zero("arm", "ball")["state"] == "ARMED" and dev.level_zero("cancel")["state"] == "IDLE",
          "LEVEL_ZERO arm, cancel")
    z = dev.level_zero("status")
    check("ntc2_temp_c" in z and "rest_min" in z, "LEVEL_ZERO answers 40 bytes: NTC2 and the rest are in it")
    z = dev.level_zero("arm", "ball", rest_min=30)
    check(z["state"] == "ARMED" and z["rest_min"] == 30, "LEVEL_ZERO arm with 30 minutes of rest")
    dev.level_zero("cancel")

    section("the reference line on the seat plate, live streams, lock")
    refused(lambda: (dev.lock(), dev.display_test("ref-raw", 20, plate=True))[1], "STATE",
            "DISPLAY_TEST armed for the seat plate while locked")
    check(not dev.status()["unlocked"], "UNLOCK \"LOCK\": locked, answered OK")
    dev.unlock()
    d = dev.display_test("ref-raw", 20, plate=True)
    t.world("set stick 0")
    t.world("undock")
    w = t.world("state")
    check(w["state"] == "SLEEP", "armed pattern: asleep after leaving the cradle (%s)" % w["state"])
    rail = w["rail_cycles"]
    t.world("place")
    w = t.world("run 5000")
    check(w["state"] == "WAIT_STILL" and w["black_pixels"] == d["black_pixels"] and w["rail_cycles"] == rail,
          "put down out of the cradle: the reference line is on the screen again (%d black pixels), "
          "no camera read" % w["black_pixels"])
    w = t.world("run 17000")
    check(w["state"] == "SLEEP" and w["rail_cycles"] == rail, "after its 20 s: asleep, still no camera read")
    t.world("set stick 1")
    t.world("dock")
    frames = dev.stream(["imu"], period_ms=50, count=8)
    check(len(frames) == 8 and all(f["source"] == "imu" for f in frames), "STREAM imu: 8 frames")
    near(frames[-1]["accel_total_g"], 1.0, 0.03, "STREAM imu: total acceleration at rest (station test 4.5 #12)")
    frames = dev.stream(["grain", "power"], period_ms=200, count=4)
    check({f["source"] for f in frames} == {"grain", "power"} and
          all(len(f["leds"]) == 16 for f in frames if f["source"] == "grain"),
          "STREAM grain + power: the live grain cycle (station test 4.5 #14)")
    check(dev.ping(), "the streams are off again and the unit answers")
    dev.unlock()

    section("the sleep-current test")
    dev.unlock()
    check(dev.sleep_test(timer_s=60) == {"armed": True, "wake_mask": 6}, "SLEEP_TEST timer 60 s (VBUS always wakes)")
    t0 = t.world("state")["t_ms"]
    w = t.world("undock")  # (one pass of the firmware's main loop: it ends asleep, up to 16 s later)
    check(w["sleep_running"] and not w["awake"], "asleep in the test as soon as VBUS has gone")
    w = t.world("run 30000")
    check(w["sleep_running"] and not w["awake"] and w["t_ms"] - t0 < 59000, "still asleep 30 s later")
    w = t.world("run 30000")
    check(not w["sleep_running"] and w["awake"], "the test ended by its timer")
    t.world("run 60000")
    t.world("dock")
    sn = dev.sensors()
    check(sn["sleep_test_woke_by"] == 2 and abs(sn["sleep_test_ms"] - 60000) < 400,
          "GET_SENSORS afterwards: woke by the timer after %d ms" % sn["sleep_test_ms"])
    refused(lambda: dev.sleep_test(timer_s=5), "STATE", "SLEEP_TEST while locked (the cradle was left)")
    dev.unlock()
    dev.sleep_test(timer_s=5)
    check(dev.sleep_test(False, 0) == {"armed": False, "wake_mask": 0}, "SLEEP_TEST off")

    section("charge hold, time, update loader, ship mode")
    dev.set_charge(True)
    check(dev.power()["flags"] & 0x100, "SET_CHARGE stop: the power report says FORCED")
    dev.set_charge(False)
    dev.set_time(1800000000)
    near(dev.status()["rtc_s"], 1800000000, 3, "SET_TIME")
    reboots = t.world("state")["reboots"]
    dev.reboot(loader=True)
    w = t.world("run 200")
    check(w["reboots"] == reboots + 1 and w["last_reboot"] == 1, "REBOOT \"DFU!\": the update loader was requested")
    dev.unlock()
    check(dev.ship_mode(True) and not dev.ship_mode(False) and dev.ship_mode(True), "SHIP_MODE arm, disarm, arm")
    t.world("undock")
    w = t.world("run 3000")
    check(w["halted"], "ship mode entered after the marker left the cradle")
    print("    supply MODEL in ship mode: %.2f uA (requirement 5: NOT MET, builder 1's finding)" % w["load_ua"])
    t.world("dock")
    w = t.world("reset")  # VBUS wakes the MCU through a reset
    check(not w["halted"] and w["vbus"], "VBUS ends ship mode")
    dev.ping()
    check(dev.get_cal("device")[1] == 3, "the calibration survived ship mode and the reset")


def test_cli(glsim, out_dir):
    section("the command line")

    def cli(*args):
        p = subprocess.run([sys.executable, os.path.join(FW, "tools", "glctl")] + list(args),
                           capture_output=True, text=True)
        return p.returncode, p.stdout, p.stderr
    rc, out, _ = cli("--sim", glsim, "ident")
    check(rc == 0 and json.loads(out)["model"] == "GL-1", "glctl --sim ident")
    rc, out, _ = cli("--sim", glsim, "display", "black", "5")
    check(rc == 0 and json.loads(out)["black_pixels"] == 16384, "glctl --sim display black")
    rc, out, _ = cli("--sim", glsim, "display-rot", "--measured", "0.8")
    check(rc == 0 and abs(json.loads(out)["rotation_deg"] + 0.8) < 1e-5,
          "glctl display-rot --measured 0.8: stores -0.8 deg (the line is turned back)")
    rc, _, err = cli("--sim", glsim, "cam-id", "5")
    check(rc == 1 and "PARAM" in err, "a refused command: exit 1 and the status in words")
    rc, _, err = cli("ident")
    check(rc == 2 and "--port" in err, "no transport named: exit 2")
    rc, _, err = cli("--port", "/dev/does-not-exist", "ident")
    try:
        import serial  # noqa: F401
        check(rc == 3 and "cannot open" in err, "a port that does not exist: exit 3")
    except ImportError:
        check(rc == 3 and "pyserial" in err, "without pyserial the serial transport says so (exit 3)")
        print("    pyserial is not installed here: the serial transport is NOT exercised")
    rc, out, _ = cli("log-decode", os.path.join(out_dir, "log.bin"), os.path.join(out_dir, "log_cli.json"))
    check(rc == 0 and json.loads(out)["reads"] >= 4, "glctl log-decode (no unit needed)")
    rc, out, _ = cli("replay", os.path.join(out_dir, "log_cli.json"))
    check(rc == 0 and "do not" in out and " 0 do not" in out, "glctl replay")
    # a dump that was cut at 3000 bytes: decoded up to its last complete record, with a
    # warning (it ended in an uncaught traceback, exit 1 = "the unit refused", nothing decoded)
    whole = open(os.path.join(out_dir, "log.bin"), "rb").read()
    with open(os.path.join(out_dir, "log_trunc.bin"), "wb") as fh:
        fh.write(whole[:3000])
    rc, out, err = cli("log-decode", os.path.join(out_dir, "log_trunc.bin"), os.path.join(out_dir, "log_trunc.json"))
    ok = rc == 0 and "Traceback" not in err and "warning" in err
    n_cut = json.loads(out)["records"] if ok else -1
    check(ok and n_cut >= 5, "glctl log-decode of a dump cut at 3000 bytes: %d complete records decoded, "
          "a warning, exit %d" % (n_cut, rc))
    with open(os.path.join(out_dir, "log_bad.bin"), "wb") as fh:
        fh.write(b"\x06\x00\x10\x00\x01\x00\x00\x00" + b"\x63" * 16)  # a read record of 16 bytes
    rc, _, err = cli("log-decode", os.path.join(out_dir, "log_bad.bin"), os.path.join(out_dir, "log_bad.json"))
    check(rc == 2 and "Traceback" not in err and "not a log dump" in err,
          "glctl log-decode of a record of an unknown layout: exit 2 and a sentence, no traceback")
    rc, out, _ = cli("--sim", glsim, "lock")
    check(rc == 0 and json.loads(out)["unlocked"] is False, "glctl lock")
    rc, out, _ = cli("--sim", glsim, "stream", "imu,tilt", "--count", "4", "--period", "50")
    check(rc == 0 and len(json.loads(out)) == 4, "glctl stream imu,tilt")
    rc, out, _ = cli("--sim", glsim, "capture", "0", "636", "0", "8", "2", os.path.join(out_dir, "edge.pgm"))
    check(rc == 0 and json.loads(out)["x0"] == 600 and json.loads(out)["width"] == 8,
          "glctl capture of an 8-pixel window at x0 636: taken at x0 600 and reported so (it answered IO)")


def test_boot_tools(boot_check, out_dir):
    section("image stamping tool against the boot stub's own check")
    stamp = os.path.join(FW, "tools", "stamp_image.py")
    raw = bytearray((i * 7 + 3) & 0xFF for i in range(20002))
    struct.pack_into("<II", raw, 0, 0x20010000, 0x08002501)
    raw[0x400:0x420] = b"\xff" * 32
    src, img = os.path.join(out_dir, "app_raw.bin"), os.path.join(out_dir, "app.bin")
    with open(src, "wb") as fh:
        fh.write(raw)

    def verdicts(path):
        a = subprocess.run([sys.executable, stamp, "check", path], capture_output=True, text=True)
        b = subprocess.run([boot_check, path], capture_output=True, text=True)
        return a.stdout.split(": ")[-1].strip(), b.stdout.split(": ")[-1].strip(), a.returncode, b.returncode
    p = subprocess.run([sys.executable, stamp, "stamp", src, img, "--fw-version", "0x0003", "--fw-build", "20261113"],
                       capture_output=True, text=True)
    check(p.returncode == 0, "stamp_image.py stamp")
    print("    " + p.stdout.strip())
    check(verdicts(img) == ("OK", "OK", 0, 0), "the stamped image: the tool and the stub's code both say OK")
    check(verdicts(src)[:2] == ("NO_HEADER", "NO_HEADER"), "the unstamped image: NO_HEADER by both")
    good = open(img, "rb").read()
    cases = {"a bit changed in the code": (lambda b: b[:9000] + bytes([b[9000] ^ 1]) + b[9001:], "BAD_CRC"),
             "cut after 12000 bytes": (lambda b: b[:12000], "BAD_LENGTH"),
             "a bit changed in the header": (lambda b: b[:0x408] + bytes([b[0x408] ^ 4]) + b[0x409:], "NO_HEADER"),
             "reset vector outside the image": (lambda b: b[:4] + struct.pack("<I", 0x08000101) + b[8:],
                                                "BAD_VECTORS")}
    for what, (fn, want) in cases.items():
        path = os.path.join(out_dir, "app_bad.bin")
        with open(path, "wb") as fh:
            fh.write(fn(good))
        v = verdicts(path)
        check(v[0] == v[1] == want and v[2] == 1 and v[3] == 1, "%s: %s by both (%r)" % (what, want, v[:2]))
    p = subprocess.run([sys.executable, stamp, "stamp", img, img + ".2", "--fw-version", "3", "--fw-build", "1"],
                       capture_output=True, text=True)
    check(p.returncode == 2 and "blank header slot" in p.stderr, "stamping an image that has a header already is refused")
    for rev, want in ((4, "BAD_HW"),):
        path = os.path.join(out_dir, "app_rev.bin")
        subprocess.run([sys.executable, stamp, "stamp", src, path, "--fw-version", "3", "--fw-build", "1", "--hw-rev",
                        str(rev)], capture_output=True, text=True)
        check(verdicts(path)[:2] == (want, want), "an image stamped for board revision %d: %s by both" % (rev, want))


def test_release_gate(make, out_dir):
    section("release gate: USB ids")
    p = subprocess.run(make.split() + ["-C", FW, "--no-print-directory", "release-gate"], capture_output=True, text=True)
    check(p.returncode != 0 and "REFUSED" in p.stdout, "`make release-gate` fails while the ids are placeholders")
    print("    " + p.stdout.strip().split("\n")[0])
    # phase 3, builder 3: the regulatory text of the INFO screen is a placeholder too
    refused = [ln for ln in p.stdout.split("\n") if "REFUSED" in ln]
    check(len(refused) == 2 and "regulatory text" in refused[1],
          "`make release-gate` also refuses while the regulatory text of the INFO screen is the placeholder")
    if len(refused) > 1:
        print("    " + refused[1].strip())
    for target in ("config-check", "boot-cross"):
        p = subprocess.run(make.split() + ["-C", FW, "--no-print-directory", "RELEASE=1", target],
                           capture_output=True, text=True)
        check(p.returncode != 0 and "REFUSED" in p.stdout,
              "`make RELEASE=1 %s` (the first step of every test and cross build) fails" % target)
    src = "#include \"gl_factory.h\"\n#include \"gl_usb_ids.h\"\nint x;\n"
    p = subprocess.run(["gcc", "-DGL_RELEASE_BUILD", "-I" + os.path.join(FW, "app"), "-I" + os.path.join(FW, "core"),
                        "-fsyntax-only", "-x", "c", "-"], input=src, capture_output=True, text=True)
    check(p.returncode != 0 and "placeholder USB ids" in p.stderr, "a compile with GL_RELEASE_BUILD stops at the #error")
    # with assigned ids (a copy of the header in a scratch directory) the same compile passes
    inc = os.path.join(out_dir, "ids")
    os.makedirs(inc, exist_ok=True)
    text = open(os.path.join(FW, "app", "gl_usb_ids.h"), encoding="utf-8").read()
    text = text.replace("#define GL_USB_VID GL_USB_VID_PLACEHOLDER", "#define GL_USB_VID 0x1209u")
    text = text.replace("#define GL_USB_PID GL_USB_PID_PLACEHOLDER", "#define GL_USB_PID 0x0001u")
    text = text.replace("#define GL_USB_IDS_ARE_PLACEHOLDERS 1", "#define GL_USB_IDS_ARE_PLACEHOLDERS 0")
    with open(os.path.join(inc, "gl_usb_ids.h"), "w", encoding="utf-8") as fh:
        fh.write(text)
    p = subprocess.run(["gcc", "-DGL_RELEASE_BUILD", "-I" + inc, "-fsyntax-only", "-x", "c", "-"],
                       input="#include \"gl_usb_ids.h\"\nint x;\n", capture_output=True, text=True)
    check(p.returncode == 0, "with ids assigned (a scratch copy of the header) the release compile passes")


def main(argv):
    opts = dict(zip(argv[1::2], argv[2::2])) if "--replay-only" not in argv else \
        dict(zip([a for a in argv[1:] if a != "--replay-only"][0::2], [a for a in argv[1:] if a != "--replay-only"][1::2]))
    replay_only = "--replay-only" in argv
    glsim = os.path.abspath(opts.get("--glsim", os.path.join(FW, "build", "host", "glsim")))
    out_dir = os.path.abspath(opts.get("--out", os.path.join(FW, "build", "tooltest")))
    os.makedirs(out_dir, exist_ok=True)

    t = SimTransport(glsim)
    try:
        t.world("dock")
        dev = Device(t)
        dev.negotiate()
        dev.set_time(1795000000)
        section("reads on the simulator (for the log)")
        truth = make_reads(t, dev)
        for rid in sorted(truth):
            e = truth[rid]["estimate"]
            print("    read %d, %s: aim %+.2f mrad, distance %.2f m, source %d%s" % (
                rid, truth[rid]["label"], 1000 * e["aim_azimuth_device"], e["distance"], e["aim_source"],
                ", FALLBACK (%s)" % ("flag missing" if e["flag_missing"] else "range missing")
                if (e["flag_missing"] or e["range_missing"]) else ""))
        test_log_and_replay(t, dev, out_dir, truth)
        if not replay_only:
            test_commands(t, dev, out_dir)
        w = t.world("state")
        check(w["violations"] == 0, "the simulated board saw no violation of its rules (%d)" % w["violations"])
    finally:
        t.close()
    if not replay_only:
        test_cli(glsim, out_dir)
        if "--boot-check" in opts:
            test_boot_tools(os.path.abspath(opts["--boot-check"]), out_dir)
        if "--make" in opts:
            test_release_gate(opts["--make"], out_dir)
    print("== glctl selftest: %d checks, %d failed -> %s" % (checks, len(failed), "PASS" if not failed else "FAIL"))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
