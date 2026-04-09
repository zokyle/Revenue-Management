from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.property import Hotel, RoomType
from app.schemas.property import (
    HotelCreate, HotelUpdate, HotelResponse, HotelListResponse,
    RoomTypeCreate, RoomTypeResponse,
)

router = APIRouter()


@router.get("", response_model=list[HotelListResponse])
def list_hotels(db: Session = Depends(get_db)):
    return db.query(Hotel).all()


@router.post("", response_model=HotelResponse, status_code=201)
def create_hotel(data: HotelCreate, db: Session = Depends(get_db)):
    hotel = Hotel(**data.model_dump())
    db.add(hotel)
    db.commit()
    db.refresh(hotel)
    return hotel


@router.get("/{hotel_id}", response_model=HotelResponse)
def get_hotel(hotel_id: int, db: Session = Depends(get_db)):
    hotel = db.query(Hotel).filter(Hotel.id == hotel_id).first()
    if not hotel:
        raise HTTPException(404, "Hotel not found")
    return hotel


@router.put("/{hotel_id}", response_model=HotelResponse)
def update_hotel(hotel_id: int, data: HotelUpdate, db: Session = Depends(get_db)):
    hotel = db.query(Hotel).filter(Hotel.id == hotel_id).first()
    if not hotel:
        raise HTTPException(404, "Hotel not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(hotel, field, value)
    db.commit()
    db.refresh(hotel)
    return hotel


@router.post("/{hotel_id}/room-types", response_model=RoomTypeResponse, status_code=201)
def create_room_type(hotel_id: int, data: RoomTypeCreate, db: Session = Depends(get_db)):
    hotel = db.query(Hotel).filter(Hotel.id == hotel_id).first()
    if not hotel:
        raise HTTPException(404, "Hotel not found")
    room_type = RoomType(hotel_id=hotel_id, **data.model_dump())
    db.add(room_type)
    db.commit()
    db.refresh(room_type)
    return room_type


@router.get("/{hotel_id}/room-types", response_model=list[RoomTypeResponse])
def list_room_types(hotel_id: int, db: Session = Depends(get_db)):
    return db.query(RoomType).filter(RoomType.hotel_id == hotel_id).order_by(RoomType.sort_order).all()
