#!/usr/bin/env python3
"""Generate hal/stm32u5/gl_pins.h from the netlist's pin map.

Usage:
    gen_pins.py [--check] <pinmap.json> <output gl_pins.h>
    gen_pins.py --selftest <pinmap.json>

SINGLE INPUT.  electrical/gl1_main/pinmap.json is exported by the netlist
(check_pinmap.py, which proves every row against ST's open pin data).  It is
the ONLY place where a pin is assigned: this script holds no port, no pin
number, no pad and no alternate function.  What it does hold is firmware
knowledge that is not a pin assignment:

  * LOGICAL: the signals of hal/gl_hal.h (gl_pin_t) IN THEIR ORDER, which is
    part of the simulator's trace format;
  * how the words of the pin map ("OUT_PP", "low or analog while V2V8_CAM is
    off", "none / 100k to GND") become the columns of the table;
  * NOTE_RULES: one entry per firmware note of the pin map.  A note this
    script does not know stops the generation: somebody has to read it, act
    on it in the firmware, and then add its key phrase here.

The layout step may still exchange pins.  The procedure is then
`make pins` (this script) and `make test`: tests/test_pins.c reads
pinmap.json again, independently, and proves the header against it.

RULES this script refuses to generate against (tests/test_pins.c checks the
same on the generated table):
  - a signal of gl_pin_t missing from the pin map, or a pin-map signal that
    is neither in gl_pin_t nor one of the fixed pads (crystal, SWD, BOOT0);
  - two signals on one pin or pad (the one declared exception: the BOOT0
    strap shares its pad with one signal, which must be an output that rests
    low or analog);
  - two interrupt signals on one EXTI line (the line is the pin number);
  - a camera PWDN line on a pin the ROM bootloader drives;
  - CHG_INHIBIT, NTC_BIAS, NTC_SENSE or CAM_PWR_EN on any ROM bootloader pin;
  - a camera-facing signal that is not SPEC on a pin the bootloader drives;
  - anything but an input or an alternate-function output on a UCPD CC pad;
  - an AF row without an AF number, an ADC signal without its channel, a
    wake-up signal without its wake-up pin;
  - a pin map whose own verification did not pass.

With --check nothing is written; exit status 1 if the header is stale.
With --selftest nothing is written either: the script seeds defects into a
copy of the pin map, one at a time (SEEDED below: a pin used twice, a PWDN
line on a pin the ROM bootloader drives, an output on a CC pad, a firmware
note nobody has read, ...), and fails unless every one is refused and the
unchanged pin map is accepted.
"""
import copy
import hashlib
import json
import re
import sys

# The signals of hal/gl_hal.h, in the order of gl_pin_t (names without the
# GL_PIN_ prefix = the "signal" of the pin map).  NOT a pin assignment.
LOGICAL = [
    "CAM_PWR_EN", "CAM_L_PWDN", "CAM_R_PWDN", "CAM_SCCB_SDA", "CAM_L_SCL", "CAM_R_SCL",
    "CAM_XVCLK", "CAM_D0", "CAM_D1", "CAM_D2", "CAM_D3", "CAM_D4", "CAM_D5", "CAM_D6", "CAM_D7",
    "CAM_PIXCLK", "CAM_HREF", "CAM_VSYNC",
    "LCD_SCS", "LCD_DISP", "LCD_EXTCOMIN",
    "SPI1_SCK", "SPI1_MOSI", "SPI1_MISO", "SPI2_SCK", "SPI2_MOSI", "SPI2_MISO",
    "FLASH_CS", "IMU_CS", "IMU_INT1", "IMU_INT2",
    "GRAIN_CP0", "GRAIN_CP1", "GRAIN_CP2", "GRAIN_CP3", "GRAIN_CP4",
    "OPAMP_VINP", "OPAMP_VINM", "OPAMP_VOUT",
    "VBAT_SENSE", "CHG_STAT", "CHG_INHIBIT", "VBUS_SENSE",
    "USB_DM", "USB_DP",
    "NTC_BIAS", "NTC_SENSE",
]
# Pin-map rows that are not signals of gl_pin_t: fixed functions of the pad.
FIXED_SIGNALS = ["OSC32_IN", "OSC32_OUT", "SWDIO", "SWCLK", "BOOT0"]

# pinmap "mode" -> GL_PINFN_*
KIND = {"OUT_PP": "GPIO", "AF": "AF", "ANALOG": "ANALOG", "SCCB_OD": "SCCB", "EXTI": "EXTI"}

# Signals with a rule of their own.
PWDN = ["CAM_L_PWDN", "CAM_R_PWDN"]
NOT_ON_BOOTLOADER_PINS = ["CHG_INHIBIT", "NTC_BIAS", "NTC_SENSE", "CAM_PWR_EN"]
EXTI_SIGNALS = ["IMU_INT1", "IMU_INT2", "VBUS_SENSE", "CHG_STAT"]
WAKEUP_SIGNALS = ["IMU_INT1", "VBUS_SENSE"]          # must sit on a PWR wake-up pin
ADC_SIGNALS = [("GRAIN_TIA", "OPAMP_VOUT"), ("VBAT_DIV", "VBAT_SENSE"), ("CELL_NTC", "NTC_SENSE")]
GRAIN_LINES = ["GRAIN_CP0", "GRAIN_CP1", "GRAIN_CP2", "GRAIN_CP3", "GRAIN_CP4"]

