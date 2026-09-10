"""The strategy optimizer: hole-by-hole game plans built from the player's own
shot patterns.

How it thinks (the casino analogy)
----------------------------------
A casino does not know the outcome of any single hand, but it knows the
*distribution* and so it always makes the play with the best expected value.
For every hole we do the same: for each candidate tee shot (club x aim point)
we throw the player's real dispersion pattern at the hole several hundred
times, play out the rest of the hole with a sensible policy, and read off the
distribution of scores.  We then pick the plan with the lowest

    objective = E[strokes] + lambda * P(double bogey or worse)

``lambda`` grows as the player's risk tolerance shrinks.  Breaking 80 is mostly
about killing the blow-up holes, so a modest ``lambda`` is on by default.

All geometry is in yards (see ``golf.engine.hole_model``); putting distances
are converted to feet only inside the expected-strokes lookup.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from golf.engine.baselines import DEFAULT_CLUBS, default_club_prior
from golf.engine.dispersion import ClubDistribution, MIN_CARRY_SIGMA, MIN_LATERAL_SIGMA, dispersion_ellipse
from golf.engine.hole_model import HoleGeometry
from golf.engine.learning import club_distributions_from_profile, personal_expected_strokes

AIM_OFFSETS = [-20.0, -15.0, -10.0, -5.0, 0.0, 5.0, 10.0, 15.0, 20.0]
GREEN_AIM_FRACTIONS = [-0.3, 0.0, 0.3]      # fraction of green half-width
LIE_CARRY_FACTOR = {"tee": 1.0, "fairway": 1.0, "fringe": 1.0, "rough": 0.93, "sand": 0.85, "recovery": 0.5, "green": 1.0}
SEARCH_SAMPLES = 300
FINAL_SAMPLES = 1500
# Strokes-to-hole-out is right-skewed with variance growing with its mean:
# var ~ a + b * (mean - 1).  Calibrated so a 15-handicap from 150 yds in the
# fairway (mean 3.4) holes out in 2 about 14%, in 5+ about 12%, and a 20-ft
# putt (mean 1.85) is a one-putt ~24% / three-putt ~10% of the time.
RESIDUAL_VAR = {"green": (0.12, 0.15), "fringe": (0.14, 0.15)}
DEFAULT_RESIDUAL_VAR = (0.25, 0.18)
DISASTER_TAIL = 0.03   # chance of an extra stroke (chunk, lost ball, four-putt) on non-green residuals
MAX_SIM_STAGES = 3
AIM_REGULARISATION = 0.002    # strokes per yard of aim offset: break ties toward the centre
CONTINGENCY_SHARE = 0.10


@dataclass
class Candidate:
    club: str
    target_x: float          # local x of the aim point (yards along the hole)
    target_y: float          # local y of the aim point (+ right)
    label: str               # "full" | "layup" | "partial"
    carry: float             # intended carry


class StrategyEngine:
    """Build strategy plans from a profile dict (see ``ProfileBuilder``)."""

    def __init__(
        self,
        profile: dict[str, Any],
        n_samples: int = SEARCH_SAMPLES,
        seed: int = 7,
        risk_tolerance: float | None = None,
        target_score: int | None = None,
    ):
        self.profile = profile
        self.n = int(n_samples)
        self.seed = int(seed)
        self.handicap = float(profile.get("handicap", 15.0) or 15.0)
        rt = 0.35 if risk_tolerance is None else float(risk_tolerance)
        self.risk_tolerance = min(max(rt, 0.0), 1.0)
        self.lam = round(0.8 * (1.0 - self.risk_tolerance), 3)
        self.target_score = int(target_score or 79)
        clubs = club_distributions_from_profile(profile)
        if not clubs:
            clubs = self._default_bag()
        self.clubs: dict[str, ClubDistribution] = {
            c: d for c, d in clubs.items() if d.category != "putter" and d.carry_mean > 0
        }
        self.club_order = sorted(self.clubs, key=lambda c: -self.clubs[c].carry_mean)
        self.max_carry = self.clubs[self.club_order[0]].carry_mean if self.club_order else 200.0
        self.min_full_carry = self.clubs[self.club_order[-1]].carry_mean if self.club_order else 70.0
        self.readiness = float((profile.get("readiness") or {}).get("score", 0.0))

    # ------------------------------------------------------------------
    def _default_bag(self) -> dict[str, ClubDistribution]:
        out = {}
        for code in ["D", "3w", "5w", "4i", "5i", "6i", "7i", "8i", "9i", "PW", "GW", "SW", "LW"]:
            p = default_club_prior(code, self.handicap)
            name = next((c["name"] for c in DEFAULT_CLUBS if c["code"] == code), code)
            out[code] = ClubDistribution(code=code, carry_mean=p["carry_mean"], carry_sigma=p["carry_sigma"],
                                         lateral_sigma=p["lateral_sigma"], category=p["category"], name=name,
                                         p_mishit=0.02 + 0.004 * max(self.handicap, 0))
        return out

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def plan_course(self, holes: list[HoleGeometry], conditions: dict[str, Any] | None = None) -> dict[str, Any]:
        conditions = conditions or {}
        plans = [self.plan_hole(h, conditions) for h in holes]
        n = FINAL_SAMPLES
        rng = np.random.default_rng(self.seed + 999)
        total = np.zeros(n)
        for p in plans:
            dist = p["score_distribution"]
            outcomes = np.array([-2, -1, 0, 1, 2, 3])
            probs = np.array([dist["eagle"], dist["birdie"], dist["par"], dist["bogey"], dist["double"], dist["triple_plus"]])
            probs = probs / probs.sum()
            total += p["par"] + rng.choice(outcomes, size=n, p=probs)
        par = sum(h.par for h in holes)
        exp = float(np.mean(total)) if holes else 0.0
        return {
            "par": par,
            "expected_score": round(exp, 1),
            "expected_vs_par": round(exp - par, 1),
            "p_break_target": round(float(np.mean(total <= self.target_score)), 3) if holes else None,
            "target_score": self.target_score,
            "score_percentiles": {
                "p10": int(np.percentile(total, 10)) if holes else None,
                "p50": int(np.percentile(total, 50)) if holes else None,
                "p90": int(np.percentile(total, 90)) if holes else None,
            },
            "expected_penalties": round(sum(p["tee"]["landing_mix"].get("penalty", 0) + p["tee"]["landing_mix"].get("ob", 0) for p in plans), 2),
            "p_break_target_note": "Holes are simulated independently; on a real day form carries between holes, so a hot round is a little more likely than this number says.",
            "risk_lambda": self.lam,
            "readiness": self.readiness,
            "holes": plans,
            "summary": self._course_summary(plans, exp, par),
        }

    def plan_hole(self, geom: HoleGeometry, conditions: dict[str, Any] | None = None) -> dict[str, Any]:
        conditions = conditions or {}
        carry_scale = float(conditions.get("carry_scale", 1.0))
        candidates = self._tee_candidates(geom)
        results = []
        for c in candidates:
            # Common random numbers: every candidate sees the same draws, so
            # differences between candidates are real, not sampling noise.
            rng = np.random.default_rng(self.seed * 1000 + geom.number)
            sim = self._simulate(geom, c, self.n, rng, carry_scale)
            obj = self._objective(sim, geom.par) + AIM_REGULARISATION * abs(c.target_y)
            results.append((obj, c, sim))
        results.sort(key=lambda r: r[0])
        best_obj, best, _ = results[0]
        # Re-simulate the winner with more samples for a stable distribution.
        final = self._simulate(geom, best, FINAL_SAMPLES, np.random.default_rng(self.seed * 1000 + geom.number + 500), carry_scale)
        alternatives = self._alternatives(results, best, geom.par)
        plan = self._describe(geom, best, final, alternatives)
        plan["objective"] = round(best_obj, 3)
        return plan

    # ------------------------------------------------------------------
    # Candidate generation
    # ------------------------------------------------------------------
    def _tee_candidates(self, geom: HoleGeometry) -> list[Candidate]:
        yards = geom.playing_yards
        cands: list[Candidate] = []
        if geom.par == 3:
            # Club that fits the distance, plus one more and one less; aim across the green.
            half_w = geom.green_width_yards / 2.0
            fits = sorted(self.club_order, key=lambda c: abs(self.clubs[c].carry_mean - yards))[:3]
            for code in fits:
                d = self.clubs[code]
                for frac in GREEN_AIM_FRACTIONS:
                    cands.append(Candidate(code, geom.yards, frac * half_w, "full", d.carry_mean))
            # A controlled shot to the exact number with the next-longer club.
            longer = [c for c in self.club_order if self.clubs[c].carry_mean >= yards]
            if longer:
                code = longer[-1]
                cands.append(Candidate(code, geom.yards, 0.0, "partial", yards))
            return cands
        # Par 4 / 5: full swings with every club that goes far enough to matter.
        for code in self.club_order:
            d = self.clubs[code]
            if d.carry_mean < 140:
                continue
            if d.carry_mean > yards + 15:
                continue
            target_x = min(d.carry_mean, geom.yards)
            for off in AIM_OFFSETS:
                cands.append(Candidate(code, target_x, off, "full", d.carry_mean))
        # Layups short of cross hazards and doglegs.
        layup_xs = []
        for f in geom.features:
            if f.side == "center" and f.kind in ("water", "creek", "penalty", "bunker", "ob") and f.start_yards > 120:
                layup_xs.append(f.start_yards - 12)
        if geom.has_dogleg:
            layup_xs.append(geom.dogleg_at_yards - 8)
        for lx in layup_xs:
            if lx < 120 or lx > self.max_carry:
                continue
            # Use the club whose full carry is just short of the target, else a partial swing.
            shorter = [c for c in self.club_order if self.clubs[c].carry_mean <= lx]
            code = shorter[0] if shorter else self.club_order[-1]
            d = self.clubs[code]
            carry = min(d.carry_mean, lx)
            for off in (-8.0, 0.0, 8.0):
                cands.append(Candidate(code, carry, off, "layup", carry))
        return cands

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------
    def _simulate(self, geom: HoleGeometry, cand: Candidate, n: int, rng: np.random.Generator, carry_scale: float) -> dict[str, Any]:
        """Roll the hole out ``n`` times starting with ``cand`` off the tee."""
        n = int(n)
        strokes = np.zeros(n)
        resolved = np.zeros(n, dtype=bool)
        club = self.clubs[cand.club]
        if cand.label in ("layup", "partial") and cand.carry < club.carry_mean:
            club = club.partial(cand.carry)
        # --- Tee shot -------------------------------------------------------
        direction = geom.aim_direction((0.0, 0.0), (cand.target_x, cand.target_y))
        carry, lateral, mishit = self._draw(club, n, rng, carry_scale)
        wx, wy = self._land((np.zeros(n), np.zeros(n)), direction, carry, lateral)
        r = geom.classify_world(wx, wy)
        lie = r["lie"].copy()
        extra = r["extra"].copy()  # lie-quality surcharge, applied when the sample is valued
        strokes += 1.0 + r["penalty"]
        tee_lie = lie.copy()
        tee_feature = r["feature"].copy()
        tee_x, tee_y = r["x"].copy(), r["y"].copy()
        # OB: stroke and distance - value the re-tee with the ES table.
        ob = lie == "ob"
        if ob.any():
            strokes[ob] += self._residual("tee", np.full(int(ob.sum()), geom.playing_yards), rng)
            extra[ob] = 0.0
            resolved[ob] = True
        # Penalty area: drop near the point of entry, in the rough.
        pen = lie == "penalty"
        if pen.any():
            wx, wy, lie = self._drop(geom, r, pen, wx, wy, lie)
        dist = geom.distance_to_hole_world(wx, wy)

        approach_dist_samples = []
        approach_lies = []
        approached = np.zeros(n, dtype=bool)  # samples that have taken a shot at the green
        gir = np.zeros(n, dtype=bool)
        stage_records: list[dict[str, Any]] = []
        for stage in range(MAX_SIM_STAGES):
            active = ~resolved
            if not active.any():
                break
            idx = np.nonzero(active)[0]
            # Recovery: punch out sideways/forward, one stroke, then continue.
            rec = idx[lie[idx] == "recovery"]
            if rec.size:
                strokes[rec] += 1.0
                lx, ly = geom.world_to_local(wx[rec], wy[rec])
                adv = rng.uniform(40, 90, rec.size)
                nx = np.minimum(lx + adv, geom.yards - 25)
                ny = ly * rng.uniform(0.0, 0.35, rec.size)
                w = np.array([geom.local_to_world(a, b) for a, b in zip(nx, ny)])
                wx[rec], wy[rec] = w[:, 0], w[:, 1]
                rr = geom.classify_world(wx[rec], wy[rec])
                lie[rec] = rr["lie"]
                extra[rec] = rr["extra"]
                strokes[rec] += rr["penalty"]
                dist[rec] = rr["dist"]
                # Anything nasty again (e.g. still in trees) -> value with the table.
                bad = rec[(lie[rec] == "recovery") | (lie[rec] == "ob") | (lie[rec] == "penalty")]
                if bad.size:
                    strokes[bad] += self._residual_mixed(lie[bad], dist[bad], rng, extra[bad])
                    resolved[bad] = True
            idx = np.nonzero(~resolved)[0]
            if idx.size == 0:
                break
            # On/around the green -> resolve with the table (putting / chipping).
            near = idx[np.isin(lie[idx], ["green", "fringe"]) | (dist[idx] <= 30)]
            if near.size:
                strokes[near] += self._residual_mixed(lie[near], dist[near], rng, extra[near])
                resolved[near] = True
            idx = np.nonzero(~resolved)[0]
            if idx.size == 0:
                break
            # Full shot toward the green (or a layup if out of range).
            lie_factor = np.array([LIE_CARRY_FACTOR.get(l, 0.9) for l in lie[idx]])
            reach = dist[idx] <= self.max_carry * lie_factor + 12
            if reach.any():
                first = reach & ~approached[idx]
                approach_dist_samples.extend(dist[idx][first].tolist())
                approach_lies.extend(lie[idx][first].tolist())
                approached[idx[reach]] = True
            # --- Approach: pick a club per sample, aim at the safe part of the green.
            if reach.any():
                a_idx = idx[reach]
                a_dist = dist[a_idx] / lie_factor[reach]
                club_idx, carry_mean, carry_sig, lat_sig, lat_bias, p_mis = self._club_for_distance(a_dist)
                aim_y = self._green_aim(geom)
                tx, ty = geom.local_to_world(geom.yards, aim_y)
                dx, dy = tx - wx[a_idx], ty - wy[a_idx]
                norm = np.hypot(dx, dy)
                norm[norm == 0] = 1.0
                dirs = (dx / norm, dy / norm)
                c, l, m = self._draw_vec(carry_mean * carry_scale, carry_sig, lat_sig, lat_bias, p_mis, rng)
                nwx, nwy = self._land((wx[a_idx], wy[a_idx]), dirs, c, l)
                rr = geom.classify_world(nwx, nwy)
                wx[a_idx], wy[a_idx] = nwx, nwy
                lie[a_idx] = rr["lie"]
                extra[a_idx] = rr["extra"]
                strokes[a_idx] += 1.0 + rr["penalty"]
                dist[a_idx] = rr["dist"]
                gir[a_idx] = (rr["lie"] == "green") & (strokes[a_idx] <= geom.par - 2)
                pen2 = a_idx[rr["lie"] == "penalty"]
                if pen2.size:
                    sub = geom.classify_world(wx[pen2], wy[pen2])
                    mask = np.ones(pen2.size, dtype=bool)
                    nwx2, nwy2, nl = self._drop(geom, sub, mask, wx[pen2].copy(), wy[pen2].copy(), lie[pen2].copy())
                    wx[pen2], wy[pen2], lie[pen2] = nwx2, nwy2, nl
                    dist[pen2] = geom.distance_to_hole_world(wx[pen2], wy[pen2])
                ob2 = a_idx[rr["lie"] == "ob"]
                if ob2.size:
                    # Replay from the previous spot: approximate with table value from there.
                    strokes[ob2] += self._residual_mixed(np.full(ob2.size, "fairway", dtype=object), a_dist[rr["lie"] == "ob"], rng)
                    extra[ob2] = 0.0
                    resolved[ob2] = True
                stage_records.append({"stage": stage, "kind": "approach", "n": int(a_idx.size),
                                      "median_dist": float(np.median(a_dist)) if a_idx.size else None,
                                      "club_mode": self._mode_club(club_idx)})
            # --- Layup / advance for the rest: simulate both options, keep the better one.
            if (~reach).any():
                l_idx = idx[~reach]
                l_dist = dist[l_idx]
                lx, ly = geom.world_to_local(wx[l_idx], wy[l_idx])
                lie_fac = np.array([LIE_CARRY_FACTOR.get(x, 0.9) for x in lie[l_idx]])
                options = self._layup_options(geom, l_dist)
                best_opt = None
                for opt in options:
                    code, carry_target = opt["club"], opt["carry"]
                    club_o = self.clubs[code]
                    cl = club_o.partial(carry_target) if carry_target < club_o.carry_mean else club_o
                    target_local_x = np.minimum(lx + carry_target, geom.yards - 5)
                    tw = np.array([geom.local_to_world(a, 0.0) for a in target_local_x])
                    dx, dy = tw[:, 0] - wx[l_idx], tw[:, 1] - wy[l_idx]
                    norm = np.hypot(dx, dy)
                    norm[norm == 0] = 1.0
                    dirs = (dx / norm, dy / norm)
                    c, l, m = self._draw(cl, l_idx.size, rng, carry_scale * lie_fac)
                    nwx, nwy = self._land((wx[l_idx], wy[l_idx]), dirs, c, l)
                    rr = geom.classify_world(nwx, nwy)
                    # Expected value of the position after this shot (no further sampling).
                    val = 1.0 + rr["penalty"] + self._expected_value_mixed(rr["lie"], rr["dist"], rr["extra"])
                    ob_m = rr["lie"] == "ob"
                    if ob_m.any():
                        val[ob_m] = 2.0 + self._expected_value_mixed(np.full(int(ob_m.sum()), "fairway", dtype=object), l_dist[ob_m], np.zeros(int(ob_m.sum())))
                    score = float(np.mean(val)) + self.lam * float(np.mean(val >= 3.5))
                    if best_opt is None or score < best_opt["score"]:
                        best_opt = {"score": score, "kind": opt["kind"], "club": code, "carry": carry_target,
                                    "wx": nwx, "wy": nwy, "rr": rr}
                rr = best_opt["rr"]
                nwx, nwy = best_opt["wx"], best_opt["wy"]
                wx[l_idx], wy[l_idx] = nwx, nwy
                lie[l_idx] = rr["lie"]
                extra[l_idx] = rr["extra"]
                strokes[l_idx] += 1.0 + rr["penalty"]
                dist[l_idx] = rr["dist"]
                pen3 = l_idx[rr["lie"] == "penalty"]
                if pen3.size:
                    sub = geom.classify_world(wx[pen3], wy[pen3])
                    mask = np.ones(pen3.size, dtype=bool)
                    nwx3, nwy3, nl = self._drop(geom, sub, mask, wx[pen3].copy(), wy[pen3].copy(), lie[pen3].copy())
                    wx[pen3], wy[pen3], lie[pen3] = nwx3, nwy3, nl
                    dist[pen3] = geom.distance_to_hole_world(wx[pen3], wy[pen3])
                ob3 = l_idx[rr["lie"] == "ob"]
                if ob3.size:
                    strokes[ob3] += self._residual_mixed(np.full(ob3.size, "fairway", dtype=object), l_dist[rr["lie"] == "ob"], rng)
                    extra[ob3] = 0.0
                    resolved[ob3] = True
                stage_records.append({"stage": stage, "kind": best_opt["kind"], "n": int(l_idx.size), "club": best_opt["club"],
                                      "carry": float(best_opt["carry"]), "median_dist": float(np.median(l_dist))})
        # Anything still unresolved: value with the table.
        left = ~resolved
        if left.any():
            strokes[left] += self._residual_mixed(lie[left], dist[left], rng, extra[left])
        return {
            "strokes": strokes,
            "tee_lie": tee_lie,
            "tee_feature": tee_feature,
            "tee_x": tee_x,
            "tee_y": tee_y,
            "mishit": mishit,
            "approach_dists": approach_dist_samples,
            "approach_lies": approach_lies,
            "gir": gir,
            "stages": stage_records,
        }

    # ------------------------------------------------------------------
    # Simulation helpers
    # ------------------------------------------------------------------
    def _draw(self, club: ClubDistribution, n: int, rng: np.random.Generator, carry_scale):
        mean = (club.carry_mean + club.long_bias) * carry_scale
        carry = rng.normal(mean, max(club.carry_sigma, MIN_CARRY_SIGMA), n)
        lateral = rng.normal(club.lateral_bias, max(club.lateral_sigma, MIN_LATERAL_SIGMA), n)
        mishit = rng.random(n) < min(max(club.p_mishit, 0.0), 0.5)
        k = int(mishit.sum())
        if k:
            m = np.broadcast_to(mean, (n,))[mishit] if np.ndim(mean) else mean
            carry[mishit] = m * rng.uniform(0.55, 0.85, k)
            lateral[mishit] = rng.normal(club.lateral_bias, max(club.lateral_sigma, MIN_LATERAL_SIGMA) * 1.6, k)
        return np.maximum(carry, 5.0), lateral, mishit

    def _draw_vec(self, mean, sig, lat_sig, lat_bias, p_mis, rng):
        n = len(mean)
        carry = rng.normal(mean, np.maximum(sig, MIN_CARRY_SIGMA))
        lateral = rng.normal(lat_bias, np.maximum(lat_sig, MIN_LATERAL_SIGMA))
        mishit = rng.random(n) < np.clip(p_mis, 0, 0.5)
        k = int(mishit.sum())
        if k:
            carry[mishit] = mean[mishit] * rng.uniform(0.55, 0.85, k)
            lateral[mishit] = rng.normal(lat_bias[mishit], np.maximum(lat_sig[mishit], MIN_LATERAL_SIGMA) * 1.6)
        return np.maximum(carry, 5.0), lateral, mishit

    @staticmethod
    def _land(start, direction, carry, lateral):
        sx, sy = start
        dx, dy = direction
        rx, ry = -dy, dx  # +lateral = right of the aim line (world +y is right of +x)
        return sx + carry * dx + lateral * rx, sy + carry * dy + lateral * ry

    def _drop(self, geom: HoleGeometry, r: dict[str, np.ndarray], mask: np.ndarray, wx, wy, lie):
        """Move penalty-area samples to a drop spot (rough, near the hazard edge)."""
        x = r["x"][mask]
        y = r["y"][mask]
        # Drop opposite the point of entry: back toward the centerline just outside the hazard.
        hazard_edge = np.zeros_like(y)
        for f in geom.features:
            if f.kind in ("water", "creek", "penalty"):
                inside = f.contains(x, y)
                if f.side in ("left", "right", "both"):
                    hazard_edge[inside] = np.sign(y[inside]) * max(f.offset_yards - 4.0, 0.0)
                else:
                    x[inside] = np.minimum(x[inside], f.start_yards - 5.0)
                    hazard_edge[inside] = y[inside]
        w = np.array([geom.local_to_world(a, b) for a, b in zip(x, hazard_edge)]) if x.size else np.zeros((0, 2))
        wx = wx.copy()
        wy = wy.copy()
        lie = lie.copy()
        wx[mask] = w[:, 0]
        wy[mask] = w[:, 1]
        lie[mask] = "rough"
        return wx, wy, lie

    def _expected_residual(self, lie: str, dist: np.ndarray) -> np.ndarray:
        return np.array([personal_expected_strokes(self.profile, lie, float(d)) for d in dist])

    def _residual(self, lie: str, dist: np.ndarray, rng: np.random.Generator, extra: np.ndarray | None = None) -> np.ndarray:
        """Stochastic strokes-to-hole-out from the personal table.

        The table gives an expectation; we add a little noise and round so the
        hole-score *distribution* has realistic tails (three-putts happen).
        ``extra`` is the lie-quality surcharge (deep rough, long miss...).
        """
        mu = self._expected_residual(lie, dist)
        if extra is not None:
            mu = mu + extra
        a, b = RESIDUAL_VAR.get(lie, DEFAULT_RESIDUAL_VAR)
        sd = np.sqrt(np.maximum(a + b * (mu - 1.0), 0.05))
        draw = mu + rng.normal(0.0, 1.0, len(mu)) * sd
        if lie not in ("green", "fringe"):
            draw = draw + (rng.random(len(mu)) < DISASTER_TAIL)
        return np.maximum(np.rint(draw), 1.0)

    def _residual_mixed(self, lies: np.ndarray, dist: np.ndarray, rng: np.random.Generator, extra: np.ndarray | None = None) -> np.ndarray:
        out = np.zeros(len(lies))
        for lie in set(lies.tolist()):
            m = lies == lie
            out[m] = self._residual(str(lie), dist[m], rng, None if extra is None else extra[m])
        return out

    def _expected_value_mixed(self, lies: np.ndarray, dist: np.ndarray, extra: np.ndarray) -> np.ndarray:
        out = np.zeros(len(lies))
        for lie in set(lies.tolist()):
            m = lies == lie
            out[m] = self._expected_residual(str(lie), dist[m]) + extra[m]
        return out

    def _club_for_distance(self, dists: np.ndarray):
        codes = self.club_order
        carries = np.array([self.clubs[c].carry_mean + self.clubs[c].long_bias for c in codes])
        c_sig = np.array([self.clubs[c].carry_sigma for c in codes])
        l_sig = np.array([self.clubs[c].lateral_sigma for c in codes])
        l_bias = np.array([self.clubs[c].lateral_bias for c in codes])
        p_mis = np.array([self.clubs[c].p_mishit for c in codes])
        # Nearest full club; below the shortest club it is a partial wedge.
        idx = np.abs(carries[None, :] - dists[:, None]).argmin(axis=1)
        full = carries[idx]
        frac = np.clip(dists / np.maximum(full, 1.0), 0.3, 1.0)
        carry_mean = np.where(dists < full, dists, full)
        carry_sig = np.maximum(c_sig[idx] * frac, MIN_CARRY_SIGMA)
        lat_sig = np.maximum(l_sig[idx] * frac, MIN_LATERAL_SIGMA)
        return idx, carry_mean, carry_sig, lat_sig, l_bias[idx] * frac, p_mis[idx]

    def _mode_club(self, idx: np.ndarray) -> str | None:
        if idx.size == 0:
            return None
        vals, counts = np.unique(idx, return_counts=True)
        return self.club_order[int(vals[counts.argmax()])]

    def _green_aim(self, geom: HoleGeometry) -> float:
        """Lateral aim on the green: shade away from green-side trouble."""
        danger_left = danger_right = 0.0
        for f in geom.features:
            if f.end_yards >= geom.yards - 45 and f.start_yards <= geom.yards + 25:
                weight = {"water": 1.0, "creek": 1.0, "penalty": 1.0, "ob": 1.2, "bunker": 0.5, "trees": 0.6}.get(f.kind, 0.3)
                if f.side == "left":
                    danger_left += weight
                elif f.side == "right":
                    danger_right += weight
        shade = (danger_left - danger_right)
        return float(np.clip(shade * 0.25 * geom.green_width_yards / 2.0, -geom.green_width_yards / 3.0, geom.green_width_yards / 3.0))

    def _layup_options(self, geom: HoleGeometry, dists: np.ndarray) -> list[dict[str, Any]]:
        """Candidate second shots when the green is out of range.

        * advance: longest non-driver club straight ahead;
        * layup: leave the player's favourite wedge number;
        * short layup: stop short of the first cross hazard ahead (if any).
        """
        med = float(np.median(dists))
        opts: list[dict[str, Any]] = []
        non_driver = [c for c in self.club_order if self.clubs[c].category != "driver"] or self.club_order
        long_code = non_driver[0]
        opts.append({"kind": "advance", "club": long_code, "carry": self.clubs[long_code].carry_mean})
        fav = self._favourite_wedge_distance()
        lay_target = max(med - fav, 60.0)
        shorter = [c for c in self.club_order if self.clubs[c].carry_mean <= lay_target]
        lay_code = shorter[0] if shorter else self.club_order[-1]
        opts.append({"kind": "layup", "club": lay_code, "carry": min(self.clubs[lay_code].carry_mean, lay_target)})
        # Stop short of a cross hazard between here and the green.
        here_x = geom.yards - med
        cross = sorted(
            (f for f in geom.features if f.side == "center" and f.kind in ("water", "creek", "penalty", "ob", "bunker")
             and f.start_yards > here_x + 40),
            key=lambda f: f.start_yards,
        )
        if cross:
            short_target = cross[0].start_yards - 12 - here_x
            if 50 <= short_target < self.clubs[long_code].carry_mean:
                sc = [c for c in self.club_order if self.clubs[c].carry_mean <= short_target]
                code = sc[0] if sc else self.club_order[-1]
                opts.append({"kind": "layup", "club": code, "carry": min(self.clubs[code].carry_mean, short_target)})
        return opts

    def _favourite_wedge_distance(self) -> float:
        wedges = [d for d in self.clubs.values() if d.category == "wedge" and 70 <= d.carry_mean <= 130]
        if not wedges:
            return 100.0
        best = min(wedges, key=lambda d: (d.lateral_sigma / max(d.carry_mean, 1)) - 0.1 * d.confidence)
        return float(best.carry_mean)

    # ------------------------------------------------------------------
    # Scoring & description
    # ------------------------------------------------------------------
    def _objective(self, sim: dict[str, Any], par: int) -> float:
        s = sim["strokes"]
        return float(np.mean(s) + self.lam * np.mean(s >= par + 2))

    @staticmethod
    def _distribution(strokes: np.ndarray, par: int) -> dict[str, float]:
        d = strokes - par
        return {
            "eagle": round(float(np.mean(d <= -2)), 3),
            "birdie": round(float(np.mean(d == -1)), 3),
            "par": round(float(np.mean(d == 0)), 3),
            "bogey": round(float(np.mean(d == 1)), 3),
            "double": round(float(np.mean(d == 2)), 3),
            "triple_plus": round(float(np.mean(d >= 3)), 3),
        }

    def _landing_mix(self, sim: dict[str, Any]) -> dict[str, float]:
        lies, counts = np.unique(sim["tee_lie"], return_counts=True)
        n = len(sim["tee_lie"])
        return {str(l): round(float(c) / n, 3) for l, c in zip(lies, counts)}

    def _alternatives(self, results, best: Candidate, par: int) -> list[dict[str, Any]]:
        seen = {best.club}
        alts = []
        for obj, c, sim in results[1:]:
            key = c.club if c.label == "full" else f"{c.club}-{c.label}"
            if key in seen:
                continue
            seen.add(key)
            s = sim["strokes"]
            alts.append({
                "club": c.club, "label": c.label, "aim_offset_yards": c.target_y, "target_yards": round(c.target_x),
                "expected_strokes": round(float(np.mean(s)), 2),
                "p_double_plus": round(float(np.mean(s >= par + 2)), 3),
                "objective_delta": round(float(obj - results[0][0]), 3),
                "landing_mix": self._landing_mix(sim),
            })
            if len(alts) >= 3:
                break
        return alts

    def _describe(self, geom: HoleGeometry, best: Candidate, sim: dict[str, Any], alternatives: list[dict[str, Any]]) -> dict[str, Any]:
        s = sim["strokes"]
        par = geom.par
        club = self.clubs[best.club]
        mix = self._landing_mix(sim)
        trouble = mix.get("penalty", 0) + mix.get("ob", 0) + mix.get("recovery", 0)
        # Most likely trouble feature under this plan.
        feats, counts = np.unique([f for f in sim["tee_feature"] if f], return_counts=True)
        avoid = None
        if feats.size:
            i = int(counts.argmax())
            avoid = {"feature": str(feats[i]), "probability": round(float(counts[i]) / len(s), 3)}
        approach_dists = sim["approach_dists"]
        approach_median = float(np.median(approach_dists)) if approach_dists else None
        approach_club = None
        if approach_median is not None:
            approach_club = min(self.club_order, key=lambda c: abs(self.clubs[c].carry_mean - approach_median))
        stages = sim["stages"]
        n_total = len(s)
        layup_stage = next((st for st in stages if st["kind"] in ("layup", "advance") and st["stage"] == 0), None)
        layup = layup_stage if (layup_stage and layup_stage["n"] >= 0.5 * n_total) else None
        contingency = layup_stage if (layup_stage and CONTINGENCY_SHARE * n_total <= layup_stage["n"] < 0.5 * n_total) else None
        aim_words = self._aim_words(best, club, geom)
        ellipse = dispersion_ellipse(club if best.label == "full" else club.partial(best.carry))
        # Sample landing points for the map (local coordinates).
        k = min(80, len(s))
        pts = [{"x": round(float(x), 1), "y": round(float(y), 1), "lie": str(l)}
               for x, y, l in zip(sim["tee_x"][:k], sim["tee_y"][:k], sim["tee_lie"][:k])]
        confidence = round(0.5 * club.confidence + 0.5 * self.readiness, 2)
        dist = self._distribution(s, par)
        plan = {
            "hole": geom.number,
            "par": par,
            "yards": round(geom.yards),
            "playing_yards": round(geom.playing_yards),
            "expected_strokes": round(float(np.mean(s)), 2),
            "expected_vs_par": round(float(np.mean(s)) - par, 2),
            "p_double_plus": dist["double"] + dist["triple_plus"],
            "score_distribution": dist,
            "tee": {
                "club": best.club,
                "club_name": club.name or best.club,
                "shot": best.label,
                "carry_yards": round(best.carry),
                "target_yards": round(best.target_x),
                "aim_offset_yards": best.target_y,
                "aim": aim_words,
                "landing_mix": mix,
                "trouble_probability": round(trouble, 3),
                "avoid": avoid,
                "ellipse": {"x": round(best.target_x, 1), "y": round(best.target_y + club.lateral_bias, 1), **ellipse},
                "landing_points": pts,
                "confidence": confidence,
            },
            "approach": {
                "from_yards": round(approach_median) if approach_median else None,
                "club": approach_club,
                "aim_offset_yards": round(self._green_aim(geom), 1),
                "aim": self._green_aim_words(geom),
                "gir_probability": round(float(np.mean(sim["gir"])), 3),
                "share": round(len(approach_dists) / n_total, 3),
            } if (approach_median and geom.par > 3 and len(approach_dists) >= 0.3 * n_total) else None,
            "layup": {"kind": layup["kind"], "club": layup["club"], "carry_yards": round(layup["carry"]),
                      "leaves_yards": round(max(layup["median_dist"] - layup["carry"], 20)),
                      "share": round(layup["n"] / n_total, 3)} if layup else None,
            "contingency": {"kind": contingency["kind"], "club": contingency["club"], "carry_yards": round(contingency["carry"]),
                            "share": round(contingency["n"] / n_total, 3)} if contingency else None,
            "alternatives": alternatives,
            "map": geom.render_spec(),
        }
        plan["rationale"] = self._rationale(plan, geom, alternatives)
        plan["key_thought"] = self._key_thought(plan)
        return plan

    # ------------------------------------------------------------------
    def _aim_words(self, best: Candidate, club: ClubDistribution, geom: HoleGeometry) -> str:
        off = best.target_y
        side = "right" if off > 0 else "left"
        if geom.par == 3:
            where = "the middle of the green" if abs(off) < 3 else f"the {side} third of the green"
            base = f"{club.name or best.club} at {where}"
        else:
            where = "the middle of the fairway" if abs(off) < 3 else f"{abs(off):.0f} yards {side} of the fairway center"
            base = f"{club.name or best.club}, aim at {where}"
            if best.label == "layup":
                base = f"{club.name or best.club} layup to {best.carry:.0f} yards, aim at {where}"
        if abs(club.lateral_bias) >= 4:
            bias_side = "right" if club.lateral_bias > 0 else "left"
            base += f" (your typical {abs(club.lateral_bias):.0f}-yard {bias_side} drift is already built in)"
        return base

    def _green_aim_words(self, geom: HoleGeometry) -> str:
        y = self._green_aim(geom)
        if abs(y) < 2:
            return "middle of the green - ignore the flag"
        return f"{'right' if y > 0 else 'left'} half of the green, {abs(y):.0f} yards from center - short-side trouble is {'left' if y > 0 else 'right'}"

    def _rationale(self, plan: dict[str, Any], geom: HoleGeometry, alts: list[dict[str, Any]]) -> str:
        tee = plan["tee"]
        parts = []
        fw = tee["landing_mix"].get("fairway", 0) + tee["landing_mix"].get("green", 0)
        parts.append(
            f"{tee['club_name']} off the tee finds short grass {fw:.0%} of the time and trouble {tee['trouble_probability']:.0%}."
        )
        if tee.get("avoid"):
            parts.append(f"The miss to avoid is the {tee['avoid']['feature']} ({tee['avoid']['probability']:.0%} under this plan).")
        if alts:
            a = alts[0]
            worse = a["objective_delta"]
            if worse > 0.02:
                parts.append(
                    f"{a['club']} was the next-best option: it costs about {worse:.2f} strokes per play"
                    f" (double-bogey risk {a['p_double_plus']:.0%} vs {plan['p_double_plus']:.0%})."
                )
            else:
                parts.append(f"{a['club']} is a coin-flip alternative (within {worse:.2f} strokes) if the tee shot feels uncomfortable.")
        if plan.get("layup"):
            l = plan["layup"]
            if l["kind"] == "layup":
                fav = self._favourite_wedge_distance()
                why = "your most reliable wedge number" if abs(l["leaves_yards"] - fav) <= 15 else "short of the trouble ahead"
                parts.append(f"Second shot: lay up with {l['club']} to leave about {l['leaves_yards']} yards, {why}.")
            else:
                parts.append(f"Second shot: advance with {l['club']} - the reward beats the risk here.")
        if plan.get("approach"):
            ap = plan["approach"]
            parts.append(f"Approach from about {ap['from_yards']} yards ({ap['club']}): aim at the {ap['aim']}. Green in regulation {ap['gir_probability']:.0%}.")
        if plan.get("contingency"):
            c = plan["contingency"]
            parts.append(f"If the tee shot leaves you out of range ({c['share']:.0%} of the time), {c['kind']} with {c['club']} rather than forcing it.")
        if geom.par == 3:
            parts.append("Ignore the flag: the middle of the green is the target on every par 3.")
        d = plan["score_distribution"]
        parts.append(f"Expected {plan['expected_strokes']:.2f} strokes: par or better {d['eagle'] + d['birdie'] + d['par']:.0%}, bogey {d['bogey']:.0%}, double-plus {plan['p_double_plus']:.0%}.")
        return " ".join(parts)

    @staticmethod
    def _key_thought(plan: dict[str, Any]) -> str:
        tee = plan["tee"]
        if tee.get("avoid") and tee["avoid"]["probability"] >= 0.08:
            return f"Whatever happens, stay out of the {tee['avoid']['feature']}."
        if plan.get("layup") and plan["layup"]["kind"] == "layup":
            return "Bogey is fine here; double is not. Take the layup."
        if plan["par"] == 3:
            return "Middle of the green, two putts, walk."
        return "Commit to the aim line - the pattern is built for it."

    def _course_summary(self, plans: list[dict[str, Any]], exp: float, par: int) -> dict[str, Any]:
        hardest = sorted(plans, key=lambda p: -p["expected_vs_par"])[:3]
        risky = sorted(plans, key=lambda p: -p["p_double_plus"])[:3]
        non_driver = [p["hole"] for p in plans if p["par"] > 3 and self.clubs.get(p["tee"]["club"]) and self.clubs[p["tee"]["club"]].category != "driver"]
        return {
            "headline": f"Expected {exp:.1f} ({exp - par:+.1f}) - {'on track to break ' + str(self.target_score) if exp <= self.target_score else 'target ' + str(self.target_score) + ' needs ' + f'{exp - self.target_score:.1f}' + ' fewer strokes'}.",
            "hardest_holes": [{"hole": p["hole"], "expected_vs_par": p["expected_vs_par"]} for p in hardest],
            "blowup_holes": [{"hole": p["hole"], "p_double_plus": p["p_double_plus"]} for p in risky],
            "non_driver_holes": non_driver,
            "game_plan": [
                "Play for the fat side of every green; the flag is a suggestion.",
                "Bogey is a fine score on the three hardest holes - double is the enemy of 79.",
                f"Leave the driver in the bag on holes {', '.join(map(str, non_driver))}." if non_driver else "Driver is the play on every par 4 and 5 - commit to the aim lines.",
            ],
        }
