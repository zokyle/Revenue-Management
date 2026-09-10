"""Building :class:`golf.models.course.Course` rows from external descriptions.

Three importers live here, in increasing order of richness:

* :func:`build_course_from_scorecard` -- par + yardage per hole, generic
  geometry chosen from the par.
* :func:`import_course_from_json` -- the full hole/feature description used by
  the manual editor and the JSON upload endpoint.
* :func:`import_course_from_osm` -- OpenStreetMap: ``golf=hole`` ways are the
  centerlines, fairway/green/bunker/water polygons are projected onto the
  nearest centerline to become the yardage-book boxes the engine simulates.

Geometry conventions used by the OSM path
-----------------------------------------
Latitude/longitude are flattened with an equirectangular projection around the
request point into a *right-handed* east/north frame measured in yards.  A
hole's centerline is the polyline of its ``golf=hole`` way, tee first.  For a
point ``p`` and a centerline segment with unit direction ``u``, the local
coordinates are

* ``x`` -- arc length along the polyline to the foot of the perpendicular
  (extrapolated along the first/last segment when ``p`` lies beyond an end);
* ``y`` -- signed lateral offset, positive to the *right* of the direction of
  travel.  "Right of ``u``" is ``(u_y, -u_x)``, so ``y = u_y*v_x - u_x*v_y``
  with ``v = p - foot``.

A clockwise change of direction between two consecutive segments (negative 2-D
cross product) is a right turn, i.e. ``dogleg_right``.  Those conventions match
the yardage-book frame described in :mod:`golf.models.course`.

Nothing here needs shapely or pandas: all geometry is plain numpy.
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Sequence

import httpx
import numpy as np
from sqlalchemy.orm import Session

from golf.models.course import Course, CourseSource, FeatureKind, FeatureSide, Hole, HoleFeature, HoleShape
from golf.schemas import CourseCreate, OSMImportRequest, ScorecardImport

__all__ = [
    "build_course_from_scorecard",
    "import_course_from_json",
    "import_course_from_osm",
    "project_onto_polyline",
    "polyline_length",
    "turn_info",
    "latlon_to_xy",
    "parse_distance_yards",
]

log = logging.getLogger(__name__)

# --- projection constants -------------------------------------------------------
METRES_PER_DEG_LAT = 110_540.0
METRES_PER_DEG_LON = 111_320.0  # at the equator; scaled by cos(latitude)
YARDS_PER_METRE = 1.09361

# --- OSM tuning ----------------------------------------------------------------
USER_AGENT = "caddie-golf-app/0.1"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
DOGLEG_THRESHOLD_DEG = 15.0
MAX_POLYGON_TO_CENTERLINE_YARDS = 120.0
CENTER_BAND_YARDS = 4.0          # |mean y| below this -> the feature straddles the centerline
MIN_FEATURE_WIDTH_YARDS = 4.0
OB_WIDTH_YARDS = 999.0
# A unit-less ``dist`` above this cannot be metres for any real hole.
MAX_PLAUSIBLE_HOLE_METRES = 650.0

_AREA_TAGS = frozenset({
    "fairway", "green", "tee", "bunker", "water_hazard", "lateral_water_hazard", "rough", "out_of_bounds",
})


# ==============================================================================
# Pure geometry helpers (numpy only)
# ==============================================================================
def _clean_polyline(polyline_xy: Any) -> np.ndarray:
    """Return the polyline as an ``(m, 2)`` float array without repeated vertices."""
    pts = np.asarray(polyline_xy, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 2 or pts.shape[0] < 2:
        raise ValueError("A polyline needs at least two (x, y) points")
    step = np.hypot(*np.diff(pts, axis=0).T)
    keep = np.concatenate([[True], step > 1e-9])
    pts = pts[keep]
    if pts.shape[0] < 2:
        raise ValueError("A polyline needs at least two distinct points")
    return pts


def polyline_length(polyline_xy: Any) -> float:
    """Total arc length of a polyline given as an ``(m, 2)`` array of points."""
    pts = np.asarray(polyline_xy, dtype=float)
    if pts.ndim != 2 or pts.shape[0] < 2:
        return 0.0
    return float(np.hypot(*np.diff(pts, axis=0).T).sum())


def _project(points_xy: Any, polyline_xy: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Project points onto a polyline.

    Returns ``(x_along, y_lateral, distance)`` where ``distance`` is the plain
    Euclidean distance from each point to the polyline (segments clamped, no
    extrapolation), used to decide which centerline a polygon belongs to.
    """
    pts = np.atleast_2d(np.asarray(points_xy, dtype=float))
    if pts.shape[-1] != 2:
        raise ValueError("points_xy must be shaped (n, 2)")
    line = _clean_polyline(polyline_xy)
    a = line[:-1]
    d = line[1:] - a
    seg_len = np.hypot(d[:, 0], d[:, 1])
    u = d / seg_len[:, None]
    cum = np.concatenate([[0.0], np.cumsum(seg_len)])

    v = pts[:, None, :] - a[None, :, :]                       # (n, m-1, 2)
    t_raw = v[..., 0] * u[None, :, 0] + v[..., 1] * u[None, :, 1]  # along-segment distance
    t_clamped = np.clip(t_raw, 0.0, seg_len[None, :])
    foot = a[None, :, :] + t_clamped[..., None] * u[None, :, :]
    dist = np.hypot(pts[:, None, 0] - foot[..., 0], pts[:, None, 1] - foot[..., 1])

    rows = np.arange(pts.shape[0])
    idx = np.argmin(dist, axis=1)
    last = seg_len.shape[0] - 1
    t_sel = t_clamped[rows, idx]
    t_unc = t_raw[rows, idx]
    # Beyond either end of the centerline: keep measuring along the end segment.
    t_sel = np.where((idx == last) & (t_unc > seg_len[idx]), t_unc, t_sel)
    t_sel = np.where((idx == 0) & (t_unc < 0.0), t_unc, t_sel)
    x_along = cum[idx] + t_sel

    ux, uy = u[idx, 0], u[idx, 1]
    vx, vy = v[rows, idx, 0], v[rows, idx, 1]
    y_lateral = uy * vx - ux * vy  # + = right of the direction of travel
    return x_along, y_lateral, dist[rows, idx]


