#!/usr/bin/python3
"""Core proof: build the unrouted mini board and let KiCad judge it.

    cd electrical/tools && /usr/bin/python3 tests/proof_core.py [out_dir]

Steps (each one must succeed, otherwise the script exits non-zero):

1. ERC-style checks on the mini design            -> 0 errors
2. build ``mini.kicad_pcb`` / ``mini.kicad_pro``   (library + custom footprints
   on both sides, cutout, notch, slot, NPTH holes, planes, keep-outs)
3. load the board back with pcbnew and compare every pad position with the
   pure-Python model
4. fill zones + KiCad DRC                          -> no geometry errors, only
   the unconnected items of an unrouted board
5. export top / bottom SVG (+ PNG) and verify from the top-view SVG that a
   feature placed at +y is drawn toward the top

Outputs are kept in ``tests/proof_out/`` by default.
"""
import json
import math
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from gleda import board, checks, drc, geometry, kicad_cli       # noqa: E402
from mini_design import mini_design                              # noqa: E402


def render_png(pcb, layers, png, half_size_mm=17.0, dpi=400):
    """PDF plot -> cropped PNG around the board centre (pdftoppm)."""
    pdf = os.path.splitext(png)[0] + ".pdf"
    kicad_cli.run_kicad_cli(["pcb", "export", "pdf", "--output", pdf, "--layers",
                             ",".join(layers), pcb])
    px = lambda mm: int(round(mm / 25.4 * dpi))
    ox, oy = 100.0, 100.0                          # gleda.coords.KICAD_ORIGIN_MM
    subprocess.run(["pdftoppm", "-png", "-r", str(dpi), "-x", str(px(ox - half_size_mm)),
                    "-y", str(px(oy - half_size_mm)), "-W", str(px(2 * half_size_mm)),
                    "-H", str(px(2 * half_size_mm)), "-singlefile", pdf,
                    os.path.splitext(png)[0]], check=True)
    os.remove(pdf)
    return png


def main(argv):
    out = os.path.abspath(argv[1] if len(argv) > 1 else os.path.join(HERE, "proof_out"))
    design = mini_design()

    report = checks.run_checks(design)
    print(report.text().strip())
    if not report.ok:
        return 1

    files = board.build_board(design, out)
    print("built", os.path.relpath(files.pcb, out), "and", os.path.relpath(files.pro, out))

    summary = board.board_summary(files.pcb)
    model = {}
    for pad in geometry.placed_pads(design):
        model.setdefault((pad.ref, pad.number), []).append(pad)
    worst, count = 0.0, 0
    for ref, fp in summary["footprints"].items():
        for pad in fp["pads"]:
            if (ref, pad["number"]) not in model:
                continue
            err = min(math.hypot(c.x - pad["x"], c.y - pad["y"])
                      for c in model[(ref, pad["number"])])
            worst, count = max(worst, err), count + 1
    print("pcbnew read-back: %d footprints, %d pads compared with the model, worst position "
          "error %.2e mm" % (len(summary["footprints"]), count, worst))
    if worst > 1e-6:
        return 1

    result = drc.run_drc(files.pcb, json_path=os.path.join(out, "mini.drc.json"))
    print(result.summary())
    try:
        drc.assert_clean(result, allow_unconnected=True)     # unrouted on purpose
    except drc.DrcError as exc:
        print(exc)
        return 1
    if result.unconnected_count == 0:
        print("unexpected: an unrouted board reported no unconnected items")
        return 1

    top = kicad_cli.export_svg(files.pcb, os.path.join(out, "mini_top.svg"),
                               ["F.Cu", "F.Fab", "F.SilkS", "Edge.Cuts"])
    kicad_cli.export_svg(files.pcb, os.path.join(out, "mini_bottom.svg"),
                         ["B.Cu", "B.Fab", "B.SilkS", "Edge.Cuts"], mirror=True)
    render_png(files.pcb, ["F.Cu", "F.Fab", "F.SilkS", "Edge.Cuts"],
               os.path.join(out, "mini_top.png"))
    render_png(files.pcb, ["B.Cu", "B.Fab", "B.SilkS", "Edge.Cuts"],
               os.path.join(out, "mini_bottom_xray.png"))

    # orientation: the round cutout sits at design (+8, 0), NPTH hole H2 at
    # (+11, +7.5).  In the SVG (y down) H2 must be ABOVE and right of the cutout.
    elements = kicad_cli.svg_elements(open(top).read())
    circles = sorted({tuple(round(v, 3) for v in d)       # drill marks repeat per layer
                      for _c, kind, d in elements if kind == "circle"})
    cut = [c for c in circles if abs(c[2] - 3.0) < 1e-3]
    h2 = [c for c in circles if abs(c[2] - 0.6) < 1e-3 and c[0] > cut[0][0]]
    if len(cut) != 1 or len(h2) != 1:
        print("orientation check: reference circles not found in SVG")
        return 1
    dx, dy = h2[0][0] - cut[0][0], cut[0][1] - h2[0][1]
    print("top-view SVG: H2 is %.3f mm right and %.3f mm ABOVE the cutout centre "
          "(design: 3.000 / 7.500)" % (dx, dy))
    if abs(dx - 3.0) > 0.01 or abs(dy - 7.5) > 0.01:
        print("orientation check FAILED")
        return 1

    with open(os.path.join(out, "mini.checks.json"), "w") as fh:
        json.dump(report.to_dict(), fh, indent=2, sort_keys=True)
        fh.write("\n")
    print("PROOF OK: 0 check errors, 0 DRC errors, %d unconnected (unrouted), +y is up"
          % result.unconnected_count)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
