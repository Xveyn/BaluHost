# Fan Control Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a unified temperature-source layer (hwmon + GPU + disk + composite mix sensors), FanControl-style curve types (graph/flat/target/mix/sync) with advanced tuning (start PWM, stop-below-temp, response time, PWM steps), GPU fan recognition with EINVAL diagnostics, and AMD GPU manual-mode unlock — all surfaced through the existing Fan Editor UI.

**Architecture:** Backend introduces a `TempSourceRegistry` that resolves namespaced sensor IDs (`hwmon:`, `gpu:`, `disk:`, `mix:`) into temperatures, and a `fan_curve_eval` module that dispatches by `curve_type` with a deterministic post-processing pipeline (stop → start → smoothing → quantize → hysteresis → emergency). The Fan Editor gains a Sensors panel, a curve-type selector with five typed editors, an Advanced collapse, and a GPU manual-mode toggle. One Alembic migration covers all schema additions; all new `FanConfig` columns are nullable or have defaults to preserve existing rows.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2, React 18, TypeScript, Tailwind CSS, Recharts, react-i18next, pytest.

**Spec:** `docs/superpowers/specs/2026-05-24-fan-overhaul-design.md`

---

## File Map

**Backend — Create:**
- `backend/app/services/power/fan_sources.py` — `TempSource` protocol, registry, `HwmonTempSource`, `GpuTempSource`, `DiskTempSource`, `MixTempSource`
- `backend/app/services/power/fan_curve_eval.py` — `evaluate_curve()` + post-processing pipeline
- `backend/app/services/power/fan_gpu_manual.py` — AMD GPU manual-mode helpers
- `backend/alembic/versions/<rev>_fan_overhaul.py` — migration for new tables + columns

**Backend — Modify:**
- `backend/app/models/fans.py` — add `TempSensorLabel`, `CompositeTempSensor`, extend `FanConfig`
- `backend/app/models/__init__.py` — register new models
- `backend/app/schemas/fans.py` — extend `TempSensorInfo`, `FanInfo`, `UpdateFanConfigRequest`; add composite/label schemas
- `backend/app/services/power/fan_control.py` — use registry + curve eval, capture `last_write_error`, track per-fan PWM map for sync
- `backend/app/services/power/fan_backend_linux.py` — add `is_gpu_fan`/`gpu_vendor`/`device_driver`, capture EINVAL diagnostic, expose `pwm_enable_path` for GPU manual mode
- `backend/app/services/power/fan_backend_dev.py` — mock one GPU fan + GPU/disk sensor channels
- `backend/app/api/routes/fans.py` — new endpoints + extended config handling
- `backend/app/services/power/fan_control.py` — `TempSensorData` extended with `kind`, `gpu_vendor`, `custom_label`

**Backend — Test:**
- `backend/tests/test_fan_sources.py`
- `backend/tests/test_fan_composite_api.py`
- `backend/tests/test_fan_sensor_label_api.py`
- `backend/tests/test_fan_curve_eval.py`
- `backend/tests/test_fan_gpu_recognition.py`
- `backend/tests/test_fan_gpu_manual_mode.py`
- `backend/tests/test_fan_einval_diagnostic.py`

**Frontend — Create:**
- `client/src/components/fan-control/SensorsPanel.tsx`
- `client/src/components/fan-control/CompositeSensorModal.tsx`
- `client/src/components/fan-control/CurveTypeSelector.tsx`
- `client/src/components/fan-control/CurveEditorFlat.tsx`
- `client/src/components/fan-control/CurveEditorTarget.tsx`
- `client/src/components/fan-control/CurveEditorMix.tsx`
- `client/src/components/fan-control/CurveEditorSync.tsx`
- `client/src/components/fan-control/AdvancedFanSettings.tsx`
- `client/src/components/fan-control/GpuManualModeToggle.tsx`

**Frontend — Modify:**
- `client/src/api/fan-control.ts`
- `client/src/pages/FanControl.tsx`
- `client/src/components/fan-control/FanDetails.tsx`
- `client/src/components/fan-control/FanCard.tsx`
- `client/src/components/fan-control/index.ts`
- `client/src/i18n/locales/de/system.json`
- `client/src/i18n/locales/en/system.json`

---

## Task 1: Branch setup

**Files:** none yet (git only)

- [ ] **Step 1: Update local main**

```bash
git switch main
git pull --ff-only origin main
```

