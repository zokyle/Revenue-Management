"""The NETLIST stage of a GL-1 board: everything that can be judged before
there is copper.  Used by ``gl1_main/build_netlist.py`` and
``gl1_cradle/build_netlist.py``.

Stages (each one recorded in ``<out>/netlist_summary.json``):

1. ``checks``     ``gleda.checks.run_checks(design)`` with its defaults - electrical
                  rules, BOM fields, footprints, placement, decoupling.  Nothing
                  is switched off; the stage passes with 0 errors and lists every
                  warning.
2. ``rules``      (optional) the board's own table "specification -> netlist", and
                  (optional) its self-test: seeded defects that must each fail a row.
                  A row is ``pass``, ``departure`` (implemented differently from the
                  letter of the spec), ``open`` (a contract that is NOT met and
                  cannot be met inside this package), ``workaround`` or ``FAIL``.
                  Only ``FAIL`` fails the stage; the other non-pass results are
                  counted, written to the summary and printed in the closing
                  lines - they are never shown as "pass".
3. ``pinmap``     (optional) the pin-map proof, run in its own interpreter with ``-I``.
4. ``schematic``  ``gleda.schematic``: sheets, PDF, PNG previews and the netlist
                  round trip through kicad-cli (KiCad's netlist of the drawing
                  must equal the model).
5. ``unrouted``   the board file WITHOUT tracks (``<out>/unrouted/``) through KiCad's
                  zone fill and DRC.  KiCad then judges what exists before
                  routing: the land patterns against the rule set (pad to pad,
                  pad to hole), courtyards, keep-outs, distances to the edge.
                  Unconnected items are expected (nothing is routed) and
                  counted; every other error fails the stage.  This is NOT the
                  DRC of a routed board.
6. ``exports``    netlist JSON, bill of materials WITH a status column, and the
                  mechanical JSON of the NOMINAL placement.

Nothing is routed: that is the layout step.  The mechanical JSON goes to
``<out>`` under the name ``<design>-nominal-mechanical.json`` - deliberately
NOT where ``mechanical/cad/board_import.py`` looks for the real board.
"""
import csv
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.normpath(os.path.join(HERE, "..", "tools"))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from gleda import board, checks, drc, outputs, schematic          # noqa: E402

BOM_STATUS_COLUMNS = ("Item", "Qty", "References", "Value", "Description", "Footprint", "MPN",
                      "Manufacturer", "Distributor", "Distributor PN", "Unit Price", "DNP",
                      "Status", "Status note")


def say(msg=""):
    print(msg, flush=True)


STATUSES = ("pass", "departure", "open", "workaround", "FAIL")


def row_status(row):
    """Result of one rule row: the sixth element if the board's rule file gives
    one, else pass / FAIL from the test alone."""
    return row[5] if len(row) > 5 else ("pass" if row[3] else "FAIL")


def write_bom_with_status(design, path):
    """The toolchain's grouped BOM (``outputs.bom_groups``) plus the evidence
    status of every line (``Part.fields['Status']`` / ``['StatusNote']``).
    Returns (lines, {status: line count})."""
    by_ref = design.parts_by_ref
    groups = outputs.bom_groups(design)
    counts = {}
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(BOM_STATUS_COLUMNS)
        for g in groups:
            statuses = sorted({by_ref[r].fields.get("Status", "") for r in g["refs"]})
            notes = sorted({by_ref[r].fields.get("StatusNote", "") for r in g["refs"]} - {""})
            status = " / ".join(statuses) or "MISSING"
            counts[status] = counts.get(status, 0) + 1
            w.writerow([g["item"], g["qty"], " ".join(g["refs"]), g["value"], g["description"],
                        g["footprint"], g["mpn"], g["manufacturer"], g["distributor"],
                        g["distributor_pn"], "" if g["unit_price"] is None else "%.2f" % g["unit_price"],
                        "DNP" if g["dnp"] else "", status, "; ".join(notes)])
    return len(groups), counts


