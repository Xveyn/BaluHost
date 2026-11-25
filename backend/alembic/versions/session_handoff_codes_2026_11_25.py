"""session handoff codes (#847)

Revision ID: d4b7e2c9a610
Revises: c9f2a6d3e581
Create Date: 2026-11-25 00:00:00.000000

Einmal-Codes fuer den Session-Handoff vom Tray in die Web-UI. Gespeichert
wird nur der SHA-256 des Codes.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4b7e2c9a610'
down_revision: Union[str, Sequence[str], None] = 'c9f2a6d3e581'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'session_handoff_codes',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False,
        ),
        sa.Column('created_ip', sa.String(length=45), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_session_handoff_codes_token_hash', 'session_handoff_codes', ['token_hash'], unique=True
    )
    op.create_index('ix_session_handoff_codes_user_id', 'session_handoff_codes', ['user_id'])
    op.create_index('ix_session_handoff_codes_expires_at', 'session_handoff_codes', ['expires_at'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_session_handoff_codes_expires_at', table_name='session_handoff_codes')
    op.drop_index('ix_session_handoff_codes_user_id', table_name='session_handoff_codes')
    op.drop_index('ix_session_handoff_codes_token_hash', table_name='session_handoff_codes')
    op.drop_table('session_handoff_codes')
