from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from app.models.pms_connection import PMSConnection


class PMSAdapter(ABC):
    """Base class for PMS integrations."""

    @abstractmethod
    def sync(self, db: Session, hotel_id: int, connection: PMSConnection) -> None:
        """Pull reservations and inventory from PMS and update local database."""
        ...

    @abstractmethod
    def push_rate(self, connection: PMSConnection, room_type_code: str, date: str, rate: float) -> bool:
        """Push a rate update to the PMS. Returns True on success."""
        ...

    @abstractmethod
    def test_connection(self, connection: PMSConnection) -> bool:
        """Test if the PMS connection is valid."""
        ...


def get_pms_adapter(provider: str) -> PMSAdapter | None:
    adapters = {
        "cloudbeds": _get_cloudbeds_adapter,
        "opera": _get_opera_adapter,
        "mews": _get_mews_adapter,
    }
    factory = adapters.get(provider)
    return factory() if factory else None


def _get_cloudbeds_adapter():
    from app.pms.cloudbeds import CloudbedsAdapter
    return CloudbedsAdapter()


def _get_opera_adapter():
    from app.pms.opera import OperaAdapter
    return OperaAdapter()


def _get_mews_adapter():
    from app.pms.mews import MewsAdapter
    return MewsAdapter()
