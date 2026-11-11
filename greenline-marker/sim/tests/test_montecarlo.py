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
    assert meta["camera"]["baseline"] == 0.0200 and meta["camera"]["h_cam"] == 0.0056  # hardware revision C
    # the shipping configuration is stated in the summary
    assert meta["estimator_config"]["use_grain"] is False and meta["human_grain"] == "none"
    assert meta["sigma_transfer_deg"] == pytest.approx(0.5) and meta["display_step_deg"] == pytest.approx(math.degrees(2 / 122))
    assert meta["default_method"] == "B1"
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
    nominal = main["by_seat"]["2.5"]
    assert {"B2_NOSURROUND", "B2_NOFRINGE", "B2_MOUNDED", "B2C", "B2J", "B2L", "B2J_MOUNDED", "B1_GRAIN", "HUMAN05_GRAIN",
            "B1_CUPS", "FLAGOUT_CUPS"} <= set(nominal)
    assert set(main["horizon_test"]) == {"realistic", "no_surround", "no_fringe", "mounded"}
    for block in main["horizon_test"].values():
        assert {"anchored", "anchored_free_c", "joint", "joint_single_start", "fits"} == set(block)
        assert block["anchored"]["all"]["verdict"] and "planar" in block["anchored"]
        assert block["fits"]["anchored"]["mean_starts"] == 5.0 and block["fits"]["joint"]["mean_starts"] == 25.0
    # the forms of the horizon fit are rolled with a perfect stroke only: no human-execution numbers for them
    assert nominal["B2J"]["overall"]["make_human"] is None and nominal["B2"]["overall"]["make_human"] is not None
    for key in ("range", "flag", "slope_error", "confidence", "aim_sources", "unsolved", "subsets", "roll_status", "paired",
                "strong_grain"):
        assert key in main["diagnostics"]
    assert set(main["paired_by_seat"]) == {"1", "2.5", "5"} and "B1_vs_HUMAN05" in main["paired_by_seat"]["5"]
    band = main["seating_breakeven_mrad"]["B1_vs_HUMAN05"]["d_make"]
    assert {"mid", "lo", "hi", "first_level", "last_level"} <= set(band) and band["first_level"] == 1.0 and band["last_level"] == 5.0
    for key in ("baseline", "camera", "h_cam_mm", "flag_base", "flag_base_paired", "stimp_error_pct", "grain", "grain_vs_off",
                "grain_strong_greens", "grain_vs_human", "transfer_deg", "transfer_vs_human", "execution", "execution_paired",
                "capture", "capture_paired", "flagout_2x2", "flagout_2x2_paired", "survey_lateral_m", "survey_lateral_paired",
                "seating_ext_mrad", "seating_breakeven_mrad", "seating_outliers", "systematics", "relief_mm", "relief_paired",
                "relief_added_slope", "horizon_sigma_mrad", "horizon_domain_m", "spin_seat_correlation",
                "survey_sigma_field_mrad", "range_first_hole"):
        assert key in data["sweeps"], key
    sw = data["sweeps"]
    assert list(sw["transfer_deg"]) == ["0", "0.5", "1", "1.5", "0, ideal display"]
    assert list(sw["seating_ext_mrad"]) == ["1", "2.5", "5", "7.5", "10"] and list(sw["relief_mm"]) == ["0", "0.5", "1", "2"]
    assert list(sw["horizon_domain_m"]) == ["24", "40", "60"] and len(sw["execution"]) == 4
    # the sweep baseline is the default configuration: the 0.5 deg transfer row and the 2.5 mrad row are that baseline
    assert sw["transfer_deg"]["0.5"]["B1"] == sw["baseline"]["B1"] == sw["seating_ext_mrad"]["2.5"]["B1"] == sw["relief_mm"]["0"]["B1"]
    # the human baselines do not use the display
    assert sw["transfer_deg"]["1.5"]["HUMAN05"] == sw["baseline"]["HUMAN05"]
    assert sw["transfer_deg"]["1.5"]["B1"] != sw["baseline"]["B1"]


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
    # every roll's end status is accounted for
    status = tiny_summary["main"]["diagnostics"]["roll_status"]
    assert status["ORACLE"]["n"] == 24 and status["ORACLE"]["n_human"] == 24 * 20
    assert status["ORACLE"]["max_time"] == 0 and status["ORACLE"]["out_of_bounds"] == 0
    assert status["B2J"]["n_human"] == 0  # perfect-stroke-only variant
    assert seats["2.5"]["ORACLE"]["overall"]["not_at_rest"] == 0.0


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
    assert launches["FLAGOUT"].transfer and not launches["STRAIGHT"].transfer  # only device modes use the display
    for i in range(len(cases)):
        meas, truth = reads.quick[i]
        if meas.flag_found:  # camera bearing: about 1 mrad
            err = math.remainder(truth.heading + meas.flag_bearing - truth.bearing, 2 * math.pi)
            assert launches["STRAIGHT"].phi[i] == pytest.approx(err, abs=1e-12) and abs(err) < 6e-3
        fo_meas, fo_truth = reads.flag_out[i]
        est = launches["FLAGOUT"].estimates[i]
        point_err = math.remainder(fo_truth.heading - fo_truth.bearing, 2 * math.pi)
        assert launches["FLAGOUT"].phi[i] == pytest.approx(point_err + est.phi, abs=1e-12)


