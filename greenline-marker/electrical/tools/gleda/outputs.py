"""Manufacturing and hand-over outputs of a routed, DRC-checked board.

``generate_outputs(design, pcb_path, out_dir)`` writes::

    fab/                         bare-board package (zip-ready)
      README.txt                 stack-up, rules, board-level minimums, drill table, file list
      <name>-F_Cu.gbr ...        Gerber X2: every copper layer, mask, paste, silk, Edge.Cuts
      <name>-job.gbrjob          Gerber job file (stack-up and rules for the CAM operator)
      <name>-PTH.drl / -NPTH.drl Excellon drill files (plated / non-plated)
      <name>-PTH-drl_map.gbr ... drill maps (Gerber X2)
    <name>-fab.zip               the same directory as one archive
    assembly/
      <name>-pos.csv             pick-and-place, both sides
      <name>-bom.csv             grouped bill of materials with prices
    <name>-netlist.json          nets, pads, net classes, parts (the design model)
    <name>-mechanical.json       outline, holes, keep-outs and every component body
                                 (ref, x, y, rot, side, L / W / H) for mechanical CAD
    <name>-board.step            the bare board as a solid (outline, cut-outs, NPTH
                                 holes; no components, no via holes)
    renders/                     top / bottom / inner-layer pictures (SVG and PNG)
    outputs.json                 manifest: every file with size and SHA-256

Honesty rules of this module

* outputs are plotted from the board FILE and belong to its DRC result:
  ``generate_outputs`` takes the :class:`gleda.drc.DrcResult` of that file (or
  runs KiCad's DRC itself) and refuses to write a package for a board that is
  not clean unless ``require_clean=False`` - and then the README says
  "NOT CLEAN - DO NOT FABRICATE" in its first lines;
* what was plotted is checked against the design model, not just "the file
  exists": :func:`verify_outputs` compares the Edge.Cuts extents, every pad
  flash on both outer layers, every drill hit and every pick-and-place row
  with the model (this also proves origin, +y direction and bottom-side
  mirroring of the exported data).

Coordinates: all Gerber, drill and position files use the board centre as
origin (KiCad's drill / place origin, set by :mod:`gleda.board`), X to the
right and Y up as seen from the top, in mm - i.e. exactly the design frame.

Determinism: creation dates are removed from Gerber, drill and job files and
the zip archive uses fixed time stamps, so re-runs give identical bytes.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from . import coords, geometry, kicad_cli
from .model import Design, Via, BOTTOM, TOP

#: non-copper layers of the fabrication set (the board's copper layers are
#: added in front, top to bottom)
FAB_TECH_LAYERS: Tuple[str, ...] = ("F.Mask", "B.Mask", "F.Paste", "B.Paste", "F.SilkS",
                                    "B.SilkS", "Edge.Cuts")

#: what each layer is, for the README
LAYER_PURPOSE: Dict[str, str] = {
    "F.Cu": "copper, top (layer 1)", "B.Cu": "copper, bottom",
    "F.Mask": "solder mask openings, top", "B.Mask": "solder mask openings, bottom",
    "F.Paste": "solder paste (stencil), top", "B.Paste": "solder paste (stencil), bottom",
    "F.SilkS": "silkscreen (legend), top", "B.SilkS": "silkscreen (legend), bottom",
    "Edge.Cuts": "board outline, cut-outs and routed (non-plated) slots",
}

#: KiCad's Gerber file name stems for layers whose name is not just "." -> "_"
_GERBER_STEM = {"F.SilkS": "F_Silkscreen", "B.SilkS": "B_Silkscreen"}

POSITION_TOLERANCE = 1e-4          # mm: exported coordinate vs model
EDGE_TOLERANCE = 0.002             # mm: Edge.Cuts Gerber vs exact outline
STEP_TOLERANCE = 0.02              # mm: STEP solid (arcs become polygons) vs outline
ZIP_TIME = (1980, 1, 1, 0, 0, 0)   # fixed time stamp of every archive member


class OutputError(Exception):
    """Outputs could not be generated or do not agree with the design."""


def gerber_name(design_name: str, layer: str) -> str:
    """File name kicad-cli gives the Gerber of ``layer``."""
    return "%s-%s.gbr" % (design_name, _GERBER_STEM.get(layer, layer.replace(".", "_")))


def fab_layers(design: Design) -> List[str]:
    """Layers of the fabrication set, copper first (top to bottom)."""
    return list(design.copper_layers) + list(FAB_TECH_LAYERS)


def natural_key(text: str) -> Tuple:
    """Sort key: "R2" < "R10"."""
    return tuple((0, int(tok)) if tok.isdigit() else (1, tok)
                 for tok in re.findall(r"\d+|\D+", str(text)))


# --------------------------------------------------------------------------
# Gerber / Excellon export and normalisation
# --------------------------------------------------------------------------

_GERBER_DATE = re.compile(r"^%TF\.CreationDate,[^*]*\*%\r?\n", re.M)
_GERBER_CREATED = re.compile(r"^(G04 Created by KiCad \([^)]*\)) date [^*]*\*", re.M)
_DRILL_DATE = re.compile(r"^(; DRILL file \{[^}]*\}) date .*$", re.M)
_DRILL_TF_DATE = re.compile(r"^; #@! TF\.CreationDate,.*\r?\n", re.M)


def strip_dates(path: str) -> None:
    """Remove the creation time from a Gerber, Excellon or Gerber job file
    (the only content that differs between two plots of the same board)."""
    with open(path, encoding="utf-8", errors="surrogateescape", newline="") as fh:
        text = fh.read()
    if path.endswith(".gbrjob"):
        data = json.loads(text)
        data.get("Header", {}).pop("CreationDate", None)
        fixed = json.dumps(data, indent=2) + "\n"
    else:
        fixed = _GERBER_DATE.sub("", text)
        fixed = _GERBER_CREATED.sub(r"\1*", fixed)
        fixed = _DRILL_TF_DATE.sub("", fixed)
        fixed = _DRILL_DATE.sub(r"\1", fixed)
    if fixed != text:
        with open(path, "w", encoding="utf-8", errors="surrogateescape", newline="") as fh:
            fh.write(fixed)


def export_gerbers(pcb_path: str, out_dir: str, layers: Sequence[str]) -> List[str]:
    """Plot ``layers`` as Gerber X2 into ``out_dir`` (one file per layer plus
    the ``.gbrjob`` job file); origin = drill / place origin.  Returns the
    files written.  An explicit layer list is mandatory."""
    layers = list(layers)
    if not layers:
        raise OutputError("export_gerbers needs an explicit layer list")
    os.makedirs(out_dir, exist_ok=True)
    before = set(os.listdir(out_dir))
    kicad_cli.run_kicad_cli([
        "pcb", "export", "gerbers", "--output", out_dir + os.sep, "--layers", ",".join(layers),
        "--use-drill-file-origin", "--subtract-soldermask", "--no-protel-ext", pcb_path])
    name = os.path.splitext(os.path.basename(pcb_path))[0]
    files = [os.path.join(out_dir, gerber_name(name, layer)) for layer in layers]
    missing = [os.path.basename(f) for f in files if not os.path.exists(f)]
    if missing:
        new = sorted(set(os.listdir(out_dir)) - before)
        raise OutputError("kicad-cli did not plot %s (it wrote: %s)" % (
            ", ".join(missing), ", ".join(new) or "nothing"))
    job = os.path.join(out_dir, "%s-job.gbrjob" % name)
    if os.path.exists(job):
        files.append(job)
    for path in files:
        strip_dates(path)
    return files


def export_drill(pcb_path: str, out_dir: str) -> List[str]:
    """Excellon drill files (separate plated / non-plated, mm, decimal, same
    origin as the Gerbers) and Gerber X2 drill maps."""
    os.makedirs(out_dir, exist_ok=True)
    kicad_cli.run_kicad_cli([
        "pcb", "export", "drill", "--output", out_dir + os.sep, "--format", "excellon",
        "--drill-origin", "plot", "--excellon-units", "mm", "--excellon-zeros-format",
        "decimal", "--excellon-separate-th", "--generate-map", "--map-format", "gerberx2",
        pcb_path])
    name = os.path.splitext(os.path.basename(pcb_path))[0]
    files = []
    for suffix in ("-PTH.drl", "-NPTH.drl", "-PTH-drl_map.gbr", "-NPTH-drl_map.gbr"):
        path = os.path.join(out_dir, name + suffix)
        if os.path.exists(path):
            strip_dates(path)
            files.append(path)
    if not any(f.endswith("-PTH.drl") for f in files):
        raise OutputError("kicad-cli did not write %s-PTH.drl" % name)
    return files


# --------------------------------------------------------------------------
# reading Gerber / Excellon back (for verification)
# --------------------------------------------------------------------------

@dataclass
class GerberData:
    """The geometry skeleton of a Gerber file: flash positions, the extents of
    everything drawn (centre lines; arcs included) and its file function."""
    file_function: str = ""
    flashes: List[Tuple[float, float]] = field(default_factory=list)
    #: start and end point of every drawn line / arc (D01)
    vertices: List[Tuple[float, float]] = field(default_factory=list)
    draws: int = 0
    regions: int = 0
    bounds: Optional[Tuple[float, float, float, float]] = None

    def _grow(self, x: float, y: float) -> None:
        if self.bounds is None:
            self.bounds = (x, y, x, y)
        else:
            b = self.bounds
            self.bounds = (min(b[0], x), min(b[1], y), max(b[2], x), max(b[3], y))


def _arc_extents(x0: float, y0: float, x1: float, y1: float, cx: float, cy: float,
                 clockwise: bool) -> List[Tuple[float, float]]:
    """End point plus the axis extremes an arc passes through."""
    r = math.hypot(x0 - cx, y0 - cy)
    a0 = math.atan2(y0 - cy, x0 - cx)
    a1 = math.atan2(y1 - cy, x1 - cx)
    sweep = (a0 - a1) if clockwise else (a1 - a0)
    sweep %= 2 * math.pi
    if sweep < 1e-12:
        sweep = 2 * math.pi                    # full circle (multi-quadrant mode)
    pts = [(x1, y1)]
    for k in range(4):
        axis = k * math.pi / 2.0
        delta = (a0 - axis) if clockwise else (axis - a0)
        delta %= 2 * math.pi
        if delta <= sweep + 1e-12:
            pts.append((cx + r * math.cos(axis), cy + r * math.sin(axis)))
    return pts


def read_gerber(path: str) -> GerberData:
    """Parse the subset of RS-274X that KiCad writes: coordinate format, D01 /
    D02 / D03 operations with modal coordinates, G01 / G02 / G03, regions."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    data = GerberData()
    m = re.search(r"%TF\.FileFunction,([^*]*)\*%", text)
    if m:
        data.file_function = m.group(1)
    m = re.search(r"%FSLAX(\d)(\d)Y(\d)(\d)\*%", text)
    if not m:
        raise OutputError("%s: no coordinate format statement" % os.path.basename(path))
    scale = 10.0 ** int(m.group(2))
    if "%MOMM*%" not in text:
        raise OutputError("%s: not in millimetres" % os.path.basename(path))
    body = re.sub(r"%[^%]*%", "", text)
    x = y = 0.0
    mode = "G01"
    op = re.compile(r"^(?:(G0?[123]))?(?:X(-?\d+))?(?:Y(-?\d+))?(?:I(-?\d+))?(?:J(-?\d+))?"
                    r"(?:D0?([123]))?$")
    last_d = None
    for stmt in body.replace("\r", "").replace("\n", "").split("*"):
        stmt = stmt.strip()
        if not stmt or stmt.startswith("G04"):
            continue
        if stmt == "G36":
            data.regions += 1
            continue
        m = op.match(stmt)
        if not m or not any(m.groups()):
            continue
        if m.group(1):
            mode = "G0" + m.group(1)[-1]
        if m.group(2) is None and m.group(3) is None and m.group(6) is None:
            continue
        nx = int(m.group(2)) / scale if m.group(2) is not None else x
        ny = int(m.group(3)) / scale if m.group(3) is not None else y
        d = m.group(6) or last_d
        last_d = d
        if d == "3":
            data.flashes.append((nx, ny))
            data._grow(nx, ny)
        elif d == "1":
            data.draws += 1
            data._grow(x, y)
            data.vertices += [(x, y), (nx, ny)]
            if mode in ("G02", "G03"):
                i = int(m.group(4) or 0) / scale
                j = int(m.group(5) or 0) / scale
                for px, py in _arc_extents(x, y, nx, ny, x + i, y + j, mode == "G02"):
                    data._grow(px, py)
            else:
                data._grow(nx, ny)
        x, y = nx, ny
    return data


