#!/usr/bin/python3
"""Fill the generated tables of NETLIST_NOTES.md (and of the cradle's
CRADLE_NOTES.md) from the design files, so that the notes cannot drift from
the netlist.

    /usr/bin/python3 -B electrical/gl1_main/update_notes.py [--check]

A generated table sits between two marker lines

    <!-- BEGIN GENERATED: NAME -->
    ...
    <!-- END GENERATED: NAME -->

and everything between them is replaced.  ``--check`` changes nothing and
exits 1 if a table in a notes file differs from what the design gives now.
``build_netlist.py`` of each board runs the update after a passing build.
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CRADLE = os.path.normpath(os.path.join(HERE, "..", "gl1_cradle"))
for _p in (os.path.normpath(os.path.join(HERE, "..", "tools")), HERE, CRADLE):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _esc(text):
    return str(text).replace("|", "/").replace("\n", " ")


def _status(row):
    return row[5] if len(row) > 5 else ("pass" if row[3] else "FAIL")


def rules_table(rows, head="What the specification says"):
    lines = ["| Rule | %s | Where it is in the netlist | Result |" % head, "|---|---|---|---|"]
    for r in rows:
        st = _status(r)
        lines.append("| %s | %s | %s%s | %s |" % (r[0], _esc(r[1]), _esc(r[2]),
                                                 (" *(%s)*" % _esc(r[4])) if r[4] else "",
                                                 st if st == "pass" else "**%s**" % st))
    return "\n".join(lines)


def rule_counts(rows, sections=("5", "5.1", "5.2")):
    order = ("pass", "departure", "open", "workaround", "FAIL")
    names = {"pass": "as specified",
             "departure": "departures from the letter of the spec (section %s)" % sections[0],
             "open": "open - NOT met (section %s)" % sections[1],
             "workaround": "workaround (section %s)" % sections[2], "FAIL": "failed"}
    parts = []
    for s in order:
        ids = [r[0] for r in rows if _status(r) == s]
        parts.append("%d %s%s" % (len(ids), names[s], (": " + ", ".join(ids)) if ids and s != "pass" else ""))
    return "**%d rows: %s.**" % (len(rows), "; ".join(parts))


def main_tables():
    import gl1_main_design as G
    import check_netlist_rules as R
    design = G.gl1_main_design()
    rows = sorted(G.pinmap_rows(), key=lambda r: (r["pad"], r["signal"] != "BOOT0"))
    pin = ["| Pad | Pin | Signal | Net | Mode | Function | Pull (MCU / board) | Initial state | Source |",
           "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        fn = r["function"] + ("" if r["af"] is None else " (AF%d)" % r["af"])
        pin.append("| %d | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["pad"], r["pin"], r["signal"], r["net"], r["mode"], fn, _esc(r["pull"]),
            _esc(r["initial_state"]), r["source"] + (" (was %s)" % r["was"] if r["was"] else "")))
    changed = [r for r in sorted(G.pinmap_rows(), key=lambda r: r["signal"]) if r["source"] == "CHANGED"]
    ch = ["| Signal | gl_pins.h | Netlist | Reason |", "|---|---|---|---|"]
    for r in changed:
        ch.append("| %s | %s | %s (pad %d) | %s |" % (r["signal"], r["was"], r["pin"], r["pad"], _esc(r["reason"])))
    same = sorted(r["signal"] for r in G.pinmap_rows() if r["source"] == "PROPOSED")
    counts = "%d rows: %d SPEC, %d PROPOSED (unchanged), %d CHANGED" % (
        len(rows), sum(1 for r in rows if r["source"] == "SPEC"), len(same), len(changed))
    balls = ["| Ball | Pin | Net |", "|---|---|---|"]
    for ball in sorted(G.BQ25101_BALLS):
        name = G.BQ25101_BALLS[ball][0]
        balls.append("| %s | %s | %s |" % (ball, name, design.pin_net("U9", name)))
    parts = [p for p in design.parts]
    summary = ("%d parts: %d on the BOM (%d fitted, %d not fitted), %d bare-copper footprints (%s), "
               "%d fiducials; %d nets" % (
                   len(parts), sum(1 for p in parts if p.in_bom),
                   sum(1 for p in parts if p.in_bom and not p.dnp),
                   sum(1 for p in parts if p.in_bom and p.dnp),
                   sum(1 for p in parts if not p.in_bom and "fiducial" not in p.footprint_name.lower()),
                   ", ".join(sorted((p.ref for p in parts if not p.in_bom
                                     and "fiducial" not in p.footprint_name.lower()),
                                    key=lambda s: (re.sub(r"\d", "", s), int(re.sub(r"\D", "", s) or 0)))),
                   sum(1 for p in parts if "fiducial" in p.footprint_name.lower()), len(design.nets)))
    rule_rows = R.rules(design)
    return {
        "RULES": rules_table(rule_rows, "What DESIGN_SPEC section 4 says"),
        "RULE_COUNTS": rule_counts(rule_rows),
        "FIRMWARE_NOTES": firmware_notes(),
        "SUPPLY_CHAIN": supply_chain_table(G),
        "PIN_TABLE": "\n".join(pin),
        "CHANGED_TABLE": "\n".join(ch),
        "PIN_COUNTS": counts + ". Unchanged PROPOSED pins: " + ", ".join(same) + ".",
        "BQ25101_BALLS": "\n".join(balls),
        "SUMMARY": summary,
    }


def firmware_notes():
    """The list check_pinmap.py exports to pinmap.json, numbered."""
    import check_pinmap as C
    return "\n".join("%d. %s" % (i, _esc(n)) for i, n in enumerate(C.FIRMWARE_NOTES, start=1))


def supply_chain_table(G):
    """Section 4.1: the cradle supply chain against the charger's input, from
    the PROVISIONAL numbers of gl1_main_design.SUPPLY_CHAIN."""
    lines = ["| Case | USB source | at the VBUS pad | VBUS_D (charger IN, U11 in) | against %.2f V |"
             % G.SUPPLY_CHAIN["charger_vin_min"], "|---|---|---|---|---|"]
    for name, src, pad, vd, margin in G.supply_chain_rows():
        lines.append("| %s | %.2f V | %.2f V | %.2f V | **%+.2f V** |" % (name, src, pad, vd, margin))
    return "\n".join(lines)


def cradle_tables():
    import gl1_cradle_design as C
    import check_cradle_rules as R
    design = C.gl1_cradle_design()
    parts = design.parts
    summary = ("%d parts: %d on the BOM (%d fitted, %d not fitted), %d bare-copper footprint (J2), "
               "%d fiducials; %d nets" % (
                   len(parts), sum(1 for p in parts if p.in_bom),
                   sum(1 for p in parts if p.in_bom and not p.dnp),
                   sum(1 for p in parts if p.in_bom and p.dnp),
                   sum(1 for p in parts if not p.in_bom and "fiducial" not in p.footprint_name.lower()),
                   sum(1 for p in parts if "fiducial" in p.footprint_name.lower()), len(design.nets)))
    rows = R.rules(design)
    return {"RULES": rules_table(rows), "SUMMARY": summary,
            "RULE_COUNTS": rule_counts(rows, sections=("6", "none", "none"))}


def apply(path, tables, check):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    new = text
    for name, body in tables.items():
        pat = re.compile(r"(<!-- BEGIN GENERATED: %s -->\n)(.*?)(<!-- END GENERATED: %s -->)"
                         % (re.escape(name), re.escape(name)), re.S)
        if not pat.search(new):
            continue
        new = pat.sub(lambda m: m.group(1) + body + "\n" + m.group(3), new)
    left = re.findall(r"<!-- BEGIN GENERATED: (\w+) -->", new)
    unknown = [n for n in left if n not in tables]
    if unknown:
        raise SystemExit("%s: no generator for table(s) %s" % (path, ", ".join(unknown)))
    if new != text and not check:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(new)
    return new != text


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="change nothing; exit 1 if a table is stale")
    ap.add_argument("--board", choices=("main", "cradle", "both"), default="both")
    args = ap.parse_args(argv)
    stale = []
    jobs = []
    if args.board in ("main", "both"):
        jobs.append((os.path.join(HERE, "NETLIST_NOTES.md"), main_tables))
    if args.board in ("cradle", "both"):
        jobs.append((os.path.join(CRADLE, "CRADLE_NOTES.md"), cradle_tables))
    for path, make in jobs:
        if not os.path.isfile(path):
            print("missing: %s" % path)
            stale.append(path)
            continue
        if apply(path, make(), args.check):
            stale.append(path)
            print(("STALE: %s" if args.check else "updated: %s") % path)
        else:
            print("up to date: %s" % path)
    return 1 if (args.check and stale) else 0


if __name__ == "__main__":
    sys.exit(main())
