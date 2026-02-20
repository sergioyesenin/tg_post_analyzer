"""add linking graph tables

Revision ID: 9f3c1a7be2d4
Revises: 6d3b7f1e9c2a
Create Date: 2026-02-20 14:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9f3c1a7be2d4"
down_revision: Union[str, Sequence[str], None] = "6d3b7f1e9c2a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("summary_current", sa.Text(), nullable=True),
        sa.Column("reporter_version", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_events_status"), "events", ["status"], unique=False)
    op.create_index(op.f("ix_events_first_seen_at"), "events", ["first_seen_at"], unique=False)
    op.create_index(op.f("ix_events_last_seen_at"), "events", ["last_seen_at"], unique=False)

    op.create_table(
        "post_features",
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("text_normalized", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("embedding", sa.JSON(), nullable=True),
        sa.Column("entities", sa.JSON(), nullable=True),
        sa.Column("lang", sa.String(length=16), nullable=True),
        sa.Column("topic", sa.String(length=255), nullable=True),
        sa.Column("analyzer_version", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("post_id"),
    )
    op.create_index(op.f("ix_post_features_content_hash"), "post_features", ["content_hash"], unique=False)

    op.create_table(
        "event_posts",
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_id", "post_id"),
    )
    op.create_index("ix_event_posts_post_id", "event_posts", ["post_id"], unique=False)

    op.create_table(
        "post_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("src_post_id", sa.Integer(), nullable=False),
        sa.Column("dst_post_id", sa.Integer(), nullable=False),
        sa.Column("link_type", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("model_version", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("src_post_id <> dst_post_id", name="ck_post_links_src_ne_dst"),
        sa.ForeignKeyConstraint(["dst_post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["src_post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("src_post_id", "dst_post_id", "link_type", name="uq_post_links_src_dst_type"),
    )
    op.create_index("ix_post_links_dst_post_id", "post_links", ["dst_post_id"], unique=False)
    op.create_index("ix_post_links_src_post_id", "post_links", ["src_post_id"], unique=False)
    op.create_index("ix_post_links_type", "post_links", ["link_type"], unique=False)

    op.create_table(
        "event_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("report_text", sa.Text(), nullable=False),
        sa.Column("report_json", sa.JSON(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_event_reports_event_id", "event_reports", ["event_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_event_reports_event_id", table_name="event_reports")
    op.drop_table("event_reports")

    op.drop_index("ix_post_links_type", table_name="post_links")
    op.drop_index("ix_post_links_src_post_id", table_name="post_links")
    op.drop_index("ix_post_links_dst_post_id", table_name="post_links")
    op.drop_table("post_links")

    op.drop_index("ix_event_posts_post_id", table_name="event_posts")
    op.drop_table("event_posts")

    op.drop_index(op.f("ix_post_features_content_hash"), table_name="post_features")
    op.drop_table("post_features")

    op.drop_index(op.f("ix_events_last_seen_at"), table_name="events")
    op.drop_index(op.f("ix_events_first_seen_at"), table_name="events")
    op.drop_index(op.f("ix_events_status"), table_name="events")
    op.drop_table("events")
