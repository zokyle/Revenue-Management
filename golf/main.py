"""Caddie - a personal golf course-strategy agent.

Run with::

    uvicorn golf.main:app --reload --port 8001

The hotel revenue app in ``app/`` is untouched; this is a sibling application
sharing only the repository and its Python dependencies.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from golf.api import courses, players, rounds, strategy
from golf.config import settings
from golf.database import init_db

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app.include_router(players.router, prefix="/api/players", tags=["players"])
app.include_router(courses.router, prefix="/api/courses", tags=["courses"])
app.include_router(rounds.router, prefix="/api/players/{player_id}/rounds", tags=["rounds"])
app.include_router(strategy.router, prefix="/api/players", tags=["profile", "strategy", "caddie"])


@app.get("/api/health")
def health():
    return {"status": "ok", "app": settings.app_name, "llm": bool(settings.anthropic_api_key)}


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
@app.get("/")
async def dashboard_page(request: Request):
    return templates.TemplateResponse(request=request, name="dashboard.html")


@app.get("/rounds")
async def rounds_page(request: Request):
    return templates.TemplateResponse(request=request, name="rounds.html")


@app.get("/rounds/{round_id}")
async def round_detail_page(request: Request, round_id: int):
    return templates.TemplateResponse(request=request, name="round_detail.html", context={"round_id": round_id})


@app.get("/courses")
async def courses_page(request: Request):
    return templates.TemplateResponse(request=request, name="courses.html")


@app.get("/courses/{course_id}")
async def course_detail_page(request: Request, course_id: int):
    return templates.TemplateResponse(request=request, name="course_detail.html", context={"course_id": course_id})


@app.get("/strategy")
async def strategy_page(request: Request):
    return templates.TemplateResponse(request=request, name="strategy.html")


@app.get("/strategy/{course_id}")
async def strategy_course_page(request: Request, course_id: int):
    return templates.TemplateResponse(request=request, name="strategy.html", context={"course_id": course_id})


@app.get("/caddie")
async def caddie_page(request: Request):
    return templates.TemplateResponse(request=request, name="caddie.html")


@app.get("/bag")
async def bag_page(request: Request):
    return templates.TemplateResponse(request=request, name="bag.html")
