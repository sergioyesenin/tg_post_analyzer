"""evidence first linking v2

Revision ID: b7e2f1d4c9aa
Revises: 9f3c1a7be2d4
Create Date: 2026-02-23 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b7e2f1d4c9aa"
down_revision: Union[str, Sequence[str], None] = "9f3c1a7be2d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


verification_status = postgresql.ENUM(
    "proposed",
    "verified",
    "rejected",
    "needs_review",
    name="verification_status",
    create_type=False,
)
link_direction = postgresql.ENUM(
    "src_to_dst",
    "dst_to_src",
    "none",
    name="link_direction",
    create_type=False,
)
post_link_type = postgresql.ENUM(
    "same_event",
    "update",
    "contradiction",
    "cause",
    "consequence",
    "background",
    "related",
    "unrelated",
    name="post_link_type",
    create_type=False,
)
process_relation_type = postgresql.ENUM(
    "cause",
    "effect",
    "update",
    "contradiction",
    "related",
    name="process_relation_type",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    verification_status.create(bind, checkfirst=True)
    link_direction.create(bind, checkfirst=True)
    post_link_type.create(bind, checkfirst=True)
    process_relation_type.create(bind, checkfirst=True)

    with op.batch_alter_table("events") as batch_op:
        batch_op.add_column(sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("created_by", sa.String(length=64), nullable=True))
    op.execute("UPDATE events SET started_at = COALESCE(started_at, first_seen_at)")
    op.execute("UPDATE events SET ended_at = COALESCE(ended_at, last_seen_at)")
    with op.batch_alter_table("events") as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=sa.String(length=50),
            type_=verification_status,
            postgresql_using=(
                "CASE "
                "WHEN status IN ('verified','rejected','proposed','needs_review') THEN status "
                "ELSE 'proposed' END::verification_status"
            ),
            existing_nullable=False,
        )
    op.drop_index("ix_events_first_seen_at", table_name="events")
    op.drop_index("ix_events_last_seen_at", table_name="events")
    op.create_index("ix_events_started_at", "events", ["started_at"], unique=False)
    op.create_index("ix_events_ended_at", "events", ["ended_at"], unique=False)
    with op.batch_alter_table("events") as batch_op:
        batch_op.drop_column("first_seen_at")
        batch_op.drop_column("last_seen_at")
        batch_op.drop_column("summary_current")
        batch_op.drop_column("reporter_version")

    with op.batch_alter_table("event_posts") as batch_op:
        batch_op.add_column(sa.Column("evidence_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
        batch_op.add_column(sa.Column("score", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "status",
                verification_status,
                nullable=False,
                server_default="proposed",
            )
        )
        batch_op.add_column(sa.Column("model_version", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("pipeline_version", sa.String(length=64), nullable=True))
        batch_op.add_column(
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))
        )
    op.execute("UPDATE event_posts SET score = confidence")
    op.execute("UPDATE event_posts SET created_at = linked_at")
    op.execute("UPDATE event_posts SET status = 'verified'::verification_status")
    with op.batch_alter_table("event_posts") as batch_op:
        batch_op.drop_column("confidence")
        batch_op.drop_column("linked_at")
    op.create_index("ix_event_posts_status", "event_posts", ["status"], unique=False)
    op.create_index("ix_event_posts_evidence_gin", "event_posts", ["evidence_json"], unique=False, postgresql_using="gin")

    with op.batch_alter_table("post_links") as batch_op:
        batch_op.add_column(
            sa.Column("direction", link_direction, nullable=False, server_default="none")
        )
        batch_op.add_column(sa.Column("score", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column("status", verification_status, nullable=False, server_default="proposed")
        )
        batch_op.add_column(sa.Column("evidence_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
        batch_op.add_column(sa.Column("pipeline_version", sa.String(length=64), nullable=True))
        batch_op.add_column(
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))
        )
    op.execute("UPDATE post_links SET score = confidence")
    op.execute("UPDATE post_links SET evidence_json = evidence")
    op.execute("UPDATE post_links SET status = 'verified'::verification_status")
    op.execute(
        """
        UPDATE post_links
        SET link_type = CASE
            WHEN UPPER(link_type) IN ('SAME_EVENT') THEN 'same_event'
            WHEN UPPER(link_type) IN ('UPDATE') THEN 'update'
            WHEN UPPER(link_type) IN ('REFUTES', 'CONTRADICTION') THEN 'contradiction'
            WHEN UPPER(link_type) IN ('CAUSE_EFFECT', 'CAUSE') THEN 'cause'
            WHEN UPPER(link_type) IN ('CONSEQUENCE', 'EFFECT') THEN 'consequence'
            WHEN UPPER(link_type) IN ('BACKGROUND') THEN 'background'
            WHEN UPPER(link_type) IN ('UNRELATED') THEN 'unrelated'
            ELSE 'related'
        END
        """
    )
    with op.batch_alter_table("post_links") as batch_op:
        batch_op.alter_column(
            "link_type",
            existing_type=sa.String(length=32),
            type_=post_link_type,
            postgresql_using="link_type::post_link_type",
            existing_nullable=False,
        )
        batch_op.drop_column("confidence")
        batch_op.drop_column("evidence")
    op.create_index("ix_post_links_status", "post_links", ["status"], unique=False)
    op.create_index("ix_post_links_score", "post_links", ["score"], unique=False)
    op.create_index("ix_post_links_evidence_gin", "post_links", ["evidence_json"], unique=False, postgresql_using="gin")

    op.create_table(
        "post_facts",
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("entities_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("topics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("key_numbers_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fingerprint_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("embedding_ref", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("post_id"),
    )
    op.create_index("ix_post_facts_created_at", "post_facts", ["created_at"], unique=False)
    op.create_index("ix_post_facts_embedding_ref", "post_facts", ["embedding_ref"], unique=False)
    op.create_index("ix_post_facts_entities_gin", "post_facts", ["entities_json"], unique=False, postgresql_using="gin")
    op.create_index("ix_post_facts_topics_gin", "post_facts", ["topics_json"], unique=False, postgresql_using="gin")
    op.create_index("ix_post_facts_key_numbers_gin", "post_facts", ["key_numbers_json"], unique=False, postgresql_using="gin")
    op.create_index("ix_post_facts_fingerprint_gin", "post_facts", ["fingerprint_json"], unique=False, postgresql_using="gin")

    op.create_table(
        "processes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("status", verification_status, nullable=False, server_default="proposed"),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_processes_status", "processes", ["status"], unique=False)
    op.create_index("ix_processes_started_at", "processes", ["started_at"], unique=False)

    op.create_table(
        "process_events",
        sa.Column("process_id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("relation_type", process_relation_type, nullable=False),
        sa.Column("direction", link_direction, nullable=False, server_default="none"),
        sa.Column("evidence_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("status", verification_status, nullable=False, server_default="proposed"),
        sa.Column("model_version", sa.String(length=64), nullable=True),
        sa.Column("pipeline_version", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["process_id"], ["processes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("process_id", "event_id"),
        sa.UniqueConstraint(
            "process_id",
            "event_id",
            "relation_type",
            "direction",
            name="uq_process_events_proc_event_relation",
        ),
    )
    op.create_index("ix_process_events_event_id", "process_events", ["event_id"], unique=False)
    op.create_index("ix_process_events_status", "process_events", ["status"], unique=False)
    op.create_index("ix_process_events_evidence_gin", "process_events", ["evidence_json"], unique=False, postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("ix_process_events_evidence_gin", table_name="process_events")
    op.drop_index("ix_process_events_status", table_name="process_events")
    op.drop_index("ix_process_events_event_id", table_name="process_events")
    op.drop_table("process_events")

    op.drop_index("ix_processes_started_at", table_name="processes")
    op.drop_index("ix_processes_status", table_name="processes")
    op.drop_table("processes")

    op.drop_index("ix_post_facts_fingerprint_gin", table_name="post_facts")
    op.drop_index("ix_post_facts_key_numbers_gin", table_name="post_facts")
    op.drop_index("ix_post_facts_topics_gin", table_name="post_facts")
    op.drop_index("ix_post_facts_entities_gin", table_name="post_facts")
    op.drop_index("ix_post_facts_embedding_ref", table_name="post_facts")
    op.drop_index("ix_post_facts_created_at", table_name="post_facts")
    op.drop_table("post_facts")

    op.drop_index("ix_post_links_evidence_gin", table_name="post_links")
    op.drop_index("ix_post_links_score", table_name="post_links")
    op.drop_index("ix_post_links_status", table_name="post_links")
    with op.batch_alter_table("post_links") as batch_op:
        batch_op.add_column(sa.Column("confidence", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("evidence", sa.JSON(), nullable=True))
    op.execute("UPDATE post_links SET confidence = score")
    op.execute("UPDATE post_links SET evidence = evidence_json")
    with op.batch_alter_table("post_links") as batch_op:
        batch_op.alter_column("link_type", type_=sa.String(length=32), existing_type=post_link_type)
        batch_op.drop_column("updated_at")
        batch_op.drop_column("pipeline_version")
        batch_op.drop_column("evidence_json")
        batch_op.drop_column("status")
        batch_op.drop_column("score")
        batch_op.drop_column("direction")

    op.drop_index("ix_event_posts_evidence_gin", table_name="event_posts")
    op.drop_index("ix_event_posts_status", table_name="event_posts")
    with op.batch_alter_table("event_posts") as batch_op:
        batch_op.add_column(sa.Column("confidence", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("linked_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE event_posts SET confidence = score")
    op.execute("UPDATE event_posts SET linked_at = created_at")
    with op.batch_alter_table("event_posts") as batch_op:
        batch_op.drop_column("created_at")
        batch_op.drop_column("pipeline_version")
        batch_op.drop_column("model_version")
        batch_op.drop_column("status")
        batch_op.drop_column("score")
        batch_op.drop_column("evidence_json")

    with op.batch_alter_table("events") as batch_op:
        batch_op.add_column(sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("summary_current", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("reporter_version", sa.String(length=64), nullable=True))
    op.execute("UPDATE events SET first_seen_at = started_at")
    op.execute("UPDATE events SET last_seen_at = ended_at")
    op.drop_index("ix_events_ended_at", table_name="events")
    op.drop_index("ix_events_started_at", table_name="events")
    op.create_index("ix_events_first_seen_at", "events", ["first_seen_at"], unique=False)
    op.create_index("ix_events_last_seen_at", "events", ["last_seen_at"], unique=False)
    with op.batch_alter_table("events") as batch_op:
        batch_op.alter_column("status", type_=sa.String(length=50), existing_type=verification_status)
        batch_op.drop_column("created_by")
        batch_op.drop_column("ended_at")
        batch_op.drop_column("started_at")

    process_relation_type.drop(op.get_bind(), checkfirst=True)
    post_link_type.drop(op.get_bind(), checkfirst=True)
    link_direction.drop(op.get_bind(), checkfirst=True)
    verification_status.drop(op.get_bind(), checkfirst=True)
