"""notification trash retention

Revision ID: 87f057d69ce4
Revises: d45e605bfc4d
Create Date: 2026-05-11 22:55:03.462093

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '87f057d69ce4'
down_revision: Union[str, Sequence[str], None] = 'd45e605bfc4d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("notifications") as batch_op:
        batch_op.add_column(
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_index("ix_notifications_deleted_at", ["deleted_at"])

    # Backfill: existing soft-dismissed rows start their retention now.
    op.execute(
        "UPDATE notifications SET deleted_at = CURRENT_TIMESTAMP "
        "WHERE is_dismissed"
    )

    with op.batch_alter_table("notifications") as batch_op:
        batch_op.drop_column("is_dismissed")

    with op.batch_alter_table("notification_preferences") as batch_op:
        batch_op.add_column(
            sa.Column(
                "trash_retention_days",
                sa.Integer(),
                nullable=False,
                server_default="7",
            )
        )
        batch_op.create_check_constraint(
            "ck_trash_retention_1_7",
            "trash_retention_days BETWEEN 1 AND 7",
        )


def downgrade() -> None:
    with op.batch_alter_table("notifications") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_dismissed",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
    op.execute(
        "UPDATE notifications SET is_dismissed = "
        "(CASE WHEN deleted_at IS NOT NULL THEN 1 ELSE 0 END)"
    )
    with op.batch_alter_table("notifications") as batch_op:
        batch_op.drop_index("ix_notifications_deleted_at")
        batch_op.drop_column("deleted_at")

    with op.batch_alter_table("notification_preferences") as batch_op:
        batch_op.drop_constraint("ck_trash_retention_1_7", type_="check")
        batch_op.drop_column("trash_retention_days")
