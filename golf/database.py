"""Database session management for the golf app (independent of the hotel app)."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from golf.config import settings

engine = create_engine(
    settings.golf_database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.golf_database_url else {},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all golf tables. Called at app startup; idempotent."""
    import golf.models  # noqa: F401  -- populate Base.metadata

    Base.metadata.create_all(bind=engine)
