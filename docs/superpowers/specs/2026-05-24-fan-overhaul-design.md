# Fan Control Overhaul — Sensors, Curve Types, GPU Fan

**Status:** Design approved (2026-05-24)
**Branch:** `feat/fan-overhaul` (off `main`)
**Scope:** "Foundation + Curve Types" (per brainstorming choice)

## Context

BaluHost has a working fan-control stack: hwmon scan, PWM write via direct or sudo-tee fallback, temperature curves with hysteresis, schedules, profiles, presets. Two real-world gaps surfaced in production on the BaluNode box (Debian 13, Ryzen 5 5600GT + dedicated AMD GPU):

1. **The GPU fan is unreachable from the UI as a first-class fan.** The PWM scanner does pick it up (it iterates all hwmon dirs) but does not label it as a GPU fan, and writes to its `pwm1` fail with `EINVAL` ("Das Argument ist ungültig"). The reason is almost certainly that AMD's `amdgpu` driver requires `pwm1_enable=1` *and* `power_dpm_force_performance_level=manual` before manual PWM writes are accepted — neither is set today. The user wants to control the GPU fan from the Fan Editor.
2. **Sensor management is rigid.** Sensors expose only their kernel-supplied label (`Tctl`, `edge`, etc.) — they cannot be renamed. There is no way to combine sensors (e.g., "use the hottest of CPU and GPU"). And only hwmon sensors are wired into fan curves; the SMART disk temps and GPU edge/junction/mem temps the app already collects are not available as curve inputs.

Layered on top, the user wants the Fan Editor to grow closer to the Windows app *FanControl* (Rem0o): multiple curve types (graph/flat/target/mix/sync), advanced tuning (start %, stop-below-temp, response time, PWM steps), and sensor mixing.

This spec defines a single feature branch that adds the foundation (unified sensor sources, custom labels, mix sensors, GPU fan recognition, EINVAL diagnostics) **and** the FanControl-style curve types in one bundle. It is large but cohesive — the UI for curve types only makes sense with the sensor work, and vice versa.

## Goals

- Make GPU fans first-class in the Fan Editor, including the manual-mode unlock for AMD GPUs (opt-in).
- Give the diagnostic information needed when a PWM write fails (driver name, `pwm_enable` state).
- Let users rename any temperature sensor to a meaningful name (e.g., "RAID disks" instead of "drivetemp temp1").
- Expose disk and GPU temperatures as curve inputs alongside hwmon.
- Let users build composite sensors via max/min/avg of multiple sources.
- Let users pick a curve type per fan: existing `graph`, new `flat`, `target`, `mix`, `sync`.
- Add advanced tuning per fan: start PWM, stop-below-temp, response-time smoothing, PWM steps.

## Non-Goals

- No new curve type beyond the five named (no PID controller, no "trigger" curves).
- No automatic discovery of which sensor "owns" which fan — sensor assignment stays manual.
- No fan-curve scripting / formulas — curves are limited to the typed editors above.
- No changes to the schedule or profile subsystems.

---

## Architecture

### 1. Unified Temperature Source layer

Today, `FanControlBackend.get_temperature(sensor_id)` only knows hwmon IDs. Replace this with a registry that resolves any source.

New file: `backend/app/services/power/fan_sources.py`

```python
class TempSource(Protocol):
    id: str                          # canonical, namespaced: "hwmon:hwmon0_temp1" | "gpu:edge" | "disk:sda" | "mix:<uuid>"
    kind: Literal["hwmon", "gpu", "disk", "mix"]
    device_name: str                 # raw driver/device name (k10temp, amdgpu, sda, …)
    backend_label: Optional[str]     # kernel-supplied label
    is_cpu_sensor: bool

    async def current_temp(self) -> Optional[float]: ...

class TempSourceRegistry:
    def all_sources(self) -> List[TempSource]: ...
    async def get_temp(self, sensor_id: str) -> Optional[float]: ...
    def display_label(self, sensor_id: str) -> str: ...   # applies custom label override
```

Concrete sources:

- `HwmonTempSource` — wraps the existing `LinuxFanControlBackend.get_available_temp_sensors()` per entry. ID format `hwmon:<hwmon_dir>_temp<n>`.
- `GpuTempSource` — reads `services/monitoring/gpu` (the existing AMD/NVIDIA collectors that already publish edge/junction/mem). One source per available channel. ID format `gpu:edge`, `gpu:junction`, `gpu:mem`.
- `DiskTempSource` — reads from the existing `services/hardware/smart` cached samples (no new smartctl call per fan tick). ID format `disk:<device>` (e.g. `disk:sda`). Falls back to `None` if no recent sample.
- `MixTempSource` — DB-backed (see Data Model). Resolves its `source_ids` recursively, applies `function`. Cycle detection by tracking the recursion path.

**ID format migration.** Existing `FanConfig.temp_sensor_id` values look like `hwmon0_temp1` (no namespace). The registry treats unprefixed IDs as `hwmon:` for backwards-compat. The migration script does **not** rewrite existing rows; the registry handles both forms.

**Where it's called.** `FanControlService._monitor_and_control_fans` calls `registry.get_temp(config.temp_sensor_id)` instead of `_backend.get_temperature(...)`. The backend method stays for the hwmon scan use case but is no longer the only path.

### 2. Custom sensor labels

New ORM model in `backend/app/models/fans.py`:

```python
class TempSensorLabel(Base):
    __tablename__ = "temp_sensor_labels"
    sensor_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    custom_label: Mapped[str] = mapped_column(String(100), nullable=False)
    updated_at: Mapped[datetime] = ...
```

`TempSourceRegistry.display_label(sensor_id)` returns `custom_label ?? backend_label ?? device_name`. Loaded once at startup, refreshed on PUT.

API:

- `PUT /api/fans/sensors/{sensor_id}/label` — body `{ "label": "RAID disks" }`. 422 if label empty or >100 chars.
- `DELETE /api/fans/sensors/{sensor_id}/label` — clear back to default.

### 3. Composite (mix) sensors

New ORM model:

```python
class CompositeTempSensor(Base):
    __tablename__ = "composite_temp_sensors"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)   # "mix:" + uuid4 hex
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    function: Mapped[str] = mapped_column(String(10), nullable=False)  # "max" | "min" | "avg"
    source_ids_json: Mapped[str] = mapped_column(Text, nullable=False) # JSON list[str]
    created_at, updated_at
```

API under `/api/fans/composite-sensors`:

- `GET /` — list with resolved current temp
- `POST /` — `{ name, function, source_ids: [...] }`. Validate: ≥2 sources, no cycle (compose with this row included), all source IDs resolvable.
- `PUT /{id}` — same body, partial allowed
- `DELETE /{id}` — also clears any `FanConfig.temp_sensor_id` pointing at it (set to NULL with audit log entry)

Hard limits: max 5 composite sensors per system, max 6 sources per composite. (Keeps the UI manageable and resolution cheap.)

### 4. Curve types

Extend `FanConfig`:

| Column | Type | Default | Meaning |
|---|---|---|---|
| `curve_type` | String(20) | `"graph"` | One of `graph` / `flat` / `target` / `mix` / `sync` |
| `flat_pwm_percent` | Integer | NULL | Used when `curve_type="flat"` |
| `target_temp_celsius` | Float | NULL | Used when `curve_type="target"` |
| `target_pwm_percent` | Integer | NULL | Used when `curve_type="target"` |
| `mix_curve_a_id` | Integer FK → fan_curve_profiles | NULL | Used when `curve_type="mix"` |
| `mix_curve_b_id` | Integer FK → fan_curve_profiles | NULL | Used when `curve_type="mix"` |
| `mix_function` | String(10) | NULL | `"max"` or `"sum"` (clamped to 100) |
| `sync_fan_id` | String(100) | NULL | Source fan for `curve_type="sync"` |
| `start_pwm_percent` | Integer | NULL | Minimum spin-up PWM when fan transitions from 0 |
| `stop_below_temp_celsius` | Float | NULL | If temp falls this far below the lowest curve point, set PWM to 0 |
| `response_time_seconds` | Float | 0.0 | Exponential smoothing of PWM changes |
| `pwm_steps` | Integer | 1 | Quantize PWM to multiples of this (1 = stepless) |

Calculation dispatch lives in a new module `backend/app/services/power/fan_curve_eval.py`:

