#!/usr/bin/env python3
"""Rebuild the whole GL-1 mechanical package and run the checks.

    python3 cad/build.py               # CAD -> STEP / STL / params, checks, drawings, renders; exit 1 on any failure
    python3 cad/build.py --no-export   # build + checks only, nothing written except the check report
    python3 cad/build.py --no-renders  # skip the headless-Chromium renders (they need node + playwright + three.js)
    python3 cad/build.py --no-drawings # skip the drawings
    python3 cad/build.py --summary     # also print the part table (bounding boxes, volumes)
    python3 cad/build.py --selftest    # negative tests: seed defects and confirm that the checks catch them

Rev D: the primary build has the routed FR-4 base plate; the parts of the alternative build (printed PA12 plate, its
adhesive sheet, seal joint and pottings) are built, exported and checked in the same run (check 16).  Amended rev D: the
optional retarder film (E9), the two calibration seat plates (E11) and the ball gauge plate (check 18) are built and exported
too; after the drawings are written the fabrication files, the legend orientation, the PCB outline DXF and two die cuts are
read back from disk and compared with the model, and README.md is compared with the numbers of this build (readme_facts).

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


def readme_facts(parts, results):
    """Numbers of THIS build that README.md states in words: [(what, text that must occur in the README)].  The README is
    written by hand; this keeps its key numbers from going stale (white space is ignored in the comparison)."""
    import math
    import legend as L
    import fabdata as FD
    import deviations as DV
    M = P.MECH
    by = {r["id"]: r for r in results}
    row = lambda rid, title, key, val: next(q for t in by[rid]["tables"] if title in t["title"] for q in t["rows"] if str(q.get(key, "")).startswith(val))
    mass = by[8]["summary"].split("marker ")[1].split(" g")[0]
    guar = row(4, "Sensitivity", "case", "GUARANTEED CASE")
    mrow = [q for t in by[4]["tables"] if "uses up" in t["title"] for q in t["rows"]]
    slot_past = (P.LOC_SLOT[0] + P.LOC_SLOT[3] / 2) + P.LCD_POCKET_X          # inner end of the slot past the inner face of the foot of post B-
    cap = sum(L.capacity(b)[0] * L.capacity(b)[1] for b in L.blocks() if b["name"].startswith("statements"))
    ch = P.retarder_chain()
    n_step = len(parts)
    warn = sum(len(r["warnings"]) for r in results)
    facts = [
        ("number of checks and warnings", f"with {warn} warnings"),
        ("check 4, guaranteed case", f"**{guar['upper_field_full_pupil_deg']:.2f} deg in the guaranteed case"),
        ("check 4, both cameras", f"camera L {guar['upper_field_full_pupil_deg_camera_L']:.2f}, camera R {guar['upper_field_full_pupil_deg_camera_R']:.2f}"),
        ("check 4, PCB hole at its upper limit", f"{mrow[1]['upper_field_deg_closed_form']:.3f} deg"),
        ("check 4, pupil diameter", f"{mrow[2]['upper_field_deg_closed_form']:.2f}"),
        ("slot under post B- past the foot", f"{slot_past:.2f} mm past the cut-back foot"),
        ("marker mass", f"**{mass} g**"),
        ("parts exported", f"one STEP per part ({n_step}:"),
        ("legend capacity", f"hold {cap} characters"),
        ("legend letter spacing", f"{L.letter_gap(M['legend_min_text_h']):.2f} mm between letters"),
        ("legend strokes in the Gerber layer", f"{len(FD.parse_gerber(FD.gerber_legend())['segments'])} strokes"),
        ("retarder film", f"dia {P.RETARDER_D:g} x {P.RETARDER_T:.2f}"),
        ("retarder film chain", f"{ch['bore'][1]:.2f} to the tape bore"),
        ("gauge plate", f"three bosses dia {P.GAUGE['boss_od']:.1f}"),
        ("bridge gauge", f"annular feet dia {P.BRIDGE['foot_od']:.1f} / {P.BRIDGE['foot_bore']:.1f}"),
        ("baffle annulus tape", f"{min(P.BAFFLE_TAPE_RANGE):.2f} to {max(P.BAFFLE_TAPE_RANGE):g} mm as available"),
        ("deviations standing", "Standing deviations: " + ", ".join(d["id"] for d in DV.OPEN)),
        ("legend-free face", f"{next(int(n.split('keep-clear: ')[1].split(' mm2')[0]) for n in by[15]['notes'] if 'keep-clear: ' in n)} of 1257 mm2"),
        ("display rotation", f"**{max(q['value_deg'] for t in by[14]['tables'] if 'rotation' in t['title'] for q in t['rows'] if str(q['quantity']).startswith('free rotation')):.2f} deg**"),
    ]
    return facts


def check_readme(parts, results):
    """(problems, number of facts): every text of readme_facts() must occur in README.md."""
    f = P.MECH_DIR / "README.md"
    text = " ".join(f.read_text().split()) if f.exists() else ""
    facts = readme_facts(parts, results)
    return [f"{what}: README.md does not say '{snip}'" for what, snip in facts if " ".join(snip.split()) not in text], len(facts)


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
    n_opt = sum(1 for i in parts.values() if i.group == "option")
    n_fix = sum(1 for i in parts.values() if i.group == "fixture")
    print(f"built {len(parts)} parts ({len(parts) - n_alt - n_opt - n_fix} primary build with the {P.BASE['key']} base plate, {n_alt} of the alternative {P.BASE_ALT} build, "
          f"{n_opt} optional, {n_fix} fixtures) in {time.time() - t:.1f} s; invalid solids: {bad or 'none'}", flush=True)
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
            problems, facts = drawings.verify_outputs(parts)
            print("written files read back: " + "; ".join(facts), flush=True)
            if problems:
                failures.append("written files differ from the model: " + "; ".join(problems))
                print("written files FAILED: " + "; ".join(problems), flush=True)
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
    try:
        rp, n_facts = check_readme(parts, results)
        print(f"README.md against this build: {n_facts - len(rp)} of {n_facts} stated numbers agree", flush=True)
        if rp:
            failures.append("README.md is stale: " + "; ".join(rp))
            print("README FAILED: " + "; ".join(rp), flush=True)
    except Exception as e:
        failures.append(f"README comparison: {e!r}")
        print(f"README comparison FAILED: {e!r}", flush=True)
    if failures:
        print(f"BUILD FAILED ({time.time() - t:.1f} s): " + "; ".join(failures))
        return 1
    print(f"ALL CHECKS PASSED with {warn} warnings - read export/check_report.md ({time.time() - t:.1f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
