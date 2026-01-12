"""Merge migration branches

Revision ID: b5a0a9df91ea
Revises: add_remote_server_start, fix_mobile_device_user_id_type
Create Date: 2026-01-12 22:07:48.801773

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b5a0a9df91ea'
down_revision: Union[str, Sequence[str], None] = ('add_remote_server_start', 'fix_mobile_device_user_id_type')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
