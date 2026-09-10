"""The caddie agent: a conversational layer over the engine and services.

Two implementations share one interface:

* ``ClaudeCaddie`` - an Anthropic-powered agent that reasons in plain English
  and calls the same "tools" the REST API exposes (profile, courses, strategy,
  hole plans, shot logging).
* ``HeuristicCaddie`` - a deterministic keyword-driven fallback that needs no
  network and no API key.  It is deliberately useful on its own: it renders
  the strategy plan, club distances, error report and readiness, and parses
  shot narratives with regular expressions.

``get_caddie`` picks the implementation.  Every user message and assistant
reply is persisted as a ``ChatMessage`` so the caddie remembers context
between visits.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload

from golf import services
from golf.config import settings
from golf.engine.baselines import default_club_prior
from golf.models import ChatMessage, Course, Round
from golf.schemas import NarrativeParsedHole, NarrativeResponse, ShotCreate

try:  # the SDK is optional at import time so the heuristic caddie always works
    import anthropic
except ImportError:  # pragma: no cover - exercised only when the SDK is absent
    anthropic = None

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared vocabulary
# ---------------------------------------------------------------------------
SHOT_TYPES = ["tee", "full", "punch", "recovery", "pitch", "chip", "bunker", "putt"]
LIES = ["tee", "fairway", "rough", "sand", "green", "fringe", "recovery", "penalty", "ob"]
OUTCOME_TAGS = [
    "good", "short", "long", "left", "right", "hook", "slice", "pull", "push", "thin", "fat", "top",
    "shank", "penalty", "ob", "three_putt", "lip_out",
]
DEFAULT_YARDS_BY_PAR = {3: 170, 4: 400, 5: 520, 6: 620}
LIE_CARRY_FACTOR = {"tee": 1.0, "fairway": 1.0, "fringe": 1.0, "rough": 0.93, "sand": 0.85, "recovery": 0.5, "green": 1.0}
HISTORY_CONTEXT = 20
MAX_TOOL_ITERATIONS = 6
FALLBACK_BETAS = ["server-side-fallback-2026-07-01"]
REFUSAL_TEXT = (
    "I can't help with that one. I'm your caddie, so ask me about course strategy, "
    "club distances, what is costing you strokes, or tell me the shots you hit and I'll log them."
)

if anthropic is not None:
    _RATE_LIMIT_ERRORS: tuple[type[BaseException], ...] = (anthropic.RateLimitError,)
    _STATUS_ERRORS: tuple[type[BaseException], ...] = (anthropic.APIStatusError,)
    _CONNECTION_ERRORS: tuple[type[BaseException], ...] = (anthropic.APIConnectionError,)
    _ANY_API_ERRORS: tuple[type[BaseException], ...] = (anthropic.APIError,)
else:  # pragma: no cover
    class _NeverRaised(Exception):
        pass

    _RATE_LIMIT_ERRORS = _STATUS_ERRORS = _CONNECTION_ERRORS = _ANY_API_ERRORS = (_NeverRaised,)


# ---------------------------------------------------------------------------
# Structured-output models for the Claude narrative parser
# ---------------------------------------------------------------------------
class ParsedShot(BaseModel):
    sequence: int = Field(..., description="1-based order of the shot on the hole")
    club_code: str | None = Field(None, description="Club code from the player's bag, e.g. D, 3w, 7i, PW, P")
    shot_type: str = Field("full", description="One of: tee, full, punch, recovery, pitch, chip, bunker, putt")
    lie_start: str = Field("fairway", description="One of: tee, fairway, rough, sand, green, fringe, recovery, penalty, ob")
    start_distance_yards: float = Field(..., description="Distance to the hole before the shot, yards (putts: feet / 3)")
    lie_end: str = Field("fairway", description="Where the ball finished (same lie vocabulary)")
    end_distance_yards: float = Field(0.0, description="Distance to the hole after the shot, yards; 0 when holed")
    lateral_miss_yards: float | None = Field(None, description="+right / -left of target, if stated")
    distance_miss_yards: float | None = Field(None, description="+long / -short of target, if stated")
    outcome_tag: str | None = Field(None, description="One of the outcome tags, or null")
    penalty_strokes: int = Field(0, description="Penalty strokes incurred by this shot (water/OB = 1)")
    holed: bool = Field(False, description="True only for the final shot of the hole")


class ParsedHole(BaseModel):
    hole_number: int
    par: int
    score: int = Field(..., description="Number of shots plus penalty strokes")
    putts: int | None = None
    fairway_hit: bool | None = Field(None, description="Null on par 3s")
    gir: bool | None = None
    penalties: int = 0
    shots: list[ParsedShot] = Field(default_factory=list)


class ParsedNarrative(BaseModel):
    holes: list[ParsedHole] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list, description="Anything you had to guess")


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
SYSTEM_PROMPT_TEXT = """You are the player's personal golf caddie inside the Caddie strategy app.

Your one goal: help this golfer break their target score through course management - the right club,
the right aim point and the discipline to take the boring play. You are not a swing coach.

How you talk
- Plain English, short sentences, concrete numbers. Lead with the recommendation, then the why.
- Use the app's analogies when they help:
  * A club's dispersion is a shotgun pattern, not a single pellet - we aim the whole pattern, not the ball.
  * Expected value is the casino's edge: we make the play that wins on average over hundreds of rounds.
  * Aim at the "fat side" of the green - the side where a miss leaves an easy chip, never the short side.
  * "Bogey is fine, double is the enemy of 79" - blow-up holes are what stop people breaking their target.
- Be honest about confidence: when the profile is built on handicap priors rather than logged shots, say so.

Rules
- Never invent numbers. Every distance, probability, expected score or club recommendation must come from a
  tool call (tool_get_profile, tool_get_strategy, tool_hole_plan, tool_recent_rounds). If you have not called the
  tool, you do not know the number.
- When the user describes shots they hit ("driver in the rough, 8 iron to 20 feet, two putts"), log them with
  tool_log_hole. You need a round id: use the most recent open (incomplete) round from tool_recent_rounds, or
  ask which round if there is none. Confirm what was saved in one or two lines and then coach on it.
- If the user asks how to play a course or hole, call tool_get_strategy (course level) or tool_hole_plan (one hole)
  and translate the plan: tee club, aim, key thought, the miss to avoid, and the second-shot plan.
- Keep replies compact: a few short paragraphs or a short list. No headings unless the answer is long.

