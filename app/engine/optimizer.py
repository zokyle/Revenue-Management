"""EBITDA optimiser -- finds the rate that maximises profit contribution
and provides displacement analysis for group business decisions."""

from __future__ import annotations

from datetime import date
from typing import Any

from scipy.optimize import minimize_scalar
from sqlalchemy.orm import Session

from app.models.costs import CostProfile
from app.models.rates import RatePlan


class EBITDAOptimizer:
    """Revenue-to-profit optimiser.

    Uses a constant-elasticity demand function and ``scipy.optimize`` to find
    the rate that maximises EBITDA contribution for a single room type on a
    single date.
    """

    _DEFAULT_ELASTICITY: float = 1.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def optimize(
        self,
        db: Session,
        hotel_id: int,
        room_type_id: int,
        target_date: date,
        forecast: dict[str, Any],
        cost_profile: CostProfile | None = None,
        elasticity: float | None = None,
    ) -> dict[str, Any]:
        """Find the rate that maximises EBITDA contribution.

        Parameters
        ----------
        db : Session
            Active SQLAlchemy session.
        hotel_id : int
            Target hotel.
        room_type_id : int
            Target room type.
        target_date : date
            The date being optimised.
        forecast : dict
            Must contain ``predicted_demand`` (unconstrained).
        cost_profile : CostProfile | None
            Explicit cost profile.  If *None* the most recent active profile
            for the hotel is queried.
        elasticity : float | None
            Price elasticity of demand.  Defaults to 1.0 (unit elastic).

        Returns
        -------
        dict with keys:
            current_scenario, optimal_scenario, improvement_pct
        """
        if cost_profile is None:
            cost_profile = self._get_cost_profile(db, hotel_id, target_date)
        if cost_profile is None:
            return {"error": "No cost profile found for hotel"}

        rate_plan = self._get_primary_rate_plan(db, hotel_id, room_type_id, target_date)
        if rate_plan is None:
            return {"error": "No active rate plan found for room type"}

        elas = elasticity if elasticity is not None else self._DEFAULT_ELASTICITY
        unconstrained_demand: float = forecast["predicted_demand"]
        base_rate: float = rate_plan.base_rate
        min_rate: float = rate_plan.min_rate
        max_rate: float = rate_plan.max_rate
        cpor: float = cost_profile.cpor
        fixed_daily: float = cost_profile.fixed_daily_cost
        variable_pct: float = cost_profile.variable_cost_pct

        # Look up total rooms for the room type
        from app.models.property import RoomType

        room_type = (
            db.query(RoomType)
            .filter(RoomType.id == room_type_id)
            .first()
        )
        total_rooms: int = room_type.physical_rooms if room_type else 0

        # --- demand function -----------------------------------------
        def demand_at_rate(rate: float) -> float:
            """D(rate) = unconstrained_demand * (base_rate / rate) ^ elasticity."""
            if rate <= 0 or base_rate <= 0:
                return 0.0
            return unconstrained_demand * (base_rate / rate) ** elas

        # --- EBITDA contribution function ----------------------------
        def ebitda(rate: float) -> float:
            d = demand_at_rate(rate)
            # Cap demand at physical room count
            d = min(d, total_rooms) if total_rooms > 0 else d
            revenue = d * rate
            variable_cost = revenue * (variable_pct / 100.0)
            room_cost = d * cpor
            fixed_cost = fixed_daily * total_rooms
            return revenue - variable_cost - room_cost - fixed_cost

        # --- current scenario ----------------------------------------
        current_demand = min(demand_at_rate(base_rate), total_rooms) if total_rooms > 0 else demand_at_rate(base_rate)
        current_ebitda = ebitda(base_rate)

        # --- optimise ------------------------------------------------
        # Negate because minimize_scalar minimises
        result = minimize_scalar(
            lambda r: -ebitda(r),
            bounds=(min_rate, max_rate),
            method="bounded",
        )

        optimal_rate: float = round(result.x, 2)
        optimal_demand = min(demand_at_rate(optimal_rate), total_rooms) if total_rooms > 0 else demand_at_rate(optimal_rate)
        optimal_ebitda = ebitda(optimal_rate)

        improvement_pct: float = 0.0
        if current_ebitda != 0:
            improvement_pct = round(
                (optimal_ebitda - current_ebitda) / abs(current_ebitda) * 100.0, 2
            )

        return {
            "target_date": target_date,
            "room_type_id": room_type_id,
            "current_scenario": {
                "rate": base_rate,
                "demand": round(current_demand, 2),
                "ebitda": round(current_ebitda, 2),
            },
            "optimal_scenario": {
                "rate": optimal_rate,
                "demand": round(optimal_demand, 2),
                "ebitda": round(optimal_ebitda, 2),
            },
            "improvement_pct": improvement_pct,
            "elasticity": elas,
        }

    # ------------------------------------------------------------------
    # Displacement analysis for group business
    # ------------------------------------------------------------------

    @staticmethod
    def displacement_analysis(
        group_rooms: int,
        group_rate: float,
        group_nights: int,
        expected_transient_rate: float,
        expected_transient_occupancy: float,
        available_rooms: int,
        cpor: float,
    ) -> dict[str, Any]:
        """Compare group block value against displaced transient revenue.

        Parameters
        ----------
        group_rooms : int
            Number of rooms the group requests per night.
        group_rate : float
            Negotiated group rate per room per night.
        group_nights : int
            Length of stay (nights).
        expected_transient_rate : float
            Expected average transient rate if rooms were sold individually.
        expected_transient_occupancy : float
            Expected transient occupancy (0-1) for those rooms if not blocked.
        available_rooms : int
            Total rooms available (before the group block).
        cpor : float
            Cost per occupied room.

        Returns
        -------
        dict with group_value, displaced_transient_value, net_value, accept
        """
        # Group value
        group_revenue = group_rooms * group_rate * group_nights
        group_cost = group_rooms * cpor * group_nights
        group_value = group_revenue - group_cost

        # Displaced transient value
        displaced_rooms_per_night = min(group_rooms, available_rooms)
        transient_rooms_sold = displaced_rooms_per_night * expected_transient_occupancy
        transient_revenue = transient_rooms_sold * expected_transient_rate * group_nights
        transient_cost = transient_rooms_sold * cpor * group_nights
        displaced_transient_value = transient_revenue - transient_cost

        net_value = group_value - displaced_transient_value
        accept = net_value >= 0

        return {
            "group_value": round(group_value, 2),
            "displaced_transient_value": round(displaced_transient_value, 2),
            "net_value": round(net_value, 2),
            "accept": accept,
            "group_rooms": group_rooms,
            "group_nights": group_nights,
            "group_rate": group_rate,
            "expected_transient_rate": expected_transient_rate,
            "expected_transient_occupancy": expected_transient_occupancy,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_cost_profile(
        db: Session, hotel_id: int, target_date: date
    ) -> CostProfile | None:
        """Return the most applicable cost profile for the hotel and date."""
        profile = (
            db.query(CostProfile)
            .filter(
                CostProfile.hotel_id == hotel_id,
                (CostProfile.effective_from.is_(None)) | (CostProfile.effective_from <= target_date),
                (CostProfile.effective_to.is_(None)) | (CostProfile.effective_to >= target_date),
            )
            .order_by(CostProfile.effective_from.desc().nullslast())
            .first()
        )
        return profile

    @staticmethod
    def _get_primary_rate_plan(
        db: Session, hotel_id: int, room_type_id: int, target_date: date
    ) -> RatePlan | None:
        """Return the first active rate plan for the room type."""
        return (
            db.query(RatePlan)
            .filter(
                RatePlan.hotel_id == hotel_id,
                RatePlan.room_type_id == room_type_id,
                RatePlan.is_active.is_(True),
                (RatePlan.valid_from.is_(None)) | (RatePlan.valid_from <= target_date),
                (RatePlan.valid_to.is_(None)) | (RatePlan.valid_to >= target_date),
            )
            .first()
        )
