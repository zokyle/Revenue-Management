from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from golf import services
from golf.database import get_db
from golf.models import Club, Player
from golf.schemas import ClubCreate, ClubResponse, ClubUpdate, PlayerCreate, PlayerResponse, PlayerUpdate

router = APIRouter()


@router.get("", response_model=list[PlayerResponse])
def list_players(db: Session = Depends(get_db)):
    return db.query(Player).order_by(Player.id).all()


@router.post("", response_model=PlayerResponse, status_code=201)
def create_player(data: PlayerCreate, db: Session = Depends(get_db)):
    payload = data.model_dump()
    default_bag = payload.pop("default_bag")
    player = Player(**payload)
    db.add(player)
    db.commit()
    db.refresh(player)
    if default_bag:
        services.create_default_bag(db, player)
        db.refresh(player)
    return player


@router.get("/{player_id}", response_model=PlayerResponse)
def get_player(player_id: int, db: Session = Depends(get_db)):
    player = services.get_player(db, player_id)
    if not player:
        raise HTTPException(404, "Player not found")
    return player


@router.put("/{player_id}", response_model=PlayerResponse)
def update_player(player_id: int, data: PlayerUpdate, db: Session = Depends(get_db)):
    player = services.get_player(db, player_id)
    if not player:
        raise HTTPException(404, "Player not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(player, k, v)
    db.commit()
    db.refresh(player)
    return player


@router.get("/{player_id}/clubs", response_model=list[ClubResponse])
def list_clubs(player_id: int, db: Session = Depends(get_db)):
    return db.query(Club).filter(Club.player_id == player_id).order_by(Club.sort_order).all()


@router.post("/{player_id}/clubs", response_model=ClubResponse, status_code=201)
def create_club(player_id: int, data: ClubCreate, db: Session = Depends(get_db)):
    if not services.get_player(db, player_id):
        raise HTTPException(404, "Player not found")
    if db.query(Club).filter(Club.player_id == player_id, Club.code == data.code).first():
        raise HTTPException(409, f"Club code {data.code} already exists")
    club = Club(player_id=player_id, **data.model_dump())
    db.add(club)
    db.commit()
    db.refresh(club)
    return club


@router.put("/{player_id}/clubs/{club_id}", response_model=ClubResponse)
def update_club(player_id: int, club_id: int, data: ClubUpdate, db: Session = Depends(get_db)):
    club = db.query(Club).filter(Club.id == club_id, Club.player_id == player_id).first()
    if not club:
        raise HTTPException(404, "Club not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(club, k, v)
    db.commit()
    db.refresh(club)
    return club


@router.delete("/{player_id}/clubs/{club_id}", status_code=204)
def delete_club(player_id: int, club_id: int, db: Session = Depends(get_db)):
    club = db.query(Club).filter(Club.id == club_id, Club.player_id == player_id).first()
    if not club:
        raise HTTPException(404, "Club not found")
    db.delete(club)
    db.commit()
    return None
