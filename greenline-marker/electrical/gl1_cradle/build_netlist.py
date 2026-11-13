#!/usr/bin/python3
"""GL-1 cradle board, NETLIST stage: checks, cradle rules, schematic round trip.

    /usr/bin/python3 -B electrical/gl1_cradle/build_netlist.py

Everything is written to ``electrical/gl1_cradle/netlist_out/`` (``--out``).
Exit status 0 only if every stage passed.  The stages are those of
``electrical/gl1_main/netlist_stage.py`` (there is no MCU, so no pin map).
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.normpath(os.path.join(HERE, "..", "gl1_main")), HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import gl1_cradle_design as G         # noqa: E402
import check_cradle_rules             # noqa: E402
import netlist_stage                  # noqa: E402
import update_notes                   # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=os.path.join(HERE, "netlist_out"))
    args = ap.parse_args(argv)
    code = netlist_stage.run(G.gl1_cradle_design(), args.out, rules=check_cradle_rules.rules,
                             rules_selftest=check_cradle_rules.selftest, title="GL-1 cradle board")
    if code == 0:                         # keep the generated tables of CRADLE_NOTES.md in step
        update_notes.main(["--board", "cradle"])
    return code


if __name__ == "__main__":
    sys.exit(main())
