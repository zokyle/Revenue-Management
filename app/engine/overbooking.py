"""Overbooking model that balances spoilage risk against walk cost."""

from __future__ import annotations

import math
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.inventory import Reservation, ReservationStatus
from app.models.property import RoomType


class OverbookingModel:
    """Calculates the optimal number of rooms to overbook.

    The model uses a newsvendor-style cost trade-off:
        - **spoilage cost**: revenue lost when a room goes unsold due to a
          cancellation or no-show (= average rate).
        - **walk cost**: cost of relocating a guest when all rooms are occupied
          (= 2.5 * average rate, covering compensation and goodwill).

    Optimal overbook percentage:
        ``cancellation_rate * spoilage_cost / (walk_cost + spoilage_cost)``
    """

    _WALK_COST_MULTIPLIER: float = 2.5
    _LOOKBACK_DAYS: int = 90

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def calculate_optimal_overbook(
        self,
        db: Session,
        hotel_id: int,
        room_type_id: int,
        target_date: date,
    ) -> dict[str, object]:
        """Return the recommended overbooking level for a room type on a date.

        Returns
        -------
        dict with keys:
            physical_rooms, cancellation_rate, no_show_rate, combined_rate,
            average_rate, walk_cost, spoilage_cost, optimal_overbook_pct,
            optimal_overbook_rooms, lookback_days, total_reservations
        """
        room_type: RoomType | None = (
            db.query(RoomType)
            .filter(RoomType.id == room_type_id, RoomType.hotel_id == hotel_id)
            .first()
        )
        if room_type is None:
            return {"error": "Room type not found"}

        physical_rooms: int = room_type.physical_rooms

        lookback_start = target_date - timedelta(days=self._LOOKBACK_DAYS)
        stats = self._query_reservation_stats(
            db, hotel_id, room_type_id, lookback_start, target_date
        )

        total: int = stats["total"]
        cancelled: int = stats["cancelled"]
        no_show: int = stats["no_show"]
        avg_rate: float = stats["average_rate"]

        # --- rates ---------------------------------------------------
        cancellation_rate = (cancelled + no_show) / total if total > 0 else 0.0
        no_show_only_rate = no_show / total if total > 0 else 0.0
        cancelled_only_rate = cancelled / total if total > 0 else 0.0

        # --- costs ---------------------------------------------------
        spoilage_cost = avg_rate if avg_rate > 0 else 0.0
        walk_cost = self._WALK_COST_MULTIPLIER * avg_rate if avg_rate > 0 else 0.0

        # --- optimal overbook ----------------------------------------
        cost_sum = walk_cost + spoilage_cost
        if cost_sum > 0 and cancellation_rate > 0:
            optimal_pct = cancellation_rate * spoilage_cost / cost_sum
        else:
            optimal_pct = 0.0

        optimal_rooms = math.ceil(physical_rooms * optimal_pct)

        return {
            "physical_rooms": physical_rooms,
            "cancellation_rate": round(cancelled_only_rate, 4),
            "no_show_rate": round(no_show_only_rate, 4),
            "combined_rate": round(cancellation_rate, 4),
            "average_rate": round(avg_rate, 2),
            "walk_cost": round(walk_cost, 2),
            "spoilage_cost": round(spoilage_cost, 2),
            "optimal_overbook_pct": round(optimal_pct, 4),
            "optimal_overbook_rooms": optimal_rooms,
            "lookback_days": self._LOOKBACK_DAYS,
            "total_reservations": total,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _query_reservation_stats(
        db: Session,
        hotel_id: int,
        room_type_id: int,
        start: date,
        end: date,
    ) -> dict[str, object]:
        """Aggregate reservation statistics over a lookback window.

        Returns dict with total, cancelled, no_show counts and average_rate.
        """
        base_query = db.query(Reservation).filter(
            Reservation.hotel_id == hotel_id,
            Reservation.room_type_id == room_type_id,
            Reservation.check_in >= start,
            Reservation.check_in <= end,
        )

        total: int = base_query.count()

        cancelled: int = (
            base_query.filter(Reservation.status == ReservationStatus.CANCELLED).count()
        )

        no_show: int = (
            base_query.filter(Reservation.status == ReservationStatus.NO_SHOW).count()
        )

        avg_rate_row = (
            db.query(func.avg(Reservation.rate_amount))
            .filter(
                Reservation.hotel_id == hotel_id,
                Reservation.room_type_id == room_type_id,
                Reservation.check_in >= start,
                Reservation.check_in <= end,
                Reservation.status.notin_([
                    ReservationStatus.CANCELLED,
                ]),
            )
            .scalar()
        )
        average_rate: float = float(avg_rate_row) if avg_rate_row is not None else 0.0

        return {
            "total": total,
            "cancelled": cancelled,
            "no_show": no_show,
            "average_rate": average_rate,
        }
