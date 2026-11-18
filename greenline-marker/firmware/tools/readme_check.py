#!/usr/bin/env python3
"""readme_check.py - the figures README.md quotes, against the runs.

    make readme-logs        runs the targets and keeps their output in build/readme/
    make readme-check       this script: compares; exit 1 on any difference
    python3 tools/readme_check.py --update     rewrites the generated blocks

Two mechanisms, both strict:

1. BLOCKS.  Text of the README between the two comment lines

       <!-- readme-check:begin NAME -->
       <!-- readme-check:end NAME -->

   is GENERATED here from the logs: a table built from them, or lines of a
   log quoted verbatim.  The check fails if a block is not, character for
   character, what the logs give now; `--update` writes it.  Nobody types a
   number into a block.

2. CHECKS.  Single figures in the README's prose: a regular expression that
   finds the figure in the README, and a function that takes the same figure
   from a log.  The check fails if the expression matches nowhere (the
   sentence was reworded: bind it again or drop the check) or if a match
   differs from the log.

What it does NOT do: it does not read the README for figures on its own.  A
number in the prose that no block holds and no check binds is not checked.
`--audit` lists the numbers of four or more digits outside the blocks that
occur in no log, as a help for finding stale ones; many of them are design
values or history and are meant to be there.

A block whose log is missing (cross-hal and boot-cross need the vendor's
header files) is reported as NOT CHECKED and does not fail the run; a
missing log of any other block does.
"""
import argparse
import os
import re
import sys

BEGIN = "<!-- readme-check:begin %s -->"
END = "<!-- readme-check:end %s -->"
OPTIONAL_LOGS = ("cross-hal", "boot-cross")


class Missing(Exception):
    pass


class Logs:
    def __init__(self, directory):
        self.dir = directory
        self.cache = {}

    def text(self, name):
        if name not in self.cache:
            path = os.path.join(self.dir, name + ".log")
            if not os.path.exists(path):
                raise Missing(name)
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                self.cache[name] = fh.read()
        return self.cache[name]

    def lines(self, name):
        return self.text(name).splitlines()

    def section(self, name, exe):
        """The output of one test executable in a `make test` / `make asan` log."""
        out, on = [], False
        for ln in self.lines(name):
            if ln.startswith("== "):
                on = ln.rstrip().endswith("/tests/" + exe)
                continue
            if on:
                out.append(ln)
        if not out:
            raise KeyError("no output of %s in %s.log" % (exe, name))
        return out

    def find(self, lines, pattern, count=1, required=True):
        """Lines matching `pattern` (a regular expression), exactly `count` of them (0 = any number)."""
        rx = re.compile(pattern)
        got = [ln for ln in lines if rx.search(ln)]
        if required and (len(got) == 0 or (count and len(got) != count)):
            raise KeyError("pattern %r: %d lines, expected %s" % (pattern, len(got), count or "some"))
        return got

    def span(self, lines, first, last):
        """Lines from the one matching `first` to the next one matching `last`, inclusive."""
        rf, rl = re.compile(first), re.compile(last)
        for i, ln in enumerate(lines):
            if rf.search(ln):
                for j in range(i, len(lines)):
                    if rl.search(lines[j]):
                        return lines[i:j + 1]
                raise KeyError("no line %r after %r" % (last, first))
        raise KeyError("no line %r" % first)


def code(lines, strip=4):
    """A fenced block of log lines, their common indentation removed."""
    lines = [ln.rstrip() for ln in lines]
    ind = min((len(ln) - len(ln.lstrip()) for ln in lines if ln.strip()), default=0)
    return "```\n" + "\n".join(ln[ind:] for ln in lines) + "\n```"


# --------------------------------------------------------------------------
# blocks
# --------------------------------------------------------------------------

def test_counts(logs, name):
    rows = []
    for ln in logs.lines(name):
        m = re.match(r"tests/(test_\w+)\.c: (\d+) tests, (\d+) checks, (\d+) failed checks -> (\w+)", ln)
        if m:
            rows.append((m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4)), m.group(5)))
    m = re.search(r"== build/\w+: (\d+) test executables, (\d+) failed", logs.text(name))
    if not m or not rows:
        raise KeyError("no test summary in %s.log" % name)
    return rows, int(m.group(1)), int(m.group(2))


