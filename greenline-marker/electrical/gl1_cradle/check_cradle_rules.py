#!/usr/bin/python3
"""DESIGN_SPEC section 4 "Cradle board (E6)", the cradle block of
design/master_params.yaml and the cradle task, row by row, against the
netlist of ``gl1_cradle_design.py``.

    /usr/bin/python3 -B electrical/gl1_cradle/check_cradle_rules.py [--selftest]

``--selftest`` seeds defects (a CC resistor on the wrong pin, the fuse
bridged, the fuse of the wrong rating, the pin row mirrored, D+ and D-
exchanged, a service pin fitted, a consumer pin not fitted, a part on the top
side, a moved screw hole, the receptacle back on the library land pattern, a
pin table that disagrees with the KiCad symbol) and requires each to fail a row.

A row is ``pass``, ``departure`` (the test passes, but the thing is done
differently from the letter of the source; note starts with DEVIATION) or
``FAIL``.  Exit status 0 only if no row FAILs (and every seeded defect is
caught).  Nothing here is a hardware test.
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.normpath(os.path.join(HERE, "..", "tools")), HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import gl1_cradle_design as G                  # noqa: E402
from gleda import geometry                     # noqa: E402
from gleda.model import BOTTOM, TOP            # noqa: E402

#: DESIGN_SPEC E6: "hold about 0.2 A, trip about 0.5 A"
SPEC_HOLD_MA, SPEC_TRIP_MA = 200, 500

KICAD_SYMBOL_DIR = "/usr/share/kicad/symbols"
#: second source for the pin -> pad tables typed into gl1_cradle_design.py:
#: ref -> (library, symbol, {netlist pin(s): symbol pin name})
LIBRARY_SYMBOLS = {
    "U1": ("Power_Protection", "USBLC6-2SC6",
           {"IO1A+IO1B": "I/O1", "IO2A+IO2B": "I/O2", "GND": "GND", "VBUS": "VBUS"}),
    "J1": ("Connector", "USB_C_Receptacle_USB2.0_16P",
           {"GND": "GND", "VBUS": "VBUS", "CC1": "CC1", "CC2": "CC2", "DP": "D+", "DM": "D-",
            "SBU1": "SBU1", "SBU2": "SBU2", "SHIELD": "SHIELD"}),
}


def kicad_symbol(lib, name, _seen=()):
    """{pad number: pin name} of an installed KiCad symbol (following
    ``extends``), or None if the library or the symbol is missing."""
    try:
        with open(os.path.join(KICAD_SYMBOL_DIR, lib + ".kicad_sym"), encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None
    start = text.find('\n  (symbol "%s"' % name)
    if start < 0:
        return None
    end = text.find('\n  (symbol "', start + 10)
    block = text[start:end if end > 0 else len(text)]
    ext = re.search(r'\(extends "([^"]+)"\)', block)
    if ext:
        return None if ext.group(1) in _seen else kicad_symbol(lib, ext.group(1), _seen + (name,))
    return {m.group(2): m.group(1) for m in
            re.finditer(r'\(pin \w+ \w+.*?\(name "([^"]*)".*?\(number "([^"]*)"', block, re.S)}


def pin_table_problems(design):
    P = design.parts_by_ref
    bad = []
    for ref, (lib, sym, names) in sorted(LIBRARY_SYMBOLS.items()):
        part, sym_pins = P.get(ref), kicad_symbol(lib, sym)
        if part is None or sym_pins is None:
            bad.append("%s: %s" % (ref, "not in the netlist" if part is None else "symbol %s:%s not found" % (lib, sym)))
            continue
        covered = set()
        for mine, theirs in names.items():
            pads = set()
            for pin in mine.split("+"):
                pads |= set(part.pins[pin].pads) if pin in part.pins else {"missing pin %s" % pin}
            want = {num for num, nm in sym_pins.items() if nm == theirs}
            covered |= want
            if ref == "J1":
                # the project land pattern has one pad object per wide land (make_usb_footprint.py):
                # contact B12 is on land A1, B9 on A4, B4 on A9, B1 on A12
                import make_usb_footprint as _M
                if any(_M.MERGED_LANDS.get(n, n) not in want for n in want):
                    bad.append("J1.%s: a merged land carries contacts of different symbol pins" % mine)
                want = {_M.MERGED_LANDS.get(n, n) for n in want}
            if pads != want:
                bad.append("%s.%s on pad(s) %s, the symbol %s has %s on %s"
                           % (ref, mine, sorted(pads), sym, theirs, sorted(want)))
        if covered != set(sym_pins):
            bad.append("%s: pins of the symbol not covered: %s" % (ref, sorted(set(sym_pins) - covered)))
    return bad


def row_status(row):
    return row[5] if len(row) > 5 else ("pass" if row[3] else "FAIL")


def rules(design):
    """[(id, what is asked, where it is in the netlist, test passed, note, result)]"""
    P = design.parts_by_ref
    Y = G.Y
    cr = Y["cradle"]
    pin_net = {}
    for net in design.nets.values():
        for node in net.nodes:
            pin_net[node] = net.name
    out = []

    def row(rid, spec, where, ok, note=""):
        status = "FAIL" if not ok else ("departure" if note.startswith("DEVIATION") else "pass")
        out.append((rid, spec, where, bool(ok), note, status))

    def net(node):
        return pin_net.get(tuple(node.split(".", 1)))

    def only(name, *nodes):
        return name in design.nets and sorted("%s.%s" % n for n in design.nets[name].nodes) == sorted(nodes)

    def two(ref, a, b):
        return ref in P and sorted(pin_net.get((ref, p)) or "" for p in ("1", "2")) == sorted((a, b))

    b = geometry.outline_polygon(design.outline).bounds
    row("board", "cradle.pcb: 30.0 x 22.0, thickness 1.6; 2 layers (task)",
        "outline rectangle about the board centre = marker (0, %.1f); layers 2" % G.Y0,
        abs(b[2] - b[0] - cr["pcb"]["dx"]) < 0.02 and abs(b[3] - b[1] - cr["pcb"]["dy"]) < 0.02
        and design.layers == 2 and abs(design.board_thickness - cr["pcb"]["thickness"]) < 1e-9
        and abs(G.Y0 - 0.5 * (cr["pcb"]["y"][0] + cr["pcb"]["y"][1])) < 1e-9)
    holes = sorted((round(h.x, 3), round(h.y + G.Y0, 3)) for h in design.outline.holes)
    row("screws", "four screw holes at cradle.pcb.screws %s" % cr["pcb"]["screws"],
        "NPTH holes MH1-MH4 dia %.1f (diameter PROVISIONAL)" % G.SCREW_HOLE_DIA,
        holes == sorted((float(x), float(y)) for x, y in cr["pcb"]["screws"]))
    pins = [P.get("SP%d" % i) for i in range(1, 8)]
    xs = Y["base_plate"]["pad_holes"]["xs"]
    have = all(p is not None for p in pins)
    pads = [geometry.part_pads(design, p)[0] for p in pins] if have else []
    row("pin row", "seven spring-pin positions on 2.54 mm pitch at pin_row_y %.1f, in the YAML order "
        "(VBUS, D-, D+, GND, SWDIO, SWCLK, NRST from x = -7.62 to +7.62 seen from above)" % cr["pin_row_y"],
        "SP1-SP7 (through hole, top side): pad centres measured at marker x = %s, y = %s"
        % ([round(q.x, 2) for q in pads], sorted({round(q.y + G.Y0, 2) for q in pads})),
        have and all(abs(q.x - x) < 1e-6 and abs(q.y + G.Y0 - cr["pin_row_y"]) < 1e-6
                     for q, x in zip(pads, xs))
        and all(p.side == TOP for p in pins)
        and [q.net for q in pads] == ["VBUS", "USB_DM", "USB_DP", "GND", "SWDIO", "SWCLK", "NRST"]
        and all(abs(xs[i + 1] - xs[i] - 2.54) < 1e-9 for i in range(6)))
    row("fitted", "four spring pins fitted (VBUS, D-, D+, GND) and three service positions (SWDIO, "
        "SWCLK, NRST) for the factory fixture",
        "SP1-SP4 fitted, SP5-SP7 not fitted (same footprint, fitted in the factory fixture)",
        have and [p.dnp for p in pins] == [False] * 4 + [True] * 3 and all(p.in_bom for p in pins)
        and cr["pins"]["populated_consumer"] == ["VBUS", "D-", "D+", "GND"]
        and all(p.mpn == G.MILLMAX_0914["mpn"] for p in pins))
    row("service", "(task) the three service positions taken to a small unpopulated header or test pads",
        "J2: four bare pads on the bottom (GND, SWDIO, SWCLK, NRST)",
        only("SWDIO", "SP5.1", "J2.SWDIO") and only("SWCLK", "SP6.1", "J2.SWCLK")
        and only("NRST", "SP7.1", "J2.NRST") and net("J2.GND") == "GND" and "J2" in P
        and not P["J2"].in_bom and P["J2"].side == BOTTOM)
    j1 = P["J1"]
    front = geometry.part_body_polygon(j1).bounds[1]
    row("USB-C", "USB-C receptacle (USB 2.0; YAML: GCT USB4105, rear exit), the USB mouth at the YAML "
        "edge (usb_mouth_y %.1f)" % cr["pcb"]["usb_mouth_y"],
        "J1 USB4105-GF-A, top side, body front at marker y %.2f (%.1f mm beyond the board edge); "
        "SBU1 / SBU2 not connected" % (front + G.Y0, cr["pcb"]["y"][0] - cr["pcb"]["usb_mouth_y"]),
        j1.mpn == "USB4105-GF-A" and abs(front + G.Y0 - cr["pcb"]["usb_mouth_y"]) < 0.01
        and j1.side == TOP and net("J1.GND") == "GND" and net("J1.SHIELD") == "GND"
        and j1.pins["SBU1"].etype == "nc" and j1.pins["SBU2"].etype == "nc" and abs(j1.x) < 1e-9)
    import make_usb_footprint as M
    holes_j1 = [q for q in geometry.part_pads(design, j1) if q.kind == "npth"]
    copper_j1 = [q for q in geometry.part_pads(design, j1) if q.kind != "npth" and q.polygon is not None]
    from shapely.geometry import Point
    gap = min(q.polygon.distance(Point(h.x, h.y)) - h.drill / 2.0 for h in holes_j1 for q in copper_j1) \
        if holes_j1 and copper_j1 else -1.0
    try:
        with open(M.LOCAL_PATH, encoding="utf-8") as fh:
            same = fh.read() == M.local_text()
    except OSError:
        same = False
    row("USB-C land", "(KiCad DRC, rule set) 0.20 mm between a hole wall and foreign copper",
        "J1 uses the project copy of KiCad's USB4105 land pattern: the four outer ground pads are 0.04 mm "
        "shorter; smallest distance from a locating-peg hole to a pad of J1 %.3f mm (library footprint: "
        "0.194); one pad object per wide land instead of two coincident ones (%s); the stored file equals "
        "the library file with exactly these changes" % (gap, ", ".join(
            "%s on %s" % kv for kv in sorted(M.MERGED_LANDS.items()))),
        gap >= design.rules.hole_clearance + 0.01 and same and j1.footprint_name.endswith("_GL1")
        and not any(q.number in M.MERGED_LANDS for q in copper_j1),
        "DEVIATION from the maker's land pattern, PROVISIONAL; no design rule is relaxed. The merged pad "
        "objects are a workaround for the toolchain's router, which cannot join coincident pads; the copper "
        "is unchanged")
    row("CC", "5.1 kohm from CC1 and from CC2 to ground",
        "R1: CC1 (A5) - GND, R2: CC2 (B5) - GND, one resistor each",
        two("R1", "CC1", "GND") and two("R2", "CC2", "GND") and P["R1"].value == P["R2"].value == "5k1"
        and only("CC1", "J1.CC1", "R1.1") and only("CC2", "J1.CC2", "R2.1")
        and tuple(j1.pins["CC1"].pads) == ("A5",) and tuple(j1.pins["CC2"].pads) == ("B5",))
    row("fuse", "a resettable fuse in VBUS (hold about 0.2 A, trip about 0.5 A, PROPOSED)",
        "F1 between VBUS_IN (J1 lands A4 / B9 and A9 / B4) and VBUS (SP1): hold %d mA, trip %d mA (PROVISIONAL part %s)"
        % (G.PTC["hold_mA"], G.PTC["trip_mA"], G.PTC["mpn"]),
        two("F1", "VBUS_IN", "VBUS") and only("VBUS", "F1.2", "SP1.1") and net("J1.VBUS") == "VBUS_IN"
        and tuple(j1.pins["VBUS"].pads) == ("A4", "A9")
        and G.PTC["hold_mA"] == SPEC_HOLD_MA and G.PTC["trip_mA"] == SPEC_TRIP_MA
        and "F1" in P and P["F1"].mpn == G.PTC["mpn"])
    row("ESD", "USBLC6-2SC6 on VBUS / D+ / D-",
        "U1: D- through pins 1 + 6, D+ through pins 3 + 4, pin 5 on VBUS_IN (C1 100n), pin 2 GND",
        P["U1"].mpn == "USBLC6-2SC6" and only("USB_DM", "J1.DM", "U1.IO1A", "U1.IO1B", "SP2.1")
        and only("USB_DP", "J1.DP", "U1.IO2A", "U1.IO2B", "SP3.1") and net("U1.VBUS") == "VBUS_IN"
        and net("U1.GND") == "GND" and two("C1", "VBUS_IN", "GND")
        and tuple(j1.pins["DP"].pads) == ("A6", "B6") and tuple(j1.pins["DM"].pads) == ("A7", "B7"),
        "ADDED: C1 100 nF at the VBUS pin of U1; the clamp sits on the connector side of the fuse")
    top = sorted(p.ref for p in design.parts if p.side == TOP and (p.height_mm or 0) > 0)
    hl = [h for h in design.height_limits if h.name == "pocket_ceiling"]
    row("top side", "nothing on the top side may reach the pocket ceiling (YAML note)",
        "height limit 0.0 mm on the whole top side, J1 and SP1-SP7 exempt; every other part is on the bottom",
        top == sorted(["J1"] + ["SP%d" % i for i in range(1, 8)]) and len(hl) == 1
        and hl[0].max_height == 0.0)
    pin_bad = pin_table_problems(design)
    row("pin tables", "(task) the pin -> pad table of every library-backed part agrees with a second source",
        "U1 against the installed KiCad symbol USBLC6-2SC6, J1 against USB_C_Receptacle_USB2.0_16P (pad "
        "numbers and pin names): %s" % ("; ".join(pin_bad) if pin_bad else "all agree"),
        not pin_bad, "the spring pins and the fuse have one or two interchangeable pads")
    n_top = sum(1 for p in design.parts if "fiducial" in p.footprint_name.lower() and p.side == TOP)
    n_bot = sum(1 for p in design.parts if "fiducial" in p.footprint_name.lower() and p.side == BOTTOM)
    row("fiducials", "(task) at least three global fiducials per side", "FID1-FID3 top, FID4-FID6 bottom",
        n_top >= 3 and n_bot >= 3)
    status = {p.ref: p.fields.get("Status") for p in design.parts if p.in_bom}
    row("status", "(task) every BOM part carries an evidence status",
        "Part.fields['Status'] is RESEARCH or PROVISIONAL on all %d BOM parts" % len(status),
        all(v in ("RESEARCH", "PROVISIONAL") for v in status.values()))
    return out


# ---------------------------------------------------------------------------
# self-test
# ---------------------------------------------------------------------------
def _move(design, node, new_net):
    key = tuple(node.split(".", 1))
    for n in design.nets.values():
        if key in n.nodes:
            n.nodes.remove(key)
    design.net(new_net, node)


def _swap_nets(design, node_a, node_b):
    a, b = tuple(node_a.split(".", 1)), tuple(node_b.split(".", 1))
    na = next(n for n in design.nets.values() if a in n.nodes)
    nb = next(n for n in design.nets.values() if b in n.nodes)
    na.nodes[na.nodes.index(a)] = b
    nb.nodes[nb.nodes.index(b)] = a


def _mirror_pins(design):
    xs = [design.part("SP%d" % i).x for i in range(1, 8)]
    for i in range(1, 8):
        p = design.part("SP%d" % i)
        p.place(xs[7 - i], p.y, 0.0)


def _move_hole(design):
    import dataclasses
    h = design.outline.holes[0]
    design.outline.holes[0] = dataclasses.replace(h, x=h.x + 0.5)


def _fuse_rating(design):
    G.PTC["hold_mA"], G.PTC["trip_mA"] = 100, 300


SEEDED = [
    ("R2 on CC1 as well (CC2 left open)", lambda d: _move(d, "R2.1", "CC1"), "CC"),
    ("fuse bridged: SP1 on VBUS_IN", lambda d: _move(d, "SP1.1", "VBUS_IN"), "fuse"),
    ("fuse rated 0.1 A / 0.3 A", _fuse_rating, "fuse"),
    ("pin row mirrored (VBUS at +7.62)", _mirror_pins, "pin row"),
    ("D+ and D- exchanged at the pins", lambda d: _swap_nets(d, "SP2.1", "SP3.1"), "pin row"),
    ("service pin SP6 fitted", lambda d: setattr(d.part("SP6"), "dnp", False), "fitted"),
    ("consumer pin SP4 (GND) not fitted", lambda d: setattr(d.part("SP4"), "dnp", True), "fitted"),
    ("C1 placed on the top side", lambda d: d.part("C1").place(1.1, 0.6, 0.0, side=TOP), "top side"),
    ("screw hole MH1 moved 0.5 mm", _move_hole, "screws"),
    ("ESD array clamps the wrong pair (IO2 on D-)", lambda d: _swap_nets(d, "U1.IO1A", "U1.IO2A"), "ESD"),
    ("SWDIO and SWCLK exchanged at the service pads", lambda d: _swap_nets(d, "J2.SWDIO", "J2.SWCLK"), "service"),
    ("CC2 on pad A8 (SBU1) in the pin table of J1",
     lambda d: d.part("J1").pins.update(CC2=d.part("J1").pins["CC2"].__class__("CC2", ("A8",), "passive"),
                                        SBU1=d.part("J1").pins["SBU1"].__class__("SBU1", ("B5",), "nc")),
     "pin tables"),
    ("ESD array drawn with pads 2 and 5 exchanged (GND / VBUS)",
     lambda d: d.part("U1").pins.update(GND=d.part("U1").pins["GND"].__class__("GND", ("5",), "power_in"),
                                        VBUS=d.part("U1").pins["VBUS"].__class__("VBUS", ("2",), "power_in")),
     "pin tables"),
    ("J1 back on the unchanged library land pattern",
     lambda d: setattr(d.part("J1"), "footprint",
                       "Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal"), "USB-C land"),
]


def selftest():
    lines, missed = [], 0
    saved = dict(G.PTC)
    for what, mutate, expect in SEEDED:
        design = G.gl1_cradle_design()
        try:
            mutate(design)
            bad = [r[0] for r in rules(design) if not r[3]]
        except Exception as exc:
            bad = ["EXCEPTION %s: %s" % (type(exc).__name__, exc)]
        finally:
            G.PTC.clear()
            G.PTC.update(saved)
        hit = [b for b in bad if b.startswith(expect) or b.startswith("EXCEPTION")]
        lines.append("  %s  %s -> %s" % ("caught" if hit else "MISSED", what, ", ".join(bad) or "no row failed"))
        missed += 0 if hit else 1
    return lines, missed


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true", help="seed defects and require each to fail a row")
    args = ap.parse_args(argv)
    rows = rules(G.gl1_cradle_design())
    bad = [r for r in rows if row_status(r) == "FAIL"]
    dep = [r[0] for r in rows if row_status(r) == "departure"]
    for r in rows:
        print("%-10s %-10s %s" % (row_status(r), r[0], r[2]))
        if r[4]:
            print("           %-10s note: %s" % ("", r[4]))
    print("\ncradle rules: %d rows: %d as specified, %d departure(s) (%s), %d failed"
          % (len(rows), len(rows) - len(bad) - len(dep), len(dep), ", ".join(dep) or "none", len(bad)))
    missed = 0
    if args.selftest:
        lines, missed = selftest()
        print("\nSELF-TEST: %d seeded defects, %d caught, %d missed" % (len(SEEDED), len(SEEDED) - missed, missed))
        print("\n".join(lines))
    return 1 if (bad or missed) else 0


if __name__ == "__main__":
    sys.exit(main())
