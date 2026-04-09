from datetime import date

from pydantic import BaseModel


class RatePlanBase(BaseModel):
    name: str
    room_type_id: int
    segment_id: int | None = None
    base_rate: float
    min_rate: float
    max_rate: float
    is_active: bool = True
    valid_from: date | None = None
    valid_to: date | None = None


class RatePlanCreate(RatePlanBase):
    pass


class RatePlanUpdate(BaseModel):
    name: str | None = None
    base_rate: float | None = None
    min_rate: float | None = None
    max_rate: float | None = None
    is_active: bool | None = None
    valid_from: date | None = None
    valid_to: date | None = None


class RatePlanResponse(RatePlanBase):
    id: int
    hotel_id: int
    model_config = {"from_attributes": True}


class RateOverrideCreate(BaseModel):
    rate_plan_id: int
    date: date
    override_rate: float
    reason: str | None = None


class RateOverrideResponse(BaseModel):
    id: int
    rate_plan_id: int
    date: date
    override_rate: float
    reason: str | None
    created_by: str
    model_config = {"from_attributes": True}


class SegmentResponse(BaseModel):
    id: int
    hotel_id: int
    name: str
    discount_pct_from_bar: float
    priority: int
    model_config = {"from_attributes": True}


class ChannelResponse(BaseModel):
    id: int
    hotel_id: int
    name: str
    commission_pct: float
    model_config = {"from_attributes": True}
