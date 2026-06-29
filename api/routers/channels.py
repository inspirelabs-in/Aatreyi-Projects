"""Channel read endpoints: list/create, dashboard, analytics, strategy, competitors."""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db import get_session
from api.schemas import ChannelSettingsUpdate, CompetitorHandleUpdate, ContentSourceCreate, ContentSourceUpdate, OnboardChannel
from api import services
from db.models import Channel, ChannelStatus, Tier
from tools.channels import get_or_create_channel

router = APIRouter(prefix="/api/channels", tags=["channels"])
log = logging.getLogger("api.channels")


async def _auto_onboard(channel_id: str) -> None:
    """Background: detect the channel (live subscribers -> tier) and run the
    tier-appropriate pipeline (DNA/competitor/analytics/strategy, or lean).
    Failures are logged to agent_runs by each agent; never crashes the request."""
    from scheduler.jobs import onboard_channel_pipeline
    try:
        result = await onboard_channel_pipeline(channel_id)
        log.info("auto-onboard %s done: %s", channel_id, result)
    except Exception as exc:  # noqa: BLE001
        log.warning("auto-onboard %s failed: %s: %s", channel_id, type(exc).__name__, exc)


@router.get("")
async def list_channels(session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(Channel).order_by(Channel.created_at.desc()))).scalars().all()
    return [
        {
            "id": str(r.id),
            "telegram_username": r.telegram_username,
            "display_name": r.display_name,
            "tier": r.tier.value if r.tier else None,
            "category": r.category,
            "status": r.status.value if r.status else None,
        }
        for r in rows
    ]


@router.post("", status_code=201)
async def onboard_channel(body: OnboardChannel, background: BackgroundTasks,
                          session: AsyncSession = Depends(get_session)):
    channel = await get_or_create_channel(
        body.telegram_username,
        category=body.category,
        growth_goal=body.growth_goal,
        language=body.language,
    )
    # Kick off the full detect-subscribers -> tier -> pipeline automatically.
    background.add_task(_auto_onboard, channel["id"])
    return {"channel_id": channel["id"], "telegram_username": channel["telegram_username"],
            "tier": channel["tier"], "status": channel["status"],
            "next_step": "auto_onboarding_started"}


async def _require_channel(session: AsyncSession, channel_id: str) -> Channel:
    ch = await services.get_channel_or_none(session, channel_id)
    if ch is None:
        raise HTTPException(status_code=404, detail="channel not found")
    return ch


@router.get("/{channel_id}/dashboard")
async def dashboard(channel_id: str, session: AsyncSession = Depends(get_session)):
    await _require_channel(session, channel_id)
    return await services.build_dashboard(session, channel_id)


@router.get("/{channel_id}/control")
async def control(channel_id: str, session: AsyncSession = Depends(get_session)):
    """Agent-centric live state for the Control Room (event stream + pipeline + system)."""
    await _require_channel(session, channel_id)
    return await services.build_control_state(session, channel_id)


@router.get("/{channel_id}/intelligence")
async def intelligence(channel_id: str, session: AsyncSession = Depends(get_session)):
    """Post/audience intelligence (virality, purpose mix, community signal) + retention plan."""
    await _require_channel(session, channel_id)
    return await services.get_intelligence(session, channel_id)


@router.get("/{channel_id}/subscribers")
async def subscribers(channel_id: str, n: int = Query(300, ge=1, le=2000),
                      session: AsyncSession = Depends(get_session)):
    """Live subscriber samples (every ~20 min) — the real, updating growth series."""
    await _require_channel(session, channel_id)
    return await services.get_subscriber_series(session, channel_id, n)


@router.get("/{channel_id}/analytics")
async def analytics(channel_id: str, snapshot_type: str = Query("daily"),
                    n: int = Query(30, ge=1, le=365), session: AsyncSession = Depends(get_session)):
    await _require_channel(session, channel_id)
    return await services.get_analytics(session, channel_id, snapshot_type, n)


