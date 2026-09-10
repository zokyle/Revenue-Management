"""Learning the player's game from logged shots.

Output is a *profile*: a JSON-serialisable dict that the strategy engine,
dashboard and caddie all read.  The learning problem is small-data by nature
(a golfer logs a few hundred shots a season), so every estimate is a
**Bayesian blend** of the player's own numbers with a handicap-based prior:

    blended_mean = (n * sample_mean + k * prior_mean) / (n + k)

where ``k`` is the "prior strength" - the number of real shots it takes before
the player's data outweighs the factory default.  Analogy: a new employee's
performance review starts at the company average and moves toward their own
record as evidence accumulates.

Profile shape (abridged)::

    {
      "player_id": 1, "handicap": 14.2, "rounds": 8, "shots": 412,
      "readiness": {"score": 0.62, "level": "warming", "rounds_needed": 10, ...},
      "clubs": {"D": {"carry_mean": 241.3, "carry_sigma": 13.1, "lateral_sigma": 24.0,
                      "lateral_bias": 6.2, "p_mishit": 0.07, "n_samples": 58, "confidence": 0.74, ...}, ...},
      "expected_strokes": {"fairway": {"100": 2.98, ...}, "rough": {...}, "sand": {...}, "green_ft": {...}},
      "tendencies": {"fir_pct": 0.48, "gir_pct": 0.31, "putts_per_round": 33.1, ...},
      "errors": [{"code": "penalties", "label": "...", "strokes_per_round": 1.9, "advice": "..."}, ...],
      "score_stats": {"avg": 86.4, "best": 81, "trend": [...]}
    }
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date
from typing import Any, Iterable

import numpy as np

from golf.engine import baselines
from golf.engine.baselines import Lie, default_club_prior, expected_strokes
from golf.engine.dispersion import ClubDistribution

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
PRIOR_STRENGTH_CARRY = 8        # shots before own carry data dominates
PRIOR_STRENGTH_SIGMA = 12       # dispersion needs more evidence than the mean
PRIOR_STRENGTH_ES = 6           # per (lie, bucket) cell of the expected-strokes table
PRIOR_STRENGTH_MISHIT = 25
ROUNDS_FOR_READY = 10           # "enough rounds" target the user asked for
SHOTS_PER_CLUB_FOR_READY = 15
MISHIT_TAGS = {"fat", "thin", "top", "shank", "duff"}
FULL_SWING_TYPES = {"tee", "full"}
DISTANCE_BUCKETS = [10, 20, 30, 40, 50, 60, 80, 100, 120, 140, 160, 180, 200, 225, 250, 275, 300, 350, 400, 450, 500, 550]
PUTT_BUCKETS_FT = [2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 40, 50, 60, 80]
STOCK_CARRY_STRENGTH = 3        # a manual "stock carry" counts like this many shots
LIE_CARRY_FACTOR = {"tee": 1.0, "fairway": 1.0, "fringe": 1.0, "rough": 0.93, "sand": 0.85, "recovery": 0.5}


def _bucket(value: float, edges: list[float]) -> float:
    """Snap a distance to the nearest bucket edge."""
    return float(min(edges, key=lambda e: abs(e - value)))


def readiness_level(score: float) -> str:
    if score < 0.25:
        return "cold"
    if score < 0.6:
        return "warming"
    if score < 0.85:
        return "ready"
    return "dialed"


READINESS_MESSAGES = {
    "cold": "Not enough data yet - strategy uses handicap-based defaults. Log full rounds to teach the caddie your game.",
    "warming": "The caddie is learning you. Club distances are starting to reflect your shots; keep logging.",
    "ready": "Enough rounds logged: strategies are built on your own dispersion and tendencies.",
    "dialed": "Your profile is well established. Strategies are highly personalised; keep logging to track improvement.",
}


class ProfileBuilder:
    """Turn ORM rounds/shots into a profile dict.

    The builder is pure Python over plain attributes so it works with ORM
    objects or simple namespaces (handy in tests).
    """

    def __init__(self, player: Any, clubs: Iterable[Any], rounds: Iterable[Any]):
        self.player = player
        self.clubs = list(clubs)
        self.rounds = [r for r in rounds]
        self.handicap = float(getattr(player, "handicap_index", 15.0) or 15.0)

    # ------------------------------------------------------------------
    def build(self) -> dict[str, Any]:
        holes = [h for r in self.rounds for h in (r.holes or [])]
        shots = [s for h in holes for s in (h.shots or [])]
        clubs = self._club_distributions(shots)
        es_table = self._expected_strokes_table(shots)
        tendencies = self._tendencies(holes, shots)
        errors = self._errors(holes, shots, clubs, tendencies)
        score_stats = self._score_stats()
        readiness = self._readiness(len(self.rounds), shots, clubs)
        return {
            "player_id": getattr(self.player, "id", None),
            "player_name": getattr(self.player, "name", ""),
            "handicap": self.handicap,
            "rounds": len(self.rounds),
            "shots": len(shots),
            "readiness": readiness,
            "clubs": {code: d.to_dict() for code, d in clubs.items()},
            "expected_strokes": es_table,
            "tendencies": tendencies,
            "errors": errors,
            "score_stats": score_stats,
        }

    # ------------------------------------------------------------------
    # Clubs
    # ------------------------------------------------------------------
    def _club_distributions(self, shots: list[Any]) -> dict[str, ClubDistribution]:
        by_code: dict[str, list[Any]] = defaultdict(list)
        club_by_id = {c.id: c for c in self.clubs if getattr(c, "id", None) is not None}
        for s in shots:
            if s.shot_type not in FULL_SWING_TYPES:
                continue
            code = s.club_code or (club_by_id.get(s.club_id).code if s.club_id in club_by_id else None)
            if not code:
                continue
            by_code[code].append(s)

        result: dict[str, ClubDistribution] = {}
        codes = [c.code for c in self.clubs if getattr(c, "active", True) and c.category != "putter"]
        for code in codes + [c for c in by_code if c not in codes]:
            club = next((c for c in self.clubs if c.code == code), None)
            prior = default_club_prior(code, self.handicap) or {
                "carry_mean": 150.0, "carry_sigma": 8.0, "lateral_sigma": 14.0, "lateral_bias": 0.0, "category": "iron",
            }
            prior_mean = prior["carry_mean"]
            prior_n = 0.0
            if club is not None and getattr(club, "stock_carry", None):
                # The player's own estimate is decent evidence - count it as a few shots.
                prior_mean = (prior_mean * PRIOR_STRENGTH_CARRY + club.stock_carry * STOCK_CARRY_STRENGTH * 2) / (
                    PRIOR_STRENGTH_CARRY + STOCK_CARRY_STRENGTH * 2
                )
            carries, laterals, longs, mishits = [], [], [], 0
            for s in by_code.get(code, []):
                tag = (s.outcome_tag or "").lower()
                if tag in MISHIT_TAGS:
                    mishits += 1
                    continue  # mishits are modelled as a separate mixture component
                carry = s.carry_yards
                full_swing = True
                if carry is not None:
                    intended = s.intended_carry_yards
                    if intended is not None and intended < 0.97 * prior_mean:
                        full_swing = False
                    carry = float(carry) / LIE_CARRY_FACTOR.get(s.lie_start, 1.0)
                if s.carry_yards is None:
                    # Only a shot where the golfer had at least a full club in
                    # hand teaches us the full carry; a 60-yard lob wedge is a
                    # partial swing, not a data point for LW distance.
                    intended = s.intended_carry_yards
                    if s.start_distance_yards < 0.95 * prior_mean or (intended is not None and intended < 0.97 * prior_mean):
                        full_swing = False
                    elif s.lie_end not in ("penalty", "ob") and s.end_distance_yards is not None:
                        lat = s.lateral_miss_yards or 0.0
                        tag = (s.outcome_tag or "").lower()
                        start, end = s.start_distance_yards, s.end_distance_yards
                        # The ball landed at (carry, lat) in the shot's frame and the
                        # hole sits at (start, 0), so end^2 = (start - carry)^2 + lat^2.
                        # Recover the along-line gap; the sign (short vs long) comes
                        # from the outcome tag, defaulting to "short".
                        along = float(np.sqrt(max(end * end - lat * lat, 0.0)))
                        if tag == "long":
                            carry = start + along
                        elif s.lie_end in ("green", "fringe") and tag != "short":
                            carry = start                   # pin-high-ish: sign unknown, zero is unbiased
                        else:
                            carry = start - along
                        carry = float(np.hypot(carry, lat)) if carry > 0 else None
                        if carry is not None:
                            # A full swing from the rough flies ~7% shorter, sand ~15%:
                            # normalise to the fairway-equivalent carry.
                            carry /= LIE_CARRY_FACTOR.get(s.lie_start, 1.0)
                if full_swing and carry is not None and 20 <= carry <= 400:
                    carries.append(float(carry))
                if s.lateral_miss_yards is not None:
                    laterals.append(float(s.lateral_miss_yards))
                if s.distance_miss_yards is not None:
                    longs.append(float(s.distance_miss_yards))
            n = len(carries)
            n_total = len(by_code.get(code, []))
            k = PRIOR_STRENGTH_CARRY
            if n:
                sample_mean = float(np.mean(carries))
                carry_mean = (n * sample_mean + k * prior_mean) / (n + k)
                sample_sigma = float(np.std(carries, ddof=1)) if n > 1 else prior["carry_sigma"]
                carry_sigma = (max(n - 1, 0) * sample_sigma + PRIOR_STRENGTH_SIGMA * prior["carry_sigma"]) / (
                    max(n - 1, 0) + PRIOR_STRENGTH_SIGMA
                )
            else:
                carry_mean, carry_sigma = prior_mean, prior["carry_sigma"]
            nl = len(laterals)
            if nl:
                lat_bias = (nl * float(np.mean(laterals)) + PRIOR_STRENGTH_CARRY * 0.0) / (nl + PRIOR_STRENGTH_CARRY)
                lat_sd = float(np.std(laterals, ddof=1)) if nl > 1 else prior["lateral_sigma"]
                lat_sigma = (max(nl - 1, 0) * lat_sd + PRIOR_STRENGTH_SIGMA * prior["lateral_sigma"]) / (
                    max(nl - 1, 0) + PRIOR_STRENGTH_SIGMA
                )
            else:
                lat_bias, lat_sigma = 0.0, prior["lateral_sigma"]
            nlong = len(longs)
            long_bias = (nlong * float(np.mean(longs))) / (nlong + PRIOR_STRENGTH_CARRY) if nlong else 0.0
            prior_mishit = 0.02 + 0.004 * max(self.handicap, 0.0)
            p_mishit = (mishits + PRIOR_STRENGTH_MISHIT * prior_mishit) / (n_total + PRIOR_STRENGTH_MISHIT)
            confidence = n_total / (n_total + PRIOR_STRENGTH_CARRY)
            result[code] = ClubDistribution(
                code=code, carry_mean=round(carry_mean, 1), carry_sigma=round(max(carry_sigma, 3.0), 1),
                lateral_sigma=round(max(lat_sigma, 3.0), 1), lateral_bias=round(lat_bias, 1),
                long_bias=round(long_bias, 1), p_mishit=round(float(p_mishit), 3), n_samples=n_total,
                confidence=round(confidence, 2), category=(club.category if club else prior.get("category", "iron")),
                name=(club.name if club else code),
                source="observed" if confidence > 0.7 else ("blended" if n_total else "prior"),
            )
        return result

    # ------------------------------------------------------------------
    # Personal expected-strokes table
    # ------------------------------------------------------------------
    def _expected_strokes_table(self, shots: list[Any]) -> dict[str, dict[str, float]]:
        """Blend observed strokes-to-hole-out with the handicap baseline.

        For each shot we know the lie and distance *before* it and, by walking
        the rest of the hole, how many strokes it actually took to hole out
        from there (including penalties).  That is a direct sample of the
        expected-strokes function.
        """
        samples: dict[tuple[str, float], list[float]] = defaultdict(list)
        # Group shots by hole result so we can count strokes remaining.
        by_hole: dict[int, list[Any]] = defaultdict(list)
        for s in shots:
            by_hole[s.hole_result_id].append(s)
        for hole_shots in by_hole.values():
            hole_shots = sorted(hole_shots, key=lambda s: s.sequence)
            total = sum(1 + (s.penalty_strokes or 0) for s in hole_shots)
            if not hole_shots or not (hole_shots[-1].holed or hole_shots[-1].end_distance_yards == 0):
                continue  # incomplete hole: cannot count strokes to hole out
            used = 0
            for s in hole_shots:
                remaining = total - used
                lie = s.lie_start
                if lie == "tee":
                    lie = "tee"
                if lie in ("green", "fringe"):
                    key = ("green_ft", _bucket(s.start_distance_yards * 3.0, PUTT_BUCKETS_FT))
                else:
                    key = (lie, _bucket(s.start_distance_yards, DISTANCE_BUCKETS))
                samples[key].append(float(remaining))
                used += 1 + (s.penalty_strokes or 0)

        table: dict[str, dict[str, float]] = {}
        for lie in ("tee", "fairway", "rough", "sand", "recovery"):
            table[lie] = {}
            for d in DISTANCE_BUCKETS:
                prior = expected_strokes(lie, d, self.handicap)
                obs = samples.get((lie, float(d)), [])
                n = len(obs)
                val = (n * float(np.mean(obs)) + PRIOR_STRENGTH_ES * prior) / (n + PRIOR_STRENGTH_ES) if n else prior
                table[lie][str(d)] = round(val, 3)
        table["green_ft"] = {}
        for ft in PUTT_BUCKETS_FT:
            prior = baselines.expected_putts(ft, self.handicap)
            obs = samples.get(("green_ft", float(ft)), [])
            n = len(obs)
            val = (n * float(np.mean(obs)) + PRIOR_STRENGTH_ES * prior) / (n + PRIOR_STRENGTH_ES) if n else prior
            table["green_ft"][str(ft)] = round(val, 3)
        table["_samples"] = {f"{k[0]}:{int(k[1])}": len(v) for k, v in samples.items()}
        return table

    # ------------------------------------------------------------------
    # Tendencies & errors
    # ------------------------------------------------------------------
    def _tendencies(self, holes: list[Any], shots: list[Any]) -> dict[str, Any]:
        n_rounds = max(len(self.rounds), 1)
        par45 = [h for h in holes if h.par >= 4]
        fir = [h.fairway_hit for h in par45 if h.fairway_hit is not None]
        gir = [h.gir for h in holes if h.gir is not None]
        putts = [h.putts for h in holes if h.putts is not None]
        three_putts = sum(1 for p in putts if p >= 3)
        penalties = sum(h.penalties or 0 for h in holes)
        scores_vs_par = [h.score - h.par for h in holes]
        doubles = sum(1 for d in scores_vs_par if d >= 2)
        birdies = sum(1 for d in scores_vs_par if d <= -1)
        pars = sum(1 for d in scores_vs_par if d == 0)
        bogeys = sum(1 for d in scores_vs_par if d == 1)
        tee_misses = defaultdict(int)
        for h in par45:
            if h.tee_miss and h.tee_miss != "none":
                tee_misses[h.tee_miss] += 1
        for s in shots:
            if s.shot_type == "tee" and s.lateral_miss_yards is not None and abs(s.lateral_miss_yards) > 15:
                tee_misses["right" if s.lateral_miss_yards > 0 else "left"] += 1
        # Approach proximity: full shots that finished on the green.
        prox = [s.end_distance_yards * 3 for s in shots if s.shot_type in FULL_SWING_TYPES and s.lie_end == "green" and s.lie_start != "tee"]
        # Short-siding: chips/pitches that ended > 10 ft or off green.
        short_game = [s for s in shots if s.shot_type in ("pitch", "chip", "bunker")]
        sg_inside_10 = sum(1 for s in short_game if s.lie_end == "green" and s.end_distance_yards * 3 <= 10)
        holes_by_par = defaultdict(list)
        for h in holes:
            holes_by_par[h.par].append(h.score - h.par)
        return {
            "fir_pct": round(sum(1 for f in fir if f) / len(fir), 3) if fir else None,
            "gir_pct": round(sum(1 for g in gir if g) / len(gir), 3) if gir else None,
            "putts_per_round": round(sum(putts) / n_rounds, 1) if putts else None,
            "three_putt_pct": round(three_putts / len(putts), 3) if putts else None,
            "penalties_per_round": round(penalties / n_rounds, 2),
            "doubles_or_worse_per_round": round(doubles / n_rounds, 2),
            "birdies_per_round": round(birdies / n_rounds, 2),
            "pars_per_round": round(pars / n_rounds, 2),
            "bogeys_per_round": round(bogeys / n_rounds, 2),
            "tee_miss_direction": dict(tee_misses),
            "dominant_miss": (max(tee_misses, key=tee_misses.get) if tee_misses else getattr(self.player, "dominant_miss", None)),
            "approach_proximity_ft": round(float(np.mean(prox)), 1) if prox else None,
            "short_game_inside_10ft_pct": round(sg_inside_10 / len(short_game), 3) if short_game else None,
            "avg_vs_par_by_par": {str(p): round(float(np.mean(v)), 2) for p, v in sorted(holes_by_par.items())},
            "holes_played": len(holes),
        }

    def _errors(self, holes: list[Any], shots: list[Any], clubs: dict[str, ClubDistribution], t: dict[str, Any]) -> list[dict[str, Any]]:
        """Rank the player's costliest habits in strokes per round."""
        n_rounds = max(len(self.rounds), 1)
        errors: list[dict[str, Any]] = []

        pen = t.get("penalties_per_round") or 0.0
        if pen > 0:
            errors.append({
                "code": "penalties", "label": "Penalty strokes",
                "strokes_per_round": round(pen * 1.0, 2),
                "detail": f"{pen:.1f} penalty strokes per round.",
                "advice": "Every penalty is a full shot gone. Strategy will aim away from water/OB even at the cost of a longer approach.",
            })
        # Tee shots into trouble (recovery / penalty / ob) by club.
        trouble = defaultdict(int)
        tee_count = defaultdict(int)
        for s in shots:
            if s.shot_type == "tee":
                code = s.club_code or "?"
                tee_count[code] += 1
                if s.lie_end in ("recovery", "penalty", "ob"):
                    trouble[code] += 1
        for code, k in trouble.items():
            n = tee_count[code]
            if n >= 5 and k / n >= 0.15:
                cost = k / n_rounds * 0.9
                errors.append({
                    "code": f"tee_trouble_{code}", "label": f"{code} off the tee finds trouble",
                    "strokes_per_round": round(cost, 2),
                    "detail": f"{k} of {n} {code} tee shots ended in trees, water or OB ({k / n:.0%}).",
                    "advice": f"Consider a shorter club off the tee on tight holes; the plan will compare {code} against safer options hole by hole.",
                })
        three = t.get("three_putt_pct")
        if three and three > 0.08:
            per_round = three * 18
            errors.append({
                "code": "three_putts", "label": "Three-putts",
                "strokes_per_round": round(per_round * 1.0, 2),
                "detail": f"Three-putting {three:.0%} of holes (~{per_round:.1f} per round).",
                "advice": "Lag putting: from 30+ feet the goal is a 3-foot circle, not the hole.",
            })
        sg = t.get("short_game_inside_10ft_pct")
        if sg is not None and sg < 0.45:
            errors.append({
                "code": "short_game", "label": "Chips and pitches leave long putts",
                "strokes_per_round": round((0.6 - sg) * 6 * 0.35, 2),
                "detail": f"Only {sg:.0%} of chips/pitches finish inside 10 feet.",
                "advice": "Approach strategy will favour the fat side of greens so misses leave simple chips.",
            })
        prox = t.get("approach_proximity_ft")
        if prox and prox > 40:
            errors.append({
                "code": "approach_long_left", "label": "Approach shots finish far from the hole",
                "strokes_per_round": round((prox - 35) / 40 * 1.5, 2),
                "detail": f"Average approach proximity {prox:.0f} ft.",
                "advice": "Aim at the middle of the green rather than the flag; take one more club when the miss is short.",
            })
        # Long/short bias worth a club.
        for code, d in clubs.items():
            if d.n_samples >= 8 and abs(d.long_bias) >= 6:
                errors.append({
                    "code": f"distance_bias_{code}", "label": f"{code} flies {'long' if d.long_bias > 0 else 'short'} of the target",
                    "strokes_per_round": round(abs(d.long_bias) / 10 * 0.25, 2),
                    "detail": f"Average {abs(d.long_bias):.0f} yards {'long' if d.long_bias > 0 else 'short'} over {d.n_samples} shots.",
                    "advice": f"Your real {code} number is {d.carry_mean + d.long_bias:.0f} yards - use it, not the number you wish it were.",
                })
            if d.n_samples >= 8 and abs(d.lateral_bias) >= 8:
                errors.append({
                    "code": f"lateral_bias_{code}", "label": f"{code} misses {'right' if d.lateral_bias > 0 else 'left'}",
                    "strokes_per_round": round(abs(d.lateral_bias) / 10 * 0.3, 2),
                    "detail": f"Average miss {abs(d.lateral_bias):.0f} yards {'right' if d.lateral_bias > 0 else 'left'}.",
                    "advice": "Aim points already account for this bias: trust the aim line even when it looks wrong.",
                })
        dbl = t.get("doubles_or_worse_per_round") or 0
        if dbl >= 2:
            errors.append({
                "code": "blowups", "label": "Double bogeys or worse",
                "strokes_per_round": round(dbl * 1.0, 2),
                "detail": f"{dbl:.1f} doubles-or-worse per round. Breaking 80 usually means at most one.",
                "advice": "The plan minimises double-bogey probability first, birdie chances second.",
            })
        errors.sort(key=lambda e: e["strokes_per_round"], reverse=True)
        return errors[:8]

    # ------------------------------------------------------------------
    def _score_stats(self) -> dict[str, Any]:
        finished = [r for r in self.rounds if r.total_score]
        finished.sort(key=lambda r: (r.played_on or date.min))
        scores = [r.total_score for r in finished]
        target = int(getattr(self.player, "target_score", 79) or 79)
        return {
            "avg": round(float(np.mean(scores)), 1) if scores else None,
            "best": min(scores) if scores else None,
            "last5_avg": round(float(np.mean(scores[-5:])), 1) if scores else None,
            "rounds_under_target": sum(1 for s in scores if s <= target),
            "target": target,
            "trend": [{"date": (r.played_on.isoformat() if r.played_on else None), "score": r.total_score} for r in finished[-20:]],
        }

    def _readiness(self, n_rounds: int, shots: list[Any], clubs: dict[str, ClubDistribution]) -> dict[str, Any]:
        full_swings = [s for s in shots if s.shot_type in FULL_SWING_TYPES]
        core = [c for c in clubs.values() if c.category in ("driver", "wood", "hybrid", "iron", "wedge")]
        club_cov = float(np.mean([min(c.n_samples / SHOTS_PER_CLUB_FOR_READY, 1.0) for c in core])) if core else 0.0
        # A round logged shot-by-shot teaches twice what a quick scorecard does.
        credited = sum(1.0 if any((h.shots or []) for h in (r.holes or [])) else 0.5 for r in self.rounds)
        round_cov = min(credited / ROUNDS_FOR_READY, 1.0)
        shot_cov = min(len(full_swings) / (ROUNDS_FOR_READY * 30), 1.0)
        score = round(0.4 * round_cov + 0.35 * club_cov + 0.25 * shot_cov, 3)
        # "Enough rounds" is a hard gate: you cannot be READY on two great rounds.
        if n_rounds < ROUNDS_FOR_READY * 0.6:
            score = min(score, 0.59)
        if n_rounds < 3:
            score = min(score, 0.24)
        level = readiness_level(score)
        weakest = sorted(core, key=lambda c: c.n_samples)[:3]
        return {
            "score": score,
            "level": level,
            "message": READINESS_MESSAGES[level],
            "rounds_logged": n_rounds,
            "rounds_credited": round(credited, 1),
            "rounds_needed": ROUNDS_FOR_READY,
            "full_swings_logged": len(full_swings),
            "club_coverage": round(club_cov, 2),
            "clubs_needing_data": [{"code": c.code, "shots": c.n_samples, "needed": SHOTS_PER_CLUB_FOR_READY} for c in weakest if c.n_samples < SHOTS_PER_CLUB_FOR_READY],
        }


