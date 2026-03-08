"""set comment interval default to 2h

Revision ID: e6b4d1a9c2f0
Revises: d9e8f7a6b5c4
Create Date: 2026-03-03 21:15:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e6b4d1a9c2f0"
down_revision: Union[str, Sequence[str], None] = "d9e8f7a6b5c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE app_settings
        SET
          value_json = jsonb_set(
            COALESCE(value_json, '{}'::jsonb),
            '{comment_interval_hours}',
            '2'::jsonb,
            true
          ),
          description = COALESCE(description, 'Ingestion and comment collection schedule')
        WHERE key = 'ingest'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE app_settings
        SET value_json = jsonb_set(
            COALESCE(value_json, '{}'::jsonb),
            '{comment_interval_hours}',
            '4'::jsonb,
            true
        )
        WHERE key = 'ingest'
        """
    )