def part_counts(design):
    parts = design.parts
    fid = [p for p in parts if "fiducial" in p.footprint_name.lower()]
    return {
        "parts_total": len(parts),
        "parts_on_the_bom": sum(1 for p in parts if p.in_bom),
        "parts_fitted": sum(1 for p in parts if p.in_bom and not p.dnp),
        "parts_dnp": sum(1 for p in parts if p.in_bom and p.dnp),
        "bare_copper_parts": sum(1 for p in parts if not p.in_bom and p not in fid),
        "fiducials": len(fid),
        "top_side": sum(1 for p in parts if p.side == "top"),
        "bottom_side": sum(1 for p in parts if p.side == "bottom"),
        "nets": len(design.nets),
        "pads_on_nets": sum(len(design.net_pads(n)) for n in design.nets),
        "no_connect_pins": len(design.no_connects)
        + sum(1 for p in parts for pin in p.pins.values() if pin.etype == "nc"),
        "net_classes": {name: sum(1 for n in design.nets.values() if n.netclass == name)
                        for name in sorted(design.netclasses)},
    }


def run(design, out, *, rules=None, rules_selftest=None, pinmap_cmd=None, title=None):
    """Run the stages; returns the process exit code (0 = every stage passed).

    ``rules``           callable(design) -> rows as in check_netlist_rules.rules, or None
    ``rules_selftest``  callable() -> (lines, number of seeded defects missed), or None
    ``pinmap_cmd``      argv of the pin-map proof (run as a subprocess), or None
    """
    os.makedirs(out, exist_ok=True)
    summary = {"design": design.name, "stage": "netlist (no copper)", "stages": {}}
    passed = True

    # ---- 1 checks ------------------------------------------------------------------------
    say("[checks] gleda.checks.run_checks, defaults, nothing switched off")
    report = checks.run_checks(design)
    with open(os.path.join(out, "checks.txt"), "w", encoding="utf-8") as fh:
        fh.write(report.text())
    with open(os.path.join(out, "checks.json"), "w", encoding="utf-8") as fh:
        json.dump(report.to_dict(), fh, indent=1, sort_keys=True)
        fh.write("\n")
    say("  %d error(s), %d warning(s)" % (len(report.errors), len(report.warnings)))
    for f in (report.errors + report.warnings)[:40]:
        say("  %s" % f)
    summary["stages"]["checks"] = {"passed": report.ok, "errors": len(report.errors),
                                   "warnings": len(report.warnings),
                                   "errors_by_code": report.codes("error"),
                                   "warnings_by_code": report.codes("warning")}
    passed = passed and report.ok

    # ---- 2 spec rules ---------------------------------------------------------------------
    if rules is not None:
        say("[rules] specification -> netlist")
        rows = rules(design)
        by_status = {s: [r[0] for r in rows if row_status(r) == s] for s in STATUSES}
        bad = [r for r in rows if row_status(r) == "FAIL"]
        for r in bad:
            say("  FAIL %s: %s" % (r[0], r[2]))
        for s in ("open", "workaround"):
            for r in rows:
                if row_status(r) == s:
                    say("  %s %s: %s" % (s.upper(), r[0], r[4]))
        say("  %d rows: %s" % (len(rows), ", ".join("%d %s" % (len(by_status[s]), s) for s in STATUSES)))
        with open(os.path.join(out, "spec_rules.md"), "w", encoding="utf-8") as fh:
            fh.write("| Spec rule | What the specification says | Where it is in the netlist | Result |\n"
                     "|---|---|---|---|\n")
            for r in rows:
                st = row_status(r)
                fh.write("| %s | %s | %s%s | %s |\n" % (r[0], r[1], r[2], (" *(%s)*" % r[4]) if r[4] else "",
                                                         st if st == "pass" else "**%s**" % st))
            fh.write("\n%d rows: %s\n" % (len(rows), ", ".join(
                "%d %s%s" % (len(by_status[s]), s, (" (%s)" % ", ".join(by_status[s]))
                             if by_status[s] and s != "pass" else "") for s in STATUSES)))
        summary["stages"]["rules"] = {"passed": not bad, "rows": len(rows),
                                      "failed": [r[0] for r in bad],
                                      "as_specified": len(by_status["pass"]),
                                      "departures": by_status["departure"], "open_not_met": by_status["open"],
                                      "workarounds": by_status["workaround"]}
        passed = passed and not bad
        if rules_selftest is not None:
            st_lines, missed = rules_selftest()
            say("  self-test: %d seeded defects, %d caught, %d missed"
                % (len(st_lines), len(st_lines) - missed, missed))
            for line in st_lines:
                if "MISSED" in line:
                    say(line)
            summary["stages"]["rules"].update(selftest_defects=len(st_lines), selftest_missed=missed,
                                              passed=not bad and not missed)
            passed = passed and not missed

    # ---- 3 pin map ---------------------------------------------------------------------------
    if pinmap_cmd is not None:
        say("[pinmap] %s" % " ".join(pinmap_cmd))
        proc = subprocess.run(pinmap_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        tail = [line for line in proc.stdout.splitlines()
                if line.startswith(("RESULT", "SELF-TEST", "PARTIAL", "data:", "  FAIL", "  MISSED"))]
        for line in tail:
            say("  " + line)
        say("  exit status %d" % proc.returncode)
        summary["stages"]["pinmap"] = {"passed": proc.returncode == 0, "exit_status": proc.returncode,
                                       "lines": tail}
        passed = passed and proc.returncode == 0

    # ---- 4 schematic ----------------------------------------------------------------------------
    say("[schematic] sheets, PDF, netlist round trip through kicad-cli")
    try:
        ok, info = schematic.build_demo_stage(design, out, {})
    except Exception as exc:                          # a crash is a failure, not a skip
        import traceback
        traceback.print_exc()
        ok, info = False, {"error": "%s: %s" % (type(exc).__name__, exc)}
    trip = info.get("round_trip", {})
    summary["stages"]["schematic"] = {
        "passed": bool(ok), "sheets": len(info.get("sheets", [])) + 1 if "sheets" in info else None,
        "pdf_pages": info.get("pdf_pages"), "round_trip_ok": trip.get("ok"),
        "nets_compared": trip.get("nets_compared"), "pads_compared": trip.get("pads_compared"),
        "components_compared": trip.get("components_compared"),
        "problems": trip.get("problems", [])[:20], "error": info.get("error")}
    passed = passed and bool(ok)

    # ---- 5 bare board through KiCad's DRC ------------------------------------------------------------
    say("[unrouted] board without tracks: KiCad zone fill + DRC (not a routed-board DRC)")
    sub = os.path.join(out, "unrouted")
    os.makedirs(sub, exist_ok=True)
    try:
        files = board.build_board(design, sub)
        res = drc.run_drc(files.pcb, json_path=os.path.join(sub, "drc.json"))
        try:
            drc.assert_clean(res, allow_unconnected=True)
            clean, problem = True, None
        except drc.DrcError as exc:
            clean, problem = False, str(exc)
        say("  %s" % res.summary())
        if problem:
            for line in problem.splitlines()[:12]:
                say("  " + line)
        summary["stages"]["unrouted"] = {
            "passed": clean, "errors": sum(res.errors_by_type.values()),
            "errors_by_type": dict(res.errors_by_type), "warnings_by_type": dict(res.warnings_by_type),
            "unconnected": res.unconnected_count, "tampered": list(getattr(res, "tampered", []) or [])}
    except Exception as exc:                          # a crash is a failure, not a skip
        import traceback
        traceback.print_exc()
        clean = False
        summary["stages"]["unrouted"] = {"passed": False, "error": "%s: %s" % (type(exc).__name__, exc)}
    passed = passed and clean

    # ---- 6 exports ---------------------------------------------------------------------------------
    say("[exports]")
    name = design.name
    with open(os.path.join(out, name + "-netlist.json"), "w", encoding="utf-8") as fh:
        json.dump(outputs.netlist_data(design), fh, indent=1, sort_keys=True)
        fh.write("\n")
    lines, status_counts = write_bom_with_status(design, os.path.join(out, name + "-bom-status.csv"))
    with open(os.path.join(out, name + "-nominal-mechanical.json"), "w", encoding="utf-8") as fh:
        json.dump(outputs.mechanical_data(design), fh, indent=1, sort_keys=True)
        fh.write("\n")
    counts = part_counts(design)
    say("  %s-netlist.json, %s-bom-status.csv (%d lines: %s), %s-nominal-mechanical.json"
        % (name, name, lines, ", ".join("%d %s" % (v, k) for k, v in sorted(status_counts.items())), name))
    missing = status_counts.get("MISSING", 0)
    summary["stages"]["exports"] = {"passed": missing == 0, "bom_lines": lines,
                                    "bom_lines_by_status": status_counts}
    passed = passed and missing == 0
    summary["counts"] = counts
    summary["passed"] = bool(passed)
    with open(os.path.join(out, "netlist_summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1, sort_keys=True)
        fh.write("\n")

    say("")
    say("=" * 78)
    say("%s - netlist stage: %d parts (%d on the BOM, %d bare-copper, %d fiducials), %d nets"
        % (title or name, counts["parts_total"], counts["parts_on_the_bom"],
           counts["bare_copper_parts"], counts["fiducials"], counts["nets"]))
    say("=" * 78)
    for stage, info in summary["stages"].items():
        extra = ""
        if stage == "checks":
            extra = "%d errors, %d warnings" % (info["errors"], info["warnings"])
        elif stage == "rules":
            extra = "%d rows: %d as specified, %d departures, %d open (not met), %d workaround, %d failed" % (
                info["rows"], info["as_specified"], len(info["departures"]), len(info["open_not_met"]),
                len(info["workarounds"]), len(info["failed"]))
            if "selftest_defects" in info:
                extra += "; self-test %d of %d seeded defects caught" % (
                    info["selftest_defects"] - info["selftest_missed"], info["selftest_defects"])
        elif stage == "pinmap":
            extra = "; ".join(l for l in info["lines"] if l.startswith(("RESULT", "SELF-TEST")))
        elif stage == "schematic":
            extra = "%s sheets, PDF %s pages, round trip %s (%s nets, %s pads, %s components)" % (
                info["sheets"], info["pdf_pages"], "matches" if info["round_trip_ok"] else "MISMATCH",
                info["nets_compared"], info["pads_compared"], info["components_compared"])
        elif stage == "unrouted":
            extra = info.get("error") or (
                "KiCad DRC on the board without tracks: %d errors, %d unconnected (expected), warnings %s"
                % (info["errors"], info["unconnected"], info["warnings_by_type"] or "none"))
        elif stage == "exports":
            extra = "BOM %d lines" % info["bom_lines"]
        say("%-10s %-5s %s" % (stage, "PASS" if info["passed"] else "FAIL", extra))
    say("-" * 78)
    rinfo = summary["stages"].get("rules", {})
    loose = [("OPEN, NOT MET", rinfo.get("open_not_met", [])), ("workaround", rinfo.get("workarounds", [])),
             ("departure from the letter of the spec", rinfo.get("departures", []))]
    for label, ids in loose:
        if ids:
            say("%s: %s" % (label, ", ".join(ids)))
    summary["open_items"] = list(rinfo.get("open_not_met", []))
    with open(os.path.join(out, "netlist_summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1, sort_keys=True)
        fh.write("\n")
    if passed and (rinfo.get("open_not_met") or rinfo.get("workarounds")):
        say("NETLIST STAGE PASSED - no check failed, BUT %d contract(s) are open (not met) and %d workaround(s) "
            "are in place: see the lines above and the board's notes" % (len(rinfo.get("open_not_met", [])),
                                                                         len(rinfo.get("workarounds", []))))
    else:
        say("NETLIST STAGE %s" % ("PASSED" if passed else "FAILED"))
    return 0 if passed else 1
