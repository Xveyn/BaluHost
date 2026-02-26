"""add vcl_mode column and vcl_file_tracking table

Revision ID: 035_add_vcl_mode_and_tracking
Revises: 034_rename_beta_to_unstable
Create Date: 2026-02-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "035_add_vcl_mode_and_tracking"
down_revision: Union[str, None] = "034_rename_beta_to_unstable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add vcl_mode column to vcl_settings
    op.add_column(
        "vcl_settings",
        sa.Column(
            "vcl_mode",
            sa.String(20),
            nullable=False,
            server_default="automatic",
        ),
    )

    # Create vcl_file_tracking table
    op.create_table(
        "vcl_file_tracking",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "file_id",
            sa.Integer(),
            sa.ForeignKey("file_metadata.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("path_pattern", sa.String(1000), nullable=True),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("is_directory", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index("ix_vcl_file_tracking_user_id", "vcl_file_tracking", ["user_id"])
    op.create_index("idx_vcl_tracking_user_action", "vcl_file_tracking", ["user_id", "action"])
    op.create_unique_constraint("uq_vcl_tracking_user_file", "vcl_file_tracking", ["user_id", "file_id"])


def downgrade() -> None:
    op.drop_table("vcl_file_tracking")
    op.drop_column("vcl_settings", "vcl_mode")
