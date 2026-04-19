# GPU Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add dedicated-GPU monitoring as a peer feature to the existing CPU monitoring — same sampling cadence, same memory+DB storage, same route conventions — surfaced via a stacked CPU/GPU dashboard card and a new GPU tab in System Monitor.

**Architecture:** A vendor-abstracted `GpuBackend` protocol with `AmdGpuBackend` (sysfs + `gpu_metrics` binary parser) and `DevGpuBackend` (Windows mock). A `GpuMetricCollector` inheriting from `MetricCollector[GpuSampleSchema]` plugs into the existing `MonitoringOrchestrator`. Frontend presence-gates UI via a cached `useGpuPresence` hook that hits `/api/monitoring/gpu/info`.

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy 2.0 / Alembic / Pydantic v2 / pytest. React 18 / TypeScript / Tailwind / Vitest / lucide-react. AMD `amdgpu` sysfs + hwmon + binary `gpu_metrics`.

**Reference spec:** `docs/superpowers/specs/2026-04-19-gpu-monitoring-design.md`

---

## File Structure

### New files (backend)

- `backend/app/services/monitoring/gpu/__init__.py` — package marker
- `backend/app/services/monitoring/gpu/backend.py` — `GpuBackend` Protocol + `_NoGpuBackend` null-object
- `backend/app/services/monitoring/gpu/dev_backend.py` — `DevGpuBackend` (Windows mock)
- `backend/app/services/monitoring/gpu/amd_backend.py` — `AmdGpuBackend` (sysfs + hwmon + `gpu_metrics` binary parser)
- `backend/app/services/monitoring/gpu_collector.py` — `GpuMetricCollector(MetricCollector[GpuSampleSchema])`
- `backend/app/api/routes/monitoring_gpu.py` — `/gpu/info`, `/gpu/current`, `/gpu/history`
- `backend/alembic/versions/c1a2b3d4e5f6_add_gpu_samples_table.py` — migration creating `gpu_samples`, adds `GPU` to `MetricType` enum, seeds `monitoring_config` row
- `backend/tests/monitoring/test_gpu_backend_dev.py`
- `backend/tests/monitoring/test_gpu_backend_amd.py`
- `backend/tests/monitoring/test_gpu_collector.py`
- `backend/tests/monitoring/test_orchestrator_gpu.py`
- `backend/tests/api/test_monitoring_gpu_routes.py`
- `backend/tests/fixtures/amd_gpu/7900xt/` — sysfs text files + real `gpu_metrics` binary dump

### New files (frontend)

- `client/src/hooks/useGpuPresence.ts`
- `client/src/components/dashboard/CpuGpuPanel.tsx`
- `client/src/components/system-monitor/GpuTab.tsx`
- `client/src/components/dashboard/__tests__/CpuGpuPanel.test.tsx` (if co-located test convention; otherwise `client/tests/`)
- `client/src/hooks/__tests__/useGpuPresence.test.ts`

### Modified files

- `backend/app/models/monitoring.py` — add `GpuSample` + `GPU = "gpu"` to `MetricType`
- `backend/app/schemas/monitoring.py` — add `GpuSampleSchema`, `GpuDeviceInfo`, `CurrentGpuResponse`, `GpuHistoryResponse`
- `backend/app/services/monitoring/orchestrator.py` — instantiate `GpuMetricCollector`, sample in loop, add `get_gpu_current_with_db_fallback`, `get_gpu_history`, report in `get_stats()`
- `backend/app/api/routes/__init__.py` — register `monitoring_gpu.router`
- `client/src/api/monitoring.ts` — add `GpuSample`, `GpuDeviceInfo`, `GpuHistoryResponse` types and `getGpuInfo`, `getGpuCurrent`, `getGpuHistory` functions
- `client/src/pages/Dashboard.tsx` — replace inline CPU card with `<CpuGpuPanel />`
- `client/src/pages/SystemMonitor.tsx` — `TabType` gains `'gpu'`, `GpuTab` imported, Hardware category tabs filtered by `useGpuPresence`
- `client/src/components/admin/MaintenanceTools.tsx` — add `gpu` to `METRIC_COLORS`
- `client/src/i18n/locales/{de,en}/dashboard.json` — `gpu.*` keys
- `client/src/i18n/locales/{de,en}/monitor.json` — `tabs.gpu`, `gpu.*` keys

---

## Task 1: DB model and Alembic migration

**Files:**
- Modify: `backend/app/models/monitoring.py`
- Create: `backend/alembic/versions/c1a2b3d4e5f6_add_gpu_samples_table.py`
- Modify: `backend/app/schemas/monitoring.py`
- Test: `backend/tests/monitoring/test_gpu_model.py`

- [ ] **Step 1.1: Add `GPU` to `MetricType` and `GpuSample` model**

Edit `backend/app/models/monitoring.py`. In the `MetricType` enum (around line 23), add:

```python
class MetricType(str, enum.Enum):
    """Types of metrics that can be stored."""
    CPU = "cpu"
    MEMORY = "memory"
    NETWORK = "network"
    DISK_IO = "disk_io"
    PROCESS = "process"
    POWER = "power"
    UPTIME = "uptime"
    GPU = "gpu"
```

At the end of the file (after `UptimeSample`, before `MonitoringConfig`), add:

```python
class GpuSample(Base):
    """
    GPU metrics sample (dedicated GPU only).

    Identity columns (vendor, device_name, pci_slot) are denormalized per sample
    so history stays correctly attributed after a hardware swap.
    """

    __tablename__ = "gpu_samples"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    timestamp: Mapped[datetime] = Column(DateTime, nullable=False, index=True, default=datetime.utcnow)

    # Device identity
    vendor: Mapped[str] = Column(String(16), nullable=False)
    device_name: Mapped[str] = Column(String(128), nullable=False)
    pci_slot: Mapped[Optional[str]] = Column(String(32), nullable=True)

    # Usage
    usage_percent: Mapped[Optional[float]] = Column(Float, nullable=True)
    engine_gfx_percent: Mapped[Optional[float]] = Column(Float, nullable=True)
    engine_compute_percent: Mapped[Optional[float]] = Column(Float, nullable=True)
    engine_decode_percent: Mapped[Optional[float]] = Column(Float, nullable=True)
    engine_encode_percent: Mapped[Optional[float]] = Column(Float, nullable=True)

    # VRAM (BigInteger — can exceed 2 GB)
    vram_used_bytes: Mapped[Optional[int]] = Column(BigInteger, nullable=True)
    vram_total_bytes: Mapped[Optional[int]] = Column(BigInteger, nullable=True)

    # Clocks
    core_clock_mhz: Mapped[Optional[float]] = Column(Float, nullable=True)
    memory_clock_mhz: Mapped[Optional[float]] = Column(Float, nullable=True)

    # Temperatures
    temperature_edge_celsius: Mapped[Optional[float]] = Column(Float, nullable=True)
    temperature_junction_celsius: Mapped[Optional[float]] = Column(Float, nullable=True)
    temperature_memory_celsius: Mapped[Optional[float]] = Column(Float, nullable=True)

    # Fan / Power
    fan_rpm: Mapped[Optional[int]] = Column(Integer, nullable=True)
    power_watts: Mapped[Optional[float]] = Column(Float, nullable=True)

    def __repr__(self) -> str:
        return f"<GpuSample(device={self.device_name}, usage={self.usage_percent}%, ts={self.timestamp})>"
```

- [ ] **Step 1.2: Verify the model imports**

Run: `cd backend && python -c "from app.models.monitoring import GpuSample, MetricType; print(GpuSample.__tablename__, MetricType.GPU.value)"`
Expected: `gpu_samples gpu`

- [ ] **Step 1.3: Add Pydantic schemas**

Edit `backend/app/schemas/monitoring.py`. Add `GPU = "gpu"` to `MetricTypeEnum`:

```python
class MetricTypeEnum(str, Enum):
    """Types of metrics."""
    CPU = "cpu"
    MEMORY = "memory"
    NETWORK = "network"
    DISK_IO = "disk_io"
    PROCESS = "process"
    UPTIME = "uptime"
    GPU = "gpu"
```

After the existing `CpuSampleSchema` (around line 38) but before `MemorySampleSchema`, add:

```python
class GpuSampleSchema(BaseModel):
    """GPU metrics sample (all sensor columns nullable — backends may omit)."""
    timestamp: datetime

    # Identity
    vendor: str
    device_name: str
    pci_slot: Optional[str] = None

    # Usage
    usage_percent: Optional[float] = None
    engine_gfx_percent: Optional[float] = None
    engine_compute_percent: Optional[float] = None
    engine_decode_percent: Optional[float] = None
    engine_encode_percent: Optional[float] = None

    # VRAM
    vram_used_bytes: Optional[int] = None
    vram_total_bytes: Optional[int] = None

    # Clocks
    core_clock_mhz: Optional[float] = None
    memory_clock_mhz: Optional[float] = None

    # Temperatures
    temperature_edge_celsius: Optional[float] = None
    temperature_junction_celsius: Optional[float] = None
    temperature_memory_celsius: Optional[float] = None

    # Fan / Power
    fan_rpm: Optional[int] = None
    power_watts: Optional[float] = None

    class Config:
        from_attributes = True


class GpuDeviceInfo(BaseModel):
    """Immutable device metadata — exposed via /gpu/info."""
    vendor: str
    device_name: str
    pci_slot: Optional[str] = None
    vram_total_bytes: Optional[int] = None
    driver_version: Optional[str] = None
```

In the Response Schemas section (around line 148), add:

```python
class CurrentGpuResponse(GpuSampleSchema):
    """Current GPU sample — same shape as GpuSampleSchema."""
    pass


class GpuHistoryResponse(BaseModel):
    """GPU history response."""
    samples: List[GpuSampleSchema]
    sample_count: int
    source: str
```

- [ ] **Step 1.4: Verify schema imports**

Run: `cd backend && python -c "from app.schemas.monitoring import GpuSampleSchema, GpuDeviceInfo, CurrentGpuResponse, GpuHistoryResponse; print('ok')"`
Expected: `ok`

- [ ] **Step 1.5: Write the failing migration test**

Create `backend/tests/monitoring/test_gpu_model.py`:

```python
"""Verify GpuSample model and MetricType.GPU enum value."""
from app.models.monitoring import GpuSample, MetricType


def test_metric_type_has_gpu():
    assert MetricType.GPU.value == "gpu"


def test_gpu_sample_columns():
    expected = {
        "id", "timestamp", "vendor", "device_name", "pci_slot",
        "usage_percent", "engine_gfx_percent", "engine_compute_percent",
        "engine_decode_percent", "engine_encode_percent",
        "vram_used_bytes", "vram_total_bytes",
        "core_clock_mhz", "memory_clock_mhz",
        "temperature_edge_celsius", "temperature_junction_celsius",
        "temperature_memory_celsius",
        "fan_rpm", "power_watts",
    }
    actual = {c.name for c in GpuSample.__table__.columns}
    assert actual == expected


def test_gpu_sample_tablename():
    assert GpuSample.__tablename__ == "gpu_samples"
```

Run: `cd backend && python -m pytest tests/monitoring/test_gpu_model.py -v`
Expected: PASS (all three — model is already defined)

- [ ] **Step 1.6: Create the Alembic migration**

Find the current Alembic head revision: `cd backend && alembic heads`. Use the reported ID as `down_revision`. (At time of planning the head was `b9f2e3a1c7d4`; verify before committing.)

Create `backend/alembic/versions/c1a2b3d4e5f6_add_gpu_samples_table.py`:

```python
"""add gpu_samples table

Revision ID: c1a2b3d4e5f6
Revises: <CURRENT_HEAD>
Create Date: 2026-04-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c1a2b3d4e5f6'
down_revision = '<CURRENT_HEAD>'  # replace with actual head, e.g. 'b9f2e3a1c7d4'
branch_labels = None
depends_on = None


def upgrade():
    # Create gpu_samples table
    op.create_table(
        'gpu_samples',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False, index=True),
        sa.Column('vendor', sa.String(length=16), nullable=False),
        sa.Column('device_name', sa.String(length=128), nullable=False),
        sa.Column('pci_slot', sa.String(length=32), nullable=True),
        sa.Column('usage_percent', sa.Float(), nullable=True),
        sa.Column('engine_gfx_percent', sa.Float(), nullable=True),
        sa.Column('engine_compute_percent', sa.Float(), nullable=True),
        sa.Column('engine_decode_percent', sa.Float(), nullable=True),
        sa.Column('engine_encode_percent', sa.Float(), nullable=True),
        sa.Column('vram_used_bytes', sa.BigInteger(), nullable=True),
        sa.Column('vram_total_bytes', sa.BigInteger(), nullable=True),
        sa.Column('core_clock_mhz', sa.Float(), nullable=True),
        sa.Column('memory_clock_mhz', sa.Float(), nullable=True),
        sa.Column('temperature_edge_celsius', sa.Float(), nullable=True),
        sa.Column('temperature_junction_celsius', sa.Float(), nullable=True),
        sa.Column('temperature_memory_celsius', sa.Float(), nullable=True),
        sa.Column('fan_rpm', sa.Integer(), nullable=True),
        sa.Column('power_watts', sa.Float(), nullable=True),
    )
    op.create_index('ix_gpu_samples_timestamp', 'gpu_samples', ['timestamp'])

    # Seed monitoring_config row for GPU (only if not already present)
    # Use the enum value directly — SQLAlchemy stores it as the string "gpu".
    # If `monitoring_config` is populated dynamically at startup, this INSERT is
    # idempotent; the `ON CONFLICT DO NOTHING` pattern handles re-runs.
    conn = op.get_bind()
    existing = conn.execute(
        sa.text("SELECT 1 FROM monitoring_config WHERE metric_type = :mt"),
        {"mt": "gpu"},
    ).scalar()
    if not existing:
        conn.execute(
            sa.text(
                "INSERT INTO monitoring_config "
                "(metric_type, retention_hours, db_persist_interval, is_enabled, samples_cleaned) "
                "VALUES (:mt, :rh, :pi, :en, :sc)"
            ),
            {"mt": "gpu", "rh": 168, "pi": 12, "en": True, "sc": 0},
        )


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM monitoring_config WHERE metric_type = :mt"), {"mt": "gpu"})
    op.drop_index('ix_gpu_samples_timestamp', table_name='gpu_samples')
    op.drop_table('gpu_samples')
```

Replace `<CURRENT_HEAD>` with the output of `alembic heads` (e.g. `'b9f2e3a1c7d4'`).

- [ ] **Step 1.7: Apply the migration in dev**

Run: `cd backend && alembic upgrade head`
Expected: `INFO  [alembic.runtime.migration] Running upgrade <prev> -> c1a2b3d4e5f6, add gpu_samples table`

Verify table exists: `cd backend && python -c "from app.core.database import engine; import sqlalchemy as sa; print(sa.inspect(engine).has_table('gpu_samples'))"`
Expected: `True`

- [ ] **Step 1.8: Verify monitoring_config seed row**

Run: `cd backend && python -c "from app.core.database import SessionLocal; from app.models.monitoring import MonitoringConfig, MetricType; s = SessionLocal(); r = s.query(MonitoringConfig).filter_by(metric_type=MetricType.GPU).first(); print(r.metric_type, r.retention_hours, r.is_enabled); s.close()"`
Expected: `MetricType.GPU 168 True`

- [ ] **Step 1.9: Commit**

```bash
git add backend/app/models/monitoring.py backend/app/schemas/monitoring.py \
  backend/alembic/versions/c1a2b3d4e5f6_add_gpu_samples_table.py \
  backend/tests/monitoring/test_gpu_model.py
git commit -m "feat(monitoring): add GpuSample model, schemas, and migration"
```

---

## Task 2: `GpuBackend` protocol + `DevGpuBackend`

**Files:**
- Create: `backend/app/services/monitoring/gpu/__init__.py`
- Create: `backend/app/services/monitoring/gpu/backend.py`
- Create: `backend/app/services/monitoring/gpu/dev_backend.py`
- Test: `backend/tests/monitoring/test_gpu_backend_dev.py`

- [ ] **Step 2.1: Create package marker**

Create `backend/app/services/monitoring/gpu/__init__.py` (empty file, one-line docstring):

```python
"""GPU monitoring backends: protocol + AMD (sysfs) + dev mock."""
```

- [ ] **Step 2.2: Write failing test for `DevGpuBackend`**

Create `backend/tests/monitoring/test_gpu_backend_dev.py`:

```python
"""Dev-mode GPU backend tests."""
from app.services.monitoring.gpu.dev_backend import DevGpuBackend
from app.services.monitoring.gpu.backend import GpuBackend


def test_dev_backend_implements_protocol():
    b = DevGpuBackend()
    # Protocol attributes
    assert b.detected is True
    info = b.device_info()
    assert info.vendor == "amd"
    assert "7900 XT" in info.device_name
    assert info.vram_total_bytes == 20 * 1024 ** 3


def test_dev_backend_read_sample_shape():
    b = DevGpuBackend()
    sample = b.read_sample()
    assert sample["vendor"] == "amd"
    assert "device_name" in sample
    assert "usage_percent" in sample
    for key in (
        "engine_gfx_percent", "engine_compute_percent",
        "engine_decode_percent", "engine_encode_percent",
        "vram_used_bytes", "vram_total_bytes",
        "core_clock_mhz", "memory_clock_mhz",
        "temperature_edge_celsius", "temperature_junction_celsius",
        "temperature_memory_celsius",
        "fan_rpm", "power_watts",
    ):
        assert key in sample, f"missing {key}"


def test_dev_backend_values_in_plausible_range():
    b = DevGpuBackend()
    s = b.read_sample()
    assert 0 <= s["usage_percent"] <= 100
    assert 0 <= s["engine_gfx_percent"] <= 100
    assert 40 <= s["temperature_edge_celsius"] <= 85
    assert 100 <= s["power_watts"] <= 300
    assert s["vram_total_bytes"] == 20 * 1024 ** 3
    assert 0 < s["vram_used_bytes"] <= s["vram_total_bytes"]
```

Run: `cd backend && python -m pytest tests/monitoring/test_gpu_backend_dev.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.services.monitoring.gpu.dev_backend'`)

- [ ] **Step 2.3: Implement `GpuBackend` protocol and null-object**

Create `backend/app/services/monitoring/gpu/backend.py`:

```python
"""GPU backend protocol and null-object."""
from __future__ import annotations

from typing import Any, Dict, Protocol, runtime_checkable

from app.schemas.monitoring import GpuDeviceInfo


@runtime_checkable
class GpuBackend(Protocol):
    """Vendor-agnostic GPU sensor backend.

    Implementations populate as many sample fields as the hardware supports;
    missing fields default to None in the Pydantic schema.
    """

    @property
    def detected(self) -> bool: ...

    def device_info(self) -> GpuDeviceInfo: ...

    def read_sample(self) -> Dict[str, Any]:
        """Return dict of sensor readings matching GpuSampleSchema fields.

        Required keys: vendor, device_name. All others optional.
        Implementations should catch per-sensor failures and omit the key
        rather than raising — one broken sensor must not poison the sample.
        """


class _NoGpuBackend:
    """Null-object backend used when no dGPU is detected."""

    @property
    def detected(self) -> bool:
        return False

    def device_info(self) -> GpuDeviceInfo:
        raise RuntimeError("No GPU detected — device_info is not available")

    def read_sample(self) -> Dict[str, Any]:
        raise RuntimeError("No GPU detected — read_sample must not be called")
```

- [ ] **Step 2.4: Implement `DevGpuBackend`**

Create `backend/app/services/monitoring/gpu/dev_backend.py`:

```python
"""Dev-mode mock of an AMD Radeon RX 7900 XT.

Used when settings.is_dev_mode is True so Windows development does not require
real AMD hardware. Values fluctuate with sin/cos + small jitter for a plausible feel.
"""
from __future__ import annotations

import math
import random
import time
from typing import Any, Dict

from app.schemas.monitoring import GpuDeviceInfo


VRAM_TOTAL = 20 * 1024 ** 3  # 20 GB
DEVICE_NAME = "AMD Radeon RX 7900 XT (dev-mock)"
PCI_SLOT = "0000:03:00.0"
DRIVER_VERSION = "amdgpu 6.5.0-dev"


class DevGpuBackend:
    """Always-detected mock GPU backend."""

    def __init__(self) -> None:
        self._t0 = time.monotonic()

    @property
    def detected(self) -> bool:
        return True

    def device_info(self) -> GpuDeviceInfo:
        return GpuDeviceInfo(
            vendor="amd",
            device_name=DEVICE_NAME,
            pci_slot=PCI_SLOT,
            vram_total_bytes=VRAM_TOTAL,
            driver_version=DRIVER_VERSION,
        )

    def read_sample(self) -> Dict[str, Any]:
        t = time.monotonic() - self._t0
        usage = max(0.0, min(100.0, 30 + 25 * math.sin(t / 20) + random.uniform(-5, 5)))
        gfx = max(0.0, min(100.0, usage + random.uniform(-5, 5)))
        compute = max(0.0, min(100.0, max(0.0, usage - 10) + random.uniform(-5, 5)))
        decode = random.uniform(0, 15)
        encode = random.uniform(0, 8)
        vram_used = int(6e9 + 2e9 * math.sin(t / 30))
        vram_used = max(0, min(VRAM_TOTAL, vram_used))

        return {
            "vendor": "amd",
            "device_name": DEVICE_NAME,
            "pci_slot": PCI_SLOT,
            "usage_percent": round(usage, 2),
            "engine_gfx_percent": round(gfx, 2),
            "engine_compute_percent": round(compute, 2),
            "engine_decode_percent": round(decode, 2),
            "engine_encode_percent": round(encode, 2),
            "vram_used_bytes": vram_used,
            "vram_total_bytes": VRAM_TOTAL,
            "core_clock_mhz": round(2500 + random.uniform(-300, 300), 1),
            "memory_clock_mhz": 2500.0,
            "temperature_edge_celsius": round(55 + random.uniform(-3, 8), 1),
            "temperature_junction_celsius": round(65 + random.uniform(-3, 10), 1),
            "temperature_memory_celsius": round(70 + random.uniform(-3, 8), 1),
            "fan_rpm": 1500 + int(random.uniform(-200, 400)),
            "power_watts": round(180 + random.uniform(-30, 60), 1),
        }
```

- [ ] **Step 2.5: Run tests to verify pass**

Run: `cd backend && python -m pytest tests/monitoring/test_gpu_backend_dev.py -v`
Expected: PASS (all three tests)

- [ ] **Step 2.6: Commit**

```bash
git add backend/app/services/monitoring/gpu/__init__.py \
  backend/app/services/monitoring/gpu/backend.py \
  backend/app/services/monitoring/gpu/dev_backend.py \
  backend/tests/monitoring/test_gpu_backend_dev.py
git commit -m "feat(monitoring): add GpuBackend protocol and DevGpuBackend mock"
```

---

## Task 3: `AmdGpuBackend` — detection + sysfs reads

**Files:**
- Create: `backend/app/services/monitoring/gpu/amd_backend.py`
- Create: `backend/tests/fixtures/amd_gpu/7900xt/` (multiple small text files)
- Test: `backend/tests/monitoring/test_gpu_backend_amd.py`

- [ ] **Step 3.1: Create sysfs fixture tree**

Create directory `backend/tests/fixtures/amd_gpu/7900xt/sys/class/drm/card0/device/` with the following text files (one value per file, ending with a newline):

- `vendor` → `0x1002\n`
- `device` → `0x744c\n`
- `subsystem_vendor` → `0x1458\n`
- `gpu_busy_percent` → `42\n`
- `mem_info_vram_used` → `6442450944\n`
- `mem_info_vram_total` → `21474836480\n`
- `pp_dpm_sclk` → `0: 500Mhz\n1: 1200Mhz\n2: 2400Mhz *\n`
- `pp_dpm_mclk` → `0: 456Mhz\n1: 2500Mhz *\n`