def blk_test_summary(logs):
    rows, n, failed = test_counts(logs, "test")
    arows, an, afailed = test_counts(logs, "asan")
    asan = {r[0]: r for r in arows}
    out = ["| Test executable | tests | checks (`make test`) | failed | checks (`make asan`) | failed |", "|---|---|---|---|---|---|"]
    for r in rows:
        a = asan.get(r[0])
        out.append("| `tests/%s.c` | %d | %d | %d | %s | %s |" % (r[0], r[1], r[2], r[3], a[2] if a else "-", a[3] if a else "-"))
    out.append("| **%d executables** | **%d** | **%d** | **%d** | **%d** | **%d** |" %
               (n, sum(r[1] for r in rows), sum(r[2] for r in rows), sum(r[3] for r in rows),
                sum(r[2] for r in arows), sum(r[3] for r in arows)))
    out.append("")
    out.append("`make test`: \"%d test executables, %d failed\". `make asan`: \"%d test executables, %d failed\" "
               "(fewer checks: `test_read.c` runs 3 reads per scene there instead of 8)." % (n, failed, an, afailed))
    return "\n".join(out)


def size_table(logs):
    rows = []
    for ln in logs.lines("cross"):
        m = re.match(r"\s+(core|drivers|app|all)\s+(\S+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$", ln)
        if m:
            rows.append((m.group(1), m.group(2), int(m.group(3)), int(m.group(4)), int(m.group(5))))
    if not rows:
        raise KeyError("no size table in cross.log")
    return rows


def blk_flash_table(logs):
    rows = size_table(logs)
    out = ["| Group | Module | text | data | bss |", "|---|---|---|---|---|"]
    for group in ("core", "drivers", "app"):
        mods = sorted((r for r in rows if r[0] == group and r[1] != "(total)"), key=lambda r: -r[2])
        for r in mods:
            out.append("| %s | %s | %d | %d | %d |" % r)
        t = [r for r in rows if r[0] == group and r[1] == "(total)"][0]
        out.append("| %s | **total** | **%d** | **%d** | **%d** |" % (group, t[2], t[3], t[4]))
    t = [r for r in rows if r[0] == "all"][0]
    out.append("| all | **total** | **%d** | **%d** | **%d** |" % (t[2], t[3], t[4]))
    return "\n".join(out)


def ram_parts(logs):
    lines = logs.span(logs.lines("cross"), r"^== RAM: the application object", r"^== boot stub")
    parts = {}
    for ln in lines[1:-1]:
        m = re.match(r"\s+(\w+)\s+(\d+)\s*$", ln)
        if m:
            parts[m.group(1)] = int(m.group(2))
    if "app" not in parts:
        raise KeyError("no RAM table in cross.log")
    return parts


def blk_ram_table(logs):
    p = ram_parts(logs)
    rows = {r[1]: r for r in size_table(logs) if r[0] == "app"}
    main_bss = rows["gl_main"][4]
    if main_bss != p["app"]:
        raise KeyError("bss of gl_main (%d) is not sizeof(gl_app_t) (%d)" % (main_bss, p["app"]))
    read_rest = p["read"] - p["read_img"] - p["read_band_work"] - p["read_stick_work"]
    named = ["read", "gfx", "lcd", "proto", "meas_cur", "meas", "solve_meas", "solver_work", "store", "fac", "motion",
             "ui", "view", "est", "log"]
    rest = p["app"] - sum(p[k] for k in named)
    scratch = rows["gl_app"][4] + rows["gl_factory"][4] + rows["gl_usb"][4]
    total = rows["(total)"][4]
    if total != main_bss + scratch:
        raise KeyError("the bss of the application objects does not add up")
    out = ["| Object | Bytes | Note |", "|---|---|---|"]
    add = out.append
    add("| **`gl_app_t`** (bss of `gl_main`) | **%d** | the sum of the rows down to \"everything else\" |" % p["app"])
    add("| - camera pipeline `gl_read_t` | %d | the next four rows |" % p["read"])
    add("| - - strip buffers `img` | %d | FOUR 96 x 480 strips, one L R R L group; the 640 x 96 band uses the same memory |" % p["read_img"])
    add("| - - `gl_vis_band_work_t` | %d | band analysis |" % p["read_band_work"])
    add("| - - `gl_vis_stick_work_t` x 4 | %d | one per strip of a group (%d each) |" % (p["read_stick_work"], p["one_stick_work"]))
    add("| - - the rest of `gl_read_t` | %d | band result (%d), sequence state, accumulators, the result |" % (read_rest, p["read_band"]))
    add("| - LCD: `gl_gfx_t` + driver `gl_lcd_t` | %d + %d | frame buffer and clip table; the driver's shadow copy |" % (p["gfx"], p["lcd"]))
    add("| - `gl_proto_t` | %d | two frame buffers |" % p["proto"])
    add("| - solver inputs `gl_measurements_t` x 9 | %d | the read shown (%d), 4 stored Survey placements (%d), the up to 4 handed "
        "to the estimator (%d; phase 3: placements behind the ball are left out) |" %
        (p["meas_cur"] + p["meas"] + p["solve_meas"], p["meas_cur"], p["meas"], p["solve_meas"]))
    add("| - `gl_solver_work_t` | %d | work area of the patch fit and its record (`gl_patch_fit_t`, %d); the aim solve needs none |" %
        (p["solver_work"], p["patch_fit"]))
    add("| - `gl_store_t` | %d | settings and calibration blobs |" % p["store"])
    add("| - `gl_motion_t`, `gl_ui_t`, `gl_ui_view_t`, `gl_estimate_t`, `gl_factory_t`, `gl_log_t` | %d + %d + %d + %d + %d + %d | |" %
        (p["motion"], p["ui"], p["view"], p["est"], p["fac"], p["log"]))
    add("| - everything else | %d | drivers' state, calibration records, settings, survey, tilt, zeroing, recall, field-log "
        "bookkeeping, padding: `gl_app_t` less the rows above |" % rest)
    add("| static scratch in `gl_app.c` + `gl_factory.c` + `gl_usb.c` | %d + %d + %d = %d | one raw-strip log record, one "
        "field-log record being assembled; the factory's buffers; two raw grain measurements |" %
        (rows["gl_app"][4], rows["gl_factory"][4], rows["gl_usb"][4], scratch))
    add("| **all `.bss` of core, drivers and app** | **%d** | = `gl_app_t` + static scratch (the size table of `make cross`); "
        "core and drivers have none |" % total)
    return "\n".join(out)


