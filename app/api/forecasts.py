from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.forecasts import ForecastRecord
from app.models.property import Hotel, RoomType
from app.engine.forecaster import DemandForecaster
from app.schemas.forecasts import ForecastResponse, ForecastGenerateRequest

router = APIRouter()


@router.get("/{hotel_id}/forecast", response_model=list[ForecastResponse])
def get_forecasts(
    hotel_id: int,
    start_date: date = Query(...),
    end_date: date = Query(...),
    room_type_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(ForecastRecord).filter(
        ForecastRecord.hotel_id == hotel_id,
        ForecastRecord.forecast_date >= start_date,
        ForecastRecord.forecast_date <= end_date,
    )
    if room_type_id:
        query = query.filter(ForecastRecord.room_type_id == room_type_id)
    return query.order_by(ForecastRecord.forecast_date).all()


@router.post("/{hotel_id}/forecast/generate", response_model=list[ForecastResponse])
def generate_forecast(hotel_id: int, data: ForecastGenerateRequest, db: Session = Depends(get_db)):
    hotel = db.query(Hotel).filter(Hotel.id == hotel_id).first()
    if not hotel:
        raise HTTPException(404, "Hotel not found")

    room_types = db.query(RoomType).filter(RoomType.hotel_id == hotel_id)
    if data.room_type_id:
        room_types = room_types.filter(RoomType.id == data.room_type_id)
    room_types = room_types.all()

    if not room_types:
        raise HTTPException(404, "No room types found")

    forecaster = DemandForecaster()
    all_records = []
    now = datetime.utcnow()

    for rt in room_types:
        forecast_dicts = forecaster.generate_forecast(
            db, hotel_id, rt.id, data.start_date, data.end_date
        )
        # Delete old forecasts for this range
        db.query(ForecastRecord).filter(
            ForecastRecord.hotel_id == hotel_id,
            ForecastRecord.room_type_id == rt.id,
            ForecastRecord.forecast_date >= data.start_date,
            ForecastRecord.forecast_date <= data.end_date,
        ).delete()

        # Convert forecast dicts to ORM objects
        for fd in forecast_dicts:
            record = ForecastRecord(
                hotel_id=hotel_id,
                room_type_id=rt.id,
                forecast_date=fd["forecast_date"],
                generated_at=now,
                method=fd.get("method", "decomposition_pickup"),
                predicted_occupancy=fd["predicted_occupancy"],
                predicted_adr=None,
                predicted_demand=fd["predicted_demand"],
                confidence_lower=fd.get("confidence_lower"),
                confidence_upper=fd.get("confidence_upper"),
            )
            db.add(record)
            all_records.append(record)

    db.commit()
    for r in all_records:
        db.refresh(r)

    return all_records
