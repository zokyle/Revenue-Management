#!/usr/bin/env python3
"""Generate hal/stm32u5/gl_pins.h: the pin map of the STM32U585RIT6 (LQFP-64).

Usage:
    gen_pins.py [--check] <DESIGN_SPEC.md> <output gl_pins.h>

Where the pin map comes from
----------------------------
DESIGN_SPEC.md section 4 fixes, with pad numbers and alternate functions that
were verified against ST's open pin data (docs/research/bom-verification-ics.md
section 1): the eleven DCMI pins, MCO, SPI1 MISO, USB D-/D+, LPTIM1_CH1 for
EXTCOMIN and the OPAMP1 pins.  Those rows are marked SPEC below, and this
script PARSES THE SPEC TEXT and refuses to generate if a SPEC row disagrees
with it, so the header cannot drift from the specification.

DESIGN_SPEC does not assign the remaining signals (no netlist exists yet).
Those rows are marked PROPOSED: they are this firmware's proposal for the
schematic, chosen from the free pads and from the candidate pins that the
BOM verification lists (SPI1 SCK/MOSI, SPI2, wake-capable pins).  For a
PROPOSED row the pad number is either in that verified list or comes from
the standard LQFP-64 pinout as remembered (it agrees with all verified pads),
and an alternate-function number that is not in the verified list is marked
"from memory".  All of them must be checked against
STM32_open_pin_data (mcu/STM32U585RITx.xml and
mcu/IP/GPIO-STM32U5x_gpio_v1_0_Modes.xml) when the schematic is drawn.

With --check nothing is written; exit status 1 if the header is stale.
"""
import re
import sys

# Function kinds (GL_PINFN_* in the header).
GPIO, AF, ANALOG, SCCB, EXTI = "GPIO", "AF", "ANALOG", "SCCB", "EXTI"

