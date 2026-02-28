"""add pihole failover fields

Revision ID: 036_add_pihole_failover_fields
Revises: ea933eb48284
Create Date: 2026-02-27 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '036_add_pihole_failover_fields'
down_revision: Union[str, Sequence[str], None] = 'ea933eb48284'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add failover columns to pihole_config."""
    op.add_column('pihole_config', sa.Column('remote_pihole_url', sa.String(length=500), nullable=True))
    op.add_column('pihole_config', sa.Column('remote_password_encrypted', sa.Text(), nullable=True))
    op.add_column('pihole_config', sa.Column('failover_active', sa.Boolean(), nullable=False, server_default='0'))
    op.add_column('pihole_config', sa.Column('health_check_interval', sa.Integer(), nullable=False, server_default='30'))
    op.add_column('pihole_config', sa.Column('last_failover_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Remove failover columns from pihole_config."""
    op.drop_column('pihole_config', 'last_failover_at')
    op.drop_column('pihole_config', 'health_check_interval')
    op.drop_column('pihole_config', 'failover_active')
    op.drop_column('pihole_config', 'remote_password_encrypted')
    op.drop_column('pihole_config', 'remote_pihole_url')
