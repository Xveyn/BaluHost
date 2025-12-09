"""add_expiration_notifications_table

Revision ID: add_expiration_notifications
Revises: add_mobile_device_expires_at_manual
Create Date: 2025-12-09 23:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_expiration_notifications'
down_revision: Union[str, Sequence[str], None] = 'add_mobile_device_expires_at_manual'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create expiration_notifications table for tracking sent warnings."""
    op.create_table(
        'expiration_notifications',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('device_id', sa.String(), nullable=False),
        sa.Column('notification_type', sa.String(), nullable=False),
        sa.Column('sent_at', sa.DateTime(), nullable=False),
        sa.Column('success', sa.Boolean(), nullable=False),
        sa.Column('fcm_message_id', sa.String(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('device_expires_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['device_id'], ['mobile_devices.id'], ondelete='CASCADE')
    )
    
    # Create index for faster queries
    op.create_index(
        'ix_expiration_notifications_device_id',
        'expiration_notifications',
        ['device_id']
    )
    op.create_index(
        'ix_expiration_notifications_sent_at',
        'expiration_notifications',
        ['sent_at']
    )


def downgrade() -> None:
    """Drop expiration_notifications table."""
    op.drop_index('ix_expiration_notifications_sent_at', table_name='expiration_notifications')
    op.drop_index('ix_expiration_notifications_device_id', table_name='expiration_notifications')
    op.drop_table('expiration_notifications')
