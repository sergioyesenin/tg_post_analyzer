"""merge heads: post parent fields and evidence-first linking v2

Revision ID: d4f6a9b2c1de
Revises: c3a91e4d2f7b, b7e2f1d4c9aa
Create Date: 2026-02-23 12:40:00.000000

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "d4f6a9b2c1de"
down_revision: Union[str, Sequence[str], None] = ("c3a91e4d2f7b", "b7e2f1d4c9aa")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Merge migration: schema changes are already applied in parent revisions.
    pass


def downgrade() -> None:
    # No-op for merge revision.
    pass
