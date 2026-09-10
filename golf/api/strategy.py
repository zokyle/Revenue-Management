from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from golf import services
from golf.database import get_db
from golf.models import StrategyPlan
from golf.schemas import ChatRequest, ChatResponse, ProfileResponse, StrategyRequest, StrategyResponse

router = APIRouter()


@router.get("/{player_id}/profile", response_model=ProfileResponse)
def get_profile(player_id: int, db: Session = Depends(get_db)):
    if not services.get_player(db, player_id):
        raise HTTPException(404, "Player not found")
    return services.latest_profile(db, player_id)


@router.post("/{player_id}/profile/recompute", response_model=ProfileResponse)
def recompute_profile(player_id: int, db: Session = Depends(get_db)):
    try:
        return services.compute_profile(db, player_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/{player_id}/dashboard")
def dashboard(player_id: int, db: Session = Depends(get_db)):
    if not services.get_player(db, player_id):
        raise HTTPException(404, "Player not found")
    return services.dashboard_summary(db, player_id)


@router.post("/{player_id}/strategy/{course_id}", response_model=StrategyResponse)
def generate_strategy(player_id: int, course_id: int, data: StrategyRequest | None = None, db: Session = Depends(get_db)):
    data = data or StrategyRequest()
    try:
        return services.generate_plan(
            db, player_id, course_id, objective=data.objective, carry_scale=data.carry_scale,
            samples=data.samples, seed=data.seed,
        )
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/{player_id}/strategy/{course_id}", response_model=StrategyResponse)
def latest_strategy(player_id: int, course_id: int, db: Session = Depends(get_db)):
    plan = services.latest_plan(db, player_id, course_id)
    if not plan:
        raise HTTPException(404, "No strategy generated yet for this course")
    return plan


@router.get("/{player_id}/strategies", response_model=list[StrategyResponse])
def list_strategies(player_id: int, db: Session = Depends(get_db)):
    return (
        db.query(StrategyPlan)
        .filter(StrategyPlan.player_id == player_id)
        .order_by(StrategyPlan.created_at.desc())
        .limit(20)
        .all()
    )


@router.post("/{player_id}/caddie/chat", response_model=ChatResponse)
def caddie_chat(player_id: int, data: ChatRequest, db: Session = Depends(get_db)):
    from golf.agent.caddie import get_caddie

    if not services.get_player(db, player_id):
        raise HTTPException(404, "Player not found")
    caddie = get_caddie(db, player_id)
    return caddie.chat(data.message, course_id=data.course_id, hole_number=data.hole_number)


@router.get("/{player_id}/caddie/history")
def caddie_history(player_id: int, limit: int = 40, db: Session = Depends(get_db)):
    from golf.agent.caddie import get_caddie

    if not services.get_player(db, player_id):
        raise HTTPException(404, "Player not found")
    return get_caddie(db, player_id).history(limit=limit)
