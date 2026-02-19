"""Add sleep mode config and state log tables

Revision ID: 028_sleep_mode
Revises: 027_residency_index
Create Date: 2026-02-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '028_sleep_mode'
down_revision: Union[str, Sequence[str], None] = '027_residency_index'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create sleep_config and sleep_state_logs tables."""
    # Singleton config table
    op.create_table(
        'sleep_config',
        sa.Column('id', sa.Integer(), nullable=False),
        # Auto-idle
        sa.Column('auto_idle_enabled', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('idle_timeout_minutes', sa.Integer(), nullable=False, server_default='15'),
        sa.Column('idle_cpu_threshold', sa.Float(), nullable=False, server_default='5.0'),
        sa.Column('idle_disk_io_threshold', sa.Float(), nullable=False, server_default='0.5'),
        sa.Column('idle_http_threshold', sa.Float(), nullable=False, server_default='5.0'),
        # Auto-escalation
        sa.Column('auto_escalation_enabled', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('escalation_after_minutes', sa.Integer(), nullable=False, server_default='60'),
        # Schedule
        sa.Column('schedule_enabled', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('schedule_sleep_time', sa.String(length=5), nullable=False, server_default='23:00'),
        sa.Column('schedule_wake_time', sa.String(length=5), nullable=False, server_default='06:00'),
        sa.Column('schedule_mode', sa.String(length=20), nullable=False, server_default='soft'),
        # WoL
        sa.Column('wol_mac_address', sa.String(length=17), nullable=True),
        sa.Column('wol_broadcast_address', sa.String(length=45), nullable=True),
        # Service pausing
        sa.Column('pause_monitoring', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('pause_disk_io', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('reduced_telemetry_interval', sa.Float(), nullable=False, server_default='30.0'),
        # Disk spindown
        sa.Column('disk_spindown_enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_sleep_config_id', 'sleep_config', ['id'])

    # State change history
    op.create_table(
        'sleep_state_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('previous_state', sa.String(length=30), nullable=False),
        sa.Column('new_state', sa.String(length=30), nullable=False),
        sa.Column('reason', sa.String(length=200), nullable=False),
        sa.Column('triggered_by', sa.String(length=30), nullable=False),
        sa.Column('details_json', sa.Text(), nullable=True),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_sleep_state_logs_id', 'sleep_state_logs', ['id'])
    op.create_index('ix_sleep_state_logs_timestamp', 'sleep_state_logs', ['timestamp'])

    # Insert default config row (singleton)
    op.execute("INSERT INTO sleep_config (id) VALUES (1)")


def downgrade() -> None:
    """Drop sleep mode tables."""
    op.drop_index('ix_sleep_state_logs_timestamp', table_name='sleep_state_logs')
    op.drop_index('ix_sleep_state_logs_id', table_name='sleep_state_logs')
    op.drop_table('sleep_state_logs')
    op.drop_index('ix_sleep_config_id', table_name='sleep_config')
    op.drop_table('sleep_config')