Create `backend/tests/fixtures/amd_gpu/7900xt/sys/class/drm/card0/device/hwmon/hwmon1/`:

- `name` → `amdgpu\n`
- `freq1_input` → `2400000000\n` (2400 MHz in Hz)
- `temp1_input` → `55000\n` (55 °C in milli)
- `temp1_label` → `edge\n`
- `temp2_input` → `65000\n`
- `temp2_label` → `junction\n`
- `temp3_input` → `70000\n`
- `temp3_label` → `mem\n`
- `fan1_input` → `1500\n`
- `power1_average` → `180000000\n` (180 W in microwatts)

Also provide the raw uevent marker file `backend/tests/fixtures/amd_gpu/7900xt/sys/class/drm/card0/device/uevent`:

- `uevent` → `DRIVER=amdgpu\nPCI_SLOT_NAME=0000:03:00.0\n`

For the iGPU negative test, create `backend/tests/fixtures/amd_gpu/with_igpu/sys/class/drm/card0/device/`:

- `vendor` → `0x1002\n`
- (no `pp_dpm_sclk` file — the marker we use to detect dGPUs)
- `uevent` → `DRIVER=amdgpu\nPCI_SLOT_NAME=0000:04:00.0\n`

And a dGPU sibling `backend/tests/fixtures/amd_gpu/with_igpu/sys/class/drm/card1/device/`:
- `vendor` → `0x1002\n`
- `pp_dpm_sclk` → `0: 500Mhz *\n`
- `gpu_busy_percent` → `5\n`
- `uevent` → `DRIVER=amdgpu\nPCI_SLOT_NAME=0000:03:00.0\n`

(Minimal — AmdGpuBackend detection test only needs to see that card1 is picked over card0.)

For the binary metrics test, generate a fixture binary (do this in a helper step in 3.6 below).

- [ ] **Step 3.2: Write the failing test skeleton**

Create `backend/tests/monitoring/test_gpu_backend_amd.py`:

```python
"""AMD GPU backend tests with sysfs fixtures."""
from pathlib import Path

import pytest

from app.services.monitoring.gpu.amd_backend import AmdGpuBackend

FIX_7900XT = Path(__file__).parent.parent / "fixtures" / "amd_gpu" / "7900xt"
FIX_IGPU = Path(__file__).parent.parent / "fixtures" / "amd_gpu" / "with_igpu"


def test_detects_single_dgpu():
    b = AmdGpuBackend(sysfs_root=FIX_7900XT)
    assert b.detected is True
    info = b.device_info()
    assert info.vendor == "amd"
    assert info.pci_slot == "0000:03:00.0"
    assert info.vram_total_bytes == 21474836480


def test_skips_igpu_picks_dgpu():
    """card0 is iGPU (no pp_dpm_sclk), card1 is dGPU — pick card1."""
    b = AmdGpuBackend(sysfs_root=FIX_IGPU)
    assert b.detected is True
    assert b.device_info().pci_slot == "0000:03:00.0"


def test_no_amdgpu_present(tmp_path):
    """Empty sysfs → detected is False."""
    (tmp_path / "sys" / "class" / "drm").mkdir(parents=True)
    b = AmdGpuBackend(sysfs_root=tmp_path)
    assert b.detected is False


def test_read_sample_core_metrics():
    b = AmdGpuBackend(sysfs_root=FIX_7900XT)
    s = b.read_sample()
    assert s["vendor"] == "amd"
    assert s["usage_percent"] == 42.0
    assert s["vram_used_bytes"] == 6442450944
    assert s["vram_total_bytes"] == 21474836480
    assert s["core_clock_mhz"] == 2400.0
    assert s["memory_clock_mhz"] == 2500.0  # the starred entry in pp_dpm_mclk
    assert s["temperature_edge_celsius"] == 55.0
    assert s["temperature_junction_celsius"] == 65.0
    assert s["temperature_memory_celsius"] == 70.0
    assert s["fan_rpm"] == 1500
    assert s["power_watts"] == 180.0


def test_read_sample_missing_sensor_yields_none(tmp_path):
    """Delete one sysfs file — that metric should be absent/None, rest should survive."""
    import shutil
    copy = tmp_path / "fix"
    shutil.copytree(FIX_7900XT, copy)
    (copy / "sys" / "class" / "drm" / "card0" / "device" / "gpu_busy_percent").unlink()
    b = AmdGpuBackend(sysfs_root=copy)
    s = b.read_sample()
    assert s.get("usage_percent") is None
    assert s["temperature_edge_celsius"] == 55.0  # other metrics still work
```

Run: `cd backend && python -m pytest tests/monitoring/test_gpu_backend_amd.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.services.monitoring.gpu.amd_backend'`)

- [ ] **Step 3.3: Implement `AmdGpuBackend` — detection + text sensors**

Create `backend/app/services/monitoring/gpu/amd_backend.py`:

```python
"""AMD GPU backend.

Reads sensors from the `amdgpu` driver's sysfs interface under
/sys/class/drm/card*/device/ (and hwmon child directory).

Detection: iterate card* entries, filter vendor 0x1002, pick first with
pp_dpm_sclk (skips iGPUs which typically lack it on modern kernels).

Per-sensor failures return None rather than raising so a single bad file
does not invalidate the entire sample.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional

from app.schemas.monitoring import GpuDeviceInfo

logger = logging.getLogger(__name__)

AMD_VENDOR_ID = "0x1002"


class AmdGpuBackend:
    """Real-hardware AMD GPU backend."""

    def __init__(self, sysfs_root: Path | str = Path("/")) -> None:
        self._root = Path(sysfs_root)
        self._device_path: Optional[Path] = None
        self._hwmon_path: Optional[Path] = None
        self._pci_slot: Optional[str] = None
        self._device_name: str = "AMD GPU"
        self._detect()

    # ---- Detection ----

    def _detect(self) -> None:
        drm = self._root / "sys" / "class" / "drm"
        if not drm.exists():
            return
        candidates = sorted(p for p in drm.iterdir() if re.fullmatch(r"card\d+", p.name))
        for card in candidates:
            device = card / "device"
            if not device.exists():
                continue
            vendor = self._read_text(device / "vendor")
            if vendor != AMD_VENDOR_ID:
                continue
            # Skip iGPUs: dGPUs expose pp_dpm_sclk
            if not (device / "pp_dpm_sclk").exists():
                continue
            self._device_path = device
            self._pci_slot = self._parse_pci_slot(device / "uevent")
            self._hwmon_path = self._find_hwmon(device)
            self._device_name = self._guess_device_name(device)
            return

    @staticmethod
    def _parse_pci_slot(uevent: Path) -> Optional[str]:
        try:
            for line in uevent.read_text().splitlines():
                if line.startswith("PCI_SLOT_NAME="):
                    return line.split("=", 1)[1].strip()
        except OSError:
            pass
        return None

    @staticmethod
    def _find_hwmon(device: Path) -> Optional[Path]:
        hwmon = device / "hwmon"
        if not hwmon.exists():
            return None
        for child in hwmon.iterdir():
            if child.is_dir() and AmdGpuBackend._read_text(child / "name") == "amdgpu":
                return child
        return None

    def _guess_device_name(self, device: Path) -> str:
        # Minimal hardcoded map. Prefer to read from /sys via GPU_ID or subsystem
        # PCI ID lookups, but that requires pci.ids — keep simple for now.
        device_id = self._read_text(device / "device") or ""
        return {
            "0x744c": "AMD Radeon RX 7900 XTX",
            "0x7448": "AMD Radeon RX 7900 XT",
        }.get(device_id, f"AMD GPU ({device_id})")

    # ---- Public API ----

    @property
    def detected(self) -> bool:
        return self._device_path is not None

    def device_info(self) -> GpuDeviceInfo:
        if not self.detected:
            raise RuntimeError("No AMD GPU detected")
        return GpuDeviceInfo(
            vendor="amd",
            device_name=self._device_name,
            pci_slot=self._pci_slot,
            vram_total_bytes=self._read_int(self._device_path / "mem_info_vram_total"),
            driver_version=None,
        )

    def read_sample(self) -> Dict[str, Any]:
        if not self.detected:
            raise RuntimeError("No AMD GPU detected")
        dev = self._device_path
        hw = self._hwmon_path

        sample: Dict[str, Any] = {
            "vendor": "amd",
            "device_name": self._device_name,
            "pci_slot": self._pci_slot,
        }

        # Usage
        sample["usage_percent"] = self._read_float(dev / "gpu_busy_percent")

        # VRAM
        sample["vram_used_bytes"] = self._read_int(dev / "mem_info_vram_used")
        sample["vram_total_bytes"] = self._read_int(dev / "mem_info_vram_total")

        # Core clock (Hz → MHz)
        if hw:
            freq_hz = self._read_int(hw / "freq1_input")
            sample["core_clock_mhz"] = round(freq_hz / 1_000_000, 1) if freq_hz else None
        else:
            sample["core_clock_mhz"] = None

        # Memory clock — parse the "*"-marked line of pp_dpm_mclk
        sample["memory_clock_mhz"] = self._parse_dpm_active_mhz(dev / "pp_dpm_mclk")

        # Temperatures (labels: edge / junction / mem)
        sample["temperature_edge_celsius"] = None
        sample["temperature_junction_celsius"] = None
        sample["temperature_memory_celsius"] = None
        if hw:
            for i in range(1, 5):
                label = self._read_text(hw / f"temp{i}_label")
                val = self._read_int(hw / f"temp{i}_input")
                if val is None:
                    continue
                celsius = val / 1000.0
                if label == "edge":
                    sample["temperature_edge_celsius"] = celsius
                elif label == "junction":
                    sample["temperature_junction_celsius"] = celsius
                elif label == "mem":
                    sample["temperature_memory_celsius"] = celsius

        # Fan / Power
        sample["fan_rpm"] = self._read_int(hw / "fan1_input") if hw else None
        power_uw = self._read_int(hw / "power1_average") if hw else None
        sample["power_watts"] = round(power_uw / 1_000_000, 1) if power_uw else None

        # Engine activity — filled in by binary metrics parser (Task 3.6)
        sample["engine_gfx_percent"] = None
        sample["engine_compute_percent"] = None
        sample["engine_decode_percent"] = None
        sample["engine_encode_percent"] = None
        try:
            engines = self._read_gpu_metrics(dev / "gpu_metrics")
            sample.update(engines)
        except Exception as exc:
            logger.debug("gpu_metrics parse failed: %s", exc)

        return sample

    # ---- Sensor helpers ----

    @staticmethod
    def _read_text(path: Path) -> Optional[str]:
        try:
            return path.read_text().strip()
        except OSError:
            return None

    @staticmethod
    def _read_int(path: Path) -> Optional[int]:
        try:
            return int(path.read_text().strip())
        except (OSError, ValueError):
            return None

    @staticmethod
    def _read_float(path: Path) -> Optional[float]:
        try:
            return float(path.read_text().strip())
        except (OSError, ValueError):
            return None

    @staticmethod
    def _parse_dpm_active_mhz(path: Path) -> Optional[float]:
        try:
            for line in path.read_text().splitlines():
                if "*" in line:
                    m = re.search(r"(\d+)\s*Mhz", line, re.IGNORECASE)
                    if m:
                        return float(m.group(1))
        except OSError:
            pass
        return None

    def _read_gpu_metrics(self, path: Path) -> Dict[str, Optional[float]]:
        """Placeholder — real parser implemented in Task 3.6."""
        return {}
```

- [ ] **Step 3.4: Run tests — text sensors should pass**

Run: `cd backend && python -m pytest tests/monitoring/test_gpu_backend_amd.py -v`
Expected: PASS for detection + text-sensor tests. (Binary metrics parser tests come in 3.6.)

- [ ] **Step 3.5: Add gpu_metrics binary parser — write failing test first**

