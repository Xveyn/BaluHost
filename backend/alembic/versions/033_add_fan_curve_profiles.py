"""Add fan curve profiles table

Revision ID: 033_add_fan_curve_profiles
Revises: e379dccff562
Create Date: 2026-02-23 21:00:00.000000

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '033_add_fan_curve_profiles'
down_revision: Union[str, Sequence[str], None] = 'e379dccff562'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# System preset curves to seed
SYSTEM_PRESETS = {
    "silent": {
        "description": "Prioritizes quiet operation with lower fan speeds",
        "curve": [
            {"temp": 40, "pwm": 30},
            {"temp": 55, "pwm": 35},
            {"temp": 70, "pwm": 55},
            {"temp": 80, "pwm": 75},
            {"temp": 90, "pwm": 100},
        ],
    },
    "balanced": {
        "description": "Balance between noise and cooling performance",
        "curve": [
            {"temp": 35, "pwm": 30},
            {"temp": 50, "pwm": 50},
            {"temp": 70, "pwm": 80},
            {"temp": 85, "pwm": 100},
        ],
    },
    "performance": {
        "description": "Maximum cooling with higher fan speeds",
        "curve": [
            {"temp": 30, "pwm": 40},
            {"temp": 45, "pwm": 60},
            {"temp": 60, "pwm": 85},
            {"temp": 75, "pwm": 100},
        ],
    },
}


def upgrade() -> None:
    # Create fan_curve_profiles table
    op.create_table(
        'fan_curve_profiles',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(100), unique=True, nullable=False),
        sa.Column('description', sa.String(255), nullable=True),
        sa.Column('curve_json', sa.Text(), nullable=False),
        sa.Column('is_system', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Seed system presets
    fan_curve_profiles = sa.table(
        'fan_curve_profiles',
        sa.column('name', sa.String),
        sa.column('description', sa.String),
        sa.column('curve_json', sa.Text),
        sa.column('is_system', sa.Boolean),
    )
    op.bulk_insert(fan_curve_profiles, [
        {
            'name': name,
            'description': data['description'],
            'curve_json': json.dumps(data['curve']),
            'is_system': True,
        }
        for name, data in SYSTEM_PRESETS.items()
    ])

    # Add profile_id FK column to fan_schedule_entries
    op.add_column(
        'fan_schedule_entries',
        sa.Column('profile_id', sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        'fk_fan_schedule_entries_profile_id',
        'fan_schedule_entries',
        'fan_curve_profiles',
        ['profile_id'],
        ['id'],
        ondelete='SET NULL',
    )

    # Make curve_json nullable on fan_schedule_entries (entries with profile_id don't need it)
    op.alter_column(
        'fan_schedule_entries',
        'curve_json',
        existing_type=sa.Text(),
        nullable=True,
    )


def downgrade() -> None:
    # Make curve_json non-nullable again
    op.alter_column(
        'fan_schedule_entries',
        'curve_json',
        existing_type=sa.Text(),
        nullable=False,
    )

    op.drop_constraint('fk_fan_schedule_entries_profile_id', 'fan_schedule_entries', type_='foreignkey')
    op.drop_column('fan_schedule_entries', 'profile_id')
    op.drop_table('fan_curve_profiles')
