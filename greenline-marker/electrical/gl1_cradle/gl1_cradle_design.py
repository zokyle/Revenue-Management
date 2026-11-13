#!/usr/bin/python3
"""GreenLine GL-1 charging / data cradle board - netlist and layout as code (gleda 0.4.0).

STAGE: LAYOUT.  Nothing has been built.  ``build_gl1_cradle.py`` routes this
board with the toolchain's router and takes it through KiCad's DRC and the
output stage; ``build_netlist.py`` is the earlier stage without copper.  The
mechanical interfaces (outline, four screw holes, the seven spring-pin
positions, the USB-C mouth) come from the ``cradle`` block of
``design/master_params.yaml``, read at import time.

What the board is (DESIGN_SPEC section 4, "Cradle board (E6)"): a USB-C
receptacle (USB 2.0 only), 5.1 kohm from CC1 and from CC2 to ground so that a
USB-C source turns VBUS on, a resettable fuse in VBUS (hold 0.2 A, trip
0.5 A), a USBLC6-2SC6 on VBUS / D+ / D-, and seven spring-pin positions that
meet the seven pads under the marker:

    pin 1 VBUS, 2 D-, 3 D+, 4 GND        fitted in the consumer cradle
    pin 5 SWDIO, 6 SWCLK, 7 NRST         fitted in the factory fixture only (not fitted here);
                                         taken to four bare pads (GND, SWDIO, SWCLK, NRST)

Frames.  Board frame (this file, the toolchain): origin at the board centre,
+x right, +y up seen from the TOP of the board.  Marker frame (the YAML):
board x = marker x, board y = marker y - Y0 with Y0 = centre of cradle.pcb.y.
Pin 1 (VBUS) is at marker x = -7.62, under pad 1 of the marker's row.
The top face of the board lies against the ceiling of its pocket in the
printed cradle (mechanical/README: "screw the PCB against the pocket ceiling");
only the receptacle (in its own pocket) and the spring pins (through the slot
in the nest floor) stand on the top side.  Every other part is on the BOTTOM.

PROVISIONAL items, each in one table: ``MILLMAX_0914`` (pin dimensions),
``PTC`` (the fuse), ``SCREW_HOLE_DIA`` / ``SCREW_HEAD_DIA``; and the project copy
of the receptacle's land pattern (``make_usb_footprint.py``).  The sizing of the
fuse and every other value is in ``CRADLE_NOTES.md``.

    /usr/bin/python3 -B electrical/gl1_cradle/gl1_cradle_design.py     # prints the checks
"""
import os
import sys
from dataclasses import replace

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.normpath(os.path.join(HERE, "..", "tools"))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import yaml                                                              # noqa: E402

from gleda.model import (Design, Outline, RoundedPolygon, Circle, Part, two_pin,   # noqa: E402
                         US_4L_STD, BOTTOM, TOP)
from gleda import footprints as F                                        # noqa: E402

YAML_PATH = os.path.normpath(os.path.join(HERE, "..", "..", "design", "master_params.yaml"))
with open(YAML_PATH, encoding="utf-8") as _fh:
    Y = yaml.safe_load(_fh)

DESIGN_NAME = "gl1_cradle"
CR = Y["cradle"]
CPCB = CR["pcb"]
X0 = 0.5 * (CPCB["x"][0] + CPCB["x"][1])             # 0.0
Y0 = 0.5 * (CPCB["y"][0] + CPCB["y"][1])             # -23.2: board centre in the marker frame
BOARD_DX, BOARD_DY = CPCB["dx"], CPCB["dy"]          # 30 x 22
BOARD_THICKNESS = CPCB["thickness"]                  # 1.6
PIN_XS = [x - X0 for x in Y["base_plate"]["pad_holes"]["xs"]]     # seven positions, 2.54 mm pitch
PIN_Y = CR["pin_row_y"] - Y0                         # 6.2
SCREWS = [(x - X0, y - Y0) for x, y in CPCB["screws"]]
USB_MOUTH_Y = CPCB["usb_mouth_y"] - Y0               # -12.3: 1.3 mm beyond the board edge (-11.0)
#: the YAML's pad order, -x to +x (DESIGN_SPEC: "VBUS, D-, D+, GND, SWDIO, SWCLK, NRST, in that
#: order from x = -7.62 to +7.62 mm seen from above")
PIN_NAMES = ("VBUS", "DM", "DP", "GND", "SWDIO", "SWCLK", "NRST")
CONSUMER_PINS = tuple(CR["pins"]["populated_consumer"])            # VBUS, D-, D+, GND

