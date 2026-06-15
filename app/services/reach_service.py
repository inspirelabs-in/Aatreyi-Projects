from statistics import mean, median
from typing import Any

from app.database.models import Post
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _normalize_rate(value: float) -> float:
    return round(max(0.0, value), 4)


class ReachService:
    def calculate(self, posts: list[Post], subscribers: int) -> dict[str, Any]:
        if subscribers <= 0 or not posts:
            return {
                "average_reach_rate": 0.0,
                "median_reach_rate": 0.0,
                "top_reach_rate": 0.0,
                "bottom_reach_rate": 0.0,
                "reach_rates": [],
            }

        reach_rates = []
        for post in posts:
            rate = (post.views / subscribers) * 100 if post.views is not None else 0.0
            reach_rates.append(_normalize_rate(rate))

        metrics = {
            "average_reach_rate": _normalize_rate(mean(reach_rates)),
            "median_reach_rate": _normalize_rate(median(reach_rates)),
            "top_reach_rate": _normalize_rate(max(reach_rates)),
            "bottom_reach_rate": _normalize_rate(min(reach_rates)),
            "reach_rates": reach_rates,
        }
        logger.info("Calculated reach metrics for %d posts", len(posts))
        return metrics
