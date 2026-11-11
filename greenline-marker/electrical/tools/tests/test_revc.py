"""Features the rev C GreenLine board needs beyond the first core: non-plated
locating hole and slot, per-side placement keep-outs (tub post feet),
height-limited zones (camera hoods), planes that share their layer with
tracks - each one checked in the model, in the checks and, where KiCad has an
opinion, by KiCad's DRC.
"""
import pytest

from gleda import board, checks, drc, geometry
from gleda import footprints as F
from gleda.model import (Design, Outline, RoundedPolygon, PathShape, Part, HeightLimit,
                         two_pin, US_4L_STD, BOTTOM, TOP)

R0402 = "Resistor_SMD:R_0402_1005Metric"
SOT23 = "Package_TO_SOT_SMD:SOT-23"


def _board(name="revc"):
    outline = Outline(PathShape.d_shape(21.1, 17.3))
    return Design(name, outline, layers=4, rules=US_4L_STD)


def _res(ref, x, y, rot=0.0, side=TOP, height=0.4):
    return Part(ref, "10k", R0402, pins=two_pin(), mpn="RC0402FR-0710KL", manufacturer="Yageo",
                distributor="Digi-Key", distributor_pn="311-10.0KLRCT-ND", unit_price=0.01,
                x=x, y=y, rotation=rot, side=side, height_mm=height)


def _wire(d, *refs):
    """Give every part a net so that the electrical checks stay quiet."""
    for i, ref in enumerate(refs):
        d.net("N%d" % i, "%s.1" % ref, "%s.2" % ref)


# --------------------------------------------------------------------------
# outline: D shape with locating hole and slot
# --------------------------------------------------------------------------

def test_npth_slot_is_a_stadium_cutout():
    outline = Outline(PathShape.d_shape(21.1, 17.3))
    outline.add_hole(-4.2, 14.55, 1.15, name="H1")
    outline.add_npth_slot(4.2, 14.55, width=1.15, length=1.65)
    assert [(h.x, h.y, h.drill) for h in outline.holes] == [(-4.2, 14.55, 1.15)]
    slot = outline.cutouts[0]
    assert (slot.x1, slot.y1, slot.x2, slot.y2, slot.width) == pytest.approx(
        (3.95, 14.55, 4.45, 14.55, 1.15))
    poly = geometry.outline_polygon(outline)
    assert len(poly.interiors) == 1
    xmin, ymin, xmax, ymax = poly.interiors[0].bounds
    assert (xmax - xmin, ymax - ymin) == pytest.approx((1.65, 1.15), abs=0.02)
    # rotated, and the degenerate "slot" that is just a hole
    outline.add_npth_slot(0.0, 0.0, width=1.0, length=2.0, rotation=90.0)
    v = outline.cutouts[1]
    assert (v.x1, v.y1, v.x2, v.y2) == pytest.approx((0.0, -0.5, 0.0, 0.5))
    outline.add_npth_slot(5.0, 5.0, width=1.0, length=1.0)
    assert len(outline.cutouts) == 2 and len(outline.holes) == 2
    with pytest.raises(ValueError):
        outline.add_npth_slot(0.0, 0.0, width=2.0, length=1.0)


def test_outline_radius_and_flat():
    poly = geometry.outline_polygon(Outline(PathShape.d_shape(21.1, 17.3)))
    xmin, ymin, xmax, ymax = poly.bounds
    assert (xmin, ymin, xmax, ymax) == pytest.approx((-21.1, -21.1, 21.1, 17.3), abs=0.01)


# --------------------------------------------------------------------------
# placement keep-outs per side
# --------------------------------------------------------------------------

