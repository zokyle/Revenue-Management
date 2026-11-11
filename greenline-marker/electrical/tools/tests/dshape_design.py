"""D-shaped reference design for the core tests: a reduced stand-in for the
GreenLine GL-1 board that exercises everything the real board needs from the
core of the toolchain.

* outline: circle r = 21.2 mm clipped by a chord at y = +17.3 mm
  (:meth:`gleda.model.PathShape.d_shape`), 4 layers, 0.8 mm
* rule set :data:`gleda.model.US_4L_FINE` (board minimums 0.09 / 0.09 mm) with
  the net classes Default (0.15 / 0.127), Power (0.30 / 0.127) and Fine
  (0.09 / 0.09, only on the nets of the inner camera balls)
* top side: LQFP-64 MCU (library), two 25-ball 0.5 mm-pitch camera BGAs
  (custom, 0.23 mm pads with a 0.09 mm clearance override) sharing an
  11-signal bus, LGA-14 IMU (library), LGA-16 inclinometer (custom),
  SOT-23 regulators / charger, 10-pin FPC connector, crystal, 0402 passives,
  two battery solder pads
* bottom side: 16 x 0402 LEDs on a 5.2 mm radius about (0, -4) charlieplexed
  on 5 lines, a 2-pad photodiode, a row of seven bare 1.8 mm contact pads
* GND plane on In1.Cu, +3V0 plane on In2.Cu
* keep-outs: no copper on F.Cu under the IMU and inclinometer bodies, no
  top-side parts under the battery body (placement only)
* vias tented on the bottom side only

The pin maps are illustrative stand-ins, NOT the real device pin-outs.  The
design passes the ERC-style checks with zero errors.  ``dshape_design()``
returns a fresh :class:`gleda.model.Design`.
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
SOT23 = "Package_TO_SOT_SMD:SOT-23"
SOT235 = "Package_TO_SOT_SMD:SOT-23-5"
FPC10 = "Connector_FFC-FPC:Hirose_FH12-10S-0.5SH_1x10-1MP_P0.50mm_Horizontal"
XTAL = "Crystal:Crystal_SMD_3215-2Pin_3.2x1.5mm"

BOARD_RADIUS = 21.2
FLAT_Y = 17.3
LED_RING = (0.0, -4.0, 5.2)          # centre x, centre y, radius
PAD_ROW_Y = -17.0

#: the 11 signals of the camera bus shared by both cameras
CAM_BUS = ["CAM_D%d" % i for i in range(8)] + ["CAM_PCLK", "CAM_HREF", "CAM_VSYNC"]

#: camera stand-in ball map: ball -> (pin name, electrical type)
CAM_BALLS = {
    # inner 3 x 3 (needs the fine class to escape between the outer balls)
    "B2": ("D0", "bidir"), "B3": ("D1", "bidir"), "B4": ("D2", "bidir"),
    "C2": ("D3", "bidir"), "C3": ("D4", "bidir"), "C4": ("D5", "bidir"),
    "D2": ("D6", "bidir"), "D3": ("D7", "bidir"), "D4": ("HREF", "bidir"),
    # outer ring
    "A1": ("NC1", "nc"), "A2": ("PCLK", "bidir"), "A3": ("VSYNC", "bidir"),
    "A4": ("XVCLK", "input"), "A5": ("NC2", "nc"),
    "B1": ("SCL", "input"), "B5": ("SDA", "bidir"),
    "C1": ("PWDN", "input"), "C5": ("AVDD", "power_in"),
    "D1": ("DOVDD", "power_in"), "D5": ("DVDD", "power_out"),
    "E1": ("NC3", "nc"), "E2": ("GND1", "power_in"), "E3": ("GND2", "power_in"),
    "E4": ("GND3", "power_in"), "E5": ("NC4", "nc"),
}
INNER_BALL_PINS = {"D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "HREF"}


def camera_footprint():
    """25-ball 5 x 5, 0.5 mm pitch.  Pad 0.23 mm with a 0.09 mm clearance
    override: 0.5 - 0.23 = 0.27 = 0.09 track + 2 x 0.09 clearance."""
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


def mcu_pins():
    """Stand-in pin map for the LQFP-64 (pad numbers are real, functions are
    illustrative)."""
    named = {
        "VDD": (("1", "19", "32", "48", "64"), "power_in"),
        "VSS": (("18", "31", "47", "63"), "power_in"),
        "SPI_SCK": ("2", "output"), "SPI_MOSI": ("3", "output"), "SPI_MISO": ("4", "input"),
        "CS_IMU": ("5", "output"), "CS_INC": ("6", "output"), "IMU_INT": ("7", "input"),
        "OSC32_IN": ("8", "input"), "OSC32_OUT": ("9", "output"),
        "LCD_SCLK": ("20", "output"), "LCD_SI": ("21", "output"), "LCD_SCS": ("22", "output"),
        "LCD_EXTCOMIN": ("23", "output"), "LCD_DISP": ("24", "output"),
        "CP1": ("25", "bidir"), "CP2": ("26", "bidir"), "CP3": ("27", "bidir"),
        "CP4": ("28", "bidir"), "CP5": ("29", "bidir"), "PD_IN": ("30", "input"),
        "SWDIO": ("34", "bidir"), "SWCLK": ("35", "input"), "NRST": ("36", "input"),
        "USB_DM": ("37", "bidir"), "USB_DP": ("38", "bidir"), "VBUS_SENSE": ("39", "input"),
        "CHG_STAT": ("40", "input"),
        "CAM_EN": ("44", "output"), "PWDN_R": ("45", "output"), "PWDN_L": ("46", "output"),
        "SDA": ("49", "bidir"),
        "D0": ("50", "bidir"), "D1": ("51", "bidir"), "D2": ("52", "bidir"),
        "D3": ("53", "bidir"), "D4": ("54", "bidir"), "D5": ("55", "bidir"),
        "D6": ("56", "bidir"), "D7": ("57", "bidir"),
        "PCLK": ("58", "bidir"), "HREF": ("59", "bidir"), "VSYNC": ("60", "bidir"),
        "XVCLK": ("61", "output"), "SCL_L": ("62", "output"), "SCL_R": ("33", "output"),
    }
    used = set()
    for pads, _etype in named.values():
        used.update([pads] if isinstance(pads, str) else pads)
    for n in range(1, 65):
        if str(n) not in used:
            named["NC%d" % n] = (str(n), "nc")
    return named


def _cap(ref, value, x, y, rot=0.0, group="power"):
    return Part(ref, value, C0402, pins=two_pin(), mpn="GRM155R61A105KE15D",
                manufacturer="Murata", distributor="Digi-Key",
                distributor_pn="490-3890-1-ND", unit_price=0.10, x=x, y=y, rotation=rot,
                height_mm=0.55, group=group, description="MLCC 0402")


def _res(ref, value, x, y, rot=0.0, group="main"):
    return Part(ref, value, R0402, pins=two_pin(), mpn="RC0402FR-0710KL",
                manufacturer="Yageo", distributor="Digi-Key",
                distributor_pn="311-10.0KLRCT-ND", unit_price=0.10, x=x, y=y,
                rotation=rot, height_mm=0.4, group=group, description="Resistor 0402 1%")


def led_ring_positions(count=16):
    """(x, y, rotation) of the grain LEDs: tangential, evenly spaced."""
    cx, cy, r = LED_RING
    out = []
    for i in range(count):
        a = 360.0 * i / count
        out.append((round(cx + r * math.cos(math.radians(a)), 4),
                    round(cy + r * math.sin(math.radians(a)), 4), (a + 90.0) % 360.0))
    return out


#: charlieplex wiring of LED pairs: (line of anode, line of cathode), the
#: second LED of each pair is antiparallel
CHARLIE_PAIRS = [(1, 2), (2, 3), (3, 4), (4, 5), (5, 1), (1, 3), (2, 4), (3, 5)]


def dshape_design(name="dshape"):
    d = Design(name, Outline(PathShape.d_shape(BOARD_RADIUS, FLAT_Y)), layers=4,
               rules=US_4L_FINE, board_thickness=0.8, title="gleda D-shape core proof",
               revision="A", company="GreenLine")
    d.add_netclass("Fine", track_width=0.09, clearance=0.09,
                   description="escape of the inner balls of the 0.5 mm-pitch BGAs")
    d.via_tenting = "bottom"

    # ---- top side ---------------------------------------------------------
    d.add(Part("U1", "MCU LQFP-64", LQFP64, pins=mcu_pins(), mpn="STM32U585RIT6",
               manufacturer="STMicroelectronics", distributor="Digi-Key",
               distributor_pn="497-STM32U585RIT6-ND", unit_price=9.5, x=0.0, y=6.9,
               height_mm=1.6, group="mcu", description="MCU (stand-in pin map)"))
    cam = camera_footprint()
    cam_pins = {pin: (ball, etype) for ball, (pin, etype) in CAM_BALLS.items()}
    for ref, x in (("U2", -10.2), ("U3", 10.2)):
        d.add(Part(ref, "Camera cube", cam, pins=cam_pins, mpn="OVM7692-RYAA",
                   manufacturer="OmniVision", distributor="Digi-Key",
                   distributor_pn="884-1027-1-ND", unit_price=6.0, x=x, y=15.6,
                   height_mm=2.76, group="camera", description="camera (stand-in ball map)"))
    # SDO / MISO are tri-state outputs sharing one line: modelled as "bidir"
    imu_pins = {"SDO": ("1", "bidir"), "SDX": ("2", "passive"), "SCX": ("3", "passive"),
                "INT1": ("4", "output"), "VDDIO": ("5", "power_in"), "GND1": ("6", "power_in"),
                "GND2": ("7", "power_in"), "VDD": ("8", "power_in"), "INT2": ("9", "nc"),
                "OCS": ("10", "nc"), "OSDO": ("11", "nc"), "CS": ("12", "input"),
                "SCL": ("13", "input"), "SDA": ("14", "input")}
    d.add(Part("U4", "IMU LGA-14", LGA14, pins=imu_pins, mpn="LSM6DSV16XTR",
               manufacturer="STMicroelectronics", distributor="Digi-Key",
               distributor_pn="497-LSM6DSV16XTRCT-ND", unit_price=4.5, x=-11.0, y=6.0,
               height_mm=0.86, group="sensor", description="6-axis IMU (stand-in pin map)"))
    inc_pins = {"VDD": ("1", "power_in"), "VDDIO": ("2", "power_in"), "GND1": ("3", "power_in"),
                "GND2": ("4", "power_in"), "CS": ("5", "input"), "SCK": ("6", "input"),
                "MOSI": ("7", "input"), "MISO": ("8", "bidir")}
    for n in range(9, 17):
        inc_pins["NC%d" % n] = (str(n), "nc")
    d.add(Part("U5", "Inclinometer LGA-16", inclinometer_footprint(), pins=inc_pins,
               mpn="IIS2ICLXTR", manufacturer="STMicroelectronics", distributor="Digi-Key",
               distributor_pn="497-IIS2ICLXTRCT-ND", unit_price=18.0, x=12.0, y=6.0,
               height_mm=1.7, group="sensor", description="inclinometer (stand-in pin map)"))
    d.add(Part("U7", "LDO 3V0", SOT23, pins={"GND": ("1", "power_in"),
                                             "VOUT": ("2", "power_out"),
                                             "VIN": ("3", "power_in")},
               mpn="MCP1700T-3002E/TT", manufacturer="Microchip", distributor="Digi-Key",
               distributor_pn="MCP1700T3002ETTCT-ND", unit_price=0.45, x=10.5, y=-13.5,
               height_mm=1.2, group="power", description="LDO 3.0 V"))
    d.add(Part("U8", "LDO 2V8", SOT235, pins={"VIN": ("1", "power_in"), "GND": ("2", "power_in"),
                                              "EN": ("3", "input"), "NC": ("4", "nc"),
                                              "VOUT": ("5", "power_out")},
               mpn="LP5907MFX-2.8/NOPB", manufacturer="Texas Instruments",
               distributor="Digi-Key", distributor_pn="296-38557-1-ND", unit_price=0.6,
               x=0.0, y=15.45, height_mm=1.45, group="power", description="LDO 2.8 V"))
    d.add(Part("U9", "Charger", SOT235, pins={"STAT": ("1", "open_drain"),
                                              "VSS": ("2", "power_in"),
                                              "VBAT": ("3", "power_out"),
                                              "VDD": ("4", "power_in"),
                                              "PROG": ("5", "passive")},
               mpn="MCP73831T-2ACI/OT", manufacturer="Microchip", distributor="Digi-Key",
               distributor_pn="MCP73831T-2ACI/OTCT-ND", unit_price=0.7, x=-10.5, y=-13.5,
               height_mm=1.45, group="power", description="Li-Po charger"))
    d.add(Part("J1", "LCD FPC 10", FPC10, pins=n_pin(10, "passive", {"MP": ("MP", "passive")}),
               mpn="FH12-10S-0.5SH(55)", manufacturer="Hirose", distributor="Digi-Key",
               distributor_pn="HFJ110CT-ND", unit_price=0.9, x=0.0, y=-13.9, rotation=0.0,
               height_mm=1.2, group="display", description="LCD FPC connector"))
    d.add(Part("Y1", "32.768k", XTAL, pins=two_pin(), mpn="ABS07-32.768KHZ-T",
               manufacturer="Abracon", distributor="Digi-Key", distributor_pn="535-9542-1-ND",
               unit_price=0.6, x=8.9, y=12.2, height_mm=0.9, group="mcu",
               description="32.768 kHz crystal 3215"))
    bt = F.battery_tab(1.5, 2.5)
    d.add(Part("BT1", "BAT+", bt, pins={"1": "1"}, x=-14.6, y=-11.6, in_bom=False,
               height_mm=0.0, group="power", description="battery + solder pad"))
    d.add(Part("BT2", "BAT-", bt, pins={"1": "1"}, x=14.6, y=-11.6, in_bom=False,
               height_mm=0.0, group="power", description="battery - solder pad"))
    d.add(_cap("C1", "100n", -7.3, 10.5, 90.0, "mcu"), _cap("C2", "100n", -7.3, 3.0, 90.0, "mcu"),
          _cap("C3", "100n", 7.3, 9.0, 90.0, "mcu"), _cap("C4", "4u7", 7.3, 3.0, 90.0, "mcu"),
          _cap("C5", "1u", 4.0, 14.6, 0.0), _cap("C6", "1u", 4.0, 16.0, 0.0),
          _cap("C7", "1u", -14.3, 13.9, 90.0, "camera"),
          _cap("C8", "1u", 14.3, 13.9, 90.0, "camera"),
          _cap("C9", "1u", -7.4, -12.6, 90.0), _cap("C10", "1u", 7.4, -12.6, 90.0),
          _cap("C11", "1u", 13.0, -13.6, 90.0), _cap("C12", "100n", -14.2, 6.0, 90.0, "sensor"),
          _cap("C13", "100n", 16.0, 6.0, 90.0, "sensor"),
          _cap("C14", "12p", 11.6, 12.2, 90.0, "mcu"), _cap("C15", "12p", 9.0, 10.4, 0.0, "mcu"),
          _cap("C16", "100n", -7.2, 15.3, 90.0, "camera"),
          _cap("C17", "100n", 7.2, 15.3, 90.0, "camera"))
    for i in range(5):                                  # charlieplex series resistors
        d.add(_res("R%d" % (i + 1), "68R", -17.0 + 2.0 * i, 2.2, 0.0, "grain"))
    d.add(_res("R6", "2k2", -5.2, 14.6, 0.0, "camera"), _res("R7", "2k2", -5.2, 16.0, 0.0, "camera"),
          _res("R8", "49k9", -7.4, -15.0, 90.0, "power"), _res("R9", "100k", 13.0, 2.2, 0.0, "power"),
          _res("R10", "2k2", -2.6, 16.0, 90.0, "camera"))

    # ---- bottom side ------------------------------------------------------
    for i, (x, y, rot) in enumerate(led_ring_positions(), start=1):
        d.add(Part("D%d" % i, "LED red" if i % 2 else "LED NIR", LED0402,
                   pins={"K": ("1", "passive"), "A": ("2", "passive")},
                   mpn="APHHS1005SURCK" if i % 2 else "APHHS1005F3C",
                   manufacturer="Kingbright", distributor="Digi-Key",
                   distributor_pn="754-1104-1-ND", unit_price=0.35, x=x, y=y, rotation=rot,
                   side=BOTTOM, height_mm=0.45, group="grain", description="grain LED 0402"))
    d.add(Part("PD1", "Photodiode", photodiode_footprint(),
               pins={"A": ("A", "passive"), "K": ("K", "passive")}, mpn="VEMD5510C",
               manufacturer="Vishay", distributor="Digi-Key", distributor_pn="VEMD5510CCT-ND",
               unit_price=1.2, x=LED_RING[0], y=LED_RING[1], side=BOTTOM, height_mm=0.48,
               group="grain", description="photodiode (stand-in land pattern)"))
    d.add(Part("J2", "Cradle pads", contact_row_footprint(), pins=n_pin(7), x=0.0,
               y=PAD_ROW_Y, side=BOTTOM, in_bom=False, height_mm=0.0, group="service",
               description="VBUS D- D+ GND SWDIO SWCLK NRST"))

    # ---- nets -------------------------------------------------------------
    d.net("GND", "U1.VSS", "U2.GND1", "U2.GND2", "U2.GND3", "U3.GND1", "U3.GND2", "U3.GND3",
          "U4.GND1", "U4.GND2", "U4.SDX", "U4.SCX", "U5.GND1", "U5.GND2", "U7.GND", "U8.GND",
          "U9.VSS", "J1.9", "J1.10", "J1.MP", "BT2.1", "J2.4", "PD1.A",
          "C1.2", "C2.2", "C3.2", "C4.2", "C5.2", "C6.2", "C7.2", "C8.2", "C9.2", "C10.2",
          "C11.2", "C12.2", "C13.2", "C14.2", "C15.2", "C16.2", "C17.2", "R9.2", netclass="Power")
    d.net("VBUS", "J2.1", "U9.VDD", "C9.1", "U1.VBUS_SENSE", netclass="Power",
          power_flag=True)
    d.net("VBAT", "BT1.1", "U9.VBAT", "U7.VIN", "U8.VIN", "C10.1", "C5.1", netclass="Power")
    d.net("+3V0", "U7.VOUT", "U1.VDD", "U4.VDD", "U4.VDDIO", "U5.VDD", "U5.VDDIO", "J1.6",
          "J1.7", "J1.8", "C1.1", "C2.1", "C3.1", "C4.1", "C11.1", "C12.1", "C13.1",
          netclass="Power")
    d.net("V2V8_CAM", "U8.VOUT", "U2.AVDD", "U2.DOVDD", "U3.AVDD", "U3.DOVDD", "C6.1",
          "C16.1", "C17.1", "R6.1", "R7.1", "R10.1", netclass="Power")
    d.net("CAM_EN", "U1.CAM_EN", "U8.EN", "R9.1")
    d.net("CAM_L_DVDD", "U2.DVDD", "C7.1")
    d.net("CAM_R_DVDD", "U3.DVDD", "C8.1")
    for i in range(8):
        d.net("CAM_D%d" % i, "U1.D%d" % i, "U2.D%d" % i, "U3.D%d" % i, netclass="Fine")
    d.net("CAM_HREF", "U1.HREF", "U2.HREF", "U3.HREF", netclass="Fine")
    d.net("CAM_PCLK", "U1.PCLK", "U2.PCLK", "U3.PCLK")
    d.net("CAM_VSYNC", "U1.VSYNC", "U2.VSYNC", "U3.VSYNC")
    d.net("CAM_XVCLK", "U1.XVCLK", "U2.XVCLK", "U3.XVCLK")
    d.net("CAM_SDA", "U1.SDA", "U2.SDA", "U3.SDA", "R10.2")
    d.net("CAM_SCL_L", "U1.SCL_L", "U2.SCL", "R6.2")
    d.net("CAM_SCL_R", "U1.SCL_R", "U3.SCL", "R7.2")
    d.net("CAM_PWDN_L", "U1.PWDN_L", "U2.PWDN")
    d.net("CAM_PWDN_R", "U1.PWDN_R", "U3.PWDN")
    d.net("SPI_SCK", "U1.SPI_SCK", "U4.SCL", "U5.SCK")
    d.net("SPI_MOSI", "U1.SPI_MOSI", "U4.SDA", "U5.MOSI")
    d.net("SPI_MISO", "U1.SPI_MISO", "U4.SDO", "U5.MISO")
    d.net("CS_IMU", "U1.CS_IMU", "U4.CS")
    d.net("CS_INC", "U1.CS_INC", "U5.CS")
    d.net("IMU_INT", "U1.IMU_INT", "U4.INT1")
    d.net("OSC32_IN", "U1.OSC32_IN", "Y1.1", "C14.1")
    d.net("OSC32_OUT", "U1.OSC32_OUT", "Y1.2", "C15.1")
    for pin, lcd in (("LCD_SCLK", 1), ("LCD_SI", 2), ("LCD_SCS", 3), ("LCD_EXTCOMIN", 4),
                     ("LCD_DISP", 5)):
        d.net(pin, "U1.%s" % pin, "J1.%d" % lcd)
    for i in range(1, 6):
        d.net("CP%d_MCU" % i, "U1.CP%d" % i, "R%d.1" % i)
        d.net("CP%d" % i, "R%d.2" % i)
    for k, (a, c) in enumerate(CHARLIE_PAIRS):
        first, second = "D%d" % (2 * k + 1), "D%d" % (2 * k + 2)
        d.net("CP%d" % a, "%s.A" % first, "%s.K" % second)
        d.net("CP%d" % c, "%s.K" % first, "%s.A" % second)
    d.net("PD_K", "PD1.K", "U1.PD_IN")
    d.net("CHG_STAT", "U9.STAT", "U1.CHG_STAT")
    d.net("CHG_PROG", "U9.PROG", "R8.1")
    d.net("GND", "R8.2")
    d.net("USB_DM", "J2.2", "U1.USB_DM")
    d.net("USB_DP", "J2.3", "U1.USB_DP")
    d.net("SWDIO", "J2.5", "U1.SWDIO")
    d.net("SWCLK", "J2.6", "U1.SWCLK")
    d.net("NRST", "J2.7", "U1.NRST")

    # ---- planes and keep-outs ---------------------------------------------
    d.add_plane("GND", "In1.Cu")
    d.add_plane("+3V0", "In2.Cu")
    d.add_body_keepout("U4")                 # no copper on F.Cu under the IMU body
    d.add_body_keepout("U5")                 # ... and under the inclinometer body
    d.add_keepout(RoundedPolygon.rect(0.0, -5.2, 34.0, 10.0), layers=("F.Cu",),
                  name="battery_body", tracks=False, vias=False, copper=False,
                  footprints=True)           # placement only: no top-side parts
    return d