def blk_stack_frames(logs):
    lines = logs.span(logs.lines("cross"), r"^== largest stack frames", r"^== forbidden symbol check")
    return code(lines[1:-1])


def blk_cross_checks(logs):
    ls = logs.lines("cross")
    pick = []
    pick += logs.find(ls, r"^  OK: no double-precision helpers")
    pick += logs.find(ls, r"^  OK: no fused instruction")
    pick += logs.find(ls, r"^  probe linked")
    pick += logs.find(ls, r"library functions the firmware's code can reach by direct calls")
    pick += logs.find(ls, r"PRESENT in the image but NOT reachable", required=False, count=0)
    pick += logs.find(ls, r"^  OK: nothing double-precision, no heap and no stdio is reachable")
    pick += logs.find(ls, r"^  OK: boot/gl_boot_logic.c references no external symbol")
    return code(pick)


def blk_appdiff(logs):
    ls = logs.lines("appdiff")
    return code(logs.span(ls, r"^scene ", r"^largest \|C double"))


def blk_bench_vision(logs):
    ls = logs.lines("bench-vision")
    return code(logs.span(ls, r"^one read of each scene", r"^  none "))


def blk_steep_sweep(logs):
    ls = logs.lines("steep-sweep")
    return code(logs.span(ls, r"^random Quick Reads", r"^GL_UI_STEEP_RATIO"))


def blk_rail_bound(logs):
    sec = logs.section("test", "test_read")
    return code(logs.span(sec, r"reads per scene; rail = camera rail on", r"cost, over the \d+ scenes"))


def blk_vision_grid(logs):
    sec = logs.section("test", "test_read")
    lines = logs.span(sec, r"flat green, 15 mm stick", r"\[ ok \] test_grid_width_contrast")
    return code(lines[:-1])


def blk_vision_scenes(logs):
    sec = logs.section("test", "test_read")
    rail = logs.span(sec, r"reads per scene; rail = camera rail on", r"test_rail_time_is_bounded_with_several_lines")
    upto = logs.span(sec, r"^\s+case\s+N ste lft", r"stick-free reads: \d+ reported a flagstick")
    keep = [ln for ln in upto if ln not in rail]
    return code(keep)


def blk_quick_read(logs):
    e2 = logs.section("test", "test_e2e")
    pick = logs.span(e2, r"^\s+states: SLEEP@", r"result shown: MCU in Stop mode")
    pick += logs.span(e2, r"Quick Read, flagstick at 6 m \(", r"read cycles per charge")
    return code(pick)


def out_of(exe):
    def gen(logs):
        return code(logs.section("test", exe))
    return gen


