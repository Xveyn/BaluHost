# GPU Power Manager Multi-Worker State Sync

**Date:** 2026-05-02
**Status:** Draft (not started)
**Branch:** `fix/gpu-power-manager-multi-worker` (created from `origin/main` 2026-05-02)
**Sibling plan:** `2026-05-01-power-manager-multi-worker-fix.md` (CPU manager — already shipped in v1.31.3)

## Problem

`GpuPowerManagerService` (`backend/app/services/power/gpu/manager.py:38`) is a per-process Python singleton with the same multi-worker bug we just fixed for the CPU power manager. Production runs 4 Uvicorn workers; only the primary worker runs `start_gpu_power_manager()` (`backend/app/core/lifespan.py:425`). On followers, `_backend` stays `None`, so:

- `get_status()` returns `detected=False, vendor=None, has_write_permission=False`
- The UI alternates between the primary's correct answer ("AMD active, write OK") and three followers' wrong answer ("No discrete GPU detected"), depending on which worker handled the request.
- `set_config()` writes only to one worker's memory; the primary's `_tick` never sees the change.
- `register_demand()` puts the demand into the worker's local `_demands` dict; the primary's monitor loop never sees it, so the wake-up to ACTIVE never fires from a secondary worker.

### Concrete production evidence

A 10-call burst against `/api/gpu-power/status` from the browser produced:

| Call | detected | vendor | has_write |
|---|---|---|---|
| 0–6 | false | null | false |
| 7 | true | amd | true |
| 8–9 | false | null | false |

9 of 10 followers, 1 of 10 primary. State field (`active`) was consistent because it comes from the service-status registry's DB-backed reader, but the GPU-detection fields read straight from the per-process manager.

## Goal

Make secondary workers safe to handle `/api/gpu-power/*` requests by moving live mutable state to the DB and dispatching hardware operations to the primary via a small command queue. Same pattern as the CPU branch — the heavy lifting is already done.

## Non-goals

- No change to the CPU power manager
- No change to AMD/NVIDIA backend drivers themselves
- No change to display detection (`display_detector.py`) — read-only sysfs is already multi-worker-safe
- No change to GPU sample reads from monitoring SHM
- No new GPU configuration knobs

## Re-use Inventory

The CPU branch (v1.31.3) shipped the building blocks; the GPU branch can re-use them with minimal adjustments:

| CPU branch artefact | GPU branch action |
|---|---|
| `backend/app/services/power/command_queue.py` | **Generalise** to take a manager instance + dispatcher. Either factor into `app/services/power/_command_queue_base.py` or duplicate as `gpu/command_queue.py`. Decision: duplicate (~200 LOC) — the CPU module's signatures (`_primary_apply_profile`, etc.) are too CPU-specific to abstract cleanly without weakening type safety. |
| `backend/app/services/power/config_store.py` runtime-state helpers | **Pattern**: separate file `gpu/runtime_state_store.py` with `load_runtime_state`/`update_runtime_state`/`upsert_demand`/`delete_demand`/`list_active_demands`/`delete_expired_demands` for `gpu_power_*` tables. |
| `IS_PRIMARY_WORKER` lifespan flag | Re-used as-is. |
| `monitoring/shm.py` | Re-used. New file: `gpu_status.json`. |
| Service registry DB-readers (`PRIMARY_ONLY_SERVICES`) | `gpu_power_manager` is **already** in the list — no change needed. |

## Implementation Steps

### Step 1 — New tables: `gpu_power_runtime_state`, `gpu_power_demands`, `gpu_power_commands`

`backend/app/models/gpu_power.py` — add three classes following the same shape as the CPU manager's tables:

```python
class GpuPowerRuntimeState(Base):
    __tablename__ = "gpu_power_runtime_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # always 1
    current_state: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    detected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    vendor: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    has_write_permission: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_transition: Mapped[Optional[datetime]] = ...
    last_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = ...
    updated_by_pid: Mapped[Optional[int]] = ...


class GpuPowerDemand(Base):
    __tablename__ = "gpu_power_demands"
    source: Mapped[str] = mapped_column(String(100), primary_key=True)
    registered_at: Mapped[datetime] = ...
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)


class GpuPowerCommand(Base):
    __tablename__ = "gpu_power_commands"
    # mirrors PowerCommand: id, command, payload_json, requested_by, requested_at, status, error_message, completed_at
    # commands: "set_config" | "register_demand" | "unregister_demand"
    # ("transition_state" is internal — only the primary's tick fires it; not exposed via queue)
```

