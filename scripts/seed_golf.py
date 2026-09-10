"""Seed the Caddie golf app with a demo player, a realistic course and a dozen
rounds of shot-level data so every screen has something to show.

    python scripts/seed_golf.py            # add demo data if missing
    python scripts/seed_golf.py --reset    # wipe golf tables first

The rounds are *simulated* from a hidden "true" version of the demo golfer's
game (club distances, dispersion, a right miss, occasional mishits).  That
lets you check the learning engine: after seeding, the profile it learns
should land close to those hidden numbers.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from golf import services  # noqa: E402
from golf.database import Base, SessionLocal, engine, init_db  # noqa: E402
from golf.engine.hole_model import HoleGeometry  # noqa: E402
from golf.models import Club, Course, Hole, HoleFeature, HoleResult, Player, Round, Shot  # noqa: E402

DEMO_NAME = "Demo Golfer"

# The golfer's real game (what the engine should rediscover).
TRUE_CLUBS = {
    #  code: (carry, carry_sigma, lateral_sigma, lateral_bias, p_mishit)
    "D": (238, 13, 27, 7, 0.10),
    "3w": (215, 11, 21, 5, 0.09),
    "3h": (196, 10, 18, 3, 0.09),
    "4i": (183, 9, 16, 2, 0.08),
    "5i": (172, 9, 16, 2, 0.09),
    "6i": (162, 8, 15, 1, 0.08),
    "7i": (152, 8, 14, 1, 0.08),
    "8i": (141, 7, 12, 0, 0.06),
    "9i": (130, 7, 11, 0, 0.06),
    "PW": (118, 6, 10, 0, 0.05),
    "GW": (104, 6, 9, 0, 0.05),
    "SW": (88, 6, 8, 0, 0.06),
    "LW": (70, 6, 8, 0, 0.07),
}

# A fictional but realistic parkland course from the white tees (par 72, 6,380 yds).
RIVERBEND = [
    # number, par, yards, shape, dogleg_at, angle, fw_width, features[(kind, side, start, end, offset, width, label)]
    (1, 4, 385, "straight", None, None, 36, [("bunker", "right", 220, 245, 16, 12, "fairway bunker right"), ("bunker", "left", 360, 385, 12, 10, "greenside bunker left")]),
    (2, 5, 520, "dogleg_left", 250, 25, 38, [("trees", "left", 120, 260, 22, 999, "trees inside the corner"), ("water", "right", 380, 470, 20, 999, "pond right")]),
    (3, 3, 168, "straight", None, None, 30, [("water", "short", 100, 155, 0, 60, "pond short"), ("bunker", "right", 155, 180, 14, 10, "bunker right")]),
    (4, 4, 412, "straight", None, None, 34, [("ob", "left", 0, 412, 30, 999, "OB left (road)"), ("bunker", "right", 235, 260, 17, 12, "fairway bunker right")]),
    (5, 4, 355, "dogleg_right", 210, 45, 32, [("trees", "right", 130, 240, 18, 999, "trees inside corner"), ("bunker", "left", 330, 355, 14, 10, "greenside bunker left")]),
    (6, 4, 440, "straight", None, None, 38, [("deep_rough", "both", 150, 440, 28, 999, "fescue both sides")]),
    (7, 3, 148, "straight", None, None, 28, [("bunker", "left", 135, 160, 12, 10, "bunker left"), ("bunker", "right", 135, 160, 12, 10, "bunker right")]),
    (8, 5, 545, "straight", None, None, 36, [("creek", "center", 285, 297, 0, 999, "creek crossing"), ("water", "left", 450, 545, 18, 999, "lake left of green")]),
    (9, 4, 398, "dogleg_right", 240, 30, 34, [("bunker", "right", 225, 250, 15, 12, "corner bunker"), ("trees", "left", 200, 330, 26, 999, "trees left")]),
    (10, 4, 372, "straight", None, None, 33, [("water", "left", 200, 290, 20, 999, "pond left"), ("bunker", "right", 350, 372, 13, 10, "greenside bunker right")]),
    (11, 3, 192, "straight", None, None, 30, [("bunker", "short", 170, 185, 0, 20, "front bunker"), ("deep_rough", "long", 200, 215, 0, 40, "thick rough long")]),
    (12, 5, 498, "straight", None, None, 40, [("ob", "right", 0, 498, 34, 999, "OB right (boundary fence)"), ("bunker", "left", 240, 262, 18, 12, "fairway bunker left")]),
    (13, 4, 335, "dogleg_left", 200, 40, 30, [("trees", "left", 110, 220, 16, 999, "trees inside corner"), ("water", "right", 250, 335, 22, 999, "lake right")]),
    (14, 4, 425, "straight", None, None, 36, [("bunker", "left", 225, 250, 17, 12, "fairway bunker left"), ("deep_rough", "right", 150, 425, 26, 999, "native area right")]),
    (15, 3, 210, "straight", None, None, 32, [("water", "left", 150, 215, 15, 999, "water left"), ("bunker", "right", 195, 220, 14, 10, "bunker right")]),
    (16, 4, 388, "straight", None, None, 34, [("trees", "both", 100, 388, 28, 999, "tree-lined"), ("bunker", "right", 365, 388, 12, 10, "greenside bunker right")]),
    (17, 5, 510, "dogleg_right", 260, 20, 38, [("water", "right", 150, 300, 24, 999, "creek right"), ("bunker", "left", 470, 495, 16, 12, "layup bunker left")]),
    (18, 4, 401, "straight", None, None, 35, [("water", "left", 220, 320, 21, 999, "lake left"), ("ob", "right", 0, 401, 38, 999, "OB right (driving range)")]),
]

HANDICAP_INDEX = {1: 7, 2: 3, 3: 15, 4: 1, 5: 13, 6: 5, 7: 17, 8: 9, 9: 11, 10: 8, 11: 14, 12: 4, 13: 16, 14: 2, 15: 12, 16: 10, 17: 6, 18: 18}


def build_course(db) -> Course:
    course = Course(name="Riverbend Golf Club", city="Austin", country="US", source="manual", tee_name="White",
                    rating=70.8, slope=128, latitude=30.27, longitude=-97.74,
                    notes="Demo course: parkland layout with water on 7 holes and OB on 3.")
    db.add(course)
    db.flush()
    for number, par, yards, shape, dl_at, dl_ang, fw, feats in RIVERBEND:
        hole = Hole(course_id=course.id, number=number, par=par, yards=yards, shape=shape, dogleg_at_yards=dl_at,
                    dogleg_angle_deg=dl_ang, fairway_width_yards=fw, fairway_start_yards=(yards if par == 3 else 100),
                    handicap_index=HANDICAP_INDEX[number], green_width_yards=30 if par > 3 else 27,
                    green_depth_yards=30 if par > 3 else 27)
        db.add(hole)
        db.flush()
        for kind, side, start, end, offset, width, label in feats:
            db.add(HoleFeature(hole_id=hole.id, kind=kind, side=side, start_yards=start, end_yards=end,
                               offset_yards=offset, width_yards=width, label=label))
    db.commit()
    course = services.get_course(db, course.id)
    services.refresh_course_totals(db, course)
    return course


def build_player(db) -> Player:
    player = Player(name=DEMO_NAME, handicap_index=14.2, target_score=79, risk_tolerance=0.35, dominant_miss="right")
    db.add(player)
    db.commit()
    db.refresh(player)
    services.create_default_bag(db, player)
    for club in db.query(Club).filter(Club.player_id == player.id).all():
        if club.code in TRUE_CLUBS:
            club.stock_carry = TRUE_CLUBS[club.code][0] + 6  # golfers overestimate a little
    db.commit()
    return services.get_player(db, player.id)


# ---------------------------------------------------------------------------
# Round simulation using the hidden "true" game
# ---------------------------------------------------------------------------
class TrueGame:
    def __init__(self, rng: np.random.Generator):
        self.rng = rng
        self.order = sorted(TRUE_CLUBS, key=lambda c: -TRUE_CLUBS[c][0])

    def club_for(self, dist: float, lie: str) -> str:
        factor = {"rough": 0.93, "sand": 0.85}.get(lie, 1.0)
        return min(self.order, key=lambda c: abs(TRUE_CLUBS[c][0] * factor - dist))

    def swing(self, code: str, target: float | None = None, lie: str = "fairway"):
        carry, csig, lsig, lbias, pm = TRUE_CLUBS[code]
        factor = {"rough": 0.93, "sand": 0.85}.get(lie, 1.0)
        mean = carry * factor
        frac = 1.0
        if target is not None and target < mean:
            frac = max(target / mean, 0.35)
            mean = target
        tag = None
        if self.rng.random() < pm:
            c = mean * self.rng.uniform(0.55, 0.85)
            l = self.rng.normal(lbias, lsig * 1.6 * frac)
            tag = self.rng.choice(["fat", "thin", "top"])
        else:
            c = self.rng.normal(mean, max(csig * frac, 3))
            l = self.rng.normal(lbias * frac, max(lsig * frac, 3))
        if tag is None:
            if l > 18:
                tag = "right"
            elif l < -18:
                tag = "left"
            elif c < mean - 1.5 * csig:
                tag = "short"
            elif c > mean + 1.5 * csig:
                tag = "long"
            else:
                tag = "good"
        return max(c, 5.0), l, tag


def putt_sequence(rng: np.random.Generator, feet: float) -> list[tuple[float, float, bool]]:
    """Return [(start_ft, end_ft, holed), ...] for a 14-handicap putter."""
    seq = []
    d = feet
    for _ in range(5):
        if d <= 2.5:
            p_make = 0.98
        elif d <= 5:
            p_make = 0.75
        elif d <= 10:
            p_make = 0.38
        elif d <= 20:
            p_make = 0.14
        else:
            p_make = 0.05
        if rng.random() < p_make:
            seq.append((d, 0.0, True))
            return seq
        # Lag: leave roughly 7-10% of the distance, occasionally much more (a three-putt).
        leave = abs(rng.normal(0.08 * d + 0.8, 0.05 * d + 0.8))
        leave = max(leave, 0.6)
        seq.append((d, leave, False))
        d = leave
    seq.append((d, 0.0, True))
    return seq


def simulate_hole(game: TrueGame, geom: HoleGeometry, rng: np.random.Generator) -> dict:
    shots = []
    strokes = 0
    penalties = 0
    pos = (0.0, 0.0)
    lie = "tee"
    dist = geom.yards
    putts = 0
    gir = False
    fairway_hit = None
    tee_miss = None
    seq = 0
    for _ in range(12):
        if lie in ("green", "fringe") or dist <= 30 and lie not in ("sand", "recovery"):
            break
        seq += 1
        if lie == "tee":
            if geom.par == 3:
                code = game.club_for(dist, "fairway")
            else:
                code = "D" if geom.yards >= 360 or rng.random() < 0.7 else "3w"
            target = None
        elif lie == "recovery":
            # Punch out.
            strokes += 1
            lx, ly = geom.world_to_local(np.array([pos[0]]), np.array([pos[1]]))
            nx = min(lx[0] + rng.uniform(40, 80), geom.yards - 30)
            ny = ly[0] * rng.uniform(0, 0.3)
            npos = geom.local_to_world(nx, ny)
            landing = geom.classify_point(nx, ny)
            shots.append(dict(sequence=seq, club_code="7i", shot_type="punch", lie_start="recovery", start_distance_yards=round(dist, 1),
                              lie_end=landing.lie, end_distance_yards=round(landing.distance_to_hole, 1), lateral_miss_yards=None,
                              outcome_tag="good", penalty_strokes=0, holed=False))
            pos, lie, dist = npos, landing.lie, landing.distance_to_hole
            continue
        elif lie == "sand" and dist <= 40:
            strokes += 1
            feet = abs(rng.normal(14, 9)) + 3
            shots.append(dict(sequence=seq, club_code="SW", shot_type="bunker", lie_start="sand", start_distance_yards=round(dist, 1),
                              lie_end="green", end_distance_yards=round(feet / 3, 2), lateral_miss_yards=None, outcome_tag="good",
                              penalty_strokes=0, holed=False))
            lie, dist = "green", feet / 3
            break
        else:
            code = game.club_for(dist, lie)
            target = dist if dist < TRUE_CLUBS[code][0] else None
        carry, lateral, tag = game.swing(code, target, lie if lie != "tee" else "fairway")
        direction = geom.aim_direction(pos, (min(geom.yards, (geom.world_to_local(np.array([pos[0]]), np.array([pos[1]]))[0][0]) + carry), 0.0))
        rx, ry = -direction[1], direction[0]
        wx = pos[0] + carry * direction[0] + lateral * rx
        wy = pos[1] + carry * direction[1] + lateral * ry
        r = geom.classify_world(np.array([wx]), np.array([wy]))
        new_lie = str(r["lie"][0])
        pen = int(r["penalty"][0])
        strokes += 1 + pen
        penalties += pen
        end_dist = float(r["dist"][0])
        if new_lie == "ob":
            # Stroke and distance: replay from the same spot.
            shots.append(dict(sequence=seq, club_code=code, shot_type="tee" if lie == "tee" else "full", lie_start=lie,
                              start_distance_yards=round(dist, 1), lie_end="ob", end_distance_yards=round(dist, 1),
                              lateral_miss_yards=round(lateral, 1), outcome_tag="ob", penalty_strokes=1, holed=False))
            if lie == "tee" and geom.par > 3:
                tee_miss = "right" if lateral > 0 else "left"
                fairway_hit = False
            continue
        if new_lie == "penalty":
            lx, ly = float(r["x"][0]), float(r["y"][0])
            drop_y = np.sign(ly) * max(abs(ly) - 6, 0)
            drop = geom.classify_point(min(lx, geom.yards - 20), drop_y)
            shots.append(dict(sequence=seq, club_code=code, shot_type="tee" if lie == "tee" else "full", lie_start=lie,
                              start_distance_yards=round(dist, 1), lie_end="penalty", end_distance_yards=round(drop.distance_to_hole, 1),
                              lateral_miss_yards=round(lateral, 1), outcome_tag="penalty", penalty_strokes=1, holed=False))
            if lie == "tee" and geom.par > 3:
                tee_miss = "right" if lateral > 0 else "left"
                fairway_hit = False
            pos = geom.local_to_world(min(lx, geom.yards - 20), drop_y)
            lie, dist = "rough", drop.distance_to_hole
            continue
        shots.append(dict(sequence=seq, club_code=code, shot_type="tee" if lie == "tee" else "full", lie_start=lie,
                          start_distance_yards=round(dist, 1), lie_end=new_lie, end_distance_yards=round(end_dist, 1),
                          lateral_miss_yards=round(lateral, 1), intended_carry_yards=(round(target, 1) if target else None),
                          distance_miss_yards=round(carry - (target or TRUE_CLUBS[code][0]), 1) if tag in ("good", "short", "long", "left", "right") else None,
                          outcome_tag=tag, penalty_strokes=0, holed=False))
        if lie == "tee" and geom.par > 3:
            fairway_hit = new_lie == "fairway"
            tee_miss = None if fairway_hit else ("right" if lateral > 10 else ("left" if lateral < -10 else "short"))
        pos, lie, dist = (wx, wy), new_lie, end_dist
    # Short game if needed.
    if lie not in ("green", "fringe"):
        seq += 1
        strokes += 1
        feet = abs(rng.normal(11 if lie == "fairway" else 16, 8)) + 2
        shots.append(dict(sequence=seq, club_code="SW" if dist > 15 else "PW", shot_type="pitch" if dist > 15 else "chip",
                          lie_start=lie, start_distance_yards=round(dist, 1), lie_end="green", end_distance_yards=round(feet / 3, 2),
                          lateral_miss_yards=None, outcome_tag="good", penalty_strokes=0, holed=False))
        lie, dist = "green", feet / 3
    if strokes <= geom.par - 2 and lie == "green":
        gir = True
    feet = dist * 3.0
    first_lie = lie  # a fringe finish putts from the fringe; the learner applies its own fringe factor
    for start_ft, end_ft, holed in putt_sequence(rng, feet * (1.1 if lie == "fringe" else 1.0)):
        seq += 1
        strokes += 1
        putts += 1
        lie_start_putt = first_lie if putts == 1 else "green"
        start_yds = dist if putts == 1 else start_ft / 3
        shots.append(dict(sequence=seq, club_code="P", shot_type="putt", lie_start=lie_start_putt, start_distance_yards=round(start_yds, 2),
                          lie_end="green", end_distance_yards=round(end_ft / 3, 2), lateral_miss_yards=None,
                          outcome_tag=("three_putt" if putts >= 3 else "good"), penalty_strokes=0, holed=holed))
    return dict(score=strokes, putts=putts, fairway_hit=fairway_hit, gir=gir, penalties=penalties, tee_miss=tee_miss, shots=shots)


def seed_rounds(db, player: Player, course: Course, n_rounds: int = 12, seed: int = 11) -> list[Round]:
    rng = np.random.default_rng(seed)
    game = TrueGame(rng)
    geoms = services.course_geometry(course)
    club_by_code = {c.code: c for c in player.clubs}
    rounds = []
    start = date.today() - timedelta(days=7 * n_rounds)
    for i in range(n_rounds):
        rnd = Round(player_id=player.id, course_id=course.id, played_on=start + timedelta(days=7 * i), tee_name="White",
                    logging_mode="full", completed=True, weather=str(rng.choice(["Sunny", "Breezy", "Overcast", "Hot"])))
        db.add(rnd)
        db.flush()
        total = 0
        for geom, hole in zip(geoms, sorted(course.holes, key=lambda h: h.number)):
            res = simulate_hole(game, geom, rng)
            hr = HoleResult(round_id=rnd.id, hole_id=hole.id, hole_number=hole.number, par=hole.par, yards=hole.yards,
                            score=res["score"], putts=res["putts"], fairway_hit=res["fairway_hit"], gir=res["gir"],
                            penalties=res["penalties"], tee_miss=res["tee_miss"],
                            tee_club_id=(club_by_code.get(res["shots"][0]["club_code"]).id if res["shots"] and res["shots"][0]["club_code"] in club_by_code else None))
            db.add(hr)
            db.flush()
            for s in res["shots"]:
                club = club_by_code.get(s["club_code"])
                db.add(Shot(hole_result_id=hr.id, club_id=club.id if club else None, **s))
            total += res["score"]
        rnd.total_score = total
        rounds.append(rnd)
    db.commit()
    return rounds


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="drop and recreate the golf tables first")
    parser.add_argument("--rounds", type=int, default=12)
    args = parser.parse_args()
    if args.reset:
        import golf.models  # noqa: F401

        Base.metadata.drop_all(bind=engine)
    init_db()
    db = SessionLocal()
    try:
        player = db.query(Player).filter(Player.name == DEMO_NAME).first()
        if player and not args.reset:
            print(f"Demo player already exists (id={player.id}); use --reset to rebuild.")
            return
        course = build_course(db)
        player = build_player(db)
        rounds = seed_rounds(db, player, course, n_rounds=args.rounds)
        snap = services.compute_profile(db, player.id)
        scores = [r.total_score for r in rounds]
        print(f"Seeded player '{player.name}' (id={player.id}) with {len(player.clubs)} clubs")
        print(f"Seeded course '{course.name}' (id={course.id}) par {course.par}, {course.yardage} yards")
        print(f"Seeded {len(rounds)} rounds: scores {scores} (avg {np.mean(scores):.1f})")
        print(f"Profile readiness: {snap.readiness_level} ({snap.readiness_score:.2f}) from {snap.shots_count} shots")
        learned = snap.data["clubs"]
        print("Learned vs true carries:")
        for code, (carry, *_rest) in TRUE_CLUBS.items():
            if code in learned:
                d = learned[code]
                print(f"  {code:>3}: learned {d['carry_mean']:6.1f} +/- {d['carry_sigma']:4.1f}  lateral sigma {d['lateral_sigma']:4.1f} bias {d['lateral_bias']:+5.1f}  (true {carry}, n={d['n_samples']})")
        print("Top errors:")
        for e in snap.data["errors"][:4]:
            print(f"  - {e['label']}: {e['strokes_per_round']} strokes/round")
        plan = services.generate_plan(db, player.id, course.id)
        print(f"Strategy for {course.name}: expected {plan.expected_score}, P(break {player.target_score}) = {plan.p_break_target}")
        for h in plan.data["holes"][:3]:
            print(f"  Hole {h['hole']} (par {h['par']}, {h['yards']}): {h['tee']['aim']} -> E={h['expected_strokes']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