def test_display_quantises_the_line_and_the_cups_model_bypasses_it(tiny_cases):
    reads = mc.take_reads(tiny_cases, se.SensorParams(), TINY, with_horizon=False, flag_out=True)
    step = TINY.display_step
    assert step == pytest.approx(2.0 / 122.0) and math.degrees(step) == pytest.approx(0.94, abs=0.005)
    smooth = mc.device_launches(reads, ["B1", "STRAIGHT", "FLAGOUT"])
    drawn = mc.device_launches(reads, ["B1", "STRAIGHT", "FLAGOUT"], display_step=step)
    for name in ("B1", "FLAGOUT"):
        az = np.array([e.aim_azimuth_device for e in drawn[name].estimates])
        err = drawn[name].phi - smooth[name].phi
        # the drawn direction is the nearest multiple of the step
        assert np.allclose(err, np.round(az / step) * step - az, atol=1e-12) and np.abs(err).max() <= 0.5 * step + 1e-12
        assert np.abs(err).max() > 0.2 * step
        assert np.array_equal(drawn[name].v0, smooth[name].v0)
    assert np.array_equal(drawn["STRAIGHT"].phi, smooth["STRAIGHT"].phi)  # the golfer aims at the hole himself
    assert np.array_equal(mc.quantise_line(np.array([0.3, -0.2]), 0.0), [0.3, -0.2])
    # break in cups: the estimator's phi relative to the TRUE line, no display, no transfer, no bearing error
    cups = mc.cups_launch(drawn["FLAGOUT"])
    assert not cups.transfer and np.array_equal(cups.phi, [e.phi for e in drawn["FLAGOUT"].estimates])
    assert np.abs(cups.phi - drawn["FLAGOUT"].phi).max() > math.radians(0.5)  # the hand-pointing error is gone
    with pytest.raises(ValueError):
        mc.cups_launch(mc.Launch(phi=np.zeros(2), v0=np.ones(2)))


def test_human_baselines_read_the_mean_cross_slope_with_the_stated_error(tiny_cases):
    reads = mc.take_reads(tiny_cases, se.SensorParams(), TINY, with_horizon=False)
    quiet = dataclasses.replace(TINY, human_cross_errors=(0.0, 0.010))
    assert quiet.human_grain == "none"
    ref = mc.reference_launches(tiny_cases, reads, quiet, ("HUMAN05", "HUMAN10", "ORACLE", "ORACLE_SLOPE"))
    with_grain = mc.reference_launches(tiny_cases, reads, dataclasses.replace(quiet, human_grain="sensor"), ("HUMAN05",))
    assert np.array_equal(ref["ORACLE"].phi, [c.oracle_phi for c in tiny_cases])
    assert ref["ORACLE"].n_unsolved == 0 and ref["HUMAN05"].n_unsolved == 0
    assert not any(launch.transfer for launch in ref.values())  # nobody here reads a display
    # with zero reading error the human solves the plane of the true mean slopes with the entered speed:
    # without grain by default, with the device's grain reading if granted
    for i, case in enumerate(tiny_cases):
        meas, truth = reads.quick[i]
        a_r = ph.stimp_to_decel(meas.stimp_ft)
        grain = ph.Grain(meas.grain_kappa, meas.grain_azimuth + truth.heading - case.bearing)
        plane = ph.PlaneSurface(case.mean_along, case.mean_cross)
        sol = ph.solve_aim(plane, (0.0, 0.0), (case.distance, 0.0), a_r, None)
        assert ref["HUMAN05"].phi[i] == pytest.approx(sol.phi, abs=1e-9)
        assert ref["HUMAN05"].v0[i] == pytest.approx(sol.v0, rel=1e-9)
        sol_g = ph.solve_aim(plane, (0.0, 0.0), (case.distance, 0.0), a_r, grain)
        assert with_grain["HUMAN05"].phi[i] == pytest.approx(sol_g.phi, abs=1e-9)
        # ORACLE_SLOPE has the device's grain knowledge: none by default
        sc = case.scenario
        sol_s = ph.solve_aim(sc.green.surface, sc.ball_xy, sc.hole_xy, a_r, None)
        assert ref["ORACLE_SLOPE"].phi[i] == pytest.approx(sol_s.phi, abs=1e-12)
    with pytest.raises(ValueError):
        mc.reference_launches(tiny_cases, reads, dataclasses.replace(quiet, human_grain="psychic"), ("HUMAN05",))
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
    # every roll ended at rest or in the hole, and that is recorded
    assert np.all(out["ORACLE"].status == int(ph.RollStatus.STOPPED)) and out["ORACLE"].status_h.shape == (n, 20)
    assert mc.summarise(out["ORACLE"])["not_at_rest"] == 0.0


