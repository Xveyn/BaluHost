"""Type comparison hook for Alembic autogenerate (wired in ``alembic/env.py``).

Silences exactly one known, dialect-intended difference and nothing else.

Migration ``71fe791d28d6`` widens ``status_bar_pill_config.pill_id`` from
VARCHAR(32) to VARCHAR(96) on PostgreSQL only: SQLite cannot change a column
type in place and does not enforce the length anyway. Every SQLite dev
database therefore keeps VARCHAR(32), and autogenerate reported an
``alter_column`` for it on every run - which then had to be deleted by hand
from whatever unrelated migration was being generated (#549).

**Deliberately not a general "ignore VARCHAR length on SQLite" rule.** SQLite
not enforcing lengths is exactly why the original 32-char column only failed
in production. A blanket filter would make autogenerate on SQLite silent about
the next forgotten widening too. So only this column, only 32 -> 96, only on
SQLite; every other mismatch - including another length on this column -
falls through to Alembic's default comparison.
"""
from __future__ import annotations

from typing import Any, Optional

import sqlalchemy as sa

# (table, column, length in a SQLite dev DB, length in the model)
_SQLITE_ONLY_WIDENINGS = {
    ("status_bar_pill_config", "pill_id", 32, 96),
}


def compare_type(
    context: Any,
    inspected_column: Any,
    metadata_column: sa.Column,
    inspected_type: Any,
    metadata_type: Any,
) -> Optional[bool]:
    """Alembic ``compare_type`` callable.

    Returns:
        False to report "no change" for a known SQLite-only widening,
        None to let Alembic's default comparison decide everything else.
    """
    if context.dialect.name != "sqlite":
        return None
    if not isinstance(inspected_type, sa.String) or not isinstance(metadata_type, sa.String):
        return None
    key = (
        metadata_column.table.name,
        metadata_column.name,
        inspected_type.length,
        metadata_type.length,
    )
    if key in _SQLITE_ONLY_WIDENINGS:
        return False
    return None
