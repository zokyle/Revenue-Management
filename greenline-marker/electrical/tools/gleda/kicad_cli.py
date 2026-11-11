"""Thin wrappers around ``kicad-cli`` (KiCad 7) used by several modules.

Only the pieces the core needs live here (running the tool, SVG export with
an explicit layer list, a tiny SVG reader for orientation checks); the full
fabrication output set is produced by :mod:`gleda.outputs`.

kicad-cli gotchas handled here

* exports must always be given an explicit ``--layers`` list;
* the SVG title contains the export time - it is replaced by a fixed title so
  that re-runs diff cleanly.
"""
from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
from typing import Dict, Iterable, List, Sequence, Tuple


class KicadCliError(Exception):
    """kicad-cli is missing or returned an error."""


def kicad_cli_path() -> str:
    path = os.environ.get("KICAD_CLI") or shutil.which("kicad-cli")
    if not path:
        raise KicadCliError("kicad-cli not found (set KICAD_CLI)")
    return path


def run_kicad_cli(args: Sequence[str], timeout: float = 600.0) -> subprocess.CompletedProcess:
    """Run ``kicad-cli <args>``; raises :class:`KicadCliError` on failure."""
    cmd = [kicad_cli_path()] + list(args)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise KicadCliError("kicad-cli timed out: %s" % " ".join(cmd))
    if proc.returncode != 0:
        raise KicadCliError("kicad-cli failed (%d): %s\n%s\n%s" % (
            proc.returncode, " ".join(cmd), proc.stdout[-2000:], proc.stderr[-2000:]))
    return proc


def export_svg(pcb_path: str, svg_path: str, layers: Iterable[str], *, mirror: bool = False,
               board_area_only: bool = True, black_and_white: bool = False) -> str:
    """Plot the given layers of a board into one SVG.

    The view is always from the TOP of the board (KiCad's canvas view), so a
    part placed at +y appears toward the top of the image; ``mirror`` flips
    left/right to show the bottom side as seen from below.
    """
    layers = list(layers)
    if not layers:
        raise ValueError("export_svg needs an explicit layer list")
    args = ["pcb", "export", "svg", "--output", svg_path, "--layers", ",".join(layers),
            "--exclude-drawing-sheet", "--page-size-mode", "2" if board_area_only else "1"]
    if mirror:
        args.append("--mirror")
    if black_and_white:
        args.append("--black-and-white")
    args.append(pcb_path)
    run_kicad_cli(args)
    if not os.path.exists(svg_path):
        raise KicadCliError("kicad-cli did not create %s" % svg_path)
    with open(svg_path, encoding="utf-8") as fh:
        text = fh.read()
    fixed = re.sub(r"<title>.*?</title>",
                   "<title>%s</title>" % os.path.basename(svg_path), text, count=1, flags=re.S)
    if fixed != text:
        with open(svg_path, "w", encoding="utf-8") as fh:
            fh.write(fixed)
    return svg_path


_NUM = r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"


def svg_viewbox(svg_text: str) -> Tuple[float, float, float, float]:
    """(min_x, min_y, width, height) of an SVG's viewBox (user units = mm for
    KiCad plots)."""
    m = re.search(r'viewBox="\s*(%s)\s+(%s)\s+(%s)\s+(%s)\s*"' % (_NUM, _NUM, _NUM, _NUM),
                  svg_text)
    if not m:
        raise ValueError("SVG has no viewBox")
    return tuple(float(g) for g in m.groups())          # type: ignore[return-value]


def _arc_points(x0: float, y0: float, rx: float, ry: float, phi_deg: float,
                large: bool, sweep: bool, x1: float, y1: float, n: int = 24
                ) -> List[Tuple[float, float]]:
    """Points along an SVG elliptical arc (endpoint parameterisation)."""
    if rx == 0 or ry == 0 or (x0 == x1 and y0 == y1):
        return [(x1, y1)]
    phi = math.radians(phi_deg)
    cp, sp = math.cos(phi), math.sin(phi)
    dx, dy = (x0 - x1) / 2.0, (y0 - y1) / 2.0
    xp, yp = cp * dx + sp * dy, -sp * dx + cp * dy
    rx, ry = abs(rx), abs(ry)
    lam = (xp * xp) / (rx * rx) + (yp * yp) / (ry * ry)
    if lam > 1:
        k = math.sqrt(lam)
        rx, ry = rx * k, ry * k
    num = rx * rx * ry * ry - rx * rx * yp * yp - ry * ry * xp * xp
    den = rx * rx * yp * yp + ry * ry * xp * xp
    coef = math.sqrt(max(0.0, num / den)) if den else 0.0
    if large == sweep:
        coef = -coef
    cxp, cyp = coef * rx * yp / ry, -coef * ry * xp / rx
    cx = cp * cxp - sp * cyp + (x0 + x1) / 2.0
    cy = sp * cxp + cp * cyp + (y0 + y1) / 2.0
    a0 = math.atan2((yp - cyp) / ry, (xp - cxp) / rx)
    a1 = math.atan2((-yp - cyp) / ry, (-xp - cxp) / rx)
    da = a1 - a0
    if sweep and da < 0:
        da += 2 * math.pi
    elif not sweep and da > 0:
        da -= 2 * math.pi
    pts = []
    for i in range(1, n + 1):
        a = a0 + da * i / n
        ex, ey = rx * math.cos(a), ry * math.sin(a)
        pts.append((cx + cp * ex - sp * ey, cy + sp * ex + cp * ey))
    return pts


