"""Add fritzbox_config table

Revision ID: 046_fritzbox_config
Revises: 045_drop_legacy_tapo
Create Date: 2026-03-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '046_fritzbox_config'
down_revision: Union[str, Sequence[str], None] = '045_drop_legacy_tapo'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create fritzbox_config singleton table."""
    op.create_table(
        'fritzbox_config',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('host', sa.String(length=255), nullable=False, server_default='192.168.178.1'),
        sa.Column('port', sa.Integer(), nullable=False, server_default='49000'),
        sa.Column('username', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('password_encrypted', sa.Text(), nullable=False, server_default=''),
        sa.Column('nas_mac_address', sa.String(length=17), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_fritzbox_config_id', 'fritzbox_config', ['id'])
    # Insert singleton row
    op.execute("INSERT INTO fritzbox_config (id) VALUES (1)")


def downgrade() -> None:
    """Drop fritzbox_config table."""
    op.drop_index('ix_fritzbox_config_id', table_name='fritzbox_config')
    op.drop_table('fritzbox_config')
