"""Add disk benchmark tables

Revision ID: 013_benchmarks
Revises: 012_plugins
Create Date: 2026-02-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '013_benchmarks'
down_revision: Union[str, None] = '012_plugins'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create disk benchmark tables."""
    # Main benchmark table
    op.create_table(
        'disk_benchmarks',
        sa.Column('id', sa.Integer(), nullable=False),
        # Disk identification
        sa.Column('disk_name', sa.String(64), nullable=False),
        sa.Column('disk_model', sa.String(256), nullable=True),
        sa.Column('disk_size_bytes', sa.BigInteger(), nullable=True),
        # Benchmark configuration
        sa.Column('profile', sa.Enum('quick', 'standard', 'comprehensive', name='benchmarkprofile'), nullable=False),
        sa.Column('target_type', sa.Enum('test_file', 'raw_device', name='benchmarktargettype'), nullable=False),
        sa.Column('test_file_path', sa.String(512), nullable=True),
        sa.Column('test_file_size_bytes', sa.BigInteger(), nullable=True),
        # Status tracking
        sa.Column('status', sa.Enum('pending', 'running', 'completed', 'failed', 'cancelled', name='benchmarkstatus'), nullable=False),
        sa.Column('progress_percent', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('current_test', sa.String(64), nullable=True),
        sa.Column('error_message', sa.String(1024), nullable=True),
        # Timing
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        # Summary results
        sa.Column('seq_read_mbps', sa.Float(), nullable=True),
        sa.Column('seq_write_mbps', sa.Float(), nullable=True),
        sa.Column('seq_read_q1_mbps', sa.Float(), nullable=True),
        sa.Column('seq_write_q1_mbps', sa.Float(), nullable=True),
        sa.Column('rand_read_iops', sa.Float(), nullable=True),
        sa.Column('rand_write_iops', sa.Float(), nullable=True),
        sa.Column('rand_read_q1_iops', sa.Float(), nullable=True),
        sa.Column('rand_write_q1_iops', sa.Float(), nullable=True),
        # User reference
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_disk_benchmarks_id', 'disk_benchmarks', ['id'], unique=False)
    op.create_index('ix_disk_benchmarks_disk_name', 'disk_benchmarks', ['disk_name'], unique=False)
    op.create_index('ix_disk_benchmarks_status', 'disk_benchmarks', ['status'], unique=False)
    op.create_index('idx_disk_benchmarks_created', 'disk_benchmarks', ['created_at'], unique=False)

    # Detailed test results table
    op.create_table(
        'benchmark_test_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('benchmark_id', sa.Integer(), sa.ForeignKey('disk_benchmarks.id', ondelete='CASCADE'), nullable=False),
        # Test identification
        sa.Column('test_name', sa.String(64), nullable=False),
        sa.Column('operation', sa.String(16), nullable=False),
        sa.Column('block_size', sa.String(16), nullable=False),
        sa.Column('queue_depth', sa.Integer(), nullable=False),
        sa.Column('num_jobs', sa.Integer(), nullable=False, server_default='1'),
        # Performance results
        sa.Column('throughput_mbps', sa.Float(), nullable=True),
        sa.Column('iops', sa.Float(), nullable=True),
        # Latency results (microseconds)
        sa.Column('latency_avg_us', sa.Float(), nullable=True),
        sa.Column('latency_min_us', sa.Float(), nullable=True),
        sa.Column('latency_max_us', sa.Float(), nullable=True),
        sa.Column('latency_p99_us', sa.Float(), nullable=True),
        sa.Column('latency_p95_us', sa.Float(), nullable=True),
        sa.Column('latency_p50_us', sa.Float(), nullable=True),
        # Additional metrics
        sa.Column('bandwidth_bytes', sa.BigInteger(), nullable=True),
        sa.Column('runtime_ms', sa.Integer(), nullable=True),
        # Timestamp
        sa.Column('completed_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_benchmark_test_results_id', 'benchmark_test_results', ['id'], unique=False)
    op.create_index('ix_benchmark_test_results_benchmark_id', 'benchmark_test_results', ['benchmark_id'], unique=False)


def downgrade() -> None:
    """Drop disk benchmark tables."""
    op.drop_index('ix_benchmark_test_results_benchmark_id', table_name='benchmark_test_results')
    op.drop_index('ix_benchmark_test_results_id', table_name='benchmark_test_results')
    op.drop_table('benchmark_test_results')

    op.drop_index('idx_disk_benchmarks_created', table_name='disk_benchmarks')
    op.drop_index('ix_disk_benchmarks_status', table_name='disk_benchmarks')
    op.drop_index('ix_disk_benchmarks_disk_name', table_name='disk_benchmarks')
    op.drop_index('ix_disk_benchmarks_id', table_name='disk_benchmarks')
    op.drop_table('disk_benchmarks')

    # Drop enums
    op.execute("DROP TYPE IF EXISTS benchmarkstatus")
    op.execute("DROP TYPE IF EXISTS benchmarktargettype")
    op.execute("DROP TYPE IF EXISTS benchmarkprofile")