#: PROVISIONAL - Mill-Max 0914 long-stroke spring pin.  Series, stroke and
#: working height: docs/research/bom-verification-opto.md ("confirmed" from a
#: distributor series page).  Tail, barrel and plunger diameters are NOT
#: confirmed there; they are the numbers mechanical/cad/params.py assumes
#: ("PROVISIONAL until the drawing is read").  Hole = tail + 0.14, as the
#: mechanical model drills it.  Correct the pin here, in one place.
MILLMAX_0914 = {
    "mpn": "0914-0-15-20-77-14-11-0",
    "tail_dia": 0.76, "hole_dia": 0.90, "pad_dia": 1.60, "barrel_dia": 1.83,
    "height_above_board": 6.96,                      # maximum working height (free plunger tip)
    "working_height": CR["pins"]["working_height"],   # 5.82 with the marker on its feet
}

#: PROVISIONAL part - resettable fuse in VBUS.  Ratings: DESIGN_SPEC E6 ("hold
#: about 0.2 A, trip about 0.5 A, PROPOSED").  CRADLE_NOTES.md has the sizing:
#: the marker draws about 30 mA at most (19.8 mA charge + charger supply +
#: VDDUSB regulator + divider), so 0.2 A leaves a factor of four at 60 C;
#: 0.5 A is what every USB 2.0 port must be able to deliver, so a hard short
#: across the pins trips on the weakest standard source.  The order code and
#: its resistance are from memory; any 0603 PTC with these ratings fits.
#: The resistance matters: at 30 mA it costs 0.06 V (2 ohm, the typical value
#: ASSUMED here) to 0.15 V (5 ohm), and with the marker's series Schottky the
#: charger's input is then below the 4.45 V the research records as its minimum
#: at the low end of a USB source (gl1_main NETLIST_NOTES 4.1; SUPPLY_CHAIN in
#: gl1_main_design.py uses the same two numbers).  Choose the lowest guaranteed
#: resistance on offer.
PTC = {"mpn": "MF-FSMF020X-2", "manufacturer": "Bourns", "hold_mA": 200, "trip_mA": 500,
       "v_max": 9, "r_typ_ohm": 2.0, "r_max_ohm": 5.0, "footprint": "Fuse:Fuse_0603_1608Metric",
       "height": 0.85}

#: PROVISIONAL - clearance hole for an M2 thread-forming screw; the YAML gives
#: the four positions only, 2.2 mm is what mechanical/cad/parts.py drills.
SCREW_HOLE_DIA = 2.2
SCREW_HEAD_DIA = 4.0                                 # PROVISIONAL: pan head of an M2 screw

#: Project copy of KiCad's GCT USB4105 land pattern (gl1_cradle_fp.pretty, made by
#: make_usb_footprint.py): the four outer ground pads are 0.04 mm shorter, because the library
#: footprint has only 0.194 mm between its own locating-peg holes and those pads and KiCad's DRC
#: asks for 0.20 mm (hole wall to foreign copper).  No rule is relaxed.  PROVISIONAL.
#: LAYOUT: the copy also has ONE pad object per wide land (the library has two coincident ones:
#: A1 / B12, A4 / B9, A9 / B4, A12 / B1), because the toolchain's router cannot join coincident
#: pads; the copper is the same.
F.add_library_dir(HERE)
USBC = "gl1_cradle_fp:USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal_GL1"
R0402 = "Resistor_SMD:R_0402_1005Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
SOT236 = "Package_TO_SOT_SMD:SOT-23-6"
BY_MPN = "any authorised distributor (order by MPN)"
PROV, RES = "PROVISIONAL", "RESEARCH"

