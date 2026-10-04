"""add runtime heartbeats table

Revision ID: <auto>
Revises: <head>
Create Date: 2026-10-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f9e8d7c6b5a4"
down_revision: Union[str, Sequence[str], None] = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runtime_heartbeats",
        sa.Column("runtime_name", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Однократный перенос существующих heartbeat-ов из app_settings.
    op.execute(
        """
        INSERT INTO runtime_heartbeats (runtime_name, status, heartbeat_at, details_json, updated_at)
        SELECT
            REPLACE(key, 'runtime.', '') AS runtime_name,
            COALESCE(value_json->>'status', 'unknown') AS status,
            COALESCE(
                NULLIF(value_json->>'heartbeat_at', '')::timestamptz,
                updated_at,
                now()
            ) AS heartbeat_at,
            CASE
                WHEN value_json ? 'details' THEN value_json->'details'
                ELSE NULL
            END AS details_json,
            COALESCE(updated_at, now()) AS updated_at
        FROM app_settings
        WHERE key LIKE 'runtime.%'
        ON CONFLICT (runtime_name) DO NOTHING
        """
    )

    op.execute("DELETE FROM app_settings WHERE key LIKE 'runtime.%'")


def downgrade() -> None:
    # Восстанавливаем heartbeat-и обратно в app_settings, чтобы откат не терял данные.
    op.execute(
        """
        INSERT INTO app_settings (key, value_json, description, created_at, updated_at)
        SELECT
            'runtime.' || runtime_name,
            jsonb_build_object(
                'runtime', runtime_name,
                'status', status,
                'heartbeat_at', heartbeat_at,
                'details', COALESCE(details_json, '{}'::jsonb)
            ),
            'Runtime heartbeat for ' || runtime_name,
            updated_at,
            updated_at
        FROM runtime_heartbeats
        ON CONFLICT (key) DO NOTHING
        """
    )
    op.drop_table("runtime_heartbeats")
    