# One entry per firmware note of pinmap.json: (key, regex that identifies the
# note, where the firmware acts on it).  check() requires every note of the
# pin map to match exactly one entry and every entry to be matched.
NOTE_RULES = [
    ("regenerate", r"^Regenerate gl_pins\.h from pinmap\.json",
     "this file; `make pins`, `make pins-check`"),
    ("chg_inhibit", r"^CHG_INHIBIT \(P[A-H]\d+\) is a PUSH-PULL output, HIGH = stop charging",
     "GL_PINS_CHG_INHIBIT_ACTIVE_HIGH; drivers/power.c inhibit_()"),
    ("chg_stat", r"^CHG_STAT is on P[A-H]\d+ \(EXTI\d+\): the BQ25101's open-drain CHG output .* low = charging",
     "GL_PINS_CHG_STAT_LOW_IS_CHARGING; no internal pull (GL_PINPULL_NONE); drivers/power.c"),
    ("exti", r"^EXTI lines: IMU_INT1 P[A-H]\d+ = EXTI\d+",
     "GL_PINS_EXTI_*; hal/stm32u5/gl_hal_stm32u5.c builds its vectors from them"),
    ("ucpd", r"^UCPD \(PROVISIONAL.*Set UCPD_DBDIS in PWR_UCPDR",
     "GL_PINS_UCPD_TABLE, GL_PINS_UCPD_DBDIS_FIRST; first statement of gl_hal_init()"),
    ("otg_vbus", r"^P[A-H]\d+ is USB_OTG_FS_VBUS and carries GRAIN_CP\d",
     "GL_PINS_USB_VBUS_SENSING_OFF; hal/stm32u5/gl_hal_stm32u5_usb.c"),
    ("usb_supply", r"^USB supply: set the USB-supply-valid bit only while BOTH VBUS_SENSE",
     "gl_hal_usb_supply_ok(); the application stops USB when it is false"),
    ("vbus_sense", r"^VBUS_SENSE: divider 100 kohm : 100 kohm on the VBUS pad",
     "GL_PINS_VBUS_REMOVAL_SEEN_MS; the simulator's VBUS_SENSE lag"),
    ("boot0", r"^CAM_R_PWDN is on P[A-H]\d+, the BOOT0 pad",
     "GL_PINS_BOOT0_SHARED_WITH; supply model: 0.28 mA while driven high"),
    ("imu_cs", r"^IMU_CS is P[A-H]\d+ and LCD_DISP is P[A-H]\d+",
     "the table"),
    ("rom_int2", r"^Before a jump to the ROM bootloader leave the IMU with its INT2 output static",
     "app/gl_usb.c: gl_imu_stop() before gl_hal_reboot(GL_REBOOT_ROM_DFU)"),
    ("grain_bias", r"^The grain bias divider hangs on LCD_DISP .* DISP must have been high for (\d+) ms",
     "GL_PINS_GRAIN_BIAS_DISP_MS; drivers/grain_frontend.c gl_grain_fe_power()"),
    ("jtag", r"^Switch P[A-H]\d+, P[A-H]\d+, P[A-H]\d+ away from JTAG",
     "gl_hal_init() gives every table pin its mode (the U5 has no remap bit: the mode write is the switch)"),
    ("rail", r"^Every camera-facing pin low or analog while V2V8_CAM is off",
     "GL_PINRAIL_PARKED column; drivers/ov7692.c; the simulator's rail rule"),
    ("floating", r"^Lines without a board pull float while the MCU is in reset or in the ROM bootloader",
     "GL_PINS_FLOATING_TABLE, GL_PINPULL_DOWN on the two MISO rows; gl_hal_init()"),
    ("opamp_out", r"^P[A-H]\d+ \(OPAMP1 output, the ROM's USART2_RX\) is held high by R31",
     "GL_PINSLEEP_ANALOG for OPAMP_VOUT; the simulator counts a driven pin"),
    ("lse_drive", r"^LSE drive: medium-low or higher",
     "GL_PINS_LSE_DRIVE_MEDIUM_LOW; clocks_osc_() in the backend"),
]


class PinError(Exception):
    pass


def port_pin(text):
    m = re.fullmatch(r"P([A-H])(\d+)", text)
    if not m or int(m.group(2)) > 15:
        raise PinError("not a port pin: %r" % (text,))
    return m.group(1), int(m.group(2))


def parse_pull(row):
    """pinmap "pull" = "<MCU-internal> / <board>" -> (internal, board)."""
    text = row["pull"]
    parts = [p.strip() for p in text.split(" / ", 1)]
    mcu = parts[0]
    board = parts[1] if len(parts) > 1 else ""
    if mcu == "none":
        internal = "NONE"
    elif mcu.startswith("reset state (pull-up)"):
        internal = "UP"
    elif mcu.startswith("reset state (pull-down)"):
        internal = "DOWN"
    elif re.match(r"\d+k to GND", mcu) and not board:
        internal, board = "NONE", mcu      # a strap row states only its resistor
    else:
        raise PinError("%s: MCU pull %r not understood" % (row["signal"], mcu))
    if not board:
        brd = "NONE"
    elif board.startswith("divider"):
        brd = "DIVIDER"
    elif "to GND" in board:
        brd = "DOWN"
    elif "to V2V8_CAM" in board:
        brd = "UP_CAM"
    elif "to V2V8" in board:
        brd = "UP"
    elif "series" in board:
        brd = "SERIES"
    else:
        raise PinError("%s: board circuit %r not understood" % (row["signal"], board))
    return internal, brd


def parse_state(row):
    """pinmap "initial_state" -> (state while V2V8_CAM is off, state in sleep)."""
    s = row["initial_state"]
    rail = "PARKED" if "while V2V8_CAM is off" in s else "ANY"
    if rail == "PARKED":
        if not s.startswith("low or analog"):
            raise PinError("%s: rail-off state %r not understood" % (row["signal"], s))
        return rail, "PARKED"
    if s.startswith("analog or low"):
        sleep = "PARKED"
    elif s.startswith("analog"):
        sleep = "ANALOG"
    elif s.startswith("input"):
        sleep = "INPUT"
    elif s.startswith("high"):
        sleep = "HIGH"
    elif s.startswith("low"):
        sleep = "LOW"
    else:
        raise PinError("%s: resting state %r not understood" % (row["signal"], s))
    return rail, sleep


def note_index(notes):
    """{key: (index, text, match)}; every note known, every rule matched."""
    found = {}
    errors = []
    for i, text in enumerate(notes):
        hits = [(key, re.search(rx, text)) for key, rx, _where in NOTE_RULES]
        hits = [(k, m) for k, m in hits if m]
        if len(hits) != 1:
            errors.append("firmware note %d of the pin map is %s: %r" %
                          (i + 1, "not known to tools/gen_pins.py (read it, act on it in the "
                                  "firmware, then add it to NOTE_RULES)" if not hits
                           else "matched by several rules", text[:90]))
            continue
        key, m = hits[0]
        if key in found:
            errors.append("two firmware notes match the rule %r" % key)
        found[key] = (i + 1, text, m)
    for key, _rx, _where in NOTE_RULES:
        if key not in found and not errors:
            errors.append("the pin map no longer carries the firmware note %r: the firmware "
                          "still acts on it (NOTE_RULES)" % key)
    if errors:
        raise PinError("\n          ".join(errors))
    return found


