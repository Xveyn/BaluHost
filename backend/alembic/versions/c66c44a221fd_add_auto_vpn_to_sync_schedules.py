"""add auto_vpn to sync_schedules

Revision ID: c66c44a221fd
Revises: 040_add_version_history
Create Date: 2026-03-11 21:24:24.164258

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c66c44a221fd'
down_revision: Union[str, Sequence[str], None] = '040_add_version_history'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add auto_vpn column to sync_schedules.

    NOTE: Migration c7fbef10fbee erroneously dropped sync_schedules before
    this migration runs.  Migration 049_recreate_sync_tables recreates it
    WITH auto_vpn, so we skip when the table is absent.
    """
    from sqlalchemy import inspect as sa_inspect
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    if 'sync_schedules' not in inspector.get_table_names():
        return  # table will be recreated later with auto_vpn included
    columns = [c['name'] for c in inspector.get_columns('sync_schedules')]
    if 'auto_vpn' in columns:
        return  # column already exists
    op.add_column(
        'sync_schedules',
        sa.Column('auto_vpn', sa.Boolean(), nullable=False, server_default='false')
    )


def downgrade() -> None:
    """Remove auto_vpn column from sync_schedules."""
    from sqlalchemy import inspect as sa_inspect
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    if 'sync_schedules' not in inspector.get_table_names():
        return
    op.drop_column('sync_schedules', 'auto_vpn')
