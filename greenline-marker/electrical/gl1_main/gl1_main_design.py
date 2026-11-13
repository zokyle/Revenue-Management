#!/usr/bin/python3
"""GreenLine GL-1 main board - netlist and layout as code (gleda 0.4.0).

STAGE: LAYOUT.  Nothing has been built.  This file holds every part, net, net
class, footprint, the MCU pin map, the mechanical contract of the board
(outline, locating features, keep-outs, height limits) and the placement
(``PLACEMENT``, ``CAM_ARRAY_MAP``, the fiducials, ``ROUTER_OPTIONS``).
``build_gl1_main.py`` routes it with the toolchain's router and takes it
through KiCad's DRC and the output stage; ``build_netlist.py`` is the earlier
stage without copper.  ``LAYOUT_LOG.md`` records every routing attempt and
says why the parts are where they are.

Implements DESIGN_SPEC rev D with the amendments E1 to E16.  The ones that
change the netlist: E1 (charger TI BQ25101 with a hardware thermistor input),
E2 (two cell thermistors, Murata NCU15XH103F60RC), E3 (named LED parts),
E4 (four top-side test points) and the stated order of the seven underside
pads.

Sources of truth (read-only):

* ``design/DESIGN_SPEC.md`` section 4 - the electrical rules.  Each block
  below quotes the rule it implements; ``NETLIST_NOTES.md`` has the table
  rule -> net / part and every calculation.
* ``design/master_params.yaml`` - read at import time (``Y``): outline,
  locating hole and slot, tub keep-outs, battery, cameras, J1, the underside.
  No mechanical number is typed into this file a second time, except where a
  comment says so.
* ``firmware/hal/stm32u5/gl_pins.h`` - the firmware's pin proposal; ``PINMAP``
  is the final map (``check_pinmap.py`` verifies it against ST's open pin
  data and exports ``pinmap.json``).

Evidence levels used in comments and in every part's ``Status`` field:

* RESEARCH  - seen in ``docs/research/*.md`` with status "confirmed" (a
  search extract, the installed KiCad library or a public repository file).
  That is not the manufacturer's datasheet.
* PINDATA   - read from ST's open pin data (STM32U585RITx.xml and the GPIO
  modes file), re-checked by ``check_pinmap.py`` on every run.
* PROVISIONAL - from engineering memory or an unconfirmed search extract.
  Must be checked against the datasheet / drawing before boards are ordered.

The PROVISIONAL items that can mirror or scramble a whole part are isolated
in ONE table each, so that each can be corrected in one place:

    OVM7692_BALLS (+ OVM7692_PITCH, OVM7692_PAD_D)   camera ball map
    BQ25101_BALLS (+ BQ25101_PITCH, BQ25101_PAD_D)   charger ball map
    LCD_TAIL (+ LCD_TAIL_PIN1_EDGE)                  LCD tail order and pin-1 edge
    VEMD8080_PADS                                    photodiode land pattern

    /usr/bin/python3 -B electrical/gl1_main/gl1_main_design.py     # prints the checks
"""
import math
import os
import sys
from dataclasses import replace

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.normpath(os.path.join(HERE, "..", "tools"))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import yaml                                                              # noqa: E402

from gleda.model import (Design, Outline, PathShape, RoundedPolygon, Circle, Slot, Part,   # noqa: E402
                         two_pin, US_4L_STD, BOTTOM, TOP, ALL_LAYERS)
from gleda import footprints as F                                        # noqa: E402

YAML_PATH = os.path.normpath(os.path.join(HERE, "..", "..", "design", "master_params.yaml"))
with open(YAML_PATH, encoding="utf-8") as _fh:
    Y = yaml.safe_load(_fh)

DESIGN_NAME = "gl1_main"

# ---------------------------------------------------------------------------
# 1. Mechanical contract, taken from design/master_params.yaml
# ---------------------------------------------------------------------------
PCB = Y["pcb"]
KO = Y["tub_keepouts"]
BAT = Y["battery"]
CAM = Y["cameras"]
BOT = Y["bottom_side_parts"]
BOARD_RADIUS = PCB["radius"]                         # 21.1
FLAT_Y = PCB["flat_y"]                               # 17.3
BOARD_THICKNESS = PCB["thickness"]                   # 0.8
LOC_ROUND = PCB["locating_holes"]["round"]           # NPTH 1.15 at (14.35, 10.8)
LOC_SLOT = PCB["locating_holes"]["slot"]             # NPTH slot 1.15 x 2.2 along x at (-14.35, 10.8)
EDGE_KEEP_IN = PCB["component_edge_clearance"]       # 0.2: part bodies stay this far inside the edge
FREE_HEIGHT = KO["free_height_above_pcb"]            # 2.55
CAM_L = (CAM["left"]["x"], CAM["left"]["y"])
CAM_R = (CAM["right"]["x"], CAM["right"]["y"])
CAM_BODY = (CAM["body_dx"], CAM["body_dy"])          # 3.47 x 2.95
CAM_HEIGHT = CAM["height"]                           # 2.76
_J1 = next(p for p in Y["top_side_parts"] if p["ref"] == "J1")
#: The YAML point of J1 is used as the footprint ANCHOR of the KiCad FH12 land pattern, because
#: that is what mechanical/cad/board_import.py (check C) compares.  It is NOT where the
#: mechanical model has the connector: the model draws the YAML box (dx x dy) CENTRED on the
#: point, with the mouth on its rear edge (J1_BOX[1], y = -16.8, where the LCD-tail keep-out
#: ends).  The body of the land pattern lies 1.6 mm behind its anchor, so on the board the
#: rear face of J1 is at y = -18.3, 1.5 mm behind the modelled mouth, and the body covers the
#: tail keep-out.  The contract cannot be met as written either: with the rear face at
#: y = -16.8 the signal pads would end at y = -9.9, 0.3 mm inside the cell.  OPEN ITEM for the
#: YAML / mechanical owner; check_netlist_rules.py row "PCB k2" measures it, NETLIST_NOTES 5.1
#: has the numbers.
J1_XY = (_J1["x"], _J1["y"])
J1_HEIGHT = _J1["h"]
#: the box the mechanical model draws for J1: (x min, y min, x max, y max)
J1_BOX = (_J1["x"] - _J1["dx"] / 2.0, _J1["y"] - _J1["dy"] / 2.0,
          _J1["x"] + _J1["dx"] / 2.0, _J1["y"] + _J1["dy"] / 2.0)
LCD_EXIT_EDGE = Y["lcd"]["fpc_exit_edge"]            # "rear": the tail leaves the glass toward -y
_U9 = next(p for p in Y["top_side_parts"] if p["ref"] == "U9")
LED_RING = BOT["grain_led_ring"]
PD_POS = BOT["photodiode"]
VIA_KO = BOT["via_keepouts"]
PAD_ROW = Y["base_plate"]["pad_holes"]               # xs and y of the seven underside pads
PAD_DIA = 1.8                                        # "7 gold pads dia 1.8": the YAML gives it only as text (bottom_side_parts.pads)
FEET = KO["foot_zones"]                              # dia 2.5 zones, dia 1.6 lands, part_margin 0.3
BAT_PAD_ZONE = BAT["pads"]["zone"]
BAT_PAD_SIZE = tuple(BAT["pads"]["size"])            # 1.5 x 2.4
#: gap between the two lead pads; mechanical/cad/params.py (bat_pad_gap) uses the same number,
#: it is not in the YAML
BAT_PAD_GAP = 0.7
#: spec E4: "1.0 mm bare round pads reachable by spring probes"
TEST_POINT_DIA = 1.0

#: pitch of the two LEDs of a pair along the tangent.  The mechanical model draws 0.90 mm
#: (led_pair_offset 0.45); two KiCad 0402 LED courtyards (0.94 mm wide) need 0.95, so the
#: netlist uses 1.00.  board_import.py checks the LEDs against the baffle ring and the wall of
#: the opening, not against this number.
LED_PAIR_PITCH = 1.00

# ---------------------------------------------------------------------------
# 2. PROVISIONAL tables - correct each of them in ONE place
# ---------------------------------------------------------------------------
#: PROVISIONAL - STAND-IN.  The OVM7692-RYAA ball map, ball pitch and pad size
#: are NOT known (docs/research/bom-verification-ics.md: "Ball map: Not found";
#: release gate of DESIGN_SPEC section 7).  The footprint below is the spec's
#: "provisional 5 x 5 footprint, 0.5 mm pitch, 0.20 mm pads"; the assignment of
#: signals to balls is the toolchain demo's stand-in (supplies and ground on the
#: outer ring, the eight data balls inside).  Row A faces the flat board edge.
#: ball -> (pin name, electrical type).  The four MIPI balls and the unknown
#: 25th ball are "nc" here.  Replace this table and the two numbers below from
#: the registered OmniVision datasheet; nothing else in the netlist changes.
OVM7692_BALLS = {
    "A1": ("NC_A1", "nc"), "A2": ("NC_A2", "nc"), "A3": ("XVCLK", "input"),
    "A4": ("NC_A4", "nc"), "A5": ("NC_A5", "nc"),
    "B1": ("SIOC", "input"), "B2": ("D0", "output"), "B3": ("D1", "output"),
    "B4": ("D2", "output"), "B5": ("SIOD", "bidir"),
    "C1": ("PCLK", "output"), "C2": ("D3", "output"), "C3": ("NC_C3", "nc"),
    "C4": ("D4", "output"), "C5": ("VSYNC", "output"),
    "D1": ("DOVDD", "power_in"), "D2": ("D5", "output"), "D3": ("D6", "output"),
    "D4": ("D7", "output"), "D5": ("AVDD", "power_in"),
    "E1": ("GND1", "power_in"), "E2": ("HREF", "output"), "E3": ("DVDD", "power_out"),
    "E4": ("PWDN", "input"), "E5": ("GND2", "power_in"),
}
OVM7692_PITCH = 0.5            # PROVISIONAL (spec section 4, PCB paragraph)
OVM7692_PAD_D = 0.20           # PROVISIONAL (spec section 4, PCB paragraph)

#: PROVISIONAL - TI BQ25101YFP, 6-ball DSBGA (spec E1: "0.4 mm ball pitch, all
#: six balls on the perimeter"; "The ball map is PROVISIONAL and is kept in one
#: marked table in the netlist").  ball -> (pin name, electrical type).
#: Source (web-search extracts of TI data sheet SLUSBV8C read on 2026-11-13,
#: NOT the data sheet itself; the TI pin table came back garbled):
#:   * "C1 = CHG on the bq25101, PRE-TERM on the bq25100; C2 = VSS" - extract of
#:     ti.com/document-viewer/BQ25100/datasheet/pin_configuration_and_functions
#:   * "A1 OUT, A2 IN, B1 TS, B2 ISET, C1 CHG, C2 VSS" - extract of a third-party
#:     copy of the same data sheet (dtsheet.com/model/4116777, BQ25101H)
#: Row A at the top, column 1 at the left, seen from the TOP of the board (the
#: view the toolchain's F.bga() draws); that the TI drawing is a top view with
#: this handedness is itself PROVISIONAL.  On the BQ25100YFP fallback ball C1 is
#: the pre-charge / termination programming input: R14 (not fitted) is its
#: resistor position.  Replace this table from SLUSBV8; nothing else changes.
BQ25101_BALLS = {
    "A1": ("OUT", "power_out"), "A2": ("IN", "power_in"),
    "B1": ("TS", "passive"), "B2": ("ISET", "passive"),
    "C1": ("CHG", "open_drain"), "C2": ("VSS", "power_in"),
}
BQ25101_PITCH = 0.4            # spec E1
BQ25101_PAD_D = 0.23           # PROVISIONAL: the land KiCad's TI 0.4 mm DSBGA patterns use (NSMD)
BQ25101_BODY = (0.9, 1.6)      # spec E1 "1.6 x 0.9 mm package"; long side along the ball rows A-C
BQ25101_HEIGHT = _U9["h"]      # 0.5 (YAML)

#: PROVISIONAL.  LCD tail pin order of the Sharp LS013B7DH03 (spec section 4:
#: "from the Sharp datasheet as remembered and consistent with public drivers";
#: docs/research/bom-verification-opto.md marks the order "confirmed" from a
#: search extract of Sharp's terminal table).  TAIL pin -> function.  This is
#: the order on the TAIL; which connector pad a tail pin meets follows below.
LCD_TAIL = {1: "SCLK", 2: "SI", 3: "SCS", 4: "EXTCOMIN", 5: "DISP",
            6: "VDDA", 7: "VDD", 8: "EXTMODE", 9: "VSS", 10: "VSSA"}
