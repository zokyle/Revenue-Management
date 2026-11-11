"""GreenLine DEMO design - a close stand-in for the real GL-1 board.

It is NOT the real circuit (that is still being finalised); it has the same
outline, layer stack, rule set, part mix and placement of the big parts, so
that a toolchain that takes this board to "0 errors" is a small step away
from the real one.

* outline (rev C of ``design/master_params.yaml``): circle r = 21.1 mm clipped
  by a chord at y = +17.3 mm, a non-plated locating hole (1.15 mm) at
  (-4.2, 14.55) and a non-plated locating slot (1.15 x 1.65 mm) at
  (+4.2, 14.55); 4 layers, 0.8 mm, rule set US_4L_FINE (board minimums
  0.09 / 0.09 mm)
* net classes: Default 0.15 / 0.127, Power 0.30 / 0.127 (may neck down to
  0.15), Fine 0.09 / 0.09 (only the signals on the two camera BGAs), CamPower
  0.15 / 0.09 (the camera supply balls).  The demo declares NO fine areas
  (``FINE_AREAS``): with the fine classes confined to windows around the
  cameras this router leaves connections open on this board, so their nets
  may be fine anywhere; the router widens them to 0.15 mm where it finds room
  and the fab README states, measured, where the fine tracks are
* GND plane on In1.Cu; In2.Cu is the V2V8 plane and, marked ``routable``, the
  third routing layer next to F.Cu and B.Cu; the other supplies are tracks;
  through vias only, tented and plugged on the bottom side (the underside is
  a wetted surface), open on the top side
* three global fiducials (1 mm copper in a 2 mm mask opening) on each side
* top: LQFP-64 MCU (real STM32U585RITx pad map from the KiCad library, the
  camera port on the pads the design spec lists), two 25-ball 0.5 mm-pitch
  camera BGAs sharing an 11-signal bus, LGA-14 IMU, LGA-16 inclinometer,
  WSON-8 flash, four SOT-23 family regulators / charger, SOT-23-6 ESD array,
  3215 crystal, 10-pin 0.5 mm FPC connector, a Schottky diode, 60 x 0402
  passives, two battery solder pads
* bottom: 16 x 0402 LEDs on a 5.2 mm radius about (0, -4), charlieplexed on
  5 lines through 5 series resistors, a 2-pad photodiode at (0, -4) and seven
  bare 1.8 mm contact pads at y = -17.0, x = -7.62 ... +7.62
* mechanics: no copper on F.Cu under the IMU and inclinometer bodies, no
  top-side parts under the battery body and on the eight 1.6 mm post feet, and
  nothing taller than 0.95 mm under the two camera hoods except the camera

The camera ball map and several pin assignments are stand-ins - see
``design/DESIGN_SPEC.md`` for what is verified.  ``demo_design()`` returns a
fresh :class:`gleda.model.Design`.
"""
import math

from gleda.model import (Design, Outline, PathShape, RoundedPolygon, Part, two_pin, n_pin,
                         US_4L_FINE, BOTTOM)
from gleda import footprints as F

R0402 = "Resistor_SMD:R_0402_1005Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
LED0402 = "LED_SMD:LED_0402_1005Metric"
LQFP64 = "Package_QFP:LQFP-64_10x10mm_P0.5mm"
LGA14 = "Package_LGA:LGA-14_3x2.5mm_P0.5mm_LayoutBorder3x4y"
WSON8 = "Package_SON:WSON-8-1EP_6x5mm_P1.27mm_EP3.4x4.3mm"
SOT23 = "Package_TO_SOT_SMD:SOT-23"
SOT235 = "Package_TO_SOT_SMD:SOT-23-5"
SOT236 = "Package_TO_SOT_SMD:SOT-23-6"
SOD323 = "Diode_SMD:D_SOD-323"
FPC10 = "Connector_FFC-FPC:Hirose_FH12-10S-0.5SH_1x10-1MP_P0.50mm_Horizontal"
XTAL = "Crystal:Crystal_SMD_3215-2Pin_3.2x1.5mm"

BOARD_RADIUS = 21.1                  # rev C of design/master_params.yaml
FLAT_Y = 17.3
CAMERA_X = 10.0                      # cameras at (-10, 15.6) and (+10, 15.6)
CAMERA_Y = 15.6
#: non-plated locating features for the tub spigots: a round hole and a slot
LOCATING_HOLE = (-4.2, 14.55, 1.15)              # x, y, diameter
LOCATING_SLOT = (4.2, 14.55, 1.15, 1.65)         # x, y, width, overall length along x
#: 1.6 mm square feet of the tub posts that land on the top side: no parts there
POST_FEET = [(-15.4, 1.8), (15.4, 1.8), (-14.35, 10.8), (14.35, 10.8), (-6.5, -18.6),
             (6.5, -18.6), (-4.2, 14.55), (4.2, 14.55)]
POST_FOOT_SIZE = 1.6
#: camera hoods of the tub: nothing taller than 0.95 mm under them but the camera
HOOD_HALF_W = 2.85
HOOD_Y0 = 13.7
HOOD_MAX_HEIGHT = 0.95
LED_RING = (0.0, -4.0, 5.2)          # centre x, centre y, radius
PAD_ROW_Y = -17.0
BATTERY_BODY = (0.0, -5.2, 34.0, 10.0)   # centre x, centre y, dx, dy
#: Fine areas (``Design.add_fine_area``) confine the fine classes to windows
#: around the camera BGAs: ``FINE_AREAS = (("U2", 5.0), ("U3", 5.0))`` asks for
#: 5 mm around each ball field (the router's escape window of 3 to 4 mm plus
#: 1 mm in which the fan-out spreads to the standard pitch).  The toolchain
#: supports that end to end (router, audit, KiCad rule, output checks) - but
#: on THIS board the router then leaves 2 to 11 of the 261 connections open
#: (ten attempts with windows from 5 mm up to the whole upper half of the
#: board, both tenting modes).  The shared camera bus has to reach MCU pins on
#: three sides of the LQFP, and at 0.15 / 0.127 mm that is more than this
#: router can do here.  So the demo does not confine them; nothing is claimed
#: that is not measured (see fab/README.txt).
FINE_AREAS = ()
#: global fiducials (x, y): three per side, far apart, not in line, not
#: mirror-symmetric, clear of the tub post feet and of the battery body
FIDUCIALS_TOP = [(-19.3, -0.8), (19.0, -3.0), (-16.5, 9.9)]
FIDUCIALS_BOTTOM = [(-13.5, -3.0), (14.0, -7.0), (0.0, -13.3)]

