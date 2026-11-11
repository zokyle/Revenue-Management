"""Monte Carlo: determinism, pairing, bookkeeping and the truth-based references."""

import copy
import dataclasses
import json
import math
import re

import numpy as np
import pytest

from greenline_sim import estimator as es
from greenline_sim import greens as gr
from greenline_sim import montecarlo as mc
from greenline_sim import physics as ph
from greenline_sim import refvectors as rv
from greenline_sim import sensors as se

TINY = mc.MCConfig(distances=(1.5, 6.0), n_seeds=3, n_seeds_sweep=2, n_exec=20, master_seed=5)

# The full pipeline rolls tens of thousands of putts; with the pure-Python kernels
# (GREENLINE_SIM_NO_NUMBA=1, about 10 ms per roll) that takes many minutes.  The
# kernels themselves are compared between the two paths in test_fallback.py.
needs_numba = pytest.mark.skipif(not ph.HAVE_NUMBA, reason="full Monte Carlo is too slow without numba")


@pytest.fixture(scope="module")
def tiny_cases():
    cases, skipped = mc.build_cases(TINY)
    assert skipped == 0 and len(cases) == 3 * 4 * 2
    return cases


@pytest.fixture(scope="module")
def tiny_summary():
    return mc.run_all(TINY, log=lambda msg: None)


def _strip_runtime(summary):
    out = copy.deepcopy(mc._clean(summary))
    out["meta"].pop("runtime_s")
    return out


@needs_numba
def test_monte_carlo_is_deterministic(tiny_summary):
    again = mc.run_all(TINY, log=lambda msg: None)
    a = json.dumps(_strip_runtime(tiny_summary), sort_keys=True, default=mc._json_default)
    b = json.dumps(_strip_runtime(again), sort_keys=True, default=mc._json_default)
    assert a == b
    other = mc.run_all(dataclasses.replace(TINY, master_seed=6), log=lambda msg: None)
    c = json.dumps(_strip_runtime(other), sort_keys=True, default=mc._json_default)
    assert c != a


@needs_numba
def test_summary_is_strict_json_and_complete(tiny_summary):
    text = json.dumps(mc._clean(tiny_summary), allow_nan=False, default=mc._json_default)
    data = json.loads(text)
    meta = data["meta"]
    assert meta["n_putts_main"] == 24 and meta["n_putts_per_cell"] == 3 and meta["n_exec"] == 20
    assert meta["camera"]["name"] == "GL1" and meta["camera"]["f_px"] == 657.0
    main = data["main"]
    assert set(main["by_seat"]) == {"1", "2.5", "5"}
    for seat in main["by_seat"].values():
        for name in mc.DEVICE_METHODS + mc.REFERENCE_METHODS:
            table = seat[name]
            assert set(table["by_distance"]) == {"1.5", "6"}
            assert set(table["by_class"]) == set(gr.GREEN_CLASSES)
            assert len(table["by_distance_class"]) == 8
            row = table["by_distance"]["6"]
            assert row["n"] == 12 and 0.0 <= row["make_perfect"] <= 1.0 and 0.0 <= row["make_human"] <= 1.0
            assert row["p90_miss"] >= row["median_miss"] >= 0.0
    assert {"B2_NOSURROUND", "B2_NOFRINGE", "B2_MOUNDED"} <= set(main["by_seat"]["2.5"])
    assert set(main["horizon_test"]) == {"realistic", "no_surround", "no_fringe", "mounded"}
    for key in ("range", "flag", "slope_error", "calibration", "aim_sources", "unsolved", "subsets"):
        assert key in main["diagnostics"]
    for key in ("baseline", "camera", "h_cam_mm", "flag_base", "flag_base_paired", "stimp_error_pct", "grain", "horizon_sigma_mrad",
                "spin_seat_correlation", "survey_sigma_field_mrad", "range_first_hole"):
        assert key in data["sweeps"], key


