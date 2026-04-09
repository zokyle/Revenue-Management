"""Demand forecasting engine using additive decomposition with pickup adjustment."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.inventory import Reservation, ReservationStatus, RoomInventory
from app.models.property import Hotel, RoomType


class DemandForecaster:
    """Generates demand forecasts using additive decomposition and pickup curves.

    Algorithm overview:
        1. Compute baseline demand from rolling DOW averages (52-week window).
        2. Apply a monthly seasonality index.
        3. Apply a day-of-week demand multiplier.
        4. Adjust for current on-the-books pickup vs. historical pickup curves.
        5. Scale up if historical occupancy hit 100% (unconstrained demand).
    """

    _LOOKBACK_WEEKS: int = 52
    _MIN_WEEKS_FOR_DECOMPOSITION: int = 4
    _UNCONSTRAINED_SCALE: float = 1.1
    _CONFIDENCE_BAND: float = 0.15

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_forecast(
        self,
        db: Session,
        hotel_id: int,
        room_type_id: int,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        """Return a list of forecast dicts for each date in [start_date, end_date].

        Each dict contains:
            forecast_date, predicted_demand, predicted_occupancy,
            confidence_lower, confidence_upper, method
        """
        room_type: RoomType | None = (
            db.query(RoomType)
            .filter(RoomType.id == room_type_id, RoomType.hotel_id == hotel_id)
            .first()
        )
        if room_type is None:
            return []

        physical_rooms: int = room_type.physical_rooms

        # --- gather historical data ----------------------------------
        lookback_start = start_date - timedelta(weeks=self._LOOKBACK_WEEKS)
        historical = self._query_historical_demand(
            db, hotel_id, room_type_id, lookback_start, start_date - timedelta(days=1)
        )

        weeks_of_data = len(historical) / 7.0 if historical else 0.0
        use_simple = weeks_of_data < self._MIN_WEEKS_FOR_DECOMPOSITION

        if use_simple:
            overall_avg = self._simple_average(historical, physical_rooms)
        else:
            dow_avgs = self._calculate_dow_averages(historical)
            seasonality = self._calculate_seasonality(historical)
            dow_factors = self._calculate_dow_factors(historical)
            pickup_map = self._build_historical_pickup(
                db, hotel_id, room_type_id, lookback_start, start_date - timedelta(days=1)
            )
            occupancy_dates = self._find_full_occupancy_dates(
                historical, physical_rooms
            )

        # --- build forecast for each target date --------------------
        forecasts: list[dict[str, Any]] = []
        current = start_date
        while current <= end_date:
            if use_simple:
                predicted = overall_avg
            else:
                predicted = self._compute_decomposed_demand(
                    db,
                    hotel_id,
                    room_type_id,
                    current,
                    start_date,
                    physical_rooms,
                    dow_avgs,
                    seasonality,
                    dow_factors,
                    pickup_map,
                    occupancy_dates,
                )

            predicted = max(predicted, 0.0)
            occupancy = min(predicted / physical_rooms, 1.0) if physical_rooms > 0 else 0.0

            forecasts.append(
                {
                    "forecast_date": current,
                    "predicted_demand": round(predicted, 2),
                    "predicted_occupancy": round(occupancy, 4),
                    "confidence_lower": round(max(predicted * (1.0 - self._CONFIDENCE_BAND), 0.0), 2),
                    "confidence_upper": round(predicted * (1.0 + self._CONFIDENCE_BAND), 2),
                    "method": "simple_average" if use_simple else "decomposition_pickup",
                }
            )
            current += timedelta(days=1)

        return forecasts

    # ------------------------------------------------------------------
    # Historical data helpers
    # ------------------------------------------------------------------

    def _query_historical_demand(
        self,
        db: Session,
        hotel_id: int,
        room_type_id: int,
        start: date,
        end: date,
    ) -> dict[date, int]:
        """Return {date: rooms_sold} from reservations in the period.

        We count reservations whose check_in falls in [start, end] and whose
        status is not 'cancelled'.
        """
        rows = (
            db.query(
                Reservation.check_in,
                func.count(Reservation.id).label("cnt"),
            )
            .filter(
                Reservation.hotel_id == hotel_id,
                Reservation.room_type_id == room_type_id,
                Reservation.check_in >= start,
                Reservation.check_in <= end,
                Reservation.status != ReservationStatus.CANCELLED,
            )
            .group_by(Reservation.check_in)
            .all()
        )
        return {row.check_in: row.cnt for row in rows}

    # ------------------------------------------------------------------
    # Simple fallback
    # ------------------------------------------------------------------

    @staticmethod
    def _simple_average(historical: dict[date, int], physical_rooms: int) -> float:
        if not historical:
            return 0.0
        return sum(historical.values()) / len(historical)

    # ------------------------------------------------------------------
    # Decomposition components
    # ------------------------------------------------------------------

    @staticmethod
    def _calculate_dow_averages(historical: dict[date, int]) -> dict[int, float]:
        """Rolling average of rooms sold per day-of-week (0=Mon .. 6=Sun)."""
        buckets: dict[int, list[int]] = defaultdict(list)
        for d, sold in historical.items():
            buckets[d.weekday()].append(sold)
        return {
            dow: (np.mean(vals).item() if vals else 0.0)
            for dow, vals in buckets.items()
        }

    @staticmethod
    def _calculate_seasonality(historical: dict[date, int]) -> dict[int, float]:
        """Monthly index = (avg demand for month) / (overall avg demand)."""
        if not historical:
            return {}
        monthly: dict[int, list[int]] = defaultdict(list)
        for d, sold in historical.items():
            monthly[d.month].append(sold)
        overall = np.mean(list(historical.values())).item()
        if overall == 0:
            return {m: 1.0 for m in monthly}
        return {
            m: (np.mean(vals).item() / overall) for m, vals in monthly.items()
        }

    @staticmethod
    def _calculate_dow_factors(historical: dict[date, int]) -> dict[int, float]:
        """Day-of-week demand multiplier = dow_avg / overall_avg."""
        if not historical:
            return {}
        overall = np.mean(list(historical.values())).item()
        if overall == 0:
            return {dow: 1.0 for dow in range(7)}
        buckets: dict[int, list[int]] = defaultdict(list)
        for d, sold in historical.items():
            buckets[d.weekday()].append(sold)
        return {
            dow: (np.mean(vals).item() / overall if vals else 1.0)
            for dow, vals in buckets.items()
        }

    # ------------------------------------------------------------------
    # Pickup curves
    # ------------------------------------------------------------------

    def _build_historical_pickup(
        self,
        db: Session,
        hotel_id: int,
        room_type_id: int,
        start: date,
        end: date,
    ) -> dict[int, float]:
        """Build average historical pickup curve.

        Returns {lead_days: avg_cumulative_bookings_ratio} where ratio is
        fraction of final demand booked at that lead time.
        """
        reservations = (
            db.query(Reservation.check_in, Reservation.booking_date)
            .filter(
                Reservation.hotel_id == hotel_id,
                Reservation.room_type_id == room_type_id,
                Reservation.check_in >= start,
                Reservation.check_in <= end,
                Reservation.status != ReservationStatus.CANCELLED,
            )
            .all()
        )
        if not reservations:
            return {}

        # Group by check_in date, then compute cumulative bookings at each
        # lead-day bucket.
        date_bookings: dict[date, list[int]] = defaultdict(list)
        for r in reservations:
            booking_dt = r.booking_date.date() if isinstance(r.booking_date, datetime) else r.booking_date
            check_in_d = r.check_in.date() if isinstance(r.check_in, datetime) else r.check_in
            lead = (check_in_d - booking_dt).days
            date_bookings[r.check_in].append(max(lead, 0))

        lead_ratios: dict[int, list[float]] = defaultdict(list)
        for ci_date, leads in date_bookings.items():
            total = len(leads)
            if total == 0:
                continue
            leads_sorted = sorted(leads, reverse=True)
            for idx, lead_day in enumerate(leads_sorted):
                ratio = (idx + 1) / total
                lead_ratios[lead_day].append(ratio)

        return {
            ld: float(np.mean(ratios))
            for ld, ratios in lead_ratios.items()
        }

    @staticmethod
    def _get_current_otb(
        db: Session,
        hotel_id: int,
        room_type_id: int,
        target_date: date,
    ) -> int:
        """Count current on-the-books (confirmed reservations) for target_date."""
        return (
            db.query(func.count(Reservation.id))
            .filter(
                Reservation.hotel_id == hotel_id,
                Reservation.room_type_id == room_type_id,
                Reservation.check_in == target_date,
                Reservation.status == ReservationStatus.CONFIRMED,
            )
            .scalar()
            or 0
        )

    def _apply_pickup_adjustment(
        self,
        baseline: float,
        otb: int,
        lead_days: int,
        pickup_map: dict[int, float],
    ) -> float:
        """Adjust baseline demand using pickup curve.

        If at the current lead time historical pickup says we should have X%
        of final demand booked, but we actually have Y rooms on the books,
        we can project final demand = otb / expected_ratio.  Blend with the
        baseline using equal weight.
        """
        if not pickup_map or lead_days < 0:
            return baseline

        # Find nearest lead-day in the map
        available_leads = sorted(pickup_map.keys())
        nearest = min(available_leads, key=lambda x: abs(x - lead_days))
        expected_ratio = pickup_map[nearest]

        if expected_ratio <= 0:
            return baseline

        pickup_projected = otb / expected_ratio
        # Blend: 50% baseline + 50% pickup projection
        return 0.5 * baseline + 0.5 * pickup_projected

    # ------------------------------------------------------------------
    # Unconstrained demand
    # ------------------------------------------------------------------

    @staticmethod
    def _find_full_occupancy_dates(
        historical: dict[date, int], physical_rooms: int
    ) -> set[int]:
        """Return set of day-of-week values where occupancy hit 100%."""
        full_dows: set[int] = set()
        for d, sold in historical.items():
            if physical_rooms > 0 and sold >= physical_rooms:
                full_dows.add(d.weekday())
        return full_dows

    # ------------------------------------------------------------------
    # Core computation
    # ------------------------------------------------------------------

    def _compute_decomposed_demand(
        self,
        db: Session,
        hotel_id: int,
        room_type_id: int,
        target_date: date,
        reference_date: date,
        physical_rooms: int,
        dow_avgs: dict[int, float],
        seasonality: dict[int, float],
        dow_factors: dict[int, float],
        pickup_map: dict[int, float],
        occupancy_full_dows: set[int],
    ) -> float:
        dow = target_date.weekday()
        month = target_date.month

        # Step 1: baseline from DOW rolling average
        baseline = dow_avgs.get(dow, 0.0)

        # Step 2: apply seasonality
        season_factor = seasonality.get(month, 1.0)
        baseline *= season_factor

        # Step 3: apply day-of-week factor (already embedded in dow_avgs,
        #         but seasonality may have shifted the scale, so renormalize)
        dow_factor = dow_factors.get(dow, 1.0)
        # The dow_avgs already capture DOW patterns; we use dow_factor only
        # for relative adjustment when combined with seasonality.
        # To avoid double-counting, we compute:
        #   adjusted = overall_avg * season_factor * dow_factor
        # Let's recompute from overall_avg directly:
        overall_avg = np.mean(list(dow_avgs.values())).item() if dow_avgs else 0.0
        baseline = overall_avg * season_factor * dow_factor

        # Step 4: pickup adjustment
        lead_days = (target_date - reference_date).days
        otb = self._get_current_otb(db, hotel_id, room_type_id, target_date)
        predicted = self._apply_pickup_adjustment(baseline, otb, lead_days, pickup_map)

        # Step 5: unconstrained demand estimation
        if dow in occupancy_full_dows:
            predicted *= self._UNCONSTRAINED_SCALE

        return predicted
