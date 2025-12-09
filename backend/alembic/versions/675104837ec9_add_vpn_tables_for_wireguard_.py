"""Add VPN tables for WireGuard configuration

Revision ID: 675104837ec9
Revises: 857f82ecde36
Create Date: 2025-12-08 21:06:29.097090

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '675104837ec9'
down_revision: Union[str, Sequence[str], None] = '857f82ecde36'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create vpn_config table (singleton for server config)
    op.create_table(
        'vpn_config',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('server_private_key', sa.String(length=64), nullable=False),
        sa.Column('server_public_key', sa.String(length=64), nullable=False),
        sa.Column('server_ip', sa.String(length=15), nullable=False),
        sa.Column('server_port', sa.Integer(), nullable=False, server_default='51820'),
        sa.Column('network_cidr', sa.String(length=18), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('server_public_key')
    )
    op.create_index(op.f('ix_vpn_config_id'), 'vpn_config', ['id'], unique=False)
    
    # Create vpn_clients table
    op.create_table(
        'vpn_clients',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('device_name', sa.String(length=100), nullable=False),
        sa.Column('public_key', sa.String(length=64), nullable=False),
        sa.Column('preshared_key', sa.String(length=64), nullable=False),
        sa.Column('assigned_ip', sa.String(length=15), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('last_handshake', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('public_key'),
        sa.UniqueConstraint('assigned_ip')
    )
    op.create_index(op.f('ix_vpn_clients_id'), 'vpn_clients', ['id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_vpn_clients_id'), table_name='vpn_clients')
    op.drop_table('vpn_clients')
    op.drop_index(op.f('ix_vpn_config_id'), table_name='vpn_config')
    op.drop_table('vpn_config')
