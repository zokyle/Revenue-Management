"""ERC-style and placement checks: every check code is triggered once."""
import dataclasses

import pytest

from gleda import checks
from gleda.model import Design, Circle, RoundedPolygon, Part, US_4L_STD, BOTTOM

C0402 = "Capacitor_SMD:C_0402_1005Metric"
R0402 = "Resistor_SMD:R_0402_1005Metric"


def codes(report, severity=None):
    return set(report.codes(severity))


def test_mini_design_is_clean(mini):
    report = checks.run_checks(mini)
    assert report.ok, report.text()
    assert report.errors == []
    assert "0 error(s)" in report.text()
    assert report.to_dict()["ok"] is True
    report.raise_if_errors()


def test_duplicate_ref(mini):
    mini.add(Part("C1", "1u", C0402, mpn="X", x=0, y=-12))
    assert "duplicate_ref" in codes(checks.run_checks(mini), "error")


def test_unconnected_pin_and_explicit_nc(mini):
    mini.nets["SWDIO"].nodes.remove(("TP1", "1"))
    mini.nets["SWDIO"].nodes.remove(("U1", "SWDIO"))
    r = checks.run_checks(mini)
    msgs = [f.message for f in r.find("pin_unconnected")]
    assert any("U1.SWDIO" in m for m in msgs) and any("TP1.1" in m for m in msgs)
    assert r.has("empty_net")
    mini.no_connect("U1.SWDIO", "TP1.1")
    r2 = checks.run_checks(mini)
    assert not r2.has("pin_unconnected")


def test_single_pin_net(mini):
    mini.nets["SWCLK"].nodes.remove(("TP2", "1"))
    mini.no_connect("TP2.1")
    r = checks.run_checks(mini)
    assert [f.net for f in r.find("single_pin_net")] == ["SWCLK"]
    assert not r.ok


def test_nc_pin_connected_and_unknown_nc(mini):
    mini.net("SCK", "U1.NC")                 # pin of electrical type nc on a net
    mini.no_connect("U1.SCK")                # explicit NC on a connected pin
    mini.no_connect("U9.X", "U1.NOPE")
    r = checks.run_checks(mini)
    assert len(r.find("nc_connected")) == 2
    assert len(r.find("nc_unknown")) == 2


def test_pin_on_two_nets(mini):
    mini.net("MOSI", "U1.SCK")
    assert "pin_multiple_nets" in codes(checks.run_checks(mini), "error")


def test_unknown_part_and_pin_in_net(mini):
    mini.net("SCK", "U7.A", "U1.BOGUS")
    r = checks.run_checks(mini)
    assert r.has("net_unknown_part") and r.has("net_unknown_pin")


def test_power_in_without_source(mini):
    mini.nets["VBAT"].power_flag = False      # only passives + power_in pins remain
    r = checks.run_checks(mini)
    assert [f.net for f in r.find("power_in_undriven")] == ["VBAT"]
    # ground nets never need a source
    assert not any(f.net == "GND" for f in r.find("power_in_undriven"))


def test_two_outputs_shorted(mini):
    mini.nets["IMU_INT"].nodes.append(("U1", "LED1"))      # output + output
    mini.nets["LED1"].nodes.remove(("U1", "LED1"))
    r = checks.run_checks(mini)
    assert [f.net for f in r.find("output_conflict")] == ["IMU_INT"]


def test_two_power_outputs_shorted(mini):
    mini.add(Part("U4", "LDO", "Package_TO_SOT_SMD:SOT-23-5",
                  pins={"VIN": ("1", "power_in"), "GND": ("2", "power_in"),
                        "EN": ("3", "input"), "NC": ("4", "nc"), "VOUT": ("5", "power_out")},
                  mpn="X", x=-2, y=-12, side=BOTTOM))
    mini.net("VBAT", "U4.VIN", "U4.EN")
    mini.net("GND", "U4.GND")
    mini.net("+3V0", "U4.VOUT")
    r = checks.run_checks(mini)
    assert "+3V0" in [f.net for f in r.find("output_conflict")]


