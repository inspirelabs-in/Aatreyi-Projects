"""SQLAlchemy declarative base + engine/session factories.

`Base.metadata` is the single source of truth that Alembic autogenerates against.
Models live in db/models.py (Phase 1) and import Base from here.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool

from config import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


# ── Sync engine (Alembic, scripts, scheduler jobs) ──────────────────────────
sync_engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=sync_engine, autoflush=False, expire_on_commit=False)

# ── Async engine (FastAPI request handlers, async agents) ───────────────────
# NullPool: every connection is opened fresh and closed after use, so asyncpg
# connections are never reused across event loops (CLI runs, scheduler jobs,
# FastAPI's TestClient loop). Fine for our scale; revisit if the API gets hot.
async_engine = create_async_engine(settings.DATABASE_URL_ASYNC, poolclass=NullPool)
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine, expire_on_commit=False, autoflush=False
)
