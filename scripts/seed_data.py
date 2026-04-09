"""
Seed data script for Hotel Revenue Management demo.

Generates realistic historical and future reservation data for
"The Grand Metropolitan" boutique hotel.

Usage:
    python scripts/seed_data.py
"""

import sys
import os
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

# Ensure project root is on sys.path so `app` is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import engine, SessionLocal, Base
from app.models import (
    Hotel,
    RoomType,
    RoomInventory,
    Reservation,
    RatePlan,
    MarketSegment,
    Channel,
    CostProfile,
    CostItem,
)
from app.models.inventory import ReservationStatus

# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------
RNG = np.random.default_rng(42)

TODAY = date.today()  # 2026-04-09

# ---------------------------------------------------------------------------
# Guest name pool (no faker dependency)
# ---------------------------------------------------------------------------
FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael",
    "Linda", "David", "Elizabeth", "William", "Barbara", "Richard", "Susan",
    "Joseph", "Jessica", "Thomas", "Sarah", "Christopher", "Karen",
    "Charles", "Lisa", "Daniel", "Nancy", "Matthew", "Betty", "Anthony",
    "Margaret", "Mark", "Sandra", "Donald", "Ashley", "Steven", "Kimberly",
    "Paul", "Emily", "Andrew", "Donna", "Joshua", "Michelle", "Kenneth",
    "Carol", "Kevin", "Amanda", "Brian", "Dorothy", "George", "Melissa",
    "Timothy", "Deborah", "Ronald", "Stephanie", "Edward", "Rebecca",
    "Jason", "Sharon", "Jeffrey", "Laura", "Ryan", "Cynthia",
    "Jacob", "Kathleen", "Gary", "Amy", "Nicholas", "Angela", "Eric",
    "Shirley", "Jonathan", "Anna", "Stephen", "Brenda", "Larry", "Pamela",
    "Justin", "Emma", "Scott", "Nicole", "Brandon", "Helen", "Benjamin",
    "Samantha", "Samuel", "Katherine", "Raymond", "Christine", "Gregory",
    "Debra", "Frank", "Rachel", "Alexander", "Carolyn", "Patrick", "Janet",
    "Jack", "Catherine", "Dennis", "Maria", "Jerry", "Heather", "Tyler",
    "Diane",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
    "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
    "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark",
    "Ramirez", "Lewis", "Robinson", "Walker", "Young", "Allen", "King",
    "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores", "Green",
    "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell",
    "Carter", "Roberts", "Gomez", "Phillips", "Evans", "Turner", "Diaz",
    "Parker", "Cruz", "Edwards", "Collins", "Reyes", "Stewart", "Morris",
    "Morales", "Murphy", "Cook", "Rogers", "Gutierrez", "Ortiz", "Morgan",
    "Cooper", "Peterson", "Bailey", "Reed", "Kelly", "Howard", "Ramos",
    "Kim", "Cox", "Ward", "Richardson", "Watson", "Brooks", "Chavez",
    "Wood", "James", "Bennett", "Gray", "Mendoza", "Ruiz", "Hughes",
    "Price", "Alvarez", "Castillo", "Sanders", "Patel", "Myers", "Long",
    "Ross", "Foster", "Jimenez",
]


def random_guest_name() -> str:
    return f"{RNG.choice(FIRST_NAMES)} {RNG.choice(LAST_NAMES)}"


# ---------------------------------------------------------------------------
# Helper: seasonal / DOW occupancy multiplier
# ---------------------------------------------------------------------------

def _seasonal_factor(d: date) -> float:
    """Return a multiplier 0-1 for seasonal demand."""
    month = d.month
    factors = {
        1: 0.55, 2: 0.55,             # low winter
        3: 0.68, 4: 0.72, 5: 0.78,    # spring ramp
        6: 0.88, 7: 0.92, 8: 0.90,    # summer peak
        9: 0.85, 10: 0.75, 11: 0.68,  # autumn decline
        12: 0.82,                       # holiday bump
    }
    return factors[month]


