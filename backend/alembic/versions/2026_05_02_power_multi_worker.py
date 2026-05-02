"""add power runtime state, demands, and command queue tables

Revision ID: 2026_05_02_power_multi_worker
Revises: f4b1c0e7d2a3
Create Date: 2026-05-02

Adds three tables to support multi-worker safe power management:

- power_runtime_state: singleton row holding live mutable state (current
  profile, dynamic mode flag, manual override / cooldown timers). Replaces
  the per-process in-memory state on PowerManagerService.
- power_demands: active demand entries, replaces the per-worker
  ``_demands`` dict so any worker can register/inspect demands.
- power_commands: cross-worker command queue. Secondary workers enqueue
  hardware operations; the primary worker's poll loop executes them.

See docs/superpowers/plans/2026-05-01-power-manager-multi-worker-fix.md
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '2026_05_02_power_multi_worker'
down_revision: Union[str, Sequence[str], None] = 'f4b1c0e7d2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'power_runtime_state',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('current_profile', sa.String(length=20), nullable=False, server_default='idle'),
        sa.Column('current_property', sa.String(length=20), nullable=True),
        sa.Column('manual_override_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cooldown_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('dynamic_mode_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('last_profile_change', sa.DateTime(timezone=True), nullable=True),
        sa.Column('backend_kind', sa.String(length=20), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_by_pid', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.execute(
        "INSERT INTO power_runtime_state (id, current_profile, dynamic_mode_enabled) "
        "VALUES (1, 'idle', false)"
    )

    op.create_table(
        'power_demands',
        sa.Column('source', sa.String(length=100), nullable=False),
        sa.Column('level', sa.String(length=20), nullable=False),
        sa.Column('power_property', sa.String(length=20), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('registered_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('source'),
    )
    op.create_index(
        op.f('ix_power_demands_expires_at'),
        'power_demands',
        ['expires_at'],
        unique=False,
    )

    op.create_table(
        'power_commands',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('command', sa.String(length=40), nullable=False),
        sa.Column('payload_json', sa.Text(), nullable=True),
        sa.Column('requested_by', sa.String(length=100), nullable=True),
        sa.Column('requested_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'idx_power_commands_status_requested',
        'power_commands',
        ['status', 'requested_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('idx_power_commands_status_requested', table_name='power_commands')
    op.drop_table('power_commands')

    op.drop_index(op.f('ix_power_demands_expires_at'), table_name='power_demands')
    op.drop_table('power_demands')

    op.drop_table('power_runtime_state')
