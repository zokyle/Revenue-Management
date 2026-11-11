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

DESIGN_SPEC does not assign the remaining signals (the netlist is being
designed separately and will export the final map; until then THIS TABLE IS
THE SINGLE PLACE WHERE PINS ARE LISTED).  Those rows are marked PROPOSED:
they are this firmware's proposal for the schematic, chosen from the free
pads and from the candidate pins that the BOM verification lists (SPI1
SCK/MOSI, SPI2, wake-capable pins).

Rev C2 of DESIGN_SPEC section 4 adds three signals (CHG_INHIBIT in place of
the PROG enable, NTC_BIAS, NTC_SENSE) and three rules that this script reads
from the spec text and enforces:
  * each PWDN line "must not use a pin that the ROM bootloader drives as an
    output (the USART transmit pins PA9, PA2 and PC10 ...)";
  * EXTCOMIN divides 32768 by 547 (exported as GL_PINS_EXTCOMIN_LSE_TICKS);
  * the pull resistors that define the chip selects during reset (exported
    as GL_PINS_RESET_TABLE, the level each such pin has while the MCU does
    not drive it).

PIN BUDGET.  The LQFP-64 package has 46 I/O pads besides SWD, the 32 kHz
crystal and BOOT0; rev C2 needs 47 signals.  The proposal therefore uses
PH3-BOOT0 (an ordinary I/O after reset, with its 10 kohm pull-down) for
NTC_BIAS, the one signal that is only ever driven HIGH for a millisecond and
whose load (the divider to ground) pulls the same way as the BOOT0 resistor.
NTC_SENSE needs an ADC input and all 16 were taken: GRAIN_CP4 (a plain GPIO)
moves from PC4 to PC10 to free one.  Both are for the netlist owner to
confirm or replace.  For a
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
    ("GL_PIN_CAM_L_PWDN",   "H", 0,  5,  GPIO,   0,  "PROPOSED", "PH0 is free (no HSE crystal); not PC10: ROM bootloader USART3_TX"),
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
    ("GL_PIN_GRAIN_CP4",    "C", 10, 51, GPIO,   0,  "PROPOSED", "68 ohm; moved from PC4 (now NTC_SENSE). PC10 is the ROM bootloader's USART3_TX: harmless here, no LED conducts with the other four pins high-Z"),
    ("GL_PIN_OPAMP_VINP",   "A", 0,  14, ANALOG, 0,  "SPEC",     "OPAMP1_VINP: mid-rail bias"),
    ("GL_PIN_OPAMP_VINM",   "A", 1,  15, ANALOG, 0,  "SPEC",     "OPAMP1_VINM: photodiode cathode"),
    ("GL_PIN_OPAMP_VOUT",   "A", 3,  17, ANALOG, 0,  "SPEC",     "OPAMP1_VOUT = ADC1_IN8"),
    ("GL_PIN_VBAT_SENSE",   "A", 2,  16, ANALOG, 0,  "PROPOSED", "ADC1_IN7 (channel number from memory)"),
    ("GL_PIN_CHG_STAT",     "B", 0,  26, EXTI,   0,  "PROPOSED", "EXTI0, both edges, pull-up; STAT must be open drain: see the notes"),
    ("GL_PIN_CHG_INHIBIT",  "H", 1,  6,  GPIO,   0,  "PROPOSED", "open drain, LOW = stop charging; gate of the PROG MOSFET. MUST be a pin with no diode to VDD (FT; PH1 is, from memory) and not a ROM bootloader pin"),
    ("GL_PIN_VBUS_SENSE",   "A", 9,  42, EXTI,   0,  "PROPOSED", "EXTI9, both edges, from the VBUS divider"),
    ("GL_PIN_USB_DM",       "A", 11, 44, AF,     10, "SPEC",     "USB D-"),
    ("GL_PIN_USB_DP",       "A", 12, 45, AF,     10, "SPEC",     "USB D+"),
    ("GL_PIN_NTC_BIAS",     "H", 3,  60, GPIO,   0,  "PROPOSED", "PH3-BOOT0 (10k pull-down stays): push-pull HIGH only during a conversion; see PIN BUDGET"),
    ("GL_PIN_NTC_SENSE",    "C", 4,  24, ANALOG, 0,  "PROPOSED", "ADC1_IN13 (channel number from memory)"),
]

