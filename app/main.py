from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import close_pool
from app.routers import alerts, buildings, compare, search


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    close_pool()


app = FastAPI(
    title="DMV Apartment Intelligence API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(search.router)
app.include_router(buildings.router)
app.include_router(compare.router)
app.include_router(alerts.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
