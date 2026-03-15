"""Add uptime_samples table

Revision ID: 043_add_uptime_samples
Revises: 042_remove_email_notif
Create Date: 2026-03-15
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "043_add_uptime_samples"
down_revision = "042_remove_email_notif"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "uptime_samples",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("server_uptime_seconds", sa.BigInteger(), nullable=False),
        sa.Column("system_uptime_seconds", sa.BigInteger(), nullable=False),
        sa.Column("server_start_time", sa.DateTime(), nullable=False),
        sa.Column("system_boot_time", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_uptime_samples_id"), "uptime_samples", ["id"], unique=False)
    op.create_index(op.f("ix_uptime_samples_timestamp"), "uptime_samples", ["timestamp"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_uptime_samples_timestamp"), table_name="uptime_samples")
    op.drop_index(op.f("ix_uptime_samples_id"), table_name="uptime_samples")
    op.drop_table("uptime_samples")
