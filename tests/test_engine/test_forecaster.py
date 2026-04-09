"""Tests for the demand forecasting engine."""

from datetime import date, timedelta

from app.engine.forecaster import DemandForecaster


def test_forecaster_returns_results(db_session, sample_hotel, sample_room_types, sample_reservations):
    forecaster = DemandForecaster()
    today = date.today()
    start = today + timedelta(days=1)
    end = today + timedelta(days=7)

    results = forecaster.generate_forecast(
        db_session, sample_hotel.id, sample_room_types[0].id, start, end
    )

    assert len(results) == 7
    for r in results:
        assert "forecast_date" in r
        assert "predicted_demand" in r
        assert "predicted_occupancy" in r
        assert r["predicted_demand"] >= 0
        assert 0 <= r["predicted_occupancy"] <= 1


def test_forecaster_empty_history(db_session, sample_hotel, sample_room_types):
    """With no historical data, forecaster should still return results (simple avg fallback)."""
    forecaster = DemandForecaster()
    today = date.today()
    start = today + timedelta(days=1)
    end = today + timedelta(days=3)

    results = forecaster.generate_forecast(
        db_session, sample_hotel.id, sample_room_types[0].id, start, end
    )

    assert len(results) == 3
    for r in results:
        assert r["predicted_demand"] == 0.0
        assert r["method"] == "simple_average"


def test_forecaster_confidence_bands(db_session, sample_hotel, sample_room_types, sample_reservations):
    forecaster = DemandForecaster()
    today = date.today()
    results = forecaster.generate_forecast(
        db_session, sample_hotel.id, sample_room_types[0].id,
        today + timedelta(days=1), today + timedelta(days=1)
    )

    assert len(results) == 1
    r = results[0]
    assert r["confidence_lower"] <= r["predicted_demand"]
    assert r["confidence_upper"] >= r["predicted_demand"]


def test_forecaster_invalid_room_type(db_session, sample_hotel):
    forecaster = DemandForecaster()
    results = forecaster.generate_forecast(
        db_session, sample_hotel.id, 9999, date.today(), date.today()
    )
    assert results == []
