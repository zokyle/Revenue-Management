from datetime import date

from sqlalchemy import Integer, String, Float, Date, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CostProfile(Base):
    __tablename__ = "cost_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    cpor: Mapped[float] = mapped_column(Float, nullable=False)  # Total CPOR
    fixed_daily_cost: Mapped[float] = mapped_column(Float, default=0.0)
    variable_cost_pct: Mapped[float] = mapped_column(Float, default=0.0)  # % of revenue
    effective_from: Mapped[date] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date] = mapped_column(Date, nullable=True)

    items: Mapped[list["CostItem"]] = relationship(back_populates="profile", cascade="all, delete-orphan")


class CostItem(Base):
    __tablename__ = "cost_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cost_profile_id: Mapped[int] = mapped_column(ForeignKey("cost_profiles.id"), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    amount_per_room: Mapped[float] = mapped_column(Float, nullable=False)
    is_variable: Mapped[bool] = mapped_column(Boolean, default=True)

    profile: Mapped["CostProfile"] = relationship(back_populates="items")
