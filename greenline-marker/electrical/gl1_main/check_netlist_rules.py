#!/usr/bin/python3
"""DESIGN_SPEC section 4 (rev E: amendments E1 to E28 and E35), rule by rule,
against the GL-1 main-board netlist.

    /usr/bin/python3 -B electrical/gl1_main/check_netlist_rules.py [--markdown FILE] [--selftest]

Every row is one sentence of the specification (rail table, the rules in the
order they appear, the PCB paragraph), the place in the netlist that
implements it, and a test that is evaluated on the design object of
``gl1_main_design.py``: connectivity, part values, order codes, rule areas,
pad positions.  The toolchain's own checks (``gleda.checks``) prove that the
netlist is consistent; this file proves that it is the netlist the amended
specification asks for.  Nothing here is a hardware test.

Every row has one of five results (``row_status``):

* ``pass``        the sentence is implemented as written (a note that starts
                  with ADDED names parts the spec does not ask for);
* ``departure``   the test passes, but the sentence is implemented differently
                  from its letter (note starts with DEVIATION; NETLIST_NOTES 5);
* ``open``        a contract that is NOT met and cannot be met inside this
                  package (note starts with OPEN; NETLIST_NOTES 5.1) - the row
                  measures it and fails outright if the numbers change;
* ``workaround``  something done to get past a gap in another package (note
                  starts with WORKAROUND; NETLIST_NOTES 5.2);
* ``FAIL``        the netlist is not what the row describes.

Only ``FAIL`` makes the exit status 1; the other three non-pass results are
counted and printed with the summary and are never reported as "pass".

``--selftest`` seeds defects of the kind the amendments guard against (the
old charger left in, the NTC part not changed, a swapped pad order, a test
point missing, the fallback resistor fitted, the CHG pull-up on the wrong
rail, the MOSFET on the wrong net, an LED reversed, a regulator on the wrong
SOT-23 pin order, the LCD pads un-mirrored, ...) and requires each to fail a row.

Exit status 0 only if no row FAILs (and, with --selftest, every seeded defect
is caught).
"""
import argparse
import math
import os
import re
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

#: parts and nets of the circuit before E1 / E2 that must be gone
OLD_MPNS = ("MCP73831", "NCP15XH103F03RC", "1N4148", "SFH 4053")
#: parts replaced by E25 / E26 that must be gone
REPLACED_MPNS = ("B0530WS", "MCP1700T-3302")
OLD_NETS = ("CHG_PROG", "CHG_PROG_SW", "CHG_PROG_EN", "CHG_STAT_RAW")
#: "keep it away from the charger and regulators" has no number in the spec;
#: this is the floor the placement is tested against (body to body)
IMU_MIN_DISTANCE = 2.5

#: the pin-1 edge of the LCD tail that the research's inference gives (see
#: LCD_TAIL_PIN1_EDGE in the design file); only a stated other source may differ
LCD_TAIL_PIN1_EDGE_BY_INFERENCE = "left"

#: note prefix -> result of a row whose test passes (see the module docstring)
NOTE_STATUS = {"DEVIATION": "departure", "OPEN": "open", "WORKAROUND": "workaround"}
STATUSES = ("pass", "departure", "open", "workaround", "FAIL")

KICAD_SYMBOL_DIR = "/usr/share/kicad/symbols"
#: Second source for the pin -> pad tables typed into gl1_main_design.py: the
#: installed KiCad symbol of the part (or of the pin-compatible family member
#: the research names).  ref -> (library, symbol, {netlist pin(s): symbol pin name}).
#: "A+B" means the pads of netlist pins A and B together.  The generic Device
#: symbols carry KiCad's convention for its two-pin land patterns (pad 1 =
#: cathode) and for the convex 4-resistor array (element n: pad n to pad 9 - n).
_SOT23_LDO = {"GND": "GND", "VOUT": "VO", "VIN": "VI"}
_TWO = {"K": "K", "A": "A"}
_RN = {"A1": "R1.1", "A2": "R2.1", "A3": "R3.1", "A4": "R4.1",
       "B4": "R4.2", "B3": "R3.2", "B2": "R2.2", "B1": "R1.2"}
LIBRARY_SYMBOLS = {
    "U7": ("Regulator_Linear", "MCP1700x-280xxTT", _SOT23_LDO),
    "U11": ("Regulator_Linear", "LP5907MFX-3.3",
            {"IN": "IN", "GND": "GND", "EN": "EN", "NC": "NC", "OUT": "OUT"}),
    "U8": ("Regulator_Linear", "LP5907MFX-2.8",
           {"IN": "IN", "GND": "GND", "EN": "EN", "NC": "NC", "OUT": "OUT"}),
    "U10": ("Power_Protection", "USBLC6-2SC6",
            {"IO1A+IO1B": "I/O1", "IO2A+IO2B": "I/O2", "GND": "GND", "VBUS": "VBUS"}),
    "Q1": ("Transistor_FET", "BSS138", {"G": "G", "S": "S", "D": "D"}),
    # same family and package; the 64 Mbit part has no symbol of its own
    "U6": ("Memory_Flash", "MX25R3235FZNxx0",
           {"CS": "~{CS}", "SO": "SO/SIO1", "WP": "~{WP}/SIO2", "GND": "GND", "SI": "SI/SIO0",
            "SCLK": "SCLK", "HOLD": "~{RESET}/SIO3", "VCC": "VCC"}),
    # spec: "LSM6DSV16X ... VERIFIED pin-compatible with the LSM6DSM symbol in the KiCad library"
    "U4": ("Sensor_Motion", "LSM6DSM",
           {"SDO": "SDO/SA0", "SDX": "SDX", "SCX": "SCX", "INT1": "INT1", "VDDIO": "VDDIO",
            "GND1+GND2": "GND", "VDD": "VDD", "INT2": "INT2", "OCS_AUX": "OCS_Aux",
            "SDO_AUX": "SDO_Aux", "CS": "CS", "SCL": "SCL", "SDA": "SDA"}),
}
LIBRARY_SYMBOLS.update({"D%d" % i: ("Device", "LED", _TWO) for i in range(1, 17)})
LIBRARY_SYMBOLS.update({"RN%d" % i: ("Device", "R_Pack04", _RN) for i in range(1, 7)})


def kicad_symbol(lib, name, _seen=()):
    """({pad number: pin name}, footprint property) of an installed KiCad
    symbol, following ``extends``.  None if the library or the symbol is missing."""
    path = os.path.join(KICAD_SYMBOL_DIR, lib + ".kicad_sym")
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None
    start = text.find('\n  (symbol "%s"' % name)
    if start < 0:
        return None
    end = text.find('\n  (symbol "', start + 10)
    block = text[start:end if end > 0 else len(text)]
    fp = re.search(r'\(property "Footprint" "([^"]*)"', block)
    ext = re.search(r'\(extends "([^"]+)"\)', block)
    if ext:
        if ext.group(1) in _seen:
            return None
        base = kicad_symbol(lib, ext.group(1), _seen + (name,))
        return None if base is None else (base[0], fp.group(1) if fp else base[1])
    pins = {}
    for m in re.finditer(r'\(pin \w+ \w+.*?\(name "([^"]*)".*?\(number "([^"]*)"', block, re.S):
        pins[m.group(2)] = m.group(1)
    return pins, (fp.group(1) if fp else "")


def pin_table_problems(design):
    """Differences between the pin -> pad tables of the netlist and the KiCad
    symbols of LIBRARY_SYMBOLS: a list of strings, empty when they agree."""
    P = design.parts_by_ref
    bad = []
    for ref, (lib, sym, names) in sorted(LIBRARY_SYMBOLS.items()):
        part = P.get(ref)
        got = kicad_symbol(lib, sym)
        if part is None or got is None:
            bad.append("%s: %s" % (ref, "not in the netlist" if part is None
                                   else "symbol %s:%s not found" % (lib, sym)))
            continue
        sym_pins, sym_fp = got
        if sym_fp and sym_fp != part.footprint_name:
            bad.append("%s: footprint %s, the symbol %s has %s" % (ref, part.footprint_name, sym, sym_fp))
        covered = set()
        for mine, theirs in names.items():
            pads = set()
            for pin in mine.split("+"):
                if pin not in part.pins:
                    bad.append("%s: no pin %s" % (ref, pin))
                    continue
                pads |= set(part.pins[pin].pads)
            want = {num for num, nm in sym_pins.items() if nm == theirs}
            covered |= want
            if pads != want:
                bad.append("%s.%s on pad(s) %s, the symbol %s has %s on %s"
                           % (ref, mine, sorted(pads), sym, theirs, sorted(want)))
        if covered != set(sym_pins) or len(part.pins) != sum(len(k.split("+")) for k in names):
            bad.append("%s: pins of the symbol not covered: %s" % (ref, sorted(set(sym_pins) - covered)))
    return bad


def row_status(row):
    """'pass', 'departure', 'open', 'workaround' or 'FAIL' of a row of rules()."""
    return row[5] if len(row) > 5 else ("pass" if row[3] else "FAIL")


def status_counts(rows):
    return {s: sum(1 for r in rows if row_status(r) == s) for s in STATUSES}


def counts_text(rows):
    c = status_counts(rows)
    ids = {s: ", ".join(r[0] for r in rows if row_status(r) == s) for s in STATUSES}
    text = "%d rows: %d as specified, %d departures from the letter of the spec (%s)" % (
        len(rows), c["pass"], c["departure"], ids["departure"] or "none")
    text += ", %d open - NOT met (%s)" % (c["open"], ids["open"] or "none")
    text += ", %d workaround (%s)" % (c["workaround"], ids["workaround"] or "none")
    return text + ", %d failed%s" % (c["FAIL"], (" (%s)" % ids["FAIL"]) if c["FAIL"] else "")


