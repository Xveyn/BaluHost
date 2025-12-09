"""add_mobile_device_expires_at

Revision ID: add_mobile_device_expires_at_manual
Revises: 675104837ec9
Create Date: 2025-12-09 23:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_mobile_device_expires_at_manual'
down_revision: Union[str, Sequence[str], None] = '675104837ec9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add expires_at column to mobile_devices table."""
    # Add expires_at column to mobile_devices (nullable)
    with op.batch_alter_table('mobile_devices', schema=None) as batch_op:
        batch_op.add_column(sa.Column('expires_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Remove expires_at column from mobile_devices table."""
    with op.batch_alter_table('mobile_devices', schema=None) as batch_op:
        batch_op.drop_column('expires_at')
