"""add competitor intelligence fields (type, similarity_breakdown, intelligence)

Revision ID: compintel01
Revises: a3b4c5d6e7f8
Create Date: 2026-06-29 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "compintel01"
down_revision: Union[str, None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE competitors ADD COLUMN IF NOT EXISTS competitor_type VARCHAR(16)")
    op.execute("ALTER TABLE competitors ADD COLUMN IF NOT EXISTS similarity_breakdown JSONB")
    op.execute("ALTER TABLE competitors ADD COLUMN IF NOT EXISTS intelligence JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE competitors DROP COLUMN IF EXISTS competitor_type")
    op.execute("ALTER TABLE competitors DROP COLUMN IF EXISTS similarity_breakdown")
    op.execute("ALTER TABLE competitors DROP COLUMN IF EXISTS intelligence")
