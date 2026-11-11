"""Net classes with their own track width and clearance - and proof that KiCad's
DRC judges them exactly as :meth:`gleda.model.Design.clearance` and
:meth:`gleda.model.Design.min_track_width` predict.

The KiCad facts pinned down here (KiCad 7.0.x):

* clearance between two nets = max(class clearance A, class clearance B),
  never below the board minimum;
* a pad's local clearance override replaces the class clearances;
* KiCad itself only checks the BOARD minimum track width - the per-class
  minimum comes from the generated ``.kicad_dru``;
* one 0.09 mm track between two pads at 0.5 mm pitch needs pads <= 0.23 mm.
"""
import json
import os
from dataclasses import replace

import pytest

from gleda import board, checks, drc, geometry
from gleda import footprints as F
from gleda.model import (Design, Outline, Circle, Part, Track, US_4L_STD, US_4L_FINE)

R0402 = "Resistor_SMD:R_0402_1005Metric"


# -- model --------------------------------------------------------------------

def _fine_design(name="nc"):
    d = Design(name, Outline(Circle(0, 0, 17)), rules=US_4L_FINE)
    d.add_netclass("Fine", track_width=0.09, clearance=0.09)
    return d


def test_fine_rule_set_and_default_classes():
    assert (US_4L_FINE.min_track, US_4L_FINE.min_clearance) == (0.09, 0.09)
    assert US_4L_FINE.default_clearance == 0.127 and US_4L_FINE.validate() == []
    d = _fine_design()
    nc = d.netclasses
    assert (nc["Default"].track_width, nc["Default"].clearance) == (0.15, 0.127)
    assert (nc["Power"].track_width, nc["Power"].clearance) == (0.30, 0.127)
    assert (nc["Fine"].track_width, nc["Fine"].clearance) == (0.09, 0.09)
    # a class created without numbers gets the DEFAULT clearance, not the minimum
    assert d.add_netclass("Other").clearance == 0.127
    assert replace(US_4L_STD, default_clearance=0.1).validate() == [
        "default clearance 0.100 < min clearance 0.127"]


def test_clearance_and_width_lookups():
    d = _fine_design()
    for name, cls in (("F1", "Fine"), ("F2", "Fine"), ("D1", "Default"), ("P1", "Power")):
        d.net(name, netclass=cls)
    d.net("W1", width=0.2)                       # wider than its class: class minimum rules
    d.net("N1", netclass="Power", width=0.12)    # explicit narrow override
    assert d.clearance("F1", "F2") == 0.09
    assert d.clearance("F1", "D1") == 0.127      # the larger class clearance wins
    assert d.clearance("D1", "P1") == 0.127
    assert d.clearance("F1", None) == 0.127      # copper without a net is in Default
    assert d.clearance("F1", "unknown") == 0.127
    # pad overrides replace the class values; the board minimum is the floor
    assert d.clearance("D1", "P1", local_a=0.09) == 0.09
    assert d.clearance("D1", "P1", local_a=0.2, local_b=0.1) == 0.2
    assert d.clearance("F1", "F2", local_b=0.05) == 0.09
    assert (d.track_width("F1"), d.min_track_width("F1")) == (0.09, 0.09)
    assert (d.track_width("D1"), d.min_track_width("D1")) == (0.15, 0.15)
    assert (d.track_width("W1"), d.min_track_width("W1")) == (0.2, 0.15)
    assert (d.track_width("N1"), d.min_track_width("N1")) == (0.12, 0.12)
    assert d.via_size("F1") == (0.5, 0.25)
    d.add_netclass("Neck", track_width=0.3, min_track_width=0.15)
    d.net("K1", netclass="Neck")
    assert (d.track_width("K1"), d.min_track_width("K1")) == (0.3, 0.15)


