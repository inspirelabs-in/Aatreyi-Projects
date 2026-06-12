import asyncio
from datetime import datetime
from typing import Any

from app.services.storage_service import StorageService

logger = setup_logger(__name__)


async def build_channel_context(channel_username: str, client: Any) -> dict[str, Any]:
    resolved = await resolve_channel(client, channel_username)
    from telethon.tl.types import InputPeerChannel

    entity = await client.get_entity(
        InputPeerChannel(
            channel_id=resolved["channel_id"],
            access_hash=resolved["access_hash"],
        )
    )

    posts = await fetch_posts(client, entity)
    subscriber_service = SubscriberService(client)
    subscriber_count = await subscriber_service.collect(entity)
    metadata_service = MetadataService(client)
    metadata = await metadata_service.collect(entity, resolved)

    content_metrics = MetricsService.calculate_content_metrics(posts, metadata["channel_id"], subscriber_count)
    performance_metrics = MetricsService.calculate_performance_metrics(posts, subscriber_count, metadata["channel_id"])

    async with AsyncSessionLocal() as session:
        storage = StorageService(session)
        await storage.save_channel(
            {
                "channel_id": metadata["channel_id"],
                "title": metadata["title"],
                "username": metadata["username"],
                "description": metadata.get("description", ""),
                "created_at": metadata.get("created_at"),
                "verified": metadata.get("verified", False),
                "public_channel": metadata.get("public_channel", True),
                "subscriber_count": subscriber_count,
            }
        )
        await storage.save_posts(
            [
                {
                    "message_id": p["message_id"],
                    "channel_id": p["channel_id"],
                    "text": p["text"],
                    "media_type": p["media_type"],
                    "timestamp": p["timestamp"],
                    "views": p["views"],
                    "forwards": p["forwards"],
                    "reactions": p["reactions"],
                    "reply_count": p["reply_count"],
                    "has_link": p.get("has_link", False),
                    "link_url": p.get("link_url"),
                    "is_affiliate": p.get("is_affiliate", False),
                }
                for p in posts
            ]
        )
        await storage.save_snapshot(metadata["channel_id"], subscriber_count)

    return {
        "channel_metadata": metadata,
        "subscriber_count": subscriber_count,
        "posts": posts,
        "content_metrics": content_metrics,
        "performance_metrics": performance_metrics,
        "collected_at": datetime.utcnow().isoformat(),
    }


def assemble_report(
    channel_username: str,
    context: dict[str, Any],
    channel_profile: str,
    audience_profile: str,
    content_intelligence: str,
    competitor_intelligence: str,
    benchmark_results: str,
    growth_analysis: str,
    retention_analysis: str,
    alerts: str,
    recommendations: str,
    outcome_tracking: str,
) -> dict[str, Any]:
    return {
        "channel_username": channel_username,
        "generated_at": datetime.utcnow().isoformat(),
        "summary": {
            "channel_profile": channel_profile,
            "audience_profile": audience_profile,
            "content_intelligence": content_intelligence,
            "competitor_intelligence": competitor_intelligence,
            "benchmark_results": benchmark_results,
            "growth_analysis": growth_analysis,
            "retention_analysis": retention_analysis,
            "alerts": alerts,
            "recommendations": recommendations,
            "outcome_tracking": outcome_tracking,
        },
        "raw_context": {
            "metadata": context["channel_metadata"],
            "metrics": context["content_metrics"],
        },
    }


