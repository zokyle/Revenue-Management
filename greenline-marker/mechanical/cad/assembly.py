"""GreenLine GL-1 assembly: named, coloured parts; STEP / STL export.

Public API (used by checks.py, the drawings and the renders):
    build_parts()            -> dict name -> PartInfo (shape is a cadquery Workplane in the assembly frame)
    solid_of(info_or_wp)     -> cadquery Shape (single solid or compound)
    build_assembly(parts)    -> cadquery.Assembly
    export_all(parts)        -> writes export/step, export/stl/parts, export/stl/print, params_resolved.json
    INTENDED_CONTACTS / MODELLING_OVERLAPS -> allow-lists for the interference check
"""
from __future__ import annotations
import pathlib, time
from collections import OrderedDict
from dataclasses import dataclass
import cadquery as cq
import params as P
import parts as PT

STEP_DIR = P.EXPORT_DIR / "step"
STL_PARTS_DIR = P.EXPORT_DIR / "stl" / "parts"
STL_PRINT_DIR = P.EXPORT_DIR / "stl" / "print"
STL_TOL, STL_ANG = 0.02, 0.2                 # part meshes for renders and mesh checks
PRINT_STL_TOL, PRINT_STL_ANG = 0.005, 0.0873   # the three files that go to the bureau: 0.005 mm chord error, 5 deg
PRINTED = ("tub", "base_plate", "cradle")


@dataclass
class PartInfo:
    name: str
    shape: cq.Workplane
    color: tuple            # r, g, b, a  (0..1)
    material: str
    density: float          # g/cm3 (PROVISIONAL typical values, used for the mass estimate)
    group: str              # "puck" or "cradle"
    kind: str               # "printed" | "purchased" | "adhesive" | "reference"
    desc: str = ""


