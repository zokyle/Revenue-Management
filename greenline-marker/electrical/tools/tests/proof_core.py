#!/usr/bin/python3
"""Core proof: build two unrouted reference boards and let KiCad judge them.

    cd electrical/tools && /usr/bin/python3 tests/proof_core.py [out_dir]

Boards

* ``mini``    round 30 mm board: castellated module, cutout, edge notch, slot,
              NPTH holes, parts on both sides (``tests/mini_design.py``)
* ``dshape``  GreenLine-shaped board: circle clipped by a chord, LQFP-64, two
              0.5 mm-pitch BGAs on a shared bus, fine net class, bottom-side
              LED ring and bare contact pad row, per-layer keep-outs under the
              sensors, vias tented on the bottom (``tests/dshape_design.py``)

Steps for each board (every one must succeed, otherwise the exit code is 1):

1. ERC-style checks                                -> 0 errors
2. build ``<name>.kicad_pcb`` / ``.kicad_pro`` / ``.kicad_dru`` + footprint library
3. load the board back with pcbnew and compare every pad position, net and
   copper layer with the pure-Python model
4. fill zones + KiCad DRC                          -> no geometry errors, only
   the unconnected items of an unrouted board
5. export top / bottom SVG (+ PNG) and verify from the plotted top-side copper
   that +x is right and +y is UP, and from the bottom-side plots that the
   bottom view is mirrored left-right only

Outputs are kept in ``tests/proof_out/<name>/`` by default.
"""
import json
import math
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from gleda import board, checks, coords, drc, geometry, kicad_cli   # noqa: E402
from mini_design import mini_design                                  # noqa: E402
from dshape_design import dshape_design                              # noqa: E402

TOP_LAYERS = ["F.Cu", "F.Fab", "F.SilkS", "Edge.Cuts"]
BOTTOM_LAYERS = ["B.Cu", "B.Fab", "B.SilkS", "Edge.Cuts"]


def render_png(pcb, layers, png, bounds, margin=1.5, dpi=400):
    """PDF plot -> PNG cropped to the board (pdftoppm).  The view is from the
    top of the board, like the KiCad canvas."""
    pdf = os.path.splitext(png)[0] + ".pdf"
    kicad_cli.run_kicad_cli(["pcb", "export", "pdf", "--output", pdf, "--layers",
                             ",".join(layers), pcb])
    x0, y1 = coords.to_kicad_mm(bounds[0] - margin, bounds[1] - margin)   # page mm, y down
    x1, y0 = coords.to_kicad_mm(bounds[2] + margin, bounds[3] + margin)
    px = lambda mm: int(round(mm / 25.4 * dpi))
    subprocess.run(["pdftoppm", "-png", "-r", str(dpi), "-x", str(px(x0)), "-y", str(px(y0)),
                    "-W", str(px(x1 - x0)), "-H", str(px(y1 - y0)), "-singlefile", pdf,
                    os.path.splitext(png)[0]], check=True)
    os.remove(pdf)
    return png


def copper_bbox_from_svg(svg_path, bounds):
    """Bounding box of the copper drawn in a two-layer (copper + Edge.Cuts)
    KiCad SVG, converted to design coordinates under the assumption that the
    plot shows +x to the right and +y UP.  ``bounds`` is the design-frame
    bounding box of the board outline (it locates the origin in the plot)."""
    boxes = kicad_cli.svg_color_bboxes(open(svg_path).read())
    boxes.pop("#FFFFFF", None)                 # drill marks of NPTH holes
    if len(boxes) != 2:
        raise RuntimeError("expected exactly two plotted layers in %s" % svg_path)
    (_ec, edge), (_cc, cu) = sorted(
        boxes.items(), key=lambda kv: -(kv[1][2] - kv[1][0]) * (kv[1][3] - kv[1][1]))
    half = board.EDGE_WIDTH_MM / 2.0
    ox = edge[0] + half - bounds[0]            # SVG x of design x = 0
    oy = edge[1] + half + bounds[3]            # SVG y of design y = 0 (SVG y grows downward)
    return (cu[0] - ox, oy - cu[3], cu[2] - ox, oy - cu[1])


def model_copper_bbox(design, layer):
    polys = [p.polygon for p in geometry.placed_pads(design)
             if p.polygon is not None and layer in p.layers]
    xs0, ys0, xs1, ys1 = zip(*(p.bounds for p in polys))
    return (min(xs0), min(ys0), max(xs1), max(ys1))


