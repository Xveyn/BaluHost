"""add dns query tables

Revision ID: 038_add_dns_query_tables
Revises: 037_add_pihole_dns_settings
Create Date: 2026-03-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '038_add_dns_query_tables'
down_revision: Union[str, Sequence[str], None] = '037_add_pihole_dns_settings'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create dns_queries, dns_query_hourly_stats, dns_query_collector_state tables."""

    # --- dns_queries ---
    op.create_table(
        'dns_queries',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('domain', sa.String(length=253), nullable=False),
        sa.Column('client', sa.String(length=45), nullable=False),
        sa.Column('query_type', sa.String(length=10), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('reply_type', sa.String(length=20), nullable=True),
        sa.Column('response_time_ms', sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_dns_queries_timestamp', 'dns_queries', ['timestamp'])
    op.create_index('ix_dns_queries_domain', 'dns_queries', ['domain'])
    op.create_index('ix_dns_queries_client', 'dns_queries', ['client'])
    op.create_index('ix_dns_queries_status', 'dns_queries', ['status'])
    op.create_index('ix_dns_queries_ts_domain', 'dns_queries', ['timestamp', 'domain'])
    op.create_index('ix_dns_queries_ts_status', 'dns_queries', ['timestamp', 'status'])
    op.create_index('ix_dns_queries_ts_client', 'dns_queries', ['timestamp', 'client'])

    # --- dns_query_hourly_stats ---
    op.create_table(
        'dns_query_hourly_stats',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('hour', sa.DateTime(), nullable=False),
        sa.Column('total_queries', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('blocked_queries', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cached_queries', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('forwarded_queries', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('unique_domains', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('unique_clients', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('avg_response_time_ms', sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('hour'),
    )
    op.create_index('ix_dns_query_hourly_stats_hour', 'dns_query_hourly_stats', ['hour'])

    # --- dns_query_collector_state ---
    op.create_table(
        'dns_query_collector_state',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('last_fetched_timestamp', sa.Float(), nullable=False, server_default='0'),
        sa.Column('last_poll_at', sa.DateTime(), nullable=True),
        sa.Column('total_queries_stored', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('last_error', sa.String(length=500), nullable=True),
        sa.Column('last_error_at', sa.DateTime(), nullable=True),
        sa.Column('poll_interval_seconds', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('retention_days', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Drop dns query tables."""
    op.drop_table('dns_query_collector_state')
    op.drop_index('ix_dns_query_hourly_stats_hour', table_name='dns_query_hourly_stats')
    op.drop_table('dns_query_hourly_stats')
    op.drop_index('ix_dns_queries_ts_client', table_name='dns_queries')
    op.drop_index('ix_dns_queries_ts_status', table_name='dns_queries')
    op.drop_index('ix_dns_queries_ts_domain', table_name='dns_queries')
    op.drop_index('ix_dns_queries_status', table_name='dns_queries')
    op.drop_index('ix_dns_queries_client', table_name='dns_queries')
    op.drop_index('ix_dns_queries_domain', table_name='dns_queries')
    op.drop_index('ix_dns_queries_timestamp', table_name='dns_queries')
    op.drop_table('dns_queries')
