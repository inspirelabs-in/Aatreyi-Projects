"""Review-queue endpoints + manual agent trigger."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.db import get_session
from api.schemas import EditPost, RejectPost, RunAgent
from api import services
from tools.content import get_review_queue, publish_generated_post, update_review_status

router = APIRouter(prefix="/api/channels", tags=["review"])
log = logging.getLogger("api.review")

# Tracks running agent tasks so they can be cancelled.
# Key: "{channel_id}:{short_agent_name}" — short names match KNOWN_AGENTS.
_active_tasks: dict[str, asyncio.Task] = {}

# Maps full AgentName enum values (used in pipeline UI) to KNOWN_AGENTS short names.
_AGENT_ALIAS: dict[str, str] = {
    "channel_dna": "dna",
    "competitor_intelligence": "competitor",
    "content_intelligence": "content",
    "analytics": "analytics",
    "strategy": "strategy",
    "onboard": "onboard",
}


async def _run_agent_bg(key: str, channel_id: str, username: str | None, agent: str,
                        snapshot_type: str, task_id: str | None, with_telegram: bool) -> None:
    """Execute an agent run. Removes itself from _active_tasks when done."""
    try:
        await services.run_agent(channel_id, username, agent, snapshot_type=snapshot_type,
                                 task_id=task_id, with_telegram=with_telegram)
    except asyncio.CancelledError:
        log.info("agent run %s/%s cancelled by user", agent, channel_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("agent run %s/%s failed: %s: %s", agent, channel_id, type(exc).__name__, exc)
    finally:
        _active_tasks.pop(key, None)


@router.get("/{channel_id}/queue")
async def queue(channel_id: str, session: AsyncSession = Depends(get_session)):
    await _require(session, channel_id)
    return await services.get_queue(session, channel_id)


@router.post("/{channel_id}/queue/{post_id}/approve")
async def approve(channel_id: str, post_id: str, session: AsyncSession = Depends(get_session)):
    channel = await _require(session, channel_id)
    res = await update_review_status(post_id, "approved")
    if not res.get("updated"):
        raise HTTPException(status_code=404, detail="post not found")
    pub = await publish_generated_post(post_id, channel.telegram_username)
    out: dict = {"post_id": post_id, "review_status": "approved",
                 "published": bool(pub.get("published"))}
    if pub.get("published"):
        out["telegram_message_id"] = pub.get("telegram_message_id")
    elif pub.get("error") == "BOT_TOKEN not set":
        out["note"] = "publishing deferred until BOT_TOKEN is set"
    else:
        out["publish_error"] = pub.get("error")
    return out


@router.post("/{channel_id}/queue/{post_id}/reject")
async def reject(channel_id: str, post_id: str, body: RejectPost | None = None,
                 session: AsyncSession = Depends(get_session)):
    await _require(session, channel_id)
    res = await update_review_status(post_id, "rejected")
    if not res.get("updated"):
        raise HTTPException(status_code=404, detail="post not found")
    return {"post_id": post_id, "review_status": "rejected", "reason": body.reason if body else None}


@router.put("/{channel_id}/queue/{post_id}")
async def edit(channel_id: str, post_id: str, body: EditPost,
               session: AsyncSession = Depends(get_session)):
    await _require(session, channel_id)
    res = await update_review_status(post_id, "edited", edited_text=body.edited_text)
    if not res.get("updated"):
        raise HTTPException(status_code=404, detail="post not found")
    return {"post_id": post_id, "review_status": "edited"}


@router.post("/{channel_id}/agents/run", status_code=202)
async def run_agent(channel_id: str, body: RunAgent,
                    session: AsyncSession = Depends(get_session)):
    """Kick off an agent run in the background and return immediately."""
    channel = await _require(session, channel_id)
    if body.agent not in services.KNOWN_AGENTS:
        raise HTTPException(status_code=400, detail=f"unknown agent {body.agent!r}")
    if body.agent == "content" and not body.task_id:
        raise HTTPException(status_code=400, detail="content agent requires task_id")
    key = f"{channel_id}:{body.agent}"
    if key in _active_tasks and not _active_tasks[key].done():
        return {"agent": body.agent, "status": "already_running"}
    task = asyncio.create_task(
        _run_agent_bg(key, str(channel.id), channel.telegram_username,
                      body.agent, body.snapshot_type, body.task_id, body.with_telegram)
    )
    _active_tasks[key] = task
    return {"agent": body.agent, "status": "started"}


@router.post("/{channel_id}/agents/cancel", status_code=200)
async def cancel_agent(channel_id: str, body: RunAgent,
                       session: AsyncSession = Depends(get_session)):
    """Cancel a running agent for this channel.

    Accepts both short names ('competitor') and full enum names
    ('competitor_intelligence') so the UI pipeline card can pass p.agent directly.
    Also clears zombie 'running' DB records left by container restarts.
    """
    from datetime import datetime, timezone
    from db.models import AgentRun, AgentName, RunStatus
    from sqlalchemy import select, update

    await _require(session, channel_id)
    short = _AGENT_ALIAS.get(body.agent, body.agent)
    key = f"{channel_id}:{short}"

    # Cancel the live asyncio task if present.
    task = _active_tasks.pop(key, None)
    if task and not task.done():
        task.cancel()

    # Always clear zombie 'running' DB records for this channel+agent —
    # container restarts kill tasks without updating their DB status.
    try:
        agent_enum_val = body.agent  # full or short name
        # Map short → full enum name for DB lookup
        _SHORT_TO_FULL = {v: k for k, v in _AGENT_ALIAS.items()}
        full_name = _SHORT_TO_FULL.get(agent_enum_val, agent_enum_val)
        import uuid
        cid = uuid.UUID(channel_id)
        await session.execute(
            update(AgentRun)
            .where(
                AgentRun.channel_id == cid,
                AgentRun.agent == AgentName(full_name),
                AgentRun.status == RunStatus.running,
            )
            .values(
                status=RunStatus.failed,
                error="Cancelled by user",
                finished_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()
    except Exception as exc:
        log.warning("cancel: failed to clear DB run record: %s", exc)

    return {"agent": body.agent, "status": "cancelled"}


async def _require(session: AsyncSession, channel_id: str):
    ch = await services.get_channel_or_none(session, channel_id)
    if ch is None:
        raise HTTPException(status_code=404, detail="channel not found")
    return ch
