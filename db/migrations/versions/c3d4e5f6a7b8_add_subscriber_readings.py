"""add subscriber_readings (high-frequency subscriber samples)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-24 17:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'subscriber_readings',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('channel_id', sa.UUID(), nullable=False),
        sa.Column('subscriber_count', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['channel_id'], ['channels.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_subscriber_readings_channel_id', 'subscriber_readings', ['channel_id'])


def downgrade() -> None:
    op.drop_index('ix_subscriber_readings_channel_id', table_name='subscriber_readings')
    op.drop_table('subscriber_readings')
