"""
Tri-Flow Connect — FastAPI Backend
Replaces Supabase BaaS for self-hosted deployment on Hugging Face Spaces.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import create_pool, close_pool
from app.routers.auth import router as auth_router
from app.routers.profiles import router as profiles_router
from app.routers.roles import router as roles_router
from app.routers.events import router as events_router
from app.routers.absence import router as absence_router
from app.routers.devices import router as devices_router
from app.routers.complaints import router as complaints_router
from app.routers.firms import firms_router, jobs_router
from app.routers.saed import router as saed_router
from app.routers.uploads import router as uploads_router
from app.routers.content import (
    news_router, community_router, notif_router, metrics_router
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await create_pool()
    yield
    # Shutdown
    await close_pool()


settings = get_settings()

app = FastAPI(
    title="Tri-Flow Connect API",
    description="NYSC Ikeja LGA Digital Ecosystem — Backend API",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(profiles_router)
app.include_router(roles_router)
app.include_router(events_router)
app.include_router(absence_router)
app.include_router(devices_router)
app.include_router(complaints_router)
app.include_router(firms_router)
app.include_router(jobs_router)
app.include_router(saed_router)
app.include_router(uploads_router)
app.include_router(news_router)
app.include_router(community_router)
app.include_router(notif_router)
app.include_router(metrics_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
