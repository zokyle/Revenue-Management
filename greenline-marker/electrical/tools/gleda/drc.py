"""Zone fill + KiCad DRC runner + report parser.

KiCad's own DRC is the judge of the generated board.  KiCad 7 has no
``kicad-cli pcb drc``, so the DRC engine is driven through
``pcbnew.WriteDRCReport`` and its text report is parsed here.

Typical use::

    from gleda import drc
    result = drc.run_drc("out/demo.kicad_pcb")       # fills zones, saves, runs DRC
    print(result.summary())
    drc.assert_clean(result)                          # raises DrcError unless clean

Honesty rules implemented here

* ``run_drc`` refuses to count a run as valid when the project file has
  downgraded one of the core checks (clearance, track width, annular ring,
  hole size, hole-to-hole, edge clearance, shorts, unconnected, ...):
  :func:`check_project_severities` records the problem in
  ``DrcResult.tampered`` and :func:`assert_clean` fails.
* :func:`assert_clean` fails on every violation of severity "error" and on any
  unconnected item.  The only violations it ignores are those whose type is in
  the explicit allow-list :data:`COSMETIC_CHECKS` (silkscreen / text
  cosmetics), and they are still listed in the result.

pcbnew gotchas handled here

* zones can only be filled on a board that was loaded from disk (filling a
  freshly built in-memory board segfaults), so the fill always happens on the
  re-loaded file;
* by default the whole job runs in a child process (``isolate=True``), so a
  pcbnew crash cannot take the calling tool down and is reported as an error.

Coordinates in the parsed result are given both as KiCad page millimetres
(``kicad_x``/``kicad_y``, what the KiCad GUI shows) and as design millimetres
(``x``/``y``, +y up, origin at the board centre).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from . import coords
from .board import CORE_ERROR_CHECKS, SEVERITY_OVERRIDES

#: Cosmetic checks that never fail :func:`assert_clean`, with the reason.
COSMETIC_CHECKS: Dict[str, str] = {
    "silk_overlap": "silkscreen items overlapping each other",
    "silk_over_copper": "silkscreen clipped by solder mask openings",
    "silk_edge_clearance": "silkscreen close to the board edge",
    "text_height": "text smaller than the fab's legibility limit",
    "text_thickness": "text stroke thinner than the fab's legibility limit",
    "lib_footprint_issues": "footprint library not configured (headless run)",
    "lib_footprint_mismatch": "footprint differs from library copy",
}


class DrcError(Exception):
    """The board did not pass DRC (or DRC could not be run)."""

    def __init__(self, message: str, result: Optional["DrcResult"] = None):
        super().__init__(message)
        self.result = result


@dataclass
class DrcItem:
    """One object named by a violation."""
    kicad_x: float
    kicad_y: float
    x: float
    y: float
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return {"x": self.x, "y": self.y, "kicad_x": self.kicad_x, "kicad_y": self.kicad_y,
                "description": self.description}


@dataclass
class DrcViolation:
    """One DRC marker: ``type`` is KiCad's check name, e.g. ``clearance``."""
    type: str
    severity: str
    description: str
    rule: str = ""
    items: List[DrcItem] = field(default_factory=list)
    section: str = "violations"       # violations | unconnected | footprints

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.type, "severity": self.severity,
                "description": self.description, "rule": self.rule,
                "section": self.section, "items": [i.to_dict() for i in self.items]}

    def __str__(self) -> str:
        where = "; ".join("(%.3f, %.3f) %s" % (i.x, i.y, i.description) for i in self.items)
        return "[%s] %s: %s -- %s" % (self.severity, self.type, self.description, where)