@dataclass
class DrillData:
    """Content of an Excellon file: tool diameters and hits."""
    plated: Optional[bool] = None
    #: (diameter, x, y) of every round hit
    hits: List[Tuple[float, float, float]] = field(default_factory=list)
    #: (diameter, x1, y1, x2, y2) of every slot (G85)
    slots: List[Tuple[float, float, float, float, float]] = field(default_factory=list)

    def table(self) -> List[Tuple[float, int]]:
        """(diameter, count) per tool size, smallest first; a slot counts once."""
        counts: Dict[float, int] = {}
        for dia, _x, _y in self.hits:
            counts[dia] = counts.get(dia, 0) + 1
        for slot in self.slots:
            counts[slot[0]] = counts.get(slot[0], 0) + 1
        return sorted(counts.items())


def read_excellon(path: str) -> DrillData:
    """Parse a KiCad Excellon file (metric, decimal coordinates)."""
    data = DrillData()
    tools: Dict[str, float] = {}
    current: Optional[float] = None
    header = True
    with open(path, encoding="utf-8", errors="replace") as fh:
        lines = fh.read().splitlines()
    if not any(line.strip() == "METRIC" or line.startswith("METRIC") for line in lines):
        raise OutputError("%s: not a metric Excellon file" % os.path.basename(path))
    coord = r"X(-?\d+(?:\.\d+)?)Y(-?\d+(?:\.\d+)?)"
    for line in lines:
        line = line.strip()
        if line.startswith(";"):
            if "TF.FileFunction,Plated" in line:
                data.plated = True
            elif "TF.FileFunction,NonPlated" in line:
                data.plated = False
            continue
        if header:
            m = re.match(r"^T(\d+)C(\d+(?:\.\d+)?)", line)
            if m:
                tools[str(int(m.group(1)))] = float(m.group(2))
            if line == "%":
                header = False
            continue
        m = re.match(r"^T(\d+)$", line)
        if m:
            current = tools.get(str(int(m.group(1))))
            continue
        m = re.match(r"^%sG85%s$" % (coord, coord), line)
        if m and current is not None:
            data.slots.append((current,) + tuple(float(g) for g in m.groups()))   # type: ignore
            continue
        m = re.match(r"^%s$" % coord, line)
        if m and current is not None:
            data.hits.append((current, float(m.group(1)), float(m.group(2))))
        elif line.startswith(("G00", "M15", "M16", "G01")) and "X" in line:
            raise OutputError("%s: routed slots (G00/M15) are not supported by the "
                              "reader" % os.path.basename(path))
    return data


# --------------------------------------------------------------------------
# pick and place, BOM, netlist, mechanical data
# --------------------------------------------------------------------------

POS_COLUMNS = ("Ref", "Val", "Package", "PosX", "PosY", "Rot", "Side", "MPN")


def placed_refs(design: Design) -> List[str]:
    """References that are assembled by machine: on the BOM and not DNP."""
    return [p.ref for p in design.parts if p.in_bom and not p.dnp]


