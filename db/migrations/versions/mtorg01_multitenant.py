"""multi-tenant: organizations, users, organization_settings + channels.organization_id

Seeds the GrabOn organization, its settings, and a Platform Admin user, then
backfills every existing channel into GrabOn and makes channels.organization_id
NOT NULL. Idempotent (IF NOT EXISTS / ON CONFLICT) so re-runs are safe.

Revision ID: mtorg01
Revises: execplan01
Create Date: 2026-07-01 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "mtorg01"
down_revision: Union[str, None] = "execplan01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Fixed seed UUIDs (migration-internal only — application code resolves GrabOn by
# slug='grabon', never by these literals).
_GRABON_ORG = "a0000000-0000-4000-8000-000000000001"
_GRABON_SETTINGS = "a0000000-0000-4000-8000-000000000002"
_GRABON_ADMIN = "a0000000-0000-4000-8000-000000000003"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS organizations (
            id UUID PRIMARY KEY,
            name VARCHAR(128) NOT NULL,
            slug VARCHAR(64) NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY,
            name VARCHAR(128) NOT NULL,
            email VARCHAR(255) UNIQUE,
            organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            is_admin BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_users_organization_id ON users(organization_id)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS organization_settings (
            id UUID PRIMARY KEY,
            organization_id UUID NOT NULL UNIQUE REFERENCES organizations(id) ON DELETE CASCADE,
            auto_approve_content BOOLEAN NOT NULL DEFAULT false,
            daily_target_posts INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    op.execute("ALTER TABLE channels ADD COLUMN IF NOT EXISTS organization_id UUID")

    # Seed the single GrabOn organization + its settings + the Platform Admin user.
    op.execute(
        f"INSERT INTO organizations (id, name, slug) "
        f"VALUES ('{_GRABON_ORG}', 'GrabOn', 'grabon') ON CONFLICT (slug) DO NOTHING"
    )
    op.execute(
        f"INSERT INTO organization_settings (id, organization_id, auto_approve_content, daily_target_posts) "
        f"VALUES ('{_GRABON_SETTINGS}', "
        f"(SELECT id FROM organizations WHERE slug='grabon'), false, NULL) "
        f"ON CONFLICT (organization_id) DO NOTHING"
    )
    op.execute(
        f"INSERT INTO users (id, name, email, organization_id, is_admin) "
        f"VALUES ('{_GRABON_ADMIN}', 'GrabOn Platform Admin', 'admin@grabon.in', "
        f"(SELECT id FROM organizations WHERE slug='grabon'), true) "
        f"ON CONFLICT (email) DO NOTHING"
    )

    # Backfill existing channels into GrabOn, then lock the column down.
    op.execute(
        "UPDATE channels SET organization_id = (SELECT id FROM organizations WHERE slug='grabon') "
        "WHERE organization_id IS NULL"
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_channels_organization'
            ) THEN
                ALTER TABLE channels ADD CONSTRAINT fk_channels_organization
                    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT;
            END IF;
        END $$
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_channels_organization_id ON channels(organization_id)")
    op.execute("ALTER TABLE channels ALTER COLUMN organization_id SET NOT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE channels ALTER COLUMN organization_id DROP NOT NULL")
    op.execute("ALTER TABLE channels DROP CONSTRAINT IF EXISTS fk_channels_organization")
    op.execute("DROP INDEX IF EXISTS ix_channels_organization_id")
    op.execute("ALTER TABLE channels DROP COLUMN IF EXISTS organization_id")
    op.execute("DROP TABLE IF EXISTS organization_settings")
    op.execute("DROP TABLE IF EXISTS users")
    op.execute("DROP TABLE IF EXISTS organizations")
