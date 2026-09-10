# Caddie - a personal golf course-strategy agent

Caddie learns *your* golf game from the rounds you log and then builds a
hole-by-hole game plan for any course you play, with one goal in mind:
**break 80**.

It lives in this repository as a self-contained FastAPI app (`golf/`) next to
the hotel revenue-management app (`app/`).  They share nothing but the Python
dependencies.

```bash
pip install -r requirements.txt
python scripts/seed_golf.py          # optional: demo golfer, course and 12 rounds
uvicorn golf.main:app --reload --port 8001
# open http://localhost:8001
```

Set `ANTHROPIC_API_KEY` in `.env` to switch the caddie chat from the built-in
rule-based caddie to the Claude-powered one (model `claude-opus-5` by default).
Everything else - learning, strategy, course import - works offline.

---

## How it works, in three pictures

### 1. Your game is a shotgun pattern, not a number

Ask a golfer how far they hit a 7-iron and they say "150".  Ask their shots
and you get a cloud: some 158, some 141, a few off the toe at 120, drifting a
little right.  Caddie stores that cloud for every club:

```
                 ^ carry (yards)
      165        |          .
      158        |      . . . .
      152  ------|--- . . x . . . ---  mean carry
      145        |      . . . .
      138        |          .
      120        |  o             <- mishit tail (fat / thin / top)
                 +----------------------> lateral (yards, + = right)
                         -12   0  +12
                              ^ your typical 2-yard right drift
```

Each club has a **carry mean and sigma**, a **lateral sigma and bias**, and a
**mishit rate**.  The first rounds you log are blended with sensible defaults
for your handicap ("factory settings") and the blend shifts toward your own
numbers as evidence accumulates - like a new employee's review that starts at
the company average and moves toward their real record.

### 2. Every spot on the course has a price

Strokes-gained research (Broadie) gives the average number of strokes it takes
to hole out from any lie and distance.  Caddie keeps that table, scales it to
your handicap, and then *personalises* it from your rounds - if you are a
great bunker player, sand costs you less than the table says.

```
   from 150 yds     Tour    12-hcp    YOU (after 10 rounds)
   fairway          2.95    3.25      3.31
   rough            3.18    3.62      3.55
   sand             3.24    3.86      3.70
   water (drop)     4.2+    4.7+      4.6+
```

### 3. Strategy = the casino's edge

A casino never knows one hand, but always knows the distribution.  For every
hole Caddie fires your shotgun pattern at the hole several hundred times for
every club-and-aim-point combination, plays out the rest of the hole, and
scores the distribution:

```
   objective = E[strokes] + lambda * P(double bogey or worse)
```

`lambda` is your risk setting.  Breaking 80 is mostly about killing the blow-up
holes, so by default the plan is slightly conservative.  The output is plain
English: *"3-wood, aim 8 yards left of the fairway centre; the miss to avoid is
the pond left (2%). Approach from ~150: middle of the green, favour the left
half - short-side trouble is right."*

---

## Data-collection workflow

| Mode | What you log | What it teaches |
|------|--------------|-----------------|
| **Quick** | score, putts, fairway hit, GIR, penalties, tee miss direction | tendencies, error ranking, readiness |
| **Full** | every shot: club, lie before/after, distance to hole before/after, lateral miss, outcome tag | club distances & dispersion, personal expected-strokes table, everything above |
| **Narrative** | "driver down the left, 7-iron to 25 feet, two putts" | same as full; the caddie parses it (Claude, or a regex parser offline) |

Ten full rounds (about 300 full swings) gets the readiness meter to
**ready**; the dashboard tells you which clubs still need data.  You can log
from a phone: the round screen auto-fills each shot's start distance from the
previous shot's end distance.

## Courses anywhere in the world

* **Scorecard quick-build** - par and yardage per hole; generic geometry.
  Enough for club selection and layup numbers.
* **OpenStreetMap import** - many courses have holes, fairways, bunkers and
  water mapped (`golf=hole`, `golf=fairway`, ...).  Caddie pulls them from the
  Overpass API and projects every polygon onto the hole centerline to build the
  hazard boxes automatically.  Needs internet; the result is editable.
