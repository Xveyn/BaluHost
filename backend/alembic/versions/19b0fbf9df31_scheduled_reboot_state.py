"""scheduled reboot state

Revision ID: 19b0fbf9df31
Revises: e7c2a9d41f86
Create Date: 2026-09-12 17:20:24.428665

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '19b0fbf9df31'
down_revision: Union[str, Sequence[str], None] = 'e7c2a9d41f86'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "scheduled_reboot_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("phase", sa.String(length=24), server_default="idle", nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_completed_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("woke_for_reboot", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("resuspend_wake_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_id", sa.Integer(), nullable=True),
        sa.Column("last_skip_reason", sa.String(length=64), nullable=True),
        sa.Column("warned_for_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("phase_entered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("scheduled_reboot_state")
