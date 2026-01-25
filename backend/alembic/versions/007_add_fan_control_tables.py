"""add fan control tables

Revision ID: 007
Revises: 006
Create Date: 2026-01-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '007_fan_control'
down_revision: Union[str, None] = '006_power_auto_scaling'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create fan control tables."""
    # Create fan_configs table
    op.create_table(
        'fan_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fan_id', sa.String(length=100), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('mode', sa.String(length=20), nullable=False, server_default='auto'),
        sa.Column('curve_json', sa.Text(), nullable=True),
        sa.Column('min_pwm_percent', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('max_pwm_percent', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('emergency_temp_celsius', sa.Float(), nullable=False, server_default='85.0'),
        sa.Column('temp_sensor_id', sa.String(length=100), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_fan_configs_id', 'fan_configs', ['id'])
    op.create_index('ix_fan_configs_fan_id', 'fan_configs', ['fan_id'], unique=True)
    op.create_index('ix_fan_configs_is_active', 'fan_configs', ['is_active'])

    # Create fan_samples table
    op.create_table(
        'fan_samples',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('fan_id', sa.String(length=100), nullable=False),
        sa.Column('pwm_percent', sa.Integer(), nullable=True),
        sa.Column('rpm', sa.Integer(), nullable=True),
        sa.Column('temperature_celsius', sa.Float(), nullable=True),
        sa.Column('mode', sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_fan_samples_id', 'fan_samples', ['id'])
    op.create_index('ix_fan_samples_timestamp', 'fan_samples', ['timestamp'])
    op.create_index('ix_fan_samples_fan_id', 'fan_samples', ['fan_id'])
    op.create_index('ix_fan_samples_fan_timestamp', 'fan_samples', ['fan_id', 'timestamp'])


def downgrade() -> None:
    """Drop fan control tables."""
    op.drop_index('ix_fan_samples_fan_timestamp', table_name='fan_samples')
    op.drop_index('ix_fan_samples_fan_id', table_name='fan_samples')
    op.drop_index('ix_fan_samples_timestamp', table_name='fan_samples')
    op.drop_index('ix_fan_samples_id', table_name='fan_samples')
    op.drop_table('fan_samples')

    op.drop_index('ix_fan_configs_is_active', table_name='fan_configs')
    op.drop_index('ix_fan_configs_fan_id', table_name='fan_configs')
    op.drop_index('ix_fan_configs_id', table_name='fan_configs')
    op.drop_table('fan_configs')
