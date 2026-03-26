"""add comment peer identity

Revision ID: a9b8c7d6e5f4
Revises: f6e7d8c9b0a1
Create Date: 2026-03-25 23:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a9b8c7d6e5f4"
down_revision: Union[str, Sequence[str], None] = "f6e7d8c9b0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("comments", sa.Column("tg_peer_id", sa.BigInteger(), nullable=True))
    op.execute("UPDATE comments SET tg_peer_id = channel_id WHERE tg_peer_id IS NULL")
    op.alter_column("comments", "tg_peer_id", nullable=False)
    op.create_index(op.f("ix_comments_tg_peer_id"), "comments", ["tg_peer_id"], unique=False)
    op.drop_constraint("uq_comments_channel_msg", "comments", type_="unique")
    op.create_unique_constraint(
        "uq_comments_channel_peer_msg",
        "comments",
        ["channel_id", "tg_peer_id", "tg_message_id"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    duplicate_count = connection.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM (
                SELECT channel_id, tg_message_id
                FROM comments
                GROUP BY channel_id, tg_message_id
                HAVING COUNT(*) > 1
            ) dupes
            """
        )
    ).scalar_one()
    if int(duplicate_count or 0) > 0:
        raise RuntimeError(
            "Cannot downgrade comments peer identity migration after peer-scoped writes created duplicate "
            "(channel_id, tg_message_id) rows; manual collapse/archive is required before rollback."
        )

    op.drop_constraint("uq_comments_channel_peer_msg", "comments", type_="unique")
    op.create_unique_constraint("uq_comments_channel_msg", "comments", ["channel_id", "tg_message_id"])
    op.drop_index(op.f("ix_comments_tg_peer_id"), table_name="comments")
    op.drop_column("comments", "tg_peer_id")