def _dow_factor(d: date) -> float:
    """Return a multiplier for day-of-week (0=Mon .. 6=Sun)."""
    dow = d.weekday()
    factors = {
        0: 0.78,  # Mon
        1: 0.85,  # Tue
        2: 0.85,  # Wed
        3: 0.82,  # Thu
        4: 0.95,  # Fri
        5: 0.98,  # Sat
        6: 0.72,  # Sun
    }
    return factors[dow]


def target_occupancy(d: date) -> float:
    """Combine seasonal and DOW factors into a target occupancy in [0.45, 0.95]."""
    raw = _seasonal_factor(d) * _dow_factor(d)
    # Scale into desired range
    occ = 0.45 + (0.95 - 0.45) * raw
    return float(np.clip(occ, 0.45, 0.95))


# ---------------------------------------------------------------------------
# Confirmation number generator
# ---------------------------------------------------------------------------
_confirmation_counter = 0


def next_confirmation() -> str:
    global _confirmation_counter
    _confirmation_counter += 1
    return f"RES-{_confirmation_counter:06d}"


# ---------------------------------------------------------------------------
# Truncate all tables
# ---------------------------------------------------------------------------

# Tables in dependency-safe deletion order (children before parents)
_TABLE_DELETE_ORDER = [
    "pricing_recommendations",
    "forecast_records",
    "rate_overrides",
    "los_restrictions",
    "rate_plans",
    "room_inventory",
    "reservations",
    "cost_items",
    "cost_profiles",
    "channels",
    "market_segments",
    "room_types",
    "pms_connections",
    "hotels",
]


def truncate_all(session) -> None:
    """Delete all rows from every table in safe order."""
    print("Clearing existing data ...")
    for tbl in _TABLE_DELETE_ORDER:
        session.execute(Base.metadata.tables[tbl].delete())
    session.commit()
    print("  Done.\n")


# ---------------------------------------------------------------------------
# Seed functions
# ---------------------------------------------------------------------------

def seed_hotel(session) -> Hotel:
    print("Creating hotel ...")
    hotel = Hotel(
        name="The Grand Metropolitan",
        address="789 Park Avenue",
        city="New York",
        country="USA",
        total_rooms=150,
        star_rating=4.5,
        currency="USD",
        timezone="America/New_York",
        pricing_aggressiveness=0.5,
        rate_protection=0.7,
        high_demand_threshold=0.85,
        low_demand_threshold=0.40,
    )
    session.add(hotel)
    session.flush()  # get hotel.id
    print(f"  Hotel id={hotel.id}\n")
    return hotel


def seed_room_types(session, hotel_id: int) -> dict:
    """Returns {code: RoomType} after flush."""
    print("Creating room types ...")
    specs = [
        ("Standard King", "STD", 2, 2, 60, 1),
        ("Deluxe Double", "DLX", 2, 3, 40, 2),
        ("Junior Suite", "JRS", 2, 4, 30, 3),
        ("Executive Suite", "EXS", 2, 4, 20, 4),
    ]
    room_types = {}
    for name, code, base_cap, max_cap, rooms, sort in specs:
        rt = RoomType(
            hotel_id=hotel_id,
            name=name,
            code=code,
            base_capacity=base_cap,
            max_capacity=max_cap,
            physical_rooms=rooms,
            sort_order=sort,
        )
        session.add(rt)
        session.flush()
        room_types[code] = rt
        print(f"  {code} - {name} ({rooms} rooms) id={rt.id}")
    print()
    return room_types


def seed_segments(session, hotel_id: int) -> dict:
    """Returns {name: MarketSegment}."""
    print("Creating market segments ...")
    specs = [
        ("BAR", 0.0, 1),
        ("Corporate", 15.0, 2),
        ("OTA", 5.0, 3),
        ("Group", 20.0, 4),
        ("Government", 25.0, 5),
        ("Wholesale", 30.0, 6),
    ]
    segments = {}
    for name, disc, pri in specs:
        seg = MarketSegment(
            hotel_id=hotel_id,
            name=name,
            discount_pct_from_bar=disc,
            priority=pri,
        )
        session.add(seg)
        session.flush()
        segments[name] = seg
        print(f"  {name} (discount={disc}%, priority={pri}) id={seg.id}")
    print()
    return segments


