"""Tests for the caddie agent (heuristic + Claude with a fake client). No network."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import httpx2
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import golf.models  # noqa: F401  -- populate Base.metadata
from golf import services
from golf.agent.caddie import (
    ClaudeCaddie, HeuristicCaddie, ParsedHole, ParsedNarrative, ParsedShot, get_caddie,
)
from golf.config import settings
from golf.database import Base
from golf.models import ChatMessage, Course, Hole, HoleResult, Player, Round

COURSE_NAME = "Pine Valley Muni"
HOLES = [(1, 4, 380), (2, 3, 165), (3, 4, 400)]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def player(db):
    p = Player(name="Test Golfer", handicap_index=14.0, target_score=79)
    db.add(p)
    db.commit()
    db.refresh(p)
    services.create_default_bag(db, p)
    return p


def _build_course(db) -> Course:
    """Build the test course through the scorecard importer (a failure there must fail these tests too)."""
    from golf.engine import course_import
    from golf.schemas import ScorecardHole, ScorecardImport

    data = ScorecardImport(name=COURSE_NAME, holes=[ScorecardHole(number=n, par=p, yards=y) for n, p, y in HOLES])
    course = course_import.build_course_from_scorecard(db, data)
    return services.get_course(db, course.id)


@pytest.fixture
def course(db, player):
    return _build_course(db)


@pytest.fixture
def open_round(db, player, course):
    rnd = Round(player_id=player.id, course_id=course.id, played_on=date.today(), completed=False, logging_mode="narrative")
    db.add(rnd)
    db.commit()
    db.refresh(rnd)
    return services.get_round(db, rnd.id)


# ---------------------------------------------------------------------------
# Fake Anthropic client
# ---------------------------------------------------------------------------
def _text_block(text):
    return SimpleNamespace(type="text", text=text)


def _tool_block(name, inp, id_):
    return SimpleNamespace(type="tool_use", name=name, input=inp, id=id_)


class _FakeBetaMessages:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        # Snapshot the message list: the caddie appends to the same list on later turns.
        kwargs["messages"] = list(kwargs.get("messages") or [])
        self.calls.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class _FakeMessages:
    def __init__(self, parsed):
        self.parsed = parsed
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.parsed, BaseException):
            raise self.parsed
        return SimpleNamespace(parsed_output=self.parsed)


class FakeClient:
    def __init__(self, responses=(), parsed=None):
        self.beta = SimpleNamespace(messages=_FakeBetaMessages(responses))
        self.messages = _FakeMessages(parsed)


# ---------------------------------------------------------------------------
# 1. Factory
# ---------------------------------------------------------------------------
def test_get_caddie_defaults_to_heuristic(db, player, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    caddie = get_caddie(db, player.id)
    assert isinstance(caddie, HeuristicCaddie)
    assert caddie.provider == "heuristic"


def test_get_caddie_uses_claude_when_client_given(db, player, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    caddie = get_caddie(db, player.id, client=FakeClient())
    assert isinstance(caddie, ClaudeCaddie)
    assert caddie.provider == "claude"


# ---------------------------------------------------------------------------
# 2-3. Heuristic narrative parser
# ---------------------------------------------------------------------------
def test_heuristic_parser_basic_hole(db, player, open_round):
    caddie = HeuristicCaddie(db, player.id)
    parsed = caddie.parse_narrative("Hole 3: driver in the fairway, 7 iron to 25 feet, two putts", round_=open_round)
    assert parsed.parser == "heuristic"
    assert len(parsed.holes) == 1
    hole = parsed.holes[0]
    assert hole.hole_number == 3
    assert hole.par == 4  # from the course
    assert len(hole.shots) == 4
    assert hole.score == 4
    assert hole.putts == 2
    assert hole.fairway_hit is True
    assert hole.gir is True
    assert hole.penalties == 0
    s1, s2, s3, s4 = hole.shots
    assert s1.club_code == "D" and s1.shot_type == "tee" and s1.lie_start == "tee" and s1.lie_end == "fairway"
    assert s1.start_distance_yards == 400
    assert s2.club_code == "7i" and s2.lie_end == "green"
    assert s2.start_distance_yards == s1.end_distance_yards
    assert s2.end_distance_yards == pytest.approx(25 / 3, abs=0.01)
    assert s3.shot_type == "putt" and s3.start_distance_yards == pytest.approx(8.33, abs=0.01) and not s3.holed
    assert s4.shot_type == "putt" and s4.holed and s4.end_distance_yards == 0
    assert [s.sequence for s in hole.shots] == [1, 2, 3, 4]


def test_heuristic_parser_water_penalty(db, player, open_round):
    caddie = HeuristicCaddie(db, player.id)
    parsed = caddie.parse_narrative(
        "hole 7 driver into the water, dropped and hit 8 iron to the green 40 feet, three putts", round_=open_round
    )
    assert len(parsed.holes) == 1
    hole = parsed.holes[0]
    assert hole.hole_number == 7
    assert hole.par == 4  # not on the course -> default par 4 / 400 yards
    assert hole.shots[0].penalty_strokes == 1
    assert hole.shots[0].lie_end == "penalty"
    assert hole.shots[0].start_distance_yards == 400
    assert hole.penalties == 1
    assert hole.score == 6
    assert hole.putts == 3
    assert hole.gir is False
    assert hole.shots[1].club_code == "8i" and hole.shots[1].lie_end == "green"
    assert hole.shots[1].end_distance_yards == pytest.approx(40 / 3, abs=0.01)
    assert sum(1 for s in hole.shots if s.shot_type == "putt") == 3
    assert hole.shots[-1].holed
    assert any("assumed" in w or "estimated" in w for w in parsed.warnings)


def test_heuristic_parser_multiple_holes_and_ob(db, player, open_round):
    caddie = HeuristicCaddie(db, player.id)
    text = "#1 3 wood down the middle, PW to 12 feet, made it. Hole 2: 6 iron long and left into the bunker, splashed out to 8 feet, two putts."
    parsed = caddie.parse_narrative(text, round_=open_round)
    assert [h.hole_number for h in parsed.holes] == [1, 2]
    h1, h2 = parsed.holes
    assert h1.score == 3 and h1.putts == 1 and h1.fairway_hit is True and h1.gir is True
    assert h1.shots[0].club_code == "3w"
    assert h2.par == 3 and h2.fairway_hit is None
    assert h2.shots[0].lie_end == "sand" and h2.shots[0].outcome_tag == "long"
    assert h2.shots[1].shot_type == "bunker" and h2.shots[1].lie_start == "sand"
    assert h2.score == 4 and h2.putts == 2 and h2.gir is False


# ---------------------------------------------------------------------------
# 4. Heuristic chat
# ---------------------------------------------------------------------------
def test_heuristic_chat_club_distances(db, player, course):
    caddie = HeuristicCaddie(db, player.id)
    result = caddie.chat("what are my club distances")
    assert result["provider"] == "heuristic"
    assert "Driver" in result["reply"] or "(D)" in result["reply"]
    assert "7 Iron" in result["reply"]
    roles = [m.role for m in db.query(ChatMessage).order_by(ChatMessage.id).all()]
    assert roles == ["user", "assistant"]
    assert [m["role"] for m in result["history"]] == ["user", "assistant"]


def test_heuristic_chat_course_strategy(db, player, course):
    caddie = HeuristicCaddie(db, player.id)
    result = caddie.chat(f"how should I play {COURSE_NAME}?")
    assert "Hole 1" in result["reply"]
    assert COURSE_NAME in result["reply"]
    assert any(a["type"] == "strategy_generated" for a in result["actions"])
    assert services.latest_plan(db, player.id, course.id) is not None
    # A second ask reuses the saved plan and a hole number gives the detailed hole plan.
    result2 = caddie.chat(f"plan for hole 2 at {COURSE_NAME}")
    assert any(a["type"] == "strategy_loaded" for a in result2["actions"])
    assert "Hole 2" in result2["reply"] and "Tee shot" in result2["reply"]


def test_heuristic_chat_logs_narrative_to_open_round(db, player, open_round):
    caddie = HeuristicCaddie(db, player.id)
    result = caddie.chat("Hole 3: driver in the fairway, 7 iron to 25 feet, two putts")
    assert any(a["type"] == "hole_logged" for a in result["actions"])
    assert "Logged" in result["reply"]
    hr = db.query(HoleResult).filter(HoleResult.round_id == open_round.id, HoleResult.hole_number == 3).one()
    assert hr.score == 4 and hr.putts == 2 and len(hr.shots) == 4
    assert hr.shots[0].club_id is not None  # linked to the bag
    assert services.get_round(db, open_round.id).total_score == 4
    # Without a hole number the caddie previews and asks.
    preview = caddie.chat("driver in the rough, 9 iron to 30 feet, two putts")
    assert any(a["type"] == "narrative_preview" for a in preview["actions"])
    assert "not saved" in preview["reply"]


def test_heuristic_chat_help_and_other_intents(db, player, course):
    caddie = HeuristicCaddie(db, player.id)
    assert "caddie" in caddie.chat("hello there")["reply"].lower()
    assert "Readiness" in caddie.chat("do you have enough data yet?")["reply"]
    assert "rounds" in caddie.chat("show my recent rounds")["reply"].lower()
    assert "strokes" in caddie.chat("what is costing me strokes?")["reply"].lower()


# ---------------------------------------------------------------------------
# 5. Claude caddie with a fake client
# ---------------------------------------------------------------------------
def test_claude_chat_tool_loop_with_fake_client(db, player, course):
    responses = [
        SimpleNamespace(stop_reason="tool_use", content=[_tool_block("tool_get_profile", {}, "tu_1")]),
        SimpleNamespace(stop_reason="end_turn", content=[_text_block("Your driver carries about 236 yards - aim the pattern, not the ball.")]),
    ]
    client = FakeClient(responses=responses)
    caddie = ClaudeCaddie(db, player.id, client=client)
    assert caddie.system_prompt.startswith("You are the player's personal golf caddie")
    assert COURSE_NAME in caddie.system_prompt

    result = caddie.chat("how far does my driver go?")
    assert result["provider"] == "claude"
    assert result["reply"] == "Your driver carries about 236 yards - aim the pattern, not the ball."
    assert "tool_get_profile" in [a.get("name") for a in result["actions"]]
    assert all(a.get("ok") for a in result["actions"] if a["type"] == "tool_call")

    calls = client.beta.messages.calls
    assert len(calls) == 2
    first = calls[0]
    assert first["model"] == settings.anthropic_model
    assert first["fallbacks"] == "default"
    assert first["betas"] == ["server-side-fallback-2026-07-01"]
    assert "thinking" not in first and "temperature" not in first and "tool_choice" not in first
    assert [t["name"] for t in first["tools"]] == [
        "tool_get_profile", "tool_list_courses", "tool_get_strategy", "tool_hole_plan", "tool_log_hole", "tool_recent_rounds",
    ]
    assert first["messages"][-1] == {"role": "user", "content": "how far does my driver go?"}
    second = calls[1]["messages"]
    assert second[-2]["role"] == "assistant"
    assert second[-1]["role"] == "user"
    tool_results = second[-1]["content"]
    assert tool_results[0]["type"] == "tool_result" and tool_results[0]["tool_use_id"] == "tu_1"
    assert "handicap" in tool_results[0]["content"]

    rows = db.query(ChatMessage).filter(ChatMessage.player_id == player.id).order_by(ChatMessage.id).all()
    assert [(r.role, r.content) for r in rows] == [
        ("user", "how far does my driver go?"),
        ("assistant", "Your driver carries about 236 yards - aim the pattern, not the ball."),
    ]
    assert len(result["history"]) == 2


def test_claude_chat_tool_error_is_reported_to_model(db, player, course):
    responses = [
        SimpleNamespace(stop_reason="tool_use", content=[_tool_block("tool_hole_plan", {"course_id": 999, "hole_number": 1}, "tu_9")]),
        SimpleNamespace(stop_reason="end_turn", content=[_text_block("That course does not exist.")]),
    ]
    client = FakeClient(responses=responses)
    caddie = ClaudeCaddie(db, player.id, client=client)
    result = caddie.chat("plan hole 1 on course 999")
    assert result["reply"] == "That course does not exist."
    tool_results = client.beta.messages.calls[1]["messages"][-1]["content"]
    assert tool_results[0]["is_error"] is True
    assert any(a["name"] == "tool_hole_plan" and a["ok"] is False for a in result["actions"])


def test_claude_chat_refusal_and_api_fallback(db, player, course):
    caddie = ClaudeCaddie(db, player.id, client=FakeClient(responses=[SimpleNamespace(stop_reason="refusal", content=[])]))
    result = caddie.chat("something odd")
    assert "can't help" in result["reply"]

    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    import anthropic

    err = anthropic.RateLimitError("slow down", response=httpx2.Response(429, request=req), body=None)
    caddie = ClaudeCaddie(db, player.id, client=FakeClient(responses=[err]))
    result = caddie.chat("what are my club distances")
    assert result["provider"] == "claude"
    assert result["reply"].startswith("(Claude unavailable: rate limited")
    assert "Driver" in result["reply"]
    assert any(a["type"] == "fallback" for a in result["actions"])


def test_claude_parse_narrative_with_fake_client(db, player, open_round):
    parsed = ParsedNarrative(
        holes=[
            ParsedHole(
                hole_number=3, par=4, score=4, putts=2, fairway_hit=True, gir=True, penalties=0,
                shots=[
                    ParsedShot(sequence=1, club_code="D", shot_type="tee", lie_start="tee", start_distance_yards=400, lie_end="fairway", end_distance_yards=160),
                    ParsedShot(sequence=2, club_code="7i", shot_type="full", lie_start="fairway", start_distance_yards=160, lie_end="green", end_distance_yards=8.33),
                    ParsedShot(sequence=3, club_code="P", shot_type="putt", lie_start="green", start_distance_yards=8.33, lie_end="green", end_distance_yards=0.67),
                    ParsedShot(sequence=4, club_code="P", shot_type="putt", lie_start="green", start_distance_yards=0.67, lie_end="green", end_distance_yards=0.0, holed=True),
                ],
            )
        ],
        warnings=["Assumed the drive finished 160 yards out."],
    )
    client = FakeClient(parsed=parsed)
    caddie = ClaudeCaddie(db, player.id, client=client)
    result = caddie.parse_narrative("Hole 3: driver in the fairway, 7 iron to 25 feet, two putts", round_=open_round)
    assert result.parser == "claude"
    assert len(result.holes) == 1
    hole = result.holes[0]
    assert hole.score == 4 and hole.putts == 2 and hole.gir is True and hole.fairway_hit is True
    assert hole.shots[-1].holed is True and hole.shots[-1].end_distance_yards == 0
    assert result.warnings == ["Assumed the drive finished 160 yards out."]

    call = client.messages.calls[0]
    assert call["model"] == settings.anthropic_model
    assert call["output_format"] is ParsedNarrative
    prompt = call["messages"][0]["content"]
    assert COURSE_NAME in prompt and "3: par 4, 400 yds" in prompt
    assert "7i" in prompt and "tee, full, punch" in prompt and "three_putt" in prompt

    # The Claude caddie's log tool saves what the parser returned.
    saved = caddie.tool_log_hole(open_round.id, None, "Hole 3: driver in the fairway, 7 iron to 25 feet, two putts")
    assert saved["parser"] == "claude" and saved["saved"][0]["score"] == 4
    assert services.get_round(db, open_round.id).total_score == 4


def test_claude_parse_falls_back_to_heuristic_on_api_error(db, player, open_round):
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    import anthropic

    client = FakeClient(parsed=anthropic.APIConnectionError(message="down", request=req))
    caddie = ClaudeCaddie(db, player.id, client=client)
    result = caddie.parse_narrative("Hole 3: driver in the fairway, 7 iron to 25 feet, two putts", round_=open_round)
    assert result.parser == "heuristic"
    assert result.warnings[0].startswith("Claude unavailable: connection error")
    assert result.holes[0].score == 4


def test_heuristic_parser_remaining_distance_sets_next_shot_start(db, player, course, open_round):
    caddie = HeuristicCaddie(db, player.id)
    parsed = caddie.parse_narrative("Hole 1: driver down the middle, had 130 in, 9 iron to 12 feet, two putts", round_=open_round)
    shots = parsed.holes[0].shots
    assert shots[0].start_distance_yards == course.holes[0].yards
    assert shots[0].end_distance_yards == pytest.approx(130)
    assert shots[1].start_distance_yards == pytest.approx(130)


def test_heuristic_parser_uses_stated_result_for_putts(db, player, course, open_round):
    caddie = HeuristicCaddie(db, player.id)
    birdie = caddie.parse_narrative("Hole 2: 7 iron to 8 feet, birdie", round_=open_round).holes[0]
    assert birdie.putts == 1 and birdie.score == course.holes[1].par - 1
    bogey = caddie.parse_narrative("Hole 1: driver in the rough, 6 iron to 40 feet, bogey", round_=open_round).holes[0]
    assert bogey.putts == 3 and bogey.score == course.holes[0].par + 1
