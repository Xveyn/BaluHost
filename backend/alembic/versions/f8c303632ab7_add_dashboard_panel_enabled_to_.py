"""add dashboard_panel_enabled to installed_plugins

Revision ID: f8c303632ab7
Revises: 957690475eb2
Create Date: 2026-03-18 20:32:01.678155

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f8c303632ab7'
down_revision: Union[str, Sequence[str], None] = '957690475eb2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add dashboard_panel_enabled column to installed_plugins."""
    op.add_column(
        'installed_plugins',
        sa.Column(
            'dashboard_panel_enabled',
            sa.Boolean(),
            server_default='0',
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Remove dashboard_panel_enabled column from installed_plugins."""
    op.drop_column('installed_plugins', 'dashboard_panel_enabled')
