# GPU Monitoring — Design Spec

**Date:** 2026-04-19
**Status:** Draft (pending user review)
**Related feature:** CPU monitoring (`backend/app/services/monitoring/cpu_collector.py`, `client/src/components/system-monitor/CpuTab.tsx`)

---

## Overview

Add dedicated-GPU monitoring as a peer feature to the existing CPU monitoring. Collect GPU usage, VRAM, clocks, temperatures, fan RPM, power draw, and per-engine activity at the same sampling cadence as CPU, persist to a new `gpu_samples` table, and surface the data in two places in the UI:

- **Dashboard** — the existing CPU quick-stat card becomes a stacked CPU/GPU panel. When a dedicated GPU is present, the card shows CPU on top and GPU below. When no dGPU is detected, the card renders exactly as today (CPU-only, unchanged height).
- **System Monitor** — a new `GPU` tab under the **Hardware** category, placed directly between `CPU` and `Memory`. The tab is hidden entirely when no dGPU is detected.

The first supported vendor is AMD (the production server runs a Radeon RX 7900 XT). NVIDIA and Intel support is deliberately **not** built in this iteration, but the backend is structured so a new vendor is a new ~150-line file without touching the collector.

## Goals

- Parity with CPU monitoring: same sampling cadence, same memory buffer, same DB persistence, same retention mechanism, same route conventions.
- AMD RX 7900 XT fully supported out of the box via `amdgpu` sysfs/hwmon plus binary `gpu_metrics` parsing for per-engine activity.
- Dev-mode (Windows) produces a plausible mocked 7900 XT so frontend/dashboard work runs without real hardware.
- Presence-gated UI: no GPU → no dashboard half, no tab.
- Vendor abstraction ready for NVIDIA/Intel without collector refactors.

## Non-Goals

This spec covers monitoring only. The following are **out of scope** and belong to their own future specs:

- FanControl integration (GPU temperature as fan-curve input).
- Power/Energy dashboard integration (GPU watts aggregated with system draw).
- GPU temperature alerts in `AlertBanner`.
- Multi-GPU setups (rare; first-detected dGPU wins for v1).
- NVIDIA / Intel backend implementations (interface only).
- Pi dashboard GPU tile (Pi build is tree-shaken to a minimal set of pages).

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                 MonitoringOrchestrator                       │
│  (samples CPU/Memory/Network/DiskIO every 3s; adds GPU)      │
└──────────────────────────┬──────────────────────────────────┘
                           │
                    ┌──────▼──────────────────────────────────┐
                    │ GpuMetricCollector (new)                 │
                    │  • 60-sample ring buffer                 │
                    │  • DB persistence → gpu_samples          │
                    │  • get_history_db / get_current          │
                    │  • sample_to_db_dict / db_to_sample      │
                    │  • no-op when backend.detected is False  │
                    └──────────┬───────────────────────────────┘
                               │ delegates raw sensor reads
                               ▼
                 ┌──────────────────────────┐
                 │ GpuBackend (Protocol)    │
                 │  • detected: bool        │
                 │  • device_info()         │
                 │  • read_sample() -> dict │
                 └──────────────────────────┘
                    ▲               ▲                ▲
                    │               │                │
           ┌────────┴─────┐  ┌──────┴─────────┐  ┌──┴────────────────┐
           │ AmdGpuBackend│  │ DevGpuBackend  │  │ (future: Nvidia…) │
           │ sysfs+hwmon+ │  │ mock 7900 XT   │  │                   │
           │ gpu_metrics  │  │                │  │                   │
           └──────────────┘  └────────────────┘  └───────────────────┘
```

**Backend selection at orchestrator startup:**

```python
if settings.is_dev_mode:
    backend = DevGpuBackend()
else:
    amd = AmdGpuBackend()
    backend = amd if amd.detected else _NoGpuBackend()
