"""add smb_enabled column to users table

Revision ID: 025_samba_support
Revises: 024_webdav_state
Create Date: 2026-02-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '025_samba_support'
down_revision: Union[str, Sequence[str], None] = '024_webdav_state'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('smb_enabled', sa.Boolean(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('users', 'smb_enabled')
