"""Tests for the EBITDA optimizer."""

from datetime import date

from app.engine.optimizer import EBITDAOptimizer
from app.models.costs import CostProfile


def test_optimizer_finds_better_rate(db_session, sample_hotel, sample_room_types, sample_rate_plans, sample_cost_profile):
    optimizer = EBITDAOptimizer()
    forecast = {"predicted_demand": 40.0}  # 40 rooms expected for 50-room type

    result = optimizer.optimize(
        db=db_session,
        hotel_id=sample_hotel.id,
        room_type_id=sample_room_types[0].id,
        target_date=date.today(),
        forecast=forecast,
        cost_profile=sample_cost_profile,
    )

    assert "error" not in result
    assert "optimal_scenario" in result
    assert "current_scenario" in result
    assert result["optimal_scenario"]["ebitda"] >= result["current_scenario"]["ebitda"]


def test_optimizer_respects_rate_bounds(db_session, sample_hotel, sample_room_types, sample_rate_plans, sample_cost_profile):
    optimizer = EBITDAOptimizer()
    forecast = {"predicted_demand": 45.0}

    result = optimizer.optimize(
        db=db_session,
        hotel_id=sample_hotel.id,
        room_type_id=sample_room_types[0].id,
        target_date=date.today(),
        forecast=forecast,
        cost_profile=sample_cost_profile,
    )

    assert "error" not in result
    optimal_rate = result["optimal_scenario"]["rate"]
    # Rate should be within bounds (min=139, max=329 from fixture)
    assert 139.0 <= optimal_rate <= 329.0


def test_displacement_accept():
    """Group should be accepted when its value exceeds displaced transient."""
    optimizer = EBITDAOptimizer()
    result = optimizer.displacement_analysis(
        group_rooms=20,
        group_rate=200.0,
        group_nights=3,
        expected_transient_rate=180.0,  # Transient rate is lower
        expected_transient_occupancy=0.6,
        available_rooms=50,
        cpor=45.0,
    )
    assert result["accept"] is True
    assert result["net_value"] > 0


def test_displacement_reject():
    """Group should be rejected when transient value is higher."""
    optimizer = EBITDAOptimizer()
    result = optimizer.displacement_analysis(
        group_rooms=20,
        group_rate=120.0,  # Low group rate
        group_nights=2,
        expected_transient_rate=250.0,  # High transient rate
        expected_transient_occupancy=0.9,  # Hotel is busy
        available_rooms=50,
        cpor=45.0,
    )
    assert result["accept"] is False
    assert result["net_value"] < 0


def test_optimizer_no_cost_profile(db_session, sample_hotel, sample_room_types, sample_rate_plans):
    """Without a cost profile, optimizer should return error."""
    optimizer = EBITDAOptimizer()
    result = optimizer.optimize(
        db=db_session,
        hotel_id=sample_hotel.id,
        room_type_id=sample_room_types[0].id,
        target_date=date.today(),
        forecast={"predicted_demand": 30.0},
    )
    assert "error" in result
