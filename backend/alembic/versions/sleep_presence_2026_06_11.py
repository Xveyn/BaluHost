"""add presence_sessions table + presence config to sleep_config (issue #214)

Revision ID: sleep_presence_2026_06_11
Revises: c7f2a1b4d8e9
Create Date: 2026-06-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'sleep_presence_2026_06_11'
down_revision: Union[str, Sequence[str], None] = 'c7f2a1b4d8e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'presence_sessions',
        sa.Column('client_id', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('client_type', sa.String(length=20), nullable=False, server_default='web'),
        sa.Column('last_heartbeat_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('client_id'),
    )
    op.create_index('ix_presence_sessions_user_id', 'presence_sessions', ['user_id'])
    op.create_index('ix_presence_sessions_last_heartbeat_at', 'presence_sessions', ['last_heartbeat_at'])

    op.add_column('sleep_config', sa.Column('presence_enabled', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column('sleep_config', sa.Column('presence_mode', sa.String(length=20), nullable=False, server_default='active'))
    op.add_column('sleep_config', sa.Column('presence_timeout_minutes', sa.Integer(), nullable=False, server_default='3'))


def downgrade() -> None:
    op.drop_column('sleep_config', 'presence_timeout_minutes')
    op.drop_column('sleep_config', 'presence_mode')
    op.drop_column('sleep_config', 'presence_enabled')
    op.drop_index('ix_presence_sessions_last_heartbeat_at', table_name='presence_sessions')
    op.drop_index('ix_presence_sessions_user_id', table_name='presence_sessions')
    op.drop_table('presence_sessions')
