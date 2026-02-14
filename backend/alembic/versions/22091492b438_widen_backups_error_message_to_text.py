"""widen backups error_message to text

Revision ID: 22091492b438
Revises: 020_checksum
Create Date: 2026-02-11 21:06:30.407378

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '22091492b438'
down_revision: Union[str, Sequence[str], None] = '020_checksum'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Widen backups.error_message from VARCHAR(1000) to TEXT."""
    op.alter_column('backups', 'error_message',
               existing_type=sa.VARCHAR(length=1000),
               type_=sa.Text(),
               existing_nullable=True)


def downgrade() -> None:
    """Revert backups.error_message back to VARCHAR(1000)."""
    op.alter_column('backups', 'error_message',
               existing_type=sa.Text(),
               type_=sa.VARCHAR(length=1000),
               existing_nullable=True)
