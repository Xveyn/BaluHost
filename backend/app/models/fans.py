"""
Database models for fan control.
"""
from sqlalchemy import Integer, String, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from typing import Optional

from app.models.base import Base


class FanCurveProfile(Base):
    """Named, reusable fan curve profile."""
    __tablename__ = "fan_curve_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    curve_json: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array of {temp, pwm}
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    def __repr__(self) -> str:
        return f"<FanCurveProfile(name='{self.name}', is_system={self.is_system})>"


class FanScheduleEntry(Base):
    """Time-based fan schedule entry for scheduled mode."""
    __tablename__ = "fan_schedule_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    fan_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    start_time: Mapped[str] = mapped_column(String(5), nullable=False)  # "HH:MM"
    end_time: Mapped[str] = mapped_column(String(5), nullable=False)  # "HH:MM"
    curve_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array of {temp, pwm}
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    profile_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("fan_curve_profiles.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    profile: Mapped[Optional["FanCurveProfile"]] = relationship("FanCurveProfile", lazy="joined")

    def __repr__(self) -> str:
        return f"<FanScheduleEntry(fan_id='{self.fan_id}', name='{self.name}', {self.start_time}-{self.end_time})>"


class FanConfig(Base):
    """Fan configuration storage."""
    __tablename__ = "fan_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    fan_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), default="auto", nullable=False)  # auto|manual|emergency
    curve_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array of {temp, pwm} points
    min_pwm_percent: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    max_pwm_percent: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    emergency_temp_celsius: Mapped[float] = mapped_column(Float, default=85.0, nullable=False)
    temp_sensor_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    # Herkunft der Zeile vor der Umstellung auf stabile Kennungen (#532).
    # Reiner Nachweis: erlaubt, eine Fehlzuordnung nachtraeglich zu erkennen.
    legacy_fan_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # Der pwm_enable-Wert, auf den beim Dienst-Ende zurueckgeschaltet wird
    # (#534). Wird ausschliesslich aus einer eigenen Beobachtung gefuellt --
    # ein Wert >= 2, den der Scan vor dem ersten Write gelesen hat. NULL heisst:
    # noch nie eine Automatik gesehen, also keine Rueckgabe.
    pwm_enable_restore: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Der Vorzustand der AMD-GPU vor dem Manual-Mode (#411). Lag frueher in
    # einem modulweiten Dict in routes/fans.py und war damit pro Uvicorn-Worker
    # getrennt: schaltete ein anderer Worker ab als eingeschaltet hatte, wurde
    # ein GERATENER Vorzustand zurueckgeschrieben. NULL heisst: kein
    # Manual-Mode aktiv, nichts zurueckzunehmen.
    gpu_manual_prev_level: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    gpu_manual_prev_pwm_enable: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    hysteresis_celsius: Mapped[float] = mapped_column(Float, default=3.0, nullable=False)
    # --- Curve type & params ---
    curve_type: Mapped[str] = mapped_column(String(20), default="graph", nullable=False)
    flat_pwm_percent: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    target_temp_celsius: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_pwm_percent: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    mix_curve_a_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("fan_curve_profiles.id", ondelete="SET NULL"), nullable=True
    )
    mix_curve_b_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("fan_curve_profiles.id", ondelete="SET NULL"), nullable=True
    )
    mix_function: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    sync_fan_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # --- Advanced tuning ---
    start_pwm_percent: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    stop_below_temp_celsius: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    response_time_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    pwm_steps: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    def __repr__(self) -> str:
        return f"<FanConfig(fan_id='{self.fan_id}', name='{self.name}', mode='{self.mode}')>"


class FanSample(Base):
    """Historical fan performance samples."""
    __tablename__ = "fan_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )
    fan_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    pwm_percent: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 0-100
    rpm: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    temperature_celsius: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)  # auto|manual|emergency

    def __repr__(self) -> str:
        return f"<FanSample(fan_id='{self.fan_id}', rpm={self.rpm}, pwm={self.pwm_percent}%)>"


class TempSensorLabel(Base):
    """User-supplied custom label for a temperature sensor."""
    __tablename__ = "temp_sensor_labels"

    sensor_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    custom_label: Mapped[str] = mapped_column(String(100), nullable=False)
    legacy_sensor_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<TempSensorLabel({self.sensor_id}='{self.custom_label}')>"


class CompositeTempSensor(Base):
    """Composite sensor combining N sources via max/min/avg."""
    __tablename__ = "composite_temp_sensors"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    function: Mapped[str] = mapped_column(String(10), nullable=False)  # "max" | "min" | "avg"
    source_ids_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<CompositeTempSensor(id={self.id}, function={self.function})>"


class FanRuntimeState(Base):
    """
    Live runtime state of fan control, shared across Uvicorn workers.

    Singleton row (id=1). The primary worker writes; secondary workers read,
    so ``GET /api/fans/permissions`` answers the same regardless of which
    worker handles the request.

    Ohne diese Zeile war ``_has_write_permission`` ein reines Instanz-Attribut:
    vier Worker, vier Wahrheiten. Geheilt hat sich nur, wer schreibt -- also
    der Primary ueber den Regelkreis. Die drei Follower blieben auf ihrem
    Startwert stehen, und der 5-Sekunden-Poll des Frontends landete
    abwechselnd auf einem geheilten und drei ungeheilten Workern (#552).

    Gleiches Muster wie ``PowerRuntimeState`` und ``GpuPowerRuntimeState``;
    letztere fuehrt dieselbe Spalte fuer denselben Zweck.
    """

    __tablename__ = "fan_runtime_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    has_write_permission: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    updated_by_pid: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return f"<FanRuntimeState(has_write_permission={self.has_write_permission})>"


class GpuFanAcousticsConfigDb(Base):
    """Singleton-Zeile (id=1) mit der GPU-Akustik-Konfiguration als JSON.

    Gleiches Muster wie GpuPowerConfigDb. Eigene Tabelle statt einer
    Erweiterung jener: die Akustikwerte gehoeren nicht in die
    Power-Konfiguration (#516).

    JSON statt vier Spalten, damit ein fuenfter Regler -- etwa
    fan_zero_rpm_enable ab Kernel 6.13 -- eine Schema-Aenderung ohne
    Migration bleibt.
    """

    __tablename__ = "gpu_fan_acoustics_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    config_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    updated_by_pid: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return f"<GpuFanAcousticsConfigDb(id={self.id})>"
