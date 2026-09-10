"""Learned player profile snapshots, generated strategy plans and caddie chat."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from golf.database import Base


class ProfileSnapshot(Base):
    """A frozen copy of everything the engine has learned about the player.

    ``data`` holds the full JSON profile (see ``golf.engine.learning`` for the
    shape): per-club distributions, personal expected-strokes table,
    tendencies, ranked errors and readiness details.
    """

    __tablename__ = "golf_profile_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("golf_players.id"), nullable=False, index=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    rounds_count: Mapped[int] = mapped_column(Integer, default=0)
    shots_count: Mapped[int] = mapped_column(Integer, default=0)
    readiness_score: Mapped[float] = mapped_column(Float, default=0.0)
    readiness_level: Mapped[str] = mapped_column(String(20), default="cold")
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class StrategyPlan(Base):
    """A hole-by-hole game plan for one player on one course."""

    __tablename__ = "golf_strategy_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("golf_players.id"), nullable=False, index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("golf_courses.id"), nullable=False, index=True)
    profile_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("golf_profile_snapshots.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    objective: Mapped[str] = mapped_column(String(30), default="break_80")
    expected_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    p_break_target: Mapped[float | None] = mapped_column(Float, nullable=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)

    course: Mapped["Course"] = relationship()  # noqa: F821


class ChatMessage(Base):
    """Persisted caddie conversation so the agent remembers context between visits."""

    __tablename__ = "golf_chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("golf_players.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(10), nullable=False)  # "user" / "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