@needs_numba
def test_oracle_holes_every_putt_and_references_are_seat_independent(tiny_summary):
    seats = tiny_summary["main"]["by_seat"]
    for seat in seats.values():
        assert seat["ORACLE"]["overall"]["make_perfect"] == 1.0
        assert seat["ORACLE"]["overall"]["median_miss"] < 1e-4
        assert abs(seat["ORACLE"]["overall"]["mean_pace_err"]) < 1e-3
    # common random numbers: methods that do not use the tilt give identical results at every seating level
    for name in ("STRAIGHT", "ORACLE", "ORACLE_SLOPE", "HUMAN05", "HUMAN10"):
        assert seats["1"][name] == seats["2.5"][name] == seats["5"][name], name
    assert seats["1"]["B1"] != seats["5"]["B1"]


def test_cases_hold_the_truth_of_each_putt(tiny_cases):
    for case in tiny_cases[:8]:
        sc = case.scenario
        assert case.distance == pytest.approx(float(np.hypot(*(sc.hole_xy - sc.ball_xy))))
        assert case.bearing == pytest.approx(sc.bearing) and case.mean_along == pytest.approx(sc.dz / sc.distance)
        gx, gy = sc.green.grad(*sc.ball_xy)
        assert case.local_cross == pytest.approx(-gx * math.sin(case.bearing) + gy * math.cos(case.bearing))
        roll = ph.simulate_putt(sc.green.surface, sc.ball_xy, sc.hole_xy, case.oracle_phi, case.oracle_v0, sc.green.a_r, sc.green.grain)
        assert case.oracle_ok and roll.captured and abs(roll.lateral_at_line) < 1e-4
    # a plane has the same cross slope everywhere and no double break
    planar = [c for c in tiny_cases if gr.GREEN_CLASSES[c.cls_idx] == "planar"]
    assert all(abs(c.local_cross - c.mean_cross) < 2e-3 and not c.double_break for c in planar)


def test_reads_and_fallbacks(tiny_cases):
    reads = mc.take_reads(tiny_cases, se.SensorParams(), TINY, spin=True, survey=True, flag_out=True)
    assert len(reads.first) == len(reads.quick) == len(reads.spin) == len(reads.survey) == len(reads.flag_out) == 24
    for i in range(24):
        assert reads.first[i][0].flag_found == reads.found[i]
        if reads.found[i]:
            assert reads.quick[i] is reads.first[i] and reads.survey[i][0] is reads.first[i]
            assert reads.spin[i][0].tilt_reads == 2 and reads.spin[i][1].heading == reads.first[i][1].heading
            assert 2 <= len(reads.survey[i]) <= 3
        else:  # camera read failed: every device mode works from the flag-out retry
            assert not reads.quick[i][0].flag_found and math.isfinite(reads.quick[i][0].user_distance)
            assert len(reads.survey[i]) == 1
        assert not reads.flag_out[i][0].flag_found
    # a camera that never finds the flag
    blind = dataclasses.replace(se.SensorParams(), p_detect_fail_floor=1.0)
    lost = mc.take_reads(tiny_cases[:6], blind, TINY)
    assert not lost.found.any() and all(math.isfinite(m.user_distance) for m, _ in lost.quick)
    with pytest.raises(ValueError):
        mc.take_reads(tiny_cases[:1], se.SensorParams(), TINY, fringe="jungle")
    with pytest.raises(ValueError):
        mc.device_launches(lost, ["B0S"])


def test_only_b2_differs_between_fringe_variants(tiny_cases):
    params = se.SensorParams()
    real = mc.device_launches(mc.take_reads(tiny_cases, params, TINY), ["B0", "B1", "B2"])
    for fringe in ("no_fringe", "no_surround", "mounded"):
        twin = mc.device_launches(mc.take_reads(tiny_cases, params, TINY, fringe=fringe), ["B0", "B1", "B2"])
        for name in ("B0", "B1"):
            assert np.array_equal(real[name].phi, twin[name].phi) and np.array_equal(real[name].v0, twin[name].v0)
        assert not np.array_equal(real["B2"].phi, twin["B2"].phi)


