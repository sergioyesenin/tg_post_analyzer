"""add jobs table

Revision ID: e2a1c4d8f9b0
Revises: d4f6a9b2c1de
Create Date: 2026-03-02 12:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "e2a1c4d8f9b0"
down_revision: Union[str, Sequence[str], None] = "d4f6a9b2c1de"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("locked_by", sa.String(length=64), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("dedupe_key", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key", name="uq_jobs_dedupe_key"),
    )

    op.create_index("ix_jobs_status_retry_priority", "jobs", ["status", "retry_at", "priority"], unique=False)
    op.create_index("ix_jobs_type_status", "jobs", ["type", "status"], unique=False)
    op.create_index("ix_jobs_type", "jobs", ["type"], unique=False)
    op.create_index("ix_jobs_status", "jobs", ["status"], unique=False)
    op.create_index("ix_jobs_priority", "jobs", ["priority"], unique=False)
    op.create_index("ix_jobs_run_at", "jobs", ["run_at"], unique=False)
    op.create_index("ix_jobs_retry_at", "jobs", ["retry_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_jobs_retry_at", table_name="jobs")
    op.drop_index("ix_jobs_run_at", table_name="jobs")
    op.drop_index("ix_jobs_priority", table_name="jobs")
    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_index("ix_jobs_type", table_name="jobs")
    op.drop_index("ix_jobs_type_status", table_name="jobs")
    op.drop_index("ix_jobs_status_retry_priority", table_name="jobs")
    op.drop_table("jobs")
