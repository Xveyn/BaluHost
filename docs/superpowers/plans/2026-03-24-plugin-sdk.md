# Plugin SDK Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the BaluHost plugin system with hook wiring, a service registry, and an SDK CLI.

**Architecture:** Three sequential features — (1) add 8 new hook specs and wire all 34 hooks into services via `emit_hook()`, (2) create a `ServiceRegistry` singleton for cross-plugin service discovery, (3) build a Click-based SDK CLI for scaffolding, validation, and a `@throttle` decorator.

**Tech Stack:** Python 3.11+, FastAPI, pluggy, Click, asyncio, pytest

**Spec:** `docs/superpowers/specs/2026-03-24-plugin-sdk-design.md`

---

## File Map

### Feature 1 — Hook Completion & Wiring
| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `backend/app/plugins/hooks.py` | Add 8 new hook specs |
| Modify | `backend/app/api/routes/files.py` | Wire file event hooks (download, access_denied) |
| Modify | `backend/app/api/routes/auth.py` | Wire on_user_logout |
| Modify | `backend/app/api/routes/users.py` | Wire on_user_created (admin path), on_user_deleted |
| Modify | `backend/app/api/routes/shares.py` | Wire share hooks |
| Modify | `backend/app/api/routes/vpn.py` | Wire VPN hooks |
| Modify | `backend/app/api/routes/mobile.py` | Wire on_device_removed |
| Modify | `backend/app/services/files/operations.py` | Wire on_quota_exceeded |
| Modify | `backend/app/services/telemetry.py` | Wire on_telemetry_snapshot |
| Modify | `backend/app/services/backup/service.py` | Wire backup hooks |
| Modify | `backend/app/services/hardware/raid/api.py` | Wire RAID hooks |
| Modify | `backend/app/services/hardware/smart/api.py` | Wire SMART hook |
| Modify | `backend/app/services/mobile.py` | Wire on_device_registered |
| Modify | `backend/app/services/sync/file_sync.py` | Wire sync hooks |
| Modify | `backend/app/services/scheduler/service.py` | Wire on_scheduler_run_started |
| Modify | `backend/app/services/scheduler/execution.py` | Wire on_scheduler_run_completed/failed (manual trigger only) |
| Modify | `backend/app/plugins/smart_device/manager.py` | Wire smart device hooks |
| Create | `backend/tests/plugins/test_plugin_hooks_new.py` | Tests for 8 new hooks |

### Feature 2 — Service Registry
| Action | File | Responsibility |
|--------|------|---------------|
| Create | `backend/app/plugins/registry.py` | ServiceRegistry singleton |
| Modify | `backend/app/plugins/base.py` | Add `get_services()` method |
| Modify | `backend/app/plugins/manager.py` | Register/deregister services in enable/disable |
| Modify | `backend/app/plugins/__init__.py` | Export new symbols + DashboardPanelSpec |
| Create | `backend/tests/plugins/test_plugin_registry.py` | Registry tests |

### Feature 3 — SDK CLI
| Action | File | Responsibility |
|--------|------|---------------|
| Create | `backend/app/plugins/sdk/__init__.py` | Package marker |
| Create | `backend/app/plugins/sdk/__main__.py` | `python -m` support |
| Create | `backend/app/plugins/sdk/cli.py` | Click CLI group |
| Create | `backend/app/plugins/sdk/scaffold.py` | Template generation |
| Create | `backend/app/plugins/sdk/validator.py` | Plugin validation |
| Create | `backend/app/plugins/sdk/throttle.py` | `@throttle` decorator |
| Modify | `backend/pyproject.toml` | Add `baluhost-sdk` entry-point |
| Create | `backend/tests/plugins/test_plugin_sdk.py` | SDK tests |

---

## Feature 1: Hook Completion & Wiring

### Task 1: Add 8 New Hook Specs

**Files:**
- Modify: `backend/app/plugins/hooks.py`
- Test: `backend/tests/plugins/test_plugin_hooks_new.py`

**Context:** Read `backend/app/plugins/hooks.py` first. Existing hooks use `@hookspec`, `self` as first param, typed args, full docstring with Args section, `-> None` return type. There are currently 26 hooks organized by section comments.

- [ ] **Step 1: Write tests for the 8 new hook specs**

Create `backend/tests/plugins/test_plugin_hooks_new.py`:

