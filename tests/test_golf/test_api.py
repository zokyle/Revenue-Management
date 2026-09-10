"""API tests for the golf app (players, courses, rounds, profile, strategy)."""

from datetime import date


def test_health(golf_client):
    r = golf_client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_pages_render(golf_client):
    for path in ("/", "/rounds", "/courses", "/strategy", "/caddie", "/bag"):
        assert golf_client.get(path).status_code == 200, path


def test_create_player_with_default_bag(golf_client):
    r = golf_client.post("/api/players", json={"name": "Kyle", "handicap_index": 14.2, "target_score": 79})
    assert r.status_code == 201
    body = r.json()
    codes = {c["code"] for c in body["clubs"]}
    assert {"D", "3w", "7i", "PW", "P"} <= codes and len(codes) == 14
    r2 = golf_client.put(f"/api/players/{body['id']}", json={"handicap_index": 12.5})
    assert r2.json()["handicap_index"] == 12.5
    # Club CRUD
    r3 = golf_client.post(f"/api/players/{body['id']}/clubs", json={"code": "2h", "name": "2 Hybrid", "category": "hybrid"})
    assert r3.status_code == 201
    assert golf_client.post(f"/api/players/{body['id']}/clubs", json={"code": "2h", "name": "dup", "category": "hybrid"}).status_code == 409
    assert golf_client.delete(f"/api/players/{body['id']}/clubs/{r3.json()['id']}").status_code == 204


def test_scorecard_import_and_hole_edit(golf_client):
    holes = [{"number": i, "par": 4 if i % 3 else 3, "yards": 400 if i % 3 else 170} for i in range(1, 19)]
    r = golf_client.post("/api/courses/import/scorecard", json={"name": "Quick GC", "holes": holes})
    assert r.status_code == 201, r.text
    course = r.json()
    assert course["par"] == sum(h["par"] for h in holes)
    assert len(course["holes"]) == 18
    # Add hazards to hole 1 and fetch its geometry.
    r2 = golf_client.put(f"/api/courses/{course['id']}/holes/1", json={
        "fairway_width_yards": 30,
        "features": [{"kind": "water", "side": "left", "start_yards": 220, "end_yards": 300, "offset_yards": 20, "label": "pond"}],
    })
    assert r2.status_code == 200, r2.text
    assert len(r2.json()["features"]) == 1
    geo = golf_client.get(f"/api/courses/{course['id']}/holes/1/geometry").json()
    assert geo["features"][0]["kind"] == "water" and geo["fairway"]["half_width"] == 15
    listing = golf_client.get("/api/courses").json()
    assert listing[0]["hole_count"] == 18


def test_json_course_validation(golf_client):
    bad = {"name": "Bad", "holes": [{"number": 1, "par": 4, "yards": 400}, {"number": 1, "par": 4, "yards": 380}]}
    assert golf_client.post("/api/courses", json=bad).status_code == 422


