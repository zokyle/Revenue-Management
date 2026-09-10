"""Rounds, per-hole results and individual shots (the raw learning data)."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from golf.database import Base


class LoggingMode(str, Enum):
    QUICK = "quick"          # score / putts / FIR / GIR / penalties per hole
    FULL = "full"            # every shot
    NARRATIVE = "narrative"  # free text parsed by the caddie agent


class ShotType(str, Enum):
    TEE = "tee"
    FULL = "full"
    PUNCH = "punch"
    RECOVERY = "recovery"
    PITCH = "pitch"
    CHIP = "chip"
    BUNKER = "bunker"
    PUTT = "putt"


class OutcomeTag(str, Enum):
    GOOD = "good"
    SHORT = "short"
    LONG = "long"
    LEFT = "left"
    RIGHT = "right"
    HOOK = "hook"
    SLICE = "slice"
    PULL = "pull"
    PUSH = "push"
    THIN = "thin"
    FAT = "fat"
    TOP = "top"
    SHANK = "shank"
    PENALTY = "penalty"
    OB = "ob"
    THREE_PUTT = "three_putt"
    LIP_OUT = "lip_out"


class Round(Base):
    __tablename__ = "golf_rounds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("golf_players.id"), nullable=False, index=True)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("golf_courses.id"), nullable=True, index=True)
    played_on: Mapped[date] = mapped_column(Date, default=date.today)
    tee_name: Mapped[str | None] = mapped_column(String(40), nullable=True)
    total_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weather: Mapped[str | None] = mapped_column(String(60), nullable=True)
    wind: Mapped[str | None] = mapped_column(String(40), nullable=True)
    logging_mode: Mapped[str] = mapped_column(String(20), default=LoggingMode.FULL.value)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    player: Mapped["Player"] = relationship(back_populates="rounds")  # noqa: F821
    course: Mapped["Course | None"] = relationship()  # noqa: F821
    holes: Mapped[list["HoleResult"]] = relationship(
        back_populates="round", cascade="all, delete-orphan", order_by="HoleResult.hole_number"
    )


class HoleResult(Base):
    __tablename__ = "golf_hole_results"
    __table_args__ = (UniqueConstraint("round_id", "hole_number", name="uq_golf_hole_result_round_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("golf_rounds.id"), nullable=False, index=True)
    hole_id: Mapped[int | None] = mapped_column(ForeignKey("golf_holes.id"), nullable=True)
    hole_number: Mapped[int] = mapped_column(Integer, nullable=False)
    par: Mapped[int] = mapped_column(Integer, nullable=False)
    yards: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    putts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fairway_hit: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # None on par 3s
    gir: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    penalties: Mapped[int] = mapped_column(Integer, default=0)
    up_and_down: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sand_save: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    tee_club_id: Mapped[int | None] = mapped_column(ForeignKey("golf_clubs.id"), nullable=True)
    tee_miss: Mapped[str | None] = mapped_column(String(20), nullable=True)  # left/right/short/long/none
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    round: Mapped["Round"] = relationship(back_populates="holes")
    shots: Mapped[list["Shot"]] = relationship(
        back_populates="hole_result", cascade="all, delete-orphan", order_by="Shot.sequence"
    )


class Shot(Base):
    __tablename__ = "golf_shots"
    __table_args__ = (UniqueConstraint("hole_result_id", "sequence", name="uq_golf_shot_hole_sequence"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hole_result_id: Mapped[int] = mapped_column(ForeignKey("golf_hole_results.id"), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    club_id: Mapped[int | None] = mapped_column(ForeignKey("golf_clubs.id"), nullable=True)
    club_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    shot_type: Mapped[str] = mapped_column(String(20), default=ShotType.FULL.value)
    lie_start: Mapped[str] = mapped_column(String(20), nullable=False)
    start_distance_yards: Mapped[float] = mapped_column(Float, nullable=False)  # distance to hole before the shot
    lie_end: Mapped[str] = mapped_column(String(20), nullable=False)
    end_distance_yards: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)  # 0 when holed
    # Measured carry when known (GPS / rangefinder). Otherwise derived.
    carry_yards: Mapped[float | None] = mapped_column(Float, nullable=True)
    intended_carry_yards: Mapped[float | None] = mapped_column(Float, nullable=True)
    lateral_miss_yards: Mapped[float | None] = mapped_column(Float, nullable=True)   # +right / -left of target
    distance_miss_yards: Mapped[float | None] = mapped_column(Float, nullable=True)  # +long / -short of target
    outcome_tag: Mapped[str | None] = mapped_column(String(20), nullable=True)
    penalty_strokes: Mapped[int] = mapped_column(Integer, default=0)
    holed: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    hole_result: Mapped["HoleResult"] = relationship(back_populates="shots")
