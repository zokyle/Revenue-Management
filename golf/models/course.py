"""Course, hole and hole-feature models.

A hole is described in a simple *hole-relative coordinate system*:

* ``x`` runs from the tee (0) along the hole's centerline toward the green
  (``Hole.yards``).  Doglegs bend the centerline but ``x`` keeps measuring
  distance *along* it, exactly like a yardage book.
* ``y`` is the lateral offset from the centerline in yards, positive to the
  right of the golfer standing on the tee.

Features (water, OB, bunkers, trees...) are boxes in that coordinate system:
``[start_yards, end_yards]`` along the hole, and from ``offset_yards`` to
``offset_yards + width_yards`` away from the centerline on ``side``.
Think of it as drawing hazards on a strip of graph paper laid over the hole.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from golf.database import Base


class CourseSource(str, Enum):
    MANUAL = "manual"
    OSM = "osm"
    JSON = "json"
    SCORECARD = "scorecard"


class HoleShape(str, Enum):
    STRAIGHT = "straight"
    DOGLEG_LEFT = "dogleg_left"
    DOGLEG_RIGHT = "dogleg_right"


class FeatureKind(str, Enum):
    WATER = "water"          # penalty area: +1 stroke, drop
    OB = "ob"                # out of bounds: stroke and distance
    BUNKER = "bunker"        # sand lie, no penalty
    TREES = "trees"          # recovery lie (punch out)
    DEEP_ROUGH = "deep_rough"  # rough lie, extra half-shot cost
    NATIVE = "native"        # native area / fescue: treated like deep rough with lost-ball risk
    CREEK = "creek"          # cross-hazard: penalty area
    PENALTY = "penalty"      # generic penalty area


class FeatureSide(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    BOTH = "both"      # mirrored on both sides (e.g. tree-lined)
    CENTER = "center"  # crosses the fairway (creek, cross bunker)
    LONG = "long"      # behind the green
    SHORT = "short"    # in front of the green


class Course(Base):
    __tablename__ = "golf_courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default=CourseSource.MANUAL.value)
    osm_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tee_name: Mapped[str] = mapped_column(String(40), default="White")
    par: Mapped[int | None] = mapped_column(Integer, nullable=True)
    yardage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    slope: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    holes: Mapped[list["Hole"]] = relationship(
        back_populates="course", cascade="all, delete-orphan", order_by="Hole.number"
    )


class Hole(Base):
    __tablename__ = "golf_holes"
    __table_args__ = (UniqueConstraint("course_id", "number", name="uq_golf_hole_course_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("golf_courses.id"), nullable=False, index=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    par: Mapped[int] = mapped_column(Integer, nullable=False)
    yards: Mapped[int] = mapped_column(Integer, nullable=False)
    handicap_index: Mapped[int | None] = mapped_column(Integer, nullable=True)  # stroke index 1-18
    shape: Mapped[str] = mapped_column(String(20), default=HoleShape.STRAIGHT.value)
    dogleg_at_yards: Mapped[float | None] = mapped_column(Float, nullable=True)
    dogleg_angle_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Corridor geometry (yards). Rough sits between the fairway edge and
    # fairway_half_width + rough_width; beyond that is "trouble" only if a
    # feature says so, otherwise it is still rough.
    fairway_width_yards: Mapped[float] = mapped_column(Float, default=35.0)
    fairway_start_yards: Mapped[float] = mapped_column(Float, default=100.0)
    rough_width_yards: Mapped[float] = mapped_column(Float, default=15.0)
    green_width_yards: Mapped[float] = mapped_column(Float, default=30.0)
    green_depth_yards: Mapped[float] = mapped_column(Float, default=30.0)
    elevation_change_ft: Mapped[float] = mapped_column(Float, default=0.0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    course: Mapped["Course"] = relationship(back_populates="holes")
    features: Mapped[list["HoleFeature"]] = relationship(
        back_populates="hole", cascade="all, delete-orphan", order_by="HoleFeature.start_yards"
    )


class HoleFeature(Base):
    __tablename__ = "golf_hole_features"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hole_id: Mapped[int] = mapped_column(ForeignKey("golf_holes.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False, default=FeatureSide.RIGHT.value)
    start_yards: Mapped[float] = mapped_column(Float, nullable=False)
    end_yards: Mapped[float] = mapped_column(Float, nullable=False)
    # Lateral distance from the centerline to the near edge of the feature.
    offset_yards: Mapped[float] = mapped_column(Float, default=20.0)
    # How far the feature extends outward from its near edge. 999 = "everything beyond".
    width_yards: Mapped[float] = mapped_column(Float, default=999.0)
    # Optional override of the stroke penalty implied by ``kind``.
    penalty_strokes: Mapped[float | None] = mapped_column(Float, nullable=True)
    label: Mapped[str | None] = mapped_column(String(120), nullable=True)

    hole: Mapped["Hole"] = relationship(back_populates="features")
