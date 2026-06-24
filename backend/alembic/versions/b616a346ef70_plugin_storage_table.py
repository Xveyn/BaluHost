"""plugin_storage table

Revision ID: b616a346ef70
Revises: 1ab0b6db5b1c
Create Date: 2026-06-24 13:05:17.933318

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b616a346ef70'
down_revision: Union[str, Sequence[str], None] = '1ab0b6db5b1c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('plugin_storage',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('plugin_name', sa.String(length=100), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=200), nullable=False),
    sa.Column('value', sa.JSON(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('plugin_name', 'user_id', 'key', name='uq_plugin_storage_scope')
    )
    op.create_index(op.f('ix_plugin_storage_id'), 'plugin_storage', ['id'], unique=False)
    op.create_index(op.f('ix_plugin_storage_plugin_name'), 'plugin_storage', ['plugin_name'], unique=False)
    op.create_index(op.f('ix_plugin_storage_user_id'), 'plugin_storage', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_plugin_storage_user_id'), table_name='plugin_storage')
    op.drop_index(op.f('ix_plugin_storage_plugin_name'), table_name='plugin_storage')
    op.drop_index(op.f('ix_plugin_storage_id'), table_name='plugin_storage')
    op.drop_table('plugin_storage')
