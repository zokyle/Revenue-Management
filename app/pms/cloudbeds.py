import httpx
from sqlalchemy.orm import Session

from app.models.pms_connection import PMSConnection
from app.pms.base import PMSAdapter


class CloudbedsAdapter(PMSAdapter):
    """Cloudbeds PMS integration.

    Cloudbeds API docs: https://hotels.cloudbeds.com/api/docs/
    Key endpoints:
    - GET /getReservations — list reservations
    - GET /getAvailability — room availability
    - PUT /putRoomRatesAvailability — update rates
    """

    API_BASE = "https://hotels.cloudbeds.com/api/v1.2"

    def _headers(self, connection: PMSConnection) -> dict:
        return {
            "Authorization": f"Bearer {connection.api_key_encrypted}",
            "Content-Type": "application/json",
        }

    def test_connection(self, connection: PMSConnection) -> bool:
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(
                    f"{self.API_BASE}/getHotelDetails",
                    headers=self._headers(connection),
                )
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def sync(self, db: Session, hotel_id: int, connection: PMSConnection) -> None:
        """Pull reservations from Cloudbeds and upsert into local DB.

        In production this would:
        1. GET /getReservations with date filters
        2. Map Cloudbeds reservation fields to our Reservation model
        3. Upsert based on confirmation number
        4. GET /getAvailability to update RoomInventory
        """
        # Placeholder — real implementation would call the Cloudbeds API
        # and transform the response into local model objects
        pass

    def push_rate(self, connection: PMSConnection, room_type_code: str, date: str, rate: float) -> bool:
        """Push rate to Cloudbeds via putRoomRatesAvailability endpoint."""
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(
                    f"{self.API_BASE}/putRoomRatesAvailability",
                    headers=self._headers(connection),
                    json={
                        "roomTypeID": room_type_code,
                        "startDate": date,
                        "endDate": date,
                        "roomRate": rate,
                    },
                )
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
