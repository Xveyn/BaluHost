"""add_rate_limit_config_table

Revision ID: e2b5fd2fe391
Revises: 9f43650fd9ef
Create Date: 2026-01-02 19:39:54.846460

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2b5fd2fe391'
down_revision: Union[str, Sequence[str], None] = '9f43650fd9ef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create rate_limit_configs table."""
    op.create_table(
        'rate_limit_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('endpoint_type', sa.String(length=50), nullable=False),
        sa.Column('limit_string', sa.String(length=20), nullable=False),
        sa.Column('description', sa.String(length=200), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_rate_limit_configs_id'), 'rate_limit_configs', ['id'], unique=False)
    op.create_index(op.f('ix_rate_limit_configs_endpoint_type'), 'rate_limit_configs', ['endpoint_type'], unique=True)


def downgrade() -> None:
    """Drop rate_limit_configs table."""
    op.drop_index(op.f('ix_rate_limit_configs_endpoint_type'), table_name='rate_limit_configs')
    op.drop_index(op.f('ix_rate_limit_configs_id'), table_name='rate_limit_configs')
    op.drop_table('rate_limit_configs')
