"""Fabrication data of the routed FR-4 base plate (GL1-011) in the formats a PCB fabricator's quoting system reads.

    profile   Gerber RS-274X, the board profile: routed outline and the routed cut-outs (round opening, slot)
    mask      Gerber RS-274X, solder mask top and bottom: full coverage with a round opening at each drilled hole
              (hole + MECH['fr4_mask_relief']), so that no mask lies on the hole wall or on its rim
    drill     Excellon, the three non-plated holes

Everything is generated from the typed section edges of the plate SOLID (geom.section_edges), never from typed-in
numbers.  parse_gerber() / parse_excellon() read the text back; check 15 compares what a fabricator's CAM would read
with the solid.  Origin = centre of the outline arc (the marker frame), millimetres, seen on the top (PCB) face.
"""
from __future__ import annotations
import math, re
import params as P
import geom as G

M = P.MECH
DEC = 6                      # decimals of the Gerber coordinate format (4.6, mm)
NAME = "GL1-011_base_plate_FR4"
FILES = {"profile": f"{NAME}-Profile.gbr", "mask_top": f"{NAME}-F_Mask.gbr", "mask_bottom": f"{NAME}-B_Mask.gbr", "drill": f"{NAME}-NPTH.drl"}


def plate_entities(plate):
    """(routed entities, drilled holes [(x, y, dia)]) of the plate at mid thickness.  A full circle no larger than the
    largest drill a fabricator stocks counts as drilled when it has the ball-hole diameter; everything else is routed."""
    bb = plate.BoundingBox()
    ents = G.section_edges(plate, "z", 0.5 * (bb.zmin + bb.zmax))
    drill = [(e[1][0], e[1][1], 2 * e[2]) for e in ents if e[0] == "circle" and abs(2 * e[2] - P.BALL_HOLE_D) < 1e-6]
    rout = [e for e in ents if not (e[0] == "circle" and abs(2 * e[2] - P.BALL_HOLE_D) < 1e-6)]
    return rout, sorted(drill, key=lambda h: (-h[1], h[0]))


def _c(v):
    return "%d" % round(v * 10 ** DEC)


def _head(function, extra=()):
    return ["G04 GreenLine GL-1, GL1-011 base plate, FR-4 0.80 mm, NO COPPER. PROVISIONAL - not released. Rev %s*" % P.REV,
            "G04 Origin = centre of the R%.2f outline arc, +y toward the flat, seen on the top (PCB) face. Units mm.*" % P.BASE_R,
            "%%TF.FileFunction,%s*%%" % function] + list(extra) + ["%TF.Part,Single*%", "%%FSLAX4%dY4%d*%%" % (DEC, DEC), "%MOMM*%", "%LPD*%"]


def gerber_profile(rout):
    out = _head("Profile,NP") + ["%ADD10C,0.050000*%", "D10*", "G75*"]
    for e in rout:
        if e[0] == "line":
            out += ["G01*", f"X{_c(e[1][0])}Y{_c(e[1][1])}D02*", f"X{_c(e[2][0])}Y{_c(e[2][1])}D01*"]
        elif e[0] == "circle":
            (cx, cy), r = e[1], e[2]
            out += ["G01*", f"X{_c(cx + r)}Y{_c(cy)}D02*", "G03*", f"X{_c(cx + r)}Y{_c(cy)}I{_c(-r)}J{_c(0.0)}D01*"]
        elif e[0] == "arc":                                   # counter-clockwise from a0 to a1
            (cx, cy), r, a0, a1 = e[1], e[2], math.radians(e[3]), math.radians(e[4])
            sx, sy = cx + r * math.cos(a0), cy + r * math.sin(a0)
            ex, ey = cx + r * math.cos(a1), cy + r * math.sin(a1)
            out += ["G01*", f"X{_c(sx)}Y{_c(sy)}D02*", "G03*", f"X{_c(ex)}Y{_c(ey)}I{_c(cx - sx)}J{_c(cy - sy)}D01*"]
        else:
            pts = e[1]
            out += ["G01*", f"X{_c(pts[0][0])}Y{_c(pts[0][1])}D02*"] + [f"X{_c(x)}Y{_c(y)}D01*" for x, y in pts[1:]]
    return "\n".join(out + ["M02*"]) + "\n"


def gerber_mask(drill, side):
    """Solder mask, negative polarity (what is drawn is an OPENING): one round opening per drilled hole."""
    d = P.BALL_HOLE_D + M["fr4_mask_relief"]
    out = _head("Soldermask,%s" % ("Top" if side == "top" else "Bot"), ["%TF.FilePolarity,Negative*%"]) + ["%%ADD10C,%.6f*%%" % d, "D10*"]
    out += [f"X{_c(x)}Y{_c(y)}D03*" for x, y, _ in drill]
    return "\n".join(out + ["M02*"]) + "\n"


def excellon(drill):
    dias = sorted({round(d, 4) for _, _, d in drill})
    out = ["M48", "; GreenLine GL-1, GL1-011 base plate FR-4: NON-PLATED holes (NPTH). PROVISIONAL - not released. Rev %s" % P.REV,
           "; origin = centre of the outline arc, absolute, millimetres, decimal point", "FMAT,2", "METRIC,TZ"]
    out += [f"T{i + 1}C{d:.3f}" for i, d in enumerate(dias)] + ["%", "G90", "G05"]
    for i, d in enumerate(dias):
        out += [f"T{i + 1}"] + [f"X{x:.3f}Y{y:.3f}" for x, y, dd in drill if abs(dd - d) < 1e-6]
    return "\n".join(out + ["T0", "M30"]) + "\n"


