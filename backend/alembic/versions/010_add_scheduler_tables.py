"""add scheduler execution history and config tables

Revision ID: 010
Revises: 009
Create Date: 2026-01-29

Tables:
- scheduler_executions: Track all scheduler job executions
- scheduler_configs: Store dynamic scheduler configuration
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '010_scheduler_tables'
down_revision: Union[str, None] = '009_fan_hysteresis'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create scheduler_executions and scheduler_configs tables."""
    # Create scheduler_executions table
    op.create_table(
        'scheduler_executions',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('scheduler_name', sa.String(100), nullable=False, index=True),
        sa.Column('job_id', sa.String(255), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, default='running', index=True),
        sa.Column('trigger_type', sa.String(20), nullable=False, default='scheduled'),
        sa.Column('result_summary', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True, index=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
    )

    # Create indexes for common queries
    op.create_index(
        'idx_scheduler_exec_name_started',
        'scheduler_executions',
        ['scheduler_name', 'started_at']
    )
    op.create_index(
        'idx_scheduler_exec_status_started',
        'scheduler_executions',
        ['status', 'started_at']
    )
    op.create_index(
        'idx_scheduler_exec_name_status',
        'scheduler_executions',
        ['scheduler_name', 'status']
    )

    # Create scheduler_configs table
    op.create_table(
        'scheduler_configs',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('scheduler_name', sa.String(100), nullable=False, unique=True, index=True),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, default=True),
        sa.Column('interval_seconds', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_by', sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    """Drop scheduler tables."""
    op.drop_table('scheduler_configs')

    op.drop_index('idx_scheduler_exec_name_status', table_name='scheduler_executions')
    op.drop_index('idx_scheduler_exec_status_started', table_name='scheduler_executions')
    op.drop_index('idx_scheduler_exec_name_started', table_name='scheduler_executions')
    op.drop_table('scheduler_executions')
