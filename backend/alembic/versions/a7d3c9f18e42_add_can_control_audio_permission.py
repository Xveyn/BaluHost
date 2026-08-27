"""add can_control_audio permission

Revision ID: a7d3c9f18e42
Revises: 16ea14ef13bb
Create Date: 2026-08-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7d3c9f18e42'
down_revision: Union[str, Sequence[str], None] = '16ea14ef13bb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fügt can_control_audio zu user_power_permissions hinzu (standardmäßig aus)."""
    op.add_column(
        'user_power_permissions',
        sa.Column('can_control_audio', sa.Boolean(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    """Entfernt can_control_audio."""
    op.drop_column('user_power_permissions', 'can_control_audio')