@router.get("/{channel_id}/strategy")
async def strategy(channel_id: str, session: AsyncSession = Depends(get_session)):
    await _require_channel(session, channel_id)
    result = await services.get_strategy(session, channel_id)
    if result is None:
        raise HTTPException(status_code=404, detail="no active strategy")
    return result


@router.get("/{channel_id}/competitors")
async def competitors(channel_id: str, session: AsyncSession = Depends(get_session)):
    await _require_channel(session, channel_id)
    return await services.get_competitors(session, channel_id)


@router.patch("/{channel_id}/competitors/{competitor_key}/handle")
async def update_competitor_handle(
    channel_id: str,
    competitor_key: str,
    body: CompetitorHandleUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update the Telegram handle for a market-only competitor."""
    import uuid as _uuid
    from db.models import Competitor as CompetitorModel

    await _require_channel(session, channel_id)
    handle = body.handle.lstrip("@").strip()
    if not handle:
        raise HTTPException(status_code=422, detail="handle must not be empty")

    result = await session.execute(
        select(CompetitorModel).where(
            CompetitorModel.channel_id == _uuid.UUID(channel_id),
            CompetitorModel.competitor_username == competitor_key,
        )
    )
    comp = result.scalar_one_or_none()
    if comp is None:
        raise HTTPException(status_code=404, detail="competitor not found")

    comp.competitor_username = handle
    await session.commit()
    return {"updated": True, "competitor_username": comp.competitor_username}


@router.get("/{channel_id}/sources")
async def list_content_sources(channel_id: str, session: AsyncSession = Depends(get_session)):
    await _require_channel(session, channel_id)
    from tools.content_sources import list_sources
    return await list_sources(channel_id)


@router.post("/{channel_id}/sources", status_code=201)
async def add_content_source(channel_id: str, body: ContentSourceCreate,
                             session: AsyncSession = Depends(get_session)):
    await _require_channel(session, channel_id)
    from tools.content_sources import add_source
    try:
        return await add_source(channel_id, type=body.type, url=body.url, name=body.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/{channel_id}/sources/{source_id}")
async def patch_content_source(channel_id: str, source_id: str, body: ContentSourceUpdate,
                               session: AsyncSession = Depends(get_session)):
    await _require_channel(session, channel_id)
    from tools.content_sources import update_source
    res = await update_source(source_id, is_active=body.is_active, name=body.name, url=body.url)
    if not res.get("updated"):
        raise HTTPException(status_code=404, detail="source not found")
    return res


@router.delete("/{channel_id}/sources/{source_id}", status_code=204)
async def remove_content_source(channel_id: str, source_id: str,
                                session: AsyncSession = Depends(get_session)):
    await _require_channel(session, channel_id)
    from tools.content_sources import delete_source
    res = await delete_source(source_id)
    if not res.get("deleted"):
        raise HTTPException(status_code=404, detail="source not found")


@router.patch("/{channel_id}/settings")
async def patch_channel_settings(channel_id: str, body: ChannelSettingsUpdate,
                                 session: AsyncSession = Depends(get_session)):
    ch = await _require_channel(session, channel_id)
    if body.auto_approve is not None:
        ch.auto_approve = body.auto_approve
    if body.score_threshold is not None:
        ch.score_threshold = body.score_threshold
    await session.commit()
    return {
        "channel_id": str(ch.id),
        "auto_approve": ch.auto_approve,
        "score_threshold": ch.score_threshold,
    }


@router.get("/{channel_id}/settings")
async def get_channel_settings(channel_id: str, session: AsyncSession = Depends(get_session)):
    ch = await _require_channel(session, channel_id)
    return {
        "channel_id": str(ch.id),
        "auto_approve": ch.auto_approve,
        "score_threshold": ch.score_threshold,
    }


@router.post("/{channel_id}/sources/seed")
async def seed_content_sources(channel_id: str, session: AsyncSession = Depends(get_session)):
    ch = await _require_channel(session, channel_id)
    from tools.content_sources import seed_default_sources
    return await seed_default_sources(channel_id, ch.category)
