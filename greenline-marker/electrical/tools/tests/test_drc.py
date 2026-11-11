"""DRC runner: report parser, zone fill, real KiCad DRC on good and bad boards."""
import json
import os
import subprocess
import sys

import pytest

from gleda import board, drc, geometry
from gleda.model import Design, Circle, Part, Track, Via, BOTTOM

R0402 = "Resistor_SMD:R_0402_1005Metric"

REPORT = """** Drc report for /some/where/demo.kicad_pcb **
** Created on 2026-01-01 00:00:00 **

** Found 4 DRC violations **
[clearance]: Clearance violation (netclass 'Default' clearance 0.1270 mm; actual 0.1000 mm)
    Rule: netclass 'Default'; Severity: error
    @(100.9900 mm, 106.5000 mm): Track [LED1] on F.Cu, length 2.0000 mm
    @(99.9900 mm, 108.0000 mm): Track [LED2] on F.Cu, length 1.2500 mm
[copper_edge_clearance]: Board edge clearance violation (board setup constraints edge clearance 0.3000 mm; actual 0.1984 mm)
    Rule: board setup constraints edge; Severity: error
    @(100.0000 mm, 100.0000 mm): Arc on Edge.Cuts
    @(100.0000 mm, 85.2000 mm): Track [SCK] on B.Cu, length 3.0150 mm
[track_dangling]: Track has unconnected end
    Local override; Severity: warning
    @(95.0000 mm, 90.5000 mm): Track [MOSI] on F.Cu, length 3.0000 mm
[silk_overlap]: Silkscreen overlap
    Local override; Severity: error
    @(101.0000 mm, 99.0000 mm): Text 'R1' of R1 on F.Silkscreen

** Found 1 unconnected pads **
[unconnected_items]: Missing connection between items
    Local override; Severity: error
    @(102.9875 mm, 91.5000 mm): Pad 6 [GND] of U2 on B.Cu
    @(102.9875 mm, 91.0000 mm): Pad 7 [GND] of U2 on B.Cu

** Found 0 Footprint errors **

** End of Report **
"""


def test_parse_report_structure():
    r = drc.parse_report(REPORT)
    assert r.board == "/some/where/demo.kicad_pcb"
    assert r.errors_by_type == {"clearance": 1, "copper_edge_clearance": 1, "silk_overlap": 1}
    assert r.warnings_by_type == {"track_dangling": 1}
    assert (r.error_count, r.warning_count, r.unconnected_count) == (3, 1, 1)
    v = r.violations[0]
    assert v.type == "clearance" and v.severity == "error"
    assert v.rule == "netclass 'Default'"
    assert "actual 0.1000 mm" in v.description
    assert len(v.items) == 2
    # KiCad page coordinates and design coordinates (+y up, board centre origin)
    assert (v.items[0].kicad_x, v.items[0].kicad_y) == (100.99, 106.5)
    assert (v.items[0].x, v.items[0].y) == (0.99, -6.5)
    assert v.items[0].description == "Track [LED1] on F.Cu, length 2.0000 mm"
    u = r.unconnected[0]
    assert u.type == "unconnected_items" and u.section == "unconnected"
    assert (u.items[0].x, u.items[0].y) == pytest.approx((2.9875, 8.5))


def test_parse_report_json_shape():
    d = drc.parse_report(REPORT).to_dict()
    assert d["errors"] == {"clearance": 1, "copper_edge_clearance": 1, "silk_overlap": 1}
    assert d["warnings"] == {"track_dangling": 1}
    assert d["unconnected"] == 1
    assert len(d["items"]) == 5
    assert d["items"][0]["items"][0] == {
        "x": 0.99, "y": -6.5, "kicad_x": 100.99, "kicad_y": 106.5,
        "description": "Track [LED1] on F.Cu, length 2.0000 mm"}
    assert "silk_overlap" in d["cosmetic_allow_list"]
    json.dumps(d)


def test_parse_report_rejects_garbage_and_truncation():
    with pytest.raises(ValueError):
        drc.parse_report("hello")
    with pytest.raises(ValueError):
        drc.parse_report(REPORT.replace("** End of Report **", ""))
    with pytest.raises(ValueError):                       # declared count != parsed count
        drc.parse_report(REPORT.replace("Found 4 DRC violations", "Found 5 DRC violations"))


