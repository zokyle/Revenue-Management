"""Tests for rates API endpoints."""

from datetime import date


def test_create_rate_plan(client, sample_hotel, sample_room_types, sample_segments):
    resp = client.post(f"/api/properties/{sample_hotel.id}/rates", json={
        "name": "STD BAR",
        "room_type_id": sample_room_types[0].id,
        "segment_id": sample_segments[0].id,
        "base_rate": 189.0,
        "min_rate": 139.0,
        "max_rate": 329.0,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["base_rate"] == 189.0
    assert data["min_rate"] == 139.0


def test_list_rate_plans(client, sample_hotel, sample_rate_plans):
    resp = client.get(f"/api/properties/{sample_hotel.id}/rates")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1


def test_update_rate_plan(client, sample_hotel, sample_rate_plans):
    plan = sample_rate_plans[0]
    resp = client.put(f"/api/properties/{sample_hotel.id}/rates/{plan.id}", json={
        "base_rate": 199.0,
    })
    assert resp.status_code == 200
    assert resp.json()["base_rate"] == 199.0


def test_create_rate_override(client, sample_hotel, sample_rate_plans):
    plan = sample_rate_plans[0]
    resp = client.post(f"/api/properties/{sample_hotel.id}/rates/override", json={
        "rate_plan_id": plan.id,
        "date": date.today().isoformat(),
        "override_rate": 259.0,
        "reason": "Special event",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["override_rate"] == 259.0


def test_list_segments(client, sample_hotel, sample_segments):
    resp = client.get(f"/api/properties/{sample_hotel.id}/segments")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    assert data[0]["name"] == "BAR"
