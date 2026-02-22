"""Add service_heartbeats table

Revision ID: 143ea37285ad
Revises: 029_desktop_sync
Create Date: 2026-02-22 17:00:22.678837

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '143ea37285ad'
down_revision: Union[str, Sequence[str], None] = '029_desktop_sync'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('service_heartbeats',
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('is_running', sa.Boolean(), nullable=False),
    sa.Column('details_json', sa.Text(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('name')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('service_heartbeats')
