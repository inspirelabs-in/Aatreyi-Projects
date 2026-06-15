from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class ChannelResolved(BaseModel):
    channel_id: int
    title: str
    username: str
    description: str = ""
    subscriber_count: int = 0
    verified: bool = False
    public_channel: bool = True


class PostRaw(BaseModel):
    post_id: int = Field(alias="message_id")
    channel_id: int
    message: str = Field(default="", alias="text")
    timestamp: datetime | None = None
    views: int = 0
    reactions: Any = None
    forwards: int = 0
    reply_count: int = 0
    media_type: str = "TEXT"


class SubscriberSnapshotIn(BaseModel):
    channel_id: int
    subscriber_count: int
    snapshot_date: date


class TrackedChannelCreate(BaseModel):
    username: str
    active: bool = True


class ValidationResult(BaseModel):
    channel_exists: bool = False
    subscriber_count: int = 0
    posts_collected: int = 0
    date_range_earliest: str | None = None
    date_range_latest: str | None = None
    minimum_posts_met: bool = False
    all_passed: bool = False