def rules(design):
    """[(id, what the spec says, where it is in the netlist, test passed, note, result)]
    - ``result`` as in the module docstring (``row_status``)."""
    nl = Netlist(design)
    P = design.parts_by_ref
    Y = G.Y
    out = []
    by_sig = {r["signal"]: r for r in G.pinmap_rows()}

    def pin_of(signal):
        return by_sig[signal]["pin"]

    def row(rid, spec, where, ok, note=""):
        status = "FAIL" if not ok else NOTE_STATUS.get(note.split(":", 1)[0].split(" ", 1)[0], "pass")
        out.append((rid, spec, where, bool(ok), note, status))

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
        """fitted capacitors from net ``name`` to GND"""
        return sorted(ref for ref, p in P.items() if p.ref_prefix == "C" and not p.dnp
                      and two(ref, name, "GND") and (value is None or p.value == value))

    def mpn(ref):
        return P[ref].mpn if ref in P else None

    def all_nodes(name):
        return sorted("%s.%s" % n for n in design.nets[name].nodes) if name in design.nets else []

    def only(name, *nodes):
        """the net consists of exactly these pins (unfitted parts included)"""
        return all_nodes(name) == sorted(nodes)

    def fitted(ref):
        return ref in P and not P[ref].dnp

    def pads(ref):
        return geometry.part_pads(design, P[ref])

    def dist_body(a, b):
        return geometry.part_body_polygon(P[a]).distance(geometry.part_body_polygon(P[b]))

    # ------------------------------------------------------------------ rail table
    row("rail VBUS a", "VBUS: cradle pad, 5 V; USBLC6-2SC6 clamps VBUS, D+, D-",
        "net VBUS = J2.VBUS (pad 1), U10.VBUS, U12.VIN, C28, R15; USB_DM / USB_DP through U10 pins 1+6 / 3+4",
        on("VBUS", "J2.VBUS", "U10.VBUS") and mpn("U10") == "USBLC6-2SC6"
        and on("USB_DM", "U10.IO1A", "U10.IO1B", "J2.DM", "U1.PA11")
        and on("USB_DP", "U10.IO2A", "U10.IO2B", "J2.DP", "U1.PA12") and on("GND", "U10.GND")
        and only("VBUS", "J2.VBUS", "U10.VBUS", "U12.VIN", "C28.1", "R15.1"),
        "ADDED: C28 100 nF at the VBUS pin of U10")
    u12 = P.get("U12")
    u12_table = u12 is not None and {pin.pads[0]: (name, pin.etype) for name, pin in u12.pins.items()} == G.LM66100_PINS
    no_replaced = not any(any(o in (p.mpn or "") for o in REPLACED_MPNS) for p in design.parts) and "D17" not in P
    row("rail VBUS b", "E25 (replaces 'Series Schottky from pad to charger'): an ideal-diode switch (TI "
        "LM66100DCKR, SC-70-6, enable pin tied to its output so that it blocks reverse current; wiring "
        "PROVISIONAL until the data sheet is read)",
        "U12 (LM66100DCKR, SC-70-6): VIN on VBUS (the pad side), VOUT and CE on VBUS_D, GND to GND, ST open; "
        "U9.IN on VBUS_D; no Schottky (D17) and no B0530WS left; every pin of U12 comes from the table "
        "LM66100_PINS (VIN 1, GND 2, CE 3, NC 4, ST 5, VOUT 6)",
        u12 is not None and mpn("U12") == "LM66100DCKR" and "SC-70-6" in u12.footprint_name
        and on("VBUS", "U12.VIN") and on("VBUS_D", "U12.VOUT", "U12.CE", "U9.IN") and on("GND", "U12.GND")
        and net("U12.ST") is None and u12_table and no_replaced
        and sorted(n for n, _t in G.LM66100_PINS.values()) == ["CE", "GND", "NC", "ST", "VIN", "VOUT"],
        "the pin table of U12 is PROVISIONAL (from memory, no second source in the KiCad library): a wrong "
        "table mis-wires the switch; that the switch is on while CE is below VIN is from memory too")
    row("rail VBUS c", "VBUS loads: BQ25101 IN, VBUS-sense divider",
        "R15 / R16 (100k : 100k) from VBUS (the pad net) to VBUS_SENSE (%s, WKUP2); U9.IN behind the "
        "ideal-diode switch: net VBUS_D = U12.VOUT, U12.CE, U9.IN, C26, U11.IN, C22" % pin_of("VBUS_SENSE"),
        two("R15", "VBUS", "VBUS_SENSE", "100k") and two("R16", "VBUS_SENSE", "GND", "100k")
        and only("VBUS_SENSE", "U1.%s" % pin_of("VBUS_SENSE"), "R15.2", "R16.1")
        and only("VBUS_D", "U12.VOUT", "U12.CE", "U9.IN", "C26.1", "U11.IN", "C22.1"),
        "the divider values are this netlist's choice (the spec gives none)")
    row("rail VBAT a", "VBAT: cell + PCM; loads MCP1700-2.8 in, LP5907 in, battery divider",
        "net VBAT = BT1, U9.OUT, U7.VIN, U8.IN, R17, C20, C24, C27, TP1",
        only("VBAT", "BT1.1", "U9.OUT", "U7.VIN", "U8.IN", "R17.1", "C20.1", "C24.1", "C27.1", "TP1.1")
        and on("GND", "BT2.1"))
    row("rail VBAT b", "2 x 1 Mohm divider with 100 nF to an ADC pin",
        "R17 / R18 1M, C29 100n on VBAT_SENSE = PA2 (ADC1_IN7)",
        two("R17", "VBAT", "VBAT_SENSE", "1M") and two("R18", "VBAT_SENSE", "GND", "1M")
        and caps("VBAT_SENSE", "100n") == ["C29"] and only("VBAT_SENSE", "U1.PA2", "R17.2", "R18.1", "C29.1"))
    led_nets = {"CP%d" % i for i in range(5)}
    leds = [p for p in design.parts if p.value.startswith("LED")]
    row("rail VBAT c", "The grain LEDs are driven from MCU pins on the 2.8 V rail, not from VBAT",
        "every LED pin is on CP0..CP4; each CPn reaches only its 68 ohm resistor and LEDs",
        len(leds) == 16 and all(nl.net(p.ref, pin) in led_nets for p in leds for pin in ("A", "K"))
        and all({n.split(".")[0][0] for n in all_nodes("CP%d" % i)} <= {"D", "R"} for i in range(5)))
    row("rail V2V8 a", "V2V8 from MCP1700T-2802E/TT; 1 uF in, 1 uF out ceramic",
        "U7: VIN VBAT (C20 1u), VOUT V2V8 (C21 1u)",
        mpn("U7") == "MCP1700T-2802E/TT" and on("VBAT", "U7.VIN") and on("V2V8", "U7.VOUT")
        and "C20" in caps("VBAT", "1u") and "C21" in caps("V2V8", "1u"))
    row("rail V2V8 b", "Loads: MCU VDD / VDDA / VBAT pin, IMU, LCD VDD / VDDA, flash",
        "U1 pads 19, 32, 64, 1; VDDA through R1; U4.VDD, U4.VDDIO; J1.VDD, J1.VDDA; U6.VCC",
        on("V2V8", "U1.VDD_19", "U1.VDD_32", "U1.VDD_64", "U1.VBAT", "U4.VDD", "U4.VDDIO",
           "J1.VDD", "J1.VDDA", "U6.VCC"),
        "ADDED: C13 (flash), C30 / C31 (IMU) 100 nF, C32 1 uF at J1")
    row("rail V2V8 c", "100 nF per MCU supply pin plus 4.7 uF bulk",
        "C1, C2, C3 (VDD), C4 (VBAT), C9 (VDDUSB) 100n; C5 4u7 on V2V8; C6 4u7 on VCAP",
        all(two(c, "V2V8", "GND", "100n") for c in ("C1", "C2", "C3", "C4"))
        and two("C9", "VDDUSB", "GND", "100n") and two("C5", "V2V8", "GND", "4u7")
        and two("C6", "VCAP", "GND", "4u7") and only("VCAP", "U1.VCAP", "C6.1"),
        "ADDED: C6 on VCAP - not in the spec, needed by the internal regulator; value PROVISIONAL")
    row("rail V2V8 d", "VDDA through 10 ohm with 1 uF + 10 nF",
        "R1 10R from V2V8 to VDDA; C7 1u, C8 10n; U1.VDDA pad 13, VSSA to GND",
        two("R1", "V2V8", "VDDA", "10R") and caps("VDDA") == ["C7", "C8"]
        and P["C7"].value == "1u" and P["C8"].value == "10n" and on("VDDA", "U1.VDDA")
        and on("GND", "U1.VSSA"))
    row("rail VDDUSB", "E26 (replaces the MCP1700T-3302E/TT of the rail table): TI LP5907MFX-3.3/NOPB, "
        "enabled by the 2.8 V rail; fed from VBUS_D (behind the series switch); MCU VDDUSB pin only; "
        "2.2 uF in, 2.2 uF out (E27)",
        "U11 (LP5907MFX-3.3/NOPB, SOT-23-5): IN VBUS_D (C22 2u2), OUT VDDUSB (C23 2u2), EN on V2V8, pad 4 "
        "open; net VDDUSB = U1 pad 48, U11.OUT, C9, C23, TP5 (test pad, added)",
        mpn("U11") == "LP5907MFX-3.3/NOPB" and "SOT-23-5" in P["U11"].footprint_name
        and on("VBUS_D", "U11.IN") and on("V2V8", "U11.EN") and on("GND", "U11.GND")
        and only("VDDUSB", "U1.VDDUSB", "U11.OUT", "C9.1", "C23.1", "TP5.1")
        and "C22" in caps("VBUS_D", "2u2") and "C23" in caps("VDDUSB", "2u2"),
        "2.2 uF in and out is the letter of the rev E rail table (E27; it was a departure from rev D's "
        "1 uF); the DC-bias curves behind E27 are PROVISIONAL. With EN on V2V8 the "
        "USB supply pin cannot rise before the main supply (E26). PROVISIONAL, from memory: the enable pin "
        "of the LP5907 has an internal pull-down of about 1 Mohm, which draws about 2.8 uA from the "
        "always-on rail - it counts against the 25 uA sleep limit of E14 (NETLIST_NOTES 11)")
    row("rail V2V8_CAM a", "LP5907MFX-2.8/NOPB, EN from MCU with 100k pull-down; 1 uF in, 1 uF out",
        "U8: IN VBAT (C24), OUT V2V8_CAM (C25), EN = CAM_EN (PH0) with R10 100k to GND",
        mpn("U8") == "LP5907MFX-2.8/NOPB" and on("VBAT", "U8.IN") and on("V2V8_CAM", "U8.OUT")
        and only("CAM_EN", "U8.EN", "U1.PH0", "R10.1") and two("R10", "CAM_EN", "GND", "100k")
        and "C24" in caps("VBAT", "1u") and "C25" in caps("V2V8_CAM", "1u"))
    row("rail V2V8_CAM b", "Loads: both camera AVDD and DOVDD; camera DVDD pin: 1 uF to ground each",
        "U2 / U3 AVDD, DOVDD on V2V8_CAM; C16, C19 1u on CAM_L_DVDD / CAM_R_DVDD",
        on("V2V8_CAM", "U2.AVDD", "U2.DOVDD", "U3.AVDD", "U3.DOVDD")
        and only("CAM_L_DVDD", "U2.DVDD", "C16.1") and only("CAM_R_DVDD", "U3.DVDD", "C19.1")
        and P["C16"].value == "1u" and P["C19"].value == "1u"
        and only("V2V8_CAM", "U8.OUT", "C25.1", "U2.AVDD", "U2.DOVDD", "U3.AVDD", "U3.DOVDD",
                 "C14.1", "C15.1", "C17.1", "C18.1", "R6.2", "R7.2", "R8.2", "TP3.1"),
        "ADDED: C14, C15, C17, C18 100 nF at the AVDD / DOVDD balls")
    # ------------------------------------------------------------------ camera rules
    row("cam 1", "SCCB pull-ups (2.2 kohm) go to V2V8_CAM, not V2V8",
        "R6 (CAM_SCL_L), R7 (CAM_SCL_R), R8 (CAM_SDA) to V2V8_CAM",
        two("R6", "CAM_SCL_L", "V2V8_CAM", "2k2") and two("R7", "CAM_SCL_R", "V2V8_CAM", "2k2")
        and two("R8", "CAM_SDA", "V2V8_CAM", "2k2"),
        "'driven low or analog while the rail is off' is a firmware rule; every camera-facing pin is a "
        "GPIO or a DCMI / MCO pin that can be set analog")
    bus = ["D%d" % i for i in range(8)] + ["PCLK", "HREF", "VSYNC"]
    ok = sorted(G.CAM_ARRAY_MAP) == ["U2", "U3"] and all(
        sorted(m) == sorted(bus) and len(set(m.values())) == 11
        and all(a in (0, 1, 2) and e in (1, 2, 3, 4) for a, e in m.values())
        for m in G.CAM_ARRAY_MAP.values())
    for sig in bus:
        for cam, side in (("U2", "L"), ("U3", "R")):
            a, e = G.CAM_ARRAY_MAP.get(cam, {}).get(sig, (0, 1))
            rn = G.CAM_ARRAYS[cam][a]
            ok = ok and only("CAM_%s_%s" % (side, sig), "%s.%s" % (cam, sig), "%s.A%d" % (rn, e))
            ok = ok and net("%s.B%d" % (rn, e)) == "CAM_%s" % sig
        ok = ok and len(all_nodes("CAM_%s" % sig)) == 3
    spare = [n for cam in ("U2", "U3") for rn in G.CAM_ARRAYS[cam] for e in range(1, 5)
             for n in ("%s.A%d" % (rn, e), "%s.B%d" % (rn, e)) if net(n) is None]
    ok = ok and len(spare) == 4
    far = max(dist_body(rn, cam) for cam, rns in (("U2", ("RN1", "RN2", "RN3")), ("U3", ("RN4", "RN5", "RN6")))
              for rn in rns)
    row("cam 2a", "The two cameras share the 8 data lines, PCLK, HREF and VSYNC; every camera output "
        "joins the shared bus through a 220 ohm series resistor placed at that camera (three 4-element "
        "0402-in-0804 arrays per camera, Panasonic EXB-28V221JX)",
        "RN1-RN3 at U2, RN4-RN6 at U3: camera pin - A side, bus (CAM_D0..7, CAM_PCLK, CAM_HREF, "
        "CAM_VSYNC) - B side, element by element as in the tables CAM_ARRAY_MAP, one per camera (free for the layout "
        "step); the 12th element of each camera is unconnected; placement: every array within "
        "%.1f mm of its camera body" % far,
        ok and all(mpn(r) == "EXB-28V221JX" and ohms(P[r].value) == 220.0
                   for r in ("RN1", "RN2", "RN3", "RN4", "RN5", "RN6")) and far <= 3.0)
    row("cam 2b", "Each camera has its own SCCB clock line and its own PWDN line; SCCB data is shared",
        "CAM_SCL_L (PC3) - U2.SIOC, CAM_SCL_R (PC0) - U3.SIOC, CAM_SDA (PC1) - both SIOD",
        only("CAM_SCL_L", "U1.PC3", "U2.SIOC", "R6.1") and only("CAM_SCL_R", "U1.PC0", "U3.SIOC", "R7.1")
        and only("CAM_SDA", "U1.PC1", "U2.SIOD", "U3.SIOD", "R8.1"))
    row("cam 2c", "XVCLK has a 33 ohm series resistor at the MCU",
        "R9 33R between MCO (PA8) and CAM_XVCLK (both XVCLK balls)",
        two("R9", "MCO", "CAM_XVCLK", "33R") and only("MCO", "U1.PA8", "R9.1")
        and only("CAM_XVCLK", "R9.2", "U2.XVCLK", "U3.XVCLK"),
        "placement: R9 is %.1f mm from pad 41; nothing fits between the MCU and the battery, "
        "the layout step moves it as close as it can" % geometry.part_body_polygon(P["R9"]).distance(
            next(q.polygon for q in pads("U1") if q.number == "41")))
    row("cam 2d", "Each PWDN line has a 1 kohm series resistor and must not use PA9, PA2 or PC10",
        "R4 1k: PC2 - U2.PWDN; R5 1k: PH3 - U3.PWDN",
        two("R4", "CAM_L_PWDN_MCU", "CAM_L_PWDN", "1k") and two("R5", "CAM_R_PWDN_MCU", "CAM_R_PWDN", "1k")
        and only("CAM_L_PWDN_MCU", "U1.PC2", "R4.1") and only("CAM_R_PWDN_MCU", "U1.PH3", "R5.1", "R2.1")
        and only("CAM_L_PWDN", "R4.2", "U2.PWDN") and only("CAM_R_PWDN", "R5.2", "U3.PWDN"),
        "DEVIATION: the right camera's PWDN shares the BOOT0 pad (R2 10k to ground is on its MCU side)")
    row("cam 3", "XVCLK comes from the MCU MCO pin (PA8)", "net MCO on U1 pad 41 (RCC_MCO, AF0)",
        on("MCO", "U1.PA8"), "12 MHz is a firmware setting")
    row("cam 4", "DCMI pin assignment on LQFP-64; SPI1 MISO for the flash must be PB4",
        "PINMAP rows marked SPEC; check_pinmap.py section E parses the spec text",
        on("SPI1_MISO", "U1.PB4", "U6.SO") and on("CAM_D0", "U1.PC6") and on("CAM_D1", "U1.PC7")
        and on("CAM_D2", "U1.PC8") and on("CAM_D3", "U1.PC9") and on("CAM_D4", "U1.PC11")
        and on("CAM_D5", "U1.PB6") and on("CAM_D6", "U1.PB8") and on("CAM_D7", "U1.PB9")
        and on("CAM_PCLK", "U1.PA6") and on("CAM_HREF", "U1.PA4") and on("CAM_VSYNC", "U1.PB7"))
    # ------------------------------------------------------------------ USB, LCD, IMU, flash
    row("usb", "USB: PA11 = D-, PA12 = D+, crystal-less; VDDUSB from its own 3.3 V regulator",
        "USB_DM / USB_DP to J2 pads 2 / 3 through U10; no high-speed crystal in the netlist; U11",
        only("USB_DM", "U1.PA11", "J2.DM", "U10.IO1A", "U10.IO1B")
        and only("USB_DP", "U1.PA12", "J2.DP", "U10.IO2A", "U10.IO2B")
        and [p.ref for p in design.parts if p.ref_prefix == "Y"] == ["Y1"])
    tail = {v: k for k, v in G.LCD_TAIL.items()}
    row("lcd a", "LCD: SPI clock and data plus an active-high chip select; DISP on a GPIO with "
        "pull-down; EXTCOMIN from LPTIM1 or LPTIM3, for example LPTIM1_CH1 on PB2; EXTMODE tied high",
        "J1: SCLK SPI1_SCK (PB3), SI SPI1_MOSI (PB5), SCS LCD_SCS (PB10), EXTCOMIN PB2, DISP LCD_DISP "
        "(PB12), VDD / VDDA / EXTMODE V2V8, VSS / VSSA GND",
        only("SPI1_SCK", "U1.PB3", "J1.SCLK", "U6.SCLK") and only("SPI1_MOSI", "U1.PB5", "J1.SI", "U6.SI")
        and on("LCD_SCS", "J1.SCS", "U1.PB10") and only("LCD_EXTCOMIN", "J1.EXTCOMIN", "U1.PB2")
        and on("LCD_DISP", "J1.DISP", "U1.PB12") and on("V2V8", "J1.EXTMODE", "J1.VDD", "J1.VDDA")
        and on("GND", "J1.VSS", "J1.VSSA"))
    row("lcd b", "J1 is a TOP-contact connector (Hirose FH12A-10S-0.5SH(55), 2.0 mm high, on the FH12 "
        "land pattern); pin order 1 SCLK 2 SI 3 SCS 4 EXTCOMIN 5 DISP 6 VDDA 7 VDD 8 EXTMODE 9 VSS 10 VSSA",
        "J1 FH12A-10S-0.5SH(55) on the KiCad FH12-10S land pattern, 2.0 mm; LCD_TAIL (tail pin -> "
        "function) is that order; every function is on exactly one pad",
        mpn("J1") == "FH12A-10S-0.5SH(55)" and "FH12-10S" in P["J1"].footprint_name
        and P["J1"].height_mm == 2.0
        and [G.LCD_TAIL[n] for n in range(1, 11)] == ["SCLK", "SI", "SCS", "EXTCOMIN", "DISP", "VDDA",
                                                      "VDD", "EXTMODE", "VSS", "VSSA"]
        and sorted(int(p.pads[0]) for fn, p in P["J1"].pins.items() if fn in tail) == list(range(1, 11))
        and all(len(P["J1"].pins[fn].pads) == 1 for fn in tail),
        "the spec's pin order is the order on the TAIL (PROVISIONAL there); which pad a tail pin meets is "
        "row lcd c")
    # ---- which end of the tail is pin 1: the evidence chain, measured on the placed footprint ----
    j1_pads = {q.number: q for q in pads("J1") if q.number != "MP"}
    j1_body = geometry.part_body_polygon(P["J1"]).bounds
    sgn = lambda v: (v > 0) - (v < 0)                                    # noqa: E731
    lcd_ok, lcd_text = False, "J1 could not be measured"
    if len(j1_pads) == 10 and G.LCD_TAIL_PIN1_EDGE in ("left", "right") and G.LCD_EXIT_EDGE == "rear":
        mouth = sgn(0.5 * (j1_body[1] + j1_body[3]) - j1_pads["1"].y)   # the body lies on the mouth side of the pads
        pad1 = sgn(j1_pads["1"].x - j1_pads["10"].x)
        # rear exit: the tail leaves the glass toward -y; "left when it points up" is then +x
        pin1 = 1 if G.LCD_TAIL_PIN1_EDGE == "left" else -1
        travel = -1 * (-1) ** G.LCD_TAIL_FOLDS_ABOUT_X                 # each fold about x turns the tail round
        straight = pin1 == pad1
        want = {fn: str(n if straight else 11 - n) for fn, n in tail.items()}
        got = {fn: P["J1"].pins[fn].pads[0] for fn in tail}
        sclk = j1_pads[got["SCLK"]]
        inferred = G.LCD_TAIL_PIN1_SOURCE.startswith("inference")
        lcd_ok = (travel == -mouth and got == want and sgn(sclk.x) == pin1
                  and G.LCD_TAIL_PIN1_AT_PAD1 == straight and G.lcd_tail_pin1_at_pad1(P["J1"].rotation) == straight
                  and G.LCD_TAIL_FOLDS_ABOUT_X == 1 and bool(G.LCD_TAIL_PIN1_SOURCE.strip())
                  and (not inferred or G.LCD_TAIL_PIN1_EDGE == LCD_TAIL_PIN1_EDGE_BY_INFERENCE))
        lcd_text = ("LCD_TAIL_PIN1_EDGE = '%s' (seen from the front, tail up; source: %s), rear exit, %d fold "
                    "about x: tail "
                    "pin 1 enters J1 at %sx; measured on the placed J1: mouth toward %sy, pad 1 at x = %+.2f, "
                    "pad 10 at %+.2f - tail pin n is on pad %s (SCLK pad %s at x = %+.2f, VSSA pad %s)"
                    % (G.LCD_TAIL_PIN1_EDGE, G.LCD_TAIL_PIN1_SOURCE, G.LCD_TAIL_FOLDS_ABOUT_X,
                       "+" if pin1 > 0 else "-",
                       "+" if mouth > 0 else "-", j1_pads["1"].x, j1_pads["10"].x,
                       "n" if straight else "11 - n", got["SCLK"], sclk.x, got["VSSA"]))
    row("lcd c", "the LCD tail makes one U-fold under the glass, which turns its contacts upward. Which "
        "end of the tail is pin 1 is PROVISIONAL and must be read from the Sharp drawing: a wrong guess "
        "mirrors all ten pins", lcd_text, lcd_ok,
        "PROVISIONAL (release gate B16): the pin-1 edge is an inference from public designs (research), "
        "not the Sharp drawing; the row proves that the pad table follows from it and that the edge is the "
        "one the stated source gives, not that it is right"
        if G.LCD_TAIL_PIN1_SOURCE.startswith("inference") else "source of the pin-1 edge: " + G.LCD_TAIL_PIN1_SOURCE)
    row("imu", "IMU on its own SPI bus; INT1 (latched) to a wake-capable pin, INT2 to a second GPIO",
        "SPI2_SCK / MOSI / MISO (PB13 / PB15 / PB14) and IMU_CS (PB1) connect U1 and U4 only; "
        "INT1 PA7 (WKUP8), INT2 PA5",
        only("SPI2_SCK", "U1.PB13", "U4.SCL") and only("SPI2_MOSI", "U1.PB15", "U4.SDA")
        and only("SPI2_MISO", "U1.PB14", "U4.SDO") and only("IMU_CS", "U1.PB1", "U4.CS", "R20.1")
        and only("IMU_INT1", "U1.PA7", "U4.INT1") and only("IMU_INT2", "U1.PA5", "U4.INT2")
        and mpn("U4") == "LSM6DSV16XTR",
        "that PA7 is a wake-up pin is proven by check_pinmap.py")
    row("flash", "(section 3) SPI NOR flash on SPI1 with the LCD; MISO on PB4",
        "U6 MX25R6435F: CS PA10, SO PB4, SI PB5, SCLK PB3; WP# and HOLD# tied to V2V8",
        on("FLASH_CS", "U6.CS", "U1.PA10") and on("SPI1_MISO", "U6.SO") and on("V2V8", "U6.WP", "U6.HOLD")
        and on("GND", "U6.GND") and mpn("U6") == "MX25R6435FZNIL0")
    row("clocks", "No high-speed crystal", "PH0 / PH1 are GPIO (CAM_PWR_EN, CHG_INHIBIT); the only "
        "crystal is Y1", on("CAM_EN", "U1.PH0") and on("CHG_INHIBIT", "U1.PH1"))
    # ------------------------------------------------------------------ grain sensor
    cp_ok = all(two("R%d" % (23 + i), "CP%d_MCU" % i, "CP%d" % i, "68R") for i in range(5)) \
        and all(len(all_nodes("CP%d_MCU" % i)) == 2 for i in range(5))
    pairs = {}
    for p in leds:
        key = frozenset((nl.net(p.ref, "A"), nl.net(p.ref, "K")))
        pairs.setdefault(key, []).append(p)
    anti = len(pairs) == 8 and all(
        len(v) == 2 and nl.net(v[0].ref, "A") == nl.net(v[1].ref, "K")
        and {v[0].value, v[1].value} == {"LED red", "LED NIR"} for v in pairs.values())
    row("grain a", "16 LEDs charlieplexed on 5 MCU pins with one series resistor per pin (5 x 68 ohm), "
        "red and NIR LED of each pair antiparallel where possible",
        "R23-R27 68R on %s; D1-D16: 8 antiparallel red / NIR pairs on 8 of the 10 line pairs "
        "(GRAIN_PAIRS = the firmware's table)" % ", ".join(pin_of("GRAIN_CP%d" % i) for i in range(5)),
        cp_ok and anti and all(net("U1.%s" % pin_of("GRAIN_CP%d" % i)) == "CP%d_MCU" % i for i in range(5)))
    red = [p for p in leds if p.value == "LED red"]
    nir = [p for p in leds if p.value == "LED NIR"]
    row("grain b", "Parts (E3): red Vishay VLMS1500-GS08 (0402); near-infrared ams OSRAM SFH 4053B "
        "(0402), alternative Inolux IN-S42CTQIR",
        "D1, D3, ... D15: VLMS1500-GS08; D2, D4, ... D16: SFH 4053B (the alternative is named in the "
        "part description)",
        len(red) == 8 and len(nir) == 8 and all(p.mpn == "VLMS1500-GS08" for p in red)
        and all(p.mpn == "SFH 4053B" and "IN-S42CTQIR" in p.description for p in nir)
        and all("0402" in p.footprint_name for p in leds))
    ring = Y["bottom_side_parts"]["grain_led_ring"]
    geo_ok = True
    worst_r = 0.0
    for k, (lo, hi) in enumerate(G.GRAIN_PAIRS):
        az = math.radians(ring["first_azimuth_deg"] + ring["step_deg"] * k)
        cx, cy = ring["x"] + ring["radius"] * math.cos(az), ring["y"] + ring["radius"] * math.sin(az)
        for ref, colour in (("D%d" % (2 * k + 1), "red"), ("D%d" % (2 * k + 2), "NIR")):
            p = P[ref]
            worst_r = max(worst_r, abs(math.hypot(p.x - cx, p.y - cy) - G.LED_PAIR_PITCH / 2.0))
            pp = sorted(pads(ref), key=lambda q: math.hypot(q.x - ring["x"], q.y - ring["y"]))
            inner, outer = pp[0], pp[-1]
            a, kk = nl.net(ref, "A"), nl.net(ref, "K")
            geo_ok = geo_ok and p.side == BOTTOM and inner.net == "CP%d" % lo and outer.net == "CP%d" % hi
            geo_ok = geo_ok and ((a, kk) == ("CP%d" % lo, "CP%d" % hi) if colour == "red"
                                 else (a, kk) == ("CP%d" % hi, "CP%d" % lo))
            geo_ok = geo_ok and p.value == "LED " + colour
    row("grain c", "(YAML) eight LED pairs on a 5.2 mm radius about (0, -4), first at 22.5 degrees, "
        "45 degrees apart, on the underside; red anode on the lower line (firmware table)",
        "D(2k+1) red, D(2k+2) NIR at azimuth 22.5 + 45 k, 0.5 mm either side of the ring point; measured "
        "on the pads: inner pad = lower line, outer pad = higher line for all 16",
        geo_ok and worst_r < 1e-3,
        "DEVIATION: 1.00 mm between the two LEDs of a pair (mechanical model 0.90): two KiCad 0402 "
        "courtyards need 0.95")
    row("grain d", "Photodiode cathode to the op-amp inverting input, 470 kohm + 10 pF feedback, "
        "non-inverting input at a mid-rail bias from a 2 x 100 kohm divider with 100 nF",
        "PD1.K, R28 470k, C33 10p on PD_K = PA1 (OPAMP1_VINM); other ends on OPAMP_OUT = PA3; R29 "
        "(from LCD_DISP) / R30 100k, C34 100n on VBIAS = PA0 (OPAMP1_VINP); PD1.A to GND",
        on("PD_K", "PD1.K", "U1.PA1") and two("R28", "PD_K", "OPAMP_OUT", "470k")
        and two("C33", "PD_K", "OPAMP_OUT", "10p") and on("OPAMP_OUT", "U1.PA3")
        and two("R29", "LCD_DISP", "VBIAS", "100k") and two("R30", "VBIAS", "GND", "100k")
        and caps("VBIAS", "100n") == ["C34"] and only("VBIAS", "U1.PA0", "R29.2", "R30.1", "C34.1")
        and on("GND", "PD1.A") and mpn("PD1") == "VEMD8080" and "0402" in P["R28"].footprint_name
        and only("OPAMP_OUT", "U1.PA3", "R28.2", "C33.2", "R31.1")
        and two("R31", "OPAMP_OUT", "V2V8", "150k"),
        "DEVIATION: the spec names neither the anode net nor the rail of the divider: anode to GND, "
        "divider fed from the LCD_DISP line so that it draws nothing asleep. ADDED: R31 150k from PA3 to "
        "V2V8 (PA3 is the ROM's USART2_RX)")
    # ------------------------------------------------------------------ charger (E1)
    balls = {pin: ball for ball, (pin, _t) in G.BQ25101_BALLS.items()}
    u9 = P.get("U9")
    fp = u9.footprint if u9 else None
    xs = sorted({round(q.x, 3) for q in fp.pads}) if fp is not None and hasattr(fp, "pads") else []
    ys = sorted({round(q.y, 3) for q in fp.pads}) if fp is not None and hasattr(fp, "pads") else []
    row("E1 a", "Charger: TI BQ25101YFP (4.20 V, DSBGA-6, 0.4 mm ball pitch, all six balls on the "
        "perimeter); the ball map is PROVISIONAL and is kept in one marked table",
        "U9 BQ25101YFPR on a generated 2 x 3 land pattern, 0.4 mm pitch; every pin of U9 comes from "
        "the table BQ25101_BALLS (OUT A1, IN A2, TS B1, ISET B2, CHG C1, VSS C2)",
        u9 is not None and u9.mpn.startswith("BQ25101YFP") and len(fp.pads) == 6 and len(xs) == 2
        and len(ys) == 3 and abs(xs[1] - xs[0] - 0.4) < 1e-9 and abs(ys[1] - ys[0] - 0.4) < 1e-9
        and {n: tuple(p.pads) for n, p in u9.pins.items()} == {n: (b,) for n, b in balls.items()}
        and sorted(balls) == ["CHG", "IN", "ISET", "OUT", "TS", "VSS"] and "PROVISIONAL" in fp.name)
    row("E1 b", "IN from VBUS_D, behind the ideal-diode switch U12 (E25), with 2.2 uF; OUT to the cell with "
        "2.2 uF (E27)",
        "U9.IN on VBUS_D with C26 2u2; U9.OUT on VBAT (BT1) with C27 2u2; U9.VSS to GND",
        on("VBUS_D", "U9.IN") and "C26" in caps("VBUS_D", "2u2") and on("VBAT", "U9.OUT", "BT1.1")
        and "C27" in caps("VBAT", "2u2") and on("GND", "U9.VSS"),
        "2.2 uF at IN and OUT is the letter of the rev E spec (E27; it was a departure from rev D's 1 uF; "
        "the DC-bias curves are PROVISIONAL). Headroom of the charger input with the switch of E25: NETLIST_NOTES 4.1 / 11 (all numbers PROVISIONAL)")
    row("E1 c", "ISET resistor 6.81 kohm 1 % to ground (K = 135 A-ohm, so 19.8 mA)",
        "R11 6k81 from CHG_ISET (U9.ISET) to GND: 135 / 6810 = %.2f mA" % (135.0 / ohms("6k81") * 1e3),
        two("R11", "CHG_ISET", "GND", "6k81") and only("CHG_ISET", "U9.ISET", "R11.1")
        and abs(135.0 / ohms(P["R11"].value) - 0.0198) < 0.0001)
    row("E1 d", "TS to a 10 kohm NTC at the cell",
        "RT1 from CHG_TS (U9.TS) to GND; the only other thing on CHG_TS is the drain of Q1",
        two("RT1", "CHG_TS", "GND") and only("CHG_TS", "U9.TS", "RT1.1", "Q1.D"))
    row("E1 e", "CHG (open drain, low while charging) to an MCU input with a 100 kohm pull-up to V2V8",
        "CHG_STAT = U9.CHG, %s, R13 100k to V2V8 (and the unfitted R14)" % pin_of("CHG_STAT"),
        two("R13", "CHG_STAT", "V2V8", "100k") and fitted("R13")
        and only("CHG_STAT", "U9.CHG", "U1.%s" % pin_of("CHG_STAT"), "R13.1", "R14.1")
        and u9.pins["CHG"].etype == "open_drain")
    row("E1 f", "Firmware stop: CHG_INHIBIT is an MCU push-pull output to the gate of a small "
        "N-MOSFET (for example onsemi BSS138, gate pulled down with 100 kohm) that pulls TS to ground",
        "Q1 BSS138: gate CHG_INHIBIT (PH1) with R12 100k to GND, drain CHG_TS, source GND",
        P["Q1"].value == "BSS138" and mpn("Q1") == "BSS138LT1G"
        and only("CHG_INHIBIT", "U1.PH1", "Q1.G", "R12.1") and two("R12", "CHG_INHIBIT", "GND", "100k")
        and on("CHG_TS", "Q1.D") and on("GND", "Q1.S"))
    row("E1 g", "Fallback on the same footprint: BQ25100YFP ... the board carries an unpopulated "
        "resistor position from that ball to ground for it",
        "R14 (0402, NOT FITTED) from CHG_STAT (ball C1) to GND",
        "R14" in P and P["R14"].dnp and two("R14", "CHG_STAT", "GND")
        and net("U9.CHG") == "CHG_STAT" and balls["CHG"] == "C1"
        and [p.ref for p in design.parts if p.dnp and p.in_bom] == ["R14"],
        "value 6k04 (10 % termination, 20 % pre-charge) is PROVISIONAL; with the BQ25100 fitted R13 "
        "must be left out")
    gone = [m for m in OLD_MPNS if any(p.mpn == m or p.mpn.startswith(m + "T") or p.value.startswith(m)
                                       for p in design.parts)]
    gone += [n for n in OLD_NETS if n in design.nets]
    row("E1 h", "(E1) the MCP73831, its PROG MOSFET circuit and its gate divider are gone",
        "no MCP73831, no 1N4148 on the status line, no net CHG_PROG*, no part on VBUS_D but the "
        "charger, the VDDUSB regulator and their capacitors",
        not gone, ", ".join(gone))
    # ------------------------------------------------------------------ cell temperature (E2)
    bat = Y["battery"]["body"]
    from shapely.geometry import box
    cell = box(bat["x"] - bat["dx"] / 2, bat["y"] - bat["dy"] / 2,
               bat["x"] + bat["dx"] / 2, bat["y"] + bat["dy"] / 2)
    d_ntc = {r: geometry.part_body_polygon(P[r]).distance(cell) for r in ("RT1", "RT2") if r in P}
    row("E2 a", "Two 10 kohm NTCs (Murata NCU15XH103F60RC, 0402, B 3380 K) on the top side within "
        "1 mm of the cell edge",
        "RT1, RT2: NCU15XH103F60RC, top side; placement %s from the cell body"
        % ", ".join("%s %.2f mm" % (r, d) for r, d in sorted(d_ntc.items())),
        len(d_ntc) == 2 and all(mpn(r) == "NCU15XH103F60RC" and P[r].side == TOP
                                and "0402" in P[r].footprint_name and 0.0 < d_ntc[r] <= 1.0
                                for r in d_ntc)
        and [p.ref for p in design.parts if p.ref_prefix == "RT"] == ["RT1", "RT2"],
        "the dab of thermal adhesive is an assembly step")
    row("E2 b", "NTC1 goes from the charger TS ball to ground and belongs to the charger alone",
        "RT1: CHG_TS - GND; no MCU pin on CHG_TS",
        two("RT1", "CHG_TS", "GND") and not any(n.startswith("U1.") for n in all_nodes("CHG_TS")))
    row("E2 c", "NTC2 is the MCU's: divider with 10.0 kohm 1 % from a GPIO (NTC_BIAS, driven only "
        "while measuring) to an ADC pin (NTC_SENSE)",
        "R19 10k: NTC_BIAS (PC5) - NTC_SENSE (PC4, ADC1_IN13); RT2: NTC_SENSE - GND; nothing else on "
        "either net",
        two("R19", "NTC_BIAS", "NTC_SENSE", "10k") and two("RT2", "NTC_SENSE", "GND")
        and only("NTC_BIAS", "U1.PC5", "R19.1") and only("NTC_SENSE", "U1.PC4", "R19.2", "RT2.1"))
    # ------------------------------------------------------------------ reset states, clock, straps
    row("reset", "100 kohm pull-down on the LCD chip select and on DISP; 100 kohm pull-ups to V2V8 "
        "on the flash and IMU chip selects",
        "R21 (LCD_SCS), R22 (LCD_DISP) to GND; R3 (FLASH_CS), R20 (IMU_CS) to V2V8",
        two("R21", "LCD_SCS", "GND", "100k") and two("R22", "LCD_DISP", "GND", "100k")
        and two("R3", "FLASH_CS", "V2V8", "100k") and two("R20", "IMU_CS", "V2V8", "100k")
        and on("FLASH_CS", "U6.CS") and on("IMU_CS", "U4.CS")
        and only("LCD_DISP", "U1.PB12", "J1.DISP", "R22.1", "R29.1"),
        "LCD_DISP also carries the top of the grain bias divider (R29 + R30 = 200k more to ground)")
    row("crystal", "32.768 kHz crystal on PC14 / PC15: Abracon ABS07-120-32.768KHZ-T with load "
        "capacitors sized for 6 pF",
        "Y1 between OSC32_IN (PC14) and OSC32_OUT (PC15); C11, C12 6p8 to GND",
        mpn("Y1") == "ABS07-120-32.768KHZ-T" and only("OSC32_IN", "U1.PC14", "Y1.1", "C11.1")
        and only("OSC32_OUT", "U1.PC15", "Y1.2", "C12.1") and P["C11"].value == P["C12"].value == "6p8")
    row("boot nrst", "BOOT0 (PH3) pulled down with 10 kohm; NRST with 100 nF",
        "R2 10k from PH3 (net CAM_R_PWDN_MCU) to GND; C10 100n on NRST",
        two("R2", "CAM_R_PWDN_MCU", "GND", "10k") and on("CAM_R_PWDN_MCU", "U1.PH3")
        and caps("NRST", "100n") == ["C10"] and only("NRST", "U1.NRST", "C10.1", "J2.NRST"))
    # ------------------------------------------------------------------ pads and test points
    order = [nl.net("J2", n) for n in ("VBUS", "DM", "DP", "GND", "SWDIO", "SWCLK", "NRST")]
    row_pads = sorted(pads("J2"), key=lambda q: q.x)
    xs_yaml = Y["base_plate"]["pad_holes"]["xs"]
    row("pads", "Test and service pads on the underside: VBUS, D-, D+, GND, SWDIO, SWCLK, NRST, in "
        "that order from x = -7.62 to +7.62 mm seen from above",
        "J2 (bottom side): pad positions measured on the placed footprint, x = %s, y = -17.0; nets "
        "left to right %s" % ([round(q.x, 2) for q in row_pads], [q.net for q in row_pads]),
        [q.net for q in row_pads] == ["VBUS", "USB_DM", "USB_DP", "GND", "SWDIO", "SWCLK", "NRST"]
        and order == ["VBUS", "USB_DM", "USB_DP", "GND", "SWDIO", "SWCLK", "NRST"]
        and P["J2"].side == BOTTOM and all(tuple(q.layers) == ("B.Cu",) for q in row_pads)
        and all(abs(q.x - x) < 1e-6 and abs(q.y - Y["base_plate"]["pad_holes"]["y"]) < 1e-6
                and abs(q.w - G.PAD_DIA) < 1e-9 for q, x in zip(row_pads, xs_yaml))
        and xs_yaml[0] == -7.62 and xs_yaml[-1] == 7.62
        and on("SWDIO", "U1.PA13") and on("SWCLK", "U1.PA14") and on("NRST", "U1.NRST"),
        "seen from below with the visor away, VBUS is on the right: the same statement mirrored")
    # TP5 (VDDUSB) is ADDED to the four test points of E4 (review: E14 sets a board-test limit for
    # that rail and it had no pad)
    tps = {"TP1": "VBAT", "TP2": "V2V8", "TP3": "V2V8_CAM", "TP4": "GND", "TP5": "VDDUSB"}
    tp_ok = True
    for ref, name in tps.items():
        p = P.get(ref)
        tp_ok = tp_ok and p is not None and p.side == TOP and not p.in_bom and nl.net(ref, "1") == name
        if p is not None:
            q = pads(ref)
            tp_ok = tp_ok and len(q) == 1 and q[0].shape == "circle" and abs(q[0].w - 1.0) < 1e-9 \
                and tuple(q[0].layers) == ("F.Cu",) and p.footprint.pads[0].kind == "conn"
    row("E4", "Test points on the top side (E4), 1.0 mm bare round pads reachable by spring probes "
        "before the unit is closed: VBAT, V2V8, V2V8_CAM, GND",
        "TP1 VBAT, TP2 V2V8, TP3 V2V8_CAM, TP4 GND, and ADDED TP5 VDDUSB (E14 gives that rail a "
        "board-test limit): round dia 1.0 pads on F.Cu, mask open, no paste",
        tp_ok and sorted(p.ref for p in design.parts if p.ref_prefix == "TP") == sorted(tps),
        "board test powers the board through BT1 / BT2 (the cell-lead pads)")
    row("imu area", "No copper pours or vias under the IMU body on the top layer; keep it away from "
        "the charger and regulators",
        "rule area under_U4 on F.Cu (tracks, vias, pours); placement: U4 to U9 %.1f mm, to U8 "
        "%.1f, to U7 %.1f, to U11 %.1f mm" % tuple(dist_body("U4", r) for r in ("U9", "U8", "U7", "U11")),
        any(k.name == "under_U4" and k.tracks and k.vias and k.copper for k in design.keepouts)
        and min(dist_body("U4", r) for r in ("U9", "U8", "U7", "U11")) >= IMU_MIN_DISTANCE,
        "'away' has no number in the spec: the test uses this file's own floor of %.1f mm between bodies "
        "(the YAML's nominal part list has 2.85 mm between U4 and U8); the layout step owns the distances"
        % IMU_MIN_DISTANCE)
    # ------------------------------------------------------------------ PCB paragraph
    r = design.rules
    row("PCB a", "4 layers, 0.8 mm, D-shaped outline (radius 21.1 mm, flat at y = 17.3 mm)",
        "Design: layers 4, thickness 0.8, PathShape.d_shape from the YAML",
        design.layers == 4 and abs(design.board_thickness - 0.8) < 1e-9
        and abs(Y["pcb"]["radius"] - 21.1) < 1e-9 and abs(Y["pcb"]["flat_y"] - 17.3) < 1e-9,
        "ENIG is the toolchain's stack-up default, written by the fabrication outputs of the layout step")
    holes = design.outline.holes
    slots = design.outline.cutouts
    row("PCB b", "two non-plated locating holes at (14.35, 10.8) and (-14.35, 10.8, a 1.15 x 2.2 mm "
        "slot along x)",
        "outline hole H1 dia 1.15 and NPTH slot",
        len(holes) == 1 and (holes[0].x, holes[0].y, holes[0].drill) == (14.35, 10.8, 1.15)
        and len(slots) == 1 and abs(slots[0].width - 1.15) < 1e-9
        and abs(abs(slots[0].x2 - slots[0].x1) + slots[0].width - 2.2) < 1e-9
        and abs((slots[0].x1 + slots[0].x2) / 2 + 14.35) < 1e-9 and slots[0].y1 == slots[0].y2 == 10.8)
    fine_nets = sorted(n.name for n in design.nets.values() if n.netclass in ("Fine", "CamPower"))
    cam_only = all(any(ref in ("U2", "U3") for ref, _p in design.nets[n].nodes) for n in fine_nets)
    nc = design.netclasses
    ync = Y["pcb"]["net_classes"]
    e35_note = [n for n in design.fab_notes if "E35" in n and "E7" in n]
    fine_margins = []
    for a in design.fine_areas:              # measured: area box against the pad field of its part
        ab = geometry.fine_area_polygon(a).bounds
        pb = geometry.part_pads_bbox(design, a.ref) if a.ref in P else (0.0, 0.0, 0.0, 0.0)
        m = (pb[0] - ab[0], pb[1] - ab[1], ab[2] - pb[2], ab[3] - pb[3])
        fine_margins.append(round(min(m), 4) if max(m) - min(m) < 1e-6 else None)
    fine_margins.sort(key=lambda v: -1.0 if v is None else v)
    row("PCB c", "through vias only, 0.25 mm drill, default 0.15 mm tracks with 0.127 mm clearance; E35: the "
        "0.100 / 0.100 mm fine class may be used on F.Cu, In2.Cu and B.Cu inside two rule areas that extend "
        "5 mm beyond each camera ball field, everywhere else 0.15 / 0.127 mm; E7 / E35: fabricator "
        "acceptance of 0.100 mm on all three layers is a release gate, the quote request names them",
        "rules GL1_4L_0.10mm; classes Default 0.15 / 0.127, Fine 0.10 / 0.10 and CamPower 0.15 / 0.10 "
        "(%d nets, each with a camera ball); two fine areas, pad field of U2 / U3 + %s mm (YAML "
        "pcb.net_classes.fine: %s / %s on %s, %s mm); the fab note on E7 / E35 names F.Cu, In2.Cu and B.Cu"
        % (len(fine_nets), "/".join("%g" % m for m in fine_margins if m is not None) or "?",
           ync["fine"]["track"], ync["fine"]["clearance"], ", ".join(ync["fine"]["layers"]),
           ync["fine"]["area_beyond_camera_ball_field"]),
        r.via_drill == 0.25 == Y["pcb"]["via_drill"] and not r.blind_buried_vias
        and nc["Default"].track_width == 0.15 == ync["default"]["track"]
        and nc["Default"].clearance == 0.127 == ync["default"]["clearance"]
        and nc["Fine"].track_width == 0.10 == ync["fine"]["track"]
        and nc["Fine"].clearance == 0.10 == ync["fine"]["clearance"]
        and r.min_track == 0.10 and r.min_clearance == 0.10
        and cam_only and len(design.fine_areas) == 2
        and sorted(a.ref for a in design.fine_areas) == ["U2", "U3"]
        and fine_margins == [5.0, 5.0] and ync["fine"]["area_beyond_camera_ball_field"] == 5.0
        and list(ync["fine"]["layers"]) == ["F.Cu", "In2.Cu", "B.Cu"] == list(G.FINE_LAYERS)
        and len(e35_note) == 1 and all(l in e35_note[0] for l in ("F.Cu", "In2.Cu", "B.Cu"))
        and "0.100" in e35_note[0],
        "DEVIATION: CamPower (0.15 / 0.10) is a second class with the fine clearance for the camera "
        "supply balls, confined to the same areas")
    row("PCB d", "provisional 5 x 5 footprint, 0.5 mm pitch, 0.20 mm pads",
        "camera_footprint(): 25 round pads 0.20 mm on 0.5 mm, pad clearance 0.10 (OVM7692_BALLS)",
        len(P["U2"].footprint.pads) == 25 and all(abs(q.w - 0.20) < 1e-9 for q in P["U2"].footprint.pads)
        and G.OVM7692_PITCH == 0.5
        and {n: tuple(p.pads) for n, p in P["U2"].pins.items()}
        == {n: (b,) for b, (n, _t) in G.OVM7692_BALLS.items()}
        and P["U2"].footprint.name == P["U3"].footprint.name)
    kos = {k.name: k for k in design.keepouts}
    row("PCB e", "Vias tented and plugged on the underside, and no via at all inside the grain opening "
        "or the pad slot",
        "via_tenting %r (the top side is tented too: the cell lies on it), via_protection text; rule "
        "areas grain_opening_no_via, pad_slot_no_via and a second area %.1f mm larger round each"
        % (design.via_tenting, G.NO_VIA_MARGIN),
        design.via_tenting in ("bottom", "both") and "plugged" in design.via_protection
        and "BOTTOM" in design.via_protection
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
        "nothing taller than 0.7 mm under the LCD flex tail behind the connector",
        "8 placement keep-outs post_foot_*; height limits free_height, camera_hood_U2 / U3, lcd_tail",
        n_post == 8 and hl["free_height"].max_height == ko["free_height_above_pcb"] == 2.55
        and hl["camera_hood_U2"].max_height == 0.95 and hl["camera_hood_U3"].max_height == 0.95
        and hl["lcd_tail"].max_height == 0.7 and set(hl["free_height"].exempt) == {"U2", "U3"}
        and tuple(hl["lcd_tail"].exempt) == ("J1",))
    lands = [p for p in design.parts if p.ref.startswith("FL")]
    row("PCB h", "no soldered part above a ball foot or within 0.3 mm of its zone; under each ball foot "
        "the bottom side has a 2.5 mm circle with no via and no track and an unmasked 1.6 mm copper land",
        "foot_zone_n_top (placement, dia 2.5 + 2 x 0.3), foot_zone_n (B.Cu: no track, no via, no pour), "
        "FL1-FL3: bare dia 1.6 pads WITHOUT a net (mask open, no paste)",
        all(kos["foot_zone_%d" % i].tracks and kos["foot_zone_%d" % i].vias
            and kos["foot_zone_%d_top" % i].footprints for i in (1, 2, 3))
        and len(lands) == 3 and all(p.side == BOTTOM and not p.pins and p.footprint.pads[0].kind == "conn"
                                    and abs(p.footprint.pads[0].w - 1.6) < 1e-9 for p in lands)
        and sorted((p.x, p.y) for p in lands) == sorted(tuple(q) for q in ko["foot_zones"]["positions"]))
    zx, zy = Y["battery"]["pads"]["zone"]["x"], Y["battery"]["pads"]["zone"]["y"]
    tabs = [q for ref in ("BT1", "BT2") for q in pads(ref)]
    row("PCB i", "Two solder pads for the cell leads sit in the strip beyond the protection-board end "
        "of the cell",
        "BT1 (+, VBAT), BT2 (-, GND): 1.5 x 2.4 pads inside battery.pads.zone",
        len(tabs) == 2 and all(zx[0] - 1e-6 <= q.polygon.bounds[0] and q.polygon.bounds[2] <= zx[1] + 1e-6
                               and zy[0] - 1e-6 <= q.polygon.bounds[1] and q.polygon.bounds[3] <= zy[1] + 1e-6
                               for q in tabs) and on("VBAT", "BT1.1") and on("GND", "BT2.1"))
    bottom = sorted(p.ref for p in design.parts if p.side == BOTTOM and p.in_bom)
    row("PCB j", "Parts on the top side except the grain LEDs, photodiode and contact pads",
        "bottom side: D1-D16, PD1 (fitted), J2, FL1-FL3, three fiducials (bare copper)",
        bottom == sorted(["D%d" % i for i in range(1, 17)] + ["PD1"]))
    cam_box = all(max(abs(a - b) for a, b in zip(
        geometry.part_body_polygon(P[ref]).bounds,
        (xy[0] - G.CAM_BODY[0] / 2, xy[1] - G.CAM_BODY[1] / 2, xy[0] + G.CAM_BODY[0] / 2, xy[1] + G.CAM_BODY[1] / 2)))
        < 1e-6 for ref, xy in (("U2", G.CAM_L), ("U3", G.CAM_R)))
    from shapely.geometry import box as _box
    jb = geometry.part_body_polygon(P["J1"]).bounds
    jc = geometry.part_courtyard(P["J1"]).bounds
    sig = [q for q in pads("J1") if q.number != "MP"]
    pad_y0, pad_y1 = min(q.polygon.bounds[1] for q in sig), max(q.polygon.bounds[3] for q in sig)
    cell_y0 = bat["y"] - bat["dy"] / 2
    e24 = (abs(jb[1] - G.J1_MOUTH_Y) < 0.005 and abs(pad_y1 - G.J1_SIGNAL_PAD_END_Y) < 0.005
           and abs(jb[3] - (-11.70)) < 0.005 and abs(G.J1_MOUTH_Y - (-17.30)) < 1e-9
           and abs(G.J1_SIGNAL_PAD_END_Y - (-10.40)) < 1e-9 and abs(cell_y0 - pad_y1 - 0.20) < 0.005
           and abs(P["J1"].x) < 1e-9 and P["J1"].rotation == G.J1_ROTATION)
    # rev E: the YAML carries E24.  The placed land pattern against every J1 key of the YAML:
    # body box (x, y, dx, dy), body_y, mouth_y, pads_end_y, anchor; and the YAML against itself
    yj = next(p for p in Y["top_side_parts"] if p["ref"] == "J1")
    j1_yaml = (max(abs(a - b) for a, b in zip(jb, G.J1_BOX)) < 0.005
               and abs((jb[0] + jb[2]) / 2 - yj["x"]) < 0.005 and abs((jb[1] + jb[3]) / 2 - yj["y"]) < 0.005
               and abs(jb[1] - yj["body_y"][0]) < 0.005 and abs(jb[3] - yj["body_y"][1]) < 0.005
               and abs(jb[1] - yj["mouth_y"]) < 0.005 and abs(pad_y1 - yj["pads_end_y"]) < 0.005
               and abs(P["J1"].x - yj["anchor"][0]) < 1e-6 and abs(P["J1"].y - yj["anchor"][1]) < 1e-6
               and tuple(G.J1_YAML_ANCHOR) == tuple(G.J1_XY)
               and abs(yj["y"] - yj["dy"] / 2 - yj["mouth_y"]) < 1e-9)
    row("PCB k", "The cameras, the LCD connector and the battery are fixed mechanical interfaces",
        "U2, U3: body boxes equal the YAML boxes; battery_body placement keep-out from the YAML; J1: at the "
        "position E24 and the rev E YAML give (row PCB k2)",
        (P["U2"].x, P["U2"].y) == G.CAM_L and (P["U3"].x, P["U3"].y) == G.CAM_R and cam_box
        and (P["J1"].x, P["J1"].y) == G.J1_XY and P["J1"].rotation == G.J1_ROTATION and "battery_body" in kos
        and e24 and j1_yaml)
    # ---- J1 by its BODY: spec E24 and the rev E YAML against the placed land pattern -------------
    tz = Y["tub_keepouts"]["lcd_tail"]
    tail_zone = _box(-tz["half_w"], tz["y"][0], tz["half_w"], tz["y"][1])
    over = tail_zone.intersection(geometry.part_body_polygon(P["J1"])).area
    bat_ko = next(k for k in design.keepouts if k.name == "battery_body")
    bat_box = _box(bat["x"] - bat["dx"] / 2, cell_y0, bat["x"] + bat["dx"] / 2, bat["y"] + bat["dy"] / 2)
    ko_poly = geometry.keepout_polygon(bat_ko)
    notch = bat_box.difference(ko_poly)
    nb = notch.bounds if notch.area > 1e-9 else (0, 0, 0, 0)
    yn = Y["battery"]["board_keepout_notch"]
    yaml_notch = _box(yn["x"][0], yn["y"][0], yn["x"][1], yn["y"][1])
    notch_ok = (abs(notch.area - 2 * G.J1_COURTYARD_NOTCH["half_w"] * G.J1_COURTYARD_NOTCH["depth"]) < 1e-6
                and ko_poly.difference(bat_box).area < 1e-9 and abs(nb[0] - jc[0]) < 0.005 and abs(nb[2] - jc[2]) < 0.005
                and abs(nb[3] - jc[3]) < 0.005 and G.J1_COURTYARD_NOTCH["depth"] <= 0.30 + 1e-9
                and bat_box.intersection(geometry.part_body_polygon(P["J1"])).area < 1e-9
                and all(bat_box.distance(q.polygon) >= 0.195 for q in pads("J1"))
                # rev E: the keep-out is battery.body less EXACTLY battery.board_keepout_notch
                and notch.symmetric_difference(yaml_notch).area < 1e-6 and yn["ref"] == "J1"
                and abs(yn["y"][0] - cell_y0) < 1e-9
                and abs(yn["pad_to_cell_gap"] - (cell_y0 - pad_y1)) < 0.005)
    tail_ok = (abs(tz["y"][1] - G.J1_MOUTH_Y) < 1e-9 and over < 1e-9)
    row("PCB k2", "E24: J1 moves 0.5 mm toward the rear: mouth at y = -17.30, body to y = -11.70, signal pads "
        "end at y = -10.40 (0.20 mm clear of the cell at y = -10.20); the tail-fold zone starts at the mouth. "
        "Rev E YAML: top_side_parts J1 body box %.1f x %.1f centred on (%.1f, %.1f), anchor (%.1f, %.1f), "
        "mouth_y %.1f, pads_end_y %.1f; battery.board_keepout_notch x %s, y %s"
        % (G.J1_BOX[2] - G.J1_BOX[0], G.J1_BOX[3] - G.J1_BOX[1], G.J1_YAML_XY[0], G.J1_YAML_XY[1],
           G.J1_YAML_ANCHOR[0], G.J1_YAML_ANCHOR[1], yj["mouth_y"], yj["pads_end_y"], yn["x"], yn["y"]),
        "measured on the placed land pattern: anchor (%.2f, %.2f), body x %.2f to %.2f, y %.2f to %.2f (rear "
        "face = mouth), signal pads y %.2f to %.2f, cell edge %.2f, courtyard to %.2f; %.2f mm2 of the body "
        "inside the YAML's LCD-tail zone (y %.1f to %.1f, which starts at the mouth). Battery keep-out: the "
        "YAML box of the cell less a notch %.2f x %.2f mm = the YAML notch"
        % (P["J1"].x, P["J1"].y, jb[0], jb[2], jb[1], jb[3], pad_y0, pad_y1, cell_y0, jc[3], over,
           tz["y"][0], tz["y"][1], nb[2] - nb[0], nb[3] - nb[1]),
        e24 and j1_yaml and notch_ok and tail_ok,
        "the courtyard of the land pattern (0.5 mm beyond the pad ends) reaches %.2f mm into the YAML box of "
        "the cell: the placement keep-out has the notch the YAML records for it; body and pads are outside "
        "the cell. No departure since rev E" % (jc[3] - cell_y0))
    board_poly = geometry.outline_polygon(design.outline)
    margins = sorted((board_poly.exterior.distance(geometry.part_body_polygon(p))
                      if board_poly.contains(geometry.part_body_polygon(p)) else -1.0, p.ref)
                     for p in design.parts if p.placed)
    row("PCB l", "(YAML pcb.component_edge_clearance) part bodies stay %.1f mm inside the board edge"
        % G.EDGE_KEEP_IN,
        "smallest distance from a part body to the board edge: %.3f mm (%s), then %.3f mm (%s)"
        % (margins[0][0], margins[0][1], margins[1][0], margins[1][1]),
        margins[0][0] >= G.EDGE_KEEP_IN - 1e-6 and all(p.placed for p in design.parts))
    pin_bad = pin_table_problems(design)
    row("pin tables", "(task) the pin -> pad table of every library-backed part agrees with a second source",
        "U7, U11, U8, U10, Q1, U6, U4 against the installed KiCad symbols (pad numbers, pin names, "
        "footprint); D1-D16 against KiCad's pad 1 = cathode; RN1-RN6 against element n = pads n and "
        "9 - n: %s" % ("; ".join(pin_bad) if pin_bad else "all agree"),
        not pin_bad,
        "U6 is compared with the MX25R3235F of the same family and package, U4 with the LSM6DSM (spec: "
        "pin-compatible); U1 is proven by check_pinmap.py; U2 / U3, U9, U12, PD1 and J1 have no second source: "
        "their tables are the PROVISIONAL ones")
    bare = sorted(p.ref for p in design.parts if p.dnp and not p.in_bom)
    copper_only = sorted(p.ref for p in design.parts if not p.in_bom and (p.height_mm or 0.0) == 0.0)
    zero_bom = sorted(p.ref for p in design.parts if p.in_bom and (p.height_mm or 0.0) == 0.0)
    bot_bare = [P[r] for r in G.BARE_BOTTOM_COPPER_REFS if r in P]
    bare_ok = (not bare and not zero_bom and len(bot_bare) == len(G.BARE_BOTTOM_COPPER_REFS)
               and all(q.board_only and q.side == BOTTOM and not q.pins and (q.height_mm or 0.0) == 0.0
                       and not q.in_bom and len(q.footprint.pads) == 1
                       and q.footprint.pads[0].kind in ("conn", "smd") for q in bot_bare)
               and all(not p.in_bom or (p.height_mm or 0.0) > 0.0 for p in design.parts))
    row("bare copper", "(mechanical/cad/board_import.py, rev E) a copper-only footprint is one with zero height "
        "and no BOM line; it is tested by its own rules and a 'not fitted' mark does not exempt it; a "
        "zero-height component with a BOM line fails",
        "%d copper-only footprints (zero height, no BOM line): %s; none of them carries a 'not fitted' mark "
        "(%s); FL1-FL3 and the three bottom fiducials are board-only footprints with one netless pad; no "
        "BOM part has zero height (%s)"
        % (len(copper_only), ", ".join(copper_only), ", ".join(bare) or "none", ", ".join(zero_bom) or "none"),
        bare_ok)
    n_top = sum(1 for p in design.parts if "fiducial" in p.footprint_name.lower() and p.side == TOP)
    n_bot = sum(1 for p in design.parts if "fiducial" in p.footprint_name.lower() and p.side == BOTTOM)
    row("fiducials", "(task) at least three global fiducials per side", "FID1-FID3 top, FID4-FID6 bottom",
        n_top >= 3 and n_bot >= 3)
    row("E5", "Assembly (E5): lead-free (SAC305) reflow, RoHS-compliant parts; no conformal coating",
        "fab note; no leaded part is named in the BOM",
        any("SAC305" in n for n in design.fab_notes))
    status = {p.ref: p.fields.get("Status") for p in design.parts if p.in_bom}
    row("status", "(task) every BOM part carries an evidence status",
        "Part.fields['Status'] is RESEARCH or PROVISIONAL on all %d BOM parts" % len(status),
        all(v in ("RESEARCH", "PROVISIONAL") for v in status.values()))
    return out


