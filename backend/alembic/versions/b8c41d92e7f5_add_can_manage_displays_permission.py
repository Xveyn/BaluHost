"""add can_manage_displays permission

Revision ID: b8c41d92e7f5
Revises: e2f81c4a7b93
Create Date: 2026-09-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8c41d92e7f5'
down_revision: Union[str, Sequence[str], None] = 'e2f81c4a7b93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fuegt can_manage_displays zu user_power_permissions hinzu (standardmaessig aus)."""
    op.add_column(
        'user_power_permissions',
        sa.Column('can_manage_displays', sa.Boolean(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    """Entfernt can_manage_displays."""
    op.drop_column('user_power_permissions', 'can_manage_displays')
