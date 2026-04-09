"""Dynamic pricing engine that converts demand forecasts into rate recommendations."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.forecasts import PricingRecommendation, RecommendationStatus
from app.models.property import Hotel, RoomType
from app.models.rates import RatePlan
from app.models.segments import MarketSegment


class PricingEngine:
    """Produces rate recommendations by applying demand-driven multipliers to
    active rate plans and enforcing hotel-level pricing guardrails.

    For each (room_type, forecast_date) combination the engine:
        1. Computes a demand ratio (predicted demand / available rooms).
        2. Maps demand ratio to a price multiplier using hotel config thresholds.
        3. Applies the multiplier to each active RatePlan's base rate.
        4. Clamps the result between min_rate and max_rate.
        5. Generates per-segment variants with discount_pct_from_bar applied.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_recommendations(
        self,
        db: Session,
        hotel_id: int,
        forecasts: list[dict[str, Any]],
        room_type_id: int | None = None,
    ) -> list[PricingRecommendation]:
        """Generate pricing recommendations for a set of forecasts.

        Parameters
        ----------
        db : Session
            Active SQLAlchemy session.
        hotel_id : int
            Target hotel.
        forecasts : list[dict]
            Output of ``DemandForecaster.generate_forecast`` -- each dict must
            contain at least ``forecast_date``, ``predicted_demand``, and
            ``predicted_occupancy``.
        room_type_id : int | None
            If provided, limit recommendations to this room type. Otherwise
            the engine assumes each forecast dict optionally carries a
            ``room_type_id`` key; when absent, it iterates over all room types.

        Returns
        -------
        list[PricingRecommendation]
            Unsaved ORM instances ready to be added to the session.
        """
        hotel: Hotel | None = db.query(Hotel).filter(Hotel.id == hotel_id).first()
        if hotel is None:
            return []

        # Resolve room types
        if room_type_id is not None:
            room_types = (
                db.query(RoomType)
                .filter(RoomType.id == room_type_id, RoomType.hotel_id == hotel_id)
                .all()
            )
        else:
            room_types = (
                db.query(RoomType)
                .filter(RoomType.hotel_id == hotel_id)
                .all()
            )

        room_type_map: dict[int, RoomType] = {rt.id: rt for rt in room_types}

        # Pre-load market segments for the hotel
        segments: list[MarketSegment] = (
            db.query(MarketSegment)
            .filter(MarketSegment.hotel_id == hotel_id)
            .all()
        )

        now = datetime.utcnow()
        recommendations: list[PricingRecommendation] = []

        for forecast in forecasts:
            forecast_date: date = forecast["forecast_date"]
            predicted_demand: float = forecast["predicted_demand"]
            predicted_occupancy: float = forecast["predicted_occupancy"]

            # Determine applicable room type(s) for this forecast row
            fc_rt_id: int | None = forecast.get("room_type_id", room_type_id)
            target_rt_ids: list[int] = (
                [fc_rt_id] if fc_rt_id is not None else list(room_type_map.keys())
            )

            for rt_id in target_rt_ids:
                rt = room_type_map.get(rt_id)
                if rt is None:
                    continue

                total_rooms = rt.physical_rooms
                demand_ratio = (
                    predicted_demand / total_rooms if total_rooms > 0 else 0.0
                )

                multiplier = self._compute_multiplier(hotel, demand_ratio)

                # Fetch active rate plans for this room type
                rate_plans = self._get_active_rate_plans(
                    db, hotel_id, rt_id, forecast_date
                )

                for rp in rate_plans:
                    recommended = self._apply_multiplier(rp, multiplier)

                    # BAR (Best Available Rate) recommendation
                    recommendations.append(
                        self._build_recommendation(
                            hotel_id=hotel_id,
                            room_type_id=rt_id,
                            forecast_date=forecast_date,
                            segment_id=rp.segment_id,
                            recommended_rate=recommended,
                            current_rate=rp.base_rate,
                            expected_occupancy=predicted_occupancy,
                            physical_rooms=total_rooms,
                            generated_at=now,
                            multiplier=multiplier,
                        )
                    )

                    # Segment-level discounted variants
                    for seg in segments:
                        if seg.discount_pct_from_bar == 0.0:
                            continue
                        seg_rate = round(
                            recommended * (1.0 - seg.discount_pct_from_bar / 100.0), 2
                        )
                        seg_rate = max(rp.min_rate, min(rp.max_rate, seg_rate))
                        recommendations.append(
                            self._build_recommendation(
                                hotel_id=hotel_id,
                                room_type_id=rt_id,
                                forecast_date=forecast_date,
                                segment_id=seg.id,
                                recommended_rate=seg_rate,
                                current_rate=rp.base_rate,
                                expected_occupancy=predicted_occupancy,
                                physical_rooms=total_rooms,
                                generated_at=now,
                                multiplier=multiplier,
                            )
                        )

        return recommendations

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_multiplier(hotel: Hotel, demand_ratio: float) -> float:
        """Determine the price multiplier given a demand ratio and hotel config.

        High-demand zone:
            multiplier = 1 + aggressiveness * normalised_excess
        Low-demand zone:
            multiplier = 1 - (1 - rate_protection) * normalised_shortfall
        Normal zone:
            multiplier = 1.0
        """
        if demand_ratio >= hotel.high_demand_threshold:
            denom = 1.0 - hotel.high_demand_threshold
            if denom <= 0:
                return 1.0
            excess = (demand_ratio - hotel.high_demand_threshold) / denom
            return 1.0 + hotel.pricing_aggressiveness * excess
        elif demand_ratio <= hotel.low_demand_threshold:
            if hotel.low_demand_threshold <= 0:
                return 1.0
            shortfall = (
                (hotel.low_demand_threshold - demand_ratio)
                / hotel.low_demand_threshold
            )
            return 1.0 - (1.0 - hotel.rate_protection) * shortfall
        else:
            return 1.0

    @staticmethod
    def _apply_multiplier(rate_plan: RatePlan, multiplier: float) -> float:
        """Apply multiplier to base rate and clamp within plan bounds."""
        recommended = rate_plan.base_rate * multiplier
        return round(
            max(rate_plan.min_rate, min(rate_plan.max_rate, recommended)), 2
        )

    @staticmethod
    def _get_active_rate_plans(
        db: Session,
        hotel_id: int,
        room_type_id: int,
        target_date: date,
    ) -> list[RatePlan]:
        """Return active rate plans valid for the given date."""
        return (
            db.query(RatePlan)
            .filter(
                RatePlan.hotel_id == hotel_id,
                RatePlan.room_type_id == room_type_id,
                RatePlan.is_active.is_(True),
                # valid_from / valid_to can be NULL (always valid)
                and_(
                    (RatePlan.valid_from.is_(None)) | (RatePlan.valid_from <= target_date),
                    (RatePlan.valid_to.is_(None)) | (RatePlan.valid_to >= target_date),
                ),
            )
            .all()
        )

    @staticmethod
    def _build_recommendation(
        *,
        hotel_id: int,
        room_type_id: int,
        forecast_date: date,
        segment_id: int | None,
        recommended_rate: float,
        current_rate: float,
        expected_occupancy: float,
        physical_rooms: int,
        generated_at: datetime,
        multiplier: float,
    ) -> PricingRecommendation:
        revpar = recommended_rate * expected_occupancy
        direction = "increase" if multiplier > 1.0 else ("decrease" if multiplier < 1.0 else "hold")
        reason = (
            f"Demand-based {direction}: multiplier {multiplier:.3f} "
            f"applied (expected occ {expected_occupancy:.1%})"
        )

        return PricingRecommendation(
            hotel_id=hotel_id,
            room_type_id=room_type_id,
            date=forecast_date,
            segment_id=segment_id,
            recommended_rate=recommended_rate,
            current_rate=current_rate,
            expected_occupancy=round(expected_occupancy, 4),
            expected_revpar=round(revpar, 2),
            status=RecommendationStatus.PENDING,
            reason_text=reason,
            generated_at=generated_at,
        )
