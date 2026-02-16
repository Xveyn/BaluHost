"""rename configured_by_user_id to user_id and update unique constraint

Revision ID: f1x_cloud_oauth_per_user
Revises: a1b2c3d4e5f6
Create Date: 2026-02-16 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f1x_cloud_oauth_per_user"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "cloud_oauth_configs",
        "configured_by_user_id",
        new_column_name="user_id",
    )
    op.drop_constraint(
        "uq_cloud_oauth_configs_provider",
        "cloud_oauth_configs",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_cloud_oauth_provider_user",
        "cloud_oauth_configs",
        ["provider", "user_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_cloud_oauth_provider_user",
        "cloud_oauth_configs",
        type_="unique",
    )
    op.alter_column(
        "cloud_oauth_configs",
        "user_id",
        new_column_name="configured_by_user_id",
    )
    op.create_unique_constraint(
        "uq_cloud_oauth_configs_provider",
        "cloud_oauth_configs",
        ["provider"],
    )
