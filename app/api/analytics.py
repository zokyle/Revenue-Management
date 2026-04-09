from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.inventory import Reservation, ReservationStatus, RoomInventory
from app.models.property import Hotel, RoomType
from app.models.costs import CostProfile

router = APIRouter()


@router.get("/{hotel_id}/analytics/kpis")
def get_kpis(hotel_id: int, db: Session = Depends(get_db)):
    """Get key performance indicators for today, MTD, and YTD."""
    today = date.today()
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)

    hotel = db.query(Hotel).filter(Hotel.id == hotel_id).first()
    total_rooms = hotel.total_rooms if hotel else 0

    def _calc_metrics(start: date, end: date) -> dict:
        reservations = db.query(Reservation).filter(
            Reservation.hotel_id == hotel_id,
            Reservation.check_in <= end,
            Reservation.check_out > start,
            Reservation.status.in_([
                ReservationStatus.CONFIRMED,
                ReservationStatus.CHECKED_IN,
                ReservationStatus.CHECKED_OUT,
            ]),
        ).all()

        days = max((end - start).days, 1)
        total_room_nights = total_rooms * days
        room_nights_sold = 0
        total_revenue = 0.0

        for r in reservations:
            overlap_start = max(r.check_in, start)
            overlap_end = min(r.check_out, end)
            nights_in_period = (overlap_end - overlap_start).days
            if nights_in_period > 0:
                room_nights_sold += nights_in_period
                total_revenue += r.rate_amount * nights_in_period

        occupancy = room_nights_sold / total_room_nights if total_room_nights > 0 else 0
        adr = total_revenue / room_nights_sold if room_nights_sold > 0 else 0
        revpar = total_revenue / total_room_nights if total_room_nights > 0 else 0

        # EBITDA estimate
        cost_profile = db.query(CostProfile).filter(CostProfile.hotel_id == hotel_id).first()
        cpor = cost_profile.cpor if cost_profile else 45.0
        fixed_daily = cost_profile.fixed_daily_cost if cost_profile else 12000.0
        variable_pct = cost_profile.variable_cost_pct if cost_profile else 0.05

        variable_costs = room_nights_sold * cpor + total_revenue * variable_pct
        fixed_costs = fixed_daily * days
        ebitda = total_revenue - variable_costs - fixed_costs

        return {
            "revenue": round(total_revenue, 2),
            "room_nights_sold": room_nights_sold,
            "occupancy": round(occupancy * 100, 1),
            "adr": round(adr, 2),
            "revpar": round(revpar, 2),
            "ebitda": round(ebitda, 2),
        }

    return {
        "today": _calc_metrics(today, today + timedelta(days=1)),
        "mtd": _calc_metrics(month_start, today + timedelta(days=1)),
        "ytd": _calc_metrics(year_start, today + timedelta(days=1)),
        "total_rooms": total_rooms,
    }


@router.get("/{hotel_id}/analytics/revpar-trend")
def revpar_trend(
    hotel_id: int,
    days: int = Query(30),
    db: Session = Depends(get_db),
):
    """Daily RevPAR for the last N days."""
    hotel = db.query(Hotel).filter(Hotel.id == hotel_id).first()
    total_rooms = hotel.total_rooms if hotel else 0
    today = date.today()

    result = []
    for i in range(days, 0, -1):
        d = today - timedelta(days=i)
        reservations = db.query(Reservation).filter(
            Reservation.hotel_id == hotel_id,
            Reservation.check_in <= d,
            Reservation.check_out > d,
            Reservation.status.in_([
                ReservationStatus.CONFIRMED,
                ReservationStatus.CHECKED_IN,
                ReservationStatus.CHECKED_OUT,
            ]),
        ).all()

        revenue = sum(r.rate_amount for r in reservations)
        rooms_sold = len(reservations)
        revpar = revenue / total_rooms if total_rooms > 0 else 0
        adr = revenue / rooms_sold if rooms_sold > 0 else 0
        occupancy = rooms_sold / total_rooms if total_rooms > 0 else 0

        result.append({
            "date": d.isoformat(),
            "revpar": round(revpar, 2),
            "adr": round(adr, 2),
            "occupancy": round(occupancy * 100, 1),
            "rooms_sold": rooms_sold,
        })

    return result


@router.get("/{hotel_id}/analytics/segments")
def segment_mix(
    hotel_id: int,
    start_date: date = Query(None),
    end_date: date = Query(None),
    db: Session = Depends(get_db),
):
    """Revenue breakdown by market segment."""
    if not start_date:
        start_date = date.today().replace(day=1)
    if not end_date:
        end_date = date.today()

    from app.models.segments import MarketSegment

    segments = db.query(MarketSegment).filter(MarketSegment.hotel_id == hotel_id).all()
    result = []

    for seg in segments:
        reservations = db.query(Reservation).filter(
            Reservation.hotel_id == hotel_id,
            Reservation.segment_id == seg.id,
            Reservation.check_in <= end_date,
            Reservation.check_out >= start_date,
            Reservation.status.in_([
                ReservationStatus.CONFIRMED,
                ReservationStatus.CHECKED_IN,
                ReservationStatus.CHECKED_OUT,
            ]),
        ).all()

        revenue = sum(r.rate_amount * r.nights for r in reservations)
        room_nights = sum(r.nights for r in reservations)

        result.append({
            "segment": seg.name,
            "revenue": round(revenue, 2),
            "room_nights": room_nights,
            "adr": round(revenue / room_nights, 2) if room_nights > 0 else 0,
        })

    return sorted(result, key=lambda x: x["revenue"], reverse=True)
