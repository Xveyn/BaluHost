"""GPU power management database models."""
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, String, DateTime, Integer, Float, Index, Text
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


class GpuPowerRuntimeState(Base):
    """
    Live runtime state of the GPU power manager, shared across Uvicorn workers.

    Singleton row (id=1). The primary worker writes; secondary workers read
    so endpoints like ``GET /api/gpu-power/status`` answer consistently
    regardless of which worker handles the request.
    """

    __tablename__ = "gpu_power_runtime_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    current_state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    detected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    vendor: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    has_write_permission: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_transition: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    capabilities_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    updated_by_pid: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return f"<GpuPowerRuntimeState(state='{self.current_state}', detected={self.detected})>"


class GpuPowerDemand(Base):
    """
    Active GPU power demand entry, shared across workers.

    Replaces the per-process ``GpuPowerManagerService._demands`` dict so any
    worker can register/inspect demands and the primary's monitor loop
    sees them on the next tick.
    """

    __tablename__ = "gpu_power_demands"

    source: Mapped[str] = mapped_column(String(100), primary_key=True)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    def __repr__(self) -> str:
        return f"<GpuPowerDemand(source='{self.source}')>"


class GpuPowerCommand(Base):
    """
    Cross-worker command queue for GPU power configuration changes.

    Secondary workers cannot drive the GPU backend directly; they enqueue
    a row here and poll for ``status != 'pending'``. The primary worker's
    command-poll loop picks up rows, executes them, and writes the result.

    Commands: ``set_config`` | ``register_demand`` | ``unregister_demand``.
    State transitions stay inside the primary's monitor tick.
    """

    __tablename__ = "gpu_power_commands"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    command: Mapped[str] = mapped_column(String(40), nullable=False)
    payload_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requested_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("idx_gpu_power_commands_status_requested", "status", "requested_at"),
    )

    def __repr__(self) -> str:
        return f"<GpuPowerCommand(id={self.id}, command='{self.command}', status='{self.status}')>"