def test_placement_keepout_is_per_side():
    d = _board()
    ko = d.add_placement_keepout(RoundedPolygon.rect(0.0, 0.0, 1.6, 1.6), side="top",
                                 name="post_foot")
    assert ko.layers == ("F.Cu",) and ko.footprints
    assert not (ko.tracks or ko.vias or ko.copper or ko.pads)     # copper is not restricted
    d.add(_res("R1", 0.5, 0.0), _res("R2", 0.5, 0.0, side=BOTTOM), _res("R3", 5.0, 0.0))
    _wire(d, "R1", "R2", "R3")
    report = checks.run_checks(d, bom=False, decoupling=False)
    hits = report.find("in_keepout")
    assert [f.refs for f in hits] == [("R1",)]
    bottom = d.add_placement_keepout(RoundedPolygon.rect(5.0, 0.0, 1.6, 1.6), side="bottom")
    assert bottom.layers == ("B.Cu",)
    assert not any("R3" in f.refs for f in
                   checks.run_checks(d, bom=False, decoupling=False).find("in_keepout"))
    with pytest.raises(ValueError):
        d.add_placement_keepout(RoundedPolygon.rect(0.0, 0.0, 1.0, 1.0), side="left")


def test_kicad_agrees_on_placement_keepouts_and_leaves_locating_holes_alone(tmp_path):
    """A post foot that sits on a locating hole: the hole (a footprint to
    KiCad) must not be reported, a part in the foot must be."""
    def build(with_part, sub):
        outline = Outline(PathShape.d_shape(21.1, 17.3))
        outline.add_hole(-4.2, 14.55, 1.15, name="H1")
        d = Design("feet", outline, layers=4, rules=US_4L_STD)
        d.add_placement_keepout(RoundedPolygon.rect(-4.2, 14.55, 1.6, 1.6), name="foot_on_hole")
        d.add_placement_keepout(RoundedPolygon.rect(8.0, 0.0, 1.6, 1.6), name="foot")
        d.add(_res("R1", 8.6 if with_part else 12.0, 0.0))
        _wire(d, "R1")
        files = board.build_board(d, str(tmp_path / sub))
        return d, drc.run_drc(files.pcb)

    d, clean = build(False, "clean")
    assert clean.errors_by_type == {}
    assert checks.run_checks(d, bom=False, decoupling=False).find("in_keepout") == []
    d, bad = build(True, "bad")
    assert bad.errors_by_type == {"items_not_allowed": 1}
    assert [f.refs for f in checks.run_checks(d, bom=False, decoupling=False)
            .find("in_keepout")] == [("R1",)]


# --------------------------------------------------------------------------
# height-limited zones
# --------------------------------------------------------------------------

def test_height_limit_zone():
    d = _board()
    hood = d.add_height_limit(RoundedPolygon.rect(-10.0, 15.5, 5.7, 3.6), 0.95, side="top",
                              exempt=("U2",), name="camera_hood")
    assert isinstance(hood, HeightLimit) and d.height_limits == [hood]
    cam = F.bga("Cam", 5, 5, pitch=0.5, pad_d=0.23, body=(3.47, 2.95), height=2.76)
    pins = {"%s%d" % (r, c): ("%s%d" % (r, c), "nc") for r in "ABCDE" for c in range(1, 6)}
    d.add(Part("U2", "cam", cam, pins=pins, x=-10.0, y=15.6, height_mm=2.76, in_bom=False))
    d.add(_res("R1", -8.0, 14.2, height=0.4))            # low part under the hood: fine
    d.add(Part("U7", "LDO", SOT23, pins={"1": ("1", "passive"), "2": ("2", "passive"),
                                         "3": ("3", "passive")},
               x=-12.0, y=12.6, height_mm=1.2, in_bom=False))        # body reaches into the zone
    d.add(_res("R2", -8.0, 15.4, height=None))           # height not given
    d.add(_res("R3", -9.0, 14.0, side=BOTTOM, height=2.0))    # other side: not concerned
    d.add(_res("R4", 5.0, 0.0, height=3.0))              # tall, but elsewhere
    for part in d.parts:
        for pin in part.pins.values():
            d.no_connect("%s.%s" % (part.ref, pin.name))
    report = checks.run_checks(d, bom=False, decoupling=False)
    assert [f.refs for f in report.find("height_limit")] == [("U7",)]
    assert "1.20 mm tall" in report.find("height_limit")[0].message
    assert [f.refs for f in report.find("height_unknown")] == [("R2",)]
    assert not report.ok
    d.part("U7").y = 10.0                                # moved out from under the hood
    d.part("R2").height_mm = 0.4
    report = checks.run_checks(d, bom=False, decoupling=False)
    assert report.find("height_limit") == [] and report.find("height_unknown") == []
    # the limits are part of the design dump for the mechanical team
    dump = d.to_dict()["height_limits"]
    assert dump == [{"name": "camera_hood", "side": "top", "max_height": 0.95, "exempt": ["U2"]}]
    with pytest.raises(ValueError):
        d.add_height_limit(RoundedPolygon.rect(0.0, 0.0, 1.0, 1.0), -1.0)
    with pytest.raises(ValueError):
        d.add_height_limit(RoundedPolygon.rect(0.0, 0.0, 1.0, 1.0), 1.0, side="inner")


