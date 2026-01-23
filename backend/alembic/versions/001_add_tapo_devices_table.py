"""Add tapo_devices table

Revision ID: 001_tapo_devices
Revises: c7fbef10fbee
Create Date: 2026-01-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_tapo_devices'
down_revision: Union[str, Sequence[str], None] = 'c7fbef10fbee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'tapo_devices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('device_type', sa.String(length=50), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=False),
        sa.Column('email_encrypted', sa.Text(), nullable=False),
        sa.Column('password_encrypted', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('is_monitoring', sa.Boolean(), nullable=False),
        sa.Column('last_connected', sa.DateTime(), nullable=True),
        sa.Column('last_error', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tapo_devices_id'), 'tapo_devices', ['id'], unique=False)
    op.create_index(op.f('ix_tapo_devices_is_active'), 'tapo_devices', ['is_active'], unique=False)
    op.create_index(op.f('ix_tapo_devices_ip_address'), 'tapo_devices', ['ip_address'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_tapo_devices_ip_address'), table_name='tapo_devices')
    op.drop_index(op.f('ix_tapo_devices_is_active'), table_name='tapo_devices')
    op.drop_index(op.f('ix_tapo_devices_id'), table_name='tapo_devices')
    op.drop_table('tapo_devices')