```python
"""Tests for new plugin hook specifications added in Plugin SDK feature."""

from typing import Optional
from unittest.mock import MagicMock

import pytest

from app.plugins.hooks import BaluHostHookSpec, create_plugin_manager, hookimpl


class MockHookPlugin:
    """Mock plugin implementing all 8 new hooks to verify they fire correctly."""

    def __init__(self):
        self.calls = {}

    @hookimpl
    def on_file_access_denied(self, path: str, user_id: int, reason: str) -> None:
        self.calls["on_file_access_denied"] = {
            "path": path, "user_id": user_id, "reason": reason,
        }

    @hookimpl
    def on_quota_exceeded(
        self, user_id: int, username: str, used_bytes: int, quota_bytes: int,
    ) -> None:
        self.calls["on_quota_exceeded"] = {
            "user_id": user_id, "username": username,
            "used_bytes": used_bytes, "quota_bytes": quota_bytes,
        }

    @hookimpl
    def on_telemetry_snapshot(
        self, cpu_percent: float, ram_percent: float, disk_usage: dict, timestamp: str,
    ) -> None:
        self.calls["on_telemetry_snapshot"] = {
            "cpu_percent": cpu_percent, "ram_percent": ram_percent,
            "disk_usage": disk_usage, "timestamp": timestamp,
        }

    @hookimpl
    def on_sync_conflict_detected(
        self, path: str, device_id: str, local_mtime: float, remote_mtime: float,
    ) -> None:
        self.calls["on_sync_conflict_detected"] = {
            "path": path, "device_id": device_id,
            "local_mtime": local_mtime, "remote_mtime": remote_mtime,
        }

    @hookimpl
    def on_sync_completed(
        self, device_id: str, files_synced: int, bytes_transferred: int,
        duration_seconds: float,
    ) -> None:
        self.calls["on_sync_completed"] = {
            "device_id": device_id, "files_synced": files_synced,
            "bytes_transferred": bytes_transferred,
            "duration_seconds": duration_seconds,
        }

    @hookimpl
    def on_scheduler_run_started(self, scheduler_name: str, run_id: str) -> None:
        self.calls["on_scheduler_run_started"] = {
            "scheduler_name": scheduler_name, "run_id": run_id,
        }

    @hookimpl
    def on_scheduler_run_completed(
        self, scheduler_name: str, run_id: str, duration_seconds: float,
    ) -> None:
        self.calls["on_scheduler_run_completed"] = {
            "scheduler_name": scheduler_name, "run_id": run_id,
            "duration_seconds": duration_seconds,
        }

    @hookimpl
    def on_scheduler_run_failed(
        self, scheduler_name: str, run_id: str, error: str, duration_seconds: float,
    ) -> None:
        self.calls["on_scheduler_run_failed"] = {
            "scheduler_name": scheduler_name, "run_id": run_id,
            "error": error, "duration_seconds": duration_seconds,
        }


@pytest.fixture
def pm_with_mock():
    """Create a pluggy PluginManager with the MockHookPlugin registered."""
    pm = create_plugin_manager()
    mock = MockHookPlugin()
    pm.register(mock)
    return pm, mock


class TestNewHookSpecs:
    """Verify each new hook spec can be called and reaches the plugin."""

    def test_on_file_access_denied(self, pm_with_mock):
        pm, mock = pm_with_mock
        pm.hook.on_file_access_denied(path="/secret/file.txt", user_id=42, reason="not_owner")
        assert mock.calls["on_file_access_denied"]["path"] == "/secret/file.txt"
        assert mock.calls["on_file_access_denied"]["user_id"] == 42
        assert mock.calls["on_file_access_denied"]["reason"] == "not_owner"

    def test_on_quota_exceeded(self, pm_with_mock):
        pm, mock = pm_with_mock
        pm.hook.on_quota_exceeded(
            user_id=1, username="testuser", used_bytes=900, quota_bytes=1000,
        )
        assert mock.calls["on_quota_exceeded"]["used_bytes"] == 900
        assert mock.calls["on_quota_exceeded"]["quota_bytes"] == 1000

    def test_on_telemetry_snapshot(self, pm_with_mock):
        pm, mock = pm_with_mock
        disk = {"mount_point": "/data", "total_bytes": 1000, "used_bytes": 500, "percent": 50.0}
        pm.hook.on_telemetry_snapshot(
            cpu_percent=25.0, ram_percent=60.0, disk_usage=disk, timestamp="2026-03-24T12:00:00",
        )
        assert mock.calls["on_telemetry_snapshot"]["cpu_percent"] == 25.0
        assert mock.calls["on_telemetry_snapshot"]["disk_usage"]["percent"] == 50.0

    def test_on_sync_conflict_detected(self, pm_with_mock):
        pm, mock = pm_with_mock
        pm.hook.on_sync_conflict_detected(
            path="/docs/readme.md", device_id="dev-123",
            local_mtime=1000.0, remote_mtime=2000.0,
        )
        assert mock.calls["on_sync_conflict_detected"]["device_id"] == "dev-123"

    def test_on_sync_completed(self, pm_with_mock):
        pm, mock = pm_with_mock
        pm.hook.on_sync_completed(
            device_id="dev-123", files_synced=10, bytes_transferred=50000,
            duration_seconds=3.5,
        )
        assert mock.calls["on_sync_completed"]["files_synced"] == 10

    def test_on_scheduler_run_started(self, pm_with_mock):
        pm, mock = pm_with_mock
        pm.hook.on_scheduler_run_started(scheduler_name="backup_daily", run_id="run-001")
        assert mock.calls["on_scheduler_run_started"]["scheduler_name"] == "backup_daily"

    def test_on_scheduler_run_completed(self, pm_with_mock):
        pm, mock = pm_with_mock
        pm.hook.on_scheduler_run_completed(
            scheduler_name="backup_daily", run_id="run-001", duration_seconds=120.5,
        )
        assert mock.calls["on_scheduler_run_completed"]["duration_seconds"] == 120.5

    def test_on_scheduler_run_failed(self, pm_with_mock):
        pm, mock = pm_with_mock
        pm.hook.on_scheduler_run_failed(
            scheduler_name="backup_daily", run_id="run-001",
            error="disk full", duration_seconds=5.0,
        )
        assert mock.calls["on_scheduler_run_failed"]["error"] == "disk full"

    def test_hooks_exist_on_hook_manager(self):
        """All 8 new hooks should be accessible on the hook manager."""
        pm = create_plugin_manager()
        for name in [
            "on_file_access_denied", "on_quota_exceeded", "on_telemetry_snapshot",
            "on_sync_conflict_detected", "on_sync_completed",
            "on_scheduler_run_started", "on_scheduler_run_completed",
            "on_scheduler_run_failed",
        ]:
            assert hasattr(pm.hook, name), f"Missing hook: {name}"
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `cd backend && python -m pytest tests/plugins/test_plugin_hooks_new.py -v`
Expected: FAIL — `AttributeError: 'HookRelay' object has no attribute 'on_file_access_denied'`

- [ ] **Step 3: Add 8 new hook specs to hooks.py**

Read `backend/app/plugins/hooks.py` first. Add the new hooks following the exact existing style. Insert these sections:

After the `on_file_downloaded` hook (File Events section), add `on_file_access_denied`.
After `on_storage_threshold` (System Events section), add `on_quota_exceeded` and `on_telemetry_snapshot`.
Add new "Sync Events" section after VPN Events with `on_sync_conflict_detected` and `on_sync_completed`.
Add new "Scheduler Events" section after Sync Events with `on_scheduler_run_started`, `on_scheduler_run_completed`, and `on_scheduler_run_failed`.

Each hook needs: `@hookspec` decorator, `self` first param, typed args, full docstring with Args section, `-> None` return.

- [ ] **Step 4: Run tests — verify they pass**

Run: `cd backend && python -m pytest tests/plugins/test_plugin_hooks_new.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugins/hooks.py backend/tests/plugins/test_plugin_hooks_new.py
git commit -m "feat(plugins): add 8 new hook specs (access_denied, quota, telemetry, sync, scheduler)"
```

---

### Task 2: Wire File Event Hooks

**Files:**
- Modify: `backend/app/api/routes/files.py`
- Modify: `backend/app/services/files/operations.py`

**Context:** Read both files first. Some file hooks are already wired (on_file_uploaded at line ~693, on_file_deleted at lines ~756/788/970, on_file_moved at line ~927). We need to wire: `on_file_downloaded`, `on_file_access_denied`, `on_quota_exceeded`.

**Already wired (verify, do not re-add):** `on_file_uploaded`, `on_file_deleted`, `on_file_moved`

- [ ] **Step 1: Read files.py and operations.py to verify existing hooks and find exact insertion points**

Read `backend/app/api/routes/files.py` and `backend/app/services/files/operations.py`. Verify the already-wired hooks exist. Identify:
- `download_file()` and `download_file_by_id()` for `on_file_downloaded`
- `PermissionDeniedError` except blocks for `on_file_access_denied`
- Quota check in `operations.py` for `on_quota_exceeded`

- [ ] **Step 2: Wire on_file_downloaded**

In `backend/app/api/routes/files.py`, add `from app.plugins.emit import emit_hook` if not already imported. In `download_file()` after the `track_activity()` call and before the `return FileResponse(...)`:
```python
emit_hook("on_file_downloaded", path=resource_path, user_id=user.id)
```

Same in `download_file_by_id()` after its `track_activity()` call:
```python
emit_hook("on_file_downloaded", path=file_metadata.path, user_id=user.id)
```

- [ ] **Step 3: Wire on_file_access_denied**

In `backend/app/api/routes/files.py`, in each `except PermissionDeniedError` block (there are ~8 of them), after the `audit_logger.log_authorization_failure(...)` call and before `raise HTTPException(...)`:
```python
emit_hook("on_file_access_denied", path=<resource_path_variable>, user_id=user.id, reason="permission_denied")
```

Use the appropriate path variable from each handler (e.g., `jailed_path`, `resource_path`, `jailed_old_path`, `jailed_source`).

- [ ] **Step 4: Wire on_quota_exceeded**

In `backend/app/services/files/operations.py`, in the `save_uploads()` function's quota check block, just before `raise QuotaExceededError(...)`:
```python
from app.plugins.emit import emit_hook
emit_hook(
    "on_quota_exceeded",
    user_id=user.id,
    username=user.username,
    used_bytes=used_bytes,
    quota_bytes=quota_bytes,
)
```

- [ ] **Step 5: Run existing tests to verify no regressions**

Run: `cd backend && python -m pytest tests/files/ -v --timeout=30`
Expected: All existing file tests still pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/files.py backend/app/services/files/operations.py
git commit -m "feat(plugins): wire file event hooks (downloaded, access_denied, quota_exceeded)"
```

