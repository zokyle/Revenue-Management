from datetime import date, datetime

from pydantic import BaseModel


class ForecastResponse(BaseModel):
    id: int
    hotel_id: int
    room_type_id: int
    forecast_date: date
    generated_at: datetime
    method: str
    predicted_occupancy: float
    predicted_adr: float | None
    predicted_demand: float
    confidence_lower: float | None
    confidence_upper: float | None
    model_config = {"from_attributes": True}


class ForecastGenerateRequest(BaseModel):
    start_date: date
    end_date: date
    room_type_id: int | None = None  # None = all room types


class PricingRecommendationResponse(BaseModel):
    id: int
    hotel_id: int
    room_type_id: int
    date: date
    segment_id: int | None
    recommended_rate: float
    current_rate: float
    expected_occupancy: float | None
    expected_revpar: float | None
    expected_ebitda_contribution: float | None
    status: str
    reason_text: str | None
    generated_at: datetime
    model_config = {"from_attributes": True}