def seed_channels(session, hotel_id: int) -> dict:
    """Returns {name: Channel}."""
    print("Creating channels ...")
    specs = [
        ("Direct Website", 0.0),
        ("Booking.com", 15.0),
        ("Expedia", 18.0),
        ("GDS", 10.0),
        ("Phone/Walk-in", 0.0),
    ]
    channels = {}
    for name, comm in specs:
        ch = Channel(hotel_id=hotel_id, name=name, commission_pct=comm)
        session.add(ch)
        session.flush()
        channels[name] = ch
        print(f"  {name} (commission={comm}%) id={ch.id}")
    print()
    return channels


def seed_rate_plans(session, hotel_id: int, room_types: dict, segments: dict) -> dict:
    """Returns {room_code: RatePlan}."""
    print("Creating rate plans ...")
    specs = {
        "STD": ("Standard BAR", 189.0, 139.0, 329.0),
        "DLX": ("Deluxe BAR", 249.0, 179.0, 429.0),
        "JRS": ("Junior Suite BAR", 349.0, 249.0, 599.0),
        "EXS": ("Executive Suite BAR", 499.0, 349.0, 849.0),
    }
    rate_plans = {}
    bar_seg = segments["BAR"]
    for code, (plan_name, base, mn, mx) in specs.items():
        rt = room_types[code]
        rp = RatePlan(
            hotel_id=hotel_id,
            room_type_id=rt.id,
            segment_id=bar_seg.id,
            name=plan_name,
            base_rate=base,
            min_rate=mn,
            max_rate=mx,
            is_active=True,
        )
        session.add(rp)
        session.flush()
        rate_plans[code] = rp
        print(f"  {plan_name}: base=${base}, range=[${mn}-${mx}] id={rp.id}")
    print()
    return rate_plans


def seed_cost_profile(session, hotel_id: int) -> CostProfile:
    print("Creating cost profile ...")
    cp = CostProfile(
        hotel_id=hotel_id,
        name="Standard Operations",
        cpor=45.0,
        fixed_daily_cost=12000.0,
        variable_cost_pct=5.0,
    )
    session.add(cp)
    session.flush()

    items = [
        ("Housekeeping", 18.0, True),
        ("Amenities", 8.0, True),
        ("Utilities", 7.0, True),
        ("Laundry", 6.0, True),
        ("Breakfast", 6.0, True),
    ]
    cost_items = []
    for cat, amount, is_var in items:
        ci = CostItem(
            cost_profile_id=cp.id,
            category=cat,
            amount_per_room=amount,
            is_variable=is_var,
        )
        cost_items.append(ci)
        print(f"  {cat}: ${amount}/room")
    session.add_all(cost_items)
    session.flush()
    print()
    return cp


# ---------------------------------------------------------------------------
# Reservation generation
# ---------------------------------------------------------------------------

# Distribution weights
SEGMENT_WEIGHTS = {
    "BAR": 0.35,
    "Corporate": 0.25,
    "OTA": 0.20,
    "Group": 0.10,
    "Government": 0.05,
    "Wholesale": 0.05,
}

CHANNEL_WEIGHTS = {
    "Direct Website": 0.30,
    "Booking.com": 0.25,
    "Expedia": 0.15,
    "GDS": 0.20,
    "Phone/Walk-in": 0.10,
}

# Length of stay distribution: 1n 35%, 2n 30%, 3n 20%, 4n 10%, 5n+ 5%
LOS_VALUES = [1, 2, 3, 4, 5, 6, 7]
LOS_WEIGHTS = [0.35, 0.30, 0.20, 0.07, 0.04, 0.025, 0.015]

# Room-type share (proportional to room count)
ROOM_TYPE_SHARES = {"STD": 60, "DLX": 40, "JRS": 30, "EXS": 20}
_total_rooms = sum(ROOM_TYPE_SHARES.values())

