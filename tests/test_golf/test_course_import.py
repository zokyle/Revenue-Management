"""Tests for golf.engine.course_import (scorecard, JSON and OpenStreetMap importers)."""

from __future__ import annotations

import json
import math
from typing import Any

import httpx
import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import golf.models  # noqa: F401  -- populate Base.metadata
from golf.database import Base
from golf.engine.course_import import (
    build_course_from_scorecard,
    import_course_from_json,
    import_course_from_osm,
    latlon_to_xy,
    parse_distance_yards,
    polyline_length,
    project_onto_polyline,
    turn_info,
)
from golf.schemas import CourseCreate, OSMImportRequest, ScorecardImport


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# Scorecard
# ---------------------------------------------------------------------------
STANDARD_PARS = [4, 5, 3, 4, 4, 3, 4, 5, 4, 4, 3, 5, 4, 4, 4, 3, 5, 4]


def _scorecard_holes() -> list[dict[str, Any]]:
    holes = []
    for i, par in enumerate(STANDARD_PARS, start=1):
        yards = {3: 165, 4: 400, 5: 530}[par] + i
        holes.append({"number": i, "par": par, "yards": yards, "handicap_index": ((i * 7) % 18) + 1})
    return holes


def test_scorecard_build_creates_holes_with_par_defaults(db):
    holes = _scorecard_holes()
    payload = ScorecardImport(name="Card Links", city="Carmel", country="US", tee_name="Blue", holes=holes)
    course = build_course_from_scorecard(db, payload)

    assert course.id is not None
    assert course.source == "scorecard"
    assert course.tee_name == "Blue"
    assert len(course.holes) == 18
    assert course.par == sum(STANDARD_PARS) == 72
    assert course.yardage == sum(h["yards"] for h in holes)
    assert [h.number for h in course.holes] == list(range(1, 19))
    for hole, spec in zip(course.holes, holes):
        assert hole.par == spec["par"]
        assert hole.yards == spec["yards"]
        assert hole.handicap_index == spec["handicap_index"]
        assert hole.features == []
        if hole.par == 3:
            assert hole.fairway_start_yards == hole.yards
            assert hole.green_width_yards == 28 and hole.green_depth_yards == 28
        elif hole.par == 4:
            assert hole.fairway_start_yards == 100 and hole.fairway_width_yards == 35
        else:
            assert hole.fairway_width_yards == 38


def test_scorecard_rejects_duplicate_numbers(db):
    payload = ScorecardImport(name="Bad", holes=[
        {"number": 1, "par": 4, "yards": 400}, {"number": 1, "par": 3, "yards": 150},
    ])
    with pytest.raises(ValueError, match="Duplicate hole numbers: 1"):
        build_course_from_scorecard(db, payload)


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------
def _json_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "name": "JSON National", "latitude": 36.5, "longitude": -121.9, "slope": 131,
        "holes": [
            {
                "number": 1, "par": 4, "yards": 410, "shape": "dogleg_right", "dogleg_at_yards": 250,
                "dogleg_angle_deg": 30, "fairway_width_yards": 32,
                "features": [
                    {"kind": "water", "side": "left", "start_yards": 200, "end_yards": 300, "offset_yards": 18, "width_yards": 40, "label": "pond"},
                    {"kind": "bunker", "side": "right", "start_yards": 240, "end_yards": 262, "offset_yards": 14, "width_yards": 8},
                ],
            },
            {"number": 2, "par": 3, "yards": 170, "features": [
                {"kind": "ob", "side": "left", "start_yards": 0, "end_yards": 170, "offset_yards": 30},
            ]},
        ],
    }
    payload.update(overrides)
    return payload


def test_json_import_round_trips_features(db):
    course = import_course_from_json(db, CourseCreate(**_json_payload()))
    assert course.source == "json"
    assert course.par == 7 and course.yardage == 580
    assert course.latitude == 36.5 and course.slope == 131
    h1, h2 = course.holes
    assert h1.shape == "dogleg_right" and h1.dogleg_at_yards == 250 and h1.fairway_width_yards == 32
    assert [(f.kind, f.side, f.start_yards, f.end_yards) for f in h1.features] == [
        ("water", "left", 200, 300), ("bunker", "right", 240, 262),
    ]
    assert h1.features[0].label == "pond" and h1.features[0].width_yards == 40
    assert h2.features[0].kind == "ob" and h2.features[0].width_yards == 999


def test_json_import_rejects_duplicate_hole_numbers(db):
    payload = _json_payload()
    payload["holes"][1]["number"] = 1
    with pytest.raises(ValueError, match="Duplicate hole numbers"):
        import_course_from_json(db, CourseCreate(**payload))


