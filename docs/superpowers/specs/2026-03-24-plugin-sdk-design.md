# Plugin SDK: Hooks, Service Registry & CLI

**Date:** 2026-03-24
**Status:** Approved
**Scope:** Backend only (`backend/app/plugins/`, `backend/tests/`)

## Overview

Three sequential features that complete the BaluHost plugin system:

1. **Feature 1 — Hook Completion:** Add 7 new hook specs and wire all 32 hooks into backend services
2. **Feature 2 — Service Registry:** Cross-plugin service discovery and communication
3. **Feature 3 — SDK CLI:** Plugin scaffolding, validation, and developer tooling

Each feature builds on the previous: Feature 1 provides hooks that Feature 3 uses as template examples. Feature 2 provides `get_services()` that Feature 3 exposes via `--with-service`.

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Hook wiring scope | All 32 hooks (25 existing + 7 new) | Existing hooks are defined but not wired anywhere in services |
| Telemetry throttle | Plugin-side `@throttle(seconds=N)` decorator | No framework intrusion, compatible with pluggy dispatch model |
| SDK CLI entry-point | `baluhost-sdk` in pyproject.toml + `python -m` fallback | Consistent with existing `baluhost-tui` pattern |
| Registry concurrency | `asyncio.Lock` per-process | Consistent with PluginManager/EventManager singleton pattern; cross-process not needed |
| Template engine | Pure f-strings | Templates are ~100-150 lines; no new dependency for internal tooling |
| Dependency validation | Existence check + direct cycle detection | No installed plugin uses dependencies yet; topological sort is over-engineering |

---

## Feature 1: Hook Completion & Wiring

### 1.1 New Hook Specs

Add to `BaluHostHookSpec` in `backend/app/plugins/hooks.py`, following existing style (docstring, typed args, section comments):

```python
# File Events (addition)
on_file_access_denied(path: str, user_id: int, reason: str)

# System Events (addition)
on_quota_exceeded(user_id: int, username: str, used_bytes: int, quota_bytes: int)
on_telemetry_snapshot(cpu_percent: float, ram_percent: float, disk_usage: dict, timestamp: str)

# Sync Events (new section)
on_sync_conflict_detected(path: str, device_id: str, local_mtime: float, remote_mtime: float)
on_sync_completed(device_id: str, files_synced: int, bytes_transferred: int, duration_seconds: float)

# Scheduler Events (new section)
on_scheduler_run_started(scheduler_name: str, run_id: str)
on_scheduler_run_failed(scheduler_name: str, run_id: str, error: str, duration_seconds: float)
```

### 1.2 Hook Wiring Map

All 32 hooks wired via `emit_hook()` from `app.plugins.emit`:

| Hook | Service File | Location |
|---|---|---|
| **File Events** | | |
| `on_file_uploaded` | `api/routes/files.py` | After successful upload |
| `on_file_deleted` | `api/routes/files.py` | After delete operation |
| `on_file_moved` | `api/routes/files.py` | After move/rename |
| `on_file_downloaded` | `api/routes/files.py` | After download response |
| `on_file_access_denied` | `api/routes/files.py` | In `_jail_path()` on rejection |
| **User Events** | | |
| `on_user_login` | `api/routes/auth.py` | After successful login |
| `on_user_logout` | `api/routes/auth.py` | After logout |
| `on_user_created` | `api/routes/auth.py` or `services/auth.py` | After user registration |
| `on_user_deleted` | `api/routes/users.py` | After user deletion |
| **Backup Events** | | |
| `on_backup_started` | `services/backup/` | Backup start |
| `on_backup_completed` | `services/backup/` | Backup end (success/fail) |
| **Share Events** | | |
| `on_share_created` | `api/routes/shares.py` | Share creation |
| `on_share_accessed` | `api/routes/shares.py` | Share access |
| **System Events** | | |
| `on_system_startup` | `main.py` lifespan | App start |
| `on_system_shutdown` | `main.py` lifespan | App shutdown |
| `on_storage_threshold` | `services/files/` or monitoring | Threshold check |
| `on_quota_exceeded` | `services/files/` | Upload quota check |
| `on_telemetry_snapshot` | `services/telemetry.py` | Telemetry interval |
| **RAID Events** | | |
| `on_raid_degraded` | `services/hardware/raid/` | Degraded detection |
| `on_raid_rebuild_started` | `services/hardware/raid/` | Rebuild start |
| `on_raid_rebuild_completed` | `services/hardware/raid/` | Rebuild end |
| **SMART Events** | | |
| `on_disk_health_warning` | `services/hardware/smart/` | Health warning |
| **Mobile/Device Events** | | |
| `on_device_registered` | `services/mobile.py` | Device registration |
| `on_device_removed` | `services/mobile.py` | Device removal |
| **Smart Device Events** | | |
| `on_smart_device_state_changed` | Smart Device Manager | State change |
| `on_smart_device_added` | Smart Device Manager | Device added |
| `on_smart_device_removed` | Smart Device Manager | Device removed |
| **VPN Events** | | |
| `on_vpn_client_created` | `services/vpn/` | Client created |
| `on_vpn_client_revoked` | `services/vpn/` | Client revoked |
| **Sync Events** | | |
| `on_sync_conflict_detected` | `services/sync/` | Conflict detection |
| `on_sync_completed` | `services/sync/` | Sync completed |
| **Scheduler Events** | | |
| `on_scheduler_run_started` | `services/scheduler/` | Job start |
| `on_scheduler_run_failed` | `services/scheduler/` | Job failure |

### 1.3 Wiring Rules

- Use `emit_hook()` from `app.plugins.emit` (fire-and-forget, catches exceptions)
- Place after the successful operation, not before
- Do not modify business logic — only add `emit_hook()` calls
- `on_file_access_denied` is the exception: fires on rejection in `_jail_path()`

### 1.4 Tests

File: `backend/tests/test_plugin_hooks_new.py`

- MockPlugin with `@hookimpl` for each of the 7 new hooks
- Register MockPlugin with pluggy PluginManager
- Each test emits the hook and asserts the mock was called with correct args
- Pattern matches existing `test_plugins.py:TestHookSystem`

---

## Feature 2: Service Registry

### 2.1 Module: `backend/app/plugins/registry.py`

```python
class ServiceNotFoundError(Exception):
    """Raised when requesting an unregistered service."""

class ServiceRegistry:
    _instance: Optional["ServiceRegistry"] = None

    def __init__(self):
        self._services: Dict[str, Any] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    async def register(self, name: str, service: Any) -> None
        # Validates namespace format: "{plugin_name}.{service_name}"
        # Regex: r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$"
        # Raises ValueError on invalid format or duplicate name

    async def deregister(self, name: str) -> None
        # Removes a single service; no-op if not found

    async def deregister_all(self, plugin_name: str) -> int
        # Removes all services with prefix "{plugin_name}."
        # Returns count of removed services

    def get(self, name: str) -> Any
        # Synchronous read (CPython GIL protects dict reads)
        # Raises ServiceNotFoundError if not found

    def list_services(self, plugin_name: Optional[str] = None) -> List[str]
        # Returns all service names, optionally filtered by plugin prefix

    @classmethod
    def get_instance(cls) -> "ServiceRegistry": ...

    @classmethod
    def reset_instance(cls) -> None: ...  # For tests

def get_service_registry() -> ServiceRegistry:
    return ServiceRegistry.get_instance()
```

### 2.2 Integration Points

**`PluginBase` (base.py)** — new optional method:
```python
def get_services(self) -> Dict[str, Any]:
    """Return services to register. Keys are service names (without plugin prefix)."""
    return {}
```

