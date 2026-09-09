"""add block_suspend_in_gaming_mode to sleep_config

Governs whether Big Picture alone suppresses an automatic suspend. A running
game suppresses unconditionally and has no setting.

Default true: the column exists because the box suspended out from under a
running session, so shipping it off by default would leave the reported
problem unfixed until someone found the toggle.

Revision ID: c3a7f0d51b64
Revises: b8c41d92e7f5
Create Date: 2026-09-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3a7f0d51b64'
down_revision: Union[str, Sequence[str], None] = 'b8c41d92e7f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fuegt block_suspend_in_gaming_mode zu sleep_config hinzu (standardmaessig an)."""
    op.add_column(
        'sleep_config',
        sa.Column(
            'block_suspend_in_gaming_mode',
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    """Entfernt block_suspend_in_gaming_mode."""
    op.drop_column('sleep_config', 'block_suspend_in_gaming_mode')
