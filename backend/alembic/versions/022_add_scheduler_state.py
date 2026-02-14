"""add scheduler_state table for worker process IPC

Revision ID: 022_scheduler_state
Revises: 021_extra_config
Create Date: 2026-02-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '022_scheduler_state'
down_revision: Union[str, Sequence[str], None] = '021_extra_config'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create scheduler_state table for worker process state tracking."""
    op.create_table(
        'scheduler_state',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('scheduler_name', sa.String(100), nullable=False, unique=True, index=True),
        sa.Column('is_running', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_executing', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_heartbeat', sa.DateTime(timezone=True), nullable=True),
        sa.Column('worker_pid', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    """Drop scheduler_state table."""
    op.drop_table('scheduler_state')