#: stand-in camera ball map: ball -> (pin name, electrical type).  Row A faces
#: the flat board edge, only 0.7 mm away: one track fits between the balls and
#: the edge and no via does, so the stand-in keeps that row nearly empty.  The
#: eight data balls are inside and can only escape between the outer balls;
#: ground is on the bottom corners, where there is room for its vias.
CAM_BALLS = {
    "A1": ("NC1", "nc"), "A2": ("NC2", "nc"), "A3": ("XVCLK", "input"),
    "A4": ("NC3", "nc"), "A5": ("NC4", "nc"),
    "B1": ("SCL", "input"), "B2": ("D0", "bidir"), "B3": ("D1", "bidir"),
    "B4": ("D2", "bidir"), "B5": ("SDA", "bidir"),
    "C1": ("PCLK", "bidir"), "C2": ("D3", "bidir"), "C3": ("NC5", "nc"),
    "C4": ("D4", "bidir"), "C5": ("VSYNC", "bidir"),
    "D1": ("DOVDD", "power_in"), "D2": ("D5", "bidir"), "D3": ("D6", "bidir"),
    "D4": ("D7", "bidir"), "D5": ("AVDD", "power_in"),
    "E1": ("GND1", "power_in"), "E2": ("HREF", "bidir"), "E3": ("DVDD", "power_out"),
    "E4": ("PWDN", "input"), "E5": ("GND2", "power_in"),
}

#: MCU pad -> (pin name, electrical type): STM32U585RITx in LQFP-64, pad
#: numbers and port names from the KiCad symbol library.
MCU_PADS = {
    1: ("VBAT", "power_in"), 2: ("PC13", "bidir"), 3: ("PC14", "bidir"), 4: ("PC15", "bidir"),
    5: ("PH0", "bidir"), 6: ("PH1", "bidir"), 7: ("NRST", "input"), 8: ("PC0", "bidir"),
    9: ("PC1", "bidir"), 10: ("PC2", "bidir"), 11: ("PC3", "bidir"), 12: ("VSSA", "power_in"),
    13: ("VDDA", "power_in"), 14: ("PA0", "bidir"), 15: ("PA1", "bidir"), 16: ("PA2", "bidir"),
    17: ("PA3", "bidir"), 18: ("VSS1", "power_in"), 19: ("VDD1", "power_in"),
    20: ("PA4", "bidir"), 21: ("PA5", "bidir"), 22: ("PA6", "bidir"), 23: ("PA7", "bidir"),
    24: ("PC4", "bidir"), 25: ("PC5", "bidir"), 26: ("PB0", "bidir"), 27: ("PB1", "bidir"),
    28: ("PB2", "bidir"), 29: ("PB10", "bidir"), 30: ("VCAP", "power_out"),
    31: ("VSS2", "power_in"), 32: ("VDD2", "power_in"), 33: ("PB12", "bidir"),
    34: ("PB13", "bidir"), 35: ("PB14", "bidir"), 36: ("PB15", "bidir"), 37: ("PC6", "bidir"),
    38: ("PC7", "bidir"), 39: ("PC8", "bidir"), 40: ("PC9", "bidir"), 41: ("PA8", "bidir"),
    42: ("PA9", "bidir"), 43: ("PA10", "bidir"), 44: ("PA11", "bidir"), 45: ("PA12", "bidir"),
    46: ("PA13", "bidir"), 47: ("VSS3", "power_in"), 48: ("VDDUSB", "power_in"),
    49: ("PA14", "bidir"), 50: ("PA15", "bidir"), 51: ("PC10", "bidir"), 52: ("PC11", "bidir"),
    53: ("PC12", "bidir"), 54: ("PD2", "bidir"), 55: ("PB3", "bidir"), 56: ("PB4", "bidir"),
    57: ("PB5", "bidir"), 58: ("PB6", "bidir"), 59: ("PB7", "bidir"), 60: ("PH3", "bidir"),
    61: ("PB8", "bidir"), 62: ("PB9", "bidir"), 63: ("VSS4", "power_in"),
    64: ("VDD3", "power_in"),
}

