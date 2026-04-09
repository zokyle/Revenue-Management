"""Shared test fixtures."""

import pytest
from datetime import date, datetime, timedelta
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session as SASession

from app.database import Base, get_db
from app.main import app
from app.models.property import Hotel, RoomType
from app.models.segments import MarketSegment, Channel
from app.models.rates import RatePlan
from app.models.costs import CostProfile, CostItem
from app.models.inventory import Reservation, ReservationStatus

# Use file-based SQLite for tests so TestClient and fixtures share data
TEST_DB_URL = "sqlite:///./test_revenue.db"


@pytest.fixture
def db_session():
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
        import os
        try:
            os.remove("./test_revenue.db")
        except OSError:
            pass


@pytest.fixture
def client(db_session):
    from fastapi.testclient import TestClient

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def sample_hotel(db_session):
    hotel = Hotel(
        name="Test Hotel",
        city="Test City",
        country="US",
        total_rooms=100,
        star_rating=4.0,
        currency="USD",
        pricing_aggressiveness=0.5,
        rate_protection=0.7,
        high_demand_threshold=0.85,
        low_demand_threshold=0.40,
    )
    db_session.add(hotel)
    db_session.commit()
    db_session.refresh(hotel)
    return hotel


@pytest.fixture
def sample_room_types(db_session, sample_hotel):
    types = [
        RoomType(hotel_id=sample_hotel.id, name="Standard", code="STD", physical_rooms=50, sort_order=0),
        RoomType(hotel_id=sample_hotel.id, name="Deluxe", code="DLX", physical_rooms=30, sort_order=1),
        RoomType(hotel_id=sample_hotel.id, name="Suite", code="STE", physical_rooms=20, sort_order=2),
    ]
    db_session.add_all(types)
    db_session.commit()
    for t in types:
        db_session.refresh(t)
    return types


@pytest.fixture
def sample_segments(db_session, sample_hotel):
    segments = [
        MarketSegment(hotel_id=sample_hotel.id, name="BAR", discount_pct_from_bar=0, priority=1),
        MarketSegment(hotel_id=sample_hotel.id, name="Corporate", discount_pct_from_bar=15, priority=2),
        MarketSegment(hotel_id=sample_hotel.id, name="OTA", discount_pct_from_bar=5, priority=3),
    ]
    db_session.add_all(segments)
    db_session.commit()
    for s in segments:
        db_session.refresh(s)
    return segments


@pytest.fixture
def sample_channels(db_session, sample_hotel):
    channels = [
        Channel(hotel_id=sample_hotel.id, name="Direct", commission_pct=0),
        Channel(hotel_id=sample_hotel.id, name="Booking.com", commission_pct=15),
    ]
    db_session.add_all(channels)
    db_session.commit()
    for c in channels:
        db_session.refresh(c)
    return channels


@pytest.fixture
def sample_rate_plans(db_session, sample_hotel, sample_room_types, sample_segments):
    plans = [
        RatePlan(
            hotel_id=sample_hotel.id,
            room_type_id=sample_room_types[0].id,
            segment_id=sample_segments[0].id,
            name="STD BAR",
            base_rate=189.0,
            min_rate=139.0,
            max_rate=329.0,
        ),
        RatePlan(
            hotel_id=sample_hotel.id,
            room_type_id=sample_room_types[1].id,
            segment_id=sample_segments[0].id,
            name="DLX BAR",
            base_rate=249.0,
            min_rate=179.0,
            max_rate=429.0,
        ),
    ]
    db_session.add_all(plans)
    db_session.commit()
    for p in plans:
        db_session.refresh(p)
    return plans


@pytest.fixture
def sample_cost_profile(db_session, sample_hotel):
    profile = CostProfile(
        hotel_id=sample_hotel.id,
        name="Standard",
        cpor=45.0,
        fixed_daily_cost=12000.0,
        variable_cost_pct=5.0,
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)

    items = [
        CostItem(cost_profile_id=profile.id, category="Housekeeping", amount_per_room=18, is_variable=True),
        CostItem(cost_profile_id=profile.id, category="Amenities", amount_per_room=8, is_variable=True),
        CostItem(cost_profile_id=profile.id, category="Utilities", amount_per_room=7, is_variable=True),
    ]
    db_session.add_all(items)
    db_session.commit()
    return profile


@pytest.fixture
def sample_reservations(db_session, sample_hotel, sample_room_types, sample_segments, sample_channels):
    """Generate 90 days of historical reservations for testing."""
    import random
    random.seed(42)

    reservations = []
    today = date.today()
    rt = sample_room_types[0]  # Standard rooms

    for days_ago in range(90, 0, -1):
        check_in = today - timedelta(days=days_ago)
        # Vary occupancy: weekends higher
        dow = check_in.weekday()
        base_occ = 0.65 if dow < 5 else 0.82
        num_rooms = int(rt.physical_rooms * (base_occ + random.uniform(-0.1, 0.1)))
        num_rooms = max(5, min(num_rooms, rt.physical_rooms))

        for i in range(num_rooms):
            nights = random.choices([1, 2, 3, 4], weights=[35, 30, 20, 15])[0]
            rate = 189 * (1 + random.uniform(-0.15, 0.15))
            lead_time = random.randint(1, 60)

            res = Reservation(
                hotel_id=sample_hotel.id,
                room_type_id=rt.id,
                segment_id=sample_segments[random.randint(0, len(sample_segments) - 1)].id,
                channel_id=sample_channels[random.randint(0, len(sample_channels) - 1)].id,
                confirmation_number=f"TEST-{days_ago:03d}-{i:03d}",
                guest_name=f"Guest {days_ago}-{i}",
                check_in=check_in,
                check_out=check_in + timedelta(days=nights),
                nights=nights,
                rate_amount=round(rate, 2),
                status=ReservationStatus.CHECKED_OUT,
                booking_date=datetime.combine(check_in - timedelta(days=lead_time), datetime.min.time()),
            )
            reservations.append(res)

    db_session.add_all(reservations)
    db_session.commit()
    return reservations