def test_assert_clean_policy():
    r = drc.parse_report(REPORT)
    with pytest.raises(drc.DrcError) as exc:
        drc.assert_clean(r)
    msg = str(exc.value)
    assert "2 DRC error(s)" in msg and "clearance" in msg and "1 unconnected" in msg
    assert "silk_overlap" not in msg.split("DRC error(s)")[1].split("\n")[0]
    # cosmetic allow-list: only silk_overlap is ignored, nothing else
    assert [v.type for v in r.errors()] == ["clearance", "copper_edge_clearance"]
    assert len(r.errors(allow=())) == 3
    assert not r.is_clean() and not r.is_clean(allow_unconnected=True)
    clean = drc.parse_report(
        "** Drc report for x **\n\n** Found 1 DRC violations **\n"
        "[silk_overlap]: Silkscreen overlap\n    Local override; Severity: warning\n"
        "    @(1.0 mm, 1.0 mm): Text\n\n** Found 0 unconnected pads **\n\n"
        "** Found 0 Footprint errors **\n\n** End of Report **\n")
    assert drc.assert_clean(clean) is clean
    clean.tampered = ["clearance"]
    with pytest.raises(drc.DrcError, match="severity"):
        drc.assert_clean(clean)


def test_core_checks_are_never_in_the_cosmetic_allow_list():
    assert not set(drc.COSMETIC_CHECKS) & set(board.CORE_ERROR_CHECKS)
    for must in ("clearance", "track_width", "annular_width", "drill_out_of_range",
                 "hole_near_hole", "copper_edge_clearance", "shorting_items",
                 "unconnected_items"):
        assert must in board.CORE_ERROR_CHECKS


# -- real KiCad runs ----------------------------------------------------------

def test_unrouted_board_has_only_unconnected_items(built_mini, mini_drc):
    """The proof for the core: a board with library + custom footprints on
    both sides, a cutout, notch, slot, holes, planes and keep-outs loads back
    into pcbnew and KiCad's DRC finds NO geometry errors - only the expected
    unconnected items of an unrouted board."""
    design, files = built_mini
    r = mini_drc
    assert r.errors_by_type == {}, r.summary()
    assert r.error_count == 0
    assert r.footprint_errors == []
    assert r.tampered == []
    # warnings: only the planes that nothing connects to yet
    assert set(r.warnings_by_type) <= {"isolated_copper"}
    # ratsnest: every net needs (number of physical pads - 1) links
    per_net = {}
    for pad in geometry.placed_pads(design):
        if pad.net:
            per_net[pad.net] = per_net.get(pad.net, 0) + 1
    expected = sum(n - 1 for n in per_net.values())
    assert r.unconnected_count == expected == 52
    assert r.zones_filled == 2
    with pytest.raises(drc.DrcError, match="52 unconnected"):
        drc.assert_clean(r)
    assert drc.assert_clean(r, allow_unconnected=True) is r


def test_drc_outputs_are_written_and_reproducible(built_mini, mini_drc):
    design, files = built_mini
    assert os.path.exists(mini_drc.report_path)
    text = open(mini_drc.report_path).read()
    assert "Created on" not in text                    # timestamp stripped
    assert text.startswith("** Drc report for mini.kicad_pcb **")
    data = json.load(open(os.path.join(files.directory, "drc.json")))
    assert data["unconnected"] == 52 and data["error_count"] == 0
    assert data["zones_filled"] == 2
    assert data["severity_overrides"]["lib_footprint_issues"]["severity"] == "ignore"
    first = data["items"][-1]["items"][0]
    assert {"x", "y", "kicad_x", "kicad_y", "description"} <= set(first)
    # unconnected marker coordinates are design coordinates of real pads
    pads = {(round(p.x, 4), round(p.y, 4)) for p in geometry.placed_pads(design)}
    for v in mini_drc.unconnected:
        for item in v.items:
            assert (item.x, item.y) in pads, item


def test_zones_are_filled_and_saved(built_mini, mini_drc):
    design, files = built_mini
    zones = {z["name"]: z for z in board.board_summary(files.pcb)["zones"]}
    assert zones["GND_In1.Cu"]["filled"] and zones["+3V0_In2.Cu"]["filled"]


def test_fill_zones_function(tmp_path, mini):
    files = board.build_board(mini, str(tmp_path))
    assert drc.fill_zones(files.pcb) == 2
    assert "filled_polygon" in open(files.pcb).read()


