"""merge smart_devices branch with main

Revision ID: 957690475eb2
Revises: 020_smart_devices, 043_add_uptime_samples
Create Date: 2026-03-18 20:31:49.328359

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '957690475eb2'
down_revision: Union[str, Sequence[str], None] = ('020_smart_devices', '043_add_uptime_samples')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
