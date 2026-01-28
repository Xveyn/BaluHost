"""add fan hysteresis column

Revision ID: 009
Revises: 008
Create Date: 2026-01-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '009_fan_hysteresis'
down_revision: Union[str, None] = '008_thread_usages'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add hysteresis_celsius column to fan_configs table."""
    op.add_column(
        'fan_configs',
        sa.Column('hysteresis_celsius', sa.Float(), nullable=False, server_default='3.0')
    )


def downgrade() -> None:
    """Remove hysteresis_celsius column from fan_configs table."""
    op.drop_column('fan_configs', 'hysteresis_celsius')
