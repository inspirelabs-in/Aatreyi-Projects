from datetime import datetime
from statistics import mean
from typing import Any


from app.config.constants import SUMMARY_SEPARATOR
from app.utils.exceptions import ValidationError
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class ValidationService:
    def __init__(self):
        self.results: dict[str, Any] = {}

    async def validate(
        self,
        channel_data: dict[str, Any],
        subscriber_count: int | None,
        posts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        logger.info("Running Validation Checks")
        all_passed = True

        if not channel_data or not channel_data.get("channel_id"):
            self.results["channel_exists"] = False
            all_passed = False
            logger.error("Validation Check 1 FAILED: Channel does not exist")
        else:
            self.results["channel_exists"] = True
            logger.info("Validation Check 1 PASSED: Channel exists")

        self.results["subscriber_count"] = subscriber_count or 0
        if not subscriber_count or subscriber_count <= 0:
            self.results["subscribers_exist"] = False
            all_passed = False
            logger.error("Validation Check 2 FAILED: Subscriber count unavailable")
        else:
            self.results["subscribers_exist"] = True
            logger.info("Validation Check 2 PASSED: Subscriber count: %d", subscriber_count)

        self.results["post_count"] = len(posts)
        if not posts:
            self.results["posts_exist"] = False
            all_passed = False
            logger.error("Validation Check 3 FAILED: No posts fetched")
        else:
            self.results["posts_exist"] = True
            logger.info("Validation Check 3 PASSED: Posts fetched: %d", len(posts))

        timestamps = [
            p["timestamp"] for p in posts if p.get("timestamp")
        ]
        if len(timestamps) >= 2:
            self.results["date_range"] = {
                "earliest": min(timestamps).strftime("%Y-%m-%d"),
                "latest": max(timestamps).strftime("%Y-%m-%d"),
            }
            self.results["date_range_available"] = True
            logger.info("Validation Check 4 PASSED: Date range available")
        else:
            self.results["date_range_available"] = False
            all_passed = False
            logger.error("Validation Check 4 FAILED: Insufficient date data")

        views = [p["views"] for p in posts if p.get("views", 0) > 0]
        if views:
            self.results["avg_views"] = round(mean(views))
            self.results["avg_views_calculable"] = True
            logger.info("Validation Check 5 PASSED: Avg views: %d", self.results["avg_views"])
        else:
            self.results["avg_views_calculable"] = False
            all_passed = False
            logger.error("Validation Check 5 FAILED: Views data unavailable")

        reactions_available = any(p.get("reactions") for p in posts if p.get("reactions"))
        self.results["reactions_available"] = reactions_available
        if reactions_available:
            logger.info("Validation Check 6 PASSED: Reaction data available")
        else:
            logger.warning("Validation Check 6: No reaction data found (may be normal)")

        self.results["all_passed"] = all_passed
        self._print_summary()
        return self.results

    def _print_summary(self):
        print(f"\n{SUMMARY_SEPARATOR}")
        print(f"Channel: {self.results.get('channel_title', 'N/A')}")
        print(f"Subscribers: {self.results.get('subscriber_count', 'N/A')}")
        print(f"Posts: {self.results.get('post_count', 0)}")

        dr = self.results.get("date_range")
        if dr:
            print(f"Date Range:\n{dr['earliest']} -> {dr['latest']}")

        if self.results.get("avg_views_calculable"):
            print(f"Average Views:\n{self.results.get('avg_views')}")

        print(f"Reaction Data:\n{'Available' if self.results.get('reactions_available') else 'Not Available'}")

        print(f"\nStatus:")
        if self.results.get("all_passed"):
            print("ALL CHECKS PASSED")
        else:
            print("VALIDATION FAILED")
        print(f"{SUMMARY_SEPARATOR}\n")

        if not self.results.get("all_passed"):
            raise ValidationError("Validation checks failed. See summary above.")