def test_board_minimums_for_the_fab_readme():
    d = _fine_design()
    d.net("F1", netclass="Fine")
    d.net("D1")
    m = d.board_minimums()
    assert (m["rule_set"], m["min_track"], m["min_clearance"]) == ("US_4L_FINE", 0.09, 0.09)
    assert (m["smallest_track_in_use"], m["smallest_clearance_in_use"]) == (0.09, 0.09)
    assert m["net_classes"]["Fine"]["nets"] == ["F1"]
    assert (m["via_diameter"], m["via_drill"], m["min_annular"]) == (0.5, 0.25, 0.125)
    assert m["via_tenting"] == "both" and m["blind_buried_vias"] is False
    # without a fine class in use the smallest features are the Default ones
    std = Design("std", Circle(0, 0, 5))
    std.net("A")
    m = std.board_minimums()
    assert (m["min_track"], m["smallest_track_in_use"], m["smallest_clearance_in_use"]) == \
        (0.127, 0.15, 0.127)
    assert m["smallest_pad_clearance_override"] is None
    json.dumps(d.to_dict())                      # the whole dump stays JSON-able


def test_checks_reject_a_fine_class_on_the_standard_rule_set():
    d = Design("bad", Circle(0, 0, 8))           # US_4L_STD: minimums 0.127 / 0.127
    d.add_netclass("Fine", track_width=0.09, clearance=0.09)
    r = checks.run_checks(d, footprints=False)
    msgs = [f.message for f in r.find("rule_violation")]
    assert any("net class Fine track 0.090 < min track 0.127" in m for m in msgs)
    assert any("net class Fine clearance 0.090 < min clearance 0.127" in m for m in msgs)
    ok = _fine_design()
    assert not checks.run_checks(ok, footprints=False).has("rule_violation")
    ok.add_netclass("Neck", track_width=0.3, min_track_width=0.05)
    ok.add_netclass("Odd", track_width=0.2, min_track_width=0.25)
    ok.add_netclass("It's", track_width=0.2)
    ok.net("a*b")
    msgs = " | ".join(f.message for f in checks.run_checks(ok, footprints=False).find(
        "rule_violation"))
    assert "Neck min_track_width 0.050 < min track 0.090" in msgs
    assert "Odd min_track_width 0.250 > its track width 0.200" in msgs
    assert "net class name \"It's\"" in msgs and "net name 'a*b'" in msgs


# -- project + rules files ------------------------------------------------------

def _two_resistor_nets(d, names_classes, x0=-11.0, x1=11.0):
    """Give every net two pads far apart so that floating test tracks keep
    their nets (KiCad merges the nets of touching pad-less copper)."""
    for i, (name, cls) in enumerate(names_classes):
        y = 9.0 - 2.0 * i
        a, b = "R%d" % (2 * i + 1), "R%d" % (2 * i + 2)
        d.add(Part(a, "1k", R0402, mpn="X", x=x0, y=y, rotation=90),
              Part(b, "1k", R0402, mpn="X", x=x1, y=y, rotation=90))
        d.net(name, "%s.1" % a, "%s.1" % b, netclass=cls)
        d.net(name + "_RET", "%s.2" % a, "%s.2" % b)


NETS = [("DA", "Default"), ("DB", "Default"), ("FA", "Fine"), ("FB", "Fine"),
        ("PA", "Power"), ("DN", "Default")]


@pytest.fixture(scope="module")
def class_board(tmp_path_factory):
    d = _fine_design("classes")
    _two_resistor_nets(d, NETS)
    d.net("DN", width=0.1)                       # per-net override below the class width
    files = board.build_board(d, str(tmp_path_factory.mktemp("classes")))
    return d, files


def test_classes_are_written_and_read_back_by_kicad(class_board):
    d, files = class_board
    pro = json.load(open(files.pro))
    classes = {c["name"]: c for c in pro["net_settings"]["classes"]}
    assert (classes["Fine"]["track_width"], classes["Fine"]["clearance"]) == (0.09, 0.09)
    assert (classes["Default"]["track_width"], classes["Default"]["clearance"]) == (0.15, 0.127)
    assert (classes["Power"]["track_width"], classes["Power"]["clearance"]) == (0.3, 0.127)
    rules = pro["board"]["design_settings"]["rules"]
    assert (rules["min_track_width"], rules["min_clearance"]) == (0.09, 0.09)
    assert 0.09 in pro["board"]["design_settings"]["track_widths"]
    s = board.board_summary(files.pcb)
    assert s["netclass_values"]["Fine"] == {"track_width": 0.09, "clearance": 0.09,
                                            "via_diameter": 0.5, "via_drill": 0.25}
    assert s["netclass_values"]["Default"]["clearance"] == 0.127
    assert s["netclasses"]["FA"] == "Fine" and s["netclasses"]["PA"] == "Power"
    assert s["netclasses"]["DA"] == "Default" and s["netclasses"]["FA_RET"] == "Default"
    assert (s["rules"]["min_track"], s["rules"]["min_clearance"]) == (0.09, 0.09)


