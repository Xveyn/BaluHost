"""Add power_samples table for energy monitoring

Revision ID: 002_power_samples
Revises: 001_tapo_devices
Create Date: 2026-01-23 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002_power_samples'
down_revision: Union[str, Sequence[str], None] = '001_tapo_devices'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'power_samples',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('watts', sa.Float(), nullable=False),
        sa.Column('voltage', sa.Float(), nullable=True),
        sa.Column('current', sa.Float(), nullable=True),
        sa.Column('energy_today', sa.Float(), nullable=True),
        sa.Column('is_online', sa.Boolean(), nullable=False, server_default='1'),
        sa.ForeignKeyConstraint(['device_id'], ['tapo_devices.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Indexes for efficient queries
    op.create_index(op.f('ix_power_samples_device_id'), 'power_samples', ['device_id'], unique=False)
    op.create_index(op.f('ix_power_samples_timestamp'), 'power_samples', ['timestamp'], unique=False)
    op.create_index('ix_power_samples_device_timestamp', 'power_samples', ['device_id', 'timestamp'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_power_samples_device_timestamp', table_name='power_samples')
    op.drop_index(op.f('ix_power_samples_timestamp'), table_name='power_samples')
    op.drop_index(op.f('ix_power_samples_device_id'), table_name='power_samples')
    op.drop_table('power_samples')
