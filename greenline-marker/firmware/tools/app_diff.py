#!/usr/bin/env python3
"""Application-level differential check of the putt estimate.

    build/host/tests/test_e2e_putt <records.jsonl>     (writes the records)
    tools/app_diff.py <records.jsonl> [--sim DIR]      (this script)

or simply `make appdiff`.

tests/test_e2e_putt.c runs the whole firmware on the host simulator - the
read sequence, the vision, the hand-over, the estimator, the renderer - and
writes, for every estimator call the APPLICATION made, one JSON object per
line with

    drops        the gl_measurements_t records it built, as the fields of
                 greenline_sim.measurements.Measurements
    ball_index   which of them is the placement at the ball
    method, past the options of the call
    firmware     what the firmware's single-precision estimator returned
    c_double     what the double-precision C build returned for the same
                 records, with the tolerances of the reference vectors
    truth        the same placements with the true values of the scene
    view, shown  the aim as drawn (measured from the frame-buffer pixels)
                 and the strings on the result screen

This script runs THE PYTHON REFERENCE (sim/greenline_sim, the package the
firmware is a port of) on the same records and compares:

  * with `c_double`: the comparison rule of sim/results/REFERENCE_VECTORS.md
    (relative 1e-4 with the absolute floors there; flags and codes exact);
  * with `firmware` (single precision, the firmware's own tolerances): flags
    and codes exact; for a solved aim (aim_source 0 or 1) the aim within
    0.5 mrad, the launch speed within 0.1 %, the break within 0.01 cup, the
    confidence within 1e-4; of an aim that is not a solution only the class;
  * the drawn aim with the reference's, within the display's quantisation
    (6.5 mrad = 0.37 degree; lines that leave the aperture are not measured).

Exit status 0 if every record agrees, 1 otherwise.  It prints the table
that the firmware README quotes.
"""
import json
import math
import os
import sys
from dataclasses import replace

METHODS = {0: "B1", 1: "B0", 2: "B2", 3: "STRAIGHT"}
DISPLAY_TOL_MRAD = 6.5


def wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


def orient(a):
    """Difference of two line orientations (mod pi)."""
    d = math.fmod(a, math.pi)
    if d > math.pi / 2:
        d -= math.pi
    elif d < -math.pi / 2:
        d += math.pi
    return d


