# GPU Power Management Design

**Date:** 2026-04-30
**Status:** Design
**Author:** Xveyn (with Claude)

## Summary

Add a dedicated GPU power management subsystem that puts a discrete GPU into low-power states when neither a display is connected nor active GPU compute is happening. Targets the existing hybrid-use case (NAS + HomeLab + Steam/Proton gaming + Ollama-backed plugins) without interfering with active workloads.

The system mirrors the existing CPU `PowerManagerService` architecture: vendor-abstracted backends (AMD via sysfs, NVIDIA via `nvidia-smi`, dev mock), demand-registration API, async monitor loop, plugin event hook for cleanup. Three power states (`active` / `standby` / `deep_idle`) handle the Ollama-style "model resident in VRAM but compute idle" case without bouncing.

## Goals

- Reduce idle GPU power draw on a NAS when display output and compute are both inactive (target: ~80 W → ~15–25 W on RX 7900 XT).
- Vendor-agnostic: support AMD (RDNA2/3) and NVIDIA out of the box. Dev backend for Windows.
- Coexist cleanly with the existing CPU `PowerManagerService`. No changes to its semantics.
- Allow plugins (e.g., Balu_Code/Ollama) to opt out of deep idle while a model is loaded, via a public demand API and a deep-idle event hook.
- Opt-in: disabled by default. Admin-toggleable via the existing Power Management UI.

## Non-Goals

- Does **not** suspend the GPU PCI device (`runtime PM` / D3) — too unstable for active dGPUs.
- Does **not** manage iGPUs (only dGPUs detected by the existing GPU monitoring backend).
- Does **not** force-kill GPU workloads. The deep-idle event is advisory; plugins decide what to do.
- Does **not** add new dependencies. AMD uses sysfs, NVIDIA uses `nvidia-smi` (already required for monitoring).

## Use Cases

1. **NAS-only night:** TV off, no Steam, no Ollama. After 30 s + 120 s grace → `deep_idle`. Lowest DPM, lowest power profile.
2. **NAS + Ollama plugin loaded, user idle:** Model resident in VRAM (e.g., 10 GB), GPU usage 0 %. Within the first 30 s → `standby` (medium profile, no clock pinning). After grace timeout, the deep-idle event fires; the Ollama plugin handles unload (`keep_alive=0`) and the GPU drops to `deep_idle`.
3. **Steam/Proton on TV:** Display connected → always `active`. Power management is bypassed regardless of usage.
4. **Mid-session pause (movie paused, AFK):** Display still connected → stays `active`. We do not down-clock based on usage alone when a display is on (that's the GPU driver's job and it does it well).

## Architecture

### Module Layout

```
backend/app/services/power/gpu/
  __init__.py
  protocol.py          # GpuPowerBackend ABC, GpuPowerState enum
  manager.py           # GpuPowerManagerService (singleton, async)
  display_detector.py  # Reads /sys/class/drm/card*/card*-*/status
  amd_backend.py       # sysfs writes (power_dpm_force_performance_level, pp_power_profile_mode)
  nvidia_backend.py    # nvidia-smi -lgc, -pl
  dev_backend.py       # Mock for Windows / dev mode
  events.py            # Event hook registry (gpu_deep_idle_entering, _exiting)
  config_store.py      # Persistence for GpuPowerConfig

backend/app/schemas/gpu_power.py
  GpuPowerState (enum: active, standby, deep_idle)
  GpuPowerConfig (thresholds, enabled flag)
  GpuPowerStatus (current state, reason, last_transition, active_demands)
  GpuPowerDemandInfo (source, expires_at, description)

backend/app/models/gpu_power.py
  GpuPowerLog (state transitions, timestamp, reason)

backend/app/api/routes/gpu_power.py
  GET    /api/gpu-power/status
  GET    /api/gpu-power/config
  PUT    /api/gpu-power/config
  POST   /api/gpu-power/demand           (register)
  DELETE /api/gpu-power/demand/{source}  (unregister)
  GET    /api/gpu-power/history

client/src/pages/PowerManagement.tsx (existing)
  + new card: GpuPowerCard
client/src/api/gpuPower.ts (new)
client/src/components/power/GpuPowerCard.tsx (new)
```

### State Machine