```

Detection runs once at startup; hotplug is not handled — a service restart is required. This matches the RAID backend pattern.

When `backend.detected == False`, the collector is still registered on the orchestrator (so routing stays consistent) but `collect_sample()` returns `None`, no DB write happens, and API endpoints respond with `404`.

## Data Model

### New table: `gpu_samples` (`backend/app/models/monitoring.py`)

```python
class GpuSample(Base):
    __tablename__ = "gpu_samples"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime(timezone=True), index=True, nullable=False)

    # Device identity (denormalized per sample — see rationale below)
    vendor = Column(String(16), nullable=False)         # "amd" | "nvidia" | "intel"
    device_name = Column(String(128), nullable=False)   # "AMD Radeon RX 7900 XT"
    pci_slot = Column(String(32), nullable=True)        # "0000:03:00.0"

    # Usage
    usage_percent = Column(Float, nullable=True)        # gpu_busy_percent
    engine_gfx_percent = Column(Float, nullable=True)
    engine_compute_percent = Column(Float, nullable=True)
    engine_decode_percent = Column(Float, nullable=True)
    engine_encode_percent = Column(Float, nullable=True)

    # VRAM (BigInteger — see migration 017 pattern for rationale)
    vram_used_bytes = Column(BigInteger, nullable=True)
    vram_total_bytes = Column(BigInteger, nullable=True)

    # Clocks
    core_clock_mhz = Column(Float, nullable=True)
    memory_clock_mhz = Column(Float, nullable=True)

    # Temperatures
    temperature_edge_celsius = Column(Float, nullable=True)
    temperature_junction_celsius = Column(Float, nullable=True)
    temperature_memory_celsius = Column(Float, nullable=True)

    # Fan / Power
    fan_rpm = Column(Integer, nullable=True)
    power_watts = Column(Float, nullable=True)
```

All metric columns are `nullable=True` so backends may omit values without schema errors (an iGPU without a fan, an NVIDIA backend without junction temp).

**Identity columns denormalized per sample** — ~40 bytes/sample overhead, but no join required, and on hardware replacement the history stays correctly attributed to the old GPU. A normalized `gpu_devices` table was considered and rejected as premature.

### Pydantic schemas (`backend/app/schemas/monitoring.py`)

```python
class GpuSampleSchema(BaseModel):
    timestamp: datetime
    vendor: str
    device_name: str
    pci_slot: Optional[str] = None

    usage_percent: Optional[float] = None
    engine_gfx_percent: Optional[float] = None
    engine_compute_percent: Optional[float] = None
    engine_decode_percent: Optional[float] = None
    engine_encode_percent: Optional[float] = None

    vram_used_bytes: Optional[int] = None
    vram_total_bytes: Optional[int] = None

    core_clock_mhz: Optional[float] = None
    memory_clock_mhz: Optional[float] = None

    temperature_edge_celsius: Optional[float] = None
    temperature_junction_celsius: Optional[float] = None
    temperature_memory_celsius: Optional[float] = None

    fan_rpm: Optional[int] = None
    power_watts: Optional[float] = None


class GpuDeviceInfo(BaseModel):
    """Immutable device metadata — exposed as its own endpoint."""
    vendor: str
    device_name: str
    pci_slot: Optional[str] = None
    vram_total_bytes: Optional[int] = None
    driver_version: Optional[str] = None


class CurrentGpuResponse(GpuSampleSchema):
    pass


class GpuHistoryResponse(BaseModel):
    samples: List[GpuSampleSchema]
    sample_count: int
    source: str   # "memory" | "database" | "memory (fallback)" | "database (fallback)"
```

### Alembic migration

A new revision under `backend/alembic/versions/` creates `gpu_samples` with the schema above (including `BigInteger` for VRAM, matching migration 017) and an index on `timestamp`. The migration also seeds a row in `monitoring_config` with `metric_name = "gpu"` using the same retention defaults as CPU, so cleanup reaps GPU samples automatically.

## Backend — Collector and Backends

### `GpuBackend` protocol (`backend/app/services/monitoring/gpu/backend.py`)

```python
class GpuBackend(Protocol):
    @property
    def detected(self) -> bool: ...
    def device_info(self) -> GpuDeviceInfo: ...
    def read_sample(self) -> dict:
        """Return a dict with any subset of GpuSample columns.
        vendor and device_name are required; all others optional."""
