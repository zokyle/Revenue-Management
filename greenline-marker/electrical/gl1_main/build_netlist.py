#!/usr/bin/python3
"""GL-1 main board, NETLIST stage: checks, spec rules, pin map, schematic round trip.

    /usr/bin/python3 -B electrical/gl1_main/build_netlist.py --pindata DIR

``DIR`` is the directory with ST's open pin data (see ``check_pinmap.py``;
without it the pin map is checked against the KiCad symbol only and the
result is PARTIAL).  Everything is written to ``electrical/gl1_main/netlist_out/``
(``--out``); ``pinmap.json`` is written next to this file and the generated
tables of ``NETLIST_NOTES.md`` are refreshed (``update_notes.py``).  Exit status 0
only if every stage passed.  See ``netlist_stage.py`` for what the stages are.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import gl1_main_design as G           # noqa: E402
import check_netlist_rules            # noqa: E402
import netlist_stage                  # noqa: E402
import update_notes                   # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pindata", default=os.environ.get("GL1_PINDATA"),
                    help="directory with ST's open pin data (outside the repository)")
    ap.add_argument("--out", default=os.path.join(HERE, "netlist_out"))
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    cmd = [sys.executable, "-I", "-B", os.path.join(HERE, "check_pinmap.py"), "--export",
           "--selftest", "--report", os.path.join(args.out, "pinmap_check.txt")]
    if args.pindata:
        cmd += ["--pindata", args.pindata]
    code = netlist_stage.run(G.gl1_main_design(), args.out, rules=check_netlist_rules.rules,
                             rules_selftest=check_netlist_rules.selftest,
                             pinmap_cmd=cmd, title="GL-1 main board")
    if code == 0:                         # keep the generated tables of NETLIST_NOTES.md in step
        update_notes.main(["--board", "main"])
    return code


if __name__ == "__main__":
    sys.exit(main())
