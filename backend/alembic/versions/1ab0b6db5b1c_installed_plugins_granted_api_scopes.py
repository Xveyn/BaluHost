"""installed_plugins granted_api_scopes

Revision ID: 1ab0b6db5b1c
Revises: cu_suspend_on_exit
Create Date: 2026-06-22 21:41:01.326755

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1ab0b6db5b1c'
down_revision: Union[str, Sequence[str], None] = 'cu_suspend_on_exit'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('installed_plugins', sa.Column('granted_api_scopes', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('installed_plugins', 'granted_api_scopes')
