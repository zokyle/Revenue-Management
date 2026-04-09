from datetime import date, datetime

from pydantic import BaseModel


class RoomInventoryResponse(BaseModel):
    id: int
    hotel_id: int
    room_type_id: int
    date: date
    total_available: int
    sold: int
    held_group: int
    out_of_order: int
    overbooking_allowance: int
    model_config = {"from_attributes": True}

    @property
    def remaining(self) -> int:
        return self.total_available - self.sold - self.held_group - self.out_of_order + self.overbooking_allowance


class RoomInventoryUpdate(BaseModel):
    out_of_order: int | None = None
    held_group: int | None = None
    overbooking_allowance: int | None = None


class ReservationResponse(BaseModel):
    id: int
    hotel_id: int
    room_type_id: int
    segment_id: int | None
    channel_id: int | None
    confirmation_number: str
    guest_name: str
    check_in: date
    check_out: date
    nights: int
    rate_amount: float
    status: str
    booking_date: datetime
    cancellation_date: datetime | None
    model_config = {"from_attributes": True}
