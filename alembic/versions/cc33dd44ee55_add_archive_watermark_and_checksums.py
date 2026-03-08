"""add archive watermark and checksums

Revision ID: cc33dd44ee55
Revises: bb22cc33dd44
Create Date: 2026-03-03 22:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "cc33dd44ee55"
down_revision: Union[str, Sequence[str], None] = "bb22cc33dd44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("archive_post_texts", sa.Column("checksum", sa.String(length=64), nullable=True))
    op.add_column("archive_events", sa.Column("checksum", sa.String(length=64), nullable=True))
    op.add_column("archive_processes", sa.Column("checksum", sa.String(length=64), nullable=True))
    op.add_column("archive_post_reports", sa.Column("checksum", sa.String(length=64), nullable=True))
    op.add_column("archive_event_reports", sa.Column("checksum", sa.String(length=64), nullable=True))
    op.add_column("archive_process_reports", sa.Column("checksum", sa.String(length=64), nullable=True))

    op.create_table(
        "archive_watermarks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_name", sa.String(length=64), nullable=False),
        sa.Column("archived_before", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rows_archived_last_run", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_name", name="uq_archive_watermarks_job_name"),
    )
    op.create_index("ix_archive_watermarks_job_name", "archive_watermarks", ["job_name"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_archive_watermarks_job_name", table_name="archive_watermarks")
    op.drop_table("archive_watermarks")

    op.drop_column("archive_process_reports", "checksum")
    op.drop_column("archive_event_reports", "checksum")
    op.drop_column("archive_post_reports", "checksum")
    op.drop_column("archive_processes", "checksum")
    op.drop_column("archive_events", "checksum")
    op.drop_column("archive_post_texts", "checksum")