def test_launch_angle_includes_the_bearing_error(tiny_cases):
    cases = tiny_cases[:8]
    reads = mc.take_reads(cases, se.SensorParams(), TINY, with_horizon=False, flag_out=True)
    launches = mc.device_launches(reads, ["STRAIGHT", "FLAGOUT"])
    for i in range(len(cases)):
        meas, truth = reads.quick[i]
        if meas.flag_found:  # camera bearing: about 1 mrad
            err = math.remainder(truth.heading + meas.flag_bearing - truth.bearing, 2 * math.pi)
            assert launches["STRAIGHT"].phi[i] == pytest.approx(err, abs=1e-12) and abs(err) < 6e-3
        fo_meas, fo_truth = reads.flag_out[i]
        est = launches["FLAGOUT"].estimates[i]
        point_err = math.remainder(fo_truth.heading - fo_truth.bearing, 2 * math.pi)
        assert launches["FLAGOUT"].phi[i] == pytest.approx(point_err + est.phi, abs=1e-12)


def test_human_baselines_read_the_mean_cross_slope_with_the_stated_error(tiny_cases):
    reads = mc.take_reads(tiny_cases, se.SensorParams(), TINY, with_horizon=False)
    quiet = dataclasses.replace(TINY, human_cross_errors=(0.0, 0.010))
    ref = mc.reference_launches(tiny_cases, reads, quiet, ("HUMAN05", "HUMAN10", "ORACLE"))
    assert np.array_equal(ref["ORACLE"].phi, [c.oracle_phi for c in tiny_cases])
    assert ref["ORACLE"].n_unsolved == 0 and ref["HUMAN05"].n_unsolved == 0
    # with zero reading error on a planar green the human is the oracle up to speed/grain knowledge
    for i, case in enumerate(tiny_cases):
        meas, truth = reads.quick[i]
        a_r = ph.stimp_to_decel(meas.stimp_ft)
        grain = ph.Grain(meas.grain_kappa, meas.grain_azimuth + truth.heading - case.bearing)
        plane = ph.PlaneSurface(case.mean_along, case.mean_cross)
        sol = ph.solve_aim(plane, (0.0, 0.0), (case.distance, 0.0), a_r, grain)
        assert ref["HUMAN05"].phi[i] == pytest.approx(sol.phi, abs=1e-9)
        assert ref["HUMAN05"].v0[i] == pytest.approx(sol.v0, rel=1e-9)
    # a 1 % reading error moves the aim by roughly (5/14) G * 0.01 / a_r * pace factor, either way
    d_phi = ref["HUMAN10"].phi - ref["HUMAN05"].phi
    assert 0.02 < float(np.sqrt(np.mean(d_phi**2))) < 0.12 and (d_phi > 0).any() and (d_phi < 0).any()


def test_evaluate_rolls_on_the_true_green(tiny_cases):
    n = len(tiny_cases)
    oracle = mc.Launch(phi=np.array([c.oracle_phi for c in tiny_cases]), v0=np.array([c.oracle_v0 for c in tiny_cases]))
    wide = mc.Launch(phi=oracle.phi + 0.2, v0=oracle.v0)
    weak = mc.Launch(phi=oracle.phi, v0=0.5 * oracle.v0)
    out = mc.evaluate(tiny_cases, {"ORACLE": oracle, "WIDE": wide, "WEAK": weak}, TINY)
    assert out["ORACLE"].made.all() and np.abs(out["ORACLE"].lat).max() < 1e-4 and not out["ORACLE"].short.any()
    assert np.abs(out["ORACLE"].pace).max() < 2e-3  # arrives at the 0.30 m target pace
    assert not out["WIDE"].made.any() and np.all(out["WIDE"].lat > 0.1)  # aimed left: misses left
    assert out["WEAK"].short.all() and not out["WEAK"].made.any() and np.all(out["WEAK"].pace < -0.3)
    assert out["ORACLE"].lat_h.shape == (n, 20)
    # human execution noise is the same for every method and costs makes on the long putt
    six = np.array([c.distance == 6.0 for c in tiny_cases])
    assert out["ORACLE"].made_h[six].mean() < 0.6 < out["ORACLE"].made_h[~six].mean()
    single = tiny_cases[0]
    sc = single.scenario
    gen = mc._stream(TINY, single, mc._STREAM_EXECUTION)
    d_phi = TINY.sigma_dir * gen.standard_normal(20)
    f_v = 1.0 + TINY.sigma_speed * gen.standard_normal(20)
    direct = ph.roll_batch(sc.green.surface, sc.ball_xy, sc.hole_xy, single.oracle_phi + d_phi, single.oracle_v0 * f_v,
                           sc.green.a_r, sc.green.grain)
    assert out["ORACLE"].made_h[0] == pytest.approx(direct.captured.mean())
    assert np.allclose(out["ORACLE"].lat_h[0], direct.lateral_miss, atol=1e-6)
    with pytest.raises(ValueError):
        mc.evaluate(tiny_cases, {"BAD": mc.Launch(phi=np.full(n, np.nan), v0=oracle.v0)}, TINY)


