"""add user_notification_routing table

Revision ID: 1a72b07a9a99
Revises: 049_recreate_sync_tables
Create Date: 2026-04-03 14:49:01.017766

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1a72b07a9a99'
down_revision: Union[str, Sequence[str], None] = '049_recreate_sync_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('user_notification_routing',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('receive_raid', sa.Boolean(), server_default='0', nullable=False),
    sa.Column('receive_smart', sa.Boolean(), server_default='0', nullable=False),
    sa.Column('receive_backup', sa.Boolean(), server_default='0', nullable=False),
    sa.Column('receive_scheduler', sa.Boolean(), server_default='0', nullable=False),
    sa.Column('receive_system', sa.Boolean(), server_default='0', nullable=False),
    sa.Column('receive_security', sa.Boolean(), server_default='0', nullable=False),
    sa.Column('receive_sync', sa.Boolean(), server_default='0', nullable=False),
    sa.Column('receive_vpn', sa.Boolean(), server_default='0', nullable=False),
    sa.Column('granted_by', sa.Integer(), nullable=True),
    sa.Column('granted_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['granted_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_notification_routing_id'), 'user_notification_routing', ['id'], unique=False)
    op.create_index(op.f('ix_user_notification_routing_user_id'), 'user_notification_routing', ['user_id'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_user_notification_routing_user_id'), table_name='user_notification_routing')
    op.drop_index(op.f('ix_user_notification_routing_id'), table_name='user_notification_routing')
    op.drop_table('user_notification_routing')
