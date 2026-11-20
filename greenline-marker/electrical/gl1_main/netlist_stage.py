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
import hashlib
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.normpath(os.path.join(HERE, "..", "tools"))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from gleda import board, checks, drc, outputs, schematic          # noqa: E402

#: Rev E: TWO status columns, because they answer two different questions.
#: * "Status" follows docs/SOURCING.md (its section 2 defines the two words): VERIFIED = a US
#:   source listing this exact part number was seen on the date given; PROVISIONAL = everything
#:   else.  It is copied from the row of docs/sourcing.csv with the same MPN; a part number
#:   that has no row is PROVISIONAL.  VERIFIED says nothing about the land pattern or pin table.
#: * "Design evidence" is the level of the DESIGN data of the line (pin table, land pattern,
#:   values): RESEARCH or PROVISIONAL, from Part.fields["Status"], with its note.
BOM_STATUS_COLUMNS = ("Item", "Qty", "References", "Value", "Description", "Footprint", "MPN",
                      "Manufacturer", "Distributor", "Distributor PN", "Unit Price", "DNP",
                      "Status", "Design evidence", "Design evidence note")
SOURCING_STATUSES = ("VERIFIED", "PROVISIONAL")


def say(msg=""):
    print(msg, flush=True)


STATUSES = ("pass", "departure", "open", "workaround", "FAIL")


def row_status(row):
    """Result of one rule row: the sixth element if the board's rule file gives
    one, else pass / FAIL from the test alone."""
    return row[5] if len(row) > 5 else ("pass" if row[3] else "FAIL")


def write_bom_with_status(design, path):
    """The toolchain's grouped BOM (``outputs.bom_groups``) plus, for every line, the sourcing
    status of its part number as docs/SOURCING.md has it (column "Status": VERIFIED /
    PROVISIONAL) and the evidence level of the design data (``Part.fields['Status']`` /
    ``['StatusNote']``, columns "Design evidence" / "Design evidence note").
    Returns (lines, {design evidence: line count}, {sourcing status: line count})."""
    by_ref = design.parts_by_ref
    groups = outputs.bom_groups(design)
    counts, src_counts = {}, {}
    sourcing = sourcing_rows()
    prefer = "cradle" if "cradle" in design.name else "main"
    SOURCING_MISMATCHES[:] = [m for m in SOURCING_MISMATCHES if not m.startswith(design.name + " ")]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(list(BOM_STATUS_COLUMNS) + list(SOURCING_COLUMNS))
        for g in groups:
            statuses = sorted({by_ref[r].fields.get("Status", "") for r in g["refs"]})
            notes = sorted({by_ref[r].fields.get("StatusNote", "") for r in g["refs"]} - {""})
            status = " / ".join(statuses) or "MISSING"
            counts[status] = counts.get(status, 0) + 1
            src_status, cells, problem = sourcing_cells(sourcing, g["mpn"], prefer,
                                                        refs=g["refs"], item=g["item"])
            if problem:
                SOURCING_MISMATCHES.append("%s item %s (%s): %s" % (design.name, g["item"],
                                                                    " ".join(g["refs"]), problem))
            src_counts[src_status] = src_counts.get(src_status, 0) + 1
            w.writerow([g["item"], g["qty"], " ".join(g["refs"]), g["value"], g["description"],
                        g["footprint"], g["mpn"], g["manufacturer"], g["distributor"],
                        g["distributor_pn"], "" if g["unit_price"] is None else "%.2f" % g["unit_price"],
                        "DNP" if g["dnp"] else "", src_status, status, "; ".join(notes)] + cells)
    return len(groups), counts, src_counts


def status_text(counts, src_counts):
    """One line for the build log: both status columns."""
    return "Status per docs/SOURCING.md: %s; design evidence: %s" % (
        ", ".join("%d %s" % (v, k) for k, v in sorted(src_counts.items())),
        ", ".join("%d %s" % (v, k) for k, v in sorted(counts.items()))) + (
        "; sourcing rows of docs/sourcing.csv out of step with the BOM: %d%s" % (
            len(SOURCING_MISMATCHES), "".join("\n    WARNING " + m for m in SOURCING_MISMATCHES)))


def bom_status_ok(counts, src_counts):
    """No line without a design evidence level; every sourcing status one of the two words of
    docs/SOURCING.md."""
    return counts.get("MISSING", 0) == 0 and all(k in SOURCING_STATUSES for k in src_counts)


ASSEMBLY_README_MARK = "ADDED BY THE BOARD BUILD (not by the toolchain)"


