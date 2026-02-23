"""ssd cache per-array refactor

Revision ID: 031_ssd_cache_per_array
Revises: 030_ssd_file_cache
Create Date: 2026-02-23

Adds array_name to ssd_cache_config and ssd_cache_entries,
converts from singleton to per-array pattern, and drops the
old bcache ssd_cache_configs table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '031_ssd_cache_per_array'
down_revision: Union[str, None] = '030_ssd_file_cache'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ===== ssd_cache_config: add array_name =====
    op.add_column(
        'ssd_cache_config',
        sa.Column('array_name', sa.String(64), nullable=True),
    )
    # Set existing row(s) to 'md0' and update cache_path to include array suffix
    op.execute("UPDATE ssd_cache_config SET array_name = 'md0' WHERE array_name IS NULL")
    op.execute(
        "UPDATE ssd_cache_config SET cache_path = cache_path || '/md0' "
        "WHERE cache_path NOT LIKE '%/md0' AND array_name = 'md0'"
    )
    # Make non-nullable
    op.alter_column('ssd_cache_config', 'array_name', nullable=False)
    op.create_index('ix_ssd_cache_config_array_name', 'ssd_cache_config', ['array_name'], unique=True)

    # ===== ssd_cache_entries: add array_name, update constraints =====
    op.add_column(
        'ssd_cache_entries',
        sa.Column('array_name', sa.String(64), nullable=True),
    )
    # Set existing entries to 'md0'
    op.execute("UPDATE ssd_cache_entries SET array_name = 'md0' WHERE array_name IS NULL")
    # Make non-nullable
    op.alter_column('ssd_cache_entries', 'array_name', nullable=False)
    op.create_index('ix_ssd_cache_entries_array_name', 'ssd_cache_entries', ['array_name'])

    # Drop old unique constraint on source_path alone
    op.drop_index('ix_ssd_cache_entries_source_path', table_name='ssd_cache_entries')

    # Create new composite unique constraint
    op.create_unique_constraint(
        'uq_ssd_cache_array_source',
        'ssd_cache_entries',
        ['array_name', 'source_path'],
    )

    # Drop old eviction index, create new per-array one
    op.drop_index('idx_ssd_cache_eviction', table_name='ssd_cache_entries')
    op.create_index(
        'idx_ssd_cache_eviction',
        'ssd_cache_entries',
        ['array_name', 'is_valid', 'access_count', 'last_accessed'],
    )

    # ===== Reset PostgreSQL sequence for ssd_cache_config =====
    # Migration 030 inserted with explicit id=1, which doesn't advance the
    # sequence. Reset it so auto-increment starts after existing rows.
    op.execute(
        "SELECT setval('ssd_cache_config_id_seq', "
        "(SELECT COALESCE(MAX(id), 0) FROM ssd_cache_config), true)"
    )

    # ===== Drop old bcache table =====
    # Check if table exists before dropping (it may not exist in fresh installs)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'ssd_cache_configs' in inspector.get_table_names():
        op.drop_table('ssd_cache_configs')


def downgrade() -> None:
    # Recreate old bcache table
    op.create_table(
        'ssd_cache_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('array_name', sa.String(64), nullable=False),
        sa.Column('cache_device', sa.String(64), nullable=False),
        sa.Column('mode', sa.String(20), nullable=False, server_default='writethrough'),
        sa.Column('sequential_cutoff_bytes', sa.Integer(), nullable=False, server_default=str(4 * 1024 * 1024)),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('attached_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ssd_cache_configs_array_name', 'ssd_cache_configs', ['array_name'], unique=True)
    op.create_index('ix_ssd_cache_configs_id', 'ssd_cache_configs', ['id'])
    op.create_index('ix_ssd_cache_configs_is_active', 'ssd_cache_configs', ['is_active'])

    # Revert ssd_cache_entries constraints
    op.drop_index('idx_ssd_cache_eviction', table_name='ssd_cache_entries')
    op.create_index(
        'idx_ssd_cache_eviction',
        'ssd_cache_entries',
        ['is_valid', 'access_count', 'last_accessed'],
    )
    op.drop_constraint('uq_ssd_cache_array_source', 'ssd_cache_entries', type_='unique')
    op.create_index('ix_ssd_cache_entries_source_path', 'ssd_cache_entries', ['source_path'], unique=True)
    op.drop_index('ix_ssd_cache_entries_array_name', table_name='ssd_cache_entries')
    op.drop_column('ssd_cache_entries', 'array_name')

    # Revert ssd_cache_config
    op.drop_index('ix_ssd_cache_config_array_name', table_name='ssd_cache_config')
    op.drop_column('ssd_cache_config', 'array_name')
