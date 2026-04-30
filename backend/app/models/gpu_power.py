"""GPU power management database models."""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Integer, Float, Index, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class GpuPowerLog(Base):
    """Log of GPU power state transitions."""

    __tablename__ = "gpu_power_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    state: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    previous_state: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    power_watts_at_transition: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    __table_args__ = (
        Index("idx_gpu_power_log_state_ts", "state", "timestamp"),
    )

    def __repr__(self) -> str:
        return f"<GpuPowerLog(id={self.id}, state='{self.state}', reason='{self.reason}')>"


class GpuPowerConfigDb(Base):
    """Singleton config row for GPU power management. JSON-serialized GpuPowerConfig.

    A separate row-as-JSON keeps the schema flexible for per-state nested overrides
    without a wide column set; matches the `power_dynamic_mode_config` precedent in spirit.
    """

    __tablename__ = "gpu_power_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # always 1
    config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<GpuPowerConfigDb(id={self.id})>"
