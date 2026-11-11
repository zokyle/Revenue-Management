"""The GreenLine DEMO board: design checks, the stored routing judged afresh
by KiCad's DRC, the whole flow of ``demo/build_demo.py`` with the stored
routing, and (slow) the whole demo build from nothing.

``demo/demo_out/routing.json`` is the routing the last demo build produced.
The quick tests prove that it still belongs to the current design (same
fingerprint), re-audit it, take it through a freshly built board and KiCad's
DRC, and run every later stage (outputs, schematic, netlist round trip).  The
slow test runs ``demo/build_demo.py`` from nothing, the router included.
"""
import json
import os
import subprocess
import sys

import pytest

from gleda import board, checks, drc, router

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO = os.path.join(TOOLS, "demo")
if DEMO not in sys.path:
    sys.path.insert(0, DEMO)

ROUTING = os.path.join(DEMO, "demo_out", "routing.json")


@pytest.fixture(scope="module")
def demo():
    from demo_design import demo_design
    return demo_design()


def test_demo_checks_have_no_errors(demo):
    report = checks.run_checks(demo)
    assert report.ok, report.text()
    assert len(demo.parts) >= 90 and len(demo.nets) >= 70


def test_demo_net_classes_and_planes(demo):
    nc = demo.netclasses
    assert (nc["Default"].track_width, nc["Default"].clearance) == (0.15, 0.127)
    assert (nc["Power"].track_width, nc["Power"].clearance) == (0.30, 0.127)
    assert (nc["Fine"].track_width, nc["Fine"].clearance) == (0.09, 0.09)
    minimums = demo.board_minimums()
    assert (minimums["min_track"], minimums["min_clearance"]) == (0.09, 0.09)
    fine = {name for name, net in demo.nets.items() if net.netclass == "Fine"}
    # the fine class is only for nets on the 0.5 mm-pitch camera BGAs
    for name in fine:
        refs = {pad.split(".")[0] for pad in ("%s.%s" % rp for rp in demo.net_pads(name))}
        assert refs & {"U2", "U3"}, name
    assert demo.full_plane_layers() == {"In1.Cu": "GND", "In2.Cu": "V2V8"}
    assert demo.signal_layers() == ("F.Cu", "In2.Cu", "B.Cu")


def test_demo_exercises_the_rev_c_mechanics():
    """Locating hole and slot, post-foot keep-outs and camera-hood height
    limits are in the demo and the checks on them are live."""
    from demo_design import demo_design, POST_FEET, HOOD_MAX_HEIGHT
    d = demo_design()
    assert [(h.x, h.y, h.drill) for h in d.outline.holes] == [(-4.2, 14.55, 1.15)]
    slot = d.outline.cutouts[0]
    assert (slot.width, slot.x2 - slot.x1 + slot.width) == pytest.approx((1.15, 1.65))
    assert ((slot.x1 + slot.x2) / 2, slot.y1) == pytest.approx((4.2, 14.55))
    feet = [k for k in d.keepouts if k.name.startswith("post_foot")]
    assert len(feet) == len(POST_FEET) == 8
    assert all(k.footprints and not k.tracks and k.layers == ("F.Cu",) for k in feet)
    assert [(h.side, h.max_height, h.exempt) for h in d.height_limits] == [
        ("top", HOOD_MAX_HEIGHT, ("U2",)), ("top", HOOD_MAX_HEIGHT, ("U3",))]
    # a 0402 on a post foot: placement keep-out
    bad = demo_design()
    bad.part("R24").place(POST_FEET[0][0], POST_FEET[0][1])
    report = checks.run_checks(bad)
    assert any("R24" in f.refs for f in report.find("in_keepout")), report.text()
    # a 1.2 mm tall regulator under the left camera hood: height limit
    bad = demo_design()
    bad.part("U7").place(-8.0, 14.6)
    report = checks.run_checks(bad)
    assert any("U7" in f.refs for f in report.find("height_limit")), report.text()
    # the camera itself is exempt, and the unmodified demo is clean
    assert not checks.run_checks(demo_design()).find("height_limit")


def test_stored_demo_routing_passes_kicad_drc(demo, tmp_path):
    if not os.path.exists(ROUTING):
        pytest.skip("no demo/demo_out/routing.json yet: run demo/build_demo.py")
    result = router.load_routing(ROUTING, demo)       # fingerprint must match the design
    assert result.complete, result.summary()
    assert result.routed_fraction == 1.0 and result.audit.violations == []
    files = board.build_board(demo, str(tmp_path))
    board.apply_routing(files.pcb, result.tracks, result.vias, via_tenting=demo.via_tenting)
    res = drc.run_drc(files.pcb)
    drc.assert_clean(res)
    assert res.error_count == 0 and res.unconnected_count == 0
    assert res.tampered == []
    assert "via_dangling" not in res.warnings_by_type       # no via that joins nothing


