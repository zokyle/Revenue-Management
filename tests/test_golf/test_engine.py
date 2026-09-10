"""Unit tests for the golf strategy engine (baselines, geometry, learning, optimizer)."""

from types import SimpleNamespace as NS
from datetime import date

import numpy as np
import pytest

from golf.engine import baselines
from golf.engine.baselines import Lie, default_club_prior, expected_putts, expected_strokes
from golf.engine.dispersion import ClubDistribution, landing_points, sample_shots
from golf.engine.hole_model import FeatureBox, HoleGeometry
from golf.engine.learning import ProfileBuilder, personal_expected_strokes, readiness_level
from golf.engine.strategy import StrategyEngine


# ---------------------------------------------------------------------------
# Baselines
# ---------------------------------------------------------------------------
def test_tour_baseline_matches_broadie_anchor_values():
    assert expected_strokes("fairway", 150, 0) == pytest.approx(2.945, abs=0.01)
    assert expected_strokes("tee", 400, 0) == pytest.approx(3.99, abs=0.01)
    assert expected_strokes("sand", 20, 0) == pytest.approx(2.53, abs=0.01)
    assert expected_putts(10, 0) == pytest.approx(1.61, abs=0.01)
    assert expected_putts(3, 0) == pytest.approx(1.053, abs=0.01)


def test_handicap_scaling_is_monotone_and_reasonable():
    for lie in ("tee", "fairway", "rough", "sand"):
        prev = expected_strokes(lie, 150, 0)
        for h in (5, 10, 18, 25):
            cur = expected_strokes(lie, 150, h)
            assert cur > prev
            prev = cur
    # An 18-handicap averages roughly a bogey on a 400-yard par 4.
    assert 4.8 <= expected_strokes("tee", 400, 18) <= 5.2
    # Distance monotonicity from the fairway.
    vals = [expected_strokes("fairway", d, 12) for d in (50, 100, 150, 200, 250)]
    assert all(b > a for a, b in zip(vals, vals[1:]))


def test_penalty_and_ob_cost_a_full_stroke_plus():
    assert expected_strokes("penalty", 150, 10) > expected_strokes("rough", 150, 10) + 1.0
    assert expected_strokes("ob", 400, 10) >= expected_strokes("tee", 400, 10) + 1.0


def test_default_club_priors_interpolate_by_handicap():
    scratch = default_club_prior("D", 0)
    mid = default_club_prior("D", 9)
    high = default_club_prior("D", 18)
    assert scratch["carry_mean"] > mid["carry_mean"] > high["carry_mean"]
    assert scratch["lateral_sigma"] < high["lateral_sigma"]
    assert default_club_prior("nope", 10) is None


# ---------------------------------------------------------------------------
# Hole geometry
# ---------------------------------------------------------------------------
@pytest.fixture
def par4():
    return HoleGeometry(number=1, par=4, yards=420, features=[
        FeatureBox("water", "left", 230, 300, offset_yards=22, label="pond"),
        FeatureBox("ob", "right", 0, 420, offset_yards=35, label="OB"),
        FeatureBox("bunker", "right", 360, 385, offset_yards=12, width_yards=10, label="greenside bunker"),
    ])


def test_classification_of_landing_spots(par4):
    assert par4.classify_point(250, 0).lie == "fairway"
    assert par4.classify_point(250, -25).lie == "penalty"
    assert par4.classify_point(250, -25).penalty_strokes == 1.0
    assert par4.classify_point(250, 40).lie == "ob"
    assert par4.classify_point(250, 25).lie == "rough"
    assert par4.classify_point(370, 15).lie == "sand"
    assert par4.classify_point(420, 0).lie == "green"
    assert par4.classify_point(420, 0).distance_to_hole == 0
    assert par4.classify_point(50, 0).lie == "rough"  # short of the fairway start
    beyond = par4.classify_point(250, 34)
    assert beyond.lie == "rough" and beyond.extra_strokes > 0


def test_dogleg_world_local_roundtrip():
    g = HoleGeometry(number=2, par=4, yards=400, shape="dogleg_right", dogleg_at_yards=240, dogleg_angle_deg=40)
    gx, gy = g.green_center_world()
    assert gx == pytest.approx(240 + 160 * np.cos(np.radians(40)))
    assert gy == pytest.approx(160 * np.sin(np.radians(40)))
    # A point on the second segment maps back to its local coordinates.
    wx, wy = g.local_to_world(300, 5)
    x, y = g.world_to_local(np.array([wx]), np.array([wy]))
    assert x[0] == pytest.approx(300, abs=1e-6)
    assert y[0] == pytest.approx(5, abs=1e-6)
    # Driving straight through a right-hand corner puts you LEFT of the new centerline.
    x, y = g.world_to_local(np.array([270.0]), np.array([0.0]))
    assert y[0] < -10


