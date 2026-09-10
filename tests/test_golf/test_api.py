"""API tests for the golf app (players, courses, rounds, profile, strategy)."""

from datetime import date

import pytest


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


def test_objective_and_seed_reach_the_engine(golf_client, golf_player, golf_course):
    pid, cid = golf_player.id, golf_course.id
    a = golf_client.post(f"/api/players/{pid}/strategy/{cid}", json={"objective": "min_expected", "samples": 120, "seed": 5}).json()
    assert a["data"]["risk_lambda"] == 0.0 and a["data"]["objective"] == "min_expected"
    b = golf_client.post(f"/api/players/{pid}/strategy/{cid}", json={"objective": "break_80", "samples": 120, "seed": 5}).json()
    assert b["data"]["risk_lambda"] == round(0.8 * (1 - 0.35), 3)
    c = golf_client.post(f"/api/players/{pid}/strategy/{cid}", json={"objective": "break_80", "samples": 120, "seed": 5}).json()
    assert [h["expected_strokes"] for h in b["data"]["holes"]] == [h["expected_strokes"] for h in c["data"]["holes"]]


def test_hole_feature_replacement(golf_client, golf_db, golf_course):
    from golf.models import HoleFeature

    cid = golf_course.id
    two = [{"kind": "bunker", "side": "left", "start_yards": 200, "end_yards": 220, "offset_yards": 15, "width_yards": 10},
           {"kind": "water", "side": "right", "start_yards": 250, "end_yards": 300, "offset_yards": 20}]
    r = golf_client.put(f"/api/courses/{cid}/holes/1", json={"features": two})
    assert r.status_code == 200 and len(r.json()["features"]) == 2
    r = golf_client.put(f"/api/courses/{cid}/holes/1", json={"features": two[:1]})
    assert len(r.json()["features"]) == 1
    hole_id = r.json()["id"]
    assert golf_db.query(HoleFeature).filter(HoleFeature.hole_id == hole_id).count() == 1
    r = golf_client.put(f"/api/courses/{cid}/holes/1", json={"fairway_width_yards": 40})
    assert len(r.json()["features"]) == 1 and r.json()["fairway_width_yards"] == 40
    r = golf_client.put(f"/api/courses/{cid}/holes/1", json={"features": []})
    assert r.json()["features"] == []


def test_narrative_endpoint_preview_and_commit(golf_client, golf_player, golf_course):
    pid, cid = golf_player.id, golf_course.id
    rid = golf_client.post(f"/api/players/{pid}/rounds", json={"course_id": cid, "logging_mode": "narrative"}).json()["id"]
    text = "Hole 1: driver in the fairway, 5 iron to 20 feet, two putts"
    preview = golf_client.post(f"/api/players/{pid}/rounds/{rid}/narrative", json={"text": text, "commit": False})
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["parser"] in ("heuristic", "claude") and body["holes"][0]["score"] == 4
    assert golf_client.get(f"/api/players/{pid}/rounds/{rid}").json()["holes"] == []
    saved = golf_client.post(f"/api/players/{pid}/rounds/{rid}/narrative", json={"text": text, "commit": True})
    assert saved.status_code == 200
    rnd = golf_client.get(f"/api/players/{pid}/rounds/{rid}").json()
    assert rnd["total_score"] == 4 and len(rnd["holes"][0]["shots"]) == 4
    assert rnd["holes"][0]["shots"][1]["start_distance_yards"] == pytest.approx(rnd["holes"][0]["shots"][0]["end_distance_yards"])


def test_profile_refreshes_after_quick_mode_edits(golf_client, golf_player, golf_course):
    pid, cid = golf_player.id, golf_course.id
    rid = golf_client.post(f"/api/players/{pid}/rounds", json={"course_id": cid, "logging_mode": "quick"}).json()["id"]
    golf_client.put(f"/api/players/{pid}/rounds/{rid}/holes/1", json={"hole_number": 1, "par": 4, "score": 6, "putts": 2, "penalties": 2})
    p1 = golf_client.get(f"/api/players/{pid}/profile").json()
    assert p1["data"]["tendencies"]["penalties_per_round"] == 2.0
    golf_client.put(f"/api/players/{pid}/rounds/{rid}/holes/2", json={"hole_number": 2, "par": 3, "score": 5, "putts": 3, "penalties": 1})
    p2 = golf_client.get(f"/api/players/{pid}/profile").json()
    assert p2["id"] != p1["id"] and p2["data"]["tendencies"]["penalties_per_round"] == 3.0
    # Editing a score without changing counts also refreshes.
    golf_client.put(f"/api/players/{pid}/rounds/{rid}/holes/2", json={"hole_number": 2, "par": 3, "score": 4, "putts": 2, "penalties": 1})
    p3 = golf_client.get(f"/api/players/{pid}/profile").json()
    assert p3["id"] != p2["id"]
    # And an unchanged database reuses the snapshot.
    assert golf_client.get(f"/api/players/{pid}/profile").json()["id"] == p3["id"]


def test_delete_course_keeps_rounds_and_drops_plans(golf_client, golf_player, golf_course):
    pid, cid = golf_player.id, golf_course.id
    rid = golf_client.post(f"/api/players/{pid}/rounds", json={"course_id": cid}).json()["id"]
    golf_client.post(f"/api/players/{pid}/strategy/{cid}", json={"samples": 120})
    assert golf_client.delete(f"/api/courses/{cid}").status_code == 204
    rnd = golf_client.get(f"/api/players/{pid}/rounds/{rid}").json()
    assert rnd["course_id"] is None
    assert golf_client.get(f"/api/players/{pid}/strategies").json() == []
