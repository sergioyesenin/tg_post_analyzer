"""set conservative ingest/jobs defaults

Revision ID: d9e8f7a6b5c4
Revises: c7d8e9f0a1b2
Create Date: 2026-03-02 15:35:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d9e8f7a6b5c4"
down_revision: Union[str, Sequence[str], None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO app_settings (key, value_json, description)
        VALUES
          (
            'ingest',
            '{
              "poll_seconds": 240,
              "max_posts_per_channel": 30,
              "comment_first_delay_hours": 2,
              "comment_interval_hours": 4,
              "comment_window_hours": 24,
              "collect_comments_sleep_min_ms": 2000,
              "collect_comments_sleep_max_ms": 4000,
              "comment_schedule_jitter_seconds": 7200
            }'::jsonb,
            'Conservative ingestion and comment collection schedule'
          ),
          (
            'jobs',
            '{
              "job_batch_size": 20,
              "collect_comments_quota_per_run": 5
            }'::jsonb,
            'Conservative jobs runner settings'
          )
        ON CONFLICT (key) DO UPDATE
        SET
          value_json = EXCLUDED.value_json,
          description = EXCLUDED.description
        """
    )


def downgrade() -> None:
    op.execute(
        """
        INSERT INTO app_settings (key, value_json, description)
        VALUES
          (
            'ingest',
            '{
              "poll_seconds": 90,
              "max_posts_per_channel": 100,
              "comment_first_delay_hours": 2,
              "comment_interval_hours": 2,
              "comment_window_hours": 24,
              "collect_comments_sleep_min_ms": 700,
              "collect_comments_sleep_max_ms": 1400,
              "comment_schedule_jitter_seconds": 1800
            }'::jsonb,
            'Ingestion and comment collection schedule'
          ),
          (
            'jobs',
            '{
              "job_batch_size": 50,
              "collect_comments_quota_per_run": 25
            }'::jsonb,
            'Jobs runner settings'
          )
        ON CONFLICT (key) DO UPDATE
        SET
          value_json = EXCLUDED.value_json,
          description = EXCLUDED.description
        """
    )