#: PROVISIONAL - the ONE fact that decides whether the ten pins are mirrored
#: (release gate B16: read it from the Sharp tail drawing).  Look at the FRONT
#: (viewing side) of the display with the tail pointing UP, away from the glass:
#: "left" = tail pin 1 is at the left edge of the tail, "right" = at the right.
#:
#: Why "left" (an inference, not a drawing): docs/research/bom-verification-opto.md
#: 3.1 - the tail's contacts are on the REAR face (inferred), and a public design
#: (its [G2]) plugs the tail STRAIGHT, display face-up beside the connector, into a
#: bottom-contact Hirose FH12 on the KiCad land pattern and wires pad 1 = SCLK.  In
#: that land pattern pad 1 is at local x = -2.25 and the mouth faces local -y, so
#: the tail enters travelling +y with pin 1 at -x: the left edge when the tail
#: points up.  The one top-contact design the research found ([G4]) is wired in the
#: reverse order, as a folded tail would need.  None of those designs is confirmed
#: as built.  A wrong value mirrors all ten pins of J1.
LCD_TAIL_PIN1_EDGE = "left"
#: Where the value above comes from.  While this still starts with "inference",
#: check_netlist_rules.py (row "lcd c") accepts only the value that inference
#: gives ("left"), so that the edge cannot be flipped by accident.  When the
#: Sharp drawing has been read, put its number and sheet here and set the edge
#: to what it shows: these two lines are the whole correction.
LCD_TAIL_PIN1_SOURCE = "inference from public designs (docs/research/bom-verification-opto.md 3.1)"
#: spec: "the LCD tail makes one U-fold under the glass, which turns its contacts
#: upward".  The fold axis is parallel to x (the tail leaves the rear glass edge
#: toward -y and comes back toward +y), so it does not exchange left and right.
LCD_TAIL_FOLDS_ABOUT_X = 1
#: KiCad land pattern Hirose_FH12-10S-0.5SH at rotation 0: pad 1 at local
#: x = -2.25, pad 10 at +2.25, mouth toward local -y (read from the library file;
#: check_netlist_rules.py measures it on the placed footprint).  That the
#: top-contact FH12A numbers its contacts like the FH12 is PROVISIONAL (spec).
J1_PAD1_X_SIGN_AT_ROT0 = -1
J1_ROTATION = 0.0                                    # mouth toward -y, the rear (YAML comment on J1)


def lcd_tail_pin1_x_sign():
    """Board x side (+1 / -1) of tail pin 1 where the tail enters J1, from
    LCD_TAIL_PIN1_EDGE, the YAML exit edge and the fold.  Rear exit: the tail
    leaves the glass pointing -y, so "left when pointing up" is +x on the
    board.  A fold about an axis parallel to x keeps every x."""
    if LCD_EXIT_EDGE != "rear":
        raise ValueError("lcd.fpc_exit_edge %r: only the rear exit is worked out here" % LCD_EXIT_EDGE)
    if LCD_TAIL_PIN1_EDGE not in ("left", "right"):
        raise ValueError("LCD_TAIL_PIN1_EDGE must be 'left' or 'right'")
    return +1 if LCD_TAIL_PIN1_EDGE == "left" else -1


def lcd_tail_pin1_at_pad1(rotation=None):
    """True: tail pin n meets connector pad n.  False: the tail is mirrored
    against the land pattern, tail pin n meets pad 11 - n."""
    rot = J1_ROTATION if rotation is None else rotation
    if abs(rot % 180.0) > 1e-9:
        raise ValueError("J1 rotation %r: the mouth must face -y or +y" % rot)
    pad1_sign = J1_PAD1_X_SIGN_AT_ROT0 * (1 if abs(rot % 360.0) < 1e-9 else -1)
    return lcd_tail_pin1_x_sign() == pad1_sign


#: DERIVED (do not edit: correct LCD_TAIL_PIN1_EDGE).  With the research's
#: inference this is False: tail pin 1 (SCLK) is at +x and meets pad 10; pad 1 is
#: VSSA.  The netlist was first written with True, which that evidence contradicts.
LCD_TAIL_PIN1_AT_PAD1 = lcd_tail_pin1_at_pad1()

#: PROVISIONAL.  Vishay VEMD8080 land pattern as three public footprints have
#: it (docs/research/bom-verification-opto.md section 3.5: "not-confirmed
#: against the Vishay drawing"): eight 0.55 x 0.55 mm pads; seven are cathode,
#: the anode is one corner pad ("pad 5 in the SamacSys numbering").  Footprint
#: local mm, +y up, seen from the component side.  pad -> (x, y, terminal).
VEMD8080_PADS = {
    "1": (-2.00, -1.19, "K"), "2": (-0.69, -1.19, "K"), "3": (0.69, -1.19, "K"),
    "4": (2.00, -1.19, "K"), "5": (2.00, 1.19, "A"), "6": (0.69, 1.19, "K"),
    "7": (-0.69, 1.19, "K"), "8": (-2.00, 1.19, "K"),
}
VEMD8080_PAD_SIZE = 0.55

#: PROVISIONAL - every number behind the supply-chain table of NETLIST_NOTES 4.1
#: (cradle USB connector -> fuse -> spring pins -> Schottky D17 -> VBUS_D).
#: None of them was read from a data sheet.  ``charger_vin_min`` is the figure
#: docs/research/power.md records for the BQ2510x ("4.45-6.45 V operating
#: input", marked UNVERIFIED there); what the charger does below it (input
#: detection, any input-voltage regulation) is not known here.
SUPPLY_CHAIN = {
    "load_A": 0.030,                 # 19.8 mA charge + up to 1 mA charger + up to 8 mA VDDUSB + divider
    "cable_ohm": 0.5,                # 1 m of USB cable, both conductors
    "contacts_ohm": 0.1,             # two spring-pin contacts (VBUS and GND)
    "fuse_ohm": {"typical": 2.0, "worst": 5.0},      # cradle PTC (gl1_cradle_design.PTC, from memory)
    "schottky_V": {"typical": 0.30, "worst": 0.35},  # D17 at 30 mA (memory; not in the research)
    "charger_vin_min": 4.45,
    # (case, source voltage at the cradle's USB connector, parts)
    "cases": (("low limit of a compliant USB source, worst parts", 4.75, "worst"),
              ("low limit of a compliant USB source, typical parts", 4.75, "typical"),
              ("nominal source, worst parts", 5.00, "worst"),
              ("nominal source, typical parts", 5.00, "typical"),
              ("a legacy port that delivers 4.40 V, typical parts", 4.40, "typical")),
}


def supply_chain_rows():
    """[(case, source V, V at the VBUS pad, VBUS_D, margin to charger_vin_min)]"""
    s = SUPPLY_CHAIN
    rows = []
    for name, src, parts in s["cases"]:
        pad = src - s["load_A"] * (s["cable_ohm"] + s["contacts_ohm"] + s["fuse_ohm"][parts])
        vd = pad - s["schottky_V"][parts]
        rows.append((name, src, pad, vd, vd - s["charger_vin_min"]))
    return rows


# ---------------------------------------------------------------------------
# 3. The microcontroller: pads and pin map
# ---------------------------------------------------------------------------
#: STM32U585RITx in LQFP-64, pad 1 .. 64 (PINDATA; check_pinmap.py compares
#: every row with ST's STM32U585RITx.xml and with the installed KiCad symbol).
MCU_PAD_NAMES = (
    "VBAT PC13 PC14 PC15 PH0 PH1 NRST PC0 PC1 PC2 PC3 VSSA VDDA PA0 PA1 PA2 "
    "PA3 VSS VDD PA4 PA5 PA6 PA7 PC4 PC5 PB0 PB1 PB2 PB10 VCAP VSS VDD "
    "PB12 PB13 PB14 PB15 PC6 PC7 PC8 PC9 PA8 PA9 PA10 PA11 PA12 PA13 VSS VDDUSB "
    "PA14 PA15 PC10 PC11 PC12 PD2 PB3 PB4 PB5 PB6 PB7 PH3 PB8 PB9 VSS VDD").split()
assert len(MCU_PAD_NAMES) == 64


def mcu_pin_name(pad):
    """Pin name used in the netlist for MCU pad ``pad`` (1 .. 64): the port
    name, or VSS_<pad> / VDD_<pad> for the supply pins that share a name."""
    name = MCU_PAD_NAMES[pad - 1]
    return "%s_%d" % (name, pad) if name in ("VSS", "VDD") else name


def mcu_pad_of(port_pin):
    return MCU_PAD_NAMES.index(port_pin) + 1


#: orientation of U1 the pin map was chosen for.  With the footprint turned
#: 270 degrees pads 1-16 are on the top edge (pad 1 at the right), 17-32 on the
#: left edge (17 at the top), 33-48 on the bottom edge (33 at the left) and
#: 49-64 on the right edge (49 at the bottom).  It is the orientation of the
#: toolchain demo (routed 261 of 261) and of the YAML's nominal part list
#: (crystal top right, flash right, IMU left).  The KiCad courtyard of the
#: LQFP-64 is 13.4 mm square and the MCU sits between the tub posts E (their
#: keep-outs start at y = 13.75) and the battery (y = -0.2), so NOTHING fits
#: between the MCU and the battery: the package edge that faces the battery is
#: the one with the least decoupling work, pads 33-48.
U1_ROTATION = 270.0