def test_vectorised_classification_matches_point(par4):
    xs = np.array([250.0, 250.0, 250.0, 420.0])
    ys = np.array([0.0, -25.0, 40.0, 0.0])
    wx, wy = xs, ys  # straight hole: world == local
    r = par4.classify_world(wx, wy)
    assert list(r["lie"]) == ["fairway", "penalty", "ob", "green"]
    assert r["penalty"].tolist() == [0.0, 1.0, 1.0, 0.0]


def test_render_spec_has_drawable_pieces(par4):
    spec = par4.render_spec()
    assert spec["fairway"]["half_width"] == 17.5
    assert spec["green"]["x"] == 420
    assert len(spec["features"]) == 3
    assert all(f["width"] <= 60 for f in spec["features"])


# ---------------------------------------------------------------------------
# Dispersion
# ---------------------------------------------------------------------------
def test_sample_shots_reproduce_distribution():
    rng = np.random.default_rng(0)
    d = ClubDistribution("D", 245, 12, 22, lateral_bias=5, p_mishit=0.0)
    s = sample_shots(d, 20000, rng)
    assert s.carry.mean() == pytest.approx(245, abs=0.5)
    assert s.carry.std() == pytest.approx(12, abs=0.5)
    assert s.lateral.mean() == pytest.approx(5, abs=0.5)
    assert s.lateral.std() == pytest.approx(22, abs=0.5)


def test_mishits_shorten_carry():
    rng = np.random.default_rng(1)
    d = ClubDistribution("7i", 150, 7, 12, p_mishit=0.3)
    s = sample_shots(d, 5000, rng)
    assert 0.25 < s.mishit.mean() < 0.35
    assert s.carry[s.mishit].mean() < 0.9 * 150


def test_landing_points_right_is_positive_y():
    s = sample_shots(ClubDistribution("D", 200, 0.1, 0.1, lateral_bias=10, p_mishit=0), 5, np.random.default_rng(2))
    wx, wy = landing_points(s, (0, 0), (1, 0))
    assert np.all(wy > 5)  # +lateral = right = +y when heading along +x


def test_partial_swing_scales_dispersion():
    d = ClubDistribution("PW", 120, 6, 10)
    p = d.partial(60)
    assert p.carry_mean == 60
    assert p.lateral_sigma < d.lateral_sigma


# ---------------------------------------------------------------------------
# Learning
# ---------------------------------------------------------------------------
def _shot(hole_result_id, seq, code, stype, lie_s, d_s, lie_e, d_e, lat=None, holed=False, tag=None, pen=0, intended=None):
    return NS(hole_result_id=hole_result_id, sequence=seq, club_id=None, club_code=code, shot_type=stype, lie_start=lie_s,
              start_distance_yards=d_s, lie_end=lie_e, end_distance_yards=d_e, carry_yards=None, intended_carry_yards=intended,
              lateral_miss_yards=lat, distance_miss_yards=None, outcome_tag=tag, penalty_strokes=pen, holed=holed)


def _player(h=14.0):
    return NS(id=1, name="T", handicap_index=h, target_score=79, dominant_miss=None)


def _clubs():
    return [NS(id=1, code="D", name="Driver", category="driver", active=True, stock_carry=None),
            NS(id=2, code="7i", name="7 Iron", category="iron", active=True, stock_carry=None),
            NS(id=3, code="P", name="Putter", category="putter", active=True, stock_carry=None)]


def test_profile_with_no_rounds_is_prior_only():
    p = ProfileBuilder(_player(), _clubs(), []).build()
    assert p["readiness"]["level"] == "cold"
    assert p["clubs"]["D"]["source"] == "prior"
    assert p["clubs"]["D"]["carry_mean"] == pytest.approx(default_club_prior("D", 14)["carry_mean"], abs=0.2)
    assert p["errors"] == []


