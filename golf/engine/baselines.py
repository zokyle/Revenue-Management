"""Expected-strokes baseline tables ("strokes gained" benchmarks).

The heart of course strategy is a single question: *from here, how many strokes
does it usually take to hole out?*  Mark Broadie's PGA Tour benchmark tables
answer that for professionals.  This module stores those tables and scales them
to a given handicap so the app has a sensible prior *before* it has learned the
player's own game.  As real shots accumulate, ``golf.engine.learning`` blends the
player's data with these priors (Bayesian shrinkage).

Analogy: the baseline tables are the "factory settings" of the caddie; every
logged shot nudges a dial away from factory settings toward the player's real
game.

Units: distances are yards for full shots and feet for putts.  Values are
strokes-to-hole-out (expected strokes remaining).

Sources: Broadie, *Every Shot Counts* (2014), PGA Tour averages 2003-2012; the
handicap adjustments are parametric fits to the amateur tables in the same book
(90-shooter and 100-shooter benchmarks).
"""

from __future__ import annotations

from enum import Enum

import numpy as np


class Lie(str, Enum):
    TEE = "tee"
    FAIRWAY = "fairway"
    ROUGH = "rough"
    SAND = "sand"
    RECOVERY = "recovery"  # trees / punch-out required
    FRINGE = "fringe"
    GREEN = "green"
    PENALTY = "penalty"  # water / lateral hazard (drop + 1)
    OB = "ob"  # out of bounds (stroke and distance)


# ---------------------------------------------------------------------------
# PGA Tour benchmark: strokes to hole out by lie and distance (yards)
# ---------------------------------------------------------------------------

_TEE_YDS = [100, 120, 140, 160, 180, 200, 220, 240, 260, 280, 300, 320, 340, 360, 380, 400,
            420, 440, 460, 480, 500, 520, 540, 560, 580, 600]
_TEE_ES = [2.92, 2.99, 2.97, 2.99, 3.05, 3.12, 3.17, 3.25, 3.45, 3.65, 3.71, 3.79, 3.86, 3.92,
           3.96, 3.99, 4.02, 4.08, 4.17, 4.28, 4.41, 4.54, 4.65, 4.74, 4.79, 4.82]

_FULL_YDS = [20, 40, 60, 80, 100, 120, 140, 160, 180, 200, 220, 240, 260, 280, 300, 320, 340,
             360, 380, 400, 420, 440, 460, 480, 500, 520, 540, 560, 580, 600]
_FAIRWAY_ES = [2.40, 2.60, 2.70, 2.75, 2.80, 2.85, 2.91, 2.98, 3.08, 3.19, 3.32, 3.45, 3.58,
               3.69, 3.78, 3.84, 3.88, 3.95, 4.03, 4.11, 4.15, 4.20, 4.29, 4.40, 4.53, 4.66,
               4.78, 4.86, 4.94, 5.00]
_ROUGH_ES = [2.59, 2.78, 2.91, 2.96, 3.02, 3.08, 3.15, 3.23, 3.31, 3.42, 3.53, 3.64, 3.74,
             3.83, 3.90, 3.95, 4.02, 4.11, 4.21, 4.30, 4.34, 4.39, 4.48, 4.59, 4.72, 4.85,
             4.97, 5.05, 5.13, 5.19]
_SAND_ES = [2.53, 2.82, 3.15, 3.24, 3.23, 3.21, 3.22, 3.28, 3.40, 3.55, 3.70, 3.84, 3.93,
            4.00, 4.04, 4.12, 4.26, 4.41, 4.55, 4.69, 4.73, 4.78, 4.87, 4.98, 5.11, 5.24,
            5.36, 5.44, 5.52, 5.58]
_RECOVERY_YDS = [100, 120, 140, 160, 180, 200, 220, 240, 260, 280, 300, 320, 340, 360, 380,
                 400, 420, 440, 460, 480, 500, 520, 540, 560, 580, 600]
_RECOVERY_ES = [3.80, 3.78, 3.80, 3.81, 3.82, 3.87, 3.92, 3.97, 4.03, 4.10, 4.20, 4.31, 4.44,
                4.56, 4.66, 4.75, 4.79, 4.84, 4.93, 5.04, 5.17, 5.30, 5.42, 5.50, 5.58, 5.64]

# Putting: feet -> expected putts
_PUTT_FT = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 20, 30, 40, 50, 60, 90]
_PUTT_ES = [1.001, 1.009, 1.053, 1.13, 1.23, 1.34, 1.42, 1.50, 1.56, 1.61, 1.78, 1.87, 1.98,
            2.06, 2.14, 2.21, 2.40]

_TOUR_TABLES: dict[Lie, tuple[list[float], list[float]]] = {
    Lie.TEE: (_TEE_YDS, _TEE_ES),
    Lie.FAIRWAY: (_FULL_YDS, _FAIRWAY_ES),
    Lie.ROUGH: (_FULL_YDS, _ROUGH_ES),
    Lie.SAND: (_FULL_YDS, _SAND_ES),
    Lie.RECOVERY: (_RECOVERY_YDS, _RECOVERY_ES),
}

