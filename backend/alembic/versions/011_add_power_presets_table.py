"""Add power presets table

Revision ID: 011_power_presets
Revises: 010_scheduler_tables
Create Date: 2026-01-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import func


# revision identifiers, used by Alembic.
revision: str = '011_power_presets'
down_revision: Union[str, None] = '010_scheduler_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create power_presets table and seed system presets."""
    op.create_table(
        'power_presets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_system_preset', sa.Boolean(), nullable=False, default=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=False),
        sa.Column('base_clock_mhz', sa.Integer(), nullable=False, default=1500),
        sa.Column('idle_clock_mhz', sa.Integer(), nullable=False, default=800),
        sa.Column('low_clock_mhz', sa.Integer(), nullable=False, default=1200),
        sa.Column('medium_clock_mhz', sa.Integer(), nullable=False, default=2500),
        sa.Column('surge_clock_mhz', sa.Integer(), nullable=False, default=4200),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    op.create_index('ix_power_presets_id', 'power_presets', ['id'], unique=False)
    op.create_index('idx_power_preset_active', 'power_presets', ['is_active'], unique=False)
    op.create_index('idx_power_preset_system', 'power_presets', ['is_system_preset'], unique=False)

    # Seed system presets
    # Using raw SQL for compatibility with both SQLite and PostgreSQL
    op.execute("""
        INSERT INTO power_presets (
            name, description, is_system_preset, is_active,
            base_clock_mhz, idle_clock_mhz, low_clock_mhz, medium_clock_mhz, surge_clock_mhz
        ) VALUES (
            'Energy Saver',
            'Minimaler Stromverbrauch. Ideal für Leerlauf und leichte Aufgaben.',
            true, false,
            800, 400, 800, 1500, 2500
        )
    """)

    op.execute("""
        INSERT INTO power_presets (
            name, description, is_system_preset, is_active,
            base_clock_mhz, idle_clock_mhz, low_clock_mhz, medium_clock_mhz, surge_clock_mhz
        ) VALUES (
            'Balanced',
            'Ausgewogene Balance zwischen Leistung und Energieeffizienz.',
            true, true,
            1500, 800, 1200, 2500, 4200
        )
    """)

    op.execute("""
        INSERT INTO power_presets (
            name, description, is_system_preset, is_active,
            base_clock_mhz, idle_clock_mhz, low_clock_mhz, medium_clock_mhz, surge_clock_mhz
        ) VALUES (
            'Performance',
            'Maximale Leistung für anspruchsvolle Aufgaben.',
            true, false,
            2500, 1200, 2000, 3500, 4600
        )
    """)


def downgrade() -> None:
    """Remove power_presets table."""
    op.drop_index('idx_power_preset_system', table_name='power_presets')
    op.drop_index('idx_power_preset_active', table_name='power_presets')
    op.drop_index('ix_power_presets_id', table_name='power_presets')
    op.drop_table('power_presets')
