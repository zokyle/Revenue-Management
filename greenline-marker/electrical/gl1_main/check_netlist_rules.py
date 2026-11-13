#!/usr/bin/python3
"""DESIGN_SPEC section 4, rule by rule, against the GL-1 main-board netlist.

    /usr/bin/python3 -B electrical/gl1_main/check_netlist_rules.py [--markdown FILE]

Every row is one sentence of the specification (rail table, the rules, the
PCB paragraph), the place in the netlist that implements it, and a test that
is evaluated on the design object of ``gl1_main_design.py``: connectivity,
part values, order codes, rule areas.  The toolchain's own checks
(``gleda.checks``) prove that the netlist is consistent; this file proves
that it is the netlist the specification asks for.  Rows marked DEVIATION
pass their test but implement the sentence differently from its letter;
``NETLIST_NOTES.md`` explains each.  Nothing here is a hardware test.

Exit status 0 only if every row passes.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.normpath(os.path.join(HERE, "..", "tools"))
for _p in (TOOLS, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import gl1_main_design as G                    # noqa: E402
from check_pinmap import Netlist, ohms         # noqa: E402
from gleda import geometry                     # noqa: E402
from gleda.model import BOTTOM, TOP            # noqa: E402


def rules(design):
    """[(id, what the spec says, where it is in the netlist, passed, note)]"""
    nl = Netlist(design)
    P = design.parts_by_ref
    Y = G.Y
    out = []

    def row(rid, spec, where, ok, note=""):
        out.append((rid, spec, where, bool(ok), note))

    def net(node):
        ref, pin = node.split(".", 1)
        return nl.net(ref, pin)

    def on(name, *nodes):
        return all(net(n) == name for n in nodes)

    def two(ref, a, b, value=None):
        """two-pin part ``ref`` between nets a and b (either way round), optionally of a value"""
        p = P.get(ref)
        if p is None or len(p.pins) != 2:
            return False
        nets = sorted(nl.net(ref, pin) or "" for pin in p.pins)
        return nets == sorted((a, b)) and (value is None or p.value == value)

    def diode(ref, anode, cathode):
        return ref in P and nl.net(ref, "A") == anode and nl.net(ref, "K") == cathode

    def caps(name, value=None):
        """capacitors from net ``name`` to GND"""
        return sorted(ref for ref, p in P.items() if p.ref_prefix == "C"
                      and two(ref, name, "GND") and (value is None or p.value == value))

    def mpn(ref):
        return P[ref].mpn if ref in P else None

    def only(name, *nodes):
        return sorted("%s.%s" % n for n in nl.nodes(name)) == sorted(nodes)

    # ------------------------------------------------------------------ rail table
    row("rail VBUS a", "VBUS: cradle pad, 5 V; USBLC6-2SC6 clamps VBUS, D+, D-",
        "net VBUS = J2.VBUS (pad 1), U10.VBUS; USB_DM / USB_DP through U10 pins 1+6 / 3+4",
        on("VBUS", "J2.VBUS", "U10.VBUS") and mpn("U10") == "USBLC6-2SC6"
        and on("USB_DM", "U10.IO1A", "U10.IO1B", "J2.DM", "U1.PA11")
        and on("USB_DP", "U10.IO2A", "U10.IO2B", "J2.DP", "U1.PA12") and on("GND", "U10.GND"))
    row("rail VBUS b", "Series Schottky from pad to charger",
        "D17 (B0530WS): anode VBUS, cathode VBUS_D; U9.VDD on VBUS_D",
        diode("D17", "VBUS", "VBUS_D") and on("VBUS_D", "U9.VDD") and mpn("D17") == "B0530WS-7-F")
    row("rail VBUS c", "VBUS loads: MCP73831 VDD, VBUS-sense divider",
        "U9.VDD, R15 / R16 (82k : 100k) from VBUS_D to VBUS_SENSE (PC13) - after the Schottky",
        two("R15", "VBUS_D", "VBUS_SENSE", "82k") and two("R16", "VBUS_SENSE", "GND", "100k")
        and on("VBUS_SENSE", "U1.PC13"), "divider values are this netlist's choice (not in the spec)")
    row("rail VBAT a", "VBAT: cell + PCM; loads MCP1700-2.8 in, LP5907 in, battery divider",
        "net VBAT = BT1, U9.VBAT, U7.VIN, U8.IN, R17",
        on("VBAT", "BT1.1", "U9.VBAT", "U7.VIN", "U8.IN", "R17.1") and on("GND", "BT2.1"))
    row("rail VBAT b", "2 x 1 Mohm divider with 100 nF to an ADC pin",
        "R17 / R18 1M, C29 100n on VBAT_SENSE = PA2 (ADC1_IN7)",
        two("R17", "VBAT", "VBAT_SENSE", "1M") and two("R18", "VBAT_SENSE", "GND", "1M")
        and caps("VBAT_SENSE", "100n") == ["C29"] and on("VBAT_SENSE", "U1.PA2"))
    led_nets = {"CP%d" % i for i in range(5)}
    leds = [p for p in design.parts if p.value.startswith("LED")]
    row("rail VBAT c", "The grain LEDs are driven from MCU pins on the 2.8 V rail, not from VBAT",
        "every LED pin is on CP0..CP4; each CPn reaches only its 68 ohm resistor and LEDs",
        len(leds) == 16 and all(nl.net(p.ref, pin) in led_nets for p in leds for pin in ("A", "K")))
    row("rail V2V8 a", "V2V8 from MCP1700T-2802E/TT; 1 uF in, 1 uF out ceramic",
        "U7: VIN VBAT (C20 1u), VOUT V2V8 (C21 1u)",
        mpn("U7") == "MCP1700T-2802E/TT" and on("VBAT", "U7.VIN") and on("V2V8", "U7.VOUT")
        and "C20" in caps("VBAT", "1u") and "C21" in caps("V2V8", "1u"))
    row("rail V2V8 b", "Loads: MCU VDD / VDDA / VBAT pin, IMU, LCD VDD / VDDA, flash",
        "U1 pads 19, 32, 64, 1; VDDA through R1; U4.VDD, U4.VDDIO; J1.VDD, J1.VDDA; U6.VCC",
        on("V2V8", "U1.VDD_19", "U1.VDD_32", "U1.VDD_64", "U1.VBAT", "U4.VDD", "U4.VDDIO",
           "J1.VDD", "J1.VDDA", "U6.VCC"))
    row("rail V2V8 c", "100 nF per MCU supply pin plus 4.7 uF bulk",
        "C1, C2, C3 (VDD), C4 (VBAT), C9 (VDDUSB) 100n; C5 4u7 on V2V8; C6 4u7 on VCAP",
        all(two(c, "V2V8", "GND", "100n") for c in ("C1", "C2", "C3", "C4"))
        and two("C9", "VDDUSB", "GND", "100n") and two("C5", "V2V8", "GND", "4u7")
        and two("C6", "VCAP", "GND", "4u7"),
        "VCAP capacitor: not in the spec, needed by the internal regulator; value PROVISIONAL")
    row("rail V2V8 d", "VDDA through 10 ohm with 1 uF + 10 nF",
        "R1 10R from V2V8 to VDDA; C7 1u, C8 10n; U1.VDDA pad 13, VSSA to GND",
        two("R1", "V2V8", "VDDA", "10R") and caps("VDDA") == ["C7", "C8"]
        and P["C7"].value == "1u" and P["C8"].value == "10n" and on("VDDA", "U1.VDDA")
        and on("GND", "U1.VSSA"))
    row("rail VDDUSB", "MCP1700T-3302E/TT fed from VBUS (after the Schottky); MCU VDDUSB pin only; "
        "1 uF in, 1 uF out",
        "U11: VIN VBUS_D (C22), VOUT VDDUSB (C23); net VDDUSB = U1 pad 48, U11.VOUT, C9, C23, R14",
        mpn("U11") == "MCP1700T-3302E/TT" and on("VBUS_D", "U11.VIN")
        and only("VDDUSB", "U1.VDDUSB", "U11.VOUT", "C9.1", "C23.1", "R14.2")
        and "C22" in caps("VBUS_D", "1u") and "C23" in caps("VDDUSB", "1u"),
        "DEVIATION: VDDUSB also feeds the 100k STAT pull-up R14 (33 uA at most), see rule 11c")
    row("rail V2V8_CAM a", "LP5907MFX-2.8/NOPB, EN from MCU with 100k pull-down; 1 uF in, 1 uF out",
        "U8: IN VBAT (C24), OUT V2V8_CAM (C25), EN = CAM_EN (PH3) with R10 100k to GND",
        mpn("U8") == "LP5907MFX-2.8/NOPB" and on("VBAT", "U8.IN") and on("V2V8_CAM", "U8.OUT")
        and on("CAM_EN", "U8.EN", "U1.PH3") and two("R10", "CAM_EN", "GND", "100k")
        and "C24" in caps("VBAT", "1u") and "C25" in caps("V2V8_CAM", "1u"),
        "CAM_EN shares the BOOT0 pad: R2 (10k) is in parallel with R10")
    row("rail V2V8_CAM b", "Loads: both camera AVDD and DOVDD; camera DVDD pin: 1 uF to ground each",
        "U2 / U3 AVDD, DOVDD on V2V8_CAM (C14, C15, C17, C18 100n); C16, C19 1u on CAM_L_DVDD / CAM_R_DVDD",
        on("V2V8_CAM", "U2.AVDD", "U2.DOVDD", "U3.AVDD", "U3.DOVDD")
        and only("CAM_L_DVDD", "U2.DVDD", "C16.1") and only("CAM_R_DVDD", "U3.DVDD", "C19.1")
        and P["C16"].value == "1u" and P["C19"].value == "1u",
        "the four 100 nF capacitors at AVDD / DOVDD are not in the spec")
    # ------------------------------------------------------------------ rules
    row("rule 1", "SCCB pull-ups (2.2 kohm) go to V2V8_CAM, not V2V8",
        "R6 (CAM_SCL_L), R7 (CAM_SCL_R), R8 (CAM_SDA) to V2V8_CAM",
        two("R6", "CAM_SCL_L", "V2V8_CAM", "2k2") and two("R7", "CAM_SCL_R", "V2V8_CAM", "2k2")
        and two("R8", "CAM_SDA", "V2V8_CAM", "2k2"),
        "'driven low or analog while the rail is off' is a firmware rule; every camera-facing pin is a GPIO")
    bus = ["D%d" % i for i in range(8)] + ["PCLK", "HREF", "VSYNC"]
    ok = True
    for i, sig in enumerate(bus):
        for cam, side, arrays in (("U2", "L", ("RN1", "RN2", "RN3")), ("U3", "R", ("RN4", "RN5", "RN6"))):
            rn, e = arrays[i // 4], i % 4 + 1
            ok = ok and only("CAM_%s_%s" % (side, sig), "%s.%s" % (cam, sig), "%s.A%d" % (rn, e))
            ok = ok and net("%s.B%d" % (rn, e)) == "CAM_%s" % sig
        ok = ok and len(nl.nodes("CAM_%s" % sig)) == 3
    row("rule 2a", "The two cameras share the 8 data lines, PCLK, HREF and VSYNC; every camera output "
        "joins the shared bus through a 220 ohm series resistor placed at that camera (three 4-element "
        "arrays per camera, Panasonic EXB-28V221JX)",
        "RN1-RN3 at U2, RN4-RN6 at U3: camera pin - A side, bus (CAM_D0..7, CAM_PCLK, CAM_HREF, "
        "CAM_VSYNC) - B side; the 12th element of each camera is unconnected",
        ok and all(mpn(r) == "EXB-28V221JX" and ohms(P[r].value) == 220.0
                   for r in ("RN1", "RN2", "RN3", "RN4", "RN5", "RN6")))
    row("rule 2b", "Each camera has its own SCCB clock line and its own PWDN line; SCCB data is shared",
        "CAM_SCL_L (PC3) - U2.SIOC, CAM_SCL_R (PC0) - U3.SIOC, CAM_SDA (PC1) - both SIOD",
        only("CAM_SCL_L", "U1.PC3", "U2.SIOC", "R6.1") and only("CAM_SCL_R", "U1.PC0", "U3.SIOC", "R7.1")
        and only("CAM_SDA", "U1.PC1", "U2.SIOD", "U3.SIOD", "R8.1"))
    row("rule 2c", "XVCLK has a 33 ohm series resistor at the MCU",
        "R9 33R between MCO (PA8) and CAM_XVCLK (both XVCLK balls)",
        two("R9", "MCO", "CAM_XVCLK", "33R") and only("MCO", "U1.PA8", "R9.1")
        and only("CAM_XVCLK", "R9.2", "U2.XVCLK", "U3.XVCLK"))
    row("rule 2d", "Each PWDN line has a 1 kohm series resistor and must not use PA9, PA2 or PC10",
        "R4 1k: PC2 - U2.PWDN; R5 1k: PH0 - U3.PWDN",
        two("R4", "CAM_L_PWDN_MCU", "CAM_L_PWDN", "1k") and two("R5", "CAM_R_PWDN_MCU", "CAM_R_PWDN", "1k")
        and only("CAM_L_PWDN_MCU", "U1.PC2", "R4.1") and only("CAM_R_PWDN_MCU", "U1.PH0", "R5.1")
        and only("CAM_L_PWDN", "R4.2", "U2.PWDN") and only("CAM_R_PWDN", "R5.2", "U3.PWDN"))
    row("rule 3", "XVCLK comes from the MCU MCO pin (PA8)", "net MCO on U1 pad 41 (RCC_MCO, AF0)",
        on("MCO", "U1.PA8"))
    row("rule 4", "DCMI pin assignment on LQFP-64; SPI1 MISO for the flash must be PB4",
        "PINMAP rows marked SPEC; check_pinmap.py section E parses the spec text",
        on("SPI1_MISO", "U1.PB4", "U6.SO") and on("CAM_D0", "U1.PC6") and on("CAM_D3", "U1.PC9")
        and on("CAM_D4", "U1.PC11") and on("CAM_D7", "U1.PB9") and on("CAM_PCLK", "U1.PA6")
        and on("CAM_HREF", "U1.PA4") and on("CAM_VSYNC", "U1.PB7"))
    row("rule 5", "USB: PA11 = D-, PA12 = D+, crystal-less; VDDUSB from its own 3.3 V regulator",
        "USB_DM / USB_DP to J2 pads 2 / 3 through U10; no high-speed crystal in the netlist; U11",
        on("USB_DM", "U1.PA11", "J2.DM") and on("USB_DP", "U1.PA12", "J2.DP")
        and [p.ref for p in design.parts if p.ref_prefix == "Y"] == ["Y1"])
    tail = {v: k for k, v in G.LCD_TAIL.items()}
    pad_of = lambda fn: str(tail[fn] if G.LCD_TAIL_PIN1_AT_PAD1 else 11 - tail[fn])    # noqa: E731
    row("rule 6a", "LCD: SPI clock and data plus an active-high chip select; DISP on a GPIO with "
        "pull-down; EXTCOMIN from LPTIM1_CH1 on PB2; EXTMODE tied high",
        "J1: SCLK SPI1_SCK, SI SPI1_MOSI, SCS LCD_SCS (PB10), EXTCOMIN PB2, DISP LCD_DISP (PB1), "
        "VDD / VDDA / EXTMODE V2V8, VSS / VSSA GND",
        on("SPI1_SCK", "J1.SCLK", "U1.PB3") and on("SPI1_MOSI", "J1.SI", "U1.PB5")
        and on("LCD_SCS", "J1.SCS", "U1.PB10") and on("LCD_EXTCOMIN", "J1.EXTCOMIN", "U1.PB2")
        and on("LCD_DISP", "J1.DISP", "U1.PB1") and on("V2V8", "J1.EXTMODE", "J1.VDD", "J1.VDDA")
        and on("GND", "J1.VSS", "J1.VSSA"),
        "C32 (1 uF at J1) is not in the spec")
    row("rule 6b", "J1 is a TOP-contact connector (Hirose FH12A-10S-0.5SH(55)) on the FH12 land "
        "pattern; pin order 1 SCLK 2 SI 3 SCS 4 EXTCOMIN 5 DISP 6 VDDA 7 VDD 8 EXTMODE 9 VSS 10 VSSA",
        "J1 pads from the tables LCD_TAIL and LCD_TAIL_PIN1_AT_PAD1 (both PROVISIONAL)",
        mpn("J1") == "FH12A-10S-0.5SH(55)" and "FH12-10S" in P["J1"].footprint_name
        and all(tuple(P["J1"].pins[fn].pads) == (pad_of(fn),) for fn in tail))
    row("rule 7", "IMU on its own SPI bus; INT1 (latched) to a wake-capable pin, INT2 to a second GPIO",
        "SPI2_SCK / MOSI / MISO (PB13 / PB15 / PB14) and IMU_CS (PB12) connect U1 and U4 only; "
        "INT1 PC5 (WKUP5), INT2 PA7",
        only("SPI2_SCK", "U1.PB13", "U4.SCL") and only("SPI2_MOSI", "U1.PB15", "U4.SDA")
        and only("SPI2_MISO", "U1.PB14", "U4.SDO") and on("IMU_CS", "U1.PB12", "U4.CS")
        and only("IMU_INT1", "U1.PC5", "U4.INT1") and only("IMU_INT2", "U1.PA7", "U4.INT2"))
    row("rule 9 (clocks)", "No high-speed crystal", "PH0 / PH1 are GPIO (CAM_R_PWDN, CHG_INHIBIT); "
        "the only crystal is Y1", on("CAM_R_PWDN_MCU", "U1.PH0") and on("CHG_INHIBIT", "U1.PH1"))
    cp_ok = all(two("R%d" % (23 + i), "CP%d_MCU" % i, "CP%d" % i, "68R") for i in range(5)) \
        and all(len([n for n in nl.nodes("CP%d_MCU" % i)]) == 2 for i in range(5))
    pairs = {}
    for p in leds:
        key = frozenset((nl.net(p.ref, "A"), nl.net(p.ref, "K")))
        pairs.setdefault(key, []).append(p)
    anti = len(pairs) == 8 and all(
        len(v) == 2 and nl.net(v[0].ref, "A") == nl.net(v[1].ref, "K")
        and {v[0].value, v[1].value} == {"LED red", "LED NIR"} for v in pairs.values())
    row("rule 10a", "16 LEDs charlieplexed on 5 MCU pins with one series resistor per pin (5 x 68 ohm), "
        "red and NIR LED of each pair antiparallel where possible",
        "R23-R27 68R on PA9, PA15, PC12, PD2, PC10; D1-D16: 8 antiparallel red / NIR pairs on 8 of the "
        "10 line pairs (GRAIN_PAIRS)", cp_ok and anti)
    row("rule 10b", "Photodiode cathode to the op-amp inverting input, 470 kohm + 10 pF feedback, "
        "non-inverting input at a mid-rail bias from a 2 x 100 kohm divider with 100 nF",
        "PD1.K, R28 470k, C33 10p on PD_K = PA1 (OPAMP1_VINM); other ends on OPAMP_OUT = PA3; R29 "
        "(from NTC_BIAS) / R30 100k, C34 100n on VBIAS = PA0 (OPAMP1_VINP); PD1.A to GND",
        on("PD_K", "PD1.K", "U1.PA1") and two("R28", "PD_K", "OPAMP_OUT", "470k")
        and two("C33", "PD_K", "OPAMP_OUT", "10p") and on("OPAMP_OUT", "U1.PA3")
        and two("R29", "NTC_BIAS", "VBIAS", "100k") and two("R30", "VBIAS", "GND", "100k")
        and caps("VBIAS", "100n") == ["C34"] and on("VBIAS", "U1.PA0") and on("GND", "PD1.A"),
        "the spec names neither the anode net nor the rail of the divider: anode to GND, divider fed "
        "from the NTC_BIAS pin (PA5) so that it draws nothing in standby; R31 (1M to V2V8) is ADDED")
    row("rule 11a", "PROG resistor 49.9 kohm (20 mA), taken to ground through a low-threshold "
        "N-MOSFET (for example onsemi BSS138)",
        "R11 49k9: U9.PROG - Q1.D; Q1.S to GND",
        two("R11", "CHG_PROG", "CHG_PROG_SW", "49k9") and only("CHG_PROG", "U9.PROG", "R11.1")
        and only("CHG_PROG_SW", "R11.2", "Q1.D") and on("GND", "Q1.S") and P["Q1"].value == "BSS138")
    row("rule 11b", "The gate is fed from a 1 Mohm / 1 Mohm divider on the charger supply (VBUS after "
        "the Schottky); an MCU open-drain pin (CHG_INHIBIT, low = stop) pulls the gate down",
        "R12 1M VBUS_D - gate, R13 1M gate - GND, gate net CHG_INHIBIT = Q1.G = PH1",
        two("R12", "VBUS_D", "CHG_INHIBIT", "1M") and two("R13", "CHG_INHIBIT", "GND", "1M")
        and only("CHG_INHIBIT", "U1.PH1", "Q1.G", "R12.2", "R13.1"))
    row("rule 11c", "STAT to an MCU input with a 100 kohm pull-up to V2V8",
        "U9.STAT - D18 (cathode at STAT) - CHG_STAT = PB0 with R14 100k to VDDUSB and R32 470k to GND",
        diode("D18", "CHG_STAT", "CHG_STAT_RAW") and only("CHG_STAT_RAW", "U9.STAT", "D18.K")
        and two("R14", "CHG_STAT", "VDDUSB", "100k") and two("R32", "CHG_STAT", "GND", "470k")
        and only("CHG_STAT", "U1.PB0", "D18.A", "R14.1", "R32.1"),
        "DEVIATION: D18 added (the MCP73831 drives STAT high to its VDD); the pull-up goes to VDDUSB "
        "(3.3 V, cradle only) and is divided to 2.72 V, not to V2V8")
    row("rule 12", "A 10 kohm NTC (Murata NCP15XH103F03RC) ... divider with 10.0 kohm 1 % from a GPIO "
        "(NTC_BIAS) to an ADC pin (NTC_SENSE)",
        "R19 10k: NTC_BIAS (PA5) - NTC_SENSE (PC4, ADC1_IN13); RT1 NTC_SENSE - GND; RT1 within 1 mm "
        "of the cell edge in the nominal placement",
        two("R19", "NTC_BIAS", "NTC_SENSE", "10k") and two("RT1", "NTC_SENSE", "GND")
        and mpn("RT1") == "NCP15XH103F03RC" and only("NTC_BIAS", "U1.PA5", "R19.1", "R29.1")
        and on("NTC_SENSE", "U1.PC4") and _ntc_near_cell(design),
        "DEVIATION: the NTC_BIAS pin also feeds the grain bias divider (R29), see rule 10b")
    row("rule 13", "100 kohm pull-down on the LCD chip select and on DISP; 100 kohm pull-ups to V2V8 "
        "on the flash and IMU chip selects",
        "R21 (LCD_SCS), R22 (LCD_DISP) to GND; R3 (FLASH_CS), R20 (IMU_CS) to V2V8",
        two("R21", "LCD_SCS", "GND", "100k") and two("R22", "LCD_DISP", "GND", "100k")
        and two("R3", "FLASH_CS", "V2V8", "100k") and two("R20", "IMU_CS", "V2V8", "100k")
        and on("FLASH_CS", "U6.CS") and on("IMU_CS", "U4.CS"))
    row("rule 14", "32.768 kHz crystal on PC14 / PC15: Abracon ABS07-120-32.768KHZ-T with load "
        "capacitors sized for 6 pF",
        "Y1 between OSC32_IN (PC14) and OSC32_OUT (PC15); C11, C12 6p8 to GND",
        mpn("Y1") == "ABS07-120-32.768KHZ-T" and only("OSC32_IN", "U1.PC14", "Y1.1", "C11.1")
        and only("OSC32_OUT", "U1.PC15", "Y1.2", "C12.1") and P["C11"].value == P["C12"].value == "6p8")
    row("rule 15", "BOOT0 (PH3) pulled down with 10 kohm; NRST with 100 nF",
        "R2 10k from PH3 (net CAM_EN) to GND; C10 100n on NRST",
        two("R2", "CAM_EN", "GND", "10k") and on("CAM_EN", "U1.PH3") and caps("NRST", "100n") == ["C10"])
    order = [nl.net("J2", n) for n in ("VBUS", "DM", "DP", "GND", "SWDIO", "SWCLK", "NRST")]
    pads = sorted(geometry.part_pads(design, P["J2"]), key=lambda q: q.x)
    row("rule 16", "Test and service pads on the underside: VBUS, D-, D+, GND, SWDIO, SWCLK, NRST",
        "J2 (bottom side), pads 1..7 at x = -7.62 ... +7.62, y = -17.0",
        order == ["VBUS", "USB_DM", "USB_DP", "GND", "SWDIO", "SWCLK", "NRST"]
        and P["J2"].side == BOTTOM and [q.number for q in pads] == [str(i) for i in range(1, 8)]
        and all(abs(q.x - x) < 1e-6 and abs(q.y - Y["base_plate"]["pad_holes"]["y"]) < 1e-6
                for q, x in zip(pads, Y["base_plate"]["pad_holes"]["xs"]))
        and on("SWDIO", "U1.PA13") and on("SWCLK", "U1.PA14") and on("NRST", "U1.NRST"))
    row("rule 17", "No copper pours or vias under the IMU body on the top layer",
        "rule area under_U4 on F.Cu (tracks, vias, pours)",
        any(k.name == "under_U4" and k.tracks and k.vias and k.copper for k in design.keepouts),
        "'keep it away from the charger and regulators' is a placement matter for the layout step")
    # ------------------------------------------------------------------ PCB paragraph
    r = design.rules
    row("PCB a", "4 layers, 0.8 mm, D-shaped outline (radius 21.1 mm, flat at y = 17.3 mm)",
        "Design: layers 4, thickness 0.8, PathShape.d_shape from the YAML",
        design.layers == 4 and abs(design.board_thickness - 0.8) < 1e-9
        and abs(Y["pcb"]["radius"] - 21.1) < 1e-9 and abs(Y["pcb"]["flat_y"] - 17.3) < 1e-9)
    holes = design.outline.holes
    slots = design.outline.cutouts
    row("PCB b", "two non-plated locating holes at (14.35, 10.8) and (-14.35, 10.8, a 1.15 x 2.2 mm "
        "slot along x)",
        "outline hole H1 dia 1.15 and NPTH slot",
        len(holes) == 1 and (holes[0].x, holes[0].y, holes[0].drill) == (14.35, 10.8, 1.15)
        and len(slots) == 1 and abs(slots[0].width - 1.15) < 1e-9
        and abs(abs(slots[0].x2 - slots[0].x1) + slots[0].width - 2.2) < 1e-9
        and abs((slots[0].x1 + slots[0].x2) / 2 + 14.35) < 1e-9 and slots[0].y1 == slots[0].y2 == 10.8)
    fine_nets = sorted(n.name for n in design.nets.values() if n.netclass == "Fine")
    cam_only = all(any(ref in ("U2", "U3") for ref, _p in design.nets[n].nodes) for n in fine_nets)
    nc = design.netclasses
    row("PCB c", "through vias only, 0.25 mm drill, default 0.15 mm tracks with 0.127 mm clearance, and "
        "a fine net class of 0.10 mm track / 0.10 mm clearance used only to escape the camera BGAs",
        "rules GL1_4L_0.10mm; classes Default 0.15 / 0.127, Fine 0.10 / 0.10 (%d nets, each with a "
        "camera ball), fine areas round U2 and U3" % len(fine_nets),
        r.via_drill == 0.25 and not r.blind_buried_vias and nc["Default"].track_width == 0.15
        and nc["Default"].clearance == 0.127 and nc["Fine"].track_width == 0.10
        and nc["Fine"].clearance == 0.10 and r.min_track == 0.10 and r.min_clearance == 0.10
        and cam_only and len(design.fine_areas) == 2,
        "CamPower (0.15 / 0.10) is a second class with the fine clearance, confined to the same areas")
    row("PCB d", "provisional 5 x 5 footprint, 0.5 mm pitch, 0.20 mm pads",
        "camera_footprint(): 25 round pads 0.20 mm on 0.5 mm, pad clearance 0.10 (OVM7692_BALLS)",
        len(P["U2"].footprint.pads) == 25 and all(abs(q.w - 0.20) < 1e-9 for q in P["U2"].footprint.pads)
        and G.OVM7692_PITCH == 0.5)
    kos = {k.name: k for k in design.keepouts}
    row("PCB e", "Vias tented and plugged on the underside, and no via at all inside the grain opening "
        "or the pad slot",
        "via_tenting 'bottom', via_protection text; rule areas grain_opening_no_via, pad_slot_no_via",
        design.via_tenting == "bottom" and "plugged" in design.via_protection
        and kos["grain_opening_no_via"].vias and kos["pad_slot_no_via"].vias)
    row("PCB f", "Layer 2 solid ground", "plane GND on In1.Cu (whole board, not routable)",
        any(pl.net == "GND" and pl.layer == "In1.Cu" and pl.shape is None and not pl.routable
            for pl in design.planes),
        "In2.Cu: V2V8 plane that is also a routing layer - the layout step may change this")
    ko = Y["tub_keepouts"]
    n_post = sum(1 for k in design.keepouts if k.name.startswith("post_foot") and k.footprints)
    hl = {h.name: h for h in design.height_limits}
    row("PCB g", "no part taller than 2.55 mm anywhere (cameras excepted), six 1.6 mm and two 2.2 mm "
        "post-foot keep-outs, nothing taller than 0.95 mm under each camera hood except the camera, "
        "nothing taller than 0.7 mm under the LCD flex tail",
        "8 placement keep-outs post_foot_*; height limits free_height, camera_hood_U2 / U3, lcd_tail",
        n_post == 8 and hl["free_height"].max_height == ko["free_height_above_pcb"] == 2.55
        and hl["camera_hood_U2"].max_height == 0.95 and hl["camera_hood_U3"].max_height == 0.95
        and hl["lcd_tail"].max_height == 0.7 and set(hl["free_height"].exempt) == {"U2", "U3"})
    lands = [p for p in design.parts if p.ref.startswith("FL")]
    row("PCB h", "no soldered part above a ball foot or within 0.3 mm of its zone; under each ball foot "
        "the bottom side has a 2.5 mm circle with no via and no track and an unmasked 1.6 mm copper land",
        "foot_zone_n_top (placement, dia 2.5 + 2 x 0.3), foot_zone_n (B.Cu: no track, no via, no pour), "
        "FL1-FL3: bare dia 1.6 pads without a net",
        all(kos["foot_zone_%d" % i].tracks and kos["foot_zone_%d" % i].vias
            and kos["foot_zone_%d_top" % i].footprints for i in (1, 2, 3))
        and len(lands) == 3 and all(p.side == BOTTOM and not p.pins for p in lands)
        and sorted((p.x, p.y) for p in lands) == sorted(tuple(q) for q in ko["foot_zones"]["positions"]))
    zx, zy = Y["battery"]["pads"]["zone"]["x"], Y["battery"]["pads"]["zone"]["y"]
    tabs = [q for ref in ("BT1", "BT2") for q in geometry.part_pads(design, P[ref])]
    row("PCB i", "Two solder pads for the cell leads sit in the strip beyond the protection-board end "
        "of the cell",
        "BT1 (+), BT2 (-): 1.5 x 2.4 pads inside battery.pads.zone",
        len(tabs) == 2 and all(zx[0] - 1e-6 <= q.polygon.bounds[0] and q.polygon.bounds[2] <= zx[1] + 1e-6
                               and zy[0] - 1e-6 <= q.polygon.bounds[1] and q.polygon.bounds[3] <= zy[1] + 1e-6
                               for q in tabs))
    bottom = sorted(p.ref for p in design.parts if p.side == BOTTOM and p.in_bom)
    row("PCB j", "Parts on the top side except the grain LEDs, photodiode and contact pads",
        "bottom side: D1-D16, PD1 (fitted), J2, FL1-FL3, three fiducials (bare copper)",
        bottom == sorted(["D%d" % i for i in range(1, 17)] + ["PD1"]))
    row("PCB k", "The cameras, the LCD connector and the battery are fixed mechanical interfaces",
        "U2, U3, J1 at the YAML positions; battery_body placement keep-out from the YAML",
        (P["U2"].x, P["U2"].y) == G.CAM_L and (P["U3"].x, P["U3"].y) == G.CAM_R
        and (P["J1"].x, P["J1"].y) == G.J1_XY and "battery_body" in kos)
    n_top = sum(1 for p in design.parts if "fiducial" in p.footprint_name.lower() and p.side == TOP)
    n_bot = sum(1 for p in design.parts if "fiducial" in p.footprint_name.lower() and p.side == BOTTOM)
    row("fiducials", "(task) at least three global fiducials per side", "FID1-FID3 top, FID4-FID6 bottom",
        n_top >= 3 and n_bot >= 3)
    return out


def _ntc_near_cell(design):
    """RT1's body within 1 mm of the battery body rectangle of the YAML."""
    from shapely.geometry import box
    b = G.BAT["body"]
    cell = box(b["x"] - b["dx"] / 2, b["y"] - b["dy"] / 2, b["x"] + b["dx"] / 2, b["y"] + b["dy"] / 2)
    return geometry.part_body_polygon(design.part("RT1")).distance(cell) <= 1.0


def markdown(rows):
    lines = ["| Spec rule | What DESIGN_SPEC section 4 says | Where it is in the netlist | Test |",
             "|---|---|---|---|"]
    for rid, spec, where, ok, note in rows:
        lines.append("| %s | %s | %s%s | %s |" % (rid, spec, where, (" *(%s)*" % note) if note else "",
                                                 "pass" if ok else "**FAIL**"))
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--markdown", help="write the table as Markdown to this file")
    args = ap.parse_args(argv)
    rows = rules(G.gl1_main_design())
    bad = [r for r in rows if not r[3]]
    for rid, spec, where, ok, note in rows:
        print("%-5s %-16s %s" % ("ok" if ok else "FAIL", rid, where))
        if note:
            print("      %-16s note: %s" % ("", note))
    print("\nspec rules: %d rows, %d passed, %d failed" % (len(rows), len(rows) - len(bad), len(bad)))
    if args.markdown:
        with open(args.markdown, "w", encoding="utf-8") as fh:
            fh.write(markdown(rows))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
