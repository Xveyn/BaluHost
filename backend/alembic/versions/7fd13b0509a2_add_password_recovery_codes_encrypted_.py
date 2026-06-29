"""add password_recovery_codes_encrypted to users

Revision ID: 7fd13b0509a2
Revises: b616a346ef70
Create Date: 2026-06-29 16:29:43.451101

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7fd13b0509a2'
down_revision: Union[str, Sequence[str], None] = 'b616a346ef70'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_recovery_codes_encrypted", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "password_recovery_codes_encrypted")
