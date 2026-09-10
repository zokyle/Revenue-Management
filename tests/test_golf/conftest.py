"""Fixtures for the golf app tests (independent SQLite file per test)."""

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from golf.database import Base, get_db
from golf.main import app
from golf.models import Club, Course, Hole, HoleFeature, Player  # noqa: F401
from golf import services

TEST_DB_URL = "sqlite:///./test_golf.db"


@pytest.fixture
def golf_db():
    engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        try:
            os.remove("./test_golf.db")
        except OSError:
            pass


@pytest.fixture
def golf_client(golf_db):
    from fastapi.testclient import TestClient

    def override_get_db():
        try:
            yield golf_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def golf_player(golf_db):
    player = Player(name="Test Golfer", handicap_index=14.0, target_score=79, risk_tolerance=0.35)
    golf_db.add(player)
    golf_db.commit()
    golf_db.refresh(player)
    services.create_default_bag(golf_db, player)
    return services.get_player(golf_db, player.id)


@pytest.fixture
def golf_course(golf_db):
    """A 4-hole course exercising par 3/4/5 and a dogleg with hazards."""
    course = Course(name="Test Links", city="Nowhere", source="manual", tee_name="White")
    golf_db.add(course)
    golf_db.flush()
    spec = [
        (1, 4, 420, "straight", None, None, [("water", "left", 230, 300, 22, 999, "pond left"), ("ob", "right", 0, 420, 35, 999, "OB right")]),
        (2, 3, 165, "straight", None, None, [("water", "short", 120, 157, 0, 40, "pond short"), ("bunker", "right", 150, 175, 14, 12, "bunker right")]),
        (3, 5, 530, "straight", None, None, [("creek", "center", 262, 276, 0, 999, "creek"), ("water", "right", 430, 530, 18, 999, "lake right")]),
        (4, 4, 390, "dogleg_right", 230, 40, [("trees", "right", 150, 260, 20, 999, "trees inside corner")]),
    ]
    for number, par, yards, shape, dl_at, dl_ang, feats in spec:
        hole = Hole(course_id=course.id, number=number, par=par, yards=yards, shape=shape, dogleg_at_yards=dl_at,
                    dogleg_angle_deg=dl_ang, fairway_start_yards=(yards if par == 3 else 100))
        golf_db.add(hole)
        golf_db.flush()
        for kind, side, start, end, offset, width, label in feats:
            golf_db.add(HoleFeature(hole_id=hole.id, kind=kind, side=side, start_yards=start, end_yards=end,
                                    offset_yards=offset, width_yards=width, label=label))
    golf_db.commit()
    course = services.get_course(golf_db, course.id)
    services.refresh_course_totals(golf_db, course)
    return course
