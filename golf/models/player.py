"""Player and club models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from golf.database import Base


class ClubCategory(str, Enum):
    DRIVER = "driver"
    WOOD = "wood"
    HYBRID = "hybrid"
    IRON = "iron"
    WEDGE = "wedge"
    PUTTER = "putter"


class Player(Base):
    __tablename__ = "golf_players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    handicap_index: Mapped[float] = mapped_column(Float, default=15.0)
    target_score: Mapped[int] = mapped_column(Integer, default=79)
    # 0 = play as safe as possible, 1 = chase birdies. Drives the double-bogey
    # penalty weight in the strategy objective.
    risk_tolerance: Mapped[float] = mapped_column(Float, default=0.35)
    dominant_miss: Mapped[str | None] = mapped_column(String(20), nullable=True)  # "left" / "right"
    units: Mapped[str] = mapped_column(String(10), default="yards")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    clubs: Mapped[list["Club"]] = relationship(
        back_populates="player", cascade="all, delete-orphan", order_by="Club.sort_order"
    )
    rounds: Mapped[list["Round"]] = relationship(back_populates="player", cascade="all, delete-orphan")  # noqa: F821


class Club(Base):
    __tablename__ = "golf_clubs"
    __table_args__ = (UniqueConstraint("player_id", "code", name="uq_golf_club_player_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("golf_players.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(10), nullable=False)  # "D", "3w", "7i", "PW", "P"
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False, default=ClubCategory.IRON.value)
    loft: Mapped[float | None] = mapped_column(Float, nullable=True)
    # The player's own estimate of stock carry (yards). Used as an extra prior
    # until logged shots take over.
    stock_carry: Mapped[float | None] = mapped_column(Float, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    player: Mapped["Player"] = relationship(back_populates="clubs")
