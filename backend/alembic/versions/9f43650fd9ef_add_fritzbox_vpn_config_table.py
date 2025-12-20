"""Add FritzBox VPN config table

Revision ID: 9f43650fd9ef
Revises: 1e4dcc044fce
Create Date: 2025-12-14 15:57:41.423128

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9f43650fd9ef'
down_revision: Union[str, Sequence[str], None] = '1e4dcc044fce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'fritzbox_vpn_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('private_key_encrypted', sa.String(length=255), nullable=False),
        sa.Column('preshared_key_encrypted', sa.String(length=255), nullable=False),
        sa.Column('address', sa.String(length=100), nullable=False),
        sa.Column('dns_servers', sa.String(length=255), nullable=False),
        sa.Column('peer_public_key', sa.String(length=64), nullable=False),
        sa.Column('allowed_ips', sa.Text(), nullable=False),
        sa.Column('endpoint', sa.String(length=255), nullable=False),
        sa.Column('persistent_keepalive', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('uploaded_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['uploaded_by_user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_fritzbox_vpn_configs_id', 'fritzbox_vpn_configs', ['id'])
    op.create_index('ix_fritzbox_vpn_configs_is_active', 'fritzbox_vpn_configs', ['is_active'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_fritzbox_vpn_configs_is_active', 'fritzbox_vpn_configs')
    op.drop_index('ix_fritzbox_vpn_configs_id', 'fritzbox_vpn_configs')
    op.drop_table('fritzbox_vpn_configs')
