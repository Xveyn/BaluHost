"""add migration_jobs table

Revision ID: 032_add_migration_jobs
Revises: 031_ssd_cache_per_array
Create Date: 2026-02-23

Adds migration_jobs table for tracking background data migration jobs
(e.g. VCL blob migration from HDD to SSD).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '032_add_migration_jobs'
down_revision: Union[str, None] = '031_ssd_cache_per_array'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'migration_jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_type', sa.String(30), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('source_path', sa.Text(), nullable=False),
        sa.Column('dest_path', sa.Text(), nullable=False),
        sa.Column('total_files', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('processed_files', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('skipped_files', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_files', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_bytes', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('processed_bytes', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('current_file', sa.String(500), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('dry_run', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_migration_jobs_id', 'migration_jobs', ['id'])
    op.create_index('ix_migration_jobs_status', 'migration_jobs', ['status'])
    op.create_index('ix_migration_jobs_job_type', 'migration_jobs', ['job_type'])


def downgrade() -> None:
    op.drop_index('ix_migration_jobs_job_type', table_name='migration_jobs')
    op.drop_index('ix_migration_jobs_status', table_name='migration_jobs')
    op.drop_index('ix_migration_jobs_id', table_name='migration_jobs')
    op.drop_table('migration_jobs')
