"""Add smart_devices and smart_device_samples tables

Revision ID: 020_smart_devices
Revises: 019_size_bigint
Create Date: 2026-03-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '020_smart_devices'
down_revision: Union[str, None] = '019_size_bigint'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create smart_devices and smart_device_samples tables."""
    op.create_table(
        'smart_devices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('plugin_name', sa.String(length=100), nullable=False),
        sa.Column('device_type_id', sa.String(length=100), nullable=False),
        sa.Column('address', sa.String(length=255), nullable=False),
        sa.Column('mac_address', sa.String(length=17), nullable=True),
        sa.Column('capabilities', sa.JSON(), nullable=False),
        sa.Column('config_secret', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('is_online', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('last_seen', sa.DateTime(), nullable=True),
        sa.Column('last_error', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_smart_devices_id'), 'smart_devices', ['id'], unique=False)
    op.create_index('idx_smart_device_plugin', 'smart_devices', ['plugin_name', 'is_active'], unique=False)

    op.create_table(
        'smart_device_samples',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.Integer(), nullable=False),
        sa.Column('capability', sa.String(length=50), nullable=False),
        sa.Column('data_json', sa.Text(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['device_id'], ['smart_devices.id'], ondelete='CASCADE'),
    )
    op.create_index(op.f('ix_smart_device_samples_id'), 'smart_device_samples', ['id'], unique=False)
    op.create_index('idx_sample_device_time', 'smart_device_samples', ['device_id', 'timestamp'], unique=False)
    op.create_index('idx_sample_capability', 'smart_device_samples', ['device_id', 'capability', 'timestamp'], unique=False)


def downgrade() -> None:
    """Drop smart_device_samples and smart_devices tables."""
    op.drop_index('idx_sample_capability', table_name='smart_device_samples')
    op.drop_index('idx_sample_device_time', table_name='smart_device_samples')
    op.drop_index(op.f('ix_smart_device_samples_id'), table_name='smart_device_samples')
    op.drop_table('smart_device_samples')

    op.drop_index('idx_smart_device_plugin', table_name='smart_devices')
    op.drop_index(op.f('ix_smart_devices_id'), table_name='smart_devices')
    op.drop_table('smart_devices')