def test_pad_mapping_errors():
    d = Design("x", Circle(0, 0, 10))
    d.add(Part("R1", "1k", R0402, pins={"1": "1", "2": "3"}, mpn="X", x=0, y=0),      # pad 3 missing
          Part("R2", "1k", R0402, pins={"A": "1", "B": "1", "C": "2"}, mpn="X", x=3, y=0),
          Part("J1", "FPC", "Connector_FFC-FPC:Hirose_FH12-10S-0.5SH_1x10-1MP_P0.50mm_Horizontal",
               pins={str(i): str(i) for i in range(1, 11)}, mpn="X", x=0, y=5),       # MP unmapped
          Part("X1", "?", "Capacitor_SMD:Nope", mpn="X", x=-4, y=0))
    d.net("A", "R1.1", "R2.A", "X1.1")
    d.net("B", "R1.2", "R2.B", "R2.C", "X1.2", *["J1.%d" % i for i in range(1, 11)])
    r = checks.run_checks(d)
    assert any("pad '3'" in f.message for f in r.find("pad_missing"))
    assert any("R1" in f.refs and "2" in f.message for f in r.find("pad_unmapped"))
    assert any("J1" in f.refs and "MP" in f.message for f in r.find("pad_unmapped"))
    assert [f.refs for f in r.find("pad_multiple_pins")] == [("R2",)]
    assert [f.refs for f in r.find("footprint_missing")] == [("X1",)]


def test_missing_mpn_and_placement(mini):
    mini.part("R1").mpn = ""
    mini.part("C1").x = None
    mini.part("C2").manufacturer = ""
    mini.part("C3").height_mm = None
    r = checks.run_checks(mini)
    assert [f.refs for f in r.find("missing_mpn")] == [("R1",)]
    assert [f.refs for f in r.find("not_placed")] == [("C1",)]
    assert ("C2",) in [f.refs for f in r.find("missing_bom_field")]
    assert [f.refs for f in r.find("missing_height")] == [("C3",)]
    # test pads are not purchasable: no MPN needed
    assert not any("TP1" in f.refs for f in r.find("missing_mpn"))


def test_dnp_part_needs_no_mpn(mini):
    mini.part("R3").mpn = ""
    mini.part("R3").dnp = True
    r = checks.run_checks(mini)
    assert not r.has("missing_mpn")
    assert any("R3" in f.refs for f in r.find("missing_bom_field"))


def test_courtyard_overlap_is_per_side(mini):
    r3 = mini.part("R3")
    c1 = mini.part("C1")
    c1.place(0.0, 12.0, 90.0)                          # free spot on both sides
    r3.place(0.3, 12.0, 90.0)                          # same side: overlap
    r = checks.run_checks(mini)
    assert [set(f.refs) for f in r.find("courtyard_overlap")] == [{"C1", "R3"}]
    r3.side = BOTTOM                                   # other side: fine
    r = checks.run_checks(mini)
    assert not r.has("courtyard_overlap")


def test_part_outside_outline_and_in_cutout(mini):
    mini.part("R1").place(14.6, 0.0)                   # hangs over the board edge
    mini.part("R2").place(8.0, 0.0)                    # inside the round cutout
    r = checks.run_checks(mini)
    outside = {f.refs[0] for f in r.find("outside_outline")}
    assert outside == {"R1", "R2"}
    assert {f.refs[0] for f in r.find("pad_edge_clearance")} == {"R1", "R2"}
    mini.part("R1").allow_overhang = True
    r = checks.run_checks(mini)
    assert {f.refs[0] for f in r.find("outside_outline")} == {"R2"}


def test_pad_too_close_to_edge(mini):
    # courtyard still inside, but the pad copper is nearer than copper_to_edge
    rules = dataclasses.replace(US_4L_STD, copper_to_edge=1.0)
    d = Design("x", Circle(0, 0, 5), rules=rules)
    d.add(Part("R1", "1k", R0402, mpn="X", x=3.6, y=0), Part("R2", "1k", R0402, mpn="X", x=0, y=0))
    d.net("A", "R1.1", "R2.1")
    d.net("B", "R1.2", "R2.2")
    r = checks.run_checks(d)
    assert [f.refs for f in r.find("pad_edge_clearance")] == [("R1",)]
    assert not r.has("outside_outline")


def test_keepout_and_hole_collisions(mini):
    mini.part("TP1").place(-11.0, -6.5, side=BOTTOM)   # inside the bottom "spring" keep-out
    mini.part("R1").place(-11.5, 5.0)                  # on top of an NPTH hole
    r = checks.run_checks(mini)
    assert [f.refs for f in r.find("in_keepout")] == [("TP1",)]
    assert ("R1",) in [f.refs for f in r.find("hole_collision")]
    # the keep-out is bottom-only: a top-side part at the same place is fine
    mini.part("TP1").side = "top"
    r = checks.run_checks(mini)
    assert not r.has("in_keepout")


def test_pads_keepout(mini):
    mini.add_keepout(RoundedPolygon.rect(1.5, -7.25, 2.5, 3.0), layers=("F.Cu",), name="nopads",
                     pads=True, tracks=False, vias=False, copper=False)
    r = checks.run_checks(mini)
    assert {f.refs[0] for f in r.find("pad_in_keepout")} == {"R1", "R2"}