# (logical name, port, pin, pad, kind, af, source, note)
#   kind  GPIO    plain output / input driven by a driver
#         AF      alternate function `af` when the pin is in GL_PIN_MODE_ALTERNATE
#         ANALOG  analog function (op-amp, ADC): ALTERNATE = analog mode
#         SCCB    bit-banged SCCB line: ALTERNATE = open-drain output, released
#         EXTI    input with an EXTI interrupt
PINS = [
    ("GL_PIN_CAM_PWR_EN",   "D", 2,  54, GPIO,   0,  "PROPOSED", "LP5907 EN, 100k pull-down on the board"),
    ("GL_PIN_CAM_L_PWDN",   "C", 10, 51, GPIO,   0,  "PROPOSED", ""),
    ("GL_PIN_CAM_R_PWDN",   "C", 12, 53, GPIO,   0,  "PROPOSED", ""),
    ("GL_PIN_CAM_SCCB_SDA", "B", 5,  57, SCCB,   0,  "PROPOSED", "shared SCCB data, 2.2k to V2V8_CAM"),
    ("GL_PIN_CAM_L_SCL",    "B", 3,  55, SCCB,   0,  "PROPOSED", "also JTDO/SWO: SWO is given up"),
    ("GL_PIN_CAM_R_SCL",    "A", 10, 43, SCCB,   0,  "PROPOSED", ""),
    ("GL_PIN_CAM_XVCLK",    "A", 8,  41, AF,     0,  "SPEC",     "RCC_MCO, 33 ohm series"),
    ("GL_PIN_CAM_D0",       "C", 6,  37, AF,     10, "SPEC",     "DCMI_D0"),
    ("GL_PIN_CAM_D1",       "C", 7,  38, AF,     10, "SPEC",     "DCMI_D1"),
    ("GL_PIN_CAM_D2",       "C", 8,  39, AF,     10, "SPEC",     "DCMI_D2"),
    ("GL_PIN_CAM_D3",       "C", 9,  40, AF,     4,  "SPEC",     "DCMI_D3 (AF4, not AF10)"),
    ("GL_PIN_CAM_D4",       "C", 11, 52, AF,     10, "SPEC",     "DCMI_D4 (AF4 on this pin is D2)"),
    ("GL_PIN_CAM_D5",       "B", 6,  58, AF,     10, "SPEC",     "DCMI_D5"),
    ("GL_PIN_CAM_D6",       "B", 8,  61, AF,     10, "SPEC",     "DCMI_D6"),
    ("GL_PIN_CAM_D7",       "B", 9,  62, AF,     10, "SPEC",     "DCMI_D7"),
    ("GL_PIN_CAM_PIXCLK",   "A", 6,  22, AF,     4,  "SPEC",     "DCMI_PIXCLK (AF4), 33 ohm at the sensors"),
    ("GL_PIN_CAM_HREF",     "A", 4,  20, AF,     10, "SPEC",     "DCMI_HSYNC"),
    ("GL_PIN_CAM_VSYNC",    "B", 7,  59, AF,     10, "SPEC",     "DCMI_VSYNC"),
    ("GL_PIN_LCD_SCS",      "B", 10, 29, GPIO,   0,  "PROPOSED", "active HIGH"),
    ("GL_PIN_LCD_DISP",     "B", 1,  27, GPIO,   0,  "PROPOSED", "pull-down on the board"),
    ("GL_PIN_LCD_EXTCOMIN", "B", 2,  28, AF,     1,  "SPEC",     "LPTIM1_CH1"),
    ("GL_PIN_SPI1_SCK",     "A", 5,  21, AF,     5,  "PROPOSED", "SPI1_SCK; AF5 from memory"),
    ("GL_PIN_SPI1_MOSI",    "A", 7,  23, AF,     5,  "PROPOSED", "SPI1_MOSI; AF5 from memory"),
    ("GL_PIN_SPI1_MISO",    "B", 4,  56, AF,     5,  "SPEC",     "SPI1_MISO (PA6 is PIXCLK)"),
    ("GL_PIN_SPI2_SCK",     "B", 13, 34, AF,     5,  "PROPOSED", "SPI2_SCK; AF5 from memory"),
    ("GL_PIN_SPI2_MOSI",    "B", 15, 36, AF,     5,  "PROPOSED", "SPI2_MOSI; AF5 from memory"),
    ("GL_PIN_SPI2_MISO",    "B", 14, 35, AF,     5,  "PROPOSED", "SPI2_MISO; AF5 from memory"),
    ("GL_PIN_FLASH_CS",     "A", 15, 50, GPIO,   0,  "PROPOSED", "JTDI pull-up keeps CS# high in reset"),
    ("GL_PIN_IMU_CS",       "B", 12, 33, GPIO,   0,  "PROPOSED", ""),
    ("GL_PIN_IMU_INT1",     "C", 13, 2,  EXTI,   0,  "PROPOSED", "EXTI13, WKUP2: wake-on-motion"),
    ("GL_PIN_IMU_INT2",     "C", 5,  25, EXTI,   0,  "PROPOSED", "EXTI5: data ready"),
    ("GL_PIN_GRAIN_CP0",    "C", 0,  8,  GPIO,   0,  "PROPOSED", "68 ohm"),
    ("GL_PIN_GRAIN_CP1",    "C", 1,  9,  GPIO,   0,  "PROPOSED", "68 ohm"),
    ("GL_PIN_GRAIN_CP2",    "C", 2,  10, GPIO,   0,  "PROPOSED", "68 ohm"),
    ("GL_PIN_GRAIN_CP3",    "C", 3,  11, GPIO,   0,  "PROPOSED", "68 ohm"),
    ("GL_PIN_GRAIN_CP4",    "C", 4,  24, GPIO,   0,  "PROPOSED", "68 ohm"),
    ("GL_PIN_OPAMP_VINP",   "A", 0,  14, ANALOG, 0,  "SPEC",     "OPAMP1_VINP: mid-rail bias"),
    ("GL_PIN_OPAMP_VINM",   "A", 1,  15, ANALOG, 0,  "SPEC",     "OPAMP1_VINM: photodiode cathode"),
    ("GL_PIN_OPAMP_VOUT",   "A", 3,  17, ANALOG, 0,  "SPEC",     "OPAMP1_VOUT = ADC1_IN8"),
    ("GL_PIN_VBAT_SENSE",   "A", 2,  16, ANALOG, 0,  "PROPOSED", "ADC1_IN7 (channel number from memory)"),
    ("GL_PIN_CHG_STAT",     "B", 0,  26, EXTI,   0,  "PROPOSED", "EXTI0, both edges, pull-up"),
    ("GL_PIN_CHG_PROG_EN",  "H", 1,  6,  GPIO,   0,  "PROPOSED", "open drain; PH1 is free (no HSE crystal)"),
    ("GL_PIN_VBUS_SENSE",   "A", 9,  42, EXTI,   0,  "PROPOSED", "EXTI9, both edges, from the VBUS divider"),
    ("GL_PIN_USB_DM",       "A", 11, 44, AF,     10, "SPEC",     "USB D-"),
    ("GL_PIN_USB_DP",       "A", 12, 45, AF,     10, "SPEC",     "USB D+"),
]

