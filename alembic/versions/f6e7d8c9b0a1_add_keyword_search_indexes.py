"""add keyword search indexes

Revision ID: f6e7d8c9b0a1
Revises: cc33dd44ee55
Create Date: 2026-03-04 13:10:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f6e7d8c9b0a1"
down_revision: Union[str, Sequence[str], None] = "cc33dd44ee55"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_posts_fts_ru_gin
        ON posts
        USING gin (to_tsvector('russian', coalesce(text_normalized, text, '')))
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_posts_entities_search_lemmas_gin
        ON posts
        USING gin ((entities -> 'search_lemmas'))
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_posts_entities_search_lemmas_gin")
    op.execute("DROP INDEX IF EXISTS ix_posts_fts_ru_gin")
