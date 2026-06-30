"""mobile timestamp columns timezone aware

Brings backend/app/models/mobile.py in line with the models/CLAUDE.md
convention ("Timestamps: DateTime(timezone=True)") and fixes the root cause
of #241: naive TIMESTAMP WITHOUT TIME ZONE columns compared against an aware
datetime.now(timezone.utc) raise "can't compare offset-naive and
offset-aware datetimes".

PostgreSQL only -- ALTER COLUMN ... TYPE TIMESTAMPTZ is a no-op on SQLite
(dev mode), which has no real timezone-aware storage and always returns
naive datetimes on read regardless of declared column type; the defensive
naive->UTC guards added alongside #241 stay in application code for that
reason and are not removed by this migration.

Revision ID: 08e59058edac
Revises: 7fd13b0509a2
Create Date: 2026-06-30 22:43:59.988379

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '08e59058edac'
down_revision: Union[str, Sequence[str], None] = '7fd13b0509a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table, column, existing_nullable)
COLUMNS = [
    ("mobile_devices", "last_seen", True),
    ("mobile_devices", "last_sync", True),
    ("mobile_devices", "expires_at", True),
    ("mobile_devices", "created_at", False),
    ("mobile_devices", "updated_at", False),
    ("mobile_registration_tokens", "expires_at", False),
    ("mobile_registration_tokens", "created_at", False),
    ("camera_backups", "last_backup", True),
    ("camera_backups", "created_at", False),
    ("camera_backups", "updated_at", True),
    ("sync_folders", "last_sync", True),
    ("sync_folders", "created_at", False),
    ("sync_folders", "updated_at", True),
    ("upload_queue", "created_at", False),
    ("upload_queue", "started_at", True),
    ("upload_queue", "completed_at", True),
    ("expiration_notifications", "sent_at", False),
    ("expiration_notifications", "device_expires_at", False),
]


def upgrade() -> None:
    """Convert mobile.py timestamp columns from TIMESTAMP to TIMESTAMPTZ."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table, column, existing_nullable in COLUMNS:
        op.alter_column(
            table, column,
            type_=sa.DateTime(timezone=True),
            existing_type=sa.DateTime(),
            existing_nullable=existing_nullable,
            postgresql_using=f'"{column}" AT TIME ZONE \'UTC\'',
        )


def downgrade() -> None:
    """Convert back to naive TIMESTAMP (no precision/data loss -- the
    session is always pinned to UTC via core/database.py's _set_pg_timezone
    connect event, so AT TIME ZONE 'UTC' round-trips losslessly)."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table, column, existing_nullable in COLUMNS:
        op.alter_column(
            table, column,
            type_=sa.DateTime(),
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=existing_nullable,
            postgresql_using=f'"{column}" AT TIME ZONE \'UTC\'',
        )
