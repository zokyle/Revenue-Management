#!/usr/bin/python3
"""GL-1 cradle board: layout, routing and outputs in one command.

    /usr/bin/python3 -B electrical/gl1_cradle/build_gl1_cradle.py

Everything goes to ``electrical/gl1_cradle/out/`` (``--out``).  Stages, each
recorded in ``out/build_summary.json``:

 1. ``checks``     ``gleda.checks.run_checks``, defaults, nothing switched off   -> 0 errors
 2. ``rules``      the cradle's table "specification / YAML -> board"
                   (``check_cradle_rules.py``) and its seeded-defect self-test
 3. ``board``      ``gl1_cradle.kicad_pcb`` / ``.kicad_pro`` / ``.kicad_dru`` and the
                   silkscreen legend (pin order; ``gl1_main/silk_text.py``)
 4. ``route``      the toolchain's router (about a second: 29 connections)
 5. ``drc``        tracks into the board, zone fill, KiCad DRC, nothing excluded   -> 0 errors, 0 unconnected
 6. ``outputs``    Gerber, drill, position, BOM (and a BOM with a status column),
                   netlist / mechanical JSON, STEP, renders, fab README
 7. ``schematic``  sheets, PDF, PNG, netlist round trip through kicad-cli
 8. ``quality``    a few figures measured on the copper and review pictures

Exit status 0 only if every stage passed.  No fabrication data is written for
a board that is not completely routed or not DRC-clean.
"""
import argparse
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = os.path.normpath(os.path.join(HERE, "..", "gl1_main"))
TOOLS = os.path.normpath(os.path.join(HERE, "..", "tools"))
for _p in (TOOLS, MAIN, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import gl1_cradle_design as G                                             # noqa: E402
import check_cradle_rules                                                 # noqa: E402
import netlist_stage                                                      # noqa: E402
import layout_quality                                                     # noqa: E402
import silk_text                                                          # noqa: E402
from gleda import board, checks, drc, outputs, router, routeplot, schematic   # noqa: E402

ALL_STAGES = ("checks", "rules", "board", "route", "drc", "outputs", "schematic", "quality")


def say(msg=""):
    print(msg, flush=True)


def stage_checks(design, out, ctx):
    report = checks.run_checks(design)
    with open(os.path.join(out, "checks.txt"), "w", encoding="utf-8") as fh:
        fh.write(report.text() + "\n")
    say("  %d error(s), %d warning(s)" % (len(report.errors), len(report.warnings)))
    for f in (report.errors + report.warnings)[:30]:
        say("  %s [%s] %s" % (f.severity.upper(), f.code, f.message))
    return report.ok, {"errors": len(report.errors), "warnings": len(report.warnings),
                       "warnings_by_code": report.codes("warning"),
                       "warning_messages": [f.message for f in report.warnings]}


def stage_rules(design, out, ctx):
    rows = check_cradle_rules.rules(design)
    status = netlist_stage.row_status
    by = {s: [r[0] for r in rows if status(r) == s] for s in netlist_stage.STATUSES}
    for r in rows:
        if status(r) == "FAIL":
            say("  FAIL %s: %s" % (r[0], r[2]))
    with open(os.path.join(out, "spec_rules.md"), "w", encoding="utf-8") as fh:
        fh.write("| Rule | What the specification says | Where it is on the board | Result |\n|---|---|---|---|\n")
        for r in rows:
            st = status(r)
            fh.write("| %s | %s | %s%s | %s |\n" % (r[0], r[1], r[2], (" *(%s)*" % r[4]) if r[4] else "",
                                                     st if st == "pass" else "**%s**" % st))
    lines, missed = check_cradle_rules.selftest()
    say("  %d rows: %s; self-test: %d seeded defects, %d missed"
        % (len(rows), ", ".join("%d %s" % (len(by[s]), s) for s in netlist_stage.STATUSES), len(lines), missed))
    return not by["FAIL"] and not missed, {
        "rows": len(rows), "failed": by["FAIL"], "as_specified": len(by["pass"]),
        "departures": by["departure"], "open_not_met": by["open"], "workarounds": by["workaround"],
        "selftest_defects": len(lines), "selftest_missed": missed}


def stage_board(design, out, ctx):
    files = board.build_board(design, out)
    ctx["files"] = files
    n = silk_text.add_silk_text(files.pcb, [silk_text.SilkText(*t[:3], **t[3]) for t in G.silk_legend()])
    say("  %s, %d silkscreen legend texts" % (os.path.relpath(files.pcb, out), n))
    return True, {"pcb": os.path.basename(files.pcb), "legend_texts": n}


def stage_route(design, out, ctx):
    options = router.RouterOptions(time_limit=ctx["args"].time_limit, **dict(G.ROUTER_OPTIONS))
    result = router.route(design, options)
    router.save_routing(os.path.join(out, "routing.json"), design, result, options)
    ctx["route"] = result
    routeplot.plot(design, result.tracks, result.vias, os.path.join(out, "routing_debug.png"), dpi=200)
    say("  " + result.summary())
    for u in result.unrouted:
        say("  UNROUTED %s: %s  [%s]" % (u.net, u.pieces, u.reason))
    for v in result.audit.violations[:10]:
        say("  AUDIT %s" % (v,))
    return result.complete, {
        "connections_total": result.connections_total, "connections_routed": result.connections_routed,
        "routed_percent": round(100.0 * result.routed_fraction, 3), "vias": len(result.vias),
        "tracks": len(result.tracks), "track_length_mm": result.stats.get("track_length_mm"),
        "audit_violations": len(result.audit.violations), "unrouted": [u.to_dict() for u in result.unrouted],
        "router_options": dict(G.ROUTER_OPTIONS)}


def stage_drc(design, out, ctx):
    files, result = ctx.get("files"), ctx.get("route")
    if files is None or result is None:
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
                "tampered": list(getattr(res, "tampered", []) or [])}


