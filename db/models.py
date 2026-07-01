"""ORM models for all 14 tables of the Telegram Growth & Retention Agent.

Schema follows db_schema.md. A handful of operational columns required by
formulae.md / the roadmap but not listed in the schema table are added and
marked with a "# roadmap/formula:" comment.
"""
from __future__ import annotations

import enum
import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


# ── Enums ────────────────────────────────────────────────────────────────────
class Tier(str, enum.Enum):
    new = "new"
    mid = "mid"
    established = "established"


class ChannelStatus(str, enum.Enum):
    onboarding = "onboarding"
    active = "active"
    paused = "paused"


class DiscoverySource(str, enum.Enum):
    telegram_api = "telegram_api"
    tgstat = "tgstat"
    telemetr = "telemetr"
    duckduckgo = "duckduckgo"


class PostFormat(str, enum.Enum):
    text = "text"
    photo = "photo"
    video = "video"
    poll = "poll"
    link = "link"


class TaskFormat(str, enum.Enum):
    text = "text"
    photo = "photo"
    video = "video"
    poll = "poll"
    link = "link"
    carousel = "carousel"


class SnapshotType(str, enum.Enum):
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"


class StrategyType(str, enum.Enum):
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"


class StrategyStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    completed = "completed"


class TaskStatus(str, enum.Enum):
    pending = "pending"
    content_sourced = "content_sourced"
    generated = "generated"
    approved = "approved"
    published = "published"
    rejected = "rejected"


class SourceType(str, enum.Enum):
    rss = "rss"
    website = "website"
    telegram_channel = "telegram_channel"
    keyword_db = "keyword_db"


class ContentItemStatus(str, enum.Enum):
    raw = "raw"
    scored = "scored"
    used = "used"
    dropped = "dropped"


class ReviewStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    edited = "edited"
    rejected = "rejected"


class QueueStatus(str, enum.Enum):
    queued = "queued"
    sent = "sent"
    failed = "failed"
    skipped = "skipped"


class AgentName(str, enum.Enum):
    channel_dna = "channel_dna"
    competitor_intelligence = "competitor_intelligence"
    analytics = "analytics"
    strategy = "strategy"
    content_intelligence = "content_intelligence"


class AgentTrigger(str, enum.Enum):
    cron_daily = "cron_daily"
    cron_weekly = "cron_weekly"
    cron_monthly = "cron_monthly"
    post_slot = "post_slot"
    manual = "manual"


class RunStatus(str, enum.Enum):
    running = "running"
    completed = "completed"
    failed = "failed"


class CadenceLabel(str, enum.Enum):
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"
    post_slot = "post_slot"
    custom = "custom"


# Shared enum type instance, reused by agent_runs.agent and cron_jobs.agent so
# the Postgres type is created exactly once.
AGENT_NAME_ENUM = SAEnum(AgentName, name="agent_name")


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


# ── 1. channels ──────────────────────────────────────────────────────────────
class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[uuid.UUID] = _pk()
    telegram_username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger)
    display_name: Mapped[str | None] = mapped_column(String(128))
    tier: Mapped[Tier] = mapped_column(SAEnum(Tier, name="tier"), default=Tier.new)
    category: Mapped[str | None] = mapped_column(String(64))
    sub_category: Mapped[str | None] = mapped_column(String(64))
    growth_goal: Mapped[str | None] = mapped_column(String(256))
    language: Mapped[str] = mapped_column(String(8), default="en")
    status: Mapped[ChannelStatus] = mapped_column(
        SAEnum(ChannelStatus, name="channel_status"), default=ChannelStatus.onboarding
    )
    # roadmap: Analytics.flag_strategy_review sets this for out-of-cycle Strategy runs
    needs_strategy_review: Mapped[bool] = mapped_column(Boolean, default=False)
    strategy_review_reason: Mapped[str | None] = mapped_column(String(256))
    # formula 5.1: per-channel 7-signal pass threshold (default 4)
    score_threshold: Mapped[int] = mapped_column(SmallInteger, default=4)
    # When True, generated posts skip manual review and publish if BOT_TOKEN is set.
    auto_approve: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    dna: Mapped[ChannelDNA | None] = relationship(
        back_populates="channel", uselist=False, cascade="all, delete-orphan"
    )
    competitors: Mapped[list[Competitor]] = relationship(
        back_populates="channel", cascade="all, delete-orphan"
    )