#: body of the KiCad USB4105 footprint reaches 3.675 mm in front of its anchor
USB_BODY_FRONT = 3.675

#: LAYOUT: placement of the free parts (bottom side).  ref -> (x, y, rotation)
PLACEMENT = {
    "F1": (-8.0, -1.6, 0.0), "C1": (1.1, 0.6, 0.0), "U1": (-2.0, 0.6, 0.0),
    "R1": (-3.4, -2.8, 0.0), "R2": (3.4, -2.8, 0.0), "J2": (7.0, 2.6, 0.0),
}
#: three per side, not in line, clear of the silkscreen legend round the pin row
FIDUCIALS_TOP = [(-11.0, 1.5), (11.5, -2.0), (12.5, 4.6)]
FIDUCIALS_BOTTOM = [(-11.5, 4.0), (12.0, -3.5), (-12.5, -4.5)]

#: LAYOUT: options of the toolchain's router for this board (defaults)
ROUTER_OPTIONS = {}

#: The pin order as it is printed on the silkscreen.
#:
#: MIRROR CHECK.  The YAML lists the marker's seven pads seen from ABOVE in the
#: marker frame: VBUS at x = -7.62 ... NRST at x = +7.62.  This board is drawn
#: in the same frame, also seen from above (board x = marker x, see "Frames"),
#: and its spring pins stand on the TOP side and press upward on the marker's
#: underside.  A pin at board x therefore meets the pad at marker x: no mirror.
#: SP1 at x = -7.62 is VBUS (check_cradle_rules.py, row "pin row", measures the
#: pad centres).  A mirror would only appear in a view from BELOW (the bottom
#: silkscreen is such a view: its text is mirrored by KiCad so that it reads
#: correctly from below, and each label still sits at its pin).
SILK_PIN_LABELS = ("VBUS", "D-", "D+", "GND", "SWDIO", "SWCLK", "NRST")


def silk_legend():
    """[(text, x, y, {options})] for gl1_main/silk_text.add_silk_text: the
    pin number and name under every spring pin on the top side, the name
    above every pin and beside every service pad on the bottom side, and the
    board name on both sides.  Design mm, seen from the top."""
    items = []
    for i, (name, x) in enumerate(zip(SILK_PIN_LABELS, PIN_XS), start=1):
        # top: reads upward and ends 1.25 mm below the pin axis (the pad is dia 1.6)
        items.append(("%d %s" % (i, name), round(x, 3), round(PIN_Y - 1.25, 3),
                      {"rotation": 90.0, "side": "top", "height": 0.8, "justify": "right"}))
        # bottom: starts 1.25 mm above the pin axis (mirrored text: KiCad's "right" is the
        # end nearer the pin here; build_gl1_cradle.py's review pictures show the result)
        items.append((name, round(x, 3), round(PIN_Y + 1.25, 3),
                      {"rotation": 90.0, "side": "bottom", "height": 0.7, "justify": "right"}))
    jx, jy = PLACEMENT["J2"][:2]
    for k, name in enumerate(("GND", "SWDIO", "SWCLK", "NRST")):
        items.append((name, round(jx + (k - 1.5) * 2.54, 3), round(jy - 1.15, 3),
                      {"rotation": 90.0, "side": "bottom", "height": 0.7, "justify": "left"}))
    items.append(("GL-1 CRADLE %s" % Y["rev"], 0.0, -2.6, {"side": "top", "height": 0.8}))
    items.append(("GL-1 CRADLE", 0.0, -7.6, {"side": "bottom", "height": 0.7}))
    items.append((str(Y["rev"]), 0.0, -8.8, {"side": "bottom", "height": 0.7}))
    return items