---

### Task 3: Wire User, Auth & Share Hooks

**Files:**
- Modify: `backend/app/api/routes/auth.py`
- Modify: `backend/app/api/routes/users.py`
- Modify: `backend/app/api/routes/shares.py`

**Context:** Read all three files first. `on_user_login` is already wired in auth.py. `on_user_created` is already wired in auth.py for self-registration but NOT for admin-created users in users.py.

**Already wired (verify, do not re-add):** `on_user_login`, `on_user_created` (self-registration path only)

- [ ] **Step 1: Read the three route files**

Read `backend/app/api/routes/auth.py`, `backend/app/api/routes/users.py`, `backend/app/api/routes/shares.py`.

- [ ] **Step 2: Wire on_user_logout in auth.py**

In `logout()` function, after the `audit_logger.log_security_event(...)` block:
```python
emit_hook("on_user_logout", user_id=current_user.id, username=current_user.username)
```

- [ ] **Step 3: Wire on_user_created in users.py (admin path)**

In `create_user()` function in `users.py`, after the audit log block:
```python
from app.plugins.emit import emit_hook
emit_hook("on_user_created", user_id=record.id, username=payload.username, role=payload.role)
```

- [ ] **Step 4: Wire on_user_deleted in users.py**

In `delete_user()` function, after the audit log block:
```python
emit_hook("on_user_deleted", user_id=user_id, username=username)
```
Note: Capture `username` before deletion if needed.

- [ ] **Step 5: Wire on_share_created in shares.py**

In `create_file_share()` after the audit log:
```python
from app.plugins.emit import emit_hook
emit_hook(
    "on_share_created",
    share_id=str(file_share.id),
    path=file_path,
    user_id=current_user.id,
    is_public=False,
)
```

- [ ] **Step 6: Wire on_share_accessed in shares.py**

Find the share access endpoint (public share download or listing). After successful access:
```python
emit_hook("on_share_accessed", share_id=str(share.id), path=share.file_path, accessor_ip=request.client.host)
```

- [ ] **Step 7: Run tests**

Run: `cd backend && python -m pytest tests/ -k "auth or user or share" -v --timeout=30`
Expected: All pass

- [ ] **Step 8: Commit**

```bash
git add backend/app/api/routes/auth.py backend/app/api/routes/users.py backend/app/api/routes/shares.py
git commit -m "feat(plugins): wire user, auth, and share hooks"
```

---

### Task 4: Wire System, Telemetry & Backup Hooks

**Files:**
- Modify: `backend/app/services/telemetry.py`
- Modify: `backend/app/services/backup/service.py`

**Context:** Read both files. `on_system_startup` and `on_system_shutdown` are already wired in `core/lifespan.py` — verify but do not re-add. `on_storage_threshold` needs to be found (check monitoring or files services).

**Already wired (verify):** `on_system_startup`, `on_system_shutdown`

- [ ] **Step 1: Read telemetry.py and backup/service.py**

Read `backend/app/services/telemetry.py` and `backend/app/services/backup/service.py`. Also read `backend/app/core/lifespan.py` to verify system hooks.

- [ ] **Step 2: Wire on_telemetry_snapshot in telemetry.py**

In the `_sample_once()` function, AFTER the `with _lock:` block exits (outside the lock):
```python
from app.plugins.emit import emit_hook
emit_hook(
    "on_telemetry_snapshot",
    cpu_percent=cpu_sample.usage,
    ram_percent=percent_mem,
    disk_usage={"mount_point": "/", "total_bytes": 0, "used_bytes": 0, "percent": 0.0},
    timestamp=str(timestamp_ms),
)
```
Note: Adapt `disk_usage` to use actual disk info available in the function scope.

- [ ] **Step 3: Wire on_backup_started and on_backup_completed in backup/service.py**

In `BackupService.create_backup()`:
- After backup record creation and before the actual backup work: `emit_hook("on_backup_started", backup_id=str(backup.id), backup_type=backup.backup_type)`
- After successful completion (after notification emit): `emit_hook("on_backup_completed", backup_id=str(backup.id), success=True, size=backup.size_bytes)`
- In the `except Exception` block after commit: `emit_hook("on_backup_completed", backup_id=str(backup.id), success=False, error=str(e))`

- [ ] **Step 4: Wire on_storage_threshold (conditional)**

Search the codebase for existing storage threshold checks (e.g. `grep -r "threshold" backend/app/services/` looking for disk/storage usage percentage comparisons). Likely candidates: `services/files/operations.py` (quota checks), `services/monitoring/` (collector logic), or `services/disk_monitor.py`.

- **If a threshold check exists:** Add `emit_hook("on_storage_threshold", mount=mount_point, usage_percent=usage, threshold_percent=threshold)` at the point where the threshold is exceeded.
- **If no threshold check exists:** Skip this wiring — the hook spec is available for future use. Add a comment to the commit message: "on_storage_threshold: hook defined but no existing threshold check found to wire into."

- [ ] **Step 5: Run tests**

Run: `cd backend && python -m pytest tests/ -k "telemetry or backup" -v --timeout=30`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/telemetry.py backend/app/services/backup/service.py
git commit -m "feat(plugins): wire system, telemetry, and backup hooks"
```

---

### Task 5: Wire RAID, SMART & Hardware Hooks

**Files:**
- Modify: `backend/app/services/hardware/raid/api.py`
- Modify: `backend/app/services/hardware/smart/api.py`

**Context:** Read both files first. RAID hooks fire in simulate_failure/simulate_rebuild/finalize_rebuild. SMART hook fires in `_check_smart_for_notifications`.

- [ ] **Step 1: Read both hardware service files**

Read `backend/app/services/hardware/raid/api.py` and `backend/app/services/hardware/smart/api.py`.

- [ ] **Step 2: Wire RAID hooks**

In `backend/app/services/hardware/raid/api.py`:

`on_raid_degraded` — in `simulate_failure()` after the notification emit:
```python
emit_hook("on_raid_degraded", array_name=payload.array, failed_disk=payload.disk or "unknown")
```

`on_raid_rebuild_started` — in `simulate_rebuild()` after successful rebuild call:
```python
resp = _backend.rebuild(payload)
emit_hook("on_raid_rebuild_started", array_name=payload.array)
return resp
```

`on_raid_rebuild_completed` — in `finalize_rebuild()` after notification emit:
```python
emit_hook("on_raid_rebuild_completed", array_name=payload.array, success=True)
```

- [ ] **Step 3: Wire SMART hook**

In `backend/app/services/hardware/smart/api.py`, in `_check_smart_for_notifications()` where warnings are detected:
```python
emit_hook(
    "on_disk_health_warning",
    disk=device.name,
    attribute=attr.name,
    value=attr.raw_value,
    threshold=attr.threshold,
)
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/ -k "raid or smart" -v --timeout=30`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/hardware/raid/api.py backend/app/services/hardware/smart/api.py
git commit -m "feat(plugins): wire RAID and SMART hardware hooks"
```