def _check_complete_build(out, summary):
    """What a passed, complete demo build must have left behind."""
    assert summary["passed"] is True and summary["complete_run"] is True
    assert summary["criteria"] == {"checks_0_errors": True, "routed_100_percent": True,
                                   "kicad_drc_0_errors_0_unconnected": True,
                                   "schematic_round_trip_matches": True}
    stages = summary["stages"]
    assert sorted(stages) == sorted(["checks", "board", "route", "drc", "outputs",
                                     "schematic"])
    assert all(info["passed"] for info in stages.values())
    assert stages["checks"]["errors"] == 0
    assert stages["route"]["routed_percent"] == 100.0
    assert stages["route"]["audit_violations"] == 0 and stages["route"]["unrouted"] == []
    assert stages["drc"]["errors"] == 0 and stages["drc"]["unconnected"] == 0
    assert stages["outputs"]["problems"] == [] and stages["outputs"]["drc_clean"] is True
    assert stages["outputs"]["position_rows"] == 91
    trip = stages["schematic"]["round_trip"]
    assert trip["ok"] is True and trip["problems"] == []
    assert (trip["nets_compared"], trip["components_compared"]) == (72, 94)
    name = "greenline_demo"
    for rel in ["%s.kicad_pcb" % name, "%s.kicad_pro" % name, "%s.kicad_dru" % name,
                "%s.kicad_sch" % name, "%s_mcu.kicad_sch" % name, "gleda.kicad_sym",
                "sym-lib-table", "fp-lib-table", "routing.json", "drc.json", "checks.json",
                "fab/README.txt", "fab/%s-F_Cu.gbr" % name, "fab/%s-In1_Cu.gbr" % name,
                "fab/%s-In2_Cu.gbr" % name, "fab/%s-B_Cu.gbr" % name,
                "fab/%s-Edge_Cuts.gbr" % name, "fab/%s-PTH.drl" % name,
                "fab/%s-NPTH.drl" % name, "fab/%s-PTH-drl_map.gbr" % name,
                "%s-fab.zip" % name, "assembly/%s-pos.csv" % name,
                "assembly/%s-bom.csv" % name, "%s-netlist.json" % name,
                "%s-mechanical.json" % name, "%s-board.step" % name,
                "renders/%s-top.png" % name,
                "renders/%s-top.svg" % name, "renders/%s-bottom.png" % name,
                "renders/%s-bottom.svg" % name, "schematic/%s-schematic.pdf" % name,
                "schematic/%s-schematic-1.png" % name, "schematic/%s.net" % name,
                "schematic/roundtrip.json", "outputs.json", "build_summary.json"]:
        path = os.path.join(out, rel)
        assert os.path.exists(path) and os.path.getsize(path) > 0, rel
    readme = open(os.path.join(out, "fab", "README.txt")).read()
    # the fine net class makes the board-level minimums 0.09 / 0.09 mm: stated
    assert "Minimum track width:        0.090 mm" in readme
    assert "Minimum copper clearance:   0.090 mm" in readme
    assert "0 error(s), 0 unconnected" in readme and "DO NOT FABRICATE" not in readme
    assert "Routed non-plated slot on Edge.Cuts: 1.150 x 1.650 mm" in readme
    assert "Non-plated hole H1: 1.150 mm at (-4.200, 14.550)" in readme
    assert "tented on the BOTTOM side" in readme
    mech = json.load(open(os.path.join(out, "%s-mechanical.json" % name)))
    assert mech["board"]["bounds"] == [-21.1, -21.1, 21.1, 17.3]
    assert [h["diameter"] for h in mech["board"]["npth_holes"]] == [1.15]
    assert len(mech["height_limits"]) == 2 and mech["height_limits"][0]["max_height"] == 0.95
    assert sum(1 for k in mech["keepouts"] if k["no_footprints"]) >= 8      # post feet
    assert len(mech["components"]) == 94
    # the project file still carries the board rules DRC ran with, and KiCad
    # still calls the final board clean
    pro = json.load(open(os.path.join(out, "%s.kicad_pro" % name)))
    from demo_design import demo_design
    want = board.project_dict(demo_design())
    assert pro["board"] == json.loads(json.dumps(want["board"]))
    assert pro["net_settings"] == json.loads(json.dumps(want["net_settings"]))
    assert len(pro["sheets"]) == 8
    res = drc.run_drc(os.path.join(out, "%s.kicad_pcb" % name), save=False,
                      report_path=os.path.join(out, "recheck.rpt"))
    drc.assert_clean(res)
    assert res.error_count == 0 and res.unconnected_count == 0 and res.tampered == []


