"""add_is_active_to_users

Revision ID: 152e33e84ff7
Revises: b1868e4ae3b3
Create Date: 2025-11-23 18:24:36.535735

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '152e33e84ff7'
down_revision: Union[str, Sequence[str], None] = 'b1868e4ae3b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add is_active column with default True
    op.add_column('users', sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove is_active column
    op.drop_column('users', 'is_active')
