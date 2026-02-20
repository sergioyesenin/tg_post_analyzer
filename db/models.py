from __future__ import annotations

from datetime import datetime
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    JSON,
    Integer,
    Float,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, index=True)  # например "mychannel"
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    posts: Mapped[list["Post"]] = relationship(back_populates="channel")


class Post(Base):
    """
    В Телеграме message_id уникален ВНУТРИ канала, поэтому делаем (channel_id, tg_message_id) уникальным.
    """
    __tablename__ = "posts"
    __table_args__ = (
        UniqueConstraint("channel_id", "tg_message_id", name="uq_posts_channel_msg"),
        Index("ix_posts_channel_date", "channel_id", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), index=True)

    tg_message_id: Mapped[int] = mapped_column(Integer, index=True)
    parent_tg_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    parent_post_id: Mapped[int | None] = mapped_column(
        ForeignKey("posts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    views: Mapped[int | None] = mapped_column(Integer, nullable=True)

    comments_count: Mapped[int] = mapped_column(Integer, default=0, index=True)
    involvement: Mapped[float | None] = mapped_column(nullable=True)

    # для логики "собрать через 10-15 мин + дособор 24 часа"
    last_comments_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    comments_scan_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    channel: Mapped["Channel"] = relationship(back_populates="posts")
    comments: Mapped[list["Comment"]] = relationship(back_populates="post")
    report: Mapped["Report | None"] = relationship(back_populates="post", uselist=False)
    feature: Mapped["PostFeature | None"] = relationship(back_populates="post", uselist=False)
    event_memberships: Mapped[list["EventPost"]] = relationship(back_populates="post")
    parent_post: Mapped["Post | None"] = relationship(
        remote_side="Post.id",
        foreign_keys=[parent_post_id],
    )
    outgoing_links: Mapped[list["PostLink"]] = relationship(
        back_populates="src_post",
        foreign_keys="PostLink.src_post_id",
    )
    incoming_links: Mapped[list["PostLink"]] = relationship(
        back_populates="dst_post",
        foreign_keys="PostLink.dst_post_id",
    )


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = (
        UniqueConstraint("channel_id", "tg_message_id", name="uq_comments_channel_msg"),
        Index("ix_comments_post_date", "post_id", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), index=True)

    tg_message_id: Mapped[int] = mapped_column(Integer, index=True)
    parent_tg_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    parent_comment_id: Mapped[int | None] = mapped_column(ForeignKey("comments.id", ondelete="SET NULL"), nullable=True, index=True)
    thread_root_tg_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    depth: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    author_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    author_username: Mapped[str | None] = mapped_column(String(255), nullable=True)

    text: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    post: Mapped["Post"] = relationship(back_populates="comments")


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        UniqueConstraint("post_id", name="uq_reports_post"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), index=True)

    status: Mapped[str] = mapped_column(String(50), default="ready")  # ready / pending / failed
    content: Mapped[str] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    post: Mapped["Post"] = relationship(back_populates="report")


class PostFeature(Base):
    __tablename__ = "post_features"

    post_id: Mapped[int] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    text_normalized: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    embedding: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    entities: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    lang: Mapped[str | None] = mapped_column(String(16), nullable=True)
    topic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    analyzer_version: Mapped[str] = mapped_column(String(64), default="v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    post: Mapped["Post"] = relationship(back_populates="feature")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="open", index=True)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary_current: Mapped[str | None] = mapped_column(Text, nullable=True)
    reporter_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    posts: Mapped[list["EventPost"]] = relationship(back_populates="event")
    reports: Mapped[list["EventReport"]] = relationship(back_populates="event")


class EventPost(Base):
    __tablename__ = "event_posts"
    __table_args__ = (
        Index("ix_event_posts_post_id", "post_id"),
    )

    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(50), default="context")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    event: Mapped["Event"] = relationship(back_populates="posts")
    post: Mapped["Post"] = relationship(back_populates="event_memberships")


class PostLink(Base):
    __tablename__ = "post_links"
    __table_args__ = (
        UniqueConstraint("src_post_id", "dst_post_id", "link_type", name="uq_post_links_src_dst_type"),
        CheckConstraint("src_post_id <> dst_post_id", name="ck_post_links_src_ne_dst"),
        Index("ix_post_links_src_post_id", "src_post_id"),
        Index("ix_post_links_dst_post_id", "dst_post_id"),
        Index("ix_post_links_type", "link_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    src_post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    dst_post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    link_type: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    src_post: Mapped["Post"] = relationship(back_populates="outgoing_links", foreign_keys=[src_post_id])
    dst_post: Mapped["Post"] = relationship(back_populates="incoming_links", foreign_keys=[dst_post_id])


class EventReport(Base):
    __tablename__ = "event_reports"
    __table_args__ = (
        Index("ix_event_reports_event_id", "event_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    report_text: Mapped[str] = mapped_column(Text)
    report_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    event: Mapped["Event"] = relationship(back_populates="reports")