# Base rates per room type for ADR calculation
BASE_RATES = {"STD": 189.0, "DLX": 249.0, "JRS": 349.0, "EXS": 499.0}
MIN_RATES = {"STD": 139.0, "DLX": 179.0, "JRS": 249.0, "EXS": 349.0}
MAX_RATES = {"STD": 329.0, "DLX": 429.0, "JRS": 599.0, "EXS": 849.0}


def _generate_reservations_for_date(
    check_in_date: date,
    hotel_id: int,
    room_types: dict,
    segments: dict,
    channels: dict,
    is_future: bool = False,
) -> list[Reservation]:
    """Generate reservations whose check_in equals check_in_date."""
    occ_target = target_occupancy(check_in_date)

    # Add noise
    occ = occ_target + RNG.normal(0, 0.04)
    occ = float(np.clip(occ, 0.40, 0.97))

    # Total rooms to sell for this check-in date
    total_sold = int(round(occ * _total_rooms))

    # Distribute across room types (proportional to physical count)
    sold_by_type: dict[str, int] = {}
    remaining = total_sold
    codes = list(ROOM_TYPE_SHARES.keys())
    for i, code in enumerate(codes):
        if i == len(codes) - 1:
            sold_by_type[code] = remaining
        else:
            share = ROOM_TYPE_SHARES[code] / _total_rooms
            count = int(round(total_sold * share))
            # Don't exceed physical rooms
            count = min(count, ROOM_TYPE_SHARES[code])
            sold_by_type[code] = count
            remaining -= count
    # Clamp last type
    last_code = codes[-1]
    sold_by_type[last_code] = min(sold_by_type[last_code], ROOM_TYPE_SHARES[last_code])

    # Prepare segment / channel arrays for weighted random choice
    seg_names = list(SEGMENT_WEIGHTS.keys())
    seg_probs = np.array(list(SEGMENT_WEIGHTS.values()))
    seg_probs /= seg_probs.sum()

    ch_names = list(CHANNEL_WEIGHTS.keys())
    ch_probs = np.array(list(CHANNEL_WEIGHTS.values()))
    ch_probs /= ch_probs.sum()

    # Rate demand factor: higher occupancy -> higher ADR multiplier
    demand_mult = 0.85 + 0.30 * occ  # when occ=0.5 -> 1.0, occ=0.95 -> 1.135

    reservations: list[Reservation] = []

    for code, count in sold_by_type.items():
        if count <= 0:
            continue
        rt = room_types[code]
        base_rate = BASE_RATES[code]
        min_rate = MIN_RATES[code]
        max_rate = MAX_RATES[code]

        for _ in range(count):
            # Segment & channel
            seg_name = RNG.choice(seg_names, p=seg_probs)
            ch_name = RNG.choice(ch_names, p=ch_probs)
            seg = segments[seg_name]
            ch = channels[ch_name]

            # Length of stay
            los = int(RNG.choice(LOS_VALUES, p=LOS_WEIGHTS))

            # Rate calculation: base * demand_mult * segment_discount + noise
            discount = 1.0 - seg.discount_pct_from_bar / 100.0
            rate = base_rate * demand_mult * discount
            rate += RNG.normal(0, base_rate * 0.05)  # small noise
            rate = float(np.clip(rate, min_rate * discount, max_rate))
            rate = round(rate, 2)

            # Booking lead time
            if is_future:
                # Future reservations: booking date is between today-60 and today
                max_lead = max(1, (check_in_date - TODAY).days + 30)
                lead = int(RNG.integers(0, min(max_lead, 90)))
            else:
                # Historical: lead time 1-90 days, skewed toward 7-30 days
                lead = int(np.clip(RNG.lognormal(2.7, 0.7), 1, 90))
            booking_dt = datetime.combine(
                check_in_date - timedelta(days=lead), datetime.min.time()
            ) + timedelta(hours=int(RNG.integers(8, 22)), minutes=int(RNG.integers(0, 60)))

            check_out_date = check_in_date + timedelta(days=los)

            # Status
            status = ReservationStatus.CONFIRMED
            cancellation_date = None

            if not is_future:
                # Historical reservation status
                r = RNG.random()
                if r < 0.12:
                    # Cancelled (~12%)
                    status = ReservationStatus.CANCELLED
                    # Cancellation happens between booking and check-in
                    cancel_lead = int(RNG.integers(0, max(lead, 1)))
                    cancellation_date = datetime.combine(
                        check_in_date - timedelta(days=cancel_lead),
                        datetime.min.time(),
                    ) + timedelta(hours=int(RNG.integers(8, 22)))
                elif r < 0.15:
                    # No-show (~3%)
                    status = ReservationStatus.NO_SHOW
                elif check_out_date <= TODAY:
                    status = ReservationStatus.CHECKED_OUT
                elif check_in_date <= TODAY:
                    status = ReservationStatus.CHECKED_IN
                # else stays CONFIRMED (future check-in)
            # Future reservations: some cancellations too
            else:
                if RNG.random() < 0.08:
                    status = ReservationStatus.CANCELLED
                    cancel_lead = int(RNG.integers(0, max(1, (TODAY - booking_dt.date()).days)))
                    cancellation_date = datetime.combine(
                        booking_dt.date() + timedelta(days=cancel_lead),
                        datetime.min.time(),
                    ) + timedelta(hours=int(RNG.integers(8, 22)))

            res = Reservation(
                hotel_id=hotel_id,
                room_type_id=rt.id,
                segment_id=seg.id,
                channel_id=ch.id,
                confirmation_number=next_confirmation(),
                guest_name=random_guest_name(),
                check_in=check_in_date,
                check_out=check_out_date,
                nights=los,
                rate_amount=rate,
                status=status.value,
                booking_date=booking_dt,
                cancellation_date=cancellation_date,
            )
            reservations.append(res)

    return reservations