```

### `AmdGpuBackend` (`backend/app/services/monitoring/gpu/amd_backend.py`)

**Detection.** Iterate `/sys/class/drm/card*/device/`. For each card, read `vendor` — match `0x1002` for AMD. Filter out iGPUs using the presence/shape of `pp_dpm_sclk` and a subsystem-ID check. Pick the first remaining dGPU. Cache sysfs paths and the PCI slot once at construction. A constructor parameter `sysfs_root: Path = Path("/")` allows test injection.

**Sensor reads** (each wrapped in a defensive `try/except`, returning `None` on failure so one broken sensor does not poison the whole sample):

| Metric | Source |
|---|---|
| `usage_percent` | `gpu_busy_percent` |
| `vram_used_bytes` / `vram_total_bytes` | `mem_info_vram_used` / `mem_info_vram_total` |
| `core_clock_mhz` | `hwmon/freq1_input` (Hz → MHz) |
| `memory_clock_mhz` | `pp_dpm_mclk` (parse `* MHz` from the line marked with `*`) |
| `temperature_edge_celsius` | `hwmon/temp1_input` (label `edge`) |
| `temperature_junction_celsius` | `hwmon/temp2_input` (label `junction`) |
| `temperature_memory_celsius` | `hwmon/temp3_input` (label `mem`) |
| `fan_rpm` | `hwmon/fan1_input` |
| `power_watts` | `hwmon/power1_average` (µW → W) |
| `engine_*_percent` | Binary parse of `gpu_metrics` (see below) |

**`gpu_metrics` binary parser.** The file begins with a `struct metrics_table_header` (4 bytes: `size u16`, `format_revision u8`, `content_revision u8`). For RDNA3 (7900 XT) the typical values are `format_revision=1, content_revision=4` (`gpu_metrics_v1_4`). The parser reads the header, dispatches to the matching layout, and extracts only:

- `average_gfx_activity` (u16, %)
- `average_mm_activity` (u16, multimedia)
- `vcn_activity[4]` on v1_4+ (maps max/mean to decode/encode)

Unknown revisions → engine values `None`, all other metrics still work. No external dependency (no `amdsmi` / `rocm-smi`).

### `DevGpuBackend` (`backend/app/services/monitoring/gpu/dev_backend.py`)

Mocks an `AMD Radeon RX 7900 XT (dev-mock)` with 20 GB VRAM. Values use sin/cos + jitter for plausible fluctuation, matching the CPU dev-mock pattern. `detected = True` always when `settings.is_dev_mode`.

Sample shape:

```python
{
  "vendor": "amd", "device_name": "AMD Radeon RX 7900 XT (dev-mock)",
  "pci_slot": "0000:03:00.0",
  "usage_percent": 30 + 25*sin(t/20) + uniform(-5,5),
  "engine_gfx_percent": usage + uniform(-5,5),
  "engine_compute_percent": max(0, usage - 10 + uniform(-5,5)),
  "engine_decode_percent": uniform(0, 15),
  "engine_encode_percent": uniform(0, 8),
  "vram_used_bytes": int(6e9 + 2e9*sin(t/30)),
  "vram_total_bytes": 20*1024**3,
  "core_clock_mhz": 2500 + uniform(-300, 300),
  "memory_clock_mhz": 2500,
  "temperature_edge_celsius": 55 + uniform(-3, 8),
  "temperature_junction_celsius": 65 + uniform(-3, 10),
  "temperature_memory_celsius": 70 + uniform(-3, 8),
  "fan_rpm": 1500 + int(uniform(-200, 400)),
  "power_watts": 180 + uniform(-30, 60),
}
```

### `GpuMetricCollector` (`backend/app/services/monitoring/gpu_collector.py`)

Inherits from `MetricCollector[GpuSampleSchema]`. Selects a backend in `__init__`:

```python
def __init__(self):
    super().__init__(...)
    if settings.is_dev_mode:
        self.backend: GpuBackend = DevGpuBackend()
    else:
        amd = AmdGpuBackend()
        self.backend = amd if amd.detected else _NoGpuBackend()

@property
def detected(self) -> bool:
    return self.backend.detected

def collect_sample(self) -> Optional[GpuSampleSchema]:
    if not self.backend.detected:
        return None
    try:
        raw = self.backend.read_sample()
        return GpuSampleSchema(timestamp=datetime.now(timezone.utc), **raw)
    except Exception as e:
        logger.error(f"GPU sample collection failed: {e}")
        return None
