"""add available_update + last_update_check_at to installed_plugins

Revision ID: b9f2e3a1c7d4
Revises: 1a72b07a9a99
Create Date: 2026-04-14 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b9f2e3a1c7d4'
down_revision: Union[str, Sequence[str], None] = '1a72b07a9a99'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add plugin update tracking columns to installed_plugins."""
    op.add_column(
        'installed_plugins',
        sa.Column('available_update', sa.String(length=50), nullable=True),
    )
    op.add_column(
        'installed_plugins',
        sa.Column(
            'last_update_check_at',
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Remove plugin update tracking columns."""
    op.drop_column('installed_plugins', 'last_update_check_at')
    op.drop_column('installed_plugins', 'available_update')
