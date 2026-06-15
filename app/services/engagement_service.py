from statistics import mean
from typing import Any

from app.database.models import Post
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _sum_reactions(reactions: Any) -> int:
    if not reactions:
        return 0
    if isinstance(reactions, list):
        return sum(int(item.get("count", 0) or 0) for item in reactions if isinstance(item, dict))
    return 0


def _normalize_rate(value: float) -> float:
    return round(max(0.0, value), 4)


class EngagementService:
    def calculate(self, posts: list[Post], subscribers: int) -> dict[str, Any]:
        if not posts:
            return {
                "avg_ER": 0.0,
                "avg_ERR": 0.0,
                "top_ER_posts": [],
                "top_ERR_posts": [],
            }

        er_values = []
        err_values = []
        er_ranking = []
        err_ranking = []

        for post in posts:
            reactions = _sum_reactions(post.reactions)
            engagement = reactions + (post.forwards or 0) + (post.reply_count or 0)
            er = (engagement / subscribers) * 100 if subscribers > 0 else 0.0
            err = (engagement / post.views) * 100 if (post.views or 0) > 0 else 0.0
            normalized_er = _normalize_rate(er)
            normalized_err = _normalize_rate(err)
            er_values.append(normalized_er)
            err_values.append(normalized_err)
            er_ranking.append({"post_id": post.post_id, "ER": normalized_er, "engagement": engagement})
            err_ranking.append({"post_id": post.post_id, "ERR": normalized_err, "engagement": engagement})

        top_ER_posts = sorted(er_ranking, key=lambda item: item["ER"], reverse=True)[:10]
        top_ERR_posts = sorted(err_ranking, key=lambda item: item["ERR"], reverse=True)[:10]

        metrics = {
            "avg_ER": _normalize_rate(mean(er_values)),
            "avg_ERR": _normalize_rate(mean(err_values)),
            "top_ER_posts": top_ER_posts,
            "top_ERR_posts": top_ERR_posts,
        }
        logger.info("Calculated engagement metrics for %d posts", len(posts))
        return metrics
