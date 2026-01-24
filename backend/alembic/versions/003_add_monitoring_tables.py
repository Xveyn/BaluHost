"""add_monitoring_tables

Revision ID: 003_monitoring
Revises: 002_power_samples
Create Date: 2026-01-24

Creates monitoring tables for system metrics:
- cpu_samples: CPU usage, frequency, temperature
- memory_samples: RAM usage
- network_samples: Network throughput
- disk_io_samples: Disk I/O per physical disk
- process_samples: BaluHost process tracking
- monitoring_config: Retention configuration per metric type
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003_monitoring'
down_revision: Union[str, Sequence[str], None] = '002_power_samples'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create monitoring tables."""

    # CPU samples table
    op.create_table(
        'cpu_samples',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('usage_percent', sa.Float(), nullable=False),
        sa.Column('frequency_mhz', sa.Float(), nullable=True),
        sa.Column('temperature_celsius', sa.Float(), nullable=True),
        sa.Column('core_count', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_cpu_samples_id'), 'cpu_samples', ['id'], unique=False)
    op.create_index(op.f('ix_cpu_samples_timestamp'), 'cpu_samples', ['timestamp'], unique=False)

    # Memory samples table
    op.create_table(
        'memory_samples',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('used_bytes', sa.BigInteger(), nullable=False),
        sa.Column('total_bytes', sa.BigInteger(), nullable=False),
        sa.Column('percent', sa.Float(), nullable=False),
        sa.Column('available_bytes', sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_memory_samples_id'), 'memory_samples', ['id'], unique=False)
    op.create_index(op.f('ix_memory_samples_timestamp'), 'memory_samples', ['timestamp'], unique=False)

    # Network samples table
    op.create_table(
        'network_samples',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('download_mbps', sa.Float(), nullable=False),
        sa.Column('upload_mbps', sa.Float(), nullable=False),
        sa.Column('bytes_sent', sa.BigInteger(), nullable=True),
        sa.Column('bytes_received', sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_network_samples_id'), 'network_samples', ['id'], unique=False)
    op.create_index(op.f('ix_network_samples_timestamp'), 'network_samples', ['timestamp'], unique=False)

    # Disk I/O samples table
    op.create_table(
        'disk_io_samples',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('disk_name', sa.String(64), nullable=False),
        sa.Column('read_mbps', sa.Float(), nullable=False),
        sa.Column('write_mbps', sa.Float(), nullable=False),
        sa.Column('read_iops', sa.Float(), nullable=False),
        sa.Column('write_iops', sa.Float(), nullable=False),
        sa.Column('avg_response_ms', sa.Float(), nullable=True),
        sa.Column('active_time_percent', sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_disk_io_samples_id'), 'disk_io_samples', ['id'], unique=False)
    op.create_index(op.f('ix_disk_io_samples_timestamp'), 'disk_io_samples', ['timestamp'], unique=False)
    op.create_index(op.f('ix_disk_io_samples_disk_name'), 'disk_io_samples', ['disk_name'], unique=False)

    # Process samples table
    op.create_table(
        'process_samples',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('process_name', sa.String(128), nullable=False),
        sa.Column('pid', sa.Integer(), nullable=False),
        sa.Column('cpu_percent', sa.Float(), nullable=False),
        sa.Column('memory_mb', sa.Float(), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('is_alive', sa.Boolean(), nullable=False, server_default='1'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_process_samples_id'), 'process_samples', ['id'], unique=False)
    op.create_index(op.f('ix_process_samples_timestamp'), 'process_samples', ['timestamp'], unique=False)
    op.create_index(op.f('ix_process_samples_process_name'), 'process_samples', ['process_name'], unique=False)

    # Monitoring configuration table
    op.create_table(
        'monitoring_config',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('metric_type', sa.String(32), nullable=False),
        sa.Column('retention_hours', sa.Integer(), nullable=False, server_default='168'),
        sa.Column('db_persist_interval', sa.Integer(), nullable=False, server_default='12'),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('last_cleanup', sa.DateTime(), nullable=True),
        sa.Column('samples_cleaned', sa.Integer(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('metric_type')
    )
    op.create_index(op.f('ix_monitoring_config_id'), 'monitoring_config', ['id'], unique=False)


def downgrade() -> None:
    """Drop monitoring tables."""
    op.drop_index(op.f('ix_monitoring_config_id'), table_name='monitoring_config')
    op.drop_table('monitoring_config')

    op.drop_index(op.f('ix_process_samples_process_name'), table_name='process_samples')
    op.drop_index(op.f('ix_process_samples_timestamp'), table_name='process_samples')
    op.drop_index(op.f('ix_process_samples_id'), table_name='process_samples')
    op.drop_table('process_samples')

    op.drop_index(op.f('ix_disk_io_samples_disk_name'), table_name='disk_io_samples')
    op.drop_index(op.f('ix_disk_io_samples_timestamp'), table_name='disk_io_samples')
    op.drop_index(op.f('ix_disk_io_samples_id'), table_name='disk_io_samples')
    op.drop_table('disk_io_samples')

    op.drop_index(op.f('ix_network_samples_timestamp'), table_name='network_samples')
    op.drop_index(op.f('ix_network_samples_id'), table_name='network_samples')
    op.drop_table('network_samples')

    op.drop_index(op.f('ix_memory_samples_timestamp'), table_name='memory_samples')
    op.drop_index(op.f('ix_memory_samples_id'), table_name='memory_samples')
    op.drop_table('memory_samples')

    op.drop_index(op.f('ix_cpu_samples_timestamp'), table_name='cpu_samples')
    op.drop_index(op.f('ix_cpu_samples_id'), table_name='cpu_samples')
    op.drop_table('cpu_samples')
