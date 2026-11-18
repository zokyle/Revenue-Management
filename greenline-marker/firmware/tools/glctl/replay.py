"""The replay path (docs/VALIDATION_PLAN.md 3.3, check 1 "same answer"):
run the PYTHON REFERENCE estimator (sim/greenline_sim) on the measurement
record of every read in a decoded log and compare its estimate with the
estimate the firmware logged.

    python3 tools/glctl replay LOG.json [--sim-dir DIR]

Needs the reference's own Python environment (numpy, scipy), like
`make appdiff`.  Exit status 0 if every replayable read agrees.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SIM_DIR = os.path.normpath(os.path.join(HERE, "..", "..", "..", "sim"))

SOURCE = ["patch", "plane", "best effort", "straight"]


def load_reference(sim_dir=None):
    sim_dir = sim_dir or DEFAULT_SIM_DIR
    if sim_dir not in sys.path:
        sys.path.insert(0, sim_dir)
    try:
        from greenline_sim import replay as ref  # noqa: PLC0415
    except ImportError as exc:
        raise SystemExit("the replay needs the Python reference in %s and its dependencies "
                         "(numpy, scipy): %s" % (sim_dir, exc))
    return ref


def replay_log(decoded, sim_dir=None, out=sys.stdout):
    """Replay every read of a decoded log.  Returns (reads replayed, reads that disagree, rows)."""
    ref = load_reference(sim_dir)
    rows, bad, n = [], 0, 0
    out.write("%-7s %-9s %-11s | %10s %10s %8s | %8s %8s | %s\n" %
              ("read", "kind", "source", "fw aim", "ref aim", "diff", "fw dist", "ref dist", "verdict"))
    out.write("%-7s %-9s %-11s | %10s %10s %8s | %8s %8s |\n" %
              ("", "", "", "[mrad]", "[mrad]", "[mrad]", "[m]", "[m]"))
    for read in decoded["reads"]:
        kind = ("survey" if read["survey"] else "precision" if read["precision"] else
                "tilt-only" if read["cameras_off"] else "quick")
        if not read["replayable"]:
            out.write("%-7d %-9s %-11s | not replayable (solver status %d, %d of %d placements in the dump)\n"
                      % (read["read_id"], kind, "-", read["solver_ret"], len(read["drops"]), read["n_drops"]))
            continue
        res = ref.replay_and_compare([read])[0]
        n += 1
        fw, rf = res["logged"], res["reference"]
        ok = not res["mismatches"]
        bad += 0 if ok else 1
        fallback = (fw["aim_source"] != 0 or fw["flag_missing"] or fw["range_missing"])
        out.write("%-7d %-9s %-11s | %+10.3f %+10.3f %8.3f | %8.3f %8.3f | %s%s\n" % (
            read["read_id"], kind, SOURCE[fw["aim_source"]] + ("*" if fallback else ""),
            1000 * fw["aim_azimuth_device"], 1000 * rf["aim_azimuth_device"], res["aim_diff_mrad"],
            fw["distance"], rf["distance"], "agrees" if ok else "DIFFERS",
            "  (fallback: %s)" % ", ".join(k for k in ("flag_missing", "range_missing") if fw[k])
            if (fw["flag_missing"] or fw["range_missing"]) else ""))
        for w in res["mismatches"]:
            out.write("        MISMATCH %s\n" % w)
        rows.append(res)
    worst = max([r["aim_diff_mrad"] for r in rows] or [0.0])
    out.write("%d reads replayed through the Python reference: %d agree with the estimate the firmware "
              "logged, %d do not; largest |firmware - reference| aim %.3f mrad (limit 0.5)\n"
              % (n, n - bad, bad, worst))
    return n, bad, rows


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    sim_dir = argv[argv.index("--sim-dir") + 1] if "--sim-dir" in argv else None
    if sim_dir in args:
        args.remove(sim_dir)
    if len(args) != 1:
        sys.stderr.write(__doc__)
        return 2
    with open(args[0], "r", encoding="utf-8") as fh:
        decoded = json.load(fh)
    n, bad, _ = replay_log(decoded, sim_dir)
    return 0 if (n > 0 and bad == 0) else 1
