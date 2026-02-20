"""add comment thread fields

Revision ID: 6d3b7f1e9c2a
Revises: 025822026b81
Create Date: 2026-02-19 22:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6d3b7f1e9c2a"
down_revision: Union[str, Sequence[str], None] = "025822026b81"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("comments", sa.Column("parent_tg_message_id", sa.Integer(), nullable=True))
    op.add_column("comments", sa.Column("parent_comment_id", sa.Integer(), nullable=True))
    op.add_column("comments", sa.Column("thread_root_tg_message_id", sa.Integer(), nullable=True))
    op.add_column("comments", sa.Column("depth", sa.Integer(), nullable=False, server_default="0"))

    op.create_index(op.f("ix_comments_parent_tg_message_id"), "comments", ["parent_tg_message_id"], unique=False)
    op.create_index(op.f("ix_comments_parent_comment_id"), "comments", ["parent_comment_id"], unique=False)
    op.create_index(op.f("ix_comments_thread_root_tg_message_id"), "comments", ["thread_root_tg_message_id"], unique=False)

    op.create_foreign_key(
        "fk_comments_parent_comment_id_comments",
        "comments",
        "comments",
        ["parent_comment_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.alter_column("comments", "depth", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_comments_parent_comment_id_comments", "comments", type_="foreignkey")

    op.drop_index(op.f("ix_comments_thread_root_tg_message_id"), table_name="comments")
    op.drop_index(op.f("ix_comments_parent_comment_id"), table_name="comments")
    op.drop_index(op.f("ix_comments_parent_tg_message_id"), table_name="comments")

    op.drop_column("comments", "depth")
    op.drop_column("comments", "thread_root_tg_message_id")
    op.drop_column("comments", "parent_comment_id")
    op.drop_column("comments", "parent_tg_message_id")
