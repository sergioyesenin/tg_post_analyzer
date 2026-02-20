"""add post parent fields

Revision ID: c3a91e4d2f7b
Revises: 9f3c1a7be2d4
Create Date: 2026-02-20 20:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3a91e4d2f7b"
down_revision: Union[str, Sequence[str], None] = "9f3c1a7be2d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("posts", sa.Column("parent_tg_message_id", sa.Integer(), nullable=True))
    op.add_column("posts", sa.Column("parent_post_id", sa.Integer(), nullable=True))

    op.create_index(op.f("ix_posts_parent_tg_message_id"), "posts", ["parent_tg_message_id"], unique=False)
    op.create_index(op.f("ix_posts_parent_post_id"), "posts", ["parent_post_id"], unique=False)

    op.create_foreign_key(
        "fk_posts_parent_post_id_posts",
        "posts",
        "posts",
        ["parent_post_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_posts_parent_post_id_posts", "posts", type_="foreignkey")
    op.drop_index(op.f("ix_posts_parent_post_id"), table_name="posts")
    op.drop_index(op.f("ix_posts_parent_tg_message_id"), table_name="posts")
    op.drop_column("posts", "parent_post_id")
    op.drop_column("posts", "parent_tg_message_id")