async def run_analysis_pipeline(channel_username: str, operator_goal: str | None = None) -> dict[str, Any]:
    await init_db()
    client = await get_telegram_client()
    await authenticate(client)

    try:
        context = await build_channel_context(channel_username, client)
        if operator_goal:
            context["operator_stated_goal"] = operator_goal

        async with AsyncSessionLocal() as session:
            result_repo = AnalysisResultRepository(session)

            async def save_stage(stage_name: str, payload: Any) -> None:
                await result_repo.save_result(
                    channel_username=channel_username,
                    stage=stage_name,
                    payload={"raw": payload},
                    channel_id=context["channel_metadata"]["channel_id"],
                )

            channel_profile_raw = run_prompt("channel_classification", context)
            await save_stage("channel_classification", channel_profile_raw)

            audience_profile_raw = run_prompt(
                "audience_intelligence",
                {**context, "channel_profile": channel_profile_raw},
            )
            await save_stage("audience_intelligence", audience_profile_raw)

            content_intelligence_raw = run_prompt(
                "content_intelligence",
                {**context, "channel_profile": channel_profile_raw, "audience_profile": audience_profile_raw},
            )
            await save_stage("content_intelligence", content_intelligence_raw)

            competitor_intelligence_raw = run_prompt(
                "competitor_intelligence",
                {**context, "channel_profile": channel_profile_raw, "content_intelligence": content_intelligence_raw},
            )
            await save_stage("competitor_intelligence", competitor_intelligence_raw)

            benchmark_raw = run_prompt(
                "benchmark_engine",
                {**context, "competitor_intelligence": competitor_intelligence_raw},
            )
            await save_stage("benchmark_engine", benchmark_raw)

            growth_raw = run_prompt(
                "growth_analysis",
                {
                    **context,
                    "channel_profile": channel_profile_raw,
                    "content_intelligence": content_intelligence_raw,
                    "competitor_intelligence": competitor_intelligence_raw,
                    "benchmark_results": benchmark_raw,
                },
            )
            await save_stage("growth_analysis", growth_raw)

            retention_raw = run_prompt(
                "retention_analysis",
                {
                    **context,
                    "channel_profile": channel_profile_raw,
                    "content_intelligence": content_intelligence_raw,
                    "competitor_intelligence": competitor_intelligence_raw,
                    "benchmark_results": benchmark_raw,
                    "growth_analysis": growth_raw,
                },
            )
            await save_stage("retention_analysis", retention_raw)

            alert_raw = run_prompt(
                "alert_generation",
                {
                    **context,
                    "channel_profile": channel_profile_raw,
                    "content_intelligence": content_intelligence_raw,
                    "competitor_intelligence": competitor_intelligence_raw,
                    "benchmark_results": benchmark_raw,
                    "growth_analysis": growth_raw,
                    "retention_analysis": retention_raw,
                },
            )
            await save_stage("alert_generation", alert_raw)

            recommendation_raw = run_prompt(
                "recommendation_generation",
                {
                    **context,
                    "channel_profile": channel_profile_raw,
                    "audience_profile": audience_profile_raw,
                    "content_intelligence": content_intelligence_raw,
                    "competitor_intelligence": competitor_intelligence_raw,
                    "benchmark_results": benchmark_raw,
                    "growth_analysis": growth_raw,
                    "retention_analysis": retention_raw,
                    "alerts": alert_raw,
                },
            )
            await save_stage("recommendation_generation", recommendation_raw)

            outcome_tracking_raw = run_prompt(
                "outcome_tracking",
                {
                    **context,
                    "recommendations": recommendation_raw,
                    "content_intelligence": content_intelligence_raw,
                    "growth_analysis": growth_raw,
                    "retention_analysis": retention_raw,
                },
            )
            await save_stage("outcome_tracking", outcome_tracking_raw)

            report = assemble_report(
                channel_username=channel_username,
                context=context,
                channel_profile=channel_profile_raw,
                audience_profile=audience_profile_raw,
                content_intelligence=content_intelligence_raw,
                competitor_intelligence=competitor_intelligence_raw,
                benchmark_results=benchmark_raw,
                growth_analysis=growth_raw,
                retention_analysis=retention_raw,
                alerts=alert_raw,
                recommendations=recommendation_raw,
                outcome_tracking=outcome_tracking_raw,
            )
            await save_stage("report_assembly", report)

        return {
            "channel_profile": channel_profile_raw,
            "audience_profile": audience_profile_raw,
            "content_intelligence": content_intelligence_raw,
            "competitor_intelligence": competitor_intelligence_raw,
            "benchmark_results": benchmark_raw,
            "growth_analysis": growth_raw,
            "retention_analysis": retention_raw,
                    "alerts": alert_raw,
                    "recommendations": recommendation_raw,
                    "outcome_tracking": outcome_tracking_raw,
                    "report": report,
                }
    finally:
        await client.disconnect()
        logger.info("Channel analysis pipeline finished for %s", channel_username)


async def run_registered_channel_analysis() -> list[dict[str, Any]]:
    await init_db()
    client = await get_telegram_client()
    await authenticate(client)

    results: list[dict[str, Any]] = []
    try:
        async with AsyncSessionLocal() as session:
            repo = RegisteredChannelRepository(session)
            channels = await repo.get_active_channels()

        for channel in channels:
            try:
                result = await run_analysis_pipeline(channel.channel_username)
                results.append(result)
                async with AsyncSessionLocal() as update_session:
                    update_repo = RegisteredChannelRepository(update_session)
                    await update_repo.update_last_run_at(channel.channel_username, datetime.utcnow())
            except Exception as exc:
                logger.error("Failed analysis for %s: %s", channel.channel_username, exc)
        return results
    finally:
        await client.disconnect()


async def run_registered_channel_analysis() -> list[dict[str, Any]]:
    await init_db()
    client = await get_telegram_client()
    await authenticate(client)

    results: list[dict[str, Any]] = []
    try:
        async with AsyncSessionLocal() as session:
            repo = RegisteredChannelRepository(session)
            channels = await repo.get_active_channels()

        for channel in channels:
            try:
                result = await run_analysis_pipeline(channel.channel_username)
                results.append(result)
                async with AsyncSessionLocal() as update_session:
                    update_repo = RegisteredChannelRepository(update_session)
                    await update_repo.update_last_run_at(channel.channel_username, datetime.utcnow())
            except Exception as exc:
                logger.error("Failed analysis for %s: %s", channel.channel_username, exc)
        return results
    finally:
        await client.disconnect()