# Extra strokes an 18-handicap needs versus the Tour benchmark, by lie and
# distance.  Linear in handicap: delta(h) = (h / 18) * gap18.  Fitted to
# Broadie's 90-shooter tables (a 90-shooter is roughly an 18 handicap).
_GAP18_YDS = [20, 50, 100, 150, 200, 250, 300, 400, 500, 600]
_GAP18: dict[Lie, list[float]] = {
    Lie.TEE: [0.40, 0.45, 0.50, 0.55, 0.65, 0.75, 0.85, 1.00, 1.15, 1.25],
    Lie.FAIRWAY: [0.35, 0.40, 0.45, 0.55, 0.70, 0.85, 0.95, 1.10, 1.25, 1.35],
    Lie.ROUGH: [0.45, 0.50, 0.55, 0.65, 0.80, 0.95, 1.05, 1.20, 1.35, 1.45],
    Lie.SAND: [0.65, 0.75, 0.80, 0.85, 0.95, 1.05, 1.15, 1.30, 1.45, 1.55],
    Lie.RECOVERY: [0.50, 0.55, 0.60, 0.70, 0.80, 0.90, 1.00, 1.15, 1.30, 1.40],
}
_PUTT_GAP18_FT = [1, 3, 5, 10, 20, 30, 60, 90]
_PUTT_GAP18 = [0.00, 0.05, 0.12, 0.22, 0.30, 0.36, 0.45, 0.50]


def _interp(x: float, xs: list[float], ys: list[float]) -> float:
    """Linear interpolation with flat extrapolation at both ends."""
    return float(np.interp(x, xs, ys))


def tour_expected_strokes(lie: Lie | str, distance_yards: float) -> float:
    """PGA Tour expected strokes to hole out from ``lie`` at ``distance_yards``.

    For ``Lie.GREEN`` the distance is converted to feet (1 yard = 3 feet).
    ``Lie.FRINGE`` is treated as a green putt from 1.1x the distance (fringe is
    slightly harder than a putt of the same length).
    """
    lie = Lie(lie)
    if lie in (Lie.GREEN, Lie.FRINGE):
        feet = distance_yards * 3.0 * (1.1 if lie is Lie.FRINGE else 1.0)
        return tour_expected_putts(feet)
    if lie is Lie.PENALTY:
        # Penalty area: one stroke plus a drop that is usually a rough lie
        # slightly farther from the hole (drop ~10 yards back).
        return 1.0 + tour_expected_strokes(Lie.ROUGH, distance_yards + 10)
    if lie is Lie.OB:
        # Stroke and distance: re-hit from the same spot (the caller passes
        # the distance of the ORIGINAL shot's starting point).
        return 1.0 + tour_expected_strokes(Lie.TEE if distance_yards > 300 else Lie.FAIRWAY, distance_yards)
    xs, ys = _TOUR_TABLES[lie]
    d = max(distance_yards, 5.0)
    if lie is Lie.RECOVERY and d < xs[0]:
        # Recovery closer than 100 yards: still costs a punch-out.
        return 3.75
    if d < xs[0]:
        # Inside the tabulated minimum (< 20 yds): blend toward a putt.
        return max(tour_expected_putts(d * 3.0) + 0.3, ys[0] - (xs[0] - d) * 0.02)
    return _interp(d, xs, ys)


def tour_expected_putts(distance_feet: float) -> float:
    """PGA Tour expected putts from ``distance_feet``."""
    if distance_feet <= 0.5:
        return 1.0
    return _interp(distance_feet, _PUTT_FT, _PUTT_ES)


def handicap_gap(lie: Lie | str, distance_yards: float, handicap: float) -> float:
    """Extra strokes (vs Tour) a ``handicap`` player needs from this spot."""
    lie = Lie(lie)
    h = max(float(handicap), -5.0)
    if lie in (Lie.GREEN, Lie.FRINGE):
        feet = distance_yards * 3.0
        return (h / 18.0) * _interp(feet, _PUTT_GAP18_FT, _PUTT_GAP18)
    if lie is Lie.PENALTY:
        return handicap_gap(Lie.ROUGH, distance_yards + 10, h)
    if lie is Lie.OB:
        return handicap_gap(Lie.TEE if distance_yards > 300 else Lie.FAIRWAY, distance_yards, h)
    return (h / 18.0) * _interp(distance_yards, _GAP18_YDS, _GAP18[lie])


def expected_strokes(lie: Lie | str, distance_yards: float, handicap: float = 0.0) -> float:
    """Expected strokes to hole out for a player of ``handicap``.

    Examples (approximate):
        >>> round(expected_strokes("fairway", 150, 0), 2)
        2.95
        >>> round(expected_strokes("fairway", 150, 18), 2)
        3.5
        >>> round(expected_strokes("green", 10 / 3, 0), 2)   # 10-foot putt
        1.61
    """
    return tour_expected_strokes(lie, distance_yards) + handicap_gap(lie, distance_yards, handicap)


