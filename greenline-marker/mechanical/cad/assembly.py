"""GreenLine GL-1 assembly: named, coloured parts; STEP / STL export.

Rev D: the base plate has two variants.  build_parts() returns the PRIMARY build (routed FR-4 plate, 0.20 mm sheet,
separate baffle ring) under the plain names, and the parts of the ALTERNATIVE build that differ (printed PA12 plate,
0.13 mm sheet, seal joint, ball pottings, grain potting) under the same names with the suffix "_pa12" and group "alt".
variant_view(parts) gives the alternative build as a complete assembly under the plain names.

Public API (used by checks.py, the drawings and the renders):
    build_parts()            -> dict name -> PartInfo (shape is a cadquery Workplane in the assembly frame)
    variant_view(parts)      -> the alternative build (PA12 base plate) under the plain part names
    solid_of(info_or_wp)     -> cadquery Shape (single solid or compound)
    build_assembly(parts)    -> cadquery.Assembly
    export_all(parts)        -> writes export/step, export/stl/parts, export/stl/print, params_resolved.json
    INTENDED_CONTACTS / MODELLING_OVERLAPS -> allow-lists for the interference check
"""
from __future__ import annotations
import dataclasses, pathlib, time
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
ALT_SUFFIX = "_" + P.BASE_ALT
PRINTED = ("tub", "cradle", "baffle_ring", "base_plate" + ALT_SUFFIX)     # MJF parts with a print file (the FR-4 plate is a fabricated part)
BASE_SPECIFIC = ["base_plate", "pcb_adhesive", "seal_bead", "grain_potting"] + [f"ball_epoxy_{i + 1}" for i in range(len(P.BALL_XY))]
PRIMARY_ONLY = ["baffle_ring", "baffle_adhesive"]                         # the PA12 plate carries its baffle itself


@dataclass
class PartInfo:
    name: str
    shape: cq.Workplane
    color: tuple            # r, g, b, a  (0..1)
    material: str
    density: float          # g/cm3 (PROVISIONAL typical values, used for the mass estimate)
    group: str              # "puck", "cradle" or "alt" (parts of the alternative base-plate build)
    kind: str               # "printed" | "fabricated" | "purchased" | "adhesive" | "reference"
    desc: str = ""


# name: (builder, colour rgba, material, density g/cm3, group, kind, description)
def _base_catalog(group):
    """The parts that depend on the base-plate variant, for the ACTIVE variant of params."""
    v = P.BASE
    c = OrderedDict()
    c["base_plate"] = (PT.base_plate, (0.20, 0.20, 0.22, 1), v["material"], v["density"], group, "printed" if v["printed"] else "fabricated",
                       f"GL1-{'012' if v['printed'] else '011'} base plate, {v['label']}")
    c["pcb_adhesive"] = (PT.pcb_adhesive, (0.95, 0.85, 0.35, 0.8), f"{v['psa_material']}, {P.PSA_T} mm, die cut (PROVISIONAL)", 1.0, group, "adhesive",
                         "die-cut adhesive sheet between PCB and base")
    c["seal_bead"] = (PT.seal_bead, (0.95, 0.55, 0.15, 0.9), f"dispensed seal adhesive: {P.BEAD_T:.2f} joint on the land + fill of the radial groove", 1.1,
                      group, "adhesive", "perimeter seal")
    c["grain_potting"] = (PT.grain_potting, (0.80, 0.90, 0.95, 0.45), "clear optical epoxy, hard, low fluorescence (PROVISIONAL, class only)", 1.15,
                          group, "adhesive", "clear potting of the grain opening")
    for i in range(len(P.BALL_XY)):
        c[f"ball_epoxy_{i + 1}"] = (lambda i=i: PT.ball_epoxy(i), (0.55, 0.75, 0.90, 0.9), "dual-cure or two-part epoxy: potting + backfill of the sheet hole (PROVISIONAL)",
                                    1.15, group, "adhesive", f"potting of foot ball {i + 1}")
    return c


