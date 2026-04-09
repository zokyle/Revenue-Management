from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api import properties, inventory, rates, forecasts, optimization, pms, analytics
from app.config import settings

app = FastAPI(title=settings.app_name, debug=settings.debug)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# API routes
app.include_router(properties.router, prefix="/api/properties", tags=["properties"])
app.include_router(inventory.router, prefix="/api/properties", tags=["inventory"])
app.include_router(rates.router, prefix="/api/properties", tags=["rates"])
app.include_router(forecasts.router, prefix="/api/properties", tags=["forecasts"])
app.include_router(optimization.router, prefix="/api/properties", tags=["optimization"])
app.include_router(pms.router, prefix="/api/properties", tags=["pms"])
app.include_router(analytics.router, prefix="/api/properties", tags=["analytics"])


# Dashboard routes
@app.get("/")
async def dashboard_home(request: Request):
    return templates.TemplateResponse(request=request, name="dashboard.html")


@app.get("/rates")
async def rates_page(request: Request):
    return templates.TemplateResponse(request=request, name="rates.html")


@app.get("/forecast")
async def forecast_page(request: Request):
    return templates.TemplateResponse(request=request, name="forecast.html")


@app.get("/optimization")
async def optimization_page(request: Request):
    return templates.TemplateResponse(request=request, name="optimization.html")


@app.get("/inventory")
async def inventory_page(request: Request):
    return templates.TemplateResponse(request=request, name="inventory.html")


@app.get("/settings")
async def settings_page(request: Request):
    return templates.TemplateResponse(request=request, name="settings.html")