def build(doc):
    """Check the pin map and return everything generate() prints."""
    errors = []
    ver = doc.get("verification", {})
    if not ver.get("checks_passed", False):
        errors.append("the pin map's own verification did not pass (verification.checks_passed)")
    rows = {}
    for r in doc["pins"]:
        if r["signal"] in rows:
            errors.append("signal %s appears twice in the pin map" % r["signal"])
        rows[r["signal"]] = r
    for name in LOGICAL:
        if name not in rows:
            errors.append("the pin map has no signal %s (hal/gl_hal.h needs it)" % name)
    for name in rows:
        if name not in LOGICAL and name not in FIXED_SIGNALS:
            errors.append("the pin map has a signal %s that hal/gl_hal.h does not know: add it to "
                          "gl_pin_t and to LOGICAL, or drop it from the netlist" % name)
    if errors:
        raise PinError("\n          ".join(errors))

    notes = note_index(doc["firmware_notes"])

    # ---- the table ----
    table = []
    by_pin = {}
    by_pad = {}
    for name in LOGICAL:
        r = rows[name]
        port, pin = port_pin(r["port_pin"])
        if r["mode"] not in KIND:
            raise PinError("%s: mode %r is not a signal mode" % (name, r["mode"]))
        kind = KIND[r["mode"]]
        internal, board = parse_pull(r)
        rail, sleep = parse_state(r)
        af = r["af"]
        if kind == "AF" and af is None:
            errors.append("%s is an alternate function without an AF number" % name)
        if kind != "AF" and af is not None:
            errors.append("%s has an AF number but is not an alternate function" % name)
        if r["source"] not in ("SPEC", "PROPOSED", "CHANGED"):
            errors.append("%s: source %r" % (name, r["source"]))
        if (port, pin) in by_pin:
            errors.append("%s and %s share P%s%d" % (name, by_pin[(port, pin)], port, pin))
        if r["pad"] in by_pad:
            errors.append("%s and %s share pad %d" % (name, by_pad[r["pad"]], r["pad"]))
        by_pin[(port, pin)] = name
        by_pad[r["pad"]] = name
        table.append({
            "name": name, "port": port, "pin": pin, "pad": r["pad"], "kind": kind,
            "af": af if af is not None else 0, "pull": internal, "board": board,
            "exti": pin if kind == "EXTI" else None, "rail": rail, "sleep": sleep,
            "source": r["source"], "function": r["function"], "row": r,
        })
    t = {e["name"]: e for e in table}

    # ---- fixed pads: crystal, SWD, the BOOT0 strap ----
    fixed = []
    boot0_shared = None
    for name in FIXED_SIGNALS:
        if name not in rows:
            errors.append("the pin map has no row %s" % name)
            continue
        r = rows[name]
        port, pin = port_pin(r["port_pin"])
        owner = by_pin.get((port, pin))
        if name == "BOOT0":
            if r["mode"] != "STRAP":
                errors.append("BOOT0 is not a STRAP row")
            if owner is not None:
                e = t[owner]
                # the pad may carry ONE signal, and only one that cannot lift
                # the strap at reset: an output that rests low or analog, on a
                # net whose only level-defining part is the strap resistor
                if e["kind"] != "GPIO" or e["sleep"] != "PARKED" or e["board"] != "DOWN":
                    errors.append("%s shares the BOOT0 pad but is not an output that rests low "
                                  "or analog on a pulled-down net" % owner)
                boot0_shared = owner
        elif owner is not None:
            errors.append("%s is on P%s%d, which is %s" % (owner, port, pin, name))
        fixed.append((name, port, pin, r["pad"]))
    for sp in doc.get("supply_pads", []):
        if sp["pad"] in by_pad:
            errors.append("%s is on pad %d, which is the supply pad %s" %
                          (by_pad[sp["pad"]], sp["pad"], sp["pin"]))

    # ---- interrupt lines ----
    seen_line = {}
    for e in table:
        if e["kind"] == "EXTI":
            if e["name"] not in EXTI_SIGNALS:
                errors.append("%s is an interrupt input the firmware has no handler for" % e["name"])
            if e["pin"] in seen_line:
                errors.append("%s and %s share EXTI line %d" % (e["name"], seen_line[e["pin"]], e["pin"]))
            seen_line[e["pin"]] = e["name"]
    for name in EXTI_SIGNALS:
        if t[name]["kind"] != "EXTI":
            errors.append("%s must be an interrupt input (mode EXTI)" % name)
    # note 4 names the four lines: it must agree with the rows
    for sig, line in re.findall(r"(IMU_INT1|IMU_INT2|VBUS_SENSE|CHG_STAT) P[A-H]\d+ = EXTI(\d+)",
                                notes["exti"][1]):
        if t[sig]["pin"] != int(line):
            errors.append("firmware note %d says %s is EXTI%s, its row says P%s%d" %
                          (notes["exti"][0], sig, line, t[sig]["port"], t[sig]["pin"]))

    # ---- wake-up pins (ship mode wakes on VBUS from Shutdown) ----
    wkup = {}
    for name in WAKEUP_SIGNALS:
        m = re.search(r"\(PWR_WKUP(\d+)\)", t[name]["function"])
        if not m or ("PWR_WKUP" + m.group(1)) not in t[name]["row"].get("wakeup", []):
            errors.append("%s is not on a PWR wake-up pin (function %r)" % (name, t[name]["function"]))
        else:
            wkup[name] = int(m.group(1))
    if len(set(wkup.values())) != len(wkup):
        errors.append("two wake-up signals share one wake-up line: %r" % (wkup,))

    # ---- ADC channels ----
    adc = {}
    for label, name in ADC_SIGNALS:
        m = re.search(r"ADC1_IN(\d+)", t[name]["function"])
        if not m or ("ADC1_IN" + m.group(1)) not in t[name]["row"].get("adc", []):
            errors.append("%s has no ADC1 channel in the pin map" % name)
        else:
            adc[label] = int(m.group(1))
        if t[name]["kind"] != "ANALOG":
            errors.append("%s must be an analog pin" % name)

    # ---- ROM bootloader pins ----
    boot = []
    for e in table:
        b = e["row"].get("bootloader")
        if not b:
            continue
        fn, what = b
        if what not in ("drive", "listen"):
            errors.append("%s: bootloader role %r" % (e["name"], what))
        boot.append((e["name"], e["port"], e["pin"], fn, 1 if what == "drive" else 0))
        if e["name"] in NOT_ON_BOOTLOADER_PINS:
            errors.append("%s is on P%s%d, a ROM bootloader pin (%s)" %
                          (e["name"], e["port"], e["pin"], fn))
        if what == "drive":
            if e["name"] in PWDN:
                errors.append("%s is on P%s%d, which the ROM bootloader drives (%s)" %
                              (e["name"], e["port"], e["pin"], fn))
            elif e["rail"] == "PARKED" and e["source"] != "SPEC":
                errors.append("%s (camera-facing, %s) is on P%s%d, which the ROM bootloader "
                              "drives (%s): it would back-power the cameras during an update" %
                              (e["name"], e["source"], e["port"], e["pin"], fn))

    # ---- camera-facing pins: the note names them ----
    parked = {e["name"] for e in table if e["rail"] == "PARKED"}
    named = {by_pin.get(port_pin(p)) for p in re.findall(r"\bP[A-H]\d+\b", notes["rail"][1])}
    named |= {e["name"] for e in table if e["function"].startswith("DCMI_")}
    if None in named or named != parked:
        errors.append("firmware note %d (camera-facing pins) and the rows that say 'while "
                      "V2V8_CAM is off' disagree: %s" %
                      (notes["rail"][0], sorted(x for x in (named ^ parked) if x)))
    first, last = LOGICAL.index("CAM_L_PWDN"), LOGICAL.index("CAM_VSYNC")
    if parked != set(LOGICAL[first:last + 1]):
        errors.append("the camera-facing rows are not GL_PIN_CAM_FACING_FIRST..LAST of hal/gl_hal.h")

    # ---- UCPD pads: an input, or an alternate-function output ----
    ucpd = []
    for role, pins in sorted(doc["ucpd_pads"].items()):
        for p in pins:
            owner = by_pin.get(port_pin(p))
            port, pin = port_pin(p)
            ucpd.append((role, port, pin, owner))
            if owner is None or "_CC" not in role or "DBCC" in role:
                continue
            if t[owner]["kind"] not in ("EXTI", "ANALOG", "AF"):
                errors.append("%s on P%s%d: a UCPD CC pad may carry an input or an alternate-"
                              "function output only" % (owner, port, pin))
            if owner not in doc.get("ucpd_pad_reasons", {}):
                errors.append("%s on the UCPD pad P%s%d has no stated reason in the pin map" %
                              (owner, port, pin))

    # ---- lines that float in reset (note 15), and the MISO pull-downs ----
    ftext = notes["floating"][1]
    head, _, tail = ftext.partition("gl_hal_init() must give each its level")
    floating = []
    for p in re.findall(r"\bP[A-H]\d+\b", head):
        owner = by_pin.get(port_pin(p))
        if owner is None:
            errors.append("firmware note %d names %s, which carries no signal" % (notes["floating"][0], p))
            continue
        if t[owner]["board"] not in ("NONE", "SERIES"):
            errors.append("firmware note %d says %s floats in reset, its row has a board pull" %
                          (notes["floating"][0], owner))
        floating.append(owner)
    m = re.search(r"keep an internal pull-down on (P[A-H]\d+) and (P[A-H]\d+)", tail)
    if not m:
        errors.append("firmware note %d no longer names the two pins that keep an internal "
                      "pull-down" % notes["floating"][0])
    else:
        for p in m.groups():
            owner = by_pin.get(port_pin(p))
            if owner is None or t[owner]["kind"] != "AF" or t[owner]["sleep"] != "INPUT":
                errors.append("firmware note %d: %s is not a bus input" % (notes["floating"][0], p))
            else:
                t[owner]["pull"] = "DOWN"

    # ---- levels the board gives a pin the MCU does not drive ----
    reset = []
    for e in table:
        if e["board"] in ("DOWN", "UP"):
            level = 1 if e["board"] == "UP" else 0
            # gl_hal_init() takes the pin over AT this level if it is an
            # output with a resting level of its own
            handover = 1 if (e["kind"] == "GPIO" and e["sleep"] in ("LOW", "HIGH")) else 0
            if handover and (e["sleep"] == "HIGH") != (level == 1):
                errors.append("%s rests %s but its board resistor pulls the other way" %
                              (e["name"], e["sleep"]))
            reset.append((e["name"], level, handover))

    # ---- charger circuit, as the notes state it ----
    chg_text = notes["chg_inhibit"][1]
    if t["CHG_INHIBIT"]["kind"] != "GPIO" or t["CHG_INHIBIT"]["board"] != "DOWN":
        errors.append("CHG_INHIBIT must be a push-pull output on a pulled-down gate")
    if "analog or low = charger on" not in chg_text:
        errors.append("firmware note %d no longer says 'analog or low = charger on'" % notes["chg_inhibit"][0])
    if t["CHG_STAT"]["board"] != "UP" or t["CHG_STAT"]["pull"] != "NONE":
        errors.append("CHG_STAT must be an input with the board's pull-up and no internal pull")
    if t["VBUS_SENSE"]["board"] != "DIVIDER":
        errors.append("VBUS_SENSE must hang on the VBUS divider")
    m = re.search(r"removal from the cradle is seen within about (\d+) ms", notes["vbus_sense"][1])
    if not m:
        errors.append("firmware note %d no longer states the VBUS removal time" % notes["vbus_sense"][0])
    vbus_ms = int(m.group(1)) if m else 0
    grain_ms = int(notes["grain_bias"][2].group(1))

    # ---- grain LEDs ----
    leds = []
    for i, led in enumerate(doc.get("grain_leds", [])):
        if led["anode_line"] not in GRAIN_LINES or led["cathode_line"] not in GRAIN_LINES:
            errors.append("grain LED %s is on a line that is not a charlieplex line" % led["ref"])
            continue
        leds.append((led["ref"], 1 if led["colour"] == "red" else 0,
                     int(round(led["azimuth_deg"] * 10.0)),
                     GRAIN_LINES.index(led["anode_line"]), GRAIN_LINES.index(led["cathode_line"])))
    if len(leds) != 16:
        errors.append("the pin map lists %d grain LEDs, the firmware drives 16" % len(leds))

    ticks = doc.get("extcomin_lse_ticks")
    if not isinstance(ticks, int) or not 547 <= ticks <= 32768:
        errors.append("extcomin_lse_ticks %r is outside 1..59.9 Hz" % (ticks,))

    if errors:
        raise PinError("\n          ".join(errors))
    return {
        "table": table, "fixed": fixed, "boot0_shared": boot0_shared, "supply": doc["supply_pads"],
        "boot": boot, "ucpd": ucpd, "wkup": wkup, "adc": adc, "reset": reset, "floating": floating,
        "leds": leds, "ticks": ticks, "notes": notes, "vbus_ms": vbus_ms, "grain_ms": grain_ms,
    }


