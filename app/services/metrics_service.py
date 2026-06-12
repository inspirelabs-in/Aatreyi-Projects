from datetime import datetime, timedelta
from typing import Any, Dict, List

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class MetricsService:
    """
    Calculate channel and content metrics from raw post data.
    Uses mathematical formulas only.
    """

    @staticmethod
    def calculate_content_metrics(posts: List[Dict[str, Any]], channel_id: int, subscriber_count: int) -> Dict[str, Any]:
        """
        Calculate content metrics from posts.
        
        Args:
            posts: List of post dictionaries with timestamp, views, reactions, etc.
            channel_id: Channel ID for reference
            
        Returns:
            Dictionary with content metrics
        """
        if not posts:
            logger.warning("No posts provided for channel %s", channel_id)
            return {
                "channel_id": channel_id,
                "total_posts": 0,
                "posts_per_day": 0,
                "posts_per_week": 0,
                "total_views": 0,
                "avg_views": 0,
                "median_views": 0,
                "view_rate": 0,
                "total_reactions": 0,
                "avg_reactions": 0,
                "total_forwards": 0,
                "avg_forwards": 0,
                "total_replies": 0,
                "avg_replies": 0,
                "content_mix": {},
                "content_type_performance": {},
                "top_posts": [],
                "bottom_posts": [],
                "period_start": None,
                "period_end": None,
            }

        total_posts = len(posts)
        
        # Period calculation
        timestamps = [p.get("timestamp") for p in posts if p.get("timestamp")]
        if timestamps:
            period_start = min(timestamps)
            period_end = max(timestamps)
            days_span = max((period_end - period_start).days, 1)
        else:
            period_start = None
            period_end = None
            days_span = 1

        # Publishing metrics
        posts_per_day = total_posts / days_span
        posts_per_week = posts_per_day * 7

        # Reach metrics
        views = [p.get("views", 0) for p in posts]
        total_views = sum(views)
        avg_views = total_views / total_posts if total_posts else 0
        median_views = MetricsService._calculate_median(views)
        view_rate = round((avg_views / max(subscriber_count, 1)) * 100, 2)

        # Engagement metrics
        total_reactions = sum(MetricsService._count_reactions(p.get("reactions")) for p in posts)
        avg_reactions = total_reactions / total_posts if total_posts else 0
        total_forwards = sum(p.get("forwards", 0) for p in posts)
        avg_forwards = total_forwards / total_posts if total_posts else 0
        total_replies = sum(p.get("reply_count", 0) for p in posts)
        avg_replies = total_replies / total_posts if total_posts else 0

        # Rates
        reaction_rate = round((avg_reactions / max(avg_views, 0.01)) * 100, 2)
        forward_rate = round((avg_forwards / max(avg_views, 0.01)) * 100, 2)
        reply_rate = round((avg_replies / max(avg_views, 0.01)) * 100, 2)
        er = round(((avg_reactions + avg_forwards + avg_replies) / max(avg_views, 0.01)) * 100, 2)

        content_mix = MetricsService._calculate_content_mix(posts)
        content_type_performance = MetricsService._calculate_content_type_performance(posts)
        top_posts = MetricsService._get_top_posts(posts)
        bottom_posts = MetricsService._get_bottom_posts(posts)

        logger.info(
            "Content metrics for channel %s: %d posts, %.1f posts/day, %.0f avg views",
            channel_id, total_posts, posts_per_day, avg_views
        )

        return {
            "channel_id": channel_id,
            "total_posts": total_posts,
            "posts_per_day": round(posts_per_day, 2),
            "posts_per_week": round(posts_per_week, 2),
            "total_views": total_views,
            "avg_views": round(avg_views),
            "median_views": round(median_views),
            "view_rate": view_rate,
            "total_reactions": total_reactions,
            "avg_reactions": round(avg_reactions, 2),
            "total_forwards": total_forwards,
            "avg_forwards": round(avg_forwards, 2),
            "total_replies": total_replies,
            "avg_replies": round(avg_replies, 2),
            "reaction_rate": reaction_rate,
            "forward_rate": forward_rate,
            "reply_rate": reply_rate,
            "er": er,
            "content_mix": content_mix,
            "content_type_performance": content_type_performance,
            "top_posts": top_posts,
            "bottom_posts": bottom_posts,
            "period_start": period_start,
            "period_end": period_end,
        }

    @staticmethod
    def calculate_performance_metrics(
        posts: List[Dict[str, Any]], 
        subscriber_count: int,
        channel_id: int
    ) -> Dict[str, Any]:
        """
        Calculate performance/engagement metrics from posts.
        
        Args:
            posts: List of post dictionaries
            subscriber_count: Current subscriber count
            channel_id: Channel ID for reference
            
        Returns:
            Dictionary with performance metrics
        """
        if not posts:
            logger.warning("No posts provided for performance metrics calculation, channel %s", channel_id)
            return {
                "channel_id": channel_id,
                "view_rate": 0,
                "engagement_rate": 0,
                "reaction_rate": 0,
                "forward_rate": 0,
                "reply_rate": 0,
                "er": 0,
                "total_views": 0,
                "total_reactions": 0,
                "total_forwards": 0,
                "total_replies": 0,
                "period_start": None,
                "period_end": None,
            }

        total_posts = len(posts)
        
        # Period
        timestamps = [p.get("timestamp") for p in posts if p.get("timestamp")]
        period_start = min(timestamps) if timestamps else None
        period_end = max(timestamps) if timestamps else None

        # Totals
        total_views = sum(p.get("views", 0) for p in posts)
        total_reactions = sum(MetricsService._count_reactions(p.get("reactions")) for p in posts)
        total_forwards = sum(p.get("forwards", 0) for p in posts)
        total_replies = sum(p.get("reply_count", 0) for p in posts)

        # Averages
        avg_views = total_views / total_posts if total_posts > 0 else 0
        avg_reactions = total_reactions / total_posts if total_posts > 0 else 0
        avg_forwards = total_forwards / total_posts if total_posts > 0 else 0
        avg_replies = total_replies / total_posts if total_posts > 0 else 0

        # Engagement rates (as percentages)
        view_rate = round((avg_views / max(subscriber_count, 1)) * 100, 2)
        reaction_rate = round((avg_reactions / max(avg_views, 0.01)) * 100, 2)
        forward_rate = round((avg_forwards / max(avg_views, 0.01)) * 100, 2)
        reply_rate = round((avg_replies / max(avg_views, 0.01)) * 100, 2)
        er = round(((avg_reactions + avg_forwards + avg_replies) / max(avg_views, 0.01)) * 100, 2)

        logger.info(
            "Performance metrics for channel %s: er=%.2f%%, reaction_rate=%.2f%%, forward_rate=%.2f%%",
            channel_id, er, reaction_rate, forward_rate
        )

        return {
            "channel_id": channel_id,
            "view_rate": view_rate,
            "engagement_rate": er,
            "reaction_rate": reaction_rate,
            "forward_rate": forward_rate,
            "reply_rate": reply_rate,
            "er": er,
            "total_views": total_views,
            "total_reactions": total_reactions,
            "total_forwards": total_forwards,
            "total_replies": total_replies,
            "period_start": period_start,
            "period_end": period_end,
        }

    @staticmethod
    def _calculate_content_mix(posts: List[Dict[str, Any]]) -> Dict[str, float]:
        """
        Calculate percentage distribution of content types.
        Formula: (count_of_type / total_posts) * 100
        """
        if not posts:
            return {}

        media_types = {}
        for post in posts:
            media_type = (post.get("media_type") or "text").lower()
            media_types[media_type] = media_types.get(media_type, 0) + 1

        total = len(posts)
        content_mix = {}
        for media_type, count in media_types.items():
            percentage = (count / total) * 100
            content_mix[media_type] = round(percentage, 2)

        return content_mix

    @staticmethod
    def _calculate_content_type_performance(posts: List[Dict[str, Any]]) -> Dict[str, float]:
        """
        Calculate avg views per content type.
        """
        if not posts:
            return {}

        totals: dict[str, int] = {}
        counts: dict[str, int] = {}
        for post in posts:
            media_type = (post.get("media_type") or "text").lower()
            views = post.get("views", 0)
            totals[media_type] = totals.get(media_type, 0) + views
            counts[media_type] = counts.get(media_type, 0) + 1

        result: dict[str, float] = {}
        for media_type, total_views in totals.items():
            result[media_type] = round(total_views / max(counts[media_type], 1), 2)

        return result

    @staticmethod
    def _to_json_safe_post(post: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert a post dictionary into JSON-safe values for storage.
        """
        timestamp = post.get("timestamp")
        if hasattr(timestamp, "isoformat"):
            timestamp = timestamp.isoformat()

        return {
            "message_id": int(post.get("message_id", 0)),
            "views": int(post.get("views", 0)),
            "text": str(post.get("text", "")) if post.get("text") is not None else "",
            "timestamp": timestamp,
        }

    @staticmethod
    def _get_top_posts(posts: List[Dict[str, Any]], limit: int = 10) -> List[Dict[str, Any]]:
        """
        Return top posts sorted by views.
        """
        sorted_posts = sorted(posts, key=lambda p: p.get("views", 0), reverse=True)
        return [MetricsService._to_json_safe_post(p) for p in sorted_posts[:limit]]

    @staticmethod
    def _get_bottom_posts(posts: List[Dict[str, Any]], limit: int = 10) -> List[Dict[str, Any]]:
        """
        Return bottom posts sorted by views.
        """
        sorted_posts = sorted(posts, key=lambda p: p.get("views", 0))
        return [MetricsService._to_json_safe_post(p) for p in sorted_posts[:limit]]

    @staticmethod
    def _calculate_average(posts: List[Dict[str, Any]], key: str) -> float:
        """
        Calculate average of a numeric field across all posts.
        Formula: sum(field_values) / total_posts
        """
        if not posts:
            return 0.0

        values = [p.get(key, 0) for p in posts]
        total = sum(values)
        return total / len(posts) if posts else 0.0

    @staticmethod
    def _calculate_median(values: List[int]) -> float:
        """
        Calculate median of a numeric list.
        """
        if not values:
            return 0.0

        sorted_values = sorted(values)
        n = len(sorted_values)
        mid = n // 2

        if n % 2 == 1:
            return float(sorted_values[mid])
        return (sorted_values[mid - 1] + sorted_values[mid]) / 2.0

    @staticmethod
    def _calculate_average_reactions(posts: List[Dict[str, Any]]) -> float:
        """
        Calculate average reaction count across all posts.
        Reactions are stored as JSON, so we count total reactions.
        """
        if not posts:
            return 0.0

        total_reactions = sum(MetricsService._count_reactions(p.get("reactions")) for p in posts)
        return total_reactions / len(posts) if posts else 0.0

    @staticmethod
    def _count_reactions(reactions: Any) -> int:
        """
        Count total reactions from reactions JSON.
        Reactions can be a dict like {"❤️": 5, "👍": 3, ...}
        """
        if not reactions:
            return 0

        if isinstance(reactions, dict):
            return sum(reactions.values())
        elif isinstance(reactions, (int, float)):
            return int(reactions)
        else:
            return 0

    @staticmethod
    def generate_summary(
        content_metrics: Dict[str, Any],
        performance_metrics: Dict[str, Any],
        subscriber_count: int,
    ) -> Dict[str, Any]:
        """
        Generate a summary report combining content and performance metrics.
        """
        return {
            "content": content_metrics,
            "performance": performance_metrics,
            "summary": {
                "subscribers": subscriber_count,
                "total_posts": content_metrics.get("total_posts", 0),
                "posts_per_day": content_metrics.get("posts_per_day", 0),
                "avg_views": content_metrics.get("avg_views", 0),
                "median_views": content_metrics.get("median_views", 0),
                "view_rate": content_metrics.get("view_rate", 0),
                "er": content_metrics.get("er", 0),
                "reaction_rate": content_metrics.get("reaction_rate", 0),
                "forward_rate": content_metrics.get("forward_rate", 0),
                "reply_rate": content_metrics.get("reply_rate", 0),
                "content_mix": content_metrics.get("content_mix", {}),
                "top_posts": content_metrics.get("top_posts", []),
                "bottom_posts": content_metrics.get("bottom_posts", []),
            },
        }
