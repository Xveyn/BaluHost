"""gpu fan acoustics config

Revision ID: d1e5a83f47c2
Revises: c9a4e77b2d10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d1e5a83f47c2"
down_revision: Union[str, Sequence[str], None] = "c9a4e77b2d10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gpu_fan_acoustics_config",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_by_pid", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("gpu_fan_acoustics_config")