# Pads that are not GPIO signals of this table (supplies, debug, crystal).
FIXED = [
    ("VBAT", 1), ("PC14-OSC32_IN", 3), ("PC15-OSC32_OUT", 4), ("PH0 (spare)", 5), ("NRST", 7),
    ("VSSA", 12), ("VDDA", 13), ("VSS", 18), ("VDD", 19), ("VCAP", 30), ("VSS", 31), ("VDD", 32),
    ("PA13-SWDIO", 46), ("VSS", 47), ("VDDUSB", 48), ("PA14-SWCLK", 49), ("PH3-BOOT0", 60),
    ("VSS", 63), ("VDD", 64),
]


def spec_facts(text):
    """Pins that DESIGN_SPEC section 4 states, as {(port, pin): (pad, af or None)}."""
    facts = {}
    # "D0 PC6 pad 37 AF10", "PIXCLK PA6 pad 22 AF4", "MCO PA8 pad 41"
    for m in re.finditer(r"\bP([A-H])(\d+) pad (\d+)(?: AF(\d+))?", text):
        facts[(m.group(1), int(m.group(2)))] = (int(m.group(3)), int(m.group(4)) if m.group(4) else None)
    # "PB4 (pad 56, AF5)", "PB2 (pad 28)", "PA11 = D- (pad 44)"
    for m in re.finditer(r"\bP([A-H])(\d+)(?: = D[-+])? \(pad (\d+)(?:, AF(\d+))?\)", text):
        facts[(m.group(1), int(m.group(2)))] = (int(m.group(3)), int(m.group(4)) if m.group(4) else None)
    return facts


def check(spec_text):
    facts = spec_facts(spec_text)
    errors = []
    seen_pads, seen_pins, seen_exti = {}, {}, {}
    for name, port, pin, pad, kind, af, source, _note in PINS:
        if pad in seen_pads:
            errors.append("%s and %s share pad %d" % (name, seen_pads[pad], pad))
        seen_pads[pad] = name
        if (port, pin) in seen_pins:
            errors.append("%s and %s share P%s%d" % (name, seen_pins[(port, pin)], port, pin))
        seen_pins[(port, pin)] = name
        if kind == EXTI:
            if pin in seen_exti:
                errors.append("%s and %s share EXTI line %d" % (name, seen_exti[pin], pin))
            seen_exti[pin] = name
        if source == "SPEC":
            if (port, pin) not in facts:
                # the OPAMP pins are stated in the BOM verification, not in the spec text
                if not name.startswith("GL_PIN_OPAMP"):
                    errors.append("%s: P%s%d is marked SPEC but DESIGN_SPEC does not state it" %
                                  (name, port, pin))
                continue
            spad, saf = facts[(port, pin)]
            if spad != pad:
                errors.append("%s: pad %d here, pad %d in DESIGN_SPEC" % (name, pad, spad))
            if saf is not None and kind == AF and saf != af:
                errors.append("%s: AF%d here, AF%d in DESIGN_SPEC" % (name, af, saf))
    for label, pad in FIXED:
        if pad in seen_pads:
            errors.append("%s uses pad %d, which is %s" % (seen_pads[pad], pad, label))
    # every DCMI pin of the spec must be in the table
    for key in [("C", 6), ("C", 7), ("C", 8), ("C", 9), ("C", 11), ("B", 6), ("B", 8), ("B", 9),
                ("A", 6), ("A", 4), ("B", 7), ("A", 8), ("B", 4), ("A", 11), ("A", 12), ("B", 2)]:
        if key not in facts:
            errors.append("DESIGN_SPEC no longer states P%s%d: the parser needs updating" % key)
        if key not in seen_pins:
            errors.append("P%s%d of DESIGN_SPEC is missing from the table" % key)
    if errors:
        raise SystemExit("gen_pins: " + "\n          ".join(errors))