def expected_putts(distance_feet: float, handicap: float = 0.0) -> float:
    """Expected putts from ``distance_feet`` for a player of ``handicap``."""
    return expected_strokes(Lie.GREEN, distance_feet / 3.0, handicap)


# ---------------------------------------------------------------------------
# Default club distances (carry, yards) by handicap band.  Used as priors
# until a player's own shots take over.
# ---------------------------------------------------------------------------

# (code, name, category, scratch carry, 18-hcp carry, lateral sigma scratch, lateral sigma 18-hcp, distance sigma pct)
DEFAULT_CLUBS: list[dict] = [
    {"code": "D", "name": "Driver", "category": "driver", "carry_0": 275, "carry_18": 225, "lat_0": 16, "lat_18": 26, "dist_sigma_pct": 0.045},
    {"code": "3w", "name": "3 Wood", "category": "wood", "carry_0": 250, "carry_18": 205, "lat_0": 14, "lat_18": 22, "dist_sigma_pct": 0.045},
    {"code": "5w", "name": "5 Wood", "category": "wood", "carry_0": 235, "carry_18": 195, "lat_0": 13, "lat_18": 20, "dist_sigma_pct": 0.045},
    {"code": "3h", "name": "3 Hybrid", "category": "hybrid", "carry_0": 225, "carry_18": 185, "lat_0": 12, "lat_18": 19, "dist_sigma_pct": 0.045},
    {"code": "4i", "name": "4 Iron", "category": "iron", "carry_0": 215, "carry_18": 175, "lat_0": 11, "lat_18": 18, "dist_sigma_pct": 0.045},
    {"code": "5i", "name": "5 Iron", "category": "iron", "carry_0": 205, "carry_18": 165, "lat_0": 10, "lat_18": 17, "dist_sigma_pct": 0.045},
    {"code": "6i", "name": "6 Iron", "category": "iron", "carry_0": 193, "carry_18": 155, "lat_0": 9, "lat_18": 16, "dist_sigma_pct": 0.045},
    {"code": "7i", "name": "7 Iron", "category": "iron", "carry_0": 180, "carry_18": 145, "lat_0": 8, "lat_18": 15, "dist_sigma_pct": 0.045},
    {"code": "8i", "name": "8 Iron", "category": "iron", "carry_0": 168, "carry_18": 135, "lat_0": 8, "lat_18": 14, "dist_sigma_pct": 0.045},
    {"code": "9i", "name": "9 Iron", "category": "iron", "carry_0": 155, "carry_18": 125, "lat_0": 7, "lat_18": 13, "dist_sigma_pct": 0.05},
    {"code": "PW", "name": "Pitching Wedge", "category": "wedge", "carry_0": 140, "carry_18": 112, "lat_0": 6, "lat_18": 11, "dist_sigma_pct": 0.05},
    {"code": "GW", "name": "Gap Wedge", "category": "wedge", "carry_0": 125, "carry_18": 100, "lat_0": 6, "lat_18": 10, "dist_sigma_pct": 0.055},
    {"code": "SW", "name": "Sand Wedge", "category": "wedge", "carry_0": 110, "carry_18": 85, "lat_0": 5, "lat_18": 9, "dist_sigma_pct": 0.06},
    {"code": "LW", "name": "Lob Wedge", "category": "wedge", "carry_0": 90, "carry_18": 70, "lat_0": 5, "lat_18": 8, "dist_sigma_pct": 0.07},
    {"code": "P", "name": "Putter", "category": "putter", "carry_0": 0, "carry_18": 0, "lat_0": 0, "lat_18": 0, "dist_sigma_pct": 0.0},
]


def default_club_prior(code: str, handicap: float) -> dict | None:
    """Prior carry / dispersion for a club code at a given handicap.

    Returns ``{"carry_mean", "carry_sigma", "lateral_sigma", "lateral_bias"}``
    or ``None`` for unknown codes.  Interpolates linearly between the scratch
    and 18-handicap columns (and extrapolates gently beyond them).
    """
    row = next((c for c in DEFAULT_CLUBS if c["code"].lower() == code.lower()), None)
    if row is None:
        return None
    t = min(max(float(handicap), -5.0), 36.0) / 18.0
    carry = row["carry_0"] + (row["carry_18"] - row["carry_0"]) * t
    lat = row["lat_0"] + (row["lat_18"] - row["lat_0"]) * t
    return {
        "carry_mean": round(carry, 1),
        "carry_sigma": round(max(carry * row["dist_sigma_pct"], 3.0), 1),
        "lateral_sigma": round(max(lat, 3.0), 1),
        "lateral_bias": 0.0,
        "category": row["category"],
    }
