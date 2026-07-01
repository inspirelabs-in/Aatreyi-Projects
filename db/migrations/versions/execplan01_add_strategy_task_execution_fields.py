"""add execution-planner slot fields to strategy_tasks

Revision ID: execplan01
Revises: compintel01
Create Date: 2026-07-01 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "execplan01"
down_revision: Union[str, None] = "compintel01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE strategy_tasks ADD COLUMN IF NOT EXISTS marketplace VARCHAR(24)")
    op.execute("ALTER TABLE strategy_tasks ADD COLUMN IF NOT EXISTS media_type VARCHAR(16)")
    op.execute("ALTER TABLE strategy_tasks ADD COLUMN IF NOT EXISTS scrape_at TIME")
    op.execute("ALTER TABLE strategy_tasks ADD COLUMN IF NOT EXISTS priority INTEGER")
    op.execute("ALTER TABLE strategy_tasks ADD COLUMN IF NOT EXISTS rationale TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE strategy_tasks DROP COLUMN IF EXISTS marketplace")
    op.execute("ALTER TABLE strategy_tasks DROP COLUMN IF EXISTS media_type")
    op.execute("ALTER TABLE strategy_tasks DROP COLUMN IF EXISTS scrape_at")
    op.execute("ALTER TABLE strategy_tasks DROP COLUMN IF EXISTS priority")
    op.execute("ALTER TABLE strategy_tasks DROP COLUMN IF EXISTS rationale")