# --------------------------------------------------------------------------
# planes that share their layer with tracks
# --------------------------------------------------------------------------

def test_routable_plane_keeps_its_layer_a_signal_layer():
    d = _board()
    d.net("GND")
    d.net("V2V8")
    d.add_plane("GND", "In1.Cu")
    assert d.signal_layers() == ("F.Cu", "In2.Cu", "B.Cu")
    plane = d.add_plane("V2V8", "In2.Cu", routable=True)
    assert plane.routable
    assert d.full_plane_layers() == {"In1.Cu": "GND", "In2.Cu": "V2V8"}
    assert d.routable_plane_layers() == {"In2.Cu": "V2V8"}
    assert d.signal_layers() == ("F.Cu", "In2.Cu", "B.Cu")
    assert d.plane_layers("V2V8") == ["In2.Cu"]
    assert [p["routable"] for p in d.to_dict()["planes"]] == [False, True]
    # a plain plane takes its inner layer away from the router
    e = _board("solid")
    e.net("GND")
    e.net("V2V8")
    e.add_plane("GND", "In1.Cu")
    e.add_plane("V2V8", "In2.Cu")
    assert e.signal_layers() == ("F.Cu", "B.Cu") and e.routable_plane_layers() == {}


# --------------------------------------------------------------------------
# the demo design uses all of it
# --------------------------------------------------------------------------

def test_demo_design_exercises_the_rev_c_features():
    import os
    import sys
    demo_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "demo")
    if demo_dir not in sys.path:
        sys.path.insert(0, demo_dir)
    import demo_design as D
    d = D.demo_design()
    xmin, ymin, xmax, ymax = geometry.outline_polygon(d.outline).bounds
    assert (xmax, ymax) == pytest.approx((21.1, 17.3), abs=0.01)
    assert [(h.x, h.y, h.drill) for h in d.outline.holes] == [(-4.2, 14.55, 1.15)]
    assert len(d.outline.cutouts) == 1                          # the locating slot
    feet = [k for k in d.keepouts if k.name.startswith("post_foot")]
    assert len(feet) == 8 and all(k.footprints and k.layers == ("F.Cu",) for k in feet)
    assert sorted(h.name for h in d.height_limits) == ["camera_hood_U2", "camera_hood_U3"]
    assert all(h.max_height == 0.95 for h in d.height_limits)
    assert {p.ref: (p.x, p.y) for p in d.parts if p.ref in ("U2", "U3")} == {
        "U2": (-10.0, 15.6), "U3": (10.0, 15.6)}
    assert d.routable_plane_layers() == {"In2.Cu": "V2V8"}
    assert d.via_tenting == "bottom"
    bottom = [p.ref for p in d.parts if p.side == BOTTOM]
    assert len([r for r in bottom if r.startswith("D")]) == 16 and "J2" in bottom
    report = checks.run_checks(d)
    assert report.ok, report.text()
