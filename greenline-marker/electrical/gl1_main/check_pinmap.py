#!/usr/bin/python3
"""Proof of the GL-1 pin map against ST's open pin data, and its export.

    /usr/bin/python3 -I -B electrical/gl1_main/check_pinmap.py --pindata DIR [--export] [--report FILE]

DIR holds the two DATA files of github.com/STMicroelectronics/STM32_open_pin_data
(raw.githubusercontent.com/STMicroelectronics/STM32_open_pin_data/master/...):

    mcu/STM32U585RITx.xml
    mcu/IP/GPIO-STM32U5x_gpio_v1_0_Modes.xml

They are third-party data: keep them OUTSIDE the repository, never execute
anything from that directory, run this script with ``-I``.  The script reads
them as text, refuses a DOCTYPE / ENTITY declaration and parses them with the
standard library.  Without ``--pindata`` (or ``GL1_PINDATA``) the script falls
back to the installed KiCad symbol ``MCU_ST_STM32U5:STM32U585RITx``: pad
numbers, pin names and the existence of each function can then still be
checked, alternate-function NUMBERS cannot, and the result says PARTIAL.

What is proven for every MCU pin of the netlist (``gl1_main_design.py``):

 A  pad number and pin name agree with the package (all 64 pads);
 B  every row of PINMAP sits on the pad the netlist connects, the alternate
    function it names exists on that pin with that AF number, analog
    functions (ADC channel, OPAMP1 pins, LSE) exist on that pin;
 C  IMU_INT1 is on a wake-up pin (PWR_WKUPx); the EXTI lines in use are distinct;
 D  no pin is used twice (the BOOT0 pad is the one declared exception), no
    I/O pad is connected without a PINMAP row, the supply pads are on their rails;
 E  the rows DESIGN_SPEC fixes are where the spec text puts them (the spec is
    parsed), PWDN is not on PA9 / PA2 / PC10, XVCLK leaves PA8 through 33 ohm,
    EXTCOMIN is an LPTIM1 / LPTIM3 channel, SPI1_MISO is PB4;
 F  the difference to firmware/hal/stm32u5/gl_pins.h is exactly the rows
    marked CHANGED, each with its old pin and a reason;
 G  ROM bootloader: every pin the bootloader drives or listens on (table
    below, PROVISIONAL: from memory of ST AN2606, the note could not be read)
    is connected only to things on an explicit allow-list, each derived from
    the netlist.  That the PERIPHERAL FUNCTION exists on each of those pins is
    verified from the pin data; that the ROM uses it is not.

``--selftest`` seeds defects into the pin map (a wrong AF number, PWDN on
PC10, an SCCB line on a pin the bootloader drives, the wake-up input on a pin
that is none, an ADC input on a pin without ADC, one pad used twice, a moved
SPEC row, an undeclared change, a swapped pad name, the PA3 pull removed) and
requires each of them to be caught.

Exit status 0: every check passed (PARTIAL in fallback mode is still 0, and
is printed in capitals).  Exit status 1: a check failed.  ``--export`` writes
``pinmap.json`` next to this file, with the verification result inside.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.normpath(os.path.join(HERE, "..", "tools"))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
for _p in (TOOLS, HERE):                      # -I removes the script directory from sys.path
    if _p not in sys.path:
        sys.path.insert(0, _p)

import gl1_main_design as G                   # noqa: E402

MCU_XML = "STM32U585RITx.xml"
GPIO_XML = "GPIO-STM32U5x_gpio_v1_0_Modes.xml"
#: SHA-256 of the files this map was first checked with (2026-11-11).  Another
#: hash is not an error (ST updates the data); it is printed.
REFERENCE_SHA256 = {
    MCU_XML: "369bb06cf9794840572c58a6a058d68aa285466a49f9a4c731534bf43c7d8325",
    GPIO_XML: "253229fd2510d58784118e5793eb54b4042cdb16951997b7a0cf8f1b5429ea49",
}
KICAD_SYMBOLS = "/usr/share/kicad/symbols/MCU_ST_STM32U5.kicad_sym"
KICAD_SYMBOL = "STM32U585RITx"
GL_PINS_H = os.path.join(ROOT, "firmware", "hal", "stm32u5", "gl_pins.h")
SPEC_MD = os.path.join(ROOT, "design", "DESIGN_SPEC.md")

#: PROVISIONAL - from memory of ST AN2606 (STM32U575 / 585 system bootloader);
#: the application note could not be read.  pin -> (peripheral signal, role).
#: role "drive": the ROM configures the pin as a push-pull output;
#:      "listen": input or open-drain line the ROM samples while it looks for
#:      its host interface.  firmware/hal/stm32u5/gl_pins.h carries the same
#: table (GL_PINS_BOOTLOADER_TABLE); section F compares the two.
BOOTLOADER_PINS = {
    "PA9": ("USART1_TX", "drive"), "PA10": ("USART1_RX", "listen"),
    "PA2": ("USART2_TX", "drive"), "PA3": ("USART2_RX", "listen"),
    "PC10": ("USART3_TX", "drive"), "PC11": ("USART3_RX", "listen"),
    "PB6": ("I2C1_SCL", "listen"), "PB7": ("I2C1_SDA", "listen"),
    "PB10": ("I2C2_SCL", "listen"), "PB11": ("I2C2_SDA", "listen"),
    "PC0": ("I2C3_SCL", "listen"), "PC1": ("I2C3_SDA", "listen"),
    "PA4": ("SPI1_NSS", "listen"), "PA5": ("SPI1_SCK", "listen"),
    "PA6": ("SPI1_MISO", "drive"), "PA7": ("SPI1_MOSI", "listen"),
    "PB12": ("SPI2_NSS", "listen"), "PB13": ("SPI2_SCK", "listen"),
    "PB14": ("SPI2_MISO", "drive"), "PB15": ("SPI2_MOSI", "listen"),
    "PB8": ("FDCAN1_RX", "listen"), "PB9": ("FDCAN1_TX", "drive"),
    "PA11": ("USB_OTG_FS_DM", "listen"), "PA12": ("USB_OTG_FS_DP", "listen"),
}
#: bootloader outputs that may sit at LOW (an SPI slave's MISO); the USART and
#: CAN transmit pins idle HIGH.  PROVISIONAL like the table above.
BOOTLOADER_MAY_DRIVE_LOW = ("PA6", "PB14")
#: spec section 4: "must not use a pin that the ROM bootloader drives as an
#: output (the USART transmit pins PA9, PA2 and PC10 ...)"
SPEC_PWDN_FORBIDDEN = ("PA9", "PA2", "PC10")

VDD = 2.8                                     # V2V8
#: PROVISIONAL (memory of DS13086): absolute maximum output current of one I/O
IO_ABS_MAX_MA = 20.0
#: rails by behaviour while the ROM bootloader runs (marker in the cradle)
GROUND = ("GND",)
ALWAYS_ON = ("V2V8", "VDDA")
CAMERA_RAIL = ("V2V8_CAM", "CAM_L_DVDD", "CAM_R_DVDD")
OTHER_RAILS = ("VBAT", "VBUS", "VBUS_D", "VDDUSB")
CAMERAS = ("U2", "U3")


# ---------------------------------------------------------------------------
# reading the data
# ---------------------------------------------------------------------------
def _read_xml(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError("%s: larger than expected for this data file" % path)
    if b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:
        raise ValueError("%s: DOCTYPE / ENTITY declarations are refused" % path)
    return ET.fromstring(raw), hashlib.sha256(raw).hexdigest()


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def port_name(name):
    """'PC14-OSC32_IN (PC14)' -> 'PC14', 'PH3-BOOT0' -> 'PH3', 'PA13 (JTMS/SWDIO)' -> 'PA13'."""
    return re.split(r"[-\s(]", name.strip(), maxsplit=1)[0]


class PinData:
    """pad -> name, type, signals; (pin, signal) -> AF number."""

    def __init__(self):
        self.source = ""
        self.pads = {}                  # pad number (int) -> {"name", "full", "type", "signals"}
        self.af = {}                    # (pin, signal) -> AF number or None when unknown
        self.has_af_numbers = False
        self.hashes = {}

    @classmethod
    def from_st(cls, directory):
        self = cls()
        mcu, h1 = _read_xml(os.path.join(directory, MCU_XML))
        gpio, h2 = _read_xml(os.path.join(directory, GPIO_XML))
        self.hashes = {MCU_XML: h1, GPIO_XML: h2}
        self.source = "ST STM32_open_pin_data (%s, package %s, %s)" % (
            mcu.get("RefName"), mcu.get("Package"), mcu.get("Line"))
        if mcu.get("RefName") != "STM32U585RITx" or mcu.get("Package") != "LQFP64":
            raise ValueError("the MCU file is for %s / %s, not STM32U585RITx / LQFP64"
                             % (mcu.get("RefName"), mcu.get("Package")))
        for el in mcu.iter():
            if _local(el.tag) != "Pin":
                continue
            pad = int(el.get("Position"))
            signals = [s.get("Name") for s in el if _local(s.tag) == "Signal"]
            self.pads[pad] = {"name": port_name(el.get("Name")), "full": el.get("Name"),
                              "type": el.get("Type"), "signals": signals}
        for gp in gpio.iter():
            if _local(gp.tag) != "GPIO_Pin":
                continue
            pin = port_name(gp.get("Name"))
            for ps in gp:
                if _local(ps.tag) != "PinSignal":
                    continue
                for el in ps.iter():
                    if _local(el.tag) == "PossibleValue" and el.text:
                        m = re.match(r"GPIO_AF(\d+)_", el.text.strip())
                        if m:
                            self.af[(pin, ps.get("Name"))] = int(m.group(1))
        self.has_af_numbers = True
        return self

    @classmethod
    def from_kicad(cls, path=KICAD_SYMBOLS, symbol=KICAD_SYMBOL):
        self = cls()
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        start = text.index('(symbol "%s"' % symbol)
        end = text.find('\n  (symbol "', start + 10)
        block = text[start:end if end > 0 else len(text)]
        self.source = "installed KiCad library %s:%s (no AF numbers)" % (
            os.path.basename(path), symbol)
        for chunk in re.split(r"\(pin\s", block)[1:]:
            m = re.search(r'\(name "([^"]+)".*?\(number "([^"]+)"', chunk, re.S)
            if not m:
                continue
            etype = chunk.split()[0]
            alts = re.findall(r'\(alternate "([^"]+)"', chunk)
            name = port_name(m.group(1))
            kind = ("Power" if etype.startswith("power")
                    or name in ("VSS", "VDD", "VSSA", "VDDA", "VBAT", "VCAP", "VDDUSB") else
                    "Reset" if name == "NRST" else "I/O")
            self.pads[int(m.group(2))] = {"name": name, "full": m.group(1), "type": kind,
                                          "signals": alts + (["GPIO"] if kind == "I/O" else [])}
        return self

    def by_name(self, pin):
        return [(pad, e) for pad, e in sorted(self.pads.items()) if e["name"] == pin]

    def signals(self, pin):
        out = []
        for _pad, e in self.by_name(pin):
            out += e["signals"]
        return out


def read_gl_pins(path=GL_PINS_H):
    """(rows, bootloader rows) of the firmware header: rows = {signal: (pin, pad, source)}."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    rows = {}
    for m in re.finditer(r"X\(GL_PIN_(\w+),\s*([A-H]),\s*(\d+),\s*(\d+),\s*GL_PINFN_\w+,\s*\d+,\s*"
                         r"GL_PINSRC_(\w+)\)", text):
        rows[m.group(1)] = ("P%s%s" % (m.group(2), m.group(3)), int(m.group(4)), m.group(5))
    boot = {}
    for m in re.finditer(r"X\(([A-H]),\s*(\d+),\s*(\w+),\s*([01])\)", text):
        boot["P%s%s" % (m.group(1), m.group(2))] = (m.group(3), "drive" if m.group(4) == "1" else "listen")
    return rows, boot