def _outcome(lat, made):
    lat = np.asarray(lat, dtype=float)
    n = lat.size
    return mc.Outcome(
        lat=lat, made=np.asarray(made, dtype=bool), short=np.zeros(n, dtype=bool), leave=np.abs(lat),
        made_h=np.asarray(made, dtype=float), lat_h=np.tile(lat[:, None], (1, 20)).astype(np.float32), pace=np.zeros(n),
    )


def test_summary_statistics():
    out = _outcome([0.01, -0.02, 0.03, -0.04, 0.5], [True, True, True, False, False])
    s = mc.summarise(out)
    assert s["n"] == 5 and s["median_miss"] == pytest.approx(0.03) and s["make_perfect"] == pytest.approx(0.6)
    assert s["p90_miss"] == pytest.approx(np.percentile([0.01, 0.02, 0.03, 0.04, 0.5], 90))
    assert s["median_miss_human"] == pytest.approx(0.03) and s["make_human"] == pytest.approx(0.6)
    part = mc.summarise(out, np.array([True, True, False, False, False]))
    assert part["n"] == 2 and part["median_miss"] == pytest.approx(0.015) and part["make_perfect"] == 1.0
    assert mc.summarise(out, np.zeros(5, dtype=bool)) == {"n": 0}


def test_paired_delta_and_verdict():
    rng = np.random.default_rng(0)
    n = 400
    base = _outcome(rng.normal(0.0, 0.10, n), rng.random(n) < 0.3)
    better = _outcome(0.5 * base.lat, base.made | (rng.random(n) < 0.3))
    worse = _outcome(2.0 * base.lat, base.made & (rng.random(n) < 0.5))
    same = _outcome(base.lat + rng.normal(0.0, 1e-4, n), base.made)
    up = mc.paired_delta(base, better)
    assert up["d_make"] > 0 and up["d_mean_miss"] < 0 and up["b_closer"] == 1.0 and mc.verdict(up) == "helps"
    down = mc.paired_delta(base, worse)
    assert down["d_make"] < 0 and down["d_mean_miss"] > 0 and mc.verdict(down) == "hurts"
    assert mc.verdict(mc.paired_delta(base, same)) == "no measurable effect"
    assert mc.paired_delta(base, better)["d_make"] == pytest.approx(better.made.mean() - base.made.mean())
    assert mc.verdict({"n": 1}) == "not enough cases"
    # misses are clipped at 1 m in the mean so that a run-away ball cannot dominate
    far = _outcome(np.where(np.arange(n) == 0, 50.0, base.lat), base.made)
    assert abs(mc.paired_delta(base, far)["d_mean_miss"]) < 1.0 / n + 1e-9


