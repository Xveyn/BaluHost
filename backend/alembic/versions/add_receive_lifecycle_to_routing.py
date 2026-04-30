"""add receive_lifecycle column to user_notification_routing

Revision ID: c9e1lifecycle01
Revises: b42843d45987
Create Date: 2026-04-30 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9e1lifecycle01'
down_revision: Union[str, Sequence[str], None] = 'b42843d45987'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'user_notification_routing',
        sa.Column('receive_lifecycle', sa.Boolean(), server_default='0', nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('user_notification_routing', 'receive_lifecycle')
