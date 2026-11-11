#!/usr/bin/python3
"""Quick start: the smallest complete design, taken through the whole flow.

    cd electrical/tools
    /usr/bin/python3 demo/quickstart_board.py /some/empty/dir     # about 10 s

A 24 mm D-shaped 4-layer board with one 16-ball 0.5 mm-pitch BGA, its
decoupling capacitor, a pull-up and a row of bare contact pads on the bottom.
It shows everything a real design needs, in the order one writes it: outline
and locating features, rules and net classes, parts with pin maps, nets,
planes, a fine area, a via keep-out, fiducials - and then checks, board,
router, KiCad DRC, outputs and the schematic round trip.  Exit code 0 only if
all of it passed.  ``tests/test_demo.py`` runs this file, so the README text
that quotes it stays true.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gleda.model import (Design, Outline, PathShape, RoundedPolygon, Part, two_pin,  # noqa: E402
                         n_pin, US_4L_FINE, BOTTOM)
from gleda import footprints as F                                                    # noqa: E402
from gleda import checks, board, router, drc, outputs, schematic                    # noqa: E402


def quickstart_design(name="quickstart"):
    # ---- 1. outline (mm, origin = board centre, +y up) and rules ------------
    outline = Outline(PathShape.d_shape(12.0, 9.0))            # circle r = 12, flat at y = +9
    outline.add_hole(-8.0, 0.0, 1.15, name="H1")               # NPTH locating hole
    outline.add_npth_slot(8.0, 0.0, width=1.15, length=1.65)   # NPTH locating slot

    d = Design(name, outline, layers=4, rules=US_4L_FINE, board_thickness=0.8,
               title="gleda quick start", revision="A")

    # ---- 2. net classes: Default 0.15/0.127 and Power 0.30/0.127 exist -------
    d.add_netclass("Fine", track_width=0.09, clearance=0.09)   # BGA escape only
    d.via_tenting = "bottom"                                   # vias open on top
    d.via_protection = "plugged from the bottom side (IPC-4761 type III-a)"
    d.fab_notes.append("The bottom side is a wetted surface: no open via holes there.")

    # ---- 3. parts ------------------------------------------------------------
    # 4 x 4 balls, A1 top left.  One 0.09 mm track fits between two 0.23 mm
    # balls and nothing wider does, so the four INNER balls (B2, B3, C2, C3)
    # must be on nets of the fine class; supplies sit on the outer ring.
    bga16 = F.bga("Demo_BGA16", 4, 4, pitch=0.5, pad_d=0.23, body=(2.4, 2.4), height=1.0,
                  pad_clearance=0.09, courtyard_margin=0.2)
    d.add(Part("U1", "Sensor", bga16,
               pins={"VDD": (("A1", "A4"), "power_in"),        # two balls, one pin
                     "GND": (("D1", "D4"), "power_in"),
                     "D0": ("B2", "bidir"), "D1": ("B3", "bidir"),
                     "D2": ("C2", "bidir"), "D3": ("C3", "bidir"),
                     "SCL": ("A2", "input"), "SDA": ("A3", "bidir"),
                     "INT": ("B1", "output"), "EN": ("B4", "input"),
                     "NC1": ("C1", "nc"), "NC2": ("C4", "nc"),
                     "NC3": ("D2", "nc"), "NC4": ("D3", "nc")},
               mpn="DEMO-BGA16", manufacturer="Demo", distributor="Digi-Key",
               distributor_pn="000-DEMO-ND", unit_price=2.5,
               x=0.0, y=3.0, rotation=0, side="top", height_mm=1.0, group="sensor"))
    d.add(Part("C1", "100n", "Capacitor_SMD:C_0402_1005Metric", pins=two_pin(),
               mpn="CL05B104KO5NNNC", manufacturer="Samsung", distributor="Digi-Key",
               distributor_pn="1276-1001-1-ND", unit_price=0.01,
               x=3.2, y=3.0, rotation=90, height_mm=0.55, group="sensor"))
    d.add(Part("R1", "10k", "Resistor_SMD:R_0402_1005Metric", pins=two_pin(),
               mpn="RC0402FR-0710KL", manufacturer="Yageo", distributor="Digi-Key",
               distributor_pn="311-10.0KLRCT-ND", unit_price=0.01,
               x=-3.2, y=3.0, rotation=90, height_mm=0.4, group="sensor"))
    d.add(Part("J1", "Contacts", F.pad_row("ContactRow10", 10, 1.6, 1.2), pins=n_pin(10),
               x=0.0, y=-7.0, side=BOTTOM, in_bom=False, height_mm=0.0, group="service"))

    # ---- 4. nets: every pin on a net, typed "nc", or in d.no_connect(...) -----
    d.net("GND", "U1.GND", "C1.2", "J1.1", netclass="Power")
    d.net("VDD", "U1.VDD", "C1.1", "R1.1", "J1.2", netclass="Power", power_flag=True)
    for i in range(4):                                         # the inner balls
        d.net("D%d" % i, "U1.D%d" % i, "J1.%d" % (3 + i), netclass="Fine")
    d.net("SCL", "U1.SCL", "J1.7")
    d.net("SDA", "U1.SDA", "J1.8")
    d.net("INT", "U1.INT", "R1.2", "J1.9")
    d.net("EN", "U1.EN", "J1.10")

    # ---- 5. planes, fine area, keep-outs, fiducials -------------------------
    d.add_plane("GND", "In1.Cu")                               # solid plane
    d.add_plane("VDD", "In2.Cu", routable=True)                # plane + third routing layer
    d.add_fine_area("U1", margin=5.0)                          # "Fine" is fine only around U1
    d.add_keepout(RoundedPolygon.rect(0.0, -3.0, 6.0, 2.0), layers=("B.Cu",),
                  name="wet_window", tracks=False, vias=True, copper=False)   # no via holes here
    for x, y in ((-9.5, 4.0), (9.5, 2.0), (0.0, -10.5)):       # three per assembled side,
        d.add_fiducial(x, y)                                   # far apart, not symmetric
    for x, y in ((-9.5, -4.0), (9.0, -4.5), (-4.0, 7.5)):
        d.add_fiducial(x, y, side=BOTTOM)
    return d


def build(design, out, say=print):
    """checks -> board -> route -> KiCad DRC -> outputs -> schematic round trip.
    Returns 0 if everything passed, 1 otherwise (and says what did not)."""
    os.makedirs(out, exist_ok=True)
    report = checks.run_checks(design)
    say(report.text())
    if not report.ok:
        return 1
    files = board.build_board(design, out)
    result = router.route(design, router.RouterOptions(time_limit=600))
    say(result.summary())
    for u in result.unrouted:                                  # never hidden
        say("OPEN %s: %s  [%s]" % (u.net, u.pieces, u.reason))
    for line in result.warnings:                               # detours, many vias
        say("LOOK AT " + line)
    if not result.complete:
        return 1
    board.apply_routing(files.pcb, result.tracks, result.vias, via_tenting=design.via_tenting)
    res = drc.run_drc(files.pcb, json_path=os.path.join(out, "drc.json"))
    say("KiCad DRC: %d error(s), %d unconnected, %d warning(s)"
        % (res.error_count, res.unconnected_count, res.warning_count))
    try:
        drc.assert_clean(res)                                  # KiCad is the judge
    except drc.DrcError as exc:
        say(str(exc))
        return 1
    package = outputs.generate_outputs(design, files.pcb, out, drc_result=res, vias=result.vias)
    say("outputs: %d files, %d problem(s) against the model"
        % (len(package.files), len(package.problems)))
    for problem in package.problems:
        say("  " + problem)
    sch = schematic.generate_schematic(design, out)
    schematic.export_pdf(sch.root, os.path.join(out, "schematic.pdf"))
    trip = schematic.round_trip(design, sch.root)
    say(trip.summary())
    return 0 if (package.ok and trip.ok) else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: quickstart_board.py OUTPUT_DIRECTORY")
    sys.exit(build(quickstart_design(), sys.argv[1]))