def blk_recall(logs):
    sec = logs.section("test", "test_e2e_recall")
    pick = logs.find(sec, r"result back on the screen")
    pick += logs.find(sec, r"age shown:")
    pick += logs.span(sec, r"what happens to the sleeping marker", r"lifted for 4 s, back")
    pick += logs.find(sec, r"twisted 10 degrees in 0.4 s")
    pick += logs.find(sec, r"Precision spin begun and given up")
    pick += logs.find(sec, r"Precision result recalled after a tap")
    pick += logs.find(sec, r"tapped 23 h 50 min after the result")
    pick += logs.find(sec, r"tapped 25 h after the result")
    return code(pick)


def blk_display_states(logs):
    ui = logs.section("test", "test_ui")
    so = logs.section("test", "test_solver")
    pick = logs.find(ui, r"NORMAL, \d+ APPROX and \d+ NONE result screens")
    pick += logs.find(ui, r"ink in the gaps of the dash pattern")
    pick += logs.span(ui, r"combinations of aim source", r"^\s+source 3:")
    pick += logs.find(ui, r"TOO STEEP from 0\.\d+ of the critical slope")
    pick += logs.span(so, r"cases whose \(aim source, solve status\) differs", r"against the double build at the reference's own tolerances")
    return code(pick)


def blk_display_mapping(logs):
    pu = logs.section("test", "test_e2e_putt")
    pick = logs.find(pu, r"^\s+Mapping only:", count=0)
    pick += logs.find(pu, r"shown as \"TOO STEEP\" without a line")
    pick += logs.find(pu, r"shown dashed, APPROX, \"TOO STEEP\"")
    pick += logs.find(pu, r"aim line: dashed on \d+ rows with 5 m dialled")
    return code(pick)


def blk_survey(logs):
    pu = logs.section("test", "test_e2e_putt")
    e2 = logs.section("test", "test_e2e")
    pick = logs.find(pu, r"the 3 placements of the E29 example handed to the estimator")
    pick += logs.find(pu, r"old order \(9 m ball first")
    pick += logs.find(e2, r"result at the second placement \(3 m; the first, 6 m, lies behind it")
    pick += logs.find(e2, r"the base of the stick at the ball \(3 m\) was classed")
    return code(pick)


def blk_info_screen(logs):
    ui = logs.section("test", "test_ui")
    rc = logs.section("test", "test_e2e_recall")
    pick = logs.find(ui, r"regulatory text: 10 lines")
    pick += logs.find(ui, r"four statements of 88 characters")
    pick += logs.find(rc, r"INFO screen: ")
    pick += logs.find(ui, r"sizeof\(gl_ui_t\)")
    return code(pick)


def blk_tooltest(logs):
    ls = logs.lines("tooltest")
    pick = logs.find(ls, r"release-gate: REFUSED", count=0)
    pick += logs.find(ls, r"reads replayed through the Python reference", count=0, required=False)
    pick += logs.find(ls, r"== glctl selftest: \d+ checks", count=0)
    return code(pick)


def blk_replay_demo(logs):
    ls = logs.lines("replay-demo")
    return code(logs.span(ls, r"^read\s+kind\s+source", r"reads replayed through the Python reference"))


def blk_diff(logs):
    ls = logs.lines("diff")
    pick = logs.find(ls, r"^(estimator_cases|solver_cases|fallback_estimator_cases|fallback_solver_cases|near_miss_estimator_cases|roll_cases)", count=0)
    pick += logs.find(ls, r"RESULT:", count=0)
    pick += logs.find(logs.section("test", "test_solver"), r"^\s+double, roll_cases: \d+ rolls")
    return code(pick)


def blk_cross_hal(logs):
    ls = logs.lines("cross-hal")
    pick = logs.span(ls, r"^\s+text\s+data\s+bss", r"gl_hal_stm32u5\.o")
    pick += logs.find(ls, r"OK: no double-precision helpers")
    return code(pick)


def blk_boot_cross(logs):
    ls = logs.lines("boot-cross")
    pick = logs.find(ls, r"^\s*\d+\s.*build/boot/gl_boot\.elf")
    pick += logs.find(ls, r"image: \d+ bytes of 8192")
    pick += logs.find(ls, r"largest stack frame of the stub")
    pick += logs.find(ls, r"OK: the boot stub links without any library")
    return code(pick)


