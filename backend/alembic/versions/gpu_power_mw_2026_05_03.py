"""add gpu power runtime state, demands, and command queue tables

Revision ID: gpu_power_mw_2026_05_03
Revises: 2026_05_02_power_multi_worker
Create Date: 2026-05-03

Adds three tables to support multi-worker safe GPU power management,
analogous to the CPU manager fix in 2026_05_02_power_multi_worker:

- gpu_power_runtime_state: singleton row holding live mutable state
  (current state, detection result, vendor, has_write_permission).
- gpu_power_demands: active demand entries shared across workers.
- gpu_power_commands: cross-worker command queue for set_config,
  register_demand, and unregister_demand operations from secondary
  workers.

NB: revision-ID purposefully short (23 chars) — alembic_version.version_num
is VARCHAR(32), so a fully spelled-out revision name overflows on the
UPDATE that closes the migration. Original attempt used
``2026_05_03_gpu_power_multi_worker`` (34 chars) which failed in prod
with ``StringDataRightTruncation``.

See docs/superpowers/plans/2026-05-02-gpu-power-manager-multi-worker-fix.md
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'gpu_power_mw_2026_05_03'
down_revision: Union[str, Sequence[str], None] = '2026_05_02_power_multi_worker'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, name: str) -> bool:
    insp = sa.inspect(bind)
    return insp.has_table(name)


def upgrade() -> None:
    """
    Idempotent: the previous (failed) attempt may have left the three
    tables already created on the production database before the
    alembic_version UPDATE failed. Skip create_table for tables that
    already exist so the rerun completes cleanly.
    """
    bind = op.get_bind()

    if not _table_exists(bind, 'gpu_power_runtime_state'):
        op.create_table(
            'gpu_power_runtime_state',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('current_state', sa.String(length=16), nullable=False, server_default='active'),
            sa.Column('detected', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('vendor', sa.String(length=20), nullable=True),
            sa.Column('has_write_permission', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('last_transition', sa.DateTime(timezone=True), nullable=True),
            sa.Column('last_reason', sa.String(length=64), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.Column('updated_by_pid', sa.Integer(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
        )
        op.execute(
            "INSERT INTO gpu_power_runtime_state (id, current_state, detected, has_write_permission) "
            "VALUES (1, 'active', false, false)"
        )

    if not _table_exists(bind, 'gpu_power_demands'):
        op.create_table(
            'gpu_power_demands',
            sa.Column('source', sa.String(length=100), nullable=False),
            sa.Column('registered_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('description', sa.String(length=500), nullable=True),
            sa.PrimaryKeyConstraint('source'),
        )
        op.create_index(
            op.f('ix_gpu_power_demands_expires_at'),
            'gpu_power_demands',
            ['expires_at'],
            unique=False,
        )

    if not _table_exists(bind, 'gpu_power_commands'):
        op.create_table(
            'gpu_power_commands',
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
            'idx_gpu_power_commands_status_requested',
            'gpu_power_commands',
            ['status', 'requested_at'],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, 'gpu_power_commands'):
        try:
            op.drop_index('idx_gpu_power_commands_status_requested', table_name='gpu_power_commands')
        except Exception:
            pass
        op.drop_table('gpu_power_commands')

    if _table_exists(bind, 'gpu_power_demands'):
        try:
            op.drop_index(op.f('ix_gpu_power_demands_expires_at'), table_name='gpu_power_demands')
        except Exception:
            pass
        op.drop_table('gpu_power_demands')

    if _table_exists(bind, 'gpu_power_runtime_state'):
        op.drop_table('gpu_power_runtime_state')
