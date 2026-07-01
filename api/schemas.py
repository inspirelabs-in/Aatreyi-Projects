"""Request/response Pydantic models for the API."""
from __future__ import annotations

from pydantic import BaseModel, Field


class OnboardChannel(BaseModel):
    telegram_username: str = Field(..., examples=["@mychannel"])
    category: str | None = None
    growth_goal: str | None = None
    language: str = "en"
    # Platform Admin only: create the channel for another organization. Ignored
    # for normal users (their channel is auto-assigned to their own org).
    organization_id: str | None = None


class ChannelUpdate(BaseModel):
    display_name: str | None = None
    category: str | None = None
    # Moving a channel to another org is Platform-Admin-only (enforced in the router).
    organization_id: str | None = None


class OrgSettingsUpdate(BaseModel):
    auto_approve_content: bool | None = None
    daily_target_posts: int | None = Field(None, ge=1, le=200)


class EditPost(BaseModel):
    edited_text: str


class RejectPost(BaseModel):
    reason: str | None = None


class RunAgent(BaseModel):
    agent: str = Field(..., description="dna | competitor | analytics | strategy | content | onboard")
    snapshot_type: str = Field("daily", description="daily | weekly | monthly (analytics/strategy)")
    task_id: str | None = Field(None, description="strategy_task id (content agent)")
    with_telegram: bool = True


class ContentSourceCreate(BaseModel):
    type: str = Field("rss", description="rss | website | telegram_channel")
    url: str
    name: str | None = None


class ContentSourceUpdate(BaseModel):
    is_active: bool | None = None
    name: str | None = None
    url: str | None = None


class ChannelSettingsUpdate(BaseModel):
    auto_approve: bool | None = None
    score_threshold: int | None = Field(None, ge=1, le=7)


class CompetitorHandleUpdate(BaseModel):
    handle: str = Field(..., description="Telegram handle (with or without leading @)")


class CreateOrganization(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, examples=["My News Network"])
    slug: str | None = Field(None, min_length=1, max_length=64, pattern=r"^[a-z0-9-]+$")


class CreateUser(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, examples=["Alice"])
    email: str | None = Field(None, max_length=255, examples=["alice@example.com"])
    is_admin: bool = False
