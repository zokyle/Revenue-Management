"""glctl - talk to a GreenLine GL-1 (or to the host simulator of its firmware).

    python3 tools/glctl [--port /dev/ttyACM0 | --sim [PATH]] COMMAND [ARGS]

Reading (no unlock):
    ident | info | status | sensors | power | settings [key=value ...] | serial
    cal-get {tilt,cam_l,cam_r,grain,device} FILE     save a calibration record
    cam-id CAM | cam-field CAM | capture CAM X0 Y0 W H FILE.pgm [--dark] | frame CAM FILE.pgm [--dark]
    display PATTERN [SECONDS]      normal white black checker1 checker8 rows columns orient ref-raw ref-corrected
    display-rot                    read the stored rotation
    grain {dark,cycle} | zero status | cal-status | log-info
    stream SOURCE[,SOURCE] [--period MS] [--count N]     imu tilt grain power; imu frames carry the
                                   acceleration in g and its total (close to 1 g at rest)
    log-download FILE.bin [--resume]      written as it arrives; --resume continues a broken one
                                   then:  log-decode FILE.bin FILE.json  and  replay FILE.json
    lock                           end the factory session (also ends a "charge stop")
Writing (the tool unlocks first; the unit refuses them while locked):
    cal-set NAME FILE | display-rot --set DEG | display-rot --measured DEG
    display PATTERN SECONDS --plate    also arm the pattern for the seat plate: shown again, with
                                   nothing on the pads, when the marker is next put down out of the cradle
    grain store | grain white | zero arm {base,ball} [--rest MINUTES] | zero cancel | six-face {0..5,solve}
    tempco FILE.csv [--t0 C]       lines: temperature C, offset x, y, z in g - AT LEAST 5 lines over
                                   at least 30 K.  Only the CHANGE with temperature is stored (b1, b2);
                                   the six-face offsets are kept, so the lines may be absolute offsets
                                   or drift against any reference (0 for an axis not measured).
                                   --t0: the six-face temperature (the unit checks it against its record)
    cam-horizon CAM ROW [ROLL_RAD] | grain-floor FILE     one modulation per line
    sleep-test [--motion] [--timer SECONDS] | sleep-test --off
    ship | ship --stay | charge {stop,auto} | serial --commit | time | log-erase
    update-loader                  leave for ST's USB loader (the boot stub starts it)
    reboot
Without a unit:
    log-decode FILE.bin FILE.json | replay FILE.json [--sim-dir DIR]

Every command prints JSON.  Exit status: 0 done, 1 the unit refused, 2 usage or a file that
cannot be read (a log dump of an unknown layout), 3 no link.  log-decode of a dump that was cut
decodes up to its last complete record and says how many bytes it left out.
"""
import json
import math
import sys

if __package__ in (None, ""):
    # run as `python3 tools/glctl ...` (a directory): make the package importable
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "glctl"

from glctl import logdec, proto, replay  # noqa: E402
from glctl.device import Device  # noqa: E402
from glctl.proto import DeviceError, ProtocolError  # noqa: E402
from glctl.transport import SerialTransport, SimTransport  # noqa: E402


def pgm(path, width, height, pixels):
    with open(path, "wb") as fh:
        fh.write(b"P5\n%d %d\n255\n" % (width, height))
        fh.write(pixels)


def numbers(path, per_line):
    rows = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.split("#")[0].strip()
            if not line:
                continue
            vals = [float(v) for v in line.replace(",", " ").split()]
            if len(vals) != per_line:
                raise ValueError("%s: expected %d numbers per line, found %r" % (path, per_line, line))
            rows.append(vals if per_line > 1 else vals[0])
    return rows


def flag(args, name, takes_value=False, default=None):
    if name not in args:
        return default
    i = args.index(name)
    args.pop(i)
    if not takes_value:
        return True
    if i >= len(args):
        raise ValueError("%s needs a value" % name)
    return args.pop(i)


