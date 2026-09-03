"""auth_policy: admin-configurable session limits

Revision ID: c4b18e9a2f37
Revises: a7d3c9f18e42
Create Date: 2026-09-03

Additive only. The server_defaults reproduce the values that were hardcoded
before (frontend hook: 4 min + 60 s; config.py: 15 min), so an existing
installation behaves exactly as it did until an admin changes something.
"""
from alembic import op
import sqlalchemy as sa

revision = "c4b18e9a2f37"
down_revision = "a7d3c9f18e42"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the three session-limit columns to auth_policy."""
    op.add_column(
        "auth_policy",
        sa.Column("idle_timeout_minutes", sa.Integer(), nullable=False, server_default="4"),
    )
    op.add_column(
        "auth_policy",
        sa.Column("idle_warning_seconds", sa.Integer(), nullable=False, server_default="60"),
    )
    op.add_column(
        "auth_policy",
        sa.Column("access_token_minutes", sa.Integer(), nullable=False, server_default="15"),
    )


def downgrade() -> None:
    """Drop the session-limit columns."""
    op.drop_column("auth_policy", "access_token_minutes")
    op.drop_column("auth_policy", "idle_warning_seconds")
    op.drop_column("auth_policy", "idle_timeout_minutes")
