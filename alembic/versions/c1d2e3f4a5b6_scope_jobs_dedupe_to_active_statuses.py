"""scope jobs dedupe to active statuses

Revision ID: c1d2e3f4a5b6
Revises: a9b8c7d6e5f4
Create Date: 2026-03-30 23:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "a9b8c7d6e5f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_jobs_dedupe_key", "jobs", type_="unique")
    op.create_index(
        "ux_jobs_active_dedupe_key",
        "jobs",
        ["dedupe_key"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )


def downgrade() -> None:
    op.drop_index("ux_jobs_active_dedupe_key", table_name="jobs")
    op.create_unique_constraint("uq_jobs_dedupe_key", "jobs", ["dedupe_key"])
