"""sleep runtime details (#834)

Revision ID: b8e5f1a7dc40
Revises: a7d4e0f6cb39
Create Date: 2026-11-17 00:00:00.000000

Der Primary veroeffentlicht neben dem Sleep-Zustand jetzt auch den
Idle-Zaehler, die pausierten Dienste und die heruntergefahrenen Platten, damit
`GET /api/system/sleep/status` auf jedem Worker dasselbe zeigt. Eine nullbare
Textspalte mit einem JSON-Objekt; NULL heisst "keine Details".
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8e5f1a7dc40'
down_revision: Union[str, Sequence[str], None] = 'a7d4e0f6cb39'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'sleep_runtime_state',
        sa.Column('details_json', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('sleep_runtime_state', 'details_json')