def extend_assembly_readme(out, name, off_board=()):
    """The toolchain's assembly README lists the files it wrote itself.  Append what this
    package adds to the folder: the status BOM and what its columns mean, and (``off_board``)
    the purchased items that are joined to the board but are on no board BOM.  Idempotent.
    Returns the path of the README."""
    path = os.path.join(out, "assembly", "README.txt")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if ASSEMBLY_README_MARK in text:
        text = text[:text.index(ASSEMBLY_README_MARK)].rstrip("\n") + "\n"
    lines = ["", ASSEMBLY_README_MARK, "-" * len(ASSEMBLY_README_MARK),
             "%s-bom-status.csv   the same grouped BOM with, for every line:" % name,
             "  Status                  sourcing status of the exact part number as docs/SOURCING.md has it:",
             "                          VERIFIED = a US source listing this part number was seen on the date in",
             "                          the last column (listed for sale, NOT a stock promise); PROVISIONAL =",
             "                          everything else. It says nothing about the land pattern or pin table.",
             "  Design evidence / note  RESEARCH or PROVISIONAL: how well the design data of the line (pin table,",
             "                          land pattern, value) is known. PROVISIONAL lines gate the board order.",
             "  Sourcing risk, alternates, sourcing row: copied from the row of docs/sourcing.csv that has the",
             "                          line's references (main-NN / cradle-NN = the BOM item number). The alternates",
             "                          are CANDIDATES named by the sourcing report, NOT approved parts: each is",
             "                          VERIFIED (a listing was seen) or PROVISIONAL as its text says, and none has",
             "                          been approved by the design owner (docs/SOURCING.md action A18).",
             "Read a live distributor page before ordering: every stock figure behind these columns is an",
             "undated snapshot."]
    if off_board:
        lines += ["", "OFF-BOARD ITEMS joined to this board (on no board BOM; they belong on the purchasing list",
                  "above the board BOMs, docs/SOURCING.md actions A11 / A12):"]
        lines += ["  " + l for l in off_board]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text + "\n".join(lines) + "\n")
    return path