@dataclass
class DrcResult:
    """Parsed DRC outcome."""
    board: str = ""
    violations: List[DrcViolation] = field(default_factory=list)
    unconnected: List[DrcViolation] = field(default_factory=list)
    footprint_errors: List[DrcViolation] = field(default_factory=list)
    report_path: Optional[str] = None
    zones_filled: Optional[int] = None
    #: core checks whose severity was downgraded in the project file
    tampered: List[str] = field(default_factory=list)
    #: counts declared in the report headers (cross-checked against the parse)
    declared: Dict[str, int] = field(default_factory=dict)
    #: names of the custom rules in the ``.kicad_dru`` next to the board that
    #: KiCad applied in addition to the project rules (empty: no rules file)
    custom_rules: List[str] = field(default_factory=list)

    # -- aggregates --------------------------------------------------------
    def _by_type(self, severity: str) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for v in self.violations + self.footprint_errors:
            if v.severity == severity:
                out[v.type] = out.get(v.type, 0) + 1
        return dict(sorted(out.items()))

    @property
    def errors_by_type(self) -> Dict[str, int]:
        return self._by_type("error")

    @property
    def warnings_by_type(self) -> Dict[str, int]:
        return self._by_type("warning")

    @property
    def error_count(self) -> int:
        return sum(self.errors_by_type.values())

    @property
    def warning_count(self) -> int:
        return sum(self.warnings_by_type.values())

    @property
    def unconnected_count(self) -> int:
        return len(self.unconnected)

    def errors(self, allow: Optional[Iterable[str]] = None) -> List[DrcViolation]:
        """Error-severity violations whose type is not in ``allow``."""
        allowed = set(COSMETIC_CHECKS if allow is None else allow)
        return [v for v in self.violations + self.footprint_errors
                if v.severity == "error" and v.type not in allowed]

    def is_clean(self, allow: Optional[Iterable[str]] = None,
                 allow_unconnected: bool = False) -> bool:
        if self.tampered:
            return False
        if self.errors(allow):
            return False
        return allow_unconnected or not self.unconnected

    def to_dict(self) -> Dict[str, Any]:
        return {
            "board": os.path.basename(self.board),      # no absolute paths: diff-clean
            "errors": self.errors_by_type,
            "warnings": self.warnings_by_type,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "unconnected": self.unconnected_count,
            "footprint_errors": len(self.footprint_errors),
            "zones_filled": self.zones_filled,
            "tampered_checks": list(self.tampered),
            "custom_rules": list(self.custom_rules),
            "cosmetic_allow_list": dict(COSMETIC_CHECKS),
            "severity_overrides": {k: {"severity": v[0], "reason": v[1]}
                                   for k, v in SEVERITY_OVERRIDES.items()},
            "items": [v.to_dict() for v in
                      self.violations + self.unconnected + self.footprint_errors],
        }

    def summary(self) -> str:
        return "DRC %s: %d error(s) %s, %d warning(s) %s, %d unconnected%s" % (
            os.path.basename(self.board), self.error_count, self.errors_by_type or "",
            self.warning_count, self.warnings_by_type or "", self.unconnected_count,
            ", TAMPERED severities: %s" % self.tampered if self.tampered else "")

    def write_json(self, path: str) -> str:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2, sort_keys=True)
            fh.write("\n")
        return path


# --------------------------------------------------------------------------
# report parser
# --------------------------------------------------------------------------

_HEAD_RE = re.compile(r"^\[(?P<type>[A-Za-z0-9_]+)\]:\s*(?P<desc>.*)$")
_RULE_RE = re.compile(r"^\s+(?P<rule>.*?);\s*Severity:\s*(?P<sev>\w+)\s*$")
_ITEM_RE = re.compile(r"^\s+@\(\s*(?P<x>-?[0-9.]+)\s*mm\s*,\s*(?P<y>-?[0-9.]+)\s*mm\s*\):\s*"
                      r"(?P<desc>.*)$")
_SECTION_RE = re.compile(r"^\*\* Found (?P<n>\d+) (?P<what>.+?) \*\*\s*$")


