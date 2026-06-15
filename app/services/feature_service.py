from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class FeatureService:
    def generate(
        self,
        content_metrics: dict[str, Any],
        reach_metrics: dict[str, Any],
        engagement_metrics: dict[str, Any],
        growth_metrics: dict[str, Any],
        performance_metrics: dict[str, Any],
    ) -> dict[str, Any]:
        features = {
            "posts_per_day": content_metrics.get("posts_per_day", 0.0),
            "avg_views": performance_metrics.get("average_views", 0.0) or 0.0,
            "avg_reach_rate": reach_metrics.get("average_reach_rate", 0.0),
            "avg_er": engagement_metrics.get("avg_ER", 0.0),
            "avg_err": engagement_metrics.get("avg_ERR", 0.0),
            "growth_rate": growth_metrics.get("growth_rate", 0.0),
            "content_mix": content_metrics.get("content_mix", {}),
            "top_ER_posts": [post["post_id"] for post in engagement_metrics.get("top_ER_posts", [])],
            "top_ERR_posts": [post["post_id"] for post in engagement_metrics.get("top_ERR_posts", [])],
        }
        logger.info("Generated channel feature record")
        return features