def test_demo_flow_with_stored_routing(tmp_path):
    """The whole flow of ``demo/build_demo.py`` except the 8 minutes of
    routing: checks -> board -> stored routing (fingerprint-checked and
    audited again) -> zone fill -> KiCad DRC -> outputs -> schematic -> round
    trip, in a fresh directory."""
    if not os.path.exists(ROUTING):
        pytest.skip("no demo/demo_out/routing.json yet: run demo/build_demo.py")
    out = str(tmp_path / "demo_out")
    proc = subprocess.run(
        ["/usr/bin/python3", os.path.join(DEMO, "build_demo.py"), "--out", out,
         "--reuse-routing", ROUTING, "--quiet"],
        capture_output=True, text=True, timeout=1200)
    assert proc.returncode == 0, proc.stdout[-4000:] + proc.stderr[-2000:]
    assert "DEMO BUILD PASSED" in proc.stdout
    assert "reusing routing.json (design fingerprint matches)" in proc.stdout
    with open(os.path.join(out, "build_summary.json")) as f:
        summary = json.load(f)
    _check_complete_build(out, summary)
    with open(os.path.join(out, "build_run.json")) as f:
        assert json.load(f)["routing_reused"] is True


def test_demo_build_fails_honestly(tmp_path, monkeypatch, capsys):
    """Exit code and summary when a criterion is not met."""
    import build_demo
    from demo_design import demo_design

    def broken():
        design = demo_design()
        design.nets["CAM_EN"].nodes.remove(("U8", "EN"))        # an input left floating
        return design
    monkeypatch.setattr(build_demo, "demo_design", broken)
    out = str(tmp_path / "broken")
    assert build_demo.main(["--out", out, "--stages", "checks", "--quiet"]) == 1
    text = capsys.readouterr().out
    assert "DEMO BUILD FAILED" in text and "DEMO BUILD PASSED" not in text
    summary = json.load(open(os.path.join(out, "build_summary.json")))
    assert summary["passed"] is False and summary["criteria"]["checks_0_errors"] is False
    assert summary["criteria"]["routed_100_percent"] is None      # not checked, not claimed
    # a partial run that passes never prints the full-pass line
    monkeypatch.setattr(build_demo, "demo_design", demo_design)
    assert build_demo.main(["--out", out, "--stages", "checks", "--quiet"]) == 0
    text = capsys.readouterr().out
    assert "not a complete run" in text and "DEMO BUILD PASSED" not in text
    # stages that need earlier ones fail instead of being skipped
    assert build_demo.main(["--out", str(tmp_path / "empty"), "--stages",
                            "drc,outputs", "--quiet"]) == 1
    text = capsys.readouterr().out
    assert "DEMO BUILD FAILED" in text


def test_criteria_cannot_be_overridden_by_a_stage_flag():
    import build_demo
    stages = {"checks": {"errors": 0, "passed": True},
              "route": {"routed_percent": 99.6, "unrouted": [{"net": "X"}],
                        "audit_violations": 0, "passed": True},
              "drc": {"errors": 0, "unconnected": 1, "passed": True},
              "schematic": {"round_trip": {"ok": False}, "passed": True}}
    assert build_demo.criteria(stages) == {
        "checks_0_errors": True, "routed_100_percent": False,
        "kicad_drc_0_errors_0_unconnected": False, "schematic_round_trip_matches": False}
    assert build_demo.criteria({}) == {
        "checks_0_errors": None, "routed_100_percent": None,
        "kicad_drc_0_errors_0_unconnected": None, "schematic_round_trip_matches": None}


@pytest.mark.slow
def test_demo_build_end_to_end(tmp_path):
    """Everything from nothing, the router included (about 8 minutes):
    checks -> board -> route -> zone fill -> KiCad DRC -> outputs ->
    schematic -> netlist round trip."""
    out = str(tmp_path / "demo_out")
    proc = subprocess.run(
        ["/usr/bin/python3", os.path.join(DEMO, "build_demo.py"), "--out", out, "--quiet"],
        capture_output=True, text=True, timeout=3600)
    assert proc.returncode == 0, proc.stdout[-4000:] + proc.stderr[-2000:]
    assert "DEMO BUILD PASSED" in proc.stdout
    with open(os.path.join(out, "build_summary.json")) as f:
        summary = json.load(f)
    _check_complete_build(out, summary)
    with open(os.path.join(out, "build_run.json")) as f:
        assert json.load(f)["routing_reused"] is False
    # a fresh routing run gives the stored result again, byte for byte
    if os.path.exists(ROUTING):
        with open(ROUTING, "rb") as a, open(os.path.join(out, "routing.json"), "rb") as b:
            assert a.read() == b.read()