```

`_NoGpuBackend` is a null-object (`detected = False`, `read_sample` never called) — keeps the `self.backend` reference non-None so consumers don't need null checks on the attribute itself.

`get_db_model()`, `sample_to_db_dict()`, `db_to_sample()` follow the `CpuMetricCollector` pattern 1:1.

### Orchestrator integration

`MonitoringOrchestrator.__init__` gains `self.gpu_collector = GpuMetricCollector()`. The main sample loop calls `gpu_collector.collect_sample()` like any other collector; `None` results skip both the ring buffer push and the DB write. New helper methods `get_gpu_history(limit)` and `get_gpu_current_with_db_fallback(db)` mirror the CPU equivalents.

## API

New route file `backend/app/api/routes/monitoring_gpu.py`, registered under the existing `/api/monitoring` prefix. Kept separate from `monitoring.py` because that file is already large.

| Method | Path | Auth | Rate limit | Behavior |
|---|---|---|---|---|
| `GET` | `/api/monitoring/gpu/info` | `get_current_user` | `system_monitor` | Device metadata. `404` when no GPU detected; `200` + `GpuDeviceInfo` otherwise. |
| `GET` | `/api/monitoring/gpu/current` | `get_current_user` | `system_monitor` | Current sample. `404` when no GPU detected; `503` when detected but buffer still empty; `200` + `CurrentGpuResponse` otherwise. |
| `GET` | `/api/monitoring/gpu/history` | `get_current_user` | `system_monitor` | History with `time_range`, `source`, `limit` query params — identical signature to `/cpu/history`. `404` when no GPU detected. |

**Why `/info` is separate from `/current`.** The frontend needs to know whether a GPU exists *before* any samples have been collected (e.g. immediately after service start) to gate the dashboard half and the system-monitor tab. A `404` on `/info` means unambiguously "no GPU". `/current` can return `503` (GPU present, buffer empty) — a different state. Keeping them separate keeps the two signals distinct.

The existing `orchestrator` reports active collectors to health/admin endpoints; the GPU collector reports `inactive` when `detected=False`, matching the existing pattern.

### MaintenanceTools color mapping

`client/src/components/admin/MaintenanceTools.tsx` defines `METRIC_COLORS` for `cpu`, `memory`, `network`, `disk_io`, `process`. Add a `gpu` entry so cleanup stats render in GPU-themed colors instead of falling through to the default. The backend cleanup service reads from `monitoring_config` generically, so the seed row added by the Alembic migration is sufficient server-side.

### Security

- No new admin-only routes; `get_current_user` suffices (same as CPU).
- No user-input paths → `_jail_path()` not relevant.
- `gpu_metrics` binary read is internal sysfs — no traversal risk.
- `system_monitor` rate limit blocks scraping abuse.

## Frontend

### API client (`client/src/api/monitoring.ts`)

Extended with three functions paralleling `getCpuCurrent` / `getCpuHistory`:

```ts
export interface GpuDeviceInfo {
  vendor: string;
  device_name: string;
  pci_slot: string | null;
  vram_total_bytes: number | null;
  driver_version: string | null;
}

export interface GpuSample { /* mirrors backend schema */ }

