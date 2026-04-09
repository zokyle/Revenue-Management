from pydantic import BaseModel


class RoomTypeBase(BaseModel):
    name: str
    code: str
    base_capacity: int = 2
    max_capacity: int = 4
    physical_rooms: int
    sort_order: int = 0


class RoomTypeCreate(RoomTypeBase):
    pass


class RoomTypeResponse(RoomTypeBase):
    id: int
    hotel_id: int
    model_config = {"from_attributes": True}


class HotelBase(BaseModel):
    name: str
    address: str | None = None
    city: str | None = None
    country: str | None = None
    total_rooms: int
    star_rating: float | None = None
    currency: str = "USD"
    timezone: str = "UTC"
    pricing_aggressiveness: float = 0.5
    rate_protection: float = 0.7
    high_demand_threshold: float = 0.85
    low_demand_threshold: float = 0.40


class HotelCreate(HotelBase):
    pass


class HotelUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    city: str | None = None
    country: str | None = None
    total_rooms: int | None = None
    star_rating: float | None = None
    currency: str | None = None
    timezone: str | None = None
    pricing_aggressiveness: float | None = None
    rate_protection: float | None = None
    high_demand_threshold: float | None = None
    low_demand_threshold: float | None = None


class HotelResponse(HotelBase):
    id: int
    room_types: list[RoomTypeResponse] = []
    model_config = {"from_attributes": True}


class HotelListResponse(HotelBase):
    id: int
    model_config = {"from_attributes": True}