def _catalog():
    PA12 = ("MJF PA12, dyed black, vapor smoothed", 1.01)
    c = OrderedDict()
    c["tub"] = (PT.tub, (0.13, 0.13, 0.14, 1), *PA12, "puck", "printed", "GL1-010 tub (top shell)")
    base = _base_catalog("puck")
    for n in ("base_plate", "pcb_adhesive", "seal_bead"):
        c[n] = base[n]
    c["main_pcb"] = (PT.main_pcb, (0.05, 0.40, 0.18, 1), "FR-4 + parts (envelope)", 2.2, "puck", "purchased", "main PCB assembly, part boxes from the YAML")
    c["baffle_ring"] = (PT.baffle_ring, (0.10, 0.10, 0.11, 1), "MJF PA12, dyed black, not vapor smoothed", 1.01, "puck", "printed", "GL1-013 grain baffle ring")
    c["baffle_adhesive"] = (PT.baffle_adhesive, (0.20, 0.20, 0.20, 0.9), f"opaque black double-coated tape {P.BAFFLE_PSA_T} mm, die-cut annulus (PROVISIONAL)", 1.0, "puck", "adhesive",
                            "adhesive annulus under the baffle ring")
    c["grain_potting"] = base["grain_potting"]
    for s in ("L", "R"):
        c[f"camera_{s}"] = (lambda s=s: PT.camera(s), (0.25, 0.25, 0.30, 1), "OVM7692-RYAA cube", 2.5, "puck", "purchased", f"camera cube {s}")
        c[f"prism_{s}"] = (lambda s=s: PT.prism(s), (0.55, 0.80, 0.95, 0.55), "N-BK7 prism, Edmund 32-526", 2.51, "puck", "purchased", f"2 mm fold prism {s}")
        c[f"visor_window_{s}"] = (lambda s=s: PT.visor_window(s), (0.60, 0.85, 0.95, 0.40), f"borosilicate {P.WIN_T} mm (D 263 T eco class), custom cut", 2.51,
                                  "puck", "purchased", f"visor window {s}")
        c[f"window_bond_{s}"] = (lambda s=s: PT.window_bond(s), (0.95, 0.85, 0.35, 0.8), "thixotropic light-cure adhesive: frame of side-gap fills, top bead and sill fillet (class only)", 1.1,
                                 "puck", "adhesive", f"adhesive round visor window {s}")
        c[f"hood_seal_{s}"] = (lambda s=s: PT.hood_seal(s), (0.08, 0.08, 0.09, 1), "black form-in-place gasket bead, silicone-free (class only)", 1.1, "puck", "adhesive", f"light seal above camera cube {s}")
    c["lcd_glass"] = (PT.lcd_glass, (0.70, 0.74, 0.70, 0.9), "Sharp LS013B7DH03 glass", 2.5, "puck", "purchased", "memory LCD")
    c["lcd_flex"] = (PT.lcd_flex, (0.85, 0.55, 0.10, 1), "polyimide FPC (PROVISIONAL shape)", 1.6, "puck", "reference", "LCD flex tail, representative")
    c["lcd_adhesive"] = (PT.lcd_adhesive, (0.95, 0.85, 0.35, 0.8), "PSA frame 0.15", 1.0, "puck", "adhesive", "LCD bonding frame")
    c["cover_glass"] = (PT.cover_glass, (0.75, 0.90, 0.98, 0.35), "mineral glass crystal 28.0 x 1.0 (EVT, not step-proof)", 2.5, "puck", "purchased", "cover glass")
    c["cover_tape"] = (PT.cover_tape, (0.95, 0.85, 0.35, 0.8), f"3M 9472LE transfer tape ring {P.CG_TAPE_T} mm, dia {P.CG_D} / {P.MECH['cover_tape_id']}", 1.0, "puck", "adhesive",
                       "cover-glass tape ring")
    c["battery"] = (PT.battery, (0.72, 0.72, 0.76, 1), "LiPo GM201030-PCB", 2.1, "puck", "purchased", "battery body (no swell)")
    for i in range(2):
        c[f"battery_lead_{i + 1}"] = (lambda i=i: PT.battery_lead(i), (0.80, 0.45, 0.30, 1), "cell lead + solder joint, envelope to the YAML joint height", 1.5, "puck",
                                      "reference", f"battery lead {i + 1} and its joint (envelope)")
    c["foam_pad"] = (PT.foam_pad, (0.35, 0.35, 0.35, 0.9), "PU foam 0.3 (e.g. Poron) PROVISIONAL", 0.32, "puck", "purchased", "foam pad under the LCD")
    for i in range(len(P.BALL_XY)):
        c[f"ball_{i + 1}"] = (lambda i=i: PT.ball(i), (0.85, 0.86, 0.90, 1), "stainless ball 1.0 mm", 7.9, "puck", "purchased", f"foot ball {i + 1}")
        c[f"ball_epoxy_{i + 1}"] = base[f"ball_epoxy_{i + 1}"]
    c["vent"] = (PT.vent, (0.95, 0.95, 0.95, 1), "Gore VE80205 ePTFE vent (PROVISIONAL)", 0.9, "puck", "purchased", "adhesive vent")
    c["cradle"] = (PT.cradle, (0.30, 0.32, 0.36, 1), "MJF PA12 (the latch is sized for PA12)", 1.01, "cradle", "printed", "GL1-020 cradle body with lip and latch")
    c["cradle_pcb"] = (PT.cradle_pcb, (0.05, 0.35, 0.50, 1), "FR-4 1.6", 1.85, "cradle", "purchased", "cradle PCB 30 x 22")
    c["usb_receptacle"] = (PT.usb_receptacle, (0.80, 0.80, 0.82, 1), "GCT USB4105 (PROVISIONAL envelope)", 2.0, "cradle", "purchased", "USB-C receptacle")
    return c


