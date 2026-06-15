from collections import deque
from datetime import date, timedelta
from statistics import mean
from typing import Any

from app.database.models import SubscriberSnapshot
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _safe_rate(new: int, old: int) -> float:
    if old <= 0:
        return 0.0
    return round(((new - old) / old) * 100, 4)


class GrowthService:
    def calculate(self, snapshots: list[SubscriberSnapshot]) -> dict[str, Any]:
        if not snapshots:
            return {
                "daily_growth": 0,
                "weekly_growth": 0,
                "growth_rate": 0.0,
                "growth_7_day": 0.0,
                "growth_30_day": 0.0,
                "growth_trend": 0.0,
                "trend_points": [],
            }

        snapshots = sorted(snapshots, key=lambda snapshot: snapshot.snapshot_date)
        latest = snapshots[-1]
        previous = snapshots[-2] if len(snapshots) > 1 else None

        daily_growth = latest.subscriber_count - (previous.subscriber_count if previous else latest.subscriber_count)
        growth_rate = _safe_rate(latest.subscriber_count, previous.subscriber_count if previous else 0)

        snapshot_by_date = {snapshot.snapshot_date: snapshot for snapshot in snapshots}
        day_7 = latest.snapshot_date - timedelta(days=7)
        day_30 = latest.snapshot_date - timedelta(days=30)

        week_snapshot = None
        for snapshot in reversed(snapshots):
            if snapshot.snapshot_date <= day_7:
                week_snapshot = snapshot
                break

        month_snapshot = None
        for snapshot in reversed(snapshots):
            if snapshot.snapshot_date <= day_30:
                month_snapshot = snapshot
                break

        weekly_growth = latest.subscriber_count - (week_snapshot.subscriber_count if week_snapshot else latest.subscriber_count)
        growth_7_day = _safe_rate(latest.subscriber_count, week_snapshot.subscriber_count if week_snapshot else 0)
        growth_30_day = _safe_rate(latest.subscriber_count, month_snapshot.subscriber_count if month_snapshot else 0)

        all_counts = [snapshot.subscriber_count for snapshot in snapshots]
        total_days = max(1, (latest.snapshot_date - snapshots[0].snapshot_date).days)
        growth_trend = round((latest.subscriber_count - snapshots[0].subscriber_count) / total_days, 4) if total_days > 0 else 0.0

        trend_points = [
            {"date": snapshot.snapshot_date.isoformat(), "subscribers": snapshot.subscriber_count}
            for snapshot in snapshots
        ]

        metrics = {
            "daily_growth": daily_growth,
            "weekly_growth": weekly_growth,
            "growth_rate": growth_rate,
            "growth_7_day": growth_7_day,
            "growth_30_day": growth_30_day,
            "growth_trend": growth_trend,
            "trend_points": trend_points,
        }
        logger.info("Calculated growth metrics for %d snapshots", len(snapshots))
        return metrics