def seed_reservations(
    session,
    hotel_id: int,
    room_types: dict,
    segments: dict,
    channels: dict,
) -> int:
    """Generate 1 year historical + 90 days future reservations."""
    print("Generating reservations ...")

    # Historical: 365 days back
    hist_start = TODAY - timedelta(days=365)
    hist_dates = pd.date_range(hist_start, TODAY - timedelta(days=1), freq="D")

    total_count = 0
    batch: list[Reservation] = []
    batch_size = 2000

    for i, ts in enumerate(hist_dates):
        d = ts.date()
        batch.extend(
            _generate_reservations_for_date(
                d, hotel_id, room_types, segments, channels, is_future=False
            )
        )
        if len(batch) >= batch_size:
            session.bulk_save_objects(batch)
            total_count += len(batch)
            batch = []
        if (i + 1) % 30 == 0:
            print(f"  Historical: {i + 1}/{len(hist_dates)} days  ({total_count + len(batch)} reservations)")

    # Flush remaining historical
    if batch:
        session.bulk_save_objects(batch)
        total_count += len(batch)
        batch = []

    session.flush()
    print(f"  Historical complete: {total_count} reservations\n")

    # Future: 90 days (declining density further out)
    fut_dates = pd.date_range(TODAY, TODAY + timedelta(days=89), freq="D")
    future_count = 0

    for i, ts in enumerate(fut_dates):
        d = ts.date()
        days_out = (d - TODAY).days

        # Declining density: near dates have more bookings
        # We scale the number of reservations that actually get created
        # by generating all then randomly dropping some for farther-out dates.
        all_res = _generate_reservations_for_date(
            d, hotel_id, room_types, segments, channels, is_future=True
        )
        # Keep fraction: 1.0 for today, ~0.25 for day 90
        keep_frac = max(0.20, 1.0 - (days_out / 120.0))
        mask = RNG.random(len(all_res)) < keep_frac
        kept = [r for r, m in zip(all_res, mask) if m]
        batch.extend(kept)

        if len(batch) >= batch_size:
            session.bulk_save_objects(batch)
            future_count += len(batch)
            batch = []
        if (i + 1) % 30 == 0:
            print(f"  Future: {i + 1}/{len(fut_dates)} days  ({future_count + len(batch)} reservations)")

    if batch:
        session.bulk_save_objects(batch)
        future_count += len(batch)
        batch = []

    session.flush()
    print(f"  Future complete: {future_count} reservations")
    total_count += future_count
    print(f"  Total reservations: {total_count}\n")
    return total_count