#: two-layer rule set: the board minimums of the toolchain's standard fab,
#: wider default tracks (this board has room)
CRADLE_RULES = replace(US_4L_STD, name="US_2L_STD", default_track=0.20, power_track=0.40,
                       default_clearance=0.15)


def _status(status, note=""):
    return {"Status": status, "StatusNote": note} if note else {"Status": status}


def spring_pin_footprint():
    m = MILLMAX_0914
    pad = F.PadSpec("1", 0.0, 0.0, m["pad_dia"], m["pad_dia"], "circle", "th", drill=m["hole_dia"])
    return F.FootprintSpec(
        name="MillMax_0914_TH_PROVISIONAL", pads=[pad], body=(m["barrel_dia"], m["barrel_dia"]),
        height=m["height_above_board"], silk=False, courtyard_margin=0.15,
        description="PROVISIONAL: Mill-Max 0914 spring pin, hole %.2f, pad %.2f"
                    % (m["hole_dia"], m["pad_dia"]), tags="spring pin pogo")


def service_pads_footprint():
    return F.pad_row("ServicePads_4x1.5mm_P2.54", 4, 2.54, 1.5,
                     description="4 bare pads 1.5 mm on 2.54 mm: GND SWDIO SWCLK NRST "
                                 "(factory fixture: probe or solder a 1x4 header)")