# Board pull resistors that define a pin while the MCU does not drive it
# (reset, ROM bootloader, unpowered MCU): (logical name, level, the spec's
# words).  check() looks for the words in DESIGN_SPEC section 4.
RESET_LEVELS = [
    ("GL_PIN_LCD_SCS",     0, "100 kohm pull-down on the LCD chip select"),
    ("GL_PIN_LCD_DISP",    0, "and on DISP"),
    ("GL_PIN_FLASH_CS",    1, "100 kohm pull-ups to V2V8 on the flash and IMU chip selects"),
    ("GL_PIN_IMU_CS",      1, "100 kohm pull-ups to V2V8 on the flash and IMU chip selects"),
    ("GL_PIN_CAM_PWR_EN",  0, "EN from MCU with 100k pull-down"),
]

# Signals of the charger / temperature circuit that the ROM bootloader must
# not be able to move: an output there would start or stop the charger, or
# feed the NTC divider for as long as a firmware update lasts.
NOT_ON_BOOTLOADER_PINS = ["GL_PIN_CHG_INHIBIT", "GL_PIN_NTC_BIAS", "GL_PIN_NTC_SENSE"]
PWDN_PINS = ["GL_PIN_CAM_L_PWDN", "GL_PIN_CAM_R_PWDN"]

# Pads that are not GPIO signals of this table (supplies, debug, crystal).
FIXED = [
    ("VBAT", 1), ("PC14-OSC32_IN", 3), ("PC15-OSC32_OUT", 4), ("NRST", 7),
    ("VSSA", 12), ("VDDA", 13), ("VSS", 18), ("VDD", 19), ("VCAP", 30), ("VSS", 31), ("VDD", 32),
    ("PA13-SWDIO", 46), ("VSS", 47), ("VDDUSB", 48), ("PA14-SWCLK", 49),
    ("VSS", 63), ("VDD", 64),
]
# I/O pads of the LQFP-64 package that a signal may use: 46 plus PH3-BOOT0.
IO_PADS_TOTAL = 46
BOOT0_PAD = 60

# Pins that the ROM bootloader of the STM32U575/585 initialises (AN2606, FROM
# MEMORY - the document could not be opened here; verify before the netlist).
# The firmware offers "reboot to ROM DFU", and during a firmware update the
# camera rail is off: a pin that the bootloader drives as a push-pull OUTPUT
# (idle-high TX, MISO) must not be a camera-facing net, or it back-powers the
# unpowered sensors - the rail rule this firmware enforces everywhere else.
#   (port, pin, function, True if the bootloader drives it as an output)
BOOTLOADER_PINS = [
    ("A", 9, "USART1_TX", True), ("A", 10, "USART1_RX", False),
    ("A", 2, "USART2_TX", True), ("A", 3, "USART2_RX", False),
    ("C", 10, "USART3_TX", True), ("C", 11, "USART3_RX", False),
    ("B", 6, "I2C1_SCL", False), ("B", 7, "I2C1_SDA", False),
    ("B", 10, "I2C2_SCL", False), ("B", 11, "I2C2_SDA", False),
    ("C", 0, "I2C3_SCL", False), ("C", 1, "I2C3_SDA", False),
    ("A", 4, "SPI1_NSS", False), ("A", 5, "SPI1_SCK", False), ("A", 6, "SPI1_MISO", True),
    ("A", 7, "SPI1_MOSI", False),
    ("B", 12, "SPI2_NSS", False), ("B", 13, "SPI2_SCK", False), ("B", 14, "SPI2_MISO", True),
    ("B", 15, "SPI2_MOSI", False),
    ("B", 8, "FDCAN1_RX", False), ("B", 9, "FDCAN1_TX", True),
]
# Camera-facing SPEC pins that ARE bootloader outputs.  DESIGN_SPEC fixes
# them, so the generator cannot move them: they are a release-gate item
# (series resistors, or accept and document).
BOOTLOADER_CONFLICTS_ACCEPTED = {("B", 9): "DCMI_D7 (SPEC)", ("A", 6): "DCMI_PIXCLK (SPEC)"}
CAMERA_FACING = [n for n in (
    "GL_PIN_CAM_L_PWDN", "GL_PIN_CAM_R_PWDN", "GL_PIN_CAM_SCCB_SDA", "GL_PIN_CAM_L_SCL",
    "GL_PIN_CAM_R_SCL", "GL_PIN_CAM_XVCLK", "GL_PIN_CAM_D0", "GL_PIN_CAM_D1", "GL_PIN_CAM_D2",
    "GL_PIN_CAM_D3", "GL_PIN_CAM_D4", "GL_PIN_CAM_D5", "GL_PIN_CAM_D6", "GL_PIN_CAM_D7",
    "GL_PIN_CAM_PIXCLK", "GL_PIN_CAM_HREF", "GL_PIN_CAM_VSYNC")]


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


