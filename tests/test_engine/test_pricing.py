"""Tests for the dynamic pricing engine."""

from app.engine.pricing import PricingEngine
from app.models.property import Hotel


def test_multiplier_high_demand():
    """When demand exceeds high threshold, multiplier should be > 1."""
    hotel = Hotel(
        id=1, name="T", total_rooms=100,
        pricing_aggressiveness=0.5,
        rate_protection=0.7,
        high_demand_threshold=0.85,
        low_demand_threshold=0.40,
    )
    engine = PricingEngine()
    # demand_ratio = 0.95 (above 0.85)
    mult = engine._compute_multiplier(hotel, 0.95)
    assert mult > 1.0


def test_multiplier_low_demand():
    """When demand is below low threshold, multiplier should be < 1 but protected."""
    hotel = Hotel(
        id=1, name="T", total_rooms=100,
        pricing_aggressiveness=0.5,
        rate_protection=0.7,
        high_demand_threshold=0.85,
        low_demand_threshold=0.40,
    )
    engine = PricingEngine()
    mult = engine._compute_multiplier(hotel, 0.20)
    assert mult < 1.0
    # Rate protection of 0.7 means rates don't drop too much
    assert mult > 0.7


def test_multiplier_neutral_zone():
    """When demand is between thresholds, multiplier should be 1.0."""
    hotel = Hotel(
        id=1, name="T", total_rooms=100,
        pricing_aggressiveness=0.5,
        rate_protection=0.7,
        high_demand_threshold=0.85,
        low_demand_threshold=0.40,
    )
    engine = PricingEngine()
    mult = engine._compute_multiplier(hotel, 0.60)
    assert mult == 1.0


def test_rate_protection_prevents_deep_discount():
    """High rate_protection should prevent aggressive discounting."""
    hotel = Hotel(
        id=1, name="T", total_rooms=100,
        pricing_aggressiveness=0.5,
        rate_protection=0.95,  # Very high protection
        high_demand_threshold=0.85,
        low_demand_threshold=0.40,
    )
    engine = PricingEngine()
    # Even at 0% demand, max discount should be (1 - 0.95) = 5%
    mult = engine._compute_multiplier(hotel, 0.0)
    assert mult >= 0.95


def test_aggressiveness_drives_rate_increase():
    """Higher aggressiveness should yield higher multiplier at same demand."""
    engine = PricingEngine()

    conservative = Hotel(
        id=1, name="T", total_rooms=100,
        pricing_aggressiveness=0.2,
        rate_protection=0.7,
        high_demand_threshold=0.85,
        low_demand_threshold=0.40,
    )
    aggressive = Hotel(
        id=2, name="T", total_rooms=100,
        pricing_aggressiveness=0.9,
        rate_protection=0.7,
        high_demand_threshold=0.85,
        low_demand_threshold=0.40,
    )

    mult_c = engine._compute_multiplier(conservative, 0.95)
    mult_a = engine._compute_multiplier(aggressive, 0.95)
    assert mult_a > mult_c