def test_missing_decoupling(mini):
    for ref in ("C1", "C2", "C4", "C5"):               # all +3V0 decouplers
        mini.parts.remove(mini.part(ref))
        for net in mini.nets.values():
            net.nodes = [n for n in net.nodes if n[0] != ref]
    r = checks.run_checks(mini)
    missing = {(f.refs[0], f.net) for f in r.find("missing_decoupling")}
    assert missing == {("U1", "+3V0"), ("U2", "+3V0")}
    # U3.VIN (VBAT) still has C3
    assert not any(f.net == "VBAT" for f in r.find("missing_decoupling"))


def test_decoupling_distance_warning(mini):
    r = checks.run_checks(mini, decoupling_max_distance=1.0)
    assert r.ok
    assert r.has("decoupling_far")
    assert not checks.run_checks(mini, decoupling_max_distance=None).has("decoupling_far")


def test_rule_and_netclass_problems(mini):
    mini.net("SCK", netclass="Missing")
    mini.net("MOSI", width=0.05)
    mini.net("MISO", layers=("In7.Cu",))
    mini.add_netclass("Thin", track_width=0.1)
    mini.add_plane("NOPE", "In1.Cu")
    mini.add_plane("GND", "F.SilkS")
    r = checks.run_checks(mini)
    assert r.has("netclass_unknown")
    assert len(r.find("rule_violation")) == 3
    assert len(r.find("plane_invalid")) == 2
    bad = Design("y", Circle(0, 0, 5), rules=dataclasses.replace(US_4L_STD, via_drill=0.4))
    assert checks.run_checks(bad, footprints=False).has("rule_violation")


def test_checks_without_pcbnew_paths(mini):
    r = checks.run_checks(mini, footprints=False)
    assert r.ok
    mini.part("C1").x = None
    assert checks.run_checks(mini, footprints=False).has("not_placed")


def test_report_structure_and_raise(mini):
    mini.part("R1").mpn = ""
    r = checks.run_checks(mini)
    d = r.to_dict()
    assert d["error_count"] == 1 and d["errors_by_code"] == {"missing_mpn": 1}
    assert d["findings"][0]["refs"] == ["R1"]
    assert "ERROR   [missing_mpn]" in r.text()
    with pytest.raises(checks.CheckError):
        r.raise_if_errors()


def test_net_names_differing_only_in_case(mini):
    mini.net("sck", "R3.1")                       # "SCK" exists already
    r = checks.run_checks(mini, footprints=False)
    assert [f.net for f in r.find("net_name_case")] == ["sck"]
    assert r.find("net_name_case")[0].severity == "warning"


# -- pours, fine areas, fiducials (review findings) ----------------------------

def test_pours_with_a_shape_are_pointed_out_and_overlaps_refused(mini):
    island = RoundedPolygon.rect(0.0, 6.0, 4.0, 3.0)
    mini.add_plane("+3V0", "In2.Cu", shape=island, priority=1)
    report = checks.run_checks(mini)
    assert report.ok
    msgs = [f.message for f in report.find("plane_partial")]
    assert len(msgs) == 1 and "the router connects pads to whole-board planes only" in msgs[0]
    # the same island at the priority of the plane it sits in: KiCad's zones_intersect
    from mini_design import mini_design
    bad = mini_design()
    whole = [p for p in bad.planes if p.shape is None]
    layer = whole[0].layer
    other = [n for n in bad.nets if n != whole[0].net][0]
    bad.add_plane(other, layer, shape=island, priority=whole[0].priority)
    report = checks.run_checks(bad)
    assert "plane_overlap" in codes(report, "error")
    assert "higher priority" in report.find("plane_overlap")[0].message


def _fine_class_design(areas=True, **kw):
    from gleda.model import US_4L_FINE
    from gleda import footprints as F
    d = Design("finechk", RoundedPolygon.rect(0.0, 0.0, 20.0, 12.0), rules=US_4L_FINE, **kw)
    d.add_netclass("Fine", track_width=0.09, clearance=0.09)
    fp = F.bga("ChkBGA9", 3, 3, pitch=0.5, pad_d=0.23, pad_clearance=0.09, height=1.0)
    balls = ["%s%d" % (r, c) for r in "ABC" for c in (1, 2, 3)]
    d.add(Part("U1", "bga", fp, pins={b: (b, "bidir") for b in balls}, mpn="x", x=-4.0, y=0.0,
               height_mm=1.0, is_ic=False))
    d.add(Part("R1", "1k", R0402, mpn="x", x=6.0, y=0.0, height_mm=0.4))
    d.net("SIG", "U1.B2", "R1.1", netclass="Fine")
    d.net("RET", "U1.B3", "R1.2")
    d.no_connect(*["U1.%s" % b for b in balls if b not in ("B2", "B3")])
    if areas:
        d.add_fine_area("U1", margin=3.0)
    return d


