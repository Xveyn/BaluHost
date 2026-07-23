"""widen status bar pill_id column

Namespaced plugin pill ids (plugin:<plugin_name>:<suffix>) can exceed the
original VARCHAR(32) — e.g. "plugin:tapo_smart_plug:consumption" is 34
chars. On PostgreSQL that overflow raises DataError inside _ensure_rows()'s
INSERT, 500-ing both the admin config load and every status-strip poll.
SQLite does not enforce VARCHAR length, so this only bites in production.

PostgreSQL can ALTER COLUMN ... TYPE VARCHAR(96) in-place (metadata-only
widen, no data rewrite), so this is safe and fast on production data.

Revision ID: 71fe791d28d6
Revises: 08e59058edac
Create Date: 2026-07-22 23:03:06.971888

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '71fe791d28d6'
down_revision: Union[str, Sequence[str], None] = '08e59058edac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Widen status_bar_pill_config.pill_id from VARCHAR(32) to VARCHAR(96)."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.alter_column(
        'status_bar_pill_config', 'pill_id',
        existing_type=sa.String(length=32),
        type_=sa.String(length=96),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Revert status_bar_pill_config.pill_id back to VARCHAR(32).

    Lossy if any namespaced plugin pill id longer than 32 chars was
    persisted while this migration was applied — acceptable for a
    dev/rollback path, not something upgrade() needs to guard against.
    """
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.alter_column(
        'status_bar_pill_config', 'pill_id',
        existing_type=sa.String(length=96),
        type_=sa.String(length=32),
        existing_nullable=False,
    )
