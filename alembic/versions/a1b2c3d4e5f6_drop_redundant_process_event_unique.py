"""drop redundant process_events unique constraint

Revision ID: a1b2c3d4e5f6
Revises: f6e7d8c9b0a1
Create Date: 2026-03-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f6e7d8c9b0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_process_events_proc_event_relation",
        "process_events",
        type_="unique",
    )


def downgrade() -> None:
    op.create_unique_constraint(
        "uq_process_events_proc_event_relation",
        "process_events",
        ["process_id", "event_id", "relation_type", "direction"],
    )
