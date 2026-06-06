"""add pin columns and auth_policy

Revision ID: 45292ba19a35
Revises: 73861c57ef63
Create Date: 2026-06-06 17:58:35.112596

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '45292ba19a35'
down_revision: Union[str, Sequence[str], None] = '73861c57ef63'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column("users", sa.Column("pin_hash", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("pin_grace_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("pin_failed_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("pin_locked_until", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "auth_policy",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pin_login_enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("pin_grace_window_seconds", sa.Integer(), nullable=False, server_default="86400"),
    )


def downgrade():
    op.drop_table("auth_policy")
    op.drop_column("users", "pin_locked_until")
    op.drop_column("users", "pin_failed_attempts")
    op.drop_column("users", "pin_grace_until")
    op.drop_column("users", "pin_hash")
