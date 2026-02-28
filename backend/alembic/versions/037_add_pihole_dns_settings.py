"""add pihole dns settings

Revision ID: 037_add_pihole_dns_settings
Revises: 036_add_pihole_failover_fields
Create Date: 2026-02-28 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '037_add_pihole_dns_settings'
down_revision: Union[str, Sequence[str], None] = '036_add_pihole_failover_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add DNS settings columns to pihole_config."""
    op.add_column('pihole_config', sa.Column('dns_dnssec', sa.Boolean(), nullable=False, server_default='0'))
    op.add_column('pihole_config', sa.Column('dns_rev_server', sa.String(length=500), nullable=True))
    op.add_column('pihole_config', sa.Column('dns_rate_limit_count', sa.Integer(), nullable=False, server_default='1000'))
    op.add_column('pihole_config', sa.Column('dns_rate_limit_interval', sa.Integer(), nullable=False, server_default='60'))
    op.add_column('pihole_config', sa.Column('dns_domain_needed', sa.Boolean(), nullable=False, server_default='0'))
    op.add_column('pihole_config', sa.Column('dns_bogus_priv', sa.Boolean(), nullable=False, server_default='1'))
    op.add_column('pihole_config', sa.Column('dns_domain_name', sa.String(length=100), nullable=False, server_default='lan'))
    op.add_column('pihole_config', sa.Column('dns_expand_hosts', sa.Boolean(), nullable=False, server_default='0'))


def downgrade() -> None:
    """Remove DNS settings columns from pihole_config."""
    op.drop_column('pihole_config', 'dns_expand_hosts')
    op.drop_column('pihole_config', 'dns_domain_name')
    op.drop_column('pihole_config', 'dns_bogus_priv')
    op.drop_column('pihole_config', 'dns_domain_needed')
    op.drop_column('pihole_config', 'dns_rate_limit_interval')
    op.drop_column('pihole_config', 'dns_rate_limit_count')
    op.drop_column('pihole_config', 'dns_rev_server')
    op.drop_column('pihole_config', 'dns_dnssec')