# name: (builder, colour rgba, material, density g/cm3, group, kind, description)
def _catalog():
    PA12 = ("MJF PA12, dyed black, vapor smoothed", 1.01)
    c = OrderedDict()
    c["tub"] = (PT.tub, (0.13, 0.13, 0.14, 1), *PA12, "puck", "printed", "GL1-010 tub (top shell)")
    c["base_plate"] = (PT.base_plate, (0.20, 0.20, 0.22, 1), "MJF PA12, dyed black, NOT vapor smoothed", 1.01, "puck", "printed", "GL1-011 base plate")
    c["main_pcb"] = (PT.main_pcb, (0.05, 0.40, 0.18, 1), "FR-4 + parts (envelope)", 2.2, "puck", "purchased", "main PCB assembly, part boxes from the YAML")
    c["pcb_adhesive"] = (PT.pcb_adhesive, (0.95, 0.85, 0.35, 0.8), "3M 9472LE (300LSE) transfer tape 0.13, die cut (PROVISIONAL)", 1.0, "puck", "adhesive", "die-cut adhesive sheet between PCB and base")
    c["seal_bead"] = (PT.seal_bead, (0.95, 0.55, 0.15, 0.9), "dispensed seal adhesive: 0.33 joint on the land + fill of the radial groove", 1.1, "puck", "adhesive", "perimeter seal")
    for s in ("L", "R"):
        c[f"camera_{s}"] = (lambda s=s: PT.camera(s), (0.25, 0.25, 0.30, 1), "OVM7692-RYAA cube", 2.5, "puck", "purchased", f"camera cube {s}")
        c[f"prism_{s}"] = (lambda s=s: PT.prism(s), (0.55, 0.80, 0.95, 0.55), "N-BK7 prism, Edmund 32-526", 2.51, "puck", "purchased", f"2 mm fold prism {s}")
        c[f"visor_window_{s}"] = (lambda s=s: PT.visor_window(s), (0.60, 0.85, 0.95, 0.40), "EVT: cast acrylic 0.5", 1.19, "puck", "purchased", f"visor window {s}")
        c[f"window_bond_{s}"] = (lambda s=s: PT.window_bond(s), (0.95, 0.85, 0.35, 0.8), "light-cure acrylic, bond line 0.05 (class only)", 1.1, "puck", "adhesive", f"adhesive frame behind visor window {s}")
        c[f"hood_seal_{s}"] = (lambda s=s: PT.hood_seal(s), (0.08, 0.08, 0.09, 1), "black form-in-place gasket bead, silicone-free (class only)", 1.1, "puck", "adhesive", f"light seal above camera cube {s}")
    c["lcd_glass"] = (PT.lcd_glass, (0.70, 0.74, 0.70, 0.9), "Sharp LS013B7DH03 glass", 2.5, "puck", "purchased", "memory LCD")
    c["lcd_flex"] = (PT.lcd_flex, (0.85, 0.55, 0.10, 1), "polyimide FPC (PROVISIONAL shape)", 1.6, "puck", "reference", "LCD flex tail, representative")
    c["lcd_adhesive"] = (PT.lcd_adhesive, (0.95, 0.85, 0.35, 0.8), "PSA frame 0.15", 1.0, "puck", "adhesive", "LCD bonding frame")
    c["cover_glass"] = (PT.cover_glass, (0.75, 0.90, 0.98, 0.35), "mineral glass crystal 28.0 x 1.0", 2.5, "puck", "purchased", "cover glass")
    c["cover_tape"] = (PT.cover_tape, (0.95, 0.85, 0.35, 0.8), "3M VHB 5907 ring 0.2", 0.72, "puck", "adhesive", "cover-glass tape ring")
    c["battery"] = (PT.battery, (0.72, 0.72, 0.76, 1), "LiPo GM201030-PCB", 2.1, "puck", "purchased", "battery body (no swell)")
    c["foam_pad"] = (PT.foam_pad, (0.35, 0.35, 0.35, 0.9), "PU foam 0.3 (e.g. Poron) PROVISIONAL", 0.32, "puck", "purchased", "foam pad under the LCD")
    for i in range(len(P.BALL_XY)):
        c[f"ball_{i + 1}"] = (lambda i=i: PT.ball(i), (0.85, 0.86, 0.90, 1), "stainless ball 1.0 mm", 7.9, "puck", "purchased", f"foot ball {i + 1}")
        c[f"ball_epoxy_{i + 1}"] = (lambda i=i: PT.ball_epoxy(i), (0.55, 0.75, 0.90, 0.9), "dual-cure epoxy: potting + backfill of the sheet hole (PROVISIONAL)", 1.15, "puck", "adhesive", f"potting of foot ball {i + 1}")
    c["vent"] = (PT.vent, (0.95, 0.95, 0.95, 1), "Gore VE80205 ePTFE vent (PROVISIONAL)", 0.9, "puck", "purchased", "adhesive vent")
    c["cradle"] = (PT.cradle, (0.30, 0.32, 0.36, 1), "MJF PA12 (the latch is sized for PA12)", 1.01, "cradle", "printed", "GL1-020 cradle body with lip and latch")
    c["cradle_pcb"] = (PT.cradle_pcb, (0.05, 0.35, 0.50, 1), "FR-4 1.6", 1.85, "cradle", "purchased", "cradle PCB 30 x 22")
    c["usb_receptacle"] = (PT.usb_receptacle, (0.80, 0.80, 0.82, 1), "GCT USB4105 (PROVISIONAL envelope)", 2.0, "cradle", "purchased", "USB-C receptacle")
    return c


