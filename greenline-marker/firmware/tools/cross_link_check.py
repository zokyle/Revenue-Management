#!/usr/bin/env python3
"""cross_link_check.py <toolchain-prefix> <out-dir> <object files...>

Part of `make cross`: the forbidden-symbol rule on a LINKED image, not only on
the objects.

The object check (tools/cross_report.sh) shows that no firmware object
references a double-precision helper, the heap or stdio.  The C library the
image is linked against can still bring such code in behind the firmware's
back: newlib's erff shares an object with erfcf, its error helpers with their
double-precision twins.  This script

  1. links the cross-compiled objects against the toolchain's libm and libc
     for the same CPU and float ABI - a PROBE, not a firmware image: no
     start-up code, no linker script, no HAL (every gl_hal_* symbol and the
     vendor HAL are left unresolved); nothing is run;
  2. disassembles the probe and builds the graph of direct calls and branches;
  3. takes EVERY function of the firmware objects as a starting point (so
     that functions reached only through pointers count) and lists what they
     can reach;
  4. FAILS if a double-precision helper, a double-precision libm function,
     the heap or stdio is reachable; and reports, without failing, the
     forbidden code that is merely PRESENT in the image (dead code the linker
     kept), with the library members that brought it in.

Calls through pointers inside the C library are not followed (there are none
on the paths from the single-precision functions the firmware uses; a
forbidden function that is only present is listed for that reason).
What this does not show: any other C library (newlib-nano, a vendor
toolchain), or anything about the HAL sources, which are not here.
"""
import os
import re
import subprocess
import sys

FORBIDDEN = re.compile(
    r"^(__aeabi_d[a-z0-9]*|__aeabi_f2d|__aeabi_i2d|__aeabi_ui2d|__aeabi_l2d|__aeabi_ul2d|__aeabi_d2f|"
    r"__aeabi_d2iz|__aeabi_d2uiz|__adddf3|__subdf3|__muldf3|__divdf3|__extendsfdf2|__truncdfsf2|"
    r"sqrt|sin|cos|tan|atan|atan2|asin|acos|exp|log|pow|floor|ceil|fabs|fmod|erf|erfc|round|"
    r"malloc|calloc|realloc|free|_malloc_r|_calloc_r|_realloc_r|_free_r|"
    r"printf|sprintf|snprintf|puts|fopen|fwrite|_printf_r|_vfprintf_r|_svfprintf_r)$"
)


def run(cmd):
    return subprocess.run(cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def main(argv):
    if len(argv) < 4:
        print(__doc__)
        return 2
    prefix, out_dir, objs = argv[1], argv[2], argv[3:]
    os.makedirs(out_dir, exist_ok=True)
    elf = os.path.join(out_dir, "link_probe.elf")
    mapf = os.path.join(out_dir, "link_probe.map")  # kept for inspection
    cmd = [prefix + "gcc", "-mcpu=cortex-m33", "-mthumb", "-mfpu=fpv5-sp-d16", "-mfloat-abi=hard", "-nostartfiles",
           "-Wl,-e,main,--gc-sections,--unresolved-symbols=ignore-all,-Map=" + mapf] + objs + ["-lm", "-lc", "-o", elf]
    r = run(cmd)
    if r.returncode != 0 or not os.path.exists(elf):
        print("  link probe SKIPPED: the toolchain could not link (no libm / libc for this CPU?)")
        for line in r.stderr.strip().splitlines()[:3]:
            print("    " + line)
        print("  The forbidden-symbol rule was checked on the objects only.")
        return 0
    # functions of the firmware objects
    fw = set()
    for line in run([prefix + "nm", "--defined-only"] + objs).stdout.splitlines():
        p = line.split()
        if len(p) == 3 and p[1] in ("T", "t"):
            fw.add(p[2])
    # direct call graph of the probe
    graph, cur = {}, None
    head = re.compile(r"^[0-9a-f]+ <([^>]+)>:$")
    ref = re.compile(r"<([A-Za-z_.$][A-Za-z0-9_.$]*)(?:\+0x[0-9a-f]+)?>")
    for line in run([prefix + "objdump", "-d", "--no-show-raw-insn", elf]).stdout.splitlines():
        m = head.match(line)
        if m:
            cur = m.group(1)
            graph.setdefault(cur, set())
            continue
        if cur is None or "\t" not in line:
            continue
        ins = line.split("\t", 2)
        if len(ins) < 2:
            continue
        mnem = ins[1].strip().split()[0] if ins[1].strip() else ""
        if not (mnem.startswith("b") or mnem.startswith("cb")):  # bl, b, b.w, bne, cbz ... (bx/blx reg: no target)
            continue
        for t in ref.findall(line):
            if t != cur:
                graph[cur].add(t)
    present = sorted(f for f in graph if FORBIDDEN.match(f))
    reach, todo = set(), [f for f in fw if f in graph]
    roots = len(todo)
    while todo:
        f = todo.pop()
        if f in reach:
            continue
        reach.add(f)
        todo.extend(t for t in graph.get(f, ()) if t not in reach)
    bad = sorted(f for f in reach if FORBIDDEN.match(f))
    lib_reached = sorted(f for f in reach if f not in fw)
    size = run([prefix + "size", "-B", elf]).stdout.splitlines()
    text = size[1].split()[0] if len(size) > 1 else "?"
    print(f"  probe linked (no start-up code, no HAL, never run): text {text} bytes; {len(graph)} functions, "
          f"{roots} of them the firmware's")
    print(f"  library functions the firmware's code can reach by direct calls ({len(lib_reached)}):")
    line = "   "
    for f in lib_reached:
        if len(line) + len(f) + 1 > 100:
            print(line)
            line = "   "
        line += " " + f
    if line.strip():
        print(line)
    if present:
        # who calls them: the library functions the linker kept that are not the firmware's
        callers = set()
        for f, targets in graph.items():
            if f not in reach and not FORBIDDEN.match(f) and any(t in present for t in targets):
                callers.add(f)
        dead = [f for f in present if f not in bad]
        print(f"  PRESENT in the image but NOT reachable from firmware code: {len(dead)} forbidden functions the "
              f"linker kept (dead code):")
        line = "   "
        for f in dead:
            if len(line) + len(f) + 1 > 100:
                print(line)
                line = "   "
            line += " " + f
        if line.strip():
            print(line)
        print("    called only from: " + (" ".join(sorted(callers)) if callers else "(each other)"))
    if bad:
        print("  FAIL: reachable from firmware code in the linked probe: " + " ".join(bad))
        return 1
    print("  OK: nothing double-precision, no heap and no stdio is reachable from firmware code in the linked probe")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