def spec_pwdn_forbidden(text):
    """The pins DESIGN_SPEC forbids for a PWDN line, e.g. [("A", 9), ("A", 2), ("C", 10)]."""
    m = re.search(r"PWDN line has a 1 kohm series resistor and must not use a pin that the ROM "
                  r"bootloader drives as an output \(the USART transmit pins ([^,)]*(?:,| and)[^)]*?)(?:,|\))",
                  text)
    if not m:
        return None
    return [(p, int(n)) for p, n in re.findall(r"\bP([A-H])(\d+)", m.group(1))]


def spec_extcomin_ticks(text):
    """The EXTCOMIN divider of the spec: "(32768 / 547; ..." -> 547."""
    m = re.search(r"\(32768 / (\d+);", text)
    return int(m.group(1)) if m else None


def check(spec_text):
    facts = spec_facts(spec_text)
    errors = []
    seen_pads, seen_pins, seen_exti = {}, {}, {}
    by_name = {p[0]: p for p in PINS}
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
    # no PROPOSED camera-facing pin on a pin the ROM bootloader drives
    boot_out = {(port, pin): fn for port, pin, fn, out in BOOTLOADER_PINS if out}
    for name, port, pin, pad, kind, af, source, _note in PINS:
        if name in CAMERA_FACING and (port, pin) in boot_out:
            if source == "SPEC":
                if (port, pin) not in BOOTLOADER_CONFLICTS_ACCEPTED:
                    errors.append("%s (SPEC) is on P%s%d, a ROM bootloader output (%s), and is "
                                  "not in the accepted list" % (name, port, pin, boot_out[(port, pin)]))
            else:
                errors.append("%s is proposed on P%s%d, which the ROM bootloader drives (%s): "
                              "it would back-power the cameras during a firmware update" %
                              (name, port, pin, boot_out[(port, pin)]))
    # every DCMI pin of the spec must be in the table
    for key in [("C", 6), ("C", 7), ("C", 8), ("C", 9), ("C", 11), ("B", 6), ("B", 8), ("B", 9),
                ("A", 6), ("A", 4), ("B", 7), ("A", 8), ("B", 4), ("A", 11), ("A", 12), ("B", 2)]:
        if key not in facts:
            errors.append("DESIGN_SPEC no longer states P%s%d: the parser needs updating" % key)
        if key not in seen_pins:
            errors.append("P%s%d of DESIGN_SPEC is missing from the table" % key)
    # rev C2: PWDN lines off the pins the spec names
    forbidden = spec_pwdn_forbidden(spec_text)
    if not forbidden or len(forbidden) != 3:
        errors.append("DESIGN_SPEC no longer names the three pins a PWDN line must avoid: "
                      "the parser needs updating (got %r)" % (forbidden,))
    else:
        for name in PWDN_PINS:
            port, pin = by_name[name][1], by_name[name][2]
            if (port, pin) in forbidden:
                errors.append("%s is on P%s%d, which DESIGN_SPEC forbids for a PWDN line" %
                              (name, port, pin))
    # rev C2: the charger / temperature signals are on no ROM bootloader pin at all
    boot_any = {(port, pin): fn for port, pin, fn, _out in BOOTLOADER_PINS}
    for name in NOT_ON_BOOTLOADER_PINS:
        port, pin = by_name[name][1], by_name[name][2]
        if (port, pin) in boot_any:
            errors.append("%s is on P%s%d, a ROM bootloader pin (%s)" %
                          (name, port, pin, boot_any[(port, pin)]))
    # rev C2: EXTCOMIN divider and the pull resistors of the reset state
    if spec_extcomin_ticks(spec_text) is None:
        errors.append("DESIGN_SPEC no longer states the EXTCOMIN divider as '(32768 / N;'")
    flat = " ".join(spec_text.split())
    for name, _level, words in RESET_LEVELS:
        if name not in by_name:
            errors.append("%s of RESET_LEVELS is not in the table" % name)
        if words not in flat:
            errors.append("DESIGN_SPEC no longer says %r (reset level of %s)" % (words, name))
    # the pin budget of the package
    used_io = len([p for p in PINS if p[3] != BOOT0_PAD])
    if used_io > IO_PADS_TOTAL:
        errors.append("%d signals on %d I/O pads" % (used_io, IO_PADS_TOTAL))
    if errors:
        raise SystemExit("gen_pins: " + "\n          ".join(errors))


