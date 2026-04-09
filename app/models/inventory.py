from datetime import date, datetime

from sqlalchemy import Integer, String, Float, Date, DateTime, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database import Base


class ReservationStatus(str, enum.Enum):
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    CHECKED_IN = "checked_in"
    CHECKED_OUT = "checked_out"


class RoomInventory(Base):
    __tablename__ = "room_inventory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), nullable=False)
    room_type_id: Mapped[int] = mapped_column(ForeignKey("room_types.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    total_available: Mapped[int] = mapped_column(Integer, nullable=False)
    sold: Mapped[int] = mapped_column(Integer, default=0)
    held_group: Mapped[int] = mapped_column(Integer, default=0)
    out_of_order: Mapped[int] = mapped_column(Integer, default=0)
    overbooking_allowance: Mapped[int] = mapped_column(Integer, default=0)

    room_type = relationship("RoomType")


class Reservation(Base):
    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), nullable=False)
    room_type_id: Mapped[int] = mapped_column(ForeignKey("room_types.id"), nullable=False)
    segment_id: Mapped[int] = mapped_column(ForeignKey("market_segments.id"), nullable=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), nullable=True)
    confirmation_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    guest_name: Mapped[str] = mapped_column(String(200), nullable=False)
    check_in: Mapped[date] = mapped_column(Date, nullable=False)
    check_out: Mapped[date] = mapped_column(Date, nullable=False)
    nights: Mapped[int] = mapped_column(Integer, nullable=False)
    rate_amount: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(ReservationStatus), default=ReservationStatus.CONFIRMED
    )
    booking_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    cancellation_date: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    room_type = relationship("RoomType")
    segment = relationship("MarketSegment")
    channel = relationship("Channel")