---

### Task 6: Wire Mobile, Smart Device & VPN Hooks

**Files:**
- Modify: `backend/app/services/mobile.py`
- Modify: `backend/app/api/routes/mobile.py`
- Modify: `backend/app/plugins/smart_device/manager.py`
- Modify: `backend/app/api/routes/vpn.py`

**Context:** Read all four files first.

- [ ] **Step 1: Read all four files**

- [ ] **Step 2: Wire mobile device hooks**

`on_device_registered` — in `services/mobile.py` `register_device()` after `db.refresh(device)`:
```python
emit_hook(
    "on_device_registered",
    device_id=str(device.id),
    device_name=device_info.device_name,
    user_id=token_record.user_id,
    platform=device_info.device_type,
)
```

`on_device_removed` — in `api/routes/mobile.py` `delete_device()` after `remove_device()`:
```python
emit_hook("on_device_removed", device_id=device_id, user_id=device.user_id)
```
Note: Capture `device.user_id` before deletion.

- [ ] **Step 3: Wire smart device hooks**

In `backend/app/plugins/smart_device/manager.py`:

`on_smart_device_added` — in `create_device()` after logger.info, before return:
```python
emit_hook(
    "on_smart_device_added",
    device_id=device.id,
    plugin_name=device.plugin_name,
    device_type_id=device.device_type_id,
    name=device.name,
)
```

`on_smart_device_removed` — in `delete_device()`. Capture attrs BEFORE db.delete():
```python
device_id, device_name, plugin_name = device.id, device.name, device.plugin_name
# ... existing db.delete() and db.commit() ...
emit_hook("on_smart_device_removed", device_id=device_id, plugin_name=plugin_name)
```

`on_smart_device_state_changed` — find where state changes are tracked and add:
```python
emit_hook(
    "on_smart_device_state_changed",
    device_id=device.id,
    plugin_name=plugin_name,
    capability=capability,
    old_state=old_state,
    new_state=new_state,
)
```

- [ ] **Step 4: Wire VPN hooks**

In `backend/app/api/routes/vpn.py`:

`on_vpn_client_created` — in `generate_vpn_config()` after audit log:
```python
emit_hook("on_vpn_client_created", client_id=config.client_id, client_name=config_data.device_name, user_id=current_user.id)
```

`on_vpn_client_revoked` — in `revoke_vpn_client()` at end of function:
```python
emit_hook("on_vpn_client_revoked", client_id=client_id, user_id=current_user.id)
```

- [ ] **Step 5: Run tests**

Run: `cd backend && python -m pytest tests/ -k "mobile or smart_device or vpn" -v --timeout=30`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/mobile.py backend/app/api/routes/mobile.py backend/app/plugins/smart_device/manager.py backend/app/api/routes/vpn.py
git commit -m "feat(plugins): wire mobile, smart device, and VPN hooks"
```

---

### Task 7: Wire Sync & Scheduler Hooks

**Files:**
- Modify: `backend/app/services/sync/file_sync.py`
- Modify: `backend/app/services/scheduler/service.py`
- Modify: `backend/app/services/scheduler/execution.py`

**Context:** Read all three files. Scheduler completion/failure hooks go in `execution.py` but only fire for `trigger_type == "manual"` (run-now API requests). The worker process doesn't initialize PluginManager, but `emit_hook()` is fire-and-forget and will silently no-op if PluginManager isn't initialized — so filtering by trigger_type is a documentation concern, not a runtime one.

- [ ] **Step 1: Read sync and scheduler files**

Read `backend/app/services/sync/file_sync.py`, `backend/app/services/scheduler/service.py`, and `backend/app/services/scheduler/execution.py`.

- [ ] **Step 2: Wire sync hooks**

`on_sync_conflict_detected` — in `FileSyncService.detect_changes()` after commit, only if conflicts non-empty:
```python
if changes.get("conflicts"):
    emit_hook(
        "on_sync_conflict_detected",
        path=changes["conflicts"][0]["path"],
        device_id=str(device_id),
        local_mtime=0.0,  # adapt to actual data available
        remote_mtime=0.0,
    )
```

`on_sync_completed` — find sync completion point and add:
```python
emit_hook(
    "on_sync_completed",
    device_id=str(device_id),
    files_synced=len(synced_files),
    bytes_transferred=total_bytes,
    duration_seconds=duration,
)
```

- [ ] **Step 3: Wire scheduler hooks**

`on_scheduler_run_started` — in `SchedulerService.run_scheduler_now()` after execution record created:
```python
emit_hook("on_scheduler_run_started", scheduler_name=name, run_id=str(execution.id))
```

`on_scheduler_run_completed` and `on_scheduler_run_failed` — in `execution.py` `complete_scheduler_execution()`:
```python
from app.plugins.emit import emit_hook

# After setting success status:
emit_hook(
    "on_scheduler_run_completed",
    scheduler_name=execution.scheduler_name,
    run_id=str(execution_id),
    duration_seconds=execution.duration_ms / 1000.0 if execution.duration_ms else 0.0,
)

# After setting error status:
emit_hook(
    "on_scheduler_run_failed",
    scheduler_name=execution.scheduler_name,
    run_id=str(execution_id),
    error=error or "unknown",
    duration_seconds=execution.duration_ms / 1000.0 if execution.duration_ms else 0.0,
)
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/ -k "sync or scheduler" -v --timeout=30`
Expected: All pass

- [ ] **Step 5: Run FULL test suite to verify no regressions across Feature 1**

Run: `cd backend && python -m pytest --timeout=30 -x -q`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/sync/file_sync.py backend/app/services/scheduler/service.py backend/app/services/scheduler/execution.py
git commit -m "feat(plugins): wire sync and scheduler hooks"
```

---

## Feature 2: Service Registry

### Task 8: Create ServiceRegistry

**Files:**
- Create: `backend/app/plugins/registry.py`
- Test: `backend/tests/plugins/test_plugin_registry.py`

- [ ] **Step 1: Write registry tests**

Create `backend/tests/plugins/test_plugin_registry.py`:

