from datetime import datetime, timedelta, timezone
from typing import Any

from app.config.settings import settings
from app.database.repositories import MetricRepository, PostRepository, SubscriberRepository
from app.services.content_metrics_service import ContentMetricsService
from app.services.engagement_service import EngagementService
from app.services.feature_service import FeatureService
from app.services.growth_service import GrowthService
from app.services.performance_metrics_service import PerformanceMetricsService
from app.services.preprocessing_service import PreprocessingService
from app.services.reach_service import ReachService
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _within_window(posts: list, days: int) -> list:
    if not posts:
        return posts
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    windowed = [p for p in posts if p.timestamp and p.timestamp >= cutoff]
    return windowed or posts


def _mature(posts: list, hours: int) -> list:
    if not posts:
        return posts
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    mature = [p for p in posts if p.timestamp and p.timestamp <= cutoff]
    return mature or posts


class MetricsService:
    def __init__(self, session):
        self.post_repo = PostRepository(session)
        self.snapshot_repo = SubscriberRepository(session)
        self.metric_repo = MetricRepository(session)
        self.preprocessing_service = PreprocessingService(session)
        self.content_service = ContentMetricsService()
        self.reach_service = ReachService()
        self.engagement_service = EngagementService()
        self.performance_service = PerformanceMetricsService()
        self.growth_service = GrowthService()
        self.feature_service = FeatureService()

    async def process_channel(self, channel_id: int, subscribers: int) -> dict[str, Any]:
        await self.preprocessing_service.clean_channel_posts(channel_id)
        all_posts = await self.post_repo.get_by_channel(channel_id)
        snapshots = await self.snapshot_repo.get_by_channel(channel_id)

        # Bound the analysis to a recent window, then derive the "mature" subset
        # (views settled) for view-dependent metrics.
        posts = _within_window(all_posts, settings.LOOKBACK_DAYS)
        mature_posts = _mature(posts, settings.POST_MATURITY_HOURS)

        content_metrics = self.content_service.calculate(posts)
        reach_metrics = self.reach_service.calculate(mature_posts, subscribers)
        engagement_metrics = self.engagement_service.calculate(mature_posts, subscribers)
        performance_metrics = self.performance_service.calculate(mature_posts)
        growth_metrics = self.growth_service.calculate(snapshots)
        feature_record = self.feature_service.generate(
            content_metrics,
            reach_metrics,
            engagement_metrics,
            growth_metrics,
            performance_metrics,
        )

        content_payload = {
            "channel_id": channel_id,
            "total_posts": content_metrics["total_posts"],
            "posts_per_day": content_metrics["posts_per_day"],
            "posts_per_week": content_metrics["posts_per_week"],
            "posting_consistency": content_metrics["posting_consistency"],
            "posting_gaps": content_metrics["posting_gaps"],
            "content_mix": content_metrics["content_mix"],
            "avg_reach_rate": reach_metrics["average_reach_rate"],
            "median_reach_rate": reach_metrics["median_reach_rate"],
            "top_reach_rate": reach_metrics["top_reach_rate"],
            "bottom_reach_rate": reach_metrics["bottom_reach_rate"],
        }

        performance_payload = {
            "channel_id": channel_id,
            "average_views": performance_metrics["average_views"],
            "average_reactions": performance_metrics["average_reactions"],
            "average_forwards": performance_metrics["average_forwards"],
            "average_replies": performance_metrics["average_replies"],
            "reaction_rate": performance_metrics["reaction_rate"],
            "forward_rate": performance_metrics["forward_rate"],
            "reply_rate": performance_metrics["reply_rate"],
            "engagement_rate": performance_metrics["engagement_rate"],
            "top_posts": performance_metrics["top_posts"],
            "bottom_posts": performance_metrics["bottom_posts"],
        }

        growth_payload = {
            "channel_id": channel_id,
            "daily_growth": growth_metrics["daily_growth"],
            "weekly_growth": growth_metrics["weekly_growth"],
            "growth_rate": growth_metrics["growth_rate"],
            "growth_7_day": growth_metrics["growth_7_day"],
            "growth_30_day": growth_metrics["growth_30_day"],
            "growth_trend": growth_metrics["growth_trend"],
            "trend_points": growth_metrics["trend_points"],
        }

        feature_payload = {
            "channel_id": channel_id,
            "posts_per_day": feature_record["posts_per_day"],
            "avg_views": feature_record["avg_views"],
            "avg_reach_rate": feature_record["avg_reach_rate"],
            "avg_er": feature_record["avg_er"],
            "avg_err": feature_record["avg_err"],
            "growth_rate": feature_record["growth_rate"],
            "content_mix": feature_record["content_mix"],
            "top_er_posts": feature_record["top_ER_posts"],
            "top_err_posts": feature_record["top_ERR_posts"],
        }

        await self.metric_repo.upsert_content_metrics(content_payload)
        await self.metric_repo.upsert_performance_metrics(performance_payload)
        await self.metric_repo.upsert_growth_metrics(growth_payload)
        await self.metric_repo.upsert_channel_features(feature_payload)

        logger.info("Processed metrics for channel %s", channel_id)

        return {
            "content_metrics": content_metrics,
            "reach_metrics": reach_metrics,
            "engagement_metrics": engagement_metrics,
            "performance_metrics": performance_metrics,
            "growth_metrics": growth_metrics,
            "feature_record": feature_record,
        }
