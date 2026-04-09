from sqlalchemy import Integer, String, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Hotel(Base):
    __tablename__ = "hotels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str] = mapped_column(String(500), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=True)
    country: Mapped[str] = mapped_column(String(100), nullable=True)
    total_rooms: Mapped[int] = mapped_column(Integer, nullable=False)
    star_rating: Mapped[float] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    timezone: Mapped[str] = mapped_column(String(50), default="UTC")

    # Pricing config
    pricing_aggressiveness: Mapped[float] = mapped_column(Float, default=0.5)
    rate_protection: Mapped[float] = mapped_column(Float, default=0.7)
    high_demand_threshold: Mapped[float] = mapped_column(Float, default=0.85)
    low_demand_threshold: Mapped[float] = mapped_column(Float, default=0.40)

    room_types: Mapped[list["RoomType"]] = relationship(back_populates="hotel", cascade="all, delete-orphan")


class RoomType(Base):
    __tablename__ = "room_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(10), nullable=False)
    base_capacity: Mapped[int] = mapped_column(Integer, default=2)
    max_capacity: Mapped[int] = mapped_column(Integer, default=4)
    physical_rooms: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    hotel: Mapped["Hotel"] = relationship(back_populates="room_types")
