"""Add fan schedule entries table

Revision ID: 026_fan_schedule
Revises: 74aa416f29d6
Create Date: 2026-02-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '026_fan_schedule'
down_revision: Union[str, Sequence[str], None] = '74aa416f29d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create fan_schedule_entries table."""
    op.create_table(
        'fan_schedule_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fan_id', sa.String(length=100), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('start_time', sa.String(length=5), nullable=False),
        sa.Column('end_time', sa.String(length=5), nullable=False),
        sa.Column('curve_json', sa.Text(), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_fan_schedule_entries_id', 'fan_schedule_entries', ['id'])
    op.create_index('ix_fan_schedule_entries_fan_id', 'fan_schedule_entries', ['fan_id'])


def downgrade() -> None:
    """Drop fan_schedule_entries table."""
    op.drop_index('ix_fan_schedule_entries_fan_id', table_name='fan_schedule_entries')
    op.drop_index('ix_fan_schedule_entries_id', table_name='fan_schedule_entries')
    op.drop_table('fan_schedule_entries')