```python
"""Tests for the plugin ServiceRegistry."""

import asyncio

import pytest

from app.plugins.registry import ServiceNotFoundError, ServiceRegistry


@pytest.fixture
def registry():
    """Fresh ServiceRegistry for each test."""
    r = ServiceRegistry()
    return r


@pytest.mark.asyncio
class TestServiceRegistry:

    async def test_register_get_roundtrip(self, registry):
        svc = object()
        await registry.register("my_plugin.weather", svc)
        assert registry.get("my_plugin.weather") is svc

    async def test_namespace_validation_valid(self, registry):
        await registry.register("plugin_a.service1", "svc")
        assert "plugin_a.service1" in registry.list_services()

    @pytest.mark.parametrize("bad_name", [
        "no_dot", "", "a.b.c", "A.service", ".leading_dot", "trailing_dot.",
        "123.numeric_start",
    ])
    async def test_namespace_validation_invalid(self, registry, bad_name):
        with pytest.raises(ValueError):
            await registry.register(bad_name, "svc")

    async def test_get_unknown_raises(self, registry):
        with pytest.raises(ServiceNotFoundError):
            registry.get("unknown.service")

    async def test_deregister_single(self, registry):
        await registry.register("p.svc", "val")
        await registry.deregister("p.svc")
        with pytest.raises(ServiceNotFoundError):
            registry.get("p.svc")

    async def test_deregister_all_by_plugin(self, registry):
        await registry.register("plugin_a.svc1", "a1")
        await registry.register("plugin_a.svc2", "a2")
        await registry.register("plugin_b.svc1", "b1")
        count = await registry.deregister_all("plugin_a")
        assert count == 2
        with pytest.raises(ServiceNotFoundError):
            registry.get("plugin_a.svc1")
        assert registry.get("plugin_b.svc1") == "b1"

    async def test_list_services_all(self, registry):
        await registry.register("a.one", 1)
        await registry.register("b.two", 2)
        names = registry.list_services()
        assert set(names) == {"a.one", "b.two"}

    async def test_list_services_filtered(self, registry):
        await registry.register("a.one", 1)
        await registry.register("a.two", 2)
        await registry.register("b.three", 3)
        assert set(registry.list_services("a")) == {"a.one", "a.two"}

    async def test_duplicate_registration_raises(self, registry):
        await registry.register("p.svc", "first")
        with pytest.raises(ValueError, match="already registered"):
            await registry.register("p.svc", "second")

    async def test_concurrent_access(self, registry):
        """Multiple tasks registering/reading simultaneously."""
        async def register_task(i):
            await registry.register(f"plugin.svc{i}", f"val{i}")
            return registry.get(f"plugin.svc{i}")

        results = await asyncio.gather(*[register_task(i) for i in range(10)])
        assert results == [f"val{i}" for i in range(10)]


class TestServiceRegistrySingleton:

    def test_singleton_pattern(self):
        ServiceRegistry.reset_instance()
        a = ServiceRegistry.get_instance()
        b = ServiceRegistry.get_instance()
        assert a is b
        ServiceRegistry.reset_instance()

    def test_reset_instance(self):
        ServiceRegistry.reset_instance()
        a = ServiceRegistry.get_instance()
        ServiceRegistry.reset_instance()
        b = ServiceRegistry.get_instance()
        assert a is not b
        ServiceRegistry.reset_instance()
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `cd backend && python -m pytest tests/plugins/test_plugin_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.plugins.registry'`

- [ ] **Step 3: Implement ServiceRegistry**

Create `backend/app/plugins/registry.py`:

```python
"""Plugin Service Registry for cross-plugin communication.

Allows plugins to register named services that other plugins can discover
and consume. Services are namespaced by plugin name.
"""

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_NAMESPACE_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


class ServiceNotFoundError(Exception):
    """Raised when requesting an unregistered service."""


class ServiceRegistry:
    """Registry for plugin-provided services.

    Thread-safe via asyncio.Lock for writes.
    Reads are synchronous (safe in single event-loop thread).
    """

    _instance: Optional["ServiceRegistry"] = None

    def __init__(self) -> None:
        self._services: Dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def register(self, name: str, service: Any) -> None:
        """Register a service under a namespaced name.

        Args:
            name: Service name in format "{plugin_name}.{service_name}"
            service: Any object or callable to register

        Raises:
            ValueError: If name format is invalid or already registered
        """
        if not _NAMESPACE_RE.match(name):
            raise ValueError(
                f"Invalid service name '{name}': must match "
                f"'{{plugin_name}}.{{service_name}}' (lowercase, snake_case)"
            )
        async with self._lock:
            if name in self._services:
                raise ValueError(f"Service '{name}' is already registered")
            self._services[name] = service
            logger.debug("Registered service: %s", name)

    async def deregister(self, name: str) -> None:
        """Remove a single service.

        Args:
            name: Service name to remove. No-op if not found.
        """
        async with self._lock:
            if name in self._services:
                del self._services[name]
                logger.debug("Deregistered service: %s", name)
            else:
                logger.debug("Service not found for deregistration: %s", name)

    async def deregister_all(self, plugin_name: str) -> int:
        """Remove all services registered by a plugin.

        Args:
            plugin_name: Plugin name prefix

        Returns:
            Number of services removed
        """
        prefix = f"{plugin_name}."
        async with self._lock:
            to_remove = [k for k in self._services if k.startswith(prefix)]
            for key in to_remove:
                del self._services[key]
            if to_remove:
                logger.debug(
                    "Deregistered %d services for plugin %s",
                    len(to_remove), plugin_name,
                )
            return len(to_remove)

    def get(self, name: str) -> Any:
        """Get a registered service by name.

        Synchronous for convenience — safe because dict reads are atomic
        in CPython and all async callers run in the same event loop thread.

        Args:
            name: Fully qualified service name

        Returns:
            The registered service object

        Raises:
            ServiceNotFoundError: If the service is not registered
        """
        try:
            return self._services[name]
        except KeyError:
            raise ServiceNotFoundError(f"Service '{name}' is not registered")

    def list_services(self, plugin_name: Optional[str] = None) -> List[str]:
        """List registered service names.

        Args:
            plugin_name: Optional filter by plugin name prefix

        Returns:
            List of service names
        """
        if plugin_name:
            prefix = f"{plugin_name}."
            return [k for k in self._services if k.startswith(prefix)]
        return list(self._services.keys())

    @classmethod
    def get_instance(cls) -> "ServiceRegistry":
        """Get the singleton ServiceRegistry instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (for testing)."""
        cls._instance = None


def get_service_registry() -> ServiceRegistry:
    """Get the global ServiceRegistry singleton."""
    return ServiceRegistry.get_instance()
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `cd backend && python -m pytest tests/plugins/test_plugin_registry.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugins/registry.py backend/tests/plugins/test_plugin_registry.py
git commit -m "feat(plugins): add ServiceRegistry for cross-plugin service discovery"
```

---

### Task 9: Integrate Registry into Plugin Lifecycle

**Files:**
- Modify: `backend/app/plugins/base.py` (add `get_services()`)
- Modify: `backend/app/plugins/manager.py` (register/deregister in enable/disable)
- Modify: `backend/app/plugins/__init__.py` (new exports)

- [ ] **Step 1: Read base.py, manager.py, __init__.py**

- [ ] **Step 2: Add get_services() to PluginBase**

In `backend/app/plugins/base.py`, add after `get_default_config()`:
```python
def get_services(self) -> Dict[str, Any]:
    """Return services to register with the ServiceRegistry.

    Override to expose services that other plugins can consume.
    Keys are service names (without plugin prefix — prefix is added automatically).

    Returns:
        Dict mapping service names to service objects
    """
    return {}
```

- [ ] **Step 3: Integrate into PluginManager.enable_plugin()**

In `backend/app/plugins/manager.py`, in `enable_plugin()` after the event handler registration block, add:
```python
# Register services
services = plugin.get_services()
if services:
    from app.plugins.registry import get_service_registry
    registry = get_service_registry()
    for svc_name, svc_instance in services.items():
        await registry.register(f"{name}.{svc_name}", svc_instance)
