"""add can_manage_bluetooth permission

Revision ID: e7c2a9d41f86
Revises: c3a7f0d51b64
Create Date: 2026-09-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7c2a9d41f86'
down_revision: Union[str, Sequence[str], None] = 'c3a7f0d51b64'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fuegt can_manage_bluetooth zu user_power_permissions hinzu (standardmaessig aus)."""
    op.add_column(
        'user_power_permissions',
        sa.Column('can_manage_bluetooth', sa.Boolean(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    """Entfernt can_manage_bluetooth."""
    op.drop_column('user_power_permissions', 'can_manage_bluetooth')
