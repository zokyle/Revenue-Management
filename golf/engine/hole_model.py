"""Hole geometry: turning a scorecard-plus-hazards description into something
the strategy engine can simulate against.

Coordinate systems
------------------
* **World coordinates** ``(wx, wy)``: a flat map of the hole in yards.  The tee
  is at (0, 0) and the first segment of the centerline runs along +wx.  A
  dogleg turns the centerline by ``dogleg_angle_deg`` (positive = right) at
  ``dogleg_at_yards``.  Shots fly in straight lines in *world* coordinates.
* **Local (yardage-book) coordinates** ``(x, y)``: ``x`` is the distance along
  the centerline from the tee, ``y`` the signed lateral offset (+ = right of
  the centerline).  Fairway, rough and hazards are described in local
  coordinates because that is how golfers think ("water left from 230 to 290").

Analogy: the world map is the satellite photo; the local strip is the page in
the yardage book.  ``HoleGeometry`` converts between them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from golf.engine.baselines import Lie

# Extra strokes on top of the base lie cost for nasty-but-playable spots.
DEEP_ROUGH_EXTRA = 0.25
NATIVE_EXTRA = 0.45
FRINGE_RING_YARDS = 3.0
GREEN_APRON_YARDS = 6.0   # short-grass run-up in front of the green counts as fairway

# Lie classification priority when features overlap (higher wins).
_KIND_PRIORITY = {
    "ob": 6, "water": 5, "creek": 5, "penalty": 5, "trees": 4, "bunker": 3,
    "native": 2, "deep_rough": 1,
}


@dataclass
class FeatureBox:
    kind: str
    side: str
    start_yards: float
    end_yards: float
    offset_yards: float = 20.0
    width_yards: float = 999.0
    penalty_strokes: float | None = None
    label: str | None = None

    def contains(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """Vectorised membership test in local coordinates."""
        in_x = (x >= self.start_yards) & (x <= self.end_yards)
        near, far = self.offset_yards, self.offset_yards + self.width_yards
        if self.side == "left":
            in_y = (y <= -near) & (y >= -far)
        elif self.side == "right":
            in_y = (y >= near) & (y <= far)
        elif self.side == "both":
            in_y = (np.abs(y) >= near) & (np.abs(y) <= far)
        else:  # center / short / long: a band centred on offset with total width
            half = self.width_yards / 2.0 if self.width_yards < 900 else 999.0
            in_y = np.abs(y - self.offset_yards) <= half
        return in_x & in_y


@dataclass
class Landing:
    """Result of classifying one landing spot."""

    lie: str
    distance_to_hole: float
    penalty_strokes: float = 0.0
    extra_strokes: float = 0.0
    feature: str | None = None
    x: float = 0.0
    y: float = 0.0


@dataclass
class HoleGeometry:
    number: int
    par: int
    yards: float
    shape: str = "straight"
    dogleg_at_yards: float | None = None
    dogleg_angle_deg: float | None = None
    fairway_width_yards: float = 35.0
    fairway_start_yards: float = 100.0
    rough_width_yards: float = 15.0
    green_width_yards: float = 30.0
    green_depth_yards: float = 30.0
    elevation_change_ft: float = 0.0
    features: list[FeatureBox] = field(default_factory=list)
    name: str | None = None

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    @classmethod
    def from_hole(cls, hole: Any) -> "HoleGeometry":
        """Build from a ``golf.models.course.Hole`` ORM object (or duck-type)."""
        feats = [
            FeatureBox(
                kind=f.kind, side=f.side, start_yards=f.start_yards, end_yards=f.end_yards,
                offset_yards=f.offset_yards, width_yards=f.width_yards,
                penalty_strokes=f.penalty_strokes, label=f.label,
            )
            for f in (hole.features or [])
        ]
        return cls(
            number=hole.number, par=hole.par, yards=float(hole.yards), shape=hole.shape or "straight",
            dogleg_at_yards=hole.dogleg_at_yards, dogleg_angle_deg=hole.dogleg_angle_deg,
            fairway_width_yards=hole.fairway_width_yards or 35.0,
            fairway_start_yards=hole.fairway_start_yards if hole.fairway_start_yards is not None else 100.0,
            rough_width_yards=hole.rough_width_yards or 15.0,
            green_width_yards=hole.green_width_yards or 30.0,
            green_depth_yards=hole.green_depth_yards or 30.0,
            elevation_change_ft=hole.elevation_change_ft or 0.0,
            features=feats,
        )

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "HoleGeometry":
        feats = [FeatureBox(**{k: v for k, v in f.items() if k in FeatureBox.__dataclass_fields__}) for f in d.get("features", [])]
        kwargs = {k: v for k, v in d.items() if k in cls.__dataclass_fields__ and k != "features"}
        return cls(features=feats, **kwargs)

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------
    @property
    def has_dogleg(self) -> bool:
        return (
            self.shape in ("dogleg_left", "dogleg_right")
            and self.dogleg_at_yards is not None
            and 0 < self.dogleg_at_yards < self.yards
        )

    @property
    def turn_radians(self) -> float:
        if not self.has_dogleg:
            return 0.0
        ang = abs(self.dogleg_angle_deg or 35.0)
        return math.radians(ang if self.shape == "dogleg_right" else -ang)

    @property
    def playing_yards(self) -> float:
        """Effective length after elevation (uphill plays longer: ~1 yd per 3 ft)."""
        return self.yards + self.elevation_change_ft / 3.0

    def green_center_world(self) -> tuple[float, float]:
        return self.local_to_world(self.yards, 0.0)

    def local_to_world(self, x: float, y: float) -> tuple[float, float]:
        if not self.has_dogleg or x <= self.dogleg_at_yards:
            return float(x), float(y)
        th = self.turn_radians
        dx, dy = math.cos(th), math.sin(th)
        s = x - self.dogleg_at_yards
        wx = self.dogleg_at_yards + s * dx - y * dy
        wy = s * dy + y * dx
        return float(wx), float(wy)

    def world_to_local(self, wx: np.ndarray, wy: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Vectorised world -> local conversion (nearest centerline segment)."""
        wx = np.asarray(wx, dtype=float)
        wy = np.asarray(wy, dtype=float)
        if not self.has_dogleg:
            return wx.copy(), wy.copy()
        th = self.turn_radians
        dx, dy = math.cos(th), math.sin(th)
        L1 = self.dogleg_at_yards
        L2 = self.yards - L1
        # Segment 1: from (0,0) along +x
        t1 = np.clip(wx, 0.0, L1)
        d1 = np.hypot(wx - t1, wy)
        # Segment 2: from corner along (dx, dy)
        rx, ry = wx - L1, wy
        t2 = np.clip(rx * dx + ry * dy, 0.0, L2)
        px, py = L1 + t2 * dx, t2 * dy
        d2 = np.hypot(wx - px, wy - py)
        use2 = d2 < d1
        x_local = np.where(use2, L1 + t2, t1)
        # Signed lateral: cross product sign of segment direction with the offset vector.
        y1 = wy  # segment 1 direction (1,0): lateral = wy
        y2 = -(wx - px) * dy + (wy - py) * dx  # rotate offset into segment-2 frame
        y_local = np.where(use2, y2, y1)
        return x_local, y_local

    def distance_to_hole_world(self, wx: np.ndarray, wy: np.ndarray) -> np.ndarray:
        gx, gy = self.green_center_world()
        return np.hypot(np.asarray(wx, dtype=float) - gx, np.asarray(wy, dtype=float) - gy)

    def aim_direction(self, from_world: tuple[float, float], target_local: tuple[float, float]) -> tuple[float, float]:
        """Unit vector in world coords from ``from_world`` toward a local target."""
        tx, ty = self.local_to_world(*target_local)
        vx, vy = tx - from_world[0], ty - from_world[1]
        n = math.hypot(vx, vy) or 1.0
        return vx / n, vy / n

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------
    def classify_world(self, wx: np.ndarray, wy: np.ndarray) -> dict[str, np.ndarray]:
        """Classify many landing spots given in world coordinates.

        Returns dict of arrays: ``lie`` (str), ``penalty`` (float),
        ``extra`` (float), ``dist`` (yards to hole), ``x``, ``y`` (local),
        ``feature`` (label or '').
        """
        wx = np.atleast_1d(np.asarray(wx, dtype=float))
        wy = np.atleast_1d(np.asarray(wy, dtype=float))
        x, y = self.world_to_local(wx, wy)
        dist = self.distance_to_hole_world(wx, wy)
        n = len(x)
        lie = np.full(n, "rough", dtype=object)
        penalty = np.zeros(n)
        extra = np.zeros(n)
        feature = np.full(n, "", dtype=object)
        ay = np.abs(y)

        # --- Base corridor -------------------------------------------------
        half_fw = self.fairway_width_yards / 2.0
        green_front = self.yards - self.green_depth_yards / 2.0
        green_back = self.yards + self.green_depth_yards / 2.0
        in_fairway_x = (x >= self.fairway_start_yards) & (x < green_front)
        fairway = in_fairway_x & (ay <= half_fw)
        # Apron / run-up short of the green is short grass.
        apron = (x >= green_front - GREEN_APRON_YARDS) & (x < green_front) & (ay <= self.green_width_yards / 2.0)
        lie[fairway | apron] = "fairway"
        # Green: ellipse centred on the hole location.
        gx = (x - self.yards) / max(self.green_depth_yards / 2.0, 1e-6)
        gy = y / max(self.green_width_yards / 2.0, 1e-6)
        r2 = gx * gx + gy * gy
        on_green = r2 <= 1.0
        fringe_r = (1.0 + FRINGE_RING_YARDS / max(min(self.green_depth_yards, self.green_width_yards) / 2.0, 1e-6))
        fringe = (~on_green) & (r2 <= fringe_r * fringe_r)
        lie[fringe] = "fringe"
        lie[on_green] = "green"
        # Rough band vs "deep" rough beyond the maintained corridor.
        beyond = (ay > half_fw + self.rough_width_yards) & ~on_green & ~fringe
        extra[beyond] += DEEP_ROUGH_EXTRA
        # Behind the green is usually the worst miss.
        long_miss = (x > green_back + FRINGE_RING_YARDS) & ~on_green & ~fringe
        extra[long_miss] += 0.15

        # --- Features (higher priority overrides) ---------------------------
        prio = np.zeros(n)
        for f in sorted(self.features, key=lambda f: _KIND_PRIORITY.get(f.kind, 0)):
            mask = f.contains(x, y)
            if not mask.any():
                continue
            p = _KIND_PRIORITY.get(f.kind, 0)
            mask &= prio <= p
            prio[mask] = p
            label = f.label or f.kind.replace("_", " ")
            feature[mask] = label
            if f.kind == "ob":
                lie[mask] = "ob"
                penalty[mask] = 1.0 if f.penalty_strokes is None else f.penalty_strokes
                extra[mask] = 0.0
            elif f.kind in ("water", "creek", "penalty"):
                lie[mask] = "penalty"
                penalty[mask] = 1.0 if f.penalty_strokes is None else f.penalty_strokes
                extra[mask] = 0.0
            elif f.kind == "trees":
                lie[mask] = "recovery"
                extra[mask] = 0.0 if f.penalty_strokes is None else f.penalty_strokes
            elif f.kind == "bunker":
                lie[mask] = "sand"
                extra[mask] = 0.0
            elif f.kind == "native":
                lie[mask] = "rough"
                extra[mask] = NATIVE_EXTRA
            elif f.kind == "deep_rough":
                lie[mask] = "rough"
                extra[mask] = DEEP_ROUGH_EXTRA
        return {"lie": lie, "penalty": penalty, "extra": extra, "dist": dist, "x": x, "y": y, "feature": feature}

    def classify_point(self, x: float, y: float) -> Landing:
        """Classify a single point given in *local* coordinates."""
        wx, wy = self.local_to_world(x, y)
        r = self.classify_world(np.array([wx]), np.array([wy]))
        return Landing(
            lie=str(r["lie"][0]), distance_to_hole=float(r["dist"][0]), penalty_strokes=float(r["penalty"][0]),
            extra_strokes=float(r["extra"][0]), feature=(str(r["feature"][0]) or None), x=float(r["x"][0]), y=float(r["y"][0]),
        )

    # ------------------------------------------------------------------
    # Rendering helpers (for the SVG hole maps in the UI)
    # ------------------------------------------------------------------
    def render_spec(self) -> dict[str, Any]:
        """Geometry in local coordinates the front-end can draw directly.

        The strip is drawn tee-at-bottom, green-at-top: the UI maps local
        ``x`` to the vertical axis and ``y`` to the horizontal axis.
        """
        half_fw = self.fairway_width_yards / 2.0
        return {
            "number": self.number,
            "par": self.par,
            "yards": self.yards,
            "shape": self.shape,
            "dogleg_at_yards": self.dogleg_at_yards if self.has_dogleg else None,
            "dogleg_angle_deg": self.dogleg_angle_deg if self.has_dogleg else None,
            "fairway": {"x0": self.fairway_start_yards, "x1": self.yards - self.green_depth_yards / 2.0,
                        "half_width": half_fw},
            "rough_half_width": half_fw + self.rough_width_yards,
            "green": {"x": self.yards, "width": self.green_width_yards, "depth": self.green_depth_yards},
            "features": [
                {"kind": f.kind, "side": f.side, "start": f.start_yards, "end": f.end_yards,
                 "offset": f.offset_yards, "width": min(f.width_yards, 60.0), "to_edge": f.width_yards >= 60.0,
                 "label": f.label}
                for f in self.features
            ],
        }

    def to_dict(self) -> dict[str, Any]:
        d = {k: getattr(self, k) for k in self.__dataclass_fields__ if k != "features"}
        d["features"] = [f.__dict__.copy() for f in self.features]
        return d