```

- [ ] **Step 4: Integrate into PluginManager.disable_plugin()**

In `disable_plugin()`, before `on_shutdown()` call:
```python
# Deregister services
from app.plugins.registry import get_service_registry
registry = get_service_registry()
await registry.deregister_all(name)
```

- [ ] **Step 5: Update __init__.py exports**

In `backend/app/plugins/__init__.py`, add imports and update `__all__`:
```python
from app.plugins.base import DashboardPanelSpec
from app.plugins.registry import ServiceRegistry, get_service_registry, ServiceNotFoundError
```
Add `"DashboardPanelSpec"`, `"ServiceRegistry"`, `"get_service_registry"`, `"ServiceNotFoundError"` to `__all__`.

- [ ] **Step 6: Add integration test for auto-deregister on disable**

Add to `backend/tests/plugins/test_plugin_registry.py`:
```python
@pytest.mark.asyncio
async def test_auto_deregister_on_disable(tmp_path):
    """Services registered by a plugin are deregistered when the plugin is disabled."""
    from app.plugins.manager import PluginManager
    from app.plugins.registry import ServiceRegistry, get_service_registry

    # Reset singletons
    PluginManager.reset_instance()
    ServiceRegistry.reset_instance()

    # Create a minimal plugin that implements get_services()
    plugin_dir = tmp_path / "svc_plugin"
    plugin_dir.mkdir()
    (plugin_dir / "__init__.py").write_text('''
from app.plugins.base import PluginBase, PluginMetadata

class SvcPlugin(PluginBase):
    @property
    def metadata(self):
        return PluginMetadata(
            name="svc_plugin", version="0.1.0",
            description="Test", author="test",
            category="general",
        )

    def get_services(self):
        return {"greeter": lambda name: f"Hello {name}"}
''')

    mgr = PluginManager(plugins_dir=tmp_path)
    registry = get_service_registry()

    # Enable plugin — should auto-register services
    result = await mgr.enable_plugin("svc_plugin", granted_permissions=[], db=None)
    assert result is True
    svc = await registry.get("svc_plugin.greeter")
    assert svc("World") == "Hello World"

    # Disable plugin — should auto-deregister
    await mgr.disable_plugin("svc_plugin")
    assert await registry.list_services("svc_plugin") == {}

    # Cleanup
    PluginManager.reset_instance()
    ServiceRegistry.reset_instance()
```

- [ ] **Step 7: Run full test suite**

Run: `cd backend && python -m pytest --timeout=30 -x -q`
Expected: All pass

- [ ] **Step 8: Commit**

```bash
git add backend/app/plugins/base.py backend/app/plugins/manager.py backend/app/plugins/__init__.py backend/tests/plugins/test_plugin_registry.py
git commit -m "feat(plugins): integrate ServiceRegistry into plugin lifecycle"
```

---

## Feature 3: SDK CLI

### Task 10: Create Throttle Decorator

**Files:**
- Create: `backend/app/plugins/sdk/throttle.py`
- Create: `backend/app/plugins/sdk/__init__.py`
- Test: `backend/tests/plugins/test_plugin_sdk.py` (start with throttle tests)

- [ ] **Step 1: Write throttle tests**

Create `backend/tests/plugins/test_plugin_sdk.py` (start with throttle section):

```python
"""Tests for the Plugin SDK (throttle, scaffold, validator, CLI)."""

import time
from unittest.mock import MagicMock

import pytest


class TestThrottleDecorator:

    def test_first_call_executes(self):
        from app.plugins.sdk.throttle import throttle

        mock = MagicMock(return_value="ok")
        throttled = throttle(seconds=10)(mock)
        result = throttled()
        mock.assert_called_once()
        assert result == "ok"

    def test_skips_within_interval(self):
        from app.plugins.sdk.throttle import throttle

        mock = MagicMock(return_value="ok")
        throttled = throttle(seconds=10)(mock)
        throttled()
        result = throttled()
        assert mock.call_count == 1
        assert result is None

    def test_allows_after_interval(self, monkeypatch):
        from app.plugins.sdk.throttle import throttle

        fake_time = [100.0]
        monkeypatch.setattr(time, "monotonic", lambda: fake_time[0])

        mock = MagicMock(return_value="ok")
        throttled = throttle(seconds=5)(mock)

        throttled()
        assert mock.call_count == 1

        fake_time[0] = 106.0
        throttled()
        assert mock.call_count == 2

    def test_preserves_function_name(self):
        from app.plugins.sdk.throttle import throttle

        @throttle(seconds=1)
        def my_func():
            pass

        assert my_func.__name__ == "my_func"
```

- [ ] **Step 2: Run — verify failure**

Run: `cd backend && python -m pytest tests/plugins/test_plugin_sdk.py::TestThrottleDecorator -v`
Expected: FAIL — import error

- [ ] **Step 3: Create SDK package and throttle module**

Create `backend/app/plugins/sdk/__init__.py`:
```python
"""BaluHost Plugin SDK — tools for plugin development."""

from app.plugins.sdk.throttle import throttle

__all__ = ["throttle"]
```

Create `backend/app/plugins/sdk/throttle.py`:
```python
"""Throttle decorator for high-frequency plugin hooks.

Use this on hook implementations (e.g. on_telemetry_snapshot) to limit
how often the hook body actually executes. Calls within the interval
are silently skipped, returning None.
"""

import time
from functools import wraps
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def throttle(seconds: float) -> Callable[[F], F]:
    """Skip hook calls within the interval.

    Args:
        seconds: Minimum interval between actual executions.

    Returns:
        Decorator that wraps a function with throttle logic.

    Example::

        @hookimpl
        @throttle(seconds=30)
        def on_telemetry_snapshot(self, cpu_percent, ...):
            # Only runs once every 30 seconds
            self.log_metrics(cpu_percent)
    """
    def decorator(func: F) -> F:
        last_called = -float("inf")  # ensure first call always executes

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            nonlocal last_called
            now = time.monotonic()
            if now - last_called < seconds:
                return None
            last_called = now
            return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]
    return decorator
```

- [ ] **Step 4: Run tests — verify pass**

Run: `cd backend && python -m pytest tests/plugins/test_plugin_sdk.py::TestThrottleDecorator -v`
Expected: All 4 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugins/sdk/__init__.py backend/app/plugins/sdk/throttle.py backend/tests/plugins/test_plugin_sdk.py
git commit -m "feat(plugins/sdk): add @throttle decorator for high-frequency hooks"
```

---

### Task 11: Create Scaffold Module

**Files:**
- Create: `backend/app/plugins/sdk/scaffold.py`
- Add to: `backend/tests/plugins/test_plugin_sdk.py`

- [ ] **Step 1: Write scaffold tests**

Add to `backend/tests/plugins/test_plugin_sdk.py`:

