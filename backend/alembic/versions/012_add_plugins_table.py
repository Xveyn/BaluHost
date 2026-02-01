"""Add installed plugins table

Revision ID: 012_plugins
Revises: 011_power_presets
Create Date: 2026-01-31

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import func


# revision identifiers, used by Alembic.
revision: str = '012_plugins'
down_revision: Union[str, None] = '011_power_presets'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create installed_plugins table for tracking plugin installations."""
    op.create_table(
        'installed_plugins',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('version', sa.String(50), nullable=False),
        sa.Column('display_name', sa.String(200), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, default=False, server_default='0'),
        sa.Column('granted_permissions', sa.JSON(), nullable=True),
        sa.Column('config', sa.JSON(), nullable=True),
        sa.Column('installed_at', sa.DateTime(timezone=True), server_default=func.now(), nullable=False),
        sa.Column('enabled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('disabled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('installed_by', sa.String(100), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_installed_plugins_name')
    )
    op.create_index('ix_installed_plugins_id', 'installed_plugins', ['id'], unique=False)
    op.create_index('ix_installed_plugins_name', 'installed_plugins', ['name'], unique=True)
    op.create_index('idx_installed_plugins_enabled', 'installed_plugins', ['is_enabled'], unique=False)


def downgrade() -> None:
    """Drop installed_plugins table."""
    op.drop_index('idx_installed_plugins_enabled', table_name='installed_plugins')
    op.drop_index('ix_installed_plugins_name', table_name='installed_plugins')
    op.drop_index('ix_installed_plugins_id', table_name='installed_plugins')
    op.drop_table('installed_plugins')
