"""Drop legacy tapo_devices and power_samples tables.

These tables have been superseded by smart_devices and smart_device_samples.
Data was migrated in revision 044_tapo_migration.

Revision ID: 045_drop_legacy_tapo
Revises: 044_tapo_migration
Create Date: 2026-03-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '045_drop_legacy_tapo'
down_revision: Union[str, None] = '044_tapo_migration'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop power_samples first (has FK to tapo_devices)
    op.drop_table('power_samples')
    op.drop_table('tapo_devices')


def downgrade() -> None:
    # Recreate tapo_devices
    op.create_table(
        'tapo_devices',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('device_type', sa.String(length=50), nullable=False, server_default='P115'),
        sa.Column('ip_address', sa.String(length=45), nullable=False),
        sa.Column('email_encrypted', sa.Text(), nullable=True),
        sa.Column('password_encrypted', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('is_monitoring', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('last_connected', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('created_by_user_id', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    # Recreate power_samples
    op.create_table(
        'power_samples',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('device_id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('watts', sa.Float(), nullable=False),
        sa.Column('voltage', sa.Float(), nullable=True),
        sa.Column('current', sa.Float(), nullable=True),
        sa.Column('energy_today', sa.Float(), nullable=True),
        sa.Column('is_online', sa.Boolean(), nullable=False, server_default='1'),
        sa.ForeignKeyConstraint(['device_id'], ['tapo_devices.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_power_samples_device_id', 'power_samples', ['device_id'])
    op.create_index('ix_power_samples_timestamp', 'power_samples', ['timestamp'])
