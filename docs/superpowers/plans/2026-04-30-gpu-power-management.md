# GPU Power Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a vendor-abstracted GPU power management subsystem that puts a discrete GPU into low-power states (`active` → `standby` → `deep_idle`) when no display output and no compute load are present, with a public demand API and a deep-idle event hook for plugins (e.g., Balu_Code/Ollama).

**Architecture:** Mirror the existing `PowerManagerService` pattern. New `services/power/gpu/` module with `GpuPowerManagerService` singleton, vendor-specific backends (AMD sysfs, NVIDIA nvidia-smi, dev mock), display detector, async monitor loop. New schema/model/route/UI layer. Plugin event hook so the GPU module stays plugin-agnostic. Per-vendor, per-state config persisted in DB with capabilities endpoint for UI bounds validation.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 typed style, Pydantic v2, pytest, Alembic, React + TypeScript, Tailwind, axios.

**Spec:** `docs/superpowers/specs/2026-04-30-gpu-power-management-design.md`

---

## File Structure

### New backend files
- `backend/app/services/power/gpu/__init__.py` (empty marker)
- `backend/app/services/power/gpu/protocol.py` — `GpuPowerBackend` ABC, `GpuPowerState` re-export
- `backend/app/services/power/gpu/display_detector.py` — `get_active_display_count()`
- `backend/app/services/power/gpu/dev_backend.py` — in-memory mock backend
- `backend/app/services/power/gpu/amd_backend.py` — sysfs writes for AMD
- `backend/app/services/power/gpu/nvidia_backend.py` — `nvidia-smi` wrapper
- `backend/app/services/power/gpu/events.py` — deep-idle hook registry
- `backend/app/services/power/gpu/config_store.py` — DB persistence
- `backend/app/services/power/gpu/manager.py` — `GpuPowerManagerService` singleton
- `backend/app/schemas/gpu_power.py` — Pydantic models
- `backend/app/models/gpu_power.py` — SQLAlchemy `GpuPowerLog`, `GpuPowerConfigDb`
- `backend/app/api/routes/gpu_power.py` — FastAPI routes
- `backend/alembic/versions/<auto>_add_gpu_power_tables.py` — migration

### New backend tests
- `backend/tests/services/power/gpu/__init__.py`
- `backend/tests/services/power/gpu/test_display_detector.py`
- `backend/tests/services/power/gpu/test_dev_backend.py`
- `backend/tests/services/power/gpu/test_amd_backend.py`
- `backend/tests/services/power/gpu/test_nvidia_backend.py`
- `backend/tests/services/power/gpu/test_event_hook.py`
- `backend/tests/services/power/gpu/test_state_machine.py`
- `backend/tests/services/power/gpu/test_demand_api.py`
- `backend/tests/services/power/gpu/test_lifespan.py`
- `backend/tests/api/test_gpu_power_routes.py`

### Modified backend files
- `backend/app/models/__init__.py` — export new models
- `backend/app/api/routes/__init__.py` — register new router
- `backend/app/core/lifespan.py` — start/stop service
- `backend/app/core/rate_limiter.py` — add `gpu_power` limit
- `backend/app/core/config.py` — add `gpu_power_management_enabled` setting

### New frontend files
- `client/src/api/gpuPower.ts` — typed API client
- `client/src/components/power/GpuPowerCard.tsx` — main card
- `client/src/components/power/GpuPowerThresholds.tsx` — threshold form
- `client/src/components/power/GpuPowerHardware.tsx` — vendor-specific overrides
- `client/src/types/gpuPower.ts` — types

### Modified frontend files
- `client/src/pages/PowerManagement.tsx` — render `GpuPowerCard`

---

## Conventions Reminders

- Per `backend/.../coding-style.md`: async/await for I/O, type hints required, services in `services/`, pytest async with mocks.
- Per `models/CLAUDE.md`: SQLAlchemy 2.0 `Mapped[T]` + `mapped_column()`, `DateTime(timezone=True)`, register in `models/__init__.py`.
- Per `schemas/CLAUDE.md`: `BaseModel`, `field_validator` (not v1 `validator`), suffix `Request`/`Response`, separate request/response schemas.
- Per `api/CLAUDE.md`: routes in `routes/`, registered in `routes/__init__.py`, auth via `Depends(deps.get_current_user)` / `get_current_admin`, rate limits via `@limiter.limit(get_limit("..."))`.
- Per `security-agent.md`: never `shell=True`, list-args only for subprocess, ORM-only DB access, audit-log security-relevant actions.
- Per `production.md` git workflow: feature branches off `development`, commit per task.

---

## Task 1: Schemas

**Files:**
- Create: `backend/app/schemas/gpu_power.py`
- Test: `backend/tests/services/power/gpu/test_schemas.py` (new file in this task)

- [ ] **Step 1: Create test file with failing schema tests**

Create `backend/tests/services/power/gpu/__init__.py` (empty file).

Then create `backend/tests/services/power/gpu/test_schemas.py`:

```python
import pytest
from pydantic import ValidationError
from app.schemas.gpu_power import (
    GpuPowerState,
    AmdProfileMode,
    AmdStateConfig,
    NvidiaStateConfig,
    GpuPowerConfig,
    GpuPowerDemandInfo,
    GpuPowerStatus,
    GpuPowerCapabilities,
)


def test_gpu_power_state_values():
    assert GpuPowerState.ACTIVE.value == "active"
    assert GpuPowerState.STANDBY.value == "standby"
    assert GpuPowerState.DEEP_IDLE.value == "deep_idle"


def test_gpu_power_config_defaults():
    config = GpuPowerConfig()
    assert config.enabled is False
    assert config.idle_window_seconds == 30
    assert config.deep_idle_extra_seconds == 120
    assert config.deep_idle_grace_seconds == 5
    assert config.usage_threshold_percent == 5.0
    assert config.monitor_interval_seconds == 5
    assert config.amd_active.performance_level == "auto"
    assert config.amd_standby.profile_mode == AmdProfileMode.POWER_SAVING
    assert config.amd_deep_idle.performance_level == "low"


def test_gpu_power_config_idle_window_bounds():
    with pytest.raises(ValidationError):
        GpuPowerConfig(idle_window_seconds=5)  # below ge=10
    with pytest.raises(ValidationError):
        GpuPowerConfig(idle_window_seconds=601)  # above le=600


def test_gpu_power_config_deep_idle_extra_bounds():
    with pytest.raises(ValidationError):
        GpuPowerConfig(deep_idle_extra_seconds=29)
    with pytest.raises(ValidationError):
        GpuPowerConfig(deep_idle_extra_seconds=3601)


def test_gpu_power_config_usage_bounds():
    with pytest.raises(ValidationError):
        GpuPowerConfig(usage_threshold_percent=-1.0)
    with pytest.raises(ValidationError):
        GpuPowerConfig(usage_threshold_percent=51.0)


def test_amd_state_config_optional_fields():
    cfg = AmdStateConfig()
    assert cfg.performance_level is None
    assert cfg.profile_mode is None


def test_nvidia_state_config_clock_validation():
    cfg = NvidiaStateConfig(min_clock_mhz=210, max_clock_mhz=1500, power_limit_watts=100)
    assert cfg.min_clock_mhz == 210
    assert cfg.max_clock_mhz == 1500
    assert cfg.power_limit_watts == 100


def test_gpu_power_demand_info_required_fields():
    from datetime import datetime, timezone
    info = GpuPowerDemandInfo(source="test", registered_at=datetime.now(timezone.utc))
    assert info.source == "test"
    assert info.expires_at is None


def test_gpu_power_capabilities_defaults():
    caps = GpuPowerCapabilities(vendor=None)
    assert caps.amd_performance_levels == []
    assert caps.amd_profile_modes == []
    assert caps.nvidia_min_clock_mhz is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
python -m pytest tests/services/power/gpu/test_schemas.py -v
```

Expected: FAIL with `ImportError: cannot import name 'GpuPowerState' from 'app.schemas.gpu_power'` (module does not exist).

- [ ] **Step 3: Implement schemas**

Create `backend/app/schemas/gpu_power.py`:

```python
"""Pydantic schemas for GPU power management."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class GpuPowerState(str, Enum):
    """Three-state GPU power machine."""
    ACTIVE = "active"
    STANDBY = "standby"
    DEEP_IDLE = "deep_idle"


class AmdProfileMode(str, Enum):
    """Canonical names parsed from `pp_power_profile_mode`. Index resolved at apply time."""
    BOOTUP_DEFAULT = "BOOTUP_DEFAULT"
    POWER_SAVING = "POWER_SAVING"
    VIDEO = "VIDEO"
    VR = "VR"
    COMPUTE = "COMPUTE"
    CUSTOM = "CUSTOM"
    FULL_SCREEN_3D = "3D_FULL_SCREEN"


class AmdStateConfig(BaseModel):
    """Per-state AMD overrides. None = use built-in default for that state."""
    performance_level: Optional[str] = Field(
        default=None,
        description="auto | low | high | manual | profile_standard | profile_min_sclk | profile_min_mclk | profile_peak"
    )
    profile_mode: Optional[AmdProfileMode] = Field(
        default=None,
        description="pp_power_profile_mode name; None = don't touch"
    )


class NvidiaStateConfig(BaseModel):
    """Per-state NVIDIA overrides."""
    min_clock_mhz: Optional[int] = Field(default=None, ge=0)
    max_clock_mhz: Optional[int] = Field(default=None, ge=0)
    power_limit_watts: Optional[int] = Field(default=None, ge=0)


class GpuPowerConfig(BaseModel):
    """Full configuration."""
    enabled: bool = False

    idle_window_seconds: int = Field(default=30, ge=10, le=600)
    deep_idle_extra_seconds: int = Field(default=120, ge=30, le=3600)
    deep_idle_grace_seconds: int = Field(default=5, ge=0, le=30)
    usage_threshold_percent: float = Field(default=5.0, ge=0.0, le=50.0)
    monitor_interval_seconds: int = Field(default=5, ge=1, le=60)

    amd_active: AmdStateConfig = Field(
        default_factory=lambda: AmdStateConfig(performance_level="auto")
    )
    amd_standby: AmdStateConfig = Field(
        default_factory=lambda: AmdStateConfig(
            performance_level="auto",
            profile_mode=AmdProfileMode.POWER_SAVING,
        )
    )
    amd_deep_idle: AmdStateConfig = Field(
        default_factory=lambda: AmdStateConfig(
            performance_level="low",
            profile_mode=AmdProfileMode.POWER_SAVING,
        )
    )

    nvidia_active: NvidiaStateConfig = Field(default_factory=NvidiaStateConfig)
    nvidia_standby: NvidiaStateConfig = Field(default_factory=NvidiaStateConfig)
    nvidia_deep_idle: NvidiaStateConfig = Field(default_factory=NvidiaStateConfig)


class GpuPowerDemandInfo(BaseModel):
    source: str
    registered_at: datetime
    expires_at: Optional[datetime] = None
    description: Optional[str] = None


class RegisterGpuDemandRequest(BaseModel):
    source: str = Field(..., min_length=1, max_length=128)
    timeout_seconds: Optional[int] = Field(default=None, ge=1, le=86400)
    description: Optional[str] = Field(default=None, max_length=500)


class GpuPowerStatus(BaseModel):
    enabled: bool
    detected: bool
    vendor: Optional[str]
    current_state: GpuPowerState
    last_transition: Optional[datetime] = None
    last_reason: Optional[str] = None
    active_demands: List[GpuPowerDemandInfo] = Field(default_factory=list)
    has_write_permission: bool
    estimated_power_watts: Optional[float] = None
    display_count: int = 0
    usage_percent: Optional[float] = None


class GpuPowerCapabilities(BaseModel):
    vendor: Optional[str]
    amd_performance_levels: List[str] = Field(default_factory=list)
    amd_profile_modes: List[str] = Field(default_factory=list)
    nvidia_min_clock_mhz: Optional[int] = None
    nvidia_max_clock_mhz: Optional[int] = None
    nvidia_min_power_watts: Optional[int] = None
    nvidia_max_power_watts: Optional[int] = None
    nvidia_default_power_watts: Optional[int] = None


class GpuPowerHistoryEntry(BaseModel):
    timestamp: datetime
    state: GpuPowerState
    previous_state: Optional[GpuPowerState] = None
    reason: str
    source: Optional[str] = None
    power_watts_at_transition: Optional[float] = None


class GpuPowerHistoryResponse(BaseModel):
    entries: List[GpuPowerHistoryEntry]
    total: int
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend
python -m pytest tests/services/power/gpu/test_schemas.py -v
```

Expected: 9 PASSED.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/gpu_power.py backend/tests/services/power/gpu/__init__.py backend/tests/services/power/gpu/test_schemas.py
git commit -m "feat(gpu-power): add Pydantic schemas for GPU power management"
```

---

## Task 2: Database Models

**Files:**
- Create: `backend/app/models/gpu_power.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/services/power/gpu/test_models.py`

- [ ] **Step 1: Write failing model tests**

Create `backend/tests/services/power/gpu/test_models.py`:

```python
"""Smoke tests for GPU power DB models — verify schema and table creation."""
import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.gpu_power import GpuPowerLog, GpuPowerConfigDb


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_gpu_power_log_table_exists(db_session):
    inspector = inspect(db_session.bind)
    assert "gpu_power_log" in inspector.get_table_names()


