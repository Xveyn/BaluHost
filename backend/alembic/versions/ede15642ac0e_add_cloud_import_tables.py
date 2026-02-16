"""add cloud import tables

Revision ID: ede15642ac0e
Revises: 28cac30edbcb
Create Date: 2026-02-16 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ede15642ac0e"
down_revision: Union[str, None] = "28cac30edbcb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cloud_connections",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("rclone_remote_name", sa.String(100), nullable=True),
        sa.Column("encrypted_config", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "cloud_import_jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("connection_id", sa.Integer(), sa.ForeignKey("cloud_connections.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("source_path", sa.String(1000), nullable=False),
        sa.Column("destination_path", sa.String(1000), nullable=False),
        sa.Column("job_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("progress_bytes", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_bytes", sa.BigInteger(), nullable=True),
        sa.Column("files_transferred", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("files_total", sa.Integer(), nullable=True),
        sa.Column("current_file", sa.String(500), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("cloud_import_jobs")
    op.drop_table("cloud_connections")
