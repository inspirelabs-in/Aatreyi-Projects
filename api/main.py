"""FastAPI application — UI backend.

    uvicorn api.main:app --reload --port 8000

Endpoints (all JSON):
    GET  /health
    GET  /api/channels
    POST /api/channels                         onboard
    GET  /api/channels/{id}/dashboard
    GET  /api/channels/{id}/queue
    POST /api/channels/{id}/queue/{post}/approve
    POST /api/channels/{id}/queue/{post}/reject
    PUT  /api/channels/{id}/queue/{post}        edit text
    GET  /api/channels/{id}/analytics
    GET  /api/channels/{id}/strategy
    GET  /api/channels/{id}/competitors
    POST /api/channels/{id}/agents/run          manual trigger
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from api import services
from api.db import get_session, AsyncSessionLocal
from api.routers import admin, channels, review
from config import settings
from db.models import AgentRun, RunStatus

log = logging.getLogger("api.main")


def _init_sentry() -> None:
    if not settings.SENTRY_DSN:
        return
    try:  # optional dependency; no-op if not installed
        import sentry_sdk

        sentry_sdk.init(dsn=settings.SENTRY_DSN, traces_sample_rate=0.1)
    except Exception:
        pass


async def _clear_stale_runs() -> None:
    """Mark any 'running' agent_runs as failed on startup.

    Container restarts kill asyncio tasks without updating their DB status,
    leaving zombie 'running' records that block the UI and prevent re-runs.
    """
    try:
        async with AsyncSessionLocal() as s:
            result = await s.execute(
                update(AgentRun)
                .where(AgentRun.status == RunStatus.running)
                .values(
                    status=RunStatus.failed,
                    error="Interrupted by API restart",
                    finished_at=datetime.now(timezone.utc),
                )
            )
            await s.commit()
            if result.rowcount:
                log.info("startup: cleared %d stale running agent_runs", result.rowcount)
    except Exception as exc:
        log.warning("startup: failed to clear stale runs: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _init_sentry()
    await _clear_stale_runs()
    yield


app = FastAPI(title="Telegram Growth Agent API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(channels.router)
app.include_router(review.router)
app.include_router(admin.router)


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok"}


@app.get("/api/agent-runs", tags=["meta"])
async def agent_runs(
    status: str | None = Query(None, description="filter: running | completed | failed"),
    limit: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
):
    """Audit log of agent executions (for monitoring failures)."""
    return await services.get_agent_runs(session, status, limit)