Tools are the app's own engine. Call them freely, in parallel when independent, and summarise their output
rather than dumping it."""

PARSER_SYSTEM = """You convert a golfer's plain-English description of holes into structured shot data for a
golf-analytics app. Be literal and conservative: only record what the text says or strongly implies, and list
anything you had to guess in `warnings`. Output only the structured object."""


TOOLS: list[dict[str, Any]] = [
    {
        "name": "tool_get_profile",
        "description": (
            "The player's learned profile: handicap, readiness (how much data the caddie has), per-club carry "
            "and dispersion (yards), tendencies, the top errors costing strokes, and score statistics."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "tool_list_courses",
        "description": "All courses stored in the app: id, name, par, yardage and number of holes.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "tool_get_strategy",
        "description": (
            "Course-level game plan for the player on a course: expected score, chance of breaking the target, "
            "summary advice and one line per hole (tee club, aim, expected strokes, double-bogey risk, key thought). "
            "Uses the latest saved plan unless regenerate is true. Generating a plan takes a few seconds."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "course_id": {"type": "integer", "description": "Course id from tool_list_courses"},
                "regenerate": {"type": "boolean", "description": "Force a fresh Monte Carlo plan", "default": False},
            },
            "required": ["course_id"],
        },
    },
    {
        "name": "tool_hole_plan",
        "description": (
            "Full plan for one hole: tee club and aim point, landing mix, the miss to avoid, approach and layup "
            "plans, alternatives with their cost, rationale and key thought."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "course_id": {"type": "integer"},
                "hole_number": {"type": "integer", "minimum": 1, "maximum": 36},
            },
            "required": ["course_id", "hole_number"],
        },
    },
    {
        "name": "tool_log_hole",
        "description": (
            "Parse a plain-English description of one or more holes into shots and save them to a round. "
            "Returns what was saved (score, putts, shots) plus parser warnings."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "round_id": {"type": "integer", "description": "Round to log into (see tool_recent_rounds)"},
                "hole_number": {"type": "integer", "description": "Hole the text refers to, if the text does not say"},
                "narrative_text": {"type": "string", "description": "The golfer's description, verbatim"},
            },
            "required": ["round_id", "narrative_text"],
        },
    },
    {
        "name": "tool_recent_rounds",
        "description": "The player's most recent rounds (id, date, course, score, holes logged, completed) and the open round id.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20}},
        },
    },
]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _fmt_pct(x: Any) -> str:
    try:
        return f"{float(x):.0%}"
    except (TypeError, ValueError):
        return "?"


def _fmt_num(x: Any, nd: int = 0) -> str:
    try:
        return f"{float(x):.{nd}f}"
    except (TypeError, ValueError):
        return "?"


def _text_of(content: Any) -> str:
    parts = []
    for block in content or []:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", "") or "")
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "\n".join(p for p in parts if p).strip()


_HOLE_MARKER_RE = re.compile(
    r"(?:\bhole\s*#?\s*(\d{1,2})\b)|(?:(?<![\w#])#\s?(\d{1,2})\b)|(?:\b(\d{1,2})(?:st|nd|rd|th)\b(?:\s+hole)?)",
    re.IGNORECASE,
)


def _marker_number(m: re.Match) -> int | None:
    for g in m.groups():
        if g:
            n = int(g)
            return n if 1 <= n <= 36 else None
    return None


def _first_hole_number(text: str) -> int | None:
    for m in _HOLE_MARKER_RE.finditer(text):
        n = _marker_number(m)
        if n:
            return n
    return None


# ---------------------------------------------------------------------------
# Heuristic narrative parser
# ---------------------------------------------------------------------------
_WORD_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}

_CLUB_SPECS: list[tuple[re.Pattern, Callable[[re.Match], str] | str, str | None]] = [
    (re.compile(r"\bdriver\b", re.I), "D", None),
    (re.compile(r"\b(?:drove|drive)\b", re.I), "D", "'drive' taken as driver"),
    (re.compile(r"\b(?:3|three)(?:-?w|[\s-]?wood)\b", re.I), "3w", None),
    (re.compile(r"\b(?:5|five)(?:-?w|[\s-]?wood)\b", re.I), "5w", None),
    (re.compile(r"\b(?:7|seven)(?:-?w|[\s-]?wood)\b", re.I), "7w", None),
    (re.compile(r"\b(?:fairway[\s-]?)?wood\b", re.I), "3w", "'wood' taken as 3 wood"),
    (re.compile(r"\b([2-6])(?:-?h|[\s-]?hybrid)\b", re.I), lambda m: f"{m.group(1)}h", None),
    (re.compile(r"\b(?:hybrid|rescue)\b", re.I), "3h", None),
    (re.compile(r"\b([2-9])(?:-?i|[\s-]?iron)\b", re.I), lambda m: f"{m.group(1)}i", None),
    (re.compile(r"\b(two|three|four|five|six|seven|eight|nine)[\s-]?iron\b", re.I),
     lambda m: f"{_WORD_NUM[m.group(1).lower()]}i", None),
    (re.compile(r"\b(?:pw|pitching[\s-]?wedge|p[\s-]?wedge)\b", re.I), "PW", None),
    (re.compile(r"\b(?:gw|aw|gap[\s-]?wedge|approach[\s-]?wedge|utility[\s-]?wedge)\b", re.I), "GW", None),
    (re.compile(r"\b(?:sw|sand[\s-]?wedge)\b", re.I), "SW", None),
    (re.compile(r"\b(?:lw|lob[\s-]?wedge)\b", re.I), "LW", None),
    (re.compile(r"\b(4[4-9]|5[0-3])\s?(?:degrees?|deg|°)", re.I), lambda m: "PW" if int(m.group(1)) <= 48 else "GW", None),
    (re.compile(r"\b(5[4-7])\s?(?:degrees?|deg|°)", re.I), "SW", None),
    (re.compile(r"\b(5[89]|6[0-4])\s?(?:degrees?|deg|°)", re.I), "LW", None),
    (re.compile(r"\bwedge\b", re.I), "PW", "'wedge' taken as pitching wedge"),
    (re.compile(r"\bputter\b", re.I), "P", None),
    (re.compile(r"(?<![\w'])D(?![\w'])"), "D", None),  # bare code, case-sensitive
]

_PUTT_COUNT_RE = re.compile(r"\b(one|two|three|four|five|1|2|3|4|5)[\s-]?putt(?:s|ed|ing)?\b", re.I)
_PUTT_RE = re.compile(r"\bputt(?:s|ed|ing)?\b", re.I)
_HOLED_RE = re.compile(
    r"\b(?:made\s+(?:it|the\s+putt|that(?:\s+one)?|this(?:\s+one)?|(?:a|the|my)\s+\d+(?:\.\d+)?[\s-]?(?:footer|foot|ft|feet))"
    r"|holed(?:\s+(?:it|out|the\s+putt|the\s+chip))?|drained|sank|sunk|tap(?:ped)?[\s-]?in|canned|knocked\s+it\s+in"
    r"|rolled\s+it\s+in|dead\s+cent(?:er|re)|chip(?:ped)?[\s-]?in|jarred|in\s+the\s+cup)\b",
    re.I,
)
_PUTT_MISS_EVENT_RE = re.compile(
    r"\blip(?:ped)?[\s-]?out\b|\bburn(?:ed|t)\s+the\s+edge\b|\bhorseshoe\b|\bmissed\s+(?:it|the\s+putt|that(?:\s+one)?)\b",
    re.I,
)
_MISS_PUTT_RE = re.compile(
    r"\b(?:missed|lip(?:ped)?[\s-]?out|burn(?:ed|t)|horseshoe|ran\s+(?:it\s+)?(?:by|past)|blew\s+(?:it\s+)?(?:by|past)"
    r"|left\s+(?:it|myself)|came\s+up\s+short|short|long)\b",
    re.I,
)

_SHOT_TYPE_SPECS: list[tuple[str, re.Pattern]] = [
    ("punch", re.compile(r"\bpunch(?:ed)?\b|\bknock(?:ed)?[\s-]down\b|\bstinger\b", re.I)),
    ("bunker", re.compile(r"\bbunker\s+shot\b|\bsand\s+shot\b|\bsplash(?:ed)?\b|\bblast(?:ed)?\b|\b(?:out\s+of|from)\s+the\s+(?:bunker|sand|trap)\b", re.I)),
    ("chip", re.compile(r"\bchip(?:ped|s)?\b|\bbump_and_run\b", re.I)),
    ("pitch", re.compile(r"\bpitch(?:ed)?\b|\bflop(?:ped)?\b|\blob(?:bed)?\b", re.I)),
    ("recovery", re.compile(r"\brecovery\b|\bhack(?:ed)?\s+out\b|\bchipped\s+out\b", re.I)),
]
_GENERIC_SHOT_RE = re.compile(
    r"\b(?:hit|knocked|smashed|bombed|laid[\s-]?up|lay[\s-]?up|layup|teed\s+off|tee\s+shot|second\s+shot|third\s+shot"
    r"|fourth\s+shot|approach(?:\s+shot)?)\b",
    re.I,
)
_STRONG_SHOT_RE = re.compile(
    r"\b(?:laid[\s-]?up|lay[\s-]?up|layup|teed\s+off|tee\s+shot|second\s+shot|third\s+shot|fourth\s+shot|approach(?:\s+shot)?)\b",
    re.I,
)

_LIE_NEGATION_RE = re.compile(
    r"\b(?:cleared|carried|over|past|flew|airmailed|through|beside|next\s+to|by|near|around|short\s+of|long\s+of|missed"
    r"|avoid(?:ed)?|skirted|just\s+short\s+of|in\s+front\s+of|behind)\s+(?:the\s+|a\s+)?"
    r"(?:water|pond|creek|lake|hazard|bunker|trap|sand|trees|green|fringe|rough|fairway)\b",
    re.I,
)
_LIE_SPECS: list[tuple[str, re.Pattern]] = [
    ("ob", re.compile(r"\bo\.?b\.?\b|\bout[\s-]of[\s-]bounds\b|\blost\s+(?:ball|it)\b|\bwhite\s+stakes\b", re.I)),
    ("penalty", re.compile(r"\bwater\b|\bpond\b|\bcreek\b|\blake\b|\bhazard\b|\bpenalty\s+area\b|\bthe\s+drink\b|\bstream\b|\bditch\b|\bmarsh\b|\bred\s+stakes\b|\byellow\s+stakes\b", re.I)),
    ("sand", re.compile(r"\bbunker\b|\bsand\b|\btrap\b|\bbeach\b", re.I)),
    ("recovery", re.compile(r"\btrees?\b|\bwoods\b|\bforest\b|\bjail\b|\bbush(?:es)?\b|\bblocked\s+out\b|\bpine\s+straw\b", re.I)),
    ("fringe", re.compile(r"\bfringe\b|\bcollar\b|\bapron\b|\bfrog[\s-]?hair\b|\bjust\s+off\s+the\s+green\b", re.I)),
    ("green", re.compile(r"\bgreen\b|\bdance[\s-]?floor\b|\bgir\b|\bputting\s+surface\b", re.I)),
    ("rough", re.compile(r"\brough\b|\bfescue\b|\bnative\b|\blong\s+grass\b|\bthick\s+stuff\b|\bjunk\b|\bcabbage\b|\bhay\b", re.I)),
    ("fairway", re.compile(r"\bfairway\b|\bshort\s+grass\b|\bdown\s+the\s+middle\b|\bmiddle\s+of\s+the\s+hole\b|\bin\s+play\b|\bin\s+the\s+middle\b", re.I)),
]

_TAG_SPECS: list[tuple[str, re.Pattern]] = [
    ("shank", re.compile(r"\bshank(?:ed)?\b|\bhosel\b", re.I)),
    ("top", re.compile(r"\btopped\b|\btop(?:ped)?\s+it\b", re.I)),
    ("fat", re.compile(r"\bfat\b|\bchunk(?:ed)?\b|\bheavy\b|\bduff(?:ed)?\b", re.I)),
    ("thin", re.compile(r"\bthin(?:ned)?\b|\bbladed\b|\bskull(?:ed)?\b", re.I)),
    ("hook", re.compile(r"\bhook(?:ed)?\b|\bsnap[\s-]hook\b|\bduck[\s-]hook\b", re.I)),
    ("slice", re.compile(r"\bslice[ds]?\b|\bbanana\b", re.I)),
    ("pull", re.compile(r"\bpull(?:ed)?\b|\byank(?:ed)?\b", re.I)),
    ("push", re.compile(r"\bpush(?:ed)?\b|\bblock(?:ed)?\b", re.I)),
    ("lip_out", re.compile(r"\blip(?:ped)?[\s-]?out\b|\bburn(?:ed|t)\s+the\s+edge\b|\bhorseshoe\b", re.I)),
    ("left", re.compile(r"\bleft\b(?!\s+(?:myself|me|it|us|him|her|a|an|the|about|with|of|to\s+go))", re.I)),
    ("right", re.compile(r"\bright\b(?!\s+(?:at|next|in|on|of|by|there|down|into|to|beside|behind|over|up|off|where))", re.I)),
    ("short", re.compile(r"\bshort\b(?!\s*-?\s*(?:game|sided?|iron|par|grass|of\s+the\s+(?:water|hazard|trouble|creek|pond)))", re.I)),
    ("long", re.compile(r"\blong\b(?!\s+(?:iron|putt|way|game|grass))", re.I)),
    ("good", re.compile(r"\bgood\b|\bpure\b|\bflush(?:ed)?\b|\bstriped\b|\bperfect\b|\bgreat\b|\bsolid\b|\bstuffed\b|\bnice\b", re.I)),
]

_DIST_UNIT = r"(feet|foot|ft|yards?|yds?|inches|inch)"
_END_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bto\s+(?:about|around|maybe|roughly|~|approx(?:imately)?)?\s*(\d+(?:\.\d+)?)\s*" + _DIST_UNIT + r"\b", re.I),
    re.compile(r"\b(?:left|leaving|leaves)\s+(?:myself|me|us|it)?\s*(?:about|around|~)?\s*(?:a|an)?\s*(\d+(?:\.\d+)?)[\s-]*(feet|foot|ft|footer|yards?|yds?|inches|inch)\b", re.I),
    re.compile(r"\b(\d+(?:\.\d+)?)[\s-]?(footer)\b", re.I),
    re.compile(r"\b(\d+(?:\.\d+)?)\s*" + _DIST_UNIT + r"\b", re.I),
]
_START_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bfrom\s+(?:about|around|~)?\s*(\d+(?:\.\d+)?)\s*(feet|foot|ft|yards?|yds?)?\b", re.I),
    re.compile(r"\b(?:had|have|with)\s+(?:about|around|~)?\s*(\d+(?:\.\d+)?)\s*(feet|foot|ft|yards?|yds?)?\s*(?:in|left|out|to\s+go|to\s+the\s+(?:pin|flag|hole|green|front|middle|centre|center))\b", re.I),
    re.compile(r"\b(\d{2,3})\s*(yards?|yds?)?\s+(?:out|to\s+go)\b", re.I),
]
_NEAR_GREEN_RE = re.compile(
    r"\b(?:(?:just\s+)?short\s+of\s+the\s+green|in\s+front\s+of\s+the\s+green|(?:just\s+)?(?:over|long\s+of|behind|past)\s+the\s+green"
    r"|pin[\s-]?high|(?:just\s+)?missed\s+the\s+green|green[\s-]?side|next\s+to\s+the\s+green|beside\s+the\s+green|around\s+the\s+green)\b",
    re.I,
)
_PAR_STATEMENT_RE = re.compile(
    r"\b\d{2,3}\s*(?:yards?|yds?)\s*,?\s*par\s*[3-6]\b|\bpar\s*[3-6]\s*,?\s*\d{2,3}\s*(?:yards?|yds?)\b|\bpar[\s-]?[3-6]\b",
    re.I,
)
_SPLIT_RE = re.compile(r"[,;:.!?\n]+|\band\s+then\b|\bthen\b|\band\b|\bfollowed\s+by\b|\bafter\s+that\b", re.I)
_PROTECT = [
    (re.compile(r"\bup\s+and\s+down\b", re.I), "up_and_down"),
    (re.compile(r"\bbump\s+and\s+run\b", re.I), "bump_and_run"),
    (re.compile(r"\bstroke\s+and\s+distance\b", re.I), "stroke_and_distance"),
]


def _to_yards(value: float, unit: str, default_feet: bool) -> tuple[float, bool]:
    """Return (yards, was_feet)."""
    u = (unit or "").lower()
    if u.startswith("f"):  # feet / foot / ft / footer
        return value / 3.0, True
    if u.startswith("in"):
        return value / 36.0, True
    if u.startswith("y"):
        return value, False
    return (value / 3.0, True) if default_feet else (value, False)


def _overlaps(a: tuple[int, int], spans: list[tuple[int, int]]) -> bool:
    return any(a[0] < e and s < a[1] for s, e in spans)


@dataclass
class _Event:
    kind: str                       # "shot" | "putt"
    raw: str
    club: str | None = None
    shot_type: str | None = None
    lie_end: str | None = None
    end_yards: float | None = None
    end_feet: bool = False
    start_yards: float | None = None
    tag: str | None = None
    penalty: int = 0
    holed: bool = False
    n_putts: int = 0
    lie_stated: bool = False
    near_green: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        """A shot we know where it finished (used to decide if 'hit it...' starts a new shot)."""
        return self.kind == "putt" or self.lie_stated or self.end_yards is not None or self.holed


class HeuristicNarrativeParser:
    """Regex-based, deterministic parser for shot narratives (no LLM)."""

    def __init__(self, handicap: float = 15.0, bag: list[tuple[str, str]] | None = None):
        self.handicap = float(handicap or 15.0)
        self.bag = list(bag or [])  # (code, category)
        self._by_lower = {c.lower(): c for c, _ in self.bag}

    # ------------------------------------------------------------------
    def parse(self, text: str, hole_number: int | None = None, round_: Any = None) -> NarrativeResponse:
        warnings: list[str] = []
        course_holes: dict[int, tuple[int, int]] = {}
        course = getattr(round_, "course", None)
        if course is not None:
            for h in getattr(course, "holes", None) or []:
                course_holes[h.number] = (h.par, h.yards)
        holes: list[NarrativeParsedHole] = []
        for num, segment in self._split_holes(text, hole_number, warnings):
            hole = self._parse_hole(num, segment, course_holes, warnings)
            if hole is not None:
                holes.append(hole)
        if not holes:
            warnings.append("No shots recognised - try 'hole 5: driver in the fairway, 8 iron to 20 feet, two putts'.")
        return NarrativeResponse(holes=holes, parser="heuristic", warnings=warnings)

    # ------------------------------------------------------------------
    def _split_holes(self, text: str, hole_number: int | None, warnings: list[str]) -> list[tuple[int, str]]:
        markers = [(m, _marker_number(m)) for m in _HOLE_MARKER_RE.finditer(text)]
        markers = [(m, n) for m, n in markers if n]
        if not markers:
            if hole_number is None:
                warnings.append("No hole number stated - assumed hole 1.")
            return [(hole_number or 1, text)]
        segments = []
        preamble = text[: markers[0][0].start()]
        if self._has_event_words(preamble):
            if hole_number is not None:
                segments.append((hole_number, preamble))
            else:
                warnings.append("Ignored text before the first hole marker: " + preamble.strip()[:60])
        for i, (m, n) in enumerate(markers):
            end = markers[i + 1][0].start() if i + 1 < len(markers) else len(text)
            segments.append((n, text[m.end():end]))
        return segments

    @staticmethod
    def _has_event_words(text: str) -> bool:
        if not re.search(r"[A-Za-z]{3,}", text):
            return False
        return any(p.search(text) for p, _, _ in _CLUB_SPECS) or bool(_PUTT_RE.search(text)) or any(p.search(text) for _, p in _SHOT_TYPE_SPECS)

    # ------------------------------------------------------------------
    def _parse_hole(self, num: int, segment: str, course_holes: dict[int, tuple[int, int]], warnings: list[str]) -> NarrativeParsedHole | None:
        par, yards = course_holes.get(num, (None, None))
        m = re.search(r"\bpar[\s-]?([3-6])\b", segment, re.I)
        if par is None:
            par = int(m.group(1)) if m else 4
            if not m:
                warnings.append(f"Hole {num}: par not known - assumed par 4.")
        if yards is None:
            ym = re.search(r"\b(\d{2,3})\s*(?:yards?|yds?)\s*,?\s*par\b|\bpar\s*[3-6]\s*,?\s*(\d{2,3})\s*(?:yards?|yds?)\b", segment, re.I)
            if ym:
                yards = int(ym.group(1) or ym.group(2))
            else:
                yards = DEFAULT_YARDS_BY_PAR.get(par, 400)
                warnings.append(f"Hole {num}: length not known - assumed {yards} yards for a par {par}.")
        cleaned = _PAR_STATEMENT_RE.sub(" ", segment)
        stated = self._stated_result(cleaned)
        events = self._events(cleaned)
        if not events:
            return None
        shots = self._build_shots(num, par, float(yards), events, warnings, stated_result=stated)
        if not shots:
            return None
        penalties = sum(s.penalty_strokes for s in shots)
        putt_shots = [s for s in shots if s.shot_type == "putt"]
        finished = shots[-1].holed
        putts = len(putt_shots) if (putt_shots or finished) else None
        used = 0
        gir = False
        for s in shots:
            used += 1 + s.penalty_strokes
            if s.lie_end == "green" and used <= par - 2:
                gir = True
                break
        fairway_hit = (shots[0].lie_end == "fairway") if par > 3 else None
        return NarrativeParsedHole(
            hole_number=num, par=par, score=len(shots) + penalties, putts=putts, fairway_hit=fairway_hit,
            gir=gir, penalties=penalties, shots=shots,
        )

    # ------------------------------------------------------------------
    def _events(self, segment: str) -> list[_Event]:
        text = segment
        for pat, repl in _PROTECT:
            text = pat.sub(repl, text)
        frags = [f.strip(" -:;,.!\n\t\"'") for f in _SPLIT_RE.split(text)]
        events: list[_Event] = []
        for frag in frags:
            if not frag:
                continue
            ev, extra = self._classify(frag, events[-1] if events else None)
            if ev is None:
                if events:
                    self._merge_modifier(events[-1], frag)
                continue
            events.append(ev)
            if extra is not None:
                events.append(extra)
        return events

    def _extract_club(self, text: str) -> tuple[str | None, str, str | None]:
        best: tuple[re.Match, Any, str | None] | None = None
        for pat, code, note in _CLUB_SPECS:
            m = pat.search(text)
            if m and (best is None or m.start() < best[0].start()):
                best = (m, code, note)
        if best is None:
            return None, text, None
        m, code, note = best
        code = code(m) if callable(code) else code
        return self._normalise_code(code), text[: m.start()] + " " + text[m.end():], note

    def _normalise_code(self, code: str) -> str:
        if code.lower() in self._by_lower:
            return self._by_lower[code.lower()]
        if code == "3h":
            hyb = next((c for c, cat in self.bag if cat == "hybrid"), None)
            if hyb:
                return hyb
        if code == "3w":
            wood = next((c for c, cat in self.bag if cat == "wood"), None)
            if wood:
                return wood
        return code

    @staticmethod
    def _lie(text: str) -> str | None:
        t = _LIE_NEGATION_RE.sub(" ", text)
        for lie, pat in _LIE_SPECS:
            if pat.search(t):
                return lie
        return None

    @staticmethod
    def _tag(text: str) -> str | None:
        for tag, pat in _TAG_SPECS:
            if pat.search(text):
                return tag
        return None

    @staticmethod
    def _distances(text: str, is_putt: bool) -> tuple[float | None, float | None, bool]:
        used: list[tuple[int, int]] = []
        start = None
        for pat in _START_PATTERNS:
            m = pat.search(text)
            if m:
                unit = m.group(2) if m.lastindex and m.lastindex >= 2 else ""
                start, _ = _to_yards(float(m.group(1)), unit or "", default_feet=is_putt)
                used.append(m.span())
                break
        end, end_feet = None, False
        for pat in _END_PATTERNS:
            for m in pat.finditer(text):
                if _overlaps(m.span(), used):
                    continue
                unit = m.group(2) if m.lastindex and m.lastindex >= 2 else ""
                end, end_feet = _to_yards(float(m.group(1)), unit or "", default_feet=is_putt)
                used.append(m.span())
                break
            if end is not None:
                break
        if is_putt and start is None and end is not None:
            # "made a 20 footer" / "30 foot putt": the number is where the putt started.
            start, end = end, None
        return start, end, end_feet

    def _classify(self, frag: str, prev: _Event | None) -> tuple[_Event | None, _Event | None]:
        club, scrubbed, note = self._extract_club(frag)
        putt_count_m = _PUTT_COUNT_RE.search(scrubbed)
        putt_word = bool(_PUTT_RE.search(scrubbed))
        holed_phrase = bool(_HOLED_RE.search(scrubbed))
        stype = next((t for t, p in _SHOT_TYPE_SPECS if p.search(scrubbed)), None)
        up_and_down = bool(re.search(r"\bup_and_down\b", scrubbed, re.I))
        lie = self._lie(scrubbed)
        tag = self._tag(scrubbed)
        penalty = 1 if re.search(r"\bpenalt(?:y|ies)\b(?!\s+area)|\bunplayable\b", scrubbed, re.I) else 0

        miss_event = bool(_PUTT_MISS_EVENT_RE.search(scrubbed))
        is_putt = club == "P" or (
            club is None and stype is None and not up_and_down
            and (putt_word or miss_event or (holed_phrase and not _GENERIC_SHOT_RE.search(scrubbed)))
        )
        if is_putt:
            start, _, _ = self._distances(scrubbed, is_putt=True)
            if putt_count_m:
                n = _WORD_NUM.get(putt_count_m.group(1).lower()) or int(putt_count_m.group(1))
                holed = True
            elif holed_phrase:
                n, holed = 1, True
            else:
                n = 1
                holed = not bool(_MISS_PUTT_RE.search(scrubbed))
            ev = _Event(kind="putt", raw=frag, club="P", n_putts=max(n, 1), holed=holed, start_yards=start, tag=tag)
            return ev, None

        is_shot = club is not None or stype is not None or up_and_down or bool(_STRONG_SHOT_RE.search(scrubbed))
        if not is_shot and _GENERIC_SHOT_RE.search(scrubbed):
            # "hit it to 5 feet" right after a bare "7 iron" describes the same shot; after a finished shot it is a new one.
            is_shot = prev is None or prev.complete
        if not is_shot:
            return None, None
        start, end, end_feet = self._distances(scrubbed, is_putt=False)
        ev = _Event(
            kind="shot", raw=frag, club=club, shot_type=stype, lie_end=lie, lie_stated=lie is not None,
            end_yards=end, end_feet=end_feet, start_yards=start, tag=tag, penalty=penalty, holed=holed_phrase,
            near_green=bool(_NEAR_GREEN_RE.search(scrubbed)),
        )
        if note:
            ev.notes.append(note)
        if club is None:
            ev.notes.append("no club stated")
        extra = None
        if up_and_down:
            ev.shot_type = ev.shot_type or "chip"
            ev.lie_end, ev.lie_stated = "green", True
            if ev.end_yards is None:
                ev.end_yards, ev.end_feet = 4 / 3.0, True
            extra = _Event(kind="putt", raw="(up and down)", club="P", n_putts=1, holed=True)
        return ev, extra

    def _merge_modifier(self, ev: _Event, frag: str) -> None:
        """A fragment without a shot of its own describes the previous shot ('long and left', 'in the rough')."""
        if ev.kind == "putt":
            if _HOLED_RE.search(frag):
                ev.holed = True
            return
        lie = self._lie(frag)
        if ev.lie_end is None and lie is not None:
            ev.lie_end, ev.lie_stated = lie, True
        if ev.tag is None:
            ev.tag = self._tag(frag)
        start, end, end_feet = self._distances(frag, is_putt=False)
        if ev.end_yards is None and end is not None:
            ev.end_yards, ev.end_feet = end, end_feet
        if ev.end_yards is None and start is not None:
            # "…, had 130 in": a remaining distance stated after a shot is where
            # that shot finished (and where the next one starts), not its start.
            ev.end_yards = start
        if _NEAR_GREEN_RE.search(frag):
            ev.near_green = True
        if re.search(r"\bpenalt(?:y|ies)\b(?!\s+area)|\bunplayable\b", frag, re.I):
            ev.penalty = max(ev.penalty, 1)
        if _HOLED_RE.search(frag) and not _PUTT_RE.search(frag):
            ev.holed = True

    # ------------------------------------------------------------------
    def _carry(self, club: str | None, lie_start: str) -> float | None:
        if not club or club == "P":
            return None
        prior = default_club_prior(club, self.handicap)
        if not prior:
            return None
        return prior["carry_mean"] * LIE_CARRY_FACTOR.get(lie_start, 1.0)

    @staticmethod
    def _infer_type(lie_start: str, start: float, club: str | None) -> str:
        if lie_start == "sand":
            return "bunker"
        if lie_start == "recovery":
            return "recovery"
        if lie_start in ("green", "fringe") or start <= 30:
            return "chip"
        if start <= 60 and (club is None or club.upper() in ("PW", "GW", "SW", "LW")):
            return "pitch"
        return "full"

    @staticmethod
    def _stated_result(text: str) -> int | None:
        """Score relative to par when the golfer states the result ('made par', 'bogey')."""
        m = re.search(r"\b(eagle|birdie|par|bogey|double(?:\s*bogey)?|triple(?:\s*bogey)?)\b(?!\s*[3-6])", text, re.I)
        if not m:
            return None
        word = m.group(1).lower()
        if word.startswith("double"):
            return 2
        if word.startswith("triple"):
            return 3
        return {"eagle": -2, "birdie": -1, "par": 0, "bogey": 1}[word]

    @staticmethod
    def _putt_chain(start: float, n: int) -> list[float]:
        """Distances left after each putt (yards); last is always 0."""
        if n <= 1:
            return [0.0]
        presets = {2: [2 / 3.0], 3: [2.0, 2 / 3.0], 4: [10 / 3.0, 5 / 3.0, 2 / 3.0]}
        mids = presets.get(n)
        if mids is None:
            mids = [start * (1 - (i + 1) / n) for i in range(n - 1)]
        mids = [min(m, start * 0.5) for m in mids]
        return mids + [0.0]

    def _build_shots(self, num: int, par: int, yards: float, events: list[_Event], warnings: list[str], stated_result: int | None = None) -> list[ShotCreate]:
        shots: list[ShotCreate] = []
        remaining = yards
        lie = "tee"
        seq = 0
        finished = False
        for i, ev in enumerate(events):
            if finished:
                warnings.append(f"Hole {num}: ignored '{ev.raw}' after the ball was holed.")
                continue
            nxt = events[i + 1] if i + 1 < len(events) else None
            if ev.kind == "putt":
                start = ev.start_yards if ev.start_yards is not None else remaining
                if lie not in ("green", "fringe") and shots:
                    warnings.append(f"Hole {num}: putting after a shot that finished in the {lie}; treated as on the green.")
                chain = self._putt_chain(start, ev.n_putts)
                if not ev.holed:
                    chain[-1] = min(2 / 3.0, start * 0.5)
                d = start
                for k, nxt_d in enumerate(chain):
                    seq += 1
                    tag = ev.tag if (k == len(chain) - 1 and ev.tag) else None
                    if ev.n_putts >= 3 and k == 0:
                        tag = "three_putt"
                    if ev.tag == "lip_out" and k == len(chain) - 1:
                        tag = "lip_out"
                    holed = nxt_d == 0.0 and (ev.holed or k < len(chain) - 1)
                    shots.append(ShotCreate(
                        sequence=seq, club_code="P", shot_type="putt", lie_start="green",
                        start_distance_yards=round(max(d, 0.0), 2), lie_end="green",
                        end_distance_yards=round(max(nxt_d, 0.0), 2), outcome_tag=tag, holed=holed,
                        notes=ev.raw[:200] if k == 0 else None,
                    ))
                    d = nxt_d
                remaining, lie = d, "green"
                finished = shots[-1].holed
                continue

            # --- a shot with a club (or a chip/pitch/punch/etc.) ---
            seq += 1
            start = ev.start_yards if ev.start_yards is not None else remaining
            lie_start = lie
            if seq == 1:
                stype, lie_start = "tee", "tee"
            else:
                stype = ev.shot_type or self._infer_type(lie_start, start, ev.club)
                if stype == "bunker" and lie_start != "sand":
                    lie_start = "sand"
                elif stype in ("punch", "recovery") and lie_start not in ("recovery", "rough"):
                    lie_start = "recovery"
            lie_end = ev.lie_end
            if lie_end is None:
                if ev.holed or ev.end_feet or (nxt is not None and nxt.kind == "putt"):
                    lie_end = "green"
                else:
                    lie_end = "fairway"
                    warnings.append(f"Hole {num}, shot {seq}: no lie stated - assumed fairway.")
            penalty = ev.penalty
            if lie_end in ("penalty", "ob") and penalty == 0:
                penalty = 1
            tag = ev.tag
            if tag is None and lie_end == "penalty":
                tag = "penalty"
            elif tag is None and lie_end == "ob":
                tag = "ob"
            club_label = ev.club or "the shot"
            if ev.holed:
                end = 0.0
            elif ev.end_yards is not None:
                end = ev.end_yards
            elif lie_end in ("green", "fringe"):
                end = 10.0
                warnings.append(f"Hole {num}, shot {seq}: on the green but no distance stated - assumed 30 feet.")
            elif lie_end == "ob":
                end = start  # stroke and distance: play again from the same spot
            elif ev.near_green and lie_end not in ("penalty",):
                end = min(20.0, max(start * 0.5, 5.0))
                warnings.append(f"Hole {num}, shot {seq}: finished around the green - assumed {end:.0f} yards from the hole.")
            else:
                carry = self._carry(ev.club, lie_start)
                if carry is None:
                    carry = min(150.0, 0.6 * start)
                    warnings.append(f"Hole {num}, shot {seq}: no club stated - guessed {carry:.0f} yards of progress.")
                if lie_end == "penalty":
                    end = max(start - carry, 15.0) + 10.0  # drop roughly where it crossed, a little back
                    warnings.append(f"Hole {num}, shot {seq}: estimated the drop at {end:.0f} yards out.")
                elif carry >= start - 10:
                    end = 15.0
                    warnings.append(f"Hole {num}, shot {seq}: {club_label} carries about the whole way - assumed it finished 15 yards from the hole.")
                else:
                    end = start - carry
                    warnings.append(f"Hole {num}, shot {seq}: no distance stated - estimated {end:.0f} yards left after {club_label}.")
            for n in ev.notes:
                warnings.append(f"Hole {num}, shot {seq}: {n}.")
            shots.append(ShotCreate(
                sequence=seq, club_code=ev.club, shot_type=stype, lie_start=lie_start,
                start_distance_yards=round(max(start, 0.0), 1), lie_end=lie_end,
                end_distance_yards=round(max(end, 0.0), 2), outcome_tag=tag, penalty_strokes=penalty,
                holed=ev.holed, notes=ev.raw[:200],
            ))
            if ev.holed:
                remaining, lie, finished = 0.0, "green", True
            elif lie_end == "ob":
                remaining, lie = start, lie_start
            elif lie_end == "penalty":
                remaining, lie = end, "rough"
            else:
                remaining, lie = end, lie_end
        if shots and not shots[-1].holed:
            if lie in ("green", "fringe"):
                n = 1 if remaining <= 1.0 else 2
                if stated_result is not None:
                    # "…, birdie": size the putt chain so the score matches the stated result.
                    so_far = len(shots) + sum(sh.penalty_strokes for sh in shots)
                    n = max(1, min(par + stated_result - so_far, 4))
                chain = self._putt_chain(remaining, n)
                d = remaining
                for nxt_d in chain:
                    seq += 1
                    shots.append(ShotCreate(
                        sequence=seq, club_code="P", shot_type="putt", lie_start="green",
                        start_distance_yards=round(max(d, 0.0), 2), lie_end="green",
                        end_distance_yards=round(nxt_d, 2), holed=nxt_d == 0.0,
                    ))
                    d = nxt_d
                warnings.append(f"Hole {num}: no putts described - assumed {n} putt{'s' if n > 1 else ''} to finish.")
            else:
                warnings.append(f"Hole {num}: the description stops before the ball is holed - score counts only the shots described.")
        return shots


# ---------------------------------------------------------------------------
# Base caddie: persistence + tools shared by both implementations
# ---------------------------------------------------------------------------
class BaseCaddie:
    provider: str = "heuristic"

    def __init__(self, db: Session, player_id: int):
        self.db = db
        self.player_id = player_id
        self._parser: HeuristicNarrativeParser | None = None

    # -- chat persistence ------------------------------------------------
    def _persist(self, role: str, content: str) -> ChatMessage:
        row = ChatMessage(player_id=self.player_id, role=role, content=content)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def _recent_messages(self, limit: int) -> list[ChatMessage]:
        rows = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.player_id == self.player_id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(limit)
            .all()
        )
        return list(reversed(rows))

    def history(self, limit: int = 40) -> list[dict[str, Any]]:
        return [
            {"id": m.id, "role": m.role, "content": m.content,
             "created_at": m.created_at.isoformat() if m.created_at else None}
            for m in self._recent_messages(limit)
        ]

    def _finish(self, reply: str, actions: list[dict[str, Any]]) -> dict[str, Any]:
        self._persist("assistant", reply)
        return {"reply": reply, "provider": self.provider, "actions": actions, "history": self.history(HISTORY_CONTEXT)}

    # -- public interface ------------------------------------------------
    def chat(self, message: str, course_id: int | None = None, hole_number: int | None = None) -> dict[str, Any]:
        raise NotImplementedError

    def parse_narrative(self, text: str, hole_number: int | None = None, round_: Any = None) -> NarrativeResponse:
        return self._heuristic_parser().parse(text, hole_number=hole_number, round_=round_)

    def _heuristic_parser(self) -> HeuristicNarrativeParser:
        if self._parser is None:
            player = services.get_player(self.db, self.player_id)
            handicap = float(player.handicap_index) if player and player.handicap_index is not None else 15.0
            bag = [(c.code, c.category) for c in (player.clubs if player else []) if getattr(c, "active", True)]
            self._parser = HeuristicNarrativeParser(handicap=handicap, bag=bag)
        return self._parser

    # -- tools -----------------------------------------------------------
    def tool_get_profile(self) -> dict[str, Any]:
        snap = services.latest_profile(self.db, self.player_id)
        p = snap.data or {}
        player = services.get_player(self.db, self.player_id)
        readiness = p.get("readiness") or {}
        clubs = {}
        for code, d in (p.get("clubs") or {}).items():
            clubs[code] = {
                "name": d.get("name", code),
                "carry_mean": d.get("carry_mean"), "carry_sigma": d.get("carry_sigma"),
                "lateral_sigma": d.get("lateral_sigma"), "lateral_bias": d.get("lateral_bias"),
                "n_samples": d.get("n_samples", 0), "confidence": d.get("confidence", 0.0),
                "source": d.get("source"),
            }
        return {
            "player": p.get("player_name") or (player.name if player else None),
            "handicap": p.get("handicap"),
            "target_score": player.target_score if player else (p.get("score_stats") or {}).get("target"),
            "rounds_logged": p.get("rounds", 0),
            "shots_logged": p.get("shots", 0),
            "readiness": {k: readiness.get(k) for k in ("score", "level", "message", "rounds_logged", "rounds_needed")},
            "clubs": clubs,
            "tendencies": p.get("tendencies") or {},
            "top_errors": (p.get("errors") or [])[:5],
            "score_stats": p.get("score_stats") or {},
        }

    def tool_list_courses(self) -> list[dict[str, Any]]:
        courses = self.db.query(Course).options(selectinload(Course.holes)).order_by(Course.name).all()
        return [
            {"id": c.id, "name": c.name, "par": c.par, "yardage": c.yardage, "hole_count": len(c.holes or [])}
            for c in courses
        ]

    def _plan_for(self, course_id: int, regenerate: bool = False):
        plan = None if regenerate else services.latest_plan(self.db, self.player_id, course_id)
        if plan is None:
            plan = services.generate_plan(self.db, self.player_id, course_id)
        return plan

    def tool_get_strategy(self, course_id: int, regenerate: bool = False) -> dict[str, Any]:
        if course_id is None:
            raise ValueError("course_id is required")
        plan = self._plan_for(int(course_id), regenerate)
        d = plan.data or {}
        holes = []
        for h in d.get("holes") or []:
            tee = h.get("tee") or {}
            holes.append({
                "hole": h.get("hole"), "par": h.get("par"), "yards": h.get("yards"),
                "tee_club": tee.get("club"), "tee_club_name": tee.get("club_name"), "aim": tee.get("aim"),
                "expected_strokes": h.get("expected_strokes"), "p_double_plus": h.get("p_double_plus"),
                "key_thought": h.get("key_thought"),
            })
        return {
            "plan_id": plan.id,
            "course": d.get("course") or {"id": course_id},
            "objective": d.get("objective", plan.objective),
            "created_at": plan.created_at.isoformat() if plan.created_at else None,
            "par": d.get("par"),
            "expected_score": d.get("expected_score", plan.expected_score),
            "p_break_target": d.get("p_break_target", plan.p_break_target),
            "target_score": d.get("target_score"),
            "expected_penalties": d.get("expected_penalties"),
            "readiness": d.get("readiness"),
            "summary": d.get("summary") or {},
            "holes": holes,
        }

    def tool_hole_plan(self, course_id: int, hole_number: int) -> dict[str, Any]:
        plan = self._plan_for(int(course_id))
        d = plan.data or {}
        hole = next((h for h in d.get("holes") or [] if h.get("hole") == int(hole_number)), None)
        if hole is None:
            raise ValueError(f"Hole {hole_number} is not part of this course's plan")
        out = {k: v for k, v in hole.items() if k != "map"}
        tee = dict(out.get("tee") or {})
        tee.pop("landing_points", None)
        out["tee"] = tee
        out["course"] = d.get("course") or {"id": course_id}
        out["plan_id"] = plan.id
        return out

    def _save_parsed(self, rnd: Round, parsed: NarrativeResponse) -> list[dict[str, Any]]:
        saved = []
        for h in parsed.holes:
            payload = h.model_dump()
            payload["shots"] = [s.model_dump() for s in h.shots]
            hr = services.upsert_hole_result(self.db, rnd, payload)
            saved.append({
                "hole_number": hr.hole_number, "par": hr.par, "score": hr.score, "putts": hr.putts,
                "fairway_hit": hr.fairway_hit, "gir": hr.gir, "penalties": hr.penalties,
                "shots": [
                    {"sequence": s.sequence, "club": s.club_code, "type": s.shot_type, "from": s.lie_start,
                     "start_yards": s.start_distance_yards, "to": s.lie_end, "end_yards": s.end_distance_yards,
                     "tag": s.outcome_tag, "penalty": s.penalty_strokes, "holed": s.holed}
                    for s in h.shots
                ],
            })
        fresh = services.get_round(self.db, rnd.id)
        if fresh is not None:
            services.recompute_round_total(self.db, fresh)
        return saved

    def tool_log_hole(self, round_id: int, hole_number: int | None, narrative_text: str) -> dict[str, Any]:
        rnd = services.get_round(self.db, int(round_id))
        if rnd is None or rnd.player_id != self.player_id:
            raise ValueError(f"Round {round_id} not found for this player")
        parsed = self.parse_narrative(narrative_text, hole_number=hole_number, round_=rnd)
        if not parsed.holes:
            return {"round_id": rnd.id, "saved": [], "parser": parsed.parser, "warnings": parsed.warnings}
        saved = self._save_parsed(rnd, parsed)
        fresh = services.get_round(self.db, rnd.id)
        return {
            "round_id": rnd.id,
            "course": rnd.course.name if rnd.course else None,
            "parser": parsed.parser,
            "saved": saved,
            "round_total": fresh.total_score if fresh else None,
            "holes_logged": len(fresh.holes) if fresh else None,
            "warnings": parsed.warnings,
        }

    def _open_round(self) -> Round | None:
        for r in services.player_rounds(self.db, self.player_id):
            if not r.completed:
                return r
        return None

    def tool_recent_rounds(self, limit: int = 5) -> dict[str, Any]:
        rounds = services.player_rounds(self.db, self.player_id)
        open_round = next((r for r in rounds if not r.completed), None)
        return {
            "open_round_id": open_round.id if open_round else None,
            "rounds": [
                {
                    "id": r.id, "date": r.played_on.isoformat() if r.played_on else None,
                    "course": r.course.name if r.course else None, "course_id": r.course_id,
                    "score": r.total_score, "holes_logged": len(r.holes or []), "completed": r.completed,
                    "logging_mode": r.logging_mode,
                }
                for r in rounds[: max(int(limit or 5), 1)]
            ],
        }

    def _dispatch_tool(self, name: str, inp: dict[str, Any]) -> Any:
        inp = inp or {}
        if name == "tool_get_profile":
            return self.tool_get_profile()
        if name == "tool_list_courses":
            return self.tool_list_courses()
        if name == "tool_get_strategy":
            return self.tool_get_strategy(int(inp["course_id"]), bool(inp.get("regenerate", False)))
        if name == "tool_hole_plan":
            return self.tool_hole_plan(int(inp["course_id"]), int(inp["hole_number"]))
        if name == "tool_log_hole":
            hn = inp.get("hole_number")
            return self.tool_log_hole(int(inp["round_id"]), int(hn) if hn is not None else None, str(inp["narrative_text"]))
        if name == "tool_recent_rounds":
            return self.tool_recent_rounds(int(inp.get("limit", 5)))
        raise ValueError(f"Unknown tool: {name}")


# ---------------------------------------------------------------------------
# Heuristic caddie (no LLM)
# ---------------------------------------------------------------------------
_STRATEGY_RE = re.compile(
    r"\b(?:strategy|strategies|game[\s-]?plan|plan\b|how\s+(?:should|do|would|can|to)\s+i\s+play|how\s+to\s+play"
    r"|play\s+(?:this|the|that)\s+(?:hole|course)|what(?:'s|\s+is)\s+the\s+play|what\s+should\s+i\s+hit\s+(?:on|off))",
    re.I,
)
_DISTANCE_RE = re.compile(
    r"\b(?:distances?|how\s+far|carry|carries|yardages?|clubs?\b|what\s+club|which\s+club|gapping|my\s+numbers)",
    re.I,
)
_ERRORS_RE = re.compile(
    r"\b(?:errors?|mistakes?|leak(?:s|ing)?|costing|cost\s+me|weakness(?:es)?|where\s+am\s+i\s+losing|losing\s+strokes"
    r"|biggest\s+problem|what\s+should\s+i\s+(?:work|improve)|improve)\b",
    re.I,
)
_READINESS_RE = re.compile(
    r"\b(?:readiness|ready|enough\s+data|enough\s+rounds|how\s+many\s+rounds|how\s+much\s+data|confidence|know\s+my\s+game|learned)\b",
    re.I,
)
_ROUNDS_RE = re.compile(r"\b(?:rounds?|last\s+round|recent\s+rounds?|history|my\s+scores?)\b", re.I)
_NARRATIVE_RE = re.compile(
    r"\b(?:driver|wood|hybrid|iron|wedge|putts?|putted|putter|chip(?:ped)?|pitch(?:ed)?|bunker)\b|\b\d\s?(?:i|iron)\b"
    r"|\b[3579]\s?w\b|\b(?:pw|gw|sw|lw)\b",
    re.I,
)
_COURSE_STOPWORDS = {"golf", "club", "course", "the", "country", "links", "gc", "cc", "and", "of"}

HELP_TEXT = """I'm your caddie. Here is what I can do right now:
- "How should I play <course>?" or "plan for hole 7 at <course>" - your Monte Carlo game plan, hole by hole.
- "What are my club distances?" - your carry numbers and dispersion, learned from your shots.
- "What is costing me strokes?" - your top errors, in strokes per round, with advice.
- "Do you have enough data?" - how well the caddie knows your game yet.
- "Show my recent rounds."
- Or just tell me what you hit: "hole 5: driver in the rough, 8 iron to 20 feet, two putts" and I'll log it to your open round."""


