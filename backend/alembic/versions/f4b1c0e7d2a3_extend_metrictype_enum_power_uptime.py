"""extend metrictype enum with POWER and UPTIME

Revision ID: f4b1c0e7d2a3
Revises: 48b9f26caec2
Create Date: 2026-05-01 22:00:00.000000

PostgreSQL's metrictype enum was created by an earlier migration without
'POWER' and 'UPTIME', so any SELECT/INSERT/UPDATE on monitoring_config
referencing those values fails with InvalidTextRepresentation. This was
the same root cause as the GPU enum bug fixed in e828c7b306d5: every
RetentionManager cleanup tick crashed at ~5s intervals on production.

ALTER TYPE ADD VALUE must run outside a transaction block in PostgreSQL,
hence the autocommit_block. SQLite (dev) doesn't have native enum types
and is skipped via dialect check.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4b1c0e7d2a3'
down_revision: Union[str, Sequence[str], None] = '48b9f26caec2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Extend metrictype enum with POWER and UPTIME (idempotent)."""
    conn = op.get_bind()

    if conn.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            conn.execute(sa.text("ALTER TYPE metrictype ADD VALUE IF NOT EXISTS 'POWER'"))
            conn.execute(sa.text("ALTER TYPE metrictype ADD VALUE IF NOT EXISTS 'UPTIME'"))


def downgrade() -> None:
    """No-op: PostgreSQL does not support removing enum values without
    rebuilding the type. Removing values is also unsafe if rows reference
    them, which is the whole point of this migration."""
    pass
