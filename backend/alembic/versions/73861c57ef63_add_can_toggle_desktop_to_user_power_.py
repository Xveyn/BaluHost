"""add can_toggle_desktop to user_power_permissions

Revision ID: 73861c57ef63
Revises: 88a45a963ed9
Create Date: 2026-06-04 14:21:28.996955

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '73861c57ef63'
down_revision: Union[str, Sequence[str], None] = '88a45a963ed9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_power_permissions",
        sa.Column("can_toggle_desktop", sa.Boolean(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    with op.batch_alter_table("user_power_permissions") as batch_op:
        batch_op.drop_column("can_toggle_desktop")
