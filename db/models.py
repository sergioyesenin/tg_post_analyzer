from __future__ import annotations

from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Float,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _value_enum(enum_cls: type[PyEnum], *, name: str) -> Enum:
    return Enum(
        enum_cls,
        name=name,
        values_callable=lambda items: [item.value for item in items],
        native_enum=True,
        validate_strings=True,
    )


class VerificationStatus(str, PyEnum):
    PROPOSED = "proposed"
    VERIFIED = "verified"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"


class LinkDirection(str, PyEnum):
    SRC_TO_DST = "src_to_dst"
    DST_TO_SRC = "dst_to_src"
    NONE = "none"


class PostLinkType(str, PyEnum):
    SAME_EVENT = "same_event"
    UPDATE = "update"
    CONTRADICTION = "contradiction"
    CAUSE = "cause"
    CONSEQUENCE = "consequence"
    BACKGROUND = "background"
    RELATED = "related"
    UNRELATED = "unrelated"


class ProcessRelationType(str, PyEnum):
    CAUSE = "cause"
    EFFECT = "effect"
    UPDATE = "update"
    CONTRADICTION = "contradiction"
    RELATED = "related"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username", name="uq_users_username"),
        UniqueConstraint("email", name="uq_users_email"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    is_local: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("name", name="uq_roles_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        Index("ix_user_roles_role_id", "role_id"),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class AuthIdentity(Base):
    __tablename__ = "auth_identities"
    __table_args__ = (
        UniqueConstraint("provider", "external_subject", name="uq_auth_identities_provider_subject"),
        Index("ix_auth_identities_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    external_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    attrs_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class AuthRefreshToken(Base):
    __tablename__ = "auth_refresh_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_auth_refresh_tokens_token_hash"),
        Index("ix_auth_refresh_tokens_user_id", "user_id"),
        Index("ix_auth_refresh_tokens_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_token_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_refresh_tokens.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_actor_created", "actor_user_id", "created_at"),
        Index("ix_audit_logs_action_created", "action", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    details_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class AppSetting(Base):
    __tablename__ = "app_settings"
    __table_args__ = (
        UniqueConstraint("key", name="uq_app_settings_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    value_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


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
    text_normalized: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    embedding: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    entities: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    lang: Mapped[str | None] = mapped_column(String(16), nullable=True)
    topic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    analyzer_version: Mapped[str] = mapped_column(String(64), default="v1")

    # для логики "собрать через 10-15 мин + дособор 24 часа"
    last_comments_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    comments_scan_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    channel: Mapped["Channel"] = relationship(back_populates="posts")
    comments: Mapped[list["Comment"]] = relationship(back_populates="post")
    report: Mapped["Report | None"] = relationship(back_populates="post", uselist=False)
    facts: Mapped["PostFact | None"] = relationship(back_populates="post", uselist=False)
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


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_jobs_dedupe_key"),
        Index("ix_jobs_status_retry_priority", "status", "retry_at", "priority"),
        Index("ix_jobs_type_status", "type", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100, index=True)
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True)
    retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    locked_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class JobDeadLetter(Base):
    __tablename__ = "job_dead_letters"
    __table_args__ = (
        UniqueConstraint("source_job_id", name="uq_job_dead_letters_source_job_id"),
        Index("ix_job_dead_letters_type", "type"),
        Index("ix_job_dead_letters_failed_at", "failed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_job_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[VerificationStatus] = mapped_column(
        _value_enum(VerificationStatus, name="verification_status"),
        default=VerificationStatus.PROPOSED,
        index=True,
    )
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    posts: Mapped[list["EventPost"]] = relationship(back_populates="event")
    reports: Mapped[list["EventReport"]] = relationship(back_populates="event")
    process_memberships: Mapped[list["ProcessEvent"]] = relationship(back_populates="event")


class EventPost(Base):
    __tablename__ = "event_posts"
    __table_args__ = (
        Index("ix_event_posts_post_id", "post_id"),
        Index("ix_event_posts_status", "status"),
    )

    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(50), default="context")
    evidence_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[VerificationStatus] = mapped_column(
        _value_enum(VerificationStatus, name="verification_status"),
        default=VerificationStatus.PROPOSED,
    )
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pipeline_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

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
        Index("ix_post_links_status", "status"),
        Index("ix_post_links_score", "score"),
        Index("ix_post_links_evidence_gin", "evidence_json", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    src_post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    dst_post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    link_type: Mapped[PostLinkType] = mapped_column(_value_enum(PostLinkType, name="post_link_type"), nullable=False)
    direction: Mapped[LinkDirection] = mapped_column(
        _value_enum(LinkDirection, name="link_direction"),
        default=LinkDirection.NONE,
        nullable=False,
    )
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[VerificationStatus] = mapped_column(
        _value_enum(VerificationStatus, name="verification_status"),
        default=VerificationStatus.PROPOSED,
        nullable=False,
    )
    evidence_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pipeline_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    src_post: Mapped["Post"] = relationship(back_populates="outgoing_links", foreign_keys=[src_post_id])
    dst_post: Mapped["Post"] = relationship(back_populates="incoming_links", foreign_keys=[dst_post_id])


class PostFact(Base):
    __tablename__ = "post_facts"
    __table_args__ = (
        Index("ix_post_facts_created_at", "created_at"),
        Index("ix_post_facts_embedding_ref", "embedding_ref"),
        Index("ix_post_facts_entities_gin", "entities_json", postgresql_using="gin"),
        Index("ix_post_facts_topics_gin", "topics_json", postgresql_using="gin"),
        Index("ix_post_facts_key_numbers_gin", "key_numbers_json", postgresql_using="gin"),
        Index("ix_post_facts_fingerprint_gin", "fingerprint_json", postgresql_using="gin"),
    )

    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True)
    entities_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    topics_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    key_numbers_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    fingerprint_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    embedding_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    post: Mapped["Post"] = relationship(back_populates="facts")


class Process(Base):
    __tablename__ = "processes"
    __table_args__ = (
        Index("ix_processes_status", "status"),
        Index("ix_processes_started_at", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[VerificationStatus] = mapped_column(
        _value_enum(VerificationStatus, name="verification_status"),
        default=VerificationStatus.PROPOSED,
        nullable=False,
    )
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    events: Mapped[list["ProcessEvent"]] = relationship(back_populates="process")


class ProcessEvent(Base):
    __tablename__ = "process_events"
    __table_args__ = (
        UniqueConstraint(
            "process_id",
            "event_id",
            "relation_type",
            "direction",
            name="uq_process_events_proc_event_relation",
        ),
        Index("ix_process_events_event_id", "event_id"),
        Index("ix_process_events_status", "status"),
        Index("ix_process_events_evidence_gin", "evidence_json", postgresql_using="gin"),
    )

    process_id: Mapped[int] = mapped_column(ForeignKey("processes.id", ondelete="CASCADE"), primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), primary_key=True)
    relation_type: Mapped[ProcessRelationType] = mapped_column(
        _value_enum(ProcessRelationType, name="process_relation_type"),
        nullable=False,
    )
    direction: Mapped[LinkDirection] = mapped_column(
        _value_enum(LinkDirection, name="link_direction"),
        default=LinkDirection.NONE,
        nullable=False,
    )
    evidence_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[VerificationStatus] = mapped_column(
        _value_enum(VerificationStatus, name="verification_status"),
        default=VerificationStatus.PROPOSED,
        nullable=False,
    )
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pipeline_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    process: Mapped["Process"] = relationship(back_populates="events")
    event: Mapped["Event"] = relationship(back_populates="process_memberships")


class EventReport(Base):
    __tablename__ = "event_reports"
    __table_args__ = (
        Index("ix_event_reports_event_id", "event_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    report_text: Mapped[str] = mapped_column(Text)
    report_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    event: Mapped["Event"] = relationship(back_populates="reports")


class ProcessReport(Base):
    __tablename__ = "process_reports"
    __table_args__ = (
        Index("ix_process_reports_process_id", "process_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    process_id: Mapped[int] = mapped_column(ForeignKey("processes.id", ondelete="CASCADE"), nullable=False)
    report_text: Mapped[str] = mapped_column(Text)
    report_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class ArchivePostText(Base):
    __tablename__ = "archive_post_texts"
    __table_args__ = (
        UniqueConstraint("src_post_id", name="uq_archive_post_texts_src_post_id"),
        Index("ix_archive_post_texts_post_date", "post_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    src_post_id: Mapped[int] = mapped_column(Integer, nullable=False)
    channel_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tg_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    post_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    archived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class ArchiveEvent(Base):
    __tablename__ = "archive_events"
    __table_args__ = (
        UniqueConstraint("src_event_id", name="uq_archive_events_src_event_id"),
        Index("ix_archive_events_started_at", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    src_event_id: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    src_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    src_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    archived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class ArchiveProcess(Base):
    __tablename__ = "archive_processes"
    __table_args__ = (
        UniqueConstraint("src_process_id", name="uq_archive_processes_src_process_id"),
        Index("ix_archive_processes_started_at", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    src_process_id: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    src_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    src_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    archived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class ArchivePostReport(Base):
    __tablename__ = "archive_post_reports"
    __table_args__ = (
        UniqueConstraint("src_report_id", name="uq_archive_post_reports_src_report_id"),
        Index("ix_archive_post_reports_post_id", "post_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    src_report_id: Mapped[int] = mapped_column(Integer, nullable=False)
    post_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    src_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    archived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class ArchiveEventReport(Base):
    __tablename__ = "archive_event_reports"
    __table_args__ = (
        UniqueConstraint("src_event_report_id", name="uq_archive_event_reports_src_id"),
        Index("ix_archive_event_reports_event_id", "event_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    src_event_report_id: Mapped[int] = mapped_column(Integer, nullable=False)
    event_id: Mapped[int] = mapped_column(Integer, nullable=False)
    report_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    src_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    archived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class ArchiveProcessReport(Base):
    __tablename__ = "archive_process_reports"
    __table_args__ = (
        UniqueConstraint("src_process_report_id", name="uq_archive_process_reports_src_id"),
        Index("ix_archive_process_reports_process_id", "process_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    src_process_report_id: Mapped[int] = mapped_column(Integer, nullable=False)
    process_id: Mapped[int] = mapped_column(Integer, nullable=False)
    report_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    src_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    archived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class ArchiveWatermark(Base):
    __tablename__ = "archive_watermarks"
    __table_args__ = (
        UniqueConstraint("job_name", name="uq_archive_watermarks_job_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    archived_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rows_archived_last_run: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
