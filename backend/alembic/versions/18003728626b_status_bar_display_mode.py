"""add display_mode to status_bar_pill_config

Revision ID: 18003728626b
Revises: 9c4dcf5d487b
Create Date: 2026-05-31

Additive column for the per-pill display mode (desktop pill). Safe for live
PostgreSQL: NOT NULL with a server default so existing rows backfill to 'always'.
"""
from alembic import op
import sqlalchemy as sa

revision = "18003728626b"
down_revision = "9c4dcf5d487b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "status_bar_pill_config",
        sa.Column("display_mode", sa.String(length=8), nullable=False, server_default="always"),
    )


def downgrade() -> None:
    op.drop_column("status_bar_pill_config", "display_mode")