```
                        +------------------+
                        |     ACTIVE       |
                        |  (auto profile)  |
                        +------------------+
                          ^   ^         |
                          |   |         | display disconnect
            display       |   |         | && usage < 5% for 30s
            connected,    |   |         v
            OR usage      |   |     +------------------+
            spike >5%     |   |     |     STANDBY      |
                          |   |     |  (medium profile)|
                          |   |     +------------------+
            demand        |   |        |          ^
            registered    |   |        | grace    | demand registered
                          |   |        | 120s     | OR vram drops <15%
                          |   |        v          |
                          |   |     +------------------+
                          |   |     |   DEEP_IDLE      |
                          |   |     |  (lowest DPM,    |
                          |   +-----+  POWER_SAVING)   |
                          |         +------------------+
                          |
                          +-- emergency wake (any signal)
```

**Transitions:**

- `active → standby`: `display_count == 0 ∧ usage_percent < 5 ∧ no_demand` for `idle_window_seconds` (default 30 s).
- `standby → deep_idle`: still all idle conditions, plus elapsed `deep_idle_extra_seconds` (default 120 s) since entering standby. **Before** transitioning, fire `gpu_deep_idle_entering` event. Plugins have a short window (default 5 s) to release VRAM (Ollama unload). Then transition.
- `deep_idle → active` / `standby → active`: any of: display connected, usage > 5 %, demand registered. Single signal is enough — no debounce on wake-up.

### Why three states (recap)

Two states would bounce between full-power and deep-idle every time an Ollama user pauses to think. Three states give us a "warm idle" that holds the model resident with low clocks and fast wake-up, without the worst-case ~80 W idle, and only commits to deep idle (which evicts the model) after a longer grace window.

### Backend Protocol

```python
# protocol.py
from abc import ABC, abstractmethod
from typing import Optional
from app.schemas.gpu_power import GpuPowerState

class GpuPowerBackend(ABC):
    @property
    @abstractmethod
    def detected(self) -> bool: ...

    @property
    @abstractmethod
    def vendor(self) -> str: ...  # "amd" | "nvidia" | "dev"

    @abstractmethod
    async def apply_state(self, state: GpuPowerState) -> tuple[bool, Optional[str]]:
        """Apply target state. Returns (success, error_message)."""

    @abstractmethod
    async def current_state(self) -> Optional[GpuPowerState]:
        """Read back current state from hardware (best-effort)."""

    @abstractmethod
    async def has_write_permission(self) -> bool: ...
```

### AMD Backend (`amd_backend.py`)

Reuses device detection from `services/monitoring/gpu/amd_backend.py` (find first dGPU with `pp_dpm_sclk`). Per-state behavior is driven by `GpuPowerConfig.amd_active / amd_standby / amd_deep_idle`. Built-in defaults:

| State | `power_dpm_force_performance_level` | `pp_power_profile_mode` |
|---|---|---|
| `active` | `auto` | (don't touch) |
| `standby` | `auto` | `POWER_SAVING` |
| `deep_idle` | `low` | `POWER_SAVING` |

The user can override either field per state via the UI. Available `performance_level` values are read from `power_dpm_force_performance_level`'s sysfs sibling enumerations (kernel exposes the set in the file's documentation); we conservatively present `auto`, `low`, `high`, `manual`, `profile_standard`, `profile_min_sclk`, `profile_min_mclk`, `profile_peak`. Available `profile_mode` indexes are parsed from `pp_power_profile_mode` on startup (the file lists each mode by name); the user picks by name and we resolve to the index at apply time. Falls back to `BOOTUP_DEFAULT` if the named mode is not exposed by the driver.

Writes go through `subprocess.run(["sudo", "tee", path], ...)` only if needed; if user has direct write permission (group `video`) we write directly. Same `has_write_permission()` pattern as `cpu_linux_backend.py`.

### NVIDIA Backend (`nvidia_backend.py`)

Detection: `nvidia-smi -L` returns ≥1 GPU. Per-state behavior driven by `GpuPowerConfig.nvidia_*`. On first detection, the backend queries the card's reported range:

```
nvidia-smi --query-gpu=clocks.gr.min,clocks.gr.max,power.min_limit,power.max_limit,power.default_limit --format=csv,noheader,nounits
```

and seeds defaults if the user hasn't set values:

| State | Default `min_clock_mhz` | Default `max_clock_mhz` | Default `power_limit_watts` |
|---|---|---|---|
| `active` | None (reset) | None (reset) | default_limit |
| `standby` | min_clock | mid = (min+max)/2 | default_limit |
| `deep_idle` | min_clock | min_clock | power.min_limit |

Apply at runtime:
- If `min_clock_mhz` and `max_clock_mhz` are both set: `nvidia-smi -lgc <min>,<max>`. Either being None means "use the value from active state on reset" — i.e. `active` calls `nvidia-smi -rgc` if both are None.
- If `power_limit_watts` is set: `nvidia-smi -pl <watts>`. Reset on `active` via the default_limit.

Persistence mode (`nvidia-smi -pm 1`) is enabled once on service start. The seeded defaults are also exposed via `GET /api/gpu-power/capabilities` so the UI can pre-populate the form and validate min/max bounds.

### Dev Backend (`dev_backend.py`)

In-memory state, no hardware writes. Returns simulated current state. Used on Windows and in `NAS_MODE=dev`. Mirrors `cpu_dev_backend.py` style.

### Display Detector (`display_detector.py`)

```python
async def get_active_display_count(sysfs_root: Path = Path("/")) -> int:
    """Count DRM connectors with status='connected' AND enabled='enabled'."""
    drm = sysfs_root / "sys/class/drm"
    if not drm.exists():
        return 0
    count = 0
    for entry in drm.iterdir():
        # connectors look like card0-HDMI-A-1, card0-DP-1
        if not re.match(r"card\d+-", entry.name):
            continue
        status = (entry / "status").read_text().strip() if (entry / "status").exists() else ""
        enabled = (entry / "enabled").read_text().strip() if (entry / "enabled").exists() else ""
        if status == "connected" and enabled == "enabled":
            count += 1
    return count
```

`enabled` covers the case where a connector is physically connected but DPMS-off / unused — we still treat that as no active display.

On dev/Windows, returns a value from a settable mock (default 0 in dev mode, configurable via dev-only debug endpoint for testing).

### Manager (`manager.py`)

Singleton, async, mirrors `PowerManagerService`:

```python
class GpuPowerManagerService:
    _instance: Optional["GpuPowerManagerService"]

    async def start(self) -> None: ...
    async def stop(self) -> None: ...

    async def get_status(self) -> GpuPowerStatus: ...
    async def get_config(self) -> GpuPowerConfig: ...
    async def set_config(self, config: GpuPowerConfig) -> None: ...

    async def register_demand(
        self, source: str, timeout_seconds: Optional[int] = None,
        description: Optional[str] = None
    ) -> str: ...
    async def unregister_demand(self, source: str) -> bool: ...

    # Event hook
    def on_deep_idle_entering(self, callback: Callable[[], Awaitable[None]]) -> None: ...
    def on_deep_idle_exiting(self, callback: Callable[[], Awaitable[None]]) -> None: ...
```

**Monitor loop (every 5 s):**

```python
async def _monitor_loop(self):
    while self._is_running:
        try:
            await self._tick()
        except Exception as e:
            logger.error(f"GPU power monitor error: {e}")
        await asyncio.sleep(self._config.monitor_interval_seconds)

async def _tick(self):
    if not self._config.enabled or not self._backend.detected:
        return

    displays = await get_active_display_count()
    sample = self._latest_gpu_sample()  # from monitoring shm
    has_demand = bool(self._demands)
    usage = sample.usage_percent if sample else 0.0

    is_idle = displays == 0 and usage < self._config.usage_threshold_percent and not has_demand

    if not is_idle:
        if self._state != GpuPowerState.ACTIVE:
            await self._transition(GpuPowerState.ACTIVE, reason="not_idle")
        return

    now = datetime.now(timezone.utc)
    if self._state == GpuPowerState.ACTIVE:
        if now - self._idle_since >= timedelta(seconds=self._config.idle_window_seconds):
            await self._transition(GpuPowerState.STANDBY, reason="idle_window_elapsed")
    elif self._state == GpuPowerState.STANDBY:
        if now - self._standby_since >= timedelta(seconds=self._config.deep_idle_extra_seconds):
            # fire event, give plugins time to unload
            await self._emit_deep_idle_entering()
            await asyncio.sleep(self._config.deep_idle_grace_seconds)
            await self._transition(GpuPowerState.DEEP_IDLE, reason="grace_elapsed")
```