def gl1_cradle_design(name=DESIGN_NAME, placement=None):
    place = dict(PLACEMENT)
    place.update(placement or {})
    outline = Outline(RoundedPolygon.rect(0.0, 0.0, BOARD_DX, BOARD_DY))
    for i, (x, y) in enumerate(SCREWS, start=1):
        outline.add_hole(x, y, SCREW_HOLE_DIA, name="MH%d" % i)
    d = Design(name, outline, layers=2, rules=CRADLE_RULES, board_thickness=BOARD_THICKNESS,
               title="GreenLine GL-1 cradle board",
               revision=str(Y["rev"]), company="GreenLine")
    d.fab_notes += [
        "The TOP face lies against a plastic ceiling: only J1 and the spring pins stand on it.",
        "Spring pins SP1-SP7 are soldered square to the board in a jig (mechanical/README).",
        "Lead-free assembly (SAC305), RoHS-compliant parts (DESIGN_SPEC E5).",
    ]

    # ---- USB-C receptacle, top side, mouth toward -y, overhanging the rear edge ----------
    # spec E6: "USB-C receptacle (USB 2.0)"; YAML: "GCT USB4105 USB-C receptacle, rear exit"
    usb_pins = {
        # one pad object per wide land: A1 is also contact B12, A4 also B9, A9 also B4, A12 also B1
        # (make_usb_footprint.MERGED_LANDS: the router cannot join two coincident pads of one net)
        "GND": (("A1", "A12"), "passive"), "VBUS": (("A4", "A9"), "passive"),
        "CC1": ("A5", "passive"), "CC2": ("B5", "passive"),
        "DP": (("A6", "B6"), "passive"), "DM": (("A7", "B7"), "passive"),
        "SBU1": ("A8", "nc"), "SBU2": ("B8", "nc"), "SHIELD": ("S1", "passive"),
    }
    j1 = Part("J1", "USB-C", USBC, pins=usb_pins, mpn="USB4105-GF-A", manufacturer="GCT",
              distributor="Digi-Key", distributor_pn="2073-USB4105-GF-ACT-ND", unit_price=1.09,
              height_mm=3.26, group="usb", allow_overhang=True,
              description="USB Type-C receptacle, USB 2.0, 16 pin, top mount, horizontal",
              fields=_status(PROV, "MPN, KiCad footprint, Digi-Key PN research-confirmed; body "
                                   "8.94 x 7.35 x 3.26 mm is the mechanical model's PROVISIONAL envelope; "
                                   "the land pattern is a project copy with four ground pads 0.04 mm "
                                   "shorter (make_usb_footprint.py), not checked against GCT's drawing"))
    j1.place(0.0, round(USB_MOUTH_Y + USB_BODY_FRONT, 4), 0.0)
    d.add(j1)
    # ---- spec E6: "5.1 kohm from CC1 and from CC2 to ground (without them a C-to-C charger
    # supplies nothing)" ------------------------------------------------------------------------
    for ref, cc in (("R1", "CC1"), ("R2", "CC2")):
        p = Part(ref, "5k1", R0402, pins=two_pin(), mpn="RC0402FR-075K1L", manufacturer="Yageo",
                 distributor=BY_MPN, distributor_pn="RC0402FR-075K1L", side=BOTTOM, height_mm=0.40,
                 group="usb", description="Resistor 0402 1 % 5.1 kohm",
                 fields=dict(_status(PROV, "MPN from memory"), Purpose="Rd on %s" % cc))
        p.place(*place[ref][:2], place[ref][2])
        d.add(p)
        d.net(cc, "J1.%s" % cc, "%s.1" % ref)
        d.net("GND", "%s.2" % ref)
    # ---- spec E6: "a resettable fuse in VBUS (hold about 0.2 A, trip about 0.5 A, PROPOSED)" ----
    f1 = Part("F1", "PTC %.1fA" % (PTC["hold_mA"] / 1000.0), PTC["footprint"], pins=two_pin(),
              mpn=PTC["mpn"], manufacturer=PTC["manufacturer"], distributor=BY_MPN,
              distributor_pn=PTC["mpn"], side=BOTTOM, height_mm=PTC["height"], group="usb",
              description="Resettable fuse, hold %d mA, trip %d mA, %d V, 0603"
                          % (PTC["hold_mA"], PTC["trip_mA"], PTC["v_max"]),
              fields=_status(PROV, "ratings from DESIGN_SPEC E6 (PROPOSED); order code, voltage and "
                                   "resistance from memory: any 0603 PTC with hold 0.2 A, trip <= 0.5 A, "
                                   ">= 6 V, <= 5 ohm fits"))
    f1.place(*place["F1"][:2], place["F1"][2])
    d.add(f1)
    d.net("VBUS_IN", "J1.VBUS", "F1.1", netclass="Power", power_flag=True)   # from the USB host
    d.net("VBUS", "F1.2", netclass="Power")
    # ---- spec E6: "USBLC6-2SC6 on VBUS / D+ / D-" ---------------------------------------------------
    u1 = Part("U1", "USBLC6-2SC6", SOT236,
              pins={"IO1A": ("1", "passive"), "GND": ("2", "power_in"), "IO2A": ("3", "passive"),
                    "IO2B": ("4", "passive"), "VBUS": ("5", "power_in"), "IO1B": ("6", "passive")},
              mpn="USBLC6-2SC6", manufacturer="STMicroelectronics", distributor="Digi-Key",
              distributor_pn="497-5235-1-ND", unit_price=0.36, side=BOTTOM, height_mm=1.45,
              group="usb", description="USB ESD protection, SOT-23-6",
              fields=_status(RES, "MPN, pin order (KiCad symbol), Digi-Key PN research-confirmed"))
    u1.place(*place["U1"][:2], place["U1"][2])
    d.add(u1)
    d.net("VBUS_IN", "U1.VBUS")
    d.net("USB_DM", "J1.DM", "U1.IO1A", "U1.IO1B")
    d.net("USB_DP", "J1.DP", "U1.IO2A", "U1.IO2B")
    c1 = Part("C1", "100n", C0402, pins=two_pin(), mpn="GRM155R71C104KA88D", manufacturer="Murata",
              distributor=BY_MPN, distributor_pn="GRM155R71C104KA88D", side=BOTTOM, height_mm=0.55,
              group="usb", description="MLCC 0402 100 nF 16 V X7R",
              fields=dict(_status(PROV, "MPN from memory"), Purpose="U1 VBUS - ADDED"))
    c1.place(*place["C1"][:2], place["C1"][2])
    d.add(c1)
    d.net("VBUS_IN", "C1.1")
    d.net("GND", "J1.GND", "J1.SHIELD", "U1.GND", "C1.2", netclass="Power")
    # ---- seven spring-pin positions, top side: four fitted, three for the factory fixture ----------
    pin_fp = spring_pin_footprint()
    consumer = {"VBUS": "VBUS", "D-": "DM", "D+": "DP", "GND": "GND"}
    fitted = {consumer[n] for n in CONSUMER_PINS}
    nets = {"VBUS": "VBUS", "DM": "USB_DM", "DP": "USB_DP", "GND": "GND",
            "SWDIO": "SWDIO", "SWCLK": "SWCLK", "NRST": "NRST"}
    for i, (pname, x) in enumerate(zip(PIN_NAMES, PIN_XS), start=1):
        sp = Part("SP%d" % i, "0914 pin", pin_fp, pins={"1": ("1", "passive")}, mpn=MILLMAX_0914["mpn"],
                  manufacturer="Mill-Max", distributor="Digi-Key", distributor_pn="ED8185-ND",
                  height_mm=MILLMAX_0914["height_above_board"], group="pins",
                  dnp=pname not in fitted,
                  description="Spring pin, long stroke, 0.59 N at the working height",
                  fields=dict(_status(PROV, "series and stroke research-confirmed; tail, barrel and "
                                            "plunger diameters and the land pattern are not (MILLMAX_0914); "
                                            "Digi-Key PN from docs/sourcing.csv"),
                              Purpose="pin %d: %s%s" % (i, pname, "" if pname in fitted
                                                         else " (factory fixture only)")))
        sp.place(round(x, 4), round(PIN_Y, 4), 0.0)
        d.add(sp)
        d.net(nets[pname], "SP%d.1" % i)
    # ---- the three service positions: bare pads on the bottom for the factory fixture --------------
    j2 = Part("J2", "Service pads", service_pads_footprint(),
              pins={"GND": ("1", "passive"), "SWDIO": ("2", "passive"), "SWCLK": ("3", "passive"),
                    "NRST": ("4", "passive")},
              side=BOTTOM, in_bom=False, height_mm=0.0, group="pins",
              description="GND SWDIO SWCLK NRST for the factory fixture (bare pads, nothing fitted)")
    j2.place(*place["J2"][:2], place["J2"][2])
    d.add(j2)
    d.net("GND", "J2.GND")
    d.net("SWDIO", "J2.SWDIO")
    d.net("SWCLK", "J2.SWCLK")
    d.net("NRST", "J2.NRST")

    # ---- mechanics -----------------------------------------------------------------------------------------
    exempt = ("J1",) + tuple("SP%d" % i for i in range(1, 8))
    d.add_height_limit(RoundedPolygon.rect(0.0, 0.0, BOARD_DX + 2.0, BOARD_DY + 4.0), 0.0, side=TOP,
                       exempt=exempt, name="pocket_ceiling")
    for i, (x, y) in enumerate(SCREWS, start=1):
        d.add_placement_keepout(Circle(x, y, SCREW_HEAD_DIA / 2.0 + 0.3), side=BOTTOM,
                                name="screw_head_%d" % i)
        d.add_keepout(Circle(x, y, SCREW_HEAD_DIA / 2.0 + 0.2), layers=("B.Cu",),
                      name="screw_head_%d_copper" % i, tracks=True, vias=True, copper=True)
    for x, y in FIDUCIALS_TOP:
        d.add_fiducial(x, y)
    for x, y in FIDUCIALS_BOTTOM:
        d.add_fiducial(x, y, side=BOTTOM)
    return d


if __name__ == "__main__":
    from gleda import checks
    design = gl1_cradle_design()
    print(design)
    print(checks.run_checks(design).text())