- [ ] Tests: schema seeded, runtime-state row id=1
- [ ] Migration with seed row

### Step 2 — `gpu/runtime_state_store.py`

DB-helpers analogous to CPU's `config_store`:

```python
def load_runtime_state() -> dict[str, Any]: ...
def update_runtime_state(**fields: Any) -> bool: ...
def upsert_demand(source, registered_at, expires_at, description) -> bool: ...
def delete_demand(source) -> bool: ...
def list_active_demands() -> List[GpuPowerDemandInfo]: ...
def delete_expired_demands() -> List[GpuPowerDemandInfo]: ...
```

Same session-handling discipline: short-lived `SessionLocal()`, never holds across `await asyncio.sleep`.

### Step 3 — `gpu/command_queue.py`

Mirror `power/command_queue.py` exactly: `enqueue_command`, `wait_for_completion` (~3 s default), `run_poll_loop(manager)` (500 ms tick), `_dispatch`. Three commands:

- `set_config` (payload = serialized `GpuPowerConfig`) → `manager._primary_set_config(config)`
- `register_demand` (payload = source, timeout_seconds, description) → `manager._primary_register_demand(...)`
- `unregister_demand` (payload = source) → `manager._primary_unregister_demand(source)`

State transitions (`_transition`) stay inside the primary's tick — no need to expose them via queue.

### Step 4 — Refactor `manager.py`: primary/follower mode

```python
class GpuPowerManagerService:
    async def start(self, primary: bool = True) -> None:
        self._primary = primary
        self._hydrate_from_runtime_state()
        self._config = load_gpu_power_config()
        self._is_running = True

        if not primary:
            self._backend = None
            return

        self._backend = self._select_backend()
        # publish detection result so followers see it
        update_runtime_state(
            detected=self._backend.detected,
            vendor=self._backend.vendor if self._backend.detected else None,
            has_write_permission=await self._backend.has_write_permission(),
        )
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        self._command_poll_task = asyncio.create_task(command_queue.run_poll_loop(self))

    # Mutations: route on followers
    async def set_config(self, config):
        if self._primary:
            return await self._primary_set_config(config)
        cmd_id = command_queue.enqueue_command("set_config", payload=config.model_dump())
        return await command_queue.wait_for_completion(cmd_id)

    async def register_demand(self, source, timeout_seconds=None, description=None):
        # DB upsert always; primary additionally fires immediate wake-up
        registered_at = datetime.now(timezone.utc)
        expires_at = registered_at + timedelta(seconds=timeout_seconds) if timeout_seconds else None
        upsert_demand(source, registered_at, expires_at, description)
        if self._primary and self._state != GpuPowerState.ACTIVE:
            await self._transition(GpuPowerState.ACTIVE, f"demand:{source}")
        return source
```

The monitor loop publishes runtime state every tick:

```python
async def _tick(self):
    self._refresh_demand_cache()  # from DB
    # ... existing logic ...
    if transitioned:
        update_runtime_state(
            current_state=self._state.value,
            last_transition=self._last_transition,
            last_reason=self._last_reason,
        )
    # SHM snapshot for followers
    self._write_status_shm()
```

`get_status()` for followers reads from DB (`load_runtime_state()` + `list_active_demands()`) plus SHM (display count, usage). For primary, behaviour is unchanged.

### Step 5 — Lifespan branching

```python
# lifespan.py — currently runs only on primary at line 425
await gpu_power_manager.start_gpu_power_manager(primary=IS_PRIMARY_WORKER)

# add to else (secondary) branch around line 462
if settings.gpu_power_management_enabled:
    try:
        await gpu_power_manager.start_gpu_power_manager(primary=False)
        logger.info("GPU power manager initialized (follower, secondary worker)")
    except Exception as e:
        logger.warning("GPU power manager init failed on secondary worker: %s", e)
```

`service_registry.py` already has `gpu_power_manager` in `PRIMARY_ONLY_SERVICES`. Apply the same `start_fn` closure pattern as for the CPU manager so a service-restart from the admin UI keeps the worker role.

### Step 6 — Routes (`api/routes/gpu_power.py`)

No changes expected. The routes call `manager.get_status()`, `manager.set_config()`, `manager.register_demand()`, etc. — all of which become primary/follower-aware in Step 4.

