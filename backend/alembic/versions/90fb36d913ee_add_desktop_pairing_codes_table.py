"""add desktop_pairing_codes table

Revision ID: 90fb36d913ee
Revises: 9c00b193b5bd
Create Date: 2026-02-20 20:55:27.950511

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '90fb36d913ee'
down_revision: Union[str, Sequence[str], None] = '9c00b193b5bd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('desktop_pairing_codes',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('device_code', sa.String(length=64), nullable=False),
    sa.Column('user_code', sa.String(length=6), nullable=False),
    sa.Column('device_name', sa.String(length=255), nullable=False),
    sa.Column('device_id', sa.String(length=255), nullable=False),
    sa.Column('platform', sa.String(length=50), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('approved_at', sa.DateTime(), nullable=True),
    sa.Column('failed_attempts', sa.Integer(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_desktop_pairing_codes_device_code'), 'desktop_pairing_codes', ['device_code'], unique=True)
    op.create_index(op.f('ix_desktop_pairing_codes_user_code'), 'desktop_pairing_codes', ['user_code'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_desktop_pairing_codes_user_code'), table_name='desktop_pairing_codes')
    op.drop_index(op.f('ix_desktop_pairing_codes_device_code'), table_name='desktop_pairing_codes')
    op.drop_table('desktop_pairing_codes')
