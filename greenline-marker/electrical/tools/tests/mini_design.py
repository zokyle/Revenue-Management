"""Small but complete design used by the core tests (and reusable by others).

Round 30 mm 4-layer board with

* a 6 mm circular cutout, an edge notch, a slot and two NPTH holes
* library footprints (0402 R/C/LED, LGA-14, DFN regulator, 10-pin FPC) and
  custom footprints (castellated module, test pads, battery tabs)
* parts on both sides, rotated
* GND plane on In1.Cu, +3V0 plane on In2.Cu, a keep-out under the antenna end
  of the module

It is electrically meaningful enough to pass the ERC-style checks with zero
errors.  ``mini_design()`` returns a fresh :class:`gleda.model.Design`.
"""
from gleda.model import (Design, Outline, Circle, RoundedPolygon, Part, two_pin, n_pin,
                         BOTTOM)
from gleda import footprints as F

R0402 = "Resistor_SMD:R_0402_1005Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
LED0402 = "LED_SMD:LED_0402_1005Metric"
LGA14 = "Package_LGA:Bosch_LGA-14_3x2.5mm_P0.5mm"
SOT235 = "Package_TO_SOT_SMD:SOT-23-5"
FPC10 = "Connector_FFC-FPC:Hirose_FH12-10S-0.5SH_1x10-1MP_P0.50mm_Horizontal"


def module_footprint():
    """7 x 9 mm castellated module, 8 pads left/right + 4 bottom, 2 GND pads under."""
    return F.castellated_module(
        "MiniModule_7x9", 7.0, 9.0, pitch=0.8, left=8, bottom=4, right=8,
        pad_w=0.4, inset=0.6, overhang=0.3,
        under_pads=[("21", -1.0, 0.0, 1.0, 1.0), ("21", 1.0, 0.0, 1.0, 1.0)],
        height=1.8)


def _cap(ref, value, x, y, rot=0.0, side="top"):
    return Part(ref, value, C0402, pins=two_pin(), mpn="GRM155R61A105KE15D",
                manufacturer="Murata", distributor="Digi-Key",
                distributor_pn="490-3890-1-ND", unit_price=0.10, x=x, y=y, rotation=rot,
                side=side, height_mm=0.55, group="power", description="MLCC 0402")


def _res(ref, value, x, y, rot=0.0, side="top", group="main"):
    return Part(ref, value, R0402, pins=two_pin(), mpn="RC0402FR-0710KL",
                manufacturer="Yageo", distributor="Digi-Key",
                distributor_pn="311-10.0KLRCT-ND", unit_price=0.10, x=x, y=y,
                rotation=rot, side=side, height_mm=0.4, group=group,
                description="Resistor 0402 1%")


