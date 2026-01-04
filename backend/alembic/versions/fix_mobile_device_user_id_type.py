"""Fix mobile_device user_id type from String to Integer

Revision ID: fix_mobile_device_user_id_type
Revises: de1758600424
Create Date: 2026-01-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fix_mobile_device_user_id_type'
down_revision: Union[str, Sequence[str], None] = 'de1758600424'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - change user_id type from String to Integer."""
    # SQLite doesn't support ALTER COLUMN, so we need to recreate the table
    conn = op.get_bind()
    
    # For SQLite, we need to do a more complex migration
    if 'sqlite' in str(conn.engine.url):
        # Create new table with correct schema
        op.execute('''
            CREATE TABLE mobile_devices_new (
                id VARCHAR NOT NULL,
                user_id INTEGER NOT NULL,
                device_name VARCHAR NOT NULL,
                device_type VARCHAR NOT NULL,
                device_model VARCHAR,
                os_version VARCHAR,
                app_version VARCHAR,
                push_token VARCHAR,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                last_sync DATETIME,
                last_seen DATETIME,
                expires_at DATETIME,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                PRIMARY KEY (id),
                FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        ''')
        
        # Copy data, converting user_id to integer
        op.execute('''
            INSERT INTO mobile_devices_new
            SELECT id, CAST(user_id AS INTEGER), device_name, device_type,
                   device_model, os_version, app_version, push_token,
                   is_active, last_sync, last_seen, expires_at,
                   created_at, updated_at
            FROM mobile_devices
        ''')
        
        # Drop old table
        op.execute('DROP TABLE mobile_devices')
        
        # Rename new table
        op.execute('ALTER TABLE mobile_devices_new RENAME TO mobile_devices')
        
        # Recreate indices
        op.execute('CREATE INDEX ix_mobile_devices_user_id ON mobile_devices (user_id)')
    else:
        # For PostgreSQL and other databases
        with op.batch_alter_table('mobile_devices', schema=None) as batch_op:
            batch_op.alter_column('user_id', existing_type=sa.String(), type_=sa.Integer())


def downgrade() -> None:
    """Downgrade schema - change user_id type back to String."""
    conn = op.get_bind()
    
    if 'sqlite' in str(conn.engine.url):
        # Create new table with original schema
        op.execute('''
            CREATE TABLE mobile_devices_new (
                id VARCHAR NOT NULL,
                user_id VARCHAR NOT NULL,
                device_name VARCHAR NOT NULL,
                device_type VARCHAR NOT NULL,
                device_model VARCHAR,
                os_version VARCHAR,
                app_version VARCHAR,
                push_token VARCHAR,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                last_sync DATETIME,
                last_seen DATETIME,
                expires_at DATETIME,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                PRIMARY KEY (id),
                FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        ''')
        
        # Copy data
        op.execute('''
            INSERT INTO mobile_devices_new
            SELECT id, CAST(user_id AS TEXT), device_name, device_type,
                   device_model, os_version, app_version, push_token,
                   is_active, last_sync, last_seen, expires_at,
                   created_at, updated_at
            FROM mobile_devices
        ''')
        
        # Drop old table
        op.execute('DROP TABLE mobile_devices')
        
        # Rename new table
        op.execute('ALTER TABLE mobile_devices_new RENAME TO mobile_devices')
        
        # Recreate indices
        op.execute('CREATE INDEX ix_mobile_devices_user_id ON mobile_devices (user_id)')
    else:
        # For PostgreSQL and other databases
        with op.batch_alter_table('mobile_devices', schema=None) as batch_op:
            batch_op.alter_column('user_id', existing_type=sa.Integer(), type_=sa.String())