# ---------------------------------------------------------------------------
# Room Inventory
# ---------------------------------------------------------------------------

def seed_room_inventory(
    session,
    hotel_id: int,
    room_types: dict,
) -> int:
    """Build room_inventory rows for past 365 + future 90 days.

    We compute sold counts from existing reservations in the database.
    """
    print("Building room inventory ...")

    start_date = TODAY - timedelta(days=365)
    end_date = TODAY + timedelta(days=89)
    all_dates = pd.date_range(start_date, end_date, freq="D")

    # Fetch all non-cancelled reservation data to compute sold counts
    # Using raw SQL for performance
    from sqlalchemy import text

    sold_query = text("""
        SELECT room_type_id, check_in, check_out, status
        FROM reservations
        WHERE hotel_id = :hid
          AND status NOT IN ('cancelled')
    """)
    rows = session.execute(sold_query, {"hid": hotel_id}).fetchall()

    # Build a lookup: (room_type_id, date) -> sold_count
    from collections import defaultdict
    sold_lookup: dict[tuple[int, date], int] = defaultdict(int)
    for rtid, ci, co, status in rows:
        # ci and co might be strings if SQLite
        if isinstance(ci, str):
            ci = date.fromisoformat(ci)
        if isinstance(co, str):
            co = date.fromisoformat(co)
        d = ci
        while d < co:
            sold_lookup[(rtid, d)] += 1
            d += timedelta(days=1)

    inventory_records: list[RoomInventory] = []
    count = 0

    for ts in all_dates:
        d = ts.date()
        for code, rt in room_types.items():
            sold = sold_lookup.get((rt.id, d), 0)
            # Cap sold at physical rooms
            sold = min(sold, rt.physical_rooms)

            # Out of order: ~5% of days, 1-2 rooms
            ooo = 0
            if RNG.random() < 0.05:
                ooo = int(RNG.integers(1, 3))  # 1 or 2

            inv = RoomInventory(
                hotel_id=hotel_id,
                room_type_id=rt.id,
                date=d,
                total_available=rt.physical_rooms,
                sold=sold,
                held_group=0,
                out_of_order=ooo,
                overbooking_allowance=0,
            )
            inventory_records.append(inv)
            count += 1

        # Bulk insert in chunks
        if len(inventory_records) >= 2000:
            session.bulk_save_objects(inventory_records)
            inventory_records = []

    if inventory_records:
        session.bulk_save_objects(inventory_records)
        inventory_records = []

    session.flush()
    print(f"  Created {count} inventory records ({len(all_dates)} days x {len(room_types)} room types)\n")
    return count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("  Hotel Revenue Management - Seed Data")
    print("=" * 60)
    print()

    session = SessionLocal()

    try:
        # 1. Clear existing data
        truncate_all(session)

        # 2. Hotel
        hotel = seed_hotel(session)

        # 3. Room types
        room_types = seed_room_types(session, hotel.id)

        # 4. Market segments
        segments = seed_segments(session, hotel.id)

        # 5. Channels
        channels = seed_channels(session, hotel.id)

        # 6. Rate plans
        rate_plans = seed_rate_plans(session, hotel.id, room_types, segments)

        # 7. Cost profile
        cost_profile = seed_cost_profile(session, hotel.id)

        # 8. Reservations (historical + future)
        res_count = seed_reservations(session, hotel.id, room_types, segments, channels)

        # 9. Room inventory
        inv_count = seed_room_inventory(session, hotel.id, room_types)

        # Commit everything
        session.commit()

        print("=" * 60)
        print("  Seed complete!")
        print(f"  Hotel:          {hotel.name} (id={hotel.id})")
        print(f"  Room types:     {len(room_types)}")
        print(f"  Segments:       {len(segments)}")
        print(f"  Channels:       {len(channels)}")
        print(f"  Rate plans:     {len(rate_plans)}")
        print(f"  Cost items:     5")
        print(f"  Reservations:   {res_count}")
        print(f"  Inventory rows: {inv_count}")
        print("=" * 60)

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
