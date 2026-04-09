from datetime import date

from pydantic import BaseModel


class OptimizationRequest(BaseModel):
    start_date: date
    end_date: date
    room_type_id: int | None = None


class OptimizationScenario(BaseModel):
    rate: float
    expected_rooms_sold: float
    expected_revenue: float
    variable_costs: float
    contribution_margin: float
    ebitda_contribution: float
    revpar: float
    occupancy_pct: float


class OptimizationResult(BaseModel):
    hotel_id: int
    room_type_id: int
    date: date
    optimal: OptimizationScenario
    current: OptimizationScenario
    improvement_pct: float
    recommendation: str


class DisplacementRequest(BaseModel):
    group_rooms: int
    group_rate: float
    group_nights: int
    check_in: date
    room_type_id: int


class DisplacementResult(BaseModel):
    group_value: float
    displaced_transient_value: float
    net_value: float
    recommendation: str  # "accept" or "reject"
    details: str
