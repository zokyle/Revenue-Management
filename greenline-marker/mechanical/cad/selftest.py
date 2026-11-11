#!/usr/bin/env python3
"""Negative tests for the checks: seed one defect at a time into a copy of the model and confirm that the
corresponding check FAILS.  A check that cannot fail proves nothing.

    python3 cad/build.py --selftest      (or: python3 cad/selftest.py)

Nothing is written to export/; meshes are tessellated in memory from the modified solids.
"""
from __future__ import annotations
import dataclasses, pathlib, sys, time
from collections import OrderedDict
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import cadquery as cq
import params as P
import parts as PT
import assembly as A
import checks as C


def _with(parts, **new):
    out = OrderedDict(parts)
    for n, shape in new.items():
        out[n] = dataclasses.replace(parts[n], shape=cq.Workplane("XY").newObject([shape]))
    return out


def _s(parts, n):
    return A.solid_of(parts[n])


def main():
    C.USE_EXPORTED = False
    t0 = time.time()
    parts = A.build_parts()
    cxr = P.CAM_XY["R"][0]
    tub, base, cradle = _s(parts, "tub"), _s(parts, "base_plate"), _s(parts, "cradle")
    bar = PT.box(cxr - 3, cxr + 3, P.WIN_RECESS_FLOOR_Y - 0.6, P.WIN_RECESS_FLOOR_Y - 0.2, P.AXIS_Z - 0.2, P.AXIS_Z + 0.2).val()
    groove = PT.box(-18.0, -16.0, -6.0, -4.0, P.ROOF_Z - 0.01, P.T - 0.3).val()
    void = PT.box(22.0, 26.0, -34.0, -30.0, -7.0, -3.0).val()
    channel = PT.cyl(24.0, -32.0, 0.5, -3.5, 5.0).val()
    lw = P.MECH["lip_half_w"]
    low_lip = PT.box(-lw, lw, P.LIP_Y0, P.NEST_FLAT, P.LIP_Z0 - 0.4, P.LIP_Z0 + 0.1).val()
    short_hook = PT.cyl(0, 0, P.HOOK_R + 0.6, P.HOOK_Z0 - 0.1, P.LATCH_TOP_Z + 0.1).val()
    rib = PT.box(-1.0, 1.0, -3.0, -1.0, 3.0, P.ROOF_Z + 0.1).val()
    cases = [
        ("prism R raised 0.30 mm into the roof", C.check_interference, _with(parts, prism_R=_s(parts, "prism_R").translate((0, 0, 0.30)))),
        ("LCD glass shifted 0.20 mm toward the cameras", C.check_clearances, _with(parts, lcd_glass=_s(parts, "lcd_glass").translate((0, 0.20, 0)))),
        ("battery raised 0.25 mm (eats the swell allowance)", C.check_clearances, _with(parts, battery=_s(parts, "battery").translate((0, 0, 0.25)))),
        ("0.4 mm bar across the camera R opening", C.check_fov, _with(parts, tub=tub.fuse(bar))),
        ("0.4 mm bar across the camera R opening", C.check_fold, _with(parts, tub=tub.fuse(bar))),
        ("2 x 2 mm pocket leaving a 0.30 mm roof", C.check_walls, _with(parts, tub=tub.cut(groove))),
        ("closed 4 mm void inside the cradle body", C.check_trapped, _with(parts, cradle=cradle.cut(void))),
        ("4 mm cavity in the cradle with only a dia 1.0 exit", C.check_trapped, _with(parts, cradle=cradle.cut(void).cut(channel))),
        ("lip 0.4 mm too low (no clearance over the tub)", C.check_cradle, _with(parts, cradle=cradle.fuse(low_lip))),
        ("latch hook cut back by 0.6 mm (overlap 0.3)", C.check_cradle, _with(parts, cradle=cradle.cut(short_hook))),
        ("2 mm rib from the roof down to z 3.0 over the PCB, outside the keep-outs", C.check_keepouts, _with(parts, tub=tub.fuse(rib))),
        ("support post A+ shortened by 0.5 mm", C.check_posts, _with(parts, tub=tub.cut(PT.box(14.0, 17.0, 0.5, 3.0, P.PCB_Z1 - 0.01, P.PCB_Z1 + 0.5).val()))),
    ]
    rows, ok = [], True
    for label, fn, mod in cases:
        t = time.time()
        r = fn(mod)
        caught = not r["passed"]
        ok &= caught
        rows.append(dict(defect=label, check=f"{r['id']} {r['name']}", caught=caught, message=r["summary"][:160]))
        print(f"[{'caught' if caught else 'MISSED'}] {label:52s} -> check {r['id']} {r['name']} ({time.time() - t:.1f} s)", flush=True)
    # and the unmodified model must pass the same checks
    for fn in (C.check_posts, C.check_keepouts):
        r = fn(parts)
        ok &= r["passed"]
    (P.EXPORT_DIR / "selftest_report.json").write_text(__import__("json").dumps(dict(all_defects_caught=ok, cases=rows), indent=1))
    print(f"{'SELFTEST PASSED: every seeded defect was caught' if ok else 'SELFTEST FAILED'} ({time.time() - t0:.1f} s)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