S, P, C = "SPEC", "PROPOSED", "CHANGED"
CAM_OFF = "low or analog while V2V8_CAM is off"
#: The pin map.  One row per signal:
#:   signal, port pin, net, mode, function, AF, pull, initial state, source, was, reason
#: signal: the name of the row in firmware/hal/stm32u5/gl_pins.h (GL_PIN_<signal>) where one exists
#: mode: AF (alternate function, number in AF) | ANALOG | OUT_PP | IN |
#:       EXTI (input with interrupt) | SCCB_OD (bit-banged open-drain) | STRAP
#: pull: what the firmware sets ("none" unless stated) / what the board fits
#: initial state: what gl_hal_init() must establish before anything else
#: source: SPEC (fixed by DESIGN_SPEC section 4), PROPOSED (same pin as
#:   gl_pins.h), CHANGED (moved from the pin in ``was``; ``reason`` says why)
PINMAP = [
    # ---- camera port: fixed by the DCMI alternate functions (spec, PINDATA) --------------
    ("CAM_D0", "PC6", "CAM_D0", "AF", "DCMI_D0", 10, "none", CAM_OFF, S, None, ""),
    ("CAM_D1", "PC7", "CAM_D1", "AF", "DCMI_D1", 10, "none", CAM_OFF, S, None, ""),
    ("CAM_D2", "PC8", "CAM_D2", "AF", "DCMI_D2", 10, "none", CAM_OFF, S, None, ""),
    ("CAM_D3", "PC9", "CAM_D3", "AF", "DCMI_D3", 4, "none", CAM_OFF, S, None, ""),
    ("CAM_D4", "PC11", "CAM_D4", "AF", "DCMI_D4", 10, "none", CAM_OFF, S, None, ""),
    ("CAM_D5", "PB6", "CAM_D5", "AF", "DCMI_D5", 10, "none", CAM_OFF, S, None, ""),
    ("CAM_D6", "PB8", "CAM_D6", "AF", "DCMI_D6", 10, "none", CAM_OFF, S, None, ""),
    ("CAM_D7", "PB9", "CAM_D7", "AF", "DCMI_D7", 10, "none", CAM_OFF, S, None, ""),
    ("CAM_PIXCLK", "PA6", "CAM_PCLK", "AF", "DCMI_PIXCLK", 4, "none", CAM_OFF, S, None, ""),
    ("CAM_HREF", "PA4", "CAM_HREF", "AF", "DCMI_HSYNC", 10, "none", CAM_OFF, S, None, ""),
    ("CAM_VSYNC", "PB7", "CAM_VSYNC", "AF", "DCMI_VSYNC", 10, "none", CAM_OFF, S, None, ""),
    ("CAM_XVCLK", "PA8", "MCO", "AF", "RCC_MCO", 0, "none", CAM_OFF, S, None, ""),
    # ---- camera control: on the package edge that faces the cameras (pads 1-16) ----------
    ("CAM_L_SCL", "PC3", "CAM_SCL_L", "SCCB_OD", "GPIO", None, "none / 2k2 to V2V8_CAM", CAM_OFF, C, "PB3",
     "PB3 is needed for SPI1_SCK next to the flash; PC3 is the left end of the camera-facing edge"),
    ("CAM_L_PWDN", "PC2", "CAM_L_PWDN_MCU", "OUT_PP", "GPIO", None, "none / 1k series", CAM_OFF, C, "PH0",
     "PC2 sits next to CAM_L_SCL on the camera-facing edge; PH0 takes CAM_PWR_EN"),
    ("CAM_SCCB_SDA", "PC1", "CAM_SDA", "SCCB_OD", "GPIO", None, "none / 2k2 to V2V8_CAM", CAM_OFF, C, "PB5",
     "PB5 is needed for SPI1_MOSI next to the flash; PC1 is in the middle of the camera-facing edge"),
    ("CAM_R_SCL", "PC0", "CAM_SCL_R", "SCCB_OD", "GPIO", None, "none / 2k2 to V2V8_CAM", CAM_OFF, C, "PA10",
     "PA10 is on the battery-facing edge; PC0 faces the cameras, PA10 takes FLASH_CS"),
    ("CAM_R_PWDN", "PH3", "CAM_R_PWDN_MCU", "OUT_PP", "GPIO", None, "none / 10k to GND (BOOT0), 1k series", CAM_OFF, C, "PC12",
     "the BOOT0 pad must carry one signal (51 signals, 51 I/O pads). PWDN of the right camera suits it: the pad is "
     "on the edge next to that camera, the net has no pull-up (BOOT0 stays low at every reset) and a static output "
     "does not mind the 10k; the firmware's proposal, NTC_BIAS, would be loaded by it"),
    ("CAM_PWR_EN", "PH0", "CAM_EN", "OUT_PP", "GPIO", None, "none / 100k to GND", "low (rail off)", C, "PD2",
     "camera-facing edge; a static signal is the right neighbour for OSC32_OUT (pad 4); PD2 goes to the grain LEDs"),
    # ---- LCD (J1): pads 28, 29, 33 are the lower left corner, the way down to J1 -----------
    ("LCD_SCS", "PB10", "LCD_SCS", "OUT_PP", "GPIO", None, "none / 100k to GND", "low (not selected)", P, None, ""),
    ("LCD_DISP", "PB12", "LCD_DISP", "OUT_PP", "GPIO", None, "none / 100k to GND (and 200k: grain bias divider)",
     "low (display off)", C, "PB1",
     "exchanged with IMU_CS (see there): a line with a pull-DOWN is what the ROM bootloader's SPI2 chip-select "
     "input can carry without harm; pad 33 is on the way down to J1"),
    ("LCD_EXTCOMIN", "PB2", "LCD_EXTCOMIN", "AF", "LPTIM1_CH1", 1, "none", "low until LPTIM1 runs", S, None, ""),
    # ---- SPI1: flash and LCD.  MISO is fixed on PB4, so clock and data sit on its neighbours
    ("SPI1_SCK", "PB3", "SPI1_SCK", "AF", "SPI1_SCK", 5, "none", "low", C, "PA5",
     "PB3 / PB4 / PB5 are three adjacent pads on the edge that faces the flash; PA5 is on the opposite edge"),
    ("SPI1_MISO", "PB4", "SPI1_MISO", "AF", "SPI1_MISO", 5, "none", "input", S, None, ""),
    ("SPI1_MOSI", "PB5", "SPI1_MOSI", "AF", "SPI1_MOSI", 5, "none", "low", C, "PA7",
     "see SPI1_SCK"),
    ("FLASH_CS", "PA10", "FLASH_CS", "OUT_PP", "GPIO", None, "none / 100k to V2V8", "high (not selected)", C, "PA15",
     "PA10 is the ROM bootloader's USART1_RX: a pulled-up chip select is exactly the idle level it wants there, "
     "a floating charlieplex line is not. PA15 is no place for a chip select either: it is the UCPD1_CC1 pad, "
     "which gets a 5.1 kohm pull-down while PB5 (SPI1_MOSI, floating in reset) is high (PROVISIONAL)"),
    # ---- IMU on SPI2: pads 34-36 at the corner next to the IMU, chip select and interrupts on the left edge
    ("SPI2_SCK", "PB13", "SPI2_SCK", "AF", "SPI2_SCK", 5, "none", "low", P, None, ""),
    ("SPI2_MOSI", "PB15", "SPI2_MOSI", "AF", "SPI2_MOSI", 5, "none", "low", P, None, ""),
    ("SPI2_MISO", "PB14", "SPI2_MISO", "AF", "SPI2_MISO", 5, "none", "input", P, None, ""),
    ("IMU_CS", "PB1", "IMU_CS", "OUT_PP", "GPIO", None, "none / 100k to V2V8", "high (not selected)", C, "PB12",
     "PB12 is the ROM bootloader's SPI2 chip-select input and PB14 its SPI2 data output, wired to the IMU's SDO. "
     "If the ROM enables a pull-down on PB12 (the remembered AN2606 text says it does), the 100k pull-up loses, "
     "the IMU is selected and its SDO fights PB14. On PB1 (left edge, next to the IMU, no bootloader function) "
     "the pull-up always wins and SDO stays high-impedance"),
    ("IMU_INT1", "PA7", "IMU_INT1", "EXTI", "GPIO (PWR_WKUP8)", None, "none", "input", C, "PC13",
     "PA7 faces the IMU and is a wake-up pin (WKUP8); PC13 is on the far corner next to the crystal and takes "
     "VBUS_SENSE"),
    ("IMU_INT2", "PA5", "IMU_INT2", "EXTI", "GPIO", None, "none", "input", C, "PC5",
     "PA5 faces the IMU. PA5 / PA7 are the ROM bootloader's SPI1 clock and data inputs: with both driven by the "
     "IMU they always have a defined level; PC5 takes NTC_BIAS"),
    # ---- grain sensor: the corner of the package next to the LED ring ------------------------
    ("GRAIN_CP0", "PA9", "CP0_MCU", "OUT_PP", "GPIO", None, "none / 68R series", "analog (no LED lit)", C, "PC0",
     "PC0-PC3 face the cameras and carry SCCB / PWDN now; PA9, PC10, PC12, PD2 are the corner next to the "
     "LED ring"),
    ("GRAIN_CP1", "PB0", "CP1_MCU", "OUT_PP", "GPIO", None, "none / 68R series", "analog (no LED lit)", C, "PC1",
     "PC1 carries SCCB data now. The free pad at the LED corner, PA15, is the UCPD1_CC1 pad (PINDATA): a 5.1 kohm "
     "dead-battery pull-down appears on it while PB5 is high until firmware sets UCPD_DBDIS, and its output "
     "stage may be weaker than an ordinary pad's (ST's FT_c structure; both PROVISIONAL, DS13086 not read). "
     "Line 1 lights 8 of the 16 LEDs at 5 to 10 mA, so it sits on an ordinary pad instead: PB0, the nearest "
     "one with no ROM bootloader function, exchanged with CHG_STAT"),
    ("GRAIN_CP2", "PC12", "CP2_MCU", "OUT_PP", "GPIO", None, "none / 68R series", "analog (no LED lit)", C, "PC2",
     "see GRAIN_CP0"),
    ("GRAIN_CP3", "PD2", "CP3_MCU", "OUT_PP", "GPIO", None, "none / 68R series", "analog (no LED lit)", C, "PC3",
     "see GRAIN_CP0"),
    ("GRAIN_CP4", "PC10", "CP4_MCU", "OUT_PP", "GPIO", None, "none / 68R series", "analog (no LED lit)", P, None, ""),
    ("OPAMP_VINP", "PA0", "VBIAS", "ANALOG", "OPAMP1_VINP", None, "none", "analog", S, None, ""),
    ("OPAMP_VINM", "PA1", "PD_K", "ANALOG", "OPAMP1_VINM", None, "none", "analog", S, None, ""),
    ("OPAMP_VOUT", "PA3", "OPAMP_OUT", "ANALOG", "OPAMP1_VOUT / ADC1_IN8", None, "none / 150k to V2V8", "analog", S, None, ""),
    # ---- power supervision -------------------------------------------------------------------
    ("VBAT_SENSE", "PA2", "VBAT_SENSE", "ANALOG", "ADC1_IN7", None, "none", "analog", P, None, ""),
    # E1: the charger's open-drain CHG output replaces the MCP73831 STAT of gl_pins.h
    ("CHG_STAT", "PA15", "CHG_STAT", "EXTI", "GPIO", None, "none / 100k to V2V8", "input", C, "PB0",
     "exchanged with GRAIN_CP1 (see there). An INPUT is what the UCPD1_CC1 pad can carry whatever its output "
     "stage is: its reset state (JTDI, internal pull-up) agrees with the 100 kohm pull-up, and a dead-battery "
     "pull-down before firmware sets UCPD_DBDIS only makes the line read 'charging' while nobody reads it"),
    # E1: push-pull, HIGH = stop charging (gl_pins.h still describes the old open-drain, LOW = stop)
    ("CHG_INHIBIT", "PH1", "CHG_INHIBIT", "OUT_PP", "GPIO", None, "none / 100k to GND",
     "analog or low: charger on (its hardware default)", P, None, ""),
    ("VBUS_SENSE", "PC13", "VBUS_SENSE", "EXTI", "GPIO (PWR_WKUP2)", None, "none / divider 100k : 100k from VBUS", "input", C, "PA9",
     "PA9 goes to the grain LEDs; PC13 is a wake-up pin, so the cradle can wake the marker from Shutdown (ship mode, "
     "E13), and a static signal is the right neighbour for OSC32_IN (pad 3); PC13 may only sink 3 mA: it is an "
     "input here"),
    ("NTC_BIAS", "PC5", "NTC_BIAS", "OUT_PP", "GPIO", None, "none", "analog; high only during an NTC conversion",
     C, "PH3",
     "PH3 carries the 10k BOOT0 pull-down, which would load the ratiometric bias (0.28 mA more through the pin's "
     "output resistance, up to 0.4 K at 0 C); PC5 is the pad next to NTC_SENSE and no ROM bootloader pin"),
    ("NTC_SENSE", "PC4", "NTC_SENSE", "ANALOG", "ADC1_IN13", None, "none", "analog", P, None, ""),
    # ---- fixed service pins ---------------------------------------------------------------------
    ("USB_DM", "PA11", "USB_DM", "AF", "USB_OTG_FS_DM", 10, "none", "analog until USB starts", S, None, ""),
    ("USB_DP", "PA12", "USB_DP", "AF", "USB_OTG_FS_DP", 10, "none", "analog until USB starts", S, None, ""),
    ("SWDIO", "PA13", "SWDIO", "AF", "DEBUG_JTMS-SWDIO", 0, "reset state (pull-up)", "reset state", S, None, ""),
    ("SWCLK", "PA14", "SWCLK", "AF", "DEBUG_JTCK-SWCLK", 0, "reset state (pull-down)", "reset state", S, None, ""),
    ("OSC32_IN", "PC14", "OSC32_IN", "ANALOG", "RCC_OSC32_IN", None, "none", "LSE", S, None, ""),
    ("OSC32_OUT", "PC15", "OSC32_OUT", "ANALOG", "RCC_OSC32_OUT", None, "none", "LSE", S, None, ""),
    ("BOOT0", "PH3", "CAM_R_PWDN_MCU", "STRAP", "BOOT0", None, "10k to GND", "low at reset", S, None, ""),
]
PINMAP_FIELDS = ("signal", "pin", "net", "mode", "function", "af", "pull", "initial_state",
                 "source", "was", "reason")

#: the one pad that carries two rows of PINMAP on purpose (strap + GPIO)
SHARED_PINS = {"PH3": ("BOOT0", "CAM_R_PWDN")}

#: charlieplex lines of the 16 grain LEDs - the firmware's own proposal
#: (firmware/drivers/grain_frontend.c, gl_grain_fe_pair), unchanged.  Pair k
#: sits at azimuth first_azimuth + k * step of the YAML ring; (i, j) with i < j
#: are the two lines of the pair.  RED: anode on line i (the lower index),
#: cathode on j.  NIR: anode on j, cathode on i (antiparallel).  With "red
#: always from the lower to the higher line" no chain of two NIR LEDs lies in
#: parallel with a lit red LED.  Pairs (2, 4) and (3, 4) are unused.
#: On the board the LOWER line is the inner pad of both LEDs of a pair: the
#: inner pads then form three runs round the ring (line 0 four pairs, line 1
#: three pairs, line 2 one pair) and only three nets have to leave the inside
#: of the ring - no via is allowed in the grain opening.
GRAIN_PAIRS = [(0, 1), (0, 2), (0, 3), (0, 4), (1, 2), (1, 3), (1, 4), (2, 3)]