def project_onto_polyline(points_xy: np.ndarray, polyline_xy: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Convert points into a polyline's local (yardage-book) coordinates.

    Args:
        points_xy: ``(n, 2)`` array of points (a single ``(2,)`` point is accepted).
        polyline_xy: ``(m, 2)`` array of centerline vertices, tee first.

    Returns:
        ``(x_along, y_lateral)``: arc length along the polyline to the foot of
        the perpendicular from each point (extrapolated past either end), and
        the signed lateral offset, positive to the right of the direction of
        travel.
    """
    x_along, y_lateral, _ = _project(points_xy, polyline_xy)
    return x_along, y_lateral


def turn_info(polyline_xy: np.ndarray, threshold_deg: float = DOGLEG_THRESHOLD_DEG) -> tuple[str, float | None, float | None]:
    """Detect a dogleg in a centerline.

    Looks at every interior vertex and takes the one with the sharpest change
    of direction.  If that turn exceeds ``threshold_deg`` the hole is a dogleg:
    a clockwise turn (travelling tee -> green) is ``dogleg_right``.

    Returns:
        ``(shape, dogleg_at_yards, dogleg_angle_deg)`` -- ``shape`` is one of
        the :class:`~golf.models.course.HoleShape` values; the other two are
        ``None`` for a straight hole.
    """
    line = _clean_polyline(polyline_xy)
    if line.shape[0] < 3:
        return HoleShape.STRAIGHT.value, None, None
    d = np.diff(line, axis=0)
    seg_len = np.hypot(d[:, 0], d[:, 1])
    u = d / seg_len[:, None]
    d1, d2 = u[:-1], u[1:]
    cross = d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0]
    dot = (d1 * d2).sum(axis=1)
    angles = np.degrees(np.arctan2(np.abs(cross), dot))
    i = int(np.argmax(angles))
    if angles[i] <= threshold_deg:
        return HoleShape.STRAIGHT.value, None, None
    shape = HoleShape.DOGLEG_LEFT.value if cross[i] > 0 else HoleShape.DOGLEG_RIGHT.value
    dogleg_at = float(np.cumsum(seg_len)[i])  # arc length to vertex i+1
    return shape, round(dogleg_at, 1), round(float(angles[i]), 1)


def latlon_to_xy(lat: Any, lon: Any, lat0: float, lon0: float) -> np.ndarray:
    """Equirectangular projection of lat/lon around ``(lat0, lon0)`` to east/north yards.

    ``x`` grows eastward, ``y`` northward; the result is shaped ``(n, 2)``.
    """
    lat_arr = np.atleast_1d(np.asarray(lat, dtype=float))
    lon_arr = np.atleast_1d(np.asarray(lon, dtype=float))
    x_m = (lon_arr - lon0) * math.cos(math.radians(lat0)) * METRES_PER_DEG_LON
    y_m = (lat_arr - lat0) * METRES_PER_DEG_LAT
    return np.column_stack([x_m, y_m]) * YARDS_PER_METRE


def _clamp(value: float, lo: float, hi: float) -> float:
    hi = max(hi, lo)
    return float(min(max(value, lo), hi))


def _polygon_lateral_extent(xs: np.ndarray, ys: np.ndarray) -> float:
    """Typical width of a polygon across the hole.

    Slices the polygon (given in local coordinates) with lines of constant
    ``x`` through its middle 80 % and returns the median of the crossing
    extents; falls back to the raw ``max(y) - min(y)`` when slicing fails.
    """
    fallback = float(ys.max() - ys.min())
    n = xs.shape[0]
    if n < 3:
        return fallback
    span = xs.max() - xs.min()
    if span < 1e-6:
        return fallback
    x0, x1 = xs.min() + 0.1 * span, xs.max() - 0.1 * span
    stations = np.linspace(x0, x1, max(int(span // 10), 3))
    # Edges of the closed polygon.
    xa, ya = xs, ys
    xb, yb = np.roll(xs, -1), np.roll(ys, -1)
    extents: list[float] = []
    for s in stations:
        crosses = (xa - s) * (xb - s) <= 0.0
        crosses &= np.abs(xb - xa) > 1e-9
        if crosses.sum() < 2:
            continue
        t = (s - xa[crosses]) / (xb[crosses] - xa[crosses])
        y_cross = ya[crosses] + t * (yb[crosses] - ya[crosses])
        extents.append(float(y_cross.max() - y_cross.min()))
    if not extents:
        return fallback
    return float(np.median(extents))


# ==============================================================================
# Shared ORM helpers
# ==============================================================================
def _apply_par_defaults(hole: Hole) -> None:
    """Generic corridor/green geometry by par (used when nothing better is known)."""
    yards = float(hole.yards)
    if hole.par <= 3:
        hole.fairway_start_yards = yards       # no fairway: tee shot lands on/around the green
        hole.fairway_width_yards = 35.0
        hole.green_width_yards = 28.0
        hole.green_depth_yards = 28.0
    else:
        hole.fairway_start_yards = min(100.0, max(yards - 60.0, 0.0))
        hole.fairway_width_yards = 35.0 if hole.par == 4 else 38.0
        hole.green_width_yards = 30.0
        hole.green_depth_yards = 30.0


def _set_totals(course: Course) -> None:
    course.par = sum(h.par for h in course.holes) if course.holes else None
    course.yardage = sum(h.yards for h in course.holes) if course.holes else None


def _persist(db: Session, course: Course) -> Course:
    """Add, commit and return the course with holes and features loaded."""
    db.add(course)
    db.commit()
    db.refresh(course)
    for hole in course.holes:
        _ = hole.features  # force-load so callers can use the object after the session closes
    return course


def _check_unique_numbers(numbers: Sequence[int]) -> None:
    dupes = sorted({n for n, c in Counter(numbers).items() if c > 1})
    if dupes:
        raise ValueError(f"Duplicate hole numbers: {', '.join(str(n) for n in dupes)}")


# ==============================================================================
# 1. Scorecard
# ==============================================================================
def build_course_from_scorecard(db: Session, payload: ScorecardImport) -> Course:
    """Create a course from a scorecard (par + yardage per hole).

    Each hole gets generic geometry by par: par 3s have no fairway (the fairway
    starts at the green) and a 28x28 green; par 4s a 35-yard fairway from 100
    yards; par 5s a 38-yard fairway.  No hazards are created.
    """
    if not payload.holes:
        raise ValueError("Scorecard has no holes")
    _check_unique_numbers([h.number for h in payload.holes])

    course = Course(
        name=payload.name, city=payload.city, country=payload.country, tee_name=payload.tee_name,
        source=CourseSource.SCORECARD.value,
    )
    for sc in sorted(payload.holes, key=lambda h: h.number):
        hole = Hole(number=sc.number, par=sc.par, yards=sc.yards, handicap_index=sc.handicap_index)
        _apply_par_defaults(hole)
        course.holes.append(hole)
    _set_totals(course)
    return _persist(db, course)


# ==============================================================================
# 2. Full JSON / manual description
# ==============================================================================
def _validate_enum(value: str, enum: type, what: str, hole_number: int) -> str:
    valid = [m.value for m in enum]  # type: ignore[attr-defined]
    if value not in valid:
        raise ValueError(f"Hole {hole_number}: invalid {what} {value!r}; expected one of {', '.join(valid)}")
    return value


def import_course_from_json(db: Session, payload: CourseCreate) -> Course:
    """Create a course from a complete :class:`~golf.schemas.CourseCreate` payload.

    Validates that hole numbers are unique, every feature has
    ``end_yards >= start_yards`` and feature ``kind``/``side`` (and hole
    ``shape``) are known enum values, raising :class:`ValueError` otherwise.
    """
    _check_unique_numbers([h.number for h in payload.holes])

    course = Course(
        name=payload.name, city=payload.city, country=payload.country,
        latitude=payload.latitude, longitude=payload.longitude, tee_name=payload.tee_name,
        rating=payload.rating, slope=payload.slope, notes=payload.notes,
        source=CourseSource.JSON.value,
    )
    for hc in sorted(payload.holes, key=lambda h: h.number):
        hole = Hole(
            number=hc.number, par=hc.par, yards=hc.yards, handicap_index=hc.handicap_index,
            shape=_validate_enum(hc.shape, HoleShape, "shape", hc.number),
            dogleg_at_yards=hc.dogleg_at_yards, dogleg_angle_deg=hc.dogleg_angle_deg,
            fairway_width_yards=hc.fairway_width_yards, fairway_start_yards=hc.fairway_start_yards,
            rough_width_yards=hc.rough_width_yards, green_width_yards=hc.green_width_yards,
            green_depth_yards=hc.green_depth_yards, elevation_change_ft=hc.elevation_change_ft,
            notes=hc.notes,
        )
        for fc in hc.features:
            if fc.end_yards < fc.start_yards:
                raise ValueError(
                    f"Hole {hc.number}: feature {fc.kind!r} has end_yards ({fc.end_yards}) "
                    f"before start_yards ({fc.start_yards})"
                )
            hole.features.append(HoleFeature(
                kind=_validate_enum(fc.kind, FeatureKind, "feature kind", hc.number),
                side=_validate_enum(fc.side, FeatureSide, "feature side", hc.number),
                start_yards=fc.start_yards, end_yards=fc.end_yards,
                offset_yards=fc.offset_yards, width_yards=fc.width_yards,
                penalty_strokes=fc.penalty_strokes, label=fc.label,
            ))
        course.holes.append(hole)
    _set_totals(course)
    return _persist(db, course)


# ==============================================================================
# 3. OpenStreetMap
# ==============================================================================
_DIST_RE = re.compile(r"^\s*([0-9]+(?:[.,][0-9]+)?)\s*([a-zA-Z]*)\s*\.?\s*$")
_YARD_UNITS = {"yd", "yds", "yard", "yards", "y"}
_METRE_UNITS = {"m", "meter", "meters", "metre", "metres"}
_FOOT_UNITS = {"ft", "feet", "foot"}


def parse_distance_yards(value: str | None, reference_yards: float | None = None) -> float | None:
    """Parse an OSM ``dist`` tag ("402 yd", "367 m", "380") into yards.

    OSM's convention is metres when no unit is given.  Because many courses
    are tagged in bare yards anyway, a unit-less value is compared with
    ``reference_yards`` (the centerline length) when available and the
    interpretation closer to it wins; without a reference, values too large to
    be metres for any hole are taken as yards.
    """
    if value is None:
        return None
    m = _DIST_RE.match(str(value))
    if not m:
        return None
    number = float(m.group(1).replace(",", "."))
    unit = m.group(2).lower()
    if unit in _YARD_UNITS:
        return number
    if unit in _METRE_UNITS:
        return number * YARDS_PER_METRE
    if unit in _FOOT_UNITS:
        return number / 3.0
    if unit:
        log.warning("Unknown distance unit %r in dist=%r; assuming metres", unit, value)
        return number * YARDS_PER_METRE
    as_metres = number * YARDS_PER_METRE
    if reference_yards is not None and reference_yards > 0:
        return number if abs(number - reference_yards) < abs(as_metres - reference_yards) else as_metres
    return number if number > MAX_PLAUSIBLE_HOLE_METRES else as_metres


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    m = re.search(r"\d+", str(value))
    return int(m.group(0)) if m else None


def _classify_tags(tags: dict[str, str]) -> str | None:
    """Map OSM tags to an internal shape kind (``hole``, ``fairway``, ``bunker``...)."""
    golf = tags.get("golf")
    if golf == "hole":
        return "hole"
    if golf in ("fairway", "green", "tee", "bunker"):
        return golf
    if golf in ("water_hazard", "lateral_water_hazard") or tags.get("natural") == "water":
        return "water"
    if golf == "out_of_bounds":
        return "ob"
    if golf == "rough":
        return "ob" if tags.get("rough") == "extreme" else "rough"
    return None


@dataclass
class _Shape:
    """One OSM way (or relation member) projected into local east/north yards."""

    osm_id: int
    kind: str
    tags: dict[str, str]
    xy: np.ndarray  # (n, 2)

    @property
    def centroid(self) -> np.ndarray:
        pts = self.xy
        if pts.shape[0] > 1 and np.allclose(pts[0], pts[-1]):
            pts = pts[:-1]
        return pts.mean(axis=0)


@dataclass
class _HoleDraft:
    """A hole under construction from a ``golf=hole`` way."""

    osm_id: int
    number: int
    tags: dict[str, str]
    centerline: np.ndarray
    hole: Hole
    fairway_polys: list[_Shape] = field(default_factory=list)


def _geometry_to_xy(geometry: Any, lat0: float, lon0: float) -> np.ndarray | None:
    pts = [(g["lat"], g["lon"]) for g in (geometry or []) if isinstance(g, dict) and "lat" in g and "lon" in g]
    if len(pts) < 2:
        return None
    arr = np.asarray(pts, dtype=float)
    return latlon_to_xy(arr[:, 0], arr[:, 1], lat0, lon0)


def _collect_shapes(data: dict[str, Any], lat0: float, lon0: float) -> tuple[list[_Shape], list[_Shape]]:
    """Split an Overpass response into hole centerlines and area shapes."""
    holes: list[_Shape] = []
    areas: list[_Shape] = []
    for el in data.get("elements", []):
        if not isinstance(el, dict):
            continue
        tags = el.get("tags") or {}
        kind = _classify_tags(tags)
        if kind is None:
            continue
        el_type, el_id = el.get("type"), int(el.get("id", 0))
        if el_type == "way":
            xy = _geometry_to_xy(el.get("geometry"), lat0, lon0)
            if xy is None:
                log.warning("Skipping OSM way %s (%s): no geometry", el_id, kind)
                continue
            (holes if kind == "hole" else areas).append(_Shape(el_id, kind, tags, xy))
        elif el_type == "relation":
            if kind == "hole":
                log.warning("Skipping OSM relation %s: hole relations are not supported", el_id)
                continue
            added = 0
            for member in el.get("members", []) or []:
                if member.get("type") != "way" or member.get("role", "outer") not in ("outer", ""):
                    continue
                xy = _geometry_to_xy(member.get("geometry"), lat0, lon0)
                if xy is None or xy.shape[0] < 3:
                    continue
                areas.append(_Shape(el_id, kind, tags, xy))
                added += 1
            if not added:
                log.warning("Skipping OSM relation %s (%s): no outer member geometry", el_id, kind)
    return holes, areas


def _draft_hole(shape: _Shape, fallback_number: int) -> _HoleDraft | None:
    """Turn a ``golf=hole`` way into a draft Hole with centerline-derived geometry."""
    try:
        line = _clean_polyline(shape.xy)
    except ValueError:
        log.warning("Skipping OSM hole way %s: degenerate centerline", shape.osm_id)
        return None
    length = polyline_length(line)
    tags = shape.tags
    yards = parse_distance_yards(tags.get("dist"), reference_yards=length) or length
    yards_int = max(int(round(yards)), 50)  # schema minimum; shorter "holes" are tagging errors
    par = _parse_int(tags.get("par"))
    if par is None or not 3 <= par <= 6:
        par = 3 if yards < 250 else 4 if yards < 480 else 5
    number = _parse_int(tags.get("ref"))
    if number is None:
        number = fallback_number
    shape_name, dogleg_at, dogleg_angle = turn_info(line)
    if dogleg_angle is not None and dogleg_angle > 90:
        # A hairpin centerline is almost always a mapping artefact; keep the bend but cap it.
        dogleg_angle = 90.0
    handicap = _parse_int(tags.get("handicap"))
    if handicap is not None and not 1 <= handicap <= 36:
        handicap = None
    hole = Hole(
        number=number, par=par, yards=yards_int, handicap_index=handicap,
        shape=shape_name, dogleg_at_yards=dogleg_at, dogleg_angle_deg=dogleg_angle,
        notes=tags.get("name"),
    )
    _apply_par_defaults(hole)
    return _HoleDraft(osm_id=shape.osm_id, number=number, tags=tags, centerline=line, hole=hole)


def _side_box(xs: np.ndarray, ys: np.ndarray) -> tuple[str, float, float]:
    """Return ``(side, offset_yards, width_yards)`` for a feature polygon in local coords."""
    mean_y = float(ys.mean())
    if abs(mean_y) < CENTER_BAND_YARDS:
        width = max(float(ys.max() - ys.min()), MIN_FEATURE_WIDTH_YARDS)
        return FeatureSide.CENTER.value, mean_y, width
    if mean_y > 0:
        near, far = max(float(ys.min()), 0.0), float(ys.max())
        side = FeatureSide.RIGHT.value
    else:
        near, far = max(float(-ys.max()), 0.0), float(-ys.min())
        side = FeatureSide.LEFT.value
    return side, near, max(far - near, MIN_FEATURE_WIDTH_YARDS)


def _apply_area(draft: _HoleDraft, shape: _Shape) -> None:
    """Fold one projected polygon into the draft hole (corridor dims or a HoleFeature)."""
    hole = draft.hole
    xs, ys = project_onto_polyline(shape.xy, draft.centerline)
    yards = float(hole.yards)
    kind = shape.kind

    if kind == "fairway":
        draft.fairway_polys.append(shape)
        width = _clamp(_polygon_lateral_extent(xs, ys), 20.0, 60.0)
        start = _clamp(float(xs.min()), 40.0, yards - 40.0)
        if len(draft.fairway_polys) == 1:
            hole.fairway_width_yards, hole.fairway_start_yards = width, start
        else:  # split fairways: keep the earliest start, average the width
            n = len(draft.fairway_polys)
            hole.fairway_width_yards = round((hole.fairway_width_yards * (n - 1) + width) / n, 1)
            hole.fairway_start_yards = min(hole.fairway_start_yards, start)
        return

    if kind == "green":
        centre_x = float((xs.max() + xs.min()) / 2.0)
        if abs(centre_x - polyline_length(draft.centerline)) > 80.0:
            log.warning("Ignoring green polygon %s: %.0f yds from the end of hole %s", shape.osm_id, centre_x, draft.number)
            return
        hole.green_width_yards = _clamp(float(ys.max() - ys.min()), 15.0, 50.0)
        hole.green_depth_yards = _clamp(float(xs.max() - xs.min()), 15.0, 50.0)
        # A laterally offset green centre is left alone: the centerline ends on the green.
        return

    if kind in ("tee", "rough"):
        return

    side, offset, width = _side_box(xs, ys)
    start = max(float(xs.min()), 0.0)
    end = max(float(xs.max()), start)
    if kind == "bunker":
        feature_kind, label = FeatureKind.BUNKER.value, f"bunker {side} at {int(round(start))} yds"
    elif kind == "water":
        feature_kind, label = FeatureKind.WATER.value, f"water {side} at {int(round(start))} yds"
    elif kind == "ob":
        feature_kind, label, width = FeatureKind.OB.value, f"OB {side} from {int(round(start))} yds", OB_WIDTH_YARDS
    else:
        return
    hole.features.append(HoleFeature(
        kind=feature_kind, side=side, start_yards=round(start, 1), end_yards=round(end, 1),
        offset_yards=round(offset, 1), width_yards=round(width, 1), label=label,
    ))


def _nearest_draft(shape: _Shape, drafts: list[_HoleDraft]) -> _HoleDraft | None:
    best: _HoleDraft | None = None
    best_dist = math.inf
    for draft in drafts:
        _, _, dist = _project(shape.centroid, draft.centerline)
        if dist[0] < best_dist:
            best, best_dist = draft, float(dist[0])
    if best is None or best_dist > MAX_POLYGON_TO_CENTERLINE_YARDS:
        return None
    return best


def _course_name_from_tags(drafts: list[_HoleDraft]) -> str:
    """Most common ``golf:course`` tag, else a hole ``name`` shared by several holes."""
    courses = Counter(d.tags["golf:course"] for d in drafts if d.tags.get("golf:course"))
    if courses:
        return courses.most_common(1)[0][0]
    names = Counter(d.tags["name"] for d in drafts if d.tags.get("name"))
    if names:
        name, count = names.most_common(1)[0]
        if count > 1:
            return name
    return "Imported course"


def _osm_get_json(client: httpx.Client, what: str, method: str, url: str, **kwargs: Any) -> Any:
    try:
        resp = client.request(method, url, **kwargs)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"OpenStreetMap request failed: {what}: {exc}") from exc
    if resp.status_code != 200:
        raise RuntimeError(f"OpenStreetMap request failed: {what} returned HTTP {resp.status_code}")
    try:
        return resp.json()
    except ValueError as exc:
        raise RuntimeError(f"OpenStreetMap request failed: {what} returned invalid JSON") from exc


def _resolve_location(client: httpx.Client, name: str) -> tuple[float, float, dict[str, Any]]:
    """Geocode ``<name> golf`` with Nominatim; returns ``(lat, lon, address)``."""
    data = _osm_get_json(
        client, "Nominatim search", "GET", NOMINATIM_URL,
        params={"q": f"{name} golf", "format": "json", "limit": 1, "addressdetails": 1},
        headers={"User-Agent": USER_AGENT},
    )
    if not isinstance(data, list) or not data:
        raise ValueError("Course not found on OpenStreetMap")
    hit = data[0]
    try:
        lat, lon = float(hit["lat"]), float(hit["lon"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Course not found on OpenStreetMap") from exc
    address = hit.get("address") if isinstance(hit.get("address"), dict) else {}
    return lat, lon, address


def _overpass_query(lat: float, lon: float, radius_m: int) -> str:
    return (
        "[out:json][timeout:30];\n"
        "(\n"
        f'  way["golf"~"^(hole|fairway|green|tee|bunker|water_hazard|lateral_water_hazard|rough|out_of_bounds)$"]'
        f"(around:{radius_m},{lat:.6f},{lon:.6f});\n"
        f'  relation["golf"~"^(fairway|green|bunker|water_hazard|lateral_water_hazard)$"]'
        f"(around:{radius_m},{lat:.6f},{lon:.6f});\n"
        ");\n"
        "out body geom;\n"
    )


def import_course_from_osm(
    db: Session,
    req: OSMImportRequest,
    client: httpx.Client | None = None,
    overpass_url: str = "https://overpass-api.de/api/interpreter",
) -> Course:
    """Import a course from OpenStreetMap.

    The location comes from ``req.latitude``/``req.longitude`` or, failing
    that, a Nominatim search for ``req.name``.  One Overpass query fetches the
    ``golf=*`` ways around it; ``golf=hole`` ways become holes (tee = first
    node) and fairway/green/bunker/water/OOB polygons are projected onto the
    nearest centerline.

    Args:
        db: SQLAlchemy session; the course is committed before returning.
        req: what to import.
        client: optional :class:`httpx.Client` (tests inject a mock transport);
            one is created and closed here when omitted.
        overpass_url: Overpass API endpoint.

    Raises:
        ValueError: nothing to search for, the name cannot be geocoded, or no
            ``golf=hole`` ways exist near the location.
        RuntimeError: network failure or a non-200 response from OSM.
    """
    own_client = client is None
    if client is None:
        client = httpx.Client(timeout=40, headers={"User-Agent": USER_AGENT})
    try:
        address: dict[str, Any] = {}
        if req.latitude is not None and req.longitude is not None:
            lat0, lon0 = float(req.latitude), float(req.longitude)
        elif req.name:
            lat0, lon0, address = _resolve_location(client, req.name)
        else:
            raise ValueError("Provide a course name or latitude/longitude to import from OpenStreetMap")

        data = _osm_get_json(
            client, "Overpass query", "POST", overpass_url,
            data={"data": _overpass_query(lat0, lon0, req.radius_m)},
            headers={"User-Agent": USER_AGENT},
        )
    finally:
        if own_client:
            client.close()

    if not isinstance(data, dict):
        raise RuntimeError("OpenStreetMap request failed: unexpected Overpass response")
    hole_shapes, area_shapes = _collect_shapes(data, lat0, lon0)
    if not hole_shapes:
        raise ValueError("No golf holes found on OpenStreetMap near that location")

    # Holes: drop duplicate numbers (first wins), sort, renumber 1..N.
    drafts: list[_HoleDraft] = []
    seen: set[int] = set()
    for i, shape in enumerate(hole_shapes):
        draft = _draft_hole(shape, fallback_number=1000 + i)
        if draft is None or draft.number in seen:
            if draft is not None:
                log.warning("Skipping duplicate OSM hole %s (way %s)", draft.number, shape.osm_id)
            continue
        seen.add(draft.number)
        drafts.append(draft)
    if not drafts:
        raise ValueError("No golf holes found on OpenStreetMap near that location")
    drafts.sort(key=lambda d: d.number)
    for n, draft in enumerate(drafts, start=1):
        draft.number = n
        draft.hole.number = n

    # Areas: attach each polygon to the nearest centerline.
    for shape in area_shapes:
        draft = _nearest_draft(shape, drafts)
        if draft is None:
            log.debug("Ignoring OSM %s %s: too far from every hole", shape.kind, shape.osm_id)
            continue
        _apply_area(draft, shape)

    course = Course(
        name=req.name or _course_name_from_tags(drafts),
        city=address.get("city") or address.get("town") or address.get("village"),
        country=address.get("country"),
        latitude=lat0, longitude=lon0, tee_name=req.tee_name,
        source=CourseSource.OSM.value, osm_id=str(drafts[0].osm_id),
    )
    for draft in drafts:
        course.holes.append(draft.hole)
    _set_totals(course)
    return _persist(db, course)