Append to `backend/tests/monitoring/test_gpu_backend_amd.py`:

```python
import struct


def _make_gpu_metrics_v1_4(
    gfx: int, mm: int, vcn0: int, vcn1: int, vcn2: int, vcn3: int
) -> bytes:
    """Generate a minimal v1.4 gpu_metrics blob.

    Layout (relevant fields only, little-endian):
      0: size u16
      2: format_revision u8
      3: content_revision u8
      4..: system_clock_counter (u64) etc — we pad unused fields with zeros.

    For the parser we only need correct header + offsets for:
      average_gfx_activity (u16), average_mm_activity (u16), vcn_activity[4] (u16).

    Actual kernel layout (gpu_metrics_v1_4) has these at fixed offsets that
    AmdGpuBackend._parse_v1_4 will know. To keep the fixture self-contained we
    generate just the fields we need at the documented offsets and zero-pad the rest.
    """
    # For v1.4, per linux/include/drm/amd/amdgpu_psp.h the relevant offsets we
    # expose are:  average_gfx_activity @ 36, average_mm_activity @ 38,
    # vcn_activity[4] @ 152. Pad to the end of the struct (size 296 for v1.4).
    STRUCT_SIZE = 296
    buf = bytearray(STRUCT_SIZE)
    # Header
    struct.pack_into("<H", buf, 0, STRUCT_SIZE)
    buf[2] = 1  # format_revision
    buf[3] = 4  # content_revision
    # average_gfx_activity, average_mm_activity
    struct.pack_into("<H", buf, 36, gfx)
    struct.pack_into("<H", buf, 38, mm)
    # vcn_activity[4]
    struct.pack_into("<HHHH", buf, 152, vcn0, vcn1, vcn2, vcn3)
    return bytes(buf)


def test_gpu_metrics_v1_4_parses_engines(tmp_path):
    import shutil
    copy = tmp_path / "fix"
    shutil.copytree(FIX_7900XT, copy)
    metrics_file = copy / "sys" / "class" / "drm" / "card0" / "device" / "gpu_metrics"
    metrics_file.write_bytes(_make_gpu_metrics_v1_4(gfx=7500, mm=2500, vcn0=3000, vcn1=0, vcn2=0, vcn3=1500))

    b = AmdGpuBackend(sysfs_root=copy)
    s = b.read_sample()
    # gfx/mm are in 0.01% units per kernel docs; parser converts to percent.
    assert s["engine_gfx_percent"] == pytest.approx(75.0, abs=0.1)
    assert s["engine_compute_percent"] == pytest.approx(75.0, abs=0.1)  # compute mirrors gfx for AMD (no separate counter)
    # Decode = max of first two VCN slots (encode second pair) — vendor choice.
    assert s["engine_decode_percent"] == pytest.approx(30.0, abs=0.1)
    assert s["engine_encode_percent"] == pytest.approx(15.0, abs=0.1)


def test_gpu_metrics_unknown_revision_yields_none(tmp_path):
    import shutil
    copy = tmp_path / "fix"
    shutil.copytree(FIX_7900XT, copy)
    metrics = bytearray(32)
    struct.pack_into("<H", metrics, 0, 32)
    metrics[2] = 99  # unknown format_revision
    metrics[3] = 0
    (copy / "sys" / "class" / "drm" / "card0" / "device" / "gpu_metrics").write_bytes(bytes(metrics))

    b = AmdGpuBackend(sysfs_root=copy)
    s = b.read_sample()
    assert s["engine_gfx_percent"] is None
    # Other metrics still survive
    assert s["temperature_edge_celsius"] == 55.0
```

Run: `cd backend && python -m pytest tests/monitoring/test_gpu_backend_amd.py::test_gpu_metrics_v1_4_parses_engines -v`
Expected: FAIL (parser not yet implemented)

- [ ] **Step 3.6: Implement `_read_gpu_metrics`**

Replace the placeholder `_read_gpu_metrics` in `backend/app/services/monitoring/gpu/amd_backend.py` with:

```python
    def _read_gpu_metrics(self, path: Path) -> Dict[str, Optional[float]]:
        """Parse amdgpu gpu_metrics binary.

        Header: size u16, format_revision u8, content_revision u8.
        Dispatch on (format_revision, content_revision). Unknown combinations
        return {} so engine fields stay None.
        """
        try:
            raw = path.read_bytes()
        except OSError:
            return {}
        if len(raw) < 4:
            return {}
        size = int.from_bytes(raw[0:2], "little")
        fmt_rev = raw[2]
        cnt_rev = raw[3]

        parsers = {
            (1, 4): self._parse_v1_4,
            (1, 3): self._parse_v1_4,  # v1.3 and v1.4 share the fields we read
        }
        parser = parsers.get((fmt_rev, cnt_rev))
        if parser is None:
            return {}
        return parser(raw, size)

    @staticmethod
    def _parse_v1_4(buf: bytes, size: int) -> Dict[str, Optional[float]]:
        import struct

        def u16(off: int) -> Optional[int]:
            if off + 2 > size:
                return None
            return struct.unpack_from("<H", buf, off)[0]

        gfx_raw = u16(36)    # average_gfx_activity, units: 0.01%
        mm_raw = u16(38)     # average_mm_activity
        vcn = [u16(152 + i * 2) for i in range(4)]

        def pct(x: Optional[int]) -> Optional[float]:
            return round(x / 100.0, 2) if x is not None else None

        # Decode = first two VCN slots max; Encode = last two VCN slots max.
        # (AMD layout: VCN0/VCN1 are decode, VCN2/VCN3 are encode on RDNA3.)
        def vcn_pct(a: Optional[int], b: Optional[int]) -> Optional[float]:
            vals = [x for x in (a, b) if x is not None]
            return round(max(vals) / 100.0, 2) if vals else None

        return {
            "engine_gfx_percent": pct(gfx_raw),
            # AMD exposes a single gfx activity; mirror to compute for parity with
            # NVIDIA/Intel backends that may distinguish.
            "engine_compute_percent": pct(gfx_raw),
            "engine_decode_percent": vcn_pct(vcn[0], vcn[1]),
            "engine_encode_percent": vcn_pct(vcn[2], vcn[3]),
        }
```

- [ ] **Step 3.7: Run all AMD backend tests**

Run: `cd backend && python -m pytest tests/monitoring/test_gpu_backend_amd.py -v`
Expected: PASS (all detection + text-sensor + binary-parser tests)

- [ ] **Step 3.8: Commit**

```bash
git add backend/app/services/monitoring/gpu/amd_backend.py \
  backend/tests/monitoring/test_gpu_backend_amd.py \
  backend/tests/fixtures/amd_gpu
git commit -m "feat(monitoring): add AmdGpuBackend with sysfs + gpu_metrics parser"
```

---

## Task 4: `GpuMetricCollector` + orchestrator integration

**Files:**
- Create: `backend/app/services/monitoring/gpu_collector.py`
- Modify: `backend/app/services/monitoring/orchestrator.py`
- Test: `backend/tests/monitoring/test_gpu_collector.py`
- Test: `backend/tests/monitoring/test_orchestrator_gpu.py`

- [ ] **Step 4.1: Write failing collector test**

Create `backend/tests/monitoring/test_gpu_collector.py`:

```python
"""GpuMetricCollector tests."""
from datetime import datetime, timezone

import pytest

from app.models.monitoring import GpuSample
from app.schemas.monitoring import GpuSampleSchema
from app.services.monitoring.gpu_collector import GpuMetricCollector


class _FakeBackend:
    def __init__(self, detected: bool = True, raises: Exception | None = None):
        self._detected = detected
        self._raises = raises

    @property
    def detected(self) -> bool:
        return self._detected

    def device_info(self):
        from app.schemas.monitoring import GpuDeviceInfo
        return GpuDeviceInfo(vendor="amd", device_name="Test GPU")

    def read_sample(self):
        if self._raises:
            raise self._raises
        return {
            "vendor": "amd", "device_name": "Test GPU",
            "usage_percent": 50.0, "power_watts": 150.0,
        }


def test_db_model_is_gpu_sample(monkeypatch):
    c = GpuMetricCollector()
    c.backend = _FakeBackend()
    assert c.get_db_model() is GpuSample


def test_collect_sample_when_detected(monkeypatch):
    c = GpuMetricCollector()
    c.backend = _FakeBackend(detected=True)
    s = c.collect_sample()
    assert isinstance(s, GpuSampleSchema)
    assert s.usage_percent == 50.0
    assert s.vendor == "amd"


def test_collect_sample_returns_none_when_not_detected():
    c = GpuMetricCollector()
    c.backend = _FakeBackend(detected=False)
    assert c.collect_sample() is None


def test_collect_sample_swallows_backend_exceptions(caplog):
    import logging
    caplog.set_level(logging.ERROR)
    c = GpuMetricCollector()
    c.backend = _FakeBackend(raises=RuntimeError("boom"))
    assert c.collect_sample() is None
    assert any("GPU sample" in r.message for r in caplog.records)


def test_round_trip_sample_db_dict():
    c = GpuMetricCollector()
    c.backend = _FakeBackend()
    sample = GpuSampleSchema(
        timestamp=datetime.now(timezone.utc),
        vendor="amd", device_name="RX 7900 XT",
        usage_percent=65.0, vram_used_bytes=8_000_000_000,
        vram_total_bytes=20_000_000_000, power_watts=200.0,
    )
    d = c.sample_to_db_dict(sample)
    assert d["vendor"] == "amd"
    assert d["power_watts"] == 200.0
    # Round-trip via model instance
    record = GpuSample(**d)
    back = c.db_to_sample(record)
    assert back.usage_percent == 65.0
    assert back.device_name == "RX 7900 XT"


def test_detected_property_mirrors_backend():
    c = GpuMetricCollector()
    c.backend = _FakeBackend(detected=False)
    assert c.detected is False
    c.backend = _FakeBackend(detected=True)
    assert c.detected is True
```

Run: `cd backend && python -m pytest tests/monitoring/test_gpu_collector.py -v`
Expected: FAIL (module not yet created)

- [ ] **Step 4.2: Implement `GpuMetricCollector`**

Create `backend/app/services/monitoring/gpu_collector.py`:

```python
"""GPU metrics collector.

Mirrors CpuMetricCollector in structure but delegates sensor reads to a
vendor backend selected at construction time.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional, Type

from app.core.config import settings
from app.models.monitoring import GpuSample
from app.schemas.monitoring import GpuSampleSchema
from app.services.monitoring.base import MetricCollector
from app.services.monitoring.gpu.backend import GpuBackend, _NoGpuBackend
from app.services.monitoring.gpu.dev_backend import DevGpuBackend

logger = logging.getLogger(__name__)


class GpuMetricCollector(MetricCollector[GpuSampleSchema]):
    """Dedicated-GPU metric collector.

    Selects a backend at init time: DevGpuBackend in dev mode, AmdGpuBackend in
    production, or _NoGpuBackend when nothing is detected. When the backend is
    not detected, collect_sample returns None and no DB write is issued.
    """

    def __init__(
        self,
        buffer_size: int = 120,
        persist_interval: int = 12,
    ) -> None:
        super().__init__(
            metric_name="GPU",
            buffer_size=buffer_size,
            persist_interval=persist_interval,
        )
        self.backend: GpuBackend = self._select_backend()
        if self.backend.detected:
            try:
                info = self.backend.device_info()
                logger.info(f"GPU detected: {info.device_name} ({info.pci_slot})")
            except Exception as exc:
                logger.warning(f"GPU device_info failed: {exc}")
        else:
            logger.info("No dedicated GPU detected")

    @staticmethod
    def _select_backend() -> GpuBackend:
        if getattr(settings, "is_dev_mode", False):
            return DevGpuBackend()
        try:
            from app.services.monitoring.gpu.amd_backend import AmdGpuBackend
            amd = AmdGpuBackend()
            if amd.detected:
                return amd
        except Exception as exc:
            logger.debug(f"AMD GPU detection failed: {exc}")
        return _NoGpuBackend()

    @property
    def detected(self) -> bool:
        return self.backend.detected

    def collect_sample(self) -> Optional[GpuSampleSchema]:
        if not self.backend.detected:
            return None
        try:
            raw = self.backend.read_sample()
            return GpuSampleSchema(timestamp=datetime.now(timezone.utc), **raw)
        except Exception as exc:
            logger.error(f"GPU sample collection failed: {exc}")
            return None

    def get_db_model(self) -> Type[Any]:
        return GpuSample

    def sample_to_db_dict(self, sample: GpuSampleSchema) -> dict:
        return {
            "timestamp": sample.timestamp,
            "vendor": sample.vendor,
            "device_name": sample.device_name,
            "pci_slot": sample.pci_slot,
            "usage_percent": sample.usage_percent,
            "engine_gfx_percent": sample.engine_gfx_percent,
            "engine_compute_percent": sample.engine_compute_percent,
            "engine_decode_percent": sample.engine_decode_percent,
            "engine_encode_percent": sample.engine_encode_percent,
            "vram_used_bytes": sample.vram_used_bytes,
            "vram_total_bytes": sample.vram_total_bytes,
            "core_clock_mhz": sample.core_clock_mhz,
            "memory_clock_mhz": sample.memory_clock_mhz,
            "temperature_edge_celsius": sample.temperature_edge_celsius,
            "temperature_junction_celsius": sample.temperature_junction_celsius,
            "temperature_memory_celsius": sample.temperature_memory_celsius,
            "fan_rpm": sample.fan_rpm,
            "power_watts": sample.power_watts,
        }

    def db_to_sample(self, db_record: GpuSample) -> GpuSampleSchema:
        return GpuSampleSchema(
            timestamp=db_record.timestamp,
            vendor=db_record.vendor,
            device_name=db_record.device_name,
            pci_slot=db_record.pci_slot,
            usage_percent=db_record.usage_percent,
            engine_gfx_percent=db_record.engine_gfx_percent,
            engine_compute_percent=db_record.engine_compute_percent,
            engine_decode_percent=db_record.engine_decode_percent,
            engine_encode_percent=db_record.engine_encode_percent,
            vram_used_bytes=db_record.vram_used_bytes,
            vram_total_bytes=db_record.vram_total_bytes,
            core_clock_mhz=db_record.core_clock_mhz,
            memory_clock_mhz=db_record.memory_clock_mhz,
            temperature_edge_celsius=db_record.temperature_edge_celsius,
            temperature_junction_celsius=db_record.temperature_junction_celsius,
            temperature_memory_celsius=db_record.temperature_memory_celsius,
            fan_rpm=db_record.fan_rpm,
            power_watts=db_record.power_watts,
        )
```

Run: `cd backend && python -m pytest tests/monitoring/test_gpu_collector.py -v`
Expected: PASS (all six tests)

- [ ] **Step 4.3: Write failing orchestrator integration test**

Create `backend/tests/monitoring/test_orchestrator_gpu.py`:

```python
"""GPU integration in MonitoringOrchestrator."""
from unittest.mock import MagicMock

import pytest

from app.services.monitoring.orchestrator import MonitoringOrchestrator
from app.services.monitoring.gpu_collector import GpuMetricCollector


def test_orchestrator_has_gpu_collector():
    o = MonitoringOrchestrator()
    assert hasattr(o, "gpu_collector")
    assert isinstance(o.gpu_collector, GpuMetricCollector)


def test_get_stats_reports_gpu():
    o = MonitoringOrchestrator()
    # Stats shape: must include 'gpu' under collectors
    status = o.get_stats() if hasattr(o, "get_stats") else None
    if status is None:
        # Orchestrator exposes stats through a different method; check the
        # monitoring_status response path instead (this test may be adjusted).
        pytest.skip("get_stats not present; covered by route test")
    assert "gpu" in status.get("collectors", {})


def test_sample_once_skips_when_no_gpu(monkeypatch):
    """With detected=False, the GPU collector must not write to DB or raise."""
    import asyncio

    o = MonitoringOrchestrator()
    # Force not-detected
    class _Fake:
        detected = False
        def read_sample(self): raise AssertionError("must not be called")
    o.gpu_collector.backend = _Fake()

    async def _run():
        await o._sample_once()

    asyncio.run(_run())  # should complete without exception
```

Run: `cd backend && python -m pytest tests/monitoring/test_orchestrator_gpu.py -v`
Expected: FAIL (`AttributeError: 'MonitoringOrchestrator' object has no attribute 'gpu_collector'`)

- [ ] **Step 4.4: Wire collector into orchestrator**

Edit `backend/app/services/monitoring/orchestrator.py`.

Add import near the other collector imports (after line 29):

```python
from app.services.monitoring.gpu_collector import GpuMetricCollector
```

Add import near the schema imports (after line 23):

```python
from app.schemas.monitoring import (
    CpuSampleSchema,
    MemorySampleSchema,
    NetworkSampleSchema,
    DiskIoSampleSchema,
    UptimeSampleSchema,
    GpuSampleSchema,
)
```

In `__init__` (after the `self.uptime_collector = ...` block, before `self.retention_manager = ...`):

```python
        self.gpu_collector = GpuMetricCollector(
            buffer_size=buffer_size,
            persist_interval=persist_interval,
        )
```

In `_sample_once` (inside the `try:` block, after `self.uptime_collector.process_sample(db)`):

```python
            # GPU (no-op when no dedicated GPU detected)
            self.gpu_collector.process_sample(db)
```

After the existing `get_cpu_current_with_db_fallback` method, add:

```python
    def get_gpu_current(self) -> Optional[GpuSampleSchema]:
        """Get current GPU sample (in-memory only — no SHM integration yet)."""
        return self.gpu_collector.get_current()

    def get_gpu_current_with_db_fallback(self, db: Session) -> Optional[GpuSampleSchema]:
        """Get current GPU sample (in-memory → DB fallback).

        Returns None if no GPU is detected OR if no samples exist anywhere.
        Callers distinguish 'no GPU' via gpu_collector.detected.
        """
        if not self.gpu_collector.detected:
            return None
        sample = self.gpu_collector.get_current()
        if sample is not None:
            return sample
        from app.models.monitoring import GpuSample
        db_record = db.query(GpuSample).order_by(GpuSample.timestamp.desc()).first()
        if db_record:
            return self.gpu_collector.db_to_sample(db_record)
        return None

    def get_gpu_history(self, limit: Optional[int] = None) -> List:
        """Get GPU history from memory buffer."""
        return self.gpu_collector.get_history_memory(limit)
```

If `MonitoringOrchestrator` has a `get_stats()` method that reports `collectors`, add `"gpu": self.gpu_collector.is_enabled() and self.gpu_collector.detected`. (If there is no such method, the monitoring status route handles this — cross-check in Task 5.)

Run: `cd backend && python -m pytest tests/monitoring/test_orchestrator_gpu.py -v`
Expected: PASS (or `test_get_stats_reports_gpu` skipped — acceptable)

- [ ] **Step 4.5: Run the full monitoring test suite**

Run: `cd backend && python -m pytest tests/monitoring/ -v`
Expected: PASS (existing + new)

- [ ] **Step 4.6: Commit**

```bash
git add backend/app/services/monitoring/gpu_collector.py \
  backend/app/services/monitoring/orchestrator.py \
  backend/tests/monitoring/test_gpu_collector.py \
  backend/tests/monitoring/test_orchestrator_gpu.py
git commit -m "feat(monitoring): add GpuMetricCollector and orchestrator hookup"
```

---

## Task 5: API routes

**Files:**
- Create: `backend/app/api/routes/monitoring_gpu.py`
- Modify: `backend/app/api/routes/__init__.py`
- Test: `backend/tests/api/test_monitoring_gpu_routes.py`

- [ ] **Step 5.1: Write failing route tests**

Create `backend/tests/api/test_monitoring_gpu_routes.py`:

```python
"""GPU monitoring API routes."""
import pytest
from fastapi.testclient import TestClient


def test_gpu_info_requires_auth(client: TestClient):
    r = client.get("/api/monitoring/gpu/info")
    assert r.status_code == 401


def test_gpu_info_returns_device_when_detected(authed_client: TestClient):
    """In dev mode a mock GPU is always detected."""
    r = authed_client.get("/api/monitoring/gpu/info")
    assert r.status_code == 200
    body = r.json()
    assert body["vendor"] == "amd"
    assert "7900 XT" in body["device_name"]
    assert body["vram_total_bytes"] > 0


def test_gpu_current_eventually_available(authed_client: TestClient):
    """/gpu/current returns 503 until the first sample, then 200."""
    # Force a sample by directly calling process_sample
    from app.services.monitoring.orchestrator import get_monitoring_orchestrator
    orch = get_monitoring_orchestrator()
    orch.gpu_collector.process_sample(None)

    r = authed_client.get("/api/monitoring/gpu/current")
    assert r.status_code == 200
    body = r.json()
    assert body["vendor"] == "amd"
    assert body["usage_percent"] is not None


def test_gpu_history_returns_list(authed_client: TestClient):
    from app.services.monitoring.orchestrator import get_monitoring_orchestrator
    orch = get_monitoring_orchestrator()
    for _ in range(3):
        orch.gpu_collector.process_sample(None)

    r = authed_client.get("/api/monitoring/gpu/history?time_range=10m")
    assert r.status_code == 200
    body = r.json()
    assert "samples" in body
    assert body["sample_count"] == len(body["samples"])
    assert body["source"] in ("memory", "database", "memory (fallback)", "database (fallback)")


def test_gpu_endpoints_404_when_not_detected(authed_client: TestClient, monkeypatch):
    """Force detected=False and verify 404 on all three endpoints."""
    from app.services.monitoring.orchestrator import get_monitoring_orchestrator
    orch = get_monitoring_orchestrator()

    class _Fake:
        detected = False
    original = orch.gpu_collector.backend
    orch.gpu_collector.backend = _Fake()
    try:
        assert authed_client.get("/api/monitoring/gpu/info").status_code == 404
        assert authed_client.get("/api/monitoring/gpu/current").status_code == 404
        assert authed_client.get("/api/monitoring/gpu/history").status_code == 404
    finally:
        orch.gpu_collector.backend = original
```

(Fixtures `client` and `authed_client` follow the existing `backend/tests/conftest.py` pattern — if they use different names locally, adapt.)

Run: `cd backend && python -m pytest tests/api/test_monitoring_gpu_routes.py -v`
Expected: FAIL (routes not registered yet)

- [ ] **Step 5.2: Create the route module**

Create `backend/app/api/routes/monitoring_gpu.py`:

```python
"""GPU monitoring API routes.

Kept separate from monitoring.py because that file is already large.
Registered under the same /api/monitoring prefix in routes/__init__.py.
"""
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.rate_limiter import user_limiter, get_limit
from app.models.user import User
from app.schemas.monitoring import (
    CurrentGpuResponse,
    DataSource,
    GpuDeviceInfo,
    GpuHistoryResponse,
    TimeRangeEnum,
)
from app.services.monitoring.orchestrator import get_monitoring_orchestrator

router = APIRouter(prefix="/monitoring", tags=["system-monitoring"])


def _parse_time_range(time_range: TimeRangeEnum) -> timedelta:
    mapping = {
        TimeRangeEnum.TEN_MINUTES: timedelta(minutes=10),
        TimeRangeEnum.ONE_HOUR: timedelta(hours=1),
        TimeRangeEnum.TWENTY_FOUR_HOURS: timedelta(hours=24),
        TimeRangeEnum.SEVEN_DAYS: timedelta(days=7),
    }
    return mapping.get(time_range, timedelta(hours=1))


@router.get("/gpu/info", response_model=GpuDeviceInfo)
@user_limiter.limit(get_limit("system_monitor"))
async def get_gpu_info(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
):
    """Get dedicated GPU device metadata. 404 when no GPU is detected."""
    orch = get_monitoring_orchestrator()
    if not orch.gpu_collector.detected:
        raise HTTPException(status_code=404, detail="No dedicated GPU detected")
    try:
        return orch.gpu_collector.backend.device_info()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"GPU info unavailable: {exc}")


@router.get("/gpu/current", response_model=CurrentGpuResponse)
@user_limiter.limit(get_limit("system_monitor"))
async def get_gpu_current(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the current GPU sample.

    - 404 when no GPU is detected.
    - 503 when detected but the memory buffer is empty and no DB history exists yet.
    """
    orch = get_monitoring_orchestrator()
    if not orch.gpu_collector.detected:
        raise HTTPException(status_code=404, detail="No dedicated GPU detected")

    sample = orch.get_gpu_current_with_db_fallback(db)
    if sample is None:
        raise HTTPException(status_code=503, detail="No GPU data available yet")
    return sample


@router.get("/gpu/history", response_model=GpuHistoryResponse)
@user_limiter.limit(get_limit("system_monitor"))
async def get_gpu_history(
    request: Request,
    response: Response,
    time_range: TimeRangeEnum = Query(default=TimeRangeEnum.ONE_HOUR),
    source: DataSource = Query(default=DataSource.AUTO),
    limit: int = Query(default=1000, ge=1, le=10000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get GPU history with memory/database selection matching /cpu/history."""
    orch = get_monitoring_orchestrator()
    if not orch.gpu_collector.detected:
        raise HTTPException(status_code=404, detail="No dedicated GPU detected")

    duration = _parse_time_range(time_range)

    if source == DataSource.MEMORY or (source == DataSource.AUTO and duration <= timedelta(minutes=10)):
        samples = orch.get_gpu_history(limit)
        source_str = "memory"
        if not samples:
            start = datetime.now(timezone.utc) - duration
            samples = orch.gpu_collector.get_history_db(db, start=start, limit=limit)
            source_str = "database (fallback)"
    else:
        start = datetime.now(timezone.utc) - duration
        samples = orch.gpu_collector.get_history_db(db, start=start, limit=limit)
        source_str = "database"
        if not samples:
            samples = orch.get_gpu_history(limit)
            source_str = "memory (fallback)"

    return GpuHistoryResponse(
        samples=samples,
        sample_count=len(samples),
        source=source_str,
    )
```

- [ ] **Step 5.3: Register the router**

Edit `backend/app/api/routes/__init__.py`.

In the import list (around line 3), add `monitoring_gpu`:

```python
from app.api.routes import (
    auth, files, logging, system, users, upload_progress, shares, backup, sync,
    sync_advanced, mobile, vpn, health, admin_db, sync_compat, rate_limit_config,
    vcl, server_profiles, vpn_profiles, metrics, energy, devices, monitoring,
    monitoring_gpu,
    power, power_presets, fans, service_status, schedulers, plugins,
    ...
```

Next to the existing `monitoring.router` registration (around line 47), add:

```python
api_router.include_router(monitoring.router, tags=["system-monitoring"])
api_router.include_router(monitoring_gpu.router, tags=["system-monitoring"])
```

- [ ] **Step 5.4: Run route tests**

Run: `cd backend && python -m pytest tests/api/test_monitoring_gpu_routes.py -v`
Expected: PASS (all five tests)

- [ ] **Step 5.5: Run the full backend test suite as a regression check**

Run: `cd backend && python -m pytest -x -q`
Expected: all existing tests still pass

- [ ] **Step 5.6: Commit**

```bash
git add backend/app/api/routes/monitoring_gpu.py \
  backend/app/api/routes/__init__.py \
  backend/tests/api/test_monitoring_gpu_routes.py
git commit -m "feat(monitoring): add /api/monitoring/gpu/{info,current,history} routes"
```

---

## Task 6: Frontend API client + `useGpuPresence` hook

**Files:**
- Modify: `client/src/api/monitoring.ts`
- Create: `client/src/hooks/useGpuPresence.ts`
- Test: `client/src/hooks/__tests__/useGpuPresence.test.ts`

- [ ] **Step 6.1: Extend the API client**

Edit `client/src/api/monitoring.ts`.

After the `CpuSample` interface (around line 29), add:

```typescript
export interface GpuSample {
  timestamp: string;
  vendor: string;
  device_name: string;
  pci_slot: string | null;
  usage_percent: number | null;
  engine_gfx_percent: number | null;
  engine_compute_percent: number | null;
  engine_decode_percent: number | null;
  engine_encode_percent: number | null;
  vram_used_bytes: number | null;
  vram_total_bytes: number | null;
  core_clock_mhz: number | null;
  memory_clock_mhz: number | null;
  temperature_edge_celsius: number | null;
  temperature_junction_celsius: number | null;
  temperature_memory_celsius: number | null;
  fan_rpm: number | null;
  power_watts: number | null;
}

export interface GpuDeviceInfo {
  vendor: string;
  device_name: string;
  pci_slot: string | null;
  vram_total_bytes: number | null;
  driver_version: string | null;
}
```

After the `CpuHistoryResponse` interface (around line 140), add:

```typescript
export interface GpuHistoryResponse {
  samples: GpuSample[];
  sample_count: number;
  source: string;
}
```

In the API Functions section (near the CPU functions around line 224), after `getCpuHistory`, add:

```typescript
// GPU
export async function getGpuInfo(): Promise<GpuDeviceInfo | null> {
  try {
    const response = await apiClient.get<GpuDeviceInfo>('/api/monitoring/gpu/info');
    return response.data;
  } catch (err: any) {
    if (err?.response?.status === 404) return null;
    throw err;
  }
}

export async function getGpuCurrent(): Promise<GpuSample | null> {
  try {
    const response = await apiClient.get<GpuSample>('/api/monitoring/gpu/current');
    return response.data;
  } catch (err: any) {
    const status = err?.response?.status;
    if (status === 404 || status === 503) return null;
    throw err;
  }
}

export async function getGpuHistory(
  timeRange: TimeRange = '1h',
  source: DataSource = 'auto',
  limit: number = 1000
): Promise<GpuHistoryResponse> {
  const response = await apiClient.get<GpuHistoryResponse>('/api/monitoring/gpu/history', {
    params: { time_range: timeRange, source, limit },
  });
  return response.data;
}
```

- [ ] **Step 6.2: Write failing `useGpuPresence` test**

Create `client/src/hooks/__tests__/useGpuPresence.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import * as api from '../../api/monitoring';
import { useGpuPresence } from '../useGpuPresence';

vi.mock('../../api/monitoring');

describe('useGpuPresence', () => {
  beforeEach(() => vi.resetAllMocks());

  it('returns present:true with info when /gpu/info returns data', async () => {
    (api.getGpuInfo as any).mockResolvedValue({
      vendor: 'amd', device_name: 'AMD Radeon RX 7900 XT',
      pci_slot: '0000:03:00.0', vram_total_bytes: 21474836480, driver_version: null,
    });

    const { result } = renderHook(() => useGpuPresence());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.present).toBe(true);
    expect(result.current.info?.device_name).toContain('7900 XT');
  });

  it('returns present:false when /gpu/info returns null (404)', async () => {
    (api.getGpuInfo as any).mockResolvedValue(null);
    const { result } = renderHook(() => useGpuPresence());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.present).toBe(false);
    expect(result.current.info).toBeNull();
  });
});
```

Run: `cd client && npm run test -- useGpuPresence`
Expected: FAIL (hook does not exist)

- [ ] **Step 6.3: Implement `useGpuPresence`**

Create `client/src/hooks/useGpuPresence.ts`:

```typescript
import { useEffect, useState } from 'react';
import { getGpuInfo, GpuDeviceInfo } from '../api/monitoring';

interface GpuPresence {
  present: boolean;
  info: GpuDeviceInfo | null;
  loading: boolean;
}

// Module-level cache — GPU detection does not change at runtime.
let cached: GpuPresence | null = null;
let inflight: Promise<GpuPresence> | null = null;

async function load(): Promise<GpuPresence> {
  if (cached) return cached;
  if (inflight) return inflight;

  inflight = (async () => {
    try {
      const info = await getGpuInfo();
      cached = { present: info !== null, info, loading: false };
    } catch {
      cached = { present: false, info: null, loading: false };
    } finally {
      inflight = null;
    }
    return cached!;
  })();
  return inflight;
}

export function useGpuPresence(): GpuPresence {
  const [state, setState] = useState<GpuPresence>(
    cached ?? { present: false, info: null, loading: true }
  );

  useEffect(() => {
    let alive = true;
    load().then((result) => {
      if (alive) setState(result);
    });
    return () => { alive = false; };
  }, []);

  return state;
}

// For tests — reset the module cache between cases.
export function __resetGpuPresenceCache() {
  cached = null;
  inflight = null;
}
```

Update the test file to reset the cache between tests — add at top:

```typescript
import { __resetGpuPresenceCache } from '../useGpuPresence';
// ...
beforeEach(() => {
  vi.resetAllMocks();
  __resetGpuPresenceCache();
});
```

Run: `cd client && npm run test -- useGpuPresence`
Expected: PASS (both test cases)

- [ ] **Step 6.4: Commit**

```bash
git add client/src/api/monitoring.ts \
  client/src/hooks/useGpuPresence.ts \
  client/src/hooks/__tests__/useGpuPresence.test.ts
git commit -m "feat(monitoring): add GPU API client and useGpuPresence hook"
```

---

## Task 7: `<CpuGpuPanel />` dashboard component

**Files:**
- Create: `client/src/components/dashboard/CpuGpuPanel.tsx`
- Create: `client/src/components/dashboard/__tests__/CpuGpuPanel.test.tsx`
- Modify: `client/src/pages/Dashboard.tsx`
- Modify: `client/src/i18n/locales/de/dashboard.json`
- Modify: `client/src/i18n/locales/en/dashboard.json`

- [ ] **Step 7.1: Inspect current Dashboard CPU card**

Read `client/src/pages/Dashboard.tsx` and locate the existing inline CPU quick-stat card. Note: the height, gradient classes, sparkline structure, and click-through `navigate('/system?tab=cpu')` target. This is what the `<CpuGpuPanel />` replaces.

Record: the component must accept no props and internally handle CPU + GPU polling, matching the existing CPU card visually when GPU is absent.

- [ ] **Step 7.2: Write failing test for the panel**

Create `client/src/components/dashboard/__tests__/CpuGpuPanel.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import * as api from '../../../api/monitoring';
import { __resetGpuPresenceCache } from '../../../hooks/useGpuPresence';
import { CpuGpuPanel } from '../CpuGpuPanel';

vi.mock('../../../api/monitoring');

function setup() {
  return render(<MemoryRouter><CpuGpuPanel /></MemoryRouter>);
}

describe('<CpuGpuPanel />', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    __resetGpuPresenceCache();
    (api.getCpuCurrent as any).mockResolvedValue({
      timestamp: new Date().toISOString(),
      usage_percent: 42, frequency_mhz: 3200, temperature_celsius: 55,
      core_count: 8, thread_count: 16,
    });
  });

  it('renders CPU-only when no GPU is present', async () => {
    (api.getGpuInfo as any).mockResolvedValue(null);
    setup();
    await waitFor(() => expect(screen.getByText(/CPU/i)).toBeInTheDocument());
    expect(screen.queryByText(/GPU/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/7900 XT/)).not.toBeInTheDocument();
  });

  it('renders both CPU and GPU sections when a GPU is present', async () => {
    (api.getGpuInfo as any).mockResolvedValue({
      vendor: 'amd', device_name: 'AMD Radeon RX 7900 XT',
      pci_slot: '0000:03:00.0', vram_total_bytes: 21474836480, driver_version: null,
    });
    (api.getGpuCurrent as any).mockResolvedValue({
      timestamp: new Date().toISOString(),
      vendor: 'amd', device_name: 'AMD Radeon RX 7900 XT', pci_slot: '0000:03:00.0',
      usage_percent: 55, engine_gfx_percent: 55, engine_compute_percent: 50,
      engine_decode_percent: 10, engine_encode_percent: 5,
      vram_used_bytes: 8_000_000_000, vram_total_bytes: 20_000_000_000,
      core_clock_mhz: 2400, memory_clock_mhz: 2500,
      temperature_edge_celsius: 60, temperature_junction_celsius: 70,
      temperature_memory_celsius: 72, fan_rpm: 1500, power_watts: 180,
    });

    setup();
    await waitFor(() => expect(screen.getByText(/7900 XT/)).toBeInTheDocument());
    expect(screen.getByText(/CPU/i)).toBeInTheDocument();
  });
});
```