def test_aim_transfer_error_applies_to_device_launches_only(tiny_cases):
    n = len(tiny_cases)
    phi = np.array([c.oracle_phi for c in tiny_cases])
    v0 = np.array([c.oracle_v0 for c in tiny_cases])
    launches = {"REF": mc.Launch(phi=phi, v0=v0), "DEV": mc.Launch(phi=phi.copy(), v0=v0.copy(), transfer=True)}
    cfg = dataclasses.replace(TINY, sigma_transfer=math.radians(1.5))
    out = mc.evaluate(tiny_cases, launches, cfg)
    none = mc.evaluate(tiny_cases, launches, dataclasses.replace(TINY, sigma_transfer=0.0))
    # the reference launch is untouched by the transfer error; the device launch misses by D * error
    assert np.array_equal(out["REF"].lat, none["REF"].lat) and np.array_equal(out["REF"].made_h, none["REF"].made_h)
    assert np.array_equal(none["DEV"].lat, none["REF"].lat)
    z = np.array([float(mc._stream(cfg, c, mc._STREAM_TRANSFER).standard_normal()) for c in tiny_cases])
    dist = np.array([c.distance for c in tiny_cases])
    assert np.allclose(out["DEV"].lat - none["DEV"].lat, dist * math.radians(1.5) * z, rtol=0.25, atol=0.004)
    assert out["DEV"].made.mean() < out["REF"].made.mean() and out["DEV"].made_h.mean() < out["REF"].made_h.mean()
    # the same draw for every device launch: comparisons between device modes stay paired
    twice = mc.evaluate(tiny_cases, {"A": launches["DEV"], "B": launches["DEV"]}, cfg)
    assert np.array_equal(twice["A"].lat, twice["B"].lat)
    # perfect-stroke-only evaluation: the same perfect putt, no human-execution numbers
    quick = mc.evaluate(tiny_cases, launches, cfg, perfect_only=True)
    assert np.array_equal(quick["DEV"].lat, out["DEV"].lat) and np.array_equal(quick["DEV"].made, out["DEV"].made)
    assert quick["DEV"].lat_h.shape == (n, 0) and np.all(np.isnan(quick["DEV"].made_h))
    stats = mc.summarise(quick["DEV"])
    assert math.isnan(stats["make_human"]) and math.isnan(stats["median_miss_human"]) and stats["make_perfect"] == out["DEV"].made.mean()
    # a stricter capture rule can only lose putts
    strict = mc.evaluate(tiny_cases, launches, cfg, capture=ph.CaptureModel(exponent=1.0))
    assert strict["REF"].made_h.mean() <= out["REF"].made_h.mean() and np.array_equal(strict["REF"].lat, out["REF"].lat)


