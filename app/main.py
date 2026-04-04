"""
ONEST Skill Discovery Node — FastAPI application entry point.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.workers import router as workers_router
from app.db.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create tables. Shutdown: nothing special yet."""
    init_db()
    yield


app = FastAPI(
    title="ONEST Skill Discovery Node",
    description="BPP backend for blue-collar worker discovery on the ONEST network.",
    version="0.1.0",
    lifespan=lifespan,
)

# ── Routers ──
app.include_router(workers_router, prefix="/api")


# ── Health ──
@app.get("/health", tags=["health"])
def health():
    return {"status": "healthy"}