def parse_report(text: str, origin: Tuple[float, float] = coords.KICAD_ORIGIN_MM
                 ) -> DrcResult:
    """Parse the text written by ``pcbnew.WriteDRCReport`` (millimetre units).

    ``origin`` is the position of the design origin on the KiCad page (used
    to convert marker positions to design coordinates).  Raises ValueError if
    the text is not a complete DRC report or if the number of parsed entries
    differs from the counts the report declares.
    """
    result = DrcResult()
    section = None
    current: Optional[DrcViolation] = None
    saw_end = False
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        if line.startswith("** Drc report for"):
            result.board = line[len("** Drc report for"):].strip(" *")
            continue
        m = _SECTION_RE.match(line)
        if m:
            what = m.group("what").lower()
            if "unconnected" in what:
                section = "unconnected"
            elif "footprint" in what:
                section = "footprints"
            else:
                section = "violations"
            result.declared[section] = int(m.group("n"))
            current = None
            continue
        if line.startswith("** End of Report"):
            saw_end = True
            current = None
            continue
        if line.startswith("**") or not line.strip():
            continue
        m = _HEAD_RE.match(line)
        if m and section:
            current = DrcViolation(m.group("type"), "error", m.group("desc").strip(),
                                   section=section)
            {"violations": result.violations, "unconnected": result.unconnected,
             "footprints": result.footprint_errors}[section].append(current)
            continue
        if current is None:
            continue
        m = _ITEM_RE.match(line)
        if m:
            kx, ky = float(m.group("x")), float(m.group("y"))
            x, y = coords.from_kicad_mm(kx, ky, origin)
            current.items.append(DrcItem(kx, ky, round(x, 4), round(y, 4),
                                         m.group("desc").strip()))
            continue
        m = _RULE_RE.match(line)
        if m:
            rule = m.group("rule").strip()
            current.rule = rule[len("Rule:"):].strip() if rule.startswith("Rule:") else rule
            current.severity = m.group("sev").strip().lower()
            continue
    if not saw_end or "violations" not in result.declared:
        raise ValueError("not a complete KiCad DRC report")
    parsed = {"violations": len(result.violations), "unconnected": len(result.unconnected),
              "footprints": len(result.footprint_errors)}
    for key, n in result.declared.items():
        if parsed[key] != n:
            raise ValueError("DRC report declares %d %s entries but %d were parsed"
                             % (n, key, parsed[key]))
    return result


# --------------------------------------------------------------------------
# project severity guard
# --------------------------------------------------------------------------

def check_project_severities(pcb_path: str) -> List[str]:
    """Core checks that are NOT at severity "error" in the board's project.

    A missing project file is itself a problem (KiCad would then use built-in
    default rules instead of the design's rule set)."""
    pro = os.path.splitext(pcb_path)[0] + ".kicad_pro"
    if not os.path.exists(pro):
        return ["<no project file: %s>" % os.path.basename(pro)]
    try:
        with open(pro, encoding="utf-8") as fh:
            data = json.load(fh)
        sev = data["board"]["design_settings"]["rule_severities"]
    except (OSError, ValueError, KeyError, TypeError):
        return ["<unreadable project file: %s>" % os.path.basename(pro)]
    return [c for c in CORE_ERROR_CHECKS if sev.get(c, "error") != "error"]


def custom_rule_names(pcb_path: str) -> List[str]:
    """Names of the rules in the ``.kicad_dru`` file next to a board (KiCad
    loads that file automatically when it runs DRC).  Empty if there is none."""
    dru = os.path.splitext(pcb_path)[0] + ".kicad_dru"
    if not os.path.exists(dru):
        return []
    with open(dru, encoding="utf-8") as fh:
        text = fh.read()
    return re.findall(r'^\(rule\s+"([^"]*)"', text, flags=re.M)


# --------------------------------------------------------------------------
# running
# --------------------------------------------------------------------------

def fill_zones(pcb_path: str, save: bool = True, board=None) -> int:
    """Fill all copper zones of a board FILE (in this process).

    The board is loaded from disk first (pcbnew crashes when filling a board
    that only exists in memory).  Returns the number of copper zones.  With
    ``save`` the filled board is written back.  A pre-loaded ``board`` (from
    :func:`gleda.board.load_board`) may be passed to avoid a second load."""
    import pcbnew
    from .board import load_board, save_board
    if board is None:
        board = load_board(pcb_path)
    zones = board.Zones()
    count = sum(1 for z in zones if not z.GetIsRuleArea())
    if count:
        filler = pcbnew.ZONE_FILLER(board)
        if not filler.Fill(zones):
            raise DrcError("zone fill failed for %s" % pcb_path)
    if save:
        save_board(board, pcb_path)
    return count


