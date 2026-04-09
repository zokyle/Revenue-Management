from datetime import datetime

from sqlalchemy import Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PMSConnection(Base):
    __tablename__ = "pms_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # opera, cloudbeds, mews
    api_key_encrypted: Mapped[str] = mapped_column(String(500), nullable=True)
    base_url: Mapped[str] = mapped_column(String(500), nullable=True)
    last_sync_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    sync_status: Mapped[str] = mapped_column(String(50), default="never_synced")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
