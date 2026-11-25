"""refresh token parent_jti (#847)

Revision ID: c9f2a6d3e581
Revises: b8e5f1a7dc40
Create Date: 2026-11-25 00:00:00.000000

Gleitende Kopplung: jede Rotation speichert den Nachfolger mit der JTI seines
Vorgaengers. Nullbar; NULL heisst "Erstausgabe".
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9f2a6d3e581'
down_revision: Union[str, Sequence[str], None] = 'b8e5f1a7dc40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'refresh_tokens',
        sa.Column('parent_jti', sa.String(length=36), nullable=True),
    )
    op.create_index('ix_refresh_tokens_parent_jti', 'refresh_tokens', ['parent_jti'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_refresh_tokens_parent_jti', table_name='refresh_tokens')
    op.drop_column('refresh_tokens', 'parent_jti')