def prove(design, out):
    name = design.name
    print("=== %s ===" % name)
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)

    # 1. checks
    report = checks.run_checks(design)
    print(report.text().strip())
    if not report.ok:
        return False

    # 2. build
    files = board.build_board(design, out)
    print("built %s, %s%s" % (os.path.basename(files.pcb), os.path.basename(files.pro),
                             ", " + os.path.basename(files.dru) if files.dru else ""))

    # 3. pcbnew read-back
    summary = board.board_summary(files.pcb)
    model = {}
    for pad in geometry.placed_pads(design):
        model.setdefault((pad.ref, pad.number), []).append(pad)
    worst, count, bottom = 0.0, 0, 0
    for ref, fp in summary["footprints"].items():
        bottom += fp["side"] == "bottom"
        for pad in fp["pads"]:
            if (ref, pad["number"]) not in model:
                continue
            best = min(model[(ref, pad["number"])],
                       key=lambda c: math.hypot(c.x - pad["x"], c.y - pad["y"]))
            worst, count = max(worst, math.hypot(best.x - pad["x"], best.y - pad["y"])), count + 1
            if (best.net or "") != pad["net"] or list(best.layers) != pad["layers"]:
                print("pad %s.%s: model and board disagree" % (ref, pad["number"]))
                return False
    print("pcbnew read-back: %d footprints (%d on the bottom), %d pads compared with the "
          "model, worst position error %.2e mm" % (
              len(summary["footprints"]), bottom, count, worst))
    if worst > 1e-6:
        return False
    classes = ", ".join("%s %.3g/%.3g" % (n, c["track_width"], c["clearance"])
                        for n, c in summary["netclass_values"].items())
    print("rules loaded by KiCad: min track %.3g, min clearance %.3g; net classes "
          "(track/clearance): %s" % (summary["rules"]["min_track"],
                                     summary["rules"]["min_clearance"], classes))

    # 4. zone fill + DRC
    result = drc.run_drc(files.pcb, json_path=os.path.join(out, name + ".drc.json"))
    print(result.summary())
    try:
        drc.assert_clean(result, allow_unconnected=True)     # unrouted on purpose
    except drc.DrcError as exc:
        print(exc)
        return False
    if result.unconnected_count == 0:
        print("unexpected: an unrouted board reported no unconnected items")
        return False

    # 5. plots + orientation
    bounds = design.outline.bounds()
    kicad_cli.export_svg(files.pcb, os.path.join(out, name + "_top.svg"), TOP_LAYERS)
    kicad_cli.export_svg(files.pcb, os.path.join(out, name + "_bottom.svg"), BOTTOM_LAYERS,
                         mirror=True)
    render_png(files.pcb, TOP_LAYERS, os.path.join(out, name + "_top.png"), bounds)
    render_png(files.pcb, BOTTOM_LAYERS, os.path.join(out, name + "_bottom_xray.png"), bounds)
    tmp = os.path.join(out, "_orient.svg")
    ok = True
    for layer, mirror, label in (("F.Cu", False, "top view"),
                                 ("B.Cu", False, "bottom copper seen from the top"),
                                 ("B.Cu", True, "bottom view (mirrored)")):
        kicad_cli.export_svg(files.pcb, tmp, [layer, "Edge.Cuts"], mirror=mirror)
        if mirror:
            # mirrored plot: the plot's x axis is the negated design x axis
            got = copper_bbox_from_svg(tmp, (-bounds[2], bounds[1], -bounds[0], bounds[3]))
            got = (-got[2], got[1], -got[0], got[3])
        else:
            got = copper_bbox_from_svg(tmp, bounds)
        want = model_copper_bbox(design, layer)
        err = max(abs(a - b) for a, b in zip(got, want))
        print("%-32s copper bbox in the plot (%.2f, %.2f)..(%.2f, %.2f), model "
              "(%.2f, %.2f)..(%.2f, %.2f), max deviation %.3f mm" % ((label,) + got + want
                                                                    + (err,)))
        ok = ok and err < 0.03
    os.remove(tmp)
    if not ok:
        print("orientation check FAILED")
        return False
    asym = model_copper_bbox(design, "F.Cu")
    if abs(asym[0] + asym[2]) < 0.2 or abs(asym[1] + asym[3]) < 0.2:
        print("orientation check is not conclusive: top copper is symmetric")
        return False

    with open(os.path.join(out, name + ".checks.json"), "w") as fh:
        json.dump(report.to_dict(), fh, indent=2, sort_keys=True)
        fh.write("\n")
    print("PROOF OK (%s): 0 check errors, 0 DRC errors, %d unconnected (unrouted), "
          "+x right / +y up" % (name, result.unconnected_count))
    return True


def main(argv):
    root = os.path.abspath(argv[1] if len(argv) > 1 else os.path.join(HERE, "proof_out"))
    ok = True
    for design in (mini_design(), dshape_design()):
        ok = prove(design, os.path.join(root, design.name)) and ok
    print("ALL PROOFS OK" if ok else "PROOF FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