def wrap(text, width, first, rest):
    """Wrap one paragraph into comment lines."""
    out, line = [], first
    for word in text.split():
        if len(line) + len(word) + 1 > width and line.strip(" *") != "":
            out.append(line.rstrip())
            line = rest
        line += word + " "
    out.append(line.rstrip())
    return out


def generate(doc, src_name, sha):
    g = build(doc)
    out = []
    w = out.append
    ver = doc["verification"]
    w("/*")
    w(" * gl_pins.h - GENERATED by tools/gen_pins.py.  DO NOT EDIT: change the netlist's")
    w(" * pin map and run `make pins`.")
    w(" *")
    w(" *   source   %s" % src_name)
    w(" *   sha256   %s" % sha)
    w(" *   design   %s, %s (%s), %s" % (doc["design"], doc["mcu"], doc["package"], doc["spec"]))
    for line in wrap(doc["status"], 84, " *   status   ", " *            "):
        w(line)
    for line in wrap("checks_passed %s, partial %s: %s" %
                     (str(bool(ver["checks_passed"])).lower(),
                      str(bool(ver.get("partial", False))).lower(), ver.get("source", "?")),
                     84, " *   proof    ", " *            "):
        w(line)
    w(" *            %d statements of that proof are PROVISIONAL (ROM bootloader pin list," %
      len(ver.get("provisional", [])))
    w(" *            UCPD behaviour, electrical limits): see pinmap.json.")
    w(" *")
    w(" * The pin map is the netlist's.  This header holds no pin of its own; the")
    w(" * layout step may still exchange pins, and then this file is regenerated by")
    w(" * `make pins` (tests/test_pins.c proves it against pinmap.json again).  The")
    w(" * header contains only macros and can be included anywhere.")
    w(" *")
    w(" * SCCB: both cameras answer at one address and have separate clock lines,")
    w(" * which no single I2C peripheral can drive, so the three SCCB lines are")
    w(" * bit-banged open-drain GPIOs (GL_PINFN_SCCB).")
    w(" */")
    w("#ifndef GL_PINS_H")
    w("#define GL_PINS_H")
    w("")
    w("#define GL_PINS_SOURCE_SHA256 \"%s\"" % sha)
    w("")
    w("/* Function kind (the pin map's \"mode\"): what GL_PIN_MODE_ALTERNATE means. */")
    w("#define GL_PINFN_GPIO   0 /* OUT_PP: no alternate function, a push-pull output */")
    w("#define GL_PINFN_AF     1 /* AF: alternate function number in the table */")
    w("#define GL_PINFN_ANALOG 2 /* ANALOG: op-amp or ADC input */")
    w("#define GL_PINFN_SCCB   3 /* SCCB_OD: bit-banged SCCB line, open-drain output */")
    w("#define GL_PINFN_EXTI   4 /* EXTI: input with an interrupt line */")
    w("")
    w("/* MCU-internal pull the firmware enables on the pin (in every mode but ANALOG). */")
    w("#define GL_PINPULL_NONE 0")
    w("#define GL_PINPULL_UP   1")
    w("#define GL_PINPULL_DOWN 2")
    w("")
    w("/* What the BOARD puts on the net. */")
    w("#define GL_PINBRD_NONE    0 /* nothing that defines a level: the line floats in reset */")
    w("#define GL_PINBRD_DOWN    1 /* resistor to ground */")
    w("#define GL_PINBRD_UP      2 /* resistor to V2V8 (always on) */")
    w("#define GL_PINBRD_UP_CAM  3 /* resistor to V2V8_CAM (off with the camera rail) */")
    w("#define GL_PINBRD_SERIES  4 /* a series resistor only */")
    w("#define GL_PINBRD_DIVIDER 5 /* divider from the VBUS pad */")
    w("")
    w("/* State while the camera rail V2V8_CAM is off. */")
    w("#define GL_PINRAIL_ANY    0 /* not camera-facing */")
    w("#define GL_PINRAIL_PARKED 1 /* camera-facing: ANALOG or driven LOW, nothing else */")
    w("")
    w("/* State asleep (Stop 2 out of the cradle, display off) - the resting state. */")
    w("#define GL_PINSLEEP_ANALOG 0 /* high impedance */")
    w("#define GL_PINSLEEP_INPUT  1 /* digital input (an interrupt line, or a bus input) */")
    w("#define GL_PINSLEEP_LOW    2 /* held low (output latch, or the idle level of its bus) */")
    w("#define GL_PINSLEEP_HIGH   3 /* held high */")
    w("#define GL_PINSLEEP_PARKED 4 /* ANALOG or driven LOW */")
    w("")
    w("/* Where the row comes from. */")
    w("#define GL_PINSRC_SPEC     0 /* fixed by DESIGN_SPEC section 4 */")
    w("#define GL_PINSRC_PROPOSED 1 /* the firmware's proposal, kept by the netlist */")
    w("#define GL_PINSRC_CHANGED  2 /* moved by the netlist */")
    w("")
    w("#define GL_PINS_NO_EXTI 255")
    w("")
    w("/*")
    w(" * X(logical pin, port letter, pin number, LQFP-64 pad, function kind, AF,")
    w(" *   internal pull, board circuit, EXTI line, state with the camera rail off,")
    w(" *   state asleep, source)")
    w(" * Rows are in the order of gl_pin_t (hal/gl_hal.h).")
    w(" */")
    w("#define GL_PINS_TABLE(X) \\")
    width = max(len(e["name"]) for e in g["table"]) + len("GL_PIN_,")
    lines = []
    for e in g["table"]:
        exti = ("%d" % e["exti"]) if e["exti"] is not None else "GL_PINS_NO_EXTI"
        lines.append(
            "    X(%-*s %s, %2d, %2d, GL_PINFN_%-7s %2d, GL_PINPULL_%-5s GL_PINBRD_%-8s %-17s"
            "GL_PINRAIL_%-7s GL_PINSLEEP_%-7s GL_PINSRC_%-9s /* %s */" %
            (width, "GL_PIN_" + e["name"] + ",", e["port"], e["pin"], e["pad"], e["kind"] + ",",
             e["af"], e["pull"] + ",", e["board"] + ",", exti + ",", e["rail"] + ",",
             e["sleep"] + ",", e["source"] + ")", e["function"]))
    for i, line in enumerate(lines):
        w(line + (" \\" if i + 1 < len(lines) else ""))
    w("")
    w("#define GL_PINS_COUNT %d" % len(g["table"]))
    w("")
    w("/* Pads that carry no signal of the table. */")
    for sp in g["supply"]:
        w("/*   pad %2d  %-7s %s */" % (sp["pad"], sp["pin"], sp["net"]))
    for name, port, pin, pad in g["fixed"]:
        w("/*   pad %2d  P%s%-5d %s */" % (pad, port, pin, name))
    w("")
    if g["boot0_shared"] is not None:
        e = [x for x in g["table"] if x["name"] == g["boot0_shared"]][0]
        w("/* The BOOT0 strap (P%s%d, pad %d, pulled down on the board) shares its pad with" %
          (e["port"], e["pin"], e["pad"]))
        w(" * ONE signal.  The pad is sampled at reset: the signal rests low or analog, so")
        w(" * the strap reads 0 at every reset; while it is driven high the strap resistor")
        w(" * takes its current. */")
        w("#define GL_PINS_BOOT0_SHARED_WITH GL_PIN_%s" % g["boot0_shared"])
        w("")
    w("/*")
    w(" * ROM BOOTLOADER PINS that carry a signal (the pin list is PROVISIONAL in the")
    w(" * pin map: memory of ST AN2606).  X(logical pin, port letter, pin number,")
    w(" * bootloader function, 1 if the bootloader DRIVES the pin).  The ROM runs with")
    w(" * the camera rail off and the charger on its hardware default.")
    w(" */")
    w("#define GL_PINS_BOOTLOADER_TABLE(X) \\")
    for i, (name, port, pin, fn, drives) in enumerate(g["boot"]):
        w("    X(%-21s %s, %2d, %-14s %d)%s" % ("GL_PIN_" + name + ",", port, pin, fn + ",", drives,
                                                " \\" if i + 1 < len(g["boot"]) else ""))
    w("")
    w("/*")
    w(" * UCPD pads (what they do is PROVISIONAL in the pin map).  X(role, port letter,")
    w(" * pin number, logical pin).  After reset a HIGH level on a DBCC pad switches a")
    w(" * 5.1 kohm pull-down onto its CC pad until UCPD_DBDIS is set: gl_hal_init()")
    w(" * sets it BEFORE it configures any pin (GL_PINS_UCPD_DBDIS_FIRST).  A CC pad")
    w(" * carries an input or an alternate-function output, nothing else.")
    w(" */")
    w("#define GL_PINS_UCPD_TABLE(X) \\")
    for i, (role, port, pin, owner) in enumerate(g["ucpd"]):
        w("    X(%-12s %s, %2d, %s)%s" % (role + ",", port, pin,
                                         ("GL_PIN_" + owner) if owner else "GL_PIN_COUNT",
                                         " \\" if i + 1 < len(g["ucpd"]) else ""))
    w("#define GL_PINS_UCPD_DBDIS_FIRST 1")
    w("")
    w("/* Interrupt lines (the EXTI line of a pin is its pin number) and the PWR wake-up")
    w(" * pins: IMU_INT1 wakes from Stop 2 by its EXTI line; VBUS_SENSE also wakes the")
    w(" * MCU from Shutdown (ship mode) through its wake-up pin. */")
    for name in EXTI_SIGNALS:
        e = [x for x in g["table"] if x["name"] == name][0]
        w("#define GL_PINS_EXTI_%-11s %d /* P%s%d */" % (name, e["pin"], e["port"], e["pin"]))
    for name in WAKEUP_SIGNALS:
        w("#define GL_PINS_WKUP_%-11s %d /* PWR_WKUP%d */" % (name, g["wkup"][name], g["wkup"][name]))
    w("")
    w("/* Analog channels (ADC1), read from the pin map. */")
    for label, _name in ADC_SIGNALS:
        w("#define GL_PINS_ADC_CH_%-9s %d" % (label, g["adc"][label]))
    w("")
    w("/*")
    w(" * RESET LEVELS.  X(logical pin, level, hand-over): the level the board's")
    w(" * resistor gives the pin while the MCU does not drive it - in reset, in the ROM")
    w(" * bootloader, in Shutdown (ship mode), unpowered.  Hand-over 1: gl_hal_init()")
    w(" * makes the pin an output AT THIS LEVEL (latch first, then the mode).  Hand-over")
    w(" * 0: the pin stays as the reset left it (an input, an analog pin, or an output")
    w(" * that rests analog: CHG_INHIBIT, the PWDN line on the BOOT0 pad).  No internal")
    w(" * pull may be enabled against one of these resistors.")
    w(" */")
    w("#define GL_PINS_RESET_TABLE(X) \\")
    for i, (name, level, handover) in enumerate(g["reset"]):
        w("    X(%-21s %d, %d)%s" % ("GL_PIN_" + name + ",", level, handover,
                                     " \\" if i + 1 < len(g["reset"]) else ""))
    w("")
    w("/*")
    w(" * LINES WITHOUT A BOARD PULL that float in reset and in the ROM bootloader")
    w(" * (firmware note %d).  X(logical pin).  gl_hal_init() gives each its level" %
      g["notes"]["floating"][0])
    w(" * BEFORE anything else it does with pins; the two MISO rows of the table carry")
    w(" * GL_PINPULL_DOWN (the lines float between transfers).")
    w(" */")
    w("#define GL_PINS_FLOATING_TABLE(X) \\")
    for i, name in enumerate(g["floating"]):
        w("    X(GL_PIN_%s)%s" % (name, " \\" if i + 1 < len(g["floating"]) else ""))
    w("")
    w("/* EXTCOMIN: LSE ticks per period (32768 / N Hz). */")
    w("#define GL_PINS_EXTCOMIN_LSE_TICKS %d" % g["ticks"])
    w("")
    w("/* The charger circuit as the pin map's notes state it (E1, BQ25101): CHG_INHIBIT")
    w(" * is a push-pull output, HIGH = stop (it turns on the MOSFET that pulls the")
    w(" * charger's TS input low), analog or low = charger on; CHG_STAT is the charger's")
    w(" * open-drain CHG output with the board's pull-up, low = charging. */")
    w("#define GL_PINS_CHG_INHIBIT_ACTIVE_HIGH 1")
    w("#define GL_PINS_CHG_STAT_LOW_IS_CHARGING 1")
    w("/* VBUS_SENSE reads the pad through a divider: removal is seen within this time,")
    w(" * while VDDUSB is gone within about a millisecond (firmware notes %d, %d). */" %
      (g["notes"]["usb_supply"][0], g["notes"]["vbus_sense"][0]))
    w("#define GL_PINS_VBUS_REMOVAL_SEEN_MS %d" % g["vbus_ms"])
    w("/* The USB core's own VBUS pad carries another signal: VBUS sensing off. */")
    w("#define GL_PINS_USB_VBUS_SENSING_OFF 1")
    w("/* The grain bias divider hangs on LCD_DISP: DISP high this long before a grain")
    w(" * measurement. */")
    w("#define GL_PINS_GRAIN_BIAS_DISP_MS %d" % g["grain_ms"])
    w("/* LSE drive: medium-low or higher. */")
    w("#define GL_PINS_LSE_DRIVE_MEDIUM_LOW 1")
    w("")
    w("/*")
    w(" * GRAIN LEDS as the netlist wires them.  X(index, reference, 1 = red / 0 = NIR,")
    w(" * azimuth in 0.1 degree, anode charlieplex line, cathode charlieplex line).")
    w(" * tests/test_pins.c compares it with the table of drivers/grain_frontend.c.")
    w(" */")
    w("#define GL_PINS_GRAIN_LED_TABLE(X) \\")
    for i, (ref, red, az10, an, ca) in enumerate(g["leds"]):
        w("    X(%2d, %-4s %d, %4d, %d, %d)%s" % (i, ref + ",", red, az10, an, ca,
                                                  " \\" if i + 1 < len(g["leds"]) else ""))
    w("")
    w("/*")
    w(" * FIRMWARE NOTES of the pin map, and where the firmware acts on each.  A note")
    w(" * that tools/gen_pins.py does not know stops the generation.")
    w(" *")
    where = {key: text for key, _rx, text in NOTE_RULES}
    ordered = sorted(g["notes"].items(), key=lambda kv: kv[1][0])
    for key, (idx, text, _m) in ordered:
        for line in wrap(text, 84, " * %2d. " % idx, " *     "):
            w(line)
        for line in wrap("-> " + where[key], 84, " *     ", " *        "):
            w(line)
    w(" */")
    w("#define GL_PINS_FIRMWARE_NOTES %d" % len(ordered))
    w("")
    w("#endif /* GL_PINS_H */")
    return "\n".join(out) + "\n"