BLOCKS = [
    ("test-summary", ("test", "asan"), blk_test_summary),
    ("flash-table", ("cross",), blk_flash_table),
    ("ram-table", ("cross",), blk_ram_table),
    ("stack-frames", ("cross",), blk_stack_frames),
    ("cross-checks", ("cross",), blk_cross_checks),
    ("cross-hal", ("cross-hal",), blk_cross_hal),
    ("boot-cross", ("boot-cross",), blk_boot_cross),
    ("quick-read", ("test",), blk_quick_read),
    ("out-e2e", ("test",), out_of("test_e2e")),
    ("out-e2e-faults", ("test",), out_of("test_e2e_faults")),
    ("out-e2e-power", ("test",), out_of("test_e2e_power")),
    ("out-e2e-review", ("test",), out_of("test_e2e_review")),
    ("appdiff", ("appdiff",), blk_appdiff),
    ("bench-vision", ("bench-vision",), blk_bench_vision),
    ("steep-sweep", ("steep-sweep",), blk_steep_sweep),
    ("rail-bound", ("test",), blk_rail_bound),
    ("vision-grid", ("test",), blk_vision_grid),
    ("vision-scenes", ("test",), blk_vision_scenes),
    ("recall", ("test",), blk_recall),
    ("display-states", ("test",), blk_display_states),
    ("display-mapping", ("test",), blk_display_mapping),
    ("survey", ("test",), blk_survey),
    ("info-screen", ("test",), blk_info_screen),
    ("tooltest", ("tooltest",), blk_tooltest),
    ("replay-demo", ("replay-demo",), blk_replay_demo),
    ("diff", ("diff",), blk_diff),
]


# --------------------------------------------------------------------------
# checks: single figures in the prose
# --------------------------------------------------------------------------

def _total(logs, col):
    t = [r for r in size_table(logs) if r[0] == "all"][0]
    return str(t[col])


def _probe(logs, which):
    m = re.search(r"probe linked .*: text (\d+) bytes; (\d+) functions, (\d+) of them the firmware's", logs.text("cross"))
    if not m:
        raise KeyError("no link probe line in cross.log")
    return m.group(which)


def _probe_reach(logs):
    m = re.search(r"library functions the firmware's code can reach by direct calls \((\d+)\)", logs.text("cross"))
    return m.group(1)


def _frame(logs, func):
    for ln in logs.span(logs.lines("cross"), r"^== largest stack frames", r"^== forbidden symbol check"):
        m = re.match(r"\s+(\d+)\s+(\S+)\s", ln)
        if m and m.group(2) == func:
            return m.group(1)
    raise KeyError("no stack frame of %s among the largest in cross.log" % func)


def _tests(logs, exe, which):
    rows, _, _ = test_counts(logs, "test")
    r = [x for x in rows if x[0] == exe][0]
    return str(r[which])


def _n_exe(logs, name="test"):
    return str(test_counts(logs, name)[1])


def _bench(logs, scene, what):
    m = re.search(r"^\s+%s\s+trace points: band \d+, strip (\d+), group (\d+) .* total ([\d.]+) M instructions \| rail on (\d+) ms" %
                  re.escape(scene), logs.text("bench-vision"), re.M)
    if not m:
        raise KeyError("no bench-vision line for %s" % scene)
    return m.group({"strips": 1, "groups": 2, "total": 3, "rail": 4}[what])


def _appdiff(logs, which):
    m = re.search(r"(\d+) estimator calls of the application: (\d+) agree with the Python reference, (\d+) do not", logs.text("appdiff"))
    m2 = re.search(r"largest \|firmware - reference\|: ([\d.]+) mrad; largest \|drawn - reference\|: ([\d.]+) mrad \(([\d.]+) deg\)",
                   logs.text("appdiff"))
    return {"n": m.group(1), "agree": m.group(2), "fw": m2.group(1), "drawn": m2.group(2), "drawn_deg": m2.group(3)}[which]


def _rail(logs, which):
    sec = logs.section("test", "test_read")
    m = re.search(r"longest rail time: (\d+) ms with the bound \(limit 2800\), (\d+) ms without it", "\n".join(sec))
    m2 = re.search(r"disparity rms ([\d.]+) px with the bound, ([\d.]+) px without; range rms ([\d.]+) % against ([\d.]+) %", "\n".join(sec))
    return {"on": m.group(1), "off": m.group(2), "d_on": m2.group(1), "d_off": m2.group(2), "r_on": m2.group(3), "r_off": m2.group(4)}[which]


def _lrrl(logs):
    m = re.search(r"L R R L completion intervals with a 9 ms sensor phase offset: (\d+) (\d+) (\d+) \|", logs.text("test"))
    return "%s / %s / %s" % m.groups()