def test_custom_rules_file(class_board):
    d, files = class_board
    assert files.dru == os.path.splitext(files.pcb)[0] + ".kicad_dru"
    assert board.custom_rules(d) == [
        ("gleda min track width of net class Default", "A.NetClass == 'Default'", 0.15),
        ("gleda min track width of net class Fine", "A.NetClass == 'Fine'", 0.09),
        ("gleda min track width of net class Power", "A.NetClass == 'Power'", 0.3),
        ("gleda min track width of net DN", "A.NetName == 'DN'", 0.1),
    ]
    text = open(files.dru).read()
    assert text.startswith("(version 1)\n")
    assert '(constraint track_width (min 0.3mm))' in text
    assert drc.custom_rule_names(files.pcb) == [r[0] for r in board.custom_rules(d)]


def _pair(net_a, wa, net_b, wb, y, gap, x0=-6.0, x1=6.0):
    """Two parallel floating tracks whose copper edges are ``gap`` apart."""
    ya, yb = y + gap / 2 + wa / 2, y - gap / 2 - wb / 2
    return [Track(net_a, "F.Cu", x0, ya, x1, ya, wa), Track(net_b, "F.Cu", x0, yb, x1, yb, wb)]


def _errors(result, kind):
    return [v for v in result.violations if v.type == kind and v.severity == "error"]


def test_kicad_checks_clearance_per_class_pair(class_board, tmp_path):
    d, files = class_board
    cases = [  # (net a, width, net b, width, gap, violation expected)
        ("DA", 0.15, "DB", 0.15, 0.100, True),      # Default / Default needs 0.127
        ("DA", 0.15, "DB", 0.15, 0.127, False),
        ("FA", 0.09, "FB", 0.09, 0.100, False),     # Fine / Fine needs 0.09
        ("FA", 0.09, "FB", 0.09, 0.085, True),
        ("FA", 0.09, "DA", 0.15, 0.100, True),      # mixed: the larger clearance applies
        ("FA", 0.09, "DA", 0.15, 0.127, False),
        ("FA", 0.09, "PA", 0.30, 0.110, True),
    ]
    tracks, expect = [], {}
    for i, (na, wa, nb, wb, gap, bad) in enumerate(cases):
        y = 7.0 - 2.0 * i
        tracks += _pair(na, wa, nb, wb, y, gap)
        expect[round(y, 3)] = bad
        # the model predicts exactly what KiCad will decide
        assert (gap < d.clearance(na, nb) - 1e-9) == bad
    res = board.apply_routing(files.pcb, tracks, [])
    assert res.renetted == []
    r = drc.run_drc(files.pcb, report_path=str(tmp_path / "drc.rpt"))
    flagged = {round(round(v.items[0].y), 3) for v in _errors(r, "clearance")}
    assert flagged == {y for y, bad in expect.items() if bad}, r.summary()
    assert not _errors(r, "track_width") and not _errors(r, "copper_edge_clearance")
    descr = " ".join(v.description for v in _errors(r, "clearance"))
    assert "netclass 'Default' clearance 0.1270 mm" in descr
    assert "netclass 'Fine' clearance 0.0900 mm" in descr


