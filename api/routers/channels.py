"""Channel read endpoints: list/create, dashboard, analytics, strategy, competitors."""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db import get_session
from api.authz import CurrentUser, can_access_channel, can_manage_channel, get_current_user, is_platform_admin, require
from api.schemas import ChannelSettingsUpdate, ChannelUpdate, CompetitorHandleUpdate, ContentSourceCreate, ContentSourceUpdate, OnboardChannel
from api import services
from db.models import Channel, ChannelStatus, Tier
from tools.channels import get_or_create_channel

router = APIRouter(prefix="/api/channels", tags=["channels"])
log = logging.getLogger("api.channels")


async def require_channel_access(
    channel_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> Channel:
    """Resolve a channel and enforce the caller may access it (404 then 403).

    Shared dependency so every /{channel_id}/* route is org-scoped without
    duplicating the check. Platform admins pass for any channel."""
    ch = await services.get_channel_or_none(session, channel_id)
    if ch is None:
        raise HTTPException(status_code=404, detail="channel not found")
    require(can_access_channel(current_user, ch), "channel not in your organization")
    return ch


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
async def list_channels(session: AsyncSession = Depends(get_session),
                        current_user: CurrentUser = Depends(get_current_user)):
    """Platform Admin sees every channel; a normal user sees only their own
    organization's channels. Filtering happens in the query, never on the client."""
    q = select(Channel).order_by(Channel.created_at.desc())
    if not is_platform_admin(current_user):
        import uuid as _uuid
        q = q.where(Channel.organization_id == _uuid.UUID(str(current_user.organization_id)))
    rows = (await session.execute(q)).scalars().all()
    return [
        {
            "id": str(r.id),
            "organization_id": str(r.organization_id),
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
                          session: AsyncSession = Depends(get_session),
                          current_user: CurrentUser = Depends(get_current_user)):
    # The channel is assigned to the caller's organization. A Platform Admin may
    # target another organization via body.organization_id; a normal user cannot
    # (no org selector is exposed to them).
    org_id = current_user.organization_id
    if body.organization_id and is_platform_admin(current_user):
        org_id = body.organization_id
    if not org_id:
        from tools.organizations import get_grabon_org
        grab = await get_grabon_org()
        org_id = grab["id"] if grab else None
    import uuid as _uuid
    channel = await get_or_create_channel(
        body.telegram_username,
        organization_id=_uuid.UUID(str(org_id)) if org_id else None,
        category=body.category,
        growth_goal=body.growth_goal,
        language=body.language,
    )
    # Kick off the full detect-subscribers -> tier -> pipeline automatically.
    background.add_task(_auto_onboard, channel["id"])
    return {"channel_id": channel["id"], "telegram_username": channel["telegram_username"],
            "tier": channel["tier"], "status": channel["status"],
            "next_step": "auto_onboarding_started"}


@router.patch("/{channel_id}")
async def update_channel(channel_id: str, body: ChannelUpdate,
                         ch: Channel = Depends(require_channel_access),
                         session: AsyncSession = Depends(get_session),
                         current_user: CurrentUser = Depends(get_current_user)):
    """Update channel meta. Moving a channel to another organization is restricted
    to Platform Admins."""
    if body.organization_id is not None:
        require(is_platform_admin(current_user), "only a platform admin can move a channel")
        import uuid as _uuid
        ch.organization_id = _uuid.UUID(str(body.organization_id))
    if body.display_name is not None:
        ch.display_name = body.display_name
    if body.category is not None:
        ch.category = body.category
    await session.commit()
    return {"channel_id": str(ch.id), "organization_id": str(ch.organization_id),
            "display_name": ch.display_name, "category": ch.category}


@router.delete("/{channel_id}", status_code=204)
async def delete_channel(channel_id: str,
                         ch: Channel = Depends(require_channel_access),
                         session: AsyncSession = Depends(get_session),
                         current_user: CurrentUser = Depends(get_current_user)):
    """Delete a channel — Platform Admin, or a user who can manage that channel's
    organization."""
    require(can_manage_channel(current_user, ch), "not allowed to delete this channel")
    await session.delete(ch)
    await session.commit()


@router.get("/{channel_id}/dashboard")
async def dashboard(channel_id: str, session: AsyncSession = Depends(get_session),
                    _auth: Channel = Depends(require_channel_access)):
    return await services.build_dashboard(session, channel_id)


@router.get("/{channel_id}/control")
async def control(channel_id: str, session: AsyncSession = Depends(get_session),
                  _auth: Channel = Depends(require_channel_access)):
    """Agent-centric live state for the Control Room (event stream + pipeline + system)."""
    return await services.build_control_state(session, channel_id)


@router.get("/{channel_id}/intelligence")
async def intelligence(channel_id: str, session: AsyncSession = Depends(get_session),
                       _auth: Channel = Depends(require_channel_access)):
    """Post/audience intelligence (virality, purpose mix, community signal) + retention plan."""
    return await services.get_intelligence(session, channel_id)


@router.get("/{channel_id}/subscribers")
async def subscribers(channel_id: str, n: int = Query(300, ge=1, le=2000),
                      session: AsyncSession = Depends(get_session),
                      _auth: Channel = Depends(require_channel_access)):
    """Live subscriber samples (every ~20 min) — the real, updating growth series."""
    return await services.get_subscriber_series(session, channel_id, n)


@router.get("/{channel_id}/analytics")
async def analytics(channel_id: str, snapshot_type: str = Query("daily"),
                    n: int = Query(30, ge=1, le=365), session: AsyncSession = Depends(get_session),
                    _auth: Channel = Depends(require_channel_access)):
    return await services.get_analytics(session, channel_id, snapshot_type, n)


@router.get("/{channel_id}/strategy")
async def strategy(channel_id: str, session: AsyncSession = Depends(get_session),
                   _auth: Channel = Depends(require_channel_access)):
    result = await services.get_strategy(session, channel_id)
    if result is None:
        raise HTTPException(status_code=404, detail="no active strategy")
    return result


@router.get("/{channel_id}/competitors")
async def competitors(channel_id: str, session: AsyncSession = Depends(get_session),
                      _auth: Channel = Depends(require_channel_access)):
    return await services.get_competitors(session, channel_id)


@router.patch("/{channel_id}/competitors/{competitor_key}/handle")
async def update_competitor_handle(
    channel_id: str,
    competitor_key: str,
    body: CompetitorHandleUpdate,
    session: AsyncSession = Depends(get_session),
    _auth: Channel = Depends(require_channel_access),
):
    """Update the Telegram handle for a market-only competitor."""
    import uuid as _uuid
    from db.models import Competitor as CompetitorModel

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
async def list_content_sources(channel_id: str, session: AsyncSession = Depends(get_session),
                               _auth: Channel = Depends(require_channel_access)):
    from tools.content_sources import list_sources
    return await list_sources(channel_id)


@router.post("/{channel_id}/sources", status_code=201)
async def add_content_source(channel_id: str, body: ContentSourceCreate,
                             session: AsyncSession = Depends(get_session),
                             _auth: Channel = Depends(require_channel_access)):
    from tools.content_sources import add_source
    try:
        return await add_source(channel_id, type=body.type, url=body.url, name=body.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/{channel_id}/sources/{source_id}")
async def patch_content_source(channel_id: str, source_id: str, body: ContentSourceUpdate,
                               session: AsyncSession = Depends(get_session),
                               _auth: Channel = Depends(require_channel_access)):
    from tools.content_sources import update_source
    res = await update_source(source_id, is_active=body.is_active, name=body.name, url=body.url)
    if not res.get("updated"):
        raise HTTPException(status_code=404, detail="source not found")
    return res


@router.delete("/{channel_id}/sources/{source_id}", status_code=204)
async def remove_content_source(channel_id: str, source_id: str,
                                session: AsyncSession = Depends(get_session),
                                _auth: Channel = Depends(require_channel_access)):
    from tools.content_sources import delete_source
    res = await delete_source(source_id)
    if not res.get("deleted"):
        raise HTTPException(status_code=404, detail="source not found")


@router.patch("/{channel_id}/settings")
async def patch_channel_settings(channel_id: str, body: ChannelSettingsUpdate,
                                 ch: Channel = Depends(require_channel_access),
                                 session: AsyncSession = Depends(get_session)):
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
async def get_channel_settings(channel_id: str, ch: Channel = Depends(require_channel_access)):
    return {
        "channel_id": str(ch.id),
        "auto_approve": ch.auto_approve,
        "score_threshold": ch.score_threshold,
    }


@router.post("/{channel_id}/sources/seed")
async def seed_content_sources(channel_id: str, ch: Channel = Depends(require_channel_access)):
    from tools.content_sources import seed_default_sources
    return await seed_default_sources(channel_id, ch.category)
