from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from golf import services
from golf.database import get_db
from golf.engine import course_import
from golf.engine.hole_model import HoleGeometry
from golf.models import Course, Hole, HoleFeature, Round, StrategyPlan
from golf.schemas import (
    CourseCreate, CourseListResponse, CourseResponse, CourseUpdate, HoleCreate, HoleResponse, HoleUpdate,
    OSMImportRequest, ScorecardImport,
)

router = APIRouter()


def _list_item(c: Course) -> dict:
    return {
        "id": c.id, "name": c.name, "city": c.city, "country": c.country, "latitude": c.latitude,
        "longitude": c.longitude, "tee_name": c.tee_name, "rating": c.rating, "slope": c.slope, "notes": c.notes,
        "source": c.source, "par": c.par, "yardage": c.yardage, "hole_count": len(c.holes),
    }


@router.get("", response_model=list[CourseListResponse])
def list_courses(db: Session = Depends(get_db)):
    return [_list_item(c) for c in db.query(Course).order_by(Course.name).all()]


@router.post("", response_model=CourseResponse, status_code=201)
def create_course(data: CourseCreate, db: Session = Depends(get_db)):
    try:
        course = course_import.import_course_from_json(db, data)
    except ValueError as e:
        raise HTTPException(422, str(e))
    course.source = "manual" if not data.holes else "json"
    db.commit()
    return services.get_course(db, course.id)


@router.post("/import/scorecard", response_model=CourseResponse, status_code=201)
def import_scorecard(data: ScorecardImport, db: Session = Depends(get_db)):
    try:
        course = course_import.build_course_from_scorecard(db, data)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return services.get_course(db, course.id)


@router.post("/import/osm", response_model=CourseResponse, status_code=201)
def import_osm(data: OSMImportRequest, db: Session = Depends(get_db)):
    if not data.name and (data.latitude is None or data.longitude is None):
        raise HTTPException(422, "Provide a course name or latitude/longitude")
    try:
        course = course_import.import_course_from_osm(db, data)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    return services.get_course(db, course.id)


@router.get("/{course_id}", response_model=CourseResponse)
def get_course(course_id: int, db: Session = Depends(get_db)):
    course = services.get_course(db, course_id)
    if not course:
        raise HTTPException(404, "Course not found")
    return course


@router.put("/{course_id}", response_model=CourseResponse)
def update_course(course_id: int, data: CourseUpdate, db: Session = Depends(get_db)):
    course = services.get_course(db, course_id)
    if not course:
        raise HTTPException(404, "Course not found")
    services.apply_updates(course, data.model_dump(exclude_unset=True))
    db.commit()
    return services.get_course(db, course_id)


@router.delete("/{course_id}", status_code=204)
def delete_course(course_id: int, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(404, "Course not found")
    # Rounds keep their history (course link cleared); plans for the course go with it.
    db.query(Round).filter(Round.course_id == course_id).update({"course_id": None})
    db.query(StrategyPlan).filter(StrategyPlan.course_id == course_id).delete()
    db.delete(course)
    db.commit()
    return None


@router.post("/{course_id}/holes", response_model=HoleResponse, status_code=201)
def add_hole(course_id: int, data: HoleCreate, db: Session = Depends(get_db)):
    course = services.get_course(db, course_id)
    if not course:
        raise HTTPException(404, "Course not found")
    if any(h.number == data.number for h in course.holes):
        raise HTTPException(409, f"Hole {data.number} already exists")
    payload = data.model_dump()
    feats = payload.pop("features", [])
    hole = Hole(course_id=course_id, **payload)
    db.add(hole)
    db.flush()
    for f in feats:
        db.add(HoleFeature(hole_id=hole.id, **f))
    db.commit()
    services.refresh_course_totals(db, services.get_course(db, course_id))
    db.refresh(hole)
    return hole


@router.put("/{course_id}/holes/{number}", response_model=HoleResponse)
def update_hole(course_id: int, number: int, data: HoleUpdate, db: Session = Depends(get_db)):
    hole = db.query(Hole).filter(Hole.course_id == course_id, Hole.number == number).first()
    if not hole:
        raise HTTPException(404, "Hole not found")
    payload = data.model_dump(exclude_unset=True)
    feats = payload.pop("features", None)
    services.apply_updates(hole, payload)
    db.commit()
    if feats is not None:
        services.replace_hole_features(db, hole, feats)
    services.refresh_course_totals(db, services.get_course(db, course_id))
    db.refresh(hole)
    return hole


@router.get("/{course_id}/holes/{number}/geometry")
def hole_geometry(course_id: int, number: int, db: Session = Depends(get_db)):
    """Render spec for the SVG hole map (local yardage-book coordinates)."""
    hole = db.query(Hole).filter(Hole.course_id == course_id, Hole.number == number).first()
    if not hole:
        raise HTTPException(404, "Hole not found")
    return HoleGeometry.from_hole(hole).render_spec()
