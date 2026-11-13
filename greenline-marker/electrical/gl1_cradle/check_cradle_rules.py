#!/usr/bin/python3
"""The cradle block of design/master_params.yaml and the cradle task, row by
row, against the netlist of ``gl1_cradle_design.py``.

    /usr/bin/python3 -B electrical/gl1_cradle/check_cradle_rules.py

Exit status 0 only if every row passes.  Nothing here is a hardware test.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.normpath(os.path.join(HERE, "..", "tools")), HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import gl1_cradle_design as G                  # noqa: E402
from gleda import geometry                     # noqa: E402
from gleda.model import BOTTOM, TOP            # noqa: E402


def rules(design):
    """[(id, what is asked, where it is in the netlist, passed, note)]"""
    P = design.parts_by_ref
    Y = G.Y
    cr = Y["cradle"]
    pin_net = {}
    for net in design.nets.values():
        for node in net.nodes:
            pin_net[node] = net.name
    out = []

    def row(rid, spec, where, ok, note=""):
        out.append((rid, spec, where, bool(ok), note))

    def net(node):
        return pin_net.get(tuple(node.split(".", 1)))

    def only(name, *nodes):
        return sorted("%s.%s" % n for n in design.nets[name].nodes) == sorted(nodes)

    def two(ref, a, b):
        return sorted(pin_net.get((ref, p)) for p in ("1", "2")) == sorted((a, b))

    b = geometry.outline_polygon(design.outline).bounds
    row("board", "cradle.pcb: 30.0 x 22.0, thickness 1.6; 2 layers (task)",
        "outline rectangle about the board centre = marker (0, %.1f); layers 2" % G.Y0,
        abs(b[2] - b[0] - cr["pcb"]["dx"]) < 0.02 and abs(b[3] - b[1] - cr["pcb"]["dy"]) < 0.02
        and design.layers == 2 and abs(design.board_thickness - cr["pcb"]["thickness"]) < 1e-9)
    holes = sorted((round(h.x, 3), round(h.y + G.Y0, 3)) for h in design.outline.holes)
    row("screws", "four screw holes at cradle.pcb.screws %s" % cr["pcb"]["screws"],
        "NPTH holes MH1-MH4 dia %.1f (diameter PROVISIONAL)" % G.SCREW_HOLE_DIA,
        holes == sorted((float(x), float(y)) for x, y in cr["pcb"]["screws"]))
    pins = [P["SP%d" % i] for i in range(1, 8)]
    xs = Y["base_plate"]["pad_holes"]["xs"]
    row("pin row", "seven spring-pin positions on 2.54 mm pitch at pin_row_y %.1f, in the YAML order"
        % cr["pin_row_y"],
        "SP1-SP7 (through hole, top side) at marker x = %s" % xs,
        all(abs(p.x - x) < 1e-6 and abs(p.y + G.Y0 - cr["pin_row_y"]) < 1e-6 and p.side == TOP
            for p, x in zip(pins, xs))
        and [net("SP%d.1" % i) for i in range(1, 8)]
        == ["VBUS", "USB_DM", "USB_DP", "GND", "SWDIO", "SWCLK", "NRST"])
    row("fitted", "the four consumer pins populated (VBUS, D-, D+, GND); three service positions "
        "for the factory fixture",
        "SP1-SP4 fitted, SP5-SP7 DNP (same footprint, fitted in the factory fixture)",
        [p.dnp for p in pins] == [False] * 4 + [True] * 3 and all(p.in_bom for p in pins)
        and cr["pins"]["populated_consumer"] == ["VBUS", "D-", "D+", "GND"])
    row("service", "the three service positions taken to a small unpopulated header or test pads",
        "J2: four bare pads on the bottom (GND, SWDIO, SWCLK, NRST)",
        only("SWDIO", "SP5.1", "J2.SWDIO") and only("SWCLK", "SP6.1", "J2.SWCLK")
        and only("NRST", "SP7.1", "J2.NRST") and net("J2.GND") == "GND" and not P["J2"].in_bom
        and P["J2"].side == BOTTOM)
    j1 = P["J1"]
    front = geometry.part_body_polygon(j1).bounds[1]
    row("USB-C", "USB-C receptacle (GCT USB4105 class, USB 2.0), the USB mouth at the YAML edge "
        "(usb_mouth_y %.1f)" % cr["pcb"]["usb_mouth_y"],
        "J1 USB4105-GF-A, top side, body front at marker y %.2f (%.1f mm beyond the board edge)"
        % (front + G.Y0, cr["pcb"]["y"][0] - cr["pcb"]["usb_mouth_y"]),
        j1.mpn == "USB4105-GF-A" and abs(front + G.Y0 - cr["pcb"]["usb_mouth_y"]) < 0.01
        and j1.side == TOP and net("J1.GND") == "GND" and net("J1.SHIELD") == "GND")
    row("CC", "5.1 kohm on CC1 and CC2",
        "R1: CC1 (A5) - GND, R2: CC2 (B5) - GND",
        two("R1", "CC1", "GND") and two("R2", "CC2", "GND") and P["R1"].value == P["R2"].value == "5k1"
        and only("CC1", "J1.CC1", "R1.1") and only("CC2", "J1.CC2", "R2.1"))
    row("fuse", "a resettable fuse in VBUS sized for the marker",
        "F1 between VBUS_IN (J1 A4, A9, B4, B9) and VBUS (SP1): hold %d mA, trip %d mA (PROVISIONAL part)"
        % (G.PTC["hold_mA"], G.PTC["trip_mA"]),
        two("F1", "VBUS_IN", "VBUS") and only("VBUS", "F1.2", "SP1.1") and net("J1.VBUS") == "VBUS_IN"
        and tuple(P["J1"].pins["VBUS"].pads) == ("A4", "A9", "B4", "B9"))
    row("ESD", "USBLC6-2SC6",
        "U1: D- through pins 1 + 6, D+ through pins 3 + 4, pin 5 on VBUS_IN (C1 100n), pin 2 GND",
        P["U1"].mpn == "USBLC6-2SC6" and only("USB_DM", "J1.DM", "U1.IO1A", "U1.IO1B", "SP2.1")
        and only("USB_DP", "J1.DP", "U1.IO2A", "U1.IO2B", "SP3.1") and net("U1.VBUS") == "VBUS_IN"
        and net("U1.GND") == "GND" and two("C1", "VBUS_IN", "GND")
        and tuple(P["J1"].pins["DP"].pads) == ("A6", "B6") and tuple(P["J1"].pins["DM"].pads) == ("A7", "B7"))
    top = sorted(p.ref for p in design.parts if p.side == TOP and (p.height_mm or 0) > 0)
    hl = [h for h in design.height_limits if h.name == "pocket_ceiling"]
    row("top side", "nothing on the top side may reach the pocket ceiling (YAML note)",
        "height limit 0.0 mm on the whole top side, J1 and SP1-SP7 exempt; every other part is on the bottom",
        top == sorted(["J1"] + ["SP%d" % i for i in range(1, 8)]) and len(hl) == 1
        and hl[0].max_height == 0.0)
    n_top = sum(1 for p in design.parts if "fiducial" in p.footprint_name.lower() and p.side == TOP)
    n_bot = sum(1 for p in design.parts if "fiducial" in p.footprint_name.lower() and p.side == BOTTOM)
    row("fiducials", "(task) at least three global fiducials per side", "FID1-FID3 top, FID4-FID6 bottom",
        n_top >= 3 and n_bot >= 3)
    return out


def main():
    rows = rules(G.gl1_cradle_design())
    bad = [r for r in rows if not r[3]]
    for rid, spec, where, ok, note in rows:
        print("%-5s %-10s %s" % ("ok" if ok else "FAIL", rid, where))
    print("\ncradle rules: %d rows, %d passed, %d failed" % (len(rows), len(rows) - len(bad), len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
