#!/usr/bin/python3
"""GL-1 main board: layout, routing and outputs in one command.

    /usr/bin/python3 -B electrical/gl1_main/build_gl1_main.py --pindata DIR
    /usr/bin/python3 -B electrical/gl1_main/build_gl1_main.py --pindata DIR --reroute   # route from nothing

Everything goes to ``electrical/gl1_main/out/`` (``--out``).  Stages, each one
recorded in ``out/build_summary.json``:

 1. ``checks``      ``gleda.checks.run_checks`` with its defaults, nothing switched off  -> 0 errors
 2. ``rules``       this board's table "specification -> netlist / layout"
                    (``check_netlist_rules.py``) and its seeded-defect self-test
 3. ``pinmap``      ``check_pinmap.py`` in its own interpreter (``-I``); with ``--pindata``
                    against ST's open pin data, without it PARTIAL (KiCad symbol only)
 4. ``board``       ``gl1_main.kicad_pcb`` / ``.kicad_pro`` / ``.kicad_dru``
 5. ``route``       the toolchain's router with the options of ``gl1_main_design.ROUTER_OPTIONS``.
                    ``out/routing.json`` (or the stored ``routing.json`` next to this file)
                    is reused when its fingerprint matches design + options - it is
                    audited again from the copper alone; ``--reroute`` routes from nothing
 6. ``drc``         tracks into the board, zone fill, KiCad DRC with the full rule set;
                    nothing is excluded, waived or downgraded                 -> 0 errors, 0 unconnected
 7. ``outputs``     Gerber, drill, position, BOM (and a BOM with the evidence status of
                    every line), netlist / mechanical JSON, STEP, renders, fab README
                    - written by the toolchain, which refuses a board that is not clean
                    and verifies the plotted data against the model
 8. ``schematic``   sheets, PDF, PNG and the netlist round trip through kicad-cli
 9. ``mechanical``  ``mechanical/cad/board_import.py`` on ``out/gl1_main-mechanical.json``
10. ``quality``     figures measured on the copper (``layout_quality.py``), review renders

Exit status 0 only if every stage passed and: 0 check errors, 100 % routed with
a clean audit, KiCad DRC 0 errors and 0 unconnected, outputs verified, round
trip equal, mechanical import passed.  A stage that cannot run is a failure.
Fabrication data is never written for an incomplete board.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.normpath(os.path.join(HERE, "..", "tools"))
for _p in (TOOLS, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import gl1_main_design as G                                               # noqa: E402
import check_netlist_rules                                                # noqa: E402
import netlist_stage                                                      # noqa: E402
import layout_quality                                                     # noqa: E402
from gleda import board, checks, drc, outputs, router, routeplot, schematic   # noqa: E402

ALL_STAGES = ("checks", "rules", "pinmap", "board", "route", "drc", "outputs", "schematic",
              "mechanical", "quality")
ITERATION_LINE = re.compile(r"iteration \d+:")
STORED_ROUTING = os.path.join(HERE, "routing.json")
MECH_DIR = os.path.normpath(os.path.join(HERE, "..", "..", "mechanical"))


def say(msg=""):
    print(msg, flush=True)


def router_options(time_limit):
    return router.RouterOptions(time_limit=time_limit, **dict(G.ROUTER_OPTIONS))


# ------------------------------------------------------------------------------------------------
def stage_checks(design, out, ctx):
    report = checks.run_checks(design)
    with open(os.path.join(out, "checks.txt"), "w", encoding="utf-8") as fh:
        fh.write(report.text() + "\n")
    with open(os.path.join(out, "checks.json"), "w", encoding="utf-8") as fh:
        json.dump(report.to_dict(), fh, indent=1, sort_keys=True)
        fh.write("\n")
    say("  %d error(s), %d warning(s)" % (len(report.errors), len(report.warnings)))
    for f in (report.errors + report.warnings)[:30]:
        say("  %s [%s] %s" % (f.severity.upper(), f.code, f.message))
    return report.ok, {"errors": len(report.errors), "warnings": len(report.warnings),
                       "errors_by_code": report.codes("error"),
                       "warnings_by_code": report.codes("warning"),
                       "warning_messages": [f.message for f in report.warnings]}


def stage_rules(design, out, ctx):
    rows = check_netlist_rules.rules(design)
    status = netlist_stage.row_status
    by = {s: [r[0] for r in rows if status(r) == s] for s in netlist_stage.STATUSES}
    for r in rows:
        if status(r) == "FAIL":
            say("  FAIL %s: %s" % (r[0], r[2]))
        elif status(r) in ("open", "workaround"):
            say("  %s %s: %s" % (status(r).upper(), r[0], r[4]))
    with open(os.path.join(out, "spec_rules.md"), "w", encoding="utf-8") as fh:
        fh.write("| Spec rule | What the specification says | Where it is on the board | Result |\n"
                 "|---|---|---|---|\n")
        for r in rows:
            st = status(r)
            fh.write("| %s | %s | %s%s | %s |\n" % (r[0], r[1], r[2], (" *(%s)*" % r[4]) if r[4] else "",
                                                     st if st == "pass" else "**%s**" % st))
        fh.write("\n%d rows: %s\n" % (len(rows), ", ".join("%d %s" % (len(by[s]), s)
                                                           for s in netlist_stage.STATUSES)))
    lines, missed = check_netlist_rules.selftest()
    say("  %d rows: %s" % (len(rows), ", ".join("%d %s" % (len(by[s]), s) for s in netlist_stage.STATUSES)))
    say("  self-test: %d seeded defects, %d missed" % (len(lines), missed))
    for line in lines:
        if "MISSED" in line:
            say(line)
    return not by["FAIL"] and not missed, {
        "rows": len(rows), "failed": by["FAIL"], "as_specified": len(by["pass"]),
        "departures": by["departure"], "open_not_met": by["open"], "workarounds": by["workaround"],
        "selftest_defects": len(lines), "selftest_missed": missed}


def stage_pinmap(design, out, ctx):
    cmd = [sys.executable, "-I", "-B", os.path.join(HERE, "check_pinmap.py"), "--export", "--selftest",
           "--report", os.path.join(out, "pinmap_check.txt")]
    pindata = ctx["args"].pindata
    if pindata:
        cmd += ["--pindata", pindata]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    tail = [l for l in proc.stdout.splitlines()
            if l.startswith(("RESULT", "SELF-TEST", "PARTIAL", "data:", "  FAIL", "  MISSED"))]
    for line in tail:
        say("  " + line)
    say("  exit status %d%s" % (proc.returncode, "" if pindata else
                                "  (no --pindata: PARTIAL, alternate-function numbers not verified)"))
    return proc.returncode == 0, {"exit_status": proc.returncode, "lines": tail,
                                  "against_st_pin_data": bool(pindata)}


def stage_board(design, out, ctx):
    files = board.build_board(design, out)
    ctx["files"] = files
    say("  %s" % os.path.relpath(files.pcb, out))
    return True, {"pcb": os.path.basename(files.pcb), "project": os.path.basename(files.pro)}


def stage_route(design, out, ctx):
    args = ctx["args"]
    path = os.path.join(out, "routing.json")
    options = router_options(args.time_limit)
    result = None
    reused = None
    if not args.reroute:
        for source in (path, STORED_ROUTING):
            if not os.path.exists(source):
                continue
            try:
                result = router.load_routing(source, design, options)
                reused = source
                say("  reusing %s (fingerprint of design + router options matches; audited again)"
                    % os.path.relpath(source, HERE))
                if os.path.abspath(source) != os.path.abspath(path):
                    router.save_routing(path, design, result, options)
                break
            except router.RoutingError as exc:
                say("  not reusing %s: %s" % (os.path.relpath(source, HERE), exc))
    if result is None:
        log = []

        def progress(line):
            log.append(line)
            if not args.quiet and not ITERATION_LINE.search(line):
                say("  " + line)

        options.progress = progress
        t0 = time.time()
        result = router.route(design, options)
        options.progress = None
        ctx["run"]["router_seconds"] = round(time.time() - t0, 1)
        router.save_routing(path, design, result, options)
        if result.complete and args.store:
            shutil.copyfile(path, STORED_ROUTING)
            say("  stored the complete routing as %s" % os.path.relpath(STORED_ROUTING, HERE))
        with open(os.path.join(out, "routing_log.txt"), "w", encoding="utf-8") as fh:
            for line in log:
                line = re.sub(r"^\[ *[0-9.]+s\] ", "", line)
                fh.write(re.sub(r", [0-9.]+ s$", "", line) + "\n")
    ctx["route"] = result
    ctx["run"]["routing_reused"] = bool(reused)
    routeplot.plot(design, result.tracks, result.vias, os.path.join(out, "routing_debug.png"), dpi=200)
    say("  " + result.summary())
    for u in result.unrouted:
        say("  UNROUTED %s: %s%s" % (u.net, " | ".join(",".join(p[:6]) for p in u.pieces),
                                   "  [%s]" % u.reason if u.reason else ""))
    for v in result.audit.violations[:10]:
        say("  AUDIT %s" % (v,))
    quality = result.quality or router.net_quality(design, result.tracks, result.vias)
    if quality.get("signal_tree_mm"):
        say("  signal track %.0f mm for %.0f mm of spanning trees (x%.2f), %d net(s) over x1.5"
            % (quality["signal_length_mm"], quality["signal_tree_mm"], quality["signal_ratio"],
               quality["nets_over_1_5"]))
    for line in quality.get("warnings", []):
        say("  LOOK AT %s" % line)
    stats = result.stats
    info = {"nets": stats.get("nets"), "connections_total": result.connections_total,
            "connections_routed": result.connections_routed,
            "routed_percent": round(100.0 * result.routed_fraction, 3),
            "vias": len(result.vias), "tracks": len(result.tracks),
            "track_length_mm": stats.get("track_length_mm"),
            "track_length_by_layer_mm": stats.get("track_length_by_layer_mm"),
            "audit_violations": len(result.audit.violations),
            "plane_pieces": dict(result.audit.plane_pieces),
            "unrouted": [u.to_dict() for u in result.unrouted],
            "failures": dict(result.failures),
            "router_options": dict(G.ROUTER_OPTIONS),
            "quality": {"signal_length_mm": quality.get("signal_length_mm"),
                        "signal_tree_mm": quality.get("signal_tree_mm"),
                        "signal_ratio": quality.get("signal_ratio"),
                        "nets_over_1_5": quality.get("nets_over_1_5"),
                        "warnings": list(quality.get("warnings", []))}}
    return result.complete, info


def stage_drc(design, out, ctx):
    files, result = ctx.get("files"), ctx.get("route")
    if files is None or result is None:
        say("  needs the board and route stages")
        return False, {"error": "board or routing missing"}
    applied = board.apply_routing(files.pcb, result.tracks, result.vias, via_tenting=design.via_tenting)
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
    return ok, {"errors": res.error_count, "errors_by_type": dict(res.errors_by_type),
                "warnings_by_type": dict(res.warnings_by_type), "unconnected": res.unconnected_count,
                "tracks_written": applied.tracks, "vias_written": applied.vias,
                "custom_rules": len(getattr(res, "custom_rules", []) or []),
                "tampered": list(getattr(res, "tampered", []) or []),
                "cosmetic_allow_list": sorted(drc.COSMETIC_CHECKS)}


def stage_outputs(design, out, ctx):
    route = ctx.get("route")
    if route is None or not route.complete:
        say("  the board is not completely routed: no fabrication data is written")
        return False, {"error": "routing incomplete"}
    ok, info = outputs.build_demo_stage(design, out, ctx)
    if "error" in info:
        return False, info
    # the toolchain's BOM has no status column: the same grouped BOM again, with the evidence
    # status of every line (Part.fields["Status"] / ["StatusNote"])
    lines, counts = netlist_stage.write_bom_with_status(
        design, os.path.join(out, "assembly", design.name + "-bom-status.csv"))
    say("  BOM with status column: %d lines (%s)" % (lines, ", ".join(
        "%d %s" % (v, k) for k, v in sorted(counts.items()))))
    outputs.write_zip(os.path.join(out, "assembly"), os.path.join(out, design.name + "-assembly.zip"))
    info["bom_status"] = {"lines": lines, "by_status": counts}
    fab = os.path.join(out, "fab", "README.txt")
    text = open(fab, encoding="utf-8").read()
    need = ("plugged", "tented", "ENIG")
    missing = [w for w in need if w.lower() not in text.lower()]
    if missing:
        say("  PROBLEM fab README does not mention: %s" % ", ".join(missing))
    info["fab_readme_mentions"] = {w: w.lower() in text.lower() for w in need}
    return ok and not missing and counts.get("MISSING", 0) == 0, info


def stage_schematic(design, out, ctx):
    return schematic.build_demo_stage(design, out, ctx)


def stage_mechanical(design, out, ctx):
    path = os.path.join(out, design.name + "-mechanical.json")
    if not os.path.exists(path):
        say("  no %s (the outputs stage writes it)" % os.path.basename(path))
        return False, {"error": "mechanical JSON missing"}
    data = json.load(open(path, encoding="utf-8"))
    names = {k.get("name") for k in data.get("keepouts", [])}
    want = ["foot_zone_1", "foot_zone_2", "foot_zone_3", "grain_opening_no_via", "pad_slot_no_via"]
    missing = [n for n in want if n not in names]
    say("  keep-outs in the file: %d; bottom-side foot zones and via keep-outs %s"
        % (len(names), "all present" if not missing else "MISSING " + ", ".join(missing)))
    py = ctx["args"].mech_python
    cmd = [py, "-B", os.path.join("cad", "board_import.py"), os.path.relpath(path, MECH_DIR)]
    try:
        proc = subprocess.run(cmd, cwd=MECH_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    except OSError as exc:
        say("  cannot run %s: %s" % (" ".join(cmd), exc))
        return False, {"error": str(exc)}
    lines = [l for l in proc.stdout.splitlines() if l.strip()]
    for line in lines[-12:]:
        say("  " + line[:400])
    say("  (cd mechanical && %s) -> exit %d" % (" ".join(cmd), proc.returncode))
    with open(os.path.join(out, "mechanical_import.txt"), "w", encoding="utf-8") as fh:
        fh.write("$ cd mechanical && %s\n" % " ".join(cmd))
        fh.write(proc.stdout)
        fh.write("exit status %d\n" % proc.returncode)
    return proc.returncode == 0 and not missing, {
        "exit_status": proc.returncode, "keepouts_missing": missing,
        "result": next((l for l in lines if l.startswith(("PASS", "FAIL"))), ""),
        "warnings": [l.strip() for l in lines if l.strip().startswith("warning:")]}


def stage_quality(design, out, ctx):
    files = ctx.get("files")
    pcb = files.pcb if files is not None else os.path.join(out, design.name + ".kicad_pcb")
    if not os.path.exists(pcb):
        return False, {"error": "board file missing"}
    tracks, vias = board.read_routing(pcb)
    q = layout_quality.quality(design, tracks, vias, cam_arrays=G.CAM_ARRAYS, cam_map=G.CAM_ARRAY_MAP,
                               bus=G.CAM_BUS)
    with open(os.path.join(out, "layout_quality.json"), "w", encoding="utf-8") as fh:
        json.dump(q, fh, indent=1, sort_keys=True)
        fh.write("\n")
    text = layout_quality.markdown(q)
    with open(os.path.join(out, "layout_quality.md"), "w", encoding="utf-8") as fh:
        fh.write(text)
    for line in text.splitlines():
        say("  " + line)
    # pictures for a human: every copper layer on its own and both assembly sides
    rdir = os.path.join(out, "review")
    if os.path.isdir(rdir):
        shutil.rmtree(rdir)
    os.makedirs(rdir)
    bounds = outputs.edge_bounds(design)
    views = [("copper-F_Cu", ["F.Cu", "Edge.Cuts"], False), ("copper-In1_Cu", ["In1.Cu", "Edge.Cuts"], False),
             ("copper-In2_Cu", ["In2.Cu", "Edge.Cuts"], False), ("copper-B_Cu", ["B.Cu", "Edge.Cuts"], True),
             ("assembly-top", ["F.Fab", "F.SilkS", "F.Mask", "Edge.Cuts"], False),
             ("assembly-bottom", ["B.Fab", "B.SilkS", "B.Mask", "Edge.Cuts"], True),
             ("silk-top", ["F.SilkS", "F.Mask", "Edge.Cuts"], False)]
    made = []
    for name, layers, mirror in views:
        png = os.path.join(rdir, "%s-%s.png" % (design.name, name))
        outputs.render_view(pcb, png, layers, bounds, mirror=mirror, dpi=ctx["args"].review_dpi)
        made.append(os.path.basename(png))
    say("  review pictures: %s" % ", ".join(made))
    return True, {"figures": q, "review_pictures": made}


STAGES = {"checks": stage_checks, "rules": stage_rules, "pinmap": stage_pinmap, "board": stage_board,
          "route": stage_route, "drc": stage_drc, "outputs": stage_outputs, "schematic": stage_schematic,
          "mechanical": stage_mechanical, "quality": stage_quality}


def criteria(stages):
    def get(stage, key):
        return stages[stage].get(key) if stage in stages else None

    out = {}
    v = get("checks", "errors")
    out["design checks: 0 errors"] = None if v is None else v == 0
    v = get("rules", "failed")
    out["spec rules: no row failed, self-test caught every seeded defect"] = None if v is None else (
        not v and get("rules", "selftest_missed") == 0)
    v = get("pinmap", "exit_status")
    out["pin map check clean"] = None if v is None else v == 0
    pct = get("route", "routed_percent")
    out["100 % of the connections routed, audit clean"] = None if pct is None else (
        pct == 100.0 and not get("route", "unrouted") and get("route", "audit_violations") == 0)
    e = get("drc", "errors")
    out["KiCad DRC: 0 errors, 0 unconnected, nothing excluded"] = None if e is None else (
        e == 0 and get("drc", "unconnected") == 0 and not get("drc", "tampered"))
    p = get("outputs", "problems")
    out["outputs verified against the model"] = None if p is None else (not p and bool(get("outputs", "drc_clean")))
    trip = get("schematic", "round_trip")
    out["schematic netlist round trip matches"] = None if trip is None else bool(trip.get("ok"))
    v = get("mechanical", "exit_status")
    out["mechanical import check passes"] = None if v is None else (v == 0 and not get("mechanical", "keepouts_missing"))
    return out


def stage_line(name, info):
    if "error" in info:
        return str(info["error"])
    if name == "checks":
        return "%d errors, %d warnings %s" % (info["errors"], info["warnings"], info["warnings_by_code"] or "")
    if name == "rules":
        return "%d rows: %d as specified, %d departures, %d open, %d workaround, %d failed; self-test %d of %d" % (
            info["rows"], info["as_specified"], len(info["departures"]), len(info["open_not_met"]),
            len(info["workarounds"]), len(info["failed"]),
            info["selftest_defects"] - info["selftest_missed"], info["selftest_defects"])
    if name == "pinmap":
        return "; ".join(l for l in info["lines"] if l.startswith(("RESULT", "SELF-TEST"))) + (
            "" if info["against_st_pin_data"] else "  [PARTIAL: no --pindata]")
    if name == "board":
        return "%s, %s" % (info["pcb"], info["project"])
    if name == "route":
        return "%d of %d connections (%.1f %%), %d vias, %d track segments, %s mm, %d audit violations" % (
            info["connections_routed"], info["connections_total"], info["routed_percent"], info["vias"],
            info["tracks"], info["track_length_mm"], info["audit_violations"])
    if name == "drc":
        w = info["warnings_by_type"]
        return "KiCad DRC %d errors, %d unconnected, %d warnings%s" % (
            info["errors"], info["unconnected"], sum(w.values()),
            " (%s)" % ", ".join("%s %d" % kv for kv in sorted(w.items())) if w else "")
    if name == "outputs":
        return "%d files, %d problems against the model, BOM %d lines (%s), %d position rows" % (
            info["files"], len(info["problems"]), info["bom"]["lines"],
            ", ".join("%d %s" % (v, k) for k, v in sorted(info["bom_status"]["by_status"].items())),
            info["position_rows"])
    if name == "schematic":
        t = info["round_trip"]
        return "%d sheets, PDF %d pages, round trip %s (%d nets, %d pads, %d components)" % (
            len(info["sheets"]) + 1, info["pdf_pages"], "matches" if t["ok"] else "MISMATCH",
            t["nets_compared"], t["pads_compared"], t["components_compared"])
    if name == "mechanical":
        return "exit %d: %s" % (info["exit_status"], info["result"][:150])
    if name == "quality":
        return "layout_quality.json / .md, %d review pictures" % len(info["review_pictures"])
    return ""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    ap.add_argument("--pindata", default=os.environ.get("GL1_PINDATA"),
                    help="directory with ST's open pin data (outside the repository); without it the pin "
                         "map check is PARTIAL")
    ap.add_argument("--stages", default=",".join(ALL_STAGES))
    ap.add_argument("--reroute", action="store_true", help="do not reuse a stored routing")
    ap.add_argument("--no-store", dest="store", action="store_false",
                    help="do not copy a complete fresh routing to routing.json next to this file")
    ap.add_argument("--time-limit", type=float, default=G.ROUTER_TIME_LIMIT,
                    help="seconds after which the router starts no new work")
    ap.add_argument("--mech-python", default="python3",
                    help="interpreter for mechanical/cad/board_import.py (needs cadquery)")
    ap.add_argument("--review-dpi", type=int, default=500)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    wanted = [s.strip() for s in args.stages.split(",") if s.strip()]
    unknown = [s for s in wanted if s not in STAGES]
    if unknown:
        ap.error("unknown stage(s): %s" % ", ".join(unknown))
    os.makedirs(args.out, exist_ok=True)
    design = G.gl1_main_design()
    run = {"stages_run": wanted, "seconds": {}}
    ctx = {"args": args, "run": run}
    summary = {"design": design.name, "stages": {}, "stages_run": wanted, "all_stages": list(ALL_STAGES)}
    t_all = time.time()
    passed = True
    for name in ALL_STAGES:
        if name not in wanted:
            continue
        say("[%s]" % name)
        t0 = time.time()
        try:
            ok, info = STAGES[name](design, args.out, ctx)
        except Exception as exc:                          # a crash is a failure, not a skip
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
    passed = passed and all(v is not False for v in crit.values())
    counts = netlist_stage.part_counts(design)
    summary.update(criteria=crit, passed=bool(passed), complete_run=complete, counts=counts)
    run["seconds"]["total"] = round(time.time() - t_all, 1)
    with open(os.path.join(args.out, "build_summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1, sort_keys=True, default=str)
        fh.write("\n")
    with open(os.path.join(args.out, "build_run.json"), "w", encoding="utf-8") as fh:
        json.dump(run, fh, indent=1, sort_keys=True)
        fh.write("\n")
    say("")
    say("=" * 100)
    say("GL-1 main board - %s: %d parts (%d on the BOM, %d bare copper, %d fiducials), %d nets"
        % (design.name, counts["parts_total"], counts["parts_on_the_bom"], counts["bare_copper_parts"],
           counts["fiducials"], counts["nets"]))
    say("=" * 100)
    for name in ALL_STAGES:
        info = summary["stages"].get(name)
        if info is None:
            say("%-10s %-8s" % (name, "not run"))
        else:
            say("%-10s %-8s %s" % (name, "PASS" if info["passed"] else "FAIL", stage_line(name, info)))
    say("-" * 100)
    for label, value in crit.items():
        say("%-66s %s" % (label, {True: "yes", False: "NO", None: "not checked"}[value]))
    say("-" * 100)
    rinfo = summary["stages"].get("rules", {})
    for label, ids in (("OPEN, NOT MET", rinfo.get("open_not_met", [])),
                       ("workaround", rinfo.get("workarounds", [])),
                       ("departure from the letter of the spec", rinfo.get("departures", []))):
        if ids:
            say("%s: %s" % (label, ", ".join(ids)))
    if passed and complete:
        say("GL-1 MAIN BOARD BUILD PASSED (%.0f s)%s" % (
            run["seconds"]["total"],
            " - with %d open contract(s) and %d workaround(s), see above"
            % (len(rinfo.get("open_not_met", [])), len(rinfo.get("workarounds", [])))
            if rinfo.get("open_not_met") or rinfo.get("workarounds") else ""))
    elif passed:
        say("stages %s passed (%.0f s) - not a complete run" % (", ".join(wanted), run["seconds"]["total"]))
    else:
        failed = [n for n, i in summary["stages"].items() if not i["passed"]]
        failed += [k for k, v in crit.items() if v is False]
        say("GL-1 MAIN BOARD BUILD FAILED: %s" % "; ".join(failed))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