def club_distributions_from_profile(profile: dict[str, Any]) -> dict[str, ClubDistribution]:
    return {code: ClubDistribution.from_dict(d) for code, d in (profile.get("clubs") or {}).items()}


def personal_expected_strokes(profile: dict[str, Any], lie: str, distance_yards: float) -> float:
    """Look up the player's expected strokes from the profile table (interpolated)."""
    table = profile.get("expected_strokes") or {}
    handicap = float(profile.get("handicap", 15.0))
    if lie in ("green", "fringe"):
        feet = distance_yards * 3.0 * (1.1 if lie == "fringe" else 1.0)
        row = table.get("green_ft")
        if not row:
            return baselines.expected_putts(feet, handicap)
        xs = np.array([float(k) for k in row])
        ys = np.array([row[k] for k in row])
        order = np.argsort(xs)
        if feet <= 0.5:
            return 1.0
        return float(np.interp(feet, xs[order], ys[order]))
    if lie == "penalty":
        return 1.0 + personal_expected_strokes(profile, "rough", distance_yards + 10)
    if lie == "ob":
        return 1.0 + personal_expected_strokes(profile, "tee" if distance_yards > 300 else "fairway", distance_yards)
    row = table.get(lie)
    if not row:
        return expected_strokes(lie, distance_yards, handicap)
    xs = np.array([float(k) for k in row])
    ys = np.array([row[k] for k in row])
    order = np.argsort(xs)
    d = max(distance_yards, 5.0)
    if d < xs.min():
        return baselines.expected_strokes(lie, d, handicap)
    return float(np.interp(d, xs[order], ys[order]))