def _run_inprocess(pcb_path: str, report_path: str, fill: bool, save: bool,
                   all_track_errors: bool) -> Dict[str, Any]:
    import pcbnew
    from .board import load_board, save_board
    board = load_board(pcb_path)
    zones_filled = None
    if fill:
        zones_filled = fill_zones(pcb_path, save=False, board=board)
        if save:
            save_board(board, pcb_path)
    board.BuildConnectivity()
    ok = pcbnew.WriteDRCReport(board, report_path, pcbnew.EDA_UNITS_MILLIMETRES,
                               bool(all_track_errors))
    if not ok or not os.path.exists(report_path):
        raise DrcError("pcbnew.WriteDRCReport failed for %s" % pcb_path)
    aux = board.GetDesignSettings().GetAuxOrigin()
    return {"zones_filled": zones_filled,
            "origin": [coords.nm_to_mm(aux.x), coords.nm_to_mm(aux.y)]}


def run_drc(pcb_path: str, report_path: Optional[str] = None,
            json_path: Optional[str] = None, *, fill: bool = True, save: bool = True,
            isolate: bool = True, all_track_errors: bool = True,
            timeout: float = 1800.0) -> DrcResult:
    """Fill zones, run KiCad's DRC and return the parsed :class:`DrcResult`.

    ``report_path``  where KiCad's text report goes (default ``<board>.drc.rpt``)
    ``json_path``    optional path for the JSON form of the result
    ``fill``         refill all zones first (needed after any copper change)
    ``save``         write the filled board back to ``pcb_path``
    ``isolate``      run pcbnew in a child process (recommended)

    This function never raises for DRC *violations* - inspect the result or
    call :func:`assert_clean`.  It raises :class:`DrcError` when DRC could not
    be run at all (crash, unreadable board, malformed report).
    """
    pcb_path = os.path.abspath(pcb_path)
    if not os.path.exists(pcb_path):
        raise DrcError("board file not found: %s" % pcb_path)
    if report_path is None:
        report_path = os.path.splitext(pcb_path)[0] + ".drc.rpt"
    report_path = os.path.abspath(report_path)
    if os.path.exists(report_path):
        os.remove(report_path)
    if isolate:
        meta = _run_isolated(pcb_path, report_path, fill, save, all_track_errors, timeout)
    else:
        meta = _run_inprocess(pcb_path, report_path, fill, save, all_track_errors)
    with open(report_path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    origin = tuple(meta.get("origin") or coords.KICAD_ORIGIN_MM)
    if origin == (0.0, 0.0):
        origin = coords.KICAD_ORIGIN_MM
    try:
        result = parse_report(text, origin)          # type: ignore[arg-type]
    except ValueError as exc:
        raise DrcError("cannot parse DRC report %s: %s" % (report_path, exc))
    result.board = pcb_path
    result.report_path = report_path
    result.zones_filled = meta.get("zones_filled")
    result.tampered = check_project_severities(pcb_path)
    result.custom_rules = custom_rule_names(pcb_path)
    _strip_report_timestamp(report_path, text)
    if json_path:
        result.write_json(json_path)
    return result


def _strip_report_timestamp(report_path: str, text: str) -> None:
    """Make the stored report reproducible: drop the 'Created on <now>' line
    and reduce the absolute board path in the title to the file name."""
    lines = []
    for line in text.splitlines():
        if line.startswith("** Created on"):
            continue
        if line.startswith("** Drc report for "):
            name = os.path.basename(line[len("** Drc report for "):].rstrip(" *"))
            line = "** Drc report for %s **" % name
        lines.append(line)
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def _run_isolated(pcb_path: str, report_path: str, fill: bool, save: bool,
                  all_track_errors: bool, timeout: float) -> Dict[str, Any]:
    tools_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ)
    env["PYTHONPATH"] = tools_dir + os.pathsep + env.get("PYTHONPATH", "")
    cmd = [sys.executable, "-m", "gleda.drc", "--worker", pcb_path, report_path,
           "1" if fill else "0", "1" if save else "0", "1" if all_track_errors else "0"]
    try:
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise DrcError("DRC worker timed out after %.0f s for %s" % (timeout, pcb_path))
    meta = None
    for line in proc.stdout.splitlines():
        if line.startswith("GLEDA_DRC_META "):
            meta = json.loads(line[len("GLEDA_DRC_META "):])
    if proc.returncode != 0 or meta is None:
        raise DrcError("DRC worker failed for %s (exit code %s)\n%s\n%s" % (
            pcb_path, proc.returncode, proc.stdout[-2000:], proc.stderr[-2000:]))
    return meta


