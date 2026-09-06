"""fan gpu manual previous state

Revision ID: b3f7d21c8a04
Revises: a6e0c0b1386b
Create Date: 2026-09-06 17:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3f7d21c8a04'
down_revision: Union[str, Sequence[str], None] = 'a6e0c0b1386b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('fan_configs', sa.Column('gpu_manual_prev_level', sa.String(length=32), nullable=True))
    op.add_column('fan_configs', sa.Column('gpu_manual_prev_pwm_enable', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('fan_configs', 'gpu_manual_prev_pwm_enable')
    op.drop_column('fan_configs', 'gpu_manual_prev_level')