#: signal -> MCU port pin.  Camera port (DCMI), MCO, USB, SWD, crystal, BOOT0,
#: SPI1 MISO and the LCD EXTCOMIN timer pin are the pins the design spec fixes.
#: The others are stand-ins chosen the way a layout engineer would choose
#: them: each signal on the side of the package that faces its destination
#: (with U1 at 270 deg pads 1-16 are on the top edge, 17-32 left, 33-48
#: bottom, 49-64 right) - SPI1 on PB3/PB4/PB5 next to the flash, the IMU on the
#: left and bottom-left pins, the camera control lines on the top edge.
MCU_SIGNALS = {
    # camera port: fixed by the DCMI alternate functions
    "CAM_D0": "PC6", "CAM_D1": "PC7", "CAM_D2": "PC8", "CAM_D3": "PC9", "CAM_D4": "PC11",
    "CAM_D5": "PB6", "CAM_D6": "PB8", "CAM_D7": "PB9", "CAM_PCLK": "PA6", "CAM_HREF": "PA4",
    "CAM_VSYNC": "PB7", "MCO": "PA8",
    # camera control: top edge, towards the cameras and their LDO
    "CAM_SCL_L": "PC3", "CAM_PWDN_L": "PC2", "CAM_EN": "PC1", "CAM_SDA": "PH1",
    "CAM_SCL_R": "PH0", "CAM_PWDN_R": "PC13",
    # fixed service pins
    "USB_DM": "PA11", "USB_DP": "PA12", "SWDIO": "PA13", "SWCLK": "PA14", "NRST": "NRST",
    "OSC32_IN": "PC14", "OSC32_OUT": "PC15", "BOOT0": "PH3",
    # flash and LCD on SPI1 (right edge, next to the flash)
    "SPI1_SCK": "PB3", "SPI1_MISO": "PB4", "SPI1_MOSI": "PB5", "FLASH_CS": "PA10",
    "LCD_SCS": "PB12", "LCD_DISP": "PB13", "LCD_EXTCOMIN": "PB2",
    # IMU and inclinometer on SPI2 (left and bottom-left pins)
    "SPI2_SCK": "PB10", "SPI2_MISO": "PB14", "SPI2_MOSI": "PB15", "IMU_CS": "PB0",
    "INC_CS": "PB1", "IMU_INT1": "PC5", "IMU_INT2": "PC4",
    # analogue and housekeeping
    "VBAT_SENSE": "PC0", "VBUS_SENSE": "PA5", "CHG_STAT": "PA2", "CHG_PROG_SW": "PA7",
    "VBIAS": "PA0", "PD_K": "PA1", "OPAMP_OUT": "PA3",
    # grain LED drive lines (to the series resistors on the right)
    "CP1_MCU": "PA15", "CP2_MCU": "PC10", "CP3_MCU": "PC12", "CP4_MCU": "PD2",
    "CP5_MCU": "PA9",
}

#: charlieplex wiring of the LED pairs: (line of anode, line of cathode) of
#: the first LED of each pair, the second LED is antiparallel
CHARLIE_PAIRS = [(1, 2), (2, 3), (3, 4), (4, 5), (5, 1), (1, 3), (2, 4), (3, 5)]


#: 0402 passives: (ref, value, schematic group, x, y, rotation).  Placement
#: rules of thumb used here: a 0402 with a plane connection needs about
#: 1.4 x 2.0 mm so that its via fits next to it; the sides of the camera
#: BGAs that face the board centre are kept clear for the bus escape; and no
#: part sits in the pocket between a locating hole / slot and its neighbour
#: (copper keeps 0.3 mm from those, a pad there can hardly be reached).
PASSIVES = [
    # MCU supply and housekeeping
    ("C1", "100n", "mcu", -7.25, 9.4, 90.0),       # VDD pad 19
    ("C2", "100n", "mcu", -7.25, 1.9, 90.0),       # VDD pad 32
    ("C3", "4u7", "mcu", -7.25, 4.4, 90.0),        # VCAP pad 30
    ("C4", "100n", "mcu", 7.25, 8.9, 90.0),        # VDD pad 64
    ("C5", "100n", "mcu", 2.75, 14.7, 90.0),       # VBAT pad 1
    ("C6", "4u7", "mcu", 7.25, 4.4, 90.0),         # bulk
    ("C7", "100n", "mcu", 7.25, 1.9, 90.0),        # VDDUSB pad 48
    ("C28", "1u", "mcu", 8.3, 1.9, 90.0),          # VDDUSB
    ("C8", "1u", "mcu", -2.75, 14.7, 90.0),        # VDDA pad 13
    ("C9", "10n", "mcu", -6.25, 12.9, 0.0),         # VDDA, in the corner notch of U1
    ("R6", "10R", "mcu", -7.25, 11.4, 90.0),       # V2V8 -> VDDA
    ("C10", "100n", "mcu", 9.3, -16.2, 0.0),       # NRST
    ("R7", "10k", "mcu", 7.25, 6.9, 90.0),         # BOOT0 pull-down
    ("C11", "6p8", "mcu", 11.5, 11.4, 90.0),       # crystal load
    ("C12", "6p8", "mcu", 12.55, 11.4, 90.0),
    ("C25", "100n", "mcu", 12.5, 9.7, 0.0),        # flash VCC
    # cameras
    ("C13", "100n", "camera", -6.9, 14.7, 90.0),   # U2 AVDD
    ("C14", "100n", "camera", -14.2, 12.9, 0.0),   # U2 DOVDD
    ("C15", "1u", "camera", -12.1, 12.9, 0.0),     # U2 DVDD
    ("C17", "100n", "camera", 14.2, 12.9, 0.0),    # U3 AVDD
    ("C18", "100n", "camera", 6.9, 14.7, 90.0),    # U3 DOVDD
    ("C19", "1u", "camera", 12.1, 12.9, 0.0),      # U3 DVDD
    ("R8", "2k2", "camera", -10.1, 10.8, 0.0),     # SCL_L pull-up
    ("R9", "2k2", "camera", 5.3, 16.3, 0.0),       # SCL_R pull-up
    ("R12", "2k2", "camera", -10.1, 9.65, 0.0),    # SDA pull-up
    ("R10", "33R", "camera", -12.2, 10.8, 0.0),    # PCLK_L series
    ("R11", "33R", "camera", 6.25, 12.9, 0.0),     # PCLK_R series, corner notch of U1
    ("R13", "33R", "camera", 9.4, 1.9, 90.0),      # MCO series
    ("C16", "1u", "power", -3.2, 16.3, 0.0),       # U8 VIN
    ("C20", "1u", "power", 3.2, 16.3, 0.0),        # U8 VOUT
    ("R14", "100k", "power", -5.3, 16.3, 0.0),     # CAM_EN pull-down
    # sensors
    ("C21", "100n", "sensor", -8.3, 4.4, 90.0),    # IMU VDD
    ("C22", "100n", "sensor", -11.5, 3.6, 0.0),    # IMU VDDIO
    ("C23", "100n", "sensor", -17.6, 1.9, 180.0),  # inclinometer VDD
    ("C24", "100n", "sensor", -12.2, 2.4, 0.0),    # inclinometer VDDIO
    # grain sensor: charlieplex series resistors and photodiode amplifier
    ("R1", "68R", "grain", 16.3, 10.4, 0.0),
    ("R2", "68R", "grain", 16.3, 9.2, 0.0),
    ("R3", "68R", "grain", 16.3, 8.0, 0.0),
    ("R4", "68R", "grain", 16.3, 6.8, 0.0),
    ("R5", "68R", "grain", 16.3, 5.6, 0.0),
    ("R16", "470k", "grain", -7.25, 6.9, 90.0),    # feedback
    ("C26", "10p", "grain", -8.3, 6.9, 90.0),
    ("R17", "100k", "grain", -12.2, 9.65, 0.0),    # bias divider
    ("R18", "100k", "grain", -12.2, 8.5, 0.0),
    ("C27", "100n", "grain", -10.1, 8.5, 0.0),
    # power
    ("C29", "4u7", "power", -6.75, -14.6, 90.0),   # charger VDD
    ("C30", "4u7", "power", -12.3, -15.9, 0.0),    # charger VBAT
    ("R20", "49k9", "power", -6.75, -12.5, 90.0),  # charger PROG
    ("C31", "1u", "power", 11.6, -15.8, 0.0),      # U7 VIN
    ("C32", "1u", "power", 7.0, -14.6, 90.0),      # U7 VOUT
    ("C33", "1u", "power", 13.6, -14.6, 0.0),      # U11 VIN
    ("C34", "1u", "power", 11.1, -10.9, 0.0),      # U11 VOUT
    ("R21", "100k", "power", -8.0, -10.9, 0.0),    # VBUS sense divider
    ("R22", "100k", "power", -10.1, -10.9, 0.0),
    ("R23", "1M", "power", 16.3, 4.3, 0.0),        # VBAT sense divider
    ("R24", "1M", "power", 17.4, 3.1, 0.0),
    ("C35", "100n", "power", 18.5, 4.3, 0.0),
    ("R25", "100k", "power", -14.3, 9.0, 0.0),     # CHG_STAT pull-up
    # display
    ("C36", "1u", "display", 6.05, -12.5, 90.0),   # LCD VDD
    ("R19", "100k", "display", 7.0, -12.5, 90.0),  # LCD DISP pull-down
]


