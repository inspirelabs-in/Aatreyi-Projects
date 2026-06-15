from collections import Counter
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


class PerformanceMetricsService:
    def calculate(self, posts: list[Post]) -> dict[str, Any]:
        if not posts:
            return {
                "average_views": 0.0,
                "average_reactions": 0.0,
                "average_forwards": 0.0,
                "average_replies": 0.0,
                "reaction_rate": 0.0,
                "forward_rate": 0.0,
                "reply_rate": 0.0,
                "engagement_rate": 0.0,
                "top_posts": [],
                "bottom_posts": [],
            }

        total_views = 0
        total_reactions = 0
        total_forwards = 0
        total_replies = 0
        scored_posts = []

        for post in posts:
            views = int(post.views or 0)
            forwards = int(post.forwards or 0)
            replies = int(post.reply_count or 0)
            reactions = _sum_reactions(post.reactions)
            total_views += views
            total_reactions += reactions
            total_forwards += forwards
            total_replies += replies
            engagement = reactions + forwards + replies
            scored_posts.append(
                {
                    "post_id": post.post_id,
                    "views": views,
                    "reactions": reactions,
                    "forwards": forwards,
                    "replies": replies,
                    "engagement": engagement,
                    "timestamp": post.timestamp.isoformat() if post.timestamp else None,
                }
            )

        post_count = len(posts)
        top_posts = sorted(scored_posts, key=lambda item: item["engagement"], reverse=True)[:10]
        bottom_posts = sorted(scored_posts, key=lambda item: item["engagement"])[:10]

        # Rates are aggregate (sum of interactions / sum of views), i.e. weighted by
        # views. This is more representative than averaging per-post ratios, which
        # over-weights low-view posts. Denominator is total views (reach), so these
        # answer "of the people who saw a post, what fraction reacted/forwarded/replied".
        total_engagement = total_reactions + total_forwards + total_replies
        reaction_rate = round(total_reactions / total_views * 100, 4) if total_views > 0 else 0.0
        forward_rate = round(total_forwards / total_views * 100, 4) if total_views > 0 else 0.0
        reply_rate = round(total_replies / total_views * 100, 4) if total_views > 0 else 0.0
        engagement_rate = round(total_engagement / total_views * 100, 4) if total_views > 0 else 0.0

        metrics = {
            "average_views": round(total_views / post_count, 4),
            "average_reactions": round(total_reactions / post_count, 4),
            "average_forwards": round(total_forwards / post_count, 4),
            "average_replies": round(total_replies / post_count, 4),
            "reaction_rate": reaction_rate,
            "forward_rate": forward_rate,
            "reply_rate": reply_rate,
            "engagement_rate": engagement_rate,
            "top_posts": top_posts,
            "bottom_posts": bottom_posts,
        }
        logger.info("Calculated performance metrics for %d posts", post_count)
        return metrics