def test_json_import_rejects_bad_side_kind_and_extent(db):
    bad_side = _json_payload()
    bad_side["holes"][0]["features"][0]["side"] = "port"
    with pytest.raises(ValueError, match="side"):
        import_course_from_json(db, CourseCreate(**bad_side))

    bad_kind = _json_payload()
    bad_kind["holes"][0]["features"][0]["kind"] = "lava"
    with pytest.raises(ValueError, match="kind"):
        import_course_from_json(db, CourseCreate(**bad_kind))

    reversed_box = _json_payload()
    reversed_box["holes"][0]["features"][1].update({"start_yards": 300, "end_yards": 250})
    with pytest.raises(ValueError, match="end_yards"):
        import_course_from_json(db, CourseCreate(**reversed_box))


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------
def test_project_onto_straight_north_line():
    line = np.array([[0.0, 0.0], [0.0, 400.0]])
    pts = np.array([[10.0, 50.0], [-10.0, 120.0], [0.0, 250.0], [5.0, 430.0], [3.0, -20.0]])
    x, y = project_onto_polyline(pts, line)
    assert np.allclose(x, [50, 120, 250, 430, -20])   # end segments extrapolate
    assert np.allclose(y, [10, -10, 0, 5, 3])          # east of a northbound line is right (+)
    assert polyline_length(line) == pytest.approx(400)


def test_project_lateral_sign_follows_direction_of_travel():
    east_line = np.array([[0.0, 0.0], [300.0, 0.0]])
    x, y = project_onto_polyline(np.array([[100.0, 20.0], [200.0, -15.0]]), east_line)
    assert np.allclose(x, [100, 200])
    assert np.allclose(y, [-20, 15])  # north of an eastbound line is on the left


def test_project_onto_dogleg_measures_arc_length():
    line = np.array([[0.0, 0.0], [0.0, 200.0], [150.0, 200.0]])
    assert polyline_length(line) == pytest.approx(350)
    x, y = project_onto_polyline(np.array([[100.0, 190.0], [-8.0, 100.0]]), line)
    assert x[0] == pytest.approx(300) and y[0] == pytest.approx(10)   # south of the eastbound leg = right
    assert x[1] == pytest.approx(100) and y[1] == pytest.approx(-8)


def test_turn_info_detects_right_dogleg():
    line = np.array([[0.0, 0.0], [0.0, 200.0], [150.0, 200.0]])
    shape, at, angle = turn_info(line)
    assert shape == "dogleg_right"
    assert at == pytest.approx(200, abs=1)
    assert angle == pytest.approx(90, abs=0.5)

    left = np.array([[0.0, 0.0], [0.0, 200.0], [-120.0, 300.0]])
    shape, at, angle = turn_info(left)
    assert shape == "dogleg_left" and at == pytest.approx(200, abs=1)
    assert 45 < angle < 55

    gentle = np.array([[0.0, 0.0], [0.0, 200.0], [30.0, 400.0]])
    assert turn_info(gentle) == ("straight", None, None)
    assert turn_info(np.array([[0.0, 0.0], [0.0, 400.0]])) == ("straight", None, None)


def test_parse_distance_yards_units():
    assert parse_distance_yards("402 yd") == pytest.approx(402)
    assert parse_distance_yards("367 m") == pytest.approx(367 * 1.09361)
    assert parse_distance_yards("1200 ft") == pytest.approx(400)
    assert parse_distance_yards("380") == pytest.approx(380 * 1.09361)          # bare value = metres
    assert parse_distance_yards("380", reference_yards=382) == pytest.approx(380)  # unless yards fits better
    assert parse_distance_yards("700") == pytest.approx(700)                       # too long to be metres
    assert parse_distance_yards(None) is None and parse_distance_yards("long") is None


# ---------------------------------------------------------------------------
# OpenStreetMap
# ---------------------------------------------------------------------------
LAT0, LON0 = 36.57, -121.95
YARDS_PER_METRE = 1.09361


def xy_to_latlon(x_yd: float, y_yd: float) -> dict[str, float]:
    """Invert the module's equirectangular projection (east/north yards -> lat/lon)."""
    x_m, y_m = x_yd / YARDS_PER_METRE, y_yd / YARDS_PER_METRE
    return {
        "lat": LAT0 + y_m / 110540.0,
        "lon": LON0 + x_m / (math.cos(math.radians(LAT0)) * 111320.0),
    }


def way(osm_id: int, tags: dict[str, str], points_xy: list[tuple[float, float]]) -> dict[str, Any]:
    return {"type": "way", "id": osm_id, "tags": tags, "geometry": [xy_to_latlon(x, y) for x, y in points_xy]}


def rect(x0: float, x1: float, y0: float, y1: float) -> list[tuple[float, float]]:
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]