def test_rolls_that_do_not_come_to_rest_are_counted_not_dropped(tiny_cases):
    cases = tiny_cases[:6]
    n = len(cases)
    phi = np.array([c.oracle_phi for c in cases])
    v0 = np.array([c.oracle_v0 for c in cases])
    out = mc.evaluate(cases, {"OK": mc.Launch(phi=phi, v0=v0), "WILD": mc.Launch(phi=phi + 0.6, v0=14.0 * np.ones(n))}, TINY,
                      perfect_only=True)
    assert np.all(out["WILD"].status == int(ph.RollStatus.OUT_OF_BOUNDS)) and not out["WILD"].made.any()
    assert mc.summarise(out["WILD"])["not_at_rest"] == 1.0 and mc.summarise(out["OK"])["not_at_rest"] == 0.0
    table = mc._roll_status(out)
    assert table["WILD"] == {"max_time": 0, "out_of_bounds": n, "n": n, "max_time_human": 0, "out_of_bounds_human": 0, "n_human": 0}
    assert mc.summarise(out["WILD"])["n"] == n  # still in every statistic


def test_twin_cases_keep_the_putt_and_recompute_the_truth(tiny_cases):
    cases = tiny_cases[:6]
    twins = mc._twin_cases(cases, lambda c: c.scenario.green.with_relief(2e-3, seed=7), n_samples=65)
    for case, twin in zip(cases, twins):
        assert np.array_equal(twin.scenario.ball_xy, case.scenario.ball_xy) and np.array_equal(twin.scenario.hole_xy, case.scenario.hole_xy)
        assert (twin.cls_idx, twin.seed, twin.distance) == (case.cls_idx, case.seed, case.distance)
        assert twin.scenario.green is not case.scenario.green and twin.local_cross != case.local_cross
        # the same random streams: sensor noise and execution noise are paired with the original
        a = mc._stream(TINY, case, mc._STREAM_CAMERA).standard_normal(3)
        b = mc._stream(TINY, twin, mc._STREAM_CAMERA).standard_normal(3)
        assert np.array_equal(a, b)
        # the oracle was solved on the twin surface
        g = twin.scenario.green
        roll = ph.simulate_putt(g.surface, twin.scenario.ball_xy, twin.scenario.hole_xy, twin.oracle_phi, twin.oracle_v0, g.a_r, g.grain)
        assert twin.oracle_ok and roll.captured
    # the six putts are on one green: one twin object serves them all
    assert len({id(t.scenario.green) for t in twins}) == len({(c.cls_idx, c.seed) for c in cases})


def test_confidence_ranks_reads_at_a_fixed_distance_through_the_mode():
    """At a fixed putt length the score is higher for modes that know the
    cross slope better, and pooled over the modes it is (weakly) negatively
    rank-correlated with the miss.  Within one mode it carries next to
    nothing beyond the length - that limitation is asserted too, so that a
    future change which makes the score informative has to update the report."""
    cfg = dataclasses.replace(TINY, distances=(3.0, 6.0), n_seeds=60)
    cases, _ = mc.build_cases(cfg)
    reads = mc.take_reads(cases, se.SensorParams(), cfg, with_horizon=True, spin=True, survey=True)
    launches = mc.device_launches(reads, ["B1", "B2", "B0S", "SURVEY3"], display_step=cfg.display_step)
    out = mc.evaluate(cases, launches, cfg, perfect_only=True)
    dist = np.array([c.distance for c in cases])
    conf = {m: np.array([e.confidence for e in launches[m].estimates]) for m in launches}
    for d in cfg.distances:
        sel = (dist == d) & reads.found
        means = [conf[m][sel].mean() for m in ("B1", "B0S", "SURVEY3")]
        assert means[0] < means[1] < means[2]
        pooled_conf = np.concatenate([conf[m][sel] for m in ("B1", "B0S", "SURVEY3")])
        pooled_miss = np.concatenate([np.abs(out[m].lat[sel]) for m in ("B1", "B0S", "SURVEY3")])
        assert mc._spearman(pooled_conf, pooled_miss) < -0.04
        assert abs(mc._spearman(conf["B1"][sel], np.abs(out["B1"].lat[sel]))) < 0.35
        # the horizon never raises the score
        assert np.all(conf["B2"][sel] <= conf["B1"][sel] + 1e-15)
    table = mc._confidence_table(cases, launches, out, reads, cfg, ("B1", "B0S", "SURVEY3"))
    for m in ("B1", "B0S", "SURVEY3"):
        row = table[m]
        assert 0.7 < row["z_rms"] < 1.4  # the claimed sigma of the mean cross slope is about right
        assert abs(row["mean_confidence"] - row["within_hole"]) < 0.08
        assert row["spearman_pooled"] < -0.3 and row["spearman_minus_distance"] < -0.3
        assert abs(row["spearman_within_length"]) < 0.35
    assert mc._spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0) and math.isnan(mc._spearman([1, 1, 1], [1, 2, 3]))


