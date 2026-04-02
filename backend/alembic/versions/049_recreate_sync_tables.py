"""Recreate sync tables dropped by c7fbef10fbee

Migration c7fbef10fbee erroneously dropped 7 sync tables because the models
in sync_progress.py and sync_state.py were not imported in models/__init__.py
at autogenerate time. This migration recreates them for production databases
where the drops were already applied.

Uses dialect-aware IF NOT EXISTS to be safe on both fresh installs (where
tables already exist from the original migrations) and production (where
they were dropped).

Revision ID: 049_recreate_sync_tables
Revises: deb715622471
Create Date: 2026-04-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect


revision: str = '049_recreate_sync_tables'
down_revision: Union[str, Sequence[str], None] = 'deb715622471'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    """Check if a table exists in the current database."""
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    """Recreate sync tables that were erroneously dropped."""

    # --- sync_states (no FK dependencies, create first) ---
    if not _table_exists('sync_states'):
        op.create_table('sync_states',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('device_id', sa.String(length=255), nullable=False),
            sa.Column('device_name', sa.String(length=255), nullable=True),
            sa.Column('last_sync', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('last_change_token', sa.String(length=255), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_sync_states_id'), 'sync_states', ['id'], unique=False)
        op.create_index(op.f('ix_sync_states_user_id'), 'sync_states', ['user_id'], unique=False)
        op.create_index(op.f('ix_sync_states_device_id'), 'sync_states', ['device_id'], unique=True)

    # --- sync_bandwidth_limits ---
    if not _table_exists('sync_bandwidth_limits'):
        op.create_table('sync_bandwidth_limits',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('upload_speed_limit', sa.Integer(), nullable=True),
            sa.Column('download_speed_limit', sa.Integer(), nullable=True),
            sa.Column('throttle_enabled', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('throttle_start_hour', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('throttle_end_hour', sa.Integer(), nullable=False, server_default='6'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_sync_bandwidth_limits_id'), 'sync_bandwidth_limits', ['id'], unique=False)
        op.create_index(op.f('ix_sync_bandwidth_limits_user_id'), 'sync_bandwidth_limits', ['user_id'], unique=True)

    # --- chunked_uploads ---
    if not _table_exists('chunked_uploads'):
        op.create_table('chunked_uploads',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('upload_id', sa.String(length=36), nullable=False),
            sa.Column('file_metadata_id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('device_id', sa.String(length=255), nullable=False),
            sa.Column('file_name', sa.String(length=255), nullable=False),
            sa.Column('file_path', sa.String(length=1000), nullable=False),
            sa.Column('total_size', sa.BigInteger(), nullable=False),
            sa.Column('chunk_size', sa.Integer(), nullable=False, server_default='5242880'),
            sa.Column('uploaded_bytes', sa.BigInteger(), nullable=False, server_default='0'),
            sa.Column('completed_chunks', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('total_chunks', sa.Integer(), nullable=False),
            sa.Column('is_completed', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('resume_token', sa.String(length=36), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(['file_metadata_id'], ['file_metadata.id']),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_chunked_uploads_id'), 'chunked_uploads', ['id'], unique=False)
        op.create_index(op.f('ix_chunked_uploads_upload_id'), 'chunked_uploads', ['upload_id'], unique=True)
        op.create_index(op.f('ix_chunked_uploads_user_id'), 'chunked_uploads', ['user_id'], unique=False)

    # --- sync_schedules ---
    if not _table_exists('sync_schedules'):
        op.create_table('sync_schedules',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('device_id', sa.String(length=255), nullable=False),
            sa.Column('schedule_type', sa.String(length=20), nullable=False),
            sa.Column('time_of_day', sa.String(length=5), nullable=True),
            sa.Column('day_of_week', sa.Integer(), nullable=True),
            sa.Column('day_of_month', sa.Integer(), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('sync_deletions', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('resolve_conflicts', sa.String(length=20), nullable=False, server_default="'keep_newest'"),
            sa.Column('auto_vpn', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_sync_schedules_id'), 'sync_schedules', ['id'], unique=False)
        op.create_index(op.f('ix_sync_schedules_user_id'), 'sync_schedules', ['user_id'], unique=False)

    # --- selective_syncs ---
    if not _table_exists('selective_syncs'):
        op.create_table('selective_syncs',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('device_id', sa.String(length=255), nullable=False),
            sa.Column('folder_path', sa.String(length=1000), nullable=False),
            sa.Column('include_subfolders', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('reason', sa.String(length=255), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_selective_syncs_id'), 'selective_syncs', ['id'], unique=False)
        op.create_index(op.f('ix_selective_syncs_user_id'), 'selective_syncs', ['user_id'], unique=False)

    # --- sync_file_versions ---
    if not _table_exists('sync_file_versions'):
        op.create_table('sync_file_versions',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('file_metadata_id', sa.Integer(), nullable=False),
            sa.Column('version_number', sa.Integer(), nullable=False),
            sa.Column('file_path', sa.String(length=500), nullable=False),
            sa.Column('file_size', sa.Integer(), nullable=False),
            sa.Column('content_hash', sa.String(length=64), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('created_by_id', sa.Integer(), nullable=False),
            sa.Column('change_reason', sa.String(length=255), nullable=True),
            sa.ForeignKeyConstraint(['created_by_id'], ['users.id']),
            sa.ForeignKeyConstraint(['file_metadata_id'], ['file_metadata.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_sync_file_versions_id'), 'sync_file_versions', ['id'], unique=False)
        op.create_index(op.f('ix_sync_file_versions_file_metadata_id'), 'sync_file_versions', ['file_metadata_id'], unique=False)

    # --- sync_metadata (depends on sync_states) ---
    if not _table_exists('sync_metadata'):
        op.create_table('sync_metadata',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('file_metadata_id', sa.Integer(), nullable=False),
            sa.Column('sync_state_id', sa.Integer(), nullable=False),
            sa.Column('content_hash', sa.String(length=64), nullable=False),
            sa.Column('file_size', sa.Integer(), nullable=False),
            sa.Column('local_modified_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('sync_modified_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('server_modified_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('conflict_detected', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('conflict_resolution', sa.String(length=50), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['file_metadata_id'], ['file_metadata.id']),
            sa.ForeignKeyConstraint(['sync_state_id'], ['sync_states.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_sync_metadata_id'), 'sync_metadata', ['id'], unique=False)
        op.create_index(op.f('ix_sync_metadata_file_metadata_id'), 'sync_metadata', ['file_metadata_id'], unique=False)
        op.create_index(op.f('ix_sync_metadata_sync_state_id'), 'sync_metadata', ['sync_state_id'], unique=False)


def downgrade() -> None:
    """Drop the recreated sync tables (reverse order for FK safety)."""
    for table in [
        'sync_metadata', 'sync_file_versions', 'selective_syncs',
        'sync_schedules', 'chunked_uploads', 'sync_bandwidth_limits',
        'sync_states',
    ]:
        if _table_exists(table):
            op.drop_table(table)
