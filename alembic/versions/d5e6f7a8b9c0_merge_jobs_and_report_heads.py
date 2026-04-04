"""merge jobs and report heads

Revision ID: d5e6f7a8b9c0
Revises: c1d2e3f4a5b6, e3f4a5b6c7d8
Create Date: 2026-03-31 00:15:00.000000

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, Sequence[str], None] = ("c1d2e3f4a5b6", "e3f4a5b6c7d8")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