def generate(spec_text):
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
    w("/*")
    w(" * ROM BOOTLOADER PINS (AN2606 for the STM32U575/585, FROM MEMORY: verify).")
    w(" * X(port letter, pin number, function, 1 if the bootloader drives it as a")
    w(" * push-pull output).  \"Reboot to ROM DFU\" runs with the camera rail off, so")
    w(" * no camera-facing net may sit on a pin with a 1: tools/gen_pins.py refuses")
    w(" * to generate a PROPOSED row there and tests/test_pins.c checks the table.")
    w(" * Two SPEC rows do sit on such pins and cannot be moved from here:")
    for (port, pin), what in sorted(BOOTLOADER_CONFLICTS_ACCEPTED.items()):
        w(" *   P%s%d  %s  - RELEASE GATE: series resistor, or accept and document" % (port, pin, what))
    w(" * Also on bootloader pins, without the rail problem: PB10 (I2C2_SCL, open")
    w(" * drain) is the active-HIGH LCD chip select - its 100 kohm pull-down keeps the")
    w(" * panel unselected during an update; PA9 (USART1_TX) is VBUS_SENSE and")
    w(" * PA2 (USART2_TX) is VBAT_SENSE: both drive into high-value dividers; PC10")
    w(" * (USART3_TX) is GRAIN_CP4: no LED conducts while the other four charlieplex")
    w(" * pins are high-Z.")
    w(" * Rev C2: each PWDN line must avoid the bootloader's USART transmit pins")
    forb = spec_pwdn_forbidden(spec_text)
    w(" * %s (read from DESIGN_SPEC); they are on %s." %
      (", ".join("P%s%d" % f for f in forb),
       " and ".join("P%s%d" % (p[1], p[2]) for p in PINS if p[0] in PWDN_PINS)))
    w(" * CHG_INHIBIT, NTC_BIAS and NTC_SENSE are on no bootloader pin at all: in the")
    w(" * ROM bootloader the charger keeps its hardware default (ON) and nothing")
    w(" * supervises the cell temperature - see the README state table.")
    w(" */")
    w("#define GL_PINS_BOOTLOADER_TABLE(X) \\")
    for i, (port, pin, fn, drives) in enumerate(BOOTLOADER_PINS):
        w("    X(%s, %2d, %-10s %d)%s" % (port, pin, fn + ",", 1 if drives else 0,
                                          " \\" if i + 1 < len(BOOTLOADER_PINS) else ""))
    w("")
    w("/*")
    w(" * CHARGER STAT (PB0, input with pull-up): the pin must only ever be pulled")
    w(" * LOW by the charger.  The BOM part MCP73831 has, as remembered, a tri-state")
    w(" * STAT output that drives HIGH (to about VBUS, 5 V) when charging is complete;")
    w(" * PB0 carries analog functions and may not be 5 V tolerant.  RELEASE GATE:")
    w(" * fit the open-drain variant (MCP73832), or a series resistor / divider to a")
    w(" * 5 V tolerant pin with an external pull-up to V2V8.  Not verifiable here.")
    w(" *")
    w(" * VBUS_SENSE (PA9) wakes the MCU from Stop 2 through its EXTI line.  It is")
    w(" * NOT a WKUP pin: Shutdown mode, should it ever be wanted for storage, needs")
    w(" * VBUS on a wake-up pin (PA2 = WKUP4 as remembered).")
    w(" */")
    w("")
    w("/* Analog channels (ADC1).  PA3 = ADC1_IN8 is verified; PA2 = ADC1_IN7 and")
    w(" * PC4 = ADC1_IN13 are from memory of the same numbering. */")
    w("#define GL_PINS_ADC_CH_GRAIN_TIA 8")
    w("#define GL_PINS_ADC_CH_VBAT_DIV  7")
    w("#define GL_PINS_ADC_CH_CELL_NTC  13")
    w("")
    w("/*")
    w(" * RESET STATE (DESIGN_SPEC section 4, rev C2).  X(logical pin, level): the")
    w(" * level the board's pull resistor gives the pin while the MCU does not drive")
    w(" * it - in reset, in the ROM bootloader, unpowered.  gl_hal_init() must make")
    w(" * each of these pins an output AT THIS LEVEL (latch first, then the mode), and")
    w(" * no internal pull may be enabled against it.")
    w(" */")
    w("#define GL_PINS_RESET_TABLE(X) \\")
    for i, (name, level, _words) in enumerate(RESET_LEVELS):
        w("    X(%-18s %d)%s" % (name + ",", level, " \\" if i + 1 < len(RESET_LEVELS) else ""))
    w("")
    w("/*")
    w(" * CHG_INHIBIT (PH1, open drain, LOW = stop charging).  The pin hangs on the")
    w(" * gate of the PROG MOSFET, which a 1 Mohm / 1 Mohm divider on the charger")
    w(" * supply holds at about 2.4 V whenever VBUS is present.  It must be a pin")
    w(" * WITHOUT a protection diode to VDD (an \"FT\" pin): with the MCU unpowered a")
    w(" * diode would clamp the gate to one diode drop and switch the charger OFF,")
    w(" * which is exactly the case (cell at its protection cut-off) the default-on")
    w(" * circuit exists for.  PH0 / PH1 are FT pins as remembered: RELEASE GATE,")
    w(" * check the pin definition table of the datasheet.  Not verifiable here.")
    w(" *")
    w(" * NTC_BIAS (PH3-BOOT0).  All 46 other I/O pads are taken, so the bias of")
    w(" * the cell-temperature divider is proposed on the BOOT0 pin, which is an")
    w(" * ordinary I/O once the MCU has started.  It is driven push-pull HIGH for")
    w(" * about 0.7 ms per measurement and is high-Z otherwise; its 10 kohm BOOT0")
    w(" * pull-down and the divider (10.0 kohm + NTC to ground) both pull it LOW, so")
    w(" * the pin reads 0 at every reset.  RELEASE GATE for the netlist: confirm, or")
    w(" * free another pad.")
    w(" */")
    w("")
    w("/* EXTCOMIN: LSE ticks per period, read from DESIGN_SPEC (\"32768 / N\"). */")
    w("#define GL_PINS_EXTCOMIN_LSE_TICKS %d" % spec_extcomin_ticks(spec_text))
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
    text = generate(spec)
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
