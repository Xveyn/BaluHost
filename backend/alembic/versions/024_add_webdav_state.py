"""add webdav_state table

Revision ID: 024_webdav_state
Revises: 023_dynamic_mode
Create Date: 2026-02-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '024_webdav_state'
down_revision: Union[str, Sequence[str], None] = '023_dynamic_mode'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'webdav_state',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('is_running', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('port', sa.Integer(), nullable=False, server_default='8080'),
        sa.Column('ssl_enabled', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('last_heartbeat', sa.DateTime(timezone=True), nullable=True),
        sa.Column('worker_pid', sa.Integer(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.String(1000), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('webdav_state')
