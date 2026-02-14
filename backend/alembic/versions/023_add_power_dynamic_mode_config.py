"""add power_dynamic_mode_config table

Revision ID: 023_dynamic_mode
Revises: 022_scheduler_state
Create Date: 2026-02-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '023_dynamic_mode'
down_revision: Union[str, Sequence[str], None] = '022_scheduler_state'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create power_dynamic_mode_config table with default singleton row."""
    op.create_table(
        'power_dynamic_mode_config',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('governor', sa.String(30), nullable=False, server_default='powersave'),
        sa.Column('min_freq_mhz', sa.Integer(), nullable=False, server_default='400'),
        sa.Column('max_freq_mhz', sa.Integer(), nullable=False, server_default='4600'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # Insert default singleton row
    op.execute(
        "INSERT INTO power_dynamic_mode_config (id, enabled, governor, min_freq_mhz, max_freq_mhz) "
        "VALUES (1, false, 'powersave', 400, 4600)"
    )


def downgrade() -> None:
    """Drop power_dynamic_mode_config table."""
    op.drop_table('power_dynamic_mode_config')
