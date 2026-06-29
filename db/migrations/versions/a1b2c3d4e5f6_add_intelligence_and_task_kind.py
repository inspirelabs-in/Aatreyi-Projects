"""add intelligence blob to analytics_snapshots + kind to strategy_tasks

Additive only (Phase 1/2): nullable columns, no changes to existing data.

Revision ID: a1b2c3d4e5f6
Revises: 51ee07bccc46
Create Date: 2026-06-24 15:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '51ee07bccc46'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('analytics_snapshots',
                  sa.Column('intelligence', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('strategy_tasks', sa.Column('kind', sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column('strategy_tasks', 'kind')
    op.drop_column('analytics_snapshots', 'intelligence')