def offline(cmd, args):
    if cmd == "log-decode":
        if len(args) != 2:
            raise ValueError("log-decode FILE.bin FILE.json")
        with open(args[0], "rb") as fh:
            decoded = logdec.decode_tolerant(fh.read())
        with open(args[1], "w", encoding="utf-8") as fh:
            json.dump(decoded, fh, indent=1)
        out = {"records": len(decoded["records"]), "reads": len(decoded["reads"]),
               "replayable": sum(1 for r in decoded["reads"] if r["replayable"]), "written": args[1]}
        if decoded["cut_bytes"]:
            out["warning"] = ("the dump ends inside a record: %d bytes behind the last complete record "
                              "were left out (log-download --resume completes the file)" % decoded["cut_bytes"])
            sys.stderr.write("glctl: warning: %s\n" % out["warning"])
        return out
    return None


def run(dev, cmd, args):
    """One command against a Device; returns what to print."""
    deg = math.pi / 180.0
    guarded = {"cal-set", "tempco", "cam-horizon", "grain-floor", "ship", "charge", "update-loader",
               "log-erase", "six-face"}
    if cmd in guarded or (cmd == "display-rot" and args) or \
            (cmd == "grain" and args[:1] in (["store"], ["white"])) or (cmd == "display" and "--plate" in args) or \
            (cmd == "zero" and args[:1] == ["arm"]) or (cmd == "sleep-test" and "--off" not in args) or \
            (cmd == "serial" and "--commit" in args):
        if cmd != "ship" or "--stay" not in args:
            dev.unlock()
    if cmd == "ping":
        return {"ping": dev.ping()}
    if cmd == "ident":
        return dev.ident()
    if cmd == "info":
        return dev.info()
    if cmd == "status":
        return dev.status()
    if cmd == "sensors":
        return dev.sensors()
    if cmd == "power":
        return dev.power()
    if cmd == "settings":
        return dev.set_settings(**dict(a.split("=", 1) for a in args)) if args else dev.get_settings()
    if cmd == "serial":
        return dev.serial(commit=flag(args, "--commit", default=False))
    if cmd == "cal-get":
        blob = dev.get_cal(args[0])
        with open(args[1], "wb") as fh:
            fh.write(blob)
        return {"record": args[0], "bytes": len(blob), "version": blob[0], "flags": blob[1], "written": args[1]}
    if cmd == "cal-set":
        with open(args[1], "rb") as fh:
            dev.set_cal(args[0], fh.read())
        return {"record": args[0], "stored": True}
    if cmd == "cam-id":
        return dev.cam_id(int(args[0]))
    if cmd == "cam-field":
        f = dev.cam_field(int(args[0]))
        f["verdict"] = ("PASS" if f["ratio"] is not None and f["ratio"] >= 0.9 else "FAIL") + \
            " (proposed limit: upper bar not more than 10 % darker)"
        return f
    if cmd == "capture":
        dark = flag(args, "--dark", default=False)
        info, px = dev.picture(int(args[0]), int(args[1]), int(args[2]), int(args[3]), int(args[4]), dark)
        pgm(args[5], info["width"], info["height"], px)
        return dict(info, written=args[5])
    if cmd == "frame":
        dark = flag(args, "--dark", default=False)
        info, px = dev.frame(int(args[0]), dark)
        pgm(args[1], 640, 480, px)
        return dict(info, written=args[1])
    if cmd == "lock":
        dev.lock()
        return dev.status()
    if cmd == "stream":
        period = int(flag(args, "--period", True, "100"))
        count = int(flag(args, "--count", True, "10"))
        return dev.stream(args[0].split(","), period, count)
    if cmd == "display":
        plate = flag(args, "--plate", default=False)
        return dev.display_test(args[0], int(args[1]) if len(args) > 1 else 30, plate=bool(plate))
    if cmd == "display-rot":
        measured = flag(args, "--measured", True)
        setv = flag(args, "--set", True)
        if measured is not None:
            # the camera saw the UNCORRECTED reference line at this angle (+ = counter-clockwise):
            # the line must be turned back by it
            r = dev.display_rot(-float(measured) * deg)
        elif setv is not None:
            r = dev.display_rot(float(setv) * deg)
        else:
            r = dev.display_rot()
        r["rotation_deg"] = r["rotation_rad"] / deg
        return r
    if cmd == "grain":
        if args[:1] == ["white"]:
            return dev.grain_white()
        return dev.grain_test(args[0] if args else "cycle")
    if cmd == "zero":
        rest = int(flag(args, "--rest", True, "0"))
        return dev.level_zero(args[0] if args else "status", args[1] if len(args) > 1 else "base", rest)
    if cmd == "cal-status":
        return dev.cal_status()
    if cmd == "six-face":
        return dev.six_face_solve() if args[0] == "solve" else dev.six_face(int(args[0]))
    if cmd == "tempco":
        t0 = float(flag(args, "--t0", True, "25"))
        return dev.tilt_tempco([tuple(r) for r in numbers(args[0], 4)], t0)
    if cmd == "cam-horizon":
        return dev.set_cam_horizon(int(args[0]), float(args[1]), float(args[2]) if len(args) > 2 else 0.0)
    if cmd == "grain-floor":
        return dev.set_grain_floor(numbers(args[0], 1))
    if cmd == "sleep-test":
        if flag(args, "--off", default=False):
            return dev.sleep_test(False, 0)
        return dev.sleep_test(flag(args, "--motion", default=False), int(flag(args, "--timer", True, "0")))
    if cmd == "ship":
        return {"armed": dev.ship_mode(not flag(args, "--stay", default=False))}
    if cmd == "charge":
        dev.set_charge(args[0] == "stop")
        return dev.power()
    if cmd == "time":
        dev.set_time()
        return dev.status()
    if cmd == "update-loader":
        dev.reboot(loader=True)
        return {"requested": "update loader"}
    if cmd == "reboot":
        dev.reboot()
        return {"requested": "reset"}
    if cmd == "log-info":
        return dev.log_info()
    if cmd == "log-erase":
        dev.log_erase()
        return {"erasing": True}
    if cmd == "log-download":
        resume = flag(args, "--resume", default=False)
        return dev.log_download_to(args[0], resume=bool(resume))
    raise ValueError("unknown command %r" % cmd)


