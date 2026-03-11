"""add file_activities table

Revision ID: 041_add_file_activities
Revises: c66c44a221fd
Create Date: 2026-03-11 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "041_add_file_activities"
down_revision: Union[str, Sequence[str], None] = "c66c44a221fd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create file_activities table with indexes."""
    op.create_table(
        "file_activities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.String(255), nullable=True),
        sa.Column("action_type", sa.String(50), nullable=False),
        sa.Column("file_path", sa.String(1000), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("is_directory", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("mime_type", sa.String(255), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="server"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
    )

    # Single-column indexes
    op.create_index("ix_file_activities_id", "file_activities", ["id"])
    op.create_index("ix_file_activities_action_type", "file_activities", ["action_type"])
    op.create_index("ix_file_activities_file_path", "file_activities", ["file_path"])

    # Composite indexes for common query patterns
    op.create_index("idx_fa_user_created", "file_activities", ["user_id", "created_at"])
    op.create_index("idx_fa_action_created", "file_activities", ["action_type", "created_at"])
    op.create_index(
        "idx_fa_user_path_action",
        "file_activities",
        ["user_id", "file_path", "action_type"],
    )


def downgrade() -> None:
    """Drop file_activities table."""
    op.drop_index("idx_fa_user_path_action", table_name="file_activities")
    op.drop_index("idx_fa_action_created", table_name="file_activities")
    op.drop_index("idx_fa_user_created", table_name="file_activities")
    op.drop_index("ix_file_activities_file_path", table_name="file_activities")
    op.drop_index("ix_file_activities_action_type", table_name="file_activities")
    op.drop_index("ix_file_activities_id", table_name="file_activities")
    op.drop_table("file_activities")
