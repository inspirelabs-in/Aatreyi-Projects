"""BaseAgent — common run lifecycle for every agent.

Subclasses implement `_execute(channel_id) -> dict`. BaseAgent wraps it with
agent_runs audit logging (start=running, end=completed/failed) and timing.
"""
from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from typing import Any

from tools.shared import log_agent_run


class BaseAgent(ABC):
    #: must match db.models.AgentName values
    name: str = "base"

    def __init__(self, trigger: str = "manual") -> None:
        #: one of db.models.AgentTrigger values
        self.trigger = trigger

    @abstractmethod
    async def _execute(self, channel_id: str, **kwargs) -> dict[str, Any]:
        """Do the agent's actual work and return a result dict."""

    async def run(self, channel_id: str, **kwargs) -> dict[str, Any]:
        run_id = uuid.uuid4()
        started = time.monotonic()
        await self._before_run(run_id, channel_id, kwargs)
        try:
            result = await self._execute(channel_id, **kwargs)
        except Exception as exc:  # noqa: BLE001 — log then re-raise
            await self._after_run(
                run_id,
                channel_id,
                status="failed",
                duration_ms=int((time.monotonic() - started) * 1000),
                error=f"{type(exc).__name__}: {exc}",
            )
            raise
        await self._after_run(
            run_id,
            channel_id,
            status="completed",
            duration_ms=int((time.monotonic() - started) * 1000),
            output_summary=self._summarize(result),
        )
        return result

    # ── lifecycle hooks ──────────────────────────────────────────────────────
    async def _before_run(self, run_id, channel_id, kwargs) -> None:
        await log_agent_run(
            channel_id=channel_id,
            agent=self.name,
            trigger=self.trigger,
            status="running",
            run_id=run_id,
            input_snapshot={"channel_id": str(channel_id), **_sanitize(kwargs)},
        )

    async def _after_run(
        self,
        run_id,
        channel_id,
        *,
        status: str,
        duration_ms: int,
        output_summary: dict | None = None,
        error: str | None = None,
    ) -> None:
        await log_agent_run(
            channel_id=channel_id,
            agent=self.name,
            trigger=self.trigger,
            status=status,
            run_id=run_id,
            output_summary=output_summary,
            duration_ms=duration_ms,
            error=error,
        )

    def _summarize(self, result: dict[str, Any]) -> dict[str, Any]:
        """Override to store a compact subset of the result in agent_runs."""
        return {k: v for k, v in result.items() if not isinstance(v, (list, dict))}


def _sanitize(d: dict[str, Any]) -> dict[str, Any]:
    """Keep only JSON-serialisable scalars from kwargs for the audit snapshot."""
    return {k: v for k, v in d.items() if isinstance(v, (str, int, float, bool))}
