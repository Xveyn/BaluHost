"""add nfs_exports table

Revision ID: c7f2a1b4d8e9
Revises: 45292ba19a35
Create Date: 2026-06-07
"""
from alembic import op
import sqlalchemy as sa

revision = "c7f2a1b4d8e9"
down_revision = "45292ba19a35"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "nfs_exports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("path", sa.String(length=1000), nullable=False),
        sa.Column("clients", sa.String(length=255), nullable=False),
        sa.Column("read_only", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("root_squash", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("path", name="uq_nfs_exports_path"),
    )


def downgrade() -> None:
    op.drop_table("nfs_exports")