def test_kicad_checks_track_width_per_class_and_net(class_board, tmp_path):
    d, files = class_board
    cases = [  # (net, width, violation expected)
        ("FA", 0.09, False), ("FB", 0.08, True),          # board minimum 0.09
        ("DA", 0.15, False), ("DB", 0.09, True),          # Default needs 0.15
        ("PA", 0.30, False), ("PA", 0.15, True),          # Power needs 0.30
        ("DN", 0.10, False), ("DN", 0.095, True),         # net override 0.10
    ]
    tracks, expect = [], {}
    for i, (net, width, bad) in enumerate(cases):
        y = 7.0 - 1.5 * i
        tracks.append(Track(net, "B.Cu", -6.0, y, 6.0, y, width))
        expect[round(y, 3)] = bad
        assert (width < d.min_track_width(net) - 1e-9) == bad
    board.apply_routing(files.pcb, tracks, [])
    r = drc.run_drc(files.pcb, report_path=str(tmp_path / "drc.rpt"))
    flagged = {round(v.items[0].y, 3) for v in _errors(r, "track_width")}
    assert flagged == {y for y, bad in expect.items() if bad}, r.summary()
    assert not _errors(r, "clearance")
    assert r.custom_rules and "custom_rules" in r.to_dict()
    with pytest.raises(drc.DrcError, match="track_width"):
        drc.assert_clean(r, allow_unconnected=True)


def test_without_enforcement_kicad_only_checks_the_board_minimum(tmp_path):
    d = _fine_design("loose")
    _two_resistor_nets(d, NETS[:2])
    d.enforce_track_widths = False
    out = str(tmp_path)
    open(os.path.join(out, "loose.kicad_dru"), "w").write("(version 1)\n")     # stale file
    files = board.build_board(d, out)
    assert files.dru is None and not os.path.exists(os.path.join(out, "loose.kicad_dru"))
    board.apply_routing(files.pcb, [Track("DA", "F.Cu", -6, 0, 6, 0, 0.09),
                                    Track("DB", "F.Cu", -6, 1, 6, 1, 0.08)], [])
    r = drc.run_drc(files.pcb)
    assert len(_errors(r, "track_width")) == 1 and r.custom_rules == []


def test_rule_names_are_validated(tmp_path):
    d = _fine_design("names")
    _two_resistor_nets(d, [("it's", "Default")])
    with pytest.raises(board.BoardBuildError, match="cannot be used in a KiCad DRC rule"):
        d.net("it's", width=0.1)
        board.build_board(d, str(tmp_path))
    d2 = _fine_design("names2")
    _two_resistor_nets(d2, [("A", "Nope")])
    with pytest.raises(board.BoardBuildError, match="undefined net class 'Nope'"):
        board.build_board(d2, str(tmp_path / "b"))


# -- BGA escape -------------------------------------------------------------------

def _bga_board(tmp_path, tag, pad_d, pad_clearance, outer_cls, inner_cls):
    """5 x 5, 0.5 mm pitch BGA; ball B2 (inner) escapes to the left between
    the outer balls B1 and C1 with a 0.09 mm track."""
    d = _fine_design("bga_" + tag)
    spec = F.bga("BGA25_" + tag, 5, 5, pitch=0.5, pad_d=pad_d, body=(3.47, 2.95),
                 pad_clearance=pad_clearance)
    balls = spec.pad_numbers()
    d.add(Part("U1", "CAM", spec, pins={b: (b, "bidir") for b in balls}, mpn="X", x=0, y=0))
    d.add(Part("R1", "1k", R0402, mpn="X", x=-6, y=3), Part("R2", "1k", R0402, mpn="X", x=-6, y=0),
          Part("R3", "1k", R0402, mpn="X", x=-6, y=-3))
    d.net("OUT_A", "U1.B1", "R1.1", netclass=outer_cls)
    d.net("OUT_B", "U1.C1", "R3.1", netclass=outer_cls)
    d.net("INNER", "U1.B2", "R2.1", netclass=inner_cls)
    d.net("X", "R1.2", "R2.2", "R3.2")
    files = board.build_board(d, str(tmp_path / tag))
    b2 = geometry.pad_position(d, "U1", "B2")
    assert b2 == pytest.approx((-0.5, 0.5))
    end = geometry.pad_position(d, "R2", "1")
    w = d.track_width("INNER")
    tracks = [Track("INNER", "F.Cu", b2[0], b2[1], -0.75, 0.25, w),      # 45 degrees out
              Track("INNER", "F.Cu", -0.75, 0.25, -3.0, 0.25, w),        # between B1 and C1
              Track("INNER", "F.Cu", -3.0, 0.25, -3.0, 1.5, w),
              Track("INNER", "F.Cu", -3.0, 1.5, end[0], 1.5, w),
              Track("INNER", "F.Cu", end[0], 1.5, end[0], end[1], w)]
    board.apply_routing(files.pcb, tracks, [])
    result = drc.run_drc(files.pcb)
    pads = {p.number: p for p in geometry.part_pads(d, d.part("U1"))}
    predicted = geometry.pad_clearance(d, pads["B1"], "INNER")
    return d, result, predicted


