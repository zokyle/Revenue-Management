"""Application services shared by the REST API and the caddie agent.

Everything that needs a database session and more than one model lives here
so that the API layer stays thin and the agent can call the same logic.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session, selectinload

from golf.config import settings
from golf.engine.baselines import DEFAULT_CLUBS
from golf.engine.hole_model import HoleGeometry
from golf.engine.learning import ProfileBuilder
from golf.engine.strategy import StrategyEngine
from golf.models import (
    Club, Course, Hole, HoleFeature, HoleResult, Player, ProfileSnapshot, Round, Shot, StrategyPlan,
)

# Objective -> risk tolerance override (None = use the player's setting).
OBJECTIVE_RISK = {"break_80": None, "min_expected": 1.0, "aggressive": 0.85}


# ---------------------------------------------------------------------------
# Players & bag
# ---------------------------------------------------------------------------
def create_default_bag(db: Session, player: Player) -> list[Club]:
    """Give a new player a standard 14-club bag (priors come from the engine)."""
    clubs = []
    for i, c in enumerate(DEFAULT_CLUBS):
        if c["code"] in ("5w", "3h"):
            continue  # standard bag: D, 3w, 4i-9i, PW, GW, SW, LW, P + one of 5w/3h
        clubs.append(Club(player_id=player.id, code=c["code"], name=c["name"], category=c["category"], sort_order=i))
    hybrid = next(c for c in DEFAULT_CLUBS if c["code"] == "3h")
    clubs.insert(2, Club(player_id=player.id, code=hybrid["code"], name=hybrid["name"], category=hybrid["category"], sort_order=2))
    db.add_all(clubs)
    db.commit()
    for c in clubs:
        db.refresh(c)
    return clubs


def get_player(db: Session, player_id: int) -> Player | None:
    return db.query(Player).options(selectinload(Player.clubs)).filter(Player.id == player_id).first()


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------
def get_course(db: Session, course_id: int) -> Course | None:
    return (
        db.query(Course)
        .options(selectinload(Course.holes).selectinload(Hole.features))
        .filter(Course.id == course_id)
        .first()
    )


def refresh_course_totals(db: Session, course: Course) -> None:
    course.par = sum(h.par for h in course.holes) if course.holes else None
    course.yardage = sum(h.yards for h in course.holes) if course.holes else None
    db.commit()


def course_geometry(course: Course) -> list[HoleGeometry]:
    return [HoleGeometry.from_hole(h) for h in sorted(course.holes, key=lambda h: h.number)]


def replace_hole_features(db: Session, hole: Hole, features: list[dict[str, Any]]) -> None:
    for f in list(hole.features):
        db.delete(f)
    db.flush()
    for f in features:
        db.add(HoleFeature(hole_id=hole.id, **f))
    db.commit()


# ---------------------------------------------------------------------------
# Rounds
# ---------------------------------------------------------------------------
def get_round(db: Session, round_id: int) -> Round | None:
    return (
        db.query(Round)
        .options(selectinload(Round.holes).selectinload(HoleResult.shots))
        .filter(Round.id == round_id)
        .first()
    )


def player_rounds(db: Session, player_id: int) -> list[Round]:
    return (
        db.query(Round)
        .options(selectinload(Round.holes).selectinload(HoleResult.shots))
        .filter(Round.player_id == player_id)
        .order_by(Round.played_on.desc(), Round.id.desc())
        .all()
    )


def resolve_club(db: Session, player_id: int, code: str | None, club_id: int | None) -> Club | None:
    if club_id is not None:
        return db.query(Club).filter(Club.id == club_id, Club.player_id == player_id).first()
    if code:
        return db.query(Club).filter(Club.player_id == player_id, Club.code.ilike(code)).first()
    return None


def upsert_hole_result(db: Session, rnd: Round, data: dict[str, Any]) -> HoleResult:
    """Create or replace one hole of a round, including its shots."""
    shots = data.pop("shots", []) or []
    existing = next((h for h in rnd.holes if h.hole_number == data["hole_number"]), None)
    if existing is None:
        existing = HoleResult(round_id=rnd.id, **data)
        db.add(existing)
        db.flush()
    else:
        for k, v in data.items():
            setattr(existing, k, v)
        for s in list(existing.shots):
            db.delete(s)
        db.flush()
    # Link to the course hole when possible.
    if existing.hole_id is None and rnd.course_id:
        hole = db.query(Hole).filter(Hole.course_id == rnd.course_id, Hole.number == existing.hole_number).first()
        if hole:
            existing.hole_id = hole.id
            existing.yards = existing.yards or hole.yards
    for s in shots:
        club = resolve_club(db, rnd.player_id, s.get("club_code"), s.get("club_id"))
        if club:
            s["club_id"] = club.id
            s["club_code"] = club.code
        db.add(Shot(hole_result_id=existing.id, **s))
    db.commit()
    db.refresh(existing)
    return existing


def recompute_round_total(db: Session, rnd: Round) -> None:
    if rnd.holes:
        rnd.total_score = sum(h.score for h in rnd.holes)
    db.commit()


# ---------------------------------------------------------------------------
# Profile & strategy
# ---------------------------------------------------------------------------
def compute_profile(db: Session, player_id: int, save: bool = True) -> ProfileSnapshot:
    player = get_player(db, player_id)
    if player is None:
        raise ValueError("Player not found")
    rounds = [r for r in player_rounds(db, player_id) if r.holes]
    profile = ProfileBuilder(player, player.clubs, rounds).build()
    snap = ProfileSnapshot(
        player_id=player_id,
        rounds_count=profile["rounds"],
        shots_count=profile["shots"],
        readiness_score=profile["readiness"]["score"],
        readiness_level=profile["readiness"]["level"],
        data=profile,
    )
    if save:
        db.add(snap)
        db.commit()
        db.refresh(snap)
    return snap


def latest_profile(db: Session, player_id: int, max_age_rounds: bool = True) -> ProfileSnapshot:
    """Return the newest snapshot, recomputing if rounds were added since."""
    snap = (
        db.query(ProfileSnapshot)
        .filter(ProfileSnapshot.player_id == player_id)
        .order_by(ProfileSnapshot.computed_at.desc(), ProfileSnapshot.id.desc())
        .first()
    )
    n_rounds = db.query(Round).filter(Round.player_id == player_id).count()
    n_shots = (
        db.query(Shot).join(HoleResult).join(Round).filter(Round.player_id == player_id).count()
    )
    if snap is None or snap.rounds_count != n_rounds or snap.shots_count != n_shots:
        snap = compute_profile(db, player_id, save=True)
    return snap


def generate_plan(
    db: Session,
    player_id: int,
    course_id: int,
    objective: str = "break_80",
    carry_scale: float = 1.0,
    samples: int | None = None,
    seed: int | None = None,
    save: bool = True,
) -> StrategyPlan:
    player = get_player(db, player_id)
    if player is None:
        raise ValueError("Player not found")
    course = get_course(db, course_id)
    if course is None:
        raise ValueError("Course not found")
    if not course.holes:
        raise ValueError("Course has no holes yet")
    snap = latest_profile(db, player_id)
    risk = OBJECTIVE_RISK.get(objective)
    engine = StrategyEngine(
        snap.data,
        n_samples=samples or settings.monte_carlo_samples,
        seed=seed if seed is not None else 7,
        risk_tolerance=player.risk_tolerance if risk is None else risk,
        target_score=player.target_score,
    )
    plan_data = engine.plan_course(course_geometry(course), {"carry_scale": carry_scale})
    plan_data["course"] = {"id": course.id, "name": course.name, "tee_name": course.tee_name, "par": course.par, "yardage": course.yardage}
    plan_data["player"] = {"id": player.id, "name": player.name, "handicap": player.handicap_index}
    plan_data["objective"] = objective
    plan_data["carry_scale"] = carry_scale
    plan = StrategyPlan(
        player_id=player_id,
        course_id=course_id,
        profile_snapshot_id=snap.id,
        objective=objective,
        expected_score=plan_data["expected_score"],
        p_break_target=plan_data["p_break_target"],
        data=plan_data,
    )
    if save:
        db.add(plan)
        db.commit()
        db.refresh(plan)
    return plan


def latest_plan(db: Session, player_id: int, course_id: int) -> StrategyPlan | None:
    return (
        db.query(StrategyPlan)
        .filter(StrategyPlan.player_id == player_id, StrategyPlan.course_id == course_id)
        .order_by(StrategyPlan.created_at.desc(), StrategyPlan.id.desc())
        .first()
    )


def dashboard_summary(db: Session, player_id: int) -> dict[str, Any]:
    """Everything the dashboard needs in one call."""
    snap = latest_profile(db, player_id)
    p = snap.data
    rounds = player_rounds(db, player_id)
    recent = [
        {"id": r.id, "date": r.played_on.isoformat() if r.played_on else None, "score": r.total_score,
         "course": r.course.name if r.course else None, "holes": len(r.holes)}
        for r in rounds[:8]
    ]
    return {
        "player": {"id": player_id, "name": p.get("player_name"), "handicap": p.get("handicap")},
        "readiness": p.get("readiness"),
        "score_stats": p.get("score_stats"),
        "tendencies": p.get("tendencies"),
        "errors": p.get("errors"),
        "clubs": p.get("clubs"),
        "recent_rounds": recent,
        "snapshot_id": snap.id,
        "computed_at": snap.computed_at.isoformat(),
    }