**`PluginManager.enable_plugin()`** — after `on_startup()`:
```python
services = plugin.get_services()
if services:
    registry = get_service_registry()
    for svc_name, svc_instance in services.items():
        await registry.register(f"{name}.{svc_name}", svc_instance)
```

**`PluginManager.disable_plugin()`** — before `on_shutdown()`:
```python
registry = get_service_registry()
await registry.deregister_all(name)
```

**`plugins/__init__.py`** — add exports:
- `ServiceRegistry`, `get_service_registry`, `ServiceNotFoundError`

### 2.3 Tests

File: `backend/tests/test_plugin_registry.py`

| Test | Description |
|---|---|
| `test_register_get_roundtrip` | Register, get, verify same instance |
| `test_namespace_validation_valid` | `"my_plugin.weather"` accepted |
| `test_namespace_validation_invalid` | `"no_dot"`, `""`, `"a.b.c"` raise ValueError |
| `test_get_unknown_raises` | `get("x.y")` raises ServiceNotFoundError |
| `test_deregister_single` | Register, deregister, get raises |
| `test_deregister_all_by_plugin` | Register 3 services, deregister_all removes only matching plugin |
| `test_auto_deregister_on_disable` | enable_plugin registers services, disable_plugin removes them |
| `test_list_services_all` | Lists all registered services |
| `test_list_services_filtered` | Lists only services for one plugin |
| `test_concurrent_access` | Multiple asyncio tasks register/read simultaneously |

---

## Feature 3: SDK CLI & Tooling

### 3.1 Package Structure

```
backend/app/plugins/sdk/
    __init__.py          # Package marker, re-exports
    __main__.py          # python -m app.plugins.sdk support
    cli.py               # Click CLI group
    scaffold.py          # Template generation (f-strings)
    validator.py         # Plugin contract validation
    throttle.py          # @throttle decorator for high-frequency hooks
```

### 3.2 CLI Commands

Entry-point in `pyproject.toml`:
```toml
baluhost-sdk = "app.plugins.sdk.cli:cli"
```

**`baluhost-sdk create <plugin_name>`**
```
Options:
  --category [monitoring|storage|network|security|general]  (default: general)
  --author TEXT                                              (default: "BaluHost Community")
  --with-router          Add example APIRouter
  --with-background-task Add example BackgroundTaskSpec
  --with-dashboard-panel Add DashboardPanelSpec + get_dashboard_data()
  --with-service         Add get_services() example
  --force                Overwrite existing plugin
```

Generates: `installed/{plugin_name}/__init__.py`

**`baluhost-sdk validate <plugin_name>`**
Loads plugin, runs validation checks, outputs structured report with exit code.

**`baluhost-sdk list`**
Shows all installed plugins with status (enabled/disabled), version, author.

### 3.3 Scaffold Template Design

Generated `__init__.py` structure:

1. Module docstring with plugin description
2. Imports (PluginBase, PluginMetadata, hookimpl, conditional imports per flag)
3. Plugin class with `metadata` property (filled from CLI args)
4. `on_startup()` / `on_shutdown()` stubs
5. Conditional blocks per `--with-*` flag:
   - `--with-router`: `get_router()` with example GET endpoint
   - `--with-background-task`: `get_background_tasks()` with example periodic task
   - `--with-dashboard-panel`: `get_dashboard_panel()` + `get_dashboard_data()`
   - `--with-service`: `get_services()` with example service object
6. Hook example matching `--category`:
   - `monitoring` → `on_telemetry_snapshot` with `@throttle(30)` example
   - `storage` → `on_file_uploaded`
   - `network` → `on_vpn_client_created`
   - `security` → `on_user_login` + `on_file_access_denied`
   - `general` → `on_system_startup`
7. Inline comments: `# Step N: ...` with "why" explanations

**Idempotency:** If `installed/{plugin_name}/` exists → abort with warning unless `--force`.

### 3.4 Validator Checks

