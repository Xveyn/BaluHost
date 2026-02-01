"""Add energy price configuration table

Revision ID: 016_energy_price
Revises: 015_updates
Create Date: 2026-02-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '016_energy_price'
down_revision: Union[str, None] = '015_updates'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create energy price configuration table."""
    op.create_table(
        'energy_price_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cost_per_kwh', sa.Float(), nullable=False, server_default='0.40'),
        sa.Column('currency', sa.String(10), nullable=False, server_default='EUR'),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_energy_price_configs_id', 'energy_price_configs', ['id'], unique=False)

    # Insert default configuration row (singleton pattern)
    op.execute(
        "INSERT INTO energy_price_configs (id, cost_per_kwh, currency) "
        "VALUES (1, 0.40, 'EUR')"
    )


def downgrade() -> None:
    """Drop energy price configuration table."""
    op.drop_index('ix_energy_price_configs_id', table_name='energy_price_configs')
    op.drop_table('energy_price_configs')