def camera_footprint():
    """25-ball 5 x 5, 0.5 mm pitch, 0.23 mm pads with a 0.09 mm clearance
    override: 0.5 - 0.23 = 0.27 = one 0.09 mm track + 2 x 0.09 mm clearance
    (0.25 mm pads cannot be escaped, see tests/test_netclasses.py)."""
    return F.bga("CamCube_BGA25_P0.5", 5, 5, pitch=0.5, pad_d=0.23, body=(3.47, 2.95),
                 height=2.76, pad_clearance=0.09, courtyard_margin=0.2)


def inclinometer_footprint():
    """Ceramic LGA-16, 5 x 5 mm, 4 pads per side at 1.0 mm pitch (stand-in)."""
    return F.quad_package("LGA-16_5x5mm_P1.0mm", 5.0, 5.0, pitch=1.0, nx=4, ny=4,
                          pad_w=0.4, pad_l=0.6, pad_centre_inset=0.4, height=1.7)


def photodiode_footprint():
    return F.two_pad("Photodiode_4.8x2.5mm", pad_w=1.0, pad_h=1.8, pitch=3.8,
                     body=(4.8, 2.5), numbers=("A", "K"), height=0.48, polarised=True,
                     tags="photodiode")


def contact_row_footprint():
    return F.pad_row("ContactRow_7x1.8mm_P2.54", 7, 2.54, 1.8,
                     description="7 flush gold contact pads for the cradle pogo pins")


def led_ring_positions(count=16):
    """(x, y, rotation) of the grain LEDs: tangential, evenly spaced."""
    cx, cy, r = LED_RING
    out = []
    for i in range(count):
        a = 360.0 * i / count
        out.append((round(cx + r * math.cos(math.radians(a)), 4),
                    round(cy + r * math.sin(math.radians(a)), 4), (a + 90.0) % 360.0))
    return out


_CAP_MPN = {"100n": ("GRM155R71C104KA88D", "490-3261-1-ND", 0.02),
            "10n": ("GRM155R71H103KA88D", "490-1312-1-ND", 0.02),
            "1u": ("GRM155R61A105KE15D", "490-3890-1-ND", 0.03),
            "4u7": ("GRM155R60J475ME47D", "490-5915-1-ND", 0.06),
            "6p8": ("GRM1555C1H6R8CA01D", "490-5947-1-ND", 0.03),
            "10p": ("GRM1555C1H100JA01D", "490-5921-1-ND", 0.03)}
_RES_MPN = {"68R": "RC0402FR-0768RL", "33R": "RC0402FR-0733RL", "10R": "RC0402FR-0710RL",
            "2k2": "RC0402FR-072K2L", "10k": "RC0402FR-0710KL", "49k9": "RC0402FR-0749K9L",
            "100k": "RC0402FR-07100KL", "470k": "RC0402FR-07470KL", "1M": "RC0402FR-071ML"}


