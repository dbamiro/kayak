from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import close_pool, get_pool
from app.routers import admin_api, alerts, auth_api, buildings, compare, incentives, monetization_api, saved_buildings, search


@asynccontextmanager
async def lifespan(_app: FastAPI):
    get_settings().validate_production()
    yield
    close_pool()


app = FastAPI(
    title="Kayak DMV — Apartment Incentive Intelligence API",
    version="0.1.0",
    lifespan=lifespan,
)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_api.router)
app.include_router(incentives.router)
app.include_router(search.router)
app.include_router(buildings.router)
app.include_router(compare.router)
app.include_router(alerts.router)
app.include_router(saved_buildings.router)
app.include_router(monetization_api.router)
app.include_router(admin_api.router)


@app.get("/")
def root() -> dict[str, str]:
    """Browser default; APIs live under `/search`, `/buildings`, etc."""
    return {
        "service": app.title,
        "docs": "/docs",
        "health": "/health",
        "openapi": "/openapi.json",
        "monetization": "/plans",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready() -> dict[str, str]:
    """Readiness: verifies Postgres connectivity."""
    try:
        with get_pool().connection() as conn:
            conn.execute("SELECT 1")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail="database_unavailable") from exc
    return {"status": "ready"}