def _outcome(lat, made):
    lat = np.asarray(lat, dtype=float)
    n = lat.size
    return mc.Outcome(
        lat=lat, made=np.asarray(made, dtype=bool), short=np.zeros(n, dtype=bool), leave=np.abs(lat),
        made_h=np.asarray(made, dtype=float), lat_h=np.tile(lat[:, None], (1, 20)).astype(np.float32), pace=np.zeros(n),
        status=np.zeros(n, dtype=np.int8), status_h=np.zeros((n, 20), dtype=np.int8),
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
    assert up["d_make_human"] == pytest.approx(up["d_make"]) and up["make_b"] == pytest.approx(better.made.mean())
    # a verdict names the measure that moved when only one of the two does
    closer = _outcome(0.5 * base.lat, base.made)
    assert mc.verdict(mc.paired_delta(base, closer)) == "reduces the mean miss, makes unchanged"
    wider = _outcome(2.0 * base.lat, base.made)
    assert mc.verdict(mc.paired_delta(base, wider)) == "increases the mean miss, makes unchanged"
    luckier = _outcome(base.lat, base.made | (rng.random(n) < 0.3))
    assert mc.verdict(mc.paired_delta(base, luckier)) == "raises the make probability, mean miss unchanged"
    odd = _outcome(2.0 * base.lat, base.made | (rng.random(n) < 0.3))
    assert mc.verdict(mc.paired_delta(base, odd)).startswith("mixed")
    assert [mc.verdict_sign(v) for v in ("helps", "hurts", "no measurable effect", "reduces the mean miss, makes unchanged",
                                         "lowers the make probability, mean miss unchanged")] == [1, -1, 0, 1, -1]
    # break-even interpolation
    assert mc._crossing([1.0, 2.5, 5.0], [0.32, 0.30, 0.25], 0.29) == pytest.approx(3.0)
    assert mc._crossing([1.0, 2.5, 5.0], [0.32, 0.30, 0.25], 0.10) is None
    deltas = [{"d_make": 0.03, "d_make_se": 0.005}, {"d_make": 0.0, "d_make_se": 0.005}, {"d_make": -0.05, "d_make_se": 0.005}]
    band = mc.breakeven_band([1.0, 2.5, 5.0], deltas)
    assert band["mid"] == pytest.approx(2.5) and band["lo"] == pytest.approx(1.0 + 1.5 * (0.03 - 0.0098) / 0.03)
    assert band["hi"] == pytest.approx(2.5 + 2.5 * 0.0098 / 0.05) and band["ahead_at_first"] and band["behind_at_last"]
    never = mc.breakeven_band([1.0, 5.0], [{"d_make": 0.10, "d_make_se": 0.01}, {"d_make": 0.08, "d_make_se": 0.01}])
    assert never["mid"] is None and never["lo"] is None and never["hi"] is None and not never["behind_at_last"]
    # misses are clipped at 1 m in the mean so that a run-away ball cannot dominate
    far = _outcome(np.where(np.arange(n) == 0, 50.0, base.lat), base.made)
    assert abs(mc.paired_delta(base, far)["d_mean_miss"]) < 1.0 / n + 1e-9


def test_reference_vectors_are_deterministic_and_self_consistent(tmp_path):
    data = rv.write_reference_vectors(str(tmp_path), n_estimator=44, n_solver=28)
    again = rv.build_reference_vectors(n_estimator=44, n_solver=28)
    assert json.dumps(data, sort_keys=True) == json.dumps(again, sort_keys=True)
    loaded = json.loads((tmp_path / "reference_vectors.json").read_text())
    schema = (tmp_path / "REFERENCE_VECTORS.md").read_text()
    assert schema.startswith("# GreenLine reference vectors") and "baseline` = 0.02 m" in schema
    assert loaded["schema_version"] == 2
    assert len(loaded["estimator_cases"]) == 44 and len(loaded["solver_cases"]) == 28
    cfg = es.EstimatorConfig(**loaded["estimator_config"])
    assert cfg == rv.reference_config() and cfg.tol_miss == 1e-9 and cfg.use_grain is False and cfg.horizon_joint is False
    modes = {c["mode"] for c in loaded["estimator_cases"]}
    assert {"B0", "B1", "B2", "PRECISION", "SURVEY3", "FLAG_OUT", "B1_GRAIN", "RANGE_MISSING"} <= modes
    # hardware revision C travels inside the measurements
    assert all(m["baseline"] == 0.0200 and m["f_px"] == 657.0 and m["h_cam"] == 0.0056
               for c in loaded["estimator_cases"] for m in c["measurements"])
    # re-running the estimator on the stored measurements reproduces the stored outputs exactly
    n_fitted = 0
    for case in loaded["estimator_cases"]:
        drops = [se.Measurements.from_dict(d) for d in case["measurements"]]
        est = es.estimate_batch([drops], case["method"], dataclasses.replace(cfg, **case["config_overrides"]))[0]
        exp = case["expected"]
        assert est.phi == exp["phi"] and est.v0 == exp["v0"] and list(est.patch) == exp["patch"]
        assert est.plays_like == exp["plays_like"] and est.break_m == exp["break_m"]
        assert est.aim_azimuth_device == pytest.approx(est.bearing + est.phi, abs=1e-12)
        assert exp["fit_converged"] and est.aim_source == exp["aim_source"] and est.confidence == exp["confidence"]
        assert est.slope_pct == pytest.approx(100.0 * math.hypot(*exp["tilt_slopes"]), rel=1e-12)
        if case["mode"] == "B1_GRAIN":
            assert case["config_overrides"] == {"use_grain": True}
        else:
            assert case["config_overrides"] == {} and exp["grain"] == [0.0, 0.0]
        if case["mode"] == "RANGE_MISSING":
            assert exp["range_missing"] and not exp["flag_missing"] and exp["bearing"] == drops[0].flag_bearing
            assert exp["distance"] == cfg.default_distance and case["fit_check"] is None
        # every fitted case is start-independent: no alternative start or damping finds a lower cost,
        # and all runs at the reference cost give the same patch
        check = case["fit_check"]
        if check is not None:
            n_fitted += 1
            assert case["start_independent"] and check["start_independent"] and check["n_runs"] == 43
            assert check["lowest_cost_found"] >= check["cost"] * (1.0 - 1e-6) - 1e-9
            assert check["max_patch_difference_scaled"] < 1e-6
            assert exp["fit_starts"] == (5 if exp["used_horizon"] else 1)
        else:
            assert exp["fit_starts"] == 0
    assert n_fitted >= 25
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
    # the two regression anchors of the roll kernel and the solver are solved
    regress = [c for c in loaded["solver_cases"] if c["tag"].startswith("regression")]
    assert len(regress) == 2 and all(c["status_name"] == "OK" for c in regress)
    assert loaded["constants"]["H_STIFF"] == 0.5 and loaded["constants"]["LINE_MISS_OFFSET"] == 1.0


@needs_numba
def test_report_is_generated_from_the_summary(tiny_summary, tmp_path):
    from greenline_sim import report

    summary = json.loads(json.dumps(mc._clean(tiny_summary), default=mc._json_default))
    path = report.write_report(summary, str(tmp_path))
    text = open(path).read()
    assert text.startswith("# GreenLine simulation report")
    for heading in ("## 1. Headline", "## 3. What each sensor buys", "## 4. Seating noise, aim transfer",
                    "### 4.2 Aim transfer", "### 4.3 Metre-scale relief", "## 5. Is the turf horizon usable?",
                    "## 6. Range to the flag", "## 9. Sensing against human execution", "## 10. Bearing and distance",
                    "## 12. Where fusion helps", "## 13. Limitations and honest caveats", "### 14.2 Closed-form check",
                    "### 14.3 Numerics"):
        assert heading in text, heading
    # the sensor chain table, the shipping configuration and the use model are stated
    assert "| STRAIGHT | camera bearing and range" in text and "| B2 | + turf-horizon profile" in text
    assert "Shipping configuration" in text and "follows the LINE" in text and "break in cup" in text
    assert "baseline 20 mm" in text and "revision C" in text
    assert "@@" not in text
    assert re.search(r"\bnan\b", text.lower()) is None and re.search(r"\binf\b", text.lower()) is None
    assert "N = 3 per (length, class) cell" in text  # the size of THIS run is stated
    for word in ("STRAIGHT", "B0S", "SURVEY3", "HUMAN05", "HUMAN10", "ORACLE", "mounded surrounds"):
        assert word in text
    figures = sorted(p.name for p in tmp_path.glob("fig*.png"))
    assert len(figures) == 9 and all((tmp_path / f).stat().st_size > 5000 for f in figures)
    for f in figures:
        assert f"({f})" in text
