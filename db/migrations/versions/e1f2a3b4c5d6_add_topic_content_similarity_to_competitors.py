"""add topic_similarity and content_similarity to competitors

Revision ID: e1f2a3b4c5d6
Revises: d4e5f6a7b8c9
Create Date: 2026-06-25 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE competitors ADD COLUMN IF NOT EXISTS topic_similarity FLOAT")
    op.execute("ALTER TABLE competitors ADD COLUMN IF NOT EXISTS content_similarity FLOAT")


def downgrade() -> None:
    op.drop_column("competitors", "content_similarity")
    op.drop_column("competitors", "topic_similarity")
