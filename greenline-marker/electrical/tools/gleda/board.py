"""Board builder: :class:`gleda.model.Design` -> ``<name>.kicad_pcb`` + ``.kicad_pro``.

``build_board(design, out_dir)`` writes

* ``<name>.kicad_pcb``   stack-up, Edge.Cuts outline with cutouts, NPTH holes,
                         placed footprints with nets, plane zones (unfilled),
                         keep-out rule areas
* ``<name>.kicad_pro``   design rules, net classes and net-class assignment,
                         DRC severities (KiCad reads rules from here)
* ``gleda.pretty/``      the generated custom footprints
* ``fp-lib-table``       project library table pointing at ``gleda.pretty``

The board is NOT routed and its zones are NOT filled here: pcbnew 7 crashes
when filling zones on a board that was built in memory, so filling is done by
:mod:`gleda.drc` on the re-loaded file.

Routing primitives produced by the router (:class:`gleda.model.Track`,
:class:`gleda.model.Via`) are written with :func:`apply_routing` and read back
with :func:`read_routing`.

Coordinates are converted with :mod:`gleda.coords` only.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from . import coords, footprints, geometry
from .model import (Design, Part, Plane, Keepout, Track, Via, Rules, Stackup,
                    BOTTOM, TOP)

EDGE_WIDTH_MM = 0.05

#: DRC checks whose severity differs from the KiCad default, with the reason.
SEVERITY_OVERRIDES: Dict[str, Tuple[str, str]] = {
    "lib_footprint_issues": (
        "ignore", "headless runs have no global footprint library table, so every "
                  "footprint would be flagged 'library not found'"),
    "lib_footprint_mismatch": (
        "ignore", "placed footprints legitimately differ from their library copy (hidden "
                  "reference, BOM properties), which KiCad reports for every generated "
                  "footprint"),
}

#: KiCad 7 default severities (written explicitly so the project file is complete).
DEFAULT_SEVERITIES: Dict[str, str] = {
    "annular_width": "error", "clearance": "error", "connection_width": "warning",
    "copper_edge_clearance": "error", "copper_sliver": "warning",
    "courtyards_overlap": "error", "diff_pair_gap_out_of_range": "error",
    "diff_pair_uncoupled_length_too_long": "error", "drill_out_of_range": "error",
    "duplicate_footprints": "warning", "extra_footprint": "warning", "footprint": "error",
    "footprint_type_mismatch": "ignore", "hole_clearance": "error",
    "hole_near_hole": "error", "invalid_outline": "error", "isolated_copper": "warning",
    "item_on_disabled_layer": "error", "items_not_allowed": "error",
    "length_out_of_range": "error", "lib_footprint_issues": "warning",
    "lib_footprint_mismatch": "warning", "malformed_courtyard": "error",
    "microvia_drill_out_of_range": "error", "missing_courtyard": "ignore",
    "missing_footprint": "warning", "net_conflict": "warning",
    "npth_inside_courtyard": "ignore", "padstack": "warning",
    "pth_inside_courtyard": "ignore", "shorting_items": "error",
    "silk_edge_clearance": "warning", "silk_over_copper": "warning",
    "silk_overlap": "warning", "skew_out_of_range": "error",
    "solder_mask_bridge": "error", "starved_thermal": "error", "text_height": "warning",
    "text_thickness": "warning", "through_hole_pad_without_hole": "error",
    "too_many_vias": "error", "track_dangling": "warning", "track_width": "error",
    "tracks_crossing": "error", "unconnected_items": "error",
    "unresolved_variable": "error", "via_dangling": "warning", "zones_intersect": "error",
}

#: Checks that must stay at severity "error" for a result to count as a pass.
CORE_ERROR_CHECKS: Tuple[str, ...] = (
    "clearance", "track_width", "annular_width", "drill_out_of_range",
    "hole_clearance", "hole_near_hole", "copper_edge_clearance", "shorting_items",
    "tracks_crossing", "unconnected_items", "invalid_outline", "items_not_allowed",
    "courtyards_overlap", "zones_intersect", "solder_mask_bridge",
)


class BoardBuildError(Exception):
    """The design cannot be turned into a board."""


@dataclass
class BoardFiles:
    """Paths written by :func:`build_board`."""
    directory: str
    pcb: str
    pro: str
    lib_dir: Optional[str]
    lib_table: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {"directory": self.directory, "pcb": self.pcb, "pro": self.pro,
                "lib_dir": self.lib_dir, "lib_table": self.lib_table}


# --------------------------------------------------------------------------
# small pcbnew helpers (all coordinate conversion goes through gleda.coords)
# --------------------------------------------------------------------------

def _pcbnew():
    import pcbnew
    return pcbnew


def kicad_point(x: float, y: float):
    """Design mm -> ``pcbnew.VECTOR2I`` on the KiCad page."""
    pcbnew = _pcbnew()
    kx, ky = coords.to_kicad_nm(x, y)
    return pcbnew.VECTOR2I(kx, ky)


def design_point(vec) -> Tuple[float, float]:
    """``pcbnew.VECTOR2I`` on the KiCad page -> design mm."""
    return coords.from_kicad_nm(vec.x, vec.y)


def layer_id(board, name: str) -> int:
    """KiCad layer id of a layer name such as ``"In1.Cu"``."""
    lid = board.GetLayerID(name)
    if lid < 0:
        raise BoardBuildError("unknown layer %r" % (name,))
    return lid


def _nm(v: float) -> int:
    return coords.mm_to_nm(v)


# --------------------------------------------------------------------------
# project file
# --------------------------------------------------------------------------

def project_dict(design: Design) -> Dict[str, Any]:
    """Content of ``<name>.kicad_pro`` (KiCad 7 format) for a design."""
    r: Rules = design.rules
    severities = dict(DEFAULT_SEVERITIES)
    for check, (sev, _why) in SEVERITY_OVERRIDES.items():
        severities[check] = sev
    classes = []
    names = ["Default"] + sorted(n for n in design.netclasses if n != "Default")
    for name in names:
        nc = design.netclasses[name]
        classes.append({
            "bus_width": 12,
            "clearance": nc.clearance,
            "diff_pair_gap": max(r.min_clearance, 0.15),
            "diff_pair_via_gap": 0.25,
            "diff_pair_width": nc.track_width,
            "line_style": 0,
            "microvia_diameter": 0.3,
            "microvia_drill": 0.1,
            "name": nc.name,
            "pcb_color": "rgba(0, 0, 0, 0.000)",
            "schematic_color": "rgba(0, 0, 0, 0.000)",
            "track_width": nc.track_width,
            "via_diameter": nc.via_diameter,
            "via_drill": nc.via_drill,
            "wire_width": 6,
        })
    patterns = []
    for net in design.nets.values():
        if net.netclass != "Default":
            patterns.append({"netclass": net.netclass, "pattern": _netclass_pattern(net.name)})
    track_widths = sorted({0.0} | {nc.track_width for nc in design.netclasses.values()}
                          | {n.width for n in design.nets.values() if n.width})
    return {
        "board": {
            "3dviewports": [],
            "design_settings": {
                "defaults": {
                    "board_outline_line_width": EDGE_WIDTH_MM,
                    "copper_line_width": 0.2,
                    "copper_text_italic": False,
                    "copper_text_size_h": 1.0,
                    "copper_text_size_v": 1.0,
                    "copper_text_thickness": 0.15,
                    "copper_text_upright": False,
                    "courtyard_line_width": 0.05,
                    "dimension_precision": 4,
                    "dimension_units": 3,
                    "dimensions": {
                        "arrow_length": 1270000, "extension_offset": 500000,
                        "keep_text_aligned": True, "suppress_zeroes": False,
                        "text_position": 0, "units_format": 1,
                    },
                    "fab_line_width": 0.1,
                    "fab_text_italic": False,
                    "fab_text_size_h": 1.0,
                    "fab_text_size_v": 1.0,
                    "fab_text_thickness": 0.15,
                    "fab_text_upright": False,
                    "other_line_width": 0.1,
                    "other_text_italic": False,
                    "other_text_size_h": 1.0,
                    "other_text_size_v": 1.0,
                    "other_text_thickness": 0.15,
                    "other_text_upright": False,
                    "pads": {"drill": 0.0, "height": 1.0, "width": 1.0},
                    "silk_line_width": 0.12,
                    "silk_text_italic": False,
                    "silk_text_size_h": 0.8,
                    "silk_text_size_v": 0.8,
                    "silk_text_thickness": 0.12,
                    "silk_text_upright": False,
                    "zones": {"min_clearance": r.zone_clearance},
                },
                "diff_pair_dimensions": [],
                "drc_exclusions": [],
                "meta": {"version": 2},
                "rule_severities": severities,
                "rules": {
                    "allow_blind_buried_vias": bool(r.blind_buried_vias),
                    "allow_microvias": False,
                    "max_error": r.max_arc_error,
                    "min_clearance": r.min_clearance,
                    "min_connection": 0.0,
                    "min_copper_edge_clearance": r.copper_to_edge,
                    "min_hole_clearance": r.hole_clearance,
                    "min_hole_to_hole": r.hole_to_hole,
                    "min_microvia_diameter": 0.2,
                    "min_microvia_drill": 0.1,
                    "min_resolved_spokes": 2,
                    "min_silk_clearance": 0.0,
                    "min_text_height": r.min_text_height,
                    "min_text_thickness": 0.08,
                    "min_through_hole_diameter": r.min_drill,
                    "min_track_width": r.min_track,
                    "min_via_annular_width": r.min_annular,
                    "min_via_diameter": r.min_via_diameter,
                    "solder_mask_clearance": r.mask_expansion,
                    "solder_mask_min_width": r.mask_min_web,
                    "solder_mask_to_copper_clearance": 0.0,
                    "use_height_for_length_calcs": True,
                },
                "teardrop_options": [{
                    "td_allow_use_two_tracks": True, "td_curve_segcount": 5,
                    "td_on_pad_in_zone": False, "td_onpadsmd": True,
                    "td_onroundshapesonly": False, "td_ontrackend": False,
                    "td_onviapad": True,
                }],
                "teardrop_parameters": [
                    {"td_curve_segcount": 0, "td_height_ratio": 1.0, "td_length_ratio": 0.5,
                     "td_maxheight": 2.0, "td_maxlen": 1.0, "td_target_name": name,
                     "td_width_to_size_filter_ratio": 0.9}
                    for name in ("td_round_shape", "td_rect_shape", "td_track_end")
                ],
                "track_widths": track_widths,
                "via_dimensions": [{"diameter": 0.0, "drill": 0.0},
                                   {"diameter": r.via_diameter, "drill": r.via_drill}],
                "zones_allow_external_fillets": False,
            },
            "layer_presets": [],
            "viewports": [],
        },
        "boards": [],
        "cvpcb": {"equivalence_files": []},
        "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
        "meta": {"filename": "%s.kicad_pro" % design.name, "version": 1},
        "net_settings": {
            "classes": classes,
            "meta": {"version": 3},
            "net_colors": None,
            "netclass_assignments": None,
            "netclass_patterns": patterns,
        },
        "pcbnew": {
            "last_paths": {"gencad": "", "idf": "", "netlist": "", "specctra_dsn": "",
                           "step": "", "vrml": ""},
            "page_layout_descr_file": "",
        },
        "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
        "sheets": [],
        "text_variables": {},
    }


def _netclass_pattern(net_name: str) -> str:
    """Net-class assignment pattern matching exactly one net.

    KiCad tries the pattern as a regular expression first and as a wildcard
    second.  Net names are therefore regex-escaped; this also keeps a name
    such as ``+3V0`` or ``D[0]`` from being misread."""
    return re.sub(r"([.^$*+?()\[\]{}|\\/])", r"\\\1", net_name)


def write_project(design: Design, pro_path: str, merge_existing: bool = True) -> str:
    """Write ``<name>.kicad_pro``.

    If the file already exists (for example written by the schematic
    generator) and ``merge_existing`` is true, only the ``board`` and
    ``net_settings`` sections are replaced so that foreign sections survive.
    """
    data = project_dict(design)
    if merge_existing and os.path.exists(pro_path):
        try:
            with open(pro_path, encoding="utf-8") as fh:
                old = json.load(fh)
        except (OSError, ValueError):
            old = None
        if isinstance(old, dict):
            for key, value in old.items():
                if key not in ("board", "net_settings", "meta"):
                    data[key] = value
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    with open(pro_path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return pro_path


def write_fp_lib_table(directory: str) -> str:
    """Project footprint library table with the generated ``gleda`` library."""
    path = os.path.join(directory, "fp-lib-table")
    text = ('(fp_lib_table\n'
            '  (version 7)\n'
            '  (lib (name "%s")(type "KiCad")(uri "${KIPRJMOD}/%s.pretty")(options "")'
            '(descr "Footprints generated by gleda"))\n'
            ')\n' % (footprints.CUSTOM_LIB, footprints.CUSTOM_LIB))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


# --------------------------------------------------------------------------
# stack-up text (pcbnew's Python API cannot edit the stack-up)
# --------------------------------------------------------------------------

_STACKUP_TYPE = {
    ("silk", "F"): "Top Silk Screen", ("silk", "B"): "Bottom Silk Screen",
    ("paste", "F"): "Top Solder Paste", ("paste", "B"): "Bottom Solder Paste",
    ("mask", "F"): "Top Solder Mask", ("mask", "B"): "Bottom Solder Mask",
}


def _num(v: float) -> str:
    s = ("%.6f" % v).rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def stackup_sexpr(stackup: Stackup, indent: str = "    ") -> str:
    """``(stackup ...)`` block for the ``(setup ...)`` section of a board file."""
    lines = [indent + "(stackup"]
    for layer in stackup.layers:
        side = layer.name[0]
        if layer.kind in ("silk", "paste", "mask"):
            parts = ['(layer "%s" (type "%s")' % (layer.name, _STACKUP_TYPE[(layer.kind, side)])]
            if layer.kind == "mask" and layer.thickness:
                parts.append("(thickness %s)" % _num(layer.thickness))
        elif layer.kind == "copper":
            parts = ['(layer "%s" (type "copper") (thickness %s)' % (
                layer.name, _num(layer.thickness))]
        else:
            parts = ['(layer "%s" (type "%s") (thickness %s) (material "%s") '
                     '(epsilon_r %s) (loss_tangent %s)' % (
                         layer.name, layer.kind, _num(layer.thickness),
                         layer.material or "FR4", _num(layer.epsilon_r or 4.5),
                         _num(layer.loss_tangent or 0.02))]
        lines.append(indent + "  " + " ".join(parts) + ")")
    lines.append(indent + '  (copper_finish "%s")' % stackup.finish)
    lines.append(indent + "  (dielectric_constraints no)")
    lines.append(indent + ")")
    return "\n".join(lines) + "\n"


def _inject_stackup(pcb_path: str, stackup: Stackup) -> None:
    """Insert (or replace) the stack-up block in a saved board file."""
    with open(pcb_path, encoding="utf-8") as fh:
        text = fh.read()
    start = text.find("\n  (setup\n")
    if start < 0:
        raise BoardBuildError("board file has no (setup ...) section")
    insert_at = start + len("\n  (setup\n")
    existing = text.find("    (stackup\n", insert_at)
    if existing == insert_at:
        end = text.find("\n    )\n", existing) + len("\n    )\n")
        text = text[:existing] + text[end:]
    text = text[:insert_at] + stackup_sexpr(stackup) + text[insert_at:]
    with open(pcb_path, "w", encoding="utf-8") as fh:
        fh.write(text)


# --------------------------------------------------------------------------
# building
# --------------------------------------------------------------------------

def _apply_rules(board, design: Design) -> None:
    """Mirror the rule set into the in-memory board (the project file is the
    authoritative copy that KiCad loads)."""
    pcbnew = _pcbnew()
    r = design.rules
    ds = board.GetDesignSettings()
    ds.SetBoardThickness(_nm(design.board_thickness))
    ds.m_MinClearance = _nm(r.min_clearance)
    ds.m_TrackMinWidth = _nm(r.min_track)
    ds.m_ViasMinAnnularWidth = _nm(r.min_annular)
    ds.m_ViasMinSize = _nm(r.min_via_diameter)
    ds.m_MinThroughDrill = _nm(r.min_drill)
    ds.m_HoleToHoleMin = _nm(r.hole_to_hole)
    ds.m_HoleClearance = _nm(r.hole_clearance)
    ds.m_CopperEdgeClearance = _nm(r.copper_to_edge)
    ds.m_SolderMaskExpansion = _nm(r.mask_expansion)
    ds.m_SolderMaskMinWidth = _nm(r.mask_min_web)
    ds.m_MaxError = _nm(r.max_arc_error)
    origin = kicad_point(0.0, 0.0)
    ds.SetAuxOrigin(origin)
    ds.SetGridOrigin(origin)
    tb = board.GetTitleBlock()
    tb.SetTitle(design.title)
    tb.SetRevision(design.revision)
    if design.company:
        tb.SetCompany(design.company)
    if design.date:
        tb.SetDate(design.date)
    tb.SetComment(0, "Generated by gleda - rule set %s" % r.name)


def _add_path(board, path: Sequence[object], layer: int, width: float) -> None:
    """Draw a geometry path (lines / arcs / circle) as board graphics."""
    pcbnew = _pcbnew()
    for el in path:
        shape = pcbnew.PCB_SHAPE(board)
        shape.SetLayer(layer)
        shape.SetWidth(_nm(width))
        if isinstance(el, geometry.Line):
            shape.SetShape(pcbnew.SHAPE_T_SEGMENT)
            shape.SetStart(kicad_point(*el.start))
            shape.SetEnd(kicad_point(*el.end))
        elif isinstance(el, geometry.Arc):
            shape.SetShape(pcbnew.SHAPE_T_ARC)
            shape.SetArcGeometry(kicad_point(*el.start), kicad_point(*el.mid),
                                 kicad_point(*el.end))
        elif isinstance(el, geometry.FullCircle):
            shape.SetShape(pcbnew.SHAPE_T_CIRCLE)
            shape.SetCenter(kicad_point(*el.center))
            shape.SetEnd(kicad_point(el.center[0] + el.radius, el.center[1]))
        else:
            raise BoardBuildError("unknown path element %r" % (el,))
        board.Add(shape)


def _set_zone_outline(zone, points: Sequence[Tuple[float, float]]) -> None:
    outline = zone.Outline()
    outline.NewOutline()
    for x, y in points:
        kx, ky = coords.to_kicad_nm(x, y)
        outline.Append(kx, ky)


def _plane_points(design: Design, plane: Plane) -> List[Tuple[float, float]]:
    if plane.shape is None:
        xmin, ymin, xmax, ymax = geometry.board_bounds(design)
        m = 1.0
        return [(xmin - m, ymin - m), (xmax + m, ymin - m), (xmax + m, ymax + m),
                (xmin - m, ymax + m)]
    poly = geometry.shape_polygon(plane.shape, design.rules.max_arc_error)
    return list(poly.exterior.coords)[:-1]


def _add_plane(board, design: Design, plane: Plane, nets: Dict[str, Any], index: int) -> None:
    pcbnew = _pcbnew()
    r = design.rules
    if plane.net not in nets:
        raise BoardBuildError("plane on %s: unknown net %r" % (plane.layer, plane.net))
    zone = pcbnew.ZONE(board)
    zone.SetLayer(layer_id(board, plane.layer))
    zone.SetNet(nets[plane.net])
    zone.SetZoneName(plane.name or "%s_%s" % (plane.net, plane.layer))
    zone.SetAssignedPriority(int(plane.priority))
    _set_zone_outline(zone, _plane_points(design, plane))
    clearance = plane.clearance if plane.clearance is not None else max(
        r.zone_clearance, design.netclass_of(plane.net).clearance)
    zone.SetLocalClearance(_nm(clearance))
    zone.SetMinThickness(_nm(plane.min_width if plane.min_width is not None
                             else r.zone_min_width))
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL if plane.thermal
                          else pcbnew.ZONE_CONNECTION_FULL)
    zone.SetThermalReliefGap(_nm(r.thermal_gap))
    zone.SetThermalReliefSpokeWidth(_nm(r.thermal_spoke))
    zone.SetFillMode(pcbnew.ZONE_FILL_MODE_POLYGONS)
    zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER if plane.keep_islands
                              else pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    board.Add(zone)


def _add_keepout(board, design: Design, ko: Keepout, index: int) -> None:
    pcbnew = _pcbnew()
    zone = pcbnew.ZONE(board)
    zone.SetIsRuleArea(True)
    lset = pcbnew.LSET()
    for name in ko.layer_names(design.copper_layers):
        lset.AddLayer(layer_id(board, name))
    zone.SetLayerSet(lset)
    zone.SetZoneName(ko.name or "keepout_%d" % (index + 1))
    zone.SetDoNotAllowTracks(bool(ko.tracks))
    zone.SetDoNotAllowVias(bool(ko.vias))
    zone.SetDoNotAllowCopperPour(bool(ko.copper))
    zone.SetDoNotAllowPads(bool(ko.pads))
    zone.SetDoNotAllowFootprints(bool(ko.footprints))
    poly = geometry.shape_polygon(ko.shape, design.rules.max_arc_error, "circumscribed")
    _set_zone_outline(zone, list(poly.exterior.coords)[:-1])
    board.Add(zone)


def _place_footprint(board, fp, x: float, y: float, rotation: float, side: str) -> None:
    """Put a freshly loaded footprint on the board (see gleda.coords for the
    bottom-side convention: flip about the footprint X axis, then rotate)."""
    board.Add(fp)
    pos = kicad_point(x, y)
    fp.SetPosition(pos)
    if side == BOTTOM:
        fp.Flip(pos, False)
    fp.SetOrientationDegrees(coords.to_kicad_angle(rotation))


def _add_part(board, design: Design, part: Part, nets: Dict[str, Any],
              lib_dir: str) -> None:
    pcbnew = _pcbnew()
    if not part.placed:
        raise BoardBuildError("%s has no placement" % part.ref)
    try:
        fp = footprints.load(part.footprint, custom_lib_dir=lib_dir)
    except footprints.FootprintError as exc:
        raise BoardBuildError("%s: %s" % (part.ref, exc))
    fp.SetReference(part.ref)
    fp.SetValue(part.value)
    if part.description:
        fp.SetDescription(part.description)
    _place_footprint(board, fp, part.x, part.y, part.rotation, part.side)
    if not design.silk_refs:
        fp.Reference().SetVisible(False)
    attrs = fp.GetAttributes()
    if not part.in_bom:
        attrs |= pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES
    if part.dnp:
        attrs |= pcbnew.FP_EXCLUDE_FROM_POS_FILES
    fp.SetAttributes(attrs)
    props = {
        "MPN": part.mpn, "Manufacturer": part.manufacturer,
        "Distributor": part.distributor, "Distributor PN": part.distributor_pn,
        "Group": part.group,
    }
    if part.dnp:
        props["DNP"] = "DNP"
    if part.height_mm is not None:
        props["Height"] = "%g mm" % part.height_mm
    for key, value in part.fields.items():
        props[str(key)] = str(value)
    for key in sorted(props):
        if props[key]:
            fp.SetProperty(key, props[key])
    pad_nets = design.pad_nets(part.ref)
    pin_of_pad: Dict[str, Any] = {}
    for pin in part.pins.values():
        for num in pin.pads:
            pin_of_pad.setdefault(num, pin)
    for pad in fp.Pads():
        number = str(pad.GetNumber())
        net = pad_nets.get(number)
        if net is not None:
            pad.SetNet(nets[net])
        pin = pin_of_pad.get(number)
        if pin is not None:
            pad.SetPinFunction(pin.name)
            pad.SetPinType(pin.etype)


def _add_hole(board, design: Design, index: int, hole, lib_dir: str) -> None:
    pcbnew = _pcbnew()
    spec = footprints.npth_hole(hole.drill)
    fp = footprints.load(spec, custom_lib_dir=lib_dir)
    fp.SetReference(hole.name or "H%d" % (index + 1))
    fp.SetValue("NPTH %gmm" % hole.drill)
    _place_footprint(board, fp, hole.x, hole.y, 0.0, TOP)
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)


def build_board(design: Design, out_dir: str, *, seed: int = 1) -> BoardFiles:
    """Generate the unrouted board, project file and custom footprint library.

    Returns a :class:`BoardFiles`.  Raises :class:`BoardBuildError` for
    designs that cannot be built (unplaced parts, missing footprints, unknown
    nets on planes).  Run :func:`gleda.checks.run_checks` first for a full
    diagnosis - this function only refuses what it cannot physically build.

    ``seed`` seeds KiCad's UUID generator so that re-running the build gives
    byte-identical files.
    """
    pcbnew = _pcbnew()
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    lib_dir = os.path.join(out_dir, footprints.CUSTOM_LIB + ".pretty")

    seen = set()
    for part in design.parts:
        if part.ref in seen:
            raise BoardBuildError("duplicate reference %s" % part.ref)
        seen.add(part.ref)
        if not part.placed:
            raise BoardBuildError("%s has no placement" % part.ref)

    # custom footprint library (also validates name clashes)
    specs = [p.footprint for p in design.parts
             if isinstance(p.footprint, footprints.FootprintSpec)]
    specs += [footprints.npth_hole(h.drill) for h in design.outline.holes]
    has_lib = bool(specs)
    if has_lib:
        try:
            footprints.write_library(specs, lib_dir)
        except footprints.FootprintError as exc:
            raise BoardBuildError(str(exc))
    # stale generated footprints from an earlier build of the same design
    if os.path.isdir(lib_dir):
        wanted = {s.name + ".kicad_mod" for s in specs}
        for fn in sorted(os.listdir(lib_dir)):
            if fn.endswith(".kicad_mod") and fn not in wanted:
                os.remove(os.path.join(lib_dir, fn))

    contours = geometry.outline_contours(design.outline, design.rules.max_arc_error)

    # Determinism: KiCad sorts board items by UUID when saving, and pcbnew's
    # footprint-library cache consumes a state-dependent number of UUIDs the
    # first time a library is touched.  So (1) warm the cache with a throw-away
    # load of every footprint in the exact order used below, (2) only then seed
    # the UUID generator.  From here on the UUID sequence is reproducible.
    try:
        for hole in design.outline.holes:
            footprints.load(footprints.npth_hole(hole.drill), custom_lib_dir=lib_dir)
        for part in design.parts:
            footprints.load(part.footprint, custom_lib_dir=lib_dir)
    except footprints.FootprintError as exc:
        raise BoardBuildError(str(exc))
    pcbnew.KIID.SeedGenerator(int(seed))
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(design.layers)
    _apply_rules(board, design)

    nets: Dict[str, Any] = {}
    for name in design.nets:
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        nets[name] = ni

    for path in contours:
        _add_path(board, path, pcbnew.Edge_Cuts, EDGE_WIDTH_MM)
    for i, hole in enumerate(design.outline.holes):
        _add_hole(board, design, i, hole, lib_dir)
    for part in design.parts:
        _add_part(board, design, part, nets, lib_dir)
    for i, plane in enumerate(design.planes):
        _add_plane(board, design, plane, nets, i)
    for i, ko in enumerate(design.keepouts):
        _add_keepout(board, design, ko, i)
    if design.tracks or design.vias:
        _add_routing(board, design.tracks, design.vias)

    pcb_path = os.path.join(out_dir, design.name + ".kicad_pcb")
    pro_path = os.path.join(out_dir, design.name + ".kicad_pro")
    if not pcbnew.SaveBoard(pcb_path, board, True):
        raise BoardBuildError("pcbnew could not save %s" % pcb_path)
    _KEEP_ALIVE.append(board)
    _inject_stackup(pcb_path, design.stackup)
    write_project(design, pro_path)
    lib_table = write_fp_lib_table(out_dir) if has_lib else None
    return BoardFiles(out_dir, pcb_path, pro_path, lib_dir if has_lib else None, lib_table)


#: In-memory boards built by this process.  They are deliberately never
#: destroyed: tearing down a hand-built BOARD while Python still holds wrapper
#: objects of its children is a classic source of pcbnew crashes.
_KEEP_ALIVE: List[Any] = []


# --------------------------------------------------------------------------
# load / save / routing
# --------------------------------------------------------------------------

def load_board(pcb_path: str):
    """``pcbnew.LoadBoard`` (also loads rules / net classes from the
    ``.kicad_pro`` next to the board).  Raises FileNotFoundError early because
    pcbnew's own error for a missing file is unhelpful."""
    if not os.path.exists(pcb_path):
        raise FileNotFoundError(pcb_path)
    board = _pcbnew().LoadBoard(pcb_path)
    if board is None:
        raise BoardBuildError("pcbnew could not load %s" % pcb_path)
    return board


