"""add ssd_cache_configs table

Revision ID: 28cac30edbcb
Revises: 025_samba_support
Create Date: 2026-02-15 23:07:01.386917

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '28cac30edbcb'
down_revision: Union[str, Sequence[str], None] = '025_samba_support'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create ssd_cache_configs table."""
    op.create_table('ssd_cache_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('array_name', sa.String(length=64), nullable=False),
        sa.Column('cache_device', sa.String(length=64), nullable=False),
        sa.Column('mode', sa.String(length=20), nullable=False),
        sa.Column('sequential_cutoff_bytes', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('attached_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_ssd_cache_configs_array_name'), 'ssd_cache_configs', ['array_name'], unique=True)
    op.create_index(op.f('ix_ssd_cache_configs_id'), 'ssd_cache_configs', ['id'], unique=False)
    op.create_index(op.f('ix_ssd_cache_configs_is_active'), 'ssd_cache_configs', ['is_active'], unique=False)


def downgrade() -> None:
    """Drop ssd_cache_configs table."""
    op.drop_index(op.f('ix_ssd_cache_configs_is_active'), table_name='ssd_cache_configs')
    op.drop_index(op.f('ix_ssd_cache_configs_id'), table_name='ssd_cache_configs')
    op.drop_index(op.f('ix_ssd_cache_configs_array_name'), table_name='ssd_cache_configs')
    op.drop_table('ssd_cache_configs')