def mini_design(name="mini"):
    outline = Outline(Circle(0.0, 0.0, 15.0))
    outline.add_cutout(Circle(8.0, 0.0, 3.0))                         # internal cutout
    outline.add_notch(RoundedPolygon.rect(0.0, -15.0, 3.0, 2.0, 0.4))  # edge notch
    outline.add_slot(-6.0, -11.0, -4.0, -11.0, 0.8)                    # routed slot
    outline.add_hole(-11.5, 5.0, 1.2)
    outline.add_hole(11.0, 7.5, 1.2)
    d = Design(name, outline, layers=4, board_thickness=0.8, title="gleda mini design",
               revision="A", company="GreenLine")

    mod_pins = {
        "GND": (("1", "8", "13", "20", "21"), "power_in"),
        "VDD": ("2", "power_in"),
        "SCK": ("3", "output"), "MOSI": ("4", "output"), "MISO": ("5", "input"),
        "CS": ("6", "output"), "INT": ("7", "input"),
        "D0": ("9", "bidir"), "D1": ("10", "bidir"), "D2": ("11", "bidir"),
        "D3": ("12", "bidir"),
        "LED1": ("14", "output"), "LED2": ("15", "output"),
        "SWDIO": ("16", "bidir"), "SWCLK": ("17", "input"),
        "EN": ("18", "input"), "NC": ("19", "nc"),
    }
    d.add(Part("U1", "MiniModule", module_footprint(), pins=mod_pins, mpn="MINI-MOD-1",
               manufacturer="Example RF", distributor="Digi-Key", distributor_pn="0000-MM1-ND",
               unit_price=6.5, x=-3.5, y=1.5, rotation=0.0, height_mm=1.8, group="mcu",
               description="BLE module (stand-in)"))
    imu_pins = {
        "SDO": ("1", "output"), "ASDX": ("2", "nc"), "ASCX": ("3", "nc"),
        "INT1": ("4", "output"), "VDDIO": ("5", "power_in"), "GNDIO": ("6", "power_in"),
        "GND": ("7", "power_in"), "VDD": ("8", "power_in"), "INT2": ("9", "nc"),
        "OCS": ("10", "nc"), "OSDO": ("11", "nc"), "CSB": ("12", "input"),
        "SCX": ("13", "input"), "SDX": ("14", "input"),
    }
    d.add(Part("U2", "BMI270", LGA14, pins=imu_pins, mpn="BMI270", manufacturer="Bosch",
               distributor="Digi-Key", distributor_pn="828-BMI270CT-ND", unit_price=4.2,
               x=4.0, y=8.5, rotation=90.0, side=BOTTOM, height_mm=0.83, group="sensor",
               description="6-axis IMU"))
    reg_pins = {"VIN": ("1", "power_in"), "GND": ("2", "power_in"), "EN": ("3", "input"),
                "NC": ("4", "nc"), "VOUT": ("5", "power_out")}
    d.add(Part("U3", "LDO 3V0", SOT235, pins=reg_pins, mpn="TLV75530PDBVR",
               manufacturer="Texas Instruments", distributor="Digi-Key",
               distributor_pn="296-TLV75530PDBVRCT-ND", unit_price=0.4,
               x=3.0, y=-8.5, rotation=180.0, side=BOTTOM, height_mm=1.45, group="power",
               description="LDO regulator 3.0 V"))
    d.add(Part("J1", "FPC 10", FPC10, pins=n_pin(10, "passive", {"MP": ("MP", "passive")}),
               mpn="FH12-10S-0.5SH(55)", manufacturer="Hirose", distributor="Digi-Key",
               distributor_pn="HFJ110CT-ND", unit_price=0.9, x=-4.0, y=7.0, rotation=180.0,
               side=BOTTOM, height_mm=2.0, group="sensor", description="FPC connector"))
    d.add(_cap("C1", "1u", -9.3, 4.0, 90.0), _cap("C2", "100n", 3.0, 11.3, 0.0, BOTTOM),
          _cap("C3", "1u", 7.5, -8.5, 90.0, BOTTOM), _cap("C4", "1u", -1.5, -8.5, 90.0, BOTTOM),
          _cap("C5", "100n", 7.0, 10.3, 0.0, BOTTOM))
    d.add(_res("R1", "1k", 1.5, -6.5, 0.0), _res("R2", "1k", 1.5, -8.0, 0.0),
          _res("R3", "10k", -9.3, 0.5, 90.0))
    for ref, x, y in (("D1", 4.5, -6.5), ("D2", 4.5, -8.0)):
        d.add(Part(ref, "LED", LED0402, pins={"K": ("1", "passive"), "A": ("2", "passive")},
                   mpn="LTST-C281KGKT", manufacturer="Lite-On", distributor="Digi-Key",
                   distributor_pn="160-1447-1-ND", unit_price=0.3, x=x, y=y, rotation=0.0,
                   height_mm=0.35, group="main", description="LED 0402"))
    tp = F.test_pad(1.0)
    for i, (x, y) in enumerate(((-8.0, -6.0), (-6.5, -7.5), (-9.5, -4.5)), start=1):
        d.add(Part("TP%d" % i, "TP", tp, pins={"1": "1"}, x=x, y=y, side=BOTTOM,
                   in_bom=False, height_mm=0.0, group="mcu", description="pogo pad"))
    bt = F.battery_tab(2.0, 3.0)
    d.add(Part("BT1", "BAT+", bt, pins={"1": "1"}, x=-10.5, y=-2.0, side=BOTTOM,
               in_bom=False, height_mm=0.0, group="power", description="battery + tab"))
    d.add(Part("BT2", "BAT-", bt, pins={"1": "1"}, x=11.5, y=-5.5, side=BOTTOM,
               in_bom=False, height_mm=0.0, group="power", description="battery - tab"))

    d.net("GND", "U1.GND", "U2.GND", "U2.GNDIO", "U3.GND", "J1.1", "J1.MP", "C1.2", "C2.2",
          "C3.2", "C4.2", "C5.2", "BT2.1", "TP3.1", "D1.K", "D2.K", netclass="Power")
    d.net("VBAT", "BT1.1", "U3.VIN", "U3.EN", "C3.1", netclass="Power", power_flag=True)
    d.net("+3V0", "U3.VOUT", "U1.VDD", "U2.VDD", "U2.VDDIO", "J1.2", "C1.1", "C2.1", "C4.1",
          "C5.1", "R3.1", netclass="Power")
    d.net("SCK", "U1.SCK", "U2.SCX", "J1.3")
    d.net("MOSI", "U1.MOSI", "U2.SDX", "J1.4")
    d.net("MISO", "U1.MISO", "U2.SDO", "J1.5")
    d.net("IMU_CS", "U1.CS", "U2.CSB")
    d.net("IMU_INT", "U1.INT", "U2.INT1")
    for i in range(4):
        d.net("D%d" % i, "U1.D%d" % i, "J1.%d" % (6 + i))
    d.net("CAM_EN", "U1.EN", "R3.2", "J1.10")
    d.net("LED1", "U1.LED1", "R1.1")
    d.net("LED2", "U1.LED2", "R2.1")
    d.net("LED1_A", "R1.2", "D1.A")
    d.net("LED2_A", "R2.2", "D2.A")
    d.net("SWDIO", "U1.SWDIO", "TP1.1")
    d.net("SWCLK", "U1.SWCLK", "TP2.1")

    d.add_plane("GND", "In1.Cu")
    d.add_plane("+3V0", "In2.Cu")
    # antenna keep-out at the top end of the module: no copper on any layer
    d.add_keepout(RoundedPolygon.rect(-3.5, 9.5, 7.0, 3.0), name="antenna",
                  tracks=True, vias=True, copper=True)
    # no components on the bottom side under the battery contact area
    d.add_keepout(Circle(-11.0, -6.5, 1.5), layers=("B.Cu",), name="spring",
                  tracks=False, vias=False, copper=False, footprints=True)
    return d
