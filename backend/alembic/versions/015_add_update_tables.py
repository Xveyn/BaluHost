"""Add update service tables

Revision ID: 015_updates
Revises: 014_notifications
Create Date: 2026-02-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '015_updates'
down_revision: Union[str, None] = '014_notifications'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create update service tables."""
    # Update history table
    op.create_table(
        'update_history',
        sa.Column('id', sa.Integer(), nullable=False),
        # Version info
        sa.Column('from_version', sa.String(50), nullable=False),
        sa.Column('to_version', sa.String(50), nullable=False),
        sa.Column('channel', sa.String(20), nullable=False, server_default='stable'),
        # Git commits
        sa.Column('from_commit', sa.String(40), nullable=False),
        sa.Column('to_commit', sa.String(40), nullable=False),
        # Timestamps
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_seconds', sa.Integer(), nullable=True),
        # Status tracking
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('current_step', sa.String(255), nullable=True),
        sa.Column('progress_percent', sa.Integer(), nullable=False, server_default='0'),
        # Error handling
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('rollback_commit', sa.String(40), nullable=True),
        sa.Column('backup_id', sa.Integer(), nullable=True),
        # Initiator
        sa.Column('user_id', sa.Integer(), nullable=True),
        # Metadata
        sa.Column('changelog', sa.Text(), nullable=True),
        sa.Column('extra_data', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_update_history_id', 'update_history', ['id'], unique=False)
    op.create_index('ix_update_history_started_at', 'update_history', ['started_at'], unique=False)
    op.create_index('ix_update_history_status', 'update_history', ['status'], unique=False)
    op.create_index('ix_update_history_user_id', 'update_history', ['user_id'], unique=False)
    op.create_index('idx_update_history_status_started', 'update_history', ['status', 'started_at'], unique=False)
    op.create_index('idx_update_history_user_started', 'update_history', ['user_id', 'started_at'], unique=False)

    # Update config table (singleton)
    op.create_table(
        'update_config',
        sa.Column('id', sa.Integer(), nullable=False),
        # Auto-check settings
        sa.Column('auto_check_enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('check_interval_hours', sa.Integer(), nullable=False, server_default='24'),
        # Channel
        sa.Column('channel', sa.String(20), nullable=False, server_default='stable'),
        # Safety options
        sa.Column('auto_backup_before_update', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('require_healthy_services', sa.Boolean(), nullable=False, server_default='1'),
        # Last check info
        sa.Column('last_check_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_available_version', sa.String(50), nullable=True),
        # Auto-update settings
        sa.Column('auto_update_enabled', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('auto_update_window_start', sa.String(5), nullable=True),
        sa.Column('auto_update_window_end', sa.String(5), nullable=True),
        # Metadata
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_update_config_id', 'update_config', ['id'], unique=False)

    # Insert default config row
    op.execute(
        "INSERT INTO update_config (id, auto_check_enabled, check_interval_hours, channel, "
        "auto_backup_before_update, require_healthy_services, auto_update_enabled) "
        "VALUES (1, 1, 24, 'stable', 1, 1, 0)"
    )


def downgrade() -> None:
    """Drop update service tables."""
    op.drop_index('ix_update_config_id', table_name='update_config')
    op.drop_table('update_config')

    op.drop_index('idx_update_history_user_started', table_name='update_history')
    op.drop_index('idx_update_history_status_started', table_name='update_history')
    op.drop_index('ix_update_history_user_id', table_name='update_history')
    op.drop_index('ix_update_history_status', table_name='update_history')
    op.drop_index('ix_update_history_started_at', table_name='update_history')
    op.drop_index('ix_update_history_id', table_name='update_history')
    op.drop_table('update_history')
