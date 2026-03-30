"""add report_json to post reports

Revision ID: e3f4a5b6c7d8
Revises: a1b2c3d4e5f6
Create Date: 2026-03-30 12:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("reports", sa.Column("report_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("archive_post_reports", sa.Column("report_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("archive_post_reports", "report_json")
    op.drop_column("reports", "report_json")