def refresh_manifest(out, paths):
    """``<out>/outputs.json`` is written by the toolchain BEFORE this package adds the status
    BOM to the assembly folder and zips that folder again, so its entry for the assembly zip
    was stale and the status BOM was not in it.  Enter ``paths`` (files under ``out``) with
    their size and SHA-256, replacing an entry of the same path, then compare EVERY entry of
    the manifest with the file on disk.  Returns the list of entries that do not match (empty
    = the manifest is true)."""
    mpath = os.path.join(out, "outputs.json")
    with open(mpath, encoding="utf-8") as fh:
        data = json.load(fh)
    entries = {e["path"]: e for e in data.get("files", [])}
    for path in paths:
        with open(path, "rb") as fh:
            blob = fh.read()
        rel = os.path.relpath(path, out).replace(os.sep, "/")
        entries[rel] = {"path": rel, "bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}
    data["files"] = [entries[k] for k in sorted(entries)]
    data["files_added_after_the_toolchain"] = sorted(
        os.path.relpath(p, out).replace(os.sep, "/") for p in paths)
    with open(mpath, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, sort_keys=True)
        fh.write("\n")
    return verify_manifest(out)


def verify_manifest(out):
    """Every entry of ``<out>/outputs.json`` against the file on disk: [problem, ...]."""
    with open(os.path.join(out, "outputs.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    bad = []
    for e in data.get("files", []):
        full = os.path.join(out, e["path"])
        if not os.path.isfile(full):
            bad.append("%s: listed but missing" % e["path"])
            continue
        with open(full, "rb") as fh:
            blob = fh.read()
        if len(blob) != e["bytes"] or hashlib.sha256(blob).hexdigest() != e["sha256"]:
            bad.append("%s: size or SHA-256 differs from the manifest" % e["path"])
    return bad


#: REVIEW ADDITION: three columns copied from docs/sourcing.csv (read-only) so that the
#: availability doubts and the alternates the sourcing report names are visible on the BOM itself
#: (docs/SOURCING.md actions A4 and A18: the alternates column).
#: FINAL-AUDIT FIX: (1) the alternates are CANDIDATES - docs/SOURCING.md A18 says they are
#: "still PROVISIONAL, to be confirmed one by one before they are listed" - so the column no
#: longer says "approved"; (2) the row is found by the line's REFERENCES (the numbered row
#: main-NN / cradle-NN whose reference list equals the BOM line's), not by the first row with
#: the same part number: two lines with one part number (cradle SP1-4 and the unfitted SP5-7)
#: now each cite their own row, and a numbered row that names another part number, or whose
#: number is not the BOM item number, is reported (SOURCING_MISMATCHES) instead of hidden.
SOURCING_COLUMNS = ("Sourcing risk (docs/sourcing.csv)",
                    "Alternates named in docs/sourcing.csv (candidates, NOT approved; VERIFIED or "
                    "PROVISIONAL as each says)",
                    "Sourcing row / status / checked on")
SOURCING_CSV = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                                             "docs", "sourcing.csv"))
#: filled by write_bom_with_status: every BOM line whose sourcing row is not "the numbered row
#: with these references, this part number and this item number"
SOURCING_MISMATCHES = []
_NUMBERED = re.compile(r"^(main|cradle)-(\d+):\s*(.*)$")


def sourcing_rows(path=SOURCING_CSV):
    """{MPN: [row, ...]} of docs/sourcing.csv ({} when the file is not there)."""
    rows = {}
    if not os.path.exists(path):
        return rows
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.setdefault((r.get("mpn") or "").strip(), []).append(r)
    return rows


def _numbered_row(rows, prefer, refs):
    """(number, row) of the numbered row of board ``prefer`` whose references are exactly
    ``refs``; (None, None) if there is none."""
    want = set(refs)
    for hits in rows.values():
        for r in hits:
            m = _NUMBERED.match((r.get("bom_ref") or "").strip())
            if m and m.group(1) == prefer:
                have = set(m.group(3).replace("(DNP)", " ").split())
                if have == want:
                    return int(m.group(2)), r
    return None, None


def sourcing_cells(rows, mpn, prefer="main", refs=None, item=None):
    """(sourcing status, [risk, alternates, row / status / date], problem) of one BOM line.

    The row is the numbered row (main-NN / cradle-NN) of docs/sourcing.csv with the line's
    references.  The status is the word that row has, PROVISIONAL when the row names another
    part number than the BOM or when there is no row at all.  ``problem`` is None when the row
    was found by its references, names the BOM's part number and carries the BOM's item
    number; else it is a sentence saying what is out of step (the caller collects them).
    Without ``refs`` (or when no numbered row has them) the row is looked up by part number,
    as before the final audit, and that is reported as a problem."""
    mpn = (mpn or "").strip()
    number, r = _numbered_row(rows, prefer, refs) if refs else (None, None)
    problem = None
    if r is not None:
        label = "%s-%02d" % (prefer, number)
        row_mpn = (r.get("mpn") or "").strip()
        if row_mpn != mpn:
            problem = "sourcing row %s names %s, the BOM %s" % (label, row_mpn, mpn)
            return "PROVISIONAL", ["SOURCING ROW %s NAMES ANOTHER PART NUMBER (%s)" % (label, row_mpn), "",
                                   "%s / part number differs / %s" % (label, (r.get("checked_on") or "").strip())], problem
        if item is not None and int(item) != number:
            problem = "sourcing row %s is not numbered like the BOM item (%s)" % (label, item)
    else:
        hits = rows.get(mpn, [])
        if not hits:
            return "PROVISIONAL", ["NOT IN docs/sourcing.csv", "", ""], "no row in docs/sourcing.csv"
        # this board's own row (main-NN / cradle-NN) first, then the other board's, then
        # replacement / candidate rows
        def rank(x):
            ref = (x.get("bom_ref") or "")
            return (not ref.startswith(prefer), not ref.startswith(("main", "cradle")))
        r = sorted(hits, key=rank)[0]
        label = (r.get("bom_ref") or r.get("item") or "").split(":")[0].strip()
        problem = "no numbered row with these references; row %r found by part number" % label
        label += " (found by part number)"
    status = (r.get("status") or "").strip()
    return (status if status in SOURCING_STATUSES else "PROVISIONAL",
            [(r.get("risk") or "").strip(), (r.get("alternative") or "").strip(),
             "%s / %s / %s" % (label, status, (r.get("checked_on") or "").strip())], problem)


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
    lines, status_counts, src_counts = write_bom_with_status(design, os.path.join(out, name + "-bom-status.csv"))
    with open(os.path.join(out, name + "-nominal-mechanical.json"), "w", encoding="utf-8") as fh:
        json.dump(outputs.mechanical_data(design), fh, indent=1, sort_keys=True)
        fh.write("\n")
    counts = part_counts(design)
    say("  %s-netlist.json, %s-bom-status.csv (%d lines: %s), %s-nominal-mechanical.json"
        % (name, name, lines, status_text(status_counts, src_counts), name))
    bom_ok = bom_status_ok(status_counts, src_counts)
    summary["stages"]["exports"] = {"passed": bom_ok, "bom_lines": lines,
                                    "bom_lines_by_status": src_counts,
                                    "bom_lines_by_design_evidence": status_counts}
    passed = passed and bom_ok
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
