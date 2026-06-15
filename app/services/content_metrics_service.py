from collections import Counter
from datetime import timedelta
from typing import Any

from app.database.models import Post
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class ContentMetricsService:
    def calculate(self, posts: list[Post]) -> dict[str, Any]:
        dates = [post.timestamp.date() for post in posts if post.timestamp]
        total_posts = len(dates)
        if not dates:
            return {
                "total_posts": 0,
                "posts_per_day": 0.0,
                "posts_per_week": 0.0,
                "posting_consistency": 0.0,
                "posting_gaps": [],
                "content_mix": {},
            }

        start, end = min(dates), max(dates)
        span_days = (end - start).days + 1
        posts_per_day = total_posts / span_days
        # weekly rate is the daily rate extrapolated; never clamp the denominator,
        # which would over-report when fewer than 7 days of data exist.
        posts_per_week = posts_per_day * 7

        # Consistency = share of days in the window that had at least one post,
        # expressed 0-100 (100 = posted every single day). The previous code used
        # raw stdev of per-day counts, which is unbounded and inversely related to
        # consistency (higher stdev = less consistent), so it was both unscaled and
        # backwards.
        active_days = len(set(dates))
        posting_consistency = round(active_days / span_days * 100, 4)

        # Gaps = number of empty days between consecutive active days (0 = posted
        # on back-to-back days). Previously this stored the raw day delta, so
        # consecutive days showed "1" instead of "0".
        sorted_dates = sorted(set(dates))
        posting_gaps = [(second - first).days - 1 for first, second in zip(sorted_dates, sorted_dates[1:])]

        content_mix = Counter(
            post.media_type.lower() if isinstance(post.media_type, str) else "other"
            for post in posts
        )

        metrics = {
            "total_posts": total_posts,
            "posts_per_day": round(posts_per_day, 4),
            "posts_per_week": round(posts_per_week, 4),
            "posting_consistency": posting_consistency,
            "posting_gaps": posting_gaps,
            "content_mix": {
                "text": content_mix.get("text", 0),
                "image": content_mix.get("image", 0),
                "video": content_mix.get("video", 0),
                "poll": content_mix.get("poll", 0),
                "link": content_mix.get("link", 0),
                "document": content_mix.get("document", 0),
                "other": content_mix.get("other", 0),
            },
        }
        logger.info("Calculated content metrics for %d posts", len(posts))
        return metrics