def test_gpu_power_log_columns(db_session):
    inspector = inspect(db_session.bind)
    cols = {c["name"] for c in inspector.get_columns("gpu_power_log")}
    assert {"id", "timestamp", "state", "previous_state", "reason", "source",
            "power_watts_at_transition"}.issubset(cols)


def test_gpu_power_config_table_exists(db_session):
    inspector = inspect(db_session.bind)
    assert "gpu_power_config" in inspector.get_table_names()


def test_gpu_power_log_insert(db_session):
    from datetime import datetime, timezone
    log = GpuPowerLog(
        timestamp=datetime.now(timezone.utc),
        state="standby",
        previous_state="active",
        reason="idle_window_elapsed",
        source=None,
        power_watts_at_transition=42.5,
    )
    db_session.add(log)
    db_session.commit()
    assert log.id is not None


def test_gpu_power_config_singleton_insert(db_session):
    cfg = GpuPowerConfigDb(id=1, config_json='{"enabled": true}')
    db_session.add(cfg)
    db_session.commit()
    assert cfg.id == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
python -m pytest tests/services/power/gpu/test_models.py -v
```

Expected: FAIL with `ImportError: cannot import name 'GpuPowerLog' from 'app.models.gpu_power'`.

- [ ] **Step 3: Create the models file**

Create `backend/app/models/gpu_power.py`:

```python
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
```

- [ ] **Step 4: Register the models**

Edit `backend/app/models/__init__.py`. After the existing `from app.models.power import (...)` block (around line 24-30), add:

```python
from app.models.gpu_power import GpuPowerLog, GpuPowerConfigDb
```

In the `__all__` list, add `"GpuPowerLog"` and `"GpuPowerConfigDb"` alongside the other power entries (after `"PowerDynamicModeConfig"`).

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend
python -m pytest tests/services/power/gpu/test_models.py -v
```

Expected: 5 PASSED.

- [ ] **Step 6: Generate Alembic migration**

```bash
cd backend
alembic revision --autogenerate -m "add gpu power tables"
```

Open the generated file under `backend/alembic/versions/` and verify it creates two tables: `gpu_power_log` (with index `idx_gpu_power_log_state_ts`) and `gpu_power_config`. If autogenerate produces extra unrelated migrations, edit the file to drop those (only keep the two table creates and the index).

- [ ] **Step 7: Apply and roll back the migration to verify**

```bash
cd backend
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```