* **JSON / manual** - full control over every hazard box.

The hole model is a strip of graph paper laid over the hole: `x` yards from
the tee along the centerline, `y` yards left/right of it.  Hazards are boxes
in that strip; doglegs bend the strip.  Shots fly straight in the real world,
so a corner-cutting drive is judged against the trees on the inside of the
bend exactly as it would be on the course.

## Code map

```
golf/
  config.py, database.py        settings, SQLite session (golf_caddie.db)
  models/                        players & clubs, courses/holes/features, rounds/shots, profiles & plans
  schemas.py                     Pydantic request/response models
  services.py                    profile computation, plan generation, round logging
  engine/
    baselines.py                 strokes-gained tables + handicap scaling + default club priors
    dispersion.py                the shotgun-pattern sampler (normal swing + mishit tail)
    hole_model.py                hole geometry, world<->local coords, lie classification, SVG spec
    learning.py                  ProfileBuilder: clubs, personal expected strokes, tendencies, errors, readiness
    strategy.py                  StrategyEngine: Monte Carlo optimiser + plain-English plans
    course_import.py             scorecard / JSON / OpenStreetMap importers
  agent/caddie.py                Claude-powered caddie (tool use + structured narrative parsing) and offline fallback
  api/                           REST routes (players, courses, rounds, profile, strategy, caddie)
  templates/, static/            dashboard, round logging, courses, strategy (SVG hole maps), caddie chat, bag
scripts/seed_golf.py             demo data generated from a hidden "true" game so you can check the learner
tests/test_golf/                 engine, API, importer and caddie tests (no network)
```

## REST API (abridged)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/players` | create a player (+ default bag) |
| GET/PUT | `/api/players/{id}` | profile settings, risk tolerance, target score |
| GET/POST/PUT/DELETE | `/api/players/{id}/clubs[/{club_id}]` | manage the bag |
| GET/POST | `/api/courses` | list / create (JSON) |
| POST | `/api/courses/import/scorecard` | quick-build from par + yardage |
| POST | `/api/courses/import/osm` | import from OpenStreetMap by name or lat/lon |
| PUT | `/api/courses/{id}/holes/{n}` | edit hole geometry and hazards |
| GET | `/api/courses/{id}/holes/{n}/geometry` | SVG render spec |
| GET/POST | `/api/players/{id}/rounds` | list / start a round |
| PUT | `/api/players/{id}/rounds/{rid}/holes/{n}` | log a hole (quick or shot-by-shot) |
| POST | `/api/players/{id}/rounds/{rid}/narrative` | log holes in plain English |
| GET | `/api/players/{id}/profile` | learned profile (recomputed when new shots exist) |
| GET | `/api/players/{id}/dashboard` | everything the dashboard shows |
| POST/GET | `/api/players/{id}/strategy/{course_id}` | generate / fetch the hole-by-hole plan |
| POST | `/api/players/{id}/caddie/chat` | talk to the caddie |

## Testing

```bash
python -m pytest tests/test_golf -q
```

The tests never touch the network: OpenStreetMap and Claude are mocked.

## Roadmap (from the design review)

The design panel that reviewed this build agreed with the architecture and
left a short list of upgrades that would sharpen the numbers further:

* **Per-cell score distributions** - learn a full strokes-to-hole-out
  histogram for each lie/distance cell (today the engine models the spread
  around the personal expectation parametrically).
* **Memoised two-shot lookahead** - value par-5 tee shots and layups on a
  10-yard grid of next-shot values solved once per hole.
* **Strike tags** - a second tag column (fat/thin/top/shank/hook/slice/...)
  next to the outcome tag, so the error ranking can separate contact faults
  from direction faults.
* **Pin positions and yellow penalty areas** - v1 aims at the centre of the
  green and treats all water as red (lateral relief).
* **Strokes lost versus an 80-shooter** - measure every habit against the
  player who shoots 79, not the tour, so the dashboard numbers sum to the gap.