def synthetic_overpass() -> dict[str, Any]:
    """Two holes running due north.

    Hole 1: par 4, tee (0, 0) -> green (0, 400); fairway 100..370 yds, 34 wide;
    bunker on the right at 240..260; water on the left at 180..300.
    Hole 2: par 3 at x = +150, tee (150, 0) -> green (150, 160), 30x28 green.
    """
    return {"elements": [
        way(101, {"golf": "hole", "ref": "1", "par": "4", "dist": "400 yd", "handicap": "5", "golf:course": "Synthetic Dunes"},
            [(0, 0), (0, 400)]),
        way(102, {"golf": "hole", "ref": "2", "par": "3", "dist": "146 m", "handicap": "17", "golf:course": "Synthetic Dunes"},
            [(150, 0), (150, 160)]),
        way(103, {"golf": "hole", "ref": "1", "par": "5"}, [(0, 0), (0, 500)]),      # duplicate number: ignored
        way(201, {"golf": "fairway"}, rect(-17, 17, 100, 370)),
        way(202, {"golf": "bunker"}, rect(12, 20, 240, 260)),
        way(203, {"golf": "water_hazard"}, rect(-45, -25, 180, 300)),
        way(204, {"golf": "green"}, rect(135, 165, 146, 174)),
        way(205, {"golf": "tee"}, rect(-5, 5, -5, 5)),                                # ignored
        way(206, {"golf": "bunker"}, rect(600, 610, 600, 620)),                       # too far from any hole
        way(207, {"golf": "hole", "ref": "3"}, [(300, 0)]),                            # degenerate: single node
        {"type": "relation", "id": 301, "tags": {"golf": "bunker"}, "members": [
            {"type": "way", "ref": 9, "role": "outer", "geometry": [xy_to_latlon(x, y) for x, y in rect(-22, -14, 380, 392)]},
        ]},
        {"type": "relation", "id": 302, "tags": {"golf": "green"}, "members": []},   # skipped with a warning
    ]}


def make_client(overpass_payload: Any = None, nominatim_payload: Any = None, overpass_status: int = 200,
                seen: list[httpx.Request] | None = None) -> httpx.Client:
    """httpx client whose transport routes by host to canned OSM responses."""
    overpass_payload = synthetic_overpass() if overpass_payload is None else overpass_payload

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        host = request.url.host
        if host == "nominatim.openstreetmap.org":
            return httpx.Response(200, json=nominatim_payload if nominatim_payload is not None else [])
        if host == "overpass-api.de":
            return httpx.Response(overpass_status, json=overpass_payload)
        return httpx.Response(404, text=f"unexpected host {host}")

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_osm_import_with_mock_transport(db):
    seen: list[httpx.Request] = []
    client = make_client(seen=seen)
    req = OSMImportRequest(latitude=LAT0, longitude=LON0, radius_m=1500, tee_name="Gold")
    course = import_course_from_osm(db, req, client=client)

    # One Overpass request carrying the location and radius; no Nominatim call.
    assert [r.url.host for r in seen] == ["overpass-api.de"]
    body = seen[0].content.decode()
    assert "golf" in body and "36.57" in body and "1500" in body

    assert course.source == "osm"
    assert course.osm_id == "101"
    assert course.name == "Synthetic Dunes"          # from the golf:course tag
    assert course.latitude == LAT0 and course.longitude == LON0
    assert course.tee_name == "Gold"
    assert [h.number for h in course.holes] == [1, 2]
    assert course.par == 7
    assert course.yardage == sum(h.yards for h in course.holes)

    h1, h2 = course.holes
    assert h1.par == 4 and h1.handicap_index == 5 and h1.shape == "straight"
    assert abs(h1.yards - 400) <= 400 * 0.05
    assert h2.par == 3 and h2.handicap_index == 17
    assert abs(h2.yards - 160) <= 160 * 0.05

    # Fairway: width from the polygon (34) and start at its near end (100).
    assert 20 <= h1.fairway_width_yards <= 60
    assert h1.fairway_width_yards == pytest.approx(34, abs=2)
    assert h1.fairway_start_yards == pytest.approx(100, abs=3)

    # Features are ordered by start_yards: water (180), fairway bunker (240), greenside bunker (380).
    assert [(f.kind, f.side) for f in h1.features] == [("water", "left"), ("bunker", "right"), ("bunker", "left")]
    water, bunker, greenside = h1.features
    assert abs(bunker.start_yards - 240) <= 15 and abs(bunker.end_yards - 260) <= 15
    assert bunker.offset_yards == pytest.approx(12, abs=1) and bunker.width_yards == pytest.approx(8, abs=1)
    assert bunker.label.startswith("bunker right at")
    assert water.start_yards == pytest.approx(180, abs=2) and water.end_yards == pytest.approx(300, abs=2)
    assert water.offset_yards == pytest.approx(25, abs=1) and water.width_yards == pytest.approx(20, abs=1)
    # The greenside bunker came from a relation's outer member, 18 yds left of hole 1's centerline.
    assert greenside.start_yards == pytest.approx(380, abs=2) and greenside.end_yards == pytest.approx(392, abs=2)
    assert greenside.offset_yards == pytest.approx(14, abs=1)
    assert sum(1 for h in course.holes for f in h.features if f.kind == "bunker") == 2  # far-away bunker dropped

    # Green dims on the par 3; par-3 fairway default (no fairway polygon there).
    assert h2.green_width_yards == pytest.approx(30, abs=1)
    assert h2.green_depth_yards == pytest.approx(28, abs=1)
    assert h2.fairway_start_yards == h2.yards
    assert h2.features == []


