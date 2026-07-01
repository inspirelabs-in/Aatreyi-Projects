"""per-user channel ownership: channels.owner_user_id

A channel is owned by a specific user. Normal users see ONLY the channels they own
(even within the same org); the GrabOn Platform Admin sees/monitors all. Existing
channels keep owner_user_id = NULL (admin-owned) — the admin still sees them.

Revision ID: mtorg02
Revises: mtorg01
Create Date: 2026-07-01 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "mtorg02"
down_revision: Union[str, None] = "mtorg01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE channels ADD COLUMN IF NOT EXISTS owner_user_id UUID")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_channels_owner_user') THEN
                ALTER TABLE channels ADD CONSTRAINT fk_channels_owner_user
                    FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE SET NULL;
            END IF;
        END $$
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_channels_owner_user_id ON channels(owner_user_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_channels_owner_user_id")
    op.execute("ALTER TABLE channels DROP CONSTRAINT IF EXISTS fk_channels_owner_user")
    op.execute("ALTER TABLE channels DROP COLUMN IF EXISTS owner_user_id")
