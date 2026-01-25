"""add_power_management_tables

Revision ID: 005_power_management
Revises: 004_add_monitoring_columns
Create Date: 2026-01-24

Creates power management tables for CPU frequency scaling:
- power_profile_logs: History of profile changes
- power_demand_logs: History of power demands
- power_profile_configs: Custom profile configurations
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '005_power_management'
down_revision: Union[str, Sequence[str], None] = '004_monitoring_columns'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create power management tables."""

    # Power profile logs - tracks profile changes
    op.create_table(
        'power_profile_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('profile', sa.String(20), nullable=False),
        sa.Column('previous_profile', sa.String(20), nullable=True),
        sa.Column('reason', sa.String(200), nullable=False),
        sa.Column('source', sa.String(100), nullable=True),
        sa.Column('frequency_mhz', sa.Float(), nullable=True),
        sa.Column('user', sa.String(100), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_power_profile_logs_id'), 'power_profile_logs', ['id'], unique=False)
    op.create_index(op.f('ix_power_profile_logs_timestamp'), 'power_profile_logs', ['timestamp'], unique=False)
    op.create_index(op.f('ix_power_profile_logs_profile'), 'power_profile_logs', ['profile'], unique=False)
    op.create_index(op.f('ix_power_profile_logs_source'), 'power_profile_logs', ['source'], unique=False)
    op.create_index('idx_power_profile_timestamp', 'power_profile_logs', ['profile', 'timestamp'], unique=False)

    # Power demand logs - tracks demand registrations
    op.create_table(
        'power_demand_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('action', sa.String(20), nullable=False),
        sa.Column('source', sa.String(100), nullable=False),
        sa.Column('level', sa.String(20), nullable=False),
        sa.Column('description', sa.String(500), nullable=True),
        sa.Column('timeout_seconds', sa.Integer(), nullable=True),
        sa.Column('resulting_profile', sa.String(20), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_power_demand_logs_id'), 'power_demand_logs', ['id'], unique=False)
    op.create_index(op.f('ix_power_demand_logs_timestamp'), 'power_demand_logs', ['timestamp'], unique=False)
    op.create_index(op.f('ix_power_demand_logs_source'), 'power_demand_logs', ['source'], unique=False)
    op.create_index('idx_power_demand_source_timestamp', 'power_demand_logs', ['source', 'timestamp'], unique=False)

    # Power profile configs - custom profile settings
    op.create_table(
        'power_profile_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('profile', sa.String(20), nullable=False),
        sa.Column('governor', sa.String(20), nullable=False, server_default='powersave'),
        sa.Column('energy_performance_preference', sa.String(30), nullable=False, server_default='balance_power'),
        sa.Column('min_freq_mhz', sa.Integer(), nullable=True),
        sa.Column('max_freq_mhz', sa.Integer(), nullable=True),
        sa.Column('description', sa.String(200), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('profile')
    )
    op.create_index(op.f('ix_power_profile_configs_id'), 'power_profile_configs', ['id'], unique=False)
    op.create_index(op.f('ix_power_profile_configs_profile'), 'power_profile_configs', ['profile'], unique=True)


def downgrade() -> None:
    """Drop power management tables."""
    op.drop_index(op.f('ix_power_profile_configs_profile'), table_name='power_profile_configs')
    op.drop_index(op.f('ix_power_profile_configs_id'), table_name='power_profile_configs')
    op.drop_table('power_profile_configs')

    op.drop_index('idx_power_demand_source_timestamp', table_name='power_demand_logs')
    op.drop_index(op.f('ix_power_demand_logs_source'), table_name='power_demand_logs')
    op.drop_index(op.f('ix_power_demand_logs_timestamp'), table_name='power_demand_logs')
    op.drop_index(op.f('ix_power_demand_logs_id'), table_name='power_demand_logs')
    op.drop_table('power_demand_logs')

    op.drop_index('idx_power_profile_timestamp', table_name='power_profile_logs')
    op.drop_index(op.f('ix_power_profile_logs_source'), table_name='power_profile_logs')
    op.drop_index(op.f('ix_power_profile_logs_profile'), table_name='power_profile_logs')
    op.drop_index(op.f('ix_power_profile_logs_timestamp'), table_name='power_profile_logs')
    op.drop_index(op.f('ix_power_profile_logs_id'), table_name='power_profile_logs')
    op.drop_table('power_profile_logs')