### Step 7 — Tests

- `tests/services/test_gpu_power_manager.py`: existing tests should still pass with an autouse fixture that creates the new tables in the test DB (analogous to the CPU branch). Add 3 new tests:
  - follower's `set_config` enqueues a command, primary applies it
  - follower's `get_status` returns the same `detected`/`vendor` as the primary's runtime-state row
  - DB-backed demand is visible across "workers" (two manager instances, primary + follower)
- `tests/services/test_gpu_command_queue.py`: 7 tests mirroring `test_power_command_queue.py` — enqueue, dispatch happy/sad path, unknown command, caller timeout, pending-row reaper

## Architecture decisions

1. **Duplicate `command_queue.py` rather than abstract**: the dispatcher dispatches manager-specific helper names. Type safety > 50 LOC of DRY.
2. **State transitions stay in the primary's tick** — never enqueued. Demand-driven wake-up to ACTIVE on a follower's `register_demand` is not surfaced as a command; instead the follower writes the demand to DB and the primary's next tick (max 5 s) picks it up. If sub-second wake-up is required, we add a "force_wake" command later — premature optimisation otherwise.
3. **`detected`/`vendor`/`has_write_permission` published via DB row** rather than SHM. Reason: these are sticky values (don't change unless backend is switched). DB persistence means a freshly started follower has them immediately, no SHM-warmup latency.

## Files Touched

| File | Action | LOC |
|---|---|---|
| `backend/app/models/gpu_power.py` | +3 classes | ~70 |
| `backend/app/models/__init__.py` | imports + `__all__` | 4 |
| `backend/alembic/versions/2026_05_03_gpu_power_multi_worker.py` | NEW, down_revision=`2026_05_02_power_multi_worker` | ~70 |
| `backend/app/services/power/gpu/runtime_state_store.py` | NEW | ~150 |
| `backend/app/services/power/gpu/command_queue.py` | NEW | ~180 |
| `backend/app/services/power/gpu/manager.py` | refactor: `start(primary=)`, `_primary_*` helpers, follower routing, runtime-state publishing, demand-cache refresh | ~150 diff |
| `backend/app/api/routes/gpu_power.py` | no changes |
| `backend/app/core/lifespan.py` | `primary=IS_PRIMARY_WORKER`, secondary branch | 8 |
| `backend/app/core/service_registry.py` | `start_fn` closure for `gpu_power_manager` | 8 |
| `backend/tests/services/test_gpu_command_queue.py` | NEW | ~150 |
| `backend/tests/services/test_gpu_power_manager.py` | autouse fixture + 3 new tests | ~120 |

**Total**: ~700 LOC code, ~270 LOC tests — analogous to the CPU branch, slightly smaller because no auto-scaling / preset / dynamic-mode complexity.

## Risks / Open Questions

1. **`set_config` latency**: command-queue round-trip on followers adds ~250 ms (half the poll interval) on average. Acceptable for a config-update endpoint.
2. **Demand wake-up latency**: up to 5 s on followers (next monitor tick). If a caller needs faster wake-up — e.g. a backup that wants the GPU at full clock immediately — they should call `register_demand` *before* starting the heavy work; the 5 s margin is the same wait the GPU itself needs to settle into ACTIVE state.
3. **`detected` flickering during boot**: the very first `_tick` on the primary writes `detected` to DB, but a follower handling a request before that tick fires will return `detected=false`. Mitigation: write `detected` synchronously inside `start()` before yielding the event loop (already in the Step 4 sketch).
4. **Migration ordering**: alembic head is `2026_05_02_power_multi_worker` (CPU branch). New revision uses that as `down_revision`.

## Verification

- [ ] All existing GPU power tests still pass (autouse fixture creates tables)
- [ ] New multi-worker tests pass
- [ ] Manual: 10×curl to `/api/gpu-power/status` returns identical responses (current state: 9× detected=false, 1× detected=true → expected: 10×detected=true)
- [ ] Manual: change a config value via UI, verify primary picks it up within ~1 s without restart
- [ ] Manual: register a demand from a route handler that lands on a follower (e.g. `@requires_gpu_power` if it exists, otherwise simulated via curl), verify primary transitions to ACTIVE within next tick

## Estimated Scope

~3–4 h implementation + ~1 h tests. Patch release. Branch `fix/gpu-power-manager-multi-worker` opens against `main`, label `release:patch`.