Expected: no errors. Tables present after upgrade.

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/gpu_power.py backend/app/models/__init__.py backend/alembic/versions/*_add_gpu_power_tables.py backend/tests/services/power/gpu/test_models.py
git commit -m "feat(gpu-power): add database models and migration"
```

---

## Task 3: Backend Protocol & Dev Backend

**Files:**
- Create: `backend/app/services/power/gpu/__init__.py`
- Create: `backend/app/services/power/gpu/protocol.py`
- Create: `backend/app/services/power/gpu/dev_backend.py`
- Test: `backend/tests/services/power/gpu/test_dev_backend.py`

- [ ] **Step 1: Write failing tests for the dev backend**

Create `backend/tests/services/power/gpu/test_dev_backend.py`:

```python
import pytest
from app.services.power.gpu.dev_backend import DevGpuPowerBackend
from app.services.power.gpu.protocol import GpuPowerBackend
from app.schemas.gpu_power import GpuPowerState, GpuPowerCapabilities


def test_dev_backend_implements_protocol():
    backend = DevGpuPowerBackend()
    assert isinstance(backend, GpuPowerBackend)


def test_dev_backend_detected():
    backend = DevGpuPowerBackend()
    assert backend.detected is True
    assert backend.vendor == "dev"


def test_dev_backend_default_state():
    backend = DevGpuPowerBackend()
    assert backend._state == GpuPowerState.ACTIVE


@pytest.mark.asyncio
async def test_dev_backend_apply_state():
    backend = DevGpuPowerBackend()
    success, error = await backend.apply_state(GpuPowerState.STANDBY, config=None)
    assert success is True
    assert error is None
    assert await backend.current_state() == GpuPowerState.STANDBY


@pytest.mark.asyncio
async def test_dev_backend_has_write_permission():
    backend = DevGpuPowerBackend()
    assert await backend.has_write_permission() is True


def test_dev_backend_capabilities():
    backend = DevGpuPowerBackend()
    caps = backend.capabilities()
    assert isinstance(caps, GpuPowerCapabilities)
    assert caps.vendor == "dev"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
python -m pytest tests/services/power/gpu/test_dev_backend.py -v
```

Expected: FAIL — module does not exist.

- [ ] **Step 3: Create the protocol**

Create `backend/app/services/power/gpu/__init__.py` (empty file).

Create `backend/app/services/power/gpu/protocol.py`:

```python
"""GPU power backend protocol."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Tuple

from app.schemas.gpu_power import GpuPowerCapabilities, GpuPowerConfig, GpuPowerState


class GpuPowerBackend(ABC):
    """Vendor-agnostic GPU power backend.

    Concrete implementations: AmdGpuPowerBackend, NvidiaGpuPowerBackend, DevGpuPowerBackend.
    """

    @property
    @abstractmethod
    def detected(self) -> bool:
        """True if this backend's hardware is present."""

    @property
    @abstractmethod
    def vendor(self) -> str:
        """One of 'amd', 'nvidia', 'dev'."""

    @abstractmethod
    async def apply_state(
        self,
        state: GpuPowerState,
        config: Optional[GpuPowerConfig],
    ) -> Tuple[bool, Optional[str]]:
        """Apply target state. Returns (success, error_message)."""

    @abstractmethod
    async def current_state(self) -> Optional[GpuPowerState]:
        """Best-effort read of the currently-applied state. None if unknown."""

    @abstractmethod
    async def has_write_permission(self) -> bool:
        """True if this process can apply state to the hardware."""

    @abstractmethod
    def capabilities(self) -> GpuPowerCapabilities:
        """Hardware-reported ranges/options for UI bounds and selects."""
```

- [ ] **Step 4: Create the dev backend**

Create `backend/app/services/power/gpu/dev_backend.py`:

```python
"""In-memory mock backend for Windows / dev mode."""
from __future__ import annotations

import logging
from typing import Optional, Tuple

from app.schemas.gpu_power import (
    GpuPowerCapabilities,
    GpuPowerConfig,
    GpuPowerState,
)
from app.services.power.gpu.protocol import GpuPowerBackend

logger = logging.getLogger(__name__)


class DevGpuPowerBackend(GpuPowerBackend):
    """Records applied state in memory; never touches hardware."""

    def __init__(self) -> None:
        self._state: GpuPowerState = GpuPowerState.ACTIVE
        self._has_permission: bool = True

    @property
    def detected(self) -> bool:
        return True

    @property
    def vendor(self) -> str:
        return "dev"

    async def apply_state(
        self,
        state: GpuPowerState,
        config: Optional[GpuPowerConfig],
    ) -> Tuple[bool, Optional[str]]:
        logger.debug("DevGpuPowerBackend: apply_state %s -> %s", self._state, state)
        self._state = state
        return True, None

    async def current_state(self) -> Optional[GpuPowerState]:
        return self._state

    async def has_write_permission(self) -> bool:
        return self._has_permission

    def capabilities(self) -> GpuPowerCapabilities:
        return GpuPowerCapabilities(
            vendor="dev",
            amd_performance_levels=["auto", "low", "high"],
            amd_profile_modes=["BOOTUP_DEFAULT", "POWER_SAVING", "VIDEO"],
            nvidia_min_clock_mhz=210,
            nvidia_max_clock_mhz=2400,
            nvidia_min_power_watts=50,
            nvidia_max_power_watts=355,
            nvidia_default_power_watts=315,
        )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend
python -m pytest tests/services/power/gpu/test_dev_backend.py -v
```

Expected: 6 PASSED.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/power/gpu/__init__.py backend/app/services/power/gpu/protocol.py backend/app/services/power/gpu/dev_backend.py backend/tests/services/power/gpu/test_dev_backend.py
git commit -m "feat(gpu-power): add backend protocol and dev mock"
```

---

## Task 4: Display Detector

**Files:**
- Create: `backend/app/services/power/gpu/display_detector.py`
- Test: `backend/tests/services/power/gpu/test_display_detector.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/services/power/gpu/test_display_detector.py`:

```python
"""Test sysfs DRM connector counting."""
from pathlib import Path
import pytest

from app.services.power.gpu.display_detector import get_active_display_count


@pytest.fixture
def fake_sysfs(tmp_path: Path) -> Path:
    """Build a fake /sys/class/drm tree."""
    drm = tmp_path / "sys" / "class" / "drm"
    drm.mkdir(parents=True)
    return tmp_path


def _make_connector(root: Path, name: str, status: str, enabled: str) -> None:
    drm = root / "sys" / "class" / "drm"
    conn = drm / name
    conn.mkdir(parents=True, exist_ok=True)
    (conn / "status").write_text(status + "\n")
    (conn / "enabled").write_text(enabled + "\n")


@pytest.mark.asyncio
async def test_no_drm_directory(tmp_path: Path):
    count = await get_active_display_count(sysfs_root=tmp_path)
    assert count == 0


@pytest.mark.asyncio
async def test_no_connectors(fake_sysfs: Path):
    count = await get_active_display_count(sysfs_root=fake_sysfs)
    assert count == 0


@pytest.mark.asyncio
async def test_one_connected_display(fake_sysfs: Path):
    _make_connector(fake_sysfs, "card0-HDMI-A-1", "connected", "enabled")
    count = await get_active_display_count(sysfs_root=fake_sysfs)
    assert count == 1


@pytest.mark.asyncio
async def test_disconnected_display_not_counted(fake_sysfs: Path):
    _make_connector(fake_sysfs, "card0-HDMI-A-1", "disconnected", "disabled")
    count = await get_active_display_count(sysfs_root=fake_sysfs)
    assert count == 0


@pytest.mark.asyncio
async def test_connected_but_disabled_not_counted(fake_sysfs: Path):
    """DPMS-off / unused: don't count as active."""
    _make_connector(fake_sysfs, "card0-DP-1", "connected", "disabled")
    count = await get_active_display_count(sysfs_root=fake_sysfs)
    assert count == 0


@pytest.mark.asyncio
async def test_card_root_not_counted(fake_sysfs: Path):
    """`card0` itself (no -CONNECTOR suffix) is not a connector."""
    drm = fake_sysfs / "sys" / "class" / "drm"
    (drm / "card0").mkdir()
    count = await get_active_display_count(sysfs_root=fake_sysfs)
    assert count == 0


@pytest.mark.asyncio
async def test_multiple_connectors(fake_sysfs: Path):
    _make_connector(fake_sysfs, "card0-HDMI-A-1", "connected", "enabled")
    _make_connector(fake_sysfs, "card0-DP-1", "disconnected", "disabled")
    _make_connector(fake_sysfs, "card0-DP-2", "connected", "enabled")
    count = await get_active_display_count(sysfs_root=fake_sysfs)
    assert count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
python -m pytest tests/services/power/gpu/test_display_detector.py -v
```

Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement the detector**

Create `backend/app/services/power/gpu/display_detector.py`:

```python
"""DRM connector status reader."""
from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_CONNECTOR_RE = re.compile(r"^card\d+-")


def _count_sync(sysfs_root: Path) -> int:
    drm = sysfs_root / "sys" / "class" / "drm"
    if not drm.exists():
        return 0
    count = 0
    for entry in drm.iterdir():
        if not _CONNECTOR_RE.match(entry.name):
            continue
        status_file = entry / "status"
        enabled_file = entry / "enabled"
        if not status_file.exists() or not enabled_file.exists():
            continue
        try:
            status = status_file.read_text().strip()
            enabled = enabled_file.read_text().strip()
        except OSError as exc:
            logger.debug("Cannot read %s: %s", entry.name, exc)
            continue
        if status == "connected" and enabled == "enabled":
            count += 1
    return count


async def get_active_display_count(sysfs_root: Path = Path("/")) -> int:
    """Count DRM connectors with status='connected' AND enabled='enabled'.

    `enabled` covers DPMS-off / unused: physically connected but no active mode.
    """
    return await asyncio.to_thread(_count_sync, sysfs_root)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend
python -m pytest tests/services/power/gpu/test_display_detector.py -v
```

Expected: 7 PASSED.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/gpu/display_detector.py backend/tests/services/power/gpu/test_display_detector.py
git commit -m "feat(gpu-power): add DRM display connector detector"
```

---

## Task 5: AMD Backend

**Files:**
- Create: `backend/app/services/power/gpu/amd_backend.py`
- Test: `backend/tests/services/power/gpu/test_amd_backend.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/services/power/gpu/test_amd_backend.py`:

```python
"""Tests for AMD GPU power backend (sysfs-based)."""
from pathlib import Path
from typing import Optional

import pytest

from app.schemas.gpu_power import (
    AmdProfileMode,
    AmdStateConfig,
    GpuPowerConfig,
    GpuPowerState,
)
from app.services.power.gpu.amd_backend import AmdGpuPowerBackend


def _make_amd_card(root: Path, *, with_profile_mode: bool = True) -> Path:
    """Create a minimal sysfs tree for an AMD dGPU."""
    device = root / "sys" / "class" / "drm" / "card0" / "device"
    device.mkdir(parents=True)
    (device / "vendor").write_text("0x1002\n")
    (device / "pp_dpm_sclk").write_text("0: 500Mhz\n1: 2400Mhz *\n")
    (device / "power_dpm_force_performance_level").write_text("auto\n")
    if with_profile_mode:
        (device / "pp_power_profile_mode").write_text(
            "PROFILE_INDEX(NAME)\n"
            "  0 BOOTUP_DEFAULT*\n"
            "  1 3D_FULL_SCREEN\n"
            "  2 POWER_SAVING\n"
            "  3 VIDEO\n"
        )
    return device


def test_detect_amd_card(tmp_path: Path):
    _make_amd_card(tmp_path)
    backend = AmdGpuPowerBackend(sysfs_root=tmp_path)
    assert backend.detected is True
    assert backend.vendor == "amd"


def test_no_amd_card(tmp_path: Path):
    backend = AmdGpuPowerBackend(sysfs_root=tmp_path)
    assert backend.detected is False


def test_skip_non_amd_vendor(tmp_path: Path):
    device = tmp_path / "sys" / "class" / "drm" / "card0" / "device"
    device.mkdir(parents=True)
    (device / "vendor").write_text("0x10de\n")  # NVIDIA
    (device / "pp_dpm_sclk").write_text("0: 500Mhz\n")
    backend = AmdGpuPowerBackend(sysfs_root=tmp_path)
    assert backend.detected is False


def test_skip_igpu_no_pp_dpm_sclk(tmp_path: Path):
    device = tmp_path / "sys" / "class" / "drm" / "card0" / "device"
    device.mkdir(parents=True)
    (device / "vendor").write_text("0x1002\n")  # AMD vendor but no pp_dpm_sclk
    backend = AmdGpuPowerBackend(sysfs_root=tmp_path)
    assert backend.detected is False


def test_parse_profile_modes(tmp_path: Path):
    _make_amd_card(tmp_path)
    backend = AmdGpuPowerBackend(sysfs_root=tmp_path)
    caps = backend.capabilities()
    assert "POWER_SAVING" in caps.amd_profile_modes
    assert "BOOTUP_DEFAULT" in caps.amd_profile_modes


@pytest.mark.asyncio
async def test_apply_active_state(tmp_path: Path):
    device = _make_amd_card(tmp_path)
    backend = AmdGpuPowerBackend(sysfs_root=tmp_path)
    config = GpuPowerConfig()
    ok, err = await backend.apply_state(GpuPowerState.ACTIVE, config)
    assert ok is True
    assert err is None
    assert (device / "power_dpm_force_performance_level").read_text().strip() == "auto"


@pytest.mark.asyncio
async def test_apply_deep_idle_state(tmp_path: Path):
    device = _make_amd_card(tmp_path)
    backend = AmdGpuPowerBackend(sysfs_root=tmp_path)
    config = GpuPowerConfig()  # defaults: deep_idle = "low" + POWER_SAVING
    ok, err = await backend.apply_state(GpuPowerState.DEEP_IDLE, config)
    assert ok is True
    assert (device / "power_dpm_force_performance_level").read_text().strip() == "low"
    # POWER_SAVING is index 2 in our fake mode list
    assert (device / "pp_power_profile_mode").read_text().splitlines()[-1].strip() == "2"


@pytest.mark.asyncio
async def test_apply_unknown_profile_falls_back(tmp_path: Path):
    """If user requests a profile mode not exposed by the driver, fall back to BOOTUP_DEFAULT."""
    device = _make_amd_card(tmp_path)
    backend = AmdGpuPowerBackend(sysfs_root=tmp_path)
    config = GpuPowerConfig(
        amd_deep_idle=AmdStateConfig(
            performance_level="low",
            profile_mode=AmdProfileMode.VR,  # not exposed in fake setup
        )
    )
    ok, _ = await backend.apply_state(GpuPowerState.DEEP_IDLE, config)
    assert ok is True
    # Should write index 0 (BOOTUP_DEFAULT) as fallback
    assert (device / "pp_power_profile_mode").read_text().splitlines()[-1].strip() == "0"


@pytest.mark.asyncio
async def test_has_write_permission(tmp_path: Path):
    _make_amd_card(tmp_path)
    backend = AmdGpuPowerBackend(sysfs_root=tmp_path)
    # Files in tmp_path are writable for current user
    assert await backend.has_write_permission() is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
python -m pytest tests/services/power/gpu/test_amd_backend.py -v
```

Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement the AMD backend**

Create `backend/app/services/power/gpu/amd_backend.py`:

```python
"""AMD GPU power backend.

Writes to amdgpu sysfs files:
- power_dpm_force_performance_level: auto/low/high/...
- pp_power_profile_mode: index of named mode (parsed at startup)

Detection mirrors `services/monitoring/gpu/amd_backend.py`: first dGPU with pp_dpm_sclk.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.schemas.gpu_power import (
    AmdProfileMode,
    AmdStateConfig,
    GpuPowerCapabilities,
    GpuPowerConfig,
    GpuPowerState,
)
from app.services.power.gpu.protocol import GpuPowerBackend

logger = logging.getLogger(__name__)

AMD_VENDOR_ID = "0x1002"

# Conservative list of valid performance_level values; the kernel exposes more
# but these are the broadly-supported ones across kernels.
AMD_PERFORMANCE_LEVELS = [
    "auto",
    "low",
    "high",
    "manual",
    "profile_standard",
    "profile_min_sclk",
    "profile_min_mclk",
    "profile_peak",
]


class AmdGpuPowerBackend(GpuPowerBackend):
    def __init__(self, sysfs_root: Path | str = Path("/")) -> None:
        self._root = Path(sysfs_root)
        self._device_path: Optional[Path] = None
        self._profile_modes: Dict[str, int] = {}  # name -> index
        self._detect()

    # ---- detection ----

    def _detect(self) -> None:
        drm = self._root / "sys" / "class" / "drm"
        if not drm.exists():
            return
        for card in sorted(p for p in drm.iterdir() if re.fullmatch(r"card\d+", p.name)):
            device = card / "device"
            if not device.exists():
                continue
            try:
                vendor = (device / "vendor").read_text().strip()
            except OSError:
                continue
            if vendor != AMD_VENDOR_ID:
                continue
            if not (device / "pp_dpm_sclk").exists():
                continue
            self._device_path = device
            self._profile_modes = self._parse_profile_modes(device / "pp_power_profile_mode")
            return

    @staticmethod
    def _parse_profile_modes(path: Path) -> Dict[str, int]:
        """Parse `pp_power_profile_mode` into {NAME: index}.

        Format example:
            PROFILE_INDEX(NAME)
              0 BOOTUP_DEFAULT*
              1 3D_FULL_SCREEN
              2 POWER_SAVING
        """
        if not path.exists():
            return {}
        modes: Dict[str, int] = {}
        try:
            text = path.read_text()
        except OSError:
            return {}
        for line in text.splitlines():
            m = re.match(r"\s*(\d+)\s+(\S+?)\*?\s*$", line)
            if m:
                idx, name = int(m.group(1)), m.group(2).rstrip("*").strip()
                modes[name] = idx
        return modes

    # ---- public API ----

    @property
    def detected(self) -> bool:
        return self._device_path is not None

    @property
    def vendor(self) -> str:
        return "amd"

    async def apply_state(
        self,
        state: GpuPowerState,
        config: Optional[GpuPowerConfig],
    ) -> Tuple[bool, Optional[str]]:
        if self._device_path is None:
            return False, "AMD GPU not detected"
        if config is None:
            config = GpuPowerConfig()

        state_config = self._config_for_state(config, state)
        try:
            await asyncio.to_thread(self._apply_sync, state_config)
        except OSError as exc:
            logger.warning("AMD apply_state failed: %s", exc)
            return False, str(exc)
        return True, None

    def _config_for_state(self, config: GpuPowerConfig, state: GpuPowerState) -> AmdStateConfig:
        return {
            GpuPowerState.ACTIVE: config.amd_active,
            GpuPowerState.STANDBY: config.amd_standby,
            GpuPowerState.DEEP_IDLE: config.amd_deep_idle,
        }[state]

    def _apply_sync(self, state_config: AmdStateConfig) -> None:
        assert self._device_path is not None
        if state_config.performance_level is not None:
            (self._device_path / "power_dpm_force_performance_level").write_text(
                state_config.performance_level
            )
        if state_config.profile_mode is not None:
            idx = self._profile_modes.get(state_config.profile_mode.value)
            if idx is None:
                idx = self._profile_modes.get("BOOTUP_DEFAULT", 0)
                logger.warning(
                    "AMD profile mode %s not exposed by driver; using fallback index %d",
                    state_config.profile_mode.value, idx,
                )
            (self._device_path / "pp_power_profile_mode").write_text(str(idx))

    async def current_state(self) -> Optional[GpuPowerState]:
        if self._device_path is None:
            return None
        try:
            level = await asyncio.to_thread(
                lambda: (self._device_path / "power_dpm_force_performance_level").read_text().strip()
            )
        except OSError:
            return None
        if level == "low":
            return GpuPowerState.DEEP_IDLE
        if level == "auto":
            return GpuPowerState.ACTIVE
        return None  # ambiguous (manual/high/profile_*)

    async def has_write_permission(self) -> bool:
        if self._device_path is None:
            return False
        target = self._device_path / "power_dpm_force_performance_level"
        return await asyncio.to_thread(os.access, str(target), os.W_OK)

    def capabilities(self) -> GpuPowerCapabilities:
        return GpuPowerCapabilities(
            vendor="amd" if self.detected else None,
            amd_performance_levels=list(AMD_PERFORMANCE_LEVELS),
            amd_profile_modes=list(self._profile_modes.keys()),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend
python -m pytest tests/services/power/gpu/test_amd_backend.py -v
```

Expected: 9 PASSED.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/gpu/amd_backend.py backend/tests/services/power/gpu/test_amd_backend.py
git commit -m "feat(gpu-power): add AMD sysfs backend"
```

---

## Task 6: NVIDIA Backend

**Files:**
- Create: `backend/app/services/power/gpu/nvidia_backend.py`
- Test: `backend/tests/services/power/gpu/test_nvidia_backend.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/services/power/gpu/test_nvidia_backend.py`:

```python
"""Tests for NVIDIA GPU power backend (nvidia-smi wrapper)."""
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from app.schemas.gpu_power import (
    GpuPowerConfig,
    GpuPowerState,
    NvidiaStateConfig,
)
from app.services.power.gpu.nvidia_backend import NvidiaGpuPowerBackend


def _mock_run(stdout: str = "", returncode: int = 0):
    result = MagicMock()
    result.stdout = stdout
    result.returncode = returncode
    return result


def test_not_detected_when_nvidia_smi_missing():
    with patch("subprocess.run", side_effect=FileNotFoundError):
        backend = NvidiaGpuPowerBackend()
        assert backend.detected is False


def test_not_detected_when_no_gpus():
    with patch("subprocess.run", return_value=_mock_run(stdout="\n")):
        backend = NvidiaGpuPowerBackend()
        assert backend.detected is False


def test_detected_with_one_gpu():
    list_out = "GPU 0: NVIDIA GeForce RTX 4080 (UUID: GPU-...)\n"
    range_out = "210, 2505, 100, 320, 320\n"
    with patch("subprocess.run", side_effect=[
        _mock_run(stdout=list_out),  # nvidia-smi -L
        _mock_run(stdout=range_out),  # range query
        _mock_run(stdout=""),  # persistence-mode set
    ]):
        backend = NvidiaGpuPowerBackend()
        assert backend.detected is True
        assert backend.vendor == "nvidia"


def test_capabilities_seeded_from_card():
    list_out = "GPU 0: NVIDIA GeForce RTX 4080\n"
    range_out = "210, 2505, 100, 320, 320\n"
    with patch("subprocess.run", side_effect=[
        _mock_run(stdout=list_out),
        _mock_run(stdout=range_out),
        _mock_run(stdout=""),
    ]):
        backend = NvidiaGpuPowerBackend()
        caps = backend.capabilities()
        assert caps.nvidia_min_clock_mhz == 210
        assert caps.nvidia_max_clock_mhz == 2505
        assert caps.nvidia_min_power_watts == 100
        assert caps.nvidia_max_power_watts == 320
        assert caps.nvidia_default_power_watts == 320


@pytest.mark.asyncio
async def test_apply_active_resets_clocks():
    list_out = "GPU 0: NVIDIA GeForce RTX 4080\n"
    range_out = "210, 2505, 100, 320, 320\n"
    apply_calls = []

    def fake_run(args, **kwargs):
        apply_calls.append(args)
        return _mock_run()

    with patch("subprocess.run", side_effect=[
        _mock_run(stdout=list_out),
        _mock_run(stdout=range_out),
        _mock_run(stdout=""),
    ]):
        backend = NvidiaGpuPowerBackend()

    with patch("subprocess.run", side_effect=fake_run):
        ok, err = await backend.apply_state(GpuPowerState.ACTIVE, GpuPowerConfig())
        assert ok is True
        # Active default: -rgc + reset power limit
        assert any("-rgc" in " ".join(a) for a in apply_calls)


@pytest.mark.asyncio
async def test_apply_deep_idle_locks_clocks():
    list_out = "GPU 0: NVIDIA GeForce RTX 4080\n"
    range_out = "210, 2505, 100, 320, 320\n"
    apply_calls = []

    def fake_run(args, **kwargs):
        apply_calls.append(args)
        return _mock_run()

    with patch("subprocess.run", side_effect=[
        _mock_run(stdout=list_out),
        _mock_run(stdout=range_out),
        _mock_run(stdout=""),
    ]):
        backend = NvidiaGpuPowerBackend()

    config = GpuPowerConfig(
        nvidia_deep_idle=NvidiaStateConfig(
            min_clock_mhz=210,
            max_clock_mhz=210,
            power_limit_watts=100,
        )
    )

    with patch("subprocess.run", side_effect=fake_run):
        ok, err = await backend.apply_state(GpuPowerState.DEEP_IDLE, config)
        assert ok is True
        joined = [" ".join(a) for a in apply_calls]
        assert any("-lgc 210,210" in c for c in joined)
        assert any("-pl 100" in c for c in joined)


@pytest.mark.asyncio
async def test_apply_returns_error_on_subprocess_failure():
    list_out = "GPU 0: NVIDIA GeForce RTX 4080\n"
    range_out = "210, 2505, 100, 320, 320\n"

    with patch("subprocess.run", side_effect=[
        _mock_run(stdout=list_out),
        _mock_run(stdout=range_out),
        _mock_run(stdout=""),
    ]):
        backend = NvidiaGpuPowerBackend()

    with patch("subprocess.run", return_value=_mock_run(returncode=1, stdout="permission denied")):
        ok, err = await backend.apply_state(GpuPowerState.DEEP_IDLE, GpuPowerConfig())
        assert ok is False
        assert err is not None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
python -m pytest tests/services/power/gpu/test_nvidia_backend.py -v
```

Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement the NVIDIA backend**

Create `backend/app/services/power/gpu/nvidia_backend.py`:

```python
"""NVIDIA GPU power backend via nvidia-smi.

Required commands (all use list-args, never shell=True):
- `nvidia-smi -L`                                    : list GPUs
- `nvidia-smi --query-gpu=... --format=csv,noheader,nounits` : capabilities
- `nvidia-smi -pm 1`                                 : enable persistence mode
- `nvidia-smi -lgc <min>,<max>` / `-rgc`             : lock/reset clocks
- `nvidia-smi -pl <watts>`                           : power limit
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
from typing import List, Optional, Tuple

from app.schemas.gpu_power import (
    GpuPowerCapabilities,
    GpuPowerConfig,
    GpuPowerState,
    NvidiaStateConfig,
)
from app.services.power.gpu.protocol import GpuPowerBackend

logger = logging.getLogger(__name__)


class NvidiaGpuPowerBackend(GpuPowerBackend):
    def __init__(self) -> None:
        self._detected: bool = False
        self._min_clock: Optional[int] = None
        self._max_clock: Optional[int] = None
        self._min_power: Optional[int] = None
        self._max_power: Optional[int] = None
        self._default_power: Optional[int] = None
        self._detect()

    def _run(self, args: List[str], check: bool = False) -> Optional[subprocess.CompletedProcess]:
        try:
            return subprocess.run(args, capture_output=True, text=True, check=check, timeout=10)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.debug("nvidia-smi run failed: %s", exc)
            return None

    def _detect(self) -> None:
        if shutil.which("nvidia-smi") is None:
            return
        result = self._run(["nvidia-smi", "-L"])
        if result is None or not result.stdout.strip():
            return
        if "GPU 0" not in result.stdout:
            return
        # Query capabilities
        query = self._run([
            "nvidia-smi",
            "--query-gpu=clocks.gr.min,clocks.gr.max,power.min_limit,power.max_limit,power.default_limit",
            "--format=csv,noheader,nounits",
        ])
        if query is not None and query.stdout.strip():
            try:
                parts = [p.strip() for p in query.stdout.strip().splitlines()[0].split(",")]
                if len(parts) == 5:
                    self._min_clock = int(float(parts[0]))
                    self._max_clock = int(float(parts[1]))
                    self._min_power = int(float(parts[2]))
                    self._max_power = int(float(parts[3]))
                    self._default_power = int(float(parts[4]))
            except (ValueError, IndexError) as exc:
                logger.debug("Could not parse nvidia-smi capabilities: %s", exc)

        # Persistence mode (best-effort)
        self._run(["nvidia-smi", "-pm", "1"])
        self._detected = True

    @property
    def detected(self) -> bool:
        return self._detected

    @property
    def vendor(self) -> str:
        return "nvidia"

    async def apply_state(
        self,
        state: GpuPowerState,
        config: Optional[GpuPowerConfig],
    ) -> Tuple[bool, Optional[str]]:
        if not self._detected:
            return False, "NVIDIA GPU not detected"
        if config is None:
            config = GpuPowerConfig()
        state_config = self._effective_state_config(config, state)
        return await asyncio.to_thread(self._apply_sync, state, state_config)

    def _effective_state_config(self, config: GpuPowerConfig, state: GpuPowerState) -> NvidiaStateConfig:
        raw = {
            GpuPowerState.ACTIVE: config.nvidia_active,
            GpuPowerState.STANDBY: config.nvidia_standby,
            GpuPowerState.DEEP_IDLE: config.nvidia_deep_idle,
        }[state]
        # Seed defaults if unset
        if state == GpuPowerState.STANDBY and (raw.min_clock_mhz is None or raw.max_clock_mhz is None):
            mid = (self._min_clock + self._max_clock) // 2 if self._min_clock and self._max_clock else None
            return NvidiaStateConfig(
                min_clock_mhz=raw.min_clock_mhz or self._min_clock,
                max_clock_mhz=raw.max_clock_mhz or mid,
                power_limit_watts=raw.power_limit_watts,
            )
        if state == GpuPowerState.DEEP_IDLE and (raw.min_clock_mhz is None or raw.max_clock_mhz is None):
            return NvidiaStateConfig(
                min_clock_mhz=raw.min_clock_mhz or self._min_clock,
                max_clock_mhz=raw.max_clock_mhz or self._min_clock,
                power_limit_watts=raw.power_limit_watts or self._min_power,
            )
        return raw

    def _apply_sync(self, state: GpuPowerState, sc: NvidiaStateConfig) -> Tuple[bool, Optional[str]]:
        # Active with no overrides → reset
        if state == GpuPowerState.ACTIVE and sc.min_clock_mhz is None and sc.max_clock_mhz is None:
            res = self._run(["nvidia-smi", "-rgc"], check=False)
            if res is None or res.returncode != 0:
                return False, (res.stdout if res else "nvidia-smi -rgc failed")
            if sc.power_limit_watts is None and self._default_power is not None:
                self._run(["nvidia-smi", "-pl", str(self._default_power)])
            return True, None

        # Lock clocks if both bounds given
        if sc.min_clock_mhz is not None and sc.max_clock_mhz is not None:
            res = self._run(
                ["nvidia-smi", "-lgc", f"{sc.min_clock_mhz},{sc.max_clock_mhz}"],
                check=False,
            )
            if res is None or res.returncode != 0:
                return False, (res.stdout if res else "nvidia-smi -lgc failed")

        if sc.power_limit_watts is not None:
            res = self._run(["nvidia-smi", "-pl", str(sc.power_limit_watts)], check=False)
            if res is None or res.returncode != 0:
                return False, (res.stdout if res else "nvidia-smi -pl failed")

        return True, None

    async def current_state(self) -> Optional[GpuPowerState]:
        # NVIDIA doesn't expose state names — best-effort heuristic via current clock cap.
        return None

    async def has_write_permission(self) -> bool:
        # nvidia-smi typically requires either root or nvidia-modprobe SUID
        # for clock/power changes. We don't probe destructively; assume true
        # if we got this far. Real failures surface in apply_state.
        return self._detected

    def capabilities(self) -> GpuPowerCapabilities:
        return GpuPowerCapabilities(
            vendor="nvidia" if self._detected else None,
            nvidia_min_clock_mhz=self._min_clock,
            nvidia_max_clock_mhz=self._max_clock,
            nvidia_min_power_watts=self._min_power,
            nvidia_max_power_watts=self._max_power,
            nvidia_default_power_watts=self._default_power,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend
python -m pytest tests/services/power/gpu/test_nvidia_backend.py -v
```

Expected: 7 PASSED.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/gpu/nvidia_backend.py backend/tests/services/power/gpu/test_nvidia_backend.py
git commit -m "feat(gpu-power): add NVIDIA nvidia-smi backend"
```

---

## Task 7: Event Hook Registry

**Files:**
- Create: `backend/app/services/power/gpu/events.py`
- Test: `backend/tests/services/power/gpu/test_event_hook.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/services/power/gpu/test_event_hook.py`:

```python
"""Tests for the deep-idle event hook registry."""
import asyncio
import pytest

from app.services.power.gpu import events


@pytest.fixture(autouse=True)
def _reset_hooks():
    events._deep_idle_entering_callbacks.clear()
    events._deep_idle_exiting_callbacks.clear()
    yield
    events._deep_idle_entering_callbacks.clear()
    events._deep_idle_exiting_callbacks.clear()


@pytest.mark.asyncio
async def test_register_and_emit_entering():
    called = []

    async def cb():
        called.append("hit")

    events.register_deep_idle_entering(cb)
    await events.emit_deep_idle_entering()
    assert called == ["hit"]


@pytest.mark.asyncio
async def test_multiple_callbacks_run_in_parallel():
    order = []

    async def slow():
        await asyncio.sleep(0.05)
        order.append("slow")

    async def fast():
        order.append("fast")

    events.register_deep_idle_entering(slow)
    events.register_deep_idle_entering(fast)
    await events.emit_deep_idle_entering()
    # Fast should finish first if running in parallel
    assert order == ["fast", "slow"]


@pytest.mark.asyncio
async def test_callback_exception_does_not_block_others():
    called = []

    async def boom():
        raise RuntimeError("kaboom")

    async def survives():
        called.append("survived")

    events.register_deep_idle_entering(boom)
    events.register_deep_idle_entering(survives)
    await events.emit_deep_idle_entering()
    assert called == ["survived"]


@pytest.mark.asyncio
async def test_exiting_hook_separate_from_entering():
    enter_called = []
    exit_called = []

    async def on_enter():
        enter_called.append("e")

    async def on_exit():
        exit_called.append("x")

    events.register_deep_idle_entering(on_enter)
    events.register_deep_idle_exiting(on_exit)

    await events.emit_deep_idle_exiting()
    assert enter_called == []
    assert exit_called == ["x"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
python -m pytest tests/services/power/gpu/test_event_hook.py -v
```

Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement the hook registry**

Create `backend/app/services/power/gpu/events.py`:

```python
"""Deep-idle event hooks for plugins (e.g., Ollama unload before deep idle)."""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, List

logger = logging.getLogger(__name__)

_DeepIdleCallback = Callable[[], Awaitable[None]]

_deep_idle_entering_callbacks: List[_DeepIdleCallback] = []
_deep_idle_exiting_callbacks: List[_DeepIdleCallback] = []


def register_deep_idle_entering(callback: _DeepIdleCallback) -> None:
    """Plugin opt-in: called just before the GPU transitions ACTIVE/STANDBY -> DEEP_IDLE.

    Plugins should release VRAM/state here. The manager waits up to
    `deep_idle_grace_seconds` (configurable) for callbacks to finish before
    applying the deep-idle state.
    """
    _deep_idle_entering_callbacks.append(callback)


def register_deep_idle_exiting(callback: _DeepIdleCallback) -> None:
    """Plugin opt-in: called when the GPU leaves DEEP_IDLE."""
    _deep_idle_exiting_callbacks.append(callback)


async def emit_deep_idle_entering() -> None:
    """Run all 'entering' callbacks in parallel; exceptions logged, never raised."""
    if not _deep_idle_entering_callbacks:
        return
    results = await asyncio.gather(
        *(_safe_call(cb) for cb in _deep_idle_entering_callbacks),
        return_exceptions=False,
    )
    del results  # gathered for completion; errors already logged


async def emit_deep_idle_exiting() -> None:
    if not _deep_idle_exiting_callbacks:
        return
    await asyncio.gather(
        *(_safe_call(cb) for cb in _deep_idle_exiting_callbacks),
        return_exceptions=False,
    )


async def _safe_call(cb: _DeepIdleCallback) -> None:
    try:
        await cb()
    except Exception as exc:
        logger.warning("Deep-idle callback %r raised: %s", cb, exc)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend
python -m pytest tests/services/power/gpu/test_event_hook.py -v
```

Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/gpu/events.py backend/tests/services/power/gpu/test_event_hook.py
git commit -m "feat(gpu-power): add plugin event hook registry"
```

---

## Task 8: Config Store

**Files:**
- Create: `backend/app/services/power/gpu/config_store.py`
- Test: `backend/tests/services/power/gpu/test_config_store.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/services/power/gpu/test_config_store.py`:

```python
"""Tests for GpuPowerConfig persistence."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.gpu_power import GpuPowerConfigDb
from app.schemas.gpu_power import GpuPowerConfig
from app.services.power.gpu import config_store


@pytest.fixture
def in_memory_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr(config_store, "SessionLocal", Session)
    yield Session


def test_load_returns_defaults_when_empty(in_memory_db):
    cfg = config_store.load_gpu_power_config()
    assert cfg.enabled is False
    assert cfg.idle_window_seconds == 30


def test_save_then_load_roundtrip(in_memory_db):
    cfg = GpuPowerConfig(enabled=True, idle_window_seconds=60, usage_threshold_percent=10.0)
    config_store.save_gpu_power_config(cfg)
    loaded = config_store.load_gpu_power_config()
    assert loaded.enabled is True
    assert loaded.idle_window_seconds == 60
    assert loaded.usage_threshold_percent == 10.0


def test_save_overwrites_existing(in_memory_db):
    config_store.save_gpu_power_config(GpuPowerConfig(idle_window_seconds=60))
    config_store.save_gpu_power_config(GpuPowerConfig(idle_window_seconds=120))
    loaded = config_store.load_gpu_power_config()
    assert loaded.idle_window_seconds == 120
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
python -m pytest tests/services/power/gpu/test_config_store.py -v
```

Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement the config store**

Create `backend/app/services/power/gpu/config_store.py`:

```python
"""Persistence for GpuPowerConfig as JSON in a singleton DB row."""
from __future__ import annotations

import logging

from app.core.database import SessionLocal
from app.models.gpu_power import GpuPowerConfigDb
from app.schemas.gpu_power import GpuPowerConfig

logger = logging.getLogger(__name__)


def load_gpu_power_config() -> GpuPowerConfig:
    """Load config from DB; return defaults if no row exists."""
    try:
        db = SessionLocal()
        try:
            row = db.query(GpuPowerConfigDb).filter(GpuPowerConfigDb.id == 1).first()
            if row is None or not row.config_json:
                return GpuPowerConfig()
            return GpuPowerConfig.model_validate_json(row.config_json)
        finally:
            db.close()
    except Exception as exc:
        logger.warning("Failed to load GpuPowerConfig from DB: %s; using defaults", exc)
        return GpuPowerConfig()


def save_gpu_power_config(config: GpuPowerConfig) -> bool:
    """Persist config as JSON to the singleton row (id=1). Returns True on success."""
    try:
        db = SessionLocal()
        try:
            row = db.query(GpuPowerConfigDb).filter(GpuPowerConfigDb.id == 1).first()
            payload = config.model_dump_json()
            if row is None:
                row = GpuPowerConfigDb(id=1, config_json=payload)
                db.add(row)
            else:
                row.config_json = payload
            db.commit()
            return True
        finally:
            db.close()
    except Exception as exc:
        logger.error("Failed to save GpuPowerConfig: %s", exc)
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend
python -m pytest tests/services/power/gpu/test_config_store.py -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/gpu/config_store.py backend/tests/services/power/gpu/test_config_store.py
git commit -m "feat(gpu-power): persist config as JSON in singleton row"
```

---

## Task 9: Manager State Machine

**Files:**
- Create: `backend/app/services/power/gpu/manager.py`
- Test: `backend/tests/services/power/gpu/test_state_machine.py`

- [ ] **Step 1: Write failing state-machine tests**

Create `backend/tests/services/power/gpu/test_state_machine.py`:

```python
"""State machine tests using DevGpuPowerBackend with controlled time and inputs."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.gpu_power import GpuPowerConfig, GpuPowerState
from app.services.power.gpu.dev_backend import DevGpuPowerBackend
from app.services.power.gpu.manager import GpuPowerManagerService


@pytest.fixture
def manager(monkeypatch):
    GpuPowerManagerService._instance = None
    mgr = GpuPowerManagerService()
    mgr._backend = DevGpuPowerBackend()
    mgr._config = GpuPowerConfig(enabled=True)
    # Stub config loaders so _tick doesn't reload
    monkeypatch.setattr(
        "app.services.power.gpu.manager.load_gpu_power_config",
        lambda: mgr._config,
    )
    monkeypatch.setattr(
        "app.services.power.gpu.manager.save_gpu_power_config",
        lambda c: True,
    )
    yield mgr
    GpuPowerManagerService._instance = None


@pytest.mark.asyncio
async def test_active_when_display_connected(manager):
    with patch.object(manager, "_get_displays", AsyncMock(return_value=1)), \
         patch.object(manager, "_get_usage_percent", AsyncMock(return_value=0.0)):
        await manager._tick()
        assert manager._state == GpuPowerState.ACTIVE


@pytest.mark.asyncio
async def test_active_when_usage_high(manager):
    with patch.object(manager, "_get_displays", AsyncMock(return_value=0)), \
         patch.object(manager, "_get_usage_percent", AsyncMock(return_value=80.0)):
        await manager._tick()
        assert manager._state == GpuPowerState.ACTIVE


@pytest.mark.asyncio
async def test_transition_active_to_standby_after_idle_window(manager):
    manager._config = GpuPowerConfig(enabled=True, idle_window_seconds=10)
    manager._idle_since = datetime.now(timezone.utc) - timedelta(seconds=15)

    with patch.object(manager, "_get_displays", AsyncMock(return_value=0)), \
         patch.object(manager, "_get_usage_percent", AsyncMock(return_value=0.0)):
        await manager._tick()
        assert manager._state == GpuPowerState.STANDBY


@pytest.mark.asyncio
async def test_transition_standby_to_deep_idle_after_grace(manager):
    manager._config = GpuPowerConfig(
        enabled=True,
        idle_window_seconds=10,
        deep_idle_extra_seconds=20,
        deep_idle_grace_seconds=0,
    )
    manager._state = GpuPowerState.STANDBY
    manager._standby_since = datetime.now(timezone.utc) - timedelta(seconds=25)
    manager._idle_since = datetime.now(timezone.utc) - timedelta(seconds=40)

    with patch.object(manager, "_get_displays", AsyncMock(return_value=0)), \
         patch.object(manager, "_get_usage_percent", AsyncMock(return_value=0.0)), \
         patch("app.services.power.gpu.manager.emit_deep_idle_entering", AsyncMock()) as mock_emit:
        await manager._tick()
        assert manager._state == GpuPowerState.DEEP_IDLE
        mock_emit.assert_awaited_once()


@pytest.mark.asyncio
async def test_demand_forces_active(manager):
    manager._state = GpuPowerState.DEEP_IDLE

    with patch.object(manager, "_get_displays", AsyncMock(return_value=0)), \
         patch.object(manager, "_get_usage_percent", AsyncMock(return_value=0.0)):
        await manager.register_demand("test_source")
        # Tick should re-evaluate; demand alone forces ACTIVE
        await manager._tick()
        assert manager._state == GpuPowerState.ACTIVE


@pytest.mark.asyncio
async def test_disabled_config_does_nothing(manager):
    manager._config = GpuPowerConfig(enabled=False)
    manager._state = GpuPowerState.DEEP_IDLE

    with patch.object(manager, "_get_displays", AsyncMock(return_value=0)), \
         patch.object(manager, "_get_usage_percent", AsyncMock(return_value=0.0)):
        await manager._tick()
        assert manager._state == GpuPowerState.DEEP_IDLE  # unchanged


@pytest.mark.asyncio
async def test_demand_expiration(manager):
    # Register with already-expired timeout
    await manager.register_demand("expired", timeout_seconds=1)
    # Manually backdate
    manager._demands["expired"].expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
    await manager._purge_expired_demands()
    assert "expired" not in manager._demands


@pytest.mark.asyncio
async def test_unregister_demand(manager):
    await manager.register_demand("plugin_x")
    assert "plugin_x" in manager._demands
    removed = await manager.unregister_demand("plugin_x")
    assert removed is True
    assert "plugin_x" not in manager._demands


@pytest.mark.asyncio
async def test_get_status_returns_current_state(manager):
    manager._state = GpuPowerState.STANDBY
    with patch.object(manager, "_get_displays", AsyncMock(return_value=0)), \
         patch.object(manager, "_get_usage_percent", AsyncMock(return_value=2.5)):
        status = await manager.get_status()
        assert status.current_state == GpuPowerState.STANDBY
        assert status.detected is True
        assert status.vendor == "dev"
        assert status.usage_percent == 2.5
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
python -m pytest tests/services/power/gpu/test_state_machine.py -v
```

Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement the manager**

Create `backend/app/services/power/gpu/manager.py`:

```python
"""GPU power management service.

Singleton, async, demand-aware. Mirrors PowerManagerService.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Dict, List, Optional, Tuple

from app.core.database import SessionLocal
from app.models.gpu_power import GpuPowerLog
from app.schemas.gpu_power import (
    GpuPowerCapabilities,
    GpuPowerConfig,
    GpuPowerDemandInfo,
    GpuPowerHistoryEntry,
    GpuPowerState,
    GpuPowerStatus,
)
from app.services.monitoring.shm import read_shm
from app.services.power.gpu.config_store import (
    load_gpu_power_config,
    save_gpu_power_config,
)
from app.services.power.gpu.display_detector import get_active_display_count
from app.services.power.gpu.events import (
    emit_deep_idle_entering,
    emit_deep_idle_exiting,
)
from app.services.power.gpu.protocol import GpuPowerBackend

logger = logging.getLogger(__name__)


class GpuPowerManagerService:
    """Singleton; create via get_gpu_power_manager()."""

    _instance: Optional["GpuPowerManagerService"] = None
    _new_lock = Lock()

    def __new__(cls) -> "GpuPowerManagerService":
        with cls._new_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._backend: Optional[GpuPowerBackend] = None
        self._config: GpuPowerConfig = GpuPowerConfig()
        self._state: GpuPowerState = GpuPowerState.ACTIVE
        self._idle_since: datetime = datetime.now(timezone.utc)
        self._standby_since: Optional[datetime] = None
        self._last_transition: Optional[datetime] = None
        self._last_reason: Optional[str] = None
        self._demands: Dict[str, GpuPowerDemandInfo] = {}
        self._monitor_task: Optional[asyncio.Task] = None
        self._is_running: bool = False
        self._state_lock = asyncio.Lock()

    # ---- backend selection ----

    def _select_backend(self) -> GpuPowerBackend:
        from app.core.config import settings

        # Try AMD first, then NVIDIA, then dev
        try:
            from app.services.power.gpu.amd_backend import AmdGpuPowerBackend
            amd = AmdGpuPowerBackend()
            if amd.detected:
                return amd
        except Exception as exc:
            logger.debug("AMD GPU power backend init failed: %s", exc)

        try:
            from app.services.power.gpu.nvidia_backend import NvidiaGpuPowerBackend
            nv = NvidiaGpuPowerBackend()
            if nv.detected:
                return nv
        except Exception as exc:
            logger.debug("NVIDIA GPU power backend init failed: %s", exc)

        if getattr(settings, "is_dev_mode", False):
            from app.services.power.gpu.dev_backend import DevGpuPowerBackend
            logger.info("Using DevGpuPowerBackend (dev mode, no real GPU detected)")
            return DevGpuPowerBackend()

        # No-op backend (detected=False) — keeps API consistent
        from app.services.power.gpu.dev_backend import DevGpuPowerBackend
        backend = DevGpuPowerBackend()
        backend._has_permission = False  # signal upstream
        return backend

    # ---- lifecycle ----

    async def start(self) -> None:
        if self._is_running:
            logger.warning("GpuPowerManagerService already running")
            return
        self._config = load_gpu_power_config()
        self._backend = self._select_backend()
        self._is_running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info(
            "GpuPowerManagerService started (vendor=%s, enabled=%s)",
            self._backend.vendor if self._backend else "none",
            self._config.enabled,
        )

    async def stop(self) -> None:
        if not self._is_running:
            return
        self._is_running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
        # Best-effort: return to ACTIVE so the next process boot starts clean
        if self._backend and self._backend.detected:
            try:
                await self._backend.apply_state(GpuPowerState.ACTIVE, self._config)
            except Exception as exc:
                logger.debug("Could not reset GPU to ACTIVE on shutdown: %s", exc)
        logger.info("GpuPowerManagerService stopped")

    # ---- monitor loop ----

    async def _monitor_loop(self) -> None:
        while self._is_running:
            try:
                await self._tick()
            except Exception as exc:
                logger.error("GPU power monitor tick failed: %s", exc)
            await asyncio.sleep(self._config.monitor_interval_seconds)

    async def _tick(self) -> None:
        if not self._config.enabled or self._backend is None or not self._backend.detected:
            return

        await self._purge_expired_demands()

        displays = await self._get_displays()
        usage = await self._get_usage_percent()
        has_demand = bool(self._demands)
        is_idle = (
            displays == 0
            and usage < self._config.usage_threshold_percent
            and not has_demand
        )

        now = datetime.now(timezone.utc)
        if not is_idle:
            if self._state != GpuPowerState.ACTIVE:
                await self._transition(GpuPowerState.ACTIVE, "not_idle")
            self._idle_since = now
            self._standby_since = None
            return

        if self._state == GpuPowerState.ACTIVE:
            if now - self._idle_since >= timedelta(seconds=self._config.idle_window_seconds):
                await self._transition(GpuPowerState.STANDBY, "idle_window_elapsed")
                self._standby_since = now
        elif self._state == GpuPowerState.STANDBY:
            assert self._standby_since is not None
            if now - self._standby_since >= timedelta(seconds=self._config.deep_idle_extra_seconds):
                await emit_deep_idle_entering()
                if self._config.deep_idle_grace_seconds > 0:
                    await asyncio.sleep(self._config.deep_idle_grace_seconds)
                await self._transition(GpuPowerState.DEEP_IDLE, "grace_elapsed")
        # DEEP_IDLE → no further forward transitions; only wake-up via is_idle=False above

    # ---- inputs ----

    async def _get_displays(self) -> int:
        return await get_active_display_count()

    async def _get_usage_percent(self) -> float:
        from app.services.monitoring.shm import TELEMETRY_FILE

        # GPU sample lives in monitoring shm under telemetry payload "gpu" key.
        data = read_shm(TELEMETRY_FILE, max_age_seconds=30.0)
        if not data:
            return 0.0
        gpu = data.get("gpu") if isinstance(data, dict) else None
        if not gpu:
            return 0.0
        usage = gpu.get("usage_percent")
        return float(usage) if usage is not None else 0.0

    # ---- transitions ----

    async def _transition(self, target: GpuPowerState, reason: str) -> None:
        if self._state == target:
            return
        if self._backend is None:
            return
        previous = self._state
        ok, err = await self._backend.apply_state(target, self._config)
        if not ok:
            logger.warning(
                "GPU apply_state(%s) failed: %s",
                target.value, err,
            )
            return

        # Fire exiting hook on leaving DEEP_IDLE
        if previous == GpuPowerState.DEEP_IDLE:
            await emit_deep_idle_exiting()

        self._state = target
        self._last_transition = datetime.now(timezone.utc)
        self._last_reason = reason
        self._persist_log(target, previous, reason)
        logger.info("GPU power state: %s -> %s (%s)", previous.value, target.value, reason)

    def _persist_log(self, state: GpuPowerState, previous: GpuPowerState, reason: str) -> None:
        try:
            db = SessionLocal()
            try:
                row = GpuPowerLog(
                    timestamp=datetime.now(timezone.utc),
                    state=state.value,
                    previous_state=previous.value if previous else None,
                    reason=reason[:64],
                )
                db.add(row)
                db.commit()
            finally:
                db.close()
        except Exception as exc:
            logger.debug("Could not persist GpuPowerLog: %s", exc)

    # ---- demands ----

    async def register_demand(
        self,
        source: str,
        timeout_seconds: Optional[int] = None,
        description: Optional[str] = None,
    ) -> str:
        async with self._state_lock:
            expires_at = None
            if timeout_seconds:
                expires_at = datetime.now(timezone.utc) + timedelta(seconds=timeout_seconds)
            self._demands[source] = GpuPowerDemandInfo(
                source=source,
                registered_at=datetime.now(timezone.utc),
                expires_at=expires_at,
                description=description,
            )
            logger.info("GPU power demand registered: %s", source)
        # Force re-evaluation immediately so callers see fast wake-up
        if self._state != GpuPowerState.ACTIVE:
            await self._transition(GpuPowerState.ACTIVE, f"demand:{source}")
        return source

    async def unregister_demand(self, source: str) -> bool:
        async with self._state_lock:
            if source not in self._demands:
                return False
            del self._demands[source]
            logger.info("GPU power demand unregistered: %s", source)
        return True

    async def _purge_expired_demands(self) -> None:
        now = datetime.now(timezone.utc)
        expired = [
            s for s, d in self._demands.items()
            if d.expires_at is not None and d.expires_at <= now
        ]
        for s in expired:
            del self._demands[s]
            logger.info("GPU power demand expired: %s", s)

    # ---- public read API ----

    async def get_status(self) -> GpuPowerStatus:
        if self._backend is None:
            return GpuPowerStatus(
                enabled=self._config.enabled,
                detected=False,
                vendor=None,
                current_state=self._state,
                has_write_permission=False,
                active_demands=list(self._demands.values()),
            )
        return GpuPowerStatus(
            enabled=self._config.enabled,
            detected=self._backend.detected,
            vendor=self._backend.vendor if self._backend.detected else None,
            current_state=self._state,
            last_transition=self._last_transition,
            last_reason=self._last_reason,
            active_demands=list(self._demands.values()),
            has_write_permission=await self._backend.has_write_permission(),
            estimated_power_watts=None,
            display_count=await self._get_displays() if self._backend.detected else 0,
            usage_percent=await self._get_usage_percent() if self._backend.detected else None,
        )

    def get_config(self) -> GpuPowerConfig:
        return self._config

    async def set_config(self, config: GpuPowerConfig) -> Tuple[bool, Optional[str]]:
        async with self._state_lock:
            self._config = config
            save_gpu_power_config(config)
        logger.info("GPU power config updated (enabled=%s)", config.enabled)
        return True, None

    def get_capabilities(self) -> GpuPowerCapabilities:
        if self._backend is None:
            return GpuPowerCapabilities(vendor=None)
        return self._backend.capabilities()

    def get_history(self, limit: int = 100) -> Tuple[List[GpuPowerHistoryEntry], int]:
        try:
            db = SessionLocal()
            try:
                from sqlalchemy import func as sa_func
                total = db.query(sa_func.count(GpuPowerLog.id)).scalar() or 0
                rows = (
                    db.query(GpuPowerLog)
                    .order_by(GpuPowerLog.timestamp.desc())
                    .limit(limit)
                    .all()
                )
                entries = [
                    GpuPowerHistoryEntry(
                        timestamp=row.timestamp,
                        state=GpuPowerState(row.state),
                        previous_state=GpuPowerState(row.previous_state) if row.previous_state else None,
                        reason=row.reason,
                        source=row.source,
                        power_watts_at_transition=row.power_watts_at_transition,
                    )
                    for row in rows
                ]
                return entries, total
            finally:
                db.close()
        except Exception as exc:
            logger.warning("Could not load gpu power history: %s", exc)
            return [], 0


# Module-level helpers
def get_gpu_power_manager() -> GpuPowerManagerService:
    return GpuPowerManagerService()


async def start_gpu_power_manager() -> None:
    await get_gpu_power_manager().start()


async def stop_gpu_power_manager() -> None:
    await get_gpu_power_manager().stop()


def get_status() -> dict:
    """Service-status registry adapter."""
    mgr = get_gpu_power_manager()
    return {
        "is_running": mgr._is_running,
        "started_at": None,
        "uptime_seconds": None,
        "sample_count": 0,
        "error_count": 0,
        "last_error": None,
        "last_error_at": None,
        "interval_seconds": float(mgr._config.monitor_interval_seconds),
        "current_state": mgr._state.value,
        "active_demands": len(mgr._demands),
        "enabled": mgr._config.enabled,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend
python -m pytest tests/services/power/gpu/test_state_machine.py -v
```

Expected: 9 PASSED.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/gpu/manager.py backend/tests/services/power/gpu/test_state_machine.py
git commit -m "feat(gpu-power): add manager service with three-state machine"
```

---

## Task 10: API Routes

**Files:**
- Create: `backend/app/api/routes/gpu_power.py`
- Modify: `backend/app/api/routes/__init__.py`
- Modify: `backend/app/core/rate_limiter.py`
- Test: `backend/tests/api/test_gpu_power_routes.py`

- [ ] **Step 1: Add rate-limit key**

Edit `backend/app/core/rate_limiter.py`. Find the `RATE_LIMITS` dict (starts ~line 67). Add a new entry alongside other moderate-traffic limits:

```python
    "gpu_power": "60/minute",
```

- [ ] **Step 2: Write failing route tests**

Create `backend/tests/api/test_gpu_power_routes.py`:

```python
"""Integration tests for /api/gpu-power/* endpoints."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_manager():
    from app.services.power.gpu.manager import GpuPowerManagerService
    GpuPowerManagerService._instance = None
    yield
    GpuPowerManagerService._instance = None


def test_get_status_requires_auth(client: TestClient):
    resp = client.get("/api/gpu-power/status")
    assert resp.status_code in (401, 403)


def test_get_status_authenticated(client: TestClient, auth_headers):
    resp = client.get("/api/gpu-power/status", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "enabled" in data
    assert "current_state" in data
    assert data["current_state"] in ("active", "standby", "deep_idle")


def test_get_config_authenticated(client: TestClient, auth_headers):
    resp = client.get("/api/gpu-power/config", headers=auth_headers)
    assert resp.status_code == 200
    assert "idle_window_seconds" in resp.json()


def test_put_config_admin_only(client: TestClient, auth_headers):
    """Non-admin user gets 403."""
    body = {"enabled": True, "idle_window_seconds": 60}
    resp = client.put("/api/gpu-power/config", json=body, headers=auth_headers)
    assert resp.status_code == 403


def test_put_config_admin_succeeds(client: TestClient, admin_headers):
    body = {"enabled": True, "idle_window_seconds": 60}
    resp = client.put("/api/gpu-power/config", json=body, headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True
    assert resp.json()["idle_window_seconds"] == 60


def test_put_config_validation_rejects_out_of_range(client: TestClient, admin_headers):
    body = {"idle_window_seconds": 5}  # below ge=10
    resp = client.put("/api/gpu-power/config", json=body, headers=admin_headers)
    assert resp.status_code == 422


def test_get_capabilities_authenticated(client: TestClient, auth_headers):
    resp = client.get("/api/gpu-power/capabilities", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "vendor" in body


def test_register_demand(client: TestClient, auth_headers):
    body = {"source": "test_demand", "timeout_seconds": 60, "description": "test"}
    resp = client.post("/api/gpu-power/demand", json=body, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["source"] == "test_demand"


def test_unregister_demand(client: TestClient, auth_headers):
    client.post("/api/gpu-power/demand", json={"source": "drop_me"}, headers=auth_headers)
    resp = client.delete("/api/gpu-power/demand/drop_me", headers=auth_headers)
    assert resp.status_code == 200


def test_unregister_unknown_demand_returns_404(client: TestClient, auth_headers):
    resp = client.delete("/api/gpu-power/demand/never_registered", headers=auth_headers)
    assert resp.status_code == 404


def test_history_authenticated(client: TestClient, auth_headers):
    resp = client.get("/api/gpu-power/history", headers=auth_headers)
    assert resp.status_code == 200
    assert "entries" in resp.json()
    assert "total" in resp.json()
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd backend
python -m pytest tests/api/test_gpu_power_routes.py -v
```

Expected: FAIL — route module not registered (404 for all).

- [ ] **Step 4: Create the route file**

Create `backend/app/api/routes/gpu_power.py`:

```python
"""GPU power management API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import ValidationError

from app.api import deps
from app.core.rate_limiter import limiter, get_limit
from app.schemas.gpu_power import (
    GpuPowerCapabilities,
    GpuPowerConfig,
    GpuPowerHistoryResponse,
    GpuPowerStatus,
    RegisterGpuDemandRequest,
)
from app.schemas.user import UserPublic
from app.services.power.gpu.manager import get_gpu_power_manager

router = APIRouter(prefix="/gpu-power", tags=["gpu-power-management"])


@router.get("/status", response_model=GpuPowerStatus)
@limiter.limit(get_limit("gpu_power"))
async def get_status(
    request: Request,
    response: Response,
    _user: UserPublic = Depends(deps.get_current_user),
) -> GpuPowerStatus:
    return await get_gpu_power_manager().get_status()


@router.get("/config", response_model=GpuPowerConfig)
@limiter.limit(get_limit("gpu_power"))
async def get_config(
    request: Request,
    response: Response,
    _user: UserPublic = Depends(deps.get_current_user),
) -> GpuPowerConfig:
    return get_gpu_power_manager().get_config()


@router.put("/config", response_model=GpuPowerConfig)
@limiter.limit(get_limit("gpu_power"))
async def put_config(
    request: Request,
    response: Response,
    body: GpuPowerConfig,
    _admin: UserPublic = Depends(deps.get_current_admin),
) -> GpuPowerConfig:
    mgr = get_gpu_power_manager()
    # Validate clocks against capabilities
    caps = mgr.get_capabilities()
    err = _validate_against_capabilities(body, caps)
    if err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=err)
    ok, err = await mgr.set_config(body)
    if not ok:
        raise HTTPException(status_code=500, detail=err or "Failed to save config")
    return mgr.get_config()


def _validate_against_capabilities(config: GpuPowerConfig, caps: GpuPowerCapabilities) -> str | None:
    """Reject NVIDIA clocks/power outside hardware-reported range."""
    if caps.vendor != "nvidia":
        return None
    for state_name, sc in [
        ("nvidia_active", config.nvidia_active),
        ("nvidia_standby", config.nvidia_standby),
        ("nvidia_deep_idle", config.nvidia_deep_idle),
    ]:
        if sc.min_clock_mhz is not None and caps.nvidia_min_clock_mhz is not None:
            if sc.min_clock_mhz < caps.nvidia_min_clock_mhz:
                return f"{state_name}.min_clock_mhz < hardware min ({caps.nvidia_min_clock_mhz})"
        if sc.max_clock_mhz is not None and caps.nvidia_max_clock_mhz is not None:
            if sc.max_clock_mhz > caps.nvidia_max_clock_mhz:
                return f"{state_name}.max_clock_mhz > hardware max ({caps.nvidia_max_clock_mhz})"
        if sc.power_limit_watts is not None and caps.nvidia_max_power_watts is not None:
            if sc.power_limit_watts > caps.nvidia_max_power_watts:
                return f"{state_name}.power_limit_watts > hardware max ({caps.nvidia_max_power_watts})"
        if sc.power_limit_watts is not None and caps.nvidia_min_power_watts is not None:
            if sc.power_limit_watts < caps.nvidia_min_power_watts:
                return f"{state_name}.power_limit_watts < hardware min ({caps.nvidia_min_power_watts})"
    return None


@router.get("/capabilities", response_model=GpuPowerCapabilities)
@limiter.limit(get_limit("gpu_power"))
async def get_capabilities(
    request: Request,
    response: Response,
    _user: UserPublic = Depends(deps.get_current_user),
) -> GpuPowerCapabilities:
    return get_gpu_power_manager().get_capabilities()


@router.post("/demand")
@limiter.limit(get_limit("gpu_power"))
async def register_demand(
    request: Request,
    response: Response,
    body: RegisterGpuDemandRequest,
    _user: UserPublic = Depends(deps.get_current_user),
) -> dict:
    src = await get_gpu_power_manager().register_demand(
        source=body.source,
        timeout_seconds=body.timeout_seconds,
        description=body.description,
    )
    return {"source": src, "success": True}


@router.delete("/demand/{source}")
@limiter.limit(get_limit("gpu_power"))
async def unregister_demand(
    request: Request,
    response: Response,
    source: str,
    _user: UserPublic = Depends(deps.get_current_user),
) -> dict:
    removed = await get_gpu_power_manager().unregister_demand(source)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Demand '{source}' not found")
    return {"source": source, "removed": True}


@router.get("/history", response_model=GpuPowerHistoryResponse)
@limiter.limit(get_limit("gpu_power"))
async def get_history(
    request: Request,
    response: Response,
    limit: int = 100,
    _user: UserPublic = Depends(deps.get_current_user),
) -> GpuPowerHistoryResponse:
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=422, detail="limit must be 1..1000")
    entries, total = get_gpu_power_manager().get_history(limit=limit)
    return GpuPowerHistoryResponse(entries=entries, total=total)
```

- [ ] **Step 5: Register the router**

Edit `backend/app/api/routes/__init__.py`. In the import block (top of file, line 3-22), add `gpu_power,` alongside the other power-related imports — match the existing format. Then in the router registration block (around line 50, after `power.router`), add:

```python
api_router.include_router(gpu_power.router, tags=["gpu-power-management"])
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd backend
python -m pytest tests/api/test_gpu_power_routes.py -v
```

Expected: 11 PASSED.

(If `auth_headers` / `admin_headers` fixtures are missing, the test file uses the same convention as existing route tests — check `backend/tests/conftest.py`. If fixtures need adjusting, copy the pattern from `tests/api/test_power_routes.py`.)

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/routes/gpu_power.py backend/app/api/routes/__init__.py backend/app/core/rate_limiter.py backend/tests/api/test_gpu_power_routes.py
git commit -m "feat(gpu-power): add API routes with capability-based validation"
```

---

## Task 11: Lifespan Integration

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/core/lifespan.py`
- Test: `backend/tests/services/power/gpu/test_lifespan.py`

- [ ] **Step 1: Add settings flag**

Edit `backend/app/core/config.py`. Find the `Settings` class. Near other power-related settings (search for `power_management_enabled`), add:

```python
    gpu_power_management_enabled: bool = Field(
        default=True,
        description="Whether to start the GPU power manager service on primary worker",
    )
```

- [ ] **Step 2: Write failing lifespan test**

Create `backend/tests/services/power/gpu/test_lifespan.py`:

```python
"""Lifespan integration: start/stop and clean shutdown."""
import pytest

from app.schemas.gpu_power import GpuPowerState
from app.services.power.gpu.manager import (
    GpuPowerManagerService,
    get_gpu_power_manager,
    start_gpu_power_manager,
    stop_gpu_power_manager,
)


@pytest.fixture(autouse=True)
def _reset():
    GpuPowerManagerService._instance = None
    yield
    GpuPowerManagerService._instance = None


@pytest.mark.asyncio
async def test_start_then_stop():
    await start_gpu_power_manager()
    mgr = get_gpu_power_manager()
    assert mgr._is_running is True
    await stop_gpu_power_manager()
    assert mgr._is_running is False


@pytest.mark.asyncio
async def test_stop_returns_to_active():
    await start_gpu_power_manager()
    mgr = get_gpu_power_manager()
    mgr._state = GpuPowerState.DEEP_IDLE
    await stop_gpu_power_manager()
    # Backend should have been asked to apply ACTIVE on shutdown
    if mgr._backend is not None and mgr._backend.detected:
        # DevGpuPowerBackend records last applied state
        assert await mgr._backend.current_state() == GpuPowerState.ACTIVE


@pytest.mark.asyncio
async def test_double_start_is_idempotent():
    await start_gpu_power_manager()
    await start_gpu_power_manager()
    mgr = get_gpu_power_manager()
    assert mgr._is_running is True
    await stop_gpu_power_manager()
```

- [ ] **Step 3: Run test to verify it fails (or runs but lifecycle isn't wired)**

```bash
cd backend
python -m pytest tests/services/power/gpu/test_lifespan.py -v
```

Expected: tests likely PASS already (the manager is self-contained); this gate confirms behavior is correct in isolation. If any fail due to async event loop issues, fix in implementation.

- [ ] **Step 4: Wire into lifespan**

Edit `backend/app/core/lifespan.py`.

In the imports section of `_startup()` (around line 354-363, where `from app.services.power import manager as power_manager` is), add:

```python
    from app.services.power.gpu import manager as gpu_power_manager
```

In the primary-worker block (around line 411, after the existing power_manager start, around line 421), add:

```python
        if settings.gpu_power_management_enabled:
            try:
                await gpu_power_manager.start_gpu_power_manager()
                logger.info("GPU power management started")
            except Exception as e:
                logger.warning(f"GPU power management could not start: {e}")
```

In the corresponding `_shutdown()` function (search for the existing `power_manager.stop_power_manager` call and mirror it). For `_shutdown()`, add:

```python
        try:
            await gpu_power_manager.stop_gpu_power_manager()
        except Exception as e:
            logger.warning(f"GPU power manager shutdown failed: {e}")
```

(If `_shutdown()` does not currently stop the CPU power manager either, add the stop call alongside other cleanup; the manager's `stop()` is safe to call even if `start()` was skipped.)

- [ ] **Step 5: Run tests again to verify**

```bash
cd backend
python -m pytest tests/services/power/gpu/ -v
```

Expected: All tests PASS.

- [ ] **Step 6: Smoke-test full app startup**

```bash
cd backend
python -c "from app.main import app; print('app created', len(app.routes), 'routes')"
```

Expected: prints `app created N routes` (N > 100) without import errors.

- [ ] **Step 7: Commit**

```bash
git add backend/app/core/config.py backend/app/core/lifespan.py backend/tests/services/power/gpu/test_lifespan.py
git commit -m "feat(gpu-power): wire manager into FastAPI lifespan"
```

---

## Task 12: Service Status Registration

**Files:**
- Modify: `backend/app/core/service_registry.py`

- [ ] **Step 1: Find the existing pattern**

Open `backend/app/core/service_registry.py` and locate the `register_all_services()` function. Find where the existing power manager (`power_manager.get_status` or similar) is registered.

- [ ] **Step 2: Add GPU power manager registration**

In `register_all_services()`, alongside the existing power-manager registration, add:

```python
    from app.services.power.gpu.manager import get_status as gpu_power_get_status
    from app.services.power.gpu.manager import (
        start_gpu_power_manager,
        stop_gpu_power_manager,
    )
    from app.services.service_status import register_service

    register_service(
        name="gpu_power_manager",
        display_name="GPU Power Management",
        get_status_fn=gpu_power_get_status,
        start_fn=start_gpu_power_manager,
        stop_fn=stop_gpu_power_manager,
        config_enabled_fn=lambda: settings.gpu_power_management_enabled,
    )
```

If the file already imports `register_service` and `settings` at module top, omit the inline imports.

- [ ] **Step 3: Smoke test**

```bash
cd backend
python -c "from app.core.service_registry import register_all_services; print('OK')"
```

Expected: prints `OK`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/service_registry.py
git commit -m "feat(gpu-power): register service in admin status dashboard"
```

---

## Task 13: Frontend API Client

**Files:**
- Create: `client/src/api/gpuPower.ts`
- Create: `client/src/types/gpuPower.ts`

- [ ] **Step 1: Define types**

Create `client/src/types/gpuPower.ts`:

```typescript
export type GpuPowerState = "active" | "standby" | "deep_idle";

export type AmdProfileMode =
  | "BOOTUP_DEFAULT"
  | "POWER_SAVING"
  | "VIDEO"
  | "VR"
  | "COMPUTE"
  | "CUSTOM"
  | "3D_FULL_SCREEN";

export interface AmdStateConfig {
  performance_level?: string | null;
  profile_mode?: AmdProfileMode | null;
}

export interface NvidiaStateConfig {
  min_clock_mhz?: number | null;
  max_clock_mhz?: number | null;
  power_limit_watts?: number | null;
}

export interface GpuPowerConfig {
  enabled: boolean;
  idle_window_seconds: number;
  deep_idle_extra_seconds: number;
  deep_idle_grace_seconds: number;
  usage_threshold_percent: number;
  monitor_interval_seconds: number;
  amd_active: AmdStateConfig;
  amd_standby: AmdStateConfig;
  amd_deep_idle: AmdStateConfig;
  nvidia_active: NvidiaStateConfig;
  nvidia_standby: NvidiaStateConfig;
  nvidia_deep_idle: NvidiaStateConfig;
}

export interface GpuPowerDemandInfo {
  source: string;
  registered_at: string;
  expires_at: string | null;
  description: string | null;
}

export interface GpuPowerStatus {
  enabled: boolean;
  detected: boolean;
  vendor: string | null;
  current_state: GpuPowerState;
  last_transition: string | null;
  last_reason: string | null;
  active_demands: GpuPowerDemandInfo[];
  has_write_permission: boolean;
  estimated_power_watts: number | null;
  display_count: number;
  usage_percent: number | null;
}

export interface GpuPowerCapabilities {
  vendor: string | null;
  amd_performance_levels: string[];
  amd_profile_modes: string[];
  nvidia_min_clock_mhz: number | null;
  nvidia_max_clock_mhz: number | null;
  nvidia_min_power_watts: number | null;
  nvidia_max_power_watts: number | null;
  nvidia_default_power_watts: number | null;
}

export interface GpuPowerHistoryEntry {
  timestamp: string;
  state: GpuPowerState;
  previous_state: GpuPowerState | null;
  reason: string;
  source: string | null;
  power_watts_at_transition: number | null;
}

export interface GpuPowerHistoryResponse {
  entries: GpuPowerHistoryEntry[];
  total: number;
}
```

- [ ] **Step 2: Create the API client**

Create `client/src/api/gpuPower.ts`:

```typescript
import { api } from "../lib/api";
import type {
  GpuPowerCapabilities,
  GpuPowerConfig,
  GpuPowerHistoryResponse,
  GpuPowerStatus,
} from "../types/gpuPower";

export const gpuPowerApi = {
  getStatus: () =>
    api.get<GpuPowerStatus>("/gpu-power/status").then((r) => r.data),

  getConfig: () =>
    api.get<GpuPowerConfig>("/gpu-power/config").then((r) => r.data),

  putConfig: (body: GpuPowerConfig) =>
    api.put<GpuPowerConfig>("/gpu-power/config", body).then((r) => r.data),

  getCapabilities: () =>
    api.get<GpuPowerCapabilities>("/gpu-power/capabilities").then((r) => r.data),

  registerDemand: (source: string, timeoutSeconds?: number, description?: string) =>
    api.post<{ source: string; success: boolean }>("/gpu-power/demand", {
      source,
      timeout_seconds: timeoutSeconds,
      description,
    }).then((r) => r.data),

  unregisterDemand: (source: string) =>
    api.delete<{ source: string; removed: boolean }>(`/gpu-power/demand/${encodeURIComponent(source)}`).then((r) => r.data),

  getHistory: (limit = 100) =>
    api.get<GpuPowerHistoryResponse>(`/gpu-power/history?limit=${limit}`).then((r) => r.data),
};
```

- [ ] **Step 3: TypeScript build check**

```bash
cd client
npm run build 2>&1 | head -30
```

Expected: build succeeds (no type errors). If existing `lib/api` doesn't expose an `api` named export, follow the existing pattern in `client/src/api/power.ts` and adjust the import (e.g. `import api from "../lib/api"`).

- [ ] **Step 4: Commit**

```bash
git add client/src/api/gpuPower.ts client/src/types/gpuPower.ts
git commit -m "feat(gpu-power): add typed frontend API client"
```

---

## Task 14: Frontend Components

**Files:**
- Create: `client/src/components/power/GpuPowerThresholds.tsx`
- Create: `client/src/components/power/GpuPowerHardware.tsx`
- Create: `client/src/components/power/GpuPowerCard.tsx`
- Modify: `client/src/pages/PowerManagement.tsx`

- [ ] **Step 1: Create the thresholds form component**

Create `client/src/components/power/GpuPowerThresholds.tsx`:

```typescript
import React from "react";
import type { GpuPowerConfig } from "../../types/gpuPower";

interface Props {
  value: GpuPowerConfig;
  onChange: (next: GpuPowerConfig) => void;
  disabled?: boolean;
}

const fields: Array<{ key: keyof GpuPowerConfig; label: string; min: number; max: number; suffix: string }> = [
  { key: "idle_window_seconds", label: "Idle window", min: 10, max: 600, suffix: "s" },
  { key: "deep_idle_extra_seconds", label: "Grace before deep idle", min: 30, max: 3600, suffix: "s" },
  { key: "deep_idle_grace_seconds", label: "Plugin unload grace", min: 0, max: 30, suffix: "s" },
  { key: "monitor_interval_seconds", label: "Monitor interval", min: 1, max: 60, suffix: "s" },
];

export function GpuPowerThresholds({ value, onChange, disabled }: Props) {
  return (
    <div className="space-y-2">
      {fields.map((f) => (
        <label key={String(f.key)} className="flex items-center justify-between gap-4">
          <span className="text-sm">{f.label}</span>
          <span className="flex items-center gap-1">
            <input
              type="number"
              min={f.min}
              max={f.max}
              disabled={disabled}
              value={Number(value[f.key])}
              onChange={(e) => onChange({ ...value, [f.key]: Number(e.target.value) })}
              className="w-20 rounded border bg-transparent px-2 py-1 text-right"
            />
            <span className="text-xs text-zinc-500">{f.suffix}</span>
          </span>
        </label>
      ))}
      <label className="flex items-center justify-between gap-4">
        <span className="text-sm">Usage threshold</span>
        <span className="flex items-center gap-1">
          <input
            type="number"
            min={0}
            max={50}
            step={0.5}
            disabled={disabled}
            value={value.usage_threshold_percent}
            onChange={(e) =>
              onChange({ ...value, usage_threshold_percent: Number(e.target.value) })
            }
            className="w-20 rounded border bg-transparent px-2 py-1 text-right"
          />
          <span className="text-xs text-zinc-500">%</span>
        </span>
      </label>
    </div>
  );
}
```

- [ ] **Step 2: Create the hardware overrides component**

Create `client/src/components/power/GpuPowerHardware.tsx`:

```typescript
import React from "react";
import type {
  AmdProfileMode,
  AmdStateConfig,
  GpuPowerCapabilities,
  GpuPowerConfig,
  NvidiaStateConfig,
} from "../../types/gpuPower";

interface Props {
  value: GpuPowerConfig;
  caps: GpuPowerCapabilities | null;
  onChange: (next: GpuPowerConfig) => void;
  disabled?: boolean;
}

const STATES: Array<{ key: "active" | "standby" | "deep_idle"; label: string }> = [
  { key: "active", label: "Active" },
  { key: "standby", label: "Standby" },
  { key: "deep_idle", label: "Deep idle" },
];

export function GpuPowerHardware({ value, caps, onChange, disabled }: Props) {
  if (!caps || caps.vendor === null) {
    return <p className="text-xs text-zinc-500">No GPU detected — hardware overrides unavailable.</p>;
  }
  if (caps.vendor === "amd" || caps.vendor === "dev") {
    return <AmdSection value={value} caps={caps} onChange={onChange} disabled={disabled} />;
  }
  if (caps.vendor === "nvidia") {
    return <NvidiaSection value={value} caps={caps} onChange={onChange} disabled={disabled} />;
  }
  return null;
}

function AmdSection({ value, caps, onChange, disabled }: Props) {
  const setField = (state: "active" | "standby" | "deep_idle", patch: Partial<AmdStateConfig>) => {
    const key = `amd_${state}` as const;
    onChange({ ...value, [key]: { ...value[key], ...patch } });
  };

  return (
    <div className="space-y-3">
      <h4 className="text-sm font-medium">AMD per-state overrides</h4>
      {STATES.map(({ key, label }) => {
        const sc = value[`amd_${key}`];
        return (
          <div key={key} className="grid grid-cols-3 gap-2 items-center">
            <span className="text-sm">{label}</span>
            <select
              disabled={disabled}
              value={sc.performance_level ?? ""}
              onChange={(e) =>
                setField(key, { performance_level: e.target.value || null })
              }
              className="rounded border bg-transparent px-2 py-1 text-sm"
            >
              <option value="">(unset)</option>
              {caps?.amd_performance_levels.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
            <select
              disabled={disabled}
              value={sc.profile_mode ?? ""}
              onChange={(e) =>
                setField(key, { profile_mode: (e.target.value || null) as AmdProfileMode | null })
              }
              className="rounded border bg-transparent px-2 py-1 text-sm"
            >
              <option value="">(unset)</option>
              {caps?.amd_profile_modes.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>
        );
      })}
    </div>
  );
}

function NvidiaSection({ value, caps, onChange, disabled }: Props) {
  const setField = (state: "active" | "standby" | "deep_idle", patch: Partial<NvidiaStateConfig>) => {
    const key = `nvidia_${state}` as const;
    onChange({ ...value, [key]: { ...value[key], ...patch } });
  };

  return (
    <div className="space-y-3">
      <h4 className="text-sm font-medium">
        NVIDIA per-state clocks (range:&nbsp;
        {caps?.nvidia_min_clock_mhz ?? "?"}–{caps?.nvidia_max_clock_mhz ?? "?"} MHz)
      </h4>
      {STATES.map(({ key, label }) => {
        const sc = value[`nvidia_${key}`];
        return (
          <div key={key} className="grid grid-cols-4 gap-2 items-center">
            <span className="text-sm">{label}</span>
            <input
              type="number"
              placeholder="min MHz"
              disabled={disabled}
              value={sc.min_clock_mhz ?? ""}
              onChange={(e) =>
                setField(key, {
                  min_clock_mhz: e.target.value === "" ? null : Number(e.target.value),
                })
              }
              className="rounded border bg-transparent px-2 py-1 text-sm"
            />
            <input
              type="number"
              placeholder="max MHz"
              disabled={disabled}
              value={sc.max_clock_mhz ?? ""}
              onChange={(e) =>
                setField(key, {
                  max_clock_mhz: e.target.value === "" ? null : Number(e.target.value),
                })
              }
              className="rounded border bg-transparent px-2 py-1 text-sm"
            />
            <input
              type="number"
              placeholder="power W"
              disabled={disabled}
              value={sc.power_limit_watts ?? ""}
              onChange={(e) =>
                setField(key, {
                  power_limit_watts: e.target.value === "" ? null : Number(e.target.value),
                })
              }
              className="rounded border bg-transparent px-2 py-1 text-sm"
            />
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 3: Create the main card**

Create `client/src/components/power/GpuPowerCard.tsx`:

```typescript
import React, { useEffect, useMemo, useState } from "react";
import { gpuPowerApi } from "../../api/gpuPower";
import type {
  GpuPowerCapabilities,
  GpuPowerConfig,
  GpuPowerStatus,
} from "../../types/gpuPower";
import { GpuPowerThresholds } from "./GpuPowerThresholds";
import { GpuPowerHardware } from "./GpuPowerHardware";

const STATE_LABELS: Record<GpuPowerStatus["current_state"], string> = {
  active: "Active",
  standby: "Standby",
  deep_idle: "Deep idle",
};

export function GpuPowerCard({ isAdmin }: { isAdmin: boolean }) {
  const [status, setStatus] = useState<GpuPowerStatus | null>(null);
  const [config, setConfig] = useState<GpuPowerConfig | null>(null);
  const [caps, setCaps] = useState<GpuPowerCapabilities | null>(null);
  const [draft, setDraft] = useState<GpuPowerConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const [s, c, k] = await Promise.all([
          gpuPowerApi.getStatus(),
          gpuPowerApi.getConfig(),
          gpuPowerApi.getCapabilities(),
        ]);
        if (cancelled) return;
        setStatus(s);
        setConfig(c);
        setCaps(k);
        setDraft(c);
      } catch (err) {
        if (!cancelled) setError(String(err));
      }
    };
    load();
    const id = window.setInterval(load, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const dirty = useMemo(
    () => draft && config && JSON.stringify(draft) !== JSON.stringify(config),
    [draft, config],
  );

  const onSave = async () => {
    if (!draft) return;
    setSaving(true);
    setError(null);
    try {
      const saved = await gpuPowerApi.putConfig(draft);
      setConfig(saved);
      setDraft(saved);
    } catch (err: any) {
      setError(err?.response?.data?.detail || String(err));
    } finally {
      setSaving(false);
    }
  };

  if (status && !status.detected) {
    return (
      <section className="rounded-lg border p-4">
        <h3 className="text-base font-semibold">GPU Power Management</h3>
        <p className="text-sm text-zinc-500">No discrete GPU detected.</p>
      </section>
    );
  }

  return (
    <section className="rounded-lg border p-4 space-y-4">
      <header className="flex items-center justify-between">
        <h3 className="text-base font-semibold">GPU Power Management</h3>
        {status && (
          <span className="text-sm">
            <span className="font-mono">{STATE_LABELS[status.current_state]}</span>
            {status.vendor && <span className="text-zinc-500"> · {status.vendor}</span>}
          </span>
        )}
      </header>

      {status && (
        <ul className="text-sm grid grid-cols-2 gap-x-4 gap-y-1 text-zinc-700 dark:text-zinc-300">
          <li>Displays connected: {status.display_count}</li>
          <li>Usage: {status.usage_percent ?? 0}%</li>
          <li>Active demands: {status.active_demands.length}</li>
          <li>Permission: {status.has_write_permission ? "ok" : "missing"}</li>
        </ul>
      )}

      {draft && (
        <>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              disabled={!isAdmin || saving}
              checked={draft.enabled}
              onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
            />
            Enable GPU power management
          </label>

          <details>
            <summary className="cursor-pointer text-sm">Thresholds</summary>
            <div className="pt-2">
              <GpuPowerThresholds
                value={draft}
                onChange={setDraft}
                disabled={!isAdmin || saving}
              />
            </div>
          </details>

          <details>
            <summary className="cursor-pointer text-sm">Hardware overrides</summary>
            <div className="pt-2">
              <GpuPowerHardware
                value={draft}
                caps={caps}
                onChange={setDraft}
                disabled={!isAdmin || saving}
              />
            </div>
          </details>

          {isAdmin && (
            <div className="flex items-center gap-2">
              <button
                onClick={onSave}
                disabled={!dirty || saving}
                className="rounded bg-blue-600 px-3 py-1 text-sm text-white disabled:opacity-50"
              >
                {saving ? "Saving..." : "Save"}
              </button>
              <button
                onClick={() => setDraft(config)}
                disabled={!dirty || saving}
                className="rounded border px-3 py-1 text-sm disabled:opacity-50"
              >
                Reset
              </button>
              {error && <span className="text-sm text-red-500">{error}</span>}
            </div>
          )}
        </>
      )}
    </section>
  );
}
```

- [ ] **Step 4: Mount on the page**

Edit `client/src/pages/PowerManagement.tsx`. Find the existing return JSX where the CPU power card is rendered. Add an import at the top:

```typescript
import { GpuPowerCard } from "../components/power/GpuPowerCard";
```

In the JSX, render `<GpuPowerCard isAdmin={isAdmin} />` after the existing CPU power card. Locate where `isAdmin` is determined (existing prop or hook). If the existing page does not derive `isAdmin`, add:

```typescript
import { useAuth } from "../hooks/useAuth"; // adjust to existing hook
// inside the component:
const { user } = useAuth();
const isAdmin = user?.role === "admin";
```

- [ ] **Step 5: Build check**

```bash
cd client
npm run build
```

Expected: build completes without type errors.

- [ ] **Step 6: Smoke test in dev**

Start dev server, log in as admin, navigate to Power Management page, expand the GPU Power Management card. Verify status shows `dev` vendor on Windows; toggle enabled, change a threshold, click Save, refresh page, value persists.

```bash
python "D:/Programme (x86)/Baluhost/start_dev.py"
```

Then open http://localhost:5173/power-management in a browser.

- [ ] **Step 7: Commit**

```bash
git add client/src/components/power/GpuPowerCard.tsx client/src/components/power/GpuPowerHardware.tsx client/src/components/power/GpuPowerThresholds.tsx client/src/pages/PowerManagement.tsx
git commit -m "feat(gpu-power): add admin UI card on Power Management page"
```

---

## Task 15: Final Validation

- [ ] **Step 1: Run the full backend test suite**

```bash
cd backend
python -m pytest tests/services/power/gpu/ tests/api/test_gpu_power_routes.py -v
```

Expected: All tests pass.

- [ ] **Step 2: Run the wider test suite to check for regressions**

```bash
cd backend
python -m pytest -q
```

Expected: No new failures vs. baseline (pre-feature).

- [ ] **Step 3: Frontend build**

```bash
cd client
npm run build
```

Expected: clean build.

- [ ] **Step 4: Verify route registration**

```bash
cd backend
python -c "from app.main import app; routes = [r.path for r in app.routes if hasattr(r, 'path') and 'gpu-power' in r.path]; print('\n'.join(routes))"
```

Expected: lists `/api/gpu-power/status`, `/api/gpu-power/config`, `/api/gpu-power/capabilities`, `/api/gpu-power/demand`, `/api/gpu-power/demand/{source}`, `/api/gpu-power/history`.

- [ ] **Step 5: Manual UI smoke test**

Start `python start_dev.py`, log in, expand the GPU Power Management card, toggle enabled, save, reload — settings should persist. Click through Thresholds and Hardware overrides accordions. No console errors.

- [ ] **Step 6: Final commit (if anything was tweaked)**

If any minor adjustments were needed during validation:

```bash
git add -A
git commit -m "chore(gpu-power): final validation tweaks"
```

---

## Self-Review Notes

**Spec coverage check:**
- 3-state machine → Task 9
- AMD backend (sysfs) → Task 5
- NVIDIA backend (nvidia-smi) → Task 6
- Dev backend → Task 3
- Display detector → Task 4
- Demand API → Task 9 + Task 10
- Plugin event hook → Task 7
- Per-state, per-vendor config → Task 1 + Task 9 + Task 14
- Capabilities endpoint → Task 10
- Routes (status/config/capabilities/demand/history) → Task 10
- DB log + JSON config singleton → Task 2 + Task 8
- Lifespan integration → Task 11
- Service status registration → Task 12
- Admin UI → Tasks 13 + 14
- Disabled by default → Task 1 (`enabled: bool = False`) + opt-in via UI

**Type consistency:**
- `GpuPowerState` enum values match between Python (`active/standby/deep_idle`) and TS.
- `apply_state()` signature `(state, config) -> Tuple[bool, Optional[str]]` consistent across protocol, dev, AMD, NVIDIA.
- `register_demand` returns `str` (the source) in the manager and is wrapped to `{source, success}` in the route.

**No-placeholder check:** No "TBD"/"add error handling"/"similar to Task N" — every step has full code.
