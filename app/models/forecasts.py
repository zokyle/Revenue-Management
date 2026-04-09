from datetime import date, datetime

from sqlalchemy import Integer, String, Float, Date, DateTime, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database import Base


class RecommendationStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ForecastRecord(Base):
    __tablename__ = "forecast_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), nullable=False)
    room_type_id: Mapped[int] = mapped_column(ForeignKey("room_types.id"), nullable=False)
    forecast_date: Mapped[date] = mapped_column(Date, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    method: Mapped[str] = mapped_column(String(50), default="decomposition_pickup")
    predicted_occupancy: Mapped[float] = mapped_column(Float, nullable=False)
    predicted_adr: Mapped[float] = mapped_column(Float, nullable=True)
    predicted_demand: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_lower: Mapped[float] = mapped_column(Float, nullable=True)
    confidence_upper: Mapped[float] = mapped_column(Float, nullable=True)

    room_type = relationship("RoomType")


class PricingRecommendation(Base):
    __tablename__ = "pricing_recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), nullable=False)
    room_type_id: Mapped[int] = mapped_column(ForeignKey("room_types.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    segment_id: Mapped[int] = mapped_column(ForeignKey("market_segments.id"), nullable=True)
    recommended_rate: Mapped[float] = mapped_column(Float, nullable=False)
    current_rate: Mapped[float] = mapped_column(Float, nullable=False)
    expected_occupancy: Mapped[float] = mapped_column(Float, nullable=True)
    expected_revpar: Mapped[float] = mapped_column(Float, nullable=True)
    expected_ebitda_contribution: Mapped[float] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum(RecommendationStatus), default=RecommendationStatus.PENDING
    )
    reason_text: Mapped[str] = mapped_column(String(500), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    room_type = relationship("RoomType")
    segment = relationship("MarketSegment")