def _path_points(d: str) -> List[Tuple[float, float]]:
    """Vertices of an SVG path made of absolute M/L/H/V/A/C/Z commands (the
    subset KiCad writes); arcs are sampled, Bezier control points are used
    as a conservative hull."""
    tokens = re.findall(r"[MLHVACZmlhvacz]|%s" % _NUM, d)
    pts: List[Tuple[float, float]] = []
    cmd = "M"
    i = 0
    x = y = 0.0
    args = {"M": 2, "L": 2, "H": 1, "V": 1, "A": 7, "C": 6, "Z": 0}
    while i < len(tokens):
        tok = tokens[i]
        if tok.isalpha():
            if tok.upper() not in args or tok != tok.upper() and tok.upper() != "Z":
                raise ValueError("unsupported SVG path command %r" % tok)
            cmd = tok.upper()
            i += 1
            if cmd == "Z":
                continue
        n = args[cmd]
        if n == 0:
            i += 1
            continue
        vals = [float(v) for v in tokens[i:i + n]]
        if len(vals) < n:
            break
        i += n
        if cmd in ("M", "L"):
            x, y = vals
            pts.append((x, y))
            if cmd == "M":
                cmd = "L"
        elif cmd == "H":
            x = vals[0]
            pts.append((x, y))
        elif cmd == "V":
            y = vals[0]
            pts.append((x, y))
        elif cmd == "A":
            arc = _arc_points(x, y, vals[0], vals[1], vals[2], bool(vals[3]), bool(vals[4]),
                              vals[5], vals[6])
            pts.extend(arc)
            x, y = vals[5], vals[6]
        elif cmd == "C":
            pts.extend([(vals[0], vals[1]), (vals[2], vals[3]), (vals[4], vals[5])])
            x, y = vals[4], vals[5]
    return pts


_SVG_TOKEN = re.compile(
    r'<g[^>]*?style="[^"]*?(?:fill|stroke):(#[0-9A-Fa-f]{6})[^"]*"'
    r'|<path[^>]*?\sd="([^"]*)"'
    r'|<circle[^>]*?cx="(%s)"[^>]*?cy="(%s)"[^>]*?r="(%s)"'
    r'|<rect[^>]*?x="(%s)"[^>]*?y="(%s)"[^>]*?width="(%s)"[^>]*?height="(%s)"'
    % (_NUM, _NUM, _NUM, _NUM, _NUM, _NUM, _NUM), re.S)


def svg_elements(svg_text: str) -> List[Tuple[str, str, Tuple[float, ...]]]:
    """Flat list of drawn elements of a KiCad SVG plot.

    Each entry is ``(color, kind, data)`` with ``kind`` in ``"path"`` (data =
    flattened x, y vertex list), ``"circle"`` (cx, cy, r) or ``"rect"``
    (x, y, w, h).  ``color`` is the ``#RRGGBB`` of the enclosing group -
    KiCad plots every layer in its own colour.  SVG user units (mm), y DOWN.
    """
    out: List[Tuple[str, str, Tuple[float, ...]]] = []
    color = "#000000"
    for m in _SVG_TOKEN.finditer(svg_text):
        if m.group(1):
            color = m.group(1).upper()
        elif m.group(2) is not None:
            flat: List[float] = []
            for px, py in _path_points(m.group(2)):
                flat += [px, py]
            if flat:
                out.append((color, "path", tuple(flat)))
        elif m.group(3) is not None:
            out.append((color, "circle",
                        (float(m.group(3)), float(m.group(4)), float(m.group(5)))))
        elif m.group(6) is not None:
            out.append((color, "rect", tuple(float(m.group(i)) for i in (6, 7, 8, 9))))
    return out


def svg_color_bboxes(svg_text: str) -> Dict[str, Tuple[float, float, float, float]]:
    """Bounding box of everything drawn in each colour of a KiCad SVG plot:
    ``{"#RRGGBB": (xmin, ymin, xmax, ymax)}`` in SVG user units (y grows
    DOWNWARD in SVG).  A cheap way to locate a layer's graphics for
    orientation tests."""
    boxes: Dict[str, List[float]] = {}

    def grow(color: str, x0: float, y0: float, x1: float, y1: float) -> None:
        b = boxes.get(color)
        if b is None:
            boxes[color] = [x0, y0, x1, y1]
        else:
            b[0], b[1] = min(b[0], x0), min(b[1], y0)
            b[2], b[3] = max(b[2], x1), max(b[3], y1)

    for color, kind, data in svg_elements(svg_text):
        if kind == "path":
            xs, ys = data[0::2], data[1::2]
            grow(color, min(xs), min(ys), max(xs), max(ys))
        elif kind == "circle":
            cx, cy, r = data
            grow(color, cx - r, cy - r, cx + r, cy + r)
        else:
            x, y, w, h = data
            grow(color, x, y, x + w, y + h)
    return {c: tuple(b) for c, b in boxes.items()}       # type: ignore[misc]


__all__ = ["KicadCliError", "kicad_cli_path", "run_kicad_cli", "export_svg",
           "svg_viewbox", "svg_elements", "svg_color_bboxes"]
