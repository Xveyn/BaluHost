"""add desktop_sync_folders table

Revision ID: 029_desktop_sync
Revises: 90fb36d913ee
Create Date: 2026-02-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '029_desktop_sync'
down_revision: Union[str, None] = '90fb36d913ee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'desktop_sync_folders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.String(length=255), nullable=False),
        sa.Column('device_name', sa.String(length=255), nullable=False),
        sa.Column('platform', sa.String(length=50), nullable=False),
        sa.Column('remote_path', sa.String(length=1000), nullable=False),
        sa.Column('sync_direction', sa.String(length=50), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('last_reported_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('device_id', 'remote_path', name='uq_device_remote_path'),
    )
    op.create_index(op.f('ix_desktop_sync_folders_id'), 'desktop_sync_folders', ['id'])
    op.create_index(op.f('ix_desktop_sync_folders_user_id'), 'desktop_sync_folders', ['user_id'])
    op.create_index(op.f('ix_desktop_sync_folders_device_id'), 'desktop_sync_folders', ['device_id'])
    op.create_index(op.f('ix_desktop_sync_folders_remote_path'), 'desktop_sync_folders', ['remote_path'])


def downgrade() -> None:
    op.drop_index(op.f('ix_desktop_sync_folders_remote_path'), table_name='desktop_sync_folders')
    op.drop_index(op.f('ix_desktop_sync_folders_device_id'), table_name='desktop_sync_folders')
    op.drop_index(op.f('ix_desktop_sync_folders_user_id'), table_name='desktop_sync_folders')
    op.drop_index(op.f('ix_desktop_sync_folders_id'), table_name='desktop_sync_folders')
    op.drop_table('desktop_sync_folders')