def export_positions(design: Design, pcb_path: str, csv_path: str) -> List[Dict[str, Any]]:
    """Pick-and-place file for both sides.

    The rows come from ``kicad-cli pcb export pos`` (so they are what KiCad
    reads in the board file), sorted by reference, with the MPN added as the
    last column.  Coordinates: mm, origin board centre, +y up, seen from the
    top for BOTH sides (bottom X is not mirrored); ``Rot`` is the footprint
    rotation in degrees counter-clockwise seen from the top.  Raises
    :class:`OutputError` if any row disagrees with the design model."""
    os.makedirs(os.path.dirname(os.path.abspath(csv_path)), exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gleda_pos_") as tmp:
        raw = os.path.join(tmp, "pos.csv")
        kicad_cli.run_kicad_cli(["pcb", "export", "pos", "--output", raw, "--format", "csv",
                                 "--units", "mm", "--side", "both", "--use-drill-file-origin",
                                 pcb_path])
        with open(raw, newline="", encoding="utf-8") as fh:
            raw_rows = list(csv.DictReader(fh))
    parts = design.parts_by_ref
    rows = []
    for r in raw_rows:
        ref = r["Ref"]
        rows.append({"Ref": ref, "Val": r["Val"], "Package": r["Package"],
                     "PosX": float(r["PosX"]), "PosY": float(r["PosY"]),
                     "Rot": coords.normalize_angle(float(r["Rot"])), "Side": r["Side"],
                     "MPN": parts[ref].mpn if ref in parts else ""})
    rows.sort(key=lambda r: natural_key(r["Ref"]))
    problems = check_positions(design, rows)
    if problems:
        raise OutputError("pick-and-place data disagrees with the design: %s" % (
            "; ".join(problems[:10])))
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(POS_COLUMNS)
        for r in rows:
            w.writerow([r["Ref"], r["Val"], r["Package"], "%.4f" % r["PosX"], "%.4f" % r["PosY"],
                        "%.2f" % r["Rot"], r["Side"], r["MPN"]])
    return rows


def check_positions(design: Design, rows: Sequence[Dict[str, Any]]) -> List[str]:
    """Compare pick-and-place rows with the model: the set of references, and
    x / y / rotation / side of each."""
    problems: List[str] = []
    parts = design.parts_by_ref
    want = set(placed_refs(design))
    got = [r["Ref"] for r in rows]
    for ref in sorted(want - set(got), key=natural_key):
        problems.append("%s is missing in the position file" % ref)
    for ref in sorted(set(got) - want, key=natural_key):
        problems.append("%s is in the position file but is not a placed BOM part" % ref)
    if len(got) != len(set(got)):
        problems.append("duplicate references in the position file")
    for r in rows:
        part = parts.get(r["Ref"])
        if part is None or r["Ref"] not in want:
            continue
        if abs(r["PosX"] - part.x) > POSITION_TOLERANCE or \
                abs(r["PosY"] - part.y) > POSITION_TOLERANCE:
            problems.append("%s at (%.4f, %.4f) in the position file, (%.4f, %.4f) in the "
                            "design" % (part.ref, r["PosX"], r["PosY"], part.x, part.y))
        d = (r["Rot"] - part.rotation) % 360.0
        if min(d, 360.0 - d) > 1e-3:
            problems.append("%s rotation %.3f in the position file, %.3f in the design" % (
                part.ref, r["Rot"], part.rotation))
        if r["Side"] != part.side:
            problems.append("%s on the %s side in the position file, %s in the design" % (
                part.ref, r["Side"], part.side))
    return problems


BOM_COLUMNS = ("Item", "Qty", "References", "Value", "Description", "Footprint", "MPN",
               "Manufacturer", "Distributor", "Distributor PN", "Unit Price",
               "Extended Price", "DNP")


def bom_groups(design: Design) -> List[Dict[str, Any]]:
    """Grouped bill of materials.

    Parts with ``in_bom=False`` (bare pads, fiducials) are left out.  Parts
    are grouped when value, footprint, MPN, manufacturer, distributor data,
    unit price and DNP state are all equal.  DNP groups are listed (so nobody
    wonders where the references went) with an extended price of 0."""
    groups: Dict[Tuple, Dict[str, Any]] = {}
    for part in design.parts:
        if not part.in_bom:
            continue
        key = (part.value, part.footprint_name, part.mpn, part.manufacturer, part.distributor,
               part.distributor_pn, part.unit_price, bool(part.dnp))
        g = groups.get(key)
        if g is None:
            g = groups[key] = {
                "refs": [], "value": part.value, "description": part.description,
                "footprint": part.footprint_name, "mpn": part.mpn,
                "manufacturer": part.manufacturer, "distributor": part.distributor,
                "distributor_pn": part.distributor_pn, "unit_price": part.unit_price,
                "dnp": bool(part.dnp)}
        g["refs"].append(part.ref)
    out = []
    for g in groups.values():
        g["refs"].sort(key=natural_key)
        g["qty"] = len(g["refs"])
        if g["dnp"]:
            g["extended_price"] = 0.0
        elif g["unit_price"] is None:
            g["extended_price"] = None
        else:
            g["extended_price"] = round(g["qty"] * g["unit_price"], 6)
        out.append(g)
    out.sort(key=lambda g: (g["dnp"], natural_key(g["refs"][0])))
    for i, g in enumerate(out, start=1):
        g["item"] = i
    return out


def bom_totals(groups: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Line count, placed part count, cost per board and what is not priced."""
    fitted = [g for g in groups if not g["dnp"]]
    unpriced = [ref for g in fitted if g["unit_price"] is None for ref in g["refs"]]
    return {
        "lines": len(groups),
        "parts_fitted": sum(g["qty"] for g in fitted),
        "parts_dnp": sum(g["qty"] for g in groups if g["dnp"]),
        "cost_per_board": round(sum(g["extended_price"] or 0.0 for g in fitted), 4),
        "unpriced_refs": unpriced,
    }


def _price(value: Optional[float]) -> str:
    return "" if value is None else "%.4f" % value


def write_bom(design: Design, csv_path: str) -> List[Dict[str, Any]]:
    """Write the grouped BOM as CSV; returns the groups."""
    groups = bom_groups(design)
    os.makedirs(os.path.dirname(os.path.abspath(csv_path)), exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(BOM_COLUMNS)
        for g in groups:
            w.writerow([g["item"], g["qty"], " ".join(g["refs"]), g["value"], g["description"],
                        g["footprint"], g["mpn"], g["manufacturer"], g["distributor"],
                        g["distributor_pn"], _price(g["unit_price"]),
                        _price(g["extended_price"]), "DNP" if g["dnp"] else ""])
    return groups


def _dump_json(data: Any, path: str) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, sort_keys=True)
        fh.write("\n")
    return path


def netlist_data(design: Design) -> Dict[str, Any]:
    """The design's netlist with everything needed to rebuild connectivity:
    nets (pins, pads, class, planes), no-connects, net classes, parts."""
    data = design.netlist()
    data["netclasses"] = {name: nc.to_dict() for name, nc in sorted(design.netclasses.items())}
    data["parts"] = {
        p.ref: {"value": p.value, "footprint": p.footprint_name, "mpn": p.mpn,
                "group": p.group, "dnp": p.dnp, "in_bom": p.in_bom,
                "pins": {n: {"pads": list(pin.pads), "type": pin.etype,
                             "net": design.pin_net(p.ref, n)}
                         for n, pin in p.pins.items()}}
        for p in design.parts}
    data["counts"] = {"parts": len(design.parts), "nets": len(design.nets),
                      "pads_on_nets": sum(len(n["pads"]) for n in data["nets"].values())}
    return data


def _element_points(el) -> List[Tuple[float, float]]:
    """Points that span the bounding box of an exact path element."""
    if isinstance(el, geometry.Line):
        return [el.start, el.end]
    if isinstance(el, geometry.FullCircle):
        (cx, cy), r = el.center, el.radius
        return [(cx - r, cy), (cx + r, cy), (cx, cy - r), (cx, cy + r)]
    _a0, sweep = el.angles
    return [el.start] + _arc_extents(el.start[0], el.start[1], el.end[0], el.end[1],
                                     el.center[0], el.center[1], sweep < 0)


def edge_contours(design: Design) -> List[List[object]]:
    """The closed contours :mod:`gleda.board` draws on Edge.Cuts (outer
    boundary first), as exact lines / arcs / circles."""
    return geometry.outline_contours(design.outline, design.rules.max_arc_error)


def edge_bounds(design: Design) -> Tuple[float, float, float, float]:
    """Exact (xmin, ymin, xmax, ymax) of the board edge centre line, notches
    included (a notch can remove the extreme point of the raw outline)."""
    pts = [p for contour in edge_contours(design) for el in contour
           for p in _element_points(el)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _path_primitives(path: Sequence[object]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for el in path:
        if isinstance(el, geometry.Line):
            out.append({"type": "line", "start": [round(v, 6) for v in el.start],
                        "end": [round(v, 6) for v in el.end]})
        elif isinstance(el, geometry.FullCircle):
            out.append({"type": "circle", "center": [round(v, 6) for v in el.center],
                        "radius": round(el.radius, 6)})
        else:
            _a0, sweep = el.angles
            out.append({"type": "arc", "start": [round(v, 6) for v in el.start],
                        "mid": [round(v, 6) for v in el.mid],
                        "end": [round(v, 6) for v in el.end],
                        "center": [round(v, 6) for v in el.center],
                        "radius": round(el.radius, 6), "ccw": sweep > 0})
    return out


def _ring(poly, digits: int = 4) -> List[List[float]]:
    return [[round(x, digits), round(y, digits)] for x, y in list(poly.exterior.coords)[:-1]]


def mechanical_data(design: Design, tol: float = 0.01) -> Dict[str, Any]:
    """Board and component geometry for the mechanical CAD team.

    Frame: mm, origin at the board centre, +x right and +y up seen from the
    TOP; z = 0 is the bottom surface of the board, the top surface is at
    ``thickness``.  The board edge is given exactly (``edge_contours``: lines,
    arcs and circles, outer boundary first, then cut-outs and slots) and as a
    polygon within ``tol``.  Every component has its footprint anchor (x, y), rotation
    (degrees CCW seen from the top), side, and its body as length (along the
    rotated footprint x axis) x width x height, the body centre (cx, cy), the
    body corner points and the z range it occupies."""
    t = design.board_thickness
    outline = geometry.outline_polygon(design.outline, tol)
    xmin, ymin, xmax, ymax = edge_bounds(design)
    contours = edge_contours(design)
    components = []
    tallest = {TOP: 0.0, BOTTOM: 0.0}
    for part in sorted(design.parts, key=lambda p: natural_key(p.ref)):
        if not part.placed:
            continue
        body = geometry.part_body(part)
        height = body["height"]
        h = float(height or 0.0)
        tallest[part.side] = max(tallest[part.side], h)
        z0, z1 = (t, t + h) if part.side == TOP else (-h, 0.0)
        cb = geometry.part_courtyard(part).bounds
        components.append({
            "ref": part.ref, "value": part.value, "footprint": part.footprint_name,
            "mpn": part.mpn, "x": round(part.x, 4), "y": round(part.y, 4),
            "rot": coords.normalize_angle(part.rotation), "side": part.side,
            "body": {"length": body["length"], "width": body["width"], "height": height,
                     "cx": body["cx"], "cy": body["cy"],
                     "corners": _ring(geometry.part_body_polygon(part))},
            "z_min": round(z0, 4), "z_max": round(z1, 4),
            "courtyard_bbox": [round(v, 4) for v in cb],
            "height_known": height is not None,
            "dnp": bool(part.dnp), "in_bom": bool(part.in_bom),
        })
    cutouts = []
    for shape in design.outline.cutouts:
        poly = geometry.shape_polygon(shape, tol)
        entry: Dict[str, Any] = {"type": type(shape).__name__, "polygon": _ring(poly)}
        for key in ("cx", "cy", "r", "x1", "y1", "x2", "y2", "width"):
            if hasattr(shape, key):
                entry[key] = getattr(shape, key)
        cutouts.append(entry)
    return {
        "design": design.name, "revision": design.revision, "units": "mm",
        "frame": "origin = board centre; +x right, +y up seen from the top; rot = degrees "
                 "counter-clockwise seen from the top (also for bottom-side parts); "
                 "z = 0 bottom surface, z = thickness top surface",
        "board": {
            "thickness": t, "copper_layers": design.layers,
            "bounds": [round(xmin, 4), round(ymin, 4), round(xmax, 4), round(ymax, 4)],
            "edge_contours": [_path_primitives(c) for c in contours],
            "outline_polygon": _ring(outline),
            "outline_polygon_holes": [[[round(x, 4), round(y, 4)]
                                       for x, y in list(ring.coords)[:-1]]
                                      for ring in outline.interiors],
            "outline_tolerance": tol,
            "cutouts": cutouts,
            "npth_holes": [{"name": h.name, "x": h.x, "y": h.y, "diameter": h.drill}
                           for h in design.outline.holes],
        },
        "keepouts": [{"name": k.name, "layers": list(k.layer_names(design.copper_layers)),
                      "no_tracks": k.tracks, "no_vias": k.vias, "no_copper": k.copper,
                      "no_footprints": k.footprints,
                      "polygon": _ring(geometry.keepout_polygon(k, tol))}
                     for k in design.keepouts],
        "height_limits": [{"name": h.name, "side": h.side, "max_height": h.max_height,
                           "exempt": list(h.exempt),
                           "polygon": _ring(geometry.shape_polygon(h.shape, tol))}
                          for h in design.height_limits],
        "max_height": {"top": tallest[TOP], "bottom": tallest[BOTTOM]},
        "components": components,
    }


# --------------------------------------------------------------------------
# bare-board STEP
# --------------------------------------------------------------------------

_STEP_FILE_NAME = re.compile(r"FILE_NAME\('([^']*)','[^']*'")
_STEP_POINT = re.compile(r"CARTESIAN_POINT\('[^']*',\(([-0-9.Ee+]+),([-0-9.Ee+]+),"
                         r"([-0-9.Ee+]+)\)\)")
STEP_FIXED_DATE = "2000-01-01T00:00:00"


def export_board_step(pcb_path: str, step_path: str) -> str:
    """Bare board as a STEP solid (``kicad-cli pcb export step --board-only``):
    outline with cut-outs and slots, NPTH holes, thickness from the stack-up.
    Origin = board centre, +y up, z = 0 at the bottom surface - the frame of
    the mechanical JSON.  Components are not included (the generated
    footprints carry no 3D models) and via holes are not drilled.  The
    creation time in the header is replaced by a fixed placeholder."""
    os.makedirs(os.path.dirname(os.path.abspath(step_path)), exist_ok=True)
    kicad_cli.run_kicad_cli(["pcb", "export", "step", "--output", step_path, "--drill-origin",
                             "--board-only", "--force", pcb_path])
    if not os.path.exists(step_path) or os.path.getsize(step_path) < 1000:
        raise OutputError("kicad-cli did not create %s" % step_path)
    with open(step_path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    fixed = _STEP_FILE_NAME.sub(lambda m: "FILE_NAME('%s','%s'" % (m.group(1), STEP_FIXED_DATE),
                                text, count=1)
    if fixed != text:
        with open(step_path, "w", encoding="utf-8") as fh:
            fh.write(fixed)
    return step_path


def step_extents(step_path: str) -> Tuple[float, float, float, float, float, float]:
    """(xmin, ymin, zmin, xmax, ymax, zmax) of the solid's vertices and curve
    points in a STEP file written by KiCad."""
    with open(step_path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    pts = [tuple(float(v) for v in m.groups()) for m in _STEP_POINT.finditer(text)]
    if not pts:
        raise OutputError("%s: no geometry" % os.path.basename(step_path))
    return (min(p[0] for p in pts), min(p[1] for p in pts), min(p[2] for p in pts),
            max(p[0] for p in pts), max(p[1] for p in pts), max(p[2] for p in pts))


def check_step(design: Design, step_path: str) -> List[str]:
    """Compare the STEP solid's extents with the board edge and thickness."""
    try:
        x0, y0, _z0, x1, y1, z1 = step_extents(step_path)
    except OutputError as exc:
        return [str(exc)]
    problems = []
    want = edge_bounds(design)
    for label, got_v, want_v in zip(("xmin", "ymin", "xmax", "ymax"), (x0, y0, x1, y1), want):
        if abs(got_v - want_v) > STEP_TOLERANCE:
            problems.append("STEP %s is %.4f, %.4f in the design" % (label, got_v, want_v))
    if abs(z1 - design.board_thickness) > 1e-6:
        problems.append("STEP top surface is at z = %.4f, the board is %.4f mm thick" % (
            z1, design.board_thickness))
    return problems


# --------------------------------------------------------------------------
# renders
# --------------------------------------------------------------------------

def _pdf_page_mm(pdf_path: str) -> Tuple[float, float]:
    proc = subprocess.run(["pdfinfo", pdf_path], capture_output=True, text=True)
    m = re.search(r"Page size:\s+([0-9.]+) x ([0-9.]+) pts", proc.stdout)
    if proc.returncode != 0 or not m:
        raise OutputError("pdfinfo failed on %s: %s" % (pdf_path, proc.stderr.strip()))
    return float(m.group(1)) * 25.4 / 72.0, float(m.group(2)) * 25.4 / 72.0


def render_view(pcb_path: str, png_path: str, layers: Sequence[str],
                bounds: Tuple[float, float, float, float], *, mirror: bool = False,
                dpi: int = 600, margin: float = 1.0) -> Dict[str, Any]:
    """Render ``layers`` of a board to a PNG cropped to ``bounds`` (design mm:
    xmin, ymin, xmax, ymax) plus ``margin``.

    kicad-cli plots a PDF page, ``pdftoppm`` rasterises and crops it.  The
    picture shows design +y towards the top.  ``mirror`` gives the view from
    BELOW (left and right swapped), the natural view of the bottom side.
    Returns the mapping between pixels and design millimetres::

        px = origin_px[0] + x_sign * x * px_per_mm
        py = origin_px[1] - y * px_per_mm
    """
    layers = list(layers)
    if not layers:
        raise OutputError("render_view needs an explicit layer list")
    os.makedirs(os.path.dirname(os.path.abspath(png_path)), exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gleda_render_") as tmp:
        pdf = os.path.join(tmp, "view.pdf")
        args = ["pcb", "export", "pdf", "--output", pdf, "--layers", ",".join(layers),
                "--exclude-value"]
        if mirror:
            args.append("--mirror")
        kicad_cli.run_kicad_cli(args + [pcb_path])
        page_w, _page_h = _pdf_page_mm(pdf)
        ppm = dpi / 25.4
        xmin, ymin, xmax, ymax = bounds
        ox, oy = coords.KICAD_ORIGIN_MM
        if mirror:                               # kicad-cli mirrors about the page centre line
            left, right = page_w - (ox + xmax), page_w - (ox + xmin)
            origin_x = page_w - ox
        else:
            left, right = ox + xmin, ox + xmax
            origin_x = ox
        top, bottom = oy - ymax, oy - ymin
        x0 = int(math.floor((left - margin) * ppm))
        y0 = int(math.floor((top - margin) * ppm))
        width = int(math.ceil((right + margin) * ppm)) - x0
        height = int(math.ceil((bottom + margin) * ppm)) - y0
        if x0 < 0 or y0 < 0:
            raise OutputError("the board does not fit the plot page (crop origin %d, %d)"
                              % (x0, y0))
        prefix = os.path.splitext(png_path)[0]
        proc = subprocess.run(["pdftoppm", "-png", "-r", str(int(dpi)), "-singlefile",
                               "-x", str(x0), "-y", str(y0), "-W", str(width), "-H",
                               str(height), pdf, prefix], capture_output=True, text=True)
        if proc.returncode != 0 or not os.path.exists(prefix + ".png"):
            raise OutputError("pdftoppm failed: %s" % proc.stderr.strip())
        if prefix + ".png" != png_path:
            os.replace(prefix + ".png", png_path)
    return {"file": os.path.basename(png_path), "layers": layers, "mirrored": bool(mirror),
            "dpi": int(dpi), "px_per_mm": round(ppm, 6), "size_px": [width, height],
            "origin_px": [round(origin_x * ppm - x0, 3), round(oy * ppm - y0, 3)],
            "x_sign": -1 if mirror else 1}


def render_board(design: Design, pcb_path: str, out_dir: str, *, dpi: int = 600
                 ) -> Dict[str, Dict[str, Any]]:
    """Top, bottom and inner-layer pictures of the board as SVG and PNG.

    ``<name>-top``       F.Cu + silkscreen + outline, seen from above
    ``<name>-bottom``    B.Cu + silkscreen + outline, seen from BELOW (mirrored)
    ``<name>-<layer>``   every inner copper layer with the outline, seen from above

    The PNGs also show the fabrication layer (part outlines and references);
    the SVGs are copper, silkscreen and outline only.  Returns, per view, the
    pixel mapping of :func:`render_view` plus the SVG file name."""
    os.makedirs(out_dir, exist_ok=True)
    bounds = edge_bounds(design)
    views: List[Tuple[str, List[str], List[str], bool, str]] = [
        ("top", ["F.Cu", "F.SilkS", "Edge.Cuts"], ["F.Cu", "F.Fab", "F.SilkS", "Edge.Cuts"],
         False, "top side seen from above"),
        ("bottom", ["B.Cu", "B.SilkS", "Edge.Cuts"], ["B.Cu", "B.Fab", "B.SilkS", "Edge.Cuts"],
         True, "bottom side seen from below (mirrored)"),
    ]
    for layer in design.copper_layers[1:-1]:
        views.append((layer.replace(".", "_"), [layer, "Edge.Cuts"], [layer, "Edge.Cuts"],
                      False, "%s seen from above" % layer))
    out: Dict[str, Dict[str, Any]] = {}
    for name, svg_layers, png_layers, mirror, what in views:
        base = os.path.join(out_dir, "%s-%s" % (design.name, name))
        kicad_cli.export_svg(pcb_path, base + ".svg", svg_layers, mirror=mirror)
        info = render_view(pcb_path, base + ".png", png_layers, bounds, mirror=mirror, dpi=dpi)
        info.update({"svg": os.path.basename(base + ".svg"), "view": what})
        out[name] = info
    _dump_json(out, os.path.join(out_dir, "renders.json"))
    return out


# --------------------------------------------------------------------------
# fab README, zip, manifest
# --------------------------------------------------------------------------

def _mil(mm: float) -> float:
    return mm / 0.0254


def fab_readme(design: Design, drill_tables: Dict[str, List[Tuple[float, int]]],
               files: Sequence[Tuple[str, str]], drc_line: str, clean: bool) -> str:
    """Text of ``fab/README.txt``: what the fab needs to quote and build."""
    r = design.rules
    m = design.board_minimums()
    xmin, ymin, xmax, ymax = edge_bounds(design)
    out: List[str] = []
    title = "%s - bare board fabrication data" % design.title
    out += [title, "=" * len(title), ""]
    if not clean:
        out += ["*** NOT CLEAN - DO NOT FABRICATE: the board these files were plotted from "
                "did not pass KiCad DRC. ***", ""]
    out += ["Design:    %s    revision %s%s" % (design.name, design.revision,
                                               "    %s" % design.company if design.company
                                               else ""),
            "Generated: by the gleda toolchain with KiCad 7 (kicad-cli) from the design "
            "script.",
            "DRC:       %s" % drc_line, ""]
    out += ["BOARD", "-----",
            "Copper layers:       %d" % design.layers,
            "Finished thickness:  %.2f mm" % design.board_thickness,
            "Surface finish:      %s" % design.stackup.finish,
            "Size:                %.2f x %.2f mm (see %s)" % (
                xmax - xmin, ymax - ymin, gerber_name(design.name, "Edge.Cuts")),
            "Outline:             routed; every closed contour on Edge.Cuts inside the "
            "outline is a routed cut-out / non-plated slot",
            "Vias:                through vias only (no blind, buried or micro vias)",
            "Via tenting:         %s" % {
                "both": "tented (covered by solder mask) on both sides",
                "bottom": "tented on the BOTTOM side; open (mask opening) on the top side",
                "top": "tented on the TOP side; open (mask opening) on the bottom side",
                "none": "not tented: mask openings on both sides"}[design.via_tenting],
            ""]
    out += ["STACK-UP (top to bottom)", "------------------------",
            "%-16s %-9s %10s  %s" % ("layer", "type", "thickness", "material")]
    for layer in design.stackup.layers:
        if layer.kind in ("silk", "paste"):
            continue
        material = layer.material
        if layer.epsilon_r:
            material += " (er %.2f)" % layer.epsilon_r
        out.append("%-16s %-9s %7.4f mm  %s" % (layer.name, layer.kind, layer.thickness,
                                                 material))
    out += ["%-16s %-9s %7.4f mm" % ("total", "", design.stackup.thickness), ""]
    out += ["BOARD-LEVEL MINIMUMS (the smallest features on this board)",
            "----------------------------------------------------------",
            "Rule set:                   %s" % r.name,
            "Minimum track width:        %.3f mm (%.1f mil)" % (m["min_track"],
                                                                 _mil(m["min_track"])),
            "Minimum copper clearance:   %.3f mm (%.1f mil)" % (m["min_clearance"],
                                                                 _mil(m["min_clearance"])),
            "Smallest track in use:      %.3f mm" % m["smallest_track_in_use"],
            "Smallest clearance in use:  %.3f mm" % m["smallest_clearance_in_use"],
            "Via pad / drill:            %.3f / %.3f mm (finished hole)" % (
                m["via_diameter"], m["via_drill"]),
            "Minimum annular ring:       %.3f mm" % m["min_annular"],
            "Minimum drill:              %.3f mm" % m["min_drill"],
            "Hole to hole (wall-wall):   %.3f mm" % m["hole_to_hole"],
            "Hole to copper:             %.3f mm" % m["hole_clearance"],
            "Copper to board edge:       %.3f mm" % m["copper_to_edge"],
            "Zone (plane) clearance:     %.3f mm" % r.zone_clearance, ""]
    out += ["NET CLASSES (track width / clearance as routed)",
            "-----------------------------------------------",
            "%-12s %9s %9s %9s  %s" % ("class", "track", "min track", "clearance", "nets")]
    for name in ["Default"] + sorted(n for n in m["net_classes"] if n != "Default"):
        nc = m["net_classes"][name]
        out.append("%-12s %6.3f mm %6.3f mm %6.3f mm  %d" % (
            name, nc["track_width"], nc["min_track_width"], nc["clearance"], len(nc["nets"])))
    fine = [n for n, nc in m["net_classes"].items()
            if nc["nets"] and (nc["min_track_width"] < r.default_track - 1e-9
                               or nc["clearance"] < r.default_clearance - 1e-9)]
    if fine:
        out.append("Classes below the standard %.3f / %.3f mm (%s) are used only where a "
                   "fine-pitch package needs them." % (r.default_track, r.default_clearance,
                                                       ", ".join(sorted(fine))))
    out.append("")
    out += ["PLANES", "------"]
    for plane in design.planes:
        out.append("%-8s %s%s" % (plane.layer, plane.net,
                                  " (whole board)" if plane.shape is None else "")
                   + (", shared with signal tracks" if plane.routable else ""))
    if not design.planes:
        out.append("none")
    out.append("")
    out += ["DRILLS", "------"]
    for fname in sorted(drill_tables):
        table = drill_tables[fname]
        out.append("%s: %d hole(s)" % (fname, sum(n for _d, n in table)))
        for dia, n in table:
            out.append("    %6.3f mm  x %d" % (dia, n))
    for hole in design.outline.holes:
        out.append("Non-plated hole %s: %.3f mm at (%.3f, %.3f)" % (
            hole.name or "", hole.drill, hole.x, hole.y))
    internal, _notches = geometry.classify_cutouts(design.outline)
    for shape in design.outline.cutouts:
        pts = [p for el in geometry.shape_path(shape) for p in _element_points(el)]
        bx0, by0 = min(p[0] for p in pts), min(p[1] for p in pts)
        bx1, by1 = max(p[0] for p in pts), max(p[1] for p in pts)
        inside = any(shape is s for s in internal)
        if type(shape).__name__ == "Slot" and inside:
            length = math.hypot(shape.x2 - shape.x1, shape.y2 - shape.y1) + shape.width
            out.append("Routed non-plated slot on Edge.Cuts: %.3f x %.3f mm centred on "
                       "(%.3f, %.3f)" % (shape.width, length, (shape.x1 + shape.x2) / 2.0,
                                         (shape.y1 + shape.y2) / 2.0))
        else:
            out.append("%s on Edge.Cuts: %s, %.3f x %.3f mm centred on (%.3f, %.3f)" % (
                "Routed cut-out" if inside else "Edge notch", type(shape).__name__,
                bx1 - bx0, by1 - by0, (bx0 + bx1) / 2.0, (by0 + by1) / 2.0))
    out.append("")
    out += ["COORDINATES", "-----------",
            "All Gerber and drill files share one origin: the centre of the board.",
            "Units mm, X to the right and Y up, seen from the top side.", ""]
    out += ["FILES", "-----"]
    width = max(len(f) for f, _w in files)
    for fname, what in files:
        out.append("%-*s  %s" % (width, fname, what))
    out.append("")
    return "\n".join(out)


def write_zip(directory: str, zip_path: str) -> str:
    """Zip a directory with sorted members and fixed time stamps."""
    names = []
    for root, _dirs, files in os.walk(directory):
        for fn in files:
            full = os.path.join(root, fn)
            names.append(os.path.relpath(full, directory).replace(os.sep, "/"))
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in sorted(names):
            info = zipfile.ZipInfo(rel, date_time=ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(os.path.join(directory, rel), "rb") as fh:
                zf.writestr(info, fh.read(), compresslevel=9)
    return zip_path


def file_manifest(out_dir: str, paths: Iterable[str]) -> List[Dict[str, Any]]:
    """[{"path", "bytes", "sha256"}] for the given files, relative to ``out_dir``."""
    out = []
    for path in sorted(set(paths)):
        with open(path, "rb") as fh:
            data = fh.read()
        out.append({"path": os.path.relpath(path, out_dir).replace(os.sep, "/"),
                    "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    return out


# --------------------------------------------------------------------------
# verification against the design model
# --------------------------------------------------------------------------

def _key(x: float, y: float) -> Tuple[int, int]:
    return (int(round(x * 1000)), int(round(y * 1000)))


def _near(points: Set[Tuple[int, int]], x: float, y: float) -> bool:
    kx, ky = _key(x, y)
    return any((kx + dx, ky + dy) in points for dx in (-1, 0, 1) for dy in (-1, 0, 1))


def expected_drills(design: Design, vias: Sequence[Via]
                    ) -> Tuple[List[Tuple[float, float, float]], List[Tuple[float, float, float]]]:
    """(plated, non-plated) round holes the model predicts: (diameter, x, y).
    Plated = vias + through-hole pads; non-plated = outline holes + NPTH pads."""
    plated = [(v.drill, v.x, v.y) for v in vias]
    npth = [(h.drill, h.x, h.y) for h in design.outline.holes]
    for pad in geometry.placed_pads(design):
        if pad.kind == "npth":
            npth.append((pad.drill, pad.x, pad.y))
        elif pad.drill > 0:
            plated.append((pad.drill, pad.x, pad.y))
    return plated, npth


def _compare_holes(name: str, want: Sequence[Tuple[float, float, float]],
                   got: Sequence[Tuple[float, float, float]]) -> List[str]:
    problems: List[str] = []
    got_keys = {(int(round(d * 1000)),) + _key(x, y) for d, x, y in got}
    want_keys = {(int(round(d * 1000)),) + _key(x, y) for d, x, y in want}
    if len(got) != len(got_keys):
        problems.append("%s: the same hole is drilled twice" % name)
    for d, x, y in want:
        dk = int(round(d * 1000))
        kx, ky = _key(x, y)
        if not any((dk, kx + dx, ky + dy) in got_keys for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
            problems.append("%s: no %.3f mm hole at (%.3f, %.3f)" % (name, d, x, y))
    for d, x, y in got:
        dk = int(round(d * 1000))
        kx, ky = _key(x, y)
        if not any((dk, kx + dx, ky + dy) in want_keys
                   for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
            problems.append("%s: unexpected %.3f mm hole at (%.3f, %.3f)" % (name, d, x, y))
    return problems


def verify_outputs(design: Design, fab_dir: str, vias: Sequence[Via],
                   pos_rows: Optional[Sequence[Dict[str, Any]]] = None,
                   groups: Optional[Sequence[Dict[str, Any]]] = None) -> List[str]:
    """Check the written fabrication data against the design model.

    * every layer of the fabrication set has a non-empty Gerber with the
      right file function;
    * the Edge.Cuts extents equal the board edge's exact bounding box (origin
      at the board centre, +y up - for a D-shaped board the flat is at max y)
      and every vertex of the outer boundary, of each cut-out and of each
      routed slot is drawn;
    * every pad of the model on F.Cu / B.Cu is a flash at the same place in
      that layer's Gerber (proves placement, rotation and bottom mirroring);
    * the drill files contain exactly the model's holes: vias and
      through-hole pads plated, outline holes and NPTH pads non-plated;
    * pick-and-place rows and BOM quantities agree with the model.

    Returns a list of problems (empty = everything agrees)."""
    problems: List[str] = []
    name = design.name
    copper = list(design.copper_layers)
    pads = geometry.placed_pads(design)
    gerbers: Dict[str, GerberData] = {}
    for layer in fab_layers(design):
        path = os.path.join(fab_dir, gerber_name(name, layer))
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            problems.append("missing Gerber for %s" % layer)
            continue
        try:
            gerbers[layer] = read_gerber(path)
        except OutputError as exc:
            problems.append(str(exc))
            continue
        ff = gerbers[layer].file_function
        if layer in copper:
            pos = copper.index(layer) + 1
            where = "Top" if pos == 1 else ("Bot" if pos == len(copper) else "Inr")
            want = "Copper,L%d,%s" % (pos, where)
            if ff != want:
                problems.append("%s: file function %r, expected %r" % (layer, ff, want))
            expected = bool(vias) or any(pl.layer == layer for pl in design.planes) \
                or any(layer in p.layers for p in pads)
            if expected and not gerbers[layer].flashes and not gerbers[layer].draws \
                    and not gerbers[layer].regions:
                problems.append("%s: the copper layer is empty, but the design has a plane, "
                                "pads or vias on it" % layer)
        elif layer == "Edge.Cuts" and not ff.startswith("Profile"):
            problems.append("Edge.Cuts: file function %r, expected Profile" % ff)
    edge = gerbers.get("Edge.Cuts")
    if edge is not None:
        want_b = edge_bounds(design)
        if edge.bounds is None:
            problems.append("Edge.Cuts: nothing drawn")
        else:
            for label, got_v, want_v in zip(("xmin", "ymin", "xmax", "ymax"), edge.bounds,
                                            want_b):
                if abs(got_v - want_v) > EDGE_TOLERANCE:
                    problems.append("Edge.Cuts %s is %.4f in the Gerber, %.4f in the design"
                                    % (label, got_v, want_v))
            drawn = {_key(x, y) for x, y in edge.vertices}
            for n, contour in enumerate(edge_contours(design)):
                what = "outer boundary" if n == 0 else "cut-out %d" % n
                for el in contour:
                    if isinstance(el, geometry.FullCircle):
                        (cx, cy), r = el.center, el.radius
                        if not any(abs(math.hypot(x - cx, y - cy) - r) < EDGE_TOLERANCE
                                   for x, y in edge.vertices):
                            problems.append("Edge.Cuts: circle r %.3f at (%.3f, %.3f) of the "
                                            "%s is not in the Gerber" % (r, cx, cy, what))
                    elif not _near(drawn, el.start[0], el.start[1]):
                        problems.append("Edge.Cuts: vertex (%.3f, %.3f) of the %s is not in "
                                        "the Gerber" % (el.start[0], el.start[1], what))
    for layer in (copper[0], copper[-1]):
        g = gerbers.get(layer)
        if g is None:
            continue
        flashes = {_key(x, y) for x, y in g.flashes}
        missing = [p for p in pads if layer in p.layers and p.kind != "npth"
                   and not _near(flashes, p.x, p.y)]
        for p in missing[:10]:
            problems.append("%s: pad %s at (%.3f, %.3f) is not flashed in the Gerber" % (
                layer, p.key, p.x, p.y))
        if len(missing) > 10:
            problems.append("%s: %d more pads are not flashed" % (layer, len(missing) - 10))
    want_pth, want_npth = expected_drills(design, vias)
    for suffix, want in (("-PTH.drl", want_pth), ("-NPTH.drl", want_npth)):
        path = os.path.join(fab_dir, name + suffix)
        if not os.path.exists(path):
            if want:
                problems.append("missing drill file %s" % os.path.basename(path))
            continue
        try:
            drill = read_excellon(path)
        except OutputError as exc:
            problems.append(str(exc))
            continue
        if drill.plated is not (suffix == "-PTH.drl"):
            problems.append("%s: wrong plating attribute" % os.path.basename(path))
        # a drilled slot (oval pad hole) must sit on a hole of the model; the
        # model knows one diameter per pad, so only the position is compared
        want = list(want)
        for _dia, x1, y1, x2, y2 in drill.slots:
            cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
            at = [h for h in want if abs(h[1] - cx) < 0.002 and abs(h[2] - cy) < 0.002]
            if not at:
                problems.append("%s: drilled slot at (%.3f, %.3f) where the design has no "
                                "hole" % (os.path.basename(path), cx, cy))
            for h in at:
                want.remove(h)
        problems += _compare_holes(os.path.basename(path), want, drill.hits)
        for dia, _x, _y in drill.hits:
            if dia < design.rules.min_drill - 1e-9:
                problems.append("%s: %.3f mm hole is below the minimum drill %.3f mm" % (
                    os.path.basename(path), dia, design.rules.min_drill))
                break
    if pos_rows is not None:
        problems += check_positions(design, pos_rows)
    if groups is not None:
        refs = [ref for g in groups for ref in g["refs"]]
        want_refs = [p.ref for p in design.parts if p.in_bom]
        if sorted(refs) != sorted(want_refs):
            problems.append("BOM references differ from the design's BOM parts")
        if sum(g["qty"] for g in groups) != len(want_refs):
            problems.append("BOM quantities do not add up to the number of BOM parts")
    return problems


# --------------------------------------------------------------------------
# the whole package
# --------------------------------------------------------------------------

@dataclass
class OutputSet:
    """What :func:`generate_outputs` wrote and found."""
    directory: str
    fab_dir: str
    fab_zip: str
    files: List[Dict[str, Any]]                  # manifest entries
    problems: List[str]
    drc_clean: bool
    drc_line: str
    drill_tables: Dict[str, List[Tuple[float, int]]]
    bom: Dict[str, Any]
    renders: Dict[str, Dict[str, Any]]
    position_rows: int

    @property
    def ok(self) -> bool:
        return self.drc_clean and not self.problems

    def to_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "drc_clean": self.drc_clean, "drc": self.drc_line,
                "problems": list(self.problems), "files": list(self.files),
                "drill_tables": {k: [[d, n] for d, n in v]
                                 for k, v in self.drill_tables.items()},
                "bom": dict(self.bom), "position_rows": self.position_rows,
                "renders": self.renders}


def _zones_unfilled(pcb_path: str) -> List[str]:
    from . import board
    return [z["net"] or z["name"] for z in board.board_summary(pcb_path)["zones"]
            if not z["rule_area"] and not z["filled"]]


def generate_outputs(design: Design, pcb_path: str, out_dir: str, *, drc_result=None,
                     vias: Optional[Sequence[Via]] = None, require_clean: bool = True,
                     renders: bool = True, step: bool = True, dpi: int = 600) -> OutputSet:
    """Write the complete output set of a routed board (see the module text).

    ``drc_result``     the :class:`gleda.drc.DrcResult` of ``pcb_path``; if None
                       KiCad's DRC is run here (zones are refilled and saved)
    ``vias``           the router's vias for the drill check (default: read
                       back from the board file)
    ``require_clean``  raise :class:`OutputError` instead of plotting a board
                       that fails DRC or has unfilled zones
    ``renders``        also write the pictures (``renders/``)
    ``step``           also write the bare-board STEP solid

    The returned :class:`OutputSet` lists every file and the result of
    :func:`verify_outputs`; ``OutputSet.ok`` is True only for a DRC-clean
    board whose outputs agree with the model."""
    from . import board, drc
    pcb_path = os.path.abspath(pcb_path)
    out_dir = os.path.abspath(out_dir)
    if not os.path.exists(pcb_path):
        raise OutputError("board file not found: %s" % pcb_path)
    if drc_result is None:
        drc_result = drc.run_drc(pcb_path)
    clean = drc_result.is_clean()
    drc_line = "KiCad DRC %d error(s), %d unconnected, %d warning(s)%s" % (
        drc_result.error_count, drc_result.unconnected_count, drc_result.warning_count,
        "" if clean else "  ** NOT CLEAN **")
    if drc_result.warnings_by_type:
        drc_line += " (%s)" % ", ".join("%s %d" % kv for kv in
                                        sorted(drc_result.warnings_by_type.items()))
    unfilled = _zones_unfilled(pcb_path)
    if unfilled:
        clean = False
        drc_line += "; zones not filled: %s" % ", ".join(unfilled)
    if not clean and require_clean:
        raise OutputError("refusing to write fabrication data for a board that is not "
                          "clean: %s" % drc_line)
    os.makedirs(out_dir, exist_ok=True)
    fab_dir = os.path.join(out_dir, "fab")
    asm_dir = os.path.join(out_dir, "assembly")
    for stale in (fab_dir, asm_dir):
        if os.path.isdir(stale):
            shutil.rmtree(stale)
    written: List[str] = []
    gerbers = export_gerbers(pcb_path, fab_dir, fab_layers(design))
    drills = export_drill(pcb_path, fab_dir)
    written += gerbers + drills
    drill_tables = {os.path.basename(p): read_excellon(p).table()
                    for p in drills if p.endswith(".drl")}
    listing: List[Tuple[str, str]] = []
    for layer in fab_layers(design):
        if layer in design.copper_layers:
            n = design.copper_layers.index(layer) + 1
            plane = design.full_plane_layers().get(layer)
            what = LAYER_PURPOSE.get(layer, "copper, inner layer %d" % n)
            if layer not in LAYER_PURPOSE:
                what = "copper, inner (layer %d)" % n
            if layer == design.copper_layers[-1]:
                what = "copper, bottom (layer %d)" % n
            if plane:
                what += ", %s plane" % plane
        else:
            what = LAYER_PURPOSE[layer]
        listing.append((gerber_name(design.name, layer), what))
    for p in gerbers:
        if p.endswith(".gbrjob"):
            listing.append((os.path.basename(p), "Gerber job file (stack-up, rules, file list)"))
    for p in drills:
        base = os.path.basename(p)
        plated = "plated" if "-PTH" in base else "non-plated"
        listing.append((base, "%s holes, Excellon, mm" % plated if base.endswith(".drl")
                        else "drill map of the %s holes (Gerber X2)" % plated))
    listing.append(("README.txt", "this file"))
    readme = os.path.join(fab_dir, "README.txt")
    with open(readme, "w", encoding="utf-8") as fh:
        fh.write(fab_readme(design, drill_tables, listing, drc_line, clean))
    written.append(readme)
    fab_zip = write_zip(fab_dir, os.path.join(out_dir, design.name + "-fab.zip"))
    written.append(fab_zip)

    pos_path = os.path.join(asm_dir, design.name + "-pos.csv")
    pos_rows = export_positions(design, pcb_path, pos_path)
    bom_path = os.path.join(asm_dir, design.name + "-bom.csv")
    groups = write_bom(design, bom_path)
    written += [pos_path, bom_path]
    written.append(_dump_json(netlist_data(design),
                              os.path.join(out_dir, design.name + "-netlist.json")))
    written.append(_dump_json(mechanical_data(design),
                              os.path.join(out_dir, design.name + "-mechanical.json")))
    render_info: Dict[str, Dict[str, Any]] = {}
    if renders:
        rdir = os.path.join(out_dir, "renders")
        if os.path.isdir(rdir):
            shutil.rmtree(rdir)
        render_info = render_board(design, pcb_path, rdir, dpi=dpi)
        written += [os.path.join(rdir, fn) for fn in sorted(os.listdir(rdir))]
    if vias is None:
        _tracks, vias = board.read_routing(pcb_path)
    problems = verify_outputs(design, fab_dir, vias, pos_rows, groups)
    if step:
        step_path = export_board_step(pcb_path,
                                      os.path.join(out_dir, design.name + "-board.step"))
        written.append(step_path)
        problems += check_step(design, step_path)
    result = OutputSet(out_dir, fab_dir, fab_zip, file_manifest(out_dir, written), problems,
                       clean, drc_line, drill_tables, bom_totals(groups), render_info,
                       len(pos_rows))
    _dump_json(result.to_dict(), os.path.join(out_dir, "outputs.json"))
    return result


def build_demo_stage(design: Design, out_dir: str, ctx: Dict[str, Any]
                     ) -> Tuple[bool, Dict[str, Any]]:
    """Stage ``outputs`` of ``demo/build_demo.py``.  Uses the board, DRC result
    and routing of the earlier stages when they ran in this process; run on
    its own it takes ``<out_dir>/<name>.kicad_pcb`` and runs KiCad's DRC on it
    first.  Passes only for a DRC-clean board whose outputs verify."""
    def say(msg: str) -> None:
        print("  " + msg, flush=True)

    files = ctx.get("files")
    pcb = files.pcb if files is not None else os.path.join(out_dir, design.name + ".kicad_pcb")
    if not os.path.exists(pcb):
        say("no board file %s: run the board, route and drc stages first" % pcb)
        return False, {"error": "board file missing"}
    route = ctx.get("route")
    try:
        result = generate_outputs(design, pcb, out_dir, drc_result=ctx.get("drc"),
                                  vias=route.vias if route is not None else None)
    except OutputError as exc:
        say(str(exc))
        return False, {"error": str(exc)}
    say(result.drc_line)
    say("%d files, fab package %s (%d bytes)" % (
        len(result.files), os.path.basename(result.fab_zip), os.path.getsize(result.fab_zip)))
    for fname in sorted(result.drill_tables):
        say("%s: %s" % (fname, ", ".join("%d x %.3f mm" % (n, d)
                                         for d, n in result.drill_tables[fname]) or "empty"))
    say("BOM: %(lines)d lines, %(parts_fitted)d parts fitted, %(cost_per_board).2f per board"
        % result.bom + ("" if not result.bom["unpriced_refs"] else
                        " (%d parts without a price)" % len(result.bom["unpriced_refs"])))
    say("pick-and-place: %d rows agree with the design" % result.position_rows)
    for problem in result.problems[:20]:
        say("PROBLEM " + problem)
    if not result.problems:
        say("outputs verified against the design model: outline extents, pad flashes on "
            "both sides, every drill hit")
    info = {"files": len(result.files), "problems": list(result.problems),
            "drc_clean": result.drc_clean, "bom": dict(result.bom),
            "position_rows": result.position_rows,
            "drill_tables": {k: [[d, n] for d, n in v]
                             for k, v in result.drill_tables.items()},
            "fab_zip": os.path.basename(result.fab_zip),
            "fab_zip_bytes": os.path.getsize(result.fab_zip)}
    return result.ok, info


__all__ = [
    "OutputError", "OutputSet", "GerberData", "DrillData", "generate_outputs",
    "export_gerbers", "export_drill", "export_positions", "check_positions", "bom_groups",
    "bom_totals", "write_bom", "netlist_data", "mechanical_data", "render_view",
    "render_board", "fab_readme", "write_zip", "file_manifest", "read_gerber",
    "read_excellon", "expected_drills", "verify_outputs", "strip_dates", "gerber_name",
    "export_board_step", "step_extents", "check_step",
    "fab_layers", "placed_refs", "edge_bounds", "edge_contours", "build_demo_stage",
    "FAB_TECH_LAYERS", "POS_COLUMNS",
    "BOM_COLUMNS",
]
