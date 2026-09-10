"""Pydantic v2 schemas for the golf API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Players & clubs
# ---------------------------------------------------------------------------
class ClubBase(BaseModel):
    code: str = Field(..., max_length=10, examples=["7i"])
    name: str = Field(..., max_length=60, examples=["7 Iron"])
    category: str = "iron"
    loft: float | None = None
    stock_carry: float | None = Field(None, description="Your own estimate of full-swing carry, yards")
    sort_order: int = 0
    active: bool = True


class ClubCreate(ClubBase):
    pass


class ClubUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    loft: float | None = None
    stock_carry: float | None = None
    sort_order: int | None = None
    active: bool | None = None


class ClubResponse(ClubBase):
    id: int
    player_id: int
    model_config = {"from_attributes": True}


class PlayerBase(BaseModel):
    name: str = Field(..., max_length=120)
    handicap_index: float = 15.0
    target_score: int = 79
    risk_tolerance: float = Field(0.35, ge=0.0, le=1.0)
    dominant_miss: str | None = None
    units: str = "yards"


class PlayerCreate(PlayerBase):
    default_bag: bool = Field(True, description="Create a standard 14-club bag with handicap-based priors")


class PlayerUpdate(BaseModel):
    name: str | None = None
    handicap_index: float | None = None
    target_score: int | None = None
    risk_tolerance: float | None = Field(None, ge=0.0, le=1.0)
    dominant_miss: str | None = None
    units: str | None = None


class PlayerResponse(PlayerBase):
    id: int
    created_at: datetime | None = None
    clubs: list[ClubResponse] = []
    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------
FEATURE_KINDS = {"water", "ob", "bunker", "trees", "deep_rough", "native", "creek", "penalty"}
FEATURE_SIDES = {"left", "right", "both", "center", "short", "long"}
HOLE_SHAPES = {"straight", "dogleg_left", "dogleg_right"}


class HoleFeatureBase(BaseModel):
    kind: str = Field(..., examples=["water"])
    side: str = Field("right", examples=["left"])
    start_yards: float = Field(..., ge=0, le=1000)
    end_yards: float = Field(..., ge=0, le=1000)
    offset_yards: float = Field(20.0, ge=0, le=300)
    width_yards: float = Field(999.0, gt=0, le=999)
    penalty_strokes: int | None = Field(None, ge=0, le=3)
    label: str | None = Field(None, max_length=120)

    @field_validator("kind", "side", mode="before")
    @classmethod
    def _norm(cls, v):
        return v.lower().strip() if isinstance(v, str) else v

    @field_validator("kind")
    @classmethod
    def _kind(cls, v):
        if v not in FEATURE_KINDS:
            raise ValueError(f"kind must be one of {sorted(FEATURE_KINDS)}")
        return v

    @field_validator("side")
    @classmethod
    def _side(cls, v):
        if v not in FEATURE_SIDES:
            raise ValueError(f"side must be one of {sorted(FEATURE_SIDES)}")
        return v

    @field_validator("end_yards")
    @classmethod
    def _range(cls, v, info):
        start = info.data.get("start_yards")
        if start is not None and v < start:
            raise ValueError("end_yards must be >= start_yards")
        return v


class HoleFeatureCreate(HoleFeatureBase):
    pass


class HoleFeatureResponse(BaseModel):
    """Read model: no input constraints, so imported data always serialises."""

    id: int
    hole_id: int
    kind: str
    side: str
    start_yards: float
    end_yards: float
    offset_yards: float
    width_yards: float
    penalty_strokes: float | None = None
    label: str | None = None
    model_config = {"from_attributes": True}


class HoleBase(BaseModel):
    number: int = Field(..., ge=1, le=36)
    par: int = Field(..., ge=3, le=6)
    yards: int = Field(..., ge=50, le=800)
    handicap_index: int | None = Field(None, ge=1, le=36)
    shape: str = "straight"
    dogleg_at_yards: float | None = Field(None, ge=0, le=800)
    dogleg_angle_deg: float | None = Field(None, ge=0, le=90)
    fairway_width_yards: float = Field(35.0, ge=10, le=120)
    fairway_start_yards: float = Field(100.0, ge=0, le=800)
    rough_width_yards: float = Field(15.0, ge=0, le=100)
    green_width_yards: float = Field(30.0, ge=8, le=80)
    green_depth_yards: float = Field(30.0, ge=8, le=80)
    elevation_change_ft: float = Field(0.0, ge=-300, le=300)
    notes: str | None = None

    @field_validator("shape", mode="before")
    @classmethod
    def _shape(cls, v):
        v = v.lower().strip() if isinstance(v, str) else v
        if v not in HOLE_SHAPES:
            raise ValueError(f"shape must be one of {sorted(HOLE_SHAPES)}")
        return v


class HoleCreate(HoleBase):
    features: list[HoleFeatureCreate] = []


class HoleUpdate(BaseModel):
    par: int | None = Field(None, ge=3, le=6)
    yards: int | None = Field(None, ge=50, le=800)
    handicap_index: int | None = Field(None, ge=1, le=36)
    shape: str | None = None
    dogleg_at_yards: float | None = Field(None, ge=0, le=800)
    dogleg_angle_deg: float | None = Field(None, ge=0, le=90)
    fairway_width_yards: float | None = Field(None, ge=10, le=120)
    fairway_start_yards: float | None = Field(None, ge=0, le=800)
    rough_width_yards: float | None = Field(None, ge=0, le=100)
    green_width_yards: float | None = Field(None, ge=8, le=80)
    green_depth_yards: float | None = Field(None, ge=8, le=80)
    elevation_change_ft: float | None = Field(None, ge=-300, le=300)
    notes: str | None = None
    features: list[HoleFeatureCreate] | None = Field(None, description="If given, replaces all features")

    @field_validator("shape", mode="before")
    @classmethod
    def _shape(cls, v):
        if v is None:
            return v
        v = v.lower().strip() if isinstance(v, str) else v
        if v not in HOLE_SHAPES:
            raise ValueError(f"shape must be one of {sorted(HOLE_SHAPES)}")
        return v


class HoleResponse(BaseModel):
    id: int
    course_id: int
    number: int
    par: int
    yards: int
    handicap_index: int | None = None
    shape: str = "straight"
    dogleg_at_yards: float | None = None
    dogleg_angle_deg: float | None = None
    fairway_width_yards: float = 35.0
    fairway_start_yards: float = 100.0
    rough_width_yards: float = 15.0
    green_width_yards: float = 30.0
    green_depth_yards: float = 30.0
    elevation_change_ft: float = 0.0
    notes: str | None = None
    features: list[HoleFeatureResponse] = []
    model_config = {"from_attributes": True}


class CourseBase(BaseModel):
    name: str = Field(..., max_length=200)
    city: str | None = None
    country: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    tee_name: str = "White"
    rating: float | None = None
    slope: int | None = None
    notes: str | None = None


class CourseCreate(CourseBase):
    holes: list[HoleCreate] = []


class CourseUpdate(BaseModel):
    name: str | None = None
    city: str | None = None
    country: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    tee_name: str | None = None
    rating: float | None = None
    slope: int | None = None
    notes: str | None = None


class CourseListResponse(CourseBase):
    id: int
    source: str
    par: int | None = None
    yardage: int | None = None
    hole_count: int = 0
    model_config = {"from_attributes": True}


class CourseResponse(CourseBase):
    id: int
    source: str
    osm_id: str | None = None
    par: int | None = None
    yardage: int | None = None
    holes: list[HoleResponse] = []
    model_config = {"from_attributes": True}


class ScorecardHole(BaseModel):
    number: int
    par: int
    yards: int
    handicap_index: int | None = None


class ScorecardImport(BaseModel):
    """Quick-build a course from a scorecard: par + yardage per hole."""

    name: str
    city: str | None = None
    country: str | None = None
    tee_name: str = "White"
    holes: list[ScorecardHole]


class OSMImportRequest(BaseModel):
    name: str | None = Field(None, description="Course name to search on OpenStreetMap")
    latitude: float | None = None
    longitude: float | None = None
    radius_m: int = Field(2500, ge=200, le=10000)
    tee_name: str = "White"


# ---------------------------------------------------------------------------
# Rounds & shots
# ---------------------------------------------------------------------------
class ShotBase(BaseModel):
    sequence: int = Field(..., ge=1)
    club_code: str | None = None
    club_id: int | None = None
    shot_type: str = "full"
    lie_start: str = "fairway"
    start_distance_yards: float = Field(..., ge=0)
    lie_end: str = "fairway"
    end_distance_yards: float = Field(0.0, ge=0)
    carry_yards: float | None = None
    intended_carry_yards: float | None = None
    lateral_miss_yards: float | None = None
    distance_miss_yards: float | None = None
    outcome_tag: str | None = None
    penalty_strokes: int = 0
    holed: bool = False
    notes: str | None = None

    @field_validator("shot_type", "lie_start", "lie_end", mode="before")
    @classmethod
    def _lower(cls, v):
        return v.lower().strip() if isinstance(v, str) else v


class ShotCreate(ShotBase):
    pass


class ShotResponse(ShotBase):
    id: int
    hole_result_id: int
    model_config = {"from_attributes": True}


class HoleResultBase(BaseModel):
    hole_number: int = Field(..., ge=1, le=36)
    hole_id: int | None = None
    par: int = Field(..., ge=3, le=6)
    yards: int | None = None
    score: int = Field(..., ge=1, le=20)
    putts: int | None = Field(None, ge=0, le=10)
    fairway_hit: bool | None = None
    gir: bool | None = None
    penalties: int = 0
    up_and_down: bool | None = None
    sand_save: bool | None = None
    tee_club_id: int | None = None
    tee_miss: str | None = None
    notes: str | None = None


class HoleResultCreate(HoleResultBase):
    shots: list[ShotCreate] = []


class HoleResultResponse(HoleResultBase):
    id: int
    round_id: int
    shots: list[ShotResponse] = []
    model_config = {"from_attributes": True}


class RoundBase(BaseModel):
    course_id: int | None = None
    played_on: date | None = None
    tee_name: str | None = None
    weather: str | None = None
    wind: str | None = None
    logging_mode: str = "full"
    notes: str | None = None


class RoundCreate(RoundBase):
    holes: list[HoleResultCreate] = []
    completed: bool = False


class RoundUpdate(BaseModel):
    course_id: int | None = None
    played_on: date | None = None
    tee_name: str | None = None
    weather: str | None = None
    wind: str | None = None
    logging_mode: str | None = None
    notes: str | None = None
    completed: bool | None = None
    total_score: int | None = None


class RoundListResponse(RoundBase):
    id: int
    player_id: int
    total_score: int | None = None
    completed: bool
    course_name: str | None = None
    holes_logged: int = 0
    model_config = {"from_attributes": True}


class RoundResponse(RoundBase):
    id: int
    player_id: int
    total_score: int | None = None
    completed: bool
    holes: list[HoleResultResponse] = []
    model_config = {"from_attributes": True}


class NarrativeRequest(BaseModel):
    """Free-text description of one or more holes, parsed by the caddie."""

    text: str = Field(..., min_length=5)
    hole_number: int | None = Field(None, description="Hole the text refers to; the parser may find several")
    commit: bool = Field(True, description="Save the parsed shots to the round (false = preview)")


class NarrativeParsedHole(BaseModel):
    hole_number: int
    par: int
    score: int
    putts: int | None = None
    fairway_hit: bool | None = None
    gir: bool | None = None
    penalties: int = 0
    shots: list[ShotCreate] = []


class NarrativeResponse(BaseModel):
    holes: list[NarrativeParsedHole]
    parser: str  # "claude" | "heuristic"
    warnings: list[str] = []


# ---------------------------------------------------------------------------
# Profile / strategy / caddie
# ---------------------------------------------------------------------------
class ProfileResponse(BaseModel):
    id: int
    player_id: int
    computed_at: datetime
    rounds_count: int
    shots_count: int
    readiness_score: float
    readiness_level: str
    data: dict[str, Any]
    model_config = {"from_attributes": True}


class StrategyRequest(BaseModel):
    objective: str = Field("break_80", pattern="^(break_80|min_expected|aggressive)$")
    carry_scale: float = Field(1.0, ge=0.8, le=1.2, description="Wind/temperature/altitude carry multiplier")
    samples: int | None = Field(None, ge=100, le=2000)
    seed: int | None = Field(None, ge=0)


class StrategyResponse(BaseModel):
    id: int
    player_id: int
    course_id: int
    created_at: datetime
    objective: str
    expected_score: float | None
    p_break_target: float | None
    data: dict[str, Any]
    model_config = {"from_attributes": True}


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    course_id: int | None = None
    hole_number: int | None = None


class ChatResponse(BaseModel):
    reply: str
    provider: str  # "claude" | "heuristic"
    actions: list[dict[str, Any]] = []
    history: list[dict[str, Any]] = []