def _cap(ref, value, x, y, rot=0.0, group="power"):
    mpn, dpn, price = _CAP_MPN[value]
    return Part(ref, value, C0402, pins=two_pin(), mpn=mpn, manufacturer="Murata",
                distributor="Digi-Key", distributor_pn=dpn, unit_price=price, x=x, y=y,
                rotation=rot, height_mm=0.55, group=group, description="MLCC 0402 %s" % value)


def _res(ref, value, x, y, rot=0.0, group="main"):
    mpn = _RES_MPN[value]
    return Part(ref, value, R0402, pins=two_pin(), mpn=mpn, manufacturer="Yageo",
                distributor="Digi-Key", distributor_pn="%s-ND" % mpn, unit_price=0.01, x=x,
                y=y, rotation=rot, height_mm=0.4, group=group,
                description="Resistor 0402 1%% %s" % value)


def demo_design(name="greenline_demo"):
    outline = Outline(PathShape.d_shape(BOARD_RADIUS, FLAT_Y))
    outline.add_hole(*LOCATING_HOLE, name="H1")
    outline.add_npth_slot(*LOCATING_SLOT)
    d = Design(name, outline, layers=4,
               rules=US_4L_FINE, board_thickness=0.8,
               title="GreenLine GL-1 DEMO (toolchain proof, not the product circuit)",
               revision="demo-1", company="GreenLine")
    d.add_netclass("Fine", track_width=0.09, clearance=0.09,
                   description="signals of the 0.5 mm-pitch camera BGAs (escape between balls)")
    d.add_netclass("CamPower", track_width=0.15, clearance=0.09,
                   description="camera supply balls: 0.15 mm track that fits the escape lanes")
    # power nets are 0.30 mm wide but may neck down to 0.15 mm at fine pads
    d.add_netclass("Power", track_width=US_4L_FINE.power_track,
                   clearance=US_4L_FINE.default_clearance, min_track_width=0.15,
                   description="supply nets; neck-down to 0.15 mm allowed")
    d.via_tenting = "bottom"
    # design/DESIGN_SPEC.md: "Vias tented and plugged on the underside (the
    # underside is a wetted surface)"
    d.via_protection = ("plugged with solder mask from the BOTTOM side and tented there "
                        "(IPC-4761 type III-a); the top side of the vias stays open")
    d.fab_notes += [
        "The bottom side is a wetted surface in use: no open via holes there.",
    ]

    # ---- ICs, top side ----------------------------------------------------
    mcu_pins = {name_: (str(pad), etype) for pad, (name_, etype) in MCU_PADS.items()}
    d.add(Part("U1", "STM32U585RIT6", LQFP64, pins=mcu_pins, mpn="STM32U585RIT6",
               manufacturer="STMicroelectronics", distributor="Digi-Key",
               distributor_pn="497-STM32U585RIT6-ND", unit_price=9.5, x=0.0, y=6.9,
               rotation=270.0, height_mm=1.6, group="mcu", description="MCU, LQFP-64"))
    cam = camera_footprint()
    cam_pins = {pin: (ball, etype) for ball, (pin, etype) in CAM_BALLS.items()}
    for ref, x in (("U2", -CAMERA_X), ("U3", CAMERA_X)):
        d.add(Part(ref, "OVM7692", cam, pins=cam_pins, mpn="OVM7692-RYAA",
                   manufacturer="OmniVision", distributor="Digi-Key",
                   distributor_pn="884-1027-1-ND", unit_price=6.0, x=x, y=CAMERA_Y,
                   height_mm=2.76, group="camera",
                   description="camera cube (stand-in ball map)"))
    # SDO / MISO are tri-state outputs sharing one line: modelled as "bidir"
    imu_pins = {"SDO": ("1", "bidir"), "SDX": ("2", "passive"), "SCX": ("3", "passive"),
                "INT1": ("4", "output"), "VDDIO": ("5", "power_in"), "GND1": ("6", "power_in"),
                "GND2": ("7", "power_in"), "VDD": ("8", "power_in"), "INT2": ("9", "output"),
                "OCS": ("10", "nc"), "OSDO": ("11", "nc"), "CS": ("12", "input"),
                "SCL": ("13", "input"), "SDA": ("14", "input")}
    d.add(Part("U4", "LSM6DSV16X", LGA14, pins=imu_pins, mpn="LSM6DSV16XTR",
               manufacturer="STMicroelectronics", distributor="Digi-Key",
               distributor_pn="497-LSM6DSV16XTRCT-ND", unit_price=4.5, x=-11.0, y=6.0,
               height_mm=0.86, group="sensor", description="6-axis IMU, LGA-14"))
    inc_pins = {"VDD": ("1", "power_in"), "VDDIO": ("2", "power_in"), "GND1": ("3", "power_in"),
                "GND2": ("4", "power_in"), "CS": ("5", "input"), "SCK": ("6", "input"),
                "MOSI": ("7", "input"), "MISO": ("8", "bidir")}
    for n in range(9, 17):
        inc_pins["NC%d" % n] = (str(n), "nc")
    d.add(Part("U5", "Inclinometer", inclinometer_footprint(), pins=inc_pins,
               mpn="IIS2ICLXTR", manufacturer="STMicroelectronics", distributor="Digi-Key",
               distributor_pn="497-IIS2ICLXTRCT-ND", unit_price=18.0, x=-15.9, y=5.5,
               rotation=90.0, height_mm=1.7, group="sensor",
               description="inclinometer, LGA-16 (stand-in pin map)"))
    flash_pins = {"CS": ("1", "input"), "DO": ("2", "bidir"), "WP": ("3", "input"),
                  "GND": (("4", "9"), "power_in"), "DI": ("5", "input"), "CLK": ("6", "input"),
                  "HOLD": ("7", "input"), "VCC": ("8", "power_in")}
    d.add(Part("U6", "SPI flash", WSON8, pins=flash_pins, mpn="MX25R6435FZNIL0",
               manufacturer="Macronix", distributor="Digi-Key",
               distributor_pn="1092-1187-1-ND", unit_price=1.6, x=11.5, y=6.4,
               height_mm=0.8, group="mcu", description="SPI NOR flash 64 Mbit, WSON-8 6x5"))
    d.add(Part("U7", "MCP1700-2.8", SOT23,
               pins={"GND": ("1", "power_in"), "VOUT": ("2", "power_out"),
                     "VIN": ("3", "power_in")},
               mpn="MCP1700T-2802E/TT", manufacturer="Microchip", distributor="Digi-Key",
               distributor_pn="MCP1700T2802ETTCT-ND", unit_price=0.45, x=10.1, y=-13.6,
               height_mm=1.2, group="power", description="LDO 2.8 V, always on"))
    d.add(Part("U8", "LP5907-2.8", SOT235,
               pins={"VIN": ("1", "power_in"), "GND": ("2", "power_in"), "EN": ("3", "input"),
                     "NC": ("4", "nc"), "VOUT": ("5", "power_out")},
               mpn="LP5907MFX-2.8/NOPB", manufacturer="Texas Instruments",
               distributor="Digi-Key", distributor_pn="296-38557-1-ND", unit_price=0.6,
               x=0.0, y=15.45, height_mm=1.45, group="power",
               description="LDO 2.8 V for the cameras"))
    d.add(Part("U9", "MCP73831", SOT235,
               pins={"STAT": ("1", "open_drain"), "VSS": ("2", "power_in"),
                     "VBAT": ("3", "power_out"), "VDD": ("4", "power_in"),
                     "PROG": ("5", "passive")},
               mpn="MCP73831T-2ACI/OT", manufacturer="Microchip", distributor="Digi-Key",
               distributor_pn="MCP73831T-2ACI/OTCT-ND", unit_price=0.7, x=-9.85, y=-13.6,
               height_mm=1.45, group="power", description="Li-Po charger"))
    d.add(Part("U10", "USBLC6-2SC6", SOT236,
               pins={"IO1A": ("1", "passive"), "GND": ("2", "power_in"),
                     "IO2A": ("3", "passive"), "IO2B": ("4", "passive"),
                     "VBUS": ("5", "power_in"), "IO1B": ("6", "passive")},
               mpn="USBLC6-2SC6", manufacturer="STMicroelectronics", distributor="Digi-Key",
               distributor_pn="497-5235-1-ND", unit_price=0.4, x=-14.0, y=-11.9,
               height_mm=1.45, group="power", description="USB ESD protection", is_ic=False))
    d.add(Part("U11", "MCP1700-3.3", SOT23,
               pins={"GND": ("1", "power_in"), "VOUT": ("2", "power_out"),
                     "VIN": ("3", "power_in")},
               mpn="MCP1700T-3302E/TT", manufacturer="Microchip", distributor="Digi-Key",
               distributor_pn="MCP1700T3302ETTCT-ND", unit_price=0.45, x=14.0, y=-11.9,
               height_mm=1.2, group="power", description="LDO 3.3 V for VDDUSB"))
    d.add(Part("D17", "Schottky", SOD323, pins={"K": ("1", "passive"), "A": ("2", "passive")},
               mpn="BAT60JFILM", manufacturer="STMicroelectronics", distributor="Digi-Key",
               distributor_pn="497-3707-1-ND", unit_price=0.3, x=-9.2, y=-16.3,
               height_mm=1.0, group="power", description="VBUS series Schottky"))
    d.add(Part("J1", "LCD FPC 10", FPC10, pins=n_pin(10, "passive", {"MP": ("MP", "passive")}),
               mpn="FH12A-10S-0.5SH(55)", manufacturer="Hirose", distributor="Digi-Key",
               distributor_pn="HFJ110CT-ND", unit_price=0.9, x=0.0, y=-13.9, rotation=0.0,
               height_mm=2.0, group="display", description="LCD FPC connector, 10 x 0.5 mm"))
    d.add(Part("Y1", "32.768k", XTAL, pins=two_pin(), mpn="ABS07-120-32.768KHZ-T",
               manufacturer="Abracon", distributor="Digi-Key", distributor_pn="535-11937-1-ND",
               unit_price=0.6, x=8.9, y=11.2, height_mm=0.9, group="mcu",
               description="32.768 kHz crystal 3215"))
    bt = F.battery_tab(1.2, 2.0)
    d.add(Part("BT1", "BAT+", bt, pins={"1": "1"}, x=-18.5, y=-3.6, in_bom=False,
               height_mm=0.0, group="power", description="battery + solder pad"))
    d.add(Part("BT2", "BAT-", bt, pins={"1": "1"}, x=-18.5, y=-6.8, in_bom=False,
               height_mm=0.0, group="power", description="battery - solder pad"))

    # ---- passives, top side -------------------------------------------------
    for ref, value, group, x, y, rot in PASSIVES:
        make = _cap if ref.startswith("C") else _res
        d.add(make(ref, value, x, y, rot, group))

    # ---- bottom side ----------------------------------------------------------
    for i, (x, y, rot) in enumerate(led_ring_positions(), start=1):
        d.add(Part("D%d" % i, "LED red" if i % 2 else "LED NIR", LED0402,
                   pins={"K": ("1", "passive"), "A": ("2", "passive")},
                   mpn="APHHS1005SURCK" if i % 2 else "APHHS1005F3C",
                   manufacturer="Kingbright", distributor="Digi-Key",
                   distributor_pn="754-1104-1-ND" if i % 2 else "754-1105-1-ND",
                   unit_price=0.35, x=x, y=y, rotation=rot, side=BOTTOM, height_mm=0.45,
                   group="grain", description="grain LED 0402"))
    d.add(Part("PD1", "Photodiode", photodiode_footprint(),
               pins={"A": ("A", "passive"), "K": ("K", "passive")}, mpn="VEMD5510C",
               manufacturer="Vishay", distributor="Digi-Key", distributor_pn="VEMD5510CCT-ND",
               unit_price=1.2, x=LED_RING[0], y=LED_RING[1], side=BOTTOM, height_mm=0.48,
               group="grain", description="photodiode (stand-in land pattern)"))
    d.add(Part("J2", "Cradle pads", contact_row_footprint(), pins=n_pin(7), x=0.0,
               y=PAD_ROW_Y, side=BOTTOM, in_bom=False, height_mm=0.0, group="service",
               description="VBUS D- D+ GND SWDIO SWCLK NRST"))

    # ---- nets ---------------------------------------------------------------
    def mcu(signal):
        return "U1.%s" % MCU_SIGNALS[signal]

    d.net("GND", "U1.VSSA", "U1.VSS1", "U1.VSS2", "U1.VSS3", "U1.VSS4",
          "U2.GND1", "U2.GND2", "U3.GND1", "U3.GND2",
          "U4.GND1", "U4.GND2", "U4.SDX", "U4.SCX", "U5.GND1", "U5.GND2", "U6.GND",
          "U7.GND", "U8.GND", "U9.VSS", "U10.GND", "U11.GND", "J1.9", "J1.10", "J1.MP",
          "BT2.1", "J2.4",
          "C1.2", "C2.2", "C3.2", "C4.2", "C5.2", "C6.2", "C7.2", "C8.2", "C9.2", "C10.2",
          "C11.2", "C12.2", "C13.2", "C14.2", "C15.2", "C16.2", "C17.2", "C18.2", "C19.2",
          "C20.2", "C21.2", "C22.2", "C23.2", "C24.2", "C25.2", "C27.2", "C28.2", "C29.2",
          "C30.2", "C31.2", "C32.2", "C33.2", "C34.2", "C35.2", "C36.2",
          "R7.2", "R14.2", "R18.2", "R19.2", "R22.2", "R24.2", netclass="Power")
    d.net("V2V8", "U7.VOUT", "U1.VBAT", "U1.VDD1", "U1.VDD2", "U1.VDD3", "U4.VDD", "U4.VDDIO",
          "U5.VDD", "U5.VDDIO", "U6.VCC", "U6.WP", "U6.HOLD", "J1.6", "J1.7", "J1.8",
          "C1.1", "C2.1", "C4.1", "C5.1", "C6.1", "C21.1", "C22.1", "C23.1", "C24.1", "C25.1",
          "C32.1", "C36.1", "R6.1", "R17.1", "R25.1", netclass="Power")
    d.net("VDDA", "R6.2", "U1.VDDA", "C8.1", "C9.1", power_flag=True)    # RC-filtered V2V8
    d.net("VCAP", "U1.VCAP", "C3.1")
    d.net("VBUS", "J2.1", "U10.VBUS", "D17.A", netclass="Power", power_flag=True)
    d.net("VBUS_D", "D17.K", "U9.VDD", "U11.VIN", "C29.1", "C33.1", "R21.1", netclass="Power",
          power_flag=True)
    d.net("VBAT", "BT1.1", "U9.VBAT", "U7.VIN", "U8.VIN", "C30.1", "C31.1", "C16.1", "R23.1",
          netclass="Power")
    d.net("VDDUSB", "U11.VOUT", "U1.VDDUSB", "C34.1", "C7.1", "C28.1", netclass="Power")
    d.net("V2V8_CAM", "U8.VOUT", "U2.AVDD", "U2.DOVDD", "U3.AVDD", "U3.DOVDD", "C20.1",
          "C13.1", "C14.1", "C17.1", "C18.1", "R8.1", "R9.1", "R12.1", netclass="CamPower")
    d.net("CAM_L_DVDD", "U2.DVDD", "C15.1", netclass="CamPower")
    d.net("CAM_R_DVDD", "U3.DVDD", "C19.1", netclass="CamPower")
    d.net("CAM_EN", mcu("CAM_EN"), "U8.EN", "R14.1")
    for i in range(8):
        d.net("CAM_D%d" % i, mcu("CAM_D%d" % i), "U2.D%d" % i, "U3.D%d" % i, netclass="Fine")
    d.net("CAM_HREF", mcu("CAM_HREF"), "U2.HREF", "U3.HREF", netclass="Fine")
    d.net("CAM_VSYNC", mcu("CAM_VSYNC"), "U2.VSYNC", "U3.VSYNC", netclass="Fine")
    d.net("CAM_PCLK_L", "U2.PCLK", "R10.1", netclass="Fine")
    d.net("CAM_PCLK_R", "U3.PCLK", "R11.1", netclass="Fine")
    d.net("CAM_PCLK", mcu("CAM_PCLK"), "R10.2", "R11.2")
    d.net("MCO", mcu("MCO"), "R13.1")
    d.net("CAM_XVCLK", "R13.2", "U2.XVCLK", "U3.XVCLK", netclass="Fine")
    d.net("CAM_SDA", mcu("CAM_SDA"), "U2.SDA", "U3.SDA", "R12.2", netclass="Fine")
    d.net("CAM_SCL_L", mcu("CAM_SCL_L"), "U2.SCL", "R8.2", netclass="Fine")
    d.net("CAM_SCL_R", mcu("CAM_SCL_R"), "U3.SCL", "R9.2", netclass="Fine")
    d.net("CAM_PWDN_L", mcu("CAM_PWDN_L"), "U2.PWDN", netclass="Fine")
    d.net("CAM_PWDN_R", mcu("CAM_PWDN_R"), "U3.PWDN", netclass="Fine")
    d.net("SPI2_SCK", mcu("SPI2_SCK"), "U4.SCL", "U5.SCK")
    d.net("SPI2_MOSI", mcu("SPI2_MOSI"), "U4.SDA", "U5.MOSI")
    d.net("SPI2_MISO", mcu("SPI2_MISO"), "U4.SDO", "U5.MISO")
    d.net("IMU_CS", mcu("IMU_CS"), "U4.CS")
    d.net("INC_CS", mcu("INC_CS"), "U5.CS")
    d.net("IMU_INT1", mcu("IMU_INT1"), "U4.INT1")
    d.net("IMU_INT2", mcu("IMU_INT2"), "U4.INT2")
    d.net("SPI1_SCK", mcu("SPI1_SCK"), "U6.CLK", "J1.1")
    d.net("SPI1_MOSI", mcu("SPI1_MOSI"), "U6.DI", "J1.2")
    d.net("SPI1_MISO", mcu("SPI1_MISO"), "U6.DO")
    d.net("FLASH_CS", mcu("FLASH_CS"), "U6.CS")
    d.net("LCD_SCS", mcu("LCD_SCS"), "J1.3")
    d.net("LCD_EXTCOMIN", mcu("LCD_EXTCOMIN"), "J1.4")
    d.net("LCD_DISP", mcu("LCD_DISP"), "J1.5", "R19.1")
    d.net("OSC32_IN", mcu("OSC32_IN"), "Y1.1", "C11.1")
    d.net("OSC32_OUT", mcu("OSC32_OUT"), "Y1.2", "C12.1")
    d.net("NRST", mcu("NRST"), "J2.7", "C10.1")
    d.net("BOOT0", mcu("BOOT0"), "R7.1")
    d.net("SWDIO", mcu("SWDIO"), "J2.5")
    d.net("SWCLK", mcu("SWCLK"), "J2.6")
    d.net("USB_DM", mcu("USB_DM"), "J2.2", "U10.IO1A", "U10.IO1B")
    d.net("USB_DP", mcu("USB_DP"), "J2.3", "U10.IO2A", "U10.IO2B")
    d.net("VBUS_SENSE", mcu("VBUS_SENSE"), "R21.2", "R22.1")
    d.net("VBAT_SENSE", mcu("VBAT_SENSE"), "R23.2", "R24.1", "C35.1")
    d.net("CHG_STAT", "U9.STAT", mcu("CHG_STAT"), "R25.2")
    d.net("CHG_PROG", "U9.PROG", "R20.1")
    d.net("CHG_PROG_SW", "R20.2", mcu("CHG_PROG_SW"))
    d.net("VBIAS", mcu("VBIAS"), "PD1.A", "R17.2", "R18.1", "C27.1")
    d.net("PD_K", mcu("PD_K"), "PD1.K", "R16.1", "C26.1")
    d.net("OPAMP_OUT", mcu("OPAMP_OUT"), "R16.2", "C26.2")
    for i in range(1, 6):
        d.net("CP%d_MCU" % i, mcu("CP%d_MCU" % i), "R%d.1" % i)
        d.net("CP%d" % i, "R%d.2" % i)
    for k, (a, c) in enumerate(CHARLIE_PAIRS):
        first, second = "D%d" % (2 * k + 1), "D%d" % (2 * k + 2)
        d.net("CP%d" % a, "%s.A" % first, "%s.K" % second)
        d.net("CP%d" % c, "%s.K" % first, "%s.A" % second)

    # ---- planes and keep-outs ---------------------------------------------
    # GND is a solid plane on In1.Cu.  In2.Cu is the V2V8 plane AND a third
    # routing layer ("routable" plane): every V2V8 pad drops into it through a
    # via, signals that do not fit on the outer layers run across it and the
    # fill flows around them.  The other supplies are tracks.
    d.add_plane("GND", "In1.Cu")
    d.add_plane("V2V8", "In2.Cu", routable=True)
    d.add_body_keepout("U4")                 # no copper on F.Cu under the IMU body
    d.add_body_keepout("U5")                 # ... and under the inclinometer body
    bx, by, bw, bh = BATTERY_BODY
    d.add_keepout(RoundedPolygon.rect(bx, by, bw, bh), layers=("F.Cu",),
                  name="battery_body", tracks=False, vias=False, copper=False,
                  footprints=True)           # placement only: no top-side parts
    for i, (x, y) in enumerate(POST_FEET, start=1):
        d.add_placement_keepout(RoundedPolygon.rect(x, y, POST_FOOT_SIZE, POST_FOOT_SIZE),
                                side="top", name="post_foot_%d" % i)
    for ref, margin in FINE_AREAS:           # (none in the demo, see FINE_AREAS)
        d.add_fine_area(ref, margin=margin)
    for x, y in FIDUCIALS_TOP:
        d.add_fiducial(x, y)
    for x, y in FIDUCIALS_BOTTOM:
        d.add_fiducial(x, y, side=BOTTOM)
    for ref, x in (("U2", -CAMERA_X), ("U3", CAMERA_X)):
        d.add_height_limit(RoundedPolygon.rect(x, (HOOD_Y0 + FLAT_Y) / 2.0, 2.0 * HOOD_HALF_W,
                                               FLAT_Y - HOOD_Y0),
                           HOOD_MAX_HEIGHT, side="top", exempt=(ref,),
                           name="camera_hood_%s" % ref)
    return d


if __name__ == "__main__":
    from gleda import checks
    design = demo_design()
    print(design)
    print(checks.run_checks(design).text())