`_latest_gpu_sample()` reads from the existing monitoring shm file (`/tmp/baluhost_shm/gpu.json`) so we don't double-poll the GPU.

### Plugin Event Hook

Plugins register callbacks via a small registry:

```python
# events.py
_deep_idle_entering_callbacks: list[Callable[[], Awaitable[None]]] = []
_deep_idle_exiting_callbacks: list[Callable[[], Awaitable[None]]] = []

def register_deep_idle_entering(cb): _deep_idle_entering_callbacks.append(cb)
def register_deep_idle_exiting(cb):  _deep_idle_exiting_callbacks.append(cb)

async def emit_deep_idle_entering():
    await asyncio.gather(*(cb() for cb in _deep_idle_entering_callbacks), return_exceptions=True)
```

Plugins (Balu_Code) register on startup:
```python
register_deep_idle_entering(lambda: ollama_client.unload_all_models())
```

The GPU power module does **not** import plugin code. Plugins import the hook.

### Schemas (`backend/app/schemas/gpu_power.py`)

```python
class GpuPowerState(str, Enum):
    ACTIVE = "active"
    STANDBY = "standby"
    DEEP_IDLE = "deep_idle"

class AmdProfileMode(str, Enum):
    """Index into pp_power_profile_mode. Detected at runtime; constants here are
    the canonical names used by the kernel driver."""
    BOOTUP_DEFAULT = "BOOTUP_DEFAULT"
    POWER_SAVING = "POWER_SAVING"
    VIDEO = "VIDEO"
    VR = "VR"
    COMPUTE = "COMPUTE"
    CUSTOM = "CUSTOM"
    FULL_SCREEN_3D = "3D_FULL_SCREEN"

class AmdStateConfig(BaseModel):
    """Per-state AMD overrides. None = use default for that state."""
    performance_level: Optional[str] = Field(None, description="auto | low | high | manual | profile_*")
    profile_mode: Optional[AmdProfileMode] = Field(None, description="pp_power_profile_mode name")

class NvidiaStateConfig(BaseModel):
    """Per-state NVIDIA overrides."""
    min_clock_mhz: Optional[int] = Field(None, ge=0, description="--lock-gpu-clocks min")
    max_clock_mhz: Optional[int] = Field(None, ge=0, description="--lock-gpu-clocks max; None = no upper lock")
    power_limit_watts: Optional[int] = Field(None, ge=0, description="-pl in watts; None = card default")

class GpuPowerConfig(BaseModel):
    enabled: bool = False

    # Thresholds (all editable via UI)
    idle_window_seconds: int = Field(30, ge=10, le=600)
    deep_idle_extra_seconds: int = Field(120, ge=30, le=3600)
    deep_idle_grace_seconds: int = Field(5, ge=0, le=30)
    usage_threshold_percent: float = Field(5.0, ge=0.0, le=50.0)
    monitor_interval_seconds: int = Field(5, ge=1, le=60, description="How often the monitor loop ticks")

    # Per-state, per-vendor clock/profile overrides. Defaults are filled at
    # startup from the detected card's reported range; user overrides win.
    amd_active: AmdStateConfig = Field(default_factory=lambda: AmdStateConfig(performance_level="auto"))
    amd_standby: AmdStateConfig = Field(default_factory=lambda: AmdStateConfig(performance_level="auto", profile_mode=AmdProfileMode.POWER_SAVING))
    amd_deep_idle: AmdStateConfig = Field(default_factory=lambda: AmdStateConfig(performance_level="low", profile_mode=AmdProfileMode.POWER_SAVING))

    nvidia_active: NvidiaStateConfig = Field(default_factory=NvidiaStateConfig)  # all None → reset clocks
    nvidia_standby: NvidiaStateConfig = Field(default_factory=NvidiaStateConfig)  # filled from card range at startup
    nvidia_deep_idle: NvidiaStateConfig = Field(default_factory=NvidiaStateConfig)  # filled from card range at startup

class GpuPowerDemandInfo(BaseModel):
    source: str
    registered_at: datetime
    expires_at: Optional[datetime] = None
    description: Optional[str] = None

class GpuPowerStatus(BaseModel):
    enabled: bool
    detected: bool
    vendor: Optional[str]
    current_state: GpuPowerState
    last_transition: Optional[datetime]
    last_reason: Optional[str]
    active_demands: list[GpuPowerDemandInfo]
    has_write_permission: bool
    estimated_power_watts: Optional[float] = None  # from monitoring sample

class GpuPowerCapabilities(BaseModel):
    """What the detected card supports — feeds the UI form."""
    vendor: Optional[str]
    # AMD
    amd_performance_levels: list[str] = Field(default_factory=list)
    amd_profile_modes: list[str] = Field(default_factory=list, description="Names parsed from pp_power_profile_mode")
    # NVIDIA
    nvidia_min_clock_mhz: Optional[int] = None
    nvidia_max_clock_mhz: Optional[int] = None
    nvidia_min_power_watts: Optional[int] = None
    nvidia_max_power_watts: Optional[int] = None
    nvidia_default_power_watts: Optional[int] = None
```

