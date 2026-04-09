from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.pms_connection import PMSConnection

router = APIRouter()


class PMSConnectRequest(BaseModel):
    provider: str  # opera, cloudbeds, mews
    api_key: str
    base_url: str | None = None


class PMSStatusResponse(BaseModel):
    id: int
    provider: str
    is_active: bool
    sync_status: str
    last_sync_at: str | None
    model_config = {"from_attributes": True}


@router.post("/{hotel_id}/pms/connect", status_code=201)
def connect_pms(hotel_id: int, data: PMSConnectRequest, db: Session = Depends(get_db)):
    # Deactivate any existing connection for this hotel
    existing = db.query(PMSConnection).filter(
        PMSConnection.hotel_id == hotel_id, PMSConnection.is_active == True  # noqa: E712
    ).all()
    for conn in existing:
        conn.is_active = False

    connection = PMSConnection(
        hotel_id=hotel_id,
        provider=data.provider,
        api_key_encrypted=data.api_key,  # In production, encrypt this
        base_url=data.base_url,
        is_active=True,
    )
    db.add(connection)
    db.commit()
    db.refresh(connection)
    return {"status": "connected", "provider": data.provider, "id": connection.id}


@router.post("/{hotel_id}/pms/sync")
def trigger_sync(hotel_id: int, db: Session = Depends(get_db)):
    connection = db.query(PMSConnection).filter(
        PMSConnection.hotel_id == hotel_id, PMSConnection.is_active == True  # noqa: E712
    ).first()
    if not connection:
        raise HTTPException(400, "No active PMS connection")

    # Import the appropriate adapter
    from app.pms.base import get_pms_adapter
    adapter = get_pms_adapter(connection.provider)
    if not adapter:
        raise HTTPException(400, f"Unsupported PMS provider: {connection.provider}")

    # In a real system, this would be an async background task
    connection.sync_status = "syncing"
    db.commit()

    try:
        adapter.sync(db, hotel_id, connection)
        connection.sync_status = "completed"
        from datetime import datetime
        connection.last_sync_at = datetime.utcnow()
    except Exception as e:
        connection.sync_status = f"error: {str(e)[:200]}"
    finally:
        db.commit()

    return {"status": connection.sync_status, "last_sync_at": str(connection.last_sync_at)}


@router.get("/{hotel_id}/pms/status")
def pms_status(hotel_id: int, db: Session = Depends(get_db)):
    connection = db.query(PMSConnection).filter(
        PMSConnection.hotel_id == hotel_id, PMSConnection.is_active == True  # noqa: E712
    ).first()
    if not connection:
        return {"connected": False}
    return {
        "connected": True,
        "provider": connection.provider,
        "sync_status": connection.sync_status,
        "last_sync_at": str(connection.last_sync_at) if connection.last_sync_at else None,
    }