# ---------------------------------------------------------------------------
# self-test: seeded defects
# ---------------------------------------------------------------------------
def _swap_nets(design, node_a, node_b):
    """exchange the nets of two pins"""
    a, b = tuple(node_a.split(".", 1)), tuple(node_b.split(".", 1))
    na = next(n for n in design.nets.values() if a in n.nodes)
    nb = next(n for n in design.nets.values() if b in n.nodes)
    na.nodes[na.nodes.index(a)] = b
    nb.nodes[nb.nodes.index(b)] = a


def _move(design, node, new_net):
    key = tuple(node.split(".", 1))
    for n in design.nets.values():
        if key in n.nodes:
            n.nodes.remove(key)
    design.net(new_net, node)


def _remove(design, ref):
    design.parts[:] = [p for p in design.parts if p.ref != ref]
    for n in design.nets.values():
        n.nodes[:] = [q for q in n.nodes if q[0] != ref]


def _repad(design, ref, table):
    """give pins of ``ref`` other pads: {pin name: pad number}"""
    part = design.part(ref)
    for name, pad in table.items():
        old = part.pins[name]
        part.pins[name] = old.__class__(name, (str(pad),), old.etype)


def _mirror_j1(design):
    """the J1 pad table as it would be with tail pin n on pad n"""
    part = design.part("J1")
    _repad(design, "J1", {fn: 11 - int(pin.pads[0]) for fn, pin in part.pins.items() if fn != "MP"})


