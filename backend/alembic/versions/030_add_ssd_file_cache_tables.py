"""add ssd_file_cache tables

Revision ID: 030_ssd_file_cache
Revises: b3c4d5e6f7a8
Create Date: 2026-02-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '030_ssd_file_cache'
down_revision: Union[str, None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SSD cache configuration (singleton, id=1)
    op.create_table(
        'ssd_cache_config',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('cache_path', sa.Text(), nullable=False, server_default='/mnt/cache-vcl/filecache'),
        sa.Column('max_size_bytes', sa.BigInteger(), nullable=False, server_default=str(500 * 1024**3)),
        sa.Column('current_size_bytes', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('eviction_policy', sa.String(length=10), nullable=False, server_default='lfru'),
        sa.Column('min_file_size_bytes', sa.BigInteger(), nullable=False, server_default=str(1024 * 1024)),
        sa.Column('max_file_size_bytes', sa.BigInteger(), nullable=False, server_default=str(4 * 1024**3)),
        sa.Column('sequential_cutoff_bytes', sa.BigInteger(), nullable=False, server_default=str(64 * 1024 * 1024)),
        sa.Column('total_hits', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('total_misses', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('total_bytes_served_from_cache', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    # SSD cache entries (one per cached file)
    op.create_table(
        'ssd_cache_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_path', sa.Text(), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('cache_path', sa.Text(), nullable=False),
        sa.Column('file_size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('checksum', sa.String(length=64), nullable=False),
        sa.Column('access_count', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('last_accessed', sa.DateTime(), nullable=False),
        sa.Column('first_cached', sa.DateTime(), nullable=False),
        sa.Column('is_valid', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('source_mtime', sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['file_id'], ['file_metadata.id'], ondelete='SET NULL'),
    )

    op.create_index('ix_ssd_cache_entries_source_path', 'ssd_cache_entries', ['source_path'], unique=True)
    op.create_index('ix_ssd_cache_entries_file_id', 'ssd_cache_entries', ['file_id'])
    op.create_index('ix_ssd_cache_entries_is_valid', 'ssd_cache_entries', ['is_valid'])
    op.create_index('ix_ssd_cache_entries_last_accessed', 'ssd_cache_entries', ['last_accessed'])
    op.create_index('ix_ssd_cache_entries_first_cached', 'ssd_cache_entries', ['first_cached'])
    op.create_index(
        'idx_ssd_cache_eviction',
        'ssd_cache_entries',
        ['is_valid', 'access_count', 'last_accessed'],
    )

    # Seed singleton config row
    op.execute(
        "INSERT INTO ssd_cache_config (id, is_enabled) VALUES (1, false)"
    )


def downgrade() -> None:
    op.drop_table('ssd_cache_entries')
    op.drop_table('ssd_cache_config')