```python
import ast

from app.plugins.sdk.scaffold import generate_plugin_code


class TestScaffold:

    def test_generates_valid_python(self):
        code = generate_plugin_code("test_plugin", category="general", author="Test")
        ast.parse(code)  # Should not raise SyntaxError

    def test_contains_metadata(self):
        code = generate_plugin_code("my_plugin", category="monitoring", author="Dev")
        assert 'name="my_plugin"' in code
        assert 'author="Dev"' in code
        assert 'category="monitoring"' in code

    def test_with_router_flag(self):
        code = generate_plugin_code("p", with_router=True)
        assert "get_router" in code
        assert "APIRouter" in code
        ast.parse(code)

    def test_with_background_task_flag(self):
        code = generate_plugin_code("p", with_background_task=True)
        assert "get_background_tasks" in code
        assert "BackgroundTaskSpec" in code
        assert "task:background" in code  # auto-added permission
        ast.parse(code)

    def test_with_dashboard_panel_flag(self):
        code = generate_plugin_code("p", with_dashboard_panel=True)
        assert "get_dashboard_panel" in code
        assert "DashboardPanelSpec" in code
        ast.parse(code)

    def test_with_service_flag(self):
        code = generate_plugin_code("p", with_service=True)
        assert "get_services" in code
        ast.parse(code)

    def test_all_flags_combined(self):
        code = generate_plugin_code(
            "full_plugin",
            category="monitoring",
            author="Test",
            with_router=True,
            with_background_task=True,
            with_dashboard_panel=True,
            with_service=True,
        )
        ast.parse(code)
        assert "get_router" in code
        assert "get_background_tasks" in code
        assert "get_dashboard_panel" in code
        assert "get_services" in code

    def test_category_monitoring_hook(self):
        code = generate_plugin_code("p", category="monitoring")
        assert "on_telemetry_snapshot" in code
        assert "throttle" in code

    def test_category_storage_hook(self):
        code = generate_plugin_code("p", category="storage")
        assert "on_file_uploaded" in code

    def test_category_network_hook(self):
        code = generate_plugin_code("p", category="network")
        assert "on_vpn_client_created" in code

    def test_category_security_hook(self):
        code = generate_plugin_code("p", category="security")
        assert "on_user_login" in code

    def test_category_general_hook(self):
        code = generate_plugin_code("p", category="general")
        assert "on_system_startup" in code
```

- [ ] **Step 2: Run — verify failure**

Run: `cd backend && python -m pytest tests/plugins/test_plugin_sdk.py::TestScaffold -v`
Expected: FAIL — import error

- [ ] **Step 3: Implement scaffold.py**

Create `backend/app/plugins/sdk/scaffold.py`. Use f-strings to build the `__init__.py` content. The function signature:

```python
def generate_plugin_code(
    plugin_name: str,
    category: str = "general",
    author: str = "BaluHost Community",
    with_router: bool = False,
    with_background_task: bool = False,
    with_dashboard_panel: bool = False,
    with_service: bool = False,
) -> str:
```

Build the code string section by section:
1. Module docstring
2. Imports (conditional on flags)
3. Plugin class with metadata property
4. on_startup/on_shutdown stubs
5. Conditional method blocks per flag
6. Hook example matching category
7. Inline "Step N" and "Why" comments

The `--with-background-task` flag auto-adds `"task:background"` to `required_permissions`.

- [ ] **Step 4: Run tests — verify pass**

Run: `cd backend && python -m pytest tests/plugins/test_plugin_sdk.py::TestScaffold -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugins/sdk/scaffold.py backend/tests/plugins/test_plugin_sdk.py
git commit -m "feat(plugins/sdk): add scaffold module for plugin code generation"
```

---

### Task 12: Create Validator Module

**Files:**
- Create: `backend/app/plugins/sdk/validator.py`
- Add to: `backend/tests/plugins/test_plugin_sdk.py`

- [ ] **Step 1: Write validator tests**

Add to `backend/tests/plugins/test_plugin_sdk.py`:

```python
from app.plugins.sdk.validator import validate_plugin, ValidationResult


class TestValidator:

    def test_validate_valid_plugin(self, tmp_path):
        """A well-formed plugin passes all checks."""
        plugin_dir = tmp_path / "good_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text('''
from app.plugins.base import PluginBase, PluginMetadata

class GoodPlugin(PluginBase):
    @property
    def metadata(self):
        return PluginMetadata(
            name="good_plugin", version="1.0.0", display_name="Good",
            description="A good plugin", author="Test",
        )
''')
        result = validate_plugin("good_plugin", plugins_dir=tmp_path)
        assert result.passed
        assert not result.failures

    def test_validate_missing_metadata_fields(self, tmp_path):
        """Plugin with empty description should fail."""
        plugin_dir = tmp_path / "bad_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text('''
from app.plugins.base import PluginBase, PluginMetadata

class BadPlugin(PluginBase):
    @property
    def metadata(self):
        return PluginMetadata(
            name="bad_plugin", version="1.0.0", display_name="Bad",
            description="", author="Test",
        )
''')
        result = validate_plugin("bad_plugin", plugins_dir=tmp_path)
        assert not result.passed
        assert any("description" in f.lower() for f in result.failures)

    def test_validate_unknown_permission(self, tmp_path):
        """Plugin requesting non-existent permission should fail."""
        plugin_dir = tmp_path / "perm_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text('''
from app.plugins.base import PluginBase, PluginMetadata

class PermPlugin(PluginBase):
    @property
    def metadata(self):
        return PluginMetadata(
            name="perm_plugin", version="1.0.0", display_name="Perm",
            description="Test", author="Test",
            required_permissions=["foo:bar"],
        )
''')
        result = validate_plugin("perm_plugin", plugins_dir=tmp_path)
        assert not result.passed
        assert any("foo:bar" in f for f in result.failures)

    def test_validate_circular_dependency(self, tmp_path):
        """Plugins with circular dependencies should fail."""
        for name, dep in [("plugin_a", "plugin_b"), ("plugin_b", "plugin_a")]:
            d = tmp_path / name
            d.mkdir()
            (d / "__init__.py").write_text(f'''
from app.plugins.base import PluginBase, PluginMetadata

class P(PluginBase):
    @property
    def metadata(self):
        return PluginMetadata(
            name="{name}", version="1.0.0", display_name="{name}",
            description="Test", author="Test", dependencies=["{dep}"],
        )
''')
        result = validate_plugin("plugin_a", plugins_dir=tmp_path)
        assert not result.passed
        assert any("circular" in f.lower() for f in result.failures)
```

- [ ] **Step 2: Run — verify failure**

Run: `cd backend && python -m pytest tests/plugins/test_plugin_sdk.py::TestValidator -v`
Expected: FAIL — import error

- [ ] **Step 3: Implement validator.py**

Create `backend/app/plugins/sdk/validator.py`:

```python
"""Plugin contract validator.

Loads a plugin and checks it against BaluHost plugin contracts:
metadata completeness, permission validity, dependency resolution.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of plugin validation."""
    plugin_name: str
    passes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.failures) == 0


def validate_plugin(
    plugin_name: str,
    plugins_dir: Optional[Path] = None,
) -> ValidationResult:
    ...
```

Implement checks:
1. Load plugin via PluginManager (use provided plugins_dir)
2. Check metadata fields non-empty: name, version, display_name, author, description
3. Check name matches directory name
4. Check required_permissions exist in PluginPermission enum values
5. Warn on dangerous permissions
6. Check dependencies exist as installed plugins
7. Check for direct circular dependencies (A→B→A)
8. If SmartDevicePlugin: call validate_capability_contracts()

- [ ] **Step 4: Run tests — verify pass**

Run: `cd backend && python -m pytest tests/plugins/test_plugin_sdk.py::TestValidator -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugins/sdk/validator.py backend/tests/plugins/test_plugin_sdk.py
git commit -m "feat(plugins/sdk): add plugin contract validator"
```

---

### Task 13: Create CLI and Entry-Points

