"""add notification updated_at

Revision ID: 16ea14ef13bb
Revises: dcabe4cc2ebc
Create Date: 2026-08-01 22:15:35.968571

Backfills from COALESCE(deleted_at, created_at) rather than letting the
server_default stamp every existing row with "now". A fresh now() would claim
a change that never happened and make the first incremental sync after deploy
return the entire history.
"""
from alembic import op
import sqlalchemy as sa

revision = "16ea14ef13bb"
down_revision = "dcabe4cc2ebc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("notifications") as batch_op:
        batch_op.add_column(
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True)
        )

    op.execute(
        "UPDATE notifications SET updated_at = COALESCE(deleted_at, created_at)"
    )

    with op.batch_alter_table("notifications") as batch_op:
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        )
        batch_op.create_index("ix_notifications_updated_at", ["updated_at"])


def downgrade() -> None:
    with op.batch_alter_table("notifications") as batch_op:
        batch_op.drop_index("ix_notifications_updated_at")
        batch_op.drop_column("updated_at")
