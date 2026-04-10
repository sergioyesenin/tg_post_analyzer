"""add reactions json to posts and comments

Revision ID: c4d5e6f7a8b9
Revises: d5e6f7a8b9c0, b2c3d4e5f6a7
Create Date: 2026-04-09 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, Sequence[str], None] = ("d5e6f7a8b9c0", "b2c3d4e5f6a7")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("posts", sa.Column("reactions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("comments", sa.Column("reactions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("comments", "reactions_json")
    op.drop_column("posts", "reactions_json")