def test_bad_geometry_is_reported_by_type(tmp_path, mini):
    """KiCad must flag every deliberately broken rule - this proves the judge
    is armed with the design's rule set (loaded from the generated project)."""
    files = board.build_board(mini, str(tmp_path))
    p = lambda ref, pad: geometry.pad_position(mini, ref, pad)
    r11, r21 = p("R1", "1"), p("R2", "1")
    tracks = [
        Track("SCK", "F.Cu", 0.0, 12.5, 3.0, 12.5, 0.10),                # thinner than min track
        Track("SCK", "B.Cu", 0.0, 14.8, 3.0, 14.5, 0.15),                # too close to the edge
        Track("MOSI", "F.Cu", -5.0, 9.5, -2.0, 9.5, 0.15),               # inside the antenna keep-out
        # two different nets 0.1 mm apart (both hang on their pads)
        Track("LED1", "F.Cu", r11[0], r11[1], r11[0] - 2.0, r11[1], 0.15),
        Track("LED2", "F.Cu", r21[0], r21[1], r21[0] - 1.0, r21[1], 0.15),
        Track("LED2", "F.Cu", r21[0] - 1.0, r21[1], r21[0] - 1.0, r11[1] - 0.25, 0.15),
        # dead short: R1.2 (LED1_A) straight into R2.1 (LED2)
        Track("LED1_A", "F.Cu", *p("R1", "2"), *r21, 0.15),
    ]
    vias = [
        Via("GND", -7.0, -11.5, 0.45, 0.25),      # annular ring 0.1 < 0.125, pad < min
        Via("GND", 0.0, -11.0, 0.5, 0.2),         # drill below minimum
        Via("+3V0", 10.0, -8.0, 0.5, 0.25),
        Via("GND", 10.4, -8.0, 0.5, 0.25),        # holes 0.15 mm apart, pads overlap
    ]
    board.apply_routing(files.pcb, tracks, vias, strict=False)
    r = drc.run_drc(files.pcb)
    errs = r.errors_by_type
    for expected in ("track_width", "copper_edge_clearance", "items_not_allowed", "clearance",
                     "annular_width", "drill_out_of_range", "hole_near_hole"):
        assert errs.get(expected, 0) >= 1, (expected, r.summary())
    # the dead short is reported as a zero clearance between different nets
    shorts = [v for v in r.violations if v.type == "clearance" and "actual 0.0000 mm" in v.description]
    assert shorts, r.summary()
    with pytest.raises(drc.DrcError) as exc:
        drc.assert_clean(r, allow_unconnected=True)
    assert "track_width" in str(exc.value) and exc.value.result is r


def test_downgraded_severity_is_detected(tmp_path, mini):
    files = board.build_board(mini, str(tmp_path))
    pro = json.load(open(files.pro))
    pro["board"]["design_settings"]["rule_severities"]["clearance"] = "warning"
    pro["board"]["design_settings"]["rule_severities"]["unconnected_items"] = "ignore"
    json.dump(pro, open(files.pro, "w"))
    assert drc.check_project_severities(files.pcb) == ["clearance", "unconnected_items"]
    r = drc.run_drc(files.pcb)
    assert r.tampered == ["clearance", "unconnected_items"]
    assert not r.is_clean(allow_unconnected=True)
    with pytest.raises(drc.DrcError, match="not at severity 'error'"):
        drc.assert_clean(r, allow_unconnected=True)
    os.remove(files.pro)
    assert "no project file" in drc.check_project_severities(files.pcb)[0]


