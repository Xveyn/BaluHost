"""sleep runtime state (#823)

Revision ID: e5b2c8d4a917
Revises: c7a3e9f1d2b4
Create Date: 2026-11-12 00:00:00.000000

Singleton-Zeile, in der der Primary seinen Sleep-Zustand veroeffentlicht,
damit jeder API-Prozess dieselbe Antwort gibt.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5b2c8d4a917'
down_revision: Union[str, Sequence[str], None] = 'c7a3e9f1d2b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'sleep_runtime_state',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('current_state', sa.String(length=32), nullable=False,
                  server_default='awake'),
        sa.Column('state_since', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('updated_by_pid', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('sleep_runtime_state')
