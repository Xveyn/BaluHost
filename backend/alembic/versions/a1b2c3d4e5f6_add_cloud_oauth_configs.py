"""add cloud_oauth_configs table

Revision ID: a1b2c3d4e5f6
Revises: ede15642ac0e
Create Date: 2026-02-16 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "ede15642ac0e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cloud_oauth_configs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("encrypted_client_id", sa.Text(), nullable=False),
        sa.Column("encrypted_client_secret", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("provider", "user_id", name="uq_cloud_oauth_provider_user"),
    )


def downgrade() -> None:
    op.drop_table("cloud_oauth_configs")