def close(a, b, rel, floor):
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= max(floor, rel * abs(b))


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    sim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "sim")
    if "--sim" in argv:
        sim = argv[argv.index("--sim") + 1]
        args = [a for a in args if a != sim]
    if len(args) != 1:
        raise SystemExit(__doc__)
    sys.path.insert(0, sim)
    from greenline_sim import estimator as es
    from greenline_sim.measurements import Measurements

    base = replace(es.EstimatorConfig(), tol_miss=1e-9, tol_pace=1e-9, lm_tol=1e-10, lm_max_iter=200)

    def run(drops, ball, method, past, use_grain, near_miss):
        ms = [Measurements.from_dict(d) for d in drops]
        ordered = [ms[ball]] + [m for i, m in enumerate(ms) if i != ball]  # the reference: ball first
        cfg = replace(base, past=past, use_grain=bool(use_grain), near_miss_keep=near_miss)
        return es.estimate_batch([ordered], METHODS[method], cfg)[0]

    bad = 0
    n = 0
    worst_c = worst_fw = worst_draw = 0.0
    print("%-60s | %9s %9s | %9s | %9s | %7s | %s" %
          ("scene", "ref aim", "ref true", "firmware", "drawn", "dr-ref", "shown (distance, plays-like, break, slope, note, boxes)"))
    print("%-60s | %9s %9s | %9s | %9s | %7s |" % ("", "[mrad]", "[mrad]", "[mrad]", "[mrad]", "[mrad]"))
    with open(args[0], "r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            n += 1
            # the options of the application's call (the step budget is not one of the
            # reference's: a solve it cuts short would show as a difference of class)
            opts = (rec["method"], rec["past"], rec.get("use_grain", 0), rec.get("near_miss", 0.0))
            est = run(rec["drops"], rec["ball_index"], *opts)
            tru = run(rec["truth"], rec["ball_index"], *opts) if rec["truth"] else None
            why = []
            ref = {
                "phi": est.phi, "aim_azimuth_device": est.aim_azimuth_device, "v0": est.v0,
                "plays_like": est.plays_like, "break_cups": est.break_cups, "distance": est.distance,
                "bearing": est.bearing, "slope_pct": est.slope_pct, "dz_hole": est.dz_hole,
                "confidence": est.confidence,
            }
            codes = {
                "base_hidden": int(est.base_hidden), "flag_missing": int(est.flag_missing),
                "range_missing": int(est.range_missing), "poor_horizon": int(est.poor_horizon),
                "fit_converged": int(est.fit.converged), "aim_source": int(est.aim_source),
                "solve_status": int(est.solve_status),
            }
            solved = codes["aim_source"] in (0, 1)
            for who in ("c_double", "firmware"):
                got = rec[who]
                if got["status"] != 0:
                    why.append("%s: status %d" % (who, got["status"]))
                    continue
                for key, val in codes.items():
                    if got[key] != val:
                        why.append("%s: %s %d, reference %d" % (who, key, got[key], val))
                if who == "c_double":
                    rule = {"phi": (1e-4, 1e-6), "aim_azimuth_device": (1e-4, 1e-6), "bearing": (1e-4, 1e-6),
                            "v0": (1e-4, 0.0), "plays_like": (1e-4, 0.0), "distance": (1e-4, 0.0),
                            "break_cups": (1e-4, 1e-5), "slope_pct": (1e-4, 1e-6), "dz_hole": (1e-4, 1e-6),
                            "confidence": (1e-4, 1e-6)}
                else:
                    rule = {"aim_azimuth_device": (0.0, 5e-4), "bearing": (0.0, 2e-6), "v0": (1e-3, 0.0),
                            "plays_like": (2e-3, 0.0), "distance": (1e-5, 1e-6), "break_cups": (1e-3, 0.01),
                            "slope_pct": (0.0, 1e-4), "confidence": (0.0, 1e-4)}
                for key, (rel, floor) in rule.items():
                    if not solved and key not in ("distance", "bearing", "slope_pct", "confidence"):
                        continue  # of a failed solve only the class is defined
                    a, b = got[key], ref[key]
                    if key in ("phi", "aim_azimuth_device", "bearing"):
                        ok = abs(wrap(a - b)) <= max(floor, rel * abs(b))
                    else:
                        ok = close(a, b, rel, floor)
                    if not ok:
                        why.append("%s: %s %.9g, reference %.9g" % (who, key, a, b))
                if solved:
                    d = abs(wrap(got["aim_azimuth_device"] - ref["aim_azimuth_device"]))
                    if who == "c_double":
                        worst_c = max(worst_c, d)
                    else:
                        worst_fw = max(worst_fw, d)
            drawn = rec["view"]["drawn_aim_read_frame"]
            dtxt = diff = "-"
            if drawn is not None:
                dd = orient(drawn - ref["aim_azimuth_device"])
                dtxt = "%+9.2f" % (1000 * drawn)
                diff = "%+7.2f" % (1000 * dd)
                worst_draw = max(worst_draw, abs(dd))
                if abs(dd) > DISPLAY_TOL_MRAD * 1e-3:
                    why.append("drawn aim %.2f mrad from the reference" % (1000 * dd))
                # a SOLID line only for a solution (by the reference) of a putt whose distance was
                # measured or dialled AND whose flagstick the cameras saw: a flag-out result (the
                # visor axis taken for the line to the hole) is tentative whatever was dialled
                # (phase-2 review); the firmware reports what its pixels are
                ball = rec["drops"][rec["ball_index"]]
                known = not (est.flag_missing or est.range_missing) or ball.get("user_distance") is not None
                firm = solved and known and not est.flag_missing
                if bool(rec["view"].get("dashed")) != (not firm):
                    why.append("line drawn %s, the reference says %s" %
                               ("dashed" if rec["view"].get("dashed") else "solid",
                                "solved, flag seen, distance known" if firm
                                else "not a solution / flag out / distance unknown"))
                if rec["view"].get("dashed"):
                    dtxt += " dashed"
            sh = rec["shown"]
            shown = ", ".join(x for x in (sh["distance"], sh["plays"] or "no plays-like", sh["break"], sh["slope"],
                                          sh["note"], "%d/5" % rec["view"]["boxes"], sh["mode"]) if x)
            print("%-60s | %+9.2f %9s | %+9.2f | %9s | %7s | %s" %
                  (rec["name"], 1000 * ref["aim_azimuth_device"],
                   ("%+9.2f" % (1000 * tru.aim_azimuth_device)) if tru is not None else "-",
                   1000 * rec["firmware"]["aim_azimuth_device"], dtxt, diff, shown))
            for w in why:
                print("    MISMATCH %s" % w)
            bad += 1 if why else 0
    print("%d estimator calls of the application: %d agree with the Python reference, %d do not" % (n, n - bad, bad))
    print("largest |C double - reference| of a solved aim: %.3g mrad; largest |firmware - reference|: %.3f mrad; "
          "largest |drawn - reference|: %.2f mrad (%.2f deg)" %
          (1000 * worst_c, 1000 * worst_fw, 1000 * worst_draw, math.degrees(worst_draw)))
    return 1 if (bad or n == 0) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
