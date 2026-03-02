"""add archive tables and process reports

Revision ID: b1c2d3e4f5a6
Revises: a4b5c6d7e8f9
Create Date: 2026-03-02 14:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "a4b5c6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "process_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("process_id", sa.Integer(), nullable=False),
        sa.Column("report_text", sa.Text(), nullable=False),
        sa.Column("report_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["process_id"], ["processes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_process_reports_process_id", "process_reports", ["process_id"], unique=False)

    op.create_table(
        "archive_post_texts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("src_post_id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=True),
        sa.Column("tg_message_id", sa.Integer(), nullable=True),
        sa.Column("post_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("src_post_id", name="uq_archive_post_texts_src_post_id"),
    )
    op.create_index("ix_archive_post_texts_post_date", "archive_post_texts", ["post_date"], unique=False)

    op.create_table(
        "archive_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("src_event_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("src_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("src_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("src_event_id", name="uq_archive_events_src_event_id"),
    )
    op.create_index("ix_archive_events_started_at", "archive_events", ["started_at"], unique=False)

    op.create_table(
        "archive_processes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("src_process_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("src_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("src_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("src_process_id", name="uq_archive_processes_src_process_id"),
    )
    op.create_index("ix_archive_processes_started_at", "archive_processes", ["started_at"], unique=False)

    op.create_table(
        "archive_post_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("src_report_id", sa.Integer(), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("src_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("src_report_id", name="uq_archive_post_reports_src_report_id"),
    )
    op.create_index("ix_archive_post_reports_post_id", "archive_post_reports", ["post_id"], unique=False)

    op.create_table(
        "archive_event_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("src_event_report_id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("report_text", sa.Text(), nullable=True),
        sa.Column("report_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("version", sa.Integer(), nullable=True),
        sa.Column("src_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("src_event_report_id", name="uq_archive_event_reports_src_id"),
    )
    op.create_index("ix_archive_event_reports_event_id", "archive_event_reports", ["event_id"], unique=False)

    op.create_table(
        "archive_process_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("src_process_report_id", sa.Integer(), nullable=False),
        sa.Column("process_id", sa.Integer(), nullable=False),
        sa.Column("report_text", sa.Text(), nullable=True),
        sa.Column("report_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("version", sa.Integer(), nullable=True),
        sa.Column("src_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("src_process_report_id", name="uq_archive_process_reports_src_id"),
    )
    op.create_index("ix_archive_process_reports_process_id", "archive_process_reports", ["process_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_archive_process_reports_process_id", table_name="archive_process_reports")
    op.drop_table("archive_process_reports")

    op.drop_index("ix_archive_event_reports_event_id", table_name="archive_event_reports")
    op.drop_table("archive_event_reports")

    op.drop_index("ix_archive_post_reports_post_id", table_name="archive_post_reports")
    op.drop_table("archive_post_reports")

    op.drop_index("ix_archive_processes_started_at", table_name="archive_processes")
    op.drop_table("archive_processes")

    op.drop_index("ix_archive_events_started_at", table_name="archive_events")
    op.drop_table("archive_events")

    op.drop_index("ix_archive_post_texts_post_date", table_name="archive_post_texts")
    op.drop_table("archive_post_texts")

    op.drop_index("ix_process_reports_process_id", table_name="process_reports")
    op.drop_table("process_reports")
