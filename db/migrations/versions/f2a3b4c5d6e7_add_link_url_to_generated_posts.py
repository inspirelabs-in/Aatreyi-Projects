"""add link_url to generated_posts

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-06-26 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE generated_posts ADD COLUMN IF NOT EXISTS link_url TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE generated_posts DROP COLUMN IF EXISTS link_url")