The `PUT /api/gpu-power/config` handler validates submitted clocks against the card's reported range from `GpuPowerCapabilities` and rejects out-of-range values with HTTP 422 (matching FastAPI/Pydantic validation patterns elsewhere in the codebase).

### Database Model (`backend/app/models/gpu_power.py`)

```python
class GpuPowerLog(Base):
    __tablename__ = "gpu_power_log"
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    state = Column(String(16), nullable=False)  # active/standby/deep_idle
    previous_state = Column(String(16), nullable=True)
    reason = Column(String(64), nullable=False)
    source = Column(String(64), nullable=True)
    power_watts_at_transition = Column(Float, nullable=True)
```

Alembic migration creates the table. No changes to existing tables.

### Routes (`backend/app/api/routes/gpu_power.py`)

All routes require `Depends(deps.get_current_user)`. Config write requires `get_current_admin`. Rate-limited via `get_limit("gpu_power")`.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/gpu-power/status` | user | Current state, demands, vendor, hw permission |
| GET | `/api/gpu-power/config` | user | Read config (enabled, thresholds, per-state clocks) |
| PUT | `/api/gpu-power/config` | admin | Update config (validated against capabilities) |
| GET | `/api/gpu-power/capabilities` | user | Card's reported clock/power range, available AMD profile modes & performance levels — used to populate UI selects and enforce bounds |
| POST | `/api/gpu-power/demand` | user | Register demand (body: `source, timeout_seconds, description`) |
| DELETE | `/api/gpu-power/demand/{source}` | user | Unregister |
| GET | `/api/gpu-power/history?limit=100` | user | State transition log |

Demands registered via the API are also accepted from internal Python callers (plugins) via `manager.register_demand(...)`.

### Frontend

New card on `pages/PowerManagement.tsx`:

```
┌─ GPU Power Management ──────────────┐
│ [enabled toggle]                     │
│                                      │
│ Status: Standby (since 14:32:11)     │
│ Vendor: AMD Radeon RX 7900 XT        │
│ Estimated draw: 32 W                 │
│ Active demands: 1 (ollama_inference) │
│                                      │
│ ▾ Thresholds                         │
│   Idle window:        [30] s         │
│   Grace before deep:  [120] s        │
│   Deep-idle grace:    [5] s          │
│   Usage threshold:    [5] %          │
│   Monitor interval:   [5] s          │
│                                      │
│ ▾ Per-state hardware (AMD)           │
│   Active:    perf=[auto▾]            │
│              profile=[(unset)▾]      │
│   Standby:   perf=[auto▾]            │
│              profile=[POWER_SAVING▾] │
│   Deep idle: perf=[low▾]             │
│              profile=[POWER_SAVING▾] │
│                                      │
│ ▾ Per-state hardware (NVIDIA)        │
│   (only shown if vendor=nvidia)      │
│   Active:    [reset]                 │
│   Standby:   min=[___] max=[___] MHz │
│              power=[___] W           │
│   Deep idle: min=[___] max=[___] MHz │
│              power=[___] W           │
│                                      │
│ Bounds: min/max enforced against     │
│ `/api/gpu-power/capabilities`.       │
│                                      │
│ [view history]                       │
└──────────────────────────────────────┘
```

If `detected == false`, show a single line: "No discrete GPU detected." If `enabled == true` but `has_write_permission == false`, show the same warning notification flow as CPU power management (`check_and_notify_permissions`).

`client/src/api/gpuPower.ts` mirrors `client/src/api/power.ts`.

### Lifespan Integration

In `app/main.py` lifespan:

```python
# startup
await start_gpu_power_manager()