def test_routing_reduces_unconnected_and_vias_reach_planes(tmp_path, mini):
    files = board.build_board(mini, str(tmp_path))
    base = drc.run_drc(files.pcb)
    a = geometry.pad_position(mini, "R1", "2")
    b = geometry.pad_position(mini, "D1", "2")          # anode; cathode pad lies in between
    # through the channel between the D1 and D2 pad rows
    tracks = [Track("LED1_A", "F.Cu", a[0], a[1], a[0], -7.25, 0.15),
              Track("LED1_A", "F.Cu", a[0], -7.25, b[0], -7.25, 0.15),
              Track("LED1_A", "F.Cu", b[0], -7.25, b[0], b[1], 0.15)]
    board.apply_routing(files.pcb, tracks, [])
    r1 = drc.run_drc(files.pcb)
    assert r1.error_count == 0, r1.summary()
    assert r1.unconnected_count == base.unconnected_count - 1
    # two GND pads dropped onto the In1 GND plane with a stub + via each
    c12 = geometry.pad_position(mini, "C1", "2")
    d1k = geometry.pad_position(mini, "D1", "1")
    tracks += [Track("GND", "F.Cu", c12[0], c12[1], c12[0] - 1.0, c12[1], 0.3),
               Track("GND", "F.Cu", d1k[0], d1k[1], d1k[0], d1k[1] + 1.1, 0.3)]
    vias = [Via("GND", c12[0] - 1.0, c12[1], 0.5, 0.25),
            Via("GND", d1k[0], d1k[1] + 1.1, 0.5, 0.25)]
    board.apply_routing(files.pcb, tracks, vias)
    r2 = drc.run_drc(files.pcb)
    assert r2.error_count == 0, r2.summary()
    assert r2.unconnected_count == base.unconnected_count - 2     # joined through the plane
    iso = [v for v in r2.violations if v.type == "isolated_copper"]
    assert all("GND" not in i.description for v in iso for i in v.items)


@pytest.fixture(scope="module")
def clean_board(tmp_path_factory):
    """A tiny, completely hand-routed 2-layer-used board that must pass."""
    d = Design("clean", Circle(0, 0, 6))
    d.add(Part("R1", "1k", R0402, mpn="X", x=-2.0, y=1.0),
          Part("R2", "1k", R0402, mpn="X", x=2.0, y=1.0),
          Part("R3", "1k", R0402, mpn="X", x=0.0, y=-2.0, side=BOTTOM))
    d.net("A", "R1.2", "R2.1")
    d.net("B", "R1.1", "R3.1", "R2.2", netclass="Power")
    out = tmp_path_factory.mktemp("clean")
    files = board.build_board(d, str(out))
    p = lambda ref, pad: geometry.pad_position(d, ref, pad)
    r11, r12, r21, r22, r31 = p("R1", "1"), p("R1", "2"), p("R2", "1"), p("R2", "2"), p("R3", "1")
    tracks = [
        Track("A", "F.Cu", r12[0], r12[1], r21[0], r21[1], 0.15),
        # B: R1.1 up and over to R2.2 on the top side, then a via down to R3.1
        Track("B", "F.Cu", r11[0], r11[1], r11[0], 2.5, 0.3),
        Track("B", "F.Cu", r11[0], 2.5, r22[0], 2.5, 0.3),
        Track("B", "F.Cu", r22[0], 2.5, r22[0], r22[1], 0.3),
        Track("B", "F.Cu", r11[0], r11[1], r11[0], -2.0, 0.3),
        Track("B", "B.Cu", r11[0], -2.0, r31[0], r31[1], 0.3),
    ]
    vias = [Via("B", r11[0], -2.0, 0.5, 0.25)]
    board.apply_routing(files.pcb, tracks, vias)
    return d, files


def test_fully_routed_board_passes(clean_board):
    d, files = clean_board
    r = drc.run_drc(files.pcb)
    assert r.error_count == 0 and r.unconnected_count == 0, r.summary()
    assert r.is_clean()
    assert drc.assert_clean(r) is r


def test_in_process_run_matches_isolated(clean_board):
    d, files = clean_board
    r = drc.run_drc(files.pcb, isolate=False, save=False)
    assert r.is_clean() and r.zones_filled == 0


def test_cli_exit_codes(clean_board, built_mini, mini_drc):
    tools = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, PYTHONPATH=tools)
    run = lambda *a: subprocess.run([sys.executable, "-m", "gleda.drc", *a], env=env,
                                    capture_output=True, text=True, cwd=tools)
    ok = run(clean_board[1].pcb)
    assert ok.returncode == 0, ok.stderr
    assert "0 error(s)" in ok.stdout and "0 unconnected" in ok.stdout
    bad = run(built_mini[1].pcb)
    assert bad.returncode == 1 and "unconnected" in bad.stderr
    tolerated = run(built_mini[1].pcb, "--allow-unconnected")
    assert tolerated.returncode == 0


def test_run_drc_errors_are_loud(tmp_path):
    with pytest.raises(drc.DrcError, match="not found"):
        drc.run_drc(str(tmp_path / "missing.kicad_pcb"))
    broken = tmp_path / "broken.kicad_pcb"
    broken.write_text("(kicad_pcb (version 20221018) (generator nobody)")
    with pytest.raises(drc.DrcError):
        drc.run_drc(str(broken))