Expected: working tree at `6eb57119` or newer (PR #96 merged).

- [ ] **Step 2: Create feature branch**

```bash
git switch -c feat/fan-overhaul
```

- [ ] **Step 3: Commit the design spec**

```bash
git add docs/superpowers/specs/2026-05-24-fan-overhaul-design.md
git commit -m "docs: add fan overhaul design spec"
```

- [ ] **Step 4: Commit the plan**

```bash
git add docs/superpowers/plans/2026-05-24-fan-overhaul.md
git commit -m "docs: add fan overhaul implementation plan"
```

---

## Task 2: Alembic migration — new tables + columns

**Files:**
- Create: `backend/alembic/versions/<rev>_fan_overhaul.py`

- [ ] **Step 1: Generate migration**

```bash
cd backend
alembic revision -m "fan overhaul: sensor labels, composite sensors, fan config extensions"
```

Note the revision filename printed. Do not use `--autogenerate` — write the migration by hand to keep ordering deterministic.

- [ ] **Step 2: Fill in the migration**

Replace the generated stub with:

```python
"""fan overhaul: sensor labels, composite sensors, fan config extensions

Revision ID: <auto-generated>
Revises: <auto-generated previous>
"""
from alembic import op
import sqlalchemy as sa


revision = "<auto-generated>"
down_revision = "<auto-generated previous>"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
```

- [ ] **Step 3: Apply migration in dev**

```bash
cd backend
alembic upgrade head
```

Expected: no errors. SQLite file `baluhost.db` updated.

- [ ] **Step 4: Verify schema**

```bash
sqlite3 baluhost.db ".schema fan_configs"
sqlite3 baluhost.db ".schema composite_temp_sensors"
sqlite3 baluhost.db ".schema temp_sensor_labels"
```

Expected: all new columns/tables present.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/*_fan_overhaul.py
git commit -m "feat(db): add fan overhaul migration (labels, composites, fan_config columns)"
```

---

## Task 3: ORM models

**Files:**
- Modify: `backend/app/models/fans.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Add `TempSensorLabel` to `fans.py`**

Append at end of `backend/app/models/fans.py`:

```python
class TempSensorLabel(Base):
    """User-supplied custom label for a temperature sensor."""
    __tablename__ = "temp_sensor_labels"

    sensor_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    custom_label: Mapped[str] = mapped_column(String(100), nullable=False)
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
```

- [ ] **Step 2: Extend `FanConfig` in `fans.py`**

Add these columns inside the existing `class FanConfig(Base)` block, right after the `hysteresis_celsius` line:

```python
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
```

- [ ] **Step 3: Register in `models/__init__.py`**

Open `backend/app/models/__init__.py`, find the section where `FanConfig`, `FanSample`, etc. are imported and re-exported. Add `TempSensorLabel` and `CompositeTempSensor` next to them.

- [ ] **Step 4: Smoke test — model imports work**

```bash
cd backend
python -c "from app.models.fans import TempSensorLabel, CompositeTempSensor, FanConfig; print(FanConfig.__table__.columns.keys())"
```

Expected output includes `curve_type`, `flat_pwm_percent`, ..., `pwm_steps`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/fans.py backend/app/models/__init__.py
git commit -m "feat(models): add TempSensorLabel, CompositeTempSensor; extend FanConfig"
```

---

## Task 4: TempSource registry — protocol + hwmon source

**Files:**
- Create: `backend/app/services/power/fan_sources.py`
- Test: `backend/tests/test_fan_sources.py`

- [ ] **Step 1: Write the failing test for hwmon parsing & resolution**

Create `backend/tests/test_fan_sources.py`:

```python
"""Tests for fan source registry."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.power.fan_sources import (
    TempSourceRegistry,
    HwmonTempSource,
    MixTempSource,
)


@pytest.mark.asyncio
async def test_hwmon_source_resolves_temp():
    src = HwmonTempSource(
        sensor_id="hwmon0_temp1",
        device_name="k10temp",
        backend_label="Tctl",
        is_cpu_sensor=True,
        read_fn=AsyncMock(return_value=42.5),
    )
    assert src.id == "hwmon:hwmon0_temp1"
    assert src.kind == "hwmon"
    assert await src.current_temp() == 42.5


@pytest.mark.asyncio
async def test_registry_accepts_legacy_unprefixed_id():
    src = HwmonTempSource(
        sensor_id="hwmon0_temp1",
        device_name="k10temp",
        backend_label="Tctl",
        is_cpu_sensor=True,
        read_fn=AsyncMock(return_value=40.0),
    )
    registry = TempSourceRegistry()
    registry.register(src)

    # Legacy ID (no namespace) must resolve as if "hwmon:" was prepended
    assert await registry.get_temp("hwmon0_temp1") == 40.0
    assert await registry.get_temp("hwmon:hwmon0_temp1") == 40.0


@pytest.mark.asyncio
async def test_registry_returns_none_for_unknown_id():
    registry = TempSourceRegistry()
    assert await registry.get_temp("hwmon:does_not_exist") is None
```

- [ ] **Step 2: Run — expect FAIL (module missing)**

```bash
cd backend
python -m pytest tests/test_fan_sources.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.power.fan_sources'`.

- [ ] **Step 3: Implement the protocol + registry skeleton**

Create `backend/app/services/power/fan_sources.py`:

```python
"""Unified temperature source layer.

Resolves namespaced sensor IDs (hwmon:, gpu:, disk:, mix:) into temperatures.
Used by FanControlService to look up any temperature regardless of origin.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Awaitable, Callable, Dict, List, Literal, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


SourceKind = Literal["hwmon", "gpu", "disk", "mix"]


@runtime_checkable
class TempSource(Protocol):
    """Resolves a sensor ID to a current temperature in °C."""

    id: str
    kind: SourceKind
    device_name: str
    backend_label: Optional[str]
    is_cpu_sensor: bool

    async def current_temp(self) -> Optional[float]: ...


class HwmonTempSource:
    """Wraps a single hwmon temp_input file."""

    kind: SourceKind = "hwmon"

    def __init__(
        self,
        sensor_id: str,                                # legacy: "hwmon0_temp1"
        device_name: str,
        backend_label: Optional[str],
        is_cpu_sensor: bool,
        read_fn: Callable[[], Awaitable[Optional[float]]],
    ) -> None:
        self.id = f"hwmon:{sensor_id}"
        self.legacy_id = sensor_id
        self.device_name = device_name
        self.backend_label = backend_label
        self.is_cpu_sensor = is_cpu_sensor
        self._read = read_fn

    async def current_temp(self) -> Optional[float]:
        return await self._read()


class TempSourceRegistry:
    """Registry of temperature sources keyed by namespaced ID."""

    def __init__(self) -> None:
        self._sources: Dict[str, TempSource] = {}
        self._labels: Dict[str, str] = {}  # sensor_id -> custom_label

    def register(self, source: TempSource) -> None:
        self._sources[source.id] = source

    def clear(self) -> None:
        self._sources.clear()

    def all_sources(self) -> List[TempSource]:
        return list(self._sources.values())

    def set_label(self, sensor_id: str, label: str) -> None:
        self._labels[self._normalize_id(sensor_id)] = label

    def clear_label(self, sensor_id: str) -> None:
        self._labels.pop(self._normalize_id(sensor_id), None)

    def display_label(self, sensor_id: str) -> str:
        nid = self._normalize_id(sensor_id)
        if nid in self._labels:
            return self._labels[nid]
        src = self._sources.get(nid)
        if src and src.backend_label:
            return src.backend_label
        if src:
            return src.device_name
        return sensor_id

    async def get_temp(self, sensor_id: str) -> Optional[float]:
        nid = self._normalize_id(sensor_id)
        src = self._sources.get(nid)
        if src is None:
            return None
        try:
            return await src.current_temp()
        except Exception as exc:
            logger.debug("Source %s temp read failed: %s", nid, exc)
            return None

    @staticmethod
    def _normalize_id(sensor_id: str) -> str:
        """Accept both namespaced (hwmon:foo) and legacy (foo) IDs."""
        if ":" in sensor_id:
            return sensor_id
        return f"hwmon:{sensor_id}"
```

- [ ] **Step 4: Run — expect PASS**

```bash
python -m pytest tests/test_fan_sources.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/fan_sources.py backend/tests/test_fan_sources.py
git commit -m "feat(power): add TempSource protocol + registry with hwmon source"
```

---

## Task 5: GPU + Disk + Mix sources

**Files:**
- Modify: `backend/app/services/power/fan_sources.py`
- Modify: `backend/tests/test_fan_sources.py`

- [ ] **Step 1: Add failing tests**

Append to `backend/tests/test_fan_sources.py`:

```python
from app.services.power.fan_sources import GpuTempSource, DiskTempSource, MixTempSource


@pytest.mark.asyncio
async def test_gpu_source_reads_channel():
    src = GpuTempSource(channel="edge", read_fn=AsyncMock(return_value=55.3))
    assert src.id == "gpu:edge"
    assert src.kind == "gpu"
    assert await src.current_temp() == 55.3


@pytest.mark.asyncio
async def test_disk_source():
    src = DiskTempSource(device="sda", read_fn=AsyncMock(return_value=38.0))
    assert src.id == "disk:sda"
    assert src.kind == "disk"
    assert await src.current_temp() == 38.0


@pytest.mark.asyncio
async def test_mix_source_max():
    registry = TempSourceRegistry()
    registry.register(HwmonTempSource("h0_t1", "k10temp", "Tctl", True, AsyncMock(return_value=50.0)))
    registry.register(HwmonTempSource("h1_t1", "amdgpu", "edge", False, AsyncMock(return_value=70.0)))

    mix = MixTempSource(
        composite_id="mix:abc",
        name="hottest",
        function="max",
        source_ids=["hwmon:h0_t1", "hwmon:h1_t1"],
        registry=registry,
    )
    registry.register(mix)
    assert await mix.current_temp() == 70.0


@pytest.mark.asyncio
async def test_mix_source_avg():
    registry = TempSourceRegistry()
    registry.register(HwmonTempSource("h0_t1", "k10temp", None, True, AsyncMock(return_value=40.0)))
    registry.register(HwmonTempSource("h1_t1", "k10temp", None, True, AsyncMock(return_value=60.0)))

    mix = MixTempSource("mix:x", "avg", "avg", ["hwmon:h0_t1", "hwmon:h1_t1"], registry)
    assert await mix.current_temp() == 50.0


@pytest.mark.asyncio
async def test_mix_source_ignores_unavailable_subsource():
    registry = TempSourceRegistry()
    registry.register(HwmonTempSource("h0_t1", "k10temp", None, True, AsyncMock(return_value=50.0)))
    registry.register(HwmonTempSource("h1_t1", "k10temp", None, True, AsyncMock(return_value=None)))

    mix = MixTempSource("mix:x", "max", "max", ["hwmon:h0_t1", "hwmon:h1_t1"], registry)
    assert await mix.current_temp() == 50.0  # None ignored, max of remaining


@pytest.mark.asyncio
async def test_mix_source_detects_cycle():
    registry = TempSourceRegistry()
    mix_a = MixTempSource("mix:a", "a", "max", ["mix:b"], registry)
    mix_b = MixTempSource("mix:b", "b", "max", ["mix:a"], registry)
    registry.register(mix_a)
    registry.register(mix_b)

    # Cycle detection should return None rather than recurse forever
    assert await mix_a.current_temp() is None
```

- [ ] **Step 2: Run — expect FAIL**

```bash
python -m pytest tests/test_fan_sources.py -v
```

Expected: 4 new test failures (`AttributeError: module ... has no attribute 'GpuTempSource'`).

- [ ] **Step 3: Implement the three new sources**

Append to `backend/app/services/power/fan_sources.py`:

```python
class GpuTempSource:
    """One temperature channel of the dedicated GPU (edge/junction/mem)."""

    kind: SourceKind = "gpu"

    def __init__(
        self,
        channel: str,                                  # "edge" | "junction" | "mem"
        read_fn: Callable[[], Awaitable[Optional[float]]],
        gpu_vendor: str = "amd",
    ) -> None:
        self.id = f"gpu:{channel}"
        self.channel = channel
        self.device_name = f"{gpu_vendor}gpu"
        self.backend_label = channel
        self.is_cpu_sensor = False
        self._read = read_fn

    async def current_temp(self) -> Optional[float]:
        return await self._read()


class DiskTempSource:
    """SMART-reported disk temperature for one block device."""

    kind: SourceKind = "disk"

    def __init__(
        self,
        device: str,                                   # "sda", "nvme0n1"
        read_fn: Callable[[], Awaitable[Optional[float]]],
    ) -> None:
        self.id = f"disk:{device}"
        self.device = device
        self.device_name = device
        self.backend_label = None
        self.is_cpu_sensor = False
        self._read = read_fn

    async def current_temp(self) -> Optional[float]:
        return await self._read()


class MixTempSource:
    """Composite source combining N other sources via max/min/avg."""

    kind: SourceKind = "mix"
    _MAX_DEPTH = 5

    def __init__(
        self,
        composite_id: str,                             # "mix:<uuid>"
        name: str,
        function: str,                                 # "max" | "min" | "avg"
        source_ids: List[str],
        registry: "TempSourceRegistry",
    ) -> None:
        if not composite_id.startswith("mix:"):
            composite_id = f"mix:{composite_id}"
        self.id = composite_id
        self.composite_id = composite_id
        self.name = name
        self.function = function
        self.source_ids = source_ids
        self._registry = registry
        self.device_name = "composite"
        self.backend_label = name
        self.is_cpu_sensor = False

    async def current_temp(self, _depth: int = 0, _path: Optional[set] = None) -> Optional[float]:
        if _depth >= self._MAX_DEPTH:
            logger.warning("MixTempSource %s exceeded max depth", self.id)
            return None
        path = _path if _path is not None else set()
        if self.id in path:
            logger.warning("MixTempSource cycle detected at %s", self.id)
            return None
        path = path | {self.id}

        values: List[float] = []
        for sid in self.source_ids:
            sub = self._registry._sources.get(self._registry._normalize_id(sid))
            if isinstance(sub, MixTempSource):
                v = await sub.current_temp(_depth + 1, path)
            elif sub is not None:
                try:
                    v = await sub.current_temp()
                except Exception:
                    v = None
            else:
                v = None
            if v is not None:
                values.append(v)

        if not values:
            return None
        if self.function == "max":
            return max(values)
        if self.function == "min":
            return min(values)
        if self.function == "avg":
            return sum(values) / len(values)
        return None
```

- [ ] **Step 4: Run — expect PASS**

```bash
python -m pytest tests/test_fan_sources.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/fan_sources.py backend/tests/test_fan_sources.py
git commit -m "feat(power): add GPU, Disk, and Mix temperature sources"
```

---

## Task 6: Fan curve evaluation module

**Files:**
- Create: `backend/app/services/power/fan_curve_eval.py`
- Test: `backend/tests/test_fan_curve_eval.py`

- [ ] **Step 1: Write failing tests covering all curve types + pipeline**

Create `backend/tests/test_fan_curve_eval.py`:

```python
"""Tests for fan_curve_eval.evaluate_curve."""
from types import SimpleNamespace

import pytest

from app.services.power.fan_curve_eval import evaluate_curve


def _cfg(**overrides):
    """Mock FanConfig with sensible defaults."""
    base = dict(
        curve_type="graph",
        curve_json='[{"temp":40,"pwm":30},{"temp":80,"pwm":100}]',
        flat_pwm_percent=None,
        target_temp_celsius=None,
        target_pwm_percent=None,
        mix_curve_a_id=None,
        mix_curve_b_id=None,
        mix_function=None,
        sync_fan_id=None,
        start_pwm_percent=None,
        stop_below_temp_celsius=None,
        response_time_seconds=0.0,
        pwm_steps=1,
        min_pwm_percent=0,
        max_pwm_percent=100,
        hysteresis_celsius=0.0,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_graph_interpolates():
    out = evaluate_curve(_cfg(), temp=60.0, prev_pwm=0, other_fan_pwms={},
                         profile_loader=lambda _id: [], dt_seconds=1.0)
    # 60 is midpoint of 40–80 → midpoint PWM (30 + 100) / 2 = 65
    assert out == 65


def test_flat_returns_constant():
    out = evaluate_curve(
        _cfg(curve_type="flat", flat_pwm_percent=42),
        temp=99.0, prev_pwm=0, other_fan_pwms={}, profile_loader=lambda _: [], dt_seconds=1.0
    )
    assert out == 42


def test_target_holds_at_target_temp():
    cfg = _cfg(curve_type="target", target_temp_celsius=70, target_pwm_percent=80)
    # Below target: linear ramp from (0,0) to (70,80)
    assert evaluate_curve(cfg, 35.0, 0, {}, lambda _: [], 1.0) == 40
    # At/above target: hold at target_pwm
    assert evaluate_curve(cfg, 70.0, 0, {}, lambda _: [], 1.0) == 80
    assert evaluate_curve(cfg, 95.0, 0, {}, lambda _: [], 1.0) == 80


def test_mix_function_max():
    cfg = _cfg(curve_type="mix", mix_curve_a_id=1, mix_curve_b_id=2, mix_function="max")
    profiles = {
        1: [{"temp": 40, "pwm": 30}, {"temp": 80, "pwm": 60}],
        2: [{"temp": 40, "pwm": 50}, {"temp": 80, "pwm": 100}],
    }
    # At 60°C: curve1 → 45, curve2 → 75 → max=75
    out = evaluate_curve(cfg, 60.0, 0, {}, profiles.get, 1.0)
    assert out == 75


def test_mix_function_sum_clamps_to_100():
    cfg = _cfg(curve_type="mix", mix_curve_a_id=1, mix_curve_b_id=2, mix_function="sum")
    profiles = {
        1: [{"temp": 40, "pwm": 60}, {"temp": 80, "pwm": 80}],
        2: [{"temp": 40, "pwm": 50}, {"temp": 80, "pwm": 70}],
    }
    out = evaluate_curve(cfg, 80.0, 0, {}, profiles.get, 1.0)
    assert out == 100  # 80 + 70 = 150 → clamped


def test_sync_copies_master_pwm():
    cfg = _cfg(curve_type="sync", sync_fan_id="hwmon0_pwm2")
    out = evaluate_curve(cfg, 50.0, 0, {"hwmon0_pwm2": 73}, lambda _: [], 1.0)
    assert out == 73


def test_sync_falls_back_to_prev_when_master_missing():
    cfg = _cfg(curve_type="sync", sync_fan_id="missing")
    out = evaluate_curve(cfg, 50.0, 40, {}, lambda _: [], 1.0)
    assert out == 40


def test_stop_below_temp_sets_pwm_zero():
    cfg = _cfg(stop_below_temp_celsius=35.0, hysteresis_celsius=2.0)
    out = evaluate_curve(cfg, 30.0, 50, {}, lambda _: [], 1.0)
    assert out == 0


def test_stop_below_temp_releases_at_threshold():
    cfg = _cfg(stop_below_temp_celsius=35.0, hysteresis_celsius=2.0)
    # Was at 0 (below stop), now at 60 → should resume normal curve
    out = evaluate_curve(cfg, 60.0, 0, {}, lambda _: [], 1.0)
    assert out == 65  # graph midpoint


def test_start_pwm_jumps_from_zero():
    cfg = _cfg(start_pwm_percent=40)
    # Curve at 50 would give 50% — but if prev was 0, jump to max(50, 40) = 50
    out = evaluate_curve(cfg, 50.0, 0, {}, lambda _: [], 1.0)
    assert out == 50


def test_start_pwm_kicks_in_when_curve_low():
    cfg = _cfg(curve_json='[{"temp":40,"pwm":10},{"temp":80,"pwm":100}]', start_pwm_percent=30)
    # At 42°C: curve → ~12. Prev was 0, so jump to max(12, 30) = 30
    out = evaluate_curve(cfg, 42.0, 0, {}, lambda _: [], 1.0)
    assert out == 30


def test_response_time_smooths_changes():
    cfg = _cfg(response_time_seconds=4.0)
    # dt=1, response=4 → α=0.25. target=80, prev=20 → 0.25*80 + 0.75*20 = 35
    out = evaluate_curve(cfg, 80.0, 20, {}, lambda _: [], 1.0)
    assert out == 35


def test_pwm_steps_quantize():
    cfg = _cfg(pwm_steps=10)
    out = evaluate_curve(cfg, 60.0, 0, {}, lambda _: [], 1.0)  # raw 65 → quantize to 70
    assert out == 70


def test_min_max_clamp_applied_last():
    cfg = _cfg(min_pwm_percent=40, max_pwm_percent=90)
    # Curve gives 65, but min/max already pass through; raise min above raw
    cfg2 = _cfg(min_pwm_percent=80, max_pwm_percent=90)
    out = evaluate_curve(cfg2, 60.0, 0, {}, lambda _: [], 1.0)
    assert out == 80


def test_pipeline_order_emergency_handled_outside():
    # evaluate_curve never returns 100 forced — emergency override is the caller's job
    cfg = _cfg(curve_type="flat", flat_pwm_percent=20, max_pwm_percent=90)
    out = evaluate_curve(cfg, 200.0, 0, {}, lambda _: [], 1.0)
    assert out == 20
```

- [ ] **Step 2: Run — expect FAIL (no module)**

```bash
python -m pytest tests/test_fan_curve_eval.py -v
```

- [ ] **Step 3: Implement `evaluate_curve`**

Create `backend/app/services/power/fan_curve_eval.py`:

```python
"""Curve type dispatch + post-processing pipeline.

Pipeline order (matters):
1. Resolve raw target from curve_type
2. stop_below_temp_celsius → may force 0
3. start_pwm_percent → minimum spin-up when prev was 0
4. response_time_seconds → exponential smoothing
5. pwm_steps → quantize
6. min/max clamp
Hysteresis and emergency override are applied by the caller (FanControlService).
"""
from __future__ import annotations

import json
import logging
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


def evaluate_curve(
    config,                                            # FanConfig-shaped (real or SimpleNamespace)
    temp: Optional[float],
    prev_pwm: int,
    other_fan_pwms: Dict[str, int],
    profile_loader: Callable[[int], List[dict]],
    dt_seconds: float,
) -> int:
    """Compute target PWM (0-100) given config, temp, and previous PWM."""
    curve_type = getattr(config, "curve_type", "graph")

    # --- 1. Raw target per curve type ---
    if curve_type == "flat":
        target = int(config.flat_pwm_percent or 0)

    elif curve_type == "target":
        if temp is None or config.target_temp_celsius is None or config.target_pwm_percent is None:
            target = prev_pwm
        elif temp >= config.target_temp_celsius:
            target = int(config.target_pwm_percent)
        else:
            ratio = max(0.0, temp / config.target_temp_celsius)
            target = round(ratio * config.target_pwm_percent)

    elif curve_type == "mix":
        a = _interpolate(profile_loader(config.mix_curve_a_id) if config.mix_curve_a_id else [], temp)
        b = _interpolate(profile_loader(config.mix_curve_b_id) if config.mix_curve_b_id else [], temp)
        if config.mix_function == "sum":
            target = min(100, a + b)
        else:  # "max" or unknown defaults to max
            target = max(a, b)

    elif curve_type == "sync":
        target = other_fan_pwms.get(config.sync_fan_id or "", prev_pwm)

    else:  # "graph"
        points = _parse_curve_json(config.curve_json)
        target = _interpolate(points, temp)

    # --- 2. stop_below_temp_celsius ---
    if config.stop_below_temp_celsius is not None and temp is not None:
        hysteresis = getattr(config, "hysteresis_celsius", 0.0) or 0.0
        # While running, drop to 0 when temp falls below (threshold - hysteresis).
        # Once at 0, only resume when temp rises back above threshold.
        if prev_pwm == 0:
            if temp < config.stop_below_temp_celsius:
                return 0
        else:
            if temp < config.stop_below_temp_celsius - hysteresis:
                return 0

    # --- 3. start_pwm_percent ---
    if (
        config.start_pwm_percent is not None
        and prev_pwm == 0
        and target > 0
        and target < config.start_pwm_percent
    ):
        target = int(config.start_pwm_percent)

    # --- 4. response_time_seconds (exponential smoothing) ---
    rt = float(getattr(config, "response_time_seconds", 0.0) or 0.0)
    if rt > 0.0 and dt_seconds > 0.0:
        alpha = min(1.0, dt_seconds / rt)
        target = round(alpha * target + (1 - alpha) * prev_pwm)

    # --- 5. pwm_steps quantization ---
    steps = int(getattr(config, "pwm_steps", 1) or 1)
    if steps > 1:
        target = round(target / steps) * steps

    # --- 6. min/max clamp ---
    min_pwm = int(getattr(config, "min_pwm_percent", 0) or 0)
    max_pwm = int(getattr(config, "max_pwm_percent", 100) or 100)
    target = max(min_pwm, min(max_pwm, target))

    return int(target)


def _interpolate(points: List[dict], temp: Optional[float]) -> int:
    if not points or temp is None:
        return 0
    pts = sorted(points, key=lambda p: p["temp"])
    if len(pts) == 1:
        return int(pts[0]["pwm"])
    if temp <= pts[0]["temp"]:
        return int(pts[0]["pwm"])
    if temp >= pts[-1]["temp"]:
        return int(pts[-1]["pwm"])
    for i in range(len(pts) - 1):
        p1, p2 = pts[i], pts[i + 1]
        if p1["temp"] <= temp <= p2["temp"]:
            ratio = (temp - p1["temp"]) / (p2["temp"] - p1["temp"])
            return round(p1["pwm"] + (p2["pwm"] - p1["pwm"]) * ratio)
    return int(pts[-1]["pwm"])


def _parse_curve_json(raw: Optional[str]) -> List[dict]:
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []
```

- [ ] **Step 4: Run — expect PASS**

```bash
python -m pytest tests/test_fan_curve_eval.py -v
```

Expected: 14 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/fan_curve_eval.py backend/tests/test_fan_curve_eval.py
git commit -m "feat(power): add fan_curve_eval with 5 curve types and post-processing"
```

---

## Task 7: GPU recognition + EINVAL diagnostic in Linux backend

**Files:**
- Modify: `backend/app/services/power/fan_backend_linux.py`
- Modify: `backend/app/services/power/fan_control.py` (FanData fields)
- Test: `backend/tests/test_fan_gpu_recognition.py`
- Test: `backend/tests/test_fan_einval_diagnostic.py`

- [ ] **Step 1: Extend `FanData` dataclass**

In `backend/app/services/power/fan_control.py`, add to the `FanData` dataclass:

```python
    # GPU recognition + write diagnostics
    is_gpu_fan: bool = False
    gpu_vendor: Optional[str] = None
    device_driver: Optional[str] = None
    last_write_error: Optional[str] = None
```

- [ ] **Step 2: Write failing test for GPU recognition**

Create `backend/tests/test_fan_gpu_recognition.py`:

```python
"""Tests that the hwmon scanner labels amdgpu/nouveau PWM fans as GPU fans."""
from pathlib import Path

import pytest

from app.services.power.fan_backend_linux import LinuxFanControlBackend
from app.core.config import get_settings


def _make_hwmon(tmp_path: Path, hwmon_name: str, driver: str) -> Path:
    d = tmp_path / "sys" / "class" / "hwmon" / hwmon_name
    d.mkdir(parents=True)
    (d / "name").write_text(driver + "\n")
    (d / "pwm1").write_text("128\n")
    (d / "fan1_input").write_text("1200\n")
    return d


@pytest.mark.asyncio
async def test_amdgpu_fan_tagged_as_gpu(tmp_path, monkeypatch):
    _make_hwmon(tmp_path, "hwmon3", "amdgpu")
    backend = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend, "_hwmon_base", tmp_path / "sys" / "class" / "hwmon")
    await backend._scan_pwm_fans()
    fans = await backend.get_fans()
    assert any(f.is_gpu_fan and f.gpu_vendor == "amd" for f in fans)


@pytest.mark.asyncio
async def test_chipset_fan_not_tagged(tmp_path, monkeypatch):
    _make_hwmon(tmp_path, "hwmon1", "nct6798")
    backend = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend, "_hwmon_base", tmp_path / "sys" / "class" / "hwmon")
    await backend._scan_pwm_fans()
    fans = await backend.get_fans()
    assert all(not f.is_gpu_fan for f in fans)
    assert all(f.device_driver == "nct6798" for f in fans)
```

- [ ] **Step 3: Update `_scan_pwm_fans` in linux backend**

In `backend/app/services/power/fan_backend_linux.py`, inside `_scan_pwm_fans()`, after `hwmon_name_value` is read, compute:

```python
is_gpu_fan = hwmon_name_value in {"amdgpu", "nouveau"}
gpu_vendor = "amd" if hwmon_name_value == "amdgpu" else ("nvidia" if hwmon_name_value == "nouveau" else None)
```

And in the `new_cache[fan_id] = {...}` dict literal, add:

```python
"is_gpu_fan": is_gpu_fan,
"gpu_vendor": gpu_vendor,
"device_driver": hwmon_name_value,
```

Then in `get_fans()`, when building `FanData(...)`, pass the new fields:

```python
fans.append(FanData(
    fan_id=fan_id,
    name=fan_info["name"],
    # ... existing fields ...
    is_gpu_fan=fan_info.get("is_gpu_fan", False),
    gpu_vendor=fan_info.get("gpu_vendor"),
    device_driver=fan_info.get("device_driver"),
    last_write_error=fan_info.get("last_write_error"),
))
```

- [ ] **Step 4: Run GPU recognition tests — expect PASS**

```bash
python -m pytest tests/test_fan_gpu_recognition.py -v
```

- [ ] **Step 5: Write failing test for EINVAL diagnostic**

Create `backend/tests/test_fan_einval_diagnostic.py`:

```python
"""When pwm write fails, capture driver name + pwm_enable in last_write_error."""
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.power.fan_backend_linux import LinuxFanControlBackend
from app.core.config import get_settings


@pytest.mark.asyncio
async def test_write_failure_captures_diagnostic(tmp_path, monkeypatch):
    d = tmp_path / "sys" / "class" / "hwmon" / "hwmon1"
    d.mkdir(parents=True)
    (d / "name").write_text("amdgpu\n")
    (d / "pwm1").write_text("128\n")
    (d / "fan1_input").write_text("1200\n")
    (d / "pwm1_enable").write_text("2\n")

    backend = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend, "_hwmon_base", tmp_path / "sys" / "class" / "hwmon")
    await backend._scan_pwm_fans()

    fan_id = next(iter(backend._fan_cache))

    # Force direct write to fail with OSError(EINVAL) and sudo path to also fail
    def fail_write(self_, value):
        raise OSError(22, "Invalid argument")

    monkeypatch.setattr(Path, "write_text", fail_write)
    with patch("subprocess.run") as srun:
        srun.return_value.returncode = 1
        srun.return_value.stderr = b"Invalid argument"
        ok = await backend.set_pwm(fan_id, 80)
    assert ok is False
    assert backend._fan_cache[fan_id].get("last_write_error") is not None
    err = backend._fan_cache[fan_id]["last_write_error"]
    assert "amdgpu" in err
    assert "pwm_enable=2" in err
```

- [ ] **Step 6: Capture diagnostic in `_write_hwmon_file` / `set_pwm`**

In `backend/app/services/power/fan_backend_linux.py`, modify `set_pwm` so the failure path stores a diagnostic on `fan_info`:

```python
async def set_pwm(self, fan_id: str, pwm_percent: int) -> bool:
    if fan_id not in self._fan_cache:
        logger.warning(f"Fan {fan_id} not found in cache")
        return False
    fan_info = self._fan_cache[fan_id]
    pwm_path = fan_info["pwm_path"]
    pwm_enable_path = fan_info.get("pwm_enable_path")

    pwm_percent = max(0, min(100, pwm_percent))
    pwm_value = self._percent_to_pwm(pwm_percent)

    if pwm_enable_path:
        await self._write_hwmon_file(pwm_enable_path, "1")

    success = await self._write_hwmon_file(pwm_path, str(pwm_value))
    if success:
        fan_info["last_write_error"] = None
        logger.debug(f"Set {fan_id} PWM to {pwm_percent}% ({pwm_value}/255)")
        return True

    # Capture diagnostic
    driver = fan_info.get("device_driver", "unknown")
    enable_val = None
    if pwm_enable_path:
        v = await self._read_hwmon_file(pwm_enable_path)
        enable_val = v if v is not None else "?"
    fan_info["last_write_error"] = (
        f"PWM write rejected by kernel (driver={driver}, pwm_enable={enable_val}). "
        f"For AMD GPUs: enable manual mode in the UI."
    )
    logger.error(f"Failed to write PWM for {fan_id}: {fan_info['last_write_error']}")
    return False
```

- [ ] **Step 7: Run diagnostic test — expect PASS**

```bash
python -m pytest tests/test_fan_einval_diagnostic.py tests/test_fan_gpu_recognition.py -v
```

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/power/fan_backend_linux.py backend/app/services/power/fan_control.py backend/tests/test_fan_gpu_recognition.py backend/tests/test_fan_einval_diagnostic.py
git commit -m "feat(power): GPU fan recognition + EINVAL diagnostic capture"
```

---

## Task 8: AMD GPU manual-mode helper

**Files:**
- Create: `backend/app/services/power/fan_gpu_manual.py`
- Test: `backend/tests/test_fan_gpu_manual_mode.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_fan_gpu_manual_mode.py`:

```python
"""Tests for AMD GPU manual-mode unlock helper."""
from pathlib import Path
import pytest

from app.services.power.fan_gpu_manual import enable_amd_manual, disable_amd_manual, AmdManualState


@pytest.mark.asyncio
async def test_enable_writes_manual_and_pwm_enable(tmp_path):
    # Lay out a fake amdgpu device tree
    drm = tmp_path / "sys" / "class" / "drm" / "card0"
    device = drm / "device"
    hwmon = device / "hwmon" / "hwmon3"
    hwmon.mkdir(parents=True)
    (device / "vendor").write_text("0x1002\n")
    (device / "pp_dpm_sclk").write_text("0: 500Mhz\n1: 1500Mhz *\n")
    (device / "power_dpm_force_performance_level").write_text("auto\n")
    (hwmon / "name").write_text("amdgpu\n")
    (hwmon / "pwm1_enable").write_text("2\n")

    state = await enable_amd_manual(hwmon_dir=hwmon, drm_root=tmp_path / "sys" / "class" / "drm")

    assert state.previous_level == "auto"
    assert state.previous_pwm_enable == 2
    assert (device / "power_dpm_force_performance_level").read_text().strip() == "manual"
    assert (hwmon / "pwm1_enable").read_text().strip() == "1"


@pytest.mark.asyncio
async def test_disable_restores_previous(tmp_path):
    drm = tmp_path / "sys" / "class" / "drm" / "card0"
    device = drm / "device"
    hwmon = device / "hwmon" / "hwmon3"
    hwmon.mkdir(parents=True)
    (device / "vendor").write_text("0x1002\n")
    (device / "pp_dpm_sclk").write_text("0: 1500Mhz *\n")
    (device / "power_dpm_force_performance_level").write_text("manual\n")
    (hwmon / "name").write_text("amdgpu\n")
    (hwmon / "pwm1_enable").write_text("1\n")

    state = AmdManualState(previous_level="auto", previous_pwm_enable=2)
    await disable_amd_manual(hwmon_dir=hwmon, drm_root=tmp_path / "sys" / "class" / "drm", state=state)

    assert (device / "power_dpm_force_performance_level").read_text().strip() == "auto"
    assert (hwmon / "pwm1_enable").read_text().strip() == "2"
```

- [ ] **Step 2: Run — expect FAIL (no module)**

- [ ] **Step 3: Implement helper**

Create `backend/app/services/power/fan_gpu_manual.py`:

```python
"""AMD GPU manual fan-control unlock.

Required so PWM writes to amdgpu hwmon are accepted by the kernel:
- power_dpm_force_performance_level=manual
- pwm{n}_enable=1

State of the prior values is captured so disable_amd_manual can revert.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

AMD_VENDOR_ID = "0x1002"


@dataclass
class AmdManualState:
    """Captured original values prior to enabling manual mode."""
    previous_level: str
    previous_pwm_enable: int


async def enable_amd_manual(hwmon_dir: Path, drm_root: Optional[Path] = None) -> AmdManualState:
    """Enable manual fan control on the AMD GPU whose hwmon_dir is given."""
    device = _device_from_hwmon(hwmon_dir, drm_root)
    if device is None:
        raise RuntimeError(f"Could not locate amdgpu device for {hwmon_dir}")

    level_path = device / "power_dpm_force_performance_level"
    prev_level = await asyncio.to_thread(lambda: level_path.read_text().strip())

    pwm_enable_path = _find_pwm_enable(hwmon_dir)
    prev_enable = 2
    if pwm_enable_path is not None:
        try:
            prev_enable = int(await asyncio.to_thread(lambda: pwm_enable_path.read_text().strip()))
        except (OSError, ValueError):
            prev_enable = 2

    await asyncio.to_thread(level_path.write_text, "manual")
    if pwm_enable_path is not None:
        await asyncio.to_thread(pwm_enable_path.write_text, "1")

    logger.info("AMD GPU manual mode enabled (prev_level=%s, prev_enable=%s)", prev_level, prev_enable)
    return AmdManualState(previous_level=prev_level, previous_pwm_enable=prev_enable)


async def disable_amd_manual(hwmon_dir: Path, drm_root: Optional[Path], state: AmdManualState) -> None:
    device = _device_from_hwmon(hwmon_dir, drm_root)
    if device is None:
        raise RuntimeError(f"Could not locate amdgpu device for {hwmon_dir}")

    level_path = device / "power_dpm_force_performance_level"
    await asyncio.to_thread(level_path.write_text, state.previous_level or "auto")

    pwm_enable_path = _find_pwm_enable(hwmon_dir)
    if pwm_enable_path is not None:
        await asyncio.to_thread(pwm_enable_path.write_text, str(state.previous_pwm_enable))

    logger.info("AMD GPU manual mode disabled (restored level=%s, enable=%s)",
                state.previous_level, state.previous_pwm_enable)


def _device_from_hwmon(hwmon_dir: Path, drm_root: Optional[Path]) -> Optional[Path]:
    """Walk up from hwmon dir to find the amdgpu PCI device directory."""
    # hwmon_dir typically looks like: <drm>/card0/device/hwmon/hwmonN
    p = hwmon_dir.resolve()
    for parent in p.parents:
        if parent.name == "device" and (parent / "vendor").exists():
            try:
                if (parent / "vendor").read_text().strip() == AMD_VENDOR_ID:
                    return parent
            except OSError:
                pass
    return None


def _find_pwm_enable(hwmon_dir: Path) -> Optional[Path]:
    """First pwmN_enable file in the hwmon dir."""
    for p in sorted(hwmon_dir.glob("pwm*_enable")):
        if re.fullmatch(r"pwm\d+_enable", p.name):
            return p
    return None
```

- [ ] **Step 4: Run — expect PASS**

```bash
python -m pytest tests/test_fan_gpu_manual_mode.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/fan_gpu_manual.py backend/tests/test_fan_gpu_manual_mode.py
git commit -m "feat(power): AMD GPU manual-mode unlock helper with state restore"
```

---

## Task 9: Wire registry + curve eval into FanControlService

**Files:**
- Modify: `backend/app/services/power/fan_control.py`

- [ ] **Step 1: Add registry build helpers**

In `backend/app/services/power/fan_control.py`, add at the top:

```python
from app.services.power.fan_sources import (
    TempSourceRegistry, HwmonTempSource, GpuTempSource, DiskTempSource, MixTempSource,
)
from app.services.power.fan_curve_eval import evaluate_curve
import time as _time
```

Add `_registry: TempSourceRegistry` and `_last_pwm_by_fan: Dict[str, int]` and `_last_tick_ts: float` to `FanControlService.__init__`:

```python
        self._registry: TempSourceRegistry = TempSourceRegistry()
        self._last_pwm_by_fan: Dict[str, int] = {}
        self._last_tick_ts: float = 0.0
```

- [ ] **Step 2: Add `_rebuild_registry()` method**

Add as a new method on `FanControlService`:

```python
    async def _rebuild_registry(self) -> None:
        """(Re)populate the registry with all current sources."""
        self._registry.clear()
        if not self._backend:
            return

        # hwmon sensors (from backend)
        try:
            hwmon_sensors = await self._backend.get_available_temp_sensors()
            for s in hwmon_sensors:
                sid = s.sensor_id
                src = HwmonTempSource(
                    sensor_id=sid,
                    device_name=s.device_name,
                    backend_label=s.label,
                    is_cpu_sensor=s.is_cpu_sensor,
                    read_fn=self._make_hwmon_reader(sid),
                )
                self._registry.register(src)
        except Exception as exc:
            logger.debug("hwmon source registration failed: %s", exc)

        # GPU sources from monitoring SHM
        for channel in ("edge", "junction", "mem"):
            self._registry.register(GpuTempSource(
                channel=channel,
                read_fn=self._make_gpu_reader(channel),
            ))

        # Disk sources from SMART cache
        for device in await self._list_smart_devices():
            self._registry.register(DiskTempSource(
                device=device,
                read_fn=self._make_disk_reader(device),
            ))

        # Composite sensors from DB
        await self._register_composites_from_db()

        # Custom labels from DB
        await self._load_sensor_labels()

    def _make_hwmon_reader(self, sensor_id: str):
        async def _read():
            try:
                return await self._backend.get_temperature(sensor_id)
            except Exception:
                return None
        return _read

    def _make_gpu_reader(self, channel: str):
        async def _read():
            from app.services.monitoring.shm import read_shm, TELEMETRY_FILE
            data = read_shm(TELEMETRY_FILE, max_age_seconds=30.0)
            if not data:
                return None
            gpu = data.get("gpu") if isinstance(data, dict) else None
            if not gpu:
                return None
            key = {
                "edge": "temperature_edge_celsius",
                "junction": "temperature_junction_celsius",
                "mem": "temperature_memory_celsius",
            }[channel]
            v = gpu.get(key)
            return float(v) if v is not None else None
        return _read

    def _make_disk_reader(self, device: str):
        async def _read():
            try:
                from app.services.hardware.smart.cache import get_cached_smart_status
                payload = get_cached_smart_status()
                if not payload:
                    return None
                for disk in getattr(payload, "disks", []) or []:
                    if getattr(disk, "device", None) == device or getattr(disk, "name", None) == device:
                        t = getattr(disk, "temperature_celsius", None) or getattr(disk, "temperature", None)
                        return float(t) if t is not None else None
            except Exception:
                return None
            return None
        return _read

    async def _list_smart_devices(self) -> List[str]:
        try:
            from app.services.hardware.smart.cache import get_cached_smart_status
            payload = get_cached_smart_status()
            if not payload:
                return []
            out: List[str] = []
            for d in getattr(payload, "disks", []) or []:
                name = getattr(d, "device", None) or getattr(d, "name", None)
                if name:
                    out.append(name)
            return out
        except Exception:
            return []

    async def _register_composites_from_db(self) -> None:
        from app.models.fans import CompositeTempSensor
        with self.db_session_factory() as db:
            rows = db.execute(select(CompositeTempSensor)).scalars().all()
            for row in rows:
                try:
                    source_ids = json.loads(row.source_ids_json)
                except Exception:
                    continue
                self._registry.register(MixTempSource(
                    composite_id=row.id,
                    name=row.name,
                    function=row.function,
                    source_ids=source_ids,
                    registry=self._registry,
                ))

    async def _load_sensor_labels(self) -> None:
        from app.models.fans import TempSensorLabel
        with self.db_session_factory() as db:
            for row in db.execute(select(TempSensorLabel)).scalars().all():
                self._registry.set_label(row.sensor_id, row.custom_label)
```

- [ ] **Step 3: Call `_rebuild_registry` from `start()` after backend init**

In `FanControlService.start()`, after the line `await self._initialize_backend()` and before `await self._load_fan_configs()`, insert:

```python
        await self._rebuild_registry()
```

- [ ] **Step 3b: Remove the silent CPU-sensor auto-correction in `_load_fan_configs`**

Today, the loader (lines 243–281 of `fan_control.py`) silently rewrites every fan's `temp_sensor_id` back to the CPU sensor at every startup if it points anywhere else. That clobbers user-chosen sensors (including future composite sensors) and is the reason case fans currently always read CPU temp.

In `_load_fan_configs`, **delete** the entire `elif cpu_sensor_id and existing.temp_sensor_id not in cpu_sensor_ids:` branch and its body. The branch that creates a *new* config with `temp_sensor_id=cpu_sensor_id or fan.temp_sensor_id` for first-discovered fans stays — that's a reasonable default. The auto-correction stays gone.

Add a test in `backend/tests/test_fan_sensor_assignment.py` to lock this in:

```python
"""User-chosen sensor must not be overwritten on service restart."""
import json
import pytest
from app.models.fans import FanConfig
from app.services.power.fan_control import FanControlService


@pytest.mark.asyncio
async def test_user_chosen_sensor_survives_reload(db_session, monkeypatch):
    # Pre-seed a fan config pointing to a non-CPU sensor (e.g., a composite)
    db_session.add(FanConfig(
        fan_id="hwmon0_pwm1",
        name="Case Fan",
        mode="auto",
        curve_json=json.dumps([{"temp": 35, "pwm": 30}, {"temp": 70, "pwm": 80}]),
        min_pwm_percent=0,
        max_pwm_percent=100,
        emergency_temp_celsius=85.0,
        temp_sensor_id="mix:user-choice",
        is_active=True,
    ))
    db_session.commit()

    # Run _load_fan_configs (simulate restart) — the assignment must NOT change
    # Use whichever test fixture this project uses to instantiate FanControlService.
    # Pseudo:
    #   svc = await FanControlService.get_instance(settings, lambda: db_session)
    #   await svc._initialize_backend(); await svc._rebuild_registry(); await svc._load_fan_configs()
    #   reloaded = db_session.execute(select(FanConfig).where(FanConfig.fan_id == "hwmon0_pwm1")).scalar_one()
    #   assert reloaded.temp_sensor_id == "mix:user-choice"
```

Use the project's existing pattern for instantiating `FanControlService` in tests — search `backend/tests/` for `FanControlService` usage to find the fixture.

- [ ] **Step 4: Replace `_monitor_and_control_fans` to use registry + curve eval**

Replace the body of `_monitor_and_control_fans` (keeping the function signature) with:

```python
    async def _monitor_and_control_fans(self):
        if not self._backend:
            return

        fans = await self._backend.get_fans()
        now_ts = _time.time()
        dt = (now_ts - self._last_tick_ts) if self._last_tick_ts else self.config.fan_sample_interval_seconds
        self._last_tick_ts = now_ts

        # Map for sync curve type
        other_fan_pwms = {f.fan_id: f.pwm_percent for f in fans}

        with self.db_session_factory() as db:
            for fan in fans:
                config = db.execute(
                    select(FanConfig).where(FanConfig.fan_id == fan.fan_id)
                ).scalar_one_or_none()
                if not config or not config.is_active:
                    continue

                mode = FanMode(config.mode)
                temperature = await self._registry.get_temp(config.temp_sensor_id) if config.temp_sensor_id else None

                target_pwm = fan.pwm_percent

                if mode in (FanMode.AUTO, FanMode.SCHEDULED):
                    if temperature is not None and temperature >= config.emergency_temp_celsius:
                        target_pwm = 100
                        mode = FanMode.EMERGENCY
                        if fan.fan_id in self._hysteresis_state:
                            del self._hysteresis_state[fan.fan_id]
                        try:
                            from app.services.notifications.events import emit_temperature_critical_sync
                            emit_temperature_critical_sync(config.temp_sensor_id or fan.fan_id, temperature)
                        except Exception:
                            pass
                    else:
                        if temperature is not None and temperature >= config.emergency_temp_celsius - 10:
                            try:
                                from app.services.notifications.events import emit_temperature_high_sync
                                emit_temperature_high_sync(config.temp_sensor_id or fan.fan_id, temperature)
                            except Exception:
                                pass

                        # Schedule override of curve_json (graph mode only)
                        curve_json = config.curve_json
                        if FanMode(config.mode) == FanMode.SCHEDULED:
                            scheduled_pts, _ = self._schedule.resolve_active_curve(
                                fan.fan_id, config.curve_json, db
                            )
                            curve_json = json.dumps([p if isinstance(p, dict) else p.model_dump() for p in scheduled_pts]) if scheduled_pts else config.curve_json

                        eval_cfg = type("CfgView", (), {
                            **{c.name: getattr(config, c.name) for c in config.__table__.columns},
                            "curve_json": curve_json,
                        })()

                        prev = self._last_pwm_by_fan.get(fan.fan_id, fan.pwm_percent)

                        def _profile_loader(pid: Optional[int]) -> List[dict]:
                            if pid is None:
                                return []
                            from app.models.fans import FanCurveProfile
                            row = db.execute(select(FanCurveProfile).where(FanCurveProfile.id == pid)).scalar_one_or_none()
                            if row is None or not row.curve_json:
                                return []
                            try:
                                return json.loads(row.curve_json)
                            except Exception:
                                return []

                        target_pwm = evaluate_curve(
                            eval_cfg, temperature, prev, other_fan_pwms, _profile_loader, dt,
                        )
                        # Hysteresis layered on top (existing helper, only for graph-like outputs)
                        target_pwm = self._calculate_pwm_with_hysteresis(
                            fan.fan_id, temperature or 0.0, [],
                            getattr(config, "hysteresis_celsius", 3.0), target_pwm,
                        ) if eval_cfg.curve_type == "graph" else target_pwm

                target_pwm = max(config.min_pwm_percent, min(config.max_pwm_percent, target_pwm))

                if target_pwm != fan.pwm_percent:
                    await self._backend.set_pwm(fan.fan_id, target_pwm)
                self._last_pwm_by_fan[fan.fan_id] = target_pwm

                if mode == FanMode.EMERGENCY and config.mode != FanMode.EMERGENCY.value:
                    config.mode = FanMode.EMERGENCY.value
                    db.commit()

                self._sample_buffer.append({
                    "timestamp": datetime.now(timezone.utc),
                    "fan_id": fan.fan_id,
                    "pwm_percent": target_pwm,
                    "rpm": fan.rpm,
                    "temperature_celsius": temperature,
                    "mode": mode.value,
                })
```

- [ ] **Step 5: Run existing fan tests — expect PASS**

```bash
cd backend
python -m pytest tests/ -k "fan" -v
```

Expected: all existing fan tests still pass plus new ones.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/power/fan_control.py
git commit -m "feat(power): wire TempSourceRegistry + evaluate_curve into FanControlService"
```

---

## Task 10: Sensor label + composite API endpoints

**Files:**
- Modify: `backend/app/schemas/fans.py`
- Modify: `backend/app/api/routes/fans.py`
- Test: `backend/tests/test_fan_sensor_label_api.py`
- Test: `backend/tests/test_fan_composite_api.py`

- [ ] **Step 1: Add schemas**

Append to `backend/app/schemas/fans.py`:

```python
class TempSensorLabelUpdate(BaseModel):
    label: str = Field(..., min_length=1, max_length=100)


class CompositeSensorCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    function: str = Field(..., pattern=r"^(max|min|avg)$")
    source_ids: List[str] = Field(..., min_length=2, max_length=6)


class CompositeSensorUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    function: Optional[str] = Field(default=None, pattern=r"^(max|min|avg)$")
    source_ids: Optional[List[str]] = Field(default=None, min_length=2, max_length=6)


class CompositeSensorInfo(BaseModel):
    id: str
    name: str
    function: str
    source_ids: List[str]
    current_temp: Optional[float] = None


class CompositeSensorListResponse(BaseModel):
    composites: List[CompositeSensorInfo]
    total_count: int
```

And extend `TempSensorInfo`:

```python
class TempSensorInfo(BaseModel):
    sensor_id: str
    device_name: str
    label: Optional[str] = None
    custom_label: Optional[str] = None
    kind: str = "hwmon"  # hwmon | gpu | disk | mix
    gpu_vendor: Optional[str] = None
    is_cpu_sensor: bool
    current_temp: Optional[float] = None
```

- [ ] **Step 2: Add label endpoints to `fans.py` route**

Append to `backend/app/api/routes/fans.py`:

```python
@router.put("/sensors/{sensor_id}/label")
@user_limiter.limit(get_limit("admin_operations"))
async def set_sensor_label(
    request: Request, response: Response,
    sensor_id: str,
    body: TempSensorLabelUpdate,
    current_user: User = Depends(get_current_admin),
    service: FanControlService = Depends(get_fan_service),
):
    from app.models.fans import TempSensorLabel
    with service.db_session_factory() as db:
        existing = db.execute(select(TempSensorLabel).where(TempSensorLabel.sensor_id == sensor_id)).scalar_one_or_none()
        if existing:
            existing.custom_label = body.label
        else:
            db.add(TempSensorLabel(sensor_id=sensor_id, custom_label=body.label))
        db.commit()
    service._registry.set_label(sensor_id, body.label)
    return {"success": True, "sensor_id": sensor_id, "custom_label": body.label}


@router.delete("/sensors/{sensor_id}/label")
@user_limiter.limit(get_limit("admin_operations"))
async def clear_sensor_label(
    request: Request, response: Response,
    sensor_id: str,
    current_user: User = Depends(get_current_admin),
    service: FanControlService = Depends(get_fan_service),
):
    from app.models.fans import TempSensorLabel
    with service.db_session_factory() as db:
        existing = db.execute(select(TempSensorLabel).where(TempSensorLabel.sensor_id == sensor_id)).scalar_one_or_none()
        if existing:
            db.delete(existing)
            db.commit()
    service._registry.clear_label(sensor_id)
    return {"success": True, "sensor_id": sensor_id}
```

Add the missing import at top of the file:

```python
from sqlalchemy import select
```

(if not already present from earlier sections).

- [ ] **Step 3: Add composite endpoints**

Append to `backend/app/api/routes/fans.py`:

```python
MAX_COMPOSITES_PER_SYSTEM = 5


@router.get("/composite-sensors", response_model=CompositeSensorListResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def list_composite_sensors(
    request: Request, response: Response,
    current_user: User = Depends(get_current_user),
    service: FanControlService = Depends(get_fan_service),
):
    from app.models.fans import CompositeTempSensor
    import json as _json
    items: List[CompositeSensorInfo] = []
    with service.db_session_factory() as db:
        rows = db.execute(select(CompositeTempSensor)).scalars().all()
        for row in rows:
            try:
                sids = _json.loads(row.source_ids_json)
            except Exception:
                sids = []
            current = await service._registry.get_temp(row.id)
            items.append(CompositeSensorInfo(
                id=row.id, name=row.name, function=row.function,
                source_ids=sids, current_temp=current,
            ))
    return CompositeSensorListResponse(composites=items, total_count=len(items))


@router.post("/composite-sensors", response_model=CompositeSensorInfo, status_code=201)
@user_limiter.limit(get_limit("admin_operations"))
async def create_composite_sensor(
    request: Request, response: Response,
    body: CompositeSensorCreate,
    current_user: User = Depends(get_current_admin),
    service: FanControlService = Depends(get_fan_service),
):
    from app.models.fans import CompositeTempSensor
    import json as _json
    import uuid as _uuid

    with service.db_session_factory() as db:
        count = db.execute(select(func.count(CompositeTempSensor.id))).scalar() or 0
        if count >= MAX_COMPOSITES_PER_SYSTEM:
            raise HTTPException(status_code=422, detail=f"Maximum {MAX_COMPOSITES_PER_SYSTEM} composite sensors")

        new_id = f"mix:{_uuid.uuid4().hex[:12]}"
        # Cycle prevention: composite cannot reference itself (it doesn't exist yet,
        # but a future PUT might create a cycle through the chain).
        if new_id in body.source_ids:
            raise HTTPException(status_code=422, detail="Composite cannot reference itself")

        row = CompositeTempSensor(
            id=new_id, name=body.name, function=body.function,
            source_ids_json=_json.dumps(body.source_ids),
        )
        db.add(row)
        db.commit()

    # Rebuild registry to include the new composite
    await service._rebuild_registry()

    return CompositeSensorInfo(
        id=new_id, name=body.name, function=body.function,
        source_ids=body.source_ids, current_temp=None,
    )


@router.put("/composite-sensors/{composite_id}", response_model=CompositeSensorInfo)
@user_limiter.limit(get_limit("admin_operations"))
async def update_composite_sensor(
    request: Request, response: Response,
    composite_id: str,
    body: CompositeSensorUpdate,
    current_user: User = Depends(get_current_admin),
    service: FanControlService = Depends(get_fan_service),
):
    from app.models.fans import CompositeTempSensor
    import json as _json
    with service.db_session_factory() as db:
        row = db.execute(select(CompositeTempSensor).where(CompositeTempSensor.id == composite_id)).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Composite sensor not found")
        if body.name is not None:
            row.name = body.name
        if body.function is not None:
            row.function = body.function
        if body.source_ids is not None:
            if composite_id in body.source_ids:
                raise HTTPException(status_code=422, detail="Composite cannot reference itself")
            row.source_ids_json = _json.dumps(body.source_ids)
        db.commit()
        sids = _json.loads(row.source_ids_json)

    await service._rebuild_registry()
    current = await service._registry.get_temp(composite_id)
    return CompositeSensorInfo(id=composite_id, name=row.name, function=row.function,
                               source_ids=sids, current_temp=current)


@router.delete("/composite-sensors/{composite_id}")
@user_limiter.limit(get_limit("admin_operations"))
async def delete_composite_sensor(
    request: Request, response: Response,
    composite_id: str,
    current_user: User = Depends(get_current_admin),
    service: FanControlService = Depends(get_fan_service),
):
    from app.models.fans import CompositeTempSensor, FanConfig
    with service.db_session_factory() as db:
        row = db.execute(select(CompositeTempSensor).where(CompositeTempSensor.id == composite_id)).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Composite sensor not found")
        # Unlink any FanConfig pointing at this composite
        for cfg in db.execute(select(FanConfig).where(FanConfig.temp_sensor_id == composite_id)).scalars():
            cfg.temp_sensor_id = None
        db.delete(row)
        db.commit()
    await service._rebuild_registry()
    return {"success": True}
```

Add `from sqlalchemy import func` to imports at the top of `routes/fans.py` if not present.

- [ ] **Step 4: Update existing `list_temp_sensors` endpoint**

Replace the body of `list_temp_sensors` with one that reads from the registry rather than the backend directly:

```python
@router.get("/sensors", response_model=TempSensorListResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def list_temp_sensors(
    request: Request, response: Response,
    current_user: User = Depends(get_current_admin),
    service: FanControlService = Depends(get_fan_service),
):
    sources = service._registry.all_sources()
    items: List[TempSensorInfo] = []
    for s in sources:
        current = await service._registry.get_temp(s.id)
        items.append(TempSensorInfo(
            sensor_id=s.id,
            device_name=s.device_name,
            label=s.backend_label,
            custom_label=service._registry._labels.get(s.id),
            kind=s.kind,
            gpu_vendor=getattr(s, "gpu_vendor", None) if s.kind == "gpu" else None,
            is_cpu_sensor=s.is_cpu_sensor,
            current_temp=current,
        ))
    return TempSensorListResponse(sensors=items, total_count=len(items))
```

- [ ] **Step 5: Write tests**

Create `backend/tests/test_fan_sensor_label_api.py`:

```python
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_set_and_clear_sensor_label(admin_client: AsyncClient):
    r = await admin_client.put("/api/fans/sensors/hwmon0_temp1/label", json={"label": "CPU primary"})
    assert r.status_code == 200
    assert r.json()["custom_label"] == "CPU primary"

    r = await admin_client.get("/api/fans/sensors")
    sensors = r.json()["sensors"]
    assert any(s.get("custom_label") == "CPU primary" for s in sensors if "hwmon0_temp1" in s["sensor_id"])

    r = await admin_client.delete("/api/fans/sensors/hwmon0_temp1/label")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_label_rejects_empty(admin_client: AsyncClient):
    r = await admin_client.put("/api/fans/sensors/hwmon0_temp1/label", json={"label": ""})
    assert r.status_code == 422
```

Create `backend/tests/test_fan_composite_api.py`:

```python
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_and_delete_composite(admin_client: AsyncClient):
    r = await admin_client.post("/api/fans/composite-sensors", json={
        "name": "Hottest", "function": "max",
        "source_ids": ["hwmon:hwmon0_temp1", "gpu:edge"],
    })
    assert r.status_code == 201
    cid = r.json()["id"]
    assert cid.startswith("mix:")

    r = await admin_client.get("/api/fans/composite-sensors")
    assert any(c["id"] == cid for c in r.json()["composites"])

    r = await admin_client.delete(f"/api/fans/composite-sensors/{cid}")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_max_composites_per_system(admin_client: AsyncClient):
    created = []
    for i in range(5):
        r = await admin_client.post("/api/fans/composite-sensors", json={
            "name": f"C{i}", "function": "avg",
            "source_ids": ["hwmon:hwmon0_temp1", "gpu:edge"],
        })
        assert r.status_code == 201
        created.append(r.json()["id"])

    r = await admin_client.post("/api/fans/composite-sensors", json={
        "name": "Extra", "function": "avg",
        "source_ids": ["hwmon:hwmon0_temp1", "gpu:edge"],
    })
    assert r.status_code == 422

    for cid in created:
        await admin_client.delete(f"/api/fans/composite-sensors/{cid}")


@pytest.mark.asyncio
async def test_composite_requires_min_two_sources(admin_client: AsyncClient):
    r = await admin_client.post("/api/fans/composite-sensors", json={
        "name": "OneOnly", "function": "max",
        "source_ids": ["hwmon:hwmon0_temp1"],
    })
    assert r.status_code == 422
```

Assumes `admin_client` fixture exists. Search the codebase for `admin_client` to confirm — if not present, use the project's standard test client fixture pattern from another test file (`grep` for `async_client` or `client` fixtures in `backend/tests/conftest.py`).

- [ ] **Step 6: Run tests**

```bash
cd backend
python -m pytest tests/test_fan_sensor_label_api.py tests/test_fan_composite_api.py -v
```

If the `admin_client` fixture is named differently in this repo, adjust the test file to use the local pattern.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/fans.py backend/app/api/routes/fans.py backend/tests/test_fan_sensor_label_api.py backend/tests/test_fan_composite_api.py
git commit -m "feat(api): sensor label + composite sensor endpoints"
```

---

## Task 11: Extended FanInfo + UpdateFanConfig schemas + GPU manual-mode endpoint

**Files:**
- Modify: `backend/app/schemas/fans.py`
- Modify: `backend/app/api/routes/fans.py`
- Modify: `backend/app/services/power/fan_control.py`

- [ ] **Step 1: Extend `FanInfo`**

In `backend/app/schemas/fans.py`, add to `FanInfo`:

```python
    is_gpu_fan: bool = False
    gpu_vendor: Optional[str] = None
    last_write_error: Optional[str] = None
    curve_type: str = "graph"
    flat_pwm_percent: Optional[int] = None
    target_temp_celsius: Optional[float] = None
    target_pwm_percent: Optional[int] = None
    mix_curve_a_id: Optional[int] = None
    mix_curve_b_id: Optional[int] = None
    mix_function: Optional[str] = None
    sync_fan_id: Optional[str] = None
    start_pwm_percent: Optional[int] = None
    stop_below_temp_celsius: Optional[float] = None
    response_time_seconds: float = 0.0
    pwm_steps: int = 1
```

- [ ] **Step 2: Extend `UpdateFanConfigRequest`**

Add all the matching `Optional[...]` fields plus a `curve_type` field. The validation rules:

- `curve_type` must be one of `graph|flat|target|mix|sync`
- If `curve_type=flat`, `flat_pwm_percent` is required (handled by caller, not validator)
- `pwm_steps` must be 1, 5, 10 or 25
- `response_time_seconds` 0–60
- `start_pwm_percent` 0–100

Use the same `field_validator` pattern already in the file.

- [ ] **Step 3: Extend `FanControlService.update_fan_config`**

In `backend/app/services/power/fan_control.py`, extend `update_fan_config` to accept and persist all the new fields. Mirror the pattern of the existing field updates (set only when not None, log change, return updated dict).

Return dict also includes the new fields.

- [ ] **Step 4: Update `get_status` to include new fields on each fan entry**

Inside the `fan_data_list.append(...)` calls in `get_status`, add:

```python
"is_gpu_fan": fan.is_gpu_fan,
"gpu_vendor": fan.gpu_vendor,
"last_write_error": fan.last_write_error,
"curve_type": getattr(config, "curve_type", "graph"),
"flat_pwm_percent": getattr(config, "flat_pwm_percent", None),
"target_temp_celsius": getattr(config, "target_temp_celsius", None),
"target_pwm_percent": getattr(config, "target_pwm_percent", None),
"mix_curve_a_id": getattr(config, "mix_curve_a_id", None),
"mix_curve_b_id": getattr(config, "mix_curve_b_id", None),
"mix_function": getattr(config, "mix_function", None),
"sync_fan_id": getattr(config, "sync_fan_id", None),
"start_pwm_percent": getattr(config, "start_pwm_percent", None),
"stop_below_temp_celsius": getattr(config, "stop_below_temp_celsius", None),
"response_time_seconds": getattr(config, "response_time_seconds", 0.0),
"pwm_steps": getattr(config, "pwm_steps", 1),
```

- [ ] **Step 5: Add GPU manual-mode endpoint**

Append to `backend/app/api/routes/fans.py`:

```python
from pydantic import BaseModel as _PydanticBase


class GpuManualModeRequest(_PydanticBase):
    enable: bool


# Stash of state across enable/disable per fan
_gpu_manual_state: Dict[str, "AmdManualState"] = {}


@router.post("/{fan_id}/gpu-manual-mode")
@user_limiter.limit(get_limit("admin_operations"))
async def set_gpu_manual_mode(
    request: Request, response: Response,
    fan_id: str,
    body: GpuManualModeRequest,
    current_user: User = Depends(get_current_admin),
    service: FanControlService = Depends(get_fan_service),
):
    from app.services.power.fan_gpu_manual import enable_amd_manual, disable_amd_manual

    # Look up the fan's hwmon dir from the backend cache
    backend = service._backend
    if not hasattr(backend, "_fan_cache") or fan_id not in backend._fan_cache:
        raise HTTPException(status_code=404, detail="Fan not found")
    info = backend._fan_cache[fan_id]
    if not info.get("is_gpu_fan") or info.get("gpu_vendor") != "amd":
        raise HTTPException(status_code=400, detail="Only available on AMD GPU fans")

    hwmon_dir = info["pwm_path"].parent

    try:
        if body.enable:
            state = await enable_amd_manual(hwmon_dir=hwmon_dir, drm_root=None)
            _gpu_manual_state[fan_id] = state
        else:
            state = _gpu_manual_state.pop(fan_id, None)
            if state is None:
                from app.services.power.fan_gpu_manual import AmdManualState
                state = AmdManualState(previous_level="auto", previous_pwm_enable=2)
            await disable_amd_manual(hwmon_dir=hwmon_dir, drm_root=None, state=state)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"GPU manual mode toggle failed: {exc}")

    return {"success": True, "fan_id": fan_id, "enabled": body.enable}
```

Add `from app.services.power.fan_gpu_manual import AmdManualState` at the top under TYPE_CHECKING or directly.

- [ ] **Step 6: Run all backend fan tests**

```bash
cd backend
python -m pytest tests/test_fan*.py -v
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/fans.py backend/app/api/routes/fans.py backend/app/services/power/fan_control.py
git commit -m "feat(api): extended FanInfo schema + GPU manual-mode endpoint"
```

---

## Task 12: Dev backend — mock GPU fan + GPU sensor channels

**Files:**
- Modify: `backend/app/services/power/fan_backend_dev.py`

- [ ] **Step 1: Read existing dev backend to understand shape**

```bash
cat backend/app/services/power/fan_backend_dev.py | head -80
```

- [ ] **Step 2: Add mock GPU fan**

In `fan_backend_dev.py`, in the list/dict that defines mock fans, add a new entry:

```python
{
    "fan_id": "dev_gpu_pwm1",
    "name": "AMD GPU Fan (sim)",
    "is_gpu_fan": True,
    "gpu_vendor": "amd",
    "device_driver": "amdgpu",
    # ... mirror the shape of existing dev fans ...
}
```

And surface `is_gpu_fan`, `gpu_vendor`, `device_driver` on every `FanData` returned from `get_fans()`.

- [ ] **Step 3: Manual verification**

```bash
cd backend
NAS_MODE=dev python -c "
import asyncio
from app.core.config import get_settings
from app.services.power.fan_backend_dev import DevFanControlBackend
async def main():
    b = DevFanControlBackend(get_settings())
    for f in await b.get_fans():
        print(f.fan_id, f.name, f.is_gpu_fan, f.gpu_vendor)
asyncio.run(main())
"
```

Expected: one fan has `is_gpu_fan=True, gpu_vendor='amd'`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/power/fan_backend_dev.py
git commit -m "feat(power-dev): add simulated AMD GPU fan to dev backend"
```

---

## Task 13: Frontend — API client extensions

**Files:**
- Modify: `client/src/api/fan-control.ts`

- [ ] **Step 1: Extend types**

Replace/extend `TempSensorInfo`:

```ts
export interface TempSensorInfo {
  sensor_id: string;
  device_name: string;
  label: string | null;
  custom_label?: string | null;
  kind: 'hwmon' | 'gpu' | 'disk' | 'mix';
  gpu_vendor?: string | null;
  is_cpu_sensor: boolean;
  current_temp: number | null;
}
```

Add to `FanInfo`:

```ts
  is_gpu_fan?: boolean;
  gpu_vendor?: string | null;
  last_write_error?: string | null;
  curve_type?: 'graph' | 'flat' | 'target' | 'mix' | 'sync';
  flat_pwm_percent?: number | null;
  target_temp_celsius?: number | null;
  target_pwm_percent?: number | null;
  mix_curve_a_id?: number | null;
  mix_curve_b_id?: number | null;
  mix_function?: 'max' | 'sum' | null;
  sync_fan_id?: string | null;
  start_pwm_percent?: number | null;
  stop_below_temp_celsius?: number | null;
  response_time_seconds?: number;
  pwm_steps?: number;
```

Extend `UpdateFanConfigRequest` with the matching optional fields.

Add new interfaces:

```ts
export interface CompositeSensorInfo {
  id: string;
  name: string;
  function: 'max' | 'min' | 'avg';
  source_ids: string[];
  current_temp: number | null;
}

export interface CompositeSensorCreate {
  name: string;
  function: 'max' | 'min' | 'avg';
  source_ids: string[];
}

export interface CompositeSensorListResponse {
  composites: CompositeSensorInfo[];
  total_count: number;
}
```

- [ ] **Step 2: Add API functions**

Append to `client/src/api/fan-control.ts`:

```ts
export async function renameSensor(sensorId: string, label: string) {
  const r = await apiClient.put(`/api/fans/sensors/${encodeURIComponent(sensorId)}/label`, { label });
  return r.data;
}

export async function clearSensorLabel(sensorId: string) {
  const r = await apiClient.delete(`/api/fans/sensors/${encodeURIComponent(sensorId)}/label`);
  return r.data;
}

export async function listComposites(): Promise<CompositeSensorListResponse> {
  const r = await apiClient.get<CompositeSensorListResponse>('/api/fans/composite-sensors');
  return r.data;
}

export async function createComposite(body: CompositeSensorCreate): Promise<CompositeSensorInfo> {
  const r = await apiClient.post<CompositeSensorInfo>('/api/fans/composite-sensors', body);
  return r.data;
}

export async function updateComposite(id: string, body: Partial<CompositeSensorCreate>): Promise<CompositeSensorInfo> {
  const r = await apiClient.put<CompositeSensorInfo>(`/api/fans/composite-sensors/${encodeURIComponent(id)}`, body);
  return r.data;
}

export async function deleteComposite(id: string): Promise<void> {
  await apiClient.delete(`/api/fans/composite-sensors/${encodeURIComponent(id)}`);
}

export async function setGpuManualMode(fanId: string, enable: boolean) {
  const r = await apiClient.post(`/api/fans/${encodeURIComponent(fanId)}/gpu-manual-mode`, { enable });
  return r.data;
}
```

- [ ] **Step 3: Type check**

```bash
cd client
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add client/src/api/fan-control.ts
git commit -m "feat(client/api): fan-control types + composite/label/gpu-manual endpoints"
```

---

## Task 14: Frontend — SensorsPanel + CompositeSensorModal

**Files:**
- Create: `client/src/components/fan-control/SensorsPanel.tsx`
- Create: `client/src/components/fan-control/CompositeSensorModal.tsx`
- Modify: `client/src/components/fan-control/index.ts`

- [ ] **Step 1: Implement `SensorsPanel`**

Create `client/src/components/fan-control/SensorsPanel.tsx`:

```tsx
import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { Pencil, X, Plus, Cpu, MonitorSmartphone, HardDrive, Sigma } from 'lucide-react';
import {
  listTempSensors, renameSensor, clearSensorLabel,
  listComposites, deleteComposite,
  TempSensorInfo, CompositeSensorInfo,
} from '../../api/fan-control';
import { handleApiError } from '../../lib/errorHandling';
import CompositeSensorModal from './CompositeSensorModal';

const KIND_ICONS = {
  hwmon: Cpu,
  gpu: MonitorSmartphone,
  disk: HardDrive,
  mix: Sigma,
} as const;

export default function SensorsPanel() {
  const { t } = useTranslation(['system', 'common']);
  const [sensors, setSensors] = useState<TempSensorInfo[]>([]);
  const [composites, setComposites] = useState<CompositeSensorInfo[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editLabel, setEditLabel] = useState('');
  const [showModal, setShowModal] = useState(false);

  const reload = useCallback(async () => {
    try {
      const [s, c] = await Promise.all([listTempSensors(), listComposites()]);
      setSensors(s.sensors);
      setComposites(c.composites);
    } catch (err) {
      handleApiError(err, t('system:fanControl.sensors.loadFailed'));
    }
  }, [t]);

  useEffect(() => { reload(); }, [reload]);

  const saveLabel = async (sensorId: string) => {
    if (!editLabel.trim()) {
      setEditingId(null);
      return;
    }
    try {
      await renameSensor(sensorId, editLabel.trim());
      toast.success(t('system:fanControl.sensors.renamed'));
      setEditingId(null);
      reload();
    } catch (err) {
      handleApiError(err);
    }
  };

  return (
    <div className="bg-card border border-border rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold">{t('system:fanControl.sensors.title')}</h3>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-1 px-2 py-1 text-xs bg-primary text-primary-foreground rounded hover:bg-primary/90"
        >
          <Plus size={14} /> {t('system:fanControl.sensors.addComposite')}
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        {sensors.map((s) => {
          const Icon = KIND_ICONS[s.kind] ?? Cpu;
          const display = s.custom_label || s.label || s.device_name;
          const isEditing = editingId === s.sensor_id;
          return (
            <div key={s.sensor_id} className="flex items-center gap-2 p-2 border border-border rounded">
              <Icon size={16} className="text-muted-foreground" />
              <div className="flex-1 min-w-0">
                {isEditing ? (
                  <input
                    value={editLabel}
                    onChange={(e) => setEditLabel(e.target.value)}
                    onBlur={() => saveLabel(s.sensor_id)}
                    onKeyDown={(e) => { if (e.key === 'Enter') saveLabel(s.sensor_id); }}
                    autoFocus
                    className="w-full bg-background border border-border rounded px-1 text-sm"
                  />
                ) : (
                  <div className="text-sm font-medium truncate">{display}</div>
                )}
                <div className="text-xs text-muted-foreground truncate">{s.sensor_id}</div>
              </div>
              <div className="text-sm tabular-nums">
                {s.current_temp != null ? `${s.current_temp.toFixed(1)}°C` : '—'}
              </div>
              {!isEditing && (
                <button
                  onClick={() => { setEditingId(s.sensor_id); setEditLabel(s.custom_label || ''); }}
                  className="p-1 text-muted-foreground hover:text-foreground"
                  title={t('common:rename')}
                >
                  <Pencil size={14} />
                </button>
              )}
              {s.custom_label && !isEditing && (
                <button
                  onClick={async () => { await clearSensorLabel(s.sensor_id); reload(); }}
                  className="p-1 text-muted-foreground hover:text-destructive"
                  title={t('common:reset')}
                >
                  <X size={14} />
                </button>
              )}
            </div>
          );
        })}
      </div>

      {composites.length > 0 && (
        <>
          <h4 className="font-medium mt-4 mb-2 text-sm">{t('system:fanControl.sensors.compositeTitle')}</h4>
          <div className="space-y-2">
            {composites.map((c) => (
              <div key={c.id} className="flex items-center gap-2 p-2 border border-border rounded">
                <Sigma size={16} className="text-primary" />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium">{c.name}</div>
                  <div className="text-xs text-muted-foreground">
                    {t(`system:fanControl.sensors.functions.${c.function}`)} · {c.source_ids.length} {t('system:fanControl.sensors.sources')}
                  </div>
                </div>
                <div className="text-sm tabular-nums">
                  {c.current_temp != null ? `${c.current_temp.toFixed(1)}°C` : '—'}
                </div>
                <button
                  onClick={async () => { await deleteComposite(c.id); reload(); }}
                  className="p-1 text-muted-foreground hover:text-destructive"
                >
                  <X size={14} />
                </button>
              </div>
            ))}
          </div>
        </>
      )}

      {showModal && (
        <CompositeSensorModal
          availableSensors={sensors}
          onClose={() => setShowModal(false)}
          onCreated={() => { setShowModal(false); reload(); }}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 2: Implement `CompositeSensorModal`**

Create `client/src/components/fan-control/CompositeSensorModal.tsx`:

```tsx
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { Modal } from '../ui/Modal';
import { createComposite, TempSensorInfo } from '../../api/fan-control';
import { handleApiError } from '../../lib/errorHandling';

interface Props {
  availableSensors: TempSensorInfo[];
  onClose: () => void;
  onCreated: () => void;
}

export default function CompositeSensorModal({ availableSensors, onClose, onCreated }: Props) {
  const { t } = useTranslation(['system', 'common']);
  const [name, setName] = useState('');
  const [fn, setFn] = useState<'max' | 'min' | 'avg'>('max');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [submitting, setSubmitting] = useState(false);

  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelected(next);
  };

  const submit = async () => {
    if (!name.trim() || selected.size < 2) return;
    setSubmitting(true);
    try {
      await createComposite({ name: name.trim(), function: fn, source_ids: Array.from(selected) });
      toast.success(t('system:fanControl.sensors.compositeCreated'));
      onCreated();
    } catch (err) {
      handleApiError(err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal isOpen onClose={onClose} title={t('system:fanControl.sensors.createComposite')}>
      <div className="space-y-3">
        <div>
          <label className="text-sm font-medium">{t('common:name')}</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={100}
            className="w-full bg-background border border-border rounded px-2 py-1"
          />
        </div>
        <div>
          <label className="text-sm font-medium">{t('system:fanControl.sensors.function')}</label>
          <div className="flex gap-2 mt-1">
            {(['max', 'min', 'avg'] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFn(f)}
                className={`px-3 py-1 rounded ${fn === f ? 'bg-primary text-primary-foreground' : 'bg-muted'}`}
              >
                {t(`system:fanControl.sensors.functions.${f}`)}
              </button>
            ))}
          </div>
        </div>
        <div>
          <label className="text-sm font-medium">{t('system:fanControl.sensors.sources')}</label>
          <div className="max-h-60 overflow-y-auto border border-border rounded p-2 space-y-1">
            {availableSensors.filter((s) => s.kind !== 'mix').map((s) => (
              <label key={s.sensor_id} className="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  checked={selected.has(s.sensor_id)}
                  onChange={() => toggle(s.sensor_id)}
                />
                <span className="flex-1 truncate">{s.custom_label || s.label || s.device_name}</span>
                <span className="text-xs text-muted-foreground">{s.kind}</span>
              </label>
            ))}
          </div>
          <div className="text-xs text-muted-foreground mt-1">
            {selected.size}/6 {t('system:fanControl.sensors.selected')}
          </div>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="px-3 py-1 rounded bg-muted">
            {t('common:cancel')}
          </button>
          <button
            onClick={submit}
            disabled={!name.trim() || selected.size < 2 || selected.size > 6 || submitting}
            className="px-3 py-1 rounded bg-primary text-primary-foreground disabled:opacity-50"
          >
            {t('common:create')}
          </button>
        </div>
      </div>
    </Modal>
  );
}
```

- [ ] **Step 3: Export from `index.ts`**

In `client/src/components/fan-control/index.ts`, add:

```ts
export { default as SensorsPanel } from './SensorsPanel';
export { default as CompositeSensorModal } from './CompositeSensorModal';
```

- [ ] **Step 4: Mount in `FanControl.tsx`**

Open `client/src/pages/FanControl.tsx`. Import `SensorsPanel` from `../components/fan-control`. Insert `<SensorsPanel />` above the fan grid (above the current `FanCard` mapping).

- [ ] **Step 5: Run dev server and verify**

```bash
python start_dev.py
```

Visit `/fans` — confirm sensors panel renders, rename works, composite creation works.

- [ ] **Step 6: Commit**

```bash
git add client/src/components/fan-control/SensorsPanel.tsx client/src/components/fan-control/CompositeSensorModal.tsx client/src/components/fan-control/index.ts client/src/pages/FanControl.tsx
git commit -m "feat(client): SensorsPanel with rename + composite sensor modal"
```

---

## Task 15: Frontend — Curve type selector + typed editors

**Files:**
- Create: `client/src/components/fan-control/CurveTypeSelector.tsx`
- Create: `client/src/components/fan-control/CurveEditorFlat.tsx`
- Create: `client/src/components/fan-control/CurveEditorTarget.tsx`
- Create: `client/src/components/fan-control/CurveEditorMix.tsx`
- Create: `client/src/components/fan-control/CurveEditorSync.tsx`
- Modify: `client/src/components/fan-control/FanDetails.tsx`

- [ ] **Step 1: Implement `CurveTypeSelector`**

```tsx
import { useTranslation } from 'react-i18next';

export type CurveType = 'graph' | 'flat' | 'target' | 'mix' | 'sync';

interface Props {
  value: CurveType;
  onChange: (v: CurveType) => void;
  disabled?: boolean;
}

const TYPES: CurveType[] = ['graph', 'flat', 'target', 'mix', 'sync'];

export default function CurveTypeSelector({ value, onChange, disabled }: Props) {
  const { t } = useTranslation(['system']);
  return (
    <div className="inline-flex bg-muted rounded p-1 gap-0.5">
      {TYPES.map((tp) => (
        <button
          key={tp}
          onClick={() => onChange(tp)}
          disabled={disabled}
          className={`px-3 py-1 text-sm rounded transition-colors ${
            value === tp ? 'bg-background shadow-sm font-medium' : 'text-muted-foreground hover:text-foreground'
          }`}
        >
          {t(`system:fanControl.curveTypes.${tp}`)}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Implement `CurveEditorFlat`**

```tsx
import { useTranslation } from 'react-i18next';

interface Props {
  value: number;
  onChange: (v: number) => void;
  disabled?: boolean;
}

export default function CurveEditorFlat({ value, onChange, disabled }: Props) {
  const { t } = useTranslation(['system']);
  return (
    <div className="space-y-2">
      <label className="text-sm font-medium">
        {t('system:fanControl.curveTypes.flatLabel')}: {value}%
      </label>
      <input
        type="range"
        min={0}
        max={100}
        step={1}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        disabled={disabled}
        className="w-full"
      />
    </div>
  );
}
```

- [ ] **Step 3: Implement `CurveEditorTarget`**

```tsx
import { useTranslation } from 'react-i18next';

interface Props {
  targetTemp: number;
  targetPwm: number;
  onChange: (next: { targetTemp: number; targetPwm: number }) => void;
  disabled?: boolean;
}

export default function CurveEditorTarget({ targetTemp, targetPwm, onChange, disabled }: Props) {
  const { t } = useTranslation(['system']);
  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">{t('system:fanControl.curveTypes.targetDescription')}</p>
      <div>
        <label className="text-sm font-medium">
          {t('system:fanControl.curveTypes.targetTemp')}: {targetTemp.toFixed(0)}°C
        </label>
        <input
          type="range" min={20} max={100} step={1}
          value={targetTemp}
          onChange={(e) => onChange({ targetTemp: Number(e.target.value), targetPwm })}
          disabled={disabled}
          className="w-full"
        />
      </div>
      <div>
        <label className="text-sm font-medium">
          {t('system:fanControl.curveTypes.targetPwm')}: {targetPwm}%
        </label>
        <input
          type="range" min={0} max={100} step={1}
          value={targetPwm}
          onChange={(e) => onChange({ targetTemp, targetPwm: Number(e.target.value) })}
          disabled={disabled}
          className="w-full"
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Implement `CurveEditorMix`**

```tsx
import { useTranslation } from 'react-i18next';
import type { FanCurveProfile } from '../../api/fan-control';

interface Props {
  profiles: FanCurveProfile[];
  curveAId: number | null;
  curveBId: number | null;
  fn: 'max' | 'sum';
  onChange: (next: { curveAId: number | null; curveBId: number | null; fn: 'max' | 'sum' }) => void;
  disabled?: boolean;
}

export default function CurveEditorMix({ profiles, curveAId, curveBId, fn, onChange, disabled }: Props) {
  const { t } = useTranslation(['system']);
  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">{t('system:fanControl.curveTypes.mixDescription')}</p>
      <div className="grid grid-cols-2 gap-2">
        <select
          value={curveAId ?? ''}
          onChange={(e) => onChange({ curveAId: e.target.value ? Number(e.target.value) : null, curveBId, fn })}
          disabled={disabled}
          className="bg-background border border-border rounded px-2 py-1"
        >
          <option value="">{t('system:fanControl.curveTypes.selectCurve')}</option>
          {profiles.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <select
          value={curveBId ?? ''}
          onChange={(e) => onChange({ curveAId, curveBId: e.target.value ? Number(e.target.value) : null, fn })}
          disabled={disabled}
          className="bg-background border border-border rounded px-2 py-1"
        >
          <option value="">{t('system:fanControl.curveTypes.selectCurve')}</option>
          {profiles.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>
      <div className="flex gap-2">
        {(['max', 'sum'] as const).map((f) => (
          <button
            key={f}
            onClick={() => onChange({ curveAId, curveBId, fn: f })}
            disabled={disabled}
            className={`px-3 py-1 rounded text-sm ${fn === f ? 'bg-primary text-primary-foreground' : 'bg-muted'}`}
          >
            {t(`system:fanControl.curveTypes.mixFn.${f}`)}
          </button>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Implement `CurveEditorSync`**

```tsx
import { useTranslation } from 'react-i18next';
import type { FanInfo } from '../../api/fan-control';

interface Props {
  allFans: FanInfo[];
  currentFanId: string;
  syncFanId: string | null;
  onChange: (v: string | null) => void;
  disabled?: boolean;
}

export default function CurveEditorSync({ allFans, currentFanId, syncFanId, onChange, disabled }: Props) {
  const { t } = useTranslation(['system']);
  return (
    <div className="space-y-2">
      <p className="text-xs text-muted-foreground">{t('system:fanControl.curveTypes.syncDescription')}</p>
      <select
        value={syncFanId ?? ''}
        onChange={(e) => onChange(e.target.value || null)}
        disabled={disabled}
        className="w-full bg-background border border-border rounded px-2 py-1"
      >
        <option value="">{t('system:fanControl.curveTypes.selectFan')}</option>
        {allFans.filter((f) => f.fan_id !== currentFanId).map((f) => (
          <option key={f.fan_id} value={f.fan_id}>{f.name}</option>
        ))}
      </select>
    </div>
  );
}
```

- [ ] **Step 6: Integrate into `FanDetails.tsx`**

Open the existing `FanDetails.tsx`. Where the fan curve chart is rendered, wrap it in a conditional based on `fan.curve_type`:

```tsx
<CurveTypeSelector value={fan.curve_type ?? 'graph'} onChange={handleCurveTypeChange} disabled={isReadOnly} />

{(fan.curve_type ?? 'graph') === 'graph' && (
  <FanCurveChart ... existing props ... />
)}
{fan.curve_type === 'flat' && (
  <CurveEditorFlat value={fan.flat_pwm_percent ?? 50} onChange={handleFlatChange} disabled={isReadOnly} />
)}
{fan.curve_type === 'target' && (
  <CurveEditorTarget targetTemp={fan.target_temp_celsius ?? 65} targetPwm={fan.target_pwm_percent ?? 80} onChange={handleTargetChange} disabled={isReadOnly} />
)}
{fan.curve_type === 'mix' && (
  <CurveEditorMix profiles={profiles} curveAId={fan.mix_curve_a_id ?? null} curveBId={fan.mix_curve_b_id ?? null} fn={(fan.mix_function as 'max'|'sum') ?? 'max'} onChange={handleMixChange} disabled={isReadOnly} />
)}
{fan.curve_type === 'sync' && (
  <CurveEditorSync allFans={allFans} currentFanId={fan.fan_id} syncFanId={fan.sync_fan_id ?? null} onChange={handleSyncChange} disabled={isReadOnly} />
)}
```

The `handle*Change` callbacks call `updateFanConfig(fan.fan_id, { ... })` with the corresponding fields, then trigger a refetch.

`FanDetails.tsx` needs `profiles` and `allFans` props — pass them down from `FanControl.tsx`.

- [ ] **Step 7: Export new components from `index.ts`**

Add all five new components to `client/src/components/fan-control/index.ts`.

- [ ] **Step 8: Verify in dev**

```bash
python start_dev.py
```

Switch a fan to each curve type, verify state persists across page reload.

- [ ] **Step 9: Commit**

```bash
git add client/src/components/fan-control/CurveTypeSelector.tsx client/src/components/fan-control/CurveEditor*.tsx client/src/components/fan-control/FanDetails.tsx client/src/components/fan-control/index.ts
git commit -m "feat(client): curve type selector + 5 typed curve editors"
```

---

## Task 16: Frontend — Advanced settings + GPU manual mode + Fan card extras

**Files:**
- Create: `client/src/components/fan-control/AdvancedFanSettings.tsx`
- Create: `client/src/components/fan-control/GpuManualModeToggle.tsx`
- Modify: `client/src/components/fan-control/FanCard.tsx`
- Modify: `client/src/components/fan-control/FanDetails.tsx`

- [ ] **Step 1: `AdvancedFanSettings.tsx`**

```tsx
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronDown, ChevronRight } from 'lucide-react';
import type { FanInfo } from '../../api/fan-control';

interface Props {
  fan: FanInfo;
  onChange: (patch: Partial<FanInfo>) => void;
  disabled?: boolean;
}

export default function AdvancedFanSettings({ fan, onChange, disabled }: Props) {
  const { t } = useTranslation(['system']);
  const [open, setOpen] = useState(false);

  return (
    <div className="border border-border rounded">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center w-full px-3 py-2 text-sm font-medium hover:bg-muted/50"
      >
        {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        <span className="ml-1">{t('system:fanControl.advanced.title')}</span>
      </button>
      {open && (
        <div className="p-3 space-y-4 border-t border-border">
          <div>
            <label className="text-sm">
              {t('system:fanControl.advanced.startPwm')}: {fan.start_pwm_percent ?? 0}%
            </label>
            <input
              type="range" min={0} max={100} step={1}
              value={fan.start_pwm_percent ?? 0}
              onChange={(e) => onChange({ start_pwm_percent: Number(e.target.value) })}
              disabled={disabled}
              className="w-full"
            />
          </div>
          <div>
            <label className="text-sm">
              {t('system:fanControl.advanced.stopBelowTemp')}:{' '}
              {fan.stop_below_temp_celsius != null ? `${fan.stop_below_temp_celsius}°C` : t('common:disabled')}
            </label>
            <input
              type="range" min={0} max={60} step={1}
              value={fan.stop_below_temp_celsius ?? 0}
              onChange={(e) => onChange({ stop_below_temp_celsius: Number(e.target.value) || null })}
              disabled={disabled}
              className="w-full"
            />
          </div>
          <div>
            <label className="text-sm">
              {t('system:fanControl.advanced.responseTime')}: {(fan.response_time_seconds ?? 0).toFixed(1)}s
            </label>
            <input
              type="range" min={0} max={10} step={0.5}
              value={fan.response_time_seconds ?? 0}
              onChange={(e) => onChange({ response_time_seconds: Number(e.target.value) })}
              disabled={disabled}
              className="w-full"
            />
          </div>
          <div>
            <label className="text-sm">{t('system:fanControl.advanced.pwmSteps')}</label>
            <div className="flex gap-2 mt-1">
              {[1, 5, 10, 25].map((s) => (
                <button
                  key={s}
                  onClick={() => onChange({ pwm_steps: s })}
                  disabled={disabled}
                  className={`px-3 py-1 text-sm rounded ${
                    (fan.pwm_steps ?? 1) === s ? 'bg-primary text-primary-foreground' : 'bg-muted'
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: `GpuManualModeToggle.tsx`**

```tsx
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { AlertTriangle } from 'lucide-react';
import { setGpuManualMode } from '../../api/fan-control';
import { handleApiError } from '../../lib/errorHandling';

interface Props {
  fanId: string;
  enabled: boolean;
  onChange: (enabled: boolean) => void;
}

export default function GpuManualModeToggle({ fanId, enabled, onChange }: Props) {
  const { t } = useTranslation(['system']);
  const [busy, setBusy] = useState(false);

  const toggle = async () => {
    setBusy(true);
    try {
      await setGpuManualMode(fanId, !enabled);
      onChange(!enabled);
      toast.success(enabled ? t('system:fanControl.gpu.manualMode.disabled') : t('system:fanControl.gpu.manualMode.enabled'));
    } catch (err) {
      handleApiError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="border border-yellow-500/30 bg-yellow-500/5 rounded p-3 space-y-2">
      <div className="flex items-start gap-2">
        <AlertTriangle size={16} className="text-yellow-500 mt-0.5" />
        <div className="flex-1">
          <div className="text-sm font-medium">{t('system:fanControl.gpu.manualMode.title')}</div>
          <div className="text-xs text-muted-foreground">{t('system:fanControl.gpu.manualMode.warning')}</div>
        </div>
      </div>
      <button
        onClick={toggle}
        disabled={busy}
        className={`px-3 py-1 text-sm rounded ${enabled ? 'bg-destructive text-destructive-foreground' : 'bg-primary text-primary-foreground'}`}
      >
        {enabled ? t('system:fanControl.gpu.manualMode.disable') : t('system:fanControl.gpu.manualMode.enable')}
      </button>
    </div>
  );
}
```

- [ ] **Step 3: Update `FanCard.tsx`**

Three changes:

**(a) GPU badge** if `fan.is_gpu_fan`, and a yellow warning chip if `fan.last_write_error`. Place these next to the fan name/title at the top of the card:

```tsx
{fan.is_gpu_fan && (
  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-xs bg-purple-500/20 text-purple-300 rounded">
    GPU{fan.gpu_vendor ? ` (${fan.gpu_vendor.toUpperCase()})` : ''}
  </span>
)}
{fan.last_write_error && (
  <span className="inline-flex items-center px-1.5 py-0.5 text-xs bg-yellow-500/20 text-yellow-300 rounded" title={fan.last_write_error}>
    PWM-Fehler
  </span>
)}
```

**(b) Source label next to the temperature.** The current temperature block (lines 111–118 today) shows just `{temp}°C` with no indication of which sensor is driving the curve. Replace it with:

```tsx
{(fan.temperature_celsius !== null || !fan.temp_sensor_id) && (
  <div className="mb-3">
    <div className="flex items-baseline justify-between">
      <p className="text-xs text-slate-400">{t('system:fanControl.card.temperature')}</p>
      {fan.temp_sensor_id && (
        <p className="text-[10px] text-slate-500 truncate ml-2" title={fan.temp_sensor_id}>
          {sensorDisplayName(fan.temp_sensor_id, sensors)}
        </p>
      )}
    </div>
    {fan.temperature_celsius !== null ? (
      <p className="text-lg font-bold text-white">
        {formatNumber(fan.temperature_celsius, 1)}°C
      </p>
    ) : (
      <p className="text-sm text-amber-400">
        {t('system:fanControl.card.noSensor')}
      </p>
    )}
  </div>
)}
```

Add a helper in `FanCard.tsx`:

```tsx
function sensorDisplayName(sensorId: string, sensors: TempSensorInfo[]): string {
  // Accept both namespaced and legacy unprefixed IDs
  const found = sensors.find((s) => s.sensor_id === sensorId || s.sensor_id === `hwmon:${sensorId}`);
  if (!found) return sensorId;
  return found.custom_label || found.label || found.device_name;
}
```

Extend props: `sensors: TempSensorInfo[]`. `FanControl.tsx` passes the list it already loads for the SensorsPanel down to each card.

**(c) "No sensor selected" call-to-action.** When `fan.temp_sensor_id` is null (which becomes possible once auto-correction is removed in Task 9 Step 3b, e.g., after a composite sensor that the fan referenced has been deleted), show the amber notice from (b). Clicking the card still selects it; the user picks a sensor in `FanDetails`.

Add the i18n key in Task 17:

```json
"card": {
  ...,
  "noSensor": "Kein Sensor zugewiesen"
}
```

- [ ] **Step 4: Wire `AdvancedFanSettings` and `GpuManualModeToggle` into `FanDetails.tsx`**

Below the curve editor section, add:

```tsx
<AdvancedFanSettings fan={fan} onChange={handleAdvancedChange} disabled={isReadOnly} />
{fan.is_gpu_fan && fan.gpu_vendor === 'amd' && (
  <GpuManualModeToggle
    fanId={fan.fan_id}
    enabled={localGpuManualEnabled}
    onChange={setLocalGpuManualEnabled}
  />
)}
```

Track `localGpuManualEnabled` via local state, initialized from whatever signal you choose (default `false`; user toggles). The backend records state internally; no need to persist across reload for the MVP.

- [ ] **Step 5: Export new components**

Add to `client/src/components/fan-control/index.ts`.

- [ ] **Step 6: Type check**

```bash
cd client
npx tsc --noEmit
```

- [ ] **Step 7: Commit**

```bash
git add client/src/components/fan-control/AdvancedFanSettings.tsx client/src/components/fan-control/GpuManualModeToggle.tsx client/src/components/fan-control/FanCard.tsx client/src/components/fan-control/FanDetails.tsx client/src/components/fan-control/index.ts
git commit -m "feat(client): advanced settings, GPU manual-mode toggle, GPU badge"
```

---

## Task 17: i18n strings

**Files:**
- Modify: `client/src/i18n/locales/de/system.json`
- Modify: `client/src/i18n/locales/en/system.json`

- [ ] **Step 1: Add German strings**

Open `client/src/i18n/locales/de/system.json`. Find the existing `fanControl` block (or add it). Insert under it:

```json
"sensors": {
  "title": "Sensoren",
  "addComposite": "Mix-Sensor",
  "compositeTitle": "Mix-Sensoren",
  "createComposite": "Mix-Sensor erstellen",
  "renamed": "Sensor umbenannt",
  "compositeCreated": "Mix-Sensor erstellt",
  "loadFailed": "Sensoren konnten nicht geladen werden",
  "function": "Funktion",
  "functions": { "max": "Maximum", "min": "Minimum", "avg": "Durchschnitt" },
  "sources": "Quellen",
  "selected": "ausgewählt"
},
"curveTypes": {
  "graph": "Graph",
  "flat": "Konstant",
  "flatLabel": "Konstante PWM",
  "target": "Ziel-Temp",
  "targetDescription": "Halte PWM bei Zieltemperatur. Darunter wird linear bis 0 heruntergeregelt.",
  "targetTemp": "Ziel-Temperatur",
  "targetPwm": "Ziel-PWM",
  "mix": "Mix",
  "mixDescription": "Kombiniere zwei Profile per Funktion.",
  "mixFn": { "max": "Maximum", "sum": "Summe (gedeckelt)" },
  "selectCurve": "Profil wählen…",
  "sync": "Sync",
  "syncDescription": "Übernimm PWM von einem anderen Lüfter.",
  "selectFan": "Lüfter wählen…"
},
"advanced": {
  "title": "Erweiterte Einstellungen",
  "startPwm": "Start-PWM (Anlauf)",
  "stopBelowTemp": "Stop unterhalb",
  "responseTime": "Antwortzeit",
  "pwmSteps": "PWM-Stufen"
},
"gpu": {
  "manualMode": {
    "title": "GPU-Lüfter manuell steuern",
    "warning": "Setzt power_dpm_force_performance_level auf 'manual' und pwm_enable auf 1. Kann GPU-Performance beeinflussen.",
    "enable": "Aktivieren",
    "disable": "Deaktivieren",
    "enabled": "Manueller Modus aktiviert",
    "disabled": "Manueller Modus deaktiviert"
  }
}
```

Also extend the existing `card` block in the same file with:

```json
"card": {
  "noSensor": "Kein Sensor zugewiesen"
}
```

Merge into the existing `card` keys — don't replace.

- [ ] **Step 2: Add English mirror in `en/system.json`**

Same structure, English values.

- [ ] **Step 3: Type check + smoke**

```bash
cd client
npx tsc --noEmit
```

Run dev server, switch language between de and en, confirm strings change.

- [ ] **Step 4: Commit**

```bash
git add client/src/i18n/locales/de/system.json client/src/i18n/locales/en/system.json
git commit -m "i18n(fan): add sensor/curve-type/advanced/gpu strings (de + en)"
```

---

## Task 18: Local verification + PR

**Files:** none

- [ ] **Step 1: Run full backend test suite**

```bash
cd backend
python -m pytest -v
```

Expected: all pass. Per memory `feedback_run_tests_before_pr`: this is the gate before the PR.

- [ ] **Step 2: Frontend type check**

```bash
cd client
npx tsc --noEmit
npm run build
```

Expected: builds cleanly.

- [ ] **Step 3: Manual dev-mode smoke test**

```bash
python start_dev.py
```

In `/fans`:
- [ ] Sensors panel shows hwmon, mock GPU, and (if dev backend exposes them) disk sensors
- [ ] Rename a sensor → label updates and persists after refresh
- [ ] Create a mix sensor (max of two) → appears in list with live temp
- [ ] For one fan, switch curve type to each of: flat, target, mix, sync. Save & refresh — selection persists.
- [ ] Advanced settings panel opens; change start PWM and pwm_steps; refresh — persists.
- [ ] Simulated GPU fan shows a "GPU (AMD)" badge.

- [ ] **Step 4: Deploy verification on BaluNode (real hardware)**

```bash
git push -u origin feat/fan-overhaul
gh pr create --title "feat: fan overhaul (sensors, curve types, GPU fan)" --body "$(cat <<'EOF'
## Summary
- Unified TempSourceRegistry (hwmon + GPU + disk + composite/mix sensors)
- Custom sensor labels (DB-persisted)
- Five curve types: graph, flat, target, mix, sync
- Advanced tuning: start PWM, stop-below-temp, response time, PWM steps
- AMD GPU fan recognition + EINVAL diagnostic + opt-in manual-mode unlock

See `docs/superpowers/specs/2026-05-24-fan-overhaul-design.md`.

## Test plan
- [ ] All backend tests pass: `python -m pytest backend/tests/`
- [ ] Frontend builds: `cd client && npm run build`
- [ ] Manual dev-mode test (see plan task 18 step 3)
- [ ] On BaluNode: GPU fan appears with badge
- [ ] On BaluNode: without manual-mode, PWM write shows diagnostic banner
- [ ] On BaluNode: with manual-mode enabled, GPU fan responds to curve
- [ ] On BaluNode: disabling manual-mode restores prior performance level

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

After PR is merged + deployed to BaluNode, verify on the real GPU per the test plan items.

- [ ] **Step 5: Done**

---

## Self-Review Notes

Spec coverage check:

- Spec §Architecture.1 (Unified Temp Source layer) → Tasks 4–5 + integration in Task 9 ✓
- Spec §Architecture.2 (custom sensor labels) → Task 3 (model), Task 10 (API), Task 14 (UI) ✓
- Spec §Architecture.3 (composite sensors) → Task 3 (model), Task 5 (MixTempSource), Task 10 (API), Task 14 (UI) ✓
- Spec §Architecture.4 (curve types + tuning) → Task 3 (columns), Task 6 (eval), Task 11 (schema + service), Task 15 (UI editors), Task 16 (advanced) ✓
- Spec §Architecture.5 (GPU recognition + EINVAL) → Task 7 ✓
- Spec §Architecture.5 (AMD manual mode) → Task 8 (helper), Task 11 (endpoint), Task 16 (UI toggle) ✓
- Spec §Architecture.6 (no new loop, cached sources) → Task 9 uses cached SMART + monitoring SHM ✓
- Spec §Data Model → Task 2 migration covers everything ✓
- Spec §API Summary → Task 10 + Task 11 cover all endpoints ✓
- Spec §Frontend → Tasks 13–17 ✓
- Spec §Testing → Tests in Tasks 4, 5, 6, 7, 8, 10 ✓
- Spec §Migration Plan ordering → Tasks follow the spec's order ✓
- Spec §Risks (manual-mode restore) → Task 8 captures + restores prior value ✓
- Spec §Verification → Task 18 step 3 + step 4 ✓

No placeholders left. Type consistency check: `evaluate_curve` signature matches its callers in Task 9; `TempSource` `id`/`kind`/`current_temp` are used consistently across registry and concrete sources.