def test_learning_moves_toward_observed_carry_with_shrinkage():
    rng = np.random.default_rng(3)
    rounds = []
    for r in range(6):
        holes = []
        for n in range(1, 19):
            hid = r * 18 + n
            carry = rng.normal(255, 10)
            lat = rng.normal(8, 20)
            shots = [
                _shot(hid, 1, "D", "tee", "tee", 400, "fairway" if abs(lat) < 18 else "rough", 400 - carry, lat=lat),
                _shot(hid, 2, "7i", "full", "fairway", 145, "green", 8, lat=rng.normal(0, 10)),
                _shot(hid, 3, "P", "putt", "green", 8, "green", 1),
                _shot(hid, 4, "P", "putt", "green", 1, "green", 0, holed=True),
            ]
            holes.append(NS(par=4, score=4, putts=2, fairway_hit=abs(lat) < 18, gir=True, penalties=0, tee_miss=None, shots=shots))
        rounds.append(NS(played_on=date(2026, 6, 1 + r), total_score=84, holes=holes))
    p = ProfileBuilder(_player(), _clubs(), rounds).build()
    d = p["clubs"]["D"]
    prior = default_club_prior("D", 14)["carry_mean"]
    assert d["n_samples"] == 108
    assert d["carry_mean"] > prior + 10          # moved well past the ~230 prior
    assert d["carry_mean"] < 257                  # ...but shrinkage keeps it just under the sample mean
    assert 5 < d["lateral_bias"] < 9              # right miss detected
    assert d["source"] == "observed"
    assert p["tendencies"]["dominant_miss"] == "right"
    assert p["readiness"]["level"] in ("warming", "ready")
    # Personal expected-strokes table blends toward what actually happened (pars from 400).
    assert personal_expected_strokes(p, "tee", 400) < expected_strokes("tee", 400, 14)


def test_partial_swings_do_not_pollute_carry():
    rounds = []
    holes = []
    for n in range(1, 19):
        shots = [_shot(n, 1, "7i", "full", "fairway", 60, "green", 3, intended=60), _shot(n, 2, "P", "putt", "green", 3, "green", 0, holed=True)]
        holes.append(NS(par=3, score=2, putts=1, fairway_hit=None, gir=True, penalties=0, tee_miss=None, shots=shots))
    rounds.append(NS(played_on=date(2026, 6, 1), total_score=36, holes=holes))
    p = ProfileBuilder(_player(), _clubs(), rounds).build()
    prior = default_club_prior("7i", 14)["carry_mean"]
    assert p["clubs"]["7i"]["carry_mean"] == pytest.approx(prior, abs=0.5)


def test_readiness_gates_on_rounds():
    assert readiness_level(0.1) == "cold"
    assert readiness_level(0.5) == "warming"
    assert readiness_level(0.7) == "ready"
    assert readiness_level(0.9) == "dialed"


def test_errors_rank_penalties_and_three_putts():
    holes = []
    for n in range(1, 19):
        holes.append(NS(par=4, score=6, putts=3, fairway_hit=False, gir=False, penalties=1, tee_miss="right", shots=[]))
    rounds = [NS(played_on=date(2026, 6, 1), total_score=108, holes=holes)]
    p = ProfileBuilder(_player(), _clubs(), rounds).build()
    codes = [e["code"] for e in p["errors"]]
    assert "penalties" in codes and "three_putts" in codes and "blowups" in codes
    assert p["errors"][0]["strokes_per_round"] >= p["errors"][-1]["strokes_per_round"]


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------
@pytest.fixture
def engine():
    return StrategyEngine({"handicap": 12.0, "readiness": {"score": 0.3}, "clubs": {}}, n_samples=200, seed=3, risk_tolerance=0.35)


def test_plan_is_deterministic_and_well_formed(engine, par4):
    a = engine.plan_hole(par4)
    b = engine.plan_hole(par4)
    assert a["tee"]["club"] == b["tee"]["club"] and a["expected_strokes"] == b["expected_strokes"]
    dist = a["score_distribution"]
    assert sum(dist.values()) == pytest.approx(1.0, abs=0.002)
    assert 4.3 <= a["expected_strokes"] <= 5.3
    assert a["tee"]["aim"] and a["rationale"] and a["key_thought"]
    assert len(a["alternatives"]) >= 1
    assert a["map"]["yards"] == 420
    assert a["approach"] is not None and a["approach"]["from_yards"] > 100


def test_water_and_ob_push_driver_out_of_the_plan(engine, par4):
    plan = engine.plan_hole(par4)
    assert plan["tee"]["club"] != "D"
    d_alt = next((a for a in plan["alternatives"] if a["club"] == "D"), None)
    if d_alt:
        assert d_alt["landing_mix"].get("penalty", 0) + d_alt["landing_mix"].get("ob", 0) > plan["tee"]["trouble_probability"]


def test_open_hole_prefers_driver(engine):
    wide = HoleGeometry(number=9, par=4, yards=430, fairway_width_yards=50, rough_width_yards=30)
    plan = engine.plan_hole(wide)
    assert plan["tee"]["club"] == "D"


def test_par3_aims_at_green_and_reports_no_approach(engine):
    p3 = HoleGeometry(number=2, par=3, yards=165, fairway_start_yards=165,
                      features=[FeatureBox("water", "short", 120, 157, 0, 40, label="pond short")])
    plan = engine.plan_hole(p3)
    assert plan["approach"] is None
    assert plan["tee"]["target_yards"] == 165
    assert plan["tee"]["landing_mix"].get("green", 0) > 0.3


