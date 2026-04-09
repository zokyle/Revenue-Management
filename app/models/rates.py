from datetime import date

from sqlalchemy import Integer, String, Float, Date, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class RatePlan(Base):
    __tablename__ = "rate_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), nullable=False)
    room_type_id: Mapped[int] = mapped_column(ForeignKey("room_types.id"), nullable=False)
    segment_id: Mapped[int] = mapped_column(ForeignKey("market_segments.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    base_rate: Mapped[float] = mapped_column(Float, nullable=False)
    min_rate: Mapped[float] = mapped_column(Float, nullable=False)
    max_rate: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    valid_from: Mapped[date] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date] = mapped_column(Date, nullable=True)

    room_type = relationship("RoomType")
    segment = relationship("MarketSegment")


class RateOverride(Base):
    __tablename__ = "rate_overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rate_plan_id: Mapped[int] = mapped_column(ForeignKey("rate_plans.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    override_rate: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(String(200), nullable=True)
    created_by: Mapped[str] = mapped_column(String(50), default="system")

    rate_plan = relationship("RatePlan")


class LOSRestriction(Base):
    __tablename__ = "los_restrictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), nullable=False)
    room_type_id: Mapped[int] = mapped_column(ForeignKey("room_types.id"), nullable=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    min_los: Mapped[int] = mapped_column(Integer, default=1)
    max_los: Mapped[int] = mapped_column(Integer, nullable=True)
    close_to_arrival: Mapped[bool] = mapped_column(Boolean, default=False)
