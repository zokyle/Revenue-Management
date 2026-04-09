import httpx
from sqlalchemy.orm import Session

from app.models.pms_connection import PMSConnection
from app.pms.base import PMSAdapter


class OperaAdapter(PMSAdapter):
    """Oracle Opera Cloud PMS integration.

    Opera Cloud REST API uses OAuth2 for auth and provides endpoints for:
    - Reservations (CRUD)
    - Rate plans and rate codes
    - Availability and inventory
    - Block/group management
    """

    def _headers(self, connection: PMSConnection) -> dict:
        return {
            "Authorization": f"Bearer {connection.api_key_encrypted}",
            "Content-Type": "application/json",
            "x-hotelid": str(connection.hotel_id),
        }

    def _base_url(self, connection: PMSConnection) -> str:
        return connection.base_url or "https://api.oracle.com/opera/v1"

    def test_connection(self, connection: PMSConnection) -> bool:
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(
                    f"{self._base_url(connection)}/hotels",
                    headers=self._headers(connection),
                )
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def sync(self, db: Session, hotel_id: int, connection: PMSConnection) -> None:
        """Pull data from Opera Cloud.

        In production this would:
        1. GET /reservations with dateRange filter
        2. Map Opera reservation fields to our model
        3. GET /availability for inventory updates
        4. Handle Opera's pagination (offset/limit)
        """
        pass

    def push_rate(self, connection: PMSConnection, room_type_code: str, date: str, rate: float) -> bool:
        """Push rate update via Opera's rate plan endpoint."""
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.put(
                    f"{self._base_url(connection)}/ratePlans/rates",
                    headers=self._headers(connection),
                    json={
                        "roomType": room_type_code,
                        "start": date,
                        "end": date,
                        "amount": {"value": rate, "currencyCode": "USD"},
                    },
                )
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
