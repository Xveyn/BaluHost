"""add steam_sessions table

Revision ID: b661786568c1
Revises: 71fe791d28d6
Create Date: 2026-07-24 09:29:49.593379

Teilprojekt 4/4 — siehe docs/superpowers/specs/2026-07-24-steam-session-history-dashboard-panel-design.md
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b661786568c1'
down_revision: Union[str, Sequence[str], None] = '71fe791d28d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create steam_sessions (play history for the steam_gaming plugin)."""
    op.create_table(
        'steam_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('app_id', sa.String(length=32), nullable=False),
        sa.Column('game_name', sa.String(length=200), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_steam_sessions_id', 'steam_sessions', ['id'])
    op.create_index('ix_steam_sessions_app_id', 'steam_sessions', ['app_id'])
    op.create_index('ix_steam_sessions_started_at', 'steam_sessions', ['started_at'])


def downgrade() -> None:
    """Drop steam_sessions. Loses the play history — dev/rollback path only."""
    op.drop_index('ix_steam_sessions_started_at', table_name='steam_sessions')
    op.drop_index('ix_steam_sessions_app_id', table_name='steam_sessions')
    op.drop_index('ix_steam_sessions_id', table_name='steam_sessions')
    op.drop_table('steam_sessions')