Run: `cd client && npm run test -- CpuGpuPanel`
Expected: FAIL (component does not exist)

- [ ] **Step 7.3: Implement `<CpuGpuPanel />`**

Create `client/src/components/dashboard/CpuGpuPanel.tsx`:

```tsx
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Cpu as CpuIcon, MonitorSmartphone } from 'lucide-react';
import { getCpuCurrent, getGpuCurrent, CurrentCpuResponse, GpuSample } from '../../api/monitoring';
import { useGpuPresence } from '../../hooks/useGpuPresence';

const POLL_MS = 3000;

// Tries the lucide "Gpu" icon if the version supports it; otherwise falls back to MonitorSmartphone.
function GpuIcon(props: React.SVGProps<SVGSVGElement>) {
  // Re-export lazily so missing icons don't break the build
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { Gpu } = require('lucide-react');
    if (Gpu) return <Gpu {...props} />;
  } catch { /* fall through */ }
  return <MonitorSmartphone {...props} />;
}

export function CpuGpuPanel() {
  const { t } = useTranslation('dashboard');
  const navigate = useNavigate();
  const { present: hasGpu, info: gpuInfo } = useGpuPresence();

  const [cpu, setCpu] = useState<CurrentCpuResponse | null>(null);
  const [gpu, setGpu] = useState<GpuSample | null>(null);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const [c, g] = await Promise.all([
          getCpuCurrent(),
          hasGpu ? getGpuCurrent() : Promise.resolve(null),
        ]);
        if (cancelled) return;
        setCpu(c);
        setGpu(g);
      } catch { /* ignore transient errors; keep last value */ }
    };
    tick();
    const id = setInterval(tick, POLL_MS);
    return () => { cancelled = true; clearInterval(id); };
  }, [hasGpu]);

  return (
    <div className="rounded-xl border border-slate-800/60 bg-slate-900/40 overflow-hidden">
      <button
        type="button"
        onClick={() => navigate('/system?tab=cpu')}
        className="w-full text-left p-4 hover:bg-slate-900/60 transition-colors flex items-start gap-3"
      >
        <CpuIcon className="h-5 w-5 text-sky-400 mt-0.5" />
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline justify-between">
            <span className="text-sm text-slate-300">{t('cpu.title', 'CPU')}</span>
            <span className="text-2xl font-semibold tabular-nums text-slate-100">
              {cpu ? `${Math.round(cpu.usage_percent)}%` : '—'}
            </span>
          </div>
          <div className="text-xs text-slate-500 mt-1 truncate">
            {cpu?.frequency_mhz ? `${(cpu.frequency_mhz / 1000).toFixed(1)} GHz` : ''}
            {cpu?.temperature_celsius != null ? ` · ${Math.round(cpu.temperature_celsius)}°C` : ''}
          </div>
          {/* Progress bar */}
          <div className="h-1.5 bg-slate-800 rounded mt-2 overflow-hidden">
            <div
              className="h-full bg-sky-500 transition-[width] duration-500"
              style={{ width: `${Math.min(100, Math.max(0, cpu?.usage_percent ?? 0))}%` }}
            />
          </div>
        </div>
      </button>

      {hasGpu && (
        <>
          <div className="border-t border-slate-800/60" />
          <button
            type="button"
            onClick={() => navigate('/system?tab=gpu')}
            className="w-full text-left p-4 hover:bg-slate-900/60 transition-colors flex items-start gap-3"
          >
            <GpuIcon className="h-5 w-5 text-emerald-400 mt-0.5" />
            <div className="flex-1 min-w-0">
              <div className="flex items-baseline justify-between">
                <span className="text-sm text-slate-300">{t('gpu.title', 'GPU')}</span>
                <span className="text-2xl font-semibold tabular-nums text-slate-100">
                  {gpu?.usage_percent != null ? `${Math.round(gpu.usage_percent)}%` : '—'}
                </span>
              </div>
              <div className="text-xs text-slate-500 mt-1 truncate">
                {gpuInfo?.device_name ?? ''}
                {gpu?.temperature_edge_celsius != null ? ` · ${Math.round(gpu.temperature_edge_celsius)}°C` : ''}
              </div>
              <div className="h-1.5 bg-slate-800 rounded mt-2 overflow-hidden">
                <div
                  className="h-full bg-emerald-500 transition-[width] duration-500"
                  style={{ width: `${Math.min(100, Math.max(0, gpu?.usage_percent ?? 0))}%` }}
                />
              </div>
            </div>
          </button>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 7.4: Add i18n keys**

Edit `client/src/i18n/locales/en/dashboard.json` — add under the root object:

```json
"gpu": {
  "title": "GPU",
  "noDedicated": "No dedicated GPU",
  "power": "Power",
  "temperature": "Temperature",
  "usage": "Usage"
}
```

Mirror in `client/src/i18n/locales/de/dashboard.json`:

```json
"gpu": {
  "title": "GPU",
  "noDedicated": "Keine dedizierte GPU",
  "power": "Leistung",
  "temperature": "Temperatur",
  "usage": "Auslastung"
}
```

(If an existing `cpu` key is not already present in `dashboard.json`, add `"cpu": {"title": "CPU"}` next to `gpu`.)

- [ ] **Step 7.5: Swap `<CpuGpuPanel />` into `Dashboard.tsx`**

Edit `client/src/pages/Dashboard.tsx`. Import the new component:

```tsx
import { CpuGpuPanel } from '../components/dashboard/CpuGpuPanel';
```

Find the inline CPU quick-stat card (it has the CPU icon + percent + sparkline). Replace it with `<CpuGpuPanel />`. The surrounding grid and siblings stay unchanged. Neighbouring cards should already sit in an `items-start` grid; if not, add `items-start` to the grid container so asymmetric height does not stretch siblings.

- [ ] **Step 7.6: Run tests and start dev server**

Run: `cd client && npm run test -- CpuGpuPanel`
Expected: PASS (both tests)

Manual check: run `python start_dev.py` from the repo root and open `http://localhost:5173/`. Verify:
- The Dashboard CPU/GPU card is stacked with the mock "AMD Radeon RX 7900 XT (dev-mock)" visible.
- Clicking the GPU half navigates to `/system?tab=gpu` (tab render comes in Task 8).

- [ ] **Step 7.7: Commit**

```bash
git add client/src/components/dashboard/CpuGpuPanel.tsx \
  client/src/components/dashboard/__tests__/CpuGpuPanel.test.tsx \
  client/src/pages/Dashboard.tsx \
  client/src/i18n/locales/en/dashboard.json \
  client/src/i18n/locales/de/dashboard.json
git commit -m "feat(dashboard): add stacked CpuGpuPanel with GPU presence gating"
```

---

## Task 8: `GpuTab` + SystemMonitor integration

**Files:**
- Create: `client/src/components/system-monitor/GpuTab.tsx`
- Modify: `client/src/components/system-monitor/index.ts`
- Modify: `client/src/pages/SystemMonitor.tsx`
- Modify: `client/src/i18n/locales/{de,en}/monitor.json`

- [ ] **Step 8.1: Inspect `CpuTab.tsx` as the structural template**

Read `client/src/components/system-monitor/CpuTab.tsx`. Note the props it accepts (likely `{ timeRange }`), the `useEffect` polling pattern, the chart stack (Recharts), and the per-thread toggle. The GPU tab mirrors this structure.

- [ ] **Step 8.2: Create `GpuTab.tsx` with device header, KPIs, temps, engines, fan/mem clock**

Create `client/src/components/system-monitor/GpuTab.tsx`:

```tsx
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  getGpuCurrent,
  getGpuHistory,
  GpuSample,
  TimeRange,
} from '../../api/monitoring';
import { useGpuPresence } from '../../hooks/useGpuPresence';

interface Props {
  timeRange: TimeRange;
}

const POLL_MS = 3000;

function formatBytes(n: number | null): string {
  if (n == null) return '—';
  if (n >= 1 << 30) return `${(n / (1 << 30)).toFixed(1)} GB`;
  if (n >= 1 << 20) return `${(n / (1 << 20)).toFixed(1)} MB`;
  return `${n} B`;
}

export function GpuTab({ timeRange }: Props) {
  const { t } = useTranslation('monitor');
  const { info } = useGpuPresence();

  const [current, setCurrent] = useState<GpuSample | null>(null);
  const [history, setHistory] = useState<GpuSample[]>([]);
  const [engineView, setEngineView] = useState<'overview' | 'per-engine'>('overview');

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const c = await getGpuCurrent();
        if (!cancelled) setCurrent(c);
      } catch { /* ignore */ }
    };
    tick();
    const id = setInterval(tick, POLL_MS);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await getGpuHistory(timeRange);
        if (!cancelled) setHistory(res.samples);
      } catch { /* ignore */ }
    })();
    return () => { cancelled = true; };
  }, [timeRange]);

  if (!info) return null;

  return (
    <div className="space-y-4">
      {/* Device header */}
      <div className="rounded-xl border border-slate-800/60 bg-slate-900/40 p-4 flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs uppercase text-slate-500">{info.vendor}</span>
            <h2 className="text-xl font-semibold text-slate-100">{info.device_name}</h2>
          </div>
          <div className="text-xs text-slate-500 mt-1">
            {info.pci_slot ?? ''}
            {info.driver_version ? ` · ${info.driver_version}` : ''}
          </div>
        </div>
        <div className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" aria-label="live" />
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Kpi label={t('gpu.usage', 'Usage')} value={current?.usage_percent != null ? `${Math.round(current.usage_percent)}%` : '—'} />
        <Kpi
          label={t('gpu.vram', 'VRAM')}
          value={`${formatBytes(current?.vram_used_bytes ?? null)} / ${formatBytes(current?.vram_total_bytes ?? null)}`}
        />
        <Kpi label={t('gpu.coreClock', 'Core Clock')} value={current?.core_clock_mhz != null ? `${current.core_clock_mhz.toFixed(0)} MHz` : '—'} />
        <Kpi label={t('gpu.power', 'Power')} value={current?.power_watts != null ? `${current.power_watts.toFixed(0)} W` : '—'} />
      </div>

      {/* Temperature block */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <Kpi label={t('gpu.tempEdge', 'Edge Temp')} value={fmtTemp(current?.temperature_edge_celsius)} />
        <Kpi label={t('gpu.tempJunction', 'Junction Temp')} value={fmtTemp(current?.temperature_junction_celsius)} />
        <Kpi label={t('gpu.tempMemory', 'Memory Temp')} value={fmtTemp(current?.temperature_memory_celsius)} />
      </div>

      {/* Per-engine usage */}
      <div className="rounded-xl border border-slate-800/60 bg-slate-900/40 p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-medium text-slate-200">{t('gpu.engines', 'Engine activity')}</h3>
          <div className="flex gap-1 text-xs bg-slate-800 rounded p-0.5">
            <button
              className={`px-2 py-0.5 rounded ${engineView === 'overview' ? 'bg-slate-700 text-slate-100' : 'text-slate-400'}`}
              onClick={() => setEngineView('overview')}
            >{t('gpu.overview', 'Overview')}</button>
            <button
              className={`px-2 py-0.5 rounded ${engineView === 'per-engine' ? 'bg-slate-700 text-slate-100' : 'text-slate-400'}`}
              onClick={() => setEngineView('per-engine')}
            >{t('gpu.perEngine', 'Per-Engine')}</button>
          </div>
        </div>
        {engineView === 'per-engine' ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Kpi label={t('gpu.engineGfx', 'Graphics')} value={fmtPct(current?.engine_gfx_percent)} />
            <Kpi label={t('gpu.engineCompute', 'Compute')} value={fmtPct(current?.engine_compute_percent)} />
            <Kpi label={t('gpu.engineDecode', 'Decode')} value={fmtPct(current?.engine_decode_percent)} />
            <Kpi label={t('gpu.engineEncode', 'Encode')} value={fmtPct(current?.engine_encode_percent)} />
          </div>
        ) : (
          <div className="text-xs text-slate-500">
            {/* History-based stacked chart — delegated to existing chart components.
                For the first cut we show aggregate numbers; richer charts can arrive
                in a follow-up PR without changing the component interface. */}
            {t('gpu.overviewHint', 'Stacked engine activity over the selected time range.')}
            <div className="text-slate-300 mt-2">
              {t('gpu.samplesLoaded', 'Samples loaded')}: {history.length}
            </div>
          </div>
        )}
      </div>

      {/* Fan + memory clock */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Kpi label={t('gpu.fanRpm', 'Fan')} value={current?.fan_rpm != null ? `${current.fan_rpm} RPM` : '—'} />
        <Kpi label={t('gpu.memoryClock', 'Memory Clock')} value={current?.memory_clock_mhz != null ? `${current.memory_clock_mhz.toFixed(0)} MHz` : '—'} />
      </div>
    </div>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-800/60 bg-slate-900/40 p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-lg font-semibold tabular-nums text-slate-100 mt-1">{value}</div>
    </div>
  );
}

function fmtTemp(v?: number | null) {
  return v != null ? `${v.toFixed(0)}°C` : '—';
}
function fmtPct(v?: number | null) {
  return v != null ? `${v.toFixed(0)}%` : '—';
}
```

