"""add_power_auto_scaling_config

Revision ID: 006_power_auto_scaling
Revises: 005_power_management
Create Date: 2026-01-24

Adds power_auto_scaling_config table for persistent auto-scaling settings.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '006_power_auto_scaling'
down_revision: Union[str, Sequence[str], None] = '005_power_management'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create power_auto_scaling_config table."""

    op.create_table(
        'power_auto_scaling_config',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('cpu_surge_threshold', sa.Integer(), nullable=False, server_default='80'),
        sa.Column('cpu_medium_threshold', sa.Integer(), nullable=False, server_default='50'),
        sa.Column('cpu_low_threshold', sa.Integer(), nullable=False, server_default='20'),
        sa.Column('cooldown_seconds', sa.Integer(), nullable=False, server_default='60'),
        sa.Column('use_cpu_monitoring', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_power_auto_scaling_config_id'), 'power_auto_scaling_config', ['id'], unique=False)

    # Insert default config (singleton pattern)
    op.execute("""
        INSERT INTO power_auto_scaling_config (
            id, enabled, cpu_surge_threshold, cpu_medium_threshold,
            cpu_low_threshold, cooldown_seconds, use_cpu_monitoring
        ) VALUES (1, 0, 80, 50, 20, 60, 1)
    """)


def downgrade() -> None:
    """Drop power_auto_scaling_config table."""
    op.drop_index(op.f('ix_power_auto_scaling_config_id'), table_name='power_auto_scaling_config')
    op.drop_table('power_auto_scaling_config')
