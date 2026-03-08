"""add job dead letters

Revision ID: aa12bb34cc56
Revises: e6b4d1a9c2f0
Create Date: 2026-03-03 22:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "aa12bb34cc56"
down_revision: Union[str, Sequence[str], None] = "e6b4d1a9c2f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "job_dead_letters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_job_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_job_id", name="uq_job_dead_letters_source_job_id"),
    )
    op.create_index("ix_job_dead_letters_source_job_id", "job_dead_letters", ["source_job_id"], unique=False)
    op.create_index("ix_job_dead_letters_type", "job_dead_letters", ["type"], unique=False)
    op.create_index("ix_job_dead_letters_failed_at", "job_dead_letters", ["failed_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_job_dead_letters_failed_at", table_name="job_dead_letters")
    op.drop_index("ix_job_dead_letters_type", table_name="job_dead_letters")
    op.drop_index("ix_job_dead_letters_source_job_id", table_name="job_dead_letters")
    op.drop_table("job_dead_letters")