def _dnp(design, ref):
    design.part(ref).dnp = True


SEEDED = [
    ("charger MPN left as the MCP73831", lambda d: setattr(d.part("U9"), "mpn", "MCP73831T-2ACI/OT"), "E1 a"),
    ("ISET resistor 49.9k instead of 6.81k", lambda d: setattr(d.part("R11"), "value", "49k9"), "E1 c"),
    ("NTC1 moved from TS to NTC_SENSE (one NTC shared)", lambda d: _move(d, "RT1.1", "NTC_SENSE"), "E1 d"),
    ("CHG pull-up to VDDUSB instead of V2V8", lambda d: _move(d, "R13.2", "VDDUSB"), "E1 e"),
    ("Q1 drain on CHG_ISET instead of TS", lambda d: _move(d, "Q1.D", "CHG_ISET"), "E1 f"),
    ("gate pull-down R12 removed", lambda d: _remove(d, "R12"), "E1 f"),
    ("fallback resistor R14 fitted", lambda d: setattr(d.part("R14"), "dnp", False), "E1 g"),
    ("charger ball map bypassed (TS and ISET exchanged on U9 only)",
     lambda d: d.part("U9").pins.update(TS=d.part("U9").pins["ISET"].__class__("TS", ("B2",), "passive"),
                                        ISET=d.part("U9").pins["ISET"].__class__("ISET", ("B1",), "passive")),
     "E1 a"),
    ("NTC part number not changed (NCP15XH103F03RC)", lambda d: setattr(d.part("RT2"), "mpn", "NCP15XH103F03RC"), "E2 a"),
    ("NTC2 placed 3 mm from the cell", lambda d: d.part("RT2").place(-9.4, 3.2, 0.0), "E2 a"),
    ("near-infrared LED left as the SFH 4053", lambda d: setattr(d.part("D2"), "mpn", "SFH 4053"), "grain b"),
    ("LED D5 reversed", lambda d: _swap_nets(d, "D5.A", "D5.K"), "grain"),
    ("test point TP3 missing", lambda d: _remove(d, "TP3"), "E4"),
    ("test point TP2 on VDDA instead of V2V8", lambda d: _move(d, "TP2.1", "VDDA"), "E4"),
    ("underside pads D- and D+ exchanged", lambda d: _swap_nets(d, "J2.DM", "J2.DP"), "pads"),
    ("underside pad row mirrored (pad 1 at +x)", lambda d: d.part("J2").place(0.0, -17.0, 180.0), "pads"),
    ("EXTMODE tied low", lambda d: _move(d, "J1.EXTMODE", "GND"), "lcd a"),
    ("PWDN series resistor of the left camera bridged", lambda d: _move(d, "U2.PWDN", "CAM_L_PWDN_MCU"), "cam 2d"),
    ("SCCB pull-up R8 to V2V8 instead of V2V8_CAM", lambda d: _move(d, "R8.2", "V2V8"), "cam 1"),
    ("BOOT0 pull-down 100k instead of 10k", lambda d: setattr(d.part("R2"), "value", "100k"), "boot nrst"),
    # ---- the four defects the circuit review found no checker for, and their relatives ----------
    ("U7 on another SOT-23 pin order (VIN and VOUT pads exchanged)",
     lambda d: _repad(d, "U7", {"VOUT": 3, "VIN": 2}), "pin tables"),
    ("U11 on another SOT-23-5 pin order (GND and EN pads exchanged)",
     lambda d: _repad(d, "U11", {"GND": 3, "EN": 2}), "pin tables"),
    ("U11 left as the MCP1700 without enable", lambda d: setattr(d.part("U11"), "mpn", "MCP1700T-3302E/TT"), "rail VDDUSB"),
    ("U11 enable on VBUS_D instead of V2V8 (always on in the cradle: E26 undone)",
     lambda d: _move(d, "U11.EN", "VBUS_D"), "rail VDDUSB"),
    ("U12 enable (CE) tied to GND instead of its output (no reverse blocking)",
     lambda d: _move(d, "U12.CE", "GND"), "rail VBUS b"),
    ("U12 turned round (VIN and VOUT exchanged)", lambda d: _swap_nets(d, "U12.VIN", "U12.VOUT"), "rail VBUS"),
    ("U12 pin table bypassed (CE on pad 5, ST on pad 3)",
     lambda d: _repad(d, "U12", {"CE": 5, "ST": 3}), "rail VBUS b"),
    ("the Schottky left in (U12 still a B0530WS)", lambda d: setattr(d.part("U12"), "mpn", "B0530WS-7-F"), "rail VBUS b"),
    ("Q1 gate and source pads exchanged", lambda d: _repad(d, "Q1", {"G": 2, "S": 1}), "pin tables"),
    ("flash SO and SI pads exchanged in the pin table", lambda d: _repad(d, "U6", {"SO": 5, "SI": 2}), "pin tables"),
    ("R31 to GND instead of V2V8", lambda d: _move(d, "R31.2", "GND"), "grain d"),
    ("R31 left at 1 Mohm", lambda d: setattr(d.part("R31"), "value", "1M"), "grain d"),
    ("J1 pad table not mirrored (tail pin n on pad n)", _mirror_j1, "lcd c"),
    ("J1 turned by 180 degrees", lambda d: d.part("J1").place(G.J1_XY[0], G.J1_XY[1], 180.0), "lcd c"),
    ("pin-1 edge of the LCD tail flipped to 'right' with no new source (design rebuilt with it)",
     "LCD_EDGE", "lcd c"),
    ("LCD SCLK and VSSA pads exchanged at J1",
     lambda d: _repad(d, "J1", {"SCLK": d.part("J1").pins["VSSA"].pads[0],
                                "VSSA": d.part("J1").pins["SCLK"].pads[0]}), "lcd c"),
    ("VBUS sense divider back behind the series switch", lambda d: _move(d, "R15.1", "VBUS_D"), "rail VBUS"),
    ("VBUS_D capacitor C22 back at 1 uF", lambda d: setattr(d.part("C22"), "value", "1u"), "rail VDDUSB"),
    ("VDDUSB capacitor C23 back at 1 uF (E27)", lambda d: setattr(d.part("C23"), "value", "1u"), "rail VDDUSB"),
    ("charger input capacitor C26 back at 1 uF (E27)", lambda d: setattr(d.part("C26"), "value", "1u"), "E1 b"),
    ("charger output capacitor C27 back at 1 uF (E27)", lambda d: setattr(d.part("C27"), "value", "1u"), "E1 b"),
    ("J1 moved 0.7 mm toward the cell", lambda d: d.part("J1").place(G.J1_XY[0], G.J1_XY[1] + 0.7, 0.0), "PCB k"),
    ("J1 anchor put on the YAML BODY centre (anchor / centre confused)",
     lambda d: d.part("J1").place(G.J1_YAML_XY[0], G.J1_YAML_XY[1], 0.0), "PCB k"),
    ("J1 back on its rev D position (anchor 0.5 mm forward: E24 not applied)",
     lambda d: d.part("J1").place(G.J1_XY[0], G.J1_XY[1] + 0.5, 0.0), "PCB k"),
    ("ball-foot land FL2 marked not fitted (the rev D workaround)", lambda d: _dnp(d, "FL2"), "bare copper"),
    ("bottom fiducial FID5 marked not fitted (the rev D workaround)", lambda d: _dnp(d, "FID5"), "bare copper"),
    ("a real bottom-side part (D3) marked not fitted", lambda d: _dnp(d, "D3"), "E1 g"),
    ("test pad TP4 marked not fitted (would hide it from the mechanical check)", lambda d: _dnp(d, "TP4"), "bare copper"),
    ("C13 placed 0.1 mm from the board edge", lambda d: d.part("C13").place(20.80, 0.0, 90.0), "PCB l"),
]


