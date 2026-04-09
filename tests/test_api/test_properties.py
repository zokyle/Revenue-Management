"""Tests for properties API endpoints."""


def test_create_hotel(client):
    resp = client.post("/api/properties", json={
        "name": "Test Hotel",
        "total_rooms": 100,
        "city": "NYC",
        "currency": "USD",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Hotel"
    assert data["total_rooms"] == 100
    assert data["id"] is not None


def test_list_hotels(client, sample_hotel):
    resp = client.get("/api/properties")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["name"] == "Test Hotel"


def test_get_hotel(client, sample_hotel):
    resp = client.get(f"/api/properties/{sample_hotel.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Test Hotel"
    assert "room_types" in data


def test_update_hotel(client, sample_hotel):
    resp = client.put(f"/api/properties/{sample_hotel.id}", json={
        "name": "Updated Hotel",
        "pricing_aggressiveness": 0.8,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Updated Hotel"
    assert data["pricing_aggressiveness"] == 0.8


def test_get_nonexistent_hotel(client):
    resp = client.get("/api/properties/999")
    assert resp.status_code == 404


def test_create_room_type(client, sample_hotel):
    resp = client.post(f"/api/properties/{sample_hotel.id}/room-types", json={
        "name": "Standard King",
        "code": "STD",
        "physical_rooms": 50,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Standard King"
    assert data["physical_rooms"] == 50