**Files:**
- Create: `backend/app/plugins/sdk/cli.py`
- Create: `backend/app/plugins/sdk/__main__.py`
- Modify: `backend/pyproject.toml`
- Add to: `backend/tests/plugins/test_plugin_sdk.py`

- [ ] **Step 1: Write CLI tests**

Add to `backend/tests/plugins/test_plugin_sdk.py`:

```python
from click.testing import CliRunner
from app.plugins.sdk.cli import cli


class TestCLI:

    def test_create_generates_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "app.plugins.sdk.cli.PLUGINS_DIR", tmp_path,
        )
        runner = CliRunner()
        result = runner.invoke(cli, ["create", "my_plugin", "--author", "Test"])
        assert result.exit_code == 0
        init_file = tmp_path / "my_plugin" / "__init__.py"
        assert init_file.exists()

    def test_create_existing_aborts(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.plugins.sdk.cli.PLUGINS_DIR", tmp_path)
        (tmp_path / "existing").mkdir()
        (tmp_path / "existing" / "__init__.py").write_text("# exists")
        runner = CliRunner()
        result = runner.invoke(cli, ["create", "existing"])
        assert result.exit_code != 0

    def test_create_existing_with_force(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.plugins.sdk.cli.PLUGINS_DIR", tmp_path)
        (tmp_path / "existing").mkdir()
        (tmp_path / "existing" / "__init__.py").write_text("# old")
        runner = CliRunner()
        result = runner.invoke(cli, ["create", "existing", "--force"])
        assert result.exit_code == 0

    def test_list_command(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.plugins.sdk.cli.PLUGINS_DIR", tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
```

- [ ] **Step 2: Run — verify failure**

Run: `cd backend && python -m pytest tests/plugins/test_plugin_sdk.py::TestCLI -v`
Expected: FAIL — import error

- [ ] **Step 3: Implement cli.py**

Create `backend/app/plugins/sdk/cli.py`:

```python
"""BaluHost Plugin SDK CLI.

Provides commands for creating, validating, and listing plugins.

Usage:
    baluhost-sdk create <plugin_name> [options]
    baluhost-sdk validate <plugin_name>
    baluhost-sdk list
"""

import sys
from pathlib import Path

import click

from app.plugins.sdk.scaffold import generate_plugin_code

# Default plugins directory — can be overridden in tests
PLUGINS_DIR = Path(__file__).parent.parent / "installed"


@click.group()
def cli() -> None:
    """BaluHost Plugin SDK — create, validate, and manage plugins."""


@cli.command()
@click.argument("plugin_name")
@click.option(
    "--category",
    type=click.Choice(["monitoring", "storage", "network", "security", "general"]),
    default="general",
    help="Plugin category",
)
@click.option("--author", default="BaluHost Community", help="Plugin author")
@click.option("--with-router", is_flag=True, help="Add example APIRouter")
@click.option("--with-background-task", is_flag=True, help="Add example BackgroundTask")
@click.option("--with-dashboard-panel", is_flag=True, help="Add DashboardPanelSpec")
@click.option("--with-service", is_flag=True, help="Add get_services() example")
@click.option("--force", is_flag=True, help="Overwrite existing plugin")
def create(plugin_name, category, author, with_router, with_background_task,
           with_dashboard_panel, with_service, force):
    """Create a new plugin from template."""
    plugin_dir = PLUGINS_DIR / plugin_name
    if plugin_dir.exists() and not force:
        click.echo(f"Error: Plugin '{plugin_name}' already exists. Use --force to overwrite.", err=True)
        sys.exit(1)

    plugin_dir.mkdir(parents=True, exist_ok=True)
    code = generate_plugin_code(
        plugin_name=plugin_name,
        category=category,
        author=author,
        with_router=with_router,
        with_background_task=with_background_task,
        with_dashboard_panel=with_dashboard_panel,
        with_service=with_service,
    )
    (plugin_dir / "__init__.py").write_text(code)
    click.echo(f"Created plugin: {plugin_dir / '__init__.py'}")


@cli.command()
@click.argument("plugin_name")
def validate(plugin_name):
    """Validate an installed plugin against contracts."""
    from app.plugins.sdk.validator import validate_plugin
    result = validate_plugin(plugin_name, plugins_dir=PLUGINS_DIR)

    click.echo(f"Plugin: {result.plugin_name}")
    for p in result.passes:
        click.echo(f"  [pass]  {p}")
    for w in result.warnings:
        click.echo(f"  [warn]  {w}")
    for f in result.failures:
        click.echo(f"  [fail]  {f}")

    if not result.passed:
        sys.exit(1)


@cli.command("list")
def list_plugins():
    """List all installed plugins with metadata."""
    if not PLUGINS_DIR.exists():
        click.echo("No plugins directory found.")
        return

    from app.plugins.manager import PluginManager
    mgr = PluginManager(plugins_dir=PLUGINS_DIR)

    for path in sorted(PLUGINS_DIR.iterdir()):
        if path.is_dir() and (path / "__init__.py").exists():
            try:
                plugin = mgr.load_plugin(path.name)
                meta = plugin.metadata
                click.echo(f"  {meta.name} v{meta.version} [{meta.category}] — {meta.author}")
            except Exception as e:
                click.echo(f"  {path.name} [error] — {e}")
```

- [ ] **Step 4: Create __main__.py**

Create `backend/app/plugins/sdk/__main__.py`:
```python
"""Allow running SDK as module: python -m app.plugins.sdk"""

from app.plugins.sdk.cli import cli

cli()
```

- [ ] **Step 5: Add entry-point to pyproject.toml**

Read `backend/pyproject.toml` first. In the `[project.scripts]` section, add:
```toml
baluhost-sdk = "app.plugins.sdk.cli:cli"
```

- [ ] **Step 6: Run tests — verify pass**

Run: `cd backend && python -m pytest tests/plugins/test_plugin_sdk.py::TestCLI -v`
Expected: All PASS

- [ ] **Step 7: Run FULL test suite**

Run: `cd backend && python -m pytest --timeout=30 -x -q`
Expected: All pass — no regressions across all 3 features

- [ ] **Step 8: Commit**

```bash
git add backend/app/plugins/sdk/cli.py backend/app/plugins/sdk/__main__.py backend/pyproject.toml backend/tests/plugins/test_plugin_sdk.py
git commit -m "feat(plugins/sdk): add CLI with create, validate, list commands"
```

---

### Task 14: Final Integration Test & Cleanup

- [ ] **Step 1: Run full test suite**

Run: `cd backend && python -m pytest --timeout=30 -v`
Expected: All tests pass including all new test files

- [ ] **Step 2: Verify SDK CLI works end-to-end**

Run: `cd backend && python -m app.plugins.sdk create test_sdk_plugin --category monitoring --with-router --with-service --author "Test"`
Expected: Creates `backend/app/plugins/installed/test_sdk_plugin/__init__.py`

Run: `cd backend && python -m app.plugins.sdk validate test_sdk_plugin`
Expected: All checks pass

Run: `cd backend && python -m app.plugins.sdk list`
Expected: Shows all installed plugins including test_sdk_plugin

- [ ] **Step 3: Clean up test plugin**

Remove the test plugin created in step 2:
```bash
rm -rf backend/app/plugins/installed/test_sdk_plugin
```

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat(plugins): complete Plugin SDK — hooks wired, registry, CLI"
```