def build_parts(only=None, verbose=False, alt=True):
    """All parts of the primary build (groups "puck" and "cradle") and, with alt=True, the parts of the alternative
    base-plate build that differ (group "alt", names ending in ALT_SUFFIX)."""
    assert P.BASE_KEY == P.BASE_PRIMARY, "build_parts() must be called with the primary base variant active"
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
    if alt:
        with P.base_variant(P.BASE_ALT):
            for name, (fn, col, mat, rho, group, kind, desc) in _base_catalog("alt").items():
                n = name + ALT_SUFFIX
                if only and n not in only:
                    continue
                out[n] = PartInfo(n, fn(), col, mat, rho, group, kind, desc)
    return out


def primary(parts):
    """The primary build only (without the group "alt")."""
    return OrderedDict((n, i) for n, i in parts.items() if i.group != "alt")


def variant_view(parts):
    """The ALTERNATIVE build as a complete assembly under the plain part names: the base-specific parts are replaced by
    their "_pa12" versions and the parts that only the primary build has (separate baffle ring and its adhesive) are left
    out.  The PartInfo objects keep their own names (= export file names).  Use inside `with P.base_variant(P.BASE_ALT):`."""
    out = OrderedDict()
    for n, i in parts.items():
        if i.group == "alt" or n in PRIMARY_ONLY:
            continue
        a = parts.get(n + ALT_SUFFIX)
        out[n] = dataclasses.replace(a, group="puck") if a is not None else i
    return out


def solid_of(obj):
    wp = obj.shape if isinstance(obj, PartInfo) else obj
    return wp.val()


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
    """Print-orientation transform for the printed parts (z = build direction, part resting exactly on z = 0).
    tub: roof down.  PA12 base plate and baffle ring: flat, as modelled.  cradle: turned so that its x axis is the build
    direction - the side profile of the latch beam and of the lip then lies in the build plane (bending stress in-plane,
    not across layers)."""
    if name == "tub":            # roof down: cosmetic top face on the bed side, cavity open upward for depowdering
        wp = wp.rotate((0, 0, 0), (1, 0, 0), 180)
    if name == "cradle":         # model x -> build z
        wp = wp.rotate((0, 0, 0), (0, 1, 0), -90)
    return wp.translate((0, 0, -bbox_of(wp)[2]))


def print_shape(name, wp):
    """The PRINT FILE of a printed part, in print orientation.  The baffle ring is printed as a sprued set of rings with a
    lapping allowance on their height (parts.baffle_ring_sprue); every other part is printed as modelled."""
    if name == "baffle_ring":
        wp = PT.baffle_ring_sprue()
    return print_orientation(name, wp)


