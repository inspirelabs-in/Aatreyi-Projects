from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, JSON, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Channel(Base):
    __tablename__ = "channels"

    channel_id = Column(BigInteger, primary_key=True)
    title = Column(Text, nullable=False)
    username = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=True)
    verified = Column(Boolean, default=False)
    public_channel = Column(Boolean, default=True)
    subscriber_count = Column(Integer, nullable=True)


class RegisteredChannel(Base):
    __tablename__ = "registered_channels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_username = Column(Text, nullable=False, unique=True, index=True)
    alias = Column(Text, nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    last_run_at = Column(DateTime(timezone=True), nullable=True)


class Post(Base):
    __tablename__ = "posts"

    message_id = Column(BigInteger, primary_key=True)
    channel_id = Column(BigInteger, ForeignKey("channels.channel_id"), nullable=False, index=True)
    text = Column(Text, nullable=True)
    media_type = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=True)
    views = Column(Integer, default=0)
    forwards = Column(Integer, default=0)
    reactions = Column(JSON, nullable=True)
    reply_count = Column(Integer, default=0)
    # Link intelligence — populated by extract_links() in helpers.py
    has_link = Column(Boolean, default=False, nullable=False)
    link_url = Column(Text, nullable=True)
    is_affiliate = Column(Boolean, default=False, nullable=False)


class SubscriberSnapshot(Base):
    __tablename__ = "subscriber_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(BigInteger, ForeignKey("channels.channel_id"), nullable=False, index=True)
    subscriber_count = Column(Integer, nullable=False)
    snapshot_date = Column(Date, nullable=False, default=date.today)


class ContentMetrics(Base):
    __tablename__ = "content_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(BigInteger, ForeignKey("channels.channel_id"), nullable=False, index=True)
    
    # Posts frequency
    total_posts = Column(Integer, nullable=False, default=0)
    posts_per_day = Column(Float, nullable=False, default=0.0)
    posts_per_week = Column(Float, nullable=False, default=0.0)
    
    # Reach metrics
    total_views = Column(Integer, nullable=False, default=0)
    avg_views = Column(Float, nullable=False, default=0.0)
    median_views = Column(Float, nullable=False, default=0.0)
    view_rate = Column(Float, nullable=False, default=0.0)
    
    # Engagement metrics
    total_reactions = Column(Integer, nullable=False, default=0)
    avg_reactions = Column(Float, nullable=False, default=0.0)
    total_forwards = Column(Integer, nullable=False, default=0)
    avg_forwards = Column(Float, nullable=False, default=0.0)
    total_replies = Column(Integer, nullable=False, default=0)
    avg_replies = Column(Float, nullable=False, default=0.0)
    reaction_rate = Column(Float, nullable=False, default=0.0)
    forward_rate = Column(Float, nullable=False, default=0.0)
    reply_rate = Column(Float, nullable=False, default=0.0)
    er = Column(Float, nullable=False, default=0.0)
    
    # Content mix percentages
    content_mix = Column(JSON, nullable=True)
    content_type_performance = Column(JSON, nullable=True)
    
    # Top / bottom posts for AI feed
    top_posts = Column(JSON, nullable=True)
    bottom_posts = Column(JSON, nullable=True)
    
    # Calculation timestamp
    calculated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    period_start = Column(DateTime(timezone=True), nullable=True)
    period_end = Column(DateTime(timezone=True), nullable=True)


class PerformanceMetrics(Base):
    __tablename__ = "performance_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(BigInteger, ForeignKey("channels.channel_id"), nullable=False, index=True)
    
    # Engagement rates (percentages)
    view_rate = Column(Float, nullable=False, default=0.0)
    engagement_rate = Column(Float, nullable=False, default=0.0)
    reaction_rate = Column(Float, nullable=False, default=0.0)
    forward_rate = Column(Float, nullable=False, default=0.0)
    reply_rate = Column(Float, nullable=False, default=0.0)
    er = Column(Float, nullable=False, default=0.0)
    
    # Total engagement
    total_views = Column(Integer, nullable=False, default=0)
    total_reactions = Column(Integer, nullable=False, default=0)
    total_forwards = Column(Integer, nullable=False, default=0)
    total_replies = Column(Integer, nullable=False, default=0)
    
    # Calculation timestamp
    calculated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    period_start = Column(DateTime(timezone=True), nullable=True)
    period_end = Column(DateTime(timezone=True), nullable=True)


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(BigInteger, ForeignKey("channels.channel_id"), nullable=True, index=True)
    channel_username = Column(Text, nullable=False, index=True)
    stage = Column(Text, nullable=False)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