class HeuristicCaddie(BaseCaddie):
    """Keyword-driven caddie. No network, no API key, still useful."""

    provider = "heuristic"

    def chat(self, message: str, course_id: int | None = None, hole_number: int | None = None) -> dict[str, Any]:
        self._persist("user", message)
        reply, actions = self._respond(message, course_id, hole_number)
        return self._finish(reply, actions)

    # ------------------------------------------------------------------
    def _respond(self, message: str, course_id: int | None, hole_number: int | None) -> tuple[str, list[dict[str, Any]]]:
        msg = (message or "").strip()
        low = msg.lower()
        actions: list[dict[str, Any]] = []
        stated_hole = _first_hole_number(msg)
        hole = stated_hole or hole_number

        if _STRATEGY_RE.search(low):
            return self._strategy_reply(low, course_id, hole, actions)
        if _DISTANCE_RE.search(low):
            if hole and (course_id is not None or self._match_course(low, course_id)):
                return self._strategy_reply(low, course_id, hole, actions)
            profile = self.tool_get_profile()
            actions.append({"type": "profile_read"})
            return self._render_clubs(profile), actions
        if _ERRORS_RE.search(low):
            profile = self.tool_get_profile()
            actions.append({"type": "profile_read"})
            return self._render_errors(profile), actions
        if _READINESS_RE.search(low):
            profile = self.tool_get_profile()
            actions.append({"type": "profile_read"})
            return self._render_readiness(profile), actions
        if _ROUNDS_RE.search(low) and not _NARRATIVE_RE.search(low):
            data = self.tool_recent_rounds(8)
            actions.append({"type": "rounds_read"})
            return self._render_rounds(data), actions
        if _NARRATIVE_RE.search(msg):
            return self._narrative_reply(msg, hole_number, stated_hole is not None or hole_number is not None, actions)
        return HELP_TEXT, actions

    # ------------------------------------------------------------------
    def _match_course(self, low: str, course_id: int | None) -> dict[str, Any] | None:
        courses = self.tool_list_courses()
        if course_id is not None:
            c = next((c for c in courses if c["id"] == course_id), None)
            if c:
                return c
        for c in courses:
            name = (c["name"] or "").lower().strip()
            if name and name in low:
                return c
        best, best_hits = None, 0
        for c in courses:
            words = [w for w in re.findall(r"[a-z0-9]+", (c["name"] or "").lower()) if len(w) > 2 and w not in _COURSE_STOPWORDS]
            hits = sum(1 for w in words if re.search(rf"\b{re.escape(w)}\b", low))
            if words and hits == len(words) and hits > best_hits:
                best, best_hits = c, hits
        if best:
            return best
        if len(courses) == 1:
            return courses[0]
        return None

    def _strategy_reply(self, low: str, course_id: int | None, hole: int | None, actions: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
        course = self._match_course(low, course_id)
        if course is None:
            courses = self.tool_list_courses()
            if not courses:
                return "There are no courses in the app yet. Add one (scorecard import is quickest) and ask me again.", actions
            names = ", ".join(f"{c['name']} (id {c['id']})" for c in courses)
            return f"Which course? I know: {names}. Say for example 'how should I play {courses[0]['name']}'.", actions
        had_plan = services.latest_plan(self.db, self.player_id, course["id"]) is not None
        try:
            plan = self._plan_for(course["id"])
        except ValueError as e:
            return f"I couldn't build a plan for {course['name']}: {e}", actions
        actions.append({"type": "strategy_loaded" if had_plan else "strategy_generated", "course_id": course["id"], "plan_id": plan.id})
        data = plan.data or {}
        if hole:
            hp = next((h for h in data.get("holes") or [] if h.get("hole") == hole), None)
            if hp is not None:
                return self._render_hole_plan(hp, data), actions
            return f"{course['name']} has no hole {hole} in the plan. " + self._render_course_plan(data), actions
        return self._render_course_plan(data), actions

    def _narrative_reply(self, msg: str, hole_number: int | None, hole_known: bool, actions: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
        rnd = self._open_round()
        parsed = self.parse_narrative(msg, hole_number=hole_number, round_=rnd)
        if not parsed.holes:
            return "I couldn't find any shots in that. " + HELP_TEXT, actions
        if rnd is not None and hole_known:
            saved = self._save_parsed(rnd, parsed)
            actions.append({"type": "hole_logged", "round_id": rnd.id, "holes": [s["hole_number"] for s in saved]})
            where = f"round #{rnd.id}" + (f" at {rnd.course.name}" if rnd.course else "")
            return f"Logged to {where}:\n" + self._render_parsed(parsed) + "\n" + self._coach_on(parsed), actions
        actions.append({"type": "narrative_preview", "holes": [h.hole_number for h in parsed.holes]})
        text = "Here is how I read that (not saved yet):\n" + self._render_parsed(parsed)
        if rnd is None:
            text += "\nYou have no open round to log into - create a round first, then tell me the hole again."
        else:
            text += f"\nTell me the hole number (e.g. 'hole {parsed.holes[0].hole_number}: ...') and I'll save it to round #{rnd.id}."
        return text, actions

    # ------------------------------------------------------------------
    # Renderers
    # ------------------------------------------------------------------
    @staticmethod
    def _render_clubs(profile: dict[str, Any]) -> str:
        clubs = profile.get("clubs") or {}
        if not clubs:
            return "No clubs in your bag yet - add clubs to your profile and I'll give you numbers."
        rows = sorted(clubs.items(), key=lambda kv: -(kv[1].get("carry_mean") or 0))
        lines = ["Your club distances (carry, yards):"]
        for code, d in rows:
            if (d.get("carry_mean") or 0) <= 0:
                continue
            src = d.get("source") or ("prior" if not d.get("n_samples") else "blended")
            lines.append(
                f"- {d.get('name', code)} ({code}): {_fmt_num(d.get('carry_mean'))} yds, +/-{_fmt_num(d.get('carry_sigma'))} long/short, "
                f"+/-{_fmt_num(d.get('lateral_sigma'))} left/right, n={d.get('n_samples', 0)} [{src}]"
            )
        r = profile.get("readiness") or {}
        lines.append("")
        lines.append(
            "Think of each club as a shotgun pattern, not a single pellet: the +/- numbers are the size of the pattern. "
            + ("Numbers marked 'prior' are handicap defaults - log shots and they become yours." if any((d.get("n_samples") or 0) == 0 for d in clubs.values()) else "These are built from your logged shots.")
        )
        if r.get("message"):
            lines.append(f"Readiness: {r.get('level')} - {r.get('message')}")
        return "\n".join(lines)

    @staticmethod
    def _render_errors(profile: dict[str, Any]) -> str:
        errors = profile.get("top_errors") or []
        if not errors:
            return ("No costly patterns show up yet - either you are playing clean or I need more logged rounds. "
                    "Log full rounds (every shot) and I'll rank what is leaking strokes.")
        lines = ["What is costing you strokes (per round):"]
        for i, e in enumerate(errors, 1):
            lines.append(f"{i}. {e.get('label')} - about {_fmt_num(e.get('strokes_per_round'), 1)} strokes/round. {e.get('detail', '')}".rstrip())
            if e.get("advice"):
                lines.append(f"   Advice: {e['advice']}")
        lines.append("")
        lines.append("Fix the top one first: bogey is fine, double is the enemy of your target score.")
        return "\n".join(lines)

    @staticmethod
    def _render_readiness(profile: dict[str, Any]) -> str:
        r = profile.get("readiness") or {}
        lines = [
            f"Readiness: {r.get('level', '?')} ({_fmt_pct(r.get('score', 0))}). {r.get('message', '')}".strip(),
            f"Rounds logged: {r.get('rounds_logged', 0)} of {r.get('rounds_needed', 10)} needed; shots logged: {profile.get('shots_logged', 0)}.",
        ]
        ss = profile.get("score_stats") or {}
        if ss.get("avg"):
            lines.append(f"Scoring: average {ss['avg']}, best {ss.get('best')}, last-5 average {ss.get('last5_avg')}, target {ss.get('target')}.")
        return "\n".join(lines)

    @staticmethod
    def _render_rounds(data: dict[str, Any]) -> str:
        rounds = data.get("rounds") or []
        if not rounds:
            return "No rounds logged yet. Create a round and tell me your shots hole by hole."
        lines = ["Your recent rounds:"]
        for r in rounds:
            status = "open" if not r.get("completed") else "done"
            lines.append(
                f"- #{r['id']} {r.get('date') or '?'} at {r.get('course') or 'unknown course'}: "
                f"{r.get('score') if r.get('score') is not None else '-'} ({r.get('holes_logged', 0)} holes logged, {status})"
            )
        if data.get("open_round_id"):
            lines.append(f"Open round: #{data['open_round_id']} - describe a hole and I'll log it there.")
        return "\n".join(lines)

    @staticmethod
    def _render_course_plan(data: dict[str, Any]) -> str:
        course = data.get("course") or {}
        summary = data.get("summary") or {}
        lines = [
            f"Game plan for {course.get('name', 'the course')} (par {course.get('par', '?')}, {course.get('yardage', '?')} yds):",
            f"{summary.get('headline', '')} Chance of breaking {data.get('target_score', '?')}: {_fmt_pct(data.get('p_break_target'))}.".strip(),
            "",
        ]
        for h in data.get("holes") or []:
            tee = h.get("tee") or {}
            lines.append(
                f"Hole {h.get('hole')} (par {h.get('par')}, {h.get('yards')} yds): {tee.get('club_name') or tee.get('club')} - {tee.get('aim')}. "
                f"Expected {_fmt_num(h.get('expected_strokes'), 2)} ({h.get('expected_vs_par', 0):+.2f}), double-or-worse {_fmt_pct(h.get('p_double_plus'))}. "
                f"{h.get('key_thought', '')}".rstrip()
            )
        if summary.get("hardest_holes"):
            lines.append("")
            lines.append("Hardest holes: " + ", ".join(f"{x['hole']} ({x['expected_vs_par']:+.2f})" for x in summary["hardest_holes"]))
        if summary.get("blowup_holes"):
            lines.append("Blow-up risk: " + ", ".join(f"{x['hole']} ({_fmt_pct(x['p_double_plus'])})" for x in summary["blowup_holes"]))
        for g in summary.get("game_plan") or []:
            lines.append(f"- {g}")
        lines.append("")
        lines.append("Ask 'plan for hole N' for the full picture on any hole.")
        return "\n".join(lines)

    @staticmethod
    def _render_hole_plan(h: dict[str, Any], data: dict[str, Any]) -> str:
        course = data.get("course") or {}
        tee = h.get("tee") or {}
        lines = [
            f"Hole {h.get('hole')} at {course.get('name', 'the course')} - par {h.get('par')}, {h.get('yards')} yds.",
            f"Tee shot: {tee.get('club_name') or tee.get('club')} - {tee.get('aim')} (carry about {tee.get('carry_yards')} yds, target {tee.get('target_yards')} yds out).",
            f"Key thought: {h.get('key_thought', '')}",
            f"Expected {_fmt_num(h.get('expected_strokes'), 2)} strokes ({h.get('expected_vs_par', 0):+.2f}); double-or-worse {_fmt_pct(h.get('p_double_plus'))}; trouble off the tee {_fmt_pct(tee.get('trouble_probability'))}.",
        ]
        if tee.get("avoid"):
            lines.append(f"The miss to avoid: {tee['avoid'].get('feature')} ({_fmt_pct(tee['avoid'].get('probability'))} under this plan).")
        if h.get("layup"):
            l = h["layup"]
            lines.append(f"Second shot: {l.get('kind')} with {l.get('club')} ({l.get('carry_yards')} yds), leaving about {l.get('leaves_yards')} yds.")
        if h.get("approach"):
            a = h["approach"]
            lines.append(f"Approach: from about {a.get('from_yards')} yds with {a.get('club')} - aim at the {a.get('aim')}. GIR chance {_fmt_pct(a.get('gir_probability'))}.")
        if h.get("rationale"):
            lines.append(f"Why: {h['rationale']}")
        alts = h.get("alternatives") or []
        if alts:
            lines.append("Alternatives:")
            for a in alts:
                lines.append(
                    f"- {a.get('club')} ({a.get('label')}): expected {_fmt_num(a.get('expected_strokes'), 2)}, double-or-worse {_fmt_pct(a.get('p_double_plus'))}, "
                    f"costs {_fmt_num(a.get('objective_delta'), 2)} strokes vs the plan"
                )
        lines.append(f"Plan confidence: {_fmt_pct(tee.get('confidence'))} (rises as you log more shots).")
        return "\n".join(lines)

    @staticmethod
    def _render_parsed(parsed: NarrativeResponse) -> str:
        lines = []
        for h in parsed.holes:
            bits = [f"score {h.score}"]
            if h.putts is not None:
                bits.append(f"{h.putts} putt{'s' if h.putts != 1 else ''}")
            if h.fairway_hit is not None:
                bits.append("fairway hit" if h.fairway_hit else "fairway missed")
            bits.append("GIR" if h.gir else "no GIR")
            if h.penalties:
                bits.append(f"{h.penalties} penalty")
            lines.append(f"Hole {h.hole_number} (par {h.par}): " + ", ".join(bits))
            for s in h.shots:
                end = "holed" if s.holed else (
                    f"{s.end_distance_yards * 3:.0f} ft" if s.lie_end in ("green", "fringe") else f"{s.end_distance_yards:.0f} yds"
                )
                tag = f" [{s.outcome_tag}]" if s.outcome_tag else ""
                pen = f" (+{s.penalty_strokes} penalty)" if s.penalty_strokes else ""
                lines.append(f"  {s.sequence}. {s.club_code or '?'} {s.shot_type} from {s.lie_start} {s.start_distance_yards:.0f} yds -> {s.lie_end}, {end}{tag}{pen}")
        if parsed.warnings:
            lines.append("Assumptions: " + " ".join(parsed.warnings))
        return "\n".join(lines)

    @staticmethod
    def _coach_on(parsed: NarrativeResponse) -> str:
        notes = []
        for h in parsed.holes:
            if h.penalties:
                notes.append(f"Hole {h.hole_number}: the penalty did the damage - the plan will aim you away from that trouble even if it means a longer approach.")
            elif h.putts and h.putts >= 3:
                notes.append(f"Hole {h.hole_number}: a three-putt. From long range the goal is a three-foot circle, not the hole.")
            elif h.score - h.par >= 2:
                notes.append(f"Hole {h.hole_number}: a double. Bogey is fine, double is the enemy of your target - take the safer line next time.")
            elif h.score <= h.par:
                notes.append(f"Hole {h.hole_number}: par or better - that is exactly how the plan wants you to play.")
        return " ".join(notes) if notes else "Keep them coming - every logged shot sharpens your numbers."


# ---------------------------------------------------------------------------
# Claude caddie
# ---------------------------------------------------------------------------
class ClaudeCaddie(BaseCaddie):
    """Anthropic-powered caddie with a manual tool-use loop."""

    provider = "claude"

    def __init__(self, db: Session, player_id: int, client: Any = None):
        super().__init__(db, player_id)
        if client is None:
            if anthropic is None:
                raise RuntimeError("The anthropic SDK is not installed")
            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.client = client
        self.model = settings.anthropic_model
        self.system_prompt = self._build_system_prompt()

    # ------------------------------------------------------------------
    def _build_system_prompt(self) -> str:
        # Stable text first so the cached prefix survives; the per-player snapshot goes last.
        parts = [SYSTEM_PROMPT_TEXT]
        try:
            profile = self.tool_get_profile()
            compact = {
                "player": profile.get("player"), "handicap": profile.get("handicap"),
                "target_score": profile.get("target_score"), "rounds_logged": profile.get("rounds_logged"),
                "readiness": profile.get("readiness"),
                "clubs": {code: {"carry": c.get("carry_mean"), "sigma": c.get("carry_sigma"), "lateral": c.get("lateral_sigma"), "n": c.get("n_samples")}
                          for code, c in (profile.get("clubs") or {}).items()},
                "top_errors": [{"label": e.get("label"), "strokes_per_round": e.get("strokes_per_round")} for e in profile.get("top_errors") or []],
                "score_stats": {k: v for k, v in (profile.get("score_stats") or {}).items() if k != "trend"},
            }
            parts.append("## Player snapshot (from tool_get_profile when this conversation started; call it again for detail)\n"
                         + json.dumps(compact, sort_keys=True, default=str))
        except Exception as e:  # pragma: no cover - defensive: a broken profile must not break chat
            log.warning("caddie: could not build profile snapshot: %s", e)
        try:
            courses = self.tool_list_courses()
            parts.append("## Courses in the app\n" + json.dumps(courses, sort_keys=True, default=str))
        except Exception as e:  # pragma: no cover
            log.warning("caddie: could not list courses: %s", e)
        return "\n\n".join(parts)

    def _context_messages(self) -> list[dict[str, Any]]:
        msgs: list[dict[str, Any]] = []
        for m in self._recent_messages(HISTORY_CONTEXT):
            if m.role not in ("user", "assistant"):
                continue
            if not msgs and m.role != "user":
                continue  # the first message must be from the user
            msgs.append({"role": m.role, "content": m.content})
        return msgs

    # ------------------------------------------------------------------
    def chat(self, message: str, course_id: int | None = None, hole_number: int | None = None) -> dict[str, Any]:
        prior = self._context_messages()
        self._persist("user", message)
        content = message
        if course_id is not None or hole_number is not None:
            content += f"\n\n[App context: course_id={course_id}, hole_number={hole_number}]"
        messages = prior + [{"role": "user", "content": content}]
        actions: list[dict[str, Any]] = []
        try:
            reply = self._run_tool_loop(messages, actions)
        except _RATE_LIMIT_ERRORS as e:
            reply = self._fallback_reply(message, course_id, hole_number, actions, "rate limited", e)
        except _STATUS_ERRORS as e:
            reply = self._fallback_reply(message, course_id, hole_number, actions, f"HTTP {getattr(e, 'status_code', '?')}", e)
        except _CONNECTION_ERRORS as e:
            reply = self._fallback_reply(message, course_id, hole_number, actions, "connection error", e)
        except _ANY_API_ERRORS as e:
            reply = self._fallback_reply(message, course_id, hole_number, actions, type(e).__name__, e)
        return self._finish(reply, actions)

    def _fallback_reply(self, message: str, course_id: int | None, hole_number: int | None, actions: list[dict[str, Any]], reason: str, exc: BaseException) -> str:
        log.warning("caddie: Claude unavailable (%s): %s", reason, exc)
        actions.append({"type": "fallback", "reason": reason})
        reply, extra = HeuristicCaddie(self.db, self.player_id)._respond(message, course_id, hole_number)
        actions.extend(extra)
        return f"(Claude unavailable: {reason} - answering with the built-in caddie.)\n\n{reply}"

    def _run_tool_loop(self, messages: list[dict[str, Any]], actions: list[dict[str, Any]]) -> str:
        last_text = ""
        for _ in range(MAX_TOOL_ITERATIONS):
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=4096,
                system=self.system_prompt,
                messages=messages,
                tools=TOOLS,
                betas=FALLBACK_BETAS,
                fallbacks="default",
            )
            stop = getattr(response, "stop_reason", None)
            if stop == "refusal":
                return REFUSAL_TEXT
            text = _text_of(getattr(response, "content", None))
            if stop != "tool_use":
                return text or "(The caddie had nothing to add.)"
            if text:
                last_text = text
            messages.append({"role": "assistant", "content": response.content})
            results: list[dict[str, Any]] = []
            for block in response.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                name = getattr(block, "name", "")
                inp = getattr(block, "input", None) or {}
                if not isinstance(inp, dict):
                    try:
                        inp = json.loads(inp)
                    except (TypeError, ValueError):
                        inp = {}
                try:
                    result = self._dispatch_tool(name, inp)
                    results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result, default=str)})
                    actions.append({"type": "tool_call", "name": name, "input": inp, "ok": True})
                except Exception as e:  # tool failures go back to the model, never to the user as a crash
                    log.warning("caddie tool %s failed: %s", name, e)
                    results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps({"error": str(e)}), "is_error": True})
                    actions.append({"type": "tool_call", "name": name, "input": inp, "ok": False, "error": str(e)})
            messages.append({"role": "user", "content": results})
        tail = "(I stopped after several tool calls - ask me again for the rest.)"
        return f"{last_text}\n\n{tail}".strip() if last_text else tail

    # ------------------------------------------------------------------
    def _parser_prompt(self, text: str, hole_number: int | None, round_: Any) -> str:
        player = services.get_player(self.db, self.player_id)
        codes = [c.code for c in (player.clubs if player else []) if getattr(c, "active", True)]
        lines = [
            "Convert the golfer's description below into structured holes and shots.",
            "",
            "Rules:",
            f"- shot_type must be one of: {', '.join(SHOT_TYPES)}.",
            f"- lie_start / lie_end must be one of: {', '.join(LIES)}.",
            f"- outcome_tag must be one of: {', '.join(OUTCOME_TAGS)} - or null.",
            f"- club_code must be one of the player's clubs: {', '.join(codes) if codes else 'D, 3w, 3h, 4i-9i, PW, GW, SW, LW, P'} (P = putter); null if not stated.",
            "- Distances are yards. Golfers describe putts and green-side distances in FEET: divide feet by 3 for start/end distances on and around the green.",
            "- Number shots 1..n in order. The first shot starts on the tee at the hole's length. Each shot's start_distance_yards equals the previous shot's end_distance_yards.",
            "- The last shot has holed = true and end_distance_yards = 0.",
            "- Water / lateral hazard = lie_end 'penalty' with penalty_strokes 1 (next shot from the drop, usually a rough lie). Out of bounds or lost ball = lie_end 'ob', penalty_strokes 1, next shot from the same spot.",
            "- score = number of shots + total penalty strokes. putts = number of shot_type 'putt' shots. gir = on the green within par-2 strokes (including penalties). fairway_hit = the tee shot finished in the fairway (null on par 3s).",
            "- If a distance or lie is not stated, make a sensible estimate and list it in warnings.",
        ]
        course = getattr(round_, "course", None)
        if course is not None and getattr(course, "holes", None):
            lines.append("")
            lines.append(f"Course: {course.name}. Holes (number: par, yards):")
            lines.append("; ".join(f"{h.number}: par {h.par}, {h.yards} yds" for h in sorted(course.holes, key=lambda h: h.number)))
        elif round_ is not None:
            lines.append("")
            lines.append("No course data: assume 400 yards for a par 4, 170 for a par 3, 520 for a par 5.")
        if hole_number is not None:
            lines.append("")
            lines.append(f"If the text does not say which hole, it is hole {hole_number}.")
        lines.append("")
        lines.append("Golfer's description:")
        lines.append(text)
        return "\n".join(lines)

    def parse_narrative(self, text: str, hole_number: int | None = None, round_: Any = None) -> NarrativeResponse:
        prompt = self._parser_prompt(text, hole_number, round_)
        try:
            response = self.client.messages.parse(
                model=self.model,
                max_tokens=4096,
                system=PARSER_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                output_format=ParsedNarrative,
            )
            parsed = getattr(response, "parsed_output", None)
        except _RATE_LIMIT_ERRORS as e:
            return self._parse_fallback(text, hole_number, round_, "rate limited", e)
        except _STATUS_ERRORS as e:
            return self._parse_fallback(text, hole_number, round_, f"HTTP {getattr(e, 'status_code', '?')}", e)
        except _CONNECTION_ERRORS as e:
            return self._parse_fallback(text, hole_number, round_, "connection error", e)
        except _ANY_API_ERRORS as e:
            return self._parse_fallback(text, hole_number, round_, type(e).__name__, e)
        if parsed is None:
            return self._parse_fallback(text, hole_number, round_, "no structured output returned", None)
        return self._convert_parsed(parsed)

    def _parse_fallback(self, text: str, hole_number: int | None, round_: Any, reason: str, exc: BaseException | None) -> NarrativeResponse:
        log.warning("caddie: Claude parser unavailable (%s): %s", reason, exc)
        out = super().parse_narrative(text, hole_number=hole_number, round_=round_)
        out.warnings.insert(0, f"Claude unavailable: {reason} - used the built-in parser.")
        return out

    @staticmethod
    def _convert_parsed(parsed: ParsedNarrative) -> NarrativeResponse:
        warnings = list(parsed.warnings or [])
        holes: list[NarrativeParsedHole] = []
        for h in parsed.holes:
            shots: list[ShotCreate] = []
            for i, s in enumerate(sorted(h.shots, key=lambda x: x.sequence), 1):
                stype = (s.shot_type or "full").lower().strip()
                if stype not in SHOT_TYPES:
                    warnings.append(f"Hole {h.hole_number}, shot {i}: unknown shot type '{s.shot_type}' - used 'full'.")
                    stype = "full"
                lie_start = (s.lie_start or "fairway").lower().strip()
                if lie_start not in LIES:
                    warnings.append(f"Hole {h.hole_number}, shot {i}: unknown lie '{s.lie_start}' - used 'fairway'.")
                    lie_start = "fairway"
                lie_end = (s.lie_end or "fairway").lower().strip()
                if lie_end not in LIES:
                    warnings.append(f"Hole {h.hole_number}, shot {i}: unknown lie '{s.lie_end}' - used 'fairway'.")
                    lie_end = "fairway"
                tag = (s.outcome_tag or "").lower().strip() or None
                if tag is not None and tag not in OUTCOME_TAGS:
                    warnings.append(f"Hole {h.hole_number}, shot {i}: unknown outcome '{s.outcome_tag}' - dropped.")
                    tag = None
                shots.append(ShotCreate(
                    sequence=i, club_code=s.club_code or None, shot_type=stype, lie_start=lie_start,
                    start_distance_yards=max(float(s.start_distance_yards or 0.0), 0.0), lie_end=lie_end,
                    end_distance_yards=max(float(s.end_distance_yards or 0.0), 0.0),
                    lateral_miss_yards=s.lateral_miss_yards, distance_miss_yards=s.distance_miss_yards,
                    outcome_tag=tag, penalty_strokes=max(int(s.penalty_strokes or 0), 0), holed=bool(s.holed),
                ))
            if shots:
                shots[-1].holed = True
                shots[-1].end_distance_yards = 0.0
            penalties = sum(s.penalty_strokes for s in shots) if shots else max(int(h.penalties or 0), 0)
            score = (len(shots) + penalties) if shots else int(h.score)
            putts = sum(1 for s in shots if s.shot_type == "putt") if shots else h.putts
            holes.append(NarrativeParsedHole(
                hole_number=h.hole_number, par=h.par, score=score, putts=putts,
                fairway_hit=h.fairway_hit if h.par > 3 else None, gir=h.gir, penalties=penalties, shots=shots,
            ))
        return NarrativeResponse(holes=holes, parser="claude", warnings=warnings)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def get_caddie(db: Session, player_id: int, client: Any = None) -> BaseCaddie:
    """Return ClaudeCaddie when an Anthropic client is given or settings.anthropic_api_key is set, else HeuristicCaddie."""
    if client is not None:
        return ClaudeCaddie(db, player_id, client=client)
    if settings.anthropic_api_key and anthropic is not None:
        return ClaudeCaddie(db, player_id)
    return HeuristicCaddie(db, player_id)


__all__ = [
    "BaseCaddie", "ClaudeCaddie", "HeuristicCaddie", "HeuristicNarrativeParser",
    "ParsedNarrative", "ParsedHole", "ParsedShot", "TOOLS", "SYSTEM_PROMPT_TEXT", "PARSER_SYSTEM", "get_caddie",
]