def assert_clean(result: DrcResult, *, allow: Optional[Iterable[str]] = None,
                 allow_unconnected: bool = False) -> DrcResult:
    """Raise :class:`DrcError` unless the board is clean.

    Clean means: no violation of severity "error" (other than types in the
    cosmetic allow-list ``allow``, default :data:`COSMETIC_CHECKS`), no
    unconnected items (unless ``allow_unconnected``, for boards that are not
    routed yet) and no downgraded core check in the project file.
    """
    problems: List[str] = []
    if result.tampered:
        problems.append("core DRC checks are not at severity 'error' in the project "
                        "file: %s" % ", ".join(result.tampered))
    errors = result.errors(allow)
    if errors:
        counts: Dict[str, int] = {}
        for v in errors:
            counts[v.type] = counts.get(v.type, 0) + 1
        problems.append("%d DRC error(s): %s" % (len(errors), dict(sorted(counts.items()))))
        for v in errors[:20]:
            problems.append("  " + str(v))
        if len(errors) > 20:
            problems.append("  ... %d more" % (len(errors) - 20))
    if result.unconnected and not allow_unconnected:
        problems.append("%d unconnected item(s)" % len(result.unconnected))
        for v in result.unconnected[:20]:
            problems.append("  " + str(v))
        if len(result.unconnected) > 20:
            problems.append("  ... %d more" % (len(result.unconnected) - 20))
    if problems:
        raise DrcError("DRC not clean for %s\n%s" % (result.board, "\n".join(problems)),
                       result)
    return result


def _main(argv: Sequence[str]) -> int:
    if len(argv) >= 2 and argv[0] == "--worker":
        pcb, report = argv[1], argv[2]
        fill, save, all_tracks = (a == "1" for a in argv[3:6])
        meta = _run_inprocess(pcb, report, fill, save, all_tracks)
        sys.stdout.write("GLEDA_DRC_META %s\n" % json.dumps(meta))
        sys.stdout.flush()
        return 0
    import argparse
    ap = argparse.ArgumentParser(
        prog="python3 -m gleda.drc",
        description="Fill zones and run KiCad DRC on a board; exit 1 unless clean.")
    ap.add_argument("board")
    ap.add_argument("--report", help="text report path (default <board>.drc.rpt)")
    ap.add_argument("--json", help="write the parsed result as JSON")
    ap.add_argument("--no-fill", action="store_true", help="do not refill zones")
    ap.add_argument("--allow-unconnected", action="store_true",
                    help="do not fail on unconnected items (unrouted boards)")
    args = ap.parse_args(list(argv))
    try:
        result = run_drc(args.board, args.report, args.json, fill=not args.no_fill)
        print(result.summary())
        assert_clean(result, allow_unconnected=args.allow_unconnected)
    except DrcError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


__all__ = ["DrcItem", "DrcViolation", "DrcResult", "DrcError", "COSMETIC_CHECKS",
           "parse_report", "fill_zones", "run_drc", "assert_clean",
           "check_project_severities", "custom_rule_names"]


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
