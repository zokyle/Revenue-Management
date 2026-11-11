#!/usr/bin/python3
"""Build the GreenLine DEMO board end to end and say honestly whether it passed.

    cd electrical/tools
    /usr/bin/python3 demo/build_demo.py                  # everything, ~6 min
    /usr/bin/python3 demo/build_demo.py --reuse-routing  # skip the router if nothing changed

Stages (each one is recorded in ``demo_out/build_summary.json``):

1. ``checks``     ERC-style and placement checks of the design      -> 0 errors
2. ``board``      ``greenline_demo.kicad_pcb`` / ``.kicad_pro`` / ``.kicad_dru``
3. ``route``      autorouter                                        -> 100 % routed,
                                                                       0 audit violations
4. ``drc``        tracks into the board, zone fill, KiCad DRC       -> 0 errors,
                                                                       0 unconnected
5. ``outputs``    fabrication package (:mod:`gleda.outputs`)
6. ``schematic``  KiCad schematic and netlist round trip (:mod:`gleda.schematic`)

The script exits 0 only if every stage passed.  A stage whose module is not
there yet counts as failed - nothing is skipped silently.  ``--stages`` runs a
subset (for development); the exit code then covers only the stages that ran
and the summary says so.

Everything is written to ``demo/demo_out/``.
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
for _p in (TOOLS, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from demo_design import demo_design                      # noqa: E402
from gleda import board, checks, drc, router, routeplot  # noqa: E402

ALL_STAGES = ("checks", "board", "route", "drc", "outputs", "schematic")


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
    if ctx["args"].reuse_routing and os.path.exists(path):
        try:
            result = router.load_routing(path, design, options)
            reused = True
            say("  reusing %s (design fingerprint matches)" % os.path.basename(path))
        except router.RoutingError as exc:
            say("  not reusing %s: %s" % (os.path.basename(path), exc))
    if result is None:
        log = []

        def progress(line):
            log.append(line)
            if not ctx["args"].quiet and "iteration" not in line:
                say("  " + line)

        options.progress = progress
        result = router.route(design, options)
        options.progress = None
        router.save_routing(path, design, result, options)
        with open(os.path.join(out, "routing_log.txt"), "w") as f:
            f.write("\n".join(line[10:] if line.startswith("[") else line for line in log))
            f.write("\n")
    ctx["route"] = result
    routeplot.plot(design, result.tracks, result.vias, os.path.join(out, "routing_debug.png"),
                   dpi=150)
    say("  " + result.summary())
    for u in result.unrouted:
        say("  UNROUTED %s: %s" % (u.net, " | ".join(",".join(p[:6]) for p in u.pieces)))
    for v in result.audit.violations[:10]:
        say("  AUDIT %s" % (v,))
    stats = result.stats
    info = {
        "reused": reused,
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
        "runtime_s": stats.get("runtime_s"),
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
    try:
        from gleda import outputs
    except ImportError as exc:
        say("  gleda.outputs is not available: %s" % exc)
        return False, {"error": "gleda.outputs missing"}
    if not hasattr(outputs, "build_demo_stage"):
        say("  gleda.outputs has no build_demo_stage(design, out_dir, context)")
        return False, {"error": "gleda.outputs.build_demo_stage missing"}
    return outputs.build_demo_stage(design, out, ctx)


def stage_schematic(design, out, ctx):
    try:
        from gleda import schematic
    except ImportError as exc:
        say("  gleda.schematic is not available: %s" % exc)
        return False, {"error": "gleda.schematic missing"}
    if not hasattr(schematic, "build_demo_stage"):
        say("  gleda.schematic has no build_demo_stage(design, out_dir, context)")
        return False, {"error": "gleda.schematic.build_demo_stage missing"}
    return schematic.build_demo_stage(design, out, ctx)


STAGES = {"checks": stage_checks, "board": stage_board, "route": stage_route,
          "drc": stage_drc, "outputs": stage_outputs, "schematic": stage_schematic}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=os.path.join(HERE, "demo_out"), help="output directory")
    ap.add_argument("--stages", default=",".join(ALL_STAGES),
                    help="comma separated subset of: %s" % ", ".join(ALL_STAGES))
    ap.add_argument("--reuse-routing", action="store_true",
                    help="use demo_out/routing.json instead of routing again when its "
                         "fingerprint matches the design")
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
    ctx = {"args": args}
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
        info["seconds"] = round(time.time() - t0, 1)
        summary["stages"][name] = info
        say("  -> %s (%.1f s)" % ("PASS" if ok else "FAIL", info["seconds"]))
        passed = passed and bool(ok)
    complete = wanted == list(ALL_STAGES)
    summary["passed"] = bool(passed)
    summary["complete_run"] = complete
    summary["seconds"] = round(time.time() - t_all, 1)
    with open(os.path.join(args.out, "build_summary.json"), "w") as f:
        json.dump(summary, f, indent=1, sort_keys=True)
        f.write("\n")
    if passed and complete:
        say("DEMO BUILD PASSED (%.0f s)" % summary["seconds"])
    elif passed:
        say("stages %s passed (%.0f s) - not a complete run" % (", ".join(wanted),
                                                                 summary["seconds"]))
    else:
        failed = [n for n, i in summary["stages"].items() if not i["passed"]]
        say("DEMO BUILD FAILED: %s" % ", ".join(failed))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