def test_par5_with_lake_right_of_green_lays_up(engine):
    p5 = HoleGeometry(number=3, par=5, yards=530, features=[
        FeatureBox("creek", "center", 262, 276, 0, 999, label="creek"),
        FeatureBox("water", "right", 430, 530, 18, 999, label="lake right"),
    ])
    plan = engine.plan_hole(p5)
    assert plan["layup"] is not None
    assert plan["tee"]["landing_mix"].get("penalty", 0) < 0.1  # stays out of the creek


def test_risk_tolerance_changes_lambda():
    safe = StrategyEngine({"handicap": 10, "clubs": {}}, risk_tolerance=0.0)
    bold = StrategyEngine({"handicap": 10, "clubs": {}}, risk_tolerance=1.0)
    assert safe.lam > bold.lam == 0.0


def test_course_plan_aggregates(engine, par4):
    p3 = HoleGeometry(number=2, par=3, yards=165, fairway_start_yards=165)
    course = engine.plan_course([par4, p3])
    assert course["par"] == 7
    assert course["expected_score"] > 7
    assert 0 <= course["p_break_target"] <= 1
    assert len(course["holes"]) == 2
    assert course["summary"]["headline"]


def test_wide_miss_on_par3_still_learns_full_carry():
    """A pin-high shot 30 yards right must not read as a 30-yard-short carry."""
    rounds = []
    holes = []
    for n in range(1, 19):
        # 210-yard par 3, 3-wood lands pin high but 30 yards right: end distance ~30.
        shots = [_shot(n, 1, "3w", "tee", "tee", 210, "rough", 30.0, lat=30.0, tag="right"),
                 _shot(n, 2, "P", "putt", "green", 3, "green", 0, holed=True)]
        holes.append(NS(par=3, score=3, putts=1, fairway_hit=None, gir=False, penalties=0, tee_miss="right", shots=shots))
    rounds.append(NS(played_on=date(2026, 6, 1), total_score=54, holes=holes))
    clubs = _clubs() + [NS(id=4, code="3w", name="3 Wood", category="wood", active=True, stock_carry=None)]
    p = ProfileBuilder(_player(), clubs, rounds).build()
    d = p["clubs"]["3w"]
    assert d["n_samples"] == 18
    assert d["carry_mean"] > 205          # ~210 observed, blended with a ~215 prior
    assert d["lateral_bias"] > 15


def test_tiny_hole_still_gets_a_plan(engine):
    """No club passes the normal filters on a 120-yard par 4; the fallback must still plan it."""
    tiny = HoleGeometry(number=7, par=4, yards=120, fairway_start_yards=40)
    plan = engine.plan_hole(tiny)
    assert plan["tee"]["club"] in engine.clubs
    assert sum(plan["score_distribution"].values()) == pytest.approx(1.0, abs=0.002)


def test_drivable_par4_credits_gir_off_the_tee(engine):
    short = HoleGeometry(number=8, par=4, yards=250, fairway_width_yards=45, rough_width_yards=30, green_width_yards=35, green_depth_yards=35)
    plan = engine.plan_hole(short)
    # With driver carrying ~242 the tee shot reaches the green often; GIR must count those.
    assert plan["tee"]["landing_mix"].get("green", 0) > 0.1
    assert plan["approach"] is None or plan["approach"]["gir_probability"] > 0.1


def test_uphill_hole_plays_longer(engine):
    flat = HoleGeometry(number=9, par=4, yards=400, fairway_width_yards=45, rough_width_yards=30)
    uphill = HoleGeometry(number=9, par=4, yards=400, fairway_width_yards=45, rough_width_yards=30, elevation_change_ft=60)
    assert engine.plan_hole(uphill)["expected_strokes"] > engine.plan_hole(flat)["expected_strokes"]


def test_course_expected_score_matches_hole_sum(engine, par4):
    p3 = HoleGeometry(number=2, par=3, yards=165, fairway_start_yards=165)
    course = engine.plan_course([par4, p3])
    assert course["expected_score"] == pytest.approx(sum(h["expected_strokes"] for h in course["holes"]), abs=0.05)


def test_fractional_penalty_does_not_break_buckets(engine):
    g = HoleGeometry(number=3, par=4, yards=400, features=[FeatureBox("water", "left", 200, 300, offset_yards=10, penalty_strokes=1.0, label="pond")])
    plan = engine.plan_hole(g)
    assert sum(plan["score_distribution"].values()) == pytest.approx(1.0, abs=0.002)