# ---- self-test: defects seeded into a copy of the pin map ----------------------

def _row(doc, signal):
    return [r for r in doc["pins"] if r["signal"] == signal][0]


def _swap(doc, a, b):
    """Exchange the pads of two signals (pin, pad and what the pad brings)."""
    ra, rb = _row(doc, a), _row(doc, b)
    for key in ("port_pin", "pad", "bootloader", "wakeup", "adc"):
        ra[key], rb[key] = rb[key], ra[key]


def _move(doc, signal, pin):
    _row(doc, signal)["port_pin"] = pin


def _set(doc, signal, key, value):
    _row(doc, signal)[key] = value


def _note(doc, old, new):
    hit = [i for i, t in enumerate(doc["firmware_notes"]) if old in t]
    assert len(hit) == 1, old
    doc["firmware_notes"][hit[0]] = doc["firmware_notes"][hit[0]].replace(old, new)


# (what is seeded, words that must be in the refusal, the mutation)
SEEDED = [
    ("two signals on one pin", "share PC",
     lambda d: _move(d, "CAM_L_PWDN", _row(d, "CAM_L_SCL")["port_pin"])),
    ("two signals on one pad", "share pad",
     lambda d: _set(d, "NTC_BIAS", "pad", _row(d, "NTC_SENSE")["pad"])),
    ("two interrupt signals on one EXTI line", "share EXTI line",
     lambda d: _move(d, "IMU_INT2", "PE%d" % port_pin(_row(d, "IMU_INT1")["port_pin"])[1])),
    ("a PWDN line on a pin the ROM bootloader drives", "CAM_L_PWDN is on PA9, which the ROM bootloader drives",
     lambda d: _swap(d, "CAM_L_PWDN", "GRAIN_CP0")),
    ("CHG_INHIBIT on a ROM bootloader pin", "CHG_INHIBIT is on PB10, a ROM bootloader pin",
     lambda d: _swap(d, "CHG_INHIBIT", "LCD_SCS")),
    ("NTC_BIAS on a ROM bootloader pin", "NTC_BIAS is on PA10, a ROM bootloader pin",
     lambda d: _swap(d, "NTC_BIAS", "FLASH_CS")),
    ("NTC_SENSE on a ROM bootloader pin", "NTC_SENSE is on PA3, a ROM bootloader pin",
     lambda d: _swap(d, "NTC_SENSE", "OPAMP_VOUT")),
    ("the camera rail enable on a ROM bootloader pin", "CAM_PWR_EN is on PC10, a ROM bootloader pin",
     lambda d: _swap(d, "CAM_PWR_EN", "GRAIN_CP4")),
    ("a moved camera-facing line on a pin the ROM bootloader drives", "it would back-power the cameras",
     lambda d: _swap(d, "CAM_L_SCL", "GRAIN_CP4")),
    ("an LED line on a USB Type-C CC pad", "a UCPD CC pad may carry an input",
     lambda d: _swap(d, "CHG_STAT", "GRAIN_CP1")),
    ("a signal with a pull-up on the BOOT0 pad", "shares the BOOT0 pad but is not an output that rests low",
     lambda d: _swap(d, "CAM_R_PWDN", "FLASH_CS")),
    ("a signal missing from the pin map", "the pin map has no signal NTC_SENSE",
     lambda d: d["pins"].remove(_row(d, "NTC_SENSE"))),
    ("a signal the firmware does not know (the old CHG_PROG_EN)", "that hal/gl_hal.h does not know",
     lambda d: d["pins"].append(dict(_row(d, "NTC_BIAS"), signal="CHG_PROG_EN", port_pin="PE1", pad=99))),
    ("an alternate function without its number", "without an AF number",
     lambda d: _set(d, "SPI1_SCK", "af", None)),
    ("the cell-temperature input without an ADC channel", "NTC_SENSE has no ADC1 channel",
     lambda d: _set(d, "NTC_SENSE", "function", "GPIO")),
    ("VBUS_SENSE off its wake-up pin", "VBUS_SENSE is not on a PWR wake-up pin",
     lambda d: _set(d, "VBUS_SENSE", "function", "GPIO")),
    ("CHG_STAT as an output", "CHG_STAT must be an interrupt input",
     lambda d: _set(d, "CHG_STAT", "mode", "OUT_PP")),
    ("CHG_INHIBIT without its gate pull-down", "CHG_INHIBIT must be a push-pull output on a pulled-down gate",
     lambda d: _set(d, "CHG_INHIBIT", "pull", "none")),
    ("an internal pull-up on CHG_STAT", "CHG_STAT must be an input with the board's pull-up and no internal pull",
     lambda d: _set(d, "CHG_STAT", "pull", "reset state (pull-up) / 100k to V2V8")),
    ("a chip select whose resistor pulls it active", "its board resistor pulls the other way",
     lambda d: _set(d, "IMU_CS", "pull", "none / 100k to GND")),
    ("a resting state in words the generator does not know", "not understood",
     lambda d: _set(d, "LCD_DISP", "initial_state", "floating")),
    ("a pull in words the generator does not know", "not understood",
     lambda d: _set(d, "FLASH_CS", "pull", "none / something new")),
    ("a camera-facing line that is no longer parked while the rail is off", "disagree",
     lambda d: _set(d, "CAM_D3", "initial_state", "low")),
    ("a firmware note nobody has read", "not known to tools/gen_pins.py",
     lambda d: d["firmware_notes"].append("Drive PB11 high for 3 ms after every reset.")),
    ("a firmware note that has gone (the UCPD pads)", "no longer carries the firmware note 'ucpd'",
     lambda d: d["firmware_notes"].remove([t for t in d["firmware_notes"] if t.startswith("UCPD")][0])),
    ("an EXTI line in the notes that is not the row's", "says IMU_INT1 is EXTI9",
     lambda d: _note(d, "= EXTI7", "= EXTI9")),
    ("a line said to float that has a board pull", "floats in reset, its row has a board pull",
     lambda d: _note(d, "CAM_L_PWDN (PC2)", "IMU_CS (PB1)")),
    ("a grain LED on a line that is not a charlieplex line", "not a charlieplex line",
     lambda d: d["grain_leds"][3].update(anode_line="LCD_DISP")),
    ("fifteen grain LEDs", "lists 15 grain LEDs",
     lambda d: d["grain_leds"].pop()),
    ("EXTCOMIN above 60 Hz", "extcomin_lse_ticks 546",
     lambda d: d.update(extcomin_lse_ticks=546)),
    ("a pin map whose own proof failed", "verification did not pass",
     lambda d: d["verification"].update(checks_passed=False)),
]


