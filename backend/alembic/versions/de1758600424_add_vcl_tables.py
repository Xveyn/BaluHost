"""Add VCL tables

Revision ID: de1758600424
Revises: e2b5fd2fe391
Create Date: 2026-01-03 00:18:44.601024

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'de1758600424'
down_revision: Union[str, Sequence[str], None] = 'e2b5fd2fe391'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create VCL tables."""
    # VCL Stats table
    op.create_table('vcl_stats',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('total_versions', sa.Integer(), nullable=False),
        sa.Column('total_size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('total_compressed_bytes', sa.BigInteger(), nullable=False),
        sa.Column('total_blobs', sa.Integer(), nullable=False),
        sa.Column('unique_blobs', sa.Integer(), nullable=False),
        sa.Column('deduplication_savings_bytes', sa.BigInteger(), nullable=False),
        sa.Column('compression_savings_bytes', sa.BigInteger(), nullable=False),
        sa.Column('priority_count', sa.Integer(), nullable=False),
        sa.Column('cached_versions_count', sa.Integer(), nullable=False),
        sa.Column('last_cleanup_at', sa.DateTime(), nullable=True),
        sa.Column('last_priority_mode_at', sa.DateTime(), nullable=True),
        sa.Column('last_deduplication_scan', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Version Blobs table (deduplicated storage)
    op.create_table('version_blobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('checksum', sa.String(length=64), nullable=False),
        sa.Column('storage_path', sa.Text(), nullable=False),
        sa.Column('original_size', sa.Integer(), nullable=False),
        sa.Column('compressed_size', sa.Integer(), nullable=False),
        sa.Column('reference_count', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_accessed', sa.DateTime(), nullable=True),
        sa.Column('can_delete', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_version_blobs_cleanup', 'version_blobs', ['can_delete', 'last_accessed'])
    op.create_index(op.f('ix_version_blobs_checksum'), 'version_blobs', ['checksum'], unique=True)
    op.create_index(op.f('ix_version_blobs_id'), 'version_blobs', ['id'])
    
    # VCL Settings table (per-user configuration)
    op.create_table('vcl_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('max_size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('current_usage_bytes', sa.BigInteger(), nullable=False),
        sa.Column('depth', sa.Integer(), nullable=False),
        sa.Column('headroom_percent', sa.Integer(), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), nullable=False),
        sa.Column('compression_enabled', sa.Boolean(), nullable=False),
        sa.Column('dedupe_enabled', sa.Boolean(), nullable=False),
        sa.Column('debounce_window_seconds', sa.Integer(), nullable=False),
        sa.Column('max_batch_window_seconds', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_vcl_settings_id'), 'vcl_settings', ['id'])
    op.create_index(op.f('ix_vcl_settings_user_id'), 'vcl_settings', ['user_id'], unique=True)
    
    # VCL File Versions table (main version tracking)
    op.create_table('vcl_file_versions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('blob_id', sa.Integer(), nullable=True),
        sa.Column('storage_type', sa.String(length=20), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('compressed_size', sa.Integer(), nullable=False),
        sa.Column('compression_ratio', sa.Float(), nullable=True),
        sa.Column('checksum', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('is_high_priority', sa.Boolean(), nullable=False),
        sa.Column('change_type', sa.String(length=20), nullable=True),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('was_cached', sa.Boolean(), nullable=False),
        sa.Column('cache_duration', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['blob_id'], ['version_blobs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['file_id'], ['file_metadata.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('file_id', 'version_number', name='uq_file_versions_file_version')
    )
    op.create_index(op.f('ix_vcl_file_versions_checksum'), 'vcl_file_versions', ['checksum'])
    op.create_index(op.f('ix_vcl_file_versions_created_at'), 'vcl_file_versions', ['created_at'])
    op.create_index(op.f('ix_vcl_file_versions_file_id'), 'vcl_file_versions', ['file_id'])
    op.create_index(op.f('ix_vcl_file_versions_id'), 'vcl_file_versions', ['id'])
    op.create_index(op.f('ix_vcl_file_versions_is_high_priority'), 'vcl_file_versions', ['is_high_priority'])
    op.create_index(op.f('ix_vcl_file_versions_user_id'), 'vcl_file_versions', ['user_id'])


def downgrade() -> None:
    """Drop VCL tables."""
    op.drop_index(op.f('ix_vcl_file_versions_user_id'), table_name='vcl_file_versions')
    op.drop_index(op.f('ix_vcl_file_versions_is_high_priority'), table_name='vcl_file_versions')
    op.drop_index(op.f('ix_vcl_file_versions_id'), table_name='vcl_file_versions')
    op.drop_index(op.f('ix_vcl_file_versions_file_id'), table_name='vcl_file_versions')
    op.drop_index(op.f('ix_vcl_file_versions_created_at'), table_name='vcl_file_versions')
    op.drop_index(op.f('ix_vcl_file_versions_checksum'), table_name='vcl_file_versions')
    op.drop_table('vcl_file_versions')
    
    op.drop_index(op.f('ix_vcl_settings_user_id'), table_name='vcl_settings')
    op.drop_index(op.f('ix_vcl_settings_id'), table_name='vcl_settings')
    op.drop_table('vcl_settings')
    
    op.drop_index(op.f('ix_version_blobs_id'), table_name='version_blobs')
    op.drop_index(op.f('ix_version_blobs_checksum'), table_name='version_blobs')
    op.drop_index('idx_version_blobs_cleanup', table_name='version_blobs')
    op.drop_table('version_blobs')
    
    op.drop_table('vcl_stats')
