"""
ONEST Skill Discovery Node — FastAPI application entry point.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.workers import router as workers_router
from app.api.chat import router as chat_router
from app.api.aadhaar import router as aadhaar_router
from app.api.beckn_gateway import router as beckn_router
from app.api.bpp import router as bpp_router
from app.api.xinput import router as xinput_router
from app.api.registry import router as registry_router, self_register
from app.db.database import init_db
from app.schedulers.verification_poller import verification_poller

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create tables, self-register BPP, launch background pollers."""
    init_db()

    # Self-register this BPP in the mock registry for auth verification
    self_register(
        bpp_id="onest-skill-discovery.bpp.io",
        bpp_uri="https://onest-skill-discovery.bpp.io",
    )

    poller_task = asyncio.create_task(verification_poller())
    yield
    poller_task.cancel()
    try:
        await poller_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="ONEST Skill Discovery Node",
    description=(
        "Beckn Provider Platform (BPP) for blue-collar worker discovery "
        "on the ONEST network. Implements the full DSEP/Beckn transaction "
        "lifecycle: search, select, init, confirm, status, update, cancel."
    ),
    version="0.2.0",
    lifespan=lifespan,
)

# ── Optional: Enable Beckn auth verification middleware ──
# Uncomment the next line to enforce ed25519 signature checks on /api/bpp/*
# from app.services.auth import verify_beckn_auth_middleware
# app.middleware("http")(verify_beckn_auth_middleware)

# ── Routers ──
app.include_router(workers_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(aadhaar_router, prefix="/api")
app.include_router(beckn_router, prefix="/api")    # mock BAP gateway (on_* callbacks)
app.include_router(bpp_router, prefix="/api")       # BPP endpoints (search, select, init, ...)
app.include_router(xinput_router, prefix="/api")    # xInput form hosting
app.include_router(registry_router, prefix="/api")  # mock registry


# ── Health ──
@app.get("/health", tags=["health"])
def health():
    return {"status": "healthy"}