```python
def evaluate_curve(
    config: FanConfig,
    temp: Optional[float],
    *,
    prev_pwm: int,
    other_fan_pwms: Dict[str, int],   # for sync
    profile_loader: Callable[[int], List[dict]],  # for mix
    dt_seconds: float,
) -> int:
```

- `graph` → existing interpolation
- `flat` → `flat_pwm_percent`
- `target` → if `temp >= target_temp` return `target_pwm`, else interpolate between (0,0) and (target_temp, target_pwm) — gentle ramp-up to the hold point
- `mix` → resolve both profiles, evaluate each with `temp`, combine via `max` or `min(100, a+b)`
- `sync` → `other_fan_pwms.get(sync_fan_id, prev_pwm)`

Then post-processing (in order):

1. Apply `stop_below_temp_celsius`: if set and `temp < threshold - hysteresis`, PWM=0. If `temp ≥ threshold`, normal flow resumes.
2. Apply `start_pwm_percent`: if `prev_pwm == 0` and target > 0, jump to `max(target, start_pwm)` on first non-zero step.
3. Apply `response_time_seconds`: `new = α·target + (1-α)·prev` with `α = min(1, dt / response_time)`. If `response_time == 0`, no smoothing.
4. Apply `pwm_steps`: `round(pwm / steps) * steps`, clamped to `[min_pwm, max_pwm]`.
5. Apply hysteresis (existing).
6. Apply emergency override (existing — unchanged).

The order matters: emergency must override smoothing; stop-below-temp must apply before start-pwm so we don't spin up immediately after stopping.

### 5. GPU fan recognition + EINVAL diagnostics

In `LinuxFanControlBackend._scan_pwm_fans`, when scanning each hwmon dir, also record:

```python
fan_info["device_driver"] = hwmon_name_value    # already read
fan_info["is_gpu_fan"] = hwmon_name_value in {"amdgpu", "nouveau"}
fan_info["gpu_vendor"] = "amd" if hwmon_name_value == "amdgpu" else None
```

Surface these new fields on `FanData` and `FanInfo` schemas.

For the EINVAL diagnostic, refactor `_write_hwmon_file` to capture the failure detail:

- On write failure, additionally read `pwm{n}_enable` (if it exists) and `name`, and log them.
- Add a new field to `FanInfo`: `last_write_error: Optional[str]` populated whenever a `set_pwm` for that fan fails. The Fan Editor reads it and shows a yellow banner with the diagnostic + suggested fix.

For AMD GPU fans specifically, add an opt-in unlock flow:

- New endpoint `POST /api/fans/{fan_id}/gpu-manual-mode` body `{ "enable": true|false }`.
- On enable: write `power_dpm_force_performance_level=manual` to the GPU's device dir, write `pwm{n}_enable=1`. Audit-log.
- On disable: revert `power_dpm_force_performance_level=auto`, write `pwm{n}_enable=2` (automatic via thermal).
- UI shows a checkbox "GPU-Fan manuell steuern (kann GPU-Performance beeinflussen)" with a warning tooltip. Off by default.

### 5b. Remove silent CPU-sensor auto-correction

The current `_load_fan_configs` (`fan_control.py` lines 243–281) rewrites any fan's `temp_sensor_id` back to the CPU sensor at every startup if it points anywhere else, with a log comment about a "board sensor ~26°C bug." This silently overrides the user's chosen sensor — including any composite sensor — on every restart, and is the reason case fans currently always display CPU temperature.

The auto-correction is removed. The branch that assigns a CPU default to *newly discovered* fans (those without any existing `FanConfig` row) stays — that's a sensible first-time default. The Fan Card will additionally display *which* sensor is driving the curve next to the temperature, so users see whether the displayed value is meaningful for that fan or whether they should reassign it. When `temp_sensor_id` is null (e.g., after a deleted composite sensor), the card shows an amber "no sensor assigned" notice instead of a misleading temperature.

### 6. Sensor monitoring loop must read all sources

Currently, the fan monitoring loop runs every `fan_sample_interval_seconds` (5s) and reads only the configured sensor per fan. The disk and GPU sources read from cached SHM/SMART data — no extra subprocess work. The composite source can recursively call other sources, but cycle detection caps depth at 5.

No new background worker. The existing `_monitoring_loop` keeps the same cadence.

---

## Data Model Summary

New tables (one Alembic migration):

