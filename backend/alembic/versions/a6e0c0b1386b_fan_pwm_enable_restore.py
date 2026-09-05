"""fan pwm_enable restore

Revision ID: a6e0c0b1386b
Revises: 193f03f94b4e
Create Date: 2026-09-06 01:15:47.353323

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a6e0c0b1386b'
down_revision: Union[str, Sequence[str], None] = '193f03f94b4e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('fan_configs', sa.Column('pwm_enable_restore', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('fan_configs', 'pwm_enable_restore')
