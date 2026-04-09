from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.inventory import RoomInventory, Reservation
from app.schemas.inventory import RoomInventoryResponse, RoomInventoryUpdate, ReservationResponse

router = APIRouter()


@router.get("/{hotel_id}/inventory", response_model=list[RoomInventoryResponse])
def get_inventory(
    hotel_id: int,
    start_date: date = Query(...),
    end_date: date = Query(...),
    room_type_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(RoomInventory).filter(
        RoomInventory.hotel_id == hotel_id,
        RoomInventory.date >= start_date,
        RoomInventory.date <= end_date,
    )
    if room_type_id:
        query = query.filter(RoomInventory.room_type_id == room_type_id)
    return query.order_by(RoomInventory.date).all()


@router.put("/{hotel_id}/inventory/{inv_date}", response_model=RoomInventoryResponse)
def update_inventory(
    hotel_id: int,
    inv_date: date,
    data: RoomInventoryUpdate,
    room_type_id: int = Query(...),
    db: Session = Depends(get_db),
):
    inv = db.query(RoomInventory).filter(
        RoomInventory.hotel_id == hotel_id,
        RoomInventory.room_type_id == room_type_id,
        RoomInventory.date == inv_date,
    ).first()
    if not inv:
        raise HTTPException(404, "Inventory record not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(inv, field, value)
    db.commit()
    db.refresh(inv)
    return inv


@router.get("/{hotel_id}/reservations", response_model=list[ReservationResponse])
def list_reservations(
    hotel_id: int,
    start_date: date = Query(...),
    end_date: date = Query(...),
    status: str | None = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(Reservation).filter(
        Reservation.hotel_id == hotel_id,
        Reservation.check_in <= end_date,
        Reservation.check_out >= start_date,
    )
    if status:
        query = query.filter(Reservation.status == status)
    return query.order_by(Reservation.check_in).all()
