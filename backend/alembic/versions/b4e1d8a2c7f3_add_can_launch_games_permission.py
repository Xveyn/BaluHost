"""add can_launch_games permission

Revision ID: b4e1d8a2c7f3
Revises: 19b0fbf9df31
Create Date: 2026-09-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4e1d8a2c7f3'
down_revision: Union[str, Sequence[str], None] = '19b0fbf9df31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fuegt can_launch_games zu user_power_permissions hinzu (standardmaessig aus)."""
    op.add_column(
        'user_power_permissions',
        sa.Column('can_launch_games', sa.Boolean(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    """Entfernt can_launch_games."""
    op.drop_column('user_power_permissions', 'can_launch_games')