def _grey(logs):
    return re.search(r"strips of (2 to \d) grey levels", logs.text("test")).group(1)


def _stickfree(logs):
    m = re.search(r"stick-free reads: 0 reported a flagstick .* mean camera-rail time (\d+) ms", logs.text("test"))
    return "%.2f" % (int(m.group(1)) / 1000.0)


def _su(logs, func):
    """A frame from the .su files of the cross build the logs were made with."""
    root = os.path.join(os.path.dirname(os.path.abspath(logs.dir)), "cross")
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            if fn.endswith(".su"):
                for ln in open(os.path.join(dirpath, fn)):
                    parts = ln.split("\t")
                    name = parts[0].split(":")[-1]
                    if name == func or name.startswith(func + "."):
                        return int(parts[1])
    raise KeyError("no frame of %s in %s" % (func, root))


def _chain(logs):
    # run_once -> actions -> estimate (Survey entry) -> estimate -> aim solve on the patch -> kernel
    # -> pace solve -> trial -> roll -> acceleration
    names = ["gl_app_run_once", "do_actions_", "gl_solver_estimate_survey", "estimate_", "solve_patch_",
             "gls_solve_kernel", "solve_pace_", "trial_", "gls_roll", "accel_"]
    return str(sum(_su(logs, n) for n in names))


def _qr(logs, row, col):
    """A cell of the timing table of test_quick_read_time_and_charge_with_computation."""
    for ln in logs.section("test", "test_e2e"):
        if ln.strip().startswith(row):
            cells = [c.split() for c in ln.split("|")[1:]]
            return cells[col[0]][col[1]]
    raise KeyError("no row %r in the Quick Read timing table" % row)


def _qr_first(logs):
    m = re.search(r"result on the screen at [\d.]+ s \(([\d.]+) s after coming to rest\); camera part ([\d.]+) s", logs.text("test"))
    return m.group(1)


def _cycles(logs):
    m = re.search(r"nothing else drawing: (\d+) / (\d+) / (\d+) read cycles per charge", logs.text("test"))
    return "%s / %s / %s" % m.groups()


def _selftest(logs):
    return re.findall(r"== glctl selftest: (\d+) checks, 0 failed", logs.text("tooltest"))[-1]