# ── 2. channel_dna ───────────────────────────────────────────────────────────
class ChannelDNA(Base):
    __tablename__ = "channel_dna"

    id: Mapped[uuid.UUID] = _pk()
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), unique=True
    )
    subscriber_count: Mapped[int | None] = mapped_column(Integer)
    avg_views_per_post: Mapped[float | None] = mapped_column(Float)
    avg_er: Mapped[float | None] = mapped_column(Float)
    post_frequency_per_day: Mapped[float | None] = mapped_column(Float)
    best_post_hour: Mapped[int | None] = mapped_column(SmallInteger)
    best_post_days: Mapped[list | None] = mapped_column(JSONB)
    top_content_formats: Mapped[list | None] = mapped_column(JSONB)
    # specific recurring topics mined from the channel's own posts (drives strategy)
    top_topics: Mapped[list | None] = mapped_column(JSONB)
    # a few of the channel's REAL recent posts ({text, format}) used as few-shot
    # style examples so generated content matches the channel's actual pattern.
    sample_posts: Mapped[list | None] = mapped_column(JSONB)
    tone_fingerprint: Mapped[dict | None] = mapped_column(JSONB)
    audience_geo_top3: Mapped[list | None] = mapped_column(JSONB)
    growth_curve: Mapped[list | None] = mapped_column(JSONB)
    category: Mapped[str | None] = mapped_column(String(64))
    sub_category: Mapped[str | None] = mapped_column(String(64))
    # roadmap: set when fewer than 10 posts are available
    insufficient_data: Mapped[bool] = mapped_column(Boolean, default=False)
    analysed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    channel: Mapped[Channel] = relationship(back_populates="dna")


# ── 3. competitors ───────────────────────────────────────────────────────────
class Competitor(Base):
    __tablename__ = "competitors"
    __table_args__ = (
        UniqueConstraint("channel_id", "competitor_username", name="uq_channel_competitor"),
    )

    id: Mapped[uuid.UUID] = _pk()
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE")
    )
    competitor_username: Mapped[str] = mapped_column(String(64))
    competitor_tg_id: Mapped[int | None] = mapped_column(BigInteger)
    display_name: Mapped[str | None] = mapped_column(String(128))
    subscriber_count: Mapped[int | None] = mapped_column(Integer)
    post_frequency_per_day: Mapped[float | None] = mapped_column(Float)
    avg_er: Mapped[float | None] = mapped_column(Float)
    top_content_themes: Mapped[list | None] = mapped_column(JSONB)
    source: Mapped[DiscoverySource | None] = mapped_column(
        SAEnum(DiscoverySource, name="discovery_source")
    )
    rank: Mapped[int | None] = mapped_column(SmallInteger)
    rank_score: Mapped[float | None] = mapped_column(Float)
    topic_similarity: Mapped[float | None] = mapped_column(Float)
    content_similarity: Mapped[float | None] = mapped_column(Float)
    # Competitor Intelligence engine (spec): classification + similarity breakdown
    # + per-competitor analysis blob (media mix, best hours, CTA, strengths, etc.).
    competitor_type: Mapped[str | None] = mapped_column(String(16))  # direct|aspirational|adjacent
    similarity_breakdown: Mapped[dict | None] = mapped_column(JSONB)  # weighted sub-scores
    intelligence: Mapped[dict | None] = mapped_column(JSONB)          # analysis (no recommendations)
    has_disappearing_messages: Mapped[bool] = mapped_column(Boolean, default=False)
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    channel: Mapped[Channel] = relationship(back_populates="competitors")
    posts: Mapped[list[CompetitorPost]] = relationship(
        back_populates="competitor", cascade="all, delete-orphan"
    )


# ── 4. competitor_posts ──────────────────────────────────────────────────────
class CompetitorPost(Base):
    __tablename__ = "competitor_posts"

    id: Mapped[uuid.UUID] = _pk()
    competitor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("competitors.id", ondelete="CASCADE")
    )
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger)
    text_preview: Mapped[str | None] = mapped_column(Text)
    format: Mapped[PostFormat | None] = mapped_column(
        SAEnum(PostFormat, name="competitor_post_format")
    )
    views: Mapped[int | None] = mapped_column(Integer)
    forwards: Mapped[int | None] = mapped_column(Integer)
    reactions_count: Mapped[int | None] = mapped_column(Integer)
    er: Mapped[float | None] = mapped_column(Float)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    competitor: Mapped[Competitor] = relationship(back_populates="posts")


# ── 5b. subscriber_readings (high-frequency, lightweight) ────────────────────
class SubscriberReading(Base):
    """A lightweight subscriber-count sample taken every ~20 min so growth/churn
    stay near-real-time without the heavy daily analytics snapshot."""
    __tablename__ = "subscriber_readings"

    id: Mapped[uuid.UUID] = _pk()
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), index=True
    )
    subscriber_count: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ── 5. analytics_snapshots ───────────────────────────────────────────────────
