"""merge post_features into posts

Revision ID: a4b5c6d7e8f9
Revises: f1a2b3c4d5e6
Create Date: 2026-03-02 13:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("posts", sa.Column("text_normalized", sa.Text(), nullable=True))
    op.add_column("posts", sa.Column("content_hash", sa.String(length=128), nullable=True))
    op.add_column("posts", sa.Column("embedding", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("posts", sa.Column("entities", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("posts", sa.Column("lang", sa.String(length=16), nullable=True))
    op.add_column("posts", sa.Column("topic", sa.String(length=255), nullable=True))
    op.add_column("posts", sa.Column("analyzer_version", sa.String(length=64), nullable=False, server_default="v1"))
    op.create_index("ix_posts_content_hash", "posts", ["content_hash"], unique=False)

    op.execute(
        """
        UPDATE posts p
        SET
            text_normalized = pf.text_normalized,
            content_hash = pf.content_hash,
            embedding = CASE WHEN pf.embedding IS NULL THEN NULL ELSE pf.embedding::jsonb END,
            entities = CASE WHEN pf.entities IS NULL THEN NULL ELSE pf.entities::jsonb END,
            lang = pf.lang,
            topic = pf.topic,
            analyzer_version = COALESCE(pf.analyzer_version, 'v1')
        FROM post_features pf
        WHERE pf.post_id = p.id
        """
    )

    op.drop_index("ix_post_features_content_hash", table_name="post_features")
    op.drop_table("post_features")


def downgrade() -> None:
    op.create_table(
        "post_features",
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("text_normalized", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("embedding", sa.JSON(), nullable=True),
        sa.Column("entities", sa.JSON(), nullable=True),
        sa.Column("lang", sa.String(length=16), nullable=True),
        sa.Column("topic", sa.String(length=255), nullable=True),
        sa.Column("analyzer_version", sa.String(length=64), nullable=False, server_default="v1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("post_id"),
    )
    op.create_index("ix_post_features_content_hash", "post_features", ["content_hash"], unique=False)
    op.execute(
        """
        INSERT INTO post_features (post_id, text_normalized, content_hash, embedding, entities, lang, topic, analyzer_version)
        SELECT id, text_normalized, content_hash, embedding, entities, lang, topic, analyzer_version
        FROM posts
        """
    )

    op.drop_index("ix_posts_content_hash", table_name="posts")
    op.drop_column("posts", "analyzer_version")
    op.drop_column("posts", "topic")
    op.drop_column("posts", "lang")
    op.drop_column("posts", "entities")
    op.drop_column("posts", "embedding")
    op.drop_column("posts", "content_hash")
    op.drop_column("posts", "text_normalized")