# (what it is, regular expression over the README with ONE group, how to get the value from the logs)
CHECKS = [
    ("number of test executables (make test)", r"runs all (\d+) test executables", lambda L: _n_exe(L)),
    ("number of test executables (status)", r"`make test` \((\d+) test executables\)", lambda L: _n_exe(L)),
    ("firmware text, bytes", r"firmware's own code is (\d+) bytes of the 2 MB flash", lambda L: _total(L, 2)),
    ("firmware bss, bytes", r"and (\d+) bytes of `\.bss`, of which", lambda L: _total(L, 4)),
    ("sizeof(gl_app_t)", r"`gl_app_t` is (\d+) bytes", lambda L: str(ram_parts(L)["app"])),
    ("link probe text", r"probe text (\d+) bytes", lambda L: _probe(L, 1)),
    ("link probe functions", r"bytes, (\d+) functions of which", lambda L: _probe(L, 2)),
    ("link probe firmware functions", r"functions of which (\d+) are the firmware's", lambda L: _probe(L, 3)),
    ("link probe reachable library functions", r"the firmware reaches (\d+) library", lambda L: _probe_reach(L)),
    ("stack frame gl_vis_band_analyse", r"`gl_vis_band_analyse` (\d+),", lambda L: _frame(L, "gl_vis_band_analyse")),
    ("stack frame gls_fit_patch", r"`gls_fit_patch` (\d+),", lambda L: _frame(L, "gls_fit_patch")),
    ("stack frame gl_app_run_once", r"`gl_app_run_once` (\d+),", lambda L: _frame(L, "gl_app_run_once")),
    ("stack frame gls_roll", r"`gls_roll` (\d+),", lambda L: _frame(L, "gls_roll")),
    ("rail time, nominal scene A (bench-vision)", r"nominal read \(scene A\): rail on (\d+) ms", lambda L: _bench(L, "A", "rail")),
    ("rail time, person scene (bench-vision)", r"person behind the stick: (\d+) ms of camera rail", lambda L: _bench(L, "person", "rail")),
    ("strips, person scene (bench-vision)", r"three lines probed; phase 3: 3 \+ 5 groups\) \| (\d+) \(", lambda L: _bench(L, "person", "strips")),
    ("cost table total, person scene (bench-vision)", r"with 32\) \| (\d+\.\d+); 2\.56 s", lambda L: _bench(L, "person", "total")),
    ("L R R L completion intervals", r"sensors free-run \((\d+ / \d+ / \d+) ms with a 9 ms phase offset in the first group", lambda L: _lrrl(L)),
    ("grey levels of the coarse-search strips", r"strips of only (2 to \d) grey levels", lambda L: _grey(L)),
    ("stick-free reads: mean camera-rail time", r"\*\*Mean camera-rail time (\d\.\d\d) s\*\*", lambda L: _stickfree(L)),
    ("deepest stack chain", r"over the deepest chain \((\d+) bytes", lambda L: _chain(L)),
    ("longest rail time with the bound (test_read)", r"longest read keeps the rail on for (\d+) ms with the bound", lambda L: _rail(L, "on")),
    ("longest rail time without the bound (test_read)", r"and for (\d+) ms without it", lambda L: _rail(L, "off")),
    ("cost of the bound: disparity rms with", r"disparity error rms (\d\.\d+) px with the bound", lambda L: _rail(L, "d_on")),
    ("cost of the bound: disparity rms without", r"against (\d\.\d+) px without it", lambda L: _rail(L, "d_off")),
    ("cost of the bound: range rms with", r"range error rms (\d\.\d+) % with the bound", lambda L: _rail(L, "r_on")),
    ("cost of the bound: range rms without", r"against (\d\.\d+) % without", lambda L: _rail(L, "r_off")),
    ("appdiff: estimator calls", r"(\d+) estimator calls of the application agree", lambda L: _appdiff(L, "n")),
    ("appdiff: largest firmware - reference", r"largest \|firmware - reference\| of a solved aim (\d\.\d+) mrad", lambda L: _appdiff(L, "fw")),
    ("appdiff: largest drawn - reference", r"Largest \|drawn - reference\| of a line on the screen: \*\*(\d\.\d+) mrad", lambda L: _appdiff(L, "drawn")),
    ("Quick Read: rest to result, low / nominal / high", r"result comes (\d\.\d\d) s \(low factor\)", lambda L: _qr(L, "low: 1.5", (0, 0))),
    ("Quick Read: rest to result, nominal", r"\(low factor\), (\d\.\d\d) s \(nominal\)", lambda L: _qr(L, "nominal: 2.0", (0, 0))),
    ("Quick Read: rest to result, high", r"\(nominal\) and (\d\.\d\d) s \(high\)", lambda L: _qr(L, "high: 3.0", (0, 0))),
    ("Quick Read: rest to result, PLL not locked", r"(\d\.\d\d) s if the PLL does not lock; the camera rail", lambda L: _qr(L, "nominal, PLL does not lock", (0, 0))),
    ("Quick Read: on the screen after rest (first test)", r"\*\*(\d\.\d\d) s after the marker came to rest\*\*", lambda L: _qr_first(L)),
    ("Quick Read: charge of a read", r"wake-up to result, is (\d+\.\d) mAs over about 5 s", lambda L: _qr(L, "nominal: 2.0", (2, 0))),
    ("read cycles per charge", r"low, nominal and high factor \((\d+ / \d+ / \d+);", lambda L: _cycles(L)),
    ("appdiff: largest drawn - reference (Solver section)", r"drawn line is within (\d\.\d+) mrad of the reference", lambda L: _appdiff(L, "drawn")),
    ("glctl selftest checks", r"`make tooltest`: every command, (\d+) checks", lambda L: _selftest(L)),
    ("test_ui.c checks", r"`tests/test_ui\.c` \((\d+) checks[:)]", lambda L: _tests(L, "test_ui", 2)),
    ("test_e2e_recall.c checks", r"`tests/test_e2e_recall\.c` \((\d+) checks[:)]", lambda L: _tests(L, "test_e2e_recall", 2)),
]


# --------------------------------------------------------------------------

def split_blocks(text):
    """{name: (start of content, end of content)} for every block of the README."""
    found = {}
    for m in re.finditer(r"<!-- readme-check:begin ([\w-]+) -->\n", text):
        name = m.group(1)
        end = text.find(END % name, m.end())
        if end < 0:
            raise SystemExit("README: block %s has no end line" % name)
        if name in found:
            raise SystemExit("README: block %s occurs twice" % name)
        found[name] = (m.end(), end)
    return found


