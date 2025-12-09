"""add_mobile_device_tables

Revision ID: 857f82ecde36
Revises: 27cc09d8d50c
Create Date: 2025-12-07 22:35:14.611943

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '857f82ecde36'
down_revision: Union[str, Sequence[str], None] = '27cc09d8d50c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create mobile_devices table
    op.create_table(
        'mobile_devices',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('device_name', sa.String(), nullable=False),
        sa.Column('device_type', sa.String(), nullable=False),
        sa.Column('device_model', sa.String(), nullable=True),
        sa.Column('os_version', sa.String(), nullable=True),
        sa.Column('app_version', sa.String(), nullable=True),
        sa.Column('push_token', sa.String(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('last_sync', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_mobile_devices_user_id'), 'mobile_devices', ['user_id'], unique=False)

    # Create mobile_registration_tokens table
    op.create_table(
        'mobile_registration_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('used', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token')
    )

    # Create camera_backups table
    op.create_table(
        'camera_backups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.String(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('backup_quality', sa.String(), nullable=False, server_default="'high'"),
        sa.Column('wifi_only', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('delete_after_upload', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('video_backup', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('photos_uploaded', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('videos_uploaded', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_backup', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['device_id'], ['mobile_devices.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_camera_backups_device_id'), 'camera_backups', ['device_id'], unique=True)

    # Create sync_folders table
    op.create_table(
        'sync_folders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.String(), nullable=False),
        sa.Column('local_path', sa.String(), nullable=False),
        sa.Column('remote_path', sa.String(), nullable=False),
        sa.Column('sync_type', sa.String(), nullable=False),
        sa.Column('auto_sync', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('last_sync', sa.DateTime(), nullable=True),
        sa.Column('sync_status', sa.String(), nullable=False, server_default="'idle'"),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['device_id'], ['mobile_devices.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create upload_queue table
    op.create_table(
        'upload_queue',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.String(), nullable=False),
        sa.Column('filename', sa.String(), nullable=False),
        sa.Column('remote_path', sa.String(), nullable=False),
        sa.Column('file_size', sa.BigInteger(), nullable=False),
        sa.Column('uploaded_bytes', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(), nullable=False, server_default="'pending'"),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_message', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['device_id'], ['mobile_devices.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('upload_queue')
    op.drop_table('sync_folders')
    op.drop_index(op.f('ix_camera_backups_device_id'), table_name='camera_backups')
    op.drop_table('camera_backups')
    op.drop_table('mobile_registration_tokens')
    op.drop_index(op.f('ix_mobile_devices_user_id'), table_name='mobile_devices')
    op.drop_table('mobile_devices')
