"""add extra_config to scheduler_configs

Revision ID: 021_extra_config
Revises: 22091492b438
Create Date: 2026-02-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '021_extra_config'
down_revision: Union[str, Sequence[str], None] = '22091492b438'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add extra_config column to scheduler_configs."""
    op.add_column('scheduler_configs', sa.Column('extra_config', sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove extra_config column from scheduler_configs."""
    op.drop_column('scheduler_configs', 'extra_config')