def save_board(board, pcb_path: str) -> str:
    """Save a board WITHOUT touching the project file.

    ``pcbnew.SaveBoard(path, board)`` rewrites ``.kicad_pro`` (and drops a
    ``.kicad_prl``) from the in-memory project by default; the toolchain owns
    the project file, so settings are skipped here."""
    if not _pcbnew().SaveBoard(pcb_path, board, True):
        raise BoardBuildError("pcbnew could not save %s" % pcb_path)
    return pcb_path


def _add_routing(board, tracks: Iterable[Track], vias: Iterable[Via]) -> Tuple[int, int]:
    pcbnew = _pcbnew()
    n_tracks = n_vias = 0
    net_cache: Dict[str, Any] = {}

    def net_item(name: str):
        if name not in net_cache:
            ni = board.FindNet(name)
            if ni is None:
                raise BoardBuildError("routing refers to unknown net %r" % (name,))
            net_cache[name] = ni
        return net_cache[name]

    for t in tracks:
        seg = pcbnew.PCB_TRACK(board)
        seg.SetStart(kicad_point(t.x1, t.y1))
        seg.SetEnd(kicad_point(t.x2, t.y2))
        seg.SetWidth(_nm(t.width))
        seg.SetLayer(layer_id(board, t.layer))
        seg.SetNet(net_item(t.net))
        board.Add(seg)
        n_tracks += 1
    for v in vias:
        via = pcbnew.PCB_VIA(board)
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetPosition(kicad_point(v.x, v.y))
        via.SetWidth(_nm(v.diameter))
        via.SetDrill(_nm(v.drill))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNet(net_item(v.net))
        board.Add(via)
        n_vias += 1
    return n_tracks, n_vias