def build_parts(only=None, verbose=False):
    out = OrderedDict()
    cat = _catalog()
    for name, (fn, col, mat, rho, group, kind, desc) in cat.items():
        if only and name not in only:
            continue
        t = time.time()
        out[name] = PartInfo(name, fn(), col, mat, rho, group, kind, desc)
        if verbose:
            print(f"  built {name:16s} {time.time() - t:5.1f} s", flush=True)
    if not only or any(n.startswith("spring_pin") for n in only):
        for n, wp in PT.spring_pins().items():
            out[n] = PartInfo(n, wp, (0.85, 0.70, 0.25, 1), "Mill-Max 0914 spring pin (PROVISIONAL)", 8.5, "cradle", "purchased", "spring pin")
    if not only or any(n.startswith("cradle_foot") for n in only):
        for n, wp in PT.cradle_feet().items():
            out[n] = PartInfo(n, wp, (0.10, 0.10, 0.10, 1), "adhesive bumper foot dia 8 x 3 (PROVISIONAL)", 1.1, "cradle", "purchased", "cradle foot")
    return out


def solid_of(obj):
    wp = obj.shape if isinstance(obj, PartInfo) else obj
    v = wp.val()
    return v


def bbox_of(obj):
    """Tight bounding box (xmin, ymin, zmin, xmax, ymax, zmax): OCC optimal box without shape tolerance."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    b = Bnd_Box()
    BRepBndLib.AddOptimal_s(solid_of(obj).wrapped, b, False, False)
    x0, y0, z0, x1, y1, z1 = b.Get()
    return (x0, y0, z0, x1, y1, z1)


def build_assembly(parts, groups=("puck", "cradle")):
    assy = cq.Assembly(name="GL1_assembly")
    for name, info in parts.items():
        if info.group in groups:
            assy.add(info.shape, name=name, color=cq.Color(*info.color))
    return assy


def print_orientation(name, wp):
    """Print-orientation transform for the three printed parts (z = build direction, part resting exactly on z = 0).
    tub: roof down.  base plate: as modelled.  cradle: turned so that its x axis is the build direction - the side
    profile of the latch beam and of the lip then lies in the build plane (bending stress in-plane, not across layers)."""
    if name == "tub":            # roof down: cosmetic top face on the bed side, cavity open upward for depowdering
        wp = wp.rotate((0, 0, 0), (1, 0, 0), 180)
    if name == "cradle":         # model x -> build z
        wp = wp.rotate((0, 0, 0), (0, 1, 0), -90)
    return wp.translate((0, 0, -bbox_of(wp)[2]))


# Pairs that touch by design (zero-volume contact) - documented for the interference report.
INTENDED_CONTACTS = {
    ("tub", "main_pcb"): "support posts land on the PCB top face (posts E round their spigots)",
    ("tub", "seal_bead"): "seal face on the bead",
    ("tub", "lcd_adhesive"): "LCD bonded under the roof ledge",
    ("tub", "cover_tape"): "tape ring on the recess floor",
    ("tub", "vent"): "vent adhered to its pad",
    ("tub", "visor_window_L"): "window bottom edge on the recess shelf",
    ("tub", "visor_window_R"): "window bottom edge on the recess shelf",
    ("tub", "window_bond_L"): "window adhesive on the recess floor", ("tub", "window_bond_R"): "window adhesive on the recess floor",
    ("visor_window_L", "window_bond_L"): "bond", ("visor_window_R", "window_bond_R"): "bond",
    ("tub", "hood_seal_L"): "gasket bead on the hood rear wall", ("tub", "hood_seal_R"): "gasket bead on the hood rear wall",
    ("camera_L", "hood_seal_L"): "cube top beds into the gasket", ("camera_R", "hood_seal_R"): "cube top beds into the gasket",
    ("lcd_flex", "main_pcb"): "tail enters the J1 mouth (modelled up to the mouth face)",
    ("base_plate", "seal_bead"): "bead on the seal land",
    ("base_plate", "pcb_adhesive"): "adhesive sheet on the base top",
    ("main_pcb", "pcb_adhesive"): "adhesive sheet on the PCB underside",
    ("main_pcb", "camera_L"): "soldered", ("main_pcb", "camera_R"): "soldered",
    ("main_pcb", "battery"): "battery on the PCB",
    ("lcd_glass", "lcd_adhesive"): "bond", ("lcd_glass", "foam_pad"): "foam under the glass",
    ("lcd_glass", "lcd_flex"): "tail attached at the rear edge",
    ("cover_glass", "cover_tape"): "bond",
    ("cradle", "cradle_pcb"): "PCB against the pocket ceiling",
    ("cradle_pcb", "usb_receptacle"): "soldered",
}
for _i in range(1, 8):
    INTENDED_CONTACTS[("main_pcb", f"spring_pin_{_i}")] = "plunger tip on the contact pad"
    INTENDED_CONTACTS[("cradle_pcb", f"spring_pin_{_i}")] = "pin soldered into the cradle PCB"
for _i in range(1, 5):
    INTENDED_CONTACTS[("cradle", f"cradle_foot_{_i}")] = "foot in its pocket"
for _i in range(1, 4):
    INTENDED_CONTACTS[(f"ball_{_i}", "cradle")] = "ball foot rests on the nest (front strip / pad)"
    INTENDED_CONTACTS[(f"ball_{_i}", f"ball_epoxy_{_i}")] = "ball potted in epoxy"
    INTENDED_CONTACTS[("base_plate", f"ball_epoxy_{_i}")] = "epoxy fills the through hole and sits on the plate top"
    INTENDED_CONTACTS[("main_pcb", f"ball_epoxy_{_i}")] = "backfill of the sheet hole: the ball bears on the PCB through epoxy"
    INTENDED_CONTACTS[("pcb_adhesive", f"ball_epoxy_{_i}")] = "epoxy fills the 2.0 mm hole of the adhesive sheet"

# Pairs that overlap in VOLUME because of a modelling convention: none in rev C (the adhesive sheet has its own 0.13 mm).
MODELLING_OVERLAPS = {}


def export_all(parts, verbose=True):
    for d in (STEP_DIR, STL_PARTS_DIR, STL_PRINT_DIR):
        d.mkdir(parents=True, exist_ok=True)
        for f in d.glob("*"):
            if f.suffix.lower() in (".step", ".stl"):
                f.unlink()
    P.write_resolved()
    for name, info in parts.items():
        cq.exporters.export(info.shape, str(STEP_DIR / f"{name}.step"))
        solid_of(info).exportStl(str(STL_PARTS_DIR / f"{name}.stl"), STL_TOL, STL_ANG)
    for name in PRINTED:
        if name in parts:
            po = print_orientation(name, parts[name].shape)
            po.val().exportStl(str(STL_PRINT_DIR / f"{name}_print.stl"), PRINT_STL_TOL, PRINT_STL_ANG)
            cq.exporters.export(po, str(STEP_DIR / f"{name}_print.step"))
    build_assembly(parts).save(str(STEP_DIR / "GL1_assembly.step"))
    build_assembly(parts, groups=("puck",)).save(str(STEP_DIR / "GL1_marker_only.step"))
    if verbose:
        print(f"exported {len(parts)} parts to {P.EXPORT_DIR}")


def section(obj, origin, normal, tol=0.01, n_edge=24):
    """True planar section of a part by boolean common with a large planar face.
    Returns (triangles, edges): triangles is a list of 3x3 point lists (for filling the cut faces),
    edges a list of polylines (lists of xyz tuples) for the section outline."""
    pl = cq.Plane(origin=tuple(origin), normal=tuple(normal))
    face = cq.Face.makeFromWires(cq.Workplane(pl).rect(500, 500).val())
    sec = solid_of(obj).intersect(face)
    tris, edges = [], []
    for f in sec.Faces():
        vs, ts = f.tessellate(tol)
        for t in ts:
            tris.append([vs[i].toTuple() for i in t])
        for e in f.Edges():
            edges.append([e.positionAt(k / n_edge).toTuple() for k in range(n_edge + 1)])
    return tris, edges
