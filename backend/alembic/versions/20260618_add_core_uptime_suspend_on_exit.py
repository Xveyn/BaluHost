"""add core_uptime_suspend_on_exit to sleep_config

Revision ID: cu_suspend_on_exit
Revises: sleep_presence_2026_06_11
Create Date: 2026-06-18

"""
from alembic import op
import sqlalchemy as sa

revision = "cu_suspend_on_exit"
down_revision = "sleep_presence_2026_06_11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sleep_config",
        sa.Column(
            "core_uptime_suspend_on_exit",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("sleep_config", "core_uptime_suspend_on_exit")