def main(argv):
    args = list(argv[1:])
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if args else 2
    try:
        port = flag(args, "--port", True)
        sim = None
        if "--sim" in args:
            i = args.index("--sim")
            args.pop(i)
            sim = args.pop(i) if i < len(args) and args[i].endswith("glsim") else ""
        if not args:
            print(__doc__)
            return 2
        cmd, rest = args[0], args[1:]
        if cmd == "replay":
            return replay.main(rest)
        out = offline(cmd, rest)
        if out is None:
            if sim is None and port is None:
                sys.stderr.write("glctl: say where the unit is: --port DEVICE, or --sim for the simulator\n")
                return 2
            transport = SimTransport(sim or None) if sim is not None else SerialTransport(port)
            try:
                if sim is not None:
                    transport.world("dock")  # USB exists only in the cradle
                dev = Device(transport)
                dev.negotiate()
                name = {"cam-id": "CAM_ID", "sensors": "GET_SENSORS", "zero": "LEVEL_ZERO"}.get(cmd)
                if name and not dev.has(name):
                    raise ProtocolError("this unit (protocol %s) does not have the command %s"
                                        % (dev.ident_cache.get("proto_version"), name))
                out = run(dev, cmd, rest)
            finally:
                transport.close()
        print(json.dumps(out, indent=1))
        return 0
    except DeviceError as exc:
        sys.stderr.write("glctl: %s\n" % exc)
        return 1
    except ProtocolError as exc:
        sys.stderr.write("glctl: %s\n" % exc)
        return 3
    except logdec.LogError as exc:
        sys.stderr.write("glctl: this is not a log dump this tool can decode: %s\n" % exc)
        return 2
    except (ValueError, IndexError, KeyError, OSError) as exc:
        sys.stderr.write("glctl: %s\n" % (exc if str(exc) else repr(exc)))
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
