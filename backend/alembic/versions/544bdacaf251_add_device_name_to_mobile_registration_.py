"""Add device_name to mobile_registration_tokens

Revision ID: 544bdacaf251
Revises: 048_add_ad_discovery_tables
Create Date: 2026-03-28 20:10:51.015450

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '544bdacaf251'
down_revision: Union[str, Sequence[str], None] = '048_add_ad_discovery_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add device_name column to store user-chosen name from QR generation."""
    op.add_column('mobile_registration_tokens', sa.Column('device_name', sa.String(), nullable=True))


def downgrade() -> None:
    """Remove device_name column."""
    op.drop_column('mobile_registration_tokens', 'device_name')
