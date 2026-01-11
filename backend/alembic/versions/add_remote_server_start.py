"""Add server and VPN profiles for remote server start feature

Revision ID: add_remote_server_start
Revises: e2b5fd2fe391
Create Date: 2025-12-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_remote_server_start'
down_revision: Union[str, Sequence[str], None] = 'e2b5fd2fe391'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create vpn_profiles table for user VPN configurations
    op.create_table(
        'vpn_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('vpn_type', sa.String(length=50), nullable=False),  # openvpn, wireguard, custom
        sa.Column('config_file_encrypted', sa.Text(), nullable=False),
        sa.Column('certificate_encrypted', sa.Text(), nullable=True),
        sa.Column('private_key_encrypted', sa.Text(), nullable=True),
        sa.Column('auto_connect', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_vpn_profiles_user_id', 'vpn_profiles', ['user_id'], unique=False)
    op.create_index('ix_vpn_profiles_created_at', 'vpn_profiles', ['created_at'], unique=False)
    
    # Create server_profiles table for remote server configurations
    op.create_table(
        'server_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('ssh_host', sa.String(length=255), nullable=False),
        sa.Column('ssh_port', sa.Integer(), nullable=False, server_default='22'),
        sa.Column('ssh_username', sa.String(length=100), nullable=False),
        sa.Column('ssh_key_encrypted', sa.Text(), nullable=False),
        sa.Column('vpn_profile_id', sa.Integer(), nullable=True),
        sa.Column('power_on_command', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_used', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['vpn_profile_id'], ['vpn_profiles.id'], ondelete='SET NULL'),
    )
    op.create_index('ix_server_profiles_user_id', 'server_profiles', ['user_id'], unique=False)
    op.create_index('ix_server_profiles_vpn_profile_id', 'server_profiles', ['vpn_profile_id'], unique=False)
    op.create_index('ix_server_profiles_created_at', 'server_profiles', ['created_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_server_profiles_created_at', table_name='server_profiles')
    op.drop_index('ix_server_profiles_vpn_profile_id', table_name='server_profiles')
    op.drop_index('ix_server_profiles_user_id', table_name='server_profiles')
    op.drop_table('server_profiles')
    
    op.drop_index('ix_vpn_profiles_created_at', table_name='vpn_profiles')
    op.drop_index('ix_vpn_profiles_user_id', table_name='vpn_profiles')
    op.drop_table('vpn_profiles')
