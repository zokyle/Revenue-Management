#!/usr/bin/python3
"""Build the GreenLine DEMO board end to end and say honestly whether it passed.

    cd electrical/tools
    /usr/bin/python3 demo/build_demo.py                  # everything, about 4 minutes
    /usr/bin/python3 demo/build_demo.py --reuse-routing  # skip the router if the design
                                                         # is unchanged (about 20 s)

Stages (each one is recorded in ``demo_out/build_summary.json``):

1. ``checks``     ERC-style and placement checks of the design      -> 0 errors
2. ``board``      ``greenline_demo.kicad_pcb`` / ``.kicad_pro`` / ``.kicad_dru``
3. ``route``      autorouter                                        -> 100 % routed,
                                                                       0 audit violations
4. ``drc``        tracks into the board, zone fill, KiCad DRC       -> 0 errors,
                                                                       0 unconnected
5. ``outputs``    Gerbers, drill, pick-and-place, BOM, netlist,     -> verified against
                  mechanical JSON, renders (:mod:`gleda.outputs`)      the design model
6. ``schematic``  KiCad schematic, PDF, netlist round trip          -> KiCad's netlist ==
                  (:mod:`gleda.schematic`)                             the design's

The script exits 0 only if every stage passed AND the four pass criteria hold:
0 check errors, 100 % of the connections routed, KiCad DRC with 0 errors and
0 unconnected items, and a schematic netlist round trip that matches exactly.
A stage that cannot run counts as failed - nothing is skipped silently.
``--stages`` runs a subset (for development); the exit code then covers only
the stages that ran, the summary says so and "DEMO BUILD PASSED" is not printed.

Everything is written to ``demo/demo_out/``.  ``build_summary.json`` holds the
results (the same on every run of the same design); run times and how the run
was started go to ``build_run.json``.
"""
import argparse
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
for _p in (TOOLS, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from demo_design import demo_design                      # noqa: E402
from gleda import board, checks, drc, outputs, router, routeplot, schematic  # noqa: E402

ALL_STAGES = ("checks", "board", "route", "drc", "outputs", "schematic")
ITERATION_LINE = re.compile(r"iteration \d+:")       # the router's per-round progress lines


def say(msg):
    print(msg, flush=True)


def stage_checks(design, out, ctx):
    report = checks.run_checks(design)
    with open(os.path.join(out, "checks.txt"), "w") as f:
        f.write(report.text() + "\n")
    with open(os.path.join(out, "checks.json"), "w") as f:
        json.dump(report.to_dict(), f, indent=1, sort_keys=True)
        f.write("\n")
    say("  %d error(s), %d warning(s)" % (len(report.errors), len(report.warnings)))
    for finding in report.errors[:20]:
        say("  ERROR [%s] %s" % (finding.code, finding.message))
    return report.ok, {"errors": len(report.errors), "warnings": len(report.warnings)}


def stage_board(design, out, ctx):
    files = board.build_board(design, out)
    ctx["files"] = files
    say("  %s" % os.path.relpath(files.pcb, out))
    return True, {"pcb": os.path.basename(files.pcb), "project": os.path.basename(files.pro)}


def stage_route(design, out, ctx):
    path = os.path.join(out, "routing.json")
    options = router.RouterOptions(time_limit=ctx["args"].time_limit)
    result = None
    reused = False
    reuse = ctx["args"].reuse_routing
    source = path if reuse in (None, True) else os.path.abspath(reuse)
    if reuse is not None and os.path.exists(source):
        try:
            # the stored copper is only accepted if its fingerprint matches this
            # design and options, and it is audited again from the copper alone
            result = router.load_routing(source, design, options)
            reused = True
            say("  reusing %s (design fingerprint matches)" % os.path.basename(source))
            if os.path.abspath(source) != os.path.abspath(path):
                router.save_routing(path, design, result, options)
        except router.RoutingError as exc:
            say("  not reusing %s: %s" % (os.path.basename(source), exc))
    elif reuse is not None:
        say("  no stored routing at %s: routing from scratch" % source)
    if result is None:
        log = []

        def progress(line):
            log.append(line)
            if not ctx["args"].quiet and not ITERATION_LINE.search(line):
                say("  " + line)

        options.progress = progress
        result = router.route(design, options)
        options.progress = None
        router.save_routing(path, design, result, options)
        with open(os.path.join(out, "routing_log.txt"), "w") as f:
            for line in log:                         # without the clock: the same on every run
                line = re.sub(r"^\[ *[0-9.]+s\] ", "", line)
                f.write(re.sub(r", [0-9.]+ s$", "", line) + "\n")
    ctx["route"] = result
    routeplot.plot(design, result.tracks, result.vias, os.path.join(out, "routing_debug.png"),
                   dpi=150)
    say("  " + result.summary())
    for u in result.unrouted:
        say("  UNROUTED %s: %s%s" % (u.net, " | ".join(",".join(p[:6]) for p in u.pieces),
                                   "  [%s]" % u.reason if u.reason else ""))
    for v in result.audit.violations[:10]:
        say("  AUDIT %s" % (v,))
    quality = result.quality or router.net_quality(design, result.tracks, result.vias)
    if quality.get("signal_tree_mm"):
        say("  signal track %.0f mm for %.0f mm of spanning trees (x%.2f), %d net(s) over x1.5"
            % (quality["signal_length_mm"], quality["signal_tree_mm"],
               quality["signal_ratio"], quality["nets_over_1_5"]))
    for line in quality.get("warnings", []):
        say("  LOOK AT %s" % line)
    stats = result.stats
    ctx["run"]["routing_reused"] = reused
    ctx["run"]["router_seconds"] = stats.get("runtime_s")
    info = {
        "nets": stats.get("nets"),
        "connections_total": result.connections_total,
        "connections_routed": result.connections_routed,
        "routed_percent": round(100.0 * result.routed_fraction, 3),
        "vias": len(result.vias),
        "tracks": len(result.tracks),
        "track_length_mm": stats.get("track_length_mm"),
        "track_length_by_layer_mm": stats.get("track_length_by_layer_mm"),
        "audit_violations": len(result.audit.violations),
        "plane_pieces": dict(result.audit.plane_pieces),
        "unrouted": [u.to_dict() for u in result.unrouted],
        # not a pass criterion: how the copper compares with the shortest
        # possible trees, and the nets a layout engineer should look at
        "quality": {"signal_length_mm": quality.get("signal_length_mm"),
                    "signal_tree_mm": quality.get("signal_tree_mm"),
                    "signal_ratio": quality.get("signal_ratio"),
                    "nets_over_1_5": quality.get("nets_over_1_5"),
                    "worst": quality.get("worst", [])[:5],
                    "warnings": list(quality.get("warnings", []))},
        "corners_cut": stats.get("corners_cut", 0),
    }
    return result.complete, info


def stage_drc(design, out, ctx):
    files = ctx.get("files")
    result = ctx.get("route")
    if files is None or result is None:
        say("  needs the board and route stages")
        return False, {"error": "board or routing missing"}
    applied = board.apply_routing(files.pcb, result.tracks, result.vias,
                                  via_tenting=design.via_tenting)
    res = drc.run_drc(files.pcb, report_path=os.path.join(out, "drc_report.txt"),
                      json_path=os.path.join(out, "drc.json"))
    ctx["drc"] = res
    say("  " + res.summary())
    ok = True
    try:
        drc.assert_clean(res)
    except drc.DrcError as exc:
        ok = False
        say("  " + str(exc).replace("\n", "\n  "))
    info = {
        "errors": res.error_count, "errors_by_type": dict(res.errors_by_type),
        "warnings_by_type": dict(res.warnings_by_type), "unconnected": res.unconnected_count,
        "tracks_written": applied.tracks, "vias_written": applied.vias,
        "cosmetic_allow_list": sorted(drc.COSMETIC_CHECKS),
    }
    return ok, info


def stage_outputs(design, out, ctx):
    return outputs.build_demo_stage(design, out, ctx)


def stage_schematic(design, out, ctx):
    return schematic.build_demo_stage(design, out, ctx)


def criteria(stages):
    """The four pass criteria of the demo, each True / False, or None when the
    stage that decides it did not run."""
    def get(stage, key):
        return stages[stage].get(key) if stage in stages else None

    out = {}
    errors = get("checks", "errors")
    out["checks_0_errors"] = None if errors is None else errors == 0
    percent, unrouted = get("route", "routed_percent"), get("route", "unrouted")
    out["routed_100_percent"] = None if percent is None else (
        percent == 100.0 and not unrouted and get("route", "audit_violations") == 0)
    drc_errors, unconnected = get("drc", "errors"), get("drc", "unconnected")
    out["kicad_drc_0_errors_0_unconnected"] = None if drc_errors is None else (
        drc_errors == 0 and unconnected == 0)
    trip = get("schematic", "round_trip")
    out["schematic_round_trip_matches"] = None if trip is None else bool(trip.get("ok"))
    return out


def stage_line(name, info):
    """One line per stage for the closing summary."""
    if "error" in info:
        return info["error"]
    if name == "checks":
        return "%d errors, %d warnings" % (info["errors"], info["warnings"])
    if name == "board":
        return "%s, %s" % (info["pcb"], info["project"])
    if name == "route":
        return "%d of %d connections (%.1f %%), %d vias, %d track segments, %d audit " \
               "violations" % (info["connections_routed"], info["connections_total"],
                               info["routed_percent"], info["vias"], info["tracks"],
                               info["audit_violations"])
    if name == "drc":
        cosmetic = sum(info["warnings_by_type"].values())
        return "KiCad DRC %d errors, %d unconnected, %d warnings%s" % (
            info["errors"], info["unconnected"], cosmetic,
            " (%s)" % ", ".join("%s %d" % kv for kv in sorted(info["warnings_by_type"].items()))
            if cosmetic else "")
    if name == "outputs":
        return "%d files, %d problems against the design model, BOM %d lines / %.2f per " \
               "board, %d pick-and-place rows" % (
                   info["files"], len(info["problems"]), info["bom"]["lines"],
                   info["bom"]["cost_per_board"], info["position_rows"])
    if name == "schematic":
        trip = info["round_trip"]
        return "%d sheets, PDF %d pages, round trip %s (%d nets, %d pads, %d components)" % (
            len(info["sheets"]) + 1, info["pdf_pages"], "matches" if trip["ok"] else "MISMATCH",
            trip["nets_compared"], trip["pads_compared"], trip["components_compared"])
    return ""


STAGES = {"checks": stage_checks, "board": stage_board, "route": stage_route,
          "drc": stage_drc, "outputs": stage_outputs, "schematic": stage_schematic}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=os.path.join(HERE, "demo_out"), help="output directory")
    ap.add_argument("--stages", default=",".join(ALL_STAGES),
                    help="comma separated subset of: %s" % ", ".join(ALL_STAGES))
    ap.add_argument("--reuse-routing", nargs="?", const=True, default=None, metavar="FILE",
                    help="use a stored routing (default: <out>/routing.json) instead of "
                         "routing again; it is only accepted when its fingerprint matches "
                         "the design, and it is audited and DRC-checked like a fresh one")
    ap.add_argument("--time-limit", type=float, default=1500.0,
                    help="seconds after which the router stops starting new work")
    ap.add_argument("--quiet", action="store_true", help="no router progress lines")
    args = ap.parse_args(argv)
    wanted = [s.strip() for s in args.stages.split(",") if s.strip()]
    unknown = [s for s in wanted if s not in STAGES]
    if unknown:
        ap.error("unknown stage(s): %s" % ", ".join(unknown))
    os.makedirs(args.out, exist_ok=True)
    design = demo_design()
    run = {"stages_run": wanted, "seconds": {}}
    ctx = {"args": args, "run": run}
    summary = {"design": design.name, "stages": {}, "stages_run": wanted,
               "all_stages": list(ALL_STAGES)}
    t_all = time.time()
    passed = True
    for name in ALL_STAGES:
        if name not in wanted:
            continue
        say("[%s]" % name)
        t0 = time.time()
        try:
            ok, info = STAGES[name](design, args.out, ctx)
        except Exception as exc:                      # a crash is a failure, not a skip
            import traceback
            traceback.print_exc()
            ok, info = False, {"error": "%s: %s" % (type(exc).__name__, exc)}
        info = dict(info or {})
        info["passed"] = bool(ok)
        run["seconds"][name] = round(time.time() - t0, 1)
        summary["stages"][name] = info
        say("  -> %s (%.1f s)" % ("PASS" if ok else "FAIL", run["seconds"][name]))
        passed = passed and bool(ok)
    complete = wanted == list(ALL_STAGES)
    crit = criteria(summary["stages"])
    # a criterion that is False fails the run even if its stage claimed a pass
    passed = passed and all(v is not False for v in crit.values())
    summary["criteria"] = crit
    summary["passed"] = bool(passed)
    summary["complete_run"] = complete
    run["seconds"]["total"] = round(time.time() - t_all, 1)
    with open(os.path.join(args.out, "build_summary.json"), "w") as f:
        json.dump(summary, f, indent=1, sort_keys=True)
        f.write("\n")
    with open(os.path.join(args.out, "build_run.json"), "w") as f:
        json.dump(run, f, indent=1, sort_keys=True)
        f.write("\n")

    say("")
    say("=" * 78)
    say("GreenLine demo build - %s (%d parts, %d nets)" % (design.name, len(design.parts),
                                                           len(design.nets)))
    say("=" * 78)
    for name in ALL_STAGES:
        info = summary["stages"].get(name)
        if info is None:
            say("%-10s %-8s" % (name, "not run"))
        else:
            say("%-10s %-8s %s" % (name, "PASS" if info["passed"] else "FAIL",
                                   stage_line(name, info)))
    say("-" * 78)
    labels = {"checks_0_errors": "design checks: 0 errors",
              "routed_100_percent": "100 % of the connections routed",
              "kicad_drc_0_errors_0_unconnected": "KiCad DRC: 0 errors, 0 unconnected",
              "schematic_round_trip_matches": "schematic netlist round trip matches"}
    for key, label in labels.items():
        say("%-38s %s" % (label, {True: "yes", False: "NO", None: "not checked"}[crit[key]]))
    say("-" * 78)
    if passed and complete:
        say("DEMO BUILD PASSED (%.0f s)" % run["seconds"]["total"])
    elif passed:
        say("stages %s passed (%.0f s) - not a complete run" % (", ".join(wanted),
                                                                 run["seconds"]["total"]))
    else:
        failed = [n for n, i in summary["stages"].items() if not i["passed"]]
        failed += [labels[k] for k, v in crit.items() if v is False]
        say("DEMO BUILD FAILED: %s" % "; ".join(failed))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
