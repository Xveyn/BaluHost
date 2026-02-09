"""grant_sequence_permissions

Revision ID: 018_seq_perms
Revises: 017_fix_bigint
Create Date: 2026-02-07

Fix: PostgreSQL sequence permissions for non-superuser DB roles.
Without USAGE on sequences, INSERTs into tables with SERIAL/IDENTITY
columns fail with 'permission denied for sequence <table>_id_seq'.
"""
from typing import Sequence, Union
from urllib.parse import urlparse

from alembic import op

from app.core.database import DATABASE_URL

# revision identifiers, used by Alembic.
revision: str = '018_seq_perms'
down_revision: Union[str, Sequence[str], None] = '017_fix_bigint'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_db_username() -> str | None:
    """Extract the database username from DATABASE_URL."""
    if not DATABASE_URL or not DATABASE_URL.startswith("postgresql"):
        return None
    try:
        parsed = urlparse(DATABASE_URL)
        return parsed.username
    except Exception:
        return None


def upgrade() -> None:
    """Grant USAGE, SELECT on all sequences to the application DB user.

    NOTE: This GRANT must be executed by the sequence owner (usually
    the 'postgres' superuser), not by the application role itself.
    When running Alembic as the application user, we skip the GRANT
    here and print instructions for the DBA to run manually.
    """
    username = _get_db_username()
    if username is None:
        # SQLite or unparseable URL — nothing to do
        return

    # Try the GRANT; if the current role lacks permission, print
    # a manual instruction instead of crashing the migration.
    try:
        op.execute(
            f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {username}"
        )
    except Exception:
        # The migration connection is inside a transaction —
        # we must let Alembic handle the rollback.  Re-raise after
        # printing guidance so the user knows what to do.
        print(
            "\n"
            "═══════════════════════════════════════════════════════════\n"
            "  Could not GRANT sequence permissions (insufficient privilege).\n"
            f"  Please run the following as the postgres superuser:\n\n"
            f"    sudo -u postgres psql -d baluhost -c \\\n"
            f"      \"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {username};\"\n"
            "\n"
            "  Then re-run: alembic upgrade head\n"
            "═══════════════════════════════════════════════════════════\n"
        )
        raise


def downgrade() -> None:
    """Revoke sequence permissions (best-effort)."""
    username = _get_db_username()
    if username is None:
        return

    op.execute(
        f"REVOKE USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public FROM {username}"
    )