# Pairs that touch by design (zero-volume contact) - documented for the interference report.
INTENDED_CONTACTS = {
    ("tub", "main_pcb"): "support posts land on the PCB top face (posts B round their spigots)",
    ("tub", "seal_bead"): "seal face on the bead",
    ("tub", "lcd_adhesive"): "LCD bonded under the roof ledge",
    ("tub", "cover_tape"): "tape ring on the recess floor",
    ("tub", "vent"): "vent adhered to its pad",
    ("tub", "visor_window_L"): "window seated on the recess floor and on the shelf",
    ("tub", "visor_window_R"): "window seated on the recess floor and on the shelf",
    ("tub", "window_bond_L"): "adhesive frame: side gaps, top bead on the recess floor, fillet on the shelf",
    ("tub", "window_bond_R"): "adhesive frame: side gaps, top bead on the recess floor, fillet on the shelf",
    ("visor_window_L", "window_bond_L"): "adhesive frame round the edge of the glass", ("visor_window_R", "window_bond_R"): "adhesive frame round the edge of the glass",
    ("tub", "hood_seal_L"): "gasket bead on the hood rear wall", ("tub", "hood_seal_R"): "gasket bead on the hood rear wall",
    ("camera_L", "hood_seal_L"): "cube top squeezes the gasket bead", ("camera_R", "hood_seal_R"): "cube top squeezes the gasket bead",
    ("lcd_flex", "main_pcb"): "tail enters the J1 mouth (modelled up to the mouth face)",
    ("base_plate", "seal_bead"): "bead on the seal land",
    ("base_plate", "pcb_adhesive"): "adhesive sheet on the base top",
    ("main_pcb", "pcb_adhesive"): "adhesive sheet on the PCB underside",
    ("base_plate", "grain_potting"): "potting bonds to the wall of the grain opening (and to the integral baffle of the PA12 plate)",
    ("pcb_adhesive", "grain_potting"): "potting covers the edge of the adhesive sheet round the opening",
    ("main_pcb", "grain_potting"): "potting on the PCB underside, round the LEDs and the photodiode",
    ("baffle_ring", "grain_potting"): "baffle ring embedded in the potting, lower face flush with its surface",
    ("baffle_adhesive", "grain_potting"): "potting against the edge of the adhesive annulus",
    ("baffle_ring", "baffle_adhesive"): "ring bonded on its annulus",
    ("main_pcb", "baffle_adhesive"): "annulus on the PCB underside round the photodiode",
    ("main_pcb", "camera_L"): "soldered", ("main_pcb", "camera_R"): "soldered",
    ("main_pcb", "battery"): "battery on the PCB",
    ("lcd_glass", "lcd_adhesive"): "bond", ("lcd_glass", "foam_pad"): "foam under the glass",
    ("lcd_glass", "lcd_flex"): "tail attached at the rear edge",
    ("cover_glass", "cover_tape"): "bond",
    ("cradle", "cradle_pcb"): "PCB against the pocket ceiling",
    ("cradle_pcb", "usb_receptacle"): "soldered",
}
for _i in range(1, 3):
    INTENDED_CONTACTS[("main_pcb", f"battery_lead_{_i}")] = "lead soldered to its pad"
    INTENDED_CONTACTS[("battery", f"battery_lead_{_i}")] = "lead leaves the protection-board end of the cell"
for _i in range(1, 8):
    INTENDED_CONTACTS[("main_pcb", f"spring_pin_{_i}")] = "plunger tip on the contact pad"
    INTENDED_CONTACTS[("cradle_pcb", f"spring_pin_{_i}")] = "pin soldered into the cradle PCB"
for _i in range(1, 5):
    INTENDED_CONTACTS[("cradle", f"cradle_foot_{_i}")] = "foot in its pocket"
for _i in range(1, 4):
    INTENDED_CONTACTS[(f"ball_{_i}", "cradle")] = "ball foot rests on the nest (front strip / pad)"
    INTENDED_CONTACTS[(f"ball_{_i}", f"ball_epoxy_{_i}")] = "ball potted in epoxy"
    INTENDED_CONTACTS[("base_plate", f"ball_epoxy_{_i}")] = "epoxy fills the through hole and sits on the plate top"
    INTENDED_CONTACTS[("main_pcb", f"ball_epoxy_{_i}")] = "backfill of the sheet hole: the ball bears on its copper land through epoxy"
    INTENDED_CONTACTS[("pcb_adhesive", f"ball_epoxy_{_i}")] = "epoxy fills the 2.0 mm hole of the adhesive sheet"

# Pairs that overlap in VOLUME because of a modelling convention: none (the adhesive sheet has its own thickness).
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
            po = print_shape(name, parts[name].shape)
            po.val().exportStl(str(STL_PRINT_DIR / f"{name}_print.stl"), PRINT_STL_TOL, PRINT_STL_ANG)
            cq.exporters.export(po, str(STEP_DIR / f"{name}_print.step"))
    build_assembly(parts).save(str(STEP_DIR / "GL1_assembly.step"))
    build_assembly(parts, groups=("puck",)).save(str(STEP_DIR / "GL1_marker_only.step"))
    with P.base_variant(P.BASE_ALT):                    # the alternative build as its own marker assembly
        build_assembly(variant_view(parts), groups=("puck",)).save(str(STEP_DIR / f"GL1_marker_only{ALT_SUFFIX}_base.step"))
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
