"""fan overhaul: sensor labels, composite sensors, fan config extensions

Revision ID: 37ae61688702
Revises: 87f057d69ce4
Create Date: 2026-05-24 15:02:30.286602

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '37ae61688702'
down_revision: Union[str, Sequence[str], None] = '87f057d69ce4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "temp_sensor_labels",
        sa.Column("sensor_id", sa.String(length=120), primary_key=True),
        sa.Column("custom_label", sa.String(length=100), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "composite_temp_sensors",
        sa.Column("id", sa.String(length=40), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("function", sa.String(length=10), nullable=False),
        sa.Column("source_ids_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    with op.batch_alter_table("fan_configs") as batch:
        batch.add_column(sa.Column("curve_type", sa.String(length=20), nullable=False, server_default="graph"))
        batch.add_column(sa.Column("flat_pwm_percent", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("target_temp_celsius", sa.Float(), nullable=True))
        batch.add_column(sa.Column("target_pwm_percent", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("mix_curve_a_id", sa.Integer(), sa.ForeignKey("fan_curve_profiles.id", ondelete="SET NULL"), nullable=True))
        batch.add_column(sa.Column("mix_curve_b_id", sa.Integer(), sa.ForeignKey("fan_curve_profiles.id", ondelete="SET NULL"), nullable=True))
        batch.add_column(sa.Column("mix_function", sa.String(length=10), nullable=True))
        batch.add_column(sa.Column("sync_fan_id", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("start_pwm_percent", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("stop_below_temp_celsius", sa.Float(), nullable=True))
        batch.add_column(sa.Column("response_time_seconds", sa.Float(), nullable=False, server_default="0.0"))
        batch.add_column(sa.Column("pwm_steps", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("fan_configs") as batch:
        for col in (
            "pwm_steps", "response_time_seconds", "stop_below_temp_celsius",
            "start_pwm_percent", "sync_fan_id", "mix_function",
            "mix_curve_b_id", "mix_curve_a_id", "target_pwm_percent",
            "target_temp_celsius", "flat_pwm_percent", "curve_type",
        ):
            batch.drop_column(col)

    op.drop_table("composite_temp_sensors")
    op.drop_table("temp_sensor_labels")