def test_reference_vectors_are_deterministic_and_self_consistent(tmp_path):
    data = rv.write_reference_vectors(str(tmp_path), n_estimator=30, n_solver=24)
    again = rv.build_reference_vectors(n_estimator=30, n_solver=24)
    assert json.dumps(data, sort_keys=True) == json.dumps(again, sort_keys=True)
    loaded = json.loads((tmp_path / "reference_vectors.json").read_text())
    assert (tmp_path / "REFERENCE_VECTORS.md").read_text().startswith("# GreenLine reference vectors")
    assert len(loaded["estimator_cases"]) == 30 and len(loaded["solver_cases"]) == 24
    cfg = es.EstimatorConfig(**loaded["estimator_config"])
    assert cfg == rv.reference_config() and cfg.tol_miss == 1e-9
    modes = {c["mode"] for c in loaded["estimator_cases"]}
    assert {"B0", "B1", "B2", "PRECISION", "SURVEY3", "FLAG_OUT"} <= modes
    # re-running the estimator on the stored measurements reproduces the stored outputs exactly
    for case in loaded["estimator_cases"]:
        drops = [se.Measurements.from_dict(d) for d in case["measurements"]]
        est = es.estimate_batch([drops], case["method"], cfg)[0]
        exp = case["expected"]
        assert est.phi == exp["phi"] and est.v0 == exp["v0"] and list(est.patch) == exp["patch"]
        assert est.plays_like == exp["plays_like"] and est.break_m == exp["break_m"]
        assert est.aim_azimuth_device == pytest.approx(est.bearing + est.phi, abs=1e-12)
        assert exp["fit_converged"] and est.aim_source == exp["aim_source"]
    # solver cases: stored solution holes the putt at the target pace when re-rolled
    for case in loaded["solver_cases"]:
        if not case["compare_values"]:
            assert case["status_name"] != "OK"
            continue
        surf = ph.QuadraticSurface(*case["coeffs"])
        sol = ph.solve_aim(surf, (0.0, 0.0), (case["distance"], 0.0), case["a_r"], np.array(case["grain"]), case["past"],
                           tol_miss=1e-9, tol_pace=1e-9)
        assert sol.phi == case["phi"] and sol.v0 == case["v0"]
        roll = ph.simulate_putt(surf, (0.0, 0.0), (case["distance"], 0.0), case["phi"], case["v0"], case["a_r"], np.array(case["grain"]))
        if case["past"] == 0.0:  # the dying putt comes to rest at the hole centre
            assert roll.captured and roll.stop_distance < 1e-6
        else:
            assert abs(roll.lateral_at_line) < 1e-7
            assert roll.speed_at_line**2 == pytest.approx(2 * case["a_r"] * case["past"], abs=4e-8 * case["a_r"])
    # the closed-form anchor: dying putt on a pure cross slope
    anchors = [c for c in loaded["solver_cases"] if c["tag"].startswith("closed-form")]
    assert len(anchors) == 9
    for c in anchors:
        theory = ph.planar_break_angle(c["coeffs"][1], c["a_r"])
        assert c["phi"] == pytest.approx(theory, rel=0.035) and c["phi"] > theory


@needs_numba
def test_report_is_generated_from_the_summary(tiny_summary, tmp_path):
    from greenline_sim import report

    summary = json.loads(json.dumps(mc._clean(tiny_summary), default=mc._json_default))
    path = report.write_report(summary, str(tmp_path))
    text = open(path).read()
    assert text.startswith("# GreenLine simulation report")
    for heading in ("## 1. Headline", "## 4. Seating noise", "## 5. Is the turf horizon usable?", "## 6. Range to the flag",
                    "## 9. Sensing against human execution", "## 12. Where fusion helps", "## 13. Assumptions and limits",
                    "### 14.2 Closed-form check"):
        assert heading in text, heading
    assert "@@" not in text
    assert re.search(r"\bnan\b", text.lower()) is None and re.search(r"\binf\b", text.lower()) is None
    assert "N = 3 per (length, class) cell" in text  # the size of THIS run is stated
    for word in ("STRAIGHT", "B0S", "SURVEY3", "HUMAN05", "HUMAN10", "ORACLE", "mounded surrounds"):
        assert word in text
    figures = sorted(p.name for p in tmp_path.glob("fig*.png"))
    assert len(figures) == 8 and all((tmp_path / f).stat().st_size > 5000 for f in figures)
    for f in figures:
        assert f"({f})" in text