def test_fine_class_without_a_fine_area_is_a_warning():
    report = checks.run_checks(_fine_class_design(areas=False), bom=False)
    assert report.ok and "fine_unconfined" in codes(report, "warning")
    assert "may use the fine geometry anywhere on the board" in \
        report.find("fine_unconfined")[0].message
    confined = _fine_class_design()
    assert "fine_unconfined" not in codes(checks.run_checks(confined, bom=False))
    assert confined.fine_areas[0].name == "fine_U1" and confined.fine_areas[0].ref == "U1"


def test_fine_area_mistakes_are_errors():
    d = _fine_class_design()
    d.enforce_track_widths = False                 # nothing would check the confinement
    report = checks.run_checks(d, bom=False)
    assert "fine_area_invalid" in codes(report, "error")
    assert "enforce_track_widths" in report.find("fine_area_invalid")[0].message
    d = _fine_class_design()
    d.add_fine_area(RoundedPolygon.rect(40.0, 0.0, 2.0, 2.0), name="lost")
    assert "fine area lost lies outside the board" in " ".join(
        f.message for f in checks.run_checks(d, bom=False).find("fine_area_invalid"))
    with pytest.raises(ValueError):
        d.add_fine_area(RoundedPolygon.rect(0.0, 0.0, 2.0, 2.0), name="lost")
    d = _fine_class_design()
    d.add_fine_area(RoundedPolygon.rect(0.0, 0.0, 2.0, 2.0), name="it's")
    assert "cannot be used in a DRC rule" in " ".join(
        f.message for f in checks.run_checks(d, bom=False).find("fine_area_invalid"))


def test_fine_pitch_side_without_fiducials_is_a_warning():
    d = _fine_class_design()
    report = checks.run_checks(d, bom=False)
    found = report.find("no_fiducials")
    assert report.ok and len(found) == 1
    assert "the top side has fine-pitch parts (U1) but 0 fiducial(s)" in found[0].message
    d.add_fiducial(-8.5, 4.5)
    d.add_fiducial(8.5, 4.5)
    assert "2 fiducial(s)" in checks.run_checks(d, bom=False).find("no_fiducials")[0].message
    fid = d.add_fiducial(8.5, -4.5)
    report = checks.run_checks(d)
    assert report.find("no_fiducials") == [] and report.ok, report.text()
    # a fiducial is a board-only part: no pins, no MPN, no symbol, not on the BOM
    assert fid.ref == "FID3" and fid.board_only and not fid.in_bom and fid.pins == {}
    assert checks.is_fiducial(fid) and fid not in d.schematic_parts and "board" not in d.groups
    # fiducials on the other side do not count; a 0402-only side needs none
    d.add(Part("R2", "1k", R0402, mpn="x", x=0.0, y=-4.0, side=BOTTOM, height_mm=0.4))
    d.net("SIG", "R2.1")
    d.net("RET", "R2.2")
    assert checks.run_checks(d).find("no_fiducials") == []
    # a fiducial in the way of a part is an ordinary courtyard overlap
    d.add_fiducial(6.0, 0.3, ref="FIDX")
    assert "courtyard_overlap" in codes(checks.run_checks(d), "error")


def test_pads_too_close_to_a_footprint_slot_are_an_error():
    """KiCad's Harwin Gecko footprint has pads 0.275 mm from its own
    non-plated slots: legal with a 0.25 mm edge rule, a DRC error (reported
    here first) with the standard 0.30 mm."""
    harwin = "Connector_Harwin:Harwin_Gecko-G125-MVX0605L1X_2x03_P1.25mm_Vertical"

    def design(rules):
        d = Design("slotpads", RoundedPolygon.rect(0.0, 0.0, 16.0, 10.0), rules=rules)
        d.add(Part("J1", "hdr", harwin, pins={str(i): str(i) for i in range(1, 7)},
                   mpn="x", x=0.0, y=0.0, height_mm=4.0))
        d.no_connect(*["J1.%d" % i for i in range(1, 7)])
        return d

    report = checks.run_checks(design(US_4L_STD), bom=False)
    found = report.find("hole_collision")
    assert len(found) == 4 and all("non-plated hole of J1 (min 0.30" in f.message for f in found)
    assert "0.275 mm" in found[0].message
    relaxed = dataclasses.replace(US_4L_STD, name="EDGE025", copper_to_edge=0.25)
    assert checks.run_checks(design(relaxed), bom=False).find("hole_collision") == []
