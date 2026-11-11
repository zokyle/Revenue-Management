"""The GreenLine DEMO board: design checks, the stored routing judged afresh
by KiCad's DRC, and (slow) the whole demo build from nothing.

``demo/demo_out/routing.json`` is the routing the last demo build produced.
The quick test proves that it still belongs to the current design (same
fingerprint), re-audits it and takes it through a freshly built board and
KiCad's DRC.  The slow test runs ``demo/build_demo.py`` itself.
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


@pytest.mark.slow
def test_demo_build_end_to_end(tmp_path):
    """checks -> board -> route -> zone fill -> KiCad DRC, from nothing."""
    out = str(tmp_path / "demo_out")
    proc = subprocess.run(
        ["/usr/bin/python3", os.path.join(DEMO, "build_demo.py"), "--out", out,
         "--stages", "checks,board,route,drc", "--quiet"],
        capture_output=True, text=True, timeout=3600)
    assert proc.returncode == 0, proc.stdout[-4000:] + proc.stderr[-2000:]
    with open(os.path.join(out, "build_summary.json")) as f:
        summary = json.load(f)
    stages = summary["stages"]
    assert stages["checks"]["errors"] == 0
    assert stages["route"]["routed_percent"] == 100.0
    assert stages["route"]["audit_violations"] == 0
    assert stages["drc"]["errors"] == 0 and stages["drc"]["unconnected"] == 0