class AnalyticsSnapshot(Base):
    __tablename__ = "analytics_snapshots"

    id: Mapped[uuid.UUID] = _pk()
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE")
    )
    snapshot_type: Mapped[SnapshotType] = mapped_column(
        SAEnum(SnapshotType, name="snapshot_type")
    )
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    subscriber_count: Mapped[int | None] = mapped_column(Integer)
    subscriber_delta: Mapped[int | None] = mapped_column(Integer)
    subscriber_delta_pct: Mapped[float | None] = mapped_column(Float)
    avg_views: Mapped[float | None] = mapped_column(Float)
    avg_er: Mapped[float | None] = mapped_column(Float)
    total_posts: Mapped[int | None] = mapped_column(SmallInteger)
    top_post_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("generated_posts.id", ondelete="SET NULL")
    )
    reach: Mapped[int | None] = mapped_column(Integer)
    churn_signal: Mapped[bool] = mapped_column(Boolean, default=False)
    churn_rate: Mapped[float | None] = mapped_column(Float)
    insights: Mapped[list | None] = mapped_column(JSONB)
    # Phase 1: post/audience intelligence blob (virality, purpose mix, community signal)
    intelligence: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ── 6. strategies ────────────────────────────────────────────────────────────
class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[uuid.UUID] = _pk()
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE")
    )
    strategy_type: Mapped[StrategyType] = mapped_column(
        SAEnum(StrategyType, name="strategy_type")
    )
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    goal: Mapped[str | None] = mapped_column(Text)
    post_frequency_per_day: Mapped[float | None] = mapped_column(Float)
    content_mix: Mapped[list | None] = mapped_column(JSONB)
    primary_topics: Mapped[list | None] = mapped_column(JSONB)
    growth_tactics: Mapped[list | None] = mapped_column(JSONB)
    # root-cause diagnosis + competitor benchmark + fatigue (shown in the UI)
    analysis: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[StrategyStatus] = mapped_column(
        SAEnum(StrategyStatus, name="strategy_status"), default=StrategyStatus.draft
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    tasks: Mapped[list[StrategyTask]] = relationship(
        back_populates="strategy", cascade="all, delete-orphan"
    )


# ── 7. strategy_tasks ────────────────────────────────────────────────────────
class StrategyTask(Base):
    __tablename__ = "strategy_tasks"

    id: Mapped[uuid.UUID] = _pk()
    strategy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE")
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE")
    )
    scheduled_date: Mapped[date | None] = mapped_column(Date)
    scheduled_time: Mapped[time | None] = mapped_column(Time)
    format: Mapped[TaskFormat | None] = mapped_column(
        SAEnum(TaskFormat, name="strategy_task_format")
    )
    topic: Mapped[str | None] = mapped_column(String(128))
    # Phase 2: habit-loop trigger kind (series / cliffhanger / weekly / challenge / reengage)
    # Deals execution-planner: kind = "loot" | "single"
    kind: Mapped[str | None] = mapped_column(String(32))
    # ── Execution-planner slot fields (Strategy Agent emits, Scheduler executes) ──
    marketplace: Mapped[str | None] = mapped_column(String(24))   # Amazon / Flipkart / None (loot mix)
    media_type: Mapped[str | None] = mapped_column(String(16))    # photo / none
    scrape_at: Mapped[time | None] = mapped_column(Time)          # when the executor scrapes (publish − lead)
    priority: Mapped[int | None] = mapped_column(Integer)         # execution priority (higher = more important)
    rationale: Mapped[str | None] = mapped_column(Text)           # why this slot (category/time/media reason)
    content_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("content_items.id", ondelete="SET NULL")
    )
    generated_post_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("generated_posts.id", ondelete="SET NULL")
    )
    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(TaskStatus, name="strategy_task_status"), default=TaskStatus.pending
    )

    strategy: Mapped[Strategy] = relationship(back_populates="tasks")


# ── 8. content_sources ───────────────────────────────────────────────────────
class ContentSource(Base):
    __tablename__ = "content_sources"

    id: Mapped[uuid.UUID] = _pk()
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE")
    )
    type: Mapped[SourceType] = mapped_column(SAEnum(SourceType, name="source_type"))
    url: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(String(128))
    category: Mapped[str | None] = mapped_column(String(64))
    fetch_interval_mins: Mapped[int | None] = mapped_column(Integer)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    avg_quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    # formula 5.2: items counted into the rolling avg (auto-deactivate after 20)
    total_items_scored: Mapped[int] = mapped_column(Integer, default=0)

    items: Mapped[list[ContentItem]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


# ── 9. content_items ─────────────────────────────────────────────────────────
class ContentItem(Base):
    __tablename__ = "content_items"

    id: Mapped[uuid.UUID] = _pk()
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE")
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("content_sources.id", ondelete="SET NULL")
    )
    external_url: Mapped[str | None] = mapped_column(Text, index=True)
    title: Mapped[str | None] = mapped_column(String(512))
    body_text: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(128))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    format_tag: Mapped[str | None] = mapped_column(String(32))
    topics: Mapped[list | None] = mapped_column(JSONB)
    status: Mapped[ContentItemStatus] = mapped_column(
        SAEnum(ContentItemStatus, name="content_item_status"),
        default=ContentItemStatus.raw,
    )

    source: Mapped[ContentSource | None] = relationship(back_populates="items")
    score: Mapped[ContentScore | None] = relationship(
        back_populates="content_item", uselist=False, cascade="all, delete-orphan"
    )