```
temp_sensor_labels      (sensor_id PK, custom_label, updated_at)
composite_temp_sensors  (id PK, name, function, source_ids_json, created_at, updated_at)
```

Modified `fan_configs`:
```
+ curve_type             default "graph"
+ flat_pwm_percent       NULL
+ target_temp_celsius    NULL
+ target_pwm_percent     NULL
+ mix_curve_a_id         NULL FK
+ mix_curve_b_id         NULL FK
+ mix_function           NULL
+ sync_fan_id            NULL
+ start_pwm_percent      NULL
+ stop_below_temp_celsius NULL
+ response_time_seconds  default 0.0
+ pwm_steps              default 1
```

All additions are nullable or have defaults — no breaking change. Existing rows keep `curve_type="graph"`.

---

## API Summary

New / changed endpoints under `/api/fans`:

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/sensors` | user | Existing — now returns custom_label, kind, gpu_vendor, namespaced ID |
| PUT | `/sensors/{sensor_id}/label` | admin | Set custom label |
| DELETE | `/sensors/{sensor_id}/label` | admin | Clear custom label |
| GET | `/composite-sensors` | user | List composite sensors with resolved temps |
| POST | `/composite-sensors` | admin | Create composite sensor |
| PUT | `/composite-sensors/{id}` | admin | Update |
| DELETE | `/composite-sensors/{id}` | admin | Delete (also unlinks from any fan) |
| PATCH | `/config` | admin | Existing — body now accepts the new curve_type + tuning fields |
| POST | `/{fan_id}/gpu-manual-mode` | admin | Toggle AMD GPU manual fan control |

`FanInfo` response gains: `is_gpu_fan: bool`, `gpu_vendor: Optional[str]`, `last_write_error: Optional[str]`, `curve_type: str`, plus the new tuning fields.

Sensor IDs in API responses are always namespaced (`hwmon:hwmon0_temp1`). Inputs accept both namespaced and legacy unprefixed IDs.

---

## Frontend

### Routes & Pages

No new route. All work lives on the existing `/fans` (`FanControl.tsx`).

### New components

`client/src/components/fan-control/`:

- `SensorsPanel.tsx` — new section above the fans, lists every source: name (inline edit), kind badge (CPU/GPU/Disk/Mix), current temp, "delete" only on composite sensors. Button "Mix-Sensor erstellen" opens `CompositeSensorModal.tsx`.
- `CompositeSensorModal.tsx` — name input, function radio (max/min/avg), multi-select source list, validation hint.
- `CurveTypeSelector.tsx` — segmented control: Graph / Target / Flat / Mix / Sync. Switches the editor below.
- `CurveEditorFlat.tsx` — single slider.
- `CurveEditorTarget.tsx` — temp + pwm inputs with a small explanatory diagram.
- `CurveEditorMix.tsx` — two profile dropdowns + function selector.
- `CurveEditorSync.tsx` — fan dropdown (excludes self).
- `AdvancedFanSettings.tsx` — collapsible inside `FanDetails`. Contains: start PWM slider, stop-below-temp slider, response time slider (0–10s), PWM steps select (1/5/10/25).
- `GpuManualModeToggle.tsx` — only rendered if `fan.is_gpu_fan && fan.gpu_vendor === "amd"`. Checkbox + warning text + button "Aktivieren". Calls the new endpoint.

`FanDetails.tsx` is restructured: top half stays (mode + current state), bottom half becomes `<CurveTypeSelector>` + the typed editor + `<AdvancedFanSettings>` + `<GpuManualModeToggle>` (when applicable).

`FanCard.tsx` gains a small GPU badge (icon + "GPU") when `is_gpu_fan`. A yellow warning chip when `last_write_error` is set.

### API client

`client/src/api/fan-control.ts`:

- Extend `TempSensorInfo`: `custom_label: string | null`, `kind: "hwmon"|"gpu"|"disk"|"mix"`, `gpu_vendor: string | null`.
- New: `renameSensor(sensorId, label)`, `clearSensorLabel(sensorId)`.
- New: `listComposites()`, `createComposite()`, `updateComposite()`, `deleteComposite()`.
- New: `setGpuManualMode(fanId, enable)`.
- Extend `UpdateFanConfigRequest` with the new tuning fields and curve config.
- Extend `FanInfo` with `is_gpu_fan`, `gpu_vendor`, `last_write_error`, `curve_type`, and curve-type-specific fields.

### i18n

New strings under `client/src/i18n/locales/{de,en}/system.json`:

- `fanControl.sensors.*` — sensors panel labels, rename modal, composite sensor wording
- `fanControl.curveTypes.{graph,flat,target,mix,sync}` — labels + short descriptions
- `fanControl.advanced.*` — start PWM, stop below temp, response time, PWM steps explanations
- `fanControl.gpu.manualMode.{title,warning,enable,disable}`
- `fanControl.errors.pwmWriteFailed` with `{driver}` and `{enableMode}` interpolation

---

## Testing

`backend/tests/`:

- `test_fan_sources.py` — registry resolves hwmon, gpu, disk, mix; cycle detection raises; missing sources return None.
- `test_fan_composite_api.py` — create/update/delete; reject self-cycle; reject >6 sources; reject >5 composites total; cascade-unlink on delete.
- `test_fan_sensor_label_api.py` — set, clear, validation (length, empty).
- `test_fan_curve_eval.py` — one test per curve type with known inputs/outputs, including post-processing chain (start/stop/response/steps interactions).
- `test_fan_gpu_recognition.py` — hwmon scan tags amdgpu PWM as GPU fan; nouveau too; intel iGPU is not (no `pp_dpm_sclk`).
- `test_fan_gpu_manual_mode.py` — endpoint flips `pwm1_enable` and `power_dpm_force_performance_level` on enable; reverts on disable; non-admin rejected.
- `test_fan_einval_diagnostic.py` — write failure captures driver name and enable mode in `last_write_error`.

Frontend tests are not the baseline (project has placeholder unit tests); manual UI verification in dev mode is the verification gate.

---

## Migration Plan

1. Branch from `main`: `git switch main && git pull && git switch -c feat/fan-overhaul`.
2. Alembic migration first — schema additions only.
3. Backend: `fan_sources.py` registry + new ORM models + label/composite services.
4. Backend: `fan_curve_eval.py` + dispatch in `FanControlService._monitor_and_control_fans`.
5. Backend: GPU recognition fields in `LinuxFanControlBackend` + EINVAL diagnostic capture.
6. Backend: new API endpoints + extend existing schemas/responses.
7. Backend tests for the above.
8. Frontend: API client updates, then `SensorsPanel`, then `CurveTypeSelector` + typed editors, then `AdvancedFanSettings`, then `GpuManualModeToggle`.
9. i18n strings.
10. Manual verification in dev mode (mock backend already exists), then on the BaluNode box via SSH for the GPU manual-mode flow.

---

## Risks & Open Questions

- **AMD GPU manual mode side-effects.** `power_dpm_force_performance_level=manual` may pin clocks or change power behavior depending on what else has been written to `pp_*` files. Mitigation: read the current value before changing, restore exactly that value on disable.
- **Composite sensor + sync curve combo.** A fan in `sync` mode that targets another fan in `mix` mode that uses a composite sensor — depth of recursion is bounded, but errors in any step must surface clearly. Mitigation: depth limit of 5 + a `last_eval_error` field similar to `last_write_error`.
- **Existing curves keep working.** Verified by the `curve_type="graph"` default and the legacy unprefixed sensor ID acceptance.
- **i18n coverage.** Only `de` and `en` are maintained today — keep parity with both for every new key.

---

## Verification

After implementation:

1. `python -m pytest backend/tests/test_fan_*.py -v` — all new tests pass.
2. `python start_dev.py` — open `/fans`, verify:
   - Sensors panel lists hwmon + simulated GPU + simulated disk sources
   - Renaming a sensor persists across page reload
   - Creating a mix sensor with `max` of two sources shows the correct value
   - Each curve type can be selected and saved
   - Advanced settings persist
3. Deploy to BaluNode via the existing deploy pipeline, verify on real hardware:
   - GPU fan appears with "GPU" badge
   - Without manual-mode enabled, attempting to set PWM shows the diagnostic banner with `amdgpu` + current `pwm1_enable` value
   - With manual-mode enabled, PWM writes succeed and the fan responds
   - Disabling manual-mode restores prior `power_dpm_force_performance_level` value
