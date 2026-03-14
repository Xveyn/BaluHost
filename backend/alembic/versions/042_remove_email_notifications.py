"""remove email_enabled from notification_preferences

Revision ID: 042_remove_email_notif
Revises: 041_add_file_activities
Create Date: 2026-03-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "042_remove_email_notif"
down_revision: Union[str, None] = "041_add_file_activities"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("notification_preferences", "email_enabled")


def downgrade() -> None:
    op.add_column(
        "notification_preferences",
        sa.Column("email_enabled", sa.Boolean(), nullable=False, server_default="1"),
    )