# ── 10. content_scores ───────────────────────────────────────────────────────
class ContentScore(Base):
    __tablename__ = "content_scores"

    id: Mapped[uuid.UUID] = _pk()
    content_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_items.id", ondelete="CASCADE"), unique=True
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE")
    )
    relevance: Mapped[int | None] = mapped_column(SmallInteger)
    freshness: Mapped[int | None] = mapped_column(SmallInteger)
    novelty: Mapped[int | None] = mapped_column(SmallInteger)
    goal_alignment: Mapped[int | None] = mapped_column(SmallInteger)
    virality: Mapped[int | None] = mapped_column(SmallInteger)
    competitor_set: Mapped[int | None] = mapped_column(SmallInteger)
    brand_safety: Mapped[int | None] = mapped_column(SmallInteger)
    total_score: Mapped[int | None] = mapped_column(SmallInteger)
    passed: Mapped[bool | None] = mapped_column(Boolean)
    threshold_used: Mapped[int | None] = mapped_column(SmallInteger)
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    content_item: Mapped[ContentItem] = relationship(back_populates="score")


# ── 11. generated_posts ──────────────────────────────────────────────────────
class GeneratedPost(Base):
    __tablename__ = "generated_posts"

    id: Mapped[uuid.UUID] = _pk()
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE")
    )
    content_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("content_items.id", ondelete="SET NULL")
    )
    # use_alter breaks the generated_posts <-> strategy_tasks FK cycle:
    # this constraint is added via ALTER after both tables exist.
    strategy_task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "strategy_tasks.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_generated_posts_strategy_task",
        )
    )
    post_text: Mapped[str | None] = mapped_column(Text)
    post_format: Mapped[PostFormat | None] = mapped_column(
        SAEnum(PostFormat, name="generated_post_format")
    )
    media_url: Mapped[str | None] = mapped_column(Text)
    # destination URL for the CTA (e.g. the deal/article link) — rendered as a
    # clickable "Shop Now"-style inline button when the post is published.
    link_url: Mapped[str | None] = mapped_column(Text)
    # poll posts: ["option 1", "option 2", ...] (post_text holds the question)
    poll_options: Mapped[list | None] = mapped_column(JSONB)
    cta: Mapped[str | None] = mapped_column(String(256))
    hashtags: Mapped[list | None] = mapped_column(JSONB)
    llm_model: Mapped[str | None] = mapped_column(String(64))
    generation_prompt: Mapped[str | None] = mapped_column(Text)
    review_status: Mapped[ReviewStatus] = mapped_column(
        SAEnum(ReviewStatus, name="review_status"), default=ReviewStatus.pending
    )
    edited_text: Mapped[str | None] = mapped_column(Text)
    rejection_reason: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ── 12. post_queue ───────────────────────────────────────────────────────────
class PostQueue(Base):
    __tablename__ = "post_queue"

    id: Mapped[uuid.UUID] = _pk()
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE")
    )
    generated_post_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("generated_posts.id", ondelete="CASCADE")
    )
    strategy_task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("strategy_tasks.id", ondelete="SET NULL")
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[QueueStatus] = mapped_column(
        SAEnum(QueueStatus, name="queue_status"), default=QueueStatus.queued
    )
    retry_count: Mapped[int] = mapped_column(SmallInteger, default=0)
    error_log: Mapped[str | None] = mapped_column(Text)


# ── 13. agent_runs ───────────────────────────────────────────────────────────
class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = _pk()
    channel_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE")
    )
    agent: Mapped[AgentName] = mapped_column(AGENT_NAME_ENUM)
    trigger: Mapped[AgentTrigger] = mapped_column(
        SAEnum(AgentTrigger, name="agent_trigger")
    )
    status: Mapped[RunStatus] = mapped_column(SAEnum(RunStatus, name="run_status"))
    input_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    output_summary: Mapped[dict | None] = mapped_column(JSONB)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ── 14. cron_jobs ────────────────────────────────────────────────────────────
class CronJob(Base):
    __tablename__ = "cron_jobs"

    id: Mapped[uuid.UUID] = _pk()
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE")
    )
    agent: Mapped[AgentName] = mapped_column(AGENT_NAME_ENUM)
    cron_expression: Mapped[str | None] = mapped_column(String(32))
    cadence_label: Mapped[CadenceLabel | None] = mapped_column(
        SAEnum(CadenceLabel, name="cadence_label")
    )
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