def clear_routing(board) -> int:
    """Remove every track and via from a loaded board; returns the count."""
    items = list(board.GetTracks())
    for item in items:
        board.Remove(item)
    return len(items)


@dataclass
class ApplyResult:
    """Outcome of :func:`apply_routing`.

    ``renetted`` lists segments whose net KiCad changed while they were added:
    ``(requested Track, net actually stored)``.  KiCad's connectivity engine
    silently merges the nets of touching tracks when the copper cluster holds
    no pad, so a non-empty list means the router emitted tracks of different
    nets that touch each other."""
    tracks: int
    vias: int
    renetted: List[Tuple[Track, str]]

    def __iter__(self):
        return iter((self.tracks, self.vias))


def _track_key(layer: str, x1: float, y1: float, x2: float, y2: float
               ) -> Tuple[str, Tuple[int, int], Tuple[int, int]]:
    a = coords.to_kicad_nm(x1, y1)
    b = coords.to_kicad_nm(x2, y2)
    return (layer,) + tuple(sorted((a, b)))            # type: ignore[return-value]


def apply_routing(pcb_path: str, tracks: Iterable[Track], vias: Iterable[Via], *,
                  replace: bool = True, seed: int = 2, strict: bool = True) -> ApplyResult:
    """Write router output into an existing board file.

    Loads the board, optionally removes the existing tracks/vias, adds the
    given :class:`Track` / :class:`Via` primitives (through vias F.Cu-B.Cu) and
    saves.  Zone fills become stale - run :func:`gleda.drc.run_drc` (which
    refills) afterwards.

    After saving, the stored nets are compared with the requested ones.  If
    KiCad re-assigned any (see :class:`ApplyResult`), the board is still saved
    for inspection and, with ``strict`` (default), :class:`BoardBuildError` is
    raised.  Returns an :class:`ApplyResult` (also unpackable as
    ``tracks_added, vias_added``).
    """
    pcbnew = _pcbnew()
    tracks = list(tracks)
    vias = list(vias)
    board = load_board(pcb_path)
    if replace:
        clear_routing(board)
        pcbnew.KIID.SeedGenerator(int(seed))
    else:
        # appending: move to a different UUID stream than the one that produced
        # the items already on the board, so no UUID is issued twice
        pcbnew.KIID.SeedGenerator(int(seed) + 1 + len(board.GetTracks()))
    n_tracks, n_vias = _add_routing(board, tracks, vias)
    save_board(board, pcb_path)
    stored: Dict[Any, List[str]] = {}
    for item in board.GetTracks():
        if isinstance(item, pcbnew.PCB_VIA):
            continue
        a = (item.GetStart().x, item.GetStart().y)
        b = (item.GetEnd().x, item.GetEnd().y)
        key = (board.GetLayerName(item.GetLayer()),) + tuple(sorted((a, b)))
        stored.setdefault(key, []).append(str(item.GetNetname()))
    renetted: List[Tuple[Track, str]] = []
    for t in tracks:
        nets_here = stored.get(_track_key(t.layer, t.x1, t.y1, t.x2, t.y2), [])
        if t.net in nets_here:
            nets_here.remove(t.net)
        elif nets_here:
            renetted.append((t, nets_here.pop(0)))
    result = ApplyResult(n_tracks, n_vias, renetted)
    if renetted and strict:
        sample = "; ".join("%s track (%.3f, %.3f)-(%.3f, %.3f) on %s became %s" % (
            t.net, t.x1, t.y1, t.x2, t.y2, t.layer, actual) for t, actual in renetted[:5])
        raise BoardBuildError(
            "KiCad re-assigned the net of %d track(s): tracks of different nets touch "
            "(%s). The board was saved to %s for inspection." % (
                len(renetted), sample, pcb_path))
    return result


