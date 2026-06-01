"""add commenters and long comments to posts

Revision ID: e7f8a9b0c1d2
Revises: c4d5e6f7a8b9
Create Date: 2026-04-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, Sequence[str], None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("posts", sa.Column("commenters", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column("posts", sa.Column("long_comments", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.alter_column("posts", "commenters", server_default=None)
    op.alter_column("posts", "long_comments", server_default=None)


def downgrade() -> None:
    op.drop_column("posts", "long_comments")
    op.drop_column("posts", "commenters")