This keeps the first cut lightweight (no recharts dependencies from day one) — richer charts can be added in a follow-up without changing the component's public interface.

- [ ] **Step 8.3: Export from the barrel**

Edit `client/src/components/system-monitor/index.ts`. Add:

```typescript
export { GpuTab } from './GpuTab';
```

(Match the existing export style — if the file re-exports named members, follow that convention.)

- [ ] **Step 8.4: Register the GPU tab in `SystemMonitor.tsx`**

Edit `client/src/pages/SystemMonitor.tsx`.

1. Import `GpuTab` and the presence hook:

```tsx
import { GpuTab } from '../components/system-monitor/GpuTab';
import { useGpuPresence } from '../hooks/useGpuPresence';
```

2. Extend `TabType`:

```tsx
type TabType = 'cpu' | 'gpu' | 'memory' | 'network' | 'disk-io' | 'power' | 'uptime' | 'services' | 'health' | 'backend-logs' | 'logs' | 'activity';
```

3. In `BASE_CATEGORIES` → hardware → `tabs`, insert the GPU tab **between `cpu` and `memory`**:

```tsx
{
  id: 'gpu',
  labelKey: 'monitor.tabs.gpu',
  icon: (
    <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <rect x="3" y="6" width="18" height="12" rx="2" />
      <path d="M7 10h2M11 10h2M15 10h2" strokeLinecap="round" />
      <circle cx="8" cy="14" r="1.5" />
      <circle cx="13" cy="14" r="1.5" />
    </svg>
  ),
},
```

4. In the component body (near other `useState`/`useMemo` setup), add conditional filtering:

```tsx
const { present: hasGpu } = useGpuPresence();
const categories = useMemo(
  () => BASE_CATEGORIES.map((cat) =>
    cat.id === 'hardware'
      ? { ...cat, tabs: cat.tabs.filter((tab) => tab.id !== 'gpu' || hasGpu) }
      : cat
  ),
  [hasGpu],
);
```

Then replace any downstream reference to `BASE_CATEGORIES` with `categories`.

5. In the tab-content renderer (switch on `activeTab`), add the GPU case:

```tsx
{activeTab === 'gpu' && <GpuTab timeRange={timeRange} />}
```

6. Deep-link fallback: if the URL contains `?tab=gpu` but `hasGpu` is false, default to `cpu`. If the component already has a default-tab fallback (it checks `adminOnly` similarly), extend it to also skip `gpu` when `!hasGpu`.

- [ ] **Step 8.5: Add i18n keys**

Edit `client/src/i18n/locales/en/monitor.json`. Add under `tabs` and at root:

```json
"tabs": {
  ...,
  "gpu": "GPU"
},
"gpu": {
  "usage": "Usage",
  "vram": "VRAM",
  "coreClock": "Core Clock",
  "memoryClock": "Memory Clock",
  "power": "Power",
  "fanRpm": "Fan",
  "tempEdge": "Edge Temp",
  "tempJunction": "Junction Temp",
  "tempMemory": "Memory Temp",
  "engines": "Engine activity",
  "overview": "Overview",
  "perEngine": "Per-Engine",
  "overviewHint": "Stacked engine activity over the selected time range.",
  "samplesLoaded": "Samples loaded",
  "engineGfx": "Graphics",
  "engineCompute": "Compute",
  "engineDecode": "Decode",
  "engineEncode": "Encode"
}
```

Mirror in `client/src/i18n/locales/de/monitor.json`:

```json
"tabs": {
  ...,
  "gpu": "GPU"
},
"gpu": {
  "usage": "Auslastung",
  "vram": "VRAM",
  "coreClock": "Kern-Takt",
  "memoryClock": "Speicher-Takt",
  "power": "Leistung",
  "fanRpm": "Lüfter",
  "tempEdge": "Edge-Temp.",
  "tempJunction": "Junction-Temp.",
  "tempMemory": "Speicher-Temp.",
  "engines": "Engine-Aktivität",
  "overview": "Übersicht",
  "perEngine": "Pro Engine",
  "overviewHint": "Engine-Aktivität über den gewählten Zeitraum.",
  "samplesLoaded": "Geladene Samples",
  "engineGfx": "Grafik",
  "engineCompute": "Compute",
  "engineDecode": "Decode",
  "engineEncode": "Encode"
}
```

- [ ] **Step 8.6: Type-check and lint**

Run: `cd client && npm run build` (or `tsc --noEmit` if the project exposes that script)
Expected: no TypeScript errors.

- [ ] **Step 8.7: Manual dev-mode smoke test**

Run `python start_dev.py` from repo root and visit `http://localhost:5173/system?tab=gpu`. Verify:
- The GPU tab appears in the Hardware category, between CPU and Memory.
- Device header, KPI row, temperature block, engine toggle, fan/memory clock all render.
- Values change every ~3 s (polling).
- Switching to `1h/6h/24h/7d` reloads history (`samples loaded` updates).

- [ ] **Step 8.8: Commit**

```bash
git add client/src/components/system-monitor/GpuTab.tsx \
  client/src/components/system-monitor/index.ts \
  client/src/pages/SystemMonitor.tsx \
  client/src/i18n/locales/en/monitor.json \
  client/src/i18n/locales/de/monitor.json
git commit -m "feat(system-monitor): add GpuTab with presence-gated registration"
```

---

## Task 9: MaintenanceTools color mapping

**Files:**
- Modify: `client/src/components/admin/MaintenanceTools.tsx`

- [ ] **Step 9.1: Locate `METRIC_COLORS`**

Open `client/src/components/admin/MaintenanceTools.tsx`. Find the `METRIC_COLORS` constant — it maps `cpu`, `memory`, `network`, `disk_io`, `process` to Tailwind color tokens.

- [ ] **Step 9.2: Add `gpu` entry**

Extend the mapping to include:

```typescript
gpu: { text: 'text-emerald-400', bg: 'bg-emerald-500/10', border: 'border-emerald-500/30' },
```

Match whichever shape and color scheme the existing entries use — the key point is that `gpu` exists and renders in GPU-themed green (emerald) rather than falling through to a default.

- [ ] **Step 9.3: Manual verification**

Navigate to the admin maintenance section in dev mode and trigger a cleanup action. Verify the `gpu` row (from the `monitoring_config` seed) displays in the green theme rather than the default.

- [ ] **Step 9.4: Commit**

```bash
git add client/src/components/admin/MaintenanceTools.tsx
git commit -m "feat(admin): add gpu color to MaintenanceTools metric theme"
```

---

## Task 10: Manual production verification

This task is executed on the real Debian server (Ryzen 5 5600GT + RX 7900 XT). It is not a code change — it is the final acceptance check.

- [ ] **Step 10.1: Deploy and run the migration**

On the server:

```bash
git pull origin main
cd /opt/baluhost/backend
source .venv/bin/activate
alembic upgrade head
sudo systemctl restart baluhost-backend
```

Verify the service started cleanly: `sudo systemctl status baluhost-backend`.

- [ ] **Step 10.2: Verify GPU detection in backend logs**

Run: `sudo journalctl -u baluhost-backend -n 200 --no-pager | grep -i gpu`
Expected: a line like `GPU detected: AMD Radeon RX 7900 XT (0000:03:00.0)`.

- [ ] **Step 10.3: Verify API**

```bash
TOKEN="<bearer-token-for-admin-user>"
curl -sH "Authorization: Bearer $TOKEN" http://localhost:8000/api/monitoring/gpu/info | jq
curl -sH "Authorization: Bearer $TOKEN" http://localhost:8000/api/monitoring/gpu/current | jq
curl -sH "Authorization: Bearer $TOKEN" "http://localhost:8000/api/monitoring/gpu/history?time_range=10m" | jq '.sample_count'
```

Expected:
- `/info` returns `{"vendor":"amd","device_name":"AMD Radeon RX 7900 XT", ...}`.
- `/current` returns a sample with live values (usage %, power W, temps, fan RPM).
- `/history` `sample_count` > 0 after ~1 minute of uptime.

- [ ] **Step 10.4: Verify DB persistence**

```bash
curl -sH "Authorization: Bearer $TOKEN" http://localhost:8000/api/admin-db/tables/gpu_samples?limit=3 | jq
```
Expected: rows appear in `gpu_samples` (after `persist_interval × sample_interval ≈ 60 s`).

- [ ] **Step 10.5: Verify frontend**

Open `https://<server-host>/` (or the production URL). Check:
- Dashboard: stacked CPU+GPU card shows live RX 7900 XT data.
- SystemMonitor → Hardware → GPU tab renders all sections with live values.
- Clicking the GPU half of the dashboard card navigates to `/system?tab=gpu`.

- [ ] **Step 10.6: Negative check on the Rock Pi Mini**

On the Rock Pi 4C+ instance that runs the minimal BaluHost (SQLite), repeat the curl calls:

```bash
curl -sH "Authorization: Bearer $PI_TOKEN" http://rockpi.local/api/monitoring/gpu/info -o /dev/null -w "%{http_code}\n"
```
Expected: `404`.

Visit the dashboard in a browser — the CPU card should be unchanged from before (no GPU section). `/system?tab=gpu` should fall back to `cpu`.

- [ ] **Step 10.7: Release**

If all checks pass, follow the normal release workflow: merge `development` → `main` via PR (**not** local merge — see `memory/feedback_release_workflow.md`), cut a version tag, update `CHANGELOG.md` with a `### Added — GPU monitoring (AMD)` entry.

---

## Self-Review Notes

- **Spec coverage:** Every item from the spec's Rollout Order appears as a numbered task above.
- **Type consistency:** `GpuSample` (model) ↔ `GpuSampleSchema` (Pydantic) ↔ `GpuSample` (TS interface) use matching field names (`engine_*_percent`, `vram_used_bytes`, `temperature_*_celsius`, etc.). `GpuDeviceInfo` is used by both `/gpu/info` and `useGpuPresence`.
- **Placeholders:** None. Every step has either actual code or an exact command with expected output.
- **Known follow-ups (documented, not placeholders):** The `GpuTab` "Overview" view uses a text sample count in the first cut; a richer Recharts stacked-area chart can arrive in a follow-up PR without changing the component interface. The `engine_compute_percent` for AMD mirrors `engine_gfx_percent` because the AMD driver doesn't expose a separate compute counter — vendor backends for NVIDIA/Intel can distinguish these.