def selftest(doc):
    try:
        build(copy.deepcopy(doc))
    except PinError as exc:
        print("gen_pins selftest: the UNCHANGED pin map is refused: %s" % exc)
        return 1
    missed = []
    for name, words, mutate in SEEDED:
        bad = copy.deepcopy(doc)
        mutate(bad)
        try:
            build(bad)
            missed.append("%s (accepted)" % name)
        except PinError as exc:
            # refused - and for the reason that was seeded, not by accident
            if words not in str(exc):
                missed.append("%s (refused, but not with %r: %s)" % (name, words, str(exc)[:100]))
    for name in missed:
        print("gen_pins selftest: NOT REFUSED AS SEEDED: %s" % name)
    print("gen_pins selftest: %d defects seeded into a copy of the pin map, %d refused" %
          (len(SEEDED), len(SEEDED) - len(missed)))
    return 1 if missed else 0


def main(argv):
    if "--selftest" in argv[1:]:
        rest = [a for a in argv[1:] if a != "--selftest"]
        if len(rest) != 1:
            raise SystemExit(__doc__)
        with open(rest[0], "rb") as fh:
            return selftest(json.loads(fh.read().decode("utf-8")))
    args = [a for a in argv[1:] if a != "--check"]
    check_only = "--check" in argv[1:]
    if len(args) != 2:
        raise SystemExit(__doc__)
    try:
        with open(args[0], "rb") as fh:
            raw = fh.read()
    except OSError as exc:
        raise SystemExit("gen_pins: cannot read the pin map %s: %s" % (args[0], exc))
    sha = hashlib.sha256(raw).hexdigest()
    try:
        doc = json.loads(raw.decode("utf-8"))
        # the name of the source as it appears in the header: from the
        # repository root, whatever directory the script was started in
        src_name = "electrical/gl1_main/pinmap.json" if args[0].replace("\\", "/").endswith(
            "electrical/gl1_main/pinmap.json") else args[0]
        text = generate(doc, src_name, sha)
    except PinError as exc:
        raise SystemExit("gen_pins: " + str(exc))
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit("gen_pins: the pin map does not have the expected form: %r" % (exc,))
    if check_only:
        try:
            with open(args[1], "r", encoding="utf-8") as fh:
                current = fh.read()
        except OSError:
            current = None
        if current != text:
            print("STALE: %s does not match %s (run `make pins`)" % (args[1], args[0]))
            return 1
        return 0
    with open(args[1], "w", encoding="utf-8") as fh:
        fh.write(text)
    print("wrote %s from %s (sha256 %s...)" % (args[1], args[0], sha[:12]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
