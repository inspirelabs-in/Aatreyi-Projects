"""add sample_posts to channel_dna

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-06-26 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE channel_dna ADD COLUMN IF NOT EXISTS sample_posts JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE channel_dna DROP COLUMN IF EXISTS sample_posts")
