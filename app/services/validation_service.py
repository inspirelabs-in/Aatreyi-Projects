from statistics import mean
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

MIN_POSTS_REQUIRED = 50


class ValidationService:
    def validate(
        self,
        channel_exists: bool,
        subscriber_count: int,
        posts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        logger.info("Running validation checks")
        result: dict[str, bool | int | str] = {}
        checks_passed = 0
        total_checks = 4

        # Check 1: Channel exists
        if channel_exists:
            result["channel_exists"] = True
            checks_passed += 1
            logger.info("CHECK 1/4 PASSED: Channel exists")
        else:
            result["channel_exists"] = False
            logger.error("CHECK 1/4 FAILED: Channel does not exist")

        # Check 2: Subscriber count available
        if subscriber_count > 0:
            result["subscriber_count"] = subscriber_count
            checks_passed += 1
            logger.info("CHECK 2/4 PASSED: Subscribers = %d", subscriber_count)
        else:
            result["subscriber_count"] = 0
            logger.error("CHECK 2/4 FAILED: No subscriber count")

        # Check 3: Minimum 50 posts
        post_count = len(posts)
        if post_count >= MIN_POSTS_REQUIRED:
            result["posts_collected"] = post_count
            result["minimum_posts_met"] = True
            checks_passed += 1
            logger.info("CHECK 3/4 PASSED: %d posts collected", post_count)
        else:
            result["posts_collected"] = post_count
            result["minimum_posts_met"] = False
            logger.error("CHECK 3/4 FAILED: Only %d posts (need %d)", post_count, MIN_POSTS_REQUIRED)

        # Check 4: Date range available
        timestamps = [p["timestamp"] for p in posts if p.get("timestamp")]
        if len(timestamps) >= 2:
            result["date_range_earliest"] = min(timestamps).strftime("%Y-%m-%d")
            result["date_range_latest"] = max(timestamps).strftime("%Y-%m-%d")
            checks_passed += 1
            logger.info("CHECK 4/4 PASSED: %s -> %s", result["date_range_earliest"], result["date_range_latest"])
        else:
            logger.error("CHECK 4/4 FAILED: Insufficient timestamp data")

        result["all_passed"] = checks_passed == total_checks
        return result