def test_round_logging_profile_and_strategy(golf_client, golf_player, golf_course):
    pid, cid = golf_player.id, golf_course.id
    r = golf_client.post(f"/api/players/{pid}/rounds", json={"course_id": cid, "played_on": date.today().isoformat(), "logging_mode": "full"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    shots = [
        {"sequence": 1, "club_code": "D", "shot_type": "tee", "lie_start": "tee", "start_distance_yards": 420, "lie_end": "fairway", "end_distance_yards": 180, "lateral_miss_yards": 6},
        {"sequence": 2, "club_code": "5i", "shot_type": "full", "lie_start": "fairway", "start_distance_yards": 180, "lie_end": "green", "end_distance_yards": 10},
        {"sequence": 3, "club_code": "P", "shot_type": "putt", "lie_start": "green", "start_distance_yards": 10, "lie_end": "green", "end_distance_yards": 1},
        {"sequence": 4, "club_code": "P", "shot_type": "putt", "lie_start": "green", "start_distance_yards": 1, "lie_end": "green", "end_distance_yards": 0, "holed": True},
    ]
    r2 = golf_client.put(f"/api/players/{pid}/rounds/{rid}/holes/1", json={"hole_number": 1, "par": 4, "score": 4, "putts": 2, "fairway_hit": True, "gir": True, "shots": shots})
    assert r2.status_code == 200, r2.text
    hole = r2.json()
    assert hole["hole_id"] is not None and len(hole["shots"]) == 4 and hole["shots"][0]["club_id"] is not None
    # Replacing the hole replaces its shots.
    r3 = golf_client.put(f"/api/players/{pid}/rounds/{rid}/holes/1", json={"hole_number": 1, "par": 4, "score": 5, "putts": 3, "shots": shots[:2]})
    assert len(r3.json()["shots"]) == 2
    golf_client.put(f"/api/players/{pid}/rounds/{rid}/holes/2", json={"hole_number": 2, "par": 3, "score": 4, "putts": 2, "penalties": 1})
    rnd = golf_client.get(f"/api/players/{pid}/rounds/{rid}").json()
    assert rnd["total_score"] == 9 and len(rnd["holes"]) == 2
    listing = golf_client.get(f"/api/players/{pid}/rounds").json()
    assert listing[0]["course_name"] == "Test Links" and listing[0]["holes_logged"] == 2
    # Profile reflects the logged data.
    prof = golf_client.get(f"/api/players/{pid}/profile").json()
    assert prof["rounds_count"] == 1 and prof["shots_count"] == 2
    assert prof["readiness_level"] == "cold"
    assert prof["data"]["tendencies"]["penalties_per_round"] == 1.0
    dash = golf_client.get(f"/api/players/{pid}/dashboard").json()
    assert dash["readiness"]["rounds_logged"] == 1 and dash["recent_rounds"][0]["score"] == 9
    # Strategy generation and retrieval.
    assert golf_client.get(f"/api/players/{pid}/strategy/{cid}").status_code == 404
    r4 = golf_client.post(f"/api/players/{pid}/strategy/{cid}", json={"objective": "break_80", "samples": 150})
    assert r4.status_code == 200, r4.text
    plan = r4.json()
    assert plan["expected_score"] > golf_course.par
    assert len(plan["data"]["holes"]) == 4
    h1 = plan["data"]["holes"][0]
    assert h1["tee"]["club"] and h1["map"]["features"]
    assert golf_client.get(f"/api/players/{pid}/strategy/{cid}").json()["id"] == plan["id"]
    assert len(golf_client.get(f"/api/players/{pid}/strategies").json()) == 1
    # Finishing the round.
    r5 = golf_client.put(f"/api/players/{pid}/rounds/{rid}", json={"completed": True})
    assert r5.json()["completed"] is True
    assert golf_client.delete(f"/api/players/{pid}/rounds/{rid}").status_code == 204


def test_strategy_requires_holes(golf_client, golf_player):
    r = golf_client.post("/api/courses", json={"name": "Empty"})
    cid = r.json()["id"]
    assert golf_client.post(f"/api/players/{golf_player.id}/strategy/{cid}", json={}).status_code == 422


def test_missing_player_404(golf_client):
    assert golf_client.get("/api/players/999").status_code == 404
    assert golf_client.get("/api/players/999/profile").status_code == 404


def test_review_regressions(golf_client, golf_player, golf_course):
    pid, cid = golf_player.id, golf_course.id
    # Explicit null on a NOT NULL column is ignored instead of crashing.
    r = golf_client.put(f"/api/players/{pid}", json={"name": None, "handicap_index": 9.5})
    assert r.status_code == 200 and r.json()["name"] == "Test Golfer" and r.json()["handicap_index"] == 9.5
    # Negative seed is a validation error, not a 404.
    assert golf_client.post(f"/api/players/{pid}/strategy/{cid}", json={"seed": -3}).status_code == 422
    # An empty round must not make the profile recompute on every read.
    golf_client.post(f"/api/players/{pid}/rounds", json={"course_id": cid})
    first = golf_client.get(f"/api/players/{pid}/profile").json()["id"]
    second = golf_client.get(f"/api/players/{pid}/profile").json()["id"]
    assert first == second
    # Duplicate shot sequences are renumbered rather than raising an integrity error.
    rid = golf_client.post(f"/api/players/{pid}/rounds", json={"course_id": cid}).json()["id"]
    shots = [
        {"sequence": 1, "club_code": "D", "shot_type": "tee", "lie_start": "tee", "start_distance_yards": 420, "lie_end": "rough", "end_distance_yards": 190},
        {"sequence": 1, "club_code": "7i", "shot_type": "full", "lie_start": "rough", "start_distance_yards": 190, "lie_end": "green", "end_distance_yards": 8},
        {"sequence": 1, "club_code": "P", "shot_type": "putt", "lie_start": "green", "start_distance_yards": 8, "lie_end": "green", "end_distance_yards": 0, "holed": True},
    ]
    r = golf_client.put(f"/api/players/{pid}/rounds/{rid}/holes/1", json={"hole_number": 1, "par": 4, "score": 3, "shots": shots})
    assert r.status_code == 200 and [s["sequence"] for s in r.json()["shots"]] == [1, 2, 3]
