"""add version_history table

Revision ID: 040_add_version_history
Revises: 039_encrypt_vpn_keys
Create Date: 2026-03-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "040_add_version_history"
down_revision: Union[str, None] = "039_encrypt_vpn_keys"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "version_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("version", sa.String(50), nullable=False, index=True),
        sa.Column("git_commit", sa.String(40), nullable=False),
        sa.Column("git_commit_short", sa.String(10), nullable=False),
        sa.Column("git_branch", sa.String(100), nullable=True),
        sa.Column("python_version", sa.String(20), nullable=True),
        sa.Column(
            "first_seen",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_seen",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "times_started",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.UniqueConstraint("version", "git_commit", name="uq_version_commit"),
    )


def downgrade() -> None:
    op.drop_table("version_history")
