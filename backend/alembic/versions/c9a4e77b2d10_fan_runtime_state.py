"""fan runtime state

Revision ID: c9a4e77b2d10
Revises: b3f7d21c8a04
Create Date: 2026-09-06 20:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9a4e77b2d10'
down_revision: Union[str, Sequence[str], None] = 'b3f7d21c8a04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'fan_runtime_state',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('has_write_permission', sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('updated_by_pid', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('fan_runtime_state')
