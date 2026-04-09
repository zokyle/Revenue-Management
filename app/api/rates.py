from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.rates import RatePlan, RateOverride, LOSRestriction
from app.models.segments import MarketSegment, Channel
from app.schemas.rates import (
    RatePlanCreate, RatePlanUpdate, RatePlanResponse,
    RateOverrideCreate, RateOverrideResponse,
    SegmentResponse, ChannelResponse,
)

router = APIRouter()


@router.get("/{hotel_id}/rates", response_model=list[RatePlanResponse])
def list_rate_plans(
    hotel_id: int,
    room_type_id: int | None = Query(None),
    active_only: bool = Query(True),
    db: Session = Depends(get_db),
):
    query = db.query(RatePlan).filter(RatePlan.hotel_id == hotel_id)
    if room_type_id:
        query = query.filter(RatePlan.room_type_id == room_type_id)
    if active_only:
        query = query.filter(RatePlan.is_active == True)  # noqa: E712
    return query.all()


@router.post("/{hotel_id}/rates", response_model=RatePlanResponse, status_code=201)
def create_rate_plan(hotel_id: int, data: RatePlanCreate, db: Session = Depends(get_db)):
    plan = RatePlan(hotel_id=hotel_id, **data.model_dump())
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@router.put("/{hotel_id}/rates/{rate_plan_id}", response_model=RatePlanResponse)
def update_rate_plan(hotel_id: int, rate_plan_id: int, data: RatePlanUpdate, db: Session = Depends(get_db)):
    plan = db.query(RatePlan).filter(RatePlan.id == rate_plan_id, RatePlan.hotel_id == hotel_id).first()
    if not plan:
        raise HTTPException(404, "Rate plan not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(plan, field, value)
    db.commit()
    db.refresh(plan)
    return plan


@router.post("/{hotel_id}/rates/override", response_model=RateOverrideResponse, status_code=201)
def create_rate_override(hotel_id: int, data: RateOverrideCreate, db: Session = Depends(get_db)):
    plan = db.query(RatePlan).filter(RatePlan.id == data.rate_plan_id, RatePlan.hotel_id == hotel_id).first()
    if not plan:
        raise HTTPException(404, "Rate plan not found")
    override = RateOverride(**data.model_dump(), created_by="manual")
    db.add(override)
    db.commit()
    db.refresh(override)
    return override


@router.get("/{hotel_id}/rates/overrides", response_model=list[RateOverrideResponse])
def list_overrides(
    hotel_id: int,
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: Session = Depends(get_db),
):
    return (
        db.query(RateOverride)
        .join(RatePlan)
        .filter(RatePlan.hotel_id == hotel_id, RateOverride.date >= start_date, RateOverride.date <= end_date)
        .all()
    )


@router.get("/{hotel_id}/segments", response_model=list[SegmentResponse])
def list_segments(hotel_id: int, db: Session = Depends(get_db)):
    return db.query(MarketSegment).filter(MarketSegment.hotel_id == hotel_id).order_by(MarketSegment.priority).all()


@router.get("/{hotel_id}/channels", response_model=list[ChannelResponse])
def list_channels(hotel_id: int, db: Session = Depends(get_db)):
    return db.query(Channel).filter(Channel.hotel_id == hotel_id).all()
