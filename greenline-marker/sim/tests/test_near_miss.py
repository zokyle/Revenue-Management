"""EstimatorConfig.near_miss_keep (added after the firmware review, phase 2).

Off by default: every published result and every reference vector outside
``near_miss_estimator_cases`` is unchanged.  On: the best iterate of the aim
solve on the fitted patch is kept when it passes within ``near_miss_keep`` of
the hole centre, instead of the secant-plane fallback.
"""

import json
import os
from dataclasses import asdict, replace

import numpy as np
import pytest

from greenline_sim import estimator as es
from greenline_sim import physics as ph
from greenline_sim import refvectors as rv
from greenline_sim.measurements import Measurements
from greenline_sim.refvectors_near_miss import NEAR_MISS_CASES

RESULTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results", "reference_vectors.json")


def _drops(entry):
    return [Measurements.from_dict(d) for d in entry["drops"]]


def test_default_is_off():
    assert es.EstimatorConfig().near_miss_keep == 0.0
    assert rv.reference_config().near_miss_keep == 0.0


def test_off_is_the_old_estimate_and_on_keeps_a_near_miss():
    cfg = rv.reference_config()
    kept = 0
    for entry in NEAR_MISS_CASES:
        drops = _drops(entry)
        off = es.estimate_batch([drops], "B1", replace(cfg, past=entry["past"]))[0]
        on = es.estimate_batch([drops], "B1", replace(cfg, past=entry["past"], near_miss_keep=0.005))[0]
        # the rule is about the aim only: the fit is the same object either way
        assert np.array_equal(off.patch, on.patch)
        assert off.distance == on.distance and off.a_r == on.a_r
        assert off.aim_source in (es.AIM_FROM_PLANE, es.AIM_BEST_EFFORT)  # every case is a fallback without it
        sol = ph.solve_aim_quadratic_batch(
            np.array([off.fit.coeffs]), np.array([off.fit.distance]), np.array([off.a_r]), np.array([off.grain]),
            entry["past"], tol_miss=cfg.tol_miss, tol_pace=cfg.tol_pace,
        )
        assert not bool(sol.usable[0])
        miss = float(sol.miss[0])
        if abs(miss) <= 0.005:
            kept += 1
            assert on.aim_source == es.AIM_FROM_PATCH
            assert on.solve_status == int(sol.status[0])  # how the solve ended is reported
            assert on.phi == float(sol.phi[0]) and on.v0 == float(sol.v0[0])
            # scored as a fallback, like the aim it replaces
            assert on.confidence == pytest.approx(off.confidence, rel=1e-12)
        else:
            assert (on.aim_source, on.solve_status, on.phi, on.v0) == (off.aim_source, off.solve_status, off.phi, off.v0)
    assert kept == 14


def test_a_usable_solution_is_never_touched():
    # a plain read: the option changes nothing
    m = Measurements(
        f_px=657.0, baseline=0.02, h_cam=0.0056, tilt=np.array([0.012, -0.018]), tilt_reads=1, flag_found=True,
        flag_bearing=0.05, flag_disparity=657.0 * 0.02 / 6.0, flag_low_elev=-0.0008, flag_base_visible=True,
        flag_top_visible=False, flag_top_elev=float("nan"), stick_height_est=1.96, stick_height_rel_sigma=0.07,
        horizon_az=np.array([]), horizon_elev=np.array([]), grain_kappa=0.0, grain_azimuth=0.0, stimp_ft=10.0,
    )
    off = es.estimate(m)
    on = es.estimate(m, config=replace(es.EstimatorConfig(), near_miss_keep=0.005))
    assert off.aim_source == es.AIM_FROM_PATCH and off.solve_status == int(ph.SolveStatus.OK)
    assert asdict(replace(off, fit=None)).keys() == asdict(replace(on, fit=None)).keys()
    assert (on.phi, on.v0, on.confidence, on.aim_source, on.solve_status) == (
        off.phi, off.v0, off.confidence, off.aim_source, off.solve_status)


def test_vectors_file_has_the_group_and_the_old_config_block():
    with open(RESULTS) as fh:
        data = json.load(fh)
    assert data["schema_version"] == 2
    assert "near_miss_keep" not in data["estimator_config"]  # the file is unchanged up to the appended group
    cases = data["near_miss_estimator_cases"]
    assert len(cases) == 18 and sum(1 for c in cases if c["kept"]) == 14
    assert list(data.keys())[-1] == "near_miss_estimator_cases"
    regenerated = rv._near_miss_estimator_cases(rv.reference_config())
    assert json.loads(json.dumps(regenerated)) == cases
    for c in cases:
        assert c["config_overrides"]["near_miss_keep"] == 0.005
        if c["kept"]:
            assert c["expected"]["aim_source"] == 0 and c["expected"]["solve_status"] not in (0, 1)
            assert abs(c["patch_solve"]["miss"]) <= 0.005
            assert c["without_rule"]["aim_source"] in (1, 2)
        else:
            assert abs(c["patch_solve"]["miss"]) > 0.005
            assert c["expected"]["aim_source"] == c["without_rule"]["aim_source"]
            assert c["expected"]["phi"] == c["without_rule"]["phi"]