def generate():
    out = []
    w = out.append
    w("/*")
    w(" * gl_pins.h - GENERATED by tools/gen_pins.py.  DO NOT EDIT; change the table")
    w(" * in the generator and run `make config`.")
    w(" *")
    w(" * Pin map of the STM32U585RIT6 (LQFP-64) for the GL-1.")
    w(" *")
    w(" *   SPEC      stated in design/DESIGN_SPEC.md section 4 (pad numbers and")
    w(" *             alternate functions verified there against ST's open pin")
    w(" *             data); the generator parses the spec text and fails if a")
    w(" *             SPEC row disagrees with it.")
    w(" *   PROPOSED  NOT assigned by DESIGN_SPEC (no netlist exists): this")
    w(" *             firmware's proposal for the schematic.  Pads not in the")
    w(" *             verified list come from the standard LQFP-64 pinout as")
    w(" *             remembered; AF numbers marked \"from memory\" likewise.")
    w(" *             Check every one against STM32_open_pin_data before layout.")
    w(" *")
    w(" * The header contains only macros and can be included anywhere (the host")
    w(" * test tests/test_pins.c checks it); hal/stm32u5/gl_hal_stm32u5.c expands")
    w(" * GL_PINS_TABLE into its port / pin table.")
    w(" *")
    w(" * SCCB: both cameras answer at one address and have separate clock lines,")
    w(" * which no single I2C peripheral can drive, so the three SCCB lines are")
    w(" * bit-banged open-drain GPIOs (GL_PINFN_SCCB).")
    w(" */")
    w("#ifndef GL_PINS_H")
    w("#define GL_PINS_H")
    w("")
    w("/* What GL_PIN_MODE_ALTERNATE means for a pin. */")
    w("#define GL_PINFN_GPIO   0 /* no alternate function: treated as a push-pull output */")
    w("#define GL_PINFN_AF     1 /* alternate function number in the table */")
    w("#define GL_PINFN_ANALOG 2 /* analog function (op-amp, ADC input) */")
    w("#define GL_PINFN_SCCB   3 /* bit-banged SCCB line: open-drain output */")
    w("#define GL_PINFN_EXTI   4 /* input with an EXTI interrupt line */")
    w("")
    w("/* Source of a row. */")
    w("#define GL_PINSRC_SPEC     0")
    w("#define GL_PINSRC_PROPOSED 1")
    w("")
    w("/*")
    w(" * X(logical pin, port letter, pin number, LQFP-64 pad, function kind, AF, source)")
    w(" * Rows are in the order of gl_pin_t (hal/gl_hal.h).")
    w(" */")
    w("#define GL_PINS_TABLE(X) \\")
    rows = []
    width = max(len(p[0]) for p in PINS)
    for name, port, pin, pad, kind, af, source, note in PINS:
        rows.append("    X(%-*s %s, %2d, %2d, GL_PINFN_%-7s %2d, GL_PINSRC_%-9s /* P%s%d%s */" %
                    (width + 1, name + ",", port, pin, pad, kind + ",", af, source + ")",
                     port, pin, (": " + note) if note else ""))
    for i, row in enumerate(rows):
        w(row + (" \\" if i + 1 < len(rows) else ""))
    w("")
    w("#define GL_PINS_COUNT %d" % len(PINS))
    w("")
    w("/* Pads that carry no signal of the table. */")
    for label, pad in FIXED:
        w("/*   pad %2d  %s */" % (pad, label))
    w("")
    w("/* Analog channels (ADC1).  PA3 = ADC1_IN8 is verified; PA2 = ADC1_IN7 is from")
    w(" * memory of the same numbering. */")
    w("#define GL_PINS_ADC_CH_GRAIN_TIA 8")
    w("#define GL_PINS_ADC_CH_VBAT_DIV  7")
    w("")
    w("#endif /* GL_PINS_H */")
    return "\n".join(out) + "\n"


def main(argv):
    args = [a for a in argv[1:] if a != "--check"]
    check_only = "--check" in argv[1:]
    if len(args) != 2:
        raise SystemExit(__doc__)
    with open(args[0], "r", encoding="utf-8") as fh:
        spec = fh.read()
    check(spec)
    text = generate()
    if check_only:
        try:
            with open(args[1], "r", encoding="utf-8") as fh:
                current = fh.read()
        except OSError:
            current = None
        if current != text:
            print("STALE: %s does not match tools/gen_pins.py (run `make config`)" % args[1])
            return 1
        return 0
    with open(args[1], "w", encoding="utf-8") as fh:
        fh.write(text)
    print("wrote %s" % args[1])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
