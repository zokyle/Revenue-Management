from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from golf import services
from golf.database import get_db
from golf.models import Round
from golf.schemas import (
    HoleResultCreate, HoleResultResponse, NarrativeRequest, NarrativeResponse, RoundCreate, RoundListResponse,
    RoundResponse, RoundUpdate,
)

router = APIRouter()


@router.get("", response_model=list[RoundListResponse])
def list_rounds(player_id: int, db: Session = Depends(get_db)):
    rounds = services.player_rounds(db, player_id)
    return [
        {
            "id": r.id, "player_id": r.player_id, "course_id": r.course_id, "played_on": r.played_on,
            "tee_name": r.tee_name, "weather": r.weather, "wind": r.wind, "logging_mode": r.logging_mode,
            "notes": r.notes, "total_score": r.total_score, "completed": r.completed,
            "course_name": r.course.name if r.course else None, "holes_logged": len(r.holes),
        }
        for r in rounds
    ]


@router.post("", response_model=RoundResponse, status_code=201)
def create_round(player_id: int, data: RoundCreate, db: Session = Depends(get_db)):
    if not services.get_player(db, player_id):
        raise HTTPException(404, "Player not found")
    payload = data.model_dump()
    holes = payload.pop("holes", [])
    rnd = Round(player_id=player_id, **payload)
    db.add(rnd)
    db.commit()
    db.refresh(rnd)
    for h in holes:
        services.upsert_hole_result(db, rnd, h)
    rnd = services.get_round(db, rnd.id)
    services.recompute_round_total(db, rnd)
    return services.get_round(db, rnd.id)


@router.get("/{round_id}", response_model=RoundResponse)
def get_round(player_id: int, round_id: int, db: Session = Depends(get_db)):
    rnd = services.get_round(db, round_id)
    if not rnd or rnd.player_id != player_id:
        raise HTTPException(404, "Round not found")
    return rnd


@router.put("/{round_id}", response_model=RoundResponse)
def update_round(player_id: int, round_id: int, data: RoundUpdate, db: Session = Depends(get_db)):
    rnd = services.get_round(db, round_id)
    if not rnd or rnd.player_id != player_id:
        raise HTTPException(404, "Round not found")
    payload = data.model_dump(exclude_unset=True)
    services.apply_updates(rnd, payload)
    db.commit()
    if "total_score" not in payload:
        services.recompute_round_total(db, rnd)
    return services.get_round(db, round_id)


@router.delete("/{round_id}", status_code=204)
def delete_round(player_id: int, round_id: int, db: Session = Depends(get_db)):
    rnd = services.get_round(db, round_id)
    if not rnd or rnd.player_id != player_id:
        raise HTTPException(404, "Round not found")
    db.delete(rnd)
    db.commit()
    return None


@router.put("/{round_id}/holes/{hole_number}", response_model=HoleResultResponse)
def upsert_hole(player_id: int, round_id: int, hole_number: int, data: HoleResultCreate, db: Session = Depends(get_db)):
    """Create or replace one hole (with its shots) - the main logging endpoint."""
    rnd = services.get_round(db, round_id)
    if not rnd or rnd.player_id != player_id:
        raise HTTPException(404, "Round not found")
    payload = data.model_dump()
    payload["hole_number"] = hole_number
    hr = services.upsert_hole_result(db, rnd, payload)
    services.recompute_round_total(db, services.get_round(db, round_id))
    return hr


@router.post("/{round_id}/narrative", response_model=NarrativeResponse)
def log_narrative(player_id: int, round_id: int, data: NarrativeRequest, db: Session = Depends(get_db)):
    """Describe holes in plain English; the caddie parses them into shots."""
    from golf.agent.caddie import get_caddie

    rnd = services.get_round(db, round_id)
    if not rnd or rnd.player_id != player_id:
        raise HTTPException(404, "Round not found")
    caddie = get_caddie(db, player_id)
    parsed = caddie.parse_narrative(data.text, hole_number=data.hole_number, round_=rnd)
    if data.commit:
        for h in parsed.holes:
            payload = h.model_dump()
            payload["shots"] = [s.model_dump() for s in h.shots]
            services.upsert_hole_result(db, rnd, payload)
        services.recompute_round_total(db, services.get_round(db, round_id))
    return parsed