def test_osm_import_resolves_name_via_nominatim(db):
    seen: list[httpx.Request] = []
    nominatim = [{"lat": str(LAT0), "lon": str(LON0), "display_name": "Synthetic Dunes, Carmel",
                  "address": {"city": "Carmel", "country": "United States"}}]
    client = make_client(nominatim_payload=nominatim, seen=seen)
    course = import_course_from_osm(db, OSMImportRequest(name="Synthetic Dunes"), client=client)

    assert [r.url.host for r in seen] == ["nominatim.openstreetmap.org", "overpass-api.de"]
    nominatim_req = seen[0]
    assert nominatim_req.url.params["q"] == "Synthetic Dunes golf"
    assert nominatim_req.url.params["format"] == "json"
    assert nominatim_req.headers["user-agent"] == "caddie-golf-app/0.1"
    assert course.name == "Synthetic Dunes"
    assert course.latitude == pytest.approx(LAT0) and course.longitude == pytest.approx(LON0)
    assert course.city == "Carmel" and course.country == "United States"
    assert len(course.holes) == 2


def test_osm_import_name_not_found(db):
    client = make_client(nominatim_payload=[])
    with pytest.raises(ValueError, match="Course not found on OpenStreetMap"):
        import_course_from_osm(db, OSMImportRequest(name="Nowhere Links"), client=client)


def test_osm_import_no_holes(db):
    client = make_client(overpass_payload={"elements": [way(1, {"golf": "bunker"}, rect(0, 5, 0, 5))]})
    with pytest.raises(ValueError, match="No golf holes found on OpenStreetMap"):
        import_course_from_osm(db, OSMImportRequest(latitude=LAT0, longitude=LON0), client=client)


def test_osm_import_wraps_http_errors(db):
    client = make_client(overpass_status=504)
    with pytest.raises(RuntimeError, match="OpenStreetMap request failed"):
        import_course_from_osm(db, OSMImportRequest(latitude=LAT0, longitude=LON0), client=client)

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    with httpx.Client(transport=httpx.MockTransport(boom)) as failing:
        with pytest.raises(RuntimeError, match="OpenStreetMap request failed"):
            import_course_from_osm(db, OSMImportRequest(latitude=LAT0, longitude=LON0), client=failing)

    with pytest.raises(ValueError, match="course name or latitude/longitude"):
        import_course_from_osm(db, OSMImportRequest(), client=make_client())


def test_osm_dogleg_and_fallbacks(db):
    """A hole without ref/par/dist: par from length, dogleg from the centerline."""
    payload = {"elements": [
        way(1, {"golf": "hole", "name": "Elbow"}, [(0, 0), (0, 250), (180, 250)]),   # 430 yds, right turn
        way(2, {"golf": "hole", "ref": "7", "dist": "150"}, [(400, 0), (400, 165)]),  # bare dist -> metres
    ]}
    course = import_course_from_osm(db, OSMImportRequest(latitude=LAT0, longitude=LON0), client=make_client(payload))
    assert course.name == "Imported course"
    assert [h.number for h in course.holes] == [1, 2]     # renumbered 1..N: ref 7 first, unnumbered last
    seven, elbow = course.holes
    assert elbow.par == 4 and abs(elbow.yards - 430) <= 2
    assert elbow.shape == "dogleg_right" and elbow.dogleg_at_yards == pytest.approx(250, abs=1)
    assert elbow.dogleg_angle_deg == pytest.approx(90, abs=0.5)
    assert elbow.notes == "Elbow"
    assert seven.par == 3 and seven.yards == round(150 * YARDS_PER_METRE)


def test_latlon_projection_round_trip():
    pts = latlon_to_xy([xy_to_latlon(120, -80)["lat"]], [xy_to_latlon(120, -80)["lon"]], LAT0, LON0)
    assert np.allclose(pts, [[120, -80]], atol=1e-6)
    # JSON-serialisable synthetic payload (guards the test helpers themselves).
    json.dumps(synthetic_overpass())
