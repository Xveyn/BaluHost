"""add can_unlock_session permission

Revision ID: dcabe4cc2ebc
Revises: b661786568c1
Create Date: 2026-07-24 16:15:37.524546

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dcabe4cc2ebc'
down_revision: Union[str, Sequence[str], None] = 'b661786568c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add can_unlock_session to user_power_permissions (defaults to off)."""
    op.add_column(
        'user_power_permissions',
        sa.Column('can_unlock_session', sa.Boolean(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    """Drop can_unlock_session."""
    op.drop_column('user_power_permissions', 'can_unlock_session')
