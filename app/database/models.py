from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class TrackedChannel(Base):
    __tablename__ = "tracked_channels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(255), nullable=False, unique=True)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.now, nullable=False)


class Channel(Base):
    __tablename__ = "channels"

    channel_id = Column(BigInteger, primary_key=True)
    title = Column(Text, nullable=False)
    username = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=True)
    verified = Column(Boolean, default=False)
    public_channel = Column(Boolean, default=True)

    posts = relationship("Post", back_populates="channel", cascade="all, delete-orphan")
    snapshots = relationship("SubscriberSnapshot", back_populates="channel", cascade="all, delete-orphan")


class Post(Base):
    __tablename__ = "posts"

    post_id = Column("message_id", BigInteger, primary_key=True, autoincrement=False)
    channel_id = Column(BigInteger, ForeignKey("channels.channel_id"), primary_key=True)
    message = Column("text", Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=True)
    views = Column(Integer, default=0)
    reactions = Column(JSON, nullable=True)
    forwards = Column(Integer, default=0)
    reply_count = Column(Integer, default=0)
    media_type = Column(String(50), default="TEXT")
    has_link = Column(Boolean, nullable=False, default=False)
    link_url = Column(Text, nullable=True)
    is_affiliate = Column(Boolean, nullable=False, default=False)

    channel = relationship("Channel", back_populates="posts")


class SubscriberSnapshot(Base):
    __tablename__ = "subscriber_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(BigInteger, ForeignKey("channels.channel_id"), nullable=False, index=True)
    subscriber_count = Column(Integer, nullable=False)
    snapshot_date = Column(Date, nullable=False, default=date.today)

    channel = relationship("Channel", back_populates="snapshots")


class ContentMetrics(Base):
    __tablename__ = "content_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(BigInteger, ForeignKey("channels.channel_id"), nullable=False, index=True)
    snapshot_date = Column(Date, default=date.today, nullable=False, index=True)
    calculated_at = Column(DateTime(timezone=True), default=datetime.now, nullable=False)
    total_posts = Column(Integer, nullable=False, default=0)
    posts_per_day = Column(Float, nullable=False, default=0.0)
    posts_per_week = Column(Float, nullable=False, default=0.0)
    posting_consistency = Column(Float, nullable=False, default=0.0)
    posting_gaps = Column(JSON, nullable=True)
    content_mix = Column(JSON, nullable=True)
    avg_reach_rate = Column(Float, nullable=False, default=0.0)
    median_reach_rate = Column(Float, nullable=False, default=0.0)
    top_reach_rate = Column(Float, nullable=False, default=0.0)
    bottom_reach_rate = Column(Float, nullable=False, default=0.0)

    __table_args__ = (UniqueConstraint("channel_id", "snapshot_date", name="uq_content_metrics_channel_snapshot"),)


class PerformanceMetrics(Base):
    __tablename__ = "performance_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(BigInteger, ForeignKey("channels.channel_id"), nullable=False, index=True)
    snapshot_date = Column(Date, default=date.today, nullable=False, index=True)
    calculated_at = Column(DateTime(timezone=True), default=datetime.now, nullable=False)
    average_views = Column(Float, nullable=False, default=0.0)
    average_reactions = Column(Float, nullable=False, default=0.0)
    average_forwards = Column(Float, nullable=False, default=0.0)
    average_replies = Column(Float, nullable=False, default=0.0)
    reaction_rate = Column(Float, nullable=False, default=0.0)
    forward_rate = Column(Float, nullable=False, default=0.0)
    reply_rate = Column(Float, nullable=False, default=0.0)
    engagement_rate = Column(Float, nullable=False, default=0.0)
    top_posts = Column(JSON, nullable=True)
    bottom_posts = Column(JSON, nullable=True)

    __table_args__ = (UniqueConstraint("channel_id", "snapshot_date", name="uq_performance_metrics_channel_snapshot"),)


class GrowthMetrics(Base):
    __tablename__ = "growth_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(BigInteger, ForeignKey("channels.channel_id"), nullable=False, index=True)
    snapshot_date = Column(Date, default=date.today, nullable=False, index=True)
    calculated_at = Column(DateTime(timezone=True), default=datetime.now, nullable=False)
    daily_growth = Column(Integer, nullable=False, default=0)
    weekly_growth = Column(Integer, nullable=False, default=0)
    growth_rate = Column(Float, nullable=False, default=0.0)
    growth_7_day = Column(Float, nullable=False, default=0.0)
    growth_30_day = Column(Float, nullable=False, default=0.0)
    growth_trend = Column(Float, nullable=False, default=0.0)
    trend_points = Column(JSON, nullable=True)

    __table_args__ = (UniqueConstraint("channel_id", "snapshot_date", name="uq_growth_metrics_channel_snapshot"),)


class ChannelFeatures(Base):
    __tablename__ = "channel_features"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(BigInteger, ForeignKey("channels.channel_id"), nullable=False, index=True)
    snapshot_date = Column(Date, default=date.today, nullable=False, index=True)
    calculated_at = Column(DateTime(timezone=True), default=datetime.now, nullable=False)
    posts_per_day = Column(Float, nullable=False, default=0.0)
    avg_views = Column(Float, nullable=False, default=0.0)
    avg_reach_rate = Column(Float, nullable=False, default=0.0)
    avg_er = Column(Float, nullable=False, default=0.0)
    avg_err = Column(Float, nullable=False, default=0.0)
    growth_rate = Column(Float, nullable=False, default=0.0)
    content_mix = Column(JSON, nullable=True)
    top_er_posts = Column(JSON, nullable=True)
    top_err_posts = Column(JSON, nullable=True)

    __table_args__ = (UniqueConstraint("channel_id", "snapshot_date", name="uq_channel_features_channel_snapshot"),)
