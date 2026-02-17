"""Add TOTP 2FA columns to users table

Revision ID: 74aa416f29d6
Revises: f1x_cloud_oauth_per_user
Create Date: 2026-02-17 17:51:49.633421

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '74aa416f29d6'
down_revision: Union[str, Sequence[str], None] = 'f1x_cloud_oauth_per_user'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add TOTP 2FA columns to users table."""
    op.add_column('users', sa.Column('totp_secret_encrypted', sa.String(length=500), nullable=True))
    op.add_column('users', sa.Column('totp_enabled', sa.Boolean(), server_default='0', nullable=False))
    op.add_column('users', sa.Column('totp_backup_codes_encrypted', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('totp_enabled_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Remove TOTP 2FA columns from users table."""
    op.drop_column('users', 'totp_enabled_at')
    op.drop_column('users', 'totp_backup_codes_encrypted')
    op.drop_column('users', 'totp_enabled')
    op.drop_column('users', 'totp_secret_encrypted')
