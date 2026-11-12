"""sleep command queue (#823)

Revision ID: a7d4e0f6cb39
Revises: f6c3d9e5ba28
Create Date: 2026-11-12 00:00:00.000000

Manual sleep actions (soft sleep, wake, suspend) and the auto-wake are
executed by the primary worker only; followers hand them over through this
table. Same columns as ``power_commands`` / ``gpu_power_commands`` (incl. the
caller deadline ``expires_at``), driven by the shared ``DbCommandQueue``.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7d4e0f6cb39'
down_revision: Union[str, Sequence[str], None] = 'f6c3d9e5ba28'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'sleep_commands',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('command', sa.String(length=40), nullable=False),
        sa.Column('payload_json', sa.Text(), nullable=True),
        sa.Column('requested_by', sa.String(length=100), nullable=True),
        sa.Column(
            'requested_at', sa.DateTime(timezone=True),
            server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False,
        ),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'idx_sleep_commands_status_requested',
        'sleep_commands',
        ['status', 'requested_at'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_sleep_commands_status_requested', table_name='sleep_commands')
    op.drop_table('sleep_commands')