def generate(plate):
    rout, drill = plate_entities(plate)
    return {"profile": gerber_profile(rout), "mask_top": gerber_mask(drill, "top"), "mask_bottom": gerber_mask(drill, "bottom"), "drill": excellon(drill)}


def write(plate, outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    out = []
    for key, text in generate(plate).items():
        f = outdir / FILES[key]
        f.write_text(text)
        out.append(f)
    return out


# ---------------------------------------------------------------------------------------------- readers (for the check)
def parse_gerber(text):
    """Minimal RS-274X reader for the files written here: returns dict(function, negative, apertures {code: dia},
    segments [('line', p0, p1) | ('arc', centre, r, p0, p1, ccw)], flashes [(x, y, dia)])."""
    fmt = re.search(r"%FSLAX(\d)(\d)Y\d\d\*%", text)
    dec = int(fmt.group(2))
    scale = 10.0 ** -dec
    unit = 1.0 if "%MOMM*%" in text else 25.4
    aps = {int(c): float(d) * unit for c, d in re.findall(r"%ADD(\d+)C,([0-9.]+)\*%", text)}
    func = re.search(r"%TF\.FileFunction,([^*]+)\*%", text)
    res = dict(function=func.group(1) if func else "", negative="FilePolarity,Negative" in text, apertures=aps, segments=[], flashes=[])
    x = y = 0.0
    mode, cur = "G01", None
    for cmd in re.sub(r"%[^%]*%", "", text).replace("\n", "").split("*"):
        cmd = cmd.strip()
        if not cmd or cmd.startswith("G04"):
            continue
        if cmd in ("G01", "G02", "G03"):
            mode = cmd; continue
        if cmd in ("G75", "M02"):
            continue
        m = re.fullmatch(r"D(\d+)", cmd)
        if m and int(m.group(1)) >= 10:
            cur = int(m.group(1)); continue
        m = re.fullmatch(r"(?:X(-?\d+))?(?:Y(-?\d+))?(?:I(-?\d+))?(?:J(-?\d+))?D0([123])", cmd)
        if not m:
            raise ValueError(f"Gerber command not understood: {cmd!r}")
        nx = int(m.group(1)) * scale * unit if m.group(1) is not None else x
        ny = int(m.group(2)) * scale * unit if m.group(2) is not None else y
        op = m.group(5)
        if op == "1":
            if mode == "G01":
                res["segments"].append(("line", (x, y), (nx, ny)))
            else:
                i = int(m.group(3) or 0) * scale * unit; j = int(m.group(4) or 0) * scale * unit
                res["segments"].append(("arc", (x + i, y + j), math.hypot(i, j), (x, y), (nx, ny), mode == "G03"))
        elif op == "3":
            res["flashes"].append((nx, ny, aps[cur]))
        x, y = nx, ny
    return res


def parse_excellon(text):
    """Holes [(x, y, dia)] of an Excellon file with decimal-point coordinates (METRIC)."""
    tools, holes, cur = {}, [], None
    unit = 1.0 if "METRIC" in text else 25.4
    for line in text.splitlines():
        line = line.strip()
        m = re.fullmatch(r"T(\d+)C([0-9.]+)", line)
        if m:
            tools[int(m.group(1))] = float(m.group(2)) * unit; continue
        m = re.fullmatch(r"T(\d+)", line)
        if m:
            cur = int(m.group(1)); continue
        m = re.fullmatch(r"X(-?[0-9.]+)Y(-?[0-9.]+)", line)
        if m and cur in tools:
            holes.append((float(m.group(1)) * unit, float(m.group(2)) * unit, tools[cur]))
    return holes


def profile_polygon(segments, chord_tol=2e-5):
    """The plate a CAM system would build from the parsed profile: shapely polygon with its routed cut-outs (the largest
    face of the linework), arcs sampled to chord_tol."""
    from shapely.geometry import LineString
    from shapely.ops import polygonize, unary_union
    lines = []
    for s in segments:
        if s[0] == "line":
            lines.append(LineString([s[1], s[2]]))
            continue
        _, (cx, cy), r, p0, p1, ccw = s
        a0 = math.atan2(p0[1] - cy, p0[0] - cx)
        a1 = math.atan2(p1[1] - cy, p1[0] - cx)
        sweep = (a1 - a0) % (2 * math.pi) if ccw else -((a0 - a1) % (2 * math.pi))
        if abs(sweep) < 1e-12:
            sweep = 2 * math.pi if ccw else -2 * math.pi
        n = max(8, int(math.ceil(abs(sweep) / (2 * math.acos(max(-1.0, 1 - chord_tol / r))))))
        pts = [(cx + r * math.cos(a0 + sweep * k / n), cy + r * math.sin(a0 + sweep * k / n)) for k in range(n + 1)]
        pts[0], pts[-1] = p0, p1
        lines.append(LineString(pts))
    faces = list(polygonize(unary_union(lines)))
    return max(faces, key=lambda g: g.area) if faces else None
