"""ERC-style and placement checks on a :class:`gleda.model.Design`.

``run_checks(design)`` returns a :class:`CheckReport` with structured
:class:`Finding` objects (severity "error" or "warning", a machine readable
``code``, a message and the refs / net involved) and can render a text report.

Check codes
-----------
Electrical (pure model):

=====================  ========  ==============================================
code                   severity  meaning
=====================  ========  ==============================================
duplicate_ref          error     two parts share a reference
net_unknown_part       error     a net node names a part that does not exist
net_unknown_pin        error     a net node names a pin the part does not have
nc_unknown             error     a no-connect names an unknown part / pin
pin_unconnected        error     pin is on no net and not marked no-connect
pin_multiple_nets      error     pin is on more than one net
nc_connected           error     no-connect pin (explicit or type ``nc``) on a net
single_pin_net         error     net with exactly one pin
empty_net              warning   net without pins
power_in_undriven      error     power_in pin on a net with no power_out and no
                                 ``power_flag`` (ground nets are exempt)
output_conflict        error     two output / power_out pins on one net
netclass_unknown       error     net refers to an undefined net class
rule_violation         error     rule set / net class / net option inconsistent
                                 (class track or clearance below the board
                                 minimum, bad via, unknown layer, bad
                                 ``via_tenting``, name unusable in a DRC rule)
plane_invalid          error     plane on an unknown net or non-copper layer
net_name_case          warning   two net names differ only in upper / lower case
=====================  ========  ==============================================

Footprint (needs pcbnew to read the footprint):

=====================  ========  ==============================================
footprint_missing      error     footprint cannot be loaded
pad_missing            error     pin mapped to a pad the footprint lacks
pad_unmapped           error     numbered footprint pad not mapped by any pin
pad_multiple_pins      error     pad number claimed by two pins
pad_clearance_override warning   pad clearance override below the board minimum
                                 (KiCad silently raises it to the minimum)
=====================  ========  ==============================================

BOM / placement:

=====================  ========  ==============================================
missing_mpn            error     purchasable, fitted part without MPN
missing_bom_field      warning   no manufacturer / distributor PN / (dnp) MPN
missing_height         warning   no component height for the mechanical export
not_placed             error     part has no x/y
courtyard_overlap      error     courtyards of two parts on one side overlap
outside_outline        error     courtyard crosses the board edge or a cutout
in_keepout             error     courtyard inside a no-footprint keep-out
pad_in_keepout         error     pad copper inside a no-pads keep-out
keepout_blocks_pad     warning   connected pad lies completely inside a no-track
                                 keep-out on its only copper layer
hole_collision         error     courtyard or pad over an NPTH hole
pad_edge_clearance     error     pad copper closer to the edge than the rule
pad_spacing            error     two pads of one part on different nets are closer
                                 than the clearance KiCad's DRC will require
missing_decoupling     error     IC power pin net has no capacitor to ground
decoupling_far         warning   nearest decoupling capacitor is far from the pin
=====================  ========  ==============================================
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from .model import Design, Part, TOP, BOTTOM, VIA_TENTING

ERROR = "error"
WARNING = "warning"

_AREA_EPS = 1e-4          # mm^2: overlaps smaller than this are numerical noise
_DIST_EPS = 1e-6


@dataclass(frozen=True)
class Finding:
    """One check result."""
    severity: str
    code: str
    message: str
    refs: Tuple[str, ...] = ()
    net: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"severity": self.severity, "code": self.code, "message": self.message,
                "refs": list(self.refs), "net": self.net}

    def __str__(self) -> str:
        return "%-7s [%s] %s" % (self.severity.upper(), self.code, self.message)


class CheckError(Exception):
    """Raised by :meth:`CheckReport.raise_if_errors`."""

    def __init__(self, report: "CheckReport"):
        self.report = report
        super().__init__("design checks failed: %d error(s)\n%s" % (
            len(report.errors), "\n".join(str(f) for f in report.errors)))


@dataclass
class CheckReport:
    """Collected findings."""
    design: str
    findings: List[Finding] = field(default_factory=list)

    @property
    def errors(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == ERROR]

    @property
    def warnings(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == WARNING]

    @property
    def ok(self) -> bool:
        """True when there are no errors (warnings allowed)."""
        return not self.errors

    def codes(self, severity: Optional[str] = None) -> Dict[str, int]:
        """code -> count (optionally for one severity)."""
        out: Dict[str, int] = {}
        for f in self.findings:
            if severity is None or f.severity == severity:
                out[f.code] = out.get(f.code, 0) + 1
        return dict(sorted(out.items()))

    def has(self, code: str) -> bool:
        return any(f.code == code for f in self.findings)

    def find(self, code: str) -> List[Finding]:
        return [f for f in self.findings if f.code == code]

    def add(self, severity: str, code: str, message: str, refs: Iterable[str] = (),
            net: Optional[str] = None) -> None:
        self.findings.append(Finding(severity, code, message, tuple(refs), net))

    def error(self, code: str, message: str, refs: Iterable[str] = (),
              net: Optional[str] = None) -> None:
        self.add(ERROR, code, message, refs, net)

    def warning(self, code: str, message: str, refs: Iterable[str] = (),
                net: Optional[str] = None) -> None:
        self.add(WARNING, code, message, refs, net)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "design": self.design,
            "ok": self.ok,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors_by_code": self.codes(ERROR),
            "warnings_by_code": self.codes(WARNING),
            "findings": [f.to_dict() for f in self.findings],
        }

    def text(self) -> str:
        """Human readable report."""
        lines = ["gleda checks for %s: %d error(s), %d warning(s)" % (
            self.design, len(self.errors), len(self.warnings))]
        for f in self.errors + self.warnings:
            lines.append(str(f))
        if not self.findings:
            lines.append("no findings")
        return "\n".join(lines) + "\n"

    def raise_if_errors(self) -> "CheckReport":
        if not self.ok:
            raise CheckError(self)
        return self


def _bad_rule_name(name: str) -> bool:
    """True if a net / net-class name cannot be quoted inside a KiCad custom
    rule condition (see :func:`gleda.board.custom_rules_text`)."""
    return not name or any(ch in name for ch in "'\"\\*?") or name != name.strip()


# --------------------------------------------------------------------------
# electrical checks (pure model)
# --------------------------------------------------------------------------

def check_electrical(design: Design, report: CheckReport) -> None:
    """Connectivity / ERC checks that need only the model."""
    parts: Dict[str, Part] = {}
    for p in design.parts:
        if p.ref in parts:
            report.error("duplicate_ref", "reference %s is used more than once" % p.ref,
                         [p.ref])
        else:
            parts[p.ref] = p

    for problem in design.rules.validate():
        report.error("rule_violation", "rule set %s: %s" % (design.rules.name, problem))
    for nc in design.netclasses.values():
        if nc.track_width < design.rules.min_track - 1e-9:
            report.error("rule_violation", "net class %s track %.3f < min track %.3f"
                         % (nc.name, nc.track_width, design.rules.min_track))
        if nc.clearance < design.rules.min_clearance - 1e-9:
            report.error("rule_violation", "net class %s clearance %.3f < min clearance %.3f"
                         % (nc.name, nc.clearance, design.rules.min_clearance))
        if (nc.via_diameter - nc.via_drill) / 2.0 < design.rules.min_annular - 1e-9:
            report.error("rule_violation", "net class %s via %.3f/%.3f violates min annular "
                         "ring %.3f" % (nc.name, nc.via_diameter, nc.via_drill,
                                        design.rules.min_annular))
        if nc.via_drill < design.rules.min_drill - 1e-9:
            report.error("rule_violation", "net class %s via drill %.3f < min drill %.3f"
                         % (nc.name, nc.via_drill, design.rules.min_drill))
        if nc.via_diameter < design.rules.min_via_diameter - 1e-9:
            report.error("rule_violation", "net class %s via diameter %.3f < min via "
                         "diameter %.3f" % (nc.name, nc.via_diameter,
                                            design.rules.min_via_diameter))
        if nc.min_track_width is not None:
            if nc.min_track_width > nc.track_width + 1e-9:
                report.error("rule_violation", "net class %s min_track_width %.3f > its "
                             "track width %.3f" % (nc.name, nc.min_track_width,
                                                   nc.track_width))
            if nc.min_track_width < design.rules.min_track - 1e-9:
                report.error("rule_violation", "net class %s min_track_width %.3f < min "
                             "track %.3f" % (nc.name, nc.min_track_width,
                                             design.rules.min_track))
        if _bad_rule_name(nc.name):
            report.error("rule_violation", "net class name %r cannot be used in a KiCad "
                         "DRC rule (quotes, backslash, * and ? are not allowed)" % nc.name)
    if "Default" not in design.netclasses:
        report.error("rule_violation", "the net class 'Default' is missing")
    if design.via_tenting not in VIA_TENTING:
        report.error("rule_violation", "via_tenting %r is not one of %s"
                     % (design.via_tenting, ", ".join(sorted(VIA_TENTING))))

    # pin -> nets
    pin_nets: Dict[Tuple[str, str], List[str]] = {}
    for net in design.nets.values():
        if net.netclass not in design.netclasses:
            report.error("netclass_unknown", "net %s uses undefined net class %r"
                         % (net.name, net.netclass), net=net.name)
        if net.width is not None and net.width < design.rules.min_track - 1e-9:
            report.error("rule_violation", "net %s width %.3f < min track %.3f"
                         % (net.name, net.width, design.rules.min_track), net=net.name)
        if _bad_rule_name(net.name):
            report.error("rule_violation", "net name %r cannot be used in a KiCad DRC "
                         "rule (quotes, backslash, * and ? are not allowed)" % net.name,
                         net=net.name)
        if net.layers:
            for layer in net.layers:
                if layer not in design.copper_layers:
                    report.error("rule_violation", "net %s: layer %r is not a copper layer "
                                 "of this board" % (net.name, layer), net=net.name)
        valid_nodes = 0
        for ref, pin in net.nodes:
            part = parts.get(ref)
            if part is None:
                report.error("net_unknown_part", "net %s references unknown part %s"
                             % (net.name, ref), [ref], net.name)
                continue
            if pin not in part.pins:
                report.error("net_unknown_pin", "net %s references %s.%s but %s has no such "
                             "pin" % (net.name, ref, pin, ref), [ref], net.name)
                continue
            valid_nodes += 1
            pin_nets.setdefault((ref, pin), []).append(net.name)
        if valid_nodes == 0:
            report.warning("empty_net", "net %s has no pins" % net.name, net=net.name)
        elif valid_nodes == 1:
            ref, pin = next((r, p) for r, p in net.nodes if r in parts and p in parts[r].pins)
            report.error("single_pin_net", "net %s has only one pin (%s.%s)"
                         % (net.name, ref, pin), [ref], net.name)

    by_lower: Dict[str, str] = {}
    for name in design.nets:
        other = by_lower.setdefault(name.lower(), name)
        if other != name:
            report.warning("net_name_case", "nets %s and %s differ only in case; KiCad's "
                           "DRC rule conditions may not tell them apart" % (other, name),
                           net=name)

    for ref, pin in sorted(design.no_connects):
        if ref not in parts or pin not in parts[ref].pins:
            report.error("nc_unknown", "no-connect %s.%s does not exist" % (ref, pin), [ref])

    for part in parts.values():
        for pin in part.pins.values():
            nets = pin_nets.get((part.ref, pin.name), [])
            is_nc = pin.etype == "nc" or (part.ref, pin.name) in design.no_connects
            if len(nets) > 1:
                report.error("pin_multiple_nets", "%s.%s is on several nets: %s"
                             % (part.ref, pin.name, ", ".join(nets)), [part.ref])
            if nets and is_nc:
                report.error("nc_connected", "%s.%s is marked no-connect but is on net %s"
                             % (part.ref, pin.name, nets[0]), [part.ref], nets[0])
            if not nets and not is_nc:
                report.error("pin_unconnected", "%s.%s (%s) is not connected and not marked "
                             "no-connect" % (part.ref, pin.name, pin.etype), [part.ref])

    # driver / power checks
    for net in design.nets.values():
        types: List[Tuple[str, str, str]] = []
        for ref, pin in net.nodes:
            part = parts.get(ref)
            if part is not None and pin in part.pins:
                types.append((ref, pin, part.pins[pin].etype))
        drivers = [(r, p, t) for r, p, t in types if t in ("output", "power_out")]
        if len(drivers) > 1:
            report.error("output_conflict", "net %s has several drivers: %s" % (
                net.name, ", ".join("%s.%s (%s)" % d for d in drivers)),
                [d[0] for d in drivers], net.name)
        power_in = [(r, p) for r, p, t in types if t == "power_in"]
        has_source = any(t == "power_out" for _, _, t in types)
        if power_in and not has_source and not net.power_flag \
                and not design.is_ground(net.name):
            report.error("power_in_undriven", "net %s feeds power input(s) %s but has no "
                         "power_out pin (set power_flag=True if it is driven externally)"
                         % (net.name, ", ".join("%s.%s" % rp for rp in power_in[:6])
                            + (" ..." if len(power_in) > 6 else "")),
                         sorted({r for r, _ in power_in}), net.name)

    for plane in design.planes:
        if plane.net not in design.nets:
            report.error("plane_invalid", "plane on %s uses unknown net %r"
                         % (plane.layer, plane.net), net=plane.net)
        if plane.layer not in design.copper_layers:
            report.error("plane_invalid", "plane for net %s on %r which is not a copper "
                         "layer of this board" % (plane.net, plane.layer), net=plane.net)
    for ko in design.keepouts:
        for layer in ko.layer_names(design.copper_layers):
            if layer not in design.copper_layers:
                report.error("rule_violation", "keep-out %r on unknown layer %r"
                             % (ko.name, layer))


# --------------------------------------------------------------------------
# BOM checks
# --------------------------------------------------------------------------

def check_bom(design: Design, report: CheckReport) -> None:
    """MPN and sourcing fields."""
    for part in design.parts:
        if not part.in_bom:
            continue
        if not part.mpn:
            if part.dnp:
                report.warning("missing_bom_field", "%s (DNP) has no MPN" % part.ref,
                               [part.ref])
            else:
                report.error("missing_mpn", "%s (%s) has no MPN" % (part.ref, part.value),
                             [part.ref])
        if not part.manufacturer:
            report.warning("missing_bom_field", "%s has no manufacturer" % part.ref,
                           [part.ref])
        if not part.distributor_pn and not part.dnp:
            report.warning("missing_bom_field", "%s has no distributor part number"
                           % part.ref, [part.ref])
        if part.height_mm is None:
            report.warning("missing_height", "%s has no height_mm (needed by the mechanical "
                           "export)" % part.ref, [part.ref])


# --------------------------------------------------------------------------
# footprint / placement checks
# --------------------------------------------------------------------------

def check_footprints(design: Design, report: CheckReport) -> Dict[str, Any]:
    """Pin <-> pad mapping against the real footprint.  Returns ref -> geom
    for parts whose footprint loaded."""
    from . import footprints
    geoms: Dict[str, Any] = {}
    for part in design.parts:
        try:
            geom = footprints.resolve(part.footprint)
        except footprints.FootprintError as exc:
            report.error("footprint_missing", "%s: %s" % (part.ref, exc), [part.ref])
            continue
        geoms[part.ref] = geom
        available = set(geom.pad_numbers)
        claimed: Dict[str, str] = {}
        for pin in part.pins.values():
            for pad in pin.pads:
                if pad not in available:
                    report.error("pad_missing", "%s pin %s maps to pad %r which footprint %s "
                                 "does not have" % (part.ref, pin.name, pad, geom.lib_id),
                                 [part.ref])
                if pad in claimed and claimed[pad] != pin.name:
                    report.error("pad_multiple_pins", "%s pad %r is mapped by pins %s and %s"
                                 % (part.ref, pad, claimed[pad], pin.name), [part.ref])
                claimed.setdefault(pad, pin.name)
        low = sorted({p.clearance for p in geom.pads
                      if p.clearance and p.clearance < design.rules.min_clearance - 1e-9})
        if low:
            report.warning("pad_clearance_override", "%s: footprint %s has pad clearance "
                           "override(s) %s mm below the board minimum %.3f mm; KiCad uses "
                           "the board minimum" % (part.ref, geom.lib_id,
                                                  ", ".join("%.3f" % c for c in low),
                                                  design.rules.min_clearance), [part.ref])
        unmapped = [n for n in geom.pad_numbers if n not in claimed]
        if unmapped:
            report.error("pad_unmapped", "%s: footprint %s pad(s) %s are not mapped by any pin"
                         % (part.ref, geom.lib_id, ", ".join(unmapped[:12])
                            + (" ..." if len(unmapped) > 12 else "")), [part.ref])
    return geoms


def _sides_occupied(part: Part, geom) -> Tuple[str, ...]:
    """Board sides a part blocks for other components."""
    if not geom.smd and any(p.kind == "th" for p in geom.pads):
        return (TOP, BOTTOM)
    return (part.side,)


def check_placement(design: Design, report: CheckReport, geoms: Dict[str, Any]) -> None:
    """Courtyard-level placement checks (per side)."""
    from . import geometry
    from shapely.geometry import Point as SPoint

    try:
        board = geometry.outline_polygon(design.outline)
    except ValueError as exc:
        report.error("outside_outline", "board outline is invalid: %s" % exc)
        return
    rules = design.rules
    holes = [(h, SPoint(h.x, h.y).buffer(h.drill / 2.0, 32)) for h in design.outline.holes]

    placed: List[Tuple[Part, Any, Any]] = []       # (part, geom, courtyard polygon)
    seen: Set[str] = set()
    for part in design.parts:
        if part.ref in seen:
            continue
        seen.add(part.ref)
        if not part.placed:
            report.error("not_placed", "%s has no placement" % part.ref, [part.ref])
            continue
        geom = geoms.get(part.ref)
        if geom is None:
            continue
        placed.append((part, geom, geometry.part_courtyard(part)))

    # courtyard overlaps
    for i in range(len(placed)):
        pa, ga, ca = placed[i]
        sides_a = _sides_occupied(pa, ga)
        for j in range(i + 1, len(placed)):
            pb, gb, cb = placed[j]
            if not set(sides_a) & set(_sides_occupied(pb, gb)):
                continue
            if not ca.intersects(cb):
                continue
            area = ca.intersection(cb).area
            if area > _AREA_EPS:
                report.error("courtyard_overlap", "courtyards of %s and %s overlap (%.3f mm^2) "
                             "on the %s side" % (pa.ref, pb.ref, area, pa.side
                                                 if pa.side == pb.side else "top/bottom"),
                             [pa.ref, pb.ref])

    boundary = board.boundary
    for part, geom, cy in placed:
        # outline
        if not part.allow_overhang:
            outside = cy.difference(board).area
            if outside > _AREA_EPS:
                report.error("outside_outline", "%s courtyard extends %.3f mm^2 beyond the "
                             "board outline / into a cutout" % (part.ref, outside), [part.ref])
        # NPTH holes
        for hole, hpoly in holes:
            if cy.intersects(hpoly) and cy.intersection(hpoly).area > _AREA_EPS:
                report.error("hole_collision", "%s courtyard overlaps NPTH hole at (%.2f, %.2f)"
                             % (part.ref, hole.x, hole.y), [part.ref])
        # keep-outs
        side_layer = "F.Cu" if part.side == TOP else "B.Cu"
        occupied_layers = {"F.Cu", "B.Cu"} if len(_sides_occupied(part, geom)) == 2 \
            else {side_layer}
        pads = None
        for ko in design.keepouts:
            ko_layers = set(ko.layer_names(design.copper_layers))
            ko_poly = None
            if ko.footprints and ko_layers & occupied_layers:
                ko_poly = geometry.keepout_polygon(ko)
                if cy.intersects(ko_poly) and cy.intersection(ko_poly).area > _AREA_EPS:
                    report.error("in_keepout", "%s courtyard is inside keep-out %s"
                                 % (part.ref, ko.name or "(unnamed)"), [part.ref])
            if ko.pads:
                ko_poly = ko_poly or geometry.keepout_polygon(ko)
                pads = pads if pads is not None else geometry.part_pads(design, part)
                for pad in pads:
                    if pad.polygon is None or not (set(pad.layers) & ko_layers):
                        continue
                    if pad.polygon.intersects(ko_poly) and \
                            pad.polygon.intersection(ko_poly).area > _AREA_EPS:
                        report.error("pad_in_keepout", "%s pad %s is inside keep-out %s"
                                     % (part.ref, pad.number, ko.name or "(unnamed)"),
                                     [part.ref])
            elif ko.tracks and ko_layers & occupied_layers:
                # a connected pad buried in a no-track area cannot be routed
                ko_poly = ko_poly or geometry.keepout_polygon(ko)
                pads = pads if pads is not None else geometry.part_pads(design, part)
                for pad in pads:
                    if pad.polygon is None or not pad.net or not pad.layers:
                        continue
                    if set(pad.layers) <= ko_layers and ko_poly.contains(pad.polygon):
                        report.warning("keepout_blocks_pad", "%s pad %s (net %s) lies "
                                       "completely inside the no-track keep-out %s"
                                       % (part.ref, pad.number, pad.net,
                                          ko.name or "(unnamed)"), [part.ref], pad.net)
        # pad copper to board edge / holes
        if not part.allow_overhang:
            pads = pads if pads is not None else geometry.part_pads(design, part)
            worst: Optional[Tuple[float, str]] = None
            for pad in pads:
                if pad.polygon is None:
                    continue
                if not board.contains(pad.polygon):
                    d = -1.0
                else:
                    d = pad.polygon.distance(boundary)
                if d < rules.copper_to_edge - _DIST_EPS and (worst is None or d < worst[0]):
                    worst = (d, pad.number)
                for hole, hpoly in holes:
                    if pad.polygon.distance(hpoly) < rules.hole_clearance - _DIST_EPS:
                        report.error("hole_collision", "%s pad %s is closer than %.2f mm to "
                                     "the NPTH hole at (%.2f, %.2f)" % (
                                         part.ref, pad.number, rules.hole_clearance,
                                         hole.x, hole.y), [part.ref])
            if worst is not None:
                if worst[0] < 0:
                    msg = "%s pad %s is outside the board" % (part.ref, worst[1])
                else:
                    msg = "%s pad %s is %.3f mm from the board edge (min %.3f)" % (
                        part.ref, worst[1], worst[0], rules.copper_to_edge)
                report.error("pad_edge_clearance", msg, [part.ref])
        # pads of this part against each other (land pattern vs. the rules)
        pads = pads if pads is not None else geometry.part_pads(design, part)
        _check_pad_spacing(design, report, part, pads)


def _check_pad_spacing(design: Design, report: CheckReport, part: Part, pads) -> None:
    """Pads of one part on different nets must keep the clearance KiCad's DRC
    will ask for (:meth:`Design.clearance`, pad overrides included).  Pad
    polygons lie slightly inside the true copper, so a finding here is always
    real; marginal cases are left to KiCad."""
    items = [(p, p.polygon.bounds) for p in pads if p.polygon is not None]
    found = 0
    for i in range(len(items)):
        a, ba = items[i]
        for j in range(i + 1, len(items)):
            b, bb = items[j]
            if a.number == b.number or (a.net is not None and a.net == b.net):
                continue
            if not set(a.layers) & set(b.layers):
                continue
            need = design.clearance(a.net, b.net, local_a=a.clearance, local_b=b.clearance)
            if bb[0] - ba[2] >= need or ba[0] - bb[2] >= need \
                    or bb[1] - ba[3] >= need or ba[1] - bb[3] >= need:
                continue
            gap = a.polygon.distance(b.polygon)
            if gap < need - _DIST_EPS:
                found += 1
                if found <= 4:
                    report.error("pad_spacing", "%s pads %s (%s) and %s (%s) are %.3f mm "
                                 "apart, KiCad will require %.3f mm" % (
                                     part.ref, a.number, a.net or "no net", b.number,
                                     b.net or "no net", gap, need), [part.ref])
    if found > 4:
        report.error("pad_spacing", "%s: %d more pad pairs are too close"
                     % (part.ref, found - 4), [part.ref])


def check_decoupling(design: Design, report: CheckReport, max_distance: Optional[float] = 6.0,
                     geoms: Optional[Dict[str, Any]] = None) -> None:
    """Every IC power pin net needs a capacitor to ground on the same net.

    A decoupling capacitor is a two-pin part whose reference starts with "C"
    with one pin on the supply net and the other on a ground net
    (:meth:`Design.is_ground`).  When placements and footprints are available
    the nearest such capacitor must be within ``max_distance`` mm of the pin
    (warning otherwise; ``None`` disables the distance check)."""
    parts = design.parts_by_ref
    caps_by_net: Dict[str, List[Part]] = {}
    for part in parts.values():
        if part.ref_prefix != "C" or len(part.pins) != 2 or part.dnp:
            continue
        nets = [design.pin_net(part.ref, pin) for pin in part.pins]
        if None in nets:
            continue
        a, b = nets
        if design.is_ground(a) and not design.is_ground(b):
            caps_by_net.setdefault(b, []).append(part)
        elif design.is_ground(b) and not design.is_ground(a):
            caps_by_net.setdefault(a, []).append(part)
    reported: Set[Tuple[str, str]] = set()
    for part in parts.values():
        if not part.ic:
            continue
        for pin in part.pins.values():
            if pin.etype != "power_in":
                continue
            net = design.pin_net(part.ref, pin.name)
            if net is None or design.is_ground(net):
                continue
            caps = caps_by_net.get(net, [])
            if not caps:
                if (part.ref, net) not in reported:
                    reported.add((part.ref, net))
                    report.error("missing_decoupling", "%s power pin %s (net %s) has no "
                                 "decoupling capacitor to ground" % (part.ref, pin.name, net),
                                 [part.ref], net)
                continue
            if max_distance is None or geoms is None or part.ref not in geoms \
                    or not part.placed:
                continue
            from . import geometry
            try:
                px, py = geometry.pad_position(design, part.ref, pin.pads[0])
            except KeyError:
                continue
            best: Optional[Tuple[float, str]] = None
            for cap in caps:
                if not cap.placed:
                    continue
                d = math.hypot(cap.x - px, cap.y - py)
                if best is None or d < best[0]:
                    best = (d, cap.ref)
            if best is not None and best[0] > max_distance and (part.ref, net) not in reported:
                reported.add((part.ref, net))
                report.warning("decoupling_far", "%s pin %s (net %s): nearest decoupling "
                               "capacitor %s is %.1f mm away (> %.1f mm)" % (
                                   part.ref, pin.name, net, best[1], best[0], max_distance),
                               [part.ref, best[1]], net)


def run_checks(design: Design, *, footprints: bool = True, placement: bool = True,
               bom: bool = True, decoupling: bool = True,
               decoupling_max_distance: Optional[float] = 6.0) -> CheckReport:
    """Run all checks and return the :class:`CheckReport`.

    ``footprints=False`` skips everything that needs pcbnew (pad mapping and
    placement geometry); ``placement=False`` skips only the geometric
    placement checks."""
    report = CheckReport(design.name)
    check_electrical(design, report)
    if bom:
        check_bom(design, report)
    geoms: Optional[Dict[str, Any]] = None
    if footprints:
        geoms = check_footprints(design, report)
        if placement:
            check_placement(design, report, geoms)
    elif placement:
        for part in design.parts:
            if not part.placed:
                report.error("not_placed", "%s has no placement" % part.ref, [part.ref])
    if decoupling:
        check_decoupling(design, report, decoupling_max_distance, geoms)
    return report


__all__ = ["Finding", "CheckReport", "CheckError", "run_checks", "check_electrical",
           "check_bom", "check_footprints", "check_placement", "check_decoupling",
           "ERROR", "WARNING"]