def read_spec_dcmi(path=SPEC_MD):
    """The DCMI assignment as written in DESIGN_SPEC section 4: {name: (pin, pad, AF)}."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    out = {}
    for m in re.finditer(r"\b(D[0-7]|PIXCLK|HSYNC|VSYNC) (P[A-H]\d+) pad (\d+) AF(\d+)", text):
        out[m.group(1)] = (m.group(2), int(m.group(3)), int(m.group(4)))
    m = re.search(r"MCO (PA\d+) pad (\d+)", text)
    if m:
        out["MCO"] = (m.group(1), int(m.group(2)), None)
    m = re.search(r"must be (PB\d+) \(pad (\d+), AF(\d+)\)", text)
    if m:
        out["SPI1_MISO"] = (m.group(1), int(m.group(2)), int(m.group(3)))
    m = re.search(r"LPTIM1_CH1 on (PB\d+) \(pad (\d+)\)", text)
    if m:
        out["EXTCOMIN"] = (m.group(1), int(m.group(2)), None)
    for name, pat in (("USB_DM", r"(PA\d+) = D- \(pad (\d+)\)"), ("USB_DP", r"(PA\d+) = D\+ \(pad (\d+)\)")):
        m = re.search(pat, text)
        if m:
            out[name] = (m.group(1), int(m.group(2)), None)
    return out


# ---------------------------------------------------------------------------
# netlist helpers
# ---------------------------------------------------------------------------
def ohms(value):
    """'68R' -> 68, '2k2' -> 2200, '49k9' -> 49900, '1M' -> 1e6, '4x220R' -> 220."""
    v = value.split("x")[-1].strip()
    m = re.match(r"^(\d+)([RkM])(\d*)$", v)
    if not m:
        return None
    mult = {"R": 1.0, "k": 1e3, "M": 1e6}[m.group(2)]
    return (float(m.group(1)) + (float("0." + m.group(3)) if m.group(3) else 0.0)) * mult


class Netlist:
    def __init__(self, design):
        self.d = design
        self.parts = design.parts_by_ref
        self.pin_net = {}
        for net in design.nets.values():
            for node in net.nodes:
                self.pin_net[node] = net.name

    def net(self, ref, pin):
        return self.pin_net.get((ref, pin))

    def nodes(self, net):
        return list(self.d.nets[net].nodes) if net in self.d.nets else []

    def other_side(self, ref, pin):
        """For a series element: (resistance, net on the other terminal) or None."""
        part = self.parts[ref]
        prefix = part.ref_prefix
        if prefix in ("R", "RT") and len(part.pins) == 2:
            other = "2" if pin == "1" else "1"
            r = 10e3 if prefix == "RT" else ohms(part.value)
            return r, self.net(ref, other)
        if prefix == "RN":
            other = ("B" if pin[0] == "A" else "A") + pin[1:]
            return ohms(part.value), self.net(ref, other)
        return None

    def pulls(self, net):
        """[(resistance, rail)] of resistors from ``net`` straight to a rail or ground."""
        out = []
        for ref, pin in self.nodes(net):
            o = self.other_side(ref, pin)
            if o and o[1] in GROUND + ALWAYS_ON + CAMERA_RAIL + OTHER_RAILS:
                out.append((o[0], o[1], ref))
        return out

    def reach(self, net, limit=3):
        """Terminals reachable from ``net`` through series resistors:
        [(ref, pin, series resistance, path)] - IC pins, diodes, capacitors, pads, rails."""
        out, seen = [], set()
        stack = [(net, 0.0, (), 0)]
        while stack:
            cur, r, path, depth = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            for ref, pin in self.nodes(cur):
                if ref == "U1":
                    continue
                o = self.other_side(ref, pin)
                if o is None:
                    out.append((ref, pin, r, path))
                elif o[1] is None:
                    continue
                elif o[1] in GROUND + ALWAYS_ON + CAMERA_RAIL + OTHER_RAILS:
                    out.append(("rail:" + o[1], "", r + (o[0] or 0.0), path + (ref,)))
                elif depth < limit and ref not in path:
                    stack.append((o[1], r + (o[0] or 0.0), path + (ref,), depth + 1))
        return out


# ---------------------------------------------------------------------------
# the checks
# ---------------------------------------------------------------------------
class Report:
    def __init__(self):
        self.lines = []
        self.fails = []
        self.provisional = []
        self.counts = {}

    def section(self, title):
        self.lines.append("")
        self.lines.append(title)
        self.lines.append("-" * len(title))
        self._sec = title.split()[0]
        self.counts.setdefault(self._sec, [0, 0])

    def ok(self, text):
        self.lines.append("  ok    " + text)
        self.counts[self._sec][0] += 1

    def fail(self, text):
        self.lines.append("  FAIL  " + text)
        self.fails.append(text)
        self.counts[self._sec][1] += 1

    def note(self, text):
        self.lines.append("        " + text)

    def prov(self, text):
        self.lines.append("  PROV  " + text)
        self.provisional.append(text)

    def check(self, cond, text, detail=""):
        (self.ok if cond else self.fail)(text + ((" - " + detail) if detail and not cond else ""))
        return cond


def run(pindata, design, rep):
    nl = Netlist(design)
    rows = G.pinmap_rows()
    u1 = design.part("U1")
    io_pads = {pad: e for pad, e in pindata.pads.items() if e["type"] == "I/O"}

    # ---- A: the package ---------------------------------------------------------------
    rep.section("A  package: 64 pads, names and numbers (%s)" % pindata.source)
    rep.check(len(pindata.pads) == 64, "the data file lists 64 pads", "found %d" % len(pindata.pads))
    bad = 0
    for pad in range(1, 65):
        want = pindata.pads.get(pad, {}).get("name")
        name = G.mcu_pin_name(pad)
        pin = u1.pins.get(name)
        got = G.MCU_PAD_NAMES[pad - 1]
        if want != got or pin is None or tuple(pin.pads) != (str(pad),):
            bad += 1
            rep.fail("pad %d: netlist %s, data %s" % (pad, got, want))
    rep.check(bad == 0, "all 64 pads of U1: pin name and pad number equal the data")
    rep.check(len(u1.pins) == 64, "U1 has exactly 64 pins in the netlist", "%d" % len(u1.pins))

    # ---- B: every row of the pin map ---------------------------------------------------
    rep.section("B  pin map rows: pad, alternate function, analog function")
    for r in rows:
        pin, sig = r["pin"], r["signal"]
        sigs = pindata.signals(pin)
        where = "%-13s %-5s pad %2d" % (sig, pin, r["pad"])
        entry = pindata.by_name(pin)
        if not entry or entry[0][0] != r["pad"]:
            rep.fail("%s: the pad is not %s in the data" % (where, pin))
            continue
        if nl.net("U1", pin) != r["net"]:
            rep.fail("%s: PINMAP says net %s, the netlist has %s" % (where, r["net"], nl.net("U1", pin)))
            continue
        mode = r["mode"]
        if mode == "AF":
            fn = r["function"]
            if fn not in sigs:
                rep.fail("%s: %s is not a function of %s" % (where, fn, pin))
            elif not pindata.has_af_numbers:
                rep.ok("%s: %s exists on the pin (AF%s NOT verified: no AF numbers in this source)"
                       % (where, fn, r["af"]))
            else:
                af = pindata.af.get((pin, fn))
                rep.check(af == r["af"], "%s: %s = AF%s" % (where, fn, r["af"]), "data says AF%s" % af)
        elif mode == "ANALOG":
            fns = [f.strip() for f in r["function"].split("/")]
            missing = [f for f in fns if f not in sigs]
            rep.check(not missing, "%s: analog %s" % (where, " + ".join(fns)),
                      "missing on the pin: %s" % ", ".join(missing))
        elif mode == "STRAP":
            if pindata.has_af_numbers:
                rep.check("BOOT0" in entry[0][1]["full"], "%s: the pad is the BOOT0 pad (%s)"
                          % (where, entry[0][1]["full"]))
            else:
                rep.ok("%s: pad %d is %s (this source does not name BOOT0: NOT verified)"
                       % (where, r["pad"], entry[0][1]["full"]))
        else:
            rep.check("GPIO" in sigs and entry[0][1]["type"] == "I/O",
                      "%s: %s on an I/O pad" % (where, mode))
            m = re.search(r"PWR_WKUP\d", r["function"])
            if m:
                rep.check(m.group(0) in sigs, "%s: %s exists on the pin" % (where, m.group(0)))

    # ---- C: wake-up, EXTI, ADC, OPAMP ----------------------------------------------------
    rep.section("C  wake-up pin, EXTI lines, ADC channels, OPAMP1")
    by_sig = {r["signal"]: r for r in rows}
    wk = [s for s in pindata.signals(by_sig["IMU_INT1"]["pin"]) if s.startswith("PWR_WKUP")]
    rep.check(bool(wk), "IMU_INT1 on %s is a wake-up pin (%s)" % (by_sig["IMU_INT1"]["pin"], ", ".join(wk)))
    wk = [s for s in pindata.signals(by_sig["VBUS_SENSE"]["pin"]) if s.startswith("PWR_WKUP")]
    rep.note("VBUS_SENSE on %s: %s" % (by_sig["VBUS_SENSE"]["pin"], ", ".join(wk) or "not a wake-up pin"))
    exti = {}
    for r in rows:
        if r["mode"] == "EXTI":
            exti.setdefault(int(re.sub(r"\D", "", r["pin"])), []).append(r["signal"])
    rep.check(all(len(v) == 1 for v in exti.values()), "EXTI lines are used once each: %s"
              % ", ".join("EXTI%d %s" % (k, "/".join(v)) for k, v in sorted(exti.items())))
    for sig in ("VBAT_SENSE", "NTC_SENSE", "OPAMP_VOUT"):
        chans = [s for s in pindata.signals(by_sig[sig]["pin"]) if s.startswith("ADC1_IN")]
        named = [f.strip() for f in by_sig[sig]["function"].split("/") if f.strip().startswith("ADC1_IN")]
        rep.check(bool(named) and all(n in chans for n in named),
                  "%s on %s: %s exists" % (sig, by_sig[sig]["pin"], ", ".join(named)), "pin has %s" % chans)
    for sig, fn in (("OPAMP_VINP", "OPAMP1_VINP"), ("OPAMP_VINM", "OPAMP1_VINM"), ("OPAMP_VOUT", "OPAMP1_VOUT")):
        owners = [e["name"] for e in pindata.pads.values() if fn in e["signals"]]
        rep.check(owners == [by_sig[sig]["pin"]], "%s is %s, the only pad with %s" % (sig, by_sig[sig]["pin"], fn),
                  "pads with it: %s" % owners)

    # ---- D: no pin twice, nothing unlisted, supplies ---------------------------------------
    rep.section("D  every pad accounted for")
    users = {}
    for r in rows:
        users.setdefault(r["pin"], []).append(r["signal"])
    for pin, sigs in sorted(users.items()):
        if len(sigs) > 1:
            rep.check(tuple(sigs) == G.SHARED_PINS.get(pin) or tuple(reversed(sigs)) == G.SHARED_PINS.get(pin),
                      "%s carries %s: the declared strap + GPIO pair" % (pin, " + ".join(sigs)),
                      "not declared in SHARED_PINS")
    rep.check(all(len(s) == 1 or p in G.SHARED_PINS for p, s in users.items()),
              "no pin is used twice (%d rows on %d pads)" % (len(rows), len(users)))
    unlisted = [e["name"] for pad, e in sorted(io_pads.items())
                if nl.net("U1", e["name"]) and e["name"] not in users]
    rep.check(not unlisted, "no I/O pad is connected without a PINMAP row", ", ".join(unlisted))
    free = [e["name"] for pad, e in sorted(io_pads.items()) if e["name"] not in users]
    rep.check(not free, "all %d I/O pads carry a signal (no spare pad)" % len(io_pads),
              "free: %s" % ", ".join(free))
    want = {"VBAT": "V2V8", "VSSA": "GND", "VDDA": "VDDA", "VSS": "GND", "VDD": "V2V8",
            "VCAP": "VCAP", "VDDUSB": "VDDUSB", "NRST": "NRST"}
    bad = []
    for pad, e in sorted(pindata.pads.items()):
        if e["type"] != "I/O":
            got = nl.net("U1", G.mcu_pin_name(pad))
            if got != want.get(e["name"]):
                bad.append("pad %d %s on %s" % (pad, e["name"], got))
    rep.check(not bad, "the %d supply / reset pads are on their nets"
              % sum(1 for e in pindata.pads.values() if e["type"] != "I/O"), "; ".join(bad))

    # ---- E: what the spec fixes ----------------------------------------------------------------
    rep.section("E  rows fixed by DESIGN_SPEC section 4 (spec text parsed)")
    spec = read_spec_dcmi()
    names = {"D0": "CAM_D0", "D1": "CAM_D1", "D2": "CAM_D2", "D3": "CAM_D3", "D4": "CAM_D4",
             "D5": "CAM_D5", "D6": "CAM_D6", "D7": "CAM_D7", "PIXCLK": "CAM_PIXCLK",
             "HSYNC": "CAM_HREF", "VSYNC": "CAM_VSYNC", "MCO": "CAM_XVCLK", "SPI1_MISO": "SPI1_MISO",
             "EXTCOMIN": "LCD_EXTCOMIN", "USB_DM": "USB_DM", "USB_DP": "USB_DP"}
    rep.check(len(spec) == len(names), "the spec text yields all %d fixed assignments" % len(names),
              "parsed %d: %s" % (len(spec), sorted(spec)))
    for key, sig in names.items():
        if key not in spec:
            continue
        pin, pad, af = spec[key]
        r = by_sig[sig]
        good = r["pin"] == pin and r["pad"] == pad and (af is None or r["af"] == af) and r["source"] == "SPEC"
        rep.check(good, "%s: %s pad %d%s as in the spec" % (sig, pin, pad, "" if af is None else " AF%d" % af),
                  "PINMAP has %s pad %d AF%s source %s" % (r["pin"], r["pad"], r["af"], r["source"]))
    for sig in ("CAM_L_PWDN", "CAM_R_PWDN"):
        pin = by_sig[sig]["pin"]
        rep.check(pin not in SPEC_PWDN_FORBIDDEN and BOOTLOADER_PINS.get(pin, ("", ""))[1] != "drive",
                  "%s on %s: not PA9 / PA2 / PC10 and not a pin the bootloader drives" % (sig, pin))
        # 1 kohm in series
        net = by_sig[sig]["net"]
        terms = nl.reach(net)
        cam = [t for t in terms if t[0] in CAMERAS]
        rep.check(len(cam) == 1 and abs(cam[0][2] - 1000.0) < 1e-6 and cam[0][1] == "PWDN",
                  "%s reaches %s.PWDN through 1 kohm" % (sig, cam[0][0] if cam else "?"), "%s" % terms)
    mco = nl.reach(by_sig["CAM_XVCLK"]["net"])
    rep.check(sorted((t[0], t[1], t[2]) for t in mco) == [("U2", "XVCLK", 33.0), ("U3", "XVCLK", 33.0)],
              "XVCLK: PA8 (RCC_MCO) through 33 ohm to both cameras", "%s" % mco)
    fn = by_sig["LCD_EXTCOMIN"]["function"]
    rep.check(re.match(r"LPTIM[13]_CH\d$", fn) is not None,
              "EXTCOMIN is %s: an LPTIM1 / LPTIM3 output (they run in Stop 2)" % fn)
    for sig, pin_name in (("CAM_L_SCL", "SIOC"), ("CAM_R_SCL", "SIOC"), ("CAM_SCCB_SDA", "SIOD")):
        net = by_sig[sig]["net"]
        pulls = nl.pulls(net)
        rep.check(len(pulls) == 1 and pulls[0][1] == "V2V8_CAM" and abs(pulls[0][0] - 2200.0) < 1e-6,
                  "%s (%s): one 2.2 kohm pull-up, to V2V8_CAM" % (sig, by_sig[sig]["pin"]), "%s" % pulls)

    # ---- F: against the firmware header ----------------------------------------------------------
    rep.section("F  difference to firmware/hal/stm32u5/gl_pins.h")
    changed = []
    try:
        gl_rows, gl_boot = read_gl_pins()
    except OSError as exc:
        gl_rows, gl_boot = {}, {}
        rep.fail("cannot read gl_pins.h: %s" % exc)
    for sig, (pin, pad, src) in sorted(gl_rows.items()):
        r = by_sig.get(sig)
        if r is None:
            rep.fail("%s of gl_pins.h has no PINMAP row" % sig)
            continue
        if r["pin"] == pin:
            want_src = "SPEC" if src == "SPEC" else "PROPOSED"
            rep.check(r["source"] == want_src and r["was"] is None,
                      "%-13s %-5s unchanged (%s)" % (sig, pin, want_src), "PINMAP source %s" % r["source"])
        else:
            good = r["source"] == "CHANGED" and r["was"] == pin and bool(r["reason"]) and src != "SPEC"
            rep.check(good, "%-13s %s -> %s CHANGED, reason given" % (sig, pin, r["pin"]),
                      "PINMAP says source %s, was %s; gl_pins.h source %s" % (r["source"], r["was"], src))
            changed.append((sig, pin, r["pin"], r["reason"]))
    extra = sorted(s for s in by_sig if s not in gl_rows)
    rep.note("rows of PINMAP that gl_pins.h does not list (service pins): %s" % ", ".join(extra))
    stale = [r["signal"] for r in rows if r["source"] == "CHANGED" and r["signal"] not in gl_rows]
    rep.check(not stale, "every CHANGED row has a row in gl_pins.h to differ from", ", ".join(stale))
    if gl_boot:
        mine = {p: v for p, v in BOOTLOADER_PINS.items() if p not in ("PA11", "PA12")}   # USB: not in the header
        rep.check(mine == gl_boot, "the bootloader table here equals GL_PINS_BOOTLOADER_TABLE of gl_pins.h "
                  "(both from memory of AN2606)", "differences: %s" % sorted(set(mine.items()) ^ set(gl_boot.items())))

    # ---- G: ROM bootloader pins ---------------------------------------------------------------------
    rep.section("G  pins the ROM bootloader drives or listens on")
    rep.prov("the list of bootloader pins is from memory of ST AN2606 (not readable here); "
             "only the existence of each peripheral function on its pin is verified below")
    on_package = {e["name"] for e in pindata.pads.values()}
    for pin, (fn, role) in sorted(BOOTLOADER_PINS.items()):
        if pin not in on_package:
            rep.ok("%-5s %-14s: the pin does not exist on LQFP-64" % (pin, fn))
            continue
        rep.check(fn in pindata.signals(pin), "%-5s %-14s exists on the pin (pin data)" % (pin, fn))
    # the camera rail must be off while the bootloader runs
    en = by_sig["CAM_PWR_EN"]
    en_pulls = [p for p in nl.pulls(en["net"]) if p[1] == "GND"]
    cam_off = bool(en_pulls) and en["pin"] not in BOOTLOADER_PINS and nl.net("U8", "EN") == en["net"]
    rep.check(cam_off, "camera rail is off in the bootloader: U8.EN on %s (not a bootloader pin) with "
              "pull-down(s) %s" % (en["pin"], ", ".join("%s %g ohm" % (p[2], p[0]) for p in en_pulls)))
    cp_pins = {by_sig["GRAIN_CP%d" % i]["pin"] for i in range(5)}
    rep.check(not (cp_pins & set(BOOTLOADER_MAY_DRIVE_LOW)),
              "no charlieplex line is on a pin the bootloader may drive LOW (%s): with every other line "
              "high or floating no LED has a current path" % ", ".join(BOOTLOADER_MAY_DRIVE_LOW))
    net_of_pin = {r["pin"]: r for r in rows}
    for pin, (fn, role) in sorted(BOOTLOADER_PINS.items()):
        if pin not in on_package:
            continue
        r = net_of_pin.get(pin)
        if r is None:
            rep.ok("%-5s %-13s %-6s: pad not connected" % (pin, fn, role))
            continue
        verdict, why = bootloader_verdict(nl, by_sig, pin, role, r, cam_off, cp_pins)
        text = "%-5s %-13s %-6s %-12s: %s" % (pin, fn, role, r["signal"], why)
        (rep.ok if verdict else rep.fail)(text)
    rep.prov("OVM7692 pins are assumed to have ordinary protection diodes to their (unpowered) "
             "supply: a line that ends only on unpowered camera pins then sits below a diode drop")
    rep.prov("whether the ROM enables pull-ups on its receive pins is not known; no verdict above relies on it")
    return changed


def bootloader_verdict(nl, by_sig, pin, role, row, cam_off, cp_pins):
    """(passes, reason) for one bootloader pin.  Every branch is an explicit,
    netlist-derived case; anything else fails so that a later pin change has
    to be looked at by a person."""
    net = row["net"]
    sig = row["signal"]
    terms = nl.reach(net)
    refs = sorted({t[0] for t in terms})
    cam_terms = [t for t in terms if t[0] in CAMERAS]
    other = [t for t in terms if t[0] not in CAMERAS]
    pulls = nl.pulls(net)

    def cam_rail_only(ts):
        return all(t[0] in CAMERAS or t[0] in ("rail:" + r for r in CAMERA_RAIL) for t in ts)

    if pin in ("PA11", "PA12"):
        ok = {t[0] for t in terms} <= {"U10", "J2"}
        return ok, "USB line to the ESD array and the cradle pad only" if ok else "unexpected: %s" % refs
    # ---- lines that end on the cameras ------------------------------------------------------
    if cam_terms and cam_rail_only(terms):
        if not cam_off:
            return False, "camera net, but the camera rail is not provably off in the bootloader"
        rmin = min(t[2] for t in cam_terms)
        direct_rail = [t for t in terms if t[0].startswith("rail:")]
        if role == "drive":
            if rmin < 220.0 - 1e-6:
                return False, "DRIVEN into camera pins through only %g ohm" % rmin
            n = len(cam_terms)
            bound = n * (VDD - 0.65) / rmin * 1e3          # rail held at 0 V, silicon diode
            likely = n * (VDD - 0.65) / (rmin + n * 230.0) * 1e3
            return bound <= IO_ABS_MAX_MA, (
                "driven into %d unpowered camera pins through %g ohm each (spec rule 2). Bound with the "
                "camera rail held at 0 V and a 0.65 V protection diode: %.1f mA from the pin, %.1f mA "
                "into each camera pin; about %.0f mA expected with the rail floating up through a "
                "230 ohm discharge path. PROVISIONAL: the %g mA absolute maximum of one I/O, the diode "
                "and the discharge path; above the 8 mA the I/O levels are specified at"
                % (n, rmin, bound, bound / n, likely, IO_ABS_MAX_MA))
        if direct_rail:
            return True, ("pulled to the unpowered camera rail through %s: static low, no edge; an internal "
                          "pull-up of the ROM would feed at most %.2f mA into that rail through the resistor"
                          % (" / ".join("%g ohm" % t[2] for t in direct_rail), VDD / 25e3 * 1e3))
        return True, ("ends only on unpowered camera outputs (through %g ohm): clamped below a diode drop, "
                      "static low" % rmin)
    if cam_terms:
        return False, "camera pins and other things on one net: %s" % refs
    # ---- charlieplex lines --------------------------------------------------------------------
    if pin in cp_pins:
        leds = all(t[0].startswith("D") and nl.parts[t[0]].value.startswith("LED") for t in terms)
        return leds, ("%s: 68 ohm, then LEDs only; current needs a second line at LOW and the "
                      "bootloader drives none of the five low" % ("driven high" if role == "drive" else "input"))
    # ---- dividers and pulled lines ------------------------------------------------------------
    parts_on_net = sorted({ref for ref, _p in nl.nodes(net) if ref != "U1"})
    kinds = {nl.parts[ref].ref_prefix for ref in parts_on_net}
    if role == "drive":
        if kinds <= {"R", "C"} and pulls:
            rmin = min(p[0] for p in pulls)
            return rmin >= 10e3, ("driven into a resistor network only (%s); lowest resistance to a rail "
                                  "%g ohm: at most %.3f mA" % (", ".join(parts_on_net), rmin, 4.2 / rmin * 1e3))
        if {(t[0], t[1]) for t in terms} == {("U4", "SDO")}:
            cs_up = [p for p in nl.pulls(nl.net("U4", "CS")) if p[1] in ALWAYS_ON]
            return bool(cs_up), (
                "driven into U4.SDO only; IMU_CS has a pull-up (%s): the IMU is not selected, its SDO pin "
                "is not an output (PROVISIONAL: LSM6DSV16X datasheet not read)"
                % ", ".join("%s %g ohm" % (p[2], p[0]) for p in cs_up))
        return False, "driven pin on an unclassified net: %s" % refs
    # role == "listen": the line must rest at a level that does not move by itself
    static = [p for p in pulls if p[1] in GROUND + ALWAYS_ON]
    drivers = [(t[0], t[1]) for t in terms
               if not t[0].startswith("rail:") and nl.parts[t[0]].pins[t[1]].etype in ("output", "open_drain", "power_out")]
    fn = BOOTLOADER_PINS[pin][0]
    spi = fn.split("_")[0] if fn.startswith("SPI") else None

    def bl_pin(function):
        return next((p for p, v in BOOTLOADER_PINS.items() if v[0] == function), None)

    def rests(net_name):
        """The resistive path of a net to ground / an always-on rail, if no output is on it."""
        ts = nl.reach(net_name)
        if any(not t[0].startswith("rail:") and nl.parts[t[0]].pins[t[1]].etype in ("output", "open_drain")
               for t in ts):
            return None
        rails = [t for t in ts if t[0].startswith("rail:") and t[0][5:] in GROUND + ALWAYS_ON]
        return min(rails, key=lambda q: q[2]) if rails else None

    if drivers and spi and fn.endswith("_MOSI"):
        sck = by_sig_by_pin(by_sig, bl_pin(spi + "_SCK"))
        level = rests(sck["net"]) if sck else None
        return level is not None, (
            "%s is driven by %s (push-pull; it can move if the IMU was left configured); harmless only "
            "because the bootloader's %s_SCK (%s = %s) rests at %s through %g ohm with no driver: "
            "without clock edges an SPI slave shifts nothing in"
            % (fn, ", ".join("%s.%s" % dd for dd in drivers), spi, bl_pin(spi + "_SCK"),
               sck["signal"] if sck else "?", level[0][5:] if level else "?", level[2] if level else float("nan"))
            if level is not None else
            "%s is driven by %s and the bootloader's %s_SCK line has no resting level"
            % (fn, drivers, spi))
    if drivers:
        return False, "an output that can move is on a bootloader receive line: %s" % drivers
    if static:
        p = min(static, key=lambda q: q[0])
        level = "low" if p[1] in GROUND else "high"
        return True, "held %s by %s (%g ohm to %s); no driver on the line" % (level, p[2], p[0], p[1])
    to_rail = [t for t in terms if t[0].startswith("rail:") and t[0][5:] in GROUND + ALWAYS_ON]
    if to_rail:
        t = min(to_rail, key=lambda q: q[2])
        return True, "rests at %s through %g ohm (%s); no driver on the line" % (
            t[0][5:], t[2], " + ".join(t[3]))
    if spi and fn.endswith(("_SCK", "_MOSI")):
        nss = by_sig_by_pin(by_sig, bl_pin(spi + "_NSS"))
        up = [p for p in (nl.pulls(nss["net"]) if nss else []) if p[1] in ALWAYS_ON]
        return bool(up), (
            "no defined level (input of %s only), but the bootloader's %s_NSS (%s = %s) is held high by "
            "%s: an unselected SPI slave ignores clock and data"
            % (", ".join(sorted({t[0] for t in terms})), spi, bl_pin(spi + "_NSS"),
               nss["signal"] if nss else "?", ", ".join("%s %g ohm" % (p[2], p[0]) for p in up))
            if up else "no defined level, and the bootloader's %s_NSS line is not held inactive" % spi)
    return False, "no defined level and no reason why that is harmless: %s" % refs


def by_sig_by_pin(by_sig, pin):
    for r in by_sig.values():
        if r["pin"] == pin:
            return r
    return None


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------
def export(path, pindata, design, rep, changed, partial):
    rows = []
    for r in G.pinmap_rows():
        sigs = pindata.signals(r["pin"])
        rows.append({
            "signal": r["signal"], "port_pin": r["pin"], "pad": r["pad"], "net": r["net"],
            "mode": r["mode"], "function": r["function"], "af": r["af"], "pull": r["pull"],
            "initial_state": r["initial_state"], "source": r["source"],
            "changed_from": r["was"], "reason": r["reason"],
            "wakeup": sorted(s for s in sigs if s.startswith("PWR_WKUP")),
            "adc": sorted(s for s in sigs if s.startswith("ADC1_IN")),
            "bootloader": list(BOOTLOADER_PINS[r["pin"]]) if r["pin"] in BOOTLOADER_PINS else None,
        })
    rows.sort(key=lambda r: (r["pad"], r["signal"]))
    nl = Netlist(design)
    supply = [{"pad": pad, "pin": e["name"], "net": nl.net("U1", G.mcu_pin_name(pad))}
              for pad, e in sorted(pindata.pads.items()) if e["type"] != "I/O"]
    leds = [{"ref": ref, "colour": colour, "azimuth_deg": az, "anode_line": "GRAIN_CP%d" % a,
             "cathode_line": "GRAIN_CP%d" % c}
            for ref, colour, _x, _y, _rot, az, a, c in G.led_positions()]
    data = {
        "design": design.name, "mcu": "STM32U585RIT6", "package": "LQFP-64",
        "u1_rotation_assumed_deg": G.U1_ROTATION,
        "status": "NETLIST STAGE - nothing built; the layout step may still move PROPOSED / CHANGED pins",
        "verification": {
            "checks_passed": not rep.fails, "partial": partial, "source": pindata.source,
            "data_sha256": pindata.hashes, "failures": rep.fails,
            "provisional": rep.provisional + [
                "bootloader pin table: memory of ST AN2606",
                "FT / TT structure of the pins (CHG_INHIBIT on PH1 needs a pin without a diode to VDD): "
                "not in the open pin data, datasheet DS13086 not read"],
        },
        "pins": rows,
        "supply_pads": supply,
        "changed_from_gl_pins_h": [{"signal": s, "from": a, "to": b, "reason": why}
                                   for s, a, b, why in changed],
        "grain_leds": leds,
        "extcomin_lse_ticks": 547,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, sort_keys=False)
        fh.write("\n")


def _swap(sig_a, sig_b):
    def mutate(rows):
        ia = next(i for i, r in enumerate(rows) if r[0] == sig_a)
        ib = next(i for i, r in enumerate(rows) if r[0] == sig_b)
        pa, pb = rows[ia][1], rows[ib][1]
        rows[ia] = (rows[ia][0], pb) + tuple(rows[ia][2:])
        rows[ib] = (rows[ib][0], pa) + tuple(rows[ib][2:])
    return mutate


def _set(sig, index, value):
    def mutate(rows):
        i = next(i for i, r in enumerate(rows) if r[0] == sig)
        row = list(rows[i])
        row[index] = value
        rows[i] = tuple(row)
    return mutate


#: (what is seeded, mutation of PINMAP or None, text that must appear in a failure)
SELFTEST = [
    ("DCMI_D3 given AF10 instead of AF4", _set("CAM_D3", 5, 10), "CAM_D3"),
    ("CAM_L_PWDN moved to PC10 (bootloader USART3_TX)", _swap("CAM_L_PWDN", "GRAIN_CP4"), "CAM_L_PWDN on PC10"),
    ("CAM_R_SCL moved to PA9 (bootloader USART1_TX)", _swap("CAM_R_SCL", "GRAIN_CP0"), "DRIVEN into camera pins"),
    ("IMU_INT1 moved to PB0 (no wake-up function)", _swap("IMU_INT1", "CHG_STAT"), "IMU_INT1"),
    ("VBAT_SENSE moved to PH1 (no ADC channel)", _swap("VBAT_SENSE", "CHG_INHIBIT"), "VBAT_SENSE"),
    ("NTC_BIAS put on PC4, the pad of NTC_SENSE", _set("NTC_BIAS", 1, "PC4"), "used twice"),
    ("SPEC row CAM_D4 moved to PC12", _swap("CAM_D4", "GRAIN_CP2"), "CAM_D4"),
    ("SPI1_SCK marked PROPOSED although it moved", _set("SPI1_SCK", 8, "PROPOSED"), "SPI1_SCK"),
    ("IMU_INT2 moved to PA10 (bootloader USART1_RX)", _swap("IMU_INT2", "FLASH_CS"), "an output that can move"),
    ("pad names of pads 8 and 9 swapped in the netlist", "pads", "pad 8"),
    ("R31 (pull on PA3 / USART2_RX) removed", "r31", "PA3"),
]


def selftest(pindata):
    """Seed each defect of SELFTEST and require a failure that names it."""
    saved_map, saved_pads = list(G.PINMAP), list(G.MCU_PAD_NAMES)
    lines, missed = [], 0
    try:
        for what, mutation, expect in SELFTEST:
            G.PINMAP[:] = saved_map
            G.MCU_PAD_NAMES[:] = saved_pads
            if callable(mutation):
                rows = list(saved_map)
                mutation(rows)
                G.PINMAP[:] = rows
            elif mutation == "pads":
                G.MCU_PAD_NAMES[7], G.MCU_PAD_NAMES[8] = G.MCU_PAD_NAMES[8], G.MCU_PAD_NAMES[7]
            rep = Report()
            try:
                design = G.gl1_main_design()
                if mutation == "r31":
                    design.parts[:] = [p for p in design.parts if p.ref != "R31"]
                    for net in design.nets.values():
                        net.nodes[:] = [n for n in net.nodes if n[0] != "R31"]
                run(pindata, design, rep)
            except Exception as exc:                 # a defect that breaks the build is caught too
                rep.fails.append("%s: %s" % (type(exc).__name__, exc))
            hit = [f for f in rep.fails if expect in f]
            lines.append("  %s  %s -> %d failure(s)%s" % (
                "caught" if hit else "MISSED", what, len(rep.fails),
                (", e.g. " + hit[0][:110]) if hit else ""))
            missed += 0 if hit else 1
    finally:
        G.PINMAP[:] = saved_map
        G.MCU_PAD_NAMES[:] = saved_pads
    return lines, missed


def main(argv=None):
    ap = argparse.ArgumentParser(description="GL-1 pin map against ST's open pin data")
    ap.add_argument("--pindata", default=os.environ.get("GL1_PINDATA"),
                    help="directory with %s and %s (outside the repository)" % (MCU_XML, GPIO_XML))
    ap.add_argument("--export", action="store_true", help="write pinmap.json next to this script")
    ap.add_argument("--report", help="also write the report to this file")
    ap.add_argument("--selftest", action="store_true",
                    help="also seed defects into the pin map and require each to be caught")
    args = ap.parse_args(argv)
    rep = Report()
    partial = False
    if args.pindata and os.path.isfile(os.path.join(args.pindata, MCU_XML)) \
            and os.path.isfile(os.path.join(args.pindata, GPIO_XML)):
        pindata = PinData.from_st(args.pindata)
    else:
        partial = True
        pindata = PinData.from_kicad()
    design = G.gl1_main_design()
    head = ["GL-1 pin map check - %s" % design.name, "data: %s" % pindata.source]
    for name, digest in sorted(pindata.hashes.items()):
        head.append("  %s sha256 %s%s" % (name, digest, "" if digest == REFERENCE_SHA256[name]
                                           else "  (differs from the reference %s)" % REFERENCE_SHA256[name]))
    if partial:
        head.append("PARTIAL: no ST pin data given (--pindata); alternate-function NUMBERS are NOT verified")
    changed = run(pindata, design, rep)
    # cross-check the pad table with the KiCad symbol when the ST data is the source
    if not partial and os.path.isfile(KICAD_SYMBOLS):
        rep.section("H  second source: the installed KiCad symbol")
        k = PinData.from_kicad()
        diff = [pad for pad in range(1, 65) if k.pads.get(pad, {}).get("name") != pindata.pads[pad]["name"]]
        rep.check(not diff and len(k.pads) == 64, "the KiCad symbol %s has the same 64 pad names" % KICAD_SYMBOL,
                  "pads that differ: %s" % diff)
    tail = ["", "changed from gl_pins.h (%d):" % len(changed)]
    tail += ["  %-13s %-5s -> %-5s %s" % c for c in changed]
    n_ok = sum(v[0] for v in rep.counts.values())
    tail += ["", "RESULT: %s - %d checks passed, %d failed%s" % (
        "FAIL" if rep.fails else ("PASS (PARTIAL)" if partial else "PASS"), n_ok, len(rep.fails),
        "; %d PROVISIONAL statements above" % len(rep.provisional))]
    missed = 0
    if args.selftest:
        st_lines, missed = selftest(pindata)
        tail += ["", "SELF-TEST: %d seeded defects, %d caught, %d missed" % (
            len(SELFTEST), len(SELFTEST) - missed, missed)] + st_lines
    text = "\n".join(head + rep.lines + tail) + "\n"
    sys.stdout.write(text)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            fh.write(text)
    if args.export:
        export(os.path.join(HERE, "pinmap.json"), pindata, design, rep, changed, partial)
    return 1 if (rep.fails or missed) else 0


if __name__ == "__main__":
    sys.exit(main())