def stage_outputs(design, out, ctx):
    route = ctx.get("route")
    if route is None or not route.complete:
        say("  the board is not completely routed: no fabrication data is written")
        return False, {"error": "routing incomplete"}
    ok, info = outputs.build_demo_stage(design, out, ctx)
    if "error" in info:
        return False, info
    lines, counts = netlist_stage.write_bom_with_status(
        design, os.path.join(out, "assembly", design.name + "-bom-status.csv"))
    outputs.write_zip(os.path.join(out, "assembly"), os.path.join(out, design.name + "-assembly.zip"))
    say("  BOM with status column: %d lines (%s)" % (lines, ", ".join(
        "%d %s" % (v, k) for k, v in sorted(counts.items()))))
    info["bom_status"] = {"lines": lines, "by_status": counts}
    return ok and counts.get("MISSING", 0) == 0, info


def stage_schematic(design, out, ctx):
    return schematic.build_demo_stage(design, out, ctx)


def stage_quality(design, out, ctx):
    files = ctx.get("files")
    pcb = files.pcb if files is not None else os.path.join(out, design.name + ".kicad_pcb")
    tracks, vias = board.read_routing(pcb)
    q = layout_quality.quality(design, tracks, vias)
    with open(os.path.join(out, "layout_quality.json"), "w", encoding="utf-8") as fh:
        json.dump(q, fh, indent=1, sort_keys=True)
        fh.write("\n")
    text = layout_quality.markdown(q)
    with open(os.path.join(out, "layout_quality.md"), "w", encoding="utf-8") as fh:
        fh.write(text)
    for line in text.splitlines():
        say("  " + line)
    rdir = os.path.join(out, "review")
    if os.path.isdir(rdir):
        shutil.rmtree(rdir)
    os.makedirs(rdir)
    bounds = outputs.edge_bounds(design)
    made = []
    for name, layers, mirror in (("copper-F_Cu", ["F.Cu", "Edge.Cuts"], False),
                                 ("copper-B_Cu", ["B.Cu", "Edge.Cuts"], True),
                                 ("assembly-top", ["F.Fab", "F.SilkS", "F.Mask", "Edge.Cuts"], False),
                                 ("assembly-bottom", ["B.Fab", "B.SilkS", "B.Mask", "Edge.Cuts"], True)):
        png = os.path.join(rdir, "%s-%s.png" % (design.name, name))
        outputs.render_view(pcb, png, layers, bounds, mirror=mirror, dpi=ctx["args"].review_dpi)
        made.append(os.path.basename(png))
    say("  review pictures: %s" % ", ".join(made))
    return True, {"figures": q, "review_pictures": made}


