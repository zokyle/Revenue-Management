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
    # The demo does not confine its fine classes (see FINE_AREAS in the design
    # script for why): the checks say so, and so does the fab README.
    assert demo.fine_areas == [] and minimums["fine_classes"] == ["CamPower", "Fine"]
    assert not any(demo.is_confined(name) for name in fine)
    report = checks.run_checks(demo)
    assert [f.code for f in report.findings] == ["fine_unconfined"]
    # ... while the same design with fine areas is a valid, confined design
    import demo_design as module
    old = module.FINE_AREAS
    try:
        module.FINE_AREAS = (("U2", 5.0), ("U3", 5.0))
        confined = module.demo_design()
    finally:
        module.FINE_AREAS = old
    assert [a.name for a in confined.fine_areas] == ["fine_U2", "fine_U3"]
    assert all(confined.is_confined(name) for name in fine)
    assert confined.outside_values("CAM_D0") == (0.15, 0.127)
    assert confined.clearance("CAM_D0", "CAM_D1", outside_a=True) == 0.127
    assert checks.run_checks(confined).findings == []


def test_demo_fab_and_assembly_details(demo):
    """Fiducials, via protection and fab notes of the design spec are in the
    demo (review findings)."""
    marks = [p for p in demo.parts if checks.is_fiducial(p)]
    assert sorted(p.side for p in marks) == ["bottom"] * 3 + ["top"] * 3
    assert all(p.board_only and not p.in_bom for p in marks)
    for side in ("top", "bottom"):
        pts = [(p.x, p.y) for p in marks if p.side == side]
        (ax, ay), (bx, by), (cx, cy) = pts
        area = abs((bx - ax) * (cy - ay) - (cx - ax) * (by - ay)) / 2.0
        assert area > 50.0                          # far apart and not in line
    assert not checks.run_checks(demo).find("no_fiducials")
    assert demo.via_tenting == "bottom"
    assert "plugged" in demo.via_protection and "BOTTOM" in demo.via_protection
    assert any("wetted" in note for note in demo.fab_notes)


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
    # review findings: plugging, fab notes, the measured account of the fine tracks
    assert "Via protection:      plugged with solder mask from the BOTTOM side" in readme
    assert "FAB NOTES" in readme and "wetted surface" in readme
    assert "Via to pad, top:     design rule 0.200 mm" in readme
    assert "TRACKS AS ROUTED (measured on the board these files were plotted from)" in readme
    assert "only where a fine-pitch package needs them" not in readme
    # the fine classes are not confined on the demo: the README says where the
    # fine tracks really are instead of reassuring anybody
    copper = stages["outputs"]["copper"]
    assert copper["confined"] is False and copper["fine_areas"] == []
    assert copper["narrow_length_mm"] > 20.0 and copper["fine_pitch_arrays"] == ["U2", "U3"]
    far = copper["narrow_farthest"]
    assert "Net classes below the standard 0.150 / 0.127 mm: CamPower, Fine." in readme
    assert "Tracks narrower than 0.150 mm: %.1f mm on %d net(s)." % (
        copper["narrow_length_mm"], len(copper["narrow_nets"])) in readme
    assert "The design declares no fine areas: these tracks may run anywhere along their " \
           "nets; the farthest is %s on %s" % (far["net"], far["layer"]) in readme
    assert "Quote the whole board at the board-level minimums." in readme
    table = copper["length_by_width"]
    assert abs(sum(row["total"] for row in table.values())
               - stages["route"]["track_length_mm"]) < 0.5
    assert copper["min_via_to_own_pad_gap"]["top"] >= 0.2 - 1e-6
    assert [o["ref"] for o in stages["outputs"]["anchor_offsets"]] == ["J1"]
    asm = open(os.path.join(out, "assembly", "README.txt")).read()
    assert "Origin:   the centre of the board" in asm and "J1     anchor" in asm
    assert "top:    (-19.300, -0.800), (19.000, -3.000), (-16.500, 9.900)" in asm
    assert os.path.getsize(os.path.join(out, "%s-assembly.zip" % name)) > 1000
    quality = stages["route"]["quality"]
    assert quality["signal_ratio"] >= 1.0 and isinstance(quality["warnings"], list)
    mech = json.load(open(os.path.join(out, "%s-mechanical.json" % name)))
    assert mech["board"]["bounds"] == [-21.1, -21.1, 21.1, 17.3]
    assert [h["diameter"] for h in mech["board"]["npth_holes"]] == [1.15]
    assert len(mech["height_limits"]) == 2 and mech["height_limits"][0]["max_height"] == 0.95
    assert sum(1 for k in mech["keepouts"] if k["no_footprints"]) >= 8      # post feet
    assert len(mech["components"]) == 100          # 94 parts and six fiducials
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


def test_quickstart_board_passes_the_whole_flow(tmp_path):
    """``demo/quickstart_board.py`` is the example the README's quick start
    quotes.  It must run as written: checks without a finding, every
    connection routed with the fine class confined to its fine area, KiCad DRC
    clean, outputs equal to the model, schematic round trip."""
    import quickstart_board
    d = quickstart_board.quickstart_design()
    report = checks.run_checks(d)
    assert report.ok and not report.findings, report.text()
    assert d.is_confined("D0") and not d.is_confined("SCL")
    assert d.outside_values("D0") == (0.15, 0.127)
    lines = []
    assert quickstart_board.build(d, str(tmp_path), say=lines.append) == 0, "\n".join(lines)
    text = "\n".join(lines)
    assert "routed 16/16 connections (100.0 %)" in text
    assert "KiCad DRC: 0 error(s), 0 unconnected" in text
    assert "0 problem(s) against the model" in text
    assert "netlist round trip matches: 10 nets, 26 pads, 4 components" in text
    assert "OPEN" not in text
    with open(os.path.join(str(tmp_path), "fab", "README.txt")) as f:
        readme = f.read()
    assert "Every one of these tracks lies completely inside a fine area" in readme
    assert "plugged from the bottom side" in readme
    with open(os.path.join(str(tmp_path), "assembly", "README.txt")) as f:
        assembly = f.read()
    assert "(-9.500, 4.000)" in assembly and "(9.000, -4.500)" in assembly   # fiducials
    for fn in ("quickstart-fab.zip", "quickstart-assembly.zip", "quickstart-netlist.json",
               "quickstart-mechanical.json", "schematic.pdf", "quickstart.net"):
        assert os.path.getsize(os.path.join(str(tmp_path), fn)) > 0, fn


def test_quickstart_pitfall_is_reported_with_its_reason(tmp_path):
    """The mistake a first design makes: an inner ball of the 0.5 mm BGA on a
    class too wide to pass between the balls.  The router must not hang and
    must not pretend: the connection is open, the net says why, the build
    function returns failure and nothing is plotted."""
    import quickstart_board
    d = quickstart_board.quickstart_design()
    d.nets["D0"].netclass = "Power"                    # 0.30 mm: cannot leave ball B2
    lines = []
    assert quickstart_board.build(d, str(tmp_path), say=lines.append) == 1
    text = "\n".join(lines)
    assert "routed 15/16 connections" in text
    assert "OPEN D0" in text and "no path from U1.B2 to J1.3" in text
    assert not os.path.exists(os.path.join(str(tmp_path), "fab"))


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
