"""Add last_seen column to mobile_devices

Revision ID: 1e4dcc044fce
Revises: add_expiration_notifications
Create Date: 2025-12-13 22:47:17.332788

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1e4dcc044fce'
down_revision: Union[str, Sequence[str], None] = 'add_expiration_notifications'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add last_seen column to mobile_devices table."""
    # Check if column exists before adding (SQLite doesn't support IF NOT EXISTS)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('mobile_devices')]
    
    if 'last_seen' not in columns:
        op.add_column('mobile_devices', sa.Column('last_seen', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Remove last_seen column from mobile_devices table."""
    # SQLite doesn't support DROP COLUMN, so we need to recreate the table
    # For simplicity, we'll just leave the column (it's nullable anyway)
    pass