export async function getGpuInfo(): Promise<GpuDeviceInfo | null>;   // null on 404
export async function getGpuCurrent(): Promise<GpuSample | null>;    // null on 404/503
export async function getGpuHistory(params): Promise<GpuHistoryResponse>;
```

### `useGpuPresence` hook (`client/src/hooks/useGpuPresence.ts`)

Central presence source. Calls `getGpuInfo()` once, caches with `staleTime: Infinity` (detection does not change at runtime). Returns `{ present, info, loading }`. Dashboard and SystemMonitor both read from the same cached state — no duplicate request, no flicker.

### Dashboard — stacked `<CpuGpuPanel />` component

The existing inline CPU quick-stat card in `Dashboard.tsx` is refactored into a new component `client/src/components/dashboard/CpuGpuPanel.tsx`. This isolates logic and keeps `Dashboard.tsx` cleaner.

Behavior:

- **No GPU:** panel renders identically to today's CPU card — same height, same sparkline, same progress bar. Side-by-side with the remaining three cards (Memory, Storage, Uptime), the grid looks unchanged.
- **GPU present:** panel is taller. Top half is CPU (icon, percent, meta, sparkline/progress) — unchanged. A thin `border-t border-slate-800/60` divider. Bottom half is GPU (GPU icon, `usage_percent`, `device_name` as meta, edge-temp as submeta, own sparkline/progress).

The height asymmetry with neighboring cards is intentional and accepted. Neighbor cards pin to `items-start`.

Icons: `lucide-react` `Cpu` for CPU, `Gpu` (with a neutral fallback like `Monitor` if unavailable) for GPU. Click handler for the GPU half: `() => navigate('/system?tab=gpu')`.

### SystemMonitor — `GpuTab` component (`client/src/components/system-monitor/GpuTab.tsx`)

Parallel in structure to `CpuTab.tsx`. Sections top-to-bottom:

1. **Device header** — Vendor badge, device name (large), PCI slot + driver version (small); live-sync indicator on the right.
2. **KPI row** (4-column grid) — Usage %, VRAM used/total, core clock, power W. Each with a sparkline below.
3. **Temperature block** (3-column grid) — Edge, Junction, Memory charts.
4. **Per-engine usage** — Toggle "Overview | Per-Engine" analogous to CPU's per-thread toggle. Per-engine shows four small cards (3D/Graphics, Compute, Decode, Encode) with sparkline + progress. Overview shows a combined stacked-area chart.
5. **Fan + memory clock** (2-column footer) — Fan RPM chart, memory clock chart.

Time-range selector (1h/6h/24h/7d) at the top, reusing `client/src/components/monitoring/TimeRangeSelector`.

### SystemMonitor — tab registration (`SystemMonitor.tsx`)

In `BASE_CATEGORIES`, the Hardware category's tab array gets `gpu` inserted **directly after `cpu`, before `memory`**. Conditional filtering:

```ts
const { present: hasGpu } = useGpuPresence();
const categories = useMemo(
  () => BASE_CATEGORIES.map(cat =>
    cat.id === 'hardware'
      ? { ...cat, tabs: cat.tabs.filter(t => t.id !== 'gpu' || hasGpu) }
      : cat
  ),
  [hasGpu]
);
```

Deep-link `/system?tab=gpu` without a GPU falls back to `cpu` via the existing default-tab logic. `TabType` gains `'gpu'`. Icon: `lucide-react` `Gpu` or an inline SVG matching the CPU chipset style.

### i18n

New keys under `client/src/i18n/locales/{de,en}/`:

- `dashboard:gpu.*` — title, "No dedicated GPU", labels for power / temp / usage in the stacked panel.
- `monitor.tabs.gpu`, `monitor.gpu.*` — tab label, section headers, engine names, unit labels.

### Device-mode

`<CpuGpuPanel />` and `GpuTab` live in the **Desktop** build (`__DEVICE_MODE__`). The **Pi** build (`PiDashboard`) has its own compact dashboard and is not extended here — Pi devices almost never have a dGPU. If this changes, a follow-up spec covers it.

## Testing

### Backend

| File | Scope |
|---|---|
| `backend/tests/monitoring/test_gpu_backend_amd.py` | Detection finds 7900 XT, ignores iGPU. `read_sample()` reads all metrics correctly from sysfs fixtures. Missing/broken files → metric `None`, no crash. `gpu_metrics` binary parser: real 7900 XT dump, `format_revision=1, content_revision=4` → correct engine values. Unknown revisions → engine values `None`, rest intact. |
| `backend/tests/monitoring/test_gpu_backend_dev.py` | Dev mock returns values in plausible ranges; `detected=True`. |
| `backend/tests/monitoring/test_gpu_collector.py` | `get_db_model() is GpuSample`. `sample_to_db_dict` / `db_to_sample` round-trip. `collect_sample()` returns `None` when `backend.detected=False`. Backend exceptions are swallowed and logged. |
| `backend/tests/monitoring/test_orchestrator_gpu.py` | Orchestrator starts cleanly with `detected=False` (no DB writes, no exceptions). GPU sample loop integrates analogously to CPU. |
| `backend/tests/api/test_monitoring_gpu_routes.py` | Auth required (401 without token). `/info` 404 when not detected, 200 + schema when detected. `/current` 503 on empty buffer, 404 when no GPU. `/history` with `time_range` returns a list. Rate limit applies. |
| `backend/tests/monitoring/test_gpu_migration.py` (optional) | Alembic upgrade/downgrade of `gpu_samples`. |

**Sysfs fixtures** live under `backend/tests/fixtures/amd_gpu/7900xt/` — one text file per sysfs path, plus a real binary `gpu_metrics` dump. `AmdGpuBackend(sysfs_root=fixture_path)` injects the fixture root during tests.

### Frontend

Vitest unit tests:

- `useGpuPresence`: 404 → `present: false`; 200 → `present: true` + info.
- `<CpuGpuPanel />`: no GPU → renders CPU-only (snapshot); with GPU → renders divider + GPU section.
- `GpuTab`: renders device header, KPI row, temperature block; engine toggle switches view; time-range change triggers reload.

Playwright E2E (optional — repo's E2E scripts are placeholders today):

- Dashboard → click GPU half → `/system?tab=gpu`.

### Manual verification

**Dev mode (Windows)** — `python start_dev.py`:

- Dashboard shows stacked CPU + mock GPU, "AMD Radeon RX 7900 XT (dev-mock)" visible.
- `/system?tab=gpu` renders all sections; engine toggle works; values fluctuate.

**Prod mode (Debian server with 7900 XT)**:

- Systemd starts cleanly; `journalctl -u baluhost-backend` shows a GPU-detection log line with device name.
- `curl -H "Authorization: …" http://localhost:8000/api/monitoring/gpu/info` returns real values.
- Dashboard + SystemMonitor match; `gpu_samples` rows appear (verify via `/api/admin-db/`).

