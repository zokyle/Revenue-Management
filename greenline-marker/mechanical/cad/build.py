#!/usr/bin/env python3
"""Rebuild the whole GL-1 mechanical package and run the checks.

    python3 cad/build.py               # CAD -> STEP / STL / params, checks, drawings, renders; exit 1 on any failure
    python3 cad/build.py --no-export   # build + checks only, nothing written except the check report
    python3 cad/build.py --no-renders  # skip the headless-Chromium renders (they need node + playwright + three.js)
    python3 cad/build.py --no-drawings # skip the drawings
    python3 cad/build.py --summary     # also print the part table (bounding boxes, volumes)
    python3 cad/build.py --selftest    # negative tests: seed defects and confirm that the checks catch them

Rev D: the primary build has the routed FR-4 base plate; the parts of the alternative build (printed PA12 plate, its
adhesive sheet, seal joint and pottings) are built, exported and checked in the same run (check 16).

Outputs: export/step, export/stl/{parts,print}, export/params_resolved.json, export/part_table.json,
export/check_report.{json,md}, drawings/*.pdf|svg (+ dxf/, fab/, preview/), renders/*.png.
"""
from __future__ import annotations
import argparse, json, pathlib, shutil, subprocess, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import params as P
import assembly as A
import checks as C


def part_table(parts):
    rows = []
    for n, info in parts.items():
        s = A.solid_of(info); b = [round(v, 3) for v in A.bbox_of(info)]
        rows.append(dict(name=n, group=info.group, kind=info.kind, material=info.material, valid=s.isValid(),
                         volume_mm3=round(s.Volume(), 3), mass_g=round(s.Volume() * info.density / 1000, 4),
                         bbox_min=tuple(b[:3]), bbox_max=tuple(b[3:]),
                         size=tuple(round(b[i + 3] - b[i], 3) for i in range(3))))
    return rows


def previews():
    """PNG previews of every drawing sheet (pdftoppm), for the README and for checking legibility."""
    d = P.MECH_DIR / "drawings"
    out = d / "preview"
    out.mkdir(exist_ok=True)
    for f in out.glob("*.png"):
        f.unlink()
    if not shutil.which("pdftoppm"):
        print("  pdftoppm not found: no drawing previews")
        return []
    for pdf in sorted(d.glob("GL1-*.pdf")):
        subprocess.run(["pdftoppm", "-r", "80", "-png", str(pdf), str(out / pdf.stem)], check=True)
    return sorted(out.glob("*.png"))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-export", action="store_true")
    ap.add_argument("--no-renders", action="store_true")
    ap.add_argument("--no-drawings", action="store_true")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        import selftest
        return selftest.main()
    t = time.time()
    failures = []
    print(f"GL-1 mechanical build, params rev {P.REV}", flush=True)
    parts = A.build_parts()
    bad = [n for n, i in parts.items() if not A.solid_of(i).isValid()]
    n_alt = sum(1 for i in parts.values() if i.group == "alt")
    print(f"built {len(parts)} parts ({len(parts) - n_alt} primary build with the {P.BASE['key']} base plate, {n_alt} of the alternative {P.BASE_ALT} build) "
          f"in {time.time() - t:.1f} s; invalid solids: {bad or 'none'}", flush=True)
    if bad:
        failures.append(f"invalid solids: {bad}")
    if a.summary:
        for r in part_table(parts):
            print(f"  {r['name']:16s} {r['volume_mm3']:10.2f} mm3  {r['size']}  min {r['bbox_min']}")
    C.USE_EXPORTED = not a.no_export
    if not a.no_export:
        A.export_all(parts)
        (P.EXPORT_DIR / "part_table.json").write_text(json.dumps(part_table(parts), indent=1))
    results = C.run_all(parts)
    failures += [f"check {r['id']} {r['name']}" for r in results if not r["passed"]]
    if not a.no_export and not a.no_drawings:
        try:
            import drawings
            out = drawings.draw_all(parts, verbose=False)
            pv = previews()
            print(f"drawings: {len([o for o in out if o.endswith('.pdf')])} PDF, {len(list((P.MECH_DIR / 'drawings').glob('*.svg')))} SVG, "
                  f"{len([o for o in out if o.endswith('.dxf')])} DXF, {len([o for o in out if o.endswith(('.gbr', '.drl'))])} fabrication files (Gerber / Excellon), "
                  f"{len(pv)} previews", flush=True)
        except Exception as e:
            failures.append(f"drawings: {e!r}")
            print(f"drawings FAILED: {e!r}", flush=True)
    if not a.no_export and not a.no_renders:
        try:
            import renders
            out = renders.render_all(parts, verbose=False)
            print(f"renders: {len(out)} PNG", flush=True)
        except Exception as e:
            failures.append(f"renders: {e!r}")
            print(f"renders FAILED: {e!r}", flush=True)
    warn = sum(len(r["warnings"]) for r in results)
    if failures:
        print(f"BUILD FAILED ({time.time() - t:.1f} s): " + "; ".join(failures))
        return 1
    print(f"ALL CHECKS PASSED with {warn} warnings - read export/check_report.md ({time.time() - t:.1f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
