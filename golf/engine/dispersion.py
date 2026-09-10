"""Shot dispersion: the "shotgun pattern" model of where a club actually sends the ball.

Every club a golfer owns produces a cloud of outcomes rather than a point.  We
model that cloud as a mixture:

* the **normal swing** - carry ~ N(mean, sigma_carry), lateral ~ N(bias, sigma_lat);
* the **mishit** (fat / thin / top / shank) - a heavy tail that travels only
  55-85 % of the intended carry and sprays wider.  Ignoring this tail is the
  classic way amateurs talk themselves into carrying water they should lay up
  short of.

Wind and elevation are handled by scaling the mean carry, not the sigmas.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# Lateral spread shrinks as a shot gets shorter roughly in proportion to the
# distance (a 60-yard wedge is not sprayed 25 yards wide).
MIN_LATERAL_SIGMA = 3.0
MIN_CARRY_SIGMA = 3.0


@dataclass
class ClubDistribution:
    code: str
    carry_mean: float
    carry_sigma: float
    lateral_sigma: float
    lateral_bias: float = 0.0
    long_bias: float = 0.0        # +long / -short tendency in yards
    p_mishit: float = 0.06
    n_samples: int = 0
    confidence: float = 0.0       # 0..1, how much of this is the player's own data
    category: str = "iron"
    name: str | None = None
    source: str = "prior"         # prior | blended | observed

    def to_dict(self) -> dict:
        return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in self.__dict__.items()}

    @classmethod
    def from_dict(cls, d: dict) -> "ClubDistribution":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def partial(self, target_carry: float) -> "ClubDistribution":
        """A controlled/partial swing aimed at ``target_carry`` yards.

        Only sensible for ``target_carry <= carry_mean``.  Sigmas scale with the
        fraction of a full swing (with floors) because a knock-down shot is
        more repeatable than a full one; the mishit rate is unchanged.
        """
        frac = min(max(target_carry / max(self.carry_mean, 1.0), 0.3), 1.0)
        return ClubDistribution(
            code=self.code, carry_mean=target_carry,
            carry_sigma=max(self.carry_sigma * frac, MIN_CARRY_SIGMA),
            lateral_sigma=max(self.lateral_sigma * frac, MIN_LATERAL_SIGMA),
            lateral_bias=self.lateral_bias * frac, long_bias=self.long_bias * frac,
            p_mishit=self.p_mishit, n_samples=self.n_samples, confidence=self.confidence,
            category=self.category, name=self.name, source=self.source,
        )


@dataclass
class ShotSample:
    carry: np.ndarray
    lateral: np.ndarray
    mishit: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=bool))


def sample_shots(
    dist: ClubDistribution,
    n: int,
    rng: np.random.Generator,
    carry_scale: float = 1.0,
) -> ShotSample:
    """Draw ``n`` (carry, lateral) outcomes in the shot's own frame.

    ``carry`` is along the aim line (yards), ``lateral`` is perpendicular
    (+right).  ``carry_scale`` applies wind/elevation/temperature to the mean.
    """
    n = int(n)
    mean = dist.carry_mean * carry_scale + dist.long_bias
    carry = rng.normal(mean, max(dist.carry_sigma, MIN_CARRY_SIGMA), n)
    lateral = rng.normal(dist.lateral_bias, max(dist.lateral_sigma, MIN_LATERAL_SIGMA), n)
    mishit = rng.random(n) < float(np.clip(dist.p_mishit, 0.0, 0.5))
    k = int(mishit.sum())
    if k:
        carry[mishit] = mean * rng.uniform(0.55, 0.85, k)
        lateral[mishit] = rng.normal(dist.lateral_bias, max(dist.lateral_sigma, MIN_LATERAL_SIGMA) * 1.6, k)
    carry = np.maximum(carry, 5.0)
    return ShotSample(carry=carry, lateral=lateral, mishit=mishit)


def landing_points(
    sample: ShotSample,
    start: tuple[float, float],
    direction: tuple[float, float],
) -> tuple[np.ndarray, np.ndarray]:
    """Convert shot samples into world coordinates.

    ``direction`` is a unit vector; lateral (+right) is the direction rotated
    90 degrees clockwise when looking down the fairway from the tee.
    """
    dx, dy = direction
    # Right of the aim line: rotate direction by -90 deg -> (dy, -dx)?  Our
    # world frame has +y to the right of +x, so "right" of (dx, dy) is (dy, -dx)
    # only when y points left.  Here +y is right, therefore right = (-dy, dx)
    # rotated... keep it explicit: for direction (1, 0) the right side is (0, +1).
    rx, ry = -dy, dx
    wx = start[0] + sample.carry * dx + sample.lateral * rx
    wy = start[1] + sample.carry * dy + sample.lateral * ry
    return wx, wy


def dispersion_ellipse(dist: ClubDistribution, k: float = 1.65) -> dict:
    """Axes of the ellipse holding ~90 % of normal-swing shots (for drawing)."""
    return {
        "carry_mean": round(dist.carry_mean + dist.long_bias, 1),
        "lateral_center": round(dist.lateral_bias, 1),
        "half_depth": round(k * max(dist.carry_sigma, MIN_CARRY_SIGMA), 1),
        "half_width": round(k * max(dist.lateral_sigma, MIN_LATERAL_SIGMA), 1),
    }
