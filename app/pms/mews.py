import httpx
from sqlalchemy.orm import Session

from app.models.pms_connection import PMSConnection
from app.pms.base import PMSAdapter


class MewsAdapter(PMSAdapter):
    """Mews PMS integration.

    Mews Connector API uses a platform-specific access token.
    Key operations:
    - getAll reservations
    - getAvailability
    - updateRatePrice
    """

    API_BASE = "https://api.mews.com/api/connector/v1"

    def _payload_base(self, connection: PMSConnection) -> dict:
        return {
            "ClientToken": connection.api_key_encrypted,
            "AccessToken": connection.base_url or "",  # Mews uses access token here
        }

    def test_connection(self, connection: PMSConnection) -> bool:
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(
                    f"{self.API_BASE}/configuration/get",
                    json=self._payload_base(connection),
                )
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def sync(self, db: Session, hotel_id: int, connection: PMSConnection) -> None:
        """Pull data from Mews.

        In production this would:
        1. POST /reservations/getAll with time filter
        2. Map Mews reservation/booking fields to our model
        3. POST /services/getAvailability for inventory
        4. Handle Mews cursor-based pagination
        """
        pass

    def push_rate(self, connection: PMSConnection, room_type_code: str, date: str, rate: float) -> bool:
        """Push rate via Mews updateRatePrice endpoint."""
        try:
            with httpx.Client(timeout=10) as client:
                payload = self._payload_base(connection)
                payload.update({
                    "RateId": room_type_code,
                    "PriceUpdates": [{
                        "StartUtc": f"{date}T00:00:00Z",
                        "EndUtc": f"{date}T23:59:59Z",
                        "Value": rate,
                    }],
                })
                resp = client.post(
                    f"{self.API_BASE}/rates/updatePrice",
                    json=payload,
                )
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
