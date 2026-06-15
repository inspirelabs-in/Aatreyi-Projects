from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Column, Date, DateTime, ForeignKey, Integer, JSON, String, Text
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

    post_id = Column(BigInteger, primary_key=True, autoincrement=False)
    channel_id = Column(BigInteger, ForeignKey("channels.channel_id"), primary_key=True)
    message = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=True)
    views = Column(Integer, default=0)
    reactions = Column(JSON, nullable=True)
    forwards = Column(Integer, default=0)
    reply_count = Column(Integer, default=0)
    media_type = Column(String(50), default="TEXT")

    channel = relationship("Channel", back_populates="posts")


class SubscriberSnapshot(Base):
    __tablename__ = "subscriber_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(BigInteger, ForeignKey("channels.channel_id"), nullable=False, index=True)
    subscriber_count = Column(Integer, nullable=False)
    snapshot_date = Column(Date, nullable=False, default=date.today)

    channel = relationship("Channel", back_populates="snapshots")
