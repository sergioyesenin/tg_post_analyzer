"""add app settings table

Revision ID: c7d8e9f0a1b2
Revises: b1c2d3e4f5a6
Create Date: 2026-03-02 14:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_app_settings_key"),
    )
    op.create_index("ix_app_settings_key", "app_settings", ["key"], unique=False)

    op.execute(
        """
        INSERT INTO app_settings (key, value_json, description)
        VALUES
            ('ingest', '{"poll_seconds": 90, "max_posts_per_channel": 100, "comment_first_delay_hours": 2, "comment_interval_hours": 2, "comment_window_hours": 24}', 'Ingestion and comment collection schedule'),
            ('reports', '{"post_report_delay_hours": 6, "min_comments": 20, "report_word_target": 350, "report_word_min": 200, "report_word_max": 500}', 'Report generation parameters'),
            ('retention', '{"retention_days": 30, "archive_batch_size": 1000}', 'Archive and retention settings'),
            ('jobs', '{"job_batch_size": 50}', 'Jobs runner settings'),
            ('api', '{"top_posts_default_limit": 20}', 'API default values')
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_app_settings_key", table_name="app_settings")
    op.drop_table("app_settings")
