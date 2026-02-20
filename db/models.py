from __future__ import annotations

from datetime import datetime
from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
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