STAGES = {"checks": stage_checks, "rules": stage_rules, "board": stage_board, "route": stage_route,
          "drc": stage_drc, "outputs": stage_outputs, "schematic": stage_schematic, "quality": stage_quality}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    ap.add_argument("--stages", default=",".join(ALL_STAGES))
    ap.add_argument("--time-limit", type=float, default=600.0)
    ap.add_argument("--review-dpi", type=int, default=500)
    args = ap.parse_args(argv)
    wanted = [s.strip() for s in args.stages.split(",") if s.strip()]
    os.makedirs(args.out, exist_ok=True)
    design = G.gl1_cradle_design()
    ctx = {"args": args}
    summary = {"design": design.name, "stages": {}, "stages_run": wanted}
    seconds = {}
    passed = True
    t_all = time.time()
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
        summary["stages"][name] = info
        seconds[name] = round(time.time() - t0, 1)
        say("  -> %s (%.1f s)" % ("PASS" if ok else "FAIL", seconds[name]))
        passed = passed and bool(ok)
    st = summary["stages"]
    crit = {
        "design checks: 0 errors": st.get("checks", {}).get("errors") == 0 if "checks" in st else None,
        "100 % of the connections routed, audit clean": (
            st["route"].get("routed_percent") == 100.0 and not st["route"].get("unrouted")
            and st["route"].get("audit_violations") == 0) if "route" in st else None,
        "KiCad DRC: 0 errors, 0 unconnected, nothing excluded": (
            st["drc"].get("errors") == 0 and st["drc"].get("unconnected") == 0
            and not st["drc"].get("tampered")) if "drc" in st else None,
        "outputs verified against the model": (not st["outputs"].get("problems", ["x"])
                                               and bool(st["outputs"].get("drc_clean"))) if "outputs" in st else None,
        "schematic netlist round trip matches": bool(st["schematic"].get("round_trip", {}).get("ok"))
        if "schematic" in st else None,
    }
    passed = passed and all(v is not False for v in crit.values())
    counts = netlist_stage.part_counts(design)
    seconds["total"] = round(time.time() - t_all, 1)
    summary.update(criteria=crit, passed=bool(passed), counts=counts, complete_run=wanted == list(ALL_STAGES))
    with open(os.path.join(args.out, "build_summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1, sort_keys=True, default=str)
        fh.write("\n")
    with open(os.path.join(args.out, "build_run.json"), "w", encoding="utf-8") as fh:
        json.dump({"seconds": seconds, "stages_run": wanted}, fh, indent=1, sort_keys=True)
        fh.write("\n")
    say("")
    say("=" * 96)
    say("GL-1 cradle board - %s: %d parts (%d on the BOM, %d bare copper, %d fiducials), %d nets"
        % (design.name, counts["parts_total"], counts["parts_on_the_bom"], counts["bare_copper_parts"],
           counts["fiducials"], counts["nets"]))
    say("=" * 96)
    for name in ALL_STAGES:
        info = st.get(name)
        say("%-10s %s" % (name, "not run" if info is None else ("PASS" if info["passed"] else "FAIL")
                          + ("  " + str(info["error"]) if info is not None and "error" in info else "")))
    say("-" * 96)
    for label, value in crit.items():
        say("%-60s %s" % (label, {True: "yes", False: "NO", None: "not checked"}[value]))
    say("-" * 96)
    if passed and summary["complete_run"]:
        say("GL-1 CRADLE BOARD BUILD PASSED (%.0f s)" % seconds["total"])
    elif passed:
        say("stages %s passed - not a complete run" % ", ".join(wanted))
    else:
        say("GL-1 CRADLE BOARD BUILD FAILED")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