**Prod mode without dGPU (Rock Pi Mini)**:

- Dashboard shows CPU only (card height unchanged from today).
- `/system` has no GPU tab.
- `/system?tab=gpu` falls back to CPU tab.
- `/api/monitoring/gpu/info` returns `404`.

## Rollout Order

The implementation plan should build in this sequence. Each step is independently testable:

1. DB model + Alembic migration + schemas.
2. `GpuBackend` protocol + `DevGpuBackend` + tests.
3. `AmdGpuBackend` + sysfs fixtures + tests (including `gpu_metrics` binary parser).
4. `GpuMetricCollector` + orchestrator hookup + tests.
5. API routes + route tests.
6. Frontend API client + `useGpuPresence` hook.
7. `<CpuGpuPanel />` + Dashboard integration.
8. `GpuTab` + SystemMonitor tab registration + icon + i18n.
9. `MaintenanceTools` color mapping extended with `gpu`.
10. Manual prod verification on the real server.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| `gpu_metrics` format changes with a future kernel update | Header-version dispatch; unknown revision → engine values `None`, other metrics still work. |
| Sysfs paths differ across kernel versions | Per-metric `try/except`; missing source → `None` instead of a crashed sample. |
| Dual-GPU setups (iGPU + dGPU) | Detection filters out iGPU via `pp_dpm_sclk` / subsystem check; takes first dGPU. |
| Multi-dGPU (rare, e.g. mining rigs) | v1 uses first detected. Documented as a limitation; future spec for multi-GPU. |
| Asymmetric card height on dashboard when GPU present | Intentional per design; neighbor cards pin to `items-start`. |

## Open Items Resolved During Brainstorming

- **Vendor strategy:** AMD now, pluggable backend interface (not a single-collector hardcoded block).
- **Metrics depth:** Full set including per-engine activity (3D / Compute / Decode / Encode) parsed from `gpu_metrics`.
- **Sampling / storage:** 1:1 with CPU — same cadence, same memory buffer, same DB persistence, same retention.
- **Absence handling:** No GPU → dashboard card stays CPU-only at original height; system-monitor tab hidden entirely.
- **Dashboard layout:** Stacked within one card — CPU top, GPU bottom when present.
- **Scope boundary:** Monitoring + retention only. No FanControl / Power / Alert integrations in this iteration.