def selftest():
    lines, missed = [], 0
    for what, mutate, expect in SEEDED:
        saved_edge, saved_flag = G.LCD_TAIL_PIN1_EDGE, G.LCD_TAIL_PIN1_AT_PAD1
        try:
            if mutate == "LCD_EDGE":                 # a module-level fact: flip it, then build the design
                G.LCD_TAIL_PIN1_EDGE = "right"
                G.LCD_TAIL_PIN1_AT_PAD1 = G.lcd_tail_pin1_at_pad1()
                design = G.gl1_main_design()
            else:
                design = G.gl1_main_design()
                mutate(design)
            bad = [r[0] for r in rules(design) if not r[3]]
        except Exception as exc:                     # a defect that breaks the evaluation is caught too
            bad = ["EXCEPTION %s: %s" % (type(exc).__name__, exc)]
        finally:
            G.LCD_TAIL_PIN1_EDGE, G.LCD_TAIL_PIN1_AT_PAD1 = saved_edge, saved_flag
        hit = [b for b in bad if b.startswith(expect) or b.startswith("EXCEPTION")]
        lines.append("  %s  %s -> %s" % ("caught" if hit else "MISSED", what, ", ".join(bad) or "no row failed"))
        missed += 0 if hit else 1
    return lines, missed


def markdown(rows):
    lines = ["| Spec rule | What DESIGN_SPEC section 4 says | Where it is in the netlist | Result |",
             "|---|---|---|---|"]
    for r in rows:
        rid, spec, where, note = r[0], r[1], r[2], r[4]
        st = row_status(r)
        lines.append("| %s | %s | %s%s | %s |" % (rid, spec, where, (" *(%s)*" % note) if note else "",
                                                 st if st == "pass" else "**%s**" % st))
    return "\n".join(lines) + "\n\n" + counts_text(rows) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--markdown", help="write the table as Markdown to this file")
    ap.add_argument("--selftest", action="store_true", help="seed defects and require each to fail a row")
    args = ap.parse_args(argv)
    rows = rules(G.gl1_main_design())
    bad = [r for r in rows if row_status(r) == "FAIL"]
    for r in rows:
        print("%-10s %-16s %s" % (row_status(r), r[0], r[2]))
        if r[4]:
            print("           %-16s note: %s" % ("", r[4]))
    print("\nspec rules: " + counts_text(rows))
    missed = 0
    if args.selftest:
        lines, missed = selftest()
        print("\nSELF-TEST: %d seeded defects, %d caught, %d missed" % (len(SEEDED), len(SEEDED) - missed, missed))
        print("\n".join(lines))
    if args.markdown:
        with open(args.markdown, "w", encoding="utf-8") as fh:
            fh.write(markdown(rows))
    return 1 if (bad or missed) else 0


if __name__ == "__main__":
    sys.exit(main())
