"""Admin (system-owner) endpoints — global, cross-tenant views.

Gated by the ``X-Role`` request header. This is a DEMO-grade guard: it separates
ADMIN data from USER data and blocks the admin API unless the caller asserts the
admin role. It is NOT cryptographic auth — production needs real login + channel
ownership before these can be trusted as a security boundary.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api import services
from api.db import get_session

router = APIRouter(prefix="/api/admin", tags=["admin"])


async def require_admin(x_role: str | None = Header(default=None)):
    """Allow only callers asserting the admin role (X-Role: admin)."""
    if (x_role or "user").strip().lower() != "admin":
        raise HTTPException(status_code=403, detail="admin role required")
    return True


@router.get("/overview")
async def overview(_: bool = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    return await services.admin_overview(session)


@router.get("/channels")
async def all_channels(_: bool = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    return await services.admin_all_channels(session)


@router.get("/agent-performance")
async def agent_performance(_: bool = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    return await services.admin_agent_performance(session)


@router.get("/global-events")
async def global_events(limit: int = Query(60, ge=1, le=200),
                        _: bool = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    return await services.admin_global_events(session, limit)


@router.get("/system-health")
async def system_health(_: bool = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    return await services.admin_system_health(session)