def audit(text, logs):
    blocks = split_blocks(text)
    outside = text
    for name in sorted(blocks, key=lambda n: -blocks[n][0]):
        a, b = blocks[name]
        outside = outside[:a] + outside[b:]
    every = ""
    for fn in sorted(os.listdir(logs.dir)):
        if fn.endswith(".log"):
            every += logs.text(fn[:-4])
    every_plain = every.replace(",", "")
    seen, missing = set(), []
    for i, line in enumerate(outside.splitlines(), 1):
        for tok in re.findall(r"(?<![\w.])\d[\d,]*\.?\d*(?![\w])", line):
            plain = tok.replace(",", "").rstrip(".")
            digits = plain.replace(".", "")
            if len(digits) < 4 or plain in seen:
                continue
            seen.add(plain)
            if plain not in every_plain:
                missing.append((i, tok, line.strip()[:110]))
    print("audit: %d different numbers of four or more digits outside the blocks; %d of them occur in no log:" % (len(seen), len(missing)))
    for i, tok, ctx in missing:
        print("  line %5d (blocks removed)  %-12s %s" % (i, tok, ctx))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--logs", default="build/readme")
    ap.add_argument("--readme", default="README.md")
    ap.add_argument("--update", action="store_true", help="rewrite the generated blocks from the logs")
    ap.add_argument("--audit", action="store_true", help="list numbers outside the blocks that occur in no log")
    args = ap.parse_args()
    logs = Logs(args.logs)
    text = open(args.readme, "r", encoding="utf-8").read()
    if args.audit:
        audit(text, logs)
        return 0
    present = split_blocks(text)
    known = [b[0] for b in BLOCKS]
    bad = 0
    for name in present:
        if name not in known:
            print("FAIL  block %-16s is in the README but this script does not generate it" % name)
            bad += 1
    n_ok = n_skip = 0
    new_text = text
    for name, needs, fn in BLOCKS:
        if name not in present:
            print("FAIL  block %-16s is not in the README" % name)
            bad += 1
            continue
        try:
            want = fn(logs) + "\n"
        except Missing as e:
            if str(e) in OPTIONAL_LOGS:
                print("NOT CHECKED  block %-16s (no %s.log: the vendor's header files were not given)" % (name, e))
                n_skip += 1
                continue
            print("FAIL  block %-16s: %s.log is missing (run `make readme-logs`)" % (name, e))
            bad += 1
            continue
        except KeyError as e:
            print("FAIL  block %-16s: %s" % (name, e.args[0]))
            bad += 1
            continue
        a, b = split_blocks(new_text)[name]
        have = new_text[a:b]
        if have == want:
            n_ok += 1
        elif args.update:
            new_text = new_text[:a] + want + new_text[b:]
            print("updated  block %s" % name)
            n_ok += 1
        else:
            hl, wl = have.splitlines(), want.splitlines()
            k = 0
            while k < min(len(hl), len(wl)) and hl[k] == wl[k]:
                k += 1
            print("FAIL  block %-16s differs from the logs at its line %d:" % (name, k + 1))
            print("        README: %s" % (hl[k][:150] if k < len(hl) else "(ends)"))
            print("        logs:   %s" % (wl[k][:150] if k < len(wl) else "(ends)"))
            bad += 1
    n_fig = 0
    flat = re.sub(r"\s+", " ", new_text)  # (a sentence may be wrapped anywhere)
    for what, pattern, fn in CHECKS:
        got = re.findall(pattern, flat)
        if not got:
            print("FAIL  figure %-48s: its sentence is not in the README (%s)" % (what, pattern))
            bad += 1
            continue
        try:
            want = fn(logs)
        except (KeyError, IndexError, AttributeError, Missing) as e:
            print("FAIL  figure %-48s: not found in the logs (%s)" % (what, e))
            bad += 1
            continue
        for g in got:
            if g.replace(",", "") != want:
                print("FAIL  figure %-48s: README %s, logs %s" % (what, g, want))
                bad += 1
            else:
                n_fig += 1
    if args.update and new_text != text:
        open(args.readme, "w", encoding="utf-8").write(new_text)
    stamp = os.path.join(args.logs, "stamp.txt")
    when = open(stamp).read().strip() if os.path.exists(stamp) else "no stamp.txt: the logs may be of different runs"
    print("readme-check: %d generated blocks equal to the logs, %d not checked, %d single figures equal to the logs; "
          "%d failures (%s)" % (n_ok, n_skip, n_fig, bad, when))
    if bad:
        print("readme-check: FAIL")
        return 1
    print("readme-check: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