#: the eleven outputs each camera puts on the shared bus (spec)
CAM_BUS = ("D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "PCLK", "HREF", "VSYNC")
#: camera -> {camera output -> (array 0..2 of that camera, element 1..4)}: which
#: of the twelve 220 ohm elements of a camera carries which output.  ARBITRARY -
#: every permutation is the same circuit.  LAYOUT: one table per camera, because
#: the two cameras have the same (not mirrored) ball map while the board round
#: them is mirrored; the order is the one in which the fan-out of the stand-in
#: ball map reaches the arrays (LAYOUT_LOG.md).  It must be revisited when the
#: real ball map replaces the stand-in.  The twelfth element stays unconnected.
CAM_ARRAY_MAP = {
    "U2": {sig: (i // 4, i % 4 + 1) for i, sig in enumerate(CAM_BUS)},
    "U3": {sig: (i // 4, i % 4 + 1) for i, sig in enumerate(CAM_BUS)},
}
CAM_ARRAYS = {"U2": ("RN1", "RN2", "RN3"), "U3": ("RN4", "RN5", "RN6")}

# ---------------------------------------------------------------------------
# 4. Bill-of-materials data
# ---------------------------------------------------------------------------
R0402 = "Resistor_SMD:R_0402_1005Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
RN0804 = "Resistor_SMD:R_Array_Convex_4x0402"
LED0402 = "LED_SMD:LED_0402_1005Metric"
LQFP64 = "Package_QFP:LQFP-64_10x10mm_P0.5mm"
LGA14 = "Package_LGA:LGA-14_3x2.5mm_P0.5mm_LayoutBorder3x4y"
WSON8 = "Package_SON:WSON-8-1EP_6x5mm_P1.27mm_EP3.4x4mm"
SOT23 = "Package_TO_SOT_SMD:SOT-23"
SOT235 = "Package_TO_SOT_SMD:SOT-23-5"
SOT236 = "Package_TO_SOT_SMD:SOT-23-6"
SOD323 = "Diode_SMD:D_SOD-323"
FPC10 = "Connector_FFC-FPC:Hirose_FH12-10S-0.5SH_1x10-1MP_P0.50mm_Horizontal"
XTAL3215 = "Crystal:Crystal_SMD_3215-2Pin_3.2x1.5mm"

BY_MPN = "any authorised distributor (order by MPN)"
PROV = "PROVISIONAL"
RES = "RESEARCH"

#: value -> (MPN, voltage / dielectric).  All from memory of the Murata GRM
#: catalogue: PROVISIONAL (MPN, stock and height not checked; NO capacitance-
#: against-bias curve was read).  A 0402 X5R part loses capacitance under DC
#: bias: NETLIST_NOTES 4.7 has the (PROVISIONAL) effective values per node.
#: "2u2" is used where the spec's "1 uF" sits at 3.3 to 5.3 V and something
#: depends on about 1 uF being there (VBUS_D, VDDUSB, the charger output).
CAPS = {
    "100n": ("GRM155R71C104KA88D", "100 nF 16 V X7R"),
    "10n": ("GRM155R71H103KA88D", "10 nF 50 V X7R"),
    "1u": ("GRM155R61A105KE15D", "1 uF 10 V X5R"),
    "2u2": ("GRM155R61A225KE95D", "2.2 uF 10 V X5R"),
    "4u7": ("GRM155R60J475ME47D", "4.7 uF 6.3 V X5R"),
    "6p8": ("GRM1555C1H6R8CA01D", "6.8 pF 50 V C0G +-0.25 pF"),
    "10p": ("GRM1555C1H100JA01D", "10 pF 50 V C0G 5 %"),
}
#: value -> MPN (Yageo RC0402, 1 %).  From memory: PROVISIONAL.
RESISTORS = {
    "10R": "RC0402FR-0710RL", "33R": "RC0402FR-0733RL", "68R": "RC0402FR-0768RL",
    "1k": "RC0402FR-071KL", "2k2": "RC0402FR-072K2L", "6k04": "RC0402FR-076K04L",
    "6k81": "RC0402FR-076K81L", "10k": "RC0402FR-0710KL", "100k": "RC0402FR-07100KL",
    "150k": "RC0402FR-07150KL", "470k": "RC0402FR-07470KL", "1M": "RC0402FR-071ML",
}
#: spec E2: "Murata NCU15XH103F60RC, 0402, B 3380 K ... PROVISIONAL stock"
NTC_MPN = "NCU15XH103F60RC"
#: spec E3
LED_RED_MPN = "VLMS1500-GS08"
LED_NIR_MPN = "SFH 4053B"
LED_NIR_ALTERNATIVE = "Inolux IN-S42CTQIR"


def _status(status, note=""):
    return {"Status": status, "StatusNote": note} if note else {"Status": status}


def _cap(ref, value, group, purpose):
    mpn, text = CAPS[value]
    return Part(ref, value, C0402, pins=two_pin(), mpn=mpn, manufacturer="Murata",
                distributor=BY_MPN, distributor_pn=mpn, height_mm=0.55, group=group,
                description="MLCC 0402 %s" % text,
                fields=dict(_status(PROV, "MPN from memory; value per DESIGN_SPEC / NETLIST_NOTES"),
                            Purpose=purpose))


def _res(ref, value, group, purpose, dnp=False):
    mpn = RESISTORS[value]
    return Part(ref, value, R0402, pins=two_pin(), mpn=mpn, manufacturer="Yageo",
                distributor=BY_MPN, distributor_pn=mpn, height_mm=0.40, group=group, dnp=dnp,
                description="Resistor 0402 1 %% %s" % value,
                fields=dict(_status(PROV, "MPN from memory; value per DESIGN_SPEC / NETLIST_NOTES"),
                            Purpose=purpose))


# ---------------------------------------------------------------------------
# 5. Footprints that are not in the KiCad library
# ---------------------------------------------------------------------------
def camera_footprint():
    """PROVISIONAL 25-ball land pattern of the OVM7692 cube (see OVM7692_BALLS).
    Escape arithmetic (spec E7): pitch 0.50 - pad 0.20 = 0.30 = one 0.10 mm
    track + two 0.10 mm clearances; the pads carry a 0.10 mm clearance override
    so that the fine geometry stays at the package."""
    return F.bga("OVM7692_BGA25_P0.5_PROVISIONAL", 5, 5, pitch=OVM7692_PITCH, pad_d=OVM7692_PAD_D,
                 body=CAM_BODY, height=CAM_HEIGHT, pad_clearance=0.10, courtyard_margin=0.2,
                 description="PROVISIONAL stand-in land pattern, OVM7692-RYAA cube 3.47 x 2.95 x 2.76 mm")


def charger_footprint():
    """PROVISIONAL land pattern of the BQ25101YFP (see BQ25101_BALLS): 2 columns
    x 3 rows on 0.4 mm, A1 top left, made with the toolchain's BGA generator.

    Copper: round lands of 0.23 mm (BQ25101_PAD_D), i.e. 0.17 mm between two
    lands - more than the standard 0.127 mm clearance, so the pads need NO
    clearance override and the part is laid out with the default rules.  Every
    ball is on the perimeter (2 columns), so no track passes between two balls;
    a 0.15 mm track leaves each land outward with 0.21 mm to the neighbouring
    lands.  The two supply nets (0.30 mm class) neck down to 0.15 mm at the
    0.23 mm lands (class Power, min_track_width).  The router does not treat
    the part as a fine-pitch array (fewer than nine balls): no escape stage,
    no via keep-out; vias keep the normal distance from the lands.

    Mask and paste: the toolchain's board-level mask expansion is 0, so the
    mask opening is drawn 1:1 on the land (0.23 mm) and the web between two
    openings is 0.17 mm; paste 1:1.  Fab note: the fabricator's own mask
    compensation must leave a web of at least 0.075 mm between these six
    openings (and between the camera balls).  Whether TI recommends a
    non-solder-mask-defined land of this size for the YFP package is
    PROVISIONAL (memory of TI's wafer-level-package application note; the
    mechanical page of SLUSBV8 has not been read)."""
    return F.bga("BQ25101_YFP_DSBGA6_P0.4_PROVISIONAL", 2, 3, pitch=BQ25101_PITCH,
                 pad_d=BQ25101_PAD_D, body=BQ25101_BODY, height=BQ25101_HEIGHT,
                 courtyard_margin=0.2,
                 description="PROVISIONAL land pattern, TI BQ25101YFP DSBGA-6 1.6 x 0.9 mm, 0.4 mm pitch")


def photodiode_footprint():
    """PROVISIONAL land pattern of the VEMD8080 (see VEMD8080_PADS)."""
    pads = [F.PadSpec(num, x, y, VEMD8080_PAD_SIZE, VEMD8080_PAD_SIZE, "rect")
            for num, (x, y, _t) in VEMD8080_PADS.items()]
    return F.FootprintSpec(
        name="VEMD8080_4.8x2.5mm_PROVISIONAL", pads=pads, body=(PD_POS["dx"], PD_POS["dy"]),
        height=PD_POS["h"], pin1=(-2.9, -1.19), courtyard_margin=0.25,
        description="PROVISIONAL land pattern, Vishay VEMD8080 photodiode 4.8 x 2.5 x 0.48 mm",
        tags="photodiode")


def contact_row_footprint():
    """Seven flush contact pads for the cradle spring pins.  The name is the
    one mechanical/cad/board_import.py parses (count, pad diameter, pitch)."""
    xs = PAD_ROW["xs"]
    pitch = round(xs[1] - xs[0], 4)
    return F.pad_row("ContactRow_%dx%.1fmm_P%.2f" % (len(xs), PAD_DIA, pitch), len(xs), pitch,
                     PAD_DIA, description="7 flush contact pads for the cradle spring pins "
                                          "(ENIG at EVT, selective hard gold in production)")


def foot_land_footprint():
    """Unmasked dia 1.6 copper land a ball foot bears on (no paste, no net)."""
    d = FEET["land_dia"]
    pad = F.PadSpec("", 0.0, 0.0, d, d, "circle", "conn")
    return F.FootprintSpec(
        name="BallFootLand_D%smm" % ("%g" % d), pads=[pad], body=(d, d), height=0.0, silk=False,
        description="Bare copper land dia %g mm under a ball foot (mechanical, no net)" % d,
        tags="ball foot land", exclude_from_bom=True, exclude_from_pos=True, board_only=True,
        courtyard_margin=0.1)


# ---------------------------------------------------------------------------
# 6. Nominal placement (top side unless computed).  ref -> (x, y, rotation)
# ---------------------------------------------------------------------------
#: NOMINAL.  U2, U3, J1, the battery pads, the underside pads, LEDs, photodiode
#: and foot lands are computed from the YAML and are not in this table.
#: Constraints the nominal placement already shows (NETLIST_NOTES section 8):
#: * U1: its pad copper is 0.45 mm from the cell body; 0.80 mm is the most any
#:   placement can give (13.4 mm courtyard between the cell and the post feet).
#: * RT1 (the charger's NTC) is 2.5 mm from the charger U9 and over the cell
#:   proper, not over its protection-board end (x < about -13); aim for 3 mm.
#: * every pad keeps 0.2 mm from the post-foot keep-out squares (R4, R5, R10, C29
#:   were 0.18 to 0.19 mm).
#: * R24 (line 1 of the LED ring, now on PB0 / pad 26) and R15 (now on the VBUS
#:   pad net) still sit where their old nets were: legal, not sensible.
PLACEMENT = {
    "U1": (0.0, 6.7, U1_ROTATION),
    "U6": (11.50, 6.40, 0.0), "U4": (-10.80, 4.00, 0.0), "U8": (-10.90, 9.60, 0.0),
    "Y1": (9.75, 10.40, 0.0), "U10": (-12.90, -13.05, 0.0), "U9": (-9.90, -12.40, 0.0),
    "U7": (8.70, -12.15, 0.0), "U11": (13.45, -12.30, 0.0), "D17": (-11.20, -15.80, 0.0),
    "Q1": (-7.60, -15.50, 0.0), "RN1": (-6.40, 15.40, 0.0), "RN2": (-9.00, 12.80, 90.0),
    "RN3": (-11.60, 12.80, 90.0), "RN4": (6.40, 15.40, 0.0), "RN5": (9.00, 12.80, 90.0),
    "RN6": (11.60, 12.80, 90.0), "C6": (-7.25, 3.95, 90.0), "C2": (-7.25, 1.95, 90.0),
    "C1": (-7.25, 9.45, 90.0), "C12": (7.20, 11.85, 90.0), "C3": (7.25, 8.25, 90.0),
    "C4": (2.80, 14.40, 90.0), "C7": (-2.80, 14.40, 90.0), "C8": (-2.40, 16.00, 0.0),
    "R1": (-4.40, 16.00, 0.0), "C9": (7.25, 1.00, 90.0), "C5": (-8.30, 3.00, 90.0),
    "C11": (12.30, 10.40, 90.0), "C10": (2.40, 16.00, 0.0), "R8": (4.40, 16.00, 0.0),
    "R2": (7.25, 6.35, 90.0), "R3": (7.25, 4.40, 90.0), "R9": (8.30, 1.00, 90.0),
    "C13": (15.35, 8.30, 90.0), "C14": (-7.20, 12.15, 90.0), "C15": (-12.50, 15.00, 90.0),
    "C16": (-13.40, 12.95, 90.0), "R6": (-14.40, 12.95, 90.0), "R4": (-16.00, 12.15, 90.0),
    "C18": (6.20, 12.15, 90.0), "C17": (12.50, 15.00, 90.0), "C19": (13.40, 12.95, 90.0),
    "R7": (14.40, 12.95, 90.0), "R5": (16.00, 12.15, 90.0), "C25": (-8.30, 10.40, 90.0),
    "C24": (-13.50, 8.60, 90.0), "R10": (-15.00, 9.15, 0.0), "R28": (-6.20, 11.85, 90.0),
    "C33": (-8.30, 8.40, 90.0), "C29": (-6.00, 13.60, 0.0), "C30": (-9.75, 1.75, 0.0),
    "C31": (-11.70, 1.75, 0.0), "RT2": (-9.40, 0.40, 0.0), "R19": (-11.40, 0.40, 0.0),
    "R21": (-7.25, 6.70, 90.0), "R22": (-8.30, 6.50, 90.0), "R31": (-9.35, 6.70, 90.0),
    "R20": (-10.40, 6.70, 90.0), "R29": (-12.30, 6.70, 90.0), "R30": (-13.35, 6.65, 90.0),
    "C34": (-14.35, 6.70, 90.0), "R17": (-16.00, 7.90, 0.0), "R18": (-18.00, 7.90, 0.0),
    "R23": (9.40, 2.90, 0.0), "R24": (11.40, 2.90, 0.0), "R25": (13.40, 2.90, 0.0),
    "R26": (10.40, 1.90, 0.0), "R27": (12.40, 1.90, 0.0), "RT1": (-6.55, -10.70, 0.0),
    "C27": (-8.50, -10.70, 0.0), "R14": (-10.45, -10.70, 0.0), "R12": (-12.40, -10.70, 0.0),
    "C28": (-15.50, -12.50, 90.0), "C26": (-8.70, -12.30, 90.0), "R11": (-7.70, -12.30, 90.0),
    "R13": (-6.70, -12.30, 90.0), "C32": (6.15, -11.50, 90.0), "C21": (6.15, -13.45, 90.0),
    "R15": (6.15, -15.40, 90.0), "C20": (9.30, -14.60, 0.0), "C23": (12.30, -14.75, 0.0),
    "C22": (15.90, -12.20, 90.0), "R16": (17.60, -1.40, 90.0), "TP1": (-18.20, 3.40, 0.0),
    "TP2": (10.60, -16.20, 0.0), "TP3": (-17.30, 9.60, 0.0), "TP4": (18.40, 2.60, 0.0),
}

FIDUCIALS_TOP = [(-19.0, 0.9), (18.6, -5.5), (17.3, 8.6)]
FIDUCIALS_BOTTOM = [(-13.5, -3.0), (14.0, -7.0), (0.0, 11.0)]

#: LAYOUT: options of the toolchain's router (gleda.router.RouterOptions) this
#: board is routed with; build_gl1_main.py passes them on, and they are part of
#: the fingerprint of the stored routing.  LAYOUT_LOG.md says why each is set.
ROUTER_OPTIONS = {"escape_neighbours": False, "escape_attempts": 6}
#: seconds after which the router starts no new work (what is open then is
#: reported as unrouted and the build fails)
ROUTER_TIME_LIMIT = 3600.0

#: LAYOUT: per-net router options (gleda.model.Net: layers, max_vias, priority).
#: The two crystal nets stay on the top layer and take no via (short, over the
#: solid ground plane of layer 2, nothing of them on the far side of the board);
#: they and the USB pair are routed before the rest so that they get the direct
#: way.  The router has no guard-trace and no differential-pair mode: what runs
#: how close to these nets is measured afterwards (layout_quality.py).
NET_ROUTING = {
    "OSC32_IN": {"layers": ("F.Cu",), "max_vias": 0, "priority": 3},
    "OSC32_OUT": {"layers": ("F.Cu",), "max_vias": 0, "priority": 3},
    "USB_DM": {"priority": 1},
    "USB_DP": {"priority": 1},
}


def led_positions():
    """[(ref, colour, x, y, rotation, azimuth, anode line, cathode line)] of the
    16 grain LEDs.  Pair k: D(2k+1) red, D(2k+2) NIR, both lying along the
    radius (the mechanical model's orientation), LED_PAIR_PITCH apart along the
    tangent.  Bottom side: pad 1 (K) of a KiCad 0402 LED lies toward -x of the
    footprint, pad 2 (A) toward +x.  Red: rotation = azimuth + 180 puts the
    anode on the INNER pad; NIR: rotation = azimuth puts the cathode on the
    inner pad.  Both inner pads of a pair are then the lower line, both outer
    pads the higher line (check_netlist_rules.py measures it)."""
    cx, cy, r = LED_RING["x"], LED_RING["y"], LED_RING["radius"]
    out = []
    for k, (i, j) in enumerate(GRAIN_PAIRS):
        az = LED_RING["first_azimuth_deg"] + LED_RING["step_deg"] * k
        a = math.radians(az)
        for n, (colour, off) in enumerate((("red", -LED_PAIR_PITCH / 2.0),
                                           ("NIR", LED_PAIR_PITCH / 2.0))):
            x = cx + r * math.cos(a) - off * math.sin(a)
            y = cy + r * math.sin(a) + off * math.cos(a)
            rot = (az + 180.0) % 360.0 if colour == "red" else az % 360.0
            anode, cathode = (i, j) if colour == "red" else (j, i)
            out.append(("D%d" % (2 * k + 1 + n), colour, round(x, 4), round(y, 4), rot, az,
                        anode, cathode))
    return out


def battery_pad_positions():
    """Centres of BT1 (+) and BT2 (-): centred in x in the YAML zone, stacked
    in y about the zone centre with BAT_PAD_GAP between them (the nominal of
    mechanical/cad/params.py battery_pad_rects)."""
    zx, zy = BAT_PAD_ZONE["x"], BAT_PAD_ZONE["y"]
    cx, cy = 0.5 * (zx[0] + zx[1]), 0.5 * (zy[0] + zy[1])
    off = 0.5 * (BAT_PAD_SIZE[1] + BAT_PAD_GAP)
    return (round(cx, 4), round(cy + off, 4)), (round(cx, 4), round(cy - off, 4))


# ---------------------------------------------------------------------------
# 7. The design
# ---------------------------------------------------------------------------
#: spec section 4, PCB paragraph: "default 0.15 mm tracks with 0.127 mm
#: clearance, and a fine net class of 0.10 mm track / 0.10 mm clearance used
#: only to escape the camera BGAs"; 0.25 mm drill, through vias only.
GL1_RULES = replace(US_4L_STD, name="GL1_4L_0.10mm", min_track=0.10, min_clearance=0.10)

#: WORKAROUND for a gap between two other packages - reported, not hidden.
#: mechanical/cad/board_import.py (check D) treats every fitted bottom-side
#: component of the mechanical JSON as a body that must lie inside the grain
#: opening or the pad slot; the toolchain's mechanical JSON lists copper-only
#: footprints as components.  The three ball-foot lands (which the spec itself
#: puts outside both openings) and the three bottom fiducials are bare copper
#: of zero height, and with them listed as fitted that check fails with six
#: rows "outside the grain opening and the pad slot".  With this flag they
#: carry the "not fitted" mark, which board_import.py skips on the bottom side
#: WITHOUT a warning: those six features are then not tested by it at all.
#: The flag changes no copper, no Gerber, no BOM line, no position row and no
#: line of the assembly README (its DNP list holds BOM parts only, its fiducial
#: list every fiducial); it writes a "DNP" property onto six board-only
#: footprints.  check_netlist_rules.py (row "bare copper") limits the mark to
#: exactly these six zero-height, pin-less, board-only footprints, so that no
#: real part can ride along.  Remove the flag when board_import.py ignores
#: copper-only footprints; set it to False to see the six rows.
BARE_BOTTOM_COPPER_NOT_FITTED = True
BARE_BOTTOM_COPPER_REFS = ("FL1", "FL2", "FL3", "FID4", "FID5", "FID6")


def gl1_main_design(name=DESIGN_NAME, placement=None):
    """The GL-1 main board as a :class:`gleda.model.Design`.  ``placement``
    overrides entries of ``PLACEMENT`` (ref -> (x, y, rotation))."""
    place = dict(PLACEMENT)
    place.update(placement or {})

    outline = Outline(PathShape.d_shape(BOARD_RADIUS, FLAT_Y))
    outline.add_hole(LOC_ROUND["x"], LOC_ROUND["y"], LOC_ROUND["dia"], name="H1")
    outline.add_npth_slot(LOC_SLOT["x"], LOC_SLOT["y"], width=LOC_SLOT["dia"],
                          length=LOC_SLOT["length_x"])
    d = Design(name, outline, layers=4, rules=GL1_RULES, board_thickness=BOARD_THICKNESS,
               title="GreenLine GL-1 main board",
               revision=str(Y["rev"]), company="GreenLine")
    # ---- net classes -----------------------------------------------------------------------
    d.add_netclass("Power", track_width=GL1_RULES.power_track,
                   clearance=GL1_RULES.default_clearance, min_track_width=0.15,
                   description="supply nets; neck-down to the default 0.15 mm allowed at fine pads")
    d.add_netclass("Fine", track_width=0.10, clearance=0.10,
                   description="camera-side nets only (ball to series array / pull-up): the escape "
                               "of the 0.5 mm-pitch camera BGAs")
    d.add_netclass("CamPower", track_width=0.15, clearance=0.10,
                   description="camera supply balls: a 0.15 mm track with the fine clearance, "
                               "confined to the same fine areas")
    d.via_tenting = "bottom"
    d.via_protection = ("plugged with solder mask from the BOTTOM side and tented there "
                        "(IPC-4761 type III-a); the top side of the vias stays open")
    d.fab_notes += [
        "The bottom side is a wetted surface in use: no open via holes there, and no via at all "
        "inside the grain opening (dia 13 at 0, -4) or the pad slot (17.44 x 2.2 at y -17).",
        "Under each ball foot (0, 15), (-16.5, -9.5), (16.5, -9.5): an UNMASKED dia 1.6 copper land "
        "on the bottom side inside a dia 2.5 zone without tracks and vias.",
        "Layer 2 (In1.Cu) is a solid ground plane.",
        "0.100 mm track and gap (3.94 mil) inside the two fine areas round the cameras: the "
        "fabricator must accept it in writing (DESIGN_SPEC E7, release gate).",
        "Lead-free assembly (SAC305), RoHS-compliant parts, no conformal coating (DESIGN_SPEC E5).",
        "Solder mask is drawn 1:1 on every land. U9 (6 balls on 0.4 mm, lands 0.23 mm) and U2 / U3 "
        "(25 balls on 0.5 mm, lands 0.20 mm): whatever mask compensation the fabricator applies must "
        "leave a mask web of at least 0.075 mm between the openings of these parts.",
        "Vias: 0.50 mm pad, 0.25 mm finished hole, through only. Every via is tented on the BOTTOM "
        "side and plugged from the bottom (see via protection); on the top side the via pads are open.",
    ]

    def add(part, xy=None, rot=0.0):
        if xy is None and part.ref in place:
            x, y, rot = place[part.ref]
            xy = (x, y)
        if xy is not None:
            part.place(xy[0], xy[1], rot)
        d.add(part)
        return part

    # =================================================================== MCU
    # spec: "STM32U585RIT6 (LQFP-64)"; pads from PINDATA.
    pins = {}
    for pad in range(1, 65):
        base = MCU_PAD_NAMES[pad - 1]
        etype = ("power_in" if base in ("VBAT", "VSSA", "VDDA", "VSS", "VDD", "VDDUSB")
                 else "power_out" if base == "VCAP" else "input" if base == "NRST" else "bidir")
        pins[mcu_pin_name(pad)] = (str(pad), etype)
    add(Part("U1", "STM32U585RIT6", LQFP64, pins=pins, mpn="STM32U585RIT6",
             manufacturer="STMicroelectronics", distributor="Digi-Key",
             distributor_pn="497-STM32U585RIT6-ND", height_mm=1.6, group="mcu",
             description="MCU Cortex-M33, 2 MB / 786 kB, LQFP-64 10 x 10 mm",
             fields=_status(RES, "MPN, package, pad map: research + ST open pin data; height "
                                 "1.6 mm and every electrical limit: PROVISIONAL")))
    for row in PINMAP:
        d.net(row[2], "U1.%s" % row[1])
    d.net("NRST", "U1.NRST")
    gnd = ["U1.VSSA"] + ["U1.%s" % mcu_pin_name(p) for p in (18, 31, 47, 63)]
    v2v8 = ["U1.VBAT"] + ["U1.%s" % mcu_pin_name(p) for p in (19, 32, 64)]
    d.net("VDDA", "U1.VDDA", power_flag=True)          # V2V8 through R1 (10 ohm): RC-filtered
    d.net("VCAP", "U1.VCAP")
    d.net("VDDUSB", "U1.VDDUSB", netclass="Power")

    # passives: (ref, value, net of pad 1, net of pad 2, sheet, what it is for)
    passives = [
        # spec: "100 nF per MCU supply pin plus 4.7 uF bulk; VDDA through 10 ohm with 1 uF + 10 nF"
        ("C1", "100n", "V2V8", "GND", "mcu", "U1 VDD pad 19"),
        ("C2", "100n", "V2V8", "GND", "mcu", "U1 VDD pad 32"),
        ("C3", "100n", "V2V8", "GND", "mcu", "U1 VDD pad 64"),
        ("C4", "100n", "V2V8", "GND", "mcu", "U1 VBAT pad 1"),
        ("C5", "4u7", "V2V8", "GND", "mcu", "V2V8 bulk at U1"),
        ("C6", "4u7", "VCAP", "GND", "mcu", "U1 VCAP pad 30 (internal regulator; value PROVISIONAL) - ADDED"),
        ("C7", "1u", "VDDA", "GND", "mcu", "U1 VDDA pad 13"),
        ("C8", "10n", "VDDA", "GND", "mcu", "U1 VDDA pad 13"),
        ("R1", "10R", "V2V8", "VDDA", "mcu", "VDDA filter"),
        ("C9", "100n", "VDDUSB", "GND", "mcu", "U1 VDDUSB pad 48"),
        # spec: "BOOT0 (PH3) pulled down with 10 kohm; NRST with 100 nF"
        ("C10", "100n", "NRST", "GND", "mcu", "NRST"),
        ("R2", "10k", "CAM_R_PWDN_MCU", "GND", "mcu", "BOOT0 (PH3) pull-down; the pad also drives PWDN of the right camera"),
        # spec: "32.768 kHz crystal ... (6 pF load) with load capacitors sized for 6 pF"
        ("C11", "6p8", "OSC32_IN", "GND", "mcu", "crystal load (2 x (6.0 - 2.5 pF stray) = 7 pF)"),
        ("C12", "6p8", "OSC32_OUT", "GND", "mcu", "crystal load"),
        # flash
        ("C13", "100n", "V2V8", "GND", "mcu", "U6 VCC - ADDED"),
        # spec: "100 kohm pull-ups to V2V8 on the flash and IMU chip selects"
        ("R3", "100k", "FLASH_CS", "V2V8", "mcu", "flash chip select high during reset"),
        # ---- cameras: spec rail table + the camera rules ---------------------------------
        ("C14", "100n", "V2V8_CAM", "GND", "camera", "U2 AVDD - ADDED"),
        ("C15", "100n", "V2V8_CAM", "GND", "camera", "U2 DOVDD - ADDED"),
        ("C16", "1u", "CAM_L_DVDD", "GND", "camera", "U2 DVDD (internal 1.5 V regulator)"),
        ("C17", "100n", "V2V8_CAM", "GND", "camera", "U3 AVDD - ADDED"),
        ("C18", "100n", "V2V8_CAM", "GND", "camera", "U3 DOVDD - ADDED"),
        ("C19", "1u", "CAM_R_DVDD", "GND", "camera", "U3 DVDD (internal 1.5 V regulator)"),
        ("R4", "1k", "CAM_L_PWDN_MCU", "CAM_L_PWDN", "camera", "PWDN series, left camera"),
        ("R5", "1k", "CAM_R_PWDN_MCU", "CAM_R_PWDN", "camera", "PWDN series, right camera"),
        ("R6", "2k2", "CAM_SCL_L", "V2V8_CAM", "camera", "SCCB clock pull-up, left camera"),
        ("R7", "2k2", "CAM_SCL_R", "V2V8_CAM", "camera", "SCCB clock pull-up, right camera"),
        ("R8", "2k2", "CAM_SDA", "V2V8_CAM", "camera", "SCCB data pull-up (shared)"),
        ("R9", "33R", "MCO", "CAM_XVCLK", "camera", "XVCLK series at the MCU"),
        # ---- regulators (spec rail table: 1 uF in, 1 uF out each) ----------------------------
        ("C20", "1u", "VBAT", "GND", "power", "U7 input"),
        ("C21", "1u", "V2V8", "GND", "power", "U7 output"),
        # 2.2 uF nominal where the spec says "1 uF" (DEVIATION, NETLIST_NOTES 5): at 5 V / 3.3 V a
        # 1 uF 10 V 0402 keeps roughly half / two thirds of its value (PROVISIONAL, no curve read)
        ("C22", "2u2", "VBUS_D", "GND", "power", "U11 input (2.2 uF nominal for about 1 uF at 5 V)"),
        ("C23", "2u2", "VDDUSB", "GND", "power", "U11 output (2.2 uF nominal for more than 1 uF at 3.3 V)"),
        ("C24", "1u", "VBAT", "GND", "power", "U8 input"),
        ("C25", "1u", "V2V8_CAM", "GND", "power", "U8 output"),
        ("R10", "100k", "CAM_EN", "GND", "power", "U8 EN pull-down"),
        # ---- charger, spec E1: "IN from VBUS after the Schottky with 1 uF; OUT to the cell with 1 uF" ----
        ("C26", "2u2", "VBUS_D", "GND", "power", "U9 IN (2.2 uF nominal for about 1 uF at 5 V)"),
        ("C27", "2u2", "VBAT", "GND", "power", "U9 OUT (2.2 uF nominal for more than 1 uF at 4.2 V)"),
        # "ISET resistor 6.81 kohm 1 % to ground (K = 135 A-ohm, so 19.8 mA)"
        ("R11", "6k81", "CHG_ISET", "GND", "power", "charge current 135 / 6810 = 19.8 mA"),
        # "CHG_INHIBIT ... gate of a small N-MOSFET (... gate pulled down with 100 kohm)"
        ("R12", "100k", "CHG_INHIBIT", "GND", "power", "Q1 gate pull-down: charger on with the MCU off"),
        # "CHG (open drain, low while charging) to an MCU input with a 100 kohm pull-up to V2V8"
        ("R13", "100k", "CHG_STAT", "V2V8", "power", "CHG status pull-up (remove if the BQ25100 is fitted)"),
        # "an unpopulated resistor position from that ball to ground" (BQ25100 fallback, ball C1)
        ("R14", "6k04", "CHG_STAT", "GND", "power", "NOT FITTED: pre-charge / termination resistor of the "
                                                    "BQ25100 fallback (value PROVISIONAL)"),
        ("C28", "100n", "VBUS", "GND", "power", "U10 VBUS (pad side of the Schottky) - ADDED"),
        # spec rail table, row VBUS: loads "BQ25101 IN, VBUS-sense divider" - the divider is on the
        # pad side of the Schottky, as the table has it (values: NETLIST_NOTES 4.3)
        ("R15", "100k", "VBUS", "VBUS_SENSE", "power", "VBUS sense divider, top (0.5 x VBUS at the pad)"),
        ("R16", "100k", "VBUS_SENSE", "GND", "power", "VBUS sense divider, bottom; with R15 it bleeds C28"),
        # spec: "2 x 1 Mohm divider with 100 nF to an ADC pin"
        ("R17", "1M", "VBAT", "VBAT_SENSE", "power", "battery divider, top"),
        ("R18", "1M", "VBAT_SENSE", "GND", "power", "battery divider, bottom"),
        ("C29", "100n", "VBAT_SENSE", "GND", "power", "battery divider reservoir at the ADC pin"),
        # spec E2: "NTC2 ... divider with 10.0 kohm 1 % from a GPIO (NTC_BIAS ...) to an ADC pin (NTC_SENSE)"
        ("R19", "10k", "NTC_BIAS", "NTC_SENSE", "power", "NTC2 divider, 10.0 kohm 1 %"),
        # ---- IMU ----------------------------------------------------------------------------
        ("C30", "100n", "V2V8", "GND", "sensor", "U4 VDD - ADDED"),
        ("C31", "100n", "V2V8", "GND", "sensor", "U4 VDDIO - ADDED"),
        ("R20", "100k", "IMU_CS", "V2V8", "sensor", "IMU chip select high during reset"),
        # ---- display -------------------------------------------------------------------------
        ("C32", "1u", "V2V8", "GND", "display", "LCD VDD / VDDA at J1 - ADDED"),
        # spec: "100 kohm pull-down on the LCD chip select (active high) and on DISP"
        ("R21", "100k", "LCD_SCS", "GND", "display", "LCD chip select low during reset"),
        ("R22", "100k", "LCD_DISP", "GND", "display", "LCD DISP low during reset"),
        # ---- grain sensor: spec "5 x 68 ohm", "470 kohm + 10 pF feedback", "2 x 100 kohm ... 100 nF"
        ("R23", "68R", "CP0_MCU", "CP0", "grain", "charlieplex line 0"),
        ("R24", "68R", "CP1_MCU", "CP1", "grain", "charlieplex line 1"),
        ("R25", "68R", "CP2_MCU", "CP2", "grain", "charlieplex line 2"),
        ("R26", "68R", "CP3_MCU", "CP3", "grain", "charlieplex line 3"),
        ("R27", "68R", "CP4_MCU", "CP4", "grain", "charlieplex line 4"),
        ("R28", "470k", "PD_K", "OPAMP_OUT", "grain", "transimpedance feedback"),
        ("C33", "10p", "PD_K", "OPAMP_OUT", "grain", "feedback capacitor (pole at 33.9 kHz)"),
        # the top of the divider is the LCD_DISP line (PB12), not V2V8: from the always-on rail the
        # divider would draw 14 uA for ever (the E14 sleep limit is 25 uA); DISP is high whenever
        # the display is on, which every grain measurement is (see NETLIST_NOTES)
        ("R29", "100k", "LCD_DISP", "VBIAS", "grain", "mid-rail bias divider, top (fed from LCD_DISP)"),
        ("R30", "100k", "VBIAS", "GND", "grain", "mid-rail bias divider, bottom"),
        ("C34", "100n", "VBIAS", "GND", "grain", "bias decoupling"),
        # 150 kohm, not more: with OPAMP1 off the photodiode pulls PA3 down through R28 (470 kohm);
        # 2.8 V x 470 / (470 + 150) = 2.12 V with the diode saturated at 0 V (NETLIST_NOTES 4.10)
        ("R31", "150k", "OPAMP_OUT", "V2V8", "grain", "PA3 (bootloader USART2_RX) held high while OPAMP1 "
                                                      "is off, also with light on the photodiode - ADDED"),
    ]
    for ref, value, net1, net2, group, purpose in passives:
        if ref.startswith("C"):
            add(_cap(ref, value, group, purpose))
        else:
            add(_res(ref, value, group, purpose, dnp=(ref == "R14")))
        d.net(net1, "%s.1" % ref)
        d.net(net2, "%s.2" % ref)

    # crystal: spec "Abracon ABS07-120-32.768KHZ-T (6 pF load ...)"
    add(Part("Y1", "32.768k", XTAL3215, pins=two_pin(), mpn="ABS07-120-32.768KHZ-T",
             manufacturer="Abracon", distributor="Digi-Key",
             distributor_pn="product page 3724043 (SKU not seen)",
             unit_price=0.68, height_mm=0.9, group="mcu",
             description="Crystal 32.768 kHz, 6 pF, 55 kohm, 3.2 x 1.5 mm",
             fields=_status(RES, "MPN and CL research-confirmed; KiCad land pattern drawn for the "
                                 "Epson FC-135, not checked against Abracon's; Digi-Key PN not seen")))
    d.net("OSC32_IN", "Y1.1")
    d.net("OSC32_OUT", "Y1.2")

    # flash: spec "SPI NOR flash", "flash on SPI1 with MISO on PB4"
    add(Part("U6", "MX25R6435F", WSON8,
             pins={"CS": ("1", "input"), "SO": ("2", "bidir"), "WP": ("3", "input"),
                   "GND": (("4", "9"), "power_in"), "SI": ("5", "input"),
                   "SCLK": ("6", "input"), "HOLD": ("7", "input"), "VCC": ("8", "power_in")},
             mpn="MX25R6435FZNIL0", manufacturer="Macronix", distributor="Digi-Key",
             distributor_pn="product page 6558605 (SKU not seen)", height_mm=0.8, group="mcu",
             description="SPI NOR flash 64 Mbit, 1.65-3.6 V, 8-WSON 6 x 5 mm",
             fields=_status(RES, "MPN, package, pin order research-confirmed (KiCad symbol); height "
                                 "0.8 mm and Digi-Key PN not seen")))
    d.net("FLASH_CS", "U6.CS")
    d.net("SPI1_MISO", "U6.SO")
    d.net("SPI1_MOSI", "U6.SI")
    d.net("SPI1_SCK", "U6.SCLK")
    # single-bit SPI only: WP# and pin 7 tied high.  Pin 7 is HOLD# or RESET# (SIO3) depending on
    # the family member (the KiCad symbol of the MX25R3235F calls it RESET#): high is inactive for both
    v2v8 += ["U6.VCC", "U6.WP", "U6.HOLD"]
    gnd.append("U6.GND")

    # ================================================================ cameras
    cam_fp = camera_footprint()
    cam_pins = {pin: (ball, etype) for ball, (pin, etype) in OVM7692_BALLS.items()}
    for ref, side, xy in (("U2", "L", CAM_L), ("U3", "R", CAM_R)):
        arrays = CAM_ARRAYS[ref]
        element_of = {v: k for k, v in CAM_ARRAY_MAP[ref].items()}   # (array, element) -> camera output
        assert len(element_of) == len(CAM_BUS) == 11 and sorted(CAM_ARRAY_MAP[ref]) == sorted(CAM_BUS)
        add(Part(ref, "OVM7692", cam_fp, pins=cam_pins, mpn="OVM7692-RYAA",
                 manufacturer="OmniVision", distributor="Digi-Key",
                 distributor_pn="884-1027-1-ND", unit_price=27.50, height_mm=CAM_HEIGHT,
                 group="camera",
                 description="VGA camera cube 2.95 x 3.47 x 2.76 mm; BALL MAP PROVISIONAL (stand-in)",
                 fields=_status(PROV, "MPN, size, Digi-Key PN research-confirmed; ball map, pitch, "
                                      "pad size, PWDN / tri-state behaviour NOT known")), xy, 0.0)
        gnd += ["%s.GND1" % ref, "%s.GND2" % ref]
        d.net("V2V8_CAM", "%s.AVDD" % ref, "%s.DOVDD" % ref)
        d.net("CAM_%s_DVDD" % side, "%s.DVDD" % ref, netclass="CamPower")
        d.net("CAM_XVCLK", "%s.XVCLK" % ref)
        d.net("CAM_SDA", "%s.SIOD" % ref)
        d.net("CAM_SCL_%s" % side, "%s.SIOC" % ref)
        d.net("CAM_%s_PWDN" % side, "%s.PWDN" % ref, netclass="Fine")
        # spec: "Every camera output (D0-D7, PCLK, HREF, VSYNC) joins the shared bus through a
        # 220 ohm series resistor placed at that camera (three 4-element 0402-in-0804 arrays per
        # camera, for example Panasonic EXB-28V221JX)".  Element n: pad n (A side, camera) to
        # pad 9 - n (B side, bus).  CAM_ARRAY_MAP says which element carries which output; the
        # twelfth element of each camera is spare.
        for a, rn in enumerate(arrays):
            add(Part(rn, "4x220R", RN0804,
                     pins={"A1": "1", "A2": "2", "A3": "3", "A4": "4",
                           "B4": "5", "B3": "6", "B2": "7", "B1": "8"},
                     mpn="EXB-28V221JX", manufacturer="Panasonic", distributor="Digi-Key",
                     distributor_pn="Y7221CT-ND", height_mm=0.45, group="camera",
                     description="Resistor array 4 x 220 ohm 5 %, 0402 x 4 (0804), convex",
                     fields=_status(PROV, "MPN from DESIGN_SPEC (stock PROVISIONAL); Digi-Key PN from "
                                          "docs/sourcing.csv; height and the match of the KiCad 4x0402 "
                                          "convex land pattern not checked")))
            for e in range(1, 5):
                sig = element_of.get((a, e))
                if sig is not None:
                    d.net("CAM_%s_%s" % (side, sig), "%s.%s" % (ref, sig), "%s.A%d" % (rn, e),
                          netclass="Fine")
                    d.net("CAM_%s" % sig, "%s.B%d" % (rn, e))
                else:
                    d.no_connect("%s.A%d" % (rn, e), "%s.B%d" % (rn, e))
    for net in ("CAM_XVCLK", "CAM_SDA", "CAM_SCL_L", "CAM_SCL_R"):
        d.nets[net].netclass = "Fine"                  # they end on camera balls
    d.net("V2V8_CAM", netclass="CamPower")

    # ================================================================== power
    # spec rail table: V2V8 from MCP1700T-2802E/TT, 1 uF in, 1 uF out
    add(Part("U7", "MCP1700-2.8", SOT23,
             pins={"GND": ("1", "power_in"), "VOUT": ("2", "power_out"), "VIN": ("3", "power_in")},
             mpn="MCP1700T-2802E/TT", manufacturer="Microchip", distributor="Digi-Key",
             distributor_pn="product page 5148837 (SKU not seen)", height_mm=1.2, group="power",
             description="LDO 2.8 V 250 mA, 1.6 uA quiescent, SOT-23 (always on)",
             fields=_status(PROV, "family, pin order, Iq research-confirmed for the 3.0 V part "
                                  "(-3002); the 2.8 V order code -2802 is from DESIGN_SPEC and a "
                                  "distributor listing in docs/sourcing.csv")))
    d.net("VBAT", "U7.VIN")
    v2v8.append("U7.VOUT")
    gnd.append("U7.GND")
    # spec rail table: VDDUSB from MCP1700T-3302E/TT fed from VBUS (after the Schottky), MCU pin only
    add(Part("U11", "MCP1700-3.3", SOT23,
             pins={"GND": ("1", "power_in"), "VOUT": ("2", "power_out"), "VIN": ("3", "power_in")},
             mpn="MCP1700T-3302E/TT", manufacturer="Microchip", distributor="Digi-Key",
             distributor_pn="product page 652676 (SKU not seen)", height_mm=1.2, group="power",
             description="LDO 3.3 V 250 mA, SOT-23 (VDDUSB, present only in the cradle)",
             fields=_status(PROV, "order code -3302 from DESIGN_SPEC and docs/sourcing.csv; see U7")))
    d.net("VBUS_D", "U11.VIN")
    d.net("VDDUSB", "U11.VOUT")
    gnd.append("U11.GND")
    # spec rail table: V2V8_CAM from LP5907MFX-2.8/NOPB, EN from the MCU with 100k pull-down
    add(Part("U8", "LP5907-2.8", SOT235,
             pins={"IN": ("1", "power_in"), "GND": ("2", "power_in"), "EN": ("3", "input"),
                   "NC": ("4", "nc"), "OUT": ("5", "power_out")},
             mpn="LP5907MFX-2.8/NOPB", manufacturer="Texas Instruments", distributor="Digi-Key",
             distributor_pn="product page 3906436 (SKU not seen)", unit_price=0.65, height_mm=1.45, group="power",
             description="LDO 2.8 V 250 mA low noise with enable, SOT-23-5 (camera rail)",
             fields=_status(RES, "MPN, pin order, 1 uF stability research-confirmed; Digi-Key PN "
                                 "and output discharge behaviour not seen")))
    d.net("VBAT", "U8.IN")
    d.net("CAM_EN", "U8.EN")
    d.net("V2V8_CAM", "U8.OUT")
    gnd.append("U8.GND")
    # spec E1: "TI BQ25101YFP (4.20 V, DSBGA-6, 0.4 mm ball pitch, all six balls on the perimeter)"
    chg_pins = {pin: (ball, etype) for ball, (pin, etype) in BQ25101_BALLS.items()}
    add(Part("U9", "BQ25101", charger_footprint(), pins=chg_pins, mpn="BQ25101YFPR",
             manufacturer="Texas Instruments", distributor=BY_MPN, distributor_pn="BQ25101YFPR",
             height_mm=BQ25101_HEIGHT, group="power",
             description="Li-ion linear charger 4.20 V, 10-250 mA, TS (JEITA) and open-drain CHG, "
                         "DSBGA-6 1.6 x 0.9 mm; BALL MAP PROVISIONAL. Fallback on the footprint: BQ25100YFP",
             fields=_status(PROV, "part from DESIGN_SPEC E1; ball map, land pattern, TS thresholds and "
                                  "the order code (YFPR reel / YFPT small reel) from web-search extracts "
                                  "of TI SLUSBV8C, not the data sheet (BQ25101_BALLS)")))
    d.net("VBUS_D", "U9.IN", netclass="Power", power_flag=True)   # fed from VBUS through D17
    d.net("VBAT", "U9.OUT", netclass="Power", power_flag=True)    # also driven by the cell (BT1)
    d.net("CHG_ISET", "U9.ISET")
    d.net("CHG_TS", "U9.TS")
    d.net("CHG_STAT", "U9.CHG")
    gnd.append("U9.VSS")
    # spec E1: "CHG_INHIBIT is an MCU push-pull output to the gate of a small N-MOSFET (for example
    # onsemi BSS138, gate pulled down with 100 kohm) that pulls TS to ground"
    add(Part("Q1", "BSS138", SOT23,
             pins={"G": ("1", "input"), "S": ("2", "passive"), "D": ("3", "passive")},
             mpn="BSS138LT1G", manufacturer="onsemi", distributor="Digi-Key",
             distributor_pn="product page 918376 (SKU not seen)", height_mm=1.2, group="power",
             description="N-MOSFET 50 V, VGS(th) 1.5 V max, SOT-23 (pulls the charger's TS input low)",
             fields=_status(PROV, "part named in DESIGN_SPEC; order code from docs/sourcing.csv; pin "
                                  "order (G1 S2 D3), threshold and leakage from memory")))
    d.net("CHG_INHIBIT", "Q1.G")
    d.net("CHG_TS", "Q1.D")
    gnd.append("Q1.S")
    # spec E2: "two 10 kohm NTCs (Murata NCU15XH103F60RC, 0402, B 3380 K ...) on the top side within
    # 1 mm of the cell edge ... NTC1 goes from the charger TS ball to ground and belongs to the
    # charger alone.  NTC2 is the MCU's"
    for ref, net, role in (("RT1", "CHG_TS", "NTC1: charger TS (hardware charge-temperature window)"),
                           ("RT2", "NTC_SENSE", "NTC2: MCU (supervision, no read above 60 C, display)")):
        add(Part(ref, "NTC 10k", R0402, pins=two_pin(), mpn=NTC_MPN,
                 manufacturer="Murata", distributor=BY_MPN, distributor_pn=NTC_MPN,
                 height_mm=0.55, group="power",
                 description="NTC thermistor 10 kohm 1 %, B 3380 K, 0402 (cell temperature)",
                 fields=dict(_status(PROV, "MPN from DESIGN_SPEC E2 (stock PROVISIONAL); B value as used "
                                           "by the firmware, no R-T table read; joined to the cell with "
                                           "thermal adhesive at assembly"), Purpose=role)))
        d.net(net, "%s.1" % ref)
        gnd.append("%s.2" % ref)
    # spec: "Series Schottky from pad to charger"; E6: "30 V 0.5 A SOD-323 class part (Diodes B0530WS-7-F)"
    add(Part("D17", "B0530WS", SOD323, pins={"K": ("1", "passive"), "A": ("2", "passive")},
             mpn="B0530WS-7-F", manufacturer="Diodes Incorporated", distributor="Digi-Key",
             distributor_pn="B0530WS-FDICT-ND", unit_price=0.30, height_mm=1.1, group="power",
             description="Schottky 30 V 0.5 A SOD-323 (VBUS pad to charger)",
             fields=_status(RES, "MPN, ratings, Digi-Key PN research-confirmed; body height and "
                                 "VF at 25 mA not seen")))
    d.net("VBUS", "D17.A", netclass="Power", power_flag=True)     # from the cradle
    d.net("VBUS_D", "D17.K")
    # spec: "USBLC6-2SC6 clamps VBUS, D+, D-"
    add(Part("U10", "USBLC6-2SC6", SOT236,
             pins={"IO1A": ("1", "passive"), "GND": ("2", "power_in"), "IO2A": ("3", "passive"),
                   "IO2B": ("4", "passive"), "VBUS": ("5", "power_in"), "IO1B": ("6", "passive")},
             mpn="USBLC6-2SC6", manufacturer="STMicroelectronics", distributor="Digi-Key",
             distributor_pn="497-5235-1-ND", unit_price=0.36, height_mm=1.45, group="power",
             description="USB ESD protection, SOT-23-6",
             fields=_status(RES, "MPN, pin order (KiCad symbol), Digi-Key PN research-confirmed")))
    d.net("VBUS", "U10.VBUS")
    d.net("USB_DM", "U10.IO1A", "U10.IO1B")
    d.net("USB_DP", "U10.IO2A", "U10.IO2B")
    gnd.append("U10.GND")
    # spec: "Two solder pads for the cell leads sit in the strip beyond the protection-board end"
    bt = F.battery_tab(BAT_PAD_SIZE[0], BAT_PAD_SIZE[1])
    (bx1, by1), (bx2, by2) = battery_pad_positions()
    add(Part("BT1", "BAT+", bt, pins={"1": "1"}, in_bom=False, height_mm=0.0, group="power",
             description="cell + lead solder pad (PowerStream GM201030-PCB is not a board part)"),
        (bx1, by1))
    add(Part("BT2", "BAT-", bt, pins={"1": "1"}, in_bom=False, height_mm=0.0, group="power",
             description="cell - lead solder pad"), (bx2, by2))
    d.net("VBAT", "BT1.1")
    gnd.append("BT2.1")

    # ==================================================================== IMU
    # spec: "IMU on its own SPI bus; INT1 (latched) to a wake-capable pin, INT2 to a second GPIO"
    # SDO is a tri-state output: "bidir".  Mode 1 wiring of the unused pins: SDx / SCx to GND,
    # OCS_Aux / SDO_Aux open (docs/research: pins 10, 11 confirmed; pins 2, 3 PROVISIONAL).
    add(Part("U4", "LSM6DSV16X", LGA14,
             pins={"SDO": ("1", "bidir"), "SDX": ("2", "passive"), "SCX": ("3", "passive"),
                   "INT1": ("4", "output"), "VDDIO": ("5", "power_in"), "GND1": ("6", "power_in"),
                   "GND2": ("7", "power_in"), "VDD": ("8", "power_in"), "INT2": ("9", "output"),
                   "OCS_AUX": ("10", "nc"), "SDO_AUX": ("11", "nc"), "CS": ("12", "input"),
                   "SCL": ("13", "input"), "SDA": ("14", "input")},
             mpn="LSM6DSV16XTR", manufacturer="STMicroelectronics", distributor="Digi-Key",
             distributor_pn="497-LSM6DSV16XTRCT-ND", unit_price=4.42, height_mm=0.86,
             group="sensor", description="6-axis IMU, LGA-14L 2.5 x 3.0 x 0.83 mm",
             fields=_status(RES, "MPN, package, pin map, Digi-Key PN research-confirmed; wiring of "
                                 "pins 2 and 3 and any INT1 power-on restriction: PROVISIONAL")))
    d.net("SPI2_MISO", "U4.SDO")
    d.net("SPI2_SCK", "U4.SCL")
    d.net("SPI2_MOSI", "U4.SDA")
    d.net("IMU_CS", "U4.CS")
    d.net("IMU_INT1", "U4.INT1")
    d.net("IMU_INT2", "U4.INT2")
    v2v8 += ["U4.VDD", "U4.VDDIO"]
    gnd += ["U4.GND1", "U4.GND2", "U4.SDX", "U4.SCX"]

    # ================================================================ display
    # spec: J1 top-contact Hirose FH12A-10S-0.5SH(55) on the FH12 land pattern; EXTMODE tied high
    straight = lcd_tail_pin1_at_pad1(J1_ROTATION)
    pad_of_tail = {n: (n if straight else 11 - n) for n in LCD_TAIL}
    j1_pins = {LCD_TAIL[n]: (str(pad_of_tail[n]), "passive") for n in LCD_TAIL}
    j1_pins["MP"] = ("MP", "passive")
    add(Part("J1", "LCD FPC 10", FPC10, pins=j1_pins, mpn="FH12A-10S-0.5SH(55)",
             manufacturer="Hirose", distributor="Digi-Key",
             distributor_pn="HFK110CT-ND", height_mm=J1_HEIGHT, group="display",
             description="FPC connector 10 x 0.5 mm, TOP contact, 2.0 mm high; PIN-1 EDGE OF THE TAIL "
                         "PROVISIONAL (tail pin n on pad %s)" % ("n" if straight else "11 - n"),
             fields=_status(PROV, "top-contact FH12A on the bottom-contact FH12 land pattern "
                                  "(spec); pin order and pin-1 edge of the tail PROVISIONAL (LCD_TAIL, "
                                  "LCD_TAIL_PIN1_EDGE); the body lies 1.5 mm behind the mechanical model's "
                                  "box (open item, NETLIST_NOTES 5.1); Digi-Key PN from docs/sourcing.csv")),
        J1_XY, J1_ROTATION)
    d.net("SPI1_SCK", "J1.SCLK")
    d.net("SPI1_MOSI", "J1.SI")
    d.net("LCD_SCS", "J1.SCS")
    d.net("LCD_EXTCOMIN", "J1.EXTCOMIN")
    d.net("LCD_DISP", "J1.DISP")
    v2v8 += ["J1.VDDA", "J1.VDD", "J1.EXTMODE"]
    gnd += ["J1.VSS", "J1.VSSA", "J1.MP"]

    # ========================================================= grain sensor (underside)
    # spec E3: "red Vishay VLMS1500-GS08 (0402); near-infrared ams OSRAM SFH 4053B (0402 ...),
    # alternative Inolux IN-S42CTQIR (850 nm, 0402)"
    for ref, colour, x, y, rot, az, anode, cathode in led_positions():
        red = colour == "red"
        part = Part(ref, "LED red" if red else "LED NIR", LED0402,
                    pins={"K": ("1", "passive"), "A": ("2", "passive")},
                    mpn=LED_RED_MPN if red else LED_NIR_MPN,
                    manufacturer="Vishay" if red else "ams OSRAM", distributor=BY_MPN,
                    distributor_pn=LED_RED_MPN if red else LED_NIR_MPN,
                    side=BOTTOM, height_mm=LED_RING["led_height"], group="grain",
                    description="LED super red 631 nm 0402" if red
                    else "LED 850 nm 0402 (alternative: %s)" % LED_NIR_ALTERNATIVE,
                    fields=dict(_status(PROV, ("MPN research-confirmed" if red else
                                               "MPN from DESIGN_SPEC E3 (successor of the SFH 4053; its "
                                               "data sheet has not been read)")
                                        + "; land pattern is the generic KiCad 0402 LED, polarity mark "
                                          "and pad sizes not checked"),
                                Purpose="grain ring, azimuth %g deg, anode CP%d, cathode CP%d"
                                        % (az, anode, cathode)))
        part.place(x, y, rot)
        d.add(part)
        d.net("CP%d" % anode, "%s.A" % ref)
        d.net("CP%d" % cathode, "%s.K" % ref)
    pd_pins = {"A": (tuple(n for n, v in VEMD8080_PADS.items() if v[2] == "A"), "passive"),
               "K": (tuple(n for n, v in VEMD8080_PADS.items() if v[2] == "K"), "passive")}
    pd = Part("PD1", "VEMD8080", photodiode_footprint(), pins=pd_pins, mpn="VEMD8080",
              manufacturer="Vishay", distributor=BY_MPN, distributor_pn="VEMD8080", side=BOTTOM,
              height_mm=PD_POS["h"], group="grain",
              description="PIN photodiode 4.5 mm2, 350-1100 nm; LAND PATTERN PROVISIONAL",
              fields=_status(PROV, "package research-confirmed; pad layout and anode pad from public "
                                   "footprints, not the Vishay drawing (VEMD8080_PADS)"))
    pd.place(PD_POS["x"], PD_POS["y"], 0.0)
    d.add(pd)
    # spec: "Photodiode cathode to the op-amp inverting input".  The anode is not given: it goes
    # to GND, so the diode is reverse-biased by VBIAS and its photocurrent does not return
    # through the bias divider (see NETLIST_NOTES).
    d.net("PD_K", "PD1.K")
    gnd.append("PD1.A")

    # ================================== underside contact pads, test points, lands
    # spec: "Test and service pads on the underside: VBUS, D-, D+, GND, SWDIO, SWCLK, NRST, in that
    # order from x = -7.62 to +7.62 mm seen from above"
    row = contact_row_footprint()
    j2_names = ("VBUS", "DM", "DP", "GND", "SWDIO", "SWCLK", "NRST")
    j2 = Part("J2", "Cradle pads", row, pins={n: (str(i + 1), "passive") for i, n in enumerate(j2_names)},
              side=BOTTOM, in_bom=False, height_mm=0.0, group="service",
              description="VBUS D- D+ GND SWDIO SWCLK NRST (underside, x = -7.62 ... +7.62 seen from above)")
    j2.place(0.5 * (PAD_ROW["xs"][0] + PAD_ROW["xs"][-1]), PAD_ROW["y"], 0.0)
    d.add(j2)
    d.net("VBUS", "J2.VBUS")
    d.net("USB_DM", "J2.DM")
    d.net("USB_DP", "J2.DP")
    gnd.append("J2.GND")
    d.net("SWDIO", "J2.SWDIO")
    d.net("SWCLK", "J2.SWCLK")
    d.net("NRST", "J2.NRST")
    # spec E4: "Test points on the top side, 1.0 mm bare round pads reachable by spring probes
    # before the unit is closed: VBAT, V2V8, V2V8_CAM, GND"
    tp = F.test_pad(TEST_POINT_DIA)
    for ref, net in (("TP1", "VBAT"), ("TP2", "V2V8"), ("TP3", "V2V8_CAM"), ("TP4", "GND")):
        add(Part(ref, net, tp, pins={"1": "1"}, in_bom=False, height_mm=0.0, group="service",
                 description="test point %s (top side, bare dia %g mm pad)" % (net, TEST_POINT_DIA)))
        if net == "GND":
            gnd.append("%s.1" % ref)
        elif net == "V2V8":
            v2v8.append("%s.1" % ref)
        else:
            d.net(net, "%s.1" % ref)
    land = foot_land_footprint()
    for i, (x, y) in enumerate(FEET["positions"], start=1):
        fl = Part("FL%d" % i, "Ball-foot land", land, pins={}, side=BOTTOM, in_bom=False,
                  board_only=True, dnp=BARE_BOTTOM_COPPER_NOT_FITTED, height_mm=0.0,
                  group="board", description="unmasked copper land under ball foot %d, no net" % i)
        fl.place(x, y, 0.0)
        d.add(fl)

    d.net("GND", *gnd, netclass="Power")
    d.net("V2V8", *v2v8, netclass="Power")

    # ---- planes -------------------------------------------------------------------------------
    d.add_plane("GND", "In1.Cu")                               # spec: "Layer 2 solid ground"
    d.add_plane("V2V8", "In2.Cu", routable=True)               # layout choice of the toolchain demo
    # ---- keep-outs of the mechanical contract ------------------------------------------------
    bb = BAT["body"]
    d.add_keepout(RoundedPolygon.rect(bb["x"], bb["y"], bb["dx"], bb["dy"]), layers=("F.Cu",),
                  name="battery_body", tracks=False, vias=False, copper=False, footprints=True)
    size = KO["post_feet"]["size"]
    for i, (x, y) in enumerate(KO["post_feet"]["centres"], start=1):
        d.add_placement_keepout(RoundedPolygon.rect(x, y, size, size), side=TOP,
                                name="post_foot_%d" % i)
    size = KO["post_feet"]["locating"]["size"]
    for i, (x, y) in enumerate(KO["post_feet"]["locating"]["centres"], start=1):
        d.add_placement_keepout(RoundedPolygon.rect(x, y, size, size), side=TOP,
                                name="post_foot_locating_%d" % i)
    for i, (x, y) in enumerate(FEET["positions"], start=1):
        # top: no soldered part in the zone, free parts 0.3 mm away (part_margin)
        d.add_placement_keepout(Circle(x, y, FEET["dia"] / 2.0 + FEET["part_margin"]), side=TOP,
                                name="foot_zone_%d_top" % i)
        # bottom: no track, no via, no pour; the land (a pad without a net) is allowed
        d.add_keepout(Circle(x, y, FEET["dia"] / 2.0), layers=("B.Cu",), name="foot_zone_%d" % i,
                      tracks=True, vias=True, copper=True)
    go = VIA_KO["grain_opening"]
    d.add_keepout(Circle(go["x"], go["y"], go["dia"] / 2.0), layers=ALL_LAYERS,
                  name="grain_opening_no_via", tracks=False, vias=True, copper=False)
    ps = VIA_KO["pad_slot"]
    half = (ps["length"] - ps["width"]) / 2.0
    d.add_keepout(Slot(-half, ps["y"], half, ps["y"], ps["width"]), layers=ALL_LAYERS,
                  name="pad_slot_no_via", tracks=False, vias=True, copper=False)
    # ---- height limits --------------------------------------------------------------------------
    hood = KO["camera_hoods"]
    for ref, (cx, _cy) in (("U2", CAM_L), ("U3", CAM_R)):
        d.add_height_limit(RoundedPolygon.rect(cx, (hood["y0"] + hood["y1"]) / 2.0,
                                               2.0 * hood["half_w"], hood["y1"] - hood["y0"]),
                           hood["max_part_height"], side=TOP, exempt=(ref,),
                           name="camera_hood_%s" % ref)
    tail = KO["lcd_tail"]
    d.add_height_limit(RoundedPolygon.rect(0.0, (tail["y"][0] + tail["y"][1]) / 2.0,
                                           2.0 * tail["half_w"], tail["y"][1] - tail["y"][0]),
                       tail["max_part_height"], side=TOP, exempt=("J1",), name="lcd_tail")
    d.add_height_limit(RoundedPolygon.rect(0.0, 0.0, 2.2 * BOARD_RADIUS, 2.2 * BOARD_RADIUS),
                       FREE_HEIGHT, side=TOP, exempt=("U2", "U3"), name="free_height")
    # ---- no copper on F.Cu under the IMU body (spec) -------------------------------------------
    # "No copper pours or vias under the IMU body on the top layer".  add_body_keepout forbids
    # tracks, vias and pours in the pad-free rectangle under the body; a through via between the
    # pads of the LGA would still put its pad on the top layer under the body, so a second rule
    # area forbids vias (only vias) under the whole body outline.
    if d.part("U4").placed:
        d.add_body_keepout("U4")
        u4 = d.part("U4")
        bw, bh = (3.0, 2.5) if abs(u4.rotation % 180.0) < 1e-9 else (2.5, 3.0)     # LGA-14 body
        d.add_keepout(RoundedPolygon.rect(u4.x, u4.y, bw, bh), layers=ALL_LAYERS,
                      name="under_U4_no_via", tracks=False, vias=True, copper=False)
    # ---- fine areas: the fine classes are fine only round the cameras --------------------------
    d.add_fine_area("U2", margin=5.0)
    d.add_fine_area("U3", margin=5.0)
    # ---- fiducials: three per side -------------------------------------------------------------
    for x, y in FIDUCIALS_TOP:
        d.add_fiducial(x, y)
    for x, y in FIDUCIALS_BOTTOM:
        d.add_fiducial(x, y, side=BOTTOM).dnp = BARE_BOTTOM_COPPER_NOT_FITTED
    # ---- per-net router options (layout) -------------------------------------------------------
    for net_name, options in NET_ROUTING.items():
        d.net(net_name, **options)
    return d


def pinmap_rows():
    """PINMAP as a list of dicts, with the LQFP-64 pad of every row."""
    rows = []
    for row in PINMAP:
        r = dict(zip(PINMAP_FIELDS, row))
        r["pad"] = mcu_pad_of(r["pin"])
        rows.append(r)
    return rows


if __name__ == "__main__":
    from gleda import checks
    design = gl1_main_design()
    print(design)
    print(checks.run_checks(design).text())