1. Metadata fields complete and non-empty (name, version, author, description)
2. `plugin.metadata.name == directory_name`
3. All `required_permissions` exist in `PluginPermission` enum
4. Dependencies: each declared dependency exists as installed plugin
5. Cycle detection: direct cycles (A depends on B, B depends on A)
6. SmartDevicePlugin: call existing `validate_capability_contracts()`

Output format:
```
Plugin: my_plugin v1.0.0
  [pass]  Metadata complete
  [pass]  Name matches directory
  [warn]  Permission "file:write" is marked as dangerous
  [fail]  Permission "foo:bar" does not exist
  [pass]  No circular dependencies
```

Exit code: 0 if no failures, 1 if any failure.

### 3.5 Throttle Decorator (`throttle.py`)

```python
import time
from functools import wraps

def throttle(seconds: float):
    """Skip hook calls within the interval. Plugin-side, pluggy-compatible."""
    def decorator(func):
        last_called = 0.0
        @wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal last_called
            now = time.monotonic()
            if now - last_called < seconds:
                return None
            last_called = now
            return func(*args, **kwargs)
        return wrapper
    return decorator
```

- Synchronous (pluggy hooks are sync)
- Per-instance state via closure
- `time.monotonic()` for clock-skew safety
- Returns `None` on skip (pluggy collects results as list, `None` is harmless)

### 3.6 Tests

File: `backend/tests/test_plugin_sdk.py`

| Test | Description |
|---|---|
| `test_create_generates_valid_python` | `ast.parse()` on output, no SyntaxError |
| `test_create_with_router_flag` | Output contains `get_router`, `APIRouter` |
| `test_create_with_background_task` | Output contains `get_background_tasks`, `BackgroundTaskSpec` |
| `test_create_with_dashboard_panel` | Output contains `get_dashboard_panel`, `DashboardPanelSpec` |
| `test_create_with_service` | Output contains `get_services` |
| `test_create_all_flags_combined` | All flags at once, valid Python |
| `test_create_category_hook_examples` | Each category generates matching hook example |
| `test_create_existing_aborts` | Without `--force` → SystemExit |
| `test_create_existing_force` | With `--force` → overwrites |
| `test_validate_valid_plugin` | Valid plugin → exit 0 |
| `test_validate_missing_metadata` | Missing fields → failure |
| `test_validate_unknown_permission` | Unknown permission → failure |
| `test_validate_missing_dependency` | Non-existent dependency → failure |
| `test_validate_circular_dependency` | A-B cycle → failure |
| `test_list_shows_plugins` | Lists installed plugins with status |
| `test_throttle_skips_within_interval` | Calls within interval are skipped |
| `test_throttle_allows_after_interval` | Calls after interval execute |

---

## Files Changed Summary

### Feature 1
- **Modified:** `backend/app/plugins/hooks.py` (7 new hook specs)
- **Modified:** ~15 service/route files (emit_hook calls)
- **New:** `backend/tests/test_plugin_hooks_new.py`

### Feature 2
- **New:** `backend/app/plugins/registry.py`
- **Modified:** `backend/app/plugins/base.py` (add `get_services()`)
- **Modified:** `backend/app/plugins/manager.py` (register/deregister in enable/disable)
- **Modified:** `backend/app/plugins/__init__.py` (new exports)
- **New:** `backend/tests/test_plugin_registry.py`

### Feature 3
- **New:** `backend/app/plugins/sdk/__init__.py`
- **New:** `backend/app/plugins/sdk/__main__.py`
- **New:** `backend/app/plugins/sdk/cli.py`
- **New:** `backend/app/plugins/sdk/scaffold.py`
- **New:** `backend/app/plugins/sdk/validator.py`
- **New:** `backend/app/plugins/sdk/throttle.py`
- **Modified:** `backend/pyproject.toml` (add entry-point)
- **New:** `backend/tests/test_plugin_sdk.py`
