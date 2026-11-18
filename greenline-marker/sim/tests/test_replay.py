"""The replay entry point (greenline_sim.replay): a logged measurement
record, run through the reference estimator, compared with a logged
estimate.  These tests need no firmware: the "logged" records are made here
from the reference's own Measurements."""
import math

import numpy as np
import pytest

from greenline_sim import estimator as es
from greenline_sim import replay
from greenline_sim.measurements import Measurements


def _meas(**over):
    base = dict(
        f_px=657.0, baseline=0.02, h_cam=0.0032, tilt=np.array([0.012, -0.020]), tilt_reads=1,
        flag_found=True, flag_bearing=0.05, flag_disparity=657.0 * 0.02 / 6.0,
        flag_low_elev=-0.0006, flag_base_visible=True, flag_top_visible=True,
        flag_top_elev=math.atan2(1.96, 6.0), stick_height_est=1.96, stick_height_rel_sigma=0.08,
        horizon_az=np.array([]), horizon_elev=np.array([]), grain_kappa=0.0, grain_azimuth=0.0,
        stimp_ft=10.0, user_distance=math.nan)
    base.update(over)
    return Measurements(**base)


def _record(ms, **extra):
    rec = {"drops": [m.to_dict() for m in ms], "ball_index": 0, "method": 0, "past": 0.30,
           "use_grain": False, "near_miss": 0.005}
    rec.update(extra)
    return rec


def test_replay_is_the_estimator_called_directly():
    m = _meas()
    rec = _record([m])
    ref = replay.replay_read(rec)
    direct = es.estimate_batch([[m]], "B1", replay.reference_config(0.30, False, 0.005))[0]
    assert ref == replay.estimate_to_dict(direct)
    assert ref["aim_source"] in (0, 1) and ref["flag_missing"] == 0
    assert ref["distance"] == pytest.approx(6.0, rel=0.02)


def test_dictionary_round_trip_keeps_not_a_number():
    m = _meas(flag_disparity=math.nan, user_distance=math.nan)
    d = m.to_dict()
    assert d["flag_disparity"] is None and d["user_distance"] is None
    back = Measurements.from_dict(d)
    assert math.isnan(back.flag_disparity) and math.isnan(back.user_distance)
    assert back.flag_bearing == m.flag_bearing


def test_a_fallback_read_replays_as_a_fallback():
    # no flagstick: the tilt-only plane at the dialled distance
    m = _meas(flag_found=False, flag_bearing=math.nan, flag_disparity=math.nan,
              flag_low_elev=math.nan, flag_base_visible=False, flag_top_visible=False,
              user_distance=4.5)
    ref = replay.replay_read(_record([m]))
    assert ref["flag_missing"] == 1
    assert ref["distance"] == pytest.approx(4.5)
    assert ref["bearing"] == 0.0


def test_survey_order_ball_index_is_honoured():
    near = _meas(tilt=np.array([0.010, -0.015]), flag_disparity=657.0 * 0.02 / 3.0,
                 flag_top_elev=math.atan2(1.96, 3.0))
    ball = _meas()
    a = replay.replay_read(_record([ball, near], ball_index=0))
    b = replay.replay_read(_record([near, ball], ball_index=1))
    assert a == b
    c = replay.replay_read(_record([near, ball], ball_index=0))
    assert c["distance"] != pytest.approx(a["distance"], rel=0.05)


def test_compare_accepts_the_firmware_tolerances_and_names_what_differs():
    rec = _record([_meas()])
    ref = replay.replay_read(rec)
    logged = dict(ref)
    assert replay.compare(ref, logged) == []
    logged["aim_azimuth_device"] = ref["aim_azimuth_device"] + 4e-4   # inside 0.5 mrad
    logged["v0"] = ref["v0"] * (1 + 5e-4)                            # inside 0.1 %
    assert replay.compare(ref, logged) == []
    logged["aim_azimuth_device"] = ref["aim_azimuth_device"] + 8e-4   # outside
    why = replay.compare(ref, logged)
    assert len(why) == 1 and why[0].startswith("aim_azimuth_device")
    logged = dict(ref)
    logged["aim_source"] = 2
    logged["fit_converged"] = 1 - ref["fit_converged"]
    why = replay.compare(ref, logged)
    assert any(w.startswith("aim_source") for w in why) and any(w.startswith("fit_converged") for w in why)


def test_replay_and_compare_reports_each_read():
    rec = _record([_meas()], read_id=17)
    rec["estimate"] = replay.replay_read(rec)
    bare = _record([_meas(tilt=np.array([0.0, 0.0]))], read_id=18)
    out = replay.replay_and_compare([rec, bare])
    assert out[0]["read_id"] == 17 and out[0]["mismatches"] == [] and out[0]["aim_diff_mrad"] == 0.0
    assert out[1]["logged"] is None and out[1]["mismatches"] is None


def test_bad_records_are_refused():
    with pytest.raises(ValueError):
        replay.replay_read({"drops": []})
    with pytest.raises(ValueError):
        replay.replay_read(_record([_meas()], ball_index=3))
