"""Design model: pins, nets, rules, stack-up."""
import dataclasses

import pytest

from gleda.model import (Design, Circle, Part, Pin, US_4L_STD, Stackup, make_pin, two_pin,
                         n_pin, parse_node, copper_layer_names)


def test_model_does_not_import_pcbnew():
    import subprocess, sys, os
    tools = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    code = ("import sys; sys.path.insert(0, %r); import gleda.model, gleda.coords; "
            "assert 'pcbnew' not in sys.modules; print('ok')" % tools)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.stdout.strip() == "ok", out.stderr


def test_default_rule_set_values():
    r = US_4L_STD
    assert r.name == "US_4L_STD"
    assert (r.min_track, r.min_clearance) == (0.127, 0.127)
    assert (r.via_diameter, r.via_drill) == (0.50, 0.25)
    assert r.min_annular == 0.125 and r.hole_to_hole == 0.25
    assert r.copper_to_edge == 0.30
    assert (r.default_track, r.power_track) == (0.15, 0.30)
    assert r.blind_buried_vias is False
    assert r.validate() == []


def test_rules_are_a_parameter_object():
    r = dataclasses.replace(US_4L_STD, name="FINE", min_track=0.09, default_track=0.1)
    d = Design("x", Circle(0, 0, 5), rules=r)
    assert d.rules.name == "FINE"
    assert d.netclasses["Default"].track_width == 0.1
    bad = dataclasses.replace(US_4L_STD, via_diameter=0.4)
    assert any("annular" in p for p in bad.validate())


def test_pin_shorthand_forms():
    assert make_pin("A", "5") == Pin("A", ("5",), "passive")
    assert make_pin("A", 5) == Pin("A", ("5",), "passive")
    assert make_pin("A", ("5", "input")) == Pin("A", ("5",), "input")
    assert make_pin("G", (("6", "7"), "power_in")) == Pin("G", ("6", "7"), "power_in")
    assert make_pin("G", ["6", "7"]) == Pin("G", ("6", "7"), "passive")
    assert make_pin("B", Pin("x", ("1",), "output")) == Pin("B", ("1",), "output")
    with pytest.raises(ValueError):
        Pin("A", ("1",), "tristate")


def test_pin_helpers():
    assert list(two_pin()) == ["1", "2"]
    pins = n_pin(3, "passive", {"MP": ("MP", "passive")})
    assert list(pins) == ["1", "2", "3", "MP"]
    p = Part("R1", "1k", "Resistor_SMD:R_0402_1005Metric")
    assert set(p.pins) == {"1", "2"}
    assert p.pad_numbers() == {"1", "2"}


def test_parse_node_allows_dots_in_pin_names():
    assert parse_node("U1.VDD") == ("U1", "VDD")
    assert parse_node("U1.P0.13") == ("U1", "P0.13")
    assert parse_node(("U1", "P0.13")) == ("U1", "P0.13")
    with pytest.raises(ValueError):
        parse_node("U1")


def test_nets_and_connectivity():
    d = Design("x", Circle(0, 0, 5))
    d.add(Part("U1", "IC", "Package_LGA:Bosch_LGA-14_3x2.5mm_P0.5mm",
               pins={"GND": (("6", "7"), "power_in"), "VDD": ("8", "power_in")}),
          Part("C1", "1u", "Capacitor_SMD:C_0402_1005Metric"))
    d.net("GND", "U1.GND", "C1.2")
    net = d.net("+3V0", "U1.VDD", netclass="Power", width=0.4, max_vias=2)
    d.net("+3V0", "C1.1")                       # extend
    d.net("+3V0", "C1.1")                       # idempotent
    assert net.nodes == [("U1", "VDD"), ("C1", "1")]
    assert d.pin_net("U1", "GND") == "GND"
    assert d.pad_nets("U1") == {"6": "GND", "7": "GND", "8": "+3V0"}
    assert d.net_pads("GND") == [("U1", "6"), ("U1", "7"), ("C1", "2")]
    assert d.connectivity() == {"GND": {"U1.6", "U1.7", "C1.2"}, "+3V0": {"U1.8", "C1.1"}}
    assert d.track_width("+3V0") == 0.4
    assert d.track_width("GND") == 0.15
    assert d.netclass_of("+3V0").name == "Power"
    assert d.is_ground("GND") and d.is_ground("AGND") and not d.is_ground("+3V0")
    with pytest.raises(TypeError):
        d.net("X", bogus=1)
    nl = d.netlist()
    assert nl["nets"]["GND"]["pads"] == ["U1.6", "U1.7", "C1.2"]


def test_planes_and_signal_layers():
    d = Design("x", Circle(0, 0, 5))
    assert d.copper_layers == ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")
    d.net("GND")
    d.net("+3V0")
    d.add_plane("GND", "In1.Cu")
    assert d.signal_layers() == ("F.Cu", "In2.Cu", "B.Cu")
    d.add_plane("+3V0", "In2.Cu")
    d.add_plane("GND", "B.Cu")                  # outer-layer pour does not block routing
    assert d.signal_layers() == ("F.Cu", "B.Cu")
    assert d.plane_layers("GND") == ["In1.Cu", "B.Cu"]
    assert d.full_plane_layers() == {"In1.Cu": "GND", "In2.Cu": "+3V0", "B.Cu": "GND"}


def test_copper_layer_names():
    assert copper_layer_names(2) == ("F.Cu", "B.Cu")
    assert copper_layer_names(6) == ("F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu")
    with pytest.raises(ValueError):
        copper_layer_names(3)


def test_stackup_thickness_and_order():
    s = Stackup.standard(4, 0.8)
    assert abs(s.thickness - 0.8) < 1e-9
    assert s.copper_layers == ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")
    kinds = [l.kind for l in s.layers]
    assert kinds == ["silk", "paste", "mask", "copper", "prepreg", "copper", "core",
                     "copper", "prepreg", "copper", "mask", "paste", "silk"]
    s16 = Stackup.standard(4, 1.6)
    assert abs(s16.thickness - 1.6) < 1e-9
    with pytest.raises(ValueError):
        Stackup.standard(4, 0.3)


def test_part_placement_and_validation():
    p = Part("U1", "x", "Lib:Name", pins={"A": "1"})
    assert not p.placed
    p.place(1.0, 2.0, 90, "bottom")
    assert p.placed and p.side == "bottom" and p.rotation == 90.0
    with pytest.raises(ValueError):
        Part("U2", "x", "Lib:Name", side="left")
    with pytest.raises(ValueError):
        Design("bad name", Circle(0, 0, 1))


def test_mini_design_shape(mini):
    assert len(mini.parts) == 19
    assert {"main", "mcu", "power", "sensor"} == set(mini.groups)
    assert mini.to_dict()["rules"]["name"] == "US_4L_STD"
    assert mini.nets["VBAT"].power_flag