def read_routing(pcb_path: str) -> Tuple[List[Track], List[Via]]:
    """Read tracks and vias of a board file back as model primitives."""
    pcbnew = _pcbnew()
    board = load_board(pcb_path)
    tracks: List[Track] = []
    vias: List[Via] = []
    for item in board.GetTracks():
        if isinstance(item, pcbnew.PCB_VIA):
            x, y = design_point(item.GetPosition())
            vias.append(Via(item.GetNetname(), round(x, 6), round(y, 6),
                            coords.nm_to_mm(item.GetWidth()), coords.nm_to_mm(item.GetDrill())))
        else:
            x1, y1 = design_point(item.GetStart())
            x2, y2 = design_point(item.GetEnd())
            tracks.append(Track(item.GetNetname(), board.GetLayerName(item.GetLayer()),
                                round(x1, 6), round(y1, 6), round(x2, 6), round(y2, 6),
                                coords.nm_to_mm(item.GetWidth())))
    return tracks, vias


def board_summary(pcb_path: str) -> Dict[str, Any]:
    """Facts read back from a board file with pcbnew (used by tests / reports).

    Footprint and pad positions are converted to design coordinates."""
    pcbnew = _pcbnew()
    board = load_board(pcb_path)
    ds = board.GetDesignSettings()
    fps = {}
    for fp in board.GetFootprints():
        x, y = design_point(fp.GetPosition())
        pads = []
        for pad in fp.Pads():
            px, py = design_point(pad.GetPosition())
            pads.append({"number": str(pad.GetNumber()), "x": round(px, 6), "y": round(py, 6),
                         "net": str(pad.GetNetname()),
                         "layers": [board.GetLayerName(l) for l in pad.GetLayerSet().Seq()
                                    if pcbnew.IsCopperLayer(l) and board.IsLayerEnabled(l)]})
        fps[str(fp.GetReference())] = {
            "lib_id": str(fp.GetFPID().GetUniStringLibId()),
            "x": round(x, 6), "y": round(y, 6),
            "rotation": coords.normalize_angle(fp.GetOrientationDegrees()),
            "side": BOTTOM if fp.IsFlipped() else TOP,
            "value": str(fp.GetValue()),
            "pads": pads,
        }
    zones = []
    for zone in board.Zones():
        zones.append({
            "name": str(zone.GetZoneName()),
            "net": str(zone.GetNetname()),
            "rule_area": bool(zone.GetIsRuleArea()),
            "layers": [board.GetLayerName(l) for l in zone.GetLayerSet().Seq()],
            "filled": bool(zone.IsFilled()),
        })
    tracks = [t for t in board.GetTracks()]
    bbox = board.GetBoardEdgesBoundingBox()
    x0, y1 = coords.from_kicad_nm(bbox.GetLeft(), bbox.GetTop())
    x1, y0 = coords.from_kicad_nm(bbox.GetRight(), bbox.GetBottom())
    return {
        "copper_layers": board.GetCopperLayerCount(),
        "thickness": coords.nm_to_mm(ds.GetBoardThickness()),
        "rules": {
            "min_clearance": coords.nm_to_mm(ds.m_MinClearance),
            "min_track": coords.nm_to_mm(ds.m_TrackMinWidth),
            "min_annular": coords.nm_to_mm(ds.m_ViasMinAnnularWidth),
            "min_via_diameter": coords.nm_to_mm(ds.m_ViasMinSize),
            "min_drill": coords.nm_to_mm(ds.m_MinThroughDrill),
            "hole_to_hole": coords.nm_to_mm(ds.m_HoleToHoleMin),
            "hole_clearance": coords.nm_to_mm(ds.m_HoleClearance),
            "copper_to_edge": coords.nm_to_mm(ds.m_CopperEdgeClearance),
        },
        "netclasses": {str(board.FindNet(n).GetNetname()): str(board.FindNet(n).GetNetClassName())
                       for n in sorted(str(k) for k in board.GetNetsByName().keys()) if n},
        "footprints": fps,
        "zones": zones,
        "track_count": sum(1 for t in tracks if not isinstance(t, pcbnew.PCB_VIA)),
        "via_count": sum(1 for t in tracks if isinstance(t, pcbnew.PCB_VIA)),
        "edge_bbox": [round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4)],
        "aux_origin": list(coords.from_kicad_nm(ds.GetAuxOrigin().x, ds.GetAuxOrigin().y)),
    }


__all__ = [
    "BoardFiles", "BoardBuildError", "ApplyResult", "build_board", "write_project", "project_dict",
    "write_fp_lib_table", "stackup_sexpr", "load_board", "save_board", "apply_routing",
    "clear_routing", "read_routing", "board_summary", "kicad_point", "design_point",
    "layer_id", "SEVERITY_OVERRIDES", "DEFAULT_SEVERITIES", "CORE_ERROR_CHECKS",
]