def test_bga_escape_fails_with_0v25_pads(tmp_path):
    """0.5 - 0.25 = 0.25 mm between the pads: a 0.09 mm track leaves 0.08 mm."""
    d, r, predicted = _bga_board(tmp_path, "d25", 0.25, None, "Fine", "Fine")
    errs = _errors(r, "clearance")
    assert len(errs) == 2 and predicted == 0.09
    assert all("clearance 0.0900 mm; actual 0.0800 mm" in v.description for v in errs)


def test_bga_escape_passes_with_0v23_pads_when_every_ball_net_is_fine(tmp_path):
    d, r, predicted = _bga_board(tmp_path, "d23", 0.23, None, "Fine", "Fine")
    assert r.error_count == 0, r.summary()
    assert predicted == 0.09


def test_bga_escape_between_default_class_balls_needs_the_pad_override(tmp_path):
    # outer balls on Default nets: KiCad wants max(0.09, 0.127) = 0.127 ...
    d, r, predicted = _bga_board(tmp_path, "mixed", 0.23, None, "Default", "Fine")
    errs = _errors(r, "clearance")
    assert len(errs) == 2 and predicted == 0.127
    assert all("netclass 'Default' clearance 0.1270 mm; actual 0.0900 mm" in v.description
               for v in errs)
    # ... unless the BGA pads carry a 0.09 mm clearance override
    d, r, predicted = _bga_board(tmp_path, "override", 0.23, 0.09, "Default", "Fine")
    assert r.error_count == 0, r.summary()
    assert predicted == 0.09
    assert d.board_minimums()["smallest_pad_clearance_override"] == 0.09
    # the override cannot undercut the board minimum
    d, r, predicted = _bga_board(tmp_path, "floor", 0.25, 0.05, "Fine", "Fine")
    errs = _errors(r, "clearance")
    assert len(errs) == 2 and predicted == 0.09
    assert all("board minimum clearance 0.0900 mm; actual 0.0800 mm" in v.description
               for v in errs)
    assert checks.run_checks(d).has("pad_clearance_override")


def test_broken_rules_file_fails_loudly(tmp_path):
    """A custom rules file KiCad cannot parse must never look like a pass."""
    d = _fine_design("broken")
    _two_resistor_nets(d, NETS[:1])
    files = board.build_board(d, str(tmp_path))
    with open(files.dru, "a") as fh:
        fh.write('(rule "oops" (condition "A.NetClass ==") (constraint nonsense))\n')
    with pytest.raises(drc.DrcError):
        drc.run_drc(files.pcb)


def test_project_merge_keeps_foreign_text_variables(tmp_path):
    d = _fine_design("merge")
    d.via_tenting = "bottom"
    path = str(tmp_path / "merge.kicad_pro")
    with open(path, "w") as fh:
        json.dump({"text_variables": {"REV": "A", board.TENTING_VARIABLE: "none"},
                   "schematic": {"x": 1}}, fh)
    board.write_project(d, path)
    pro = json.load(open(path))
    assert pro["text_variables"] == {"REV": "A", board.TENTING_VARIABLE: "bottom"}
    assert pro["schematic"] == {"x": 1}
    assert board.project_via_tenting(str(tmp_path / "merge.kicad_pcb")) == "bottom"
    assert board.project_via_tenting(str(tmp_path / "nope.kicad_pcb")) == "both"