# shutdown
await stop_gpu_power_manager()
```

On `stop()`, the manager attempts to apply `ACTIVE` so the next process boot starts clean.

`service_status.py` registers the GPU power manager so admin dashboard shows its health (sample count, errors, current state).

## Error Handling

| Failure | Behavior |
|---|---|
| Backend write fails (sysfs EACCES) | Log warning, surface in `has_write_permission=false`, do not retry transition. State machine reverts to `ACTIVE` to be safe. |
| `nvidia-smi` not on PATH | Backend `detected=false`, manager idles. |
| GPU monitoring shm missing/stale (>30 s old) | Treat as `usage=0, vram=0` — assume idle. Log warning. We trust display detection alone in this degraded mode. |
| Plugin event callback raises | Caught by `gather(return_exceptions=True)`, logged, transition proceeds. |
| Demand from non-existent plugin (orphan) | Auto-expires via `expires_at` if set; otherwise visible in admin UI for manual cleanup. |

## Testing

### Unit
- `tests/services/power/gpu/test_state_machine.py` — drive `_tick()` with synthetic time/sample inputs, assert transitions.
- `tests/services/power/gpu/test_amd_backend.py` — temp dir mock for sysfs; verify writes to `power_dpm_force_performance_level`.
- `tests/services/power/gpu/test_nvidia_backend.py` — mock subprocess, assert command shape.
- `tests/services/power/gpu/test_display_detector.py` — temp sysfs tree fixture.
- `tests/services/power/gpu/test_demand_api.py` — register/unregister, `expires_at` cleanup.
- `tests/services/power/gpu/test_event_hook.py` — `register_deep_idle_entering` is invoked, exception in one callback does not block others.

### Integration
- `tests/api/test_gpu_power_routes.py` — endpoint contract, auth requirements, rate limiting.
- `tests/services/power/gpu/test_lifespan.py` — start/stop cycles, ensures `ACTIVE` on shutdown.

### Manual verification (production)
- On the deployed Debian box with RX 7900 XT: enable, disconnect TV, observe `journalctl -u baluhost-backend` for state transitions and `cat /sys/class/drm/card0/device/power_dpm_force_performance_level` to verify `low` is written.
- Run `radeontop` or `sensors amdgpu-pci-*` to confirm power draw drops.
- Reconnect TV, verify return to `auto` within one tick (≤5 s).

## Security

- Routes require auth (user for read, admin for config/write).
- Demand `source` strings are not interpolated into shell commands. Backend writes use list-args.
- No new secrets. AMD writes use the `video` group permission check; NVIDIA uses `nvidia-smi` (root or with `nvidia-modprobe` SUID set up).
- Audit log: state transitions and config changes go through `audit/get_audit_logger_db()` with category `power`.

## Migration / Rollout

- Disabled by default. Existing users see no change until they toggle it.
- Alembic migration: `add_gpu_power_log_table`. Table-only addition, no breaking changes.
- Config persisted to a new row in the existing `power_profile_config` table-style key/value store (`backend/app/services/power/config_store.py` pattern), under key `gpu_power_config`. JSON-serialized `GpuPowerConfig`. Falls back to defaults on first load.

## Open Questions / Future Work (out of scope here)

- Auto-tuned NVIDIA standby clocks: detect optimal mid-range from card metadata rather than a fixed default.
- Per-display-output policy: e.g., always-on on DP-1 (monitor on desk), aggressive on HDMI-A-1 (TV).
- Deeper integration with sleep manager: when the system goes to soft-sleep, force `deep_idle` directly (skip standby grace).
- Multi-GPU systems: design assumes one dGPU. If a second is added later, manager would need a list of backends.

## Acceptance Criteria

1. With feature enabled, no display connected, no plugin demands, after 30 + 120 s the AMD backend writes `low` to `power_dpm_force_performance_level` and the deep-idle event fires.
2. Plugging in a display causes a transition back to `active` within 5 s.
3. Registering a demand via `POST /api/gpu-power/demand` causes immediate transition to `active` regardless of state.
4. Disabling the feature releases all DPM locks (writes `auto`) and stops the monitor loop.
5. With no dGPU detected, the feature reports `detected=false` and performs no writes.
6. All new endpoints respond correctly under rate-limit and auth dependencies; admin-only writes reject non-admin tokens with 403.
