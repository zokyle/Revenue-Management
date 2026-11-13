#!/usr/bin/python3
"""GreenLine GL-1 main board - netlist as code (gleda 0.4.0).

STAGE: NETLIST.  Nothing has been built, nothing is routed.  This file holds
every part, net, net class, footprint, the MCU pin map and the mechanical
contract of the board (outline, locating features, keep-outs, height limits)
so that the toolchain's checks and its schematic generator can run.  The part
positions in ``PLACEMENT`` are NOMINAL: legal (the checks pass) and roughly
where each part belongs, nothing more.  The layout step owns them.

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
* PROVISIONAL - from engineering memory or an unconfirmed extract.  Must be
  checked against the datasheet / drawing before boards are ordered.

The three PROVISIONAL items that can mirror or scramble a whole part are
isolated in one table each: ``OVM7692_BALLS``, ``LCD_TAIL`` (+
``LCD_TAIL_PIN1_AT_PAD1``) and ``VEMD8080_PADS``.

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
                         two_pin, n_pin, US_4L_STD, BOTTOM, TOP, ALL_LAYERS)
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
J1_XY = (_J1["x"], _J1["y"])                         # footprint ANCHOR (mechanical/cad/board_import.py compares the anchor)
J1_HEIGHT = _J1["h"]
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
#: 25th ball are "nc" here.  Replace this table and OVM7692_FOOTPRINT from the
#: registered OmniVision datasheet; nothing else in the netlist changes.
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

#: PROVISIONAL.  LCD tail pin order of the Sharp LS013B7DH03 (spec section 4:
#: "from the Sharp datasheet as remembered and consistent with public drivers";
#: docs/research/bom-verification-opto.md marks the order "confirmed" from a
#: search extract of Sharp's terminal table).  tail pin -> function.
LCD_TAIL = {1: "SCLK", 2: "SI", 3: "SCS", 4: "EXTCOMIN", 5: "DISP",
            6: "VDDA", 7: "VDD", 8: "EXTMODE", 9: "VSS", 10: "VSSA"}
#: PROVISIONAL.  True: tail pin n meets connector pad n (pad 1 at x = -2.25 mm
#: of J1, the KiCad FH12 land pattern).  False: the tail is mirrored, tail pin n
#: meets pad 11 - n.  Which one is right depends on the U-fold and on the Sharp
#: tail drawing (release gate B16); a wrong guess mirrors all ten pins.
LCD_TAIL_PIN1_AT_PAD1 = True

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
#: 49-64 on the right edge (49 at the bottom).  Reason for 270: the KiCad
#: courtyard of the LQFP-64 is 13.4 mm square, so NOTHING fits between the MCU
#: and the battery (1.4 mm).  The package edge that faces the battery must be
#: the one without decoupling work: pads 33-48 (only VSS / VDDUSB at its end).
#: Pads 17-32 (VDD, VCAP, VDD) and 49-64 (VDD) then face free board on the left
#: and right, pads 1-16 (VBAT, crystal, VDDA) the strip toward the cameras.
U1_ROTATION = 270.0

S, P, C = "SPEC", "PROPOSED", "CHANGED"
#: The pin map.  One row per signal:
#:   signal, port pin, net, mode, function, AF, pull, initial state, source, was, reason
#: mode: AF (alternate function, number in AF) | ANALOG | OUT_PP | OUT_OD | IN |
#:       EXTI (input with interrupt) | SCCB_OD (bit-banged open-drain) | STRAP
#: pull: what the firmware sets ("none" unless stated) / what the board fits
#: initial state: what gl_hal_init() must establish before anything else
#: source: SPEC (fixed by DESIGN_SPEC section 4), PROPOSED (same pin as
#:   gl_pins.h), CHANGED (moved from the pin in ``was``; ``reason`` says why)
PINMAP = [
    # ---- camera port: fixed by the DCMI alternate functions (spec, PINDATA) --------------
    ("CAM_D0", "PC6", "CAM_D0", "AF", "DCMI_D0", 10, "none", "low or analog while V2V8_CAM is off", S, None, ""),
    ("CAM_D1", "PC7", "CAM_D1", "AF", "DCMI_D1", 10, "none", "low or analog while V2V8_CAM is off", S, None, ""),
    ("CAM_D2", "PC8", "CAM_D2", "AF", "DCMI_D2", 10, "none", "low or analog while V2V8_CAM is off", S, None, ""),
    ("CAM_D3", "PC9", "CAM_D3", "AF", "DCMI_D3", 4, "none", "low or analog while V2V8_CAM is off", S, None, ""),
    ("CAM_D4", "PC11", "CAM_D4", "AF", "DCMI_D4", 10, "none", "low or analog while V2V8_CAM is off", S, None, ""),
    ("CAM_D5", "PB6", "CAM_D5", "AF", "DCMI_D5", 10, "none", "low or analog while V2V8_CAM is off", S, None, ""),
    ("CAM_D6", "PB8", "CAM_D6", "AF", "DCMI_D6", 10, "none", "low or analog while V2V8_CAM is off", S, None, ""),
    ("CAM_D7", "PB9", "CAM_D7", "AF", "DCMI_D7", 10, "none", "low or analog while V2V8_CAM is off", S, None, ""),
    ("CAM_PIXCLK", "PA6", "CAM_PCLK", "AF", "DCMI_PIXCLK", 4, "none", "low or analog while V2V8_CAM is off", S, None, ""),
    ("CAM_HREF", "PA4", "CAM_HREF", "AF", "DCMI_HSYNC", 10, "none", "low or analog while V2V8_CAM is off", S, None, ""),
    ("CAM_VSYNC", "PB7", "CAM_VSYNC", "AF", "DCMI_VSYNC", 10, "none", "low or analog while V2V8_CAM is off", S, None, ""),
    ("CAM_XVCLK", "PA8", "MCO", "AF", "RCC_MCO", 0, "none", "low or analog while V2V8_CAM is off", S, None, ""),
    # ---- camera control: on the package edge that faces the cameras (pads 1-16) ----------
    ("CAM_L_SCL", "PC3", "CAM_SCL_L", "SCCB_OD", "GPIO", None, "none / 2k2 to V2V8_CAM", "driven low while V2V8_CAM is off", C, "PB3",
     "PB3 is needed for SPI1_SCK next to the flash; PC3 faces the cameras"),
    ("CAM_L_PWDN", "PC2", "CAM_L_PWDN_MCU", "OUT_PP", "GPIO", None, "none / 1k series", "driven low while V2V8_CAM is off", C, "PH0",
     "PC2 is on the left half of the camera-facing edge; PH0 goes to the right camera"),
    ("CAM_SCCB_SDA", "PC1", "CAM_SDA", "SCCB_OD", "GPIO", None, "none / 2k2 to V2V8_CAM", "driven low while V2V8_CAM is off", C, "PB5",
     "PB5 is needed for SPI1_MOSI next to the flash; PC1 faces the cameras"),
    ("CAM_R_SCL", "PC0", "CAM_SCL_R", "SCCB_OD", "GPIO", None, "none / 2k2 to V2V8_CAM", "driven low while V2V8_CAM is off", C, "PA10",
     "PA10 is on the battery-facing edge; PC0 faces the cameras, PA10 takes FLASH_CS"),
    ("CAM_R_PWDN", "PH0", "CAM_R_PWDN_MCU", "OUT_PP", "GPIO", None, "none / 1k series", "driven low while V2V8_CAM is off", C, "PC12",
     "camera-facing edge, right half; a quasi-static signal is the right neighbour for OSC32_OUT (pad 4)"),
    ("CAM_PWR_EN", "PH3", "CAM_EN", "OUT_PP", "GPIO", None, "none / 100k + 10k (BOOT0) to GND", "low (rail off)", C, "PD2",
     "takes the BOOT0 pad instead of NTC_BIAS: the 10k BOOT0 pull-down would load the ratiometric NTC bias "
     "(0.28 mA extra through the pin's on-resistance, about 0.5 K error at 0 C); a rail enable does not care"),
    # ---- LCD (J1): pads 27-29 face the left side of the board, the way down to J1 --------
    ("LCD_SCS", "PB10", "LCD_SCS", "OUT_PP", "GPIO", None, "none / 100k to GND", "low (not selected)", P, None, ""),
    ("LCD_DISP", "PB1", "LCD_DISP", "OUT_PP", "GPIO", None, "none / 100k to GND", "low (display off)", P, None, ""),
    ("LCD_EXTCOMIN", "PB2", "LCD_EXTCOMIN", "AF", "LPTIM1_CH1", 1, "none", "low until LPTIM1 runs", S, None, ""),
    # ---- SPI1: flash and LCD.  MISO is fixed on PB4, so clock and data sit on its neighbours
    ("SPI1_SCK", "PB3", "SPI1_SCK", "AF", "SPI1_SCK", 5, "none", "low", C, "PA5",
     "PB3 / PB4 / PB5 are three adjacent pads on the edge that faces the flash; PA5 is on the opposite edge"),
    ("SPI1_MISO", "PB4", "SPI1_MISO", "AF", "SPI1_MISO", 5, "none", "input", S, None, ""),
    ("SPI1_MOSI", "PB5", "SPI1_MOSI", "AF", "SPI1_MOSI", 5, "none", "low", C, "PA7",
     "see SPI1_SCK"),
    ("FLASH_CS", "PA10", "FLASH_CS", "OUT_PP", "GPIO", None, "none / 100k to V2V8", "high (not selected)", C, "PA15",
     "PA10 is the ROM bootloader's USART1_RX: the chip-select pull-up keeps it at idle-high during the "
     "detection phase; PA15 goes to the grain LEDs"),
    # ---- IMU on SPI2: pads 33-36 at the corner next to the IMU ---------------------------
    ("SPI2_SCK", "PB13", "SPI2_SCK", "AF", "SPI2_SCK", 5, "none", "low", P, None, ""),
    ("SPI2_MOSI", "PB15", "SPI2_MOSI", "AF", "SPI2_MOSI", 5, "none", "low", P, None, ""),
    ("SPI2_MISO", "PB14", "SPI2_MISO", "AF", "SPI2_MISO", 5, "none", "input", P, None, ""),
    ("IMU_CS", "PB12", "IMU_CS", "OUT_PP", "GPIO", None, "none / 100k to V2V8", "high (not selected)", P, None, ""),
    ("IMU_INT1", "PC5", "IMU_INT1", "EXTI", "GPIO (PWR_WKUP5)", None, "none", "input", C, "PC13",
     "PC5 faces the IMU and is a wake-up pin (WKUP5); PC13 is on the far corner next to the crystal"),
    ("IMU_INT2", "PA7", "IMU_INT2", "EXTI", "GPIO", None, "none", "input", C, "PC5",
     "PC5 is taken by IMU_INT1; PA7 is on the same edge (and is WKUP8)"),
    # ---- grain sensor ----------------------------------------------------------------------
    ("GRAIN_CP0", "PA9", "CP0_MCU", "OUT_PP", "GPIO", None, "none / 68R series", "analog (no LED lit)", C, "PC0",
     "PC0-PC3 face the cameras and carry SCCB / PWDN now; PA9, PA15, PC10, PC12, PD2 are the corner next to the LED ring"),
    ("GRAIN_CP1", "PA15", "CP1_MCU", "OUT_PP", "GPIO", None, "none / 68R series", "analog (no LED lit)", C, "PC1", "see GRAIN_CP0"),
    ("GRAIN_CP2", "PC12", "CP2_MCU", "OUT_PP", "GPIO", None, "none / 68R series", "analog (no LED lit)", C, "PC2", "see GRAIN_CP0"),
    ("GRAIN_CP3", "PD2", "CP3_MCU", "OUT_PP", "GPIO", None, "none / 68R series", "analog (no LED lit)", C, "PC3", "see GRAIN_CP0"),
    ("GRAIN_CP4", "PC10", "CP4_MCU", "OUT_PP", "GPIO", None, "none / 68R series", "analog (no LED lit)", P, None, ""),
    ("OPAMP_VINP", "PA0", "VBIAS", "ANALOG", "OPAMP1_VINP", None, "none", "analog", S, None, ""),
    ("OPAMP_VINM", "PA1", "PD_K", "ANALOG", "OPAMP1_VINM", None, "none", "analog", S, None, ""),
    ("OPAMP_VOUT", "PA3", "OPAMP_OUT", "ANALOG", "OPAMP1_VOUT / ADC1_IN8", None, "none / 1M to V2V8", "analog", S, None, ""),
    # ---- power supervision -------------------------------------------------------------------
    ("VBAT_SENSE", "PA2", "VBAT_SENSE", "ANALOG", "ADC1_IN7", None, "none", "analog", P, None, ""),
    ("CHG_STAT", "PB0", "CHG_STAT", "EXTI", "GPIO", None, "none / 100k to VDDUSB, 470k to GND", "input", P, None, ""),
    ("CHG_INHIBIT", "PH1", "CHG_INHIBIT", "OUT_OD", "GPIO", None, "none / 1M to VBUS_D, 1M to GND", "released (analog): charger on", P, None, ""),
    ("VBUS_SENSE", "PC13", "VBUS_SENSE", "EXTI", "GPIO (PWR_WKUP2)", None, "none / divider 82k : 100k", "input", C, "PA9",
     "PA9 goes to the grain LEDs; PC13 is a wake-up pin (cradle insertion can wake from Shutdown) and a "
     "static signal is the right neighbour for OSC32_IN (pad 3); PC13 may only sink 3 mA: it is an input here"),
    ("NTC_BIAS", "PA5", "NTC_BIAS", "OUT_PP", "GPIO", None, "none",
     "analog; high only during an NTC conversion or a grain measurement (it also feeds the grain bias divider R29)",
     C, "PH3",
     "PH3 carries the 10k BOOT0 pull-down, which would load the bias (see CAM_PWR_EN); PA5 is two pads from NTC_SENSE"),
    ("NTC_SENSE", "PC4", "NTC_SENSE", "ANALOG", "ADC1_IN13", None, "none", "analog", P, None, ""),
    # ---- fixed service pins ---------------------------------------------------------------------
    ("USB_DM", "PA11", "USB_DM", "AF", "USB_OTG_FS_DM", 10, "none", "analog until USB starts", S, None, ""),
    ("USB_DP", "PA12", "USB_DP", "AF", "USB_OTG_FS_DP", 10, "none", "analog until USB starts", S, None, ""),
    ("SWDIO", "PA13", "SWDIO", "AF", "DEBUG_JTMS-SWDIO", 0, "reset state (pull-up)", "reset state", S, None, ""),
    ("SWCLK", "PA14", "SWCLK", "AF", "DEBUG_JTCK-SWCLK", 0, "reset state (pull-down)", "reset state", S, None, ""),
    ("OSC32_IN", "PC14", "OSC32_IN", "ANALOG", "RCC_OSC32_IN", None, "none", "LSE", S, None, ""),
    ("OSC32_OUT", "PC15", "OSC32_OUT", "ANALOG", "RCC_OSC32_OUT", None, "none", "LSE", S, None, ""),
    ("BOOT0", "PH3", "CAM_EN", "STRAP", "BOOT0", None, "10k to GND", "low at reset", S, None, ""),
]
PINMAP_FIELDS = ("signal", "pin", "net", "mode", "function", "af", "pull", "initial_state",
                 "source", "was", "reason")

#: the one pad that carries two rows of PINMAP on purpose (strap + GPIO)
SHARED_PINS = {"PH3": ("BOOT0", "CAM_PWR_EN")}

#: charlieplex lines of the 16 grain LEDs.  Pair k sits at azimuth
#: first_azimuth + k * step of the YAML ring; (i, j) with i < j are the two
#: lines of the pair.  RED: anode on line i (the lower index), cathode on j.
#: NIR: anode on j, cathode on i (antiparallel).  With "red always from the
#: lower to the higher line" no chain of two NIR LEDs lies in parallel with a
#: lit red LED (two NIR junctions in series would conduct microamps at the
#: 1.85 V of a red LED and NIR light weighs heavily in the photodiode).
#: The order round the ring groups pairs that share their inner pad net.
GRAIN_PAIRS = [(3, 4), (0, 4), (2, 4), (2, 3), (1, 3), (1, 2), (0, 2), (0, 1)]

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
#: catalogue: PROVISIONAL (MPN, stock and height not checked).
CAPS = {
    "100n": ("GRM155R71C104KA88D", "100 nF 16 V X7R"),
    "10n": ("GRM155R71H103KA88D", "10 nF 50 V X7R"),
    "1u": ("GRM155R61A105KE15D", "1 uF 10 V X5R"),
    "4u7": ("GRM155R60J475ME47D", "4.7 uF 6.3 V X5R"),
    "4u7/10V": ("GRM155R61A475MEAAD", "4.7 uF 10 V X5R (on the 5 V node)"),
    "6p8": ("GRM1555C1H6R8CA01D", "6.8 pF 50 V C0G +-0.25 pF"),
    "10p": ("GRM1555C1H100JA01D", "10 pF 50 V C0G 5 %"),
}
#: value -> MPN (Yageo RC0402, 1 %).  From memory: PROVISIONAL.
RESISTORS = {
    "10R": "RC0402FR-0710RL", "33R": "RC0402FR-0733RL", "68R": "RC0402FR-0768RL",
    "1k": "RC0402FR-071KL", "2k2": "RC0402FR-072K2L", "10k": "RC0402FR-0710KL",
    "49k9": "RC0402FR-0749K9L", "82k": "RC0402FR-0782KL", "100k": "RC0402FR-07100KL",
    "470k": "RC0402FR-07470KL",
    "1M": "RC0402FR-071ML",
}


def _status(status, note=""):
    return {"Status": status, "StatusNote": note} if note else {"Status": status}


def _cap(ref, value, group, purpose):
    mpn, text = CAPS[value]
    return Part(ref, value.split("/")[0], C0402, pins=two_pin(), mpn=mpn, manufacturer="Murata",
                distributor=BY_MPN, distributor_pn=mpn, height_mm=0.55, group=group,
                description="MLCC 0402 %s" % text,
                fields=dict(_status(PROV, "MPN from memory; value per DESIGN_SPEC / NETLIST_NOTES"),
                            Purpose=purpose))


def _res(ref, value, group, purpose):
    mpn = RESISTORS[value]
    return Part(ref, value, R0402, pins=two_pin(), mpn=mpn, manufacturer="Yageo",
                distributor=BY_MPN, distributor_pn=mpn, height_mm=0.40, group=group,
                description="Resistor 0402 1 %% %s" % value,
                fields=dict(_status(PROV, "MPN from memory; value per DESIGN_SPEC / NETLIST_NOTES"),
                            Purpose=purpose))


# ---------------------------------------------------------------------------
# 5. Footprints that are not in the KiCad library
# ---------------------------------------------------------------------------
def camera_footprint():
    """PROVISIONAL 25-ball land pattern of the OVM7692 cube (see OVM7692_BALLS).
    Escape arithmetic: pitch 0.50 - pad 0.20 = 0.30 = one 0.10 mm track + two
    0.10 mm clearances; the pads carry a 0.10 mm clearance override so that the
    fine geometry stays at the package."""
    return F.bga("OVM7692_BGA25_P0.5_PROVISIONAL", 5, 5, pitch=OVM7692_PITCH, pad_d=OVM7692_PAD_D,
                 body=CAM_BODY, height=CAM_HEIGHT, pad_clearance=0.10, courtyard_margin=0.2,
                 description="PROVISIONAL stand-in land pattern, OVM7692-RYAA cube 3.47 x 2.95 x 2.76 mm")


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
PLACEMENT = {
    "U1": (0.0, 6.7, U1_ROTATION),
    "U6": (11.50, 6.40, 0.0), "U4": (-10.80, 4.00, 0.0), "U8": (-10.90, 9.60, 0.0),
    "Y1": (9.75, 10.40, 0.0), "U9": (-8.90, -12.15, 0.0), "U10": (-13.10, -12.15, 0.0),
    "U7": (8.70, -12.15, 0.0), "U11": (13.45, -12.30, 0.0), "Q1": (-16.90, 4.60, 0.0),
    "D17": (-9.30, -15.00, 0.0), "D18": (-9.20, -17.00, 0.0), "RN1": (-6.40, 15.40, 0.0),
    "RN2": (-9.00, 12.80, 90.0), "RN3": (-11.60, 12.80, 90.0), "RN4": (6.40, 15.40, 0.0),
    "RN5": (9.00, 12.80, 90.0), "RN6": (11.60, 12.80, 90.0), "C6": (-7.25, 3.95, 90.0),
    "C2": (-7.25, 1.95, 90.0), "C1": (-7.25, 9.45, 90.0), "C12": (7.20, 11.85, 90.0),
    "C3": (7.25, 8.25, 90.0), "C4": (2.80, 14.40, 90.0), "C7": (-2.80, 14.40, 90.0),
    "C8": (-2.40, 16.00, 0.0), "R1": (-4.40, 16.00, 0.0), "C9": (7.25, 1.00, 90.0),
    "C5": (-8.30, 3.00, 90.0), "C11": (12.30, 10.40, 90.0), "C10": (2.40, 16.00, 0.0),
    "R8": (4.40, 16.00, 0.0), "R2": (7.25, 6.35, 90.0), "R3": (7.25, 4.40, 90.0),
    "R9": (8.30, 1.00, 90.0), "C13": (15.35, 8.30, 90.0), "C14": (-7.20, 12.15, 90.0),
    "C15": (-12.50, 15.00, 90.0), "C16": (-13.40, 12.95, 90.0), "R6": (-14.40, 12.95, 90.0),
    "R4": (-15.95, 12.15, 90.0), "C18": (6.20, 12.15, 90.0), "C17": (12.50, 15.00, 90.0),
    "C19": (13.40, 12.95, 90.0), "R7": (14.40, 12.95, 90.0), "R5": (15.95, 12.15, 90.0),
    "C25": (-8.30, 10.40, 90.0), "C24": (-13.50, 8.60, 90.0), "R28": (-6.20, 11.85, 90.0),
    "C33": (-8.30, 8.40, 90.0), "C29": (-5.95, 13.60, 0.0), "C30": (-9.75, 1.75, 0.0),
    "C31": (-11.70, 1.75, 0.0), "RT1": (-9.40, 0.40, 0.0), "R19": (-11.40, 0.40, 0.0),
    "R21": (-7.25, 6.70, 90.0), "R22": (-8.30, 6.50, 90.0), "R31": (-9.35, 6.70, 90.0),
    "R20": (-10.40, 6.70, 90.0), "R10": (-11.45, 6.70, 90.0), "R29": (-12.50, 6.70, 90.0),
    "R30": (-13.55, 6.65, 90.0), "C34": (-14.55, 7.30, 90.0), "R12": (-16.05, 6.90, 0.0),
    "R13": (-18.00, 6.90, 0.0), "R17": (-16.05, 7.90, 0.0), "R18": (-18.00, 7.90, 0.0),
    "R23": (9.40, 2.90, 0.0), "R24": (11.40, 2.90, 0.0), "R25": (13.40, 2.90, 0.0),
    "R26": (10.40, 1.90, 0.0), "R27": (12.40, 1.90, 0.0), "R11": (-6.20, -11.50, 90.0),
    "C26": (-6.20, -13.45, 90.0), "R14": (-6.20, -15.40, 90.0), "C27": (-12.60, -14.60, 0.0),
    "C28": (-12.60, -15.60, 0.0), "C32": (6.15, -11.50, 90.0), "C21": (6.15, -13.45, 90.0),
    "R15": (6.15, -15.40, 90.0), "C20": (9.30, -14.60, 0.0), "C23": (12.30, -14.75, 0.0),
    "C22": (15.90, -12.20, 90.0), "R16": (17.60, -1.40, 90.0), "R32": (-16.05, 8.90, 0.0),
}


def led_positions():
    """[(ref, colour, x, y, rotation, azimuth, anode line, cathode line)] of the
    16 grain LEDs.  Pair k: D(2k+1) red, D(2k+2) NIR, both lying along the
    radius (the mechanical model's orientation), 1.0 mm apart along the tangent.
    Bottom side: pad 1 (K) of a KiCad 0402 LED lies toward -x of the footprint,
    so rotation = azimuth puts the cathode on the inner pad; the NIR LED is
    turned by 180 degrees.  Both inner pads of a pair are then the higher line,
    both outer pads the lower line."""
    cx, cy, r = LED_RING["x"], LED_RING["y"], LED_RING["radius"]
    out = []
    for k, (i, j) in enumerate(GRAIN_PAIRS):
        az = LED_RING["first_azimuth_deg"] + LED_RING["step_deg"] * k
        a = math.radians(az)
        for n, (colour, off) in enumerate((("red", -LED_PAIR_PITCH / 2.0),
                                           ("NIR", LED_PAIR_PITCH / 2.0))):
            x = cx + r * math.cos(a) - off * math.sin(a)
            y = cy + r * math.sin(a) + off * math.cos(a)
            rot = az % 360.0 if colour == "red" else (az + 180.0) % 360.0
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

FIDUCIALS_TOP = [(-19.0, 0.9), (18.6, -5.5), (17.3, 8.6)]
FIDUCIALS_BOTTOM = [(-13.5, -3.0), (14.0, -7.0), (0.0, 11.0)]

#: Bare copper on the underside outside the two openings (the three ball-foot
#: lands and the three bottom fiducials) is flagged "not fitted".  Nothing is
#: placed on it, the copper is on the board all the same.  Reason for the flag:
#: mechanical/cad/board_import.py (check D) treats every fitted bottom-side
#: component of the mechanical JSON as a body that must lie inside the grain
#: opening or the pad slot, and the toolchain lists copper-only footprints as
#: components.  Set to False to see those six rows fail in board_import.
BARE_BOTTOM_COPPER_NOT_FITTED = True


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
               title="GreenLine GL-1 main board (netlist stage, nothing routed)",
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
        ("C6", "4u7", "VCAP", "GND", "mcu", "U1 VCAP pad 30 (internal regulator; value PROVISIONAL)"),
        ("C7", "1u", "VDDA", "GND", "mcu", "U1 VDDA pad 13"),
        ("C8", "10n", "VDDA", "GND", "mcu", "U1 VDDA pad 13"),
        ("R1", "10R", "V2V8", "VDDA", "mcu", "VDDA filter"),
        ("C9", "100n", "VDDUSB", "GND", "mcu", "U1 VDDUSB pad 48"),
        # spec: "BOOT0 (PH3) pulled down with 10 kohm; NRST with 100 nF"
        ("C10", "100n", "NRST", "GND", "mcu", "NRST"),
        ("R2", "10k", "CAM_EN", "GND", "mcu", "BOOT0 (PH3) pull-down; the pad also drives CAM_EN"),
        # spec: "32.768 kHz crystal ... (6 pF load) with load capacitors sized for 6 pF"
        ("C11", "6p8", "OSC32_IN", "GND", "mcu", "crystal load (2 x (6.0 - 2.5 pF stray) = 7 pF)"),
        ("C12", "6p8", "OSC32_OUT", "GND", "mcu", "crystal load"),
        # flash
        ("C13", "100n", "V2V8", "GND", "mcu", "U6 VCC"),
        # spec: "100 kohm pull-ups to V2V8 on the flash and IMU chip selects"
        ("R3", "100k", "FLASH_CS", "V2V8", "mcu", "flash chip select high during reset"),
        # ---- cameras: spec rail table + rules 1 and 2 ------------------------------------
        ("C14", "100n", "V2V8_CAM", "GND", "camera", "U2 AVDD"),
        ("C15", "100n", "V2V8_CAM", "GND", "camera", "U2 DOVDD"),
        ("C16", "1u", "CAM_L_DVDD", "GND", "camera", "U2 DVDD (internal 1.5 V regulator)"),
        ("C17", "100n", "V2V8_CAM", "GND", "camera", "U3 AVDD"),
        ("C18", "100n", "V2V8_CAM", "GND", "camera", "U3 DOVDD"),
        ("C19", "1u", "CAM_R_DVDD", "GND", "camera", "U3 DVDD (internal 1.5 V regulator)"),
        ("R4", "1k", "CAM_L_PWDN_MCU", "CAM_L_PWDN", "camera", "PWDN series, left camera"),
        ("R5", "1k", "CAM_R_PWDN_MCU", "CAM_R_PWDN", "camera", "PWDN series, right camera"),
        ("R6", "2k2", "CAM_SCL_L", "V2V8_CAM", "camera", "SCCB clock pull-up, left camera"),
        ("R7", "2k2", "CAM_SCL_R", "V2V8_CAM", "camera", "SCCB clock pull-up, right camera"),
        ("R8", "2k2", "CAM_SDA", "V2V8_CAM", "camera", "SCCB data pull-up (shared)"),
        ("R9", "33R", "MCO", "CAM_XVCLK", "camera", "XVCLK series at the MCU"),
        # ---- power -------------------------------------------------------------------------
        ("C20", "1u", "VBAT", "GND", "power", "U7 input"),
        ("C21", "1u", "V2V8", "GND", "power", "U7 output"),
        ("C22", "1u", "VBUS_D", "GND", "power", "U11 input"),
        ("C23", "1u", "VDDUSB", "GND", "power", "U11 output"),
        ("C24", "1u", "VBAT", "GND", "power", "U8 input"),
        ("C25", "1u", "V2V8_CAM", "GND", "power", "U8 output"),
        ("R10", "100k", "CAM_EN", "GND", "power", "U8 EN pull-down"),
        ("C26", "4u7/10V", "VBUS_D", "GND", "power", "U9 VDD"),
        ("C27", "4u7", "VBAT", "GND", "power", "U9 VBAT"),
        # spec: "PROG resistor 49.9 kohm (20 mA), taken to ground through a low-threshold N-MOSFET"
        ("R11", "49k9", "CHG_PROG", "CHG_PROG_SW", "power", "charge current 20 mA"),
        ("R12", "1M", "VBUS_D", "CHG_INHIBIT", "power", "gate divider, top: charger on by default"),
        ("R13", "1M", "CHG_INHIBIT", "GND", "power", "gate divider, bottom"),
        # spec: "STAT to an MCU input with a 100 kohm pull-up to V2V8".  DEVIATION: the pull-up goes
        # to VDDUSB (3.3 V, present only with VBUS) and R32 divides it to 2.72 V - a pull-up from the
        # always-on rail could leak through the unpowered charger's STAT pin (see NETLIST_NOTES)
        ("R14", "100k", "CHG_STAT", "VDDUSB", "power", "STAT pull-up, to the cradle-only 3.3 V"),
        ("R32", "470k", "CHG_STAT", "GND", "power", "STAT high level 3.3 V x 470 / 570 = 2.72 V - ADDED"),
        ("C28", "100n", "VBUS", "GND", "power", "U10 VBUS (pad side of the Schottky) - ADDED, see notes"),
        ("R15", "82k", "VBUS_D", "VBUS_SENSE", "power", "VBUS sense divider, top (0.549 x VBUS_D)"),
        ("R16", "100k", "VBUS_SENSE", "GND", "power", "VBUS sense divider, bottom"),
        # spec: "2 x 1 Mohm divider with 100 nF to an ADC pin"
        ("R17", "1M", "VBAT", "VBAT_SENSE", "power", "battery divider, top"),
        ("R18", "1M", "VBAT_SENSE", "GND", "power", "battery divider, bottom"),
        ("C29", "100n", "VBAT_SENSE", "GND", "power", "battery divider reservoir at the ADC pin"),
        # spec: "divider with 10.0 kohm 1 % from a GPIO (NTC_BIAS ...) to an ADC pin (NTC_SENSE)"
        ("R19", "10k", "NTC_BIAS", "NTC_SENSE", "power", "cell NTC divider, 10.0 kohm 1 %"),
        # ---- IMU ----------------------------------------------------------------------------
        ("C30", "100n", "V2V8", "GND", "sensor", "U4 VDD"),
        ("C31", "100n", "V2V8", "GND", "sensor", "U4 VDDIO"),
        ("R20", "100k", "IMU_CS", "V2V8", "sensor", "IMU chip select high during reset"),
        # ---- display -------------------------------------------------------------------------
        ("C32", "1u", "V2V8", "GND", "display", "LCD VDD / VDDA at J1 - ADDED, see notes"),
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
        # the top of the divider is the NTC_BIAS pin (PA5), not V2V8: from the always-on rail the
        # divider would draw 14 uA for ever; the firmware drives PA5 high while the grain sensor measures
        ("R29", "100k", "NTC_BIAS", "VBIAS", "grain", "mid-rail bias divider, top (fed from PA5)"),
        ("R30", "100k", "VBIAS", "GND", "grain", "mid-rail bias divider, bottom"),
        ("C34", "100n", "VBIAS", "GND", "grain", "bias decoupling"),
        ("R31", "1M", "OPAMP_OUT", "V2V8", "grain", "known level on PA3 (bootloader USART2_RX) while "
                                                    "OPAMP1 is off - ADDED, see notes"),
    ]
    for ref, value, net1, net2, group, purpose in passives:
        add((_cap if ref.startswith("C") else _res)(ref, value, group, purpose))
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
    v2v8 += ["U6.VCC", "U6.WP", "U6.HOLD"]             # single-bit SPI only: WP# and HOLD# tied high
    gnd.append("U6.GND")

    # ================================================================ cameras
    cam_fp = camera_footprint()
    cam_pins = {pin: (ball, etype) for ball, (pin, etype) in OVM7692_BALLS.items()}
    bus = ["D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "PCLK", "HREF", "VSYNC"]
    for ref, side, xy, arrays in (("U2", "L", CAM_L, ("RN1", "RN2", "RN3")),
                                  ("U3", "R", CAM_R, ("RN4", "RN5", "RN6"))):
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
        # pad 9 - n (B side, bus).  The twelfth element of each camera is spare.
        for a, rn in enumerate(arrays):
            add(Part(rn, "4x220R", RN0804,
                     pins={"A1": "1", "A2": "2", "A3": "3", "A4": "4",
                           "B4": "5", "B3": "6", "B2": "7", "B1": "8"},
                     mpn="EXB-28V221JX", manufacturer="Panasonic", distributor=BY_MPN,
                     distributor_pn="EXB-28V221JX", height_mm=0.45, group="camera",
                     description="Resistor array 4 x 220 ohm 5 %, 0402 x 4 (0804), convex",
                     fields=_status(PROV, "MPN from DESIGN_SPEC (stock PROVISIONAL); height and the "
                                          "match of the KiCad 4x0402 convex land pattern not checked")))
            for e in range(4):
                idx = 4 * a + e
                if idx < len(bus):
                    sig = bus[idx]
                    d.net("CAM_%s_%s" % (side, sig), "%s.%s" % (ref, sig), "%s.A%d" % (rn, e + 1),
                          netclass="Fine")
                    d.net("CAM_%s" % sig, "%s.B%d" % (rn, e + 1))
                else:
                    d.no_connect("%s.A%d" % (rn, e + 1), "%s.B%d" % (rn, e + 1))
    for net in ("CAM_XVCLK", "CAM_SDA", "CAM_SCL_L", "CAM_SCL_R"):
        d.nets[net].netclass = "Fine"                  # they end on camera balls
    d.net("V2V8_CAM", netclass="CamPower")

    # ================================================================== power
    # spec rail table: V2V8 from MCP1700T-2802E/TT, 1 uF in, 1 uF out
    add(Part("U7", "MCP1700-2.8", SOT23,
             pins={"GND": ("1", "power_in"), "VOUT": ("2", "power_out"), "VIN": ("3", "power_in")},
             mpn="MCP1700T-2802E/TT", manufacturer="Microchip", distributor=BY_MPN,
             distributor_pn="MCP1700T-2802E/TT", height_mm=1.2, group="power",
             description="LDO 2.8 V 250 mA, 1.6 uA quiescent, SOT-23 (always on)",
             fields=_status(PROV, "family, pin order, Iq research-confirmed for the 3.0 V part "
                                  "(-3002); the 2.8 V order code -2802 is from DESIGN_SPEC, not seen")))
    d.net("VBAT", "U7.VIN")
    v2v8.append("U7.VOUT")
    gnd.append("U7.GND")
    # spec rail table: VDDUSB from MCP1700T-3302E/TT fed from VBUS (after the Schottky), MCU pin only
    add(Part("U11", "MCP1700-3.3", SOT23,
             pins={"GND": ("1", "power_in"), "VOUT": ("2", "power_out"), "VIN": ("3", "power_in")},
             mpn="MCP1700T-3302E/TT", manufacturer="Microchip", distributor=BY_MPN,
             distributor_pn="MCP1700T-3302E/TT", height_mm=1.2, group="power",
             description="LDO 3.3 V 250 mA, SOT-23 (VDDUSB, present only in the cradle)",
             fields=_status(PROV, "order code -3302 from DESIGN_SPEC, not seen; see U7")))
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
    # spec: charger MCP73831, 20 mA; STAT to an MCU input with a 100 kohm pull-up to V2V8
    add(Part("U9", "MCP73831", SOT235,
             pins={"STAT": ("1", "open_drain"), "VSS": ("2", "power_in"),
                   "VBAT": ("3", "power_out"), "VDD": ("4", "power_in"), "PROG": ("5", "passive")},
             mpn="MCP73831T-2ACI/OT", manufacturer="Microchip", distributor="Digi-Key",
             distributor_pn="MCP73831T-2ACI/OTCT-ND", height_mm=1.45, group="power",
             description="Li-Po charger 4.20 V, I = 1000 V / R_PROG, SOT-23-5",
             fields=_status(RES, "MPN, pin order, PROG formula research-confirmed; the tri-state "
                                 "STAT output (drives HIGH when done) is from memory: PROVISIONAL")))
    d.net("CHG_STAT_RAW", "U9.STAT")
    d.net("VBAT", "U9.VBAT", netclass="Power", power_flag=True)   # also driven by the cell (BT1)
    d.net("VBUS_D", "U9.VDD", netclass="Power", power_flag=True)  # fed from VBUS through D17
    d.net("CHG_PROG", "U9.PROG")
    gnd.append("U9.VSS")
    # STAT isolation - ADDED: the MCP73831 (not the open-drain MCP73832) drives STAT to VDD
    # (about 4.7 V) at end of charge; the diode makes it pull-down-only for the 2.8 V input.
    add(Part("D18", "1N4148WS", SOD323, pins={"K": ("1", "passive"), "A": ("2", "passive")},
             mpn="1N4148WS-7-F", manufacturer="Diodes Incorporated", distributor=BY_MPN,
             distributor_pn="1N4148WS-7-F", height_mm=1.1, group="power",
             description="Switching diode 75 V 150 mA SOD-323 (charger STAT can only pull low)",
             fields=_status(PROV, "ADDED part; MPN from memory")))
    d.net("CHG_STAT_RAW", "D18.K")
    d.net("CHG_STAT", "D18.A")
    # spec: "low-threshold N-MOSFET (gate threshold 1.5 V maximum, for example onsemi BSS138)"
    add(Part("Q1", "BSS138", SOT23,
             pins={"G": ("1", "input"), "S": ("2", "passive"), "D": ("3", "passive")},
             mpn="BSS138LT1G", manufacturer="onsemi", distributor=BY_MPN,
             distributor_pn="BSS138LT1G", height_mm=1.2, group="power",
             description="N-MOSFET 50 V, VGS(th) 1.5 V max, SOT-23 (PROG return switch)",
             fields=_status(PROV, "part named in DESIGN_SPEC; order code, pin order (G1 S2 D3) and "
                                  "threshold from memory")))
    d.net("CHG_INHIBIT", "Q1.G")
    d.net("CHG_PROG_SW", "Q1.D")
    gnd.append("Q1.S")
    # spec: "Series Schottky from pad to charger"
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
    # spec: "a 10 kohm NTC (Murata NCP15XH103F03RC, 0402 ...) on the top side within 1 mm of the cell edge"
    add(Part("RT1", "NTC 10k", R0402, pins=two_pin(), mpn="NCP15XH103F03RC",
             manufacturer="Murata", distributor=BY_MPN, distributor_pn="NCP15XH103F03RC",
             height_mm=0.55, group="power",
             description="NTC thermistor 10 kohm 1 %, B 3380 K, 0402 (cell temperature)",
             fields=_status(PROV, "MPN from DESIGN_SPEC (stock PROVISIONAL); B value as used by the "
                                  "firmware, no R-T table read")))
    d.net("NTC_SENSE", "RT1.1")
    gnd.append("RT1.2")
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
    pad_of_tail = {n: (n if LCD_TAIL_PIN1_AT_PAD1 else 11 - n) for n in LCD_TAIL}
    j1_pins = {LCD_TAIL[n]: (str(pad_of_tail[n]), "passive") for n in LCD_TAIL}
    j1_pins["MP"] = ("MP", "passive")
    add(Part("J1", "LCD FPC 10", FPC10, pins=j1_pins, mpn="FH12A-10S-0.5SH(55)",
             manufacturer="Hirose", distributor="Digi-Key",
             distributor_pn="product page 1110331 (SKU not seen)", height_mm=J1_HEIGHT, group="display",
             description="FPC connector 10 x 0.5 mm, TOP contact, 2.0 mm high; PIN-1 END PROVISIONAL",
             fields=_status(PROV, "top-contact FH12A on the bottom-contact FH12 land pattern "
                                  "(spec); pin order and pin-1 end PROVISIONAL (LCD_TAIL)")), J1_XY, 0.0)
    d.net("SPI1_SCK", "J1.SCLK")
    d.net("SPI1_MOSI", "J1.SI")
    d.net("LCD_SCS", "J1.SCS")
    d.net("LCD_EXTCOMIN", "J1.EXTCOMIN")
    d.net("LCD_DISP", "J1.DISP")
    v2v8 += ["J1.VDDA", "J1.VDD", "J1.EXTMODE"]
    gnd += ["J1.VSS", "J1.VSSA", "J1.MP"]

    # ========================================================= grain sensor (underside)
    for ref, colour, x, y, rot, az, anode, cathode in led_positions():
        red = colour == "red"
        part = Part(ref, "LED red" if red else "LED NIR", LED0402,
                    pins={"K": ("1", "passive"), "A": ("2", "passive")},
                    mpn="VLMS1500-GS08" if red else "SFH 4053",
                    manufacturer="Vishay" if red else "ams OSRAM", distributor=BY_MPN,
                    distributor_pn="VLMS1500-GS08" if red else "SFH 4053",
                    side=BOTTOM, height_mm=LED_RING["led_height"], group="grain",
                    description="LED super red 631 nm 0402" if red else "LED 850 nm 0402",
                    fields=dict(_status(PROV, "MPN research-confirmed; land pattern is the generic "
                                              "KiCad 0402 LED, polarity mark and pad sizes not checked"),
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

    # ==================================================== underside contact pads, lands
    row = contact_row_footprint()
    j2_names = ("VBUS", "DM", "DP", "GND", "SWDIO", "SWCLK", "NRST")          # YAML order, -x to +x
    j2 = Part("J2", "Cradle pads", row, pins={n: (str(i + 1), "passive") for i, n in enumerate(j2_names)},
              side=BOTTOM, in_bom=False, height_mm=0.0, group="service",
              description="VBUS D- D+ GND SWDIO SWCLK NRST (underside, x = -7.62 ... +7.62)")
    j2.place(0.5 * (PAD_ROW["xs"][0] + PAD_ROW["xs"][-1]), PAD_ROW["y"], 0.0)
    d.add(j2)
    d.net("VBUS", "J2.VBUS")
    d.net("USB_DM", "J2.DM")
    d.net("USB_DP", "J2.DP")
    gnd.append("J2.GND")
    d.net("SWDIO", "J2.SWDIO")
    d.net("SWCLK", "J2.SWCLK")
    d.net("NRST", "J2.NRST")
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
    if d.part("U4").placed:
        d.add_body_keepout("U4")
    # ---- fine areas: the fine classes are fine only round the cameras --------------------------
    d.add_fine_area("U2", margin=5.0)
    d.add_fine_area("U3", margin=5.0)
    # ---- fiducials: three per side -------------------------------------------------------------
    for x, y in FIDUCIALS_TOP:
        d.add_fiducial(x, y)
    for x, y in FIDUCIALS_BOTTOM:
        d.add_fiducial(x, y, side=BOTTOM).dnp = BARE_BOTTOM_COPPER_NOT_FITTED
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
